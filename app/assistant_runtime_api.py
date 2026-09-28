"""Employee HTTP views of Runtime records, independent of worker availability.

GETs use the original login and original business GET routes. They never issue a
Runtime capability, reconcile a confirmation, start a model, or upgrade a plan.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
import asyncio
import json
import re
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from . import business_assistant_service as service
from .assistant_runtime_models import Run, RunEvent, RunItem, WorkItem
from .assistant_runtime_principal import _identity, _login, _reader, _time
from .assistant_runtime_schemas import (
    BusinessObjectRef, FollowupAction, NotificationList, NotificationQuery, NotificationView,
    PlanView, ReceiptLookup, RunCancel, RunCreate, RunEventView, RunView, UUIDText,
    WorkspaceQuery, WorkspaceView,
)
from .business_assistant_models import AssistantProposal, AssistantSession, AssistantWorkPlan
from .config import settings
from .db import get_db, utcnow
from .security import get_user
from .tenancy import set_scope, single_store


router = APIRouter(prefix='/api/business-assistant', tags=['业务助手执行'])


@dataclass(frozen=True)
class _LoginRead:
    """Frozen original HTTP identity; not an issued RuntimePrincipal."""
    actor_id: int
    store_id: int
    role: str
    access_version: int
    session_id: str | None
    login_ref: str = field(repr=False)
    bind: object = field(repr=False, compare=False)

    @property
    def id(self):
        return self.actor_id

    @property
    def _active_store_id(self):
        return self.store_id

    @property
    def _aggregate_scope(self):
        return False


def _unavailable():
    raise HTTPException(503, '助手记录暂时不可用，请稍后重新读取')


def _no_query(request):
    # These routes have no query contract, especially no caller-selected
    # actor, table, request ID or operation for receipt lookup.
    if request.query_params:
        raise HTTPException(422, '此接口不接受查询参数')


@contextmanager
def _errors(db):
    try:
        yield
    except (SQLAlchemyError, ValidationError):
        db.rollback()
        _unavailable()


def _capture(db, request, user, session_id=None):
    if '_huakang_runtime' in request.scope:
        raise HTTPException(403, '请由员工本人打开助手记录')
    store = single_store(db)
    if (getattr(user, '_aggregate_scope', False) or db.info.get('aggregate_scope')
            or getattr(user, '_active_store_id', None) != store
            or {value for value in db.info.get('store_scope', ()) if value > 0} != {store}):
        raise HTTPException(409, '请先选择当前门店')
    # Capture before rollback/populate_existing can refresh the ORM account.
    auth = _LoginRead(user.id, store, user.role, user.access_version, session_id,
                      getattr(request.state, 'session_hash', None), db.get_bind())
    service.require_preparation_read_phase(db)
    db.rollback()
    return auth


def _check(reader, auth):
    _login(reader, auth.login_ref, auth.actor_id, _time(utcnow()))
    if auth.session_id is None:
        raise HTTPException(404, '没有找到这段对话')
    # The old owner/role/access snapshot remains a visibility boundary.
    service.owned_session(reader, auth, auth.session_id)
    _identity(reader, auth.actor_id, auth.store_id, auth.role,
              auth.access_version, auth.session_id)


@contextmanager
def _reading(db, auth, *, check=True):
    if db.get_bind() is not auth.bind:
        raise HTTPException(403, '登录来源与当前数据库不一致')
    with _reader(db) as reader:
        set_scope(reader, [auth.store_id], auth.store_id)
        if check:
            _check(reader, auth)
        yield reader


def _guard(db, auth):
    with _reading(db, auth):
        pass


def _owned(reader, auth, model, record_id):
    row = reader.scalar(select(model).join(AssistantSession,
        AssistantSession.id == model.session_id).where(
        model.id == record_id, model.owner_id == auth.actor_id, model.store_id == auth.store_id,
        AssistantSession.owner_id == auth.actor_id, AssistantSession.store_id == auth.store_id,
        AssistantSession.owner_role == auth.role, AssistantSession.access_version == auth.access_version))
    if row is None:
        raise HTTPException(404, '记录不存在或当前不可访问')
    if auth.session_id is not None and row.session_id != auth.session_id:
        raise HTTPException(404, '记录不存在或当前不可访问')
    return row


def _text(value, limit=None):
    from .assistant_runtime_events import _safe_display
    if type(value) is not str:
        _unavailable()
    try:
        value = _safe_display(value, final=True)
    except HTTPException:
        _unavailable()
    return value[:limit] if limit is not None else value


def _native_reader(db, request, original_user, auth):
    from . import business_assistant_gateway as gateway
    from .assistant_runtime_registry import domain_registry, make_native_reader
    providers = domain_registry()
    # The sealed static adapter catalogue supplies this set, never HTTP input.
    allowed = tuple(sorted({operation for spec in providers._specs.values()
                            for operation in spec.operation_ids if operation.startswith('GET ')}))

    async def transport(operation_id, **arguments):
        _guard(db, auth)
        try:
            return await gateway.invoke(request, original_user, operation_id, **arguments)
        finally:
            # Even a rejected native GET cannot expose a revoked login's body.
            _guard(db, auth)

    return make_native_reader(transport, auth, allowed)


async def _visible_object(db, auth, native, ref, *, strict_sources=False):
    from .assistant_runtime_objects import read_object
    try:
        result = await read_object(auth, BusinessObjectRef.model_validate(ref), native_reader=native)
    except HTTPException as exc:
        _guard(db, auth)
        if strict_sources and exc.status_code in {409, 501, 502, 503}:
            raise HTTPException(503, '原业务记录暂时无法核对，请稍后重新读取工作区') from None
        if exc.status_code in {401, 403, 404, 409, 501, 502, 503}:
            return None
        raise
    _guard(db, auth)
    return result


_ERROR_TEXT = {
    'invalid_input': '本次执行需要补充资料', 'not_found': '相关记录当前不可访问',
    'permission_denied': '本次执行的授权已失效', 'version_conflict': '内容版本已变化，请重新核对',
    'request_conflict': '发送编号与原内容不一致', 'precondition_conflict': '执行条件已变化，请重新核对',
    'runtime_unavailable': '本次执行未能完成，请核对已保存的实际结果',
}


def _result_refs(reader, auth, run):
    """Only actual child attempts and their owned confirmation links contribute."""
    direct = list(reader.scalars(select(RunItem).where(RunItem.run_id == run.id)))
    work_ids = {item.work_item_id for item in direct if item.work_item_id}
    confirmations = list(reader.scalars(select(RunItem).where(
        RunItem.kind == 'confirmation', RunItem.work_item_id.in_(work_ids)))) if work_ids else []
    refs = {}
    for item in [*direct, *confirmations]:
        if item.status not in {'succeeded', 'uncertain'}:
            continue
        work = reader.get(WorkItem, item.work_item_id) if item.work_item_id else None
        if item.work_item_id and (work is None or (work.owner_id, work.store_id, work.session_id)
                                  != (auth.actor_id, auth.store_id, auth.session_id)):
            _unavailable()
        if item.proposal_id:
            card = _owned(reader, auth, AssistantProposal, item.proposal_id)
            if ((card.owner_role, card.access_version) != (auth.role, auth.access_version)
                    or card.source_work_item_id != item.work_item_id):
                _unavailable()
        if item.kind == 'confirmation' and (item.run_id is not None or not item.proposal_id or work is None):
            _unavailable()
        if item.result_refs is not None and type(item.result_refs) is not list:
            _unavailable()
        for value in item.result_refs or []:
            ref = BusinessObjectRef.model_validate(value)
            refs[(ref.type, str(ref.id))] = ref
    return tuple(refs[key] for key in sorted(refs))


async def _run_view(db, request, user, auth, run_id):
    with _reading(db, auth, check=False) as reader:
        run = _owned(reader, auth, Run, run_id)
        auth = replace(auth, session_id=run.session_id)
        _check(reader, auth)
        if run.plan_id is not None:
            _owned(reader, auth, AssistantWorkPlan, run.plan_id)
        refs = _result_refs(reader, auth, run)
        code = run.error_code if run.error_code in _ERROR_TEXT else 'runtime_unavailable'
        data = {'id': run.id, 'session_id': run.session_id, 'plan_id': run.plan_id,
            'status': run.status, 'version': run.version, 'last_seq': run.event_seq,
            'display': {'phase': run.status, 'text': _text(run.display_text), 'revision': run.display_revision},
            'result_refs': [], 'error': {'code': code, 'detail': _ERROR_TEXT[code]} if run.error_code else None,
            'allowed_actions': ['cancel'] if settings.assistant_runtime_enabled
                and run.status in {'queued', 'running'} and not run.stop_requested else []}
    native = _native_reader(db, request, user, auth)
    for ref in refs:
        snapshot = await _visible_object(db, auth, native, ref)
        if snapshot is not None:
            data['result_refs'].append(snapshot.ref.model_dump(mode='json'))
    result = RunView.model_validate(data)
    _guard(db, auth)
    return result


def _require_runtime_schema(db):
    inspector = inspect(db.connection())
    if not all(inspector.has_table(name) for name in (
            Run.__tablename__, RunItem.__tablename__, 'business_assistant_run_events')):
        _unavailable()
    db.rollback()


async def accept_run(db, request, user, sid, body: RunCreate) -> RunView:
    """Shared HTTP acceptance; callers retain their own query/wire contract."""
    from . import assistant_runtime_queue as queue
    with _errors(db):
        body = RunCreate.model_validate(body.model_dump(mode='python') if isinstance(body, RunCreate) else body)
        auth = _capture(db, request, user, sid)
        _guard(db, auth)
        if not settings.assistant_runtime_enabled:
            raise HTTPException(503, '助手运行服务尚未开启')
        _require_runtime_schema(db)
        principal = queue._original_login(db, request, auth, sid, clock=utcnow)
        digest = queue._digest({'schema_version': 1, **body.model_dump(mode='json')})
        existing = queue._existing(db, principal, f'user:{sid}:{body.request_id}', digest)
        if existing is None:
            config = service.load_config()
            if not config.enabled or not config.api_key or config.tool_profile != 'business_v1':
                # A concurrent identical send may have committed while model
                # configuration was being read. Recover that accepted Run.
                existing = queue._existing(db, principal, f'user:{sid}:{body.request_id}', digest)
                if existing is None:
                    raise HTTPException(503, '业务助手尚未连接业务工具，请联系管理员配置')
            else:
                existing = await queue.enqueue_run(db, request, auth, sid, body)
        return await _run_view(db, request, user, auth, existing.id)


@router.post('/sessions/{session_id}/runs', status_code=202, response_model=RunView)
async def create_run(session_id: UUIDText, body: RunCreate, request: Request,
                     db=Depends(get_db), user=Depends(get_user)):
    _no_query(request)
    return await accept_run(db, request, user, session_id, body)


@router.get('/runs/{run_id}', response_model=RunView)
async def get_run(run_id: UUIDText, request: Request, db=Depends(get_db), user=Depends(get_user)):
    with _errors(db):
        _no_query(request)
        auth = _capture(db, request, user)
        return await _run_view(db, request, user, auth, run_id)


@router.post('/runs/{run_id}/cancel', response_model=RunView)
async def cancel_run(run_id: UUIDText, body: RunCancel, request: Request,
                     db=Depends(get_db), user=Depends(get_user)):
    from .assistant_runtime_queue import request_cancel
    with _errors(db):
        _no_query(request)
        auth = _capture(db, request, user)
        result = request_cancel(db, request, auth, run_id, body.expected_version)
        return await _run_view(db, request, user, auth, result.id)


def _legacy_view(plan, projection):
    """Keep old derived facts without upgrading JSON or inventing conditions."""
    states = {'step_completed': ('completed', None), 'awaiting_confirmation': ('awaiting_confirmation', None),
        'needs_input': ('needs_input', 'employee_input'), 'failed': ('failed', 'row_failed'),
        'cancelled': ('cancelled', 'cancelled'), 'uncertain': ('uncertain', 'result_unknown'),
        'executing': ('uncertain', 'confirmation_in_progress'), 'expired': ('waiting', 'expired'),
        'unavailable': ('needs_input', 'source_inaccessible'), 'waiting_dependency': ('waiting', 'dependency'),
        'waiting_fact': ('waiting', 'external_fact'), 'following_case': ('waiting', 'external_fact'),
        'needs_preparation': ('waiting', 'preparation_pending'), 'planned': ('waiting', 'not_prepared')}
    steps = []
    for position, step in enumerate(projection['steps']):
        state, reason = states.get(step['status'], ('waiting', 'recheck_required'))
        steps.append({'key': step['key'], 'position': position, 'title': step.get('title') or f'第{position + 1}步',
            'wait_for': step.get('wait_for') or '', 'status': state, 'wait_reason': reason,
            'proposal_id': step.get('proposal_id'),
            'proposal_ids': [step['proposal_id']] if step.get('proposal_id') else [],
            'object_ref': None, 'manual_route': None})
    return {'id': plan.id, 'session_id': plan.session_id, 'version': plan.version,
        'goal_version': plan.goal_version, 'goal': plan.goal, 'status': plan.status, 'steps': steps,
        'grant': {'status': None, 'enabled': False, 'stop_reason': None}, 'allowed_actions': []}


def _followup_actions(actions):
    """Filter original lifecycle actions by the actual service gates only."""
    if not settings.assistant_runtime_enabled:
        return []
    if not settings.assistant_followup_enabled:
        return [action for action in actions if action in {'pause', 'revoke'}]
    return list(actions)


async def shared_plan_view(db, request, user, auth, plan_id, *, strict_sources=False):
    """The same private/native-filtered PlanView for GETs and employee control."""
    from .assistant_runtime_plans import project_legacy_plan, _plan_view, _plan_grants, _current_grant
    with _reading(db, auth, check=False) as reader:
        plan = _owned(reader, auth, AssistantWorkPlan, plan_id)
        auth = replace(auth, session_id=plan.session_id)
        _check(reader, auth)
        projection = project_legacy_plan(reader, auth, auth.session_id, plan)
        if plan.engine_version == 2:
            thread = service.owned_session(reader, auth, auth.session_id)
            data = _plan_view(plan, projection, _current_grant(_plan_grants(reader, thread, plan)))
        else:
            data = _legacy_view(plan, projection)
        candidates = []
        for step in projection['steps']:
            value = deepcopy(step.get('object_ref'))
            if value is None and type(step.get('case_id')) is int and step['case_id'] > 0:
                value = {'type': 'case', 'id': step['case_id']}
            candidates.append(value)
    data['goal'] = _text(data['goal'], 300) or '待核对事项'
    native = _native_reader(db, request, auth, auth)
    visible = {}
    for position, (step, candidate) in enumerate(zip(data['steps'], candidates)):
        step['title'] = _text(step['title'], 160) or f'第{position + 1}步'
        step['wait_for'] = _text(step['wait_for'], 500)
        step['object_ref'], step['manual_route'] = None, None
        if candidate is None:
            continue
        ref = BusinessObjectRef.model_validate(candidate)
        key = (ref.type, ref.id)
        if key not in visible:
            visible[key] = await _visible_object(db, auth, native, ref, strict_sources=strict_sources)
        snapshot = visible[key]
        if snapshot is not None:
            step['object_ref'] = snapshot.ref.model_dump(mode='json')
            step['manual_route'] = snapshot.manual_route
        elif step['status'] not in {'failed', 'cancelled', 'uncertain', 'needs_input'}:
            step['status'], step['wait_reason'] = 'waiting', 'source_inaccessible'
    data['allowed_actions'] = _followup_actions(data['allowed_actions'])
    result = PlanView.model_validate(data)
    _guard(db, auth)
    return result


@router.get('/plans/{plan_id}', response_model=PlanView)
async def get_plan(plan_id: UUIDText, request: Request, db=Depends(get_db), user=Depends(get_user)):
    with _errors(db):
        _no_query(request)
        auth = _capture(db, request, user)
        return await shared_plan_view(db, request, user, auth, plan_id)


@router.post('/plans/{plan_id}/followup', response_model=PlanView)
async def set_followup(plan_id: UUIDText, body: FollowupAction, request: Request,
                       db=Depends(get_db), user=Depends(get_user)):
    from .assistant_runtime_plans import followup_transition, project_legacy_plan
    from .assistant_runtime_principal import principal_for_followup_request
    with _errors(db):
        _no_query(request)
        auth = _capture(db, request, user)
        with _reading(db, auth, check=False) as reader:
            plan = _owned(reader, auth, AssistantWorkPlan, plan_id)
            auth = replace(auth, session_id=plan.session_id)
            _check(reader, auth)
            version, engine = plan.version, plan.engine_version
            # Legacy text cannot carry the finite condition schema. Keep it
            # intact and identify the actual owned steps needing an explicit
            # structured update; neither wait_for nor card state is a condition.
            legacy_steps = []
            if engine != 2:
                projection = project_legacy_plan(reader, auth, auth.session_id, plan)
                legacy_steps = [{'key': step['key'],
                    'title': _text(step.get('title') or f'第{position + 1}步', 160),
                    'missing': ['conditions', 'completion_conditions']}
                    for position, step in enumerate(projection['steps'])]
        # Use the existing original-cookie/CSRF verifier even for a rejected
        # legacy upgrade. This does not grant a worker/model capability.
        principal_for_followup_request(db, request, auth, auth.session_id, plan_id, action=body.action)
        if version != body.expected_version:
            raise HTTPException(409, '计划已更新，请读取最新版本后修改')
        if engine != 2:
            raise HTTPException(409, {'message': '请先为以下步骤补充明确的结构化前置与完成条件，显式保存新版事项后再设置跟进；原计划说明不会自动转换',
                'plan_id': plan_id, 'steps': legacy_steps})
        # All transitions, version CAS, stop semantics and audit writes remain
        # in the original M3.5 service. No model or preparation is invoked here.
        followup_transition(db, request, auth, plan_id, body.model_dump(mode='python'))
        service.require_preparation_read_phase(db)
        db.rollback()  # Close an idempotent no-op's read transaction as well.
        return await shared_plan_view(db, request, auth, auth, plan_id)


def _workspace_query(request):
    allowed = {'group', 'cursor', 'limit'}
    if set(request.query_params) - allowed or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, '工作区只接受单个group、cursor和limit参数')
    values = dict(request.query_params)
    if 'limit' in values:
        if re.fullmatch(r'[0-9]+', values['limit']) is None:
            raise HTTPException(422, '每页数量必须是1至100的整数')
        try:
            values['limit'] = int(values['limit'])
        except ValueError:
            raise HTTPException(422, '每页数量必须是1至100的整数') from None
    try:
        return WorkspaceQuery.model_validate(values)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '请核对工作区分组、游标和每页数量') from None


@router.get('/workspace', response_model=WorkspaceView)
async def get_workspace(request: Request, db=Depends(get_db), user=Depends(get_user)):
    from .assistant_runtime_workspace import read_workspace
    query = _workspace_query(request)
    with _errors(db):
        # Workspace has no conversation on first load; its own original-login
        # checks also retain the original aggregate read-only task boundary.
        return await read_workspace(db, request, user, query)


def _notification_query(request):
    if set(request.query_params) - {'cursor', 'limit'} or any(
            len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise HTTPException(422, '通知列表只接受单个cursor和limit参数')
    values = dict(request.query_params)
    if 'limit' in values:
        if re.fullmatch(r'[0-9]+', values['limit']) is None:
            raise HTTPException(422, '每页数量必须是1至100的整数')
        try:
            values['limit'] = int(values['limit'])
        except ValueError:
            raise HTTPException(422, '每页数量必须是1至100的整数') from None
    try:
        return NotificationQuery.model_validate(values)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '请核对通知游标和每页数量') from None


@router.get('/notifications', response_model=NotificationList)
async def get_notifications(request: Request, db=Depends(get_db), user=Depends(get_user)):
    from .assistant_runtime_workspace import read_notifications
    query = _notification_query(request)
    with _errors(db):
        return await read_notifications(db, request, user, query)


@router.post('/notifications/{notification_id}/read', response_model=NotificationView)
async def read_notification(notification_id: UUIDText, request: Request,
                            db=Depends(get_db), user=Depends(get_user)):
    from .assistant_runtime_workspace import mark_notification_read
    _no_query(request)
    if await request.body():
        raise HTTPException(422, '标记通知已读不接受请求内容')
    with _errors(db):
        # The shared service revalidates the real cookie/CSRF identity and the
        # current source. Read state cannot finish a task or authorize a Plan.
        return await mark_notification_read(db, request, user, notification_id)


@router.get('/sessions/{session_id}/proposals/{proposal_id}/execution-result', response_model=ReceiptLookup)
async def execution_result(session_id: UUIDText, proposal_id: UUIDText, request: Request,
                           db=Depends(get_db), user=Depends(get_user)):
    from .assistant_runtime_receipts import _owned_lookup_proposal, lookup_receipt
    with _errors(db):
        _no_query(request)
        auth = _capture(db, request, user, session_id)
        _guard(db, auth)
        with _reading(db, auth) as reader:
            _owned_lookup_proposal(reader, auth, session_id, proposal_id)
        native = _native_reader(db, request, user, auth)
        result = await lookup_receipt(db, auth, session_id, proposal_id, native_reader=native)
        _guard(db, auth)
        return result


_EVENT_BATCH = 100
_EVENT_POLL_SECONDS = 1.0
_EVENT_HEARTBEAT_SECONDS = 15.0
_TERMINAL_EVENTS = {'succeeded': 'run.completed', 'failed': 'run.failed', 'cancelled': 'run.cancelled'}


def _event_conflict():
    raise HTTPException(409, '执行事件不完整或游标已失效，请重新读取执行记录')


def _event_cursor(request):
    if set(request.query_params) - {'after_seq'} or len(request.query_params.getlist('after_seq')) > 1:
        raise HTTPException(422, '事件接口只接受一个after_seq游标')
    headers = request.headers.getlist('last-event-id')
    if len(headers) > 1:
        raise HTTPException(422, '事件游标无效')
    values = [request.query_params.get('after_seq'), headers[0] if headers else None]
    parsed = [0]
    for value in values:
        if value is None:
            continue
        if not re.fullmatch(r'[0-9]+', value):
            raise HTTPException(422, '事件游标必须是非负整数')
        try:
            parsed.append(int(value))
        except ValueError:
            raise HTTPException(422, '事件游标无效') from None
    # EventSource retains the original URL on reconnect; its latest received
    # ID may advance beyond that URL's initial after_seq.
    return max(parsed)


def _event_view(row):
    return RunEventView.model_validate({'run_id': row.run_id, 'seq': row.seq,
        'type': row.type, 'payload': deepcopy(row.payload), 'created_at': row.created_at})


def _event_work(reader, auth, work_id):
    if work_id is None:
        return None
    work = reader.get(WorkItem, work_id)
    if work is None or (work.owner_id, work.store_id, work.session_id) != (
            auth.actor_id, auth.store_id, auth.session_id):
        _event_conflict()
    return work


def _event_card(reader, auth, card_id, work_id):
    card = _owned(reader, auth, AssistantProposal, card_id)
    if ((card.owner_role, card.access_version) != (auth.role, auth.access_version)
            or card.source_work_item_id != work_id):
        _event_conflict()
    return card


def _event_sources(reader, auth, run, event):
    """Validate historical references, without reinterpreting them as success."""
    payload = event.payload
    if event.run_id != run.id:
        _event_conflict()
    if event.type == 'run.progress':
        if payload.display.revision > run.display_revision:
            _event_conflict()
    elif event.type == 'tool.finished':
        item = reader.scalar(select(RunItem).where(RunItem.id == payload.run_item_id,
            RunItem.run_id == run.id))
        if (item is None or item.kind not in {'tool', 'batch_row'} or item.finished_at is None
                or item.status not in {'succeeded', 'failed', 'uncertain', 'skipped'}
                or item.work_item_id != payload.work_item_id):
            _event_conflict()
        _event_work(reader, auth, item.work_item_id)
        if item.proposal_id:
            _event_card(reader, auth, item.proposal_id, item.work_item_id)
        current_refs = [BusinessObjectRef.model_validate(value) for value in item.result_refs or []]
        if any(value not in current_refs for value in payload.result_refs):
            _event_conflict()
    elif event.type == 'proposal.prepared':
        work = _event_work(reader, auth, payload.work_item_id)
        _event_card(reader, auth, payload.proposal_id, payload.work_item_id)
        if work is None or work.item_kind != 'prepare' or work.plan_id != payload.plan_id:
            _event_conflict()
        if payload.plan_id is not None:
            _owned(reader, auth, AssistantWorkPlan, payload.plan_id)
        linked = reader.scalar(select(RunItem.id).where(RunItem.run_id == run.id,
            RunItem.work_item_id == work.id).limit(1))
        if linked is None:
            from .assistant_runtime_runner import _manifest_data
            manifests = reader.scalars(select(RunItem).where(RunItem.run_id == run.id,
                RunItem.tool_name == 'prepare_inputs'))
            linked = any(any(row.get('work_item_id') == work.id
                and row.get('proposal_id') == payload.proposal_id for row in _manifest_data(item)['rows'])
                for item in manifests)
        if not linked:
            _event_conflict()
    elif event.type == 'plan.updated' or event.type.startswith('run.'):
        if payload.plan_id is not None:
            _owned(reader, auth, AssistantWorkPlan, payload.plan_id)
            if payload.plan_id != run.plan_id:
                _event_conflict()
    else:
        _event_conflict()


def _event_batch(db, auth, run_id, after_seq):
    """Copy one contiguous committed batch; no transaction survives the call."""
    with _errors(db), _reading(db, auth) as reader:
        run = _owned(reader, auth, Run, run_id)
        if after_seq > run.event_seq:
            _event_conflict()
        if run.event_seq < 1:
            _event_conflict()
        if after_seq and reader.scalar(select(RunEvent.id).where(
                RunEvent.run_id == run.id, RunEvent.seq == after_seq)) is None:
            _event_conflict()
        rows = list(reader.scalars(select(RunEvent).where(RunEvent.run_id == run.id,
            RunEvent.seq > after_seq).order_by(RunEvent.seq).limit(_EVENT_BATCH)))
        events = []
        expected = after_seq + 1
        for row in rows:
            if row.seq != expected or row.seq > run.event_seq:
                _event_conflict()
            event = _event_view(row)
            _event_sources(reader, auth, run, event)
            events.append(event)
            expected += 1
        if expected <= run.event_seq and len(events) < _EVENT_BATCH:
            _event_conflict()
        if run.status in _TERMINAL_EVENTS:
            last = reader.scalar(select(RunEvent).where(RunEvent.run_id == run.id,
                RunEvent.seq == run.event_seq))
            if last is None or last.type != _TERMINAL_EVENTS[run.status]:
                _event_conflict()
        return tuple(events), run.status, run.event_seq


async def _public_event(db, request, auth, event):
    """Recheck each cached event immediately before sending its safe projection."""
    with _errors(db), _reading(db, auth) as reader:
        run = _owned(reader, auth, Run, event.run_id)
        row = reader.scalar(select(RunEvent).where(RunEvent.run_id == run.id, RunEvent.seq == event.seq))
        if row is None or _event_view(row) != event:
            _event_conflict()
        _event_sources(reader, auth, run, event)
    public = event.model_copy(deep=True)
    if public.type == 'run.progress':
        public.payload.display.text = _text(public.payload.display.text)
    elif public.type == 'tool.finished':
        native = _native_reader(db, request, auth, auth)
        visible = []
        for value in public.payload.result_refs:
            snapshot = await _visible_object(db, auth, native, value)
            if snapshot is not None:
                visible.append(snapshot.ref)
        public.payload.result_refs = visible
    _guard(db, auth)
    return public


async def open_event_stream(db, request, user, run_id, *, after_seq=0):
    """Authorize and prime a subscription, returning an async iterator.

    The iterator yields typed events or None for a read-only heartbeat. It owns
    an idle same-engine Session only as a factory anchor: every actual read uses
    a short independent Session closed before an await/sleep/yield. Closing it
    never cancels a Run, releases a lease, or starts any execution.
    """
    if type(after_seq) is not int or after_seq < 0:
        raise HTTPException(422, '事件游标必须是非负整数')
    with _errors(db):
        auth = _capture(db, request, user)
        with _reading(db, auth, check=False) as reader:
            run = _owned(reader, auth, Run, run_id)
            auth = replace(auth, session_id=run.session_id)
            _check(reader, auth)
        first, _, _ = _event_batch(db, auth, run_id, after_seq)
        _guard(db, auth)

    async def iterate():
        cursor, batch = after_seq, first
        last_heartbeat = monotonic()
        # No ORM object from get_db or an event payload is kept as authority.
        with Session(bind=auth.bind, autoflush=False, expire_on_commit=False) as anchor:
            while True:
                with _errors(anchor):
                    for event in batch:
                        public = await _public_event(anchor, request, auth, event)
                        cursor = public.seq
                        yield public
                    batch, status, last_seq = _event_batch(anchor, auth, run_id, cursor)
                    if batch:
                        continue
                    if status in _TERMINAL_EVENTS and cursor == last_seq:
                        _guard(anchor, auth)
                        return
                    if monotonic() - last_heartbeat >= _EVENT_HEARTBEAT_SECONDS:
                        _guard(anchor, auth)
                        last_heartbeat = monotonic()
                        yield None
                await asyncio.sleep(_EVENT_POLL_SECONDS)
    return iterate()


@router.get('/runs/{run_id}/events')
async def run_events(run_id: UUIDText, request: Request, db=Depends(get_db), user=Depends(get_user)):
    events = await open_event_stream(db, request, user, run_id, after_seq=_event_cursor(request))

    async def body():
        try:
            while not await request.is_disconnected():
                try:
                    event = await anext(events)
                except StopAsyncIteration:
                    return
                if event is None:
                    yield ': heartbeat\n\n'
                else:
                    yield ('id: ' + str(event.seq) + '\nevent: ' + event.type + '\ndata: '
                           + json.dumps(event.model_dump(mode='json'), ensure_ascii=False, allow_nan=False) + '\n\n')
        except HTTPException as exc:
            yield 'event: error\ndata: ' + json.dumps({'status': exc.status_code,
                'detail': '订阅已停止，请重新读取执行记录；登录失效时请重新登录'}, ensure_ascii=False) + '\n\n'
        finally:
            await events.aclose()

    class EventStream(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                # ASGI 2.4 send failures need not close a suspended iterator.
                await self.body_iterator.aclose()
                await events.aclose()

    return EventStream(body(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
