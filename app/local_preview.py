"""Opt-in Windows loopback preview. Never adopts an existing unmarked database."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import uuid
from .preview_runtime import source_identity

MARKER_KEY = 'huakangos_local_preview'
DB_NAME = 'preview.sqlite'


def preview_root(value):
    root = Path(value).resolve()
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise ValueError('LOCALAPPDATA 未配置，无法建立独立预览目录')
    allowed = (Path(local) / 'huakangos').resolve()
    repo = Path(__file__).resolve().parent.parent
    if root == allowed or not root.is_relative_to(allowed) or root.is_relative_to(repo):
        raise ValueError('预览数据必须放在 LOCALAPPDATA/huakangos 下的独立子目录，不能使用仓库或公司数据库')
    # A junction/symlink must not redirect any runtime file outside its private root.
    for child in ('preview.sqlite', 'preview.json', 'bootstrap.json'):
        path = root / child
        if path.is_symlink() or (path.exists() and path.resolve().parent != root):
            raise ValueError('预览文件不能使用符号链接或目录重定向')
    return root


def configure(root):
    root = preview_root(root)
    os.environ.update({
        'DATABASE_URL': 'sqlite:///' + str(root / DB_NAME), 'APP_ENV': 'local',
        'HUAKANGOS_LOCAL_PREVIEW': '1', 'HUAKANGOS_PREVIEW_ROOT': str(root),
        'ALLOWED_HOSTS': '127.0.0.1', 'COOKIE_SECURE': 'false',
        'SCHEDULER_ENABLED': 'false', 'SCHEDULER_MODE': 'off',
        'LEGACY_BUSINESS_WRITE': 'false', 'ALLOW_AI_EXTERNAL': 'false',
        'DEEPSEEK_API_KEY': '', 'FILE_SCAN_MODE': 'structure_only',
        'FILE_STORAGE_MODE': 'blob', 'PRIVATE_FILE_ROOT': '',
        'HUAKANGOS_INITIAL_PASSWORD': '', 'DEALER_INITIAL_PASSWORD': '',
    })
    return root


def marker_from_disk(root):
    try:
        with sqlite3.connect((root / DB_NAME).as_uri() + '?mode=ro', uri=True) as conn:
            item = conn.execute('SELECT value FROM app_metadata WHERE key=?', (MARKER_KEY,)).fetchone()
            if not item:
                raise ValueError('此数据库没有本地预览标记，拒绝接管或重置；' + preparation_recovery())
            marker = json.loads(item[0])
            count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    except (sqlite3.Error, json.JSONDecodeError) as error:
        raise ValueError('预览实例标记无法验证，首次准备可能尚未完成；' + preparation_recovery()) from error
    manifest = json.loads((root / 'preview.json').read_text(encoding='utf-8-sig'))
    if marker.get('instance_id') != manifest.get('instance_id') or marker.get('schema') != 1:
        raise ValueError('预览目录与数据库实例不匹配，拒绝启动')
    if manifest.get('repository_id') and manifest['repository_id'] != source_identity()['repository_id']:
        raise ValueError('此预览目录属于另一份源码，拒绝接管')
    if not marker.get('setup_complete') and count:
        raise ValueError('预览库已有账号，不能再次初始化管理员')
    return marker, count


def preparation_recovery():
    return ('现有资料已保留，不会自动接管或删除。请在此源码目录打开 PowerShell，使用新的独立目录重试：'
            ' .\\start-preview.ps1 -DataDirectory (Join-Path $env:LOCALAPPDATA '
            "('huakangos\\preview-retry-' + [guid]::NewGuid().ToString('N')))")


def prepare(value):
    root = configure(value)
    root.mkdir(parents=True, exist_ok=True)
    database = root / DB_NAME
    existed = database.exists()
    if existed:
        marker_from_disk(root)  # Check ownership BEFORE any migration.
    else:
        manifest = root / 'preview.json'
        if manifest.exists():
            raise ValueError('首次准备未完成：预览标记已存在但数据库缺失；' + preparation_recovery())
        with manifest.open('x', encoding='utf-8') as out:
            json.dump({'instance_id': str(uuid.uuid4()), 'schema': 1,
                       'repository_id': source_identity()['repository_id']}, out)
    from .cli import migrate
    migrate()
    if not existed:
        manifest = json.loads((root / 'preview.json').read_text(encoding='utf-8'))
        with sqlite3.connect(database) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                raise ValueError('新预览库出现非预期账号，拒绝初始化')
            conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)', (
                MARKER_KEY, json.dumps({**manifest, 'setup_complete': False})))
    marker, count = marker_from_disk(root)
    return {'instance_id': marker['instance_id'], 'bootstrap_required': count == 0}


def main():
    parser = argparse.ArgumentParser(description='huakangos 独立本机预览')
    parser.add_argument('command', choices=('prepare', 'serve'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--expected-repository-id')
    parser.add_argument('--expected-source-fingerprint')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            print(json.dumps(prepare(args.root)))
        else:
            root = configure(args.root)
            marker_from_disk(root)
            identity = source_identity()
            if ((args.expected_repository_id and args.expected_repository_id != identity['repository_id']) or
                    (args.expected_source_fingerprint and args.expected_source_fingerprint != identity['source_fingerprint'])):
                raise ValueError('启动过程中源码已经变化，请重新运行启动器')
            # The API imports this once; never recompute the running version from disk.
            from . import local_preview_api
            local_preview_api.RUNNING_SOURCE = identity
            import uvicorn
            # Proxy headers are deliberately disabled: loopback means the socket peer.
            uvicorn.run('app.main:app', host='127.0.0.1', port=args.port,
                        proxy_headers=False, access_log=False, log_level='warning')
    except (ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit('本地预览未启动：' + str(error)) from None


if __name__ == '__main__':
    main()
