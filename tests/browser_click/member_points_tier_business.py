"""Unregistered original membership tier, earned points and direct coupon candidate.

Only native employee forms write. All database reads are SELECT in the external
same-run mirror; no bundle gift, old null claim or fixture result earns a check.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import require
from sales_order_business import fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import checkbox, live_choice, select_value, rejected_submit, response_meta
from finance_business import submit, original_form, get_match
from membership_business import group_receipt
from member_followon_business import (read_as, responsible, upload, choose_file,
                                      submit_created, prepare_retail, flow_receipt)

SCENARIO = "member-points-tier-hk121-122-188-120-119-131"
MEMBERSHIP = "membership-hk117-128-118-089-094"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
MASTERS = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
MEM = "/api/membership"
PRICE = "/api/member-pricing"
BENEFIT = "/api/group/benefits"
RETAIL = "/api/retail"
REQUIREMENTS = (("HK-121", "会员级别调整"), ("HK-122", "会员续会"),
                ("HK-188", "会员级别"), ("HK-120", "会员积分调整"),
                ("HK-119", "会员积分兑换"), ("HK-131", "消费券赠送"))
VERSION = {"version", "updated_at"}
CASE = VERSION | {"data", "state", "cost_cents", "completed_date"}
TASK = VERSION | {"status", "done_by", "done_at"}
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "group_members",
    "group_receipts", "group_events", "membership_rules", "membership_orders",
    "membership_events", "membership_periods", "membership_period_voids", "membership_fees",
    "membership_fee_refund_bases", "membership_points_claims", "membership_points_changes",
    "benefit_rules", "benefit_wallets", "benefit_entries", "member_pricing_rules",
    "member_pricing_scopes", "member_pricing_decisions", "member_pricing_snapshots",
    "member_pricing_lines", "member_pricing_authorizations", "flow_items", "flow_stock_moves",
    "flow_accounts", "cash_entries", "flow_payment_links", "flow_request_receipts",
    "retail_orders", "retail_lines", "retail_reservations", "retail_dispatches", "retail_payments",
    "warehouse_allocations", "warehouse_allocation_lines", "warehouse_balances", "warehouse_entries",
}
READ_TABLES = TABLES | {"flow_customers", "membership_cards", "master_member_tiers",
    "master_work_items", "master_warehouses", "master_locations", "warehouse_enrollments",
    "group_entries", "group_identity_links", "membership_points_debts", "membership_points_debt_payments",
    "procurement_orders", "procurement_lines", "procurement_receipts"}
ASSOCIATIONS = {"case_id", "member_id", "wallet_id", "rule_id", "item_id", "snapshot_id",
                "claim_id", "period_id", "entry_id", "allocation_id"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rows(e, table):
    require(table in READ_TABLES, "未审阅原表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY id")


def one(e, table, key):
    require(table in READ_TABLES and type(key) is int and key > 0, "缺有限原ID")
    found = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (key,))
    require(len(found) == 1, "有限原件缺失：" + table + "/" + str(key))
    return found[0]


def subset(e, table, field, key):
    require(table in READ_TABLES and field in ASSOCIATIONS and type(key) is int, "未审阅原关联")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY id", (key,))


def decoded(row, *fields):
    value = dict(row)
    for field in fields:
        value[field] = json.loads(value[field])
    require(not any(isinstance(v, bytes) for v in value.values()), "附件正文不得输出JSON")
    return value


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        source = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(source[key]["title"] == title and source[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in source[key]["acceptance_checks"]), "原需求绑定变化：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "complete": False, "passed": False,
            "scope": [k for k, _ in REQUIREMENTS], "source_contract_sha256": self.digest,
            "candidate_sha256": sha(Path(__file__).read_bytes()), "execution": "native_browser_original_forms",
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "requirements": [{"id": k, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": k + "-business", "check_id": k + "-business", "status": "not_tested", "evidence": {}}]}
                for k, title in REQUIREMENTS],
            "conditional_checks": [{"status": "not_tested", "scope": text} for text in
                ("HK133/126/127混合作业配件套餐", "原消费退回欠分追回/清偿", "过期/跨店/互斥/并发/全等级全部异常",
                 "真实模型/PostgreSQL/员工试用/生产环境及真实银行支付")],
            "conditions": {"new_fixture_results": False, "new_roles": 0, "synthetic_inputs_only": True,
                "file_scan": "structure_only_not_clamav", "centre_payment": False},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False, "human_acceptance": "pending"}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def note(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].setdefault("steps", []).append(value)
        self.save()

    async def passed(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].update(status="passed", evidence=value)
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active = None
        self.save()

    def failed(self, error):
        for row in self.report["requirements"]:
            if row["status"] == "running":
                status = "failed" if row is self.active else "partial"
                row["status"] = row["acceptance_checks"][0]["status"] = status
                row["acceptance_checks"][0]["error"] = self.e.scrub(error)
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "finite_source_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "六项未完整实际执行")
        self.report.update(complete=True, passed=True, executed_requirements=6, passed_requirements=6,
                           member_points_tier_sources=sources, report_sources=sources)
        self.save()
        self.e.observe("member_points_tier_checkpoint", {"path": str(self.path), "passed_checks": 6,
                       "full_193_business_acceptance": False, "human_acceptance": "pending"})


class Guard:
    """All tables/old rows protected; only one original action's finite deltas."""
    def __init__(self, e, label, actor, *, append, update=None, cases=(), member=None,
                 customer=None, new_kind=None, item=None, wallets=()):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = dict(append), update or {}
        self.cases, self.wallets = set(cases), set(wallets)
        self.member, self.customer, self.new_kind, self.item = member, customer, new_kind, item
        require(self.append.keys() | self.update.keys() <= TABLES, "守卫超出本批原表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "原动作改变无关表：" + str(sorted(changed)))
        added = {t: [r for r in rows(self.e, t) if r["id"] not in {x["id"] for x in old}] for t, old in self.old.items()}
        for table, new in added.items():
            count = self.append.get(table, 0)
            low, high = count if isinstance(count, tuple) else (count, count)
            require(low <= len(new) <= high, "本次追加数不符：" + table + "/" + str(len(new)))
        new_cases = added.get("flow_cases", [])
        require(not new_cases or len(new_cases) == 1 and new_cases[0]["kind"] == self.new_kind
                and new_cases[0]["flow_version"] == (1 if self.new_kind == "member_pricing_rule" else 2)
                and new_cases[0]["customer_id"] == self.customer
                and new_cases[0]["created_by"] == new_cases[0]["owner_id"] == self.actor["id"], "新原单归属/类型失配")
        cases = self.cases | {r["id"] for r in new_cases}
        wallets = self.wallets | {r["id"] for r in added.get("benefit_wallets", [])}
        cash_ids = {r["id"] for r in added.get("cash_entries", [])}
        modified = {}
        for table, old in self.old.items():
            current = {r["id"]: r for r in rows(self.e, table)}
            modified[table] = []
            for prior in old:
                key = prior["id"]
                require(key in current, "删除原旧行：" + table)
                columns = {k for k in prior if prior[k] != current[key][k]}
                require(columns <= self.update.get(table, {}).get(key, set()), "覆盖无授权原列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if table == "flow_cases" and "data" in columns:
                    before_data, now_data = json.loads(prior["data"]), json.loads(current[key]["data"])
                    require(all(now_data.get(k) == v for k, v in before_data.items()), "本批正向动作覆盖既有原data")
                if columns:
                    modified[table].append({"id": key, "columns": sorted(columns)})
            for row in added[table]:
                for field in ("store_id", "issuer_store_id"):
                    if field in row:
                        require(row[field] == 1, "新增事实跨店：" + table)
                for field in ("case_id", "source_case_id"):
                    if field in row:
                        require(row[field] in cases, "新增事实串原宿主：" + table)
                if "member_id" in row and row["member_id"] is not None:
                    require(row["member_id"] == self.member, "新增事实串会员：" + table)
                if "wallet_id" in row and row["wallet_id"] is not None:
                    require(row["wallet_id"] in wallets, "新增事实串原批次：" + table)
                if "customer_id" in row:
                    require(row["customer_id"] == self.customer, "新增事实串客户：" + table)
                if "item_id" in row:
                    require(row["item_id"] == self.item, "新增事实串物资：" + table)
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "新增事实借用身份：" + table)
                if table == "audit_logs":
                    require(row["entity_type"] == "flow" and row["entity_id"] in cases
                            or row["entity_type"] == "cash" and row["entity_id"] in cash_ids, "新增审计串实体")
        self.added = added
        result = {"label": self.label, "changed_tables": sorted(changed), "expected_counts": self.append,
                  "appended_ids": {t: [r["id"] for r in v] for t, v in added.items()}, "updated_columns": modified,
                  "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("member_points_tier_original_guard", result)
        return result


def updates(e, cases=(), *, member=None, wallet=None, account=None):
    value = {"flow_cases": {key: CASE for key in cases},
             "flow_tasks": {t["id"]: TASK for key in cases for t in subset(e, "flow_tasks", "case_id", key)}}
    if member:
        value["group_members"] = {member: VERSION}
    if wallet:
        value["benefit_wallets"] = {wallet: VERSION | {"balance_units", "reserved_units"}}
    if account:
        value["flow_accounts"] = {account: VERSION}
    return {k: v for k, v in value.items() if v}


def dependencies(e, cp):
    root = Path(e.manifest["evidence_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True
            and Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "非同轮外置合成库")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "源码快照不稳定")
    for name in ("member_points_tier_business.py", "member_followon_business.py", "membership_business.py", "material_business.py",
                 "master_data_business.py", "finance_business.py", "sales_business.py", "sales_order_business.py",
                 "vehicle_purchase_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "不属同轮脚本指纹：" + name)
    prior, material, master = [fixed_dependency(e, cp, s) for s in (MEMBERSHIP, MATERIAL, MASTERS)]
    source, primary = prior["membership_sources"], material["material_sources"]["primary"]
    customer, member, account = [one(e, t, source[k]) for t, k in
        (("flow_customers", "customer_id"), ("group_members", "member_id"), ("flow_accounts", "account_id"))]
    original, returned = one(e, "group_entries", source["topup_entry_id"]), one(e, "group_entries", source["refund_entry_id"])
    require(original["amount_cents"] == 10000 and returned["amount_cents"] == -4000
            and returned["original_id"] == original["id"] and original["cash_id"] == source["topup_cash_id"]
            and returned["cash_id"] == source["refund_cash_id"] and original["account_id"] == returned["account_id"] == account["id"], "普通前序原款事实失配")
    for entry, direction, amount in ((original, "in", 10000), (returned, "out", 4000)):
        cash = one(e, "cash_entries", entry["cash_id"])
        require(cash["direction"] == direction and cash["amount_cents"] == amount and cash["account"] == account["name"], "普通前序真实收退款失配")
    require(member["active"] == 1 and member["balance_cents"] >= 0 and member["reserved_cents"] == 0
            and one(e, "membership_cards", source["active_card_id"])["status"] == "active"
            and not subset(e, "membership_periods", "member_id", member["id"])
            and not subset(e, "membership_points_debts", "member_id", member["id"]), "没有明确初始有效会员/会期/无欠分来源")
    item, location, warehouse, enrollment = [one(e, t, primary[k]) for t, k in
        (("flow_items", "item_id"), ("master_locations", "source_location_id"), ("master_warehouses", "warehouse_id"), ("warehouse_enrollments", "enrollment_id"))]
    balance = [b for b in subset(e, "warehouse_balances", "item_id", item["id"])
               if b["location_id"] == location["id"] and b["transit_case_id"] is None]
    require(item["active"] == location["active"] == warehouse["active"] == 1 and item["quantity_milli"] >= 1000
            and len(balance) == 1 and balance[0]["quantity_milli"] >= 1000 and location["id"] in primary["location_ids"]
            and location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials"
            and enrollment["item_id"] == item["id"], "真实当前物资来源/库位不足")
    purchase = one(e, "procurement_orders", primary["purchase_order_id"])
    receipts = [one(e, "procurement_receipts", key) for key in primary["receipt_ids"]]
    require(receipts and purchase["store_id"] == 1 and one(e, "flow_cases", purchase["id"])["kind"] == "procurement", "缺当次真实采购/入库来源")
    for receipt in receipts:
        line, move = one(e, "procurement_lines", receipt["line_id"]), one(e, "flow_stock_moves", receipt["stock_move_id"])
        require(receipt["case_id"] == purchase["id"] and line["item_id"] == move["item_id"] == item["id"]
                and move["id"] in primary["stock_move_ids"] and move["quantity_milli"] == receipt["quantity_milli"]
                and move["value_cents"] == receipt["value_cents"], "物资原入库/有限采购行/StockMove不匹配")
    work = checkpoint_evidence(master, "HK-175")["row"]
    require(one(e, "master_work_items", work["id"])["active"] == 1, "同轮主档前序失效")
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    fixture["admin_key"] = "admin"
    for role in ("service", "manager", "finance", "sales", "inventory"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=1 AND role=?", (actor["id"], role))) == 1, "当前店岗位不真实：" + role)
    require(fixture["store_id"] == customer["store_id"] == account["store_id"] == item["store_id"] == warehouse["store_id"] == location["store_id"] == 1
            and customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"] and account["active"] == 1
            and not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=1"), "前序跨店/本人/原账户或主体策略不满足")
    cp.report["source_preconditions"] = {"ordinary_membership": source, "primary": primary, "customer": customer,
        "member": member, "account": account, "work": work, "current_source_balance": balance[0], "original_purchase": purchase,
        "original_receipts": receipts, "provenance_sha256": sha((root / "provenance.json").read_bytes())}
    cp.save()
    return fixture, customer, member["id"], account, primary


async def visible_action(e, selector, label):
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        summary = button.locator("xpath=ancestor::details[1]/summary")
        await expect(summary).to_have_count(1)
        e.action("click", "展开本页原办理组")
        await summary.click()
    await expect(button).to_be_visible()
    await expect(button).to_be_enabled()
    await e.click(selector, label)


def month_end(start, months):
    ordinal = start.year * 12 + start.month - 1 + months
    year, month = divmod(ordinal, 12)
    return date(year, month + 1, min(start.day, monthrange(year, month + 1)[1])) - timedelta(days=1)


async def publish_benefit(e, context, credentials, fixture, customer, member, token, kind):
    actor, _ = await read_as(e, context, credentials, fixture, "manager", "benefits/" + str(customer["id"]), BENEFIT + "/members", "集团权益")
    await visible_action(e, '#main [data-act="benefit-rule"]', "发布本次独立积分或兑换券规则")
    await expect(e.page.locator("#modal-title")).to_have_text("发布权益规则新版本")
    values = {"code": "PT-" + kind + "-" + token, "name": "本轮消费" + kind + token,
        "kind": kind, "allowed_store_ids": [1], "credit_cents_per_unit": 1 if kind == "points" else 500,
        "sale_cents_per_unit": 0, "settlement_cents_per_unit": 0, "exchange_points_per_unit": 0 if kind == "points" else 2,
        "discount_bearer": "service_store", "validity_days": 30, "refund_policy": "none", "service_code": ""}
    for name, value in (("code", values["code"]), ("name", values["name"]), ("stores", "1"),
                        ("credit", fen_text(values["credit_cents_per_unit"])), ("sale", "0"), ("settlement", "0"),
                        ("exchange_points_per_unit", str(values["exchange_points_per_unit"])), ("validity_days", "30")):
        await e.fill(f'#modal [name="{name}"]', value, "填写原冻结权益字段：" + name)
    for name in ("kind", "discount_bearer", "refund_policy"):
        await select_value(e, f'#modal [name="{name}"]', values[name], "选择原权益用途：" + name)
    await expect(e.page.locator('#modal [name="service_code"]')).to_have_value("")
    guard = Guard(e, "new_" + kind + "_benefit_rule", actor, append={"benefit_rules": 1, "group_events": 1, "group_receipts": 1})
    body, request, _, native = await submit(e, BENEFIT + "/rules", BENEFIT + "/rules", status=201)
    rule = decoded(one(e, "benefit_rules", body["id"]), "allowed_store_ids")
    require(request == {"request_id": request["request_id"], "values": values}
            and all(rule[k] == v for k, v in values.items()) and rule["rule_version"] == 1
            and rule["created_by"] == actor["id"], "独立权益规则原输入失配")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "benefit_rule", values, body))
    require(guard.added["group_events"][0]["action"] == "benefit_rule"
            and json.loads(guard.added["group_events"][0]["detail"]) == {"rule_id": rule["id"]}, "原权益规则事件不符")
    return rule, native


async def membership_rule(e, context, credentials, fixture, points, token, letter):
    actor, _ = await read_as(e, context, credentials, fixture, "admin", "membership-rules", MEM + "/rules", "集团会员规则")
    await visible_action(e, '#main [data-act="membership-rule"]', "管理员发布明确本店会期规则")
    await expect(e.page.locator("#modal-title")).to_have_text("发布集团会员规则")
    values = {"code": "PT-TIER-" + letter + "-" + token, "name": "本轮等级" + letter + token,
        "enabled": True, "allowed_store_ids": [1], "validity_months": 1, "fee_cents": 300,
        "fee_owner": "collecting_store", "refund_policy": "before_start", "points_enabled": True,
        "points_numerator": 1, "points_denominator_fen": 100, "points_benefit_rule_id": points["id"]}
    for name, value in (("code", values["code"]), ("name", values["name"]), ("validity_months", "1"),
                        ("fee", "3.00"), ("points_numerator", "1"), ("points_denominator_fen", "100")):
        await e.fill(f'#modal [name="{name}"]', value, "填写原自然月和整数积分比例：" + name)
    await checkbox(e, '#modal [name="store_1"]', True, "明确只适用本店")
    for store in e.manifest["stores"]:
        key = store["id"]
        if key != 1 and await e.page.locator(f'#modal [name="store_{key}"]').count():
            await checkbox(e, f'#modal [name="store_{key}"]', False, "不扩大其他门店")
    await checkbox(e, '#modal [name="enabled"]', True, "明确启用新申请")
    await checkbox(e, '#modal [name="points_enabled"]', True, "明确启用本轮以后真实消费积分")
    await select_value(e, '#modal [name="refund_policy"]', "未生效期间整笔原款退款", "明确原未开始收费退款政策")
    await select_value(e, '#modal [name="points_rule"]', f'{points["id"]} · {points["name"]} · 版本1', "关联独立冻结积分规则")
    guard = Guard(e, "membership_rule_" + letter, actor, append={"membership_rules": 1, "group_receipts": 1})
    body, request, shown, native = await submit(e, MEM + "/rules", MEM + "/rules", status=201)
    rule = decoded(one(e, "membership_rules", body["id"]), "allowed_store_ids")
    require(request == {"request_id": request["request_id"], "values": values}
            and all(rule[k] == v for k, v in values.items()) and rule["rule_version"] == 1
            and rule["created_by"] == actor["id"] and any(r["id"] == rule["id"] for r in shown["items"]), "会期规则发布原值不符")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "membership_rule", values, body))
    await expect(e.page.locator("#main")).to_contain_text(values["name"])
    return rule, native


async def member_view(e, context, credentials, fixture, customer, member, role="service", *, period=None):
    actor, view = await read_as(e, context, credentials, fixture, role, "membership/" + str(customer["id"]), MEM + "/members", "会员卡与续会")
    require(view["customer"]["id"] == customer["id"] and view["member"]["id"] == member
            and view["points_debt_units"] == 0, "原会员/客户/欠分不匹配")
    if period:
        found = next((p for p in view["periods"] if p["id"] == period["id"]), None)
        require(view["active_period_id"] == period["id"] and found and found["rule"]["id"] == period["rule_id"]
                and found["starts_on"] == period["starts_on"] and found["ends_on"] == period["ends_on"], "原有效会期API/DB不匹配")
        await expect(e.page.locator("#main")).to_contain_text(one(e, "membership_rules", period["rule_id"])["name"])
    return actor, view


async def create_member_order(e, context, credentials, fixture, customer, member, key, values, token, *, root_case=None):
    role = "manager" if key in {"adjust", "grant"} else "service"
    actor, _ = await member_view(e, context, credentials, fixture, customer, member, role)
    purposes = {"adjust": "points_adjust", "exchange": "points_adjust", "grant": "benefit_issue"}
    purpose = purposes.get(key, key)
    identifier = values.get("period_id") if key == "renew_refund" else None
    await original_form(e, "membership-create", key, {"points_adjust": "积分办理", "benefit_issue": "权益发行",
        "tier_change": "会员等级调整", "renew": "会员续会", "renew_refund": "未生效续会退款"}[purpose], identifier=identifier)
    if key in {"tier_change", "renew", "grant", "exchange"}:
        rule_key = values["target_rule_id"] if key == "exchange" else values["rule_id"]
        rule = one(e, "benefit_rules" if key in {"grant", "exchange"} else "membership_rules", rule_key)
        await select_value(e, '#modal [name="rule"]', f'{rule["id"]} · {rule["name"]} · 版本{rule["rule_version"]}', "选择本次原规则版本")
    if "wallet_id" in values:
        wallet = one(e, "benefit_wallets", values["wallet_id"])
        rule = one(e, "benefit_rules", wallet["rule_id"])
        label = f'{wallet["id"]} · {rule["name"]} · 可用{wallet["balance_units"] - wallet["reserved_units"]}'
        await select_value(e, '#modal [name="wallet"]', label, "明确本轮消费赚取积分批次")
    if "units" in values:
        await e.fill('#modal [name="units"]', str(values["units"]), "填写真实整数积分或券份数")
    reason = "本轮原" + key + "明确来源及客户申请" + token
    await e.fill('#modal [name="reason"]', reason, "输入本次会员办理依据")
    permitted = {"group_members": {member: VERSION}}
    if root_case:
        permitted["flow_cases"] = {root_case: VERSION}
    guard = Guard(e, "membership_create_" + key, actor,
        append={"flow_cases": 1, "flow_tasks": 1, "membership_orders": 1, "membership_events": 1,
                "flow_events": 1, "audit_logs": 1, "group_receipts": 1}, update=permitted,
        cases={root_case} if root_case else (), member=member, customer=customer["id"], new_kind="membership")
    body, request, shown, native = await submit_created(e, MEM + "/orders", MEM + "/orders/", status=201, body_key=("case", "id"))
    expected = {"customer_id": customer["id"], "purpose": purpose, "values": values, "reason": reason}
    require(request == {"request_id": request["request_id"], **expected} and shown["order"]["purpose"] == purpose
            and shown["order"]["values"] == values and shown["case"]["id"] == body["case"]["id"], "会员原申请内容不符")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "membership_create", expected, body))
    row = one(e, "flow_cases", body["case"]["id"])
    return row["id"], native


async def member_action(e, context, credentials, fixture, customer, member, key, action, role, token,
                        *, account=None, wallet=None, root_case=None):
    handoff = await responsible(e, context, credentials, fixture, key,
        "membership_review" if action == "approve" else "membership_execute", role, member)
    actor, view = await read_as(e, context, credentials, fixture, role, "membership-order/" + str(key), MEM + "/orders/" + str(key), "会员业务办理")
    proof = await upload(e, actor, key, member, MEM + "/orders/" + str(key), "evidence", "points-tier-" + action + "-" + str(key), token)
    case, order, current_member = one(e, "flow_cases", key), subset(e, "membership_orders", "case_id", key)[0], one(e, "group_members", member)
    source_values = json.loads(order["values"])
    await original_form(e, "membership-action", action, "独立复核批准" if action == "approve" else "确认实际办理")
    await choose_file(e, proof)
    reason = "本人核对原会员" + action + "实际事实" + token
    await e.fill('#modal [name="reason"]', reason, "填写本次员工核对事实")
    values = {"reason": reason, "evidence_id": proof["file"]["id"]}
    if account:
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        values.update(account_id=account["id"], reference="PT-FEE-" + str(key) + "-" + token)
        await e.fill('#modal [name="reference"]', values["reference"], "记录本次实际原收退款流水")
    if wallet:
        values["wallet_version"] = one(e, "benefit_wallets", wallet)["version"]
    permitted = updates(e, [key], member=member, wallet=wallet, account=account["id"] if account else None)
    permitted["membership_orders"] = {order["id"]: VERSION | {"status", "approved_by"}}
    if root_case:
        permitted["flow_cases"][root_case] = VERSION
    append = {"flow_events": 1, "audit_logs": 1, "group_receipts": 1, "membership_events": 1}
    if action == "approve":
        append["flow_tasks"] = 1
    elif order["purpose"] in {"tier_change", "renew"}:
        append["membership_periods"] = 1
        if account:
            append.update(membership_fees=1, cash_entries=1)
    elif order["purpose"] == "renew_refund":
        append.update(flow_events=2, audit_logs=2, membership_events=2, membership_fees=1,
                      cash_entries=1, membership_period_voids=1, membership_fee_refund_bases=1)
    else:
        delegated = source_values["action"]
        append.update(flow_events=2, audit_logs=2, group_events=1)
        append["benefit_entries"] = 2 if delegated == "exchange" else 1
        if delegated in {"grant", "exchange"}:
            append["benefit_wallets"] = 1
    guard = Guard(e, "membership_" + action + "_" + str(key), actor, append=append, update=permitted,
                  cases={key, root_case} if root_case else {key}, member=member, customer=customer["id"], wallets={wallet} if wallet else ())
    body, request, shown, native = await submit(e, MEM + f"/orders/{key}/actions/{action}", MEM + "/orders/" + str(key))
    expected = {"version": order["version"], "case_version": case["version"], "member_version": current_member["version"], "values": values}
    require(request == {"request_id": request["request_id"], **expected} and shown["order"]["status"] == ("approved" if action == "approve" else "completed")
            and shown["case"]["version"] == one(e, "flow_cases", key)["version"], "会员原Task/多版本/结果不符")
    protection = guard.finish()
    if action == "execute" and order["purpose"] in {"benefit_issue", "points_adjust"}:
        delegated = source_values["action"]
        payload = {k: v for k, v in source_values.items() if k != "action"} | values | {"case_id": key, "case_version": case["version"]}
        receipt = group_receipt(e, request, actor, f"benefit:{member}:{delegated}", {"version": current_member["version"], "values": payload}, body["result"])
        require([r["action"] for r in guard.added["flow_events"]] == ["membership_" + delegated, "benefit_" + delegated], "原宿主和权益事件不完整")
        if delegated in {"grant", "exchange"}:
            new_wallet = guard.added["benefit_wallets"][0]
            rule_key = source_values["target_rule_id"] if delegated == "exchange" else source_values["rule_id"]
            rule = one(e, "benefit_rules", rule_key)
            issued = date.fromisoformat(one(e, "flow_cases", key)["completed_date"])
            require(new_wallet["rule_id"] == rule_key and new_wallet["source_case_id"] == key and new_wallet["reserved_units"] == 0
                    and new_wallet["expires_on"] == (issued + timedelta(days=rule["validity_days"])).isoformat(), "原独立权益批次/期限未按冻结规则发行")
    else:
        receipt = group_receipt(e, request, actor, f"membership:{key}:{action}", expected, body)
    require(all(r["case_id"] == key and r["actor_id"] == actor["id"] for r in guard.added["flow_events"] + guard.added["membership_events"]), "会员办理事件串单/身份")
    native.update(guard=protection, receipt=receipt, proof=proof, handoff=handoff,
                  facts={t: v for t, v in guard.added.items() if t not in {"group_receipts", "audit_logs"}})
    return native


async def price_rule(e, context, credentials, fixture, member, primary, membership, token, *, enabled=True):
    actor, _ = await read_as(e, context, credentials, fixture, "manager", "member-pricing", PRICE + "/rules", "会员价格规则")
    await visible_action(e, '#main [data-act="member-price-new"]', "主管提出本店明确价格版本")
    await expect(e.page.locator("#modal-title")).to_have_text("提出本店会员价格规则")
    starts = await e.page.locator('#modal [name="starts_on"]').input_value()
    ends = (date.fromisoformat(starts) + timedelta(days=60)).isoformat()
    values = {"code": "PT-PRICE-" + token, "name": "本轮等级九折" + token + ("启用" if enabled else "停用"),
        "enabled": enabled, "membership_rule_id": membership["id"], "reference_tier_id": None, "reference_tier_version": None,
        "starts_on": starts, "ends_on": ends, "stack_mode": "member_then_benefits",
        "scopes": [{"business_kind": "retail", "component": "goods", "source_id": primary["item_id"],
                    "basis_points": 9000, "bundle_rule_id": None}], "reason": "本店明确只对本轮原商品九折，使用当前等级"}
    for name in ("code", "name", "ends_on", "reason"):
        await e.fill(f'#modal [name="{name}"]', values[name], "填写本店价格原字段：" + name)
    for name, value in (("membership_rule", membership["id"]), ("tier", ""), ("enabled", "true" if enabled else "false"),
                        ("stack_mode", values["stack_mode"]), ("component", "retail:goods"), ("source", primary["item_id"]), ("bundle", "")):
        await select_value(e, f'#modal [name="{name}"]', value, "明确原等级/范围/价格状态：" + name)
    await e.fill('#modal [name="basis_points"]', "9000", "明确整数9000基点")
    guard = Guard(e, "member_price_create_" + str(enabled), actor,
        append={"flow_cases": 1, "flow_tasks": 1, "flow_events": 1, "audit_logs": 1, "group_receipts": 1,
                "member_pricing_rules": 1, "member_pricing_scopes": 1}, new_kind="member_pricing_rule", member=member)
    body, request, shown, native = await submit_created(e, PRICE + "/rules", PRICE + "/rules/", status=201, body_key=("id",))
    require(request == {"request_id": request["request_id"], **values} and shown["id"] == body["id"]
            and shown["state"] == "draft" and shown["enabled"] is enabled, "本店价格原申请字段不符")
    parsed = {**values, "scopes": [{**s, "allow_contract_pricing": False} for s in values["scopes"]]}
    rule = decoded(one(e, "member_pricing_rules", body["id"]), "membership_snapshot", "reference_tier_snapshot")
    scopes = [decoded(s, "source_snapshot", "bundle_snapshot") for s in subset(e, "member_pricing_scopes", "rule_id", rule["id"])]
    require(len(scopes) == 1 and scopes[0]["source_id"] == primary["item_id"] and scopes[0]["basis_points"] == 9000
            and scopes[0]["source_snapshot"]["version"] == one(e, "flow_items", primary["item_id"])["version"]
            and rule["membership_snapshot"]["id"] == membership["id"] and rule["actor_id"] == actor["id"], "价格范围/源版本/会期冻结不符")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "member_price_create", parsed, body), rule=rule, scopes=scopes)
    return rule, native


async def price_action(e, context, credentials, fixture, member, rule, action, role, token, *, reject_self=False):
    handoff = None if reject_self else await responsible(e, context, credentials, fixture, rule["case_id"],
        "member_price_submit" if action == "submit" else "member_price_approve", role, member)
    actor, view = await read_as(e, context, credentials, fixture, role, "member-pricing/" + str(rule["id"]), PRICE + "/rules/" + str(rule["id"]), "会员价格规则")
    proof = await upload(e, actor, rule["case_id"], member, PRICE + "/rules/" + str(rule["id"]), "evidence",
                         "price-" + action + "-" + str(rule["id"]) + ("-self" if reject_self else ""), token)
    case = one(e, "flow_cases", rule["case_id"])
    await original_form(e, "member-price-action", action, "提交规则依据" if action == "submit" else "独立批准本版规则")
    reason = "本人核对当前等级、原商品与九折范围，禁止申请人自批"
    await e.fill('#modal [name="reason"]', reason, "填写本次独立规则依据")
    await choose_file(e, proof)
    if reject_self:
        path = PRICE + f'/rules/{rule["id"]}/actions/approve'
        message = "申请人不能自批会员价格，管理员也不例外"
        before = e.business_snapshot("before_member_price_self_refusal")
        old = e.db.rows("SELECT * FROM escalation_refusals ORDER BY id")
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "原申请人实际尝试自批一次，核对服务器规则拒绝")
        response = await pending.value
        body = await response.json()
        require(response.status == 403 and body.get("detail") == message, "自批拒绝须保留原服务器完整文案")
        refusal = body.get("refusal")
        require(isinstance(refusal, dict) and type(refusal.get("id")) is int and refusal["id"] > 0
                and refusal == {"id": refusal["id"], "category": "rule", "can_escalate": False},
                "业务规则拒绝不能改成权限不足或可评审")
        metadata, request = await response_meta(e, response, body)
        require(request == {"request_id": request["request_id"], "version": case["version"],
                "values": {"reason": reason, "evidence_id": proof["file"]["id"]}}
                and actor["id"] == rule["actor_id"] and actor["role"] == "manager",
                "自批拒绝须由本次申请人按当前原Case版本提交")
        after = e.business_snapshot("after_member_price_self_refusal")
        changed = {t for t in before["tables"].keys() | after["tables"].keys()
                   if before["tables"].get(t) != after["tables"].get(t)}
        require(changed == {"escalation_refusals"}, "自批拒绝仅允许追加一条真实拒绝，其余业务全表不变")
        current = e.db.rows("SELECT * FROM escalation_refusals ORDER BY id")
        old_by_id, current_by_id = {r["id"]: r for r in old}, {r["id"]: r for r in current}
        require(all(current_by_id.get(key) == row for key, row in old_by_id.items()), "自批拒绝不可覆盖或删除任何旧拒绝")
        added = [r for r in current if r["id"] not in old_by_id]
        require(len(added) == 1, "本次单次自批须恰有一条原拒绝")
        recorded = added[0]
        require(recorded["id"] == refusal["id"] and recorded["user_id"] == actor["id"]
                and recorded["store_id"] == fixture["store_id"] == 1 and recorded["role"] == actor["role"]
                and recorded["method"] == "POST" and recorded["path"] == path
                and recorded["status_code"] == 403 and recorded["message"] == message
                and recorded["category"] == "rule" and recorded["source"] == "page"
                and recorded["consumed_at"] is None and recorded["consumed_by_id"] is None
                and bool(recorded["created_at"]), "真实拒绝的本人、门店、原路径或未消费状态不符")
        await expect(e.page.locator("#modal .formerror")).to_contain_text(message)
        metadata.update(detail=message, refusal=refusal, refusal_row=recorded,
                        all_old_refusals_unchanged=True, all_other_business_tables_unchanged=True)
        e.observe("member_price_self_refusal", metadata)
        await e.snapshot("member-price-self-rule-refusal")
        await expect(e.page.locator("#modal form")).not_to_have_attribute("aria-busy", "true")
        await e.click('#modal .modalhead [data-act="close"]', "关闭被拒绝的原自批表单")
        await expect(e.page.locator("#modal .wfx-discard")).to_be_visible()
        await expect(e.page.locator("#modal .wfx-discard strong")).to_have_text("还有未保存的填写内容")
        await e.click('#modal [data-wfx-discard]', "明确放弃自批表单的未保存填写")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        e.business_unchanged(after, "after_member_price_self_refusal_discard")
        require(e.db.rows("SELECT * FROM escalation_refusals ORDER BY id") == current, "放弃填写不能消费或改写原拒绝")
        metadata.update(explicit_discard=True, discard_business_unchanged=True)
        e.observe("member_price_self_refusal_discard", metadata)
        return {"refusal": metadata, "proof": proof, "actor_id": actor["id"]}
    guard = Guard(e, "member_price_" + action + "_" + str(rule["id"]), actor,
        append={"flow_events": 1, "audit_logs": 1, "group_receipts": 1, "member_pricing_decisions": 1,
                **({"flow_tasks": 1} if action == "submit" else {})}, update=updates(e, [rule["case_id"]]), cases={rule["case_id"]})
    body, request, shown, native = await submit(e, PRICE + f'/rules/{rule["id"]}/actions/{action}', PRICE + "/rules/" + str(rule["id"]))
    values = {"reason": reason, "evidence_id": proof["file"]["id"]}
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}
            and shown["state"] == ("approval" if action == "submit" else "completed"), "会员价格原Case版本/独立结果不符")
    protection = guard.finish()
    decision = guard.added["member_pricing_decisions"][0]
    require(decision["rule_id"] == rule["id"] and decision["decision"] == ("submitted" if action == "submit" else "approved")
            and decision["evidence_id"] == proof["file"]["id"]
            and (action == "submit" or actor["id"] != rule["actor_id"]), "原规则决策与独立身份失配")
    payload = {"rule_id": rule["id"], "version": case["version"], "values": values}
    native.update(guard=protection, proof=proof, handoff=handoff, decision=decision,
                  receipt=group_receipt(e, request, actor, "member_price_" + action, payload, body))
    return native


async def retail_view(e, context, credentials, fixture, role, key):
    case = one(e, "flow_cases", key)
    actor, view = await read_as(e, context, credentials, fixture, role, "retail/" + str(key), RETAIL + "/orders/" + str(key), "精品销售 · " + case["number"])
    require(view["id"] == key and view["version"] == case["version"] and view["state"] == case["state"], "原精品页面/DB版本不符")
    return actor, view


async def new_retail_form(e, context, credentials, fixture, customer):
    actor, _ = await read_as(e, context, credentials, fixture, "sales", "retail", RETAIL + "/orders", "精品销售与退货")
    await visible_action(e, '#main [data-act="retail-new"]', "本人客户原商品按明确会员价购买")
    await expect(e.page.locator("#modal-title")).to_have_text("新建精品订单")
    label = await e.page.locator(f'#modal [name="customer"] option[value="{customer["id"]}"]').text_content()
    async with e.page.expect_response(lambda r: get_match(r, PRICE + "/candidates")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        await live_choice(e, "customer", customer["name"], label, expected_value=customer["id"])
    response = await pending.value
    require(response.status == 200, "本客户原会员价格候选未核对")
    candidates = await response.json()
    await expect(e.page.locator('#modal [data-member-price-field]')).not_to_have_attribute("data-loading", "true")
    await expect(e.page.locator('#modal [data-related-status]')).not_to_contain_text("正在")
    return actor, candidates


async def create_retail(e, context, credentials, fixture, customer, member, primary, rule):
    actor, candidates = await new_retail_form(e, context, credentials, fixture, customer)
    require(any(r["id"] == rule["id"] and r["rule_version"] == rule["rule_version"] for r in candidates["items"]), "原有效等级没有当前批准价格候选")
    item = one(e, "flow_items", primary["item_id"])
    label = await e.page.locator(f'#modal [name="item"] option[value="{item["id"]}"]').text_content()
    await live_choice(e, "item", item["sku"], label, expected_value=item["id"])
    for name, value in (("quantity", "1.000"), ("price", "10.00"), ("install_price", "0.00"), ("discount", "0.00")):
        await e.fill(f'#modal [name="{name}"]', value, "填写本次明确商品整数报价：" + name)
    await expect(e.page.locator('#modal [name="work"]')).to_have_value("")
    await expect(e.page.locator('#modal [name="related"]')).to_have_value("")
    await select_value(e, '#modal [name="member_pricing_rule"]', rule["id"], "员工明确选本版会员九折价")
    guard = Guard(e, "member_price_retail_create", actor,
        append={"flow_cases": 1, "flow_tasks": 1, "flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1,
                "retail_orders": 1, "retail_lines": 1, "retail_reservations": 1, "member_pricing_snapshots": 1, "member_pricing_lines": 2},
        update={"flow_items": {item["id"]: VERSION}, "group_members": {member: VERSION}},
        new_kind="retail", customer=customer["id"], member=member, item=item["id"])
    body, request, shown, native = await submit_created(e, RETAIL + "/orders", RETAIL + "/orders/", status=201, body_key=("id",))
    expected = {"customer_id": customer["id"], "related_repair_id": None, "discount_cents": 0,
        "member_pricing": {"rule_id": rule["id"], "rule_version": rule["rule_version"]},
        "lines": [{"item_id": item["id"], "quantity_milli": 1000, "unit_price_cents": 1000,
                   "work_item_id": None, "installation_unit_price_cents": 0}]}
    require(request == {"request_id": request["request_id"], **expected} and shown["amount_cents"] == 900
            and shown["state"] == "approval" and shown["revision"] == 1, "本轮真实九折原单输入/金额失配")
    key = body["id"]
    native.update(guard=guard.finish(), receipt=flow_receipt(e, request, actor, key, "retail_create", expected))
    snapshot = decoded(guard.added["member_pricing_snapshots"][0], "contract")
    goods = next(r for r in guard.added["member_pricing_lines"] if r["component"] == "goods")
    require(snapshot["rule_id"] == rule["id"] and snapshot["customer_id"] == customer["id"] and snapshot["member_id"] == member
            and snapshot["contract"]["rule_version"] == rule["rule_version"]
            and goods["basis_cents"] == 1000 and goods["net_cents"] == 900 and goods["member_discount_cents"] == 100
            and goods["manual_discount_cents"] == 0 and goods["basis_points"] == 9000
            and guard.added["retail_lines"][0]["goods_cents"] == 900, "会员价原快照/分摊不能只靠标题")
    native.update(price_snapshot=snapshot, price_lines=guard.added["member_pricing_lines"], retail_line=guard.added["retail_lines"][0])
    await expect(e.page.locator("#main")).to_contain_text(rule["name"])
    return key, snapshot, native


async def retail_action(e, context, credentials, fixture, customer, member, primary, key, action, token, membership, *, account=None):
    role, category, title = {"approve": ("manager", None, "主管价格授权"),
        "authorize": ("sales", "authorization", "记录客户报价确认"), "dispatch": ("inventory", "evidence", "确认整单实际出库"),
        "receive": ("finance", "receipt", "登记实际收款"), "accept": ("sales", "evidence", "确认客户接收")}[action]
    handoff = await responsible(e, context, credentials, fixture, key, "retail_" + action, role, member)
    actor, view = await retail_view(e, context, credentials, fixture, role, key)
    proof = await upload(e, actor, key, member, RETAIL + "/orders/" + str(key), category, "points-retail-" + action, token) if category else None
    case, item = one(e, "flow_cases", key), one(e, "flow_items", primary["item_id"])
    balances = subset(e, "warehouse_balances", "item_id", item["id"])
    await original_form(e, "retail-action", action, title)
    values = {}
    if proof:
        await choose_file(e, proof, category)
        values["evidence_id"] = proof["file"]["id"]
    if action == "approve":
        await e.fill('#modal [name="minimum"]', "9.00", "主管明确900分原最低成交额")
        await checkbox(e, '#modal [name="allow_below_minimum"]', False, "无需低价例外")
        reason = "独立核对当前九折授权与本次1.000件900分"
        await e.fill('#modal [name="reason"]', reason, "原价格授权依据")
        values = {"minimum_total_cents": 900, "allow_below_minimum": False, "reason": reason}
    if action == "authorize":
        values["revision"] = 1
    if action == "receive":
        require(account is not None, "现金必须原账户")
        await e.fill('#modal [name="amount"]', "9.00", "财务实际收900分，不用权益面值替代")
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        reference = "PT-RETAIL-IN-" + token
        await e.fill('#modal [name="reference"]', reference, "登记本次实际到账流水")
        values.update(amount_cents=900, account_id=account["id"], reference=reference)
    append = {"flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1, "flow_tasks": (0, 2)}
    permitted = updates(e, [key])
    if action == "authorize":
        append.update(membership_points_claims=1, member_pricing_authorizations=1)
        permitted["group_members"] = {member: VERSION}
    allocation = None
    if action == "dispatch":
        prepared = [a for a in subset(e, "warehouse_allocations", "case_id", key)
                    if a["item_id"] == item["id"] and a["status"] == "prepared" and a["purpose"] == "retail_dispatch"]
        require(len(prepared) == 1, "本单没有唯一原库位准备")
        allocation = prepared[0]
        permitted.update(flow_items={item["id"]: VERSION | {"quantity_milli", "inventory_value_cents", "unit_cost_cents"}},
            warehouse_balances={b["id"]: VERSION | {"quantity_milli", "value_cents"} for b in balances},
            warehouse_allocations={allocation["id"]: VERSION | {"status", "stock_move_id"}})
        append.update(retail_reservations=1, flow_stock_moves=1, retail_dispatches=1, warehouse_entries=(1, len(balances)))
    if action == "receive":
        append.update(cash_entries=1, flow_payment_links=1, retail_payments=1, audit_logs=2)
        permitted["flow_accounts"] = {account["id"]: VERSION}
    if action == "accept":
        claim = subset(e, "membership_points_claims", "case_id", key)[0]
        require(claim["rule_id"] == membership["id"] and claim["target_units"] == claim["basis_cents"] == 0, "接受前不得伪造积分")
        append.update(membership_points_changes=1, benefit_wallets=1, benefit_entries=1)
        permitted["membership_points_claims"] = {claim["id"]: VERSION | {"basis_cents", "target_units"}}
        permitted["group_members"] = {member: VERSION}
    guard = Guard(e, "points_retail_" + action, actor, append=append, update=permitted,
                  cases={key}, member=member, customer=customer["id"], item=item["id"])
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/{action}", RETAIL + "/orders/" + str(key))
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}
            and shown["id"] == key and shown["version"] == one(e, "flow_cases", key)["version"], "原精品动作版本/载荷不符")
    native.update(guard=guard.finish(), handoff=handoff, proof=proof,
        receipt=flow_receipt(e, request, actor, key, "retail_" + action, {"case_id": key, "version": case["version"], "values": values}))
    if action == "authorize":
        claim = guard.added["membership_points_claims"][0]
        auth = guard.added["member_pricing_authorizations"][0]
        snap = subset(e, "member_pricing_snapshots", "case_id", key)[0]
        require(claim["rule_id"] == membership["id"] and claim["member_id"] == member and claim["target_units"] == 0
                and auth["snapshot_id"] == snap["id"] and auth["snapshot_digest"] == snap["digest"]
                and auth["evidence_id"] == proof["file"]["id"], "原报价授权/真正积分规则未冻结")
        native.update(points_claim=claim, price_authorization=auth)
    elif action == "dispatch":
        move = guard.added["flow_stock_moves"][0]
        cost = item["inventory_value_cents"] if item["quantity_milli"] == 1000 else (2 * item["inventory_value_cents"] * 1000 + item["quantity_milli"]) // (2 * item["quantity_milli"])
        now = one(e, "flow_items", item["id"])
        require(move["quantity_milli"] == -1000 and move["value_cents"] == -cost and move["purpose"] == "retail_dispatch"
                and now["quantity_milli"] == item["quantity_milli"] - 1000 and now["inventory_value_cents"] == item["inventory_value_cents"] - cost
                and one(e, "warehouse_allocations", allocation["id"])["stock_move_id"] == move["id"]
                and sum(r["quantity_milli"] for r in guard.added["warehouse_entries"]) == -1000
                and sum(r["value_cents"] for r in guard.added["warehouse_entries"]) == -cost, "原出库/平均成本/位置不守恒")
        native.update(stock_move=move, dispatch=guard.added["retail_dispatches"][0], warehouse_entries=guard.added["warehouse_entries"])
    elif action == "receive":
        link, cash = guard.added["flow_payment_links"][0], guard.added["cash_entries"][0]
        require(link["cash_id"] == cash["id"] and link["amount_cents"] == cash["amount_cents"] == 900
                and cash["direction"] == link["direction"] == "in" and cash["category"] == "workflow_retail"
                and link["account_id"] == account["id"] and cash["account"] == account["name"]
                and link["reference"] == cash["voucher_no"] == values["reference"]
                and subset(e, "membership_points_claims", "case_id", key)[0]["target_units"] == 0, "本次现金/原支付或接受前积分失配")
        native.update(cash=cash, payment_link=link, payment=guard.added["retail_payments"][0])
    elif action == "accept":
        claim = subset(e, "membership_points_claims", "case_id", key)[0]
        change, wallet, entry = guard.added["membership_points_changes"][0], guard.added["benefit_wallets"][0], guard.added["benefit_entries"][0]
        require(claim["basis_cents"] == change["basis_cents"] == 900 and claim["target_units"] == change["units"] == 9
                and change["claim_id"] == claim["id"] and change["wallet_id"] == wallet["id"] == entry["wallet_id"]
                and wallet["rule_id"] == membership["points_benefit_rule_id"] and wallet["source_case_id"] == key
                and wallet["source_kind"] == entry["purpose"] == "grant"
                and wallet["balance_units"] == wallet["initial_units"] == entry["units"] == 9 and wallet["reserved_units"] == 0
                and change["evidence_id"] == entry["evidence_id"] == proof["file"]["id"]
                and one(e, "flow_cases", key)["state"] == "completed", "真实消费赚取9分缺原来源或履约终态")
        native.update(points_claim=claim, points_change=change, earned_wallet=wallet, earned_entry=entry)
    return native


async def wallet_view(e, context, credentials, fixture, customer, member, wallet_ids, stage):
    actor, _ = await read_as(e, context, credentials, fixture, "finance", "benefits/" + str(customer["id"]), BENEFIT + "/members", "集团权益")
    before = e.business_snapshot("before_points_wallet_read_" + stage)
    async with e.page.expect_response(lambda r: get_match(r, BENEFIT + "/members")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        e.action("navigate", "刷新原权益批次与原整数余额：" + stage)
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["customer"]["id"] == customer["id"] and view["member"]["id"] == member, "原权益范围串人")
    await expect(e.page.locator("#main h1")).to_have_text("集团权益")
    result = []
    for key in wallet_ids:
        wallet = one(e, "benefit_wallets", key)
        found = next((w for w in view["wallets"] if w["id"] == key), None)
        require(found and all(found[k] == wallet[k] for k in ("member_id", "rule_id", "version", "initial_units",
            "balance_units", "reserved_units", "source_kind", "expires_on")), "原权益API/DB余额或批次不符")
        rule = one(e, "benefit_rules", wallet["rule_id"])
        unit = "积分" if rule["kind"] == "points" else "张"
        line = e.page.locator("#main tr").filter(has_text=rule["name"]).filter(has_text=f'{wallet["balance_units"] - wallet["reserved_units"]} / {wallet["reserved_units"]} {unit}')
        await expect(line).to_have_count(1)
        await expect(line).to_contain_text(wallet["expires_on"])
        entries = subset(e, "benefit_entries", "wallet_id", key)
        for entry in entries:
            api_entry = next((r for r in view["entries"] if r["id"] == entry["id"]), None)
            require(api_entry and all(api_entry[k] == entry[k] for k in api_entry), "原权益逐账API/DB不符")
        result.append({"wallet": wallet, "entries": entries})
    e.business_unchanged(before, "after_points_wallet_read_" + stage)
    return {"stage": stage, "wallet_facts": result, "native_refresh": True, "business_unchanged": True}


async def rejected_exchange(e, context, credentials, fixture, customer, member, wallet, target, token, units, status, message):
    values = {"action": "exchange", "wallet_id": wallet, "units": units, "target_rule_id": target["id"]}
    key, created = await create_member_order(e, context, credentials, fixture, customer, member, "exchange", values, token)
    handoff = await responsible(e, context, credentials, fixture, key, "membership_execute", "finance", member)
    actor, _ = await read_as(e, context, credentials, fixture, "finance", "membership-order/" + str(key), MEM + "/orders/" + str(key), "会员业务办理")
    proof = await upload(e, actor, key, member, MEM + "/orders/" + str(key), "evidence", "rejected-exchange-" + str(key), token)
    await original_form(e, "membership-action", "execute", "确认实际办理")
    await choose_file(e, proof)
    await e.fill('#modal [name="reason"]', "原消费积分边界明确核对" + token, "员工提交明确原拒绝边界")
    refusal = await rejected_submit(e, MEM + f"/orders/{key}/actions/execute", status, message)
    require(subset(e, "membership_orders", "case_id", key)[0]["status"] == "draft"
            and one(e, "benefit_wallets", wallet)["balance_units"] == 8, "拒绝后原积分或办理状态改变")
    actor, _ = await read_as(e, context, credentials, fixture, "service", "membership-order/" + str(key),
                             MEM + "/orders/" + str(key), "会员业务办理")
    case, order, current_member = one(e, "flow_cases", key), subset(e, "membership_orders", "case_id", key)[0], one(e, "group_members", member)
    require(order["requested_by"] == actor["id"], "撤销被拒绝申请必须回到原申请人")
    await original_form(e, "membership-action", "cancel", "撤销申请")
    reason = "已核原拒绝，取消这份未完成申请并保留记录"
    await e.fill('#modal [name="reason"]', reason, "取消被拒绝的独立会员申请")
    permitted = updates(e, [key], member=member)
    permitted["membership_orders"] = {order["id"]: VERSION | {"status"}}
    guard = Guard(e, "cancel_rejected_exchange_" + str(key), actor,
        append={"flow_events": 1, "audit_logs": 1, "group_receipts": 1, "membership_events": 1},
        update=permitted, cases={key}, member=member, customer=customer["id"])
    body, request, shown, native = await submit(e, MEM + f"/orders/{key}/actions/cancel", MEM + "/orders/" + str(key))
    expected = {"version": order["version"], "case_version": case["version"], "member_version": current_member["version"], "values": {"reason": reason}}
    require(request == {"request_id": request["request_id"], **expected} and shown["order"]["status"] == "cancelled", "被拒绝原申请未明确取消")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, f"membership:{key}:cancel", expected, body))
    return {"case_id": key, "create": created, "handoff": handoff, "proof": proof, "refusal": refusal, "cancel": native}


async def disabled_price_read(e, context, credentials, fixture, customer, original):
    actor, candidates = await new_retail_form(e, context, credentials, fixture, customer)
    require(not any(r["id"] == original["id"] or r["name"] == original["name"] for r in candidates["items"]), "停用新版后旧规则仍可新报价")
    await expect(e.page.locator(f'#modal [name="member_pricing_rule"] option[value="{original["id"]}"]')).to_have_count(0)
    before = e.business_snapshot("before_cancel_unsubmitted_price_lookup")
    await e.click('#modal .modalhead [data-act="close"]', "关闭未提交报价，保留原业务")
    discard = e.page.locator('#modal [data-wfx-discard]')
    if await discard.is_visible():
        await e.click('#modal [data-wfx-discard]', "明确放弃本次未提交的填写")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "after_cancel_unsubmitted_price_lookup")
    return {"native_new_quote_candidates": candidates, "original_rule_unavailable": True, "business_unchanged": True}


def new_period(execution, rule, member, case_id, *, start, end, kind):
    periods = execution["facts"]["membership_periods"]
    require(len(periods) == 1, "实办没有唯一新会期")
    period = periods[0]
    require(period["member_id"] == member and period["rule_id"] == rule["id"] and period["case_id"] == case_id
            and period["starts_on"] == start and period["ends_on"] == end and period["kind"] == kind, "实际自然月/原等级会期不符")
    return period


async def member_points_tier_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, customer, member, account, primary = dependencies(e, cp)
        token = uuid.uuid4().hex[:10]
        baseline_member = one(e, "group_members", member)
        sources = {"customer_id": customer["id"], "member_id": member, "account_id": account["id"],
                   "primary_item_id": primary["item_id"], "source_location_id": primary["source_location_id"],
                   "centre_payment_performed": False, "full_193_business_acceptance": False}

        cp.start("HK-121")
        points, points_publish = await publish_benefit(e, context, credentials, fixture, customer, member, token, "points")
        tier_a, a_publish = await membership_rule(e, context, credentials, fixture, points, token, "A")
        tier_b, b_publish = await membership_rule(e, context, credentials, fixture, points, token, "B")
        cp.note({"points_rule": points_publish, "tier_rules": [a_publish, b_publish]})
        a_key, a_create = await create_member_order(e, context, credentials, fixture, customer, member, "tier_change", {"rule_id": tier_a["id"]}, token)
        a_review = await member_action(e, context, credentials, fixture, customer, member, a_key, "approve", "manager", token)
        a_execute = await member_action(e, context, credentials, fixture, customer, member, a_key, "execute", "service", token)
        day = date.fromisoformat(one(e, "flow_cases", a_key)["business_date"])
        period_a = new_period(a_execute, tier_a, member, a_key, start=day.isoformat(), end=month_end(day, 1).isoformat(), kind="tier_change")
        b_key, b_create = await create_member_order(e, context, credentials, fixture, customer, member, "tier_change", {"rule_id": tier_b["id"]}, token)
        b_review = await member_action(e, context, credentials, fixture, customer, member, b_key, "approve", "manager", token)
        b_execute = await member_action(e, context, credentials, fixture, customer, member, b_key, "execute", "service", token)
        b_day = date.fromisoformat(one(e, "flow_cases", b_key)["business_date"])
        period_b = new_period(b_execute, tier_b, member, b_key, start=b_day.isoformat(), end=period_a["ends_on"], kind="tier_change")
        require(one(e, "membership_periods", period_a["id"]) == period_a, "真实改级覆盖旧会期")
        _, active_view = await member_view(e, context, credentials, fixture, customer, member, period=period_b)
        sources.update(points_rule_id=points["id"], membership_rule_ids=[tier_a["id"], tier_b["id"]],
                       tier_case_ids=[a_key, b_key], period_ids=[period_a["id"], period_b["id"]], active_period_id=period_b["id"])
        await cp.passed({"tier_a": {"create": a_create, "approve": a_review, "execute": a_execute, "period": period_a},
            "tier_b": {"create": b_create, "approve": b_review, "execute": b_execute, "period": period_b}, "active_view": active_view})

        cp.start("HK-122")
        renew_key, renew_create = await create_member_order(e, context, credentials, fixture, customer, member, "renew", {"rule_id": tier_b["id"]}, token)
        renew_review = await member_action(e, context, credentials, fixture, customer, member, renew_key, "approve", "manager", token)
        renew_execute = await member_action(e, context, credentials, fixture, customer, member, renew_key, "execute", "finance", token, account=account)
        renew_start = max(date.fromisoformat(one(e, "flow_cases", renew_key)["business_date"]),
                          date.fromisoformat(period_b["ends_on"]) + timedelta(days=1))
        renewed = new_period(renew_execute, tier_b, member, renew_key, start=renew_start.isoformat(), end=month_end(renew_start, 1).isoformat(), kind="renew")
        fee, fee_cash = renew_execute["facts"]["membership_fees"][0], renew_execute["facts"]["cash_entries"][0]
        require(fee["amount_cents"] == fee_cash["amount_cents"] == 300 and fee["period_id"] == renewed["id"]
                and fee["cash_id"] == fee_cash["id"] and fee["account_id"] == account["id"]
                and fee_cash["category"] == "group_member_fee" and fee_cash["direction"] == "in"
                and fee_cash["account"] == account["name"] and fee["original_id"] is None
                and fee["reference"] == fee_cash["voucher_no"]
                and fee["evidence_id"] == renew_execute["proof"]["file"]["id"], "续会原实际收费不符")
        cp.note({"renew_create": renew_create, "review": renew_review, "execute": renew_execute, "future_period": renewed, "fee": fee, "cash": fee_cash})
        refund_key, refund_create = await create_member_order(e, context, credentials, fixture, customer, member, "renew_refund", {"period_id": renewed["id"]}, token, root_case=renew_key)
        refund_review = await member_action(e, context, credentials, fixture, customer, member, refund_key, "approve", "manager", token, root_case=renew_key)
        refund_execute = await member_action(e, context, credentials, fixture, customer, member, refund_key, "execute", "finance", token, account=account, root_case=renew_key)
        refunded_fee, refund_cash = refund_execute["facts"]["membership_fees"][0], refund_execute["facts"]["cash_entries"][0]
        basis, void = refund_execute["facts"]["membership_fee_refund_bases"][0], refund_execute["facts"]["membership_period_voids"][0]
        require(refunded_fee["amount_cents"] == -300 and refund_cash["amount_cents"] == 300 and refund_cash["direction"] == "out"
                and refund_cash["category"] == "group_member_fee_refund" and refunded_fee["cash_id"] == refund_cash["id"]
                and refunded_fee["original_id"] == fee["id"] and refunded_fee["account_id"] == fee["account_id"] == account["id"]
                and basis["refund_fee_id"] == refunded_fee["id"] and basis["original_fee_id"] == fee["id"]
                and basis["original_cash_id"] == fee_cash["id"] and void["period_id"] == renewed["id"]
                and refunded_fee["reference"] == refund_cash["voucher_no"] and refund_cash["account"] == account["name"]
                and refunded_fee["evidence_id"] == refund_execute["proof"]["file"]["id"]
                and one(e, "membership_periods", renewed["id"]) == renewed, "未开始原续会费/原账户/整笔退款来源不符")
        _, view = await member_view(e, context, credentials, fixture, customer, member, period=period_b)
        require(not any(p["id"] == renewed["id"] for p in view["periods"]), "原退会期没有Void生效")
        sources.update(renew_case_id=renew_key, renew_period_id=renewed["id"], renew_fee_id=fee["id"], renew_cash_id=fee_cash["id"],
            renew_refund_case_id=refund_key, renew_refund_fee_id=refunded_fee["id"], renew_refund_cash_id=refund_cash["id"],
            period_void_id=void["id"], fee_refund_basis_id=basis["id"])
        await cp.passed({"create": refund_create, "approve": refund_review, "execute": refund_execute,
            "original_fee": fee, "original_cash": fee_cash, "refund_fee": refunded_fee, "refund_cash": refund_cash,
            "period_void": void, "original_fee_basis": basis, "renew_cash_net_cents": 0, "current_period": period_b})

        cp.start("HK-188")
        price, price_create = await price_rule(e, context, credentials, fixture, member, primary, tier_b, token)
        price_submit = await price_action(e, context, credentials, fixture, member, price, "submit", "manager", token)
        price_refusal = await price_action(e, context, credentials, fixture, member, price, "approve", "manager", token, reject_self=True)
        price_approve = await price_action(e, context, credentials, fixture, member, price, "approve", "admin", token)
        cp.note({"price_create": price_create, "submit": price_submit, "self_approve_refusal": price_refusal, "independent_approve": price_approve})
        retail_key, price_snapshot, retail_create = await create_retail(e, context, credentials, fixture, customer, member, primary, price)
        retail_steps = {"create": retail_create}
        for action in ("approve", "authorize"):
            retail_steps[action] = await retail_action(e, context, credentials, fixture, customer, member, primary, retail_key, action, token, tier_b)
            cp.note({action: retail_steps[action]})
        retail_steps["prepare"] = await prepare_retail(e, context, credentials, fixture, member, primary, retail_key)
        for action in ("dispatch", "receive", "accept"):
            retail_steps[action] = await retail_action(e, context, credentials, fixture, customer, member, primary, retail_key, action, token, tier_b,
                                                       account=account if action == "receive" else None)
            cp.note({action: retail_steps[action]})
        accepted = retail_steps["accept"]
        earned_wallet, earned_entry = accepted["earned_wallet"], accepted["earned_entry"]
        change, claim = accepted["points_change"], accepted["points_claim"]
        frozen_original = {"rule": one(e, "member_pricing_rules", price["id"]), "snapshot": one(e, "member_pricing_snapshots", price_snapshot["id"]),
                           "lines": subset(e, "retail_lines", "case_id", retail_key), "cash": retail_steps["receive"]["cash"]}
        disabled, disabled_create = await price_rule(e, context, credentials, fixture, member, primary, tier_b, token, enabled=False)
        disabled_submit = await price_action(e, context, credentials, fixture, member, disabled, "submit", "manager", token)
        disabled_approve = await price_action(e, context, credentials, fixture, member, disabled, "approve", "admin", token)
        disabled_lookup = await disabled_price_read(e, context, credentials, fixture, customer, price)
        require(disabled["rule_version"] == price["rule_version"] + 1
                and one(e, "member_pricing_rules", price["id"]) == frozen_original["rule"]
                and one(e, "member_pricing_snapshots", price_snapshot["id"]) == frozen_original["snapshot"]
                and subset(e, "retail_lines", "case_id", retail_key) == frozen_original["lines"]
                and one(e, "cash_entries", frozen_original["cash"]["id"]) == frozen_original["cash"], "新停用价重写已授权原报价或到账")
        sources.update(member_price_rule_id=price["id"], member_price_disabled_rule_id=disabled["id"], member_price_snapshot_id=price_snapshot["id"],
            member_price_line_ids=[r["id"] for r in subset(e, "member_pricing_lines", "snapshot_id", price_snapshot["id"])],
            member_price_authorization_id=retail_steps["authorize"]["price_authorization"]["id"], retail_case_id=retail_key,
            retail_line_ids=[r["id"] for r in subset(e, "retail_lines", "case_id", retail_key)], retail_stock_move_id=retail_steps["dispatch"]["stock_move"]["id"],
            retail_cash_id=retail_steps["receive"]["cash"]["id"], retail_payment_link_id=retail_steps["receive"]["payment_link"]["id"],
            points_claim_id=claim["id"], points_change_id=change["id"], earned_points_wallet_id=earned_wallet["id"], earned_points_entry_id=earned_entry["id"])
        await cp.passed({"member_price_rule": price, "retail": retail_steps, "earned_points_source": {"claim": claim, "change": change, "wallet": earned_wallet, "entry": earned_entry},
            "new_disabled_version": {"create": disabled_create, "submit": disabled_submit, "approve": disabled_approve, "new_quote_lookup": disabled_lookup},
            "original_quote_and_cash_unchanged": True, "member_discount_cents": 100, "actual_cash_cents": 900})

        cp.start("HK-120")
        adjust_key, adjust_create = await create_member_order(e, context, credentials, fixture, customer, member, "adjust",
            {"action": "adjust", "wallet_id": earned_wallet["id"], "units": 1}, token)
        adjust = await member_action(e, context, credentials, fixture, customer, member, adjust_key, "execute", "manager", token, wallet=earned_wallet["id"])
        negative = adjust["facts"]["benefit_entries"][0]
        require(negative["wallet_id"] == earned_wallet["id"] and negative["purpose"] == "adjust" and negative["units"] == -1
                and one(e, "benefit_wallets", earned_wallet["id"])["balance_units"] == 8
                and one(e, "benefit_entries", earned_entry["id"]) == earned_entry, "原扣1覆盖消费原批次/原账")
        grant_key, grant_create = await create_member_order(e, context, credentials, fixture, customer, member, "grant",
            {"action": "grant", "rule_id": points["id"], "units": 5}, token)
        grant = await member_action(e, context, credentials, fixture, customer, member, grant_key, "execute", "manager", token)
        gift_wallet, gift_entry = grant["facts"]["benefit_wallets"][0], grant["facts"]["benefit_entries"][0]
        require(gift_wallet["id"] != earned_wallet["id"] and gift_wallet["rule_id"] == points["id"]
                and gift_wallet["initial_units"] == gift_wallet["balance_units"] == gift_entry["units"] == 5
                and gift_wallet["source_case_id"] == gift_entry["case_id"] == grant_key and gift_entry["purpose"] == "grant"
                and gift_entry["cash_id"] is None and gift_wallet["reserved_units"] == 0
                and one(e, "membership_points_changes", change["id"]) == change, "正赠5必须另批、不能伪装赚取积分")
        adjusted_view = await wallet_view(e, context, credentials, fixture, customer, member, [earned_wallet["id"], gift_wallet["id"]], "adjust-and-separate-grant")
        sources.update(points_adjust_case_id=adjust_key, points_adjust_entry_id=negative["id"], points_grant_case_id=grant_key,
                       independent_points_wallet_id=gift_wallet["id"], independent_points_grant_entry_id=gift_entry["id"])
        await cp.passed({"negative_adjust": {"create": adjust_create, "execute": adjust, "entry": negative},
            "positive_separate_grant": {"create": grant_create, "execute": grant, "wallet": gift_wallet, "entry": gift_entry},
            "native_balances": adjusted_view, "original_earned_points_change_unchanged": True, "cash_change_cents": 0})

        cp.start("HK-119")
        target, target_publish = await publish_benefit(e, context, credentials, fixture, customer, member, token, "coupon")
        odd = await rejected_exchange(e, context, credentials, fixture, customer, member, earned_wallet["id"], target, token, 3, 422, "积分必须是本版本每份兑换积分的整数倍")
        excess = await rejected_exchange(e, context, credentials, fixture, customer, member, earned_wallet["id"], target, token, 10, 409, "权益不足或已被消费/退款占用")
        exchange_key, exchange_create = await create_member_order(e, context, credentials, fixture, customer, member, "exchange",
            {"action": "exchange", "wallet_id": earned_wallet["id"], "units": 4, "target_rule_id": target["id"]}, token)
        exchange = await member_action(e, context, credentials, fixture, customer, member, exchange_key, "execute", "finance", token, wallet=earned_wallet["id"])
        outgoing = next(r for r in exchange["facts"]["benefit_entries"] if r["purpose"] == "exchange_out")
        incoming = next(r for r in exchange["facts"]["benefit_entries"] if r["purpose"] == "exchange_in")
        exchanged_wallet = exchange["facts"]["benefit_wallets"][0]
        require(outgoing["wallet_id"] == earned_wallet["id"] and outgoing["units"] == -4
                and incoming["original_id"] == outgoing["id"] and incoming["wallet_id"] == exchanged_wallet["id"]
                and incoming["units"] == exchanged_wallet["initial_units"] == exchanged_wallet["balance_units"] == 2
                and exchanged_wallet["rule_id"] == target["id"] and exchanged_wallet["source_kind"] == "exchange"
                and outgoing["cash_id"] is None and incoming["cash_id"] is None
                and one(e, "benefit_wallets", earned_wallet["id"])["balance_units"] == 4
                and one(e, "benefit_wallets", gift_wallet["id"])["balance_units"] == 5, "原积分兑券/来源/精确整数倍不守恒")
        exchanged_view = await wallet_view(e, context, credentials, fixture, customer, member,
            [earned_wallet["id"], gift_wallet["id"], exchanged_wallet["id"]], "exact-earned-points-exchange")
        sources.update(exchange_target_rule_id=target["id"], points_exchange_case_id=exchange_key,
            points_exchange_out_entry_id=outgoing["id"], points_exchange_in_entry_id=incoming["id"], exchanged_coupon_wallet_id=exchanged_wallet["id"],
            rejected_exchange_case_ids=[odd["case_id"], excess["case_id"]])
        await cp.passed({"target_rule": target_publish, "exact_multiple_refusal": odd, "over_available_refusal": excess,
            "create": exchange_create, "execute": exchange, "outgoing": outgoing, "incoming": incoming,
            "exchanged_wallet": exchanged_wallet, "native_balances": exchanged_view, "cash_change_cents": 0})

        cp.start("HK-131")
        direct_key, direct_create = await create_member_order(e, context, credentials, fixture, customer, member, "grant",
            {"action": "grant", "rule_id": target["id"], "units": 1}, token)
        direct = await member_action(e, context, credentials, fixture, customer, member, direct_key, "execute", "manager", token)
        direct_wallet, direct_entry = direct["facts"]["benefit_wallets"][0], direct["facts"]["benefit_entries"][0]
        require(direct_wallet["id"] != exchanged_wallet["id"] and direct_wallet["rule_id"] == target["id"]
                and direct_wallet["source_kind"] == direct_entry["purpose"] == "grant"
                and direct_wallet["initial_units"] == direct_wallet["balance_units"] == direct_entry["units"] == 1
                and direct_wallet["source_case_id"] == direct_entry["case_id"] == direct_key
                and direct_entry["cash_id"] is None and direct_entry["original_id"] is None
                and direct_wallet["reserved_units"] == 0, "原直接赠券不是独立grant或误用组合/购买")
        final_view = await wallet_view(e, context, credentials, fixture, customer, member,
            [earned_wallet["id"], gift_wallet["id"], exchanged_wallet["id"], direct_wallet["id"]], "direct-grant-four-distinct-sources")
        final_member = one(e, "group_members", member)
        require(final_member["balance_cents"] == baseline_member["balance_cents"] and final_member["reserved_cents"] == baseline_member["reserved_cents"]
                and one(e, "membership_points_changes", change["id"]) == change and one(e, "benefit_entries", earned_entry["id"]) == earned_entry
                and one(e, "membership_periods", period_a["id"]) == period_a and one(e, "membership_periods", period_b["id"]) == period_b, "本批改写会员本金或原积分/会期历史")
        sources.update(direct_coupon_grant_case_id=direct_key, direct_coupon_wallet_id=direct_wallet["id"], direct_coupon_grant_entry_id=direct_entry["id"],
            actual_points_earned_units=9, earned_points_remaining_units=4, independent_points_granted_units=5,
            coupon_exchange_units=2, direct_coupon_grant_units=1, cash_ids=[fee_cash["id"], refund_cash["id"], sources["retail_cash_id"]],
            cash_net_cents=900, member_principal_unchanged=True, points_consumption_or_points_change=True,
            points_debt_acceptance=False, mixed_package_acceptance=False)
        await cp.passed({"create": direct_create, "execute": direct, "wallet": direct_wallet, "entry": direct_entry,
            "native_balances": final_view, "separate_source_kind": "direct_grant", "cash_change_cents": 0,
            "original_period_points_principal_unchanged": True})
        cp.finish(sources)
    except Exception as error:
        cp.failed(error)
        raise


MEMBER_POINTS_TIER_SCENARIOS = ((SCENARIO, member_points_tier_business, 1200),)
