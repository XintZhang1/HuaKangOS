"""This run's original appointment, repair, material, cash and departure UI.

No app imports, API business writes, seeded repair results or mutable UI state.
Only passed fixed checkpoints and Evidence's read-only database supply sources.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import require, login_as, employee_choice
from sales_order_business import fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import select_value, checkbox, live_choice


SCENARIO = "repair-selfpay-hk031-034-044-049-053-079"
CUSTOMER = "customer-service-hk098-107-108-109"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
CONTRACTS = (
    ("HK-031", "维修预约", ["原客户车辆预约及改约，实际到店核VIN/里程/原凭据", "预约、ArrivalFact和唯一转换维修各有原任务事件，错误VIN拒绝且零业务修改"]),
    ("HK-034", "一般维修", ["本版报价、独立核价、客户授权、实际施工和质检分别产生事实", "真实承担/净材料成本/现金与原接车及工位释放一致"]),
    ("HK-044", "维修工单提醒", ["本人今日非空原维修任务与API/DB期限身份一致", "实际点击提醒进入同原维修，不冒充外发或完工"]),
    ("HK-049", "维修退料入库", ["从本次实际领料原批退250千分量到原真实位置", "原数量/成本恢复，旧领料不覆盖，不能越批次"]),
    ("HK-053", "维修领料出库", ["当前授权行原位置准备后实领1250，再按剩余补领250", "净领1250、RepairStock/StockMove/Allocation/Entry数量成本准确，准备不减库存"]),
    ("HK-079", "维修收款", ["当前真实客户承担原到账与RepairPayment/PaymentLink/Cash唯一对应", "接车不是收款，刷新不重复现金，旧原款不删除"]),
)
INTAKE = "/api/service-intake"
REPAIR = "/api/repair-orders"
TITLES = {"quote": "维修报价与授权增项", "price_approve": "主管价格授权", "authorize": "记录客户当前版本授权",
          "start": "确认实际开工", "issue": "按授权配件发料", "return_material": "原领料退回",
          "finish": "提交施工结果", "quality": "检查维修质量", "allocate": "确认费用承担",
          "receive": "登记实际到账", "release": "确认客户接车"}
CASE_FIELDS = {"state", "data", "version", "updated_at", "completed_date", "amount_cents", "cost_cents", "revenue_cents"}
TASK_FIELDS = {"status", "assignee_id", "due_date", "done_by", "done_at", "version", "updated_at"}
COMMON = {"flow_events", "flow_request_receipts", "audit_logs"}
PRIMARY_KEYS = {name: "id" for name in (
    "flow_cases", "flow_tasks", "flow_events", "flow_request_receipts", "audit_logs", "flow_items", "flow_accounts",
    "flow_files", "file_scan_events", "cash_entries", "flow_payment_links", "flow_stock_moves", "care_customer_vehicles",
    "intake_resources", "intake_appointments", "intake_arrivals", "intake_resource_uses", "intake_command_receipts",
    "repair_quotes", "repair_lines", "repair_price_approvals", "repair_authorizations", "repair_stock", "repair_quality",
    "repair_settlements", "repair_allocations", "repair_payments", "warehouse_allocations", "warehouse_allocation_lines",
    "warehouse_balances", "warehouse_entries", "membership_points_claims")}
PRIMARY_KEYS.update(file_security="file_id", intake_repair_contexts="case_id", intake_vehicle_bindings="case_id",
                    business_entity_case_contexts="case_id")


class Guard:
    """Finite original repair IDs and columns; every other old row stays equal."""
    def __init__(self, e, label, actor, store_id, *, append=(), update=None, cases=(), item_ids=(), vehicle_id=None,
                 resource_id=None, new_kind=None):
        self.e, self.label, self.actor, self.store_id = e, label, actor, store_id
        self.append, self.update = set(append), update or {}
        self.cases, self.items = set(cases), set(item_ids)
        self.vehicle, self.resource, self.new_kind = vehicle_id, resource_id, new_kind
        require((self.append | self.update.keys()) <= PRIMARY_KEYS.keys(), "维修守卫表未核准")
        self.snapshot = e.business_snapshot("before_" + label)
        self.old = {t: self.rows(t) for t in self.append | self.update.keys()}

    def rows(self, table):
        return self.e.db.rows(f"SELECT * FROM {table} ORDER BY {PRIMARY_KEYS[table]}")

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.snapshot["tables"].keys() | after["tables"].keys()
                   if self.snapshot["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "维修确认改动了无关原表：" + str(sorted(changed)))
        new_cases = set()
        if "flow_cases" in self.append:
            old_ids = {r["id"] for r in self.old["flow_cases"]}
            new = [r for r in self.rows("flow_cases") if r["id"] not in old_ids]
            require(len(new) == 1 and new[0]["kind"] == self.new_kind and new[0]["created_by"] == self.actor["id"], "维修动作创建了非唯一或错误类型原单")
            new_cases = {new[0]["id"]}
        owned = self.cases | new_cases
        added, updated = {}, {}
        for table, old_rows in self.old.items():
            pk = PRIMARY_KEYS[table]
            current = {r[pk]: r for r in self.rows(table)}
            old_ids = {r[pk] for r in old_rows}
            updated[table] = []
            for old in old_rows:
                require(old[pk] in current, "维修动作删除了原事实：" + table)
                columns = {k for k in old if old[k] != current[old[pk]][k]}
                require(columns <= self.update.get(table, {}).get(old[pk], set()),
                        "维修动作覆盖了未授权原行/列：" + table + "/" + str(old[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": old[pk], "columns": sorted(columns)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(not new or table in self.append, "维修只允许更新的表出现新增行：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store_id, "维修新增事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "维修新增事实串原单：" + table)
                for column in ("actor_id", "created_by"):
                    if column in row:
                        require(row[column] == self.actor["id"], "维修新增事实串办理人：" + table)
                if row.get("item_id") is not None:
                    require(row["item_id"] in self.items, "维修新增事实串物资：" + table)
                if "customer_vehicle_id" in row:
                    require(row["customer_vehicle_id"] == self.vehicle, "维修新增事实串客户车辆：" + table)
                if "resource_id" in row:
                    require(row["resource_id"] == self.resource, "维修新增事实串工位：" + table)
                if "quote_id" in row:
                    require(one(self.e, "repair_quotes", row["quote_id"])["case_id"] in owned, "维修新增事实串报价：" + table)
                if table in {"file_security", "file_scan_events"}:
                    require(one(self.e, "flow_files", row["file_id"])["case_id"] in owned, "维修检查记录串附件")
                if table == "warehouse_allocation_lines":
                    allocation = one(self.e, "warehouse_allocations", row["allocation_id"])
                    require(allocation["case_id"] in owned and allocation["item_id"] in self.items, "维修库位准备串原来源")
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", row["balance_id"])["item_id"] in self.items, "维修位置流水串物资")
                if table == "repair_payments":
                    require(one(self.e, "repair_allocations", row["allocation_id"])["case_id"] in owned, "维修到账串承担")
                if table == "cash_entries":
                    links = self.e.db.rows("SELECT * FROM flow_payment_links WHERE cash_id=?", (row["id"],))
                    require(len(links) == 1 and links[0]["case_id"] in owned, "维修现金缺同原单唯一流水来源")
                if table == "membership_points_claims":
                    require(row["member_id"] is None and row["rule_id"] is None and row["basis_cents"] == row["target_units"] == 0,
                            "本次非会员客户意外产生了会员奖励来源")
            added[table] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": added, "updated_columns": updated,
                  "unrelated_tables_unchanged": True, "protected_old_rows_and_other_stores": True}
        self.e.observe("repair_original_row_guard", {"label": self.label, **result})
        return result


def mutable(e, case_id, *, item_ids=(), physical=False, allocations=False, resource_id=None, vehicle_id=None, account_id=None):
    update = {"flow_cases": {case_id: CASE_FIELDS}, "flow_tasks": {r["id"]: TASK_FIELDS
        for r in e.db.rows("SELECT * FROM flow_tasks WHERE case_id=?", (case_id,))}}
    if physical:
        update["flow_items"] = {key: {"quantity_milli", "inventory_value_cents", "unit_cost_cents", "version", "updated_at"} for key in item_ids}
        update["warehouse_balances"] = {r["id"]: {"quantity_milli", "value_cents", "version", "updated_at"}
            for key in item_ids for r in e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=?", (key,))}
    if allocations:
        update["warehouse_allocations"] = {r["id"]: {"status", "stock_move_id", "version", "updated_at"}
            for r in e.db.rows("SELECT * FROM warehouse_allocations WHERE case_id=?", (case_id,))}
    if resource_id is not None:
        update["intake_resources"] = {resource_id: {"active_case_id", "version", "updated_at"}}
    if vehicle_id is not None:
        update["care_customer_vehicles"] = {vehicle_id: {"version", "updated_at"}}
    if account_id is not None:
        update["flow_accounts"] = {account_id: {"version", "updated_at"}}
    return update


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        bindings = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, _, _ in CONTRACTS:
            require(bindings[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in bindings[key]["acceptance_checks"]), "维修目录未核准：" + key)
        self.path = e.directory / "business-checkpoint.json"
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in CONTRACTS],
            "complete": False, "passed": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "execution": "native_browser_original_forms", "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_money_and_physical_inputs": True, "file_scan": "original_structure_only_not_clamav",
                "production_bank_or_physical_acceptance": False, "business_entity_policy_acceptance": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": criteria, "evidence": {}}], "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "conditional_checks": []} for key, title, criteria in CONTRACTS]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.save()

    def note(self, evidence):
        merged = {**self.active["acceptance_checks"][0]["evidence"], **evidence}
        json.dumps(merged, ensure_ascii=False)
        self.active["acceptance_checks"][0]["evidence"] = merged
        self.save()

    async def passed(self, evidence, conditional=()):
        self.note(evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["conditional_checks"] = list(conditional)
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
            self.report["failed_requirement"] = self.active["id"]
        for row in self.report["requirements"]:
            if row["status"] == "running":
                row["status"] = row["acceptance_checks"][0]["status"] = "partial"
                row["acceptance_checks"][0]["incomplete_reason"] = "原前序已有事实，后继未完成；停止后不保留running"
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "维修六项未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=6, passed_requirements=6, report_sources=sources)
        self.save()
        self.e.observe("repair_original_business_checkpoint", {"path": str(self.path), "report_sources": sources, "business_accepted": False})


def one(e, table, key):
    rows = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (key,))
    require(len(rows) == 1, "有限原ID不存在或不唯一：" + table)
    return rows[0]


def case_facts(e, case_id):
    row = one(e, "flow_cases", case_id)
    row["data"] = json.loads(row["data"])
    tasks = e.db.rows("SELECT * FROM flow_tasks WHERE case_id=? ORDER BY id", (case_id,))
    events = e.db.rows("SELECT * FROM flow_events WHERE case_id=? ORDER BY id", (case_id,))
    for event in events:
        event["detail"] = json.loads(event["detail"])
    return {"case": row, "tasks": tasks, "events": events}


def facts(e, case_id):
    f = case_facts(e, case_id)
    for key, table in (("quotes", "repair_quotes"), ("stock", "repair_stock"), ("quality", "repair_quality"),
                       ("settlements", "repair_settlements"), ("allocations", "repair_allocations"),
                       ("moves", "flow_stock_moves"), ("payments", "flow_payment_links")):
        f[key] = e.db.rows(f"SELECT * FROM {table} WHERE case_id=? ORDER BY id", (case_id,))
    for key, table in (("lines", "repair_lines"), ("approvals", "repair_price_approvals"), ("authorizations", "repair_authorizations")):
        f[key] = e.db.rows(f"SELECT t.* FROM {table} t JOIN repair_quotes q ON q.id=t.quote_id WHERE q.case_id=? ORDER BY t.id", (case_id,))
    f["repair_payments"] = e.db.rows("SELECT p.* FROM repair_payments p JOIN repair_allocations a ON a.id=p.allocation_id WHERE a.case_id=? ORDER BY p.id", (case_id,))
    f["cash"] = [one(e, "cash_entries", p["cash_id"]) for p in f["payments"]]
    f["context"] = e.db.rows("SELECT * FROM intake_repair_contexts WHERE case_id=?", (case_id,))
    f["binding"] = e.db.rows("SELECT * FROM intake_vehicle_bindings WHERE case_id=?", (case_id,))
    f["resource_uses"] = e.db.rows("SELECT * FROM intake_resource_uses WHERE case_id=? ORDER BY id", (case_id,))
    return f


def task(f, key, status="open"):
    rows = [t for t in f["tasks"] if t["key"] == key and t["status"] == status]
    require(len(rows) == 1, "维修原任务不唯一或状态错误：" + key)
    return rows[0]


def event_added(before, after, action, actor):
    require(after["events"][:len(before["events"])] == before["events"], "原维修事件被覆盖")
    events = [r for r in after["events"][len(before["events"]):] if r["action"] == action]
    require(len(events) == 1 and events[0]["actor_id"] == actor["id"]
            and events[0]["case_id"] == before["case"]["id"] and events[0]["store_id"] == before["case"]["store_id"], "原维修动作事件串单/身份或次数错误")
    return events[0]


def source_facts(e, checkpoint):
    require(e.manifest.get("synthetic_data_only") is True, "维修只允许本次外置合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "维修数据库不是同次外置runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance.get("snapshot_stable") is True, "本次维修源码镜像未完整冻结")
    for name in ("repair_business.py", "business_acceptance_catalog.json", "customer_service_business.py", "master_data_business.py",
                 "material_business.py", "sales_business.py", "sales_order_business.py", "vehicle_purchase_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "维修同次脚本指纹变化：" + name)
    checkpoint.report["mirror"] = {"sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": provenance["source_sha256"],
                                   "script_sha256": provenance["script_sha256"]}
    fixture = dict(e.manifest["business_fixtures"]["repair"])
    for role in ("service", "manager", "inventory", "finance", "technician"):
        require(e.manifest["users"][fixture[role + "_key"]]["role"] == role, "维修缺本人原岗位：" + role)
    care = fixed_dependency(e, checkpoint, CUSTOMER)
    master = fixed_dependency(e, checkpoint, MASTER)
    material = fixed_dependency(e, checkpoint, MATERIAL)
    partial = next((r for r in care["partial_requirements"] if r["id"] == "HK-099"), None)
    require(partial is not None and partial["local_scope_status"] == "local_scope_passed", "当前客服HK099本店车辆来源未通过")
    given = partial["evidence"]
    vehicle = one(e, "care_customer_vehicles", given["vehicle"]["id"])
    customer = one(e, "flow_customers", vehicle["customer_id"])
    for k in ("id", "store_id", "customer_id", "vin", "customer_identity_id", "vehicle_identity_id"):
        require(vehicle[k] == given["vehicle"][k], "原客户车辆身份已变化：" + k)
    require(vehicle["active"] and vehicle["store_id"] == customer["store_id"] == fixture["store_id"]
            and given["observations"] and given["original_consultation_history"] != "pending", "原客户车辆/原观察/咨询来源不完整")
    require(not e.db.rows("SELECT m.id FROM group_members m JOIN group_identity_links l ON l.identity_id=m.identity_id "
        "WHERE l.local_kind='customer' AND l.local_id=? AND l.store_id=? AND m.active=1", (customer["id"], fixture["store_id"])),
        "本批普通自费客户存在另需验收的会员奖励来源")
    for supplied in given["observations"]:
        require(one(e, "care_vehicle_observations", supplied["observation"]["id"]) == supplied["observation"], "原客户车辆观察被覆盖")
    require(one(e, "care_history_links", given["original_consultation_history"]["original_link"]["id"])
            == given["original_consultation_history"]["original_link"], "原咨询与车辆历史关联被覆盖")
    work_given = checkpoint_evidence(master, "HK-175")["row"]
    work = one(e, "master_work_items", work_given["id"])
    require(work["active"] and all(work[k] == work_given[k] for k in ("code", "name", "version", "billing_unit", "standard_fee_cents")), "本轮作业来源变更或未启用")
    primary = material["material_sources"]["primary"]
    item = one(e, "flow_items", primary["item_id"])
    require(item["id"] == checkpoint_evidence(master, "HK-183")["item"]["id"]
            and item["active"] and item["store_id"] == primary["store_id"] == fixture["store_id"]
            and item["sku"] == primary["sku"] and item["unit"] == primary["unit"] == "升", "同次真实材料来源错误")
    enrollment = one(e, "warehouse_enrollments", primary["enrollment_id"])
    location = one(e, "master_locations", primary["source_location_id"])
    warehouse = one(e, "master_warehouses", primary["warehouse_id"])
    require(enrollment["item_id"] == item["id"] and location["id"] in primary["location_ids"]
            and location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials"
            and location["active"] and warehouse["active"] and location["store_id"] == warehouse["store_id"] == fixture["store_id"], "材料未真正启用或指定原位置错误")
    balances = e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=? ORDER BY id", (item["id"],))
    balance = next((b for b in balances if b["location_id"] == location["id"]), None)
    require(balance and balance["quantity_milli"] >= 1250 and item["quantity_milli"] >= 1250
            and item["inventory_value_cents"] > 0 and sum(b["quantity_milli"] for b in balances) == item["quantity_milli"], "当前真实材料或指定原位可用量不足")
    receipts = [one(e, "procurement_receipts", key) for key in primary["receipt_ids"]]
    moves = [one(e, "flow_stock_moves", key) for key in primary["stock_move_ids"]]
    require(receipts and moves and all(r["case_id"] == primary["purchase_order_id"] for r in receipts)
            and any(m["item_id"] == item["id"] and m["quantity_milli"] > 0 and m["case_id"] == primary["purchase_order_id"] for m in moves), "材料正余额缺本轮原采购验收来源")
    checkpoint.report["source_preconditions"] = {"customer_vehicle": vehicle, "customer_id": customer["id"], "work_item": work,
        "material_source": primary, "current_item": item, "current_source_balance": balance,
        "synthetic_declared_inputs": {"part_price_cents": 8020, "part_quantity_milli": 1250, "labor_cost_cents": 1234, "arrival_odometer_km": 32100}}
    checkpoint.save()
    return fixture, vehicle, customer, work, item, warehouse, location


async def metadata(e, response, store_id, *, multipart=False):
    headers = await response.request.all_headers()
    endpoint, origin = urlsplit(response.url), urlsplit(e.manifest["origin"])
    require((endpoint.scheme, endpoint.netloc) == (origin.scheme, origin.netloc) and headers.get("cookie")
            and headers.get("x-csrf-token") and headers.get("x-store-id") == str(store_id), "原维修请求缺本店同源Cookie/CSRF")
    request = None if multipart else response.request.post_data_json
    if request and request.get("request_id"):
        require(isinstance(request["request_id"], str) and len(request["request_id"]) >= 16, "原维修请求编号不完整")
    result = {"path": urlsplit(response.url).path, "method": response.request.method, "status": response.status,
        "native_ui": True, "cookie_present": True, "csrf_present": True, "submitted_version": request.get("version") if request else None,
        "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request and request.get("request_id") else None}
    e.observe("original_repair_response", result)
    return result, request


async def submit(e, path, render_path, store_id, status=200, *, multipart=False, protection):
    def rendered(r):
        p = urlsplit(r.url).path
        return r.request.method == "GET" and (p == render_path if not render_path.endswith("/*") else p.startswith(render_path[:-1]) and p.rsplit("/", 1)[-1].isdigit())
    async with e.page.expect_response(rendered) as ready:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "员工确认原维修事实")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原维修提交HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await ready.value
    view = await read.json()
    require(read.status == 200, "原维修成功后页面读取失败")
    meta, request = await metadata(e, response, store_id, multipart=multipart)
    meta.update(render_get_path=urlsplit(read.url).path, render_get_status=read.status, source_guard=protection.finish())
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return body, view, meta, request


async def read_as(e, context, credentials, fixture, role, route, path):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, fixture["store_id"])
    response = await pending.value
    view = await response.json()
    require(response.status == 200, "原岗位未实际读到同维修单")
    await expect(e.page.locator("#main h1")).to_have_text(view["title"])
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    if role in ("inventory", "technician"):
        require("amount_cents" not in view and "cost_cents" not in view and "allocations" in view and not view["allocations"], "原施工/库管页面泄漏钱款")
    return actor, view


async def responsible(e, context, credentials, fixture, case_id, key, role, *, appointment_id=None):
    original = task(case_facts(e, case_id), key)
    selected = e.manifest["users"][fixture[role + "_key"]]
    meta = {"task_id": original["id"], "task_key": key, "assignee_id": selected["id"], "handoff_needed": original["assignee_id"] != selected["id"]}
    if meta["handoff_needed"]:
        await login_as(e, context, credentials, fixture["manager_key"], f"case/{case_id}", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text(case_facts(e, case_id)["case"]["title"])
        await e.click(f'#main [data-act="assign"][data-id="{original["id"]}"]', "主管明确交接本店原维修任务")
        await employee_choice(e, selected)
        await e.fill('#modal [name="reason"]', "合成本店维修明确由所选原岗位员工本人经办", "填写原任务交接原因")
        protection = Guard(e, "repair_original_task_handoff", e.manifest["users"][fixture["manager_key"]], fixture["store_id"],
            append={"flow_events", "audit_logs"}, update={"flow_tasks": {original["id"]: TASK_FIELDS},
                "flow_cases": {case_id: {"updated_at", "version"}}}, cases={case_id})
        _, _, native, request = await submit(e, f'/api/flow/tasks/{original["id"]}/assign', f"/api/flow/cases/{case_id}", fixture["store_id"], protection=protection)
        require(request["version"] == original["version"] and request["assignee_id"] == selected["id"], "原维修交接缺真实员工/版本")
        after = task(case_facts(e, case_id), key)
        require(after["assignee_id"] == selected["id"] and after["version"] > original["version"], "原任务交接未生效")
        meta["native"] = native
    if appointment_id is not None:
        actor, view = await read_as(e, context, credentials, fixture, role, f"service-intake/appointments/{appointment_id}", f"{INTAKE}/appointments/{appointment_id}")
    else:
        actor, view = await read_as(e, context, credentials, fixture, role, f"repair-orders/{case_id}", f"{REPAIR}/{case_id}")
    require(task(case_facts(e, case_id), key)["assignee_id"] == actor["id"], "原维修未由真实任务本人办理")
    return actor, view, meta


async def upload(e, case_id, actor, category, name, text, store_id):
    folder = e.directory / "synthetic-inputs"
    folder.mkdir(exist_ok=True)
    path = folder / name
    content = ("合成维修点击材料，不代表真实客户现场、授权或到账。\n" + text + "\n").encode("utf-8")
    path.write_bytes(content)
    await e.click('#main [data-act="upload"]', "原员工选择本次合成维修凭据")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "选择本次原附件类别")
    e.action("select_file", "员工选择合成外置文件", filename=name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal input[name="file"]').set_input_files(str(path))
    protection = Guard(e, "repair_actual_file_upload", actor, store_id,
        append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={case_id})
    body, view, meta, _ = await submit(e, f"/api/flow/cases/{case_id}/files", f"/api/flow/cases/{case_id}", store_id, multipart=True, protection=protection)
    row = one(e, "flow_files", body["id"])
    require(row["case_id"] == case_id and row["store_id"] == store_id and row["category"] == category and row["created_by"] == actor["id"]
            and not row["generated"] and row["sha256"] == hashlib.sha256(content).hexdigest() and row["size"] == len(content), "原维修附件来源不匹配")
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (row["id"],))
    security = e.db.rows("SELECT * FROM file_security WHERE file_id=?", (row["id"],))
    shown = next((f for f in view["files"] if f["id"] == row["id"]), None)
    require(len(scans) == 1 and len(security) == 1 and scans[0]["state"] == security[0]["state"] == "structure_only"
            and shown and shown["security"]["can_use"], "本次合成附件未通过原结构检查")
    await expect(e.page.locator("#main .filerecord").filter(has_text=name)).to_contain_text(shown["security"]["label"])
    stored = row.pop("content")
    require(isinstance(stored, bytes) and len(stored) == row["size"] == len(content)
            and hashlib.sha256(stored).hexdigest() == row["sha256"], "原维修附件实际字节与员工所选文件不匹配")
    return {"file": row, "stored_blob": {"length": len(stored), "sha256": hashlib.sha256(stored).hexdigest()},
            "scan": scans[0], "native": meta, "clamav_acceptance": False}


async def file_choice(e, name, evidence):
    row = evidence["file"]
    await live_choice(e, name, row["name"], row["name"] + " · " + {"evidence": "业务凭据", "authorization": "客户授权", "inspection": "检测记录"}[row["category"]], expected_value=row["id"])


async def form(e, action, *, intake=False):
    selector = f'#main [data-act="{"intake-action" if intake else "repair-action"}"][data-key="{action}"]'
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "原员工办理 " + action)
    await expect(e.page.locator("#modal form")).to_be_visible()
    if not intake:
        await expect(e.page.locator("#modal-title")).to_have_text(TITLES[action])


async def command(e, fixture, case_id, action, actor):
    before = facts(e, case_id)
    item_ids = {r["item_id"] for r in before["lines"] if r["item_id"] is not None}
    if action == "quote":
        selects = e.page.locator('#modal [data-repair-line] [name="source"]')
        values = [await selects.nth(i).input_value() for i in range(await selects.count())]
        item_ids = {int(value.split(":")[1]) for value in values if value.startswith("part:")}
    appended = COMMON | {"flow_tasks"} | {
        "quote": {"repair_quotes", "repair_lines"}, "price_approve": {"repair_price_approvals"},
        "authorize": {"repair_authorizations", "membership_points_claims"}, "start": {"intake_resource_uses"},
        "issue": {"repair_stock", "flow_stock_moves", "warehouse_entries"},
        "return_material": {"repair_stock", "flow_stock_moves", "warehouse_entries"}, "finish": set(),
        "quality": {"repair_quality"}, "allocate": {"repair_settlements", "repair_allocations"},
        "receive": {"repair_payments", "flow_payment_links", "cash_entries"}, "release": {"intake_resource_uses"}}[action]
    ctx, binding = before["context"][0], before["binding"][0]
    account_id = int(await e.page.locator('#modal [name="account_id"]').input_value()) if action == "receive" else None
    protection = Guard(e, "repair_original_" + action, actor, fixture["store_id"], append=appended,
        update=mutable(e, case_id, item_ids=item_ids, physical=action in {"issue", "return_material"},
            allocations=action in {"issue", "return_material"}, resource_id=ctx["resource_id"] if action in {"start", "release"} else None,
            vehicle_id=binding["customer_vehicle_id"] if action in {"start", "release"} else None, account_id=account_id),
        cases={case_id}, item_ids=item_ids, vehicle_id=binding["customer_vehicle_id"], resource_id=ctx["resource_id"])
    body, view, meta, request = await submit(e, f"{REPAIR}/{case_id}/actions/{action}", f"{REPAIR}/{case_id}", fixture["store_id"], protection=protection)
    after = facts(e, case_id)
    require(body["id"] == view["id"] == case_id and request["version"] == before["case"]["version"]
            and after["case"]["version"] == body["version"] > before["case"]["version"], "原维修版本或同单读取错误")
    for k in ("id", "number", "kind", "flow_version", "store_id", "customer_id", "created_by"):
        require(before["case"][k] == after["case"][k], "原维修身份被替换：" + k)
    for k in ("quotes", "lines", "approvals", "authorizations", "stock", "quality", "settlements", "allocations", "payments", "repair_payments", "moves"):
        require(after[k][:len(before[k])] == before[k], "维修原历史被覆盖：" + k)
    event = event_added(before, after, "repair_v4_" + action, actor)
    require(event["before_state"] == before["case"]["state"] and event["after_state"] == after["case"]["state"], "原维修事件前后状态错误")
    await expect(e.page.locator("#main h1")).to_have_text(after["case"]["title"])
    return after, view, {"native": meta, "event": event, "submitted_values": request["values"]}


def material_facts(e, item_id):
    return {"item": one(e, "flow_items", item_id),
        "balances": e.db.rows("SELECT * FROM warehouse_balances WHERE item_id=? ORDER BY id", (item_id,)),
        "moves": e.db.rows("SELECT * FROM flow_stock_moves WHERE item_id=? ORDER BY id", (item_id,)),
        "entries": e.db.rows("SELECT t.* FROM warehouse_entries t JOIN warehouse_balances b ON b.id=t.balance_id WHERE b.item_id=? ORDER BY t.id", (item_id,))}


async def prepare_bin(e, fixture, case_id, item, warehouse, location, quantity, purpose):
    before = material_facts(e, item["id"])
    await e.click('#modal [data-prep-open]', "按本次数量明确分配真实材料库位")
    section = e.page.locator(f'#modal [data-prep-item="{item["id"]}"]')
    await expect(section).to_be_visible()
    await expect(section.locator("[data-prep-location]")).to_have_count(1)
    query = section.locator('.lookup [role="combobox"]')
    e.action("fill", "查找本轮明确领退料位置", value=location["name"])
    await query.fill(location["name"])
    option = section.get_by_role("option", name=warehouse["name"] + " · " + location["name"], exact=True)
    await expect(option).to_be_visible()
    e.action("click", "明确选择本次真实材料位置", location_id=location["id"])
    await option.click()
    await expect(section.locator("[data-prep-bin]")).to_have_value(str(location["id"]))
    await e.fill(f'#modal [data-prep-item="{item["id"]}"] [data-prep-quantity]', f"{quantity // 1000}.{quantity % 1000:03}", "填写本原位精确数量")
    original_version = facts(e, case_id)["case"]["version"]
    protection = Guard(e, "repair_prepare_actual_bin", e.manifest["users"][fixture["inventory_key"]], fixture["store_id"],
        append=COMMON | {"warehouse_allocations", "warehouse_allocation_lines"},
        update=mutable(e, case_id, allocations=True), cases={case_id}, item_ids={item["id"]})
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"/api/warehouse/allocations/{case_id}") as pending:
        await e.click('#modal [data-prep-save]', "保存位置准备后再确认实际领退料")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["prepared"] and body["case_id"] == case_id, "原维修库位准备失败")
    meta, request = await metadata(e, response, fixture["store_id"])
    meta["source_guard"] = protection.finish()
    signed = quantity if purpose == "repair_return_v3" else -quantity
    require(request["version"] == original_version and request["values"] == {"item_id": item["id"], "quantity_milli": signed,
        "purpose": purpose, "locations": [{"location_id": location["id"], "quantity_milli": quantity}]}, "原库位准备数量/位置/方向错误")
    await expect(e.page.locator('#modal [data-prep-status]')).to_have_text("库位已保存。核对本表后，再确认实际收发。")
    require(before == material_facts(e, item["id"]), "准备库位错误地产生实际库存变化")
    allocations = e.db.rows("SELECT * FROM warehouse_allocations WHERE case_id=? AND item_id=? AND purpose=? AND status='prepared'", (case_id, item["id"], purpose))
    require(len(allocations) == 1 and allocations[0]["quantity_milli"] == signed, "本次原位置准备不唯一")
    lines = e.db.rows("SELECT * FROM warehouse_allocation_lines WHERE allocation_id=?", (allocations[0]["id"],))
    require(len(lines) == 1 and lines[0]["location_id"] == location["id"] and lines[0]["quantity_milli"] == quantity, "位置准备行不匹配")
    return {"native": meta, "allocation": allocations[0], "line": lines[0], "physical_unchanged": True}


async def stock_action(e, fixture, case_id, action, actor, item, warehouse, location, quantity, *, original=None, filename=None):
    evidence = await upload(e, case_id, actor, "evidence", filename,
        f"本次原维修{case_id} {action} 数量{quantity}千分量，指定位置{location['id']}，独立合成现场凭据。", fixture["store_id"])
    before = facts(e, case_id)
    stock_before = material_facts(e, item["id"])
    await form(e, action)
    line = next(r for r in before["lines"] if r["kind"] == "part")
    if action == "issue":
        issued = sum(r["quantity_milli"] for r in before["stock"] if r["line_key"] == line["line_key"])
        label = f'{line["code"]} · {line["name"]} · 尚可领 {(line["quantity_milli"] - issued) / 1000:g}'
        await live_choice(e, "line_label", line["name"], label, expected_value=label)
    else:
        require(original is not None and original["original_id"] is None, "退料必须引用本次原领料")
        root = e.page.locator('#modal .lookup').filter(has=e.page.locator('select[name="original_id"]'))
        e.action("fill", "查找明确原领料批次", value=line["name"])
        await root.locator('[role="combobox"]').fill(line["name"])
        option = root.get_by_role("option").filter(has_text=re.compile(r"领料 " + str(original["id"]) + r"$"))
        await expect(option).to_have_count(1)
        await expect(option).to_be_visible()
        e.action("click", "选择实际原领料批次", repair_stock_id=original["id"])
        await option.click()
        await expect(root.locator('select[name="original_id"]')).to_have_value(str(original["id"]))
    await e.fill('#modal [name="quantity"]', f"{quantity // 1000}.{quantity % 1000:03}", "确认本次原领退数量")
    await file_choice(e, "evidence_id", evidence)
    prepared = await prepare_bin(e, fixture, case_id, item, warehouse, location, quantity,
                                 "repair_issue_v3" if action == "issue" else "repair_return_v3")
    after, view, native = await command(e, fixture, case_id, action, actor)
    current = material_facts(e, item["id"])
    require(len(after["stock"]) == len(before["stock"]) + 1 and len(after["moves"]) == len(before["moves"]) + 1, "一次领退料不是一条原事实")
    fact, move = after["stock"][-1], after["moves"][-1]
    if action == "issue":
        qty, value = stock_before["item"]["quantity_milli"], stock_before["item"]["inventory_value_cents"]
        amount = value if quantity == qty else (2 * value * quantity + qty) // (2 * qty)
        sign = -1
        require(fact["original_id"] is None and fact["quantity_milli"] == quantity and fact["value_cents"] == amount
                and move["original_id"] is None, "原领料数量/平均实际成本错误")
    else:
        returns = [r for r in before["stock"] if r["original_id"] == original["id"]]
        remaining = original["quantity_milli"] + sum(r["quantity_milli"] for r in returns)
        value = original["value_cents"] + sum(r["value_cents"] for r in returns)
        amount = value if quantity == remaining else (2 * value * quantity + remaining) // (2 * remaining)
        sign = 1
        require(quantity <= remaining and fact["original_id"] == original["id"] and fact["quantity_milli"] == -quantity
                and fact["value_cents"] == -amount and move["original_id"] == original["stock_move_id"], "原退料越批次或未恢复原数量/成本")
    require(move["actor_id"] == actor["id"] and move["item_id"] == item["id"] and move["quantity_milli"] == sign * quantity
            and move["value_cents"] == sign * amount and move["purpose"] == prepared["allocation"]["purpose"]
            and fact["stock_move_id"] == move["id"] and fact["line_key"] == line["line_key"] and fact["evidence_id"] == evidence["file"]["id"], "维修领退与原StockMove不一致")
    allocation = one(e, "warehouse_allocations", prepared["allocation"]["id"])
    require(allocation["status"] == "consumed" and allocation["stock_move_id"] == move["id"], "实际领退未消耗原位置准备")
    require(current["moves"][:-1] == stock_before["moves"] and current["entries"][:len(stock_before["entries"])] == stock_before["entries"], "原物资收发历史被改写")
    added = current["entries"][len(stock_before["entries"]):]
    require(added and all(x["stock_move_id"] == move["id"] and x["case_id"] == case_id and x["actor_id"] == actor["id"] for x in added)
            and sum(x["quantity_milli"] for x in added) == sign * quantity and sum(x["value_cents"] for x in added) == sign * amount, "库位实际流水未守恒原收发数量/成本")
    old_bin = next(b for b in stock_before["balances"] if b["location_id"] == location["id"])
    new_bin = next(b for b in current["balances"] if b["location_id"] == location["id"])
    require(new_bin["quantity_milli"] - old_bin["quantity_milli"] == sign * quantity
            and current["item"]["quantity_milli"] - stock_before["item"]["quantity_milli"] == sign * quantity
            and current["item"]["inventory_value_cents"] - stock_before["item"]["inventory_value_cents"] == sign * amount
            and sum(b["quantity_milli"] for b in current["balances"]) == current["item"]["quantity_milli"]
            and sum(b["value_cents"] for b in current["balances"]) == current["item"]["inventory_value_cents"], "指定实际位置/门店库存数量价值不一致")
    await expect(e.page.locator("#main")).to_contain_text("实际领退料")
    return after, {"native": native, "file": evidence, "prepared": prepared, "repair_stock": fact,
                   "stock_move": move, "warehouse_entries": added, "original_bin": old_bin, "current_bin": new_bin}


async def reminder(e, fixture, f, actor):
    original = task(f, "repair_quote")
    before = e.business_snapshot("repair_before_reminder")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks") as pending:
        await e.click('.sidebar a[href="#work"]', "打开本人的维修工作")
    require((await pending.value).status == 200, "原我的工作读取失败")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks"
            and parse_qs(urlsplit(r.url).query).get("area") == ["repair"]) as pending:
        await e.click('#main .mux-work-filter a[href="#work/repair"]', "原工作筛选维修模块")
    require((await pending.value).status == 200, "原维修任务筛选失败")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks"
            and parse_qs(urlsplit(r.url).query).get("due") == ["today"]) as pending:
        await e.click('#main [data-mux-due="today"]', "实际筛选今天的维修提醒")
    require((await pending.value).status == 200, "原今日维修任务读取失败")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks"
            and parse_qs(urlsplit(r.url).query).get("q") == [f["case"]["number"]]) as pending:
        await e.fill('#filters [name="q"]', f["case"]["number"], "查找本次原维修提醒")
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and len(view["items"]) == 1, "今日本人的原维修提醒不唯一或为空")
    read = view["items"][0]
    for key in ("id", "case_id", "key", "assignee_id", "status", "due_date", "version", "title"):
        require(read[key] == original[key], "维修提醒API/DB不一致：" + key)
    require(read["assignee_id"] == actor["id"] and read["case_number"] == f["case"]["number"], "维修提醒身份/原单错误")
    row = e.page.locator("#main .work-table tbody tr")
    await expect(row).to_have_count(1)
    for text in (original["title"], original["due_date"], actor["display_name"], f["case"]["number"]):
        await expect(row).to_contain_text(text)
    await e.snapshot("repair-today-reminder")
    visible_row = await row.inner_text()
    query = parse_qs(urlsplit(response.url).query)
    require(query.get("scope") == ["mine"] and query.get("status") == ["open"] and query.get("area") == ["repair"]
            and query.get("due") == ["today"], "维修提醒没有按本人/本模块/今日未结真实筛选")
    route = read.get("entry_route") or f'case/{f["case"]["id"]}'
    require(route in (f'repair-orders/{f["case"]["id"]}', f'case/{f["case"]["id"]}'), "原提醒入口未指向同维修")
    target_path = f'{REPAIR}/{f["case"]["id"]}' if route.startswith("repair-orders/") else f'/api/flow/cases/{f["case"]["id"]}'
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == target_path) as pending:
        await e.click(f'#main .work-table [data-act="open"][data-route="{route}"]', "从原今日提醒实际进入同维修")
    require((await pending.value).status == 200, "维修提醒原单入口失败")
    await expect(e.page.locator("#main h1")).to_have_text(f["case"]["title"])
    e.business_unchanged(before, "repair_after_reminder")
    return {"native_read": {"path": urlsplit(response.url).path, "status": 200, "route": route}, "task": original,
            "visible_row": visible_row, "click_to_original": True, "business_unchanged": True}


async def repair_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    checkpoint.start("HK-031")
    try:
        fixture, vehicle, customer, work, item, warehouse, location = source_facts(e, checkpoint)
        store_id, token = fixture["store_id"], uuid.uuid4().hex[:10]
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        original_material = material_facts(e, item["id"])
        manager = await login_as(e, context, credentials, fixture["manager_key"], "service-intake/resources", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("工位与快捷项目")
        await e.click('#main [data-act="intake-resource-new"]', "主管新增本次真实维修工位")
        resource_name = "合成维修工位" + token
        await e.fill('#modal [name="code"]', "R" + token, "填写明确工位代码")
        await e.fill('#modal [name="name"]', resource_name, "填写明确工位名称")
        await select_value(e, '#modal [name="type"]', "维修", "明确维修工位类型")
        protection = Guard(e, "repair_create_resource", manager, store_id, append={"intake_resources", "intake_command_receipts"})
        created, _, resource_native, _ = await submit(e, INTAKE + "/resources", INTAKE + "/catalog", store_id, 201, protection=protection)
        resource = one(e, "intake_resources", created["id"])
        require(resource["store_id"] == store_id and resource["code"] == "R" + token, "新维修工位来源错误")
        require(resource["name"] == resource_name and resource["resource_type"] == "repair" and resource["active"] and resource["active_case_id"] is None, "新维修工位类型/实际占用错误")
        service = await login_as(e, context, credentials, fixture["service_key"], "service-intake/appointments", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("维修预约与到店")
        await e.click('#main [data-act="intake-new"][data-mode="appointment"]', "服务顾问登记本次原客户车辆预约")
        vehicle_label = " · ".join(str(v) for v in (customer["name"], customer["phone"], vehicle["plate"], vehicle["vin"]) if v)
        await live_choice(e, "customer_vehicle_id", vehicle["vin"], vehicle_label, expected_value=vehicle["id"])
        await live_choice(e, "resource_id", resource_name, resource_name, expected_value=resource["id"])
        for field in ("starts_at", "ends_at"):
            value = await e.page.locator(f'#modal [name="{field}"]').input_value()
            await e.fill(f'#modal [name="{field}"]', value, "明确页面所列本次预约时段")
        await e.fill('#modal [name="reason"]', "本次合成现场检查并更换明确授权用料", "填写客户本次维修诉求")
        protection = Guard(e, "repair_original_appointment_create", service, store_id,
            append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_appointments", "intake_command_receipts", "business_entity_case_contexts"},
            update={"intake_resources": {resource["id"]: {"updated_at", "version"}}},
            vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="service_intake")
        booked, view, booked_native, book_request = await submit(e, INTAKE + "/appointments", INTAKE + "/appointments/*", store_id, 201, protection=protection)
        appointment_id, intake_case_id = booked["id"], booked["case_id"]
        appointment = one(e, "intake_appointments", appointment_id)
        intake_before = case_facts(e, intake_case_id)
        require(appointment["customer_vehicle_id"] == vehicle["id"] and appointment["resource_id"] == resource["id"]
                and appointment["status"] == "scheduled" and appointment["repair_case_id"] is None and view["id"] == appointment_id
                and intake_before["case"]["customer_id"] == customer["id"] and intake_before["case"]["created_by"] == service["id"]
                and task(intake_before, "intake_arrive")["role"] == "service", "原预约没有真实车辆/客户/任务来源")
        book_event = [event for event in intake_before["events"] if event["action"] == "intake_book"]
        require(len(book_event) == 1 and book_event[0]["actor_id"] == service["id"] and book_request["customer_vehicle_id"] == vehicle["id"]
                and book_request["resource_id"] == resource["id"] and book_request["mode"] == "appointment" and book_request["preset_id"] is None,
                "原预约没有唯一员工创建事件或选错普通接待模式")
        require(original_material == material_facts(e, item["id"]), "预约错误地产生材料收发")
        await form(e, "reschedule", intake=True)
        starts = datetime.fromisoformat(await e.page.locator('#modal [name="starts_at"]').input_value()) + timedelta(minutes=30)
        ends = datetime.fromisoformat(await e.page.locator('#modal [name="ends_at"]').input_value()) + timedelta(minutes=30)
        await e.fill('#modal [name="starts_at"]', starts.isoformat(timespec="minutes"), "明确新的预约开始")
        await e.fill('#modal [name="ends_at"]', ends.isoformat(timespec="minutes"), "明确新的预约结束")
        await e.fill('#modal [name="reason"]', "本次合成客户要求延后半小时", "填写真实合成改约原因")
        protection = Guard(e, "repair_original_appointment_reschedule", service, store_id,
            append={"flow_events", "audit_logs", "intake_command_receipts"},
            update={**mutable(e, intake_case_id), "intake_resources": {resource["id"]: {"updated_at", "version"}},
                "intake_appointments": {appointment_id: {"resource_id", "starts_at", "ends_at", "updated_at", "version"}}}, cases={intake_case_id})
        _, _, rescheduled_native, reschedule_request = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/reschedule", f"{INTAKE}/appointments/{appointment_id}", store_id, protection=protection)
        changed = one(e, "intake_appointments", appointment_id)
        intake_after = case_facts(e, intake_case_id)
        normalize = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None) if "+" in value or value.endswith("Z") else datetime.fromisoformat(value)
        require(changed["version"] > appointment["version"] and normalize(changed["starts_at"]) == normalize(reschedule_request["values"]["starts_at"])
                and normalize(changed["ends_at"]) == normalize(reschedule_request["values"]["ends_at"]), "原改约未保存明确新时段")
        reschedule_event = event_added(intake_before, intake_after, "intake_reschedule", service)
        service, _, arrive_owner = await responsible(e, context, credentials, fixture, intake_case_id, "intake_arrive", "service", appointment_id=appointment_id)
        arrival_file = await upload(e, intake_case_id, service, "evidence", "arrival-" + token + ".txt", "本次逐位核VIN " + vehicle["vin"] + "，合成现场里程32100公里。", store_id)
        await form(e, "arrive", intake=True)
        wrong_vin = ("M" if vehicle["vin"][0] != "M" else "L") + vehicle["vin"][1:]
        await e.fill('#modal [name="checked_vin"]', wrong_vin, "填写合法但不对应原车辆的VIN拒绝边界")
        await e.fill('#modal [name="odometer_km"]', "32100", "填写明确本次合成现场里程")
        await file_choice(e, "evidence_id", arrival_file)
        digest_before = e.business_snapshot("repair_before_wrong_vin")
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"{INTAKE}/appointments/{appointment_id}/actions/arrive") as pending:
            await e.click('#modal form button[type="submit"]', "员工提交真实错误VIN守卫")
        refusal = await pending.value
        rejected = await refusal.json()
        require(refusal.status == 409 and "现场VIN与客户车辆档案不符" in rejected.get("detail", ""), "原到店错VIN拒绝不符合真实合同")
        await expect(e.page.locator("#modal .formerror")).to_contain_text(rejected["detail"])
        e.business_unchanged(digest_before, "repair_after_wrong_vin")
        refusal_native, _ = await metadata(e, refusal, store_id)
        await e.snapshot("repair-protected-wrong-vin")
        await expect(e.page.locator("#modal form")).not_to_have_attribute("aria-busy", "true")
        await e.click('#modal .modalhead [data-act="close"]', "取消错误VIN表单后重新现场核对")
        await expect(e.page.locator("#modal .wfx-discard")).to_be_visible()
        await e.click('#modal [data-wfx-discard]', "明确放弃错误VIN填写")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        e.business_unchanged(digest_before, "repair_after_wrong_vin_discard")
        await form(e, "arrive", intake=True)
        await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "现场重新逐位核对真实原VIN")
        await e.fill('#modal [name="odometer_km"]', "32100", "填写明确本次合成现场里程")
        await file_choice(e, "evidence_id", arrival_file)
        arrival_before = case_facts(e, intake_case_id)
        protection = Guard(e, "repair_original_arrival", service, store_id,
            append={"flow_tasks", "flow_events", "audit_logs", "intake_arrivals", "intake_command_receipts"},
            update={**mutable(e, intake_case_id, vehicle_id=vehicle["id"]), "intake_appointments": {appointment_id: {"status", "updated_at", "version"}}},
            cases={intake_case_id}, vehicle_id=vehicle["id"])
        _, _, arrival_native, arrival_request = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/arrive", f"{INTAKE}/appointments/{appointment_id}", store_id, protection=protection)
        arrivals = e.db.rows("SELECT * FROM intake_arrivals WHERE appointment_id=?", (appointment_id,))
        require(len(arrivals) == 1 and arrivals[0]["checked_vin"] == vehicle["vin"] and arrivals[0]["customer_vehicle_id"] == vehicle["id"]
                and arrivals[0]["odometer_km"] == 32100 and arrivals[0]["evidence_id"] == arrival_file["file"]["id"] and arrivals[0]["actor_id"] == service["id"], "实际到店来源/VIN/里程错误")
        arrived_intake = case_facts(e, intake_case_id)
        arrival_event = event_added(arrival_before, arrived_intake, "intake_arrive", service)
        require(one(e, "intake_appointments", appointment_id)["status"] == "arrived" and arrived_intake["case"]["state"] == "working", "原到店未保存实际状态")
        task(arrived_intake, "intake_arrive", "done")
        task(arrived_intake, "intake_convert")
        service, _, convert_owner = await responsible(e, context, credentials, fixture, intake_case_id, "intake_convert", "service", appointment_id=appointment_id)
        await form(e, "convert", intake=True)
        await e.fill('#modal [name="due_date"]', day, "明确本次维修预计交接日")
        convert_before = case_facts(e, intake_case_id)
        protection = Guard(e, "repair_original_intake_convert", service, store_id,
            append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_command_receipts", "intake_repair_contexts", "intake_vehicle_bindings", "business_entity_case_contexts"},
            update={**mutable(e, intake_case_id), "intake_appointments": {appointment_id: {"status", "repair_case_id", "updated_at", "version"}}},
            cases={intake_case_id}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="repair")
        converted, _, convert_native, _ = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/convert", f"{INTAKE}/appointments/{appointment_id}", store_id, protection=protection)
        case_id = converted["repair_case_id"]
        repair = facts(e, case_id)
        require(repair["case"]["kind"] == "repair" and repair["case"]["flow_version"] == 4 and repair["case"]["state"] == "assessment"
                and repair["case"]["customer_id"] == customer["id"] and len(repair["context"]) == len(repair["binding"]) == 1
                and repair["context"][0]["appointment_id"] == appointment_id and repair["context"][0]["profile"] == "regular"
                and repair["binding"][0]["vin"] == vehicle["vin"] and repair["binding"][0]["evidence_id"] == arrival_file["file"]["id"]
                and one(e, "intake_appointments", appointment_id)["repair_case_id"] == case_id, "真实到店没有唯一转换同客户/VIN明细维修")
        require(all(repair["binding"][0][key] == vehicle[key] for key in ("customer_identity_id", "vehicle_identity_id"))
                and repair["binding"][0]["customer_vehicle_id"] == vehicle["id"] and repair["binding"][0]["reviewed_by"] == service["id"]
                and repair["context"][0]["resource_id"] == resource["id"], "维修转换没有冻结真实原车辆身份和工位")
        converted_intake = case_facts(e, intake_case_id)
        convert_event = event_added(convert_before, converted_intake, "intake_convert", service)
        require(converted_intake["case"]["state"] == "completed" and all(t["status"] != "open" for t in converted_intake["tasks"])
                and one(e, "intake_appointments", appointment_id)["status"] == "converted", "原预约转换后仍有悬置原接待")
        models = [event for event in repair["events"] if event["action"] == "repair_vehicle_model_snapshot"]
        require(len(models) == 1 and models[0]["detail"]["customer_vehicle_id"] == vehicle["id"]
                and models[0]["detail"]["model_name"] == vehicle["model_name"] and models[0]["detail"]["vin"] == vehicle["vin"]
                and models[0]["actor_id"] == service["id"], "维修原车型来源未冻结或串车")
        await checkpoint.passed({"resource": resource, "native_resource": resource_native, "book": booked_native, "appointment": changed,
            "reschedule": rescheduled_native, "book_event": book_event[0], "reschedule_event": reschedule_event,
            "arrive": arrival_native, "arrival": arrivals[0], "arrival_event": arrival_event,
            "protected_wrong_vin": {"native": refusal_native, "detail": e.scrub(rejected["detail"]), "business_unchanged": True, "explicit_discard": True},
            "convert": convert_native, "convert_event": convert_event, "model_snapshot": models[0], "repair_case_id": case_id,
            "context": repair["context"][0], "binding": repair["binding"][0],
            "task_owners": [arrive_owner, convert_owner]}, conditional=[{"check_id": "HK-031-overlap-no-show", "status": "not_tested", "reason": "本批核改约与错误VIN；未造另一重叠预约或核实未到"}])
        checkpoint.start("HK-044")
        service, _, quote_owner = await responsible(e, context, credentials, fixture, case_id, "repair_quote", "service")
        await checkpoint.passed(await reminder(e, fixture, facts(e, case_id), service))
        checkpoint.start("HK-034")
        service, _, _ = await responsible(e, context, credentials, fixture, case_id, "repair_quote", "service")
        await form(e, "quote")
        line = e.page.locator('#modal [data-repair-line]').nth(0)
        e.action("fill", "查找明确原作业项目", value=work["name"])
        await line.locator('[role="combobox"]').fill(work["name"])
        chosen = line.get_by_role("option", name="项目 · " + work["code"] + " " + work["name"], exact=True)
        await expect(chosen).to_be_visible()
        e.action("click", "明确选择原作业项目", work_item_id=work["id"])
        await chosen.click()
        await expect(line.locator('[name="source"]')).to_have_value("work:" + str(work["id"]))
        await e.fill('#modal [data-repair-line]:nth-child(1) [name="quantity"]', "1.000", "填写本次明确作业数量")
        await e.fill('#modal [data-repair-line]:nth-child(1) [name="price"]', fen_text(work["standard_fee_cents"]), "填写本次原作业标准价")
        await e.click('#modal [data-act="repair-add-line"]', "增加本次真实采购配件行")
        part = e.page.locator('#modal [data-repair-line]').nth(1)
        e.action("fill", "查找本轮原采购材料", value=item["name"])
        await part.locator('[role="combobox"]').fill(item["name"])
        chosen = part.get_by_role("option", name="配件 · " + item["sku"] + " " + item["name"], exact=True)
        await expect(chosen).to_be_visible()
        e.action("click", "明确选择本轮原采购材料", item_id=item["id"])
        await chosen.click()
        await expect(part.locator('[name="source"]')).to_have_value("part:" + str(item["id"]))
        await e.fill('#modal [data-repair-line]:nth-child(2) [name="quantity"]', "1.250", "填写当前授权用料数量")
        await e.fill('#modal [data-repair-line]:nth-child(2) [name="price"]', "80.20", "填写本批明确合成配件报价")
        await e.fill('#modal [name="discount"]', "0.00", "明确本次不另优惠")
        await e.fill('#modal [name="reason"]', "合成现场按项检查及明确更换1.250升用料，报价非采购成本", "填写本版诊断方案及报价原因")
        repair, _, quoted = await command(e, fixture, case_id, "quote", service)
        quote = repair["quotes"][0]
        expected_amount = work["standard_fee_cents"] + 10025
        require(len(repair["quotes"]) == 1 and len(repair["lines"]) == 2 and quote["amount_cents"] == expected_amount and quote["discount_cents"] == 0
                and quote["created_by"] == service["id"] and repair["case"]["state"] == "approval", "本版原作业/配件报价金额错误")
        sources = {r["kind"]: r for r in repair["lines"]}
        require(set(sources) == {"work", "part"} and len({r["line_key"] for r in repair["lines"]}) == 2
                and sources["work"]["work_item_id"] == work["id"] and sources["work"]["item_id"] is None
                and sources["work"]["code"] == work["code"] and sources["work"]["name"] == work["name"]
                and sources["work"]["unit"] == work["billing_unit"] and sources["work"]["quantity_milli"] == 1000
                and sources["work"]["unit_price_cents"] == sources["work"]["standard_fee_cents"] == sources["work"]["amount_cents"] == work["standard_fee_cents"]
                and sources["part"]["item_id"] == item["id"] and sources["part"]["work_item_id"] is None
                and sources["part"]["code"] == item["sku"] and sources["part"]["name"] == item["name"] and sources["part"]["unit"] == item["unit"]
                and sources["part"]["quantity_milli"] == 1250 and sources["part"]["unit_price_cents"] == 8020 and sources["part"]["amount_cents"] == 10025
                and all(r["discount_cents"] == 0 and r["quote_id"] == quote["id"] for r in repair["lines"]), "报价原项目/配件/数量/单位/逐行金额不匹配")
        frozen_specs = [{k: row[k] for k in ("line_key", "kind", "work_item_id", "item_id", "code", "name", "unit", "standard_fee_cents",
            "quantity_milli", "unit_price_cents", "amount_cents", "discount_cents")} for row in repair["lines"]]
        digest = hashlib.sha256(json.dumps({"purpose": quote["purpose"], "reason": quote["reason"], "lines": frozen_specs}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        require(quote["digest"] == digest, "本版维修摘要不是实际冻结逐行字节")
        manager, _, price_owner = await responsible(e, context, credentials, fixture, case_id, "repair_price_" + str(quote["id"]), "manager")
        await form(e, "price_approve")
        await e.fill('#modal [name="minimum"]', fen_text(expected_amount), "填写主管本次确认最低价")
        await checkbox(e, '#modal [name="allow_below_minimum"]', False, "不默认批准低价例外")
        await e.fill('#modal [name="reason"]', "独立核对本版作业材料数量与合成约定价格", "填写主管独立核价说明")
        repair, _, price_approved = await command(e, fixture, case_id, "price_approve", manager)
        require(len(repair["approvals"]) == 1 and repair["approvals"][0]["actor_id"] == manager["id"] != service["id"]
                and repair["approvals"][0]["quote_id"] == quote["id"] and repair["approvals"][0]["minimum_total_cents"] == expected_amount
                and not repair["approvals"][0]["allow_below_minimum"], "主管未独立批准本版维修价")
        service, _, authorize_owner = await responsible(e, context, credentials, fixture, case_id, "repair_authorize_" + str(quote["id"]), "service")
        auth_file = await upload(e, case_id, service, "authorization", "authorization-" + token + ".txt",
            f"本次维修{case_id} 报价{quote['id']} 摘要{quote['digest']} 金额{expected_amount}分；合成客户确认这两行。", store_id)
        await form(e, "authorize")
        await file_choice(e, "evidence_id", auth_file)
        repair, _, authorized = await command(e, fixture, case_id, "authorize", service)
        require(len(repair["authorizations"]) == 1 and repair["authorizations"][0]["quote_digest"] == quote["digest"]
                and repair["authorizations"][0]["evidence_id"] == auth_file["file"]["id"] and repair["case"]["data"]["authorized_quote_id"] == quote["id"], "客户明确授权未绑定当前版及实际凭据")
        technician, _, work_owner = await responsible(e, context, credentials, fixture, case_id, "repair_work", "technician")
        await form(e, "start")
        await e.fill('#modal [name="result"]', "合成现场逐位核车并已进入原工位实际开工", "技师记录实际开工结果")
        repair, _, started = await command(e, fixture, case_id, "start", technician)
        require(repair["case"]["data"]["started"] and one(e, "intake_resources", resource["id"])["active_case_id"] == case_id
                and len(repair["resource_uses"]) == 1 and repair["resource_uses"][0]["action"] == "acquire"
                and repair["resource_uses"][0]["resource_id"] == resource["id"] and repair["resource_uses"][0]["actor_id"] == technician["id"], "实际开工未占用本次原工位")
        checkpoint.note({"case_id": case_id, "quote": quote, "lines": repair["lines"], "native_quote": quoted, "native_price": price_approved,
            "native_authorize": authorized, "native_start": started, "task_owners": [quote_owner, price_owner, authorize_owner, work_owner]})
        checkpoint.start("HK-053")
        inventory, _, issue_owner = await responsible(e, context, credentials, fixture, case_id, "repair_issue", "inventory")
        repair, first_issue = await stock_action(e, fixture, case_id, "issue", inventory, item, warehouse, location, 1250, filename="issue-" + token + ".txt")
        checkpoint.note({"first_issue": first_issue, "task_owner": issue_owner})
        checkpoint.start("HK-049")
        repair, returned = await stock_action(e, fixture, case_id, "return_material", inventory, item, warehouse, location, 250,
                                            original=first_issue["repair_stock"], filename="return-" + token + ".txt")
        await checkpoint.passed({"case_id": case_id, "original_issue": first_issue["repair_stock"], "return": returned,
            "net_after_return_milli": sum(r["quantity_milli"] for r in repair["stock"])}, conditional=[{"check_id": "HK-049-after-settlement", "status": "not_tested", "reason": "原领料退回在冻结结算前，未冒充已结算售后退货"}])
        checkpoint.start("HK-053")
        inventory, _, reissue_owner = await responsible(e, context, credentials, fixture, case_id, "repair_issue", "inventory")
        repair, reissued = await stock_action(e, fixture, case_id, "issue", inventory, item, warehouse, location, 250, filename="reissue-" + token + ".txt")
        require(sum(r["quantity_milli"] for r in repair["stock"]) == 1250 and sum(m["quantity_milli"] for m in repair["moves"]) == -1250,
                "维修原领退补领没有满足授权净量1250")
        task(repair, "repair_issue", "done")
        await checkpoint.passed({"case_id": case_id, "first_issue": first_issue, "reissue": reissued, "return_reference": returned["repair_stock"],
            "net_quantity_milli": 1250, "net_material_cost_cents": sum(r["value_cents"] for r in repair["stock"]), "task_owners": [issue_owner, reissue_owner]})
        checkpoint.start("HK-034")
        technician, _, finish_owner = await responsible(e, context, credentials, fixture, case_id, "repair_work", "technician")
        await form(e, "finish")
        await e.fill('#modal [name="result"]', "本次合成施工已完成，净用料1.250升并交服务顾问质检", "技师记录明确施工完成结果")
        repair, _, finished = await command(e, fixture, case_id, "finish", technician)
        require(repair["case"]["state"] == "quality", "原施工完成未进入质检")
        service, _, quality_owner = await responsible(e, context, credentials, fixture, case_id, "repair_quality", "service")
        quality_file = await upload(e, case_id, service, "inspection", "inspection-" + token + ".txt", f"本次工单{case_id}当前报价{quote['id']}合成安全与施工检查合格。", store_id)
        await form(e, "quality")
        await e.fill('#modal [name="result"]', "本次合成施工项目与授权用料一致，交接安全检查合格", "服务顾问记录本次实际质检结果")
        await select_value(e, '#modal [name="outcome"]', "合格", "明确本次检查合格")
        await file_choice(e, "evidence_id", quality_file)
        repair, _, quality = await command(e, fixture, case_id, "quality", service)
        require(len(repair["quality"]) == 1 and repair["quality"][0]["passed"] and repair["quality"][0]["quote_id"] == quote["id"]
                and repair["quality"][0]["evidence_id"] == quality_file["file"]["id"] and repair["case"]["state"] == "settling", "当前本版质检事实错误")
        manager, _, allocate_owner = await responsible(e, context, credentials, fixture, case_id, "repair_allocate", "manager")
        allocation_file = await upload(e, case_id, manager, "evidence", "allocation-" + token + ".txt", "本批明确人工成本12.34元，客户全额承担本版合成维修。", store_id)
        await form(e, "allocate")
        await e.click('#modal [data-repair-customer-all]', "明确原客户全额承担当前授权")
        await e.fill('#modal [name="due_customer"]', day, "明确客户本次款项到期日")
        await e.fill('#modal [name="labor_cost"]', "12.34", "填写本批明确合成人工成本")
        await file_choice(e, "evidence", allocation_file)
        repair, _, allocated = await command(e, fixture, case_id, "allocate", manager)
        net_cost = sum(s["value_cents"] for s in repair["stock"])
        require(len(repair["settlements"]) == len(repair["allocations"]) == 1 and not repair["payments"]
                and repair["settlements"][0]["labor_cost_cents"] == 1234 and repair["case"]["cost_cents"] == net_cost + 1234, "承担错误地产生现金或成本不匹配")
        allocation = repair["allocations"][0]
        require(allocation["payer_type"] == "customer" and allocation["payer_name"] == customer["name"]
                and allocation["amount_cents"] == expected_amount and allocation["due_date"] == day, "原客户承担金额/身份/期限错误")
        checkpoint.note({"native_finish": finished, "native_quality": quality, "native_allocate": allocated, "quality": repair["quality"][0],
            "settlement": repair["settlements"][0], "allocation": allocation, "cost_cents": net_cost + 1234,
            "completion_task_owners": [finish_owner, quality_owner, allocate_owner]})
        checkpoint.start("HK-079")
        finance, _, receive_owner = await responsible(e, context, credentials, fixture, case_id, "repair_receive_" + str(allocation["id"]), "finance")
        pay_file = await upload(e, case_id, finance, "evidence", "received-" + token + ".txt", f"合成原客户本次真实登记到账{expected_amount}分，独立流水R-{token}。", store_id)
        await form(e, "receive")
        await e.fill('#modal [name="amount"]', fen_text(expected_amount), "核对原客户本次合成实际收款")
        account_root = e.page.locator('#modal .lookup[data-kind="account"]')
        e.action("fill", "查找本店明确实际资金账户", value="门店结算账户（演示）")
        await account_root.locator('[role="combobox"]').fill("门店结算账户（演示）")
        option = account_root.get_by_role("option").filter(has_text="门店结算账户（演示）")
        await expect(option).to_have_count(1)
        await expect(option).to_be_visible()
        e.action("click", "明确选择原启用资金账户")
        await option.click()
        account_id = int(await e.page.locator('#modal [name="account_id"]').input_value())
        account = one(e, "flow_accounts", account_id)
        require(account["active"] and account["store_id"] == store_id and account["name"] == "门店结算账户（演示）", "原明确账户不在本店启用范围")
        await e.fill('#modal [name="reference"]', "R-" + token, "填写本次独立原收款凭证号")
        await file_choice(e, "evidence_id", pay_file)
        repair, received_view, received = await command(e, fixture, case_id, "receive", finance)
        require(len(repair["repair_payments"]) == len(repair["payments"]) == len(repair["cash"]) == 1, "一次维修到账重复或缺独立资金事实")
        payment, link, cash = repair["repair_payments"][0], repair["payments"][0], repair["cash"][0]
        require(payment["allocation_id"] == allocation["id"] and payment["payment_link_id"] == link["id"] and payment["evidence_id"] == pay_file["file"]["id"]
                and link["direction"] == cash["direction"] == "in" and link["amount_cents"] == cash["amount_cents"] == expected_amount
                and link["account_id"] == account_id and link["reference"] == cash["voucher_no"] == "R-" + token
                and cash["created_by"] == finance["id"] and cash["account"] == account["name"] and cash["category"] == "workflow_repair"
                and cash["approval_state"] == "approved" and cash["business_date"] == link["business_date"] == day
                and link["original_id"] is None and received_view["customer_due_cents"] == received_view["receivable_cents"] == 0
                and not repair["case"]["data"].get("released_date"), "原维修到账/客户承担/尚未接车事实不匹配")
        await checkpoint.passed({"case_id": case_id, "allocation": allocation, "repair_payment": payment, "payment_link": link,
            "cash": cash, "native_receive": received, "account": account, "task_owner": receive_owner})
        checkpoint.start("HK-034")
        service, _, release_owner = await responsible(e, context, credentials, fixture, case_id, "repair_release", "service")
        release_file = await upload(e, case_id, service, "evidence", "released-" + token + ".txt", "本次合成客户已核车并实际接车，原维修收款另行保留。", store_id)
        await form(e, "release")
        await file_choice(e, "evidence_id", release_file)
        repair, _, released = await command(e, fixture, case_id, "release", service)
        require(repair["case"]["state"] == "completed" and repair["case"]["data"]["released_date"] == day
                and repair["case"]["completed_date"] == day and one(e, "intake_resources", resource["id"])["active_case_id"] is None
                and [u["action"] for u in repair["resource_uses"]] == ["acquire", "release"] and all(t["status"] != "open" for t in repair["tasks"]), "客户实际接车/任务结束/工位释放错误")
        require(repair["payments"] == [link] and repair["cash"] == [cash] and sum(s["quantity_milli"] for s in repair["stock"]) == 1250,
                "接车重复了现金或领料")
        before_refresh = e.business_snapshot("repair_before_final_refresh")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{REPAIR}/{case_id}") as pending:
            await e.page.reload()
        refresh = await pending.value
        require(refresh.status == 200 and (await refresh.json())["state"] == "completed", "刷新原维修完成结果错误")
        await expect(e.page.locator("#main h1")).to_have_text(repair["case"]["title"])
        e.business_unchanged(before_refresh, "repair_after_final_refresh")
        require(facts(e, case_id) == repair, "刷新改变了维修原事实")
        await checkpoint.passed({"case_id": case_id, "final_case": repair["case"], "native_release": released, "release_file": release_file,
            "release_task_owner": release_owner, "resource_uses": repair["resource_uses"], "tasks": repair["tasks"], "events": repair["events"],
            "net_material_cost_cents": net_cost, "labor_cost_cents": 1234, "refresh_business_unchanged": True}, conditional=[
                {"check_id": "HK-034-quality-negative", "status": "not_tested", "reason": "本批合格施工路径；未冒充不合格整改复检、停工、索赔或洗车"}])
        checkpoint.finish({"customer_id": customer["id"], "customer_vehicle_id": vehicle["id"], "vin": vehicle["vin"],
            "appointment_id": appointment_id, "intake_case_id": intake_case_id, "repair_case_id": case_id,
            "quote_id": quote["id"], "allocation_id": allocation["id"], "payment_link_id": link["id"], "cash_id": cash["id"], "material_item_id": item["id"]})
    except Exception as error:
        checkpoint.failed(error)
        raise


REPAIR_SCENARIOS = ((SCENARIO, repair_business, 300),)
