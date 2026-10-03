"""Reproduce an operations release from tracked Git bytes, without importing app.

Untracked files, working-tree changes, symlinks and private runtime configuration
are never read. This mirrors app.ops_context's published inventory policy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT_DOCS = {
    'AGENTS.md', 'README.md', 'PROJECT_SPEC.md', 'ARCHITECTURE.md',
    'docs/阿里云试运行与运维助手.md',
}
SOURCE_SUFFIXES = {'.py', '.js', '.mjs', '.css', '.html', '.md', '.json'}
MAX_FILE_BYTES = 512_000


class VerificationError(Exception):
    """A stable error code safe to print without Git/configuration diagnostics."""


def allowed_name(name):
    path = PurePosixPath(name)
    return (not path.is_absolute() and '\\' not in name
            and not any(part.startswith('.') for part in path.parts)
            and (name in ROOT_DOCS or len(path.parts) >= 2
                 and path.parts[0] in {'app', 'web', 'scripts'})
            and path.suffix in SOURCE_SUFFIXES
            and path.name not in {'workflow-guides.json', 'workflow-handbook.html'})


def git_read(repo, arguments, data=None):
    environment = os.environ.copy()
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
        environment.pop(key, None)
    environment['GIT_OPTIONAL_LOCKS'] = '0'
    try:
        result = subprocess.run(
            ['git', '-C', str(repo), *arguments], input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, check=False, timeout=55,
        )
    except FileNotFoundError as exc:
        raise VerificationError('git_unavailable') from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError('git_read_failed') from exc
    if result.returncode:
        raise VerificationError('git_read_failed')
    return result.stdout


def verify_commit(repo, commit):
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
        raise VerificationError('expected_full_commit_sha')
    resolved = git_read(repo, ['rev-parse', '--verify', '--end-of-options',
                               commit + '^{commit}']).strip().decode('ascii')
    if resolved.lower() != commit.lower():
        raise VerificationError('commit_mismatch')
    tree = git_read(repo, ['ls-tree', '-r', '-l', '--full-tree', '-z', resolved])
    selected = []
    try:
        for entry in tree.split(b'\0'):
            if not entry:
                continue
            metadata, raw_name = entry.split(b'\t', 1)
            mode, kind, oid, size = metadata.split()
            name = raw_name.decode('utf-8')
            if (mode in {b'100644', b'100755'} and kind == b'blob'
                    and allowed_name(name) and int(size) <= MAX_FILE_BYTES):
                selected.append((name, oid, int(size)))
    except (ValueError, UnicodeError) as exc:
        raise VerificationError('invalid_git_tree') from exc
    if not selected:
        raise VerificationError('empty_source_inventory')
    blobs = git_read(repo, ['cat-file', '--batch'],
                     b''.join(oid + b'\n' for _, oid, _ in selected))
    files, offset = {}, 0
    try:
        for name, oid, size in selected:
            end = blobs.index(b'\n', offset)
            header = blobs[offset:end].split()
            if header != [oid, b'blob', str(size).encode('ascii')]:
                raise VerificationError('invalid_git_blob')
            start = end + 1
            raw = blobs[start:start + size]
            if len(raw) != size or blobs[start + size:start + size + 1] != b'\n':
                raise VerificationError('invalid_git_blob')
            files[name] = hashlib.sha256(raw).hexdigest()
            offset = start + size + 1
        if offset != len(blobs):
            raise VerificationError('invalid_git_blob')
    except ValueError as exc:
        raise VerificationError('invalid_git_blob') from exc
    release_id = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'commit': resolved, 'release_id': release_id, 'file_count': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True, help='Exact 40-character Git commit SHA')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--expected-release', help='Expected 64-character release SHA256')
    arguments = parser.parse_args()
    try:
        if (arguments.expected_release is not None
                and not re.fullmatch(r'[0-9a-fA-F]{64}', arguments.expected_release)):
            raise VerificationError('invalid_expected_release')
        result = verify_commit(arguments.repo, arguments.commit)
        if (arguments.expected_release is not None
                and result['release_id'] != arguments.expected_release.lower()):
            print(json.dumps(result | {'ok': False, 'error': 'release_mismatch'}))
            return 1
        print(json.dumps(result | {'ok': True}))
        return 0
    except VerificationError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
