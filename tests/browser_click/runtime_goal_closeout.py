"""Original UI structural goal edits stop old scope and require own resume."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import expect

from runtime_context_closeout import _response
from runtime_faults import _atomic_json, _digest, _load, _rows, _utc
from runtime_followup_closeout import _end_grant, _first_card, _observations, _setup
from sales_business import require


GOAL_PREFIX = "浏览器修改原事项目标 "
STEP_FIELDS = ("key", "title", "depends_on", "proposal_id", "workflow_id", "wait_for",
               "object_ref", "form_ref", "conditions", "completion_conditions", "required")
JSON_FIELDS = {"depends_on", "object_ref", "conditions", "completion_conditions"}


def extend_goal_provider(provider):
    """Wrap the context provider; only an explicit current goal-edit input acts."""
    from provider import reply, tool
    original = provider.handle

    async def handle(request):
        body = json.loads(request.content)
        messages = body["messages"]
        current = next((message["content"] for message in reversed(messages) if message["role"] == "user"), "")
        if not current.startswith(GOAL_PREFIX):
            return await original(request)
        if (request.url.scheme, request.url.host, request.url.path) != ("https", "api.deepseek.com", "/chat/completions"):
            raise RuntimeError("Unexpected goal provider request")
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1])
        source = json.loads(current.split("\n", 1)[1])
        calls = sum(message["role"] == "tool" for message in messages)
        require(context["principal"]["session_id"] == source["session_id"]
                and context["goal_constraints"]["plan_id"] == source["plan_id"], "原UI修改未绑定本人当前真实计划")
        require(not context["trigger"]["background_is_not_new_employee_instruction"], "后台目标不能作为新修改指令")
        if calls:
            return _response(provider, body, reply("新目标已保存，请核对后恢复跟进。"), calls, False)
        plans = [plan for plan in context["plans_cards_tasks"]["plans"] if plan["id"] == source["plan_id"]]
        require(len(plans) == 1 and plans[0]["goal"] == source["old_goal"], "修改输入与真实当前目标不一致")
        rows = _rows(provider.manifest["database_path"],
                     "SELECT * FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (source["plan_id"],))
        steps = [{key: json.loads(row[key]) if key in JSON_FIELDS and row[key] is not None else row[key]
                  for key in STEP_FIELDS} for row in rows]
        for step in steps:
            step["required"] = bool(step["required"])
        require(len(steps) == 2, "必须保留原完整两步依赖")
        args = {"schema_version": 2, "plan_id": source["plan_id"], "expected_version": plans[0]["version"],
                "goal": source["new_goal"], "steps": steps}
        _atomic_json(Path(provider.manifest["evidence_root"]) / ("goal-input-" + context["trigger"]["run_id"] + ".json"),
                     {"run_id": context["trigger"]["run_id"], "session_id": source["session_id"],
                      "plan_id": source["plan_id"], "goal_version": context["goal_constraints"]["goal_version"],
                      "expected_version": args["expected_version"], "steps_digest": _digest(steps), "utc": _utc()})
        return _response(provider, body, tool("save_work_plan", args), calls, False)

    provider.handle = handle


def _history_rows(e, sid):
    return {table: e.db.rows("SELECT * FROM " + table + " WHERE session_id=? ORDER BY id", (sid,))
            for table in ("business_assistant_proposals", "business_assistant_work_items",
                          "business_assistant_messages", "business_assistant_context_snapshots")}


async def structural_goal_own_resume(e, context, credentials):
    state = await _setup(e, context, credentials, "cancel")
    card = await _first_card(e, state)
    await expect(e.page.locator('[data-baws-followup="pause"]')).to_be_enabled()
    original_plan = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE id=?", (state["plan_id"],))[0]
    original_grants = e.db.rows("SELECT * FROM business_assistant_followup_grants WHERE plan_id=?", (state["plan_id"],))
    require(len(original_grants) == 1 and original_grants[0]["status"] == "active", "原活跃Grant不唯一")
    original_grant = original_grants[0]
    history = _history_rows(e, state["session_id"])
    before = e.business_snapshot("goal_before_original_ui_structural_edit")
    new_goal = original_plan["goal"] + "；保持原接待及依赖，核对新目标后继续"
    source = {"session_id": state["session_id"], "plan_id": state["plan_id"],
              "old_goal": original_plan["goal"], "new_goal": new_goal}
    edit_text = GOAL_PREFIX + state["plan_id"] + "\n" + json.dumps(source, ensure_ascii=False)
    async with e.page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path ==
                                      "/api/business-assistant/sessions/" + state["session_id"] + "/runs") as pending:
        await e.send(edit_text)
    submitted = await pending.value
    payload = submitted.request.post_data_json
    require(submitted.status == 202 and payload["plan_id"] == state["plan_id"] and payload["content"] == edit_text,
            "原UI POST未真实携当前计划和本人新目标")
    edited_run = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    require(payload["request_id"] == edited_run["request_id"], "原UI请求号与在途修改Run不一致")
    saved_items = e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id=? AND kind='tool'", (edited_run["id"],))
    require(len(saved_items) == 1 and saved_items[0]["tool_name"] == "save_work_plan"
            and saved_items[0]["status"] == "succeeded" and saved_items[0]["error_code"] is None,
            "原goal修改未实际成功执行save_work_plan工具")
    updated_events = e.db.rows("SELECT * FROM business_assistant_run_events WHERE run_id=? AND type='plan.updated'", (edited_run["id"],))
    require(len(updated_events) == 1 and json.loads(updated_events[0]["payload"])["plan_id"] == state["plan_id"],
            "原goal修改未追加真实同Plan的plan.updated事件")
    changed = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE id=?", (state["plan_id"],))[0]
    require(len(e.db.rows("SELECT id FROM business_assistant_work_plans WHERE session_id=?", (state["session_id"],))) == 1
            and changed["goal"] == new_goal and changed["goal_version"] == original_plan["goal_version"] + 1,
            "原UI未修改同一计划goal_version，不能以新Plan代替")
    require(edited_run["plan_id"] == state["plan_id"] and edited_run["goal_version"] == original_plan["goal_version"]
            and edited_run["stop_requested"] and edited_run["status"] == "cancelled", "在途修改Run未保留旧目标范围并停止")
    paused = e.db.rows("SELECT * FROM business_assistant_followup_grants WHERE id=?", (original_grant["id"],))[0]
    require(paused["status"] == "paused" and paused["stop_reason"] == "goal_changed"
            and paused["goal_version"] == original_plan["goal_version"], "旧Grant未因真实目标改变暂停")
    current_history = _history_rows(e, state["session_id"])
    for table, rows in history.items():
        current = {row["id"]: row for row in current_history[table]}
        require(all(row["id"] in current and _digest(current[row["id"]]) == _digest(row) for row in rows),
                "目标修改覆盖或丢失原历史：" + table)
    require(not e.db.rows("SELECT id FROM business_assistant_runs WHERE plan_id=? AND goal_version=? AND status IN ('queued','running')",
                         (state["plan_id"], original_plan["goal_version"])), "旧goal仍有继续运行或排队Run")
    e.business_unchanged(before, "goal_saved_old_scope_stopped_business_unchanged")
    await e.click('[data-ba-action="refresh"]', "本人重读新目标与暂停原因")
    await e.ready()
    await expect(e.page.locator("#ba-current-plan .ba-plan-goal")).to_contain_text(new_goal)
    await expect(e.page.locator('[data-baws-followup="resume"]')).to_be_enabled()
    prior_checks = {(row["pid"], row["started_at"], row["run_id"]) for row in
                    _observations(e, state["scope"])["fact_checks"]}
    await e.followup_click("resume", "本人核对新目标后明确恢复")
    grants = await e.wait(lambda: (rows if len(rows := e.db.rows(
        "SELECT * FROM business_assistant_followup_grants WHERE plan_id=? ORDER BY granted_at,id", (state["plan_id"],))) == 2 else None),
                         "新goal唯一Grant")
    old = next(row for row in grants if row["id"] == original_grant["id"])
    active = [row for row in grants if row["status"] == "active"]
    require(old["status"] == "revoked" and old["stop_reason"] == "goal_changed" and len(active) == 1
            and active[0]["id"] != old["id"] and active[0]["goal_version"] == changed["goal_version"],
            "恢复复活旧Grant或没有新目标唯一授权")
    checks = await e.wait(lambda: [row for row in _observations(e, state["scope"])["fact_checks"]
                                  if (row["pid"], row["started_at"], row["run_id"]) not in prior_checks
                                  and row.get("returned") and row["plan_id"] == state["plan_id"]
                                  and row["auth_kind"] == "grant" and row["grant_id"] == active[0]["id"]
                                  and row["goal_version"] == changed["goal_version"]
                                  and any(call["method"] == "GET" and call["status"] == 200 for call in row["native_gets"])],
                          "新授权后原GET事实核对", timeout=30)
    require(e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=?", (state["session_id"],)) == history["business_assistant_proposals"],
            "新目标恢复替代原pending卡或自动办理")
    e.business_unchanged(before, "goal_new_grant_rechecks_original_business_unchanged")
    e.observe("structural_goal_original_ui_own_resume", {"plan_id": state["plan_id"], "old_goal_version": original_plan["goal_version"],
              "new_goal_version": changed["goal_version"], "editing_run": {key: edited_run[key] for key in
                  ("id", "plan_id", "goal_version", "status", "stop_requested", "error_code")},
              "original_proposal_id": card["id"], "grant_versions": [{key: row[key] for key in
                  ("id", "goal_version", "status", "stop_reason")} for row in grants], "real_new_grant_fact_checks": checks,
              "original_ui_post_plan_id": payload["plan_id"], "save_work_plan_item_id": saved_items[0]["id"],
              "plan_updated_event_id": updated_events[0]["id"],
              "provider_source": _load(Path(e.manifest["evidence_root"]) / ("goal-input-" + edited_run["id"] + ".json"))})
    await e.snapshot("original-goal-changed-own-new-grant-resume")
    await _end_grant(e, state)


GOAL_CLOSEOUT_SCENARIOS = (("runtime-original-ui-goal-change-own-resume", structural_goal_own_resume, 210),)
