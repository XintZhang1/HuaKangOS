"""Nine original local material workflows, from same-run UI sources only.

All writes are visible native forms. Evidence uses
read-only SQLite; balances, money and fulfillment are never seeded here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, new_event, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from master_data_business import save_item
from vehicle_purchase_business import (
    checkbox, live_choice, master_form, master_page, nav, response_meta,
    save_master, select_value, submit, upload,
)

SCENARIO = "materials-hk069-045-054-083-070-072-073-051-061"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
CONTRACTS = (
    ("HK-069", "物资采购订货"), ("HK-045", "物资采购入库"),
    ("HK-054", "物资采购入库退货"), ("HK-083", "采购入库退货收款"),
    ("HK-070", "物资库存查询"), ("HK-072", "物资店内移库"),
    ("HK-073", "物资库存盘点"), ("HK-051", "物资盘盈入库查询"),
    ("HK-061", "盘亏出库查询"),
)
OP_TITLES = {"activate": "真实库位启用", "count": "库位盘点", "local_move": "店内移库"}
CASE_FIELDS = {"state", "data", "version", "updated_at", "completed_date"}
TASK_FIELDS = {"status", "assignee_id", "due_date", "done_by", "done_at", "version", "updated_at"}
ITEM_FIELDS = {"quantity_milli", "inventory_value_cents", "unit_cost_cents", "version", "updated_at"}
BALANCE_FIELDS = {"quantity_milli", "value_cents", "version", "updated_at"}
ALLOCATION_FIELDS = {"status", "stock_move_id", "version", "updated_at"}
COMMON = {"flow_events", "flow_request_receipts", "audit_logs"}
STOCK_APPEND = {"flow_stock_moves", "warehouse_entries", "warehouse_balances"}
WAREHOUSE_APPEND = {"warehouse_allocations", "warehouse_allocation_lines"}
# SQL identifiers below are a finite source-declared table set, never UI input.
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "flow_request_receipts", "audit_logs",
    "flow_items", "flow_accounts", "flow_files", "file_security", "file_scan_events",
    "cash_entries", "master_locations", "master_receipts", "master_item_profiles",
    "master_suppliers", "master_warehouses", "flow_stock_moves",
    "procurement_orders", "procurement_lines", "procurement_receipts",
    "procurement_returns", "procurement_return_lines", "procurement_return_postings",
    "procurement_return_valuations", "procurement_payments",
    "procurement_prepayment_facilities", "procurement_prepayment_requests",
    "procurement_prepayment_decisions", "procurement_prepayment_disbursements",
    "procurement_payment_allocations", "warehouse_documents", "warehouse_approvals",
    "warehouse_enrollments", "warehouse_balances", "warehouse_entries", "warehouse_holds",
    "warehouse_allocations", "warehouse_allocation_lines", "warehouse_count_observations",
}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        source = {r["id"]: r for r in json.loads(raw)["requirements"]}
        rows = []
        for key, title in CONTRACTS:
            binding = source[key]
            require(binding["source_review_status"] == "source_reviewed", key + " 原合同未审阅")
            require(binding["title"] == title, key + " 原需求名称不匹配")
            require(any(c["check_id"] == key + "-business" for c in binding["acceptance_checks"]), key + " 原check缺失")
            rows.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                    "status": "not_tested", "criteria": ["本人原页面输入及结果", "原API、版本、任务、原流水与DB一致",
                        "旧原行、其他业务及金额数量保护"], "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}, "conditional_checks": []})
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in CONTRACTS],
            "complete": False, "passed": False, "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution": "native_browser_original_forms", "requirements": rows,
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "human_acceptance": "pending", "conditions": {"synthetic_money_and_physical_inputs": True,
                "production_bank_or_physical_handover_acceptance": False, "file_scan": "original_structure_only_not_clamav",
                "cross_store_transfer_acceptance": False, "postgresql_or_employee_acceptance": False},
            "out_of_scope": ["HK-055", "HK-047", "HK-071", "精品/耗材/礼品/其他材料来源及维修另原链"]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] != "passed", "不覆盖已完成check")
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def note(self, **values):
        self.active["acceptance_checks"][0]["evidence"].update(values)
        self.save()

    async def passed(self, **values):
        self.note(**values)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
            self.report["failed_requirement"] = self.active["id"]
        for r in self.report["requirements"]:
            if r["status"] == "running":
                r["status"] = r["acceptance_checks"][0]["status"] = "partial"
                r["incomplete_reason"] = "后继依赖未完成，失败后终止，不重放"
        self.report.update(error=self.e.scrub(error),
            executed_requirements=sum(r["status"] != "not_tested" for r in self.report["requirements"]),
            passed_requirements=sum(r["status"] == "passed" for r in self.report["requirements"]))
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "九项物资check未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=9, passed_requirements=9, material_sources=sources)
        self.save()
        self.e.observe("materials_original_business_checkpoint", {"path": str(self.path), "material_sources": sources,
            "business_accepted": False, "full_193_business_acceptance": False})


def rows(e, table):
    require(table in TABLES, "非已审阅表标识")
    pk = "file_id" if table == "file_security" else "id"
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {pk}")


def one(e, table, record_id):
    require(table in TABLES, "非已审阅表标识")
    found = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (record_id,))
    require(len(found) == 1, "明确原ID不存在或不唯一：" + table)
    return found[0]


def qty(value):
    require(type(value) is int, "数量须为整数千分位")
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    return sign + str(magnitude // 1000) + ("." + f"{magnitude % 1000:03d}".rstrip("0") if magnitude % 1000 else "")


def money(value):
    require(type(value) is int, "金额须为整数分")
    magnitude = abs(value)
    return ("-" if value < 0 else "") + f"{magnitude // 100:,}.{magnitude % 100:02d}"


class Guard:
    """Every untouched table and old immutable row stays byte-for-byte equal.

    Current mutable IDs permit only explicit source columns. Append permissions
    are action-specific; new rows must retain this store and finite owned IDs.
    """
    def __init__(self, e, label, *, append=(), update=None, cases=(), items=(), new_kind=None):
        self.e, self.label = e, label
        self.append, self.update = set(append), update or {}
        self.cases, self.items, self.new_kind = set(cases), set(items), new_kind
        require((self.append | self.update.keys()) <= TABLES, "守卫表未审阅")
        self.snapshot = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.snapshot["tables"].keys() | after["tables"].keys()
                   if self.snapshot["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "原确认影响未授权表：" + str(sorted(changed)))
        added, updates = {}, {}
        new_cases = set()
        if "flow_cases" in self.append:
            previous_ids = {r["id"] for r in self.old["flow_cases"]}
            for r in rows(self.e, "flow_cases"):
                if r["id"] not in previous_ids:
                    require(r["kind"] == self.new_kind and r["created_by"] == r["owner_id"], "新增原单类型/申请人不匹配")
                    new_cases.add(r["id"])
            require(len(new_cases) == 1, "一次创建必须唯一新原单")
        for table, previous in self.old.items():
            pk = "file_id" if table == "file_security" else "id"
            current = {r[pk]: r for r in rows(self.e, table)}
            previous_ids = {r[pk] for r in previous}
            updates[table] = []
            for old in previous:
                require(old[pk] in current, "旧原事实被删除：" + table)
                now = current[old[pk]]
                columns = {k for k in old if old[k] != now[k]}
                allowed = self.update.get(table, {}).get(old[pk], set())
                require(columns <= allowed, "旧原事实被覆盖：" + table + "/" + str(old[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updates[table].append({"id": old[pk], "columns": sorted(columns)})
            new = [r for key, r in current.items() if key not in previous_ids]
            require(not new or table in self.append, "仅允许更新的表出现新行：" + table)
            for r in new:
                if "store_id" in r:
                    require(r["store_id"] == self.e.manifest["business_fixtures"]["vehicle_purchase"]["store_id"], "新增事实串店：" + table)
                if "case_id" in r:
                    require(r["case_id"] in self.cases | new_cases, "新增事实串原单：" + table)
                if "item_id" in r and table not in {"procurement_lines"}:
                    require(r["item_id"] in self.items, "新增事实串物资：" + table)
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", r["balance_id"])["item_id"] in self.items, "新增库位流水串物资")
                if table == "warehouse_allocation_lines":
                    allocation = one(self.e, "warehouse_allocations", r["allocation_id"])
                    require(allocation["case_id"] in self.cases | new_cases and allocation["item_id"] in self.items, "新增准备位置串原单/物资")
            added[table] = [r[pk] for r in new]
        result = {"label": self.label, "changed_tables": sorted(changed), "appended_ids": added,
                  "updated_columns": updates, "protected_other_tables": True, "protected_old_facts": True}
        self.e.observe("material_original_row_guard", result)
        return result


def mutable(e, case_id, item_ids=(), *, balances=False, allocations=False, funds=False, returns=False, account_id=None):
    update = {"flow_cases": {case_id: CASE_FIELDS}, "flow_tasks": {
        r["id"]: TASK_FIELDS for r in rows(e, "flow_tasks") if r["case_id"] == case_id}}
    if item_ids:
        update["flow_items"] = {i: ITEM_FIELDS for i in item_ids}
    if balances:
        update["warehouse_balances"] = {r["id"]: BALANCE_FIELDS for r in rows(e, "warehouse_balances") if r["item_id"] in item_ids}
    if allocations:
        update["warehouse_allocations"] = {r["id"]: ALLOCATION_FIELDS for r in rows(e, "warehouse_allocations") if r["case_id"] == case_id}
    if funds:
        update["procurement_prepayment_requests"] = {r["id"]: {"status", "version", "updated_at"}
            for r in rows(e, "procurement_prepayment_requests") if r["case_id"] == case_id}
    if returns:
        update["procurement_returns"] = {r["id"]: {"status", "approved_by", "version", "updated_at"}
            for r in rows(e, "procurement_returns") if r["case_id"] == case_id}
    if account_id:
        update["flow_accounts"] = {account_id: {"version", "updated_at"}}
    return update


def facts(e, case_id):
    case = one(e, "flow_cases", case_id)
    case["data"] = json.loads(case["data"])
    tasks = e.db.rows("SELECT * FROM flow_tasks WHERE case_id=? ORDER BY id", (case_id,))
    events = e.db.rows("SELECT * FROM flow_events WHERE case_id=? ORDER BY id", (case_id,))
    for event in events:
        event["detail"] = json.loads(event["detail"])
    return {"case": case, "tasks": tasks, "events": events}


def open_task(e, case_id, key):
    found = [r for r in facts(e, case_id)["tasks"] if r["key"] == key and r["status"] == "open"]
    require(len(found) == 1, "原未完成待办不唯一：" + key)
    return found[0]


def request_receipt(e, request, case_id, actor):
    found = e.db.rows("SELECT * FROM flow_request_receipts WHERE request_key=?", (request["request_id"],))
    require(len(found) == 1 and found[0]["case_id"] == case_id and found[0]["actor_id"] == actor["id"], "原幂等回执缺失或串单")
    require(len(found[0]["digest"]) == 64, "原回执缺完整指纹")
    return {k: v for k, v in found[0].items() if k != "request_key"}


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许外置合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "数据库不是同次外置runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance.get("snapshot_stable") is True, "镜像未完整冻结")
    for name in ("material_business.py", "business_acceptance_catalog.json", "master_data_business.py",
                 "vehicle_purchase_business.py", "sales_business.py", "sales_order_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "同次脚本指纹变化：" + name)
    cp.report["mirror"] = {"sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": provenance["source_sha256"],
                           "script_sha256": provenance["script_sha256"]}
    master, purchase = fixed_dependency(e, cp, MASTER), fixed_dependency(e, cp, PURCHASE)
    item_evidence = checkpoint_evidence(master, "HK-183")
    location_evidence = checkpoint_evidence(master, "HK-184")
    item = one(e, "flow_items", item_evidence["item"]["id"])
    profile = one(e, "master_item_profiles", item_evidence["profile"]["id"])
    warehouse = one(e, "master_warehouses", location_evidence["warehouse"]["row"]["id"])
    location = one(e, "master_locations", location_evidence["location"]["row"]["id"])
    supplier = one(e, "master_suppliers", checkpoint_evidence(purchase, "HK-171")["supplier"]["id"])
    account = one(e, "flow_accounts", checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"])
    require(item == item_evidence["item"] and profile == item_evidence["profile"], "前置零库存物资或真实归类已变化")
    require(item["unit"] == "升" and item["quantity_milli"] == item["inventory_value_cents"] == 0 and item["active"], "本轮A不是零库存升材料")
    require(warehouse == location_evidence["warehouse"]["row"] and location == location_evidence["location"]["row"], "材料仓位前置已变化")
    require(location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials" and warehouse["active"] and location["active"], "材料仓/库位关系不匹配")
    require(supplier == checkpoint_evidence(purchase, "HK-171")["supplier"] and supplier["active"] and account["active"], "同次供应商/账户缺真实启用来源")
    fixture = dict(e.manifest["business_fixtures"]["vehicle_purchase"])
    for role in ("inventory", "manager", "finance"):
        selected = e.manifest["users"][fixture[role + "_key"]]
        require(selected["role"] == role and selected["id"] > 0, "缺真实本人岗位：" + role)
    require({r["store_id"] for r in (item, profile, warehouse, location, supplier, account)} == {fixture["store_id"]}, "同次前置串店")
    require(not e.db.rows("SELECT id FROM warehouse_enrollments WHERE item_id=?", (item["id"],)), "本轮物资已经由其他来源启用")
    cp.report["source_preconditions"] = {"item": item, "profile": profile, "warehouse": warehouse,
        "location": location, "supplier": supplier, "account": {k: account[k] for k in ("id", "store_id", "name", "active")}}
    cp.save()
    return fixture, item, warehouse, location, supplier, account


async def detail(e, context, credentials, fixture, role, case_id, domain):
    prefix = "/api/procurement/orders/" if domain == "procurement" else "/api/warehouse/cases/"
    actor = await login_as(e, context, credentials, fixture[role + "_key"], domain, fixture["store_id"])
    before = e.business_snapshot("before_material_detail")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == prefix + str(case_id)) as pending:
        await e.page.goto(e.origin + "/#" + domain + "/" + str(case_id))
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == case_id and body["store_id"] == fixture["store_id"], "原详情读取串单/串店")
    original = facts(e, case_id)["case"]
    require(body["version"] == original["version"] and body["state"] == original["state"], "原详情版本/状态与DB不一致")
    heading = body["supplier_name"] + " · 采购办理" if domain == "procurement" else body["operation_label"]
    await expect(e.page.locator("#main h1")).to_have_text(heading)
    await expect(e.page.locator("#main .pagehead")).to_contain_text(original["number"])
    if domain == "procurement" and role == "inventory":
        require("totals" not in body and not body["payments"] and all("unit_cost_cents" not in r for r in body["lines"]), "库管采购详情泄漏资金")
    e.business_unchanged(before, "after_material_detail")
    return actor, body


async def responsible(e, context, credentials, fixture, case_id, key, role, domain):
    task = open_task(e, case_id, key)
    actor = e.manifest["users"][fixture[role + "_key"]]
    evidence = {"task_id": task["id"], "task_key": key, "actor_id": actor["id"], "handoff_needed": task["assignee_id"] != actor["id"]}
    if evidence["handoff_needed"]:
        await login_as(e, context, credentials, fixture["manager_key"], "case/" + str(case_id), fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text(facts(e, case_id)["case"]["title"])
        await e.click(f'#main [data-act="assign"][data-id="{task["id"]}"]', "主管转交这项原待办")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, actor)
        await e.fill('#modal [name="reason"]', "本轮材料业务由本店已选本人独立经办", "填写明确岗位交接依据")
        guard = Guard(e, "material_task_handoff", append={"flow_events", "audit_logs"},
            update={"flow_tasks": {task["id"]: {"assignee_id", "version", "updated_at"}}}, cases={case_id})
        _, meta, _, request = await submit(e, f'/api/flow/tasks/{task["id"]}/assign', 200, f"/api/flow/cases/{case_id}")
        require(request == {"version": task["version"], "assignee_id": actor["id"], "reason": "本轮材料业务由本店已选本人独立经办"}, "原AssignInput合同错误")
        evidence.update(native=meta, guard=guard.finish())
        require(open_task(e, case_id, key)["version"] > task["version"], "原任务版本未推进")
    selected, body = await detail(e, context, credentials, fixture, role, case_id, domain)
    require(open_task(e, case_id, key)["assignee_id"] == selected["id"], "经办本人不是原待办接手人")
    e.observe("material_original_task_owner", evidence)
    return selected, body


async def evidence_file(e, case_id, actor, category, filename, text):
    guard = Guard(e, "material_file_upload", append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={case_id})
    key = await upload(e, case_id, actor, category, filename, text)
    guard.finish()
    return one(e, "flow_files", key)


async def choose(e, root, selector, search, label, value):
    lookup = root.locator(".lookup").filter(has=e.page.locator(selector))
    await expect(lookup).to_have_count(1)
    query = lookup.get_by_role("combobox")
    await expect(query).to_be_visible()
    e.action("fill", "查找明确原选项", value=search)
    await query.fill(search)
    option = lookup.get_by_role("option", name=label, exact=True)
    await expect(option).to_have_count(1)
    await expect(option).to_be_visible()
    e.action("click", "选择明确原选项", label=label)
    await option.click()
    await expect(lookup.locator("select")).to_have_value(str(value))


async def file_choice(e, field, file):
    titles = {"evidence": "业务凭据", "receipt": "收退款凭据", "procurement_contract": "采购合同与核价凭据"}
    await live_choice(e, field, file["name"], file["name"] + " · " + titles[file["category"]], expected_value=file["id"])


async def visible_original_button(e, selector, label):
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        group = button.locator('xpath=ancestor::details[1]')
        await expect(group).to_have_count(1)
        summary = group.locator(':scope > summary')
        await expect(summary).to_be_visible()
        e.action('click', '展开原操作组：' + label)
        await summary.click()
    await expect(button).to_be_visible()
    await expect(button).to_be_enabled()


async def action_form(e, domain, key, sub_id=None):
    act = "procurement-action" if domain == "procurement" else "wh-action"
    selector = f'#main [data-act="{act}"][data-key="{key}"]' + (f'[data-id="{sub_id}"]' if sub_id else "")
    await visible_original_button(e, selector, key)
    await e.click(selector, "办理原材料步骤 " + key)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def create_submit(e, path, domain, guard, actor):
    read_prefix = "/api/procurement/orders/" if domain == "procurement" else "/api/warehouse/cases/"
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path.startswith(read_prefix)
            and urlsplit(r.url).path[len(read_prefix):].isdigit()) as rendered:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "提交本人原材料申请")
        response = await pending.value
        body = await response.json()
        require(response.status == 201, "原材料创建返回拒绝：" + e.scrub(body.get("detail", "")))
    read = await rendered.value
    shown = await read.json()
    require(read.status == 200 and shown["id"] == body["id"], "创建后原详情读取错误")
    meta, request = await response_meta(e, response, body)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    title = shown["supplier_name"] + " · 采购办理" if domain == "procurement" else shown["operation_label"]
    await expect(e.page.locator("#main h1")).to_have_text(title)
    original = facts(e, body["id"])
    require(original["case"]["created_by"] == actor["id"] and original["case"]["version"] == shown["version"], "申请身份/版本不匹配")
    require(len(original["events"]) == 1 and original["events"][0]["actor_id"] == actor["id"]
        and original["events"][0]["action"] == ("procurement_create" if domain == "procurement" else "warehouse_create"), "原申请未唯一追加本人创建事件")
    metadata = {"native": meta, "request": request, "receipt": request_receipt(e, request, body["id"], actor), "guard": guard.finish()}
    return body["id"], metadata


async def command_submit(e, domain, case_id, key, actor, guard, expected_values):
    before = facts(e, case_id)
    path = (f"/api/procurement/orders/{case_id}/actions/" if domain == "procurement"
            else f"/api/warehouse/cases/{case_id}/commands/") + key
    render = ("/api/procurement/orders/" if domain == "procurement" else "/api/warehouse/cases/") + str(case_id)
    body, meta, shown, request = await submit(e, path, 200, render)
    after = facts(e, case_id)
    require(request["version"] == before["case"]["version"] and request["values"] == expected_values, "本人原提交版本/精确整数事实不匹配：" + key)
    require(after["case"]["version"] > before["case"]["version"] and body["version"] == shown["version"] == after["case"]["version"], "原版本未推进或渲染迟到")
    event = new_event(before, after, ("procurement_" if domain == "procurement" else "warehouse_") + key, actor["id"])
    require(event["before_state"] == before["case"]["state"] and event["after_state"] == after["case"]["state"], "原事件状态与提交不一致")
    result = {"native": meta, "submitted_values": expected_values, "event": event,
              "receipt": request_receipt(e, request, case_id, actor), "guard": guard.finish(), "db": after, "api": shown}
    e.observe("material_original_command", result)
    return shown, result


async def warehouse_create(e, context, credentials, fixture, item, operation, quantity, source=None, destination=None):
    actor = await login_as(e, context, credentials, fixture["inventory_key"], "warehouse", fixture["store_id"])
    await expect(e.page.locator("#main h1")).to_have_text("库位与仓储作业")
    selector = f'#main [data-act="wh-new"][data-operation="{operation}"]'
    await visible_original_button(e, selector, OP_TITLES[operation])
    await e.click(selector, "申请原" + OP_TITLES[operation])
    await expect(e.page.locator("#modal-title")).to_have_text(OP_TITLES[operation])
    await select_value(e, '#modal [name="item_id"]', item["id"], "选择同轮明确物资")
    if operation != "count":
        await e.fill('#modal [name="quantity"]', qty(quantity), "填写本次数量")
    if source:
        await select_value(e, '#modal [name="source"]', source["id"], "选择原实际库位")
    if destination and operation != "activate":
        await select_value(e, '#modal [name="destination"]', destination["id"], "选择接收实际库位")
    if operation == "activate":
        await select_value(e, '#modal [name="location"]', destination["id"], "明确零库存实际接收库位")
        await e.fill('#modal [name="location_qty"]', "0", "明确启用数量零")
    reason = "本轮合成材料" + OP_TITLES[operation] + "，凭实际输入及本单记录办理"
    await e.fill('#modal [name="reason"]', reason, "填写明确本次来源")
    business_day = await e.page.locator('#modal [name="due_date"]').input_value()
    require(len(business_day) == 10, "原UI业务日缺失")
    guard = Guard(e, "warehouse_create_" + operation, append=COMMON | {"flow_cases", "flow_tasks", "warehouse_documents"}
        | (WAREHOUSE_APPEND if operation == "activate" else set()), items={item["id"]}, new_kind="warehouse")
    case_id, meta = await create_submit(e, "/api/warehouse/cases", "warehouse", guard, actor)
    doc = one(e, "warehouse_documents", case_id)
    require(doc["operation"] == operation and doc["item_id"] == item["id"] and doc["quantity_milli"] == quantity,
            "原作业申请整数/物资不匹配")
    require(doc["source_location_id"] == (source["id"] if source else None)
            and doc["destination_location_id"] == (destination["id"] if destination and operation != "activate" else None), "原作业申请库位不匹配")
    require(facts(e, case_id)["case"]["due_date"] == business_day, "原作业期限不匹配")
    proof = await evidence_file(e, case_id, actor, "evidence", operation + "-" + str(case_id) + ".txt", reason)
    return case_id, proof, meta


async def warehouse_command(e, context, credentials, fixture, case_id, item_id, action, proof, *, quantity=None, counted=None):
    task_key, role = {"approve": ("wh_approve", "manager"), "capture": ("wh_capture", "inventory"),
        "post_count": ("wh_count_review", "manager"), "dispatch": ("wh_execute", "inventory"),
        "accept": ("wh_accept", "inventory")}[action]
    actor, body = await responsible(e, context, credentials, fixture, case_id, task_key, role, "warehouse")
    await action_form(e, "warehouse", action)
    await select_value(e, '#modal [name="evidence_id"]', proof["id"], "选择本单原实物依据")
    values = {"evidence_id": proof["id"]}
    if quantity is not None:
        await e.fill('#modal [name="quantity"]', qty(quantity), "填写本批实际接收量")
        values["quantity_milli"] = quantity
    if counted is not None:
        await e.fill('#modal [name="counted"]', qty(counted), "填写现场实盘结果")
        values["counted_quantity_milli"] = counted
    append = COMMON | {"flow_tasks"}
    if action == "approve":
        append |= {"warehouse_approvals"}
        if body["operation"] == "activate":
            append |= {"warehouse_enrollments", "warehouse_balances", "warehouse_entries"}
        if body["operation"] == "local_move":
            append |= {"warehouse_holds"}
    if action == "capture":
        append |= {"warehouse_count_observations"}
    if action == "post_count":
        append |= STOCK_APPEND | WAREHOUSE_APPEND
    if action in {"dispatch", "accept"}:
        append |= {"warehouse_balances", "warehouse_entries"}
        if action == "dispatch":
            append |= {"warehouse_holds"}
    guard = Guard(e, "warehouse_" + action, append=append,
        update=mutable(e, case_id, {item_id}, balances=True, allocations=True), cases={case_id}, items={item_id})
    return await command_submit(e, "warehouse", case_id, action, actor, guard, values)


def item_stock(e, item_id):
    item = one(e, "flow_items", item_id)
    balances = e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=? ORDER BY id", (item_id,))
    moves = e.db.rows("SELECT * FROM flow_stock_moves WHERE item_id=? ORDER BY id", (item_id,))
    entries = e.db.rows("SELECT e.* FROM warehouse_entries e JOIN warehouse_balances b ON b.id=e.balance_id WHERE b.item_id=? ORDER BY e.id", (item_id,))
    enrollment = e.db.rows("SELECT * FROM warehouse_enrollments WHERE item_id=?", (item_id,))
    require(len(enrollment) == 1 and sum(b["quantity_milli"] for b in balances) == item["quantity_milli"]
            and sum(b["value_cents"] for b in balances) == item["inventory_value_cents"], "门店Item与实际位置量值不守恒")
    require(sum(m["quantity_milli"] for m in moves) == item["quantity_milli"]
            and sum(m["value_cents"] for m in moves) == item["inventory_value_cents"], "本轮零期初与不可变收发量值不对平")
    for b in balances:
        source = [x for x in entries if x["balance_id"] == b["id"]]
        require(sum(x["quantity_milli"] for x in source) == b["quantity_milli"]
                and sum(x["value_cents"] for x in source) == b["value_cents"], "位置账与不可变流水不对平")
    return {"item": item, "enrollment": enrollment[0], "balances": balances, "stock_moves": moves, "entries": entries}


async def stock_page(e, context, credentials, fixture, role, item_id, *, quantity, value, reserved=0):
    await login_as(e, context, credentials, fixture[role + "_key"], "warehouse", fixture["store_id"])
    before = e.business_snapshot("before_material_stock_read")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/warehouse/items/{item_id}/stock") as pending:
        await e.page.goto(e.origin + f"/#warehouse-item/{item_id}")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == item_id and body["quantity_milli"] == quantity
        and body["reserved_milli"] == reserved and body["available_milli"] == quantity - reserved, "原库存API账面/可用/预占不匹配")
    original = item_stock(e, item_id)
    require(original["item"]["quantity_milli"] == quantity and original["item"]["inventory_value_cents"] == value, "原库存DB量值不匹配")
    require({b["id"] for b in body["balances"]} == {b["id"] for b in original["balances"]}, "原位置列表不完整")
    require({x["id"] for x in body["entries"]} == {x["id"] for x in original["entries"]}, "原位置流水列表不完整")
    for actual, displayed in ((original["balances"], body["balances"]), (original["entries"], body["entries"])):
        for shown in displayed:
            source = next(r for r in actual if r["id"] == shown["id"])
            for key in (shown.keys() & source.keys()) - {"business_date"}:
                require(shown[key] == source[key], "原库位读取字段与DB不一致：" + key)
    await expect(e.page.locator("#main h1")).to_have_text("物资真实库位")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(original["item"]["name"])
    await expect(e.page.locator("#main")).to_contain_text(f"账面 {qty(quantity)}，当前可用 {qty(quantity - reserved)}")
    if role == "inventory":
        require("value_cents" not in body and all("value_cents" not in b for b in body["balances"] + body["entries"]), "库管实际库存泄漏金额")
        await expect(e.page.locator("#main")).not_to_contain_text("门店库存价值")
    else:
        require(body["value_cents"] == value, "财务库存金额与DB不一致")
        await expect(e.page.locator("#main")).to_contain_text(f"门店库存价值 {money(value)} 元")
    e.business_unchanged(before, "after_material_stock_read")
    result = {"api": body, "db": original, "role": role, "read_only": True}
    e.observe("material_nonempty_original_stock_read", result)
    return result


async def procurement_command(e, context, credentials, fixture, case_id, key, item_ids, *, role, task_key=None,
                              file=None, amount=None, account=None, reference=None, funds=None, returned=None, original=None):
    if task_key:
        actor, body = await responsible(e, context, credentials, fixture, case_id, task_key, role, "procurement")
    else:
        actor, body = await detail(e, context, credentials, fixture, role, case_id, "procurement")
    await action_form(e, "procurement", key, funds["id"] if funds else returned["id"] if returned else None)
    values = {}
    if funds:
        values.update(funds_request_id=funds["id"], funds_version=funds["version"])
    if returned:
        values.update(return_id=returned["id"], return_version=returned["version"])
    if key in {"prepay_request", "prepay_approve", "return_approve"}:
        reason = "本次原材料" + key + "，按本单合成原凭据核对"
        await e.fill('#modal [name="reason"]', reason, "填写本次原办理依据")
        values["reason"] = reason
    if key == "prepay_request":
        business_day = facts(e, case_id)["case"]["business_date"]
        await e.fill('#modal [name="valid_until"]', business_day, "使用本单原业务日作为有效期")
        values["valid_until"] = business_day
    if amount is not None:
        await e.fill('#modal [name="amount"]', f"{amount // 100}.{amount % 100:02d}", "填写本次真实合成款项")
        values["amount_cents"] = amount
    if account:
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        await e.fill('#modal [name="reference"]', reference, "填写唯一原款凭证号")
        values.update(account_id=account["id"], reference=reference)
    if original:
        select = e.page.locator('#modal select[name="original_payment_id"]')
        option = select.locator(f'option[value="{original["id"]}"]')
        await expect(option).to_have_count(1)
        label = await option.text_content()
        require(original["reference"] in label and "本笔剩余 10.00 元" in label, "原退款选项缺明确释放款项来源")
        await live_choice(e, "original_payment_id", original["reference"], label, expected_value=original["id"])
        values["original_payment_id"] = original["id"]
    if file:
        await file_choice(e, "evidence_id", file)
        values["evidence_id"] = file["id"]
    if key == "prepay_pay":
        await checkbox(e, '#modal [name="confirmed"]', True, "财务本人明确已核实际原付款")
        values["confirmed"] = True
    append = COMMON | {"flow_tasks", "procurement_payment_allocations"}
    if key == "prepay_request":
        append |= {"procurement_prepayment_facilities", "procurement_prepayment_requests"}
    if key == "prepay_approve":
        append |= {"procurement_prepayment_decisions"}
    if key == "prepay_pay":
        append |= {"procurement_prepayment_disbursements"}
    if key in {"pay", "refund", "prepay_pay"}:
        append |= {"procurement_payments", "cash_entries"}
    if key == "return_dispatch":
        append |= STOCK_APPEND | {"procurement_return_postings", "procurement_return_valuations"}
    changed_items = item_ids if key in {"return_approve", "return_dispatch"} else ()
    guard = Guard(e, "procurement_" + key, append=append,
        update=mutable(e, case_id, changed_items, balances=key == "return_dispatch", allocations=key == "return_dispatch",
            funds=bool(funds), returns=bool(returned), account_id=account["id"] if account else None),
        cases={case_id}, items=set(item_ids))
    shown, meta = await command_submit(e, "procurement", case_id, key, actor, guard, values)
    return shown, meta


async def inline_receive(e, context, credentials, fixture, case_id, items, quantities, location, warehouse, proof):
    actor, body = await responsible(e, context, credentials, fixture, case_id, "procurement_receive", "inventory", "procurement")
    await action_form(e, "procurement", "receive")
    line_ids = {r["item_id"]: r["id"] for r in body["lines"]}
    for item, quantity in zip(items, quantities):
        await e.fill(f'#modal [name="quantity_{line_ids[item["id"]]}"]', f"{quantity // 1000}.{quantity % 1000:03d}", "填写本批明确原到货量")
    await file_choice(e, "evidence", proof)
    await e.click('#modal [data-prep-open]', "分配本次真实收货库位")
    await expect(e.page.locator('#modal [data-prep-body]')).to_be_visible()
    for item, quantity in zip(items, quantities):
        root = e.page.locator(f'#modal [data-prep-item="{item["id"]}"]')
        label = warehouse["name"] + " · " + location["name"]
        await choose(e, root, "select[data-prep-bin]", location["name"], label, location["id"])
        e.action("fill", "填写该原库位接收量", item_id=item["id"], quantity_milli=quantity)
        await root.locator('[data-prep-quantity]').fill(f"{quantity // 1000}.{quantity % 1000:03d}")
    before_version = facts(e, case_id)["case"]["version"]
    before_allocations = {r["id"] for r in rows(e, "warehouse_allocations")}
    guard = Guard(e, "procurement_inline_position_prepare", append=COMMON | WAREHOUSE_APPEND,
        update=mutable(e, case_id, allocations=True), cases={case_id}, items={i["id"] for i in items})
    responses = []
    def collect(response):
        if response.request.method == "POST" and urlsplit(response.url).path == f"/api/warehouse/allocations/{case_id}":
            responses.append(response)
    e.page.on("response", collect)
    try:
        await e.click('#modal [data-prep-save]', "保存本批精确库位准备")
        await expect(e.page.locator('#modal [data-prep-status]')).to_have_text("库位已保存。核对本表后，再确认实际收发。")
    finally:
        e.page.remove_listener("response", collect)
    require(len(responses) == len(items), "库位准备未逐项完整提交")
    native = []
    for index, response in enumerate(responses):
        reply = await response.json()
        require(response.status == 200 and reply["case_id"] == case_id and reply["prepared"] is True, "库位准备真实失败")
        meta, request = await response_meta(e, response, reply)
        require(request["version"] == before_version + index, "逐项库位准备版本未依原响应推进")
        expected = {"item_id": items[index]["id"], "quantity_milli": quantities[index], "purpose": "procurement_receipt",
                    "locations": [{"location_id": location["id"], "quantity_milli": quantities[index]}]}
        require(request["values"] == expected, "库位准备精确原引用不匹配")
        native.append({"native": meta, "receipt": request_receipt(e, request, case_id, actor)})
    prepared = [r for r in rows(e, "warehouse_allocations") if r["id"] not in before_allocations]
    require(len(prepared) == len(items) and all(r["status"] == "prepared" for r in prepared), "没有逐项真实准备行")
    for item, quantity in zip(items, quantities):
        allocation = [r for r in prepared if r["item_id"] == item["id"]]
        require(len(allocation) == 1 and allocation[0]["quantity_milli"] == quantity
            and allocation[0]["actor_id"] == actor["id"] and allocation[0]["purpose"] == "procurement_receipt", "原准备行没有精确来源")
        lines = e.db.rows("SELECT * FROM warehouse_allocation_lines WHERE allocation_id=?", (allocation[0]["id"],))
        require(len(lines) == 1 and lines[0]["location_id"] == location["id"] and lines[0]["quantity_milli"] == quantity, "原准备库位行不匹配")
    preparation = {"native": native, "allocations": prepared, "guard": guard.finish()}
    before_receipt_ids = {r["id"] for r in e.db.rows("SELECT * FROM procurement_receipts WHERE case_id=?", (case_id,))}
    guard = Guard(e, "procurement_receive", append=COMMON | {"flow_tasks", "procurement_receipts", "procurement_payment_allocations"} | STOCK_APPEND,
        update=mutable(e, case_id, {i["id"] for i in items}, balances=True, allocations=True), cases={case_id}, items={i["id"] for i in items})
    values = {"lines": [{"line_id": line_ids[i["id"]], "quantity_milli": q} for i, q in zip(items, quantities)], "evidence_id": proof["id"]}
    shown, evidence = await command_submit(e, "procurement", case_id, "receive", actor, guard, values)
    require(all(one(e, "warehouse_allocations", a["id"])["status"] == "consumed" for a in prepared), "原验收未消费明确准备来源")
    receipts = [r for r in e.db.rows("SELECT * FROM procurement_receipts WHERE case_id=? ORDER BY id", (case_id,)) if r["id"] not in before_receipt_ids]
    require(len(receipts) == len(items), "本批实际验收没有逐行唯一来源")
    moves = []
    for item, quantity in zip(items, quantities):
        receipt = [r for r in receipts if r["line_id"] == line_ids[item["id"]]]
        require(len(receipt) == 1 and receipt[0]["quantity_milli"] == quantity and receipt[0]["evidence_id"] == proof["id"], "本批原验收引用不匹配")
        receipt = receipt[0]
        move = one(e, "flow_stock_moves", receipt["stock_move_id"])
        allocation = next(r for r in prepared if r["item_id"] == item["id"])
        require(move["case_id"] == case_id and move["item_id"] == item["id"] and move["actor_id"] == actor["id"]
            and move["quantity_milli"] == quantity and move["value_cents"] == receipt["value_cents"]
            and move["purpose"] == "procurement_receipt" and move["original_id"] is None
            and one(e, "warehouse_allocations", allocation["id"])["stock_move_id"] == move["id"], "本批StockMove没有精确原验收/准备来源")
        position = e.db.rows("SELECT * FROM warehouse_entries WHERE stock_move_id=?", (move["id"],))
        require(sum(r["quantity_milli"] for r in position) == quantity and sum(r["value_cents"] for r in position) == move["value_cents"], "本批原库位流水与实际收发不对平")
        moves.append(move)
    return {"preparation": preparation, "receive": evidence, "api": shown, "receipts": receipts, "stock_moves": moves}


def cash_fact(e, case_id, amount, direction, reference, account, actor, original=None):
    payments = e.db.rows("SELECT * FROM procurement_payments WHERE case_id=? AND reference=?", (case_id, reference))
    require(len(payments) == 1, "实际款项未唯一追加")
    payment = payments[0]
    cash = one(e, "cash_entries", payment["cash_id"])
    require(payment["amount_cents"] == amount and payment["direction"] == direction and payment["account_id"] == account["id"]
        and payment["original_id"] == (original["id"] if original else None), "原付款/退款来源金额账户不匹配")
    require(cash["amount_cents"] == amount and cash["direction"] == direction and cash["account"] == account["name"]
        and cash["voucher_no"] == reference and cash["created_by"] == actor["id"] and cash["approval_state"] == "approved"
        and cash["category"] == ("procurement_payment" if direction == "out" else "procurement_refund"), "实际现金原分类/岗位/凭据不匹配")
    return {"payment": payment, "cash": cash}


async def count_capture(e, context, credentials, fixture, item_id, location, counted):
    item = one(e, "flow_items", item_id)
    case_id, proof, creation = await warehouse_create(e, context, credentials, fixture, item, "count", 0, source=location)
    _, approval = await warehouse_command(e, context, credentials, fixture, case_id, item_id, "approve", proof)
    _, capture = await warehouse_command(e, context, credentials, fixture, case_id, item_id, "capture", proof, counted=counted)
    observation = e.db.rows("SELECT * FROM warehouse_count_observations WHERE case_id=?", (case_id,))
    require(len(observation) == 1 and observation[0]["counted_quantity_milli"] == counted
        and observation[0]["actor_id"] == e.manifest["users"][fixture["inventory_key"]]["id"], "原现场实盘观察不匹配")
    return case_id, proof, {"creation": creation, "approval": approval, "capture": capture, "observation": observation[0]}


async def count_post(e, context, credentials, fixture, case_id, item_id, proof, *, baseline, counted, bridge, delta):
    actor, body = await detail(e, context, credentials, fixture, "manager", case_id, "warehouse")
    count = body["count"]
    expected = {"baseline_quantity_milli": baseline, "counted_quantity_milli": counted, "difference_milli": delta,
                "movement_bridge_milli": bridge, "current_book_milli": baseline + bridge, "projected_milli": counted + bridge}
    require(all(count[k] == v for k, v in expected.items()), "盘点期间衔接原值不匹配")
    for label, number in (("开始账面", baseline), ("现场实盘", counted), ("原观察差额", delta), ("期间净收发", bridge),
                          ("当前账面", baseline + bridge), ("差额处理后应有", counted + bridge)):
        field = e.page.locator('#main .formgrid > div').filter(has_text=label)
        await expect(field).to_have_count(1)
        await expect(field).to_contain_text(qty(number))
    before_moves = e.db.rows("SELECT * FROM flow_stock_moves WHERE case_id=? ORDER BY id", (case_id,))
    _, posting = await warehouse_command(e, context, credentials, fixture, case_id, item_id, "post_count", proof)
    moves = e.db.rows("SELECT * FROM flow_stock_moves WHERE case_id=? ORDER BY id", (case_id,))
    require(not before_moves, "盘点复核前已提前过账")
    require(len(moves) == (1 if delta else 0), "零盘差不得记物资流水，非零须唯一过账")
    if delta:
        require(moves[0]["quantity_milli"] == delta and moves[0]["value_cents"] == delta and moves[0]["purpose"] == "wh_count"
            and moves[0]["actor_id"] == actor["id"], "原盘差数量/可靠成本/经办不匹配")
    require(facts(e, case_id)["case"]["state"] == "completed" and all(t["status"] != "open" for t in facts(e, case_id)["tasks"]), "盘点原任务未结束")
    return {"case_id": case_id, "prepost_api": body, "posting": posting, "stock_moves": moves, "stock": item_stock(e, item_id)}


async def query_count_source(e, context, credentials, fixture, case_id, item_id, expected_delta):
    _, body = await detail(e, context, credentials, fixture, "finance", case_id, "warehouse")
    before = e.business_snapshot("before_material_count_query")
    moves = e.db.rows("SELECT * FROM flow_stock_moves WHERE case_id=? ORDER BY id", (case_id,))
    require(len(moves) == len(body["stock_moves"]) == 1 and moves[0]["quantity_milli"] == expected_delta
        and moves[0]["value_cents"] == expected_delta and body["stock_moves"][0]["id"] == moves[0]["id"], "盘盈亏原非空查询与实际来源不一致")
    panel = e.page.locator('#main .panel').filter(has=e.page.get_by_text("本单实物收发", exact=True))
    await expect(panel).to_contain_text(str(moves[0]["id"]))
    await expect(panel).to_contain_text(qty(expected_delta))
    await expect(panel).to_contain_text(money(expected_delta))
    e.business_unchanged(before, "after_material_count_query")
    return {"case_id": case_id, "api": body, "stock_move": moves[0], "db": facts(e, case_id), "read_only": True}


async def replenishment_query(e, context, credentials, fixture, items):
    """Original nonempty material table, including this run's low-stock row."""
    await login_as(e, context, credentials, fixture["finance_key"], "warehouse", fixture["store_id"])
    before = e.business_snapshot("before_material_replenishment_table")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/analytics") as pending:
        await e.page.goto(e.origin + "/#table/materials")
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原材料及补货明细读取失败")
    table = body["tables"]["materials"]
    await expect(e.page.locator("#main h1")).to_have_text(table["title"])
    selected = []
    for supplied in items:
        item = one(e, "flow_items", supplied["id"])
        candidates = [r for r in table["rows"] if r.get("route", {}).get("type") == "master"
            and r["route"].get("module") == "items" and r["route"].get("id") == item["id"]]
        require(len(candidates) == 1, "原材料明细缺本轮实际Item来源")
        row = candidates[0]
        status = "需补货" if item["quantity_milli"] <= item["reorder_milli"] else "正常"
        require(row["values"][0] == item["sku"] and row["values"][2:] == [item["name"], qty(item["quantity_milli"]),
            "0", qty(item["quantity_milli"]), item["unit"], money(item["inventory_value_cents"]), status], "原材料补货/数量/成本明细不匹配")
        ui = e.page.locator('#main tbody tr').filter(has_text=item["sku"])
        await expect(ui).to_have_count(1)
        for value in row["values"]:
            await expect(ui).to_contain_text(str(value))
        selected.append({"item_id": item["id"], "reorder_milli": item["reorder_milli"], "row": row})
    require(any(r["row"]["values"][-1] == "需补货" for r in selected), "本轮补货查询没有真实非空来源")
    e.business_unchanged(before, "after_material_replenishment_table")
    return {"api_path": "/api/flow/analytics", "table": table["title"], "rows": selected, "read_only": True}


async def material_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        cp.start("HK-069")
        fixture, a, warehouse, location, supplier, account = dependencies(e, cp)
        token = uuid.uuid4().hex[:10].upper()
        inventory = await login_as(e, context, credentials, fixture["inventory_key"], "master/items", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text("物资目录")
        guard = Guard(e, "material_second_zero_item", append={"flow_items", "audit_logs"})
        b, b_meta = await save_item(e, inventory, fixture["store_id"],
            {"sku": "BM-" + token, "name": "合成材料B" + token, "unit": "件", "reorder": "3.000", "active": True})
        b_meta["guard"] = guard.finish()
        await master_page(e, "locations", "库位")
        await master_form(e, "locations", "库位")
        await live_choice(e, "warehouse_id", warehouse["name"], warehouse["code"] + " · " + warehouse["name"], expected_value=warehouse["id"])
        guard = Guard(e, "material_second_actual_location", append={"master_locations", "master_receipts", "audit_logs"})
        second_location, location_meta = await save_master(e, "locations", {"code": "MB-" + token, "name": "合成材料移入位" + token, "active": True})
        location_meta["guard"] = guard.finish()
        require(second_location["warehouse_id"] == warehouse["id"], "第二库位不属于同次材料仓")
        activation = []
        for item in (a, b):
            case_id, proof, creation = await warehouse_create(e, context, credentials, fixture, item, "activate", 0, destination=location)
            _, approval = await warehouse_command(e, context, credentials, fixture, case_id, item["id"], "approve", proof)
            stock = item_stock(e, item["id"])
            require(stock["item"]["quantity_milli"] == stock["item"]["inventory_value_cents"] == 0 and not stock["stock_moves"], "启用制造库存成果")
            activation.append({"case_id": case_id, "creation": creation, "approval": approval, "stock": stock})
        inventory = await login_as(e, context, credentials, fixture["inventory_key"], "procurement", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text("采购与供应商结算")
        await e.click('#main [data-act="procurement-new"]', "申请本轮两行真实材料采购")
        await live_choice(e, "supplier", supplier["name"], supplier["code"] + " · " + supplier["name"], expected_value=supplier["id"])
        reason = "本轮明确合成材料A八升、材料B两件采购，独立审核及分批验收"
        await e.fill('#modal [name="reason"]', reason, "填写采购实际约定")
        for index, (item, quantity, cost) in enumerate(((a, "8.000", "10.00"), (b, "2.000", "20.00"))):
            if index:
                await e.click('#modal [data-act="procurement-add-line"]', "增加第二条独立物资约定")
            root = e.page.locator('#modal [data-purchase-line]').nth(index)
            await choose(e, root, 'select[name="item"]', item["sku"], f'{item["sku"]} · {item["name"]}（{item["unit"]}）', item["id"])
            e.action("fill", "填写该原物资采购数量及单价", item_id=item["id"], quantity=quantity, cost=cost)
            await root.locator('[name="quantity"]').fill(quantity)
            await root.locator('[name="cost"]').fill(cost)
        ids = {a["id"], b["id"]}
        guard = Guard(e, "material_procurement_create", append=COMMON | {"flow_cases", "flow_tasks", "procurement_orders", "procurement_lines"}, items=ids, new_kind="procurement")
        purchase_id, creation = await create_submit(e, "/api/procurement/orders", "procurement", guard, inventory)
        lines = e.db.rows("SELECT * FROM procurement_lines WHERE case_id=? ORDER BY id", (purchase_id,))
        require([(r["item_id"], r["quantity_milli"], r["unit_cost_cents"], r["amount_cents"]) for r in lines]
            == [(a["id"], 8000, 1000, 8000), (b["id"], 2000, 2000, 4000)], "原多行约定数量/金额不匹配")
        order = one(e, "procurement_orders", purchase_id)
        require(order["supplier_id"] == supplier["id"] and facts(e, purchase_id)["case"]["amount_cents"] == 12000, "原约定供应商/总额不匹配")
        _, approval = await procurement_command(e, context, credentials, fixture, purchase_id, "approve", ids, role="manager", task_key="procurement_approve")
        finance, _ = await detail(e, context, credentials, fixture, "finance", purchase_id, "procurement")
        contract = await evidence_file(e, purchase_id, finance, "procurement_contract", "material-contract-" + token + ".txt", "A 8.000升×10.00元、B 2.000件×20.00元，约定120.00元，先实际预付30.00元")
        _, prepay_request = await procurement_command(e, context, credentials, fixture, purchase_id, "prepay_request", ids,
            role="finance", file=contract, amount=3000)
        requests = e.db.rows("SELECT * FROM procurement_prepayment_requests WHERE case_id=? ORDER BY id", (purchase_id,))
        require(len(requests) == 1 and requests[0]["requested_by"] == finance["id"] and requests[0]["amount_cents"] == 3000, "原预付申请来源错误")
        funds_id = requests[0]["id"]
        _, prepay_approval = await procurement_command(e, context, credentials, fixture, purchase_id, "prepay_approve", ids,
            role="manager", task_key="procurement_prepay_review_" + str(funds_id), file=contract, funds=requests[0])
        decisions = e.db.rows("SELECT * FROM procurement_prepayment_decisions WHERE request_id=?", (funds_id,))
        require(len(decisions) == 1 and decisions[0]["actor_id"] != finance["id"] and decisions[0]["action"] == "approve", "原预付未独立批准")
        finance, _ = await detail(e, context, credentials, fixture, "finance", purchase_id, "procurement")
        payment_proof = await evidence_file(e, purchase_id, finance, "receipt", "material-cash-" + token + ".txt", "合成实际预付30.00、第一批尾付20.00、第二批70.00及按原款实退10.00的各原凭证号独立记录")
        _, prepay_paid = await procurement_command(e, context, credentials, fixture, purchase_id, "prepay_pay", ids,
            role="finance", task_key="procurement_prepay_pay_" + str(funds_id), file=payment_proof, amount=3000,
            account=account, reference="MAT-PRE-" + token, funds=one(e, "procurement_prepayment_requests", funds_id))
        prepaid = cash_fact(e, purchase_id, 3000, "out", "MAT-PRE-" + token, account, finance)
        disbursements = e.db.rows("SELECT * FROM procurement_prepayment_disbursements WHERE request_id=?", (funds_id,))
        require(len(disbursements) == 1 and disbursements[0]["payment_id"] == prepaid["payment"]["id"], "原预付实际款缺分配来源")
        require(one(e, "procurement_prepayment_requests", funds_id)["status"] == "paid"
            and disbursements[0]["actor_id"] == finance["id"], "预付批准不等于本人实际付清")
        require(not e.db.rows("SELECT id FROM procurement_receipts WHERE case_id=?", (purchase_id,))
            and not e.db.rows("SELECT id FROM procurement_payment_allocations WHERE case_id=?", (purchase_id,)), "预付已假造验收/抵用")
        await cp.passed(second_item={"row": b, "native": b_meta}, second_location={"row": second_location, "native": location_meta},
            activation=activation, order=order, lines=lines, creation=creation, approval=approval,
            prepay={"request": prepay_request, "approval": prepay_approval, "payment": prepay_paid, "cash": prepaid, "disbursement": disbursements[0]})

        cp.start("HK-045")
        inventory, _ = await detail(e, context, credentials, fixture, "inventory", purchase_id, "procurement")
        physical_proof = await evidence_file(e, purchase_id, inventory, "evidence", "material-receive-return-" + token + ".txt", "第一批A3.000/B1.000，第二批A5.000/B1.000；原第一批A实退1.000，原库位逐项分配")
        first = await inline_receive(e, context, credentials, fixture, purchase_id, (a, b), (3000, 1000), location, warehouse, physical_proof)
        first_receipts = e.db.rows("SELECT * FROM procurement_receipts WHERE case_id=? ORDER BY id", (purchase_id,))
        require([(r["quantity_milli"], r["value_cents"]) for r in first_receipts] == [(3000, 3000), (1000, 2000)], "第一批实际到货金额/数量不匹配")
        original_allocation = e.db.rows("SELECT * FROM procurement_payment_allocations WHERE payment_id=?", (prepaid["payment"]["id"],))
        require(len(original_allocation) == 1 and original_allocation[0]["receipt_id"] == first_receipts[0]["id"] and original_allocation[0]["amount_cents"] == 3000, "原预付未按真实第一批A抵用")
        shown, first_pay = await procurement_command(e, context, credentials, fixture, purchase_id, "pay", ids,
            role="finance", task_key="procurement_pay", file=payment_proof, amount=2000, account=account, reference="MAT-PAY1-" + token)
        first_cash = cash_fact(e, purchase_id, 2000, "out", "MAT-PAY1-" + token, account, finance)
        require(shown["totals"]["received_cents"] == 5000 and shown["totals"]["paid_net_cents"] == 5000 and shown["totals"]["payable_cents"] == 0, "第一批原应付/实付不对平")
        cp.note(first_batch=first, first_receipts=first_receipts, first_pay=first_pay, first_cash=first_cash, original_prepay_allocation=original_allocation[0])
        cp.start("HK-073")
        positive_id, positive_proof, positive_observation = await count_capture(e, context, credentials, fixture, a["id"], location, 3500)
        require(positive_observation["observation"]["baseline_quantity_milli"] == 3000, "盘点开始账面缺第一批来源")
        cp.note(positive_capture=positive_observation)
        cp.start("HK-045")
        second = await inline_receive(e, context, credentials, fixture, purchase_id, (a, b), (5000, 1000), location, warehouse, physical_proof)
        shown, second_pay = await procurement_command(e, context, credentials, fixture, purchase_id, "pay", ids,
            role="finance", task_key="procurement_pay", file=payment_proof, amount=7000, account=account, reference="MAT-PAY2-" + token)
        second_cash = cash_fact(e, purchase_id, 7000, "out", "MAT-PAY2-" + token, account, finance)
        receipts = e.db.rows("SELECT * FROM procurement_receipts WHERE case_id=? ORDER BY id", (purchase_id,))
        require(len(receipts) == 4 and sum(r["value_cents"] for r in receipts) == 12000
            and shown["receiving_closed"] and shown["state"] == "completed" and shown["totals"]["paid_net_cents"] == 12000
            and shown["totals"]["payable_cents"] == 0, "分批到货及实际尾款未完成")
        require(item_stock(e, a["id"])["item"]["quantity_milli"] == 8000 and item_stock(e, b["id"])["item"]["quantity_milli"] == 2000, "实际验收量不匹配")
        await cp.passed(second_batch=second, receipts=receipts, second_pay=second_pay, second_cash=second_cash, settled_api=shown)
        cp.start("HK-073")
        positive = await count_post(e, context, credentials, fixture, positive_id, a["id"], positive_proof,
            baseline=3000, counted=3500, bridge=5000, delta=500)
        require({r["case_id"] for r in positive["prepost_api"]["count"]["entries"]} == {purchase_id}, "期间桥接不是本次第二批采购")
        cp.note(positive=positive, positive_capture=positive_observation)
        cp.start("HK-051")
        await cp.passed(query=await query_count_source(e, context, credentials, fixture, positive_id, a["id"], 500))

        cp.start("HK-054")
        inventory, body = await detail(e, context, credentials, fixture, "inventory", purchase_id, "procurement")
        await action_form(e, "procurement", "return_request")
        await e.fill(f'#modal [name="quantity_{first_receipts[0]["id"]}"]', "1.000", "明确原第一批A实际退货一升")
        await file_choice(e, "evidence", physical_proof)
        reason = "本轮原第一批A一升实际退货，保留原验收批次与原付款"
        await e.fill('#modal [name="reason"]', reason, "填写原退货真实原因")
        guard = Guard(e, "procurement_return_request", append=COMMON | {"flow_tasks", "procurement_returns", "procurement_return_lines"},
            update=mutable(e, purchase_id), cases={purchase_id}, items=ids)
        _, return_request = await command_submit(e, "procurement", purchase_id, "return_request", inventory, guard,
            {"lines": [{"receipt_id": first_receipts[0]["id"], "quantity_milli": 1000}], "evidence_id": physical_proof["id"], "reason": reason})
        returned = e.db.rows("SELECT * FROM procurement_returns WHERE case_id=?", (purchase_id,))
        require(len(returned) == 1 and returned[0]["requested_by"] == inventory["id"], "原退货申请不唯一/来源不匹配")
        return_id = returned[0]["id"]
        _, return_approval = await procurement_command(e, context, credentials, fixture, purchase_id, "return_approve", ids,
            role="manager", task_key="procurement_return_review_" + str(return_id), returned=returned[0])
        require(one(e, "procurement_returns", return_id)["approved_by"] != inventory["id"], "原退货没有独立批准")
        await stock_page(e, context, credentials, fixture, "inventory", a["id"], quantity=8500, value=8500, reserved=1000)
        inventory, _ = await responsible(e, context, credentials, fixture, purchase_id,
            "procurement_return_dispatch_" + str(return_id), "inventory", "procurement")
        await login_as(e, context, credentials, fixture["inventory_key"], f"case/{purchase_id}", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text(facts(e, purchase_id)["case"]["title"])
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/warehouse/allocations/{purchase_id}") as pending:
            await e.click(f'#main [data-act="open"][data-route="warehouse-allocation/{purchase_id}"]', "从原单准备实际退货库位")
        require((await pending.value).status == 200, "原退货库位读取失败")
        await expect(e.page.locator("#main h1")).to_have_text("准备物资库位")
        await e.click(f'#main [data-act="wh-allocate"][data-id="{a["id"]}"]', "准备明确原材料A退货位置")
        await select_value(e, '#modal [name="purpose"]', "procurement_return", "选择原采购退回动作")
        await e.fill('#modal [name="quantity"]', "1.000", "填写实际退货数量")
        await select_value(e, '#modal [name="location"]', location["id"], "选择原到货实际库位")
        await e.fill('#modal [name="location_qty"]', "1.000", "填写实际库位出量")
        guard = Guard(e, "procurement_return_position_prepare", append=COMMON | WAREHOUSE_APPEND,
            update=mutable(e, purchase_id, allocations=True), cases={purchase_id}, items=ids)
        _, prepare_meta, _, request = await submit(e, f"/api/warehouse/allocations/{purchase_id}", 200, f"/api/warehouse/allocations/{purchase_id}")
        require(request["values"] == {"item_id": a["id"], "quantity_milli": -1000, "purpose": "procurement_return",
            "locations": [{"location_id": location["id"], "quantity_milli": 1000}]}, "原退货库位方向/引用不匹配")
        preparation = {"native": prepare_meta, "guard": guard.finish(), "receipt": request_receipt(e, request, purchase_id, inventory)}
        shown, return_dispatch = await procurement_command(e, context, credentials, fixture, purchase_id, "return_dispatch", ids,
            role="inventory", task_key="procurement_return_dispatch_" + str(return_id), returned=one(e, "procurement_returns", return_id), file=physical_proof)
        postings = e.db.rows("SELECT * FROM procurement_return_postings WHERE case_id=?", (purchase_id,))
        require(len(postings) == 1 and postings[0]["receipt_id"] == first_receipts[0]["id"] and postings[0]["quantity_milli"] == 1000 and postings[0]["value_cents"] == 1000, "实退未引用原验收批次")
        posting = postings[0]
        move = one(e, "flow_stock_moves", posting["stock_move_id"])
        valuation = one(e, "procurement_return_valuations", posting["id"])
        require(move["original_id"] == first_receipts[0]["stock_move_id"] and move["quantity_milli"] == -1000 and move["value_cents"] == -1000
            and valuation["inventory_cost_cents"] == valuation["supplier_credit_cents"] == 1000 and valuation["variance_cents"] == 0, "实际库存扣减/原批冲款成本不匹配")
        released = e.db.rows("SELECT * FROM procurement_payment_allocations WHERE return_posting_id=?", (posting["id"],))
        require(len(released) == 1 and released[0]["original_id"] == original_allocation[0]["id"]
            and released[0]["payment_id"] == prepaid["payment"]["id"] and released[0]["amount_cents"] == -1000, "原退货未释放明确预付抵用来源")
        require(item_stock(e, a["id"])["item"]["quantity_milli"] == 7500, "实际退货没有减库存")
        await cp.passed(request=return_request, approval=return_approval, preparation=preparation, dispatch=return_dispatch,
            return_row=one(e, "procurement_returns", return_id), posting=posting, stock_move=move, valuation=valuation, released_allocation=released[0])
        cp.start("HK-083")
        _, before_refund = await detail(e, context, credentials, fixture, "finance", purchase_id, "procurement")
        available = next(p for p in before_refund["prepayments"]["original_cash"] if p["payment_id"] == prepaid["payment"]["id"])
        require(available["available_cents"] == before_refund["totals"]["supplier_refund_due_cents"] == 1000, "原退款额度没有明确释放来源")
        shown, refund = await procurement_command(e, context, credentials, fixture, purchase_id, "refund", ids,
            role="finance", task_key="procurement_refund", file=payment_proof, amount=1000, account=account,
            reference="MAT-REF-" + token, original=prepaid["payment"])
        refunded = cash_fact(e, purchase_id, 1000, "in", "MAT-REF-" + token, account, finance, prepaid["payment"])
        require(shown["state"] == "completed" and shown["totals"]["paid_net_cents"] == 11000
            and shown["totals"]["payable_cents"] == shown["totals"]["supplier_refund_due_cents"] == 0, "原实退后净付款/应付未对平")
        require(one(e, "procurement_payments", prepaid["payment"]["id"]) == prepaid["payment"], "原预付款被退款覆盖")
        await cp.passed(original_payment=prepaid, released_source=available, refund=refund, actual_cash=refunded, api=shown)

        cp.start("HK-072")
        local_id, local_proof, local_create = await warehouse_create(e, context, credentials, fixture,
            one(e, "flow_items", a["id"]), "local_move", 2000, source=location, destination=second_location)
        _, local_approval = await warehouse_command(e, context, credentials, fixture, local_id, a["id"], "approve", local_proof)
        await stock_page(e, context, credentials, fixture, "inventory", a["id"], quantity=7500, value=7500, reserved=2000)
        _, dispatch = await warehouse_command(e, context, credentials, fixture, local_id, a["id"], "dispatch", local_proof)
        transit = await stock_page(e, context, credentials, fixture, "finance", a["id"], quantity=7500, value=7500, reserved=2000)
        require(sum(b["quantity_milli"] for b in transit["db"]["balances"] if b["transit_case_id"] == local_id) == 2000, "实际移库未进入明确本店在途")
        _, accept_first = await warehouse_command(e, context, credentials, fixture, local_id, a["id"], "accept", local_proof, quantity=750)
        await stock_page(e, context, credentials, fixture, "finance", a["id"], quantity=7500, value=7500, reserved=1250)
        _, accept_second = await warehouse_command(e, context, credentials, fixture, local_id, a["id"], "accept", local_proof, quantity=1250)
        local_stock = item_stock(e, a["id"])
        require(not e.db.rows("SELECT id FROM flow_stock_moves WHERE case_id=?", (local_id,)), "本店移库制造门店收发")
        require({b["location_id"]: b["quantity_milli"] for b in local_stock["balances"] if b["location_id"]}
            == {location["id"]: 5500, second_location["id"]: 2000}, "分批接收位置数量不守恒")
        require(facts(e, local_id)["case"]["state"] == "completed" and sum(h["quantity_milli"] for h in rows(e, "warehouse_holds") if h["case_id"] == local_id) == 0, "实际移库任务/预占未结束")
        require(all(t["status"] != "open" for t in facts(e, local_id)["tasks"]), "原移库仍有未完成待办")
        await cp.passed(case_id=local_id, creation=local_create, approval=local_approval, dispatch=dispatch,
            first_accept=accept_first, second_accept=accept_second, final_stock=local_stock, transit=transit)
        cp.start("HK-073")
        negative_id, negative_proof, negative_capture = await count_capture(e, context, credentials, fixture, a["id"], location, 5250)
        negative = await count_post(e, context, credentials, fixture, negative_id, a["id"], negative_proof,
            baseline=5500, counted=5250, bridge=0, delta=-250)
        cp.note(negative_capture=negative_capture, negative=negative)
        zero_id, zero_proof, zero_capture = await count_capture(e, context, credentials, fixture, a["id"], location, 5250)
        zero = await count_post(e, context, credentials, fixture, zero_id, a["id"], zero_proof,
            baseline=5250, counted=5250, bridge=0, delta=0)
        require(len({positive_id, negative_id, zero_id}) == 3, "正负零盘差不是三次独立实盘")
        await cp.passed(positive=positive, positive_capture=positive_observation, negative=negative, negative_capture=negative_capture,
            zero=zero, zero_capture=zero_capture, distinct_case_ids=[positive_id, negative_id, zero_id])
        cp.start("HK-061")
        await cp.passed(query=await query_count_source(e, context, credentials, fixture, negative_id, a["id"], -250))
        cp.start("HK-070")
        a_inventory = await stock_page(e, context, credentials, fixture, "inventory", a["id"], quantity=7250, value=7250)
        a_finance = await stock_page(e, context, credentials, fixture, "finance", a["id"], quantity=7250, value=7250)
        b_finance = await stock_page(e, context, credentials, fixture, "finance", b["id"], quantity=2000, value=4000)
        before = e.business_snapshot("before_material_replenishment_query")
        data = await nav(e, "master/items", "物资目录", "/api/flow/master/items")
        for item, quantity, value in ((a, 7250, 7250), (b, 2000, 4000)):
            selected = next(r for r in data["items"] if r["id"] == item["id"])
            require(selected["quantity"] == selected["available_quantity"] == qty(quantity)
                and selected["reserved_quantity"] == "0" and selected["inventory_value_cents"] == value, "原非空材料目录与真实库位不一致")
            row = e.page.locator('#main tbody tr').filter(has_text=item["sku"])
            await expect(row).to_have_count(1)
            await expect(row).to_contain_text(item["name"])
        e.business_unchanged(before, "after_material_replenishment_query")
        replenishment = await replenishment_query(e, context, credentials, fixture, (a, b))
        await cp.passed(primary_inventory=a_inventory, primary_finance=a_finance, secondary_finance=b_finance,
            material_directory=data, replenishment=replenishment, original_reorder_milli=one(e, "flow_items", a["id"])["reorder_milli"])
        sources = {}
        for name, item in (("primary", a), ("secondary", b)):
            stock = item_stock(e, item["id"])
            item_lines = {r["id"] for r in lines if r["item_id"] == item["id"]}
            sources[name] = {"item_id": item["id"], "sku": item["sku"], "name": item["name"], "unit": item["unit"],
                "store_id": fixture["store_id"], "warehouse_id": warehouse["id"],
                "location_ids": [r["location_id"] for r in stock["balances"] if r["location_id"] is not None], "source_location_id": location["id"],
                "enrollment_id": stock["enrollment"]["id"], "purchase_order_id": purchase_id,
                "receipt_ids": [r["id"] for r in receipts if r["line_id"] in item_lines],
                "stock_move_ids": [r["id"] for r in stock["stock_moves"]], "entry_ids": [r["id"] for r in stock["entries"]],
                "balance_ids": [r["id"] for r in stock["balances"]], "current_quantity_milli": stock["item"]["quantity_milli"],
                "current_value_cents": stock["item"]["inventory_value_cents"], "current_version": stock["item"]["version"]}
        cp.finish(sources)
    except Exception as error:
        cp.failed(error)
        raise


MATERIAL_SCENARIOS = ((SCENARIO, material_business, 420),)
