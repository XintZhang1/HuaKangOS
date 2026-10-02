"""One isolated real-browser click entry point for local review and CI."""
import argparse
import ctypes
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
import urllib.error
import urllib.request
from uuid import uuid4
import secrets

HERE = Path(__file__).resolve().parent
SOURCE_FOLDERS = ("app", "web", "migrations")
SOURCE_FILES = ("requirements.txt", "alembic.ini")
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".sqlite3", ".db", ".log", ".key", ".pem", ".zip"}
SCRIPT_FILES = ("run.py", "fixture_server.py", "provider.py", "scenarios.py", "rubric.json",
                "requirements_click.py", "requirements_manifest.json", "sales_business.py",
                "business_acceptance_catalog.json", "vehicle_purchase_business.py", "master_data_business.py",
                "customer_service_business.py", "sales_order_business.py", "report_business.py", "material_business.py",
                "system_management_business.py", "repair_business.py", "membership_business.py",
                "repair_followon_business.py", "sales_followon_business.py", "finance_business.py", "insurance_business.py",
                "finance_followon_business.py", "system_followon_business.py", "report_followon_business.py",
                "member_followon_business.py", "finance_report_business.py",
                "vehicle_operations_business.py", "warehouse_operations_business.py",
                "boutique_business.py", "member_points_tier_business.py", "customer_followon_business.py",
                "repair_packages_business.py", "interstore_business.py", "repair_claims_business.py", "repair_rework_business.py",
                "report_remaining_business.py", "customer_reminders_business.py", "sales_pdi_business.py", "retail_remaining_business.py",
                "roles_dossier_business.py", "finance_remaining_business.py", "inventory_scope_business.py", "receivables_business.py",
                "report_complete_source_business.py", "pending_ui.py")
EXCLUDED_DIRECTORIES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_output():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    if os.name == "nt":
        root = Path("C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click")
    else:
        root = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "huakangos-browser-click"
    return root / stamp


def verify_output(source, output):
    if output == source or output.is_relative_to(source):
        raise ValueError("All instance data and evidence must stay outside the source repository")
    if output.exists():
        raise ValueError("Output already exists; choose a fresh directory")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.GetVolumePathNameW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
        kernel.GetVolumeInformationW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            wintypes.LPWSTR, wintypes.DWORD)
        volume_root = ctypes.create_unicode_buffer(261)
        fs_name = ctypes.create_unicode_buffer(261)
        if not kernel.GetVolumePathNameW(str(ancestor), volume_root, len(volume_root)):
            raise ValueError("Could not verify the output volume")
        if not kernel.GetVolumeInformationW(volume_root.value, None, 0, None, None, None, fs_name, len(fs_name)):
            raise ValueError("Could not verify the output filesystem")
        if fs_name.value != "NTFS":
            raise ValueError("Windows synthetic instances require an external NTFS directory")


def browser_choice(explicit):
    if explicit:
        selected = Path(explicit).resolve()
        if not selected.is_file():
            raise ValueError("The explicit browser executable does not exist")
        return {"executable": str(selected), "source": "explicit", "playwright_version": version("playwright")}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        selected = Path(playwright.chromium.executable_path).resolve()
    if not selected.is_file():
        raise ValueError("The Playwright browser is missing; install it or pass --browser explicitly")
    return {"executable": str(selected), "source": "playwright-bundled", "playwright_version": version("playwright")}


def source_entries(source):
    paths = [source / name for name in SOURCE_FILES]
    for folder in SOURCE_FOLDERS:
        paths.extend(sorted((source / folder).rglob("*")))
    for path in paths:
        relative = path.relative_to(source)
        if not path.is_file() or EXCLUDED_DIRECTORIES.intersection(relative.parts):
            continue
        if any(part.startswith(".env") for part in relative.parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("Source snapshot refuses external links: " + str(path.relative_to(source)))
        yield relative, path.read_bytes()


def source_inventory(source):
    return {relative.as_posix(): hashlib.sha256(content).hexdigest()
            for relative, content in source_entries(source)}


def script_inventory(directory):
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in SCRIPT_FILES if (directory / name).is_file()}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def changed_paths(before, after):
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def snapshot_source(source, destination):
    inventory = {}
    for relative, content in source_entries(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        inventory[relative.as_posix()] = hashlib.sha256(content).hexdigest()
    required = {"app/main.py", "web/index.html", "migrations/env.py", *SOURCE_FILES}
    if not required.issubset(inventory):
        raise ValueError("Source snapshot is missing required application files")
    return inventory


def child_environment():
    # Do not inherit database URLs, model credentials or preview configuration.
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "LOCALAPPDATA",
            "APPDATA", "USERPROFILE", "HOME", "LANG", "LC_ALL", "TZ", "PLAYWRIGHT_BROWSERS_PATH"}
    result = {key: value for key, value in os.environ.items() if key.upper() in keep}
    result.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    return result


def repository_state(source):
    try:
        head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True, encoding="utf-8", stderr=subprocess.DEVNULL).strip()
        status = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain=v1", "--untracked-files=all"],
                                         text=True, encoding="utf-8", stderr=subprocess.DEVNULL).splitlines()
        return {"head": head, "working_tree_paths": status}
    except (OSError, subprocess.CalledProcessError):
        return {"head": None, "working_tree_paths": None, "reason": "source has no available Git metadata"}


def wait_for_server(server, origin):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(200):
        if server.poll() is not None:
            raise RuntimeError("Synthetic application exited before it became ready; inspect server.log")
        try:
            opener.open(origin + "/api/auth/me", timeout=0.5)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return
            raise RuntimeError("Unexpected response from the new synthetic application") from exc
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
        else:
            raise RuntimeError("A fresh synthetic application should require login")
    raise TimeoutError("Synthetic application did not become ready")


def stop_server(server, runtime):
    if server.poll() is None:
        (runtime / "stop-requested").write_text("Stop this synthetic instance.\n", encoding="utf-8")
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--browser", help="explicit browser executable; no automatic replacement")
    parser.add_argument("--serve", action="store_true", help="keep the synthetic app available for interactive browser review")
    parser.add_argument("--review-after-tests", action="store_true", help="after successful automatic clicks, keep the same synthetic app available until its external stop request")
    parser.add_argument("--scenario", action="append", default=[], help="run a named increment only; repeated names are rejected and no full-suite acceptance is claimed")
    args = parser.parse_args()
    source = args.source.resolve()
    output = (args.output or default_output()).resolve()
    try:
        if args.serve and args.scenario:
            raise ValueError("Interactive review cannot be combined with a scenario selection")
        if args.serve and args.review_after_tests:
            raise ValueError("Post-test review cannot be combined with interactive-only mode")
        if len(args.scenario) != len(set(args.scenario)):
            raise ValueError("Scenario selection contains duplicate names")
        if not (source / "app/main.py").is_file():
            raise ValueError("The selected source has no app/main.py")
        verify_output(source, output)
        browser = browser_choice(args.browser)
        required_scripts = SCRIPT_FILES if not args.serve else SCRIPT_FILES[:3]
        if any(not (HERE / name).is_file() for name in required_scripts):
            raise ValueError("Browser click scripts are incomplete")
    except (ValueError, OSError, ImportError) as exc:
        print("Browser click preflight refused: " + str(exc), file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    source_root, runtime, evidence, scripts = (output / folder for folder in ("source", "runtime", "evidence", "scripts"))
    for directory in (source_root, runtime, evidence, scripts):
        directory.mkdir()
    server = None
    exit_code = 3
    state = {"schema": 1, "mode": "interactive" if args.serve else "automatic", "complete": False,
             "passed": False, "synthetic_data_only": True, "native_transport": True,
             "real_model_calls": 0, "output": str(output), "browser": browser,
             "scope": "selected" if args.scenario else "full_registered",
             "requested_scenarios": args.scenario, "full_registered_suite_complete": False,
             "full193_business_acceptance": False}
    try:
        source_before = source_inventory(source)
        scripts_before = script_inventory(HERE)
        inventory = snapshot_source(source, source_root)
        copied_scripts = {}
        for name in SCRIPT_FILES:
            path = HERE / name
            if path.is_file():
                content = path.read_bytes()
                (scripts / name).write_bytes(content)
                copied_scripts[name] = hashlib.sha256(content).hexdigest()
        source_after = source_inventory(source)
        scripts_after = script_inventory(HERE)
        stable = source_before == inventory == source_after and scripts_before == copied_scripts == scripts_after
        write_json(evidence / "provenance.json", {"schema": 1, "source_root": str(source),
            "source_sha256": fingerprint(inventory), "script_sha256": fingerprint(copied_scripts),
            "source_files": inventory, "script_files": copied_scripts, "python": sys.version,
            "browser": browser, "repository": repository_state(source),
            "snapshot_stable": stable,
            "source_before_sha256": fingerprint(source_before), "source_after_sha256": fingerprint(source_after),
            "script_before_sha256": fingerprint(scripts_before), "script_after_sha256": fingerprint(scripts_after),
            "source_changed_paths": sorted(set(changed_paths(source_before, inventory)
                                               + changed_paths(inventory, source_after))),
            "script_changed_paths": sorted(set(changed_paths(scripts_before, copied_scripts)
                                               + changed_paths(copied_scripts, scripts_after)))})
        if not stable:
            raise RuntimeError("Source or scripts changed while copying; refusing a mixed snapshot before application import")
        credentials_path = runtime / "credentials.json"
        users = {role: {"username": "browser_" + role + "_" + uuid4().hex[:8],
                        "password": secrets.token_urlsafe(24)} for role in ("admin", "sales", "reception", "manager", "sales_peer", "inventory", "finance", "service", "technician")}
        write_json(credentials_path, {"synthetic_data_only": True, "users": users})
        credentials_path.chmod(0o600)
        with socket.socket() as available:
            # Match the server's reusable listener; a bind-only port reservation
            # does not prove Windows will permit the real listener to bind.
            available.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            available.bind(("127.0.0.1", 0))
            available.listen(1)
            port = available.getsockname()[1]
        origin = "http://127.0.0.1:" + str(port)
        manifest_path = output / "manifest.json"
        write_json(manifest_path, {"schema": 1, "synthetic_data_only": True, "origin": origin,
                   "port": port, "source_root": str(source_root), "runtime_root": str(runtime),
                   "evidence_root": str(evidence), "database_path": str(runtime / "synthetic.sqlite"),
                   "credentials_path": str(credentials_path), "browser": browser,
                   "users": {role: {"username": user["username"]} for role, user in users.items()}})
        environment = child_environment()
        fixture_command = [sys.executable, str(scripts / "fixture_server.py"), "--manifest", str(manifest_path)]
        with (evidence / "initialize.log").open("w", encoding="utf-8") as log:
            initialized = subprocess.run(fixture_command + ["--initialize"], cwd=source_root,
                                         env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        if initialized.returncode:
            raise RuntimeError("Synthetic initialization failed; inspect initialize.log")
        with (evidence / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(fixture_command, cwd=source_root, env=environment,
                                      stdout=log, stderr=subprocess.STDOUT)
            wait_for_server(server, origin)
            print("Synthetic browser URL: " + origin, flush=True)
            print("Manifest: " + str(manifest_path), flush=True)
            print("Synthetic usernames: " + ", ".join(user["username"] for user in users.values()), flush=True)
            print("Passwords stay in: " + str(credentials_path), flush=True)
            if args.serve:
                print("Interactive review instance is running; stop this process to close it.", flush=True)
                while server.poll() is None:
                    time.sleep(0.25)
                if (runtime / "stop-requested").is_file() and server.returncode == 0:
                    state.update({"stopped": True, "reason": "Interactive review stopped by its external stop request"})
                    exit_code = 0
                    return exit_code
                raise RuntimeError("The interactive synthetic application stopped without a successful stop request")
            with (evidence / "scenarios.log").open("w", encoding="utf-8") as scenario_log:
                selected_arguments = [value for name in args.scenario for value in ("--scenario", name)]
                result = subprocess.run([sys.executable, str(scripts / "scenarios.py"), "--manifest", str(manifest_path),
                                         "--browser", browser["executable"], *selected_arguments], cwd=scripts, env=environment, timeout=3600,
                                        stdout=scenario_log, stderr=subprocess.STDOUT)
            state["scenario_exit_code"] = result.returncode
            if args.review_after_tests and result.returncode == 0:
                if server.poll() is not None:
                    raise RuntimeError("The synthetic application stopped before post-test review")
                state["post_test_review"] = {"requested": True, "phase": "awaiting_external_stop",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "automatic_evidence_preserved": True, "manual_acceptance": "pending"}
                write_json(evidence / "run-summary.json", state)
                print("Post-test browser review URL: " + origin, flush=True)
                print("Stop request: " + str(runtime / "stop-requested"), flush=True)
                while server.poll() is None:
                    time.sleep(0.25)
                if not (runtime / "stop-requested").is_file() or server.returncode != 0:
                    raise RuntimeError("The post-test synthetic application stopped without a successful stop request")
                state["post_test_review"].update({"phase": "stopped",
                    "stopped_at": datetime.now(timezone.utc).isoformat()})
            stop_server(server, runtime)
        report_path = evidence / "browser-click-report.json"
        if result.returncode:
            raise RuntimeError("Browser click scenarios failed")
        if not report_path.is_file():
            raise RuntimeError("Browser click scenarios did not write their report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report.get("complete") or not report.get("passed") or not report.get("scenarios"):
            raise RuntimeError("Browser click report is incomplete, failed or empty")
        expected = report.get("expected_scenarios")
        executed = [scenario.get("id") for scenario in report["scenarios"]]
        if (not isinstance(expected, list) or not expected or len(expected) != len(set(expected))
                or len(executed) != len(set(executed)) or set(expected) != set(executed)
                or any(scenario.get("status") != "passed" for scenario in report["scenarios"])):
            raise RuntimeError("Expected and executed browser scenarios differ or include an unpassed scenario")
        if report.get("scope") != state["scope"]:
            raise RuntimeError("Browser report scope differs from the requested execution")
        if args.scenario and set(expected) != set(args.scenario):
            raise RuntimeError("Selected browser scenarios differ from the requested names")
        if not args.scenario and report.get("full_registered_suite_complete") is not True:
            raise RuntimeError("Full registered browser suite did not execute completely")
        coverage = report.get("requirements_coverage", {})
        expected_coverage = {"requirements_searched": 193, "guides_displayed": 111,
                             "page_targets_opened": 70, "forms_opened_cancelled": 9}
        if not args.scenario and (coverage.get("complete") is not True or coverage.get("passed") is not True
                or coverage.get("actual_counts") != expected_coverage
                or coverage.get("business_acceptance") is not False):
            raise RuntimeError("Requirement UI coverage is incomplete, failed or misstates business acceptance")
        provider_path = evidence / "provider.json"
        if not provider_path.is_file():
            raise RuntimeError("The synthetic provider did not leave its final network record")
        provider = json.loads(provider_path.read_text(encoding="utf-8"))
        if provider.get("real_model_calls") != 0 or provider.get("blocked_external_attempts") != 0:
            raise RuntimeError("Synthetic network isolation record is missing or reports unexpected traffic")
        state.update({"complete": True, "passed": True, "scenario_count": len(report["scenarios"]),
                      "synthetic_model_requests": provider["synthetic_requests"],
                      "requirements_coverage": coverage,
                      "business_acceptance": report.get("business_acceptance", {}),
                      "full_registered_suite_complete": report["full_registered_suite_complete"]})
        exit_code = 0
    except KeyboardInterrupt:
        state["stopped"] = True
        state["reason"] = "Interactive review was stopped" if args.serve else "Browser run was interrupted"
        exit_code = 0 if args.serve else 3
    except Exception as exc:
        state["reason"] = type(exc).__name__ + ": " + str(exc)
        print("Browser click run failed: " + state["reason"], file=sys.stderr)
    finally:
        if server is not None:
            stop_server(server, runtime)
        write_json(evidence / "run-summary.json", state)
        print("Evidence retained: " + str(evidence), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
