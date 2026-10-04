"""Original UI procurement inputs, independent approval, cash and VIN receipts.

The registered runner supplies Evidence and isolated credentials. Business facts
are produced only by visible original forms. Database access remains SELECT-only.
Synthetic input files live in the external evidence directory and are uploaded
through the original file picker; structure checks are not antivirus acceptance.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, new_event, require


SCENARIO = "vehicle-purchase-hk171-177-178-026-021-018-029"
REQUIREMENTS = (
    ("HK-171", "供应商设置", ("原供应商搜索、新增及修改已知联系人", "代码、名称、联系方式、账期与原数据库及列表一致")),
    ("HK-177", "品牌车系车型", ("原单表明确新增品牌车系及车型，再明确选已有品牌车系保存另一车型", "层级、年款、动力、座位及整数参数同事务一致")),
    ("HK-178", "整车仓库", ("原管理表新增整车专用仓与真实库位，配置不增加车辆", "实际采购验收引用本店启用仓及库位")),
    ("HK-026", "采购计划管理", ("库管原计划填写两条已知车型、颜色、台数及日期", "独立主管上传依据、逐行核价及请款，未发运验收不增加车辆")),
    ("HK-021", "车辆采购入库", ("财务原凭据登记付款，预付与实车验收分别产生原事实", "库管逐VIN发运及现场重新核对后验收，成本、代次、位置及不可覆盖流水一致", "错误现场VIN被拒绝，刷新不重复记款或收车")),
    ("HK-018", "所有车辆品牌型号筛参数选展示专题页", ("品牌、车系、动力、座位、价格及名称组合筛选非空本店车型", "实际展开原入库VIN，参数及数量与API和数据库一致，查询零业务写入")),
    ("HK-029", "车辆库存查询", ("原车辆列表显示本轮VIN、位置、库存及审核状态", "Vehicle、Position、Custody及真实来源一致；无占用源时不宣称占用分支通过")),
)
PURCHASE_TABLES = {
    "lines": "vehicle_purchase_lines", "prices": "vehicle_purchase_prices",
    "shipments": "vehicle_purchase_shipments", "receipts": "vehicle_purchase_receipts",
    "funds": "vehicle_purchase_funds_requests", "payments": "vehicle_purchase_payments",
    "movements": "vehicle_purchase_movements",
}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        source = Path(__file__).with_name("business_acceptance_catalog.json")
        require(source.is_file(), "本轮逐项业务源目录未随脚本镜像")
        contents = source.read_bytes()
        catalogue = json.loads(contents)
        bindings = {row["id"]: row for row in catalogue["requirements"]}
        for key, _, _ in REQUIREMENTS:
            row = bindings.get(key)
            require(row is not None and row["source_review_status"] == "source_reviewed", key + " 尚未核准原源合同")
            require(any(check["check_id"] == key + "-business" for check in row["acceptance_checks"]), key + " 目录 check_id 不匹配")
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in REQUIREMENTS],
            "complete": False, "passed": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": hashlib.sha256(contents).hexdigest(),
            "conditions": {"synthetic_money_and_physical_inputs": True,
                           "production_bank_or_physical_handover_acceptance": False,
                           "file_scan": "original_structure_only_not_clamav",
                           "business_entity_policy_acceptance": False},
            "requirements": [{
                "id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                    "status": "not_tested", "criteria": list(criteria), "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "conditional_checks": [],
            } for key, title, criteria in REQUIREMENTS],
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(row for row in self.report["requirements"] if row["id"] == key)
        self.active["status"] = "running"
        self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    async def passed(self, evidence, *, conditional=()):
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = "passed"
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        self.active["conditional_checks"] = list(conditional)
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.active["evidence_action_end"] = len(self.e.actions)
            self.report["failed_requirement"] = self.active["id"]
        for row in self.report["requirements"]:
            if row["status"] == "running":
                reason = "已完成部分原UI事实；后续依赖步骤未完成，场景失败后终止。"
                row["status"] = "partial"
                row["acceptance_checks"][0].update(status="partial", incomplete_reason=reason)
                row["evidence_action_end"] = len(self.e.actions)
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self):
        require(all(row["status"] == "passed" for row in self.report["requirements"]), "本轮采购原链未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=7, passed_requirements=7,
                           human_acceptance="pending", conditional_coverage_complete=False)
        self.save()
        self.e.observe("vehicle_purchase_business_checkpoint", {"path": str(self.path), "requirements": 7,
                                                                "passed": 7, "business_accepted": False})


def purchase_facts(e, case_id):
    original = e.db.rows("SELECT id,number,kind,state,flow_version,store_id,title,owner_id,created_by,"
                         "version,business_date,due_date,amount_cents,completed_date FROM flow_cases WHERE id=?", (case_id,))
    require(len(original) == 1, "原采购单不存在或不唯一")
    result = {"case": original[0], "order": e.db.rows("SELECT * FROM vehicle_purchase_orders WHERE id=?", (case_id,))[0]}
    for key, table in PURCHASE_TABLES.items():
        result[key] = e.db.rows(f"SELECT * FROM {table} WHERE case_id=? ORDER BY id", (case_id,))
    result["tasks"] = e.db.rows("SELECT id,case_id,store_id,key,title,role,assignee_id,status,due_date,version,"
                                "done_by,done_at FROM flow_tasks WHERE case_id=? ORDER BY id", (case_id,))
    result["events"] = e.db.rows("SELECT id,case_id,store_id,actor_id,action,label,before_state,after_state,"
                                 "detail FROM flow_events WHERE case_id=? ORDER BY id", (case_id,))
    for event in result["events"]:
        event["detail"] = json.loads(event["detail"])
    return result


def open_task(f, key):
    tasks = [t for t in f["tasks"] if t["key"] == key and t["status"] == "open"]
    require(len(tasks) == 1, "原采购 " + key + " 待办不唯一或已结束")
    return tasks[0]


def command_facts(before, after, action, user):
    for field in ("id", "number", "kind", "flow_version", "store_id", "created_by", "business_date", "due_date"):
        require(before["case"][field] == after["case"][field], "采购原事实被替换：" + field)
    require(after["case"]["version"] > before["case"]["version"], "原采购业务版本未前进")
    require(before["order"] == after["order"] and before["lines"] == after["lines"], "原采购约定被覆盖")
    for key in ("prices", "payments", "receipts", "movements"):
        require(after[key][:len(before[key])] == before[key], "不可覆盖的原 " + key + " 被改写")
    return new_event(before, after, "vp_" + action, user["id"])


async def select_value(e, selector, value, label):
    target = e.page.locator(selector)
    await expect(target).to_have_count(1)
    await expect(target).to_be_visible()
    e.action("select", label, value=str(value))
    await target.select_option(str(value))
    await expect(target).to_have_value(str(value))


async def checkbox(e, selector, checked, label):
    target = e.page.locator(selector)
    await expect(target).to_have_count(1)
    await expect(target).to_be_visible()
    e.action("check" if checked else "uncheck", label)
    await target.set_checked(checked)
    if checked:
        await expect(target).to_be_checked()
    else:
        await expect(target).not_to_be_checked()


async def response_meta(e, response, body, *, json_contract=True):
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token")), "原表单缺 Cookie 或 CSRF")
    require(headers.get("x-store-id") == str(e.manifest["business_fixtures"]["vehicle_purchase"]["store_id"]), "采购原表单门店不匹配")
    request = response.request.post_data_json if json_contract else None
    metadata = {"path": urlsplit(response.url).path, "method": response.request.method,
                "status": response.status, "native_ui": True, "cookie_present": True, "csrf_present": True,
                "submitted_version": request.get("version") if request else None,
                "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request and request.get("request_id") else None,
                "response_id": body.get("id"), "response_version": body.get("version")}
    e.observe("original_vehicle_form_response", metadata)
    return metadata, request


async def submit(e, path, status, render_path, *, method="POST", json_contract=True):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == render_path) as rendered:
        async with e.page.expect_response(lambda r: r.request.method == method and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "提交原采购或主档表单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原表单返回 HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await rendered.value
    read_body = await read.json()
    require(read.status == 200, "原表单成功后的原页面读取失败")
    metadata, request = await response_meta(e, response, body, json_contract=json_contract)
    metadata.update(render_get_path=render_path, render_get_status=read.status)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return body, metadata, read_body, request


async def rejected_submit(e, path, status, text, *, method="POST"):
    before = e.business_snapshot("original_before_rejected_vehicle_form")
    async with e.page.expect_response(lambda r: r.request.method == method and urlsplit(r.url).path == path) as pending:
        await e.click('#modal form button[type="submit"]', "提交员工已核对的拒绝边界")
    response = await pending.value
    body = await response.json()
    require(response.status == status and text in str(body.get("detail", "")), "原拒绝状态或真实 refusal 不匹配")
    await expect(e.page.locator("#modal .formerror")).to_contain_text(text)
    e.business_unchanged(before, "original_after_rejected_vehicle_form")
    metadata, _ = await response_meta(e, response, body)
    metadata.update(detail=e.scrub(body["detail"]), business_unchanged=True)
    e.observe("original_vehicle_refusal", metadata)
    await e.snapshot("protected-original-vehicle-refusal")
    await expect(e.page.locator("#modal form")).not_to_have_attribute("aria-busy", "true")
    await e.click('#modal .modalhead [data-act="close"]', "取消被拒绝的原表单后重新核对")
    await expect(e.page.locator("#modal .wfx-discard")).to_be_visible()
    await expect(e.page.locator("#modal .wfx-discard strong")).to_have_text("还有未保存的填写内容")
    await e.click('#modal [data-wfx-discard]', "明确放弃被拒绝表单的填写")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "original_after_rejected_vehicle_form_discard")
    metadata.update(explicit_discard=True, discard_business_unchanged=True)
    e.observe("original_vehicle_refusal_discard", metadata)
    return metadata


async def nav(e, route, title, path):
    # The original statistics entry now opens charts and a retained report directory.
    analytics = route == "module/analytics"
    if analytics:
        route, title = "analytics/overview", "数据可视化"
    sidebar = e.page.locator(".sidebar")
    if not await sidebar.is_visible():
        await e.click('[data-act="menu"]', "打开原窄屏业务导航")
        await expect(sidebar).to_be_visible()
    link = e.page.locator('.sidebar a[href="#' + route + '"]')
    await expect(link).to_have_count(1)
    parent = link.locator("xpath=ancestor::details[1]")
    if await parent.count() and await parent.get_attribute("open") is None:
        e.action("click", "展开原业务导航", route=route)
        await parent.locator(":scope > summary").click()
    before = e.business_snapshot("original_before_vehicle_navigation")
    data = None
    if path is None:
        # The original master directory legitimately uses its native cache.
        e.action("click", "打开原业务页面", route=route)
        await link.click()
    else:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            e.action("click", "打开原业务页面", route=route)
            await link.click()
        response = await pending.value
        data = await response.json()
        require(response.status == 200, "原业务页面读取失败")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    if analytics:
        await expect(e.page.locator("#main > .loading")).to_have_count(0)
        directory = e.page.locator(".analytics-report-directory")
        await expect(directory).to_have_count(1)
        if await directory.get_attribute("open") is None:
            await e.click('.analytics-report-directory > summary', "展开数据可视化内的报表与专题")
        await expect(e.page.locator("#mux-query")).to_be_visible()
    e.business_unchanged(before, "original_after_vehicle_navigation")
    return data


async def master_page(e, kind, title):
    await nav(e, "masters", "基础资料", None)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/masters/" + kind) as pending:
        await e.click(f'#main [data-act="open"][data-route="masters/{kind}"]', "查找已有" + title)
    response = await pending.value
    require(response.status == 200, "原主档页面读取失败")
    await response.body()
    await expect(e.page.locator("#main h1")).to_have_text(title)


async def master_form(e, kind, title, record_id=None):
    selector = f'#main [data-act="typed-edit"][data-kind="{kind}"][data-id="{record_id}"]' if record_id else f'#main [data-act="typed-new"][data-kind="{kind}"]'
    await e.click(selector, ("编辑" if record_id else "新增") + title)
    await expect(e.page.locator("#modal-title")).to_have_text(("编辑" if record_id else "新增") + title)


def master_row(e, kind, record_id):
    names = {"suppliers": "master_suppliers", "warehouses": "master_warehouses", "locations": "master_locations"}
    rows = e.db.rows(f"SELECT * FROM {names[kind]} WHERE id=?", (record_id,))
    require(len(rows) == 1, "主档原ID不存在或不唯一")
    return rows[0]


async def save_master(e, kind, values, *, record_id=None):
    for key, value in values.items():
        selector = f'#modal [name="{key}"]'
        if isinstance(value, bool):
            await checkbox(e, selector, value, "明确主档启用状态")
        elif key == "warehouse_type":
            await select_value(e, selector, value, "选择整车仓库用途")
        else:
            await e.fill(selector, str(value), "填写原主档" + key)
    path = "/api/masters/" + kind
    body, meta, listing, request = await submit(e, path + ("/" + str(record_id) if record_id else ""),
                                               200 if record_id else 201, path, method="PUT" if record_id else "POST")
    row = master_row(e, kind, body["id"])
    require(row["store_id"] == e.manifest["business_fixtures"]["vehicle_purchase"]["store_id"], "主档串店")
    for key, value in request["values"].items():
        require(row[key] == value and body[key] == value, "主档 UI/API/DB 字段不一致：" + key)
    visible = next((item for item in listing["items"] if item["id"] == row["id"]), None)
    require(visible is not None, "保存后的原主档列表没有该真实ID")
    for key in ("id", "code", "name", "version", "active"):
        require(visible[key] == row[key], "主档列表与数据库不一致：" + key)
    await expect(e.page.locator("#main tbody tr").filter(has=e.page.locator(f'[data-act="typed-edit"][data-id="{row["id"]}"]'))).to_contain_text(row["name"])
    return row, meta


async def live_choice(e, select_name, search, label, *, expected_value=None):
    root = e.page.locator('#modal .lookup').filter(has=e.page.locator(f'select[name="{select_name}"]'))
    await expect(root).to_have_count(1)
    query = root.locator('[role="combobox"]')
    await expect(query).to_be_visible()
    e.action("fill", "查找明确" + label, value=search)
    await query.fill(search)
    option = root.get_by_role("option", name=label, exact=True)
    await expect(option).to_have_count(1)
    await expect(option).to_be_visible()
    e.action("click", "选择" + label)
    await option.click()
    if expected_value is not None:
        await expect(root.locator("select")).to_have_value(str(expected_value))


async def create_model(e, names, *, parent=None, hybrid=False):
    await e.click('#main [data-act="catalog-entry"]', "新增明确车型层级")
    await expect(e.page.locator("#vehicle-catalog-entry")).to_be_visible()
    if parent:
        await live_choice(e, "brand_id", names["brand"], names["brand"], expected_value=parent["brand"]["id"])
        await live_choice(e, "series_id", names["series"], names["series"], expected_value=parent["series"]["id"])
    else:
        await live_choice(e, "brand_id", names["brand"], "＋ 新增品牌", expected_value="new")
        await e.fill('#modal [name="brand_name"]', names["brand"], "填写合成新品牌")
        # New-brand selection selects the explicit new-series branch itself.
        await expect(e.page.locator('#modal [name="series_id"]')).to_have_value("new")
        await e.fill('#modal [name="series_name"]', names["series"], "填写合成新车系")
    values = {"name": names["model"], "model_year": "2026", "seats": "7" if hybrid else "5",
              "displacement": "2.0" if hybrid else "1.5", "price": "130000.00" if hybrid else "120000.00"}
    await select_value(e, '#modal [name="fuel_type"]', "hybrid" if hybrid else "petrol", "选择真实动力参数")
    for key, value in values.items():
        await e.fill(f'#modal [name="{key}"]', value, "填写明确车型参数" + key)
    if hybrid:
        await e.fill('#modal [name="battery"]', "20.5", "填写已知混动车型电池容量")
    body, meta, _, request = await submit(e, "/api/vehicle-catalog/entry", 200, "/api/vehicle-catalog")
    for key, table in (("brand", "catalog_vehicle_brands"), ("series", "catalog_vehicle_series"),
                       ("model", "master_vehicle_models"), ("classification", "catalog_model_classifications")):
        row = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (body[key]["id"],))[0]
        require(row["store_id"] == e.manifest["business_fixtures"]["vehicle_purchase"]["store_id"], "车型层级串店")
        for field in (field for field in body[key] if field not in {"created_at", "updated_at"}):
            require(field in row, "原车型响应字段缺数据库来源：" + field)
            require(row[field] == body[key][field], "原车型层级 API/DB 不匹配")
    model = body["model"]
    for field in ("name", "model_year", "fuel_type", "seats", "displacement_ml", "battery_wh", "guide_price_cents"):
        require(model[field] == request[field], "车型整数参数不匹配：" + field)
    require(model["displacement_ml"] == (2000 if hybrid else 1500) and model["battery_wh"] == (20500 if hybrid else 0), "原UI参数换算错误")
    require(body["series"]["brand_id"] == body["brand"]["id"] and body["classification"]["series_id"] == body["series"]["id"]
            and body["classification"]["model_id"] == model["id"], "车型原层级关系错误")
    require(body["created"]["model"] is True, "本轮明确新增车型没有产生原结果")
    if parent:
        require(body["created"]["brand"] is False and body["created"]["series"] is False, "已有品牌车系被重复新建")
        require(request["brand_id"] == parent["brand"]["id"] and request["brand_version"] == parent["brand"]["version"]
                and request["series_id"] == parent["series"]["id"] and request["series_version"] == parent["series"]["version"], "已有层级缺真实ID/version")
    else:
        require(body["created"]["brand"] is True and body["created"]["series"] is True, "新层级原事务结果缺失")
    await expect(e.page.locator("#main")).to_contain_text(model["name"])
    return body, meta


async def detail_as(e, context, credentials, role, case_id, store_id):
    path = f"/api/vehicle-procurement/orders/{case_id}"
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        user = await login_as(e, context, credentials, role, f"vehicle-procurement/{case_id}", store_id)
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == case_id and body["store_id"] == store_id, "原采购详情串单/串店或无权读取")
    await expect(e.page.locator("#main h1")).to_have_text("整车采购办理")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(body["number"])
    if user["role"] == "inventory":
        require("totals" not in body and not body["payments"] and not body["funds_requests"]
                and all("unit_cost_cents" not in row for row in body["lines"]), "原库管详情泄漏财务字段")
        await expect(e.page.locator('#main [data-key="approve"], #main [data-key="pay"]')).to_have_count(0)
    if user["role"] == "finance":
        await expect(e.page.locator('#main [data-key="ship"], #main [data-key="receive"]')).to_have_count(0)
    return user, body


async def responsible(e, context, credentials, fixture, case_id, task_key, role):
    original = open_task(purchase_facts(e, case_id), task_key)
    selected = e.manifest["users"][fixture[role + "_key"]]
    evidence = {"task_id": original["id"], "task_key": task_key, "assignee_id": selected["id"], "handoff_needed": original["assignee_id"] != selected["id"]}
    if evidence["handoff_needed"]:
        await login_as(e, context, credentials, fixture["manager_key"], f"case/{case_id}", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text(purchase_facts(e, case_id)["case"]["title"])
        await e.click(f'#main [data-act="assign"][data-id="{original["id"]}"]', "主管按真实待办转交可登录员工")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, selected)
        await e.fill('#modal [name="reason"]', "本次合成原采购由已选择的本店员工独立经办", "填写实际任务交接说明")
        _, meta, _, request = await submit(e, f'/api/flow/tasks/{original["id"]}/assign', 200, f"/api/flow/cases/{case_id}")
        require(request["version"] == original["version"] and request["assignee_id"] == selected["id"], "原任务交接缺实际版本或员工ID")
        after = open_task(purchase_facts(e, case_id), task_key)
        require(after["id"] == original["id"] and after["assignee_id"] == selected["id"] and after["version"] > original["version"], "原采购待办交接失败")
        evidence["native_handoff"] = meta
    user, body = await detail_as(e, context, credentials, fixture[role + "_key"], case_id, fixture["store_id"])
    require(open_task(purchase_facts(e, case_id), task_key)["assignee_id"] == user["id"], "真实经办员工不是原待办负责人")
    e.observe("original_purchase_task_owner", evidence)
    return user, body, evidence


async def upload(e, case_id, actor, category, filename, text):
    inputs = e.directory / "synthetic-inputs"
    inputs.mkdir(exist_ok=True)
    path = inputs / filename
    content = ("合成浏览器验收资料；不表示真实公司款项或实物已发生。\n" + text + "\n").encode("utf-8")
    path.write_bytes(content)
    await e.click('#main [data-act="upload"]', "选择并上传本单明确合成凭据")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "明确原附件类别")
    e.action("select_file", "员工选择外部合成凭据", filename=filename, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal input[name="file"]').set_input_files(str(path))
    body, meta, original, _ = await submit(e, f"/api/flow/cases/{case_id}/files", 200,
                                          f"/api/flow/cases/{case_id}", json_contract=False)
    files = e.db.rows("SELECT id,case_id,store_id,category,name,sha256,size,created_by,generated FROM flow_files WHERE id=?", (body["id"],))
    require(len(files) == 1, "原上传未产生唯一附件")
    row = files[0]
    require(row["case_id"] == case_id and row["category"] == category and row["created_by"] == actor["id"]
            and row["name"] == filename and row["sha256"] == hashlib.sha256(content).hexdigest()
            and row["size"] == len(content) and not row["generated"], "原上传内容/类别/来源不一致")
    scans = e.db.rows("SELECT file_id,actor_id,action,state,engine,sha256,size FROM file_scan_events WHERE file_id=? ORDER BY id", (row["id"],))
    security = e.db.rows("SELECT file_id,state FROM file_security WHERE file_id=?", (row["id"],))
    require(len(scans) == 1 and len(security) == 1 and security[0]["state"] == scans[0]["state"] == "structure_only"
            and scans[0]["actor_id"] == actor["id"] and scans[0]["action"] == "initial"
            and scans[0]["sha256"] == row["sha256"] and scans[0]["size"] == row["size"], "原结构扫描来源不匹配")
    shown = next((f for f in original["files"] if f["id"] == row["id"]), None)
    require(shown is not None and shown["security"]["can_use"] is True, "原文件未通过当前隔离结构检查或不可用于原业务")
    await expect(e.page.locator("#main .filerecord").filter(has_text=filename)).to_contain_text(shown["security"]["label"])
    e.observe("original_uploaded_synthetic_evidence", {"file": row, "scan": scans[0], "native": meta,
                                                       "clamav_acceptance": False})
    return row["id"]


async def action_form(e, key):
    selector = f'#main [data-act="vp-action"][data-key="{key}"]'
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "办理原采购步骤 " + key)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def purchase_command(e, case_id, key, actor, fills, selects=()):
    before = purchase_facts(e, case_id)
    await action_form(e, key)
    for field, value in fills.items():
        await e.fill(f'#modal [name="{field}"]', str(value), "填写员工已知原采购事实 " + field)
    for field, value in selects:
        await select_value(e, f'#modal [name="{field}"]', value, "选择本单原事实 " + field)
    body, meta, _, request = await submit(e, f"/api/vehicle-procurement/orders/{case_id}/actions/{key}", 200,
                                         f"/api/flow/cases/{case_id}")
    require(body["id"] == case_id and request["version"] == before["case"]["version"], "原采购提交串单或版本错误")
    after = purchase_facts(e, case_id)
    event = command_facts(before, after, key, actor)
    require(body["version"] == after["case"]["version"] and body["state"] == after["case"]["state"], "原响应与采购数据库版本/状态不一致")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(after["case"]["number"])
    return body, after, {"native": meta, "event": event, "submitted_values": request["values"]}


def vehicle_fact(e, receipt, shipment, line, price, warehouse, location, actor):
    car = e.db.rows("SELECT id,store_id,vin,inventory_generation,brand,model,color,supplier,location,"
                    "purchase_cost_cents,list_price_cents,approval_state,created_by FROM vehicles WHERE id=?", (receipt["vehicle_id"],))[0]
    position = e.db.rows("SELECT vehicle_id,store_id,location_id,status,version FROM vehicle_positions WHERE vehicle_id=?", (car["id"],))
    custody = e.db.rows("SELECT id,vin,identity_id,current_vehicle_id,current_store_id,generation,pending_transfer_id,version "
                        "FROM vehicle_custodies WHERE vin=?", (car["vin"],))
    entry = e.db.rows("SELECT case_id,vehicle_id,location_id,kind,quantity,inventory_delta,value_cents,evidence_id,actor_id "
                      "FROM vehicle_position_entries WHERE vehicle_id=? ORDER BY id", (car["id"],))
    link = e.db.rows("SELECT identity_id,store_id,local_kind,local_id,confirmed_by FROM group_identity_links "
                     "WHERE local_kind='vehicle' AND local_id=?", (car["id"],))
    require(car["store_id"] == receipt["store_id"] and car["vin"] == shipment["vin"] and car["model"] == line["model_name"]
            and car["color"] == line["color"] and car["brand"] == line["brand"] and car["created_by"] == actor["id"]
            and car["purchase_cost_cents"] == receipt["value_cents"] == price["unit_cost_cents"]
            and car["list_price_cents"] == price["list_price_cents"] and car["approval_state"] == "approved", "实车原采购来源/成本/身份错误")
    require(car["location"] == warehouse["name"] + " / " + location["name"] and receipt["location_id"] == location["id"], "原车辆位置或验收库位错误")
    require(len(position) == len(custody) == len(entry) == len(link) == 1, "原位置/监管/身份/位置流水不唯一")
    require(position[0]["status"] == "stored" and position[0]["location_id"] == location["id"] and position[0]["store_id"] == car["store_id"], "原Position不在实际本店整车库位")
    require(custody[0]["current_vehicle_id"] == car["id"] and custody[0]["current_store_id"] == car["store_id"]
            and custody[0]["generation"] == car["inventory_generation"] == 1 and custody[0]["pending_transfer_id"] is None, "原VIN监管/库存代次不一致")
    require(link[0]["identity_id"] == custody[0]["identity_id"] and link[0]["store_id"] == car["store_id"] and link[0]["confirmed_by"] == actor["id"], "原集团VIN身份关联错误")
    require(entry[0]["case_id"] == receipt["case_id"] and entry[0]["kind"] == "purchase_receive" and entry[0]["quantity"] == 1
            and entry[0]["inventory_delta"] == 0 and entry[0]["value_cents"] == car["purchase_cost_cents"]
            and entry[0]["evidence_id"] == receipt["evidence_id"] and entry[0]["actor_id"] == actor["id"], "原位置流水重复计库存或来源错误")
    return {"vehicle": car, "position": position[0], "custody": custody[0], "position_entry": entry[0], "identity_link": link[0]}


async def catalog_filter(e, model, *, available=True, min_seats=None):
    before = e.business_snapshot("original_before_vehicle_catalog_filter")
    selector = '#vehicle-catalog-filters '
    await e.fill(selector + '[name="q"]', model["model"]["name"], "检索本轮真实车型")
    await select_value(e, selector + '[name="brand_id"]', model["brand"]["id"], "筛选原品牌")
    await select_value(e, selector + '[name="series_id"]', model["series"]["id"], "筛选品牌下原车系")
    await select_value(e, selector + '[name="fuel_type"]', model["model"]["fuel_type"], "筛选明确动力")
    await e.fill(selector + '[name="min_seats"]', str(min_seats or model["model"]["seats"]), "筛选已知最少座位")
    await e.fill(selector + '[name="max_price"]', str(model["model"]["guide_price_cents"] // 100), "按主档指导价筛选")
    await checkbox(e, selector + '[name="available_only"]', available, "明确仅看当前可选配")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/vehicle-catalog"
                                      and parse_qs(urlsplit(r.url).query).get("q") == [model["model"]["name"]]) as pending:
        await e.click(selector + 'button[type="submit"]', "原页面组合筛选车型")
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原车型组合筛选失败")
    params = parse_qs(urlsplit(response.url).query)
    for key, value in (("brand_id", model["brand"]["id"]), ("series_id", model["series"]["id"]),
                       ("fuel_type", model["model"]["fuel_type"]), ("min_seats", min_seats or model["model"]["seats"]),
                       ("max_price_cents", model["model"]["guide_price_cents"])):
        require(params.get(key) == [str(value)], "实际筛选参数不匹配：" + key)
    require(params.get("available_only") == (["true"] if available else None), "原筛选未携带明确可选配条件")
    await expect(e.page.locator("#main h1")).to_have_text("车型目录")
    e.business_unchanged(before, "original_after_vehicle_catalog_filter")
    return body, {"path": urlsplit(response.url).path, "method": "GET", "status": 200, "params": params,
                  "native_ui": True, "business_unchanged": True}


async def vehicle_purchase(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        fixture = e.manifest["business_fixtures"]["vehicle_purchase"]
        store_id = fixture["store_id"]
        token = uuid.uuid4().hex[:10].upper()
        manager = await login_as(e, context, credentials, fixture["manager_key"], "masters/suppliers", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("供应商")
        checkpoint.start("HK-171")
        supplier_values = {"code": "BCS" + token, "name": "合成采购供应商" + token, "active": True,
                           "tax_identifier": "SYNTHETIC" + token, "contact_name": "合成原联系人", "phone": "13800000071", "payment_terms_days": 7}
        before = e.business_snapshot("original_before_supplier_search")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/masters/suppliers"
                                          and parse_qs(urlsplit(r.url).query).get("q") == [supplier_values["name"]]) as pending:
            await e.fill('#filters [name="q"]', supplier_values["name"], "先搜索本轮明确供应商避免重复")
        searched = await (await pending.value).json()
        require(searched["total"] == 0, "本轮唯一输入已存在，不能冒充新建")
        e.business_unchanged(before, "original_after_supplier_search")
        await master_form(e, "suppliers", "供应商")
        supplier, created = await save_master(e, "suppliers", supplier_values)
        await master_form(e, "suppliers", "供应商", supplier["id"])
        supplier, edited = await save_master(e, "suppliers", {"contact_name": "合成已核对联系人", "phone": "13800000072"}, record_id=supplier["id"])
        await checkpoint.passed({"supplier": supplier, "native_create": created, "native_edit": edited}, conditional=[
            {"check_id": "HK-171-deactivate-if-unused", "status": "not_tested", "reason": "本轮供应商继续用于采购；不宣称停用分支执行"}])

        checkpoint.start("HK-177")
        await nav(e, "vehicle-catalog", "车型目录", "/api/vehicle-catalog")
        names = {"brand": "合成品牌" + token, "series": "合成车系" + token, "model": "合成汽油车型" + token}
        model_a, model_a_meta = await create_model(e, names)
        model_b, model_b_meta = await create_model(e, {**names, "model": "合成混动车型" + token}, parent=model_a, hybrid=True)
        await checkpoint.passed({"new_hierarchy": model_a, "existing_hierarchy_new_model": model_b,
                                 "native": [model_a_meta, model_b_meta]})

        checkpoint.start("HK-178")
        vehicles_before = e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"]
        await master_page(e, "warehouses", "仓库")
        await master_form(e, "warehouses", "仓库")
        warehouse, warehouse_meta = await save_master(e, "warehouses", {"code": "BCW" + token, "name": "合成整车仓" + token,
                                                                        "active": True, "warehouse_type": "vehicles", "address": "合成现场整车库区"})
        await master_page(e, "locations", "库位")
        await master_form(e, "locations", "库位")
        await live_choice(e, "warehouse_id", warehouse["name"], warehouse["code"] + " · " + warehouse["name"], expected_value=warehouse["id"])
        location, location_meta = await save_master(e, "locations", {"code": "BCL" + token, "name": "合成整车库位" + token, "active": True})
        require(location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "vehicles", "本轮未创建真实整车仓与库位关系")
        require(e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"] == vehicles_before, "主档配置制造实车库存")
        warehouse_evidence = {"warehouse": warehouse, "location": location, "native": [warehouse_meta, location_meta], "configuration_added_vehicles": 0}
        checkpoint.active["acceptance_checks"][0]["evidence"] = warehouse_evidence
        checkpoint.save()

        checkpoint.start("HK-026")
        inventory = await login_as(e, context, credentials, fixture["inventory_key"], "vehicle-procurement", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("整车采购与付款")
        await e.click('#main [data-act="vp-new"]', "库管建立原两行整车采购计划")
        await expect(e.page.locator("#modal-title")).to_have_text("整车采购计划")
        await select_value(e, '#modal [name="supplier_id"]', supplier["id"], "明确选择本轮原供应商")
        party = e.page.locator('#modal [name="contracting_party"]')
        if await party.get_attribute("readonly") is not None:
            contracting_party = await party.input_value()
            require(bool(contracting_party.strip()), "原已批准采购抬头为空")
        else:
            contracting_party = "合成采购公司" + token
            await e.fill('#modal [name="contracting_party"]', contracting_party, "填写本轮明确合成合同抬头")
        today = await e.page.locator('#modal [name="due_date"]').input_value()
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", today) is not None, "原默认采购日期无效")
        await e.fill('#modal [name="reason"]', "合成采购约定：本轮两车型各一台，独立核价付款及逐VIN实车验收", "填写合成采购事实来源")
        await e.click('#modal [data-act="vp-add-line"]', "原计划增加第二条已知车型")
        await expect(e.page.locator('#modal [data-vp-line]')).to_have_count(2)
        for index, model, color in ((0, model_a, "合成白"), (1, model_b, "合成黑")):
            row = f'#modal [data-vp-line]:nth-child({index + 1}) '
            await select_value(e, row + '[name="model"]', model["model"]["id"], "选择明确采购车型")
            await e.fill(row + '[name="color"]', color, "填写明确采购颜色")
            await e.fill(row + '[name="quantity"]', "1", "填写原计划整数台数")
        # Capture the actual new original order GET without guessing its ID.
        async with e.page.expect_response(lambda r: r.request.method == "GET" and re.fullmatch(r"/api/flow/cases/\d+", urlsplit(r.url).path)) as rendered:
            async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/vehicle-procurement/orders") as pending:
                await e.click('#modal form button[type="submit"]', "提交原采购计划给主管")
            response = await pending.value
            body = await response.json()
            require(response.status == 201, "本轮原采购计划创建未成功：" + e.scrub(body.get("detail", "")))
        read = await rendered.value
        require(read.status == 200 and (await read.json())["id"] == body["id"], "原采购新页面未读取同原单")
        create_meta, request = await response_meta(e, response, body)
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main h1")).to_have_text("整车采购办理")
        case_id = body["id"]
        f = purchase_facts(e, case_id)
        require(f["case"]["kind"] == "vehicle_procurement" and f["case"]["flow_version"] == 2 and f["case"]["state"] == "approval"
                and f["case"]["created_by"] == inventory["id"] and f["case"]["store_id"] == store_id
                and f["case"]["due_date"] == today and f["order"]["supplier_id"] == supplier["id"]
                and f["order"]["contracting_party"] == contracting_party and f["order"]["payment_terms_days"] == supplier["payment_terms_days"], "原采购输入或身份不匹配")
        await expect(e.page.locator("#main")).to_contain_text(supplier["name"])
        await expect(e.page.locator("#main")).to_contain_text(contracting_party)
        await expect(e.page.locator("#main")).to_contain_text(today)
        for model in (model_a, model_b):
            await expect(e.page.locator("#main")).to_contain_text(model["model"]["name"])
        require(len(f["lines"]) == 2 and len(f["events"]) == 1 and f["events"][0]["action"] == "vp_create"
                and f["events"][0]["actor_id"] == inventory["id"] and not f["prices"] and not f["receipts"] and not f["payments"], "创建原计划提前造价/款/实车或事件错误")
        for actual, proposed in zip(f["lines"], request["lines"]):
            require(all(actual[key] == proposed[key] for key in ("model_id", "quantity", "color")), "原采购行与显式输入不一致")
        require(e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"] == vehicles_before, "采购准备提前增加实车")
        manager, _, approve_owner = await responsible(e, context, credentials, fixture, case_id, "vp_approve", "manager")
        require(manager["id"] != inventory["id"], "采购申请与批准没有独立身份")
        contract_file = await upload(e, case_id, manager, "procurement_contract", "synthetic-contract.txt",
                                     f"采购原单 {f['case']['number']}；合同抬头 {contracting_party}；供方 {supplier['name']}。\n"
                                     f"{model_a['model']['name']} 合成白 1台 单车100000元；{model_b['model']['name']} 合成黑 1台 单车110000元。")
        costs = {model_a["model"]["id"]: 10_000_000, model_b["model"]["id"]: 11_000_000}
        prices = {}
        for line in f["lines"]:
            prices["cost_" + str(line["id"])] = str(costs[line["model_id"]] // 100)
            prices["price_" + str(line["id"])] = str((12_000_000 if line["model_id"] == model_a["model"]["id"] else 13_000_000) // 100)
        approved, f, approve_evidence = await purchase_command(e, case_id, "approve", manager, prices, [("evidence_id", contract_file)])
        require(len(f["prices"]) == 2 and f["case"]["amount_cents"] == 21_000_000 and f["case"]["state"] == "receiving", "主管未冻结两行原价格")
        for frozen in f["prices"]:
            line = next(l for l in f["lines"] if l["id"] == frozen["line_id"])
            require(frozen["unit_cost_cents"] == costs[line["model_id"]] and frozen["approved_by"] == manager["id"]
                    and frozen["evidence_id"] == contract_file, "原冻结成本或独立批准来源错误")
        funds_body, f, funds_evidence = await purchase_command(e, case_id, "request_funds", manager,
            {"amount": "210000.00", "reason": "按本单已批准两台约定申请合成采购付款"}, [("evidence_id", contract_file)])
        require(len(f["funds"]) == 1 and f["funds"][0]["status"] == "open" and f["funds"][0]["amount_cents"] == 21_000_000
                and f["funds"][0]["requested_by"] == manager["id"] and not f["payments"] and not f["receipts"], "原请款误当付款或验收")
        require(funds_body["totals"]["paid_net_cents"] == funds_body["totals"]["received_cents"] == funds_body["totals"]["prepaid_cents"] == 0,
                "批准请款提前产生资金或实物")
        require(e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"] == vehicles_before, "批准请款提前增加实车")
        await checkpoint.passed({"case_id": case_id, "case_number": f["case"]["number"], "order": f["order"], "lines": f["lines"],
                                 "prices": f["prices"], "funds": f["funds"], "create": create_meta, "owner": approve_owner,
                                 "approve": approve_evidence, "request_funds": funds_evidence, "pre_receipt_vehicles_added": 0})

        checkpoint.start("HK-021")
        finance, _, pay_owner = await responsible(e, context, credentials, fixture, case_id, "vp_pay", "finance")
        require(len({manager["id"], finance["id"], inventory["id"]}) == 3, "核价、付款、实车经办未分离")
        reference = "SYNTHETIC-VP-" + token
        receipt_file = await upload(e, case_id, finance, "receipt", "synthetic-payment-receipt.txt",
                                    f"合成付款输入：原采购 {f['case']['number']}；本次210000元；凭证号 {reference}；不是银行实付证明。")
        accounts = e.db.rows("SELECT id,name,account_type,active,store_id FROM flow_accounts WHERE store_id=? AND active=1 AND account_type='bank' ORDER BY id", (store_id,))
        require(len(accounts) == 1, "合成本店结算账户不唯一，须明确输入后再选择")
        account = accounts[0]
        paid, f, pay_evidence = await purchase_command(e, case_id, "pay", finance,
            {"amount": "210000.00", "reference": reference}, [("funds_request_id", f["funds"][0]["id"]), ("account_id", account["id"]), ("evidence_id", receipt_file)])
        require(len(f["payments"]) == 1 and f["funds"][0]["status"] == "closed" and not f["receipts"]
                and paid["totals"]["paid_net_cents"] == paid["totals"]["prepaid_cents"] == 21_000_000
                and paid["totals"]["received_cents"] == paid["totals"]["payable_cents"] == 0, "原付款/预付与实车验收混淆")
        payment = f["payments"][0]
        cash = e.db.rows("SELECT id,store_id,created_by,direction,category,amount_cents,account,voucher_no,approval_state FROM cash_entries WHERE id=?", (payment["cash_id"],))[0]
        require(payment["amount_cents"] == cash["amount_cents"] == 21_000_000 and payment["reference"] == cash["voucher_no"] == reference
                and payment["account_id"] == account["id"] and cash["account"] == account["name"] and cash["created_by"] == finance["id"]
                and cash["category"] == "vehicle_procurement_payment" and cash["direction"] == "out" and cash["approval_state"] == "approved"
                and payment["evidence_id"] == receipt_file and cash["store_id"] == store_id, "真实原Cash/Payment资金来源错误")
        require(e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"] == vehicles_before, "付款登记提前制造实车")
        inventory, _, ship_owner = await responsible(e, context, credentials, fixture, case_id, "vp_ship", "inventory")
        ship_file = await upload(e, case_id, inventory, "evidence", "synthetic-shipping.txt", "合成逐VIN发运资料；两台原采购车辆的现场输入。")
        vin_base = "LHKV" + uuid.uuid4().hex[:12].upper()
        shipping_evidence = []
        for index, line in enumerate(f["lines"]):
            _, f, evidence = await purchase_command(e, case_id, "ship", inventory,
                {"vin": vin_base + str(index + 1), "shipped_date": today, "expected_date": today}, [("line_id", line["id"]), ("evidence_id", ship_file)])
            shipment = next(s for s in f["shipments"] if s["line_id"] == line["id"])
            require(shipment["status"] == "transit" and shipment["active_vin"] == shipment["vin"] and shipment["actor_id"] == inventory["id"]
                    and not f["receipts"] and e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"] == vehicles_before, "发运被误当实物验收")
            shipping_evidence.append(evidence)
            await expect(e.page.locator("#main tbody tr").filter(has_text=shipment["vin"])).to_contain_text("在途待验收")
        inventory, _, receive_owner = await responsible(e, context, credentials, fixture, case_id, "vp_receive", "inventory")
        receive_file = await upload(e, case_id, inventory, "evidence", "synthetic-receiving.txt", "合成现场验收输入；重新逐VIN核对，存放于本轮明确整车库位。")
        shipment = f["shipments"][0]
        await action_form(e, "receive")
        await select_value(e, '#modal [name="shipment_id"]', shipment["id"], "明确原在途VIN")
        await e.fill('#modal [name="vin"]', "LHKV0000000000000", "提交与原发运不同的现场VIN负例")
        await select_value(e, '#modal [name="location_id"]', location["id"], "选择原整车库位")
        await select_value(e, '#modal [name="evidence_id"]', receive_file, "选择原验收凭据")
        wrong_vin = await rejected_submit(e, f"/api/vehicle-procurement/orders/{case_id}/actions/receive", 422, "现场VIN与发运VIN不一致")
        receiving_evidence, vehicle_facts = [], []
        for original in f["shipments"]:
            _, f, evidence = await purchase_command(e, case_id, "receive", inventory, {"vin": original["vin"]},
                [("shipment_id", original["id"]), ("location_id", location["id"]), ("evidence_id", receive_file)])
            shipment = next(s for s in f["shipments"] if s["id"] == original["id"])
            receipt = next(r for r in f["receipts"] if r["shipment_id"] == shipment["id"])
            line = next(l for l in f["lines"] if l["id"] == shipment["line_id"])
            price = next(p for p in f["prices"] if p["line_id"] == line["id"])
            require(shipment["status"] == "received" and shipment["active_vin"] is None and receipt["actor_id"] == inventory["id"]
                    and receipt["due_date"] == (date.fromisoformat(today) + timedelta(days=supplier["payment_terms_days"])).isoformat(), "原逐车验收状态/账期错误")
            movement = next(m for m in f["movements"] if m["shipment_id"] == shipment["id"])
            require(movement["kind"] == "receive" and movement["quantity"] == 1 and movement["value_cents"] == price["unit_cost_cents"]
                    and movement["vehicle_id"] == receipt["vehicle_id"] and movement["actor_id"] == inventory["id"]
                    and movement["evidence_id"] == receive_file, "原入库不可覆盖流水错误")
            vehicle_facts.append(vehicle_fact(e, receipt, shipment, line, price, warehouse, location, inventory))
            receiving_evidence.append(evidence)
            await expect(e.page.locator("#main tbody tr").filter(has_text=shipment["vin"]).filter(has_text="已验收入库")).to_have_count(1)
        require(f["case"]["state"] == "completed" and f["case"]["completed_date"] == today and len(f["receipts"]) == len(f["movements"]) == 2
                and e.db.rows("SELECT COUNT(*) AS n FROM vehicles")[0]["n"] == vehicles_before + 2 and not any(t["status"] == "open" for t in f["tasks"]), "采购结束未与两台实车/原任务一致")
        finance, final = await detail_as(e, context, credentials, fixture["finance_key"], case_id, store_id)
        require(final["totals"]["received_quantity"] == 2 and final["totals"]["received_cents"] == final["totals"]["paid_net_cents"] == 21_000_000
                and all(final["totals"][key] == 0 for key in ("payable_cents", "prepaid_cents", "supplier_refund_due_cents", "unshipped_quantity", "in_transit_quantity")), "最终原资金/实物对账不一致")
        before_refresh = e.business_snapshot("original_before_purchase_refresh")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/flow/cases/{case_id}") as pending:
            e.action("refresh", "刷新原采购事实，不重复记款或收车")
            await e.page.reload(wait_until="domcontentloaded")
        require((await pending.value).status == 200, "原采购刷新失败")
        await (await pending.value).body()
        await expect(e.page.locator("#main h1")).to_have_text("整车采购办理")
        e.business_unchanged(before_refresh, "original_after_purchase_refresh")
        require(purchase_facts(e, case_id) == f, "刷新改写或重复生成原采购事实")
        await checkpoint.passed({"case_id": case_id, "payment": payment, "cash": cash, "native_pay": pay_evidence,
            "task_owners": [pay_owner, ship_owner, receive_owner], "native_ship": shipping_evidence,
            "native_receive": receiving_evidence, "protected_wrong_vin": wrong_vin, "vehicles": vehicle_facts,
            "final_totals": final["totals"], "refresh_business_unchanged": True})

        checkpoint.start("HK-178")
        await checkpoint.passed({**warehouse_evidence, "used_by_receipt_ids": [r["id"] for r in f["receipts"]],
                                 "actual_positions": [v["position"] for v in vehicle_facts]}, conditional=[
            {"check_id": "HK-178-edit-deactivate-type-if-needed", "status": "not_tested", "reason": "本轮整车仓保持实际使用；未编辑或停用已在用仓库"}])

        checkpoint.start("HK-018")
        inventory, _ = await detail_as(e, context, credentials, fixture["inventory_key"], case_id, store_id)
        await nav(e, "vehicle-catalog", "车型目录", "/api/vehicle-catalog")
        catalogue_evidence = []
        for model in (model_a, model_b):
            displayed, meta = await catalog_filter(e, model)
            require(displayed["total"] == 1 and len(displayed["items"]) == 1, "组合筛选没有唯一真实车型")
            item = displayed["items"][0]
            for field in ("id", "name", "model_year", "fuel_type", "seats", "displacement_ml", "battery_wh", "guide_price_cents"):
                require(item[field] == model["model"][field], "车型筛选参数/DB不匹配：" + field)
            source = next(v for v in vehicle_facts if v["vehicle"]["model"] == item["name"])
            require(item["stock_count"] == item["available_count"] == 1 and len(item["vehicles"]) == 1, "真实本店在库/可配数量错误")
            actual = item["vehicles"][0]
            require(actual["id"] == source["vehicle"]["id"] and actual["vin"] == source["vehicle"]["vin"]
                    and actual["color"] == source["vehicle"]["color"] and actual["available"] is True and actual["source"] == "原入库车型", "可选配展示没有真实原入库来源")
            card = e.page.locator("#main .chartgrid .panel").filter(has=e.page.get_by_role("heading", name=item["name"], exact=True))
            await expect(card).to_have_count(1)
            summary = card.locator("details > summary")
            await expect(summary).to_have_text("查看本店车辆（1）")
            e.action("click", "展开本店原入库VIN", model_id=item["id"])
            await summary.click()
            await expect(card.get_by_text(actual["vin"], exact=True)).to_be_visible()
            await expect(card).to_contain_text("当前可选配")
            await expect(card).to_contain_text("原入库车型")
            catalogue_evidence.append({"native_get": meta, "model": item, "position": source["position"]})
        excluded, excluded_meta = await catalog_filter(e, model_a, min_seats=6)
        require(excluded["total"] == 0 and not excluded["items"], "已知五座车型未被六座条件排除")
        await checkpoint.passed({"positive": catalogue_evidence, "negative_known_parameter": excluded_meta,
                                 "queries_added_business": False})

        checkpoint.start("HK-029")
        await nav(e, "legacy/vehicles", "整车库存", "/api/records/vehicles")
        stock_evidence = []
        for source in vehicle_facts:
            car = source["vehicle"]
            before = e.business_snapshot("original_before_vin_stock_query")
            async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/records/vehicles"
                                              and parse_qs(urlsplit(r.url).query).get("q") == [car["vin"]]) as pending:
                await e.fill('#filters [name="q"]', car["vin"], "按真实VIN查询原车辆库存")
            response = await pending.value
            listing = await response.json()
            require(response.status == 200 and listing["total"] == 1 and len(listing["items"]) == 1, "原VIN库存查询未唯一返回本轮实车")
            row = listing["items"][0]
            for field in ("id", "vin", "model", "location", "approval_state"):
                require(row[field] == car[field], "原车辆查询 UI/API/DB不一致：" + field)
            require(row["stock_state"] == "available", "原新入库车辆未处于真实可用状态")
            require(row["stock_age_days"] == 0, "本轮当日验收车辆原库龄不为零")
            ui = e.page.locator("#main tbody tr")
            await expect(ui).to_have_count(1)
            for text in (car["vin"], car["model"], car["location"]):
                await expect(ui).to_contain_text(text)
            await expect(ui).to_contain_text("可售")
            await expect(ui).to_contain_text("已审核")
            headers = await e.page.locator("#main thead th").all_text_contents()
            require(headers.count("库龄（天）") == 1, "原库存表缺少唯一库龄列")
            await expect(ui.locator("td").nth(headers.index("库龄（天）"))).to_have_text("0")
            holds = e.db.rows("SELECT vehicle_id,case_id,store_id,delivered FROM flow_vehicle_holds WHERE vehicle_id=?", (car["id"],))
            require(not holds, "本轮实车出现未由当前UI产生的占用")
            e.business_unchanged(before, "original_after_vin_stock_query")
            stock_evidence.append({"native_query": {"path": "/api/records/vehicles", "method": "GET", "status": 200,
                                                   "vin": car["vin"], "native_ui": True, "business_unchanged": True},
                                   "original_stock_state": row["stock_state"], "stock_age_days": row["stock_age_days"],
                                   "native_age_cell_text": "0", **source,
                                   "hold_observation": {"actual_rows": 0, "positive_occupied_branch_tested": False}})
        await checkpoint.passed({"stock": stock_evidence}, conditional=[
            {"check_id": "HK-029-occupied-source", "status": "not_tested", "reason": "本轮原采购生成可用实车；占用分支需后续真实销售配车事实，空Hold仅用于校对当前可用状态"}])
        checkpoint.finish()
    except Exception as error:
        checkpoint.failed(error)
        raise


VEHICLE_PURCHASE_SCENARIOS = ((SCENARIO, vehicle_purchase, 300),)
