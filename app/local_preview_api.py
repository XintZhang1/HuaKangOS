"""First-admin bootstrap for an explicit, isolated loopback preview only."""
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from .config import settings
from .db import get_db
from .local_preview import MARKER_KEY, DB_NAME, preview_root
from .models import AppMetadata, Store, User, UserStore
from .security import hash_password
from .preview_runtime import source_identity

router = APIRouter(prefix='/api/local-preview', tags=['local-preview'])
RUNNING_SOURCE = source_identity()


def context(request):
    if settings.environment != 'local' or os.environ.get('HUAKANGOS_LOCAL_PREVIEW') != '1':
        raise HTTPException(404, '本地预览初始化未启用')
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback:
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(403, '首次设置仅允许从本机访问') from None
    try:
        root = preview_root(os.environ.get('HUAKANGOS_PREVIEW_ROOT', ''))
        url = make_url(settings.database_url)
        if url.drivername != 'sqlite' or Path(url.database).resolve() != root / DB_NAME:
            raise ValueError()
        manifest = json.loads((root / 'preview.json').read_text(encoding='utf-8-sig'))
        if manifest.get('schema') != 1 or not re.fullmatch(r'[0-9a-f-]{36}', manifest.get('instance_id', '')):
            raise ValueError()
        if manifest.get('repository_id') and manifest['repository_id'] != RUNNING_SOURCE['repository_id']:
            raise ValueError()
    except (OSError, ValueError, TypeError):
        raise HTTPException(409, '预览实例校验失败，请重新运行预览启动器') from None
    return root, manifest


def marker(db, manifest):
    record = db.scalar(select(AppMetadata).where(AppMetadata.key == MARKER_KEY))
    if not record or not isinstance(record.value, dict) or record.value.get('instance_id') != manifest['instance_id'] or record.value.get('schema') != 1:
        raise HTTPException(409, '数据库不属于此独立预览，禁止初始化')
    return record


@router.get('/status')
def status(request: Request, db=Depends(get_db)):
    _, manifest = context(request)
    record = marker(db, manifest)
    count = db.scalar(select(func.count()).select_from(User))
    return {'status': 'ok', 'local_preview': True, 'instance_id': manifest['instance_id'],
            'bootstrap_required': not record.value.get('setup_complete') and count == 0,
            'repository_id': RUNNING_SOURCE['repository_id'],
            'source_fingerprint': RUNNING_SOURCE['source_fingerprint'],
            'pid': os.getpid(), 'notice': '独立本机预览；请只填写虚构资料。附件仅做结构校验，未进行病毒扫描。'}


class BootstrapInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=128)


def verify_token(root, manifest, token):
    try:
        ticket = json.loads((root / 'bootstrap.json').read_text(encoding='utf-8-sig'))
        now = time.time()
        valid = (ticket['instance_id'] == manifest['instance_id'] and
                 0 < ticket['expires_at'] - now <= 16 * 60 and
                 isinstance(token, str) and 40 <= len(token) <= 100 and
                 hmac.compare_digest(ticket['token_hash'], hashlib.sha256(token.encode()).hexdigest()))
    except (OSError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        raise HTTPException(403, '首次设置链接已失效或不匹配，请重新运行 start-preview.cmd 获取新链接')


@router.post('/bootstrap')
def bootstrap(body: BootstrapInput, request: Request, db=Depends(get_db)):
    root, manifest = context(request)
    if request.headers.get('X-App-Request') != '1':
        raise HTTPException(403, '请通过本机首次设置页面提交')
    verify_token(root, manifest, request.headers.get('X-Local-Preview-Token'))
    try:
        # First SQL is a write lock. Concurrent zero-user requests serialize before
        # checking the immutable instance marker and user count. No new schema needed.
        db.execute(update(AppMetadata).where(AppMetadata.key == MARKER_KEY).values(value=AppMetadata.value))
        record = marker(db, manifest)
        if record.value.get('setup_complete') or db.scalar(select(func.count()).select_from(User)):
            raise HTTPException(409, '管理员已经设置完成，请使用已有账号登录；不会重置密码')
        if db.scalar(select(func.count()).select_from(Store)):
            raise HTTPException(409, '预览库已有门店资料，禁止覆盖初始化')
        store = Store(code='PREVIEW', name='本地预览门店（虚构试用）')
        user = User(username=body.username.lower(), display_name='本地预览管理员', role='admin',
                    password_hash=hash_password(body.password), must_change_password=False)
        db.add_all([store, user]); db.flush()
        db.add(UserStore(user_id=user.id, store_id=store.id))
        record.value = {**record.value, 'setup_complete': True, 'admin_id': user.id}
        db.commit()
    except OperationalError:
        db.rollback()
        raise HTTPException(409, '另一窗口正在完成首次设置，请刷新后登录') from None
    return {'configured': True, 'username': user.username, 'notice': '管理员已设置，请登录。本预览未灌入业务数据或正式经营主体。'}
