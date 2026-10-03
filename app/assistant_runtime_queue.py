"""Database queue and fenced leases; no worker, model or business submission.

Queue methods own their short transaction. Worker claim/reclaim require a new,
unscoped Session without a transaction. Native entry reads precede enqueue's
write. Identity readers always use an independent Session on the same Engine.
The stable busy token identifies a Run; its mutable fence is verified separately
before every worker write or release. No HTTP/model tool exposes these helpers.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import re
from time import monotonic
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary, ref

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import and_, exists, false, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm.exc import StaleDataError

from .assistant_runtime_models import FollowupGrant, Run, RunItem, WorkItem
from .business_assistant_models import AssistantMessage, AssistantProposal, AssistantSession, AssistantWorkPlan
from .assistant_runtime_principal import (
    _enabled, _identity, _login, _reader, _time, principal_for_request,
    principal_for_run, revalidate_control_principal, revalidate_principal,
    runtime_request_context,
)
from .assistant_runtime_schemas import MessageRequestId, RunCreate, UUIDText
from .db import utcnow


LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20
RETRY_DELAYS = (30, 120, 600)
WORKER_SLOTS = 1
_ERRORS = frozenset({'runtime_unavailable', 'permission_denied', 'version_conflict',
                     'precondition_conflict', 'invalid_input', 'request_conflict'})


@dataclass(frozen=True, slots=True)
class RunHandle:
    """Server return value deliberately omits private login references/content."""
    id: str
    session_id: str
    plan_id: str | None
    goal_version: int | None
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Durable resource facts; a reservation is not a completed model request."""
    round_no: int
    remaining_seconds: float
    tool_count: int
    corrected: bool
    truncation_replanned: bool
    prepared_count: int
    exhausted_reason: str | None


def _handle(run):
    return RunHandle(run.id, run.session_id, run.plan_id, run.goal_version, run.status, run.version)


def runtime_busy_token(run_id):
    return 'runtime:' + UUID(_uuid(run_id)).hex


def _uuid(value):
    try:
        return TypeAdapter(UUIDText).validate_python(value)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '运行或事项编号不正确') from None


def _key(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,255}', value):
        raise HTTPException(422, '内部唤醒来源编号不正确')
    return value


def _digest(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return sha256(raw.encode('utf-8')).hexdigest()
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise HTTPException(422, '请求内容不能完整保存，请核对输入') from None


def _conflict(message='执行状态已变化，请重新读取后继续'):
    raise HTTPException(409, message)


def _clean(db):
    from .business_assistant_service import require_preparation_read_phase
    require_preparation_read_phase(db)


def _scope(db, store_id):
    from .tenancy import set_scope
    scope = db.info.get('store_scope')
    if scope is None and db.info.get('write_store') is None:
        set_scope(db, [store_id], store_id)
    elif (scope not in {(store_id,), (store_id, 0), (0, store_id)}
          or db.info.get('write_store') != store_id or db.info.get('aggregate_scope')):
        _conflict('运行控制必须使用原员工的单店范围')


def _failure(db, exc):
    db.rollback()
    if isinstance(exc, (StaleDataError, IntegrityError)):
        _conflict()
    if isinstance(exc, OperationalError):
        code = getattr(exc.orig, 'sqlstate', None) or getattr(exc.orig, 'pgcode', None)
        if code in {'40001', '40P01', '55P03'} or 'locked' in str(exc.orig).lower() or 'busy' in str(exc.orig).lower():
            _conflict('队列正在协调其他执行，请稍后重试')
    raise exc


def _race(exc):
    if isinstance(exc, (IntegrityError, StaleDataError)) or isinstance(exc, HTTPException) and exc.status_code == 409:
        return True
    if isinstance(exc, OperationalError):
        code = getattr(exc.orig, 'sqlstate', None) or getattr(exc.orig, 'pgcode', None)
        return code in {'40001', '40P01', '55P03'} or any(word in str(exc.orig).lower() for word in ('locked', 'busy'))
    return False


def _commit(db):
    from .business_assistant_service import commit
    commit(db)


def _state_event(db, run, previous_status, *, clock):
    """Append only a queue transition already made in this same transaction."""
    from .assistant_runtime_events import _append_queue_transition
    db.flush()
    _append_queue_transition(db, run, previous_status=previous_status, clock=clock)
    from .config import settings
    if (settings.assistant_notifications_enabled and run.plan_id is not None
            and previous_status != run.status
            and (run.status in {'succeeded', 'failed', 'cancelled'}
                 or run.status == 'queued' and run.auth_kind == 'login'
                 and run.trigger_kind in {'user', 'manual'})):
        # Covers normal release and lease-recovery failure. A real employee
        # continuation can also resolve an earlier same-goal attention item.
        # The consumer uses only fixed outcome fields, never reply/usage text.
        from .assistant_runtime_outbox import emit_wake_event
        emit_wake_event(db, f'run:{run.id}:{run.version}:{run.status}', 'plan', {
            'store_id': run.store_id, 'plan_id': run.plan_id,
            'source_ref': {'type': 'run', 'id': run.id, 'version': run.version}})


def _version_cas(db, row, values, *, predicates=()):
    """Fixed assistant control tables only; never disable tenancy's ORM guard."""
    if type(row) not in {Run, AssistantSession}:
        raise TypeError('Queue CAS is restricted to its two control tables')
    table = row.__table__
    conditions = [table.c.id == row.id, table.c.owner_id == row.owner_id,
                  table.c.store_id == row.store_id, table.c.version == row.version]
    if type(row) is Run:
        conditions.extend([table.c.session_id == row.session_id, table.c.status == row.status,
            table.c.fence == row.fence, table.c.lease_owner == row.lease_owner,
            table.c.lease_until == row.lease_until, table.c.plan_id == row.plan_id,
            table.c.goal_version == row.goal_version, table.c.auth_kind == row.auth_kind,
            table.c.login_session_ref == row.login_session_ref, table.c.grant_id == row.grant_id,
            table.c.stop_requested == row.stop_requested])
    else:
        conditions.extend([table.c.owner_role == row.owner_role, table.c.access_version == row.access_version])
    updated = {**values, 'version': row.version + 1}
    result = db.connection().execute(table.update().where(*conditions, *predicates).values(**updated))
    if result.rowcount != 1:
        _conflict()
    for name, value in updated.items():
        set_committed_value(row, name, value)


def _busy(db, thread, *, mode, token, now, until=None):
    from .business_assistant_service import cas_session_busy
    if not cas_session_busy(db, thread, mode=mode, token=token, now=now, until=until,
            touch_updated_at=mode != 'heartbeat', require_live=mode == 'heartbeat'):
        _conflict('会话正由其他执行处理，不能覆盖其忙标记')


def _lock_rows(db, source):
    thread = db.scalar(select(AssistantSession).where(AssistantSession.id == source['session_id'],
        AssistantSession.owner_id == source['owner_id'], AssistantSession.store_id == source['store_id'])
        .with_for_update().execution_options(populate_existing=True))
    if thread is None or (thread.owner_role, thread.access_version) != (source['role'], source['access_version']):
        _conflict()
    plan = None
    if source.get('plan_id'):
        plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == source['plan_id'],
            AssistantWorkPlan.owner_id == source['owner_id'], AssistantWorkPlan.store_id == source['store_id'],
            AssistantWorkPlan.session_id == source['session_id']).with_for_update()
            .execution_options(populate_existing=True))
        if plan is None:
            _conflict()
    run = None
    if source.get('run_id'):
        run = db.scalar(select(Run).where(Run.id == source['run_id'], Run.owner_id == source['owner_id'],
            Run.store_id == source['store_id'], Run.session_id == source['session_id'])
            .with_for_update().execution_options(populate_existing=True))
        if run is None:
            _conflict()
    return thread, plan, run


def _principal_source(principal):
    return {'owner_id': principal.actor_id, 'store_id': principal.store_id,
        'session_id': principal.session_id, 'role': principal.role,
        'access_version': principal.access_version, 'run_id': principal.run_id,
        'plan_id': principal.plan_id, 'goal_version': principal.goal_version}


def _source(reader, run, now):
    """Validate a committed queued/running source without minting a principal."""
    _enabled(run.auth_kind)
    thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == run.session_id,
        AssistantSession.owner_id == run.owner_id, AssistantSession.store_id == run.store_id))
    if thread is None:
        raise HTTPException(403, '原对话身份已失效')
    _identity(reader, run.owner_id, run.store_id, thread.owner_role, thread.access_version, run.session_id)
    plan = None
    if run.plan_id:
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == run.plan_id,
            AssistantWorkPlan.owner_id == run.owner_id, AssistantWorkPlan.store_id == run.store_id,
            AssistantWorkPlan.session_id == run.session_id))
        if (plan is None or plan.engine_version != 2 or plan.status != 'active'
                or plan.goal_version != run.goal_version):
            _conflict('事项范围已变化，原执行不能继续')
    elif run.goal_version is not None:
        _conflict()
    grant = None
    if run.auth_kind == 'login':
        if run.grant_id is not None:
            _conflict()
        _login(reader, run.login_session_ref, run.owner_id, now)
    elif run.auth_kind == 'grant':
        grant = reader.scalar(select(FollowupGrant).where(FollowupGrant.id == run.grant_id))
        if (grant is None or grant.status != 'active' or grant.revoked_at is not None
                or run.login_session_ref is not None or plan is None
                or (grant.owner_id, grant.store_id, grant.session_id, grant.plan_id,
                    grant.owner_role, grant.access_version, grant.goal_version)
                != (run.owner_id, run.store_id, run.session_id, run.plan_id,
                    thread.owner_role, thread.access_version, run.goal_version)
                or grant.expires_at is not None and _time(grant.expires_at) <= now):
            raise HTTPException(403, '持续跟进授权已失效')
    else:
        raise HTTPException(403, '执行身份来源不正确')
    return {'owner_id': run.owner_id, 'store_id': run.store_id, 'session_id': run.session_id,
        'role': thread.owner_role, 'access_version': thread.access_version, 'run_id': run.id,
        'plan_id': run.plan_id, 'goal_version': run.goal_version,
        'session_version': thread.version, 'plan_version': plan.version if plan else None,
        'run_version': run.version, 'grant_version': grant.version if grant else None}


def _fresh_source(db, run_id, *, clock, read_session_factory=None):
    with _reader(db, read_session_factory) as reader:
        run = reader.scalar(select(Run).where(Run.id == run_id))
        if run is None:
            raise HTTPException(404, '执行不存在或不可访问')
        return _source(reader, run, _time(clock()))


def _maintenance_snapshot(db, run_id, *, clock, read_session_factory=None):
    """Internal control evidence only; failure never grants access to content."""
    with _reader(db, read_session_factory) as reader:
        run = reader.scalar(select(Run).where(Run.id == run_id))
        if run is None:
            raise HTTPException(404, '执行不存在')
        thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == run.session_id,
            AssistantSession.owner_id == run.owner_id, AssistantSession.store_id == run.store_id))
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == run.plan_id,
            AssistantWorkPlan.owner_id == run.owner_id, AssistantWorkPlan.store_id == run.store_id,
            AssistantWorkPlan.session_id == run.session_id)) if run.plan_id else None
        if thread is None or run.plan_id and plan is None:
            _conflict('执行归属不完整，需先核对持久记录')
        source = {'owner_id': run.owner_id, 'store_id': run.store_id, 'session_id': run.session_id,
            'role': thread.owner_role, 'access_version': thread.access_version, 'run_id': run.id,
            'plan_id': run.plan_id, 'goal_version': run.goal_version, 'session_version': thread.version,
            'plan_version': plan.version if plan else None, 'run_version': run.version,
            'status': run.status, 'stop_requested': run.stop_requested, 'lease_until': run.lease_until,
            'authorized': True, 'error_code': None}
        try:
            _source(reader, run, _time(clock()))
        except HTTPException as exc:
            # These codes are produced only by the fixed identity/source
            # checks above, not arbitrary business/native response strings.
            if exc.status_code not in {401, 403, 409, 503}:
                raise
            source['authorized'] = False
            source['error_code'] = ('permission_denied' if exc.status_code in {401, 403}
                                    else 'precondition_conflict' if exc.status_code == 409 else 'runtime_unavailable')
        return source


def _cancel_invalid_candidate(db, source, *, clock, read_session_factory):
    _scope(db, source['store_id'])
    with db.no_autoflush:
        thread, plan, run = _lock_rows(db, source)
        _source_versions(source, thread, plan, run)
        if run.status != 'queued' or source['authorized'] and not run.stop_requested:
            _conflict()
        now = _time(clock())
        _version_cas(db, thread, {'updated_at': now})
        _version_cas(db, run, {'status': 'cancelled', 'stop_requested': True,
            'lease_owner': None, 'lease_until': None, 'finished_at': now,
            'error_code': source['error_code'] or 'precondition_conflict'})
        _skip_pending(db, run, now)
        _release_busy(db, thread, run, now)
        _state_event(db, run, 'queued', clock=clock)
    latest = _maintenance_snapshot(db, run.id, clock=clock, read_session_factory=read_session_factory)
    if latest['authorized'] and not latest['stop_requested']:
        _conflict('执行来源已恢复，请重新判断')
    _commit(db)


def _source_versions(source, thread, plan, run):
    if (source['session_version'] != thread.version or source['run_version'] != run.version
            or source['plan_version'] != (plan.version if plan else None)):
        _conflict()


def _leased(run, principal, now, *, control=False):
    if (run.status != 'running' or run.lease_until is None or _time(run.lease_until) <= now
            or not control and run.stop_requested
            or (run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version,
                run.auth_kind, run.grant_id, run.login_session_ref, run.lease_owner, run.fence)
            != (principal.actor_id, principal.store_id, principal.session_id, principal.plan_id,
                principal.goal_version, principal.auth_kind, principal.grant_id, principal._login_ref,
                principal.lease_owner, principal.fence)):
        _conflict('执行租约已失效，旧执行不能写入或释放新租约')


def _original_login(db, request, user, session_id, *, clock, read_session_factory=None):
    """Only original employee requests; HTTP adapters must enforce POST/CSRF."""
    if runtime_request_context(request) is not None:
        raise HTTPException(403, '请由员工本人发送请求')
    principal = principal_for_request(db, request, user, session_id,
        clock=clock, read_session_factory=read_session_factory)
    if principal.auth_kind != 'login' or principal.run_id is not None:
        raise HTTPException(403, '请由员工本人发送请求')
    return principal


async def _validate_entry(db, principal, entry, *, client_factory=None):
    if entry is None:
        return None
    from .assistant_runtime_objects import read_object
    from .assistant_runtime_principal import native_reader_for_principal
    from .assistant_runtime_registry import domain_registry
    from .assistant_runtime_schemas import BusinessObjectRef
    providers = domain_registry()

    async def native(operation_id, **args):
        if not operation_id.startswith('GET ') or providers.spec_for_operation(operation_id) is None:
            raise HTTPException(403, '入口只能核对已登记的原业务查询')
        return await native_reader_for_principal(db, principal, (operation_id,), client_factory=client_factory)(operation_id, **args)

    if entry['source_type'] == 'workflow':
        from .workflow_guides_api import load_catalogue
        guide = next((row for row in load_catalogue() if row['id'] == entry['workflow_id']), None)
        if (guide is None or principal.role not in guide.get('roles', [])
                or principal.role not in guide.get('entry', {}).get('roles', [])):
            raise HTTPException(404, '此操作入口不存在或当前岗位不可进入')
    elif entry['source_type'] == 'object':
        await read_object(principal, BusinessObjectRef.model_validate(entry['object_ref']), native_reader=native, registry=providers)
    else:
        from .flow_models import Task
        with _reader(db, principal._read_session_factory) as reader:
            task = reader.scalar(select(Task).where(Task.id == entry['task_id'], Task.store_id == principal.store_id))
            case_id = task.case_id if task is not None else None
        if case_id is None:
            raise HTTPException(404, '待办不存在或当前岗位不可查看')
        snapshot = await read_object(principal, BusinessObjectRef(type='case', id=case_id), native_reader=native, registry=providers)
        if not any(task.id == entry['task_id'] and task.case_id == case_id for task in snapshot.tasks):
            raise HTTPException(404, '待办未由可见原单返回')
    revalidate_principal(db, principal)
    return deepcopy(entry)


def _existing(db, principal, trigger_key, digest):
    with _reader(db, principal._read_session_factory) as reader:
        row = reader.scalar(select(Run).where(Run.owner_id == principal.actor_id,
            Run.store_id == principal.store_id, Run.trigger_key == trigger_key))
        if row is None:
            return None
        if row.session_id != principal.session_id or row.request_digest != digest:
            _conflict('这次发送编号已被使用，请保持原正文、思考设置和入口')
        return _handle(row)


def _existing_mcp(db, principal, trigger_key, digest):
    from .assistant_runtime_mcp import is_mcp_run
    with _reader(db, principal._read_session_factory) as reader:
        row = reader.scalar(select(Run).where(Run.owner_id == principal.actor_id,
            Run.store_id == principal.store_id, Run.trigger_key == trigger_key))
        if row is None:
            return None
        if (row.session_id != principal.session_id or row.request_digest != digest
                or not is_mcp_run(row)):
            _conflict('此工具请求编号已被使用，请保持原工具和完整参数')
        return _handle(row)


def enqueue_mcp_run(db, request, user, session_id, request_id, name, args, *,
                    clock=utcnow, read_session_factory=None):
    """Persist an employee's complete tool request without a message or model.

    The static MCP builder writes the only tool envelope in the same transaction.
    It cannot perform native reads, issue a Grant, bind a Plan or commit here.
    """
    from .assistant_runtime_mcp import create_request_item
    from .assistant_runtime_registry import registry_for_config
    from .business_assistant_service import AssistantConfig, scrub
    _clean(db)
    session_id = _uuid(session_id)
    try:
        request_id = TypeAdapter(MessageRequestId).validate_python(request_id)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '工具请求编号不正确') from None
    canonical = registry_for_config(AssistantConfig(tool_profile='business_v1')).validate_arguments(name, args)
    if _digest(scrub(canonical)) != _digest(canonical):
        raise HTTPException(422, '工具参数含不能完整保存的内容，请核对后发送')
    digest = _digest({'schema_version': 1, 'tool_profile': 'business_v1',
        'name': name, 'arguments': canonical})
    principal = _original_login(db, request, user, session_id, clock=clock,
        read_session_factory=read_session_factory)
    trigger_key = f'mcp:{session_id}:{request_id}'
    existing = _existing_mcp(db, principal, trigger_key, digest)
    if existing is not None:
        revalidate_principal(db, principal, clock=clock)
        return existing
    _scope(db, principal.store_id)
    try:
        with db.no_autoflush:
            thread, _, _ = _lock_rows(db, _principal_source(principal))
            now = _time(clock())
            if (thread.busy_token is not None and thread.busy_until is not None
                    and _time(thread.busy_until) > now
                    or db.scalar(select(Run.id).where(Run.session_id == session_id,
                        Run.status == 'running').limit(1)) is not None):
                # Even an expired running lease must first be reclaimed; a new
                # request must not invalidate the old worker's source snapshot.
                _conflict('当前对话正在处理，请稍后再发送新的工具请求')
            _version_cas(db, thread, {'updated_at': now})
            run = Run(id=str(uuid4()), owner_id=principal.actor_id, store_id=principal.store_id,
                session_id=session_id, plan_id=None, goal_version=None,
                trigger_kind='manual', trigger_key=trigger_key, request_id=request_id,
                request_digest=digest, entry_context=None, auth_kind='login',
                login_session_ref=principal._login_ref, grant_id=None,
                status='queued', next_run_at=now, priority=50)
            db.add(run)
            create_request_item(db, run, name, deepcopy(canonical))
            _state_event(db, run, None, clock=clock)
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        db.rollback()
        if _race(exc):
            existing = _existing_mcp(db, principal, trigger_key, digest)
            if existing is not None:
                revalidate_principal(db, principal, clock=clock)
                return existing
        _failure(db, exc)
    revalidate_principal(db, principal, clock=clock)
    return _handle(run)


async def enqueue_run(db, request, user, session_id, args, *, clock=utcnow,
                      read_session_factory=None, client_factory=None):
    """Atomically persist exactly one original user message and one Run."""
    _clean(db)
    session_id = _uuid(session_id)
    try:
        body = RunCreate.model_validate(args.model_dump(mode='python') if isinstance(args, RunCreate) else args)
        payload = body.model_dump(mode='json')
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '请核对完整消息和原入口参数') from None
    principal = _original_login(db, request, user, session_id, clock=clock, read_session_factory=read_session_factory)
    digest = _digest({'schema_version': 1, **payload})
    trigger_key = f'user:{session_id}:{body.request_id}'
    existing = _existing(db, principal, trigger_key, digest)
    if existing is not None:
        revalidate_principal(db, principal, clock=clock)
        return existing
    entry = await _validate_entry(db, principal, payload['entry_context'], client_factory=client_factory)
    source = _principal_source(principal)
    source['plan_id'] = body.plan_id
    try:
        _sqlite_writer(db)
        revalidate_principal(db, principal, clock=clock)
        _scope(db, principal.store_id)
        with db.no_autoflush:
            thread, plan, _ = _lock_rows(db, source)
            if plan is not None and (plan.engine_version != 2 or plan.status != 'active'):
                _conflict('请先核对当前可继续的事项')
            if db.scalar(select(AssistantMessage.id).where(AssistantMessage.session_id == session_id,
                    AssistantMessage.request_id == body.request_id)) is not None:
                _conflict('此编号已属于原对话消息，不能另建一次执行')
            now = _time(clock())
            _version_cas(db, thread, {'updated_at': now, **({'title': body.content[:36]} if thread.title == '新对话' else {})})
            run = Run(id=str(uuid4()), owner_id=principal.actor_id, store_id=principal.store_id,
                session_id=session_id, plan_id=plan.id if plan else None,
                goal_version=plan.goal_version if plan else None, trigger_kind='user', trigger_key=trigger_key,
                request_id=body.request_id, request_digest=digest, entry_context=entry,
                auth_kind='login', login_session_ref=principal._login_ref, grant_id=None,
                status='queued', next_run_at=now, priority=100)
            db.add(run)
            db.add(AssistantMessage(store_id=principal.store_id, session_id=session_id,
                request_id=body.request_id, role='user', content=body.content, thinking=body.thinking))
            # Priority is observed at a complete tool boundary. Setting stop
            # here would revoke the background worker's in-flight checkpoint.
            _state_event(db, run, None, clock=clock)
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        db.rollback()
        if _race(exc):
            existing = _existing(db, principal, trigger_key, digest)
            if existing is not None:
                revalidate_principal(db, principal, clock=clock)
                return existing
        _failure(db, exc)
    revalidate_principal(db, principal, clock=clock)
    return _handle(run)


def _fresh_worker_session(db):
    _clean(db)
    if db.in_transaction() or db.info.get('store_scope') is not None or db.info.get('write_store') is not None:
        _conflict('队列调度需要新的无事务会话，不能复用旧权限快照')


def _slot_lock(db):
    """First SQL in a fresh claim TX; PG refuses contention, SQLite reserves writes."""
    connection = db.connection()
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE business_assistant_runs IN SHARE ROW EXCLUSIVE MODE NOWAIT')
    elif connection.dialect.name == 'sqlite':
        table = Run.__table__
        connection.execute(table.update().where(false()).values(version=table.c.version))
    else:
        raise HTTPException(503, '运行队列仅支持已评审的SQLite或PostgreSQL事务')


def _sqlite_writer(db):
    """Reserve only the short SQLite write, retaining the principal's Engine."""
    if db.get_bind().dialect.name == 'sqlite':
        _clean(db)
        db.rollback()
        _slot_lock(db)


def claim_next(db, lease_owner, *, clock=utcnow, read_session_factory=None):
    """Claim one global slot; commit before issuing its RuntimePrincipal."""
    return _claim_queued_run(db, lease_owner, clock=clock,
        read_session_factory=read_session_factory)


def claim_mcp_run(db, run_id, lease_owner, *, clock=utcnow, read_session_factory=None):
    """Claim only this fixed MCP request; never execute a neighbouring Run."""
    return _claim_queued_run(db, lease_owner, target_run_id=_uuid(run_id), clock=clock,
        read_session_factory=read_session_factory)


def _claim_queued_run(db, lease_owner, *, target_run_id=None, clock=utcnow,
                      read_session_factory=None):
    """Shared global-slot, Session busy and fence transaction for both callers."""
    _enabled()
    if type(lease_owner) is not str or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,80}', lease_owner):
        raise HTTPException(422, 'Worker租约持有者编号不正确')
    _fresh_worker_session(db)
    try:
        _slot_lock(db)
        now = _time(clock())
        if db.scalar(select(Run.id).where(Run.status == 'running', Run.lease_until > now).limit(WORKER_SLOTS)):
            db.rollback()
            return None
        from .config import settings
        other = Run.__table__.alias('other_active_run')
        occupied = exists(select(other.c.id).where(other.c.id != Run.id, other.c.status == 'running',
            or_(other.c.session_id == Run.session_id,
                and_(Run.plan_id.is_not(None), other.c.plan_id == Run.plan_id))))
        candidate = db.scalar(select(Run).join(AssistantSession, AssistantSession.id == Run.session_id)
            .where(Run.status == 'queued', Run.next_run_at <= now, ~occupied,
                or_(Run.auth_kind != 'grant', settings.assistant_followup_enabled),
                or_(AssistantSession.busy_token.is_(None), AssistantSession.busy_until.is_(None), AssistantSession.busy_until <= now))
            .order_by(Run.priority.desc(), Run.next_run_at, Run.created_at, Run.id).limit(1))
        if candidate is None or target_run_id is not None and candidate.id != target_run_id:
            # A targeted HTTP caller may claim only when its request is also
            # the next globally eligible Run; it must not bypass user priority.
            db.rollback()
            return None
        if target_run_id is not None:
            from .assistant_runtime_mcp import is_mcp_run
            if not is_mcp_run(candidate):
                _conflict('此执行不是已保存的 MCP 工具请求')
        source = _maintenance_snapshot(db, candidate.id, clock=clock, read_session_factory=read_session_factory)
        if not source['authorized'] or source['stop_requested']:
            _cancel_invalid_candidate(db, source, clock=clock, read_session_factory=read_session_factory)
            return None
        _scope(db, source['store_id'])
        thread, plan, run = _lock_rows(db, source)
        _source_versions(source, thread, plan, run)
        if run.status != 'queued' or run.stop_requested or run.next_run_at > now:
            _conflict()
        if db.scalar(select(Run.id).where(Run.id != run.id, Run.status == 'running',
                or_(Run.session_id == run.session_id, Run.plan_id == run.plan_id if run.plan_id else false())).limit(1)):
            db.rollback()
            return None
        token, until = runtime_busy_token(run.id), now + timedelta(seconds=LEASE_SECONDS)
        _busy(db, thread, mode='claim', token=token, now=now, until=until)
        _version_cas(db, run, {'status': 'running', 'lease_owner': lease_owner, 'lease_until': until,
            'fence': run.fence + 1, 'attempt': run.attempt + 1,
            'started_at': run.started_at or now, 'finished_at': None, 'error_code': None},
            predicates=(Run.__table__.c.next_run_at <= now,))
        _state_event(db, run, 'queued', clock=clock)
        # The independent source is still committed queued here; it validates
        # authority/goal, not the pending running mutation or mutable versions.
        _fresh_source(db, run.id, clock=clock, read_session_factory=read_session_factory)
        run_id, fence = run.id, run.fence
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    return principal_for_run(db, run_id, lease_owner=lease_owner, fence=fence,
        clock=clock, read_session_factory=read_session_factory)


def heartbeat(db, principal, *, clock=utcnow):
    _clean(db)
    revalidate_principal(db, principal, clock=clock)
    _scope(db, principal.store_id)
    try:
        _sqlite_writer(db)
        with db.no_autoflush:
            thread, _, run = _lock_rows(db, _principal_source(principal))
            now = _time(clock())
            _leased(run, principal, now)
            until = now + timedelta(seconds=LEASE_SECONDS)
            _version_cas(db, run, {'lease_until': until})
            _busy(db, thread, mode='heartbeat', token=runtime_busy_token(run.id), now=now, until=until)
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    return until


def _grant_source(db, grant_id, *, clock, read_session_factory=None):
    _enabled('grant')
    with _reader(db, read_session_factory) as reader:
        grant = reader.scalar(select(FollowupGrant).where(FollowupGrant.id == grant_id))
        if (grant is None or grant.status != 'active' or grant.revoked_at is not None
                or grant.expires_at is not None and _time(grant.expires_at) <= _time(clock())):
            raise HTTPException(403, '持续跟进授权已失效')
        _identity(reader, grant.owner_id, grant.store_id, grant.owner_role, grant.access_version, grant.session_id)
        thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == grant.session_id))
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == grant.plan_id,
            AssistantWorkPlan.owner_id == grant.owner_id, AssistantWorkPlan.store_id == grant.store_id,
            AssistantWorkPlan.session_id == grant.session_id))
        if plan is None or plan.engine_version != 2 or plan.status != 'active' or plan.goal_version != grant.goal_version:
            _conflict('原授权事项范围已变化')
        return {'owner_id': grant.owner_id, 'store_id': grant.store_id, 'session_id': grant.session_id,
            'role': grant.owner_role, 'access_version': grant.access_version, 'plan_id': grant.plan_id,
            'goal_version': grant.goal_version, 'session_version': thread.version, 'plan_version': plan.version,
            'grant_id': grant.id, 'grant_version': grant.version, 'auth_kind': 'grant', 'login_session_ref': None}


def _find_internal(db, source, trigger_key, digest, factory):
    with _reader(db, factory) as reader:
        row = reader.scalar(select(Run).where(Run.owner_id == source['owner_id'],
            Run.store_id == source['store_id'], Run.trigger_key == trigger_key))
        if row is None:
            return None
        if row.session_id != source['session_id'] or row.request_digest != digest:
            _conflict('同一唤醒编号的来源或授权范围已变化')
        return _handle(row)


def _enqueue_internal(db, source, *, trigger_kind, trigger_key, digest, check, clock, factory):
    old = _find_internal(db, source, trigger_key, digest, factory)
    if old is not None:
        check()
        return old
    _scope(db, source['store_id'])
    try:
        with db.no_autoflush:
            thread, plan, _ = _lock_rows(db, source)
            if (thread.version != source['session_version'] or plan is None
                    or plan.version != source['plan_version'] or plan.status != 'active'
                    or plan.engine_version != 2 or plan.goal_version != source['goal_version']):
                _conflict()
            now = _time(clock())
            _version_cas(db, thread, {'updated_at': now})
            run = Run(id=str(uuid4()), owner_id=source['owner_id'], store_id=source['store_id'],
                session_id=source['session_id'], plan_id=plan.id, goal_version=plan.goal_version,
                trigger_kind=trigger_kind, trigger_key=trigger_key, request_id=None,
                request_digest=digest, entry_context=None, auth_kind=source['auth_kind'],
                login_session_ref=source['login_session_ref'], grant_id=source['grant_id'],
                status='queued', next_run_at=now, priority=50 if trigger_kind == 'manual' else 0)
            db.add(run)
            _state_event(db, run, None, clock=clock)
        check()
        _commit(db)
    except Exception as exc:
        db.rollback()
        if _race(exc):
            old = _find_internal(db, source, trigger_key, digest, factory)
            if old is not None:
                check()
                return old
        _failure(db, exc)
    check()
    return _handle(run)


def enqueue_signal_run(db, grant_id, signal_key, *, clock=utcnow, read_session_factory=None):
    """Dispatcher-only: a fixed source key wakes one currently granted goal."""
    _clean(db)
    resolved = resolve_signal_runs(db, (_uuid(grant_id),), signal_key, clock=clock,
                                   read_session_factory=read_session_factory)
    source = _signal_resolutions[resolved]['sources'][0]
    old = _find_internal(db, source, source['trigger_key'], source['digest'], read_session_factory)
    if old is not None:
        validate_signal_resolution(db, resolved, clock=clock)
        return old
    try:
        handles = persist_signal_runs(db, resolved, clock=clock)
        validate_signal_resolution(db, resolved, clock=clock)
        _commit(db)
    except Exception as exc:
        db.rollback()
        if _race(exc):
            state = _signal_resolutions.get(resolved)
            source = state['sources'][0] if state is not None else None
            old = _find_internal(db, source, source['trigger_key'], source['digest'], read_session_factory) if source else None
            if old is not None:
                validate_signal_resolution(db, resolved, clock=clock)
                return old
        _failure(db, exc)
    validate_signal_resolution(db, resolved, clock=clock)
    return handles[0]


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ResolvedSignalRuns:
    """One-use, same-session server authority for a complete signal fan-out."""


_signal_resolutions = WeakKeyDictionary()
_SIGNAL_RESOLUTION_SECONDS = 60
_SIGNAL_AUTH_FIELDS = ('owner_id', 'store_id', 'session_id', 'role', 'access_version',
                       'plan_id', 'goal_version', 'grant_id', 'grant_version')


def resolve_signal_runs(db, grant_ids, signal_key, *, clock=utcnow, read_session_factory=None):
    """Resolve all real Grant sources before any outbox/queue write transaction."""
    _clean(db)
    _enabled('grant')
    signal_key = _key(signal_key)
    if type(grant_ids) is not tuple or len(set(grant_ids)) != len(grant_ids):
        raise ValueError('Signal fan-out requires distinct server-selected Grant IDs')
    sources = []
    for grant_id in sorted(_uuid(value) for value in grant_ids):
        source = _grant_source(db, grant_id, clock=clock, read_session_factory=read_session_factory)
        payload = {'schema_version': 1, 'trigger_kind': 'signal', 'plan_id': source['plan_id'],
            'goal_version': source['goal_version'], 'grant_id': grant_id, 'signal_key': signal_key}
        source.update(trigger_key=f"signal:{source['plan_id']}:{source['goal_version']}:{sha256(signal_key.encode()).hexdigest()}",
                      digest=_digest(payload))
        sources.append(source)
    if len({source['store_id'] for source in sources}) > 1 or len({source['plan_id'] for source in sources}) != len(sources):
        _conflict('One signal may target only distinct Plans in its original store')
    for session_id in {source['session_id'] for source in sources}:
        group = [source for source in sources if source['session_id'] == session_id]
        if len({(row['owner_id'], row['role'], row['access_version'], row['session_version']) for row in group}) != 1:
            _conflict()
    token = ResolvedSignalRuns()
    _signal_resolutions[token] = {'session_ref': ref(db), 'bind': db.get_bind(),
        'sources': sources, 'factory': read_session_factory, 'issued_at': monotonic(),
        'consumed': False, 'transaction_ref': None}
    validate_signal_resolution(db, token, clock=clock)
    return token


def _signal_state(db, token):
    state = _signal_resolutions.get(token) if type(token) is ResolvedSignalRuns else None
    if (state is None or state['session_ref']() is not db or state['bind'] is not db.get_bind()
            or not 0 <= monotonic() - state['issued_at'] <= _SIGNAL_RESOLUTION_SECONDS):
        _conflict('Signal resolution has expired or belongs to another database session')
    return state


def validate_signal_resolution(db, resolved, *, clock=utcnow):
    """Fresh source authorization; caller repeats this immediately before commit."""
    state = _signal_state(db, resolved)
    for source in state['sources']:
        latest = _grant_source(db, source['grant_id'], clock=clock, read_session_factory=state['factory'])
        if any(latest[key] != source[key] for key in _SIGNAL_AUTH_FIELDS):
            _conflict('原跟进授权已变化')


def persist_signal_runs(db, resolved, *, clock=utcnow):
    """Persist a whole fan-out, without commit, network or native business calls.

    Lock all Sessions, then Plans in stable order before creating any Run. This
    avoids self-conflicts when several Plans share the same employee session.
    The caller owns rollback and the outbox CAS in this same short transaction.
    """
    _clean(db)
    state = _signal_state(db, resolved)
    if state['consumed']:
        _conflict('Signal resolution has already been consumed')
    state['consumed'] = True
    validate_signal_resolution(db, resolved, clock=clock)
    sources = state['sources']
    if not sources:
        return ()
    _scope(db, sources[0]['store_id'])
    threads, plans, handles = {}, {}, []
    with db.no_autoflush:
        for sid in sorted({source['session_id'] for source in sources}):
            source = next(source for source in sources if source['session_id'] == sid)
            thread = db.scalar(select(AssistantSession).where(AssistantSession.id == sid,
                AssistantSession.owner_id == source['owner_id'], AssistantSession.store_id == source['store_id'])
                .with_for_update().execution_options(populate_existing=True))
            if (thread is None or (thread.owner_role, thread.access_version, thread.version)
                    != (source['role'], source['access_version'], source['session_version'])):
                _conflict()
            threads[sid] = thread
        for source in sorted(sources, key=lambda row: row['plan_id']):
            plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == source['plan_id'],
                AssistantWorkPlan.owner_id == source['owner_id'], AssistantWorkPlan.store_id == source['store_id'],
                AssistantWorkPlan.session_id == source['session_id']).with_for_update()
                .execution_options(populate_existing=True))
            if (plan is None or (plan.version, plan.goal_version, plan.engine_version, plan.status)
                    != (source['plan_version'], source['goal_version'], 2, 'active')):
                _conflict()
            plans[plan.id] = plan
        touched = set()
        for source in sorted(sources, key=lambda row: row['trigger_key']):
            old = db.scalar(select(Run).where(Run.owner_id == source['owner_id'],
                Run.store_id == source['store_id'], Run.trigger_key == source['trigger_key'])
                .execution_options(populate_existing=True))
            if old is not None:
                if old.session_id != source['session_id'] or old.request_digest != source['digest']:
                    _conflict('同一唤醒编号的来源或授权范围已变化')
                handles.append(_handle(old))
                continue
            now = _time(clock())
            if source['session_id'] not in touched:
                _version_cas(db, threads[source['session_id']], {'updated_at': now})
                touched.add(source['session_id'])
            run = Run(id=str(uuid4()), owner_id=source['owner_id'], store_id=source['store_id'],
                session_id=source['session_id'], plan_id=source['plan_id'], goal_version=source['goal_version'],
                trigger_kind='signal', trigger_key=source['trigger_key'], request_id=None,
                request_digest=source['digest'], entry_context=None, auth_kind='grant',
                login_session_ref=None, grant_id=source['grant_id'], status='queued', next_run_at=now, priority=0)
            db.add(run)
            _state_event(db, run, None, clock=clock)
            handles.append(_handle(run))
    state['transaction_ref'] = ref(db.get_transaction())
    return tuple(handles)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ResolvedFollowupRuns:
    """One-use binding between real condition checks and their original sources."""


_followup_resolutions = WeakKeyDictionary()
_FOLLOWUP_RESOLUTION_SECONDS = 60


def _followup_occupied(db, source, now):
    thread = db.scalar(select(AssistantSession).where(AssistantSession.id == source['session_id'],
        AssistantSession.owner_id == source['owner_id'], AssistantSession.store_id == source['store_id']))
    if thread is None:
        _conflict()
    if thread.busy_token and thread.busy_until is not None and _time(thread.busy_until) > now:
        return True
    return db.scalar(select(Run.id).where(Run.owner_id == source['owner_id'],
        Run.store_id == source['store_id'], Run.status.in_({'queued', 'running'}),
        or_(Run.session_id == source['session_id'], Run.plan_id == source['plan_id'])).limit(1)) is not None


def resolve_followup_runs(db, checks, *, clock=utcnow, read_session_factory=None):
    """Bind already-read, issued checks; signals and periodic checks share a key.

    No event ID, observation time, Grant generation or transient assistant
    version enters the key/digest. A terminal result for these same facts is
    retained, never reset into another automatic attempt.
    """
    from .assistant_runtime_plans import FollowupCheck, validate_followup_check
    _clean(db)
    _enabled('grant')
    if type(checks) is not tuple or any(type(check) is not FollowupCheck for check in checks):
        raise ValueError('Follow-up scheduling requires issued condition checks')
    entries = []
    for check in checks:
        principal = validate_followup_check(db, check, clock=clock)
        if (principal.run_id is not None or principal.auth_kind != 'grant'
                or (check.plan_id, check.goal_version, check.grant_id)
                != (principal.plan_id, principal.goal_version, principal.grant_id)
                or type(check.fingerprint) is not str or not re.fullmatch(r'[0-9a-f]{64}', check.fingerprint)
                or type(check.ready) is not bool or type(check.required_complete) is not bool):
            _conflict('Follow-up checks must retain their actual Grant scope')
        factory = read_session_factory if read_session_factory is not None else principal._read_session_factory
        source = _grant_source(db, principal.grant_id, clock=clock, read_session_factory=factory)
        if (source['owner_id'], source['store_id'], source['session_id'], source['role'],
                source['access_version'], source['plan_id'], source['goal_version'], source['grant_version']) != (
                principal.actor_id, principal.store_id, principal.session_id, principal.role,
                principal.access_version, principal.plan_id, principal.goal_version, principal._probe_grant_version):
            _conflict()
        with _reader(db, factory) as reader:
            occupied = _followup_occupied(reader, source, _time(clock()))
        payload = {'schema_version': 1, 'trigger_kind': 'followup', 'owner_id': source['owner_id'],
            'store_id': source['store_id'], 'session_id': source['session_id'],
            'plan_id': source['plan_id'], 'goal_version': source['goal_version'], 'fingerprint': check.fingerprint}
        entries.append({'check': check, 'principal': principal, 'source': source, 'factory': factory,
            'fingerprint': check.fingerprint, 'occupied': occupied,
            'trigger_key': f"followup:{source['plan_id']}:{source['goal_version']}:{check.fingerprint}",
            'digest': _digest(payload)})
    if (len({entry['source']['store_id'] for entry in entries}) > 1
            or len({entry['source']['plan_id'] for entry in entries}) != len(entries)):
        _conflict('Follow-up scheduling requires distinct Plans in one store')
    token = ResolvedFollowupRuns()
    _followup_resolutions[token] = {'session_ref': ref(db), 'bind': db.get_bind(),
        'entries': entries, 'issued_at': monotonic(), 'consumed': False, 'transaction_ref': None}
    validate_followup_resolution(db, token, clock=clock)
    return token


def _followup_state(db, token):
    state = _followup_resolutions.get(token) if type(token) is ResolvedFollowupRuns else None
    if (state is None or state['session_ref']() is not db or state['bind'] is not db.get_bind()
            or not 0 <= monotonic() - state['issued_at'] <= _FOLLOWUP_RESOLUTION_SECONDS):
        _conflict('Follow-up resolution has expired or belongs to another database session')
    if state['transaction_ref'] is not None and (db.get_transaction() is None
            or state['transaction_ref']() is not db.get_transaction()):
        _conflict('Follow-up resolution belongs to another transaction')
    return state


def validate_followup_resolution(db, resolved, *, clock=utcnow):
    """Final committed-source check, including a pending in-TX completion.

    Plan completion and Grant revocation are still uncommitted when this runs.
    The independent reader must see the original authorization that permitted
    that narrow control change. It does not grant a stopped worker a write.
    """
    from .assistant_runtime_plans import validate_followup_check
    _enabled('grant')
    state = _followup_state(db, resolved)
    for entry in state['entries']:
        principal = validate_followup_check(db, entry['check'], clock=clock)
        if principal is not entry['principal'] or entry['check'].fingerprint != entry['fingerprint']:
            _conflict()
        latest = _grant_source(db, entry['source']['grant_id'], clock=clock,
                               read_session_factory=entry['factory'])
        if any(latest[key] != entry['source'][key] for key in _SIGNAL_AUTH_FIELDS):
            _conflict('原跟进授权已变化')


def _existing_followup(db, entry):
    source = entry['source']
    old = db.scalar(select(Run).where(Run.owner_id == source['owner_id'], Run.store_id == source['store_id'],
        Run.trigger_key == entry['trigger_key']).execution_options(populate_existing=True))
    if old is None:
        return None
    if (old.request_digest != entry['digest'] or old.session_id != source['session_id']
            or old.plan_id != source['plan_id'] or old.goal_version != source['goal_version']
            or old.auth_kind != 'grant' or old.trigger_kind != 'signal'
            or old.request_id is not None or old.login_session_ref is not None):
        _conflict('A facts key already belongs to a different follow-up source')
    grant = db.scalar(select(FollowupGrant).where(FollowupGrant.id == old.grant_id,
        FollowupGrant.owner_id == source['owner_id'], FollowupGrant.store_id == source['store_id'],
        FollowupGrant.session_id == source['session_id'], FollowupGrant.plan_id == source['plan_id'],
        FollowupGrant.goal_version == source['goal_version']))
    if grant is None:
        _conflict()
    return old


def persist_followup_runs(db, resolved, *, clock=utcnow):
    """Save condition progress and eligible Run inserts in one caller-owned TX.

    The only preparation/control writer here is plans.persist_followup_checks;
    no caller callback or generic probe write capability is accepted. It locks
    all Session/Plan/Grant sources and proves every snapshot before changing any
    Step. The queue then uses those returned *new* versions, not the old signal
    resolver's versions, to create at most one queued Run per idle session.
    """
    from .assistant_runtime_plans import persist_followup_checks
    _clean(db)
    state = _followup_state(db, resolved)
    if state['consumed']:
        _conflict('Follow-up resolution has already been consumed')
    validate_followup_resolution(db, resolved, clock=clock)
    state['consumed'] = True
    entries = state['entries']
    if not entries:
        return ()
    _scope(db, entries[0]['source']['store_id'])
    results = persist_followup_checks(db, tuple(entry['check'] for entry in entries), clock=clock)
    if len(results) != len(entries) or {result.plan_id for result in results} != {entry['source']['plan_id'] for entry in entries}:
        _conflict('Condition persistence returned an incomplete Plan set')
    by_plan = {result.plan_id: result for result in results}
    threads = {}
    # Check the whole batch before this queue's own Session CAS changes any of
    # the post-condition versions shared by two Plans in the same session.
    with db.no_autoflush:
        for entry in entries:
            source, result = entry['source'], by_plan[entry['source']['plan_id']]
            if ((result.plan_id, result.goal_version, result.grant_id, result.fingerprint)
                    != (source['plan_id'], source['goal_version'], source['grant_id'], entry['fingerprint'])
                    or type(result.ready) is not bool or type(result.completed) is not bool
                    or result.ready and (result.completed or not entry['check'].ready)
                    or result.completed and not entry['check'].required_complete):
                _conflict()
            thread = db.scalar(select(AssistantSession).where(AssistantSession.id == source['session_id'],
                AssistantSession.owner_id == source['owner_id'], AssistantSession.store_id == source['store_id']))
            plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == source['plan_id'],
                AssistantWorkPlan.owner_id == source['owner_id'], AssistantWorkPlan.store_id == source['store_id'],
                AssistantWorkPlan.session_id == source['session_id']))
            grant = db.scalar(select(FollowupGrant).where(FollowupGrant.id == source['grant_id'],
                FollowupGrant.owner_id == source['owner_id'], FollowupGrant.store_id == source['store_id'],
                FollowupGrant.plan_id == source['plan_id'], FollowupGrant.session_id == source['session_id']))
            if (thread is None or plan is None or grant is None
                    or (thread.owner_role, thread.access_version, thread.version)
                    != (source['role'], source['access_version'], result.session_version)
                    or (plan.engine_version, plan.goal_version, plan.version)
                    != (2, source['goal_version'], result.plan_version)
                    or plan.status != ('completed' if result.completed else 'active')
                    or grant.goal_version != source['goal_version']
                    or result.completed and (grant.status != 'revoked' or grant.stop_reason != 'completed' or grant.revoked_at is None)
                    or not result.completed and (grant.status != 'active' or grant.revoked_at is not None)):
                _conflict()
            threads[source['session_id']] = thread
        handles, touched = [], set()
        for entry in sorted(entries, key=lambda value: value['trigger_key']):
            source, result = entry['source'], by_plan[entry['source']['plan_id']]
            if not result.ready or result.completed:
                continue
            old = _existing_followup(db, entry)
            if old is not None:
                handles.append(_handle(old))
                continue
            now = _time(clock())
            if entry['occupied'] or _followup_occupied(db, source, now):
                continue
            thread = threads[source['session_id']]
            if source['session_id'] not in touched:
                _version_cas(db, thread, {'updated_at': now})
                touched.add(source['session_id'])
            run = Run(id=str(uuid4()), owner_id=source['owner_id'], store_id=source['store_id'],
                session_id=source['session_id'], plan_id=source['plan_id'], goal_version=source['goal_version'],
                trigger_kind='signal', trigger_key=entry['trigger_key'], request_id=None,
                request_digest=entry['digest'], entry_context=None, auth_kind='grant',
                login_session_ref=None, grant_id=source['grant_id'], status='queued', next_run_at=now, priority=0)
            db.add(run)
            _state_event(db, run, None, clock=clock)
            handles.append(_handle(run))
    state['transaction_ref'] = ref(db.get_transaction())
    validate_followup_resolution(db, resolved, clock=clock)
    return tuple(handles)


def enqueue_manual_run(db, request, user, plan_id, request_key, *, clock=utcnow, read_session_factory=None):
    """An explicit employee continue action creates no fabricated user message."""
    _clean(db)
    plan_id = _uuid(plan_id)
    try:
        request_key = TypeAdapter(MessageRequestId).validate_python(request_key)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '请提供本次继续操作的原请求编号') from None
    with _reader(db, read_session_factory) as reader:
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
            AssistantWorkPlan.owner_id == user.id, AssistantWorkPlan.store_id == getattr(user, '_active_store_id', None)))
        session_id = plan.session_id if plan is not None else None
    if session_id is None:
        raise HTTPException(404, '事项不存在或不可访问')
    principal = _original_login(db, request, user, session_id, clock=clock, read_session_factory=read_session_factory)
    with _reader(db, read_session_factory) as reader:
        thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == session_id))
        plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
            AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id,
            AssistantWorkPlan.session_id == session_id))
        if plan is None or plan.engine_version != 2 or plan.status != 'active':
            _conflict('请先恢复当前事项，再明确继续')
        source = {**_principal_source(principal), 'plan_id': plan_id, 'goal_version': plan.goal_version,
            'session_version': thread.version, 'plan_version': plan.version, 'auth_kind': 'login',
            'login_session_ref': principal._login_ref, 'grant_id': None}
    payload = {'schema_version': 1, 'trigger_kind': 'manual', 'plan_id': plan_id,
        'goal_version': source['goal_version'], 'request_key': request_key}

    def check():
        revalidate_principal(db, principal, clock=clock)
        with _reader(db, read_session_factory) as reader:
            current = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
                AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id))
            if current is None or current.status != 'active' or current.goal_version != source['goal_version']:
                _conflict('事项范围已变化')

    return _enqueue_internal(db, source, trigger_kind='manual', trigger_key=f'manual:{plan_id}:{request_key}',
        digest=_digest(payload), check=check, clock=clock, factory=read_session_factory)


def lock_for_write(db, principal, *, clock=utcnow, control=False):
    """Server checkpoint primitive, no commit: call after reads, before artifacts.

    control=True only authorizes stopping this Run and minimal cancellation
    events. It is never authority to prepare cards or advance Step/Plan progress.
    Caller must rollback on any later failure; no native/model wait in this TX.
    After adding/flushing artifacts, call revalidate_principal (or the control
    guard for cancellation only) again immediately before committing.
    """
    _clean(db)
    if type(control) is not bool:
        raise TypeError('Control authorization is a server-only boolean')
    guard = revalidate_control_principal if control else revalidate_principal
    guard(db, principal, clock=clock)
    if not principal.run_id:
        _conflict('写回必须属于已领取的真实执行')
    _scope(db, principal.store_id)
    _sqlite_writer(db)
    with db.no_autoflush:
        thread, plan, run = _lock_rows(db, _principal_source(principal))
        now = _time(clock())
        _leased(run, principal, now, control=control)
        if (thread.busy_token != runtime_busy_token(run.id) or thread.busy_until is None
                or _time(thread.busy_until) <= now):
            _conflict('本执行已不再持有会话忙租约')
        _version_cas(db, run, {})
        db.info['assistant_preparation_transaction'] = db.get_transaction()
    guard(db, principal, clock=clock)
    from .assistant_runtime_events import _bind_fenced_transaction
    _bind_fenced_transaction(db, principal, control=control, clock=clock)
    return thread, plan, run


_BUDGET_KEY = 'runtime_v1'
_TOKEN_KEYS = ('prompt_tokens', 'completion_tokens', 'total_tokens',
               'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'reasoning_tokens')


def _limits(max_rounds, turn_timeout_seconds, call_budget, max_preparations):
    if (type(max_rounds) is not int or not 4 <= max_rounds <= 40
            or type(turn_timeout_seconds) is not int or not 30 <= turn_timeout_seconds <= 600
            or type(call_budget) is not int or call_budget != max(200, max_rounds * 200)
            or max_preparations is not None and (type(max_preparations) is not int or max_preparations < 0)):
        raise ValueError('Runtime budgets must retain the original server limits')
    return {'max_rounds': max_rounds, 'turn_timeout_seconds': turn_timeout_seconds,
            'call_budget': call_budget, 'max_preparations': max_preparations}


def _provider_usage(value, *, background):
    """Copy only finite provider counters, never response/reasoning/content."""
    if value is None:
        return None
    counters = ('http_requests', 'retries', 'elapsed_ms', 'tool_count')
    if (type(value) is not dict or set(value) != {*counters, 'background', 'token_usage_status', 'tokens'}
            or any(type(value[key]) is not int or value[key] < 0 for key in counters)
            or type(value['background']) is not bool or value['background'] != background
            or value['retries'] != max(0, value['http_requests'] - 1) or value['tool_count'] > 200
            or type(value['tokens']) is not dict or set(value['tokens']) != set(_TOKEN_KEYS)
            or any(count is not None and (type(count) is not int or count < 0)
                   for count in value['tokens'].values())):
        raise ValueError('Expected safe provider usage counters')
    tokens = value['tokens']
    status = ('known' if all(tokens[key] is not None for key in _TOKEN_KEYS[:3])
              else 'partial' if any(count is not None for count in tokens.values()) else 'unknown')
    if value['token_usage_status'] != status:
        raise ValueError('Provider usage status differs from its counters')
    return deepcopy(value)


def _ledger(run):
    """Validate the fixed server ledger; never infer yields from error text."""
    if type(run.usage) is not dict:
        _conflict('Runtime usage ledger is invalid')
    value = deepcopy(run.usage.get(_BUDGET_KEY))
    if value is None:
        return {'schema_version': 1, 'limits': None, 'rounds': [], 'corrected': False,
                'truncation_replanned': False, 'prepared_count': 0, 'yield_count': 0}
    try:
        if (type(value) is not dict or set(value) != {'schema_version', 'limits', 'rounds',
                'corrected', 'truncation_replanned', 'prepared_count', 'yield_count'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or any(type(value[key]) is not bool for key in ('corrected', 'truncation_replanned'))
                or any(type(value[key]) is not int or value[key] < 0 for key in ('prepared_count', 'yield_count'))
                or value['yield_count'] > run.attempt or type(value['rounds']) is not list
                or len(value['rounds']) > 40):
            raise ValueError('Invalid durable ledger')
        if value['limits'] is not None:
            limits = value['limits']
            if type(limits) is not dict or _limits(**limits) != limits:
                raise ValueError('Invalid durable limits')
            if len(value['rounds']) > limits['max_rounds']:
                raise ValueError('Invalid reservation count')
        elif value['rounds'] or value['corrected'] or value['truncation_replanned']:
            raise ValueError('Budget must precede model use')
        for number, row in enumerate(value['rounds'], 1):
            if (type(row) is not dict or set(row) != {'round_no', 'fence', 'started_at', 'finished', 'usage'}
                    or type(row['round_no']) is not int or row['round_no'] != number
                    or type(row['fence']) is not int or not 1 <= row['fence'] <= run.fence
                    or type(row['finished']) is not bool or type(row['started_at']) is not str
                    or not row['finished'] and row['usage'] is not None):
                raise ValueError('Invalid round reservation')
            _time(datetime.fromisoformat(row['started_at']))
            _provider_usage(row['usage'], background=run.auth_kind == 'grant')
    except (TypeError, ValueError, KeyError, OverflowError):
        _conflict('Runtime usage ledger is invalid')
    return value


def _budget_view(run, ledger, now):
    limits = ledger['limits']
    if limits is None or run.started_at is None:
        _conflict('Runtime budget has not been configured')
    elapsed = max(0.0, (now - _time(run.started_at)).total_seconds())
    remaining = max(0.0, limits['turn_timeout_seconds'] - elapsed)
    count = sum(row['usage']['tool_count'] for row in ledger['rounds'] if row['usage'] is not None)
    reason = ('time_budget' if remaining <= 0 else 'model_round_budget'
              if len(ledger['rounds']) >= limits['max_rounds'] else 'tool_budget'
              if count >= limits['call_budget'] else None)
    return BudgetSnapshot(len(ledger['rounds']), remaining, count, ledger['corrected'],
                          ledger['truncation_replanned'], ledger['prepared_count'], reason)


def _save_ledger(db, run, ledger):
    # The ledger keeps unknown/crashed reservations. Summary counters distinguish
    # known lower bounds from an exact total, rather than calling missing usage 0.
    rows = ledger['rounds']
    reported = [row['usage'] for row in rows if row['usage'] is not None]
    complete = bool(rows) and len(reported) == len(rows)
    tokens = {key: sum(value['tokens'][key] for value in reported)
              if complete and all(value['tokens'][key] is not None for value in reported) else None
              for key in _TOKEN_KEYS}
    status = ('known' if all(tokens[key] is not None for key in _TOKEN_KEYS[:3])
              else 'partial' if any(value is not None for value in tokens.values()) else 'unknown')
    summary = {'reserved_rounds': len(rows), 'unreported_rounds': len(rows) - len(reported),
               'background': run.auth_kind == 'grant', 'tokens': tokens, 'token_usage_status': status}
    for key in ('http_requests', 'retries', 'elapsed_ms'):
        observed = sum(value[key] for value in reported)
        summary[key] = observed if complete else None
        summary['observed_' + key] = observed
    summary['tool_count'] = sum(value['tool_count'] for value in reported)
    _version_cas(db, run, {'usage': {**deepcopy(run.usage), _BUDGET_KEY: ledger, 'summary': summary}})


def _budget_transaction(db, principal, mutate, *, clock):
    try:
        _, _, run = lock_for_write(db, principal, clock=clock)
        ledger = _ledger(run)
        result, changed = mutate(run, ledger, _time(clock()))
        if changed:
            _save_ledger(db, run, ledger)
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
        return result
    except Exception as exc:
        _failure(db, exc)


def configure_budget(db, principal, *, max_rounds, turn_timeout_seconds, call_budget,
                     max_preparations=None, clock=None):
    """Freeze original server limits once, before recovery or any model request."""
    limits = _limits(max_rounds, turn_timeout_seconds, call_budget, max_preparations)

    def configure(run, ledger, now):
        if ledger['limits'] is not None and ledger['limits'] != limits:
            _conflict('The persisted Run budget cannot be replaced')
        changed = ledger['limits'] is None
        ledger['limits'] = limits
        return _budget_view(run, ledger, now), changed

    return _budget_transaction(db, principal, configure, clock=clock or principal._clock)


def reserve_model_round(db, principal, *, max_rounds, turn_timeout_seconds, call_budget,
                        max_preparations=None, clock=None):
    """Commit a round before external I/O; crashes never refund reservations."""
    limits = _limits(max_rounds, turn_timeout_seconds, call_budget, max_preparations)

    def reserve(run, ledger, now):
        if ledger['limits'] is not None and ledger['limits'] != limits:
            _conflict('The persisted Run budget cannot be replaced')
        configured = ledger['limits'] is None
        ledger['limits'] = limits
        view = _budget_view(run, ledger, now)
        if view.exhausted_reason:
            return view, configured
        ledger['rounds'].append({'round_no': view.round_no + 1, 'fence': run.fence, 'started_at': now.isoformat(),
                                 'finished': False, 'usage': None})
        # This reservation is permitted even when it consumes the last round;
        # exhausted_reason describes a denied reservation, not the next one.
        return BudgetSnapshot(view.round_no + 1, view.remaining_seconds, view.tool_count,
            view.corrected, view.truncation_replanned, view.prepared_count, None), True

    return _budget_transaction(db, principal, reserve, clock=clock or principal._clock)


def budget_snapshot(db, principal, *, clock=None):
    """Fresh committed counters; safe for every actual provider-request guard."""
    clock = clock or principal._clock
    _clean(db)
    revalidate_principal(db, principal, clock=clock)
    with _reader(db, principal._read_session_factory) as reader:
        run = reader.scalar(select(Run).where(Run.id == principal.run_id))
        if run is None:
            _conflict()
        now = _time(clock())
        _leased(run, principal, now)
        result = _budget_view(run, _ledger(run), now)
    revalidate_principal(db, principal, clock=clock)
    return result


def finish_model_round(db, principal, round_no, usage, *, clock=None):
    """Idempotently store safe usage before accepting its complete tool frame."""
    value = _provider_usage(usage, background=principal.auth_kind == 'grant')
    if type(round_no) is not int or round_no < 1:
        raise ValueError('Expected an actual reserved model round')

    def finish(run, ledger, now):
        if round_no > len(ledger['rounds']):
            _conflict('Model round was not reserved')
        row = ledger['rounds'][round_no - 1]
        changed = not row['finished']
        if changed and row['fence'] != run.fence:
            _conflict('An earlier lease cannot supply a new model receipt')
        if row['finished'] and row['usage'] != value:
            _conflict('Model round usage cannot be replaced')
        row['finished'], row['usage'] = True, value
        return _budget_view(run, ledger, now), changed

    return _budget_transaction(db, principal, finish, clock=clock or principal._clock)


def mark_loop_flag(db, principal, flag, *, clock=None):
    """Persist the one correction/replan allowance before its model request."""
    name = {'correction': 'corrected', 'truncation': 'truncation_replanned'}.get(flag)
    if name is None:
        raise ValueError('Only the original two loop allowances are supported')

    def mark(run, ledger, now):
        _budget_view(run, ledger, now)
        changed = not ledger[name]
        ledger[name] = True
        return changed, changed

    return _budget_transaction(db, principal, mark, clock=clock or principal._clock)


def add_preparation_usage(db, principal, count, *, clock=None):
    """No commit: caller supplies only cards just created in this fenced TX.

    Call once with len(new_cards), after their real inserts, in the same atomic
    checkpoint. Reused cards, pending input rows and failed prepares count zero.
    """
    from .assistant_runtime_events import _capability
    if type(count) is not int or count < 0:
        raise ValueError('Preparation count must be a nonnegative integer')
    clock = clock or principal._clock
    run = _capability(db, principal, clock=clock)
    ledger = _ledger(run)
    # The pre-existing checkpoint/execute_tools API also records real cards
    # without a model loop. Keep that contract and carry its count into the
    # later configure_budget call instead of requiring a model configuration.
    maximum = ledger['limits']['max_preparations'] if ledger['limits'] else None
    if maximum is not None and ledger['prepared_count'] + count > maximum:
        _conflict('Runtime preparation budget would be exceeded')
    if count:
        ledger['prepared_count'] += count
        _save_ledger(db, run, ledger)
    return ledger['prepared_count']


def _fault_attempt(run):
    # Claims remain monotonic. Only an actual same-TX cooperative yield earns
    # this offset; transient failures retain the original finite retry budget.
    attempt = run.attempt - _ledger(run)['yield_count']
    if not 1 <= attempt <= run.attempt:
        _conflict('Runtime claim and yield counters disagree')
    return attempt


def _skip_pending(db, run, now):
    for item in db.scalars(select(RunItem).where(RunItem.run_id == run.id,
            RunItem.status == 'pending', RunItem.kind != 'confirmation')
            .execution_options(populate_existing=True)):
        item.status, item.finished_at, item.error_code = 'skipped', now, 'precondition_conflict'


def _retry_model_frame(db, run, items, model_id):
    """Read a complete persisted model/tool frame, without issuing a principal."""
    from .assistant_runtime_registry import _registry_for_profile
    from .assistant_runtime_runner import _model_calls, _tool_data, _manifest_data, _call_rows
    model = next((item for item in items if item.id == model_id), None)
    if model is None or model.run_id != run.id or model.finished_at is None:
        raise ValueError('Missing complete model origin')
    calls = _model_calls(model, _registry_for_profile('business_v1'))
    model_key = model.validated_arguments['model_key']
    if (type(model_key) is not str or not model_key or len(model_key) > 100
            or model.item_key != 'model:' + _digest({'run': run.id, 'key': model_key})
            or model.attempt_no != 1):
        raise ValueError('Invalid model origin key')
    by_call = {call.id: call for call in calls}
    groups, data = {}, {}
    for item in items:
        raw = item.validated_arguments
        if (item.kind not in {'tool', 'batch_row'} or item.tool_name == 'prepare_inputs'
                or type(raw) is not dict or raw.get('model_item_id') != model.id):
            continue
        value = _tool_data(item)
        call = by_call.get(value['call_id'])
        if (call is None or value['name'] != call.name or value['arguments'] != call.arguments
                or type(item.attempt_no) is not int or item.attempt_no < 1):
            raise ValueError('Invalid complete tool origin')
        key = 'call:' + _digest({'model': model_key, 'call': call.id})
        if item.kind == 'batch_row':
            if call.name not in {'prepare_operations', 'prepare_business_batch'}:
                raise ValueError('Unexpected batch row')
            key = 'row:' + _digest({'tool': key, 'input': value['input_item_id']})
        elif value['input_item_id'] is not None:
            raise ValueError('Parent contains a row identity')
        if item.item_key != key:
            raise ValueError('Invalid stable tool key')
        groups.setdefault(key, []).append(item)
        data[item.id] = value
    latest = []
    for group in groups.values():
        group.sort(key=lambda item: item.attempt_no)
        if ([item.attempt_no for item in group] != list(range(1, len(group) + 1))
                or any(item.kind != group[0].kind or data[item.id] != data[group[0].id] for item in group)):
            raise ValueError('Incomplete or changed attempt chain')
        latest.append(group[-1])
    parents = [item for item in latest if item.kind == 'tool']
    if len(parents) != len(calls) or {data[item.id]['call_id'] for item in parents} != set(by_call):
        raise ValueError('Incomplete model call set')
    for parent in parents:
        value = data[parent.id]
        call = by_call[value['call_id']]
        children = [item for item in latest if item.kind == 'batch_row'
                    and data[item.id]['call_id'] == call.id]
        if call.kind != 'prepare':
            if value['manifest_id'] is not None or value['step_id'] is not None or children:
                raise ValueError('Unexpected read/plan preparation origin')
            continue
        manifest = db.scalar(select(RunItem).where(RunItem.id == _uuid(value['manifest_id']))
                             .execution_options(populate_existing=True))
        if manifest is None:
            raise ValueError('Missing full input manifest')
        manifest_data = _manifest_data(manifest)
        if (manifest_data['scope']['step_id'] != value['step_id']
                or manifest_data['input_digest'] != _digest(_call_rows(call.name, call.arguments))):
            raise ValueError('Manifest differs from complete tool input')
        if call.name in {'prepare_operations', 'prepare_business_batch'}:
            row_ids = [data[item.id]['input_item_id'] for item in children]
            if len(row_ids) != len(manifest_data['rows']) or set(row_ids) != {row['input_item_id'] for row in manifest_data['rows']}:
                raise ValueError('Incomplete stable batch row set')
        elif children or len(manifest_data['rows']) != 1:
            raise ValueError('Invalid single preparation row set')
        for child in children:
            if any(data[child.id][key] != value[key] for key in
                   ('arguments', 'manifest_id', 'step_id', 'name', 'model_item_id')):
                raise ValueError('Batch row differs from its parent')
    return {'parents': parents, 'groups': groups, 'data': data}


def _completed_unbound_history(db, run, items):
    """Prove only completed Runtime work predating this Run's own new Plan.

    The original retry guards still inspect every returned work/card. This
    helper performs no writes, native reads, receipts or live-lease checks.
    Old M2 reprepare/carry histories have no complete Runtime origin here and
    fail closed; the ordinary same-Plan retry path remains unchanged.
    """
    from .assistant_runtime_runner import _manifest_data, _tool_data, _work_key, _intent_digest, _read_intent
    empty = (set(), set())
    if run.plan_id is None:
        return empty
    try:
        manifests, work_ids = {}, {item.work_item_id for item in items if item.work_item_id}
        for item in items:
            if item.tool_name != 'prepare_inputs':
                continue
            value = _manifest_data(item)
            if value['scope']['plan_id'] is None:
                manifests[item.id] = (item, value)
            work_ids.update(_uuid(row['work_item_id']) for row in value['rows'] if row.get('work_item_id'))
        works = list(db.scalars(select(WorkItem).where(WorkItem.id.in_(work_ids))
                               .execution_options(populate_existing=True)))
        if len(works) != len(work_ids):
            return None
        historical = {work.id: work for work in works if work.plan_id is None}
        if not manifests and not historical:
            return empty
        thread = db.scalar(select(AssistantSession).where(AssistantSession.id == run.session_id,
            AssistantSession.owner_id == run.owner_id, AssistantSession.store_id == run.store_id)
            .execution_options(populate_existing=True))
        plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == run.plan_id,
            AssistantWorkPlan.owner_id == run.owner_id, AssistantWorkPlan.store_id == run.store_id,
            AssistantWorkPlan.session_id == run.session_id).execution_options(populate_existing=True))
        if (thread is None or plan is None or run.auth_kind != 'login' or plan.engine_version != 2
                or plan.status != 'active' or plan.goal_version != run.goal_version
                or plan.request_id != runtime_busy_token(run.id)):
            return None
        frames, proven_works = {}, set()

        def frame_for(item):
            value = _tool_data(item)
            model_id = _uuid(value['model_item_id'])
            if model_id not in frames:
                frames[model_id] = _retry_model_frame(db, run, items, model_id)
            return frames[model_id]

        for manifest_id, (manifest, value) in manifests.items():
            scope = value['scope']
            if (manifest.run_id != run.id or manifest.status != 'succeeded' or manifest.finished_at is None
                    or (scope['owner_id'], scope['store_id'], scope['session_id'], scope['role'], scope['access_version'])
                    != (run.owner_id, run.store_id, run.session_id, thread.owner_role, thread.access_version)
                    or any(scope[key] is not None for key in ('plan_id', 'step_id', 'step_key', 'goal_version'))
                    or any(type(scope[key]) is not int for key in ('owner_id', 'store_id', 'access_version', 'intent_version'))
                    or scope['intent_version'] != 1 or scope['origin_request_id'] != (run.request_id or 'run:' + run.id)
                    or value.get('previous_manifest_id') is not None
                    or value.get('previous_compatibility_proposal_id') is not None
                    or value.get('selected_input_item_ids') != []):
                return None
            linked = [item for item in items if item.kind == 'tool' and item.tool_name != 'prepare_inputs'
                      and type(item.validated_arguments) is dict
                      and item.validated_arguments.get('manifest_id') == manifest_id]
            if not linked:
                return None
            frame = frame_for(linked[0])
            parents = [item for item in frame['parents'] if frame['data'][item.id]['manifest_id'] == manifest_id]
            if len(parents) != 1 or parents[0].item_key != scope['tool_key']:
                return None
            parent = parents[0]
            if any(item.item_key != parent.item_key for item in linked):
                return None
            effective = [group[-1] for group in frame['groups'].values()
                         if frame['data'][group[-1].id]['manifest_id'] == manifest_id]
            if any(item.status != 'succeeded' or item.finished_at is None or item.error_code is not None for item in effective):
                return None
            children = {frame['data'][item.id]['input_item_id']: item for item in effective if item.kind == 'batch_row'}
            if children and (parent.work_item_id is not None or parent.proposal_id is not None):
                return None
            for row in value['rows']:
                work_id, card_id = _uuid(row.get('work_item_id')), _uuid(row.get('proposal_id'))
                work = historical.get(work_id)
                if (row['outcome'] not in {'prepared', 'settled'} or row.get('carry_forward') is not None
                        or row.get('supersedes_id') is not None or work is None or work.item_kind != 'prepare'
                        or work.step_id is not None or work.intent_version != 1 or work.supersedes_id is not None
                        or work.status not in {'prepared', 'settled'}
                        or (work.owner_id, work.store_id, work.session_id) != (run.owner_id, run.store_id, run.session_id)
                        or work.origin_request_id != scope['origin_request_id'] or work.input_item_id != row['input_item_id']
                        or work.intent_key != _work_key(scope, row['input_item_id'])):
                    return None
                intent = deepcopy(work.validated_intent)
                if type(intent) is not dict or set(intent) != {'schema_version', 'operation_id', 'path_args', 'query',
                        'body', 'questions', 'question_fields', 'generate_request_id', 'intent_digest'}:
                    return None
                digest = intent.pop('intent_digest')
                if (intent['schema_version'] != 1 or intent['operation_id'] != work.operation_id
                        or type(intent['generate_request_id']) is not bool
                        or any(type(intent[key]) is not dict for key in ('path_args', 'query', 'body'))
                        or type(intent['questions']) is not list
                        or intent['question_fields'] is not None and type(intent['question_fields']) is not list
                        or intent['generate_request_id'] and 'request_id' in intent['body']
                        or digest != _intent_digest(intent)):
                    return None
                card = db.scalar(select(AssistantProposal).where(AssistantProposal.id == card_id)
                                 .execution_options(populate_existing=True))
                if (card is None or card.source_work_item_id != work.id or card.operation_id != work.operation_id
                        or (card.owner_id, card.store_id, card.session_id, card.owner_role, card.access_version)
                        != (run.owner_id, run.store_id, run.session_id, thread.owner_role, thread.access_version)):
                    return None
                attempt = children.get(row['input_item_id']) if children else parent
                if attempt is None or (attempt.work_item_id, attempt.proposal_id) != (work.id, card.id):
                    return None
                proven_works.add(work.id)
        for work in historical.values():
            if work.id in proven_works:
                continue
            if (work.item_kind != 'read' or work.status != 'settled' or work.step_id is not None
                    or work.intent_version != 1 or work.supersedes_id is not None
                    or (work.owner_id, work.store_id, work.session_id) != (run.owner_id, run.store_id, run.session_id)
                    or work.origin_request_id != (run.request_id or 'run:' + run.id)):
                return None
            associated = list(db.scalars(select(RunItem).where(RunItem.work_item_id == work.id)
                .execution_options(populate_existing=True)))
            if not associated or any(item.run_id != run.id or item.kind != 'tool'
                    or item.tool_name != 'read_data' or item.proposal_id is not None
                    or type(item.attempt_no) is not int or item.attempt_no < 1 for item in associated):
                return None
            latest = max(associated, key=lambda item: item.attempt_no)
            if (latest.status != 'succeeded' or latest.finished_at is None or latest.error_code is not None
                    or any(item.item_key != latest.item_key for item in associated)):
                return None
            frame = frame_for(latest)
            group = frame['groups'].get(latest.item_key)
            if (not group or group[-1].id != latest.id
                    or {item.id for item in associated} != {item.id for item in group if item.work_item_id == work.id}):
                return None
            data = frame['data'][latest.id]
            if (any(data[key] is not None for key in ('manifest_id', 'input_item_id', 'step_id'))
                    or work.intent_key != 'read:' + _digest({'run_id': run.id, 'item_key': latest.item_key})):
                return None
            _uuid(work.input_item_id)
            intent = deepcopy(work.validated_intent)
            if (type(intent) is not dict or set(intent) != {'operation_id', 'path_args', 'query', 'body'}
                    or intent['body'] not in (None, {}) or type(intent['path_args']) is not dict
                    or type(intent['query']) is not dict or intent['operation_id'] != work.operation_id):
                return None
            intent['body'] = None
            if (data['arguments'].get('body') not in (None, {})
                    or intent != _read_intent('read_data', data['arguments'])):
                return None
            for earlier in group[:-1]:
                if (earlier.status != 'failed' or earlier.finished_at is None or earlier.proposal_id is not None
                        or earlier.work_item_id not in {None, work.id}):
                    return None
            proven_works.add(work.id)
        if proven_works != set(historical):
            return None
        return set(manifests), proven_works
    except (HTTPException, ValidationError, ValueError, TypeError, KeyError, AttributeError,
            RecursionError, OverflowError):
        # Database/connection errors deliberately propagate and roll back the
        # queue transaction; they are not proof of permanent unsafe work.
        return None


def _safe_retry(db, run, now):
    """Classify persisted work; this does not reset/replay any individual item."""
    items = list(db.scalars(select(RunItem).where(RunItem.run_id == run.id)
        .execution_options(populate_existing=True)))
    if any(item.kind == 'confirmation' or item.status == 'uncertain' for item in items):
        return False
    if type(run.trigger_key) is str and run.trigger_key.startswith('mcp:'):
        from .assistant_runtime_mcp import is_mcp_run, safe_retry
        return is_mcp_run(run) and safe_retry(db, run, items, now)
    from .assistant_runtime_registry import _registry_for_profile
    from .assistant_runtime_runner import _manifest_data
    history = _completed_unbound_history(db, run, items)
    if history is None:
        return False
    historical_manifests, historical_works = history
    work_ids = {item.work_item_id for item in items if item.work_item_id}
    bound_cards = {}
    for item in items:
        if item.tool_name == 'prepare_inputs':
            try:
                manifest = _manifest_data(item)
            except (HTTPException, ValueError, TypeError, KeyError):
                return False
            scope = manifest['scope']
            if ((scope['owner_id'], scope['store_id'], scope['session_id'], scope['plan_id'], scope['goal_version'])
                    != (run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version)
                    and item.id not in historical_manifests):
                return False
            for row in manifest['rows']:
                if row['outcome'] in {'uncertain', 'failed', 'needs_input', 'cancelled', 'expired'}:
                    return False
                if row.get('work_item_id'):
                    work_ids.add(row['work_item_id'])
                if row.get('proposal_id'):
                    bound_cards[row['proposal_id']] = row.get('work_item_id')
            continue
        if item.status in {'succeeded', 'skipped'} or item.kind == 'model':
            continue
        if item.kind not in {'tool', 'batch_row'} or not isinstance(item.validated_arguments, dict):
            return False
        if item.error_code not in {None, 'runtime_unavailable'}:
            return False
        try:
            if _registry_for_profile('business_v1').spec(item.tool_name).kind not in {'read', 'prepare', 'plan'}:
                return False
        except (HTTPException, TypeError, ValueError):
            return False
    works = list(db.scalars(select(WorkItem).where(WorkItem.id.in_(work_ids)).execution_options(populate_existing=True)))
    if len(works) != len(work_ids):
        return False
    cards = {}
    for work in works:
        if ((work.owner_id, work.store_id, work.session_id) != (run.owner_id, run.store_id, run.session_id)
                or work.plan_id != run.plan_id and work.id not in historical_works or work.status == 'uncertain'
                or db.scalar(select(WorkItem.id).where(WorkItem.supersedes_id == work.id).limit(1))):
            return False
        card = db.scalar(select(AssistantProposal).where(AssistantProposal.source_work_item_id == work.id)
            .execution_options(populate_existing=True))
        if work.item_kind == 'read':
            if (card is not None or work.status not in {'planned', 'settled'}
                    or not work.operation_id.startswith('GET ')):
                return False
        elif work.item_kind == 'prepare':
            if card is None:
                if work.status != 'planned':
                    return False
            elif ((card.owner_id, card.store_id, card.session_id) != (run.owner_id, run.store_id, run.session_id)
                  or card.status not in {'pending', 'succeeded'}
                  or card.status == 'pending' and (card.expires_at is None or _time(card.expires_at) <= now)):
                return False
        else:
            return False
        if card is not None:
            cards[card.id] = card
    if any(key not in cards or cards[key].source_work_item_id != work_id for key, work_id in bound_cards.items()):
        return False
    if db.scalar(select(RunItem.id).where(RunItem.kind == 'confirmation', RunItem.proposal_id.in_(cards),
            RunItem.status.in_({'pending', 'running', 'uncertain'})).limit(1)):
        return False
    return True


def _release_busy(db, thread, run, now):
    # Caller has already won this Run's lease/fence CAS. A different token is
    # never cleared, even if its timestamp looks expired.
    if thread.busy_token == runtime_busy_token(run.id):
        _busy(db, thread, mode='release', token=runtime_busy_token(run.id), now=now)


def _priority_user(db, principal, priority, now):
    """Only observe other sources; never acquire another employee's write scope."""
    with _reader(db, principal._read_session_factory) as reader:
        candidates = reader.scalars(select(Run).join(AssistantSession,
            AssistantSession.id == Run.session_id).where(Run.id != principal.run_id,
            Run.trigger_kind == 'user', Run.auth_kind == 'login', Run.status == 'queued',
            Run.stop_requested.is_(False), Run.next_run_at <= now, Run.priority > priority,
            or_(AssistantSession.busy_token.is_(None), AssistantSession.busy_until.is_(None),
                AssistantSession.busy_until <= now,
                AssistantSession.busy_token == runtime_busy_token(principal.run_id)))
            .order_by(Run.priority.desc(), Run.next_run_at, Run.created_at, Run.id))
        for candidate in candidates:
            # Another expired running owner must first be reclaimed. Ignore our
            # own slot because this transaction is about releasing that slot.
            occupied = reader.scalar(select(Run.id).where(Run.id != principal.run_id,
                Run.status == 'running', or_(Run.session_id == candidate.session_id,
                    and_(candidate.plan_id is not None, Run.plan_id == candidate.plan_id))).limit(1))
            if occupied is not None:
                continue
            try:
                _source(reader, candidate, now)
            except HTTPException as exc:
                if exc.status_code in {401, 403, 409, 503}:
                    continue
                raise
            return candidate.id
    return None


def _tool_boundary(db, run):
    """No active model/tool/confirmation can be abandoned by a priority yield."""
    ledger = _ledger(run)
    if any(not row['finished'] and row['fence'] == run.fence for row in ledger['rounds']):
        return False
    items = list(db.scalars(select(RunItem).where(RunItem.run_id == run.id)
                           .execution_options(populate_existing=True)))
    if any(item.status == 'uncertain' or item.kind == 'confirmation' for item in items):
        return False
    try:
        models = [item for item in items if item.kind == 'model']
        covered, manifests = set(), set()
        for model in models:
            frame = _retry_model_frame(db, run, items, model.id)
            manifests.update(value['manifest_id'] for value in frame['data'].values() if value['manifest_id'])
            for group in frame['groups'].values():
                covered.update(item.id for item in group)
                latest = group[-1]
                if (latest.status not in {'pending', 'succeeded', 'failed', 'skipped'}
                        or latest.status != 'pending' and latest.finished_at is None):
                    return False
        executable = {item.id for item in items if item.kind in {'tool', 'batch_row'}
                      and item.tool_name != 'prepare_inputs'}
        if covered != executable:
            return False
        if manifests != {item.id for item in items if item.tool_name == 'prepare_inputs'}:
            return False
        # Complete manifests may retain pending rows for a later tool. They are
        # not a license to abandon an active parent, checked above.
        if any(item.kind not in {'model', 'tool', 'batch_row'} for item in items):
            return False
        card_ids = {item.proposal_id for item in items if item.proposal_id}
        if db.scalar(select(AssistantProposal.id).where(AssistantProposal.id.in_(card_ids),
                AssistantProposal.status.in_({'executing', 'uncertain'})).limit(1)):
            return False
        if db.scalar(select(RunItem.id).where(RunItem.kind == 'confirmation',
                RunItem.proposal_id.in_(card_ids), RunItem.status.in_({'pending', 'running', 'uncertain'})).limit(1)):
            return False
    except (HTTPException, ValueError, TypeError, KeyError):
        return False
    return True


def yield_to_user(db, principal, *, clock=None):
    """Cooperatively queue a background Run, without cancelling its work.

    The global worker slot is released only after a complete persisted tool
    boundary. Higher-priority employee work may belong to another session or
    store. Its content and credentials never enter the background Run.
    """
    clock = clock or principal._clock
    _clean(db)
    revalidate_principal(db, principal, clock=clock)
    if principal.auth_kind != 'grant':
        return None
    _scope(db, principal.store_id)
    try:
        with db.no_autoflush:
            thread, _, run = _lock_rows(db, _principal_source(principal))
            now = _time(clock())
            _leased(run, principal, now)
            if (thread.busy_token != runtime_busy_token(run.id) or thread.busy_until is None
                    or _time(thread.busy_until) <= now):
                _conflict('This Run no longer owns the session busy lease')
            candidate = _priority_user(db, principal, run.priority, now)
            if candidate is None or not _tool_boundary(db, run):
                db.rollback()
                return None
            ledger = _ledger(run)
            _fault_attempt(run)
            ledger['yield_count'] += 1
            _save_ledger(db, run, ledger)
            _version_cas(db, run, {'status': 'queued', 'next_run_at': now,
                'lease_owner': None, 'lease_until': None, 'finished_at': None,
                'stop_requested': False, 'error_code': None})
            _release_busy(db, thread, run, now)
            _state_event(db, run, 'running', clock=clock)
        if _priority_user(db, principal, run.priority, _time(clock())) is None:
            db.rollback()
            return None
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    return _handle(run)


def release(db, principal, *, outcome='succeeded', error_code=None, clock=utcnow, before_finish=None):
    """End/requeue a safe fragment; no confirmation is submitted or retried.

    before_finish(db, principal, run_id) is a synchronous server-only appender
    for an already constructed safe assistant reply and final display snapshot.
    The queue appends the lifecycle event afterwards. The appender may neither
    commit nor perform network/model/native operations.
    A retry request may provide it, but only a classified final failed target
    invokes it. Queued retry and control cancellation never append a final reply.
    """
    _clean(db)
    if outcome not in {'succeeded', 'failed', 'retry', 'cancelled'} or error_code is not None and error_code not in _ERRORS:
        raise HTTPException(422, '执行收尾参数不正确')
    if before_finish is not None and (not callable(before_finish) or outcome not in {'succeeded', 'failed', 'retry'}):
        raise TypeError('Only strict completion/retry accepts a synchronous reply appender')
    control = outcome == 'cancelled'
    guard = revalidate_control_principal if control else revalidate_principal
    guard(db, principal, clock=clock)
    _scope(db, principal.store_id)
    try:
        _sqlite_writer(db)
        with db.no_autoflush:
            thread, _, run = _lock_rows(db, _principal_source(principal))
            now = _time(clock())
            _leased(run, principal, now, control=control)
            if outcome == 'succeeded' and db.scalar(select(RunItem.id).where(
                    RunItem.run_id == run.id, RunItem.status == 'running').limit(1)):
                _conflict('仍有未完整结束的执行项，不能报告执行成功')
            target = outcome
            next_run_at = run.next_run_at
            if outcome == 'retry':
                if error_code != 'runtime_unavailable':
                    _conflict('只有已分类的瞬时读取或准备故障可退避')
                fault_attempt = _fault_attempt(run)
                retry = _safe_retry(db, run, now) and fault_attempt <= len(RETRY_DELAYS)
                target = 'queued' if retry else 'failed'
                if retry:
                    next_run_at = now + timedelta(seconds=RETRY_DELAYS[fault_attempt - 1])
            if target == 'cancelled':
                _skip_pending(db, run, now)
            _version_cas(db, run, {'status': target, 'next_run_at': next_run_at,
                'lease_owner': None, 'lease_until': None, 'finished_at': None if target == 'queued' else now,
                'stop_requested': target == 'cancelled', 'error_code': error_code})
            _release_busy(db, thread, run, now)
            db.info['assistant_preparation_transaction'] = db.get_transaction()
            if before_finish is not None and target in {'succeeded', 'failed'}:
                from inspect import isawaitable, iscoroutine
                from .assistant_runtime_events import _bind_fenced_transaction
                _bind_fenced_transaction(db, principal, control=False, clock=clock)
                result = before_finish(db, principal, run.id)
                if isawaitable(result):
                    if iscoroutine(result):
                        result.close()
                    raise TypeError('Reply appender must complete synchronously without I/O')
            _state_event(db, run, 'running', clock=clock)
        db.flush()
        guard(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    return _handle(run)


def cancel_owned_run(db, principal, *, clock=utcnow):
    return release(db, principal, outcome='cancelled', error_code='precondition_conflict', clock=clock)


def request_cancel(db, request, user, run_id, expected_version, *, clock=utcnow, read_session_factory=None):
    """Employee cancellation: queued ends immediately; running yields safely."""
    _clean(db)
    run_id = _uuid(run_id)
    if type(expected_version) is not int or expected_version < 1:
        raise HTTPException(422, '请提供当前执行版本')
    with _reader(db, read_session_factory) as reader:
        row = reader.scalar(select(Run).where(Run.id == run_id, Run.owner_id == user.id,
            Run.store_id == getattr(user, '_active_store_id', None)))
        session_id = row.session_id if row else None
    if session_id is None:
        raise HTTPException(404, '执行不存在或不可访问')
    principal = _original_login(db, request, user, session_id, clock=clock, read_session_factory=read_session_factory)
    with _reader(db, read_session_factory) as reader:
        row = reader.scalar(select(Run).where(Run.id == run_id))
        source = {**_principal_source(principal), 'run_id': run_id, 'plan_id': row.plan_id}
    _scope(db, principal.store_id)
    try:
        with db.no_autoflush:
            thread, _, run = _lock_rows(db, source)
            if run.version != expected_version:
                _conflict()
            if run.status in {'succeeded', 'failed', 'cancelled'}:
                revalidate_principal(db, principal, clock=clock)
                result = _handle(run)
                db.rollback()
                return result
            now = _time(clock())
            _version_cas(db, thread, {'updated_at': now})
            values = {'stop_requested': True}
            if run.status == 'queued':
                values.update(status='cancelled', finished_at=now, lease_owner=None, lease_until=None)
                _skip_pending(db, run, now)
            _version_cas(db, run, values)
            # Only a queued/released Run can be cleared here. A running worker
            # retains its token until its own valid fenced control boundary.
            if run.status == 'cancelled':
                _release_busy(db, thread, run, now)
                _state_event(db, run, 'queued', clock=clock)
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    revalidate_principal(db, principal, clock=clock)
    return _handle(run)


def bind_run_plan(db, principal, plan_id, *, expected_plan_version, clock=utcnow):
    """Bind only a Plan actually saved under this Run's stable busy token.

    A new principal is issued after commit. The original request_digest remains
    immutable, including an originally null plan_id in the accepted input.
    """
    _clean(db)
    plan_id = _uuid(plan_id)
    if type(expected_plan_version) is not int or expected_plan_version < 1:
        raise HTTPException(422, '请提供新事项的实际版本')
    revalidate_principal(db, principal, clock=clock)
    if principal.auth_kind != 'login' or not principal.run_id or principal.plan_id not in {None, plan_id}:
        _conflict('不能把已有授权执行改绑到另一事项')
    _scope(db, principal.store_id)
    source = {**_principal_source(principal), 'plan_id': plan_id}
    try:
        with db.no_autoflush:
            thread, plan, run = _lock_rows(db, source)
            now = _time(clock())
            _leased(run, principal, now)
            if (plan.engine_version != 2 or plan.status != 'active' or plan.version != expected_plan_version
                    or plan.request_id != runtime_busy_token(run.id)
                    or thread.busy_token != runtime_busy_token(run.id)
                    or thread.busy_until is None or _time(thread.busy_until) <= now):
                _conflict('事项必须由本次执行真实建立，不能按模型编号重绑')
            if run.plan_id is None:
                _version_cas(db, thread, {'updated_at': now})
                _version_cas(db, run, {'plan_id': plan.id, 'goal_version': plan.goal_version})
            elif run.plan_id != plan.id or run.goal_version != plan.goal_version:
                _conflict()
        revalidate_principal(db, principal, clock=clock)
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    return principal_for_run(db, principal.run_id, lease_owner=principal.lease_owner, fence=principal.fence,
        clock=clock, read_session_factory=principal._read_session_factory)


def reclaim_expired(db, *, clock=utcnow, read_session_factory=None):
    """Recover at most one expired claim in a fresh Session, by recorded facts.

    Call before claim_next in the worker's maintenance loop, using a separate
    fresh Session for each call. Safe reads/preparations requeue with backoff;
    confirmations or unknown/cancelled/failed preparation histories never replay.
    This server maintenance path cannot renew an expired lease or mint authority.
    """
    _enabled()
    _fresh_worker_session(db)
    with _reader(db, read_session_factory) as reader:
        now = _time(clock())
        run_id = reader.scalar(select(Run.id).where(Run.status == 'running',
            or_(Run.lease_until.is_(None), Run.lease_until <= now))
            .order_by(Run.lease_until, Run.created_at, Run.id).limit(1))
    if run_id is None:
        return None
    source = _maintenance_snapshot(db, run_id, clock=clock, read_session_factory=read_session_factory)
    _scope(db, source['store_id'])
    try:
        _sqlite_writer(db)
        with db.no_autoflush:
            thread, plan, run = _lock_rows(db, source)
            _source_versions(source, thread, plan, run)
            now = _time(clock())
            if run.status != 'running' or run.lease_until is not None and _time(run.lease_until) > now:
                _conflict('原执行已续租或被其他恢复器处理')
            if run.stop_requested or not source['authorized']:
                target, error = 'cancelled', source['error_code'] or 'precondition_conflict'
            else:
                fault_attempt = _fault_attempt(run)
                target = ('queued' if _safe_retry(db, run, now)
                          and fault_attempt <= len(RETRY_DELAYS) else 'failed')
                error = 'runtime_unavailable'
            next_run_at = (now + timedelta(seconds=RETRY_DELAYS[fault_attempt - 1])
                           if target == 'queued' else run.next_run_at)
            _version_cas(db, thread, {'updated_at': now})
            _version_cas(db, run, {'status': target, 'lease_owner': None, 'lease_until': None,
                'next_run_at': next_run_at, 'finished_at': None if target == 'queued' else now,
                'stop_requested': target == 'cancelled', 'error_code': error})
            if target == 'cancelled':
                _skip_pending(db, run, now)
            _release_busy(db, thread, run, now)
            _state_event(db, run, 'running', clock=clock)
        latest = _maintenance_snapshot(db, run_id, clock=clock, read_session_factory=read_session_factory)
        if (latest['run_version'] != source['run_version'] or latest['status'] != 'running'
                or latest['lease_until'] is not None and _time(latest['lease_until']) > _time(clock())
                or target in {'queued', 'failed'} and (not latest['authorized'] or latest['stop_requested'])
                or target == 'cancelled' and latest['authorized'] and not latest['stop_requested']):
            _conflict('恢复期间执行或授权已变化，请重新读取')
        _commit(db)
    except Exception as exc:
        _failure(db, exc)
    return _handle(run)
