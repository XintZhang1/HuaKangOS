"""Original followup and pending-card paths in one fresh synthetic instance.

Only model replies and external observations are synthetic. Business sources,
permissions, plans, grants, scheduling, deadlines and confirmations are real.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
from urllib.parse import urlsplit

from playwright.async_api import expect

from runtime_faults import _atomic_json, _file_mutex, _load, _rows, _utc
from sales_business import facts, native_submit, require, task


PREFIX = "浏览器收口跟进 "


@contextmanager
def _observation_mutex(path):
    path = Path(path).resolve()
    if not re.fullmatch(r"followup-observations-[1-9][0-9]*\.json", path.name):
        raise ValueError("Observation mutex only accepts the exact PID report name")
    with _file_mutex(path):
        yield


def _read_observation(path):
    with _observation_mutex(path):
        return _load(path)


def _write_observation(path, value):
    with _observation_mutex(path):
        _atomic_json(path, value)


def _control_path(manifest):
    return Path(manifest["runtime_root"]) / "followup-observe-control.json"


@contextmanager
def observe_followup(manifest):
    """Record actual ticks and the native GETs within real fact evaluations."""
    require(manifest.get("synthetic_data_only") is True, "跟进观察器只允许外部合成实例")
    from unittest.mock import patch
    from app import assistant_runtime_plans as plans, business_assistant_gateway as gateway
    from app.assistant_worker import Worker

    path = Path(manifest["evidence_root"]) / ("followup-observations-" + str(os.getpid()) + ".json")
    current = ContextVar("synthetic_followup_fact_observation", default=None)
    report = {"schema": 1, "pid": os.getpid(), "ticks": [], "fact_checks": []}
    original_tick, original_facts, original_invoke = Worker.tick, plans._evaluate_plan_facts, gateway.invoke

    def control():
        file = _control_path(manifest)
        return _load(file) if file.is_file() else None

    async def tick(worker):
        scope = control()
        value = await original_tick(worker)
        if scope is not None:
            report["ticks"].append({"scope": scope["scope"], "session_id": scope["session_id"],
                                    "pid": os.getpid(), "worker_id": worker.worker_id,
                                    "run_id": value.get("run_id") if isinstance(value, dict) else None,
                                    "utc": _utc(), "maintenance": {key: value.get(key)
                                        for key in ("dispatch", "poll") if isinstance(value, dict)}})
            _write_observation(path, report)
        return value

    async def evaluate(db, principal, *args, **kwargs):
        scope = control()
        if scope is None or principal.session_id != scope["session_id"]:
            return await original_facts(db, principal, *args, **kwargs)
        row = {"scope": scope["scope"], "session_id": principal.session_id,
               "pid": os.getpid(), "lease_owner": principal.lease_owner,
               "plan_id": principal.plan_id, "run_id": principal.run_id,
               "auth_kind": principal.auth_kind, "grant_id": principal.grant_id,
               "goal_version": principal.goal_version, "started_at": _utc(), "native_gets": []}
        token = current.set(row)
        try:
            value = await original_facts(db, principal, *args, **kwargs)
            row["returned"] = True
            return value
        except BaseException as error:
            row["error_type"] = type(error).__name__
            raise
        finally:
            current.reset(token)
            row["finished_at"] = _utc()
            report["fact_checks"].append(row)
            _write_observation(path, report)

    async def invoke(request, user, operation_id, *args, **kwargs):
        result = await original_invoke(request, user, operation_id, *args, **kwargs)
        row = current.get()
        if row is not None:
            operation = gateway._operation(operation_id)
            require(operation["method"] == "GET" and not operation["write"], "事实求值调用了原写接口")
            row["native_gets"].append({"operation_id": operation_id, "method": "GET",
                                      "status": result.get("status"), "utc": _utc()})
        return result

    _write_observation(path, report)
    try:
        with patch.object(Worker, "tick", tick), patch.object(plans, "_evaluate_plan_facts", evaluate), \
                patch.object(gateway, "invoke", invoke):
            yield
    finally:
        _write_observation(path, report)


def extend_followup_provider(provider):
    """Extend only the unique explicit followup input; preserve other replies."""
    from provider import reply, tool
    import httpx

    original = provider.handle

    async def handle(request):
        body = json.loads(request.content)
        messages = body["messages"]
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1]) \
            if marker in messages[0]["content"] else {}
        texts = [message["content"] for message in messages if message["role"] == "user"]
        texts += [message["content"] for message in context.get("recent_messages", [])
                  if message["role"] == "user"]
        text = next((value for value in reversed(texts) if value.startswith(PREFIX)), None)
        if text is None:
            return await original(request)
        if (request.url.scheme, request.url.host, request.url.path) != (
                "https", "api.deepseek.com", "/chat/completions"):
            raise RuntimeError("Unexpected followup provider request")
        header, encoded = text.split("\n", 1)
        require(re.fullmatch(re.escape(PREFIX) + r"followup_[0-9a-f]{12}", header), "跟进输入必须唯一")
        source = json.loads(encoded)
        require(set(source) == {"case_ids", "task_ids", "assignee_id", "mode"}
                and len(source["case_ids"]) == len(source["task_ids"]) == 2
                and source["mode"] in {"logout", "revoke", "cancel", "expiry"}, "跟进输入来源不完整")
        calls = sum(message["role"] == "tool" for message in messages)
        background = bool(context.get("trigger", {}).get("background_is_not_new_employee_instruction"))
        stage = None
        if calls:
            message = reply("事项已准备，请核对。")
        elif not background:
            steps = [{"key": "assign_" + str(index), "title": "分派第" + str(index + 1) + "项接待",
                      "object_ref": {"type": "case", "id": case_id},
                      "form_ref": f"case:{case_id}:assign", "depends_on": ["assign_0"] if index else [],
                      "conditions": [{"type": "native_action_available", "object_ref": {"type": "case", "id": case_id},
                                      "action_key": "assign"}],
                      "completion_conditions": [{"type": "native_task_state", "task_id": source["task_ids"][index],
                                                  "expected_status": "done"}]}
                     for index, case_id in enumerate(source["case_ids"])]
            message = tool("save_work_plan", {"schema_version": 2, "goal": header, "steps": steps})
        else:
            run_id = context["trigger"]["run_id"]
            runs = _rows(provider.manifest["database_path"],
                         "SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))
            require(len(runs) == 1 and runs[0]["auth_kind"] == "grant" and runs[0]["status"] == "running",
                    "后台模型调用没有原真实Grant Run")
            run = runs[0]
            pending = _rows(provider.manifest["database_path"],
                "SELECT id FROM flow_cases WHERE id IN (?,?) AND state='unassigned' ORDER BY id",
                tuple(source["case_ids"]))
            require(pending, "真实接待都已分派，不应再次准备")
            case_id = pending[0]["id"]
            if source["mode"] == "logout" and case_id == source["case_ids"][1]:
                runtime = Path(provider.manifest["runtime_root"])
                stage_path = runtime / ("followup-logout-" + run_id + ".json")
                release_path = runtime / ("followup-logout-" + run_id + "-release.json")
                require(not stage_path.exists() and not release_path.exists(), "登出门控拒绝旧文件")
                stage = {"run_id": run_id, "session_id": run["session_id"], "grant_id": run["grant_id"],
                         "plan_id": run["plan_id"], "phase": "waiting_original_logout", "utc": _utc(),
                         "case_id": case_id, "returned_after_logout": False}
                _atomic_json(stage_path, stage)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and not release_path.is_file():
                    await asyncio.sleep(.025)
                require(release_path.is_file() and _load(release_path) == {"run_id": run_id, "action": "return_after_logout"},
                        "登出后未按原Run身份释放后继响应")
            if source["mode"] == "revoke":
                runtime = Path(provider.manifest["runtime_root"])
                stage_path = runtime / ("followup-revoke-" + run_id + ".json")
                release_path = runtime / ("followup-revoke-" + run_id + "-release.json")
                require(not stage_path.exists() and not release_path.exists(), "撤销门控拒绝旧文件")
                stage = {"run_id": run_id, "session_id": run["session_id"], "grant_id": run["grant_id"],
                         "plan_id": run["plan_id"], "phase": "waiting_prepare_response", "utc": _utc(),
                         "case_id": case_id, "returned_after_revoke": False}
                _atomic_json(stage_path, stage)
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline and not release_path.is_file():
                        await asyncio.sleep(.025)
                    require(release_path.is_file() and _load(release_path) == {"run_id": run_id, "action": "return_prepare_response"},
                            "原本人撤销后未按固定身份释放响应")
                    grants = _rows(provider.manifest["database_path"],
                        "SELECT status,stop_reason FROM business_assistant_followup_grants WHERE id=?", (run["grant_id"],))
                    require(len(grants) == 1 and grants[0]["status"] == "revoked"
                            and grants[0]["stop_reason"] == "employee_ended", "响应释放前原Grant尚未本人撤销")
                except BaseException as error:
                    stage.update(phase="aborted", error_type=type(error).__name__, ended_at=_utc())
                    _atomic_json(stage_path, stage)
                    raise
            message = tool("prepare_business_form", {"form_ref": f"case:{case_id}:assign",
                           "values": {"assignee_id": source["assignee_id"]}, "summary": "分派接待"})
        provider.counts["synthetic_requests"] += 1
        provider.counts["requests"].append({"tools": calls, "stream": bool(body.get("stream")), "background": background})
        finish = "tool_calls" if message.get("tool_calls") else "stop"
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        if body.get("stream"):
            packets = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": message.get("content") or ""},
                                      "finish_reason": None}]}]
            packets += [{"choices": [{"index": 0, "delta": {"tool_calls": [{"index": index, **call}]}, "finish_reason": None}]}
                        for index, call in enumerate(message.get("tool_calls", []))]
            packets.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage})
            response = httpx.Response(200, content="".join("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n"
                                                          for packet in packets) + "data: [DONE]\n\n",
                                      headers={"content-type": "text/event-stream"})
        else:
            response = httpx.Response(200, json={"choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage})
        if stage is not None and source["mode"] == "revoke":
            stage.update(phase="returned_after_revoke", returned_after_revoke=True, returned_at=_utc())
            _atomic_json(stage_path, stage)
        elif stage is not None:
            stage.update(phase="returned_after_logout", returned_after_logout=True, returned_at=_utc())
            _atomic_json(stage_path, stage)
        return response

    provider.handle = handle


def _observations(e, scope, worker=None):
    reports = [_read_observation(path) for path in Path(e.manifest["evidence_root"]).glob("followup-observations-*.json")]
    return {key: [row for report in reports for row in report[key] if row["scope"] == scope
                 and (key != "ticks" or worker is None or (row["pid"], row["worker_id"]) == worker)]
            for key in ("ticks", "fact_checks")}


async def _setup(e, context, credentials, mode):
    user = await e.login(context, credentials, role="admin", route="cases/lead")
    cases = []
    for index in range(2):
        if index:
            e.action("navigate", "返回原接待列表创建独立第二单")
            await e.page.goto(e.origin + "/#cases/lead", wait_until="domcontentloaded")
        await expect(e.page.locator("#main h1")).to_have_text("售前接待")
        await e.click('[data-act="newcase"][data-kind="lead"]', "原UI新建收口接待")
        await e.fill('#modal [name="customer_name"]', "合成收口" + mode + str(index) + uuid.uuid4().hex[:8])
        e.action("select", "原接待来源", value="展厅到店")
        await e.page.locator('#modal [name="source"]').select_option(label="展厅到店")
        created, _, _ = await native_submit(e, "/api/flow/cases", 201)
        source = facts(e, created["id"])
        require(source["case"]["state"] == "unassigned" and source["case"]["created_by"] == user["id"],
                "独立原UI接待来源错误")
        cases.append(source)
    e.action("navigate", "进入原助手准备本人两步事项")
    await e.page.goto(e.origin + "/#business-assistant", wait_until="domcontentloaded")
    await e.ready()
    await e.new_matter()
    source = {"case_ids": [row["case"]["id"] for row in cases],
              "task_ids": [task(row, "assign")["id"] for row in cases],
              "assignee_id": e.manifest["users"]["sales"]["id"], "mode": mode}
    before = e.business_snapshot("followup_" + mode + "_after_original_ui_sources")
    await e.send(PREFIX + "followup_" + uuid.uuid4().hex[:12] + "\n" + json.dumps(source, ensure_ascii=False))
    sid = e.latest_session
    plans = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE session_id=?", (sid,))
    require(len(plans) == 1, "真实事项不唯一")
    plan = plans[0]
    steps = e.db.rows("SELECT key,depends_on FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (plan["id"],))
    require(len(steps) == 2 and json.loads(steps[1]["depends_on"]) == [steps[0]["key"]], "真实事项未保存完整两步依赖")
    require(not e.db.proposals(user["id"], session_id=sid), "未开启Grant却后台准备了卡")
    e.business_unchanged(before, "followup_" + mode + "_before_grant_business_unchanged")
    scope = uuid.uuid4().hex
    _atomic_json(_control_path(e.manifest), {"scope": scope, "session_id": sid, "plan_id": plan["id"]})
    await expect(e.page.locator("#ba-current-plan .ba-plan-goal")).to_contain_text(plan["goal"], timeout=20000)
    await expect(e.page.locator('[data-baws-followup="enable"]')).to_be_visible(timeout=20000)
    await expect(e.page.locator('[data-baws-followup="enable"]')).to_be_enabled(timeout=20000)
    await e.followup_click("enable", "本人明确开启此事项跟进")
    await e.wait(lambda: e.db.rows("SELECT id FROM business_assistant_followup_grants WHERE plan_id=? AND status='active'", (plan["id"],)),
                 "原active Grant")
    return {"user": user, "source": source, "cases": cases, "session_id": sid, "plan_id": plan["id"], "scope": scope}


async def _first_card(e, state):
    cards = await e.wait(lambda: e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=?", (state["session_id"],)),
                         "真实首步唯一准备", timeout=45)
    require(len(cards) == 1 and cards[0]["status"] == "pending", "首步不是唯一真实pending卡")
    require(json.loads(cards[0]["payload"])["path_args"]["case_id"] == state["source"]["case_ids"][0], "首步串原单")
    runs = await e.wait(lambda: e.db.rows(
        "SELECT DISTINCT run_id FROM business_assistant_run_items WHERE proposal_id=? AND run_id IS NOT NULL",
        (cards[0]["id"],)), "原首卡与准备Run真实关联", timeout=20)
    require(len(runs) == 1, "真实首卡准备没有唯一原Run")
    terminal = await e.wait(lambda: (rows[0] if (rows := e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (runs[0]["run_id"],)))
                                   and rows[0]["status"] in {"succeeded", "failed", "cancelled"} else None),
                            "原首卡准备Run真实终态", timeout=35)
    require(terminal["status"] == "succeeded" and terminal["error_code"] is None
            and terminal["auth_kind"] == "grant" and terminal["plan_id"] == state["plan_id"], "原首卡Grant Run未成功完成")
    ticks = await e.wait(lambda: [row for row in _observations(e, state["scope"])["ticks"]
                                 if row["run_id"] == runs[0]["run_id"]], "实际首卡Run所属原worker已记录", timeout=25)
    workers = {(row["pid"], row["worker_id"]) for row in ticks}
    require(len(workers) == 1, "原首卡Run跨多个worker，不可累加20tick")
    state["worker"] = workers.pop()
    await e.click('[data-ba-action="refresh"]', "原首卡Run和tick完成后重读卡与会话busy")
    await e.ready()
    await expect(e.page.locator('[data-proposal="' + cards[0]["id"] + '"]')).to_be_visible()
    await expect(e.page.locator('[data-ba-action="cancel-proposal"][data-id="' + cards[0]["id"] + '"]')).to_be_enabled()
    e.observe("followup_original_worker_identity", {"pid": state["worker"][0], "worker_id": state["worker"][1],
                                                   "preparation_run_id": runs[0]["run_id"]})
    return cards[0]


async def _end_grant(e, state):
    await e.click('[data-ba-action="refresh"]', "本人结束前完整重读原事项与授权")
    await e.ready()
    await e.page.wait_for_function("id => { const view=globalThis.AssistantWorkspace?.snapshot?.();"
        "return view?.plan?.id===id && !view.planLoading && !view.followupPending"
        "&& !businessAssistantState.workLoading && !businessAssistantState.busy && !businessAssistantState.runId; }",
        arg=state["plan_id"], timeout=20000)
    await expect(e.page.locator('[data-baws-followup="revoke"]')).to_be_enabled()
    await e.click('[data-baws-followup="revoke"]', "本人结束事项第一次核对")
    await expect(e.page.locator('[data-baws-followup="revoke"]')).to_have_text("确认结束这件事")
    await e.followup_click("revoke", "本人确认结束事项")
    await e.wait(lambda: e.db.rows("SELECT id FROM business_assistant_followup_grants WHERE plan_id=? AND status='revoked'", (state["plan_id"],)),
                 "原Grant真实撤销")


async def followup_logout_wait(e, context, credentials):
    state = await _setup(e, context, credentials, "logout")
    card = await _first_card(e, state)
    nochange = e.business_snapshot("followup_before_twenty_unchanged_ticks")
    tick_start = len(_observations(e, state["scope"], state["worker"])["ticks"])
    cards_before = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=?", (state["session_id"],))
    await e.wait(lambda: len(_observations(e, state["scope"], state["worker"])["ticks"]) >= tick_start + 20, "20个实际原worker tick", timeout=130)
    observed = _observations(e, state["scope"], state["worker"])
    checks = [row for row in observed["fact_checks"] if row.get("returned")
              and any(call["method"] == "GET" and call["status"] == 200 for call in row["native_gets"])]
    require(checks, "20个空poll不能替代至少一次真实原GET事实核查")
    require(e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=?", (state["session_id"],)) == cards_before,
            "无变化等待重复准备或改写原卡")
    e.business_unchanged(nochange, "followup_after_twenty_unchanged_ticks")
    e.observe("followup_twenty_ticks_separate_from_fact_reads", {"no_change_ticks": len(observed["ticks"]) - tick_start,
              "real_fact_checks": len(checks), "native_get_count": sum(len(row["native_gets"]) for row in checks),
              "fact_check_scope": "this_real_grant_from_enable; separately_from_no_change_ticks",
              "counted_worker": {"pid": state["worker"][0], "worker_id": state["worker"][1]},
              "empty_tick_is_not_fact_check": True, "observation_files": "followup-observations-*.json"})
    async with e.page.expect_response(lambda response: urlsplit(response.url).path == "/api/auth/logout") as pending:
        await e.click('[data-act="logout"]', "本人已开Grant后真实退出")
    require((await pending.value).status == 200, "原登出未成功")
    await expect(e.page.locator('input[name="username"]')).to_be_visible()
    original_page = e.page
    secondary = await context.browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    try:
        await e.attach(secondary, await secondary.new_page())
        await e.login(secondary, credentials, role="admin")
        await e.ready()
        await e.click('[data-ba-action="history"]', "本人另一登录查看原事项")
        await expect(e.page.locator('[data-ba-action="session"][data-id="' + state["session_id"] + '"]')).to_be_visible(timeout=20000)
        await e.click('[data-ba-action="session"][data-id="' + state["session_id"] + '"]', "打开本人真实原会话")
        await e.ready()
        async with e.page.expect_response(lambda response: urlsplit(response.url).path.endswith("/confirm")) as pending:
            await e.click('[data-ba-action="confirm"][data-id="' + card["id"] + '"]', "本人另一登录页确认原首卡")
        require((await pending.value).status == 200, "原本人确认失败")
        await e.wait(lambda: e.db.case(state["source"]["case_ids"][0])["state"] == "contacting", "原首单实际分派")
        after_confirm = e.business_snapshot("followup_original_business_after_explicit_confirmation")
        # Leave every login closed while the same original Grant prepares its successor.
        async with e.page.expect_response(lambda response: urlsplit(response.url).path == "/api/auth/logout") as pending:
            await e.click('[data-act="logout"]', "确认后再次退出，等待后台查询和后继准备")
        require((await pending.value).status == 200, "确认后的真实登出失败")
        after_logout = e.business_snapshot("followup_business_after_confirmation_and_logout_audit")
        runtime = Path(e.manifest["runtime_root"])
        stage_path = await e.wait(lambda: next((path for path in runtime.glob("followup-logout-*.json")
                                  if "-release" not in path.name and _load(path)["session_id"] == state["session_id"]), None),
                                  "原后台后继Run准备边界", timeout=25)
        stage = _load(stage_path)
        require(stage["phase"] == "waiting_original_logout", "后继没有保持原登出边界")
        _atomic_json(runtime / ("followup-logout-" + stage["run_id"] + "-release.json"),
                     {"run_id": stage["run_id"], "action": "return_after_logout"})
        cards = await e.wait(lambda: (rows if len(rows := e.db.rows(
            "SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id",
            (state["session_id"],))) == 2 else None), "原Grant在全部登出后准备唯一后继", timeout=50)
        require([row["status"] for row in cards] == ["succeeded", "pending"], "后继自动确认或首卡结果不正确")
        require(_load(stage_path).get("returned_after_logout") is True, "后继响应没有真实在原登出后返回")
        require(json.loads(cards[1]["payload"])["path_args"]["case_id"] == state["source"]["case_ids"][1], "后继串原单")
        require(e.db.case(state["source"]["case_ids"][1])["state"] == "unassigned", "登出后后台自动提交第二原单")
        e.business_unchanged(after_logout, "followup_logout_successor_business_unchanged")
        mapped = e.db.rows("SELECT DISTINCT run_id,proposal_id FROM business_assistant_run_items WHERE proposal_id IN (?,?) AND run_id IS NOT NULL",
                           (cards[0]["id"], cards[1]["id"]))
        require(len(mapped) == 2 and len({row["run_id"] for row in mapped}) == 2
                and {row["proposal_id"] for row in mapped} == {row["id"] for row in cards}, "两原卡未分别对应唯一准备Run")
        await e.wait(lambda: all(e.db.rows("SELECT status FROM business_assistant_runs WHERE id=?", (row["run_id"],))[0]["status"]
                                in {"succeeded", "failed", "cancelled"} for row in mapped), "原后继准备Run真实终态", timeout=30)
        runs = e.db.rows("SELECT id,auth_kind,status,grant_id,error_code FROM business_assistant_runs WHERE session_id=? ORDER BY created_at,id",
                         (state["session_id"],))
        granted_runs = [row for row in runs if row["auth_kind"] == "grant"]
        require(len(granted_runs) == 2 and {row["id"] for row in granted_runs} == {row["run_id"] for row in mapped}
                and all(row["status"] == "succeeded" and row["error_code"] is None for row in granted_runs),
                "原两步存在额外Grant Run或准备未成功，不能把卡commit当Run终态")
        await e.wait(lambda: e.db.rows("SELECT id FROM business_assistant_notifications WHERE session_id=? AND proposal_id=? AND kind='proposal_ready'",
                                       (state["session_id"], cards[1]["id"])), "原后继proposal_ready通知实际耐久", timeout=35)
        notices = e.db.rows("SELECT source_key,kind,status,proposal_id FROM business_assistant_notifications WHERE session_id=? ORDER BY id",
                            (state["session_id"],))
        require(len({(row["source_key"], row["kind"]) for row in notices}) == len(notices)
                and any(row["proposal_id"] == cards[1]["id"] for row in notices), "后继真实通知丢失或重复")
        e.observe("followup_logout_complete", {"session_id": state["session_id"], "plan_id": state["plan_id"],
                  "proposal_ids": [row["id"] for row in cards], "runs": runs, "notices": notices,
                  "explicit_confirmation_business_hash": after_confirm["sha256"], "all_logins_closed": True})
        await e.login(secondary, credentials, role="admin")
        await e.ready()
        await e.click('[data-ba-action="history"]', "本人重新登录核对仍待确认后继")
        await expect(e.page.locator('[data-ba-action="session"][data-id="' + state["session_id"] + '"]')).to_be_visible(timeout=20000)
        await e.click('[data-ba-action="session"][data-id="' + state["session_id"] + '"]', "原会话后继展示")
        await e.ready()
        await e.snapshot("followup-logout-successor-pending")
        await _end_grant(e, state)
    finally:
        await secondary.close()
        e.page = original_page


async def followup_revoke_inflight(e, context, credentials):
    state = await _setup(e, context, credentials, "revoke")
    runtime = Path(e.manifest["runtime_root"])
    stage_path = await e.wait(lambda: next((path for path in runtime.glob("followup-revoke-*.json")
                                          if "-release" not in path.name and _load(path)["session_id"] == state["session_id"]), None),
                             "真实Grant Run已到准备响应边界", timeout=35)
    stage = _load(stage_path)
    require(stage["phase"] == "waiting_prepare_response", "准备响应边界已中断")
    before = e.business_snapshot("followup_revoke_before_explicit_ui_end")
    await _end_grant(e, state)
    _atomic_json(runtime / ("followup-revoke-" + stage["run_id"] + "-release.json"),
                 {"run_id": stage["run_id"], "action": "return_prepare_response"})
    await e.wait(lambda: _load(stage_path).get("returned_after_revoke"), "合成prepare响应真实在撤销后返回", timeout=10)
    terminal = await e.wait(lambda: (rows[0] if (rows := e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (stage["run_id"],)))
                                    and rows[0]["status"] in {"cancelled", "failed"} else None), "原Grant Run停止", timeout=30)
    require(not e.db.proposals(state["user"]["id"], session_id=state["session_id"]), "撤销后迟到准备新增卡")
    require(not e.db.rows("SELECT id FROM business_assistant_work_items WHERE session_id=? AND item_kind='prepare'", (state["session_id"],)),
            "撤销后迟到准备写入WorkItem")
    e.business_unchanged(before, "followup_revoke_late_prepare_business_unchanged")
    e.observe("followup_revoke_late_response", {"stage": _load(stage_path), "run_id": terminal["id"], "status": terminal["status"],
                                               "error_code": terminal["error_code"], "new_preparations": 0})
    await e.snapshot("followup-revoked-no-preparation")


async def followup_cancel_card(e, context, credentials):
    state = await _setup(e, context, credentials, "cancel")
    card = await _first_card(e, state)
    before = e.business_snapshot("followup_pending_before_original_cancel")
    async with e.page.expect_response(lambda response: urlsplit(response.url).path.endswith("/cancel")) as pending:
        await e.click('[data-ba-action="cancel-proposal"][data-id="' + card["id"] + '"]', "本人原UI取消pending首卡")
    require((await pending.value).status == 200, "原卡取消未成功")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_proposals WHERE id=?", (card["id"],))[0]["status"] == "cancelled", "原卡真实取消")
    tick_start = len(_observations(e, state["scope"], state["worker"])["ticks"])
    await e.wait(lambda: len(_observations(e, state["scope"], state["worker"])["ticks"]) >= tick_start + 20, "取消后的20实际worker tick", timeout=130)
    cards = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=?", (state["session_id"],))
    require(len(cards) == 1 and cards[0]["status"] == "cancelled", "取消后自动补卡或准备依赖后继")
    steps = e.db.rows("SELECT key,status,proposal_id FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (state["plan_id"],))
    require(len(steps) == 2 and steps[0]["status"] == "cancelled" and steps[1]["proposal_id"] is None
            and steps[1]["status"] != "completed", "取消原首卡未阻塞原依赖")
    e.business_unchanged(before, "followup_cancel_original_business_unchanged")
    e.observe("followup_pending_cancel_dependency", {"card_id": card["id"], "steps": steps, "automatic_replacements": 0})
    await e.snapshot("followup-original-card-cancelled")
    await _end_grant(e, state)


async def followup_natural_expiry(e, context, credentials):
    state = await _setup(e, context, credentials, "expiry")
    card = await _first_card(e, state)
    deadline = datetime.fromisoformat(card["expires_at"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    created = datetime.fromisoformat(card["created_at"].replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    require(1799 <= (deadline - created).total_seconds() <= 1801, "必须使用原30分钟卡片deadline")
    before = e.business_snapshot("followup_expiry_original_business_before_natural_wait")
    e.action("natural_deadline_wait", "等待原30分钟截止，不改时间/状态", expires_at=deadline.isoformat())
    while datetime.now(timezone.utc) <= deadline:
        await asyncio.sleep(min(5, max(.05, (deadline - datetime.now(timezone.utc)).total_seconds())))
    await e.click('[data-ba-action="refresh"]', "真实截止后读取原卡")
    await e.ready()
    await e.click('[data-ba-action="queue-filter"][data-filter="attention"]', "查看原过期卡")
    ui = e.page.locator('section.ba-proposal[data-proposal="' + card["id"] + '"]')
    await expect(ui).to_have_count(1)
    await expect(ui).to_be_visible()
    await expect(ui).to_contain_text("已过期")
    await expect(ui).to_contain_text("不能继续提交")
    await expect(e.page.locator('button[data-ba-action="confirm"][data-id="' + card["id"] + '"]')).to_have_count(0)
    await expect(e.page.locator('[data-ba-confirm-bar="' + card["id"] + '"]')).to_have_count(0)
    cookies = {cookie["name"]: cookie["value"] for cookie in await context.cookies()}
    e.action("supplemental_http_rejection", "原过期confirm拒绝，UI确认入口已隐藏", native_ui=False)
    response = await context.request.post(e.origin + "/api/business-assistant/sessions/" + state["session_id"]
        + "/proposals/" + card["id"] + "/confirm",
        headers={"x-csrf-token": cookies["dealer_csrf"], "x-store-id": str(card["store_id"])}, data={"digest": card["digest"]})
    require(response.status == 409, "原过期卡确认没有返回409拒绝")
    tick_start = len(_observations(e, state["scope"], state["worker"])["ticks"])
    await e.wait(lambda: len(_observations(e, state["scope"], state["worker"])["ticks"]) >= tick_start + 3, "自然过期后的原worker tick", timeout=25)
    cards = e.db.rows("SELECT id,status,expires_at FROM business_assistant_proposals WHERE session_id=?", (state["session_id"],))
    require(len(cards) == 1 and cards[0]["id"] == card["id"] and cards[0]["status"] == "expired", "自然过期新增替代卡或未落原expired")
    steps = e.db.rows("SELECT key,status,wait_reason,proposal_id FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (state["plan_id"],))
    require(steps[0]["status"] == "waiting" and steps[0]["wait_reason"] == "expired"
            and steps[1]["proposal_id"] is None and steps[1]["status"] != "completed", "自然过期未阻塞依赖")
    e.business_unchanged(before, "followup_natural_expiry_original_business_unchanged")
    e.observe("followup_natural_expiry", {"created_at": created.isoformat(), "expires_at": deadline.isoformat(),
              "observed_at": _utc(), "confirmation_status": response.status,
              "ui_confirmation_hidden": True, "ui_submission_unavailable": True,
              "card_ids": [row["id"] for row in cards], "steps": steps, "automatic_replacements": 0})
    await e.snapshot("followup-natural-thirty-minute-expiry")
    await _end_grant(e, state)


FOLLOWUP_CLOSEOUT_SCENARIOS = (
    ("runtime-followup-grant-logout-twenty-ticks", followup_logout_wait, 240),
    ("runtime-followup-revoke-before-prepare-response", followup_revoke_inflight, 120),
    ("runtime-pending-card-cancel-blocks-dependent", followup_cancel_card, 240),
)
FOLLOWUP_LONG_SCENARIOS = (("runtime-pending-card-natural-thirty-minute-expiry", followup_natural_expiry, 1950),)
