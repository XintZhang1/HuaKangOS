from datetime import timedelta
from ipaddress import ip_address
import hashlib
import hmac
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db, utcnow
from .models import User, LoginSession, LoginAttempt

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))
ROLES = {'admin':'系统管理员', 'manager':'店长 / 老板', 'sales':'销售', 'inventory':'库存管理员', 'service':'售后 / 保险', 'finance':'财务', 'auditor':'复核 / 审计'}
ALL = {'vehicles','sales','repairs','policies','cash'}
READ = {'admin':ALL, 'manager':ALL, 'finance':ALL, 'auditor':ALL,
        'sales':{'vehicles','sales'}, 'inventory':{'vehicles'}, 'service':{'repairs','policies'}}
WRITE = {'admin':ALL, 'manager':ALL, 'finance':{'cash'}, 'auditor':set(),
         'sales':{'sales'}, 'inventory':{'vehicles'}, 'service':{'repairs','policies'}}
FULL_VIEW = {'admin','manager','finance','auditor'}
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def identifies_a_client(ip: str) -> bool:
    """这个来源地址能不能代表「某一个客户端」。

    容器化部署时，请求往往不是直连进来的：docker 端口映射让同宿主机的连接看起来来自
    网桥地址，反向代理 / 内网穿透（例如花生壳客户端跑在同一台机器上）更是把所有访客
    都变成同一个内网地址。这时按 IP 计数就不再是「这个人失败了几次」，而是「所有人一共
    失败了几次」——任何一个陌生人都能靠失败 10 次把全店锁在门外 15 分钟。
    所以只有全球可达的单播地址才拿来当客户端身份。

    用 is_global 而不是自己拼 is_private 等条件，是因为它一并覆盖了运营商大内网
    （100.64.0.0/10，国内移动网络上很常见，成百上千人共用一个出口）、文档段与保留段：
    这些地址同样不能代表某一个人。
    """
    try:
        address = ip_address((ip or '').strip())
    except ValueError:
        return False
    return bool(address.is_global)


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError('密码长度必须为 12–128 字符')
    return hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def authenticate(db: Session, username: str, password: str, ip: str) -> User:
    username = username.lower()
    cutoff = utcnow() - LOGIN_FAILURE_WINDOW

    def failures(column) -> int:
        return db.scalar(select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.occurred_at > cutoff, column)) or 0

    if failures(LoginAttempt.username == username) >= LOGIN_FAILURE_LIMIT:
        raise HTTPException(429, '该账号登录失败次数过多，请 15 分钟后重试')
    if identifies_a_client(ip) and failures(LoginAttempt.ip == ip) >= LOGIN_FAILURE_LIMIT:
        # 只在来源地址真的代表某个客户端时才按它计数，否则会变成一把全店通用的锁。
        raise HTTPException(429, '当前网络登录失败次数过多，请 15 分钟后重试')
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        db.add(LoginAttempt(username=username, ip=ip[:100]))
        db.commit()
        raise HTTPException(401, '用户名或密码错误，或账户已停用')
    db.execute(delete(LoginAttempt).where(LoginAttempt.occurred_at < utcnow() - timedelta(days=1)))
    # Retain recent failures to prevent a successful login from resetting IP throttling.
    return user


def set_session(db: Session, user: User, response: Response):
    raw, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    max_age = settings.session_hours * 3600
    db.add(LoginSession(id=digest(raw), user_id=user.id, csrf_hash=digest(csrf), expires_at=utcnow()+timedelta(seconds=max_age)))
    db.execute(delete(LoginSession).where(LoginSession.expires_at <= utcnow()))
    db.commit()
    response.set_cookie('dealer_session', raw, max_age=max_age, httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')
    response.set_cookie('dealer_csrf', csrf, max_age=max_age, httponly=False, secure=settings.cookie_secure, samesite='strict', path='/')


def clear_cookies(response: Response):
    for name in ('dealer_session','dealer_csrf'):
        response.delete_cookie(name, path='/', secure=settings.cookie_secure, samesite='strict')


def get_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get('dealer_session', '')
    session = db.get(LoginSession, digest(token)) if token else None
    if session is None or session.expires_at <= utcnow():
        raise HTTPException(401, '请先登录，或登录已过期')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, '账户已停用')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        csrf = request.headers.get('X-CSRF-Token', '')
        if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(403, '请求校验失败，请刷新页面')
    request.state.session_hash = session.id
    if user.must_change_password and request.url.path not in {'/api/auth/me','/api/auth/password','/api/auth/logout'}:
        raise HTTPException(403, '首次登录必须修改密码')
    from .tenancy import attach_scope
    attach_scope(request, db, user)
    return user


def require_module(user: User, module: str, write: bool = False):
    if module not in ALL:
        raise HTTPException(404, '模块不存在')
    if module not in (WRITE if write else READ).get(user.role, set()):
        raise HTTPException(403, '没有此模块的操作权限')


def require_full(user: User):
    if user.role not in FULL_VIEW:
        raise HTTPException(403, '该内容仅向管理层、财务和审计角色开放')


def user_info(user: User):
    return {'id': user.id, 'username': user.username, 'display_name': user.display_name,
            'store_ids':getattr(user,'_store_ids',[]), 'stores':getattr(user,'_stores',[]),
            'active_store_id':getattr(user,'_active_store_id',None),
            'role': user.role, 'role_label': ROLES[user.role], 'active': user.active,
            'must_change_password': user.must_change_password,
            'read_modules': sorted(READ[user.role]), 'write_modules': sorted(WRITE[user.role]),
            'can_approve': user.role in {'admin','manager'}, 'can_report': user.role in FULL_VIEW,
            'can_users': user.role == 'admin', 'can_audit': user.role in {'admin','manager','auditor'}}
