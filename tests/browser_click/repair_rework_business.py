"""Same-run original-liability rework with a separate actual self-pay result.

Positive writes use visible original forms only. Dependencies, evidence, versions,
and immutable history are explicit; SQLite is opened through the read-only helper.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import SCENARIO as PRESALES, login_as, require, employee_choice
from sales_order_business import SCENARIO as SALE, fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import SCENARIO as PURCHASE, master_form, select_value, checkbox, live_choice
from master_data_business import save_typed
from repair_business import (
    SCENARIO as FIRST_REPAIR, CUSTOMER, MASTER, MATERIAL, PRIMARY_KEYS,
    CASE_FIELDS, TASK_FIELDS, COMMON, INTAKE, REPAIR, one, facts, case_facts,
    task, mutable, submit, responsible, upload, file_choice, form, command, event_added,
)
from repair_followon_business import Checkpoint as BaseCheckpoint, dependencies as first_dependencies, zero_nav

SCENARIO = "repair-rework-hk038"
EXT = "/api/rework-extensions"
PARENTS = (PRESALES, PURCHASE, MASTER, CUSTOMER, SALE, MATERIAL, FIRST_REPAIR)
CONTRACTS = (("HK-038", "返修单", [
    "本次获准原项目、同身份/VIN、责任限额及明确接收人，经另一主管批准并本店承接",
    "本次现场核车凭据和转换事件建立新的v4返修，原责任与新增自费逐行冻结并独立审批/授权",
    "真实纯作业施工质检、正确分摊、仅新增自费到账及接车，原维修资金/库存/历史不变",
]),)
KEYS = {**PRIMARY_KEYS, **{name: "id" for name in (
    "master_work_items", "master_receipts", "rework_source_grants", "rework_grant_decisions",
    "rework_grant_receipts", "intake_rework_requests", "intake_rework_source_lines", "intake_rework_liabilities",
)}, "rework_extensions": "request_id", "rework_quote_scopes": "quote_id", "rework_line_scopes": "line_id"}
REQUEST_FIELDS = {"status", "approved_by", "repair_case_id", "active_source_id", "version", "updated_at"}
GRANT_FIELDS = {"status", "version", "updated_at"}
SCOPE_FIELDS = (
    "definition_version", "from_store_id", "to_store_id", "source_case_id", "source_case_version",
    "source_quote_id", "from_vehicle_id", "to_vehicle_id", "customer_identity_id", "vehicle_identity_id",
    "vin", "source_number", "source_lines", "original_liability_limit_cents", "responsible_name",
    "recipient_id", "recipient_role", "recipient_access_version", "requested_by", "requester_role",
    "requester_access_version", "evidence_id", "reason", "expires_at", "created_at",
)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Checkpoint(BaseCheckpoint):
    def __init__(self, e):
        super().__init__(e, SCENARIO, CONTRACTS)
        self.report["candidate_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.report["planned_pending"] = [{"id": key, "status": "not_tested", "reason": "PDI、现金更正及跨店返修须独立真实来源"}
                                          for key in ("HK-037", "HK-075", "HK-076", "HK-078", "HK-081")]
        self.report["arrival_contract"] = "original_rework_convert_event_and_vehicle_binding_not_appointment_arrival_fact"
        self.save()


class ReworkGuard:
    """All business hashes, exact mutable IDs/columns, and finite appended sources.

    Existing BLOBs stay only in memory. No old table is excluded wholesale.
    """
    def __init__(self, e, label, actor, store, *, append, update=None, cases=(),
                 source=None, request_id=None, grant_id=None, vehicle_id=None, resource_id=None, new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store
        self.append, self.update, self.cases = set(append), update or {}, set(cases)
        self.source, self.request, self.grant = source, request_id, grant_id
        self.vehicle, self.resource, self.kind = vehicle_id, resource_id, new_kind
        require((self.append | self.update.keys()) <= KEYS.keys(), "返修守卫存在未核准表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {name: self.rows(name) for name in self.append | self.update.keys()}

    def rows(self, name):
        return self.e.db.rows(f"SELECT * FROM {name} ORDER BY {KEYS[name]}")

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {name for name in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(name) != after["tables"].get(name)}
        require(changed <= self.append | self.update.keys(), "返修改变无关表：" + str(sorted(changed)))
        owned, request_ids, grant_ids = set(self.cases), {self.request} - {None}, {self.grant} - {None}
        if "flow_cases" in self.append:
            added = [r for r in self.rows("flow_cases") if r["id"] not in {x["id"] for x in self.old["flow_cases"]}]
            require(len(added) == 1 and added[0]["kind"] == self.kind and added[0]["created_by"] == self.actor["id"]
                    and added[0]["parent_id"] is None, "返修创建多余或错误原单")
            owned.add(added[0]["id"])
        for name, ids in (("intake_rework_requests", request_ids), ("rework_source_grants", grant_ids)):
            if name in self.append:
                new = [r for r in self.rows(name) if r["id"] not in {x["id"] for x in self.old[name]}]
                require(len(new) == 1 and new[0]["source_case_id"] == self.source, "返修新授权/申请串原单")
                ids.add(new[0]["id"])
        appended, updated = {}, {}
        for name, old in self.old.items():
            pk, now = KEYS[name], {r[KEYS[name]]: r for r in self.rows(name)}
            old_ids = {r[pk] for r in old}
            updated[name] = []
            for row in old:
                require(row[pk] in now, "返修删除旧事实：" + name)
                columns = {k for k in row if row[k] != now[row[pk]][k]}
                require(columns <= self.update.get(name, {}).get(row[pk], set()), "返修覆盖无关旧行/列：" + name + "/" + str(row[pk]))
                if columns:
                    updated[name].append({"id": row[pk], "columns": sorted(columns)})
            new = [r for k, r in now.items() if k not in old_ids]
            require(not new or name in self.append, "返修更新表出现额外新增行：" + name)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "返修新增事实串店：" + name)
                if "case_id" in row:
                    require(row["case_id"] in owned, "返修新增事实串本单：" + name)
                for key in ("actor_id", "created_by", "requested_by", "approved_by"):
                    if key in row and row[key] is not None:
                        require(row[key] == self.actor["id"], "返修新增事实串经办人：" + name)
                if "source_case_id" in row and row["source_case_id"] is not None:
                    require(row["source_case_id"] == self.source, "返修引用错误原维修")
                if name.startswith("rework_") or name.startswith("intake_rework_"):
                    if "grant_id" in row:
                        require(row["grant_id"] in grant_ids, "返修引用错误授权")
                    if "request_id" in row:
                        require(row["request_id"] in request_ids, "返修引用错误申请")
                if "quote_id" in row:
                    quote = one(self.e, "repair_quotes", row["quote_id"])
                    require(quote["case_id"] in owned or name == "intake_rework_requests" and quote["case_id"] == self.source,
                            "返修引用错误冻结报价")
                if "customer_vehicle_id" in row:
                    require(row["customer_vehicle_id"] == self.vehicle, "返修引用错误客车")
                if "resource_id" in row:
                    require(row["resource_id"] == self.resource, "返修引用错误工位")
            appended[name] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": appended, "updated_columns": updated,
                  "all_unrelated_old_rows_and_other_stores_unchanged": True}
        self.e.observe("rework_original_row_guard", {"label": self.label, **result})
        return result


def dependencies(e, checkpoint):
    fixture, sources, vehicle, customer, _ = first_dependencies(e, checkpoint)
    parents = {name: fixed_dependency(e, checkpoint, name) for name in (PRESALES, PURCHASE, CUSTOMER, SALE)}
    care = next(r for r in parents[CUSTOMER]["partial_requirements"] if r["id"] == "HK-099")
    require(care["local_scope_status"] == "local_scope_passed", "返修缺同轮客车局部来源")
    for key in ("id", "customer_id", "store_id", "vin", "customer_identity_id", "vehicle_identity_id"):
        require(vehicle[key] == care["evidence"]["vehicle"][key], "返修原客车身份改变：" + key)
    provenance = json.loads((Path(e.manifest["evidence_root"]) / "provenance.json").read_bytes())
    for name in ("repair_rework_business.py", "customer_service_business.py", "material_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "返修来源脚本指纹改变：" + name)
    for role in ("service", "manager", "technician", "finance", "inventory"):
        user = e.manifest["users"][fixture[role + "_key"]]
        links = e.db.rows("SELECT * FROM user_stores WHERE user_id=? AND store_id=?", (user["id"], fixture["store_id"]))
        require(len(links) == 1 and links[0]["role"] == user["role"] == role and one(e, "users", user["id"])["active"], "返修缺本人当前店岗位")
    original = facts(e, sources["repair_case_id"])
    require(len(original["settlements"]) == 1 and original["settlements"][0]["quote_id"] == sources["quote_id"], "原维修未冻结唯一实际承担")
    lines = [r for r in original["lines"] if r["quote_id"] == sources["quote_id"] and r["kind"] == "work"]
    require(len(lines) == 1, "本代表例必须明确唯一原责任作业，不默选其他原行")
    line = lines[0]
    work = one(e, "master_work_items", line["work_item_id"])
    require(work["active"] and work["store_id"] == fixture["store_id"] and line["unit"] == "job"
            and line["discount_cents"] == 0 and line["quantity_milli"] == 1000 and line["amount_cents"] > 0
            and line["amount_cents"] == line["unit_price_cents"], "原责任不是明确本店启用的单份原作业")
    resource = one(e, "intake_resources", original["context"][0]["resource_id"])
    require(resource["active"] and resource["resource_type"] == "repair" and resource["active_case_id"] is None,
            "原有限工位不是当前真实空闲维修工位")
    require(not e.db.rows("SELECT id FROM intake_rework_requests WHERE active_source_id=?", (sources["repair_case_id"],)), "原单已有未结束返修")
    fixture["account_id"] = one(e, "flow_payment_links", sources["payment_link_id"])["account_id"]
    account = one(e, "flow_accounts", fixture["account_id"])
    require(account["active"] and account["account_type"] == "bank" and account["store_id"] == fixture["store_id"], "原同轮实际账户不可用")
    require(not e.db.rows("SELECT m.id FROM group_members m JOIN group_identity_links l ON l.identity_id=m.identity_id "
        "WHERE l.local_kind='customer' AND l.local_id=? AND l.store_id=? AND m.active=1", (customer["id"], fixture["store_id"])), "本批客户另有需核对会员计费来源")
    checkpoint.report["source_preconditions"].update(current_original_work=work, selected_source_line=line,
        current_resource=resource, current_account=account, required_parent_scenarios=list(PARENTS),
        synthetic_declared_inputs={"extra_fee_cents": 2000, "labor_cost_cents": 1000, "arrival_odometer_km": 37000})
    checkpoint.save()
    return fixture, sources, vehicle, customer, original, work, line, resource


def grant_facts(e, grant_id):
    row = one(e, "rework_source_grants", grant_id)
    row["source_lines"] = json.loads(row["source_lines"])
    return {"grant": row, "decisions": e.db.rows("SELECT * FROM rework_grant_decisions WHERE grant_id=? ORDER BY id", (grant_id,))}


def grant_receipt(e, request, actor, grant_id, action):
    payload = {k: v for k, v in request.items() if k != "request_id"} if action == "propose" else {
        "id": grant_id, "version": request["version"], **request["values"]}
    if action == "propose":
        # Proposal.model_dump(mode='json') serializes UTC without JS's zero milliseconds.
        payload["expires_at"] = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")
    rows = e.db.rows("SELECT * FROM rework_grant_receipts WHERE request_key=?", (request["request_id"],))
    require(len(rows) == 1 and rows[0]["actor_id"] == actor["id"] and rows[0]["grant_id"] == grant_id
            and rows[0]["digest"] == digest([action, payload]), "原授权回执家族/员工/内容错误")
    return rows[0]


def intake_receipt(e, request, actor, body, action, request_id=None):
    payload = {k: v for k, v in request.items() if k != "request_id"} if action == "rework_extension_create" else {
        "id": request_id, "version": request["version"], **request["values"]}
    rows = e.db.rows("SELECT * FROM intake_command_receipts WHERE request_key=?", (request["request_id"],))
    require(len(rows) == 1 and rows[0]["actor_id"] == actor["id"]
            and rows[0]["digest"] == digest({"operation": "intake_" + action, "payload": payload})
            and json.loads(rows[0]["result"]) == body, "返修接待原回执版本/员工/内容/结果错误")
    return {k: rows[0][k] for k in ("id", "request_key", "digest", "actor_id")}


def repair_receipt(e, request, actor, body, case_id, action):
    values = dict(request["values"])
    if action == "quote":
        # The original service removes an absent member-pricing selection before hashing.
        if values.get("member_pricing") is None:
            values.pop("member_pricing", None)
        for key, default in (("purpose", "service"), ("discount_cents", 0), ("retained_amount_cents", None)):
            values.setdefault(key, default)
        values["lines"] = [{"line_key": None, "source_line_id": None, **r} for r in values["lines"]]
    if action == "allocate":
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        values["allocations"] = [{"due_date": day, "payer_id": None, "payer_name": "", **r} for r in values["allocations"]]
    rows = e.db.rows("SELECT * FROM flow_request_receipts WHERE request_key=?", (request["request_id"],))
    require(len(rows) == 1 and rows[0]["actor_id"] == actor["id"] and rows[0]["case_id"] == body["id"] == case_id
            and rows[0]["digest"] == digest({"operation": "repair_v3_" + action,
                "payload": {"id": case_id, "version": request["version"], "values": values}}), "返修原维修回执家族/双行默认值/版本错误")
    return {k: rows[0][k] for k in ("id", "request_key", "digest", "actor_id", "case_id")}


async def original_read(e, context, credentials, fixture, role, route, path, title):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, fixture["store_id"])
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原返修页面未实际读到当前单")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    return actor, body


async def rework_owner(e, context, credentials, fixture, rework_id, key, role):
    request = one(e, "intake_rework_requests", rework_id)
    original = task(case_facts(e, request["case_id"]), key)
    selected = e.manifest["users"][fixture[role + "_key"]]
    info = {"task_id": original["id"], "key": key, "assignee_id": selected["id"], "handoff_needed": original["assignee_id"] != selected["id"]}
    require(original["role"] == role, "返修交接不是原责任岗位任务")
    if info["handoff_needed"]:
        manager, _ = await original_read(e, context, credentials, fixture, "manager", f'case/{request["case_id"]}',
            f'/api/flow/cases/{request["case_id"]}', case_facts(e, request["case_id"])["case"]["title"])
        button = e.page.locator(f'#main [data-act="assign"][data-id="{original["id"]}"]')
        await expect(button).to_be_visible()
        await e.click(f'#main [data-act="assign"][data-id="{original["id"]}"]', "主管交接指定本店返修原任务")
        await employee_choice(e, selected)
        reason = "本次混合责任返修由明确原岗位员工本人办理"
        await e.fill('#modal [name="reason"]', reason, "记录原责任任务交接依据")
        guard = ReworkGuard(e, "rework_task_handoff", manager, fixture["store_id"], append={"flow_events", "audit_logs"},
            update={"flow_cases": {request["case_id"]: {"updated_at", "version"}}, "flow_tasks": {original["id"]: TASK_FIELDS}}, cases={request["case_id"]})
        _, _, native, posted = await submit(e, f'/api/flow/tasks/{original["id"]}/assign', f'/api/flow/cases/{request["case_id"]}', fixture["store_id"], protection=guard)
        require(posted == {"version": original["version"], "assignee_id": selected["id"], "reason": reason}, "原AssignInput不是精确三字段")
        info["native"] = native
    actor, view = await original_read(e, context, credentials, fixture, role, f"service-intake/reworks/{rework_id}",
        f"{INTAKE}/reworks/{rework_id}", case_facts(e, request["case_id"])["case"]["title"])
    require(view["id"] == rework_id and view["case_id"] == request["case_id"]
            and task(case_facts(e, request["case_id"]), key)["assignee_id"] == actor["id"], "返修待办不是当前原单本人")
    return actor, view, info


async def extra_work(e, context, credentials, fixture, token):
    manager = await login_as(e, context, credentials, fixture["manager_key"], "masters/work_items", fixture["store_id"])
    await expect(e.page.locator("#main h1")).to_have_text("作业项目")
    await master_form(e, "work_items", "作业项目")
    guard = ReworkGuard(e, "rework_create_extra_work", manager, fixture["store_id"], append={"master_work_items", "master_receipts", "audit_logs"})
    work, native = await save_typed(e, manager, fixture["store_id"], "work_items", {"code": "RW" + token, "name": "合成返修新增自费作业" + token,
        "active": True, "billing_unit": "job", "standard_minutes": 10, "standard_fee_cents": "20.00", "warranty_days": 0})
    native["source_guard"] = guard.finish()
    require(work["standard_fee_cents"] == 2000 and work["store_id"] == fixture["store_id"] and work["active"], "新自费作业未通过原UI建立")
    return work, native


async def authorization(e, context, credentials, fixture, sources, vehicle, original, line, resource, token):
    store, source_id = fixture["store_id"], sources["repair_case_id"]
    service, _ = await original_read(e, context, credentials, fixture, "service", f"repair-orders/{source_id}", f"{REPAIR}/{source_id}", original["case"]["title"])
    source_proof = await upload(e, source_id, service, "evidence", "rework-source-" + token + ".txt",
        f"合成核实本次原作业缺陷：原单{source_id} 原行{line['id']} 同VIN {vehicle['vin']}，只承担该原项目，新增作业另收费。", store)
    await zero_nav(e, "rework-extensions", EXT + "/grants", "原责任与新增自费返修")
    await e.click('#main [data-act="rework-new"]', "申请本次明确原项目责任授权")
    await expect(e.page.locator("#modal-title")).to_have_text("申请本次原责任授权")
    await select_value(e, '#modal [name="source_case_id"]', source_id, "明确同次已接车维修原单")
    await expect(e.page.locator(f'#modal [name="source_line"][value="{line["id"]}"]')).to_be_visible()
    await expect(e.page.locator("#rework-source-details")).to_contain_text(vehicle["vin"])
    await checkbox(e, f'#modal [name="source_line"][value="{line["id"]}"]', True, "选择本次核实的原责任作业")
    await select_value(e, '#modal [name="to_store_id"]', store, "明确本次原店接收")
    await select_value(e, '#modal [name="to_vehicle_id"]', vehicle["id"], "明确原身份和同VIN客车")
    await select_value(e, '#modal [name="recipient_id"]', service["id"], "明确本店原服务顾问接收人")
    await select_value(e, '#modal [name="evidence_id"]', source_proof["file"]["id"], "明确原店本次责任核验原件")
    await expect(e.page.locator('#modal [name="source_line"]:checked')).to_have_count(1)
    await e.fill('#modal [name="limit"]', fen_text(line["amount_cents"]), "明确不向客户再收费的原责任限额")
    expiry = (datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    await e.fill('#modal [name="expires"]', expiry, "明确本次两天内接收期限")
    await e.fill('#modal [name="reason"]', "合成核实原作业缺陷，限原行责任；本次20元新增作业另取客户授权", "说明原责任与新增范围")
    current_source = facts(e, source_id)
    guard = ReworkGuard(e, "rework_propose_grant", service, store, append={"rework_source_grants", "rework_grant_receipts"}, source=source_id)
    body, _, native, posted = await submit(e, EXT + "/grants", EXT + "/grants/*", store, 201, protection=guard)
    g = grant_facts(e, body["id"])
    require(posted["source_case_id"] == source_id and posted["source_case_version"] == current_source["case"]["version"]
            and posted["source_line_ids"] == [line["id"]] and posted["to_store_id"] == store
            and posted["to_vehicle_id"] == vehicle["id"] and posted["recipient_id"] == service["id"]
            and posted["original_liability_limit_cents"] == line["amount_cents"] and posted["evidence_id"] == source_proof["file"]["id"], "原授权输入/当前源版本/限额错误")
    grant = g["grant"]
    sender = one(e, "users", service["id"])
    expected_lines = [{k: line[k] for k in ("id", "code", "name", "quantity_milli")}]
    require(grant["status"] == "pending" and grant["version"] == 1 and grant["definition_version"] == 1 and not g["decisions"]
            and grant["source_lines"] == expected_lines and grant["source_quote_id"] == sources["quote_id"]
            and grant["from_vehicle_id"] == grant["to_vehicle_id"] == vehicle["id"] and grant["vin"] == vehicle["vin"]
            and grant["from_store_id"] == grant["to_store_id"] == store and grant["recipient_id"] == grant["requested_by"] == service["id"], "原责任授权未冻结具体原单/身份/接收人")
    require(grant["recipient_role"] == grant["requester_role"] == service["role"] == "service"
            and grant["recipient_access_version"] == grant["requester_access_version"] == sender["access_version"]
            and datetime.fromisoformat(grant["expires_at"]) > datetime.fromisoformat(grant["created_at"]),
            "原授权未冻结当前实际岗位/权限版本/接收期限")
    require(all(grant[k] == vehicle[k] for k in ("customer_identity_id", "vehicle_identity_id")), "授权共享身份不是原车身份")
    canonical = {k: grant[k] for k in SCOPE_FIELDS}
    for key in ("expires_at", "created_at"):
        canonical[key] = datetime.fromisoformat(canonical[key]).isoformat()
    require(digest(canonical) == grant["scope_digest"], "原授权冻结摘要不匹配")
    native["receipt"] = grant_receipt(e, posted, service, grant["id"], "propose")
    manager, current = await original_read(e, context, credentials, fixture, "manager", f'rework-extensions/{grant["id"]}',
        f'{EXT}/grants/{grant["id"]}', "核对原责任授权")
    require(manager["id"] != grant["requested_by"] and current["version"] == grant["version"], "原授权不是另一主管独立审核")
    await e.click('#main [data-act="rework-decide"][data-key="approve"]', "另一主管独立批准具体原责任")
    await expect(e.page.locator("#modal-title")).to_have_text("独立批准本次原责任")
    await e.fill('#modal [name="reason"]', "本人核对原作业、同身份VIN、指定接收人与原责任限额，新增自费另行授权", "记录另一主管原责任复核")
    guard = ReworkGuard(e, "rework_approve_grant", manager, store, append={"rework_grant_decisions", "rework_grant_receipts"},
        update={"rework_source_grants": {grant["id"]: GRANT_FIELDS}}, grant_id=grant["id"])
    approved, _, approval_native, posted = await submit(e, f'{EXT}/grants/{grant["id"]}/actions/approve', f'{EXT}/grants/{grant["id"]}', store, protection=guard)
    after = grant_facts(e, grant["id"])
    decision = after["decisions"][0]
    require(posted["version"] == grant["version"] and approved["version"] == after["grant"]["version"] > grant["version"]
            and after["grant"]["status"] == "approved" and decision["action"] == "approve"
            and decision["previous_version"] == grant["version"] and decision["actor_id"] == manager["id"]
            and decision["scope_digest"] == grant["scope_digest"], "原授权独立批准/版本/责任摘要错误")
    require(len(after["decisions"]) == 1 and all(after["grant"][key] == grant[key] for key in SCOPE_FIELDS), "主管批准改写冻结责任范围")
    approval_native["receipt"] = grant_receipt(e, posted, manager, grant["id"], "approve")
    service, current = await original_read(e, context, credentials, fixture, "service", f'rework-extensions/{grant["id"]}',
        f'{EXT}/grants/{grant["id"]}', "核对原责任授权")
    require(current["can_receive"] and current["version"] == after["grant"]["version"], "指定本店接收人未获当前授权")
    await e.click('#main [data-act="rework-receive"]', "指定员工明确领用原责任授权")
    await expect(e.page.locator("#modal-title")).to_have_text("核对并建立本店返修申请")
    await select_value(e, '#modal [name="resource"]', resource["name"] + " · " + resource["code"], "选择本轮有限真实空闲维修工位")
    await e.fill('#modal [name="reason"]', "本次原作业责任返修及明确20元新增自费作业，实际到店再逐位核VIN", "记录承接原责任与新需求")
    guard = ReworkGuard(e, "rework_receive_grant", service, store,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "business_entity_case_contexts", "intake_command_receipts",
                "intake_rework_requests", "intake_rework_source_lines", "rework_extensions", "rework_grant_decisions"},
        update={"rework_source_grants": {grant["id"]: GRANT_FIELDS}}, source=source_id, grant_id=grant["id"],
        vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="service_intake")
    received, _, receive_native, posted = await submit(e, EXT + "/requests", INTAKE + "/reworks/*", store, 201, protection=guard)
    r = one(e, "intake_rework_requests", received["id"])
    extension = e.db.rows("SELECT * FROM rework_extensions WHERE request_id=?", (r["id"],))
    lines = e.db.rows("SELECT * FROM intake_rework_source_lines WHERE request_id=? ORDER BY id", (r["id"],))
    consumed = grant_facts(e, grant["id"])
    require(posted["grant_id"] == grant["id"] and posted["grant_version"] == after["grant"]["version"]
            and posted["resource_id"] == resource["id"] and r["status"] == "requested"
            and r["requested_by"] == service["id"] and r["source_case_id"] == source_id and r["source_quote_id"] == sources["quote_id"]
            and r["active_source_id"] == source_id and r["repair_case_id"] is None and len(extension) == len(lines) == 1
            and lines[0]["source_line_id"] == line["id"] and extension[0]["grant_digest"] == grant["scope_digest"]
            and extension[0]["grant_id"] == grant["id"] and extension[0]["actor_id"] == service["id"]
            and consumed["grant"]["status"] == "consumed" and [d["action"] for d in consumed["decisions"]] == ["approve", "consume"], "原授权领用/独立返修申请错误")
    require(consumed["decisions"][0] == after["decisions"][0] and consumed["decisions"][1]["actor_id"] == service["id"]
            and consumed["decisions"][1]["previous_version"] == after["grant"]["version"]
            and consumed["decisions"][1]["scope_digest"] == grant["scope_digest"]
            and consumed["grant"]["version"] > after["grant"]["version"]
            and all(consumed["grant"][key] == grant[key] for key in SCOPE_FIELDS), "指定接收未留下唯一消耗决定或改写授权范围")
    receive_native["receipt"] = intake_receipt(e, posted, service, received, "rework_extension_create")
    return r, {"source_file": source_proof, "proposed": g, "approved": after, "consumed": consumed,
        "extension": extension[0], "source_lines": lines, "native": [native, approval_native, receive_native]}


async def approve_convert(e, context, credentials, fixture, r, vehicle, resource, grant, token):
    store, request_id, intake_id = fixture["store_id"], r["id"], r["case_id"]
    manager, _, owner = await rework_owner(e, context, credentials, fixture, request_id, "intake_liability", "manager")
    require(manager["id"] != r["requested_by"], "本店返修申请存在自批")
    proof = await upload(e, intake_id, manager, "evidence", "rework-liability-" + token + ".txt", "本次合成复核获准原责任，明确原承担主体与新增自费分开。", store)
    await form(e, "approve", intake=True)
    await expect(e.page.locator("#modal-title")).to_have_text("批准内部返修责任")
    require(await e.page.locator('#modal [name="internal_name"]').count() == 0, "扩展返修不应允许篡改冻结责任主体")
    await e.fill('#modal [name="reason"]', "核对本次冻结授权及明确本店接收人，责任额度和新增自费分类保持分离", "主管记录本店独立承接复核")
    await file_choice(e, "evidence_id", proof)
    before = case_facts(e, intake_id)
    guard = ReworkGuard(e, "rework_approve_intake", manager, store, append=COMMON - {"flow_request_receipts"} | {"flow_tasks", "intake_command_receipts", "intake_rework_liabilities"},
        update={**mutable(e, intake_id), "intake_rework_requests": {request_id: REQUEST_FIELDS}}, cases={intake_id}, request_id=request_id)
    body, _, native, posted = await submit(e, f"{INTAKE}/reworks/{request_id}/actions/approve", f"{INTAKE}/reworks/{request_id}", store, protection=guard)
    require(posted["version"] == r["version"] and posted["values"]["internal_name"] == grant["responsible_name"], "承接复核未引用当前申请版本/冻结主体")
    liabilities = e.db.rows("SELECT * FROM intake_rework_liabilities WHERE request_id=?", (request_id,))
    require(len(liabilities) == 1 and liabilities[0]["approved_by"] == manager["id"] and liabilities[0]["internal_name"] == grant["responsible_name"]
            and liabilities[0]["evidence_id"] == proof["file"]["id"] and body["status"] == "approved", "返修责任审批原事实错误")
    native["receipt"] = intake_receipt(e, posted, manager, body, "rework_approve", request_id)
    native["event"] = event_added(before, case_facts(e, intake_id), "intake_rework_approve", manager)
    service, _, convert_owner = await rework_owner(e, context, credentials, fixture, request_id, "intake_rework_convert", "service")
    arrival = await upload(e, intake_id, service, "evidence", "rework-arrival-" + token + ".txt",
        f"本次独立合成返修现场逐位VIN {vehicle['vin']}，明确里程37000公里，原责任和新增自费同车。", store)
    current = one(e, "intake_rework_requests", request_id)
    before = case_facts(e, intake_id)
    await form(e, "convert", intake=True)
    await expect(e.page.locator("#modal-title")).to_have_text("建立本次维修明细")
    await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "本次现场逐位核对同VIN")
    await e.fill('#modal [name="odometer_km"]', "37000", "记录本次明确现场里程")
    await e.fill('#modal [name="due_date"]', datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(), "明确本次预计交接日")
    await file_choice(e, "evidence_id", arrival)
    matching_vins = e.db.rows("SELECT id FROM care_customer_vehicles WHERE store_id=? AND vin=? ORDER BY id", (store, vehicle["vin"]))
    require([v["id"] for v in matching_vins] == [vehicle["id"]], "返修本店VIN锁必须唯一指向本次原CV")
    guard = ReworkGuard(e, "rework_actual_arrival_convert", service, store,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_command_receipts", "intake_repair_contexts", "intake_vehicle_bindings", "business_entity_case_contexts"},
        update={**mutable(e, intake_id, vehicle_id=vehicle["id"]), "intake_rework_requests": {request_id: REQUEST_FIELDS}}, cases={intake_id},
        source=r["source_case_id"], request_id=request_id, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="repair")
    converted, _, convert_native, posted = await submit(e, f"{INTAKE}/reworks/{request_id}/actions/convert", f"{INTAKE}/reworks/{request_id}", store, protection=guard)
    repair = facts(e, converted["repair_case_id"])
    event = event_added(before, case_facts(e, intake_id), "intake_rework_convert", service)
    require(posted["version"] == current["version"] and event["detail"] == posted["values"]
            and event["detail"]["checked_vin"] == vehicle["vin"] and event["detail"]["odometer_km"] == 37000
            and event["detail"]["evidence_id"] == arrival["file"]["id"], "本次实际核车/里程/凭据未保存原转换事件")
    require(repair["case"]["flow_version"] == 4 and repair["case"]["state"] == "assessment"
            and repair["context"][0]["profile"] == "rework" and repair["context"][0]["rework_id"] == request_id
            and repair["context"][0]["appointment_id"] is None and repair["binding"][0]["customer_vehicle_id"] == vehicle["id"]
            and repair["binding"][0]["vin"] == vehicle["vin"] and repair["binding"][0]["evidence_id"] == arrival["file"]["id"]
            and not repair["quotes"] and not repair["payments"] and not repair["stock"]
            and converted["status"] == "converted" and case_facts(e, intake_id)["case"]["state"] == "working", "新返修转换/原车辆绑定/结果边界错误")
    require(repair["case"]["id"] != r["source_case_id"] and repair["case"]["owner_id"] == repair["case"]["created_by"] == service["id"]
            and repair["case"]["customer_id"] == vehicle["customer_id"] and repair["context"][0]["resource_id"] == resource["id"], "新返修未独立原单/本人/客户/真实工位")
    require(all(repair["binding"][0][k] == vehicle[k] for k in ("customer_identity_id", "vehicle_identity_id")), "返修转换替换原共享身份")
    convert_native.update(receipt=intake_receipt(e, posted, service, converted, "rework_convert", request_id), event=event)
    return repair, {"liability": liabilities[0], "actual_arrival_event": event, "arrival_binding": repair["binding"][0],
        "arrival_fact_table_used": False, "files": [proof, arrival], "task_owners": [owner, convert_owner], "native": [native, convert_native]}


async def scoped_command(e, fixture, case_id, action, actor, *, intake_id, request_id, path=None):
    before = facts(e, case_id)
    owner = task(before, {"quote": "repair_quote", "allocate": "repair_allocate", "release": "repair_release"}[action])
    require(owner["assignee_id"] == actor["id"] and owner["role"] == actor["role"] == ("manager" if action == "allocate" else "service"),
            "本次返修不是原任务当前岗位本人")
    appended = COMMON | {"flow_tasks"} | {"quote": {"repair_quotes", "repair_lines", "rework_quote_scopes", "rework_line_scopes"},
        "allocate": {"repair_settlements", "repair_allocations"}, "release": {"intake_resource_uses"}}[action]
    update = mutable(e, case_id, resource_id=before["context"][0]["resource_id"] if action == "release" else None,
        vehicle_id=before["binding"][0]["customer_vehicle_id"] if action == "release" else None)
    if action == "release":
        update["flow_cases"][intake_id] = CASE_FIELDS
        update["flow_tasks"].update({t["id"]: TASK_FIELDS for t in case_facts(e, intake_id)["tasks"]})
        update["intake_rework_requests"] = {request_id: REQUEST_FIELDS}
    guard = ReworkGuard(e, "rework_scoped_" + action, actor, fixture["store_id"], append=appended, update=update,
        cases={case_id, intake_id}, request_id=request_id, vehicle_id=before["binding"][0]["customer_vehicle_id"], resource_id=before["context"][0]["resource_id"])
    body, view, native, posted = await submit(e, path or f"{REPAIR}/{case_id}/actions/{action}", f"{REPAIR}/{case_id}", fixture["store_id"], protection=guard)
    after = facts(e, case_id)
    require(posted["version"] == before["case"]["version"] and body["id"] == view["id"] == case_id
            and body["version"] == after["case"]["version"] > before["case"]["version"], "原返修提交缺当前版本/同单响应")
    for key in ("quotes", "lines", "approvals", "authorizations", "stock", "quality", "settlements", "allocations", "payments", "repair_payments", "moves"):
        require(after[key][:len(before[key])] == before[key], "返修覆盖本单旧历史：" + key)
    native.update(receipt=repair_receipt(e, posted, actor, body, case_id, action),
        event=event_added(before, after, "repair_v4_" + action, actor), submitted_values=posted["values"])
    await expect(e.page.locator("#main h1")).to_have_text(body["title"])
    return after, view, native


async def normal_command(e, fixture, case_id, action, actor):
    # Observe the same native response consumed by the existing original helper.
    # This does not submit another request or replay any captured body.
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"{REPAIR}/{case_id}/actions/{action}") as pending:
        after, view, native = await command(e, fixture, case_id, action, actor)
    response = await pending.value
    body, posted = await response.json(), response.request.post_data_json
    require(response.status == 200, "返修原动作未成功")
    native["receipt"] = repair_receipt(e, posted, actor, body, case_id, action)
    return after, view, native


async def quote_and_work(e, context, credentials, fixture, repair, r, source_line, original_work, extra, token):
    store, case_id = fixture["store_id"], repair["case"]["id"]
    service, view, owner = await responsible(e, context, credentials, fixture, case_id, "repair_quote", "service")
    require(view["service_intake"]["internal_only"] is False and view["service_intake"]["rework_extension"]["definition_version"] == 1,
            "本批不是原责任加新增自费扩展返修")
    await expect(e.page.locator('#main [data-act="repair-action"][data-key="quote"]')).to_be_visible()
    await e.click('#main [data-act="repair-action"][data-key="quote"]', "分别填写原责任与新增自费行")
    await expect(e.page.locator("#modal-title")).to_have_text("原责任与新增自费逐行报价")
    for index, (work, scope, price) in enumerate(((original_work, "original_liability", source_line["amount_cents"]), (extra, "customer_extra", 2000))):
        if index:
            await e.click('#modal [data-act="rework-add-line"]', "增加独立的新自费作业行")
        line = e.page.locator('#modal [data-rework-line]').nth(index)
        for key, value in (("source", "work:" + str(work["id"])), ("charge_scope", scope), ("source_line_id", source_line["id"] if not index else "")):
            e.action("select", "明确本行原项目/责任分类", field=key, value=str(value))
            await line.locator(f'[name="{key}"]').select_option(str(value))
            await expect(line.locator(f'[name="{key}"]')).to_have_value(str(value))
        e.action("fill", "核对单份本行实际合成作业报价", work_item_id=work["id"], quantity="1.000", price=fen_text(price))
        await line.locator('[name="quantity"]').fill("1.000")
        await line.locator('[name="price"]').fill(fen_text(price))
    await e.fill('#modal [name="discount"]', "0.00", "本版原责任和新增作业不另优惠")
    await e.fill('#modal [name="reason"]', "原责任获准项目免客户再付，本次新增20元自费纯作业逐行另授权", "明确本次独立诊断范围")
    repair, _, quoted = await scoped_command(e, fixture, case_id, "quote", service, intake_id=r["case_id"], request_id=r["id"], path=f"{EXT}/orders/{case_id}/quote")
    q = repair["quotes"][0]
    scopes = e.db.rows("SELECT * FROM rework_line_scopes WHERE quote_id=? ORDER BY line_id", (q["id"],))
    summary = e.db.rows("SELECT * FROM rework_quote_scopes WHERE quote_id=?", (q["id"],))
    require(len(repair["quotes"]) == 1 and len(repair["lines"]) == len(scopes) == 2 and len(summary) == 1
            and q["amount_cents"] == source_line["amount_cents"] + 2000 and not repair["payments"] and not repair["stock"], "返修双行报价/零提前结果错误")
    for index, work in enumerate((original_work, extra)):
        line, scope = repair["lines"][index], scopes[index]
        require(line["work_item_id"] == work["id"] and line["kind"] == "work" and line["unit"] == "job" and line["quantity_milli"] == 1000
                and scope["line_id"] == line["id"] and scope["charge_scope"] == ("original_liability" if not index else "customer_extra")
                and scope["source_line_id"] == (source_line["id"] if not index else None), "返修原/新增行分类未正确冻结")
        require(line["unit_price_cents"] == line["amount_cents"] == (source_line["amount_cents"] if not index else 2000)
                and line["discount_cents"] == 0 and line["item_id"] is None, "两行报价有未知优惠、金额或材料")
    canonical_scopes = [{"charge_scope": s["charge_scope"], "source_line_id": s["source_line_id"]} for s in scopes]
    require(summary[0]["request_id"] == r["id"] and summary[0]["original_liability_cents"] == source_line["amount_cents"]
            and summary[0]["customer_extra_cents"] == 2000 and summary[0]["digest"] == digest({"quote_digest": q["digest"], "scopes": canonical_scopes}), "双行责任冻结摘要/金额错误")
    manager, _, price_owner = await responsible(e, context, credentials, fixture, case_id, "repair_price_" + str(q["id"]), "manager")
    await form(e, "price_approve")
    await e.fill('#modal [name="minimum"]', fen_text(q["amount_cents"]), "主管独立逐行核对全部本版报价")
    await checkbox(e, '#modal [name="allow_below_minimum"]', False, "不默认授权低价例外")
    await e.fill('#modal [name="reason"]', "本人复核原责任行和本次新增20元自费行的数量、金额与分类", "记录不同主管价格复核")
    repair, _, price_native = await normal_command(e, fixture, case_id, "price_approve", manager)
    require(repair["approvals"][0]["actor_id"] == manager["id"] != q["created_by"], "返修报价存在自批")
    service, _, auth_owner = await responsible(e, context, credentials, fixture, case_id, "repair_authorize_" + str(q["id"]), "service")
    auth = await upload(e, case_id, service, "authorization", "rework-auth-" + token + ".txt",
        f"合成客户核对本版{q['id']} 摘要{q['digest']}，原责任不再收费，只授权本次新增20元。", store)
    await form(e, "authorize"); await file_choice(e, "evidence_id", auth)
    repair, _, auth_native = await normal_command(e, fixture, case_id, "authorize", service)
    require(repair["authorizations"][0]["quote_id"] == q["id"] and repair["authorizations"][0]["quote_digest"] == q["digest"]
            and repair["authorizations"][0]["evidence_id"] == auth["file"]["id"], "返修客户未授权当前分类报价")
    technician, _, work_owner = await responsible(e, context, credentials, fixture, case_id, "repair_work", "technician")
    await form(e, "start")
    await e.fill('#modal [name="result"]', "同VIN车辆实际入位，开始原责任和新增自费两项纯作业", "技师本人记录实际开工")
    repair, _, start_native = await normal_command(e, fixture, case_id, "start", technician)
    require(repair["case"]["data"].get("started") and one(e, "intake_resources", repair["context"][0]["resource_id"])["active_case_id"] == case_id
            and repair["resource_uses"][0]["action"] == "acquire", "返修实际工位/开工未发生")
    await form(e, "finish")
    await e.fill('#modal [name="result"]', "两项合成纯作业实际完成，原缺陷已处理，本次不领材料", "记录两行实际施工完成")
    repair, _, finish_native = await normal_command(e, fixture, case_id, "finish", technician)
    require(repair["case"]["state"] == "quality" and not repair["stock"] and not repair["moves"], "返修施工未完成或误生成材料")
    service, _, quality_owner = await responsible(e, context, credentials, fixture, case_id, "repair_quality", "service")
    inspection = await upload(e, case_id, service, "inspection", "rework-quality-" + token + ".txt", "本次合成原缺陷与新增作业实查合格，未复用旧检查凭据。", store)
    await form(e, "quality")
    await e.fill('#modal [name="result"]', "原缺陷处理和新增作业实查合格，同VIN安全检查完成", "服务顾问独立质检")
    await select_value(e, '#modal [name="outcome"]', "合格", "明确本次实际质检结果")
    await file_choice(e, "evidence_id", inspection)
    repair, _, quality_native = await normal_command(e, fixture, case_id, "quality", service)
    require(repair["case"]["state"] == "settling" and len(repair["quality"]) == 1 and repair["quality"][0]["passed"]
            and repair["quality"][0]["actor_id"] != technician["id"] and repair["quality"][0]["quote_id"] == q["id"]
            and not repair["payments"] and not repair["settlements"], "返修实际质检/未提前收费错误")
    return repair, {"quote": q, "line_scopes": scopes, "quote_scope": summary[0], "files": [auth, inspection],
        "native": [quoted, price_native, auth_native, start_native, finish_native, quality_native],
        "task_owners": [owner, price_owner, auth_owner, work_owner, quality_owner]}


async def settle_release(e, context, credentials, fixture, repair, r, source_line, token):
    store, case_id = fixture["store_id"], repair["case"]["id"]
    manager, _, allocate_owner = await responsible(e, context, credentials, fixture, case_id, "repair_allocate", "manager")
    proof = await upload(e, case_id, manager, "evidence", "rework-allocation-" + token + ".txt", "合成核对冻结分类，原责任内部承担，本次新增20元仅客户承担。", store)
    await expect(e.page.locator('#main [data-act="repair-action"][data-key="allocate"]')).to_be_visible()
    await e.click('#main [data-act="repair-action"][data-key="allocate"]', "主管核对冻结双行承担")
    await expect(e.page.locator("#modal-title")).to_have_text("核对冻结行承担")
    await e.fill('#modal [name="labor_cost"]', "10.00", "记录本次明确合成人工成本")
    await file_choice(e, "evidence_id", proof)
    repair, view, allocated = await scoped_command(e, fixture, case_id, "allocate", manager, intake_id=r["case_id"], request_id=r["id"])
    allocations = {a["payer_type"]: a for a in repair["allocations"]}
    liability = e.db.rows("SELECT * FROM intake_rework_liabilities WHERE request_id=?", (r["id"],))[0]
    require(len(repair["allocations"]) == 2 and set(allocations) == {"customer", "internal"}
            and allocations["internal"]["amount_cents"] == source_line["amount_cents"] and allocations["internal"]["payer_name"] == liability["internal_name"]
            and allocations["customer"]["amount_cents"] == 2000 and repair["settlements"][0]["labor_cost_cents"] == 1000
            and repair["case"]["cost_cents"] == 1000 and view["customer_due_cents"] == view["receivable_cents"] == 2000
            and next(a for a in view["allocations"] if a["payer_type"] == "internal")["due_cents"] == 0
            and not repair["payments"] and not repair["cash"], "冻结原责任被客户重复承担或提前产生款")
    allocation = allocations["customer"]
    finance, _, receive_owner = await responsible(e, context, credentials, fixture, case_id, "repair_receive_" + str(allocation["id"]), "finance")
    payment_proof = await upload(e, case_id, finance, "evidence", "rework-payment-" + token + ".txt", "合成本次客户只付新增自费20元，原责任免重复收费。", store)
    selector = f'#main [data-act="repair-action"][data-key="receive"][data-id="{allocation["id"]}"]'
    await expect(e.page.locator(selector)).to_be_visible()
    await e.click(selector, "财务本人登记仅新增自费实际到账")
    await expect(e.page.locator("#modal-title")).to_have_text("登记实际到账")
    await e.fill('#modal [name="amount"]', "20.00", "明确本次新增自费实际到账额")
    account = one(e, "flow_accounts", fixture["account_id"])
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference = "REWORK-PAY-" + token
    await e.fill('#modal [name="reference"]', reference, "记录本次独立新增自费原流水号")
    await file_choice(e, "evidence_id", payment_proof)
    repair, view, received = await normal_command(e, fixture, case_id, "receive", finance)
    require(len(repair["payments"]) == len(repair["cash"]) == len(repair["repair_payments"]) == 1
            and received["submitted_values"]["allocation_id"] == allocation["id"]
            and view["receivable_cents"] == view["customer_due_cents"] == 0 and repair["case"]["state"] == "settling"
            and not repair["case"]["data"].get("released_date"), "实际新增自费到账重复/串承担/提前交车")
    p, link, cash = repair["repair_payments"][0], repair["payments"][0], repair["cash"][0]
    require(p["allocation_id"] == allocation["id"] and p["payment_link_id"] == link["id"] and p["evidence_id"] == payment_proof["file"]["id"]
            and link["cash_id"] == cash["id"] and link["direction"] == cash["direction"] == "in"
            and link["amount_cents"] == cash["amount_cents"] == 2000 and link["account_id"] == account["id"]
            and cash["account"] == account["name"] and link["reference"] == cash["voucher_no"] == reference
            and cash["created_by"] == finance["id"] and cash["approval_state"] == "approved" and link["original_id"] is None,
            "新增自费实际原款/账户/凭据错误")
    service, _, release_owner = await responsible(e, context, credentials, fixture, case_id, "repair_release", "service")
    release_proof = await upload(e, case_id, service, "evidence", "rework-release-" + token + ".txt", "合成客户核验同VIN后实际接车，新增自费结清，原责任没有重复收费。", store)
    await form(e, "release"); await file_choice(e, "evidence_id", release_proof)
    repair, view, released = await scoped_command(e, fixture, case_id, "release", service, intake_id=r["case_id"], request_id=r["id"])
    closed = one(e, "intake_rework_requests", r["id"])
    parent = case_facts(e, r["case_id"])
    require(repair["case"]["state"] == "completed" and repair["case"]["data"].get("released_date")
            and closed["status"] == "completed" and closed["active_source_id"] is None and parent["case"]["state"] == "completed"
            and all(t["status"] != "open" for t in repair["tasks"] + parent["tasks"])
            and one(e, "intake_resources", repair["context"][0]["resource_id"])["active_case_id"] is None
            and [u["action"] for u in repair["resource_uses"]] == ["acquire", "release"]
            and len(repair["payments"]) == len(repair["cash"]) == 1 and not repair["stock"] and not repair["moves"], "返修实际接车/父申请/工位未完成或重复收费")
    before_refresh = e.business_snapshot("before_completed_rework_refresh")
    require(urlsplit(e.page.url).fragment == f"repair-orders/{case_id}", "原接车后不在该返修页面")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{REPAIR}/{case_id}") as pending:
        e.action("refresh", "本人刷新已完成返修，核原接车与独立原款")
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    refreshed = await response.json()
    require(response.status == 200, "已完成返修原刷新读取失败")
    await expect(e.page.locator("#main h1")).to_have_text(repair["case"]["title"])
    e.business_unchanged(before_refresh, "after_completed_rework_refresh")
    require(refreshed["state"] == "completed" and refreshed["customer_due_cents"] == 0 and facts(e, case_id) == repair,
            "返修刷新未保留原接车结果或生成重复事实")
    return repair, {"allocations": allocations, "settlement": repair["settlements"][0], "repair_payment": p,
        "payment_link": link, "cash": cash, "closed_request": closed, "completed_intake": parent,
        "files": [proof, payment_proof, release_proof], "native": [allocated, received, released],
        "task_owners": [allocate_owner, receive_owner, release_owner], "no_internal_cash": True}


async def repair_rework_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        checkpoint.start("HK-038")
        fixture, sources, vehicle, customer, original, original_work, source_line, resource = dependencies(e, checkpoint)
        token = uuid.uuid4().hex[:8].upper()
        extra, work_native = await extra_work(e, context, credentials, fixture, token)
        checkpoint.note({"new_selfpay_work": extra, "native_work_creation": work_native})
        request, authorization_evidence = await authorization(e, context, credentials, fixture, sources, vehicle, original, source_line, resource, token)
        # Responsibility upload appends a legitimate source event/file; from here the entire old source is immutable.
        source_baseline = facts(e, sources["repair_case_id"])
        checkpoint.note({"request": request, "authorization": authorization_evidence, "protected_original_repair_id": sources["repair_case_id"]})
        repair, conversion = await approve_convert(e, context, credentials, fixture, request, vehicle, resource,
            authorization_evidence["consumed"]["grant"], token)
        checkpoint.note({"conversion": conversion, "new_repair_case_id": repair["case"]["id"]})
        repair, construction = await quote_and_work(e, context, credentials, fixture, repair, request, source_line, original_work, extra, token)
        checkpoint.note({"construction": construction, "quality_before_money": repair["quality"]})
        repair, settlement = await settle_release(e, context, credentials, fixture, repair, request, source_line, token)
        require(facts(e, sources["repair_case_id"]) == source_baseline, "新返修改写原维修/原款/原库存/历史")
        require(one(e, "care_customer_vehicles", vehicle["id"])["vin"] == vehicle["vin"]
                and repair["case"]["customer_id"] == customer["id"], "返修完成替换原客户/VIN")
        await checkpoint.passed({"source_case_id": sources["repair_case_id"], "source_line": source_line, "new_selfpay_work": extra,
            "authorization": authorization_evidence, "conversion": conversion, "construction": construction,
            "settlement": settlement, "completed_repair": repair, "original_repair_unchanged": True}, conditional=[
            {"check_id": "HK-038-cross-store-rework", "status": "not_tested", "reason": "本例为原店明确接收；跨店授权另验"},
            {"check_id": "HK-038-material-and-external-liability", "status": "not_tested", "reason": "本例纯作业且原责任内部承担，不借原材料/原外部款"},
            {"check_id": "HK-038-expiry-and-withdrawal", "status": "not_tested", "reason": "本次授权在期限内独立批准并消耗，撤销/过期另验"}])
        report_sources = {"customer_id": customer["id"], "customer_vehicle_id": vehicle["id"], "vin": vehicle["vin"],
            "source_case_id": sources["repair_case_id"], "source_quote_id": sources["quote_id"], "source_line_id": source_line["id"],
            "grant_id": authorization_evidence["consumed"]["grant"]["id"], "rework_request_id": request["id"],
            "intake_case_id": request["case_id"], "repair_case_id": repair["case"]["id"], "quote_id": repair["quotes"][0]["id"],
            "resource_id": resource["id"], "customer_allocation_id": settlement["allocations"]["customer"]["id"],
            "internal_allocation_id": settlement["allocations"]["internal"]["id"], "payment_link_id": settlement["payment_link"]["id"],
            "cash_id": settlement["cash"]["id"], "extra_work_item_id": extra["id"], "actual_new_selfpay_cents": 2000}
        checkpoint.finish(rework_sources=report_sources, report_sources=report_sources)
    except Exception as exc:
        checkpoint.failed(exc)
        raise


REPAIR_REWORK_SCENARIOS = ((SCENARIO, repair_rework_business, 600),)
