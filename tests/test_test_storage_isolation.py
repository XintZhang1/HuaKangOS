"""Inherited private storage must not receive even synthetic test uploads."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('entry', ['pytest', 'browser'])
def test_inherited_attachment_directory_is_untouched(tmp_path, entry):
    if entry == 'browser':
        pytest.importorskip('playwright')
    outside = tmp_path/'external-configured-objects'
    outside.mkdir()
    (outside/'sentinel.bin').write_bytes(b'leave original bytes untouched')
    env = {**os.environ, 'FILE_STORAGE_MODE': 'private_local', 'PRIVATE_FILE_ROOT': str(outside),
           'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'ISOLATION_ENTRY': entry}
    code = r'''
import os, tempfile
from pathlib import Path
if os.environ['ISOLATION_ENTRY'] == 'browser':
    from tests.browser_huakangos import browser_environment
    child = browser_environment(Path(tempfile.mkdtemp(prefix='huakangos-storage-probe-')), 'SyntheticOnly!2026')
    assert child['FILE_STORAGE_MODE'] == 'blob' and child['PRIVATE_FILE_ROOT'] == ''
    os.environ.update(child)
from tests.conftest import isolated_database, login, app, SessionLocal
from app.config import settings
assert settings.file_storage_mode == 'blob' and settings.private_file_root == ''
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.private_file_models import PrivateFileObject
from app.flow_models import FileAsset
from tests.test_workflow import order
from tests.test_file_security import upload
fixture = isolated_database.__wrapped__()
next(fixture)
try:
    with TestClient(app) as client:
        login(client)
        case = order(client)
        asset = upload(client, case, b'synthetic upload stays in test database')
        assert client.get('/api/flow/files/'+str(asset['id'])).content == b'synthetic upload stays in test database'
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(PrivateFileObject)) == 0
            assert db.scalar(select(FileAsset.content).where(FileAsset.id == asset['id'])) == b'synthetic upload stays in test database'
finally:
    next(fixture, None)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=120,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stdout + result.stderr
    assert {p.relative_to(outside).as_posix(): p.read_bytes() for p in outside.rglob('*') if p.is_file()} == {
        'sentinel.bin': b'leave original bytes untouched'}
