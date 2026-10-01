"""Native repair-related Retail, partial actual return and frozen bundle sales.

Unregistered candidate. Only original employee forms write; all DB access is
SELECT. Synthetic bank/reference intent is declared before the first receipt.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import require
from sales_order_business import fixed_dependency, fen_text
from vehicle_purchase_business import checkbox, live_choice, select_value, rejected_submit
from finance_business import get_match, original_form, submit
import boutique_business as BT
import material_business as MAT
import member_followon_business as MF
import repair_business as REP

SCENARIO = "retail-repair-return-bundle-hk063-066-067-068"
RETAIL, BUNDLE = "/api/retail", "/api/retail-bundles"
REQUIREMENTS = (("HK-063", "维修精品销售单"), ("HK-066", "维修精品销售出库"),
                ("HK-067", "精品销售退货"), ("HK-068", "精品销售套餐设置"))
VERSION, CASE, TASK, FLOW = BT.VERSION, BT.CASE, BT.TASK, BT.FLOW
TABLES = BT.TABLES | {"retail_returns", "retail_return_lines", "retail_return_postings",
    "retail_bundle_rules", "retail_bundle_components", "retail_bundle_sales",
    "retail_bundle_allocations", "retail_bundle_receipts"}
FIELDS = BT.FIELDS | {"rule_id", "sale_id", "dispatch_id", "return_line_id", "line_id"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def business_day():
    # Matches the external fixture's explicit APP_TIMEZONE, without app import.
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def rows(e, table):
    require(table in TABLES, "未审阅原表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {BT.pk(table)}")


def one(e, table, key):
    require(table in TABLES and type(key) is int and key > 0, "必须明确原ID")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {BT.pk(table)}=?", (key,))
    require(len(found) == 1, "原来源缺失/重复：" + table + "/" + str(key))
    return found[0]


def subset(e, table, field, key):
    require(table in TABLES and field in FIELDS, "未审阅原关联")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {BT.pk(table)}", (key,))


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]), "原合同错配：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__).read_bytes()),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "business_accepted": False, "human_acceptance": "pending",
            "contract_rules": {"automatic_pass_is_not_business_acceptance": True,
                "human_six_criteria_review": "pending", "untested_conditions_are_not_passed": True,
                "unknown_result_replay": False, "deliberately_misrecorded_reference_is_not_corrected": True},
            "requirements": [{"id": k, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": k + "-business", "check_id": k + "-business", "status": "not_tested",
                    "criteria": ["本人原UI和非空原事实", "原API/DB/Task/CAS/回执一致",
                        "原库存成本/安装/收退款各自关联", "所有无关旧行和原件字节保护"], "evidence": {}}]}
                for k, title in REQUIREMENTS],
            "conditional_checks": [{"status": "not_tested", "scope": s} for s in (
                "HK071授权两店非空库存/非零在途/汇总与未授权阴性", "HK086原款误录更正",
                "不可售退货整改复检/拒收交回、退货撤销及多次最后余分",
                "套餐下一版/停售/历史版和套餐原组件退货", "混合会员权益退款、并发及重复提交",
                "人工六类标准、PostgreSQL、Linux、真实银行/实物/ClamAV/模型及生产门槛")],
            "conditions": {"synthetic_inputs_only": True, "prebuilt_business_results": False,
                "actual_bank_or_company_handover": False, "file_scan": "structure_only_not_clamav"}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] in {"not_tested", "running"}, "不可重复领取已执行check")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.save()

    def note(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].setdefault("steps", []).append(value)
        self.save()

    async def passed(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active["acceptance_checks"][0].update(status="passed", evidence=value)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active = None
        self.save()

    def failed(self, error):
        for r in self.report["requirements"]:
            if r["status"] == "running":
                status = "failed" if r is self.active else "partial"
                r["status"] = r["acceptance_checks"][0]["status"] = status
                r["acceptance_checks"][0]["error"] = self.e.scrub(error)
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "sources_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "四原业务链未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=4, passed_requirements=4, report_sources=sources)
        self.save()
        self.e.observe("retail_remaining_original_checkpoint", {"path": str(self.path), "passed_checks": 4,
            "human_acceptance": "pending", "business_accepted": False, "full_193_business_acceptance": False})


class Guard:
    """Whole database hashes, finite old IDs/columns and exact new identities."""
    def __init__(self, e, label, actor, *, append, update=None, cases=(), items=(), new_customer=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = dict(append), update or {}
        self.cases, self.items, self.customer = set(cases), set(items), new_customer
        require(self.append.keys() | self.update.keys() <= TABLES, "本次守卫越过有限原表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
            if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "影响无关原表：" + str(sorted(changed)))
        self.added = {t: [r for r in rows(self.e, t) if r[BT.pk(t)] not in {o[BT.pk(t)] for o in old}]
            for t, old in self.old.items()}
        for t, added in self.added.items():
            n = self.append.get(t, 0)
            lo, hi = n if isinstance(n, tuple) else (n, n)
            require(lo <= len(added) <= hi, "原新增数不符：" + t + "/" + str(len(added)))
        created = self.added.get("flow_cases", [])
        require(not created or len(created) == 1 and created[0]["kind"] == "retail" and created[0]["flow_version"] == 2
            and created[0]["customer_id"] == self.customer and created[0]["created_by"] == created[0]["owner_id"] == self.actor["id"], "新Retail身份/客户不符")
        cases = self.cases | {r["id"] for r in created}
        rules = {r["id"] for r in self.added.get("retail_bundle_rules", [])}
        cash = {r["id"] for r in self.added.get("cash_entries", [])}
        modified = {}
        for t, prior in self.old.items():
            current = {r[BT.pk(t)]: r for r in rows(self.e, t)}
            modified[t] = []
            for old in prior:
                key = old[BT.pk(t)]
                require(key in current, "不可删除旧事实：" + t)
                columns = {k for k in old if old[k] != current[key][k]}
                require(columns <= self.update.get(t, {}).get(key, set()), "覆盖未允许原列：" + t + "/" + str(key) + "/" + str(sorted(columns)))
                if t == "flow_cases" and "data" in columns:
                    a, b = json.loads(old["data"]), json.loads(current[key]["data"])
                    require(all(k in b and b[k] == v for k, v in a.items()), "正向原单不能覆盖既有事实")
                if columns:
                    modified[t].append({"id": key, "columns": sorted(columns)})
            for r in self.added[t]:
                if "store_id" in r:
                    require(r["store_id"] == 1, "新增事实串店：" + t)
                if "case_id" in r:
                    require(r["case_id"] in cases, "新增事实串原单：" + t)
                if "item_id" in r:
                    require(r["item_id"] in self.items, "新增事实串商品：" + t)
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in r and r[field] is not None:
                        require(r[field] == self.actor["id"], "新增事实借身份：" + t)
                if t == "audit_logs":
                    require(r["entity_id"] in {"flow": cases, "cash": cash, "retail_bundle_rule": rules}.get(r["entity_type"], set()), "审计串来源")
                if t == "membership_points_claims":
                    require(r["rule_id"] is None and r["member_id"] is None, "非会员纯现金不能编造奖分")
        value = {"label": self.label, "changed_tables": sorted(changed),
            "appended_ids": {t: [r[BT.pk(t)] for r in added] for t, added in self.added.items()},
            "updated_columns": modified, "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("retail_remaining_original_row_guard", value)
        return value


def events(e, guard, key, actions):
    found = guard.added["flow_events"]
    require(len(found) == len(actions) and [r["action"] for r in found] == actions
        and all(r["case_id"] == key and r["actor_id"] == guard.actor["id"] for r in found), "本次原事件缺失/串原单")
    audits = [r for r in guard.added["audit_logs"] if r["entity_type"] == "flow"]
    require(len(audits) == len(actions) and [r["action"] for r in audits] == ["flow_" + a for a in actions]
        and all(r["entity_id"] == key and r["actor_id"] == guard.actor["id"] for r in audits), "本次原事件审计缺失/借身份")
    return [{"event_id": r["id"], "action": r["action"], "detail": json.loads(r["detail"])} for r in found]


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "仅允许同轮外部合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(not root.is_relative_to(Path(e.manifest["source_root"]).resolve())
        and Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "证据/DB不是仓库外同轮runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance.get("snapshot_stable") is True, "同轮源码快照不稳定")
    for name in ("retail_remaining_business.py", "boutique_business.py", "repair_business.py", "member_followon_business.py",
        "material_business.py", "finance_business.py", "vehicle_purchase_business.py", "sales_business.py",
        "sales_order_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "脚本不是同轮指纹：" + name)
    boutique, repair = [fixed_dependency(e, cp, name) for name in (BT.SCENARIO, REP.SCENARIO)]
    bs, rs = boutique["report_sources"], repair["report_sources"]
    require(len(bs["item_ids"]) == 2 and len(set(bs["item_ids"])) == 2, "缺本轮精品两件明确来源")
    customer, original, account = one(e, "flow_customers", rs["customer_id"]), one(e, "flow_cases", rs["repair_case_id"]), one(e, "flow_accounts", bs["account_id"])
    location, warehouse, work = one(e, "master_locations", bs["location_id"]), one(e, "master_warehouses", bs["warehouse_id"]), one(e, "master_work_items", bs["work_item_id"])
    require(original["kind"] == "repair" and original["customer_id"] == customer["id"] and original["state"] == "completed"
        and json.loads(original["data"]).get("released_date") and customer["phone"] and customer["contact_allowed"]
        and account["active"] == location["active"] == warehouse["active"] == work["active"] == 1
        and location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials"
        and all(r["store_id"] == 1 for r in (customer, original, account, location, warehouse, work)), "原维修/客户/现金/库位前序不符")
    require(not e.db.rows("SELECT m.id FROM group_members m JOIN group_identity_links l ON l.identity_id=m.identity_id WHERE l.store_id=1 AND l.local_kind='customer' AND l.local_id=? AND m.active=1", (customer["id"],)), "当前客户已另开会员，不能沿用非会员奖分合同")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=1"), "缺实体策略完整前序，不能宽放业务实体")
    items = [one(e, "flow_items", key) for key in bs["item_ids"]]
    for item, needed in zip(items, (2000, 1000)):
        balances = subset(e, "warehouse_balances", "item_id", item["id"])
        source = [b for b in balances if b["location_id"] == location["id"] and b["transit_case_id"] is None]
        occupied = sum(r["quantity_milli"] for r in subset(e, "retail_reservations", "item_id", item["id"]))
        require(item["store_id"] == 1 and item["active"] == 1 and item["quantity_milli"] >= needed
            and item["quantity_milli"] - occupied >= needed and len(source) == 1 and source[0]["quantity_milli"] >= needed
            and sum(b["quantity_milli"] for b in balances if b["id"] != source[0]["id"]) == 0, "当前真实可用量/原精品库位不足或另有分布")
        enrollments = subset(e, "warehouse_enrollments", "item_id", item["id"])
        profiles = subset(e, "master_item_profiles", "item_id", item["id"])
        require(len(enrollments) == len(profiles) == 1 and profiles[0]["id"] in bs["profile_ids"]
            and profiles[0]["location_id"] == location["id"] and profiles[0]["brand_id"] == bs["brand_id"]
            and profiles[0]["category_id"] == bs["category_id"] and enrollments[0]["id"] in bs["enrollment_ids"], "精品主档/原库位启用不是同轮有限来源")
    fixture = {**e.manifest["business_fixtures"]["sales_order"], **e.manifest["business_fixtures"]["repair"]}
    for role in ("service", "manager", "inventory", "technician", "finance"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=1 AND role=?", (actor["id"], role))) == 1, "缺本店真实岗位：" + role)
    cp.report["source_preconditions"] = {"boutique": bs, "repair": rs, "current_items": items,
        "current_original_repair": original, "customer": customer, "account": account, "work": work,
        "location": location, "warehouse": warehouse, "provenance_sha256": sha(raw)}
    cp.save()
    return fixture, customer, original, account, items, work, location


async def retail_read(e, context, credentials, fixture, role, key):
    actor, view = await BT.retail_read(e, context, credentials, fixture, role, key)
    require(not view.get("member_pricing") and not subset(e, "retail_group_plans", "case_id", key), "本批独立纯现金原单不能混入会员优惠/资金")
    return actor, view


def portion(value, quantity, remaining):
    require(type(value) is int and value >= 0 and 0 < quantity <= remaining, "原成本必须已知整数且数量足够")
    return value if quantity == remaining else (2 * value * quantity + remaining) // (2 * remaining)


async def ordinary_create(e, context, credentials, fixture, customer, repair, item, work):
    actor, _ = await BT.read_as(e, context, credentials, fixture, "service", "retail", RETAIL + "/orders", "精品销售与退货")
    await e.click('#main [data-act="retail-new"]', "创建维修附带独立精品单")
    await expect(e.page.locator("#modal-title")).to_have_text("新建精品订单")
    label = await e.page.locator(f'#modal [name="customer"] option[value="{customer["id"]}"]').text_content()
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases"
        and parse_qs(urlsplit(r.url).query).get("kind") == ["repair"] and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        await live_choice(e, "customer", customer["name"], label, expected_value=customer["id"])
    require((await pending.value).status == 200, "同客户原维修候选未完成读取")
    await expect(e.page.locator('#modal [data-member-price-field]')).not_to_have_attribute("data-loading", "true")
    label = await e.page.locator(f'#modal [name="related"] option[value="{repair["id"]}"]').text_content()
    await live_choice(e, "related", repair["number"], label, expected_value=repair["id"])
    line = e.page.locator('#modal [data-retail-line]')
    await expect(line).to_have_count(1)
    for field, query, row in (("item", item["sku"], item), ("work", work["code"], work)):
        label = await line.locator(f'[name="{field}"] option[value="{row["id"]}"]').text_content()
        await MAT.choose(e, line, f'[name="{field}"]', query, label, row["id"])
    for field, value in (("quantity", "1.000"), ("price", "20.00"), ("install_price", "5.00")):
        e.action("fill", "明确独立商品和安装金额：" + field)
        await line.locator(f'[name="{field}"]').fill(value)
    await e.fill('#modal [name="discount"]', "0.00", "本批不猜优惠")
    await select_value(e, '#modal [name="member_pricing_rule"]', "", "非会员不选择价格规则")
    before_item = one(e, "flow_items", item["id"])
    values = {"customer_id": customer["id"], "related_repair_id": repair["id"], "discount_cents": 0,
        "lines": [{"item_id": item["id"], "quantity_milli": 1000, "unit_price_cents": 2000,
            "work_item_id": work["id"], "installation_unit_price_cents": 500}]}
    guard = Guard(e, "retail_related_create", actor, append={**FLOW, "flow_cases": 1, "flow_tasks": 1,
        "retail_orders": 1, "retail_lines": 1, "retail_reservations": 1}, update={"flow_items": {item["id"]: VERSION}},
        items={item["id"]}, new_customer=customer["id"])
    body, request, shown, native = await MF.submit_created(e, RETAIL + "/orders", RETAIL + "/orders/", status=201, body_key=("id",))
    key = body["id"]
    require(request == {"request_id": request["request_id"], **values} and shown["state"] == "approval"
        and shown["amount_cents"] == 2500 and shown["related_repair_id"] == repair["id"] and shown["revision"] == 1, "维修关联/独立报价原封包不符")
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_create"]),
        receipt=MF.flow_receipt(e, request, actor, key, "retail_create", values))
    frozen = guard.added["retail_lines"][0]
    require(frozen["goods_cents"] == 2000 and frozen["installation_cents"] == 500 and frozen["quantity_milli"] == 1000
        and frozen["work_code"] == work["code"] and guard.added["retail_reservations"][0]["reason"] == "reserve"
        and guard.added["retail_reservations"][0]["quantity_milli"] == 1000
        and one(e, "flow_items", item["id"])["quantity_milli"] == before_item["quantity_milli"]
        and one(e, "flow_items", item["id"])["inventory_value_cents"] == before_item["inventory_value_cents"], "冻结报价占额不能作实物出库")
    await expect(e.page.locator('#main h1')).to_have_text("精品销售 · " + body["number"])
    return key, {"native": native, "order": one(e, "retail_orders", key), "line": frozen,
        "reservation": guard.added["retail_reservations"][0], "amount_cents": 2500}


async def retail_action(e, context, credentials, fixture, key, action, items, amount, token):
    role, task_key, title, category = {
        "approve": ("manager", "retail_approve", "主管价格授权", None),
        "authorize": ("service", "retail_authorize", "记录客户报价确认", "authorization"),
        "dispatch": ("inventory", "retail_dispatch", "确认整单实际出库", "evidence"),
        "install": ("technician", "retail_install", "确认实际安装", "evidence"),
        "accept": ("service", "retail_accept", "确认客户接收", "evidence"),
    }[action]
    handoff = await BT.responsible(e, context, credentials, fixture, key, task_key, role)
    actor, view = await retail_read(e, context, credentials, fixture, role, key)
    proof = await MF.upload(e, actor, key, None, RETAIL + f"/orders/{key}", category,
        "retail-remaining-" + action + "-" + str(key), token) if category else None
    case = one(e, "flow_cases", key)
    old_items = {i["id"]: one(e, "flow_items", i["id"]) for i in items}
    await original_form(e, "retail-action", action, title)
    values = {"evidence_id": proof["file"]["id"]} if proof else {}
    if action == "approve":
        values = {"minimum_total_cents": amount, "allow_below_minimum": False,
            "reason": "独立核对本单冻结商品与安装总价" + fen_text(amount) + "元"}
        await e.fill('#modal [name="minimum"]', fen_text(amount), "独立主管明确原最低成交金额")
        await checkbox(e, '#modal [name="allow_below_minimum"]', False, "无低价例外")
        await e.fill('#modal [name="reason"]', values["reason"], "独立价格复核依据")
        require(actor["id"] != case["created_by"], "开单人不能批准本单")
    elif action == "authorize":
        values["revision"] = 1
    elif action == "install":
        values["result"] = "本人已实际完成本单明确作业安装并核对数量；其他商品无需安装"
        await e.fill('#modal [name="result"]', values["result"], "本人实际安装结果")
    if proof:
        await MF.choose_file(e, proof, category)
    append, permitted, allocations = {**FLOW, "flow_tasks": (0, 2)}, BT.updates(e, key), []
    if action == "authorize":
        append["membership_points_claims"] = 1
    if action == "dispatch":
        for item in items:
            matches = [a for a in subset(e, "warehouse_allocations", "case_id", key)
                if a["item_id"] == item["id"] and a["purpose"] == "retail_dispatch" and a["status"] == "prepared"
                and a["quantity_milli"] == -1000]
            require(len(matches) == 1, "实际出库缺唯一当前原准备")
            allocations.extend(matches)
        append.update(retail_reservations=len(items), flow_stock_moves=len(items), retail_dispatches=len(items), warehouse_entries=len(items))
        permitted = BT.updates(e, key, items=set(old_items), balances=True)
        permitted["warehouse_allocations"] = {a["id"]: VERSION | {"status", "stock_move_id"} for a in allocations}
    guard = Guard(e, "retail_" + action + "_" + str(key), actor, append=append, update=permitted, cases={key}, items=set(old_items))
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/{action}", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}
        and shown["version"] == one(e, "flow_cases", key)["version"] > case["version"], "原动作当前CAS/内容不符")
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_" + action]), handoff=handoff, proof=proof,
        receipt=MF.flow_receipt(e, request, actor, key, "retail_" + action, {"case_id": key, "version": case["version"], "values": values}))
    data = json.loads(one(e, "flow_cases", key)["data"])
    flag = {"approve": "approved", "authorize": "authorized", "dispatch": "dispatched", "install": "installed", "accept": "accepted_date"}[action]
    require(bool(data.get(flag)), "原动作没有真实结果：" + flag)
    if action == "authorize":
        require(guard.added["membership_points_claims"][0]["member_id"] is None
            and guard.added["membership_points_claims"][0]["rule_id"] is None, "非会员不能借冻结奖分规则")
    if action == "dispatch":
        for item in items:
            original_item = old_items[item["id"]]
            cost = portion(original_item["inventory_value_cents"], 1000, original_item["quantity_milli"])
            move = next(r for r in guard.added["flow_stock_moves"] if r["item_id"] == item["id"])
            dispatch = next(r for r in guard.added["retail_dispatches"] if r["stock_move_id"] == move["id"])
            allocation = next(a for a in allocations if a["item_id"] == item["id"])
            entry = next(r for r in guard.added["warehouse_entries"] if r["stock_move_id"] == move["id"])
            after = one(e, "flow_items", item["id"])
            require(move["quantity_milli"] == -1000 and move["value_cents"] == -cost and move["purpose"] == "retail_dispatch"
                and move["original_id"] is None and dispatch["quantity_milli"] == 1000 and dispatch["value_cents"] == cost
                and dispatch["evidence_id"] == proof["file"]["id"] and entry["quantity_milli"] == -1000 and entry["value_cents"] == -cost
                and one(e, "warehouse_allocations", allocation["id"])["status"] == "consumed"
                and one(e, "warehouse_allocations", allocation["id"])["stock_move_id"] == move["id"]
                and after["quantity_milli"] == original_item["quantity_milli"] - 1000
                and after["inventory_value_cents"] == original_item["inventory_value_cents"] - cost, "实物出库/成本/准备/仓位没有守恒")
        require(all(r["quantity_milli"] == -1000 and r["reason"] == "dispatch" for r in guard.added["retail_reservations"]), "原占量未释放")
        native.update(dispatches=guard.added["retail_dispatches"], stock_moves=guard.added["flow_stock_moves"],
            warehouse_entries=guard.added["warehouse_entries"], released_reservations=guard.added["retail_reservations"])
    return native


async def bank_receipt(e, actor, key, token, declaration):
    """Actual original file upload; metadata leaves the in-memory BLOB guard."""
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    file = directory / ("retail-A-bank-source-" + token + ".txt")
    content = ("合成实际到账样例，不表示真实银行支付。\n" + json.dumps(declaration, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    file.write_bytes(content)
    await e.click('#main [data-act="upload"]', "本人上传事前声明的合成原到账凭据")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', "receipt", "选择原收退款凭据类别")
    e.action("select_file", "选择带正确BANK编号及误录声明的原件", name=file.name, sha256=sha(content))
    await e.page.locator('#modal [name="file"]').set_input_files(str(file))
    guard = MF.Guard(e, "retail_A_bank_upload", actor,
        append={**MF.FLOW, "flow_files": 1, "file_security": 1, "file_scan_events": 1}, cases={key}, member=None)
    body, _, _, native = await submit(e, f"/api/flow/cases/{key}/files", RETAIL + f"/orders/{key}", multipart=True)
    asset = one(e, "flow_files", body["id"])
    blob = asset.pop("content")
    require(isinstance(blob, bytes) and blob == content and len(blob) == asset["size"] and sha(blob) == asset["sha256"]
        and asset["case_id"] == key and asset["created_by"] == actor["id"] and asset["category"] == "receipt"
        and not asset["generated"] and body["security"]["can_use"], "原件内容/类别/来源错配")
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (asset["id"],))
    security = one(e, "file_security", asset["id"])
    require(len(scans) == 1 and scans[0]["state"] == security["state"] == "structure_only"
        and scans[0]["sha256"] == asset["sha256"] and scans[0]["size"] == asset["size"], "原结构扫描事实不完整")
    await expect(e.page.locator("#main .filerecord").filter(has_text=file.name)).to_have_count(1)
    return {"file": asset, "stored_blob": {"length": len(blob), "sha256": sha(blob)}, "native": native,
        "guard": guard.finish(), "event": MF.event(e, guard, key, "upload"), "declaration": declaration,
        "clamav_acceptance": False}


async def money(e, context, credentials, fixture, key, account, token, *, amount, refund=None, declaration=None):
    action = "refund" if refund else "receive"
    handoff = await BT.responsible(e, context, credentials, fixture, key, "retail_" + action, "finance")
    actor, view = await retail_read(e, context, credentials, fixture, "finance", key)
    cap = view["totals"]["refund_due_cents" if refund else "receivable_cents"]
    require(cap == amount, "本次必须按当前实际原应收/应退余额")
    if declaration:
        require(not refund and declaration["case_id"] == key and declaration["amount_cents"] == amount
            and declaration["account_id"] == account["id"] and declaration["business_date"] == business_day().isoformat()
            and declaration["correct_reference"] != declaration["entered_reference"]
            and not subset(e, "flow_payment_links", "case_id", key), "误录样例声明必须先于实际原款")
        proof = await bank_receipt(e, actor, key, token, declaration)
        reference = declaration["entered_reference"]
    else:
        proof = await MF.upload(e, actor, key, None, RETAIL + f"/orders/{key}", "receipt", "retail-" + action + "-" + str(key), token)
        reference = "RT-" + action.upper() + "-" + str(key) + "-" + token
    await original_form(e, "retail-action", action, "登记原款实际退款" if refund else "登记实际收款")
    await e.fill('#modal [name="amount"]', fen_text(amount), "只登记这次实际原款金额")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    await e.fill('#modal [name="reference"]', reference, "填事前声明误录ENTRY编号" if declaration else "填本次实际独立流水编号")
    await MF.choose_file(e, proof, "receipt")
    values = {"amount_cents": amount, "account_id": account["id"], "reference": reference, "evidence_id": proof["file"]["id"]}
    if refund:
        await select_value(e, '#modal [name="original"]', str(refund["payment"]["id"]) + " · 收款 " + fen_text(refund["payment"]["amount_cents"]) + " 元", "选择本单本店唯一原实收款")
        values["original_payment_id"] = refund["payment"]["id"]
    case = one(e, "flow_cases", key)
    guard = Guard(e, "retail_money_" + action + "_" + str(key), actor,
        append={"flow_events": 1, "audit_logs": 2, "flow_request_receipts": 1,
            "cash_entries": 1, "flow_payment_links": 1, "retail_payments": 1},
        update=BT.updates(e, key, account=account["id"]), cases={key})
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/{action}", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "实际原收退款封包不符")
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_" + action]), proof=proof, handoff=handoff,
        receipt=MF.flow_receipt(e, request, actor, key, "retail_" + action, {"case_id": key, "version": case["version"], "values": values}))
    cash, payment, binding = guard.added["cash_entries"][0], guard.added["flow_payment_links"][0], guard.added["retail_payments"][0]
    direction = "out" if refund else "in"
    require(cash["direction"] == payment["direction"] == direction and cash["amount_cents"] == payment["amount_cents"] == amount
        and cash["account"] == account["name"] and cash["category"] == ("workflow_refund" if refund else "workflow_retail")
        and cash["created_by"] == actor["id"] and cash["voucher_no"] == payment["reference"] == reference
        and cash["approval_state"] == "approved" and cash["payment_method"] == ("cash" if account["account_type"] == "cash" else "bank")
        and cash["business_date"] == payment["business_date"] == business_day().isoformat()
        and payment["account_id"] == account["id"] and payment["cash_id"] == cash["id"]
        and payment["original_id"] == (refund["payment"]["id"] if refund else None)
        and binding["payment_link_id"] == payment["id"] and binding["evidence_id"] == proof["file"]["id"], "真实现金/原款/证据链接不唯一")
    require(shown["state"] == "completed" and shown["totals"]["receivable_cents"] == shown["totals"]["refund_due_cents"] == 0,
        "本单实际安装/接收/款没有闭合")
    return {"native": native, "cash": cash, "payment": payment, "retail_payment": binding, "final_api": shown}


async def return_goods(e, context, credentials, fixture, key, item, location, token):
    actor, _ = await retail_read(e, context, credentials, fixture, "service", key)
    proof = await MF.upload(e, actor, key, None, RETAIL + f"/orders/{key}", "evidence", "retail-partial-return-request", token)
    dispatches = subset(e, "retail_dispatches", "case_id", key)
    require(len(dispatches) == 1 and dispatches[0]["quantity_milli"] == 1000, "只能原A实际出库一件来源")
    dispatch = dispatches[0]
    await original_form(e, "retail-action", "return_request", "申请原单部分退货")
    await select_value(e, '#modal [name="source"]', str(dispatch["id"]) + " · " + item["name"] + " · 尚未退 1", "明确原出库商品")
    await e.fill('#modal [name="quantity"]', "0.500", "明确半件原商品退回")
    reason = "原已安装精品退回半件，安装完成费用按原约定保留"
    await e.fill('#modal [name="reason"]', reason, "原申请依据")
    await MF.choose_file(e, proof)
    values = {"evidence_id": proof["file"]["id"], "reason": reason, "lines": [{"dispatch_id": dispatch["id"], "quantity_milli": 500}]}
    case = one(e, "flow_cases", key)
    guard = Guard(e, "retail_partial_return_request", actor,
        append={**FLOW, "flow_tasks": 1, "retail_returns": 1, "retail_return_lines": 1}, update=BT.updates(e, key), cases={key}, items={item["id"]})
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/return_request", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "原部分退货来源/数量不符")
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_return_request"]), proof=proof,
        receipt=MF.flow_receipt(e, request, actor, key, "retail_return_request", {"case_id": key, "version": case["version"], "values": values}))
    returned = guard.added["retail_returns"][0]
    line = guard.added["retail_return_lines"][0]
    require(returned["status"] == "requested" and line["return_id"] == returned["id"] and line["dispatch_id"] == dispatch["id"]
        and line["quantity_milli"] == 500 and shown["totals"]["refund_due_cents"] == 0, "申请不能当退货入库或退款")
    request_result = {"native": native, "return": returned, "line": line}
    owner = await BT.responsible(e, context, credentials, fixture, key, "retail_return_review_" + str(returned["id"]), "manager")
    actor, _ = await retail_read(e, context, credentials, fixture, "manager", key)
    before_return, case = one(e, "retail_returns", returned["id"]), one(e, "flow_cases", key)
    await original_form(e, "retail-action", "return_approve", "批准退货", identifier=returned["id"])
    reason = "另一员工核准原半件退货及已履约安装费用保留"
    await e.fill('#modal [name="reason"]', reason, "独立原退货复核")
    values = {"return_id": returned["id"], "return_version": before_return["version"], "reason": reason}
    permitted = BT.updates(e, key)
    permitted["retail_returns"] = {returned["id"]: VERSION | {"status", "approved_by", "retain_installation"}}
    guard = Guard(e, "retail_partial_return_approve", actor, append={**FLOW, "flow_tasks": 1}, update=permitted, cases={key})
    require(actor["id"] != returned["requested_by"], "退货申请人与批准必须独立")
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/return_approve", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "原退货双CAS/独立批准封包不符")
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_return_approve"]), handoff=owner,
        receipt=MF.flow_receipt(e, request, actor, key, "retail_return_approve", {"case_id": key, "version": case["version"], "values": values}))
    approved = one(e, "retail_returns", returned["id"])
    require(approved["status"] == "approved" and approved["retain_installation"] == 1
        and approved["approved_by"] == actor["id"] and shown["totals"]["refund_due_cents"] == 0, "批准未冻结保留费或误作实际退货")
    approval_result = {"native": native, "return": approved}
    prepared = await BT.prepare(e, context, credentials, fixture, key, [item], location, "retail_return", [500])
    owner = await BT.responsible(e, context, credentials, fixture, key, "retail_return_receive_" + str(returned["id"]), "inventory")
    actor, _ = await retail_read(e, context, credentials, fixture, "inventory", key)
    proof = await MF.upload(e, actor, key, None, RETAIL + f"/orders/{key}", "evidence", "retail-partial-return-resalable", token)
    before_return, case, before_item = one(e, "retail_returns", returned["id"]), one(e, "flow_cases", key), one(e, "flow_items", item["id"])
    await original_form(e, "retail-action", "return_receive", "检查退货可售性", identifier=returned["id"])
    result = "本人实际收到原半件商品，独立检查完整可售并放回指定原库位"
    await e.fill('#modal [name="result"]', result, "库存本人实际可售检查")
    await select_value(e, '#modal [name="outcome"]', "合格", "实际检查合格才回可售库存")
    await MF.choose_file(e, proof)
    values = {"return_id": returned["id"], "return_version": before_return["version"], "evidence_id": proof["file"]["id"], "result": result, "passed": True}
    permitted = BT.updates(e, key, items={item["id"]}, balances=True)
    permitted["retail_returns"] = {returned["id"]: VERSION | {"status"}}
    allocation = prepared[0]["allocation"]
    permitted["warehouse_allocations"] = {allocation["id"]: VERSION | {"status", "stock_move_id"}}
    guard = Guard(e, "retail_partial_return_actual", actor,
        append={**FLOW, "flow_tasks": 1, "flow_stock_moves": 1, "warehouse_entries": 1, "retail_return_postings": 1},
        update=permitted, cases={key}, items={item["id"]})
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/return_receive", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "真实可售验收双CAS不符")
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_return_receive"]), proof=proof, handoff=owner,
        receipt=MF.flow_receipt(e, request, actor, key, "retail_return_receive", {"case_id": key, "version": case["version"], "values": values}))
    posting, move, entry = guard.added["retail_return_postings"][0], guard.added["flow_stock_moves"][0], guard.added["warehouse_entries"][0]
    cost = portion(dispatch["value_cents"], 500, dispatch["quantity_milli"])
    require(posting["return_line_id"] == line["id"] and posting["dispatch_id"] == dispatch["id"]
        and posting["stock_move_id"] == move["id"] and posting["quantity_milli"] == move["quantity_milli"] == entry["quantity_milli"] == 500
        and posting["value_cents"] == move["value_cents"] == entry["value_cents"] == cost
        and move["original_id"] == dispatch["stock_move_id"] and move["purpose"] == "retail_return"
        and posting["goods_cents"] == 1000 and posting["installation_cents"] == posting["retained_cents"] == 250
        and posting["evidence_id"] == proof["file"]["id"] and one(e, "retail_returns", returned["id"])["status"] == "accepted"
        and one(e, "warehouse_allocations", allocation["id"])["status"] == "consumed"
        and one(e, "warehouse_allocations", allocation["id"])["stock_move_id"] == move["id"]
        and one(e, "flow_items", item["id"])["quantity_milli"] == before_item["quantity_milli"] + 500
        and one(e, "flow_items", item["id"])["inventory_value_cents"] == before_item["inventory_value_cents"] + cost,
        "原半件/成本/商品减免/已安装保留费/可售入库未守恒")
    return {"request": request_result, "approval": approval_result, "prepare": prepared, "actual_receive": native,
        "return": one(e, "retail_returns", returned["id"]), "posting": posting, "stock_move": move, "warehouse_entry": entry}


async def refund_limit(e, context, credentials, fixture, key, original, account, token):
    await BT.responsible(e, context, credentials, fixture, key, "retail_refund", "finance")
    actor, view = await retail_read(e, context, credentials, fixture, "finance", key)
    require(view["totals"]["refund_due_cents"] == 1000 and view["totals"]["return_reduction_cents"] == 1000
        and view["totals"]["retained_installation_cents"] == 250, "实际半件可售/保留费没有产生唯一10元应退")
    proof = await MF.upload(e, actor, key, None, RETAIL + f"/orders/{key}", "receipt", "retail-refund-limit-check", token)
    await original_form(e, "retail-action", "refund", "登记原款实际退款")
    await e.fill('#modal [name="amount"]', "11.00", "明确超过实际原应退的11元阴性")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    await e.fill('#modal [name="reference"]', "RT-REFUND-LIMIT-" + token, "阴性原提交流水，不重放")
    await select_value(e, '#modal [name="original"]', str(original["payment"]["id"]) + " · 收款 25.00 元", "仅选择本单原实收25元")
    await MF.choose_file(e, proof, "receipt")
    case = one(e, "flow_cases", key)
    refusal = await rejected_submit(e, RETAIL + f"/orders/{key}/actions/refund", 409, "超过验收退货或取消后的实际应退余额")
    require(one(e, "flow_cases", key) == case, "拒绝超过原限额不能改原单")
    return {"amount_cents": 1100, "actual_refund_due_cents": 1000, "status": 409,
        "native": refusal, "proof": proof, "full_business_hash_unchanged": True, "explicit_discard": True}


async def repair_drill(e, key, repair):
    before = e.business_snapshot("before_actual_related_repair_drill")
    selector = f'#main [data-act="open"][data-route="case/{repair["id"]}"]'
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        parent = button.locator("xpath=ancestor::details[1]")
        require(await parent.count() == 1, "关联原维修入口不可见且无原展开栏目")
        e.action("click", "展开原维修关联栏目")
        await parent.locator(":scope > summary").click()
    async with e.page.expect_response(lambda r: get_match(r, f'/api/flow/cases/{repair["id"]}')) as pending:
        await e.click(selector, "从本精品单查看同客户原维修，不改其库存和款")
    response = await pending.value
    view = await response.json()
    current = one(e, "flow_cases", repair["id"])
    require(response.status == 200 and view["id"] == current["id"] and view["version"] == current["version"]
        and current == repair and view["customer_id"] == one(e, "flow_cases", key)["customer_id"], "关联钻取串客户/改原维修")
    await expect(e.page.locator("#main h1")).to_have_text(repair["title"])
    e.business_unchanged(before, "after_actual_related_repair_drill")
    return {"retail_case_id": key, "repair_case_id": repair["id"], "repair_version": repair["version"], "original_repair_unchanged": True,
        "native_click": True, "business_unchanged": True}


async def publish_bundle(e, context, credentials, fixture, items, work, token):
    actor, _ = await BT.read_as(e, context, credentials, fixture, "manager", "retail-bundle-rules", BUNDLE + "/rules", "精品套餐配置")
    await e.click('#main [data-act="retail-bundle-rule"]:not([data-id])', "主管发布本次新店内精品套餐版本")
    await expect(e.page.locator("#modal-title")).to_have_text("发布精品套餐")
    day = business_day()
    values = {"code": "RT-BUNDLE-" + token, "name": "本轮双商品安装套餐" + token, "enabled": True,
        "sale_starts_on": day.isoformat(), "sale_ends_on": (day + timedelta(days=30)).isoformat(),
        "price_cents_per_set": 3000, "refund_terms": "按原每套商品及安装分摊退货，已完成安装费保留，未施工的对应安装费随验收退货減免。",
        "components": [{"item_id": items[0]["id"], "quantity_milli_per_set": 500, "goods_reference_cents": 1000,
                "work_item_id": work["id"], "installation_reference_cents": 300},
            {"item_id": items[1]["id"], "quantity_milli_per_set": 500, "goods_reference_cents": 2000,
                "work_item_id": None, "installation_reference_cents": 0}]}
    for field, value in (("code", values["code"]), ("name", values["name"]), ("price", "30.00"),
        ("starts", values["sale_starts_on"]), ("ends", values["sale_ends_on"]), ("terms", values["refund_terms"])):
        await e.fill(f'#modal [name="{field}"]', value, "发布前明确冻结套餐字段：" + field)
    await e.click('#modal [data-act="retail-bundle-add"]', "套餐增加第二件明确商品")
    lines = e.page.locator('#modal [data-retail-bundle-line]')
    await expect(lines).to_have_count(2)
    for index, component in enumerate(values["components"]):
        root = lines.nth(index)
        e.action("select", "明确本店套餐原商品及安装项目", item_id=component["item_id"], work_item_id=component["work_item_id"])
        await root.locator('[name="item"]').select_option(str(component["item_id"]))
        await root.locator('[name="work"]').select_option(str(component["work_item_id"]) if component["work_item_id"] else "")
        for field, text in (("quantity", "0.500"), ("goods", fen_text(component["goods_reference_cents"])),
            ("installation", fen_text(component["installation_reference_cents"]))):
            e.action("fill", "每整套组件原参考金额和精确数量：" + field, sequence=index + 1)
            await root.locator(f'[name="{field}"]').fill(text)
    await checkbox(e, '#modal [name="enabled"]', True, "明确启用此新冻结版本")
    guard = Guard(e, "retail_bundle_rule_publish", actor,
        append={"retail_bundle_rules": 1, "retail_bundle_components": 2, "retail_bundle_receipts": 1, "audit_logs": 1}, items={i["id"] for i in items})
    body, request, shown, native = await submit(e, BUNDLE + "/rules", BUNDLE + "/rules", status=201)
    require(request == {"request_id": request["request_id"], "base_version": 0, "values": values}, "原店内套餐发布内容/基版不符")
    native["guard"] = guard.finish()
    rule, components, receipt = guard.added["retail_bundle_rules"][0], guard.added["retail_bundle_components"], guard.added["retail_bundle_receipts"][0]
    require(body["id"] == rule["id"] and rule["created_by"] == actor["id"] and rule["rule_version"] == 1
        and all(rule[k] == v for k, v in values.items() if k != "components")
        and [(r["sequence"], r["item_id"], r["goods_cents_per_set"], r["installation_cents_per_set"]) for r in components]
            == [(1, items[0]["id"], 909, 273), (2, items[1]["id"], 1818, 0)]
        and all(r["rule_id"] == rule["id"] for r in components), "真实最大余分每套分摊/冻结原组件不符")
    payload = {"base_version": 0, "values": values}
    digest = sha(json.dumps({"operation": "retail_bundle_rule", "payload": payload}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    require(receipt["request_id"] == request["request_id"] and receipt["digest"] == digest and receipt["rule_id"] == rule["id"]
        and receipt["actor_id"] == actor["id"] and receipt["store_id"] == 1, "原RuleReceipt不得替换为FlowReceipt")
    displayed = [r for r in shown["items"] if r["id"] == rule["id"]]
    require(len(displayed) == 1 and displayed[0]["is_latest"] and displayed[0]["enabled"]
        and [(r["goods_cents_per_set"], r["installation_cents_per_set"]) for r in displayed[0]["components"]] == [(909, 273), (1818, 0)], "原配置UI读取没有对应冻结分摊")
    await expect(e.page.locator("#main")).to_contain_text(values["name"])
    await expect(e.page.locator("#main")).to_contain_text("本版本已启用")
    native.update(rule_receipt={"id": receipt["id"], "digest": digest, "rule_id": rule["id"], "actor_id": actor["id"]})
    return rule, {"native": native, "rule": rule, "components": components}


async def bundle_create(e, context, credentials, fixture, customer, rule, items):
    actor, _ = await BT.read_as(e, context, credentials, fixture, "service", "retail-bundles", BUNDLE + "/rules", "精品销售套餐")
    await e.click(f'#main [data-act="retail-bundle-sale"][data-id="{rule["id"]}"]', "核对这次新套餐客户与两套数量")
    await expect(e.page.locator("#modal-title")).to_have_text("选择客户和套餐套数")
    await select_value(e, '#modal [name="customer"]', customer["id"], "明确本次同客户独立套餐单")
    await e.fill('#modal [name="sets"]', "2", "明确购买完整两套")
    before = e.business_snapshot("before_original_bundle_preview")
    async with e.page.expect_response(lambda r: get_match(r, BUNDLE + f'/rules/{rule["id"]}/preview')
        and parse_qs(urlsplit(r.url).query).get("sets") == ["2"]) as pending:
        await e.click('#modal button[type="submit"]', "只读取本次完整两套冻结清单")
    response = await pending.value
    preview = await response.json()
    require(response.status == 200 and preview["id"] == rule["id"] and preview["rule_version"] == 1 and preview["sets"] == 2
        and preview["amount_cents"] == 6000 and preview["available_sets"] >= 2
        and [(r["quantity_milli"], r["goods_cents"], r["installation_cents"]) for r in preview["components"]] == [(1000, 1818, 546), (1000, 3636, 0)], "原预览不符两套冻结分摊或当前可用量不足")
    await expect(e.page.locator("#modal-title")).to_have_text("确认套餐分摊与退货规则")
    for text in (rule["name"], "两套", "18.18", "5.46", "36.36", "60.00"):
        # UI formats the count as “2 套”; amounts remain the per-sale components.
        await expect(e.page.locator("#modal")).to_contain_text("2 套" if text == "两套" else text)
    e.business_unchanged(before, "after_original_bundle_preview")
    await select_value(e, '#modal [name="member_pricing_rule"]', "", "本独立纯Cash套餐不选会员优惠")
    await checkbox(e, '#modal [name="accepted"]', True, "客户明确组成分摊及原安装退费规则")
    old_items = {i["id"]: one(e, "flow_items", i["id"]) for i in items}
    guard = Guard(e, "retail_bundle_create", actor,
        append={"flow_events": 2, "audit_logs": 2, "flow_request_receipts": 1,
            "flow_cases": 1, "flow_tasks": 1, "retail_orders": 1, "retail_lines": 2, "retail_reservations": 2,
            "retail_bundle_sales": 1, "retail_bundle_allocations": 2},
        update={"flow_items": {i: VERSION for i in old_items}}, items=set(old_items), new_customer=customer["id"])
    body, request, shown, native = await MF.submit_created(e, BUNDLE + "/sales", RETAIL + "/orders/", status=201, body_key=("id",))
    key = body["id"]
    expected = {"rule_id": rule["id"], "rule_version": 1, "sets": 2, "customer_id": customer["id"], "terms_accepted": True}
    require(request == {"request_id": request["request_id"], **expected} and shown["state"] == "approval"
        and shown["amount_cents"] == 6000 and shown["related_repair_id"] is None, "Bundle原UI不能猜注入维修关联或改分摊")
    # Sale schema supplies related_repair_id=None; the original service removes
    # member_pricing=None only. The receipt therefore includes that exact default.
    native.update(guard=guard.finish(), events=events(e, guard, key, ["retail_create", "retail_bundle_create"]),
        receipt=MF.flow_receipt(e, request, actor, key, "retail_bundle_create", {**expected, "related_repair_id": None}),
        preview=preview, preview_business_unchanged=True)
    sale, allocations, lines = guard.added["retail_bundle_sales"][0], guard.added["retail_bundle_allocations"], guard.added["retail_lines"]
    require(sale["case_id"] == key and sale["rule_id"] == rule["id"] and sale["sets"] == 2 and sale["terms_accepted"] == 1
        and [(r["quantity_milli"], r["goods_cents"], r["installation_cents"]) for r in allocations] == [(1000, 1818, 546), (1000, 3636, 0)]
        and all(r["sale_id"] == sale["id"] and r["line_id"] == lines[n]["id"] for n, r in enumerate(allocations))
        and [(r["item_id"], r["quantity_milli"], r["goods_cents"], r["installation_cents"], r["work_item_id"]) for r in lines]
            == [(items[0]["id"], 1000, 1818, 546, one(e, "retail_bundle_components", allocations[0]["component_id"])["work_item_id"]),
                (items[1]["id"], 1000, 3636, 0, None)]
        and all(r["unit_price_cents"] == r["installation_unit_price_cents"] == 0 for r in lines)
        and one(e, "retail_orders", key)["discount_cents"] == 600
        and all(r["pricing_mode"] == "frozen_bundle" and "unit_price_cents" not in r for r in shown["lines"]), "原套餐每套乘套数/安装项目/显示定价模式不符")
    require(all(one(e, "flow_items", i)["quantity_milli"] == r["quantity_milli"]
        and one(e, "flow_items", i)["inventory_value_cents"] == r["inventory_value_cents"] for i, r in old_items.items()), "Bundle开单不能当实际出库")
    await expect(e.page.locator("#main h1")).to_have_text("精品销售 · " + body["number"])
    return key, {"native": native, "sale": sale, "allocations": allocations, "lines": lines, "order": one(e, "retail_orders", key)}


async def final_read(e, context, credentials, fixture, key, *, charge, reduction, retained, cost):
    _, view = await retail_read(e, context, credentials, fixture, "finance", key)
    case = one(e, "flow_cases", key)
    totals = view["totals"]
    require(case["state"] == view["state"] == "completed" and json.loads(case["data"])["installed"] is True
        and json.loads(case["data"])["accepted_date"] and not [t for t in subset(e, "flow_tasks", "case_id", key) if t["status"] == "open"]
        and totals["charge_cents"] == totals["net_paid_cents"] == totals["cash_paid_cents"] == totals["revenue_cents"] == charge
        and totals["return_reduction_cents"] == reduction and totals["retained_installation_cents"] == retained
        and totals["receivable_cents"] == totals["refund_due_cents"] == totals["advance_credit_cents"] == 0
        and totals["cost_cents"] == case["cost_cents"] == cost and "group_paid_cents" not in totals
        and not subset(e, "membership_points_changes", "case_id", key), "原商品/实际安装/接收/纯现金/净成本未闭合")
    before = e.business_snapshot("before_retail_final_refresh_" + str(key))
    async with e.page.expect_response(lambda r: get_match(r, RETAIL + f"/orders/{key}")) as pending:
        e.action("navigate", "刷新核对原单没有重复出库收退款", case_id=key)
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    require(response.status == 200 and await response.json() == view, "刷新原单事实不一致")
    await expect(e.page.locator("#main h1")).to_have_text("精品销售 · " + case["number"])
    await expect(e.page.locator("#main")).to_contain_text("已实际安装")
    await expect(e.page.locator("#main")).to_contain_text("客户已接收")
    e.business_unchanged(before, "after_retail_final_refresh_" + str(key))
    return {"case": MF.json_row(case, "data"), "api": view, "tasks": subset(e, "flow_tasks", "case_id", key),
        "no_duplicate_on_refresh": True, "pure_cash_without_group_or_points": True}


async def retail_remaining_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, customer, repair, account, items, work, location = dependencies(e, cp)
        token = uuid.uuid4().hex[:10]
        initial = {i["id"]: one(e, "flow_items", i["id"]) for i in items}
        cp.start("HK-063")
        a, created = await ordinary_create(e, context, credentials, fixture, customer, repair, items[0], work)
        approved = await retail_action(e, context, credentials, fixture, a, "approve", [items[0]], 2500, token)
        authorized = await retail_action(e, context, credentials, fixture, a, "authorize", [items[0]], 2500, token)
        cp.note({"case_id": a, "create": created, "independent_approve": approved, "current_revision_authorize": authorized})
        cp.start("HK-066")
        prepared = await BT.prepare(e, context, credentials, fixture, a, [items[0]], location, "retail_dispatch", [-1000])
        dispatched = await retail_action(e, context, credentials, fixture, a, "dispatch", [items[0]], 2500, token)
        _, source_ui = await retail_read(e, context, credentials, fixture, "finance", a)
        require(source_ui["related_repair_id"] == repair["id"] and source_ui["state"] == "working"
            and source_ui["totals"]["cost_cents"] == dispatched["dispatches"][0]["value_cents"], "维修附带实际出库没有独立原成本")
        await cp.passed({"case_id": a, "repair_case_id": repair["id"], "prepare_not_physical": prepared,
            "actual_dispatch": dispatched, "dispatch_api": source_ui, "original_repair_unchanged": one(e, "flow_cases", repair["id"]) == repair})
        cp.start("HK-063")
        installed = await retail_action(e, context, credentials, fixture, a, "install", [items[0]], 2500, token)
        accepted = await retail_action(e, context, credentials, fixture, a, "accept", [items[0]], 2500, token)
        declaration = {"schema": 1, "sample": "synthetic_known_reference_misrecord_before_original_cash",
            "case_id": a, "customer_id": customer["id"], "account_id": account["id"], "business_date": business_day().isoformat(),
            "amount_cents": 2500, "correct_reference": "RT-IN-CORRECT-" + token,
            "entered_reference": "RT-IN-MISRECORDED-" + token, "actual_synthetic_receipt_confirmed": True,
            "intentional_reference_error": True, "correction_executed": False, "real_bank_payment": False}
        directory = e.directory / "synthetic-inputs"
        directory.mkdir(exist_ok=True)
        declaration_path = directory / ("retail-A-before-cash-declaration-" + token + ".json")
        declaration_bytes = (json.dumps(declaration, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
        declaration_path.write_bytes(declaration_bytes)
        e.observe("before_original_cash_synthetic_misrecord_declaration", {"path": str(declaration_path),
            "sha256": sha(declaration_bytes), "declaration": declaration, "business_payment_rows_before": 0})
        cp.note({"before_original_cash_declaration": declaration, "declaration_path": str(declaration_path), "sha256": sha(declaration_bytes)})
        paid = await money(e, context, credentials, fixture, a, account, token, amount=2500, declaration=declaration)
        a_original_final = await final_read(e, context, credentials, fixture, a, charge=2500, reduction=0, retained=0,
            cost=dispatched["dispatches"][0]["value_cents"])
        drill = await repair_drill(e, a, repair)
        await cp.passed({"case_id": a, "original_order": created, "independent_approve": approved,
            "authorize_current_revision": authorized, "actual_dispatch": dispatched, "technician_install": installed,
            "customer_accept": accepted, "actual_cash": paid, "known_uncorrected_reference": declaration,
            "native_related_repair_drill": drill, "original_complete_result": a_original_final})
        cp.start("HK-067")
        returned = await return_goods(e, context, credentials, fixture, a, items[0], location, token)
        limit = await refund_limit(e, context, credentials, fixture, a, paid, account, token)
        refunded = await money(e, context, credentials, fixture, a, account, token, amount=1000, refund=paid)
        a_final = await final_read(e, context, credentials, fixture, a, charge=1500, reduction=1000, retained=250,
            cost=dispatched["dispatches"][0]["value_cents"] - returned["posting"]["value_cents"])
        require(len(subset(e, "flow_payment_links", "case_id", a)) == len(subset(e, "retail_payments", "case_id", a)) == 2
            and refunded["payment"]["original_id"] == paid["payment"]["id"], "退款不能新造实收或丢失原款关联")
        await cp.passed({"case_id": a, "actual_original_partial_return": returned, "refund_limit_negative": limit,
            "original_actual_refund": refunded, "final": a_final, "retained_installation_cents": 250,
            "refund_cash_cents": 1000, "no_new_income_for_return": True})
        cp.start("HK-068")
        rule, publication = await publish_bundle(e, context, credentials, fixture, items, work, token)
        b, bundle = await bundle_create(e, context, credentials, fixture, customer, rule, items)
        b_approved = await retail_action(e, context, credentials, fixture, b, "approve", items, 6000, token)
        b_authorized = await retail_action(e, context, credentials, fixture, b, "authorize", items, 6000, token)
        b_prepared = await BT.prepare(e, context, credentials, fixture, b, items, location, "retail_dispatch", [-1000, -1000])
        b_dispatched = await retail_action(e, context, credentials, fixture, b, "dispatch", items, 6000, token)
        b_installed = await retail_action(e, context, credentials, fixture, b, "install", items, 6000, token)
        b_accepted = await retail_action(e, context, credentials, fixture, b, "accept", items, 6000, token)
        b_paid = await money(e, context, credentials, fixture, b, account, token, amount=6000)
        b_final = await final_read(e, context, credentials, fixture, b, charge=6000, reduction=0, retained=0,
            cost=sum(r["value_cents"] for r in b_dispatched["dispatches"]))
        require(b_final["api"]["bundle"]["rule_id"] == rule["id"] and b_final["api"]["bundle"]["rule_version"] == 1
            and b_final["api"]["bundle"]["sets"] == 2 and b_final["api"]["bundle"]["terms_accepted"] is True
            and len(subset(e, "flow_payment_links", "case_id", b)) == 1 and not subset(e, "retail_returns", "case_id", b), "独立套餐不能借普通A原退或再次计现金")
        await cp.passed({"rule_publication": publication, "case_id": b, "two_set_create_and_preview": bundle,
            "independent_approval": b_approved, "revision_authorization": b_authorized, "actual_positions": b_prepared,
            "actual_dispatch": b_dispatched, "technician_install": b_installed, "customer_accept": b_accepted,
            "actual_cash_6000": b_paid, "final": b_final, "bundle_has_no_ui_repair_selection": True})
        final_stocks = [MAT.item_stock(e, i["id"]) for i in items]
        for index, item in enumerate(items):
            costs = sum(r["value_cents"] for r in b_dispatched["dispatches"] if one(e, "retail_lines", r["line_id"])["item_id"] == item["id"])
            if index == 0:
                costs += dispatched["dispatches"][0]["value_cents"] - returned["posting"]["value_cents"]
            quantity = initial[item["id"]]["quantity_milli"] - (1500 if index == 0 else 1000)
            value = initial[item["id"]]["inventory_value_cents"] - costs
            require(final_stocks[index]["item"]["quantity_milli"] == quantity
                and final_stocks[index]["item"]["inventory_value_cents"] == value, "本批所有实物出退量/原成本整体不守恒")
            await MAT.stock_page(e, context, credentials, fixture, "finance", item["id"], quantity=quantity, value=value)
        require(one(e, "flow_cases", repair["id"]) == repair, "原维修不能被附带销售改写")
        correction_source = {"customer_id": customer["id"], "case_id": a, "original_cash_id": paid["cash"]["id"],
            "original_payment_id": paid["payment"]["id"], "refund_cash_id": refunded["cash"]["id"], "refund_payment_id": refunded["payment"]["id"],
            "original_account_id": account["id"], "business_date": paid["cash"]["business_date"],
            "entered_reference": declaration["entered_reference"], "correct_reference": declaration["correct_reference"],
            "gross_cents": 2500, "refunded_cents": 1000, "remaining_cents": 1500, "allocation_basis": "remaining_after_refunds",
            "before_cash_declaration_path": str(declaration_path), "before_cash_declaration_sha256": sha(declaration_bytes),
            "original_receipt_file": paid["native"]["proof"]["file"], "original_receipt_blob": paid["native"]["proof"]["stored_blob"],
            "intentional_reference_error": True, "correction_executed": False, "HK086_status": "not_tested"}
        sources = {"store_id": 1, "customer_id": customer["id"], "customer_vehicle_id": cp.report["source_preconditions"]["repair"]["customer_vehicle_id"],
            "original_repair_case_id": repair["id"], "account_id": account["id"], "item_ids": [i["id"] for i in items],
            "work_item_id": work["id"], "warehouse_id": location["warehouse_id"], "location_id": location["id"],
            "related_retail_case_id": a, "related_retail_dispatch_id": dispatched["dispatches"][0]["id"],
            "related_retail_line_id": created["line"]["id"], "return_id": returned["return"]["id"], "return_posting_id": returned["posting"]["id"],
            "original_cash_id": paid["cash"]["id"], "original_payment_link_id": paid["payment"]["id"],
            "refund_cash_id": refunded["cash"]["id"], "refund_payment_link_id": refunded["payment"]["id"],
            "bundle_rule_id": rule["id"], "bundle_rule_version": 1, "bundle_case_id": b, "bundle_sale_id": bundle["sale"]["id"],
            "bundle_allocation_ids": [r["id"] for r in bundle["allocations"]], "bundle_line_ids": [r["id"] for r in bundle["lines"]],
            "bundle_dispatch_ids": [r["id"] for r in b_dispatched["dispatches"]], "bundle_cash_id": b_paid["cash"]["id"],
            "bundle_payment_link_id": b_paid["payment"]["id"], "warehouse_allocation_ids": [r["id"] for key in (a, b) for r in subset(e, "warehouse_allocations", "case_id", key)],
            "stock_move_ids": [r["id"] for key in (a, b) for r in subset(e, "flow_stock_moves", "case_id", key)],
            "final_item_stocks": [{"item_id": s["item"]["id"], "quantity_milli": s["item"]["quantity_milli"],
                "inventory_value_cents": s["item"]["inventory_value_cents"]} for s in final_stocks],
            "cash_correction_source": correction_source, "ordinary_totals": a_final["api"]["totals"], "bundle_totals": b_final["api"]["totals"]}
        cp.finish(sources)
    except Exception as error:
        cp.failed(error)
        raise


RETAIL_REMAINING_SCENARIOS = ((SCENARIO, retail_remaining_business, 1200),)
