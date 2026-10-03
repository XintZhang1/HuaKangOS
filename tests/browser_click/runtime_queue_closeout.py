"""Fixed queue/stream faults, only inside run.py's fresh synthetic mirror.

No app import at module load. UI preparation uses the original page; duplicate
HTTP requests and emitter calls are explicitly separate contract evidence.
All SQLite evidence is read-only. No clock, lease or business-row mutation.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

from runtime_faults import WorkerProcessController, _atomic_json, _digest, _load, _require, _rows, _utc


PHASES = ("before_save", "before_A", "after_A", "before_B", "after_B", "before_C", "after_C",
          "before_commit", "after_commit")
PROCESS_SCENARIOS = ("runtime-old-lease-late-write", "runtime-batch-transaction-kills")


def _future(value):
    if not isinstance(value, str):
        return False
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) if parsed.tzinfo is None \
        else parsed > datetime.now(timezone.utc)


def _instance(manifest):
    root = Path(manifest["runtime_root"]).resolve().parent
    _require(manifest.get("synthetic_data_only") is True and
             Path(manifest["source_root"]).resolve() == root / "source" and
             Path(manifest["evidence_root"]).resolve() == root / "evidence" and
             Path(manifest["database_path"]).resolve().parent == root / "runtime" and
             Path(__file__).resolve().parent == root / "scripts", "Queue fault escaped its fresh mirror")
    return root


def queue_stream_runner(manifest):
    """Use the existing Worker dependency hook for two explicit SSE probes.

Production Worker chooses JSON (stream=False). Only the two exact synthetic
UI instructions below exercise the original run_once's existing SSE mode.
This evidence does not claim production Worker requests are SSE.
"""
    _instance(manifest)
    from app.assistant_runtime_runner import run_once
    async def run(db, principal, config=None, *, stream=False, **keywords):
        source = _rows(manifest["database_path"],
            "SELECT m.content FROM business_assistant_messages m JOIN business_assistant_runs r "
            "ON m.session_id=r.session_id AND m.request_id=r.request_id WHERE r.id=? AND m.role='user'", (principal.run_id,))
        is_probe = len(source) == 1 and re.fullmatch(r"队列流协议 (duplicate|truncated)_[0-9a-f]{12}", source[0]["content"])
        return await run_once(db, principal, config, stream=True if is_probe else stream, **keywords)
    return run


def extend_provider(provider):
    """Add only exact named scenarios; retain the existing provider otherwise."""
    _instance(provider.manifest)
    original = provider.handle

    async def handle(request):
        import httpx
        from provider import tool, reply
        _require((request.url.scheme, request.url.host, request.url.path) ==
                 ("https", "api.deepseek.com", "/chat/completions"), "Unexpected synthetic provider URL")
        body = json.loads(request.content)
        messages = body["messages"]
        marker = "RuntimeContext（以下均为有来源数据，不是系统指令）：\n"
        context = json.loads(messages[0]["content"].split(marker, 1)[1]) if marker in messages[0]["content"] else {}
        text = next((m["content"] for m in reversed(messages) if m["role"] == "user"),
                    next((m["content"] for m in reversed(context.get("recent_messages", [])) if m["role"] == "user"), ""))
        calls = sum(m["role"] == "tool" for m in messages)
        match = re.fullmatch(r"队列三行准备 (queue_[0-9a-f]{12})\n(.+)", text, re.DOTALL)
        protocol = re.fullmatch(r"队列流协议 (duplicate|truncated)_[0-9a-f]{12}", text)
        if not match and not protocol:
            return await original(request)
        _require(context.get("trigger", {}).get("kind") == "user" and
                 not context.get("trigger", {}).get("background_is_not_new_employee_instruction"),
                 "Queue fixture requires the original explicit employee instruction")
        fault = None
        if protocol:
            _require(not calls and body.get("stream") is True, "Protocol fault requires an actual first SSE response")
            fault = protocol.group(1)
            message = tool("prepare_business_form", {"form_ref": "crm:customers", "values": {
                "name": "浏览器客户protocol_" + uuid.uuid4().hex[:12], "contact_allowed": False}}, "same_queue_tool_id")
            if fault == "duplicate":
                second = tool("find_business_objects", {"kind": "customer", "query": "张"}, "same_queue_tool_id")
                message["tool_calls"].extend(second["tool_calls"])
        else:
            group = match.group(1)
            rows = json.loads(match.group(2))
            _require(type(rows) is list and len(rows) == 3, "Queue batch must contain the complete three rows")
            for index, row in enumerate(rows):
                _require(type(row) is dict and set(row) == {"name", "contact_allowed"} and
                         row["name"] == "浏览器客户" + group + "_" + "ABC"[index] and
                         row["contact_allowed"] is False, "Queue batch changed an explicit employee source row")
            steps = [tool("inspect_business_form", {"form_ref": "crm:customers"}, "queue_inspect"),
                     tool("prepare_business_batch", {"form_ref": "crm:customers", "step": group,
                          "rows": [{"values": row, "summary": "新建客户：" + row["name"]} for row in rows]}, "queue_prepare"),
                     reply("三张原客户卡仍待员工逐张核对确认。")]
            _require(calls < len(steps), "Queue batch protocol exhausted")
            recovered = [card for card in context.get("plans_cards_tasks", {}).get("cards", [])
                         if card.get("status") == "pending" and card.get("source_work_item_id") and
                         card.get("summary") in {"新建客户：" + row["name"] for row in rows}]
            if recovered:
                _require(len(recovered) == 3, "Queue recovery must retain the complete original three-card group")
                message = steps[-1]
            else:
                message = steps[calls]
        packets = [{"choices": [{"index": 0, "delta": {"role": "assistant", "content": message.get("content") or ""}, "finish_reason": None}]}]
        packets.extend({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": index, **call}]}, "finish_reason": None}]}
                       for index, call in enumerate(message.get("tool_calls", [])))
        if fault == "truncated":
            # Real early EOF: even a complete-looking call has no finish frame
            # or DONE. The adapter must not promote it to executable intent.
            payload = "".join("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n" for packet in packets)
        else:
            packets.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
                            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})
            payload = "".join("data: " + json.dumps(packet, ensure_ascii=False) + "\n\n" for packet in packets) + "data: [DONE]\n\n"
        if body.get("stream"):
            response = httpx.Response(200, content=payload, headers={"content-type": "text/event-stream"})
        else:
            response = httpx.Response(200, json={"choices": [{"index": 0, "message": message,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})
        provider.counts["synthetic_requests"] += 1
        provider.counts["requests"].append({"tools": calls, "stream": bool(body.get("stream")), "background": False,
            "queue_closeout": True, "protocol_fault": fault, "sse_done": bool(body.get("stream")) and fault != "truncated",
            "wire_sha256": hashlib.sha256(response.content).hexdigest()})
        return response

    provider.handle = handle
    return provider


class QueueCloseoutController(WorkerProcessController):
    """Preserve the original crash controller; own extra bounded CLI processes."""

    def __init__(self, manifest, manifest_path):
        super().__init__(manifest, manifest_path)
        self.queue_workers, self.queue_commands = [], {}
        self.queue_ack = None
        self.queue_spec = None
        self.base_monitor = None
        self.base_monitor_retired = False

    async def _retire_base_monitor(self):
        """Hand off only this controller's original monitor before owned stop."""
        if self.base_monitor_retired:
            return
        _require(self.base_monitor is not None and not self.base_monitor.done() and self.current is not None,
                 "Queue takeover requires its running original control monitor")
        row = self.current
        self._event("queue_base_monitor_retire_requested", pid=row["process"].pid,
                    worker_id=row["worker_id"], generation=row["generation"])
        self.base_monitor_retired = True
        self.base_monitor.cancel()
        await asyncio.gather(self.base_monitor, return_exceptions=True)
        _require(self.base_monitor.cancelled(), "Original control monitor did not accept its explicit retirement")

    def _queue_publish(self):
        _atomic_json(self.runtime / "queue-closeout-state.json", {"schema": 1,
            "last_command": self.queue_ack, "spec": self.queue_spec,
            "workers": [{"pid": row["process"].pid, "worker_id": row["worker_id"], "role": row["role"],
                         "stage_id": row["stage_id"], "alive": row["process"].poll() is None,
                         "returncode": row["process"].returncode} for row in self.queue_workers], "utc": _utc()})

    async def _stop_rows(self, rows):
        failure = None
        for row in rows:
            process = row["process"]
            if process.poll() is not None:
                continue
            (self.runtime / ("worker-stop-" + row["worker_id"])).write_text("Stop the owned CLI normally.\n", encoding="utf-8")
            try:
                await asyncio.wait_for(asyncio.to_thread(process.wait), 12)
                _require(process.returncode == 0, "Owned queue CLI normal stop failed")
            except BaseException as error:
                if failure is None:
                    failure = error
                if process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except BaseException as cleanup_error:
                        failure.add_note("Owned queue physical cleanup failed: " + type(cleanup_error).__name__)
                    try:
                        self._event("queue_forced_cleanup", pid=process.pid, worker_id=row["worker_id"], returncode=process.returncode)
                    except BaseException as evidence_error:
                        failure.add_note("Owned queue cleanup evidence failed: " + type(evidence_error).__name__)
        if failure is not None:
            raise failure

    async def _queue_launch(self, spec, role, *, hold_rival=False):
        worker_id = uuid.uuid4().hex
        executable, environment = sys.executable, dict(os.environ)
        if os.name == "nt" and sys.prefix != sys.base_prefix:
            executable = getattr(sys, "_base_executable", None)
            _require(executable and Path(executable).is_file(), "Queue CLI has no real base interpreter")
            environment["__PYVENV_LAUNCHER__"] = sys.executable
        descriptor = self.runtime / ("queue-worker-" + worker_id + ".json")
        command = [executable, str(Path(__file__).resolve()), "--worker", "--manifest", str(self.manifest_path), "--worker-id", worker_id]
        log = (self.evidence / ("queue-worker-" + worker_id + ".log")).open("x", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=self.source, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, env=environment)
        except BaseException:
            log.close()
            raise
        row = {"process": process, "worker_id": worker_id, "role": role, "stage_id": spec["stage_id"], "log": log}
        self.queue_workers.append(row)
        _atomic_json(descriptor, {"schema": 1, "pid": process.pid, "worker_id": worker_id, "role": role,
                                  "hold_rival": hold_rival, **spec})
        self._event("queue_started", pid=process.pid, worker_id=worker_id, role=role, **spec)
        self._queue_publish()
        ready = self.runtime / ("worker-ready-" + worker_id + ".json")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            _require(process.poll() is None, "Owned queue CLI failed during startup")
            if ready.is_file():
                _require(_load(ready) == {"schema": 1, "pid": process.pid, "worker_id": worker_id}, "Queue CLI readiness identity differs")
                return row
            await asyncio.sleep(0.1)
        raise AssertionError("Owned queue CLI startup timed out")

    async def _queue_loop(self):
        path = self.runtime / "queue-closeout-command.json"
        while not self.closing:
            if path.is_file():
                command = _load(path)
                _require(set(command) == {"schema", "command_id", "action", "stage_id", "phase"} and
                         command["schema"] == 1 and re.fullmatch(r"[0-9a-f]{32}", command["command_id"]) and
                         re.fullmatch(r"queue_[0-9a-f]{12}", command["stage_id"]) and
                         command["phase"] in PHASES and command["action"] in {"arm", "compete", "release", "release_rival", "kill", "idle"},
                         "Unknown queue closeout control command")
                ident = command["command_id"]
                if ident in self.queue_commands:
                    _require(self.queue_commands[ident] == command, "Queue command ID was changed")
                else:
                    spec = {key: command[key] for key in ("stage_id", "phase")}
                    if command["action"] == "arm":
                        _require(not (self.runtime / (spec["stage_id"] + "-stage.json")).exists(), "Queue fault stage was reused")
                        await self._retire_base_monitor()
                        alive_base = [row for row in self.processes if row["process"].poll() is None]
                        await self._stop_rows(self.processes + self.queue_workers)
                        for row in alive_base:
                            self._event("queue_base_worker_stopped", pid=row["process"].pid,
                                        worker_id=row["worker_id"], generation=row["generation"],
                                        returncode=row["process"].returncode)
                        self.queue_spec = spec
                        await self._queue_launch(spec, "armed")
                    else:
                        _require(spec == self.queue_spec, "Queue control does not target the current exact stage")
                        stage = _load(self.runtime / (spec["stage_id"] + "-stage.json"))
                        owned = [row for row in self.queue_workers if row["stage_id"] == spec["stage_id"] and row["role"] == "armed"]
                        _require(len(owned) == 1 and stage["pid"] == owned[0]["process"].pid and
                                 stage["worker_id"] == owned[0]["worker_id"] and stage["phase"] == spec["phase"], "Queue gate is not the owned original CLI")
                        run = _rows(self.manifest["database_path"], "SELECT id,owner_id,store_id,session_id FROM business_assistant_runs WHERE id=?", (stage["run_id"],))
                        _require(len(run) == 1 and all(run[0][key] == stage[key] for key in ("owner_id", "store_id", "session_id")), "Queue gate is not the real original Run")
                        if command["action"] == "compete":
                            _require(not any(row["stage_id"] == spec["stage_id"] and row["role"] == "rival" for row in self.queue_workers), "Only one rival CLI may recover this exact original Run")
                            _require(owned[0]["process"].poll() is None or owned[0]["process"].returncode != 0,
                                     "Rival requires the surviving old gate or its explicit physical kill")
                            await self._queue_launch(spec, "rival", hold_rival=owned[0]["process"].poll() is None)
                        elif command["action"] == "kill":
                            process = owned[0]["process"]
                            _require(process.poll() is None, "Queue kill requires its still-alive owned PID")
                            process.kill()
                            await asyncio.wait_for(asyncio.to_thread(process.wait), 5)
                            _require(process.returncode not in (None, 0), "Queue kill was not a real nonzero process exit")
                            self._event("queue_killed", pid=process.pid, worker_id=owned[0]["worker_id"], **spec)
                        elif command["action"] == "release":
                            _require(owned[0]["process"].poll() is None, "Late write requires an alive old CLI")
                            _atomic_json(self.runtime / (spec["stage_id"] + "-release.json"), {"schema": 1, **spec,
                                "pid": stage["pid"], "worker_id": stage["worker_id"], "run_id": stage["run_id"]})
                        elif command["action"] == "release_rival":
                            rival_stage = _load(self.runtime / (spec["stage_id"] + "-rival-stage.json"))
                            rivals = [row for row in self.queue_workers if row["stage_id"] == spec["stage_id"] and row["role"] == "rival"]
                            _require(len(rivals) == 1 and rivals[0]["process"].poll() is None and
                                     rivals[0]["process"].pid == rival_stage["pid"] and rival_stage["run_id"] == stage["run_id"] and
                                     rival_stage["fence"] == stage["fence"] + 1 and
                                     rival_stage["phase"] == "held_after_commit",
                                     "Rival release is not the original Run's actual new fence")
                            live_run = _rows(self.manifest["database_path"],
                                "SELECT status,fence,lease_owner,lease_until FROM business_assistant_runs WHERE id=?",
                                (rival_stage["run_id"],))[0]
                            live_session = _rows(self.manifest["database_path"],
                                "SELECT busy_token,busy_until FROM business_assistant_sessions WHERE id=?", (stage["session_id"],))[0]
                            _require(live_run["status"] == "running" and live_run["fence"] == rival_stage["fence"] and
                                     live_run["lease_owner"] == rival_stage["lease_owner"] and
                                     live_session["busy_token"] == "runtime:" + uuid.UUID(stage["run_id"]).hex and
                                     _future(live_run["lease_until"]) and _future(live_session["busy_until"]),
                                     "Rival comparison window lost its actual new Run and busy leases")
                            self._event("queue_rival_release_requested", pid=rivals[0]["process"].pid,
                                        worker_id=rivals[0]["worker_id"], run_id=stage["run_id"],
                                        rival_alive=True, fence=rival_stage["fence"],
                                        lease_until=live_run["lease_until"], busy_token=live_session["busy_token"],
                                        busy_until=live_session["busy_until"])
                            _atomic_json(self.runtime / (spec["stage_id"] + "-rival-release.json"), {
                                "schema": 1, "run_id": rival_stage["run_id"], "pid": rival_stage["pid"],
                                "worker_id": rival_stage["worker_id"], "fence": rival_stage["fence"]})
                        elif command["action"] == "idle":
                            await self._stop_rows(self.queue_workers)
                            await self._queue_launch(spec, "idle")
                    self.queue_commands[ident] = command
                    self.queue_ack = {"command_id": ident, "action": command["action"], "status": "complete"}
                    self._queue_publish()
            await asyncio.sleep(0.1)

    async def serve_commands(self):
        original = asyncio.create_task(super().serve_commands())
        self.base_monitor = original
        queue = asyncio.create_task(self._queue_loop())
        try:
            pending = {original, queue}
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task is original and self.base_monitor_retired:
                        _require(task.cancelled(), "Retired original monitor ended without the owned cancellation")
                        continue
                    task.result()
                    _require(self.closing, "Owned process control stopped unexpectedly")
        finally:
            original.cancel()
            queue.cancel()
            await asyncio.gather(original, queue, return_exceptions=True)

    async def stop(self):
        failure = None
        try:
            await self._stop_rows(self.queue_workers)
        except BaseException as error:
            failure = error
        finally:
            for row in self.queue_workers:
                row["log"].close()
            await super().stop()
            self._queue_publish()
        if failure:
            raise failure

    def collect_provider_counts(self, parent_counts):
        result = super().collect_provider_counts(parent_counts)
        for row in self.queue_workers:
            _require(row["process"].poll() is not None, "Queue provider aggregation requires exited CLI")
            path = self.evidence / ("provider-queue-" + row["worker_id"] + ".json")
            ledger = _load(path)
            _require(ledger["pid"] == row["process"].pid and ledger["worker_id"] == row["worker_id"] and
                     ledger["counts"]["synthetic_requests"] == len(ledger["counts"]["requests"]), "Queue CLI provider ledger differs")
            for key in ("synthetic_requests", "real_model_calls", "blocked_external_attempts"):
                value = ledger["counts"][key]
                _require(type(value) is int and value >= 0, "Malformed queue provider count")
                result[key] += value
            result["requests"].extend({**value, "worker_id": row["worker_id"], "queue_role": row["role"]} for value in ledger["counts"]["requests"])
            result["worker_process_ledgers"].append({"path": str(path), "pid": row["process"].pid,
                "worker_id": row["worker_id"], "queue_role": row["role"], "returncode": row["process"].returncode,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return result


def _worker_main(args):
    from fixture_server import read_instance, configure_environment
    from provider import SyntheticProvider, local_network_only
    manifest = read_instance(args.manifest)
    _instance(manifest)
    _require(manifest.get("worker_mode") == "process" and re.fullmatch(r"[0-9a-f]{32}", args.worker_id), "Queue CLI requires its process-mode identity")
    configure_environment(manifest, False)
    runtime, evidence = Path(manifest["runtime_root"]), Path(manifest["evidence_root"])
    descriptor = runtime / ("queue-worker-" + args.worker_id + ".json")
    deadline = time.monotonic() + 5
    while not descriptor.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    spec = _load(descriptor)
    _require(spec["schema"] == 1 and spec["pid"] == os.getpid() and spec["worker_id"] == args.worker_id and
             spec["phase"] in PHASES and spec["role"] in {"armed", "rival", "idle"}, "Queue CLI was not registered by its owner")
    provider = extend_provider(SyntheticProvider(manifest))
    ledger = evidence / ("provider-queue-" + args.worker_id + ".json")
    def save_counts():
        _atomic_json(ledger, {"schema": 1, "pid": os.getpid(), "worker_id": args.worker_id, "counts": provider.counts, "utc": _utc()})
    provider_handle = provider.handle
    async def recorded(request):
        try:
            return await provider_handle(request)
        finally:
            save_counts()
    save_counts()
    done, watchers = threading.Event(), []
    with local_network_only(provider.counts), provider.installed(), ExitStack() as adapters:
        from app.main import app  # noqa: F401 - original model import order.
        from runtime_followup_closeout import extend_followup_provider, observe_followup
        from runtime_context_closeout import extend_context_provider, observe_context_proof
        from runtime_outbox_closeout import outbox_transaction_faults
        from runtime_goal_closeout import extend_goal_provider
        from runtime_access_closeout import extend_access_provider
        from runtime_source_hooks_closeout import source_hook_faults
        from runtime_receipt_closeout import extend_provider as receipt_provider, receipt_faults
        from sqlite_outbox_closeout import observe_outbox
        extend_followup_provider(provider)
        extend_context_provider(provider)
        extend_goal_provider(provider)
        extend_access_provider(provider)
        adapters.enter_context(receipt_provider(provider))
        adapters.enter_context(receipt_faults(manifest))
        adapters.enter_context(observe_followup(manifest))
        adapters.enter_context(observe_context_proof(manifest))
        adapters.enter_context(outbox_transaction_faults(manifest))
        adapters.enter_context(source_hook_faults(manifest))
        adapters.enter_context(observe_outbox(manifest))
        provider_handle = provider.handle
        provider.handle = recorded
        from app import assistant_worker, assistant_runtime_runner as runner
        from app.db import engine
        original_save, original_row, original_finish, original_worker = runner._save_preparations, runner._prepare_row, runner._finish_write, assistant_worker.Worker
        active, fired = [None], [False]
        def gate(phase, db, principal, item_id, provisional=()):
            if fired[0] or spec["role"] != "armed" or phase != spec["phase"]:
                return
            fired[0] = True
            _require(principal.auth_kind == "login" and principal.lease_owner == "worker:" + args.worker_id, "Queue gate lost its original login principal")
            save_counts()
            stage = {"schema": 1, "stage_id": spec["stage_id"], "phase": phase, "pid": os.getpid(),
                "worker_id": args.worker_id, "run_id": principal.run_id, "session_id": principal.session_id,
                "owner_id": principal.actor_id, "store_id": principal.store_id, "lease_owner": principal.lease_owner,
                "fence": principal.fence, "run_item_id": item_id, "commit_returned": phase == "after_commit",
                "row_calls": active[0]["row_calls"], "provisional_rows": list(provisional), "entered_at": _utc()}
            _atomic_json(runtime / (spec["stage_id"] + "-stage.json"), stage)
            release = runtime / (spec["stage_id"] + "-release.json")
            until = time.monotonic() + 210
            # Synchronically blocking this actual CLI event loop stops both
            # Run and worker heartbeat. Before_save owns no write transaction.
            while not release.is_file() and time.monotonic() < until:
                time.sleep(0.1)
            _require(release.is_file() and _load(release) == {"schema": 1, "stage_id": spec["stage_id"],
                "phase": phase, "pid": os.getpid(), "worker_id": args.worker_id, "run_id": principal.run_id}, "Queue fixed gate timed out or release identity differs")
        def saved(db, principal, item_id, resolutions, *values, **keywords):
            if spec["role"] == "rival" and spec["hold_rival"] and spec["phase"] == "before_save" and resolutions and not fired[0]:
                result = original_save(db, principal, item_id, resolutions, *values, **keywords)
                _require(result["new_preparations"] == 3 and not db.in_transaction(),
                         "Rival gate requires the original complete commit and no open transaction")
                fired[0] = True
                rival = {"schema": 1, "run_id": principal.run_id, "session_id": principal.session_id,
                    "pid": os.getpid(), "worker_id": args.worker_id, "fence": principal.fence,
                    "lease_owner": principal.lease_owner, "commit_returned": True, "entered_at": _utc(),
                    "phase": "held_after_commit", "hold_seconds": 55,
                    "heartbeat_mode": "original_same_event_loop_blocked_by_fixed_sync_gate"}
                save_counts()
                _atomic_json(runtime / (spec["stage_id"] + "-rival-stage.json"), rival)
                release = runtime / (spec["stage_id"] + "-rival-release.json")
                until = time.monotonic() + 55
                while not release.is_file() and time.monotonic() < until:
                    time.sleep(0.1)
                released = release.is_file() and _load(release) == {"schema": 1, "run_id": principal.run_id,
                    "pid": os.getpid(), "worker_id": args.worker_id, "fence": principal.fence}
                rival.update(phase="released_after_old_write" if released else "hold_timeout",
                             finished_at=_utc(), held_seconds=55 - (until - time.monotonic()))
                _atomic_json(runtime / (spec["stage_id"] + "-rival-stage.json"), rival)
                _require(released, "Rival write-boundary release timed out or identity differs")
                return result
            if spec["role"] != "armed" or fired[0] or not resolutions:
                return original_save(db, principal, item_id, resolutions, *values, **keywords)
            _require(len(resolutions) == 3, "Queue gate requires the real complete three-row resolution vector")
            active[0] = {"principal": principal, "item_id": item_id, "row_calls": 0, "provisional": []}
            try:
                if spec["phase"] == "before_save":
                    # Match the original save prefix before blocking; discard
                    # only the completed native-read snapshot, holding no TX.
                    runner.service.require_preparation_read_phase(db)
                    db.rollback()
                    _require(not db.in_transaction(), "Before-save gate must hold no write transaction")
                gate("before_save", db, principal, item_id)
                result = original_save(db, principal, item_id, resolutions, *values, **keywords)
                _require(result["new_preparations"] == 3 and len(result["items"]) == 3, "Queue group did not commit all three preparations")
                gate("after_commit", db, principal, item_id, result["items"])
                _atomic_json(runtime / (spec["stage_id"] + "-late-result.json"), {"schema": 1, "run_id": principal.run_id,
                    "worker_id": args.worker_id, "fence": principal.fence, "save_returned": True, "status_code": None})
                return result
            except Exception as error:
                _atomic_json(runtime / (spec["stage_id"] + "-late-result.json"), {"schema": 1, "run_id": principal.run_id,
                    "worker_id": args.worker_id, "fence": principal.fence, "save_returned": False,
                    "error_type": type(error).__name__, "status_code": getattr(error, "status_code", None)})
                raise
            finally:
                active[0] = None
        def row(db, user, thread, data, values, preparation):
            current = active[0]
            if current is None:
                return original_row(db, user, thread, data, values, preparation)
            index = current["row_calls"]
            _require(index < 3, "Queue batch exceeded its exact original three rows")
            gate("before_" + "ABC"[index], db, current["principal"], current["item_id"], current["provisional"])
            result = original_row(db, user, thread, data, values, preparation)
            current["row_calls"] += 1
            current["provisional"].append({key: values[key] for key in ("input_item_id", "work_item_id", "proposal_id")})
            gate("after_" + "ABC"[index], db, current["principal"], current["item_id"], current["provisional"])
            return result
        def finish(db, principal, clock=None):
            if active[0] is not None:
                _require(active[0]["row_calls"] == 3, "Unified preparation commit did not contain all three original rows")
                gate("before_commit", db, principal, active[0]["item_id"], active[0]["provisional"])
            return original_finish(db, principal, clock)
        def watched(*values, **keywords):
            _require("runner" not in keywords, "Queue CLI runner dependency was already replaced")
            keywords["runner"] = queue_stream_runner(manifest)
            worker = original_worker(*values, **keywords)
            def watch():
                while not done.wait(0.1):
                    if (runtime / ("worker-stop-" + args.worker_id)).is_file():
                        worker.stop_signal()
                        return
            thread = threading.Thread(target=watch, daemon=True, name="queue-owned-stop")
            watchers.append(thread)
            thread.start()
            _atomic_json(runtime / ("worker-ready-" + args.worker_id + ".json"), {"schema": 1, "pid": os.getpid(), "worker_id": args.worker_id})
            return worker
        runner._save_preparations, runner._prepare_row, runner._finish_write, assistant_worker.Worker = saved, row, finish, watched
        try:
            return assistant_worker.main(["--worker-id", args.worker_id])
        finally:
            done.set()
            for thread in watchers:
                thread.join(timeout=1)
            runner._save_preparations, runner._prepare_row, runner._finish_write, assistant_worker.Worker = original_save, original_row, original_finish, original_worker
            save_counts()
            engine.dispose()


@asynccontextmanager
async def queue_emitter_control(manifest):
    """Replay only one real, already dispatched event through its original emitter."""
    _instance(manifest)
    runtime, evidence = Path(manifest["runtime_root"]), Path(manifest["evidence_root"])
    processed = {}
    async def serve():
        from app.db import SessionLocal
        from app.assistant_runtime_models import WakeEvent
        from app.assistant_runtime_outbox import emit_wake_event
        from fastapi import HTTPException
        command_path = runtime / "queue-emitter-command.json"
        while True:
            if command_path.is_file():
                command = _load(command_path)
                _require(set(command) == {"schema", "command_id", "event_id"} and command["schema"] == 1 and
                         re.fullmatch(r"[0-9a-f]{32}", command["command_id"]), "Unknown fixed emitter command")
                ident = command["command_id"]
                if ident in processed:
                    _require(command == processed[ident], "Emitter command ID changed")
                else:
                    with SessionLocal() as db:
                        source = db.get(WakeEvent, command["event_id"])
                        _require(source is not None and source.state == "dispatched" and source.source_ref and source.plan_id and
                                 source.topic == "plan" and source.source_ref["type"] == "plan", "Emitter control requires its real dispatched Plan source")
                        values = {key: getattr(source, key) for key in ("store_id", "object_ref", "proposal_id", "task_id", "plan_id", "source_ref")}
                        before = _rows(manifest["database_path"], "SELECT * FROM business_assistant_wake_events WHERE id=?", (source.id,))[0]
                        key, topic, event_id = source.signal_key, source.topic, source.id
                        same = emit_wake_event(db, key, topic, values)
                        _require(same.id == event_id, "Duplicate emitter created another event")
                        db.commit()
                    after = _rows(manifest["database_path"], "SELECT * FROM business_assistant_wake_events WHERE id=?", (event_id,))[0]
                    _require(before == after, "Duplicate emitter reset dispatch state, attempt or facts")
                    refused = None
                    with SessionLocal() as db:
                        try:
                            emit_wake_event(db, key, "plan.changed", values)
                        except HTTPException as error:
                            refused = error.status_code
                        finally:
                            db.rollback()
                    _require(refused == 409, "Same signal key with different content was not refused")
                    _atomic_json(evidence / ("queue-emitter-" + ident + ".json"), {"schema": 1, "command_id": ident,
                        "event_id": event_id, "source_ref": values["source_ref"], "signal_key": key,
                        "before": before, "after_duplicate": after, "duplicate_same_id": True, "changed_content_status": refused,
                        "execution_surface": "fixed original emitter contract; no UI claim", "utc": _utc()})
                    processed[ident] = command
            await asyncio.sleep(0.1)
    task = asyncio.create_task(serve())
    try:
        yield
    finally:
        if task.done() and not task.cancelled():
            task.result()
            raise AssertionError("Fixed emitter control stopped unexpectedly")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _command(e, stage_id, phase, action):
    ident = uuid.uuid4().hex
    e.action("worker_process_control", action, stage_id=stage_id, phase=phase)
    _atomic_json(Path(e.manifest["runtime_root"]) / "queue-closeout-command.json", {
        "schema": 1, "command_id": ident, "action": action, "stage_id": stage_id, "phase": phase})
    path = Path(e.manifest["runtime_root"]) / "queue-closeout-state.json"
    def ack():
        state = _load(path) if path.is_file() else None
        return state if state and (state.get("last_command") or {}).get("command_id") == ident else None
    return await e.wait(ack, "原CLI队列控制完成：" + action, timeout=55)


async def _preserve_and_new(e):
    """The employee's real pending-card handoff choice, without cancelling cards."""
    await e.click('[data-ba-action="new"]', "新事项；保留此前待确认原卡")
    await e.page.wait_for_function("() => document.querySelector('[data-ba-action=handoff-open]') || document.querySelector('#ba-current-heading')?.textContent === '新对话'")
    choice = e.page.locator('[data-ba-action="handoff-open"]')
    if await choice.count():
        await e.click('[data-ba-action="handoff-open"]', "员工明确保留当前事项并打开新事项")
    await e.page.wait_for_function("() => document.querySelector('#ba-current-heading')?.textContent === '新对话'")
    e.latest_session = None


async def _gate_batch(e, stage_id, phase):
    await _command(e, stage_id, phase, "arm")
    values = [{"name": "浏览器客户" + stage_id + "_" + label, "contact_allowed": False} for label in "ABC"]
    await e.send("队列三行准备 " + stage_id + "\n" + json.dumps(values, ensure_ascii=False), wait=False)
    await e.wait(lambda: e.latest_run and e.latest_session, "原UI创建三行准备Run")
    stage_path = Path(e.manifest["runtime_root"]) / (stage_id + "-stage.json")
    await e.wait(stage_path.is_file, "原三行实际固定边界：" + phase, timeout=40)
    stage = _load(stage_path)
    original = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    _require(stage["run_id"] == e.latest_run and stage["session_id"] == e.latest_session and stage["fence"] == original["fence"] and
             stage["owner_id"] == original["owner_id"] and stage["store_id"] == original["store_id"] and original["status"] == "running", "Queue stage is not this UI's exact original claim")
    return stage, original, values


def _artifact_rows(e, session_id):
    return {"cards": e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY id", (session_id,)),
            "works": e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? ORDER BY id", (session_id,)),
            "items": e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id IN (SELECT id FROM business_assistant_runs WHERE session_id=?) ORDER BY id", (session_id,)),
            "events": e.db.rows("SELECT * FROM business_assistant_run_events WHERE run_id IN (SELECT id FROM business_assistant_runs WHERE session_id=?) ORDER BY seq", (session_id,))}


async def _recovered(e, original):
    e.action("await_original_lease_recovery", "原90秒租约及30秒退避自然恢复", run_id=original["id"], timeout_seconds=175)
    def terminal():
        row = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (original["id"],))[0]
        return row if row["status"] in {"succeeded", "failed", "cancelled"} else None
    final = await e.wait(terminal, "原Run自然恢复终态", timeout=175)
    _require(final["status"] == "succeeded" and final["error_code"] is None and final["fence"] == original["fence"] + 1 and
             final["attempt"] == original["attempt"] + 1 and final["request_id"] == original["request_id"] and
             final["started_at"] == original["started_at"] and final["lease_owner"] is None and final["lease_until"] is None,
             "Queue recovery changed the original request/Run/budget or failed its new fence")
    _require(e.db.rows("SELECT id FROM business_assistant_runs WHERE session_id=?", (original["session_id"],)) == [{"id": original["id"]}], "Recovery created another Run")
    return final


async def _three_cards(e, session_id, values):
    from playwright.async_api import expect
    rows = _artifact_rows(e, session_id)
    cards = rows["cards"]
    works = [row for row in rows["works"] if row["item_kind"] == "prepare"]
    children = [row for row in rows["items"] if row["kind"] == "batch_row"]
    parents = [row for row in rows["items"] if row["tool_name"] == "prepare_business_batch" and row["kind"] == "tool"]
    _require(len(cards) == len(works) == len(children) == 3 and len(parents) == 1 and parents[0]["status"] == "succeeded" and
             all(row["status"] == "pending" for row in cards) and all(row["status"] == "prepared" for row in works) and
             {row["proposal_id"] for row in children} == {row["id"] for row in cards} and
             {row["work_item_id"] for row in children} == {row["id"] for row in works} and
             not any(row["kind"] == "confirmation" for row in rows["items"]), "Recovery lost or duplicated three real source-backed preparations")
    for card in cards:
        work = next(row for row in works if row["id"] == card["source_work_item_id"])
        payload = json.loads(card["payload"])
        _require(payload["body"]["values"] in values and card["session_id"] == work["session_id"] == session_id, "Card did not preserve its original employee facts")
    events = [row for row in rows["events"] if row["type"] == "proposal.prepared"]
    _require(len(events) == 3 and {json.loads(row["payload"])["proposal_id"] for row in events} == {row["id"] for row in cards}, "Preparation events were repeated or omitted")
    await e.ready()
    await e.click('[data-ba-action="refresh"]', "原UI核对自然恢复的三原卡")
    await e.ready()
    chooser = e.page.locator("#ba-queue-select")
    await expect(chooser.locator("option")).to_have_count(3)
    option_ids = await chooser.locator("option").evaluate_all("nodes => nodes.map(node => node.value)")
    _require(set(option_ids) == {card["id"] for card in cards}, "原选择框丢失或混入恢复卡")
    for card in cards:
        e.action("select", "按真实卡ID逐张核对恢复结果", proposal_id=card["id"])
        await chooser.select_option(card["id"])
        shown = e.page.locator('[data-proposal="' + card["id"] + '"]')
        await expect(shown).to_have_count(1)
        await expect(shown.locator(".pill")).to_have_text("待确认")
    return rows


async def old_lease_late_write(e, context, credentials):
    _require(e.manifest.get("worker_mode") == "process", "Late lease requires two real original CLI processes")
    await e.login(context, credentials)
    await e.ready()
    before = e.business_snapshot("old_lease_business_before")
    stage_id = "queue_" + uuid.uuid4().hex[:12]
    stage, original, values = await _gate_batch(e, stage_id, "before_save")
    initial = _artifact_rows(e, original["session_id"])
    _require(not initial["cards"] and not any(row["item_kind"] == "prepare" for row in initial["works"]), "Old lease already committed preparations")
    competing = await _command(e, stage_id, "before_save", "compete")
    live = [row for row in competing["workers"] if row["stage_id"] == stage_id and row["alive"]]
    _require(len(live) == 2 and len({row["pid"] for row in live}) == 2, "Two actual CLI processes did not compete for the original Run")
    e.action("await_original_lease_recovery", "原90秒租约及30秒退避自然恢复到新owner仍持busy", run_id=original["id"], timeout_seconds=175)
    rival_path = Path(e.manifest["runtime_root"]) / (stage_id + "-rival-stage.json")
    await e.wait(rival_path.is_file, "第二原CLI自然回收后在统一准备commit后保留原busy", timeout=175)
    rival = _load(rival_path)
    held = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (original["id"],))[0]
    _require(rival["run_id"] == original["id"] and rival["fence"] == held["fence"] == original["fence"] + 1 and
             held["attempt"] == original["attempt"] + 1 and held["status"] == "running" and
             held["lease_owner"] == rival["lease_owner"] and held["lease_owner"] != original["lease_owner"] and
             rival["phase"] == "held_after_commit" and rival["hold_seconds"] == 55 and
             rival["heartbeat_mode"] == "original_same_event_loop_blocked_by_fixed_sync_gate" and
             _future(held["lease_until"]),
             "Rival gate did not own the new original live claim")
    saved = _artifact_rows(e, original["session_id"])
    session = e.db.rows("SELECT * FROM business_assistant_sessions WHERE id=?", (original["session_id"],))
    _require(session[0]["busy_token"] == "runtime:" + uuid.UUID(original["id"]).hex and _future(session[0]["busy_until"]),
             "Late-write assertion requires the new owner's still-live original busy lease")
    await _command(e, stage_id, "before_save", "release")
    late_path = Path(e.manifest["runtime_root"]) / (stage_id + "-late-result.json")
    await e.wait(late_path.is_file, "旧进程实际进入原保存函数后被新fence拒绝", timeout=20)
    late = _load(late_path)
    _require(late["save_returned"] is False and late["status_code"] == 409 and late["run_id"] == original["id"] and
             late["fence"] == original["fence"], "Old surviving worker did not actually lose its original write fence")
    _require(e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (original["id"],)) == [held] and
             _artifact_rows(e, original["session_id"]) == saved and
             e.db.rows("SELECT * FROM business_assistant_sessions WHERE id=?", (original["session_id"],)) == session and
             _load(rival_path)["phase"] == "held_after_commit" and
             not (Path(e.manifest["runtime_root"]) / (stage_id + "-rival-release.json")).exists() and
             _future(held["lease_until"]) and _future(session[0]["busy_until"]),
             "Old lease changed new state, items, events or busy after its real late write attempt")
    await _command(e, stage_id, "before_save", "release_rival")
    releases = [row for row in _load(Path(e.manifest["evidence_root"]) / "worker-process-events.json")
                if row["event"] == "queue_rival_release_requested" and row["run_id"] == original["id"]]
    _require(len(releases) == 1 and releases[0]["rival_alive"] is True and
             releases[0]["pid"] == rival["pid"] and releases[0]["worker_id"] == rival["worker_id"] and
             releases[0]["fence"] == held["fence"] and releases[0]["lease_until"] == held["lease_until"] and
             releases[0]["busy_token"] == session[0]["busy_token"] and releases[0]["busy_until"] == session[0]["busy_until"],
             "Rival was not actually alive with the unchanged new fence and busy at comparison-window release")
    final = await _recovered(e, original)
    await _command(e, stage_id, "before_save", "idle")
    await _three_cards(e, original["session_id"], values)
    e.business_unchanged(before, "old_lease_business_after")
    e.observe("old_lease_late_write_rejected", {"stage": stage, "original_fence": original["fence"], "new_fence": final["fence"],
        "live_competing_pids": [row["pid"] for row in live], "late": late, "whole_rows_unchanged_after_late": True,
        "new_owner_busy_preserved_while_running": True, "rival_stage": rival,
        "comparison_run_sha256": _digest(held), "comparison_session_sha256": _digest(session),
        "whole_lease_columns_compared": True, "rival_comparison_window_release": releases[0],
        "clock_changed": False, "lease_seconds": 90, "retry_seconds": 30, "business_accepted": False})
    await e.snapshot("old-surviving-worker-cannot-write-new-fence")


async def batch_transaction_kills(e, context, credentials):
    _require(e.manifest.get("worker_mode") == "process", "Batch transaction kill requires real CLI processes")
    await e.login(context, credentials)
    await e.ready()
    before = e.business_snapshot("batch_kills_business_before")
    for index, phase in enumerate(PHASES):
        if index:
            await _preserve_and_new(e)
            await e.ready()
        stage_id = "queue_" + uuid.uuid4().hex[:12]
        stage, original, values = await _gate_batch(e, stage_id, phase)
        durable = _artifact_rows(e, original["session_id"])
        children = [row for row in durable["items"] if row["kind"] == "batch_row"]
        manifest = [row for row in durable["items"] if row["kind"] == "tool" and row["tool_name"] == "prepare_inputs"]
        _require(len(children) == 3 and len(manifest) == 1, "Kill stage lost the preexisting complete durable manifest/children")
        if phase == "after_commit":
            _require(stage["commit_returned"] is True and len(durable["cards"]) == 3 and
                     len([row for row in durable["works"] if row["item_kind"] == "prepare"]) == 3,
                     "After-commit kill did not observe the real unified three-card commit")
        else:
            _require(not durable["cards"] and not any(row["item_kind"] == "prepare" for row in durable["works"]),
                     "A batch row committed independently before the original whole-group transaction")
        killed = await _command(e, stage_id, phase, "kill")
        _require(any(row["stage_id"] == stage_id and row["role"] == "armed" and not row["alive"] and
                     row["returncode"] not in (None, 0) for row in killed["workers"]), "Batch fault did not really kill its owned CLI")
        _require(_artifact_rows(e, original["session_id"]) == durable, "Physical kill changed durable earlier manifest or left partial batch facts")
        await _command(e, stage_id, phase, "compete")
        final = await _recovered(e, original)
        recovered = await _three_cards(e, original["session_id"], values)
        if phase == "after_commit":
            _require(recovered["cards"] == durable["cards"] and recovered["works"] == durable["works"] and
                     all(next((current for current in recovered["items"] if current["id"] == saved["id"]), None) == saved
                         for saved in durable["items"]), "After-commit recovery changed original three cards/Work/mappings")
        else:
            restored_manifest = next(row for row in recovered["items"] if row["id"] == manifest[0]["id"])
            original_data, restored_data = json.loads(manifest[0]["validated_arguments"]), json.loads(restored_manifest["validated_arguments"])
            _require(original_data["scope"] == restored_data["scope"] and
                     [(row["input_item_id"], row["position"], row["input"]) for row in original_data["rows"]] ==
                     [(row["input_item_id"], row["position"], row["input"]) for row in restored_data["rows"]] and
                     {row["id"] for row in recovered["items"] if row["kind"] == "batch_row"} == {row["id"] for row in children},
                     "Recovery replaced durable original input identities/positions/facts or children")
        e.business_unchanged(before, "batch_kills_business_after_" + phase)
        e.observe("batch_transaction_kill_" + phase, {"stage": stage, "run_id": original["id"], "new_fence": final["fence"],
            "durable_sha256_before_kill": _digest(durable), "after_kill_same": True, "recovered_cards": [row["id"] for row in recovered["cards"]],
            "unified_commit": True, "no_row_commit": True, "confirmation_count": 0, "business_accepted": False})
        await e.snapshot("batch-kill-" + phase)
        await _command(e, stage_id, phase, "idle")


async def duplicate_request_and_wake(e, context, credentials):
    # The existing plan references admin-created, unassigned lead cases.
    # Sales/reception have only their own case scope; use the real store
    # manager's original login and permissions for this entire contract.
    user = await e.login(context, credentials, "manager")
    await e.ready()
    before = e.business_snapshot("duplicate_request_business_before")
    captured = []
    def capture(request):
        if request.method == "POST" and re.fullmatch(r"/api/business-assistant/sessions/[^/]+/runs", urlsplit(request.url).path):
            captured.append({"url": request.url, "body": request.post_data_json})
    e.page.on("request", capture)
    try:
        await e.send("查询本店张姓客户")
    finally:
        e.page.remove_listener("request", capture)
    _require(len(captured) == 1, "Original UI did not send exactly one source request")
    original = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    artifacts = _artifact_rows(e, e.latest_session)
    cookie = next(row["value"] for row in await context.cookies() if row["name"] == "dealer_csrf")
    headers = {"X-Store-ID": str(original["store_id"]), "X-App-Request": "1", "X-CSRF-Token": cookie}
    e.action("api_contract", "原本人Cookie/CSRF重复同request_id与拒绝不同内容；独立HTTP证据")
    repeated = await context.request.post(captured[0]["url"], data=captured[0]["body"], headers=headers)
    _require(repeated.status == 202, "Same exact request did not retain the original queued Run handle")
    body = await repeated.json()
    _require(body["id"] == original["id"], "Duplicate HTTP request created another Run")
    changed = await context.request.post(captured[0]["url"], data={**captured[0]["body"], "content": "查询不同的内容"}, headers=headers)
    _require(changed.status == 409 and _artifact_rows(e, original["session_id"]) == artifacts and
             e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (original["id"],)) == [original],
             "Conflicting request ID was not refused without assistant writes")
    e.observe("duplicate_request_contract", {"execution_surface": "HTTP contract after native UI source send", "ui_source_posts": 1,
        "duplicate_status": repeated.status, "conflict_status": changed.status, "run_id": original["id"], "request_id": original["request_id"],
        "owner_id": user["id"], "store_id": original["store_id"], "whole_original_artifacts_unchanged": True})
    await e.new_matter()
    await e.ready()
    await e.send("浏览器接待计划")
    plan_run = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
    plan_tools = e.db.rows("SELECT id,status,error_code FROM business_assistant_run_items WHERE run_id=? AND kind='tool' AND tool_name='save_work_plan'",
                           (plan_run["id"],))
    _require(plan_run["status"] == "succeeded" and plan_run["owner_id"] == user["id"] and
             plan_run["store_id"] == original["store_id"] and len(plan_tools) == 1 and
             plan_tools[0]["status"] == "succeeded" and plan_tools[0]["error_code"] is None,
             "Wake source Plan was not actually saved by this employee's original authorized tool")
    plans = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE session_id=?", (e.latest_session,))
    _require(len(plans) == 1, "Wake contract requires the original UI's actual Plan")
    _require(plans[0]["owner_id"] == user["id"] and plans[0]["store_id"] == original["store_id"] and
             plans[0]["session_id"] == plan_run["session_id"] and plans[0]["engine_version"] == 2,
             "Wake source Plan changed employee, store, session or original structured engine")
    e.observe("actual_wake_plan_source", {"execution_surface": "native manager login and original UI send",
        "run_id": plan_run["id"], "save_work_plan_item_id": plan_tools[0]["id"], "plan_id": plans[0]["id"],
        "owner_id": user["id"], "store_id": plans[0]["store_id"], "session_id": plans[0]["session_id"],
        "engine_version": 2, "case_ids": e.manifest["lead_plan"]["case_ids"],
        "task_ids": e.manifest["lead_plan"]["task_ids"], "business_accepted": False})
    def dispatched():
        rows = e.db.rows("SELECT * FROM business_assistant_wake_events WHERE plan_id=? AND topic='plan' ORDER BY created_at,id", (plans[0]["id"],))
        return next((row for row in rows if row["state"] == "dispatched" and json.loads(row["source_ref"])["type"] == "plan"), None)
    event = await e.wait(dispatched, "原Plan实际唤醒并唯一分发", timeout=30)
    _require(event["attempt"] == 1 and event["dispatched_at"], "Original wake event was not actually dispatched exactly once")
    runs = e.db.rows("SELECT * FROM business_assistant_runs WHERE plan_id=? ORDER BY id", (plans[0]["id"],))
    ident = uuid.uuid4().hex
    e.action("emitter_contract", "原真实source/key重复及内容冲突；不声明UI调用")
    _atomic_json(Path(e.manifest["runtime_root"]) / "queue-emitter-command.json", {"schema": 1, "command_id": ident, "event_id": event["id"]})
    path = Path(e.manifest["evidence_root"]) / ("queue-emitter-" + ident + ".json")
    await e.wait(path.is_file, "原emitter重复合同完成", timeout=20)
    result = _load(path)
    _require(result["duplicate_same_id"] is True and result["changed_content_status"] == 409 and
             e.db.rows("SELECT * FROM business_assistant_wake_events WHERE id=?", (event["id"],)) == [event] and
             e.db.rows("SELECT * FROM business_assistant_runs WHERE plan_id=? ORDER BY id", (plans[0]["id"],)) == runs and
             e.db.rows("SELECT count(*) AS n FROM business_assistant_wake_events WHERE signal_key=?", (event["signal_key"],))[0]["n"] == 1,
             "Duplicate emitter changed original dispatch, repeated wake or inserted another signal")
    e.observe("actual_wake_duplicate_contract", result)
    e.business_unchanged(before, "duplicate_request_and_wake_business_after")
    await e.snapshot("duplicate-request-and-original-wake")


async def stream_protocol_closeout(e, context, credentials):
    from playwright.async_api import expect
    user = await e.login(context, credentials)
    await e.ready()
    before = e.business_snapshot("stream_protocol_business_before")
    for mode in ("duplicate", "truncated"):
        await e.send("队列流协议 " + mode + "_" + uuid.uuid4().hex[:12])
        run = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
        items = e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id=? ORDER BY id", (run["id"],))
        _require(run["status"] == "failed" and not e.db.proposals(user["id"], session_id=run["session_id"]) and
                 not any(row["kind"] in {"tool", "input_manifest", "batch_row", "confirmation"} for row in items),
                 "Invalid duplicate/truncated model stream became executable intent or preparation")
        visible = await e.page.locator("#business-assistant-messages").inner_text()
        error = await e.page.locator("#business-assistant-error").inner_text()
        _require(error.strip() or any(word in visible for word in ("失败", "未完成", "中断", "无法")), "Invalid model stream had no employee-visible failure")
        e.observe("stream_protocol_" + mode, {"run_id": run["id"], "status": run["status"], "error_code": run["error_code"],
            "same_tool_ids": mode == "duplicate", "provider_done_sent": mode != "truncated", "no_executable_intent": True,
            "execution_surface": "native UI source send; isolated Worker runner dependency selects original SSE mode",
            "production_worker_stream_mode": False,
            "preparation_count": 0, "business_accepted": False})
        await e.snapshot("stream-" + mode + "-rejected")
        await e.send("查询本店张姓客户")
        recovered = e.db.rows("SELECT id,status FROM business_assistant_runs WHERE id=?", (e.latest_run,))[0]
        _require(recovered["id"] != run["id"] and recovered["status"] == "succeeded", "Original page did not recover after invalid model stream")
        await expect(e.page.locator("#business-assistant-error")).to_have_text("")
        _require(not e.db.proposals(user["id"], session_id=run["session_id"]), "Protocol recovery created a new proposal")
        e.business_unchanged(before, "stream_protocol_business_after_" + mode)
        await e.snapshot("stream-" + mode + "-original-page-recovered")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(_worker_main(args))
    except Exception as error:
        print(json.dumps({"queue_worker_failed": type(error).__name__}), flush=True)
        raise SystemExit(2)
