"""Server-owned Runtime identity and private GET request capabilities.

Only committed login/Run/Grant records authorize work. Every validation uses a
short, independent read Session on the caller's database, never its transaction.
Callers must commit queue claims before constructing an identity. These helpers
reject stale authority; queue/grant services own subsequent state transitions.
No cookie, login hash or Python capability belongs in events/model/UI payloads.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import re

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import SingletonThreadPool, StaticPool


_SCOPE_KEY = '_huakang_runtime'
_ISSUER = object()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _time(value):
    if not isinstance(value, datetime):
        raise ValueError('Runtime clock must return a datetime')
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _denied():
    raise HTTPException(403, '员工、门店或事项授权已失效，请重新核对')


def _stopped():
    raise HTTPException(409, '此执行已停止、租约已失效或事项版本已变化')


def _enabled(auth_kind=None):
    from .config import settings
    if not settings.assistant_runtime_enabled:
        raise HTTPException(503, '助手运行服务尚未开启')
    if auth_kind == 'grant' and not settings.assistant_followup_enabled:
        raise HTTPException(503, '持续跟进服务尚未开启')


@dataclass(frozen=True, slots=True)
class RuntimePrincipal:
    actor_id: int
    store_id: int
    role: str
    access_version: int
    session_id: str
    auth_kind: str
    run_id: str | None = None
    plan_id: str | None = None
    goal_version: int | None = None
    grant_id: str | None = None
    lease_owner: str | None = None
    fence: int | None = None
    _login_ref: str | None = field(default=None, repr=False)
    _probe_grant_version: int | None = field(default=None, repr=False)
    _issuer: object = field(default=None, repr=False, compare=False)
    _clock: object = field(default=_utcnow, repr=False, compare=False)
    _read_session_factory: object = field(default=None, repr=False, compare=False)
    _bind: object = field(default=None, repr=False, compare=False)

    @property
    def id(self):
        return self.actor_id

    @property
    def _active_store_id(self):
        return self.store_id

    @property
    def _aggregate_scope(self):
        return False


def _issued(principal):
    if type(principal) is not RuntimePrincipal or principal._issuer is not _ISSUER:
        _denied()
    _enabled(principal.auth_kind)
    return principal


@contextmanager
def _reader(db, factory=None):
    """An injected factory must return a fresh Session bound to this same Engine.

    A Connection-bound caller or an active transaction on a shared-connection
    pool cannot safely be treated as an independent authorization snapshot.
    In-memory databases retain their original semantics, never become files.
    """
    bind = db.get_bind()
    if not isinstance(bind, Engine):
        raise HTTPException(409, '身份核对需要独立的同库读取连接')
    if db.in_transaction() and isinstance(bind.pool, (StaticPool, SingletonThreadPool)):
        raise HTTPException(409, '当前连接仍有事务，请在结束事务后重新核对身份')
    reader = factory(bind) if factory is not None else Session(
        bind=bind, autoflush=False, expire_on_commit=False)
    if (not isinstance(reader, Session) or reader is db or reader.get_bind() is not bind
            or reader.in_transaction() or reader.new or reader.dirty or reader.deleted):
        # An invalid injected caller-owned Session must not be closed/rolled back.
        raise ValueError('Authorization reader must be a fresh same-engine Session')
    try:
        with db.no_autoflush, reader.no_autoflush:
            yield reader
    finally:
        reader.close()


def _identity(reader, actor_id, store_id, role, access_version, session_id):
    from .models import User, Store, UserStore
    from .business_assistant_models import AssistantSession
    from .tenancy import role_for_store
    account = reader.scalar(select(User).where(User.id == actor_id))
    store = reader.scalar(select(Store.id).where(Store.id == store_id, Store.active.is_(True)))
    thread = reader.scalar(select(AssistantSession).where(
        AssistantSession.id == session_id, AssistantSession.owner_id == actor_id,
        AssistantSession.store_id == store_id))
    if (account is None or not account.active or account.must_change_password
            or account.access_version != access_version or store is None or thread is None
            or thread.owner_role != role or thread.access_version != access_version):
        _denied()
    # Keep the original account/admin and nullable legacy membership-role rules.
    reader.scalar(select(UserStore).where(UserStore.user_id == actor_id, UserStore.store_id == store_id))
    if role_for_store(reader, account, store_id) != role:
        _denied()
    return account


def _login(reader, login_ref, actor_id, now):
    from .models import LoginSession
    if type(login_ref) is not str or re.fullmatch(r'[0-9a-f]{64}', login_ref) is None:
        _denied()
    login = reader.scalar(select(LoginSession).where(LoginSession.id == login_ref,
        LoginSession.user_id == actor_id))
    if login is None or _time(login.expires_at) <= now:
        raise HTTPException(401, '原登录已退出或过期，请重新登录')


def _run_values(reader, run_id, lease_owner, fence, now):
    from .assistant_runtime_models import Run, FollowupGrant
    from .business_assistant_models import AssistantSession, AssistantWorkPlan
    if (type(run_id) is not str or not run_id or type(lease_owner) is not str or not lease_owner
            or type(fence) is not int or fence < 1):
        _stopped()
    run = reader.scalar(select(Run).where(Run.id == run_id))
    if (run is None or run.status != 'running' or run.stop_requested
            or run.lease_owner != lease_owner or run.fence != fence
            or run.lease_until is None or _time(run.lease_until) <= now):
        _stopped()
    _enabled(run.auth_kind)
    thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == run.session_id,
        AssistantSession.owner_id == run.owner_id, AssistantSession.store_id == run.store_id))
    if thread is None:
        _denied()
    if run.plan_id is not None:
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == run.plan_id,
            AssistantWorkPlan.owner_id == run.owner_id, AssistantWorkPlan.store_id == run.store_id,
            AssistantWorkPlan.session_id == run.session_id))
        if (plan is None or plan.engine_version != 2 or plan.status != 'active'
                or run.goal_version is None or plan.goal_version != run.goal_version):
            _stopped()
    elif run.goal_version is not None:
        _stopped()
    if run.auth_kind == 'login':
        if run.grant_id is not None:
            _denied()
        _login(reader, run.login_session_ref, run.owner_id, now)
    elif run.auth_kind == 'grant':
        if run.login_session_ref is not None or run.grant_id is None or run.plan_id is None:
            _denied()
        grant = reader.scalar(select(FollowupGrant).where(FollowupGrant.id == run.grant_id))
        if (grant is None or grant.status != 'active' or grant.revoked_at is not None
                or (grant.owner_id, grant.store_id, grant.session_id, grant.plan_id,
                    grant.owner_role, grant.access_version, grant.goal_version)
                != (run.owner_id, run.store_id, run.session_id, run.plan_id,
                    thread.owner_role, thread.access_version, run.goal_version)
                or grant.expires_at is not None and _time(grant.expires_at) <= now):
            _denied()
    else:
        _denied()
    return dict(actor_id=run.owner_id, store_id=run.store_id, role=thread.owner_role,
        access_version=thread.access_version, session_id=run.session_id, auth_kind=run.auth_kind,
        run_id=run.id, plan_id=run.plan_id, goal_version=run.goal_version, grant_id=run.grant_id,
        lease_owner=lease_owner, fence=fence, _login_ref=run.login_session_ref)


def principal_for_run(db, run_id, *, lease_owner, fence, clock=_utcnow, read_session_factory=None):
    """Validate a committed claim, without binding the mutable Run.version."""
    _enabled()
    with _reader(db, read_session_factory) as reader:
        values = _run_values(reader, run_id, lease_owner, fence, _time(clock()))
        _identity(reader, values['actor_id'], values['store_id'], values['role'],
                  values['access_version'], values['session_id'])
    return RuntimePrincipal(**values, _issuer=_ISSUER, _clock=clock,
                            _read_session_factory=read_session_factory, _bind=db.get_bind())


def _grant_probe_values(reader, grant_id, now):
    """Actual current authorization for reads before a Run has been enqueued."""
    from .assistant_runtime_models import FollowupGrant
    from .business_assistant_models import AssistantWorkPlan
    _enabled('grant')
    if type(grant_id) is not str or not grant_id:
        _denied()
    grant = reader.scalar(select(FollowupGrant).where(FollowupGrant.id == grant_id))
    if (grant is None or grant.status != 'active' or grant.revoked_at is not None
            or grant.expires_at is not None and _time(grant.expires_at) <= now):
        _denied()
    plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == grant.plan_id,
        AssistantWorkPlan.owner_id == grant.owner_id, AssistantWorkPlan.store_id == grant.store_id,
        AssistantWorkPlan.session_id == grant.session_id))
    if (plan is None or plan.engine_version != 2 or plan.status != 'active'
            or plan.goal_version != grant.goal_version):
        _stopped()
    _identity(reader, grant.owner_id, grant.store_id, grant.owner_role,
              grant.access_version, grant.session_id)
    return dict(actor_id=grant.owner_id, store_id=grant.store_id, role=grant.owner_role,
        access_version=grant.access_version, session_id=grant.session_id, auth_kind='grant',
        run_id=None, plan_id=plan.id, goal_version=plan.goal_version, grant_id=grant.id,
        lease_owner=None, fence=None, _login_ref=None, _probe_grant_version=grant.version)


def principal_for_grant_probe(db, grant_id, *, clock=_utcnow, read_session_factory=None):
    """Issue only a current Grant's pre-dispatch read capability, without a Run.

    It works through the same fixed original GET transport and employee/store
    checks. It grants no queue lease, write fence, model execution or login;
    preparation, general Plan saves and Run mutations still require a claimed
    Run. Separate fixed services may consume their own verified condition or
    receipt proof for narrow assistant bookkeeping; this probe alone cannot.
    """
    _enabled('grant')
    with _reader(db, read_session_factory) as reader:
        values = _grant_probe_values(reader, grant_id, _time(clock()))
    return RuntimePrincipal(**values, _issuer=_ISSUER, _clock=clock,
                            _read_session_factory=read_session_factory, _bind=db.get_bind())


def revalidate_principal(db, principal, *, clock=None, read_session_factory=None):
    """Recheck all frozen authority against a fresh committed snapshot; no writes."""
    principal = _issued(principal)
    if db.get_bind() is not principal._bind:
        raise HTTPException(403, '身份来源与当前数据库不一致')
    clock = principal._clock if clock is None else clock
    factory = principal._read_session_factory if read_session_factory is None else read_session_factory
    with _reader(db, factory) as reader:
        now = _time(clock())
        if principal.run_id is not None:
            if principal._probe_grant_version is not None:
                _denied()
            values = _run_values(reader, principal.run_id, principal.lease_owner, principal.fence, now)
            if any(getattr(principal, key) != value for key, value in values.items()):
                _denied()
        elif principal.auth_kind == 'login' and all(value is None for value in (
                principal.plan_id, principal.goal_version, principal.grant_id, principal.lease_owner,
                principal.fence, principal._probe_grant_version)):
            _login(reader, principal._login_ref, principal.actor_id, now)
        elif principal.auth_kind == 'grant' and type(principal._probe_grant_version) is int:
            values = _grant_probe_values(reader, principal.grant_id, now)
            if any(getattr(principal, key) != value for key, value in values.items()):
                _denied()
        else:
            _denied()
        _identity(reader, principal.actor_id, principal.store_id, principal.role,
                  principal.access_version, principal.session_id)
    return principal


def _caller_matches(user, principal, session_id):
    if (getattr(user, '_aggregate_scope', False) or
            (user.id, getattr(user, '_active_store_id', None), user.role, user.access_version, session_id)
            != (principal.actor_id, principal.store_id, principal.role, principal.access_version, principal.session_id)):
        _denied()


def principal_for_request(db, request, user, session_id, *, clock=_utcnow, read_session_factory=None):
    """Use the original authenticated login, or retain a private Runtime source.

    Capture caller primitives before database reads. Never refresh the account
    behind a RequestPrincipal and silently adopt its changed access version.
    """
    _enabled()
    context = runtime_request_context(request)
    if context is not None:
        _caller_matches(user, context.principal, session_id)
        return revalidate_principal(db, context.principal)
    if getattr(user, '_aggregate_scope', False):
        _denied()
    actor_id, store_id, role, version = user.id, getattr(user, '_active_store_id', None), user.role, user.access_version
    login_ref = getattr(request.state, 'session_hash', None)
    if type(actor_id) is not int or type(store_id) is not int or store_id < 1 or type(version) is not int:
        _denied()
    with _reader(db, read_session_factory) as reader:
        _login(reader, login_ref, actor_id, _time(clock()))
        _identity(reader, actor_id, store_id, role, version, session_id)
    return RuntimePrincipal(actor_id, store_id, role, version, session_id, 'login',
        _login_ref=login_ref, _issuer=_ISSUER, _clock=clock,
        _read_session_factory=read_session_factory, _bind=db.get_bind())


@dataclass(frozen=True, slots=True, repr=False)
class _RequestContext:
    principal: RuntimePrincipal
    db: object
    client_factory: object = None
    issuer: object = _ISSUER


@dataclass(frozen=True, slots=True, repr=False)
class _InternalCall:
    context: _RequestContext
    operation_id: str
    path: str
    query_string: bytes
    issuer: object = _ISSUER


def runtime_request_context(request):
    if _SCOPE_KEY not in request.scope:
        return None
    value = request.scope[_SCOPE_KEY]
    if type(value) is _InternalCall and value.issuer is _ISSUER:
        _check_call(request, value)
        value = value.context
    if type(value) is not _RequestContext or value.issuer is not _ISSUER:
        _denied()
    _issued(value.principal)
    return value


def internal_base_url():
    """Choose an ASGI origin from trusted configuration, never a caller URL."""
    from .config import settings
    for configured in settings.allowed_hosts:
        host = 'localhost' if configured == '*' else 'runtime.' + configured[2:] if configured.startswith('*.') else configured
        if re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
            scheme = 'https' if settings.cookie_secure or settings.environment == 'production' else 'http'
            return scheme + '://' + host
    raise HTTPException(503, '未配置内部查询可用的受信主机名')


def request_for_principal(db, principal, *, client_factory=None):
    """An ephemeral carrier for existing tool APIs, never a network credential."""
    from urllib.parse import urlsplit
    principal = revalidate_principal(db, principal)
    origin = urlsplit(internal_base_url())
    return Request({'type': 'http', 'http_version': '1.1', 'method': 'GET',
        'scheme': origin.scheme, 'server': (origin.hostname, 443 if origin.scheme == 'https' else 80),
        'client': ('127.0.0.1', 0), 'path': '/api/business-assistant/runtime-internal',
        'raw_path': b'/api/business-assistant/runtime-internal', 'query_string': b'', 'root_path': '',
        'headers': [(b'host', origin.netloc.encode('ascii')), (b'x-store-id', str(principal.store_id).encode('ascii'))],
        _SCOPE_KEY: _RequestContext(principal, db, client_factory)})


def _check_call(request, call):
    if (type(call) is not _InternalCall or call.issuer is not _ISSUER
            or request.method != 'GET' or request.scope.get('path') != call.path
            or request.scope.get('query_string', b'') != call.query_string
            or request.headers.get('x-store-id') != str(call.context.principal.store_id)
            or any(request.headers.get(key) for key in ('cookie', 'authorization', 'x-csrf-token'))):
        _denied()
    from .business_assistant_gateway import _operation, _declared_dispatch
    operation = _operation(call.operation_id)
    if operation['method'] != 'GET' or operation['write']:
        _denied()
    _declared_dispatch(operation, call.path)


def internal_user(request, db):
    """Called only by get_user's private branch; invalid markers never fall back."""
    call = request.scope.get(_SCOPE_KEY)
    if type(call) is not _InternalCall or call.issuer is not _ISSUER:
        _denied()
    if not isinstance(db.get_bind(), Engine) or db.get_bind() is not call.context.db.get_bind():
        raise HTTPException(403, '内部查询与身份来源数据库不一致')
    _check_call(request, call)
    principal = revalidate_principal(db, call.context.principal)
    with _reader(db, principal._read_session_factory) as reader:
        account = _identity(reader, principal.actor_id, principal.store_id, principal.role,
                            principal.access_version, principal.session_id)
    from .tenancy import attach_scope
    user = attach_scope(request, db, account)
    _caller_matches(user, principal, principal.session_id)
    request.state.user_id = user.id
    request.state.store_id = principal.store_id
    request.state.role = user.role
    return user


def native_reader_for_principal(db, principal, allowed_operations, *, client_factory=None):
    """Bind an adapter to its static GET set; the gateway still checks originals."""
    from .assistant_runtime_registry import make_native_reader
    from .business_assistant_gateway import invoke
    request = request_for_principal(db, principal, client_factory=client_factory)

    async def transport(operation_id, *, path_args=None, query=None, body=None):
        revalidate_principal(db, principal)
        result = await invoke(request, principal, operation_id, path_args, query, body)
        revalidate_principal(db, principal)
        return result

    return make_native_reader(transport, principal, allowed_operations)


def principal_for_followup_request(db, request, user, session_id, plan_id, *,
                                  action, clock=_utcnow, read_session_factory=None):
    """Only the employee's original POST/CSRF request can change a grant."""
    if (_SCOPE_KEY in request.scope or isinstance(user, RuntimePrincipal)
            or request.method != 'POST'
            or request.url.path != '/api/business-assistant/plans/' + plan_id + '/followup'):
        _denied()
    if action in {'enable', 'resume'}:
        _enabled('grant')
    principal = principal_for_request(db, request, user, session_id,
        clock=clock, read_session_factory=read_session_factory)
    raw = request.cookies.get('dealer_session', '')
    csrf = request.headers.get('x-csrf-token', '')
    if (not raw or not csrf or not hmac.compare_digest(
            hashlib.sha256(raw.encode()).hexdigest(), principal._login_ref)):
        raise HTTPException(403, '请求校验失败，请刷新页面')
    from .models import LoginSession
    with _reader(db, read_session_factory) as reader:
        _login(reader, principal._login_ref, principal.actor_id, _time(clock()))
        login = reader.scalar(select(LoginSession).where(LoginSession.id == principal._login_ref))
        if not hmac.compare_digest(login.csrf_hash, hashlib.sha256(csrf.encode()).hexdigest()):
            raise HTTPException(403, '请求校验失败，请刷新页面')
    return principal


def revalidate_control_principal(db, principal, *, clock=None):
    """A valid lease may stop its own work after authority/goal loss, never read it.

    This deliberately does not return a business principal or bypass ordinary
    revalidation. Queue CAS must additionally guard its own final status write.
    """
    if (type(principal) is not RuntimePrincipal or principal._issuer is not _ISSUER
            or db.get_bind() is not principal._bind or principal.run_id is None):
        _denied()
    from .assistant_runtime_models import Run
    now = _time((principal._clock if clock is None else clock)())
    with _reader(db, principal._read_session_factory) as reader:
        run = reader.scalar(select(Run).where(Run.id == principal.run_id))
        if (run is None or run.status != 'running' or run.lease_until is None
                or _time(run.lease_until) <= now
                or (run.owner_id, run.store_id, run.session_id, run.auth_kind,
                    run.login_session_ref, run.grant_id, run.plan_id, run.goal_version,
                    run.lease_owner, run.fence)
                != (principal.actor_id, principal.store_id, principal.session_id, principal.auth_kind,
                    principal._login_ref, principal.grant_id, principal.plan_id, principal.goal_version,
                    principal.lease_owner, principal.fence)):
            _stopped()
    return principal


def identity_is_current(db, principal):
    """Control-only check: logout is not an employee/store permission change."""
    if (type(principal) is not RuntimePrincipal or principal._issuer is not _ISSUER
            or db.get_bind() is not principal._bind):
        _denied()
    with _reader(db, principal._read_session_factory) as reader:
        try:
            _identity(reader, principal.actor_id, principal.store_id, principal.role,
                      principal.access_version, principal.session_id)
        except HTTPException as exc:
            if exc.status_code == 403:
                return False
            raise
    return True


def invalid_grant_snapshot(db, grant_id, expected_version, *, clock=_utcnow, read_session_factory=None):
    """Internal dispatcher check, with no Run requirement or caller-supplied reason.

    This is not exposed as an HTTP/model/MCP capability. A valid or ordinarily
    paused authorization is never revoked by this path. Return only control IDs.
    """
    from .assistant_runtime_models import FollowupGrant
    from .business_assistant_models import AssistantSession, AssistantWorkPlan
    if type(expected_version) is not int or expected_version < 1:
        raise HTTPException(422, '请提供授权版本')
    with _reader(db, read_session_factory) as reader:
        grant = reader.scalar(select(FollowupGrant).where(FollowupGrant.id == grant_id))
        if grant is None:
            raise HTTPException(404, '未找到授权记录')
        if grant.version != expected_version:
            _stopped()
        reason = None
        try:
            _identity(reader, grant.owner_id, grant.store_id, grant.owner_role,
                      grant.access_version, grant.session_id)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            reason = 'permission_changed'
        if reason is None and grant.expires_at is not None and _time(grant.expires_at) <= _time(clock()):
            reason = 'expired'
        if grant.status != 'revoked' and reason is None:
            raise HTTPException(409, '原授权仍然有效，不能通过失效清理停用')
        thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == grant.session_id,
            AssistantSession.owner_id == grant.owner_id, AssistantSession.store_id == grant.store_id))
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == grant.plan_id,
            AssistantWorkPlan.owner_id == grant.owner_id, AssistantWorkPlan.store_id == grant.store_id,
            AssistantWorkPlan.session_id == grant.session_id))
        if thread is None or plan is None:
            _stopped()
        return {'grant_id': grant.id, 'grant_version': grant.version, 'status': grant.status,
            'owner_id': grant.owner_id, 'store_id': grant.store_id, 'session_id': grant.session_id,
            'session_version': thread.version, 'plan_id': grant.plan_id, 'plan_version': plan.version,
            'goal_version': grant.goal_version, 'reason': reason}


def validate_completion_authority(db, principal, *, clock=None):
    """Completion advances progress, so the ordinary stop/goal guards still apply."""
    revalidate_control_principal(db, principal, clock=clock)
    # The caller's pending stop flag is not visible in this independent reader.
    # A previously committed stop request must prevent advancing Plan status.
    revalidate_principal(db, principal, clock=clock)
