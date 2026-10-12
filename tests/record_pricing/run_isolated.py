"""Run focused record-pricing checks in a new source-only external mirror."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ('app', 'web', 'tests/record_pricing', 'tests/record_delivery')
SOURCE_FILES = {'app/assets/sales-contract-2026.pdf'}
SUFFIXES = {'.py', '.js', '.mjs', '.css', '.html', '.json', '.md'}
BOOTSTRAP = '''import os, runpy, socket, sys, threading
from pathlib import Path
root = Path(__file__).resolve().parent
os.chdir(root)
sys.path.insert(0, str(root))
def blocked(*args, **kwargs):
    raise RuntimeError('Network is disabled in record-pricing checks')
original_connect, original_socketpair = socket.socket.connect, socket.socketpair
local = threading.local()
def connect(self, address, *args, **kwargs):
    if (getattr(local, 'socketpair', False) and self.family in (socket.AF_INET, socket.AF_INET6)
            and address[0] in ('127.0.0.1', '::1')):
        return original_connect(self, address, *args, **kwargs)
    return blocked()
def socketpair(*args, **kwargs):
    local.socketpair = True
    try:
        return original_socketpair(*args, **kwargs)
    finally:
        local.socketpair = False
socket.socketpair = socketpair
socket.socket.connect = connect
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
sys.argv = ['pytest', '-q', '-p', 'no:cacheprovider',
    '--basetemp=' + os.environ['RECORD_PRICING_RUNTIME'] + '/pytest',
    '--junitxml=' + os.environ['RECORD_PRICING_EVIDENCE'] + '/junit.xml',
    os.environ['RECORD_TEST_SUITE']]
runpy.run_module('pytest', run_name='__main__')
'''


def inventory():
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--cached',
        '--others', '--exclude-standard', '-z']).decode('utf-8').split('\0')
    result = {}
    for name in sorted(set(names)):
        relative = Path(name)
        if not name or not (name in SOURCE_FILES or any(name.startswith(folder + '/') for folder in SOURCE_DIRS)):
            continue
        if (relative.suffix not in SUFFIXES and name not in SOURCE_FILES) or any(p.startswith('.') or p == '__pycache__' for p in relative.parts):
            continue
        source = ROOT / relative
        if not source.is_file():
            continue
        if any(p.is_symlink() for p in [source, *source.parents]) or not source.resolve().is_relative_to(ROOT):
            raise RuntimeError('Refusing a source symlink or external path')
        result[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--suite', choices=('pricing', 'delivery'), default='pricing')
    args = parser.parse_args()
    output = (args.output or Path(tempfile.gettempdir()) / ('huakangos-record-pricing-' + uuid.uuid4().hex)).resolve()
    if output.is_relative_to(ROOT) or ROOT.is_relative_to(output):
        parser.error('Output must be outside the repository and its parents')
    if output.exists() and any(output.iterdir()):
        parser.error('Output must be new or empty')
    mirror, runtime, evidence = (output / name for name in ('source', 'runtime', 'evidence'))
    for directory in (mirror, runtime, evidence):
        directory.mkdir(parents=True, exist_ok=True)
    (runtime / 'disabled-model.json').write_text(json.dumps({'enabled': False, 'synthetic': True}), encoding='utf-8')
    before = inventory()
    for name in before:
        destination = mirror / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    copied = {name: hashlib.sha256((mirror / name).read_bytes()).hexdigest() for name in before}
    after = inventory()
    manifest = {'synthetic_data_only': True, 'suite': args.suite,
        'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip(),
        'source_sha256': hashlib.sha256(json.dumps(copied, sort_keys=True).encode()).hexdigest(),
        'snapshot_stable': before == copied == after, 'files': copied}
    (evidence / 'source-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if not manifest['snapshot_stable']:
        raise RuntimeError('Source changed during mirroring; evidence retained, no tests started')
    (mirror / '_record_pricing_bootstrap.py').write_text(BOOTSTRAP, encoding='utf-8')
    # Never inherit application/model credentials or deployment configuration.
    env = {k: v for k, v in os.environ.items() if k in {
        'PATH', 'Path', 'SYSTEMROOT', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT',
        'TMP', 'TEMP', 'TMPDIR', 'LANG', 'LC_ALL'}}
    env.update({'RECORD_PRICING_RUNTIME': str(runtime), 'RECORD_PRICING_EVIDENCE': str(evidence),
        'RECORD_PRICING_ISOLATED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'RECORD_TEST_SUITE': 'tests/record_delivery/test_delivery_api.py' if args.suite == 'delivery' else 'tests/record_pricing/test_pricing_api.py',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'APP_ENV': 'test',
        'DATABASE_URL': 'sqlite:///' + (runtime / 'unused.sqlite').as_posix(),
        'FILE_SCAN_MODE': 'structure_only', 'FILE_STORAGE_MODE': 'blob',
        'SCHEDULER_ENABLED': 'false', 'SCHEDULER_MODE': 'off',
        'ALLOW_AI_EXTERNAL': 'false', 'BUSINESS_ASSISTANT_CONFIG': str(runtime / 'disabled-model.json'),
        'TMP': str(runtime), 'TEMP': str(runtime), 'TMPDIR': str(runtime)})
    result = subprocess.run([sys.executable, '-I', '-B', str(mirror / '_record_pricing_bootstrap.py')],
        cwd=mirror, env=env, text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (evidence / 'python.log').write_text(result.stdout, encoding='utf-8')
    summary = {'synthetic_data_only': True, 'suite': args.suite, 'source_sha256': manifest['source_sha256'],
        'passed': result.returncode == 0, 'exit_code': result.returncode,
        'network': 'All Python network sockets blocked; in-process ASGI transport only',
        'real_model_calls': 0, 'database': 'Fresh ORM-created SQLite; not a migration acceptance test'}
    (evidence / 'result.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(result.stdout, end='')
    print('Evidence:', evidence)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
