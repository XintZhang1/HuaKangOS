"""Finite confirmation/receipt faults against original employee HTTP paths.

Importing this module starts nothing and imports no application module. Runtime
controls are external JSON; database evidence is SELECT-only. The original API
creates every Flow case, Task, Event, Audit and RequestReceipt. Lookup never
replays a write. The batch contract is explicitly HTTP rather than a UI click.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import asyncio
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlsplit

from runtime_faults import _atomic_json, _digest, _load, _require, _rows, _utc


FLOW_CREATE = "POST /api/flow/cases"
FLOW_READ = "GET /api/flow/cases/{case_id}"
FLOW_ACTION = "POST /api/flow/cases/{case_id}/actions/{action}"
MASTER_CREATE = "POST /api/flow/master/{kind}"
FLOW_TABLES = ("flow_cases", "flow_customers", "flow_tasks", "flow_events", "flow_request_receipts", "audit_logs")
_MODES = {"before_invoke", "success_commit_failure", "lost_response"}


def _decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def _payload(card):
    value = _decoded(card["payload"])
    return {key: value.get(key) or {} for key in ("path_args", "query", "body")}


def _one(database, table, ident):
    values = _rows(database, "SELECT * FROM " + table + " WHERE id=?", (ident,))
    _require(len(values) == 1, "固定来源必须唯一存在：" + table)
    return values[0]


def _frozen(database, arm):
    card = _one(database, "business_assistant_proposals", arm["proposal_id"])
    work = _one(database, "business_assistant_work_items", arm["work_item_id"])
    items = _rows(database, "SELECT * FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id=?", (card["id"],))
    _require(len(items) == 1, "固定故障须有唯一真实确认冻结")
    item = items[0]
    snapshot = _decoded(item["submission_snapshot"])
    _require(card["status"] == "executing" and card["version"] == arm["proposal_version"] + 1
             and card["digest"] == arm["proposal_digest"] and _payload(card) == arm["payload"]
             and (card["owner_id"], card["store_id"], card["session_id"], card["source_work_item_id"])
                 == (arm["owner_id"], arm["store_id"], arm["session_id"], arm["work_item_id"])
             and work == arm["work"] and item["status"] == "running" and item["run_id"] is None
             and item["work_item_id"] == work["id"] and item["attempt_no"] == 1
             and item["item_key"] == "confirmation:" + card["id"]
             and isinstance(snapshot, dict) and set(snapshot) == {
                 "operation_id", "path_args", "query", "body", "request_id", "actor_id", "store_id",
                 "role", "access_version", "confirmed_at"}
             and snapshot["operation_id"] == arm["operation_id"] == card["operation_id"]
             and all(snapshot[key] == arm["payload"][key] for key in ("path_args", "query", "body"))
             and (snapshot["actor_id"], snapshot["store_id"], snapshot["role"], snapshot["access_version"])
                 == (arm["owner_id"], arm["store_id"], arm["owner_role"], arm["access_version"])
             and snapshot["request_id"] == arm["payload"]["body"].get("request_id")
             and _digest(snapshot) == item["submission_digest"],
             "故障来源必须是已提交的原卡/WorkItem/原冻结字节，不修改或猜填")
    return card, item, snapshot


def _native_facts(database, arm, result, snapshot):
    _require(result.get("status") == 201, "只有原invoke实际201可进入提交后故障")
    if arm["operation_id"] == FLOW_CREATE:
        key = snapshot["request_id"]
        _require(isinstance(key, str) and 16 <= len(key) <= 80, "原Flow须有真实原request_id")
        receipts = _rows(database, "SELECT * FROM flow_request_receipts WHERE store_id=? AND request_key=?", (arm["store_id"], key))
        _require(len(receipts) == 1, "原Flow必须真实生成唯一RequestReceipt")
        receipt = receipts[0]
        case = _one(database, "flow_cases", receipt["case_id"])
        customer = _one(database, "flow_customers", case["customer_id"])
        tasks = _rows(database, "SELECT * FROM flow_tasks WHERE case_id=? ORDER BY id", (case["id"],))
        events = _rows(database, "SELECT * FROM flow_events WHERE case_id=? ORDER BY id", (case["id"],))
        audits = _rows(database, "SELECT * FROM audit_logs WHERE entity_type='flow' AND entity_id=? AND action='flow_create' ORDER BY id", (case["id"],))
        native_digest = _digest({"operation": "create", "payload": {"kind": "lead", "values": snapshot["body"].get("values", {})}})
        _require(receipt["actor_id"] == arm["owner_id"] and receipt["digest"] == native_digest
                 and receipt["store_id"] == arm["store_id"] and result.get("data", {}).get("id") == case["id"]
                 and case["kind"] == "lead" and case["state"] == "unassigned" and case["flow_version"] == 2
                 and case["owner_id"] == case["created_by"] == arm["owner_id"] and case["store_id"] == arm["store_id"]
                 and customer["name"] == arm["name"] and customer["phone"] == arm["phone"]
                 and customer["owner_id"] == arm["owner_id"] and customer["store_id"] == arm["store_id"]
                 and len(tasks) == len(events) == len(audits) == 1
                 and tasks[0]["key"] == "assign" and tasks[0]["status"] == "open"
                 and events[0]["action"] == "create" and events[0]["actor_id"] == arm["owner_id"]
                 and audits[0]["actor_id"] == arm["owner_id"] and audits[0]["store_id"] == arm["store_id"],
                 "原Flow201须对应本人本店实际Case/Customer/Task/Event/Audit及规范原receipt摘要")
        return {"case_id": case["id"], "customer_id": customer["id"], "receipt_id": receipt["id"],
                "receipt_sha256": _digest(receipt), "case_sha256": _digest(case), "customer_sha256": _digest(customer),
                "task_ids": [row["id"] for row in tasks], "event_ids": [row["id"] for row in events],
                "audit_ids": [row["id"] for row in audits]}
    _require(arm["operation_id"] == MASTER_CREATE, "故障仅支持本场Flow或批量客户原提交")
    customers = _rows(database, "SELECT * FROM flow_customers WHERE name=?", (arm["name"],))
    _require(len(customers) == 1, "第二客户真实201须已提交唯一原客户")
    customer = customers[0]
    audits = _rows(database, "SELECT * FROM audit_logs WHERE entity_type='flow_master' AND entity_id=? AND action='master_create'", (customer["id"],))
    _require(result.get("data", {}).get("id") == customer["id"] and customer["phone"] == arm["phone"]
             and customer["owner_id"] == arm["owner_id"] and customer["store_id"] == arm["store_id"]
             and len(audits) == 1 and audits[0]["actor_id"] == arm["owner_id"] and audits[0]["store_id"] == arm["store_id"],
             "B真实201须对应本人本店客户与审计，不合成成功响应")
    return {"customer_id": customer["id"], "customer_sha256": _digest(customer),
            "audit_id": audits[0]["id"], "audit_sha256": _digest(audits[0])}


@contextmanager
def receipt_faults(manifest):
    """Install only after the isolated app imports, under its network guard."""
    from app import business_assistant_gateway as gateway, business_assistant_service as service
    from app.business_assistant_models import AssistantProposal
    from app.assistant_runtime_models import RunItem
    import httpx

    runtime, evidence = Path(manifest["runtime_root"]).resolve(), Path(manifest["evidence_root"]).resolve()
    database = Path(manifest["database_path"]).resolve()
    _require(runtime.is_dir() and evidence.is_dir() and database.is_relative_to(runtime), "故障只允许本局外置合成实例")
    arm_path, gate_path = runtime / "receipt-closeout-active.json", runtime / "receipt-closeout-get-gate.json"
    _require(not arm_path.exists() and not gate_path.exists(), "不能复用旧回执故障实例")
    active = ContextVar("synthetic_receipt_confirmation", default=None)
    original_decide, original_invoke, original_commit = service.decide_proposal, gateway.invoke, service.commit
    consumed, gates = {}, {}

    async def decide(db, request, user, session_id, row, digest, cancel=False, answers=None):
        if not arm_path.is_file() or row is None or cancel:
            return await original_decide(db, request, user, session_id, row, digest, cancel, answers)
        arm = _load(arm_path)
        if row.id != arm["proposal_id"]:
            return await original_decide(db, request, user, session_id, row, digest, cancel, answers)
        path = "/api/business-assistant/sessions/" + session_id + "/proposals/"
        _require(arm["mode"] in _MODES and re.fullmatch(r"[0-9a-f]{32}", arm["arm_id"])
                 and request.method == "POST" and request.url.path == path + ("batch" if arm["batch"] else row.id + "/confirm")
                 and session_id == arm["session_id"] and digest == arm["proposal_digest"]
                 and user.id == arm["owner_id"] and user.role == arm["owner_role"] and user.access_version == arm["access_version"]
                 and getattr(user, "_active_store_id", None) == arm["store_id"]
                 and request.headers.get("cookie") and request.headers.get("x-csrf-token")
                 and request.headers.get("x-store-id") == str(arm["store_id"]), "固定故障必须匹配员工原确认身份与真实路由")
        _require(arm["arm_id"] not in consumed, "固定原确认目标不得再次消费或重放")
        state = {"arm": arm, "db": db, "phase": "armed", "native_invocations": 0, "injections": 0}
        consumed[arm["arm_id"]] = state
        token = active.set(state)
        try:
            return await original_decide(db, request, user, session_id, row, digest, cancel, answers)
        finally:
            active.reset(token)

    def save(state):
        arm = state["arm"]
        value = {key: value for key, value in state.items() if key not in {"arm", "db"}}
        value.update(schema=1, arm_id=arm["arm_id"], mode=arm["mode"], proposal_id=arm["proposal_id"],
                     session_id=arm["session_id"], owner_id=arm["owner_id"], store_id=arm["store_id"], recorded_at=_utc())
        _atomic_json(evidence / ("receipt-closeout-fault-" + arm["arm_id"] + ".json"), value)

    async def invoke(request, user, operation_id, path_args=None, query=None, body=None):
        state = active.get()
        if state is not None:
            arm = state["arm"]
            try:
                _require(state["phase"] == "armed" and operation_id == arm["operation_id"]
                         and {"path_args": path_args or {}, "query": query or {}, "body": body or {}} == arm["payload"],
                         "原invoke必须使用本卡完整冻结payload且仅进入一次")
                card, item, snapshot = _frozen(database, arm)
                state.update(phase="frozen_before_native", confirmation_id=item["id"],
                             submission_digest=item["submission_digest"], snapshot_sha256=_digest(snapshot),
                             frozen_card_sha256=_digest(card), frozen_item_sha256=_digest(item))
                save(state)
                if arm["mode"] == "before_invoke":
                    state.update(phase="before_native_failure", injections=1)
                    save(state)
                    raise httpx.ReadError("Synthetic transport failed after the durable freeze, before any original native invocation")
                state["native_invocations"] = 1
                result = await original_invoke(request, user, operation_id, path_args, query, body)
                state.update(_native_facts(database, arm, result, snapshot))
                state.update(phase="native_success_returned", native_status=201, native_returned_at=_utc())
                save(state)
                if arm["mode"] == "lost_response":
                    state.update(phase="native_committed_response_dropped", injections=1)
                    save(state)
                    raise httpx.ReadError("Synthetic response lost after the original native Flow or customer commit")
                return result
            except Exception as error:
                if state["phase"] not in {"before_native_failure", "native_committed_response_dropped"}:
                    state.update(phase="fault_validation_failed", error_type=type(error).__name__)
                    save(state)
                raise
        # The mismatch gate delays the untouched successful original GET. It
        # does not fake a receipt, mutate SQL, or change original authorization.
        if gate_path.is_file() and request.method == "GET" and operation_id == FLOW_READ:
            gate = _load(gate_path)
            path = "/api/business-assistant/sessions/" + gate["session_id"] + "/proposals/" + gate["proposal_id"] + "/execution-result"
            if request.url.path == path:
                _require(gate["gate_id"] not in gates and path_args == {"case_id": gate["case_id"]}
                         and user.id == gate["owner_id"] and request.headers.get("cookie")
                         and request.headers.get("x-store-id") == str(gate["store_id"]), "只门控本卡原内部GET一次")
                original_card = _one(database, "business_assistant_proposals", gate["proposal_id"])
                _require(original_card["status"] in {"executing", "uncertain"}, "source变化场须有尚未协调的真实确认")
                result = await original_invoke(request, user, operation_id, path_args, query, body)
                _require(result.get("status") == 200 and result.get("data", {}).get("id") == gate["case_id"], "门控前必须读取真实原单200")
                ledger_path = evidence / ("receipt-closeout-gate-" + gate["gate_id"] + ".json")
                ledger = {"schema": 1, "phase": "held_original_get", **gate, "original_card_sha256": _digest(original_card), "held_at": _utc()}
                gates[gate["gate_id"]] = ledger
                _atomic_json(ledger_path, ledger)
                release_path = runtime / ("receipt-closeout-gate-release-" + gate["gate_id"] + ".json")
                deadline = asyncio.get_running_loop().time() + 25
                while asyncio.get_running_loop().time() < deadline:
                    if release_path.is_file():
                        _require(_load(release_path) == {"gate_id": gate["gate_id"], "action": "release_original_get"}, "释放必须绑定本次原GET")
                        latest = _one(database, "business_assistant_proposals", gate["proposal_id"])
                        _require(latest["status"] == "succeeded" and latest["version"] > original_card["version"], "只在原协调器真实推进source之后释放")
                        ledger.update(phase="released_after_original_reconciliation", latest_card_sha256=_digest(latest), released_at=_utc())
                        _atomic_json(ledger_path, ledger)
                        return result
                    await asyncio.sleep(0.025)
                ledger.update(phase="gate_timeout", failed_at=_utc())
                _atomic_json(ledger_path, ledger)
                raise RuntimeError("Original receipt GET gate exceeded its finite deadline")
        return await original_invoke(request, user, operation_id, path_args, query, body)

    def commit(db):
        state = active.get()
        if state is None or state["arm"]["mode"] != "success_commit_failure" or state["phase"] != "native_success_returned":
            return original_commit(db)
        arm = state["arm"]
        try:
            _require(db is state["db"], "结果失败仅可发生于该原confirm事务")
            cards = [row for row in db.identity_map.values() if isinstance(row, AssistantProposal) and row.id == arm["proposal_id"]]
            items = [row for row in db.identity_map.values() if isinstance(row, RunItem) and row.id == state["confirmation_id"]]
            _require(len(cards) == len(items) == 1 and cards[0].status == items[0].status == "succeeded"
                     and cards[0].result["status"] == 201 and items[0].submission_digest == state["submission_digest"],
                     "服务必须已观察原201并准备真实success结果后才拦结果commit")
            durable_card, durable_item, snapshot = _frozen(database, arm)
            _require(_digest(snapshot) == state["snapshot_sha256"], "结果commit失败不得改变原冻结")
            state.update(phase="observed_success_result_commit_failed", injections=1,
                         result_business_status="succeeded", durable_before_failure_card_sha256=_digest(durable_card),
                         durable_before_failure_item_sha256=_digest(durable_item))
            save(state)
        except Exception as error:
            state.update(phase="fault_validation_failed", error_type=type(error).__name__)
            save(state)
            raise
        raise RuntimeError("Synthetic assistant result commit failure after original native success was observed")

    service.decide_proposal, gateway.invoke, service.commit = decide, invoke, commit
    normal = False
    try:
        yield
        normal = True
    finally:
        service.decide_proposal, gateway.invoke, service.commit = original_decide, original_invoke, original_commit
        if normal:
            expected = {"before_invoke": "before_native_failure", "lost_response": "native_committed_response_dropped",
                        "success_commit_failure": "observed_success_result_commit_failed"}
            for state in consumed.values():
                _require(state["phase"] == expected[state["arm"]["mode"]] and state["injections"] == 1,
                         "已命中的故障必须完成唯一指定边界，不忽略validation失败")
            _require(all(value["phase"] == "released_after_original_reconciliation" for value in gates.values()), "原GET门控未完成")


def _response(provider, request, body, message, calls, background):
    import httpx
    provider.counts["synthetic_requests"] += 1
    provider.counts["requests"].append({"tools": calls, "stream": bool(body.get("stream")), "background": bool(background), "receipt_closeout": True})
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    if not body.get("stream"):
        return httpx.Response(200, json={"choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage}, request=request)
    packets = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": message.get("content") or ""}, "finish_reason": None}]}]
    packets.extend({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": index, **call}]}, "finish_reason": None}]}
                   for index, call in enumerate(message.get("tool_calls", [])))
    packets.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage})
    content = "".join("data: " + json.dumps(value, ensure_ascii=False) + "\n\n" for value in packets) + "data: [DONE]\n\n"
    return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"}, request=request)


@contextmanager
def extend_provider(provider):
    """Add only the finite, fully supplied receipt employee instruction."""
    from provider import tool, reply
    original = provider.handle

    async def handle(request):
        body = json.loads(request.content)
        messages = body["messages"]
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1]) if marker in messages[0]["content"] else {}
        text = next((row["content"] for row in reversed(messages) if row["role"] == "user"),
                    next((row["content"] for row in reversed(context.get("recent_messages", [])) if row["role"] == "user"), ""))
        match = re.fullmatch(r"回执收口 (freeze|storage|recovery) (浏览器回执(?:freeze|storage|recovery)_[0-9a-f]{12})\n(.+)", text, re.DOTALL)
        if match is None:
            return await original(request)
        _require((request.url.scheme, request.url.host, request.url.path) == ("https", "api.deepseek.com", "/chat/completions"), "有限provider入口不匹配")
        mode, name = match.group(1), match.group(2)
        source = json.loads(match.group(3))
        successor = None
        if mode == "freeze":
            values = source
        else:
            _require(set(source) == {"values", "successor"}, "恢复场须明确提供两项独立原业务来源")
            values, successor = source["values"], source["successor"]
            _require(set(successor) == {"case_id", "task_id", "case_version", "case_number", "customer_name", "assignee_id"}
                     and all(type(successor[key]) is int and successor[key] > 0
                             for key in ("case_id", "task_id", "case_version", "assignee_id"))
                     and isinstance(successor["case_number"], str) and successor["case_number"]
                     and successor["customer_name"] == name + "_后继", "后继分派只能引用员工已读取的原单/任务/员工事实")
        _require(set(values) == {"customer_name", "customer_phone", "source"} and values["customer_name"] == name
                 and re.fullmatch(r"198[0-9]{8}", values["customer_phone"]) and values["source"] == "展厅到店",
                 "原Flow准备只使用员工完整提供的事实")
        tools = [row for row in messages if row["role"] == "tool"]
        calls = len(tools)
        background = bool(context.get("trigger", {}).get("background_is_not_new_employee_instruction"))
        if background:
            _require(mode in {"storage", "recovery"}, "冻结失败事项未获后台准备授权")
            if not calls:
                runs = _rows(provider.manifest["database_path"], "SELECT * FROM business_assistant_runs WHERE id=?",
                             (context["trigger"]["run_id"],))
                _require(len(runs) == 1 and runs[0]["auth_kind"] == "grant" and runs[0]["status"] == "running",
                         "依赖后继准备须来自本人原真实Grant Run")
                steps = _rows(provider.manifest["database_path"],
                              "SELECT * FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (runs[0]["plan_id"],))
                _require(len(steps) == 2 and steps[0]["key"] == "create" and steps[0]["status"] == "completed"
                         and steps[1]["key"] == "next" and _decoded(steps[1]["depends_on"]) == ["create"]
                         and _one(provider.manifest["database_path"], "business_assistant_proposals",
                                  steps[0]["proposal_id"])["status"] == "succeeded",
                         "只有原协调器保存首项真实成功并完成依赖之后可准备后继")
                case = _one(provider.manifest["database_path"], "flow_cases", successor["case_id"])
                assignment = _one(provider.manifest["database_path"], "flow_tasks", successor["task_id"])
                _require(case["number"] == successor["case_number"] and case["version"] == successor["case_version"]
                         and case["state"] == "unassigned" and case["kind"] == "lead"
                         and case["store_id"] == runs[0]["store_id"] and case["created_by"] == runs[0]["owner_id"]
                         and assignment["case_id"] == case["id"] and assignment["store_id"] == case["store_id"]
                         and assignment["key"] == "assign" and assignment["status"] == "open"
                         and assignment["assignee_id"] == runs[0]["owner_id"], "后继须仍是本人本店真实未分派原单及原任务")
                message = tool("prepare_business_form", {"form_ref": "case:" + str(successor["case_id"]) + ":assign",
                    "values": {"assignee_id": successor["assignee_id"]},
                    "summary": "分派接待：" + successor["case_number"] + " " + successor["customer_name"]}, "receipt_successor")
            elif calls == 1:
                prepared = json.loads(tools[-1]["content"])
                _require(prepared.get("status") == 200 and len(prepared.get("items", [])) == 1
                         and isinstance(prepared["items"][0].get("proposal_id"), str), "原后继prepare必须实际准备唯一卡")
                message = reply("原后继接待的分派已准备，仍须本人核对确认。")
            else:
                raise RuntimeError("Finite receipt background protocol exhausted")
        elif calls == 0:
            message = tool("inspect_business_form", {"form_ref": "flow:lead"}, "receipt_inspect")
        elif calls == 1:
            message = tool("prepare_business_form", {"form_ref": "flow:lead", "values": values,
                "summary": "新建售前接待：" + name}, "receipt_prepare")
        elif calls == 2 and mode != "freeze":
            prepared = json.loads(tools[-1]["content"])
            _require(prepared.get("status") == 200 and len(prepared.get("items", [])) == 1
                     and isinstance(prepared["items"][0].get("proposal_id"), str), "计划只能引用原prepare真实卡")
            proposal_id = prepared["items"][0]["proposal_id"]
            condition = {"type": "proposal_succeeded", "proposal_id": proposal_id}
            message = tool("save_work_plan", {"schema_version": 2, "goal": name + "：先核对首项，再准备原后继接待的分派",
                "steps": [{"key": "create", "title": "第一项真实接待", "proposal_id": proposal_id,
                           "completion_conditions": [condition]},
                          {"key": "next", "title": "原首项成功后分派第二接待", "depends_on": ["create"],
                           "object_ref": {"type": "case", "id": successor["case_id"]},
                           "form_ref": "case:" + str(successor["case_id"]) + ":assign",
                           "conditions": [condition, {"type": "native_action_available",
                               "object_ref": {"type": "case", "id": successor["case_id"]}, "action_key": "assign"}],
                           "completion_conditions": [{"type": "native_task_state", "task_id": successor["task_id"],
                               "expected_status": "done"}]}]}, "receipt_plan")
        elif calls == (2 if mode == "freeze" else 3):
            message = reply("接待已准备，请核对；持续跟进由本人另行开启。")
        else:
            raise RuntimeError("Finite receipt employee protocol exhausted")
        return _response(provider, request, body, message, calls, background)

    provider.handle = handle
    try:
        yield
    finally:
        provider.handle = original


def _assistant_rows(e, session_id):
    return {table: e.db.rows("SELECT * FROM " + table + " WHERE session_id=? ORDER BY id", (session_id,))
            for table in ("business_assistant_proposals", "business_assistant_work_items", "business_assistant_runs")}


def _confirmations(e, card_id):
    return e.db.rows("SELECT * FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id=? ORDER BY id", (card_id,))


async def _prepare_flow(e, context, credentials, mode):
    from playwright.async_api import expect
    from sales_business import employee_choice, facts, login_as, native_submit, new_event, same_original, task
    user = await e.login(context, credentials, "reception", route="cases/lead" if mode != "freeze" else None)
    token = uuid.uuid4().hex[:12]
    name = "浏览器回执" + mode + "_" + token
    phone = "198" + str(int(token, 16) % 100000000).zfill(8)
    _require(not e.db.rows("SELECT id FROM flow_customers WHERE phone IN (?,?)", (phone, "198" + str((int(phone[3:]) + 1) % 100000000).zfill(8))), "本场员工事实不能复用已有客户")
    values = {"customer_name": name, "customer_phone": phone, "source": "展厅到店"}
    source, target = values, None
    if mode != "freeze":
        await expect(e.page.locator("#main h1")).to_have_text("售前接待")
        await e.click('[data-act="newcase"][data-kind="lead"]', "原UI先建立本场独立依赖后继来源")
        await e.fill('#modal [name="customer_name"]', name + "_后继")
        await e.fill('#modal [name="customer_phone"]', "198" + str((int(phone[3:]) + 1) % 100000000).zfill(8))
        e.action("select", "后继原接待来源", value="展厅到店")
        await e.page.locator('#modal [name="source"]').select_option(label="展厅到店")
        created, response, _ = await native_submit(e, "/api/flow/cases", 201)
        target = facts(e, created["id"])
        assignment = task(target, "assign")
        _require(target["case"]["state"] == "unassigned" and target["case"]["created_by"] == user["id"]
                 and target["case"]["store_id"] == 1 and target["customer"]["name"] == name + "_后继",
                 "原UI后继须是本人员工创建的独立接待")
        handoff = None
        if assignment["assignee_id"] != user["id"]:
            original = target
            manager = await login_as(e, context, credentials, "manager", f'case/{target["case"]["id"]}', 1)
            await expect(e.page.locator("#main h1")).to_have_text(target["case"]["title"])
            transfer_button = e.page.locator(f'#main [data-act="assign"][data-id="{assignment["id"]}"]')
            await expect(transfer_button).to_be_visible()
            await expect(transfer_button).to_be_enabled()
            await e.click(f'#main [data-act="assign"][data-id="{assignment["id"]}"]', "主管转交本场原分派任务给创建员工")
            await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
            await employee_choice(e, user)
            reason = "本场接待由创建员工继续核对并准备分派，保留原创建人与客户事实。"
            await e.fill('#modal [name="reason"]', reason, "原分派任务转交原因")
            _, handoff, _ = await native_submit(e, f'/api/flow/tasks/{assignment["id"]}/assign', 200,
                                                 case_id=target["case"]["id"])
            reassigned = facts(e, target["case"]["id"])
            same_original(original, reassigned)
            event = new_event(original, reassigned, "reassign", manager["id"])
            current_task = task(reassigned, "assign")
            _require(current_task["id"] == assignment["id"] and current_task["version"] == assignment["version"] + 1
                     and current_task["assignee_id"] == user["id"] and handoff["submitted_version"] == assignment["version"]
                     and reassigned["case"]["version"] == original["case"]["version"]
                     and reassigned["case"]["state"] == original["case"]["state"]
                     and reassigned["case"]["owner_id"] == original["case"]["owner_id"]
                     and reassigned["customer"] == original["customer"]
                     and event["detail"] == {"task_id": assignment["id"], "from": assignment["assignee_id"],
                                                "to": user["id"], "reason": reason},
                     "原主管转交须只改变原assign任务负责人并保留本人员工创建事实")
            e.observe("receipt_original_UI_successor_task_handoff", {"native_api": handoff,
                        "original_business_before": original, "original_business_after": reassigned,
                        "completed_before_first_card_audit_baseline": True})
            await login_as(e, context, credentials, "reception", "business-assistant", 1)
            target = facts(e, target["case"]["id"])
            assignment = task(target, "assign")
        else:
            e.action("navigate", "进入原助手保存首项回执与后继原分派事项")
            await e.page.goto(e.origin + "/#business-assistant", wait_until="domcontentloaded")
        _require(target["case"]["state"] == "unassigned" and target["case"]["created_by"] == user["id"]
                 and target["case"]["store_id"] == 1 and assignment["assignee_id"] == user["id"]
                 and target["customer"]["name"] == name + "_后继", "本人重新登录后须读取实际可分派原任务")
        source = {"values": values, "successor": {"case_id": target["case"]["id"], "task_id": assignment["id"],
                  "case_version": target["case"]["version"], "case_number": target["case"]["number"],
                  "customer_name": target["customer"]["name"], "assignee_id": e.manifest["users"]["sales"]["id"]}}
        e.observe("receipt_original_UI_successor_source", {"native_api": response, "native_task_handoff": handoff,
                    "source": source["successor"],
                    "original_business_source": target, "completed_before_first_card_audit_baseline": True})
    await e.ready()
    before = e.business_snapshot("receipt_original_business_before_preparation")
    old = {table: e.db.rows("SELECT * FROM " + table + " ORDER BY id") for table in FLOW_TABLES}
    await e.send("回执收口 " + mode + " " + name + "\n" + json.dumps(source, ensure_ascii=False))
    sid = e.latest_session
    cards = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY created_at,id", (sid,))
    _require(len(cards) == 1 and cards[0]["status"] == "pending" and cards[0]["operation_id"] == FLOW_CREATE
             and not _decoded(cards[0]["questions"]), "原UI应恰好准备一张完整Flow卡")
    card = cards[0]
    payload = _payload(card)
    _require(payload["path_args"] == {} and payload["query"] == {} and payload["body"]["kind"] == "lead"
             and all(payload["body"]["values"].get(key) == value for key, value in values.items())
             and re.fullmatch(r"[A-Za-z0-9_-]{16,80}", payload["body"]["request_id"])
             and card["owner_id"] == user["id"] and card["store_id"] == 1,
             "原Flow待确认payload须有真实原request_id及完整员工姓名/电话/来源")
    work = e.db.rows("SELECT * FROM business_assistant_work_items WHERE id=?", (card["source_work_item_id"],))
    _require(len(work) == 1 and work[0]["status"] == "prepared" and not _confirmations(e, card["id"]), "准备不能制造确认冻结")
    plans = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE session_id=? ORDER BY id", (sid,))
    _require(len(plans) == (0 if mode == "freeze" else 1)
             and not e.db.rows("SELECT id FROM business_assistant_followup_grants WHERE session_id=?", (sid,)),
             "保存计划不等于持续跟进授权")
    if mode != "freeze":
        steps = e.db.rows("SELECT * FROM business_assistant_plan_steps WHERE plan_id=? ORDER BY position", (plans[0]["id"],))
        _require(len(steps) == 2 and steps[0]["proposal_id"] == card["id"]
                 and _decoded(steps[0]["completion_conditions"]) == [{"type": "proposal_succeeded", "proposal_id": card["id"]}]
                 and _decoded(steps[1]["depends_on"]) == ["create"]
                 and steps[1]["form_ref"] == "case:" + str(source["successor"]["case_id"]) + ":assign"
                 and _decoded(steps[1]["completion_conditions"]) == [{"type": "native_task_state",
                     "task_id": source["successor"]["task_id"], "expected_status": "done", "expected_assignee_id": None}],
                 "原事项两步须保留准确依赖和可核对的各自真实完成条件")
    e.business_unchanged(before, "receipt_original_business_after_preparation")
    shown = e.page.locator('[data-proposal="' + card["id"] + '"]')
    await shown.wait_for(state="visible")
    await expect(shown).to_contain_text(name)
    await e.snapshot("receipt-real-Flow-card-before-confirmation")
    return {"user": user, "before": before, "old": old, "session_id": sid, "card": card,
            "work": work[0], "name": name, "phone": phone, "plan": plans[0] if plans else None,
            "successor": source["successor"] if target is not None else None, "target": target}


def _arm(e, prepared, mode, *, batch=False, card=None, work=None):
    card, work = card or prepared["card"], work or prepared["work"]
    arm = {"schema": 1, "arm_id": uuid.uuid4().hex, "mode": mode, "batch": batch,
           "session_id": prepared["session_id"], "proposal_id": card["id"], "work_item_id": work["id"],
           "owner_id": card["owner_id"], "store_id": card["store_id"], "owner_role": card["owner_role"],
           "access_version": card["access_version"], "proposal_digest": card["digest"], "proposal_version": card["version"],
           "operation_id": card["operation_id"], "payload": _payload(card), "work": work,
           "name": prepared["name"], "phone": prepared["phone"]}
    runtime = Path(e.manifest["runtime_root"])
    _atomic_json(runtime / ("receipt-closeout-arm-" + arm["arm_id"] + ".json"), arm)
    _atomic_json(runtime / "receipt-closeout-active.json", arm)
    e.action("fixed_fault_arm", "仅该原卡指定边界", arm_id=arm["arm_id"], mode=mode, proposal_id=card["id"], native_ui_confirmation=not batch)
    return arm


async def _confirm_ui(e, prepared, arm):
    from playwright.async_api import expect
    path = "/api/business-assistant/sessions/" + prepared["session_id"] + "/proposals/" + prepared["card"]["id"] + "/confirm"
    async with e.page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path == path) as pending:
        await e.click('[data-ba-action="confirm"][data-id="' + prepared["card"]["id"] + '"]', "员工核对后提交原Flow一次")
    response = await pending.value
    body = await response.json()
    headers = await response.request.all_headers()
    _require(response.status == 200 and headers.get("cookie") and headers.get("x-csrf-token")
             and headers.get("x-store-id") == str(prepared["card"]["store_id"])
             and response.request.post_data_json == {"digest": prepared["card"]["digest"]}
             and len(body["confirmation_results"]) == 1 and body["confirmation_results"][0]["id"] == prepared["card"]["id"],
             "confirm真实200须保留原digest与本人Cookie/CSRF，不能称native成功")
    outcome = body["confirmation_results"][0]
    ledger = _load(Path(e.manifest["evidence_root"]) / ("receipt-closeout-fault-" + arm["arm_id"] + ".json"))
    _require(outcome["status"] == "uncertain" and ledger["injections"] == 1, "固定故障必须准确呈现结果不明")
    if arm["mode"] == "success_commit_failure":
        _require(outcome["business_status"] == "succeeded" and outcome["result_persisted"] is False
                 and ledger["phase"] == "observed_success_result_commit_failed" and ledger["native_invocations"] == 1,
                 "已观察原成功必须与助手结果未保存分别呈现")
        await expect(e.page.locator("#business-assistant-cards")).to_contain_text("原业务接口已返回成功")
    else:
        _require(outcome["result_persisted"] is True and ledger["phase"] == ("before_native_failure" if arm["mode"] == "before_invoke" else "native_committed_response_dropped")
                 and ledger["native_invocations"] == (0 if arm["mode"] == "before_invoke" else 1), "固定传输失败窗口与native次数不匹配")
    e.observe("receipt_original_confirmation_outcome", {"path": path, "native_ui": True, "http_status": 200,
                "cookie_present": True, "csrf_present": True, "outcome": outcome, "fault": ledger})
    await e.snapshot("receipt-original-confirmation-unknown")
    return body, ledger


async def _receipt_ready(e, session_id, proposal_id):
    """Wait for this original card's UI before freezing lookup evidence."""
    from playwright.async_api import expect
    await e.ready()
    selector = ('button[data-baws-action="receipt"][data-session="' + session_id
                + '"][data-proposal="' + proposal_id + '"]')
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    await expect(button).to_be_visible()
    return selector


async def _lookup_ui(e, prepared, expected, *, expected_case=None):
    receipt_selector = await _receipt_ready(e, prepared["session_id"], prepared["card"]["id"])
    path = "/api/business-assistant/sessions/" + prepared["session_id"] + "/proposals/" + prepared["card"]["id"] + "/execution-result"
    rows, items = _assistant_rows(e, prepared["session_id"]), _confirmations(e, prepared["card"]["id"])
    before = e.business_snapshot("receipt_lookup_business_before")
    async with e.page.expect_response(lambda response: response.request.method == "GET" and urlsplit(response.url).path == path) as pending:
        await e.click(receipt_selector, "员工只读核对原办理结果")
    response = await pending.value
    lookup = await response.json()
    headers = await response.request.all_headers()
    _require(response.status == 200 and lookup["status"] == expected and headers.get("cookie")
             and headers.get("x-store-id") == str(prepared["card"]["store_id"]), "原GET回执结果/本人本店不匹配")
    _require(_assistant_rows(e, prepared["session_id"]) == rows and _confirmations(e, prepared["card"]["id"]) == items,
             "回执lookup不得协调、改卡/WorkItem/Run/冻结或重放")
    e.business_unchanged(before, "receipt_lookup_business_after")
    if expected == "not_found":
        _require(lookup["reason_code"] == "native_receipt_not_found" and not lookup["object_refs"] and not lookup["evidence_refs"], "冻结无提交须真实not_found，无伪成功")
    if expected == "confirmed_success":
        receipts = e.db.rows("SELECT * FROM flow_request_receipts WHERE store_id=? AND request_key=?",
                             (prepared["card"]["store_id"], _payload(prepared["card"])["body"]["request_id"]))
        _require(len(receipts) == 1 and receipts[0]["case_id"] == expected_case
                 and receipts[0]["actor_id"] == prepared["user"]["id"], "lookup依据须是本人本店原request_id唯一真实receipt")
        case = e.db.rows("SELECT * FROM flow_cases WHERE id=?", (expected_case,))[0]
        evidence = lookup["evidence_refs"]
        _require(lookup["object_refs"] == [{"type": "case", "id": expected_case}]
                 and len(evidence) == 2 and {row["source_type"] for row in evidence} == {"object", "receipt"}
                 and all(row["observed_at"] == lookup["checked_at"] for row in evidence)
                 and any(row["source_type"] == "receipt" and row["source_id"] == {
                     "operation_id": FLOW_CREATE, "id": receipts[0]["id"]} and row["native_version"] is None for row in evidence)
                 and any(row["source_type"] == "object" and row["source_id"] == {"type": "case", "id": expected_case}
                         and row["native_version"] == case["version"] for row in evidence),
                 "Flow可靠回执须准确引用原case/receipt及同次真实版本与核对时刻")
    e.observe("receipt_original_lookup", {"method": "GET", "path": path, "http_status": 200, "native_ui": True,
                "cookie_present": True, "store_id": prepared["card"]["store_id"], "lookup": lookup,
                "whole_assistant_source_rows_unchanged": True, "whole_business_rows_unchanged": True})
    return lookup


def _flow_delta(e, prepared, ledger):
    after = e.business_snapshot("receipt_native_Flow_business_after")
    changed = {table for table in prepared["before"]["tables"] if prepared["before"]["tables"][table] != after["tables"][table]}
    _require(changed == set(FLOW_TABLES), "原Flow创建只允许Case/Customer/Task/Event/RequestReceipt/Audit六表追加")
    added = {}
    for table, previous in prepared["old"].items():
        current = {row["id"]: row for row in e.db.rows("SELECT * FROM " + table + " ORDER BY id")}
        _require(all(current.get(row["id"]) == row for row in previous), "原Flow不能覆盖旧业务事实：" + table)
        old_ids = {row["id"] for row in previous}
        added[table] = [row for key, row in current.items() if key not in old_ids]
        _require(len(added[table]) == 1, "原Flow各来源须只新增一行：" + table)
    _require(added["flow_cases"][0]["id"] == ledger["case_id"] and _digest(added["flow_request_receipts"][0]) == ledger["receipt_sha256"], "真实原case/receipt须与故障点完整来源相同")
    e.observe("receipt_original_Flow_append_only", {"appended_rows": added, "all_old_rows_whole_unchanged": True,
                "all_other_business_tables_unchanged": True, "native_invocations": 1})
    return after


async def frozen_before_native(e, context, credentials):
    prepared = await _prepare_flow(e, context, credentials, "freeze")
    arm = _arm(e, prepared, "before_invoke")
    await _confirm_ui(e, prepared, arm)
    e.business_unchanged(prepared["before"], "receipt_frozen_no_native_business_zero_change")
    items = _confirmations(e, prepared["card"]["id"])
    _require(len(items) == 1 and items[0]["status"] == "uncertain" and items[0]["error_code"] == "runtime_unavailable", "原冻结未提交须uncertain，无重试")
    await _lookup_ui(e, prepared, "not_found")
    await e.click('[data-ba-action="refresh"]', "读取原未知结果，不重新提交")
    await e.ready()
    _require(_confirmations(e, prepared["card"]["id"]) == items
             and not e.db.rows("SELECT id FROM flow_request_receipts WHERE request_key=?", (_payload(prepared["card"])["body"]["request_id"],)), "刷新不能补造原回执或重新提交")
    e.business_unchanged(prepared["before"], "receipt_frozen_after_refresh_business_zero_change")


async def _recover_followup(e, prepared, ledger, *, mismatch):
    from playwright.async_api import expect
    first_id, sid, plan_id = prepared["card"]["id"], prepared["session_id"], prepared["plan"]["id"]
    receipt_selector = None
    if mismatch:
        receipt_selector = await _receipt_ready(e, sid, first_id)
    before = e.business_snapshot("receipt_before_original_background_reconciliation")
    item_before = _confirmations(e, first_id)[0]
    gate = None
    receipt_future = None
    receipt_listener = None
    if mismatch:
        gate = {"gate_id": uuid.uuid4().hex, "session_id": sid, "proposal_id": first_id,
                "case_id": ledger["case_id"], "owner_id": prepared["user"]["id"], "store_id": prepared["card"]["store_id"]}
        _atomic_json(Path(e.manifest["runtime_root"]) / "receipt-closeout-get-gate.json", gate)
        path = "/api/business-assistant/sessions/" + sid + "/proposals/" + first_id + "/execution-result"
        receipt_future = asyncio.get_running_loop().create_future()
        def receipt_listener(response):
            if (not receipt_future.done() and response.request.method == "GET"
                    and urlsplit(response.url).path == path):
                receipt_future.set_result(response)
        e.page.on("response", receipt_listener)
        await e.click(receipt_selector, "读取原回执并保留真实在途GET")
        await e.wait(lambda: (Path(e.manifest["evidence_root"]) / ("receipt-closeout-gate-" + gate["gate_id"] + ".json")).is_file(), "原内部GET真实门控")
    try:
        await e.page.locator('[data-baws-followup="enable"]').wait_for(state="visible")
        await e.followup_click("enable", "本人明确开启此事项，依据真实原回执继续准备")
        await e.wait(lambda: e.db.rows("SELECT id FROM business_assistant_proposals WHERE id=? AND status='succeeded'", (first_id,)), "原协调器核对真实Flow回执并保存原卡", timeout=25)
        if mismatch:
            _atomic_json(Path(e.manifest["runtime_root"]) / ("receipt-closeout-gate-release-" + gate["gate_id"] + ".json"), {"gate_id": gate["gate_id"], "action": "release_original_get"})
            response = await receipt_future
            lookup = await response.json()
            _require(response.status == 200 and lookup["status"] == "mismatch" and lookup["reason_code"] == "confirmation_source_changed",
                     "原协调器真实改变source后，旧在途lookup必须mismatch而非返回过时success")
            e.observe("receipt_original_source_change_mismatch", {"lookup": lookup, "gate": gate, "native_ui": True,
                        "source_change": "original Grant reconciliation", "fabricated_receipt": False})
        await e.wait(lambda: len(e.db.rows("SELECT id FROM business_assistant_proposals WHERE session_id=? AND status='pending'", (sid,))) == 1,
                     "依据原首项回执仅准备唯一依赖后继", timeout=35)
        await e.followup_click("pause", "暂停后继准备，独立核对原协调结果")
        card = e.db.rows("SELECT * FROM business_assistant_proposals WHERE id=?", (first_id,))[0]
        items = _confirmations(e, first_id)
        work = e.db.rows("SELECT * FROM business_assistant_work_items WHERE id=?", (prepared["work"]["id"],))[0]
        _require(len(items) == 1 and items[0]["status"] == card["status"] == "succeeded" and work["status"] == "settled"
                 and all(items[0][key] == item_before[key] for key in ("id", "proposal_id", "work_item_id", "run_id", "item_key", "attempt_no", "submission_snapshot", "submission_digest", "created_at", "started_at")),
                 "原协调器只核对既有确认，不更换或新增原冻结/请求")
        result = _decoded(card["result"])
        record = result["reconciliation"]
        _require(record["status"] == "confirmed_success" and record["confirmation_id"] == item_before["id"]
                 and record["submission_digest"] == item_before["submission_digest"]
                 and record["object_refs"] == [{"type": "case", "id": ledger["case_id"]}], "原协调记录须引用准确既有确认和真实原单")
        pending = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? AND status='pending'", (sid,))
        successor = prepared["successor"]
        _require(len(pending) == 1 and pending[0]["operation_id"] == FLOW_ACTION
                 and _payload(pending[0])["path_args"] == {"case_id": successor["case_id"], "action": "assign"}
                 and _payload(pending[0])["body"]["version"] == successor["case_version"]
                 and _payload(pending[0])["body"]["values"] == {"assignee_id": successor["assignee_id"]}
                 and not _confirmations(e, pending[0]["id"]), "依赖后继仍为原待确认卡，绝不自动确认")
        e.business_unchanged(before, "receipt_original_reconciliation_and_successor_no_native_writes")
        _require(_digest(e.db.rows("SELECT * FROM flow_request_receipts WHERE id=?", (ledger["receipt_id"],))[0]) == ledger["receipt_sha256"], "原回执整行不得改写")
        await e.click('[data-ba-action="refresh"]', "读取后继实际原卡")
        await e.ready()
        await e.click('[data-ba-action="queue-filter"][data-filter="pending"]', "员工查看依赖后继待确认卡")
        await expect(e.page.locator("#business-assistant-cards")).to_contain_text(prepared["name"] + "_后继")
        await e.snapshot("receipt-original-reconciliation-dependent-pending")
        e.observe("receipt_original_coordinator_recovery", {"plan_id": plan_id, "proposal_id": first_id,
                    "confirmation_id": items[0]["id"], "work_item_id": work["id"], "receipt_id": ledger["receipt_id"],
                    "original_frozen_immutable": True, "coordinator_real_success_saved": True,
                    "successor_pending_id": pending[0]["id"], "successor_original_source": successor,
                    "successor_confirmations": 0, "original_business_unchanged": True})
        await e.click('[data-baws-followup="revoke"]', "结束本次独立回执事项第一次核对")
        await expect(e.page.locator('[data-baws-followup="revoke"]')).to_have_text("确认结束这件事")
        await e.followup_click("revoke", "本人确认结束本次回执事项")
    finally:
        if receipt_listener is not None:
            e.page.remove_listener("response", receipt_listener)
        if receipt_future is not None and not receipt_future.done():
            receipt_future.cancel()
            await asyncio.gather(receipt_future, return_exceptions=True)


async def observed_success_storage_failure(e, context, credentials):
    prepared = await _prepare_flow(e, context, credentials, "storage")
    arm = _arm(e, prepared, "success_commit_failure")
    _, ledger = await _confirm_ui(e, prepared, arm)
    _flow_delta(e, prepared, ledger)
    card = e.db.rows("SELECT * FROM business_assistant_proposals WHERE id=?", (prepared["card"]["id"],))[0]
    items = _confirmations(e, card["id"])
    _require(card["status"] == "executing" and len(items) == 1 and items[0]["status"] == "running"
             and items[0]["submission_digest"] == ledger["submission_digest"], "助手结果commit失败必须保留原durable executing/running冻结")
    await _lookup_ui(e, prepared, "confirmed_success", expected_case=ledger["case_id"])
    await _recover_followup(e, prepared, ledger, mismatch=True)


async def lost_response_reliable_recovery(e, context, credentials):
    prepared = await _prepare_flow(e, context, credentials, "recovery")
    arm = _arm(e, prepared, "lost_response")
    _, ledger = await _confirm_ui(e, prepared, arm)
    _flow_delta(e, prepared, ledger)
    items = _confirmations(e, prepared["card"]["id"])
    _require(len(items) == 1 and items[0]["status"] == "uncertain", "实际原201返回丢失须保持uncertain直到真实核对")
    await _lookup_ui(e, prepared, "confirmed_success", expected_case=ledger["case_id"])
    await _recover_followup(e, prepared, ledger, mismatch=False)


async def _batch_http(e, context, credentials, mode):
    from runtime_batch import _prepare, _business_delta
    prepared = await _prepare(e, context, credentials, mode)
    cards, sid = prepared["cards"], prepared["session_id"]
    arm = None
    if mode == "unknown":
        selected = {"session_id": sid, "name": prepared["values"][1]["name"], "phone": prepared["values"][1]["phone"]}
        arm = _arm(e, selected, "lost_response", batch=True, card=cards[1], work=prepared["works"][1])
    cookies = {row["name"]: row["value"] for row in await context.cookies()}
    _require(cookies.get("dealer_session") and cookies.get("dealer_csrf"), "独立batch合同须沿本次浏览器真实身份")
    path = "/api/business-assistant/sessions/" + sid + "/proposals/batch"
    payload = {"action": "confirm", "items": [{"id": card["id"], "digest": card["digest"]} for card in cards]}
    e.action("employee_http_contract", "员工已核对三张原卡后提交原batch HTTP合同一次", method="POST", path=path,
             native_ui=False, cookie_present=True, csrf_present=True, store_id=prepared["run"]["store_id"])
    response = await context.request.post(e.origin + path, data=payload,
        headers={"X-CSRF-Token": cookies["dealer_csrf"], "X-Store-ID": str(prepared["run"]["store_id"])})
    body = await response.json()
    expected = ["succeeded", "failed" if mode == "rule" else "uncertain", "skipped"]
    _require(response.status == 200 and body["batch"]["total"] == 3 and body["batch"]["done"] == 1 and body["batch"]["stopped"] is True
             and [item["id"] for item in body["batch"]["items"]] == [card["id"] for card in cards]
             and [item["status"] for item in body["batch"]["items"]] == expected, "原batch HTTP须完整三行首故障停止并C skipped")
    final = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id", (sid,))
    _require([row["id"] for row in final] == [card["id"] for card in cards]
             and [row["status"] for row in final] == expected[:2] + ["pending"] and final[2] == cards[2]
             and e.db.rows("SELECT * FROM business_assistant_work_items WHERE id=?", (prepared["works"][2]["id"],)) == [prepared["works"][2]]
             and not _confirmations(e, cards[2]["id"]), "本次skipped不能改变C原卡/WorkItem或制造确认")
    _business_delta(e, prepared, 1 if mode == "rule" else 2)
    if arm:
        ledger = _load(Path(e.manifest["evidence_root"]) / ("receipt-closeout-fault-" + arm["arm_id"] + ".json"))
        _require(ledger["phase"] == "native_committed_response_dropped" and ledger["native_invocations"] == ledger["injections"] == 1,
                 "原batch B unknown只能来自真实201后丢返回一次")
        e.observe("batch_http_actual_B_committed_response_lost", ledger)
    e.observe("batch_original_HTTP_contract", {"path": path, "method": "POST", "http_status": response.status,
                "native_ui": False, "preparation_native_ui": True, "cookie_present": True, "csrf_present": True,
                "store_id": prepared["run"]["store_id"], "result": body["batch"], "C_whole_original_card_and_work_unchanged": True})
    before = e.business_snapshot("batch_HTTP_business_before_refresh")
    await e.click('[data-ba-action="refresh"]', "原页面读取batch结果，不重放合同")
    await e.ready()
    e.business_unchanged(before, "batch_HTTP_business_after_refresh")
    await e.snapshot("batch-HTTP-" + mode + "-C-pending-no-replay")


async def backend_batch_rule_stops(e, context, credentials):
    await _batch_http(e, context, credentials, "rule")


async def backend_batch_unknown_stops(e, context, credentials):
    await _batch_http(e, context, credentials, "unknown")


RECEIPT_SCENARIOS = (
    ("runtime-confirm-frozen-before-native-not-found", frozen_before_native, 120),
    ("runtime-Flow-observed-success-result-save-failure-mismatch", observed_success_storage_failure, 180),
    ("runtime-Flow-lost-response-reliable-receipt-followup", lost_response_reliable_recovery, 180),
    ("runtime-backend-batch-rule-stops-skipped", backend_batch_rule_stops, 120),
    ("runtime-backend-batch-unknown-stops-skipped", backend_batch_unknown_stops, 120),
)
