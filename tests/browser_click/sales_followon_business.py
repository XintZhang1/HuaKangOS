"""This run's delivered-sale add-on, agency and two other-income sources.

All positive mutations are original visible forms, with finite old-row guards.
No application imports, business HTTP writes, seeded outcomes or POST retries.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import require, login_as, employee_choice
from sales_order_business import fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import select_value, live_choice, nav


SCENARIO = "sales-followon-hk012-015-016-017"
SALES = "sales-order-hk008-009-011-022"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
CONTRACTS = {
    "HK-012": ("精品加装单", ["本版独立核价授权、原VIN实际出库和安装分别留痕", "不合格、整改、独立复检、客户接收和实际到账均完成"]),
    "HK-015": ("代办服务单", ["服务费与代缴本金各自原款分配和实际代缴", "逐项外部提交、补件及批准后真实办结，非空原事实对账"]),
    "HK-016": ("代办核价单", ["两版报价各自独立批准和客户授权，原历史不覆盖", "新版不能借旧授权，后续原资金和办理只用本版"]),
    "HK-017": ("整车其它收入单", ["客户其它收入真实履约与到账独立完成", "厂家原车辆来源、有据目标修订、独立批准、实际收款及原账户退款完成"]),
}
DOMAIN = {"addon": "/api/addon-orders", "service": "/api/service-orders", "income": "/api/vehicle-income"}
ROUTE = {"addon": "addon-orders", "service": "service-orders", "income": "vehicle-income"}
RECEIPT = {"addon": "addon_receipts", "service": "service_requests", "income": "vehicle_income_receipts"}
CASE_COLUMNS = {"version", "updated_at", "state", "data", "amount_cents", "cost_cents", "revenue_cents", "completed_date", "due_date"}
TASK_COLUMNS = {"version", "updated_at", "status", "done_by", "done_at", "assignee_id", "due_date", "title", "role"}
COMMON = {"flow_tasks", "flow_events", "audit_logs"}
TABLES = {name: "id" for name in (
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_request_receipts", "flow_files", "file_scan_events",
    "flow_items", "flow_accounts", "vehicles", "flow_stock_moves", "flow_payment_links", "cash_entries",
    "warehouse_allocations", "warehouse_allocation_lines", "warehouse_balances", "warehouse_entries",
    "addon_orders", "addon_targets", "addon_quotes", "addon_lines", "addon_approvals", "addon_authorizations",
    "addon_reservations", "addon_dispatches", "addon_installations", "addon_inspections", "addon_rectifications",
    "addon_acceptances", "addon_payments", "addon_receipts", "service_payees", "service_income_items",
    "service_orders", "service_quotes", "service_lines", "service_price_approvals", "service_authorizations",
    "service_submissions", "service_external_results", "service_fulfillments", "service_tender_slices", "service_pass_entries",
    "service_requests", "vehicle_income_orders", "vehicle_income_sources", "vehicle_income_revisions",
    "vehicle_income_decisions", "vehicle_income_cash", "vehicle_income_receipts")}
TABLES.update(file_security="file_id", business_entity_case_contexts="case_id", business_entity_cash_contexts="cash_id")
QUOTE_PARENT = {t: p for p, children in {
    "addon_quotes": ("addon_lines", "addon_approvals", "addon_authorizations"),
    "service_quotes": ("service_lines", "service_price_approvals", "service_authorizations"),
}.items() for t in children}


def one(e, table, key, pk="id"):
    rows = e.db.rows(f"SELECT * FROM {table} WHERE {pk}=?", (key,))
    require(len(rows) == 1, "本轮明确原ID缺失或不唯一：" + table)
    return rows[0]


def rows(e, table, case_id):
    return e.db.rows(f"SELECT * FROM {table} WHERE case_id=? ORDER BY id", (case_id,))


def case(e, key):
    row = one(e, "flow_cases", key)
    row["data"] = json.loads(row["data"])
    return row


def owner_case(e, table, row):
    if "case_id" in row:
        return row["case_id"]
    if table in {"addon_orders", "service_orders", "vehicle_income_orders"}:
        return row["id"]
    if table in QUOTE_PARENT:
        return one(e, QUOTE_PARENT[table], row["quote_id"])["case_id"]
    parents = {"addon_installations": ("addon_dispatches", "dispatch_id"),
               "addon_inspections": ("addon_installations", "installation_id"),
               "addon_rectifications": ("addon_inspections", "inspection_id"),
               "service_external_results": ("service_submissions", "submission_id"),
               "vehicle_income_decisions": ("vehicle_income_revisions", "revision_id"),
               "warehouse_allocation_lines": ("warehouse_allocations", "allocation_id"),
               "file_security": ("flow_files", "file_id"), "file_scan_events": ("flow_files", "file_id")}
    if table in parents:
        parent, field = parents[table]
        return owner_case(e, parent, one(e, parent, row[field]))
    return None


class Guard:
    """Every unrelated table and every unlisted old row/column remains equal."""
    def __init__(self, e, label, actor, store_id, *, append=(), update=None, cases=(), item_id=None, new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store_id
        self.append, self.update, self.cases = set(append), update or {}, set(cases)
        self.item, self.kind = item_id, new_kind
        require((self.append | self.update.keys()) <= TABLES.keys(), "后续原表守卫未核准")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: e.db.rows(f"SELECT * FROM {t} ORDER BY {TABLES[t]}") for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "后续确认改动了无关原表：" + str(sorted(changed)))
        added, updated = {}, {}
        owned = set(self.cases)
        if self.kind:
            old = {r["id"] for r in self.old["flow_cases"]}
            new = [r for r in self.e.db.rows("SELECT * FROM flow_cases ORDER BY id") if r["id"] not in old]
            require(len(new) == 1 and new[0]["kind"] == self.kind and new[0]["created_by"] == self.actor["id"], "原动作新建了错误或多个原单")
            owned.add(new[0]["id"])
        for table, old_rows in self.old.items():
            pk = TABLES[table]
            current = {r[pk]: r for r in self.e.db.rows(f"SELECT * FROM {table} ORDER BY {pk}")}
            old_ids = {r[pk] for r in old_rows}
            updated[table] = []
            for old in old_rows:
                require(old[pk] in current, "后续动作删除了原事实：" + table)
                columns = {k for k in old if old[k] != current[old[pk]][k]}
                require(columns <= self.update.get(table, {}).get(old[pk], set()), "后续动作覆盖无权原行/列：" + table + "/" + str(old[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": old[pk], "columns": sorted(columns)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(not new or table in self.append, "只允许更新的表出现新行：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "后续新增事实串店：" + table)
                for field in ("actor_id", "created_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "后续新增事实串本人：" + table)
                scoped = owner_case(self.e, table, row)
                if scoped is not None:
                    require(scoped in owned, "后续新增事实串原单：" + table)
                if row.get("item_id") is not None:
                    require(row["item_id"] == self.item, "后续新增事实串物资：" + table)
                if table == "cash_entries":
                    links = self.e.db.rows("SELECT case_id FROM flow_payment_links WHERE cash_id=? UNION ALL SELECT case_id FROM service_pass_entries WHERE cash_id=? UNION ALL SELECT case_id FROM vehicle_income_cash WHERE cash_id=?", (row["id"], row["id"], row["id"]))
                    require(len(links) == 1 and links[0]["case_id"] in owned, "新现金缺同原单唯一来源")
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", row["balance_id"])["item_id"] == self.item, "原位置分录串物资")
            added[table] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": added, "updated_columns": updated,
                  "unrelated_tables_unchanged": True, "protected_old_rows_and_other_stores": True}
        self.e.observe("sales_followon_row_guard", {"label": self.label, **result})
        return result


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        bindings = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key in CONTRACTS:
            require(bindings[key]["source_review_status"] == "source_reviewed" and any(c["check_id"] == key + "-business" for c in bindings[key]["acceptance_checks"]), "后续目录源合同未核准：" + key)
        self.path = e.directory / "business-checkpoint.json"
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": list(CONTRACTS), "complete": False, "passed": False,
            "source_contract_sha256": self.digest, "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution": "native_browser_original_forms", "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "conditions": {"synthetic_money_and_physical_inputs": True, "production_bank_or_external_results": False,
                "file_scan": "original_structure_only_not_clamav", "customer_real_signature": False},
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested", "criteria": checks, "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}, "conditional_checks": []} for key, (title, checks) in CONTRACTS.items()]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.save()

    def note(self, **evidence):
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, *, conditional=(), **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.active["conditional_checks"] = list(conditional)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
            self.report["failed_requirement"] = self.active["id"]
        for row in self.report["requirements"]:
            if row["status"] == "running":
                row["status"] = row["acceptance_checks"][0]["status"] = "partial"
                row["acceptance_checks"][0]["incomplete_reason"] = "已有前序原事实；场景失败后停止，后继未完成"
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "销售后续四项未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=4, passed_requirements=4, report_sources=sources)
        self.save()
        self.e.observe("sales_followon_business_checkpoint", {"path": str(self.path), "report_sources": sources, "business_accepted": False})


def source_facts(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "销售后续仅允许本次外置合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "数据库不是本次外部runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "本次来源镜像未冻结")
    for name in ("sales_followon_business.py", "sales_order_business.py", "master_data_business.py", "vehicle_purchase_business.py", "material_business.py", "sales_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "本次来源脚本指纹变化：" + name)
    cp.report["mirror"] = {"provenance_sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    sale, purchase, master, material = [fixed_dependency(e, cp, name) for name in (SALES, PURCHASE, MASTER, MATERIAL)]
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    fixture["technician_key"] = e.manifest["business_fixtures"]["repair"]["technician_key"]
    for role in ("sales", "manager", "service", "inventory", "finance", "technician"):
        require(e.manifest["users"][fixture[role + "_key"]]["role"] == role, "后续缺真实本人岗位：" + role)
    given = sale["report_sources"]
    source, customer = case(e, given["delivered_order_id"]), one(e, "flow_customers", given["customer_id"])
    vehicle = one(e, "vehicles", given["delivered_vehicle_id"])
    require(source["kind"] == "order" and source["flow_version"] == 4 and source["state"] == "delivered"
            and source["customer_id"] == customer["id"] and source["store_id"] == vehicle["store_id"] == customer["store_id"] == fixture["store_id"]
            and customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"], "本次销售交付/客户归属不匹配")
    holds = e.db.rows("SELECT * FROM flow_vehicle_holds WHERE case_id=?", (source["id"],))
    require(len(holds) == 1 and holds[0]["vehicle_id"] == vehicle["id"] and holds[0]["delivered"], "本次销售没有已提车的真实原配车")
    supplied = material["material_sources"]["secondary"]
    item = one(e, "flow_items", supplied["item_id"])
    warehouse, location = one(e, "master_warehouses", supplied["warehouse_id"]), one(e, "master_locations", supplied["source_location_id"])
    enrollment = one(e, "warehouse_enrollments", supplied["enrollment_id"])
    bins = e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=? ORDER BY id", (item["id"],))
    selected = [b for b in bins if b["location_id"] == location["id"]]
    require(item["active"] and item["unit"] == supplied["unit"] == "件" and item["sku"] == supplied["sku"]
            and item["store_id"] == warehouse["store_id"] == location["store_id"] == fixture["store_id"]
            and enrollment["item_id"] == item["id"] and warehouse["warehouse_type"] == "materials" and warehouse["active"] and location["active"]
            and location["warehouse_id"] == warehouse["id"] and len(selected) == 1 and selected[0]["quantity_milli"] >= 1000
            and item["quantity_milli"] >= 1000 and item["inventory_value_cents"] > 0
            and sum(b["quantity_milli"] for b in bins) == item["quantity_milli"], "本次明确原商品/库位现余量不足或身份不符")
    original_receipts = [one(e, "procurement_receipts", key) for key in supplied["receipt_ids"]]
    require(original_receipts and all(r["case_id"] == supplied["purchase_order_id"] for r in original_receipts), "加装商品缺本次真实采购验收")
    work = one(e, "master_work_items", checkpoint_evidence(master, "HK-175")["row"]["id"])
    project = one(e, "master_agency_projects", checkpoint_evidence(master, "HK-179")["row"]["id"])
    supplier = one(e, "master_suppliers", checkpoint_evidence(purchase, "HK-171")["supplier"]["id"])
    account = one(e, "flow_accounts", checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"])
    require(all(r["active"] and r["store_id"] == fixture["store_id"] for r in (work, project, supplier, account)), "后续原主档或账户已停用/串店")
    cp.report["source_preconditions"] = {"delivered_order_id": source["id"], "customer_id": customer["id"], "vehicle": vehicle,
        "material_source": supplied, "current_item": item, "current_source_balance": selected[0], "work_item": work, "agency_project": project,
        "supplier": supplier, "account": account, "planned_inputs": {"addon_goods_cents": 3000, "addon_installation_cents": 500,
        "agency_fee_v1_cents": 2000, "agency_fee_v2_cents": 2500, "agency_pass_cents": 1000, "customer_other_cents": 800,
        "manufacturer_target_v1_cents": 10000, "manufacturer_target_v2_cents": 7000}}
    cp.save()
    return fixture, source, customer, vehicle, item, warehouse, location, work, project, supplier, account


def updates(e, case_id, parent=None, *, item=None, physical=False, allocation=False, vehicle=None, account=None):
    result = {"flow_cases": {case_id: CASE_COLUMNS}, "flow_tasks": {r["id"]: TASK_COLUMNS for r in rows(e, "flow_tasks", case_id)}}
    if parent is not None:
        result["flow_cases"][parent] = {"version", "updated_at"}
    if item is not None:
        result["flow_items"] = {item: {"version", "updated_at"} | ({"quantity_milli", "inventory_value_cents", "unit_cost_cents"} if physical else set())}
    if physical:
        result["warehouse_balances"] = {r["id"]: {"version", "updated_at", "quantity_milli", "value_cents"} for r in e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=?", (item,))}
    if allocation:
        result["warehouse_allocations"] = {r["id"]: {"status", "stock_move_id", "version", "updated_at"} for r in rows(e, "warehouse_allocations", case_id)}
    if vehicle is not None:
        result["vehicles"] = {vehicle: {"version", "updated_at"}}
    if account is not None:
        result["flow_accounts"] = {account: {"version", "updated_at"}}
    return result


async def original_submit(e, path, rendered, guard, store_id, *, status=200, multipart=False, request_id_required=True):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and rendered(urlsplit(r.url).path)) as ready:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人确认这一步原业务事实")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原提交HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await ready.value
    view = await read.json()
    require(read.status == 200, "原提交后同单读取失败")
    headers = await response.request.all_headers()
    require(urlsplit(response.url).netloc == urlsplit(e.manifest["origin"]).netloc and headers.get("cookie") and headers.get("x-csrf-token")
            and headers.get("x-store-id") == str(store_id), "原业务缺同源Cookie/CSRF或当前店")
    request = None if multipart else response.request.post_data_json
    if not multipart and request_id_required:
        require(isinstance(request, dict) and isinstance(request.get("request_id"), str) and len(request["request_id"]) >= 16, "原业务缺请求编号")
    elif not request_id_required:
        require(not multipart and re.fullmatch(r"/api/flow/tasks/\d+/assign", path)
                and isinstance(request, dict) and set(request) == {"version", "assignee_id", "reason"}
                and type(request["version"]) is int and type(request["assignee_id"]) is int
                and isinstance(request["reason"], str) and len(request["reason"]) >= 2, "原任务交接须保持独立三字段AssignInput合同")
    meta = {"path": path, "method": "POST", "status": response.status, "native_ui": True, "cookie_present": True, "csrf_present": True,
        "render_get_path": urlsplit(read.url).path, "render_get_status": read.status, "source_guard": guard.finish(),
        "submitted_version": request.get("version") if request else None,
        "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request and request_id_required else None}
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    e.observe("sales_followon_original_response", meta)
    return body, view, meta, request


async def read_as(e, context, credentials, fixture, role, domain, key):
    path = DOMAIN[domain] + "/" + str(key)
    catalogue = None
    if domain == "addon" and role in {"sales", "service", "manager"}:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == DOMAIN[domain] + "/catalog") as options:
            async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
                actor = await login_as(e, context, credentials, fixture[role + "_key"], ROUTE[domain] + "/" + str(key), fixture["store_id"])
        catalogue_response = await options.value
        require(catalogue_response.status == 200, "原加装候选来源读取失败")
        catalogue = await catalogue_response.json()
    else:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            actor = await login_as(e, context, credentials, fixture[role + "_key"], ROUTE[domain] + "/" + str(key), fixture["store_id"])
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == key and view["version"] == case(e, key)["version"], "原岗位没有读取同单当前CAS")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    if catalogue is not None:
        view["original_catalogue"] = catalogue
    return actor, view


async def responsible(e, context, credentials, fixture, domain, key, task_key, role, *, optional=False):
    selected = e.manifest["users"][fixture[role + "_key"]]
    tasks = [t for t in rows(e, "flow_tasks", key) if t["key"] == task_key and t["status"] == "open"]
    require(len(tasks) == 1 or optional and not tasks, "原后续任务未开放或不唯一：" + task_key)
    meta = {"task_key": task_key, "task_id": tasks[0]["id"] if tasks else None, "assignee_id": selected["id"], "handoff_needed": False}
    if tasks and tasks[0]["assignee_id"] != selected["id"]:
        original = tasks[0]
        path = f"/api/flow/cases/{key}"
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as loaded:
            manager = await login_as(e, context, credentials, fixture["manager_key"], "case/" + str(key), fixture["store_id"])
        response = await loaded.value
        require(response.status == 200, "主管原交接单读取失败")
        view = await response.json()
        current = case(e, key)
        rendered_tasks = [t for t in view["tasks"] if t["id"] == original["id"]]
        require(view["id"] == key and view["version"] == current["version"] and len(rendered_tasks) == 1
                and all(rendered_tasks[0][field] == original[field] for field in ("case_id", "key", "status", "assignee_id", "version")),
                "本次原交接单或开放任务已变化，须重新核对")
        await expect(e.page.locator("#main h1")).to_have_text(current["title"])
        selector = f'#main [data-act="assign"][data-id="{original["id"]}"]'
        await expect(e.page.locator(selector)).to_have_count(1)
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "主管明确交接当前原业务任务")
        await employee_choice(e, selected)
        await e.fill('#modal [name="reason"]', "本次原岗位员工本人办理，明确交接当前原任务", "填写原交接原因")
        guard = Guard(e, "original_task_handoff", manager, fixture["store_id"], append={"flow_events", "audit_logs"},
            update={"flow_tasks": {original["id"]: TASK_COLUMNS}, "flow_cases": {key: {"version", "updated_at"}}}, cases={key})
        _, _, native, request = await original_submit(e, f'/api/flow/tasks/{original["id"]}/assign', lambda p: p == f"/api/flow/cases/{key}", guard, fixture["store_id"], request_id_required=False)
        require(request["version"] == original["version"] and request["assignee_id"] == selected["id"]
                and request["reason"] == "本次原岗位员工本人办理，明确交接当前原任务" and native["request_id_sha256"] is None, "原交接缺真实员工/CAS/原因或误加业务请求编号")
        meta.update(handoff_needed=True, native=native)
    actor, view = await read_as(e, context, credentials, fixture, role, domain, key)
    if tasks:
        require(one(e, "flow_tasks", tasks[0]["id"])["assignee_id"] == actor["id"], "原任务不是当前本人办理")
    return actor, view, meta


async def upload(e, fixture, key, actor, category, action, text):
    folder = e.directory / "synthetic-inputs"
    folder.mkdir(exist_ok=True)
    name = action + "-" + uuid.uuid4().hex[:12] + ".txt"
    content = ("合成销售后续点击材料；不代表银行、真实签字或现场外部手续。\n" + text + "\n" + name + "\n").encode("utf-8")
    path = folder / name
    path.write_bytes(content)
    await e.click('#main [data-act="upload"]', "本人选取本步独立原件")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "明确本动作原件类别")
    e.action("select_file", "本人选取外部合成原件", filename=name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    guard = Guard(e, "original_file_upload", actor, fixture["store_id"], append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={key})
    body, view, meta, _ = await original_submit(e, f"/api/flow/cases/{key}/files", lambda p: p == f"/api/flow/cases/{key}", guard, fixture["store_id"], multipart=True)
    stored = one(e, "flow_files", body["id"])
    blob = stored["content"]
    require(isinstance(blob, bytes) and len(blob) == len(content) and hashlib.sha256(blob).hexdigest() == hashlib.sha256(content).hexdigest(), "原文件数据库实际字节不符")
    file = {k: v for k, v in stored.items() if k != "content"}
    require(file["case_id"] == key and file["created_by"] == actor["id"] and file["category"] == category and file["name"] == name
            and file["sha256"] == hashlib.sha256(content).hexdigest() and file["size"] == len(content) and not file["generated"], "原文件内容/类别/本人来源不符")
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (file["id"],))
    visible = next((f for f in view["files"] if f["id"] == file["id"]), None)
    require(len(scans) == 1 and scans[0]["state"] == "structure_only" and visible and visible["security"]["can_use"], "合成原件未完成原结构检查")
    await expect(e.page.locator("#main .filerecord").filter(has_text=name)).to_contain_text(visible["security"]["label"])
    return {"file": file, "stored_blob": {"length": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}, "scan": scans[0], "native": meta, "clamav_acceptance": False}


async def proof_choice(e, proof):
    file = proof["file"]
    label = {"evidence": "业务凭据", "authorization": "客户授权", "inspection": "检测记录", "receipt": "收退款凭据"}[file["category"]]
    await live_choice(e, "evidence_id", file["name"], file["name"] + " · " + label, expected_value=file["id"])


async def form(e, domain, action, *, extra=""):
    selector = f'#main [data-act="{ {"addon": "addon-action", "service": "serviceorder-action", "income": "vehicle-income-action"}[domain] }"][data-key="{action}"]' + extra
    await expect(e.page.locator(selector)).to_have_count(1)
    await expect(e.page.locator(selector)).to_be_visible()
    await e.click(selector, "办理原步骤 " + action)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def command(e, fixture, domain, key, actor, action, *, append=(), parent=None, item=None, physical=False, allocation=False, vehicle=None, account=None, expected=None):
    before = case(e, key)
    old_events = rows(e, "flow_events", key)
    guard = Guard(e, "original_" + domain + "_" + action, actor, fixture["store_id"], append=COMMON | {RECEIPT[domain]} | set(append),
        update=updates(e, key, parent, item=item, physical=physical, allocation=allocation, vehicle=vehicle, account=account), cases={key}, item_id=item)
    body, view, meta, request = await original_submit(e, DOMAIN[domain] + f"/{key}/actions/{action}", lambda p: p == DOMAIN[domain] + "/" + str(key), guard, fixture["store_id"])
    current = case(e, key)
    require(request["version"] == before["version"] and body["id"] == view["id"] == key and current["version"] == body["version"] > before["version"], "原步骤CAS或返回身份不符")
    require(all(current[k] == before[k] for k in ("id", "kind", "flow_version", "number", "parent_id", "customer_id", "owner_id", "created_by", "store_id")), "原步骤改写了业务身份")
    for k, value in (expected or {}).items():
        require(request["values"][k] == value, "原步骤提交字段不符：" + k)
    receipts = e.db.rows(f"SELECT * FROM {RECEIPT[domain]} WHERE request_key=?", (request["request_id"],))
    require(len(receipts) == 1 and receipts[0]["actor_id"] == actor["id"], "原步骤缺唯一本人回执")
    events = rows(e, "flow_events", key)
    require(events[:len(old_events)] == old_events and len(events) == len(old_events) + 1
            and events[-1]["action"] == {"addon": "addon_", "service": "serviceorder_", "income": "vehicle_income_"}[domain] + action
            and events[-1]["actor_id"] == actor["id"], "原步骤没有唯一追加本人事件")
    return view, {"native": meta, "event": events[-1], "request_values": request["values"], "receipt_id": receipts[0]["id"]}


async def account_choice(e, account):
    root = e.page.locator('#modal .lookup').filter(has=e.page.locator('select[name="account_id"]'))
    e.action("fill", "查找明确原账户", value=account["name"])
    await root.locator('[role="combobox"]').fill(account["name"])
    option = root.get_by_role("option").filter(has_text=account["name"])
    await expect(option).to_have_count(1)
    e.action("click", "明确选择原账户", account_id=account["id"])
    await option.click()
    await expect(root.locator('select[name="account_id"]')).to_have_value(str(account["id"]))


async def current_source(e, context, credentials, fixture, role, source_id):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/flow/cases/{source_id}") as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], "case/" + str(source_id), fixture["store_id"])
    response = await pending.value
    view = await response.json()
    current = case(e, source_id)
    require(response.status == 200 and view["version"] == current["version"] and current["state"] == "delivered", "原销售当前读取或交付来源失效")
    return actor, current


async def refresh(e, domain, key):
    before = e.business_snapshot("before_followon_refresh")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == DOMAIN[domain] + "/" + str(key)) as pending:
        await e.page.reload()
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == key and view["version"] == case(e, key)["version"], "原后续刷新不是同单当前版")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    e.business_unchanged(before, "after_followon_refresh")
    return view


def stock_facts(e, item_id):
    return {"item": one(e, "flow_items", item_id), "balances": e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=? ORDER BY id", (item_id,)),
        "moves": e.db.rows("SELECT * FROM flow_stock_moves WHERE item_id=? ORDER BY id", (item_id,)),
        "entries": e.db.rows("SELECT x.* FROM warehouse_entries x JOIN warehouse_balances b ON b.id=x.balance_id WHERE b.item_id=? ORDER BY x.id", (item_id,))}


async def addon_path(e, context, credentials, fixture, cp, source, vehicle, item, warehouse, location, work, account, day):
    cp.start("HK-012")
    sales, current = await current_source(e, context, credentials, fixture, "sales", source["id"])
    await nav(e, "addon-orders", "销售加装明细", DOMAIN["addon"])
    await e.click('#main [data-act="addon-new"]', "为已交付原车提出非阻断加装")
    await select_value(e, '#modal [name="source"]', f'{current["id"]} · {current["number"]} · {current["title"]}', "明确本次已交付原销售")
    await select_value(e, '#modal [name="blocking"]', "允许交车后办理", "明确交付后继续办理")
    await e.fill('#modal [name="due_date"]', day, "明确本次加装期限")
    await e.fill('#modal [name="reason"]', "原车已交付，客户明确后续安装一件合成商品与安装项目", "填写本次加装申请")
    guard = Guard(e, "addon_create", sales, fixture["store_id"], append=COMMON | {"flow_cases", "addon_orders", "addon_receipts", "business_entity_case_contexts"},
        update={"flow_cases": {source["id"]: {"version", "updated_at"}}}, new_kind="addon")
    body, view, created, request = await original_submit(e, DOMAIN["addon"], lambda p: bool(re.fullmatch(r"/api/addon-orders/\d+", p)), guard, fixture["store_id"], status=201)
    key = body["id"]
    require(request["source_order_id"] == current["id"] and request["source_version"] == current["version"] and not request["delivery_blocking"]
            and body["flow_version"] == 3 and case(e, key)["parent_id"] == source["id"], "加装创建未绑定当前原单或误作交车前阻断")
    await expect(e.page.locator("#main h1")).to_have_text("销售加装明细")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    e.observe("addon_created_page_ready", {"case_id": key, "number": view["number"], "original_detail_and_catalogue_rendered": True})
    sales, initial_view, quote_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_quote", "sales")
    options = initial_view["original_catalogue"]
    await form(e, "addon", "quote")
    candidates = [r for r in options["items"] if r["id"] == item["id"]]
    require(len(candidates) == 1 and candidates[0]["available_milli"] >= 1000, "加装当前原商品可用量不足，不可借前序旧数量")
    line = e.page.locator('#modal [data-addon-line]').nth(0)
    await select_value(e, '#modal [data-addon-line]:nth-of-type(1) [name="item"]', item["id"], "明确本次采购商品")
    await select_value(e, '#modal [data-addon-line]:nth-of-type(1) [name="work"]', work["id"], "明确原安装作业")
    for name, value in (("quantity", "1.000"), ("goods", "30.00"), ("installation", "5.00")):
        e.action("fill", "填写本版明确加装金额数量", field=name, value=value)
        await line.locator(f'[name="{name}"]').fill(value)
    await e.fill('#modal [name="discount"]', "0.00", "明确本版无额外折扣")
    await e.fill('#modal [name="reason"]', "收费商品30元及安装5元；采购成本取实际原账，不以报价猜成本", "填写本版核价依据")
    view, quoted = await command(e, fixture, "addon", key, sales, "quote", parent=source["id"], item=item["id"], append={"addon_quotes", "addon_lines"})
    q = rows(e, "addon_quotes", key)[0]
    lines = e.db.rows("SELECT * FROM addon_lines WHERE quote_id=? ORDER BY id", (q["id"],))
    require(len(lines) == 1 and q["goods_cents"] == 3000 and q["installation_cents"] == 500 and q["discount_cents"] == 0
            and lines[0]["item_id"] == item["id"] and lines[0]["work_item_id"] == work["id"] and lines[0]["quantity_milli"] == 1000
            and lines[0]["goods_unit_cents"] == 3000 and lines[0]["installation_unit_cents"] == 500 and not json.loads(q["gift_terms"]), "加装本版冻结项目/金额不符")
    cp.note(case_id=key, native_create=created, native_quote=quoted, quote=q, line=lines[0], quote_owner=quote_owner)
    manager, _, approve_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_approve", "manager")
    proof = await upload(e, fixture, key, manager, "authorization", "addon-price", f"独立核本版{q['id']}商品与安装合计3500分。")
    await form(e, "addon", "approve")
    await e.fill('#modal [name="minimum"]', "35.00", "主管明确本版最低合计")
    await select_value(e, '#modal [name="allow"]', "不允许低于最低额", "不默认批准低价")
    await e.fill('#modal [name="reason"]', "独立核对当前原件与3500分合计，不批准赠送或额外优惠", "填写独立价格批准")
    await proof_choice(e, proof)
    _, approved = await command(e, fixture, "addon", key, manager, "approve", parent=source["id"], item=item["id"], append={"addon_approvals"}, expected={"minimum_cents": 3500, "allow_below_minimum": False, "evidence_id": proof["file"]["id"]})
    approval = one(e, "addon_approvals", e.db.rows("SELECT id FROM addon_approvals WHERE quote_id=?", (q["id"],))[0]["id"])
    require(approval["actor_id"] == manager["id"] != sales["id"] and approval["minimum_cents"] == 3500, "加装核价未独立批准当前版")
    sales, _, auth_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_authorize", "sales")
    proof = await upload(e, fixture, key, sales, "authorization", "addon-authorize", f"合成客户明确当前报价{q['id']}摘要{q['digest']}1件商品与安装。")
    before = stock_facts(e, item["id"])
    await form(e, "addon", "authorize")
    await proof_choice(e, proof)
    _, authorized = await command(e, fixture, "addon", key, sales, "authorize", parent=source["id"], item=item["id"], append={"addon_authorizations", "addon_reservations"}, expected={"quote_id": q["id"], "evidence_id": proof["file"]["id"]})
    after = stock_facts(e, item["id"])
    require(before["moves"] == after["moves"] and before["balances"] == after["balances"] and before["entries"] == after["entries"]
            and before["item"]["quantity_milli"] == after["item"]["quantity_milli"] and sum(r["quantity_milli"] for r in rows(e, "addon_reservations", key)) == 1000, "加装授权占用冒充实际出库")
    inventory, _, dispatch_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_dispatch", "inventory")
    proof = await upload(e, fixture, key, inventory, "evidence", "addon-dispatch", f"实际核对原VIN{vehicle['vin']}及商品1件；原库位{location['id']}。")
    await e.click(f'#main [data-act="open"][data-route="warehouse-allocation/{key}"]', "原库管进入本单库位准备")
    await expect(e.page.locator("#main h1")).to_have_text("准备物资库位")
    await e.click(f'#main [data-act="wh-allocate"][data-id="{item["id"]}"]', "明确该原商品的准备位置")
    await select_value(e, '#modal [name="purpose"]', "addon_dispatch_v3", "明确原加装出库动作")
    await e.fill('#modal [name="quantity"]', "1.000", "填写实际本次数量")
    await select_value(e, '#modal [name="location"]', location["id"], "明确来源库位")
    await e.fill('#modal [name="location_qty"]', "1.000", "完整分配原库位数量")
    prepared_before = stock_facts(e, item["id"])
    version = case(e, key)["version"]
    guard = Guard(e, "addon_original_bin_prepare", inventory, fixture["store_id"], append={"flow_events", "audit_logs", "flow_request_receipts", "warehouse_allocations", "warehouse_allocation_lines"},
        update=updates(e, key, allocation=True), cases={key}, item_id=item["id"])
    prepared, _, prepared_api, request = await original_submit(e, f"/api/warehouse/allocations/{key}", lambda p: p == f"/api/warehouse/allocations/{key}", guard, fixture["store_id"])
    require(prepared["prepared"] and request["version"] == version and request["values"] == {"item_id": item["id"], "quantity_milli": -1000, "purpose": "addon_dispatch_v3", "locations": [{"location_id": location["id"], "quantity_milli": 1000}]}
            and stock_facts(e, item["id"]) == prepared_before, "库位准备改写了实际库存或分配错误")
    plans = e.db.rows("SELECT * FROM warehouse_allocations WHERE case_id=? AND item_id=? AND purpose='addon_dispatch_v3' AND status='prepared'", (key, item["id"]))
    require(len(plans) == 1, "本次加装原位置准备不唯一")
    inventory, _, _ = await responsible(e, context, credentials, fixture, "addon", key, "addon_dispatch", "inventory")
    await form(e, "addon", "dispatch")
    await select_value(e, '#modal [name="line"]', lines[0]["line_key"] + " · " + item["name"], "明确获准本行原商品")
    await e.fill('#modal [name="quantity"]', "1.000", "确认实际领出一件")
    await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "逐位核对本次原实车VIN")
    await proof_choice(e, proof)
    stock_before = stock_facts(e, item["id"])
    _, dispatched = await command(e, fixture, "addon", key, inventory, "dispatch", parent=source["id"], item=item["id"], physical=True, allocation=True, vehicle=vehicle["id"],
        append={"addon_targets", "addon_dispatches", "addon_reservations", "flow_stock_moves", "warehouse_entries"}, expected={"checked_vin": vehicle["vin"], "lines": [{"line_key": lines[0]["line_key"], "quantity_milli": 1000}]})
    dispatches = rows(e, "addon_dispatches", key)
    require(len(dispatches) == 1, "本次原发料批不唯一")
    dispatch = dispatches[0]
    move = one(e, "flow_stock_moves", dispatch["stock_move_id"])
    cost = stock_before["item"]["inventory_value_cents"] if stock_before["item"]["quantity_milli"] == 1000 else (2 * stock_before["item"]["inventory_value_cents"] * 1000 + stock_before["item"]["quantity_milli"]) // (2 * stock_before["item"]["quantity_milli"])
    physical = stock_facts(e, item["id"])
    entries = physical["entries"][len(stock_before["entries"]):]
    original_balance = next(b for b in stock_before["balances"] if b["location_id"] == location["id"])
    current_balance = one(e, "warehouse_balances", original_balance["id"])
    consumed = one(e, "warehouse_allocations", plans[0]["id"])
    target = one(e, "addon_targets", dispatch["target_id"])
    require(target["vin"] == vehicle["vin"] and target["vehicle_id"] == vehicle["id"] and dispatch["value_cents"] == cost
            and move["case_id"] == key and move["item_id"] == item["id"] and move["quantity_milli"] == -1000 and move["value_cents"] == -cost
            and move["purpose"] == "addon_dispatch_v3" and move["original_id"] is None and move["actor_id"] == inventory["id"]
            and physical["item"]["quantity_milli"] == stock_before["item"]["quantity_milli"] - 1000
            and physical["item"]["inventory_value_cents"] == stock_before["item"]["inventory_value_cents"] - cost
            and sum(x["quantity_milli"] for x in entries) == -1000 and sum(x["value_cents"] for x in entries) == -cost
            and all(x["stock_move_id"] == move["id"] and x["actor_id"] == inventory["id"]
                    and (x["balance_id"] == original_balance["id"] or x["quantity_milli"] == 0 and x["reason"] == "average_revaluation") for x in entries)
            and current_balance["quantity_milli"] == original_balance["quantity_milli"] - 1000
            and current_balance["value_cents"] == original_balance["value_cents"] + sum(x["value_cents"] for x in entries if x["balance_id"] == original_balance["id"])
            and sum(b["quantity_milli"] for b in physical["balances"]) == physical["item"]["quantity_milli"]
            and sum(b["value_cents"] for b in physical["balances"]) == physical["item"]["inventory_value_cents"]
            and consumed["status"] == "consumed" and consumed["stock_move_id"] == move["id"]
            and sum(r["quantity_milli"] for r in rows(e, "addon_reservations", key)) == 0, "真实原VIN发料/原成本/位置或占额释放不符")
    cp.note(native_approve=approved, native_authorize=authorized, prepare=prepared_api, dispatch=dispatch, stock_move=move, warehouse_entries=entries, target=target, native_dispatch=dispatched)
    technician, _, install_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_install", "technician")
    proof = await upload(e, fixture, key, technician, "inspection", "addon-install", f"原领料批{dispatch['id']}实际安装1件在VIN{vehicle['vin']}。")
    await form(e, "addon", "install", extra=f'[data-dispatch="{dispatch["id"]}"]')
    await e.fill('#modal [name="quantity"]', "1.000", "记录真实安装数量")
    await e.fill('#modal [name="result"]', "本次合成现场安装完成，尚待服务顾问独立检查", "技师记录安装事实")
    await proof_choice(e, proof)
    _, installed = await command(e, fixture, "addon", key, technician, "install", parent=source["id"], append={"addon_installations"}, expected={"dispatch_id": dispatch["id"], "quantity_milli": 1000})
    installations = e.db.rows("SELECT * FROM addon_installations WHERE dispatch_id=? ORDER BY id", (dispatch["id"],))
    require(len(installations) == 1 and installations[0]["actor_id"] == technician["id"], "原安装事实缺本人或重复")
    installation = installations[0]
    quality_facts = []
    for passed in (False, True):
        service, _, quality_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_quality", "service")
        proof = await upload(e, fixture, key, service, "inspection", "addon-quality", f"安装{installation['id']}本次独立检查{passed}；{'整改后复检合格' if passed else '合成支架固定不合格'}。")
        await form(e, "addon", "quality", extra=f'[data-installation="{installation["id"]}"]')
        await select_value(e, '#modal [name="outcome"]', "合格" if passed else "不合格", "明确本次实际检查结论")
        await e.fill('#modal [name="result"]', "整改后合成固定及安全检查合格" if passed else "合成检查支架固定不足，需技师整改后复检", "独立服务顾问记录检查结果")
        await proof_choice(e, proof)
        view, checked = await command(e, fixture, "addon", key, service, "quality", parent=source["id"], append={"addon_inspections"}, expected={"installation_id": installation["id"], "passed": passed})
        checks = e.db.rows("SELECT * FROM addon_inspections WHERE installation_id=? ORDER BY id", (installation["id"],))
        require(checks[-1]["passed"] == passed and checks[-1]["actor_id"] == service["id"] != technician["id"], "原检查未与安装岗位分离")
        quality_facts.append({"check": checks[-1], "native": checked, "task_owner": quality_owner})
        if not passed:
            require(not rows(e, "addon_acceptances", key) and "addon_accept" not in {t["key"] for t in rows(e, "flow_tasks", key) if t["status"] == "open"}, "不合格检查被误作客户接收")
            technician, _, rectify_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_rectify", "technician")
            proof = await upload(e, fixture, key, technician, "inspection", "addon-rectify", f"原不合格检查{checks[-1]['id']}重新紧固并待独立复检。")
            await form(e, "addon", "rectify", extra=f'[data-inspection="{checks[-1]["id"]}"]')
            await e.fill('#modal [name="result"]', "本次合成支架已重新固定，提交原检查后的独立复检", "技师记录原缺陷整改")
            await proof_choice(e, proof)
            _, rectified = await command(e, fixture, "addon", key, technician, "rectify", parent=source["id"], append={"addon_rectifications"}, expected={"inspection_id": checks[-1]["id"]})
            rectifications = e.db.rows("SELECT * FROM addon_rectifications WHERE inspection_id=?", (checks[-1]["id"],))
            require(len(rectifications) == 1 and rectifications[0]["actor_id"] == technician["id"], "原缺陷整改未独立追加")
    sales, _, accept_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_accept", "sales")
    proof = await upload(e, fixture, key, sales, "authorization", "addon-accept", f"合成客户实际接收原当前报价{q['id']}已复检的安装。")
    await form(e, "addon", "accept")
    await proof_choice(e, proof)
    _, accepted = await command(e, fixture, "addon", key, sales, "accept", parent=source["id"], append={"addon_acceptances"}, expected={"quote_id": q["id"]})
    accepts = rows(e, "addon_acceptances", key)
    require(len(accepts) == 1 and accepts[0]["amount_cents"] == 3500 and accepts[0]["value_cents"] == cost and not rows(e, "flow_payment_links", key), "客户接收金额成本不符或伪造到账")
    finance, _, receive_owner = await responsible(e, context, credentials, fixture, "addon", key, "addon_receive", "finance")
    proof = await upload(e, fixture, key, finance, "receipt", "addon-receive", "合成原客户本次加装真实到账3500分，独立原款。")
    await form(e, "addon", "receive")
    await e.fill('#modal [name="amount"]', "35.00", "登记原客户真实加装款")
    await account_choice(e, account)
    reference = "A-" + uuid.uuid4().hex[:20]
    await e.fill('#modal [name="reference"]', reference, "填写本次独立实际原流水")
    await proof_choice(e, proof)
    view, received = await command(e, fixture, "addon", key, finance, "receive", parent=source["id"], account=account["id"], append={"addon_payments", "flow_payment_links", "cash_entries", "business_entity_cash_contexts"}, expected={"amount_cents": 3500, "account_id": account["id"], "reference": reference})
    links, payments = rows(e, "flow_payment_links", key), rows(e, "addon_payments", key)
    require(len(links) == len(payments) == 1 and payments[0]["payment_link_id"] == links[0]["id"] and links[0]["original_id"] is None, "加装独立原款关联错误")
    cash = one(e, "cash_entries", links[0]["cash_id"])
    require(links[0]["amount_cents"] == cash["amount_cents"] == 3500 and links[0]["direction"] == cash["direction"] == "in" and cash["created_by"] == finance["id"]
            and cash["voucher_no"] == reference and cash["account"] == account["name"] and cash["approval_state"] == "approved"
            and view["totals"]["receivable_cents"] == view["totals"]["refund_due_cents"] == 0 and case(e, key)["state"] == "completed", "加装实际现金或最终应收状态错误")
    await refresh(e, "addon", key)
    await cp.passed(case_id=key, native_install=installed, installation=installation, quality=quality_facts, native_rectify=rectified, rectification=rectifications[0], native_accept=accepted,
        acceptance=accepts[0], payment_link=links[0], addon_payment=payments[0], cash=cash, native_receive=received, refresh_business_unchanged=True,
        task_owners=[quote_owner, approve_owner, auth_owner, dispatch_owner, install_owner, rectify_owner, accept_owner, receive_owner],
        conditional=[{"check_id": "HK-012-original-disposition", "status": "not_tested", "reason": "未走零价赠送、拆回/取消/随车移交及原款退款；不继承收费安装路径"}])
    return key


def digest(operation, payload):
    return hashlib.sha256(json.dumps({"operation": operation, "payload": payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def service_master(e, context, credentials, fixture, kind, token):
    manager = await login_as(e, context, credentials, fixture["manager_key"], "service-orders", fixture["store_id"])
    await expect(e.page.locator("#main h1")).to_have_text("代办与其它客户服务")
    await e.click(f'#main [data-act="serviceorder-master"][data-kind="{kind}"]', "主管原UI建立本次明确服务主档")
    values = {"code": ("P" if kind == "payees" else "I") + token,
        "name": ("合成代缴机构" if kind == "payees" else "合成客户其它服务") + token}
    values.update({"account_name": "合成代缴机构独立户名", "account_reference": "SYNTH-PAYEE-" + token} if kind == "payees" else {"unit": "次", "standard_fee": "8.00"})
    for field, value in values.items():
        await e.fill(f'#modal [name="{field}"]', value, "明确主档原字段 " + field)
    table = "service_payees" if kind == "payees" else "service_income_items"
    guard = Guard(e, "service_original_master_" + kind, manager, fixture["store_id"], append={table, "service_requests"})
    body, _, meta, request = await original_submit(e, DOMAIN["service"] + "/" + kind, lambda p: p == DOMAIN["service"], guard, fixture["store_id"], status=201)
    row = one(e, table, body["id"])
    require(row["code"] == values["code"] and row["name"] == values["name"] and row["active"] and row["store_id"] == fixture["store_id"], "原服务主档保存不符")
    for k, value in request.items():
        if k != "request_id":
            require(row[k] == value, "主档UI/API/DB字段不一致：" + k)
    await expect(e.page.locator("#main h1")).to_have_text("代办与其它客户服务")
    return row, meta


async def service_create(e, context, credentials, fixture, source, customer, subtype, role, day):
    actor, current = await current_source(e, context, credentials, fixture, role, source["id"])
    await nav(e, "service-orders", "代办与其它客户服务", DOMAIN["service"])
    await e.click('#main [data-act="serviceorder-new"]', "明确建立本次独立客户服务")
    await select_value(e, '#modal [name="subtype"]', "代办服务" if subtype == "agency" else "其它客户服务", "明确原业务类别")
    await select_value(e, '#modal [name="customer"]', f'{customer["id"]} · {customer["name"]}', "明确原销售客户")
    await select_value(e, '#modal [name="source"]', f'{current["id"]} · {current["number"]}', "关联本次当前已交付原销售")
    await select_value(e, '#modal [name="vehicle"]', "不关联车辆", "客户服务未声明额外客户车辆事实")
    await select_value(e, '#modal [name="blocking"]', "允许后续办理", "明确交付后办理")
    await e.fill('#modal [name="due_date"]', day, "明确本次客户服务期限")
    await e.fill('#modal [name="reason"]', "本次原客户独立服务申请，服务费与代缴本金逐项明示", "填写实际服务申请")
    guard = Guard(e, "service_original_create_" + subtype, actor, fixture["store_id"], append=COMMON | {"flow_cases", "service_orders", "service_requests", "business_entity_case_contexts"},
        update={"flow_cases": {source["id"]: {"version", "updated_at"}}}, new_kind=subtype)
    body, view, meta, request = await original_submit(e, DOMAIN["service"], lambda p: bool(re.fullmatch(r"/api/service-orders/\d+", p)), guard, fixture["store_id"], status=201)
    require(request["subtype"] == subtype and request["customer_id"] == customer["id"] and request["source_order_id"] == current["id"]
            and request["source_version"] == current["version"] and not request["delivery_blocking"] and request["customer_vehicle_id"] is None
            and case(e, body["id"])["flow_version"] == (3 if subtype == "agency" else 2) and view["order"]["source_order_id"] == source["id"], "独立客户服务创建身份或当前来源不符")
    return body["id"], meta


async def service_quote(e, context, credentials, fixture, key, source_id, role, fee_source, fee_cents, day, *, payee=None, revision=1):
    actor, _, owner = await responsible(e, context, credentials, fixture, "service", key, "serviceorder_quote", role, optional=revision > 1)
    await form(e, "service", "quote")
    for index, source_value, amount in ((0, "fee:" + str(fee_source["id"]), fee_cents),) + (((1, "pass:" + str(payee["id"]), 1000),) if payee else ()):
        section = e.page.locator('#modal [data-service-line]').nth(index)
        e.action("select", "选择当前原服务项目", source=source_value)
        await section.locator('[name="source"]').select_option(source_value)
        await expect(section.locator('[name="source"]')).to_have_value(source_value)
        if index == 1:
            e.action("fill", "明确代缴事项", value="合成办理原证件代缴本金")
            await section.locator('[name="name"]').fill("合成办理原证件代缴本金")
        for field, value in (("quantity", "1.000"), ("price", fen_text(amount)), ("due_date", day)):
            e.action("fill", "填写本版原服务项目数量价格期限", field=field, value=value)
            await section.locator(f'[name="{field}"]').fill(value)
    await e.fill('#modal [name="discount"]', "0.00", "明确本版不另减服务费")
    await e.fill('#modal [name="reason"]', f"本次明确第{revision}版客户服务费{fee_cents}分，代缴本金{'1000' if payee else '0'}分；本版独立确认", "填写本版真实报价依据")
    view, meta = await command(e, fixture, "service", key, actor, "quote", parent=source_id, append={"service_quotes", "service_lines"})
    quotes = rows(e, "service_quotes", key)
    require(len(quotes) == revision and quotes[-1]["revision"] == revision and quotes[-1]["fee_cents"] == fee_cents
            and quotes[-1]["pass_cents"] == (1000 if payee else 0) and quotes[-1]["discount_cents"] == 0, "原服务本版金额或版本不符")
    q = quotes[-1]
    lines = e.db.rows("SELECT * FROM service_lines WHERE quote_id=? ORDER BY id", (q["id"],))
    require(len(lines) == (2 if payee else 1) and {l["bucket"] for l in lines} == ({"fee", "pass"} if payee else {"fee"})
            and len({l["line_key"] for l in lines}) == len(lines) and all(l["quantity_milli"] == 1000 and l["discount_cents"] == 0 and l["due_date"] == day for l in lines), "服务行真实数量/单位/到期或重复行不符")
    for line in lines:
        if line["bucket"] == "fee":
            field = "agency_project_id" if case(e, key)["kind"] == "agency" else "income_item_id"
            require(line[field] == fee_source["id"] and line["amount_cents"] == line["unit_price_cents"] == fee_cents and line["payee_id"] is None, "服务费误用代缴或主档")
        else:
            frozen_payee = json.loads(line["payee_snapshot"])
            require(line["payee_id"] == payee["id"] and line["amount_cents"] == line["unit_price_cents"] == 1000 and frozen_payee == {k: payee[k] for k in ("name", "account_name", "account_reference")}, "原本金和第三方收款主体快照不符")
    canonical = [{k: json.loads(l[k]) if k == "payee_snapshot" else l[k] for k in ("line_key", "bucket", "agency_project_id", "income_item_id", "payee_id", "code", "name", "unit", "payee_snapshot", "quantity_milli", "unit_price_cents", "discount_cents", "amount_cents", "due_date")} for l in lines]
    require(q["digest"] == digest("service_quote", canonical) and not view["quote_approved"] and not view["summary"]["authorized"]
            and not rows(e, "flow_payment_links", key) and not rows(e, "service_tender_slices", key) and not rows(e, "service_fulfillments", key), "报价冻结摘要/新版准入错误或报价制造资金履约")
    return q, lines, {"native": meta, "task_owner": owner, "frozen_quote_digest_verified": True}


async def service_approve_authorize(e, context, credentials, fixture, key, source_id, role, quote):
    manager, _, owner = await responsible(e, context, credentials, fixture, "service", key, "serviceorder_approve", "manager")
    proof = await upload(e, fixture, key, manager, "authorization", "service-price", f"主管独立核当前报价{quote['id']}摘要{quote['digest']}，服务费{quote['fee_cents']}分。")
    await form(e, "service", "approve")
    await e.fill('#modal [name="minimum"]', fen_text(quote["fee_cents"]), "明确本版最低服务费")
    await select_value(e, '#modal [name="allow"]', "不允许低于最低额", "明确不批准低价例外")
    await e.fill('#modal [name="reason"]', "独立逐项核服务费及原代缴本金，本版原件真实相符", "填写主管本版核价说明")
    await proof_choice(e, proof)
    _, approved = await command(e, fixture, "service", key, manager, "approve", parent=source_id, append={"service_price_approvals"}, expected={"minimum_fee_cents": quote["fee_cents"], "allow_below_minimum": False})
    approvals = e.db.rows("SELECT * FROM service_price_approvals WHERE quote_id=?", (quote["id"],))
    require(len(approvals) == 1 and approvals[0]["actor_id"] == manager["id"] != quote["actor_id"] and manager["id"] != case(e, key)["created_by"], "服务本版核价不是另一主管")
    actor, _, auth_owner = await responsible(e, context, credentials, fixture, "service", key, "serviceorder_authorize", role)
    proof = await upload(e, fixture, key, actor, "authorization", "service-authorize", f"合成客户明确授权第{quote['revision']}版报价{quote['id']}摘要{quote['digest']}及逐项费用。")
    await form(e, "service", "authorize")
    await proof_choice(e, proof)
    view, authorized = await command(e, fixture, "service", key, actor, "authorize", parent=source_id, append={"service_authorizations"}, expected={"quote_id": quote["id"]})
    authorizations = e.db.rows("SELECT * FROM service_authorizations WHERE quote_id=?", (quote["id"],))
    require(len(authorizations) == 1 and authorizations[0]["actor_id"] == actor["id"] and view["quote"]["id"] == quote["id"] and view["summary"]["authorized"], "客户当前版本授权缺独立实际事实")
    return view, {"approval": approvals[0], "authorization": authorizations[0], "native_approve": approved, "native_authorize": authorized, "task_owners": [owner, auth_owner]}


async def service_receive(e, context, credentials, fixture, key, source_id, account, amount, day):
    finance, _, owner = await responsible(e, context, credentials, fixture, "service", key, "serviceorder_receive", "finance")
    proof = await upload(e, fixture, key, finance, "receipt", "service-receive", f"合成实际原客户到账{amount}分，费用与本金明确按本版分配。")
    await form(e, "service", "receive")
    await e.fill('#modal [name="amount"]', fen_text(amount), "登记客户实际到账金额")
    await account_choice(e, account)
    reference = "S-" + uuid.uuid4().hex[:20]
    await e.fill('#modal [name="reference"]', reference, "填写独立实际收款流水")
    await proof_choice(e, proof)
    view, native = await command(e, fixture, "service", key, finance, "receive", parent=source_id, account=account["id"], append={"cash_entries", "flow_payment_links", "service_tender_slices", "business_entity_cash_contexts"}, expected={"amount_cents": amount, "account_id": account["id"], "reference": reference})
    links = rows(e, "flow_payment_links", key)
    require(len(links) == 1, "本次客户服务现金不唯一")
    link = links[0]
    cash = one(e, "cash_entries", link["cash_id"])
    tenders = rows(e, "service_tender_slices", key)
    require(link["original_id"] is None and link["account_id"] == account["id"] and link["direction"] == cash["direction"] == "in"
            and link["amount_cents"] == cash["amount_cents"] == amount and cash["account"] == account["name"] and cash["voucher_no"] == reference
            and cash["created_by"] == finance["id"] and cash["approval_state"] == "approved" and cash["business_date"] == link["business_date"] == day
            and tenders and all(t["payment_link_id"] == link["id"] and t["credit_link_id"] is None and t["original_id"] is None for t in tenders)
            and sum(t["amount_cents"] for t in tenders) == amount and view["summary"]["customer_due_cents"] == 0, "原服务现金/逐项本金分配不匹配")
    return view, {"native": native, "task_owner": owner, "payment_link": link, "cash": cash, "tenders": tenders}


async def service_line_action(e, context, credentials, fixture, key, source_id, role, line, action, day, *, outcome=None, supplement=None):
    actor, before, owner = await responsible(e, context, credentials, fixture, "service", key, "serviceorder_handle", role)
    proof = await upload(e, fixture, key, actor, "authorization", "service-" + action, f"原服务{key}明细{line['line_key']}本次真实{action}，结果{outcome}补件来源{supplement}。")
    await form(e, "service", action, extra=f'[data-line="{line["line_key"]}"]')
    expected = {"line_key": line["line_key"], "evidence_id": proof["file"]["id"]}
    if action == "submit":
        reference = "EXT-" + uuid.uuid4().hex[:20]
        await e.fill('#modal [name="external_reference"]', reference, "填写实际合成外部受理编号")
        await e.fill('#modal [name="submitted_on"]', day, "填写本次实际提交日期")
        expected.update(external_reference=reference, submitted_on=day)
        if supplement:
            expected["supplement_result_id"] = supplement
        appended = {"service_submissions"}
    elif action == "external_result":
        submissions = [s for s in before["submissions"] if s["line_key"] == line["line_key"]]
        require(submissions, "原项目没有实际外部提交")
        await select_value(e, '#modal [name="outcome"]', {"approved": "批准", "need_documents": "要求补件"}[outcome], "明确真实外部结果类别")
        await e.fill('#modal [name="result"]', "合成机关要求补充本项原资料，尚未批准" if outcome == "need_documents" else "合成外部单位已批准本项目原提交，本次结果独立确认", "记录本项实际外部结果")
        expected.update(submission_id=submissions[-1]["id"], outcome=outcome)
        appended = {"service_external_results"}
    else:
        await e.fill('#modal [name="result"]', "本项合成手续和原资料已实际办理并向原客户交接", "记录本项真实办结与交接")
        appended = {"service_fulfillments"}
    await proof_choice(e, proof)
    view, native = await command(e, fixture, "service", key, actor, action, parent=source_id, append=appended, expected=expected)
    native.update(task_owner=owner, proof=proof)
    if action == "submit":
        current = [s for s in rows(e, "service_submissions", key) if s["line_key"] == line["line_key"]]
        require(current[-1]["quote_id"] == line["quote_id"] and current[-1]["external_reference"] == reference and current[-1]["supplement_result_id"] == supplement, "实际提交没有绑定本版原行/原补件要求")
        native["fact"] = current[-1]
    elif action == "external_result":
        current = e.db.rows("SELECT * FROM service_external_results WHERE submission_id=?", (expected["submission_id"],))
        require(len(current) == 1 and current[0]["outcome"] == outcome and current[0]["actor_id"] == actor["id"], "外部结果缺唯一当前原提交")
        native["fact"] = current[0]
        if outcome == "need_documents":
            require(not any(f["line_key"] == line["line_key"] for f in view["fulfillments"]), "补件要求被误作办结")
    else:
        current = [f for f in rows(e, "service_fulfillments", key) if f["line_key"] == line["line_key"]]
        require(len(current) == 1 and current[0]["line_id"] == line["id"] and current[0]["amount_cents"] == line["amount_cents"] and current[0]["actor_id"] == actor["id"], "实际办结未绑定本版原费用")
        native["fact"] = current[0]
    return view, native


async def agency_path(e, context, credentials, fixture, cp, source, customer, project, account, day, token):
    cp.start("HK-015")
    payee, master_api = await service_master(e, context, credentials, fixture, "payees", token)
    key, created = await service_create(e, context, credentials, fixture, source, customer, "agency", "sales", day)
    cp.note(case_id=key, payee=payee, native_payee=master_api, native_create=created)
    cp.start("HK-016")
    q1, lines1, quote1 = await service_quote(e, context, credentials, fixture, key, source["id"], "sales", project, 2000, day, payee=payee)
    _, authorization1 = await service_approve_authorize(e, context, credentials, fixture, key, source["id"], "sales", q1)
    q2, lines2, quote2 = await service_quote(e, context, credentials, fixture, key, source["id"], "sales", project, 2500, day, payee=payee, revision=2)
    require({l["line_key"] for l in lines1} == {l["line_key"] for l in lines2} and q2["id"] != q1["id"] and q2["digest"] != q1["digest"], "代办改版未保留稳定原项目或摘要未变化")
    require(one(e, "service_quotes", q1["id"]) == q1 and e.db.rows("SELECT * FROM service_lines WHERE quote_id=? ORDER BY id", (q1["id"],)) == lines1, "旧报价原行被覆盖")
    view, authorization2 = await service_approve_authorize(e, context, credentials, fixture, key, source["id"], "sales", q2)
    require(len(view["quote_history"]) == 2 and all(v["approval"] and v["authorization"] for v in view["quote_history"])
            and view["quote"]["id"] == q2["id"] and not rows(e, "service_tender_slices", key) and not rows(e, "service_fulfillments", key), "两版报价未各自授权或报价阶段制造资金/履约")
    history = e.page.locator('#main details').filter(has=e.page.locator('summary').filter(has_text="查看全部 2 个冻结版本"))
    await expect(history).to_have_count(1)
    e.action("click", "核对本单两个冻结报价及各自授权历史")
    await history.locator('summary').click()
    await expect(history).to_contain_text("服务费 20.00 元")
    await expect(history).to_contain_text("服务费 25.00 元")
    await expect(history.locator('h3')).to_have_count(2)
    await cp.passed(case_id=key, first_quote=q1, first_lines=lines1, first_quote_api=quote1, first_approval_authorization=authorization1,
        second_quote=q2, second_lines=lines2, second_quote_api=quote2, second_approval_authorization=authorization2, history=view["quote_history"],
        conditional=[{"check_id": "HK-016-frozen-fact-reprice", "status": "not_tested", "reason": "本次改价发生于真实资金和履约前；未提交已履约原行改价"}])
    cp.start("HK-015")
    _, collection = await service_receive(e, context, credentials, fixture, key, source["id"], account, 3500, day)
    require({t["bucket"]: t["amount_cents"] for t in collection["tenders"]} == {"fee": 2500, "pass": 1000}, "客户服务费与原代缴本金未精确分离")
    tender = next(t for t in collection["tenders"] if t["bucket"] == "pass")
    finance, _, owner = await responsible(e, context, credentials, fixture, "service", key, "serviceorder_pass", "finance")
    proof = await upload(e, fixture, key, finance, "receipt", "service-disburse", f"本次原本金分配{tender['id']}实际第三方支付1000分，同原账户。")
    await form(e, "service", "disburse", extra=f'[data-tender="{tender["id"]}"]')
    await e.fill('#modal [name="amount"]', "10.00", "登记本次真实第三方代缴")
    await account_choice(e, account)
    reference = "PASS-" + uuid.uuid4().hex[:20]
    await e.fill('#modal [name="reference"]', reference, "填写实际代缴独立流水")
    await proof_choice(e, proof)
    view, disbursed = await command(e, fixture, "service", key, finance, "disburse", parent=source["id"], account=account["id"], append={"service_pass_entries", "cash_entries", "business_entity_cash_contexts"}, expected={"tender_id": tender["id"], "amount_cents": 1000, "account_id": account["id"]})
    entries = rows(e, "service_pass_entries", key)
    require(len(entries) == 1 and entries[0]["tender_id"] == tender["id"] and entries[0]["purpose"] == "disburse" and entries[0]["original_id"] is None, "第三方实际代缴没有引用原本金")
    pass_cash = one(e, "cash_entries", entries[0]["cash_id"])
    require(pass_cash["direction"] == "out" and pass_cash["amount_cents"] == 1000 and pass_cash["account"] == account["name"] and pass_cash["category"] == "service_pass_pay"
            and pass_cash["voucher_no"] == reference and pass_cash["created_by"] == finance["id"] and pass_cash["business_date"] == day
            and view["summary"]["pass_cash_balance_cents"] == 0, "第三方支付现金或剩余本金不符")
    line_evidence = []
    for line in lines2:
        _, submitted = await service_line_action(e, context, credentials, fixture, key, source["id"], "sales", line, "submit", day)
        supplement = None
        if line["bucket"] == "fee":
            _, requested = await service_line_action(e, context, credentials, fixture, key, source["id"], "sales", line, "external_result", day, outcome="need_documents")
            supplement = requested["fact"]["id"]
            _, resubmitted = await service_line_action(e, context, credentials, fixture, key, source["id"], "sales", line, "submit", day, supplement=supplement)
        _, approved = await service_line_action(e, context, credentials, fixture, key, source["id"], "sales", line, "external_result", day, outcome="approved")
        final, fulfilled = await service_line_action(e, context, credentials, fixture, key, source["id"], "sales", line, "fulfill", day)
        line_evidence.append({"line": line, "submission": submitted, "need_documents": requested if supplement else None,
            "supplement": resubmitted if supplement else None, "approved": approved, "fulfilled": fulfilled})
    require(len(final["submissions"]) == 3 and len(final["results"]) == 3 and len(final["fulfillments"]) == 2
            and final["summary"]["fee_charge_cents"] == 2500 and final["summary"]["pass_charge_cents"] == 1000
            and final["summary"]["customer_paid_cents"] == 3500 and final["summary"]["customer_due_cents"] == 0
            and final["summary"]["thirdparty_paid_cents"] == 1000 and final["summary"]["thirdparty_returned_cents"] == final["summary"]["pass_cash_balance_cents"] == 0
            and case(e, key)["state"] == "completed" and not [t for t in rows(e, "flow_tasks", key) if t["status"] == "open"], "代办逐项办结或原资金终点不完整")
    await refresh(e, "service", key)
    await cp.passed(case_id=key, current_quote=q2, collection=collection, thirdparty=entries[0], thirdparty_cash=pass_cash, native_disburse=disbursed,
        disburse_owner=owner, line_results=line_evidence, final_summary=final["summary"], refresh_business_unchanged=True,
        conditional=[{"check_id": "HK-015-original-refunds", "status": "not_tested", "reason": "实际逐项补件办结已执行；第三方原路退回/终止保留费/客户退款另需原事实，未本批执行"}])
    return key


async def customer_other_path(e, context, credentials, fixture, cp, source, customer, account, day, token):
    income_item, master_api = await service_master(e, context, credentials, fixture, "income-items", token)
    key, created = await service_create(e, context, credentials, fixture, source, customer, "other_income", "service", day)
    cp.note(customer_other_case_id=key, customer_income_item=income_item, customer_master_api=master_api, customer_create=created)
    quote, lines, quoted = await service_quote(e, context, credentials, fixture, key, source["id"], "service", income_item, 800, day)
    _, authorized = await service_approve_authorize(e, context, credentials, fixture, key, source["id"], "service", quote)
    _, fulfilled = await service_line_action(e, context, credentials, fixture, key, source["id"], "service", lines[0], "fulfill", day)
    view, collection = await service_receive(e, context, credentials, fixture, key, source["id"], account, 800, day)
    summary = view["summary"]
    require(len(view["fulfillments"]) == 1 and not view["submissions"] and not view["results"]
            and not rows(e, "service_pass_entries", key) and len(collection["tenders"]) == 1
            and collection["tenders"][0]["bucket"] == "fee" and summary["fee_charge_cents"] == summary["customer_paid_cents"] == 800
            and summary["pass_charge_cents"] == summary["customer_due_cents"] == summary["pass_cash_balance_cents"] == 0
            and case(e, key)["state"] == "completed" and not [t for t in rows(e, "flow_tasks", key) if t["status"] == "open"], "客户其它收入没有独立真实履约/到账终点或被伪作外部代办")
    await refresh(e, "service", key)
    cp.note(customer_other={"case_id": key, "quote": quote, "line": lines[0], "quote_api": quoted,
        "approval_authorization": authorized, "fulfillment": fulfilled, "collection": collection,
        "summary": summary, "refresh_business_unchanged": True, "complete": True})
    return key


async def income_create(e, context, credentials, fixture, source, vehicle, supplier, day, token):
    actor, current = await current_source(e, context, credentials, fixture, "finance", source["id"])
    await nav(e, "vehicle-income", "厂家及供应商整车其他收入", DOMAIN["income"])
    await e.click('#main [data-act="vehicle-income-new"]', "从本次已交付原VIN建立独立厂家收入")
    await expect(e.page.locator("#modal-title")).to_have_text("建立非客户整车收入")
    e.action("select", "明确本次原供应商", supplier_id=supplier["id"])
    await e.page.locator('#modal [name="supplier"]').select_option(str(supplier["id"]))
    await expect(e.page.locator('#modal [name="supplier"]')).to_have_value(str(supplier["id"]))
    source_selector = e.page.locator('#modal [data-income-source]')
    original_option = source_selector.locator("option").filter(has_text=current["number"] + " · " + vehicle["vin"])
    await expect(original_option).to_have_count(1)
    original_value = await original_option.get_attribute("value")
    require(original_value not in {None, ""}, "厂家原车来源候选没有原值")
    e.action("select", "明确同一原销售及原VIN", case_id=current["id"], vehicle_id=vehicle["id"])
    await source_selector.select_option(original_value)
    await expect(source_selector).to_have_value(original_value)
    external_reference = "SETTLE-" + token
    await e.fill('#modal [name="external_reference"]', external_reference, "填写本次独立厂家结算编号")
    await e.fill('#modal [name="due_date"]', day, "明确厂家应收期限")
    await e.fill('#modal [name="reason"]', "合成厂家原结算凭据，明确关联本次已交付原车辆；原销量不推断厂家收入", "填写厂家收入真实原依据")
    source_before = one(e, "flow_cases", current["id"])
    guard = Guard(e, "manufacturer_income_create", actor, fixture["store_id"],
        append=COMMON | {"flow_cases", "vehicle_income_orders", "vehicle_income_sources", "vehicle_income_receipts", "business_entity_case_contexts"}, new_kind="vehicle_income")
    body, view, meta, request = await original_submit(e, DOMAIN["income"], lambda p: bool(re.fullmatch(r"/api/vehicle-income/\d+", p)), guard, fixture["store_id"], status=201)
    key = body["id"]
    current_supplier = one(e, "master_suppliers", supplier["id"])
    require(request["supplier_id"] == current_supplier["id"] and request["supplier_version"] == current_supplier["version"]
            and request["external_reference"] == external_reference and request["sources"] == [{"source_case_id": current["id"], "source_version": current["version"], "vehicle_id": vehicle["id"]}]
            and case(e, key)["flow_version"] == 1 and case(e, key)["parent_id"] == current["id"]
            and case(e, key)["customer_id"] is None and view["supplier"]["id"] == supplier["id"], "厂家单原往来单位/当前车源/CAS不符")
    frozen_sources = rows(e, "vehicle_income_sources", key)
    require(len(frozen_sources) == len(view["sources"]) == 1, "厂家单没有唯一明确原车来源")
    frozen = frozen_sources[0]
    snapshot = json.loads(frozen["snapshot"])
    allocated = one(e, "flow_events", snapshot["allocation_event_id"])
    detail = json.loads(allocated["detail"])
    require(frozen["source_case_id"] == current["id"] and frozen["source_version"] == current["version"] and frozen["vehicle_id"] == vehicle["id"]
            and snapshot["case_id"] == current["id"] and snapshot["version"] == current["version"]
            and snapshot["vehicle_id"] == vehicle["id"] and snapshot["vin"] == vehicle["vin"]
            and frozen["digest"] == digest("vehicle_income_source", snapshot) and allocated["case_id"] == current["id"]
            and allocated["action"] == "allocate" and detail["vehicle_id"] == vehicle["id"]
            and one(e, "flow_cases", current["id"]) == source_before and not rows(e, "vehicle_income_cash", key), "厂家源快照缺原配车事实或建单制造现金/修改原销售")
    order = one(e, "vehicle_income_orders", key)
    require(order["supplier_id"] == supplier["id"] and order["primary_source_case_id"] == current["id"]
            and order["external_reference"] == external_reference and order["actor_id"] == actor["id"], "厂家原单业务身份不符")
    return key, {"native": meta, "source": frozen, "source_snapshot": snapshot, "allocation_event": allocated, "order": order}


async def income_propose(e, context, credentials, fixture, key, source_id, target, day, *, revision):
    actor, before, owner = await responsible(e, context, credentials, fixture, "income", key, "vehicle_income_propose", "finance", optional=revision > 1)
    proof = await upload(e, fixture, key, actor, "evidence", "income-propose", f"合成厂家第{revision}版原结算依据，目标{target}分，修订原目标但不覆盖原款。")
    await form(e, "income", "propose")
    await e.fill('#modal [name="amount"]', fen_text(target), "按本次原结算依据提出新目标")
    await select_value(e, '#modal [name="mode"]', "按对方原票或结算凭据办理", "明确本版对方开票依据")
    await e.fill('#modal [name="due_date"]', day, "明确本版原应收到期日期")
    reason = f"合成厂家第{revision}版结算凭据，独立确认目标{target}分；保留此前批准和实际收退款原事实"
    await e.fill('#modal [name="reason"]', reason, "记录本次有据修订原因")
    await proof_choice(e, proof)
    source_before = one(e, "flow_cases", source_id)
    view, native = await command(e, fixture, "income", key, actor, "propose", append={"vehicle_income_revisions"},
        expected={"target_cents": target, "invoice_mode": "external_document", "due_date": day, "reason": reason, "evidence_id": proof["file"]["id"]})
    facts = rows(e, "vehicle_income_revisions", key)
    require(len(facts) == revision and facts[-1]["revision"] == revision, "厂家目标版次不符")
    fact = facts[-1]
    previous = one(e, "vehicle_income_revisions", before["current_revision_id"]) if before["current_revision_id"] else None
    versions = {str(source_id): source_before["version"]}
    canonical = {"previous_id": previous["id"] if previous else None, "previous_cents": previous["target_cents"] if previous else 0,
        "target_cents": target, "invoice_mode": "external_document", "due_date": day, "source_versions": versions, "reason": reason, "evidence_id": proof["file"]["id"]}
    require(fact["previous_id"] == canonical["previous_id"] and fact["previous_cents"] == canonical["previous_cents"] and fact["target_cents"] == target
            and fact["invoice_mode"] == "external_document" and json.loads(fact["source_versions"]) == versions
            and fact["digest"] == digest("vehicle_income_revision", canonical) and fact["actor_id"] == actor["id"]
            and view["pending_revision_id"] == fact["id"] and view["current_revision_id"] == before["current_revision_id"]
            and view["totals"] == before["totals"] and view["state"] == "approval"
            and one(e, "flow_cases", source_id) == source_before, "厂家目标冻结/前版/源CAS错误或提案变成有效应收/现金")
    return fact, {"native": native, "proof": proof, "task_owner": owner, "pending_revision_id": view["pending_revision_id"]}


async def income_approve(e, context, credentials, fixture, key, revision):
    actor, before, owner = await responsible(e, context, credentials, fixture, "income", key, "vehicle_income_review", "manager")
    require(actor["id"] not in {revision["actor_id"], case(e, key)["created_by"]} and before["pending_revision_id"] == revision["id"], "厂家本版复核人或原待批版本不独立")
    proof = await upload(e, fixture, key, actor, "evidence", "income-approve", f"合成独立主管核对原厂家第{revision['revision']}版目标及原车辆来源。")
    await form(e, "income", "approve")
    await e.fill('#modal [name="reason"]', "独立核对厂家本版原结算凭据、车辆来源、目标与实际原款，批准本版", "主管填写本版真实核对结果")
    await proof_choice(e, proof)
    view, native = await command(e, fixture, "income", key, actor, "approve", append={"vehicle_income_decisions"}, expected={"revision_id": revision["id"], "evidence_id": proof["file"]["id"]})
    decisions = e.db.rows("SELECT * FROM vehicle_income_decisions WHERE revision_id=?", (revision["id"],))
    require(len(decisions) == 1 and decisions[0]["decision"] == "approved" and decisions[0]["actor_id"] == actor["id"]
            and view["current_revision_id"] == revision["id"] and view["pending_revision_id"] is None
            and view["totals"]["target_cents"] == revision["target_cents"], "厂家本版缺唯一独立批准或有效目标不符")
    return view, {"native": native, "proof": proof, "task_owner": owner, "decision": decisions[0]}


async def income_money(e, context, credentials, fixture, key, account, amount, day, *, original=None):
    action = "refund" if original else "receive"
    actor, before, owner = await responsible(e, context, credentials, fixture, "income", key, "vehicle_income_" + action, "finance")
    proof = await upload(e, fixture, key, actor, "receipt", "income-" + action, f"合成原厂家款本次实际{action} {amount}分，原账户{account['id']}，原款{original['id'] if original else None}。")
    await form(e, "income", action)
    await e.fill('#modal [name="amount"]', fen_text(amount), "明确本次实际厂家收退款金额")
    await account_choice(e, account)
    reference = "VI-" + uuid.uuid4().hex[:20]
    await e.fill('#modal [name="reference"]', reference, "填写本次独立真实流水编号")
    await e.fill('#modal [name="business_date"]', day, "填写本次实际原资金日期")
    await e.fill('#modal [name="reason"]', "本人实际核对本版厂家款及原账户，独立登记原收退款，不覆盖原款", "填写本次实际原资金依据")
    expected = {"amount_cents": amount, "account_id": account["id"], "reference": reference, "business_date": day, "evidence_id": proof["file"]["id"]}
    if original:
        option = e.page.locator('#modal [name="original"] option').filter(has_text=re.compile(r"^" + re.escape(str(original["id"])) + r" · "))
        await expect(option).to_have_count(1)
        original_value = await option.get_attribute("value")
        require(original_value and account["id"] == original["account_id"], "厂家退款没有本单同原账户实际款候选")
        e.action("select", "明确本单原实际到账用于退款", original_id=original["id"])
        await e.page.locator('#modal [name="original"]').select_option(original_value)
        await expect(e.page.locator('#modal [name="original"]')).to_have_value(original_value)
        expected["original_id"] = original["id"]
    await proof_choice(e, proof)
    old_payments = rows(e, "vehicle_income_cash", key)
    view, native = await command(e, fixture, "income", key, actor, action, account=account["id"],
        append={"vehicle_income_cash", "cash_entries", "business_entity_cash_contexts"}, expected=expected)
    payments = rows(e, "vehicle_income_cash", key)
    require(payments[:len(old_payments)] == old_payments and len(payments) == len(old_payments) + 1, "厂家原资金历史被覆盖或出现重复实际款")
    payment = payments[-1]
    cash = one(e, "cash_entries", payment["cash_id"])
    direction = "out" if original else "in"
    require(payment["revision_id"] == before["current_revision_id"] and payment["original_id"] == (original["id"] if original else None)
            and payment["direction"] == cash["direction"] == direction and payment["amount_cents"] == cash["amount_cents"] == amount
            and payment["account_id"] == account["id"] and json.loads(payment["account_snapshot"])["name"] == cash["account"] == account["name"]
            and payment["reference"] == cash["voucher_no"] == reference and payment["business_date"] == cash["business_date"] == day
            and payment["actor_id"] == cash["created_by"] == actor["id"] and cash["approval_state"] == "approved"
            and cash["category"] == "vehicle_other_income_" + direction, "厂家实际款原账户/日期/流水/批准版本或原款关联错误")
    return view, {"native": native, "proof": proof, "task_owner": owner, "payment": payment, "cash": cash}


async def manufacturer_path(e, context, credentials, fixture, cp, source, vehicle, supplier, account, day, token):
    key, created = await income_create(e, context, credentials, fixture, source, vehicle, supplier, day, token)
    cp.note(manufacturer_income_case_id=key, manufacturer_create=created)
    revision1, proposed1 = await income_propose(e, context, credentials, fixture, key, source["id"], 10000, day, revision=1)
    approved_view, approved1 = await income_approve(e, context, credentials, fixture, key, revision1)
    require(approved_view["totals"]["target_cents"] == approved_view["totals"]["receivable_cents"] == 10000
            and approved_view["totals"]["net_received_cents"] == approved_view["totals"]["refund_due_cents"] == 0
            and approved_view["state"] == "credit_open" and not rows(e, "vehicle_income_cash", key), "厂家独立批准被误作实际款或首版应收错误")
    collected_view, received = await income_money(e, context, credentials, fixture, key, account, 10000, day)
    require(collected_view["state"] == "completed" and collected_view["totals"]["net_received_cents"] == 10000
            and collected_view["totals"]["receivable_cents"] == 0, "厂家首版实际到账未结清")
    original_cash = dict(received["cash"])
    revision2, proposed2 = await income_propose(e, context, credentials, fixture, key, source["id"], 7000, day, revision=2)
    require(revision2["previous_id"] == revision1["id"] and revision2["previous_cents"] == 10000 and revision2["digest"] != revision1["digest"]
            and one(e, "vehicle_income_revisions", revision1["id"]) == revision1, "厂家减额未追加有据新版或覆盖原批准目标")
    refund_view, approved2 = await income_approve(e, context, credentials, fixture, key, revision2)
    require(refund_view["state"] == "refund_pending" and refund_view["totals"]["target_cents"] == 7000
            and refund_view["totals"]["net_received_cents"] == 10000 and refund_view["totals"]["refund_due_cents"] == 3000
            and len(rows(e, "vehicle_income_cash", key)) == 1 and one(e, "cash_entries", original_cash["id"]) == original_cash,
            "厂家减额批准缺独立超收事实或自动改变实际原款")
    view, refunded = await income_money(e, context, credentials, fixture, key, account, 3000, day, original=received["payment"])
    require(len(view["revisions"]) == len(view["payments"]) == 2 and all(r["decision"]["decision"] == "approved" for r in view["revisions"])
            and view["totals"] == {"target_cents": 7000, "received_cents": 10000, "refunded_cents": 3000,
                "net_received_cents": 7000, "receivable_cents": 0, "refund_due_cents": 0}
            and view["state"] == "completed" and not view["tasks"] and not [t for t in rows(e, "flow_tasks", key) if t["status"] == "open"]
            and one(e, "cash_entries", original_cash["id"]) == original_cash, "厂家两版目标和原款退款终点不完整")
    await expect(e.page.locator("#main")).to_contain_text("原到账 " + str(received["payment"]["id"]))
    await refresh(e, "income", key)
    await cp.passed(manufacturer={"case_id": key, "first_revision": revision1, "first_proposal": proposed1, "first_approval": approved1,
        "collection": received, "second_revision": revision2, "second_proposal": proposed2, "second_approval": approved2, "refund": refunded,
        "final_totals": view["totals"], "same_original_account": True, "original_cash_unchanged": True, "refresh_business_unchanged": True},
        both_customer_and_manufacturer_sources_complete=True,
        conditional=[{"check_id": "HK-017-additional-sources-and-cancellations", "status": "not_tested", "reason": "本次单一明确VIN和对方结算凭据；多车批次、门店开票、退回/撤回等原分支未本批执行"}])
    return key


async def sales_followon_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        cp.start("HK-012")
        fixture, source, customer, vehicle, item, warehouse, location, work, project, supplier, account = source_facts(e, cp)
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        token = uuid.uuid4().hex[:12].upper()
        addon_id = await addon_path(e, context, credentials, fixture, cp, source, vehicle, item, warehouse, location, work, account, day)
        agency_id = await agency_path(e, context, credentials, fixture, cp, source, customer, project, account, day, token)
        cp.start("HK-017")
        customer_other_id = await customer_other_path(e, context, credentials, fixture, cp, source, customer, account, day, token)
        manufacturer_id = await manufacturer_path(e, context, credentials, fixture, cp, source, vehicle, supplier, account, day, token)
        cp.finish({"delivered_order_id": source["id"], "customer_id": customer["id"], "vehicle_id": vehicle["id"],
            "addon_case_id": addon_id, "agency_case_id": agency_id, "customer_other_case_id": customer_other_id,
            "manufacturer_income_case_id": manufacturer_id, "material_item_id": item["id"], "material_warehouse_id": warehouse["id"],
            "material_location_id": location["id"], "work_item_id": work["id"], "agency_project_id": project["id"],
            "supplier_id": supplier["id"], "account_id": account["id"]})
    except Exception as error:
        cp.failed(error)
        raise


SALES_FOLLOWON_SCENARIOS = ((SCENARIO, sales_followon_business, 600),)
