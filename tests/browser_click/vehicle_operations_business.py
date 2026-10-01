"""Six original vehicle import/physical flows, authored but not self-executed.

The runner supplies an external synthetic DB and credentials. All mutations use
visible original forms. SQL is SELECT-only; unknown POST outcomes stop the run.
"""
from __future__ import annotations

import csv
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as email_policy
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import employee_choice, login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from vehicle_purchase_business import (
    checkbox, command_facts, live_choice, master_form, master_page,
    purchase_facts, response_meta, save_master, select_value, upload,
)

SCENARIO = "vehicle-import-operations-hk019-027-028-030-025-023"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
VP = "/api/vehicle-procurement/orders"
VI = "/api/vehicle-imports"
VO = "/api/vehicle-operations/orders"
CONTRACTS = (
    ("HK-019", "车辆请款导入", "三方原单来源及本次两VIN请款；试跑回滚业务、独立复核、本人确认"),
    ("HK-027", "请款导入车辆发货", "本次confirmed请款manifest、逐VIN真实发运、在途与尚未入库"),
    ("HK-028", "请款导入车辆到货", "原发运和现场库位实际收车；唯一代次、身份、成本及Position"),
    ("HK-030", "车辆店内移库", "同车同代次源位发出、在途、目的位接收及量值守恒"),
    ("HK-025", "车辆其他出库", "明确去向实际出库、原单实际退回新代次，保留旧车和成本"),
    ("HK-023", "车辆采购退回", "原B车采购退运与同原付款账户实际退款分别留事实"),
)
CASE_FIELDS = {"state", "data", "version", "updated_at", "completed_date"}
TASK_FIELDS = {"status", "assignee_id", "due_date", "done_by", "done_at", "version", "updated_at"}
COMMON = {"flow_events", "flow_request_receipts", "audit_logs"}
FILES = {"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}
IMPORT = {"vehicle_import_batches", "vehicle_import_rows", "vehicle_import_claims", "vehicle_import_requests"}
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "flow_request_receipts", "audit_logs",
    "flow_files", "file_security", "file_scan_events", "flow_accounts", "cash_entries",
    "vehicles", "vehicle_positions", "vehicle_position_entries", "vehicle_custodies",
    "group_identities", "group_identity_links", "master_locations", "master_receipts",
    "master_warehouses", "master_suppliers", "master_vehicle_models",
    "vehicle_purchase_orders", "vehicle_purchase_lines", "vehicle_purchase_prices",
    "vehicle_purchase_shipments", "vehicle_purchase_receipts", "vehicle_purchase_movements",
    "vehicle_purchase_returns", "vehicle_purchase_funds_requests", "vehicle_purchase_payments",
    "vehicle_import_batches", "vehicle_import_rows", "vehicle_import_claims",
    "vehicle_import_results", "vehicle_import_requests", "vehicle_operations",
    "vehicle_operation_claims", "vehicle_operation_reviews",
}
PK = {"file_security": "file_id", "vehicle_import_claims": "key"}
HEADERS = {
    "funds": ["source_row", "line_id", "vin", "amount_cents"],
    "ship": ["source_row", "manifest_row_id", "vin", "shipped_date", "expected_date"],
    "receive": ["source_row", "manifest_row_id", "vin", "received_date", "location_id"],
}


def today():
    # The isolated fixture explicitly uses this business timezone on all hosts.
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def rows(e, table):
    require(table in TABLES, "查询表不在车辆来源有限集合")
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {PK.get(table, 'id')}")


def one(e, table, key):
    require(table in TABLES, "查询表不在车辆来源有限集合")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PK.get(table, 'id')}=?", (key,))
    require(len(found) == 1, "原车辆事实不存在或不唯一：" + table + "/" + str(key))
    return found[0]


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        source = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title, _ in CONTRACTS:
            require(source[key]["title"] == title and source[key]["source_review_status"] == "source_reviewed",
                    key + " 原标题或源合同不匹配")
            require(any(c["check_id"] == key + "-business" for c in source[key]["acceptance_checks"]), key + " check_id不匹配")
        self.report = {
            "schema": 1, "scenario": SCENARIO, "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": [r[0] for r in CONTRACTS], "complete": False, "passed": False,
            "execution": "native_browser_original_forms", "human_acceptance": "pending",
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_money_and_physical_inputs": True,
                "production_bank_or_physical_handover_acceptance": False,
                "file_scan": "original_structure_only_not_clamav", "business_entity_policy_acceptance": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": [{"category": "frontend_expected", "status": "not_tested"},
                                 {"category": "simple_flow", "status": "manual_review_pending"},
                                 {"category": "concise_copy", "status": "manual_review_pending"},
                                 {"category": "backend_matches", "status": "not_tested"},
                                 {"category": "hard_bugs", "status": "not_tested"},
                                 {"category": "scope_source_integrity", "status": "not_tested"}],
                    "contract": contract, "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "conditional_checks": []} for key, title, contract in CONTRACTS],
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    async def passed(self, evidence, conditional=()):
        check = self.active["acceptance_checks"][0]
        check.update(status="passed", evidence=evidence)
        for criterion in check["criteria"]:
            if criterion["status"] != "manual_review_pending":
                criterion["status"] = "passed"
        self.active.update(status="passed", evidence_action_end=len(self.e.actions), conditional_checks=list(conditional))
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "车辆六项尚未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=6, passed_requirements=6,
                           conditional_coverage_complete=False, report_sources=sources)
        self.save()
        self.e.observe("vehicle_operations_business_checkpoint", {"path": str(self.path), "scope": self.report["scope"],
            "report_sources": sources, "business_accepted": False})


class Guard:
    """Full DB hashes plus finite old primary-key/column permissions, including bytes."""
    def __init__(self, e, label, actor, store, *, append=(), update=None, cases=(), vins=(), new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store
        self.append, self.update = set(append), update or {}
        require(self.append | self.update.keys() <= TABLES, "车辆Guard表超出已读来源")
        self.cases, self.vins, self.new_kind = set(cases), set(vins), new_kind
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "车辆原动作改变未授权表：" + str(sorted(changed)))
        new_cases = set()
        if "flow_cases" in self.append:
            previous = {r["id"] for r in self.old["flow_cases"]}
            fresh = [r for r in rows(self.e, "flow_cases") if r["id"] not in previous]
            require(len(fresh) == 1 and fresh[0]["kind"] == self.new_kind and fresh[0]["flow_version"] == 2
                    and fresh[0]["created_by"] == self.actor["id"] and fresh[0]["owner_id"] == self.actor["id"], "新增原单非本次唯一原岗位来源")
            new_cases.add(fresh[0]["id"])
        owned = self.cases | new_cases
        added, updated = {}, {}
        for table, old_rows in self.old.items():
            pk = PK.get(table, "id")
            now = {r[pk]: r for r in rows(self.e, table)}
            previous = {r[pk] for r in old_rows}
            updated[table] = []
            for old in old_rows:
                require(old[pk] in now, "旧车辆事实被删除：" + table)
                columns = {k for k in old if old[k] != now[old[pk]][k]}
                require(columns <= set(self.update.get(table, {}).get(old[pk], ())),
                        "旧车辆事实被覆盖：" + table + "/" + str(old[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": old[pk], "columns": sorted(columns)})
            fresh = [r for key, r in now.items() if key not in previous]
            require(not fresh or table in self.append, "仅更新表出现新行：" + table)
            for row in fresh:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "车辆新增事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "车辆新增事实串原单：" + table)
                if "operation_id" in row:
                    require(row["operation_id"] is None or row["operation_id"] in owned, "位置/评审串车辆作业")
                if "batch_id" in row:
                    require(one(self.e, "vehicle_import_batches", row["batch_id"])["case_id"] in owned, "新增导入事实串批次")
                if "row_id" in row and table in {"vehicle_import_claims", "vehicle_import_results"}:
                    source = one(self.e, "vehicle_import_rows", row["row_id"])
                    require(one(self.e, "vehicle_import_batches", source["batch_id"])["case_id"] in owned, "导入Claim/Result串来源")
                if "vin" in row:
                    require(row["vin"] in self.vins, "车辆新增事实VIN无本次来源")
                if table == "group_identities":
                    require(row["kind"] == "vehicle" and row["canonical_key"] in self.vins, "新集团身份不是本次VIN")
                if table == "group_identity_links":
                    require(row["local_kind"] == "vehicle" and one(self.e, "vehicles", row["local_id"])["vin"] in self.vins, "新身份关联无本次实车")
                if table == "vehicle_positions":
                    require(one(self.e, "vehicles", row["vehicle_id"])["vin"] in self.vins, "新Position无本次实车")
                if row.get("vehicle_id") is not None:
                    require(one(self.e, "vehicles", row["vehicle_id"])["vin"] in self.vins, "新增车辆分录无本次VIN原车")
                if table in {"file_security", "file_scan_events"}:
                    require(one(self.e, "flow_files", row["file_id"])["case_id"] in owned, "新扫描串附件")
                for field in ("actor_id", "user_id", "created_by", "requested_by", "prepared_by", "confirmed_by", "approved_by"):
                    if field in row and row[field] is not None and table != "flow_tasks":
                        require(row[field] == self.actor["id"], "新增事实办理员工错误：" + table + "/" + field)
            added[table] = [r[pk] for r in fresh]
        proof = {"label": self.label, "changed_tables": sorted(changed), "appended_ids": added,
                 "updated_columns": updated, "protected_other_tables": True, "protected_old_facts": True}
        self.e.observe("vehicle_original_row_guard", proof)
        return proof


def mutable(e, case_id, *, prices=False, batch_id=None, vehicles=(), funds=(), shipments=(), returns=(), account=None, operation=False):
    result = {"flow_cases": {case_id: CASE_FIELDS | ({"amount_cents"} if prices else set())},
              "flow_tasks": {r["id"]: TASK_FIELDS for r in rows(e, "flow_tasks") if r["case_id"] == case_id}}
    if batch_id is not None:
        result["vehicle_import_batches"] = {batch_id: {"status", "reviewed_by", "confirmed_by", "version", "updated_at"}}
    if funds:
        result["vehicle_purchase_funds_requests"] = {key: {"status", "version", "updated_at"} for key in funds}
    if shipments:
        result["vehicle_purchase_shipments"] = {key: {"status", "active_vin", "version", "updated_at"} for key in shipments}
    if returns:
        result["vehicle_purchase_returns"] = {key: {"status", "active_shipment_id", "approved_by", "version", "updated_at"} for key in returns}
    if account:
        result["flow_accounts"] = {account: {"version", "updated_at"}}
    if vehicles:
        result["vehicles"] = {key: {"approval_state", "location", "updated_at", "version"} for key in vehicles}
        result["vehicle_positions"] = {r["id"]: {"location_id", "status", "version", "updated_at"}
                                        for r in rows(e, "vehicle_positions") if r["vehicle_id"] in vehicles}
        vins = {one(e, "vehicles", key)["vin"] for key in vehicles}
        result["vehicle_custodies"] = {r["id"]: {"version", "generation", "current_vehicle_id", "current_store_id"}
                                       for r in rows(e, "vehicle_custodies") if r["vin"] in vins}
    if operation:
        result["vehicle_operations"] = {case_id: {"status", "received_vehicle_id"}}
        result["vehicle_operation_claims"] = {r["id"]: {"active_vin"} for r in rows(e, "vehicle_operation_claims") if r["case_id"] == case_id}
    return result


async def submit(e, path, actor, store, protection, *, status=200, case_id=None, multipart=False, task_assign=False):
    predicate = lambda r: r.request.method == "GET" and (urlsplit(r.url).path == f"/api/flow/cases/{case_id}"
        if case_id else re.fullmatch(r"/api/flow/cases/\d+", urlsplit(r.url).path))
    async with e.page.expect_response(predicate) as rendered:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "员工确认本次原车辆业务")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"车辆原表单HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await rendered.value
    view = await read.json()
    expected_id = case_id or body.get("case_id") or body.get("id")
    require(read.status == 200 and view["id"] == expected_id, "车辆提交后读到了其他原单")
    native, request = await response_meta(e, response, body, json_contract=not multipart)
    require(urlsplit(response.url).netloc == urlsplit(e.manifest["origin"]).netloc
            and urlsplit(response.url).scheme == urlsplit(e.manifest["origin"]).scheme, "车辆写入不是原同源请求")
    if multipart:
        headers = await response.request.all_headers()
        raw = response.request.post_data_buffer
        require(isinstance(raw, bytes), "原CSV上传缺真实multipart字节")
        message = BytesParser(policy=email_policy).parsebytes(
            ("Content-Type: " + headers["content-type"] + "\r\nMIME-Version: 1.0\r\n\r\n").encode("ascii") + raw)
        request, files = {}, []
        require(message.is_multipart(), "原CSV上传并非multipart")
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            content = part.get_payload(decode=True)
            require(name and isinstance(content, bytes), "原CSV上传字段不完整")
            if part.get_filename() is not None:
                files.append({"field": name, "name": part.get_filename(), "length": len(content),
                              "sha256": hashlib.sha256(content).hexdigest(), "content_observed": bool(content)})
            else:
                require(name not in request, "原CSV上传重复字段")
                request[name] = content.decode("utf-8")
        require(set(request) == {"source_reference", "kind", "request_id", "version"}
                and len(files) == 1 and files[0]["field"] == "file"
                and re.fullmatch(r"[A-Za-z0-9_-]{16,80}", request["request_id"]), "原CSV封包不是精确合同")
        native.update(submitted_version=int(request["version"]),
                      request_id_sha256=hashlib.sha256(request["request_id"].encode()).hexdigest(), uploaded_file=files[0])
    if request is not None and not multipart:
        if task_assign:
            require(set(request) == {"version", "assignee_id", "reason"}, "原Task交接封包改变")
            require(request["reason"] and request["version"] > 0, "原交接未提供真实版本和原因")
            native["request_id_sha256"] = None
        else:
            require(isinstance(request.get("request_id"), str) and len(request["request_id"]) >= 16, "原车辆命令缺幂等键")
    if request is not None and not multipart and not task_assign:
        receipt_table = "vehicle_import_requests" if path.startswith(VI + "/batches/") else "flow_request_receipts"
        receipt_rows = e.db.rows(f"SELECT * FROM {receipt_table} WHERE request_key=?", (request["request_id"],))
        require(len(receipt_rows) == 1 and receipt_rows[0]["actor_id"] == actor["id"] and receipt_rows[0]["store_id"] == store
                and receipt_rows[0]["batch_id" if receipt_table == "vehicle_import_requests" else "case_id"] ==
                    (body["id"] if receipt_table == "vehicle_import_requests" else expected_id), "原车辆幂等回执串员工/原单")
        native["receipt_id"] = receipt_rows[0]["id"]
    native.update(render_get_path=urlsplit(read.url).path, render_get_status=read.status,
                  actor_id=actor["id"], store_id=store, source_guard=protection.finish())
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return body, view, native, request


async def read_as(e, context, credentials, fixture, role, route, path, title):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, fixture["store_id"])
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原车辆页面读取失败")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    if body.get("id") is not None and re.search(r"/\d+$", path):
        require(body["id"] == int(path.rsplit("/", 1)[-1]), "原车辆页面串单")
    return actor, body


async def visible_original_button(e, selector):
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        group = button.locator("xpath=ancestor::details[not(@open)]").first
        await expect(group).to_have_count(1)
        summary = group.locator(":scope > summary")
        await expect(summary).to_be_visible()
        e.action("click", "展开原业务操作组")
        await summary.click()
    await expect(button).to_be_visible()
    await expect(button).to_be_enabled()


async def proof_upload(e, case_id, actor, fixture, category, name, text):
    guard = Guard(e, "vehicle_file_upload", actor, fixture["store_id"], append=FILES, cases={case_id})
    file_id = await upload(e, case_id, actor, category, name, text)
    protection = guard.finish()
    row = one(e, "flow_files", file_id)
    stored = row.pop("content")
    require(isinstance(stored, bytes) and len(stored) == row["size"] and hashlib.sha256(stored).hexdigest() == row["sha256"],
            "原附件实际字节不匹配")
    return {"file": row, "stored_blob": {"length": len(stored), "sha256": hashlib.sha256(stored).hexdigest()}, "source_guard": protection}


def open_task(e, case_id, key):
    found = [r for r in rows(e, "flow_tasks") if r["case_id"] == case_id and r["key"] == key and r["status"] == "open"]
    require(len(found) == 1, "当前原车辆待办不唯一：" + key)
    return found[0]


async def purchase_owner(e, context, credentials, fixture, case_id, key, role):
    task = open_task(e, case_id, key)
    selected = e.manifest["users"][fixture[role + "_key"]]
    evidence = {"task_id": task["id"], "key": key, "assignee_id": selected["id"], "handoff_needed": task["assignee_id"] != selected["id"]}
    if evidence["handoff_needed"]:
        manager, view = await read_as(e, context, credentials, fixture, "manager", f"case/{case_id}", f"/api/flow/cases/{case_id}", one(e, "flow_cases", case_id)["title"])
        require(view["id"] == case_id and view["version"] == one(e, "flow_cases", case_id)["version"], "交接前原单读取过期")
        button = e.page.locator(f'#main [data-act="assign"][data-id="{task["id"]}"]')
        await expect(button).to_have_count(1)
        await expect(button).to_be_visible()
        await e.click(f'#main [data-act="assign"][data-id="{task["id"]}"]', "主管按真实任务转交本店原岗位")
        await employee_choice(e, selected)
        await e.fill('#modal [name="reason"]', "合成车辆原业务由已明确的本店岗位本人实际办理", "说明原任务交接")
        guard = Guard(e, "vehicle_purchase_task_handoff", manager, fixture["store_id"], append={"flow_events", "audit_logs"},
                      update={"flow_tasks": {task["id"]: {"assignee_id", "version", "updated_at"}}}, cases={case_id})
        _, _, native, request = await submit(e, f'/api/flow/tasks/{task["id"]}/assign', manager, fixture["store_id"], guard, case_id=case_id, task_assign=True)
        require(request["version"] == task["version"] and request["assignee_id"] == selected["id"], "Task原版本/经办错误")
        evidence["native_handoff"] = native
    actor, view = await read_as(e, context, credentials, fixture, role, f"vehicle-procurement/{case_id}", VP + f"/{case_id}", "整车采购办理")
    require(open_task(e, case_id, key)["assignee_id"] == actor["id"], "采购实际员工不是待办本人")
    if role == "inventory":
        require("totals" not in view and not view["payments"] and not view["funds_requests"], "库管读到采购财务详情")
    return actor, view, evidence


async def purchase_action(e, fixture, case_id, action, actor, fills, selects=(), *, extra="", append=(), update=None):
    before = purchase_facts(e, case_id)
    button = f'#main [data-act="vp-action"][data-key="{action}"]{extra}'
    await visible_original_button(e, button)
    await e.click(button, "本人办理原采购 " + action)
    await expect(e.page.locator("#modal form")).to_be_visible()
    for name, value in fills.items():
        await e.fill(f'#modal [name="{name}"]', str(value), "填写本次原采购事实 " + name)
    for name, value in selects:
        await select_value(e, f'#modal [name="{name}"]', value, "明确本单原来源 " + name)
    protection = Guard(e, "vehicle_purchase_" + action, actor, fixture["store_id"],
        append=COMMON | {"flow_tasks"} | set(append), update=update or mutable(e, case_id), cases={case_id}, vins=fixture["vins"])
    body, _, native, request = await submit(e, VP + f"/{case_id}/actions/{action}", actor, fixture["store_id"], protection, case_id=case_id)
    after = purchase_facts(e, case_id)
    require(request["version"] == before["case"]["version"] and body["id"] == case_id and body["version"] == after["case"]["version"], "采购CAS或原ID不匹配")
    event = command_facts(before, after, action, actor)
    await expect(e.page.locator("#main h1")).to_have_text("整车采购办理")
    return body, after, {"native": native, "event": event, "submitted_values": request["values"]}


def csv_file(e, kind, values, suffix=""):
    folder = e.directory / "synthetic-inputs"
    folder.mkdir(exist_ok=True)
    path = folder / ("synthetic-vehicle-" + kind + suffix + ".csv")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADERS[kind])
    writer.writerows([[r[h] for h in HEADERS[kind]] for r in values])
    content = buffer.getvalue().encode("utf-8")
    require(len(content) <= 131072 and len(values) <= 200, "候选CSV超原资源合同")
    path.write_bytes(content)
    return path, content


def batch_facts(e, batch_id):
    batch = one(e, "vehicle_import_batches", batch_id)
    batch["errors"] = json.loads(batch["errors"])
    actual = e.db.rows("SELECT * FROM vehicle_import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,))
    for row in actual:
        row["values"], row["errors"] = json.loads(row["values"]), json.loads(row["errors"])
    results = e.db.rows("SELECT r.* FROM vehicle_import_results r JOIN vehicle_import_rows s ON s.id=r.row_id WHERE s.batch_id=? ORDER BY s.row_number", (batch_id,))
    claims = e.db.rows("SELECT c.* FROM vehicle_import_claims c JOIN vehicle_import_rows s ON s.id=c.row_id WHERE s.batch_id=? ORDER BY c.key", (batch_id,))
    file = one(e, "flow_files", batch["source_file_id"])
    stored = file.pop("content")
    require(isinstance(stored, bytes) and len(stored) == file["size"] and hashlib.sha256(stored).hexdigest() == file["sha256"] == batch["source_digest"], "CSV冻结内容实际字节/hash错误")
    return {"batch": batch, "rows": actual, "claims": claims, "results": results, "file": file,
            "stored_blob": {"length": len(stored), "sha256": hashlib.sha256(stored).hexdigest()}}


async def imports_as(e, context, credentials, fixture, case_id, role):
    return await read_as(e, context, credentials, fixture, role, f"vehicle-imports/{case_id}", VI + f"/orders/{case_id}/manifest", "车辆请款与批量交接")


async def batch_as(e, context, credentials, fixture, batch_id, role):
    actor, view = await read_as(e, context, credentials, fixture, role, f"vehicle-import/{batch_id}", VI + f"/batches/{batch_id}", "车辆导入批次 " + str(batch_id))
    current = batch_facts(e, batch_id)
    require(view["case_id"] == current["batch"]["case_id"] and view["version"] == current["batch"]["version"]
            and view["case_version"] == one(e, "flow_cases", view["case_id"])["version"]
            and view["source_digest"] == current["batch"]["source_digest"], "批次GET/DB范围或版本不匹配")
    return actor, view


async def prepare_batch(e, fixture, case_id, kind, actor, values, *, suffix="", invalid=False):
    source_case = one(e, "flow_cases", case_id)
    before_purchase = purchase_facts(e, case_id)
    path, content = csv_file(e, kind, values, suffix)
    reference = "SYNTHETIC-" + kind.upper() + "-" + fixture["token"] + suffix
    await e.click(f'#main [data-act="vi-new"][data-kind="{kind}"]', "导入明确本次 " + kind + " 原资料")
    await expect(e.page.locator("#modal form")).to_be_visible()
    await e.fill('#modal [name="source_reference"]', reference, "明确供应方合成清单编号")
    e.action("select_file", "选择本次严格CSV原文件", filename=path.name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    # Read only the employee-selected native File. Some request observers expose
    # an empty file part even when the server stores the uploaded bytes correctly.
    browser_file = await e.page.locator('#modal [name="file"]').evaluate("""async input => {
        const count=input.files.length;
        if(count!==1)return {count};
        const file=input.files[0], bytes=await file.arrayBuffer();
        const digest=await crypto.subtle.digest('SHA-256',bytes);
        return {count,name:file.name,type:file.type,length:bytes.byteLength,
            sha256:Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('')};
    }""")
    require(browser_file["count"] == 1 and browser_file["name"] == path.name
        and browser_file["length"] == len(content) and browser_file["sha256"] == hashlib.sha256(content).hexdigest(),
        "员工原file控件所选字节与本次CSV不符")
    e.observe("employee_selected_csv_file", browser_file)
    guard = Guard(e, "vehicle_csv_prepare_" + kind + suffix, actor, fixture["store_id"],
        append=IMPORT | FILES | {"flow_tasks"}, cases={case_id}, vins=fixture["vins"])
    body, _, native, request = await submit(e, VI + f"/orders/{case_id}/batches", actor, fixture["store_id"], guard,
                                    status=201, case_id=case_id, multipart=True)
    await expect(e.page.locator("#main h1")).to_have_text("车辆导入批次 " + str(body["id"]))
    facts = batch_facts(e, body["id"])
    b = facts["batch"]
    require(int(request["version"]) == source_case["version"] and request["kind"] == kind and request["source_reference"] == reference
            and native["uploaded_file"]["name"] == browser_file["name"], "CSV原浏览器封包/CAS/员工所选文件错配")
    if native["uploaded_file"]["content_observed"]:
        require(native["uploaded_file"]["length"] == browser_file["length"]
            and native["uploaded_file"]["sha256"] == browser_file["sha256"], "CSV请求观察字节与原file控件不符")
    require(facts["file"]["size"] == browser_file["length"] and facts["file"]["sha256"] == browser_file["sha256"]
        and facts["stored_blob"]["sha256"] == browser_file["sha256"] == b["source_digest"], "CSV原控件/服务器冻结文件/批次字节错配")
    native.update(employee_selected_file=browser_file,
                  multipart_file_content_observed=native["uploaded_file"]["content_observed"])
    receipts = e.db.rows("SELECT actor_id,batch_id FROM vehicle_import_requests WHERE request_key=?", (request["request_id"],))
    require(len(receipts) == 1 and receipts[0]["actor_id"] == actor["id"] and receipts[0]["batch_id"] == body["id"], "原CSV请求回执串员工/批次")
    require(b["case_id"] == case_id and b["kind"] == kind and b["source_case_version"] == source_case["version"]
            and b["prepared_by"] == actor["id"] and b["source_reference"] == reference and b["row_count"] == len(values)
            and b["source_digest"] == hashlib.sha256(content).hexdigest(), "CSV原来源/员工/原版本未冻结")
    require([r["values"] for r in facts["rows"]] == values and [r["row_number"] for r in facts["rows"]] == list(range(2, len(values) + 2)), "CSV逐行值与原字节不符")
    require(not facts["results"] and before_purchase["funds"] == purchase_facts(e, case_id)["funds"]
            and before_purchase["shipments"] == purchase_facts(e, case_id)["shipments"]
            and before_purchase["receipts"] == purchase_facts(e, case_id)["receipts"], "CSV预检提前形成请款/发运/实车")
    require(b["status"] == ("invalid" if invalid else "prepared"), "CSV原预检状态错误")
    require(bool(b["errors"]) == invalid and len(facts["claims"]) == (0 if invalid else len(values) * 2), "CSV错误或占用没有整批处理")
    if invalid:
        await expect(e.page.locator("#main")).to_contain_text("逐行错误")
        await expect(e.page.locator("#main")).to_contain_text("该来源行或 VIN 已有批次")
    for row in facts["rows"]:
        await expect(e.page.locator("#main")).to_contain_text(row["values"]["vin"])
        await expect(e.page.locator("#main")).to_contain_text("清单行编号 " + str(row["id"]))
    return body["id"], {"native": native, "facts": facts}


async def import_action(e, fixture, batch_id, action, actor, *, task_id=None, assignee=None):
    before = batch_facts(e, batch_id)
    b = before["batch"]
    case_id = b["case_id"]
    original = one(e, "flow_cases", case_id)
    selector = f'#main [data-act="vi-action"][data-key="{action}"]'
    await visible_original_button(e, selector)
    await e.click(selector, "原编制核验步骤 " + action)
    await expect(e.page.locator("#modal form")).to_be_visible()
    await e.fill('#modal [name="reason"]', "已逐项核对合成来源、VIN、原版和本岗位实际事实", "记录独立原核对依据")
    if action == "confirm":
        await checkbox(e, '#modal [name="confirmed"]', True, "本人明确确认本次实际办理")
    if action == "reassign":
        await select_value(e, '#modal [name="task_id"]', task_id, "选择本批原核验任务")
        await select_value(e, '#modal [name="assignee_id"]', assignee["id"], "选择明确独立复核主管")
    append = {"vehicle_import_requests", "flow_events", "flow_tasks", "audit_logs"}
    update = {"vehicle_import_batches": {batch_id: {"status", "reviewed_by", "confirmed_by", "version", "updated_at"}},
              "flow_tasks": {r["id"]: TASK_FIELDS for r in rows(e, "flow_tasks") if r["case_id"] == case_id and r["key"].startswith(f"vi_{batch_id}_")}}
    if action == "confirm":
        append |= COMMON | {"vehicle_import_results"}
        update = mutable(e, case_id, batch_id=batch_id)
        if b["kind"] == "funds":
            append.add("vehicle_purchase_funds_requests")
        elif b["kind"] == "ship":
            append |= {"vehicle_purchase_shipments", "vehicle_custodies", "group_identities"}
        else:
            append |= {"vehicle_purchase_receipts", "vehicle_purchase_movements", "vehicles", "vehicle_positions", "vehicle_position_entries", "group_identity_links"}
            shipment_ids = [r["id"] for r in rows(e, "vehicle_purchase_shipments") if r["case_id"] == case_id and r["vin"] in fixture["vins"]]
            update["vehicle_purchase_shipments"] = {key: {"status", "active_vin", "version", "updated_at"} for key in shipment_ids}
            update["vehicle_custodies"] = {r["id"]: {"version", "generation", "current_vehicle_id", "current_store_id"}
                                           for r in rows(e, "vehicle_custodies") if r["vin"] in fixture["vins"]}
    guard = Guard(e, "vehicle_csv_" + action + "_" + b["kind"], actor, fixture["store_id"],
                  append=append, update=update, cases={case_id}, vins=fixture["vins"])
    body, _, native, request = await submit(e, VI + f"/batches/{batch_id}/actions/{action}", actor, fixture["store_id"], guard, case_id=case_id)
    require(request["version"] == b["version"] and request["source_case_version"] == original["version"], "导入双CAS不是最新原GET")
    facts = batch_facts(e, batch_id)
    target = {"trial": "trial_passed", "review": "reviewed", "confirm": "confirmed", "reassign": b["status"]}[action]
    require(body["id"] == batch_id and body["status"] == facts["batch"]["status"] == target and body["version"] == facts["batch"]["version"], "导入响应/DB状态不匹配")
    if action == "trial":
        require(not facts["results"] and one(e, "flow_cases", case_id) == original, "试跑保留业务结果或改原采购")
        require(all(t not in native["source_guard"]["changed_tables"] for t in ("cash_entries", "vehicles", "vehicle_purchase_funds_requests", "vehicle_purchase_shipments", "vehicle_purchase_receipts", "vehicle_custodies", "group_identities")), "试跑未回滚实物资金/全局VIN")
        await expect(e.page.locator("#main")).to_contain_text("待主管复核")
    if action == "review":
        require(actor["id"] != b["prepared_by"] and facts["batch"]["reviewed_by"] == actor["id"] and not facts["results"], "复核替编制人或提前执行业务")
    if action == "confirm":
        require(actor["id"] == b["prepared_by"] and facts["batch"]["confirmed_by"] == actor["id"] and request["values"]["confirmed"] is True
                and len(facts["results"]) == len(facts["rows"]), "正式逐行结果/本人确认不完整")
        await expect(e.page.locator("#main")).to_contain_text("已执行原单动作")
    await expect(e.page.locator("#main h1")).to_have_text("车辆导入批次 " + str(batch_id))
    return {"native": native, "facts": facts}


async def complete_batch(e, context, credentials, fixture, batch_id, preparer_role, reviewer_role):
    actor, _ = await batch_as(e, context, credentials, fixture, batch_id, preparer_role)
    trial = await import_action(e, fixture, batch_id, "trial", actor)
    reviewer, _ = await batch_as(e, context, credentials, fixture, batch_id, reviewer_role)
    require(reviewer["id"] != actor["id"], "导入未使用独立复核人")
    task = open_task(e, trial["facts"]["batch"]["case_id"], f"vi_{batch_id}_review")
    handoff = None
    if task["assignee_id"] != reviewer["id"]:
        handoff = await import_action(e, fixture, batch_id, "reassign", reviewer, task_id=task["id"], assignee=reviewer)
        require(open_task(e, task["case_id"], task["key"])["assignee_id"] == reviewer["id"], "复核原任务交接未生效")
    review = await import_action(e, fixture, batch_id, "review", reviewer)
    actor, _ = await batch_as(e, context, credentials, fixture, batch_id, preparer_role)
    require(open_task(e, task["case_id"], f"vi_{batch_id}_confirm")["assignee_id"] == actor["id"], "本人确认任务归属错误")
    confirmation = await import_action(e, fixture, batch_id, "confirm", actor)
    return {"trial": trial, "review_handoff": handoff, "review": review, "confirmation": confirmation}


def vehicle_fact(e, key):
    car = one(e, "vehicles", key)
    position = [r for r in rows(e, "vehicle_positions") if r["vehicle_id"] == key]
    custody = [r for r in rows(e, "vehicle_custodies") if r["vin"] == car["vin"]]
    links = [r for r in rows(e, "group_identity_links") if r["local_kind"] == "vehicle" and r["local_id"] == key]
    require(len(position) == len(custody) == len(links) == 1 and links[0]["identity_id"] == custody[0]["identity_id"], "库存代次/位置/集团身份来源不唯一")
    return {"vehicle": car, "position": position[0], "custody": custody[0], "identity_link": links[0],
            "position_entries": [r for r in rows(e, "vehicle_position_entries") if r["vehicle_id"] == key]}


async def operation_as(e, context, credentials, fixture, case_id, role):
    operation = one(e, "vehicle_operations", case_id)
    title = {"local_move": "整车店内移库", "other_out": "整车其他出库", "other_return": "其他出库原车退回"}[operation["kind"]]
    actor, view = await read_as(e, context, credentials, fixture, role, f"vehicle-operation/{case_id}", VO + f"/{case_id}", title)
    require(view["version"] == one(e, "flow_cases", case_id)["version"] and view["vin"] == operation["vin"]
            and view["source_generation"] == operation["source_generation"], "车辆作业GET身份/CAS错误")
    if role == "inventory":
        require("cost_cents" not in view and all("value_cents" not in r for r in view["entries"]), "库管作业页面泄漏金额")
    await expect(e.page.locator("#main")).to_contain_text(operation["vin"])
    return actor, view


async def operation_action(e, fixture, case_id, action, actor, proof=None, *, task_id=None, selected=None):
    original = one(e, "flow_cases", case_id)
    operation = one(e, "vehicle_operations", case_id)
    selector = f'#main [data-act="vo-action"][data-key="{action}"]'
    await visible_original_button(e, selector)
    await e.click(selector, "原岗位办理车辆作业 " + action)
    await expect(e.page.locator("#modal form")).to_be_visible()
    await e.fill('#modal [name="reason"]', "已核对本次原VIN、代次、批准依据与合成现场实物交接", "记录本人实际办理依据")
    if proof:
        await select_value(e, '#modal [name="evidence_id"]', proof["file"]["id"], "选择本单原实物凭据")
    if action in {"dispatch", "accept", "receive"}:
        await e.fill('#modal [name="vin"]', operation["vin"], "重新核对现场17位VIN")
    if action == "reassign":
        await select_value(e, '#modal [name="task_id"]', task_id, "选择当前原待办")
        await e.fill('#modal [name="due_date"]', today(), "明确实际交接期限")
        assignee = e.page.locator('#modal [name="assignee_id"]')
        await expect(assignee).to_have_value("")
        require(await assignee.get_attribute("required") is not None
                and await assignee.evaluate("element => element.validity.valueMissing"), "接手员工必须保持明确未选择")
        before = e.business_snapshot("before_empty_vehicle_assignee")
        attempted = []

        def record_attempt(request):
            if request.method == "POST" and urlsplit(request.url).path == VO + f"/{case_id}/actions/reassign":
                attempted.append({"method": request.method, "path": urlsplit(request.url).path})

        e.page.on("request", record_attempt)
        try:
            await e.click('#modal button[type="submit"]', "未选择接手员工时原界面阻止提交")
            await expect(assignee).to_have_value("")
            require(await assignee.evaluate("element => element.validity.valueMissing") and not attempted,
                    "未选择接手员工仍然提交原业务")
            e.business_unchanged(before, "after_empty_vehicle_assignee")
            e.observe("empty_assignee_native_validation", {"required": True, "value_missing": True,
                "business_posts": len(attempted), "all_business_unchanged": True})
        finally:
            e.page.remove_listener("request", record_attempt)
        await select_value(e, '#modal [name="assignee_id"]', selected["id"], "选择本店原岗位员工")
    append = COMMON | {"flow_tasks"}
    update = mutable(e, case_id, operation=True)
    if action == "approve":
        append.add("vehicle_operation_reviews")
    if action in {"dispatch", "accept", "receive"}:
        append.add("vehicle_position_entries")
        update = mutable(e, case_id, operation=True, vehicles={operation["source_vehicle_id"]})
    if action == "receive":
        # other_return never updates the previous exited car/Position.
        update.pop("vehicles", None)
        update.pop("vehicle_positions", None)
        append |= {"vehicles", "vehicle_positions", "group_identity_links"}
    guard = Guard(e, "vehicle_operation_" + action, actor, fixture["store_id"],
                  append=append, update=update, cases={case_id}, vins={operation["vin"]})
    body, _, native, request = await submit(e, VO + f"/{case_id}/actions/{action}", actor, fixture["store_id"], guard, case_id=case_id)
    require(request["version"] == original["version"] and body["version"] == one(e, "flow_cases", case_id)["version"], "车辆作业原CAS错误")
    after = one(e, "vehicle_operations", case_id)
    for field in ("source_vehicle_id", "source_generation", "vin", "source_location_id", "destination_location_id", "original_operation_id", "cost_cents", "requested_by"):
        require(after[field] == operation[field], "车辆作业冻结源被改写：" + field)
    events = e.db.rows("SELECT * FROM flow_events WHERE case_id=? AND action=? ORDER BY id", (case_id, "vo_" + action))
    require(events[-1]["actor_id"] == actor["id"], "车辆作业事件不是当前员工")
    await expect(e.page.locator("#main h1")).to_have_text({"local_move": "整车店内移库", "other_out": "整车其他出库", "other_return": "其他出库原车退回"}[operation["kind"]])
    await expect(e.page.locator("#main .pagehead")).to_contain_text(original["number"])
    return {"native": native, "operation": after, "case": one(e, "flow_cases", case_id), "event_id": events[-1]["id"]}


async def operation_owner(e, context, credentials, fixture, case_id, key, role):
    selected = e.manifest["users"][fixture[role + "_key"]]
    task = open_task(e, case_id, key)
    handoff = None
    if task["assignee_id"] != selected["id"]:
        manager, _ = await operation_as(e, context, credentials, fixture, case_id, "manager")
        handoff = await operation_action(e, fixture, case_id, "reassign", manager, task_id=task["id"], selected=selected)
        require(open_task(e, case_id, key)["assignee_id"] == selected["id"], "车辆作业任务交接未生效")
    actor, view = await operation_as(e, context, credentials, fixture, case_id, role)
    require(open_task(e, case_id, key)["assignee_id"] == actor["id"], "车辆实物/复核未由本人办理")
    return actor, view, handoff


async def create_operation(e, context, credentials, fixture, kind, vehicle, location=None, original=None):
    actor, _ = await read_as(e, context, credentials, fixture, "inventory", "vehicle-operations", VO, "整车库位与出退库")
    before_car = one(e, "vehicles", vehicle["id"])
    await e.click('#main [data-act="vo-new"]', "库管建立本次明确车辆作业")
    await expect(e.page.locator("#modal-title")).to_have_text("建立车辆作业")
    await select_value(e, '#modal [name="kind"]', kind, "选择原作业类型")
    if original:
        await select_value(e, '#modal [name="original_operation_id"]', original, "选择本次已完成其他出库原单")
        await expect(e.page.locator('#modal [name="vehicle_id"]')).not_to_be_visible()
    else:
        await select_value(e, '#modal [name="vehicle_id"]', vehicle["id"], "选择本次实车VIN原库存记录")
        await expect(e.page.locator('#modal [name="vehicle_id"] option:checked')).to_contain_text(vehicle["vin"])
    if location:
        await select_value(e, '#modal [name="location_id"]', location["id"], "选择明确本店整车库位")
        await expect(e.page.locator('#modal [name="location_id"] option:checked')).to_contain_text(location["name"])
    if kind == "other_out":
        await e.fill('#modal [name="recipient"]', "合成内部设备接收方；经批准转用后原车实际退回", "明确实际处置去向")
    await e.fill('#modal [name="reason"]', "合成现场交接安排，保留本次VIN原成本及历史来源", "填写原作业安排")
    await e.fill('#modal [name="due_date"]', today(), "明确本次实际期限")
    update = mutable(e, -1, vehicles={vehicle["id"]})
    update.pop("flow_cases")
    update.pop("flow_tasks")
    # Creation only locks custody/version and touches an available car; it never moves a Position.
    update.pop("vehicle_positions", None)
    if "vehicles" in update:
        update["vehicles"] = {vehicle["id"]: {"updated_at", "version"}}
    update["vehicle_custodies"] = {key: {"version"} for key in update.get("vehicle_custodies", {})}
    if kind == "other_return":
        update.pop("vehicles", None)
    guard = Guard(e, "vehicle_operation_create_" + kind, actor, fixture["store_id"], append=COMMON | {"flow_cases", "flow_tasks", "vehicle_operations", "vehicle_operation_claims"},
                  update=update, vins={vehicle["vin"]}, new_kind="vehicle_operations")
    body, _, native, request = await submit(e, VO, actor, fixture["store_id"], guard, status=201)
    case_id = body["id"]
    op = one(e, "vehicle_operations", case_id)
    require(op["status"] == "requested" and op["source_vehicle_id"] == vehicle["id"] and op["source_generation"] == before_car["inventory_generation"]
            and op["cost_cents"] == before_car["purchase_cost_cents"] and op["original_operation_id"] == original, "车辆作业准备原来源错误")
    require(one(e, "vehicles", vehicle["id"])["approval_state"] == before_car["approval_state"], "建单提前改变实车库存状态")
    await expect(e.page.locator("#main h1")).to_have_text(body["kind_label"])
    return case_id, {"native": native, "operation": op, "submitted": request}


def payment_fact(e, case_id, payment_id, actor, account, amount, direction, *, original=None):
    payment = one(e, "vehicle_purchase_payments", payment_id)
    cash = one(e, "cash_entries", payment["cash_id"])
    require(payment["case_id"] == case_id and payment["amount_cents"] == cash["amount_cents"] == amount
            and payment["direction"] == cash["direction"] == direction and payment["account_id"] == account["id"]
            and cash["account"] == account["name"] and cash["approval_state"] == "approved"
            and cash["created_by"] == actor["id"] and payment["original_id"] == original, "原采购实际现金/账户/原款不匹配")
    require(cash["category"] == ("vehicle_procurement_payment" if direction == "out" else "vehicle_procurement_refund"), "原采购款分类错误")
    return {"payment": payment, "cash": cash}


async def vehicle_operations(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        fixture = dict(e.manifest["business_fixtures"]["vehicle_purchase"])
        fixture["admin_key"] = "admin"
        store = fixture["store_id"]
        for role in ("inventory", "manager", "finance", "admin"):
            key = fixture[role + "_key"]
            require(key in e.manifest["users"] and e.manifest["users"][key]["role"] == role, "车辆链缺真实原岗位：" + role)
        purchase = fixed_dependency(e, checkpoint, PURCHASE)
        fixed_dependency(e, checkpoint, MASTER)
        supplier = checkpoint_evidence(purchase, "HK-171")["supplier"]
        hierarchy = checkpoint_evidence(purchase, "HK-177")
        models = [hierarchy["new_hierarchy"]["model"], hierarchy["existing_hierarchy_new_model"]["model"]]
        sources = checkpoint_evidence(purchase, "HK-178")
        warehouse, location = sources["warehouse"], sources["location"]
        account_id = checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"]
        for table, source in (("master_suppliers", supplier), ("master_warehouses", warehouse), ("master_locations", location)):
            current = one(e, table, source["id"])
            require(current["store_id"] == store and current["active"] and current["code"] == source["code"] and current["name"] == source["name"], "本轮主档源失效或串店")
        require(warehouse["warehouse_type"] == "vehicles" and location["warehouse_id"] == warehouse["id"], "本轮仓与库位原关系错误")
        for model in models:
            current = one(e, "master_vehicle_models", model["id"])
            require(current["store_id"] == store and current["active"] and current["name"] == model["name"], "本轮车型原源失效")
        account = one(e, "flow_accounts", account_id)
        require(account["store_id"] == store and account["active"] and account["account_type"] == "bank", "本次原款账户失效")
        token = uuid.uuid4().hex[:12].upper()
        fixture.update(token=token, vins=["LTEST" + uuid.uuid4().hex[:12].upper() for _ in range(2)])
        require(len(set(fixture["vins"])) == 2 and all(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin) for vin in fixture["vins"]), "新VIN输入无效")
        require(not e.db.rows("SELECT id FROM vehicles WHERE vin IN (?,?)", tuple(fixture["vins"])), "合成VIN已存在，停止而不重用旧事实")
        checkpoint.start("HK-019")
        inventory, _ = await read_as(e, context, credentials, fixture, "inventory", "masters", "/api/masters/catalog", "基础资料")
        await master_page(e, "locations", "库位")
        await master_form(e, "locations", "库位")
        await live_choice(e, "warehouse_id", warehouse["name"], warehouse["code"] + " · " + warehouse["name"], expected_value=warehouse["id"])
        guard = Guard(e, "vehicle_second_location", inventory, store, append={"master_locations", "master_receipts", "audit_logs"})
        destination, location_native = await save_master(e, "locations", {"code": "VIO" + token, "name": "合成车辆目的位" + token, "active": True})
        location_native["source_guard"] = guard.finish()
        require(destination["warehouse_id"] == warehouse["id"], "目的位不属于原整车仓")

        inventory, _ = await read_as(e, context, credentials, fixture, "inventory", "vehicle-procurement", VP, "整车采购与付款")
        await e.click('#main [data-act="vp-new"]', "建立本次独立两VIN新采购")
        await expect(e.page.locator("#modal-title")).to_have_text("整车采购计划")
        await select_value(e, '#modal [name="supplier_id"]', supplier["id"], "选择本轮已验证供方")
        party = e.page.locator('#modal [name="contracting_party"]')
        if await party.get_attribute("readonly") is None:
            await e.fill('#modal [name="contracting_party"]', "合成车辆导入采购主体" + token, "按合成合同明确采购主体")
        require(bool((await party.input_value()).strip()), "原采购抬头为空")
        await e.fill('#modal [name="due_date"]', today(), "按本店业务日安排实际到货")
        await e.fill('#modal [name="reason"]', "两车独立导入：A本地移库及原车出退，B原供方退车退款", "明确本次独立采购理由")
        await e.click('#modal [data-act="vp-add-line"]', "添加另一原车型采购行")
        for index, model in enumerate(models):
            root = f'#modal [data-vp-line]:nth-child({index + 1}) '
            await select_value(e, root + '[name="model"]', model["id"], "选择同轮明确车型")
            await e.fill(root + '[name="color"]', "合成导入" + ("白" if index == 0 else "黑"), "明确采购颜色")
            await e.fill(root + '[name="quantity"]', "1", "明确每行整数一台")
        guard = Guard(e, "vehicle_import_purchase_create", inventory, store, append=COMMON | {"flow_cases", "flow_tasks", "vehicle_purchase_orders", "vehicle_purchase_lines"}, new_kind="vehicle_procurement")
        body, _, created, request = await submit(e, VP, inventory, store, guard, status=201)
        case_id = body["id"]
        await expect(e.page.locator("#main h1")).to_have_text("整车采购办理")
        original = purchase_facts(e, case_id)
        require(original["order"]["supplier_id"] == supplier["id"] and len(original["lines"]) == 2
                and original["case"]["created_by"] == inventory["id"] and original["case"]["state"] == "approval"
                and not original["shipments"] and not original["payments"] and not original["prices"], "新采购提前造价/款/实车")
        require([{"model_id": l["model_id"], "quantity": l["quantity"], "color": l["color"]} for l in original["lines"]] == request["lines"], "新原采购行与UI输入不一致")
        manager, _, owner = await purchase_owner(e, context, credentials, fixture, case_id, "vp_approve", "manager")
        require(manager["id"] != inventory["id"], "新采购缺独立核价")
        contract = await proof_upload(e, case_id, manager, fixture, "procurement_contract", "synthetic-import-contract.txt", "本次两车型各1台，冻结成本1000分与2000分，建议售价1200分与2200分。")
        prices = {}
        for index, line in enumerate(original["lines"]):
            prices["cost_" + str(line["id"])] = str((index + 1) * 10)
            prices["price_" + str(line["id"])] = str((index + 1) * 10 + 2)
        _, original, approved = await purchase_action(e, fixture, case_id, "approve", manager, prices, [("evidence_id", contract["file"]["id"])], append={"vehicle_purchase_prices"}, update=mutable(e, case_id, prices=True))
        require(original["case"]["amount_cents"] == 3000 and len(original["prices"]) == 2 and all(p["approved_by"] == manager["id"] for p in original["prices"]), "原逐行冻结价不符")
        funds_values = [{"source_row": "A", "line_id": original["lines"][0]["id"], "vin": fixture["vins"][0], "amount_cents": 1000},
                        {"source_row": "B", "line_id": original["lines"][1]["id"], "vin": fixture["vins"][1], "amount_cents": 2000}]
        manager, _ = await imports_as(e, context, credentials, fixture, case_id, "manager")
        funds_batch, prepared = await prepare_batch(e, fixture, case_id, "funds", manager, funds_values)
        funds_steps = await complete_batch(e, context, credentials, fixture, funds_batch, "manager", "admin")
        funds = funds_steps["confirmation"]["facts"]
        require(funds["batch"]["amount_cents"] == 3000 and len(funds["results"]) == 2, "正式请款整批总额/逐行错误")
        current = purchase_facts(e, case_id)
        require(len(current["funds"]) == 2 and not current["payments"] and not current["receipts"] and not current["shipments"], "请款冒实际付款/发运/收车")
        for row, result in zip(funds["rows"], funds["results"]):
            fact = one(e, "vehicle_purchase_funds_requests", result["funds_request_id"])
            require(result["row_id"] == row["id"] and result["shipment_id"] is None and result["receipt_id"] is None
                    and fact["amount_cents"] == row["values"]["amount_cents"] and fact["evidence_id"] == funds["file"]["id"]
                    and fact["requested_by"] == manager["id"] and fact["status"] == "open", "逐VIN请款原事实错配")
        # Known successful source duplicated in a fresh batch: precheck rejects
        # all rows and reserves/executes nothing, while preserving its own source.
        manager, _ = await imports_as(e, context, credentials, fixture, case_id, "manager")
        duplicate_id, duplicate = await prepare_batch(e, fixture, case_id, "funds", manager, funds_values, suffix="-duplicate", invalid=True)
        await expect(e.page.locator('#main [data-act="vi-action"][data-key="trial"]')).to_have_count(0)
        await checkpoint.passed({"case_id": case_id, "new_order": current, "created": created, "approval_owner": owner,
            "contract": contract, "approval": approved, "location_precondition": {"row": destination, "native": location_native},
            "prepared": prepared, "steps": funds_steps, "duplicate_precheck": duplicate, "invalid_batch_id": duplicate_id},
            [{"id": "batch-replacement-cancel-and-resource-limit", "status": "not_tested", "requirement": "conditional"}])

        # Actual synthetic payments are original finance facts, not CSV effects.
        payments = []
        for index, result in enumerate(funds["results"]):
            finance, _, pay_owner = await purchase_owner(e, context, credentials, fixture, case_id, "vp_pay", "finance")
            amount = funds_values[index]["amount_cents"]
            receipt = await proof_upload(e, case_id, finance, fixture, "receipt", f"synthetic-import-pay-{index}.txt", f"本次已知合成原请款 {result['funds_request_id']} 实际付款 {amount} 分；非银行实付。")
            reference = "SYNTHETIC-VI-PAY-" + token + "-" + str(index)
            _, current, paid = await purchase_action(e, fixture, case_id, "pay", finance, {"amount": str(amount // 100), "reference": reference},
                [("funds_request_id", result["funds_request_id"]), ("account_id", account_id), ("evidence_id", receipt["file"]["id"])],
                append={"vehicle_purchase_payments", "cash_entries"}, update=mutable(e, case_id, funds={result["funds_request_id"]}, account=account_id))
            found = [p for p in current["payments"] if p["reference"] == reference]
            require(len(found) == 1, "本次原付款不唯一")
            fact = payment_fact(e, case_id, found[0]["id"], finance, account, amount, "out")
            payments.append({**fact, "native": paid, "owner": pay_owner, "proof": receipt})

        checkpoint.start("HK-027")
        _, _, ship_owner = await purchase_owner(e, context, credentials, fixture, case_id, "vp_ship", "inventory")
        inventory, manifest = await imports_as(e, context, credentials, fixture, case_id, "inventory")
        require({r["id"] for r in manifest["items"]} == {r["id"] for r in funds["rows"]}, "真实请款manifest不是本次两VIN")
        for r in manifest["items"]:
            require(set(r) == {"id", "batch_id", "line_id", "vin", "source_row"}, "库管manifest泄漏资金或来源文件字段")
            await expect(e.page.locator("#main")).to_contain_text("清单行编号")
            await expect(e.page.locator("#main")).to_contain_text(r["vin"])
            require(r["vin"] in fixture["vins"], "manifest出现其它VIN")
        await expect(e.page.locator('#main [data-act="vi-new"][data-kind="funds"]')).to_have_count(0)
        ship_values = [{"source_row": r["source_row"], "manifest_row_id": r["id"], "vin": r["vin"], "shipped_date": today(), "expected_date": today()} for r in manifest["items"]]
        ship_batch, prepared = await prepare_batch(e, fixture, case_id, "ship", inventory, ship_values)
        ship_steps = await complete_batch(e, context, credentials, fixture, ship_batch, "inventory", "manager")
        ship = ship_steps["confirmation"]["facts"]
        current = purchase_facts(e, case_id)
        require(len(current["shipments"]) == 2 and not current["receipts"] and not current["movements"] and len(current["payments"]) == 2, "发运误算收车或重复实际付款")
        for r, result in zip(ship["rows"], ship["results"]):
            s = one(e, "vehicle_purchase_shipments", result["shipment_id"])
            c = next(c for c in rows(e, "vehicle_custodies") if c["vin"] == r["vin"])
            require(s["vin"] == r["vin"] and s["line_id"] == r["line_id"] and s["status"] == "transit" and s["active_vin"] == r["vin"]
                    and s["actor_id"] == inventory["id"] and s["evidence_id"] == ship["file"]["id"]
                    and s["shipped_date"] == s["expected_date"] == today() and c["generation"] == 0 and c["current_vehicle_id"] is None,
                    "正式发运原manifest/在途/未库存来源错误")
        _, view = await read_as(e, context, credentials, fixture, "manager", f"vehicle-procurement/{case_id}", VP + f"/{case_id}", "整车采购办理")
        require(view["totals"]["paid_net_cents"] == view["totals"]["prepaid_cents"] == view["totals"]["in_transit_cents"] == 3000
                and view["totals"]["received_cents"] == 0, "实际预付/发运/收车口径混淆")
        await expect(e.page.locator("#main")).to_contain_text("在途待验收")
        await checkpoint.passed({"case_id": case_id, "manifest": manifest, "prepared": prepared, "steps": ship_steps,
            "payments": payments, "purchase_ship_owner": ship_owner, "shipments": current["shipments"], "pre_receipt_totals": view["totals"]})

        checkpoint.start("HK-028")
        _, _, receive_owner = await purchase_owner(e, context, credentials, fixture, case_id, "vp_receive", "inventory")
        inventory, manifest = await imports_as(e, context, credentials, fixture, case_id, "inventory")
        receive_values = [{"source_row": r["source_row"], "manifest_row_id": r["id"], "vin": r["vin"], "received_date": today(), "location_id": location["id"]} for r in manifest["items"]]
        receive_batch, prepared = await prepare_batch(e, fixture, case_id, "receive", inventory, receive_values)
        receive_steps = await complete_batch(e, context, credentials, fixture, receive_batch, "inventory", "manager")
        receive = receive_steps["confirmation"]["facts"]
        current = purchase_facts(e, case_id)
        require(len(current["receipts"]) == len(current["movements"]) == 2 and current["case"]["state"] == "completed", "两车实际收款收车未闭合")
        cars = {}
        for r, result in zip(receive["rows"], receive["results"]):
            receipt = one(e, "vehicle_purchase_receipts", result["receipt_id"])
            shipment = one(e, "vehicle_purchase_shipments", receipt["shipment_id"])
            fact = vehicle_fact(e, receipt["vehicle_id"])
            price = next(p for p in current["prices"] if p["line_id"] == shipment["line_id"])
            movement = next(m for m in current["movements"] if m["shipment_id"] == shipment["id"])
            require(fact["vehicle"]["vin"] == r["vin"] == shipment["vin"] and shipment["status"] == "received" and shipment["active_vin"] is None
                    and fact["vehicle"]["inventory_generation"] == fact["custody"]["generation"] == 1
                    and fact["custody"]["current_vehicle_id"] == fact["vehicle"]["id"] and fact["custody"]["current_store_id"] == store
                    and fact["position"]["status"] == "stored" and fact["position"]["location_id"] == receipt["location_id"] == location["id"]
                    and receipt["value_cents"] == movement["value_cents"] == fact["vehicle"]["purchase_cost_cents"] == price["unit_cost_cents"]
                    and receipt["actor_id"] == movement["actor_id"] == inventory["id"] and receipt["evidence_id"] == receive["file"]["id"]
                    and movement["kind"] == "receive" and movement["quantity"] == 1, "实际收车VIN/成本/代次/原入库不匹配")
            require(len(fact["position_entries"]) == 1 and fact["position_entries"][0]["kind"] == "purchase_receive"
                    and fact["position_entries"][0]["inventory_delta"] == 0, "库位入库重复计算门店库存")
            cars[r["vin"]] = {**fact, "receipt": receipt, "shipment": shipment, "movement": movement}
        _, view = await read_as(e, context, credentials, fixture, "manager", f"vehicle-procurement/{case_id}", VP + f"/{case_id}", "整车采购办理")
        require(view["totals"]["paid_net_cents"] == view["totals"]["received_cents"] == 3000 and view["totals"]["prepaid_cents"] == view["totals"]["payable_cents"] == 0, "已收车原账未与实际付款一致")
        await expect(e.page.locator("#main")).to_contain_text("已验收入库")
        await checkpoint.passed({"case_id": case_id, "prepared": prepared, "steps": receive_steps, "purchase_receive_owner": receive_owner,
            "vehicles": list(cars.values()), "totals": view["totals"]})

        car_a, car_b = cars[fixture["vins"][0]]["vehicle"], cars[fixture["vins"][1]]["vehicle"]
        checkpoint.start("HK-030")
        move_id, move_create = await create_operation(e, context, credentials, fixture, "local_move", car_a, destination)
        manager, _, review_handoff = await operation_owner(e, context, credentials, fixture, move_id, "vo_review", "manager")
        move_proof = await proof_upload(e, move_id, manager, fixture, "evidence", "synthetic-local-move.txt", "本次车辆A从明确原库位实际移往同店第二库位；不增减门店实车。")
        move_approve = await operation_action(e, fixture, move_id, "approve", manager, move_proof)
        inventory, _, physical_handoff = await operation_owner(e, context, credentials, fixture, move_id, "vo_physical", "inventory")
        move_dispatch = await operation_action(e, fixture, move_id, "dispatch", inventory, move_proof)
        transit = vehicle_fact(e, car_a["id"])
        require(transit["position"]["status"] == "transit" and transit["position"]["location_id"] is None and transit["vehicle"]["approval_state"] == "approved"
                and transit["custody"]["current_vehicle_id"] == car_a["id"] and move_dispatch["operation"]["status"] == "transit", "店内发出错误减库存或增加代次")
        move_accept = await operation_action(e, fixture, move_id, "accept", inventory, move_proof)
        moved = vehicle_fact(e, car_a["id"])
        entries = [r for r in moved["position_entries"] if r["operation_id"] == move_id]
        require(moved["position"]["status"] == "stored" and moved["position"]["location_id"] == destination["id"] and moved["vehicle"]["inventory_generation"] == 1
                and moved["vehicle"]["purchase_cost_cents"] == car_a["purchase_cost_cents"] and len(entries) == 2
                and {r["kind"] for r in entries} == {"local_dispatch", "local_accept"} and sum(r["quantity"] for r in entries) == sum(r["value_cents"] for r in entries) == sum(r["inventory_delta"] for r in entries) == 0,
                "店内移库源/在途/目的位量值不守恒")
        outgoing, incoming = sorted(entries, key=lambda r: r["quantity"])
        require(outgoing["location_id"] == location["id"] and incoming["location_id"] == destination["id"] and incoming["original_id"] == outgoing["id"], "同店移库两端源分录断开")
        await expect(e.page.locator("#main")).to_contain_text("目的库位接收")
        await checkpoint.passed({"create": move_create, "review_handoff": review_handoff, "physical_handoff": physical_handoff,
            "approve": move_approve, "dispatch": move_dispatch, "transit": transit, "accept": move_accept, "vehicle": moved, "entries": entries},
            [{"id": "destination-reject-and-return", "status": "not_tested", "requirement": "conditional"}])

        checkpoint.start("HK-025")
        out_id, out_create = await create_operation(e, context, credentials, fixture, "other_out", moved["vehicle"])
        manager, _, out_owner = await operation_owner(e, context, credentials, fixture, out_id, "vo_review", "manager")
        out_proof = await proof_upload(e, out_id, manager, fixture, "evidence", "synthetic-other-out.txt", "车辆A实际交给已明确的合成内部接收方；依原其他出库办理。")
        out_approve = await operation_action(e, fixture, out_id, "approve", manager, out_proof)
        inventory, _, out_physical = await operation_owner(e, context, credentials, fixture, out_id, "vo_physical", "inventory")
        out_dispatch = await operation_action(e, fixture, out_id, "dispatch", inventory, out_proof)
        exited = vehicle_fact(e, car_a["id"])
        exit_entry = next(r for r in exited["position_entries"] if r["operation_id"] == out_id)
        require(exited["vehicle"]["approval_state"] == "void" and exited["position"]["status"] == "exited" and exited["position"]["location_id"] is None
                and exited["custody"]["current_vehicle_id"] is exited["custody"]["current_store_id"] is None
                and exit_entry["kind"] == "other_out" and exit_entry["quantity"] == exit_entry["inventory_delta"] == -1
                and exit_entry["value_cents"] == -car_a["purchase_cost_cents"], "其他实际出库未减少真实可售库存")
        return_id, return_create = await create_operation(e, context, credentials, fixture, "other_return", exited["vehicle"], location, original=out_id)
        manager, _, return_owner = await operation_owner(e, context, credentials, fixture, return_id, "vo_review", "manager")
        return_proof = await proof_upload(e, return_id, manager, fixture, "evidence", "synthetic-other-return.txt", "按本次其他出库原单核对同VIN实际退回原整车库位，保留旧代次及原成本。")
        return_approve = await operation_action(e, fixture, return_id, "approve", manager, return_proof)
        inventory, _, return_physical = await operation_owner(e, context, credentials, fixture, return_id, "vo_physical", "inventory")
        returned = await operation_action(e, fixture, return_id, "receive", inventory, return_proof)
        new_vehicle_id = returned["operation"]["received_vehicle_id"]
        require(new_vehicle_id and new_vehicle_id != car_a["id"], "原车退回覆盖旧库存代次")
        returned_car = vehicle_fact(e, new_vehicle_id)
        new_entry = returned_car["position_entries"][0]
        require(returned_car["vehicle"]["vin"] == car_a["vin"] and returned_car["vehicle"]["inventory_generation"] == returned_car["custody"]["generation"] == 2
                and returned_car["custody"]["current_vehicle_id"] == new_vehicle_id and returned_car["custody"]["current_store_id"] == store
                and returned_car["vehicle"]["purchase_cost_cents"] == car_a["purchase_cost_cents"] and returned_car["position"]["location_id"] == location["id"]
                and new_entry["kind"] == "other_return" and new_entry["inventory_delta"] == new_entry["quantity"] == 1
                and new_entry["original_id"] == exit_entry["id"] and new_entry["value_cents"] == -exit_entry["value_cents"], "原车退回新代次/原出库/原成本未守恒")
        require(all(returned_car["vehicle"][field] == car_a[field] for field in ("vin", "brand", "model", "color", "supplier", "purchase_cost_cents", "list_price_cents")), "新代次冻结原车辆事实未完整继承")
        require(one(e, "vehicles", car_a["id"]) == exited["vehicle"] and one(e, "vehicle_positions", exited["position"]["id"]) == exited["position"], "原车退回改写旧车辆或Position")
        await expect(e.page.locator("#main")).to_contain_text("已生成新库存记录")
        await checkpoint.passed({"out_create": out_create, "out_owner": out_owner, "out_physical": out_physical, "out_approve": out_approve,
            "out_dispatch": out_dispatch, "exited": exited, "return_create": return_create, "return_owner": return_owner,
            "return_physical": return_physical, "return_approve": return_approve, "receive": returned, "new_current_vehicle": returned_car})

        checkpoint.start("HK-023")
        inventory, _ = await read_as(e, context, credentials, fixture, "inventory", f"vehicle-procurement/{case_id}", VP + f"/{case_id}", "整车采购办理")
        bsource = cars[car_b["vin"]]
        ret_proof = await proof_upload(e, case_id, inventory, fixture, "evidence", "synthetic-supplier-return.txt", "本次B车保留原采购收车来源，经独立批准实际退回原供应商；退运不等于退款。")
        return_touch = mutable(e, case_id, vehicles={car_b["id"]})
        return_touch["vehicles"] = {car_b["id"]: {"updated_at", "version"}}
        return_touch["vehicle_custodies"] = {bsource["custody"]["id"]: {"version"}}
        return_touch.pop("vehicle_positions")
        _, current, requested = await purchase_action(e, fixture, case_id, "return_request", inventory,
            {"reason": "合成B车按原采购来源申请退供应商"}, [("shipment_id", bsource["shipment"]["id"]), ("evidence_id", ret_proof["file"]["id"])], append={"vehicle_purchase_returns"}, update=return_touch)
        ret = e.db.rows("SELECT * FROM vehicle_purchase_returns WHERE case_id=? AND shipment_id=?", (case_id, bsource["shipment"]["id"]))
        require(len(ret) == 1 and ret[0]["status"] == "requested" and ret[0]["requested_by"] == inventory["id"], "原退回申请错误")
        ret = ret[0]
        manager, _, ret_owner = await purchase_owner(e, context, credentials, fixture, case_id, "vp_return_approve", "manager")
        return_touch = mutable(e, case_id, vehicles={car_b["id"]}, returns={ret["id"]})
        return_touch["vehicles"] = {car_b["id"]: {"updated_at", "version"}}
        return_touch["vehicle_custodies"] = {bsource["custody"]["id"]: {"version"}}
        return_touch.pop("vehicle_positions")
        _, current, ret_approved = await purchase_action(e, fixture, case_id, "return_approve", manager, {"reason": "独立核对B车原供方收车来源与实际退运安排"},
            extra=f'[data-id="{ret["id"]}"]', update=return_touch)
        require(one(e, "vehicle_purchase_returns", ret["id"])["approved_by"] == manager["id"] != inventory["id"], "退车申请/批准未独立")
        inventory, _, ret_physical = await purchase_owner(e, context, credentials, fixture, case_id, "vp_return_dispatch", "inventory")
        _, current, dispatched = await purchase_action(e, fixture, case_id, "return_dispatch", inventory, {"reason": "已核对原B车VIN和现场实际退运合成凭据"},
            [("evidence_id", ret_proof["file"]["id"])], extra=f'[data-id="{ret["id"]}"]', append={"vehicle_purchase_movements", "vehicle_position_entries"},
            update=mutable(e, case_id, vehicles={car_b["id"]}, shipments={bsource["shipment"]["id"]}, returns={ret["id"]}))
        return_movement = [m for m in current["movements"] if m["return_id"] == ret["id"]]
        require(len(return_movement) == 1 and return_movement[0]["original_id"] == bsource["movement"]["id"] and return_movement[0]["quantity"] == -1
                and return_movement[0]["value_cents"] == -2000 and one(e, "vehicle_purchase_shipments", bsource["shipment"]["id"])["status"] == "returned", "B车实际采购退回原账错误")
        bfinal = vehicle_fact(e, car_b["id"])
        require(bfinal["vehicle"]["approval_state"] == "void" and bfinal["position"]["status"] == "exited" and bfinal["custody"]["current_vehicle_id"] is None, "采购退回未退出真实库存")
        finance, view, refund_owner = await purchase_owner(e, context, credentials, fixture, case_id, "vp_refund", "finance")
        require(view["totals"]["supplier_refund_due_cents"] == 2000 and view["totals"]["paid_net_cents"] == 3000, "实际退车提前变现金退款")
        refund_proof = await proof_upload(e, case_id, finance, fixture, "receipt", "synthetic-supplier-refund.txt", "本次原B车付款2000分由原供应商退到原账户；仅本次合成实际资金输入。")
        original_payment = payments[1]["payment"]
        reference = "SYNTHETIC-VI-REFUND-" + token
        refund, current, refund_native = await purchase_action(e, fixture, case_id, "refund", finance,
            {"amount": "20", "reference": reference}, [("original_payment_id", original_payment["id"]), ("account_id", account_id), ("evidence_id", refund_proof["file"]["id"])],
            append={"cash_entries", "vehicle_purchase_payments"}, update=mutable(e, case_id, account=account_id))
        payment = next(p for p in current["payments"] if p["reference"] == reference)
        refund_fact = payment_fact(e, case_id, payment["id"], finance, account, 2000, "in", original=original_payment["id"])
        require(refund["totals"]["paid_net_cents"] == refund["totals"]["commitment_cents"] == 1000 and refund["totals"]["supplier_refund_due_cents"] == refund["totals"]["payable_cents"] == 0
                and current["case"]["state"] == "completed" and sum(p["amount_cents"] if p["direction"] == "out" else -p["amount_cents"] for p in current["payments"]) == 1000,
                "原供应方退款后净款/约定未闭合")
        require(one(e, "vehicle_purchase_payments", original_payment["id"]) == original_payment, "退款改写原付款")
        await expect(e.page.locator("#main")).to_contain_text("已退回供应商")
        await expect(e.page.locator("#main")).to_contain_text(reference)
        await checkpoint.passed({"case_id": case_id, "B_source": bsource, "request": requested, "review_owner": ret_owner, "approve": ret_approved,
            "physical_owner": ret_physical, "dispatch": dispatched, "return_movement": return_movement[0], "exited_vehicle": bfinal,
            "refund_owner": refund_owner, "refund_native": refund_native, "refund": refund_fact, "final_totals": refund["totals"]},
            [{"id": "transit-return-cancel-partial-refund", "status": "not_tested", "requirement": "conditional"}])
        refresh_before = e.business_snapshot("before_vehicle_final_refresh")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == VP + f"/{case_id}") as pending:
            e.action("reload", "刷新同原采购结果核对无重复实物或款项")
            await e.page.reload()
        require((await pending.value).status == 200, "原采购最终刷新失败")
        await expect(e.page.locator("#main h1")).to_have_text("整车采购办理")
        e.business_unchanged(refresh_before, "after_vehicle_final_refresh")
        final_a = vehicle_fact(e, new_vehicle_id)
        require(final_a["vehicle"]["approval_state"] == "approved" and final_a["custody"]["current_vehicle_id"] == new_vehicle_id, "B车退回破坏A车新代次")
        owned_cases = {case_id, move_id, out_id, return_id}
        require(not [task for task in rows(e, "flow_tasks") if task["case_id"] in owned_cases and task["status"] == "open"], "原车辆实物流转仍有未完成待办")
        checkpoint.finish({"purchase_case_id": case_id, "import_batch_ids": {"funds": funds_batch, "ship": ship_batch, "receive": receive_batch},
            "invalid_duplicate_batch_id": duplicate_id, "vin_manifest_row_ids": {r["vin"]: r["id"] for r in funds["rows"]},
            "original_vehicle_ids": [car_a["id"], car_b["id"]], "current_vehicle_id": new_vehicle_id,
            "local_move_case_id": move_id, "other_out_case_id": out_id, "other_return_case_id": return_id,
            "purchase_return_id": ret["id"], "purchase_return_movement_id": return_movement[0]["id"],
            "payment_ids": [p["payment"]["id"] for p in payments], "refund_payment_id": payment["id"],
            "cash_ids": [p["cash"]["id"] for p in payments] + [refund_fact["cash"]["id"]],
            "account_id": account_id, "source_location_id": location["id"], "destination_location_id": destination["id"],
            "final_A": final_a, "final_B": bfinal, "refresh_business_unchanged": True})
    except Exception as exc:
        checkpoint.failed(str(exc))
        raise


VEHICLE_OPERATIONS_SCENARIOS = ((SCENARIO, vehicle_operations, 720),)
