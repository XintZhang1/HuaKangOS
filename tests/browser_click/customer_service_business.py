"""Original customer inputs and three separate, actually handled care cases.

Only visible original forms write business data. Evidence supplies the isolated
browser, credentials and SELECT-only database. HK099 is a local source partial,
never an acceptance check; cross-store history/files remain independently due.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import login_as, require
from vehicle_purchase_business import checkbox, nav, select_value

SCENARIO = "customer-service-hk098-107-108-109"
CARE_API = "/api/customer-service"
CUSTOMERS_API = "/api/flow/master/customers"
FIXTURE_ZONE = ZoneInfo("Asia/Shanghai")  # fixture_server explicitly sets APP_TIMEZONE.
REQUIREMENTS = (
    ("HK-098", "客户档案", ("原客户搜索、新建、补电话和说明、编辑重读", "同号明确另建且不覆盖原档案", "撤回联系、本人恢复403及主管明确恢复")),
    ("HK-107", "客户咨询", ("独立咨询原单及本人接手", "两次实际答复分别追加原记录和事件", "原结案、负责人及唯一任务与数据库一致")),
    ("HK-108", "客户投诉", ("独立投诉原单及本人接手", "两次实际处理分别追加原记录和事件", "原结案结果和依据可追溯")),
    ("HK-109", "客户救援", ("独立救援原单、明确客户位置及本人接手", "两次实际协调结果分别追加原记录和事件", "原结案不冒称车辆维修或真实外部派车")),
)
PRIMARY_KEYS = {
    "flow_cases": "id", "flow_tasks": "id", "flow_events": "id",
    "flow_customers": "id", "audit_logs": "id",
    "care_customer_vehicles": "id", "care_vehicle_observations": "id",
    "care_cases": "case_id", "care_records": "id", "care_receipts": "id",
    "care_history_links": "id", "group_identities": "id",
    "group_identity_links": "id", "group_events": "id",
    "business_entity_case_contexts": "case_id", "business_entity_store_controls": "id",
    "escalation_refusals": "id",
}


def business_today():
    return datetime.now(FIXTURE_ZONE).date()


class Checkpoint:
    """The same external per-check evidence contract as the existing candidates."""
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        contents = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        catalogue = {row["id"]: row for row in json.loads(contents)["requirements"]}
        rows = []
        for key, title, criteria in REQUIREMENTS:
            source = catalogue.get(key)
            require(source is not None and source["title"] == title
                    and source["source_review_status"] == "source_reviewed", key + " 原源合同未核准")
            require(any(c["check_id"] == key + "-business" for c in source["acceptance_checks"]),
                    key + " 源check_id不匹配")
            rows.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                         "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                            "status": "not_tested", "criteria": list(criteria), "evidence": {}}],
                         "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}})
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in REQUIREMENTS],
            "complete": False, "passed": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": hashlib.sha256(contents).hexdigest(), "requirements": rows,
            "partial_requirements": [{"id": "HK-099", "title": "车辆档案", "status": "not_tested",
                "local_scope_status": "not_tested", "business_accepted": False,
                "acceptance_check_submitted": False, "evidence": {},
                "unexecuted_scope": ["明确跨店集团身份及摘要授权", "来源店独立复核的原单与逐件文件授权",
                                     "到期及撤销后的读取范围", "有据原观察纠正和独立复核"]}],
            "conditions": {"synthetic_customer_and_service_inputs": True,
                           "external_contact_dispatch_repair_or_payment_acceptance": False,
                           "production_business_acceptance": False},
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    async def passed(self, evidence):
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        self.save()
        self.active = None

    def local_source(self, evidence, *, complete=False):
        partial = self.report["partial_requirements"][0]
        partial.update(status="partial", local_scope_status="local_scope_passed" if complete else "partial",
                       evidence=evidence)
        self.save()

    def failed(self, error):
        if self.active:
            self.active.update(status="failed", evidence_action_end=len(self.e.actions))
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        else:
            self.report["failed_source_precondition"] = "HK-099-local"
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "四项原业务链未完整执行")
        require(self.report["partial_requirements"][0]["local_scope_status"] == "local_scope_passed",
                "本店客户车辆与真实服务摘要前置未完成")
        self.report.update(complete=True, passed=True, executed_requirements=4,
                           passed_requirements=4, human_acceptance="pending")
        self.save()
        self.e.observe("customer_service_business_checkpoint", {"path": str(self.path), "requirements": 4,
                       "passed": 4, "hk099": "partial/local_scope_passed", "business_accepted": False})


def one(e, table, key, *, primary="id"):
    rows = e.db.rows(f"SELECT * FROM {table} WHERE {primary}=?", (key,))
    require(len(rows) == 1, "原记录不存在或不唯一：" + table)
    return rows[0]


def before_write(e, *, updates=None, appends=()):
    updates = updates or {}
    allowed = set(updates) | set(appends)
    snapshot = e.business_snapshot("before_original_customer_form")
    old = {table: e.db.rows(f"SELECT * FROM {table} ORDER BY {PRIMARY_KEYS[table]}") for table in allowed}
    return snapshot, old, {table: set(keys) for table, keys in updates.items()}, allowed


def after_write(e, protection):
    before, old, updates, allowed = protection
    after = e.business_snapshot("after_original_customer_form")
    changed = [name for name in before["tables"].keys() | after["tables"].keys()
               if name not in allowed and before["tables"].get(name) != after["tables"].get(name)]
    require(not changed, "客户办理改动了无关原事实：" + "、".join(sorted(changed)))
    for table, rows in old.items():
        pk = PRIMARY_KEYS[table]
        current = {r[pk]: r for r in e.db.rows(f"SELECT * FROM {table} ORDER BY {pk}")}
        for row in rows:
            require(row[pk] in current, "客户办理删除了原行：" + table)
            if row[pk] not in updates.get(table, set()):
                require(current[row[pk]] == row, "客户办理覆盖了无关或不可改原行：" + table)
    return {"unrelated_tables_unchanged": True, "protected_old_rows_unchanged": True,
            "stock_and_cash_unchanged": True}


async def restore_contact_refusal(e, user, store_id, customer):
    path = CUSTOMERS_API + "/" + str(customer["id"])
    message = "重新启用联系需要主管核对客户意愿"
    protection = before_write(e, appends={"escalation_refusals"})
    old_ids = {r["id"] for r in protection[1]["escalation_refusals"]}
    async with e.page.expect_response(lambda r: r.request.method == "PUT" and urlsplit(r.url).path == path) as pending:
        await e.click('#modal form button[type="submit"]', "本人明确尝试恢复联系并核对原拒绝")
    response = await pending.value
    body = await response.json()
    require(response.status == 403 and body.get("detail") == message, "联系恢复原拒绝不匹配")
    refusal = body.get("refusal", {})
    require(refusal.get("category") == "rule" and refusal.get("can_escalate") is False,
            "原业务规则拒绝被改写为可评审权限拒绝")
    headers = await response.request.all_headers()
    request = response.request.post_data_json
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token"))
            and headers.get("x-store-id") == str(store_id)
            and request["version"] == customer["version"]
            and request["values"]["contact_allowed"] is True, "拒绝探针不是当前本人原表单")
    protection_result = after_write(e, protection)
    new_rows = [r for r in e.db.rows("SELECT * FROM escalation_refusals ORDER BY id") if r["id"] not in old_ids]
    require(len(new_rows) == 1, "一次原拒绝未精确新增一条服务器记录")
    row = new_rows[0]
    require(row["id"] == refusal.get("id") and row["store_id"] == store_id and row["user_id"] == user["id"]
            and row["role"] == "service" and row["method"] == "PUT" and row["path"] == path
            and row["status_code"] == 403 and row["message"] == message and row["category"] == "rule"
            and row["source"] == "page" and row["created_at"]
            and row["consumed_at"] is None and row["consumed_by_id"] is None,
            "服务器拒绝记录串人/串店/串操作或已被消费")
    await expect(e.page.locator("#modal .formerror")).to_contain_text(message)
    await e.snapshot("protected-contact-restore-refusal")
    after_refusal = e.business_snapshot("after_exact_contact_refusal")
    await expect(e.page.locator("#modal form")).not_to_have_attribute("aria-busy", "true")
    await e.click('#modal .modalhead [data-act="close"]', "关闭被拒绝的联系恢复表单")
    await expect(e.page.locator("#modal .wfx-discard")).to_be_visible()
    await e.click('#modal [data-wfx-discard]', "明确放弃被拒绝的填写")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(after_refusal, "after_contact_refusal_discard")
    evidence = {"path": path, "method": "PUT", "status": 403, "detail": message,
                "refusal": row, "can_escalate": False, "native_ui": True,
                "exact_refusal_append_only": True, "discard_business_unchanged": True, **protection_result}
    e.observe("original_contact_restore_refusal", evidence)
    return evidence


async def fields(e, values):
    for name, value in values.items():
        selector = f'#modal [name="{name}"]'
        target = e.page.locator(selector)
        await expect(target).to_have_count(1)
        if not await target.is_visible():
            details = target.locator("xpath=ancestor::details[1]")
            await expect(details).to_have_count(1)
            e.action("click", "展开原表单选填说明", field=name)
            await details.locator(":scope > summary").click()
        if isinstance(value, bool):
            await checkbox(e, selector, value, "明确原表单" + name)
        elif await e.page.locator(f'#modal select[name="{name}"]').count():
            await select_value(e, selector, value, "明确原表单" + name)
        else:
            await e.fill(selector, str(value), "填写原表单" + name)


def render_matches(response, path):
    actual = urlsplit(response.url).path
    return response.request.method == "GET" and (
        actual == path if not path.endswith("/") else actual.startswith(path) and actual[len(path):].isdigit())


async def submit(e, path, render_path, store_id, protection, *, method="POST", status=200):
    async with e.page.expect_response(lambda r: render_matches(r, render_path)) as rendered:
        async with e.page.expect_response(lambda r: r.request.method == method and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "明确提交原客户或服务表单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原客户表单HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await rendered.value
    read_body = await read.json()
    require(read.status == 200, "原提交成功后的页面读取失败")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token")), "原表单缺Cookie或CSRF")
    require(headers.get("x-store-id") == str(store_id), "原客户表单串店")
    request = response.request.post_data_json
    require(isinstance(request, dict) and isinstance(request.get("values"), dict), "原表单JSON合同不完整")
    care = path.startswith(CARE_API)
    if care:
        require(isinstance(request.get("request_id"), str) and len(request["request_id"]) >= 16,
                "原客户服务缺request_id")
    meta = {"path": path, "method": method, "status": response.status, "store_id": store_id,
            "native_ui": True, "cookie_present": True, "csrf_present": True,
            "submitted_version": request.get("version"), "render_get_path": urlsplit(read.url).path,
            "render_get_status": read.status, **after_write(e, protection)}
    if request.get("request_id"):
        meta["request_id_sha256"] = hashlib.sha256(request["request_id"].encode()).hexdigest()
        receipts = e.db.rows("SELECT actor_id,store_id FROM care_receipts WHERE request_key=?", (request["request_id"],))
        require(len(receipts) == 1 and receipts[0]["store_id"] == store_id, "原请求回执不存在或串店")
        meta["receipt_actor_id"] = receipts[0]["actor_id"]
    e.observe("original_customer_form_response", meta)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return body, read_body, request, meta


async def open_page(e, route, title, path):
    if urlsplit(e.page.url).fragment != route:
        await nav(e, route, title, path)
    else:
        await expect(e.page.locator("#main h1")).to_have_text(title)


async def refresh(e, path):
    before = e.business_snapshot("before_customer_original_refresh")
    async with e.page.expect_response(lambda r: render_matches(r, path)) as pending:
        e.action("browser_reload", "重新读取当前原页面")
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    data = await response.json()
    require(response.status == 200, "原页面刷新读取失败")
    e.business_unchanged(before, "after_customer_original_refresh")
    return data


async def search_customers(e, query):
    before = e.business_snapshot("before_original_customer_search")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == CUSTOMERS_API
            and parse_qs(urlsplit(r.url).query).get("q") == [query]) as pending:
        await e.fill('#filters [name="q"]', query, "先查询本次客户档案")
    response = await pending.value
    data = await response.json()
    require(response.status == 200, "原客户搜索失败")
    e.business_unchanged(before, "after_original_customer_search")
    return data


async def customer_form(e, key=None):
    await e.click(f'#main [data-act="editmaster"][data-id="{key}"]' if key else
                  '#main [data-act="newmaster"][data-kind="customers"]', "编辑原客户档案" if key else "新增原客户档案")
    await expect(e.page.locator("#modal-title")).to_have_text("编辑客户档案" if key else "新增客户档案")


async def save_customer(e, user, store_id, values, *, key=None):
    old = one(e, "flow_customers", key) if key else None
    await fields(e, values)
    protection = before_write(e, updates={"flow_customers": {key} if key else set()}, appends={"audit_logs"})
    body, listing, request, meta = await submit(e, CUSTOMERS_API + ("/" + str(key) if key else ""),
        CUSTOMERS_API, store_id, protection, method="PUT" if key else "POST", status=200 if key else 201)
    row = one(e, "flow_customers", body["id"])
    require(row["store_id"] == store_id and row["owner_id"] == (old["owner_id"] if old else user["id"]),
            "客户门店或负责人不匹配")
    for name in ("name", "phone", "contact_allowed", "note"):
        require(row[name] == request["values"][name] and body[name] == row[name], "客户原输入/API/DB不一致：" + name)
    if old:
        require(request["version"] == old["version"] and row["version"] > old["version"], "原客户CAS未匹配并前进")
    visible = next((r for r in listing["items"] if r["id"] == row["id"]), None)
    require(visible is not None and all(visible[k] == row[k] for k in ("name", "phone", "contact_allowed", "version")),
            "原客户列表/API/DB不一致")
    table_row = e.page.locator("#main tbody tr").filter(has=e.page.locator(f'[data-act="editmaster"][data-id="{row["id"]}"]'))
    await expect(table_row).to_have_count(1)
    await expect(table_row).to_contain_text(row["name"])
    if row["phone"]:
        await expect(table_row).to_contain_text(row["phone"])
    await expect(table_row.locator("td").nth(2)).to_have_text("是" if row["contact_allowed"] else "否")
    audits = e.db.rows("SELECT actor_id,store_id,action,entity_id FROM audit_logs WHERE entity_type='flow_master' "
                       "AND entity_id=? AND action=? ORDER BY id DESC LIMIT 1",
                       (row["id"], "master_update" if key else "master_create"))
    require(len(audits) == 1 and audits[0]["actor_id"] == user["id"] and audits[0]["store_id"] == store_id,
            "原客户审计员工或门店不匹配")
    return row, {"original_form": meta, "customer": row, "audit": audits[0]}


async def duplicate_refusal(e, phone, original):
    before = e.business_snapshot("before_customer_explicit_duplicate_choice")
    writes = []
    def observe(request):
        if request.method == "POST" and urlsplit(request.url).path == CUSTOMERS_API:
            writes.append(request.url)
    e.page.on("request", observe)
    try:
        async with e.page.expect_response(lambda r: r.request.method == "GET"
                and urlsplit(r.url).path == "/api/customer-choice/matches"
                and parse_qs(urlsplit(r.url).query).get("phone") == [phone]) as pending:
            await e.click('#modal form button[type="submit"]', "核对同号客户，尚未确认另建")
        response = await pending.value
        matches = await response.json()
        require(response.status == 200 and any(r["id"] == original["id"] for r in matches["items"]),
                "同号候选未返回原客户")
        await expect(e.page.locator("#modal .formerror")).to_contain_text("请核对匹配档案并明确勾选另建")
        await expect(e.page.locator("#modal [data-choice-results]")).to_contain_text(original["name"])
        await expect(e.page.locator('#modal [name="choice_confirm"]')).not_to_be_checked()
        require(not writes, "未明确另建时已经提交新客户")
        e.business_unchanged(before, "after_customer_explicit_duplicate_choice")
        await e.snapshot("customer-duplicate-explicit-choice")
        return {"phone_match": {"path": "/api/customer-choice/matches", "status": response.status,
                                "candidate_id": original["id"]}, "new_customer_posts": 0,
                "business_unchanged": True, "native_choice_prompt": True}
    finally:
        e.page.remove_listener("request", observe)


def vehicle_facts(e, key):
    return {"vehicle": one(e, "care_customer_vehicles", key),
            "observations": e.db.rows("SELECT * FROM care_vehicle_observations WHERE vehicle_id=? ORDER BY id", (key,)),
            "history": e.db.rows("SELECT * FROM care_history_links WHERE vehicle_id=? ORDER BY id", (key,))}


async def vehicle_rendered(e, f, api):
    row = f["vehicle"]
    require(all(api["vehicle"][k] == row[k] for k in ("id", "version", "customer_id", "vin", "plate", "model_name", "active")),
            "本店车辆关系API/DB不一致")
    await expect(e.page.locator("#main h1")).to_have_text("客户车辆 · " + (row["plate"] or row["vin"]))
    for text in (row["vin"], row["model_name"], row["identity_source"]):
        await expect(e.page.locator("#main")).to_contain_text(text)
    require(len(api["observations"]) == len(f["observations"]), "日期里程API/DB数量不一致")
    for original, read in zip(reversed(f["observations"]), api["observations"]):
        require(all(read[k] == original[k] for k in ("id", "vehicle_id", "kind", "observed_date", "odometer_km", "source_reference", "actor_id")),
                "原观察API/DB内容不一致")
        await expect(e.page.locator("#main")).to_contain_text(original["source_reference"])
    if f["observations"]:
        latest = f["observations"][-1]
        require(api["vehicle"]["odometer_km"] == latest["odometer_km"]
                and api["vehicle"]["observed_date"] == latest["observed_date"], "有效实际日期里程未显示最新来源")
        await expect(e.page.locator("#main")).to_contain_text(str(latest["odometer_km"]) + " 公里")


def care_facts(e, key):
    case = one(e, "flow_cases", key)
    records = e.db.rows("SELECT * FROM care_records WHERE case_id=? ORDER BY id", (key,))
    events = e.db.rows("SELECT * FROM flow_events WHERE case_id=? ORDER BY id", (key,))
    for row in records:
        row["details"] = json.loads(row["details"])
    for row in events:
        row["detail"] = json.loads(row["detail"])
    return {"case": case, "care": one(e, "care_cases", key, primary="case_id"), "records": records,
            "events": events, "tasks": e.db.rows("SELECT * FROM flow_tasks WHERE case_id=? ORDER BY id", (key,))}


def same_timestamp(left, right):
    return datetime.fromisoformat(str(left).rstrip("Z")).replace(tzinfo=None) == datetime.fromisoformat(str(right).rstrip("Z")).replace(tzinfo=None)


def stable_vehicle(before, after):
    require(all(after[k] == value for k, value in before.items() if k not in {"version", "updated_at"}),
            "服务或观察改写了原客户车辆身份/关系/车牌车型")
    require(after["version"] > before["version"], "车辆受控版本未前进")


async def care_rendered(e, f, api, user):
    case, care = f["case"], f["care"]
    customer = one(e, "flow_customers", case["customer_id"])
    require(len(f["tasks"]) == 1, "客服原待办不唯一")
    task = f["tasks"][0]
    require(all(api[k] == case[k] for k in ("id", "number", "version", "state", "customer_id", "due_date")),
            "客服原单API/DB不一致")
    require(api["vehicle_id"] == care["vehicle_id"] and api["subtype"] == care["subtype"]
            and api["result"] == care["result"] and api["assignee_id"] == task["assignee_id"] == user["id"],
            "客服类型、车辆、结果或本人经办不一致")
    require(task["key"] == "care_handle" and task["case_id"] == case["id"]
            and task["store_id"] == case["store_id"] and task["due_date"] == case["due_date"]
            and task["status"] == ("done" if case["state"] == "completed" else "open"),
            "原客服待办串单/串店/期限或实际状态不一致")
    require(api["customer_name"] == customer["name"] and api["customer_phone"] == customer["phone"]
            and api["contact_allowed"] == bool(customer["contact_allowed"])
            and api["description"] == care["description"] and api["location"] == care["location"],
            "客服显示的客户联系资料或原诉求与DB不一致")
    require(len(api["records"]) == len(f["records"]), "原办理记录数量不一致")
    for read, row in zip(api["records"], f["records"]):
        require(all(read[k] == row[k] for k in ("id", "case_id", "store_id", "actor_id", "action", "note", "details"))
                and same_timestamp(read["created_at"], row["created_at"]), "客服原记录API/DB不一致")
    await expect(e.page.locator("#main h1")).to_have_text(case["title"] + " · " + case["number"])
    await expect(e.page.locator("#main")).to_contain_text(care["topic"])
    await expect(e.page.locator("#main")).to_contain_text(customer["name"])
    await expect(e.page.locator("#main")).to_contain_text(customer["phone"] or "未留电话")
    await expect(e.page.locator("#main")).to_contain_text(care["description"])
    await expect(e.page.locator("#main")).to_contain_text(user["display_name"])
    await expect(e.page.locator("#main")).to_contain_text(api["state_label"])
    panel = e.page.locator("#main .panel").filter(has=e.page.get_by_role("heading", name="办理记录", exact=True))
    await expect(panel).to_have_count(1)
    await expect(panel.locator("article")).to_have_count(len(f["records"]))
    for row in f["records"]:
        await expect(panel).to_contain_text(row["note"])
    if care["location"]:
        await expect(e.page.locator("#main")).to_contain_text(care["location"])
    if care["result"]:
        await expect(e.page.locator("#main")).to_contain_text(api["result_label"])


def case_updates(e, vehicle_id, store_id, *, case_id=None, closing=False):
    updates = {"care_customer_vehicles": {vehicle_id}}
    appends = {"care_receipts", "care_records", "flow_events", "audit_logs"}
    if case_id:
        updates["flow_cases"] = {case_id}
        updates["flow_tasks"] = {r["id"] for r in e.db.rows("SELECT id FROM flow_tasks WHERE case_id=?", (case_id,))}
        if closing:
            updates["care_cases"] = {case_id}
    else:
        appends |= {"flow_cases", "flow_tasks", "care_cases", "business_entity_case_contexts"}
        controls = e.db.rows("SELECT id FROM business_entity_store_controls WHERE store_id=?", (store_id,))
        updates["business_entity_store_controls"] = {r["id"] for r in controls}
    return before_write(e, updates=updates, appends=appends)


def care_audit(e, protection, facts, user):
    old_ids = {r["id"] for r in protection[1]["audit_logs"]}
    audits = [r for r in e.db.rows("SELECT * FROM audit_logs ORDER BY id") if r["id"] not in old_ids]
    require(len(audits) == 1, "一次客服办理没有恰好追加一条原审计")
    audit, event, case = audits[0], facts["events"][-1], facts["case"]
    require(audit["actor_id"] == user["id"] and audit["store_id"] == case["store_id"]
            and audit["action"] == "flow_" + event["action"] and audit["entity_type"] == "flow"
            and audit["entity_id"] == case["id"] and audit["reason"] == event["label"]
            and json.loads(audit["before_data"]) is None
            and json.loads(audit["after_data"]) == {"store_id": case["store_id"], "state": case["state"], "number": case["number"]},
            "客服原审计身份、源单或实际结果不匹配")
    return audit


async def handle_care(e, user, store_id, customer, vehicle, subtype, token):
    labels = {"consultation": "客户咨询", "complaint": "客户投诉", "rescue": "客户救援"}
    label = labels[subtype]
    topic = label + "-" + token
    description = {"consultation": "合成客户咨询下次进店需携带的资料。", "complaint": "合成客户反馈上次服务说明不清，要求核对并答复。",
                   "rescue": "合成客户在约定位置等待，要求提供本店支持联系人和下一步安排。"}[subtype]
    location = "合成停车场东入口第3车位" if subtype == "rescue" else ""
    if subtype == "consultation":
        await e.click('#main [data-act="care-new-vehicle-case"]', "登记本车独立咨询")
        await expect(e.page.locator('#modal [name="customer_id"]')).to_have_value(str(customer["id"]))
        await expect(e.page.locator('#modal [name="vehicle_id"]')).to_have_value(str(vehicle["id"]))
    else:
        await open_page(e, "customer-service", "客户服务工作台", CARE_API + "/cases")
        await select_value(e, '#main [name="care_create_type"]', subtype, "选择独立" + label)
        await e.click('#main [data-act="care-new"]', "登记独立" + label)
        async with e.page.expect_response(lambda r: r.request.method == "GET"
                and urlsplit(r.url).path == CARE_API + "/lookup/vehicles"
                and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
            await select_value(e, '#modal [name="customer_id"]', customer["id"], "选择本轮原客户")
        response = await pending.value
        require(response.status == 200, "原客户车辆候选读取失败")
        await response.body()
        await expect(e.page.locator(f'#modal [name="vehicle_id"] option[value="{vehicle["id"]}"]')).to_have_count(1)
        await select_value(e, '#modal [name="vehicle_id"]', vehicle["id"], "明确关联本轮客户车辆")
    await expect(e.page.locator("#modal-title")).to_have_text("登记" + label)
    values = {"topic": topic, "description": description, "priority": "normal",
              "assignee_id": user["id"], "due_date": business_today().isoformat()}
    if location:
        values["location"] = location
    await fields(e, values)
    vehicle_before = one(e, "care_customer_vehicles", vehicle["id"])
    protection = case_updates(e, vehicle["id"], store_id)
    body, read, request, create_meta = await submit(e, CARE_API + "/cases", CARE_API + "/cases/", store_id, protection, status=201)
    f = care_facts(e, body["case"]["id"])
    create_meta["original_audit"] = care_audit(e, protection, f, user)
    stable_vehicle(vehicle_before, one(e, "care_customer_vehicles", vehicle["id"]))
    require(create_meta["receipt_actor_id"] == user["id"] and request["values"]["customer_id"] == customer["id"]
            and request["values"]["vehicle_id"] == vehicle["id"] and request["values"]["assignee_id"] == user["id"],
            "原客服表单缺明确客户、车辆或本人经办")
    require(f["case"]["store_id"] == store_id and f["case"]["kind"] == "customer_care" and f["case"]["flow_version"] == 2
            and f["case"]["state"] == "pending" and f["case"]["owner_id"] == f["case"]["created_by"] == user["id"]
            and f["care"]["subtype"] == subtype and f["care"]["topic"] == topic and f["care"]["description"] == description
            and f["care"]["location"] == location and f["care"]["source_case_id"] is None,
            "独立客服原事实与输入不一致")
    require(len(f["records"]) == len(f["events"]) == len(f["tasks"]) == 1
            and f["records"][0]["action"] == "create" and f["events"][0]["action"] == "care_create"
            and f["tasks"][0]["status"] == "open", "客服创建缺原记录/事件/唯一待办")
    await care_rendered(e, f, read, user)
    submitted = [create_meta]
    notes = {"consultation": ["已当面答复需带车辆资料，客户要求再核对接待时间。", "已核对接待时间并当面告知，客户确认资料清单。"],
             "complaint": ["已核对客户反馈及本店说明，向客户解释处理范围。", "已当面补充说明处理结果，客户确认本次问题已解决。"],
             "rescue": ["已当面核对合成停车位置，并提供本店支持联系人。", "已核对后续支持安排，客户确认本次协调诉求已解决。"]}[subtype]
    operations = [
        ("start", {}, "working"),
        ("followup", {"channel": "in_person", "contact_result": "progress", "note": notes[0],
                      "next_due_date": (business_today() + timedelta(days=1)).isoformat()}, "working"),
        ("followup", {"channel": "in_person", "contact_result": "contacted", "note": notes[1],
                      "next_due_date": (business_today() + timedelta(days=2)).isoformat()}, "working"),
        ("close", {"result": "resolved", "note": label + "合成原诉求已当面核对并答复，依据为上列两次实际办理记录。"}, "completed"),
    ]
    for action, values, state in operations:
        before = f
        await e.click(f'#main [data-act="care-action"][data-action="{action}"]', "本人" + {"start": "接手办理", "followup": "登记实际跟进", "close": "登记实际结案"}[action])
        await fields(e, values)
        vehicle_before = one(e, "care_customer_vehicles", vehicle["id"])
        protection = case_updates(e, vehicle["id"], store_id, case_id=f["case"]["id"], closing=action == "close")
        _, read, request, meta = await submit(e, CARE_API + f'/cases/{f["case"]["id"]}/actions/{action}',
            CARE_API + f'/cases/{f["case"]["id"]}', store_id, protection)
        f = care_facts(e, before["case"]["id"])
        meta["original_audit"] = care_audit(e, protection, f, user)
        stable_vehicle(vehicle_before, one(e, "care_customer_vehicles", vehicle["id"]))
        require(meta["receipt_actor_id"] == user["id"] and request["version"] == before["case"]["version"]
                and f["case"]["version"] > before["case"]["version"] and f["case"]["state"] == state,
                "客服原CAS/本人身份/办理状态不匹配")
        for key, value in before["case"].items():
            if key not in {"state", "due_date", "updated_at", "version", "completed_date"}:
                require(f["case"][key] == value, "客服原身份被替换：" + key)
        for key, value in before["care"].items():
            if key != "result":
                require(f["care"][key] == value, "客服原诉求或关联被覆盖：" + key)
        require(f["records"][:-1] == before["records"] and f["events"][:-1] == before["events"],
                "原办理记录或事件被覆盖/未单次追加")
        record, event = f["records"][-1], f["events"][-1]
        require(record["action"] == action and event["action"] == "care_" + action
                and record["actor_id"] == event["actor_id"] == user["id"]
                and record["case_id"] == event["case_id"] == f["case"]["id"]
                and record["store_id"] == event["store_id"] == store_id and event["after_state"] == state,
                "新原记录身份、源单或办理后状态不匹配")
        require(f["tasks"][0]["id"] == before["tasks"][0]["id"] and len(f["tasks"]) == 1,
                "跟进另建待办而非更新原任务")
        for key, value in before["tasks"][0].items():
            if key not in {"status", "due_date", "version", "updated_at", "done_by", "done_at"}:
                require(f["tasks"][0][key] == value, "客服原任务身份被替换：" + key)
        if action == "followup":
            require(record["note"] == values["note"] and all(record["details"][k] == values[k]
                    for k in ("channel", "contact_result", "next_due_date"))
                    and f["case"]["due_date"] == f["tasks"][0]["due_date"] == values["next_due_date"],
                    "原实际跟进或期限与输入不一致")
        if action == "close":
            require(f["care"]["result"] == "resolved" and record["note"] == values["note"]
                    and f["tasks"][0]["status"] == "done" and f["tasks"][0]["done_by"] == user["id"]
                    and f["tasks"][0]["done_at"] and f["case"]["completed_date"] == business_today().isoformat(),
                    "原客服结案结果或任务完成事实不一致")
        await care_rendered(e, f, read, user)
        submitted.append(meta)
    read = await refresh(e, CARE_API + f'/cases/{f["case"]["id"]}')
    require(care_facts(e, f["case"]["id"]) == f, "客服刷新重复记录或覆盖原结果")
    await care_rendered(e, f, read, user)
    await expect(e.page.locator('#main [data-act="care-action"]')).to_have_count(0)
    return f, {"original_forms": submitted, "original_facts": f, "refresh_business_unchanged": True,
               "two_distinct_followups": notes, "external_contact_or_dispatch_claimed": False}


async def customer_service_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    store_id = e.manifest["business_fixtures"]["vehicle_purchase"]["store_id"]
    token = uuid.uuid4().hex[:10]
    prefix = "服务档案-" + token
    try:
        checkpoint.start("HK-098")
        service = await login_as(e, context, credentials, "service", "master/customers", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("客户档案")
        listing = await search_customers(e, prefix)
        require(not listing["items"], "本轮独立客户命名已经存在")
        await customer_form(e)
        customer, created = await save_customer(e, service, store_id, {
            "name": prefix + "甲", "phone": "", "contact_allowed": True, "note": "合成客户本人到店咨询，电话稍后补充。"})
        phone = "139" + str(int(token, 16) % 100_000_000).zfill(8)
        await customer_form(e, customer["id"])
        customer, edited = await save_customer(e, service, store_id, {
            "phone": phone, "note": "合成客户明确提供电话和车辆关系资料，允许后续联系。"}, key=customer["id"])
        await customer_form(e)
        await fields(e, {"name": prefix + "乙", "phone": phone, "contact_allowed": True,
                         "note": "合成同号独立客户；员工明确核对后另建，禁止合并。"})
        duplicate_prompt = await duplicate_refusal(e, phone, customer)
        await checkbox(e, '#modal [name="choice_confirm"]', True, "员工明确仍然新建独立客户")
        duplicate, duplicate_created = await save_customer(e, service, store_id, {})
        require(duplicate["id"] != customer["id"] and duplicate["phone"] == customer["phone"]
                and duplicate["name"] != customer["name"], "同号客户被覆盖或自动合并")
        require(one(e, "flow_customers", customer["id"]) == customer, "另建客户改写了原客户联系资料")
        await customer_form(e, customer["id"])
        customer, withdrawn = await save_customer(e, service, store_id, {"contact_allowed": False,
            "note": "合成客户撤回主动联系授权；只保留客户已到店的内部服务办理。"}, key=customer["id"])
        await customer_form(e, customer["id"])
        await fields(e, {"contact_allowed": True})
        refusal = await restore_contact_refusal(e, service, store_id, customer)
        require(one(e, "flow_customers", customer["id"]) == customer, "本人恢复拒绝后客户被修改")
        manager = await login_as(e, context, credentials, "manager", "master/customers", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("客户档案")
        await search_customers(e, prefix)
        await customer_form(e, customer["id"])
        customer, restored = await save_customer(e, manager, store_id, {"contact_allowed": True,
            "note": "主管当面核对合成客户重新同意后续联系；保留此前撤回审计。"}, key=customer["id"])
        reread = await refresh(e, CUSTOMERS_API)
        require(any(r["id"] == customer["id"] and r["contact_allowed"] is True for r in reread["items"]),
                "主管恢复后的原客户没有真实重读")
        await checkpoint.passed({"create": created, "edit": edited, "duplicate_prompt": duplicate_prompt,
            "explicit_duplicate_create": duplicate_created, "withdraw": withdrawn,
            "service_restore_refusal": refusal, "manager_restore": restored,
            "distinct_customer_ids": [customer["id"], duplicate["id"]], "original_owner_id": service["id"]})

        service = await login_as(e, context, credentials, "service", "customer-vehicles", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("客户车辆档案")
        await e.click('#main [data-act="care-vehicle-new"]', "登记本店真实客户车辆前置")
        vin = "LHGCM8263" + token[:8].upper()
        model = "合成客户车辆-" + token
        await fields(e, {"customer_id": customer["id"], "vin": vin, "plate": "合成" + token[-6:],
            "model_name": model, "source_reference": "合成客户本人现场提供VIN与关系资料-" + token, "confirmed": True})
        protection = before_write(e, appends={"care_customer_vehicles", "group_identities", "group_identity_links",
                                             "group_events", "care_receipts", "audit_logs"})
        body, read, request, vehicle_created = await submit(e, CARE_API + "/vehicles", CARE_API + "/vehicles/",
                                                           store_id, protection, status=201)
        vf = vehicle_facts(e, body["vehicle"]["id"])
        vehicle = vf["vehicle"]
        require(vehicle["customer_id"] == customer["id"] and vehicle["store_id"] == store_id
                and vehicle["created_by"] == service["id"] and vehicle["vin"] == vin
                and request["values"]["customer_identity_id"] is None and vehicle_created["receipt_actor_id"] == service["id"],
                "车辆关系缺当前客户、VIN或本人身份")
        links = e.db.rows("SELECT * FROM group_identity_links WHERE local_kind='customer' AND local_id=? AND store_id=?",
                          (customer["id"], store_id))
        require(len(links) == 1 and links[0]["identity_id"] == vehicle["customer_identity_id"]
                and links[0]["confirmed_by"] == service["id"], "原集团客户身份关联不明确")
        vehicle_identity = one(e, "group_identities", vehicle["vehicle_identity_id"])
        require(vehicle_identity["kind"] == "vehicle" and vehicle_identity["canonical_key"] == vin, "集团车辆身份VIN不匹配")
        await vehicle_rendered(e, vf, read)
        await e.click('#main [data-act="care-vehicle-edit"]', "维护本店车辆车牌和车型说明")
        await fields(e, {"plate": "核对" + token[-6:], "model_name": model + "已核对", "active": True,
                         "reason": "合成客户本人补充车牌与完整车型，VIN与客户关系保持原样。"})
        before_vehicle = vehicle
        protection = before_write(e, updates={"care_customer_vehicles": {vehicle["id"]}}, appends={"care_receipts", "audit_logs"})
        _, read, request, vehicle_edited = await submit(e, CARE_API + "/vehicles/" + str(vehicle["id"]),
            CARE_API + "/vehicles/" + str(vehicle["id"]), store_id, protection, method="PUT")
        vf = vehicle_facts(e, vehicle["id"])
        vehicle = vf["vehicle"]
        require(request["version"] == before_vehicle["version"] and vehicle["version"] > before_vehicle["version"],
                "原车辆关系CAS未核对并前进")
        require(all(vehicle[k] == request["values"][k] for k in ("plate", "model_name", "active")),
                "车辆维护输入与实际保存不一致")
        for key in ("customer_id", "customer_identity_id", "vehicle_identity_id", "vin", "store_id", "created_by", "identity_source"):
            require(vehicle[key] == before_vehicle[key], "维护关系覆盖原身份：" + key)
        await vehicle_rendered(e, vf, read)
        observation_meta = []
        for offset, km in ((1, 12000), (0, 12125)):
            before_vf = vf
            await e.click('#main [data-act="care-observe"]', "追加独立实测日期里程")
            values = {"kind": "odometer", "observed_date": (business_today() - timedelta(days=offset)).isoformat(),
                      "odometer_km": km, "source_reference": f"合成现场里程照片记录-{token}-{km}", "confirmed": True}
            await fields(e, values)
            protection = before_write(e, updates={"care_customer_vehicles": {vehicle["id"]}},
                                      appends={"care_vehicle_observations", "care_receipts", "audit_logs"})
            _, read, request, meta = await submit(e, CARE_API + f'/vehicles/{vehicle["id"]}/observations',
                CARE_API + "/vehicles/" + str(vehicle["id"]), store_id, protection)
            vf = vehicle_facts(e, vehicle["id"])
            stable_vehicle(before_vf["vehicle"], vf["vehicle"])
            require(vf["observations"][:-1] == before_vf["observations"] and len(vf["observations"]) == len(before_vf["observations"]) + 1,
                    "实测观察未单次追加或改写了原记录")
            observation = vf["observations"][-1]
            require(request["version"] == before_vf["vehicle"]["version"]
                    and observation["actor_id"] == meta["receipt_actor_id"] == service["id"]
                    and all(observation[k] == values[k] for k in ("kind", "observed_date", "odometer_km", "source_reference"))
                    and observation["valid_until"] is None and observation["evidence_id"] is None, "实际观察来源/单位/日期不匹配")
            await vehicle_rendered(e, vf, read)
            observation_meta.append({"original_form": meta, "observation": observation})
        vehicle = vf["vehicle"]
        local = {"vehicle_create": vehicle_created, "vehicle_edit": vehicle_edited, "identity_link": links[0],
                 "vehicle_identity": {"id": vehicle_identity["id"], "kind": "vehicle", "vin": vin},
                 "observations": observation_meta, "vehicle": vehicle, "original_consultation_history": "pending"}
        checkpoint.local_source(local)

        care_results = {}
        for key, subtype in (("HK-107", "consultation"), ("HK-108", "complaint"), ("HK-109", "rescue")):
            checkpoint.start(key)
            f, evidence = await handle_care(e, service, store_id, customer, vehicle, subtype, token)
            care_results[subtype] = f
            await checkpoint.passed(evidence)
        require(len({f["case"]["id"] for f in care_results.values()}) == 3, "三种客服类型复用了同一原单")

        await open_page(e, "customer-vehicles", "客户车辆档案", CARE_API + "/vehicles")
        async with e.page.expect_response(lambda r: render_matches(r, CARE_API + "/vehicles/" + str(vehicle["id"]))) as pending:
            await e.click(f'#main [data-act="open"][data-route="customer-vehicles/{vehicle["id"]}"]', "读取本轮客户车辆及有效来源")
        response = await pending.value
        read = await response.json()
        require(response.status == 200, "本轮客户车辆详情读取失败")
        await vehicle_rendered(e, vehicle_facts(e, vehicle["id"]), read)
        await e.click('#main [data-act="care-history-link"]', "将真实已结案咨询关联为本车服务摘要")
        consultation = care_results["consultation"]["case"]
        await expect(e.page.locator(f'#modal [name="case_id"] option[value="{consultation["id"]}"]')).to_contain_text(consultation["number"])
        summary = "已当面核对本车后续进店资料和接待时间；不含费用及隐私资料。"
        await fields(e, {"case_id": consultation["id"], "summary": summary,
                         "source_reference": "本人核对本次咨询原单与客户车辆关系-" + token, "confirmed": True})
        protection = before_write(e, appends={"care_history_links", "care_receipts", "audit_logs"})
        body, read, request, history_meta = await submit(e, CARE_API + f'/vehicles/{vehicle["id"]}/history-links',
            CARE_API + "/vehicles/" + str(vehicle["id"]), store_id, protection, status=201)
        histories = e.db.rows("SELECT * FROM care_history_links WHERE vehicle_id=? ORDER BY id", (vehicle["id"],))
        require(len(histories) == 1 and histories[0]["id"] == body["link_id"]
                and histories[0]["case_id"] == request["values"]["case_id"] == consultation["id"]
                and histories[0]["summary"] == summary and histories[0]["confirmed_by"] == service["id"],
                "本车服务摘要缺真实已结束原咨询来源")
        await expect(e.page.locator("#main")).to_contain_text(summary)
        await expect(e.page.locator("#main")).to_contain_text(consultation["number"])
        before_refresh = e.business_snapshot("before_local_customer_vehicle_history_refresh")
        async with e.page.expect_response(lambda r: render_matches(r, CARE_API + f'/vehicles/{vehicle["id"]}/history')) as history_read:
            await refresh(e, CARE_API + "/vehicles/" + str(vehicle["id"]))
        history_response = await history_read.value
        history_body = await history_response.json()
        require(history_response.status == 200 and len(history_body["items"]) == 1, "原车辆历史必须为非空且唯一")
        item = history_body["items"][0]
        require(item["case_id"] == consultation["id"] and item["number"] == consultation["number"]
                and item["state"] == "completed" and item["summary"] == summary and item["external"] is False,
                "本车原历史UI/API/DB事实不一致")
        e.business_unchanged(before_refresh, "after_local_customer_vehicle_history_refresh")
        local.update(original_consultation_history={"original_form": history_meta, "original_link": histories[0],
                     "history_get": {"path": CARE_API + f'/vehicles/{vehicle["id"]}/history', "status": 200, "item": item},
                     "refresh_business_unchanged": True}, vehicle=one(e, "care_customer_vehicles", vehicle["id"]))
        checkpoint.local_source(local, complete=True)
        await e.snapshot("hk099-local-source-partial-not-business-accepted")
        checkpoint.finish()
    except Exception as error:
        checkpoint.failed(error)
        raise


CUSTOMER_SERVICE_SCENARIOS = ((SCENARIO, customer_service_business, 360),)
