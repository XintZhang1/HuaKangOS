"""Real source-map transactions, duplicates and natural late-event dispatch."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, expect

from runtime_access_closeout import _employee_plan
from runtime_faults import _atomic_json, _digest, _load, _rows, _utc
from runtime_receipt_closeout import _prepare_flow
from sales_business import employee_choice, facts, login_as, native_submit, new_event, require, task
from system_management_business import (
    create_staff, field, native_login, one, open_page, personal_password,
    private_accounts, store_form,
)
from vehicle_purchase_business import checkbox


SOURCE_TABLES = ("flow_customers", "flow_cases", "flow_tasks", "flow_events", "audit_logs",
                 "users", "user_stores", "stores", "login_sessions", "user_access_receipts",
                 "business_assistant_sessions", "business_assistant_work_plans", "business_assistant_plan_steps",
                 "business_assistant_proposals", "business_assistant_followup_grants")


def _fingerprints(read):
    return {table: {"rows": len(rows), "sha256": _digest(rows)}
            for table in SOURCE_TABLES for rows in [read("SELECT * FROM " + table + " ORDER BY rowid")]}


def _runtime_rows(e, arm):
    result = {table: e.db.rows("SELECT * FROM " + table + " WHERE store_id=? ORDER BY id", (arm["store_id"],))
              for table in ("business_assistant_wake_events", "business_assistant_notifications")}
    sid = arm.get("session_id")
    if sid:
        for table in ("business_assistant_work_plans", "business_assistant_proposals", "business_assistant_followup_grants",
                      "business_assistant_runs", "business_assistant_work_items", "business_assistant_context_snapshots"):
            result[table] = e.db.rows("SELECT * FROM " + table + " WHERE session_id=? ORDER BY id", (sid,))
        result["business_assistant_sessions"] = e.db.rows("SELECT * FROM business_assistant_sessions WHERE id=?", (sid,))
        result["business_assistant_run_events"] = e.db.rows(
            "SELECT * FROM business_assistant_run_events WHERE run_id IN (SELECT id FROM business_assistant_runs WHERE session_id=?) ORDER BY id", (sid,))
        result["business_assistant_run_items"] = e.db.rows(
            "SELECT * FROM business_assistant_run_items WHERE run_id IN (SELECT id FROM business_assistant_runs WHERE session_id=?) ORDER BY id", (sid,))
        result["business_assistant_plan_steps"] = e.db.rows(
            "SELECT * FROM business_assistant_plan_steps WHERE plan_id IN (SELECT id FROM business_assistant_work_plans WHERE session_id=?) ORDER BY id", (sid,))
    return result


@contextmanager
def source_hook_faults(manifest):
    """Fixed original emit calls only; source data and schedules are untouched."""
    require(manifest.get("synthetic_data_only") is True, "source hook装置仅允许全新外部合成实例")
    from unittest.mock import patch
    from sqlalchemy import text
    from app import assistant_runtime_outbox as outbox, assistant_runtime_access_signals as access

    original_emit, original_access, original_cas, original_dispatch = outbox.emit_wake_event, access._emit, outbox._event_cas, outbox.dispatch_one
    runtime, evidence = Path(manifest["runtime_root"]), Path(manifest["evidence_root"])
    path = evidence / ("source-hook-observations-" + str(os.getpid()) + ".json")
    control_path = runtime / "source-hook-control.json"
    consumed, order_consumed = set(), set()
    report = {"schema": 1, "pid": os.getpid(), "producer_failures": [], "duplicates": [], "order_failures": []}

    def save():
        _atomic_json(path, report)

    def arm():
        return _load(control_path) if control_path.is_file() else None

    def read(db, sql, values=None):
        return [dict(row) for row in db.execute(text(sql), values or {}).mappings()]

    def case_name(db, ident):
        rows = read(db, "SELECT c.created_by,u.name FROM flow_cases c JOIN flow_customers u ON u.id=c.customer_id WHERE c.id=:id", {"id": ident})
        return rows[0] if len(rows) == 1 else None

    def matches(db, control, topic, refs):
        kind, source = control["kind"], refs["source_ref"]
        if refs["store_id"] != control["store_id"]:
            return False
        if kind in {"flow", "order"}:
            obj = refs.get("object_ref") or {}
            row = case_name(db, obj.get("id")) if obj.get("type") == "case" else None
            names = control.get("names", [control.get("name")])
            return topic == "flow" and source["type"] == "flow_event" and row is not None and row["name"] in names and row["created_by"] == control["owner_id"]
        if kind == "task":
            return topic == "task" and refs.get("task_id") == control["task_id"] and source["type"] == "task"
        if kind == "proposal":
            return topic == "proposal" and refs.get("proposal_id") == control["proposal_id"] and source["type"] == "proposal"
        if kind == "grant":
            return topic == "grant" and refs.get("plan_id") == control["plan_id"] and source["type"] == "grant"
        if kind == "plan_close":
            return topic == "grant" and refs.get("plan_id") == control["plan_id"] and source["type"] == "plan"
        return False

    def producer_failure(db, control, event_ids, source_ref):
        key = control["scope"], control["kind"]
        if key in consumed:
            return
        sources = _fingerprints(lambda sql: read(db, sql))
        changes = [table for table in SOURCE_TABLES if sources[table] != control["source_before"][table]]
        events = read(db, "SELECT * FROM business_assistant_wake_events WHERE id IN (" +
                      ",".join(":id" + str(index) for index in range(len(event_ids))) + ") ORDER BY id",
                      {"id" + str(index): ident for index, ident in enumerate(event_ids)})
        require(events and changes, "必须已有实际原source改变及同事务真实Wake flush后再注入")
        report["producer_failures"].append({"scope": control["scope"], "kind": control["kind"], "utc": _utc(),
            "source_ref": source_ref, "actual_event_ids": list(event_ids), "actual_changed_source_tables": changes,
            "flushed_source_fingerprints": sources, "flushed_wake_events": events, "injection_count": 1})
        consumed.add(key)
        save()
        raise RuntimeError("Fixed synthetic original source hook failure after real Wake flush")

    def emit(db, signal_key, topic, refs, **kwargs):
        row = original_emit(db, signal_key, topic, refs, **kwargs)
        control = arm()
        if control is None or not matches(db, control, topic, refs):
            return row
        if control["kind"] != "order":
            producer_failure(db, control, (row.id,), refs["source_ref"])
        else:
            before = read(db, "SELECT * FROM business_assistant_wake_events WHERE id=:id", {"id": row.id})[0]
            duplicate = original_emit(db, signal_key, topic, refs, **kwargs)
            after = read(db, "SELECT * FROM business_assistant_wake_events WHERE id=:id", {"id": row.id})[0]
            require(duplicate.id == row.id and before == after, "同一真实source重复emit改变原event或重置退避")
            report["duplicates"].append({"scope": control["scope"], "utc": _utc(), "source_ref": refs["source_ref"],
                "event_id": row.id, "signal_key": signal_key, "before": before, "after": after, "same_original_transaction": True})
            old_id = control.get("replay_dispatched_id")
            if old_id:
                prior = read(db, "SELECT * FROM business_assistant_wake_events WHERE id=:id", {"id": old_id})[0]
                old_refs = {key: json.loads(prior[key]) if key in {"object_ref", "source_ref"} and prior[key] is not None else prior[key]
                            for key in ("store_id", "object_ref", "proposal_id", "task_id", "plan_id", "source_ref")}
                old = original_emit(db, prior["signal_key"], prior["topic"], old_refs)
                current = read(db, "SELECT * FROM business_assistant_wake_events WHERE id=:id", {"id": old_id})[0]
                require(old.id == old_id and prior["state"] == "dispatched" and prior == current,
                        "已分发真实source重复emit重置状态或自然调度")
                report["duplicates"].append({"scope": control["scope"], "utc": _utc(), "source_ref": old_refs["source_ref"],
                    "event_id": old_id, "signal_key": prior["signal_key"], "before": prior, "after": current,
                    "same_original_transaction": True, "already_dispatched_original_source": True})
            save()
        return row

    def access_emit(db, stores, *, key_prefix, topic, source_ref):
        ids = original_access(db, stores, key_prefix=key_prefix, topic=topic, source_ref=source_ref)
        control = arm()
        if control is None or control["kind"] not in {"access", "security", "store"}:
            return ids
        if control["kind"] == "access":
            target = read(db, "SELECT target_id FROM user_access_receipts WHERE id=:id", {"id": source_ref["id"]}) if source_ref["type"] == "user_access_receipt" else []
            matches_target = len(target) == 1 and target[0]["target_id"] == control["target_id"]
        else:
            target = read(db, "SELECT entity_id,entity_type,action FROM audit_logs WHERE id=:id", {"id": source_ref["id"]}) if source_ref["type"] == "audit_log" else []
            matches_target = (len(target) == 1 and target[0]["entity_id"] == control["target_id"]
                and (target[0]["entity_type"], target[0]["action"]) ==
                    (("users", "reset_password") if control["kind"] == "security" else ("stores", "update_store")))
        if matches_target:
            require(control["store_id"] in stores, "权限真实来源没有目标原门店")
            producer_failure(db, control, ids, source_ref)
        return ids

    def cas(db, event, *, state, now):
        result = original_cas(db, event, state=state, now=now)
        control = arm()
        if state != "dispatched" or control is None or control["kind"] != "order" or control["scope"] in order_consumed:
            return result
        obj = event.get("object_ref") or {}
        candidate = case_name(db, obj.get("id")) if obj.get("type") == "case" else None
        if event["topic"] != "flow" or candidate is None or candidate["name"] != control["names"][0] or candidate["created_by"] != control["owner_id"]:
            return result
        db.info["synthetic_order_failure"] = {"scope": control["scope"], "event": event, "injected_at": _utc()}
        order_consumed.add(control["scope"])
        raise RuntimeError("Fixed synthetic first real Flow dispatch failure")

    async def dispatch(db, *args, **kwargs):
        result = await original_dispatch(db, *args, **kwargs)
        state = db.info.pop("synthetic_order_failure", None)
        if state is not None:
            current = _rows(manifest["database_path"], "SELECT * FROM business_assistant_wake_events WHERE id=?", (state["event"]["id"],))[0]
            require(result.state == current["state"] == "pending" and current["attempt"] == state["event"]["attempt"] + 1,
                    "首真实Flow失败未自然pending退避")
            report["order_failures"].append({"scope": state["scope"], "event_id": current["id"], "injected_at": state["injected_at"],
                "pending_after_failure": current, "injection_count": 1})
            save()
        return result

    save()
    with patch.object(outbox, "emit_wake_event", emit), patch.object(access, "_emit", access_emit), \
            patch.object(outbox, "_event_cas", cas), patch.object(outbox, "dispatch_one", dispatch):
        yield


def _reports(e, scope, key):
    return [row for path in Path(e.manifest["evidence_root"]).glob("source-hook-observations-*.json")
            for row in _load(path)[key] if row["scope"] == scope]


async def _fault_submit(e, target, path, kind, store_id, *, method="POST", **source):
    await e.wait(lambda: not [row for row in e.db.rows(
        "SELECT id,next_attempt_at FROM business_assistant_wake_events WHERE store_id=? AND state='pending'", (store_id,))
        if datetime.fromisoformat(row["next_attempt_at"]).replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)],
        "原store已到期Wake自然分发后冻结完整新旧Wake观察", timeout=75)
    arm = {"scope": uuid.uuid4().hex, "kind": kind, "store_id": store_id, **source,
           "source_before": _fingerprints(e.db.rows)}
    before = e.business_snapshot("source_" + kind + "_before_original_transaction")
    runtime_before = _runtime_rows(e, arm)
    login_before = _digest(e.db.rows("SELECT * FROM login_sessions ORDER BY id"))
    control = Path(e.manifest["runtime_root"]) / "source-hook-control.json"
    _atomic_json(control, arm)
    async with e.page.expect_response(lambda response: response.request.method == method and urlsplit(response.url).path == path) as pending:
        await e.click(target, "原" + kind + "生产者表单仅提交一次，固定signal故障")
    response = await pending.value
    await response.body()
    require(response.status == 500, "原source固定抛错没有实际原HTTP失败")
    headers = await response.request.all_headers()
    require(headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-store-id"), "source写未使用真实本人Cookie/CSRF/store")
    injected = await e.wait(lambda: _reports(e, arm["scope"], "producer_failures"), "原source真实flush后固定失败账本")
    require(len(injected) == 1 and injected[0]["injection_count"] == 1, "原source故障不是唯一实际注入")
    e.business_unchanged(before, "source_" + kind + "_original_business_rollback_exact")
    require(_runtime_rows(e, arm) == runtime_before and _digest(e.db.rows("SELECT * FROM login_sessions ORDER BY id")) == login_before,
            "原source、登录会话或新/旧Runtime Wake等未完整回滚")
    require(_load(control)["scope"] == arm["scope"], "source控制scope意外切换")
    control.unlink()
    e.injected_http_failures.append({"scope": arm["scope"], "kind": kind, "path": path, "method": method,
        "status": response.status, "unique_injection_proven": True, "whole_transaction_rollback_proven": True})
    e.observe("source_hook_original_transaction_rollback", {"kind": kind, "path": path, "method": method, "native_status": response.status,
              "actual_fault": injected[0], "original_business_sha256": before["sha256"], "runtime_before_after_sha256": _digest(runtime_before),
              "login_before_after_sha256": login_before, "all_original_rows_rolled_back": True, "all_new_wake_rows_rolled_back": True,
              "fault_disarmed_before_next_native_action": True, "clock_or_deadline_modified": False})
    await e.snapshot("source-" + kind + "-actual-transaction-rollback")


async def _case_form(e, name):
    e.action("navigate", "原页面准备唯一新接待来源", name=name)
    await e.page.goto(e.origin + "/#cases/lead", wait_until="domcontentloaded")
    await expect(e.page.locator("#main h1")).to_have_text("售前接待")
    await e.click('[data-act="newcase"][data-kind="lead"]', "原新接待表单")
    await e.fill('#modal [name="customer_name"]', name)
    e.action("select", "原接待来源", value="展厅到店")
    await e.page.locator('#modal [name="source"]').select_option(label="展厅到店")


async def _create_case(e, name):
    await _case_form(e, name)
    body, _, _ = await native_submit(e, "/api/flow/cases", 201)
    value = facts(e, body["id"])
    await expect(e.page.locator("#main h1")).to_have_text(value["case"]["title"])
    return value


async def _discard_failed_form(e, label):
    before = e.business_snapshot("source_before_explicit_failed_form_discard")
    await e.click('#modal .modalhead [data-act="close"]', label)
    discard = e.page.locator('#modal [data-wfx-discard]')
    if await discard.count():
        await expect(discard).to_be_visible()
        await e.click('#modal [data-wfx-discard]', "本人明确放弃此已拒绝表单的未保存填写")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "source_after_explicit_failed_form_discard")


async def _arm_original_end(e, plan_id):
    settled = ("expectation => { const view=globalThis.AssistantWorkspace?.snapshot?.();"
        "return view?.plan?.id===expectation.id && view.plan.revokeArmed===expectation.armed"
        "&& !view.planLoading && !view.followupPending && !businessAssistantState.workLoading"
        "&& !businessAssistantState.busy && !businessAssistantState.runId; }")
    button = e.page.locator('[data-baws-followup="revoke"]')

    async def wait_settled(armed, stage):
        try:
            await e.page.wait_for_function(settled, arg={"id": plan_id, "armed": armed}, timeout=20000)
        except PlaywrightTimeoutError:
            try:
                view = await e.page.evaluate("""() => {
                    const workspace=globalThis.AssistantWorkspace?.snapshot?.(), button=document.querySelector('[data-baws-followup="revoke"]');
                    return {plan:workspace?.plan, planLoading:workspace?.planLoading, followupPending:workspace?.followupPending,
                        planError:workspace?.planError, workLoading:businessAssistantState.workLoading,
                        workErrorPresent:!!businessAssistantState.workError, workPlanId:businessAssistantState.workPlanId,
                        busy:businessAssistantState.busy, runId:businessAssistantState.runId,
                        button:button?{text:button.textContent.trim(),disabled:button.disabled,visible:!!button.getClientRects().length}:null};
                }""")
                if view.get("planError"):
                    view["planError"] = e.scrub(view["planError"])
                e.observe("original_followup_settlement_timeout", {"stage": stage, "plan_id": plan_id,
                    "expected_revoke_armed": armed, "readonly_workspace": view,
                    "durable_plan": e.db.rows("SELECT id,status,version,goal_version FROM business_assistant_work_plans WHERE id=?", (plan_id,)),
                    "durable_grants": e.db.rows("SELECT id,plan_id,status,version,goal_version,stop_reason FROM business_assistant_followup_grants WHERE plan_id=? ORDER BY id", (plan_id,)),
                    "state_or_clock_modified": False})
                await e.snapshot("source-original-end-timeout-" + stage)
            except Exception as diagnostic_error:
                e.observe("original_followup_settlement_timeout_diagnostic_error", {"stage": stage, "plan_id": plan_id,
                    "error": e.scrub(diagnostic_error), "original_timeout_preserved": True})
            raise

    # Receiving HTTP 500 does not mean the original browser catch/finally has
    # cleared its confirmation. Let that UI settle before refreshing its scope.
    e.action("await_original_followup_settlement", "原失败前端结算后再重新核对结束", plan_id=plan_id, revoke_armed=False)
    await wait_settled(False, "before-refresh")
    await expect(button).to_have_text("结束这件事")
    await expect(button).to_be_enabled()
    await e.click('[data-ba-action="refresh"]', "原结束前完整重读同一事项")
    await e.ready()
    await wait_settled(False, "after-refresh")
    await expect(button).to_have_text("结束这件事")
    await expect(button).to_be_enabled()
    await e.click('[data-baws-followup="revoke"]', "本人原结束第一次核对")
    await wait_settled(True, "after-first-confirmation")
    await expect(button).to_have_text("确认结束这件事")
    await expect(button).to_be_enabled()


async def source_map_original_rollbacks(e, context, credentials):
    token, admin_page = uuid.uuid4().hex[:10], e.page
    store_id = e.manifest["stores"][0]["id"]
    admin = await login_as(e, context, credentials, "admin", "stores", store_id)
    own_store, _ = await store_form(e, admin, store_id, {"name": "信号合成店" + token, "code": "SH" + token, "active": True})
    _, private = private_accounts(e, token)
    secret = private["accounts"]["receiver"]
    employee, _ = await create_staff(e, admin, store_id, secret, "信号合成员工" + token, {store_id: "reception"})
    employee_context = await context.browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    card_context = await context.browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    try:
        employee_page = await employee_context.new_page()
        await e.attach(employee_context, employee_page)
        await native_login(e, employee, secret["initial"], first=True)
        await personal_password(e, employee, secret["initial"], secret["first"], store_id, opened=True)
        employee = one(e, "users", employee["id"])
        await native_login(e, employee, secret["first"])
        sid, plan, _ = await _employee_plan(e, employee, token, administrator_page=admin_page)
        await _fault_submit(e, '[data-baws-followup="enable"]', "/api/business-assistant/plans/" + plan["id"] + "/followup",
                            "grant", store_id, plan_id=plan["id"], session_id=sid)
        await _arm_original_end(e, plan["id"])
        await _fault_submit(e, '[data-baws-followup="revoke"]', "/api/business-assistant/plans/" + plan["id"] + "/followup",
                            "plan_close", store_id, plan_id=plan["id"], session_id=sid)
        await _arm_original_end(e, plan["id"])
        await e.followup_click("revoke", "解除装置后原本人正常关闭无Grant事项")
        e.page = admin_page
        name = "信号故障Flow" + token
        await _case_form(e, name)
        await _fault_submit(e, '#modal form button[type="submit"]', "/api/flow/cases", "flow", store_id, name=name, owner_id=admin["id"])
        await _discard_failed_form(e, "原Flow故障后取消未保存表单，不重放请求")
        source = await _create_case(e, "信号独立Task" + token)
        original_task = task(source, "assign")
        recipient = employee if original_task["assignee_id"] != employee["id"] else e.manifest["users"]["reception"]
        require(original_task["assignee_id"] != recipient["id"], "Task交接必须真实改变接手人")
        await expect(e.page.locator(f'#main [data-act="assign"][data-id="{original_task["id"]}"]')).to_be_visible()
        await e.click(f'#main [data-act="assign"][data-id="{original_task["id"]}"]', "原主管仅交接独立新任务")
        await employee_choice(e, recipient)
        await e.fill('#modal [name="reason"]', "信号事务回滚合成核查")
        await _fault_submit(e, '#modal form button[type="submit"]', f'/api/flow/tasks/{original_task["id"]}/assign', "task", store_id,
                            task_id=original_task["id"])
        await _discard_failed_form(e, "Task故障后关闭原未保存表单")
        await open_page(e, "users", "员工账号", "/api/users")
        await e.click(f'[data-act="edituser"][data-id="{employee["id"]}"]', "原管理员仅编辑独立新员工")
        await checkbox(e, '#modal [name="active"]', False, "原员工授权停用值")
        await _fault_submit(e, '#modal form button[type="submit"]', f'/api/users/{employee["id"]}', "access", store_id,
                            method="PUT", target_id=employee["id"])
        await _discard_failed_form(e, "授权故障后关闭原未保存表单")
        await e.click(f'[data-act="resetpassword"][data-id="{employee["id"]}"]', "原管理员只重置独立新员工")
        await field(e, "password", secret["reset"], private=True)
        await field(e, "reason", "原密码安全信号事务回滚合成核查")
        await _fault_submit(e, '#modal form button[type="submit"]', f'/api/users/{employee["id"]}/password', "security", store_id,
                            target_id=employee["id"])
        await _discard_failed_form(e, "密码故障后关闭原未保存表单")
        await open_page(e, "stores", "门店设置", "/api/stores")
        await e.click(f'[data-act="editstore"][data-id="{own_store["id"]}"]', "仅独立新店原停用表单")
        await checkbox(e, '#modal [name="active"]', False, "原新店停用值")
        await _fault_submit(e, '#modal form button[type="submit"]', f'/api/stores/{own_store["id"]}', "store", own_store["id"],
                            method="PUT", target_id=own_store["id"])
        await _discard_failed_form(e, "原新店故障后取消未保存表单")
        card_page = await card_context.new_page()
        await e.attach(card_context, card_page)
        prepared = await _prepare_flow(e, card_context, credentials, "freeze")
        await expect(e.page.locator('[data-ba-action="cancel-proposal"][data-id="' + prepared["card"]["id"] + '"]')).to_be_enabled()
        await _fault_submit(e, '[data-ba-action="cancel-proposal"][data-id="' + prepared["card"]["id"] + '"]',
                            "/api/business-assistant/sessions/" + prepared["session_id"] + "/proposals/" + prepared["card"]["id"] + "/cancel",
                            "proposal", store_id, proposal_id=prepared["card"]["id"], session_id=prepared["session_id"])
        require(e.db.rows("SELECT status FROM business_assistant_proposals WHERE id=?", (prepared["card"]["id"],))[0]["status"] == "pending",
                "原取消source失败后卡未完整回滚pending")
        await e.click('[data-ba-action="refresh"]', "原取消故障后重新核对真实pending卡")
        await e.ready()
        async with e.page.expect_response(lambda response: urlsplit(response.url).path.endswith("/cancel")) as pending:
            await e.click('[data-ba-action="cancel-proposal"][data-id="' + prepared["card"]["id"] + '"]', "解除故障后本人重新核对并正常取消")
        require((await pending.value).status == 200, "原取消在解除固定故障后未正常提交")
        e.observe("all_source_map_native_producers_executed", {"families": ["flow", "task", "proposal", "grant", "access", "security", "store"],
                  "extra_original_no_grant_plan_close": True, "actual_original_transactions": 8,
                  "existing_fixture_accounts_modified": False, "all_proposal_branches_claimed": False,
                  "all_unmapped_domain_producers_claimed": False})
    finally:
        e.page = admin_page
        await card_context.close()
        await employee_context.close()


async def real_source_late_dispatch_duplicates(e, context, credentials):
    store_id = e.manifest["stores"][0]["id"]
    user = await login_as(e, context, credentials, "admin", "cases/lead", store_id)
    token = uuid.uuid4().hex[:10]
    names = ["后到原Flow甲" + token, "后到原Flow乙" + token]
    arm = {"scope": uuid.uuid4().hex, "kind": "order", "store_id": store_id, "owner_id": user["id"], "names": names}
    control = Path(e.manifest["runtime_root"]) / "source-hook-control.json"
    _atomic_json(control, arm)
    first = await _create_case(e, names[0])
    failed = await e.wait(lambda: _reports(e, arm["scope"], "order_failures"), "首个真实Flow自然分发失败及pending", timeout=35)
    require(len(failed) == 1 and failed[0]["injection_count"] == 1, "首原Flow实际故障次数错误")
    delay = (datetime.fromisoformat(failed[0]["pending_after_failure"]["next_attempt_at"]) -
             datetime.fromisoformat(failed[0]["injected_at"]).replace(tzinfo=None)).total_seconds()
    require(28 <= delay <= 32, "首真实Flow没有原30秒自然退避")
    first_task = task(first, "assign")
    if not any(value["id"] == first_task["assignee_id"] for value in e.manifest["users"].values()):
        # Least-load routing can select a newly created synthetic employee.
        # Explicitly hand over this actual task to the known reception account
        # before testing that recipient's own login and notification controls.
        recipient = e.manifest["users"]["reception"]
        selector = f'#main [data-act="assign"][data-id="{first_task["id"]}"]'
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "原主管明确指定本场通知本人接手真实新任务")
        await employee_choice(e, recipient)
        reason = "本场原通知由明确原合成接待本人核对，不借用其他员工登录。"
        await e.fill('#modal [name="reason"]', reason)
        _, metadata, _ = await native_submit(e, f'/api/flow/tasks/{first_task["id"]}/assign', 200, case_id=first["case"]["id"])
        current = facts(e, first["case"]["id"])
        assigned = task(current, "assign")
        event = new_event(first, current, "reassign", user["id"])
        require(assigned["id"] == first_task["id"] and assigned["assignee_id"] == recipient["id"]
                and assigned["version"] == first_task["version"] + 1 and assigned["status"] == "open"
                and current["case"] == first["case"] and current["customer"] == first["customer"]
                and event["detail"] == {"task_id": first_task["id"], "from": first_task["assignee_id"],
                                           "to": recipient["id"], "reason": reason},
                "指定通知本人必须由原Task交接，只改变真实Task归属和版本")
        e.observe("late_source_original_recipient_handoff", {"native_api": metadata, "task_id": assigned["id"],
                  "recipient_id": recipient["id"], "original_assignee_id": first_task["assignee_id"]})
        first = current
    second = await _create_case(e, names[1])
    sources = []
    for value in (first, second):
        events = [row for row in value["events"] if row["action"] == "create"]
        require(len(events) == 1, "原接待仅应产生唯一create来源")
        rows = e.db.rows("SELECT * FROM business_assistant_wake_events WHERE signal_key=?", ("flow:" + str(events[0]["id"]),))
        require(len(rows) == 1, "实际FlowEvent没有唯一原signal_key")
        sources.append(rows[0])
    await e.wait(lambda: e.db.rows("SELECT state FROM business_assistant_wake_events WHERE id=?", (sources[1]["id"],))[0]["state"] == "dispatched",
                 "后创建真实Flow先于原退避来源分发", timeout=20)
    require(e.db.rows("SELECT state FROM business_assistant_wake_events WHERE id=?", (sources[0]["id"],))[0]["state"] == "pending",
            "未实际形成后创建先分发的自然窗口")
    await e.wait(lambda: e.db.rows("SELECT state FROM business_assistant_wake_events WHERE id=?", (sources[0]["id"],))[0]["state"] == "dispatched",
                 "较早原来源自然退避后独立恢复", timeout=65)
    recovered = [e.db.rows("SELECT * FROM business_assistant_wake_events WHERE id=?", (row["id"],))[0] for row in sources]
    require(recovered[0]["created_at"] < recovered[1]["created_at"] and recovered[1]["dispatched_at"] < recovered[0]["dispatched_at"]
            and recovered[0]["dispatched_at"] >= failed[0]["pending_after_failure"]["next_attempt_at"]
            and recovered[0]["attempt"] == 2 and recovered[1]["attempt"] == 1, "实际较早来源后到/自然恢复关系不成立")
    original_task = task(first, "assign")
    owner_id = original_task["assignee_id"]
    keys = [key for key, value in e.manifest["users"].items() if value["id"] == owner_id]
    require(len(keys) == 1, "原通知本人必须来自实际已知合成员工，不猜账号或使用管理员读取私人通知")
    notices = await e.wait(lambda: e.db.rows("SELECT * FROM business_assistant_notifications WHERE task_id=? AND owner_id=? AND kind='task_assigned'",
                                            (original_task["id"], owner_id)), "原source实际员工Task通知耐久", timeout=35)
    require(len(notices) == 1, "真实Task source原通知缺失或重复")
    await login_as(e, context, credentials, keys[0], "business-assistant", store_id)
    await e.ready()
    await e.click('[data-baws-action="notices"]', "原通知本人打开实际通知列表")
    await expect(e.page.locator('[data-baws-action="notice-open"][data-notice-id="' + notices[0]["id"] + '"]')).to_be_visible(timeout=20000)
    async with e.page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path ==
                                     "/api/business-assistant/notifications/" + notices[0]["id"] + "/read") as pending:
        await e.click('[data-baws-action="notice-open"][data-notice-id="' + notices[0]["id"] + '"]', "本人打开原任务并显式已读")
    read_response = await pending.value
    read_body = await read_response.json()
    e.observe("actual_original_notice_read_response", {"notice_id": notices[0]["id"], "native_status": read_response.status,
              "request_body_present": bool(read_response.request.post_data), "server_detail": e.scrub(read_body.get("detail", ""))})
    require(read_response.status == 200, "原本人通知已读未成功")
    require(not read_response.request.post_data, "原标记通知已读入口明确不接受请求内容")
    read_notice = e.db.rows("SELECT * FROM business_assistant_notifications WHERE id=?", (notices[0]["id"],))[0]
    require(read_notice["status"] == "read" and read_notice["read_at"] is not None, "真实原通知未持久已读")
    after_read = e.business_snapshot("late_source_read_notice_original_task_unchanged")
    require(e.db.rows("SELECT status FROM flow_tasks WHERE id=?", (original_task["id"],))[0]["status"] == "open", "读通知自动完成原任务")
    await login_as(e, context, credentials, "admin", "case/" + str(first["case"]["id"]), store_id)
    # A new original reassign event provides a real caller transaction in which
    # the older already-dispatched source can be duplicated without SQL writes.
    candidates = [e.manifest["users"][key] for key in ("admin", "manager", "reception")
                  if e.manifest["users"][key]["id"] != owner_id]
    require(candidates, "没有明确另一原接待岗位合成员工可形成真实交接来源")
    target = candidates[0]
    arm["replay_dispatched_id"] = recovered[0]["id"]
    _atomic_json(control, arm)
    await expect(e.page.locator(f'#main [data-act="assign"][data-id="{original_task["id"]}"]')).to_be_visible()
    await e.click(f'#main [data-act="assign"][data-id="{original_task["id"]}"]', "原主管明确交接形成后到真实事件")
    await employee_choice(e, target)
    await e.fill('#modal [name="reason"]', "已读真实来源重复核查的原任务交接")
    await native_submit(e, f'/api/flow/tasks/{original_task["id"]}/assign', 200, case_id=first["case"]["id"])
    after_native = e.business_snapshot("late_source_after_explicit_original_task_handoff")
    require(e.db.rows("SELECT * FROM business_assistant_notifications WHERE id=?", (read_notice["id"],))[0] == read_notice,
            "已分发原source重复使已读通知复活")
    duplicates = _reports(e, arm["scope"], "duplicates")
    require(any(row.get("already_dispatched_original_source") and row["event_id"] == recovered[0]["id"] for row in duplicates),
            "没有实际复用已分发旧source进行重复核验")
    require(e.db.rows("SELECT status FROM flow_tasks WHERE id=?", (original_task["id"],))[0]["status"] == "open", "重复或已读变成原任务完成")
    control.unlink()
    e.business_unchanged(after_native, "late_source_duplicate_no_additional_business_write")
    all_notices = e.db.rows("SELECT owner_id,store_id,source_key,kind FROM business_assistant_notifications WHERE store_id=?", (store_id,))
    require(len({tuple(row.values()) for row in all_notices}) == len(all_notices), "真实owner/store/source通知重复")
    e.observe("actual_late_source_and_duplicate_original_signal", {"source_events": recovered, "actual_fixed_failure": failed[0],
              "duplicates": duplicates, "actual_later_created_dispatched_first": True, "original_read_notice_id": read_notice["id"],
              "read_notice_kept": True, "native_task_status": "open", "native_201_case_ids": [first["case"]["id"], second["case"]["id"]],
              "business_read_notice_sha256": after_read["sha256"], "business_after_explicit_handoff_sha256": after_native["sha256"],
              "clock_or_deadline_modified": False})
    await e.snapshot("actual-older-source-later-recovery-read-notice-kept")


SOURCE_HOOK_CLOSEOUT_SCENARIOS = (
    ("runtime-original-source-map-seven-producer-transaction-rollbacks", source_map_original_rollbacks, 420),
    ("runtime-original-late-source-natural-backoff-duplicate-read-notice", real_source_late_dispatch_duplicates, 240),
)
