"""One real worker-process crash after the original preparation commit.

Control and provider files belong to this new synthetic instance. No helper
writes application rows, changes time, replays a chat, or confirms a proposal.
Importing this module starts nothing and imports no application module.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _utc():
    return datetime.now(timezone.utc).isoformat()


class _ObservationMutexError(RuntimeError):
    def __init__(self, reason, status):
        super().__init__(reason)
        self.wait_status = status


@contextmanager
def _file_mutex(path):
    path = Path(path).resolve()
    if path.name != "worker-state.json" and not re.fullmatch(r"followup-observations-[1-9][0-9]*\.json", path.name):
        raise ValueError("File mutex only accepts worker state or the exact PID report name")
    name = "Local\\HKOSBrowserFollowupObservation-" + hashlib.sha256(
        os.path.normcase(str(path)).encode("utf-8")).hexdigest()
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        state = kernel.WaitForSingleObject(handle, 10000)
        owned = state in (0, 0x80)
        if state == 0x80:
            raise _ObservationMutexError("observation_mutex_abandoned", state)
        if state == 0x102:
            error = TimeoutError("observation_mutex_timeout")
            error.wait_status = state
            raise error
        if state == 0xFFFFFFFF:
            error = ctypes.WinError(ctypes.get_last_error())
            error.wait_status = state
            raise error
        if state != 0:
            raise _ObservationMutexError("observation_mutex_unexpected_wait", state)
        yield
    finally:
        try:
            if owned and not kernel.ReleaseMutex(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if not kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())



def _load(path):
    if Path(path).name == "worker-state.json":
        with _file_mutex(path):
            return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_json(path, value):
    path = Path(path)
    with (_file_mutex(path) if path.name == "worker-state.json" else nullcontext()):
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def _rows(database, sql, values=()):
    _require(sql.lstrip().upper().startswith("SELECT "), "Fault evidence permits SELECT only")
    with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return [dict(row) for row in connection.execute(sql, values)]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


class WorkerProcessController:
    """Own two CLI processes serially; commands cannot name an arbitrary PID."""

    def __init__(self, manifest, manifest_path):
        self.manifest, self.manifest_path = manifest, Path(manifest_path).resolve()
        self.root = self.manifest_path.parent
        self.runtime = Path(manifest["runtime_root"]).resolve()
        self.evidence = Path(manifest["evidence_root"]).resolve()
        self.source = Path(manifest["source_root"]).resolve()
        _require(manifest.get("synthetic_data_only") is True and manifest.get("worker_mode") == "process",
                 "Process controller requires the explicit synthetic process mode")
        _require(self.runtime == self.root / "runtime" and self.evidence == self.root / "evidence"
                 and self.source == self.root / "source" and Path(__file__).resolve().parent == self.root / "scripts"
                 and Path(manifest["database_path"]).resolve().parent == self.runtime,
                 "Worker control escaped its frozen isolated instance")
        self.state_path = self.runtime / "worker-state.json"
        self.command_path = self.runtime / "worker-command.json"
        self.stage_path = self.runtime / "preparation-committed.json"
        self.events_path = self.evidence / "worker-process-events.json"
        self.processes, self.events, self.commands = [], [], {}
        self.current = None
        self.last_command = None
        self.closing = False

    def _event(self, event, **fields):
        self.events.append({"seq": len(self.events) + 1, "event": event, "utc": _utc(), **fields})
        _atomic_json(self.events_path, self.events)

    def _publish(self):
        row = self.current
        _atomic_json(self.state_path, {"schema": 1, "worker_mode": "process", "pid": row["process"].pid,
            "worker_id": row["worker_id"], "generation": row["generation"], "armed": row["armed"],
            "alive": row["process"].poll() is None, "returncode": row["process"].returncode,
            "started_at": row["started_at"], "last_command": self.last_command, "utc": _utc()})

    async def _launch(self, *, armed):
        _require(not self.closing and (self.current is None or self.current["process"].poll() is not None),
                 "A live worker cannot be replaced")
        generation, worker_id = len(self.processes) + 1, uuid.uuid4().hex
        _require(generation in (1, 2) and armed == (generation == 1), "Only one preparation crash may be armed")
        launch_executable, environment = sys.executable, dict(os.environ)
        if os.name == "nt" and sys.prefix != sys.base_prefix:
            # Windows venv python.exe is a redirector with a different PID.
            # Launch the same underlying interpreter directly, retaining this
            # venv through CPython's original launcher path mechanism.
            base_executable = getattr(sys, "_base_executable", None)
            _require(base_executable and Path(base_executable).is_file(), "The current venv has no real base interpreter")
            launch_executable = str(Path(base_executable).resolve())
            environment["__PYVENV_LAUNCHER__"] = sys.executable
        command = [launch_executable, str(Path(__file__).resolve()), "--worker", "--manifest",
                   str(self.manifest_path), "--worker-id", worker_id]
        if armed:
            command.append("--arm-crash")
        log = (self.evidence / ("worker-process-" + worker_id + ".log")).open("x", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=self.source, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, env=environment)
        except BaseException:
            log.close()
            raise
        row = {"process": process, "worker_id": worker_id, "generation": generation,
               "armed": armed, "started_at": _utc(), "log": log}
        self.current = row
        self.processes.append(row)
        self._event("started", pid=process.pid, worker_id=worker_id, generation=generation, armed=armed,
                    launch_executable=launch_executable, interpreter_executable=sys.executable, interpreter_prefix=sys.prefix)
        self._publish()
        ready = self.runtime / ("worker-ready-" + worker_id + ".json")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            _require(process.poll() is None, "Original worker CLI exited during startup")
            if ready.is_file():
                value = _load(ready)
                _require(value == {"schema": 1, "pid": process.pid, "worker_id": worker_id,
                                   "generation": generation, "armed": armed}, "Worker startup identity differs")
                self._event("ready", pid=process.pid, worker_id=worker_id, generation=generation)
                self._publish()
                return
            await asyncio.sleep(0.1)
        raise AssertionError("Original worker CLI did not become ready")

    async def start(self):
        _require(not self.processes and not any(path.exists() for path in
                 (self.state_path, self.command_path, self.stage_path, self.events_path)),
                 "Crash control refuses reused instance files")
        try:
            await self._launch(armed=True)
        except BaseException as startup_error:
            # The fixture's lifespan has not yielded yet; it cannot own cleanup
            # of a startup timeout unless this controller finishes its child.
            try:
                await self.stop()
            except BaseException as cleanup_error:
                startup_error.add_note("Owned worker startup cleanup failed: " + type(cleanup_error).__name__)
            raise

    def _committed_stage(self, command):
        row = self.current
        stage = _load(self.stage_path)
        _require(stage["schema"] == 1 and stage["phase"] == "preparations_committed"
                 and stage["commit_returned"] is True and stage["new_preparations"] > 0
                 and stage["worker_id"] == command["worker_id"] == row["worker_id"]
                 and stage["pid"] == command["pid"] == row["process"].pid
                 and stage["generation"] == command["generation"] == row["generation"] == 1
                 and stage["run_id"] == command["run_id"], "Kill did not reference this committed preparation")
        run = _rows(self.manifest["database_path"],
                    "SELECT id,status,owner_id,store_id,session_id,lease_owner,fence FROM business_assistant_runs WHERE id=?",
                    (stage["run_id"],))
        _require(len(run) == 1 and run[0]["status"] == "running"
                 and all(run[0][key] == stage[key] for key in
                         ("owner_id", "store_id", "session_id", "lease_owner", "fence")),
                 "Original Run is not the matching committed live claim")
        item = _rows(self.manifest["database_path"],
                     "SELECT id,status,run_id FROM business_assistant_run_items WHERE id=?", (stage["run_item_id"],))
        _require(len(item) == 1 and item[0]["run_id"] == stage["run_id"] and item[0]["status"] == "succeeded",
                 "Preparation tool has not really committed")
        for saved in stage["prepared_rows"]:
            cards = _rows(self.manifest["database_path"],
                "SELECT id,status,source_work_item_id,session_id FROM business_assistant_proposals WHERE id=?",
                (saved["proposal_id"],))
            works = _rows(self.manifest["database_path"],
                "SELECT id,status,input_item_id,session_id FROM business_assistant_work_items WHERE id=?",
                (saved["work_item_id"],))
            _require(len(cards) == len(works) == 1 and cards[0]["status"] == "pending"
                     and works[0]["status"] == "prepared"
                     and cards[0]["source_work_item_id"] == works[0]["id"]
                     and works[0]["input_item_id"] == saved["input_item_id"]
                     and cards[0]["session_id"] == works[0]["session_id"] == stage["session_id"],
                     "The saved proposal/WorkItem does not match the committed stage")
        _require(stage["prepared_rows"], "Committed stage has no real card")
        return stage

    async def serve_commands(self):
        while not self.closing:
            if self.command_path.is_file():
                command = _load(self.command_path)
                _require(set(command) == {"schema", "command_id", "action", "pid", "generation", "worker_id", "run_id"}
                         and command["schema"] == 1 and command["action"] in {"kill", "restart"}
                         and re.fullmatch(r"[0-9a-f]{32}", command["command_id"]), "Unknown worker control command")
                ident = command["command_id"]
                if ident in self.commands:
                    _require(self.commands[ident] == command, "A worker command ID was changed")
                else:
                    row, process = self.current, self.current["process"]
                    _require(command["pid"] == process.pid and command["generation"] == row["generation"] == 1
                             and command["worker_id"] == row["worker_id"], "Command does not target the owned current process")
                    stage = self._committed_stage(command)
                    if command["action"] == "kill":
                        _require(process.poll() is None and not any(event["event"] == "killed" for event in self.events),
                                 "The original worker must be alive and killed only once")
                        self._event("kill_requested", **{key: command[key] for key in ("command_id", "pid", "generation", "worker_id", "run_id")})
                        process.kill()  # The owned Popen only; never a supplied PID or process group.
                        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=10)
                        _require(process.returncode != 0, "Hard-killed worker unexpectedly exited normally")
                        row["log"].close()
                        self._event("killed", pid=process.pid, worker_id=row["worker_id"], generation=1,
                                    run_id=stage["run_id"], returncode=process.returncode)
                    else:
                        _require(process.poll() is not None and process.returncode != 0
                                 and any(event["event"] == "killed" and event["pid"] == process.pid for event in self.events),
                                 "Restart requires the original process's observed nonzero terminal state")
                        await self._launch(armed=False)
                        self._event("restarted", pid=self.current["process"].pid, worker_id=self.current["worker_id"],
                                    generation=2, previous_pid=process.pid, run_id=stage["run_id"])
                    self.commands[ident] = command
                    self.last_command = {**command, "status": "complete", "returncode": process.returncode}
                    self._publish()
            if self.current["process"].poll() is not None:
                _require(any(event["event"] == "killed" and event["pid"] == self.current["process"].pid
                             for event in self.events), "Worker CLI ended outside its controlled crash/stop")
            await asyncio.sleep(0.1)

    async def stop(self):
        self.closing = True
        if self.current is None:
            return
        row, process = self.current, self.current["process"]
        failure = None
        try:
            if process.poll() is None:
                (self.runtime / ("worker-stop-" + row["worker_id"])).write_text("Stop this owned synthetic worker normally.\n", encoding="utf-8")
                self._event("stop_requested", pid=process.pid, worker_id=row["worker_id"], generation=row["generation"])
                await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=10)
                _require(process.returncode == 0, "Worker normal shutdown failed")
                self._event("stopped", pid=process.pid, worker_id=row["worker_id"],
                            generation=row["generation"], returncode=process.returncode)
            for owned in self.processes:
                _require(owned["process"].poll() is not None, "An owned worker is still alive")
            self._publish()
        except BaseException as error:
            failure = error
            forced = False
            # Physical cleanup precedes all additional evidence I/O. A short
            # synchronous wait also survives cancellation of this async task.
            try:
                if process.poll() is None:
                    forced = True
                    try:
                        process.kill()  # Still only the owned Popen.
                    finally:
                        process.wait(timeout=3)
            except BaseException as cleanup_error:
                failure.add_note("Owned worker physical cleanup failed: " + type(cleanup_error).__name__)
            try:
                if forced:
                    self._event("forced_cleanup", pid=process.pid, worker_id=row["worker_id"],
                                generation=row["generation"], returncode=process.returncode)
                self._publish()
            except BaseException as evidence_error:
                failure.add_note("Worker cleanup evidence failed: " + type(evidence_error).__name__)
        finally:
            for owned in self.processes:
                try:
                    owned["log"].close()
                except BaseException as close_error:
                    if failure is None:
                        failure = close_error
                    else:
                        failure.add_note("Worker log close failed: " + type(close_error).__name__)
        if failure is not None:
            raise failure  # Forced cleanup, including an I/O failure, is never normal stop.

    def collect_provider_counts(self, parent_counts):
        result = {key: parent_counts[key] for key in ("synthetic_requests", "real_model_calls", "blocked_external_attempts")}
        result["requests"] = [dict(value) for value in parent_counts["requests"]]
        ledgers = []
        for row in self.processes:
            _require(row["process"].poll() is not None, "Provider aggregation requires real terminal workers")
            path = self.evidence / ("provider-worker-" + row["worker_id"] + ".json")
            ledger = _load(path)
            _require(ledger["schema"] == 1 and ledger["pid"] == row["process"].pid
                     and ledger["worker_id"] == row["worker_id"] and ledger["generation"] == row["generation"],
                     "Worker provider ledger belongs to another process")
            counts = ledger["counts"]
            for key in ("synthetic_requests", "real_model_calls", "blocked_external_attempts"):
                _require(type(counts[key]) is int and counts[key] >= 0, "Malformed worker provider counts")
                result[key] += counts[key]
            _require(counts["synthetic_requests"] == len(counts["requests"]), "Worker provider ledger lost processed requests")
            result["requests"].extend({**value, "worker_id": row["worker_id"], "generation": row["generation"]}
                                      for value in counts["requests"])
            ledgers.append({"path": str(path), "worker_id": row["worker_id"], "generation": row["generation"],
                            "pid": row["process"].pid, "returncode": row["process"].returncode,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        result["worker_process_ledgers"] = ledgers
        return result


async def preparation_crash(e, context, credentials):
    """Prepare once in Chrome, kill the committed worker, naturally recover."""
    from playwright.async_api import expect

    _require(e.manifest.get("worker_mode") == "process", "准备崩溃场景需要真实worker子进程")
    runtime, evidence = Path(e.manifest["runtime_root"]), Path(e.manifest["evidence_root"])
    state_path, stage_path = runtime / "worker-state.json", runtime / "preparation-committed.json"
    initial = _load(state_path)
    _require(initial["generation"] == 1 and initial["alive"] and initial["armed"] and not stage_path.exists(),
             "必须是本轮首次armed worker且无旧故障阶段")
    user = await e.login(context, credentials)
    await e.ready()
    before = e.business_snapshot("preparation_crash_original_business_before")
    name = "浏览器客户crash_" + uuid.uuid4().hex[:12]
    await e.send("新建客户 " + name, wait=False)
    await e.wait(lambda: e.latest_run and e.latest_session, "原UI实际创建唯一Run")
    run_id, session_id = e.latest_run, e.latest_session
    await e.wait(stage_path.is_file, "原准备真实提交后的阶段标记", timeout=35)
    stage = _load(stage_path)
    _require(stage["run_id"] == run_id and stage["session_id"] == session_id
             and stage["owner_id"] == user["id"] and str(stage["store_id"]) == await e.page.locator("#store").input_value()
             and stage["pid"] == initial["pid"] and stage["worker_id"] == initial["worker_id"]
             and stage["generation"] == 1 and stage["new_preparations"] == 1 and stage["commit_returned"] is True,
             "故障阶段必须是当前本人本店原Run的首次已提交准备")
    original = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))[0]
    cards = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY id", (session_id,))
    works = e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? AND item_kind='prepare' ORDER BY id", (session_id,))
    tool = e.db.rows("SELECT * FROM business_assistant_run_items WHERE id=?", (stage["run_item_id"],))
    _require(original["status"] == "running" and original["fence"] == stage["fence"]
             and original["lease_owner"] == stage["lease_owner"] == "worker:" + initial["worker_id"]
             and len(cards) == len(works) == len(tool) == 1 and cards[0]["status"] == "pending"
             and works[0]["status"] == "prepared" and cards[0]["source_work_item_id"] == works[0]["id"]
             and tool[0]["run_id"] == run_id and tool[0]["status"] == "succeeded", "崩溃前真实卡/WorkItem/工具提交未成立")
    card, work = cards[0], works[0]
    _require(card["summary"] == "新建客户：" + name and card["owner_id"] == work["owner_id"] == user["id"]
             and card["store_id"] == work["store_id"] == stage["store_id"]
             and stage["prepared_rows"] == [{"proposal_id": card["id"], "work_item_id": work["id"], "input_item_id": work["input_item_id"]}],
             "准备卡必须来自当前显式新客户指令及其真实输入关系")
    e.observe("preparation_committed_before_process_crash", {"stage": stage, "run_id": run_id,
        "proposal_id": card["id"], "work_item_id": work["id"], "proposal_sha256": _digest(card),
        "work_item_sha256": _digest(work), "tool_sha256": _digest(tool), "attempt": original["attempt"],
        "lease_until": original["lease_until"], "business_accepted": False})
    e.business_unchanged(before, "preparation_crash_original_business_after_commit")

    async def command(action, current):
        ident = uuid.uuid4().hex
        body = {"schema": 1, "command_id": ident, "action": action, "pid": current["pid"],
                "generation": current["generation"], "worker_id": current["worker_id"], "run_id": run_id}
        e.action("worker_process_control", action, **{key: body[key] for key in ("pid", "generation", "worker_id", "run_id")})
        _atomic_json(runtime / "worker-command.json", body)
        def acknowledged():
            value = _load(state_path)
            ack = value.get("last_command")
            return value if ack and ack["command_id"] == ident and ack["status"] == "complete" else None
        return await e.wait(acknowledged, "原worker进程控制终局：" + action, timeout=35)

    killed = await command("kill", initial)
    _require(not killed["alive"] and killed["returncode"] not in (None, 0)
             and killed["pid"] == initial["pid"] and killed["generation"] == 1, "原worker未实际非零退出")
    ledger = _load(evidence / ("provider-worker-" + initial["worker_id"] + ".json"))
    _require(ledger["counts"]["synthetic_requests"] >= 2 and ledger["counts"]["real_model_calls"] == 0
             and ledger["counts"]["blocked_external_attempts"] == 0, "被kill前已处理合成模型请求账本丢失或联网")
    e.observe("preparation_crash_killed_worker", killed)
    restarted = await command("restart", killed)
    _require(restarted["alive"] and restarted["generation"] == 2 and not restarted["armed"]
             and restarted["worker_id"] != initial["worker_id"], "必须实际启动另一不armed原worker")
    e.observe("preparation_crash_restarted_worker", restarted)
    e.action("await_original_lease_recovery", "等待原90秒租约自然过期及首次30秒退避，不改时钟或重发聊天", run_id=run_id, timeout_seconds=160)

    def terminal():
        rows = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))
        return rows[0] if rows and rows[0]["status"] in {"succeeded", "failed", "cancelled"} else None

    final = await e.wait(terminal, "原Run自然回收并重新领取的真实终态", timeout=160)
    _require(final["status"] == "succeeded" and final["error_code"] is None
             and final["fence"] == original["fence"] + 1 and final["attempt"] == original["attempt"] + 1
             and final["started_at"] == original["started_at"] and final["request_id"] == original["request_id"]
             and final["lease_owner"] is None and final["lease_until"] is None and final["finished_at"],
             "原合同恢复未成功或更换了原Run/请求/预算起点")
    _require(e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY id", (session_id,)) == cards
             and e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? AND item_kind='prepare' ORDER BY id", (session_id,)) == works
             and e.db.rows("SELECT * FROM business_assistant_run_items WHERE id=?", (stage["run_item_id"],)) == tool,
             "恢复重复准备或改写原卡/准备意图/已完成工具")
    _require(e.db.rows("SELECT id FROM business_assistant_runs WHERE session_id=?", (session_id,)) == [{"id": run_id}]
             and not e.db.rows("SELECT id FROM business_assistant_run_items WHERE proposal_id=? AND kind='confirmation'", (card["id"],)),
             "不得重发聊天、新建Run或自动确认业务")
    session = e.db.rows("SELECT busy_token,busy_until FROM business_assistant_sessions WHERE id=?", (session_id,))[0]
    messages = e.db.rows("SELECT id,role,request_id FROM business_assistant_messages WHERE session_id=? ORDER BY id", (session_id,))
    _require(session == {"busy_token": None, "busy_until": None} and len(messages) == 2
             and [row["role"] for row in messages] == ["user", "assistant"]
             and messages[0]["request_id"] == original["request_id"]
             and messages[1]["request_id"] == original["request_id"] + ":reply", "原busy/唯一最终回复未正常收尾")
    events = e.db.rows("SELECT seq,type,payload FROM business_assistant_run_events WHERE run_id=? ORDER BY seq", (run_id,))
    prepared = [event for event in events if event["type"] == "proposal.prepared"]
    _require([event["seq"] for event in events] == list(range(1, final["event_seq"] + 1))
             and events[-1]["type"] == "run.completed" and len(prepared) == 1
             and json.loads(prepared[0]["payload"])["proposal_id"] == card["id"]
             and sum(event["type"] == "run.started" for event in events) == 2
             and sum(event["type"] == "run.queued" for event in events) == 2,
             "真实恢复事件不连续、重复准备或缺少原重新排队/领取")
    process_events = _load(evidence / "worker-process-events.json")
    _require(sum(event["event"] == "killed" for event in process_events) == 1
             and sum(event["event"] == "restarted" for event in process_events) == 1,
             "崩溃/重启必须各实际发生一次")
    e.observe("preparation_crash_same_run_recovered", {"run_id": run_id, "status": final["status"],
        "before_fence": original["fence"], "after_fence": final["fence"], "before_attempt": original["attempt"],
        "after_attempt": final["attempt"], "proposal_id": card["id"], "work_item_id": work["id"],
        "proposal_whole_row_unchanged": True, "prepare_work_whole_row_unchanged": True,
        "prepared_tool_whole_row_unchanged": True, "events": [{"seq": row["seq"], "type": row["type"]} for row in events],
        "process_events": process_events, "chat_not_resent": True, "confirmation_count": 0, "business_accepted": False})
    await e.ready()
    await e.click('[data-ba-action="refresh"]', "原UI重读崩溃恢复后的原卡")
    await e.ready()
    shown = e.page.locator(f'[data-proposal="{card["id"]}"]')
    await expect(shown).to_have_count(1)
    await expect(shown).to_be_visible()
    await expect(shown).to_contain_text(name)
    await expect(shown.locator(".pill")).to_have_text("待确认")
    await expect(e.page.locator(f'[data-ba-action="confirm"][data-id="{card["id"]}"]')).to_be_enabled()
    e.business_unchanged(before, "preparation_crash_original_business_after_recovery_and_read")
    await e.snapshot("preparation-crash-original-card-awaits-employee-confirmation")


async def inflight_stop(e, context, credentials):
    """Click the original stop UI, then return its blocked preparation reply."""
    from urllib.parse import urlsplit
    from playwright.async_api import expect

    user = await e.login(context, credentials)
    await e.ready()
    before = e.business_snapshot("inflight_stop_original_business_before")
    name = "浏览器客户cancel_" + uuid.uuid4().hex[:12]
    await e.send("新建客户 " + name, wait=False)
    await e.wait(lambda: e.latest_run and e.latest_session, "原UI实际创建停止场景Run")
    run_id, session_id = e.latest_run, e.latest_session
    runtime = Path(e.manifest["runtime_root"])
    stage_path = runtime / ("inflight-stop-" + run_id + ".json")
    release_path = runtime / ("inflight-stop-" + run_id + "-release.json")
    await e.wait(stage_path.is_file, "原inspect成功后的第二轮模型响应门控", timeout=20)
    stage = _load(stage_path)
    original = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))[0]
    busy_before = e.db.rows("SELECT busy_token,busy_until FROM business_assistant_sessions WHERE id=?", (session_id,))[0]
    items = e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id=? ORDER BY id", (run_id,))
    tools = [row for row in items if row["kind"] == "tool"]
    works = e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? ORDER BY id", (session_id,))
    messages = e.db.rows("SELECT * FROM business_assistant_messages WHERE session_id=? ORDER BY id", (session_id,))
    events_before = e.db.rows("SELECT seq,type,payload FROM business_assistant_run_events WHERE run_id=? ORDER BY seq", (run_id,))
    _require(stage["phase"] == "waiting_before_prepare_response" and stage["stage_id"] == name
             and stage["run_id"] == run_id and stage["session_id"] == session_id
             and stage["owner_id"] == original["owner_id"] == user["id"]
             and stage["store_id"] == original["store_id"] == int(await e.page.locator("#store").input_value())
             and stage["request_id"] == original["request_id"] and stage["fence"] == original["fence"]
             and stage["attempt"] == original["attempt"] and stage["tools_before_response"] == 1
             and stage["response_tool"] == "prepare_business_form" and not stage["returned_after_stop"]
             and original["status"] == "running" and not original["stop_requested"]
             and original["lease_owner"] and original["lease_until"]
             and busy_before["busy_token"] == "runtime:" + uuid.UUID(run_id).hex
             and busy_before["busy_until"] and not release_path.exists(),
             "门控阶段必须来自本人的原running Run且准备响应尚未返回")
    _require(len(items) == 2 and sum(row["kind"] == "model" for row in items) == 1
             and all(row["status"] == "succeeded" for row in items)
             and not any(row["kind"] == "confirmation" for row in items)
             and len(tools) == 1 and tools[0]["id"] == stage["inspect_item_id"]
             and tools[0]["tool_name"] == "inspect_business_form" and tools[0]["status"] == "succeeded"
             and _digest(tools[0]) == stage["inspect_sha256"]
             and len(messages) == 1 and messages[0]["role"] == "user"
             and messages[0]["request_id"] == original["request_id"]
             and not e.db.rows("SELECT id FROM business_assistant_proposals WHERE session_id=?", (session_id,))
             and not any(row["item_kind"] == "prepare" for row in works),
             "停止前真实inspect未完整成功，或准备/助手回复已经产生")
    e.observe("inflight_stop_inspected_before_response", {"stage": stage, "run_id": run_id,
        "status": original["status"], "version": original["version"], "fence": original["fence"],
        "attempt": original["attempt"], "inspect_whole_row_sha256": _digest(tools[0]),
        "run_items_sha256": _digest(items), "preparation_count": 0, "business_accepted": False})
    e.business_unchanged(before, "inflight_stop_original_business_after_inspection")

    await e.page.wait_for_function("id => { const v=globalThis.AssistantRuntime?.snapshot(id)?.view; return v && ['queued','running'].includes(v.status) && v.allowed_actions.includes('cancel'); }", arg=run_id)
    cancel_path = "/api/business-assistant/runs/" + run_id + "/cancel"
    run_path = "/api/business-assistant/runs/" + run_id
    responses = []

    def observe_response(response):
        path = urlsplit(response.url).path
        if (path == cancel_path and response.request.method == "POST"
                or path == run_path and response.request.method == "GET"):
            responses.append(response)

    e.page.on("response", observe_response)

    async def click_stop(label):
        view = await e.page.evaluate("id => globalThis.AssistantRuntime?.snapshot(id)?.view", run_id)
        async with e.page.expect_response(lambda response: urlsplit(response.url).path == cancel_path
                                          and response.request.method == "POST") as pending:
            await e.click('[data-ba-action="stop"]', label)
        response = await pending.value
        headers = await response.request.all_headers()
        body = response.request.post_data_json
        result = await response.json()
        _require(isinstance(body, dict) and set(body) == {"expected_version"}
                 and type(body["expected_version"]) is int and body["expected_version"] > 0
                 and headers.get("cookie") and headers.get("x-csrf-token")
                 and headers.get("x-store-id") == str(original["store_id"]),
                 "停止必须由原UI携带本人Cookie/CSRF/当前门店及实际执行版本")
        e.observe("inflight_stop_native_cancel_" + str(len([r for r in responses if r.request.method == "POST"])),
            {"path": cancel_path, "method": "POST", "status": response.status,
             "cookie_present": True, "csrf_present": True, "store_id": original["store_id"],
             "expected_version": body["expected_version"], "ui_version_before_click": view["version"],
             "response": result})
        return response, body, result

    try:
        response, request_body, result = await click_stop("员工点击停止本次准备")
        if response.status == 409:
            _require(not e.protected_conflicts, "停止出现第二次版本冲突，不能继续点击")
            refusal = {"action": "stop", "first_status": 409, "detail": e.scrub(result.get("detail", "")),
                       "outcome": "protected_conflict_observed", "employee_rechecks": 0}
            e.protected_conflicts.append(refusal)
            await expect(e.page.locator("#business-assistant")).to_contain_text("执行状态已变化，请核对后重试。")
            def reread():
                return next((value for value in responses[responses.index(response) + 1:]
                             if value.request.method == "GET" and value.status == 200), None)
            read_response = await e.wait(reread, "409后原UI实际GET重读执行状态", timeout=5)
            read_view = await read_response.json()
            _require(read_view["id"] == run_id and read_view["status"] == "running"
                     and read_view["version"] > request_body["expected_version"]
                     and "cancel" in read_view["allowed_actions"]
                     and not e.db.rows("SELECT stop_requested FROM business_assistant_runs WHERE id=?", (run_id,))[0]["stop_requested"],
                     "409后未原样拒绝或原UI未实际读到新的可取消版本")
            await e.page.wait_for_function("arg => globalThis.AssistantRuntime?.snapshot(arg.id)?.view?.version === arg.version", arg={"id": run_id, "version": read_view["version"]})
            e.action("employee_conflict_review", "核对原UI新执行版本后最多一次明确点击", run_id=run_id, max_new_attempts=1)
            refusal["employee_rechecks"] = 1
            response, request_body, result = await click_stop("员工重读后再次点击停止本次准备")
            refusal["reviewed_status"] = response.status
            _require(response.status == 200, "重读后停止仍未成功，停止，不循环重放")
            refusal["outcome"] = "covered_protected_conflict"
            e.observe("inflight_stop_covered_version_conflict", {**refusal, "reread_version": read_view["version"]})
        _require(response.status == 200 and result["id"] == run_id and result["session_id"] == session_id
                 and result["status"] == "running" and result["version"] == request_body["expected_version"] + 1
                 and "cancel" not in result["allowed_actions"], "running停止200必须只请求停止，不能假装已终局")
        stopped = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))[0]
        busy = e.db.rows("SELECT busy_token,busy_until FROM business_assistant_sessions WHERE id=?", (session_id,))[0]
        identity = ("id", "session_id", "owner_id", "store_id", "request_id", "fence", "attempt", "started_at")
        _require(stopped["status"] == "running" and stopped["stop_requested"]
                 and stopped["version"] == result["version"] and stopped["finished_at"] is None
                 and stopped["lease_owner"] == original["lease_owner"] and stopped["lease_until"]
                 and busy["busy_token"] == busy_before["busy_token"] and busy["busy_until"]
                 and all(stopped[key] == original[key] for key in identity)
                 and _load(stage_path)["phase"] == "waiting_before_prepare_response",
                 "停止请求尚未释放原忙状态/租约且应保持同Run，响应必须仍被门控")
        _require(e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id=? ORDER BY id", (run_id,)) == items,
                 "点击停止时不得执行迟到准备或改写原inspect")
        e.observe("inflight_stop_requested_not_terminal", {"run_id": run_id, "status": stopped["status"],
            "stop_requested": True, "version": stopped["version"], "busy_preserved": True,
            "lease_preserved": True, "same_request_fence_attempt": True, "response_still_waiting": True})
        e.action("synthetic_response_release", "仅释放已请求停止的第二轮模型响应", run_id=run_id, stage_id=name)
        _atomic_json(release_path, {"schema": 1, "stage_id": name, "run_id": run_id,
                                  "session_id": session_id, "action": "return_prepare_response"})
        def response_finished():
            value = _load(stage_path)
            return value if value["phase"] != "waiting_before_prepare_response" else None
        returned = await e.wait(response_finished, "合成模型实际迟到返回或明确中断阶段", timeout=8)
        e.observe("inflight_stop_provider_response_outcome", returned)
        _require(returned["phase"] == "returned_after_stop" and returned["returned_after_stop"] is True
                 and returned.get("stop_requested_observed") is True and returned.get("response_status") == 200
                 and returned.get("stop_version") == stopped["version"] and returned.get("returned_at"),
                 "心跳中断/超时不等于停止后的准备模型响应实际返回")
    finally:
        e.page.remove_listener("response", observe_response)

    def terminal():
        row = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))[0]
        return row if row["status"] in {"succeeded", "failed", "cancelled"} else None
    final = await e.wait(terminal, "原worker控制边界拒绝迟到响应并取消原Run", timeout=25)
    _require(final["status"] == "cancelled" and final["stop_requested"]
             and final["error_code"] == "precondition_conflict" and final["finished_at"]
             and final["lease_owner"] is None and final["lease_until"] is None
             and all(final[key] == original[key] for key in identity),
             "迟到响应未通过原控制边界取消同Run，或重建请求/领取/租约")
    _require(e.db.rows("SELECT id FROM business_assistant_runs WHERE session_id=?", (session_id,)) == [{"id": run_id}]
             and e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id=? ORDER BY id", (run_id,)) == items
             and e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? ORDER BY id", (session_id,)) == works
             and not e.db.rows("SELECT id FROM business_assistant_proposals WHERE session_id=?", (session_id,))
             and e.db.rows("SELECT * FROM business_assistant_messages WHERE session_id=? ORDER BY id", (session_id,)) == messages
             and e.db.rows("SELECT busy_token,busy_until FROM business_assistant_sessions WHERE id=?", (session_id,))[0]
                 == {"busy_token": None, "busy_until": None},
             "停止后新增卡/准备/确认/回复/Run，改写原inspect或未释放原忙状态")
    events = e.db.rows("SELECT seq,type,payload FROM business_assistant_run_events WHERE run_id=? ORDER BY seq", (run_id,))
    _require([row["seq"] for row in events] == list(range(1, final["event_seq"] + 1))
             and events[:len(events_before)] == events_before
             and events[-1]["type"] == "run.cancelled"
             and sum(row["type"] == "run.cancelled" for row in events) == 1
             and sum(row["type"] == "run.queued" for row in events) == 1
             and sum(row["type"] == "run.started" for row in events) == 1
             and sum(row["type"] == "tool.finished" for row in events) == 1
             and not any(row["type"] in {"proposal.prepared", "run.completed", "run.failed"} for row in events),
             "原取消事件序列不连续，或迟到准备/成功/重排被错误保留")
    await e.page.wait_for_function("() => !document.querySelector('[data-ba-action=stop]')", timeout=25000)
    await e.ready()
    await expect(e.page.locator("#business-assistant")).to_contain_text("本次准备已停止")
    await expect(e.page.locator("#business-assistant-cards [data-proposal]")).to_have_count(0)
    await e.snapshot("inflight-stop-late-response-rejected")
    await e.click('[data-ba-action="refresh"]', "原UI刷新停止后的原对话")
    await e.ready()
    await expect(e.page.locator("#business-assistant-cards [data-proposal]")).to_have_count(0)
    e.business_unchanged(before, "inflight_stop_original_business_after_stop_and_refresh")
    e.observe("inflight_stop_late_response_rejected", {"run_id": run_id, "status": final["status"],
        "error_code": final["error_code"], "same_request_fence_attempt": True, "chat_not_resent": True,
        "inspect_whole_row_unchanged": True, "run_items_whole_rows_unchanged": True,
        "preparation_count": 0, "confirmation_count": 0, "assistant_reply_count": 0,
        "events": [{"seq": row["seq"], "type": row["type"]} for row in events],
        "returned_after_stop": True, "business_accepted": False})
    await e.snapshot("inflight-stop-refresh-still-no-preparation")


def _worker_main(args):
    from fixture_server import read_instance, configure_environment
    from provider import SyntheticProvider, local_network_only

    manifest = read_instance(args.manifest)
    _require(manifest.get("worker_mode") == "process" and re.fullmatch(r"[0-9a-f]{32}", args.worker_id),
             "CLI worker requires one explicit process-mode identity")
    configure_environment(manifest, False)  # Always before any app/config import.
    runtime, evidence = Path(manifest["runtime_root"]), Path(manifest["evidence_root"])
    # Popen gives the owner its PID before the owner can atomically publish it.
    # A replacement can briefly see generation one's state. This is a bounded
    # process-registration handshake, before any application import or claim.
    state_path, state = runtime / "worker-state.json", None
    registration_deadline = time.monotonic() + 5
    while time.monotonic() < registration_deadline:
        if state_path.is_file():
            candidate = _load(state_path)
            if candidate["pid"] == os.getpid() and candidate["worker_id"] == args.worker_id:
                state = candidate
                break
        time.sleep(0.05)
    _require(state is not None and state["armed"] is args.arm_crash
             and state["generation"] == (1 if args.arm_crash else 2),
             "Worker CLI was not registered by its owning controller")
    generation = state["generation"]
    from runtime_queue_closeout import extend_provider as extend_queue_provider
    from runtime_followup_closeout import extend_followup_provider
    from runtime_context_closeout import extend_context_provider
    from runtime_goal_closeout import extend_goal_provider
    from runtime_access_closeout import extend_access_provider
    from runtime_receipt_closeout import extend_provider as extend_receipt_provider
    provider = extend_queue_provider(SyntheticProvider(manifest))
    extend_followup_provider(provider)
    extend_context_provider(provider)
    extend_goal_provider(provider)
    extend_access_provider(provider)
    ledger = evidence / ("provider-worker-" + args.worker_id + ".json")

    def save_counts():
        _atomic_json(ledger, {"schema": 1, "worker_id": args.worker_id, "pid": os.getpid(),
            "generation": generation, "counts": provider.counts, "utc": _utc()})

    original_handle = provider.handle

    async def recorded_handle(request):
        try:
            return await original_handle(request)
        finally:
            save_counts()  # A hard kill cannot erase a previously handled request.

    provider.handle = recorded_handle
    save_counts()
    watcher_done = threading.Event()
    watchers = []
    with extend_receipt_provider(provider), local_network_only(provider.counts), provider.installed(), ExitStack() as adapters:
        from app.main import app  # noqa: F401 - preserve the original model import order.
        from app import assistant_worker, assistant_runtime_runner as runner
        from app.assistant_runtime_principal import RuntimePrincipal
        from app.db import engine
        from runtime_followup_closeout import observe_followup
        from runtime_context_closeout import observe_context_proof
        from runtime_outbox_closeout import outbox_transaction_faults
        from runtime_source_hooks_closeout import source_hook_faults
        from sqlite_outbox_closeout import observe_outbox
        from runtime_queue_closeout import queue_stream_runner
        adapters.enter_context(observe_followup(manifest))
        adapters.enter_context(observe_context_proof(manifest))
        adapters.enter_context(outbox_transaction_faults(manifest))
        adapters.enter_context(source_hook_faults(manifest))
        adapters.enter_context(observe_outbox(manifest))

        original_save, original_worker = runner._save_preparations, assistant_worker.Worker
        armed = [args.arm_crash]

        def crash_after_commit(db, principal, item_id, *values, **keywords):
            result = original_save(db, principal, item_id, *values, **keywords)
            if armed[0] and result["new_preparations"] > 0:
                armed[0] = False
                _require(type(principal) is RuntimePrincipal and principal.auth_kind == "login"
                         and principal.lease_owner == "worker:" + args.worker_id and principal.run_id,
                         "Crash stage requires the original claimed login principal")
                _require(not (runtime / "preparation-committed.json").exists(), "The single crash stage already exists")
                save_counts()  # Also freeze any blocked connect attempts since the last model response.
                _atomic_json(runtime / "preparation-committed.json", {"schema": 1,
                    "phase": "preparations_committed", "commit_returned": True,
                    "principal_kind": "RuntimePrincipal", "pid": os.getpid(), "worker_id": args.worker_id,
                    "generation": generation, "run_id": principal.run_id, "run_item_id": item_id,
                    "session_id": principal.session_id, "owner_id": principal.actor_id, "store_id": principal.store_id,
                    "owner_role": principal.role, "access_version": principal.access_version, "auth_kind": principal.auth_kind,
                    "lease_owner": principal.lease_owner, "fence": principal.fence, "committed_at": _utc(),
                    "new_preparations": result["new_preparations"],
                    "prepared_rows": [{key: row[key] for key in ("proposal_id", "work_item_id", "input_item_id")}
                                      for row in result["items"] if row["proposal_id"]]})
                while True:
                    time.sleep(1)  # Freeze this event loop after the real commit, until owned PID kill.
            return result

        def watched_worker(*values, **keywords):
            _require('runner' not in keywords, 'Synthetic runner dependency already replaced')
            keywords['runner'] = queue_stream_runner(manifest)
            worker = original_worker(*values, **keywords)
            stop = runtime / ("worker-stop-" + args.worker_id)

            def watch():
                while not watcher_done.wait(0.1):
                    if stop.is_file():
                        worker.stop_signal()  # The original CLI loop's normal shutdown.
                        return

            thread = threading.Thread(target=watch, name="synthetic-worker-stop", daemon=True)
            watchers.append(thread)
            thread.start()
            _atomic_json(runtime / ("worker-ready-" + args.worker_id + ".json"), {
                "schema": 1, "pid": os.getpid(), "worker_id": args.worker_id,
                "generation": generation, "armed": args.arm_crash})
            return worker

        runner._save_preparations = crash_after_commit
        assistant_worker.Worker = watched_worker
        try:
            return assistant_worker.main(["--worker-id", args.worker_id])
        finally:
            watcher_done.set()
            for thread in watchers:
                thread.join(timeout=1)
            runner._save_preparations = original_save
            assistant_worker.Worker = original_worker
            save_counts()
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--arm-crash", action="store_true")
    args = parser.parse_args()
    try:
        return _worker_main(args)
    except Exception as error:
        print(json.dumps({"worker_failed": type(error).__name__}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
