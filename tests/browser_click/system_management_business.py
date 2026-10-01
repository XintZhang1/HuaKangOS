"""Original-UI system management candidate; synthetic accounts only.

HK189/HK191 submit their two batch checks. Password/parameter and audit-detail
subranges remain HK192/HK193 partial; dossier grants and branding are not run.
No app import, positive HTTP shortcut, SQL write, or unknown-result replay.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import login_as, require
from vehicle_purchase_business import checkbox, nav, select_value

SCENARIO = "system-management-hk189-191"
REQUIREMENTS = (
    ("HK-189", "机构管理", ("原界面新增、编辑本批第三机构", "仅新店停启用及当前店停用后真实回到可用店", "原两店与其全部业务保持")),
    ("HK-191", "员工管理", ("两名新员工默认销售且不默认勾店，明确逐店岗位", "两名本人首次改密及原身份重新登录", "仅新员工编辑、停启用、他人重置与所有旧会话失效")),
)
PRIMARY = {"stores": ("id",), "users": ("id",), "user_stores": ("user_id", "store_id"),
           "audit_logs": ("id",), "user_access_receipts": ("id",)}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        contents = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        catalog = {row["id"]: row for row in json.loads(contents)["requirements"]}
        rows = []
        for key, title, criteria in REQUIREMENTS:
            source = catalog.get(key)
            require(source is not None and source["title"] == title and source["source_review_status"] == "source_reviewed",
                    key + " 原合同未核准")
            require(any(check["check_id"] == key + "-business" for check in source["acceptance_checks"]), key + " check_id不匹配")
            rows.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                         "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                         "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                                                "status": "not_tested", "criteria": list(criteria), "evidence": {}}]})
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [row[0] for row in REQUIREMENTS],
                       "source_contract_sha256": hashlib.sha256(contents).hexdigest(), "requirements": rows,
                       "execution": "native_browser_original_forms", "complete": False, "passed": False,
                       "full_193_business_acceptance": False, "full_registered_suite_complete": False,
                       "human_acceptance": "pending", "partial_requirements": [
                           {"id": "HK-192", "title": "参数设置密码修改", "status": "not_tested", "business_accepted": False,
                            "acceptance_check_submitted": False, "evidence": {},
                            "unexecuted_scope": ["机构登录图片上传及恢复", "各独立原业务参数发布与复核"]},
                           {"id": "HK-193", "title": "系统日志", "status": "not_tested", "business_accepted": False,
                            "acceptance_check_submitted": False, "evidence": {},
                            "unexecuted_scope": ["原UI未提供的类型及原ID筛选", "各岗位非空本店审计范围及分页"]}],
                       "conditional_not_tested": {"HK-189": ["最后可用店拒绝：原两店不在本批停用范围"],
                                                  "HK-190": ["跨店原单逐件授权、独立批准、接收、撤销、到期、换岗失效"]},
                       "conditions": {"synthetic_data_only": True, "existing_passwords_changed": False,
                                      "production_acceptance": False, "manual_review": "pending"}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(row for row in self.report["requirements"] if row["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    async def passed(self, evidence):
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        self.active = None
        self.save()

    def partial(self, key, evidence):
        row = next(row for row in self.report["partial_requirements"] if row["id"] == key)
        row.update(status="partial", local_scope_status="local_scope_passed", evidence=evidence)
        self.save()

    def failed(self, error):
        if self.active:
            self.active.update(status="failed", evidence_action_end=len(self.e.actions))
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        for row in self.report["requirements"]:
            if row["status"] == "running" and row is not self.active:
                row["status"] = "partial"
                row["acceptance_checks"][0]["status"] = "partial"
        if self.active is None:
            self.report["failed_subrange"] = self.report.get("current_subrange", "system_source_precondition")
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self):
        require(all(row["status"] == "passed" for row in self.report["requirements"]), "系统本批两项未完整执行")
        require(all(row.get("local_scope_status") == "local_scope_passed" for row in self.report["partial_requirements"]),
                "参数及日志明确子范围未执行完")
        self.report.update(complete=True, passed=True, passed_requirements=2, executed_requirements=2)
        self.save()
        self.e.observe("system_management_checkpoint", {"path": str(self.path), "passed_checks": 2,
                       "hk192": "partial", "hk193": "partial", "manual_review": "pending", "business_accepted": False})


def one(e, table, key):
    rows = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (key,))
    require(len(rows) == 1, "原记录不是唯一：" + table)
    return rows[0]


def identity(row, table):
    return tuple(row[column] for column in PRIMARY[table])


def before_write(e, *, updates=None, appends=(), session_user=None):
    updates = updates or {}
    allowed = set(updates) | set(appends)
    before = e.business_snapshot("before_original_system_form")
    old = {table: e.db.rows(f"SELECT * FROM {table} ORDER BY {','.join(PRIMARY[table])}") for table in allowed}
    login_rows = e.db.rows("SELECT * FROM login_sessions ORDER BY id")
    return before, old, {table: set(keys) for table, keys in updates.items()}, allowed, set(appends), login_rows, session_user


def after_write(e, protection):
    before, old, updates, allowed, appends, login_rows, session_user = protection
    after = e.business_snapshot("after_original_system_form")
    changed = [table for table in before["tables"].keys() | after["tables"].keys()
               if table not in allowed and before["tables"].get(table) != after["tables"].get(table)]
    require(not changed, "系统办理改动无关原业务：" + "、".join(sorted(changed)))
    for table, rows in old.items():
        current = {identity(row, table): row for row in e.db.rows(f"SELECT * FROM {table} ORDER BY {','.join(PRIMARY[table])}")}
        if table not in appends:
            require(set(current) == {identity(row, table) for row in rows}, "系统编辑意外新增或删除行：" + table)
        for row in rows:
            key = identity(row, table)
            require(key in current, "系统办理删除原行：" + table)
            if key not in updates.get(table, set()):
                require(current[key] == row, "系统办理覆盖无关原行：" + table)
    current_login_rows = e.db.rows("SELECT * FROM login_sessions ORDER BY id")
    require([row for row in login_rows if row["user_id"] != session_user]
            == [row for row in current_login_rows if row["user_id"] != session_user], "系统办理影响了其他员工原登录会话")
    return {"old_rows_unchanged_except_explicit_target": True, "all_other_business_tables_unchanged": True,
            "stock_moves_and_cash_entries_unchanged": True}


def sessions(e, user_id):
    return e.db.rows("SELECT count(*) AS n FROM login_sessions WHERE user_id=?", (user_id,))[0]["n"]


def audit_one(e, protection, actor_id, action, entity, key, *, reason=None):
    old_ids = {row["id"] for row in protection[1]["audit_logs"]}
    new = [row for row in e.db.rows("SELECT * FROM audit_logs ORDER BY id") if row["id"] not in old_ids]
    require(len(new) == 1, "一次原系统动作未精确追加一条审计")
    row = new[0]
    require(row["actor_id"] == actor_id and row["action"] == action and row["entity_type"] == entity
            and row["entity_id"] == key and row["store_id"] == 0, "系统原审计身份、对象或全局归属不匹配")
    if reason is not None:
        require(row["reason"] == reason, "原审计原因不匹配")
    instant = datetime.fromisoformat(row["occurred_at"]).replace(tzinfo=timezone.utc)
    require(0 <= (datetime.now(timezone.utc) - instant).total_seconds() < 120, "原审计时间不在本次实际办理窗口")
    for column in ("before_data", "after_data"):
        data = json.loads(row[column]) if row[column] is not None else None
        require(not any(word in json.dumps(data).lower() for word in ("password_hash", "csrf_hash", "dealer_session")),
                "审计泄露凭据字段")
    return row


def metadata(e, response, body, *, store_id, version=None):
    # The request JSON is inspected in memory only. Never persist password bodies.
    headers = response.request.headers
    require(headers.get("x-app-request") == "1" and headers.get("x-store-id") == str(store_id), "原表单身份门店头不匹配")
    request = response.request.post_data_json
    result = {"method": response.request.method, "path": urlsplit(response.url).path, "status": response.status,
              "original_ui": True, "response_id": body.get("id"), "submitted_version": version}
    if request.get("request_id"):
        result["request_id_sha256"] = hashlib.sha256(request["request_id"].encode()).hexdigest()
    e.observe("original_system_form", result)
    return request, result


async def original_submit(e, path, status, *, method="POST", store_id, version=None):
    async with e.page.expect_response(lambda r: r.request.method == method and urlsplit(r.url).path == path) as pending:
        await e.click('#modal form button[type="submit"]', "提交当前员工核对的原系统表单")
    response = await pending.value
    body = await response.json()
    require(response.status == status, f"原系统表单 HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token")), "原系统写未使用同源Cookie/CSRF")
    request, info = metadata(e, response, body, store_id=store_id, version=version)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    return body, request, info


async def open_page(e, route, title, api_path):
    if urlsplit(e.page.url).fragment == route:
        before = e.business_snapshot("before_native_system_reload")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == api_path) as pending:
            e.action("navigate", "原页面重新载入", route=route)
            await e.page.reload(wait_until="domcontentloaded")
        response = await pending.value
        require(response.status == 200, "原系统页面重新读取失败")
        body = await response.json()
        await expect(e.page.locator("#main h1")).to_have_text(title)
        e.business_unchanged(before, "after_native_system_reload")
        return body
    return await nav(e, route, title, api_path)


async def field(e, name, value, *, private=False):
    control = e.page.locator('#modal [name="' + name + '"]')
    await expect(control).to_have_count(1)
    ancestors = control.locator("xpath=ancestor::details")
    for index in range(await ancestors.count()):
        details = ancestors.nth(index)
        if await details.get_attribute("open") is None:
            e.action("click", "展开原表单字段组", field=name)
            await details.locator(":scope > summary").click()
    await expect(control).to_be_visible()
    await e.fill('#modal [name="' + name + '"]', str(value), "填写原系统字段：" + name, private=private)


async def switch_store(e, store_id, account, role):
    require(await e.page.locator("#store").input_value() != str(store_id), "切店动作必须改变当前店")
    before = e.business_snapshot("before_original_system_store_switch")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/auth/me") as pending:
        await select_value(e, "#store", store_id, "明确选择获授门店并重新读取岗位")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == account["id"] and body["active_store_id"] == store_id
            and body["account_role"] == account["role"] and body["role"] == role, "原切店未取得真实本人本店岗位")
    await expect(e.page.locator("#store")).to_have_value(str(store_id))
    # Original switchStore resets the destination and waits for its fresh store context.
    await expect(e.page).to_have_url(e.origin + "/#business-assistant")
    await expect(e.page.locator("#main h1")).to_have_text("业务助手")
    e.business_unchanged(before, "after_original_system_store_switch")
    return {"user_id": body["id"], "account_role": body["account_role"], "current_role": body["role"],
            "active_store_id": body["active_store_id"], "store_ids": body["store_ids"], "native_me_status": 200}


def private_accounts(e, token):
    require(e.manifest.get("synthetic_data_only") is True, "系统候选只允许全新外部合成实例")
    require(isinstance(e.secrets, list), "Evidence.secrets必须是整份证据共用可扩展词表")
    runtime = Path(e.manifest["runtime_root"]).resolve()
    require(runtime.is_relative_to(Path(e.manifest["credentials_path"]).resolve().parent), "系统私有凭据目录不在本次外部实例")
    provenance = json.loads((Path(e.manifest["evidence_root"]) / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "系统私有凭据需要本次稳定镜像")
    source = Path(provenance["source_root"]).resolve()
    mirror = Path(e.manifest["source_root"]).resolve()
    require(not runtime.is_relative_to(source) and not runtime.is_relative_to(mirror), "随机密码不得保存仓库或生产镜像")
    require(runtime.parent == mirror.parent, "私有凭据与生产镜像不是本次同一外部实例")
    path = runtime / ("system-management-accounts-" + token + ".json")
    data = {"schema": 1, "synthetic_data_only": True, "accounts": {}}
    for key in ("receiver", "manager"):
        data["accounts"][key] = {"username": "sys_" + key[0] + "_" + token,
                                "initial": secrets.token_urlsafe(24), "first": secrets.token_urlsafe(24),
                                "reset": secrets.token_urlsafe(24), "after_reset": secrets.token_urlsafe(24),
                                "final": secrets.token_urlsafe(24), "wrong_old": secrets.token_urlsafe(24),
                                "short_new": secrets.token_hex(4)}
        e.secrets.extend(value for name, value in data["accounts"][key].items() if name != "username")
    # Exclusive creation: never replace an existing recovery record.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
    os.chmod(path, 0o600)
    e.observe("synthetic_system_private_credentials", {"path": str(path), "account_count": 2,
              "all_passwords_in_shared_scrubber": True, "credentials_in_evidence": False})
    return path, data


def save_private(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


async def create_staff(e, admin, store_id, secret, display_name, roles):
    await open_page(e, "users", "员工账号", "/api/users")
    await e.click('[data-act="newuser"]', "新增独立随机合成员工")
    await expect(e.page.locator('#modal [name="role"]')).to_have_value("sales")
    await expect(e.page.locator('#modal [name="can_group_summary"]')).not_to_be_checked()
    boxes = e.page.locator('#modal [name="store_ids"]')
    require(await boxes.count() >= 3, "新店未出现在原员工门店候选")
    require(not any([await boxes.nth(index).is_checked() for index in range(await boxes.count())]), "新增员工自动获授门店")
    await field(e, "username", secret["username"])
    await field(e, "password", secret["initial"], private=True)
    await field(e, "display_name", display_name)
    for target, role in roles.items():
        await checkbox(e, f'#modal [name="store_ids"][value="{target}"]', True, "明确勾选新员工获授门店")
        await select_value(e, f'#modal [name="store_role_{target}"]', role, "明确选择该店实际岗位")
    protection = before_write(e, appends=("users", "user_stores", "audit_logs"))
    body, request, info = await original_submit(e, "/api/users", 201, store_id=store_id)
    require(request["role"] == "sales" and request["can_group_summary"] is False
            and set(request["store_ids"]) == set(roles) and {row["store_id"]: row["role"] for row in request["store_roles"]} == roles,
            "原新员工提交与明确门店岗位不匹配")
    target = one(e, "users", body["id"])
    old_users = {row["id"] for row in protection[1]["users"]}
    require({row["id"] for row in e.db.rows("SELECT id FROM users ORDER BY id")} - old_users == {target["id"]},
            "一次新增员工产生了其他账号")
    old_memberships = {identity(row, "user_stores") for row in protection[1]["user_stores"]}
    require({identity(row, "user_stores") for row in e.db.rows("SELECT * FROM user_stores ORDER BY user_id,store_id")}
            - old_memberships == {(target["id"], store) for store in roles}, "新增员工产生其他门店关系")
    require(target["username"] == secret["username"] and target["display_name"] == display_name
            and target["role"] == "sales" and target["active"] == 1 and target["must_change_password"] == 1
            and target["can_group_summary"] == 0 and target["access_version"] == 1, "新员工原事实不匹配")
    require({row["store_id"]: row["role"] for row in e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (target["id"],))} == roles,
            "新员工逐店岗位关系不匹配")
    audit = audit_one(e, protection, admin["id"], "create_user", "users", target["id"])
    safety = after_write(e, protection)
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{target["id"]}"])')).to_contain_text(display_name)
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{target["id"]}"]) td').nth(1)).to_have_text(target["username"])
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{target["id"]}"]) td').nth(2)).to_have_text("销售")
    require("password" not in body and "password_hash" not in body, "新员工响应泄露密码")
    return target, {**info, **safety, "user_id": target["id"], "audit_id": audit["id"],
                    "default_sales": True, "default_store_selection_empty": True, "store_roles": roles}


async def fresh_identity(e, context, contexts):
    separate = await context.browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 900})
    contexts.append(separate)
    page = await separate.new_page()
    await e.attach(separate, page)
    return separate, page


async def native_login(e, account, password, *, first=False):
    e.action("navigate", "新合成员工原生登录", user_id=account["id"])
    await e.page.goto(e.origin + "/#parameters", wait_until="domcontentloaded")
    await expect(e.page.locator('input[name="username"]')).to_be_visible()
    await e.fill('input[name="username"]', account["username"], "本批新员工账号")
    await e.fill('input[name="password"]', password, "本批新员工密码", private=True)
    protection = before_write(e, appends=("audit_logs",), session_user=account["id"])
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/auth/login") as pending:
        await e.click('form button[type="submit"]', "本人原生登录一次")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == account["id"] and body["account_role"] == account["role"]
            and body["must_change_password"] is first, "新员工实际登录或首次改密状态不符")
    audit = audit_one(e, protection, account["id"], "login", "users", account["id"])
    after_write(e, protection)
    await expect(e.page.locator("#store")).to_be_visible()
    cookies = {cookie["name"]: cookie for cookie in await e.page.context.cookies(e.origin)}
    require(cookies.get("dealer_session", {}).get("httpOnly") is True
            and cookies.get("dealer_session", {}).get("sameSite") == "Strict"
            and cookies.get("dealer_csrf", {}).get("httpOnly") is False, "新员工原登录Cookie合同不匹配")
    if first:
        await expect(e.page.locator("#main h1")).to_have_text("设置个人密码")
        await expect(e.page.locator('#modal [name="current_password"]')).to_be_visible()
    else:
        await expect(e.page.locator("#main h1")).to_have_text("参数与个人密码")
    return {"user_id": body["id"], "account_role": body["account_role"], "current_role": body["role"],
            "active_store_id": body["active_store_id"], "store_ids": body["store_ids"],
            "must_change_password": body["must_change_password"], "audit_id": audit["id"], "status": 200}


async def personal_password(e, account, current, new, store_id, *, opened=False):
    if not opened:
        await e.click('.passwordbutton[data-act="password"]', "本人打开原改密表单")
    await field(e, "current_password", current, private=True)
    await field(e, "new_password", new, private=True)
    require(sessions(e, account["id"]) > 0, "本人改密没有实际旧会话")
    count = sessions(e, account["id"])
    before_user = one(e, "users", account["id"])
    protection = before_write(e, updates={"users": {(account["id"],)}}, appends=("audit_logs",), session_user=account["id"])
    body, _, info = await original_submit(e, "/api/auth/password", 200, store_id=store_id)
    require(body.get("ok") is True and body.get("message") == "密码已修改，请重新登录", "本人原改密结果不符")
    after_user = one(e, "users", account["id"])
    require(after_user["password_hash"] != before_user["password_hash"] and after_user["must_change_password"] == 0,
            "本人密码未变化或首次改密标志未清除")
    require({k: v for k, v in before_user.items() if k not in {"password_hash", "must_change_password"}}
            == {k: v for k, v in after_user.items() if k not in {"password_hash", "must_change_password"}}, "改密改动其他账号资料")
    require(sessions(e, account["id"]) == 0, "本人改密未撤销全部旧会话")
    audit = audit_one(e, protection, account["id"], "change_password", "users", account["id"], reason="修改密码并撤销全部登录会话")
    safety = after_write(e, protection)
    cookies = await e.page.context.cookies(e.origin)
    require(not any(cookie["name"] in {"dealer_session", "dealer_csrf"} for cookie in cookies), "成功改密未清除原登录Cookie")
    await expect(e.page.locator('input[name="username"]')).to_be_visible()
    return {**info, **safety, "audit_id": audit["id"], "old_session_count": count, "remaining_sessions": 0,
            "password_hash_changed": True, "cookies_cleared": True}


async def revoked_page(e, page, user_id):
    e.page = page
    require(sessions(e, user_id) == 0, "失效页面前本人会话仍有效")
    before = e.business_snapshot("before_revoked_native_page_reload")
    async with page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/auth/me") as pending:
        e.action("navigate", "旧页面实际重新载入并即时重验本人会话", user_id=user_id)
        await page.reload(wait_until="domcontentloaded")
    response = await pending.value
    require(response.status == 401, "旧登录会话未被原读取即时拒绝")
    await expect(page.locator('input[name="username"]')).to_be_visible()
    e.business_unchanged(before, "after_revoked_native_page_reload")
    return {"user_id": user_id, "native_me_status": 401, "login_page_visible": True, "business_unchanged": True}


async def edit_staff(e, admin, target, store_id, roles, *, active=True, display_name=None):
    await open_page(e, "users", "员工账号", "/api/users")
    await e.click(f'[data-act="edituser"][data-id="{target["id"]}"]', "编辑本批新员工原账号")
    await field(e, "display_name", display_name or target["display_name"])
    await checkbox(e, '#modal [name="active"]', active, "明确新员工启用状态")
    for store, role in roles.items():
        await checkbox(e, f'#modal [name="store_ids"][value="{store}"]', True, "核对新员工原授权门店")
        await select_value(e, f'#modal [name="store_role_{store}"]', role, "核对新员工原逐店岗位")
    require(sessions(e, target["id"]) > 0 or target["active"] == 0, "编辑有效员工未形成待撤销会话")
    memberships = e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (target["id"],))
    protection = before_write(e, updates={"users": {(target["id"],)}, "user_stores": {identity(row, "user_stores") for row in memberships}},
                             appends=("user_access_receipts", "audit_logs"), session_user=target["id"])
    old_receipts = {row["id"] for row in protection[1]["user_access_receipts"]}
    body, request, info = await original_submit(e, "/api/users/" + str(target["id"]), 200, method="PUT",
                                               store_id=store_id, version=target["access_version"])
    require(request["access_version"] == target["access_version"] and bool(request["request_id"])
            and request["active"] is active and request["role"] == "sales"
            and {row["store_id"]: row["role"] for row in request["store_roles"]} == roles, "原编辑CAS或岗位提交不匹配")
    current = one(e, "users", target["id"])
    require(current["access_version"] == target["access_version"] + 1 and bool(current["active"]) is active
            and current["display_name"] == (display_name or target["display_name"])
            and current["password_hash"] == target["password_hash"] and current["must_change_password"] == target["must_change_password"],
            "原员工编辑事实、版本或密码保护不匹配")
    require({row["store_id"]: row["role"] for row in e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (target["id"],))} == roles,
            "原员工编辑实际门店关系不符")
    require(sessions(e, target["id"]) == 0, "原员工编辑未撤销全部会话")
    audit = audit_one(e, protection, admin["id"], "update_user", "users", target["id"], reason="核对账号授权版本后修改；原登录会话全部失效")
    receipts = [row for row in e.db.rows("SELECT * FROM user_access_receipts ORDER BY id") if row["id"] not in old_receipts]
    require(len(receipts) == 1, "原员工编辑未精确追加一条收据")
    receipt = receipts[0]
    require(receipt["actor_id"] == admin["id"] and receipt["target_id"] == target["id"] and receipt["request_key"] == request["request_id"]
            and receipt["previous_version"] == target["access_version"] and receipt["audit_id"] == audit["id"]
            and json.loads(receipt["result"]) == body, "原编辑收据身份/版本/结果不匹配")
    require(json.loads(receipt["request_data"]) == {key: value for key, value in request.items() if key != "request_id"},
            "原编辑收据不绑定本次明确表单")
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{target["id"]}"])')).to_contain_text(current["display_name"])
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{target["id"]}"]) td').nth(5)).to_have_text("启用" if active else "停用")
    return current, {**info, **after_write(e, protection), "audit_id": audit["id"], "receipt_id": receipt["id"],
                     "access_version": current["access_version"], "active": active, "all_old_sessions_revoked": True}


async def reset_staff(e, admin, target, store_id, password, reason):
    await open_page(e, "users", "员工账号", "/api/users")
    await e.click(f'[data-act="resetpassword"][data-id="{target["id"]}"]', "管理员只重置本批新员工密码")
    await field(e, "password", password, private=True)
    await field(e, "reason", reason)
    count = sessions(e, target["id"])
    require(count >= 2, "重置前未形成两个真实本人会话")
    protection = before_write(e, updates={"users": {(target["id"],)}}, appends=("audit_logs",), session_user=target["id"])
    body, request, info = await original_submit(e, "/api/users/" + str(target["id"]) + "/password", 200, store_id=store_id)
    current = one(e, "users", target["id"])
    require(body.get("ok") is True and request["reason"] == reason and current["password_hash"] != target["password_hash"]
            and current["must_change_password"] == 1 and sessions(e, target["id"]) == 0, "原管理员重置结果或旧会话撤销不符")
    require({k: v for k, v in target.items() if k not in {"password_hash", "must_change_password"}}
            == {k: v for k, v in current.items() if k not in {"password_hash", "must_change_password"}}, "重置密码改变其他授权")
    audit = audit_one(e, protection, admin["id"], "reset_password", "users", target["id"], reason=reason)
    return current, {**info, **after_write(e, protection), "audit_id": audit["id"], "old_session_count": count,
                     "remaining_sessions": 0, "must_change_password": True, "password_hash_changed": True}


async def password_edges(e, current, wrong, new, short, store_id):
    await e.click('.passwordbutton[data-act="password"]', "本人核对原密码拒绝与长度边界")
    results = []
    for old, replacement, status, detail in ((wrong, new, 400, "当前密码不正确"), (current, current, 422, "新密码不能与旧密码相同")):
        await field(e, "current_password", old, private=True)
        await field(e, "new_password", replacement, private=True)
        before = e.business_snapshot("before_original_password_refusal")
        before_sessions = e.db.rows("SELECT * FROM login_sessions ORDER BY id")
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/auth/password") as pending:
            await e.click('#modal form button[type="submit"]', "本人只提交一次原密码校验")
        response = await pending.value
        body = await response.json()
        require(response.status == status and body.get("detail") == detail, "原密码拒绝状态或文案不匹配")
        await expect(e.page.locator("#modal .formerror")).to_contain_text(detail)
        e.business_unchanged(before, "after_original_password_refusal")
        require(e.db.rows("SELECT * FROM login_sessions ORDER BY id") == before_sessions, "密码拒绝改变原会话")
        _, info = metadata(e, response, body, store_id=store_id)
        results.append({**info, "detail": detail, "business_unchanged": True})
    await field(e, "current_password", current, private=True)
    require(short in e.secrets and len(short) < 12, "临时长度边界密码必须已在外部私有文件及整份脱敏词表")
    await field(e, "new_password", short, private=True)
    requests = []
    listener = lambda request: requests.append(request) if request.method == "POST" and urlsplit(request.url).path == "/api/auth/password" else None
    e.page.on("request", listener)
    before = e.business_snapshot("before_native_password_length_refusal")
    before_sessions = e.db.rows("SELECT * FROM login_sessions ORDER BY id")
    try:
        await e.click('#modal form button[type="submit"]', "不足12位由原输入控件拒绝")
        await expect(e.page.locator('#modal [name="new_password"]:invalid')).to_have_count(1)
        require(not requests, "不足12位密码仍发出原提交")
        e.business_unchanged(before, "after_native_password_length_refusal")
        require(e.db.rows("SELECT * FROM login_sessions ORDER BY id") == before_sessions, "原密码长度拒绝改变会话")
    finally:
        e.page.remove_listener("request", listener)
    results.append({"native_minlength": 12, "actual_post_count": 0, "business_unchanged": True})
    await field(e, "new_password", new, private=True)
    return results


async def store_form(e, admin, store_id, values, *, target=None):
    await open_page(e, "stores", "门店设置", "/api/stores")
    await e.click('[data-act="newstore"]' if target is None else f'[data-act="editstore"][data-id="{target["id"]}"]',
                  "新增本批第三店" if target is None else "编辑本批第三店")
    await field(e, "name", values["name"])
    await field(e, "code", values["code"])
    await checkbox(e, '#modal [name="active"]', values["active"], "明确新店实际启用状态")
    protection = before_write(e, updates={"stores": {(target["id"],)}} if target else {},
                             appends=("audit_logs",) if target else ("stores", "audit_logs"))
    body, request, info = await original_submit(e, "/api/stores" + ("/" + str(target["id"]) if target else ""),
                                               200 if target else 201, method="PUT" if target else "POST", store_id=store_id)
    require(request == values, "原店表单提交不匹配")
    current = one(e, "stores", body["id"])
    if target is None:
        old_ids = {row["id"] for row in protection[1]["stores"]}
        require({row["id"] for row in e.db.rows("SELECT id FROM stores ORDER BY id")} - old_ids == {current["id"]},
                "一次新增门店产生了其他机构")
    require(current["name"] == values["name"] and current["code"] == values["code"] and bool(current["active"]) is values["active"],
            "原门店行与明确表单不匹配")
    audit = audit_one(e, protection, admin["id"], "update_store" if target else "create_store", "stores", current["id"])
    safety = after_write(e, protection)
    await expect(e.page.locator("#main h1")).to_have_text("门店设置")
    await expect(e.page.locator(f'#main tr:has([data-act="editstore"][data-id="{current["id"]}"])')).to_contain_text(current["name"])
    await expect(e.page.locator(f'#main tr:has([data-act="editstore"][data-id="{current["id"]}"]) td').nth(1)).to_have_text(current["code"])
    await expect(e.page.locator(f'#main tr:has([data-act="editstore"][data-id="{current["id"]}"]) td').nth(2)).to_have_text("启用" if values["active"] else "停用")
    return current, {**info, **safety, "store_id": current["id"], "active": values["active"], "audit_id": audit["id"]}


async def parameter_partial(e, account, *, role):
    data = await open_page(e, "parameters", "参数与个人密码", "/api/parameters/catalog")
    require(data["password_action"] == "password" and data["deployment_read_only"] is True and data["aggregate_scope"] is False,
            "原安全配置目录合同不符")
    if role in {"admin", "manager"}:
        require(data["deployment"]["timezone"] == "Asia/Shanghai", "合成业务时区不是已知夹具时区")
    else:
        require(data["deployment"] is None, "普通岗位读取部署参数")
    require(not any(word in json.dumps(data).lower() for word in ("api_key", "database_url", "password_hash", "credentials_path")),
            "安全配置目录包含凭据或私有配置")
    await expect(e.page.locator('#main [data-act="password"]')).to_be_visible()
    await expect(e.page.locator('.sidebar a[href="#users"]')).to_have_count(1 if account["role"] == "admin" else 0)
    return {"user_id": account["id"], "role": role, "safe_catalog_nonempty": bool(data["entries"]),
            "deployment_read_only": True, "deployment_visible": data["deployment"] is not None,
            "timezone": data["deployment"].get("timezone") if data["deployment"] else None,
            "original_password_action_visible": True, "branding_executed": False}


async def audit_partial(e, admin, audit_id):
    data = await open_page(e, "audit", "操作记录", "/api/audit")
    require(data["total"] > 0 and bool(data["items"]), "日志只打开了空表")
    source = one(e, "audit_logs", audit_id)
    visible = next((row for row in data["items"] if row["id"] == audit_id), None)
    require(visible is not None, "本批明确原店编辑日志不在实际第一页")
    for key in ("id", "actor_id", "action", "entity_type", "entity_id", "reason", "store_id"):
        require(visible[key] == source[key], "原日志UI响应与数据库不匹配：" + key)
    for key in ("before_data", "after_data"):
        require(visible[key] == json.loads(source[key]), "原审计前后资料不匹配")
    require(visible["actor_name"] == admin["display_name"], "原日志员工名称不符")
    instant = datetime.fromisoformat(source["occurred_at"]).replace(tzinfo=timezone.utc)
    require(datetime.fromisoformat(visible["occurred_at"].replace("Z", "+00:00")) == instant, "审计API时间与原UTC事实不符")
    local = instant.astimezone(ZoneInfo("Asia/Shanghai"))
    displayed_time = f"{local.year}/{local.month}/{local.day} {local.hour:02d}:{local.minute:02d}:{local.second:02d}"
    await expect(e.page.locator(f'#main tr:has([data-act="auditdetail"][data-id="{audit_id}"]) td').nth(0)).to_have_text(displayed_time)
    before = e.business_snapshot("before_original_audit_detail")
    await e.click(f'[data-act="auditdetail"][data-id="{audit_id}"]', "查看本次真实原店变更详情")
    await expect(e.page.locator("#modal")).to_contain_text("操作详情")
    await expect(e.page.locator("#modal")).to_contain_text("操作前")
    await expect(e.page.locator("#modal")).to_contain_text("操作后")
    await expect(e.page.locator("#modal")).to_contain_text(admin["display_name"])
    await expect(e.page.locator("#modal .stack > p")).to_contain_text(displayed_time)
    await expect(e.page.locator("#modal")).to_contain_text(visible["before_data"]["name"])
    await expect(e.page.locator("#modal")).to_contain_text(visible["after_data"]["name"])
    await e.snapshot("hk193-nonempty-original-audit-detail-partial")
    await e.click('#modal .modalhead [data-act="close"]', "关闭原审计只读详情")
    e.business_unchanged(before, "after_original_audit_detail")
    return {"audit_id": audit_id, "actor_id": visible["actor_id"], "entity_id": visible["entity_id"],
            "global_store_id": 0, "nonempty_total": data["total"], "original_before_after_matched": True,
            "utc_api_and_shanghai_visible_time_matched": True,
            "detail_clicked": True, "type_id_filter_executed": False, "all_role_scopes_executed": False}


async def system_management_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    contexts, main_page = [], e.page
    token = uuid.uuid4().hex[:10]
    private_path, private = private_accounts(e, token)
    receiver_secret, manager_secret = private["accounts"]["receiver"], private["accounts"]["manager"]
    original_stores = e.db.rows("SELECT * FROM stores ORDER BY id")
    original_users = e.db.rows("SELECT * FROM users ORDER BY id")
    original_memberships = e.db.rows("SELECT * FROM user_stores ORDER BY user_id,store_id")
    first_store = e.manifest["stores"][0]["id"]
    second_store = e.manifest["stores"][1]["id"]
    store_evidence, employee_evidence, passwords = [], [], []
    try:
        checkpoint.start("HK-189")
        admin = await login_as(e, context, credentials, "admin", "stores", first_store)
        third, created_store = await store_form(e, admin, first_store, {"name": "合成机构-" + token, "code": "SYS_" + token, "active": True})
        store_evidence.append(created_store)
        third, edited_store = await store_form(e, admin, first_store, {"name": "合成机构-" + token + "已核", "code": third["code"], "active": True}, target=third)
        store_evidence.append(edited_store)
        checkpoint.start("HK-191")
        receiver_roles = {second_store: "service", third["id"]: "auditor"}
        manager_roles = {first_store: "manager"}
        receiver, receiver_created = await create_staff(e, admin, first_store, receiver_secret, "合成员工甲-" + token, receiver_roles)
        manager, manager_created = await create_staff(e, admin, first_store, manager_secret, "合成员工乙-" + token, manager_roles)
        employee_evidence.extend((receiver_created, manager_created))
        receiver_secret["id"], manager_secret["id"] = receiver["id"], manager["id"]
        save_private(private_path, private)
        _, receiver_page = await fresh_identity(e, context, contexts)
        receiver_login = await native_login(e, receiver, receiver_secret["initial"], first=True)
        require(set(receiver_login["store_ids"]) == set(receiver_roles) and receiver_login["current_role"] == "service", "首登录没有原逐店service岗位")
        passwords.append(await personal_password(e, receiver, receiver_secret["initial"], receiver_secret["first"], second_store, opened=True))
        receiver = one(e, "users", receiver["id"])
        receiver_login = await native_login(e, receiver, receiver_secret["first"])
        receiver_parameters = await parameter_partial(e, receiver, role="service")
        receiver_switch = await switch_store(e, third["id"], receiver, "auditor")
        auditor_parameters = await parameter_partial(e, receiver, role="auditor")
        await switch_store(e, second_store, receiver, "service")
        _, manager_page = await fresh_identity(e, context, contexts)
        manager_login = await native_login(e, manager, manager_secret["initial"], first=True)
        require(manager_login["store_ids"] == [first_store] and manager_login["current_role"] == "manager", "新主管非明确本店独立身份")
        passwords.append(await personal_password(e, manager, manager_secret["initial"], manager_secret["first"], first_store, opened=True))
        manager = one(e, "users", manager["id"])
        await native_login(e, manager, manager_secret["first"])
        manager_parameters = await parameter_partial(e, manager, role="manager")
        e.page = main_page
        receiver, renamed = await edit_staff(e, admin, receiver, first_store, receiver_roles, display_name=receiver["display_name"] + "已核")
        employee_evidence.append(renamed)
        employee_evidence.append(await revoked_page(e, receiver_page, receiver["id"]))
        await native_login(e, receiver, receiver_secret["first"])
        e.page = main_page
        receiver, disabled = await edit_staff(e, admin, receiver, first_store, receiver_roles, active=False)
        employee_evidence.append(disabled)
        employee_evidence.append(await revoked_page(e, receiver_page, receiver["id"]))
        e.page = main_page
        receiver, enabled = await edit_staff(e, admin, receiver, first_store, receiver_roles, active=True)
        employee_evidence.append(enabled)
        e.page = receiver_page
        await native_login(e, receiver, receiver_secret["first"])
        _, sibling_page = await fresh_identity(e, context, contexts)
        await native_login(e, receiver, receiver_secret["first"])
        e.page = main_page
        receiver, reset = await reset_staff(e, admin, receiver, first_store, receiver_secret["reset"], "仅本批合成员工忘记初始凭据，管理员明确重置。")
        employee_evidence.append(reset)
        employee_evidence.append(await revoked_page(e, receiver_page, receiver["id"]))
        employee_evidence.append(await revoked_page(e, sibling_page, receiver["id"]))
        e.page = receiver_page
        await native_login(e, receiver, receiver_secret["reset"], first=True)
        passwords.append(await personal_password(e, receiver, receiver_secret["reset"], receiver_secret["after_reset"], second_store, opened=True))
        receiver = one(e, "users", receiver["id"])
        await native_login(e, receiver, receiver_secret["after_reset"])
        e.page = sibling_page
        await native_login(e, receiver, receiver_secret["after_reset"])
        e.page = receiver_page
        require(sessions(e, receiver["id"]) >= 2, "本人改密未形成两个实际会话")
        edges = await password_edges(e, receiver_secret["after_reset"], receiver_secret["wrong_old"], receiver_secret["final"],
                                     receiver_secret["short_new"], second_store)
        passwords.append(await personal_password(e, receiver, receiver_secret["after_reset"], receiver_secret["final"], second_store, opened=True))
        employee_evidence.append(await revoked_page(e, sibling_page, receiver["id"]))
        receiver = one(e, "users", receiver["id"])
        e.page = receiver_page
        final_login = await native_login(e, receiver, receiver_secret["final"])
        final_parameters = await parameter_partial(e, receiver, role="service")
        receiver_secret["current_password_stage"] = "final"
        manager_secret["current_password_stage"] = "first"
        save_private(private_path, private)
        checkpoint.partial("HK-192", {"personal_passwords": passwords, "password_edges": edges,
                           "safe_catalogs": [receiver_parameters, auditor_parameters, manager_parameters, final_parameters],
                           "full_requirement_accepted": False})
        await checkpoint.passed({"staff_actions": employee_evidence, "personal_passwords": passwords,
                                 "actual_store_projection": receiver_switch, "final_login": final_login,
                                 "only_new_users_changed": True, "independent_dossier_approval_executed": False})
        checkpoint.start("HK-189")
        e.page = main_page
        await open_page(e, "stores", "门店设置", "/api/stores")
        await switch_store(e, third["id"], admin, "admin")
        third, disabled_store = await store_form(e, admin, third["id"], {"name": third["name"], "code": third["code"], "active": False}, target=third)
        store_evidence.append(disabled_store)
        await expect(e.page.locator("#store")).to_have_value(str(first_store))
        await expect(e.page.locator("body")).to_contain_text("当前门店已停用，已切换到")
        third, enabled_store = await store_form(e, admin, first_store, {"name": third["name"], "code": third["code"], "active": True}, target=third)
        store_evidence.append(enabled_store)
        admin_switch = await switch_store(e, third["id"], admin, "admin")
        await switch_store(e, first_store, admin, "admin")
        require(all(one(e, "stores", row["id"]) == row for row in original_stores), "新店操作改变原两店")
        require(all(one(e, "users", row["id"]) == row for row in original_users), "系统候选改变已有员工/密码")
        require([row for row in e.db.rows("SELECT * FROM user_stores ORDER BY user_id,store_id")
                 if row["user_id"] in {original["id"] for original in original_users}] == original_memberships,
                "系统候选改变原员工逐店授权")
        await checkpoint.passed({"store_actions": store_evidence, "real_reenabled_store_projection": admin_switch,
                                 "original_stores_users_and_memberships_unchanged": True,
                                 "last_usable_store_branch": "not_tested"})
        checkpoint.report["current_subrange"] = "HK-193-original-audit-detail-partial"
        checkpoint.save()
        audit_detail = await audit_partial(e, admin, edited_store["audit_id"])
        checkpoint.partial("HK-193", audit_detail)
        checkpoint.finish()
    except Exception as error:
        checkpoint.failed(error)
        raise
    finally:
        e.page = main_page
        for separate in reversed(contexts):
            await separate.close()


SYSTEM_MANAGEMENT_SCENARIOS = ((SCENARIO, system_management_business, 420),)
