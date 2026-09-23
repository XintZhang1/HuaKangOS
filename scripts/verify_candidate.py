"""Run every pytest module against one frozen source tree, using isolated processes."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def source_manifest():
    files = []
    for folder in ('app', 'web', 'migrations', 'tests', 'scripts'):
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and not {'__pycache__', '.pytest_cache'} & set(p.parts)
                     and p.suffix != '.pyc')
    files.extend(p for p in ROOT.iterdir() if p.is_file() and
                 (p.name.startswith(('requirements', 'start')) or p.name in {'alembic.ini', 'Dockerfile', 'compose.yml'}))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('测试日志及合成证据必须保存在源码目录之外')
    output.mkdir(parents=True, exist_ok=False)
    modules = sorted({p.relative_to(ROOT).as_posix() for pattern in ('test_*.py', '*_test.py')
                      for p in (ROOT/'tests').rglob(pattern) if '__pycache__' not in p.parts})
    partitions = [modules[index::args.workers] for index in range(args.workers)]
    before = source_manifest()
    (output/'source-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    started = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'FILE_STORAGE_MODE': 'blob', 'PRIVATE_FILE_ROOT': '', 'PYTEST_ADDOPTS': '',
           'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}

    def run(index, group):
        report = output/f'part-{index}.xml'
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   '--junitxml='+str(report), *group]
        (output/f'part-{index}-command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2), encoding='utf-8')
        with (output/f'part-{index}.log').open('w', encoding='utf-8') as log:
            done = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        counts = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
        if report.exists():
            root = ET.parse(report).getroot()
            suites = [root] if root.tag == 'testsuite' else root.findall('testsuite')
            for suite in suites:
                for key in counts:
                    counts[key] += int(suite.get(key, 0))
        result = {'partition': index, 'modules': group, 'returncode': done.returncode, **counts}
        print(json.dumps({k: v for k, v in result.items() if k != 'modules'}, ensure_ascii=False), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = [job.result() for job in as_completed([pool.submit(run, index+1, group)
                                                       for index, group in enumerate(partitions) if group])]
    after = source_manifest()
    (output/'source-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    counts = {key: sum(item[key] for item in results) for key in ('tests', 'failures', 'errors', 'skipped')}
    status = 'passed' if not changed and all(r['returncode'] == 0 for r in results) else 'failed'
    summary = {'status': status, 'started_utc': started, 'seconds': round(time.monotonic()-start, 2),
               'python': sys.version, 'platform': platform.platform(), 'module_count': len(modules),
               'source_file_count': len(before), 'source_changed': changed,
               'source_digest': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
               'passed': counts['tests']-counts['failures']-counts['errors']-counts['skipped'],
               **counts, 'partitions': sorted(results, key=lambda r: r['partition'])}
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'partitions'}, ensure_ascii=False), flush=True)
    raise SystemExit(0 if status == 'passed' else 1)


if __name__ == '__main__':
    main()
