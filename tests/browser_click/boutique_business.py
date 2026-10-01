"""Six native boutique workflows; no prebuilt stock, funding or fulfillment.

Only external Evidence and original visible employee forms operate. SQL is read
only; existing helpers and production are unchanged. Human acceptance is pending.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency, fen_text
from vehicle_purchase_business import checkbox, live_choice, master_form, master_page, select_value
from finance_business import get_match, original_form, submit
from membership_business import group_receipt
import master_data_business as MD
import material_business as MAT
import member_followon_business as MF

SCENARIO = "boutique-purchase-retail-hk074-052-058-062-064-082"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
MASTER = MD.SCENARIO
MATERIAL = MAT.SCENARIO
MEMBERSHIP = MF.MEMBERSHIP
MEMBER = MF.SCENARIO
RETAIL, RG = "/api/retail", "/api/retail-group"
REQUIREMENTS = (("HK-074", "精品采购订货"), ("HK-052", "精品采购入库"),
                ("HK-058", "精品采购入库退货"), ("HK-062", "精品销售单"),
                ("HK-064", "精品销售出库"), ("HK-082", "精品销售收款"))
VERSION = {"version", "updated_at"}
CASE = VERSION | {"state", "data", "cost_cents", "completed_date"}
TASK = VERSION | {"status", "done_by", "done_at"}
ITEM = VERSION | {"quantity_milli", "inventory_value_cents", "unit_cost_cents"}
BALANCE = VERSION | {"quantity_milli", "value_cents"}
FLOW = {"flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1}
# Identifiers are finite, source-declared; no SQL identifier is derived from UI.
TABLES = MF.READ_TABLES | MAT.TABLES | {
    "master_material_categories", "master_material_brands", "business_entity_policies",
    "retail_payments", "flow_payment_links", "retail_group_cash_allocations",
    "membership_points_changes",
}
FIELDS = {"case_id", "item_id", "member_id", "wallet_id", "receipt_id", "return_id",
          "stock_move_id", "allocation_id", "plan_id", "tender_id", "unit_id", "eligibility_id", "entry_id"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pk(table):
    return "file_id" if table == "file_security" else "id"


def rows(e, table):
    require(table in TABLES, "未审阅原表")
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {pk(table)}")


def one(e, table, key):
    require(table in TABLES and type(key) is int and key > 0, "必须明确原ID")
    value = e.db.rows(f"SELECT * FROM {table} WHERE {pk(table)}=?", (key,))
    require(len(value) == 1, "原来源缺失或重复：" + table + "/" + str(key))
    return value[0]


def subset(e, table, field, value):
    require(table in TABLES and field in FIELDS, "未审阅原关联")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {pk(table)}", (value,))


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]), "精品原合同不符：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__).read_bytes()),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "business_accepted": False, "human_acceptance": "pending",
            "contract_rules": {"automatic_pass_is_not_business_acceptance": True, "human_six_criteria_review": "pending",
                               "untested_conditions_are_not_passed": True, "unknown_result_replay": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": ["本人原UI输入和非空结果", "原API/DB/Task/CAS/回执一致", "原来源、现金与库存旧行保护"], "evidence": {}}]}
                for key, title in REQUIREMENTS],
            "conditional_checks": [{"status": "not_tested", "scope": s} for s in (
                "采购预付款、终止余量和未发出退货撤销", "混合成本非零差额、缺货、并发及重复提交",
                "精品维修附带、加装、客户退货及安装保留费、销售套餐", "券原退恢复、到期、跨店、积分兑换和消费积分",
                "人工体验、真实ClamAV、PostgreSQL、Linux、真实模型和生产门槛")],
            "conditions": {"synthetic_inputs_only": True, "prebuilt_business_results": False,
                           "actual_bank_or_company_handover": False, "file_scan": "structure_only_not_clamav"}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] in {"not_tested", "running"}, "不可重复领取已执行check")
        self.active.update(status="running", evidence_action_start=self.active.get("evidence_action_start", len(self.e.actions)))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def note(self, value):
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
                r["status"] = status
                r["acceptance_checks"][0].update(status=status, error=self.e.scrub(error))
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "sources_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "六项原链未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=6, passed_requirements=6,
                           boutique_sources=sources, report_sources=sources)
        self.save()
        self.e.observe("boutique_original_checkpoint", {"path": str(self.path), "passed_checks": 6,
                       "human_acceptance": "pending", "full_193_business_acceptance": False})


class Guard:
    """Whole business hashes plus exact old IDs/columns and bounded new facts."""
    def __init__(self, e, label, actor, *, append, update=None, cases=(), items=(), member=None,
                 wallets=(), new_kind=None, customer=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = dict(append), update or {}
        self.cases, self.items, self.wallets = set(cases), set(items), set(wallets)
        self.member, self.new_kind, self.customer = member, new_kind, customer
        require(self.append.keys() | self.update.keys() <= TABLES, "精品守卫越过有限表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "本次影响无关原表：" + str(sorted(changed)))
        self.added = {t: [r for r in rows(self.e, t) if r[pk(t)] not in {o[pk(t)] for o in old}] for t, old in self.old.items()}
        for t, added in self.added.items():
            n = self.append.get(t, 0)
            low, high = n if isinstance(n, tuple) else (n, n)
            require(low <= len(added) <= high, "新增数不符：" + t + "/" + str(len(added)))
        created = self.added.get("flow_cases", [])
        require(not created or len(created) == 1 and created[0]["kind"] == self.new_kind
                and created[0]["customer_id"] == self.customer
                and created[0]["flow_version"] == (3 if self.new_kind == "procurement" else 2)
                and created[0]["created_by"] == created[0]["owner_id"] == self.actor["id"], "新增原单类型/身份/客户错配")
        cases = self.cases | {r["id"] for r in created}
        items = self.items | {r["id"] for r in self.added.get("flow_items", [])}
        wallets = self.wallets | {r["id"] for r in self.added.get("benefit_wallets", [])}
        audit_ids = {"flow": cases, "flow_master": items,
                     "cash": {r["id"] for r in self.added.get("cash_entries", [])},
                     "typed_master": {r["id"] for t, added in self.added.items() if t.startswith("master_") and t != "master_receipts" for r in added}}
        modified = {}
        for t, prior in self.old.items():
            current = {r[pk(t)]: r for r in rows(self.e, t)}
            modified[t] = []
            for old in prior:
                key = old[pk(t)]
                require(key in current, "不可删除旧事实：" + t)
                columns = {k for k in old if old[k] != current[key][k]}
                require(columns <= self.update.get(t, {}).get(key, set()), "覆盖未授权原列：" + t + "/" + str(key) + "/" + str(sorted(columns)))
                if t == "flow_cases" and "data" in columns:
                    a, b = json.loads(old["data"]), json.loads(current[key]["data"])
                    require(all(k in b and (b[k] == v or k == "receiving_closed" and v is False and b[k] is True
                            and self.label == "boutique_batch_receive") for k, v in a.items()), "正向步骤覆盖既有原单事实")
                if columns:
                    modified[t].append({"id": key, "columns": sorted(columns)})
            for r in self.added[t]:
                for field in ("store_id", "issuer_store_id"):
                    if field in r:
                        require(r[field] == 1, "新增事实串店：" + t)
                if "case_id" in r:
                    require(r["case_id"] in cases, "新增事实串原单：" + t)
                if "source_case_id" in r:
                    require(r["source_case_id"] in cases, "新增发行串宿主")
                if "item_id" in r:
                    require(r["item_id"] in items, "新增事实串商品：" + t)
                if "member_id" in r and r["member_id"] is not None:
                    require(r["member_id"] == self.member, "新增事实串会员：" + t)
                if "wallet_id" in r and r["wallet_id"] is not None:
                    require(r["wallet_id"] in wallets, "新增事实串原批次：" + t)
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in r and r[field] is not None:
                        require(r[field] == self.actor["id"], "新增事实借身份：" + t)
                if t == "audit_logs":
                    require(r["entity_id"] in audit_ids.get(r["entity_type"], set()), "审计串来源实体")
                if t == "warehouse_allocation_lines":
                    a = one(self.e, "warehouse_allocations", r["allocation_id"])
                    require(a["case_id"] in cases and a["item_id"] in items, "准备行串原单商品")
                if t == "membership_points_claims":
                    require(r["rule_id"] is None and r["member_id"] == self.member, "无会期不得编造奖分")
        result = {"label": self.label, "changed_tables": sorted(changed), "appended_ids": {t: [r[pk(t)] for r in a] for t, a in self.added.items()},
                  "updated_columns": modified, "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("boutique_original_row_guard", result)
        return result


def updates(e, key, *, items=(), balances=False, allocations=False, returned=None, member=None, wallet=None, account=None):
    value = {"flow_cases": {key: CASE}, "flow_tasks": {t["id"]: TASK for t in subset(e, "flow_tasks", "case_id", key)}}
    if items:
        value["flow_items"] = {i: ITEM for i in items}
    if balances:
        value["warehouse_balances"] = {b["id"]: BALANCE for i in items for b in subset(e, "warehouse_balances", "item_id", i)}
    if allocations:
        value["warehouse_allocations"] = {a["id"]: VERSION | {"status", "stock_move_id"}
            for a in subset(e, "warehouse_allocations", "case_id", key) if a["item_id"] in items}
    if returned:
        value["procurement_returns"] = {returned: VERSION | {"status", "approved_by"}}
    if member:
        value["group_members"] = {member: MF.MEMBER}
    if wallet:
        value["benefit_wallets"] = {wallet: MF.WALLET}
    if account:
        value["flow_accounts"] = {account: VERSION}
    return {t: v for t, v in value.items() if v}


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许合成外部实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(not root.is_relative_to(Path(e.manifest["source_root"]).resolve()), "证据不能在被测源码内")
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "DB不是同轮外部runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "镜像不是稳定快照")
    for name in ("boutique_business.py", "member_followon_business.py", "membership_business.py", "material_business.py",
                 "master_data_business.py", "vehicle_purchase_business.py", "finance_business.py", "sales_business.py",
                 "sales_order_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "同轮脚本指纹已变化：" + name)
    purchase, masters, materials, membership, followon = [fixed_dependency(e, cp, s) for s in (PURCHASE, MASTER, MATERIAL, MEMBERSHIP, MEMBER)]
    source = followon["member_followon_sources"]
    customer, member, account = one(e, "flow_customers", source["customer_id"]), one(e, "group_members", source["member_id"]), one(e, "flow_accounts", source["account_id"])
    supplier = one(e, "master_suppliers", checkpoint_evidence(purchase, "HK-171")["supplier"]["id"])
    warehouse = one(e, "master_warehouses", checkpoint_evidence(masters, "HK-184")["warehouse"]["row"]["id"])
    location = one(e, "master_locations", checkpoint_evidence(masters, "HK-184")["location"]["row"]["id"])
    brand = one(e, "master_material_brands", checkpoint_evidence(masters, "HK-181")["row"]["id"])
    parent = one(e, "master_material_categories", checkpoint_evidence(masters, "HK-182")["parent"]["row"]["id"])
    work = one(e, "master_work_items", checkpoint_evidence(masters, "HK-175")["row"]["id"])
    fixture = {**e.manifest["business_fixtures"]["sales_order"], **e.manifest["business_fixtures"]["repair"], "admin_key": "admin"}
    require(fixture["store_id"] == 1 and all(r["store_id"] == 1 for r in (customer, account, supplier, warehouse, location, brand, parent, work))
            and all(r["active"] == 1 for r in (account, supplier, warehouse, location, brand, parent, work))
            and member["active"] == 1, "有限前序串店/停用")
    require(customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"]
            and customer["phone"] and customer["contact_allowed"], "客户缺同轮原经办人或明确联系事实")
    linked = e.db.rows("SELECT id FROM group_identity_links WHERE store_id=? AND local_kind=? AND local_id=? AND identity_id=?",
                       (1, "customer", customer["id"], member["identity_id"]))
    require(len(linked) == 1, "集团会员必须由本店真实客户身份关联，不伪造门店归属")
    require(location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials", "材料真实库位前序不符")
    require(member["balance_cents"] == source["member_balance_cents"] == 9700 and member["reserved_cents"] == 0
            and not subset(e, "membership_periods", "member_id", member["id"]), "同轮本金或无期会前置不符")
    require(source["customer_id"] == membership["membership_sources"]["customer_id"]
            and source["member_id"] == membership["membership_sources"]["member_id"]
            and account["id"] == checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"], "会员/原账户不是同轮同源")
    for role in ("manager", "inventory", "finance", "service", "technician", "admin"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and actor["id"] > 0, "缺已存在本人岗位：" + role)
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=?", (1,)), "已有经营主体策略须另核，不默改既有前序")
    cp.report["source_preconditions"] = {"fixed_scenarios": [PURCHASE, MASTER, MATERIAL, MEMBERSHIP, MEMBER], "provenance_sha256": sha(raw),
        "customer_id": customer["id"], "member_id": member["id"], "member_balance_cents": member["balance_cents"], "account_id": account["id"],
        "supplier": supplier, "warehouse": warehouse, "location": location, "brand": brand, "parent_category": parent, "work_item": work,
        "old_wallet_ids_not_reused": source["wallet_ids"], "material_source_not_consumed": materials["material_sources"]["primary"]["item_id"]}
    cp.save()
    return fixture, customer, member["id"], account, supplier, warehouse, location, brand, parent, work


async def read_as(e, context, credentials, fixture, role, route, path, heading):
    actor = await login_as(e, context, credentials, fixture[role + "_key"], "work", 1)
    before = e.business_snapshot("before_boutique_original_read")
    async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
        e.action("navigate", "本人读取明确精品原单", route=route)
        if urlsplit(e.page.url).fragment == route:
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.page.goto(e.origin + "/#" + route)
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "本人原读取失败：" + path)
    await expect(e.page.locator("#main h1")).to_have_text(heading)
    e.business_unchanged(before, "after_boutique_original_read")
    return actor, body


async def responsible(e, context, credentials, fixture, key, task_key, role):
    current = MF.task(e, key, task_key)
    if role == "service" and task_key in {"retail_authorize", "retail_accept"}:
        actor = e.manifest["users"][fixture["service_key"]]
        require(current["role"] == "sales" and current["assignee_id"] == one(e, "flow_cases", key)["owner_id"] == actor["id"],
                "原精品客户待办须由建单服务顾问本人办理，不能越岗交接")
        return {"task_id": current["id"], "key": task_key, "target_id": actor["id"], "original_task_role": "sales", "handoff_needed": False}
    return await MF.responsible(e, context, credentials, fixture, key, task_key, role, None)


async def proof(e, actor, key, member, path, category, label, token):
    return await MF.upload(e, actor, key, member, path, category, "boutique-" + label, token)


async def make_items(e, context, credentials, fixture, brand, parent, location, supplier, token):
    actor = await login_as(e, context, credentials, fixture["inventory_key"], "masters/material_categories", 1)
    await master_page(e, "material_categories", "物资分类")
    await master_form(e, "material_categories", "物资分类")
    await live_choice(e, "parent_id", parent["name"], parent["code"] + " · " + parent["name"], expected_value=parent["id"])
    guard = Guard(e, "boutique_category_create", actor, append={"master_material_categories": 1, "master_receipts": 1, "audit_logs": 1})
    category, native = await MD.save_typed(e, actor, 1, "material_categories", {"code": "BT-C-" + token, "name": "本轮精品子类" + token, "active": True})
    category_meta = {"row": category, "native": native, "guard": guard.finish()}
    require(category["parent_id"] == parent["id"], "新精品子类缺真实父分类")
    items, metadata = [], []
    for suffix in ("A", "B"):
        await read_as(e, context, credentials, fixture, "inventory", "master/items", "/api/flow/master/items", "物资目录")
        guard = Guard(e, "boutique_item_" + suffix, actor, append={"flow_items": 1, "audit_logs": 1})
        item, created = await MD.save_item(e, actor, 1, {"sku": "BT-" + suffix + "-" + token, "name": "本轮精品" + suffix + token,
            "unit": "件", "reorder": "0", "active": True})
        protected = guard.finish()
        await master_page(e, "item_profiles", "物资归类与库位")
        await master_form(e, "item_profiles", "物资归类与库位")
        for field, row in (("item_id", item), ("category_id", category), ("brand_id", brand), ("location_id", location), ("supplier_id", supplier)):
            label = (row.get("code") or row.get("sku")) + " · " + row["name"]
            await live_choice(e, field, row["name"], label, expected_value=row["id"])
        guard = Guard(e, "boutique_profile_" + suffix, actor, append={"master_item_profiles": 1, "master_receipts": 1, "audit_logs": 1}, items={item["id"]})
        profile, profile_meta = await MD.save_typed(e, actor, 1, "item_profiles", {"active": True})
        require(profile["item_id"] == item["id"] and profile["category_id"] == category["id"] and profile["brand_id"] == brand["id"]
                and profile["location_id"] == location["id"] and profile["supplier_id"] == supplier["id"], "新精品原归类引用不符")
        item_meta = {"item": item, "create": created, "guard": protected, "profile": profile, "profile_native": profile_meta, "profile_guard": guard.finish()}
        activation, uploaded, create = await MAT.warehouse_create(e, context, credentials, fixture, item, "activate", 0, destination=location)
        _, approved = await MAT.warehouse_command(e, context, credentials, fixture, activation, item["id"], "approve", uploaded)
        uploaded = dict(uploaded)
        blob = uploaded.pop("content")
        require(isinstance(blob, bytes) and sha(blob) == uploaded["sha256"] and len(blob) == uploaded["size"], "启用原件字节不符")
        stock = MAT.item_stock(e, item["id"])
        require(stock["item"]["quantity_milli"] == stock["item"]["inventory_value_cents"] == 0 and not stock["stock_moves"]
                and len(stock["balances"]) == 1 and stock["balances"][0]["location_id"] == location["id"], "零库存启用假造实物")
        item_meta["activation"] = {"case_id": activation, "create": create, "approve": approved, "file": uploaded,
                                    "stored_blob": {"length": len(blob), "sha256": sha(blob)}, "stock": stock}
        items.append(one(e, "flow_items", item["id"]))
        metadata.append(item_meta)
    return items, {"category": category_meta, "items": metadata}


async def purchase_create(e, context, credentials, fixture, items, supplier):
    actor, _ = await read_as(e, context, credentials, fixture, "inventory", "procurement", "/api/procurement/orders", "采购与供应商结算")
    await e.click('#main [data-act="procurement-new"]', "申请本轮两新精品采购")
    await expect(e.page.locator("#modal-title")).to_have_text("申请多行采购")
    await live_choice(e, "supplier", supplier["name"], supplier["code"] + " · " + supplier["name"], expected_value=supplier["id"])
    reason = "本轮两件新精品实际采购，分两批到货并独立实付"
    await e.fill('#modal [name="reason"]', reason, "填写原精品采购依据")
    await e.click('#modal [data-act="procurement-add-line"]', "增加第二件精品采购行")
    lines = []
    for n, (item, quantity, cost) in enumerate(zip(items, (4000, 2000), (1000, 2000))):
        root = e.page.locator('#modal [data-purchase-line]').nth(n)
        label = item["sku"] + " · " + item["name"] + "（" + item["unit"] + "）"
        await MAT.choose(e, root, 'select[name="item"]', item["sku"], label, item["id"])
        e.action("fill", "明确本行原精品数量与单价", item_id=item["id"])
        await root.locator('[name="quantity"]').fill(MAT.qty(quantity))
        await root.locator('[name="cost"]').fill(fen_text(cost))
        lines.append({"item_id": item["id"], "quantity_milli": quantity, "unit_cost_cents": cost})
    guard = Guard(e, "boutique_purchase_create", actor, append={**FLOW, "flow_cases": 1, "flow_tasks": 1, "procurement_orders": 1, "procurement_lines": 2},
                  new_kind="procurement", items={i["id"] for i in items})
    body, request, shown, native = await MF.submit_created(e, "/api/procurement/orders", "/api/procurement/orders/", status=201, body_key=("id",))
    key = body["id"]
    require(request == {"request_id": request["request_id"], "supplier_id": supplier["id"], "reason": reason, "lines": lines}
            and shown["state"] == "approval" and shown["flow_version"] == 3, "新精品采购原封包/类型不符")
    protection = guard.finish()
    native.update(guard=protection, receipt=MF.flow_receipt(e, request, actor, key, "procurement_create", {k: v for k, v in request.items() if k != "request_id"}),
                  event=MF.event(e, guard, key, "procurement_create"))
    require([(r["item_id"], r["quantity_milli"], r["unit_cost_cents"], r["amount_cents"]) for r in subset(e, "procurement_lines", "case_id", key)]
            == [(items[0]["id"], 4000, 1000, 4000), (items[1]["id"], 2000, 2000, 4000)], "两行采购量价未按原输入冻结")
    return key, native


async def purchase_action(e, context, credentials, fixture, key, action, item_ids, *, role, task_key=None, evidence=None,
                          amount=None, account=None, reference=None, returned=None, original=None):
    handoff = await responsible(e, context, credentials, fixture, key, task_key, role) if task_key else None
    actor, view = await MAT.detail(e, context, credentials, fixture, role, key, "procurement")
    await MAT.action_form(e, "procurement", action, returned["id"] if returned else None)
    values = {}
    if returned:
        current = one(e, "procurement_returns", returned["id"])
        values.update(return_id=current["id"], return_version=current["version"])
    if action == "return_approve":
        values["reason"] = "另一主管核对原精品批次实际可退量与供应商冲款"
        await e.fill('#modal [name="reason"]', values["reason"], "填写独立原退审批依据")
    if amount is not None:
        await e.fill('#modal [name="amount"]', fen_text(amount), "填写本笔实际精品原款")
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        await e.fill('#modal [name="reference"]', reference, "填写唯一实际款项凭证")
        values.update(amount_cents=amount, account_id=account["id"], reference=reference)
    if original:
        option = e.page.locator(f'#modal select[name="original_payment_id"] option[value="{original["id"]}"]')
        await expect(option).to_have_count(1)
        label = await option.text_content()
        cash = one(e, "cash_entries", original["cash_id"])
        require(cash["store_id"] == 1 and cash["account"] == account["name"] and cash["amount_cents"] == 4000
                and original["amount_cents"] == 4000 and original["direction"] == "out", "本次原40元付款及冻结现金来源不符")
        require(all(part in label for part in (cash["business_date"], "凭证 " + original["reference"],
                cash["account"], "原付 40.00 元", "本笔剩余 40.00 元", "付款 " + str(original["id"]))),
                "原款选项未明确本次原40元付款的日期/账户/凭证/余额/ID")
        await live_choice(e, "original_payment_id", original["reference"], label, expected_value=original["id"])
        values["original_payment_id"] = original["id"]
    if evidence:
        await MAT.file_choice(e, "evidence_id", evidence["file"])
        values["evidence_id"] = evidence["file"]["id"]
    allowed = {**FLOW, "flow_tasks": (0, 2)}
    changed_items = item_ids if action in {"return_approve", "return_dispatch"} else ()
    if action in {"pay", "refund"}:
        allowed.update(cash_entries=1, procurement_payments=1)
    if action == "return_dispatch":
        allowed.update(flow_stock_moves=1, procurement_return_postings=1, procurement_return_valuations=1, warehouse_entries=1)
    guard = Guard(e, "boutique_purchase_" + action, actor, append=allowed,
        update=updates(e, key, items=changed_items, balances=action == "return_dispatch", allocations=action == "return_dispatch",
                       returned=returned["id"] if returned else None, account=account["id"] if account else None), cases={key}, items=item_ids)
    before = one(e, "flow_cases", key)
    body, request, shown, native = await submit(e, f"/api/procurement/orders/{key}/actions/{action}", f"/api/procurement/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": before["version"], "values": values}
            and shown["version"] == one(e, "flow_cases", key)["version"] > before["version"], "原精品采购提交CAS/精确内容不符")
    native.update(guard=guard.finish(), handoff=handoff,
                  receipt=MF.flow_receipt(e, request, actor, key, "procurement_" + action, {"case_id": key, "version": before["version"], "values": values}))
    events = guard.added["flow_events"]
    require(len(events) == 1 and events[0]["action"] == "procurement_" + action and events[0]["actor_id"] == actor["id"], "采购原事件错配")
    audit = guard.added["audit_logs"][0]
    require(audit["actor_id"] == actor["id"] and audit["store_id"] == 1
            and audit["action"] == "flow_procurement_" + action
            and audit["entity_type"] == "flow" and audit["entity_id"] == key, "原采购审计本人/动作/来源错配")
    native["event"] = MF.json_row(events[0], "detail")
    return shown, native


async def receive_batch(e, context, credentials, fixture, key, items, location, warehouse, evidence):
    # Login ends before both original prepare and receive baselines.
    await responsible(e, context, credentials, fixture, key, "procurement_receive", "inventory")
    actor, shown = await MAT.detail(e, context, credentials, fixture, "inventory", key, "procurement")
    await MAT.action_form(e, "procurement", "receive")
    quantities = (2000, 1000)
    line_ids = {r["item_id"]: r["id"] for r in shown["lines"]}
    for item, quantity in zip(items, quantities):
        await e.fill(f'#modal [name="quantity_{line_ids[item["id"]]}"]', MAT.qty(quantity), "本批真实到货精品数量")
    await MAT.file_choice(e, "evidence", evidence["file"])
    await e.click('#modal [data-prep-open]', "为本批到货分配原实物库位")
    await expect(e.page.locator('#modal [data-prep-body]')).to_be_visible()
    for item, quantity in zip(items, quantities):
        root = e.page.locator(f'#modal [data-prep-item="{item["id"]}"]')
        await MAT.choose(e, root, 'select[data-prep-bin]', location["name"], warehouse["name"] + " · " + location["name"], location["id"])
        e.action("fill", "本批这件精品原库位数量", item_id=item["id"], quantity_milli=quantity)
        await root.locator('[data-prep-quantity]').fill(MAT.qty(quantity))
    version = one(e, "flow_cases", key)["version"]
    guard = Guard(e, "boutique_batch_position", actor, append={"flow_events": 2, "audit_logs": 2, "flow_request_receipts": 2,
        "warehouse_allocations": 2, "warehouse_allocation_lines": 2}, update={"flow_cases": {key: VERSION}}, cases={key}, items={i["id"] for i in items})
    responses = []
    def collect(response):
        if response.request.method == "POST" and urlsplit(response.url).path == f"/api/warehouse/allocations/{key}":
            responses.append(response)
    e.page.on("response", collect)
    try:
        await e.click('#modal [data-prep-save]', "保存两行原库位准备")
        await expect(e.page.locator('#modal [data-prep-status]')).to_have_text("库位已保存。核对本表后，再确认实际收发。")
    finally:
        e.page.remove_listener("response", collect)
    require(len(responses) == 2, "本批两行库位未分别确认")
    natives = []
    for index, response in enumerate(responses):
        body = await response.json()
        require(response.status == 200 and body["prepared"] is True and body["case_id"] == key, "原准备响应不符")
        meta, request = await MAT.response_meta(e, response, body)
        values = {"item_id": items[index]["id"], "quantity_milli": quantities[index], "purpose": "procurement_receipt",
                  "locations": [{"location_id": location["id"], "quantity_milli": quantities[index]}]}
        require(request == {"request_id": request["request_id"], "version": version + index, "values": values}, "两行原准备未推进当前版本")
        meta["receipt"] = MF.flow_receipt(e, request, actor, key, "warehouse_allocation", {"id": key, "version": version + index, **values})
        natives.append(meta)
    preparation = {"native": natives, "guard": guard.finish(), "allocations": guard.added["warehouse_allocations"], "lines": guard.added["warehouse_allocation_lines"]}
    before_receipts = {r["id"] for r in subset(e, "procurement_receipts", "case_id", key)}
    guard = Guard(e, "boutique_batch_receive", actor,
        append={**FLOW, "flow_tasks": (0, 1), "procurement_receipts": 2, "flow_stock_moves": 2, "warehouse_entries": 2},
        update=updates(e, key, items={i["id"] for i in items}, balances=True, allocations=True), cases={key}, items={i["id"] for i in items})
    current = one(e, "flow_cases", key)
    values = {"lines": [{"line_id": line_ids[i["id"]], "quantity_milli": q} for i, q in zip(items, quantities)], "evidence_id": evidence["file"]["id"]}
    body, request, shown, native = await submit(e, f"/api/procurement/orders/{key}/actions/receive", f"/api/procurement/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": current["version"], "values": values}, "真实收货封包不符")
    native.update(guard=guard.finish(), event=MF.event(e, guard, key, "procurement_receive"),
                  receipt=MF.flow_receipt(e, request, actor, key, "procurement_receive", {"case_id": key, "version": current["version"], "values": values}))
    receipts = guard.added["procurement_receipts"]
    require([(r["quantity_milli"], r["value_cents"]) for r in receipts] == [(2000, 2000), (1000, 2000)]
            and all(r["id"] not in before_receipts and r["evidence_id"] == evidence["file"]["id"] for r in receipts), "本批新精品实收量价或唯一原源不符")
    for item, receipt in zip(items, receipts):
        move = one(e, "flow_stock_moves", receipt["stock_move_id"])
        allocation = next(a for a in preparation["allocations"] if a["item_id"] == item["id"])
        positions = subset(e, "warehouse_entries", "stock_move_id", move["id"])
        require(receipt["line_id"] == line_ids[item["id"]] and move["item_id"] == item["id"] and move["purpose"] == "procurement_receipt"
                and move["original_id"] is None and (move["quantity_milli"], move["value_cents"]) == (receipt["quantity_milli"], receipt["value_cents"])
                and one(e, "warehouse_allocations", allocation["id"])["stock_move_id"] == move["id"]
                and sum(r["quantity_milli"] for r in positions) == move["quantity_milli"] and sum(r["value_cents"] for r in positions) == move["value_cents"], "真实收货/库存/位置原源不守恒")
    return {"preparation": preparation, "receive": native, "api": shown, "receipts": receipts, "stock_moves": guard.added["flow_stock_moves"]}


async def prepare(e, context, credentials, fixture, key, items, location, purpose, quantities):
    actor, _ = await read_as(e, context, credentials, fixture, "inventory", "warehouse-allocation/" + str(key),
                             "/api/warehouse/allocations/" + str(key), "准备物资库位")
    result = []
    for item, quantity in zip(items, quantities):
        await e.click(f'#main [data-act="wh-allocate"][data-id="{item["id"]}"]', "准备这件精品本次精确库位")
        await expect(e.page.locator("#modal-title")).to_have_text("准备库位（尚未实际收发）")
        await select_value(e, '#modal [name="purpose"]', purpose, "选择本次原收发动作")
        await e.fill('#modal [name="quantity"]', MAT.qty(abs(quantity)), "填写本次实际数量")
        await select_value(e, '#modal [name="location"]', location["id"], "选实际原精品库位")
        await e.fill('#modal [name="location_qty"]', MAT.qty(abs(quantity)), "填写这个真实库位数量")
        before = one(e, "flow_cases", key)
        previous = {r["id"] for r in subset(e, "warehouse_allocations", "case_id", key)}
        guard = Guard(e, "boutique_position_prepare", actor, append={**FLOW, "warehouse_allocations": 1, "warehouse_allocation_lines": 1},
            update=updates(e, key, allocations=True, items={item["id"]}), cases={key}, items={item["id"]})
        # Preparing must not touch Item or balances, even though actual post will.
        guard.update.pop("flow_items", None)
        body, request, shown, native = await submit(e, f"/api/warehouse/allocations/{key}", f"/api/warehouse/allocations/{key}")
        expected = {"item_id": item["id"], "quantity_milli": quantity, "purpose": purpose,
                    "locations": [{"location_id": location["id"], "quantity_milli": abs(quantity)}]}
        require(request == {"request_id": request["request_id"], "version": before["version"], "values": expected}
                and body["prepared"] is True and shown["version"] == one(e, "flow_cases", key)["version"], "库位准备原内容/版本错配")
        native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, key, "warehouse_allocation", {"id": key, "version": before["version"], **expected}))
        added = [r for r in subset(e, "warehouse_allocations", "case_id", key) if r["id"] not in previous]
        require(len(added) == 1 and added[0]["quantity_milli"] == quantity and added[0]["purpose"] == purpose and added[0]["status"] == "prepared", "缺唯一原库位准备")
        result.append({"allocation": added[0], "native": native})
    return result


async def purchase_return(e, context, credentials, fixture, key, items, receipt, evidence, location, account, cash_proof, first_payment, token):
    actor, _ = await MAT.detail(e, context, credentials, fixture, "inventory", key, "procurement")
    await MAT.action_form(e, "procurement", "return_request")
    await e.fill(f'#modal [name="quantity_{receipt["id"]}"]', "1.000", "原第一批A实退一件")
    await MAT.file_choice(e, "evidence", evidence["file"])
    reason = "原第一批精品A一件退供应商，保持原批次和原款"
    await e.fill('#modal [name="reason"]', reason, "填写真实退货来源")
    guard = Guard(e, "boutique_return_request", actor, append={**FLOW, "flow_tasks": 1, "procurement_returns": 1, "procurement_return_lines": 1},
                  update=updates(e, key), cases={key}, items={i["id"] for i in items})
    before = one(e, "flow_cases", key)
    body, request, _, native = await submit(e, f"/api/procurement/orders/{key}/actions/return_request", f"/api/procurement/orders/{key}")
    values = {"lines": [{"receipt_id": receipt["id"], "quantity_milli": 1000}], "evidence_id": evidence["file"]["id"], "reason": reason}
    require(request == {"request_id": request["request_id"], "version": before["version"], "values": values}, "原退货不是指定第一批")
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, key, "procurement_return_request", {"case_id": key, "version": before["version"], "values": values}))
    returned = guard.added["procurement_returns"][0]
    require(returned["requested_by"] == actor["id"] and guard.added["procurement_return_lines"][0]["receipt_id"] == receipt["id"], "原退申请人/批次错误")
    _, approval = await purchase_action(e, context, credentials, fixture, key, "return_approve", {items[0]["id"]}, role="manager",
        task_key="procurement_return_review_" + str(returned["id"]), returned=returned)
    require(one(e, "procurement_returns", returned["id"])["approved_by"] != actor["id"], "退货未由不同主管批准")
    await MAT.stock_page(e, context, credentials, fixture, "inventory", items[0]["id"], quantity=4000, value=4000, reserved=1000)
    prepared = await prepare(e, context, credentials, fixture, key, (items[0],), location, "procurement_return", (-1000,))
    _, dispatched = await purchase_action(e, context, credentials, fixture, key, "return_dispatch", {items[0]["id"]}, role="inventory",
        task_key="procurement_return_dispatch_" + str(returned["id"]), returned=returned, evidence=evidence)
    posting = subset(e, "procurement_return_postings", "case_id", key)
    require(len(posting) == 1 and posting[0]["receipt_id"] == receipt["id"] and posting[0]["quantity_milli"] == posting[0]["value_cents"] == 1000, "实退未引用原批次")
    move = one(e, "flow_stock_moves", posting[0]["stock_move_id"])
    valuation = one(e, "procurement_return_valuations", posting[0]["id"])
    require(move["original_id"] == receipt["stock_move_id"] and move["quantity_milli"] == move["value_cents"] == -1000
            and valuation["inventory_cost_cents"] == valuation["supplier_credit_cents"] == 1000 and valuation["variance_cents"] == 0, "原库存成本/冲款/差额混淆")
    shown, refund = await purchase_action(e, context, credentials, fixture, key, "refund", (), role="finance", task_key="procurement_refund",
        evidence=cash_proof, amount=1000, account=account, reference="BT-REF-" + token, original=first_payment)
    finance = e.manifest["users"][fixture["finance_key"]]
    cash = MAT.cash_fact(e, key, 1000, "in", "BT-REF-" + token, account, finance, first_payment)
    require(shown["state"] == "completed" and shown["totals"]["received_cents"] == 8000 and shown["totals"]["returned_cents"] == 1000
            and shown["totals"]["paid_net_cents"] == 7000 and shown["totals"]["payable_cents"] == shown["totals"]["supplier_refund_due_cents"] == 0,
            "部分原退/实际退款未独立闭合")
    return {"request": native, "return": one(e, "procurement_returns", returned["id"]), "approval": approval, "preparation": prepared,
            "dispatch": dispatched, "posting": posting[0], "stock_move": move, "valuation": valuation, "refund": refund, "cash": cash}


async def coupon_rule(e, context, credentials, fixture, customer, member, token):
    actor, _ = await read_as(e, context, credentials, fixture, "manager", "benefits/" + str(customer["id"]),
                             "/api/group/benefits/members", "集团权益")
    await e.click('#main [data-act="benefit-rule"]', "发布本次新精品的独立付费券版")
    await expect(e.page.locator("#modal-title")).to_have_text("发布权益规则新版本")
    values = {"code": "BT-COUPON-" + token, "name": "本轮精品商品券" + token, "kind": "coupon", "allowed_store_ids": [1],
              "credit_cents_per_unit": 500, "settlement_cents_per_unit": 500, "sale_cents_per_unit": 400,
              "exchange_points_per_unit": 0, "refund_policy": "unused_before_expiry", "discount_bearer": "group",
              "validity_days": 30, "service_code": ""}
    for field, value in (("code", values["code"]), ("name", values["name"]), ("stores", "1"), ("credit", "5.00"),
                         ("settlement", "5.00"), ("sale", "4.00"), ("exchange_points_per_unit", "0"), ("validity_days", "30"), ("service_code", "")):
        await e.fill(f'#modal [name="{field}"]', value, "新券的冻结字段：" + field)
    for field in ("kind", "refund_policy", "discount_bearer"):
        await select_value(e, f'#modal [name="{field}"]', values[field], "明确原券枚举：" + field)
    guard = Guard(e, "boutique_new_coupon_rule", actor, append={"benefit_rules": 1, "group_events": 1, "group_receipts": 1}, member=member)
    body, request, _, native = await submit(e, "/api/group/benefits/rules", "/api/group/benefits/rules", status=201)
    row = MF.json_row(one(e, "benefit_rules", body["id"]), "allowed_store_ids")
    require(request == {"request_id": request["request_id"], "values": values} and all(row[k] == v for k, v in values.items())
            and row["rule_version"] == 1 and row["created_by"] == actor["id"] and row["issuer_store_id"] == 1, "券C/P/S或承担方冻结不符")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "benefit_rule", values, body))
    ge = guard.added["group_events"][0]
    require(ge["action"] == "benefit_rule" and ge["member_id"] is None and json.loads(ge["detail"]) == {"rule_id": row["id"]}, "券原发布事件串源")
    native["group_event_id"] = ge["id"]
    await expect(e.page.locator("#main")).to_contain_text(row["name"])
    return row, native


async def paid_coupon(e, context, credentials, fixture, customer, member, rule, account, token, eligibility):
    actor, _ = await read_as(e, context, credentials, fixture, "service", "membership/" + str(customer["id"]), "/api/membership/members", "会员卡与续会")
    await original_form(e, "membership-create", "purchase", "权益发行")
    await select_value(e, '#modal [name="rule"]', f'{rule["id"]} · {rule["name"]} · 版本{rule["rule_version"]}', "选本次新券冻结版")
    await e.fill('#modal [name="units"]', "1", "本次实际购买一张新商品券")
    reason = "客户购买本轮精品新券一张，发行宿主和消费单分别留事实"
    await e.fill('#modal [name="reason"]', reason, "填写新券原购买依据")
    values = {"action": "purchase", "rule_id": rule["id"], "units": 1}
    guard = Guard(e, "boutique_coupon_host", actor, append={"flow_events": 1, "audit_logs": 1, "flow_cases": 1, "flow_tasks": 1, "membership_orders": 1,
        "membership_events": 1, "group_receipts": 1}, update={"group_members": {member: VERSION}}, new_kind="membership", customer=customer["id"], member=member)
    body, request, shown, native = await MF.submit_created(e, "/api/membership/orders", "/api/membership/orders/", status=201, body_key=("case", "id"))
    key = body["case"]["id"]
    require(request == {"request_id": request["request_id"], "customer_id": customer["id"], "purpose": "benefit_issue", "values": values, "reason": reason}
            and shown["case"]["amount_cents"] == 400, "新券宿主不是本次一张400分")
    created = {"native": native, "guard": guard.finish(), "event": MF.event(e, guard, key, "membership_create"),
        "receipt": group_receipt(e, request, actor, "membership_create", {k: v for k, v in request.items() if k != "request_id"}, body)}
    handoff = await responsible(e, context, credentials, fixture, key, "membership_execute", "finance")
    actor, _ = await read_as(e, context, credentials, fixture, "finance", "membership-order/" + str(key), "/api/membership/orders/" + str(key), "会员业务办理")
    evidence = await proof(e, actor, key, member, "/api/membership/orders/" + str(key), "evidence", "boutique-new-coupon-paid", token)
    case, db_member = one(e, "flow_cases", key), one(e, "group_members", member)
    order = subset(e, "membership_orders", "case_id", key)[0]
    await original_form(e, "membership-action", "execute", "确认实际办理")
    await MF.choose_file(e, evidence)
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference, reason = "BT-COUPON-IN-" + token, "实际收到本张精品券款4元，集团承担1元优惠"
    await e.fill('#modal [name="reference"]', reference, "填写本笔发行实收唯一流水")
    await e.fill('#modal [name="reason"]', reason, "财务本人核对实际发行款")
    values = {"evidence_id": evidence["file"]["id"], "reason": reason, "account_id": account["id"], "reference": reference}
    permitted = updates(e, key, member=member, account=account["id"])
    permitted["group_members"] = {member: VERSION}
    permitted["flow_cases"][eligibility["case_id"]] = VERSION
    permitted["membership_orders"] = {order["id"]: VERSION | {"status"}}
    guard = Guard(e, "boutique_coupon_actual_issuance", actor, append={"flow_events": 2, "audit_logs": 2, "group_receipts": 1,
        "group_events": 1, "membership_events": 1, "cash_entries": 1, "benefit_wallets": 1, "benefit_entries": 1,
        "benefit_settlements": 2, "retail_group_wallets": 1}, update=permitted, cases={key, eligibility["case_id"]}, member=member)
    body, request, shown, native = await submit(e, f"/api/membership/orders/{key}/actions/execute", f"/api/membership/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": order["version"], "case_version": case["version"],
        "member_version": db_member["version"], "values": values} and shown["order"]["status"] == "completed", "新券发行当前双CAS不符")
    protection = guard.finish()
    wallet, entry, binding = guard.added["benefit_wallets"][0], guard.added["benefit_entries"][0], guard.added["retail_group_wallets"][0]
    require(wallet["source_kind"] == entry["purpose"] == "purchase" and wallet["initial_units"] == wallet["balance_units"] == entry["units"] == 1
            and wallet["reserved_units"] == 0 and wallet["rule_id"] == rule["id"] and wallet["cash_id"] == entry["cash_id"]
            and entry["wallet_id"] == binding["wallet_id"] == wallet["id"] and binding["origin_id"] == entry["id"]
            and binding["decision_id"] == eligibility["decision"]["id"] and one(e, "group_members", member)["balance_cents"] == db_member["balance_cents"], "发行没有绑定本次独立商品资格或错加本金")
    cash = MF.cash_fact(e, entry, "in", 400, "benefit_purchase", account, actor)
    payload = {"rule_id": rule["id"], "units": 1, **values, "case_id": key, "case_version": case["version"]}
    native.update(guard=protection, receipt=group_receipt(e, request, actor, "benefit:" + str(member) + ":purchase",
                  {"version": db_member["version"], "values": payload}, body["result"]))
    require([r["action"] for r in guard.added["flow_events"]] == ["membership_purchase", "benefit_purchase"], "发行两原事件缺失")
    return {"case_id": key, "wallet": wallet, "purchase_entry": entry, "cash": cash,
            "settlements": MF.paired(e, "benefit_settlements", entry["id"], 400), "binding": binding,
            "create": created, "handoff": handoff, "proof": evidence, "execute": native}


async def retail_read(e, context, credentials, fixture, role, key):
    original = one(e, "flow_cases", key)
    actor, body = await read_as(e, context, credentials, fixture, role, "retail/" + str(key), RETAIL + "/orders/" + str(key), "精品销售 · " + original["number"])
    require(body["id"] == key and body["version"] == original["version"] and body["state"] == original["state"], "精品原详情当前CAS/状态不符")
    return actor, body


async def retail_create(e, context, credentials, fixture, customer, member, items, work):
    actor, _ = await read_as(e, context, credentials, fixture, "service", "retail", RETAIL + "/orders", "精品销售与退货")
    await e.click('#main [data-act="retail-new"]', "服务顾问本人创建本次两件精品原销售单")
    await expect(e.page.locator("#modal-title")).to_have_text("新建精品订单")
    label = await e.page.locator(f'#modal [name="customer"] option[value="{customer["id"]}"]').text_content()
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases"
            and parse_qs(urlsplit(r.url).query).get("kind") == ["repair"] and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        await live_choice(e, "customer", customer["name"], label, expected_value=customer["id"])
    require((await pending.value).status == 200, "原关联维修候选未读取完成")
    await expect(e.page.locator('#modal [data-member-price-field]')).not_to_have_attribute("data-loading", "true")
    await e.click('#modal [data-act="retail-add-line"]', "新增另一件明确精品商品行")
    require(await e.page.locator('#modal [data-retail-line]').count() == 2, "原多商品行未生成")
    values = []
    for index, item in enumerate(items):
        root = e.page.locator('#modal [data-retail-line]').nth(index)
        label = await root.locator(f'[name="item"] option[value="{item["id"]}"]').text_content()
        await MAT.choose(e, root, '[name="item"]', item["sku"], label, item["id"])
        e.action("fill", "本商品精确数量/商品单价", item_id=item["id"])
        await root.locator('[name="quantity"]').fill("1.000")
        await root.locator('[name="price"]').fill("25.00" if index == 0 else "30.00")
        if index == 0:
            label = await root.locator(f'[name="work"] option[value="{work["id"]}"]').text_content()
            await MAT.choose(e, root, '[name="work"]', work["code"], label, work["id"])
        else:
            await expect(root.locator('[name="work"]')).to_have_value("")
        e.action("fill", "本商品明确安装费用", item_id=item["id"], installation_cents=500 if index == 0 else 0)
        await root.locator('[name="install_price"]').fill("5.00" if index == 0 else "0.00")
        values.append({"item_id": item["id"], "quantity_milli": 1000, "unit_price_cents": 2500 if index == 0 else 3000,
                       "work_item_id": work["id"] if index == 0 else None, "installation_unit_price_cents": 500 if index == 0 else 0})
    await expect(e.page.locator('#modal [name="related"]')).to_have_value("")
    await e.fill('#modal [name="discount"]', "0.00", "本次不猜手工整单优惠")
    await select_value(e, '#modal [name="member_pricing_rule"]', "", "无会期价格规则，不默认优惠")
    item_ids = {i["id"] for i in items}
    guard = Guard(e, "boutique_retail_create", actor, append={**FLOW, "flow_cases": 1, "flow_tasks": 1,
        "retail_orders": 1, "retail_lines": 2, "retail_reservations": 2}, update={"flow_items": {i: VERSION for i in item_ids}},
        items=item_ids, member=member, new_kind="retail", customer=customer["id"])
    body, request, shown, native = await MF.submit_created(e, RETAIL + "/orders", RETAIL + "/orders/", status=201, body_key=("id",))
    key = body["id"]
    expected = {"customer_id": customer["id"], "related_repair_id": None, "discount_cents": 0, "lines": values}
    require(request == {"request_id": request["request_id"], **expected} and shown["amount_cents"] == 6000 and shown["revision"] == 1
            and shown["state"] == "approval", "两商品/安装原冻结报价不符")
    native.update(guard=guard.finish(), event=MF.event(e, guard, key, "retail_create"),
                  receipt=MF.flow_receipt(e, request, actor, key, "retail_create", expected))
    lines = guard.added["retail_lines"]
    require(len(lines) == 2 and [(r["item_id"], r["quantity_milli"], r["goods_cents"], r["installation_cents"], r["work_item_id"]) for r in lines]
            == [(items[0]["id"], 1000, 2500, 500, work["id"]), (items[1]["id"], 1000, 3000, 0, None)]
            and lines[0]["work_code"] == work["code"] and all(r["quantity_milli"] == 1000 for r in guard.added["retail_reservations"]), "冻结行/实际安装代码/占量错配")
    for item, quantity, value in ((items[0], 3000, 3000), (items[1], 2000, 4000)):
        require(one(e, "flow_items", item["id"])["quantity_milli"] == quantity and one(e, "flow_items", item["id"])["inventory_value_cents"] == value, "建单占额冒充实物出库")
    return key, {"native": native, "lines": lines, "order": one(e, "retail_orders", key), "reservations": guard.added["retail_reservations"]}


async def retail_action(e, context, credentials, fixture, key, action, items, member, token):
    role, task_key, title, category = {
        "approve": ("manager", "retail_approve", "主管价格授权", None),
        "authorize": ("service", "retail_authorize", "记录客户报价确认", "authorization"),
        "dispatch": ("inventory", "retail_dispatch", "确认整单实际出库", "evidence"),
        "install": ("technician", "retail_install", "确认实际安装", "evidence"),
        "accept": ("service", "retail_accept", "确认客户接收", "evidence"),
    }[action]
    handoff = await responsible(e, context, credentials, fixture, key, task_key, role)
    actor, _ = await retail_read(e, context, credentials, fixture, role, key)
    evidence = await proof(e, actor, key, member, RETAIL + f"/orders/{key}", category, "boutique-" + action, token) if category else None
    original = one(e, "flow_cases", key)
    before_items = {i["id"]: one(e, "flow_items", i["id"]) for i in items}
    await original_form(e, "retail-action", action, title)
    values = {"evidence_id": evidence["file"]["id"]} if evidence else {}
    if action == "approve":
        await e.fill('#modal [name="minimum"]', "60.00", "独立主管明确两商品含安装最低价")
        await checkbox(e, '#modal [name="allow_below_minimum"]', False, "本单无需低价例外")
        values = {"minimum_total_cents": 6000, "allow_below_minimum": False, "reason": "独立核对两件精品及安装合计60元"}
        await e.fill('#modal [name="reason"]', values["reason"], "主管原价格复核依据")
        require(actor["id"] != original["created_by"], "精品报价不能由开单人自批")
    if action == "authorize":
        values["revision"] = 1
    if action == "install":
        values["result"] = "本人实际安装精品A并核对完成，精品B无需安装"
        await e.fill('#modal [name="result"]', values["result"], "本人实际安装结果")
    if evidence:
        await MF.choose_file(e, evidence, category)
    append = {**FLOW, "flow_tasks": (0, 2)}
    permitted = updates(e, key)
    allocations = []
    if action == "authorize":
        append["membership_points_claims"] = 1
        permitted["group_members"] = {member: VERSION}
    if action == "dispatch":
        for item in items:
            matches = [a for a in subset(e, "warehouse_allocations", "case_id", key) if a["item_id"] == item["id"]
                       and a["purpose"] == "retail_dispatch" and a["status"] == "prepared" and a["quantity_milli"] == -1000]
            require(len(matches) == 1, "实物出库没有唯一原准备")
            allocations.extend(matches)
        append.update(retail_reservations=2, flow_stock_moves=2, retail_dispatches=2, warehouse_entries=2)
        permitted = updates(e, key, items={i["id"] for i in items}, balances=True)
        permitted["warehouse_allocations"] = {a["id"]: VERSION | {"status", "stock_move_id"} for a in allocations}
    guard = Guard(e, "boutique_retail_" + action, actor, append=append, update=permitted,
                  cases={key}, items=set(before_items), member=member)
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/{action}", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": original["version"], "values": values}
            and shown["version"] == one(e, "flow_cases", key)["version"] > original["version"], "精品原动作CAS/内容不符")
    native.update(guard=guard.finish(), event=MF.event(e, guard, key, "retail_" + action), handoff=handoff, proof=evidence,
                  receipt=MF.flow_receipt(e, request, actor, key, "retail_" + action, {"case_id": key, "version": original["version"], "values": values}))
    data = json.loads(one(e, "flow_cases", key)["data"])
    flag = {"approve": "approved", "authorize": "authorized", "dispatch": "dispatched", "install": "installed", "accept": "accepted_date"}[action]
    require(bool(data.get(flag)), "原动作未留真实事实：" + flag)
    if action == "dispatch":
        for item, cost in zip(items, (1000, 2000)):
            move = next(r for r in guard.added["flow_stock_moves"] if r["item_id"] == item["id"])
            d = next(r for r in guard.added["retail_dispatches"] if r["stock_move_id"] == move["id"])
            a = next(a for a in allocations if a["item_id"] == item["id"])
            require(move["quantity_milli"] == -1000 and move["value_cents"] == -cost and move["purpose"] == "retail_dispatch"
                    and d["quantity_milli"] == 1000 and d["value_cents"] == cost and d["evidence_id"] == evidence["file"]["id"]
                    and one(e, "warehouse_allocations", a["id"])["stock_move_id"] == move["id"], "整单实物/原库存成本错配")
            after = MAT.item_stock(e, item["id"])
            require(after["item"]["quantity_milli"] == before_items[item["id"]]["quantity_milli"] - 1000
                    and after["item"]["inventory_value_cents"] == before_items[item["id"]]["inventory_value_cents"] - cost, "实际出库量值未守恒")
        require(all(r["quantity_milli"] == -1000 and r["reason"] == "dispatch" for r in guard.added["retail_reservations"]), "出库未释放原预占")
        native.update(dispatches=guard.added["retail_dispatches"], stock_moves=guard.added["flow_stock_moves"], warehouse_entries=guard.added["warehouse_entries"], reservations=guard.added["retail_reservations"])
    return native


async def mixed_plan(e, context, credentials, fixture, key, member, wallet, items, token):
    actor, catalog = await read_as(e, context, credentials, fixture, "service", "retail-group/" + str(key), RG + f"/orders/{key}/catalog", "精品集团混合付款")
    require(catalog["can_authorize"] and not catalog["has_plan"], "真实接收后仍不具备原混合方案条件")
    evidence = await proof(e, actor, key, member, RG + f"/orders/{key}/catalog", "authorization", "boutique-mixed-payment", token)
    case, db_member, db_wallet = one(e, "flow_cases", key), one(e, "group_members", member), one(e, "benefit_wallets", wallet["id"])
    await e.click('#main [data-act="rg-authorize"]', "客户明确新券一张与本金5元")
    await expect(e.page.locator("#modal-title")).to_have_text("冻结精品原付款方案")
    await e.fill('#modal [name="principal"]', "5.00", "明确使用本人原本金5元")
    await e.fill(f'#modal [name="wallet_{wallet["id"]}"]', "1", "只使用本批独立发行的一张新券")
    await select_value(e, '#modal [name="evidence"]', evidence["file"]["id"], "选择这次客户资金来源授权")
    await checkbox(e, '#modal [name="confirmed"]', True, "客户明确原批及原退期限")
    guard = Guard(e, "boutique_mixed_plan", actor, append={"flow_events": 1, "audit_logs": 1, "group_receipts": 1, "flow_tasks": 1,
        "retail_group_plans": 1, "retail_group_tenders": 3, "retail_group_units": 3, "retail_group_allocations": 7},
        update=updates(e, key), cases={key}, items={i["id"] for i in items}, member=member, wallets={wallet["id"]})
    body, request, shown, native = await submit(e, RG + f"/orders/{key}/actions/authorize", RG + f"/orders/{key}")
    selections = [{"kind": "principal", "amount_cents": 500}, {"kind": "coupon", "wallet_id": wallet["id"], "wallet_version": db_wallet["version"], "units": 1}]
    values = {"member_id": member, "member_version": db_member["version"], "evidence_id": evidence["file"]["id"], "selections": selections}
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "只应授权本次新券/本金两非现金来源")
    payload = {**values, "selections": [{"amount_cents": None, "wallet_id": None, "wallet_version": None, "units": None, **s} for s in selections]}
    native.update(guard=guard.finish(), event=MF.event(e, guard, key, "retail_group_authorize"), proof=evidence,
        receipt=group_receipt(e, request, actor, "retail_group_authorize", {"case_id": key, "version": case["version"], "values": payload}, body))
    plan = guard.added["retail_group_plans"][0]
    tenders = guard.added["retail_group_tenders"]
    require([(t["kind"], t["units"], t["credit_cents"], t["consideration_cents"], t["settlement_cents"]) for t in tenders]
            == [("principal", 500, 500, 500, 500), ("coupon", 1, 500, 400, 500), ("cash", 5000, 5000, 5000, 5000)]
            and tenders[1]["wallet_id"] == wallet["id"] and all(t["wallet_id"] is None for t in (tenders[0], tenders[2])), "混合方案面值/实款/往来或单位混淆")
    lines = subset(e, "retail_lines", "case_id", key)
    capacities = {(lines[0]["id"], "goods"): 2500, (lines[0]["id"], "installation"): 500, (lines[1]["id"], "goods"): 3000}
    frozen = []
    for tender in tenders:
        unit = subset(e, "retail_group_units", "tender_id", tender["id"])
        require(len(unit) == 1, "本次每笔原来源需唯一单位")
        allocations = subset(e, "retail_group_allocations", "unit_id", unit[0]["id"])
        require(all(sum(a[f] for a in allocations) == unit[0][f] == tender[f] for f in ("credit_cents", "consideration_cents", "settlement_cents")), "单位/行份额C/P/S不守恒")
        require({(a["line_id"], a["component"]) for a in allocations} == ({(lines[0]["id"], "goods")} if tender["kind"] == "coupon" else set(capacities)), "新券不得扩到B或安装费")
        frozen.append({"tender": tender, "unit": unit[0], "allocations": allocations})
    for cell, capacity in capacities.items():
        require(sum(a["credit_cents"] for a in guard.added["retail_group_allocations"] if (a["line_id"], a["component"]) == cell) == capacity, "现金余份与原行核价不守恒")
    digest = sha(json.dumps(["retail_group_plan", {"selections": payload["selections"], "evidence_id": evidence["file"]["id"], "case_id": key}], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    require(plan["digest"] == digest and one(e, "group_members", member) == db_member and one(e, "benefit_wallets", wallet["id"]) == db_wallet
            and all(t["status"] == "authorized" for t in shown["tenders"] if t["kind"] != "cash"), "方案冻结不得提前占额/扣款")
    return {"plan": plan, "tenders": tenders, "frozen_parts": frozen, "native": native}


async def mixed_capture(e, context, credentials, fixture, key, member, wallet, plan, token):
    handoff = await responsible(e, context, credentials, fixture, key, "retail_group_payment", "finance")
    actor, _ = await read_as(e, context, credentials, fixture, "finance", "retail-group/" + str(key), RG + f"/orders/{key}", "精品集团混合付款")
    evidence = await proof(e, actor, key, member, RG + f"/orders/{key}", "evidence", "boutique-original-reserve-capture", token)
    operations = []
    for tender in [t for t in plan["tenders"] if t["kind"] != "cash"]:
        wid = tender["wallet_id"]
        for action in ("reserve", "capture"):
            case, current_plan, db_member = one(e, "flow_cases", key), one(e, "retail_group_plans", plan["plan"]["id"]), one(e, "group_members", member)
            db_wallet = one(e, "benefit_wallets", wid) if wid else None
            underlying = None
            if action == "capture":
                link = subset(e, "retail_group_reservations", "tender_id", tender["id"])
                require(len(link) == 1, "实际核销缺唯一原占额")
                underlying = one(e, "benefit_reservations" if wid else "group_reservations", link[0]["benefit_id"] if wid else link[0]["principal_id"])
            await original_form(e, "rg-action", action, "占用原批次" if action == "reserve" else "确认实际核销", identifier=tender["id"])
            await MF.choose_file(e, evidence)
            values = {"evidence_id": evidence["file"]["id"], "plan_version": current_plan["version"], "member_version": db_member["version"], "tender_id": tender["id"]}
            if wid:
                values["wallet_version"] = db_wallet["version"]
            if underlying:
                values["reservation_version"] = underlying["version"]
            permitted = updates(e, key, member=member, wallet=wid)
            permitted["retail_group_plans"] = {current_plan["id"]: VERSION}
            append = {"flow_events": 1, "audit_logs": 1, "group_receipts": 1}
            if action == "reserve":
                append.update(retail_group_reservations=1)
                append["benefit_reservations" if wid else "group_reservations"] = 1
            else:
                append.update(retail_group_captures=1)
                append["benefit_entries" if wid else "group_entries"] = 1
                append["benefit_payment_links" if wid else "group_payment_links"] = 1
                append["benefit_settlements" if wid else "group_settlement_entries"] = 2
                permitted["benefit_reservations" if wid else "group_reservations"] = {underlying["id"]: VERSION | {"status"}}
            guard = Guard(e, "boutique_" + action + "_" + str(tender["id"]), actor, append=append, update=permitted,
                          cases={key}, member=member, wallets={wid} if wid else ())
            body, request, shown, native = await submit(e, RG + f"/orders/{key}/actions/{action}", RG + f"/orders/{key}")
            require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "每笔本金/券当前多CAS不符")
            native.update(guard=guard.finish(), event=MF.event(e, guard, key, "retail_group_" + action),
                receipt=group_receipt(e, request, actor, "retail_group_" + action, {"case_id": key, "version": case["version"], "values": {"wallet_version": None, **values}}, body))
            rendered = next(t for t in shown["tenders"] if t["id"] == tender["id"])
            require(rendered["status"] == ("reserved" if action == "reserve" else "captured"), "原UI资金状态与实际原账不符")
            current_member = one(e, "group_members", member)
            if wid:
                current_wallet = one(e, "benefit_wallets", wid)
                require(current_wallet["balance_units"] == db_wallet["balance_units"] - (1 if action == "capture" else 0)
                        and current_wallet["reserved_units"] == db_wallet["reserved_units"] + (1 if action == "reserve" else -1)
                        and current_member["balance_cents"] == db_member["balance_cents"] and current_member["reserved_cents"] == db_member["reserved_cents"], "券核销错误扣本金")
            else:
                require(current_member["balance_cents"] == db_member["balance_cents"] - (500 if action == "capture" else 0)
                        and current_member["reserved_cents"] == db_member["reserved_cents"] + (500 if action == "reserve" else -500), "本金占額与消费混淆")
            if action == "capture":
                entry = guard.added["benefit_entries" if wid else "group_entries"][0]
                require(entry["purpose"] == "capture" and entry["case_id"] == key and entry["cash_id"] is None
                        and (entry["units"] == -1 and entry["credit_cents"] == 500 if wid else entry["amount_cents"] == -500), "非现金原核销不得造实收现金")
                native.update(entry=entry, settlements=MF.paired(e, "benefit_settlements" if wid else "group_settlement_entries", entry["id"], -500))
            operations.append({"tender_id": tender["id"], "action": action, "native": native})
            await expect(e.page.locator("#main")).to_contain_text("已占额，未核销" if action == "reserve" else "已实际核销")
    totals = shown["totals"]
    require(totals["group_paid_cents"] == totals["group_internal_settlement_cents"] == 1000 and totals["group_recognized_cents"] == 900
            and totals["group_discount_borne_cents"] == 100 and totals["service_discount_borne_cents"] == 0 and totals["cash_collectable_cents"] == 5000
            and not subset(e, "retail_payments", "case_id", key) and not subset(e, "flow_payment_links", "case_id", key)
            and one(e, "group_members", member)["balance_cents"] == 9200, "两种原核销C/P/S或剩余现金混账")
    return {"handoff": handoff, "proof": evidence, "operations": operations, "totals": totals}


async def retail_cash(e, context, credentials, fixture, key, member, account, plan, amount, remaining, token, ordinal):
    handoff = await responsible(e, context, credentials, fixture, key, "retail_receive", "finance")
    actor, view = await retail_read(e, context, credentials, fixture, "finance", key)
    require(view["totals"]["cash_collectable_cents"] == amount + remaining, "不能按旧快照或集团抵扣额收现金")
    evidence = await proof(e, actor, key, member, RETAIL + f"/orders/{key}", "receipt", "boutique-cash-" + str(ordinal), token)
    await original_form(e, "retail-action", "receive", "登记实际收款")
    await e.fill('#modal [name="amount"]', fen_text(amount), "仅登记本笔实际现金")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference = "BT-RETAIL-IN-" + str(ordinal) + "-" + token
    await e.fill('#modal [name="reference"]', reference, "实际收款唯一流水")
    await MF.choose_file(e, evidence, "receipt")
    case = one(e, "flow_cases", key)
    current_plan = one(e, "retail_group_plans", plan["plan"]["id"])
    permitted = updates(e, key, account=account["id"])
    permitted["retail_group_plans"] = {current_plan["id"]: VERSION}
    guard = Guard(e, "boutique_cash_" + str(ordinal), actor, append={"flow_events": 1, "audit_logs": 2, "flow_request_receipts": 1,
        "flow_tasks": (0, 1), "cash_entries": 1, "flow_payment_links": 1, "retail_payments": 1, "retail_group_cash_allocations": (1, 3)},
        update=permitted, cases={key}, member=member)
    values = {"amount_cents": amount, "account_id": account["id"], "reference": reference, "evidence_id": evidence["file"]["id"]}
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/receive", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "两笔真实收款封包不符")
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, key, "retail_receive", {"case_id": key, "version": case["version"], "values": values}), handoff=handoff, proof=evidence)
    cash, link, payment = guard.added["cash_entries"][0], guard.added["flow_payment_links"][0], guard.added["retail_payments"][0]
    require(cash["direction"] == link["direction"] == "in" and cash["amount_cents"] == link["amount_cents"] == amount
            and cash["account"] == account["name"] and cash["category"] == "workflow_retail" and cash["created_by"] == actor["id"]
            and cash["voucher_no"] == link["reference"] == reference and cash["approval_state"] == "approved"
            and cash["payment_method"] == ("cash" if account["account_type"] == "cash" else "bank")
            and link["cash_id"] == cash["id"] and link["account_id"] == account["id"]
            and payment["payment_link_id"] == link["id"] and payment["evidence_id"] == evidence["file"]["id"], "实际现金/原付款/精品关联未唯一匹配")
    cash_tender = next(t for t in plan["tenders"] if t["kind"] == "cash")
    unit = subset(e, "retail_group_units", "tender_id", cash_tender["id"])[0]
    allowed_allocations = {a["id"] for a in subset(e, "retail_group_allocations", "unit_id", unit["id"])}
    parts = guard.added["retail_group_cash_allocations"]
    require(sum(p["amount_cents"] for p in parts) == amount and all(p["payment_link_id"] == link["id"] and p["allocation_id"] in allowed_allocations
            and p["original_id"] is None for p in parts), "原现金不得落到券/本金份额")
    totals = shown["totals"]
    require(totals["cash_collectable_cents"] == totals["receivable_cents"] == remaining and totals["group_paid_cents"] == 1000
            and totals["net_paid_cents"] == 6000 - remaining, "两笔现金与非现金抵扣累计不符")
    events = guard.added["flow_events"]
    require(len(events) == 1 and events[0]["action"] == "retail_receive" and events[0]["case_id"] == key, "每笔原收款事件缺失")
    return {"native": native, "cash": cash, "payment_link": link, "retail_payment": payment, "cash_allocations": parts,
            "event": MF.json_row(events[0], "detail"), "totals": totals}


async def boutique_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, customer, member, account, supplier, warehouse, location, brand, parent, work = dependencies(e, cp)
        token = uuid.uuid4().hex[:10]
        cp.start("HK-074")
        items, created_items = await make_items(e, context, credentials, fixture, brand, parent, location, supplier, token)
        purchase_id, created = await purchase_create(e, context, credentials, fixture, items, supplier)
        _, approved = await purchase_action(e, context, credentials, fixture, purchase_id, "approve", {i["id"] for i in items}, role="manager", task_key="procurement_approve")
        require(not subset(e, "procurement_receipts", "case_id", purchase_id) and not subset(e, "procurement_payments", "case_id", purchase_id)
                and all(one(e, "flow_items", i["id"])["quantity_milli"] == one(e, "flow_items", i["id"])["inventory_value_cents"] == 0 for i in items), "原采购申请批准不得造收货或付款")
        await cp.passed({"new_items_and_zero_positions": created_items, "original_purchase": created, "independent_approval": approved,
                         "no_stock_or_cash": True})

        cp.start("HK-052")
        inventory, _ = await MAT.detail(e, context, credentials, fixture, "inventory", purchase_id, "procurement")
        receiving_proof = await proof(e, inventory, purchase_id, None, f"/api/procurement/orders/{purchase_id}", "evidence", "boutique-actual-receipts", token)
        finance, _ = await MAT.detail(e, context, credentials, fixture, "finance", purchase_id, "procurement")
        cash_proof = await proof(e, finance, purchase_id, None, f"/api/procurement/orders/{purchase_id}", "receipt", "boutique-original-payments-refund", token)
        batches, payments = [], []
        for ordinal in (1, 2):
            batch = await receive_batch(e, context, credentials, fixture, purchase_id, items, location, warehouse, receiving_proof)
            _, paid = await purchase_action(e, context, credentials, fixture, purchase_id, "pay", (), role="finance", task_key="procurement_pay",
                evidence=cash_proof, amount=4000, account=account, reference="BT-PAY-" + str(ordinal) + "-" + token)
            actor = e.manifest["users"][fixture["finance_key"]]
            payment = MAT.cash_fact(e, purchase_id, 4000, "out", "BT-PAY-" + str(ordinal) + "-" + token, account, actor)
            batches.append(batch)
            payments.append({"native": paid, **payment})
            cp.note({"batch": ordinal, "receiving": batch, "actual_payment": payments[-1]})
        require(one(e, "flow_cases", purchase_id)["state"] == "completed" and len(subset(e, "procurement_receipts", "case_id", purchase_id)) == 4
                and not subset(e, "procurement_payment_allocations", "case_id", purchase_id), "两批新入库及原款未闭合，不能借预付款抵用")
        for item, quantity, value in ((items[0], 4000, 4000), (items[1], 2000, 4000)):
            await MAT.stock_page(e, context, credentials, fixture, "finance", item["id"], quantity=quantity, value=value)
        await cp.passed({"purchase_case_id": purchase_id, "batches": batches, "actual_payments": payments, "stocks": [MAT.item_stock(e, i["id"]) for i in items]})

        cp.start("HK-058")
        returned = await purchase_return(e, context, credentials, fixture, purchase_id, items, batches[0]["receipts"][0], receiving_proof,
                                         location, account, cash_proof, payments[0]["payment"], token)
        for item, quantity, value in ((items[0], 3000, 3000), (items[1], 2000, 4000)):
            await MAT.stock_page(e, context, credentials, fixture, "finance", item["id"], quantity=quantity, value=value)
        await cp.passed({"original_partial_supplier_return": returned, "stocks": [MAT.item_stock(e, i["id"]) for i in items], "zero_cost_variance_explicit": True})

        cp.start("HK-062")
        rule, rule_meta = await coupon_rule(e, context, credentials, fixture, customer, member, token)
        eligibility = await MF.retail_eligibility(e, context, credentials, fixture, member, {"item_id": items[0]["id"]}, rule, token)
        require(eligibility["decision"]["actor_id"] != one(e, "flow_cases", eligibility["case_id"])["created_by"], "新券商品资格未独立复核")
        paid = await paid_coupon(e, context, credentials, fixture, customer, member, rule, account, token, eligibility)
        retail_id, retail_created = await retail_create(e, context, credentials, fixture, customer, member, items, work)
        retail_approved = await retail_action(e, context, credentials, fixture, retail_id, "approve", items, member, token)
        retail_authorized = await retail_action(e, context, credentials, fixture, retail_id, "authorize", items, member, token)
        cp.note({"new_rule": rule_meta, "independent_eligibility": eligibility, "new_paid_coupon_host": paid,
                 "original_order": retail_created, "approval": retail_approved, "customer_revision_authorization": retail_authorized})

        cp.start("HK-064")
        prepared = await prepare(e, context, credentials, fixture, retail_id, items, location, "retail_dispatch", (-1000, -1000))
        dispatched = await retail_action(e, context, credentials, fixture, retail_id, "dispatch", items, member, token)
        await cp.passed({"retail_case_id": retail_id, "original_two_line_preparation": prepared, "actual_dispatch": dispatched,
                         "stocks": [MAT.item_stock(e, i["id"]) for i in items]})

        cp.start("HK-062")
        installed = await retail_action(e, context, credentials, fixture, retail_id, "install", items, member, token)
        accepted = await retail_action(e, context, credentials, fixture, retail_id, "accept", items, member, token)
        cp.note({"technician_actual_installation": installed, "customer_actual_acceptance": accepted})

        cp.start("HK-082")
        plan = await mixed_plan(e, context, credentials, fixture, retail_id, member, paid["wallet"], items, token)
        captures = await mixed_capture(e, context, credentials, fixture, retail_id, member, paid["wallet"], plan, token)
        retail_payments = []
        for ordinal, amount, remaining in ((1, 2000, 3000), (2, 3000, 0)):
            fact = await retail_cash(e, context, credentials, fixture, retail_id, member, account, plan, amount, remaining, token, ordinal)
            retail_payments.append(fact)
            cp.note({"actual_cash_ordinal": ordinal, "fact": fact})
        _, view = await retail_read(e, context, credentials, fixture, "finance", retail_id)
        totals = view["totals"]
        final = one(e, "flow_cases", retail_id)
        require(final["state"] == view["state"] == "completed" and not [t for t in subset(e, "flow_tasks", "case_id", retail_id) if t["status"] == "open"]
                and totals["charge_cents"] == totals["net_paid_cents"] == 6000 and totals["receivable_cents"] == totals["refund_due_cents"] == 0
                and totals["net_price_cents"] == totals["revenue_cents"] == 5900 and totals["cost_cents"] == 3000
                and totals["group_paid_cents"] == totals["group_internal_settlement_cents"] == 1000 and totals["group_recognized_cents"] == 900
                and totals["group_discount_borne_cents"] == 100 and totals["service_discount_borne_cents"] == totals["cash_collectable_cents"] == 0,
                "精品实际安装履约及三类资金未完整守恒")
        require(len(subset(e, "retail_payments", "case_id", retail_id)) == len(subset(e, "flow_payment_links", "case_id", retail_id)) == 2
                and sum(p["cash"]["amount_cents"] for p in retail_payments) == 5000 and one(e, "group_members", member)["balance_cents"] == 9200
                and one(e, "group_members", member)["reserved_cents"] == one(e, "benefit_wallets", paid["wallet"]["id"])["balance_units"]
                == one(e, "benefit_wallets", paid["wallet"]["id"])["reserved_units"] == 0, "终态现金不能包含发行款或权益往来")
        require(not subset(e, "membership_points_changes", "case_id", retail_id), "无期会规则不得虚构消费奖积分")
        await cp.passed({"new_coupon_rule": rule, "new_eligibility": eligibility, "actual_new_coupon_purchase": paid, "funding_plan": plan,
                         "actual_principal_coupon_captures": captures, "actual_cash_payments": retail_payments, "final_api": view,
                         "final_member": one(e, "group_members", member), "final_wallet": one(e, "benefit_wallets", paid["wallet"]["id"])})
        cp.start("HK-062")
        await cp.passed({"original_order": retail_created, "independent_quote_approval": retail_approved, "customer_current_revision": retail_authorized,
                         "actual_dispatch": dispatched, "technician_actual_install": installed, "customer_accept": accepted,
                         "settlement": {"plan_id": plan["plan"]["id"], "totals": totals, "cash_ids": [p["cash"]["id"] for p in retail_payments]},
                         "final_case": MF.json_row(final, "data"), "unmeasured_quality_not_fabricated": True})
        stocks = [MAT.item_stock(e, i["id"]) for i in items]
        require([(s["item"]["quantity_milli"], s["item"]["inventory_value_cents"]) for s in stocks] == [(2000, 2000), (1000, 2000)], "最终两件精品库存量值错误")
        for item, quantity, value in ((items[0], 2000, 2000), (items[1], 1000, 2000)):
            await MAT.stock_page(e, context, credentials, fixture, "finance", item["id"], quantity=quantity, value=value)
        plan_ids = {t["id"] for t in plan["tenders"]}
        unit_ids = {u["id"] for t in plan["tenders"] for u in subset(e, "retail_group_units", "tender_id", t["id"])}
        source = {"store_id": 1, "customer_id": customer["id"], "member_id": member, "account_id": account["id"], "supplier_id": supplier["id"],
            "category_id": created_items["category"]["row"]["id"], "brand_id": brand["id"], "item_ids": [i["id"] for i in items],
            "profile_ids": [r["profile"]["id"] for r in created_items["items"]], "warehouse_id": warehouse["id"], "location_id": location["id"],
            "enrollment_ids": [s["enrollment"]["id"] for s in stocks], "purchase_case_id": purchase_id,
            "purchase_line_ids": [r["id"] for r in subset(e, "procurement_lines", "case_id", purchase_id)],
            "procurement_receipt_ids": [r["id"] for r in subset(e, "procurement_receipts", "case_id", purchase_id)],
            "zero_activation_case_ids": [r["activation"]["case_id"] for r in created_items["items"]],
            "warehouse_allocation_ids": [a["id"] for k in (purchase_id, retail_id) for a in subset(e, "warehouse_allocations", "case_id", k)],
            "purchase_payment_ids": [p["payment"]["id"] for p in payments], "purchase_cash_ids": [p["cash"]["id"] for p in payments],
            "supplier_return_id": returned["return"]["id"], "supplier_return_posting_id": returned["posting"]["id"],
            "supplier_return_line_ids": [r["id"] for r in subset(e, "procurement_return_lines", "return_id", returned["return"]["id"])],
            "supplier_return_receipt_id": returned["posting"]["receipt_id"], "supplier_return_valuation_id": returned["valuation"]["id"],
            "supplier_refund_original_payment_id": payments[0]["payment"]["id"],
            "supplier_refund_payment_id": returned["cash"]["payment"]["id"], "supplier_refund_cash_id": returned["cash"]["cash"]["id"],
            "work_item_id": work["id"], "work_code": work["code"], "retail_case_id": retail_id,
            "retail_line_ids": [r["id"] for r in subset(e, "retail_lines", "case_id", retail_id)],
            "retail_dispatch_ids": [r["id"] for r in subset(e, "retail_dispatches", "case_id", retail_id)],
            "installation_event_id": installed["event"]["event_id"], "accept_event_id": accepted["event"]["event_id"],
            "coupon_rule_id": rule["id"], "coupon_rule_version": rule["rule_version"], "eligibility_case_id": eligibility["case_id"],
            "eligibility_id": eligibility["eligibility"]["id"], "eligibility_scope_id": eligibility["scope"]["id"], "eligibility_decision_id": eligibility["decision"]["id"],
            "membership_issue_case_id": paid["case_id"], "coupon_wallet_id": paid["wallet"]["id"], "coupon_purchase_entry_id": paid["purchase_entry"]["id"],
            "coupon_issuance_cash_id": paid["cash"]["id"], "coupon_binding_id": paid["binding"]["id"],
            "retail_group_plan_id": plan["plan"]["id"], "tender_ids": sorted(plan_ids), "unit_ids": sorted(unit_ids),
            "allocation_ids": [r["id"] for u in unit_ids for r in subset(e, "retail_group_allocations", "unit_id", u)],
            "retail_group_reservation_ids": [r["id"] for t in plan_ids for r in subset(e, "retail_group_reservations", "tender_id", t)],
            "retail_group_capture_ids": [r["id"] for t in plan_ids for r in subset(e, "retail_group_captures", "tender_id", t)],
            "group_entry_ids": [r["id"] for r in subset(e, "group_entries", "case_id", retail_id)],
            "benefit_capture_entry_ids": [r["id"] for r in subset(e, "benefit_entries", "case_id", retail_id)],
            "group_payment_link_ids": [r["id"] for r in subset(e, "group_payment_links", "case_id", retail_id)],
            "benefit_payment_link_ids": [r["id"] for r in subset(e, "benefit_payment_links", "case_id", retail_id)],
            "principal_reservation_ids": [r["id"] for r in subset(e, "group_reservations", "case_id", retail_id)],
            "coupon_reservation_ids": [r["id"] for r in subset(e, "benefit_reservations", "case_id", retail_id)],
            "group_settlement_ids": [s["id"] for r in subset(e, "group_entries", "case_id", retail_id) for s in subset(e, "group_settlement_entries", "entry_id", r["id"])],
            "benefit_settlement_ids": [s["id"] for r in (paid["purchase_entry"], *subset(e, "benefit_entries", "case_id", retail_id)) for s in subset(e, "benefit_settlements", "entry_id", r["id"])],
            "retail_payment_ids": [p["retail_payment"]["id"] for p in retail_payments], "retail_payment_link_ids": [p["payment_link"]["id"] for p in retail_payments],
            "retail_cash_ids": [p["cash"]["id"] for p in retail_payments], "cash_allocation_ids": [r["id"] for p in retail_payments for r in p["cash_allocations"]],
            "stock_move_ids": [r["id"] for s in stocks for r in s["stock_moves"]], "warehouse_entry_ids": [r["id"] for s in stocks for r in s["entries"]],
            "current_member_balance_cents": 9200, "retail_totals": totals, "synthetic_only": True, "business_accepted": False,
            "human_acceptance": "pending", "full_193_business_acceptance": False}
        cp.finish(source)
    except BaseException as error:
        cp.failed(str(error))
        raise


BOUTIQUE_SCENARIOS = ((SCENARIO, boutique_business, 1500),)
