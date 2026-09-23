"""Fail-closed attachment quarantine with bounded ClamAV INSTREAM scanning.

Scanning happens before the caller's one transaction commits. No scan failure
raises away the quarantine record, and no raw scanner response is shown to staff.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import socket
import struct
import time
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .config import settings
from .db import utcnow
from .models import User
from .flow_models import FileAsset
from .file_security_models import FileSecurity, FileScanEvent
from .tenancy import single_store

LABELS = {'unscanned': '历史文件未扫描，已隔离', 'quarantined': '已隔离，等待扫描',
          'clean': '扫描未发现已知威胁', 'structure_only': '仅结构校验通过（未查毒）',
          'infected': '扫描发现风险，已隔离', 'error': '扫描失败，保持隔离',
          'rejected': '结构校验未通过，已隔离'}
MESSAGES = {'unscanned': '历史文件尚无扫描记录，请重扫后再使用。',
    'awaiting_scan': '扫描策略为隔离，文件尚不能下载或作为业务凭据。',
    'structure_only': '仅完成文件格式和结构校验，未进行病毒扫描；只用于明确配置的本地试用。',
    'clean': '本次 ClamAV 扫描未发现已知威胁，不代表电子签名真实性或绝对安全。',
    'malware_detected': '扫描发现已知威胁或扫描器风险提示，请提交其他凭据并联系管理员。',
    'scanner_timeout': '扫描服务超时，文件继续隔离；稍后由获权员工重扫。',
    'scanner_unavailable': '扫描服务不可用，文件继续隔离；请联系管理员检查扫描服务。',
    'scanner_protocol': '扫描服务未返回有效完整结果，文件继续隔离。',
    'structure_rejected': '文件结构不符合允许的文档格式，不能下载或用于办理。',
    'fingerprint_mismatch': '文件内容与原始摘要不一致，保持隔离；请联系管理员核对恢复来源。',
    'policy_requires_scan': '当前策略要求 ClamAV 扫描，原结构校验记录不足以放行。'}
MESSAGES['prior_threat_requires_scan'] = '此文件曾被扫描器发现风险；仅结构校验不能解除隔离，须重新通过 ClamAV 扫描。'


@dataclass(frozen=True)
class ScanResult:
    state: str
    engine: str
    code: str
    engine_version: str = ''


def policy_mode():
    mode = settings.file_scan_mode
    if mode not in {'quarantine', 'structure_only', 'clamav'}:
        raise HTTPException(503, '附件扫描策略无效；附件继续隔离，请联系管理员')
    if settings.environment == 'production' and mode != 'clamav':
        raise HTTPException(503, '正式环境必须启用 ClamAV 扫描，不能只做结构校验')
    return mode


def _socket_timeout(sock, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError()
    sock.settimeout(remaining)


def _read_record(sock, deadline, maximum=4096):
    reply = bytearray()
    while b'\0' not in reply:
        _socket_timeout(sock, deadline)
        chunk = sock.recv(min(1024, maximum+1-len(reply)))
        if not chunk:
            raise ValueError('Incomplete clamd record')
        reply.extend(chunk)
        if len(reply) > maximum:
            raise ValueError('Oversized clamd record')
    record, extra = bytes(reply).split(b'\0', 1)
    if extra:
        raise ValueError('Unexpected extra clamd record')
    return record


def scan_clamav(content, host, port, timeout):
    """Use VERSION + INSTREAM, one total deadline, no shell or public file path.

    clamd protocol: https://docs.clamav.net/manual/Usage/ClamdProtocol.html
    Tests provide a synthetic loopback daemon; no company scanner is contacted.
    """
    deadline = time.monotonic()+timeout
    version = ''
    try:
        with socket.create_connection((host, port), timeout=max(.001, deadline-time.monotonic())) as sock:
            _socket_timeout(sock, deadline)
            sock.sendall(b'zVERSION\0')
            raw_version = _read_record(sock, deadline, 512)
            if not raw_version.startswith(b'ClamAV ') or any(c < 32 for c in raw_version):
                raise ValueError('Invalid clamd version')
            version = raw_version.decode('ascii', 'strict')[:200]
        with socket.create_connection((host, port), timeout=max(.001, deadline-time.monotonic())) as sock:
            _socket_timeout(sock, deadline)
            sock.sendall(b'zINSTREAM\0')
            for start in range(0, len(content), 65536):
                chunk = content[start:start+65536]
                _socket_timeout(sock, deadline)
                sock.sendall(struct.pack('!I', len(chunk))+chunk)
            _socket_timeout(sock, deadline)
            sock.sendall(struct.pack('!I', 0))
            reply = _read_record(sock, deadline)
        if reply == b'stream: OK':
            return ScanResult('clean', 'clamav', 'clean', version)
        if reply.startswith(b'stream: ') and reply.endswith(b' FOUND') and len(reply) > 15:
            return ScanResult('infected', 'clamav', 'malware_detected', version)
        return ScanResult('error', 'clamav', 'scanner_protocol', version)
    except (TimeoutError, socket.timeout):
        return ScanResult('error', 'clamav', 'scanner_timeout', version)
    except (ValueError, UnicodeError):
        return ScanResult('error', 'clamav', 'scanner_protocol', version)
    except OSError:
        return ScanResult('error', 'clamav', 'scanner_unavailable', version)


def scan_asset(db,asset):
    mode = policy_mode()
    from .private_files import read_content
    try:content=read_content(db,asset)
    except HTTPException:
        return ScanResult('rejected', 'structure', 'fingerprint_mismatch')
    from .flow_documents import validate_upload
    try:
        media = validate_upload(asset.name, content)
        if media.split(';')[0] != asset.media_type.split(';')[0]:
            return ScanResult('rejected', 'structure', 'structure_rejected')
    except HTTPException:
        return ScanResult('rejected', 'structure', 'structure_rejected')
    if mode == 'quarantine':
        return ScanResult('quarantined', 'none', 'awaiting_scan')
    if mode == 'structure_only':
        return ScanResult('structure_only', 'structure', 'structure_only', 'huakangos-structure-v1')
    return scan_clamav(content, settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)


def _records(db, asset):
    status = db.scalar(select(FileSecurity).where(FileSecurity.file_id == asset.id,
                                                FileSecurity.store_id == asset.store_id))
    event = db.scalar(select(FileScanEvent).where(FileScanEvent.file_id == asset.id,
        FileScanEvent.store_id == asset.store_id).order_by(FileScanEvent.id.desc()).limit(1)) if status and status.last_scan_id else None
    if event and event.id != status.last_scan_id:
        event = None  # A partial/tampered restore cannot point past a newer risk result.
    return status, event


def security_info(db, asset):
    mode = policy_mode()
    status, event = _records(db, asset)
    state = status.state if status else 'unscanned'
    valid = bool(event and event.state == state and event.sha256 == asset.sha256 and event.size == asset.size)
    antivirus = valid and state == 'clean' and event.engine == 'clamav' and event.code == 'clean'
    structural = valid and state == 'structure_only' and event.engine == 'structure'
    last_antivirus = db.scalar(select(FileScanEvent).where(FileScanEvent.file_id == asset.id,
        FileScanEvent.store_id == asset.store_id, FileScanEvent.engine == 'clamav',
        FileScanEvent.state.in_(['clean', 'infected'])).order_by(FileScanEvent.id.desc()).limit(1))
    known_threat = bool(last_antivirus and last_antivirus.state == 'infected')
    usable = bool(antivirus or (structural and not known_threat and mode == 'structure_only' and settings.environment != 'production'))
    code = event.code if event else 'unscanned'
    label = LABELS.get(state, LABELS['quarantined'])
    if code=='fingerprint_mismatch':label='原文件字节与摘要不一致，已隔离'
    if status and not valid:
        code, label = 'fingerprint_mismatch', '扫描凭据不一致，保持隔离'
    elif known_threat and not antivirus and state != 'infected':
        code, label = 'prior_threat_requires_scan', '曾发现风险，须重新通过查毒'
    elif structural and not usable:
        code = 'policy_requires_scan'
        label = '当前策略要求重新扫描，已隔离'
    return {'state': state, 'label': label, 'version': status.version if status else 0,
            'can_use': usable, 'antivirus_scanned': bool(antivirus), 'required_mode': mode,
            'scan_id': event.id if event else None, 'engine': event.engine if event else 'none',
            'engine_version': event.engine_version if event else '', 'code': code,
            'message': MESSAGES.get(code, MESSAGES['scanner_protocol']),
            'scanned_at': event.occurred_at.isoformat()+'Z' if event else None}


def is_usable(db, asset):
    return security_info(db, asset)['can_use']


def require_usable(db, asset):
    info = security_info(db, asset)
    if not info['can_use']:
        raise HTTPException(409, '附件不可使用：'+info['label']+'。'+info['message'])
    from .private_files import read_content
    read_content(db,asset)
    return asset


@contextmanager
def _authority(db):
    old = db.info.get('_file_scan_authority')
    db.info['_file_scan_authority'] = True
    try:
        yield
    finally:
        if old is None:
            db.info.pop('_file_scan_authority', None)
        else:
            db.info['_file_scan_authority'] = old


def _record_scan(db, user, asset, status, action, request_key=None, request_digest=None):
    scanned = scan_asset(db,asset)
    event = FileScanEvent(store_id=asset.store_id, file_id=asset.id, actor_id=user.id, action=action,
        request_key=request_key, request_digest=request_digest, state=scanned.state, engine=scanned.engine,
        engine_version=scanned.engine_version, code=scanned.code, sha256=asset.sha256, size=asset.size,
        result={'message': MESSAGES[scanned.code], 'mode': policy_mode()})
    db.add(event)
    db.flush()
    status.state, status.last_scan_id, status.updated_at = scanned.state, event.id, utcnow()
    db.flush()
    return event


def initialize_file_security(db, user, row, asset):
    """Called only for newly persisted uploads/generated documents; does not commit."""
    store_id = single_store(db)
    if asset.store_id != store_id or row.store_id != store_id or asset.case_id != row.id:
        raise HTTPException(403, '不能为其他门店附件写入扫描状态')
    existing = db.scalar(select(FileSecurity).where(FileSecurity.file_id == asset.id,
                                                   FileSecurity.store_id == store_id))
    if existing:
        raise HTTPException(409, '该文件已有扫描状态，请通过重扫动作追加记录')
    with _authority(db):
        status = FileSecurity(store_id=store_id, file_id=asset.id, state='quarantined')
        db.add(status)
        db.flush()
        _record_scan(db, user, asset, status, 'initial')
    return security_info(db, asset)


def _authorized_asset(db, user, file_id, rescan=False):
    from .flow_engine import get_case
    from .flow_documents import can_file
    asset = db.scalar(select(FileAsset).where(FileAsset.id == file_id))
    if not asset:
        raise HTTPException(404, '文件不存在或不可访问')
    row = get_case(db, user, asset.case_id)
    if not can_file(user, row, asset):
        raise HTTPException(403, '没有此类文件的查看权限')
    if rescan:
        single_store(db)
        if user.role == 'auditor':
            raise HTTPException(403, '审计账号只能查看扫描记录，不能重扫附件')
        if asset.category in {'receipt', 'invoice', 'procurement_contract'} and user.role not in {'admin', 'manager', 'finance'}:
            raise HTTPException(403, '财务凭据由获权财务岗位重扫')
        if asset.category.startswith('signed_') and user.role not in {'admin', 'manager', 'sales'}:
            raise HTTPException(403, '签回凭据由销售或主管重扫')
    return row, asset


def file_security_detail(db, user, file_id):
    _, asset = _authorized_asset(db, user, file_id)
    events = list(db.scalars(select(FileScanEvent).where(FileScanEvent.file_id == asset.id,
        FileScanEvent.store_id == asset.store_id).order_by(FileScanEvent.id.desc()).limit(100)))
    return {'file_id': asset.id, 'security': security_info(db, asset), 'scans': [
        {'id': e.id, 'state': e.state, 'label': LABELS[e.state], 'engine': e.engine,
         'engine_version': e.engine_version, 'code': e.code, 'message': MESSAGES.get(e.code, MESSAGES['scanner_protocol']),
         'actor_id': e.actor_id, 'occurred_at': e.occurred_at.isoformat()+'Z'} for e in events]}


def rescan_file(db, user, file_id, version, request_id):
    row, asset = _authorized_asset(db, user, file_id, rescan=True)
    digest = hashlib.sha256(json.dumps([file_id, version], separators=(',', ':')).encode()).hexdigest()
    try:
        old = db.scalar(select(FileScanEvent).where(FileScanEvent.store_id == asset.store_id,
                                                   FileScanEvent.request_key == request_id))
        if old:
            if old.actor_id != user.id or old.request_digest != digest or old.file_id != asset.id:
                raise HTTPException(409, '重扫请求编号已用于其他操作')
            return {'file_id': asset.id, 'scan_id': old.id, 'security': security_info(db, asset)}
        status = db.scalar(select(FileSecurity).where(FileSecurity.file_id == asset.id,
            FileSecurity.store_id == asset.store_id).with_for_update())
        if version != (status.version if status else 0):
            raise HTTPException(409, '文件扫描状态已变化，请刷新核对，保留原请求编号确认结果')
        with _authority(db):
            if not status:
                status = FileSecurity(store_id=asset.store_id, file_id=asset.id, state='quarantined')
                db.add(status)
                db.flush()
            event = _record_scan(db, user, asset, status, 'rescan', request_id, digest)
            from .flow_engine import log_event
            log_event(db, user, row, 'file_rescan', '重新扫描业务附件', row.state,
                      {'file_id': asset.id, 'scan_id': event.id, 'state': event.state})
            db.commit()
        return {'file_id': asset.id, 'scan_id': event.id, 'security': security_info(db, asset)}
    except (IntegrityError, OperationalError, StaleDataError):
        db.rollback()
        raise HTTPException(409, '扫描状态同时变化，请刷新核对，勿盲目更换请求编号重试')
    except Exception:
        db.rollback()
        raise


def validate_file_security_sqlite(connection):
    """Read-only consistency verification on an offline SQLite backup.

    Missing status for a historical file is allowed and remains quarantined at
    runtime. Existing status must point to its own newest immutable scan.
    """
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {'file_security', 'file_scan_events'}
    if not names.intersection(required):
        return {'verified_scan_events': 0, 'verified_scan_statuses': 0}
    if not (required | {'flow_files'}) <= names:
        raise ValueError('附件扫描表或原文件表不完整')
    bad_event = connection.execute('''SELECT e.id FROM file_scan_events e
        LEFT JOIN flow_files f ON f.id=e.file_id
        WHERE f.id IS NULL OR e.store_id!=f.store_id OR e.sha256!=f.sha256 OR e.size!=f.size LIMIT 1''').fetchone()
    if bad_event:
        raise ValueError('附件扫描记录与原文件、门店或摘要不一致')
    bad_status = connection.execute('''SELECT s.id FROM file_security s
        LEFT JOIN flow_files f ON f.id=s.file_id
        LEFT JOIN file_scan_events e ON e.id=s.last_scan_id
        WHERE f.id IS NULL OR e.id IS NULL OR s.store_id!=f.store_id
          OR e.file_id!=s.file_id OR e.store_id!=s.store_id OR e.state!=s.state
          OR e.id!=(SELECT MAX(newest.id) FROM file_scan_events newest WHERE newest.file_id=s.file_id)
        LIMIT 1''').fetchone()
    if bad_status:
        raise ValueError('附件当前扫描状态与最新原文件扫描记录不一致')
    return {'verified_scan_events': connection.execute('SELECT COUNT(*) FROM file_scan_events').fetchone()[0],
            'verified_scan_statuses': connection.execute('SELECT COUNT(*) FROM file_security').fetchone()[0]}
