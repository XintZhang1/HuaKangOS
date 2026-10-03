"""Real history-window rollover, fresh facts and natural proof TTL checks."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx
from playwright.async_api import expect

from runtime_faults import _atomic_json, _digest, _load, _rows, _utc
from runtime_followup_closeout import PREFIX, _end_grant, _first_card, _setup
from sales_business import action_form, employee_choice, facts, native_submit, require


def _response(provider, body, message, calls, background):
    provider.counts["synthetic_requests"] += 1
    provider.counts["requests"].append({"tools": calls, "stream": bool(body.get("stream")), "background": bool(background)})
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    if not body.get("stream"):
        return httpx.Response(200, json={"choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage})
    packets = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": message.get("content") or ""}, "finish_reason": None}]}]
    packets += [{"choices": [{"index": 0, "delta": {"tool_calls": [{"index": index, **call}]}, "finish_reason": None}]}
                for index, call in enumerate(message.get("tool_calls", []))]
    packets.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage})
    return httpx.Response(200, content="".join("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n"
                                             for packet in packets) + "data: [DONE]\n\n",
                          headers={"content-type": "text/event-stream"})


def extend_context_provider(provider):
    """Install after extend_followup_provider; only fixed named inputs change."""
    from provider import reply, tool
    original = provider.handle

    async def handle(request):
        if (request.url.scheme, request.url.host, request.url.path) != (
                "https", "api.deepseek.com", "/chat/completions"):
            raise RuntimeError("Unexpected context provider request")
        body = json.loads(request.content)
        messages = body["messages"]
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1]) if marker in messages[0]["content"] else {}
        current = next((message["content"] for message in reversed(messages) if message["role"] == "user"), "")
        calls = sum(message["role"] == "tool" for message in messages)
        background = context.get("trigger", {}).get("background_is_not_new_employee_instruction")
        if current.startswith("浏览器摘要片段 ") or current.startswith("浏览器摘要核对 "):
            require(re.match(r"浏览器摘要(?:片段|核对) [0-9a-f-]{36}(?: \d+)?\n", current), "摘要输入必须绑定当前真实会话")
            require(current.split("\n", 1)[0].split(" ")[1] == context["principal"]["session_id"], "摘要输入串会话")
            require(not calls and not background, "摘要记录不执行业务工具或后台目标")
            recent = context.get("recent_messages", [])
            used_chars = len(current) + sum(len(row["content"]) for row in recent)
            through = context.get("source_snapshots", [])
            latest_older = (_rows(provider.manifest["database_path"],
                "SELECT id,length(content) AS chars FROM business_assistant_messages WHERE session_id=? AND id=?",
                (context["principal"]["session_id"], through[0]["through_message_id"])) if through else [])
            window_count = len(recent) + 1
            observation = {"run_id": context["trigger"]["run_id"], "pid": os.getpid(), "utc": _utc(),
                           "recent_message_count": len(recent), "window_message_count": window_count,
                           "window_used_chars": used_chars, "has_real_source_snapshot": bool(through),
                           "adding_last_excluded_would_exceed_messages": bool(latest_older) and window_count + 1 > 30,
                           "adding_last_excluded_would_exceed_chars": bool(latest_older) and used_chars + latest_older[0]["chars"] > 24000,
                           "fresh_objects": [{key: row.get(key) for key in ("ref", "native_version", "state")}
                                             for row in context.get("fresh_facts", {}).get("objects", [])],
                           "snapshot_message_ids": [row.get("through_message_id") for row in context.get("source_snapshots", [])]}
            path = Path(provider.manifest["evidence_root"]) / ("context-native-facts-" + context["trigger"]["run_id"] + ".json")
            _atomic_json(path, observation)
            return _response(provider, body, reply("已记录；业务状态仍以本轮原单查询为准。"), calls, background)
        texts = [message["content"] for message in messages if message["role"] == "user"]
        texts += [message["content"] for message in context.get("recent_messages", []) if message["role"] == "user"]
        text = next((value for value in reversed(texts) if value.startswith(PREFIX)), None)
        if text is None or json.loads(text.split("\n", 1)[1]).get("mode") != "proof":
            return await original(request)
        source = json.loads(text.split("\n", 1)[1])
        require(len(source["case_ids"]) == len(source["task_ids"]) == 2, "TTL核查必须使用两真实原单")
        if calls:
            message = reply("事项已准备，请核对。")
        elif not background:
            steps = [{"key": "assign_" + str(index), "title": "分派第" + str(index + 1) + "项接待",
                      "object_ref": {"type": "case", "id": ident}, "form_ref": f"case:{ident}:assign",
                      "depends_on": ["assign_0"] if index else [],
                      "conditions": [{"type": "native_action_available", "object_ref": {"type": "case", "id": ident}, "action_key": "assign"}],
                      "completion_conditions": [{"type": "native_task_state", "task_id": source["task_ids"][index], "expected_status": "done"}]}
                     for index, ident in enumerate(source["case_ids"])]
            message = tool("save_work_plan", {"schema_version": 2, "goal": text.split("\n", 1)[0], "steps": steps})
        else:
            runs = _rows(provider.manifest["database_path"],
                         "SELECT auth_kind,status FROM business_assistant_runs WHERE id=?", (context["trigger"]["run_id"],))
            require(len(runs) == 1 and runs[0]["auth_kind"] == "grant" and runs[0]["status"] == "running",
                    "TTL恢复准备必须属于原正在运行的Grant Run")
            waiting = _rows(provider.manifest["database_path"], "SELECT id FROM flow_cases WHERE id IN (?,?) AND state='unassigned' ORDER BY id",
                            tuple(source["case_ids"]))
            require(waiting, "TTL恢复没有真实待分派原单")
            message = tool("prepare_business_form", {"form_ref": f"case:{waiting[0]['id']}:assign",
                           "values": {"assignee_id": source["assignee_id"]}, "summary": "分派接待"})
        return _response(provider, body, message, calls, background)

    provider.handle = handle


@contextmanager
def observe_context_proof(manifest):
    """Let an actual in-memory FollowupCheck age past its unchanged 60s TTL."""
    require(manifest.get("synthetic_data_only") is True, "TTL装置只允许外部合成实例")
    from unittest.mock import patch
    from app import assistant_runtime_plans as plans

    original_resolve, original_state = plans.resolve_followup_check, plans._followup_state
    held = {}

    async def resolve(db, principal, *args, **kwargs):
        check = await original_resolve(db, principal, *args, **kwargs)
        messages = _rows(manifest["database_path"], "SELECT content FROM business_assistant_messages WHERE session_id=? AND role='user' ORDER BY id",
                         (principal.session_id,))
        match = next((row["content"] for row in messages if row["content"].startswith(PREFIX)
                      and json.loads(row["content"].split("\n", 1)[1]).get("mode") == "proof"), None)
        path = Path(manifest["runtime_root"]) / ("followup-proof-" + principal.session_id + ".json")
        if match is None or path.exists():
            return check
        issued = plans._followup_checks.get(check)["issued_at"]
        stage = {"pid": os.getpid(), "session_id": principal.session_id, "plan_id": principal.plan_id,
                 "grant_id": principal.grant_id, "phase": "issued_waiting_real_ttl", "issued_observed_at": _utc(),
                 "ttl_seconds": plans._CONDITION_PROOF_SECONDS, "hold_seconds": 61, "expired_rejected": False}
        require(stage["ttl_seconds"] == 60 and check.ready, "必须是真实可准备FollowupCheck及原60sTTL")
        held[id(check)] = (check, path, stage, issued)
        _atomic_json(path, stage)
        await asyncio.sleep(61)
        stage.update(phase="returning_old_proof", returned_at=_utc(), elapsed_since_issue=time.monotonic() - issued)
        _atomic_json(path, stage)
        return check

    def state(db, check):
        try:
            return original_state(db, check)
        except Exception as error:
            observed = held.get(id(check))
            if observed is not None and observed[0] is check:
                _, path, stage, issued = observed
                stage.update(phase="expired_rejected", expired_rejected=True, rejection_status=getattr(error, "status_code", None),
                             elapsed_since_issue=time.monotonic() - issued, rejected_at=_utc(),
                             cards_at_rejection=len(_rows(manifest["database_path"],
                                 "SELECT id FROM business_assistant_proposals WHERE session_id=?", (stage["session_id"],))),
                             grant_runs_at_rejection=len(_rows(manifest["database_path"],
                                 "SELECT id FROM business_assistant_runs WHERE plan_id=? AND auth_kind='grant'", (stage["plan_id"],))))
                _atomic_json(path, stage)
            raise

    with patch.object(plans, "resolve_followup_check", resolve), patch.object(plans, "_followup_state", state):
        yield


async def context_proof_natural_ttl(e, context, credentials):
    state = await _setup(e, context, credentials, "proof")
    before = e.business_snapshot("ttl_original_business_after_real_plan_and_grant")
    path = Path(e.manifest["runtime_root"]) / ("followup-proof-" + state["session_id"] + ".json")
    await e.wait(lambda: path.is_file(), "原事实求值已签发60s凭据", timeout=30)
    initial = _load(path)
    require(initial["phase"] == "issued_waiting_real_ttl" and initial["ttl_seconds"] == 60, "原TTL凭据等待窗口不正确")
    require(not e.db.proposals(state["user"]["id"], session_id=state["session_id"]), "未消费凭据却准备了卡")
    await e.wait(lambda: _load(path).get("expired_rejected"), "原61秒后消费真正拒绝", timeout=80)
    rejected = _load(path)
    require(rejected["rejection_status"] == 409 and rejected["elapsed_since_issue"] > 60
            and rejected["cards_at_rejection"] == rejected["grant_runs_at_rejection"] == 0, "过期旧依据未真实409拒绝或已落准备")
    card = await _first_card(e, state)
    require(len(e.db.proposals(state["user"]["id"], session_id=state["session_id"])) == 1, "新原事实核查恢复重复准备")
    e.business_unchanged(before, "ttl_old_proof_rejected_fresh_proof_unique_card_business_unchanged")
    e.observe("natural_followup_proof_ttl", {**rejected, "fresh_proposal_id": card["id"], "clock_or_issued_at_modified": False})
    await e.snapshot("followup-old-proof-expired-fresh-unique-card")
    await _end_grant(e, state)


async def context_summary_fresh_fact(e, context, credentials):
    state = await _setup(e, context, credentials, "cancel")
    card = await _first_card(e, state)
    await e.followup_click("pause", "原UI暂停Grant，单独验证历史上下文")
    before = e.business_snapshot("summary_original_business_before_real_message_window")
    plan_before = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE id=?", (state["plan_id"],))[0]
    semantic_fields = ("key", "title", "depends_on", "proposal_id", "workflow_id", "wait_for",
                       "object_ref", "form_ref", "conditions", "completion_conditions", "required", "intent_version")
    step_semantics = [{key: row[key] for key in semantic_fields} for row in e.db.rows(
        "SELECT * FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (state["plan_id"],))]
    cards_before = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY id", (state["session_id"],))
    run_ids, windows = [], []
    for index in range(31):
        text = "浏览器摘要片段 " + state["session_id"] + " " + str(index) + "\n" + (
            "合成员工资料用于历史窗口核查。接待是否分派仍必须查原单，不依据这段话办理或判定业务完成。" * (22 if index < 16 else 42))
        await e.send(text)
        require(e.latest_session == state["session_id"], "原31轮输入串会话")
        run = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
        require(run["status"] == "succeeded" and run["error_code"] is None and run["auth_kind"] == "login"
                and run["trigger_kind"] == "user", "真实摘要轮次失败或不是本人输入Run")
        require(not e.db.rows("SELECT id FROM business_assistant_run_items WHERE run_id=? AND kind IN ('tool','batch_row')", (run["id"],)),
                "摘要资料轮次调用了工具")
        run_ids.append(run["id"])
        current_steps = e.db.rows("SELECT * FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (state["plan_id"],))
        require(all(set(semantic_fields) <= row.keys() for row in current_steps)
                and [{key: row[key] for key in semantic_fields} for row in current_steps] == step_semantics,
                "真实摘要轮次改变当前schema的object_ref/form_ref或完整步骤语义")
        windows.append(_load(Path(e.manifest["evidence_root"]) / ("context-native-facts-" + run["id"] + ".json")))
    messages = e.db.rows("SELECT id,role,length(content) AS chars FROM business_assistant_messages WHERE session_id=? ORDER BY id",
                         (state["session_id"],))
    require(len(messages) > 30 and sum(row["chars"] for row in messages) > 24000, "没有真实跨过30消息与24000字符窗口")
    message_boundaries = [row for row in windows if row["has_real_source_snapshot"]
                          and row["adding_last_excluded_would_exceed_messages"] and not row["adding_last_excluded_would_exceed_chars"]]
    char_boundaries = [row for row in windows if row["has_real_source_snapshot"]
                       and row["adding_last_excluded_would_exceed_chars"] and not row["adding_last_excluded_would_exceed_messages"]]
    require(message_boundaries and char_boundaries, "必须分别实际触发30消息与24000字符窗口，不能只统计会话总字数")
    summary_messages = e.db.rows("SELECT id,request_id FROM business_assistant_messages WHERE session_id=? AND role='user' AND content LIKE ? ORDER BY id",
                                (state["session_id"], "浏览器摘要片段 " + state["session_id"] + " %"))
    summary_runs = e.db.rows("SELECT id,request_id FROM business_assistant_runs WHERE session_id=? AND trigger_kind='user' ORDER BY id", (state["session_id"],))
    require(len(run_ids) == len(set(run_ids)) == len(summary_messages) == 31
            and {row["request_id"] for row in summary_runs if row["id"] in set(run_ids)} == {row["request_id"] for row in summary_messages},
            "31轮没有唯一对应真实user消息和Run")
    plan_after = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE id=?", (state["plan_id"],))[0]
    require(all(plan_after[key] == plan_before[key] for key in
                ("id", "owner_id", "store_id", "session_id", "request_id", "goal", "goal_version", "engine_version", "status"))
            and len(e.db.rows("SELECT id FROM business_assistant_work_plans WHERE session_id=?", (state["session_id"],))) == 1,
            "摘要改变目标/目标版本或新增计划")
    require([{key: row[key] for key in semantic_fields} for row in e.db.rows(
        "SELECT * FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (state["plan_id"],))] == step_semantics,
            "摘要改变完整原步骤语义")
    require(e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY id", (state["session_id"],)) == cards_before,
            "31轮摘要新增或改写原卡")
    snapshots = e.db.rows("SELECT * FROM business_assistant_context_snapshots WHERE session_id=? ORDER BY created_at,id", (state["session_id"],))
    require(snapshots and all(row["through_message_id"] in {message["id"] for message in messages} for row in snapshots),
            "没有真实有来源的append-only摘要")
    old_hashes = {row["id"]: _digest(row) for row in snapshots}
    e.business_unchanged(before, "summary_real_history_messages_original_business_unchanged")
    case_id = state["source"]["case_ids"][0]
    old_fact = facts(e, case_id)
    e.action("navigate", "原业务UI改变摘要所关联的首单事实")
    await e.page.goto(e.origin + "/#case/" + str(case_id), wait_until="domcontentloaded")
    await expect(e.page.locator("#main h1")).to_have_text(old_fact["case"]["title"])
    await action_form(e, "assign", "分派接待")
    await employee_choice(e, e.manifest["users"]["sales"])
    await native_submit(e, f"/api/flow/cases/{case_id}/actions/assign", 200, case_id=case_id)
    current_fact = facts(e, case_id)
    require(current_fact["case"]["state"] == "contacting" and current_fact["case"]["version"] > old_fact["case"]["version"],
            "原UI没有真实改变原单状态及版本")
    after_commit = e.business_snapshot("summary_original_business_after_native_fact_change")
    e.action("navigate", "返回本人原会话用新上下文读取当前事实")
    await e.page.goto(e.origin + "/#business-assistant", wait_until="domcontentloaded")
    await e.ready()
    await e.click('[data-ba-action="history"]', "打开原长会话")
    await e.click('[data-ba-action="session"][data-id="' + state["session_id"] + '"]', "继续本人同一长会话")
    await e.ready()
    await e.send("浏览器摘要核对 " + state["session_id"] + "\n核对原单当前事实，旧员工资料不能代替新状态。")
    fact_run = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    require(fact_run["status"] == "succeeded" and fact_run["error_code"] is None
            and not e.db.rows("SELECT id FROM business_assistant_run_items WHERE run_id=? AND kind IN ('tool','batch_row')", (fact_run["id"],)),
            "原单变化后的真实查询Run失败或调用写准备工具")
    observation = _load(Path(e.manifest["evidence_root"]) / ("context-native-facts-" + e.latest_run + ".json"))
    matching = [row for row in observation["fresh_objects"] if row["ref"] == {"type": "case", "id": case_id}]
    require(len(matching) == 1 and matching[0]["state"] == current_fact["case"]["state"]
            and matching[0]["native_version"] == current_fact["case"]["version"], "长摘要后新模型上下文使用旧状态或旧版本")
    current_snapshots = e.db.rows("SELECT * FROM business_assistant_context_snapshots WHERE session_id=? ORDER BY created_at,id", (state["session_id"],))
    require(all(_digest(row) == old_hashes[row["id"]] for row in current_snapshots if row["id"] in old_hashes)
            and len({row["id"] for row in current_snapshots} & old_hashes.keys()) == len(old_hashes), "旧摘要被覆盖或丢失")
    e.business_unchanged(after_commit, "summary_fresh_context_after_original_commit_business_unchanged")
    e.observe("summary_native_fact_rollover", {"session_id": state["session_id"], "real_messages": len(messages),
              "real_chars": sum(row["chars"] for row in messages), "old_snapshot_count": len(snapshots),
              "summary_user_run_ids": run_ids, "query_run_id": fact_run["id"], "all_summary_and_query_runs_succeeded": True,
              "tools_new_cards_or_plans": 0, "original_plan_and_step_semantics_preserved": True,
              "actual_message_window_boundaries": message_boundaries, "actual_char_window_boundaries": char_boundaries,
              "old_snapshot_hashes": old_hashes, "new_context": observation, "case_id": case_id,
              "old_native_version": old_fact["case"]["version"], "current_native_version": current_fact["case"]["version"]})
    await e.snapshot("long-summary-current-real-case-fact")
    await _end_grant(e, state)


CONTEXT_CLOSEOUT_SCENARIOS = (
    ("runtime-followup-proof-natural-sixty-second-expiry", context_proof_natural_ttl, 210),
    ("runtime-real-summary-window-fresh-business-fact", context_summary_fresh_fact, 360),
)
