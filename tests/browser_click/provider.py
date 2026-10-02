"""Deterministic model replies; original tools, APIs and transactions stay real."""
import asyncio
from contextlib import contextmanager
import ipaddress
import json
from pathlib import Path
import re
import socket
from unittest.mock import patch

import httpx


def tool(name, arguments, ident="browser_click_tool"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": ident, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}


def reply(text):
    return {"role": "assistant", "content": text}


@contextmanager
def local_network_only(record):
    """Reject non-loopback DNS/connect attempts, including connect_ex callers."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def allowed(host):
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if host in (None, "localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def check(host):
        if not allowed(host):
            record["blocked_external_attempts"] += 1
            raise RuntimeError("External network is disabled in synthetic browser validation")

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(address[0])
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            check(address[0])
        return original_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        check(host)
        return original_getaddrinfo(host, *args, **kwargs)

    with patch.object(socket.socket, "connect", connect), \
            patch.object(socket.socket, "connect_ex", connect_ex), \
            patch.object(socket, "getaddrinfo", getaddrinfo):
        yield


class SyntheticProvider:
    def __init__(self, manifest):
        self.manifest = manifest
        self.counts = {"synthetic_requests": 0, "real_model_calls": 0,
                       "blocked_external_attempts": 0, "requests": []}

    async def _inflight_stop_response(self, context, messages, name):
        """Hold only this named second customer reply; never write app rows."""
        from runtime_faults import _atomic_json, _digest, _load, _rows, _utc

        trigger = context.get("trigger", {})
        run_id = trigger.get("run_id")
        if (trigger.get("kind") != "user"
                or trigger.get("background_is_not_new_employee_instruction")
                or not isinstance(run_id, str)
                or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", run_id)
                or not re.fullmatch(r"浏览器客户cancel_[0-9a-f]{12}", name)):
            raise RuntimeError("In-flight stop requires its unique explicit login Run")
        prior = [message for message in messages if message["role"] == "tool"]
        if (len(prior) != 1 or prior[0].get("tool_call_id") != "inspect_customer"
                or json.loads(prior[0]["content"]).get("status") != 200):
            raise RuntimeError("In-flight stop requires the original successful customer inspection")
        rows = _rows(self.manifest["database_path"], "SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))
        inspections = _rows(self.manifest["database_path"],
            "SELECT * FROM business_assistant_run_items WHERE run_id=? AND kind='tool' ORDER BY id", (run_id,))
        if (len(rows) != 1 or len(inspections) != 1 or rows[0]["status"] != "running"
                or rows[0]["stop_requested"] or rows[0]["auth_kind"] != "login"
                or inspections[0]["tool_name"] != "inspect_business_form"
                or inspections[0]["status"] != "succeeded"):
            raise RuntimeError("In-flight stop stage has no real running inspected source")
        original = rows[0]
        runtime = Path(self.manifest["runtime_root"])
        stage_path = runtime / ("inflight-stop-" + run_id + ".json")
        release_path = runtime / ("inflight-stop-" + run_id + "-release.json")
        if stage_path.exists() or release_path.exists():
            raise RuntimeError("In-flight stop cannot reuse an earlier stage or release")
        stage = {"schema": 1, "stage_id": name, "phase": "waiting_before_prepare_response",
                 "run_id": run_id, "session_id": original["session_id"], "owner_id": original["owner_id"],
                 "store_id": original["store_id"], "request_id": original["request_id"],
                 "fence": original["fence"], "attempt": original["attempt"], "version": original["version"],
                 "inspect_item_id": inspections[0]["id"], "inspect_sha256": _digest(inspections[0]),
                 "tools_before_response": 1, "response_tool": "prepare_business_form",
                 "synthetic_request_index": self.counts["synthetic_requests"] + 1,
                 "started_at": _utc(), "gate_seconds": 15, "returned_after_stop": False}
        _atomic_json(stage_path, stage)
        deadline = asyncio.get_running_loop().time() + stage["gate_seconds"]
        release = {"schema": 1, "stage_id": name, "run_id": run_id, "session_id": original["session_id"],
                   "action": "return_prepare_response"}
        try:
            while asyncio.get_running_loop().time() < deadline:
                if release_path.is_file():
                    if _load(release_path) != release:
                        raise RuntimeError("In-flight stop received an unrelated release")
                    latest = _rows(self.manifest["database_path"],
                        "SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))[0]
                    same = ("session_id", "owner_id", "store_id", "request_id", "fence", "attempt", "lease_owner")
                    if (latest["status"] != "running" or not latest["stop_requested"]
                            or any(latest[key] != original[key] for key in same)):
                        raise RuntimeError("Synthetic reply can return only after this Run's real stop request")
                    stage.update(stop_requested_observed=True, stop_version=latest["version"], released_at=_utc())
                    return stage_path, stage
                await asyncio.sleep(0.025)
            stage.update(phase="gate_timeout", failed_at=_utc())
            _atomic_json(stage_path, stage)
            raise RuntimeError("In-flight stop response gate exceeded its fixed deadline")
        except asyncio.CancelledError:
            stage.update(phase="heartbeat_aborted", aborted_at=_utc(), abort_signal="asyncio.CancelledError",
                         cancellation_origin_not_instrumented=True)
            _atomic_json(stage_path, stage)
            raise
        except Exception as error:
            if stage["phase"] != "gate_timeout":
                stage.update(phase="gate_failed", error_type=type(error).__name__, failed_at=_utc())
                _atomic_json(stage_path, stage)
            raise

    async def handle(self, request):
        if (request.url.scheme, request.url.host, request.url.path) != (
                "https", "api.deepseek.com", "/chat/completions"):
            raise RuntimeError("Unexpected provider request in browser validation")
        body = json.loads(request.content)
        messages = body["messages"]
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1]) \
            if marker in messages[0]["content"] else {}
        text = next((m["content"] for m in reversed(messages) if m["role"] == "user"),
                    next((m["content"] for m in reversed(context.get("recent_messages", []))
                          if m["role"] == "user"), ""))
        calls = sum(m["role"] == "tool" for m in messages)
        stop_stage = None
        background = context.get("trigger", {}).get("background_is_not_new_employee_instruction")
        if "慢速查询" in text and not calls:
            await asyncio.sleep(2)
        if "模拟异常" in text:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "invalid_protocol", "type": "function", "function": {
                    "name": "prepare_business_form", "arguments": '{"broken":'}}]}
        elif "浏览器接待计划" in text:
            plan = self.manifest["lead_plan"]
            if not calls and not background:
                steps = [{"key": "assign_" + str(index), "title": "分派第" + str(index + 1) + "项接待",
                          "object_ref": {"type": "case", "id": case_id},
                          "form_ref": f"case:{case_id}:assign",
                          "depends_on": ["assign_0"] if index else [],
                          "conditions": [{"type": "native_action_available",
                                          "object_ref": {"type": "case", "id": case_id},
                                          "action_key": "assign"}],
                          "completion_conditions": [{"type": "native_task_state",
                                                     "task_id": plan["task_ids"][index],
                                                     "expected_status": "done"}]}
                         for index, case_id in enumerate(plan["case_ids"])]
                message = tool("save_work_plan", {"schema_version": 2,
                               "goal": "浏览器接待计划", "steps": steps})
            elif not calls:
                from app.db import SessionLocal
                from app.flow_models import Case
                with SessionLocal() as db:
                    waiting = next((ident for ident in plan["case_ids"]
                                    if db.get(Case, ident).state == "unassigned"), None)
                if waiting is None:
                    raise RuntimeError("Finished synthetic plan requested another preparation")
                message = tool("prepare_business_form", {
                    "form_ref": f"case:{waiting}:assign",
                    "values": {"assignee_id": plan["assignee_id"]}, "summary": "分派接待"})
            else:
                message = reply("事项已准备，请核对。")
        elif "浏览器批量rule_" in text or "浏览器批量unknown_" in text:
            matched = re.fullmatch(r"新建客户批量 (浏览器批量(rule|unknown)_[0-9a-f]{12})\n(.+)", text, re.DOTALL)
            if not matched or background:
                raise RuntimeError("Synthetic batch requires one explicit employee group and complete rows")
            group, mode = matched.group(1), matched.group(2)
            data = json.loads(matched.group(3))
            if not isinstance(data, dict) or set(data) != {"rows"} or not isinstance(data["rows"], list) or len(data["rows"]) != 3:
                raise RuntimeError("Synthetic batch must preserve all three supplied rows")
            rows = data["rows"]
            for index, row in enumerate(rows):
                if (not isinstance(row, dict) or set(row) != {"name", "phone", "contact_allowed", "confirm_new_customer"}
                        or row["name"] != group + "_" + "ABC"[index]
                        or not isinstance(row["phone"], str) or not re.fullmatch(r"199[0-9]{8}", row["phone"])
                        or row["contact_allowed"] is not False or row["confirm_new_customer"] is not False):
                    raise RuntimeError("Synthetic customer batch requires exact source names, phones and explicit false choices")
            phones = [row["phone"] for row in rows]
            if ((mode == "rule" and not (phones[0] == phones[1] and phones[2] != phones[0]))
                    or (mode == "unknown" and len(set(phones)) != 3)):
                raise RuntimeError("Synthetic batch phones do not match the named fault contract")
            steps = [tool("inspect_business_form", {"form_ref": "crm:customers"}, "inspect_batch_customers"),
                     tool("prepare_business_batch", {"form_ref": "crm:customers", "step": group,
                          "rows": [{"values": row, "summary": "新建客户：" + row["name"]} for row in rows]},
                          "prepare_batch_customers"),
                     reply("三项客户档案已准备，请逐项核对本组。")]
            if calls >= len(steps):
                raise RuntimeError("Synthetic batch protocol exhausted")
            message = steps[calls]
        elif "新建客户" in text:
            matched = re.search(r"浏览器客户[A-Za-z0-9_-]+", text)
            if not matched:
                raise RuntimeError("The customer scenario requires an explicit synthetic name")
            name = matched.group(0)
            steps = [tool("inspect_business_form", {"form_ref": "crm:customers"}, "inspect_customer"),
                     tool("prepare_business_form", {"form_ref": "crm:customers",
                          "values": {"name": name, "contact_allowed": False},
                          "summary": "新建客户：" + name}, "prepare_customer"),
                     reply("客户档案已准备，请核对。")]
            if calls >= len(steps):
                raise RuntimeError("Synthetic customer protocol exhausted")
            recovered = [card for card in context.get("plans_cards_tasks", {}).get("cards", [])
                         if card.get("status") == "pending" and card.get("source_work_item_id")
                         and card.get("summary") == "新建客户：" + name]
            if name.startswith("浏览器客户crash_") and recovered:
                if len(recovered) != 1 or not context.get("trigger", {}).get("run_id"):
                    raise RuntimeError("Synthetic crash recovery requires one source-backed pending card")
                message = reply("原客户档案卡已保留，仍待员工核对确认。")
            else:
                message = steps[calls]
                if name.startswith("浏览器客户cancel_") and calls == 1:
                    stop_stage = await self._inflight_stop_response(context, messages, name)
        elif not calls:
            message = tool("find_business_objects", {"kind": "customer", "query": "张"})
        else:
            result = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
            if result.get("status") == 200:
                labels = [item["label"] for item in result.get("data", {}).get("items", [])]
                message = reply("本店客户：" + "、".join(labels) + "。" if labels else "未找到匹配客户。")
            else:
                message = reply("本次查询未完成。")
        self.counts["synthetic_requests"] += 1
        self.counts["requests"].append({"tools": calls, "stream": bool(body.get("stream")),
                                         "background": bool(background)})
        finish = "tool_calls" if message.get("tool_calls") else "stop"
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        if body.get("stream"):
            packets = [{"choices": [{"index": 0, "delta": {"role": "assistant",
                         "content": message.get("content") or ""}, "finish_reason": None}]}]
            packets.extend({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": index, **call}]},
                                        "finish_reason": None}]}
                           for index, call in enumerate(message.get("tool_calls", [])))
            packets.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage})
            payload = "".join("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n" for packet in packets)
            response = httpx.Response(200, content=payload + "data: [DONE]\n\n",
                                      headers={"content-type": "text/event-stream"})
        else:
            response = httpx.Response(200, json={"choices": [{"index": 0, "message": message,
                                 "finish_reason": finish}], "usage": usage})
        if stop_stage is not None:
            from runtime_faults import _atomic_json, _utc
            path, stage = stop_stage
            stage.update(phase="returned_after_stop", returned_after_stop=True, returned_at=_utc(), response_status=response.status_code)
            _atomic_json(path, stage)
        return response

    @contextmanager
    def installed(self):
        provider = self
        original_client = httpx.AsyncClient

        class SyntheticClient(original_client):
            def __init__(self, *args, **kwargs):
                # Explicit internal ASGI transports are the application's real tool gateway.
                if kwargs.get("transport") is None:
                    kwargs["transport"] = httpx.MockTransport(provider.handle)
                super().__init__(*args, **kwargs)

        with patch.object(httpx, "AsyncClient", SyntheticClient):
            yield
