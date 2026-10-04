"""Run the operations review checks from a fresh source-only external mirror."""
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
SOURCE_DIRS = ('app', 'web', 'tests/ops_review')
SOURCE_FILES = ('scripts/huakangos_ops_mail.mjs',)
SUFFIXES = {'.py', '.js', '.mjs', '.css', '.html', '.json', '.md'}

BOOTSTRAP = '''import os, runpy, socket, sys, threading
from pathlib import Path
root = Path(__file__).resolve().parent
os.chdir(root)
sys.path.insert(0, str(root))
def blocked(*args, **kwargs):
    raise RuntimeError('Network is disabled in operations review checks')
original_connect = socket.socket.connect
original_socketpair = socket.socketpair
local = threading.local()
def connect(self, address, *args, **kwargs):
    if (getattr(local, 'socketpair', False) and self.family in (socket.AF_INET, socket.AF_INET6)
            and address[0] in ('127.0.0.1', '::1')):
        return original_connect(self, address, *args, **kwargs)
    return blocked()
def socketpair(*args, **kwargs):
    # Windows implements asyncio's internal pair via a local TCP handshake.
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
sys.argv = ['pytest', '-q', '-p', 'no:cacheprovider', 'tests/ops_review']
runpy.run_module('pytest', run_name='__main__')
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    output = (args.output or Path(tempfile.gettempdir()) / ('huakangos-ops-review-' + uuid.uuid4().hex)).resolve()
    if output.is_relative_to(ROOT) or ROOT.is_relative_to(output):
        parser.error('Output must be outside the repository and its parents')
    if output.exists() and any(output.iterdir()):
        parser.error('Output must be new or empty')
    mirror = output / 'source'
    runtime = output / 'runtime'
    evidence = output / 'evidence'
    for directory in (mirror, runtime, evidence):
        directory.mkdir(parents=True, exist_ok=True)
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--cached',
                                     '--others', '--exclude-standard', '-z']).decode('utf-8').split('\0')
    hashes = {}
    for name in sorted(set(names)):
        relative = Path(name)
        if not name or not (name in SOURCE_FILES or any(name.startswith(d + '/') for d in SOURCE_DIRS)):
            continue
        if relative.suffix not in SUFFIXES or any(p.startswith('.') or p == '__pycache__' for p in relative.parts):
            continue
        source = ROOT / relative
        if not source.is_file():
            continue
        if any(p.is_symlink() for p in [source, *source.parents]) or not source.resolve().is_relative_to(ROOT):
            raise RuntimeError('Refusing a source symlink or external path')
        destination = mirror / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        hashes[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    if not (mirror / 'tests/ops_review/test_worker.py').is_file():
        raise RuntimeError('Operations review tests are missing')
    manifest = {'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip(),
                'source_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
                'files': hashes}
    (evidence / 'source-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (mirror / '_ops_review_bootstrap.py').write_text(BOOTSTRAP, encoding='utf-8')
    # No inherited app/model/mail configuration or credentials enter the child.
    env = {k: v for k, v in os.environ.items() if k in {
        'PATH', 'Path', 'SYSTEMROOT', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT',
        'TMP', 'TEMP', 'TMPDIR', 'LANG', 'LC_ALL'}}
    env.update({'OPS_REVIEW_RUNTIME': str(runtime), 'OPS_REVIEW_ISOLATED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'DATABASE_URL': 'sqlite:///' + (runtime / 'business.sqlite').as_posix(),
                'UPLOAD_DIR': str(runtime / 'uploads'), 'TMP': str(output), 'TEMP': str(output), 'TMPDIR': str(output)})
    commands = [([sys.executable, '-I', '-B', str(mirror / '_ops_review_bootstrap.py')], 'python'),
                ([args.node, str(mirror / 'tests/ops_review/test_mail.mjs')], 'mail')]
    results = []
    for command, label in commands:
        result = subprocess.run(command, cwd=mirror, env=env, text=True, encoding='utf-8',
                                errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (evidence / (label + '.log')).write_text(result.stdout, encoding='utf-8')
        results.append({'check': label, 'exit_code': result.returncode})
        print(result.stdout, end='')
    summary = {'source_sha256': manifest['source_sha256'], 'checks': results,
               'passed': all(r['exit_code'] == 0 for r in results),
               'network': 'Python sockets disabled; Node uses injected sender and loopback only'}
    (evidence / 'result.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('Evidence:', evidence)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
