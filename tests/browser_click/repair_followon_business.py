"""Same-run wash, quick repair and direct customer reimbursement original UI.

No application imports, positive API requests, fixture business outcomes, or
mutable browser state. Each predecessor and every current source is explicit.
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

from sales_business import login_as, require, employee_choice
from sales_order_business import fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import master_form, live_choice, select_value, checkbox
from master_data_business import save_typed
from repair_business import (
    SCENARIO as FIRST_REPAIR, MASTER, MATERIAL, Guard, Checkpoint as FirstCheckpoint,
    CASE_FIELDS, TASK_FIELDS, COMMON, INTAKE, REPAIR, one, case_facts, facts, task,
    event_added, mutable, submit, metadata, responsible, upload, file_choice, form, command,
    material_facts,
)

SCENARIO = "repair-wash-quick-hk032-080-033"
REIMBURSEMENT_SCENARIO = "repair-customer-reimbursement-hk042"
WASH_CONTRACTS = (
    ("HK-032", "洗车开单", ["本次真实洗车工位、快捷组合、到店和唯一wash维修", "本版授权、施工质检、承担及实际接车工位释放"]),
    ("HK-080", "洗车收款", ["该wash单实际客户承担、账户、独立凭据与Cash/PaymentLink/RepairPayment对应", "到账与接车独立，刷新无重复现金"]),
    ("HK-033", "快捷开单", ["另一新quick组合及实际接待转换唯一维修，原项目/数量/版本和报价一致", "独立核价、授权施工质检、实际到账及接车全部完成"]),
)
CLAIM_CONTRACTS = (("HK-042", "客户报销", ["首单客户实际现金及原报价，独立核价和本次外部提交/结果/报销批准", "第三方实际直接付客户产生客户支付事实，不产生门店现金"]),)
CLAIMS = "/api/claims"
KEYS = {t: "id" for t in (
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "master_work_items", "master_receipts",
    "intake_presets", "intake_preset_lines", "intake_command_receipts", "claims_orders",
    "claims_assessments", "claims_approvals", "claims_transmissions", "claims_results",
    "claims_reimbursement_approvals", "claims_customer_payments", "claims_request_receipts")}
KEYS["business_entity_case_contexts"] = "case_id"
CLAIM_TABLES = {
    "assessments": "claims_assessments", "transmissions": "claims_transmissions",
    "results": "claims_results", "reimbursement_approvals": "claims_reimbursement_approvals",
    "customer_payments": "claims_customer_payments", "cash": "claims_cash", "bindings": "claims_bindings",
}


class Checkpoint(FirstCheckpoint):
    def __init__(self, e, scenario, contracts):
        self.e, self.active = e, None
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        bindings = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, _, _ in contracts:
            require(bindings[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in bindings[key]["acceptance_checks"]), "后继目录未核准：" + key)
        self.path = e.directory / "business-checkpoint.json"
        self.report = {"schema": 1, "scenario": scenario, "scope": [r[0] for r in contracts],
            "complete": False, "passed": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending", "business_accepted": False,
            "execution": "native_browser_original_forms", "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_money_and_physical_inputs": True, "file_scan": "original_structure_only_not_clamav",
                "production_bank_or_physical_acceptance": False, "actual_insurer_certification": False,
                "business_entity_policy_acceptance": False, "gate_visit_acceptance": False},
            "planned_pending": [{"id": "HK-081", "status": "not_tested", "reason": "首单没有已声明误记；不冲正正确现金求覆盖"}],
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": criteria, "evidence": {}}], "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "conditional_checks": []} for key, title, criteria in contracts]}
        self.save()

    def note(self, evidence):
        json.dumps(evidence, ensure_ascii=False)  # Reject a raw BLOB before contaminating terminal failure evidence.
        super().note(evidence)

    def finish(self, **sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "后继实际检查未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=len(self.report["requirements"]),
                           passed_requirements=len(self.report["requirements"]), **sources)
        self.save()
        self.e.observe("repair_followon_original_checkpoint", {"path": str(self.path), "scope": self.report["scope"], "business_accepted": False})


class SourceGuard:
    """Only new configured sources/claim facts and specified old Case columns."""
    def __init__(self, e, label, actor, store_id, *, append, update=None, cases=(), source_id=None,
                 preset_id=None, work_id=None, new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store_id
        self.append, self.update = set(append), update or {}
        self.cases, self.source, self.preset, self.work, self.kind = set(cases), source_id, preset_id, work_id, new_kind
        require((self.append | self.update.keys()) <= KEYS.keys(), "后继守卫表未核准")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: self.rows(t) for t in self.append | self.update.keys()}

    def rows(self, table):
        return self.e.db.rows(f"SELECT * FROM {table} ORDER BY {KEYS[table]}")

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "后继改变了无关业务表：" + str(sorted(changed)))
        new_cases = set()
        new_presets = set()
        if "flow_cases" in self.append:
            old_ids = {r["id"] for r in self.old["flow_cases"]}
            added_cases = [r for r in self.rows("flow_cases") if r["id"] not in old_ids]
            require(len(added_cases) == 1 and added_cases[0]["kind"] == self.kind
                    and added_cases[0]["created_by"] == self.actor["id"], "后继创建了错误或多余原单")
            new_cases = {added_cases[0]["id"]}
        if "intake_presets" in self.append:
            old_ids = {r["id"] for r in self.old["intake_presets"]}
            new_presets = {r["id"] for r in self.rows("intake_presets") if r["id"] not in old_ids}
            require(len(new_presets) == 1, "本次配置不是唯一新组合")
        owned = self.cases | new_cases
        added_ids, updates = {}, {}
        for table, old in self.old.items():
            pk = KEYS[table]
            current = {r[pk]: r for r in self.rows(table)}
            old_ids = {r[pk] for r in old}
            updates[table] = []
            for row in old:
                require(row[pk] in current, "后继删除了原事实：" + table)
                columns = {k for k in row if row[k] != current[row[pk]][k]}
                require(columns <= self.update.get(table, {}).get(row[pk], set()), "后继覆盖无关旧行/列：" + table + "/" + str(row[pk]))
                if columns:
                    updates[table].append({"id": row[pk], "columns": sorted(columns)})
            new = [r for k, r in current.items() if k not in old_ids]
            require(not new or table in self.append, "后继更新表出现额外新增行：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "后继新增事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "后继新增事实串原单：" + table)
                for key in ("actor_id", "created_by"):
                    if key in row:
                        require(row[key] == self.actor["id"], "后继新增事实串员工：" + table)
                if "source_case_id" in row:
                    require(row["source_case_id"] == self.source, "客户报销串原维修")
                if "quote_id" in row:
                    require(one(self.e, "repair_quotes", row["quote_id"])["case_id"] == self.source, "核赔引用错误原报价")
                if "assessment_id" in row:
                    require(one(self.e, "claims_assessments", row["assessment_id"])["case_id"] in owned, "核赔串核价版本")
                if table == "claims_orders":
                    require(row["id"] in owned and row["payment_route"] == "customer_direct", "报销原路径错误")
                if table == "intake_presets":
                    require(len(new) == 1 and row["active"], "快捷配置未唯一启用")
                if table == "intake_preset_lines":
                    require(row["work_item_id"] == self.work and row["quantity_milli"] == 1000,
                            "快捷配置包含未声明项目或数量")
                    require(row["preset_id"] in new_presets
                            and one(self.e, "intake_presets", row["preset_id"])["created_by"] == self.actor["id"], "快捷行不属于本次唯一新组合")
            added_ids[table] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": added_ids, "updated_columns": updates,
                  "unrelated_tables_unchanged": True, "protected_old_rows_and_other_stores": True}
        self.e.observe("repair_followon_original_row_guard", {"label": self.label, **result})
        return result


def dependencies(e, checkpoint, *, completed_new=False):
    require(e.manifest.get("synthetic_data_only") is True, "后继只允许外置合成运行")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "后继数据库不在同次runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance.get("snapshot_stable") is True, "后继镜像没有完整冻结")
    for name in ("repair_followon_business.py", "repair_business.py", "master_data_business.py", "business_acceptance_catalog.json",
                 "sales_business.py", "sales_order_business.py", "vehicle_purchase_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "后继脚本指纹变化：" + name)
    checkpoint.report["mirror"] = {"sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    fixture = dict(e.manifest["business_fixtures"]["repair"])
    for role in ("manager", "service", "technician", "inventory", "finance"):
        require(e.manifest["users"][fixture[role + "_key"]]["role"] == role, "后继缺本店原岗位：" + role)
    original = fixed_dependency(e, checkpoint, FIRST_REPAIR)
    master = fixed_dependency(e, checkpoint, MASTER)
    material = fixed_dependency(e, checkpoint, MATERIAL)
    s = dict(original["report_sources"])
    require(set(s) == {"customer_id", "customer_vehicle_id", "vin", "appointment_id", "intake_case_id", "repair_case_id",
                       "quote_id", "allocation_id", "payment_link_id", "cash_id", "material_item_id"}, "首维修来源键不完整")
    f = facts(e, s["repair_case_id"])
    vehicle, customer = one(e, "care_customer_vehicles", s["customer_vehicle_id"]), one(e, "flow_customers", s["customer_id"])
    require(f["case"]["kind"] == "repair" and f["case"]["flow_version"] == 4 and f["case"]["state"] == "completed"
            and f["case"]["customer_id"] == customer["id"] == vehicle["customer_id"] and vehicle["vin"] == s["vin"]
            and f["case"]["store_id"] == vehicle["store_id"] == customer["store_id"] == fixture["store_id"], "原已接车客户/VIN/本店身份错误")
    require(len(f["context"]) == len(f["binding"]) == 1 and f["context"][0]["appointment_id"] == s["appointment_id"]
            and f["binding"][0]["customer_vehicle_id"] == vehicle["id"] and f["binding"][0]["vin"] == vehicle["vin"], "首维修接待/绑定源不一致")
    require(f["case"]["data"]["quote_id"] == s["quote_id"] and len(f["quotes"]) == 1
            and f["allocations"][0]["id"] == s["allocation_id"] and f["payments"][0]["id"] == s["payment_link_id"]
            and f["cash"][0]["id"] == s["cash_id"] and f["payments"][0]["cash_id"] == s["cash_id"]
            and len(f["payments"]) == len(f["cash"]) == len(f["repair_payments"]) == 1, "首单原实际到账有限来源错误")
    source_paid = checkpoint_evidence(original, "HK-079")
    require(f["allocations"][0] == source_paid["allocation"] and f["repair_payments"][0] == source_paid["repair_payment"]
            and f["payments"][0] == source_paid["payment_link"] and f["cash"][0] == source_paid["cash"]
            and f["allocations"][0]["payer_type"] == "customer", "首单原资金旧事实被覆盖或已被更正")
    require(len([r for r in f["events"] if r["action"] == "repair_v4_release"]) == 1
            and all(t["status"] != "open" for t in f["tasks"])
            and one(e, "intake_resources", f["context"][0]["resource_id"])["active_case_id"] is None, "首单实际离场/工位未释放")
    for key in ("customer_identity_id", "vehicle_identity_id"):
        require(f["binding"][0][key] == vehicle[key], "客户车辆原身份改变")
    primary = material["material_sources"]["primary"]
    require(primary["item_id"] == s["material_item_id"], "首单材料未承接同次原物资")
    current_material = material_facts(e, primary["item_id"])
    insurer = one(e, "master_insurers", checkpoint_evidence(master, "HK-172")["row"]["id"])
    require(insurer["active"] and insurer["store_id"] == fixture["store_id"], "原保险公司不是本店启用主档")
    checkpoint.report["source_preconditions"] = {"report_sources": s, "current_customer_vehicle": vehicle,
        "current_material": current_material, "insurer": insurer, "original_received_payment": source_paid,
        "current_case_version": f["case"]["version"], "no_old_cv_or_stock_version_equality": True}
    if completed_new:
        preceding = fixed_dependency(e, checkpoint, SCENARIO)
        for key in ("wash_sources", "quick_sources"):
            added = preceding[key]
            current = facts(e, added["repair_case_id"])
            require(current["case"]["state"] == "completed" and current["binding"][0]["vin"] == vehicle["vin"]
                    and current["case"]["customer_id"] == customer["id"]
                    and len([x for x in current["events"] if x["action"] == "repair_v4_release"]) == 1
                    and one(e, "intake_resources", added["resource_id"])["active_case_id"] is None, "新洗车/快捷未实际接车，不能续报销")
    checkpoint.save()
    return fixture, s, vehicle, customer, insurer


async def zero_nav(e, route, path, title):
    before = e.business_snapshot("before_followon_read_" + route.replace("/", "_"))
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        e.action("navigate", "打开原业务页面", route=route)
        await e.page.goto(e.manifest["origin"] + "/#" + route)
    response = await pending.value
    view = await response.json()
    require(response.status == 200, "原后继页面读取失败")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    e.business_unchanged(before, "after_followon_read_" + route.replace("/", "_"))
    return view


async def reveal(e, target, label):
    parent = target.locator("xpath=ancestor::details[1]")
    if await parent.count():
        await reveal(e, parent, label)
        if await parent.get_attribute("open") is None:
            summary = parent.locator(":scope > summary")
            await expect(summary).to_be_visible()
            e.action("click", label)
            await summary.click()
    await expect(target).to_be_visible()


async def configured(e, context, credentials, fixture, profile, token, fee):
    store = fixture["store_id"]
    label = "洗车" if profile == "wash" else "快捷检查"
    manager = await login_as(e, context, credentials, fixture["manager_key"], "masters/work_items", store)
    await expect(e.page.locator("#main h1")).to_have_text("作业项目")
    await master_form(e, "work_items", "作业项目")
    values = {"code": "FW" + profile[0] + token, "name": "合成" + label + token, "active": True,
              "billing_unit": "job", "standard_minutes": 20, "standard_fee_cents": fen_text(fee), "warranty_days": 0}
    protection = SourceGuard(e, profile + "_create_work", manager, store, append={"master_work_items", "master_receipts", "audit_logs"})
    work, native_work = await save_typed(e, manager, store, "work_items", values)
    native_work["source_guard"] = protection.finish()
    require(work["billing_unit"] == "job" and work["standard_fee_cents"] == fee and work["active"], "本次明确洗车/快捷作业费错误")
    await zero_nav(e, "service-intake/resources", INTAKE + "/catalog", "工位与快捷项目")
    await e.click('#main [data-act="intake-resource-new"]', "主管原UI建立本次工位")
    await e.fill('#modal [name="code"]', "FR" + profile[0] + token, "填写本次工位代码")
    await e.fill('#modal [name="name"]', "合成" + label + "工位" + token, "填写本次明确工位")
    await select_value(e, '#modal [name="type"]', "洗车" if profile == "wash" else "维修", "明确工位与组合类别")
    protection = Guard(e, profile + "_create_resource", manager, store, append={"intake_resources", "intake_command_receipts"})
    created, _, native_resource, _ = await submit(e, INTAKE + "/resources", INTAKE + "/catalog", store, 201, protection=protection)
    resource = one(e, "intake_resources", created["id"])
    require(resource["resource_type"] == ("wash" if profile == "wash" else "repair") and resource["active"]
            and resource["active_case_id"] is None, "本次实际工位类型或占用错误")
    await e.click('#main [data-act="intake-preset-new"]', "主管原UI建立本次固定作业组合")
    await expect(e.page.locator("#modal-title")).to_have_text("新增快捷项目预填")
    await e.fill('#modal [name="code"]', "FP" + profile[0] + token, "填写明确组合代码")
    await e.fill('#modal [name="name"]', "合成" + label + "组合" + token, "填写组合名称")
    await select_value(e, '#modal [name="profile"]', profile, "明确原组合profile")
    await e.fill(f'#modal [data-work-id="{work["id"]}"]', "1.000", "只填本批实际作业一项数量")
    protection = SourceGuard(e, profile + "_create_preset", manager, store,
        append={"intake_presets", "intake_preset_lines", "intake_command_receipts"}, work_id=work["id"])
    created, _, native_preset, request = await submit(e, INTAKE + "/presets", INTAKE + "/catalog", store, 201, protection=protection)
    preset = one(e, "intake_presets", created["id"])
    lines = e.db.rows("SELECT * FROM intake_preset_lines WHERE preset_id=?", (preset["id"],))
    require(preset["profile"] == profile and preset["active"] and preset["created_by"] == manager["id"] and len(lines) == 1
            and lines[0]["work_item_id"] == work["id"] and lines[0]["quantity_milli"] == 1000
            and request["lines"] == [{"work_item_id": work["id"], "quantity_milli": 1000}], "真实快捷配置/原数量不匹配")
    return work, resource, preset, {"work": work, "resource": resource, "preset": preset, "preset_lines": lines,
                                   "native": [native_work, native_resource, native_preset]}


async def new_intake(e, context, credentials, fixture, vehicle, customer, work, resource, preset, token, odo):
    store, day = fixture["store_id"], datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    service = await login_as(e, context, credentials, fixture["service_key"], "service-intake/appointments", store)
    await expect(e.page.locator("#main h1")).to_have_text("维修预约与到店")
    await e.click('#main [data-act="intake-new"][data-mode="walk_in"]', "服务顾问记录本次实际现场来访")
    vehicle_label = " · ".join(str(v) for v in (customer["name"], customer["phone"], vehicle["plate"], vehicle["vin"]) if v)
    await live_choice(e, "customer_vehicle_id", vehicle["vin"], vehicle_label, expected_value=vehicle["id"])
    await live_choice(e, "resource_id", resource["name"], resource["name"], expected_value=resource["id"])
    await live_choice(e, "preset_id", preset["name"], preset["name"] + " · " + ("快捷洗车" if preset["profile"] == "wash" else "快捷项目"), expected_value=preset["id"])
    for key in ("starts_at", "ends_at"):
        await e.fill(f'#modal [name="{key}"]', await e.page.locator(f'#modal [name="{key}"]').input_value(), "明确当前页面现场排队时段")
    await e.fill('#modal [name="reason"]', "本次合成" + work["name"] + "，客户现场核车后独立办理", "填写本次明确客户诉求")
    protection = Guard(e, preset["profile"] + "_book", service, store,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_appointments", "intake_command_receipts", "business_entity_case_contexts"},
        update={"intake_resources": {resource["id"]: {"updated_at", "version"}}}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="service_intake")
    book, _, native_book, request = await submit(e, INTAKE + "/appointments", INTAKE + "/appointments/*", store, 201, protection=protection)
    appointment_id, intake_id = book["id"], book["case_id"]
    require(request["mode"] == "walk_in" and request["preset_id"] == preset["id"] and request["customer_vehicle_id"] == vehicle["id"]
            and request["resource_id"] == resource["id"], "新到店未明确选择真实组合与原车辆")
    service, _, arrival_owner = await responsible(e, context, credentials, fixture, intake_id, "intake_arrive", "service", appointment_id=appointment_id)
    proof = await upload(e, intake_id, service, "evidence", "arrival-" + token + ".txt", f"本次独立合成到店VIN {vehicle['vin']}，现场里程{odo}。", store)
    await form(e, "arrive", intake=True)
    await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "现场逐位核对本次原VIN")
    await e.fill('#modal [name="odometer_km"]', str(odo), "填写本次明确合成现场里程")
    await file_choice(e, "evidence_id", proof)
    protection = Guard(e, preset["profile"] + "_arrive", service, store,
        append={"flow_tasks", "flow_events", "audit_logs", "intake_arrivals", "intake_command_receipts"},
        update={**mutable(e, intake_id, vehicle_id=vehicle["id"]), "intake_appointments": {appointment_id: {"status", "updated_at", "version"}}},
        cases={intake_id}, vehicle_id=vehicle["id"])
    _, _, native_arrival, _ = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/arrive", f"{INTAKE}/appointments/{appointment_id}", store, protection=protection)
    arrivals = e.db.rows("SELECT * FROM intake_arrivals WHERE appointment_id=?", (appointment_id,))
    require(len(arrivals) == 1 and arrivals[0]["checked_vin"] == vehicle["vin"] and arrivals[0]["odometer_km"] == odo
            and arrivals[0]["evidence_id"] == proof["file"]["id"] and arrivals[0]["actor_id"] == service["id"], "新实际到店事实不唯一或不匹配")
    service, _, convert_owner = await responsible(e, context, credentials, fixture, intake_id, "intake_convert", "service", appointment_id=appointment_id)
    await form(e, "convert", intake=True)
    await e.fill('#modal [name="due_date"]', day, "明确本次实际预计交接日")
    protection = Guard(e, preset["profile"] + "_convert", service, store,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_command_receipts", "intake_repair_contexts",
                "intake_vehicle_bindings", "business_entity_case_contexts", "repair_quotes", "repair_lines"},
        update={**mutable(e, intake_id), "intake_appointments": {appointment_id: {"status", "repair_case_id", "updated_at", "version"}}},
        cases={intake_id}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="repair")
    converted, _, native_convert, _ = await submit(e, f"{INTAKE}/appointments/{appointment_id}/actions/convert", f"{INTAKE}/appointments/{appointment_id}", store, protection=protection)
    repair = facts(e, converted["repair_case_id"])
    require(repair["case"]["state"] == "approval" and repair["case"]["flow_version"] == 4
            and repair["case"]["customer_id"] == customer["id"] and len(repair["context"]) == len(repair["binding"]) == 1
            and repair["context"][0]["profile"] == preset["profile"] and repair["context"][0]["preset_id"] == preset["id"]
            and repair["context"][0]["appointment_id"] == appointment_id and repair["context"][0]["resource_id"] == resource["id"]
            and repair["binding"][0]["vin"] == vehicle["vin"] and repair["binding"][0]["customer_vehicle_id"] == vehicle["id"], "快捷转换没有绑定本次profile/原VIN/预约工位")
    require(one(e, "intake_presets", preset["id"]) == preset and one(e, "master_work_items", work["id"]) == work, "配置在转换期间发生改变")
    require(len(repair["quotes"]) == len(repair["lines"]) == 1 and not repair["stock"] and not repair["payments"], "自动预填生成了多版或实际库存现金")
    quote, line = repair["quotes"][0], repair["lines"][0]
    require(line["kind"] == "work" and line["work_item_id"] == work["id"] and line["item_id"] is None
            and line["quantity_milli"] == 1000 and line["unit"] == work["billing_unit"]
            and line["name"] == work["name"] and line["code"] == work["code"]
            and line["unit_price_cents"] == line["standard_fee_cents"] == line["amount_cents"] == work["standard_fee_cents"]
            and quote["amount_cents"] == work["standard_fee_cents"] and quote["created_by"] == service["id"] and line["discount_cents"] == 0,
            "自动预填本版原作业费用数量来源不准确")
    specs = [{k: line[k] for k in ("line_key", "kind", "work_item_id", "item_id", "code", "name", "unit", "standard_fee_cents",
             "quantity_milli", "unit_price_cents", "amount_cents", "discount_cents")}]
    digest = hashlib.sha256(json.dumps({"purpose": quote["purpose"], "reason": quote["reason"], "lines": specs}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    require(quote["digest"] == digest and one(e, "intake_appointments", appointment_id)["repair_case_id"] == repair["case"]["id"], "自动预填原版本摘要/唯一转换不准确")
    require(len([x for x in repair["events"] if x["action"] == "intake_convert"]) == 1
            and all(t["status"] != "open" for t in case_facts(e, intake_id)["tasks"]), "本次快捷转换事件或原接待任务不完整")
    return repair, {"appointment": one(e, "intake_appointments", appointment_id), "arrival": arrivals[0],
                    "arrival_file": proof, "native": [native_book, native_arrival, native_convert], "task_owners": [arrival_owner, convert_owner]}


async def finish_repair(e, context, credentials, fixture, repair, customer, token, labor, checkpoint, *, wash):
    store, case_id, quote = fixture["store_id"], repair["case"]["id"], repair["quotes"][0]
    day, amount = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(), quote["amount_cents"]
    native, owners = [], []
    manager, _, owner = await responsible(e, context, credentials, fixture, case_id, "repair_price_" + str(quote["id"]), "manager")
    await form(e, "price_approve")
    await e.fill('#modal [name="minimum"]', fen_text(amount), "主管明确本次原组合核价")
    await checkbox(e, '#modal [name="allow_below_minimum"]', False, "不默认授权低价例外")
    await e.fill('#modal [name="reason"]', "独立核对本次组合原项目数量及约定费用", "记录主管独立核价")
    repair, _, result = await command(e, fixture, case_id, "price_approve", manager)
    require(len(repair["approvals"]) == 1 and repair["approvals"][0]["actor_id"] == manager["id"] != quote["created_by"]
            and repair["approvals"][0]["quote_id"] == quote["id"], "洗车/快捷未独立核价")
    native.append(result); owners.append(owner)
    service, _, owner = await responsible(e, context, credentials, fixture, case_id, "repair_authorize_" + str(quote["id"]), "service")
    proof = await upload(e, case_id, service, "authorization", "authorization-" + token + ".txt", f"本次合成客户授权报价{quote['id']} 摘要{quote['digest']} 金额{amount}分。", store)
    await form(e, "authorize"); await file_choice(e, "evidence_id", proof)
    repair, _, result = await command(e, fixture, case_id, "authorize", service)
    require(len(repair["authorizations"]) == 1 and repair["authorizations"][0]["quote_digest"] == quote["digest"]
            and repair["authorizations"][0]["evidence_id"] == proof["file"]["id"], "新组合授权未绑定本版原字节")
    native.append(result); owners.append(owner)
    technician, _, owner = await responsible(e, context, credentials, fixture, case_id, "repair_work", "technician")
    await form(e, "start")
    await e.fill('#modal [name="result"]', "本次合成原组合已核车入位实际开始施工", "技师记录本次实际开工")
    repair, _, result = await command(e, fixture, case_id, "start", technician)
    require(repair["case"]["data"]["started"] and len(repair["resource_uses"]) == 1 and repair["resource_uses"][0]["action"] == "acquire"
            and one(e, "intake_resources", repair["context"][0]["resource_id"])["active_case_id"] == case_id
            and not repair["stock"] and not any(t["key"] == "repair_issue" and t["status"] == "open" for t in repair["tasks"]), "作业组合实际入位或无配件施工错误")
    native.append(result); owners.append(owner)
    technician, _, owner = await responsible(e, context, credentials, fixture, case_id, "repair_work", "technician")
    await form(e, "finish")
    await e.fill('#modal [name="result"]', "本次明确合成作业组合施工完成，未领用配件", "技师记录实际施工完成")
    repair, _, result = await command(e, fixture, case_id, "finish", technician)
    require(repair["case"]["state"] == "quality", "新组合施工未进入质检")
    native.append(result); owners.append(owner)
    service, _, owner = await responsible(e, context, credentials, fixture, case_id, "repair_quality", "service")
    proof = await upload(e, case_id, service, "inspection", "quality-" + token + ".txt", "本次合成作业与授权一致，实际交接质检合格。", store)
    await form(e, "quality")
    await e.fill('#modal [name="result"]', "本次合成组合完成质量及交接安全检查合格", "服务顾问记录本次检查")
    await select_value(e, '#modal [name="outcome"]', "合格", "明确本次实际检查合格")
    await file_choice(e, "evidence_id", proof)
    repair, _, result = await command(e, fixture, case_id, "quality", service)
    require(len(repair["quality"]) == 1 and repair["quality"][0]["passed"] and repair["quality"][0]["quote_id"] == quote["id"], "新组合质检没有当前版本来源")
    native.append(result); owners.append(owner)
    manager, _, owner = await responsible(e, context, credentials, fixture, case_id, "repair_allocate", "manager")
    proof = await upload(e, case_id, manager, "evidence", "allocation-" + token + ".txt", f"本次明确合成人工成本{labor}分，客户承担本版{amount}分。", store)
    await form(e, "allocate")
    await e.click('#modal [data-repair-customer-all]', "客户明确全额承担本次作业")
    await e.fill('#modal [name="due_customer"]', day, "明确本次承担到期日期")
    await e.fill('#modal [name="labor_cost"]', fen_text(labor), "填写本批事先声明合成人工成本")
    await file_choice(e, "evidence", proof)
    repair, _, result = await command(e, fixture, case_id, "allocate", manager)
    require(len(repair["settlements"]) == len(repair["allocations"]) == 1 and not repair["stock"] and not repair["payments"]
            and repair["settlements"][0]["labor_cost_cents"] == repair["case"]["cost_cents"] == labor, "纯作业承担误算材料/成本或提前生成现金")
    allocation = repair["allocations"][0]
    require(allocation["payer_type"] == "customer" and allocation["payer_name"] == customer["name"] and allocation["amount_cents"] == amount, "原客户承担身份/金额错误")
    native.append(result); owners.append(owner)
    checkpoint.note({"case_id": case_id, "quote": quote, "authorization": repair["authorizations"][0],
        "quality": repair["quality"][0], "allocation": allocation, "labor_cost_cents": labor, "native_before_cash": native})
    if wash:
        checkpoint.start("HK-080")
    finance, _, receive_owner = await responsible(e, context, credentials, fixture, case_id, "repair_receive_" + str(allocation["id"]), "finance")
    reference = "WF-" + token
    proof = await upload(e, case_id, finance, "evidence", "payment-" + token + ".txt", f"本次合成实际客户到账{amount}分，独立凭证{reference}。", store)
    await form(e, "receive")
    await e.fill('#modal [name="amount"]', fen_text(amount), "核对本次原客户实际到账")
    await live_choice(e, "account_id", "门店结算账户（演示）", "门店结算账户（演示）", expected_value=None)
    account_id = int(await e.page.locator('#modal [name="account_id"]').input_value())
    account = one(e, "flow_accounts", account_id)
    require(account["active"] and account["store_id"] == store and account["account_type"] == "bank", "本次原资金账户非本店启用银行账户")
    await e.fill('#modal [name="reference"]', reference, "填写本次独立合成收款凭证")
    await file_choice(e, "evidence_id", proof)
    repair, view, received = await command(e, fixture, case_id, "receive", finance)
    require(len(repair["repair_payments"]) == len(repair["payments"]) == len(repair["cash"]) == 1, "新组合一次到账产生重复或缺失原款")
    payment, link, cash = repair["repair_payments"][0], repair["payments"][0], repair["cash"][0]
    require(payment["allocation_id"] == allocation["id"] and payment["payment_link_id"] == link["id"] and payment["evidence_id"] == proof["file"]["id"]
            and link["cash_id"] == cash["id"] and link["direction"] == cash["direction"] == "in"
            and link["amount_cents"] == cash["amount_cents"] == amount and link["account_id"] == account["id"]
            and link["reference"] == cash["voucher_no"] == reference and cash["created_by"] == finance["id"]
            and cash["business_date"] == link["business_date"] == day and cash["approval_state"] == "approved"
            and link["original_id"] is None and view["customer_due_cents"] == view["receivable_cents"] == 0
            and not repair["case"]["data"].get("released_date"), "本次资金与客户承担/未接车各自事实不一致")
    if wash:
        checkpoint.note({"case_id": case_id, "allocation": allocation, "repair_payment": payment, "payment_link": link,
            "cash": cash, "native_receive": received, "account": account, "file": proof, "task_owner": receive_owner})
        checkpoint.start("HK-032")
    service, _, release_owner = await responsible(e, context, credentials, fixture, case_id, "repair_release", "service")
    proof = await upload(e, case_id, service, "evidence", "release-" + token + ".txt", "本次新合成业务客户已核车实际接车，收款另有原记录。", store)
    await form(e, "release"); await file_choice(e, "evidence_id", proof)
    repair, _, released = await command(e, fixture, case_id, "release", service)
    require(repair["case"]["state"] == "completed" and repair["case"]["data"]["released_date"] == day
            and all(t["status"] != "open" for t in repair["tasks"]) and [u["action"] for u in repair["resource_uses"]] == ["acquire", "release"]
            and one(e, "intake_resources", repair["context"][0]["resource_id"])["active_case_id"] is None
            and repair["payments"] == [link] and repair["cash"] == [cash] and not repair["stock"], "新组合实际接车/工位/原资金保持错误")
    before = e.business_snapshot("before_new_repair_refresh")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{REPAIR}/{case_id}") as pending:
        e.action("refresh", "刷新本次原组合完成结果")
        await e.page.reload()
    response = await pending.value
    require(response.status == 200 and (await response.json())["state"] == "completed", "新组合刷新完成结果错误")
    await expect(e.page.locator("#main h1")).to_have_text(repair["case"]["title"])
    e.business_unchanged(before, "after_new_repair_refresh")
    require(facts(e, case_id) == repair, "刷新重复或改变了新组合原事实")
    return repair, {"native_completion": native + [received, released], "task_owners": owners + [receive_owner, release_owner],
                    "cash": cash, "payment_link": link, "repair_payment": payment, "refresh_business_unchanged": True}


def finite_new_sources(e, vehicle, repair, configured_source):
    return {"customer_id": vehicle["customer_id"], "customer_vehicle_id": vehicle["id"], "vin": vehicle["vin"],
            "resource_id": configured_source["resource"]["id"], "preset_id": configured_source["preset"]["id"],
            "appointment_id": repair["context"][0]["appointment_id"],
            "intake_case_id": one(e, "intake_appointments", repair["context"][0]["appointment_id"])["case_id"],
            "repair_case_id": repair["case"]["id"], "quote_id": repair["quotes"][0]["id"],
            "allocation_id": repair["allocations"][0]["id"], "payment_link_id": repair["payments"][0]["id"], "cash_id": repair["cash"][0]["id"]}


async def wash_quick_business(e, context, credentials):
    checkpoint = Checkpoint(e, SCENARIO, WASH_CONTRACTS)
    checkpoint.start("HK-032")
    try:
        fixture, original, vehicle, customer, _ = dependencies(e, checkpoint)
        material_before = material_facts(e, original["material_item_id"])
        previous = facts(e, original["repair_case_id"])
        outputs = {}
        for profile, requirement, fee, labor, odo in (("wash", "HK-032", 1000, 200, 32101), ("quick", "HK-033", 2000, 300, 32102)):
            checkpoint.start(requirement)
            token = profile + uuid.uuid4().hex[:10]
            work, resource, preset, config = await configured(e, context, credentials, fixture, profile, token, fee)
            repair, intake = await new_intake(e, context, credentials, fixture, vehicle, customer, work, resource, preset, token, odo)
            checkpoint.note({"configured_source": config, "new_intake": intake, "current_quote": repair["quotes"][0], "new_case_id": repair["case"]["id"]})
            repair, completion = await finish_repair(e, context, credentials, fixture, repair, customer, token, labor, checkpoint, wash=profile == "wash")
            require(material_facts(e, original["material_item_id"]) == material_before, "纯作业洗车/快捷改变了原材料余额或历史")
            require(facts(e, original["repair_case_id"]) == previous, "洗车/快捷覆盖原已完成普通维修")
            sources = finite_new_sources(e, vehicle, repair, config)
            outputs[profile + "_sources"] = sources
            await expect(e.page.locator("#main")).to_contain_text("快捷洗车" if profile == "wash" else "快捷项目")
            if profile == "wash":
                checkpoint.start("HK-080")
                await checkpoint.passed({"refresh_business_unchanged": completion["refresh_business_unchanged"],
                    "payment_link_after_refresh": repair["payments"][0], "cash_after_refresh": repair["cash"][0],
                    "separate_actual_release": repair["resource_uses"][-1]})
                checkpoint.start("HK-032")
            await checkpoint.passed({"case_id": repair["case"]["id"], "configured_source": config, "intake": intake,
                "original_profile": profile, "original_quote": repair["quotes"][0], "original_line": repair["lines"][0],
                "final_case": repair["case"], "resource_uses": repair["resource_uses"], "actual_completion": completion,
                "finite_sources": sources, "original_repair_and_material_unchanged": True}, conditional=[
                    {"status": "not_tested", "reason": "本批作业组合无配件，未继承普通维修领退料、保安进出厂或质量不合格整改"}])
        checkpoint.finish(**outputs)
    except Exception as error:
        checkpoint.failed(error)
        raise


def claim_facts(e, case_id):
    f = case_facts(e, case_id)
    f["order"] = one(e, "claims_orders", case_id)
    f["order"]["source_snapshot"] = json.loads(f["order"]["source_snapshot"])
    for key, table in CLAIM_TABLES.items():
        f[key] = e.db.rows(f"SELECT * FROM {table} WHERE case_id=? ORDER BY id", (case_id,))
        if key in ("assessments", "results"):
            for row in f[key]:
                row["lines"] = json.loads(row["lines"])
    f["approvals"] = e.db.rows("SELECT t.* FROM claims_approvals t JOIN claims_assessments a ON a.id=t.assessment_id WHERE a.case_id=? ORDER BY t.id", (case_id,))
    return f


async def claim_read(e, context, credentials, fixture, role, case_id):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{CLAIMS}/{case_id}") as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], f"claims/{case_id}", fixture["store_id"])
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == case_id, "当前员工未读取到本报销原单")
    await expect(e.page.locator("#main h1")).to_have_text(view["title"])
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    return actor, view


async def claim_responsible(e, context, credentials, fixture, case_id, key, role):
    original = task(case_facts(e, case_id), key)
    selected = e.manifest["users"][fixture[role + "_key"]]
    meta = {"task_id": original["id"], "task_key": key, "assignee_id": selected["id"], "handoff_needed": original["assignee_id"] != selected["id"]}
    if meta["handoff_needed"]:
        manager, _ = await claim_read(e, context, credentials, fixture, "manager", case_id)
        selector = f'#main [data-act="assign"][data-id="{original["id"]}"]'
        await reveal(e, e.page.locator(selector), "展开原报销岗位交接栏目")
        await e.click(selector, "主管明确交接本次报销原岗位任务")
        await employee_choice(e, selected)
        await e.fill('#modal [name="reason"]', "本次合成报销由所选本店原岗位员工本人办理", "填写明确岗位交接依据")
        protection = Guard(e, "claim_original_handoff", manager, fixture["store_id"], append={"flow_events", "audit_logs"},
            update={"flow_tasks": {original["id"]: TASK_FIELDS}, "flow_cases": {case_id: {"updated_at", "version"}}}, cases={case_id})
        _, _, native, request = await submit(e, f'/api/flow/tasks/{original["id"]}/assign', f"{CLAIMS}/{case_id}", fixture["store_id"], protection=protection)
        require(request["version"] == original["version"] and request["assignee_id"] == selected["id"], "报销任务交接版本/员工错误")
        meta["native"] = native
    actor, view = await claim_read(e, context, credentials, fixture, role, case_id)
    require(task(case_facts(e, case_id), key)["assignee_id"] == actor["id"], "报销未由原任务本人办理")
    return actor, view, meta


async def claim_form(e, key):
    selector = f'#main [data-act="claim-action"][data-key="{key}"]'
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "本人办理原报销 " + key)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def claim_file_choice(e, evidence):
    row = evidence["file"]
    label = {"authorization": "客户授权", "receipt": "收退款凭据"}[row["category"]]
    field = e.page.locator('#modal .lookup').filter(has=e.page.locator('select[name="evidence_id"]'))
    await expect(field.locator('.inline-file-tools')).to_have_attribute("data-file-requirement", row["category"])
    await live_choice(e, "evidence_id", row["name"], row["name"] + " · " + label, expected_value=row["id"])


async def claim_command(e, fixture, case_id, source_id, action, actor):
    before = claim_facts(e, case_id)
    source_before = facts(e, source_id)
    appended = {"flow_tasks", "flow_events", "audit_logs", "claims_request_receipts"} | {
        "assess": {"claims_assessments"}, "approve": {"claims_approvals"}, "transmit": {"claims_transmissions"},
        "result": {"claims_results"}, "reimbursement_approve": {"claims_reimbursement_approvals"},
        "direct_confirm": {"claims_customer_payments"}}[action]
    protection = SourceGuard(e, "claim_original_" + action, actor, fixture["store_id"], append=appended,
        update={"flow_cases": {case_id: CASE_FIELDS, source_id: {"updated_at", "version"}},
                "flow_tasks": {r["id"]: TASK_FIELDS for r in before["tasks"]}}, cases={case_id}, source_id=source_id)
    body, view, native, request = await submit(e, f"{CLAIMS}/{case_id}/actions/{action}", f"{CLAIMS}/{case_id}", fixture["store_id"], protection=protection)
    after = claim_facts(e, case_id)
    require(body["id"] == view["id"] == case_id and request["version"] == before["case"]["version"]
            and request["source_version"] == source_before["case"]["version"]
            and after["case"]["version"] == body["version"] > before["case"]["version"], "核赔原当前双版本/CAS错误")
    for key in ("order", "assessments", "approvals", "transmissions", "results", "reimbursement_approvals", "customer_payments", "cash", "bindings"):
        if isinstance(before[key], list):
            require(after[key][:len(before[key])] == before[key], "报销原历史被改写：" + key)
        else:
            require(after[key] == before[key], "报销原来源快照被改写")
    source_after = facts(e, source_id)
    for key in source_before:
        if key != "case":
            require(source_after[key] == source_before[key], "报销改变原维修事实：" + key)
    require(source_after["case"]["state"] == "completed" and not after["cash"] and not after["bindings"], "直接客户报销生成了门店资金/第三方承担")
    event = event_added(before, after, "claims_" + action, actor)
    await expect(e.page.locator("#main h1")).to_have_text(after["case"]["title"])
    return after, view, {"native": native, "event": event, "submitted_values": request["values"]}


async def select_claim_line(e, line, amount, *, result=False, evidence=None, day=None):
    fields = e.page.locator('#modal [data-claim-line]')
    ids = [await fields.nth(i).get_attribute("data-id") for i in range(await fields.count())]
    require(str(line["id"]) in ids, "核赔表单没有本次明确原维修行")
    for row_id in ids:
        await checkbox(e, f'#modal [data-claim-line][data-id="{row_id}"] [name="selected"]', row_id == str(line["id"]), "明确仅选择本次原核价行")
    root = f'#modal [data-claim-line][data-id="{line["id"]}"]'
    await e.fill(root + ' [name="quantity"]', "1.000", "核对本次原作业数量")
    await e.fill(root + ' [name="amount"]', fen_text(amount), "填写本次明确合成逐项核准金额")
    await e.fill('#modal [name="reason"]', "本次合成第三方仅核准这一原作业行，未认证真实保险结果", "记录本次明确外部事实")
    if result:
        await select_value(e, '#modal [name="outcome"]', "approved", "选择本次已声明合成全部核准")
        await e.fill('#modal [name="result_on"]', day, "填写本次明确外部结果日期")
        await select_value(e, '#modal [name="evidence_id"]', str(evidence["file"]["id"]), "明确选择本次独立外部结果原件")


async def reimbursement_business(e, context, credentials):
    checkpoint = Checkpoint(e, REIMBURSEMENT_SCENARIO, CLAIM_CONTRACTS)
    checkpoint.start("HK-042")
    try:
        fixture, sources, vehicle, customer, insurer = dependencies(e, checkpoint, completed_new=True)
        store, source_id = fixture["store_id"], sources["repair_case_id"]
        token, day = uuid.uuid4().hex[:10], datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        source = facts(e, source_id)
        line = next(r for r in source["lines"] if r["kind"] == "work")
        amount = line["amount_cents"]
        require(line["quantity_milli"] == 1000 and amount > 0 and amount <= source["cash"][0]["amount_cents"], "原实际客户款不能覆盖本次明确作业报销")
        service = await login_as(e, context, credentials, fixture["service_key"], f"repair-orders/{source_id}", store)
        await expect(e.page.locator("#main h1")).to_have_text(source["case"]["title"])
        selector = f'#main [data-act="claim-new"][data-source="{source_id}"]'
        await reveal(e, e.page.locator(selector), "展开原维修报销栏目")
        await e.click(selector, "由原已付款维修明确建立本次客户报销")
        await expect(e.page.locator("#modal-title")).to_have_text("建立原维修核赔申请")
        source_label = str(source_id) + " · " + source["case"]["number"] + " · " + source["case"]["title"]
        await select_value(e, '#modal [name="source"]', source_label, "明确选择同次原维修付款来源")
        await select_value(e, '#modal [name="party"]', "保险 · " + insurer["name"], "选择同次真实启用保险主档")
        await select_value(e, '#modal [name="route"]', "第三方直接报销给客户", "明确直接客户支付无公司现金")
        await e.fill('#modal [name="reason"]', "原客户已自费支付，本次合成第三方直接报销指定作业费用", "记录本次明确报销路径依据")
        before_source = facts(e, source_id)
        protection = SourceGuard(e, "claim_original_create", service, store,
            append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "claims_orders", "claims_request_receipts", "business_entity_case_contexts"},
            update={"flow_cases": {source_id: {"updated_at", "version"}}}, source_id=source_id, new_kind="claim")
        created, view, native_create, request = await submit(e, CLAIMS, CLAIMS + "/*", store, 201, protection=protection)
        case_id = created["id"]
        f = claim_facts(e, case_id)
        require(f["case"]["parent_id"] == source_id and f["case"]["customer_id"] == customer["id"] and f["case"]["flow_version"] == 2
                and f["order"]["source_case_id"] == source_id and f["order"]["insurer_id"] == insurer["id"]
                and f["order"]["payment_route"] == "customer_direct" and request["source_version"] == before_source["case"]["version"]
                and view["customer_available_cents"] == source["cash"][0]["amount_cents"], "新直接报销原现金/保险/客户来源不准确或已被占额")
        native, owners, files = [native_create], [], []
        service, _, owner = await claim_responsible(e, context, credentials, fixture, case_id, "claim_assess", "service")
        await claim_form(e, "assess"); await select_claim_line(e, line, amount)
        f, _, submitted = await claim_command(e, fixture, case_id, source_id, "assess", service)
        assessment = f["assessments"][0]
        require(len(f["assessments"]) == 1 and assessment["quote_id"] == sources["quote_id"]
                and assessment["quote_digest"] == source["quotes"][0]["digest"] and assessment["amount_cents"] == amount
                and len(assessment["lines"]) == 1 and assessment["lines"][0]["line_id"] == line["id"], "本次核价未绑定原当前作业版")
        native.append(submitted); owners.append(owner)
        for action, key, role, category in (("approve", "claim_approve", "manager", "authorization"),
                                            ("transmit", "claim_transmit", "service", "authorization")):
            actor, _, owner = await claim_responsible(e, context, credentials, fixture, case_id, key, role)
            proof = await upload(e, case_id, actor, category, action + "-" + token + ".txt", f"本次{action}合成外部核价/提交原件，原维修{source_id}核价{assessment['id']}金额{amount}分。", store)
            await claim_form(e, action)
            if action == "approve":
                require(actor["id"] != service["id"] == assessment["actor_id"], "核价人不能自批")
                await e.fill('#modal [name="reason"]', "独立核对本次原已付作业与合成核价，未认证外部真实性", "主管独立核价审批")
            else:
                await e.fill('#modal [name="external_reference"]', "CLAIM-" + token, "记录本次独立合成外部受理号")
                await e.fill('#modal [name="submitted_on"]', day, "记录本次明确实际提交日")
            await claim_file_choice(e, proof)
            f, _, submitted = await claim_command(e, fixture, case_id, source_id, action, actor)
            native.append(submitted); owners.append(owner); files.append(proof)
        require(len(f["approvals"]) == len(f["transmissions"]) == 1 and f["approvals"][0]["assessment_id"] == assessment["id"]
                and f["approvals"][0]["actor_id"] != assessment["actor_id"]
                and f["transmissions"][0]["assessment_id"] == assessment["id"] and f["transmissions"][0]["submitted_on"] == day
                and f["transmissions"][0]["external_reference"] == "CLAIM-" + token, "独立核价与实际外部提交不完整")
        service, _, owner = await claim_responsible(e, context, credentials, fixture, case_id, "claim_result", "service")
        proof = await upload(e, case_id, service, "authorization", "result-" + token + ".txt", f"本次合成外部结果核准原作业行{line['id']}金额{amount}分，客户直接收款另有独立事实。", store)
        await claim_form(e, "result"); await select_claim_line(e, line, amount, result=True, evidence=proof, day=day)
        f, _, submitted = await claim_command(e, fixture, case_id, source_id, "result", service)
        result = f["results"][0]
        require(len(f["results"]) == 1 and result["assessment_id"] == assessment["id"] and result["transmission_id"] == f["transmissions"][0]["id"]
                and result["outcome"] == "approved" and result["amount_cents"] == amount and result["result_on"] == day
                and result["evidence_id"] == proof["file"]["id"] and result["lines"] == assessment["lines"], "实际外部结果与原核价逐行不匹配")
        native.append(submitted); owners.append(owner); files.append(proof)
        manager, _, owner = await claim_responsible(e, context, credentials, fixture, case_id, "claim_reimbursement_approve", "manager")
        require(manager["id"] not in {f["case"]["created_by"], assessment["actor_id"], result["actor_id"]}, "客户报销未由另一主管复核")
        proof = await upload(e, case_id, manager, "authorization", "reimbursement-approve-" + token + ".txt", f"独立核对原客户现金及未占用额度，批准本次合成报销{amount}分。", store)
        await claim_form(e, "reimbursement_approve")
        await e.fill('#modal [name="reason"]', "独立核对原客户自付净现金及本次已核准逐项额度", "主管独立批准实际报销额度")
        await claim_file_choice(e, proof)
        f, _, submitted = await claim_command(e, fixture, case_id, source_id, "reimbursement_approve", manager)
        approval = f["reimbursement_approvals"][0]
        require(len(f["reimbursement_approvals"]) == 1 and approval["result_id"] == result["id"] and approval["amount_cents"] == amount
                and approval["actor_id"] == manager["id"] and f["case"]["data"]["phase"] == "reimbursement", "原客户报销批准/占额来源错误")
        native.append(submitted); owners.append(owner); files.append(proof)
        finance, _, owner = await claim_responsible(e, context, credentials, fixture, case_id, "claim_reimburse", "finance")
        proof = await upload(e, case_id, finance, "receipt", "direct-payment-" + token + ".txt", f"本次合成第三方已直接付本原客户{amount}分；无门店实际到账或转付。", store)
        await claim_form(e, "direct_confirm")
        await expect(e.page.locator('#modal [name="account_id"], #modal [name="reference"]')).to_have_count(0)
        await e.fill('#modal [name="amount"]', fen_text(amount), "财务明确客户实际直接收款金额")
        await claim_file_choice(e, proof)
        f, view, submitted = await claim_command(e, fixture, case_id, source_id, "direct_confirm", finance)
        payment = f["customer_payments"][0]
        require(len(f["customer_payments"]) == 1 and payment["purpose"] == "reimbursement" and payment["amount_cents"] == amount
                and payment["actor_id"] == finance["id"] and payment["business_date"] == day and payment["evidence_id"] == proof["file"]["id"]
                and payment["original_id"] is None and payment["return_plan_id"] is None and f["case"]["state"] == "completed"
                and view["phase"] == "completed" and view["reimbursement_usage_cents"] == amount
                and not f["cash"] and not f["bindings"] and all(t["status"] != "open" for t in f["tasks"]), "实际直接客户支付/结案产生错误门店现金或重复付款")
        native.append(submitted); owners.append(owner); files.append(proof)
        require(len({p["file"]["sha256"] for p in files}) == len(files), "核价/提交/结果/审批/付款复用了同一字节")
        await expect(e.page.locator("#main")).to_contain_text("第三方直接报销给客户")
        await expect(e.page.locator("#main")).to_contain_text("直接付客户不产生公司现金")
        before = e.business_snapshot("before_direct_claim_refresh")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{CLAIMS}/{case_id}") as pending:
            e.action("refresh", "刷新原客户报销实际完成结果")
            await e.page.reload()
        refresh = await pending.value
        require(refresh.status == 200 and (await refresh.json())["phase"] == "completed", "报销刷新状态错误")
        await expect(e.page.locator("#main h1")).to_have_text(f["case"]["title"])
        e.business_unchanged(before, "after_direct_claim_refresh")
        require(claim_facts(e, case_id) == f, "刷新重复或覆盖了实际客户报销")
        await checkpoint.passed({"source_report_sources": sources, "claim": f, "original_work_line": line, "files": files,
            "native_actions": native, "task_owners": owners, "refresh_business_unchanged": True,
            "no_store_cash_or_original_repair_payment_change": True}, conditional=[
                {"check_id": "HK-042-via-store", "status": "not_tested", "reason": "客户直接付款路径，未冒充门店到店收款/原路转付"},
                {"check_id": "HK-042-external-negative", "status": "not_tested", "reason": "未测拒赔/补件/第三方调减/报销返还或跨店"}])
        checkpoint.finish(claim_sources={"source_repair_case_id": source_id, "source_quote_id": sources["quote_id"],
            "source_allocation_id": sources["allocation_id"], "source_payment_link_id": sources["payment_link_id"], "source_cash_id": sources["cash_id"],
            "claim_case_id": case_id, "assessment_id": assessment["id"], "transmission_id": f["transmissions"][0]["id"],
            "result_id": result["id"], "reimbursement_approval_id": approval["id"], "customer_payment_id": payment["id"]})
    except Exception as error:
        checkpoint.failed(error)
        raise


REPAIR_FOLLOWON_SCENARIOS = ((SCENARIO, wash_quick_business, 300), (REIMBURSEMENT_SCENARIO, reimbursement_business, 180))
