"""Original administrator revokes a new employee during real Grant prepare."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid

from playwright.async_api import expect

from runtime_context_closeout import _response
from runtime_faults import _atomic_json, _digest, _load, _rows, _utc
from runtime_followup_closeout import _control_path, _observations
from sales_business import employee_choice, facts, login_as, native_submit, new_event, require, same_original, task
from system_management_business import (
    after_write, audit_one, before_write, create_staff, field, identity,
    native_login, one, open_page, original_submit, personal_password,
    private_accounts, revoked_page, sessions, store_form,
)
from vehicle_purchase_business import checkbox


ACCESS_PREFIX = "浏览器管理员撤权 "


def extend_access_provider(provider):
    """Only the unique new employee's real prepare response is held."""
    from provider import reply, tool
    original = provider.handle

    async def handle(request):
        body = json.loads(request.content)
        messages = body["messages"]
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1]) if marker in messages[0]["content"] else {}
        texts = [message["content"] for message in messages if message["role"] == "user"]
        texts += [message["content"] for message in context.get("recent_messages", []) if message["role"] == "user"]
        text = next((value for value in reversed(texts) if value.startswith(ACCESS_PREFIX)), None)
        if text is None:
            return await original(request)
        require((request.url.scheme, request.url.host, request.url.path) ==
                ("https", "api.deepseek.com", "/chat/completions"), "非固定管理员撤权provider地址")
        header, encoded = text.split("\n", 1)
        require(re.fullmatch(re.escape(ACCESS_PREFIX) + r"adm_[0-9a-f]{12}", header), "撤权原输入必须唯一")
        source = json.loads(encoded)
        require(set(source) == {"owner_id", "case_ids", "task_ids", "assignee_id"}
                and len(source["case_ids"]) == len(source["task_ids"]) == 2
                and context["principal"]["actor_id"] == source["owner_id"], "撤权准备必须是新员工本人原事项")
        calls = sum(message["role"] == "tool" for message in messages)
        background = bool(context["trigger"]["background_is_not_new_employee_instruction"])
        stage = None
        if calls:
            message = reply("事项已准备，请核对。")
        elif not background:
            steps = [{"key": "assign_" + str(index), "title": "分派第" + str(index + 1) + "项接待",
                      "object_ref": {"type": "case", "id": ident}, "form_ref": f"case:{ident}:assign",
                      "depends_on": ["assign_0"] if index else [],
                      "conditions": [{"type": "native_action_available", "object_ref": {"type": "case", "id": ident}, "action_key": "assign"}],
                      "completion_conditions": [{"type": "native_task_state", "task_id": source["task_ids"][index], "expected_status": "done"}]}
                     for index, ident in enumerate(source["case_ids"])]
            message = tool("save_work_plan", {"schema_version": 2, "goal": header, "steps": steps})
        else:
            run_id = context["trigger"]["run_id"]
            runs = _rows(provider.manifest["database_path"], "SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))
            require(len(runs) == 1 and runs[0]["auth_kind"] == "grant" and runs[0]["status"] == "running"
                    and runs[0]["owner_id"] == source["owner_id"], "管理员撤权必须发生于新员工实际Grant Run")
            run = runs[0]
            runtime = Path(provider.manifest["runtime_root"])
            arm = _load(runtime / "access-closeout-control.json")
            require(arm["session_id"] == run["session_id"] and arm["plan_id"] == run["plan_id"]
                    and arm["owner_id"] == run["owner_id"], "撤权响应门控串员工事项")
            user = _rows(provider.manifest["database_path"], "SELECT active,access_version FROM users WHERE id=?", (run["owner_id"],))[0]
            require(user["active"] == 1, "到达响应边界前员工已被停用")
            stage_path = runtime / ("access-prepare-" + run_id + ".json")
            release_path = runtime / ("access-prepare-" + run_id + "-release.json")
            require(not stage_path.exists() and not release_path.exists(), "撤权响应拒绝旧装置文件")
            stage = {"scope": arm["scope"], "run_id": run_id, "session_id": run["session_id"], "plan_id": run["plan_id"],
                     "grant_id": run["grant_id"], "owner_id": run["owner_id"], "access_version": user["access_version"],
                     "lease_owner": run["lease_owner"], "phase": "waiting_admin_commit", "utc": _utc(), "returned_after_access_commit": False}
            _atomic_json(stage_path, stage)
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and not release_path.is_file():
                    await asyncio.sleep(.025)
                release = _load(release_path) if release_path.is_file() else {}
                require(release.get("run_id") == run_id and release.get("scope") == arm["scope"]
                        and release.get("action") == "return_after_admin_commit", "管理员原提交后未释放唯一实际Run响应")
                current = _rows(provider.manifest["database_path"], "SELECT active,access_version FROM users WHERE id=?", (run["owner_id"],))[0]
                receipts = _rows(provider.manifest["database_path"], "SELECT * FROM user_access_receipts WHERE id=?", (release["receipt_id"],))
                require(current["active"] == 0 and current["access_version"] == user["access_version"] + 1
                        and len(receipts) == 1 and receipts[0]["target_id"] == run["owner_id"]
                        and receipts[0]["previous_version"] == user["access_version"], "迟到返回前没有实际原管理员撤权commit")
                stage.update(receipt_id=receipts[0]["id"], audit_id=receipts[0]["audit_id"], new_access_version=current["access_version"])
                message = tool("prepare_business_form", {"form_ref": f"case:{source['case_ids'][0]}:assign",
                               "values": {"assignee_id": source["assignee_id"]}, "summary": "分派接待"})
            except BaseException as error:
                stage.update(phase="aborted", error_type=type(error).__name__, ended_at=_utc())
                _atomic_json(stage_path, stage)
                raise
        response = _response(provider, body, message, calls, background)
        if stage is not None:
            stage.update(phase="returned_after_admin_commit", returned_after_access_commit=True, returned_at=_utc())
            _atomic_json(stage_path, stage)
        return response

    provider.handle = handle


async def _employee_plan(e, employee, token, *, administrator_page):
    employee_page = e.page
    cases = []
    for index in range(2):
        e.action("navigate", "新员工本人创建独立原接待", index=index)
        await e.page.goto(e.origin + "/#cases/lead", wait_until="domcontentloaded")
        await expect(e.page.locator("#main h1")).to_have_text("售前接待")
        await e.click('[data-act="newcase"][data-kind="lead"]', "本人原新接待表单")
        await e.fill('#modal [name="customer_name"]', "撤权合成" + token + str(index))
        await e.page.locator('#modal [name="source"]').select_option(label="展厅到店")
        e.action("select", "原接待来源", value="展厅到店")
        created, _, _ = await native_submit(e, "/api/flow/cases", 201)
        value = facts(e, created["id"])
        require(value["case"]["created_by"] == employee["id"] and value["case"]["state"] == "unassigned", "原接待不是该员工本人真实来源")
        original_task = task(value, "assign")
        if original_task["assignee_id"] != employee["id"]:
            # Original least-load assignment may choose another reception
            # employee. Only the original administrator UI may hand it over.
            e.page = administrator_page
            e.action("navigate", "原管理员读取新员工真实接待并交接原任务", case_id=created["id"])
            await e.page.goto(e.origin + "/#case/" + str(created["id"]), wait_until="domcontentloaded")
            await expect(e.page.locator("#main h1")).to_have_text(value["case"]["title"])
            selector = f'#main [data-act="assign"][data-id="{original_task["id"]}"]'
            await expect(e.page.locator(selector)).to_be_visible()
            await e.click(selector, "原管理员仅交接本场新员工原assign任务")
            await employee_choice(e, employee)
            reason = "本场新员工本人继续核对原接待，保留真实创建人和客户来源。"
            await e.fill('#modal [name="reason"]', reason)
            _, metadata, _ = await native_submit(e, f'/api/flow/tasks/{original_task["id"]}/assign', 200, case_id=created["id"])
            changed = facts(e, created["id"])
            same_original(value, changed)
            event = new_event(value, changed, "reassign", e.manifest["users"]["admin"]["id"])
            assigned = task(changed, "assign")
            require(assigned["id"] == original_task["id"] and assigned["version"] == original_task["version"] + 1
                    and assigned["assignee_id"] == employee["id"] and assigned["status"] == "open"
                    and changed["case"] == value["case"] and changed["customer"] == value["customer"]
                    and event["detail"] == {"task_id": original_task["id"], "from": original_task["assignee_id"],
                                               "to": employee["id"], "reason": reason},
                    "原任务交接必须只改变实际Task及追加事件，保留原Case和客户")
            e.observe("new_employee_original_task_handoff", {"native_api": metadata, "task_id": assigned["id"],
                      "original_assignee_id": original_task["assignee_id"], "employee_id": employee["id"],
                      "completed_before_plan_and_grant": True})
            e.page = employee_page
            value = changed
        cases.append(value)
    e.action("navigate", "新员工本人原助手创建事项")
    await e.page.goto(e.origin + "/#business-assistant", wait_until="domcontentloaded")
    await e.ready()
    await e.new_matter()
    source = {"owner_id": employee["id"], "case_ids": [value["case"]["id"] for value in cases],
              "task_ids": [task(value, "assign")["id"] for value in cases], "assignee_id": e.manifest["users"]["sales"]["id"]}
    before = e.business_snapshot("admin_revoke_before_employee_plan")
    await e.send(ACCESS_PREFIX + "adm_" + uuid.uuid4().hex[:12] + "\n" + json.dumps(source, ensure_ascii=False))
    sid = e.latest_session
    plans = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE session_id=?", (sid,))
    threads = e.db.rows("SELECT owner_id,owner_role,access_version FROM business_assistant_sessions WHERE id=?", (sid,))
    require(len(plans) == len(threads) == 1 and plans[0]["owner_id"] == threads[0]["owner_id"] == employee["id"]
            and threads[0]["owner_role"] == "reception" and threads[0]["access_version"] == employee["access_version"],
            "本人新事项真实岗位或归属错误")
    require(not e.db.proposals(employee["id"], session_id=sid), "新员工尚未开启Grant就准备卡")
    e.business_unchanged(before, "admin_revoke_employee_plan_no_business_write")
    await expect(e.page.locator("#ba-current-plan .ba-plan-goal")).to_contain_text(plans[0]["goal"], timeout=20000)
    await expect(e.page.locator('[data-baws-followup="enable"]')).to_be_enabled(timeout=20000)
    return sid, plans[0], cases


async def administrator_access_inflight(e, context, credentials):
    token, original_page = uuid.uuid4().hex[:10], e.page
    store_id = e.manifest["stores"][0]["id"]
    admin = await login_as(e, context, credentials, "admin", "stores", store_id)
    _, private = private_accounts(e, token)
    secret = private["accounts"]["receiver"]
    own_store, _ = await store_form(e, admin, store_id, {"name": "撤权合成店" + token, "code": "AC" + token, "active": True})
    employee, created = await create_staff(e, admin, store_id, secret, "撤权合成员工" + token, {store_id: "reception"})
    employee_context = await context.browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    try:
        employee_page = await employee_context.new_page()
        await e.attach(employee_context, employee_page)
        await native_login(e, employee, secret["initial"], first=True)
        await personal_password(e, employee, secret["initial"], secret["first"], store_id, opened=True)
        employee = one(e, "users", employee["id"])
        await native_login(e, employee, secret["first"])
        sid, plan, cases = await _employee_plan(e, employee, token, administrator_page=original_page)
        # Prepare the original administrator form before arming the short
        # response boundary. No administrator business commit occurs here.
        e.page = original_page
        await open_page(e, "users", "员工账号", "/api/users")
        await e.click(f'[data-act="edituser"][data-id="{employee["id"]}"]', "原管理员核对仅新员工撤权表单")
        await field(e, "display_name", employee["display_name"])
        await checkbox(e, '#modal [name="active"]', False, "明确停用仅本场新员工")
        e.page = employee_page
        arm = {"scope": uuid.uuid4().hex, "session_id": sid, "plan_id": plan["id"], "owner_id": employee["id"]}
        runtime = Path(e.manifest["runtime_root"])
        _atomic_json(runtime / "access-closeout-control.json", arm)
        _atomic_json(_control_path(e.manifest), arm)
        await e.followup_click("enable", "新员工本人明确开启自己的跟进")
        stage_path = await e.wait(lambda: next((path for path in runtime.glob("access-prepare-*.json")
            if "-release" not in path.name and _load(path).get("scope") == arm["scope"]), None), "真实新员工Grant Run准备响应", timeout=40)
        stage = _load(stage_path)
        require(stage["phase"] == "waiting_admin_commit", "原准备响应已提前退出边界")
        require(sessions(e, employee["id"]) > 0 and not e.db.proposals(employee["id"], session_id=sid), "原撤权前会话或零卡边界不符")
        e.page = original_page
        memberships = e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (employee["id"],))
        protection = before_write(e, updates={"users": {(employee["id"],)}, "user_stores": {identity(row, "user_stores") for row in memberships}},
                                  appends=("user_access_receipts", "audit_logs"), session_user=employee["id"])
        old_receipts = {row["id"] for row in protection[1]["user_access_receipts"]}
        body, request, info = await original_submit(e, "/api/users/" + str(employee["id"]), 200, method="PUT", store_id=store_id,
                                                  version=employee["access_version"])
        current = one(e, "users", employee["id"])
        require(request["active"] is False and request["access_version"] == employee["access_version"]
                and request["role"] == "sales" and request["store_roles"] == [{"store_id": store_id, "role": "reception"}]
                and current["active"] == 0 and current["access_version"] == employee["access_version"] + 1
                and current["password_hash"] == employee["password_hash"] and sessions(e, employee["id"]) == 0,
                "原管理员撤权身份、版本、岗位、密码或登录失效不符")
        audit = audit_one(e, protection, admin["id"], "update_user", "users", employee["id"],
                          reason="核对账号授权版本后修改；原登录会话全部失效")
        receipts = [row for row in e.db.rows("SELECT * FROM user_access_receipts ORDER BY id") if row["id"] not in old_receipts]
        require(len(receipts) == 1 and receipts[0]["actor_id"] == admin["id"] and receipts[0]["target_id"] == employee["id"]
                and receipts[0]["audit_id"] == audit["id"] and receipts[0]["request_key"] == request["request_id"]
                and receipts[0]["previous_version"] == employee["access_version"] and json.loads(receipts[0]["result"]) == body,
                "原撤权实际receipt/audit不匹配")
        safety = after_write(e, protection)
        signals = e.db.rows("SELECT * FROM business_assistant_wake_events WHERE signal_key=?",
                            ("user_access_receipt:" + str(receipts[0]["id"]) + ":store:" + str(store_id),))
        require(len(signals) == 1 and signals[0]["topic"] == "access.changed"
                and json.loads(signals[0]["source_ref"]) == {"type": "user_access_receipt", "id": receipts[0]["id"], "version": current["access_version"]},
                "原授权修改没有同事务实际access.changed source")
        after_commit = e.business_snapshot("admin_revoke_business_after_original_access_commit")
        _atomic_json(runtime / ("access-prepare-" + stage["run_id"] + "-release.json"),
                     {"scope": arm["scope"], "run_id": stage["run_id"], "receipt_id": receipts[0]["id"], "action": "return_after_admin_commit"})
        await e.wait(lambda: _load(stage_path).get("returned_after_access_commit") is True, "迟到prepare响应实际在撤权commit后返回", timeout=10)
        terminal = await e.wait(lambda: (rows[0] if (rows := e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (stage["run_id"],)))
            and rows[0]["status"] in {"failed", "cancelled"} else None), "原权限错误Run终止", timeout=35)
        grant = await e.wait(lambda: (rows[0] if (rows := e.db.rows("SELECT * FROM business_assistant_followup_grants WHERE id=?", (stage["grant_id"],)))
            and rows[0]["status"] == "revoked" and rows[0]["stop_reason"] == "permission_changed" else None), "原Grant权限失效真实清理", timeout=35)
        e.observe("original_admin_access_actual_terminal", {"run_id": terminal["id"], "status": terminal["status"],
                  "attempt": terminal["attempt"], "error_code": terminal["error_code"], "stop_requested": bool(terminal["stop_requested"]),
                  "finished_at": terminal["finished_at"], "grant_id": grant["id"], "grant_stop_reason": grant["stop_reason"],
                  "grant_revoked_at": grant["revoked_at"], "receipt_id": receipts[0]["id"], "wake_id": signals[0]["id"],
                  "late_response_stage": _load(stage_path), "twenty_ticks_not_yet_checked": True})
        require(terminal["error_code"] == "permission_denied", "撤权被误归因成业务错误或可重试网络失败")
        ticks = await e.wait(lambda: [row for row in _observations(e, arm["scope"])["ticks"] if row["run_id"] == stage["run_id"]],
                             "原撤权Run所属实际worker tick", timeout=25)
        workers = {(row["pid"], row["worker_id"]) for row in ticks}
        require(len(workers) == 1, "撤权Run不能跨worker累加观察")
        worker = workers.pop()
        tick_start = len(_observations(e, arm["scope"], worker)["ticks"])
        await e.wait(lambda: len(_observations(e, arm["scope"], worker)["ticks"]) >= tick_start + 20,
                     "权限终止后20个同一原worker tick无重试", timeout=130)
        runs = e.db.rows("SELECT id,status,attempt,error_code FROM business_assistant_runs WHERE plan_id=? AND auth_kind='grant'", (plan["id"],))
        require(len(runs) == 1 and runs[0]["id"] == stage["run_id"] and runs[0]["attempt"] == terminal["attempt"]
                and runs[0]["status"] in {"failed", "cancelled"} and runs[0]["error_code"] == "permission_denied"
                and not e.db.proposals(employee["id"], session_id=sid)
                and not e.db.rows("SELECT id FROM business_assistant_work_items WHERE session_id=? AND item_kind='prepare'", (sid,)),
                "撤权迟到准备、新Run或权限错误退避重试")
        e.business_unchanged(after_commit, "admin_revoke_late_response_and_twenty_ticks_no_business_write")
        await revoked_page(e, employee_page, employee["id"])
        await e.snapshot("admin-revoked-original-employee-page-no-late-card")
        e.observe("original_admin_access_inflight", {"new_employee_id": employee["id"], "new_store_id": own_store["id"],
                  "original_ui_new_employee": created, "original_access_submit": info, "source_safety": safety,
                  "receipt_id": receipts[0]["id"], "audit_id": audit["id"], "wake_event_id": signals[0]["id"],
                  "grant_id": grant["id"], "grant_stop_reason": grant["stop_reason"], "run": runs[0],
                  "response_stage": _load(stage_path), "no_change_ticks": len(_observations(e, arm["scope"], worker)["ticks"]) - tick_start,
                  "counted_worker": {"pid": worker[0], "worker_id": worker[1]}, "original_case_ids": [value["case"]["id"] for value in cases],
                  "business_after_access_commit_sha256": after_commit["sha256"], "clock_or_deadline_modified": False,
                  "existing_fixture_accounts_modified": False, "actual_access_source_digest": _digest(json.loads(signals[0]["source_ref"]))})
        control = runtime / "access-closeout-control.json"
        require(_load(control)["scope"] == arm["scope"], "撤权控制scope意外切换")
        control.unlink()
    finally:
        e.page = original_page
        await employee_context.close()


ACCESS_CLOSEOUT_SCENARIOS = (("runtime-original-admin-access-revoke-inflight-prepare", administrator_access_inflight, 330),)
