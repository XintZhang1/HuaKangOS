"""Original repair/claims UI: independent assessments, results and actual receipts.

Only the current run's fixed passed checkpoints supply existing identities.
All new business facts are created by visible original forms; SQL is read-only.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import SCENARIO as PRESALES, login_as, require
from sales_order_business import SCENARIO as SALE, fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import SCENARIO as PURCHASE, master_form, live_choice, select_value, checkbox
from master_data_business import save_typed
from repair_business import (
    SCENARIO as FIRST_REPAIR, CUSTOMER, MASTER, MATERIAL, PRIMARY_KEYS, Guard,
    CASE_FIELDS, TASK_FIELDS, COMMON, INTAKE, REPAIR, one, case_facts, facts, task,
    event_added, mutable, submit, read_as, responsible, upload, file_choice, form, command,
    material_facts,
)
from repair_followon_business import (
    Checkpoint as FollowonCheckpoint, CLAIMS, claim_facts,
    claim_responsible, claim_form, claim_file_choice, zero_nav, reveal,
)

SCENARIO = "repair-claims-hk035-036-039-040-041"
CONTRACTS = (
    ("HK-035", "保险理赔维修", ["本次新到店、原维修本版授权和真实施工质检", "保险当前核价及获准结果绑定原承担，财务真实到账与接车分开"]),
    ("HK-036", "厂家索赔维修", ["原厂家和当前维修第二行独立核价及获准结果", "厂家承担、当前版本绑定与实际到账、原接车对应"]),
    ("HK-039", "保险账核价单", ["初版独立复核、补件精确旧结果、拒赔与新版部分核准完整保留", "原行数量金额、不同凭据及双版本/回执，不产生提前现金"]),
    ("HK-040", "索赔账核价单", ["本店启用厂家、原第二行核价、不同主管批准和实际外部批准结果", "原报价摘要、提交/结果/版本及金额一致，不把核准当到账"]),
    ("HK-041", "内部账核价单", ["真实内部主体及原第三行核价、不同主管批准和唯一内部承担绑定", "不产生外部提交、结果、内部现金或客户报销"]),
)
PARENTS = (PRESALES, PURCHASE, MASTER, CUSTOMER, SALE, MATERIAL, FIRST_REPAIR)
KEYS = {**PRIMARY_KEYS, **{t: "id" for t in (
    "flow_references", "master_work_items", "master_receipts", "claims_orders",
    "claims_assessments", "claims_approvals", "claims_transmissions", "claims_results",
    "claims_bindings", "claims_request_receipts",
)}}
HISTORY = ("assessments", "approvals", "transmissions", "results", "bindings", "cash", "customer_payments", "reimbursement_approvals")


class Checkpoint(FollowonCheckpoint):
    def __init__(self, e):
        super().__init__(e, SCENARIO, CONTRACTS)
        self.report["candidate_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.report["conditions"].update(actual_manufacturer_certification=False)
        self.report["planned_pending"] = [
            {"id": key, "status": "not_tested", "reason": "返修、PDI或原误记更正属于后继独立来源批次"}
            for key in ("HK-037", "HK-038", "HK-075", "HK-076", "HK-078", "HK-081")]
        self.save()


class ClaimsGuard:
    """Whole-business hashes plus exact permitted old IDs/columns and new sources.

    BLOBs stay in this in-memory comparison; reports contain IDs/columns only.
    No table is excluded merely because one new claim uses that table.
    """
    def __init__(self, e, label, actor, store, *, append, update=None, cases=(),
                 source_id=None, new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store
        self.append, self.update = set(append), update or {}
        self.cases, self.source, self.kind = set(cases), source_id, new_kind
        require((self.append | self.update.keys()) <= KEYS.keys(), "核赔守卫存在未核准表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: self.rows(t) for t in self.append | self.update.keys()}

    def rows(self, table):
        return self.e.db.rows(f"SELECT * FROM {table} ORDER BY {KEYS[table]}")

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "核赔改变无关业务表：" + str(sorted(changed)))
        owned = set(self.cases)
        if "flow_cases" in self.append:
            old_ids = {r["id"] for r in self.old["flow_cases"]}
            new = [r for r in self.rows("flow_cases") if r["id"] not in old_ids]
            require(len(new) == 1 and new[0]["kind"] == self.kind
                    and new[0]["created_by"] == self.actor["id"]
                    and new[0]["parent_id"] == self.source, "核赔创建错误/多余原单")
            owned.add(new[0]["id"])
        added_ids, updates = {}, {}
        for table, old in self.old.items():
            pk = KEYS[table]
            current = {r[pk]: r for r in self.rows(table)}
            old_ids = {r[pk] for r in old}
            updates[table] = []
            for row in old:
                require(row[pk] in current, "核赔删除原事实：" + table)
                columns = {k for k in row if row[k] != current[row[pk]][k]}
                require(columns <= self.update.get(table, {}).get(row[pk], set()),
                        "核赔覆盖未授权旧行/列：" + table + "/" + str(row[pk]))
                if columns:
                    updates[table].append({"id": row[pk], "columns": sorted(columns)})
            new = [r for k, r in current.items() if k not in old_ids]
            require(not new or table in self.append, "只允许更新的表出现新行：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "核赔新增事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "核赔新增事实串单：" + table)
                for key in ("actor_id", "created_by"):
                    if key in row:
                        require(row[key] == self.actor["id"], "核赔新增事实串员工：" + table)
                if "source_case_id" in row:
                    require(row["source_case_id"] == self.source, "核赔引用错误原维修")
                if "quote_id" in row:
                    require(one(self.e, "repair_quotes", row["quote_id"])["case_id"] == self.source, "核赔引用错误报价")
                if "assessment_id" in row:
                    require(one(self.e, "claims_assessments", row["assessment_id"])["case_id"] in owned, "核赔引用错误核价")
                if "allocation_id" in row:
                    require(one(self.e, "repair_allocations", row["allocation_id"])["case_id"] == self.source, "核赔引用错误承担")
                if table == "claims_orders":
                    require(row["id"] in owned and row["payment_route"] in {"repair_receivable", "internal"}, "核赔混入客户报销路径")
            added_ids[table] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": added_ids, "updated_columns": updates,
                  "all_unrelated_old_rows_and_other_stores_unchanged": True}
        self.e.observe("claims_original_row_guard", {"label": self.label, **result})
        return result


def dependencies(e, checkpoint):
    require(e.manifest.get("synthetic_data_only") is True, "核赔只允许本次合成外置运行")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "核赔数据库不在同次runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance.get("snapshot_stable") is True, "核赔镜像未冻结")
    for name in ("repair_claims_business.py", "repair_business.py", "repair_followon_business.py", "sales_business.py",
                 "sales_order_business.py", "vehicle_purchase_business.py", "master_data_business.py", "material_business.py",
                 "customer_service_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "核赔脚本指纹改变：" + name)
    checkpoint.report["mirror"] = {"sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": provenance["source_sha256"],
                                   "script_sha256": provenance["script_sha256"]}
    parents = {name: fixed_dependency(e, checkpoint, name) for name in PARENTS}
    fixture = dict(e.manifest["business_fixtures"]["repair"])
    for role in ("service", "manager", "technician", "finance", "inventory"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role, "核赔缺原岗位：" + role)
        links = e.db.rows("SELECT * FROM user_stores WHERE user_id=? AND store_id=?", (actor["id"], fixture["store_id"]))
        require(len(links) == 1 and links[0]["role"] == role
                and one(e, "users", actor["id"])["active"], "核赔原员工缺当前店真实岗位")
    s = dict(parents[FIRST_REPAIR]["report_sources"])
    vehicle, customer = one(e, "care_customer_vehicles", s["customer_vehicle_id"]), one(e, "flow_customers", s["customer_id"])
    care = next(r for r in parents[CUSTOMER]["partial_requirements"] if r["id"] == "HK-099")
    require(care["local_scope_status"] == "local_scope_passed", "客服原车辆局部来源未实际通过")
    for key in ("id", "customer_id", "store_id", "vin", "customer_identity_id", "vehicle_identity_id"):
        require(vehicle[key] == care["evidence"]["vehicle"][key], "核赔原客车身份改变：" + key)
    original = facts(e, s["repair_case_id"])
    require(original["case"]["state"] == "completed" and original["binding"][0]["vin"] == vehicle["vin"] == s["vin"]
            and vehicle["active"] and vehicle["customer_id"] == customer["id"]
            and vehicle["store_id"] == customer["store_id"] == fixture["store_id"], "核赔首维修未接车或客户/VIN/当前店错误")
    work = one(e, "master_work_items", checkpoint_evidence(parents[MASTER], "HK-175")["row"]["id"])
    insurer = one(e, "master_insurers", checkpoint_evidence(parents[MASTER], "HK-172")["row"]["id"])
    require(work["active"] and insurer["active"] and work["store_id"] == insurer["store_id"] == fixture["store_id"], "核赔原主档未启用或串店")
    primary = parents[MATERIAL]["material_sources"]["primary"]
    require(primary["item_id"] == s["material_item_id"], "核赔材料背景与首维修不同源")
    current_material = material_facts(e, primary["item_id"])
    require(one(e, "flow_items", primary["item_id"])["store_id"] == fixture["store_id"], "原材料串店")
    fixture["account_id"] = checkpoint_evidence(parents[PURCHASE], "HK-021")["payment"]["account_id"]
    account = one(e, "flow_accounts", fixture["account_id"])
    require(account["active"] and account["account_type"] == "bank" and account["store_id"] == fixture["store_id"]
            and one(e, "flow_payment_links", s["payment_link_id"])["account_id"] == account["id"], "核赔原账户不是同轮采购和首维修实际资金源")
    require(not e.db.rows("SELECT m.id FROM group_members m JOIN group_identity_links l ON l.identity_id=m.identity_id "
        "WHERE l.local_kind='customer' AND l.local_id=? AND l.store_id=? AND m.active=1", (customer["id"], fixture["store_id"])),
        "本批核赔客户存在另需核对的会员消费来源")
    checkpoint.report["source_preconditions"] = {"first_repair_sources": s, "current_customer_vehicle": vehicle,
        "current_customer": customer, "original_completed_repair_id": original["case"]["id"], "insurer": insurer,
        "original_work_item": work, "current_material": current_material, "current_account": account,
        "synthetic_declared_inputs": {"arrival_odometer_km": 35000, "work_amounts_cents": [3000, 4000, 5000],
            "labor_cost_cents": 3000, "allocations_cents": {"customer": 1000, "insurer": 2000, "manufacturer": 4000, "internal": 5000}},
        "no_old_cv_or_material_version_equality": True}
    checkpoint.save()
    return fixture, vehicle, customer, insurer


def receipt(e, request, actor, result, action, *, source_id=None, claim_id=None):
    require(isinstance(request.get("request_id"), str) and len(request["request_id"]) >= 16, "核赔缺原请求编号")
    if claim_id is not None:
        table, purpose = "claims_request_receipts", "claims_" + action
        values = dict(request["values"])
        if action == "transmit":
            values.setdefault("supplement_result_id", None)  # Original Transmission schema's explicit default.
        payload = {"case_id": claim_id, "version": request["version"], "source_version": request["source_version"], "values": values}
    elif source_id is not None:
        table, purpose = "flow_request_receipts", "repair_v3_" + action  # Original family also covers flow v4.
        values = dict(request["values"])
        if action == "allocate":
            values["allocations"] = [{"payer_id": None, "payer_name": "", **r} for r in values["allocations"]]
        payload = {"id": source_id, "version": request["version"], "values": values}
    else:
        table, purpose = "claims_request_receipts", "claims_create"
        payload = {k: v for k, v in request.items() if k != "request_id"}
    found = e.db.rows(f"SELECT * FROM {table} WHERE request_key=?", (request["request_id"],))
    digest = hashlib.sha256(json.dumps({"operation": purpose, "payload": payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["digest"] == digest,
            "原核赔/维修回执家族、内容或身份错误")
    if table == "claims_request_receipts":
        require(json.loads(found[0]["result"]) == result, "核赔回执未保存本次原返回")
    else:
        require(found[0]["case_id"] == source_id == result["id"], "维修回执关联错误原单")
    return {"id": found[0]["id"], "family": table, "digest": digest, "request_id": request["request_id"], "actor_id": actor["id"]}


def immutable_prefix(before, after):
    require(after["order"] == before["order"], "核赔覆盖原单位/维修身份")
    for key in HISTORY + ("events",):
        require(after[key][:len(before[key])] == before[key], "核赔覆盖原历史：" + key)


async def claim_command(e, fixture, claim_id, source_id, action, actor):
    before, source = claim_facts(e, claim_id), facts(e, source_id)
    role = "manager" if action == "approve" else "service"
    key = "claim_handle" if action == "assess" and before["case"]["data"]["phase"] == "ready" else "claim_" + action
    owner = task(before, key)
    require(owner["role"] == actor["role"] == role and owner["assignee_id"] == actor["id"], "核价没有原岗位本人任务来源")
    append = {"flow_tasks", "flow_events", "audit_logs", "claims_request_receipts"}
    append |= {"assess": {"claims_assessments"}, "approve": {"claims_approvals"},
               "transmit": {"claims_transmissions"}, "result": {"claims_results"}}[action]
    protection = ClaimsGuard(e, "claims_" + action, actor, fixture["store_id"], append=append,
        update={**mutable(e, claim_id), "flow_cases": {claim_id: CASE_FIELDS, source_id: {"version", "updated_at"}}},
        cases={claim_id}, source_id=source_id)
    body, view, native, request = await submit(e, f"{CLAIMS}/{claim_id}/actions/{action}", f"{CLAIMS}/{claim_id}", fixture["store_id"], protection=protection)
    require(request["version"] == before["case"]["version"] and request["source_version"] == source["case"]["version"], "核赔提交缺真实双版本")
    after, current_source = claim_facts(e, claim_id), facts(e, source_id)
    immutable_prefix(before, after)
    require(after["case"]["version"] > before["case"]["version"] and current_source["case"]["version"] > source["case"]["version"]
            and body["id"] == view["id"] == claim_id and body["source_id"] == source_id
            and body["source_version"] == current_source["case"]["version"], "核赔返回未绑定当前原单/来源版本")
    require(all(current_source[k] == source[k] for k in ("quotes", "lines", "approvals", "authorizations", "stock", "quality", "settlements", "allocations", "payments", "cash")), "核价提前改变施工、承担、库存或现金")
    require(not after["bindings"] and not after["cash"] and not after["customer_payments"] and not after["reimbursement_approvals"], "本核价阶段错误产生绑定/报销/现金")
    native.update(receipt=receipt(e, request, actor, body, action, claim_id=claim_id),
                  event=event_added(before, after, "claims_" + action, actor), submitted_values=request["values"])
    await expect(e.page.locator("#main h1")).to_have_text(body["title"])
    return after, native


async def configured(e, context, credentials, fixture, token):
    manager = await login_as(e, context, credentials, fixture["manager_key"], "masters/work_items", fixture["store_id"])
    await expect(e.page.locator("#main h1")).to_have_text("作业项目")
    works, native = [], []
    for index, fee in enumerate((3000, 4000, 5000), 1):
        await master_form(e, "work_items", "作业项目")
        values = {"code": "CL" + str(index) + token, "name": "合成核赔作业" + str(index) + token,
                  "active": True, "billing_unit": "job", "standard_minutes": 20,
                  "standard_fee_cents": fen_text(fee), "warranty_days": 0}
        guard = ClaimsGuard(e, "claim_create_work_" + str(index), manager, fixture["store_id"],
                            append={"master_work_items", "master_receipts", "audit_logs"})
        work, created = await save_typed(e, manager, fixture["store_id"], "work_items", values)
        created["source_guard"] = guard.finish()
        require(work["active"] and work["billing_unit"] == "job" and work["standard_fee_cents"] == fee
                and work["code"] == values["code"] and work["name"] == values["name"], "新核赔作业单位/明确费用错误")
        works.append(work); native.append(created)
    await zero_nav(e, "master/references", "/api/flow/master/references", "基础资料")
    await e.click('#main [data-act="newmaster"][data-kind="references"]', "主管原UI新增本次厂家往来档案")
    await expect(e.page.locator("#modal-title")).to_have_text("新增基础资料")
    await select_value(e, '#modal [name="category"]', "厂家", "明确原厂家类别")
    name = "合成核赔厂家" + token
    await e.fill('#modal [name="name"]', name, "填写本次明确厂家名称")
    await e.fill('#modal [name="detail"]', "仅本次合成厂家维修核价，不代表实际厂家核准", "说明合成厂家用途")
    await checkbox(e, '#modal [name="active"]', True, "明确启用原厂家档案")
    guard = ClaimsGuard(e, "claim_create_manufacturer", manager, fixture["store_id"], append={"flow_references", "audit_logs"})
    body, listing, reference_native, request = await submit(e, "/api/flow/master/references", "/api/flow/master/references",
        fixture["store_id"], 201, protection=guard)
    manufacturer = one(e, "flow_references", body["id"])
    require(manufacturer["category"] == "厂家" and manufacturer["name"] == name and manufacturer["active"]
            and manufacturer["store_id"] == fixture["store_id"]
            and request["values"]["category"] == "厂家"
            and any(r["id"] == manufacturer["id"] for r in listing["items"]), "真实原厂家类别/列表错误")
    await expect(e.page.locator("#main tbody tr").filter(has=e.page.locator(f'[data-act="editmaster"][data-id="{manufacturer["id"]}"]'))).to_contain_text(name)
    await zero_nav(e, "service-intake/resources", INTAKE + "/catalog", "工位与快捷项目")
    await e.click('#main [data-act="intake-resource-new"]', "主管新增本次核赔实际工位")
    for key, value in (("code", "CR" + token), ("name", "合成核赔工位" + token)):
        await e.fill(f'#modal [name="{key}"]', value, "填写明确本次核赔工位")
    await select_value(e, '#modal [name="type"]', "维修", "选择实际维修工位类型")
    guard = Guard(e, "claim_create_resource", manager, fixture["store_id"], append={"intake_resources", "intake_command_receipts"})
    created, _, resource_native, _ = await submit(e, INTAKE + "/resources", INTAKE + "/catalog", fixture["store_id"], 201, protection=guard)
    resource = one(e, "intake_resources", created["id"])
    require(resource["active"] and resource["resource_type"] == "repair" and resource["active_case_id"] is None, "新核赔工位非真实空闲维修工位")
    return works, manufacturer, resource, {"work_creation": native, "manufacturer": reference_native, "resource": resource_native}


async def new_repair(e, context, credentials, fixture, vehicle, customer, resource, works, token):
    store, day = fixture["store_id"], datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    service = await login_as(e, context, credentials, fixture["service_key"], "service-intake/appointments", store)
    await expect(e.page.locator("#main h1")).to_have_text("维修预约与到店")
    await e.click('#main [data-act="intake-new"][data-mode="walk_in"]', "服务顾问原UI登记本次核赔现场来访")
    label = " · ".join(str(v) for v in (customer["name"], customer["phone"], vehicle["plate"], vehicle["vin"]) if v)
    await live_choice(e, "customer_vehicle_id", vehicle["vin"], label, expected_value=vehicle["id"])
    await live_choice(e, "resource_id", resource["name"], resource["name"], expected_value=resource["id"])
    for field in ("starts_at", "ends_at"):
        await e.fill(f'#modal [name="{field}"]', await e.page.locator(f'#modal [name="{field}"]').input_value(), "明确本次现场来访时段")
    await e.fill('#modal [name="reason"]', "本次合成三项独立核损，逐位核对原车辆后实际维修", "填写本次实际来访问题")
    guard = Guard(e, "claim_book_new_intake", service, store,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_appointments", "intake_command_receipts", "business_entity_case_contexts"},
        update={"intake_resources": {resource["id"]: {"updated_at", "version"}}}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="service_intake")
    booked, _, book_native, request = await submit(e, INTAKE + "/appointments", INTAKE + "/appointments/*", store, 201, protection=guard)
    appointment_id, intake_id = booked["id"], booked["case_id"]
    require(request["mode"] == "walk_in" and request["preset_id"] is None and request["customer_vehicle_id"] == vehicle["id"]
            and request["resource_id"] == resource["id"], "新核赔来访不是本车无快捷组合的regular接待")
    service, _, arrive_owner = await responsible(e, context, credentials, fixture, intake_id, "intake_arrive", "service", appointment_id=appointment_id)
    odo = 35000  # Explicit synthetic on-site reading for this new Arrival, not a guessed CV column.
    proof = await upload(e, intake_id, service, "evidence", "claims-arrival-" + token + ".txt", f"本次独立合成现场核VIN {vehicle['vin']}，里程{odo}。", store)
    await form(e, "arrive", intake=True)
    await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "现场逐位核对原VIN")
    await e.fill('#modal [name="odometer_km"]', str(odo), "登记本次明确现场里程")
    await file_choice(e, "evidence_id", proof)
    guard = Guard(e, "claim_actual_arrival", service, store,
        append={"flow_tasks", "flow_events", "audit_logs", "intake_arrivals", "intake_command_receipts"},
        update={**mutable(e, intake_id, vehicle_id=vehicle["id"]), "intake_appointments": {appointment_id: {"status", "version", "updated_at"}}},
        cases={intake_id}, vehicle_id=vehicle["id"])
    _, _, arrived_native, _ = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/arrive", f"{INTAKE}/appointments/{appointment_id}", store, protection=guard)
    arrivals = e.db.rows("SELECT * FROM intake_arrivals WHERE appointment_id=? ORDER BY id", (appointment_id,))
    require(len(arrivals) == 1 and arrivals[0]["checked_vin"] == vehicle["vin"] and arrivals[0]["odometer_km"] == odo
            and arrivals[0]["customer_vehicle_id"] == vehicle["id"] and arrivals[0]["evidence_id"] == proof["file"]["id"]
            and arrivals[0]["actor_id"] == service["id"], "新到店没有本次真实唯一Arrival来源")
    service, _, convert_owner = await responsible(e, context, credentials, fixture, intake_id, "intake_convert", "service", appointment_id=appointment_id)
    await form(e, "convert", intake=True)
    await e.fill('#modal [name="due_date"]', day, "明确本次预计交接日")
    guard = Guard(e, "claim_convert_actual_arrival", service, store,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_command_receipts", "intake_repair_contexts", "intake_vehicle_bindings", "business_entity_case_contexts"},
        update={**mutable(e, intake_id), "intake_appointments": {appointment_id: {"status", "repair_case_id", "version", "updated_at"}}},
        cases={intake_id}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="repair")
    converted, _, convert_native, _ = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/convert", f"{INTAKE}/appointments/{appointment_id}", store, protection=guard)
    case_id = converted["repair_case_id"]
    repair = facts(e, case_id)
    require(repair["case"]["flow_version"] == 4 and repair["case"]["state"] == "assessment" and repair["case"]["customer_id"] == customer["id"]
            and repair["context"][0]["profile"] == "regular" and repair["context"][0]["appointment_id"] == appointment_id
            and repair["context"][0]["resource_id"] == resource["id"] and repair["binding"][0]["vin"] == vehicle["vin"]
            and repair["binding"][0]["customer_vehicle_id"] == vehicle["id"] and repair["binding"][0]["evidence_id"] == proof["file"]["id"]
            and not repair["quotes"] and not repair["stock"] and not repair["payments"], "新核赔转换错误或预造业务结果")
    require(all(repair["binding"][0][k] == vehicle[k] for k in ("customer_identity_id", "vehicle_identity_id"))
            and case_facts(e, intake_id)["case"]["state"] == "completed", "新维修没有冻结原身份或原接待未完成")
    service, _, quote_owner = await responsible(e, context, credentials, fixture, case_id, "repair_quote", "service")
    await form(e, "quote")
    for index, work in enumerate(works):
        if index:
            await e.click('#modal [data-act="repair-add-line"]', "增加另一个明确原核赔作业")
        line = e.page.locator('#modal [data-repair-line]').nth(index)
        e.action("fill", "查找本次明确原作业", work_item_id=work["id"])
        await line.locator('[role="combobox"]').fill(work["name"])
        choice = line.get_by_role("option", name="项目 · " + work["code"] + " " + work["name"], exact=True)
        await expect(choice).to_be_visible()
        e.action("click", "明确选择本次原作业", work_item_id=work["id"])
        await choice.click()
        await expect(line.locator('[name="source"]')).to_have_value("work:" + str(work["id"]))
        e.action("fill", "明确原作业数量与费用", work_item_id=work["id"], quantity="1.000", price=fen_text(work["standard_fee_cents"]))
        await line.locator('[name="quantity"]').fill("1.000")
        await line.locator('[name="price"]').fill(fen_text(work["standard_fee_cents"]))
    await e.fill('#modal [name="discount"]', "0.00", "明确本版没有另行优惠")
    await e.fill('#modal [name="reason"]', "本次三项实际合成核损分别30、40、50元，不领用材料", "记录本版维修诊断与报价")
    repair, _, quote_native = await command(e, fixture, case_id, "quote", service)
    quote = repair["quotes"][0]
    require(len(repair["quotes"]) == 1 and len(repair["lines"]) == 3 and quote["amount_cents"] == 12000
            and {r["work_item_id"] for r in repair["lines"]} == {w["id"] for w in works}, "本版三项核赔报价来源/金额错误")
    for work in works:
        line = next(r for r in repair["lines"] if r["work_item_id"] == work["id"])
        require(line["kind"] == "work" and line["quantity_milli"] == 1000 and line["unit"] == "job"
                and line["amount_cents"] == line["unit_price_cents"] == line["standard_fee_cents"] == work["standard_fee_cents"]
                and line["item_id"] is None and line["discount_cents"] == 0, "原核损行数量/明示价格错误")
    manager, _, price_owner = await responsible(e, context, credentials, fixture, case_id, "repair_price_" + str(quote["id"]), "manager")
    await form(e, "price_approve")
    await e.fill('#modal [name="minimum"]', "120.00", "主管独立核对三项报价合计")
    await checkbox(e, '#modal [name="allow_below_minimum"]', False, "不授权默认低价例外")
    await e.fill('#modal [name="reason"]', "不同主管逐项核对本次核损作业、数量与120元报价", "填写本次独立价格复核")
    repair, _, price_native = await command(e, fixture, case_id, "price_approve", manager)
    require(repair["approvals"][0]["actor_id"] == manager["id"] != quote["created_by"], "新核赔维修报价存在自批")
    service, _, auth_owner = await responsible(e, context, credentials, fixture, case_id, "repair_authorize_" + str(quote["id"]), "service")
    auth = await upload(e, case_id, service, "authorization", "claims-authorize-" + token + ".txt", f"本次合成客户授权原报价{quote['id']} 摘要{quote['digest']} 合计12000分。", store)
    await form(e, "authorize"); await file_choice(e, "evidence_id", auth)
    repair, _, auth_native = await command(e, fixture, case_id, "authorize", service)
    require(repair["authorizations"][0]["quote_digest"] == quote["digest"] and repair["authorizations"][0]["evidence_id"] == auth["file"]["id"], "核赔维修未授权当前版")
    technician, _, work_owner = await responsible(e, context, credentials, fixture, case_id, "repair_work", "technician")
    await form(e, "start")
    await e.fill('#modal [name="result"]', "实际核车入位，开始本版三项合成作业", "技师原UI记录实际开工")
    repair, _, start_native = await command(e, fixture, case_id, "start", technician)
    require(repair["case"]["data"].get("started") and repair["resource_uses"][0]["action"] == "acquire"
            and one(e, "intake_resources", resource["id"])["active_case_id"] == case_id, "核赔新维修未实际入位开工")
    await form(e, "finish")
    await e.fill('#modal [name="result"]', "本版三项合成作业实际完成，不领配件", "技师原UI记录实际施工完成")
    repair, _, finish_native = await command(e, fixture, case_id, "finish", technician)
    require(repair["case"]["state"] == "quality" and not repair["stock"], "核赔施工未真实完成或误生成材料")
    service, _, quality_owner = await responsible(e, context, credentials, fixture, case_id, "repair_quality", "service")
    quality = await upload(e, case_id, service, "inspection", "claims-quality-" + token + ".txt", "本次三项合成核损作业实查合格，与本版原授权一致。", store)
    await form(e, "quality")
    await e.fill('#modal [name="result"]', "本版三项原作业质量与安全检查合格", "服务顾问记录实际独立质检")
    await select_value(e, '#modal [name="outcome"]', "合格", "明确实际质检结果")
    await file_choice(e, "evidence_id", quality)
    repair, _, quality_native = await command(e, fixture, case_id, "quality", service)
    require(repair["case"]["state"] == "settling" and len(repair["quality"]) == 1 and repair["quality"][0]["passed"]
            and repair["quality"][0]["quote_id"] == quote["id"] and repair["quality"][0]["actor_id"] != technician["id"]
            and not repair["settlements"] and not repair["payments"], "核赔新单质检/未冻结承担边界错误")
    return repair, {"appointment": one(e, "intake_appointments", appointment_id), "arrival": arrivals[0],
        "files": [proof, auth, quality], "quote": quote, "lines": repair["lines"],
        "native": [book_native, arrived_native, convert_native, quote_native, price_native, auth_native, start_native, finish_native, quality_native],
        "task_owners": [arrive_owner, convert_owner, quote_owner, price_owner, auth_owner, work_owner, quality_owner]}


async def create_claim(e, context, credentials, fixture, source_id, party, payer, token):
    service, _ = await claim_source_read(e, context, credentials, fixture, source_id)
    source = facts(e, source_id)
    selector = f'#main [data-act="claim-new"][data-source="{source_id}"]'
    await reveal(e, e.page.locator(selector), "展开本维修原核赔栏目")
    await e.click(selector, "由本次原维修明确建立独立" + party + "核价")
    await expect(e.page.locator("#modal-title")).to_have_text("建立原维修核赔申请")
    source_label = str(source_id) + " · " + source["case"]["number"] + " · " + source["case"]["title"]
    await select_value(e, '#modal [name="source"]', source_label, "选择本次新维修来源")
    party_label = {"insurer": "保险 · ", "manufacturer": "厂家 · "}.get(party, "") + payer["name"] if party != "internal" else "内部承担"
    await select_value(e, '#modal [name="party"]', party_label, "明确原核价单位")
    route = "internal" if party == "internal" else "repair_receivable"
    await select_value(e, '#modal [name="route"]', "内部承担核价" if party == "internal" else "原维修第三方应收", "明确本次原结算路径")
    await e.fill('#modal [name="internal_name"]', payer["name"] if party == "internal" else "", "明确内部主体或外部留空")
    await e.fill('#modal [name="reason"]', "本次合成" + party + "核损，逐项引用本版维修费用", "填写本次独立核损依据")
    guard = ClaimsGuard(e, "claim_create_" + party, service, fixture["store_id"],
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "claims_orders", "claims_request_receipts", "business_entity_case_contexts"},
        update={"flow_cases": {source_id: {"updated_at", "version"}}}, source_id=source_id, new_kind="claim")
    body, _, native, request = await submit(e, CLAIMS, CLAIMS + "/*", fixture["store_id"], 201, protection=guard)
    f = claim_facts(e, body["id"])
    require(request["source_case_id"] == source_id and request["source_version"] == source["case"]["version"]
            and request["party_type"] == party and request["payment_route"] == route
            and f["order"]["source_case_id"] == source_id and f["order"]["payment_route"] == route
            and f["order"]["party_type"] == party and f["order"]["party_name"] == payer["name"]
            and f["case"]["flow_version"] == 2 and f["case"]["customer_id"] == source["case"]["customer_id"]
            and f["case"]["owner_id"] == f["case"]["created_by"] == service["id"]
            and f["case"]["data"]["phase"] == "assessment", "原核价创建单位/来源/路径错误")
    if party != "internal":
        require(request["payer_id"] == payer["id"] and f["order"][party + "_id"] == payer["id"], "核价外部单位ID错误")
    else:
        require(request["payer_id"] is None and request["payer_name"] == payer["name"], "内部核价没有明确主体")
    require(not f["assessments"] and not f["cash"] and not facts(e, source_id)["payments"], "创建核价预造获准或现金")
    native["receipt"] = receipt(e, request, service, body, "create")
    return f, {"create": native, "original_order": f["order"]}


async def claim_source_read(e, context, credentials, fixture, source_id):
    return await read_as(e, context, credentials, fixture, "service", f"repair-orders/{source_id}", f"{REPAIR}/{source_id}")


async def selected_line(e, line, amount, *, include=True):
    fieldsets = e.page.locator('#modal [data-claim-line]')
    require(await fieldsets.count() > 0, "原核损表单没有来源明细")
    for index in range(await fieldsets.count()):
        row = fieldsets.nth(index)
        selected = include and await row.get_attribute("data-id") == str(line["id"])
        e.action("click", "明确本次核损逐行选择", line_id=await row.get_attribute("data-id"), included=selected)
        await row.locator('[name="selected"]').set_checked(selected)
    if include:
        target = e.page.locator(f'#modal [data-claim-line][data-id="{line["id"]}"]')
        await expect(target).to_have_count(1)
        e.action("fill", "明确本次原行数量及金额", line_id=line["id"], quantity="1.000", amount_cents=amount)
        await target.locator('[name="quantity"]').fill("1.000")
        await target.locator('[name="amount"]').fill(fen_text(amount))


async def assess_approve(e, context, credentials, fixture, claim_id, source_id, line, amount, token, revision):
    current = claim_facts(e, claim_id)
    if current["case"]["data"]["phase"] == "assessment":
        service, _, assess_owner = await claim_responsible(e, context, credentials, fixture, claim_id, "claim_assess", "service")
    else:
        require(current["case"]["data"]["phase"] == "ready", "新版核价没有当前最终结果")
        service, _, assess_owner = await claim_responsible(e, context, credentials, fixture, claim_id, "claim_handle", "service")
    await claim_form(e, "assess")
    await selected_line(e, line, amount)
    await e.fill('#modal [name="reason"]', f"本次合成核价第{revision}版，只申请原行{line['id']}已知费用", "记录当前独立核价原因")
    assessed, native_assess = await claim_command(e, fixture, claim_id, source_id, "assess", service)
    a = assessed["assessments"][-1]
    quote = facts(e, source_id)["quotes"][0]
    require(len(assessed["assessments"]) == revision and a["revision"] == revision and a["amount_cents"] == amount
            and a["quote_id"] == quote["id"] and a["quote_digest"] == quote["digest"] and a["actor_id"] == service["id"]
            and len(a["lines"]) == 1 and a["lines"][0]["line_id"] == line["id"]
            and a["lines"][0]["quantity_milli"] == 1000 and a["lines"][0]["amount_cents"] == amount,
            "核价版本或当前报价/逐项数量金额错误")
    manager, _, approve_owner = await claim_responsible(e, context, credentials, fixture, claim_id, "claim_approve", "manager")
    proof = await upload(e, claim_id, manager, "authorization", f"claims-approve-{token}-{revision}.txt",
        f"本次不同主管独立复核核价{a['id']} 报价摘要{quote['digest']}，核价金额{amount}分。", fixture["store_id"])
    await claim_form(e, "approve")
    await e.fill('#modal [name="reason"]', "不同主管独立核对本版原行、数量及金额", "主管记录本次独立核价复核")
    await claim_file_choice(e, proof)
    approved, native_approve = await claim_command(e, fixture, claim_id, source_id, "approve", manager)
    p = approved["approvals"][-1]
    require(p["assessment_id"] == a["id"] and p["actor_id"] == manager["id"] != a["actor_id"]
            and manager["id"] != approved["case"]["created_by"] and p["evidence_id"] == proof["file"]["id"]
            and approved["case"]["data"]["phase"] == ("ready" if approved["order"]["party_type"] == "internal" else "send"), "原核价复核自批或未绑定当前版")
    return approved, {"assessment": a, "approval": p, "file": proof, "native": [native_assess, native_approve], "task_owners": [assess_owner, approve_owner]}


async def transmit_result(e, context, credentials, fixture, claim_id, source_id, line, outcome, amount, token, sequence, supplement=None):
    store, day = fixture["store_id"], datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    service, _, transmit_owner = await claim_responsible(e, context, credentials, fixture, claim_id, "claim_transmit", "service")
    proof = await upload(e, claim_id, service, "authorization", f"claims-send-{token}-{sequence}.txt",
        f"本次合成实际外部提交{sequence}，原核价{claim_facts(e, claim_id)['assessments'][-1]['id']}；指定补件结果{supplement}。", store)
    await claim_form(e, "transmit")
    reference = "CL-" + token + "-" + str(sequence)
    await e.fill('#modal [name="external_reference"]', reference, "记录本次独立外部受理号")
    await e.fill('#modal [name="submitted_on"]', day, "核对本次实际合成提交日")
    await claim_file_choice(e, proof)
    sent, native_send = await claim_command(e, fixture, claim_id, source_id, "transmit", service)
    transmission = sent["transmissions"][-1]
    require(transmission["supplement_result_id"] == supplement and transmission["external_reference"] == reference
            and transmission["submitted_on"] == day and transmission["evidence_id"] == proof["file"]["id"]
            and transmission["assessment_id"] == sent["assessments"][-1]["id"] and sent["case"]["data"]["phase"] == "waiting", "本次外部提交未引用正确核价或补件要求")
    if supplement is not None:
        require(native_send["submitted_values"]["supplement_result_id"] == supplement
                and next(r for r in sent["results"] if r["id"] == supplement)["outcome"] == "need_documents", "补件请求没有精确原结果关系")
    service, _, result_owner = await claim_responsible(e, context, credentials, fixture, claim_id, "claim_result", "service")
    result_proof = await upload(e, claim_id, service, "authorization", f"claims-result-{token}-{sequence}.txt",
        f"本次合成外部实际结果{outcome}；原提交{transmission['id']} 本次获准{amount}分。", store)
    await claim_form(e, "result")
    await select_value(e, '#modal [name="outcome"]', outcome, "明确本次实际外部结果")
    await selected_line(e, line, amount, include=outcome in {"approved", "partial"})
    await e.fill('#modal [name="reason"]', "本次独立合成外部结果：" + outcome + "，不代表实际保险或厂家认证", "保留本次外部结果与差异说明")
    await e.fill('#modal [name="result_on"]', day, "核对结果在提交日至本地业务今天内")
    await select_value(e, '#modal [name="evidence_id"]', str(result_proof["file"]["id"]), "明确本次独立外部结果凭据")
    result, native_result = await claim_command(e, fixture, claim_id, source_id, "result", service)
    r = result["results"][-1]
    require(r["outcome"] == outcome and r["amount_cents"] == amount and r["transmission_id"] == transmission["id"]
            and r["assessment_id"] == transmission["assessment_id"] and r["evidence_id"] == result_proof["file"]["id"]
            and r["result_on"] == day and r["actor_id"] == service["id"]
            and result["case"]["data"]["phase"] == ("supplement" if outcome == "need_documents" else "ready"), "本次核赔结果未绑定真实原提交/获准额")
    if outcome in {"need_documents", "rejected"}:
        require(r["lines"] == [] and native_result["submitted_values"]["lines"] == [], "补件或拒赔错误形成批准行")
    else:
        require(len(r["lines"]) == 1 and r["lines"][0]["line_id"] == line["id"]
                and r["lines"][0]["quantity_milli"] == 1000 and r["lines"][0]["amount_cents"] == amount, "当前实际获准行数量/金额错误")
    return result, {"transmission": transmission, "result": r, "files": [proof, result_proof],
        "native": [native_send, native_result], "task_owners": [transmit_owner, result_owner]}


async def coupled_command(e, fixture, source_id, claims, action, actor):
    """Original repair transaction may legitimately advance its three bound claims."""
    before = facts(e, source_id)
    role = "manager" if action == "allocate" else "finance"
    if action == "allocate":
        owner = task(before, "repair_allocate")
    else:
        selected = e.page.locator('#modal [name="amount"]')
        await expect(selected).to_be_visible()
        open_tasks = [t for t in before["tasks"] if t["status"] == "open" and t["key"].startswith("repair_receive_")
                      and t["assignee_id"] == actor["id"]]
        require(open_tasks, "本次到账缺原财务本人待办")
        owner = None  # The exact allocation/task is checked against the captured original submission below.
    require(actor["role"] == role and (owner is None or owner["role"] == role and owner["assignee_id"] == actor["id"]), "原承担/到账未由岗位本人办理")
    originals = {key: claim_facts(e, key) for key in claims}
    appended = COMMON | {"flow_tasks"} | {
        "allocate": {"repair_settlements", "repair_allocations", "claims_bindings"},
        "receive": {"repair_payments", "flow_payment_links", "cash_entries"},
    }[action]
    update = mutable(e, source_id,
        account_id=int(await e.page.locator('#modal [name="account_id"]').input_value()) if action == "receive" else None)
    for key in claims:
        update["flow_cases"][key] = {"state", "data", "version", "updated_at", "completed_date"}
        update["flow_tasks"].update({t["id"]: TASK_FIELDS for t in originals[key]["tasks"]})
    guard = ClaimsGuard(e, "repair_claims_" + action, actor, fixture["store_id"], append=appended,
                        update=update, cases={source_id, *claims}, source_id=source_id)
    body, view, native, request = await submit(e, f"{REPAIR}/{source_id}/actions/{action}", f"{REPAIR}/{source_id}", fixture["store_id"], protection=guard)
    if action == "receive":
        owner = task(before, "repair_receive_" + str(request["values"]["allocation_id"]))
        require(owner["role"] == "finance" and owner["assignee_id"] == actor["id"], "实际到账提交与原承担财务任务错配")
    after = facts(e, source_id)
    require(request["version"] == before["case"]["version"] and body["id"] == view["id"] == source_id
            and body["version"] == after["case"]["version"] > before["case"]["version"], "原核赔承担/到账缺真实维修版本或结果")
    for k in ("id", "number", "kind", "flow_version", "store_id", "customer_id", "created_by"):
        require(after["case"][k] == before["case"][k], "核赔承担或到账替换维修身份：" + k)
    for k in ("quotes", "lines", "approvals", "authorizations", "quality", "settlements", "allocations", "payments", "repair_payments", "stock", "moves"):
        require(after[k][:len(before[k])] == before[k], "核赔承担或到账覆盖原历史：" + k)
    for key in claims:
        current = claim_facts(e, key)
        immutable_prefix(originals[key], current)
        require(not current["cash"] and not current["customer_payments"] and not current["reimbursement_approvals"], "原承担到账被误记为客户报销或ClaimCash")
    native.update(receipt=receipt(e, request, actor, body, action, source_id=source_id),
        event=event_added(before, after, "repair_v4_" + action, actor), submitted_values=request["values"])
    await expect(e.page.locator("#main h1")).to_have_text(body["title"])
    return after, view, native


async def allocate_receive_release(e, context, credentials, fixture, source_id, claims, payer_sources, token):
    store, day = fixture["store_id"], datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    declaration_dir = Path(e.manifest["evidence_root"]) / SCENARIO / "synthetic-inputs"
    declaration_dir.mkdir(parents=True, exist_ok=True)
    declaration_path = declaration_dir / "customer-payment-declaration.json"
    declaration = {"schema": 1, "synthetic": True, "correction_executed": False,
        "store_id": store, "repair_case_id": source_id, "customer_id": payer_sources["customer"]["id"],
        "account_id": fixture["account_id"], "amount_cents": 1000, "business_date": day,
        "correct_bank_reference": "BANK-CL-" + token, "misrecorded_reference": "ENTRY-CL-" + token}
    require(not facts(e, source_id)["payments"] and declaration["correct_bank_reference"] != declaration["misrecorded_reference"],
            "误录输入必须在本次原修单任何到账前明确")
    declaration_path.write_text(json.dumps(declaration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    declared_source = {"path": str(declaration_path), "sha256": hashlib.sha256(declaration_path.read_bytes()).hexdigest(), **declaration}
    e.observe("claims_customer_payment_declaration", declared_source)
    manager, _, allocate_owner = await responsible(e, context, credentials, fixture, source_id, "repair_allocate", "manager")
    proof = await upload(e, source_id, manager, "evidence", "claims-allocation-" + token + ".txt",
        "本次合成客户10/保险20/厂家40/内部50元，人工成本明确30元，各方结果分别核对。", store)
    await form(e, "allocate")
    await expect(e.page.locator('#modal [data-repair-customer-all]')).not_to_be_enabled()
    allocations = {"customer": 1000, "insurer": 2000, "manufacturer": 4000, "internal": 5000}
    for party, amount in allocations.items():
        if party != "customer":
            await e.click(f'#modal [data-repair-add-payer="{party}"]', "明确增加本次原" + party + "承担")
            await expect(e.page.locator(f'#modal [data-repair-payer="{party}"]')).to_be_visible()
            await expect(e.page.locator(f'#modal [data-repair-payer="{party}"]')).not_to_be_disabled()
            if party != "internal":
                payer = payer_sources[party]
                await live_choice(e, "payer_" + party, payer["name"], payer["name"], expected_value=payer["id"])
            else:
                await e.fill('#modal [name="internal_name"]', payer_sources[party]["name"], "填写已核内部主体")
        await e.fill(f'#modal [name="amount_{party}"]', fen_text(amount), "按实际核价和客户授权明确承担额")
        await e.fill(f'#modal [name="due_{party}"]', day, "明确本次承担期限")
    await e.fill('#modal [name="labor_cost"]', "30.00", "填写事先明确本批合成人工成本")
    await file_choice(e, "evidence", proof)
    repair, view, allocated = await coupled_command(e, fixture, source_id, claims, "allocate", manager)
    require(len(repair["settlements"]) == 1 and len(repair["allocations"]) == 4 and not repair["stock"] and not repair["payments"]
            and repair["settlements"][0]["quote_id"] == repair["quotes"][0]["id"]
            and repair["settlements"][0]["labor_cost_cents"] == repair["case"]["cost_cents"] == 3000
            and repair["case"]["amount_cents"] == 12000 and view["revenue_cents"] == 7000
            and sum(a["amount_cents"] for a in repair["allocations"] if a["payer_type"] != "internal") == 7000,
            "核赔承担冻结数量、原成本、外部收入或提前现金错误")
    by_party = {a["payer_type"]: a for a in repair["allocations"]}
    require(set(by_party) == set(allocations) and sum(a["amount_cents"] for a in by_party.values()) == 12000,
            "四原承担不能恰好覆盖授权金额")
    for party, amount in allocations.items():
        a = by_party[party]
        require(a["amount_cents"] == amount and a["payer_name"] == payer_sources[party]["name"] and a["due_date"] == day,
                "原承担单位/金额/期限错误：" + party)
        if party in {"insurer", "manufacturer"}:
            require(a[party + "_id"] == payer_sources[party]["id"], "原承担档案ID错误")
    bound = {}
    for claim_id, party in claims.items():
        f = claim_facts(e, claim_id)
        require(len(f["bindings"]) == 1, "原allocate没有唯一自动核价绑定")
        b, a = f["bindings"][0], f["assessments"][-1]
        require(b["assessment_id"] == a["id"] and b["allocation_id"] == by_party[party]["id"]
                and b["approved_cents"] == allocations[party] and f["order"]["source_case_id"] == source_id,
                "自动绑定未引用当前核价版/原承担")
        require(b["result_id"] == (None if party == "internal" else f["results"][-1]["id"]), "自动绑定借用错误旧核赔结果")
        require(f["case"]["data"]["phase"] == ("completed" if party == "internal" else "bound"), "内部零应收或外部应收阶段错误")
        if party == "internal":
            require(not f["transmissions"] and not f["results"] and not f["cash"]
                    and all(t["status"] != "open" for t in f["tasks"]), "内部核价伪造外部事实或留下应收")
        bound[party] = {"case_id": claim_id, "binding": b, "phase": f["case"]["data"]["phase"]}
    due = {a["payer_type"]: a["due_cents"] for a in view["allocations"]}
    require(due == {"customer": 1000, "insurer": 2000, "manufacturer": 4000, "internal": 0}
            and view["customer_due_cents"] == 1000 and view["receivable_cents"] == 7000,
            "实际核价绑定后应收不能由获准文字替代到账")
    receipt_history, owners = [], [allocate_owner]
    for party in ("customer", "insurer", "manufacturer"):
        a, amount = by_party[party], allocations[party]
        finance, _, receive_owner = await responsible(e, context, credentials, fixture, source_id, "repair_receive_" + str(a["id"]), "finance")
        reference = declaration["misrecorded_reference"] if party == "customer" else "CL-PAY-" + party + "-" + token
        proof_text = (f"本次合成实际客户到账1000分，银行原凭证{declaration['correct_bank_reference']}；"
            f"原表故意误录{reference}，为后继独立更正输入，本批未办理更正。") if party == "customer" else (
            f"本次合成实际{party}到账{amount}分，独立凭证{reference}；不是核价批准。")
        payment_proof = await upload(e, source_id, finance, "evidence", "claims-pay-" + party + "-" + token + ".txt",
            proof_text, store)
        selector = f'#main [data-act="repair-action"][data-key="receive"][data-id="{a["id"]}"]'
        await expect(e.page.locator(selector)).to_be_visible()
        await expect(e.page.locator(selector)).to_be_enabled()
        await e.click(selector, "财务本人登记指定原承担方实际到账")
        await expect(e.page.locator("#modal-title")).to_have_text("登记实际到账")
        await e.fill('#modal [name="amount"]', fen_text(amount), "核对本次真实承担方到账额")
        account_source = one(e, "flow_accounts", fixture["account_id"])
        await live_choice(e, "account_id", account_source["name"], account_source["name"], expected_value=account_source["id"])
        account_id = int(await e.page.locator('#modal [name="account_id"]').input_value())
        account = one(e, "flow_accounts", account_id)
        require(account["id"] == fixture["account_id"] and account["active"] and account["store_id"] == store
                and account["account_type"] == "bank", "实际到账账户不是同轮本店原启用银行账户")
        await e.fill('#modal [name="reference"]', reference, "填写本次独立原流水号")
        await file_choice(e, "evidence_id", payment_proof)
        old = facts(e, source_id)
        repair, view, received = await coupled_command(e, fixture, source_id, claims, "receive", finance)
        require(len(repair["payments"]) == len(old["payments"]) + 1 and len(repair["cash"]) == len(old["cash"]) + 1
                and len(repair["repair_payments"]) == len(old["repair_payments"]) + 1
                and received["submitted_values"]["allocation_id"] == a["id"], "实际一次到账重复/缺失或串承担")
        p, link, cash = repair["repair_payments"][-1], repair["payments"][-1], repair["cash"][-1]
        require(p["allocation_id"] == a["id"] and p["payment_link_id"] == link["id"] and p["evidence_id"] == payment_proof["file"]["id"]
                and link["case_id"] == source_id and link["cash_id"] == cash["id"]
                and link["direction"] == cash["direction"] == "in" and link["amount_cents"] == cash["amount_cents"] == amount
                and link["account_id"] == account_id and cash["account"] == account["name"] and cash["created_by"] == finance["id"]
                and link["business_date"] == cash["business_date"] == day and link["reference"] == cash["voucher_no"] == reference
                and cash["approval_state"] == "approved" and link["original_id"] is None
                and not repair["case"]["data"].get("released_date"), "实际到账原款/凭据/账户/未交车独立事实错误")
        require(next(x for x in view["allocations"] if x["id"] == a["id"])["due_cents"] == 0, "实收后当前承担欠额未消除")
        if party != "customer":
            claim_id = next(key for key, value in claims.items() if value == party)
            f = claim_facts(e, claim_id)
            require(f["case"]["data"]["phase"] == "completed" and all(t["status"] != "open" for t in f["tasks"]), "对应核赔未随真实原承担到账结束")
        receipt_history.append({"party_type": party, "allocation": a, "repair_payment": p, "payment_link": link,
            "cash": cash, "file": payment_proof, "native": received, "remaining_receivable_cents": view["receivable_cents"]})
        owners.append(receive_owner)
    require(view["customer_due_cents"] == view["receivable_cents"] == 0
            and sum(c["amount_cents"] for c in repair["cash"]) == 7000 and repair["case"]["state"] == "settling", "全到账未守恒或提前交车")
    service, _, release_owner = await responsible(e, context, credentials, fixture, source_id, "repair_release", "service")
    release_proof = await upload(e, source_id, service, "evidence", "claims-release-" + token + ".txt",
        "本次合成客户逐位核车实际接车，三方到账已有独立原流水，内部承担不造款。", store)
    await form(e, "release"); await file_choice(e, "evidence_id", release_proof)
    before = facts(e, source_id)
    repair, _, release_native = await command(e, fixture, source_id, "release", service)
    require(repair["case"]["state"] == "completed" and repair["case"]["data"]["released_date"] == day
            and repair["cash"] == before["cash"] and repair["payments"] == before["payments"] and not repair["stock"]
            and [u["action"] for u in repair["resource_uses"]] == ["acquire", "release"]
            and one(e, "intake_resources", repair["context"][0]["resource_id"])["active_case_id"] is None
            and all(t["status"] != "open" for t in repair["tasks"]), "本次原接车/工位/到账独立事实错误")
    for claim_id in claims:
        f = claim_facts(e, claim_id)
        require(f["case"]["state"] == "completed" and len(f["bindings"]) == 1 and not f["cash"]
                and all(t["status"] != "open" for t in f["tasks"]), "接车后对应核赔未独立完整结束")
    before_refresh = e.business_snapshot("before_claim_repair_completed_refresh")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{REPAIR}/{source_id}") as pending:
        e.action("refresh", "刷新本次核赔维修完整结果")
        await e.page.reload()
    response = await pending.value
    require(response.status == 200 and (await response.json())["state"] == "completed", "核赔维修刷新未保留真实完成结果")
    await expect(e.page.locator("#main h1")).to_have_text(repair["case"]["title"])
    e.business_unchanged(before_refresh, "after_claim_repair_completed_refresh")
    require(facts(e, source_id) == repair, "刷新重复或改变原核赔维修结果")
    return repair, {"native_allocate": allocated, "binding_stage": bound, "allocations": by_party,
        "actual_receipts": receipt_history, "native_release": release_native, "release_file": release_proof,
        "task_owners": owners + [release_owner], "refresh_business_unchanged": True,
        "customer_payment_declaration": declared_source}


async def repair_claims_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    checkpoint.start("HK-035")
    try:
        fixture, vehicle, customer, insurer = dependencies(e, checkpoint)
        token = uuid.uuid4().hex[:10]
        works, manufacturer, resource, creation = await configured(e, context, credentials, fixture, token)
        repair, intake = await new_repair(e, context, credentials, fixture, vehicle, customer, resource, works, token)
        source_id = repair["case"]["id"]
        lines = [next(r for r in repair["lines"] if r["work_item_id"] == w["id"]) for w in works]
        checkpoint.note({"source_id": source_id, "new_intake": intake, "configured_sources": creation,
                         "works": works, "manufacturer": manufacturer, "resource": resource})
        checkpoint.start("HK-039")
        insurance, insurance_evidence = await create_claim(e, context, credentials, fixture, source_id, "insurer", insurer, token)
        insurance_id = insurance["case"]["id"]
        insurance, first_assessment = await assess_approve(e, context, credentials, fixture, insurance_id, source_id, lines[0], 3000, "I" + token, 1)
        insurance, supplement = await transmit_result(e, context, credentials, fixture, insurance_id, source_id, lines[0], "need_documents", 0, "I" + token, 1)
        need_id = supplement["result"]["id"]
        insurance, rejection = await transmit_result(e, context, credentials, fixture, insurance_id, source_id, lines[0], "rejected", 0, "I" + token, 2, supplement=need_id)
        insurance, second_assessment = await assess_approve(e, context, credentials, fixture, insurance_id, source_id, lines[0], 3000, "I" + token, 2)
        insurance, partial = await transmit_result(e, context, credentials, fixture, insurance_id, source_id, lines[0], "partial", 2000, "I" + token, 3)
        require([r["revision"] for r in insurance["assessments"]] == [1, 2] and len(insurance["approvals"]) == 2
                and [r["outcome"] for r in insurance["results"]] == ["need_documents", "rejected", "partial"]
                and [r["amount_cents"] for r in insurance["results"]] == [0, 0, 2000]
                and [r["assessment_id"] for r in insurance["results"]] == [first_assessment["assessment"]["id"], first_assessment["assessment"]["id"], second_assessment["assessment"]["id"]]
                and [r["supplement_result_id"] for r in insurance["transmissions"]] == [None, need_id, None],
                "保险补件、拒赔与新版部分核准原历史不完整")
        await checkpoint.passed({**insurance_evidence, "case_id": insurance_id, "source_case_id": source_id,
            "assessments": [first_assessment, second_assessment], "external_rounds": [supplement, rejection, partial], "db": insurance,
            "no_cash_before_allocation": True}, conditional=[{"check_id": "HK-039-real-insurer-certification", "status": "not_tested", "reason": "本轮外部结果为明确合成输入，无真实保险公司认证"}])
        checkpoint.start("HK-040")
        factory, factory_evidence = await create_claim(e, context, credentials, fixture, source_id, "manufacturer", manufacturer, token)
        factory_id = factory["case"]["id"]
        factory, factory_assessment = await assess_approve(e, context, credentials, fixture, factory_id, source_id, lines[1], 4000, "M" + token, 1)
        factory, factory_result = await transmit_result(e, context, credentials, fixture, factory_id, source_id, lines[1], "approved", 4000, "M" + token, 1)
        await checkpoint.passed({**factory_evidence, "manufacturer": manufacturer, "case_id": factory_id, "source_case_id": source_id,
            "assessment": factory_assessment, "external_result": factory_result, "db": factory, "no_cash_before_allocation": True},
            conditional=[{"check_id": "HK-040-real-manufacturer-certification", "status": "not_tested", "reason": "真实厂家手续另验，本轮为独立合成提交和结果原件"}])
        checkpoint.start("HK-041")
        internal_party = {"name": "合成核赔内部主体" + token}
        internal, internal_evidence = await create_claim(e, context, credentials, fixture, source_id, "internal", internal_party, token)
        internal_id = internal["case"]["id"]
        internal, internal_assessment = await assess_approve(e, context, credentials, fixture, internal_id, source_id, lines[2], 5000, "N" + token, 1)
        require(not internal["transmissions"] and not internal["results"] and not internal["cash"] and internal["case"]["data"]["phase"] == "ready", "内部核价错误地提交外部或造款")
        checkpoint.note({**internal_evidence, "case_id": internal_id, "source_case_id": source_id, "assessment": internal_assessment,
                         "ready_before_allocation": internal, "no_external_or_cash": True})
        claims = {insurance_id: "insurer", factory_id: "manufacturer", internal_id: "internal"}
        checkpoint.start("HK-035")
        repair, completion = await allocate_receive_release(e, context, credentials, fixture, source_id, claims,
            {"customer": customer, "insurer": insurer, "manufacturer": manufacturer, "internal": internal_party}, token)
        insurance, factory, internal = (claim_facts(e, key) for key in (insurance_id, factory_id, internal_id))
        insurance_payment = next(r for r in completion["actual_receipts"] if r["party_type"] == "insurer")
        factory_payment = next(r for r in completion["actual_receipts"] if r["party_type"] == "manufacturer")
        await checkpoint.passed({"new_intake": intake, "repair_case_id": source_id, "quote": repair["quotes"][0],
            "actual_completed_repair": repair, "insurance_current_assessment": insurance["assessments"][-1],
            "insurance_current_result": insurance["results"][-1], "binding": insurance["bindings"][0], "actual_insurer_payment": insurance_payment,
            "completion": completion, "claim_case_id": insurance_id, "no_internal_cash": True})
        checkpoint.start("HK-036")
        await checkpoint.passed({"repair_case_id": source_id, "manufacturer": manufacturer, "original_work_line": lines[1],
            "assessment": factory["assessments"][0], "approval": factory["approvals"][0], "transmission": factory["transmissions"][0],
            "result": factory["results"][0], "binding": factory["bindings"][0], "actual_manufacturer_payment": factory_payment,
            "claim_case_id": factory_id, "repair_state": repair["case"]["state"], "actual_release": completion["native_release"]})
        checkpoint.start("HK-041")
        await checkpoint.passed({"binding": internal["bindings"][0], "completed_original_internal_claim": internal,
            "allocation": completion["allocations"]["internal"], "no_external_or_internal_cash": True})
        sources = {"customer_id": customer["id"], "customer_vehicle_id": vehicle["id"], "vin": vehicle["vin"],
            "repair_case_id": source_id, "intake_case_id": intake["appointment"]["case_id"], "appointment_id": intake["appointment"]["id"],
            "arrival_id": intake["arrival"]["id"], "quote_id": repair["quotes"][0]["id"], "work_item_ids": [w["id"] for w in works],
            "line_ids": [line["id"] for line in lines], "insurer_id": insurer["id"], "manufacturer_id": manufacturer["id"],
            "claim_ids": {"insurer": insurance_id, "manufacturer": factory_id, "internal": internal_id},
            "assessment_ids": [a["id"] for f in (insurance, factory, internal) for a in f["assessments"]],
            "approval_ids": [p["id"] for f in (insurance, factory, internal) for p in f["approvals"]],
            "transmission_ids": [t["id"] for f in (insurance, factory) for t in f["transmissions"]],
            "result_ids": [r["id"] for f in (insurance, factory) for r in f["results"]],
            "binding_ids": [f["bindings"][0]["id"] for f in (insurance, factory, internal)],
            "allocation_ids": {k: a["id"] for k, a in completion["allocations"].items()},
            "payment_link_ids": [r["payment_link"]["id"] for r in completion["actual_receipts"]],
            "cash_ids": [r["cash"]["id"] for r in completion["actual_receipts"]], "actual_cash_cents": 7000,
            "internal_absorption_cents": 5000, "labor_cost_cents": 3000, "completed_date": repair["case"]["completed_date"]}
        customer_payment = next(r for r in completion["actual_receipts"] if r["party_type"] == "customer")
        declared = completion["customer_payment_declaration"]
        sources.update(customer_payment_link_id=customer_payment["payment_link"]["id"], customer_cash_id=customer_payment["cash"]["id"],
            customer_payment_evidence_id=customer_payment["file"]["file"]["id"], account_id=declared["account_id"],
            declaration_path=declared["path"], declaration_sha256=declared["sha256"],
            customer_correct_bank_reference=declared["correct_bank_reference"], customer_misrecorded_reference=declared["misrecorded_reference"],
            correction_executed=False)
        checkpoint.finish(repair_claims_sources=sources, report_sources=sources)
    except BaseException as error:
        checkpoint.failed(str(error))
        raise


REPAIR_CLAIMS_SCENARIOS = ((SCENARIO, repair_claims_business, 720),)
