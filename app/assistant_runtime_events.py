"""Transactional, minimal Runtime events; this module never commits or does I/O.

Queue lifecycle writers and the fixed Plan hook are server-only entry points.
Workers first acquire queue.lock_for_write, append artifacts/events, flush, then
revalidate their principal before committing. A capability expires with that
transaction; it is neither a model tool nor an HTTP authorization mechanism.
"""
from datetime import timezone
import re
from uuid import UUID
from weakref import WeakKeyDictionary, ref

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.orm.attributes import set_committed_value

from .assistant_runtime_models import Run, RunEvent, RunItem, WorkItem
from .assistant_runtime_principal import (
    _reader, _time, principal_for_request, revalidate_control_principal,
    revalidate_principal, runtime_request_context,
)
from .assistant_runtime_schemas import RunEventView
from .business_assistant_models import AssistantProposal, AssistantWorkPlan
from .db import utcnow


_LIFECYCLE = {'queued': 'run.queued', 'running': 'run.started',
              'succeeded': 'run.completed', 'failed': 'run.failed', 'cancelled': 'run.cancelled'}
_CAP_KEY = 'assistant_runtime_event_capability'
_CAPS = WeakKeyDictionary()
_SOURCE_FIELDS = ('id', 'owner_id', 'store_id', 'session_id', 'plan_id', 'goal_version',
                  'auth_kind', 'login_session_ref', 'grant_id', 'fence')


class _Capability:
    pass


def _conflict():
    raise HTTPException(409, '运行事件来源或执行版本已变化，请重新读取')


def _now(principal=None, clock=None):
    return _time((clock or (principal._clock if principal else utcnow))())


def _scope(db, store_id):
    if (db.info.get('store_scope') not in {(store_id,), (store_id, 0), (0, store_id)}
            or db.info.get('write_store') != store_id or db.info.get('aggregate_scope')):
        _conflict()


def _committed(db, run_id, factory=None):
    with _reader(db, factory) as reader:
        row = reader.scalar(select(Run).where(Run.id == run_id))
        return None if row is None else {key: getattr(row, key) for key in
            (*_SOURCE_FIELDS, 'version', 'event_seq', 'status')}


def _attached(db, run):
    state = inspect(run)
    if state.session is not db or not state.persistent or state.deleted:
        _conflict()
    _scope(db, run.store_id)


def _matches(run, principal):
    return (run.id, run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version,
            run.auth_kind, run.login_session_ref, run.grant_id, run.fence) == (
        principal.run_id, principal.actor_id, principal.store_id, principal.session_id,
        principal.plan_id, principal.goal_version, principal.auth_kind, principal._login_ref,
        principal.grant_id, principal.fence)


def _locked_run(db, principal, *, control=False, terminal=False, clock=None):
    guard = revalidate_control_principal if control else revalidate_principal
    guard(db, principal, clock=clock)
    if principal.run_id is None or db.get_transaction() is None:
        _conflict()
    with db.no_autoflush:
        run = db.scalar(select(Run).where(Run.id == principal.run_id,
            Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
            Run.session_id == principal.session_id))
        if run is None:
            _conflict()
        _attached(db, run)
        old = _committed(db, run.id, principal._read_session_factory)
        if (old is None or not _matches(run, principal) or run.version <= old['version']
                or any(getattr(run, name) != old[name] for name in _SOURCE_FIELDS)):
            _conflict()
        if terminal and run.status in {'succeeded', 'failed'}:
            if control or run.stop_requested or run.lease_owner is not None or run.lease_until is not None:
                _conflict()
        elif (run.status != 'running' or run.lease_owner != principal.lease_owner
              or run.lease_until is None or _time(run.lease_until) <= _now(principal, clock)
              or run.stop_requested and not control):
            _conflict()
    return run


def _bind_fenced_transaction(db, principal, *, control=False, clock=None):
    """Queue-only, after its actual Run CAS and fresh authorization check.

    Release may bind after its pending succeeded/failed transition. That special
    capability permits only the final display snapshot, never a new tool/card.
    The committed source must still be the principal's live running lease.
    """
    if type(control) is not bool:
        raise TypeError('control must be boolean')
    run = _locked_run(db, principal, control=control, terminal=True, clock=clock)
    cap = _Capability()
    _CAPS[cap] = (ref(db), ref(db.get_transaction()), principal, control,
                  run.status != 'running', run.version)
    db.info[_CAP_KEY] = cap


def _capability(db, principal, *, final=False, clock=None):
    cap = db.info.get(_CAP_KEY)
    state = _CAPS.get(cap) if type(cap) is _Capability else None
    if state is None:
        _conflict()
    session_ref, tx_ref, original, control, terminal, version = state
    if (session_ref() is not db or tx_ref() is not db.get_transaction()
            or original is not principal or control or terminal and not final):
        _conflict()
    run = _locked_run(db, principal, terminal=terminal, clock=clock)
    if run.version < version:
        _conflict()
    return run


def _view(run, event_type, payload, now, seq=None):
    try:
        return RunEventView(run_id=run.id, seq=run.event_seq + 1 if seq is None else seq,
            type=event_type, payload=payload, created_at=now.replace(tzinfo=timezone.utc))
    except (ValidationError, ValueError, TypeError, UnicodeError):
        raise HTTPException(422, '运行事件必须使用已定义的安全展示结构') from None


def _append(db, run, event_type, payload, now, *, display=None):
    """Fixed Core CAS bypasses no tenant guard and never commits its caller."""
    _attached(db, run)
    view = _view(run, event_type, payload, now)
    db.flush()
    table = Run.__table__
    predicates = [table.c.id == run.id, table.c.owner_id == run.owner_id,
        table.c.store_id == run.store_id, table.c.session_id == run.session_id,
        table.c.version == run.version, table.c.event_seq == run.event_seq]
    for name in ('status', 'fence', 'lease_owner', 'lease_until', 'stop_requested',
                 'plan_id', 'goal_version', 'auth_kind', 'login_session_ref', 'grant_id'):
        predicates.append(table.c[name] == getattr(run, name))
    values = {'version': run.version + 1, 'event_seq': view.seq}
    if display is not None:
        values.update(display_text=display['text'], display_revision=display['revision'])
    result = db.connection().execute(table.update().where(*predicates).values(**values))
    if result.rowcount != 1:
        _conflict()
    for key, value in values.items():
        set_committed_value(run, key, value)
    row = RunEvent(run_id=run.id, seq=view.seq, type=event_type,
        payload=view.payload.model_dump(mode='json'), created_at=now)
    db.add(row)
    db.flush()
    db.info['assistant_preparation_transaction'] = db.get_transaction()
    return view


def _append_queue_transition(db, run, *, previous_status, clock=utcnow):
    """Only queue's authenticated state transaction may call this private API.

    Queue must flush the status CAS first and perform its final fresh source
    check afterwards. This independently proves the committed prior state and
    emits no event for stop requests, heartbeat or repeated target states.
    """
    _attached(db, run)
    if previous_status == run.status:
        return None
    old = _committed(db, run.id)
    if old is None:
        if previous_status is not None or run.status != 'queued':
            _conflict()
        floor = 0
    else:
        if (old['status'] != previous_status or run.version <= old['version']
                or any(getattr(run, key) != old[key] for key in
                       ('id', 'owner_id', 'store_id', 'session_id'))):
            _conflict()
        floor = old['event_seq']
        if previous_status not in {'queued', 'running'}:
            _conflict()
        if run.status == 'running' and previous_status != 'queued':
            _conflict()
    event_type = _LIFECYCLE.get(run.status)
    if event_type is None:
        _conflict()
    with db.no_autoflush:
        duplicate = db.scalar(select(RunEvent).where(RunEvent.run_id == run.id,
            RunEvent.seq > floor, RunEvent.type == event_type).order_by(RunEvent.seq.desc()))
    if duplicate is not None:
        return _view(run, duplicate.type, duplicate.payload, _time(duplicate.created_at), duplicate.seq)
    return _append(db, run, event_type, {'plan_id': run.plan_id}, _now(clock=clock))


def _owned(row, run):
    return row is not None and (row.owner_id, row.store_id, row.session_id) == (
        run.owner_id, run.store_id, run.session_id)


def _artifact_refs(db, run, principal, event_type, payload):
    if event_type == 'tool.finished':
        item = db.scalar(select(RunItem).where(RunItem.id == payload.run_item_id,
            RunItem.run_id == run.id))
        if (item is None or item.kind not in {'tool', 'batch_row'}
                or item.status not in {'succeeded', 'failed', 'uncertain', 'skipped'}
                or item.finished_at is None or item.work_item_id != payload.work_item_id
                or [v.model_dump(mode='json') for v in payload.result_refs] != (item.result_refs or [])):
            _conflict()
    elif event_type == 'proposal.prepared':
        card = db.scalar(select(AssistantProposal).where(AssistantProposal.id == payload.proposal_id))
        work = db.scalar(select(WorkItem).where(WorkItem.id == payload.work_item_id)) if payload.work_item_id else None
        if (not _owned(card, run) or not _owned(work, run) or card.source_work_item_id != work.id
                or (card.owner_role, card.access_version) != (principal.role, principal.access_version)
                or payload.plan_id != work.plan_id or work.plan_id != run.plan_id
                or work.item_kind != 'prepare'):
            _conflict()
        linked = db.scalar(select(RunItem.id).where(RunItem.run_id == run.id,
            RunItem.work_item_id == work.id))
        if linked is None:
            from .assistant_runtime_runner import _manifest_data
            manifests = db.scalars(select(RunItem).where(RunItem.run_id == run.id,
                RunItem.tool_name == 'prepare_inputs'))
            linked = any(any(row.get('work_item_id') == work.id and row.get('proposal_id') == card.id
                for row in _manifest_data(item)['rows']) for item in manifests)
            if not linked:
                _conflict()
    elif event_type == 'plan.updated':
        plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == payload.plan_id))
        if not _owned(plan, run) or plan.id != run.plan_id or plan.goal_version != run.goal_version:
            _conflict()
    else:
        raise HTTPException(422, '此事件只能由固定状态或展示服务产生')


def append_event(db, principal, event_type, payload, *, clock=None):
    """Append a typed artifact reference after queue.lock_for_write, no commit."""
    run = _capability(db, principal, clock=clock)
    now = _now(principal, clock)
    view = _view(run, event_type, payload, now)
    with db.no_autoflush:
        db.flush()
        _artifact_refs(db, run, principal, event_type, view.payload)
        result = _append(db, run, event_type, view.payload, now)
    revalidate_principal(db, principal, clock=clock)
    return result


def append_plan_updated(db, principal, plan_id, version, *, clock=None):
    """Fixed plans.on_plan_updated hook; safe even for permission-loss cleanup.

    Plans already holds Session/Plan/Run locks and has flushed its Run CAS. This
    hook only records the Plan ID; it cannot publish content on a control path.
    """
    revalidate_control_principal(db, principal, clock=clock)
    with db.no_autoflush:
        plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id))
        if (plan is None or type(version) is not int or version != plan.version
                or (plan.owner_id, plan.store_id, plan.session_id, plan.id, plan.goal_version)
                != (principal.actor_id, principal.store_id, principal.session_id,
                    principal.plan_id, principal.goal_version)):
            _conflict()
        control = plan.status in {'paused', 'completed', 'cancelled'}
        run = _locked_run(db, principal, control=control, clock=clock)
        if control and not run.stop_requested:
            _conflict()
        result = _append(db, run, 'plan.updated', {'plan_id': plan.id}, _now(principal, clock))
    (revalidate_control_principal if control else revalidate_principal)(db, principal, clock=clock)
    return result


_EXTRA_LABEL = r'(?:authorization|cookie|set-cookie|x[-_ ]csrf(?:[-_ ]token)?|csrf(?:[-_ ]token)?|session[_ -]?token|dealer_session|password|api[_ -]?key|secret|密码|口令|验证码)'
_LABEL_BOUNDARY = r'(?<![A-Za-z0-9_])'
_EXTRA_SECRET = re.compile(r'(?i)' + _LABEL_BOUNDARY + _EXTRA_LABEL + r'\s*["\']?\s*[:：=]\s*[^\r\n]*')


def _safe_display(value, *, final):
    """Only complete cumulative content, never provider dictionaries/reasoning.

    Holding unfinished credential tails is intentionally in-memory: the caller
    supplies the full content again, rather than persisting raw pending bytes.
    """
    from .business_assistant_service import MODEL_TEXT_CHARS, safe_text
    from .business_assistant_stream import SafeDeltas
    if type(value) is not str or len(value) > MODEL_TEXT_CHARS:
        raise HTTPException(422, '展示内容必须是有限的完整文本快照')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise HTTPException(422, '展示文本编码无效') from None
    # Provider reasoning fields are never accepted; explicit reasoning markup
    # is also removed defensively, including an unfinished final block.
    value = re.sub(r'(?is)<(?:think|reasoning)>.*?(?:</(?:think|reasoning)>|$)', '', value)
    value = _EXTRA_SECRET.sub('[凭据已隐藏]', value)
    value = re.sub(r'(?i)' + _LABEL_BOUNDARY + r'(?:sk|tp)-[A-Za-z0-9_-]*', '[密钥已隐藏]', value)
    if not final:
        words = ('authorization', 'cookie', 'set-cookie', 'x-csrf-token', 'x_csrf_token',
                 'csrf_token', 'session_token', 'session token', 'dealer_session')
        cut, lowered = len(value), value.lower()
        for word in words:
            for length in range(1, min(len(word), len(value)) + 1):
                if lowered.endswith(word[:length]):
                    cut = min(cut, len(value) - length)
        label = re.search(r'(?i)' + _LABEL_BOUNDARY + _EXTRA_LABEL + r'\s*["\']?\s*[:：=]?\s*$', value)
        if label:
            cut = min(cut, label.start())
        value = value[:cut]
    else:
        # No final credential token or open label is released merely because
        # generation ended. Redact malformed/incomplete keys as well.
        value = re.sub(r'(?i)(?:Bearer\s*|(?:密码|口令|验证码|password|api[_ -]?key|secret)\s*(?:[:：=]|是)\s*)[^\s,，;；"\']*$', '[凭据已隐藏]', value)
    return SafeDeltas(safe_text).feed(value, final=final)


def progress(db, principal, full_display_text, *, final=False, clock=None):
    """Coalesce full safe snapshots at one-second intervals; final bypasses it.

    A skipped candidate is not stored anywhere. The caller retains its content
    in memory and must explicitly send its latest full text with final=True.
    """
    if type(final) is not bool:
        raise TypeError('final must be boolean')
    run = _capability(db, principal, final=final, clock=clock)
    text, now = _safe_display(full_display_text, final=final), _now(principal, clock)
    with db.no_autoflush:
        last = db.scalar(select(RunEvent).where(RunEvent.run_id == run.id,
            RunEvent.type == 'run.progress').order_by(RunEvent.seq.desc()).limit(1))
        if last is not None:
            previous = _view(run, last.type, last.payload, _time(last.created_at), last.seq).payload.display
            if previous.text == text and previous.phase == run.status:
                revalidate_principal(db, principal, clock=clock)
                return None
            if not final and (now - _time(last.created_at)).total_seconds() < 1:
                revalidate_principal(db, principal, clock=clock)
                return None
        display = {'phase': run.status, 'text': text, 'revision': run.display_revision + 1}
        result = _append(db, run, 'run.progress', {'display': display}, now, display=display)
    revalidate_principal(db, principal, clock=clock)
    return result


def read_events(db, request, user, run_id, *, after_seq=0, limit=100, clock=utcnow,
                read_session_factory=None):
    """Read one SSE backlog batch using this employee's current real login.

    The SSE owner must call this again for each batch and revalidate immediately
    before yielding a cached event. Returned DTOs are not authorization tokens.
    """
    if (type(after_seq) is not int or after_seq < 0 or type(limit) is not int
            or not 1 <= limit <= 200):
        raise HTTPException(422, '事件游标或读取数量无效')
    try:
        if type(run_id) is not str or str(UUID(run_id)) != run_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, '未找到可访问的执行记录') from None
    if runtime_request_context(request) is not None or getattr(user, '_aggregate_scope', False):
        raise HTTPException(403, '运行事件只供员工本人登录后查看')
    actor_id, store_id = user.id, getattr(user, '_active_store_id', None)
    if type(actor_id) is not int or type(store_id) is not int or store_id < 1:
        raise HTTPException(403, '请使用当前门店的员工身份')
    with _reader(db, read_session_factory) as reader:
        row = reader.scalar(select(Run).where(Run.id == run_id, Run.owner_id == actor_id,
            Run.store_id == store_id))
        if row is None:
            raise HTTPException(404, '未找到可访问的执行记录')
        session_id = row.session_id
    principal = principal_for_request(db, request, user, session_id, clock=clock,
        read_session_factory=read_session_factory)
    with _reader(db, read_session_factory) as reader:
        run = reader.scalar(select(Run).where(Run.id == run_id, Run.owner_id == actor_id,
            Run.store_id == store_id, Run.session_id == principal.session_id))
        if run is None:
            raise HTTPException(404, '未找到可访问的执行记录')
        rows = reader.scalars(select(RunEvent).where(RunEvent.run_id == run.id,
            RunEvent.seq > after_seq).order_by(RunEvent.seq.asc()).limit(limit))
        result = []
        for event in rows:
            view = _view(run, event.type, event.payload, _time(event.created_at), event.seq)
            if view.type == 'run.progress':
                view.payload.display.text = _safe_display(view.payload.display.text, final=True)
            result.append(view)
    revalidate_principal(db, principal, clock=clock)
    return result
