"""Native Playwright clicks against the isolated current HTTP application.

No application state injection, fetch replacement, business API setup, or legacy
unit suite. The fixture owns synthetic preconditions. SQLite is opened read-only.
Security rejection probes and a supplemental read-only domain lookup use
context.request; all positive business submissions use the rendered UI.
Evidence intentionally excludes traces/HAR, raw cookie
values, login bodies, model reasoning, and random synthetic passwords.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import async_playwright, expect
from pending_ui import review_followup_ui
from runtime_faults import preparation_crash, inflight_stop
from runtime_batch import batch_rule_failure, batch_result_unknown
from requirements_click import REQUIREMENT_SCENARIOS, finalize_requirement_report
from sales_business import BUSINESS_SCENARIOS as PRESALES_SCENARIOS
from vehicle_purchase_business import VEHICLE_PURCHASE_SCENARIOS
from master_data_business import MASTER_DATA_SCENARIOS
from customer_service_business import CUSTOMER_SERVICE_SCENARIOS
from sales_order_business import SALES_ORDER_SCENARIOS
from report_business import REPORT_SCENARIOS
from material_business import MATERIAL_SCENARIOS
from system_management_business import SYSTEM_MANAGEMENT_SCENARIOS
from repair_business import REPAIR_SCENARIOS
from membership_business import MEMBERSHIP_SCENARIOS
from repair_followon_business import REPAIR_FOLLOWON_SCENARIOS
from sales_followon_business import SALES_FOLLOWON_SCENARIOS
from finance_business import FINANCE_SCENARIOS
from insurance_business import INSURANCE_SCENARIOS
from finance_followon_business import FINANCE_FOLLOWON_SCENARIOS
from system_followon_business import SYSTEM_FOLLOWON_SCENARIOS
from report_followon_business import REPORT_FOLLOWON_SCENARIOS
from member_followon_business import MEMBER_FOLLOWON_SCENARIOS
from finance_report_business import FINANCE_REPORT_SCENARIOS
from vehicle_operations_business import VEHICLE_OPERATIONS_SCENARIOS
from warehouse_operations_business import WAREHOUSE_OPERATIONS_SCENARIOS
from boutique_business import BOUTIQUE_SCENARIOS
from member_points_tier_business import MEMBER_POINTS_TIER_SCENARIOS
from customer_followon_business import CUSTOMER_FOLLOWON_SCENARIOS
from repair_packages_business import REPAIR_PACKAGES_SCENARIOS
from interstore_business import INTERSTORE_SCENARIOS
from repair_claims_business import REPAIR_CLAIMS_SCENARIOS
from repair_rework_business import REPAIR_REWORK_SCENARIOS
from report_remaining_business import REPORT_REMAINING_SCENARIOS
from customer_reminders_business import CUSTOMER_REMINDERS_SCENARIOS
from sales_pdi_business import SALES_PDI_SCENARIOS
from retail_remaining_business import RETAIL_REMAINING_SCENARIOS
from roles_dossier_business import ROLES_DOSSIER_SCENARIOS
from finance_remaining_business import FINANCE_REMAINING_SCENARIOS
from inventory_scope_business import INVENTORY_SCOPE_SCENARIOS
from receivables_business import RECEIVABLES_SCENARIOS
from report_complete_source_business import REPORT_COMPLETE_SOURCE_SCENARIOS

BUSINESS_SCENARIOS = (PRESALES_SCENARIOS + VEHICLE_PURCHASE_SCENARIOS + MASTER_DATA_SCENARIOS
                      + CUSTOMER_SERVICE_SCENARIOS + SALES_ORDER_SCENARIOS + REPORT_SCENARIOS + MATERIAL_SCENARIOS
                      + REPAIR_SCENARIOS + SYSTEM_MANAGEMENT_SCENARIOS + MEMBERSHIP_SCENARIOS
                      + REPAIR_FOLLOWON_SCENARIOS + SALES_FOLLOWON_SCENARIOS + FINANCE_SCENARIOS + INSURANCE_SCENARIOS
                      + FINANCE_FOLLOWON_SCENARIOS + SYSTEM_FOLLOWON_SCENARIOS + REPORT_FOLLOWON_SCENARIOS
                      + MEMBER_FOLLOWON_SCENARIOS + FINANCE_REPORT_SCENARIOS
                      + VEHICLE_OPERATIONS_SCENARIOS + WAREHOUSE_OPERATIONS_SCENARIOS
                      + BOUTIQUE_SCENARIOS + MEMBER_POINTS_TIER_SCENARIOS + CUSTOMER_FOLLOWON_SCENARIOS
                      + REPAIR_PACKAGES_SCENARIOS + INTERSTORE_SCENARIOS + REPAIR_CLAIMS_SCENARIOS + REPAIR_REWORK_SCENARIOS
                      + REPORT_REMAINING_SCENARIOS + CUSTOMER_REMINDERS_SCENARIOS + SALES_PDI_SCENARIOS + RETAIL_REMAINING_SCENARIOS
                      + ROLES_DOSSIER_SCENARIOS + FINANCE_REMAINING_SCENARIOS + INVENTORY_SCOPE_SCENARIOS + RECEIVABLES_SCENARIOS
                      + REPORT_COMPLETE_SOURCE_SCENARIOS)


INPUT = "#business-assistant-input"
SEND = "#business-assistant-form button[type=submit]"
CONFIRM = '[data-ba-action="confirm"]'
TABLES = ("flow_customers", "flow_cases", "flow_tasks", "flow_events")


class GateFailure(AssertionError):
    pass


def require(condition, message):
    if not condition:
        raise GateFailure(message)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def rows(self, sql, values=()):
        require(sql.lstrip().upper().startswith("SELECT "), "数据库证据只允许 SELECT")
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            return [dict(row) for row in connection.execute(sql, values)]

    def counts(self):
        return {table: self.rows(f"SELECT count(*) AS n FROM {table}")[0]["n"] for table in TABLES}

    def business_snapshot(self):
        """Hash every original row, including updates invisible to row counts.

        Assistant-owned records and the two actual login bookkeeping tables are
        outside the original business facts. In app_metadata only exact worker
        prefix rows are excluded; every other metadata row remains protected.
        SQLite's own sequence/schema machinery is not an application table.
        """
        tables = {}
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")  # One coherent read snapshot across tables.
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            for name in names:
                if name.startswith(("business_assistant_", "assistant_")) or name in {"login_sessions", "login_attempts"}:
                    continue
                quoted = '"' + name.replace('"', '""') + '"'
                cursor = connection.execute("SELECT * FROM " + quoted)
                columns = [column[0] for column in cursor.description]
                hashes = []
                for row in cursor:
                    if name == "app_metadata" and str(row[columns.index("key")]).startswith("assistant_runtime_worker:"):
                        continue
                    encoded = []
                    for value in row:
                        if isinstance(value, bytes):
                            encoded.append({"type": "bytes", "length": len(value), "sha256": hashlib.sha256(value).hexdigest()})
                        else:
                            encoded.append({"type": type(value).__name__, "value": value})
                    hashes.append(hashlib.sha256(json.dumps(encoded, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())
                serialized = json.dumps({"columns": columns, "rows": sorted(hashes)}, ensure_ascii=False, separators=(",", ":"))
                tables[name] = {"rows": len(hashes), "sha256": hashlib.sha256(serialized.encode()).hexdigest()}
        return {"table_count": len(tables), "row_count": sum(table["rows"] for table in tables.values()),
                "sha256": hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "tables": tables}

    def case(self, case_id):
        return self.rows("SELECT id,store_id,state,owner_id,version FROM flow_cases WHERE id=?", (case_id,))[0]

    def proposals(self, owner_id, *, session_id=None):
        sql = "SELECT id,session_id,operation_id,status,step_order FROM business_assistant_proposals WHERE owner_id=?"
        values = [owner_id]
        if session_id:
            sql += " AND session_id=?"
            values.append(session_id)
        return self.rows(sql + " ORDER BY created_at,id", values)


class Evidence:
    def __init__(self, manifest, secrets, name):
        self.manifest = manifest
        self.origin = manifest["origin"].rstrip("/")
        self.directory = Path(manifest["evidence_root"]) / name
        self.directory.mkdir(parents=True, exist_ok=False)
        self.db = Database(manifest["database_path"])
        self.secrets = secrets
        self.actions = []
        self.observations = []
        self.network = []
        self.page_errors = []
        self.external_requests = []
        self.response_jobs = set()
        self.latest_session = None
        self.latest_run = None
        self.workspace_features = None
        self.protected_conflicts = []
        self.page = None

    def scrub(self, value):
        output = str(value)
        for secret in self.secrets:
            if secret:
                output = output.replace(secret, "[redacted]")
        return output[:2000]

    def action(self, kind, target, **details):
        self.actions.append({"index": len(self.actions) + 1, "kind": kind, "target": target, **details})

    def observe(self, label, value):
        self.observations.append({"label": label, "value": value})

    def business_snapshot(self, label):
        snapshot = self.db.business_snapshot()
        self.observe(label, snapshot)
        return snapshot

    def business_unchanged(self, before, label):
        after = self.business_snapshot(label)
        changed = [name for name in sorted(before["tables"].keys() | after["tables"].keys())
                   if before["tables"].get(name) != after["tables"].get(name)]
        require(before["sha256"] == after["sha256"], "原业务行发生非确认写入：" + "、".join(changed))

    async def attach(self, context, page):
        self.page = page
        page.on("pageerror", lambda error: self.page_errors.append(self.scrub(error)))
        page.on("request", self.on_request)
        page.on("response", self.on_response)

        async def guard(route):
            parsed = urlsplit(route.request.url)
            if parsed.scheme in {"http", "https"} and f"{parsed.scheme}://{parsed.netloc}" != self.origin:
                self.external_requests.append(parsed.netloc)
                await route.abort("blockedbyclient")
            else:
                await route.continue_()

        # Blocks external attempts, without changing same-origin request content.
        await context.route("**/*", guard)

    def on_request(self, request):
        job = asyncio.create_task(self.capture_request(request))
        self.response_jobs.add(job)
        job.add_done_callback(self.observation_finished)

    def observation_finished(self, job):
        self.response_jobs.discard(job)
        if job.cancelled():
            self.page_errors.append("原生网络证据读取被取消")
        elif job.exception() is not None:
            self.page_errors.append("原生网络证据读取失败：" + self.scrub(job.exception()))

    async def capture_request(self, request):
        parsed = urlsplit(request.url)
        if f"{parsed.scheme}://{parsed.netloc}" != self.origin:
            return
        # Playwright's .headers omits security headers such as Cookie.
        headers = await request.all_headers()
        self.network.append({"event": "request", "path": parsed.path, "method": request.method,
                             "resource_type": request.resource_type,
                             "cookie_present": bool(headers.get("cookie")),
                             "csrf_present": bool(headers.get("x-csrf-token")),
                             "store_id": headers.get("x-store-id"),
                             "same_origin": True})

    def on_response(self, response):
        job = asyncio.create_task(self.capture_response(response))
        self.response_jobs.add(job)
        job.add_done_callback(self.observation_finished)

    async def capture_response(self, response):
        parsed = urlsplit(response.url)
        if f"{parsed.scheme}://{parsed.netloc}" != self.origin:
            return
        headers = response.headers
        item = {"event": "response", "path": parsed.path, "method": response.request.method,
                "status": response.status, "content_type": headers.get("content-type", ""),
                "csp": headers.get("content-security-policy", "")}
        self.network.append(item)
        if parsed.path == "/api/business-assistant/workspace" and response.request.method == "GET" and response.ok:
            body = await response.json()
            features = body.get("features", {})
            if all(isinstance(features.get(key), bool) for key in ("home", "runtime", "followup", "notifications")):
                self.workspace_features = {key: features[key] for key in ("home", "runtime", "followup", "notifications")}
                item["workspace_features"] = self.workspace_features
        if (response.request.method == "POST" and response.ok
                and (parsed.path == "/api/business-assistant/sessions" or parsed.path.endswith("/runs"))):
            try:
                body = await response.json()
                if parsed.path.endswith("/runs"):
                    self.latest_run = body["id"]
                else:
                    self.latest_session = body["id"]
            except Exception as error:
                item["read_error"] = self.scrub(error)
        if "text/event-stream" in item["content_type"]:
            # Observe native SSE headers; do not copy tool payloads or reasoning.
            item["native_sse"] = True

    async def click(self, selector, label=None):
        target = self.page.locator(selector)
        require(await target.count() == 1, f"点击目标必须唯一：{selector}")
        self.action("click", label or selector)
        # Locator.click resolves the current element and performs scrolling and
        # actionability together; separate preflight steps race a page repaint.
        await target.click()

    async def followup_submit_click(self, action, label):
        async with self.page.expect_response(lambda r: urlsplit(r.url).path.endswith("/followup")
                                              and r.request.method == "POST") as pending:
            await self.click(f'[data-baws-followup="{action}"]', label)
        return await pending.value

    async def followup_click(self, action, label):
        grant_sql = "SELECT id,plan_id,status,version,goal_version,revoked_at,stop_reason FROM business_assistant_followup_grants WHERE session_id=? ORDER BY id"
        grants_before = self.db.rows(grant_sql, (self.latest_session,))
        business_before = self.business_snapshot(f"original_business_before_{action}_click")
        response = await self.followup_submit_click(action, label)
        if response.status == 200:
            return
        require(response.status == 409, f"{label}真实请求未成功，HTTP {response.status}")
        require(not self.protected_conflicts, "同场景第二次版本冲突：停止，不继续点击")
        body = await response.json()
        conflict = {"action": action, "first_status": 409, "detail": self.scrub(body.get("detail", "")),
                    "outcome": "protected_conflict_observed", "employee_rechecks": 0}
        self.protected_conflicts.append(conflict)
        self.network.append({"event": "protected_conflict", **conflict})
        await expect(self.page.locator("#ba-current-plan .ba-plan-error")).to_contain_text("事项已变化")
        grants_after = self.db.rows(grant_sql, (self.latest_session,))
        require(grants_before == grants_after, "409 拒绝后授权被改写")
        self.business_unchanged(business_before, f"original_business_after_{action}_conflict")
        self.observe(f"protected_{action}_conflict", {**conflict, "grants_before": grants_before, "grants_after": grants_after,
                                                       "grants_unchanged": True, "business_unchanged": True})
        await self.snapshot(f"followup-{action}-protected-conflict")
        self.action("employee_conflict_review", "员工核对服务器新状态后重新点击", action=action, max_new_attempts=1)
        conflict["employee_rechecks"] = 1
        if action == "revoke":
            # The refusal resets the original two-click confirmation. Re-arm it
            # through the real UI; this is never a request/body replay.
            await expect(self.page.locator('[data-baws-followup="revoke"]')).to_have_text("结束这件事")
            await self.click('[data-baws-followup="revoke"]', "重新核对结束这件事")
            await expect(self.page.locator('[data-baws-followup="revoke"]')).to_have_text("确认结束这件事")
        reviewed_response = await self.followup_submit_click(action, "员工重新核对后：" + label)
        conflict["reviewed_status"] = reviewed_response.status
        require(reviewed_response.status == 200, f"重新核对后 {label}未成功，HTTP {reviewed_response.status}；停止")
        conflict["outcome"] = "covered_protected_conflict"
        self.observe(f"covered_{action}_conflict", conflict.copy())

    async def fill(self, selector, value, label=None, *, private=False):
        self.action("fill", label or selector, **({"private": True} if private else {"value": value}))
        await self.page.locator(selector).fill(value)

    async def key(self, selector, key):
        self.action("keyboard", selector, key=key)
        await self.page.locator(selector).press(key)

    async def snapshot(self, label, *, business_ready=False):
        if business_ready:
            await expect(self.page.locator("#main > .loading")).to_have_count(0)
            await expect(self.page.locator("#main h1")).to_be_visible()
            await expect(self.page.locator("#main > .errorpage")).to_have_count(0)
        path = self.directory / f"{len(self.observations):02d}-{label}.png"
        await self.page.screenshot(path=str(path), full_page=True)
        visible = await self.page.locator("body").inner_text()
        # Password inputs never enter inner_text; synthetic content only.
        self.observe(label, {"screenshot": str(path), "visible_text": self.scrub(visible)})

    async def wait(self, predicate, label, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            await asyncio.sleep(0.1)
        raise GateFailure(f"等待超时：{label}")

    async def login(self, context, credentials, role="sales", *, default_home=False, route=None):
        user = self.manifest["users"][role]
        destination = self.origin + "/#" + route if route else self.origin if default_home else self.origin + "/#business-assistant"
        self.action("navigate", destination)
        await self.page.goto(destination, wait_until="domcontentloaded")
        await self.page.locator('input[name="username"]').wait_for(state="visible")
        await self.fill('input[name="username"]', user["username"], "登录账号")
        await self.fill('input[name="password"]', credentials["users"][role]["password"], "登录密码", private=True)
        async with self.page.expect_response(lambda r: urlsplit(r.url).path == "/api/auth/login") as pending:
            await self.click('form button[type="submit"]', "登录")
        response = await pending.value
        require(response.status == 200, "原生登录未成功")
        await self.page.locator("#store").wait_for(state="visible")
        cookies = await context.cookies()
        metadata = [{key: cookie[key] for key in ("name", "httpOnly", "secure", "sameSite", "path")} for cookie in cookies]
        self.observe("cookie_metadata", metadata)
        names = {cookie["name"]: cookie for cookie in cookies}
        require(names.get("dealer_session", {}).get("httpOnly") is True, "会话 Cookie 必须 HttpOnly")
        require(names.get("dealer_session", {}).get("sameSite") == "Strict", "会话 Cookie 必须 SameSite=Strict")
        require(names.get("dealer_csrf", {}).get("httpOnly") is False, "CSRF Cookie 合同不匹配")
        return user

    async def ready(self):
        await self.page.locator(INPUT).wait_for(state="visible")
        await self.page.wait_for_function("() => { const x=document.querySelector('#business-assistant-input'); return x && !x.readOnly; }")

    async def send(self, text, *, keyboard=False, wait=True):
        await self.fill(INPUT, text, "输入事项")
        self.latest_run = None
        if keyboard:
            await self.key(INPUT, "Enter")
        else:
            await self.click(SEND, "发送")
        if wait:
            await self.wait(lambda: self.latest_run, "实际 UI 发送创建 Run")
            run_id = self.latest_run
            await self.wait(lambda: self.db.rows("SELECT status FROM business_assistant_runs WHERE id=?", (run_id,))[0]["status"] in ("succeeded", "failed", "cancelled"), "Run 原始终态", timeout=40)
            await self.page.wait_for_function("() => !document.querySelector('[data-ba-action=stop]')", timeout=40000)
            await self.ready()
        return self.latest_session

    async def new_matter(self):
        await self.click('[data-ba-action="new"]', "新对话")
        await self.page.wait_for_function("() => document.querySelector('#ba-current-heading')?.textContent === '新对话'")
        self.latest_session = None

    async def finish(self):
        if self.response_jobs:
            await asyncio.gather(*list(self.response_jobs))
        save_json(self.directory / "actions.json", self.actions)
        save_json(self.directory / "network.json", self.network)
        save_json(self.directory / "observations.json", self.observations)
        return {"actions": len(self.actions), "clicks": sum(a["kind"] == "click" for a in self.actions),
                "readonly_http_checks": sum(a["kind"] == "readonly_http" for a in self.actions),
                "protected_conflicts": self.protected_conflicts,
                "native_keyboard_actions": sum(a["kind"] == "keyboard" for a in self.actions),
                "evidence": str(self.directory)}


async def welcome(e, context, credentials):
    before = e.db.counts()
    sessions = e.db.rows("SELECT count(*) AS n FROM business_assistant_sessions")[0]["n"]
    await e.login(context, credentials, default_home=True)
    await e.ready()
    business_before = e.business_snapshot("original_business_before_welcome")
    await e.wait(lambda: e.workspace_features, "原生工作区响应的实际功能开关")
    require(e.workspace_features["home"] is True, "当前隔离场景未实际开启默认助手首页")
    await expect(e.page.locator("#main h1")).to_have_text("业务助手")
    require(await e.page.locator(INPUT).is_visible(), "home=true 无hash新登录未显示助手输入区")
    e.observe("default_home_native_contract", {"login_origin_has_no_hash": True, "workspace_features": e.workspace_features, "heading": await e.page.locator("#main h1").inner_text()})
    suggestions = e.page.locator('[data-ba-action="suggestion"]')
    require(1 <= await suggestions.count() <= 4, "欢迎建议应显示 1 至 4 条")
    for width in (390, 768, 1440):
        e.action("viewport", "浏览器宽度", width=width, height=1000)
        await e.page.set_viewport_size({"width": width, "height": 1000})
        measurements = await e.page.evaluate("""() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
          buttons:[...document.querySelectorAll('#business-assistant button')].filter(x=>x.getClientRects().length)
          .map(x=>({label:x.textContent.trim(),disabled:x.disabled,width:x.getBoundingClientRect().width}))})""")
        e.observe(f"layout_{width}", measurements)
        require(measurements["scrollWidth"] <= width + 1, f"{width} 宽度页面横向溢出")
        require(all(button["label"] and len(button["label"]) <= 30 for button in measurements["buttons"]), "核心按钮文案为空或过长")
        await e.page.locator(INPUT).scroll_into_view_if_needed()
        require(await e.page.locator(INPUT).is_visible(), f"{width} 输入框不可见")
        # Suggestions are actionable at all three widths and do not send.
        await e.fill(INPUT, "", "清空未发草稿")
        suggestion_label = (await e.page.locator('[data-ba-action="suggestion"]:first-of-type').inner_text()).strip()
        await e.click('[data-ba-action="suggestion"]:first-of-type', "欢迎建议")
        suggested_draft = await e.page.locator(INPUT).input_value()
        require(suggested_draft.strip() and len(suggested_draft) <= 80 and "\n" not in suggested_draft and "\r" not in suggested_draft,
                "建议应预填不超过 80 字的单行目标")
        require(suggestion_label in suggested_draft, "建议预填未包含员工所点业务名称")
        await e.snapshot(f"welcome-{width}")
    await e.fill(INPUT, "未发草稿：明天下午回访张先生", "已有草稿")
    await e.click('[data-ba-action="suggestion"]:first-of-type', "已有草稿时点击建议")
    require(await e.page.locator(INPUT).input_value() == "未发草稿：明天下午回访张先生", "建议覆盖未发草稿")
    await e.click('[data-ba-action="new"]', "已有草稿时新对话")
    require(await e.page.locator(INPUT).input_value() == "未发草稿：明天下午回访张先生", "新对话覆盖未发草稿")
    await e.fill(INPUT, "", "清空未发草稿")
    await e.page.locator(INPUT).focus()
    e.action("keyboard", INPUT, key="原生 insert_text 中文")
    await e.page.keyboard.insert_text("查询本店张姓客户")
    await e.key(INPUT, "Shift+Enter")
    require(await e.page.locator(INPUT).input_value() == "查询本店张姓客户\n", "Shift+Enter 未保留中文并换行")
    await e.key(INPUT, "ArrowLeft")
    focus = await e.page.locator(INPUT).evaluate("x => ({focused:document.activeElement===x,start:x.selectionStart,end:x.selectionEnd})")
    # The existing client really polls every 30 seconds. Observe that request,
    # rather than claiming a short idle wait exercised background rendering.
    e.action("await_native_refresh", "保持输入焦点等待真实通知轮询")
    refresh = await e.page.wait_for_event("response", predicate=lambda r: urlsplit(r.url).path == "/api/business-assistant/notifications", timeout=35000)
    require(refresh.status == 200, "保持输入时通知读取失败")
    # In pinned Playwright 1.56 Response.finished() leaves its target-close
    # watcher pending after success. body() waits for this actual JSON response
    # to complete without that detached task; bytes are not written to evidence.
    await refresh.body()
    await e.page.wait_for_timeout(100)
    after_focus = await e.page.locator(INPUT).evaluate("x => ({focused:document.activeElement===x,start:x.selectionStart,end:x.selectionEnd})")
    require(focus == after_focus and focus["focused"], "后台刷新移走输入焦点或光标")
    require(e.db.rows("SELECT count(*) AS n FROM business_assistant_sessions")[0]["n"] == sessions, "建议/草稿/换行错误创建会话")
    require(e.db.counts() == before, "欢迎交互写入业务数据")
    e.business_unchanged(business_before, "original_business_after_welcome")
    await e.snapshot("draft-keyboard")


async def manual_navigation(e, context, credentials):
    await e.login(context, credentials)
    await e.ready()
    await e.fill(INPUT, "导航前未发草稿", "未发草稿")
    # Navigate within the real document first: unsent draft must survive.
    await e.click('.sidebar details:has(a[href="#master/customers"]) > summary', "展开原客户管理导航")
    await e.click('a[href="#master/customers"]', "原人工客户模块")
    await expect(e.page.locator("#main h1")).to_contain_text("客户")
    await e.snapshot("manual-customer-module")
    await e.click('a[href="#business-assistant"]', "原导航返回业务助手")
    await e.ready()
    require(await e.page.locator(INPUT).input_value() == "导航前未发草稿", "原人工模块往返丢失未发草稿")
    await e.fill(INPUT, "", "清空未发草稿")
    await e.click('[data-act="logout"]', "退出以验证深链接登录")
    await e.page.locator('input[name="username"]').wait_for(state="visible")
    await e.login(context, credentials, route="master/customers")
    await expect(e.page.locator("#main h1")).to_contain_text("客户")
    require(urlsplit(e.page.url).fragment == "master/customers", "有效人工深链接登录后被默认助手入口覆盖")
    await e.snapshot("manual-published-deeplink")
    e.observe("navigation_note", "整页深链接刷新会重建会话内存；此处不声称跨刷新持久保存业务草稿。")


async def readonly_query(e, context, credentials):
    user = await e.login(context, credentials)
    await e.ready()
    before = e.db.counts()
    business_before = e.business_snapshot("original_business_before_readonly")
    cards = len(e.db.proposals(user["id"]))
    await e.send("查询本店张姓客户", keyboard=True)
    await e.page.locator(".ba-message.ba-assistant").wait_for(state="visible")
    customer_id = e.manifest["domain_samples"]["customer_id"]
    customer = e.db.rows("SELECT id,name,store_id,owner_id FROM flow_customers WHERE id=?", (customer_id,))[0]
    require(customer["owner_id"] == user["id"], "只读查询合成客户不属当前销售")
    await expect(e.page.locator(".ba-message.ba-assistant").last).to_contain_text(customer["name"])
    e.observe("queried_customer_database", customer)
    # Supplemental backend consistency path: the actual browser cookie jar,
    # explicit current store, GET only, and the real domain serializer.
    member_id = e.manifest["domain_samples"]["group_member_id"]
    wallet = e.db.rows("SELECT id,identity_id,number,version,balance_cents,reserved_cents,active FROM group_members WHERE id=?", (member_id,))[0]
    expected_wallet = {**wallet, "active": bool(wallet["active"]), "available_cents": wallet["balance_cents"] - wallet["reserved_cents"]}
    store_id = await e.page.locator("#store").input_value()
    e.action("readonly_http", "当前销售本人客户的集团会员详情", path=f"/api/group/members/{member_id}")
    response = await context.request.get(e.origin + f"/api/group/members/{member_id}", headers={"X-Store-ID": store_id, "X-App-Request": "1"})
    require(response.status == 200, "真实 Cookie 会员详情未读取成功")
    body = await response.json()
    require(body["member"] == expected_wallet, "真实会员详情与数据库钱包字段不匹配")
    require(body["entries"] == [] and body["reservations"] == [] and body["refund_requests"] == [], "合成新会员返回不实流水")
    e.network.append({"event": "readonly_domain_response", "path": f"/api/group/members/{member_id}", "method": "GET", "status": response.status, "store_id": store_id, "same_origin": True, "cookie_jar": "browser_context"})
    e.observe("member_domain_database_match", {"member": body["member"], "database": expected_wallet})
    e.action("readonly_http", "当前本人客户的集团权益详情", path=f"/api/group/benefits/members/{member_id}")
    benefits_response = await context.request.get(e.origin + f"/api/group/benefits/members/{member_id}", headers={"X-Store-ID": store_id, "X-App-Request": "1"})
    require(benefits_response.status == 200, "真实 Cookie 集团权益详情未读取成功")
    benefits_detail = await benefits_response.json()
    require(benefits_detail["member"] == expected_wallet == body["member"], "新增权益详情与原会员/数据库不匹配")
    wallet_ids = e.db.rows("SELECT id FROM benefit_wallets WHERE member_id=?", (member_id,))
    require(wallet_ids == [], "本场景的新会员未实际获授或发行权益，应无权益钱包")
    require(all(benefits_detail[key] == [] for key in ("wallets", "entries", "reservations", "refunds")), "无权益钱包却返回虚构流水")
    require(benefits_detail["history_limit"] == 100 and benefits_detail["history_may_be_truncated"] == {"entries": False, "reservations": False, "refunds": False}, "新增权益详情未明确真实历史边界")
    e.network.append({"event": "readonly_domain_response", "path": f"/api/group/benefits/members/{member_id}", "method": "GET", "status": benefits_response.status, "store_id": store_id, "same_origin": True, "cookie_jar": "browser_context"})
    e.observe("benefits_domain_database_match", {"member": benefits_detail["member"], "wallet_ids": wallet_ids, "history_limit": benefits_detail["history_limit"], "history_may_be_truncated": benefits_detail["history_may_be_truncated"]})
    purchase_id = e.manifest["domain_samples"]["package_purchase_id"]
    purchase = e.db.rows("SELECT id,member_id,status,version,issuer_store_id FROM repair_package_purchases WHERE id=?", (purchase_id,))[0]
    require(purchase["member_id"] == member_id and purchase["issuer_store_id"] == int(store_id), "套餐预置与当前本人客户/门店不匹配")
    require(purchase["status"] == "proposed", "本场景要求原服务生成的未实际收款套餐购买")
    e.action("readonly_http", "当前销售本人客户的维修套餐购买详情", path=f"/api/repair-packages/purchases/{purchase_id}")
    package_response = await context.request.get(e.origin + f"/api/repair-packages/purchases/{purchase_id}", headers={"X-Store-ID": store_id, "X-App-Request": "1"})
    require(package_response.status == 200, "真实 Cookie 套餐购买详情未读取成功")
    package_detail = await package_response.json()
    fields = ("id", "member_id", "status", "version")
    require({key: package_detail[key] for key in fields} == {key: purchase[key] for key in fields}, "套餐详情状态/身份/版本与数据库不匹配")
    captures = e.db.rows("SELECT e.id,e.store_id,e.lot_id,e.case_id,e.purpose,e.hold_id,e.quantity_milli FROM repair_package_entries e JOIN repair_package_lots l ON l.id=e.lot_id WHERE l.purchase_id=? AND e.store_id=? AND e.purpose='capture' ORDER BY e.id DESC", (purchase_id, int(store_id)))
    require(package_detail["capture_entries"] == captures and package_detail["capture_entry_limit"] == 500, "套餐详情本店核销来源与数据库不匹配")
    require(captures == [] and package_detail["lots"] == [] and package_detail["refunds"] == [], "未实际发行的套餐不应有发行组件、核销或退款流水")
    require("cash_id" not in package_detail and "account_id" not in package_detail, "普通销售详情泄露超出原岗位的现金字段")
    e.network.append({"event": "readonly_domain_response", "path": f"/api/repair-packages/purchases/{purchase_id}", "method": "GET", "status": package_response.status, "store_id": store_id, "same_origin": True, "cookie_jar": "browser_context"})
    e.observe("package_domain_database_match", {"purchase": {key: purchase[key] for key in fields}, "capture_entries": captures, "capture_entry_limit": package_detail["capture_entry_limit"]})
    require(e.db.counts() == before, "只读查询写入原业务")
    e.business_unchanged(business_before, "original_business_after_readonly")
    require(len(e.db.proposals(user["id"])) == cards, "只读查询生成写入卡片")
    require(await e.page.locator(CONFIRM).count() == 0, "只读查询显示确认业务按钮")
    await e.snapshot("readonly-query")


async def customer_confirmation(e, context, credentials):
    user = await e.login(context, credentials)
    await e.ready()
    before = e.db.counts()
    business_before = e.business_snapshot("original_business_before_customer_prepare")
    suffix = hashlib.sha256(str(e.directory).encode()).hexdigest()[:10]
    name = "浏览器客户" + suffix
    session_id = await e.send("新建客户 " + name)
    cards = e.db.proposals(user["id"], session_id=session_id)
    require(len(cards) == 1 and cards[0]["status"] == "pending", "客户准备应恰有一张待确认卡")
    require(e.db.counts() == before, "准备客户卡前已写入原业务")
    e.business_unchanged(business_before, "original_business_after_customer_prepare")
    await e.page.set_viewport_size({"width": 390, "height": 1000})
    e.action("viewport", "手机确认卡", width=390, height=1000)
    await e.click('[data-ba-action="pane-cards"]', "手机办理事项页签")
    await e.page.locator(CONFIRM).wait_for(state="visible")
    require(name in await e.page.locator("[data-proposal]").inner_text(), "手机卡片缺少真实姓名事实")
    require(await e.page.evaluate("document.documentElement.scrollWidth <= innerWidth+1"), "手机卡片页面横向溢出")
    await e.snapshot("customer-prepared-mobile")
    async with e.page.expect_response(lambda r: urlsplit(r.url).path.endswith("/confirm")) as pending:
        await e.click(CONFIRM, "员工核对后确认办理")
    require((await pending.value).status == 200, "客户 UI 确认未成功")
    await e.page.locator(".ba-card-receipt").wait_for(state="visible")
    rows = e.db.rows("SELECT id,name,store_id,owner_id FROM flow_customers WHERE name=?", (name,))
    require(len(rows) == 1 and rows[0]["owner_id"] == user["id"], "确认后客户未恰有一行或员工不匹配")
    require(rows[0]["store_id"] == int(await e.page.locator("#store").input_value()), "确认后客户门店不匹配")
    require(name in await e.page.locator("#business-assistant-cards").inner_text(), "前端成功结果与新客户不匹配")
    after = e.db.counts()
    business_after_confirm = e.business_snapshot("original_business_after_customer_confirm")
    require(after["flow_customers"] == before["flow_customers"] + 1, "客户确认新增行数错误")
    require(all(after[t] == before[t] for t in TABLES if t != "flow_customers"), "客户确认产生意外其他业务")
    await e.snapshot("customer-confirmed")
    await e.page.set_viewport_size({"width": 1440, "height": 1000})
    await e.click('[data-ba-action="refresh"]', "刷新原结果")
    await e.ready()
    await e.click('[data-ba-action="history"]', "展开真实历史")
    await e.click(f'[data-ba-action="session"][data-id="{session_id}"]', "重开原对话")
    await e.ready()
    await e.click('[data-ba-action="queue-filter"][data-filter="history"]', "查看已结束卡")
    require(e.db.counts() == after, "刷新或历史重开重复写入")
    e.business_unchanged(business_after_confirm, "original_business_after_customer_history")
    require(await e.page.locator(CONFIRM).count() == 0, "已成功历史卡仍可重复确认")
    require(e.db.proposals(user["id"], session_id=session_id)[0]["status"] == "succeeded", "卡片数据库未记录成功")
    e.observe("customer_database", rows)
    await e.snapshot("customer-history")


async def followup(e, context, credentials):
    user = await e.login(context, credentials, "admin")
    await e.ready()
    ids = e.manifest["lead_plan"]["case_ids"]
    originals = [e.db.case(case_id) for case_id in ids]
    business_before = e.business_snapshot("original_business_before_plan")
    session_id = await e.send("浏览器接待计划")
    plans = e.db.rows("SELECT id FROM business_assistant_work_plans WHERE session_id=?", (session_id,))
    require(len(plans) == 1, "两步接待请求未生成唯一真实计划")
    plan_id = plans[0]["id"]
    steps = e.db.rows("SELECT key,position,depends_on,status FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (plan_id,))
    require(len(steps) == 2 and json.loads(steps[1]["depends_on"]) == [steps[0]["key"]], "计划未保存真实两步依赖")
    require([e.db.case(case_id) for case_id in ids] == originals, "计划创建改变原接待业务")
    await e.page.locator('[data-baws-followup="enable"]').wait_for(state="visible")
    await e.followup_click("enable", "开启此事项持续跟进")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_followup_grants WHERE plan_id=? AND status='active'", (plan_id,)), "真实跟进授权生效")
    await e.wait(lambda: len(e.db.proposals(user["id"], session_id=session_id)) == 1, "后台只准备真实第一步", timeout=40)
    require([e.db.case(case_id) for case_id in ids] == originals, "持续跟进自动提交原业务")
    e.business_unchanged(business_before, "original_business_after_followup_prepare")
    await e.followup_click("pause", "暂停跟进")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_followup_grants WHERE plan_id=? AND status='paused'", (plan_id,)), "暂停授权")
    await expect(e.page.locator("#ba-current-plan .ba-plan-grant")).to_contain_text("已暂停跟进")
    await e.snapshot("followup-paused")
    # Confirming original business remains independent of paused preparation.
    # Cross a real worker check interval, then prove no dependent card appeared.
    await e.click('[data-ba-action="refresh"]', "读取后台已准备卡")
    await e.ready()
    await e.page.locator(CONFIRM).wait_for(state="visible")
    async with e.page.expect_response(lambda r: urlsplit(r.url).path.endswith("/confirm")) as pending:
        await e.click(CONFIRM, "确认第一步真实接待分派")
    require((await pending.value).status == 200, "第一步原业务确认失败")
    await e.wait(lambda: e.db.case(ids[0])["state"] == "contacting", "真实第一步接待事实")
    require(e.db.case(ids[0])["owner_id"] == e.manifest["lead_plan"]["assignee_id"], "第一步分派员工不匹配")
    business_after_confirm = e.business_snapshot("original_business_after_plan_first_confirmation")
    await e.page.wait_for_timeout(6000)
    require(len(e.db.proposals(user["id"], session_id=session_id)) == 1, "暂停后仍自动准备依赖后继")
    require(e.db.case(ids[1]) == originals[1], "暂停时改动第二步原业务")
    await e.followup_click("resume", "恢复跟进")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_followup_grants WHERE plan_id=? AND status='active'", (plan_id,)), "恢复授权")
    await expect(e.page.locator("#ba-current-plan .ba-plan-grant")).to_contain_text("持续跟进中")
    await e.wait(lambda: len(e.db.proposals(user["id"], session_id=session_id)) == 2, "真实前序完成后准备第二步", timeout=40)
    require(e.db.case(ids[1]) == originals[1], "第二步未确认却改变原业务")
    e.business_unchanged(business_after_confirm, "original_business_after_dependent_prepare")
    await e.click('[data-ba-action="refresh"]', "查看依赖后继卡")
    await e.ready()
    await e.click('[data-ba-action="queue-filter"][data-filter="pending"]', "查看第二步待确认卡")
    pending_cards = [card for card in e.db.proposals(user["id"], session_id=session_id) if card["status"] == "pending"]
    require(len(pending_cards) == 1, "后继必须恰有一张真实待确认卡")
    second_card = pending_cards[0]
    payload = json.loads(e.db.rows("SELECT payload FROM business_assistant_proposals WHERE id=?", (second_card["id"],))[0]["payload"])
    require(payload["path_args"]["case_id"] == ids[1], "后继卡未绑定真实第二原单")
    second_case = e.db.rows("SELECT id,number,title FROM flow_cases WHERE id=?", (ids[1],))[0]
    card = e.page.locator(f'[data-proposal="{second_card["id"]}"]')
    await card.wait_for(state="visible")
    await expect(card).to_contain_text(second_case["number"])
    await expect(card).to_contain_text(second_case["title"])
    require(await card.locator(f'a[href="#case/{ids[1]}"]').count() >= 1, "后继卡缺少第二原单的真实深链接")
    e.observe("dependent_pending_card_identity", {"proposal_id": second_card["id"], "case_id": second_case["id"], "number": second_case["number"], "title": second_case["title"]})
    await e.snapshot("followup-dependent-card")
    await e.click('[data-baws-followup="revoke"]', "结束这件事第一次核对")
    await expect(e.page.locator('[data-baws-followup="revoke"]')).to_have_text("确认结束这件事")
    await e.followup_click("revoke", "确认结束这件事")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_followup_grants WHERE plan_id=? AND status='revoked'", (plan_id,)), "授权真实撤销")
    require(e.db.case(ids[0])["state"] == "contacting" and e.db.case(ids[1]) == originals[1], "结束跟进改动原业务")
    cards = e.db.proposals(user["id"], session_id=session_id)
    require(sorted(card["status"] for card in cards) == ["pending", "succeeded"], "结束跟进取消或覆盖已有卡")
    e.observe("followup_database", {"plan_id": plan_id, "steps": steps, "cases": [e.db.case(case_id) for case_id in ids], "cards": cards})
    await e.snapshot("followup-revoked")
    await review_followup_ui(e, session_id, plan_id, second_card["id"], ids[1])


async def slow_switch(e, context, credentials):
    user = await e.login(context, credentials)
    await e.ready()
    before = e.db.counts()
    business_before = e.business_snapshot("original_business_before_slow_switch")
    await e.send("慢速查询换店", wait=False)
    await e.wait(lambda: e.latest_run, "慢查询实际提交")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]["status"] == "running", "慢查询确已启动")
    e.observe("run_before_store_switch", {"id": e.latest_run, "status": "running"})
    origin_store = await e.page.locator("#store").input_value()
    target = next(store for store in e.manifest["stores"] if str(store["id"]) != origin_store)
    e.action("select", "当前门店", value=str(target["id"]))
    await e.page.locator("#store").select_option(str(target["id"]))
    await e.ready()
    await e.page.wait_for_timeout(3000)
    require(await e.page.locator("#store").input_value() == str(target["id"]), "慢响应恢复了旧门店")
    require(await e.page.locator(INPUT).input_value() == "", "换店未清理原草稿")
    require("慢速查询换店" not in await e.page.locator("#business-assistant-messages").inner_text(), "迟到回复污染新门店")
    require(e.db.counts() == before, "慢查询换店产生业务写入")
    e.business_unchanged(business_before, "original_business_after_slow_switch")
    require(not e.db.proposals(user["id"], session_id=e.latest_session), "慢只读查询生成卡")
    await e.snapshot("slow-store-switch")


async def slow_logout(e, context, credentials):
    await e.login(context, credentials)
    await e.ready()
    before = e.db.counts()
    business_before = e.business_snapshot("original_business_before_slow_logout")
    await e.send("慢速查询退出", wait=False)
    await e.wait(lambda: e.latest_run, "慢查询实际提交")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]["status"] == "running", "慢查询确已启动")
    e.observe("run_before_logout", {"id": e.latest_run, "status": "running"})
    await e.click('[data-act="logout"]', "退出登录")
    await e.page.locator('input[name="username"]').wait_for(state="visible")
    await e.page.wait_for_timeout(3000)
    require(await e.page.locator(INPUT).count() == 0, "退出后迟到响应恢复助手")
    require("慢速查询退出" not in await e.page.locator("body").inner_text(), "迟到内容污染登录页")
    require(not any(cookie["name"] in {"dealer_session", "dealer_csrf"} for cookie in await context.cookies()), "退出未清 Cookie")
    require(e.db.counts() == before, "慢查询退出产生业务写入")
    e.business_unchanged(business_before, "original_business_after_slow_logout")
    def cancelled():
        rows = e.db.rows("SELECT id,owner_id,session_id,status,lease_owner,lease_until,finished_at,event_seq FROM business_assistant_runs WHERE id=?", (e.latest_run,))
        require(len(rows) == 1, "退出后的原Run不存在")
        return rows[0] if rows[0]["status"] == "cancelled" else None
    terminal = await e.wait(cancelled, "退出后原Run及时取消")
    require(terminal["lease_owner"] is None and terminal["lease_until"] is None and terminal["finished_at"], "退出后的原Run未释放租约")
    events = e.db.rows("SELECT seq,type FROM business_assistant_run_events WHERE run_id=? ORDER BY seq", (terminal["id"],))
    require(events and events[-1]["type"] == "run.cancelled" and events[-1]["seq"] == terminal["event_seq"], "退出后的原取消事件不完整")
    require(not e.db.proposals(terminal["owner_id"], session_id=terminal["session_id"]), "退出慢查询生成了写入卡片")
    e.business_unchanged(business_before, "original_business_after_logout_terminal")
    e.observe("logout_cancelled_terminal", {"run": terminal, "events": events, "card_count": 0})
    await e.snapshot("slow-logout")
    # Exercise the employee's recovery through the same native login form.
    # The prior Run must remain cancelled and its late text must not return.
    await e.login(context, credentials)
    await e.ready()
    require(await e.page.locator(INPUT).input_value() == "", "重新登录恢复了已退出的草稿")
    require("慢速查询退出" not in await e.page.locator("#business-assistant-messages").inner_text(), "重新登录带回迟到内容")
    recovered_business = e.business_snapshot("original_business_before_logout_recovery_query")
    await e.send("查询本店张姓客户")
    recovered = e.db.rows("SELECT id,owner_id,session_id,status FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    require(recovered["status"] == "succeeded" and recovered["owner_id"] == terminal["owner_id"]
            and recovered["session_id"] != terminal["session_id"], "重新登录查询未建立本人新上下文")
    require(e.db.rows("SELECT status FROM business_assistant_runs WHERE id=?", (terminal["id"],))[0]["status"] == "cancelled", "恢复查询改变原取消Run")
    require(not e.db.proposals(recovered["owner_id"], session_id=recovered["session_id"]), "重新登录只读查询制造卡片")
    e.business_unchanged(recovered_business, "original_business_after_logout_recovery_query")
    e.observe("logout_native_recovery", {"run": recovered, "old_run_still_cancelled": True,
                                         "empty_draft_after_login": True, "card_count": 0})
    await e.snapshot("slow-logout-native-recovery")


async def protocol_error(e, context, credentials):
    user = await e.login(context, credentials)
    await e.ready()
    before = e.db.counts()
    business_before = e.business_snapshot("original_business_before_protocol_error")
    count = len(e.db.proposals(user["id"]))
    await e.send("模拟异常")
    error = await e.page.locator("#business-assistant-error").inner_text()
    status = await e.page.locator("#business-assistant-messages").inner_text()
    require(error.strip() or any(word in status for word in ("失败", "未完成", "中断", "无法")), "协议异常未向员工显示失败")
    require(len(e.db.proposals(user["id"])) == count and e.db.counts() == before, "协议异常产生卡片或业务")
    e.business_unchanged(business_before, "original_business_after_protocol_error")
    await e.snapshot("protocol-error")
    failed_run = e.latest_run
    await e.send("查询本店张姓客户")
    recovered = e.db.rows("SELECT id,owner_id,session_id,status FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    require(recovered["id"] != failed_run and recovered["owner_id"] == user["id"]
            and recovered["status"] == "succeeded", "协议异常后原界面未能继续有效查询")
    require(not (await e.page.locator("#business-assistant-error").inner_text()).strip(), "有效查询后仍显示旧协议错误")
    require(len(e.db.proposals(user["id"])) == count and e.db.counts() == before, "异常恢复查询产生卡片或业务")
    e.business_unchanged(business_before, "original_business_after_protocol_recovery")
    e.observe("protocol_native_recovery", {"failed_run": failed_run, "recovered_run": recovered,
                                           "old_error_cleared": True, "business_unchanged": True})
    await e.snapshot("protocol-error-native-recovery")


async def security(e, context, credentials):
    user = await e.login(context, credentials)
    await e.ready()
    before = e.db.counts()
    business_before = e.business_snapshot("original_business_before_security_readonly")
    await e.send("查询本店张姓客户")
    e.business_unchanged(business_before, "original_business_after_security_readonly")
    require(any(item.get("native_sse") for item in e.network), "未观察到原生 SSE 响应")
    writes = [item for item in e.network if item["event"] == "request" and item["method"] == "POST" and item["path"] != "/api/auth/login"]
    require(writes and all(item["csrf_present"] and item["cookie_present"] for item in writes), "原生助手写缺少 Cookie/CSRF")
    csp = [item["csp"] for item in e.network if item["event"] == "response" and item["path"] == "/"]
    require(csp and all("script-src 'self'" in value and "connect-src 'self'" in value and "object-src 'none'" in value for value in csp), "同源 CSP 未保留")
    sessions_before = e.db.rows("SELECT count(*) AS n FROM business_assistant_sessions")[0]["n"]
    old_refusals = e.db.rows("SELECT * FROM escalation_refusals ORDER BY id")
    e.action("security_negative", "缺 CSRF 的建会话写请求")
    missing_csrf = await context.request.post(e.origin + "/api/business-assistant/sessions", data={}, headers={"X-Store-ID": str(e.manifest["stores"][0]["id"]), "X-App-Request": "1"})
    require(missing_csrf.status == 403, "缺 CSRF 的写请求未拒绝")
    require(e.db.rows("SELECT count(*) AS n FROM business_assistant_sessions")[0]["n"] == sessions_before, "缺 CSRF 拒绝后仍写会话")
    e.action("security_negative", "普通销售伪造 Runtime/Admin 身份头")
    forged = await context.request.get(e.origin + "/api/users", headers={"X-Store-ID": str(e.manifest["stores"][0]["id"]), "X-User-ID": str(e.manifest["users"]["admin"]["id"]), "X-Role": "admin", "X-Assistant-Runtime": "1"})
    require(forged.status == 403, "伪造身份头绕过真实销售权限")
    refusal_response = await forged.json()
    refusals = e.db.rows("SELECT * FROM escalation_refusals ORDER BY id")
    require(refusals[:len(old_refusals)] == old_refusals and len(refusals) == len(old_refusals) + 1,
            "故意权限拒绝没有仅追加唯一原拒绝记录")
    refusal = refusals[-1]
    require(refusal["id"] == refusal_response["refusal"]["id"] and refusal["user_id"] == user["id"]
            and refusal["store_id"] == e.manifest["stores"][0]["id"] and refusal["role"] == "sales"
            and refusal["method"] == "GET" and refusal["path"] == "/api/users" and refusal["status_code"] == 403
            and refusal["message"] == refusal_response["detail"] and refusal["category"] == refusal_response["refusal"]["category"] == "rule"
            and refusal_response["refusal"]["can_escalate"] is False
            and refusal["source"] == "page" and refusal["consumed_at"] is None and refusal["consumed_by_id"] is None,
            "原403拒绝记录未绑定真实本人门店与服务器refusal")
    after_negative = e.business_snapshot("original_business_after_deliberate_security_refusal")
    require({k: v for k, v in business_before["tables"].items() if k != "escalation_refusals"}
            == {k: v for k, v in after_negative["tables"].items() if k != "escalation_refusals"},
            "安全拒绝改写原拒绝记录以外的业务事实")
    e.observe("original_security_refusal", {"id": refusal["id"], "path": refusal["path"],
        "user_id": refusal["user_id"], "store_id": refusal["store_id"], "old_rows_unchanged": True,
        "all_other_business_tables_unchanged": True})
    business_before = after_negative
    require(e.db.counts() == before, "安全拒绝探测改变业务数据")
    e.observe("negative_statuses", {"missing_csrf": missing_csrf.status, "forged_identity": forged.status, "actual_user": user["id"]})
    await e.snapshot("native-security")
    reconnect_requests, interrupted_requests, native_requests = [], [], {}
    cdp = await context.new_cdp_session(e.page)
    await cdp.send("Network.enable")
    def capture_native_request(event):
        parsed = urlsplit(event["request"]["url"])
        if parsed.path.startswith("/api/business-assistant/runs/") and parsed.path.endswith("/events"):
            native_requests[event["requestId"]] = parsed.path.split("/")[-2]
    def capture_interruption(event):
        run_id = native_requests.get(event["requestId"])
        if run_id:
            interrupted_requests.append({"run_id": run_id, "request_id": event["requestId"],
                                         "error": event["errorText"], "cancelled": event.get("canceled", False)})
    cdp.on("Network.requestWillBeSent", capture_native_request)
    cdp.on("Network.loadingFailed", capture_interruption)
    def capture_cursor(request):
        parsed = urlsplit(request.url)
        if request.method == "GET" and parsed.path.startswith("/api/business-assistant/runs/") and parsed.path.endswith("/events"):
            reconnect_requests.append({"run_id": parsed.path.split("/")[-2],
                                       "after_seq": int(parse_qs(parsed.query)["after_seq"][0])})
    e.page.on("request", capture_cursor)
    try:
        await e.send("慢速查询断网补读", wait=False)
        await e.wait(lambda: e.latest_run, "断网查询实际Run")
        run_id = e.latest_run
        await e.page.wait_for_function("id => globalThis.AssistantRuntime?.snapshot(id)?.lastAppliedSeq > 0", arg=run_id)
        cursor = await e.page.evaluate("id => globalThis.AssistantRuntime.snapshot(id).lastAppliedSeq", run_id)
        e.action("network", "原生浏览器离线", run_id=run_id, last_applied_seq=cursor)
        await context.set_offline(True)
        try:
            # Offline mode alone leaves an already-open SSE fetch alive in Chrome.
            # Stop actual resource loading, preserving the page and Runtime memory.
            await cdp.send("Page.stopLoading")
            await e.wait(lambda: any(r["run_id"] == run_id for r in interrupted_requests), "原事件请求真实中断")
            await e.page.wait_for_function("id => globalThis.AssistantRuntime?.snapshot(id)?.connectionState === 'reconnecting'", arg=run_id)
            disconnected = await e.page.evaluate("id => globalThis.AssistantRuntime.snapshot(id).lastAppliedSeq", run_id)
            e.observe("native_sse_interruption", {"run_id": run_id, "cursor_before_offline": cursor,
                "disconnected_cursor": disconnected, "failed_requests": interrupted_requests.copy(),
                "method": "Chrome Page.stopLoading while offline; original document retained"})
            terminal = await e.wait(lambda: next((r for r in e.db.rows("SELECT id,status,event_seq,session_id FROM business_assistant_runs WHERE id=?", (run_id,)) if r["status"] == "succeeded"), None), "离线期间服务器真实终态")
            offline_seq = await e.page.evaluate("id => globalThis.AssistantRuntime.snapshot(id).lastAppliedSeq", run_id)
            require(offline_seq == disconnected < terminal["event_seq"], "离线已中断原流却仍收到后继事件或未留下补读缺口")
        finally:
            e.action("network", "原生浏览器恢复联网", run_id=run_id)
            await context.set_offline(False)
        await e.page.wait_for_function("id => globalThis.AssistantRuntime?.snapshot(id)?.view?.status === 'succeeded' && !document.querySelector('[data-ba-action=stop]')", arg=run_id)
        applied = await e.page.evaluate("id => globalThis.AssistantRuntime.snapshot(id).lastAppliedSeq", run_id)
        requests = [r for r in reconnect_requests if r["run_id"] == run_id]
        e.observe("native_sse_reconnect_cursor_diagnostic", {"run": terminal, "before_offline_seq": cursor,
                                                           "after_online_seq": applied, "requests": requests})
        require(applied == terminal["event_seq"] and any(r["after_seq"] == disconnected and r["after_seq"] > 0 for r in requests), "断网恢复未按真实seq补读到终态")
        events = e.db.rows("SELECT seq,type FROM business_assistant_run_events WHERE run_id=? ORDER BY seq", (run_id,))
        require([r["seq"] for r in events] == list(range(1, applied + 1)) and events[-1]["type"] == "run.completed", "原事件序列不完整")
        require(not e.db.proposals(user["id"], session_id=terminal["session_id"]), "断网只读恢复制造卡片")
        e.business_unchanged(business_before, "original_business_after_native_sse_reconnect")
        e.observe("native_sse_reconnect", {"run": terminal, "before_offline_seq": cursor, "after_reconnect_seq": applied,
                                           "requests": requests, "events": events, "card_count": 0})
        await e.snapshot("native-sse-reconnected")
    finally:
        e.page.remove_listener("request", capture_cursor)
        await cdp.detach()
    await native_browser_restart(e, context, credentials, user)


async def native_browser_restart(e, original_context, credentials, user):
    """Close an actual independent Chrome; recover through native login/history."""
    import system_management_business as SYS
    original_page = e.page
    actor = e.db.rows("SELECT id,username,role,active,must_change_password FROM users WHERE id=?", (user["id"],))[0]
    password = credentials["users"]["sales"]["password"]
    source_session = source_run = None
    async with async_playwright() as p:
        for phase in ("before_restart", "after_restart"):
            browser = await p.chromium.launch(executable_path=e.manifest["browser"]["executable"], headless=True)
            separate = await browser.new_context()
            page = await separate.new_page()
            await e.attach(separate, page)
            try:
                identity = await SYS.native_login(e, actor, password)
                require(identity["user_id"] == user["id"] and identity["active_store_id"] == 1, "重启Chrome身份/门店不符")
                baseline = e.business_snapshot("browser_" + phase + "_after_native_login")
                await e.click('.sidebar a[href="#business-assistant"]', "原导航返回业务助手")
                await e.ready()
                if phase == "before_restart":
                    await e.send("查询本店张姓客户")
                    source_session, source_run = e.latest_session, e.latest_run
                else:
                    count = e.db.rows("SELECT count(*) AS n FROM business_assistant_runs WHERE owner_id=?", (user["id"],))[0]["n"]
                    await e.click('[data-ba-action="history"]', "重启后本人历史对话")
                    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/business-assistant/sessions/" + source_session):
                        await e.click('[data-ba-action="session"][data-id="' + source_session + '"]', "读取重启前原会话，不重新发送")
                    await e.ready()
                    require(e.db.rows("SELECT count(*) AS n FROM business_assistant_runs WHERE owner_id=?", (user["id"],))[0]["n"] == count, "重启恢复重发原Run")
                    run = e.db.rows("SELECT id,owner_id,session_id,status FROM business_assistant_runs WHERE id=?", (source_run,))[0]
                    require(run["owner_id"] == user["id"] and run["session_id"] == source_session and run["status"] == "succeeded", "重启恢复原Run归属/终态不符")
                    await expect(e.page.locator("#business-assistant-messages")).to_contain_text("本店客户：")
                    require(not e.db.proposals(user["id"], session_id=source_session), "重启恢复只读查询产生卡")
                    e.observe("native_browser_restart", {"original_run": run, "native_relogin": True, "run_not_resent": True, "card_count": 0})
                e.business_unchanged(baseline, "browser_" + phase + "_business_unchanged")
                await e.snapshot("native-browser-" + phase)
                if e.response_jobs:
                    await asyncio.gather(*list(e.response_jobs))
            finally:
                await separate.close()
                await browser.close()
    e.page = original_page


SCENARIOS = (
    ("runtime-preparation-process-crash", preparation_crash, 240),
    ("runtime-inflight-stop-before-prepare-response", inflight_stop, 90),
    ("runtime-batch-rule-failure-stops-remaining", batch_rule_failure, 120),
    ("runtime-batch-native-commit-result-lost", batch_result_unknown, 120),
    ("welcome-responsive-draft-keyboard", welcome, 130),
    ("manual-module-deeplink", manual_navigation, 130),
    ("readonly-query-no-card", readonly_query, 130),
    ("customer-prepare-confirm-history-mobile", customer_confirmation, 130),
    ("dependent-plan-followup-controls", followup, 130),
    ("slow-query-store-switch", slow_switch, 130),
    ("slow-query-logout", slow_logout, 130),
    ("provider-protocol-error-no-card", protocol_error, 130),
    ("native-cookie-csrf-csp-sse", security, 130),
) + REQUIREMENT_SCENARIOS + BUSINESS_SCENARIOS


def finalize_business_report(manifest, report):
    """Map only this run's registered checkpoints to the reviewed contracts.

    Automatic business results and the required human review stay separate.
    No earlier run, navigation result or fixture row contributes a passed check.
    """
    catalog = json.loads((Path(__file__).parent / "business_acceptance_catalog.json").read_text(encoding="utf-8"))
    contracts = {row["id"]: row for row in catalog["requirements"]}
    require(len(contracts) == len(catalog["requirements"]) == 193, "193项业务目录缺失或重复")
    contract_ids = {check["check_id"] for row in contracts.values() for check in row["acceptance_checks"]}
    require(len(contract_ids) == sum(len(row["acceptance_checks"]) for row in contracts.values()), "业务验收check_id重复")
    business_names = {name for name, _, _ in BUSINESS_SCENARIOS}
    results = {}
    for scenario in report["scenarios"]:
        if scenario["id"] not in business_names:
            continue
        path = Path(manifest["evidence_root"]) / scenario["id"] / "business-checkpoint.json"
        require(path.is_file(), "实际业务场景缺少逐项checkpoint：" + scenario["id"])
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        require(checkpoint.get("scenario") == scenario["id"], "业务checkpoint串场景")
        for row in checkpoint["requirements"]:
            require(row["id"] in contracts, "业务checkpoint含未知需求")
            expected = {check["check_id"] for check in contracts[row["id"]]["acceptance_checks"]}
            for check in row["acceptance_checks"]:
                key = check["check_id"]
                require(key in expected and key not in results, "业务checkpoint含未知、串需求或重复检查：" + key)
                results[key] = {"check_id": key, "status": check["status"],
                                "scenario": scenario["id"], "scenario_passed": scenario["status"] == "passed",
                                "checkpoint": str(path)}
    rows = []
    for key, contract in contracts.items():
        checks = [results.get(check["check_id"], {"check_id": check["check_id"], "status": "not_tested"})
                  for check in contract["acceptance_checks"]]
        complete = bool(checks) and all(check["status"] == "passed" and check.get("scenario_passed") for check in checks)
        status = "passed" if complete else "failed" if any(check["status"] == "failed" for check in checks) else "not_tested"
        rows.append({"id": key, "title": contract["title"], "automatic_status": status,
                     "checks": checks, "manual_review": "pending", "business_accepted": False})
    passed = sum(row["automatic_status"] == "passed" for row in rows)
    value = {"schema": 1, "scope": report["scope"], "requirements": rows,
             "catalog_requirements": 193, "automatic_requirements_passed": passed,
             "diagnostic_checks_passed": sum(check["status"] == "passed" for check in results.values()),
             "business_requirements_accepted": 0, "full193_business_acceptance": False,
             "manual_review": "pending", "historical_results_reused": False,
             "policy": "仅本次完整通过场景的所有目录检查计入自动结果；人工体验、文案和未执行异常路径仍需独立证据。"}
    save_json(Path(manifest["evidence_root"]) / "business-acceptance-report.json", value)
    return {key: value[key] for key in ("catalog_requirements", "automatic_requirements_passed",
            "diagnostic_checks_passed", "business_requirements_accepted", "full193_business_acceptance", "manual_review")}


async def run(manifest, credentials, executable, selected_names=()):
    secrets = [user["password"] for user in credentials["users"].values()]
    require(len(SCENARIOS) > 0, "空场景不能通过")
    registered_names = [name for name, _, _ in SCENARIOS]
    require(len(registered_names) == len(set(registered_names)), "注册场景重复")
    require(len(selected_names) == len(set(selected_names)), "定向场景重复")
    require(set(selected_names).issubset(registered_names), "定向场景没有对应注册实现")
    chosen = tuple(item for item in SCENARIOS if not selected_names or item[0] in selected_names)
    scope = "selected" if selected_names else "full_registered"
    report_path = Path(manifest["evidence_root"]) / "browser-click-report.json"
    report = {"schema": 1, "registered": len(chosen), "executed": 0, "passed_count": 0, "failed": 0,
              "expected_scenarios": [name for name, _, _ in chosen], "complete": False, "passed": False,
              "scope": scope, "all_registered_scenarios": registered_names,
              "full_registered_suite_complete": False, "full193_business_acceptance": False,
              "browser": manifest.get("browser", {}), "scenarios": [],
              "manual_review": {"status": "pending", "rubric": "rubric.json", "employee_efficiency": "not_measured"},
              "method": "当前真实 HTTP 服务；正业务原生 Playwright 点击；193需求/111指引/70共用原页面/9代表表单真实UI分层记录；3项Cookie只读API补充检查单独计数；合成模型；SQLite原业务全行摘要核对"}
    save_json(report_path, report)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=executable, headless=True)
        report["actual_browser_version"] = browser.version
        for name, scenario, timeout_seconds in chosen:
            e = Evidence(manifest, secrets, name)
            context = await browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
            page = await context.new_page()
            page.set_default_timeout(15000)
            await e.attach(context, page)
            started = time.monotonic()
            result = {"id": name, "status": "failed"}
            report["executed"] += 1
            try:
                await asyncio.wait_for(scenario(e, context, credentials), timeout=timeout_seconds)
                if e.response_jobs:
                    await asyncio.gather(*list(e.response_jobs))
                require(e.actions, "空点击场景不能通过")
                require(not e.page_errors, "出现未处理页面异常：" + "; ".join(e.page_errors))
                require(not e.external_requests, "浏览器尝试外部请求")
                failures = [item for item in e.network if item["event"] == "response" and item["status"] >= 500]
                require(not failures, "真实应用请求返回 5xx")
                result["status"] = "passed"
                report["passed_count"] += 1
            except Exception as error:
                result["error"] = e.scrub(f"{type(error).__name__}: {error}")
                report["failed"] += 1
                try:
                    await e.snapshot("failure")
                except Exception as screenshot_error:
                    result["screenshot_error"] = e.scrub(screenshot_error)
            finally:
                result["duration_seconds"] = round(time.monotonic() - started, 2)
                result.update(await e.finish())
                result["page_errors"] = e.page_errors
                result["external_attempts"] = e.external_requests
                report["scenarios"].append(result)
                save_json(report_path, report)
                await context.close()
            print(f"{name}: {result['status']}", flush=True)
        await browser.close()
    report["complete"] = report["registered"] == report["executed"] == len(report["scenarios"])
    report["passed"] = report["complete"] and report["passed_count"] == report["registered"] and report["failed"] == 0
    report["full_registered_suite_complete"] = report["complete"] and set(report["expected_scenarios"]) == set(registered_names)
    requirement_names = {name for name, _, _ in REQUIREMENT_SCENARIOS}
    if requirement_names.issubset(report["expected_scenarios"]):
        report["requirements_coverage"] = finalize_requirement_report(manifest, report)
        report["passed"] = report["passed"] and report["requirements_coverage"]["passed"]
    else:
        report["requirements_coverage"] = {"status": "not_executed_in_selected_scope", "complete": False,
                                           "passed": False, "business_acceptance": False, "full_flow_tested": False}
    report["business_acceptance"] = finalize_business_report(manifest, report)
    report["automatic_gate"] = "passed" if report["passed"] else "failed"
    save_json(report_path, report)
    print(json.dumps({"report": str(report_path), "registered": report["registered"], "executed": report["executed"], "passed": report["passed_count"], "failed": report["failed"]}, ensure_ascii=False))
    return 0 if report["automatic_gate"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--browser")
    parser.add_argument("--scenario", action="append", default=[])
    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == 1, "隔离 manifest 版本不匹配")
    require(manifest.get("synthetic_data_only") is True, "只允许明确标记的全新合成实例")
    origin = urlsplit(manifest["origin"])
    require(origin.scheme in {"http", "https"} and origin.hostname in {"127.0.0.1", "localhost"}
            and not origin.username and not origin.password and origin.path in {"", "/"},
            "点击脚本只允许本机隔离 origin")
    runtime_root = Path(manifest["runtime_root"]).resolve()
    require(Path(manifest["database_path"]).resolve().is_relative_to(runtime_root), "合成数据库必须在隔离 runtime 中")
    require(Path(manifest["credentials_path"]).resolve().is_relative_to(runtime_root), "合成密码必须在隔离 runtime 中")
    credentials_path = Path(manifest["credentials_path"]).resolve()
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    executable = args.browser or manifest["browser"]["executable"]
    return asyncio.run(run(manifest, credentials, executable, args.scenario))


if __name__ == "__main__":
    sys.exit(main())
