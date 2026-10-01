"""Unregistered original invoice and nonempty period-close browser candidate.

Every business write is an employee's original form click. SELECT-only facts
come from the current external mirror and its fully passed finance dependency.
External invoices are explicit synthetic inputs, never tax-provider acceptance.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, require
from sales_order_business import fixed_dependency, fen_text
from vehicle_purchase_business import live_choice, select_value, rejected_submit
from finance_business import submit, original_form, get_match

SCENARIO = "finance-followon-hk095-097"
DEPENDENCY = "finance-hk087-090-091-093-096"
INVOICES = "/api/invoices"
RECON = "/api/reconciliation"
REQUIREMENTS = (("HK-095", "月结查询"), ("HK-097", "开发票"))
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_files", "file_security",
    "file_scan_events", "flow_request_receipts", "invoice_applications", "invoice_approvals",
    "invoice_results", "reconciliation_batches", "reconciliation_issues", "reconciliation_events",
    "reconciliation_receipts",
}
READ_TABLES = TABLES | {
    "users", "stores",
    "flow_customers", "flow_accounts", "cash_entries", "flow_payment_links", "service_orders",
    "service_quotes", "service_tender_slices", "business_finance_advances",
    "business_finance_advance_entries", "business_finance_credit_links", "business_finance_statements",
    "business_finance_statement_lines", "business_finance_cash_batches", "business_finance_cash_allocations",
    "business_finance_stored_corrections",
}
VERSION = {"version", "updated_at"}
CASE_COLUMNS = VERSION | {"state", "completed_date"}
TASK_COLUMNS = VERSION | {"status", "done_by", "done_at"}
COMMON = {"flow_events": 1, "audit_logs": 1}
INVOICE_COMMON = {**COMMON, "flow_request_receipts": 1}
RECON_COMMON = {**COMMON, "reconciliation_events": 1, "reconciliation_receipts": 1}
INVOICE_LABELS = {
    "approve": "独立复核批准", "submit": "登记已提交外部办理", "difference": "记录票据差异",
    "record": "登记实际发票", "review_result": "独立复核结果差异",
}
RECON_LABELS = {
    "issue": "记录本条差异", "resolve": "记录差异处理结果", "submit": "提交独立店长复核",
    "seal": "复核封存", "recalculate": "重算为新版本", "reopen": "注明原因并复开",
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def pk(table):
    return "file_id" if table == "file_security" else "id"


def rows(e, table):
    require(table in READ_TABLES, "开票核账读取表未经核准")
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {pk(table)}")


def one(e, table, key):
    require(table in READ_TABLES, "开票核账原表未经核准")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {pk(table)}=?", (key,))
    require(len(found) == 1, "有限原来源缺失或重复：" + table)
    return found[0]


def related(e, table, field, key):
    require(table in READ_TABLES and field in {"case_id", "source_case_id", "batch_id", "advance_id", "statement_id"},
            "开票核账关联字段未经核准")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {pk(table)}", (key,))


def case(e, key):
    row = one(e, "flow_cases", key)
    row["data"] = json.loads(row["data"])
    return row


def task(e, key, name):
    found = [r for r in related(e, "flow_tasks", "case_id", key) if r["key"] == name and r["status"] == "open"]
    require(len(found) == 1, "原核账/开票本人待办不唯一：" + name)
    return found[0]


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]),
                    "开票核账原标题/check未核准：" + key)
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "candidate_sha256": sha(Path(__file__).read_bytes()), "source_contract_sha256": self.digest,
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "human_acceptance": "pending", "business_accepted": False,
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                                       "status": "not_tested", "evidence": {}}]} for key, title in REQUIREMENTS],
            "conditional_checks": [
                {"id": "HK-097", "status": "not_tested", "scope": "实际税务平台、经营主体策略、佣金开票、失败重办及原票过额"},
                {"id": "HK-095", "status": "not_tested", "scope": "跨期/跨店清算、旧定义1–21复验及超过前200来源的办理"}],
            "conditions": {"tax_provider_acceptance": False, "bank_acceptance": False,
                           "file_scan": "structure_only_not_clamav", "production_acceptance": False,
                           "member_principal_used": False, "synthetic_external_invoice_inputs": True,
                           "file_storage_validation": "blob_fixture_private_local_pending"},
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        if self.active["status"] == "not_tested":
            self.active.update(status="running", evidence_action_start=len(self.e.actions))
            self.active["acceptance_checks"][0]["status"] = "running"
        require(self.active["status"] == "running", "不能重开已结束原需求")
        self.save()

    def note(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].setdefault("steps", []).append(value)
        self.save()

    async def passed(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].update(status="passed", evidence=value)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active = None
        self.save()

    def failed(self, error):
        for r in self.report["requirements"]:
            if r["status"] == "running":
                status = "failed" if r is self.active else "partial"
                r["status"] = status
                r["acceptance_checks"][0].update(status=status, error=self.e.scrub(error))
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "source_or_final_guard")
        self.save()

    def finish(self, value):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "开票与核账两项未完整实际通过")
        self.report.update(complete=True, passed=True, executed_requirements=2, passed_requirements=2,
                           finance_followon_sources=value)
        self.save()


class Guard:
    def __init__(self, e, label, actor, *, append, update=None, cases=(), new_kind=None, customer=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = dict(append), update or {}
        self.cases, self.new_kind, self.customer = set(cases), new_kind, customer
        require(self.append.keys() | self.update.keys() <= TABLES, "开票核账守卫越出原域")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append.keys() | self.update.keys()}

    def additions(self, table):
        return [r for r in rows(self.e, table) if r[pk(table)] not in {x[pk(table)] for x in self.old[table]}]

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append.keys() | self.update.keys(), "开票核账改变无关原表：" + str(sorted(changed)))
        added = {t: self.additions(t) for t in self.old}
        require({t: len(v) for t, v in added.items() if v} == {t: n for t, n in self.append.items() if n},
                "开票核账原事实新增数量不一致")
        new_cases = added.get("flow_cases", [])
        if new_cases:
            require(len(new_cases) == 1 and new_cases[0]["kind"] == self.new_kind
                    and new_cases[0]["flow_version"] == (3 if self.new_kind == "invoice" else 2)
                    and new_cases[0]["customer_id"] == self.customer
                    and new_cases[0]["created_by"] == new_cases[0]["owner_id"] == self.actor["id"],
                    "新增核账/开票原单身份、类型或客户错误")
        owned = self.cases | {r["id"] for r in new_cases}
        changed_columns = {}
        for t, old in self.old.items():
            current = {r[pk(t)]: r for r in rows(self.e, t)}
            changed_columns[t] = []
            for original in old:
                key = original[pk(t)]
                require(key in current, "开票核账删除原行：" + t)
                columns = {k for k in original if original[k] != current[key][k]}
                require(columns <= self.update.get(t, {}).get(key, set()), "开票核账覆盖原行/列：" + t + "/" + str(key))
                if columns:
                    changed_columns[t].append({"id": key, "columns": sorted(columns)})
            for r in added[t]:
                if "store_id" in r:
                    require(r["store_id"] == 1, "新增开票核账串店")
                if "case_id" in r:
                    require(r["case_id"] in owned, "新增开票核账串原单")
                if "customer_id" in r:
                    require(r["customer_id"] == self.customer, "新增开票串客户")
                for field in ("actor_id", "created_by", "opened_by", "prepared_by"):
                    if field in r:
                        require(r[field] == self.actor["id"], "新增开票核账借用身份：" + t)
                if t == "audit_logs":
                    require(r["entity_type"] == "flow" and r["entity_id"] in owned, "开票核账审计串原单")
                if t in {"file_security", "file_scan_events"}:
                    require(one(self.e, "flow_files", r["file_id"])["case_id"] in owned, "扫描事实串原附件")
                if t == "invoice_applications":
                    require(r["id"] in owned and r["source_case_id"] in self.cases, "发票申请串原来源")
                if t == "reconciliation_batches":
                    require(r["case_id"] in owned and r["prepared_by"] == self.actor["id"], "新核账批次串原单或经办人")
                if t == "reconciliation_issues":
                    require(one(self.e, "reconciliation_batches", r["batch_id"])["case_id"] in owned, "差异串对账批次")
        result = {"label": self.label, "changed_tables": sorted(changed),
                  "appended_ids": {t: [r[pk(t)] for r in v] for t, v in added.items()},
                  "updated_columns": changed_columns, "expected_append_counts": self.append,
                  "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("finance_followon_original_guard", result)
        return result


def mutable(e, key, *, source=None, batch=None, issue=None, data=False):
    out = {"flow_cases": {key: CASE_COLUMNS | ({"data"} if data else set())},
           "flow_tasks": {r["id"]: TASK_COLUMNS for r in related(e, "flow_tasks", "case_id", key)}}
    if source:
        out["flow_cases"][source] = VERSION
    if batch:
        out["reconciliation_batches"] = {batch: VERSION | {"status", "submitted_by", "sealed_by", "sealed_at"}}
    if issue:
        out["reconciliation_issues"] = {issue: VERSION | {"status", "resolved_by", "resolution", "resolution_evidence_id"}}
    return out


def event(e, guard, key, actor, action, *, reconciliation=False):
    native, audits = guard.additions("flow_events"), guard.additions("audit_logs")
    require(len(native) == len(audits) == 1 and native[0]["action"] == action
            and native[0]["case_id"] == audits[0]["entity_id"] == key
            and native[0]["actor_id"] == audits[0]["actor_id"] == actor["id"]
            and audits[0]["action"] == "flow_" + action and native[0]["after_state"] == case(e, key)["state"],
            "原事件及唯一审计未绑定本次动作")
    result = {"flow_event_id": native[0]["id"], "audit_id": audits[0]["id"], "action": action,
              "detail": json.loads(native[0]["detail"])}
    if reconciliation:
        original = guard.additions("reconciliation_events")
        require(len(original) == 1 and original[0]["case_id"] == key and original[0]["actor_id"] == actor["id"]
                and original[0]["action"] == action, "对账原事件未匹配本人动作")
        result["reconciliation_event_id"] = original[0]["id"]
    return result


def receipt(e, actor, request, result, action, *, reconciliation=False):
    payload = {k: v for k, v in request.items() if k != "request_id"}
    if reconciliation:
        table = "reconciliation_receipts"
        hashed = digest({"action": action, "values": payload})
    else:
        table = "flow_request_receipts"
        if action != "create":
            payload = {"id": result["id"], **payload}
        hashed = digest({"operation": "invoice_v3_" + action, "payload": payload})
    found = e.db.rows(f"SELECT * FROM {table} WHERE request_key=?", (request["request_id"],))
    require(len(found) == 1 and found[0]["store_id"] == 1 and found[0]["actor_id"] == actor["id"]
            and found[0]["digest"] == hashed, "开票核账原回执未绑定完整参数")
    if reconciliation:
        require(json.loads(found[0]["result"]) == result, "对账回执不是原实际响应")
    else:
        require(found[0]["case_id"] == result["id"], "开票回执串原单")
    return {"id": found[0]["id"], "digest": hashed, "result_sha256": digest(result)}


def invoice_facts(e, key):
    return {"case": case(e, key), "application": one(e, "invoice_applications", key),
            "approvals": related(e, "invoice_approvals", "case_id", key),
            "results": related(e, "invoice_results", "case_id", key),
            "tasks": related(e, "flow_tasks", "case_id", key), "events": related(e, "flow_events", "case_id", key)}


def batch_facts(e, key):
    row = one(e, "reconciliation_batches", key)
    row["manifest"], row["summary"] = json.loads(row["manifest"]), json.loads(row["summary"])
    return {"batch": row, "case": case(e, row["case_id"]), "issues": related(e, "reconciliation_issues", "batch_id", key),
            "tasks": related(e, "flow_tasks", "case_id", row["case_id"]),
            "events": related(e, "reconciliation_events", "case_id", row["case_id"])}


def invoice_view(e, view, key):
    facts = invoice_facts(e, key)
    row, application = facts["case"], facts["application"]
    require(all(view[k] == row[k] for k in ("id", "number", "state", "version", "store_id", "title", "amount_cents"))
            and all(view[k] == application[k] for k in ("source_case_id", "original_case_id", "direction", "issuer_name",
                                                      "issuer_tax_id", "buyer_name", "buyer_tax_id", "reason"))
            and application["amount_cents"] == row["amount_cents"]
            and view["source_version"] == case(e, application["source_case_id"])["version"], "原票页面字段与DB不一致")
    if facts["results"]:
        require(len(facts["results"]) == 1 and all(view["result"][k] == facts["results"][0][k]
                for k in ("invoice_number", "amount_cents", "issued_on", "evidence_id")), "原票实际结果未匹配DB")
    else:
        require(view["result"] is None, "原票页面虚构实际结果")
    return facts


def batch_view(e, view, key):
    facts = batch_facts(e, key)
    require(all(view[k] == v for k, v in comparable(facts["batch"]).items())
            and view["case_version"] == facts["case"]["version"]
            and view["issues"] == [comparable(r) for r in facts["issues"]]
            and view["definition_version"] == facts["batch"]["summary"]["definition_version"] == 22
            and view["digest"] == digest({"manifest": view["manifest"], "summary": view["summary"]}),
            "原对账页面/完整冻结来源/digest与DB不一致")
    require(facts["case"]["kind"] == "reconciliation" and facts["case"]["flow_version"] == 2
            and facts["case"]["store_id"] == 1 and facts["case"]["data"]["reconciliation_id"] == key,
            "原核账批次与Case来源不一致")
    return facts


async def read_as(e, context, credentials, fixture, role, domain, key):
    if domain == "invoice":
        route, path = "invoices/" + str(key), f"{INVOICES}/orders/{key}"
    elif domain == "batch":
        route, path = "reconciliation/" + str(key), f"{RECON}/batches/{key}"
    else:
        route, path = "case/" + str(key), f"/api/flow/cases/{key}"
    async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/auth/login") as identity_pending:
            actor = await login_as(e, context, credentials, "admin" if role == "admin" else fixture[role + "_key"], route, 1)
    identity_response = await identity_pending.value
    identity = await identity_response.json()
    require(identity_response.status == 200 and identity["id"] == actor["id"]
            and identity["account_role"] == actor["role"] and identity["role"] == role
            and identity["active_store_id"] == 1 and identity["aggregate_scope"] is False
            and 1 in identity["store_ids"], "原登录响应没有当前一店本人岗位投影")
    e.observe("reconciliation_native_actor", {"actor_id": actor["id"], "account_role": identity["account_role"],
              "current_role": role, "active_store_id": 1, "original_login_status": 200, "aggregate_scope": False})
    response = await pending.value
    view = await response.json()
    require(response.status == 200, "本人不能读取原票/对账/任务页")
    if domain == "invoice":
        f = invoice_view(e, view, key)
        title = "原票冲红" if f["application"]["direction"] == "red" else "开票申请"
        await expect(e.page.locator("#main .pagehead")).to_contain_text(f["case"]["number"])
    elif domain == "batch":
        batch_view(e, view, key)
        title = "业务对账与月结"
    else:
        title = case(e, key)["title"]
        require(view["id"] == key and view["version"] == case(e, key)["version"], "原Case读取版本或对象错误")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return actor, view


async def responsible(e, context, credentials, fixture, domain, key, task_key, role):
    if role == "admin":
        require(domain == "batch" and task_key == "reconcile_seal", "管理员只参与本批原独立封存复核")
    case_id = key if domain == "invoice" else one(e, "reconciliation_batches", key)["case_id"]
    original = task(e, case_id, task_key)
    selected = e.manifest["users"]["admin" if role == "admin" else fixture[role + "_key"]]
    evidence = {"task_id": original["id"], "key": task_key, "actor_id": selected["id"],
                "handoff_needed": original["assignee_id"] != selected["id"]}
    if evidence["handoff_needed"]:
        manager, _ = await read_as(e, context, credentials, fixture, "manager", "case", case_id)
        button = f'#main [data-act="assign"][data-id="{original["id"]}"]'
        await expect(e.page.locator(button)).to_be_visible()
        await expect(e.page.locator(button)).to_be_enabled()
        await e.click(button, "主管在已加载的原任务页明确交接本人待办")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, selected)
        reason = "本次合成开票核账由所选当前门店岗位本人办理"
        await e.fill('#modal [name="reason"]', reason, "填写明确原待办交接依据")
        guard = Guard(e, "handoff_" + task_key, manager, append=COMMON,
                      update={"flow_tasks": {original["id"]: VERSION | {"assignee_id"}}}, cases={case_id})
        _, request, _, meta = await submit(e, f'/api/flow/tasks/{original["id"]}/assign', f"/api/flow/cases/{case_id}")
        require(request == {"version": original["version"], "assignee_id": selected["id"], "reason": reason},
                "原AssignInput三字段或本人身份错误")
        evidence.update(native=meta, guard=guard.finish(), event=event(e, guard, case_id, manager, "reassign"))
    actor, view = await read_as(e, context, credentials, fixture, role, domain, key)
    current = task(e, case_id, task_key)
    expected_task_role = "manager" if role == "admin" else role
    require(current["assignee_id"] == actor["id"] and current["role"] == expected_task_role,
            "原待办未由当前岗位本人接手或原任务岗位改变")
    evidence["task_version"] = current["version"]
    evidence["task_role"] = current["role"]
    evidence["actor_role"] = role
    return actor, view, evidence


async def upload(e, context, credentials, fixture, role, domain, key, category, purpose, token):
    case_id = key if domain == "invoice" else one(e, "reconciliation_batches", key)["case_id"]
    actor, _ = await read_as(e, context, credentials, fixture, role, "case", case_id)
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    destination = directory / (purpose + "-" + token + ".txt")
    content = ("合成浏览器输入；不表示真实税务开票、公司资金或客户签字。\n" + purpose +
               "；原单=" + str(case_id) + "；独立凭据=" + uuid.uuid4().hex + "\n").encode()
    destination.write_bytes(content)
    await expect(e.page.locator('#main [data-act="upload"]')).to_be_visible()
    await e.click('#main [data-act="upload"]', "员工选择并上传本次原事实文件")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "明确本单文件类别")
    e.action("select_file", "选择外部独立合成原件", filename=destination.name, sha256=sha(content))
    await e.page.locator('#modal [name="file"]').set_input_files(str(destination))
    guard = Guard(e, "upload_" + purpose, actor,
                  append={**COMMON, "flow_files": 1, "file_security": 1, "file_scan_events": 1}, cases={case_id})
    body, _, _, meta = await submit(e, f"/api/flow/cases/{case_id}/files", f"/api/flow/cases/{case_id}", multipart=True)
    asset = one(e, "flow_files", body["id"])
    stored = asset.pop("content")
    require(isinstance(stored, bytes) and stored == content and asset["size"] == len(content)
            and asset["sha256"] == sha(content) and asset["case_id"] == case_id and asset["category"] == category
            and asset["name"] == destination.name and asset["media_type"] == "text/plain; charset=utf-8"
            and asset["created_by"] == actor["id"] and not asset["generated"], "原附件BLOB/元信息与实际选中文件不匹配")
    security = one(e, "file_security", asset["id"])
    scans = [r for r in rows(e, "file_scan_events") if r["file_id"] == asset["id"]]
    require(len(scans) == 1 and security["state"] == scans[0]["state"] == "structure_only"
            and scans[0]["action"] == "initial" and scans[0]["actor_id"] == actor["id"]
            and scans[0]["sha256"] == sha(content) and scans[0]["size"] == len(content)
            and body["security"]["can_use"], "原结构扫描及本单使用权限不完整")
    await expect(e.page.locator("#main .filerecord").filter(has_text=destination.name)).to_have_count(1)
    proof = {"file": asset, "stored_blob": {"length": len(content), "sha256": sha(content)},
             "native": meta, "guard": guard.finish(), "event": event(e, guard, case_id, actor, "upload"),
             "clamav_acceptance": False}
    await read_as(e, context, credentials, fixture, role, domain, key)
    return proof


async def choose_file(e, proof):
    asset = proof["file"]
    label = {"evidence": "业务凭据", "invoice": "发票"}[asset["category"]]
    await live_choice(e, "evidence_id", asset["name"], asset["name"] + " · " + label, expected_value=asset["id"])


def comparable(row):
    from datetime import datetime
    out = {}
    for k, v in row.items():
        if isinstance(v, str) and len(v) > 18 and v[4:5] == "-" and v[7:8] == "-" and v[10:11] == " ":
            v = datetime.fromisoformat(v).isoformat()
        out[k] = v
    return out


def dependencies(e, cp):
    root = Path(e.manifest["evidence_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True
            and Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"),
            "开票核账只能消费同轮外部合成库")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf8"))
    require(provenance.get("snapshot_stable") is True, "开票核账镜像没有稳定冻结")
    for name in ("finance_followon_business.py", "finance_business.py", "sales_business.py", "sales_order_business.py",
                 "vehicle_purchase_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()),
                "开票核账与前序脚本不是同轮指纹：" + name)
    original = fixed_dependency(e, cp, DEPENDENCY)
    src = dict(original["finance_sources"])
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    for role in ("finance", "manager", "admin"):
        actor = e.manifest["users"]["admin" if role == "admin" else fixture[role + "_key"]]
        current = one(e, "users", actor["id"])
        require(current["active"] == 1 and current["role"] == actor["role"] == role,
                "开票核账缺当前有效随机本人员工")
        if role == "admin":
            require(one(e, "stores", 1)["active"] == 1, "独立复核目标门店未启用")
        else:
            require(len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=? AND role=?",
                    (actor["id"], 1, role))) == 1, "开票核账缺当前逐店本人员工岗位")
    customer = one(e, "flow_customers", src["customer_id"])
    account = one(e, "flow_accounts", src["account_id"])
    require(fixture["store_id"] == customer["store_id"] == account["store_id"] == 1 and account["active"],
            "前序客户或实际账户不属于当前门店")
    require(len(src["service_case_ids"]) == len(src["quote_ids"]) == 2, "前序必须完整输出两张真实服务原单")
    services = []
    for key, quote_id in zip(src["service_case_ids"], src["quote_ids"]):
        c, s, q = case(e, key), one(e, "service_orders", key), one(e, "service_quotes", quote_id)
        payments = related(e, "flow_payment_links", "case_id", key)
        tenders = related(e, "service_tender_slices", "case_id", key)
        require(c["store_id"] == 1 and c["customer_id"] == customer["id"]
                and c["kind"] == "other_income" and c["flow_version"] == 2 and c["state"] == "completed"
                and c["amount_cents"] == q["fee_cents"] == 6000 and q["pass_cents"] == q["discount_cents"] == 0 and q["case_id"] == key
                and sum(r["amount_cents"] for r in tenders) == 6000
                and {r["id"] for r in payments} <= set(src["payment_link_ids"]), "前序服务真实履约/收费/当前收款不完整")
        require(not related(e, "invoice_applications", "source_case_id", key), "前序A/B已有开票，不能改用旧票据成绩")
        services.append({"case": c, "order": s, "quote": q, "payments": payments, "tenders": tenders})
    advance = one(e, "business_finance_advances", src["advance_id"])
    correction = one(e, "business_finance_stored_corrections", src["stored_correction_id"])
    batches = [one(e, "business_finance_cash_batches", key) for key in src["collection_batch_ids"]]
    require(advance["customer_id"] == customer["id"] and advance["balance_cents"] == advance["reserved_cents"] == 0
            and advance["initial_cents"] == 10000 and advance["correction_cents"] == -1000
            and correction["original_cash_id"] == src["original_advance_cash_id"]
            and correction["corrected_cash_id"] == src["corrected_cash_id"], "前序预收实际更正/抵用/退款没有完成")
    cash_ids = [src["original_advance_cash_id"], correction["reversing_cash_id"], src["corrected_cash_id"],
                *[r["cash_id"] for r in batches], src["refund_cash_id"]]
    cash = [one(e, "cash_entries", key) for key in cash_ids]
    require(len(set(cash_ids)) == len(cash_ids) == 6
            and [(r["direction"], r["amount_cents"]) for r in cash] ==
            [("in", 10000), ("out", 10000), ("in", 9000), ("in", 3000), ("in", 5000), ("out", 5000)]
            and all(r["store_id"] == 1 and r["account"] == account["name"] and r["approval_state"] == "approved" for r in cash),
            "前序六笔原现金金额、方向或账户错误")
    entries = related(e, "business_finance_advance_entries", "advance_id", advance["id"])
    require([(r["purpose"], r["amount_cents"]) for r in entries] ==
            [("receive", 10000), ("correction", -1000), ("apply", -4000), ("refund", -5000)], "前序预收账不守恒")
    src.update(cash_ids=cash_ids, reversing_cash_id=correction["reversing_cash_id"])
    pinned = {"services": services, "cash": cash, "advance": advance, "entries": entries,
              "correction": correction, "batches": batches, "customer": customer, "account": account,
              "credit": one(e, "business_finance_credit_links", src["credit_link_id"]),
              "statement": one(e, "business_finance_statements", src["statement_id"]),
              "statement_lines": related(e, "business_finance_statement_lines", "statement_id", src["statement_id"])}
    cp.report.update(mirror={"source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]},
                     source_preconditions=pinned)
    cp.save()
    return fixture, src, pinned


def invoice_balance(e, source_id):
    actual, pending = 0, 0
    for application in related(e, "invoice_applications", "source_case_id", source_id):
        result = related(e, "invoice_results", "case_id", application["id"])
        if result:
            require(len(result) == 1, "一张申请有重复原实际票据")
            actual += result[0]["amount_cents"] * (1 if application["direction"] == "blue" else -1)
        elif application["direction"] == "blue" and case(e, application["id"])["state"] not in {"cancelled", "rejected"}:
            pending += application["amount_cents"]
    return {"invoiceable_cents": 6000, "actual_net_cents": actual, "pending_blue_cents": pending,
            "available_cents": max(0, 6000 - actual - pending), "correction_cents": max(0, actual - 6000)}


async def source_button(e, context, credentials, fixture, source_id):
    async with e.page.expect_response(lambda r: get_match(r, INVOICES + "/sources")) as pending:
        actor = await login_as(e, context, credentials, fixture["finance_key"], "invoices", 1)
    response = await pending.value
    shown = await response.json()
    require(response.status == 200, "不能读取原业务开票依据")
    await expect(e.page.locator("#main h1")).to_have_text("开票与原票冲红")
    while not any(r["id"] == source_id for r in shown["items"]):
        require(shown["page"] * shown["page_size"] < shown["total"], "本轮业务不在真实开票来源目录")
        button = '#main [data-act="invoice-page"][data-kind="source"][data-page="' + str(shown["page"] + 1) + '"]'
        before = e.business_snapshot("before_original_invoice_source_page")
        async with e.page.expect_response(lambda r: get_match(r, INVOICES + "/sources")) as pending:
            await expect(e.page.locator(button)).to_be_enabled()
            await e.click(button, "通过原分页找到本次业务开票依据")
        response = await pending.value
        shown = await response.json()
        require(response.status == 200, "开票来源下一页读取失败")
        e.business_unchanged(before, "after_original_invoice_source_page")
    original = next(r for r in shown["items"] if r["id"] == source_id)
    require({k: original[k] for k in invoice_balance(e, source_id)} == invoice_balance(e, source_id),
            "原开票来源额度与真实已登记票据不一致")
    button = f'#main [data-act="invoice-new"][data-source="{source_id}"]'
    await expect(e.page.locator(button)).to_be_visible()
    await expect(e.page.locator(button)).to_be_enabled()
    async with e.page.expect_response(lambda r: get_match(r, f"{INVOICES}/sources/{source_id}")) as pending:
        await e.click(button, "明确选择本轮服务原单申请开票")
    response = await pending.value
    source = await response.json()
    require(response.status == 200 and source["id"] == source_id, "原开票表单选择了错误原单")
    await expect(e.page.locator("#modal-title")).to_have_text("申请原业务开票")
    return actor, source


async def submit_new_entity(e, path, render_prefix, *, status):
    responses = []
    matching = asyncio.get_running_loop().create_future()
    expected_path = None

    def observe(response):
        if get_match(response, render_prefix):
            responses.append(response)
            if urlsplit(response.url).path == expected_path and not matching.done():
                matching.set_result(response)

    e.page.on("response", observe)
    try:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人核对后提交原表单并查看本次新单")
        response = await pending.value
        body = await response.json()
        require(response.status == status and type(body.get("id")) is int and body["id"] > 0,
                f"原新单HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
        expected_path = render_prefix + str(body["id"])
        for read in responses:
            if urlsplit(read.url).path == expected_path and not matching.done():
                matching.set_result(read)
        read = await asyncio.wait_for(matching, 30)
        shown = await read.json()
        headers = await response.request.all_headers()
        request = response.request.post_data_json
        require(read.status == 200 and shown["id"] == body["id"]
                and headers.get("x-app-request") == "1" and headers.get("x-store-id") == "1"
                and headers.get("cookie") and headers.get("x-csrf-token")
                and isinstance(request, dict) and len(request.get("request_id", "")) >= 16,
                "新单精确读取、原同源员工门店/CSRF/请求号不完整")
        route = "invoices" if render_prefix == INVOICES + "/orders/" else "reconciliation"
        await expect(e.page).to_have_url(e.origin.rstrip("/") + "/#" + route + "/" + str(body["id"]))
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main .notice.error")).to_have_count(0)
        meta = {"path": path, "method": "POST", "status": status, "native_ui": True,
                "cookie_present": True, "csrf_present": True, "store_id": 1,
                "request_id_sha256": sha(request["request_id"].encode()),
                "render_get_path": expected_path, "render_get_status": read.status,
                "created_entity_id": body["id"],
                "unrelated_render_gets": sum(urlsplit(r.url).path != expected_path for r in responses)}
        e.observe("finance_followon_new_entity_submit", meta)
        return body, request, shown, meta
    finally:
        e.page.remove_listener("response", observe)


async def invoice_create(e, context, credentials, fixture, src, token, amount, *, original=None):
    source_id = src["service_case_ids"][0]
    if original:
        actor, view = await read_as(e, context, credentials, fixture, "finance", "invoice", original)
        async with e.page.expect_response(lambda r: get_match(r, f"{INVOICES}/sources/{source_id}")) as pending:
            await e.click('#main [data-act="invoice-red"]', "关联本次已登记蓝票明确部分冲红")
        response = await pending.value
        source = await response.json()
        require(response.status == 200, "原红票表单读取依据失败")
        await expect(e.page.locator("#modal-title")).to_have_text("申请关联原票冲红")
        issuer_name, issuer_tax_id, buyer_name, buyer_tax_id = [view[k] for k in ("issuer_name", "issuer_tax_id", "buyer_name", "buyer_tax_id")]
    else:
        actor, source = await source_button(e, context, credentials, fixture, source_id)
        issuer = source["issuer"]
        issuer_name = issuer["legal_name"] if issuer else "本轮合成开票经营主体" + token
        issuer_tax_id = issuer["tax_identifier"] if issuer else "SYNTHETIC0000000001"
        buyer_name, buyer_tax_id = one(e, "flow_customers", src["customer_id"])["name"], ""
        if not issuer:
            await e.fill('#modal [name="issuer_name"]', issuer_name, "填写明确合成销售主体全称")
            await e.fill('#modal [name="issuer_tax_id"]', issuer_tax_id, "填写明确合成大写税号")
        await e.fill('#modal [name="buyer_name"]', buyer_name, "填写本轮真实合成客户抬头")
        await e.fill('#modal [name="buyer_tax_id"]', buyer_tax_id, "个人购买方税号按原表单可空")
    day = await e.page.locator('#modal [name="due_date"]').input_value()
    require(len(day) == 10, "原业务今天/计划日期缺失")
    reason = "明确本次合成原票部分冲红，不登记现金退款" if original else "依据本轮已履约服务实际办理合成开票"
    await e.fill('#modal [name="amount"]', fen_text(amount), "填写本次真实申请金额")
    await e.fill('#modal [name="reason"]', reason, "填写本次原票办理依据")
    before_source = case(e, source_id)
    guard = Guard(e, "invoice_create_" + str(amount), actor,
                  append={**INVOICE_COMMON, "flow_cases": 1, "flow_tasks": 1, "invoice_applications": 1},
                  update={"flow_cases": {source_id: VERSION}}, cases={source_id}, new_kind="invoice", customer=src["customer_id"])
    body, request, shown, meta = await submit_new_entity(e, INVOICES + "/orders", INVOICES + "/orders/", status=201)
    expected = {"source_case_id": source_id, "source_version": before_source["version"], "direction": "red" if original else "blue",
                "original_case_id": original, "amount_cents": amount, "issuer_name": issuer_name, "issuer_tax_id": issuer_tax_id,
                "buyer_name": buyer_name, "buyer_tax_id": buyer_tax_id, "due_date": day, "reason": reason}
    require(request == {"request_id": request["request_id"], **expected}, "原开票创建内容、来源或版本不匹配")
    facts = invoice_view(e, shown, body["id"])
    require(body == shown and facts["case"]["state"] == "approval" and facts["case"]["parent_id"] == source_id
            and facts["case"]["amount_cents"] == amount
            and all(facts["application"][k] == expected[k] for k in ("source_case_id", "original_case_id", "direction", "amount_cents",
                                                                    "issuer_name", "issuer_tax_id", "buyer_name", "buyer_tax_id", "reason"))
            and facts["application"]["source_version"] == case(e, source_id)["version"] > before_source["version"],
            "原开票冻结申请/父单/来源版本不正确")
    return body["id"], {"facts": facts, "native": meta, "guard": guard.finish(),
                        "event": event(e, guard, body["id"], actor, "invoice_v3_create"),
                        "receipt": receipt(e, actor, request, body, "create"), "day": day}


async def invoice_action(e, context, credentials, fixture, key, action, token, *, amount=None, number=None):
    role = "manager" if action in {"approve", "review_result"} else "finance"
    task_key = {"approve": "invoice_review", "submit": "invoice_submit", "difference": "invoice_result",
                "record": "invoice_result", "review_result": "invoice_result_review"}[action]
    actor, _, handoff = await responsible(e, context, credentials, fixture, "invoice", key, task_key, role)
    category = "invoice" if action == "record" else "evidence"
    proof = await upload(e, context, credentials, fixture, role, "invoice", key, category, action + "-" + str(key), token)
    _, view = await read_as(e, context, credentials, fixture, role, "invoice", key)
    await original_form(e, "invoice-action", action, INVOICE_LABELS[action])
    values = {"reason": "本人按本次独立合成票据核对并登记" + action, "evidence_id": proof["file"]["id"]}
    if action == "submit":
        values["reference"] = "SYN-EXT-" + str(key) + "-" + token
        await e.fill('#modal [name="reference"]', values["reference"], "登记明确合成外部办理编号")
    elif action == "difference":
        values.update(external_number="SYN-DIFF-" + token, observed_amount_cents=amount)
        await e.fill('#modal [name="external_number"]', values["external_number"], "记录实际待核对票据编号")
        await e.fill('#modal [name="observed_amount"]', fen_text(amount), "记录合成实际票面与批准差异")
    elif action == "record":
        values.update(invoice_number=number, issued_on=await e.page.locator('#modal [name="issued_on"]').input_value(), amount_cents=amount)
        await e.fill('#modal [name="invoice_number"]', number, "登记本次唯一真实合成票号")
        await e.fill('#modal [name="amount"]', fen_text(amount), "按本次原票实际金额登记")
    await choose_file(e, proof)
    await e.fill('#modal [name="reason"]', values["reason"], "填写本人办理及核对结论")
    before = invoice_facts(e, key)
    source_id = before["application"]["source_case_id"]
    added = {"invoice_approvals": 1, "flow_tasks": 1} if action == "approve" else {"flow_tasks": 1} if action == "submit" else {}
    if action == "record":
        added = {"invoice_results": 1, **({"flow_tasks": 1} if amount != before["application"]["amount_cents"] else {})}
    guard = Guard(e, "invoice_" + action, actor, append={**INVOICE_COMMON, **added},
                  update=mutable(e, key, source=source_id, data=action == "submit"),
                  cases={key, source_id}, customer=before["case"]["customer_id"])
    body, request, shown, meta = await submit(e, f"{INVOICES}/orders/{key}/actions/{action}", f"{INVOICES}/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": before["case"]["version"],
            "source_version": view["source_version"], "values": values}, "开票原动作双CAS或实际参数不正确")
    facts = invoice_view(e, shown, key)
    expected_state = {"approve": "pending", "submit": "working", "difference": "working", "review_result": "completed"}.get(action)
    if action == "record":
        expected_state = "resolving" if amount != before["application"]["amount_cents"] else "completed"
        result = facts["results"][0]
        require(result["amount_cents"] == amount and result["invoice_number"] == number
                and result["issued_on"] == values["issued_on"] and result["issuer_tax_id"] == before["application"]["issuer_tax_id"]
                and result["actor_id"] == actor["id"] and result["evidence_id"] == proof["file"]["id"], "实际票据未匹配员工输入")
        await expect(e.page.locator("#main")).to_contain_text(number)
    require(body == shown and facts["case"]["state"] == expected_state
            and facts["case"]["version"] > before["case"]["version"]
            and case(e, source_id)["version"] > view["source_version"], "开票原状态或成功版本不正确")
    current_task = one(e, "flow_tasks", handoff["task_id"])
    require(current_task["status"] == ("open" if action == "difference" else "done")
            and (action == "difference" or current_task["done_by"] == actor["id"]), "开票原本人待办未按真实结果推进")
    if action == "approve":
        approval = facts["approvals"][0]
        require(len(facts["approvals"]) == 1 and approval["actor_id"] == actor["id"]
                and approval["evidence_id"] == proof["file"]["id"] and approval["reason"] == values["reason"]
                and actor["id"] != before["case"]["created_by"], "原票未有独立批准事实")
    if action == "submit":
        require(facts["case"]["data"]["external_reference"] == values["reference"], "实际外部提交编号未保存")
    require(shown["balance"] == invoice_balance(e, source_id), "原票详情额度/净额与DB不一致")
    original_event = event(e, guard, key, actor, "invoice_v3_" + action)
    require(original_event["detail"] == values, "原票办理事件没有保留本次真实事实")
    return {"facts": facts, "native": meta, "handoff": handoff, "proof": proof, "guard": guard.finish(),
            "event": original_event,
            "receipt": receipt(e, actor, request, body, action)}


def frozen(batch):
    return {k: batch[k] for k in ("case_id", "start", "end", "revision", "previous_id", "prepared_by",
                                  "reason", "digest", "manifest", "summary")}


def batch_sources(e, view, src, result_ids=()):
    require(view["manifest"] and len({r["key"] for r in view["manifest"]}) == len(view["manifest"]), "对账没有完整唯一非空来源")
    matched = []
    samples = [("cash_entries", src["cash_ids"]), ("flow_payment_links", src["payment_link_ids"]),
               ("service_orders", src["service_case_ids"]), ("service_quotes", src["quote_ids"]),
               ("business_finance_advances", [src["advance_id"]]),
               ("business_finance_stored_corrections", [src["stored_correction_id"]]),
               ("business_finance_credit_links", [src["credit_link_id"]]),
               ("business_finance_cash_batches", src["collection_batch_ids"]), ("invoice_results", list(result_ids))]
    for table, ids in samples:
        for key in ids:
            found = [r for r in view["manifest"] if r["source"] == table and r["source_id"] == key]
            require(len(found) == 1, "完整核账来源缺少本轮原事实：" + table + "/" + str(key))
            original = comparable(one(e, table, key))
            for field, value in found[0]["data"].items():
                require(field in original, "核账本轮源出现无原模型字段")
                expected = original[field]
                if isinstance(value, (dict, list)) and isinstance(expected, str):
                    expected = json.loads(expected)
                if value is None and expected == "null":
                    expected = None
                require(expected == value, "完整核账来源字段不同于原事实：" + table + "/" + field)
            matched.append({"key": found[0]["key"], "basis": found[0]["basis"], "data_sha256": digest(found[0]["data"])})
    excluded = set(view["summary"]["excluded_cash_ids"])
    require({src["original_advance_cash_id"], src["reversing_cash_id"]} <= excluded
            and not ({src["corrected_cash_id"], src["refund_cash_id"]} & excluded), "现金定义7未保护原误记/冲正及正确收退款")
    totals = {"in": 0, "out": 0}
    own_totals = {"in": 0, "out": 0}
    for entry in view["manifest"]:
        if entry["source"] != "cash_entries" or entry["source_id"] in excluded or entry["data"]["category"] == "transfer":
            continue
        data = entry["data"]
        require(entry["basis"] == "period" and type(data["amount_cents"]) is int, "现金来源期间/整数分口径错误")
        totals[data["direction"]] += data["amount_cents"]
        if entry["source_id"] in src["cash_ids"]:
            own_totals[data["direction"]] += data["amount_cents"]
    require(totals["in"] == view["summary"]["period_cash_in_cents"]
            and totals["out"] == view["summary"]["period_cash_out_cents"]
            and own_totals == {"in": 17000, "out": 5000}, "完整期间现金摘要或本轮净现金12000不守恒")
    return {"matched_sources": matched, "all_store_effective_cash_cents": totals,
            "same_run_effective_cash_cents": own_totals, "same_run_cash_net_cents": 12000,
            "definition_version": 22, "cash_definition_version": 7,
            "background_not_claimed_as_new_business": True}


async def create_batch(e, context, credentials, fixture, src):
    async with e.page.expect_response(lambda r: get_match(r, "/api/flow/catalog")) as catalog_pending:
        async with e.page.expect_response(lambda r: get_match(r, RECON + "/batches")) as pending:
            actor = await login_as(e, context, credentials, fixture["finance_key"], "reconciliation", 1)
    response, catalog_response = await pending.value, await catalog_pending.value
    listing, catalog = await response.json(), await catalog_response.json()
    require(response.status == catalog_response.status == 200, "原对账目录或当前业务日读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("业务对账与月结")
    day = catalog["today"]
    dates = [one(e, "cash_entries", key)["business_date"] for key in src["cash_ids"]]
    dates += [case(e, key)["business_date"] for key in src["service_case_ids"]] + [day]
    start, end = min(dates), max(dates)
    require(end <= day and not any(r["start"] == start and r["end"] == end for r in listing["items"]),
            "本次真实来源期间已有批次或超过当前业务日，不能绕过")
    await expect(e.page.locator('#main [data-act="reconcile-new"]')).to_be_visible()
    await e.click('#main [data-act="reconcile-new"]', "财务冻结本轮实际非空期间业务来源")
    await expect(e.page.locator("#modal-title")).to_have_text("新建业务期间对账")
    reason = "核对本轮客户预收更正、抵用、两服务收款及原款退款完整来源"
    for name, value in (("start", start), ("end", end), ("reason", reason)):
        await e.fill(f'#modal [name="{name}"]', value, "明确本次期间核账 " + name)
    guard = Guard(e, "reconcile_create", actor,
                  append={**RECON_COMMON, "flow_cases": 1, "flow_tasks": 1, "reconciliation_batches": 1}, new_kind="reconciliation")
    body, request, shown, meta = await submit_new_entity(e, RECON + "/batches", RECON + "/batches/", status=201)
    require(request == {"request_id": request["request_id"], "start": start, "end": end, "reason": reason}
            and body == shown and shown["status"] == "draft" and shown["revision"] == 1
            and shown["previous_id"] is None and shown["prepared_by"] == actor["id"] and not shown["source_changed"],
            "真实原对账版本1或期间参数不一致")
    facts = batch_view(e, shown, body["id"])
    return body["id"], {"facts": facts, "native": meta, "guard": guard.finish(),
                        "event": event(e, guard, facts["case"]["id"], actor, "reconcile_create", reconciliation=True),
                        "receipt": receipt(e, actor, request, body, "batch_create", reconciliation=True),
                        "sources": batch_sources(e, shown, src), "day": day}


async def batch_action(e, context, credentials, fixture, key, action, token, *, line=None, issue_id=None, seal_role="manager"):
    require(seal_role in {"manager", "admin"}, "原独立复核岗位超出当前店长或管理员范围")
    role = seal_role if action == "seal" else "manager" if action == "reopen" else "finance"
    handoff = None
    if action in {"submit", "seal"}:
        actor, view, handoff = await responsible(e, context, credentials, fixture, "batch", key,
                                                "reconcile_seal" if action == "seal" else "reconcile", role)
    else:
        actor, view = await read_as(e, context, credentials, fixture, role, "batch", key)
    proof = None
    if action in {"issue", "resolve", "seal"}:
        proof = await upload(e, context, credentials, fixture, role, "batch", key, "evidence", action + "-" + str(key), token)
        actor, view = await read_as(e, context, credentials, fixture, role, "batch", key)
    selector = f'#main [data-act="reconcile-action"][data-key="{action}"]'
    if line:
        selector += '[data-line="' + line + '"]'
    if issue_id:
        selector += '[data-id="' + str(issue_id) + '"]'
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "员工按本批原来源办理 " + action)
    await expect(e.page.locator("#modal-title")).to_have_text(RECON_LABELS[action])
    reasons = {
        "issue": "差额为0；核对本轮100元误记、冲回和90元正确记录的完整对应关系",
        "resolve": "已逐原StoredCorrection和六现金核对；原误记与冲正保留，正确9000加月结8000减退款5000净12000；无需另改账",
        "submit": "本人核对全部原来源、完整CSV及已处理差异后提交另一主管复核",
        "seal": "独立核对本轮完整来源及原处理凭据，确认来源未变后封存",
        "recalculate": "新增本轮蓝红票实际结果，原版本保留，明确重算为新版本",
        "reopen": "独立复开已封存版本用于复核原冻结内容，未修改任何原业务账目",
    }
    values = {"reason": reasons[action]}
    if proof:
        await choose_file(e, proof)
        values["evidence_id"] = proof["file"]["id"]
    if action == "issue":
        values.update(line_key=line, difference_cents=0)
        await e.fill('#modal [name="difference"]', "0", "有据核对原误记与冲正，明确不造现金差额")
    if action == "resolve":
        original_issue = one(e, "reconciliation_issues", issue_id)
        values.update(issue_id=issue_id, issue_version=original_issue["version"])
    await e.fill('#modal [name="reason"]', values["reason"], "填写本人本批实际核对依据")
    before = batch_facts(e, key)
    case_id = before["case"]["id"]
    new_version = action in {"recalculate", "reopen"}
    added = {"reconciliation_issues": 1} if action == "issue" else {"flow_tasks": 1} if action == "submit" else {}
    if new_version:
        added = {"flow_cases": 1, "flow_tasks": 1, "reconciliation_batches": 1,
                 "flow_events": 2, "audit_logs": 2, "reconciliation_events": 2}
    guard = Guard(e, "reconcile_" + action, actor, append={**RECON_COMMON, **added},
                  update=mutable(e, case_id, batch=key, issue=issue_id), cases={case_id}, new_kind="reconciliation")
    path = f"{RECON}/batches/{key}/actions/{action}"
    body, request, shown, meta = (await submit_new_entity(e, path, RECON + "/batches/", status=200) if new_version
                                  else await submit(e, path, f"{RECON}/batches/{key}"))
    require(request == {"request_id": request["request_id"], "version": before["batch"]["version"],
            "case_version": before["case"]["version"], "values": values} and body == shown,
            "原对账动作双CAS、差异版本或实际响应不一致")
    after = batch_view(e, shown, shown["id"])
    old_after = batch_facts(e, key)
    require(frozen(old_after["batch"]) == frozen(before["batch"]), "原对账历史冻结内容被覆盖")
    if new_version:
        require(shown["previous_id"] == key and shown["revision"] == before["batch"]["revision"] + 1
                and shown["prepared_by"] == actor["id"] and shown["status"] == "draft" and not shown["source_changed"]
                and old_after["batch"]["status"] == ("sealed" if action == "reopen" else "superseded"),
                "原对账后继版本链或旧状态错误")
        expected_pairs = {(case_id, "reconcile_" + action), (after["case"]["id"], "reconcile_create")}
        native, audits, original = guard.additions("flow_events"), guard.additions("audit_logs"), guard.additions("reconciliation_events")
        require({(r["case_id"], r["action"]) for r in native} == expected_pairs
                and {(r["case_id"], r["action"]) for r in original} == expected_pairs
                and {(r["entity_id"], r["action"]) for r in audits} == {(i, "flow_" + a) for i, a in expected_pairs}
                and all(r["actor_id"] == actor["id"] for r in native + audits + original), "对账追加版本的两组唯一事件/审计错误")
        events = {"flow_event_ids": [r["id"] for r in native], "audit_ids": [r["id"] for r in audits],
                  "reconciliation_event_ids": [r["id"] for r in original]}
    else:
        expected_state = {"issue": "draft", "resolve": "draft", "submit": "review", "seal": "sealed"}[action]
        require(shown["id"] == key and shown["status"] == expected_state, "原核账动作状态错误")
        events = event(e, guard, case_id, actor, "reconcile_" + action, reconciliation=True)
        if action == "seal":
            require(shown["sealed_by"] == actor["id"] and actor["id"] not in {shown["prepared_by"], shown["submitted_by"]}
                    and after["case"]["state"] == "completed", "原核账未由不同主管独立封存")
        if action == "resolve":
            resolved = one(e, "reconciliation_issues", issue_id)
            require(resolved["status"] == "resolved" and resolved["resolved_by"] == actor["id"]
                    and resolved["resolution"] == values["reason"] and resolved["resolution_evidence_id"] == proof["file"]["id"],
                    "差异原处理结果或独立原件未匹配")
        if action == "issue":
            added_issue = guard.additions("reconciliation_issues")
            require(len(added_issue) == 1 and all(added_issue[0][k] == values[k] for k in ("line_key", "difference_cents", "reason", "evidence_id"))
                    and added_issue[0]["status"] == "open" and added_issue[0]["batch_id"] == key
                    and added_issue[0]["opened_by"] == actor["id"], "原有据差异内容或批次错误")
    return shown["id"], {"facts": after, "original_version_after": old_after, "native": meta, "handoff": handoff,
                         "proof": proof, "guard": guard.finish(), "events": events,
                         "receipt": receipt(e, actor, request, body, "batch:" + str(key) + ":" + action, reconciliation=True)}


def csv_cell(value):
    if value is None:
        return ""
    text = str(value)
    return "'" + text if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else text


async def export_csv(e, context, credentials, fixture, key):
    actor, view = await read_as(e, context, credentials, fixture, "finance", "batch", key)
    path = f"{RECON}/batches/{key}/export"
    before = e.business_snapshot("before_original_reconciliation_csv")
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
            await e.click('#main [data-act="reconcile-action"][data-key="export"]', "下载本版本全部原冻结来源CSV")
        response = await pending.value
        headers = await response.request.all_headers()
        require(response.status == 200 and headers.get("cookie") and headers.get("x-store-id") == "1"
                and headers.get("x-app-request") == "1", "原同源CSV下载状态或员工门店错误")
    download = await downloaded.value
    require(await download.failure() is None, "原CSV实际下载失败")
    directory = e.directory / "exports"
    directory.mkdir(exist_ok=True)
    destination = directory / ("reconciliation-" + str(key) + "-r" + str(view["revision"]) + ".csv")
    await download.save_as(destination)
    raw = destination.read_bytes()
    actual = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    expected = [["对账版本", "源条目", "来源", "期间或时点", "原单", "金额分", "数量千分位", "权益单位", "冻结来源内容"]]
    for entry in view["manifest"]:
        data = entry["data"]
        values = [view["revision"], entry["key"], entry["source"], entry["basis"], entry["case_id"] or "",
                  data.get("amount_cents", data.get("value_cents", "")), data.get("quantity_milli", ""), data.get("units", ""),
                  json.dumps(data, ensure_ascii=False, sort_keys=True)]
        expected.append([csv_cell(v) for v in values])
    require(raw.startswith(b"\xef\xbb\xbf") and actual == expected, "原CSV不是本版本完整冻结来源、整数口径或原转义")
    e.business_unchanged(before, "after_original_reconciliation_csv")
    evidence = {"path": str(destination), "sha256": sha(raw), "size": len(raw), "rows": len(actual) - 1,
                "batch_id": key, "revision": view["revision"], "frozen_digest": view["digest"],
                "native_http": {"method": "GET", "path": path, "status": 200, "cookie_present": True, "store_id": 1},
                "all_business_rows_unchanged": True, "no_export_audit_in_original_contract": True,
                "actor_id": actor["id"]}
    e.observe("original_reconciliation_csv", evidence)
    return evidence


async def download_invoice(e, context, credentials, fixture, key):
    actor, view = await read_as(e, context, credentials, fixture, "finance", "invoice", key)
    file_id = view["result"]["evidence_id"]
    asset = one(e, "flow_files", file_id)
    content = asset.pop("content")
    guard = Guard(e, "download_original_invoice", actor, append={"audit_logs": 1}, cases={key}, customer=case(e, key)["customer_id"])
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: get_match(r, f"/api/flow/files/{file_id}")) as pending:
            await e.click(f'#main [data-act="downloadfile"][data-id="{file_id}"]', "下载本次实际票据原件核对字节")
        response = await pending.value
        headers = await response.request.all_headers()
        require(response.status == 200 and headers.get("cookie") and headers.get("x-store-id") == "1"
                and headers.get("x-app-request") == "1", "原票据同源下载失败或门店身份错误")
    download = await downloaded.value
    require(await download.failure() is None, "原票据浏览器下载失败")
    directory = e.directory / "exports"
    directory.mkdir(exist_ok=True)
    destination = directory / ("invoice-" + str(key) + ".txt")
    await download.save_as(destination)
    raw = destination.read_bytes()
    audit = guard.additions("audit_logs")
    require(isinstance(content, bytes) and raw == content and len(raw) == asset["size"] and sha(raw) == asset["sha256"]
            and len(audit) == 1 and audit[0]["action"] == "download" and audit[0]["actor_id"] == actor["id"]
            and audit[0]["entity_id"] == key and audit[0]["reason"] == "下载文件 " + str(file_id), "票据原字节或唯一下载审计不匹配")
    return {"path": str(destination), "size": len(raw), "sha256": sha(raw), "file": asset,
            "audit_id": audit[0]["id"], "guard": guard.finish()}


def preserve_finance(e, src, pinned):
    for original in pinned["cash"]:
        require(one(e, "cash_entries", original["id"]) == original, "开票核账覆盖原现金")
    for table, key, original in (
        ("business_finance_advances", src["advance_id"], pinned["advance"]),
        ("business_finance_stored_corrections", src["stored_correction_id"], pinned["correction"]),
        ("business_finance_credit_links", src["credit_link_id"], pinned["credit"]),
        ("business_finance_statements", src["statement_id"], pinned["statement"]),
        ("flow_customers", src["customer_id"], pinned["customer"]), ("flow_accounts", src["account_id"], pinned["account"]),
    ):
        require(one(e, table, key) == original, "开票核账改写已passed财务来源：" + table)
    require(related(e, "business_finance_advance_entries", "advance_id", src["advance_id"]) == pinned["entries"]
            and related(e, "business_finance_statement_lines", "statement_id", src["statement_id"]) == pinned["statement_lines"],
            "开票核账覆盖原本金Entry或冻结月结行")
    for original in pinned["batches"]:
        require(one(e, "business_finance_cash_batches", original["id"]) == original, "核账产生第二笔原收款关联")
    for i, original in enumerate(pinned["services"]):
        key = original["case"]["id"]
        current = case(e, key)
        require(all(current[k] == v for k, v in original["case"].items() if i != 0 or k not in VERSION)
                and one(e, "service_orders", key) == original["order"]
                and one(e, "service_quotes", original["quote"]["id"]) == original["quote"]
                and related(e, "flow_payment_links", "case_id", key) == original["payments"]
                and related(e, "service_tender_slices", "case_id", key) == original["tenders"], "核账/票据替代或覆盖原服务收费与款项")
    return {"same_run_cash_net_cents": 12000, "service_charge_cents": 12000, "invoice_a_net_cents": 6000,
            "original_cash_and_finance_rows_unchanged": True, "member_and_inventory_protected_each_action": True}


async def finance_followon_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, src, pinned = dependencies(e, cp)
        token = uuid.uuid4().hex[:10].upper()
        cp.start("HK-095")
        first, created = await create_batch(e, context, credentials, fixture, src)
        cp.note({"created_nonempty_version_1": created})
        first_frozen = frozen(batch_facts(e, first)["batch"])
        cp.start("HK-097")
        blue, blue_create = await invoice_create(e, context, credentials, fixture, src, token, 6000)
        cp.note({"blue_created": blue_create})
        blue_steps = []
        for action, kwargs in (("approve", {}), ("submit", {}), ("difference", {"amount": 5800}),
                               ("record", {"amount": 5800, "number": "SYN-BLUE-" + token}), ("review_result", {})):
            step = await invoice_action(e, context, credentials, fixture, blue, action, token, **kwargs)
            blue_steps.append(step)
            cp.note({"blue_action": action, "result": step})
        red, red_create = await invoice_create(e, context, credentials, fixture, src, token, 800, original=blue)
        cp.note({"linked_red_created": red_create})
        red_steps = []
        for action, kwargs in (("approve", {}), ("submit", {}), ("record", {"amount": 800, "number": "SYN-RED-" + token})):
            step = await invoice_action(e, context, credentials, fixture, red, action, token, **kwargs)
            red_steps.append(step)
            cp.note({"red_action": action, "result": step})
        require(invoice_balance(e, src["service_case_ids"][0])["actual_net_cents"] == 5000, "原部分冲红未形成5800减800净5000")
        supplement, supplement_create = await invoice_create(e, context, credentials, fixture, src, token, 1000)
        cp.note({"new_blue_created": supplement_create})
        supplement_steps = []
        for action, kwargs in (("approve", {}), ("submit", {}), ("record", {"amount": 1000, "number": "SYN-BLUE2-" + token})):
            step = await invoice_action(e, context, credentials, fixture, supplement, action, token, **kwargs)
            supplement_steps.append(step)
            cp.note({"new_blue_action": action, "result": step})
        result_ids = [invoice_facts(e, key)["results"][0]["id"] for key in (blue, red, supplement)]
        require(invoice_balance(e, src["service_case_ids"][0]) ==
                {"invoiceable_cents": 6000, "actual_net_cents": 6000, "pending_blue_cents": 0, "available_cents": 0, "correction_cents": 0}
                and invoice_facts(e, red)["application"]["original_case_id"] == blue, "三实际票据净額/原蓝红关联不正确")
        downloads = [await download_invoice(e, context, credentials, fixture, key) for key in (blue, red, supplement)]
        await cp.passed({"blue": blue_create, "blue_actual_difference_steps": blue_steps, "red": red_create,
                         "red_actual_steps": red_steps, "supplement_blue": supplement_create,
                         "supplement_actual_steps": supplement_steps, "result_ids": result_ids,
                         "native_original_downloads": downloads, "net_invoice_cents": 6000,
                         "unchanged_finance": preserve_finance(e, src, pinned), "tax_provider_acceptance": False})
        cp.start("HK-095")
        actor, old_view, handoff = await responsible(e, context, credentials, fixture, "batch", first, "reconcile", "finance")
        require(old_view["source_changed"] is True and frozen(batch_facts(e, first)["batch"]) == first_frozen,
                "真实票据产生后旧来源未提示变化或被覆盖")
        await original_form(e, "reconcile-action", "submit", RECON_LABELS["submit"])
        await e.fill('#modal [name="reason"]', "明确核对旧版本来源变化应拒绝，随后按原流程重算", "填写原来源变化边界")
        refusal = await rejected_submit(e, f"{RECON}/batches/{first}/actions/submit", 409, "来源有晚到、冲正或余额变化")
        cp.note({"source_changed_409_without_write": refusal, "handoff": handoff})
        second, recalculated = await batch_action(e, context, credentials, fixture, first, "recalculate", token)
        cp.note({"recalculated_version_2": recalculated})
        _, current = await read_as(e, context, credentials, fixture, "finance", "batch", second)
        source_evidence = batch_sources(e, current, src, result_ids)
        line = "cash_entries:" + str(src["original_advance_cash_id"])
        require(line in {r["key"] for r in current["manifest"][:200]},
                "本轮待核Cash不在原UI前200来源，不能API或DOM代办差异")
        _, opened = await batch_action(e, context, credentials, fixture, second, "issue", token, line=line)
        issue_ids = opened["guard"]["appended_ids"]["reconciliation_issues"]
        require(len(issue_ids) == 1, "有据差异没有唯一原Issue")
        issue_id = issue_ids[0]
        _, resolved = await batch_action(e, context, credentials, fixture, second, "resolve", token, issue_id=issue_id)
        cp.note({"issue": opened, "resolved": resolved})
        _, stable = await read_as(e, context, credentials, fixture, "finance", "batch", second)
        require(stable["source_changed"] is False and stable["manifest"] == current["manifest"]
                and stable["digest"] == current["digest"], "本批证明文件或Issue错误影响定义22原业务来源")
        csv2 = await export_csv(e, context, credentials, fixture, second)
        _, submitted2 = await batch_action(e, context, credentials, fixture, second, "submit", token)
        _, sealed2 = await batch_action(e, context, credentials, fixture, second, "seal", token)
        cp.note({"version_2_full_csv": csv2, "submitted": submitted2, "sealed": sealed2})
        original_sealed = batch_facts(e, second)["batch"]
        third, reopened = await batch_action(e, context, credentials, fixture, second, "reopen", token)
        cp.note({"reopened_version_3": reopened})
        _, current3 = await read_as(e, context, credentials, fixture, "finance", "batch", third)
        require(current3["manifest"] == original_sealed["manifest"] and current3["summary"] == original_sealed["summary"]
                and current3["digest"] == original_sealed["digest"], "无业务变化复开仍改变原冻结范围")
        source3 = batch_sources(e, current3, src, result_ids)
        csv3 = await export_csv(e, context, credentials, fixture, third)
        _, submitted3 = await batch_action(e, context, credentials, fixture, third, "submit", token)
        _, sealed3 = await batch_action(e, context, credentials, fixture, third, "seal", token, seal_role="admin")
        preserved2 = batch_facts(e, second)["batch"]
        require(preserved2 == original_sealed and frozen(batch_facts(e, first)["batch"]) == first_frozen,
                "复开/后继封存覆盖旧封存记录或版本1内容")
        csv_old = await export_csv(e, context, credentials, fixture, second)
        await cp.passed({"created": created, "old_source_changed_409": refusal, "recalculated": recalculated,
                         "source_version_2": source_evidence, "issue": opened, "resolved": resolved,
                         "csv_version_2": csv2, "submitted_version_2": submitted2, "sealed_version_2": sealed2,
                         "reopened": reopened, "source_version_3": source3, "csv_version_3": csv3,
                         "submitted_version_3": submitted3, "sealed_version_3": sealed3,
                         "old_sealed_csv_after_reopen": csv_old, "old_frozen_rows_preserved": True,
                         "unchanged_finance": preserve_finance(e, src, pinned)})
        cp.finish({"customer_id": src["customer_id"], "source_case_id": src["service_case_ids"][0],
                   "blue_case_ids": [blue, supplement], "red_case_id": red, "invoice_result_ids": result_ids,
                   "reconciliation_batch_ids": [first, second, third],
                   "reconciliation_case_ids": [batch_facts(e, key)["case"]["id"] for key in (first, second, third)],
                   "issue_id": issue_id, "period": {"start": current3["start"], "end": current3["end"]},
                   "definition_version": 22, "cash_definition_version": 7})
    except Exception as error:
        cp.failed(error)
        raise


FINANCE_FOLLOWON_SCENARIOS = ((SCENARIO, finance_followon_business, 600),)


