"""Unregistered mixed repair-package purchase, real fulfilment and unused refunds.

Only original native employee forms write; same-run passed sources and SELECT
reads supply IDs. No app import, seeded outcome or second cash at capture.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency, fen_text
from vehicle_purchase_business import checkbox, live_choice, select_value
from finance_business import get_match, submit
from membership_business import group_receipt
import member_followon_business as MF
import repair_business as R

SCENARIO = "repair-packages-hk043-133-126-127"
MEMBERSHIP = MF.MEMBERSHIP
MATERIAL = MF.MATERIAL
MASTER = MF.MASTERS
REPAIR_SOURCE = R.SCENARIO
POINTS_SOURCE = "member-points-tier-hk121-122-188-120-119-131"
API = "/api/repair-packages"
REQUIREMENTS = (("HK-043", "维修套餐设置"), ("HK-133", "套餐卡类型"),
                ("HK-126", "会员套餐购买"), ("HK-127", "会员套餐退款"))
VERSION = {"version", "updated_at"}
TASK = VERSION | {"status", "done_by", "done_at", "due_date"}
FLOW = {"flow_events": 1, "audit_logs": 1}
GROUP_FLOW = {**FLOW, "group_receipts": 1}
REPAIR_FLOW = {**FLOW, "flow_request_receipts": 1}
PACKAGE_TABLES = {"repair_package_" + suffix for suffix in (
    "rules", "rule_decisions", "mappings", "purchases", "purchase_events", "lots", "holds", "entries",
    "reservation_links", "payment_links", "settlements", "refunds", "refund_claims", "quote_snapshots")}
TABLES = PACKAGE_TABLES | set(R.PRIMARY_KEYS) | {
    "group_members", "group_entries", "group_receipts", "group_identities", "group_identity_links", "group_events", "care_receipts",
    "benefit_wallets", "benefit_entries", "membership_points_changes"}
READ_TABLES = TABLES | {"flow_customers", "membership_cards", "membership_periods", "membership_rules", "benefit_rules",
    "membership_points_debts", "master_work_items", "master_locations", "master_warehouses", "warehouse_enrollments",
    "procurement_orders", "procurement_receipts", "procurement_lines"}
PKEYS = {**{t: "id" for t in READ_TABLES}, **R.PRIMARY_KEYS}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def rows(e, table):
    require(table in READ_TABLES, "套餐未审原表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {PKEYS[table]}")


def one(e, table, key):
    require(table in READ_TABLES and type(key) is int and key > 0, "缺有限原ID：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PKEYS[table]}=?", (key,))
    require(len(found) == 1, "有限原记录不唯一：" + table)
    return found[0]


def subset(e, table, field, value):
    require(table in READ_TABLES and field in {"case_id", "member_id", "rule_id", "purchase_id", "quote_id", "refund_id",
        "item_id", "allocation_id", "appointment_id", "claim_id", "lot_id", "entry_id"}, "未审关联")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {PKEYS[table]}", (value,))


def decoded(row, *fields):
    result = dict(row)
    for field in fields:
        result[field] = json.loads(result[field])
    require(not any(isinstance(v, bytes) for v in result.values()), "原件正文不得进入JSON证据")
    return result


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]), "套餐原目录不匹配：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__).read_bytes()),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False, "human_acceptance": "pending",
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested", "evidence": {}}]}
                for key, title in REQUIREMENTS],
            "conditional_checks": [{"status": "not_tested", "scope": scope} for scope in
                ("已耗配件售后实际回库及权益恢复", "逐组件停工和保留费用", "过期、跨店、全部异常及并发",
                 "零对价注销、真实银行、ClamAV、PostgreSQL和员工验收")],
            "conditions": {"synthetic_inputs_only": True, "file_scan": "structure_only_not_clamav", "centre_payment": False,
                           "new_fixture_results": False, "new_roles": 0, "bank_acceptance": False}}
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
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "source_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "套餐四项未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=4, passed_requirements=4,
                           repair_package_sources=sources, report_sources=sources)
        self.save()


class Guard:
    """One original action: finite IDs/columns, append counts, all old rows protected."""
    def __init__(self, e, label, actor, *, append, update=None, cases=(), customer=None, member=None,
                 item=None, work=None, vehicle=None, resource=None, new_kind=None, lots=(), purchase=None, refund=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = dict(append), update or {}
        self.cases, self.lots = set(cases), set(lots)
        self.customer, self.member, self.item, self.work = customer, member, item, work
        self.vehicle, self.resource, self.new_kind = vehicle, resource, new_kind
        self.purchase, self.refund = purchase, refund
        require(self.append.keys() | self.update.keys() <= TABLES, "套餐保护超出已审原表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "套餐改变无关原表：" + str(sorted(changed)))
        added = {t: [r for r in rows(self.e, t) if r[PKEYS[t]] not in {v[PKEYS[t]] for v in old}] for t, old in self.old.items()}
        for table, new in added.items():
            count = self.append.get(table, 0)
            low, high = count if isinstance(count, tuple) else (count, count)
            require(low <= len(new) <= high, "原新增数错误：" + table + "/" + str(len(new)))
        fresh_cases = added.get("flow_cases", [])
        require(not fresh_cases or len(fresh_cases) == 1 and fresh_cases[0]["kind"] == self.new_kind
                and fresh_cases[0]["customer_id"] == self.customer and fresh_cases[0]["created_by"] == self.actor["id"], "新增宿主串客户/身份/类型")
        owned = self.cases | {r["id"] for r in fresh_cases}
        owned_lots = self.lots | {r["id"] for r in added.get("repair_package_lots", [])}
        owned_purchases = ({self.purchase} if self.purchase else set()) | {r["id"] for r in added.get("repair_package_purchases", [])}
        owned_refunds = ({self.refund} if self.refund else set()) | {r["id"] for r in added.get("repair_package_refunds", [])}
        changed_columns = {}
        for table, old in self.old.items():
            current = {r[PKEYS[table]]: r for r in rows(self.e, table)}
            changed_columns[table] = []
            for prior in old:
                key = prior[PKEYS[table]]
                require(key in current, "删除旧原行：" + table)
                columns = {k for k in prior if prior[k] != current[key][k]}
                require(columns <= self.update.get(table, {}).get(key, set()), "覆盖非授权原列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if columns:
                    changed_columns[table].append({"id": key, "columns": sorted(columns)})
            for row in added[table]:
                for field in ("store_id", "issuer_store_id"):
                    if field in row:
                        require(row[field] == 1, "新增事实串门店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "新增事实串原单：" + table)
                if "customer_id" in row:
                    require(row["customer_id"] == self.customer, "新增事实串客户：" + table)
                if "member_id" in row and row["member_id"] is not None:
                    require(row["member_id"] == self.member, "新增事实串会员：" + table)
                if "item_id" in row:
                    if table == "repair_lines" and row["item_id"] is None:
                        require(row["kind"] == "work" and self.work is not None and row["work_item_id"] == self.work,
                                "新增纯作业必须引用本次明确作业：" + table)
                    else:
                        require(row["item_id"] == self.item, "新增事实串物资：" + table)
                if "customer_vehicle_id" in row:
                    require(row["customer_vehicle_id"] == self.vehicle, "新增事实串客户车辆：" + table)
                if "resource_id" in row:
                    require(row["resource_id"] == self.resource, "新增事实串工位：" + table)
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "新增事实借用身份：" + table)
                if "lot_id" in row:
                    require(row["lot_id"] in owned_lots, "新增事实串原Lot")
                if "purchase_id" in row:
                    require(row["purchase_id"] in owned_purchases, "新增事实串购买原批")
                if row.get("refund_id") is not None:
                    require(row["refund_id"] in owned_refunds, "新增事实串退款原批")
                if "quote_id" in row:
                    require(one(self.e, "repair_quotes", row["quote_id"])["case_id"] in owned, "新增事实串报价")
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", row["balance_id"])["item_id"] == self.item, "位置流水串物资")
                if table == "warehouse_allocation_lines":
                    allocation = one(self.e, "warehouse_allocations", row["allocation_id"])
                    require(allocation["case_id"] in owned and allocation["item_id"] == self.item, "位置准备串原单")
        self.added = added
        value = {"label": self.label, "changed_tables": sorted(changed), "expected_counts": self.append,
            "appended_ids": {t: [r[PKEYS[t]] for r in new] for t, new in added.items()}, "updated_columns": changed_columns,
            "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("repair_package_original_guard", value)
        return value


def updates(e, case_ids=(), *, member=None, account=None, purchase=None, lots=(), refund=None, case_columns=()):
    value = {"flow_cases": {k: VERSION | set(case_columns) for k in case_ids},
             "flow_tasks": {t["id"]: TASK for k in case_ids for t in subset(e, "flow_tasks", "case_id", k) if t["status"] == "open"}}
    if member:
        value["group_members"] = {member: VERSION}
    if account:
        value["flow_accounts"] = {account: VERSION}
    if purchase:
        value["repair_package_purchases"] = {purchase: VERSION}
    if lots:
        value["repair_package_lots"] = {key: VERSION for key in lots}
    if refund:
        value["repair_package_refunds"] = {refund: VERSION}
    return {t: by_id for t, by_id in value.items() if by_id}


def intake_receipt(guard, request, operation, payload, result):
    found = guard.added["intake_command_receipts"]
    require(len(found) == 1 and found[0]["request_key"] == request["request_id"]
            and found[0]["actor_id"] == guard.actor["id"]
            and found[0]["digest"] == canonical({"operation": "intake_" + operation, "payload": payload})
            and json.loads(found[0]["result"]) == result, "原接待回执未绑定本次本人完整输入及唯一结果")
    return {"id": found[0]["id"], "digest": found[0]["digest"], "actor_id": found[0]["actor_id"]}


def dependencies(e, cp):
    root = Path(e.manifest["evidence_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True
            and Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "只允许同轮外置合成库")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "镜像快照不稳定")
    for name in ("repair_packages_business.py", "repair_business.py", "member_followon_business.py", "membership_business.py",
                 "material_business.py", "master_data_business.py", "sales_business.py", "sales_order_business.py",
                 "vehicle_purchase_business.py", "finance_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "非同轮脚本指纹：" + name)
    membership, material, master, repair = [fixed_dependency(e, cp, s) for s in (MEMBERSHIP, MATERIAL, MASTER, REPAIR_SOURCE)]
    source, primary = membership["membership_sources"], material["material_sources"]["primary"]
    customer, member, account = [one(e, t, source[k]) for t, k in
        (("flow_customers", "customer_id"), ("group_members", "member_id"), ("flow_accounts", "account_id"))]
    original, returned = one(e, "group_entries", source["topup_entry_id"]), one(e, "group_entries", source["refund_entry_id"])
    require(original["amount_cents"] == 10000 and returned["amount_cents"] == -4000 and returned["original_id"] == original["id"], "会员普通原款来源不匹配")
    require(member["active"] == account["active"] == 1 and member["reserved_cents"] == 0
            and one(e, "membership_cards", source["active_card_id"])["status"] == "active", "当前会员或原账户失效")
    link = e.db.rows("SELECT * FROM group_identity_links WHERE local_kind='customer' AND local_id=? AND store_id=1", (customer["id"],))
    require(len(link) == 1 and link[0]["identity_id"] == member["identity_id"], "会员与本店原客户未明确同一身份")
    item, warehouse, location, enrollment = [one(e, t, primary[k]) for t, k in
        (("flow_items", "item_id"), ("master_warehouses", "warehouse_id"), ("master_locations", "source_location_id"), ("warehouse_enrollments", "enrollment_id"))]
    require(item["active"] == warehouse["active"] == location["active"] == 1 and item["unit"] == "升"
            and enrollment["item_id"] == item["id"] and location["id"] in primary["location_ids"]
            and location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials", "原材料有限来源失效")
    balance = [r for r in subset(e, "warehouse_balances", "item_id", item["id"])
               if r["location_id"] == location["id"] and r["transit_case_id"] is None]
    require(len(balance) == 1 and balance[0]["quantity_milli"] >= 1000 and item["quantity_milli"] >= 1000
            and item["inventory_value_cents"] is not None, "原采购实位当前数量/成本不足")
    for rid in primary["receipt_ids"]:
        receipt = one(e, "procurement_receipts", rid)
        move = one(e, "flow_stock_moves", receipt["stock_move_id"])
        require(receipt["case_id"] == primary["purchase_order_id"] and move["id"] in primary["stock_move_ids"]
                and move["item_id"] == item["id"] and move["quantity_milli"] == receipt["quantity_milli"], "缺同轮真实原采购入库")
    work = one(e, "master_work_items", checkpoint_evidence(master, "HK-175")["row"]["id"])
    resource = one(e, "intake_resources", checkpoint_evidence(repair, "HK-031")["resource"]["id"])
    require(work["active"] == resource["active"] == 1 and work["billing_unit"] == "job"
            and resource["active_case_id"] is None and one(e, "flow_cases", repair["report_sources"]["repair_case_id"])["state"] == "completed", "原工位未释放或作业单位不符")
    fixture = dict(e.manifest["business_fixtures"]["repair"])
    fixture["sales_key"] = e.manifest["business_fixtures"]["sales_order"]["sales_key"]
    for role in ("service", "manager", "technician", "inventory", "finance", "sales"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=1 AND role=?", (actor["id"], role))) == 1, "缺本人当前门店岗位：" + role)
    require(customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"] and all(r["store_id"] == 1 for r in (customer, account, item, warehouse, location, work, resource)), "有限来源串店或客户归属改变")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=1"), "本候选不代经营主体策略或现金主体验收")
    points = None
    periods = subset(e, "membership_periods", "member_id", member["id"])
    if periods:
        points = fixed_dependency(e, cp, POINTS_SOURCE)["member_points_tier_sources"]
        require(points["member_id"] == member["id"] and points["customer_id"] == customer["id"], "会期不是同轮同会员通过来源")
        require(provenance["script_files"].get("member_points_tier_business.py") == sha(Path(__file__).with_name("member_points_tier_business.py").read_bytes()), "积分来源脚本不同轮")
    cp.report["source_preconditions"] = {"membership": source, "primary": primary, "work": work, "resource": resource,
        "customer": customer, "member": member, "account": account, "source_balance": balance[0], "points_source": points,
        "old_repair_customer_id": repair["report_sources"]["customer_id"], "new_same_member_vehicle_required": True,
        "provenance_sha256": sha((root / "provenance.json").read_bytes())}
    cp.save()
    return fixture, customer, member["id"], account, work, item, warehouse, location, resource, points


async def read_as(e, context, credentials, fixture, role, route, path, heading=None):
    async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, 1)
    response = await pending.value
    view = await response.json()
    require(response.status == 200, "本人原页面读取失败：" + path)
    await expect(e.page.locator("#main h1")).to_have_text(heading or view["title"])
    return actor, view


async def handoff(e, context, credentials, fixture, case_id, task_key, role, member):
    return await MF.responsible(e, context, credentials, fixture, case_id, task_key, role, member)


async def proof(e, context, credentials, fixture, role, case_id, member, category, label, token):
    actor, _ = await read_as(e, context, credentials, fixture, role, "case/" + str(case_id), "/api/flow/cases/" + str(case_id))
    return await MF.upload(e, actor, case_id, member, "/api/flow/cases/" + str(case_id), category, label, token)


async def click_form(e, selector, title):
    await expect(e.page.locator(selector)).to_have_count(1)
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "本人打开原表单：" + title)
    await expect(e.page.locator("#modal-title")).to_have_text(title)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def submit_vehicle(e):
    """Bind the new vehicle GET to the one native POST, including render races."""
    path, prefix = "/api/customer-service/vehicles", "/api/customer-service/vehicles/"
    observed, wanted = [], None
    matching = asyncio.get_running_loop().create_future()

    def listener(response):
        if get_match(response, prefix):
            observed.append(response)
            if urlsplit(response.url).path == wanted and not matching.done():
                matching.set_result(response)

    e.page.on("response", listener)
    try:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "销售本人明确提交同会员新车辆关系")
        response = await pending.value
        body = await response.json()
        require(response.status == 201 and type(body.get("vehicle", {}).get("id")) is int, "原车辆提交失败：" + e.scrub(body.get("detail", "")))
        wanted = prefix + str(body["vehicle"]["id"])
        for read in observed:
            if urlsplit(read.url).path == wanted and not matching.done():
                matching.set_result(read)
        read = await asyncio.wait_for(matching, 30)
        view = await read.json()
        require(read.status == 200 and view["vehicle"]["id"] == body["vehicle"]["id"], "原新车辆GET串ID")
        meta, request = await R.metadata(e, response, 1)
        require((await response.request.all_headers()).get("x-app-request") == "1", "原车辆请求缺同源应用标记")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main .notice.error")).to_have_count(0)
        meta.update(render_get_path=wanted, render_get_status=200)
        return body, request, view, meta
    finally:
        e.page.remove_listener("response", listener)
        if not matching.done():
            matching.cancel()


async def create_vehicle(e, context, credentials, fixture, customer, member, token):
    actor, _ = await read_as(e, context, credentials, fixture, "sales", "customer-vehicles", "/api/customer-service/vehicles", "客户车辆档案")
    require(customer["owner_id"] == actor["id"], "车辆创建必须原客户销售本人")
    await click_form(e, '#main [data-act="care-vehicle-new"]', "登记客户车辆")
    await select_value(e, '#modal [name="customer_id"]', customer["id"], "明确同会员本人客户")
    identity = one(e, "group_members", member)["identity_id"]
    values = {"customer_id": customer["id"], "customer_identity_id": identity, "vin": "LHGCM8263" + token[:8].upper(),
        "plate": "套餐" + token[-6:], "model_name": "本轮套餐合成车型" + token,
        "source_reference": "合成会员本人到店提供17位VIN及独立车辆关系凭据-" + token, "confirmed": True}
    for name in ("customer_identity_id", "vin", "plate", "model_name", "source_reference"):
        await e.fill(f'#modal [name="{name}"]', str(values[name]), "填写明确原车辆关系：" + name)
    await checkbox(e, '#modal [name="confirmed"]', True, "本人核对同一会员客户及完整VIN")
    guard = Guard(e, "same_member_vehicle_create", actor, append={"care_customer_vehicles": 1, "group_identities": 1,
        "care_receipts": 1, "audit_logs": 1}, customer=customer["id"], member=member)
    body, request, shown, native = await submit_vehicle(e)
    vehicle = one(e, "care_customer_vehicles", body["vehicle"]["id"])
    require(request == {"request_id": request["request_id"], "values": values} and vehicle["customer_id"] == customer["id"]
            and vehicle["customer_identity_id"] == identity and vehicle["vin"] == values["vin"]
            and vehicle["created_by"] == actor["id"] and vehicle["identity_source"] == values["source_reference"]
            and all(shown["vehicle"][k] == vehicle[k] for k in ("id", "version", "customer_id", "vin", "plate", "model_name")), "新车关系不是同会员本人原输入")
    new_identity = one(e, "group_identities", vehicle["vehicle_identity_id"])
    require(new_identity["kind"] == "vehicle" and new_identity["canonical_key"] == values["vin"]
            and new_identity["created_by"] == actor["id"], "原VIN独立集团车辆身份不匹配")
    matching_vins = e.db.rows("SELECT id FROM care_customer_vehicles WHERE store_id=? AND vin=? ORDER BY id", (1, vehicle["vin"]))
    require([r["id"] for r in matching_vins] == [vehicle["id"]], "本次工位VIN锁须唯一指向本店新CV")
    receipt = e.db.rows("SELECT * FROM care_receipts WHERE request_key=?", (request["request_id"],))
    require(len(receipt) == 1 and receipt[0]["actor_id"] == actor["id"] and json.loads(receipt[0]["result"]) == body
            and receipt[0]["digest"] == canonical(["vehicle_create", values]), "原车辆回执摘要/结果不一致")
    native.update(guard=guard.finish(), receipt_id=receipt[0]["id"], new_vehicle_identity=new_identity)
    return vehicle, native


async def new_intake(e, context, credentials, fixture, customer, member, vehicle, resource, token):
    service, _ = await read_as(e, context, credentials, fixture, "service", "service-intake/appointments", R.INTAKE + "/appointments", "维修预约与到店")
    await click_form(e, '#main [data-act="intake-new"][data-mode="walk_in"]', "现场来访登记")
    label = " · ".join(str(v) for v in (customer["name"], customer["phone"], vehicle["plate"], vehicle["vin"]) if v)
    await live_choice(e, "customer_vehicle_id", vehicle["vin"], label, expected_value=vehicle["id"])
    await live_choice(e, "resource_id", resource["name"], resource["name"], expected_value=resource["id"])
    for field in ("starts_at", "ends_at"):
        value = await e.page.locator(f'#modal [name="{field}"]').input_value()
        await e.fill(f'#modal [name="{field}"]', value, "核对当前原业务时段")
    await e.fill('#modal [name="reason"]', "本会员实际到店办理原套餐一完整作业及一升材料", "记录本次明确现场诉求")
    guard = Guard(e, "same_member_walk_in", service, append={**FLOW, "flow_cases": 1, "flow_tasks": 1,
        "intake_appointments": 1, "intake_command_receipts": 1},
        update={"intake_resources": {resource["id"]: VERSION}}, customer=customer["id"], member=member,
        vehicle=vehicle["id"], resource=resource["id"], new_kind="service_intake")
    body, request, view, native = await MF.submit_created(e, R.INTAKE + "/appointments", R.INTAKE + "/appointments/", status=201, body_key=("id",))
    aid, cid = body["id"], body["case_id"]
    require(request["mode"] == "walk_in" and request["preset_id"] is None and request["customer_vehicle_id"] == vehicle["id"]
            and request["resource_id"] == resource["id"] and view["case_id"] == cid, "现场接待未引用同会员新车或错误套用快捷旧报价")
    native["guard"] = guard.finish()
    normalized = {k: value for k, value in request.items() if k != "request_id"}
    for field in ("starts_at", "ends_at"):
        normalized[field] = datetime.fromisoformat(normalized[field].replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")
    native["receipt"] = intake_receipt(guard, request, "appointment_create", normalized, body)
    owner_arrive = await handoff(e, context, credentials, fixture, cid, "intake_arrive", "service", member)
    arrival_file = await proof(e, context, credentials, fixture, "service", cid, member, "evidence", "package-arrival", token)
    service, _ = await read_as(e, context, credentials, fixture, "service", f"service-intake/appointments/{aid}", f"{R.INTAKE}/appointments/{aid}")
    await R.form(e, "arrive", intake=True)
    await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "现场逐位核对本次17位VIN")
    await e.fill('#modal [name="odometer_km"]', "12345", "记录本次明确合成现场里程")
    await MF.choose_file(e, arrival_file)
    before = one(e, "intake_appointments", aid)
    guard = Guard(e, "same_member_actual_arrival", service, append={**FLOW, "intake_arrivals": 1, "intake_command_receipts": 1, "flow_tasks": 1},
        update={**updates(e, (cid,), case_columns={"state"}), "intake_appointments": {aid: VERSION | {"status"}},
                "care_customer_vehicles": {vehicle["id"]: VERSION}}, cases={cid},
        customer=customer["id"], member=member, vehicle=vehicle["id"], resource=resource["id"])
    body, request, _, arrived = await submit(e, f"{R.INTAKE}/appointments/{aid}/actions/arrive", f"{R.INTAKE}/appointments/{aid}")
    require(request["version"] == before["version"] and request["values"] == {"checked_vin": vehicle["vin"], "odometer_km": 12345, "evidence_id": arrival_file["file"]["id"]}, "原到店当前版本/完整输入不一致")
    arrived["guard"] = guard.finish()
    arrived["receipt"] = intake_receipt(guard, request, "appointment_arrive", {"id": aid, "version": before["version"], **request["values"]}, body)
    arrival = subset(e, "intake_arrivals", "appointment_id", aid)
    require(len(arrival) == 1 and arrival[0]["checked_vin"] == vehicle["vin"] and arrival[0]["evidence_id"] == arrival_file["file"]["id"], "到店没有真实唯一原事实")
    owner_convert = await handoff(e, context, credentials, fixture, cid, "intake_convert", "service", member)
    service, _ = await read_as(e, context, credentials, fixture, "service", f"service-intake/appointments/{aid}", f"{R.INTAKE}/appointments/{aid}")
    await R.form(e, "convert", intake=True)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    await e.fill('#modal [name="due_date"]', day, "明确当前业务日预计交车")
    before = one(e, "intake_appointments", aid)
    guard = Guard(e, "same_member_convert_v4", service, append={"flow_cases": 1, "flow_tasks": 1, "flow_events": 3, "audit_logs": 3,
        "intake_command_receipts": 1, "intake_repair_contexts": 1, "intake_vehicle_bindings": 1},
        update={**updates(e, (cid,), case_columns={"state"}), "intake_appointments": {aid: VERSION | {"status", "repair_case_id"}}}, cases={cid},
        customer=customer["id"], member=member, vehicle=vehicle["id"], resource=resource["id"], new_kind="repair")
    body, request, _, converted = await submit(e, f"{R.INTAKE}/appointments/{aid}/actions/convert", f"{R.INTAKE}/appointments/{aid}")
    rid = body["repair_case_id"]
    require(request["version"] == before["version"] and request["values"] == {"due_date": day}, "原转换未用最新预约版本及真实业务日期")
    converted["guard"] = guard.finish()
    converted["receipt"] = intake_receipt(guard, request, "appointment_convert", {"id": aid, "version": before["version"], "due_date": day}, body)
    f = R.facts(e, rid)
    require(f["case"]["customer_id"] == customer["id"] and f["case"]["flow_version"] == 4 and f["case"]["state"] == "assessment"
            and not f["quotes"] and f["binding"][0]["customer_vehicle_id"] == vehicle["id"]
            and f["binding"][0]["customer_identity_id"] == one(e, "group_members", member)["identity_id"]
            and f["context"][0]["resource_id"] == resource["id"] and one(e, "flow_cases", cid)["state"] == "completed", "原现场转换未建立同会员未报价v4宿主")
    return rid, {"book": native, "arrive": arrived, "convert": converted, "appointment_id": aid, "intake_case_id": cid,
        "arrival": arrival[0], "binding": f["binding"][0], "context": f["context"][0], "files": [arrival_file],
        "task_owners": [owner_arrive, owner_convert]}


async def package_view(e, context, credentials, fixture, role, member=None):
    return await read_as(e, context, credentials, fixture, role,
        "repair-packages" + ("/" + str(member) if member else ""),
        f"{API}/members/{member}/purchases" if member else API + "/rules", "维修组合套餐")


async def create_rule(e, context, credentials, fixture, work, item, token, *, revision=1):
    actor, _ = await package_view(e, context, credentials, fixture, "service")
    await click_form(e, '#main [data-act="package-rule-new"]', "拟定售前套餐组件")
    values = {"code": "PK-" + token, "name": "本轮真实混合套餐" + token + "版" + str(revision),
        "allowed_store_ids": [1], "validity_days": 30, "refund_policy": "unused_before_expiry", "discount_bearer": "service_store",
        "components": [{"key": "component_1", "kind": "work", "name": work["name"], "unit": "job", "specification": "原作业两完整次，按合同单次履约",
            "quantity_milli": 2000, "credit_cents": 2000, "paid_cents": 1600, "settlement_cents": 1600},
            {"key": "component_2", "kind": "part", "name": item["name"], "unit": item["unit"], "specification": "原采购同批用料两升，按实际原位置领用",
             "quantity_milli": 2000, "credit_cents": 1000, "paid_cents": 800, "settlement_cents": 800}]}
    for name in ("code", "name"):
        await e.fill(f'#modal form > label [name="{name}"]', values[name], "填写新原规则：" + name)
    await e.fill('#modal [name="days"]', "30", "明确套餐原有效天数")
    await select_value(e, '#modal [name="refund"]', "unused_before_expiry", "仅原到期前未用量退款")
    await select_value(e, '#modal [name="bearer"]', "service_store", "明确原履约店承担优惠")
    stores = e.page.locator('#modal [name="store"]')
    for i in range(await stores.count()):
        target = stores.nth(i)
        store_id = await target.get_attribute("value")
        e.action("checkbox", "明确本次适用门店", store_id=store_id, checked=store_id == "1")
        await target.set_checked(store_id == "1")
    for i, component in enumerate(values["components"]):
        prefix = f'#modal [data-package-component]:nth-child({i + 1})'
        await select_value(e, prefix + ' [name="kind"]', component["kind"], "明确原组件类型")
        for name in ("name", "specification", "unit"):
            await e.fill(prefix + f' [name="{name}"]', component[name], "核对真实原组件：" + name)
        for name, value in (("quantity", "2.000"), ("credit", fen_text(component["credit_cents"])), ("paid", fen_text(component["paid_cents"]))):
            await e.fill(prefix + f' [name="{name}"]', value, "填写原精确数量及对价")
    guard = Guard(e, "mixed_rule_v" + str(revision), actor, append={"repair_package_rules": 1, "group_receipts": 1})
    body, request, _, native = await submit(e, API + "/rules", API + "/rules", status=201)
    rule = decoded(one(e, "repair_package_rules", body["id"]), "contract")
    contract = {k: values[k] for k in ("name", "allowed_store_ids", "validity_days", "refund_policy", "discount_bearer", "components")}
    contract.update(definition_version=1, issuer_store_id=1)
    require(request == {"request_id": request["request_id"], **values} and rule["rule_version"] == revision
            and rule["contract"] == contract and rule["digest"] == canonical(contract) and rule["actor_id"] == actor["id"], "原混合类型/CPS/冻结版本不匹配")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "repair_package:rule", values, body))
    await expect(e.page.locator("#main")).to_contain_text(rule["name"])
    return rule, native


async def decide_rule(e, context, credentials, fixture, rule, action):
    actor, _ = await package_view(e, context, credentials, fixture, "manager")
    require(actor["id"] != rule["actor_id"], "规则必须另一真实员工复核")
    await click_form(e, f'#main [data-act="package-rule-decide"][data-id="{rule["id"]}"][data-key="{action}"]', "核对套餐规则决定")
    reason = "独立核对原混合作业材料CPS、单位及未用原款政策" if action == "approve" else "停止此版新购买，保护已售原合同与实际履约"
    await e.fill('#modal [name="reason"]', reason, "记录原独立规则决定")
    guard = Guard(e, "mixed_rule_" + action, actor, append={"repair_package_rule_decisions": 1, "group_receipts": 1})
    body, request, _, native = await submit(e, f'{API}/rules/{rule["id"]}/actions/{action}', API + "/rules")
    require(request == {"request_id": request["request_id"], "reason": reason} and body["id"] == rule["id"], "原规则决定错版/参数")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, f'repair_package:rule:{rule["id"]}:{action}', {"reason": reason}, body))
    decision = guard.added["repair_package_rule_decisions"][0]
    require(decision["rule_id"] == rule["id"] and decision["action"] == action and decision["reason"] == reason, "原独立决定未落同规则")
    return {"decision": decision, "native": native}


async def map_rule(e, context, credentials, fixture, rule, source, component):
    actor, _ = await package_view(e, context, credentials, fixture, "manager")
    await click_form(e, f'#main [data-act="package-map"][data-id="{rule["id"]}"][data-key="{component["key"]}"]', "确认本店真实组件")
    await select_value(e, '#modal [name="source"]', f'{source["id"]} · {source.get("code", source.get("sku"))} · {source["name"]}', "明确本店真实原项目物资")
    reason = "现场核对同轮原主档、单位和本套餐冻结规格"
    await e.fill('#modal [name="reason"]', reason, "记录真实组件映射依据")
    values = {"component_key": component["key"], "source_id": source["id"], "reason": reason}
    guard = Guard(e, "mixed_mapping_" + component["key"], actor, append={"repair_package_mappings": 1, "group_receipts": 1})
    body, request, _, native = await submit(e, f'{API}/rules/{rule["id"]}/mappings', API + "/rules", status=201)
    mapping = decoded(one(e, "repair_package_mappings", body["id"]), "snapshot")
    require(request == {"request_id": request["request_id"], **values} and mapping["rule_id"] == rule["id"]
            and mapping["kind"] == component["kind"] and mapping["source_id"] == source["id"]
            and mapping["snapshot"] == {"code": source.get("code", source.get("sku")), "name": source["name"], "unit": component["unit"],
                "source_version": source["version"], "specification": component["specification"], "confirmation": reason}, "原组件映射来源/规格/版本失配")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "repair_package:map:" + str(rule["id"]), values, body))
    return {"mapping": mapping, "native": native}


async def account_choice(e, account):
    root = e.page.locator('#modal .lookup[data-kind="account"]')
    await expect(root).to_have_count(1)
    e.action("fill", "查找真实原收退款账户", value=account["name"])
    await root.locator('[role="combobox"]').fill(account["name"])
    option = root.get_by_role("option").filter(has_text=account["name"])
    await expect(option).to_have_count(1)
    await expect(option).to_be_visible()
    e.action("click", "明确选择原账户", account_id=account["id"])
    await option.click()
    await expect(e.page.locator('#modal [name="account_id"]')).to_have_value(str(account["id"]))


async def purchase(e, context, credentials, fixture, customer, member, case_id, rule):
    actor, _ = await package_view(e, context, credentials, fixture, "service", member)
    await click_form(e, '#main [data-act="package-purchase"]', "申请购买已批准套餐")
    case = one(e, "flow_cases", case_id)
    await select_value(e, '#modal [name="source"]', f'{case_id} · {case["number"]} · {case["title"]}', "选择同会员新未終态修单")
    await select_value(e, '#modal [name="rule"]', f'{rule["id"]} · {rule["name"]} / {rule["rule_version"]}', "明确本次新混合套餐")
    await e.fill('#modal [name="sets"]', "1", "购买明确一套原合同")
    guard = Guard(e, "mixed_purchase_propose", actor, append={**GROUP_FLOW, "repair_package_purchases": 1, "repair_package_purchase_events": 1, "flow_tasks": 1},
        update=updates(e, (case_id,), member=member), cases={case_id}, customer=customer["id"], member=member)
    body, request, shown, native = await submit(e, API + "/purchases", f"{API}/members/{member}/purchases", status=201)
    values = {"rule_id": rule["id"], "member_id": member, "case_id": case_id, "case_version": case["version"], "sets": 1}
    p = decoded(one(e, "repair_package_purchases", body["id"]), "contract")
    require(request == {"request_id": request["request_id"], **values} and p["status"] == "proposed" and p["amount_cents"] == 2400
            and p["cash_id"] is None and not subset(e, "repair_package_lots", "purchase_id", p["id"])
            and p["contract"] == {**rule["contract"], "rule_id": rule["id"], "rule_digest": rule["digest"], "sets": 1,
                "member_id": member, "customer_identity_id": one(e, "group_members", member)["identity_id"], "source_customer_id": customer["id"]}
            and p["digest"] == canonical(p["contract"]) and any(v["id"] == p["id"] for v in shown["items"]), "原购买未完整冻结或未实收即发行")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "repair_package:purchase", values, body))
    return p, native


async def purchase_action(e, context, credentials, fixture, customer, member, p_id, action, account, token):
    p = one(e, "repair_package_purchases", p_id)
    case_id, role = p["case_id"], "finance" if action == "issue" else "service"
    owner = await handoff(e, context, credentials, fixture, case_id, f'repair_package_{"pay" if action == "issue" else "authorize"}_{p_id}', role, member)
    category = "receipt" if action == "issue" else "authorization"
    file = await proof(e, context, credentials, fixture, role, case_id, member, category, "mixed-purchase-" + action, token)
    actor, _ = await package_view(e, context, credentials, fixture, role, member)
    p, case = one(e, "repair_package_purchases", p_id), one(e, "flow_cases", case_id)
    await click_form(e, f'#main [data-act="package-purchase-action"][data-id="{p_id}"][data-key="{action}"]',
        "登记套餐购买实际到账" if action == "issue" else "记录本版套餐客户授权")
    await MF.choose_file(e, file, category)
    values = {"case_version": case["version"], "evidence_id": file["file"]["id"]}
    if action == "issue":
        await account_choice(e, account)
        reference = "PK-IN-" + token
        await e.fill('#modal [name="reference"]', reference, "记录真实合成原购买流水号")
        values.update(account_id=account["id"], reference=reference, amount_cents=2400)
    append = {**GROUP_FLOW, "repair_package_purchase_events": 1}
    update = updates(e, (case_id,), member=member, account=account["id"] if action == "issue" else None)
    update["repair_package_purchases"] = {p_id: VERSION | {"status"} | ({"cash_id", "account_id"} if action == "issue" else set())}
    if action == "issue":
        append.update(repair_package_lots=2, cash_entries=1)
    else:
        append["flow_tasks"] = 1
    guard = Guard(e, "mixed_purchase_" + action, actor, append=append, update=update, cases={case_id}, customer=customer["id"], member=member, purchase=p_id)
    body, request, shown, native = await submit(e, f"{API}/purchases/{p_id}/actions/{action}", f"{API}/members/{member}/purchases")
    require(request == {"request_id": request["request_id"], "version": p["version"], "values": values}, "原购买双版本/原件/款项参数不一致")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, f"repair_package:purchase:{p_id}:{action}", {"version": p["version"], **values}, body), task_owner=owner, file=file)
    result = one(e, "repair_package_purchases", p_id)
    require(result["status"] == ("issued" if action == "issue" else "authorized") and result["version"] > p["version"], "原发行状态/版本未真实推进")
    if action == "issue":
        cash = one(e, "cash_entries", result["cash_id"])
        require(cash["direction"] == "in" and cash["category"] == "repair_package_purchase" and cash["amount_cents"] == 2400
                and cash["voucher_no"] == values["reference"] and cash["account"] == account["name"] and cash["created_by"] == actor["id"], "真实套餐原购买现金不匹配")
        lots = [decoded(r, "snapshot") for r in subset(e, "repair_package_lots", "purchase_id", p_id)]
        contract = json.loads(result["contract"])
        require(len(lots) == 2 and all({k: lot[k] for k in ("component_key", "quantity_milli", "credit_cents", "paid_cents", "settlement_cents")} ==
            {"component_key": c["key"], **{k: c[k] for k in ("quantity_milli", "credit_cents", "paid_cents", "settlement_cents")}}
            and lot["snapshot"] == c for lot, c in zip(lots, contract["components"])), "原批两个Lot数量/CPS/快照发行错误")
        native.update(cash=cash, lots=lots)
    else:
        require(result["cash_id"] is None and not subset(e, "repair_package_lots", "purchase_id", p_id), "授权被误记实收发行")
    require(any(v["id"] == p_id and v["status"] == result["status"] for v in shown["items"]), "前端购买状态与DB不匹配")
    return result, native


def package_facts(e, purchase_id, case_id):
    p = decoded(one(e, "repair_package_purchases", purchase_id), "contract")
    value = {"purchase": p, "purchase_events": subset(e, "repair_package_purchase_events", "purchase_id", purchase_id),
        "lots": [decoded(r, "snapshot") for r in subset(e, "repair_package_lots", "purchase_id", purchase_id)],
        "holds": [decoded(r, "spans") for r in subset(e, "repair_package_holds", "case_id", case_id)],
        "entries": [decoded(r, "spans") for r in subset(e, "repair_package_entries", "case_id", case_id)],
        "links": subset(e, "repair_package_payment_links", "case_id", case_id),
        "reservations": subset(e, "repair_package_reservation_links", "case_id", case_id),
        "quote_snapshots": [decoded(r, "contract") for r in subset(e, "repair_package_quote_snapshots", "case_id", case_id)],
        "refunds": [decoded(r, "selections") for r in subset(e, "repair_package_refunds", "purchase_id", purchase_id)]}
    value["settlements"] = [s for link in value["links"] for s in subset(e, "repair_package_settlements", "entry_id", link["entry_id"])]
    value["refund_claims"] = [decoded(c, "spans") for refund in value["refunds"] for c in subset(e, "repair_package_refund_claims", "refund_id", refund["id"])]
    value["cash"] = [one(e, "cash_entries", p["cash_id"])] if p["cash_id"] else []
    value["cash"].extend(one(e, "cash_entries", r["cash_id"]) for r in value["refunds"] if r["cash_id"])
    return value


async def package_quote(e, context, credentials, fixture, customer, member, case_id, purchase_id, item, work):
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_quote", "service", member)
    actor, view = await package_view(e, context, credentials, fixture, "service", member)
    p = next(v for v in view["items"] if v["id"] == purchase_id)
    buttons = e.page.locator(f'#main [data-act="package-use"][data-id="{purchase_id}"]')
    require(len(p["lots"]) == 2 and all(l["available_milli"] == 2000 for l in p["lots"]), "消费前原Lot非完整发行未占量")
    await expect(buttons).to_have_count(2)
    await expect(buttons.first).to_be_visible()
    e.action("click", "从明确购买批次进入真实修单选择", purchase_id=purchase_id)
    await buttons.first.click()
    await expect(e.page.locator("#modal-title")).to_have_text("选择本店实际维修工单")
    case = one(e, "flow_cases", case_id)
    choice = e.page.locator('#modal [name="choice"]')
    choice_label = case["number"] + " · " + case["title"]
    option = choice.locator("option").filter(has_text=choice_label)
    await expect(option).to_have_count(1)
    await expect(option).to_have_text(choice_label)
    choice_value = await option.get_attribute("value")
    require(choice_value is not None and choice_value.isdecimal(), "原修单选择须有当前候选索引")
    e.action("select", "选择同会员本次新未报价修单", value=choice_value, label=choice_label)
    await choice.select_option(label=choice_label)
    await expect(choice).to_have_value(choice_value)
    await expect(choice.locator("option:checked")).to_have_text(choice_label)
    await e.click('#modal form button[type="submit"]', "核对原修单后继续原套餐报价")
    await expect(e.page.locator("#modal-title")).to_have_text("核对原套餐及新增自费")
    for i in range(2):
        await e.fill(f'#modal [name="q{i}"]', "1.000", "本次明确履约一完整次或一升")
    await e.fill('#modal [name="discount"]', "0.00", "原套餐不再重复折扣")
    reason = "本次原会员实际一完整作业及一升原材料，剩余原批未用另行退款"
    await e.fill('#modal [name="reason"]', reason, "明确当前套餐维修范围")
    if await e.page.locator('#modal [name="member_pricing_rule"]').count():
        await select_value(e, '#modal [name="member_pricing_rule"]', "", "不另套用会员价于原套餐组件")
    lots = subset(e, "repair_package_lots", "purchase_id", purchase_id)
    guard = Guard(e, "mixed_original_quote_hold", actor,
        append={**REPAIR_FLOW, "repair_quotes": 1, "repair_lines": 2, "flow_tasks": 1,
            "repair_package_holds": 2, "repair_package_reservation_links": 2, "repair_package_quote_snapshots": 1},
        update=updates(e, (case_id,), member=member, lots=[r["id"] for r in lots], case_columns={"state", "data"}), cases={case_id}, customer=customer["id"],
        member=member, item=item["id"], work=work["id"], lots=[r["id"] for r in lots], purchase=purchase_id)
    body, request, shown, native = await submit(e, f"{API}/orders/{case_id}/quote", f"{R.REPAIR}/{case_id}")
    require(request["version"] == case["version"] and request["values"]["reason"] == reason and request["values"]["discount_cents"] == 0
            and len(request["values"]["lines"]) == 2 and "member_pricing" not in request["values"], "原套餐报价当前CAS/额外收费/重复优惠错误")
    expected = []
    for lot in lots:
        snapshot = json.loads(lot["snapshot"])
        mapping = next(r for r in subset(e, "repair_package_mappings", "rule_id", one(e, "repair_package_purchases", purchase_id)["rule_id"])
                       if r["component_key"] == lot["component_key"])
        expected.append({"kind": snapshot["kind"], "source_id": mapping["source_id"], "quantity_milli": 1000,
            "unit_price_cents": lot["credit_cents"] // 2, "package_lot_id": lot["id"], "package_lot_version": lot["version"]})
    require(request["values"]["lines"] == expected, "原Quote行非原Lot当前版/真实映射/基价/数量")
    normalized = {"purpose": "service", "retained_amount_cents": None, "package_retained": None, **request["values"]}
    normalized["lines"] = [{"line_key": None, **line} for line in expected]
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, case_id, "repair_v3_quote",
        {"id": case_id, "version": case["version"], "values": normalized}), task_owner=owner)
    repair, package = R.facts(e, case_id), package_facts(e, purchase_id, case_id)
    require(body["id"] == shown["id"] == case_id and repair["case"]["state"] == "approval" and len(repair["quotes"]) == 1
            and repair["quotes"][0]["amount_cents"] == 1500 and len(package["holds"]) == len(package["reservations"]) == 2
            and len(package["quote_snapshots"]) == 1 and not package["entries"] and not package["links"], "报价占额被误计消费或现金")
    snap = package["quote_snapshots"][0]
    require(snap["digest"] == canonical(snap["contract"]) and snap["quote_id"] == repair["quotes"][0]["id"], "原套餐QuoteSnapshot摘要与同版报价不符")
    for hold in package["holds"]:
        line = one(e, "repair_lines", hold["line_id"])
        link = next(v for v in package["reservations"] if v["hold_id"] == hold["id"])
        require(hold["status"] == link["status"] == "reserved" and hold["spans"] == [[0, 1000]] and hold["quantity_milli"] == 1000
                and hold["line_key"] == line["line_key"] and line["quantity_milli"] == 1000
                and hold["credit_cents"] == link["amount_cents"] == line["amount_cents"]
                and hold["paid_cents"] == hold["settlement_cents"] == link["recognized_cents"]
                and hold["digest"] == canonical({"quote_digest": repair["quotes"][0]["digest"], "lot_id": hold["lot_id"], "spans": hold["spans"],
                    **{k: hold[k] for k in ("quantity_milli", "credit_cents", "paid_cents", "settlement_cents")}}), "原Hold/区间/分摊/ReservationLink未绑定真实当前行")
    await expect(e.page.locator("#main h1")).to_have_text(repair["case"]["title"])
    return repair["quotes"][0], {"native": native, "package": package, "lines": repair["lines"]}


async def repair_read(e, context, credentials, fixture, role, case_id):
    actor, view = await read_as(e, context, credentials, fixture, role, f"repair-orders/{case_id}", f"{R.REPAIR}/{case_id}")
    case = one(e, "flow_cases", case_id)
    require(all(view[k] == case[k] for k in ("id", "version", "state", "customer_id", "flow_version")), "原维修详情与当前DB/CAS不同")
    if role in ("inventory", "technician"):
        require("amount_cents" not in view and "cost_cents" not in view, "施工或库管泄漏财务字段")
    return actor, view


async def repair_command(e, fixture, customer, member, case_id, p_id, action, actor, *, vehicle, resource, item, points=None):
    before = R.facts(e, case_id)
    lots = subset(e, "repair_package_lots", "purchase_id", p_id)
    append = {**REPAIR_FLOW, "flow_tasks": {"price_approve": 1, "authorize": 1, "start": 1, "issue": 0,
        "finish": 1, "quality": 1, "allocate": (0, 2), "release": 0}[action]}
    balances = subset(e, "warehouse_balances", "item_id", item["id"])
    append.update({"price_approve": {"repair_price_approvals": 1}, "authorize": {"repair_authorizations": 1, "membership_points_claims": 1},
        "start": {"intake_resource_uses": 1}, "issue": {"repair_stock": 1, "flow_stock_moves": 1, "warehouse_entries": (1, len(balances))},
        "finish": {}, "quality": {"repair_quality": 1}, "allocate": {"repair_settlements": 1, "repair_allocations": 1},
        "release": {"intake_resource_uses": 1}}[action])
    update = updates(e, (case_id,), member=member if action in {"authorize", "release"} else None,
                     lots=[r["id"] for r in lots] if action == "authorize" else ())
    update["flow_cases"] = {case_id: VERSION | {"price_approve": {"state"}, "authorize": {"state", "data", "amount_cents"},
        "start": {"data"}, "issue": set(), "finish": {"state", "data"}, "quality": {"state"},
        "allocate": {"data", "cost_cents"}, "release": {"state", "data", "completed_date"}}[action]}
    if action == "start":
        update["intake_resources"] = {resource["id"]: VERSION | {"active_case_id"}}
        update["care_customer_vehicles"] = {vehicle["id"]: VERSION}
    if action == "release":
        update["intake_resources"] = {resource["id"]: VERSION | {"active_case_id"}}
        update["care_customer_vehicles"] = {vehicle["id"]: VERSION}
        claims = subset(e, "membership_points_claims", "case_id", case_id)
        require(len(claims) == 1, "释放前缺唯一冻结消费积分claim")
        if claims[0]["rule_id"] is not None:
            require(points is not None and claims[0]["rule_id"] in points["membership_rule_ids"], "有效积分缺同轮passed有限来源")
            append.update(membership_points_changes=1, benefit_wallets=1, benefit_entries=1)
            update["membership_points_claims"] = {claims[0]["id"]: VERSION | {"basis_cents", "target_units"}}
    if action == "issue":
        update["flow_items"] = {item["id"]: VERSION | {"quantity_milli", "inventory_value_cents", "unit_cost_cents"}}
        prepared = [a for a in subset(e, "warehouse_allocations", "case_id", case_id) if a["status"] == "prepared"]
        require(len(prepared) == 1, "本次实际发料缺唯一准备")
        line = subset(e, "warehouse_allocation_lines", "allocation_id", prepared[0]["id"])
        require(len(line) == 1, "本次原领料只准一个明确实位")
        update["warehouse_balances"] = {r["id"]: VERSION | {"value_cents"} | ({"quantity_milli"} if r["location_id"] == line[0]["location_id"] else set()) for r in balances}
        update["warehouse_allocations"] = {r["id"]: VERSION | {"status", "stock_move_id"} for r in subset(e, "warehouse_allocations", "case_id", case_id)}
    guard = Guard(e, "mixed_repair_" + action, actor, append=append, update=update, cases={case_id}, customer=customer["id"],
        member=member, item=item["id"], vehicle=vehicle["id"], resource=resource["id"], purchase=p_id, lots=[r["id"] for r in lots])
    body, request, shown, native = await submit(e, f"{R.REPAIR}/{case_id}/actions/{action}", f"{R.REPAIR}/{case_id}")
    require(request["version"] == before["case"]["version"] and body["id"] == shown["id"] == case_id
            and body["version"] > before["case"]["version"], "真实维修动作同单/当前版不符")
    values = dict(request["values"])
    if action == "allocate":
        values["allocations"] = [{"payer_id": None, "payer_name": "", **r} for r in values["allocations"]]
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, case_id, "repair_v3_" + action,
        {"id": case_id, "version": request["version"], "values": values}), submitted_values=request["values"])
    after = R.facts(e, case_id)
    native["event"] = R.event_added(before, after, "repair_v4_" + action, actor)
    for family in ("quotes", "lines", "approvals", "authorizations", "stock", "quality", "settlements", "allocations", "moves", "payments"):
        require(after[family][:len(before[family])] == before[family], "维修旧历史被覆盖：" + family)
    await expect(e.page.locator("#main h1")).to_have_text(after["case"]["title"])
    return after, shown, native


async def prepare_material(e, actor, customer, member, case_id, item, warehouse, location):
    prior, case = R.material_facts(e, item["id"]), one(e, "flow_cases", case_id)
    await e.click('#modal [data-prep-open]', "展开本次原实际领料库位准备")
    section = e.page.locator(f'#modal [data-prep-item="{item["id"]}"]')
    await expect(section).to_be_visible()
    await expect(section.locator("[data-prep-location]")).to_have_count(1)
    e.action("fill", "查找有限同轮领料位置", value=location["name"])
    await section.locator('.lookup [role="combobox"]').fill(location["name"])
    option = section.get_by_role("option", name=warehouse["name"] + " · " + location["name"], exact=True)
    await expect(option).to_be_visible()
    e.action("click", "选择明确本原位", location_id=location["id"])
    await option.click()
    await expect(section.locator("[data-prep-bin]")).to_have_value(str(location["id"]))
    await e.fill(f'#modal [data-prep-item="{item["id"]}"] [data-prep-quantity]', "1.000", "准备精确一升原材料")
    guard = Guard(e, "mixed_material_prepare", actor, append={**REPAIR_FLOW, "warehouse_allocations": 1, "warehouse_allocation_lines": 1},
        update={"flow_cases": {case_id: VERSION}}, cases={case_id}, customer=customer["id"], member=member, item=item["id"])
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"/api/warehouse/allocations/{case_id}") as pending:
        await e.click('#modal [data-prep-save]', "保存原位置准备，尚不实际发料")
    response = await pending.value
    body = await response.json()
    native, request = await R.metadata(e, response, 1)
    values = {"item_id": item["id"], "quantity_milli": -1000, "purpose": "repair_issue_v3",
              "locations": [{"location_id": location["id"], "quantity_milli": 1000}]}
    require(response.status == 200 and body["prepared"] is True and request == {"request_id": request["request_id"], "version": case["version"], "values": values}, "原库位準备方向/数量/当前版不符")
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, case_id, "warehouse_allocation", {"id": case_id, "version": case["version"], **values}))
    require(R.material_facts(e, item["id"]) == prior, "准备错误地产生材料出库")
    await expect(e.page.locator('#modal [data-prep-status]')).to_have_text("库位已保存。核对本表后，再确认实际收发。")
    allocation = guard.added["warehouse_allocations"][0]
    line = guard.added["warehouse_allocation_lines"][0]
    require(allocation["quantity_milli"] == -1000 and allocation["purpose"] == "repair_issue_v3" and line["location_id"] == location["id"]
            and line["quantity_milli"] == 1000 and line["allocation_id"] == allocation["id"], "原准备未绑定明确实位")
    return {"native": native, "allocation": allocation, "line": line, "physical_unchanged": True}


async def fulfil(e, context, credentials, fixture, customer, member, case_id, purchase_id, quote,
                 vehicle, resource, item, warehouse, location, points, token):
    evidence, roles = {}, []
    qid = quote["id"]
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_price_" + str(qid), "manager", member)
    manager, _ = await repair_read(e, context, credentials, fixture, "manager", case_id)
    await R.form(e, "price_approve")
    await e.fill('#modal [name="minimum"]', "15.00", "独立主管确认本版原面值最低价1500分")
    await checkbox(e, '#modal [name="allow_below_minimum"]', False, "不批准额外低价例外")
    await e.fill('#modal [name="reason"]', "原组件合同基价和本次实际1000milli数量逐项独立核对", "填写真实独立核价依据")
    f, _, approved = await repair_command(e, fixture, customer, member, case_id, purchase_id, "price_approve", manager,
        vehicle=vehicle, resource=resource, item=item)
    require(f["approvals"][0]["actor_id"] == manager["id"] != quote["created_by"] and f["approvals"][0]["minimum_total_cents"] == 1500, "原套餐维修核价未独立")
    evidence["price_approval"], roles = approved, [owner]
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_authorize_" + str(qid), "service", member)
    file = await proof(e, context, credentials, fixture, "service", case_id, member, "authorization", "mixed-current-quote-auth", token)
    service, _ = await repair_read(e, context, credentials, fixture, "service", case_id)
    await R.form(e, "authorize")
    await MF.choose_file(e, file, "authorization")
    f, _, authorized = await repair_command(e, fixture, customer, member, case_id, purchase_id, "authorize", service,
        vehicle=vehicle, resource=resource, item=item)
    require(len(f["authorizations"]) == 1 and f["authorizations"][0]["quote_id"] == qid
            and f["authorizations"][0]["quote_digest"] == quote["digest"] and f["authorizations"][0]["evidence_id"] == file["file"]["id"], "本版维修授权未绑定真实报价摘要及原件")
    claim = subset(e, "membership_points_claims", "case_id", case_id)
    require(len(claim) == 1 and claim[0]["member_id"] == member and claim[0]["target_units"] == claim[0]["basis_cents"] == 0,
            "本次同会员消费积分claim缺失或尚未接车即赠分")
    if points:
        require(claim[0]["rule_id"] in points["membership_rule_ids"], "本次授权未冻结同轮真实有效积分会期")
    else:
        require(claim[0]["rule_id"] is None, "无同轮通过会期却继承静态消费奖励")
    evidence["authorization"] = {"native": authorized, "file": file, "points_claim": claim[0]}
    roles.append(owner)
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_work", "technician", member)
    technician, _ = await repair_read(e, context, credentials, fixture, "technician", case_id)
    await R.form(e, "start")
    await e.fill('#modal [name="result"]', "技师现场核车后实际进位执行原合同一完整次作业", "技师确认真实开工")
    f, _, started = await repair_command(e, fixture, customer, member, case_id, purchase_id, "start", technician,
        vehicle=vehicle, resource=resource, item=item)
    require(one(e, "intake_resources", resource["id"])["active_case_id"] == case_id
            and f["resource_uses"][0]["action"] == "acquire" and f["case"]["data"]["started"], "原实际进位或施工开始未发生")
    evidence["start"] = started
    roles.append(owner)
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_issue", "inventory", member)
    file = await proof(e, context, credentials, fixture, "inventory", case_id, member, "evidence", "mixed-actual-material", token)
    inventory, _ = await repair_read(e, context, credentials, fixture, "inventory", case_id)
    await R.form(e, "issue")
    before_stock = R.material_facts(e, item["id"])
    part = next(line for line in f["lines"] if line["kind"] == "part")
    label = f'{part["code"]} · {part["name"]} · 尚可领 1'
    await live_choice(e, "line_label", part["name"], label, expected_value=label)
    await e.fill('#modal [name="quantity"]', "1.000", "本人确认原授权一升实际发料")
    await MF.choose_file(e, file)
    preparation = await prepare_material(e, inventory, customer, member, case_id, item, warehouse, location)
    f, _, issued = await repair_command(e, fixture, customer, member, case_id, purchase_id, "issue", inventory,
        vehicle=vehicle, resource=resource, item=item)
    stock, move = f["stock"][0], f["moves"][0]
    qty, value = before_stock["item"]["quantity_milli"], before_stock["item"]["inventory_value_cents"]
    cost = value if qty == 1000 else (2 * value * 1000 + qty) // (2 * qty)
    current = R.material_facts(e, item["id"])
    require(len(f["stock"]) == len(f["moves"]) == 1 and stock["quantity_milli"] == 1000 and stock["value_cents"] == cost
            and stock["line_key"] == part["line_key"] and stock["stock_move_id"] == move["id"] and stock["original_id"] is None
            and move["quantity_milli"] == -1000 and move["value_cents"] == -cost and move["purpose"] == "repair_issue_v3"
            and current["item"]["quantity_milli"] == qty - 1000 and current["item"]["inventory_value_cents"] == value - cost
            and one(e, "warehouse_allocations", preparation["allocation"]["id"])["stock_move_id"] == move["id"], "原套餐实际领料/净量/平均成本/实位不守恒")
    fresh_entries = current["entries"][len(before_stock["entries"]):]
    require(fresh_entries and sum(r["quantity_milli"] for r in fresh_entries) == -1000 and sum(r["value_cents"] for r in fresh_entries) == -cost
            and all(r["quantity_milli"] == 0 or r["quantity_milli"] == -1000
                and one(e, "warehouse_balances", r["balance_id"])["location_id"] == location["id"] for r in fresh_entries), "原领料位置及全库位平均成本再分摊流水不匹配")
    evidence["material"] = {"native": issued, "file": file, "prepare": preparation, "stock": stock, "move": move,
                            "warehouse_entries": fresh_entries, "actual_cost_cents": cost}
    roles.append(owner)
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_work", "technician", member)
    technician, _ = await repair_read(e, context, credentials, fixture, "technician", case_id)
    await R.form(e, "finish")
    await e.fill('#modal [name="result"]', "实际完成一完整原作业和一升原净领材料，交独立服务顾问质检", "技师记录真实施工完成")
    f, _, finished = await repair_command(e, fixture, customer, member, case_id, purchase_id, "finish", technician,
        vehicle=vehicle, resource=resource, item=item)
    require(f["case"]["state"] == "quality" and f["case"]["data"]["finish_result"], "原实际施工完成缺失")
    evidence["finish"] = finished
    roles.append(owner)
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_quality", "service", member)
    file = await proof(e, context, credentials, fixture, "service", case_id, member, "inspection", "mixed-quality", token)
    service, _ = await repair_read(e, context, credentials, fixture, "service", case_id)
    require(service["id"] != technician["id"], "施工及质检须真实不同岗位")
    await R.form(e, "quality")
    await e.fill('#modal [name="result"]', "原一完整作业与净用料一致，实际安全交接检查合格", "服务顾问记录实际独立质检")
    await select_value(e, '#modal [name="outcome"]', "合格", "明确实际检查合格")
    await R.file_choice(e, "evidence_id", file)
    f, _, quality = await repair_command(e, fixture, customer, member, case_id, purchase_id, "quality", service,
        vehicle=vehicle, resource=resource, item=item)
    require(len(f["quality"]) == 1 and f["quality"][0]["passed"] and f["quality"][0]["evidence_id"] == file["file"]["id"]
            and f["quality"][0]["quote_id"] == qid and f["case"]["state"] == "settling", "原质检并非当前报价实际事实")
    evidence["quality"] = {"native": quality, "file": file, "fact": f["quality"][0]}
    roles.append(owner)
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_allocate", "manager", member)
    file = await proof(e, context, credentials, fixture, "manager", case_id, member, "evidence", "mixed-payer", token)
    manager, _ = await repair_read(e, context, credentials, fixture, "manager", case_id)
    await R.form(e, "allocate")
    await e.click('#modal [data-repair-customer-all]', "明确本次原客户全额1500面值承担")
    day = one(e, "flow_cases", case_id)["business_date"]
    await e.fill('#modal [name="due_customer"]', day, "明确当前业务日原客户承担期限")
    await e.fill('#modal [name="labor_cost"]', "0.00", "本次明确合成人工成本零，材料成本独立沿原批")
    await R.file_choice(e, "evidence", file)
    f, view, allocated = await repair_command(e, fixture, customer, member, case_id, purchase_id, "allocate", manager,
        vehicle=vehicle, resource=resource, item=item)
    require(len(f["allocations"]) == len(f["settlements"]) == 1 and f["allocations"][0]["payer_type"] == "customer"
            and f["allocations"][0]["payer_name"] == customer["name"] and f["allocations"][0]["amount_cents"] == 1500
            and f["settlements"][0]["labor_cost_cents"] == 0 and f["case"]["cost_cents"] == cost
            and not f["cash"] and view["customer_due_cents"] == 0 and view["receivable_cents"] == 1500,
            "原承担/成本冻结不符：套餐占额保留待核销，不能冒充实际实付")
    evidence["allocation"] = {"native": allocated, "file": file, "fact": f["allocations"][0], "settlement": f["settlements"][0]}
    roles.append(owner)
    return f, {"steps": evidence, "task_owners": roles, "actual_material_cost_cents": cost}


async def capture_and_release(e, context, credentials, fixture, customer, member, case_id, p_id, vehicle, resource, item, points, token):
    file = await proof(e, context, credentials, fixture, "finance", case_id, member, "evidence", "mixed-actual-capture", token)
    actor, _ = await repair_read(e, context, credentials, fixture, "finance", case_id)
    before = package_facts(e, p_id, case_id)
    case = one(e, "flow_cases", case_id)
    await click_form(e, '#main [data-act="package-capture"]', "按本版实际履约核销原组件")
    await MF.choose_file(e, file)
    lots = [r["id"] for r in before["lots"]]
    update = updates(e, (case_id,), member=member, lots=lots, case_columns={"state"})
    update["repair_package_holds"] = {r["id"]: VERSION | {"status"} for r in before["holds"]}
    update["repair_package_reservation_links"] = {r["id"]: VERSION | {"status"} for r in before["reservations"]}
    guard = Guard(e, "mixed_original_capture", actor, append={**GROUP_FLOW, "repair_package_entries": 2,
        "repair_package_payment_links": 2, "repair_package_settlements": 4}, update=update, cases={case_id}, customer=customer["id"],
        member=member, item=item["id"], vehicle=vehicle["id"], resource=resource["id"], purchase=p_id, lots=lots)
    body, request, view, native = await submit(e, f"{API}/orders/{case_id}/capture", f"{R.REPAIR}/{case_id}")
    values = {"evidence_id": file["file"]["id"]}
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}
            and body["case_id"] == case_id and body["credit_cents"] == 1500 and body["case_version"] > case["version"], "本版原核销请求/结果不一致")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "repair_package:capture:" + str(case_id),
        {"version": case["version"], **values}, body), file=file)
    captured = package_facts(e, p_id, case_id)
    require(captured["cash"] == before["cash"] and len(captured["entries"]) == len(captured["links"]) == 2
            and len(captured["settlements"]) == 4 and all(h["status"] == "captured" for h in captured["holds"])
            and all(h["status"] == "captured" for h in captured["reservations"])
            and view["customer_due_cents"] == view["receivable_cents"] == 0, "核销重复现金、链接不完整或原客户款未结清")
    for entry in captured["entries"]:
        hold = next(h for h in before["holds"] if h["id"] == entry["hold_id"])
        link = next(p for p in captured["links"] if p["entry_id"] == entry["id"])
        settlements = [s for s in captured["settlements"] if s["entry_id"] == entry["id"]]
        require(entry["purpose"] == link["purpose"] == "capture" and entry["spans"] == [[0, 1000]]
                and entry["original_id"] is None and entry["refund_id"] is None and entry["evidence_id"] == file["file"]["id"]
                and all(entry[k] == hold[k] for k in ("quantity_milli", "credit_cents", "paid_cents", "settlement_cents"))
                and link["amount_cents"] == entry["credit_cents"] and link["recognized_cents"] == entry["paid_cents"]
                and {(s["side"], s["amount_cents"]) for s in settlements} == {("center", -entry["settlement_cents"]), ("store", entry["settlement_cents"])}, "原Capture Entry/正区间/CPS及双边内部结算不守恒")
    require(sum(r["credit_cents"] for r in captured["entries"]) == 1500
            and sum(r["paid_cents"] for r in captured["entries"]) == sum(r["settlement_cents"] for r in captured["entries"]) == 1200,
            "本次实际原组件C/P/S不是1500/1200/1200")
    owner = await handoff(e, context, credentials, fixture, case_id, "repair_release", "service", member)
    file = await proof(e, context, credentials, fixture, "service", case_id, member, "evidence", "mixed-customer-departure", token)
    service, _ = await repair_read(e, context, credentials, fixture, "service", case_id)
    await R.form(e, "release")
    await MF.choose_file(e, file)
    f, _, released = await repair_command(e, fixture, customer, member, case_id, p_id, "release", service,
        vehicle=vehicle, resource=resource, item=item, points=points)
    require(f["case"]["state"] == "completed" and f["case"]["data"]["released_date"] == f["case"]["completed_date"]
            and one(e, "intake_resources", resource["id"])["active_case_id"] is None
            and [r["action"] for r in f["resource_uses"]] == ["acquire", "release"] and not any(t["status"] == "open" for t in f["tasks"]), "原实际接车/工位释放/任务完结不成立")
    claim = subset(e, "membership_points_claims", "case_id", case_id)[0]
    changes = subset(e, "membership_points_changes", "claim_id", claim["id"])
    points_evidence = {"claim": claim, "changes": changes}
    if claim["rule_id"] is not None:
        rule = one(e, "membership_rules", claim["rule_id"])
        target = 1200 * rule["points_numerator"] // rule["points_denominator_fen"]
        require(points is not None and len(changes) == 1 and claim["basis_cents"] == changes[0]["basis_cents"] == 1200
                and claim["target_units"] == changes[0]["units"] == target and target == 12
                and changes[0]["evidence_id"] == file["file"]["id"], "实际履约P1200未按同轮冻结规则获12分")
        wallet = one(e, "benefit_wallets", changes[0]["wallet_id"])
        entries = subset(e, "benefit_entries", "case_id", case_id)
        require(len(entries) == 1 and entries[0]["wallet_id"] == wallet["id"] and entries[0]["purpose"] == wallet["source_kind"] == "grant"
                and entries[0]["units"] == wallet["initial_units"] == wallet["balance_units"] == 12 and wallet["reserved_units"] == 0
                and wallet["rule_id"] == rule["points_benefit_rule_id"] and wallet["source_case_id"] == case_id
                and entries[0]["cash_id"] is None, "真正消费积分原批缺履约来源或冒充再次现金")
        points_evidence.update(wallet=wallet, entry=entries[0])
    else:
        require(not changes and claim["basis_cents"] == claim["target_units"] == 0, "无原会期规则仍制造消费积分")
    require(package_facts(e, p_id, case_id)["cash"] == captured["cash"], "交车重复原套餐现金")
    return {"capture": native, "capture_facts": captured, "release": released, "release_file": file,
            "release_task_owner": owner, "repair": f, "points": points_evidence}


async def refund_component(e, context, credentials, fixture, customer, member, p_id, lot_id, amount, account, token):
    p = one(e, "repair_package_purchases", p_id)
    cid = p["case_id"]
    file = await proof(e, context, credentials, fixture, "service", cid, member, "evidence", "mixed-refund-request-" + str(lot_id), token)
    actor, view = await package_view(e, context, credentials, fixture, "service", member)
    shown = next(r for r in view["items"] if r["id"] == p_id)
    lot = next(l for l in shown["lots"] if l["id"] == lot_id)
    require(lot["available_milli"] == 1000, "退款申请只准本批实际剩余一完整量")
    p, case = one(e, "repair_package_purchases", p_id), one(e, "flow_cases", cid)
    await click_form(e, f'#main [data-act="package-purchase-action"][data-id="{p_id}"][data-key="refund_request"]', "申请未用组件原款退款")
    await select_value(e, '#modal [name="component"]', f'{lot_id} · {lot["name"]} · 当前未占 1 {lot["unit"]}', "明确本次单一原批未用组件")
    await e.fill('#modal [name="quantity"]', "1.000", "只退本原批真实未用1000milli")
    reason = "原已履约区间[0,1000]保留，仅未用[1000,2000]原分摊实退"
    await e.fill('#modal [name="reason"]', reason, "记录原未用组件退款依据")
    await MF.choose_file(e, file)
    values = {"case_version": case["version"], "selections": [{"lot_id": lot_id, "quantity_milli": 1000}], "reason": reason, "evidence_id": file["file"]["id"]}
    guard = Guard(e, "mixed_unused_refund_request_" + str(lot_id), actor, append={**GROUP_FLOW, "repair_package_refunds": 1, "flow_tasks": 1},
        update=updates(e, (cid,), member=member, purchase=p_id), cases={cid}, customer=customer["id"], member=member, purchase=p_id, lots={lot_id})
    body, request, _, native = await submit(e, f"{API}/purchases/{p_id}/actions/refund_request", f"{API}/members/{member}/purchases")
    require(request == {"request_id": request["request_id"], "version": p["version"], "values": values}, "原退款申请双CAS/组件原批/精确量不一致")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "repair_package:refund_request:" + str(p_id), {"version": p["version"], **values}, body), file=file)
    rid = body["id"]
    refund = decoded(one(e, "repair_package_refunds", rid), "selections")
    original_lot = one(e, "repair_package_lots", lot_id)
    selection = {"lot_id": lot_id, "spans": [[1000, 2000]], "quantity_milli": 1000,
        **{k: original_lot[k] - original_lot[k] // 2 for k in ("credit_cents", "paid_cents", "settlement_cents")}}
    require(refund["status"] == "requested" and refund["requested_by"] == actor["id"] and refund["amount_cents"] == amount
            and refund["selections"] == [selection] and refund["cash_id"] is None
            and not subset(e, "repair_package_refund_claims", "refund_id", rid), "申请未冻结正确原剩余区间或提前占额付款")
    owner_review = await handoff(e, context, credentials, fixture, cid, "repair_package_refund_review_" + str(rid), "manager", member)
    manager, _ = await package_view(e, context, credentials, fixture, "manager", member)
    require(manager["id"] != refund["requested_by"], "原未用退款必须不同真实员工批准")
    refund, p, case = one(e, "repair_package_refunds", rid), one(e, "repair_package_purchases", p_id), one(e, "flow_cases", cid)
    await click_form(e, f'#main [data-act="package-refund"][data-id="{rid}"][data-purchase="{p_id}"][data-key="approve"]', "核对未用组件退款")
    decision = "独立核对原未用区间及原购买对价，批准该单一原组件退款"
    await e.fill('#modal [name="reason"]', decision, "记录原独立退款复核")
    values = {"case_version": case["version"], "reason": decision}
    update = updates(e, (cid,), member=member, purchase=p_id, lots={lot_id})
    update["repair_package_refunds"] = {rid: VERSION | {"status", "approved_by"}}
    guard = Guard(e, "mixed_unused_refund_approve_" + str(rid), manager,
        append={**GROUP_FLOW, "repair_package_refund_claims": 1, "flow_tasks": 1}, update=update,
        cases={cid}, customer=customer["id"], member=member, purchase=p_id, refund=rid, lots={lot_id})
    body, request, _, approved = await submit(e, f"{API}/refunds/{rid}/actions/approve", f"{API}/members/{member}/purchases")
    require(request == {"request_id": request["request_id"], "version": refund["version"], "values": values}, "原退款批准双CAS/原因失配")
    approved.update(guard=guard.finish(), receipt=group_receipt(e, request, manager, f"repair_package:refund:{rid}:approve", {"version": refund["version"], **values}, body), task_owner=owner_review)
    claim = subset(e, "repair_package_refund_claims", "refund_id", rid)
    require(len(claim) == 1 and claim[0]["status"] == "reserved" and json.loads(claim[0]["spans"]) == [[1000, 2000]]
            and claim[0]["lot_id"] == lot_id and one(e, "repair_package_refunds", rid)["cash_id"] is None, "独立批准缺原RefundClaim占额或冒充实退")
    owner_pay = await handoff(e, context, credentials, fixture, cid, "repair_package_refund_pay_" + str(rid), "finance", member)
    file = await proof(e, context, credentials, fixture, "finance", cid, member, "receipt", "mixed-refund-paid-" + str(rid), token)
    finance, _ = await package_view(e, context, credentials, fixture, "finance", member)
    refund, case = one(e, "repair_package_refunds", rid), one(e, "flow_cases", cid)
    await click_form(e, f'#main [data-act="package-refund"][data-id="{rid}"][data-purchase="{p_id}"][data-key="pay"]', "登记实际原款退款")
    await account_choice(e, account)
    reference = "PK-OUT-" + str(rid) + "-" + token
    await e.fill('#modal [name="reference"]', reference, "登记本笔真实合成原账户退款号")
    await MF.choose_file(e, file, "receipt")
    values = {"case_version": case["version"], "account_id": account["id"], "reference": reference,
              "evidence_id": file["file"]["id"], "amount_cents": amount}
    update = updates(e, (cid,), member=member, account=account["id"], purchase=p_id, lots={lot_id})
    update["repair_package_refunds"] = {rid: VERSION | {"status", "cash_id"}}
    update["repair_package_refund_claims"] = {claim[0]["id"]: VERSION | {"status"}}
    guard = Guard(e, "mixed_unused_refund_pay_" + str(rid), finance,
        append={**GROUP_FLOW, "repair_package_entries": 1, "cash_entries": 1}, update=update,
        cases={cid}, customer=customer["id"], member=member, purchase=p_id, refund=rid, lots={lot_id})
    body, request, shown, paid = await submit(e, f"{API}/refunds/{rid}/actions/pay", f"{API}/members/{member}/purchases")
    require(request == {"request_id": request["request_id"], "version": refund["version"], "values": values}, "原实际退款不是本人双CAS/原款完整输入")
    paid.update(guard=guard.finish(), receipt=group_receipt(e, request, finance, f"repair_package:refund:{rid}:pay", {"version": refund["version"], **values}, body), task_owner=owner_pay, file=file)
    final = decoded(one(e, "repair_package_refunds", rid), "selections")
    entry = guard.added["repair_package_entries"][0]
    cash = one(e, "cash_entries", final["cash_id"])
    require(final["status"] == "executed" and final["approved_by"] == manager["id"] and final["amount_cents"] == amount
            and final["selections"] == [selection] and entry["purpose"] == "refund" and entry["refund_id"] == rid
            and entry["hold_id"] is None and entry["original_id"] is None and json.loads(entry["spans"]) == [[1000, 2000]]
            and entry["quantity_milli"] == 1000 and entry["paid_cents"] == entry["settlement_cents"] == amount
            and entry["evidence_id"] == file["file"]["id"] and cash["direction"] == "out"
            and cash["category"] == "repair_package_refund" and cash["amount_cents"] == amount
            and cash["account"] == account["name"] and cash["voucher_no"] == reference and cash["created_by"] == finance["id"]
            and one(e, "repair_package_refund_claims", claim[0]["id"])["status"] == "applied", "原退Entry/正区间/Claim/真实原账户现金失配")
    displayed = next(p for p in shown["items"] if p["id"] == p_id)
    require(next(l for l in displayed["lots"] if l["id"] == lot_id)["available_milli"] == 0
            and next(r for r in displayed["refunds"] if r["id"] == rid)["status"] == "executed", "前端未真实显示该原批已退款注销")
    return {"request": native, "approve": approved, "pay": paid, "refund": final,
            "claim": decoded(one(e, "repair_package_refund_claims", claim[0]["id"]), "spans"),
            "entry": decoded(entry, "spans"), "cash": cash}


async def repair_packages_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, customer, member, account, work, item, warehouse, location, resource, points = dependencies(e, cp)
        token = uuid.uuid4().hex[:10]
        baseline_member = one(e, "group_members", member)
        baseline_material = R.material_facts(e, item["id"])
        cp.start("HK-043")
        rule, created = await create_rule(e, context, credentials, fixture, work, item, token)
        decision = await decide_rule(e, context, credentials, fixture, rule, "approve")
        mappings = [await map_rule(e, context, credentials, fixture, rule, source, component)
                    for source, component in zip((work, item), rule["contract"]["components"])]
        cp.note({"new_rule": rule, "native_create": created, "independent_decision": decision, "actual_mappings": mappings,
                 "mixed_type_distinct_from_legacy_benefit_package": True})
        vehicle, vehicle_native = await create_vehicle(e, context, credentials, fixture, customer, member, token)
        case_id, intake = await new_intake(e, context, credentials, fixture, customer, member, vehicle, resource, token)
        cp.note({"same_member_new_vehicle": vehicle, "native_vehicle": vehicle_native, "new_same_member_v4_intake": intake})
        cp.start("HK-126")
        p, proposed = await purchase(e, context, credentials, fixture, customer, member, case_id, rule)
        p_id = p["id"]
        _, authorized = await purchase_action(e, context, credentials, fixture, customer, member, p_id, "authorize", account, token)
        _, issued = await purchase_action(e, context, credentials, fixture, customer, member, p_id, "issue", account, token)
        issued_facts = package_facts(e, p_id, case_id)
        frozen_lots = [{k: lot[k] for k in ("id", "purchase_id", "component_key", "quantity_milli", "credit_cents", "paid_cents", "settlement_cents", "snapshot")} for lot in issued_facts["lots"]]
        await cp.passed({"propose": proposed, "purchase_authorization": authorized, "full_actual_issue": issued,
            "original_purchase": issued_facts["purchase"], "original_lots": issued_facts["lots"], "purchase_cash": issued_facts["cash"],
            "purchase_cash_cents": 2400, "proposed_or_authorized_not_issuance": True})
        cp.start("HK-043")
        quote, quote_evidence = await package_quote(e, context, credentials, fixture, customer, member, case_id, p_id, item, work)
        _, fulfilment = await fulfil(e, context, credentials, fixture, customer, member, case_id, p_id, quote,
            vehicle, resource, item, warehouse, location, points, token)
        completed = await capture_and_release(e, context, credentials, fixture, customer, member, case_id, p_id, vehicle, resource, item, points, token)
        await cp.passed({"new_rule": rule, "create": created, "independent_decision": decision, "real_source_mappings": mappings,
            "native_same_member_vehicle": vehicle_native, "new_intake": intake, "original_quote": quote_evidence,
            "real_fulfilment": fulfilment, "original_capture_and_departure": completed,
            "capture_credit_cents": 1500, "capture_recognized_cents": 1200, "internal_settlement_cents": 1200,
            "capture_new_cash_cents": 0, "original_unused_quantity_per_component_milli": 1000})
        cp.start("HK-127")
        refunds = []
        for lot in issued_facts["lots"]:
            amount = 800 if lot["component_key"] == "component_1" else 400
            refunds.append(await refund_component(e, context, credentials, fixture, customer, member, p_id, lot["id"], amount, account, token))
        final = package_facts(e, p_id, case_id)
        require(len(final["refunds"]) == len(final["refund_claims"]) == 2 and len(final["entries"]) == 4 and len(final["links"]) == 2
                and final["links"] == completed["capture_facts"]["links"] and final["settlements"] == completed["capture_facts"]["settlements"]
                and len(final["cash"]) == 3 and sum(c["amount_cents"] * (1 if c["direction"] == "in" else -1) for c in final["cash"]) == 1200,
                "原两未用退款不得改变已履约权益、内部结算或重复现金")
        require([{k: lot[k] for k in frozen_lots[0]} for lot in final["lots"]] == frozen_lots
                and one(e, "flow_cases", case_id)["state"] == "completed", "未用退款覆盖冻结Lot或重新开启终态修单")
        await cp.passed({"two_original_component_refunds": refunds, "facts": final, "refund_cash_cents": 1200,
            "original_purchase_cash_cents": 2400, "net_purchase_cash_cents": 1200, "remaining_free_quantity_milli": [0, 0],
            "already_consumed_parts_not_returned": True, "ordinary_refundhold_not_used": True})
        cp.start("HK-133")
        frozen_contract = final["purchase"]["contract"]
        new_rule, new_rule_native = await create_rule(e, context, credentials, fixture, work, item, token, revision=2)
        new_rule_decision = await decide_rule(e, context, credentials, fixture, new_rule, "approve")
        stopped = await decide_rule(e, context, credentials, fixture, rule, "revoke")
        require(package_facts(e, p_id, case_id) == final and final["purchase"]["contract"] == frozen_contract
                and new_rule["code"] == rule["code"] and new_rule["rule_version"] == rule["rule_version"] + 1
                and one(e, "repair_package_rules", rule["id"])["digest"] == rule["digest"], "新类型版本/停止新购买重写已售历史")
        finance, shown = await package_view(e, context, credentials, fixture, "finance", member)
        displayed = next(v for v in shown["items"] if v["id"] == p_id)
        require(displayed["status"] == "issued" and len(displayed["lots"]) == 2 and all(v["available_milli"] == 0 for v in displayed["lots"])
                and {r["status"] for r in displayed["refunds"]} == {"executed"}, "原套餐类型/已售实际结果前端不一致")
        before_read = e.business_snapshot("before_final_package_refresh")
        async with e.page.expect_response(lambda r: get_match(r, f"{API}/members/{member}/purchases")) as pending:
            e.action("reload", "原生刷新核对已售原批及两笔实退")
            await e.page.reload(wait_until="domcontentloaded")
        response = await pending.value
        require(response.status == 200 and package_facts(e, p_id, case_id) == final, "刷新重复或改写原套餐事实")
        e.business_unchanged(before_read, "after_final_package_refresh")
        current_member = one(e, "group_members", member)
        current_material = R.material_facts(e, item["id"])
        require(current_member["balance_cents"] == baseline_member["balance_cents"] and current_member["reserved_cents"] == baseline_member["reserved_cents"]
                and current_material["item"]["quantity_milli"] == baseline_material["item"]["quantity_milli"] - 1000
                and current_material["item"]["inventory_value_cents"] == baseline_material["item"]["inventory_value_cents"] - fulfilment["actual_material_cost_cents"],
                "套餐误用普通本金或退款伪造实物回库")
        await cp.passed({"rule_v1": rule, "rule_v2": new_rule, "new_rule": new_rule_native, "independent_v2_decision": new_rule_decision,
            "stop_original_new_purchases": stopped, "sold_contract_unchanged": True, "sold_quote_and_capture_unchanged": True,
            "frozen_lots_unchanged": True, "native_final_status": displayed, "native_refresh_no_mutation": True,
            "mixed_type_not_scalar_legacy_package": True})
        claim = completed["points"]["claim"]
        sources = {"customer_id": customer["id"], "member_id": member, "account_id": account["id"], "customer_vehicle_id": vehicle["id"], "vin": vehicle["vin"],
            "resource_id": resource["id"], "work_item_id": work["id"], "material_item_id": item["id"], "source_location_id": location["id"],
            "appointment_id": intake["appointment_id"], "intake_case_id": intake["intake_case_id"], "repair_case_id": case_id,
            "rule_id": rule["id"], "new_rule_id": new_rule["id"], "mapping_ids": [m["mapping"]["id"] for m in mappings],
            "purchase_id": p_id, "purchase_cash_id": final["purchase"]["cash_id"], "lot_ids": [lot["id"] for lot in final["lots"]], "quote_id": quote["id"],
            "hold_ids": [h["id"] for h in final["holds"]], "capture_entry_ids": [r["id"] for r in final["entries"] if r["purpose"] == "capture"],
            "payment_link_ids": [r["id"] for r in final["links"]], "settlement_ids": [r["id"] for r in final["settlements"]],
            "refund_ids": [r["id"] for r in final["refunds"]], "refund_claim_ids": [r["id"] for r in final["refund_claims"]],
            "refund_entry_ids": [r["id"] for r in final["entries"] if r["purpose"] == "refund"], "cash_ids": [c["id"] for c in final["cash"]],
            "repair_stock_id": fulfilment["steps"]["material"]["stock"]["id"], "stock_move_id": fulfilment["steps"]["material"]["move"]["id"],
            "net_cash_cents": 1200, "capture_credit_cents": 1500, "recognized_cents": 1200, "internal_cents": 1200,
            "actual_material_cost_cents": fulfilment["actual_material_cost_cents"], "points_claim_id": claim["id"],
            "points_change_ids": [c["id"] for c in completed["points"]["changes"]], "centre_payment_performed": False,
            "consumed_material_aftercare_return_acceptance": False, "full_193_business_acceptance": False}
        cp.finish(sources)
    except Exception as error:
        cp.failed(error)
        raise


REPAIR_PACKAGES_SCENARIOS = ((SCENARIO, repair_packages_business, 1500),)
