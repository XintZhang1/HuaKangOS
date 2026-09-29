"""M8.4 entry point: one real-browser acceptance run with verified evidence.

This is the single command a reviewer runs to obtain real-HTTP browser evidence
for the current source tree. It never substitutes a transport: `native` is a
real loopback navigation with the application's own cookies, fetch and network
SSE, and `fixture` is the explicit in-page bridge that must never be described
as native acceptance. A failed native run stays failed; the pipeline does not
retry it as `fixture`.

Isolation contract (unchanged, inherited from run_isolated.py):
  * the suite is copied to a brand-new directory outside the source tree;
  * the source must not carry a `.env`, and no real database is ever opened;
  * the model provider is deterministic synthetic content (0 real model calls);
  * evidence is never overwritten, so every run keeps its own directory.

Exit codes: 0 verified, 2 preflight refused, 3 execution failed,
4 evidence incomplete or contradictory.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROWSER_CANDIDATES = (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
)


def refuse(message):
    print('PIPELINE REFUSED: ' + message, file=sys.stderr)
    return 2


def find_browser(explicit, bundled=None):
    """Resolve the browser in a deliberate order, and say where it came from.

    The Playwright-managed browser is the pinned one CI installs, so it wins
    over whatever the host happens to ship; otherwise a runner image with a
    system Chromium would silently substitute a different browser for the
    pinned one. An explicit choice still overrides everything.
    """
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ValueError('The supplied browser executable does not exist: ' + str(path))
        return str(path), 'explicit'
    from_env = os.environ.get('HUAKANGOS_CHROMIUM')
    if from_env:
        if not Path(from_env).is_file():
            raise ValueError('HUAKANGOS_CHROMIUM does not exist: ' + from_env)
        return from_env, 'environment'
    if bundled and Path(bundled).is_file():
        return str(bundled), 'playwright-bundled'
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).is_file():
            return candidate, 'system-candidate'
    return None, None


def playwright_state():
    """Report whether the driver and a bundled browser are usable."""
    try:
        import playwright
    except ImportError:
        return {'installed': False, 'version': None, 'bundled': None}
    try:
        from importlib.metadata import version as distribution_version
        version = distribution_version('playwright')
    except Exception:                             # source checkout without metadata
        version = getattr(playwright, '__version__', None)
    bundled = None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as started:
            candidate = Path(started.chromium.executable_path)
            # The driver reports the expected path even when the browser was
            # never downloaded, so only an existing file counts as available.
            bundled = str(candidate) if candidate.is_file() else None
    except Exception as exc:                      # driver or registry unavailable
        return {'installed': True, 'version': version, 'bundled': None,
                'driver_error': type(exc).__name__ + ': ' + str(exc)}
    return {'installed': True, 'version': version, 'bundled': bundled}


def source_fingerprint(source):
    digest = hashlib.sha256()
    for folder in ('app', 'web', 'migrations'):
        for path in sorted((source / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                digest.update(str(path.relative_to(source)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def bucket(browser_mode):
    return 'browser-native' if browser_mode == 'native' else 'browser-fixture'


def default_output(browser_mode):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for root in (Path('C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1'),
                 Path(os.environ.get('TEMP', '.'))):
        if root.is_dir():
            break
    else:
        root = Path(os.environ.get('TEMP', '.'))
    return (root / 'browser' / (bucket(browser_mode) + '-' + stamp)).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, default=HERE.parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--browser-mode', choices=('native', 'fixture'), default='native')
    parser.add_argument('--browser', help='explicit browser executable for the real run')
    args = parser.parse_args()
    source = args.source.resolve()
    if not (source / 'app/main.py').is_file():
        return refuse('the source tree has no app/main.py: ' + str(source))
    if (source / '.env').exists():
        return refuse('the source tree carries a .env; use a disposable checkout')
    if not (HERE / 'run_isolated.py').is_file():
        return refuse('run_isolated.py is missing next to the pipeline')
    output = (args.output or default_output(args.browser_mode)).resolve()
    if output.is_relative_to(source):
        return refuse('the output directory must stay outside the source tree')
    if output.exists():
        return refuse('choose a new output path; evidence is never overwritten')
    state = playwright_state()
    if not state['installed']:
        return refuse('playwright is not installed for this interpreter')
    try:
        browser, origin_of_choice = find_browser(args.browser, state.get('bundled'))
    except ValueError as exc:
        return refuse(str(exc))
    if browser is None:
        return refuse('no browser available: install playwright chromium or pass --browser')
    environment = {
        'schema': 1,
        'milestone': 'M8.4',
        'browser_mode': args.browser_mode,
        'native_transport': args.browser_mode == 'native',
        'origin': 'http://127.0.0.1:8765',
        'synthetic_data_only': True,
        'real_model_calls': 0,
        'python': sys.version,
        'playwright_version': state.get('version'),
        'browser_executable': browser,
        'browser_source': origin_of_choice,
        'browser_explicit': bool(browser),
        'source': str(source),
        'source_sha256_prefix': source_fingerprint(source)[:16],
    }
    command = [sys.executable, str(HERE / 'run_isolated.py'), '--source', str(source),
               '--output', str(output), '--browser-mode', args.browser_mode]
    # The browser choice must reach the harness explicitly; the pipeline never
    # relies on whatever the ambient environment happens to contain.
    child_environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
    if environment['browser_executable']:
        child_environment['HUAKANGOS_CHROMIUM'] = str(environment['browser_executable'])
    environment_path = output.parent / (output.name + '.environment.json')
    print('Pipeline output: ' + str(output), flush=True)
    print('Browser: ' + str(environment['browser_executable']), flush=True)
    result = subprocess.run(command, cwd=str(HERE.parents[1]), env=child_environment)
    environment_path.write_text(json.dumps(environment, ensure_ascii=False, indent=2),
                                encoding='utf-8')
    if result.returncode != 0:
        print('PIPELINE FAILED: the isolated run exited ' + str(result.returncode), file=sys.stderr)
        return 3
    evidence = output / 'evidence'
    summary_path = evidence / 'run-summary.json'
    bundle_path = evidence / 'browser-evidence.json'
    if not summary_path.is_file() or not bundle_path.is_file():
        print('PIPELINE FAILED: the run left no summary or browser bundle', file=sys.stderr)
        return 4
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    problems = []
    if summary.get('browser_transport') != args.browser_mode:
        problems.append('transport mismatch: ' + str(summary.get('browser_transport')))
    if args.browser_mode == 'native' and not summary.get('complete'):
        problems.append('the native run did not complete the full scope')
    if bundle.get('mode') != args.browser_mode or bundle.get('page_count', 0) < 1:
        problems.append('the browser bundle does not match the executed mode')
    if args.browser_mode == 'native':
        if not bundle.get('native_transport'):
            problems.append('the bundle does not assert native transport')
        if bundle.get('page_errors_total'):
            problems.append('pages reported errors: ' + str(bundle['page_errors_total']))
        context = bundle.get('environment') or {}
        if not context.get('browser_version'):
            problems.append('the browser version was not recorded')
        if not context.get('csp_script_src_self'):
            problems.append('the application CSP was not observed')
    if summary.get('real_model_calls'):
        problems.append('real model calls were reported')
    pipeline = {
        'schema': 1,
        'milestone': 'M8.4',
        'verified': not problems,
        'problems': problems,
        'browser_mode': args.browser_mode,
        'native_transport': args.browser_mode == 'native',
        'output': str(output),
        'evidence': str(evidence),
        'environment': environment,
        'run': {'complete': summary.get('complete'), 'scope': summary.get('scope'),
                'counts': summary.get('counts'),
                'browser_transport': summary.get('browser_transport'),
                'real_model_calls': summary.get('real_model_calls')},
        'browser': {'page_count': bundle.get('page_count'),
                    'page_errors_total': bundle.get('page_errors_total'),
                    'browser_version': (bundle.get('environment') or {}).get('browser_version')},
        'release_accepted': False,
    }
    (output / 'browser-pipeline.json').write_text(
        json.dumps(pipeline, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(pipeline, ensure_ascii=False, indent=2))
    if problems:
        print('PIPELINE EVIDENCE INCOMPLETE: ' + '; '.join(problems), file=sys.stderr)
        return 4
    print('PIPELINE VERIFIED: ' + str(output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())