"""Unregistered native single-store warehouse and supplier-return candidate.

Only same-run passed checkpoints supply master sources. The two new items and
every physical, approval and cash result are created through original forms.
Database reads are SELECT-only; binary files remain outside JSON evidence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from vehicle_purchase_business import live_choice, select_value
from master_data_business import save_item
from material_business import item_stock, qty, money, visible_original_button
from finance_business import choose_file, get_match, original_form, receipt as finance_receipt, submit

SCENARIO = "warehouse-original-flows-hk046-056-048-059-050-057-060-085"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
CONTRACTS = (
    ("HK-046", "物资其它入库"), ("HK-056", "耗材领用出库"),
    ("HK-048", "耗材领用退回"), ("HK-059", "礼品出库"),
    ("HK-050", "礼品退货入库"), ("HK-057", "其它入库退货"),
    ("HK-060", "物资其他出库"), ("HK-085", "其他入库退货收款"),
)
NAMES = {"activate": "真实库位启用", "other_in": "其他物资入库",
         "consumable": "耗材领用", "consumable_return": "原耗材领用退回",
         "gift": "礼品发出", "gift_return": "原礼品退回",
         "other_in_return": "原其他入库退回", "disposal": "其他处置出库"}
RETURN_TITLES = {"consumable_return": "耗材退回", "gift_return": "礼品退回",
                 "other_in_return": "其他入库退回"}
PURPOSES = {"other_in": "wh_other_in", "consumable": "wh_consumable",
            "consumable_return": "wh_consume_return", "gift": "wh_gift",
            "gift_return": "wh_gift_return", "other_in_return": "wh_other_return",
            "disposal": "wh_disposal"}
OUT = {"consumable", "gift", "other_in_return", "disposal"}
WH = "/api/warehouse/cases/"
BF = "/api/business-finance/orders/"
VERSION = {"version", "updated_at"}
CASE_COLUMNS = VERSION | {"state", "completed_date"}
TASK_COLUMNS = VERSION | {"status", "done_at", "done_by", "assignee_id"}
ITEM_COLUMNS = VERSION | {"quantity_milli", "inventory_value_cents", "unit_cost_cents"}
BALANCE_COLUMNS = VERSION | {"quantity_milli", "value_cents"}
COMMON = {"flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1}
FINANCE_COMMON = {"flow_events": 1, "audit_logs": 1,
                  "business_finance_events": 1, "business_finance_receipts": 1}
TABLES = {
    "flow_cases", "flow_tasks", "flow_items", "flow_events", "audit_logs",
    "flow_request_receipts", "flow_files", "file_security", "file_scan_events",
    "master_warehouses", "master_locations", "master_suppliers", "flow_accounts",
    "warehouse_documents", "warehouse_approvals", "warehouse_enrollments",
    "warehouse_balances", "warehouse_entries", "warehouse_holds",
    "warehouse_allocations", "warehouse_allocation_lines", "flow_stock_moves",
    "business_finance_orders", "business_finance_events", "business_finance_receipts",
    "business_finance_return_receivables", "business_finance_cash_batches",
    "business_finance_cash_allocations", "flow_payment_links", "cash_entries",
}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        source = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in CONTRACTS:
            binding = source[key]
            require(binding["title"] == title and binding["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in binding["acceptance_checks"]),
                    key + " 原目录标题或check合同未核准")
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in CONTRACTS],
            "complete": False, "passed": False, "executed_requirements": 0,
            "passed_requirements": 0, "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution": "native_browser_original_forms", "business_accepted": False,
            "full_193_business_acceptance": False, "human_acceptance": "pending",
            "provenance": {k: e.manifest[k] for k in
                           ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_inputs": True, "actual_bank_acceptance": False,
                           "actual_physical_handover_acceptance": False,
                           "file_scan": "original_structure_only_not_clamav",
                           "business_entity_policy_acceptance": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested",
                "business_accepted": False, "acceptance_checks": [{"id": key + "-business",
                "check_id": key + "-business", "status": "not_tested", "evidence": {},
                "criteria": ["原页面本人真实输入与单次明确点击", "原ID、当前CAS、岗位待办及回执对应",
                             "原数量、成本、位置、现金分别核对", "所有旧行及未授权表保留"]}],
                "human_criteria": {"expected_display": "pending", "simple_flow": "pending",
                    "concise_copy": "pending", "backend_match": "pending",
                    "hard_bug": "pending", "consistent_rules": "pending"},
                "conditional_checks": [{"name": "超退、过时版本及未知结果分支",
                                        "status": "not_tested"}]} for key, title in CONTRACTS],
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def note(self, **evidence):
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.report["passed_requirements"] = sum(r["status"] == "passed" for r in self.report["requirements"])
        self.report["executed_requirements"] = sum(r["status"] != "not_tested" for r in self.report["requirements"])
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
            self.report["failed_requirement"] = self.active["id"]
        self.report.update(error=self.e.scrub(error), executed_requirements=sum(
            r["status"] != "not_tested" for r in self.report["requirements"]),
            passed_requirements=sum(r["status"] == "passed" for r in self.report["requirements"]))
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "仓储八项未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=8,
                           passed_requirements=8, warehouse_sources=sources, report_sources=sources)
        self.save()
        self.e.observe("warehouse_original_flows_checkpoint", {"path": str(self.path),
                       "warehouse_sources": sources, "business_accepted": False})


def pk(table):
    return "file_id" if table == "file_security" else "id"


def rows(e, table):
    require(table in TABLES, "仓储表标识未核准")
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {pk(table)}")


def one(e, table, key):
    require(table in TABLES, "仓储表标识未核准")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {pk(table)}=?", (key,))
    require(len(found) == 1, "明确原ID不存在或不唯一：" + table)
    return found[0]


def related(e, table, field, key):
    require(table in TABLES and field in {"case_id", "item_id", "allocation_id", "batch_id"},
            "仓储关联读取未核准")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {pk(table)}", (key,))


class Guard:
    """Exact append counts; all previous rows, IDs and other tables protected."""
    def __init__(self, e, label, actor, *, expected, update=None, cases=(), items=(), new_kind=None):
        self.e, self.label, self.actor = e, label, actor
        self.expected, self.update = dict(expected), update or {}
        self.cases, self.items, self.new_kind = set(cases), set(items), new_kind
        require(self.expected.keys() | self.update.keys() <= TABLES, "动作守卫有未审表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.expected.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.expected.keys() | self.update.keys(),
                "原提交影响未授权表：" + str(sorted(changed)))
        added, updates = {}, {}
        new_cases, new_items = set(), set()
        for table, target in (("flow_cases", new_cases), ("flow_items", new_items)):
            if table in self.expected:
                old_ids = {r["id"] for r in self.old[table]}
                target.update(r["id"] for r in rows(self.e, table) if r["id"] not in old_ids)
        for table, before in self.old.items():
            current = {r[pk(table)]: r for r in rows(self.e, table)}
            old_ids = {r[pk(table)] for r in before}
            updates[table] = []
            for old in before:
                require(old[pk(table)] in current, "旧原行被删除：" + table)
                cols = {k for k in old if old[k] != current[old[pk(table)]][k]}
                require(cols <= self.update.get(table, {}).get(old[pk(table)], set()),
                        "旧原行被覆盖：" + table + "/" + str(old[pk(table)]) + "/" + str(sorted(cols)))
                if cols:
                    updates[table].append({"id": old[pk(table)], "columns": sorted(cols)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(len(new) == self.expected.get(table, 0),
                    "原动作新增数量不匹配：" + table + "/" + str(len(new)))
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == 1, "新增事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in self.cases | new_cases, "新增事实串原单：" + table)
                if "item_id" in row:
                    require(row["item_id"] in self.items | new_items, "新增事实串物资：" + table)
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "新增事实不是本次本人：" + table)
                if table == "flow_cases":
                    require(row["kind"] == self.new_kind and row["flow_version"] == 2
                            and row["owner_id"] == self.actor["id"] and row["customer_id"] is None,
                            "新增仓储/供应方单类型或身份错误")
                if table == "warehouse_documents":
                    require(row["id"] in new_cases, "仓储原文档未绑定唯一新单")
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", row["balance_id"])["item_id"] in self.items,
                            "库位流水串物资")
                if table == "warehouse_allocation_lines":
                    a = one(self.e, "warehouse_allocations", row["allocation_id"])
                    require(a["case_id"] in self.cases | new_cases and a["item_id"] in self.items,
                            "准备行串原单/物资")
                if table == "business_finance_cash_allocations":
                    require(one(self.e, "business_finance_cash_batches", row["batch_id"])["case_id"]
                            in self.cases, "现金分配串原单")
            added[table] = [r[pk(table)] for r in new]
        result = {"label": self.label, "appended_ids": added, "updated_columns": updates,
                  "changed_tables": sorted(changed), "all_old_rows_preserved": True,
                  "all_other_tables_preserved": True, "membership_and_prior_cash_stock_preserved": True}
        self.e.observe("warehouse_original_row_guard", result)
        return result


def mutable(e, case_id, *, item_id=None, finance=False, account_id=None):
    result = {"flow_cases": {case_id: CASE_COLUMNS}, "flow_tasks": {
        r["id"]: TASK_COLUMNS for r in related(e, "flow_tasks", "case_id", case_id)}}
    if item_id:
        result["flow_items"] = {item_id: ITEM_COLUMNS}
        result["warehouse_balances"] = {r["id"]: BALANCE_COLUMNS
            for r in related(e, "warehouse_balances", "item_id", item_id)}
        result["warehouse_allocations"] = {r["id"]: VERSION | {"status", "stock_move_id"}
            for r in related(e, "warehouse_allocations", "case_id", case_id)}
    if finance:
        result["business_finance_orders"] = {r["id"]: VERSION | {"status", "approved_by"}
            for r in related(e, "business_finance_orders", "case_id", case_id)}
    if account_id:
        result["flow_accounts"] = {account_id: VERSION}
    return result


def source_dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "仅允许外部合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"),
            "合成数据库未外置于本轮runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "当前镜像未冻结")
    for name in (Path(__file__).name, "business_acceptance_catalog.json", "master_data_business.py",
                 "vehicle_purchase_business.py", "material_business.py", "finance_business.py",
                 "sales_business.py", "sales_order_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()).hexdigest(), "同轮脚本指纹变化：" + name)
    cp.report["mirror"] = {"sha256": hashlib.sha256(raw).hexdigest(),
                            "source_sha256": provenance["source_sha256"],
                            "script_sha256": provenance["script_sha256"]}
    master = fixed_dependency(e, cp, MASTER)
    purchase = fixed_dependency(e, cp, PURCHASE)
    material = fixed_dependency(e, cp, MATERIAL)
    fixture = dict(e.manifest["business_fixtures"]["vehicle_purchase"])
    require(fixture["store_id"] == 1, "仅本店仓储八项")
    for role in ("inventory", "manager", "finance"):
        user = e.manifest["users"][fixture[role + "_key"]]
        access = e.db.rows("SELECT user_id,store_id,role FROM user_stores WHERE user_id=? AND store_id=?",
                           (user["id"], 1))
        require(user["role"] == role and len(access) == 1 and access[0]["role"] == role,
                "缺本店原随机岗位：" + role)
    evidence = checkpoint_evidence(master, "HK-184")
    warehouse = one(e, "master_warehouses", evidence["warehouse"]["row"]["id"])
    location = one(e, "master_locations", evidence["location"]["row"]["id"])
    supplier = one(e, "master_suppliers", checkpoint_evidence(purchase, "HK-171")["supplier"]["id"])
    account = one(e, "flow_accounts", checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"])
    require(warehouse == evidence["warehouse"]["row"] and location == evidence["location"]["row"]
            and location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials",
            "同轮原仓库/库位关系已改变")
    require(supplier == checkpoint_evidence(purchase, "HK-171")["supplier"], "原供应方资料已改变")
    require(all(r["store_id"] == 1 and r["active"] for r in (warehouse, location, supplier, account)),
            "同轮仓位/供应方/账户未在本店启用")
    primary = material["material_sources"]["primary"]
    original_item = one(e, "flow_items", primary["item_id"])
    enrollment = one(e, "warehouse_enrollments", primary["enrollment_id"])
    require(original_item["store_id"] == 1 and enrollment["item_id"] == original_item["id"]
            and primary["source_location_id"] in primary["location_ids"]
            and primary["warehouse_id"] == warehouse["id"], "同轮材料有限来源不匹配")
    for move_id in primary["stock_move_ids"]:
        require(one(e, "flow_stock_moves", move_id)["item_id"] == original_item["id"], "材料原收发来源串物资")
    cp.report["source_preconditions"] = {"warehouse": warehouse, "location": location,
        "supplier": supplier, "account": {k: account[k] for k in ("id", "store_id", "name", "active")},
        "prior_material_item_id": original_item["id"], "prior_material_enrollment_id": enrollment["id"],
        "prior_material_current_quantity_milli": original_item["quantity_milli"],
        "prior_material_current_value_cents": original_item["inventory_value_cents"],
        "prior_material_is_not_new_stock_source": True}
    cp.save()
    return fixture, warehouse, location, supplier, account


async def submit_new(e, path, render_prefix, *, status=201, financial=False):
    """Bind the native post's new ID to its real render GET, including fast GETs."""
    future = asyncio.get_running_loop().create_future()
    observed, new_id = [], None

    def bind(response):
        actual = urlsplit(response.url).path
        if response.request.method == "GET" and actual.startswith(render_prefix) and actual[len(render_prefix):].isdigit():
            observed.append(response)
            if new_id is not None and actual == render_prefix + str(new_id) and not future.done():
                future.set_result(response)

    e.page.on("response", bind)
    try:
        await expect(e.page.locator('#modal form button[type="submit"]')).to_be_enabled()
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人核对后唯一提交原新单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, "原新单提交HTTP " + str(response.status) + "：" + e.scrub(body.get("detail", "")))
        new_id = body["case"]["id"] if financial else body["id"]
        require(type(new_id) is int and new_id > 0, "原新单响应缺唯一ID")
        for read in observed:
            if urlsplit(read.url).path == render_prefix + str(new_id) and not future.done():
                future.set_result(read)
        read = await asyncio.wait_for(future, timeout=30)
        shown = await read.json()
        headers = await response.request.all_headers()
        request = response.request.post_data_json
        require(read.status == 200 and headers.get("cookie") and headers.get("x-csrf-token")
                and headers.get("x-store-id") == "1" and headers.get("x-app-request") == "1"
                and len(request.get("request_id", "")) >= 16, "新单原同源身份或幂等合同不完整")
        require((shown["case"]["id"] if financial else shown["id"]) == new_id, "新单原GET串旧单")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main h1")).to_have_text("财务业务办理" if financial else shown["operation_label"])
        meta = {"path": path, "status": status, "native_ui": True, "single_click": True,
                "cookie_present": True, "csrf_present": True, "store_id": 1,
                "new_case_id": new_id, "render_get_path": urlsplit(read.url).path,
                "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest()}
        e.observe("warehouse_original_new_entity", meta)
        return body, request, shown, meta
    finally:
        e.page.remove_listener("response", bind)
        if not future.done():
            future.cancel()


def warehouse_receipt(e, request, case_id, actor, action):
    payload = {k: v for k, v in request.items() if k != "request_id"}
    if action == "create":
        payload = {"source_location_id": None, "destination_location_id": None,
                   "original_move_id": None, "recipient": "", "locations": [], **payload}
    else:
        values = {"value_cents": None, **payload["values"]} if action == "approve" else payload["values"]
        payload = {"id": case_id, "version": payload["version"], **values}
    digest = hashlib.sha256(json.dumps({"operation": "warehouse_" + action, "payload": payload},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    found = e.db.rows("SELECT id,case_id,actor_id,store_id,digest FROM flow_request_receipts WHERE request_key=?",
                       (request["request_id"],))
    require(len(found) == 1 and found[0]["case_id"] == case_id and found[0]["actor_id"] == actor["id"]
            and found[0]["store_id"] == 1 and found[0]["digest"] == digest,
            "仓储原回执未绑定本人、全部原字段与本单")
    return found[0]


def action_event(e, guard, case_id, actor, action, *, finance=False):
    old_ids = {r["id"] for r in guard.old["flow_events"]}
    events = [r for r in rows(e, "flow_events") if r["id"] not in old_ids]
    require(len(events) == 1 and events[0]["case_id"] == case_id and events[0]["actor_id"] == actor["id"]
            and events[0]["action"] == action and events[0]["after_state"] == one(e, "flow_cases", case_id)["state"],
            "原业务事件未绑定单次本人动作及真实后状态")
    audit_ids = {r["id"] for r in guard.old["audit_logs"]}
    audits = [r for r in rows(e, "audit_logs") if r["id"] not in audit_ids]
    require(len(audits) == 1 and audits[0]["actor_id"] == actor["id"]
            and audits[0]["entity_id"] == case_id and audits[0]["entity_type"] == "flow"
            and audits[0]["action"] == "flow_" + action,
            "原审计未绑定本单本人")
    result = {"flow_event_id": events[0]["id"], "audit_id": audits[0]["id"], "action": action,
              "before_state": events[0]["before_state"], "after_state": events[0]["after_state"],
              "detail": json.loads(events[0]["detail"])}
    if finance:
        old = {r["id"] for r in guard.old["business_finance_events"]}
        new = [r for r in rows(e, "business_finance_events") if r["id"] not in old]
        require(len(new) == 1 and new[0]["case_id"] == case_id and new[0]["actor_id"] == actor["id"]
                and action == "business_finance_" + new[0]["action"], "财务事件与原事件不一致")
        result["finance_event_id"] = new[0]["id"]
    return result


def open_task(e, case_id, key):
    found = [r for r in related(e, "flow_tasks", "case_id", case_id) if r["key"] == key and r["status"] == "open"]
    require(len(found) == 1, "原待办不唯一：" + key)
    return found[0]


async def detail(e, context, credentials, fixture, role, case_id, *, financial=False):
    route = ("business-finance-order/" if financial else "warehouse/") + str(case_id)
    path = (BF if financial else WH) + str(case_id)
    # Original login may append its own legitimate audit; read-only guard starts after it.
    actor = await login_as(e, context, credentials, fixture[role + "_key"],
                           "business-finance" if financial else "warehouse", 1)
    before = e.business_snapshot("before_warehouse_detail_read")
    async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
        await e.page.goto(e.origin + "/#" + route)
    response = await pending.value
    shown = await response.json()
    require(response.status == 200, "本人原仓储/财务详情不可读")
    row = one(e, "flow_cases", case_id)
    view = shown["case"] if financial else shown
    fields = ("id", "store_id", "number", "version", "state", "business_date", "due_date")
    if financial:
        fields += ("title",)
    require(all(view[k] == row[k] for k in fields),
            "原页面单号、状态、版本或店与DB不一致")
    await expect(e.page.locator("#main h1")).to_have_text("财务业务办理" if financial else shown["operation_label"])
    if financial:
        finance_view(e, shown)
    else:
        doc = one(e, "warehouse_documents", case_id)
        item = one(e, "flow_items", doc["item_id"])
        require(shown["operation_label"] == NAMES[doc["operation"]] and shown["item_name"] == item["name"]
            and row["title"] == NAMES[doc["operation"]] + " · " + item["name"], "原仓储作业名称或物资错配")
        await expect(e.page.locator("#main .pagehead")).to_contain_text(row["number"])
        require(all(shown[k] == doc[k] for k in ("operation", "item_id", "quantity_milli",
            "source_location_id", "destination_location_id", "original_move_id", "reason", "recipient")),
            "原仓储文档与页面字段不一致")
        if role == "inventory":
            require("approved_value_cents" not in shown and all("value_cents" not in r for r in shown["stock_moves"]),
                    "库管页面泄漏原资金价值")
    e.business_unchanged(before, "after_warehouse_detail_read")
    return actor, shown


async def responsible(e, context, credentials, fixture, role, case_id, task_key, *, financial=False):
    task = open_task(e, case_id, task_key)
    target = e.manifest["users"][fixture[role + "_key"]]
    handoff = {"task_id": task["id"], "task_key": task_key, "actor_id": target["id"],
               "needed": task["assignee_id"] != target["id"]}
    if handoff["needed"]:
        async with e.page.expect_response(lambda r: get_match(r, "/api/flow/cases/" + str(case_id))) as pending:
            manager = await login_as(e, context, credentials, fixture["manager_key"], "case/" + str(case_id), 1)
        require((await pending.value).status == 200, "原任务转交前未读取当前原单")
        await expect(e.page.locator("#main h1")).to_have_text(one(e, "flow_cases", case_id)["title"])
        button = f'#main [data-act="assign"][data-id="{task["id"]}"]'
        await expect(e.page.locator(button)).to_be_visible()
        await expect(e.page.locator(button)).to_be_enabled()
        await e.click(button, "主管明确转交本店这项原待办")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, target)
        reason = "本轮合成仓储原单由明确本店岗位员工本人核对办理"
        await e.fill('#modal [name="reason"]', reason, "填写原任务交接依据")
        guard = Guard(e, "warehouse_task_handoff", manager, expected={"flow_events": 1, "audit_logs": 1},
            update={"flow_tasks": {task["id"]: VERSION | {"assignee_id"}}}, cases={case_id})
        _, request, _, meta = await submit(e, f'/api/flow/tasks/{task["id"]}/assign', "/api/flow/cases/" + str(case_id))
        require(request == {"version": task["version"], "assignee_id": target["id"], "reason": reason},
                "原AssignInput应仅三字段，无虚构request_id")
        handoff.update(native=meta, guard=guard.finish(), event=action_event(e, guard, case_id, manager, "reassign"))
    actor, shown = await detail(e, context, credentials, fixture, role, case_id, financial=financial)
    current = open_task(e, case_id, task_key)
    require(current["assignee_id"] == actor["id"] and current["role"] == role, "办理人不是本店本人待办")
    handoff["version"] = current["version"]
    return actor, shown, handoff


async def upload_original(e, case_id, actor, category, purpose, token, *, financial=False):
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    path = directory / (purpose + "-" + token + ".txt")
    content = ("本轮隔离合成业务输入，非真实公司款项或实物交接证明。\n用途=" + purpose +
               "；原单=" + str(case_id) + "；独立输入=" + uuid.uuid4().hex + "\n").encode("utf-8")
    path.write_bytes(content)
    await expect(e.page.locator('#main [data-act="upload"]')).to_be_visible()
    await e.click('#main [data-act="upload"]', "员工上传本单独立合成原件")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "选择本次原件类别")
    e.action("select_file", "选择外部合成文件", name=path.name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    guard = Guard(e, "warehouse_upload_" + purpose, actor, expected={"flow_events": 1, "audit_logs": 1,
        "flow_files": 1, "file_security": 1, "file_scan_events": 1}, cases={case_id})
    body, _, shown, meta = await submit(e, "/api/flow/cases/" + str(case_id) + "/files",
                                      (BF if financial else WH) + str(case_id), multipart=True)
    asset = one(e, "flow_files", body["id"])
    stored = asset.pop("content")
    require(isinstance(stored, bytes) and stored == content and asset["size"] == len(content)
            and asset["sha256"] == hashlib.sha256(content).hexdigest() and asset["category"] == category
            and asset["case_id"] == case_id and asset["created_by"] == actor["id"] and not asset["generated"],
            "原文件字节、元数据、类别或本单来源错误")
    security = one(e, "file_security", asset["id"])
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (asset["id"],))
    require(len(scans) == 1 and scans[0]["state"] == security["state"] == "structure_only"
            and scans[0]["action"] == "initial" and scans[0]["actor_id"] == actor["id"]
            and scans[0]["sha256"] == asset["sha256"] and scans[0]["size"] == asset["size"]
            and body["security"]["can_use"], "合成原扫描事实应明确structure_only且可使用")
    await expect(e.page.locator("#main .filerecord").filter(has_text=path.name)).to_have_count(1)
    require((shown["case"]["id"] if financial else shown["id"]) == case_id, "上传后原GET串单")
    result = {"file": asset, "security": security, "native": meta,
              "stored_blob": {"length": len(stored), "sha256": hashlib.sha256(stored).hexdigest()},
              "guard": guard.finish(), "event": action_event(e, guard, case_id, actor, "upload"),
              "scans": scans, "clamav_acceptance": False}
    return result


async def new_item(e, context, credentials, fixture, token, key, unit):
    actor = await login_as(e, context, credentials, fixture["inventory_key"], "master/items", 1)
    await expect(e.page.locator("#main h1")).to_have_text("物资目录")
    values = {"sku": "WO-" + key.upper() + "-" + token, "name": "合成" + ("耗材" if key == "consumable" else "礼品") + token,
              "unit": unit, "active": True, "reorder": "0"}
    guard = Guard(e, "warehouse_new_zero_" + key, actor, expected={"flow_items": 1, "audit_logs": 1})
    item, meta = await save_item(e, actor, 1, values)
    require(item["quantity_milli"] == item["inventory_value_cents"] == item["unit_cost_cents"] == 0,
            "新物资主档不得预造库存成本")
    require(not related(e, "warehouse_enrollments", "item_id", item["id"])
            and not related(e, "flow_stock_moves", "item_id", item["id"]), "新物资已被其他来源制造库存")
    return item, {"item": item, "native": meta, "guard": guard.finish()}


async def create_warehouse(e, context, credentials, fixture, item_id, location, operation, quantity, *, original=None, warehouse=None, token):
    recipient = ""
    if original:
        actor, view = await detail(e, context, credentials, fixture, "inventory", original["case_id"])
        source = next((r for r in view["stock_moves"] if r["id"] == original["id"]), None)
        require(source and source["can_return"] and source["return_operation"] == operation
                and quantity <= source["returnable_milli"], "原完成批次可退量/类型错误")
        prior_returns = e.db.rows("SELECT quantity_milli,value_cents FROM flow_stock_moves WHERE original_id=? ORDER BY id",
                                  (original["id"],))
        require(source["returnable_milli"] == abs(original["quantity_milli"]) - sum(
                abs(r["quantity_milli"]) for r in prior_returns)
                and source["returned_milli"] == sum(abs(r["quantity_milli"]) for r in prior_returns),
                "原退回候选尚可退量与真实原流水不一致")
        selector = (f'#main [data-act="wh-original-return"][data-operation="{operation}"]'
                    f'[data-original="{original["id"]}"]')
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "从本次已完成原批次申请实际退回")
        await expect(e.page.locator("#modal-title")).to_have_text(RETURN_TITLES[operation])
        await expect(e.page.locator('#modal [name="original"]')).to_have_value(str(original["id"]))
        await expect(e.page.locator('#modal [data-return-summary]')).to_contain_text(one(e, "flow_cases", original["case_id"])["number"])
        await expect(e.page.locator('#modal form button[type="submit"]')).to_be_enabled()
        require(await e.page.locator('#modal [name="quantity"]').get_attribute("max") == qty(source["returnable_milli"]),
                "原退回表单未绑定尚可退量")
        await live_choice(e, "location", location["name"], warehouse["name"] + " / " + location["name"], expected_value=location["id"])
    else:
        actor = await login_as(e, context, credentials, fixture["inventory_key"], "warehouse", 1)
        await expect(e.page.locator("#main h1")).to_have_text("库位与仓储作业")
        selector = f'#main [data-act="wh-new"][data-operation="{operation}"]'
        await visible_original_button(e, selector, NAMES[operation])
        await e.click(selector, "申请原" + NAMES[operation])
        await expect(e.page.locator("#modal-title")).to_have_text(NAMES[operation])
        await select_value(e, '#modal [name="item_id"]', item_id, "选择本轮明确新物资")
        if operation == "activate":
            await select_value(e, '#modal [name="location"]', location["id"], "明确零实物启用位置")
            await e.fill('#modal [name="location_qty"]', "0", "明确启用零实物")
        else:
            await select_value(e, '#modal [name="source"]' if operation in OUT else '#modal [name="destination"]',
                               location["id"], "选择本店实际收发库位")
        if operation in {"consumable", "gift"}:
            recipient = "合成" + ("维修班组" if operation == "consumable" else "礼品接收人") + token
            await e.fill('#modal [name="recipient"]', recipient, "明确实际合成领取人")
    await e.fill('#modal [name="quantity"]', qty(quantity), "填写本次精确数量")
    reason = ("本轮合成耗材破损0.25包，由明确合成回收方接收处置，凭本单实际出库依据办理"
              if operation == "disposal" else "本轮合成" + NAMES[operation] + "，仅按本单真实输入及原来源办理")
    await e.fill('#modal [name="reason"]', reason, "填写本次明确来源与原因")
    day = await e.page.locator('#modal [name="due_date"]').input_value()
    before_item = one(e, "flow_items", item_id)
    expected = {**COMMON, "flow_cases": 1, "flow_tasks": 1, "warehouse_documents": 1}
    if operation == "activate":
        expected.update(warehouse_allocations=1, warehouse_allocation_lines=1)
    guard = Guard(e, "warehouse_create_" + operation, actor, expected=expected,
                  items={item_id}, new_kind="warehouse")
    body, request, shown, meta = await submit_new(e, "/api/warehouse/cases", WH)
    case_id = body["id"]
    doc = one(e, "warehouse_documents", case_id)
    require(request["operation"] == operation and request["item_id"] == item_id
            and request["quantity_milli"] == quantity and request["reason"] == reason
            and request["due_date"] == day, "原作业UI输入与POST不一致")
    require(doc["item_id"] == item_id and doc["operation"] == operation and doc["quantity_milli"] == quantity
            and doc["recipient"] == request.get("recipient", "") == recipient
            and doc["original_move_id"] == (original["id"] if original else None)
            and doc["source_location_id"] == (location["id"] if operation in OUT else None)
            and doc["destination_location_id"] == (location["id"] if operation not in OUT and operation != "activate" else None)
            and doc["baseline_item_version"] == before_item["version"]
            and doc["baseline_quantity_milli"] == before_item["quantity_milli"]
            and doc["baseline_value_cents"] == before_item["inventory_value_cents"], "原申请文档或位置/期初版本错误")
    require(one(e, "flow_items", item_id) == before_item and shown["state"] == "pending"
            and one(e, "flow_cases", case_id)["due_date"] == day, "申请不能先办理库存或替换本人期限")
    if operation == "activate":
        require(request["locations"] == [{"location_id": location["id"], "quantity_milli": 0}]
                and "destination_location_id" not in request, "零实物启用应使用原locations[]")
    meta.update(guard=guard.finish(), receipt=warehouse_receipt(e, request, case_id, actor, "create"),
                event=action_event(e, guard, case_id, actor, "warehouse_create"))
    return case_id, meta


async def warehouse_command(e, context, credentials, fixture, case_id, item_id, action, token, *, value=None):
    role, task_key = ("manager", "wh_approve") if action == "approve" else ("inventory", "wh_execute")
    actor, before_view, handoff = await responsible(e, context, credentials, fixture, role, case_id, task_key)
    doc, before_item = one(e, "warehouse_documents", case_id), one(e, "flow_items", item_id)
    category = "receipt" if action == "approve" and doc["operation"] == "other_in" else "evidence"
    proof = await upload_original(e, case_id, actor, category, doc["operation"] + "-" + action, token)
    await original_form(e, "wh-action", action, "批准作业" if action == "approve" else "确认实际收发")
    await select_value(e, '#modal [name="evidence_id"]', proof["file"]["id"], "选择本单本次原依据")
    values = {"evidence_id": proof["file"]["id"]}
    if value is not None:
        require(action == "approve" and doc["operation"] == "other_in", "只有原其它入库批准输入成本")
        await e.fill('#modal [name="value"]', money(value).replace(",", ""), "主管核对本次来源总价值")
        values["value_cents"] = value
    expected = dict(COMMON)
    if action == "approve":
        expected["warehouse_approvals"] = 1
        if doc["operation"] == "activate":
            expected.update(warehouse_enrollments=1, warehouse_balances=1)
        else:
            expected["flow_tasks"] = 1
            if doc["operation"] in OUT:
                expected["warehouse_holds"] = 1
    else:
        expected.update(flow_stock_moves=1, warehouse_entries=1,
                        warehouse_allocations=1, warehouse_allocation_lines=1)
        if doc["operation"] in OUT:
            expected["warehouse_holds"] = 1
    guard = Guard(e, "warehouse_" + action + "_" + doc["operation"], actor, expected=expected,
                  update=mutable(e, case_id, item_id=item_id), cases={case_id}, items={item_id})
    body, request, shown, meta = await submit(e, WH + str(case_id) + "/commands/" + action, WH + str(case_id))
    require(request == {"request_id": request["request_id"], "version": before_view["version"], "values": values},
            "原仓储命令CAS/凭据/值或多余字段错误")
    after_item, after_case = one(e, "flow_items", item_id), one(e, "flow_cases", case_id)
    require(after_case["version"] > before_view["version"] and after_item["version"] > before_item["version"],
            "原作业及库存锁版本未推进")
    require(body["version"] == shown["version"] == after_case["version"] and body["state"] == after_case["state"],
            "原命令响应、渲染GET与当前Case版本状态错误")
    done = [r for r in related(e, "flow_tasks", "case_id", case_id) if r["id"] == handoff["task_id"]][0]
    require(done["status"] == "done" and done["done_by"] == actor["id"], "原本人任务未独立完成")
    if action == "approve":
        require(after_item["quantity_milli"] == before_item["quantity_milli"]
                and after_item["inventory_value_cents"] == before_item["inventory_value_cents"]
                and after_item["unit_cost_cents"] == before_item["unit_cost_cents"],
                "主管批准不得冒充实际实物收发")
        approval = related(e, "warehouse_approvals", "case_id", case_id)
        require(len(approval) == 1 and approval[0]["actor_id"] == actor["id"]
                and approval[0]["value_cents"] == (value or 0) and approval[0]["evidence_id"] == proof["file"]["id"]
                and actor["id"] != after_case["created_by"], "原批准凭据、成本或独立主管错误")
        if doc["operation"] == "activate":
            enrollment = related(e, "warehouse_enrollments", "item_id", item_id)
            require(after_case["state"] == "completed" and len(enrollment) == 1
                    and enrollment[0]["case_id"] == case_id and enrollment[0]["baseline_quantity_milli"] == 0
                    and enrollment[0]["baseline_value_cents"] == 0 and enrollment[0]["stock_move_cursor"] == 0,
                    "零实物启用不应制造期初或原收发")
            require(not related(e, "warehouse_entries", "case_id", case_id)
                    and not related(e, "flow_stock_moves", "case_id", case_id), "零启用制造数量流水")
        else:
            require(after_case["state"] == "ready", "原批准后应等待本人实际收发")
            if doc["operation"] in OUT:
                hold = related(e, "warehouse_holds", "case_id", case_id)
                require(len(hold) == 1 and hold[0]["reason"] == "reserve"
                        and hold[0]["item_id"] == item_id and hold[0]["location_id"] == doc["source_location_id"]
                        and hold[0]["quantity_milli"] == doc["quantity_milli"] and hold[0]["actor_id"] == actor["id"],
                        "原批准出库应只追加本单本位置预占")
    else:
        require(after_case["state"] == "completed" and after_case["completed_date"], "实际收发未独立完成")
    meta.update(guard=guard.finish(), receipt=warehouse_receipt(e, request, case_id, actor, action),
                event=action_event(e, guard, case_id, actor, "warehouse_" + action),
                handoff=handoff, proof=proof)
    return meta


def physical_result(e, case_id, item_id, location, operation, quantity, value, *, original=None):
    moves = related(e, "flow_stock_moves", "case_id", case_id)
    entries = related(e, "warehouse_entries", "case_id", case_id)
    allocations = related(e, "warehouse_allocations", "case_id", case_id)
    approvals = related(e, "warehouse_approvals", "case_id", case_id)
    holds = related(e, "warehouse_holds", "case_id", case_id)
    require(len(moves) == len(entries) == len(allocations) == len(approvals) == 1, "单次实物收发缺唯一原事实")
    move, entry, allocation = moves[0], entries[0], allocations[0]
    inventory_id = e.manifest["users"][e.manifest["business_fixtures"]["vehicle_purchase"]["inventory_key"]]["id"]
    require(move["item_id"] == item_id and move["quantity_milli"] == quantity and move["value_cents"] == value
            and move["purpose"] == PURPOSES[operation] and move["original_id"] == (original["id"] if original else None)
            and move["actor_id"] == inventory_id and move["unit_cost_cents"] == abs(value) * 1000 // abs(quantity),
            "实物原流水量、成本、原批次、本人不一致")
    balance = one(e, "warehouse_balances", entry["balance_id"])
    require(balance["item_id"] == item_id and balance["location_id"] == location["id"]
            and balance["transit_case_id"] is None and entry["stock_move_id"] == move["id"]
            and entry["quantity_milli"] == quantity and entry["value_cents"] == value
            and entry["reason"] == move["purpose"] and entry["actor_id"] == inventory_id
            and entry["business_date"] == move["business_date"], "真实位置流水与原库存不一致")
    lines = related(e, "warehouse_allocation_lines", "allocation_id", allocation["id"])
    require(allocation["item_id"] == item_id and allocation["quantity_milli"] == quantity
            and allocation["purpose"] == move["purpose"] and allocation["status"] == "consumed"
            and allocation["stock_move_id"] == move["id"] and allocation["actor_id"] == inventory_id
            and len(lines) == 1 and lines[0]["location_id"] == location["id"]
            and lines[0]["quantity_milli"] == abs(quantity), "原准备量及消耗来源不匹配")
    if operation in OUT:
        require(len(holds) == 2 and holds[0]["reason"] == "reserve" and holds[1]["reason"] == "release"
                and holds[0]["quantity_milli"] == abs(quantity) and holds[1]["quantity_milli"] == -abs(quantity)
                and all(r["item_id"] == item_id and r["location_id"] == location["id"] for r in holds),
                "原出库预占与实际后释放不守恒")
    else:
        require(not holds, "正向入库不能制造出库预占")
    return {"case": one(e, "flow_cases", case_id), "document": one(e, "warehouse_documents", case_id),
            "stock_move": move, "entry": entry, "allocation": allocation, "allocation_lines": lines,
            "approval": approvals[0], "holds": holds, "tasks": related(e, "flow_tasks", "case_id", case_id)}


async def stock_read(e, context, credentials, fixture, item_id, quantity, value):
    actor = await login_as(e, context, credentials, fixture["finance_key"], "warehouse", 1)
    before = e.business_snapshot("before_warehouse_actual_stock")
    async with e.page.expect_response(lambda r: get_match(r, f"/api/warehouse/items/{item_id}/stock")) as pending:
        await e.page.goto(e.origin + f"/#warehouse-item/{item_id}")
    response = await pending.value
    view = await response.json()
    state = item_stock(e, item_id)
    require(response.status == 200 and view["id"] == item_id and view["enabled"]
            and view["quantity_milli"] == view["available_milli"] == quantity and view["reserved_milli"] == 0
            and view["value_cents"] == value and state["item"]["quantity_milli"] == quantity
            and state["item"]["inventory_value_cents"] == value and view["version"] == state["item"]["version"],
            "原实物库存页面、API、DB量值可用量不一致")
    require(len(state["balances"]) == len(view["balances"]) == 1, "本批库存只能在明确实际库位")
    for observed, family in ((view["balances"], state["balances"]), (view["entries"], state["entries"])):
        require(len(observed) == len(family), "原实物列表缺明细")
        for shown in observed:
            db = next(r for r in family if r["id"] == shown["id"])
            require(all(shown[k] == db[k] for k in shown if k != "location_name"), "原实物明细与DB字段不一致")
    await expect(e.page.locator("#main h1")).to_have_text("物资真实库位")
    await expect(e.page.locator("#main")).to_contain_text("账面 " + qty(quantity))
    await expect(e.page.locator("#main")).to_contain_text("门店库存价值 " + money(value) + " 元")
    await expect(e.page.locator('#main [data-act="wh-new"], #main [data-act="wh-action"]')).to_have_count(0)
    e.business_unchanged(before, "after_warehouse_actual_stock")
    return {"reader_id": actor["id"], "native_get": {"path": urlsplit(response.url).path, "status": response.status},
            "view": view, "db": state, "read_only": True}


async def operate(e, context, credentials, fixture, item_id, location, warehouse, operation,
                  quantity, delta_value, token, *, original=None):
    before = one(e, "flow_items", item_id)
    case_id, created = await create_warehouse(e, context, credentials, fixture, item_id, location,
        operation, quantity, original=original, warehouse=warehouse, token=token)
    approved = await warehouse_command(e, context, credentials, fixture, case_id, item_id, "approve", token,
                                       value=delta_value if operation == "other_in" else None)
    executed = await warehouse_command(e, context, credentials, fixture, case_id, item_id, "execute", token)
    signed = -quantity if operation in OUT else quantity
    # Costs follow original source remainder for returns, or the original weighted average.
    if original:
        prior = e.db.rows("SELECT quantity_milli,value_cents FROM flow_stock_moves WHERE original_id=? AND case_id<>? ORDER BY id",
                          (original["id"], case_id))
        remaining = abs(original["quantity_milli"]) - sum(abs(r["quantity_milli"]) for r in prior)
        remaining_value = abs(original["value_cents"]) - sum(abs(r["value_cents"]) for r in prior)
        calculated = remaining_value if quantity == remaining else (2 * remaining_value * quantity + remaining) // (2 * remaining)
    elif operation in OUT:
        calculated = before["inventory_value_cents"] if quantity == before["quantity_milli"] else (
            2 * before["inventory_value_cents"] * quantity + before["quantity_milli"]) // (2 * before["quantity_milli"])
    else:
        calculated = delta_value
    require(delta_value == (-calculated if signed < 0 else calculated), "本批样例成本与原算法不一致")
    facts = physical_result(e, case_id, item_id, location, operation, signed, delta_value, original=original)
    stock = await stock_read(e, context, credentials, fixture, item_id,
                            before["quantity_milli"] + signed, before["inventory_value_cents"] + delta_value)
    expected_average = (2 * stock["db"]["item"]["inventory_value_cents"] * 1000 + stock["db"]["item"]["quantity_milli"]) // (2 * stock["db"]["item"]["quantity_milli"])
    require(stock["db"]["item"]["unit_cost_cents"] == expected_average, "原成本分/数量千分位平均算法错误")
    return {"created": created, "approved": approved, "executed": executed, "db": facts, "stock": stock}


def finance_facts(e, case_id):
    case = one(e, "flow_cases", case_id)
    orders = related(e, "business_finance_orders", "case_id", case_id)
    require(len(orders) == 1, "供应方应收原Order不唯一")
    order = dict(orders[0]); order["values"] = json.loads(order["values"])
    batches = related(e, "business_finance_cash_batches", "case_id", case_id)
    return {"case": case, "order": order,
        "receivables": related(e, "business_finance_return_receivables", "case_id", case_id),
        "payments": related(e, "flow_payment_links", "case_id", case_id), "batches": batches,
        "allocations": [r for b in batches for r in related(e, "business_finance_cash_allocations", "batch_id", b["id"])],
        "cash": [one(e, "cash_entries", b["cash_id"]) for b in batches],
        "tasks": related(e, "flow_tasks", "case_id", case_id),
        "events": related(e, "business_finance_events", "case_id", case_id)}


def finance_view(e, view):
    f = finance_facts(e, view["case"]["id"])
    for key in ("case", "order"):
        expected = dict(f[key])
        if key == "case":
            expected["data"] = json.loads(expected["data"])
        require(all(view[key].get(k) == v for k, v in expected.items() if k not in {"created_at", "updated_at"}),
                "供应方财务页面字段与原DB不匹配：" + key)
    require(view["batches"] == f["batches"] and sorted(view["allocations"], key=lambda r: r["id"]) == f["allocations"],
            "供应方实际现金批次/分配与原DB不一致")
    if f["receivables"]:
        require(len(f["receivables"]) == 1, "原应收不是唯一")
        r = f["receivables"][0]
        target = view["return_target"]
        received = sum(p["amount_cents"] * (1 if p["direction"] == "in" else -1) for p in f["payments"])
        require(target == {"receivable_id": r["id"], "source_case_id": r["case_id"],
            "original_amount_cents": r["amount_cents"], "target_cents": r["amount_cents"],
            "received_cents": received, "overpayment_cents": 0, "refund_reserved_cents": 0, "revisions": []},
            "退物成本、应收目标和已收款被混算")
    return f


async def collect_other_return(e, context, credentials, fixture, source, supplier, account, token):
    move, source_case = source["db"]["stock_move"], source["db"]["case"]
    require(move["purpose"] == "wh_other_return" and move["quantity_milli"] == -500
            and move["value_cents"] == -200 and source_case["state"] == "completed",
            "085前序必须是本次实际完成原其他入库退货")
    actor = await login_as(e, context, credentials, fixture["finance_key"], "business-finance", 1)
    await expect(e.page.locator("#main h1")).to_have_text("业务财务结算")
    async with e.page.expect_response(lambda r: get_match(r, "/api/business-finance/other-returns")) as pending:
        await e.click('#main [data-act="business-finance-other"]', "财务申请本次原实际退货应收")
    response = await pending.value
    candidates = (await response.json())["items"]
    choice = next((r for r in candidates if r["stock_move_id"] == move["id"]), None)
    require(response.status == 200 and choice and choice["case_id"] == source_case["id"]
            and choice["source_version"] == one(e, "flow_cases", source_case["id"])["version"]
            and choice["quantity_milli"] == 500 and choice["value_cents"] == 200, "原应收候选未匹配本次原批次")
    await expect(e.page.locator("#modal-title")).to_have_text("其他入库退货应收")
    label = choice["number"] + " · " + choice["item_name"] + " · 原成本" + money(200) + "元"
    await select_value(e, '#modal [name="source"]', label, "选择这次已实际完成的原退货")
    await select_value(e, '#modal [name="supplier"]', supplier["name"], "选择同轮确切原供应方")
    await e.fill('#modal [name="amount"]', "2.00", "明确合成供应方应退金额")
    reason = "合成供应方确认本次原其他入库退货应收2元，退物成本与到账分别核对"
    await e.fill('#modal [name="reason"]', reason, "填写供应方原应退事实依据")
    guard = Guard(e, "other_return_receivable_request", actor,
        expected={**FINANCE_COMMON, "flow_cases": 1, "flow_tasks": 1, "business_finance_orders": 1},
        new_kind="business_finance")
    body, request, shown, meta = await submit_new(e, "/api/business-finance/orders", BF, financial=True)
    case_id = body["case"]["id"]
    require({k: v for k, v in request.items() if k != "request_id"} == {
        "customer_id": None, "purpose": "other_return", "reason": reason, "values": {
            "stock_move_id": move["id"], "source_version": choice["source_version"],
            "supplier_id": supplier["id"], "amount_cents": 200}}, "应收原申请源ID/版本/金额错误")
    f = finance_view(e, shown)
    require(f["order"]["status"] == "draft" and f["order"]["requested_by"] == actor["id"]
            and not f["receivables"] and not f["payments"] and not f["cash"], "应收申请不能产生批准或现金")
    created = {"native": meta, "guard": guard.finish(),
        "receipt": finance_receipt(e, request, actor, body, finance_action="create"),
        "event": action_event(e, guard, case_id, actor, "business_finance_create", finance=True), "db": f}
    stages = []
    reference = "WO-RETURN-" + token
    for action, role, key in (("approve", "manager", "business_finance_review"),
                              ("collect", "finance", "business_finance_execute")):
        actor, before, handoff = await responsible(e, context, credentials, fixture, role, case_id, key, financial=True)
        proof = await upload_original(e, case_id, actor, "evidence" if action == "approve" else "receipt",
                                      "supplier-return-" + action, token, financial=True)
        await original_form(e, "business-finance-action", action,
                            "独立复核批准" if action == "approve" else "登记真实到账并分配")
        await choose_file(e, proof, "evidence" if action == "approve" else "receipt")
        stage_reason = "本轮合成供应方原退货" + ("应退目标独立复核" if action == "approve" else "实际到账2元，原库存不重复办理")
        await e.fill('#modal [name="reason"]', stage_reason, "记录独立批准或实际到账依据")
        values = {"evidence_id": proof["file"]["id"], "reason": stage_reason, "source_versions": {}}
        expected = dict(FINANCE_COMMON)
        if action == "approve":
            require(actor["id"] != before["order"]["requested_by"], "085不得自批")
            expected.update(business_finance_return_receivables=1, flow_tasks=1)
        else:
            await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
            await e.fill('#modal [name="reference"]', reference, "记录唯一合成原到账流水号")
            await e.fill('#modal [name="amount"]', "2.00", "登记本次实际收到2元")
            values.update(account_id=account["id"], reference=reference, amount_cents=200)
            expected.update(cash_entries=1, business_finance_cash_batches=1,
                            business_finance_cash_allocations=1, flow_payment_links=1)
        guard = Guard(e, "supplier_return_" + action, actor, expected=expected,
            update=mutable(e, case_id, finance=True, account_id=account["id"] if action == "collect" else None),
            cases={case_id})
        body, request, shown, meta = await submit(e, BF + str(case_id) + "/actions/" + action, BF + str(case_id))
        require(request == {"request_id": request["request_id"], "version": before["order"]["version"],
                            "case_version": before["case"]["version"], "values": values}, "085双版本或原参数错误")
        f = finance_view(e, shown)
        require(f["case"]["version"] > before["case"]["version"] and f["order"]["version"] > before["order"]["version"],
                "085原Case/Order版本未推进")
        done = next(t for t in f["tasks"] if t["id"] == handoff["task_id"])
        require(done["status"] == "done" and done["done_by"] == actor["id"], "085本人任务未完成")
        receivable = f["receivables"][0]
        require(receivable["stock_move_id"] == move["id"] and receivable["supplier_id"] == supplier["id"]
                and receivable["amount_cents"] == receivable["value_cents"] == 200
                and receivable["quantity_milli"] == 500
                and receivable["approved_by"] == e.manifest["users"][fixture["manager_key"]]["id"],
                "原物资退回/成本/供应方应收批准不一致")
        require(f["order"]["status"] == ("approved" if action == "approve" else "completed"), "085状态错误")
        if action == "approve":
            require(not f["cash"] and not f["payments"] and receivable["evidence_id"] == proof["file"]["id"],
                    "批准应收不能冒充现金到账")
        else:
            require(len(f["cash"]) == len(f["payments"]) == len(f["batches"]) == len(f["allocations"]) == 1,
                    "085实际现金与原款分配不是唯一")
            cash, payment, batch, allocation = f["cash"][0], f["payments"][0], f["batches"][0], f["allocations"][0]
            require(cash["direction"] == "in" and cash["category"] == "business_finance_collection"
                    and cash["amount_cents"] == payment["amount_cents"] == batch["amount_cents"] == allocation["amount_cents"] == 200
                    and cash["created_by"] == actor["id"] and cash["account"] == account["name"]
                    and cash["voucher_no"] == payment["reference"] == reference and cash["approval_state"] == "approved"
                    and payment["account_id"] == account["id"] and payment["cash_id"] == batch["cash_id"] == cash["id"]
                    and payment["direction"] == "in" and payment["original_id"] is None
                    and batch["kind"] == "collection" and batch["actor_id"] == actor["id"]
                    and batch["evidence_id"] == proof["file"]["id"] and allocation["batch_id"] == batch["id"]
                    and allocation["payment_link_id"] == payment["id"] and allocation["case_id"] == case_id
                    and allocation["statement_line_id"] is None and payment["business_date"] == cash["business_date"]
                    and f["case"]["state"] == "completed" and f["case"]["completed_date"],
                    "085原到账账户、现金、分配、凭据或独立完成事实错误")
            await expect(e.page.locator("#main")).to_contain_text("实际收款")
            await expect(e.page.locator("#main")).to_contain_text("2.00")
        stages.append({"action": action, "native": meta, "guard": guard.finish(),
            "receipt": finance_receipt(e, request, actor, body, finance_action=str(case_id) + ":" + action),
            "event": action_event(e, guard, case_id, actor, "business_finance_" + action, finance=True),
            "handoff": handoff, "proof": proof, "db": f})
    require(one(e, "flow_cases", source_case["id"]) == source_case
            and one(e, "flow_stock_moves", move["id"]) == move, "应收和到账改写了已完成原退物")
    return {"created": created, "stages": stages, "db": f, "source_stock_move_id": move["id"],
            "source_case_id": source_case["id"], "account_id": account["id"], "actual_received_cents": 200}


def item_sources(e, item_id, location, warehouse, actions):
    state = item_stock(e, item_id)
    return {"item_id": item_id, "sku": state["item"]["sku"], "name": state["item"]["name"],
        "unit": state["item"]["unit"], "store_id": 1, "warehouse_id": warehouse["id"],
        "source_location_id": location["id"], "location_ids": [location["id"]],
        "enrollment_id": state["enrollment"]["id"], "activation_case_id": state["enrollment"]["case_id"],
        "case_ids": [r["db"]["case"]["id"] for r in actions],
        "stock_move_ids": [r["id"] for r in state["stock_moves"]], "entry_ids": [r["id"] for r in state["entries"]],
        "balance_ids": [r["id"] for r in state["balances"]],
        "current_quantity_milli": state["item"]["quantity_milli"],
        "current_value_cents": state["item"]["inventory_value_cents"], "current_version": state["item"]["version"]}


async def warehouse_operations_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, warehouse, location, supplier, account = source_dependencies(e, cp)
        token = uuid.uuid4().hex[:10].upper()
        cp.start("HK-046")
        consumable, consumable_master = await new_item(e, context, credentials, fixture, token, "consumable", "包")
        gift, gift_master = await new_item(e, context, credentials, fixture, token, "gift", "份")
        cp.note(new_zero_items={"consumable": consumable_master, "gift": gift_master})
        activations = []
        for item in (consumable, gift):
            case_id, created = await create_warehouse(e, context, credentials, fixture, item["id"], location,
                "activate", 0, warehouse=warehouse, token=token)
            approved = await warehouse_command(e, context, credentials, fixture, case_id, item["id"], "approve", token)
            zero = await stock_read(e, context, credentials, fixture, item["id"], 0, 0)
            activations.append({"item_id": item["id"], "case_id": case_id,
                                "created": created, "approved": approved, "zero_stock": zero})
            cp.note(zero_real_activations=activations)
        cin = await operate(e, context, credentials, fixture, consumable["id"], location, warehouse, "other_in", 4000, 1600, token)
        cp.note(consumable_actual_in=cin)
        gin = await operate(e, context, credentials, fixture, gift["id"], location, warehouse, "other_in", 2000, 600, token)
        await cp.passed(gift_actual_in=gin)
        actions_c, actions_g = [cin], [gin]
        cp.start("HK-056")
        consumed = await operate(e, context, credentials, fixture, consumable["id"], location, warehouse, "consumable", 1000, -400, token)
        actions_c.append(consumed)
        await cp.passed(original_consumption=consumed)
        cp.start("HK-048")
        returned = await operate(e, context, credentials, fixture, consumable["id"], location, warehouse,
                                 "consumable_return", 250, 100, token, original=consumed["db"]["stock_move"])
        actions_c.append(returned)
        await cp.passed(original_consumption_return=returned)
        cp.start("HK-059")
        gifted = await operate(e, context, credentials, fixture, gift["id"], location, warehouse, "gift", 500, -150, token)
        actions_g.append(gifted)
        await cp.passed(original_gift=gifted)
        cp.start("HK-050")
        gift_returned = await operate(e, context, credentials, fixture, gift["id"], location, warehouse,
                                     "gift_return", 250, 75, token, original=gifted["db"]["stock_move"])
        actions_g.append(gift_returned)
        await cp.passed(original_gift_return=gift_returned)
        cp.start("HK-057")
        other_returned = await operate(e, context, credentials, fixture, consumable["id"], location, warehouse,
                                      "other_in_return", 500, -200, token, original=cin["db"]["stock_move"])
        actions_c.append(other_returned)
        await cp.passed(original_other_in_return=other_returned, supplier_collection_not_yet_performed=True)
        cp.start("HK-060")
        disposed = await operate(e, context, credentials, fixture, consumable["id"], location, warehouse, "disposal", 250, -100, token)
        actions_c.append(disposed)
        await cp.passed(original_disposal=disposed)
        cp.start("HK-085")
        collected = await collect_other_return(e, context, credentials, fixture, other_returned, supplier, account, token)
        await cp.passed(original_other_return_finance=collected)
        final_c = await stock_read(e, context, credentials, fixture, consumable["id"], 2500, 1000)
        final_g = await stock_read(e, context, credentials, fixture, gift["id"], 1750, 525)
        cp.report["final_stock_protected_after_collection"] = {"consumable": final_c, "gift": final_g}
        cp.finish({"consumable": item_sources(e, consumable["id"], location, warehouse, actions_c),
                   "gift": item_sources(e, gift["id"], location, warehouse, actions_g),
                   "other_return_finance": {"source_stock_move_id": collected["source_stock_move_id"],
                       "source_case_id": collected["source_case_id"], "case_id": collected["db"]["case"]["id"],
                       "receivable_id": collected["db"]["receivables"][0]["id"],
                       "cash_id": collected["db"]["cash"][0]["id"],
                       "payment_link_id": collected["db"]["payments"][0]["id"],
                       "cash_batch_id": collected["db"]["batches"][0]["id"],
                       "cash_allocation_id": collected["db"]["allocations"][0]["id"],
                       "account_id": account["id"], "supplier_id": supplier["id"], "actual_received_cents": 200}})
    except Exception as exc:
        cp.failed(str(exc))
        raise


WAREHOUSE_OPERATIONS_SCENARIOS = ((SCENARIO, warehouse_operations_business, 720),)
