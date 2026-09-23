"""Standard-library checks shared by the Windows launcher and serving process."""
import argparse
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = ('fastapi', 'starlette', 'uvicorn', 'sqlalchemy', 'pydantic', 'httpx',
           'argon2', 'dotenv', 'alembic', 'tzdata', 'docx', 'multipart', 'PIL')


def source_identity(repository=ROOT):
    repository = Path(repository).resolve()
    canonical = os.path.normcase(str(repository)).rstrip('\\/')
    repository_id = hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:20]
    digest = hashlib.sha256()
    files = []
    for folder in ('app', 'web', 'migrations'):
        files.extend(p for p in (repository / folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix != '.pyc')
    files.extend(p for pattern in ('requirements*.txt', 'alembic.ini', 'start-preview.*')
                 for p in repository.glob(pattern) if p.is_file())
    launcher = repository / 'scripts' / 'preview_launcher.ps1'
    if launcher.is_file():
        files.append(launcher)
    for path in sorted(files, key=lambda p: p.relative_to(repository).as_posix()):
        digest.update(path.relative_to(repository).as_posix().encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {'repository_id': repository_id, 'repository': str(repository),
            'source_fingerprint': digest.hexdigest()}


def dependency_problems(repository=ROOT):
    if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
        return ['需要 Python 3.11–3.13']
    problems = []
    for line in (Path(repository) / 'requirements.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([\w.-]+)==([^\s;]+)', line.strip())
        if not match:
            if line.strip() and not line.lstrip().startswith('#'):
                problems.append('无法核对依赖声明：' + line)
            continue
        name, expected = match.groups()
        try:
            if metadata.version(name) != expected:
                problems.append(name + ' 版本不匹配')
        except metadata.PackageNotFoundError:
            problems.append(name + ' 尚未安装')
    for module in IMPORTS:
        try:
            importlib.import_module(module)
        except Exception:
            problems.append(module + ' 无法加载')
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('identity', 'dependencies', 'python-version'))
    args = parser.parse_args()
    if args.command == 'identity':
        print(json.dumps(source_identity(), ensure_ascii=True))
    elif args.command == 'python-version':
        if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
            raise SystemExit('需要 Python 3.11–3.13')
    else:
        problems = dependency_problems()
        print(json.dumps({'ready': not problems, 'problems': problems}, ensure_ascii=True))
        raise SystemExit(bool(problems))


if __name__ == '__main__':
    main()
