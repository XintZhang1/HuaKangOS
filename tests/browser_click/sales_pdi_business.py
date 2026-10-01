"""This run's independently purchased VIN: PDI and two real UI payments.

The completed add-on path is consumed from finite same-run click evidence and
opened through its original UI. No app imports or positive API/SQL writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import employee_choice, login_as, native_submit, new_event, require
import sales_order_business as S
import sales_followon_business as F
import receivables_business as AR
from vehicle_purchase_business import live_choice, select_value


SCENARIO = "sales-pdi-addon-hk037-065-075"
CONTRACTS = {
    "HK-037": ("新车检测(PDI)", ["同一新订单/VIN不合格后真实发车受阻，技师整改、服务顾问复检独立留痕",
        "两轮检查、三份原件和原任务/事件完整，复检后实际发车、签回与客户提车分别完成"]),
    "HK-065": ("精品加装出库", ["同轮完整父的真实领料、安装、不合格整改、复检、客户接收及到账点击证据对应同VIN",
        "当次真实原加装页面和即时数据库事实一致，零追加出库或收款，不借映射计通过"]),
    "HK-075": ("车辆销售收款", ["新单原财务两笔实际收款对应独立回执/原款/现金/账户/凭据，累计与剩余准确",
        "原生UI连续点击只有一次提交和现金，原款不修改；事前误记说明与原正确凭据分别保留"]),
}
TABLES = {name: "id" for name in (
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_request_receipts", "flow_files", "file_scan_events",
    "sales_quotes", "sales_quote_reviews", "sales_quote_resolutions", "sales_quote_consents", "flow_vehicle_holds",
    "vehicles", "vehicle_positions", "vehicle_position_entries", "vehicle_custodies", "flow_payment_links", "cash_entries", "flow_accounts")}
TABLES.update(flow_vehicle_holds="vehicle_id", file_security="file_id", business_entity_case_contexts="case_id", business_entity_cash_contexts="cash_id")
CASE_COLUMNS = F.CASE_COLUMNS | {"vehicle_id"}
COMMON = {"flow_tasks", "flow_events", "audit_logs", "flow_request_receipts"}
FILES = {"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}


def one(e, table, key, pk="id"):
    result = e.db.rows(f"SELECT * FROM {table} WHERE {pk}=?", (key,))
    require(len(result) == 1, "有限本轮原件缺失或重复：" + table)
    return result[0]


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        catalogue = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, (title, _) in CONTRACTS.items():
            row = catalogue[key]
            require(row["title"] == title and row["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == key + "-business" for c in row["acceptance_checks"]), "PDI目录合同不一致：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": list(CONTRACTS), "complete": False, "passed": False,
            "source_contract_sha256": self.digest, "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution": "native_browser_original_forms", "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_money_and_physical_inputs": True, "file_scan": "original_structure_only_not_clamav",
                "production_bank_or_physical_handover_acceptance": False, "company_contract_template_approval_acceptance": False,
                "business_entity_policy_acceptance": False, "original_payment_correction_executed": False},
            "requirements": [{"id": k, "title": v[0], "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending", "visual_pixels": "pending"},
                "acceptance_checks": [{"id": k + "-business", "check_id": k + "-business", "status": "not_tested",
                    "criteria": v[1], "evidence": {}}], "conditional_checks": []} for k, v in CONTRACTS.items()]}
        self.save()

    def save(self):
        raw = json.dumps(self.report, ensure_ascii=False, indent=2) + "\n"
        self.path.write_text(raw, encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.save()

    def note(self, **evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
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
                row["acceptance_checks"][0]["incomplete_reason"] = "后续原依赖失败，本轮终止"
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "三项原业务闭包未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=3, passed_requirements=3, report_sources=sources)
        self.save()
        self.e.observe("sales_pdi_business_checkpoint", {"path": str(self.path), "report_sources": sources, "business_accepted": False})


class Guard:
    """Only finite current source rows and declared append-only facts may change."""
    def __init__(self, e, label, actor, store_id, *, case_id=None, append=(), update=None, new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store_id
        self.case_id, self.append, self.update, self.kind = case_id, set(append), update or {}, new_kind
        require(self.append | self.update.keys() <= TABLES.keys(), "PDI原表守卫白名单错误")
        self.before = e.business_snapshot("before_pdi_" + label)
        self.old = {t: e.db.rows(f"SELECT * FROM {t} ORDER BY {TABLES[t]}") for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_pdi_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
            if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "PDI改动了无关原表：" + str(sorted(changed)))
        owned = {self.case_id} if self.case_id is not None else set()
        if self.kind:
            previous = {r["id"] for r in self.old["flow_cases"]}
            added_cases = [r for r in self.e.db.rows("SELECT * FROM flow_cases ORDER BY id") if r["id"] not in previous]
            require(len(added_cases) == 1 and added_cases[0]["kind"] == self.kind
                and added_cases[0]["store_id"] == self.store and added_cases[0]["created_by"] == self.actor["id"], "PDI动作新增了错误原单")
            if self.kind == "callback":
                source = one(self.e, "flow_cases", self.case_id)
                require(added_cases[0]["parent_id"] == self.case_id and added_cases[0]["customer_id"] == source["customer_id"], "交付回访未对应本次原单客户")
            owned.add(added_cases[0]["id"])
        appended, updates = {}, {}
        for table, old in self.old.items():
            pk = TABLES[table]
            current = {r[pk]: r for r in self.e.db.rows(f"SELECT * FROM {table} ORDER BY {pk}")}
            old_ids = {r[pk] for r in old}
            updates[table] = []
            for row in old:
                require(row[pk] in current, "PDI删除旧事实：" + table)
                columns = {k for k in row if row[k] != current[row[pk]][k]}
                require(columns <= self.update.get(table, {}).get(row[pk], set()), "PDI覆盖无权旧行：" + table + "/" + str(row[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updates[table].append({"id": row[pk], "columns": sorted(columns)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(not new or table in self.append, "PDI只许更新的表新增原件：" + table)
            require(len(new) <= (8 if table == "flow_tasks" else 3), "PDI单步新增事实超出原动作范围：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "PDI新增事实串店：" + table)
                for field in ("actor_id", "created_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "PDI新增事实串员工：" + table)
                owner = row.get("case_id")
                if table == "flow_cases":
                    owner = row["id"]
                elif table in {"sales_quote_reviews", "sales_quote_resolutions", "sales_quote_consents"}:
                    owner = one(self.e, "sales_quotes", row["quote_id"])["case_id"]
                elif table in {"file_security", "file_scan_events"}:
                    owner = one(self.e, "flow_files", row["file_id"])["case_id"]
                elif table == "business_entity_cash_contexts":
                    links = self.e.db.rows("SELECT case_id FROM flow_payment_links WHERE cash_id=?", (row["cash_id"],))
                    require(len(links) == 1, "现金主体缺唯一原款")
                    owner = links[0]["case_id"]
                elif table == "cash_entries":
                    links = self.e.db.rows("SELECT case_id FROM flow_payment_links WHERE cash_id=?", (row["id"],))
                    require(len(links) == 1, "PDI现金缺唯一原款")
                    owner = links[0]["case_id"]
                elif table == "audit_logs":
                    require(row["entity_type"] in {"flow", "cash"}, "PDI原动作出现无关审计范围")
                    if row["entity_type"] == "flow":
                        owner = row["entity_id"]
                    else:
                        links = self.e.db.rows("SELECT case_id FROM flow_payment_links WHERE cash_id=?", (row["entity_id"],))
                        require(len(links) == 1, "PDI现金审计缺原款")
                        owner = links[0]["case_id"]
                if owner is not None:
                    require(owner in owned, "PDI新增事实串原单：" + table)
            appended[table] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": appended, "updated_columns": updates,
            "all_unrelated_business_rows_and_other_stores_unchanged": True, "old_file_bytes_unchanged": True}
        self.e.observe("sales_pdi_original_row_guard", {"label": self.label, **result})
        return result


def mutable(e, key, *, car=None, account=None, hold=False, position=False):
    result = {"flow_cases": {key: CASE_COLUMNS}, "flow_tasks": {r["id"]: F.TASK_COLUMNS for r in e.db.rows("SELECT id FROM flow_tasks WHERE case_id=?", (key,))}}
    if car:
        result["vehicles"] = {car: {"version", "updated_at"}}
        custody = e.db.rows("SELECT id FROM vehicle_custodies WHERE current_vehicle_id=?", (car,))
        require(len(custody) == 1, "本次原车必须对应唯一当前保管身份")
        result["vehicle_custodies"] = {custody[0]["id"]: {"version"}}
    if account:
        result["flow_accounts"] = {account: {"version", "updated_at"}}
    if hold:
        result["flow_vehicle_holds"] = {r["vehicle_id"]: {"delivered"} for r in e.db.rows("SELECT vehicle_id FROM flow_vehicle_holds WHERE case_id=?", (key,))}
    if position:
        result["vehicle_positions"] = {r["id"]: {"version", "updated_at", "location_id", "status"} for r in e.db.rows("SELECT id FROM vehicle_positions WHERE vehicle_id=?", (car,))}
    return result


def dependencies(e, cp):
    root = Path(e.manifest["evidence_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True and Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime")
        and not root.is_relative_to(Path(e.manifest["source_root"]).resolve()), "PDI仅允许同轮仓库外合成源/证据")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance["snapshot_stable"] is True, "PDI同轮镜像未稳定")
    for name in ("sales_pdi_business.py", "business_acceptance_catalog.json", "sales_business.py", "sales_order_business.py",
        "sales_followon_business.py", "vehicle_purchase_business.py", "master_data_business.py", "material_business.py",
        "receivables_business.py", "vehicle_operations_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "PDI原镜像脚本变化：" + name)
    cp.report["mirror"] = {k: provenance[k] for k in ("source_sha256", "script_sha256")}
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    require(one(e, "stores", fixture["store_id"])["active"], "本轮原门店必须启用")
    fixture["technician_key"] = e.manifest["business_fixtures"]["repair"]["technician_key"]
    for role in ("sales", "manager", "inventory", "finance", "service", "technician"):
        user = e.manifest["users"][fixture[role + "_key"]]
        row = one(e, "users", user["id"])
        memberships = e.db.rows("SELECT role FROM user_stores WHERE user_id=? AND store_id=?", (user["id"], fixture["store_id"]))
        require(row["active"] and user["role"] == role and len(memberships) == 1 and memberships[0]["role"] == role, "缺真实本店员工岗位：" + role)
    reports = {name: S.fixed_dependency(e, cp, name) for name in (S.PRESALES, S.PURCHASE, F.MASTER, F.MATERIAL, S.SCENARIO, S.CANCELLATION_SCENARIO, F.SCENARIO)}
    sale, cancel = reports[S.SCENARIO]["report_sources"], reports[S.CANCELLATION_SCENARIO]["report_sources"]
    customer = one(e, "flow_customers", sale["customer_id"])
    salesperson = e.manifest["users"][fixture["sales_key"]]
    old_case = S.facts(e, cancel["cancelled_order_id"])
    car_id = cancel["cancelled_vehicle_id"]
    require(old_case["case"]["state"] == "cancelled" and old_case["case"]["vehicle_id"] == car_id
        and car_id != sale["delivered_vehicle_id"] and not old_case["holds"]
        and sum(p["amount_cents"] * (1 if p["direction"] == "in" else -1) for p in old_case["payments"]) == 0, "本轮退订未释放明确第二原车")
    require(customer["id"] == cancel["customer_id"] and customer["store_id"] == fixture["store_id"]
        and customer["owner_id"] == salesperson["id"] and customer["phone"] and customer["contact_allowed"], "有限客户归属/真实联系来源不匹配")
    purchase = S.checkpoint_evidence(reports[S.PURCHASE], "HK-021")
    originals = [c for c in purchase["vehicles"] if c["vehicle"]["id"] == car_id]
    require(len(originals) == 1, "退订车辆不是同轮实际采购收车来源")
    original = originals[0]
    car = e.db.rows("SELECT id,vin,store_id,model,inventory_generation,purchase_cost_cents,approval_state,color,location FROM vehicles WHERE id=?", (car_id,))[0]
    receipts = e.db.rows("SELECT r.id,r.vehicle_id,r.case_id,r.shipment_id,l.model_id FROM vehicle_purchase_receipts r JOIN vehicle_purchase_shipments s ON s.id=r.shipment_id JOIN vehicle_purchase_lines l ON l.id=s.line_id WHERE r.case_id=? AND r.vehicle_id=?", (purchase["case_id"], car_id))
    # This is historical purchase/refund provenance, not current availability.
    require(len(receipts) == 1 and all(car[k] == original["vehicle"][k] for k in ("id", "vin", "store_id", "model", "inventory_generation", "purchase_cost_cents")), "退订原车的历史采购来源已变化")
    hierarchy = S.checkpoint_evidence(reports[S.PURCHASE], "HK-177")["new_hierarchy"]
    model = dict(hierarchy["model"], brand_name=hierarchy["brand"]["name"], series_name=hierarchy["series"]["name"])
    current_model = one(e, "master_vehicle_models", model["id"])
    require(current_model["active"] and current_model["version"] == model["version"]
        and current_model["name"] == model["name"], "独立采购的原已发布车型来源变化")
    supplier_original = S.checkpoint_evidence(reports[S.PURCHASE], "HK-171")["supplier"]
    storage = S.checkpoint_evidence(reports[S.PURCHASE], "HK-178")
    supplier = one(e, "master_suppliers", supplier_original["id"])
    warehouse = one(e, "master_warehouses", storage["warehouse"]["id"])
    location = one(e, "master_locations", storage["location"]["id"])
    for row, original_row in ((supplier, supplier_original), (warehouse, storage["warehouse"]), (location, storage["location"])):
        require(row["store_id"] == fixture["store_id"] and row["active"] and row["version"] == original_row["version"], "独立采购的本店原主档失效或版本变化")
    require(warehouse["warehouse_type"] == "vehicles" and location["warehouse_id"] == warehouse["id"], "独立采购的真实整车仓库/库位关系错误")
    fixture["account_id"] = purchase["payment"]["account_id"]
    account = one(e, "flow_accounts", fixture["account_id"])
    require(account["store_id"] == fixture["store_id"] and account["active"] and account["account_type"] == "bank", "有限本店原银行账户不可用")
    cp.report["source_preconditions"] = {"cancelled_order_id": old_case["case"]["id"],
        "historical_cancelled_vehicle": car, "historical_purchase_receipt": receipts[0],
        "historical_vehicle_not_used_as_available_stock": True, "supplier_id": supplier["id"],
        "model_id": model["id"], "warehouse_id": warehouse["id"], "location_id": location["id"], "account_id": account["id"]}
    cp.save()
    return fixture, reports, customer, supplier, model, warehouse, location, account


async def real_login(e, fixture, role, operation):
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/auth/login") as logged:
        result = await operation()
    response = await logged.value
    projection = await response.json()
    target = e.manifest["users"][fixture[role + "_key"]]
    require(response.status == 200 and projection["id"] == target["id"] and projection["active"] is True
        and projection["role"] == role and projection["active_store_id"] == fixture["store_id"]
        and projection["aggregate_scope"] is False, "原真实登录未投影为本人当前店岗位")
    e.observe("sales_pdi_original_login_scope", {"actor_id": projection["id"], "store_id": projection["active_store_id"],
        "role": projection["role"], "aggregate_scope": False, "native_login_status": 200})
    return result


async def detail_as(e, context, credentials, fixture, role, key):
    actor, view = await real_login(e, fixture, role,
        lambda: S.detail_as(e, context, credentials, fixture[role + "_key"], key, fixture["store_id"]))
    require(actor["id"] == e.manifest["users"][fixture[role + "_key"]]["id"] and actor["role"] == role, "当前登录不是声明员工原岗位")
    require(view["id"] == key and S.facts(e, key)["case"]["store_id"] == fixture["store_id"], "当前原单不是当前店")
    return actor, view


async def responsible(e, context, credentials, fixture, key, task_key, role):
    current = S.task(S.facts(e, key), task_key)
    target = e.manifest["users"][fixture[role + "_key"]]
    require(current["role"] == role, "原责任任务岗位与动作不符")
    meta = {"task_id": current["id"], "key": task_key, "original_assignee_id": current["assignee_id"], "actual_employee_id": target["id"], "task_role": role}
    if current["assignee_id"] != target["id"]:
        path = f"/api/flow/cases/{key}"
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as ready:
            manager = await real_login(e, fixture, "manager", lambda: login_as(e, context, credentials, fixture["manager_key"], f"case/{key}", fixture["store_id"]))
        response = await ready.value
        view = await response.json()
        now = S.facts(e, key)
        require(response.status == 200 and view["id"] == key and view["version"] == now["case"]["version"], "原转交页面未读取当前CAS")
        await expect(e.page.locator("#main h1")).to_have_text(now["case"]["title"])
        selector = f'#main [data-act="assign"][data-id="{current["id"]}"]'
        await expect(e.page.locator(selector)).to_have_count(1)
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "主管在原任务中转交明确本人")
        await employee_choice(e, target)
        reason = "本次PDI由明确选择的本店员工本人办理，保留原任务来源"
        await e.fill('#modal [name="reason"]', reason, "填写本次真实责任交接原因")
        old = S.task(S.facts(e, key), task_key)
        guard = Guard(e, "task_handoff", manager, fixture["store_id"], case_id=key,
            append={"flow_events", "audit_logs"}, update={"flow_tasks": {old["id"]: {"version", "updated_at", "assignee_id"}}})
        assign_path = f'/api/flow/tasks/{old["id"]}/assign'
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == assign_path) as submitted:
            _, response_meta, _ = await native_submit(e, assign_path, 200, case_id=key)
        assign_request = (await submitted.value).request.post_data_json
        require(assign_request == {"version": old["version"], "assignee_id": target["id"], "reason": reason}, "原AssignInput封包不是精确三字段")
        changed = S.task(S.facts(e, key), task_key)
        require(changed["id"] == old["id"] and changed["assignee_id"] == target["id"] and changed["version"] > old["version"], "原责任交接未改变明确任务")
        event = S.facts(e, key)["events"][-1]
        require(event["action"] == "reassign" and event["actor_id"] == manager["id"]
            and event["detail"] == {"task_id": old["id"], "from": old["assignee_id"], "to": target["id"], "reason": reason}, "原转交追加事件不符")
        meta.update(native_handoff=response_meta, handoff_guard=guard.finish())
        require(response_meta["request_id_sha256"] is None and response_meta["submitted_version"] == old["version"], "AssignInput必须沿原三字段CAS且无request_id")
    actor, view = await detail_as(e, context, credentials, fixture, role, key)
    actual = S.task(S.facts(e, key), task_key)
    require(actual["assignee_id"] == actor["id"] and actual["role"] == role, "不是原当前待办负责人")
    meta["current_task_version"] = actual["version"]
    return actor, view, meta


def receipt(e, key, actor, request, operation):
    rows = e.db.rows("SELECT * FROM flow_request_receipts WHERE request_key=?", (request["request_id"],))
    payload = {k: v for k, v in request.items() if k != "request_id"}
    if operation == "sales_quote_create":
        for field in ("customer_name", "customer_phone", "confirm_new_customer"):
            payload.pop(field, None)
    require(len(rows) == 1 and rows[0]["case_id"] == key and rows[0]["actor_id"] == actor["id"]
        and rows[0]["store_id"] == one(e, "flow_cases", key)["store_id"] and rows[0]["digest"] == F.digest(operation, payload), "原请求回执身份/内容摘要不符")
    return {"id": rows[0]["id"], "case_id": key, "actor_id": actor["id"], "store_id": rows[0]["store_id"],
        "digest": rows[0]["digest"], "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest()}


async def upload(e, fixture, key, actor, category, token, text, source_file=None):
    guard = Guard(e, "file_" + token, actor, fixture["store_id"], case_id=key, append=FILES)
    file, meta = await S.upload(e, key, actor, category, token + "-" + uuid.uuid4().hex[:12] + ".txt", text, source_file=source_file)
    blob = one(e, "flow_files", file["id"])["content"]
    require(isinstance(blob, bytes), "原附件储存字段必须为字节")
    if blob:
        require(len(blob) == file["size"] and hashlib.sha256(blob).hexdigest() == file["sha256"], "原附件内联储存字节与元数据不匹配")
    # A private-object FileAsset may keep b'' in SQLite; its actual UI download
    # proves the stored object bytes, rather than treating b'' as a fake payload.
    async with e.page.expect_download() as ready:
        await e.click(f'#main .filerecord [data-act="downloadfile"][data-id="{file["id"]}"]', "下载本步原独立凭据核对实际储存字节")
    folder = e.directory / "downloaded-inputs"
    folder.mkdir(exist_ok=True)
    downloaded = folder / file["name"]
    await (await ready.value).save_as(str(downloaded))
    actual = downloaded.read_bytes()
    require(len(actual) == file["size"] and hashlib.sha256(actual).hexdigest() == file["sha256"], "原UI下载凭据与实际上传字节不一致")
    protected = guard.finish()
    require(len(protected["appended_ids"]["flow_files"]) == len(protected["appended_ids"]["file_security"])
        == len(protected["appended_ids"]["file_scan_events"]) == 1, "本步独立凭据未唯一追加")
    require(len(protected["appended_ids"]["flow_events"]) == 1 and len(protected["appended_ids"]["audit_logs"]) == 2, "一次上传和一次下载必须各有唯一原审计")
    audits = [one(e, "audit_logs", i) for i in protected["appended_ids"]["audit_logs"]]
    downloads = [r for r in audits if r["action"] == "download"]
    require(len(downloads) == 1 and downloads[0]["reason"] == "下载文件 " + str(file["id"])
        and json.loads(downloads[0]["before_data"]) is None and json.loads(downloads[0]["after_data"]) is None
        and len([r for r in audits if r["action"] == "flow_upload"]) == 1, "原下载或上传审计未精确绑定本文件")
    meta["source_guard"] = protected
    meta["stored_blob"] = {"length": len(blob), "sha256": hashlib.sha256(blob).hexdigest(), "private_object_when_empty": not bool(blob)}
    meta["native_download"] = {"path": str(downloaded), "length": len(actual), "sha256": hashlib.sha256(actual).hexdigest()}
    meta["native_download"]["audit_id"] = downloads[0]["id"]
    return file, meta


async def generate(e, fixture, key, actor, kind):
    guard = Guard(e, "generate_" + kind, actor, fixture["store_id"], case_id=key, append=FILES)
    file, meta = await S.generate(e, key, actor, kind)
    meta["source_guard"] = guard.finish()
    return file, meta


async def command(e, fixture, key, actor, action, *, fills=None, selects=(), lookups=(), append=(), car=None, account=None, hold=False, position=False, callback=False):
    before = S.facts(e, key)
    await S.action_form(e, action)
    for field, value in (fills or {}).items():
        await e.fill(f'#modal [name="{field}"]', str(value), "填写明确原事实 " + field)
    for field, value in selects:
        await select_value(e, f'#modal [name="{field}"]', value, "选择本版原来源 " + field)
    for field, label, value in lookups:
        await live_choice(e, field, label, label, expected_value=value)
    guard = Guard(e, action, actor, fixture["store_id"], case_id=key,
        append=COMMON | set(append), update=mutable(e, key, car=car, account=account, hold=hold, position=position), new_kind="callback" if callback else None)
    _, view, meta, request = await S.original_write(e, f"/api/flow/cases/{key}/actions/{action}", 200, case_id=key)
    after = S.facts(e, key)
    S.appended(before, after)
    event = new_event(before, after, action, actor["id"])
    require(request["version"] == before["case"]["version"] and after["case"]["version"] == view["version"], "原业务CAS错误")
    meta.update(event_id=event["id"], actor_id=actor["id"], request_values=request["values"],
        receipt=receipt(e, key, actor, request, f"{key}:{action}"), source_guard=guard.finish())
    return after, view, meta


def native_parent(meta, path, event, actor):
    native = meta["native"]
    require(native["path"] == path and native["status"] == 200 and native["native_ui"] is True
        and native["cookie_present"] and native["csrf_present"] and native["request_id_sha256"]
        and meta["event"]["id"] == event["id"] and meta["event"]["actor_id"] == actor
        and native["source_guard"]["protected_old_rows_and_other_stores"] is True, "父原点击/来源守卫证据不完整")


async def addon_read_closure(e, context, credentials, fixture, reports, cp):
    cp.start("HK-065")
    parent = reports[F.SCENARIO]
    evidence = S.checkpoint_evidence(parent, "HK-012")
    sources = parent["report_sources"]
    key = sources["addon_case_id"]
    require(key == evidence["case_id"] and sources["vehicle_id"] == reports[S.SCENARIO]["report_sources"]["delivered_vehicle_id"], "本轮加装没有明确已交付原VIN")
    parent_root = Path(e.manifest["evidence_root"]) / F.SCENARIO
    actions_raw = (parent_root / "actions.json").read_bytes()
    actions = json.loads(actions_raw)
    parent_row = next(r for r in parent["requirements"] if r["id"] == "HK-012")
    start, end = parent_row["evidence_action_start"], parent_row["evidence_action_end"]
    require(0 <= start < end <= len(actions) and sum(a["kind"] == "click" for a in actions[start:end]) >= 10, "加装父缺实际完整点击范围")
    dispatch, move = evidence["dispatch"], evidence["stock_move"]
    installation, quality = evidence["installation"], evidence["quality"]
    rectification, acceptance = evidence["rectification"], evidence["acceptance"]
    link, payment, cash = evidence["payment_link"], evidence["addon_payment"], evidence["cash"]
    require([q["check"]["passed"] for q in quality] == [0, 1] and installation["dispatch_id"] == dispatch["id"]
        and installation["quantity_milli"] == dispatch["quantity_milli"] == 1000
        and rectification["inspection_id"] == quality[0]["check"]["id"]
        and all(q["check"]["installation_id"] == installation["id"] for q in quality), "原加装安装/失败整改/复检链错误")
    for table, row in (("addon_dispatches", dispatch), ("flow_stock_moves", move), ("addon_installations", installation),
        ("addon_rectifications", rectification), ("addon_acceptances", acceptance), ("flow_payment_links", link), ("addon_payments", payment), ("cash_entries", cash)):
        current = one(e, table, row["id"])
        require(all(current[k] == value for k, value in row.items()), "已完成加装原事实被覆盖：" + table)
    for q in quality:
        require(one(e, "addon_inspections", q["check"]["id"]) == q["check"], "原加装检查历史被覆盖")
    for entry in evidence["warehouse_entries"]:
        require(one(e, "warehouse_entries", entry["id"]) == entry and entry["stock_move_id"] == move["id"], "原加装库位分录与实际出库源不符")
    for table, field in (("addon_quotes", "quote"), ("addon_lines", "line")):
        require(one(e, table, evidence[field]["id"]) == evidence[field], "原加装本版商品/报价历史被覆盖")
    approved, authorized = evidence["native_approve"], evidence["native_authorize"]
    require(approved["event"]["actor_id"] != authorized["event"]["actor_id"], "原加装批准与客户授权必须不同员工")
    target = one(e, "addon_targets", evidence["target"]["id"])
    vehicle = one(e, "vehicles", sources["vehicle_id"])
    require(target["vehicle_id"] == vehicle["id"] and target["vin"] == vehicle["vin"] and dispatch["target_id"] == target["id"]
        and dispatch["stock_move_id"] == move["id"] and move["item_id"] == sources["material_item_id"]
        and move["quantity_milli"] == -1000 and acceptance["amount_cents"] == link["amount_cents"] == cash["amount_cents"] == 3500
        and acceptance["value_cents"] == dispatch["value_cents"] and payment["payment_link_id"] == link["id"]
        and cash["direction"] == link["direction"] == "in", "加装本店实车/商品/原成本/履约/现金不匹配")
    native = {"approve": approved, "authorize": authorized, "dispatch": evidence["native_dispatch"], "install": evidence["native_install"], "rectify": evidence["native_rectify"],
        "accept": evidence["native_accept"], "receive": evidence["native_receive"]}
    native.update({"quality_" + str(i): q["native"] for i, q in enumerate(quality)})
    for action, meta in native.items():
        actual = "quality" if action.startswith("quality_") else action
        event = one(e, "flow_events", meta["event"]["id"])
        role = {"approve": "manager", "authorize": "sales", "dispatch": "inventory", "install": "technician",
            "quality": "service", "rectify": "technician", "accept": "sales", "receive": "finance"}[actual]
        actor_id = e.manifest["users"][fixture[role + "_key"]]["id"]
        require(event["case_id"] == key and event["action"] == "addon_" + actual and event["actor_id"] == actor_id, "原加装点击事件串单/岗位")
        native_parent(meta, f"/api/addon-orders/{key}/actions/{actual}", event, actor_id)
        original_receipt = one(e, "addon_receipts", meta["receipt_id"])
        require(original_receipt["actor_id"] == actor_id and original_receipt["store_id"] == fixture["store_id"]
            and json.loads(original_receipt["result"])["id"] == key
            and hashlib.sha256(original_receipt["request_key"].encode()).hexdigest() == meta["native"]["request_id_sha256"], "父原点击缺同请求唯一本人回执")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/addon-orders/{key}") as ready:
        manager = await real_login(e, fixture, "manager", lambda: login_as(e, context, credentials, fixture["manager_key"], f"addon-orders/{key}", fixture["store_id"]))
    response = await ready.value
    view = await response.json()
    require(manager["role"] == "manager" and response.status == 200 and view["id"] == key and view["state"] == "completed", "当次原加装详情未显示完成原单")
    before = e.business_snapshot("before_pdi_addon_readonly_closure")
    await expect(e.page.locator("#main h1")).to_have_text("销售加装明细")
    await expect(e.page.locator("#main")).to_contain_text(vehicle["vin"])
    await expect(e.page.locator("#main")).to_contain_text("原领料批次 " + str(dispatch["id"]))
    batch = e.page.locator("#main .panel").filter(has=e.page.locator("h2").filter(has_text=re.compile(r"^实际安装批次 " + str(installation["id"]) + r"$")))
    await expect(batch).to_contain_text(installation["result"])
    for q in quality:
        await expect(batch).to_contain_text(q["check"]["result"])
    await expect(batch).to_contain_text("已整改并完成复检")
    require(view["totals"]["paid_cents"] == 3500 and view["totals"]["receivable_cents"] == view["totals"]["refund_due_cents"] == 0, "加装当前原资金读取错误")
    await F.refresh(e, "addon", key)
    e.business_unchanged(before, "after_pdi_addon_readonly_closure")
    cp.active["conditional_checks"] = [{"check_id": "HK-065-blocking-before-delivery", "status": "not_tested", "reason": "该真实父为交付后非阻断加装；不证明交车前阻断、拆回或赠送"}]
    await cp.passed(case_id=key, finite_parent_original_clicks={"scenario": F.SCENARIO, "range": [start, end],
        "clicks": sum(a["kind"] == "click" for a in actions[start:end]), "actions_sha256": hashlib.sha256(actions_raw).hexdigest()},
        native_actions=native, dispatch=dispatch, stock_move=move, warehouse_entries=evidence["warehouse_entries"],
        installation=installation, quality=quality, rectification=rectification, acceptance=acceptance, payment_link=link, cash=cash,
        original_page={"route": f"addon-orders/{key}", "get_status": 200, "vehicle_id": vehicle["id"], "vin": vehicle["vin"]},
        readonly_original_business_unchanged=True)


async def create_order(e, context, credentials, fixture, customer, source):
    sales = await real_login(e, fixture, "sales", lambda: login_as(e, context, credentials, fixture["sales_key"], "sales-quotes", fixture["store_id"]))
    await expect(e.page.locator("#main h1")).to_have_text("车辆报价与预订")
    await e.click('#main [data-act="sales-quote-new"]', "同轮已知客户建立新PDI车辆报价")
    await expect(e.page.locator("#modal-title")).to_have_text("新建预订合同")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/customer-choice/matches"
        and parse_qs(urlsplit(r.url).query).get("q") == [customer["name"]]) as matches:
        await e.fill('#modal [name="customer_name"]', customer["name"], "查本店明确本人客户")
    response = await matches.value
    body = await response.json()
    require(response.status == 200 and any(c["id"] == customer["id"] for c in body["items"]), "当前客户不在原本人候选")
    choice = f'#modal [data-quote-customers] [data-customer-id="{customer["id"]}"]'
    await expect(e.page.locator(choice)).to_be_visible()
    await e.click(choice, "真实选择本店客户，未新建或猜填客户")
    await expect(e.page.locator('#modal [name="customer_phone"]')).to_have_value(customer["phone"])
    await S.fill_quote(e, source["model"], 13000000, "合成PDI订单130000元，仅整车价；无加装保险代办，分两笔收款。")
    guard = Guard(e, "quote_create", sales, fixture["store_id"], append=COMMON | FILES | {"flow_cases", "sales_quotes", "business_entity_case_contexts"}, new_kind="order")
    body, view, meta, request = await S.original_write(e, "/api/sales-quotes/orders", 201)
    key = body["id"]
    facts = S.facts(e, key)
    quote = facts["quotes"][0]
    require(request["customer_id"] == customer["id"] and request["lead_id"] is None and request["lead_version"] is None
        and quote["amount_cents"] == 13000000 and quote["model_id"] == source["model"]["id"] and quote["revision"] == 1
        and facts["case"]["flow_version"] == 4 and facts["case"]["parent_id"] is None
        and facts["case"]["customer_id"] == customer["id"] and facts["case"]["owner_id"] == sales["id"]
        and not any(quote["services"].values()) and not facts["payments"] and not facts["holds"], "原新单身份/本版车型/金额或服务不符")
    meta.update(receipt=receipt(e, key, sales, request, "sales_quote_create"), source_guard=guard.finish())
    return key, quote, meta


async def prepare_signed_order(e, context, credentials, fixture, key, quote, source):
    manager, _, approve_owner = await responsible(e, context, credentials, fixture, key, "quote_approve", "manager")
    require(manager["id"] != one(e, "sales_quotes", quote["id"])["actor_id"], "报价不得本人自批")
    facts, _, approved = await command(e, fixture, key, manager, "quote_approve", fills={"reason": "独立核准本版车型130000元及无配套条件"}, append={"sales_quote_reviews"})
    require(len(facts["reviews"]) == 1 and facts["reviews"][0]["decision"] == "approved" and facts["reviews"][0]["actor_id"] == manager["id"], "原本版独立价格批准错误")
    inventory, _, allocate_owner = await responsible(e, context, credentials, fixture, key, "allocate", "inventory")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/sales-quotes/orders/{key}/vehicles") as ready:
        await S.action_form(e, "allocate")
    response = await ready.value
    candidates = await response.json()
    matching = [r for r in candidates["items"] if r["id"] == source["vehicle"]["id"]]
    require(response.status == 200 and len(matching) == 1 and source["vehicle"]["vin"] in matching[0]["label"], "原可用配车候选未含有限采购VIN")
    await select_value(e, '#modal [name="vehicle"]', matching[0]["label"], "明确同轮退订释放的第二VIN")
    before = S.facts(e, key)
    guard = Guard(e, "allocate", inventory, fixture["store_id"], case_id=key, append=COMMON | {"flow_vehicle_holds"}, update=mutable(e, key, car=source["vehicle"]["id"]))
    _, _, allocated, request = await S.original_write(e, f"/api/flow/cases/{key}/actions/allocate", 200, case_id=key)
    after = S.facts(e, key)
    S.appended(before, after)
    event = new_event(before, after, "allocate", inventory["id"])
    require(request["values"] == {"vehicle_id": source["vehicle"]["id"]} and request["version"] == before["case"]["version"], "原配车未精确选择当前VIN/CAS")
    allocated.update(event_id=event["id"], receipt=receipt(e, key, inventory, request, f"{key}:allocate"), source_guard=guard.finish())
    S.physical(e, source, state="stored", case_id=key)
    await S.stock_ui(e, source, "reserved", "已预订")
    sales, _, sign_owner = await responsible(e, context, credentials, fixture, key, "sign", "sales")
    document, generated = await generate(e, fixture, key, sales, "contract")
    file, uploaded = await upload(e, fixture, key, sales, "signed_contract", "pdi-contract", "合成客户签回本版130000元和明确VIN " + source["vehicle"]["vin"], document)
    facts, _, signed = await command(e, fixture, key, sales, "sign", append={"sales_quote_consents", "sales_quote_resolutions"}, lookups=[("evidence_id", file["name"] + " · 合同签回件", file["id"])])
    consent = facts["consents"][-1]
    require(consent["quote_id"] == quote["id"] and consent["vehicle_id"] == source["vehicle"]["id"] and consent["source_file_id"] == document["id"]
        and consent["evidence_id"] == file["id"] and consent["fingerprint"] == document["source_fingerprint"]
        and facts["case"]["data"]["active_quote_id"] == quote["id"] and facts["case"]["data"]["pending_quote_id"] is None, "本版合同签回未绑定真实报价/VIN/源字节")
    return {"approve_owner": approve_owner, "approve": approved, "allocate_owner": allocate_owner, "allocate": allocated,
        "sign_owner": sign_owner, "generated_contract": generated, "signed_file": uploaded, "sign": signed, "consent": consent}


async def double_submit(e, path, key, store):
    observed = []
    def collect(response):
        if response.request.method == "POST" and urlsplit(response.url).path == path:
            observed.append(response)
    e.page.on("response", collect)
    try:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/sales-quotes/orders/{key}") as rendered:
            async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
                submit = e.page.locator('#modal form button[type="submit"]')
                await expect(submit).to_be_visible()
                await expect(submit).to_be_enabled()
                e.action("click", "原生收款连续点击第1次", native_click_index=1, native_click_count=2)
                e.action("click", "原生收款连续点击第2次", native_click_index=2, native_click_count=2)
                await submit.dblclick()
            response = await pending.value
            body = await response.json()
            require(response.status == 200, "原分笔到账HTTP" + str(response.status) + "：" + e.scrub(body.get("detail", "")))
        read = await rendered.value
        view = await read.json()
        require(read.status == 200 and view["id"] == key and len(observed) == 1, "原UI连续点击产生重复提交或未读取本单")
        headers = await response.request.all_headers()
        request = response.request.post_data_json
        require(headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-store-id") == str(store), "原分笔到账缺同源Cookie/CSRF/本店")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main h1")).to_have_text("预订合同 · " + view["number"])
        return body, view, {"path": path, "method": "POST", "status": 200, "native_ui": True,
            "cookie_present": True, "csrf_present": True, "native_click_count": 2, "observed_post_count": 1,
            "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest(),
            "render_get_path": urlsplit(read.url).path, "render_get_status": 200, "backend_raw_replay_tested": False}, request
    finally:
        e.page.remove_listener("response", collect)


async def payment(e, context, credentials, fixture, key, account, amount, reference, correct, token):
    finance, _, owner = await responsible(e, context, credentials, fixture, key, "receive", "finance")
    file, proof = await upload(e, fixture, key, finance, "receipt", "pdi-payment-" + token,
        f"事前合成银行凭据编号 {correct}；明确本次到账{amount}分、账户{account['id']}。本输入用于合成更正边界，不代表真实银行。")
    before = S.facts(e, key)
    await S.action_form(e, "receive")
    await expect(e.page.locator('#modal [name="amount"]')).to_have_value(S.fen_text(13000000 - sum(p["amount_cents"] for p in before["payments"])))
    await e.fill('#modal [name="amount"]', S.fen_text(amount), "登记该笔实际到账金额")
    await e.fill('#modal [name="reference"]', reference, "登记事前说明中的本笔员工录入编号")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    await live_choice(e, "evidence_id", file["name"] + " · 收退款凭据", file["name"] + " · 收退款凭据", expected_value=file["id"])
    guard = Guard(e, "receive_" + token, finance, fixture["store_id"], case_id=key,
        append=COMMON | {"flow_payment_links", "cash_entries", "business_entity_cash_contexts"}, update=mutable(e, key, account=account["id"]))
    _, view, meta, request = await double_submit(e, f"/api/flow/cases/{key}/actions/receive", key, fixture["store_id"])
    facts = S.facts(e, key)
    S.appended(before, facts)
    event = new_event(before, facts, "receive", finance["id"])
    require(request["version"] == before["case"]["version"] and request["values"] == {"amount": S.fen_text(amount), "account_id": account["id"], "reference": reference, "evidence_id": file["id"]}
        and event["detail"]["amount"] == amount, "原分笔到账输入字符串/后端整分/来源/CAS错误")
    require(len(facts["payments"]) == len(before["payments"]) + 1 and len(facts["cash"]) == len(before["cash"]) + 1, "UI连续点击未唯一追加原款及现金")
    link, cash = facts["payments"][-1], facts["cash"][-1]
    require(link["cash_id"] == cash["id"] and link["direction"] == cash["direction"] == "in" and link["amount_cents"] == cash["amount_cents"] == amount
        and link["account_id"] == account["id"] and link["reference"] == cash["voucher_no"] == reference and cash["account"] == account["name"]
        and link["original_id"] is None and cash["created_by"] == finance["id"] and cash["approval_state"] == "approved" and cash["category"] == "workflow_order", "原分笔账户、流水、金额或本人现金错误")
    paid = sum(p["amount_cents"] for p in facts["payments"])
    require(view["amount_cents"] == 13000000 and view["paid_cents"] == paid and 0 <= paid <= 13000000, "当次原GET累计金额不符")
    for label, cents in (("当前约定价款", 13000000), ("已收及已抵用", paid)):
        card = e.page.locator("#main .card").filter(has_text=label)
        await expect(card).to_have_count(1)
        await expect(card.locator("strong")).to_have_text(S.displayed_money(cents))
    await expect(e.page.locator("#main")).to_contain_text(reference)
    require((S.task(facts, "receive")["status"] == "open") if paid < 13000000 else not any(t["key"] == "receive" and t["status"] == "open" for t in facts["tasks"]), "分笔后原收款待办状态错误")
    meta.update(event_id=event["id"], actor_id=finance["id"], receipt=receipt(e, key, finance, request, f"{key}:receive"), source_guard=guard.finish())
    await S.refresh(e, key)
    return {"task_owner": owner, "proof": proof, "native": meta, "payment_link": link, "cash": cash,
        "paid_cents": paid, "remaining_cents": 13000000 - paid, "reference": reference, "correct_synthetic_bank_reference": correct}


async def original_case(e, key, label):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/flow/cases/{key}") as ready:
        e.action("navigate", label, route=f"case/{key}")
        await e.page.goto(e.origin + f"/#case/{key}", wait_until="domcontentloaded")
    response = await ready.value
    view = await response.json()
    current = S.facts(e, key)["case"]
    require(response.status == 200 and view["id"] == key and view["version"] == current["version"], "原只读页面未读取同单当前CAS")
    await expect(e.page.locator("#main h1")).to_have_text(current["title"])
    return view


async def generic_inspection(e, key, expected, result, round_no):
    before = e.business_snapshot("before_pdi_read_inspection_banner")
    await original_case(e, key, "打开原流程检查摘要")
    await expect(e.page.locator("#main")).to_contain_text(expected)
    await expect(e.page.locator("#main")).to_contain_text("第 " + str(round_no) + " 轮检查")
    await expect(e.page.locator("#main")).to_contain_text(result)
    e.business_unchanged(before, "after_pdi_read_inspection_banner")
    return {"get_path": f"/api/flow/cases/{key}", "status": 200, "visible_warning": expected, "round": round_no, "readonly_business_unchanged": True}


async def blocked_dispatch(e, context, credentials, fixture, key, source):
    inventory, view, owner = await responsible(e, context, credentials, fixture, key, "dispatch", "inventory")
    before = e.business_snapshot("before_pdi_blocked_dispatch")
    actions = [a for a in view["actions"] if a["key"] == "dispatch"]
    require(len(actions) == 1 and actions[0]["enabled"] is False
        and actions[0]["reason"] == "交车检查尚未合格，须处理缺陷并复检通过", "原GET未按PDI检查失败阻断，或混入他人任务/资金原因")
    button = e.page.locator('#main [data-act="sales-quote-action"][data-key="dispatch"]')
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        details = button.locator("xpath=ancestor::details[1]")
        await expect(details).to_have_count(1)
        e.action("click", "展开原发车阻断说明")
        await details.locator(":scope > summary").click()
    await expect(button).to_be_visible()
    await expect(button).to_be_disabled()
    await expect(e.page.locator("#main")).to_contain_text(actions[0]["reason"])
    require(not any(v["action"] in {"dispatch", "deliver"} for v in S.facts(e, key)["events"])
        and not e.db.rows("SELECT id FROM vehicle_position_entries WHERE case_id=?", (key,)), "PDI失败期间存在原发车/交车事实")
    S.physical(e, source, state="stored", case_id=key)
    e.business_unchanged(before, "after_pdi_blocked_dispatch")
    return {"actor_id": inventory["id"], "task_owner": owner, "reason": actions[0]["reason"], "native_dispatch_button_disabled": True,
        "no_forced_click_or_post": True, "position_unchanged": True, "backend_direct_refusal_tested": False}


async def pdi_steps(e, context, credentials, fixture, key, source, cp):
    proofs, steps = [], []
    for action, role, outcome, result in (
        ("inspect", "service", "不合格", "合成PDI右前灯固定松动，禁止发车，待技师整改"),
        ("rectify", "technician", None, "按第一轮明确缺陷重新紧固右前灯，等待服务顾问独立复检"),
        ("reinspect", "service", "合格", "同VIN右前灯紧固及全部交车条件复检合格")):
        actor, _, owner = await responsible(e, context, credentials, fixture, key, action, role)
        file, proof = await upload(e, fixture, key, actor, "inspection", "pdi-" + action, source["vehicle"]["vin"] + "；" + result)
        fills = {"result": result}
        facts, _, meta = await command(e, fixture, key, actor, action, fills=fills,
            selects=[("outcome", outcome)] if outcome else [], lookups=[("evidence_id", file["name"] + " · 检测记录", file["id"])])
        data = facts["case"]["data"]
        require(data["inspection"]["vehicle_id"] == source["vehicle"]["id"] and data["inspection"]["round"] == (2 if action == "reinspect" else 1)
            and data["inspection_status"] == {"inspect": "failed", "rectify": "awaiting_reinspection", "reinspect": "passed"}[action], "原PDI轮次、状态或VIN不符")
        if action == "rectify":
            require(data["rectification"]["inspection_round"] == 1 and data["rectification"]["evidence_id"] == file["id"] and data["inspection"]["outcome"] == "不合格", "整改冒充复检或未绑定第一轮")
        else:
            require(data["inspection"]["outcome"] == outcome and data["inspection"]["evidence_id"] == file["id"], "原检查结果凭据不符")
        require(any(t["key"] == action and t["status"] == "done" and t["done_by"] == actor["id"] for t in facts["tasks"]), "原PDI本人任务未办结")
        proofs.append(proof)
        step = {"action": action, "task_owner": owner, "native": meta, "current_inspection": data["inspection"], "status": data["inspection_status"]}
        if action != "reinspect":
            warning = "检查不合格，禁止出库" if action == "inspect" else "缺陷已处理，等待复检"
            step["banner"] = await generic_inspection(e, key, warning, data["inspection"]["result"], 1)
            step["blocked_dispatch"] = await blocked_dispatch(e, context, credentials, fixture, key, source)
        steps.append(step)
        cp.note(case_id=key, pdi_steps=steps, inspection_files=proofs)
    require(len({p["file"]["id"] for p in proofs}) == 3 and len({p["file"]["sha256"] for p in proofs}) == 3, "三步PDI不得借同一原件")
    return steps, proofs


async def deliver(e, context, credentials, fixture, key, source):
    inventory, _, owner = await responsible(e, context, credentials, fixture, key, "dispatch", "inventory")
    file, proof = await upload(e, fixture, key, inventory, "evidence", "pdi-dispatch", "本次同VIN复检合格后实际发车 " + source["vehicle"]["vin"])
    facts, _, dispatched = await command(e, fixture, key, inventory, "dispatch", lookups=[("evidence_id", file["name"] + " · 业务凭据", file["id"])],
        append={"vehicle_position_entries"}, car=source["vehicle"]["id"], position=True)
    entries = e.db.rows("SELECT * FROM vehicle_position_entries WHERE case_id=? ORDER BY id", (key,))
    require(len(entries) == 1 and entries[0]["kind"] == "sale_dispatch" and entries[0]["quantity"] == -1 and entries[0]["inventory_delta"] == 0
        and entries[0]["value_cents"] == -source["vehicle"]["purchase_cost_cents"] and entries[0]["vehicle_id"] == source["vehicle"]["id"]
        and entries[0]["store_id"] == fixture["store_id"] and entries[0]["location_id"] == source["original_position"]["location_id"]
        and entries[0]["actor_id"] == inventory["id"] and entries[0]["evidence_id"] == file["id"]
        and entries[0]["original_id"] is None and facts["case"]["state"] != "delivered", "发车库存流水或尚未交车事实不符")
    S.physical(e, source, state="handover", case_id=key)
    sales, _, deliver_owner = await responsible(e, context, credentials, fixture, key, "deliver", "sales")
    document, generated = await generate(e, fixture, key, sales, "handover")
    signed, signature = await upload(e, fixture, key, sales, "signed_handover", "pdi-handover", "本版同VIN已合格、款齐并真实客户接车 " + source["vehicle"]["vin"], document)
    facts, view, delivered = await command(e, fixture, key, sales, "deliver", lookups=[("evidence_id", signed["name"] + " · 提车签回件", signed["id"])],
        append={"flow_cases"}, car=source["vehicle"]["id"], position=True, hold=True, callback=True)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    require(facts["case"]["state"] == "delivered" and facts["case"]["completed_date"] == day.isoformat() and view["paid_cents"] == 13000000
        and all(t["status"] != "open" for t in facts["tasks"]), "最终原交车、到账或待办不完整")
    S.physical(e, source, state="exited", case_id=key, delivered=True)
    require(e.db.rows("SELECT * FROM vehicle_position_entries WHERE case_id=? ORDER BY id", (key,)) == entries, "提车重复记实际出库")
    await S.refresh(e, key)
    callbacks = e.db.rows("SELECT * FROM flow_cases WHERE parent_id=? AND kind='callback'", (key,))
    require(len(callbacks) == 1 and callbacks[0]["customer_id"] == facts["case"]["customer_id"] and callbacks[0]["due_date"] == (day + timedelta(days=3)).isoformat(), "原交车回访来源未真实生成")
    callback = callbacks[0]
    callback.pop("data")
    before = e.business_snapshot("before_pdi_final_customer_callback_read")
    await original_case(e, key, "查看同VIN新订单的原客户与回访来源")
    await expect(e.page.locator("#main")).to_contain_text(one(e, "flow_customers", facts["case"]["customer_id"])["name"])
    route = f'case/{callback["id"]}'
    selector = f'#main [data-act="open"][data-route="{route}"]'
    await expect(e.page.locator(selector)).to_have_count(1)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f'/api/flow/cases/{callback["id"]}') as ready:
        await e.click(selector, "打开本次交车的真实原回访来源，未提交回访")
    response = await ready.value
    callback_view = await response.json()
    require(response.status == 200 and callback_view["id"] == callback["id"] and callback_view["customer_id"] == facts["case"]["customer_id"], "最后原客户回访读取串单")
    await expect(e.page.locator("#main h1")).to_have_text(callback["title"])
    callback_tasks = e.db.rows("SELECT id,case_id,key,title,role,status,assignee_id,due_date FROM flow_tasks WHERE case_id=?", (callback["id"],))
    require(len(callback_tasks) == 1 and callback_tasks[0]["status"] == "open" and callback_tasks[0]["due_date"] == callback["due_date"], "原回访仅生成待办，不能冒充员工已完成")
    await expect(e.page.locator("#main")).to_contain_text(callback_tasks[0]["title"])
    e.business_unchanged(before, "after_pdi_final_customer_callback_read")
    return {"dispatch_owner": owner, "dispatch_proof": proof, "native_dispatch": dispatched, "position_entry": entries[0],
        "deliver_owner": deliver_owner, "generated_handover": generated, "signed_handover": signature, "native_deliver": delivered,
        "case": facts["case"], "callback": callback, "callback_tasks": callback_tasks, "customer_callback_readonly_business_unchanged": True}


async def sales_pdi_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, reports, customer, supplier, model, warehouse, location, account = dependencies(e, cp)
        token = uuid.uuid4().hex[:14]
        source, purchase = await AR.vehicle_precondition(e, context, credentials, fixture, supplier, model, warehouse, location, account, "PDI-" + token)
        source = dict(source, original_position=source["position"])
        require(source["vehicle"]["id"] != cp.report["source_preconditions"]["historical_cancelled_vehicle"]["id"]
            and source["vehicle"]["approval_state"] == "approved", "PDI必须使用原UI独立验收的当前实车")
        S.physical(e, source, state="stored")
        cp.report["necessary_original_ui_new_vehicle_purchase"] = purchase
        cp.save()
        folder = e.directory / "synthetic-inputs"
        folder.mkdir(exist_ok=True)
        declaration = {"schema": 1, "scenario": SCENARIO, "synthetic_only": True, "declared_before_new_order_ui": True,
            "quote_amount_cents": 13000000, "account_id": account["id"], "customer_id": customer["id"], "vehicle_id": source["vehicle"]["id"],
            "first": {"amount_cents": 5000000, "correct_bank_reference": "PDI-" + token + "-BANK-01", "deliberate_entry_reference": "PDI-" + token + "-ENTRY-01"},
            "second": {"amount_cents": 8000000, "reference": "PDI-" + token + "-BANK-02"}, "correction_in_this_candidate": False}
        require(declaration["first"]["correct_bank_reference"] != declaration["first"]["deliberate_entry_reference"], "合成事前误记说明不能相同")
        path = folder / "payment-declaration.json"
        raw = (json.dumps(declaration, ensure_ascii=False, indent=2) + "\n").encode()
        path.write_bytes(raw)
        cp.report["synthetic_payment_declaration"] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "length": len(raw), **declaration}
        cp.save()
        await addon_read_closure(e, context, credentials, fixture, reports, cp)
        cp.start("HK-037")
        key, quote, created = await create_order(e, context, credentials, fixture, customer, source)
        cp.note(case_id=key, quote=quote, native_create=created, original_vehicle=source)
        signed = await prepare_signed_order(e, context, credentials, fixture, key, quote, source)
        cp.note(signed_order=signed)
        cp.start("HK-075")
        first = declaration["first"]
        pay1 = await payment(e, context, credentials, fixture, key, account, first["amount_cents"], first["deliberate_entry_reference"], first["correct_bank_reference"], "first")
        require(pay1["paid_cents"] == 5000000 and pay1["remaining_cents"] == 8000000, "第一笔累计和尚欠错误")
        cp.note(case_id=key, first_payment=pay1, declaration=cp.report["synthetic_payment_declaration"])
        second = declaration["second"]
        pay2 = await payment(e, context, credentials, fixture, key, account, second["amount_cents"], second["reference"], second["reference"], "second")
        require(pay2["paid_cents"] == 13000000 and pay2["remaining_cents"] == 0 and pay1["native"]["receipt"]["id"] != pay2["native"]["receipt"]["id"]
            and pay1["native"]["request_id_sha256"] != pay2["native"]["request_id_sha256"] and pay1["cash"]["id"] != pay2["cash"]["id"], "两笔原款没有独立回执/现金或未结清")
        cp.active["conditional_checks"] = [{"check_id": "HK-075-backend-replay", "status": "not_tested", "reason": "真实UI连续点击仅发一个原请求，没有raw正向重放"},
            {"check_id": "HK-078-correction", "status": "not_tested", "reason": "本批只事前声明并原UI误录第一笔凭据编号，原款保持；更正另批"}]
        await cp.passed(case_id=key, first_payment=pay1, second_payment=pay2, paid_cents=13000000, remaining_cents=0, original_account={"id": account["id"], "name": account["name"]})
        cp.start("HK-037")
        steps, proofs = await pdi_steps(e, context, credentials, fixture, key, source, cp)
        closure = await deliver(e, context, credentials, fixture, key, source)
        await cp.passed(case_id=key, pdi_steps=steps, inspection_files=proofs, delivery=closure, original_vehicle=source,
            quote=quote, signed_order=signed, original_payments=[pay1["payment_link"], pay2["payment_link"]])
        cp.finish({"customer_id": customer["id"], "pdi_order_id": key, "pdi_order_number": closure["case"]["number"],
            "vehicle_id": source["vehicle"]["id"], "vin": source["vehicle"]["vin"], "quote_id": quote["id"], "account_id": account["id"],
            "independent_purchase_case_id": purchase["case_id"], "original_purchase_cost_cents": source["vehicle"]["purchase_cost_cents"],
            "addon_case_id": reports[F.SCENARIO]["report_sources"]["addon_case_id"], "callback_case_id": closure["callback"]["id"],
            "first_payment_link_id": pay1["payment_link"]["id"], "first_cash_id": pay1["cash"]["id"], "first_receipt_id": pay1["native"]["receipt"]["id"],
            "first_evidence_id": pay1["proof"]["file"]["id"], "first_correct_bank_reference": first["correct_bank_reference"],
            "first_misrecorded_reference": first["deliberate_entry_reference"], "second_payment_link_id": pay2["payment_link"]["id"], "second_cash_id": pay2["cash"]["id"],
            "declaration_path": str(path), "declaration_sha256": hashlib.sha256(raw).hexdigest(), "correction_executed": False})
    except Exception as error:
        cp.failed(error)
        raise


SALES_PDI_SCENARIOS = ((SCENARIO, sales_pdi_business, 720),)
