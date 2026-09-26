"""Package the current Git working tree without local data or Git history.

Uses existing tracked files, including local edits, plus the named delivery files.
Run from a Git checkout; never packages .env, virtualenv, caches or databases.
"""
import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    '.dockerignore', '.env.example', '.gitattributes', '.gitignore',
    'AGENTS.md', 'CHECKPOINT_STATUS.json', 'README.md', 'Dockerfile',
    'alembic.ini', 'compose.yml', 'requirements.txt', 'requirements-postgres.txt',
    'start.ps1', 'start.sh', 'start-preview.cmd', 'start-preview.ps1',
}
DIRECTORIES = {'app', 'web', 'migrations', 'scripts', 'docs'}
NEW_FILES = {'scripts/package_source.py', 'docs/业务助手交接.md', 'docs/交付说明.md'}
FORBIDDEN = {'.git', '.venv', '__pycache__', '.pytest_cache', 'data', 'backups',
             'tests', 'maintenance', 'deploy', 'example', 'node_modules'}
FORBIDDEN_SUFFIXES = {'.pyc', '.pyo', '.db', '.sqlite', '.sqlite3', '.log', '.zip', '.pem', '.key'}


def source_files():
    names = set(subprocess.check_output(
        ['git', '-C', str(ROOT), 'ls-files', '-z'], encoding='utf-8').split('\0'))
    names.update(NEW_FILES)
    files = []
    for name in sorted(names):
        if not name:
            continue
        relative = Path(name)
        if name not in ROOT_FILES and relative.parts[0] not in DIRECTORIES:
            continue
        if set(relative.parts) & FORBIDDEN or relative.suffix.lower() in FORBIDDEN_SUFFIXES:
            continue
        if relative.name.startswith('.env') and name != '.env.example':
            continue
        path = ROOT / relative
        if not path.is_file():
            continue  # Working-tree deletions must not reappear from HEAD.
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise SystemExit('Refusing external path or symlink: ' + name)
        files.append((name, path))
    required = ROOT_FILES | NEW_FILES | {
        'app/main.py', 'app/business_assistant_capabilities.json',
        'web/index.html', 'web/workflow-guides.json',
        'scripts/preview_launcher.ps1', 'migrations/env.py',
    }
    missing = required - {name for name, _ in files}
    if missing:
        raise SystemExit('Missing delivery files: ' + ', '.join(sorted(missing)))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = (args.output or ROOT.parent / ('huakangos-source-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.zip')).resolve()
    if output.is_relative_to(ROOT) or output.suffix.lower() != '.zip':
        raise SystemExit('Choose a .zip path outside the repository.')
    if output.exists():
        raise SystemExit('Output exists; refusing to overwrite it.')
    files = source_files()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in files:
            archive.write(path, 'huakangos/' + name)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit('Archive validation failed: ' + bad)
    print('Archive:', output)
    print('Files:', len(files))
    print('SHA256:', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
