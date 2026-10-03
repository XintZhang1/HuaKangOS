"""Package hash-registered validation source inputs outside the checkout.

The archive contains definitions only. Tests still run through run_validation.py
against its fresh synthetic mirror. Credentials, runs and results are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile


SUFFIXES = {'.py', '.cjs', '.js', '.json', '.txt', '.md', '.html', '.cmd'}
ROOT_FILES = {'run_validation.py', 'validation-manifest.json',
              'dependencies.in.txt', 'dependencies.lock.txt'}
PREFIXES = ('harness/', 'archive/baseline-original/',
            'tests/baseline/overlay/', 'tests/m82-closeout/')
EXACT = {'archive/baseline-restoration.json', 'tests/baseline/applicability.json'}
DENIED_PARTS = {'.git', '.venv', '__pycache__', '.pytest_cache', 'runs',
                'evidence', 'logs', 'backups',
                'objects', 'attachments', 'profiles', 'node_modules'}
LIMIT = 256 * 1024 * 1024


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or '\\' in value or ':' in value:
        raise ValueError('noncanonical_input_path')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('unsafe_input_path')
    if value != path.as_posix() or any(part in DENIED_PARTS for part in path.parts):
        raise ValueError('unsafe_input_path')
    if (path.suffix not in SUFFIXES or path.name.startswith('.env')
            or path.name == 'binding.json' or path.name.endswith('.bak')):
        raise ValueError('non_source_input')
    if value not in ROOT_FILES | EXACT and not value.startswith(PREFIXES):
        raise ValueError('input_outside_registered_roots')
    logical = value
    for prefix in ('archive/baseline-original/', 'tests/baseline/overlay/'):
        if logical.startswith(prefix):
            logical = logical[len(prefix):]
            break
    # These names also occur in real source namespaces. Permit the registered
    # Runtime test modules and this one archived synthetic JSON source fixture.
    if 'runtime' in path.parts and not (logical.startswith('tests/runtime/') and path.suffix == '.py'):
        raise ValueError('runtime_result_input')
    if 'fixtures' in path.parts and logical != 'tests/fixtures/questionnaire_o57b_synthetic.json':
        raise ValueError('runtime_fixture_input')
    return path


def read_inventory(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    files = value['files']
    if not isinstance(files, dict) or not files:
        raise ValueError('empty_input_inventory')
    for name, digest in files.items():
        safe_relative(name)
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('invalid_input_hash')
    return files


def pack(args):
    root = args.validation_root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(root):
        raise ValueError('new_external_archive_required')
    files = read_inventory(args.inventory)
    total = 0
    for name, digest in files.items():
        path = root / name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('input_link_outside_root')
        if sha(path) != digest:
            raise ValueError('registered_input_changed')
        total += path.stat().st_size
        if total > LIMIT:
            raise ValueError('input_size_limit')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'schema': 1, 'kind': 'validation_source_only',
                'files': files, 'uncompressed_bytes': total,
                'credentials': False, 'database': False, 'runtime_evidence': False}
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('capsule-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        for name in sorted(files):
            archive.write(root / name, name)
    # A definition changing while packaging cannot be published as frozen input.
    if any(sha(root / name) != digest for name, digest in files.items()):
        raise ValueError('input_changed_during_packaging')
    print(json.dumps({'archive': str(output), 'sha256': sha(output),
                      'files': len(files), 'uncompressed_bytes': total}))


def extract(args):
    archive_path = args.archive.resolve(strict=True)
    if sha(archive_path) != args.sha256:
        raise ValueError('archive_hash_mismatch')
    target = args.output.resolve()
    if target.exists():
        raise ValueError('new_validation_root_required')
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            raise ValueError('duplicate_archive_member')
        total = 0
        for member in members:
            if member.filename != 'capsule-manifest.json':
                safe_relative(member.filename)
            if stat.S_ISLNK(member.external_attr >> 16) or member.is_dir():
                raise ValueError('archive_links_or_directories')
            total += member.file_size
            if total > LIMIT + 2 * 1024 * 1024:
                raise ValueError('archive_size_limit')
            if member.filename == 'capsule-manifest.json' and member.file_size > 2 * 1024 * 1024:
                raise ValueError('capsule_manifest_size_limit')
        if 'capsule-manifest.json' not in names:
            raise ValueError('capsule_manifest_missing')
        manifest = json.loads(archive.read('capsule-manifest.json'))
        if manifest.get('schema') != 1 or manifest.get('kind') != 'validation_source_only':
            raise ValueError('capsule_schema')
        files = manifest['files']
        if set(names) != set(files) | {'capsule-manifest.json'}:
            raise ValueError('capsule_inventory_mismatch')
        if archive.testzip() is not None:
            raise ValueError('archive_crc_error')
        for name, digest in files.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('capsule_member_hash_mismatch')
        target.mkdir(parents=True)
        archive.extractall(target)
    print(json.dumps({'validation_root': str(target), 'files': len(files),
                      'capsule_sha256': args.sha256, 'safe_paths': True}))


def platform_binding(args):
    root = args.validation_root.absolute()
    sys.path.insert(0, str(root / 'harness'))
    from isolation import clean_path
    root = clean_path(root)
    repo = clean_path(args.repo)
    if root.is_relative_to(repo) or sys.prefix == sys.base_prefix or clean_path(sys.prefix) != root / '.venv':
        raise ValueError('owned_validation_venv_required')
    node = shutil.which('node')
    if not node:
        raise ValueError('actual_node_required')
    node_path = clean_path(node)
    value = {'schema': 2, 'python': sys.version,
             'executable': str(clean_path(sys.executable)),
             'venv': str(clean_path(sys.prefix)),
             'base_prefix': str(clean_path(sys.base_prefix)),
             'platform': platform.platform(),
             'node': {'path': str(node_path),
                      'version': subprocess.check_output([str(node_path), '--version'], text=True).strip(),
                      'sha256': sha(node_path)}}
    path = root / 'harness/runtime-platform.json'
    previous = root / 'capsule-platform-source.json'
    if previous.exists():
        raise ValueError('platform_binding_already_created')
    manifest_path = root / 'validation-manifest.json'
    source_manifest = root / 'capsule-validation-manifest-source.json'
    if source_manifest.exists() or (root / 'binding.json').exists():
        raise ValueError('repository_binding_already_created')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    before_repo = manifest['repository']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    git_dir = subprocess.check_output(['git', 'rev-parse', '--absolute-git-dir'], cwd=repo, text=True).strip()
    shutil.copyfile(manifest_path, source_manifest)
    shutil.copyfile(path, previous)
    manifest['repository'] = str(repo)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / 'binding.json').write_text(json.dumps({'schema': 1, 'repository': str(repo)}), encoding='utf-8')
    (root / 'capsule-repository-rebinding.json').write_text(json.dumps({
        'source_repository': before_repo, 'current_repository': str(repo),
        'head': head, 'git_dir': git_dir, 'source_manifest_sha256': sha(source_manifest),
        'rebound_manifest_sha256': sha(manifest_path),
        'only_registration_field_changed': 'repository'}, indent=2) + '\n', encoding='utf-8')
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(value))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def download(args):
    # Only the authenticated API receives Authorization. The signed asset URL
    # stays in memory and its request receives no credential or proxy setting.
    token = os.environ.get('GH_TOKEN', '')
    if not token or args.output.exists():
        raise ValueError('download_input_guard')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    url = f'https://api.github.com/repos/XintZhang1/HuaKangOS/releases/assets/{args.asset_id}'
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
        'Accept': 'application/octet-stream', 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        response = opener.open(request, timeout=120)
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise ValueError('asset_api_status') from None
        signed = error.headers['Location']
    else:
        response.close()
        raise ValueError('asset_api_redirect_required')
    token = None
    parsed = urllib.parse.urlsplit(signed)
    if parsed.scheme != 'https' or parsed.hostname != 'release-assets.githubusercontent.com':
        raise ValueError('asset_redirect_host')
    request = urllib.request.Request(signed, headers={'Accept-Encoding': 'identity'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with opener.open(request, timeout=120) as response, args.output.open('xb') as stream:
        if response.status != 200:
            raise ValueError('asset_download_status')
        total = 0
        while chunk := response.read(65536):
            total += len(chunk)
            if total > LIMIT:
                raise ValueError('asset_size_limit')
            stream.write(chunk)
    if sha(args.output) != args.sha256:
        raise ValueError('asset_hash_mismatch')
    print(json.dumps({'archive': str(args.output), 'sha256': args.sha256,
                      'asset_id': args.asset_id, 'bytes': total, 'signed_url_persisted': False}))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='operation', required=True)
    command = sub.add_parser('pack')
    command.add_argument('--validation-root', type=Path, required=True)
    command.add_argument('--inventory', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('extract')
    command.add_argument('--archive', type=Path, required=True)
    command.add_argument('--sha256', required=True)
    command.add_argument('--output', type=Path, required=True)
    command = sub.add_parser('platform')
    command.add_argument('--validation-root', type=Path, required=True)
    command.add_argument('--repo', type=Path, required=True)
    command = sub.add_parser('download')
    command.add_argument('--asset-id', type=int, required=True)
    command.add_argument('--sha256', required=True)
    command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if hasattr(args, 'sha256') and not re.fullmatch(r'[0-9a-f]{64}', args.sha256):
        parser.error('sha256 must be the full frozen archive digest')
    try:
        {'pack': pack, 'extract': extract, 'platform': platform_binding, 'download': download}[args.operation](args)
    except Exception as error:
        # HTTP exception text can contain a signed URL. Keep it out of evidence.
        reason = str(error) if isinstance(error, ValueError) and re.fullmatch(r'[a-z_]+', str(error)) else type(error).__name__
        print('VALIDATION_INPUT_FAILED:' + reason, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
