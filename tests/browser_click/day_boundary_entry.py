"""Resume a passed full synthetic instance for one natural-date UI phase.

The original manifest/database/source/scripts remain fixed. This narrow entry
does not initialize, migrate, start a Runtime worker or overwrite full evidence.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import day_boundary_business as D
import fixture_server as F
import run as R
from provider import SyntheticProvider, local_network_only
from scenarios import Database, Evidence, require

PHASES = {"stage": (D.STAGE, D.day_boundary_stage), "verify": (D.VERIFY, D.day_boundary_verify)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def inventory(folder):
    result = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            require(not path.is_symlink() and path.resolve().is_relative_to(folder), "phase 不能追随外部证据链接")
            result[path.relative_to(folder).as_posix()] = sha(path)
    return result


def worker_facts(database):
    # SELECT-only facts detect any unexpected worker marker or queue claim.
    marker = database.rows("SELECT * FROM app_metadata WHERE key LIKE 'assistant_runtime_worker:%' ORDER BY key")
    runs = database.rows("SELECT * FROM business_assistant_runs ORDER BY id")
    return {"worker_marker_count": len(marker), "worker_marker_sha256": digest(marker),
        "run_count": len(runs), "all_run_rows_sha256": digest(runs)}


def preflight(manifest_path, phase):
    require(phase in PHASES, "未知自然跨日 phase")
    manifest_path = manifest_path.resolve()
    manifest = F.read_instance(manifest_path)
    require(manifest_path == Path(manifest["runtime_root"]).resolve().parent / "manifest.json", "必须复用原实例唯一 manifest.json")
    mirror = D.fixed_mirror(manifest)
    require(Path(__file__).resolve().parent == Path(manifest["runtime_root"]).resolve().parent / "scripts", "入口必须运行已镜像固定脚本")
    provenance = json.loads((Path(manifest["evidence_root"]) / "provenance.json").read_text(encoding="utf-8"))
    instance_root = Path(manifest["runtime_root"]).resolve().parent
    repository_root = Path(provenance["source_root"]).resolve()
    require(instance_root != repository_root and not instance_root.is_relative_to(repository_root), "phase 数据/证据必须保留在原仓库外")
    require(provenance["script_files"].get(Path(__file__).name) == sha(__file__), "窄入口未登记在原镜像清单")
    require(R.source_inventory(Path(manifest["source_root"])) == provenance["source_files"]
        and R.script_inventory(Path(__file__).parent) == provenance["script_files"], "原 source/scripts 完整清单不一致")
    evidence = Path(manifest["evidence_root"])
    summary = json.loads((evidence / "run-summary.json").read_text(encoding="utf-8"))
    full = json.loads((evidence / "browser-click-report.json").read_text(encoding="utf-8"))
    provider = json.loads((evidence / "provider.json").read_text(encoding="utf-8"))
    require(summary.get("complete") is True and summary.get("passed") is True
        and summary.get("scope") == "full_registered" and summary.get("full_registered_suite_complete") is True
        and summary.get("service_shutdown") == {"returncode": 0, "forced": False}, "只能复用已完整通过且正常关闭的 full 实例")
    names = full.get("expected_scenarios")
    require(full.get("complete") is True and full.get("passed") is True
        and full.get("full_registered_suite_complete") is True and full.get("scope") == "full_registered"
        and isinstance(names, list) and names and len(names) == len(set(names))
        and [r["id"] for r in full.get("scenarios", [])] == names
        and all(r.get("status") == "passed" for r in full["scenarios"]), "原 full 不能缺项、失败或冒充完整")
    require(provider.get("real_model_calls") == provider.get("blocked_external_attempts") == 0, "原 full 外网隔离证据不符")
    require(Path(manifest["database_path"]).is_file() and Path(manifest["credentials_path"]).is_file(), "原合成数据库或密码文件缺失")
    credentials = json.loads(Path(manifest["credentials_path"]).read_text(encoding="utf-8"))
    require(credentials.get("synthetic_data_only") is True and isinstance(credentials.get("users"), dict), "密码必须是原合成实例来源")
    config = json.loads((Path(manifest["runtime_root"]) / "synthetic-assistant.json").read_text(encoding="utf-8"))
    require(config.get("synthetic") is True and config.get("api_key") == "SYNTHETIC-NOT-A-CREDENTIAL", "禁止真实模型配置进入日期阶段")
    origin = urlsplit(manifest["origin"])
    require(origin.hostname == "127.0.0.1" and origin.scheme == "http" and origin.port == manifest["port"], "必须保留原本机同源监听地址和端口")
    if phase == "verify":
        D.resume_checkpoint(manifest)
    return manifest, credentials, {"manifest_sha256": sha(manifest_path), "mirror": mirror,
        "original_full_report_sha256": sha(evidence / "browser-click-report.json"),
        "original_full_summary_sha256": sha(evidence / "run-summary.json"),
        "original_full_provider_sha256": sha(evidence / "provider.json"),
        "full_scenario_count": len(names), "original_full_normal_shutdown": True}


def phase_paths(manifest, phase):
    return (Path(manifest["runtime_root"]) / "day-boundary-entry" / phase,
        Path(manifest["evidence_root"]) / ("day-boundary-entry-" + phase))


def original_inventory(manifest):
    runtime = Path(manifest["runtime_root"]).resolve()
    database = Path(manifest["database_path"]).resolve()
    auxiliaries = {str(database) + suffix for suffix in ("", "-wal", "-shm", "-journal")}
    runtime_files = {name: value for name, value in inventory(runtime).items()
        if str((runtime / name).resolve()) not in auxiliaries}
    return {"evidence": inventory(Path(manifest["evidence_root"]).resolve()), "runtime": runtime_files}


def originals_unchanged(manifest, original, allowed_evidence, allowed_runtime):
    results = {}
    for kind, root, allowed in (("evidence", Path(manifest["evidence_root"]).resolve(), allowed_evidence),
        ("runtime", Path(manifest["runtime_root"]).resolve(), allowed_runtime)):
        before = original[kind]
        current = inventory(root)
        require(all(current.get(name) == expected for name, expected in before.items()), "覆盖或删除了 phase 前原 " + kind + " 证据/配置")
        additions = set(current) - set(before)
        if kind == "runtime":
            database = Path(manifest["database_path"]).resolve()
            additions = {name for name in additions if str((root / name).resolve()) not in
                {str(database) + suffix for suffix in ("", "-wal", "-shm", "-journal")}}
        require(all(any((root / name).resolve().is_relative_to(folder) for folder in allowed) for name in additions),
            "phase 在准许独立目录以外追加了 " + kind + " 文件")
        results[kind] = {"preexisting_files": len(before), "all_preexisting_sha256_unchanged": True,
            "preexisting_inventory_sha256": digest(before), "new_phase_files": len(additions)}
    return results


def assert_free_port(manifest):
    # Never connect a phase browser to a service that the entry does not own.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", manifest["port"]))
        probe.listen(1)


def server_main(args):
    manifest, _, prior = preflight(args.manifest, args.phase)
    control, evidence = phase_paths(manifest, args.phase)
    require(args.control and args.control.resolve() == control.resolve() and control.is_dir() and evidence.is_dir(), "phase server 控制目录不是本次明确范围")
    request = json.loads((control / "request.json").read_text(encoding="utf-8"))
    require(request.get("schema") == 1 and request.get("phase") == args.phase
        and request.get("source_provenance") == prior and isinstance(request.get("nonce"), str)
        and len(request["nonce"]) == 32 and not (control / "stop-requested").exists(), "phase server 请求身份或停机状态不符")
    F.configure_environment(manifest, initialize=False)
    require(os.environ["SCHEDULER_ENABLED"] == "false" and os.environ["SCHEDULER_MODE"] == "off"
        and os.environ["HUAKANGOS_LOCAL_PREVIEW"] == "0", "原隔离配置没有关闭后台作业")
    provider = SyntheticProvider(manifest)
    lifecycle = {"schema": 1, "phase": args.phase, "nonce": request["nonce"], "pid": os.getpid(),
        "origin": manifest["origin"], "database_path": manifest["database_path"], "initialized": False,
        "migrated": False, "intentional_runtime_workers_started": 0, "started": False, "finished": False,
        "runtime_worker_deployment_acceptance": False, "source_provenance": prior}
    with local_network_only(provider.counts), provider.installed():
        # Only after exact external paths/configuration have been checked.
        import app.main as main
        from app.config import settings
        from app.db import engine
        import uvicorn

        require(settings.environment == "test" and settings.timezone == "Asia/Shanghai"
            and not settings.scheduler_enabled and settings.scheduler_mode == "off"
            and not settings.allow_ai and main._EMBEDDED_WORKER is None and main.scheduler.thread is None,
            "原 app 实際配置或初始后台状态不符")
        original_lifespan = main.app.router.lifespan_context
        server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=manifest["port"],
            log_level="warning", access_log=False))

        async def watch_phase():
            while not server.started:
                await asyncio.sleep(0.05)
            require(main._EMBEDDED_WORKER is None and main.scheduler.thread is None, "原 app lifespan 意外启动后台 worker/定时作业")
            lifecycle.update(started=True, actual_embedded_worker_present=False, actual_report_scheduler_thread_present=False,
                scheduler_mode=settings.scheduler_mode, local_preview=os.environ["HUAKANGOS_LOCAL_PREVIEW"],
                started_at_utc=datetime.now(timezone.utc).isoformat())
            write_json(control / "ready.json", lifecycle)
            while not (control / "stop-requested").exists():
                await asyncio.sleep(0.1)
            server.should_exit = True

        @asynccontextmanager
        async def phase_lifespan(application):
            async with original_lifespan(application):
                require(main._EMBEDDED_WORKER is None and main.scheduler.thread is None, "原 lifespan 不满足纯日期阶段后台边界")
                watching = asyncio.create_task(watch_phase())
                try:
                    yield
                finally:
                    watching.cancel()
                    result = await asyncio.gather(watching, return_exceptions=True)
                    if result and isinstance(result[0], BaseException) and not isinstance(result[0], asyncio.CancelledError):
                        raise result[0]
            require(main._EMBEDDED_WORKER is None and main.scheduler.thread is None, "phase 关闭时原 app 后台边界变化")
            lifecycle.update(finished=True, actual_embedded_worker_present=False,
                actual_report_scheduler_thread_present=False, finished_at_utc=datetime.now(timezone.utc).isoformat())

        main.app.router.lifespan_context = phase_lifespan
        try:
            server.run()
        finally:
            write_json(evidence / "provider.json", provider.counts)
            write_json(evidence / "server-lifecycle.json", lifecycle)
            engine.dispose()
    return 0 if lifecycle["started"] and lifecycle["finished"] else 3


async def native_phase(manifest, credentials, phase):
    from playwright.async_api import async_playwright

    name, function = PHASES[phase]
    secrets = [v for user in credentials["users"].values() for k, v in user.items() if k == "password" and isinstance(v, str)]
    e = Evidence(manifest, secrets, name)
    result = {"name": name, "phase": phase, "status": "failed", "real_model_calls": 0,
        "transport": "actual_browser_same_origin_cookie_csrf_original_ui", "runtime_worker_deployment_acceptance": False}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=manifest["browser"]["executable"], headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        page = await context.new_page()
        page.set_default_timeout(15000)
        await e.attach(context, page)
        started = time.monotonic()
        try:
            await asyncio.wait_for(function(e, context, credentials), timeout=1200)
            if e.response_jobs:
                await asyncio.gather(*list(e.response_jobs))
            require(e.actions and any(a["kind"] == "click" for a in e.actions), "空原浏览器 phase 不能通过")
            require(not e.page_errors and not e.external_requests, "phase 页面异常或浏览器外网尝试")
            require(not any(r["event"] == "response" and r["status"] >= 500 for r in e.network), "原业务 HTTP 出现 5xx")
            checkpoint = json.loads((e.directory / "business-checkpoint.json").read_text(encoding="utf-8"))
            if phase == "stage":
                require(checkpoint.get("stage_complete") is True and checkpoint.get("natural_boundary_verified") is False
                    and checkpoint.get("passed") is False and checkpoint.get("status") == "waiting_real_shanghai_d_plus_one",
                    "stage 不能冒称自然跨日已通过")
                result.update(status="staged_waiting_real_date", natural_boundary_verified=False)
            else:
                require(checkpoint.get("complete") is True and checkpoint.get("passed") is True
                    and checkpoint.get("natural_boundary_verified") is True
                    and checkpoint.get("hk099", {}).get("status") == checkpoint.get("hk152", {}).get("status") == "passed",
                    "两个独立原合同未完整实测")
                result.update(status="passed", natural_boundary_verified=True)
            result.update(actual_browser_version=browser.version, playwright_version=version("playwright"))
        except BaseException as error:
            result["error"] = e.scrub(type(error).__name__ + ": " + str(error))
            try:
                await e.snapshot("day-boundary-entry-failure")
            except Exception as screenshot_error:
                result["screenshot_error"] = e.scrub(type(screenshot_error).__name__)
        finally:
            result.update(await e.finish())
            result["duration_seconds"] = round(time.monotonic() - started, 2)
            await context.close()
            await browser.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="existing passed full instance manifest; never initialized again")
    parser.add_argument("--phase", choices=tuple(PHASES), required=True)
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--control", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.server:
        return server_main(args)
    server = None
    owns_evidence = False
    state = {"schema": 1, "phase": args.phase, "complete": False, "passed": False,
        "phase_completed": False, "phase_passed": False, "natural_boundary_verified": False,
        "synthetic_data_only": True, "human_acceptance": "pending", "full193_business_acceptance": False,
        "runtime_worker_deployment_acceptance": False, "initialized": False, "migrated": False,
        "real_model_calls": 0, "runtime_workers_started": 0}
    try:
        manifest, credentials, source = preflight(args.manifest, args.phase)
        control, evidence = phase_paths(manifest, args.phase)
        phase_directory = Path(manifest["evidence_root"]) / PHASES[args.phase][0]
        require(not control.exists() and not evidence.exists() and not phase_directory.exists(), "已有 phase 原件：停止，不能覆盖、重放或自动重建")
        assert_free_port(manifest)
        original = original_inventory(manifest)
        database = Database(manifest["database_path"])
        workers_before = worker_facts(database)
        state.update(source_provenance=source, original_worker_facts=workers_before,
            browser=manifest["browser"], started_at_utc=datetime.now(timezone.utc).isoformat())
        control.mkdir(parents=True, exist_ok=False)
        evidence.mkdir(exist_ok=False)
        owns_evidence = True
        write_json(evidence / "preexisting-originals.json", original)
        nonce = uuid4().hex
        write_json(control / "request.json", {"schema": 1, "phase": args.phase, "nonce": nonce, "source_provenance": source})
        with (evidence / "server.log").open("x", encoding="utf-8") as log:
            executable, environment = sys.executable, R.child_environment()
            # Match the established physical-PID launch used by the queue CLI:
            # Windows' venv redirector can otherwise create a second process.
            if os.name == "nt" and sys.prefix != sys.base_prefix:
                executable = getattr(sys, "_base_executable", None)
                require(executable and Path(executable).is_file(), "phase 缺少真实 base interpreter")
                environment["__PYVENV_LAUNCHER__"] = sys.executable
            command = [executable, str(Path(__file__).resolve()), "--manifest", str(args.manifest.resolve()),
                "--phase", args.phase, "--server", "--control", str(control)]
            server = subprocess.Popen(command, cwd=manifest["source_root"], env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            R.wait_for_server(server, manifest["origin"])
            deadline = time.monotonic() + 10
            while not (control / "ready.json").is_file():
                require(server.poll() is None and time.monotonic() < deadline, "phase 没有本次真实服务启动凭据")
                time.sleep(0.05)
            ready = json.loads((control / "ready.json").read_text(encoding="utf-8"))
            require(ready["pid"] == server.pid and ready["nonce"] == nonce and ready["started"] is True
                and ready["source_provenance"] == source and ready["intentional_runtime_workers_started"] == 0
                and ready["actual_embedded_worker_present"] is False and ready["actual_report_scheduler_thread_present"] is False,
                "浏览器服务不是本次 owned PID 或意外启动了后台作业")
            require(worker_facts(database) == workers_before, "原 app 启动改变了旧 worker/Run 事实")
            state["native_phase"] = asyncio.run(native_phase(manifest, credentials, args.phase))
            state["service_shutdown"] = R.stop_server(server, control)
        require(state["service_shutdown"] == {"returncode": 0, "forced": False}, "phase 关闭失败或需要强制终止")
        lifecycle = json.loads((evidence / "server-lifecycle.json").read_text(encoding="utf-8"))
        provider = json.loads((evidence / "provider.json").read_text(encoding="utf-8"))
        require(lifecycle["pid"] == server.pid and lifecycle["nonce"] == nonce
            and lifecycle["started"] is True and lifecycle["finished"] is True
            and lifecycle["intentional_runtime_workers_started"] == 0
            and provider.get("real_model_calls") == provider.get("blocked_external_attempts") == provider.get("synthetic_requests") == 0,
            "纯日期/流水阶段后台或模型隔离证据不符")
        require(worker_facts(database) == workers_before, "日期阶段意外更新了旧 worker/Run 或创建新 Run")
        state["originals_protection"] = originals_unchanged(manifest, original, {evidence.resolve(), phase_directory.resolve()}, {control.resolve()})
        require(sha(args.manifest.resolve()) == source["manifest_sha256"] and D.fixed_mirror(manifest) == source["mirror"], "phase 改动了原 manifest/source/scripts")
        require(state["native_phase"]["status"] == ("staged_waiting_real_date" if args.phase == "stage" else "passed"), "实际浏览器 phase 未通过，保留失败原件")
        state.update(phase_completed=True, phase_passed=True, all_original_worker_and_run_rows_unchanged=True,
            lifecycle_evidence=str(evidence / "server-lifecycle.json"), provider_evidence=str(evidence / "provider.json"))
        if args.phase == "verify":
            state.update(complete=True, passed=True, natural_boundary_verified=True)
        exit_code = 0
    except BaseException as error:
        state["error"] = type(error).__name__ + ": " + str(error)[:2000]
        print("Day boundary phase failed: " + type(error).__name__, file=sys.stderr)
        exit_code = 3
    finally:
        if server is not None and server.poll() is None:
            shutdown = R.stop_server(server, control)
            state.setdefault("service_shutdown", shutdown)
            state.update(complete=False, passed=False, phase_completed=False, phase_passed=False)
        if owns_evidence:
            state["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(evidence / "phase-summary.json", state)
            print("Independent phase evidence: " + str(evidence), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
