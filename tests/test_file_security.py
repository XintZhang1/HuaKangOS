"""Quarantine, real protocol adapter, authorization and immutable rescans.

Only synthetic file contents and test loopback sockets are used. No installed
antivirus daemon, company service or customer artifact is contacted.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import socket
import sqlite3
import struct
import threading
import time
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.config import Settings
from app.db import SessionLocal
from app.models import User, Store, CashEntry
from app.flow_models import FileAsset, Case
from app.file_security_models import FileSecurity, FileScanEvent
from app import file_security as security
from app.tenancy import set_scope
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import login, TEST_DIR
from tests.test_workflow import order, action, account, seed_car, approved_doc


def mode(monkeypatch, value):
    monkeypatch.setattr(security, 'settings', replace(security.settings, file_scan_mode=value))


def scanner(monkeypatch, result):
    monkeypatch.setattr(security, 'scan_clamav', lambda *_: result)
    mode(monkeypatch, 'clamav')


def upload(c, case, content=b'fictional evidence', category='evidence', source=None, status=200, name='合成凭据.txt'):
    data = {'category': category}
    if source is not None:
        data['source_file_id'] = str(source)
    response = c.post(f"/api/flow/cases/{case['id']}/files", data=data,
                      files={'file': (name, content, 'text/plain')})
    assert response.status_code == status, response.text
    return response.json()


def scan(c, file_id, expected=200, key=None, version=None):
    if version is None:
        detail = c.get(f'/api/flow/files/{file_id}/security')
        assert detail.status_code == 200, detail.text
        version = detail.json()['security']['version']
    response = c.post(f'/api/flow/files/{file_id}/scan',
        json={'version': version, 'request_id': key or uuid.uuid4().hex})
    assert response.status_code == expected, response.text
    return response.json()


def test_quarantine_keeps_uploaded_bytes_and_blocks_download_lookup_and_payment(client, monkeypatch):
    mode(monkeypatch, 'quarantine')
    case = action(client, order(client), 'approve')
    file = upload(client, case)
    assert file['security']['state'] == 'quarantined' and not file['security']['can_use']
    assert '隔离' in file['security']['label']
    assert client.get(f"/api/flow/files/{file['id']}").status_code == 409
    assert client.get('/api/flow/lookup/file', params={'case_id': case['id']}).json()['items'] == []
    action(client, case, 'receive', {'amount': '1', 'account_id': account(client),
        'reference': 'quarantine-block', 'evidence_id': file['id']}, 409)
    with SessionLocal() as db:
        original = db.scalar(select(FileAsset).where(FileAsset.id == file['id']))
        assert original.content == b'fictional evidence'
        assert db.scalar(select(func.count()).select_from(CashEntry)) == 0
        event = db.scalar(select(FileScanEvent).where(FileScanEvent.file_id == file['id']))
        assert event.state == 'quarantined' and event.code == 'awaiting_scan'


def test_explicit_local_structure_mode_never_claims_antivirus(client):
    case = order(client)
    file = upload(client, case)
    assert file['security']['state'] == 'structure_only'
    assert file['security']['can_use'] and not file['security']['antivirus_scanned']
    assert '未查毒' in file['security']['label']
    downloaded = client.get(f"/api/flow/files/{file['id']}")
    assert downloaded.status_code == 200 and downloaded.content == b'fictional evidence'
    assert 'sandbox' in downloaded.headers['Content-Security-Policy']


@pytest.mark.parametrize('result', [security.ScanResult('infected', 'clamav', 'malware_detected', 'ClamAV-test'),
    security.ScanResult('error', 'clamav', 'scanner_timeout', 'ClamAV-test'),
    security.ScanResult('error', 'clamav', 'scanner_unavailable'),
    security.ScanResult('error', 'clamav', 'scanner_protocol', 'ClamAV-test')])
def test_scanner_failure_or_detection_keeps_file_quarantined_with_audit(client, monkeypatch, result):
    scanner(monkeypatch, result)
    case = order(client)
    file = upload(client, case)
    assert file['security']['state'] == result.state
    assert file['security']['code'] == result.code and not file['security']['can_use']
    assert client.get(f"/api/flow/files/{file['id']}").status_code == 409
    detail = client.get(f"/api/flow/files/{file['id']}/security").json()
    assert len(detail['scans']) == 1 and detail['scans'][0]['code'] == result.code
    assert '127.0.0.1' not in str(detail)  # Infrastructure details are not exposed.


def test_clean_scan_and_rescan_are_versioned_idempotent_and_immutable(client, monkeypatch):
    case = order(client)
    file = upload(client, case)
    original_hash = file['sha256']
    version = file['security']['version']
    scanner(monkeypatch, security.ScanResult('clean', 'clamav', 'clean', 'ClamAV test/123'))
    key = uuid.uuid4().hex
    clean = scan(client, file['id'], key=key, version=version)
    replay = scan(client, file['id'], key=key, version=version)
    assert clean == replay
    assert clean['security']['state'] == 'clean' and clean['security']['antivirus_scanned']
    assert client.get(f"/api/flow/files/{file['id']}").status_code == 200
    scan(client, file['id'], expected=409, version=version)
    detail = client.get(f"/api/flow/files/{file['id']}/security").json()
    assert len(detail['scans']) == 2
    with SessionLocal() as db:
        asset = db.scalar(select(FileAsset).where(FileAsset.id == file['id']))
        assert asset.sha256 == original_hash and asset.content == b'fictional evidence'
        first = db.scalar(select(FileScanEvent).where(FileScanEvent.file_id == file['id']).order_by(FileScanEvent.id))
        assert first.state == 'structure_only'
        first.state = 'clean'
        with pytest.raises(HTTPException, match='扫描记录不可覆盖'):
            db.flush()
        db.rollback()


def test_historical_missing_scan_is_not_silently_trusted_even_in_local_mode(client):
    case = order(client)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == 'admin'))
        content = b'legacy fixture'
        asset = FileAsset(store_id=1, case_id=case['id'], category='evidence', name='旧附件.txt',
            media_type='text/plain', sha256=hashlib.sha256(content).hexdigest(), size=len(content),
            content=content, created_by=user.id)
        db.add(asset)
        db.commit()
        file_id = asset.id
    detail = client.get(f'/api/flow/files/{file_id}/security').json()
    assert detail['security']['version'] == 0 and detail['security']['state'] == 'unscanned'
    assert client.get(f'/api/flow/files/{file_id}').status_code == 409
    result = scan(client, file_id, version=0)
    assert result['security']['state'] == 'structure_only'
    assert client.get(f'/api/flow/files/{file_id}').content == b'legacy fixture'


def test_stricter_policy_revokes_structure_only_permission_until_real_scan(client, monkeypatch):
    case = order(client)
    file = upload(client, case)
    scanner(monkeypatch, security.ScanResult('clean', 'clamav', 'clean', 'ClamAV test'))
    assert client.get(f"/api/flow/files/{file['id']}").status_code == 409
    assert client.get(f"/api/flow/files/{file['id']}/security").json()['security']['code'] == 'policy_requires_scan'
    result = scan(client, file['id'])
    assert result['security']['can_use']


def test_known_threat_cannot_be_released_by_switching_to_structure_only(client, monkeypatch):
    scanner(monkeypatch, security.ScanResult('infected', 'clamav', 'malware_detected', 'ClamAV test'))
    case = order(client)
    file = upload(client, case)
    mode(monkeypatch, 'structure_only')
    structural = scan(client, file['id'])
    assert structural['security']['state'] == 'structure_only'
    assert not structural['security']['can_use']
    assert structural['security']['code'] == 'prior_threat_requires_scan'
    assert client.get(f"/api/flow/files/{file['id']}").status_code == 409
    scanner(monkeypatch, security.ScanResult('clean', 'clamav', 'clean', 'ClamAV test/new-signatures'))
    cleared = scan(client, file['id'])
    assert cleared['security']['can_use'] and cleared['security']['antivirus_scanned']


def test_generated_documents_require_same_policy_as_uploads(client, monkeypatch):
    mode(monkeypatch, 'quarantine')
    case = order(client)
    generated = client.get(f"/api/flow/cases/{case['id']}").json()['files'][0]
    assert generated['generated'] and not generated['security']['can_use']
    assert client.get(f"/api/flow/files/{generated['id']}").status_code == 409
    upload(client, case, category='signed_contract', source=generated['id'], status=409)


def test_signed_document_cannot_bypass_quarantined_scan_or_new_source_scan(client, monkeypatch):
    scanner(monkeypatch, security.ScanResult('clean', 'clamav', 'clean', 'ClamAV test'))
    case = action(client, order(client), 'approve')
    case = action(client, case, 'allocate', {'vehicle_id': seed_car()})
    source = approved_doc(client, case, 'contract')
    signed = upload(client, case, b'signed fixture', category='signed_contract', source=source)
    # A later threat finding on the generated source blocks old signed copies as well.
    scanner(monkeypatch, security.ScanResult('infected', 'clamav', 'malware_detected', 'ClamAV test/new-signatures'))
    scan(client, source)
    action(client, case, 'sign', {'evidence_id': signed['id']}, 409)
    with SessionLocal() as db:
        row = db.scalar(select(Case).where(Case.id == case['id']))
        assert 'signed_file' not in row.data


def test_scan_permissions_and_cross_store_scope(client):
    case = order(client)
    neutral = upload(client, case)
    financial = upload(client, case, b'fictional receipt', category='receipt')
    login(client, 'auditor')
    assert client.get(f"/api/flow/files/{neutral['id']}/security").status_code == 200
    scan(client, neutral['id'], expected=403)
    login(client, 'inventory')
    scan(client, neutral['id'])
    assert client.get(f"/api/flow/files/{financial['id']}/security").status_code == 403
    scan(client, financial['id'], expected=403, version=financial['security']['version'])
    login(client, 'finance')
    scan(client, financial['id'])
    login(client, 'admin')
    with SessionLocal() as db:
        db.add(Store(id=2, code='SECOND_SCAN', name='另一模拟门店'))
        db.commit()
    client.headers['X-Store-ID'] = '2'
    assert client.get(f"/api/flow/files/{neutral['id']}/security").status_code == 404
    scan(client, neutral['id'], expected=404, version=neutral['security']['version'])
    client.headers['X-Store-ID'] = 'all'
    scan(client, neutral['id'], expected=409, version=neutral['security']['version'])
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == 'admin'))
        cached = db.scalar(select(FileAsset).where(FileAsset.id == neutral['id']))
        assert cached
        set_scope(db, [2], 2)
        with pytest.raises(HTTPException) as error:
            security.file_security_detail(db, user, neutral['id'])
        assert error.value.status_code == 404


def test_competing_rescans_cannot_overwrite_each_others_version(client):
    case = order(client)
    file = upload(client, case)
    body = {'version': file['security']['version']}
    with TestClient(app) as second:
        login(second)
        def run(c):
            return c.post(f"/api/flow/files/{file['id']}/scan", json=body | {'request_id': uuid.uuid4().hex}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(run, [client, second]))
    assert sorted(codes) == [200, 409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FileScanEvent).where(FileScanEvent.file_id == file['id'])) == 2


def test_rejected_structure_and_digest_mismatch_cannot_gain_scan_approval(client):
    case = order(client)
    upload(client, case, b'%PDF-1.4\n/JavaScript 1\n%%EOF', name='含脚本.pdf', status=422)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == 'admin'))
        asset = FileAsset(store_id=1, case_id=case['id'], category='evidence', name='损坏记录.txt',
            media_type='text/plain', sha256='a'*64, size=5, content=b'wrong', created_by=user.id)
        db.add(asset)
        db.commit()
        file_id = asset.id
    result = scan(client, file_id, version=0)
    assert result['security']['state'] == 'rejected' and result['security']['code'] == 'fingerprint_mismatch'
    assert client.get(f'/api/flow/files/{file_id}').status_code == 409


@pytest.mark.parametrize('value', ['quarantine', 'structure_only'])
def test_production_configuration_requires_antivirus(value):
    with pytest.raises(ValueError, match='FILE_SCAN_MODE'):
        Settings(environment='production', cookie_secure=True, allowed_hosts=('example.invalid',),
                 legacy_business_write=False, file_scan_mode=value)
    configured = Settings(environment='production', cookie_secure=True, allowed_hosts=('example.invalid',),
                          legacy_business_write=False, file_scan_mode='clamav')
    assert configured.file_scan_mode == 'clamav'


def _read_exact(sock, length):
    value = bytearray()
    while len(value) < length:
        chunk = sock.recv(length-len(value))
        if not chunk:
            raise AssertionError('Test protocol ended early')
        value.extend(chunk)
    return bytes(value)


@contextmanager
def fake_clamd(reply=b'stream: OK\0', *, delay=0, version=b'ClamAV synthetic/123/test\0'):
    """A bounded loopback protocol peer, not an antivirus implementation."""
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(2)
    listener.settimeout(2)
    captured, errors = [], []
    def server():
        try:
            with listener.accept()[0] as sock:
                sock.settimeout(2)
                assert _read_exact(sock, 9) == b'zVERSION\0'
                sock.sendall(version)
            if not version.startswith(b'ClamAV ') or not version.endswith(b'\0'):
                return
            with listener.accept()[0] as sock:
                sock.settimeout(2)
                assert _read_exact(sock, 10) == b'zINSTREAM\0'
                body = bytearray()
                while True:
                    length = struct.unpack('!I', _read_exact(sock, 4))[0]
                    if not length:
                        break
                    assert length <= 65536
                    body.extend(_read_exact(sock, length))
                captured.append(bytes(body))
                if delay:
                    time.sleep(delay)
                try:
                    sock.sendall(reply)
                except OSError:
                    pass  # The timeout test intentionally closes its client first.
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], captured
    finally:
        thread.join(3)
        listener.close()
        assert not thread.is_alive()
        assert not errors, errors


@pytest.mark.parametrize(('reply', 'state', 'code'), [
    (b'stream: OK\0', 'clean', 'clean'),
    (b'stream: Synthetic-Test-Signature FOUND\0', 'infected', 'malware_detected'),
    (b'INSTREAM size limit exceeded. ERROR\0', 'error', 'scanner_protocol'),
    (b'stream: UNKNOWN\0', 'error', 'scanner_protocol'),
    (b'stream: OK', 'error', 'scanner_protocol'),
])
def test_real_clamd_instream_adapter_is_fail_closed(reply, state, code):
    content = b'x'*70000+b'end'
    with fake_clamd(reply) as (port, captured):
        result = security.scan_clamav(content, '127.0.0.1', port, 1)
        assert result.state == state and result.code == code
    assert captured == [content]


def test_clamd_version_handshake_failure_never_sends_document_content():
    with fake_clamd(version=b'unknown scanner\0') as (port, captured):
        result = security.scan_clamav(b'private fixture', '127.0.0.1', port, .5)
    assert result.state == 'error' and result.code == 'scanner_protocol'
    assert captured == []


def test_real_clamd_adapter_timeout_and_unavailable_service_are_not_clean(monkeypatch):
    with fake_clamd(delay=.15) as (port, _):
        started = time.monotonic()
        result = security.scan_clamav(b'test', '127.0.0.1', port, .05)
        assert result.state == 'error' and result.code == 'scanner_timeout'
        assert time.monotonic()-started < .3
    # Hold an unlistening local socket so its port cannot be claimed by a service.
    with socket.socket() as inactive:
        inactive.bind(('127.0.0.1', 0))
        result = security.scan_clamav(b'test', '127.0.0.1', inactive.getsockname()[1], .2)
        assert result.state == 'error' and result.code in {'scanner_unavailable', 'scanner_timeout'}
    def refused(*_, **__):
        raise ConnectionRefusedError()
    monkeypatch.setattr(socket, 'create_connection', refused)
    result = security.scan_clamav(b'test', '127.0.0.1', 1, .2)
    assert result.state == 'error' and result.code == 'scanner_unavailable'


def test_file_security_backup_preserves_history_and_rejects_stale_or_cross_file_status(client, tmp_path):
    case = order(client)
    first = upload(client, case)
    second = upload(client, case, b'other file')
    scan(client, first['id'])
    backup_path = tmp_path/'scan-history.sqlite'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
        checked = security.validate_file_security_sqlite(backup)
        assert checked == {'verified_scan_events': 4, 'verified_scan_statuses': 3}
        original_sha = backup.execute('SELECT sha256 FROM flow_files WHERE id=?', (first['id'],)).fetchone()[0]
        assert original_sha == hashlib.sha256(b'fictional evidence').hexdigest()
        oldest = backup.execute('SELECT MIN(id) FROM file_scan_events WHERE file_id=?', (first['id'],)).fetchone()[0]
        backup.execute('UPDATE file_security SET last_scan_id=? WHERE file_id=?', (oldest, first['id']))
        with pytest.raises(ValueError, match='最新'):
            security.validate_file_security_sqlite(backup)
        newest = backup.execute('SELECT MAX(id) FROM file_scan_events WHERE file_id=?', (first['id'],)).fetchone()[0]
        backup.execute('UPDATE file_security SET last_scan_id=? WHERE file_id=?', (newest, first['id']))
        foreign = backup.execute('SELECT MAX(id) FROM file_scan_events WHERE file_id=?', (second['id'],)).fetchone()[0]
        backup.execute('UPDATE file_security SET last_scan_id=? WHERE file_id=?', (foreign, first['id']))
        with pytest.raises(ValueError, match='最新'):
            security.validate_file_security_sqlite(backup)
