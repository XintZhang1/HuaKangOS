"""Unregistered same-run customer advance, correction and statement candidate.

All writes use original employee forms. The only database access is SELECT in
the external synthetic mirror. No fixture money, member principal, or replay.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency, fen_text
from vehicle_purchase_business import live_choice, select_value, rejected_submit

SCENARIO = "finance-hk087-090-091-093-096"
SALES = "sales-order-hk008-009-011-022"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
SERVICE = "/api/service-orders"
FINANCE = "/api/business-finance"
REQUIREMENTS = (("HK-087", "财务预收款"), ("HK-090", "其他收款单调整"),
                ("HK-091", "客户应收款查询"), ("HK-093", "预收款退款"), ("HK-096", "客户月结处理"))
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_files", "file_security",
    "file_scan_events", "flow_accounts", "cash_entries", "flow_payment_links",
    "service_income_items", "service_orders", "service_quotes", "service_lines",
    "service_price_approvals", "service_authorizations", "service_fulfillments",
    "service_tender_slices", "service_requests", "business_finance_orders",
    "business_finance_advances", "business_finance_advance_entries", "business_finance_applications",
    "business_finance_credit_links", "business_finance_stored_correction_requests",
    "business_finance_stored_corrections", "business_finance_statements",
    "business_finance_statement_lines", "business_finance_cash_batches",
    "business_finance_cash_allocations", "business_finance_events", "business_finance_receipts",
}
CASE_COLUMNS = {"version", "updated_at", "state", "completed_date"}
SERVICE_CASE_COLUMNS = CASE_COLUMNS | {"amount_cents", "data"}
TASK_COLUMNS = {"version", "updated_at", "status", "done_by", "done_at"}
VERSION = {"version", "updated_at"}
COMMON = {"flow_events": 1, "audit_logs": 1}
SERVICE_COMMON = {**COMMON, "service_requests": 1}
FINANCE_COMMON = {**COMMON, "business_finance_events": 1, "business_finance_receipts": 1}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]),
                    key + " 财务原源合同未核准")
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "human_acceptance": "pending", "business_accepted": False,
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                                      "status": "not_tested", "evidence": {}}]} for key, title in REQUIREMENTS],
            "partial_requirements": [
                {"id": "HK-017", "status": "not_tested", "acceptance_check_submitted": False,
                 "unexecuted_scope": ["厂家原往来独立批准、实际收款与原款退款"]},
                {"id": "HK-088", "status": "not_tested", "acceptance_check_submitted": False,
                 "unexecuted_scope": ["整车厂家其它收入原源与实际收退"]}],
            "conditional_checks": [
                {"id": "HK-090", "status": "not_tested", "scope": "会员及组合本金更正、已退款原款更正"},
                {"id": "HK-096", "status": "not_tested", "scope": "晚到款冲突、追加重算版本、跨期及跨店"}],
            "conditions": {"synthetic_money_and_fulfillment_inputs": True, "bank_acceptance": False,
                           "file_scan": "structure_only_not_clamav", "business_entity_policy_acceptance": False,
                           "production_acceptance": False, "member_principal_used": False},
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def note(self, evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.active["acceptance_checks"][0].setdefault("steps", []).append(evidence)
        self.save()

    async def passed(self, evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active = None
        self.save()

    def failed(self, error):
        for r in self.report["requirements"]:
            if r["status"] == "running":
                status = "failed" if r is self.active else "partial"
                r["status"] = status
                r["acceptance_checks"][0].update(status=status, error=self.e.scrub(error))
        self.report.update(error=self.e.scrub(error),
                           failed_requirement=self.active["id"] if self.active else "source_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "财务五项未完整实际执行")
        self.report.update(complete=True, passed=True, executed_requirements=5, passed_requirements=5,
                           finance_sources=sources)
        for r in self.report["partial_requirements"]:
            r.update(status="partial", local_scope_status="customer_other_income_scope_passed",
                     evidence={"service_case_ids": sources["service_case_ids"]})
        self.save()
        self.e.observe("finance_original_checkpoint", {"path": str(self.path), "passed_checks": 5,
                       "full_193_business_acceptance": False})


def pk(table):
    return "file_id" if table == "file_security" else "id"


def rows(e, table):
    require(table in TABLES, "财务守卫表未核准：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {pk(table)}")


def one(e, table, key):
    require(table in TABLES | {"flow_customers"}, "财务原来源表未核准：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE {pk(table)}=?", (key,))
    require(len(found) == 1, "财务原记录缺失或重复：" + table)
    return found[0]


def related(e, table, field, key):
    allowed = {
        "case_id", "quote_id", "advance_id", "statement_id", "batch_id",
    }
    require(table in TABLES and field in allowed, "财务关联查询未核准")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {pk(table)}", (key,))


def case_facts(e, case_id):
    row = one(e, "flow_cases", case_id)
    row["data"] = json.loads(row["data"])
    return {"case": row, "tasks": related(e, "flow_tasks", "case_id", case_id),
            "events": related(e, "flow_events", "case_id", case_id)}


def service_facts(e, case_id):
    f = case_facts(e, case_id)
    f["order"] = one(e, "service_orders", case_id)
    f["order"]["vehicle_snapshot"] = json.loads(f["order"]["vehicle_snapshot"])
    f["quotes"] = related(e, "service_quotes", "case_id", case_id)
    quote_ids = {q["id"] for q in f["quotes"]}
    for key, table in (("lines", "service_lines"), ("approvals", "service_price_approvals"),
                       ("authorizations", "service_authorizations")):
        f[key] = [r for r in rows(e, table) if r["quote_id"] in quote_ids]
    for line in f["lines"]:
        line["payee_snapshot"] = json.loads(line["payee_snapshot"])
    f["fulfillments"] = related(e, "service_fulfillments", "case_id", case_id)
    f["tenders"] = related(e, "service_tender_slices", "case_id", case_id)
    f["payments"] = related(e, "flow_payment_links", "case_id", case_id)
    f["credits"] = related(e, "business_finance_credit_links", "case_id", case_id)
    return f


def finance_facts(e, case_id):
    f = case_facts(e, case_id)
    for key, table in (
        ("orders", "business_finance_orders"), ("advances", "business_finance_advances"),
        ("applications", "business_finance_applications"), ("entries", "business_finance_advance_entries"),
        ("stored_requests", "business_finance_stored_correction_requests"),
        ("stored_facts", "business_finance_stored_corrections"),
        ("statements", "business_finance_statements"), ("batches", "business_finance_cash_batches"),
        ("finance_events", "business_finance_events")):
        f[key] = related(e, table, "case_id", case_id)
    require(len(f["orders"]) == 1, "缺唯一财务原Order")
    f["order"] = f.pop("orders")[0]
    f["order"]["values"] = json.loads(f["order"]["values"])
    sids = {r["id"] for r in f["statements"]}
    bids = {r["id"] for r in f["batches"]}
    f["lines"] = [r for r in rows(e, "business_finance_statement_lines") if r["statement_id"] in sids]
    for line in f["lines"]:
        line["snapshot"] = json.loads(line["snapshot"])
    f["allocations"] = [r for r in rows(e, "business_finance_cash_allocations") if r["batch_id"] in bids]
    return f


def finance_view(e, view, facts):
    for key in ("case", "order"):
        require(all(view[key].get(field) == value for field, value in facts[key].items()
                    if field not in {"created_at", "updated_at"}), "原财务页面字段与DB不一致：" + key)
    for key, family in (("stored_request", "stored_requests"), ("statement", "statements"),
                        ("application", "applications")):
        if facts[family]:
            require(len(facts[family]) == 1 and all(view[key].get(field) == value
                    for field, value in facts[family][0].items() if field not in {"created_at", "updated_at"}),
                    "原财务页面冻结事实与DB不一致：" + key)
    if "advance" in view:
        advance_id = facts["advances"][0]["id"] if facts["advances"] else facts["applications"][0]["advance_id"]
        original = one(e, "business_finance_advances", advance_id)
        require(all(view["advance"].get(field) == value for field, value in original.items()
                    if field not in {"created_at", "updated_at"}), "财务页面原预收本金/占额/余额与DB不一致")
    require(view.get("lines", []) == facts["lines"]
            and sorted(view["allocations"], key=lambda r: r["id"]) == facts["allocations"]
            and sorted(view["batches"], key=lambda r: r["id"]) == facts["batches"], "月结页面冻结行及逐单资金分配与DB不一致")


def open_task(e, case_id, key):
    found = [r for r in related(e, "flow_tasks", "case_id", case_id) if r["key"] == key and r["status"] == "open"]
    require(len(found) == 1, "本人财务/服务原待办不唯一：" + key)
    return found[0]


def mutable(e, cases=(), *, order=None, advance=None, application=None, stored=None, account=None, service=False):
    result = {
        "flow_cases": {key: SERVICE_CASE_COLUMNS if service else CASE_COLUMNS for key in cases},
        "flow_tasks": {r["id"]: TASK_COLUMNS for key in cases for r in related(e, "flow_tasks", "case_id", key)},
    }
    if order:
        result["business_finance_orders"] = {order: VERSION | {"status", "approved_by"}}
    if advance:
        result["business_finance_advances"] = {advance: VERSION | {"balance_cents", "reserved_cents", "correction_cents"}}
    if application:
        result["business_finance_applications"] = {application: VERSION | {"status"}}
    if stored:
        result["business_finance_stored_correction_requests"] = {stored: VERSION | {"status"}}
    if account:
        result["flow_accounts"] = {account: VERSION}
    return {t: v for t, v in result.items() if v}


class Guard:
    """All tables protected; only this action's finite IDs and columns may change."""
    def __init__(self, e, label, actor, *, expected, update=None, cases=(), customer=None, new_kind=None):
        self.e, self.label, self.actor = e, label, actor
        self.expected, self.update = dict(expected), update or {}
        self.cases, self.customer, self.new_kind = set(cases), customer, new_kind
        require(self.expected.keys() | self.update.keys() <= TABLES, "财务动作守卫超出已审表范围")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.expected.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.expected.keys() | self.update.keys(), "财务动作改变无关原表：" + str(sorted(changed)))
        additions = {t: [r for r in rows(self.e, t) if r[pk(t)] not in {x[pk(t)] for x in old}]
                     for t, old in self.old.items()}
        require({t: len(v) for t, v in additions.items() if v} == {t: n for t, n in self.expected.items() if n},
                "财务原事实新增数错误：" + str({t: len(v) for t, v in additions.items() if v}))
        new_cases = additions.get("flow_cases", [])
        if new_cases:
            require(len(new_cases) == 1 and new_cases[0]["kind"] == self.new_kind
                    and new_cases[0]["flow_version"] == 2 and new_cases[0]["customer_id"] == self.customer
                    and new_cases[0]["created_by"] == new_cases[0]["owner_id"] == self.actor["id"],
                    "财务新原单身份/客户/类型不一致")
        owned = self.cases | {r["id"] for r in new_cases}
        updated = {}
        for table, old in self.old.items():
            current = {r[pk(table)]: r for r in rows(self.e, table)}
            updated[table] = []
            for original in old:
                key = original[pk(table)]
                require(key in current, "财务动作删除旧原事实：" + table)
                columns = {k for k in original if original[k] != current[key][k]}
                require(columns <= self.update.get(table, {}).get(key, set()),
                        "财务动作覆盖旧原行/列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": key, "columns": sorted(columns)})
            for r in additions[table]:
                if "store_id" in r:
                    require(r["store_id"] == 1, "财务新增事实串店：" + table)
                if "case_id" in r:
                    require(r["case_id"] in owned, "财务新增事实串原单：" + table)
                if "customer_id" in r:
                    require(r["customer_id"] == self.customer, "财务新增事实串客户")
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in r:
                        require(r[field] == self.actor["id"], "财务新增事实借用身份：" + table)
                if table == "audit_logs":
                    require(r["entity_type"] == "flow" and r["entity_id"] in owned, "财务新增审计串原业务")
                if "quote_id" in r:
                    require(one(self.e, "service_quotes", r["quote_id"])["case_id"] in owned, "财务服务事实串报价")
                if "batch_id" in r:
                    require(one(self.e, "business_finance_cash_batches", r["batch_id"])["case_id"] in owned, "月结分配串批次")
                if "statement_id" in r:
                    require(one(self.e, "business_finance_statements", r["statement_id"])["case_id"] in owned, "月结行串账单")
                if table == "service_orders":
                    require(r["id"] in owned and r["source_order_id"] is None and not r["delivery_blocking"],
                            "本批其它客户服务错误关联旧销售")
        result = {"label": self.label, "changed_tables": sorted(changed),
                  "appended_ids": {t: [r[pk(t)] for r in v] for t, v in additions.items()},
                  "updated_columns": updated, "expected_append_counts": self.expected,
                  "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("finance_original_guard", result)
        return result


def events(e, guard, case_id, actor, action, *, finance=False):
    added = [r for r in rows(e, "flow_events") if r["id"] not in {x["id"] for x in guard.old["flow_events"]}]
    audits = [r for r in rows(e, "audit_logs") if r["id"] not in {x["id"] for x in guard.old["audit_logs"]}]
    require(len(added) == len(audits) == 1 and added[0]["action"] == action
            and added[0]["actor_id"] == audits[0]["actor_id"] == actor["id"]
            and added[0]["case_id"] == audits[0]["entity_id"] == case_id
            and audits[0]["action"] == "flow_" + action, "财务原事件及审计未精确对应本人动作")
    result = {"flow_event_id": added[0]["id"], "audit_id": audits[0]["id"], "action": action,
              "detail": json.loads(added[0]["detail"])}
    if finance:
        native = [r for r in rows(e, "business_finance_events")
                  if r["id"] not in {x["id"] for x in guard.old["business_finance_events"]}]
        require(len(native) == 1 and native[0]["case_id"] == case_id and native[0]["actor_id"] == actor["id"]
                and action == "business_finance_" + native[0]["action"], "财务独立事件与原事件不一致")
        result["finance_event_id"] = native[0]["id"]
    return result


def receipt(e, request, actor, result, *, service_action=None, finance_action=None):
    if service_action:
        table, payload = "service_requests", {k: v for k, v in request.items() if k != "request_id"}
        if service_action.startswith("master_"):
            payload.setdefault("active", True)
        elif service_action != "create":
            payload["case_id"] = result["id"]
            if service_action == "quote":
                payload["values"] = dict(payload["values"])
                payload["values"]["lines"] = [
                    {"agency_project_id": None, "income_item_id": None, "payee_id": None, "name": "", **line}
                    for line in payload["values"]["lines"]]
        operation = "service_orders_" + service_action
        hashed = hashlib.sha256(json.dumps({"operation": operation, "payload": payload},
                                ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    else:
        table = "business_finance_receipts"
        payload = {k: v for k, v in request.items() if k != "request_id"}
        hashed = hashlib.sha256(json.dumps({"action": finance_action, "values": payload},
                                ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    found = e.db.rows(f"SELECT * FROM {table} WHERE request_key=?", (request["request_id"],))
    require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["store_id"] == 1
            and found[0]["digest"] == hashed and json.loads(found[0]["result"]) == result,
            "原回执未绑定本次本人完整参数及真实响应：" + table)
    return {"id": found[0]["id"], "digest": hashed, "actor_id": actor["id"],
            "result_sha256": hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


def get_match(response, path):
    actual = urlsplit(response.url).path
    return response.request.method == "GET" and (
        actual.startswith(path) and actual[len(path):].isdigit() if path.endswith("/") else actual == path)


async def submit(e, path, render_path, *, status=200, multipart=False):
    async with e.page.expect_response(lambda r: get_match(r, render_path)) as rendered:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人核对后提交原财务业务表单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原财务表单HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await rendered.value
    shown = await read.json()
    headers = await response.request.all_headers()
    request = None if multipart else response.request.post_data_json
    assign = path.startswith("/api/flow/tasks/") and path.endswith("/assign")
    require(read.status == 200 and headers.get("x-app-request") == "1" and headers.get("x-store-id") == "1"
            and headers.get("cookie") and headers.get("x-csrf-token")
            and (multipart or isinstance(request, dict) and (assign or len(request.get("request_id", "")) >= 16)),
            "财务原同源身份/CSRF/请求号或成功读取不完整")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    meta = {"path": path, "method": "POST", "status": status, "native_ui": True,
            "cookie_present": True, "csrf_present": True, "store_id": 1,
            "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request and request.get("request_id") else None,
            "submitted_version": request.get("version") if request else None,
            "submitted_case_version": request.get("case_version") if request else None,
            "render_get_path": urlsplit(read.url).path, "render_get_status": read.status}
    e.observe("finance_original_submit", meta)
    return body, request, shown, meta


async def ready(e, context, credentials, fixture, role, case_id, *, financial=False):
    path = f"{FINANCE}/orders/{case_id}" if financial else f"{SERVICE}/{case_id}"
    route = ("business-finance-order/" if financial else "service-orders/") + str(case_id)
    async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, 1)
    response = await pending.value
    view = await response.json()
    require(response.status == 200, "当前本人无法读取财务/服务原单")
    f = finance_facts(e, case_id) if financial else service_facts(e, case_id)
    seen = view["case"] if financial else view
    require(all(seen[k] == f["case"][k] for k in ("id", "number", "version", "state", "title")),
            "原单页面响应与当前DB不一致")
    if financial:
        finance_view(e, view, f)
    await expect(e.page.locator("#main h1")).to_have_text("财务业务办理" if financial else f["case"]["title"])
    await expect(e.page.locator("#main .pagehead")).to_contain_text(f["case"]["title"] if financial else f["case"]["number"])
    return actor, view


async def responsible(e, context, credentials, fixture, case_id, key, role, *, financial=False):
    target = e.manifest["users"][fixture[role + "_key"]]
    original = open_task(e, case_id, key)
    evidence = {"task_id": original["id"], "key": key, "actor_id": target["id"],
                "handoff_needed": original["assignee_id"] != target["id"]}
    if evidence["handoff_needed"]:
        manager = await login_as(e, context, credentials, fixture["manager_key"], "case/" + str(case_id), 1)
        await expect(e.page.locator("#main h1")).to_have_text(one(e, "flow_cases", case_id)["title"])
        selector = f'#main [data-act="assign"][data-id="{original["id"]}"]'
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "主管明确交接本次原岗位待办")
        await employee_choice(e, target)
        reason = "本次合成财务链由所选本店岗位员工本人核对办理"
        await e.fill('#modal [name="reason"]', reason, "填写原待办明确交接原因")
        guard = Guard(e, "original_handoff", manager, expected=COMMON,
                      update={"flow_tasks": {original["id"]: VERSION | {"assignee_id"}}}, cases={case_id})
        _, request, _, meta = await submit(e, f'/api/flow/tasks/{original["id"]}/assign', f"/api/flow/cases/{case_id}")
        require(request == {"version": original["version"], "assignee_id": target["id"], "reason": reason},
                "原AssignInput版本或本人员工不匹配")
        evidence.update(native=meta, protection=guard.finish(), events=events(e, guard, case_id, manager, "reassign"))
    actor, view = await ready(e, context, credentials, fixture, role, case_id, financial=financial)
    current = open_task(e, case_id, key)
    require(current["assignee_id"] == actor["id"] and current["role"] == role, "办理人不是本店原任务本人")
    evidence["current_version"] = current["version"]
    return actor, view, evidence


async def original_form(e, act, key, title, *, identifier=None):
    selector = f'#main [data-act="{act}"][data-key="{key}"]' + (f'[data-id="{identifier}"]' if identifier else "")
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        parent = button.locator("xpath=ancestor::details[1]")
        require(await parent.count() == 1 and await parent.get_attribute("open") is None, "原按钮隐藏且没有原展开栏目")
        summary = parent.locator(":scope > summary")
        await expect(summary).to_be_visible()
        e.action("click", "展开原次要办理栏目")
        await summary.click()
    await expect(button).to_be_visible()
    await expect(button).to_be_enabled()
    await e.click(selector, "本人打开原表单：" + title)
    await expect(e.page.locator("#modal-title")).to_have_text(title)


async def upload_original(e, case_id, actor, category, purpose, token, *, financial=False):
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    path = directory / (purpose + "-" + token + ".txt")
    content = ("合成浏览器输入，不表示真实公司款项或客户履约。\n用途=" + purpose +
               "；原单=" + str(case_id) + "；独立事实=" + uuid.uuid4().hex + "\n").encode("utf-8")
    path.write_bytes(content)
    await e.click('#main [data-act="upload"]', "选择并上传本单本次独立合成原件")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "选择原表单要求的本次文件类别")
    e.action("select_file", "员工选择外部合成输入文件", name=path.name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    guard = Guard(e, "upload_" + purpose, actor, expected={**COMMON, "flow_files": 1, "file_security": 1, "file_scan_events": 1},
                  cases={case_id})
    render = f"{FINANCE}/orders/{case_id}" if financial else f"{SERVICE}/{case_id}"
    body, _, _, meta = await submit(e, f"/api/flow/cases/{case_id}/files", render, multipart=True)
    asset = one(e, "flow_files", body["id"])
    stored = asset.pop("content")
    require(isinstance(stored, bytes) and stored == content and asset["size"] == len(content)
            and asset["sha256"] == hashlib.sha256(content).hexdigest()
            and asset["category"] == category and asset["case_id"] == case_id
            and asset["created_by"] == actor["id"] and not asset["generated"], "本单原附件字节/类别/来源不匹配")
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (asset["id"],))
    security = one(e, "file_security", asset["id"])
    require(len(scans) == 1 and scans[0]["state"] == security["state"] == "structure_only"
            and scans[0]["action"] == "initial" and scans[0]["actor_id"] == actor["id"]
            and scans[0]["sha256"] == asset["sha256"] and scans[0]["size"] == asset["size"]
            and body["security"]["can_use"], "原附件隔离结构扫描不完整")
    await expect(e.page.locator("#main .filerecord").filter(has_text=path.name)).to_have_count(1)
    return {"file": asset, "stored_blob": {"length": len(stored), "sha256": hashlib.sha256(stored).hexdigest()},
            "native": meta, "protection": guard.finish(), "event": events(e, guard, case_id, actor, "upload"),
            "clamav_acceptance": False}


async def choose_file(e, evidence, category):
    asset = evidence["file"]
    require(asset["category"] == category, "原财务附件类别未核准")
    control = e.page.locator('#modal [name="evidence_id"]')
    require(await control.count() == 1, "原财务凭据控件不唯一")
    labels = {"authorization": "客户授权", "evidence": "业务凭据", "receipt": "收退款凭据"}
    await live_choice(e, "evidence_id", asset["name"], asset["name"] + " · " + labels[category], expected_value=asset["id"])


def dependencies(e, checkpoint):
    require(e.manifest.get("synthetic_data_only") is True, "财务仅允许同轮新外部合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "财务DB不是同轮外部runtime")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "同轮源码镜像未冻结")
    for name in ("finance_business.py", "business_acceptance_catalog.json", "sales_business.py",
                 "sales_order_business.py", "vehicle_purchase_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(),
                "同轮财务脚本指纹变化：" + name)
    sale, purchase = fixed_dependency(e, checkpoint, SALES), fixed_dependency(e, checkpoint, PURCHASE)
    customer = one(e, "flow_customers", sale["report_sources"]["customer_id"])
    account = one(e, "flow_accounts", checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"])
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    for role in ("service", "manager", "finance"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=? AND role=?",
                (actor["id"], 1, role))) == 1, "缺当前随机本人门店岗位：" + role)
    require(fixture["store_id"] == customer["store_id"] == account["store_id"] == 1
            and customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"]
            and account["active"] and account["account_type"] == "bank", "同轮本店客户/账户来源失效")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=?", (1,)),
            "本批无经营主体策略验收，不绕过实际策略")
    checkpoint.report["mirror"] = {"source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    checkpoint.report["source_preconditions"] = {"customer_id": customer["id"], "account": account,
        "synthetic_declared_inputs": {"service_fees_cents": [6000, 6000], "erroneous_advance_cents": 10000,
            "correct_advance_cents": 9000, "apply_cents": 4000, "statement_batches_cents": [3000, 5000], "refund_cents": 5000}}
    checkpoint.save()
    return fixture, customer, account


async def create_income_item(e, context, credentials, fixture, token):
    manager = await login_as(e, context, credentials, fixture["manager_key"], "service-orders", 1)
    await expect(e.page.locator("#main h1")).to_have_text("代办与其它客户服务")
    await e.click('#main [data-act="serviceorder-master"][data-kind="income-items"]', "主管建立本轮真实其它服务项目")
    await expect(e.page.locator("#modal-title")).to_have_text("新增其它客户服务项目")
    name, code = "本次合成服务收费" + token, "FI" + token
    for field, value in (("code", code), ("name", name), ("unit", "次"), ("standard_fee", "60.00")):
        await e.fill(f'#modal [name="{field}"]', value, "填写本次明确收费项目 " + field)
    guard = Guard(e, "create_income_item", manager, expected={"service_income_items": 1, "service_requests": 1})
    body, request, _, meta = await submit(e, SERVICE + "/income-items", SERVICE, status=201)
    item = one(e, "service_income_items", body["id"])
    require(request == {"request_id": request["request_id"], "code": code, "name": name, "unit": "次", "standard_fee_cents": 6000}
            and item["code"] == code and item["name"] == name and item["unit"] == "次"
            and item["standard_fee_cents"] == 6000 and item["active"], "原服务收费项目未匹配真实输入")
    return item, {"item": item, "native": meta, "guard": guard.finish(),
                  "receipt": receipt(e, request, manager, body, service_action="master_income-items")}


async def service_command(e, case_id, action, actor, *, expected, values):
    before = service_facts(e, case_id)
    guard = Guard(e, "service_" + action, actor, expected={**SERVICE_COMMON, **expected},
                  update=mutable(e, {case_id}, service=True), cases={case_id})
    body, request, shown, meta = await submit(e, f"{SERVICE}/{case_id}/actions/{action}", f"{SERVICE}/{case_id}")
    require(request == {"request_id": request["request_id"], "version": before["case"]["version"], "values": values},
            "本次原服务提交内容/版本不匹配：" + action)
    after = service_facts(e, case_id)
    require(body["id"] == shown["id"] == case_id and body["version"] == shown["version"] == after["case"]["version"]
            and after["case"]["version"] > before["case"]["version"], "服务成功结果未匹配当前原单版本")
    for key in ("quotes", "lines", "approvals", "authorizations", "fulfillments", "tenders", "payments", "credits", "events"):
        require(after[key][:len(before[key])] == before[key], "服务旧原事实被覆盖：" + key)
    return after, shown, {"native": meta, "guard": guard.finish(),
        "event": events(e, guard, case_id, actor, "serviceorder_" + action),
        "receipt": receipt(e, request, actor, body, service_action=action), "submitted_values": values}


async def create_service_source(e, context, credentials, fixture, customer, item, token, label):
    service = await login_as(e, context, credentials, fixture["service_key"], "service-orders", 1)
    await expect(e.page.locator("#main h1")).to_have_text("代办与其它客户服务")
    await e.click('#main [data-act="serviceorder-new"]', "服务顾问建立本轮服务应收 " + label)
    await expect(e.page.locator("#modal-title")).to_have_text("建立客户服务")
    for field, value in (("subtype", "其它客户服务"), ("customer", f'{customer["id"]} · {customer["name"]}'),
                         ("source", "不关联销售"), ("vehicle", "不关联车辆"), ("blocking", "允许后续办理")):
        await select_value(e, f'#modal [name="{field}"]', value, "明确原服务关系 " + field)
    day = await e.page.locator('#modal [name="due_date"]').input_value()
    require(len(day) == 10, "当前原UI未提供真实业务日期")
    await e.fill('#modal [name="due_date"]', day, "明确当前页面办理日期")
    reason = "本次合成客户委托服务" + label + "；已明确60元服务费用与独立办结事实 " + token
    await e.fill('#modal [name="reason"]', reason, "填写本次明确客户服务申请")
    guard = Guard(e, "create_service_" + label, service,
                  expected={**SERVICE_COMMON, "flow_cases": 1, "flow_tasks": 1, "service_orders": 1},
                  customer=customer["id"], new_kind="other_income")
    body, request, shown, meta = await submit(e, SERVICE, SERVICE + "/", status=201)
    require(request == {"request_id": request["request_id"], "subtype": "other_income", "customer_id": customer["id"],
            "source_order_id": None, "source_version": None, "customer_vehicle_id": None,
            "delivery_blocking": False, "due_date": day, "reason": reason}, "本次服务错误关联原销售或车辆")
    case_id = body["id"]
    f = service_facts(e, case_id)
    require(shown["id"] == case_id and f["case"]["parent_id"] is None and f["case"]["due_date"] == day
            and f["order"]["subtype"] == "other_income" and f["order"]["vehicle_snapshot"] == {}
            and not f["quotes"] and not f["payments"], "新服务产生错误业务前序")
    trail = [{"native": meta, "guard": guard.finish(), "event": events(e, guard, case_id, service, "serviceorder_create"),
              "receipt": receipt(e, request, service, body, service_action="create")}]
    owners, proofs = [], []
    service, _, owner = await responsible(e, context, credentials, fixture, case_id, "serviceorder_quote", "service")
    owners.append(owner)
    await original_form(e, "serviceorder-action", "quote", "项目及报价版本")
    line = e.page.locator('#modal [data-service-line][data-line-key="line1"]')
    await expect(line).to_have_count(1)
    await select_value(e, '#modal [data-service-line][data-line-key="line1"] [name="source"]',
                       "fee:" + str(item["id"]), "只选择本轮新服务费项目")
    for field, value in (("quantity", "1.000"), ("price", "60.00"), ("due_date", day)):
        e.action("fill", "明确本次服务报价 " + field, value=value)
        await line.locator('[name="' + field + '"]').fill(value)
    await expect(e.page.locator('#modal [data-service-line] [name="source"]').nth(1)).to_have_value("")
    await expect(e.page.locator('#modal [data-service-line] [name="source"]').nth(2)).to_have_value("")
    await e.fill('#modal [name="discount"]', "0.00", "明确不折扣服务费")
    quote_reason = "明确本次服务" + label + "数量1次、单价60元、无代缴及折扣 " + token
    await e.fill('#modal [name="reason"]', quote_reason, "记录本次服务报价依据")
    values = {"lines": [{"line_key": "line1", "bucket": "fee", "income_item_id": item["id"],
                        "quantity_milli": 1000, "unit_price_cents": 6000, "due_date": day}],
              "discount_cents": 0, "reason": quote_reason}
    f, view, native = await service_command(e, case_id, "quote", service,
                        expected={"service_quotes": 1, "service_lines": 1, "flow_tasks": 1}, values=values)
    trail.append(native)
    quote, dbline = f["quotes"][0], f["lines"][0]
    require(len(f["quotes"]) == len(f["lines"]) == 1 and quote["fee_cents"] == 6000 and quote["pass_cents"] == 0
            and quote["discount_cents"] == 0 and quote["actor_id"] == service["id"]
            and all(dbline[k] == value for k, value in {
                "quote_id": quote["id"], "line_key": "line1", "bucket": "fee", "income_item_id": item["id"],
                "agency_project_id": None, "payee_id": None, "name": item["name"], "code": item["code"],
                "unit": "次", "quantity_milli": 1000, "unit_price_cents": 6000, "amount_cents": 6000,
                "discount_cents": 0, "due_date": day, "payee_snapshot": {}}.items()), "真实服务报价/项目来源不一致")
    digest_line = {k: dbline[k] for k in ("line_key", "bucket", "agency_project_id", "income_item_id", "payee_id",
        "code", "name", "unit", "payee_snapshot", "quantity_milli", "unit_price_cents", "discount_cents", "amount_cents", "due_date")}
    digest = hashlib.sha256(json.dumps({"operation": "service_quote", "payload": [digest_line]},
                                      sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(quote["digest"] == digest and view["quote"]["digest"] == digest, "本版原服务报价冻结摘要错误")
    manager, _, owner = await responsible(e, context, credentials, fixture, case_id, "serviceorder_approve", "manager")
    owners.append(owner)
    proof = await upload_original(e, case_id, manager, "authorization", label + "-price", token)
    proofs.append(proof)
    await original_form(e, "serviceorder-action", "approve", "独立批准当前价格")
    await e.fill('#modal [name="minimum"]', "60.00", "主管明确当前服务费最低额")
    await select_value(e, '#modal [name="allow"]', "不允许低于最低额", "明确不批准本版低价例外")
    reason = "独立核对本次服务" + label + "原项目数量与60元净收费"
    await e.fill('#modal [name="reason"]', reason, "主管独立核价依据")
    await choose_file(e, proof, "authorization")
    f, _, native = await service_command(e, case_id, "approve", manager, expected={"service_price_approvals": 1, "flow_tasks": 1},
        values={"minimum_fee_cents": 6000, "allow_below_minimum": False, "reason": reason, "evidence_id": proof["file"]["id"]})
    require(f["approvals"][0]["actor_id"] == manager["id"] != service["id"]
            and f["approvals"][0]["quote_id"] == quote["id"], "服务没有独立核价")
    trail.append(native)
    service, _, owner = await responsible(e, context, credentials, fixture, case_id, "serviceorder_authorize", "service")
    owners.append(owner)
    proof = await upload_original(e, case_id, service, "authorization", label + "-customer", token)
    proofs.append(proof)
    await original_form(e, "serviceorder-action", "authorize", "客户当前版授权")
    await choose_file(e, proof, "authorization")
    f, _, native = await service_command(e, case_id, "authorize", service,
        expected={"service_authorizations": 1, "flow_tasks": 2},
        values={"quote_id": quote["id"], "evidence_id": proof["file"]["id"]})
    require(f["authorizations"][0]["quote_id"] == quote["id"], "客户授权未绑定当前服务报价")
    trail.append(native)
    service, _, owner = await responsible(e, context, credentials, fixture, case_id, "serviceorder_handle", "service")
    owners.append(owner)
    proof = await upload_original(e, case_id, service, "authorization", label + "-fulfillment", token)
    proofs.append(proof)
    await original_form(e, "serviceorder-action", "fulfill", "确认本项实际办结")
    result = "本次合成客户服务" + label + "已独立实际办结并与客户交接 " + token
    await e.fill('#modal [name="result"]', result, "记录本次明确服务实际办结结果")
    await choose_file(e, proof, "authorization")
    f, view, native = await service_command(e, case_id, "fulfill", service, expected={"service_fulfillments": 1},
        values={"line_key": "line1", "result": result, "evidence_id": proof["file"]["id"]})
    trail.append(native)
    require(len(f["fulfillments"]) == 1 and f["fulfillments"][0]["line_id"] == dbline["id"]
            and f["fulfillments"][0]["amount_cents"] == 6000 and f["fulfillments"][0]["result"] == result
            and f["fulfillments"][0]["actor_id"] == service["id"] and not f["tenders"] and not f["payments"]
            and view["summary"]["customer_due_cents"] == 6000 and f["case"]["state"] == "working", "实际办结与未到账原事实错误")
    await expect(e.page.locator("#main")).to_contain_text("已实际办结")
    await expect(e.page.locator("#main")).to_contain_text("60.00")
    finance, _, owner = await responsible(e, context, credentials, fixture, case_id, "serviceorder_receive", "finance")
    owners.append(owner)
    require(open_task(e, case_id, "serviceorder_receive")["assignee_id"] == finance["id"], "原源单收款待办未交财务本人")
    return service_facts(e, case_id), {"label": label, "facts": f, "native": trail, "files": proofs, "task_owners": owners}


async def query_customer(e, context, credentials, fixture, customer, expected_due):
    path = FINANCE + "/sources"
    async with e.page.expect_response(lambda r: get_match(r, path)
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        actor = await login_as(e, context, credentials, fixture["finance_key"], "business-finance/" + str(customer["id"]), 1)
    response = await pending.value
    shown = await response.json()
    require(response.status == 200 and {r["case_id"]: r["due_cents"] for r in shown["items"]} == expected_due,
            "真实客户应收来源缺失、重复或夹杂旧原单")
    await expect(e.page.locator("#main h1")).to_have_text("业务财务结算")
    for row in shown["items"]:
        f = service_facts(e, row["case_id"])
        require(row["customer_id"] == customer["id"] and row["kind"] == "other_income"
                and row["version"] == f["case"]["version"] and row["amount_cents"] == 6000
                and row["number"] == f["case"]["number"]
                and row["credit_cents"] == sum(x["amount_cents"] for x in f["credits"])
                and row["due_cents"] == 6000 - sum(t["amount_cents"] for t in f["tenders"]), "应收API与原Service/Tender/信用不一致")
        displayed = e.page.locator("#main .panel").filter(has_text="可结算客户原单").locator("tbody tr").filter(has_text=row["number"])
        await expect(displayed).to_have_count(1)
        await expect(displayed).to_contain_text(fen_text(row["due_cents"]))
    before = e.business_snapshot("before_finance_customer_refresh")
    async with e.page.expect_response(lambda r: get_match(r, path)
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as fresh:
        e.action("refresh", "本人刷新同客户原应收并核对无写入")
        await e.page.reload()
    reread = await fresh.value
    repeated = await reread.json()
    require(reread.status == 200 and repeated == shown, "客户应收刷新改变原范围或金额")
    await expect(e.page.locator("#main h1")).to_have_text("业务财务结算")
    e.business_unchanged(before, "after_finance_customer_refresh")
    return actor, {"items": shown["items"], "refresh_same_items": True, "full_business_unchanged": True}


async def create_finance(e, context, credentials, fixture, customer, purpose, values, reason,
                         *, advance=None, targets=(), extra=None, role="service"):
    async with e.page.expect_response(lambda r: get_match(r, FINANCE + "/sources")) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], "business-finance/" + str(customer["id"]), 1)
    response = await pending.value
    require(response.status == 200, "财务申请前未读取当前原应收")
    await expect(e.page.locator("#main h1")).to_have_text("业务财务结算")
    title = {"advance": "客户预收款", "advance_apply": "预收抵用原单", "advance_refund": "未用预收退款",
             "statement": "客户期间月结", "stored_correction": "预收／会员原充值误记更正"}[purpose]
    await original_form(e, "business-finance-create", purpose, title, identifier=advance["id"] if advance and purpose != "stored_correction" else None)
    if "amount_cents" in values:
        await e.fill('#modal [name="amount"]', fen_text(values["amount_cents"]), "填写本次明确财务金额")
    if purpose == "advance_apply":
        target = next(x for x in targets if x["case"]["id"] == values["target_case_id"])
        await select_value(e, '#modal [name="source"]', f'{target["case"]["number"]} · 60.00元',
                           "明确抵用本轮服务A原单")
    if purpose == "statement":
        for key in ("starts_on", "ends_on"):
            await e.fill(f'#modal [name="{key}"]', values[key], "明确本次期间边界")
    if purpose == "stored_correction":
        cash = one(e, "cash_entries", values["original_cash_id"])
        label = f'{cash["business_date"]} · {cash["account"]} · {cash["voucher_no"]} · {fen_text(cash["amount_cents"])}元'
        await select_value(e, '#modal [name="original"]', label, "员工明确选已查明误记的本轮原预收")
        await e.fill('#modal [name="actual_business_date"]', values["actual_business_date"], "记录正确原到账日期")
        await live_choice(e, "account_id", extra["account"]["name"], extra["account"]["name"], expected_value=values["account_id"])
        await e.fill('#modal [name="reference"]', values["reference"], "明确正确重记原流水")
    await e.fill('#modal [name="reason"]', reason, "本人明确申请及原事实依据")
    expected = {**FINANCE_COMMON, "flow_cases": 1, "flow_tasks": 1, "business_finance_orders": 1}
    if purpose in ("advance_apply", "advance_refund"):
        expected["business_finance_applications"] = 1
    if purpose == "stored_correction":
        expected["business_finance_stored_correction_requests"] = 1
    if purpose == "statement":
        expected.update(business_finance_statements=1, business_finance_statement_lines=2)
    update = {"flow_cases": {values["target_case_id"]: VERSION}} if purpose == "advance_apply" else {}
    guard = Guard(e, "create_finance_" + purpose, actor, expected=expected, update=update,
                  cases={x["case"]["id"] for x in targets}, customer=customer["id"], new_kind="business_finance")
    body, request, shown, meta = await submit(e, FINANCE + "/orders", FINANCE + "/orders/", status=201)
    require(request == {"request_id": request["request_id"], "customer_id": customer["id"], "purpose": purpose,
                        "values": values, "reason": reason}, "财务原申请未匹配明确输入/CAS：" + purpose)
    case_id = body["case"]["id"]
    f = finance_facts(e, case_id)
    require(shown["case"]["id"] == case_id and f["order"]["purpose"] == purpose and f["order"]["status"] == "draft"
            and f["order"]["requested_by"] == actor["id"] and not f["batches"], "财务申请错误生效/产生资金")
    finance_view(e, body, f)
    finance_view(e, shown, f)
    return f, {"native": meta, "guard": guard.finish(),
        "event": events(e, guard, case_id, actor, "business_finance_create", finance=True),
        "receipt": receipt(e, request, actor, body, finance_action="create"), "submitted_values": values}


async def finance_command(e, context, credentials, fixture, case_id, action, role, customer, token,
                          *, expected, update_extra=None, sources=(), amounts=None, account=None, reference=None):
    key = "business_finance_review" if action == "approve" else "business_finance_execute"
    actor, view, owner = await responsible(e, context, credentials, fixture, case_id, key, role, financial=True)
    f = finance_facts(e, case_id)
    require(action != "approve" or actor["id"] != f["order"]["requested_by"], "财务自批禁止")
    category = "evidence" if action == "approve" else "receipt"
    proof = await upload_original(e, case_id, actor, category, f["order"]["purpose"] + "-" + action + "-" + token, token, financial=True)
    title = {"approve": "独立复核批准", "execute": "确认批准内容及实际办理", "collect": "登记真实到账并分配"}[action]
    source_versions = {str(sid): one(e, "flow_cases", sid)["version"] for sid in sources}
    await original_form(e, "business-finance-action", action, title)
    await choose_file(e, proof, category)
    reason = "本人核对本次原单、批准额度及独立实际事实 " + token
    await e.fill('#modal [name="reason"]', reason, "明确本人原批准/收退款依据")
    values = {"reason": reason, "evidence_id": proof["file"]["id"], "source_versions": source_versions}
    if account:
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        await e.fill('#modal [name="reference"]', reference, "记录本次实际收退款独立流水")
        values.update(account_id=account["id"], reference=reference)
    if amounts is not None:
        for sid, amount in amounts.items():
            await e.fill(f'#modal [name="allocation_{sid}"]', fen_text(amount), "明确本次到账逐原单分配")
        values.update(amount_cents=sum(amounts.values()),
                      allocations=[{"source_case_id": l["source_case_id"], "amount_cents": amounts[l["source_case_id"]]}
                                   for l in f["lines"] if amounts.get(l["source_case_id"], 0) > 0])
    all_cases = {case_id, *sources}
    update = mutable(e, all_cases, order=f["order"]["id"], account=account["id"] if account else None)
    for table, selected in (update_extra or {}).items():
        update.setdefault(table, {}).update(selected)
    guard = Guard(e, "finance_" + f["order"]["purpose"] + "_" + action, actor,
                  expected={**FINANCE_COMMON, **expected}, update=update, cases=all_cases, customer=customer["id"])
    body, request, shown, meta = await submit(e, f"{FINANCE}/orders/{case_id}/actions/{action}", f"{FINANCE}/orders/{case_id}")
    require(request == {"request_id": request["request_id"], "version": f["order"]["version"],
                        "case_version": f["case"]["version"], "values": values}, "财务原动作没有当前完整CAS/来源版本或明确输入")
    after = finance_facts(e, case_id)
    require(body["case"]["id"] == shown["case"]["id"] == case_id
            and body["case"]["version"] == shown["case"]["version"] == after["case"]["version"]
            and after["case"]["version"] > f["case"]["version"]
            and body["order"]["version"] == shown["order"]["version"] == after["order"]["version"], "财务原响应与实际DB版本不符")
    require(after["order"]["values"] == f["order"]["values"]
            and after["events"][:len(f["events"])] == f["events"]
            and after["finance_events"][:len(f["finance_events"])] == f["finance_events"]
            and after["lines"] == f["lines"] and after["allocations"][:len(f["allocations"])] == f["allocations"]
            and after["batches"][:len(f["batches"])] == f["batches"], "财务覆盖原冻结申请/行/资金/事件")
    finance_view(e, body, after)
    finance_view(e, shown, after)
    return after, shown, {"native": meta, "guard": guard.finish(),
        "event": events(e, guard, case_id, actor, "business_finance_" + action, finance=True),
        "receipt": receipt(e, request, actor, body, finance_action=str(case_id) + ":" + action),
        "submitted_values": values, "file": proof, "task_owner": owner}


async def reject_excess_refund(e, context, credentials, fixture, customer, advance):
    async with e.page.expect_response(lambda r: get_match(r, FINANCE + "/advances")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        await login_as(e, context, credentials, fixture["service_key"], "business-finance/" + str(customer["id"]), 1)
    read = await pending.value
    view = await read.json()
    found = [r for r in view["items"] if r["id"] == advance["id"]]
    require(read.status == 200 and len(found) == 1 and found[0]["available_cents"] == 5000
            and found[0]["version"] == advance["version"], "退款拒绝前未核本原款当前可用50元")
    await expect(e.page.locator("#main h1")).to_have_text("业务财务结算")
    await original_form(e, "business-finance-create", "advance_refund", "未用预收退款", identifier=advance["id"])
    await e.fill('#modal [name="amount"]', "60.00", "明确探测超过已核原预收可用50元的申请")
    await e.fill('#modal [name="reason"]', "本次明确拒绝边界：原款仅余50元，申请60元必须被拒绝", "记录已知退款上限边界")
    return await rejected_submit(e, FINANCE + "/orders", 409, "超过本客户这笔原预收的未用余额")


def wallet(e, advance_id, balance, reserved, correction):
    row = one(e, "business_finance_advances", advance_id)
    require(row["initial_cents"] == 10000 and row["balance_cents"] == balance
            and row["reserved_cents"] == reserved and row["correction_cents"] == correction,
            "原预收本金/余额/占额/更正累计不匹配")
    return row


def cash_fact(e, key, amount, direction, category, account, actor_id, *, reference=None, day=None):
    row = one(e, "cash_entries", key)
    require(row["amount_cents"] == amount and row["direction"] == direction and row["category"] == category
            and row["account"] == account["name"] and row["created_by"] == actor_id and row["store_id"] == 1
            and row["approval_state"] == "approved" and (reference is None or row["voucher_no"] == reference)
            and (day is None or row["business_date"] == day), "原实际Cash账户/金额/方向/来源不匹配")
    return row


async def finance_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        fixture, customer, account = dependencies(e, checkpoint)
        token = uuid.uuid4().hex[:12]
        checkpoint.start("HK-091")
        _, initial = await query_customer(e, context, credentials, fixture, customer, {})
        checkpoint.note({"initial_empty_is_only_precondition_not_acceptance": initial})
        item, item_evidence = await create_income_item(e, context, credentials, fixture, token)
        a, a_evidence = await create_service_source(e, context, credentials, fixture, customer, item, token, "A")
        b, b_evidence = await create_service_source(e, context, credentials, fixture, customer, item, token, "B")
        aid, bid = a["case"]["id"], b["case"]["id"]
        _, nonempty = await query_customer(e, context, credentials, fixture, customer, {aid: 6000, bid: 6000})
        checkpoint.note({"new_project": item_evidence, "same_run_nonempty_sources": [a_evidence, b_evidence], "positive_query": nonempty})

        checkpoint.start("HK-087")
        advance_order, create = await create_finance(e, context, credentials, fixture, customer, "advance",
            {"amount_cents": 10000}, "本次合成正确原到账90元被明确误录为100元；后续按查明依据追加原更正 " + token)
        advance_case = advance_order["case"]["id"]
        posted, view, posting = await finance_command(e, context, credentials, fixture, advance_case, "execute", "finance", customer, token,
            expected={"cash_entries": 1, "business_finance_advances": 1, "business_finance_advance_entries": 1},
            account=account, reference="ADV-" + token)
        require(len(posted["advances"]) == len(posted["entries"]) == 1 and posted["case"]["state"] == posted["order"]["status"] == "completed"
                and not any(t["status"] == "open" for t in posted["tasks"]), "原预收未唯一登记及办结")
        advance, original_entry = posted["advances"][0], posted["entries"][0]
        advance_id = advance["id"]
        original_cash = cash_fact(e, advance["cash_id"], 10000, "in", "business_finance_advance", account,
            e.manifest["users"][fixture["finance_key"]]["id"], reference="ADV-" + token, day=posted["case"]["business_date"])
        wallet(e, advance_id, 10000, 0, 0)
        require(original_entry["advance_id"] == advance_id and original_entry["purpose"] == "receive"
                and original_entry["cash_id"] == original_cash["id"] and original_entry["amount_cents"] == 10000
                and original_entry["original_id"] is None and original_entry["evidence_id"] == posting["file"]["file"]["id"],
                "预收原Entry与实际Cash/本次凭据未关联")
        checkpoint.note({"created": create, "posted": posting, "advance": advance, "original_entry": original_entry, "cash": original_cash})

        checkpoint.start("HK-090")
        correct_values = {"original_cash_id": original_cash["id"], "amount_cents": 9000,
                          "source_version": advance["version"], "account_id": account["id"], "reference": "COR-" + token,
                          "actual_business_date": original_cash["business_date"]}
        correction, create_correction = await create_finance(e, context, credentials, fixture, customer, "stored_correction",
            correct_values, "已查明本次合成预收正确到账90元，原100元为明确录入错误；冲正重记不是客户退款 " + token,
            role="finance", extra={"account": account})
        correction_case = correction["case"]["id"]
        request = correction["stored_requests"][0]
        require(len(correction["stored_requests"]) == 1 and request["source_kind"] == "advance"
                and request["advance_id"] == advance_id and request["member_id"] is request["topup_id"] is None
                and request["original_cash_id"] == original_cash["id"] and request["original_amount_cents"] == 10000
                and request["corrected_amount_cents"] == 9000 and request["reserved_cents"] == 1000
                and request["status"] == "requested", "更正未冻结精确普通预收来源")
        wallet(e, advance_id, 10000, 0, 0)
        correction, _, approved = await finance_command(e, context, credentials, fixture, correction_case, "approve", "manager", customer, token,
            expected={"flow_tasks": 1}, update_extra=mutable(e, advance=advance_id, stored=request["id"]))
        wallet(e, advance_id, 10000, 1000, 0)
        require(correction["stored_requests"][0]["status"] == "reserved", "更正批准未占原预收差额")
        correction, corrected_view, executed = await finance_command(e, context, credentials, fixture, correction_case, "execute", "finance", customer, token,
            expected={"cash_entries": 2, "business_finance_advance_entries": 1, "business_finance_stored_corrections": 1},
            update_extra=mutable(e, advance=advance_id, stored=request["id"], account=account["id"]))
        require(len(correction["stored_facts"]) == 1 and correction["stored_requests"][0]["status"] == "applied"
                and correction["case"]["state"] == correction["order"]["status"] == "completed", "预收更正未唯一生效")
        fact = correction["stored_facts"][0]
        correcting_entry = one(e, "business_finance_advance_entries", fact["advance_entry_id"])
        corrected = cash_fact(e, fact["corrected_cash_id"], 9000, "in", "business_finance_stored_corrected",
            account, e.manifest["users"][fixture["finance_key"]]["id"], reference="COR-" + token, day=original_cash["business_date"])
        contra = cash_fact(e, fact["reversing_cash_id"], 10000, "out", "business_finance_stored_reverse",
            account, e.manifest["users"][fixture["finance_key"]]["id"])
        require(fact["original_cash_id"] == original_cash["id"] and fact["request_id"] == request["id"] and fact["group_entry_id"] is None
                and correcting_entry["purpose"] == "correction" and correcting_entry["amount_cents"] == -1000
                and correcting_entry["original_id"] == original_entry["id"] and correcting_entry["cash_id"] is None
                and correcting_entry["evidence_id"] == fact["evidence_id"] == executed["file"]["file"]["id"]
                and one(e, "cash_entries", original_cash["id"]) == original_cash
                and one(e, "business_finance_advance_entries", original_entry["id"]) == original_entry, "原款误记更正覆盖旧款或混成退款/集团本金")
        corrected_wallet = wallet(e, advance_id, 9000, 0, -1000)
        await expect(e.page.locator("#main")).to_contain_text("批准后正确重记")
        await expect(e.page.locator("#main")).to_contain_text("COR-" + token)
        await expect(e.page.locator("#main")).to_contain_text("90.00")
        await checkpoint.passed({"created": create_correction, "approved": approved, "executed": executed,
            "stored_request": correction["stored_requests"][0], "stored_correction": fact, "contra_cash": contra,
            "correct_cash": corrected, "advance_entry": correcting_entry, "wallet": corrected_wallet,
            "old_cash_and_entry_unchanged": True, "member_and_inventory_tables_unchanged_each_guard": True})

        checkpoint.start("HK-087")
        a = service_facts(e, aid)
        apply_values = {"amount_cents": 4000, "advance_id": advance_id, "advance_version": corrected_wallet["version"],
                        "target_case_id": aid, "target_version": a["case"]["version"]}
        apply, apply_create = await create_finance(e, context, credentials, fixture, customer, "advance_apply", apply_values,
            "客户明确以本笔普通预收抵用本次服务A40元，现金不重复登记 " + token, advance=corrected_wallet, targets=(a,))
        apply_case, application = apply["case"]["id"], apply["applications"][0]
        require(application["kind"] == "apply" and application["status"] == "requested"
                and application["amount_cents"] == 4000 and application["target_case_id"] == aid, "抵用申请错误来源")
        wallet(e, advance_id, 9000, 0, -1000)
        apply, _, apply_approve = await finance_command(e, context, credentials, fixture, apply_case, "approve", "manager", customer, token,
            expected={"flow_tasks": 1}, update_extra=mutable(e, advance=advance_id, application=application["id"]), sources=(aid,))
        wallet(e, advance_id, 9000, 4000, -1000)
        apply, _, apply_execute = await finance_command(e, context, credentials, fixture, apply_case, "execute", "finance", customer, token,
            expected={"business_finance_advance_entries": 1, "business_finance_credit_links": 1, "service_tender_slices": 1},
            update_extra=mutable(e, advance=advance_id, application=application["id"]), sources=(aid,))
        apply_entry = apply["entries"][0]
        credit = next(r for r in related(e, "business_finance_credit_links", "case_id", aid) if r["entry_id"] == apply_entry["id"])
        a = service_facts(e, aid)
        require(apply["case"]["state"] == apply["order"]["status"] == "completed"
                and apply["applications"][0]["status"] == "applied" and apply_entry["amount_cents"] == -4000
                and apply_entry["purpose"] == "apply" and apply_entry["cash_id"] is None
                and apply_entry["original_id"] == original_entry["id"] and credit["application_id"] == application["id"]
                and credit["amount_cents"] == 4000 and credit["case_id"] == aid and credit["original_id"] is None
                and len(a["tenders"]) == 1 and a["tenders"][0]["credit_link_id"] == credit["id"]
                and a["tenders"][0]["payment_link_id"] is None and a["tenders"][0]["amount_cents"] == 4000
                and not a["payments"], "抵用未独立生成真实Credit/Tender或重复记Cash")
        available = wallet(e, advance_id, 5000, 0, -1000)
        _, after_apply = await query_customer(e, context, credentials, fixture, customer, {aid: 2000, bid: 6000})
        await checkpoint.passed({"original_advance": {"advance_id": advance_id, "cash": original_cash, "entry": original_entry},
            "create": create, "actual_post": posting, "apply_create": apply_create, "apply_approve": apply_approve,
            "apply_execute": apply_execute, "credit_link": credit, "apply_entry": apply_entry, "wallet": available,
            "after_apply_customer_due": after_apply, "apply_produces_no_cash": True})

        checkpoint.start("HK-096")
        dates = [one(e, "flow_cases", sid)["business_date"] for sid in (aid, bid)]
        period = {"starts_on": min(dates), "ends_on": max(dates)}
        statement, statement_create = await create_finance(e, context, credentials, fixture, customer, "statement", period,
            "客户明确本次两服务原单8000分期间月结，到账另分两笔逐单确认 " + token, role="finance", targets=(a, b))
        statement_case = statement["case"]["id"]
        statement_record = statement["statements"][0]
        lines = statement["lines"]
        require(len(statement["statements"]) == 1 and len(lines) == 2 and statement["case"]["amount_cents"] == 8000
                and statement_record["revision"] == 1 and statement_record["previous_id"] is None
                and {l["source_case_id"]: l["due_cents"] for l in lines} == {aid: 2000, bid: 6000}, "月结未冻结本次两原应收")
        frozen_sources = [l["snapshot"] for l in lines]
        digest = hashlib.sha256(json.dumps(frozen_sources, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        require(statement_record["digest"] == digest and all(l["snapshot"]["version"] == one(e, "flow_cases", l["source_case_id"])["version"]
                for l in lines), "月结摘要与当前源版本冻结错误")
        for line in lines:
            shown_row = e.page.locator("#main .panel").filter(has_text="冻结逐单客户余额").locator("tbody tr").filter(has_text=line["snapshot"]["number"])
            await expect(shown_row).to_have_count(1)
            await expect(shown_row).to_contain_text(fen_text(line["due_cents"]))
        statement, _, statement_approve = await finance_command(e, context, credentials, fixture, statement_case, "approve", "manager", customer, token,
            expected={"flow_tasks": 1})
        require(statement["order"]["status"] == "approved" and statement["lines"] == lines and not statement["batches"], "月结批准错误记现金或改冻结行")
        collections, batch_cash, payment_ids = [], [], []
        for ordinal, allocations in enumerate(({aid: 1000, bid: 2000}, {aid: 1000, bid: 4000}), 1):
            statement, _, native = await finance_command(e, context, credentials, fixture, statement_case, "collect", "finance", customer, token + str(ordinal),
                expected={"cash_entries": 1, "business_finance_cash_batches": 1, "business_finance_cash_allocations": 2,
                          "flow_payment_links": 2, "service_tender_slices": 2},
                sources=(aid, bid), amounts=allocations, account=account, reference="ST" + str(ordinal) + "-" + token)
            batch = statement["batches"][-1]
            selected = [r for r in statement["allocations"] if r["batch_id"] == batch["id"]]
            money = sum(allocations.values())
            actual_cash = cash_fact(e, batch["cash_id"], money, "in", "business_finance_collection",
                account, e.manifest["users"][fixture["finance_key"]]["id"], reference="ST" + str(ordinal) + "-" + token,
                day=statement["case"]["business_date"])
            require(batch["amount_cents"] == money and batch["kind"] == "collection"
                    and batch["evidence_id"] == native["file"]["file"]["id"]
                    and {r["case_id"]: r["amount_cents"] for r in selected} == allocations, "月结一Cash批次与逐原单分配不一致")
            for allocation in selected:
                link = one(e, "flow_payment_links", allocation["payment_link_id"])
                source = service_facts(e, allocation["case_id"])
                matching = [r for r in source["tenders"] if r["payment_link_id"] == link["id"]]
                source_line = next(l for l in lines if l["source_case_id"] == source["case"]["id"])
                require(allocation["statement_line_id"] == source_line["id"] and link["case_id"] == source["case"]["id"]
                        and link["amount_cents"] == allocation["amount_cents"] and link["direction"] == "in"
                        and link["original_id"] is None and link["cash_id"] == actual_cash["id"]
                        and link["account_id"] == account["id"] and link["reference"] == actual_cash["voucher_no"]
                        and link["business_date"] == actual_cash["business_date"] and len(matching) == 1
                        and matching[0]["amount_cents"] == link["amount_cents"] and matching[0]["credit_link_id"] is None
                        and matching[0]["evidence_id"] == native["file"]["file"]["id"], "月结实际PaymentLink/ServiceTender未引用同批本原款")
                payment_ids.append(link["id"])
            batch_cash.append(actual_cash)
            collections.append({"native": native, "batch": batch, "cash": actual_cash, "allocations": selected})
            require(statement["lines"] == lines and wallet(e, advance_id, 5000, 0, -1000), "月结覆盖旧行或重复消费预收")
            if ordinal == 1:
                require(statement["order"]["status"] == "approved" and statement["case"]["state"] == "pending",
                        "分笔首款未收足却提前完成月结")
                _, partial = await query_customer(e, context, credentials, fixture, customer, {aid: 1000, bid: 4000})
                checkpoint.note({"first_batch": collections[-1], "remaining_source_query": partial})
        a, b = service_facts(e, aid), service_facts(e, bid)
        require(statement["case"]["state"] == statement["order"]["status"] == "completed"
                and len(statement["batches"]) == 2 and len(statement["allocations"]) == 4
                and sum(x["amount_cents"] for x in statement["allocations"]) == 8000
                and all(f["case"]["state"] == "completed" and all(t["status"] != "open" for t in f["tasks"])
                        and sum(x["amount_cents"] for x in f["tenders"]) == 6000 for f in (a, b)), "月结或两原服务未按实际资金完成")
        await checkpoint.passed({"created": statement_create, "approved": statement_approve,
            "statement": statement_record, "frozen_lines": lines, "actual_collections": collections,
            "two_source_final": [a, b], "partial_first_batch_not_completed": True})

        checkpoint.start("HK-091")
        _, final_query = await query_customer(e, context, credentials, fixture, customer, {})
        await checkpoint.passed({"initial_nonempty_query": nonempty, "after_apply": after_apply,
            "final_zero_due_after_real_collections": final_query, "source_ids": [aid, bid],
            "original_service_tenders": [a["tenders"], b["tenders"]], "all_explicit_refreshes_full_business_unchanged": True})

        checkpoint.start("HK-093")
        current_wallet = wallet(e, advance_id, 5000, 0, -1000)
        refused = await reject_excess_refund(e, context, credentials, fixture, customer, current_wallet)
        checkpoint.note({"actual_excess_refund_409": refused})
        refund, refund_create = await create_finance(e, context, credentials, fixture, customer, "advance_refund",
            {"amount_cents": 5000, "advance_id": advance_id, "advance_version": current_wallet["version"]},
            "客户明确实际退回本笔未用预收50元；已抵用与真实月结保持原事实 " + token, advance=current_wallet)
        refund_case, refund_application = refund["case"]["id"], refund["applications"][0]
        require(refund_application["kind"] == "refund" and refund_application["status"] == "requested"
                and refund_application["target_case_id"] is None and refund_application["advance_id"] == advance_id, "退款错误申请非原预收")
        refund, _, refund_approve = await finance_command(e, context, credentials, fixture, refund_case, "approve", "manager", customer, token,
            expected={"flow_tasks": 1}, update_extra=mutable(e, advance=advance_id, application=refund_application["id"]))
        wallet(e, advance_id, 5000, 5000, -1000)
        refund, _, refund_execute = await finance_command(e, context, credentials, fixture, refund_case, "execute", "finance", customer, token,
            expected={"cash_entries": 1, "business_finance_advance_entries": 1},
            update_extra=mutable(e, advance=advance_id, application=refund_application["id"]),
            account=account, reference="REF-" + token)
        require(len(refund["entries"]) == 1 and refund["applications"][0]["status"] == "applied"
                and refund["case"]["state"] == refund["order"]["status"] == "completed", "退款未唯一执行及完成")
        refund_entry = refund["entries"][0]
        refund_cash = cash_fact(e, refund_entry["cash_id"], 5000, "out", "business_finance_advance_refund", account,
            e.manifest["users"][fixture["finance_key"]]["id"], reference="REF-" + token, day=refund["case"]["business_date"])
        require(refund_entry["advance_id"] == advance_id and refund_entry["purpose"] == "refund"
                and refund_entry["amount_cents"] == -5000 and refund_entry["original_id"] == original_entry["id"]
                and refund_entry["evidence_id"] == refund_execute["file"]["file"]["id"], "实际退款不引用原预收Entry/凭据")
        closed_wallet = wallet(e, advance_id, 0, 0, -1000)
        ledger = related(e, "business_finance_advance_entries", "advance_id", advance_id)
        require([(r["purpose"], r["amount_cents"]) for r in ledger] ==
                [("receive", 10000), ("correction", -1000), ("apply", -4000), ("refund", -5000)]
                and sum(r["amount_cents"] for r in ledger) == 0, "原预收分项账本不守恒")
        all_cash = [original_cash, contra, corrected, *batch_cash, refund_cash]
        require(len({c["id"] for c in all_cash}) == 6 and sum(c["amount_cents"] * (1 if c["direction"] == "in" else -1)
                for c in all_cash) == 12000 and 4000 + sum(c["amount_cents"] for c in batch_cash) == 12000
                and one(e, "cash_entries", original_cash["id"]) == original_cash
                and service_facts(e, aid) == a and service_facts(e, bid) == b, "更正/抵用/两现金批次/退款混账或覆盖原服务")
        await checkpoint.passed({"created": refund_create, "approved": refund_approve, "executed": refund_execute,
            "application": refund["applications"][0], "refund_entry": refund_entry, "cash": refund_cash,
            "wallet": closed_wallet, "ledger": ledger, "separate_cash": all_cash, "net_cash_cents": 12000,
            "actual_excess_refund_409_and_explicit_discard": refused, "member_and_inventory_unchanged_each_guard": True})
        checkpoint.finish({"customer_id": customer["id"], "account_id": account["id"], "income_item_id": item["id"],
            "service_case_ids": [aid, bid], "quote_ids": [a["quotes"][0]["id"], b["quotes"][0]["id"]],
            "advance_case_id": advance_case, "advance_id": advance_id, "original_advance_cash_id": original_cash["id"],
            "stored_correction_case_id": correction_case, "stored_correction_id": fact["id"], "corrected_cash_id": corrected["id"],
            "apply_case_id": apply_case, "credit_link_id": credit["id"], "statement_case_id": statement_case,
            "statement_id": statement_record["id"], "collection_batch_ids": [c["batch"]["id"] for c in collections],
            "payment_link_ids": payment_ids, "refund_case_id": refund_case, "refund_cash_id": refund_cash["id"]})
    except Exception as error:
        checkpoint.failed(error)
        raise


FINANCE_SCENARIOS = ((SCENARIO, finance_business, 600),)
