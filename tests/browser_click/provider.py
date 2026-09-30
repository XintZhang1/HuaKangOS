"""Deterministic model replies; original tools, APIs and transactions stay real."""
import asyncio
from contextlib import contextmanager
import ipaddress
import json
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
            message = steps[calls]
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
            return httpx.Response(200, content=payload + "data: [DONE]\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"index": 0, "message": message,
                             "finish_reason": finish}], "usage": usage})

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
