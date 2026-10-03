"""Real native 201 survives dispatch/notification TX failure and natural backoff."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid

from playwright.async_api import expect

from runtime_faults import _atomic_json, _digest, _load, _rows, _utc
from runtime_receipt_closeout import FLOW_CREATE, _prepare_flow, _payload
from sales_business import require


RUNTIME_TABLES = ("business_assistant_sessions", "business_assistant_work_plans", "business_assistant_plan_steps",
                  "business_assistant_followup_grants", "business_assistant_runs", "business_assistant_notifications",
                  "business_assistant_run_events", "business_assistant_wake_events")


def _table_rows(db, sid, plan_id, store_id):
    from sqlalchemy import text
    output = {}
    for table in RUNTIME_TABLES:
        if table == "business_assistant_run_events":
            output[table] = [dict(row) for row in db.execute(text(
                "SELECT * FROM business_assistant_run_events WHERE run_id IN "
                "(SELECT id FROM business_assistant_runs WHERE session_id=:value) ORDER BY id"), {"value": sid}).mappings()]
            continue
        where, value = (("id", sid) if table == "business_assistant_sessions" else
                        ("store_id", store_id) if table in {"business_assistant_notifications", "business_assistant_wake_events"} else
                        ("plan_id", plan_id) if table == "business_assistant_plan_steps" else ("session_id", sid))
        output[table] = [dict(row) for row in db.execute(text("SELECT * FROM " + table + " WHERE " + where + "=:value ORDER BY id"),
                                                       {"value": value}).mappings()]
    return output


def _committed_rows(manifest, sid, plan_id, store_id):
    output = {}
    for table in RUNTIME_TABLES:
        if table == "business_assistant_run_events":
            output[table] = _rows(manifest["database_path"],
                "SELECT * FROM business_assistant_run_events WHERE run_id IN "
                "(SELECT id FROM business_assistant_runs WHERE session_id=?) ORDER BY id", (sid,))
            continue
        where, value = (("id", sid) if table == "business_assistant_sessions" else
                        ("store_id", store_id) if table in {"business_assistant_notifications", "business_assistant_wake_events"} else
                        ("plan_id", plan_id) if table == "business_assistant_plan_steps" else ("session_id", sid))
        output[table] = _rows(manifest["database_path"], "SELECT * FROM " + table + " WHERE " + where + "=? ORDER BY id", (value,))
    return output


def _rollback_equal(before, after, source_id):
    for table in RUNTIME_TABLES:
        old, current = before[table], after[table]
        if table == "business_assistant_wake_events":
            old = [row for row in old if row["id"] != source_id]
            current = [row for row in current if row["id"] != source_id]
        if old != current:
            return False
    return True


def _plain(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@contextmanager
def outbox_transaction_faults(manifest):
    """Fixed same-source failures; no production writes outside original functions."""
    require(manifest.get("synthetic_data_only") is True, "outbox故障只允许外部合成实例")
    from unittest.mock import patch
    from app import assistant_runtime_outbox as outbox, assistant_runtime_workspace as workspace
    from app import business_assistant_gateway as gateway
    from app.assistant_runtime_models import WakeEvent
    from sqlalchemy import select

    runtime, evidence = Path(manifest["runtime_root"]), Path(manifest["evidence_root"])
    control_path = runtime / "outbox-closeout-control.json"
    report_path = evidence / ("outbox-closeout-observations-" + str(os.getpid()) + ".json")
    original_dispatch, original_resolve, original_cas = outbox.dispatch_one, outbox._resolve_dispatch, outbox._event_cas
    original_notices, original_invoke = workspace.persist_event_notifications, gateway.invoke
    consumed, report = set(), {"schema": 1, "pid": os.getpid(), "failures": [], "native_successes": []}

    def save():
        _atomic_json(report_path, report)

    def active():
        return _load(control_path) if control_path.is_file() else None

    def native_source(arm):
        rows = _rows(manifest["database_path"], "SELECT * FROM flow_request_receipts WHERE store_id=? AND request_key=?",
                     (arm["store_id"], arm["request_key"]))
        return rows[0] if len(rows) == 1 else None

    def matches(event, arm, receipt):
        return (event["proposal_id"] == arm["proposal_id"] or
                event["plan_id"] == arm["plan_id"] or
                event["object_ref"] == {"type": "case", "id": receipt["case_id"]})

    async def invoke(request, user, operation_id, path_args=None, query=None, body=None):
        result = await original_invoke(request, user, operation_id, path_args, query, body)
        arm = active()
        if arm is not None and operation_id == FLOW_CREATE and (body or {}).get("request_id") == arm["request_key"]:
            receipt = native_source(arm)
            require(result["status"] == 201 and receipt is not None and receipt["actor_id"] == arm["owner_id"]
                    and receipt["case_id"] == result["data"]["id"], "故障前必须真实本人原201及原receipt")
            value = {"scope": arm["scope"], "pid": os.getpid(), "native_status": 201, "case_id": receipt["case_id"],
                     "receipt_id": receipt["id"], "receipt_digest": _digest(receipt), "utc": _utc()}
            report["native_successes"].append(value)
            _atomic_json(runtime / ("outbox-native-" + arm["scope"] + ".json"), value)
            save()
        return result

    async def resolve(db, event, *args, **kwargs):
        arm = active()
        receipt = native_source(arm) if arm else None
        if arm is None or receipt is None or not matches(event, arm, receipt):
            return await original_resolve(db, event, *args, **kwargs)
        # Original native commit is durable; the Web's separate result save may
        # finish next. Wait only in the read phase, before any dispatcher writer.
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            card = _rows(manifest["database_path"], "SELECT status FROM business_assistant_proposals WHERE id=?", (arm["proposal_id"],))[0]
            if card["status"] == "succeeded" and (runtime / ("outbox-native-" + arm["scope"] + ".json")).is_file():
                break
            await asyncio.sleep(.05)
        require(card["status"] == "succeeded", "原201结果保存未完成，不能推定依赖故障")
        key = arm["scope"], event["id"]
        if key not in consumed:
            db.info["synthetic_outbox_closeout"] = {"arm": arm, "event": event, "receipt": receipt,
                "before": _committed_rows(manifest, arm["session_id"], arm["plan_id"], arm["store_id"]), "injected": False}
        return await original_resolve(db, event, *args, **kwargs)

    def fault(db, phase):
        state = db.info.get("synthetic_outbox_closeout")
        if state is None or state["injected"] or state["arm"]["mode"] != phase:
            return
        arm, event = state["arm"], state["event"]
        pending = _table_rows(db, arm["session_id"], arm["plan_id"], arm["store_id"])
        state.update(injected=True, phase=phase, flushed=pending, injected_at=_utc())
        consumed.add((arm["scope"], event["id"]))
        raise RuntimeError("Fixed synthetic " + phase + " failure inside original outbox transaction")

    def notices(db, proof, *args, **kwargs):
        result = original_notices(db, proof, *args, **kwargs)
        fault(db, "notice_flush")
        return result

    def cas(db, event, *, state, now):
        result = original_cas(db, event, state=state, now=now)
        if state == "dispatched":
            fault(db, "dispatch_cas")
        return result

    async def dispatch(db, *args, **kwargs):
        result = await original_dispatch(db, *args, **kwargs)
        state = db.info.pop("synthetic_outbox_closeout", None)
        if state is not None and state["injected"]:
            arm, event = state["arm"], state["event"]
            after = _committed_rows(manifest, arm["session_id"], arm["plan_id"], arm["store_id"])
            current_event = _rows(manifest["database_path"], "SELECT * FROM business_assistant_wake_events WHERE id=?", (event["id"],))[0]
            original_event = next(row for row in state["before"]["business_assistant_wake_events"] if row["id"] == event["id"])
            retry_fields = {"version", "attempt", "state", "next_attempt_at", "dispatched_at"}
            require(result.state == "pending" and current_event["state"] == "pending"
                    and current_event["attempt"] == event["attempt"] + 1 and current_event["version"] == event["version"] + 1
                    and {key: value for key, value in current_event.items() if key not in retry_fields}
                        == {key: value for key, value in original_event.items() if key not in retry_fields}
                    and _rollback_equal(state["before"], after, event["id"]),
                    "固定outbox失败没有原Runtime整事务回滚及pending退避")
            row = {"scope": arm["scope"], "mode": arm["mode"], "phase": state["phase"], "event": _plain(event),
                   "native_case_id": state["receipt"]["case_id"], "native_receipt_id": state["receipt"]["id"],
                   "before": state["before"], "flushed_before_failure": state["flushed"], "after_rollback": after,
                   "pending_after_failure": current_event, "injected_at": state["injected_at"], "recorded_at": _utc(),
                   "source_retry_fields_only": {"before": {key: original_event[key] for key in sorted(retry_fields)},
                                                "after": {key: current_event[key] for key in sorted(retry_fields)}},
                   "runtime_rollback_exact_except_original_source_retry": True,
                   "derived_run_events_and_wake_events_rolled_back": True, "business_success_retained": True}
            report["failures"].append(row)
            save()
        return result

    save()
    with patch.object(gateway, "invoke", invoke), patch.object(outbox, "_resolve_dispatch", resolve), \
            patch.object(workspace, "persist_event_notifications", notices), patch.object(outbox, "_event_cas", cas), \
            patch.object(outbox, "dispatch_one", dispatch):
        yield


def _reports(e, scope):
    reports = [_load(path) for path in Path(e.manifest["evidence_root"]).glob("outbox-closeout-observations-*.json")]
    return {key: [row for report in reports for row in report[key] if row["scope"] == scope]
            for key in ("native_successes", "failures")}


async def _transaction_case(e, context, credentials, mode):
    prepared = await _prepare_flow(e, context, credentials, "recovery")
    await expect(e.page.locator("#ba-current-plan .ba-plan-goal")).to_contain_text(prepared["plan"]["goal"], timeout=20000)
    await expect(e.page.locator('[data-baws-followup="enable"]')).to_be_enabled(timeout=20000)
    await e.followup_click("enable", "本人开启真实201后的原依赖跟进")
    arm = {"scope": uuid.uuid4().hex, "mode": mode, "session_id": prepared["session_id"],
           "plan_id": prepared["plan"]["id"], "proposal_id": prepared["card"]["id"],
           "owner_id": prepared["user"]["id"], "store_id": prepared["card"]["store_id"],
           "request_key": _payload(prepared["card"])["body"]["request_id"]}
    _atomic_json(Path(e.manifest["runtime_root"]) / "outbox-closeout-control.json", arm)
    confirm_path = "/api/business-assistant/sessions/" + arm["session_id"] + "/proposals/" + arm["proposal_id"] + "/confirm"
    async with e.page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path == confirm_path) as pending:
        await e.click('[data-ba-action="confirm"][data-id="' + arm["proposal_id"] + '"]', "本人仅一次确认原Flow首卡")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["confirmation_results"][0]["status"] == "succeeded", "原Flow确认结果应保持成功")
    native = await e.wait(lambda: _reports(e, arm["scope"])["native_successes"], "原native201已返回")
    require(len(native) == 1, "原业务201被重放")
    after_native = e.business_snapshot("outbox_original_business_after_native_201")
    def complete_fault_evidence():
        rows = _reports(e, arm["scope"])["failures"]
        if (not any(row["event"]["topic"] == "flow" for row in rows)
                or not any(len(row["flushed_before_failure"]["business_assistant_runs"])
                           > len(row["before"]["business_assistant_runs"]) for row in rows)
                or mode == "notice_flush" and not any(
                    row["flushed_before_failure"]["business_assistant_notifications"]
                    != row["before"]["business_assistant_notifications"] for row in rows)):
            return None
        return rows
    failures = await e.wait(complete_fault_evidence,
                            "真实Flow来源、依赖Run及本场通知flush完整回滚证据", timeout=60)
    require(any(row["event"]["topic"] == "flow" for row in failures), "没有对真实原Flow来源注入，不能推定全生产者")
    require(any(len(row["flushed_before_failure"]["business_assistant_runs"]) > len(row["before"]["business_assistant_runs"])
                for row in failures), "固定失败前没有原依赖Run实际flush，不覆盖其回滚")
    if mode == "notice_flush":
        require(any(row["flushed_before_failure"]["business_assistant_notifications"] != row["before"]["business_assistant_notifications"]
                    for row in failures), "通知失败前未实际写通知")
    for row in failures:
        delay = (datetime.fromisoformat(row["pending_after_failure"]["next_attempt_at"]) -
                 datetime.fromisoformat(row["injected_at"]).replace(tzinfo=None)).total_seconds()
        require(28 <= delay <= 32, "原第一次自然退避并非30秒")
    cards = await e.wait(lambda: (rows if len(rows := e.db.rows(
        "SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY created_at,id", (arm["session_id"],))) == 2 else None),
                         "自然退避后唯一依赖后继", timeout=95)
    first = [row for row in cards if row["id"] == arm["proposal_id"]]
    successors = [row for row in cards if row["id"] != arm["proposal_id"]]
    require(len(first) == len(successors) == 1, "必须按原首卡ID核对两原卡，不能跨Run使用step_order猜身份")
    cards = [first[0], successors[0]]
    require([row["status"] for row in cards] == ["succeeded", "pending"], "恢复重复准备或后台自动办理后继")
    require(json.loads(cards[1]["payload"])["path_args"]["case_id"] == prepared["successor"]["case_id"], "自然恢复后继串原单")
    await e.wait(lambda: all(e.db.rows("SELECT state FROM business_assistant_wake_events WHERE id=?", (row["event"]["id"],))[0]["state"] == "dispatched"
                            for row in _reports(e, arm["scope"])["failures"]), "全部本场故障source自然恢复", timeout=95)
    reports = _reports(e, arm["scope"])
    for row in reports["failures"]:
        recovered = e.db.rows("SELECT * FROM business_assistant_wake_events WHERE id=?", (row["event"]["id"],))[0]
        require(recovered["attempt"] == row["pending_after_failure"]["attempt"] + 1
                and recovered["dispatched_at"] >= row["pending_after_failure"]["next_attempt_at"], "原source未按真实退避恢复或额外重试")
    mapped = await e.wait(lambda: e.db.rows(
        "SELECT DISTINCT run_id FROM business_assistant_run_items WHERE proposal_id=? AND run_id IS NOT NULL",
        (cards[1]["id"],)), "恢复后原后继卡与准备Run真实关联", timeout=20)
    require(len(mapped) == 1, "恢复后继未对应唯一准备Run")
    await e.wait(lambda: e.db.rows("SELECT status FROM business_assistant_runs WHERE id=?", (mapped[0]["run_id"],))[0]["status"]
                        in {"succeeded", "failed", "cancelled"}, "恢复后继准备Run真实终态", timeout=30)
    runs = e.db.rows("SELECT id,status,plan_id,error_code FROM business_assistant_runs WHERE session_id=? AND auth_kind='grant'",
                     (arm["session_id"],))
    require(len(runs) == 1 and runs[0]["id"] == mapped[0]["run_id"] and runs[0]["status"] == "succeeded"
            and runs[0]["plan_id"] == arm["plan_id"] and runs[0]["error_code"] is None, "同一实际变化额外Grant Run或恢复Run未成功")
    await e.wait(lambda: e.db.rows("SELECT id FROM business_assistant_notifications WHERE session_id=? AND proposal_id=? AND kind='proposal_ready'",
                                   (arm["session_id"], cards[1]["id"])), "恢复后继原proposal_ready通知实际耐久", timeout=35)
    notices = e.db.rows("SELECT source_key,kind,status,proposal_id,task_id FROM business_assistant_notifications WHERE store_id=? ORDER BY id", (arm["store_id"],))
    require(len({(row["source_key"], row["kind"]) for row in notices}) == len(notices)
            and any(row["proposal_id"] == cards[1]["id"] for row in notices), "恢复通知丢失或重复")
    e.business_unchanged(after_native, "outbox_rollback_backoff_recovery_original_201_business_unchanged")
    control_path = Path(e.manifest["runtime_root"]) / "outbox-closeout-control.json"
    require(control_path.is_file() and _load(control_path)["scope"] == arm["scope"], "故障scope在核查前意外切换")
    control_path.unlink()
    e.action("fixed_fault_disarm", "恢复核查终点解除本场外部故障装置，原撤销正常执行", scope=arm["scope"])
    source_ids = [row["event"]["id"] for row in reports["failures"]]
    require(len(source_ids) == len(set(source_ids)), "单个真实source被重复注入故障")
    e.observe("outbox_same_transaction_natural_recovery", {"mode": mode, "original_native_201": native, "fault_sources": reports["failures"],
              "actual_injection_count": len(source_ids), "injections_per_source": {ident: source_ids.count(ident) for ident in source_ids},
              "control_disarmed_at_recovery_endpoint": True,
              "unique_successor_id": cards[1]["id"], "unique_grant_run": runs, "unique_notifications": notices,
              "clock_or_deadline_modified": False, "all_source_map_hooks_claimed": False})
    await e.click('[data-ba-action="refresh"]', "本人核对恢复后的原卡与仍待确认后继")
    await e.ready()
    await e.snapshot("outbox-" + mode + "-native-success-unique-pending-successor")
    await e.page.wait_for_function("id => { const view=globalThis.AssistantWorkspace?.snapshot?.();"
        "return view?.plan?.id===id && !view.planLoading && !view.followupPending"
        "&& !businessAssistantState.workLoading && !businessAssistantState.busy && !businessAssistantState.runId; }",
        arg=arm["plan_id"], timeout=20000)
    await expect(e.page.locator('[data-baws-followup="revoke"]')).to_be_enabled()
    await e.click('[data-baws-followup="revoke"]', "原本人结束本场跟进第一次")
    await expect(e.page.locator('[data-baws-followup="revoke"]')).to_have_text("确认结束这件事")
    await e.followup_click("revoke", "原本人确认结束本场跟进")


async def dispatch_cas_failure(e, context, credentials):
    await _transaction_case(e, context, credentials, "dispatch_cas")


async def notice_flush_failure(e, context, credentials):
    await _transaction_case(e, context, credentials, "notice_flush")


OUTBOX_CLOSEOUT_SCENARIOS = (
    ("runtime-original-201-outbox-cas-rollback-natural-recovery", dispatch_cas_failure, 240),
    ("runtime-original-201-notice-flush-rollback-natural-recovery", notice_flush_failure, 240),
)
