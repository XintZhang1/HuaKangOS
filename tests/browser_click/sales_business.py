"""Native presales acceptance for HK-001 through HK-007.

The existing runner supplies Evidence, a real browser context and isolated
credentials. Every business mutation comes from the original visible form.
SQLite is opened read-only by Evidence; no production module is imported.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect


SCENARIO = "sales-presales-hk001-007"
STATE_LABELS = {"unassigned": "待分派", "contacting": "待接待反馈", "reminder": "接待回访中", "intent": "意向跟进中"}
CONTRACTS = (
    ("HK-001", "展厅接待", "HK-001-create", (
        "原新建表单实际建立一张接待与一个新客户",
        "原 assign 任务和创建事件同店、同原单、同创建人",
        "姓名、来源及原单状态真实显示且与数据库一致",
    )),
    ("HK-002", "展厅接待分派", "HK-002-assign", (
        "主管在原分派表单明确选择本店启用销售",
        "原 assign 任务结束、contact 任务交给该销售",
        "同原单及客户负责人转交，分派事件保留原身份",
    )),
    ("HK-003", "意向客户管理", "HK-003-intent", (
        "销售从原接待转意向，明确填写需求和下次日期",
        "原单 intent、need、due_date 与原 follow 任务一致",
        "客户及接待 ID 不变，原接待和回访历史保留",
    )),
    ("HK-004", "意向单分派", "HK-004-reassign", (
        "主管在原 follow 任务转交表单选择另一位本店销售及原因",
        "Task、Case 及原负责人持有的 Customer 同事务转交",
        "转交历史保留，旧销售的原列表和我的工作不再含此原单",
    )),
    ("HK-005", "意向单跟进记录", "HK-005-history", (
        "接手销售在同一原单实际提交两次不同沟通结果及日期",
        "独立 follow 事件追加，第一次记录不被第二次覆盖",
        "原 follow 任务更新期限且仍唯一，不新增客户或接待",
    )),
    ("HK-006", "展厅接待提醒", "HK-006-reminder", (
        "缺电话时原必填校验阻止回访提交且原业务不变",
        "销售在原表单补电话、沟通结果及今日回访日期",
        "今日我的工作显示同原单 contact 提醒并可点击办理",
    )),
    ("HK-007", "意向客户提醒", "HK-007-reminder", (
        "意向 follow 任务期限为今日且与原单期限一致",
        "接手销售的今日我的工作显示标题、单号、负责人及期限",
        "从提醒实际点击进入同原单提交新跟进，刷新不重复建任务",
    )),
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Checkpoint:
    def __init__(self, e):
        self.e = e
        self.active = None
        self.path = e.directory / "business-checkpoint.json"
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": "HK-001..HK-007",
            "complete": False, "passed": False,
            "full_193_business_acceptance": False,
            "full_registered_suite_complete": False,
            "execution": "native_browser_original_forms",
            "reminder_contract": "original_due_today_task_in_my_work; no_external_notification_claim",
            "requirements": [{
                "id": key, "title": title, "status": "not_tested",
                "acceptance_checks": [{"id": check_id, "check_id": check_id, "status": "not_tested",
                                       "criteria": list(criteria), "evidence": {}}],
            } for key, title, check_id, criteria in CONTRACTS],
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(row for row in self.report["requirements"] if row["id"] == key)
        self.active["status"] = "running"
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    async def passed(self, evidence):
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active["status"] = "passed"
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active is not None:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self):
        require(all(row["status"] == "passed" for row in self.report["requirements"]), "售前七项业务验收不完整")
        self.report.update(complete=True, passed=True, executed_requirements=7, passed_requirements=7)
        self.save()
        self.e.observe("presales_business_checkpoint", {"path": str(self.path), "requirements": 7, "passed": 7})


def facts(e, case_id):
    cases = e.db.rows(
        "SELECT id,number,kind,state,flow_version,store_id,title,owner_id,created_by,customer_id,"
        "version,business_date,due_date,data FROM flow_cases WHERE id=?", (case_id,))
    require(len(cases) == 1, "真实点击返回的原接待不存在或不唯一")
    row = cases[0]
    row["data"] = json.loads(row["data"])
    customers = e.db.rows(
        "SELECT id,store_id,name,phone,contact_allowed,owner_id,version FROM flow_customers WHERE id=?",
        (row["customer_id"],))
    require(len(customers) == 1, "原客户事实不存在或不唯一")
    tasks = e.db.rows(
        "SELECT id,case_id,store_id,key,title,role,assignee_id,status,due_date,version,done_by,done_at "
        "FROM flow_tasks WHERE case_id=? ORDER BY id", (case_id,))
    events = e.db.rows(
        "SELECT id,case_id,store_id,actor_id,action,label,before_state,after_state,detail "
        "FROM flow_events WHERE case_id=? ORDER BY id", (case_id,))
    for event in events:
        event["detail"] = json.loads(event["detail"])
    return {"case": row, "customer": customers[0], "tasks": tasks, "events": events}


def task(f, key, status="open"):
    rows = [row for row in f["tasks"] if row["key"] == key and row["status"] == status]
    require(len(rows) == 1, f"原 {key} 任务必须唯一且状态为 {status}")
    return rows[0]


def new_event(before, after, action, actor_id):
    require(after["events"][:-1] == before["events"], "原历史被改写或事件未单次追加")
    row = after["events"][-1]
    require(row["action"] == action and row["actor_id"] == actor_id, "原事件动作或员工身份不匹配")
    require(row["case_id"] == before["case"]["id"] and row["store_id"] == before["case"]["store_id"], "原事件串单或串店")
    return row


def same_original(before, after):
    for key in ("id", "number", "kind", "flow_version", "store_id", "created_by", "customer_id"):
        require(before["case"][key] == after["case"][key], f"原接待事实 {key} 改变")
    require(before["customer"]["id"] == after["customer"]["id"], "后继动作另建客户")


async def rendered_case(e, f):
    await expect(e.page.locator("#main h1")).to_have_text(f["case"]["title"])
    await expect(e.page.locator("#main .timelineitem")).to_have_count(len(f["events"]))
    await expect(e.page.locator("#main .pagehead")).to_contain_text(f["case"]["number"])
    await expect(e.page.locator("#main .pagehead")).to_contain_text(STATE_LABELS[f["case"]["state"]])
    await expect(e.page.locator("#main")).to_contain_text(f["customer"]["name"])
    for original in (row for row in f["tasks"] if row["status"] == "open"):
        task_ui = e.page.locator('#main .taskitem:has(.taskstate.open)').filter(has_text=original["title"])
        await expect(task_ui).to_have_count(1)
        await expect(task_ui).to_contain_text(original["due_date"])
        known = next((u for u in e.manifest["users"].values() if u["id"] == original["assignee_id"]), None)
        if known is not None:
            await expect(task_ui).to_contain_text(known["display_name"])
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)


async def login_as(e, context, credentials, key, route, store_id):
    if await e.page.locator('[data-act="logout"]').count():
        async with e.page.expect_response(lambda r: urlsplit(r.url).path == "/api/auth/logout" and r.request.method == "POST") as pending:
            await e.click('[data-act="logout"]', "退出后换员工登录")
        response = await pending.value
        require(response.status == 200, "换员工前真实退出未成功")
        await response.body()
        await expect(e.page.locator('input[name="username"]')).to_be_visible()
    user = await e.login(context, credentials, role=key, route=route)
    await expect(e.page.locator(".identity .who")).to_contain_text(user["display_name"])
    await expect(e.page.locator("#store")).to_have_value(str(store_id))
    return user


async def native_submit(e, path, expected_status, *, case_id=None):
    # The response observer sees untouched Cookie/CSRF requests from the form.
    async with e.page.expect_response(lambda r: r.request.method == "GET"
            and (urlsplit(r.url).path == f"/api/flow/cases/{case_id}" if case_id is not None
                 else urlsplit(r.url).path.startswith("/api/flow/cases/")
                 and urlsplit(r.url).path.rsplit("/", 1)[-1].isdigit())) as rendered:
        async with e.page.expect_response(lambda r: urlsplit(r.url).path == path and r.request.method == "POST") as pending:
            await e.click('#modal form button[type="submit"]', "提交原业务表单")
        response = await pending.value
        body = await response.json()
        require(response.status == expected_status, f"原业务点击返回 HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read_response = await rendered.value
    read_body = await read_response.json()
    require(read_response.status == 200, "提交后原单真实读取失败")
    require(read_body.get("id") == (case_id if case_id is not None else body.get("id")), "提交后原页面读取了其他原单")
    request = response.request.post_data_json
    require(isinstance(request, dict), "原表单未提交原 JSON 合同")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token")), "原表单请求缺 Cookie 或 CSRF")
    require(headers.get("x-store-id") == str(e.manifest["business_fixtures"]["presales"]["store_id"]), "原提交门店错误")
    metadata = {"path": path, "method": "POST", "status": response.status,
                "native_ui": True, "cookie_present": True, "csrf_present": True,
                "submitted_version": request.get("version"),
                "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request.get("request_id") else None,
                "response_id": body.get("id"), "response_version": body.get("version"),
                "render_get_path": urlsplit(read_response.url).path, "render_get_status": read_response.status}
    e.observe("original_form_response", metadata)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    return body, metadata, read_body


async def employee_choice(e, user):
    query = '#modal .lookup[data-kind="employee"] [data-lookup-query]'
    await e.fill(query, user["display_name"], "查找明确的本店接手员工")
    option = '#modal .lookup[data-kind="employee"] [role="option"]'
    matching = e.page.locator(option).filter(has_text=re.compile(r"^" + re.escape(user["display_name"]) + r"\s*·"))
    await expect(matching).to_have_count(1)
    # Search replaces the list and its generated indices. Keep the locator tied
    # to the exact employee name so native click resolves the current option.
    await expect(matching).to_be_visible()
    e.action("click", "选择" + user["display_name"], employee_id=user["id"])
    await matching.click()
    await expect(e.page.locator('#modal select[name="assignee_id"]')).to_have_value(str(user["id"]))


async def action_form(e, key, title):
    selector = f'#main [data-act="caseaction"][data-key="{key}"]'
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, title)
    await expect(e.page.locator("#modal-title")).to_have_text(title)


async def due_work(e, f, key, *, open_case=True):
    before = e.business_snapshot("original_business_before_due_work")
    async with e.page.expect_response(lambda r: urlsplit(r.url).path == "/api/flow/tasks" and r.request.method == "GET") as pending:
        await e.click('.sidebar a[href="#work"]', "打开我的工作")
    require((await pending.value).status == 200, "我的工作真实读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("我的工作")
    async with e.page.expect_response(lambda r: urlsplit(r.url).path == "/api/flow/tasks"
            and parse_qs(urlsplit(r.url).query).get("due") == ["today"] and r.request.method == "GET") as pending:
        await e.click('[data-mux-due="today"]', "筛选计划今天的提醒")
    require((await pending.value).status == 200, "计划今天筛选真实读取失败")
    async with e.page.expect_response(lambda r: urlsplit(r.url).path == "/api/flow/tasks"
            and parse_qs(urlsplit(r.url).query).get("q") == [f["case"]["number"]]
            and parse_qs(urlsplit(r.url).query).get("due") == ["today"] and r.request.method == "GET") as pending:
        await e.fill('#filters [name="q"]', f["case"]["number"], "查找本次原单提醒")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and len(body.get("items", [])) == 1, "原今日提醒查询必须真实返回一条本单任务")
    original = task(f, key)
    item = body["items"][0]
    for field in ("id", "case_id", "key", "title", "assignee_id", "status", "due_date", "version"):
        require(item[field] == original[field], f"原提醒 API / DB 的 {field} 不一致")
    require(item["case_number"] == f["case"]["number"] and item["state_label"] in ("接待回访中", "意向跟进中"), "提醒串单或状态错误")
    row = e.page.locator("#main .work-table tbody tr")
    await expect(row).to_have_count(1)
    for text in (original["title"], f["case"]["number"], item["assignee_name"], original["due_date"]):
        await expect(row).to_contain_text(text)
    await expect(e.page.locator('[data-mux-due="today"]')).to_have_attribute("aria-pressed", "true")
    evidence = {"path": urlsplit(response.url).path, "method": "GET", "status": 200,
                "source": "native_my_work_ui", "task_id": original["id"], "case_id": f["case"]["id"],
                "due_date": original["due_date"], "visible_row": await row.inner_text()}
    await e.snapshot(key + "-today-reminder")
    if open_case:
        async with e.page.expect_response(lambda r: urlsplit(r.url).path == f'/api/flow/cases/{f["case"]["id"]}' and r.request.method == "GET") as pending:
            await e.click(f'#main .work-table [data-act="open"][data-route="case/{f["case"]["id"]}"]', "从今日提醒进入原单办理")
        require((await pending.value).status == 200, "原提醒办理入口未读取同原单")
        await rendered_case(e, f)
    e.business_unchanged(before, "original_business_after_due_work")
    e.observe("original_due_reminder", evidence)
    return evidence


async def old_sales_scope(e, f):
    """Inspect original UI lists as the former owner, without a positive API bypass."""
    before = e.business_snapshot("original_business_before_old_sales_scope")
    await expect(e.page.locator("#main h1")).to_have_text("售前接待")
    async with e.page.expect_response(lambda r: urlsplit(r.url).path == "/api/flow/cases"
            and parse_qs(urlsplit(r.url).query).get("q") == [f["case"]["number"]] and r.request.method == "GET") as pending:
        await e.fill('#filters [name="q"]', f["case"]["number"], "旧销售查询交出原单")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body.get("total") == 0 and body.get("items") == [], "旧销售仍能从原列表读取交出的原单")
    await expect(e.page.locator(f'#main [data-route="case/{f["case"]["id"]}"]')).to_have_count(0)
    async with e.page.expect_response(lambda r: urlsplit(r.url).path == "/api/flow/tasks" and r.request.method == "GET") as pending:
        await e.click('.sidebar a[href="#work"]', "旧销售查看我的工作")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and not any(item["case_id"] == f["case"]["id"] for item in body.get("items", [])), "旧销售仍持有交出原单待办")
    await expect(e.page.locator("#main h1")).to_have_text("我的工作")
    await expect(e.page.locator(f'#main [data-route="case/{f["case"]["id"]}"]')).to_have_count(0)
    e.business_unchanged(before, "original_business_after_old_sales_scope")
    return {"native_case_search_total": 0, "native_my_work_contains_case": False, "business_unchanged": True}


async def sales_presales(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        fixture = e.manifest["business_fixtures"]["presales"]
        store_id = fixture["store_id"]
        keys = {role: fixture[role + "_key"] for role in ("reception", "manager", "sales", "sales_peer")}
        users = {role: e.manifest["users"][key] for role, key in keys.items()}
        require(users["sales"]["id"] != users["sales_peer"]["id"], "交接必须有两个真实不同销售")
        for role, user in users.items():
            expected = "sales" if role == "sales_peer" else role
            require(user["role"] == expected, "售前夹具岗位与原表单合同不一致")
        counts_before = e.db.counts()
        unique = uuid.uuid4().hex[:10]
        customer_name = "浏览器接待" + unique
        customer_phone = "138" + str(int(unique, 16) % 100000000).zfill(8)

        checkpoint.start("HK-001")
        await login_as(e, context, credentials, keys["reception"], "cases/lead", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("售前接待")
        before_create = e.business_snapshot("original_business_before_create_form")
        await e.click('[data-act="newcase"][data-kind="lead"]', "新建售前接待")
        await expect(e.page.locator("#modal-title")).to_have_text("新建售前接待")
        await e.fill('#modal [name="customer_name"]', customer_name, "接待客户姓名")
        require(await e.page.locator('#modal [name="customer_phone"]').input_value() == "", "本场景需要真实缺电话前置")
        e.action("select", "接待来源", value="展厅到店")
        await e.page.locator('#modal [name="source"]').select_option(label="展厅到店")
        e.business_unchanged(before_create, "original_business_before_create_confirm")
        created, create_api, _ = await native_submit(e, "/api/flow/cases", 201)
        case_id = created["id"]
        initial = facts(e, case_id)
        case = initial["case"]
        require(case["kind"] == "lead" and case["state"] == "unassigned" and case["flow_version"] == 2, "原新增接待状态/流程版本错误")
        require(case["store_id"] == store_id and case["owner_id"] == case["created_by"] == users["reception"]["id"], "原新增接待身份/门店错误")
        require(case["data"]["source"] == "展厅到店" and initial["customer"]["name"] == customer_name and initial["customer"]["phone"] == "", "原接待输入事实不一致")
        require(initial["customer"]["contact_allowed"] == 1, "原新客户不允许联系，不能继续假造回访")
        assignment = task(initial, "assign")
        require(assignment["role"] == "reception" and assignment["store_id"] == store_id, "原分派任务岗位/门店错误")
        require(len(initial["events"]) == 1 and initial["events"][0]["action"] == "create" and initial["events"][0]["actor_id"] == users["reception"]["id"], "原创建事件不匹配")
        require(e.db.counts()["flow_cases"] == counts_before["flow_cases"] + 1 and e.db.counts()["flow_customers"] == counts_before["flow_customers"] + 1, "原新建没有恰好建立一张接待和一个客户")
        await rendered_case(e, initial)
        await checkpoint.passed({"native_api": create_api, "db": initial, "initial_assign_assignee_id": assignment["assignee_id"]})

        checkpoint.start("HK-002")
        await login_as(e, context, credentials, keys["manager"], f"case/{case_id}", store_id)
        await rendered_case(e, initial)
        unresolved_before = e.business_snapshot("business_before_unselected_employee")
        assign_path = f"/api/flow/cases/{case_id}/actions/assign"
        post_count = sum(item.get("event") == "request" and item.get("method") == "POST"
                         and item.get("path") == assign_path for item in e.network)
        query = '#modal .lookup[data-kind="employee"] [data-lookup-query]'
        unresolved_validation = []
        for width in (390, 768, 1440):
            await e.page.set_viewport_size({"width": width, "height": 1000})
            e.action("viewport", "核对展开候选时的原生提交", width=width, height=1000)
            await action_form(e, "assign", "分派接待")
            await expect(e.page.locator("#modal .formerror")).to_have_text("")
            await e.fill(query, users["sales"]["display_name"], "只输入姓名，尚未选择接手员工")
            await expect(e.page.locator('#modal select[name="assignee_id"]')).to_have_value("")
            await expect(e.page.locator("#modal .wfx-progress")).to_have_text("还有 1 项必填")
            await expect(e.page.locator('#modal .lookup [role="option"]').filter(has_text=users["sales"]["display_name"]).first).to_be_visible()
            await e.click('#modal form button[type="submit"]', "实际鼠标核对未选候选不能分派")
            await expect(e.page.locator("#modal .formerror")).to_contain_text("请从列表中选择")
            await expect(e.page.locator("#modal")).to_be_visible()
            validation = await e.page.locator(query).evaluate("el => ({customError:el.validity.customError,message:el.validationMessage})")
            require(validation["customError"], "未选候选没有原生校验拒绝")
            require(post_count == sum(item.get("event") == "request" and item.get("method") == "POST"
                                     and item.get("path") == assign_path for item in e.network), "未选候选仍向原分派提交")
            require(facts(e, case_id) == initial, "未选候选的拒绝改写原单、客户或任务")
            e.business_unchanged(unresolved_before, f"business_after_unselected_employee_{width}")
            unresolved_validation.append({"width": width, "native_pointer_submit": True, **validation})
            await e.snapshot(f"unselected-employee-refused-{width}")
            if width != 1440:
                await e.click('#modal form [data-act="close"]', "取消未提交的填写")
                await expect(e.page.locator('#modal [data-wfx-discard]')).to_be_visible()
                await e.click('#modal [data-wfx-discard]', "明确放弃未提交的填写")
                await expect(e.page.locator("#modal")).not_to_be_visible()
        await employee_choice(e, users["sales"])
        await expect(e.page.locator("#modal .wfx-progress")).to_have_text("已填完整")
        await e.fill(query, users["sales_peer"]["display_name"], "修改搜索文字使原员工选择失效")
        await expect(e.page.locator('#modal select[name="assignee_id"]')).to_have_value("")
        await expect(e.page.locator("#modal .wfx-progress")).to_have_text("还有 1 项必填")
        await employee_choice(e, users["sales"])
        await expect(e.page.locator("#modal .wfx-progress")).to_have_text("已填完整")
        _, assign_api, _ = await native_submit(e, f"/api/flow/cases/{case_id}/actions/assign", 200, case_id=case_id)
        assigned = facts(e, case_id)
        same_original(initial, assigned)
        assign_event = new_event(initial, assigned, "assign", users["manager"]["id"])
        require(assign_api["submitted_version"] == initial["case"]["version"], "原分派未携带实际原单版本")
        require(assigned["case"]["state"] == "contacting" and assigned["case"]["owner_id"] == assigned["customer"]["owner_id"] == users["sales"]["id"], "接待/客户负责人未真实分派给所选销售")
        require(task(assigned, "assign", "done")["done_by"] == users["manager"]["id"] and task(assigned, "contact")["assignee_id"] == users["sales"]["id"], "原分派任务未结束或后继 contact 负责人错误")
        require(assign_event["detail"]["assignee_id"] == users["sales"]["id"] and assigned["case"]["version"] > initial["case"]["version"], "原分派留痕/版本错误")
        await rendered_case(e, assigned)
        await checkpoint.passed({"native_api": assign_api, "unselected_employee_validation": unresolved_validation,
                                 "unselected_employee_posts": 0, "edited_selection_cleared": True, "db": assigned})

        checkpoint.start("HK-006")
        await login_as(e, context, credentials, keys["sales"], f"case/{case_id}", store_id)
        await rendered_case(e, assigned)
        await action_form(e, "remind", "安排接待回访")
        today = await e.page.locator('#modal [name="due_date"]').get_attribute("min")
        require(today == assigned["case"]["business_date"], "前端今日日期与本次原单业务日期不一致")
        date.fromisoformat(today)
        await e.fill('#modal [name="due_date"]', today, "今日接待回访日期")
        reception_result = "客户计划本周看车，先电话确认到店时间。"
        await e.fill('#modal [name="result"]', reception_result, "实际合成接待沟通结果")
        await expect(e.page.locator('#modal [name="customer_phone"]')).to_have_attribute("required", "")
        before_missing = e.business_snapshot("original_business_before_missing_phone_submit")
        writes = []
        def observe_write(request):
            if request.method == "POST" and urlsplit(request.url).path == f"/api/flow/cases/{case_id}/actions/remind":
                writes.append(urlsplit(request.url).path)
        e.page.on("request", observe_write)
        try:
            await e.click('#modal form button[type="submit"]', "缺电话时尝试原回访提交")
            await expect(e.page.locator('#modal [name="customer_phone"]:invalid')).to_be_visible()
            require(writes == [], "缺电话必填校验未阻止业务 POST")
            e.business_unchanged(before_missing, "original_business_after_missing_phone_block")
            validation = await e.page.locator('#modal [name="customer_phone"]').evaluate("el => ({valueMissing: el.validity.valueMissing, message: el.validationMessage})")
            require(validation["valueMissing"] is True and bool(validation["message"]), "缺电话未呈现原浏览器必填提示")
        finally:
            e.page.remove_listener("request", observe_write)
        await e.fill('#modal [name="customer_phone"]', customer_phone, "由员工明确补充合成联系电话")
        _, remind_api, _ = await native_submit(e, f"/api/flow/cases/{case_id}/actions/remind", 200, case_id=case_id)
        reminded = facts(e, case_id)
        same_original(assigned, reminded)
        remind_event = new_event(assigned, reminded, "remind", users["sales"]["id"])
        require(remind_api["submitted_version"] == assigned["case"]["version"], "原回访未携带实际原单版本")
        contact = task(reminded, "contact")
        require(reminded["case"]["state"] == "reminder" and reminded["case"]["due_date"] == contact["due_date"] == today and contact["assignee_id"] == users["sales"]["id"], "回访原状态、期限或负责人不匹配")
        require(reminded["customer"]["phone"] == customer_phone and remind_event["detail"]["result"] == reception_result and remind_event["detail"]["due_date"] == today, "原回访电话/沟通事实错误")
        await rendered_case(e, reminded)
        reception_reminder = await due_work(e, reminded, "contact")
        await checkpoint.passed({"missing_phone_validation": validation, "missing_phone_post_count": len(writes), "native_api": remind_api, "native_reminder": reception_reminder, "db": reminded})

        checkpoint.start("HK-003")
        await action_form(e, "intent", "转意向客户")
        intent_due = (date.fromisoformat(today) + timedelta(days=2)).isoformat()
        need = "比较家用车型，核对后再决定预订；当前只登记意向。"
        await e.fill('#modal [name="need"]', need, "合成购车需求")
        await e.fill('#modal [name="due_date"]', intent_due, "意向下次日期")
        _, intent_api, _ = await native_submit(e, f"/api/flow/cases/{case_id}/actions/intent", 200, case_id=case_id)
        intended = facts(e, case_id)
        same_original(reminded, intended)
        intent_event = new_event(reminded, intended, "intent", users["sales"]["id"])
        require(intent_api["submitted_version"] == reminded["case"]["version"], "原转意向未携带实际原单版本")
        follow = task(intended, "follow")
        require(intended["case"]["state"] == "intent" and intended["case"]["data"]["need"] == need and intended["case"]["due_date"] == follow["due_date"] == intent_due, "原意向、购车需求或任务日期不匹配")
        require(follow["assignee_id"] == users["sales"]["id"] and task(intended, "contact", "cancelled")["done_by"] == users["sales"]["id"] and intent_event["detail"]["need"] == need, "原意向转换未结束接待任务或接手事实错误")
        await rendered_case(e, intended)
        await expect(e.page.locator("#main")).to_contain_text(need)
        await checkpoint.passed({"native_api": intent_api, "db": intended})

        checkpoint.start("HK-004")
        await login_as(e, context, credentials, keys["manager"], f"case/{case_id}", store_id)
        await rendered_case(e, intended)
        await e.click(f'#main [data-act="assign"][data-id="{follow["id"]}"]', "主管转交原意向任务")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, users["sales_peer"])
        reason = "原销售交接，由销售乙接续同一客户意向。"
        await e.fill('#modal [name="reason"]', reason, "原意向交接说明")
        _, reassign_api, _ = await native_submit(e, f'/api/flow/tasks/{follow["id"]}/assign', 200, case_id=case_id)
        reassigned = facts(e, case_id)
        same_original(intended, reassigned)
        reassign_event = new_event(intended, reassigned, "reassign", users["manager"]["id"])
        require(reassign_api["submitted_version"] == follow["version"], "原转交未携带实际原任务版本")
        peer_task = task(reassigned, "follow")
        require(peer_task["id"] == follow["id"] and peer_task["version"] > follow["version"] and peer_task["due_date"] == intent_due, "原意向任务被另建、未版本更新或期限被改")
        require(peer_task["assignee_id"] == reassigned["case"]["owner_id"] == reassigned["customer"]["owner_id"] == users["sales_peer"]["id"], "原 Task/Case/Customer 负责人没有一致转交")
        require(reassign_event["detail"] == {"task_id": follow["id"], "from": users["sales"]["id"], "to": users["sales_peer"]["id"], "reason": reason}, "原转交事件未保留准确前后员工和原因")
        await rendered_case(e, reassigned)
        await login_as(e, context, credentials, keys["sales"], "cases/lead", store_id)
        old_scope = await old_sales_scope(e, reassigned)
        await login_as(e, context, credentials, keys["sales_peer"], f"case/{case_id}", store_id)
        await rendered_case(e, reassigned)
        await expect(e.page.locator('#main [data-act="caseaction"][data-key="follow"]')).to_be_enabled()
        await checkpoint.passed({"native_api": reassign_api, "old_sales_native_scope": old_scope, "db": reassigned})

        checkpoint.start("HK-005")
        follow_results = ["第一次意向跟进：已介绍车型，客户需要与家人讨论。", "第二次意向跟进：已补充配置说明，今天继续核对客户决定。"]
        previous = reassigned
        follow_evidence = []
        for result, due in zip(follow_results, ((date.fromisoformat(today) + timedelta(days=1)).isoformat(), today)):
            await action_form(e, "follow", "记录意向跟进")
            await e.fill('#modal [name="result"]', result, "追加独立意向沟通结果")
            await e.fill('#modal [name="due_date"]', due, "原意向下次日期")
            _, response_meta, _ = await native_submit(e, f"/api/flow/cases/{case_id}/actions/follow", 200, case_id=case_id)
            current = facts(e, case_id)
            same_original(previous, current)
            event = new_event(previous, current, "follow", users["sales_peer"]["id"])
            require(response_meta["submitted_version"] == previous["case"]["version"], "原跟进未携带实际原单版本")
            current_task = task(current, "follow")
            require(event["detail"]["result"] == result and event["detail"]["due_date"] == due, "原跟进事件未准确记录本次沟通和日期")
            require(current["case"]["state"] == "intent" and current["case"]["due_date"] == current_task["due_date"] == due and current_task["id"] == peer_task["id"] and current_task["assignee_id"] == users["sales_peer"]["id"], "原跟进未保持同一意向和唯一任务期限")
            require(current["case"]["version"] > previous["case"]["version"] and current_task["version"] > task(previous, "follow")["version"], "原跟进版本未更新")
            await rendered_case(e, current)
            follow_evidence.append({"native_api": response_meta, "event": event, "task": current_task})
            previous = current
        followed = previous
        actual_history = [row for row in followed["events"] if row["action"] == "follow"]
        require(len(actual_history) == 2 and [row["detail"]["result"] for row in actual_history] == follow_results, "两次意向沟通历史被覆盖、遗漏或重复")
        counts_after = e.db.counts()
        require(counts_after["flow_cases"] == counts_before["flow_cases"] + 1 and counts_after["flow_customers"] == counts_before["flow_customers"] + 1, "跟进期间另建客户或接待")
        history_items = e.page.locator('#main [data-panel-role="history"] .timelineitem').filter(has_text="记录意向跟进")
        await expect(history_items).to_have_count(2)
        outer_selector = '#main details.ux-history:has([data-panel-role="history"])'
        await expect(e.page.locator(outer_selector + ' > summary')).to_have_text("操作留痕")
        await e.click(outer_selector + ' > summary', "打开操作留痕")
        await expect(e.page.locator(outer_selector)).to_have_attribute("open", "")
        for result in follow_results:
            # Both history and each original event are folded. Keep the event
            # locator tied to its distinct communication result, not its index.
            item = history_items.filter(has_text=result)
            await expect(item).to_have_count(1)
            summary = item.locator("summary")
            await expect(summary).to_have_count(1)
            await expect(summary).to_be_visible()
            e.action("click", "展开原意向跟进留痕", communication_result=result)
            await summary.click()
        for result in follow_results:
            await expect(e.page.locator('#main [data-panel-role="history"]').get_by_text(result, exact=True)).to_be_visible()
        await checkpoint.passed({"native_follow_submissions": follow_evidence, "new_case_count": 1, "new_customer_count": 1, "db": followed})

        checkpoint.start("HK-007")
        intent_reminder = await due_work(e, followed, "follow")
        await expect(e.page.locator('#main [data-act="caseaction"][data-key="follow"]')).to_be_enabled()
        await action_form(e, "follow", "记录意向跟进")
        reminder_result = "按今日提醒再次联系，客户计划明日回复，已安排明日继续跟进。"
        next_due = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
        await e.fill('#modal [name="result"]', reminder_result, "实际办理今日意向提醒的沟通结果")
        await e.fill('#modal [name="due_date"]', next_due, "本次提醒办理后的明日日期")
        _, reminder_api, _ = await native_submit(e, f"/api/flow/cases/{case_id}/actions/follow", 200, case_id=case_id)
        processed = facts(e, case_id)
        same_original(followed, processed)
        reminder_event = new_event(followed, processed, "follow", users["sales_peer"]["id"])
        processed_task = task(processed, "follow")
        require(reminder_api["submitted_version"] == followed["case"]["version"], "提醒办理未携带原单当前版本")
        require(reminder_event["detail"]["result"] == reminder_result and reminder_event["detail"]["due_date"] == next_due, "原提醒办理没有追加实际沟通和下次日期")
        require(processed["case"]["state"] == "intent" and processed["case"]["due_date"] == processed_task["due_date"] == next_due and processed_task["id"] == task(followed, "follow")["id"] and processed_task["assignee_id"] == users["sales_peer"]["id"], "今日提醒办理没有延续同一原意向和跟进任务")
        await rendered_case(e, processed)
        before_refresh = e.business_snapshot("original_business_before_final_refresh")
        async with e.page.expect_response(lambda r: urlsplit(r.url).path == f"/api/flow/cases/{case_id}" and r.request.method == "GET") as pending:
            await e.click('#main [data-act="refresh"]', "刷新原意向核对提醒不重复")
        response = await pending.value
        require(response.status == 200, "原意向刷新真实读取失败")
        await response.body()
        final = facts(e, case_id)
        require(final == processed, "提醒办理后的刷新改写原业务")
        require(len([row for row in final["tasks"] if row["key"] == "follow" and row["status"] == "open"]) == 1, "提醒刷新重复建立 follow 任务")
        await rendered_case(e, final)
        e.business_unchanged(before_refresh, "original_business_after_final_refresh")
        require(e.db.counts()["flow_cases"] == counts_before["flow_cases"] + 1 and e.db.counts()["flow_customers"] == counts_before["flow_customers"] + 1, "提醒办理另建原单或客户")
        await checkpoint.passed({"native_reminder": intent_reminder, "native_reminder_follow_submission": reminder_api, "reminder_follow_event": reminder_event, "refresh_status": 200, "open_follow_count": 1, "db": final})
        checkpoint.finish()
    except Exception as error:
        checkpoint.failed(error)
        raise


BUSINESS_SCENARIOS = ((SCENARIO, sales_presales, 240),)
