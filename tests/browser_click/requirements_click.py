"""Finite native UI coverage of the published original requirement catalogue.

Search, help articles, shared manual pages, and nine empty original forms are
separate coverage levels. None of them claims a business workflow succeeded.
The caller supplies the existing Evidence/native browser and isolated fixture.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import expect


GUIDES = "requirements-help-guides"
SEARCH = "requirements-search"
PAGES = "requirements-original-pages"
FORMS = "requirements-representative-forms"
FORM_CONTRACTS = (
    ("wf-reception", "接待", "customer_name"),
    ("wf-vehicle-purchase", "整车采购计划", "color"),
    ("wf-repair-complete", "建立维修明细工单", "plate"),
    ("wf-material-purchase", "申请多行采购", "quantity"),
    ("wf-period-close", "新建业务期间对账", "start"),
    ("wf-customer-profile", "新增客户档案", "name"),
    ("wf-member-card", "按卡号识别本店客户", "number"),
    ("wf-suppliers-and-insurers", "新增供应商", "name"),
    ("wf-employee-store-roles", "新增员工", "username"),
)
SOURCE_REPORTS = {
    "visit-activity": ("/api/visit-activity-reports", ("complete",), "visit_source_issues"),
    "vehicle-period": ("/api/inventory-reports/vehicles", ("complete", "transit_complete"), "vehicle_period_unverified_generations"),
    "procurement-cohort": ("/api/inventory-reports/procurement", ("complete",), "procurement_cohort_issue_count"),
    "warehouse-period": ("/api/inventory-reports/warehouses", ("complete", "closing_complete"), "warehouse_period_gap_count"),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def catalogue(manifest=None):
    path = Path(__file__).with_name("requirements_manifest.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(data.get("schema") == 1 and data.get("business_accepted") is False, "原需求清单版本/未验收标记不正确")
    expected = {"requirements": 193, "modules": 10, "workflows": 111, "targets": 70}
    require(data.get("counts") == expected, "原需求清单数量不完整")
    for key in ("requirements", "workflows", "targets"):
        require(len(data[key]) == expected[key], f"{key} 清单长度不正确")
    requirements = {row["id"]: row for row in data["requirements"]}
    workflows = {row["id"]: row for row in data["workflows"]}
    targets = {row["route"]: row for row in data["targets"]}
    require(len(requirements) == 193 and len(workflows) == 111 and len(targets) == 70, "原需求清单存在重复编号/入口")
    require(len({row["module"] for row in requirements.values()}) == 10, "原需求模块不完整")
    for item in requirements.values():
        require(item["workflow_ids"] and item["target_routes"], f"需求没有既有入口：{item['id']}")
        require(set(item["workflow_ids"]) <= workflows.keys() and set(item["target_routes"]) <= targets.keys(), "需求入口引用不存在")
        require({workflows[key]["entry"]["route"] for key in item["workflow_ids"]} == set(item["target_routes"]), "需求工作流/入口引用不一致")
    for item in workflows.values():
        require(item["requirement_ids"] and set(item["requirement_ids"]) <= requirements.keys(), "工作流原需求引用不存在")
        require(all(item["id"] in requirements[key]["workflow_ids"] for key in item["requirement_ids"]), "原需求双向工作流关联不一致")
    if manifest is not None:
        published_path = Path(manifest["source_root"]) / "web" / "workflow-guides.json"
        published_bytes = published_path.read_bytes()
        published = json.loads(published_bytes.decode("utf-8"))
        require(published.get("schema_version") == 1 and published.get("source_sha256") == data["source_sha256"], "本次源码的指引来源指纹不一致")
        published_requirements = {row["id"]: row for row in published["requirements"]}
        published_workflows = {row["id"]: row for row in published["workflows"]}
        require(len(published["requirements"]) == len(published_requirements) == 193
                and len(published["workflows"]) == len(published_workflows) == 111
                and published_requirements.keys() == requirements.keys()
                and published_workflows.keys() == workflows.keys(), "本次发布指引的完整编号与需求清单不一致")
        for key, item in requirements.items():
            source = published_requirements[key]
            require(all(source[field] == item[field] for field in ("id", "module", "group", "title", "workflow_ids")), "本次源码原需求合同变化：" + key)
        for key, item in workflows.items():
            source = published_workflows[key]
            require(all(source[field] == item[field] for field in ("id", "title", "category", "requirement_ids", "entry")), "本次源码工作流合同变化：" + key)
        require({row["entry"]["route"] for row in published_workflows.values()} == targets.keys(), "本次源码共用入口集合不一致")
        data["published_guides_sha256"] = hashlib.sha256(published_bytes).hexdigest()
    return data, hashlib.sha256(path.read_bytes()).hexdigest()


class Checkpoint:
    def __init__(self, e, name, rows):
        self.e = e
        self.data, manifest_hash = catalogue(e.manifest)
        self.path = e.directory / "checkpoint.json"
        self.report = {
            "schema": 1, "scenario": name, "source_sha256": self.data["source_sha256"],
            "published_guides_sha256": self.data["published_guides_sha256"],
            "manifest_sha256": manifest_hash, "expected_items": [row["id"] for row in rows],
            "registered": len(rows), "executed": 0, "passed_count": 0, "complete": False,
            "passed": False, "business_flow_tested": False, "original_business_unchanged": False,
            "items": [{**row, "status": "unexecuted"} for row in rows],
            "scope": "原UI读取、空表单打开/取消；未提交原业务",
        }
        self.business_before = None
        self.request_start = None
        self.write()

    def write(self):
        save_json(self.path, self.report)

    def begin(self, index):
        item = self.report["items"][index]
        item.update(status="running", first_action=len(self.e.actions) + 1)
        self.report["executed"] += 1
        self.write()
        return item

    def pass_item(self, item, evidence):
        item.update(status="passed", last_action=len(self.e.actions), evidence=evidence)
        self.report["passed_count"] += 1
        self.write()

    async def start(self, context, credentials):
        await self.e.login(context, credentials, role="admin", route="workflows")
        await drain_network(self.e)
        self.business_before = self.e.business_snapshot("original_business_before_requirement_ui")
        self.request_start = len(self.e.network)
        await open_index(self.e)

    async def finish(self, error=None):
        if error is not None:
            self.report["error"] = self.e.scrub(f"{type(error).__name__}: {error}")
            for item in self.report["items"]:
                if item["status"] == "running":
                    item.update(status="failed", error=self.report["error"], last_action=len(self.e.actions))
        try:
            await drain_network(self.e)
            if self.business_before is not None:
                self.e.business_unchanged(self.business_before, "original_business_after_requirement_ui")
                self.report["original_business_unchanged"] = True
            if self.request_start is not None:
                mutations = [row for row in self.e.network[self.request_start:]
                             if row["event"] == "request" and row["path"].startswith("/api/")
                             and row["method"] not in {"GET", "HEAD"}]
                require(not mutations, "原需求UI读取/取消出现业务写请求")
            self.report["complete"] = (self.report["executed"] == self.report["registered"]
                                       and all(row["status"] in {"passed", "failed"} for row in self.report["items"]))
            self.report["passed"] = (error is None and self.report["complete"]
                                     and self.report["passed_count"] == self.report["registered"]
                                     and self.report["original_business_unchanged"])
        except BaseException as finish_error:
            self.report["passed"] = False
            self.report["final_gate_error"] = self.e.scrub(f"{type(finish_error).__name__}: {finish_error}")
            if error is None:
                raise
        finally:
            self.write()
            self.e.observe("requirement_checkpoint", {"path": str(self.path), "registered": self.report["registered"],
                                                       "executed": self.report["executed"], "passed_count": self.report["passed_count"],
                                                       "complete": self.report["complete"], "passed": self.report["passed"]})


async def drain_network(e):
    if e.response_jobs:
        await asyncio.gather(*tuple(e.response_jobs))


async def open_index(e):
    await e.click('.sidebar a[href="#workflows"]', "原操作指引目录")
    await expect(e.page.locator("#main h1")).to_have_text("操作指引")
    await expect(e.page.locator("#workflow-guide-query")).to_be_visible()
    await expect(e.page.locator("#workflow-guide-results .wf-card")).to_have_count(111)


async def open_article(e, item):
    await e.click(f'#workflow-guide-results .wf-card[data-wfh-guide="{item["id"]}"]', "打开指引：" + item["title"])
    article = e.page.locator(f'.wf-article[data-workflow="{item["id"]}"]')
    await expect(article).to_be_visible()
    await expect(article.locator("h1")).to_have_text(item["title"])
    require(urlsplit(e.page.url).fragment == "workflows/" + item["id"], "指引点击未到达原发布路由")
    return article


async def capture_ui(e, label, selector="#main"):
    path = e.directory / (label + ".png")
    await e.page.screenshot(path=str(path), full_page=False)
    text = await e.page.locator(selector).inner_text()
    return {"screenshot": str(path), "visible_text": e.scrub(text),
            "visible_text_sha256": hashlib.sha256(text.encode()).hexdigest()}


class NativeSourceReport:
    """Observe only the original report GET caused by this actual UI click.

    Keep flags and source-issue messages/counts; never retain original rows,
    source IDs, credentials, request bodies, or the full response JSON.
    """
    def __init__(self, e, route):
        self.e, self.route = e, route
        self.spec = SOURCE_REPORTS.get(route)
        self.jobs, self.observations = [], []
        if self.spec:
            e.page.on("response", self.on_response)

    def on_response(self, response):
        parsed = urlsplit(response.url)
        if (f"{parsed.scheme}://{parsed.netloc}" == self.e.origin
                and parsed.path == self.spec[0] and response.request.method == "GET"):
            self.jobs.append(asyncio.create_task(self.capture(response)))

    async def capture(self, response):
        record = {"path": self.spec[0], "method": "GET", "status": response.status}
        self.observations.append(record)
        require(response.status == 200, "原统计来源读取不是真实200")
        headers = await response.request.all_headers()
        require(bool(headers.get("cookie")), "原统计GET未沿用浏览器真实Cookie")
        data = await response.json()
        require(all(type(data.get(key)) is bool for key in self.spec[1]), "原统计完整性字段不是明确布尔值")
        flags = {key: data[key] for key in self.spec[1]}
        messages = []
        if self.route == "visit-activity":
            # This original serializer exposes issue messages in one dedicated
            # table. Read only its final explanation column, never IDs/rows.
            for row in data.get("tables", {}).get("visit_source_issues", {}).get("rows", []):
                values = row.get("values", [])
                if len(values) == 3 and isinstance(values[2], str):
                    messages.append(values[2])
        elif isinstance(data.get("issues"), list):
            messages = [row["issue"] for row in data["issues"] if isinstance(row, dict) and isinstance(row.get("issue"), str)]
        else:
            for row in data.get("rows", []):
                if isinstance(row, dict):
                    messages.extend(value for value in row.get("issues", []) if isinstance(value, str))
        counts = Counter(self.e.scrub(message) for message in messages)
        gap_count = data.get("metrics", {}).get(self.spec[2])
        require(type(gap_count) is int and gap_count >= 0, "原统计来源差异计数不明确")
        record.update(cookie_present=True, completeness_flags=flags,
                      source_complete=all(flags.values()),
                      source_issue_summary={"reported_gap_count": gap_count, "message_occurrences": len(messages),
                                            "message_counts": [{"message": message, "count": count} for message, count in sorted(counts.items())]})

    async def finish(self):
        if self.spec:
            self.e.page.remove_listener("response", self.on_response)
            if self.jobs:
                await asyncio.gather(*self.jobs)
            require(len(self.observations) == 1, "本次真实点击未观察到唯一原统计GET；不得继承旧响应")
        return self.observations


def expected_source_notice(route, flags):
    if route == "visit-activity":
        return ("本次获权来源可核对；不代表未录入的历史完整。" if flags["complete"]
                else "存在来源待核对；下表只统计具有明确来源的实际记录。")
    if route == "vehicle-period":
        stock = "本次所列代次均可核对" if flags["complete"] else "存在不完整来源；不展示完整期末合计"
        transit = "本次授权范围内可核对" if flags["transit_complete"] else "存在对店历史确认不可读的调拨，不能确认其历史在途数量"
        return "库内库存来源：" + stock + "。在途来源：" + transit + "。"
    if route == "procurement-cohort":
        source = "原订货与到退货来源可核对" if flags["complete"] else "存在来源差异或历史简表；不展示完整履约合计"
        return source + "。此处不是期间到货统计。"
    if route == "warehouse-period":
        period = "完整" if flags["complete"] else "有未知期初或覆盖缺口"
        closing = "已知并可核对；这不代表全期间完整" if flags["closing_complete"] else "来源不足，不能生成完整期末图"
        return "全期间来源：" + period + "。期末来源：" + closing + "。"
    raise AssertionError("未登记的来源提示合同")


async def verify_page_notices(e, target, source_reports):
    require(await e.page.locator('#main .notice.error[role="alert"]').count() == 0, "原人工页面显示读取拒绝/错误警报：" + target)
    error_texts = await e.page.locator("#main .notice.error").all_inner_texts()
    if not source_reports:
        require(not error_texts, "原人工页面显示错误提示：" + target)
        return {"source_incomplete_warning": False}
    source = source_reports[0]
    flags = source["completeness_flags"]
    expected = "".join(expected_source_notice(target, flags).split())
    notices = await e.page.locator("#main .notice").all_inner_texts()
    require(sum("".join(text.split()) == expected for text in notices) == 1, "原来源完整性字段与确切可见提示不一致")
    if flags["complete"] is False:
        require(len(error_texts) == 1 and "".join(error_texts[0].split()) == expected,
                "来源不完整只能显示已核对的保护提示，不能掩盖其他错误")
    else:
        require(not error_texts, "来源完整时仍显示未登记错误提示")
    return {"source_incomplete_warning": not source["source_complete"], "source_complete": source["source_complete"],
            "source_report": source, "source_notice": expected_source_notice(target, flags),
            "data_source_acceptance": False, "business_acceptance": False}


async def help_guides(e, context, credentials):
    data, _ = catalogue(e.manifest)
    categories = list(dict.fromkeys(item["category"] for item in data["workflows"]))
    require(len(categories) == 10, "发布指引应有十个业务分类")
    rows = [{"id": "category:" + category, "kind": "module", "category": category} for category in categories]
    rows += [{"id": item["id"], "kind": "workflow", "requirement_ids": item["requirement_ids"]} for item in data["workflows"]]
    checkpoint = Checkpoint(e, GUIDES, rows)
    error = None
    try:
        await checkpoint.start(context, credentials)
        actual_categories = await e.page.locator("#workflow-guide-category option").all_text_contents()
        require(set(actual_categories) == {"全部", *categories}, "真实分类选项与发布十模块不一致")
        for index, category in enumerate(categories):
            item = checkpoint.begin(index)
            e.action("select", "业务分类", value=category)
            await e.page.locator("#workflow-guide-category").select_option(label=category)
            expected = {row["id"] for row in data["workflows"] if row["category"] == category}
            await expect(e.page.locator("#workflow-guide-results .wf-card")).to_have_count(len(expected))
            actual = await e.page.locator("#workflow-guide-results .wf-card").evaluate_all("xs => xs.map(x=>x.dataset.wfhGuide)")
            require(set(actual) == expected, "分类筛选丢失或混入指引：" + category)
            checkpoint.pass_item(item, {"actual_workflow_ids": actual})
        e.action("select", "全部业务分类", value="")
        await e.page.locator("#workflow-guide-category").select_option("")
        require(await e.page.locator("#workflow-guide-results .wf-card").count() == 111, "取消分类筛选后目录不完整")
        requirements = {row["id"]: row for row in data["requirements"]}
        pictured = set()
        for index, workflow in enumerate(data["workflows"], len(categories)):
            item = checkpoint.begin(index)
            article = await open_article(e, workflow)
            await expect(article.locator('[data-wf-action="manual"]')).to_be_enabled()
            await expect(article.locator('[data-wf-action="manual"]')).to_have_text(workflow["entry"]["label"])
            await e.click('.wf-article .wf-references > summary', "显示原需求引用")
            actual_refs = await article.locator(".wf-references li span").all_text_contents()
            require(set(actual_refs) == set(workflow["requirement_ids"]) and len(actual_refs) == len(set(actual_refs)), "文章原需求引用不完整/重复")
            refs = await article.locator(".wf-references li").all_inner_texts()
            require(all(any(key in ref and requirements[key]["title"] in ref for ref in refs)
                        for key in workflow["requirement_ids"]), "文章未保留原需求名称")
            evidence = {"heading": await article.locator("h1").inner_text(), "reference_rows": refs,
                        "manual_entry_label": workflow["entry"]["label"], "manual_entry_enabled": True}
            if workflow["category"] not in pictured:
                # Sample both visible help tabs once per category; no assistant
                # request or model-triggering action is clicked.
                await e.click('.wf-article [data-wf-path="assistant"]', "查看助手办理说明")
                await expect(article.locator('[data-wf-panel="assistant"]')).to_be_visible()
                await e.click('.wf-article [data-wf-path="manual"]', "返回人工办理说明")
                await expect(article.locator('[data-wf-panel="manual"]')).to_be_visible()
                evidence.update(await capture_ui(e, workflow["id"]))
                pictured.add(workflow["category"])
            checkpoint.pass_item(item, evidence)
            await e.click('.wf-back [data-wf-action="browse"]', "返回全部指引")
            await expect(e.page.locator("#workflow-guide-results .wf-card")).to_have_count(111)
    except BaseException as caught:
        error = caught
        raise
    finally:
        await checkpoint.finish(error)


async def requirement_search(e, context, credentials):
    data, _ = catalogue(e.manifest)
    checkpoint = Checkpoint(e, SEARCH, [{"id": row["id"], "module": row["module"], "title": row["title"]} for row in data["requirements"]])
    error = None
    try:
        await checkpoint.start(context, credentials)
        for index, requirement in enumerate(data["requirements"]):
            item = checkpoint.begin(index)
            expected = set(requirement["workflow_ids"])
            await e.fill("#workflow-guide-query", requirement["id"], "搜索原需求编号")
            await expect(e.page.locator("#workflow-guide-results .wf-card")).to_have_count(len(expected))
            actual_ids = await e.page.locator("#workflow-guide-results .wf-card").evaluate_all("xs => xs.map(x=>x.dataset.wfhGuide)")
            require(set(actual_ids) == expected, "编号搜索未匹配完整原需求指引：" + requirement["id"])
            await e.fill("#workflow-guide-query", requirement["title"], "搜索原需求名称")
            for workflow_id in requirement["workflow_ids"]:
                await expect(e.page.locator(f'#workflow-guide-results .wf-card[data-wfh-guide="{workflow_id}"]')).to_be_visible()
            title_ids = await e.page.locator("#workflow-guide-results .wf-card").evaluate_all("xs => xs.map(x=>x.dataset.wfhGuide)")
            require(expected <= set(title_ids), "原名称搜索漏掉关联指引：" + requirement["id"])
            checkpoint.pass_item(item, {"id_query": requirement["id"], "id_result_workflows": actual_ids,
                                        "name_query": requirement["title"], "name_result_workflows": title_ids,
                                        "result_count_text": await e.page.locator("#workflow-guide-count").inner_text()})
        await capture_ui(e, "requirements-search-final")
    except BaseException as caught:
        error = caught
        raise
    finally:
        await checkpoint.finish(error)


async def original_pages(e, context, credentials):
    data, _ = catalogue(e.manifest)
    workflows = {row["id"]: row for row in data["workflows"]}
    checkpoint = Checkpoint(e, PAGES, [{"id": row["route"], "workflow_ids": row["workflow_ids"],
                                       "requirement_ids": row["requirement_ids"]} for row in data["targets"]])
    error = None
    try:
        await checkpoint.start(context, credentials)
        for index, target in enumerate(data["targets"]):
            item = checkpoint.begin(index)
            workflow = workflows[target["workflow_ids"][0]]
            await open_article(e, workflow)
            network_start = len(e.network)
            source_observer = NativeSourceReport(e, target["route"])
            try:
                await e.click(f'.wf-article [data-wf-action="manual"][data-id="{workflow["id"]}"]', "打开原人工入口：" + target["route"])
                await e.page.wait_for_url(e.origin + "/#" + target["route"])
                await e.page.wait_for_function("""() => { const m=document.querySelector('#main');
                  return m && !m.querySelector('.wf-article,.loading') && (m.querySelector('h1') || m.querySelector('.errorpage')); }""")
            finally:
                source_reports = await source_observer.finish()
            require(await e.page.locator("#main .errorpage").count() == 0, "原人工入口显示读取错误：" + target["route"])
            source_evidence = await verify_page_notices(e, target["route"], source_reports)
            await expect(e.page.locator("#main h1")).to_be_visible()
            heading = (await e.page.locator("#main h1").inner_text()).strip()
            require(heading and heading not in {"操作指引", "请选择工作栏目"}, "原页面未真实显示业务标题")
            require(urlsplit(e.page.url).fragment == target["route"], "人工入口与清单目标路由不一致")
            require(not await e.page.locator("#modal").is_visible(), "只读页面导航意外打开业务提交窗口")
            await drain_network(e)
            responses = [{key: row[key] for key in ("path", "method", "status")} for row in e.network[network_start:]
                         if row["event"] == "response" and row["path"].startswith("/api/")]
            require(all(200 <= row["status"] < 300 for row in responses), "原页面真实API读取拒绝/失败：" + target["route"])
            evidence = {"representative_workflow_id": workflow["id"], "actual_route": target["route"], "heading": heading,
                        "native_api_responses": responses,
                        "response_observation": "native_read_observed" if responses else "cached_or_static_page_no_new_api",
                        "tables": await e.page.locator("#main table").count(),
                        "buttons": await e.page.locator("#main button").count()}
            evidence.update(source_evidence)
            evidence.update(await capture_ui(e, "page-" + target["route"].replace("/", "--")))
            checkpoint.pass_item(item, evidence)
            await open_index(e)
    except BaseException as caught:
        error = caught
        raise
    finally:
        await checkpoint.finish(error)


async def representative_forms(e, context, credentials):
    data, _ = catalogue(e.manifest)
    workflows = {row["id"]: row for row in data["workflows"]}
    checkpoint = Checkpoint(e, FORMS, [{"id": workflow_id, "requirement_ids": workflows[workflow_id]["requirement_ids"]}
                                     for workflow_id, _, _ in FORM_CONTRACTS])
    error = None
    try:
        await checkpoint.start(context, credentials)
        for index, (workflow_id, title, focus_name) in enumerate(FORM_CONTRACTS):
            item = checkpoint.begin(index)
            workflow = workflows[workflow_id]
            await open_article(e, workflow)
            await expect(e.page.locator(f'.wf-article [data-wf-action="form"][data-id="{workflow_id}"]')).to_be_enabled()
            await e.click(f'.wf-article [data-wf-action="form"][data-id="{workflow_id}"]', "打开原表单：" + workflow["title"])
            await expect(e.page.locator("#modal[open]")).to_be_visible()
            await expect(e.page.locator("#modal-title")).to_contain_text(title)
            await expect(e.page.locator("#modal form")).to_be_visible()
            await expect(e.page.locator(f'#modal [name="{focus_name}"]')).to_be_visible()
            await e.click(f'#modal [name="{focus_name}"]', "实际聚焦原表单字段")
            focused = await e.page.locator(f'#modal [name="{focus_name}"]').evaluate("x => document.activeElement===x")
            require(focused, "原表单字段无法实际聚焦")
            controls = await e.page.locator("#modal input,#modal select,#modal textarea").evaluate_all("""xs => xs.map(x=>({
              name:x.name,type:x.type,required:x.required,disabled:x.disabled,visible:!!x.getClientRects().length}))""")
            require(any(control["visible"] and control["name"] for control in controls), "原表单没有可见命名字段")
            evidence = {"modal_heading": await e.page.locator("#modal-title").inner_text(),
                        "fields": controls, "focused_field": focus_name, "business_submitted": False}
            if workflow_id == "wf-employee-store-roles":
                role = await e.page.locator('#modal select[name="role"]').input_value()
                checks = await e.page.locator('#modal input[name="store_ids"]').evaluate_all("xs => xs.map(x=>({store_id:x.value,checked:x.checked}))")
                require(role == "sales", "新增员工默认岗位不是普通销售")
                require(len(checks) == len(e.manifest["stores"]) and all(not row["checked"] for row in checks), "新增员工默认门店被勾选/漏掉可用门店")
                evidence.update(default_role=role, default_store_checks=checks)
            evidence.update(await capture_ui(e, "form-" + workflow_id, "#modal"))
            # The original header close is available on every original form,
            # including procurement forms that have no footer cancel button.
            await e.click('#modal .modalhead [data-act="close"]', "取消原表单")
            await expect(e.page.locator("#modal[open]")).to_have_count(0)
            e.business_unchanged(checkpoint.business_before, "original_business_after_cancel_" + workflow_id)
            evidence["cancelled_through_original_ui"] = True
            checkpoint.pass_item(item, evidence)
            await open_index(e)
    except BaseException as caught:
        error = caught
        raise
    finally:
        await checkpoint.finish(error)


REQUIREMENT_SCENARIOS = (
    (GUIDES, help_guides, 180),
    (SEARCH, requirement_search, 130),
    (PAGES, original_pages, 300),
    (FORMS, representative_forms, 180),
)


def finalize_requirement_report(manifest, browser_report):
    """Combine only these four checkpoints in this one fresh evidence root.

    Partial successful UI observations remain individually visible. Missing,
    failed, or incomplete groups cannot pass the coverage gate. The caller may
    add separately substantiated business sub-action evidence by exact HK ID.
    """
    data, manifest_hash = catalogue(manifest)
    root = Path(manifest["evidence_root"])
    groups = {}
    for name, _, _ in REQUIREMENT_SCENARIOS:
        path = root / name / "checkpoint.json"
        if path.is_file():
            group = json.loads(path.read_text(encoding="utf-8"))
            require(group["manifest_sha256"] == manifest_hash and group["source_sha256"] == data["source_sha256"], "跨清单指纹的需求结果不能复用")
            require(group["published_guides_sha256"] == data["published_guides_sha256"], "跨发布指引源码指纹的需求结果不能复用")
            expected_ids = {
                GUIDES: {row["id"] for row in data["workflows"]} | {"category:" + row["category"] for row in data["workflows"]},
                SEARCH: {row["id"] for row in data["requirements"]},
                PAGES: {row["route"] for row in data["targets"]},
                FORMS: {row[0] for row in FORM_CONTRACTS},
            }[name]
            require(set(group["expected_items"]) == expected_ids and len(group["expected_items"]) == len(expected_ids)
                    and {row["id"] for row in group["items"]} == expected_ids and len(group["items"]) == len(expected_ids),
                    "需求检查点清单不完整/重复")
            groups[name] = group
    statuses = {name: {row["id"]: row["status"] for row in group["items"]} for name, group in groups.items()}
    page_evidence = {row["id"]: row.get("evidence", {}) for row in groups.get(PAGES, {}).get("items", [])}
    scenario_results = {row["id"]: row for row in browser_report["scenarios"]}
    rows_by_id = {row["id"]: row for row in data["requirements"]}

    def scenario_passed(name):
        return scenario_results.get(name, {}).get("status") == "passed"

    def scenario_evidence(name):
        return {"scenario_id": name, "evidence": scenario_results[name]["evidence"]}

    rows = []
    for requirement in data["requirements"]:
        search_ok = statuses.get(SEARCH, {}).get(requirement["id"]) == "passed"
        guides_ok = all(statuses.get(GUIDES, {}).get(key) == "passed" for key in requirement["workflow_ids"])
        pages_ok = all(statuses.get(PAGES, {}).get(key) == "passed" for key in requirement["target_routes"])
        forms_opened = [key for key in requirement["workflow_ids"] if statuses.get(FORMS, {}).get(key) == "passed"]
        source_warnings = [{"route": key, "completeness_flags": page_evidence[key]["source_report"]["completeness_flags"],
                            "source_issue_summary": page_evidence[key]["source_report"]["source_issue_summary"],
                            "visible_notice": page_evidence[key]["source_notice"]}
                           for key in requirement["target_routes"] if page_evidence.get(key, {}).get("source_incomplete_warning")]
        subactions = []
        supplemental = []
        if requirement["id"] == "HK-098" and scenario_passed("customer-prepare-confirm-history-mobile"):
            subactions.append({"action": "新增客户原UI一次确认及历史刷新无重复", "status": "passed",
                               **scenario_evidence("customer-prepare-confirm-history-mobile")})
        if requirement["id"] == "HK-002" and scenario_passed("dependent-plan-followup-controls"):
            subactions.append({"action": "第一张接待分派卡原UI确认", "status": "passed", "second_card": "prepared_only",
                               **scenario_evidence("dependent-plan-followup-controls")})
        if requirement["id"] in {"HK-117", "HK-126"} and scenario_passed("readonly-query-no-card"):
            supplemental.append({"kind": "supplemental_read", "status": "passed", "actual_ui_click": False,
                                 "scope": "真实Cookie GET及SQLite字段对照；未办理会员/套餐业务",
                                 **scenario_evidence("readonly-query-no-card")})
        rows.append({**requirement, "search_tested": search_ok, "guide_article_tested": guides_ok,
                     "help_route_tested": search_ok and guides_ok, "page_ui_tested": pages_ok,
                     "observed_statuses": {"search": statuses.get(SEARCH, {}).get(requirement["id"], "unexecuted"),
                                           "guides": {key: statuses.get(GUIDES, {}).get(key, "unexecuted") for key in requirement["workflow_ids"]},
                                           "pages": {key: statuses.get(PAGES, {}).get(key, "unexecuted") for key in requirement["target_routes"]}},
                     "representative_forms_opened_cancelled": forms_opened, "form_scope": "empty_original_form_open_focus_cancel_only",
                     "source_incomplete_warnings": source_warnings, "data_source_acceptance": False,
                     "business_subactions": subactions, "supplemental_reads": supplemental,
                     "business_flow_tested": False, "full_flow_tested": False,
                     "business_flow_status": "partial_subaction_tested" if subactions else "not_tested",
                     "business_acceptance": False})
    expected_groups = [name for name, _, _ in REQUIREMENT_SCENARIOS]
    complete = set(groups) == set(expected_groups) and all(group["complete"] for group in groups.values())
    actual_counts = {
        "requirements_searched": sum(row["search_tested"] for row in rows),
        "guides_displayed": sum(statuses.get(GUIDES, {}).get(row["id"]) == "passed" for row in data["workflows"]),
        "page_targets_opened": sum(value == "passed" for value in statuses.get(PAGES, {}).values()),
        "forms_opened_cancelled": sum(value == "passed" for value in statuses.get(FORMS, {}).values()),
    }
    count_gate = actual_counts == {"requirements_searched": 193, "guides_displayed": 111,
                                   "page_targets_opened": 70, "forms_opened_cancelled": 9}
    original_and_new_passed = (len(scenario_results) == len(browser_report["scenarios"])
                               and set(scenario_results) == set(browser_report["expected_scenarios"])
                               and all(row["status"] == "passed" for row in scenario_results.values()))
    passed = complete and count_gate and all(group["passed"] for group in groups.values()) and original_and_new_passed
    path = root / "requirements-coverage.json"
    report = {"schema": 1, "source_sha256": data["source_sha256"], "manifest_sha256": manifest_hash,
              "published_guides_sha256": data["published_guides_sha256"],
              "counts": data["counts"], "expected_groups": expected_groups, "complete": complete,
              "passed": passed, "actual_counts": actual_counts, "automatic_ui_gate": "passed" if passed else "failed",
              "help_route_tested": sum(row["help_route_tested"] for row in rows),
              "page_ui_tested": sum(row["page_ui_tested"] for row in rows), "business_flow_tested": 0,
              "business_subactions_tested": sum(len(row["business_subactions"]) for row in rows),
              "source_incomplete_warning_targets": sum(bool(item.get("source_incomplete_warning")) for item in page_evidence.values()),
              "data_source_acceptance": False,
              "business_acceptance": False, "full_flow_tested": False, "requirements": rows,
              "groups": [{"id": name, "registered": group["registered"], "executed": group["executed"],
                          "passed_count": group["passed_count"], "complete": group["complete"], "passed": group["passed"],
                          "evidence": str(root / name / "checkpoint.json")} for name, group in groups.items()],
              "scope": "193搜索/111指引/70共享页面/9原空表单取消；业务实测另按真实子动作留证；未作193业务验收"}
    require(len(rows_by_id) == len(rows) == 193, "需求汇总遗漏原编号")
    save_json(path, report)
    return {"path": str(path), "complete": complete, "passed": passed, "actual_counts": actual_counts,
            "help_route_tested": report["help_route_tested"], "page_ui_tested": report["page_ui_tested"],
            "business_subactions_tested": report["business_subactions_tested"],
            "business_acceptance": False, "full_flow_tested": False}
