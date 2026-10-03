"""Transactional wake signals and one-event dispatch, without model calls.

Producers supply real persisted reference IDs from their successful transaction.
This helper neither grants access nor proves a domain fact. It flushes the
caller's transaction, never commits it, and never stores conversation content.
The dispatcher authorizes each consumer and re-reads the original source. A
signal is a reason to inspect a Plan, never proof that a condition is satisfied.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from .assistant_runtime_models import FollowupGrant, PlanStep, WakeEvent
from .assistant_runtime_schemas import BusinessObjectRef, Condition, EvidenceRef
from .db import utcnow


_REF_FIELDS = ('object_ref', 'proposal_id', 'task_id', 'plan_id', 'source_ref')


def _invalid():
    raise HTTPException(422, '唤醒事件必须使用真实来源和明确的原记录引用') from None


def _conflict():
    raise HTTPException(409, '唤醒事件来源已存在或发生并发变化，请核对原事务') from None


def _uuid(value):
    if type(value) is not str:
        _invalid()
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        _invalid()
    if str(parsed) != value:
        _invalid()
    return value


def _positive(value):
    if type(value) is not int or value < 1:
        _invalid()
    return value


def _source(value):
    # Native event/row families are named by producer code, never model text.
    # This structural contract also accommodates the later dedicated domains
    # without an arbitrary JSON blob or a second source-specific event table.
    if (type(value) is not dict or set(value) - {'type', 'id', 'version'}
            or not {'type', 'id'} <= set(value)
            or type(value['type']) is not str
            or re.fullmatch(r'[a-z][a-z0-9_]{0,79}', value['type']) is None):
        _invalid()
    ident = _positive(value['id']) if type(value['id']) is int else _uuid(value['id'])
    version = _positive(value['version']) if value.get('version') is not None else None
    return {'type': value['type'], 'id': ident, 'version': version}


def _values(signal_key, topic, refs):
    if (type(signal_key) is not str or not 1 <= len(signal_key) <= 255
            or re.fullmatch(r'[A-Za-z0-9_.:/-]+', signal_key) is None
            or type(topic) is not str or re.fullmatch(r'[a-z][a-z0-9_.-]{0,79}', topic) is None
            or type(refs) is not dict or set(refs) - {'store_id', *_REF_FIELDS}
            or not {'store_id', 'source_ref'} <= set(refs)):
        _invalid()
    values = {'signal_key': signal_key, 'topic': topic, 'store_id': _positive(refs['store_id'])}
    for field in ('proposal_id', 'plan_id'):
        values[field] = _uuid(refs[field]) if refs.get(field) is not None else None
    values['task_id'] = _positive(refs['task_id']) if refs.get('task_id') is not None else None
    try:
        values['object_ref'] = (BusinessObjectRef.model_validate(refs['object_ref']).model_dump(mode='json')
                                if refs.get('object_ref') is not None else None)
    except (ValueError, TypeError):
        _invalid()
    values['source_ref'] = _source(refs['source_ref'])
    return values


def _check_references(db, values):
    from .business_assistant_models import AssistantProposal, AssistantWorkPlan
    from .flow_models import Task
    # These optional FK refs must be in the producer's real store. Object and
    # source families are proved by the original producer, not guessed by SQL.
    for field, model in (('proposal_id', AssistantProposal), ('plan_id', AssistantWorkPlan), ('task_id', Task)):
        ident = values[field]
        if ident is not None and db.scalar(select(model.id).where(
                model.id == ident, model.store_id == values['store_id'])) is None:
            raise HTTPException(404, '唤醒事件所引用的记录不属于当前门店')


def _same(row, values):
    if any(getattr(row, key) != value for key, value in values.items()):
        _conflict()
    # A duplicate never resets dispatched state, attempts or next_attempt_at.
    return row


def emit_wake_event(db, signal_key, topic, refs, *, not_before=None):
    """Add/flush one unique signal in the caller's existing transaction.

    Parents and native source IDs must already exist in this transaction. If a
    concurrent duplicate is not visible in its repeatable-read snapshot, return
    a conflict; never roll back/commit the caller or fabricate a successful emit.
    Original business idempotency decides what a subsequent request may do.
    A producer may delay a newly inserted event; duplicates retain their exact
    existing retry schedule and dispatched state.
    """
    values = _values(signal_key, topic, refs)
    schedule = {}
    if not_before is not None:
        from .assistant_runtime_principal import _time
        schedule['next_attempt_at'] = _time(not_before)
    scope = db.info.get('store_scope')
    if scope is not None and (values['store_id'] not in scope
                             or values['store_id'] != db.info.get('write_store')):
        raise HTTPException(403, '不能在当前门店范围外写入唤醒事件')
    # Flush parent versions outside the unique-event savepoint exception path:
    # an unrelated business integrity failure must retain its original meaning.
    db.flush()
    with db.no_autoflush:
        _check_references(db, values)
        prior = db.scalar(select(WakeEvent).where(WakeEvent.signal_key == signal_key))
        if prior is not None:
            return _same(prior, values)
    try:
        with db.begin_nested():
            row = WakeEvent(id=str(uuid4()), **deepcopy(values), **schedule)
            db.add(row)
            db.flush()
    except IntegrityError:
        with db.no_autoflush:
            prior = db.scalar(select(WakeEvent).where(WakeEvent.signal_key == signal_key))
            if prior is not None:
                return _same(prior, values)
        _conflict()
    return row


@dataclass(frozen=True, slots=True)
class DispatchResult:
    event_id: str
    state: str
    attempt: int
    run_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PollResult:
    plan_id: str
    state: str
    run_ids: tuple[str, ...] = ()


CHECK_INTERVAL_SECONDS = 5
_POLL_RETRY_SECONDS = 30
_EVENT_FIELDS = ('id', 'signal_key', 'topic', 'store_id', *_REF_FIELDS,
                 'state', 'attempt', 'next_attempt_at', 'created_at', 'dispatched_at', 'version')
_DISPATCH_DELAYS = (30, 120, 600)


def _event_snapshot(row):
    return {name: deepcopy(getattr(row, name)) for name in _EVENT_FIELDS}


def _event_values(event):
    values = _values(event['signal_key'], event['topic'],
                     {name: event[name] for name in ('store_id', *_REF_FIELDS)})
    if any(values[name] != event[name] for name in values):
        _invalid()
    return values


def _source_facts(reader, event):
    """Fixed producer families only; no arbitrary table/URL/JSON traversal."""
    from .assistant_runtime_models import Run
    from .business_assistant_models import AssistantProposal, AssistantWorkPlan
    from .flow_models import Case, FlowEvent, Task
    values = _event_values(event)
    source = values['source_ref']
    ident, version, store_id = source['id'], source['version'], values['store_id']
    family = (values['topic'], source['type'])
    facts = {'owner_id': None, 'session_id': None, 'role': None, 'access_version': None,
             'grant_id': None, 'goal_version': None}
    if family == ('flow', 'flow_event'):
        row = reader.execute(select(FlowEvent.case_id).where(
            FlowEvent.id == ident, FlowEvent.store_id == store_id)).first()
        if (type(ident) is not int or version is not None or row is None
                or values['signal_key'] != f'flow:{ident}'
                or values['object_ref'] != {'type': 'case', 'id': row.case_id}
                or any(values[key] is not None for key in ('task_id', 'proposal_id', 'plan_id'))):
            _invalid()
        if reader.scalar(select(Case.id).where(Case.id == row.case_id, Case.store_id == store_id)) is None:
            _invalid()
    elif family == ('task', 'task'):
        row = reader.execute(select(Task.version, Task.case_id).where(
            Task.id == ident, Task.store_id == store_id)).first()
        if (type(ident) is not int or version is None or row is None or row.version < version
                or values['signal_key'] != f'task:{ident}:{version}' or values['task_id'] != ident
                or values['object_ref'] != {'type': 'case', 'id': row.case_id}
                or values['proposal_id'] is not None or values['plan_id'] is not None):
            _invalid()
    elif family == ('proposal', 'proposal'):
        row = reader.execute(select(AssistantProposal.version, AssistantProposal.status,
            AssistantProposal.owner_id, AssistantProposal.session_id,
            AssistantProposal.owner_role, AssistantProposal.access_version).where(
                AssistantProposal.id == ident, AssistantProposal.store_id == store_id)).first()
        statuses = {'pending', 'executing', 'succeeded', 'failed', 'uncertain', 'cancelled', 'expired'}
        state = values['signal_key'].removeprefix(f'proposal:{ident}:{version}:')
        if (type(ident) is not str or version is None or row is None or row.version < version
                or values['signal_key'] != f'proposal:{ident}:{version}:{state}' or state not in statuses
                or row.version == version and row.status != state or values['proposal_id'] != ident
                or any(values[key] is not None for key in ('object_ref', 'task_id', 'plan_id'))):
            _invalid()
        facts.update(owner_id=row.owner_id, session_id=row.session_id,
                     role=row.owner_role, access_version=row.access_version)
    elif family == ('plan', 'run'):
        row = reader.execute(select(Run.version, Run.status, Run.owner_id,
            Run.session_id, Run.plan_id, Run.goal_version, Run.auth_kind, Run.trigger_kind).where(
                Run.id == ident, Run.store_id == store_id)).first()
        state = values['signal_key'].removeprefix(f'run:{ident}:{version}:')
        if (type(ident) is not str or version is None or row is None or row.version < version
                or state not in {'queued', 'succeeded', 'failed', 'cancelled'}
                or values['signal_key'] != f'run:{ident}:{version}:{state}'
                or row.version == version and row.status != state
                or row.plan_id is None or values['plan_id'] != row.plan_id
                or type(row.goal_version) is not int or row.goal_version < 1
                or state == 'queued' and (row.auth_kind != 'login' or row.trigger_kind not in {'user', 'manual'})
                or any(values[key] is not None for key in ('object_ref', 'task_id', 'proposal_id'))):
            _invalid()
        plan = reader.execute(select(AssistantWorkPlan.goal_version).where(
            AssistantWorkPlan.id == row.plan_id, AssistantWorkPlan.store_id == store_id,
            AssistantWorkPlan.owner_id == row.owner_id, AssistantWorkPlan.session_id == row.session_id)).first()
        if plan is None or row.goal_version > plan.goal_version:
            _invalid()
        # A later goal cannot inherit a historical Run's blocker or an old
        # employee continuation. Consumers still recheck current Plan facts.
        facts.update(owner_id=row.owner_id, session_id=row.session_id, goal_version=row.goal_version)
    elif family in {('grant', 'grant'), ('grant', 'plan'), ('plan', 'plan')}:
        model = FollowupGrant if source['type'] == 'grant' else AssistantWorkPlan
        fields = [model.id, model.version, model.status, model.owner_id, model.session_id, model.goal_version]
        if model is FollowupGrant:
            fields.append(model.plan_id)
        row = reader.execute(select(*fields).where(model.id == ident, model.store_id == store_id)).first()
        statuses = {'active', 'paused', 'revoked'} if model is FollowupGrant else {'active', 'paused', 'completed', 'cancelled'}
        state = values['signal_key'].removeprefix(f"{source['type']}:{ident}:{version}:")
        if (type(ident) is not str or version is None or row is None or row.version < version
                or state not in statuses or values['signal_key'] != f"{source['type']}:{ident}:{version}:{state}"
                or row.version == version and row.status != state
                or values['plan_id'] != (row.plan_id if model is FollowupGrant else row.id)
                or any(values[key] is not None for key in ('object_ref', 'task_id', 'proposal_id'))):
            _invalid()
        facts.update(owner_id=row.owner_id, session_id=row.session_id)
        if model is FollowupGrant:
            facts.update(grant_id=row.id, goal_version=row.goal_version)
    else:
        return _access_source_facts(reader, values)
    return facts


def _access_source_facts(reader, values):
    from .models import AuditLog, Store, User
    from .user_access_models import UserAccessReceipt
    source, store_id = values['source_ref'], values['store_id']
    ident, version = source['id'], source['version']
    if (type(ident) is not int or any(values[key] is not None for key in
            ('object_ref', 'proposal_id', 'task_id', 'plan_id'))
            or reader.scalar(select(Store.id).where(Store.id == store_id)) is None):
        _invalid()
    facts = {'owner_id': None, 'session_id': None, 'role': None, 'access_version': None,
             'grant_id': None, 'goal_version': None, 'access_change': True}
    if (values['topic'], source['type']) == ('access.changed', 'user_access_receipt'):
        receipt = reader.scalar(select(UserAccessReceipt).where(UserAccessReceipt.id == ident))
        audit = reader.scalar(select(AuditLog).where(AuditLog.id == receipt.audit_id)) if receipt else None
        if (receipt is None or audit is None or audit.store_id != 0
                or audit.action != 'update_user' or audit.entity_type != 'users'
                or audit.entity_id != receipt.target_id or audit.actor_id != receipt.actor_id
                or type(audit.before_data) is not dict or type(audit.after_data) is not dict
                or receipt.result != audit.after_data or version != receipt.previous_version + 1
                or audit.before_data.get('id') != receipt.target_id or audit.after_data.get('id') != receipt.target_id
                or audit.before_data.get('access_version') != receipt.previous_version
                or audit.after_data.get('access_version') != version
                or values['signal_key'] != f'user_access_receipt:{ident}:store:{store_id}'):
            _invalid()
        access_version = reader.scalar(select(User.access_version).where(User.id == receipt.target_id))
        if access_version is None or access_version < version:
            _invalid()
        facts['owner_id'] = receipt.target_id
        return facts
    if source['type'] != 'audit_log' or version is not None:
        _invalid()
    audit = reader.scalar(select(AuditLog).where(AuditLog.id == ident, AuditLog.store_id == 0))
    if audit is None:
        _invalid()
    if (values['topic'] == 'access.changed' and audit.action == 'reset_password'
            and audit.entity_type == 'users' and type(audit.entity_id) is int
            and audit.entity_id != audit.actor_id
            and values['signal_key'] == f'audit_log:{ident}:access:store:{store_id}'):
        if reader.scalar(select(User.id).where(User.id == audit.entity_id)) is None:
            _invalid()
        # The employee may already have changed the reset password. The actual
        # historical reset remains the source; current access is checked below.
        facts['owner_id'] = audit.entity_id
        return facts
    if (values['topic'] == 'store.access_changed' and audit.action == 'update_store'
            and audit.entity_type == 'stores' and audit.entity_id == store_id
            and values['signal_key'] == f'audit_log:{ident}:store:{store_id}'
            and type(audit.before_data) is dict and type(audit.after_data) is dict
            and audit.before_data.get('id') == store_id and audit.after_data.get('id') == store_id
            and type(audit.before_data.get('active')) is bool and type(audit.after_data.get('active')) is bool
            and audit.before_data['active'] is not audit.after_data['active']):
        return facts
    _invalid()


def _plan_links(reader, plan, principal, *, include_cards):
    """Typed stable references only, including actual current WorkItem links."""
    from .flow_models import Task
    steps = list(reader.scalars(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.id)))
    objects, tasks, proposals = set(), set(), set()
    for step in steps:
        if step.object_ref is not None:
            value = BusinessObjectRef.model_validate(step.object_ref)
            objects.add((value.type, value.id))
        if step.proposal_id:
            proposals.add(step.proposal_id)
        for value in TypeAdapter(list[Condition]).validate_python(step.conditions + step.completion_conditions):
            if value.type in {'native_action_available', 'fact_exists'}:
                objects.add((value.object_ref.type, value.object_ref.id))
            elif value.type == 'native_task_state':
                tasks.add(value.task_id)
            elif value.type == 'proposal_succeeded':
                proposals.add(value.proposal_id)
        for evidence in (EvidenceRef.model_validate(value) for value in step.last_evidence or []):
            if evidence.source_type == 'object':
                objects.add((evidence.source_id.type, evidence.source_id.id))
            elif evidence.source_type == 'task':
                tasks.add(evidence.source_id)
            elif evidence.source_type == 'proposal':
                proposals.add(evidence.source_id)
    # process_action's task completion emits its real Case FlowEvent. A typed
    # task condition may have no explicit object_ref; route through the same
    # native Task->Case relationship that the condition evaluator uses.
    objects.update(('case', case_id) for case_id in reader.scalars(select(Task.case_id).where(
        Task.id.in_(tasks), Task.store_id == plan.store_id)))
    if include_cards:
        from .assistant_runtime_plans import project_legacy_plan
        projection = project_legacy_plan(reader, principal, plan.session_id, plan)
        # The shared projection proves current full manifest rows, including
        # explicit carry_forward history. Do not widen to every historical card.
        proposals.update(row['proposal_id'] for step in projection['steps']
                         for row in step['rows'] if row['proposal_id'])
    return objects, tasks, proposals, tuple((step.id, step.version, step.intent_version) for step in steps)


def _matches_plan(reader, event, facts, plan, principal):
    if (facts['owner_id'] is not None and plan.owner_id != facts['owner_id']
            or facts['session_id'] is not None and plan.session_id != facts['session_id']):
        return None
    objects, tasks, proposals, versions = _plan_links(reader, plan, principal,
                                                     include_cards=event['proposal_id'] is not None)
    if event['plan_id'] is not None:
        return versions if event['plan_id'] == plan.id else None
    if facts.get('access_change'):
        return versions
    ref = event['object_ref']
    matched = (ref is not None and (ref['type'], ref['id']) in objects
               or event['task_id'] is not None and event['task_id'] in tasks
               or event['proposal_id'] is not None and event['proposal_id'] in proposals)
    return versions if matched else None


async def _authorize_native_source(db, principal, event, *, client_factory):
    from .assistant_runtime_objects import read_object
    from .assistant_runtime_principal import native_reader_for_principal, revalidate_principal
    from .assistant_runtime_registry import domain_registry
    ref = event['object_ref']
    if ref is not None:
        registry = domain_registry()

        async def native(operation_id, *, path_args=None, query=None, body=None):
            if not operation_id.startswith('GET ') or registry.spec_for_operation(operation_id) is None:
                _invalid()
            reader = native_reader_for_principal(db, principal, (operation_id,), client_factory=client_factory)
            return await reader(operation_id, path_args=path_args, query=query, body=body)

        snapshot = await read_object(principal, ref, native_reader=native, registry=registry)
        if event['task_id'] is not None and not any(
                task.id == event['task_id'] and task.case_id == ref['id'] for task in snapshot.tasks):
            raise HTTPException(404, '原任务不在当前可读原单中')
    revalidate_principal(db, principal)


async def _matching_dispatch_principal(db, event, facts, grant_id, plan_id, goal, *,
                                       clock, read_session_factory, client_factory):
    from .assistant_runtime_principal import _reader, principal_for_grant_probe, revalidate_principal
    from .assistant_runtime_queue import _scope
    from .business_assistant_models import AssistantWorkPlan
    try:
        principal = principal_for_grant_probe(db, grant_id, clock=clock, read_session_factory=read_session_factory)
        if (principal.plan_id != plan_id or principal.goal_version != goal
                or facts['role'] is not None and principal.role != facts['role']
                or facts['access_version'] is not None and principal.access_version != facts['access_version']):
            return None
        with _reader(db, read_session_factory) as reader:
            _scope(reader, principal.store_id)
            plan = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
                AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id,
                AssistantWorkPlan.session_id == principal.session_id, AssistantWorkPlan.status == 'active',
                AssistantWorkPlan.engine_version == 2, AssistantWorkPlan.goal_version == principal.goal_version))
            if plan is None:
                _conflict()
            if _matches_plan(reader, event, facts, plan, principal) is None:
                return None
        await _authorize_native_source(db, principal, event, client_factory=client_factory)
        revalidate_principal(db, principal, clock=clock)
    except HTTPException as exc:
        if exc.status_code in {401, 403, 404}:
            return None
        raise
    return principal


async def _resolve_dispatch(db, event, *, clock, read_session_factory, client_factory):
    from .assistant_runtime_plans import resolve_followup_check
    from .assistant_runtime_principal import _reader, principal_for_grant_probe
    from .assistant_runtime_queue import resolve_followup_runs
    from .assistant_runtime_receipts import reconcile_plan_confirmations
    from .business_assistant_models import AssistantWorkPlan
    with _reader(db, read_session_factory) as reader:
        facts = _source_facts(reader, event)
        targets = []
        for grant in reader.scalars(select(FollowupGrant).where(FollowupGrant.store_id == event['store_id'],
                FollowupGrant.status == 'active', FollowupGrant.revoked_at.is_(None)).order_by(FollowupGrant.id)):
            if (facts['grant_id'] is not None and facts['grant_id'] != grant.id
                    or facts['goal_version'] is not None and facts['goal_version'] != grant.goal_version):
                continue
            plan = reader.execute(select(AssistantWorkPlan.id, AssistantWorkPlan.owner_id,
                AssistantWorkPlan.session_id, AssistantWorkPlan.goal_version).where(AssistantWorkPlan.id == grant.plan_id,
                AssistantWorkPlan.owner_id == grant.owner_id, AssistantWorkPlan.store_id == grant.store_id,
                AssistantWorkPlan.session_id == grant.session_id, AssistantWorkPlan.status == 'active',
                AssistantWorkPlan.engine_version == 2, AssistantWorkPlan.goal_version == grant.goal_version)).first()
            if plan is None:
                continue
            if (facts['owner_id'] is not None and plan.owner_id != facts['owner_id']
                    or facts['session_id'] is not None and plan.session_id != facts['session_id']):
                continue
            targets.append((grant.id, grant.version, plan.id, plan.goal_version, grant.store_id))
    # Finish independent invalid-authority cleanup before resolving any proof.
    # Cleanup may advance a shared Session version, so a later valid Plan must
    # not retain a snapshot taken before that control transaction.
    valid = []
    for grant_id, version, plan_id, goal, store_id in targets:
        try:
            principal_for_grant_probe(db, grant_id, clock=clock, read_session_factory=read_session_factory)
        except HTTPException as exc:
            if exc.status_code not in {401, 403}:
                raise
            _cleanup_invalid_grant(db, grant_id, version, store_id, clock=clock,
                                   read_session_factory=read_session_factory)
            continue
        valid.append((grant_id, plan_id, goal))
    coordinated = []
    for grant_id, plan_id, goal in valid:
        principal = await _matching_dispatch_principal(db, event, facts, grant_id, plan_id, goal,
            clock=clock, read_session_factory=read_session_factory, client_factory=client_factory)
        if principal is None:
            continue
        # This fixed service may repair existing confirmation records in its
        # own short transaction. Never coordinate unrelated signal targets.
        await reconcile_plan_confirmations(db, principal, clock=clock, client_factory=client_factory)
        db.rollback()
        coordinated.append((grant_id, plan_id, goal))
    # Complete every candidate's reconciliation before issuing the first
    # condition proof: two Plans may share the same Session version.
    checks = []
    for grant_id, plan_id, goal in coordinated:
        principal = await _matching_dispatch_principal(db, event, facts, grant_id, plan_id, goal,
            clock=clock, read_session_factory=read_session_factory, client_factory=client_factory)
        if principal is None:
            continue
        checks.append(await resolve_followup_check(db, principal, clock=clock,
                                                   client_factory=client_factory))
    # The plans proof binds all source rows. Its fixed batch persist verifies
    # that snapshot before applying results; checking old versions afterwards
    # would conflict with this transaction's own legitimate progress updates.
    return resolve_followup_runs(db, tuple(checks), clock=clock,
                                 read_session_factory=read_session_factory)


def _cleanup_invalid_grant(db, grant_id, version, store_id, *, clock, read_session_factory):
    """Separate control TX; the original helper independently proves invalidity."""
    from .assistant_runtime_plans import invalidate_followup_grant
    from .assistant_runtime_principal import _reader
    from .assistant_runtime_queue import _scope
    with _reader(db, read_session_factory) as control:
        _scope(control, store_id)
        return invalidate_followup_grant(control, grant_id, version, clock=clock,
                                         read_session_factory=read_session_factory)


def _event_cas(db, event, *, state, now):
    """Per-row pending CAS, never a high-water ID or a destructive cursor."""
    table = WakeEvent.__table__
    values = {'version': event['version'] + 1, 'attempt': event['attempt'] + 1,
              'state': state, 'dispatched_at': now if state == 'dispatched' else None}
    if state == 'pending':
        values['next_attempt_at'] = now + timedelta(seconds=_DISPATCH_DELAYS[min(event['attempt'], len(_DISPATCH_DELAYS) - 1)])
    elif state != 'dispatched':
        raise ValueError('Unknown dispatch state')
    result = db.connection().execute(table.update().where(table.c.id == event['id'],
        table.c.store_id == event['store_id'], table.c.version == event['version'],
        table.c.state == 'pending', table.c.attempt == event['attempt'],
        table.c.next_attempt_at == event['next_attempt_at'], table.c.next_attempt_at <= now).values(**values))
    if result.rowcount != 1:
        _conflict()
    return values['attempt']


def _dispatch_modes():
    from .config import settings
    # Notifications remain independent when Runtime execution is switched off.
    # Only the followup branch may obtain a Grant probe or create a Run.
    modes = (settings.assistant_runtime_enabled and settings.assistant_followup_enabled,
             settings.assistant_notifications_enabled)
    if not any(modes):
        raise HTTPException(503, '跟进和提醒分发服务尚未开启')
    return modes


async def dispatch_one(db, *, clock=utcnow, read_session_factory=None, client_factory=None):
    """Handle one due event using a fresh Session; no periodic worker here.

    All original GETs finish before the queue write transaction. All selected
    Run inserts, private notifications and the one dispatched CAS commit
    together. Failure rolls them all back and separately defers this still-
    pending event; later smaller IDs remain independently eligible. Returned
    values contain no private content.
    """
    from .assistant_runtime_principal import _reader, _time
    from .assistant_runtime_queue import (_fresh_worker_session, _scope, _commit, _failure,
        persist_followup_runs, validate_followup_resolution, _sqlite_writer)
    from .assistant_runtime_workspace import (
        resolve_event_notifications, persist_event_notifications, validate_event_notifications,
    )
    modes = _dispatch_modes()
    _fresh_worker_session(db)
    with _reader(db, read_session_factory) as reader:
        row = reader.scalar(select(WakeEvent).where(WakeEvent.state == 'pending',
            WakeEvent.next_attempt_at <= _time(clock())).order_by(
            WakeEvent.next_attempt_at, WakeEvent.created_at, WakeEvent.id).limit(1))
        event = _event_snapshot(row) if row is not None else None
    if event is None:
        return None
    try:
        # Confirmation recovery may commit source repairs; finish all such
        # followup work before freezing the independent notification proof.
        resolved = (await _resolve_dispatch(db, event, clock=clock,
            read_session_factory=read_session_factory, client_factory=client_factory)) if modes[0] else None
        notification = (await resolve_event_notifications(db, event, clock=clock,
            read_session_factory=read_session_factory, client_factory=client_factory)) if modes[1] else None
        db.rollback()  # Native reads must not leave an old database snapshot.
        _sqlite_writer(db)
        _scope(db, event['store_id'])
        if _dispatch_modes() != modes:
            raise HTTPException(503, '提醒或跟进配置已变化，请稍后重新分发')
        handles = persist_followup_runs(db, resolved, clock=clock) if modes[0] else ()
        if modes[1]:
            persist_event_notifications(db, notification, clock=clock)
        attempt = _event_cas(db, event, state='dispatched', now=_time(clock()))
        if modes[0]:
            validate_followup_resolution(db, resolved, clock=clock)
        if modes[1]:
            validate_event_notifications(db, notification, clock=clock)
        if _dispatch_modes() != modes:
            raise HTTPException(503, '提醒或跟进配置已变化，请稍后重新分发')
        _commit(db)
        return DispatchResult(event['id'], 'dispatched', attempt, tuple(handle.id for handle in handles))
    except Exception as exc:
        db.rollback()
        # Neither dispatch failure nor failure to schedule a retry changes the
        # already-committed native business outcome. CAS cannot resurrect an
        # event dispatched by a concurrent worker.
        try:
            _sqlite_writer(db)
            _scope(db, event['store_id'])
            attempt = _event_cas(db, event, state='pending', now=_time(clock()))
            _commit(db)
        except Exception as retry_exc:
            db.rollback()
            _failure(db, retry_exc)
        return DispatchResult(event['id'], 'pending', attempt)


def _due_plan(reader, now, *, expected=None):
    """Only routing/control columns; private Plan content needs a real probe."""
    from .business_assistant_models import AssistantWorkPlan
    plan, grant = AssistantWorkPlan, FollowupGrant
    query = select(grant.id.label('grant_id'), grant.version.label('grant_version'),
        grant.owner_id, grant.store_id, grant.session_id, grant.plan_id, grant.goal_version,
        plan.version.label('plan_version'), plan.next_check_at).join(plan, and_(
            plan.id == grant.plan_id, plan.owner_id == grant.owner_id,
            plan.store_id == grant.store_id, plan.session_id == grant.session_id,
            plan.goal_version == grant.goal_version)).where(
        grant.status == 'active', grant.revoked_at.is_(None),
        plan.engine_version == 2, plan.status == 'active')
    if expected is None:
        query = query.where(or_(plan.next_check_at.is_(None), plan.next_check_at <= now))
    else:
        # After reconciliation, refresh this exact control source only. A new
        # goal/Grant must not inherit the old check or its retry write.
        query = query.where(grant.id == expected['grant_id'], grant.version == expected['grant_version'],
            grant.owner_id == expected['owner_id'], grant.store_id == expected['store_id'],
            grant.session_id == expected['session_id'], grant.plan_id == expected['plan_id'],
            grant.goal_version == expected['goal_version'])
    row = reader.execute(query.order_by(plan.next_check_at.asc().nulls_first(),
        plan.created_at, plan.id).limit(1)).mappings().first()
    return dict(row) if row is not None else None


def _defer_due_plan(db, seed, *, clock, read_session_factory):
    """Retry metadata only; no Step evidence, status, or private content writes."""
    from .assistant_runtime_principal import _enabled, _time, principal_for_grant_probe, revalidate_principal
    from .assistant_runtime_queue import _scope, _version_cas, _commit, _sqlite_writer
    from .business_assistant_models import AssistantSession, AssistantWorkPlan
    principal = principal_for_grant_probe(db, seed['grant_id'], clock=clock,
                                         read_session_factory=read_session_factory)
    if (principal.actor_id, principal.store_id, principal.session_id, principal.plan_id,
            principal.goal_version, principal._probe_grant_version) != (
            seed['owner_id'], seed['store_id'], seed['session_id'], seed['plan_id'],
            seed['goal_version'], seed['grant_version']):
        _conflict()
    _sqlite_writer(db)
    _scope(db, seed['store_id'])
    table = AssistantWorkPlan.__table__
    grant_table = FollowupGrant.__table__
    with db.no_autoflush:
        thread = db.scalar(select(AssistantSession).where(
            AssistantSession.id == seed['session_id'], AssistantSession.owner_id == seed['owner_id'],
            AssistantSession.store_id == seed['store_id']).with_for_update()
            .execution_options(populate_existing=True))
        if thread is None or (thread.owner_role, thread.access_version) != (principal.role, principal.access_version):
            _conflict()
        plan = db.execute(select(table.c.version, table.c.goal_version, table.c.status,
            table.c.engine_version, table.c.next_check_at).where(table.c.id == seed['plan_id'],
            table.c.owner_id == seed['owner_id'], table.c.store_id == seed['store_id'],
            table.c.session_id == seed['session_id']).with_for_update()).mappings().first()
        grant = db.execute(select(grant_table.c.version, grant_table.c.status, grant_table.c.revoked_at)
            .where(grant_table.c.id == seed['grant_id'], grant_table.c.owner_id == seed['owner_id'],
                grant_table.c.store_id == seed['store_id'], grant_table.c.session_id == seed['session_id'],
                grant_table.c.plan_id == seed['plan_id'], grant_table.c.goal_version == seed['goal_version'])
            .with_for_update()).mappings().first()
        if (plan is None or grant is None
                or (plan['version'], plan['goal_version'], plan['status'], plan['engine_version'], plan['next_check_at'])
                    != (seed['plan_version'], seed['goal_version'], 'active', 2, seed['next_check_at'])
                or (grant['version'], grant['status'], grant['revoked_at']) != (seed['grant_version'], 'active', None)):
            _conflict()
        now = _time(clock())
        _version_cas(db, thread, {'updated_at': now})
        changed = db.connection().execute(table.update().where(
            table.c.id == seed['plan_id'], table.c.owner_id == seed['owner_id'],
            table.c.store_id == seed['store_id'], table.c.session_id == seed['session_id'],
            table.c.engine_version == 2, table.c.status == 'active',
            table.c.goal_version == seed['goal_version'], table.c.version == seed['plan_version'],
            table.c.next_check_at == seed['next_check_at']).values(
                version=seed['plan_version'] + 1, updated_at=now,
                next_check_at=now + timedelta(seconds=_POLL_RETRY_SECONDS)))
        if changed.rowcount != 1:
            _conflict()
    revalidate_principal(db, principal, clock=clock)
    _enabled('grant')
    _commit(db)


async def poll_due_plan(db, *, clock=utcnow, read_session_factory=None, client_factory=None):
    """Check one explicitly granted due Plan, without starting a worker/model.

    The worker supplies a fresh Session per call at CHECK_INTERVAL_SECONDS.
    Normal five-minute checks and earlier future due conditions are scheduled
    by the same complete plans proof used by event dispatch. One Plan is a
    scheduling unit: its full Steps and input rows are never truncated.
    """
    from .assistant_runtime_plans import resolve_followup_check
    from .assistant_runtime_principal import _enabled, _reader, _time, principal_for_grant_probe
    from .assistant_runtime_receipts import reconcile_plan_confirmations
    from .assistant_runtime_queue import (_fresh_worker_session, _scope, _commit, _failure,
        resolve_followup_runs, persist_followup_runs, validate_followup_resolution, _sqlite_writer)
    _enabled('grant')
    _fresh_worker_session(db)
    with _reader(db, read_session_factory) as reader:
        seed = _due_plan(reader, _time(clock()))
    if seed is None:
        return None
    try:
        try:
            principal = principal_for_grant_probe(db, seed['grant_id'], clock=clock,
                                                 read_session_factory=read_session_factory)
        except HTTPException as exc:
            if exc.status_code not in {401, 403}:
                raise
            _cleanup_invalid_grant(db, seed['grant_id'], seed['grant_version'], seed['store_id'],
                                   clock=clock, read_session_factory=read_session_factory)
            return PollResult(seed['plan_id'], 'invalidated')
        await reconcile_plan_confirmations(db, principal, clock=clock, client_factory=client_factory)
        db.rollback()
        with _reader(db, read_session_factory) as reader:
            current = _due_plan(reader, _time(clock()), expected=seed)
        if current is None:
            _conflict()
        seed = current
        principal = principal_for_grant_probe(db, seed['grant_id'], clock=clock,
                                             read_session_factory=read_session_factory)
        check = await resolve_followup_check(db, principal, clock=clock, client_factory=client_factory)
        resolved = resolve_followup_runs(db, (check,), clock=clock, read_session_factory=read_session_factory)
        db.rollback()
        _sqlite_writer(db)
        _scope(db, seed['store_id'])
        handles = persist_followup_runs(db, resolved, clock=clock)
        validate_followup_resolution(db, resolved, clock=clock)
        _enabled('grant')
        _commit(db)
        return PollResult(seed['plan_id'], 'checked', tuple(handle.id for handle in handles))
    except Exception:
        db.rollback()
        # A transient GET/condition failure must not revoke a valid Grant. Only
        # fresh control authority can defer its unchanged due snapshot. If that
        # check also fails, report the error instead of inventing a retry write.
        try:
            _defer_due_plan(db, seed, clock=clock, read_session_factory=read_session_factory)
        except Exception as retry_exc:
            db.rollback()
            _failure(db, retry_exc)
        return PollResult(seed['plan_id'], 'deferred')
