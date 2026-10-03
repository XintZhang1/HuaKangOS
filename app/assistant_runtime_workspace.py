"""Read-only employee workspace assembled from original authorized facts.

Native counts are mine/open tasks, not completed-task history. Finished entries
are the employee's ended assistant cards/plans. Aggregate mode exposes original
tasks only and retains every original aggregate exclusion; private conversations
are never pooled across stores. No task/card association is guessed from a Case.
"""
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from hashlib import sha256
import hmac
import json
from time import monotonic
from uuid import uuid4
from weakref import WeakKeyDictionary
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from .assistant_runtime_labels import waiting_label
from .assistant_runtime_principal import _reader, _login, _time
from .assistant_runtime_schemas import BusinessObjectRef, WorkspaceItem, WorkspaceQuery, WorkspaceView
from .business_assistant_models import AssistantProposal, AssistantSession, AssistantWorkPlan
from .config import settings
from .db import utcnow
from .models import User
from .tenancy import RequestPrincipal, SUMMARY_ROLES, accessible_stores, role_for_store, set_scope


_GROUPS = ('attention', 'following', 'finished')
_LABELS = {'pending': '待你确认', 'awaiting_confirmation': '待你确认',
    'needs_input': '请补充资料', 'executing': '正在办理，请勿重复提交',
    'uncertain': '结果待核对', 'failed': '办理未完成', 'succeeded': '原操作已办理',
    'expired': '草稿已过期', 'cancelled': '已停止', 'active': '等待后续条件',
    'paused': '已暂停跟进', 'completed': '事项已结束', 'open': '我的待办'}
_INPUT_REASONS = {'employee_input', 'completion_conditions_missing', 'completion_evidence_missing',
                  'explicit_time_missing', 'time_source_missing', 'source_inaccessible'}


@dataclass(frozen=True)
class _Identity:
    actor_id: int
    role: str
    account_role: str
    access_version: int
    store_id: int | None
    aggregate: bool
    store_roles: tuple
    login_ref: str = field(repr=False)
    bind: object = field(repr=False, compare=False)


def _unavailable():
    raise HTTPException(503, '事项列表暂时不可用，请稍后重新读取')


def _changed():
    raise HTTPException(409, '事项或可见范围已变化，请刷新列表后继续查看')


def _capture(db, request, user):
    from .business_assistant_service import require_preparation_read_phase
    if '_huakang_runtime' in request.scope:
        raise HTTPException(403, '请由员工本人打开事项列表')
    aggregate = getattr(user, '_aggregate_scope', False)
    store_id = getattr(user, '_active_store_id', None)
    scope = db.info.get('store_scope')
    if (type(scope) not in (tuple, list) or type(aggregate) is not bool
            or any(type(value) is not int or value < 0 for value in scope)):
        raise HTTPException(403, '请使用原登录选择可查看的门店')
    stores = tuple(sorted(value for value in scope if type(value) is int and value > 0))
    roles = {value['id']: value['role'] for value in getattr(user, '_stores', ())}
    if (not stores or len(set(stores)) != len(stores)
            or aggregate != bool(db.info.get('aggregate_scope'))
            or aggregate and (store_id is not None or db.info.get('write_store') is not None
                or set(stores) != set(getattr(user, '_group_store_ids', ())))
            or not aggregate and (stores != (store_id,) or db.info.get('write_store') != store_id)
            or any(store not in roles for store in stores)):
        raise HTTPException(403, '当前门店范围无效，请重新选择')
    identity = _Identity(user.id, user.role, user.account_role, user.access_version, store_id,
        aggregate, tuple((store, roles[store]) for store in stores),
        getattr(request.state, 'session_hash', None), db.get_bind())
    require_preparation_read_phase(db)
    db.rollback()
    return identity


def _account(reader, identity):
    """Revalidate current login plus every frozen store membership, no Session needed."""
    _login(reader, identity.login_ref, identity.actor_id, _time(utcnow()))
    account = reader.scalar(select(User).where(User.id == identity.actor_id))
    if (account is None or not account.active or account.must_change_password
            or account.access_version != identity.access_version or account.role != identity.account_role):
        raise HTTPException(403, '员工或门店权限已变化，请重新登录')
    available = {store.id: role_for_store(reader, account, store.id) for store in accessible_stores(reader, account)}
    if identity.aggregate:
        current = tuple(sorted((store, role) for store, role in available.items() if role in SUMMARY_ROLES))
        if (identity.role != 'auditor' or not (account.role == 'admin' or account.can_group_summary)
                or current != identity.store_roles):
            raise HTTPException(403, '集团汇总范围已变化，请重新选择门店')
    elif (identity.store_roles != ((identity.store_id, identity.role),)
          or available.get(identity.store_id) != identity.role):
        raise HTTPException(403, '当前门店岗位已变化，请重新选择门店')
    return account


@contextmanager
def _reading(db, identity):
    if db.get_bind() is not identity.bind:
        raise HTTPException(403, '登录来源与当前数据库不一致')
    with _reader(db) as reader:
        account = _account(reader, identity)
        set_scope(reader, [store for store, _ in identity.store_roles], identity.store_id)
        reader.info['aggregate_scope'] = identity.aggregate
        yield reader, account


def _guard(db, identity):
    with _reading(db, identity):
        pass


def _login_read(identity, session_id):
    from .assistant_runtime_api import _LoginRead
    if identity.aggregate or identity.store_id is None:
        raise HTTPException(403, '请在具体门店查看本人事项')
    return _LoginRead(identity.actor_id, identity.store_id, identity.role, identity.access_version,
                      session_id, identity.login_ref, identity.bind)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode('utf-8')).hexdigest()


def _scope_key(identity):
    # Cursor holds a one-way binding, never the login hash or another store's IDs.
    return _hash({'actor': identity.actor_id, 'access': identity.access_version,
        'role': identity.role, 'stores': identity.store_roles, 'aggregate': identity.aggregate,
        'login': identity.login_ref})


def _due(value):
    # Task.due_date is an original business date, not an employee-authorized
    # followup deadline. Only the display DTO gets local midnight converted UTC.
    return datetime.combine(value, time.min, tzinfo=ZoneInfo(settings.timezone))


def _entry(item, group, rank, *, version):
    item.setdefault('waiting_label', waiting_label(item.get('waiting_reason')))
    item = WorkspaceItem.model_validate(item)
    when = _time(item.updated_at)
    micros = ((when - datetime(1970, 1, 1)).days * 86400000000
              + (when - datetime(1970, 1, 1)).seconds * 1000000 + when.microsecond)
    due = _time(item.due_at).isoformat(timespec='microseconds') if item.due_at else '9999'
    return {'item': item, 'group': group, 'sort': (rank, due, -micros, item.key), 'version': version}


def _tasks(db, identity):
    from . import flow_engine as eng
    from .flow_api import task_info
    from .flow_models import Case, Task
    from .assistant_runtime_api import _text
    result = {}
    with _reading(db, identity) as (reader, account):
        original = RequestPrincipal(account, identity.role, _aggregate_scope=identity.aggregate,
            _active_store_id=identity.store_id)
        # Exactly the original default task scope, before any page or count.
        query = select(Task).where(Task.status == 'open', Task.assignee_id == identity.actor_id,
            Task.case_id.in_(eng.case_query(original).with_only_columns(Case.id)))
        roles = dict(identity.store_roles)
        for task in reader.scalars(query.order_by(Task.id)):
            row = eng.scoped_get(reader, Case, task.case_id)
            if row is None or row.store_id != task.store_id or task.store_id not in roles:
                continue
            if not eng.can_read(reader, original, row):
                continue
            if identity.aggregate:
                # Keep aggregate exclusions and add actual per-store role checks;
                # never masquerade as a normal single-store request/admin.
                local = RequestPrincipal(account, roles[task.store_id], _aggregate_scope=True,
                    _active_store_id=None)
                if (reader.scalar(eng.case_query(local).where(Case.id == row.id).with_only_columns(Case.id)) is None
                        or not eng.can_read(reader, local, row)):
                    continue
            data = task_info(reader, original, task, row)
            item = {'key': f'task:{task.id}', 'kind': 'native_task', 'task_id': task.id,
                'object_ref': {'type': 'case', 'id': row.id}, 'title': _text(data['title'], 160),
                'status': 'open', 'status_label': '我的逾期待办' if data['overdue'] else '我的待办',
                'waiting_reason': 'native_prerequisite' if data['blocked'] else None,
                'due_at': _due(task.due_date), 'manual_route': data['entry_route'],
                'allowed_actions': ['open'], 'updated_at': task.updated_at}
            result[task.id] = _entry(item, 'attention', 2 if data['overdue'] else 3,
                                    version=[task.version, row.version])
    return list(result.values())


def _private_sources(db, identity):
    from .assistant_runtime_models import WorkItem, RunItem, Run, PlanStep, FollowupGrant
    from .assistant_runtime_plans import _card_objects, project_legacy_plan
    from .assistant_runtime_runner import _card_status
    result, plans = [], []
    with _reading(db, identity) as (reader, _):
        predicates = (AssistantSession.owner_id == identity.actor_id,
            AssistantSession.store_id == identity.store_id, AssistantSession.owner_role == identity.role,
            AssistantSession.access_version == identity.access_version)
        cards = reader.scalars(select(AssistantProposal).join(AssistantSession,
            AssistantSession.id == AssistantProposal.session_id).where(*predicates,
            AssistantProposal.owner_id == identity.actor_id, AssistantProposal.store_id == identity.store_id,
            AssistantProposal.owner_role == identity.role, AssistantProposal.access_version == identity.access_version)
            .order_by(AssistantProposal.id))
        for card in cards:
            work = reader.get(WorkItem, card.source_work_item_id) if card.source_work_item_id else None
            if card.source_work_item_id and (work is None or (work.owner_id, work.store_id, work.session_id)
                    != (identity.actor_id, identity.store_id, card.session_id)
                    or work.item_kind != 'prepare' or work.operation_id != card.operation_id):
                _changed()
            if work is not None and work.plan_id is not None:
                linked = reader.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == work.plan_id,
                    AssistantWorkPlan.owner_id == identity.actor_id, AssistantWorkPlan.store_id == identity.store_id,
                    AssistantWorkPlan.session_id == card.session_id))
                if linked is None:
                    _changed()
            refs = list(_card_objects(card))
            confirmation_versions = []
            if work is not None:
                confirmations = reader.scalars(select(RunItem).where(RunItem.kind == 'confirmation',
                    RunItem.proposal_id == card.id, RunItem.work_item_id == work.id, RunItem.status == 'succeeded')
                    .order_by(RunItem.id))
                for confirmation in confirmations:
                    confirmation_versions.append((confirmation.id, confirmation.version))
                    for value in confirmation.result_refs or []:
                        ref = BusinessObjectRef.model_validate(value).model_dump(mode='json')
                        if ref not in refs:
                            refs.append(ref)
            result.append({'id': card.id, 'session_id': card.session_id,
                'plan_id': work.plan_id if work else None, 'status': _card_status(card),
                'label': card.label, 'questions': bool(card.questions), 'refs': refs, 'version': card.version,
                'work_version': work.version if work is not None else None,
                'confirmation_versions': sorted(confirmation_versions),
                'updated_at': card.finished_at or card.started_at or card.created_at})
        for plan in reader.scalars(select(AssistantWorkPlan).join(AssistantSession,
                AssistantSession.id == AssistantWorkPlan.session_id).where(*predicates,
                AssistantWorkPlan.owner_id == identity.actor_id, AssistantWorkPlan.store_id == identity.store_id)
                .order_by(AssistantWorkPlan.id)):
            # These are source revision guards, not completion evidence. Include
            # accepted rows without cards, and avoid ordinary Run heartbeats.
            steps = list(reader.execute(select(PlanStep.id, PlanStep.version)
                .where(PlanStep.plan_id == plan.id).order_by(PlanStep.id)))
            works = list(reader.execute(select(WorkItem.id, WorkItem.version).where(
                WorkItem.plan_id == plan.id, WorkItem.owner_id == identity.actor_id,
                WorkItem.store_id == identity.store_id, WorkItem.session_id == plan.session_id)
                .order_by(WorkItem.id)))
            grants = list(reader.execute(select(FollowupGrant.id, FollowupGrant.version).where(
                FollowupGrant.plan_id == plan.id, FollowupGrant.owner_id == identity.actor_id,
                FollowupGrant.store_id == identity.store_id, FollowupGrant.session_id == plan.session_id)
                .order_by(FollowupGrant.id)))
            items = list(reader.execute(select(RunItem.id, RunItem.version).join(Run, Run.id == RunItem.run_id)
                .where(Run.owner_id == identity.actor_id, Run.store_id == identity.store_id,
                    Run.session_id == plan.session_id,
                    ((RunItem.work_item_id.in_([value[0] for value in works]))
                     | ((RunItem.tool_name == 'prepare_inputs')
                        & (RunItem.validated_arguments['scope']['plan_id'].as_string() == plan.id))))
                .order_by(RunItem.id)))
            projection = project_legacy_plan(reader, _login_read(identity, plan.session_id), plan.session_id, plan)
            blocker, run_facts = _plan_notice_blocker(reader, _NoticeActor(identity.actor_id, identity.store_id,
                identity.role, identity.account_role, identity.access_version), plan)
            refs = []
            for step in projection['steps']:
                value = step.get('object_ref')
                if value is None and type(step.get('case_id')) is int and step['case_id'] > 0:
                    value = {'type': 'case', 'id': step['case_id']}
                if value is not None:
                    ref = BusinessObjectRef.model_validate(value).model_dump(mode='json')
                    if ref not in refs:
                        refs.append(ref)
            plans.append({'id': plan.id, 'session_id': plan.session_id, 'updated_at': plan.updated_at,
                'version': plan.version, 'steps': [tuple(value) for value in steps],
                'works': [tuple(value) for value in works], 'grants': [tuple(value) for value in grants],
                'items': [tuple(value) for value in items], 'refs': refs, 'projection': projection,
                'blocker': blocker, 'run_facts': run_facts})
    return result, plans


async def _cards(db, request, identity, sources):
    from .assistant_runtime_api import _native_reader, _visible_object, _text
    entries, pending = [], 0
    for card in sources:
        auth = _login_read(identity, card['session_id'])
        native = _native_reader(db, request, auth, auth)
        objects = []
        for value in card['refs']:
            snapshot = await _visible_object(db, auth, native, value, strict_sources=True)
            if snapshot is None:
                break
            objects.append(snapshot)
        if len(objects) != len(card['refs']):
            continue
        status = card['status']
        if status == 'pending':
            pending += 1
            state = 'needs_input' if card['questions'] else 'pending'
            group, rank = 'attention', 1
        elif status in {'executing', 'uncertain', 'failed'}:
            state, group, rank = status, 'attention', 0
        else:
            state, group, rank = status, 'finished', 5
        obj = objects[0] if len(objects) == 1 else None
        entries.append(_entry({'key': 'proposal:' + card['id'], 'kind': 'proposal',
            'session_id': card['session_id'], 'plan_id': card['plan_id'], 'proposal_id': card['id'],
            'object_ref': obj.ref.model_dump(mode='json') if obj else None,
            'title': _text(card['label'], 160) or '待核对业务卡', 'status': state,
            'status_label': _LABELS.get(state, '请核对原卡'),
            'waiting_reason': 'employee_input' if state == 'needs_input'
                else 'result_unknown' if state in {'executing', 'uncertain'} else None,
            'manual_route': obj.manual_route if obj else None,
            # The sidebar is an entry point. Original card UI performs the
            # actual fill/confirmation/cancellation permission checks.
            'allowed_actions': ['open'], 'updated_at': card['updated_at']},
            group, rank, version=card['version']))
    return entries, pending


async def _plans(db, request, identity, sources):
    from .assistant_runtime_api import shared_plan_view, _native_reader, _visible_object
    entries = []
    for source in sources:
        auth = _login_read(identity, source['session_id'])
        native = _native_reader(db, request, auth, auth)
        visible = True
        for ref in source['refs']:
            if await _visible_object(db, auth, native, ref, strict_sources=True) is None:
                visible = False
                break
        if not visible:
            continue
        view = await shared_plan_view(db, request, auth, auth, source['id'], strict_sources=True)
        if any(step.wait_reason == 'source_inaccessible' for step in view.steps):
            # An inaccessible business relationship is not a missing or
            # completed business fact. Leave it in the private chat only.
            continue
        if view.status in {'completed', 'cancelled'}:
            state, group, rank, reason = view.status, 'finished', 5, None
        else:
            abnormal = next((step for step in view.steps if step.status in {'failed', 'uncertain'}), None)
            needed = next((step for step in view.steps if step.status in {'needs_input', 'awaiting_confirmation'}
                           or step.wait_reason in _INPUT_REASONS), None)
            blocker = source['blocker']
            if blocker is not None:
                state, group, rank, reason = blocker['state'], 'attention', 0 if blocker['state'] == 'failed' else 1, blocker['reason']
            elif abnormal is not None:
                state, group, rank, reason = abnormal.status, 'attention', 0, abnormal.wait_reason
            elif needed is not None:
                state = 'awaiting_confirmation' if needed.status == 'awaiting_confirmation' else 'needs_input'
                group, rank, reason = 'attention', 1, needed.wait_reason
            else:
                state, group, rank = view.status, 'following', 4
                reason = ('employee_paused' if state == 'paused' else
                          'external_fact' if view.grant.enabled else 'employee_continue')
        objects = {(step.object_ref.type, step.object_ref.id): step for step in view.steps if step.object_ref}
        only = next(iter(objects.values())) if len(objects) == 1 else None
        entries.append(_entry({'key': 'plan:' + view.id, 'kind': 'plan', 'plan_id': view.id,
            'session_id': view.session_id, 'object_ref': only.object_ref if only else None,
            'title': view.goal, 'status': state,
            'status_label': '待你继续' if reason == 'employee_continue' else _LABELS.get(state, '请核对事项'),
            'waiting_reason': reason, 'manual_route': only.manual_route if only else None,
            'allowed_actions': ['open', *view.allowed_actions], 'updated_at': source['updated_at']},
            group, rank, version=[view.version, view.goal_version, view.grant.model_dump(mode='json')]))
    return entries


def _cursor(identity, group, limit, fingerprint, entry):
    data = {'v': 1, 'scope': _scope_key(identity), 'group': group, 'limit': limit,
            'facts': fingerprint, 'after': list(entry['sort'])}
    return urlsafe_b64encode(_json(data).encode('utf-8')).decode('ascii').rstrip('=')


def _position(identity, query, fingerprint, entries):
    if query.cursor is None:
        return 0
    if query.group is None or not query.cursor or len(query.cursor) > 4096:
        raise HTTPException(422, '翻页须提供分组及完整游标')
    try:
        raw = urlsafe_b64decode(query.cursor + '=' * (-len(query.cursor) % 4))
        data = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError):
        raise HTTPException(422, '事项游标无效') from None
    if (type(data) is not dict or set(data) != {'v', 'scope', 'group', 'limit', 'facts', 'after'}
            or type(data['v']) is not int or data['v'] != 1 or type(data['limit']) is not int
            or data['scope'] != _scope_key(identity) or data['group'] != query.group
            or data['limit'] != query.limit):
        raise HTTPException(422, '事项游标与当前身份、门店或分组不匹配')
    if data['facts'] != fingerprint:
        _changed()
    for index, entry in enumerate(entries):
        if list(entry['sort']) == data['after']:
            return index + 1
    _changed()


async def read_workspace(db, request, user, query: WorkspaceQuery) -> WorkspaceView:
    """Filter complete real sources first, then count, group and page them."""
    try:
        query = WorkspaceQuery.model_validate(query.model_dump() if isinstance(query, WorkspaceQuery) else query)
    except ValidationError:
        raise HTTPException(422, '请核对事项分组、数量和游标') from None
    identity = _capture(db, request, user)
    try:
        _guard(db, identity)
        native = _tasks(db, identity)
        entries, pending = list(native), 0
        if not identity.aggregate:
            card_sources, plan_sources = _private_sources(db, identity)
            cards, pending = await _cards(db, request, identity, card_sources)
            entries.extend(cards)
            entries.extend(await _plans(db, request, identity, plan_sources))
        # No reader survives an await. Rebuild the same original authorized
        # Task dataset and private source revisions after all native reads;
        # reassignment, status/permission or row changes invalidate this page.
        latest_tasks = _tasks(db, identity)
        task_signature = lambda values: [(value['item'].model_dump(mode='json'), value['version'])
                                         for value in values]
        if task_signature(native) != task_signature(latest_tasks):
            _changed()
        if not identity.aggregate and (card_sources, plan_sources) != _private_sources(db, identity):
            _changed()
        # The only native deduplication is Task.id above. Case/title/condition
        # references are not evidence that a proposal replaces a task.
        groups = {group: sorted((value for value in entries if value['group'] == group),
                                key=lambda value: value['sort']) for group in _GROUPS}
        fingerprint = _hash([{'group': value['group'], 'sort': value['sort'], 'version': value['version'],
            'item': value['item'].model_dump(mode='json')}
            for value in sorted(entries, key=lambda value: value['item'].key)])
        result_groups = []
        for group in (query.group,) if query.group else _GROUPS:
            values = groups[group]
            start = _position(identity, query, fingerprint, values)
            page = values[start:start + query.limit]
            more = start + len(page) < len(values)
            result_groups.append({'key': group, 'items': [entry['item'] for entry in page],
                'next_cursor': _cursor(identity, group, query.limit, fingerprint, page[-1]) if more else None})
        result = WorkspaceView.model_validate({'features': {
            'home': settings.assistant_home_enabled, 'runtime': settings.assistant_runtime_enabled,
            'followup': settings.assistant_followup_enabled, 'notifications': settings.assistant_notifications_enabled},
            'counts': {'native_tasks': len(native), 'pending_proposals': pending,
                **{group: len(groups[group]) for group in _GROUPS}},
            'groups': result_groups, 'checked_at': utcnow()})
        _guard(db, identity)
        return result
    except (SQLAlchemyError, ValidationError):
        db.rollback()
        _unavailable()


# Notifications are fixed references and fixed text, not excerpts of a chat,
# model result or employee's goal. A source must still be visible on every read.
_NOTICE_TEXT = {
    'proposal_ready': '有一张业务卡待你核对并确认。',
    'proposal_input': '有一张业务卡需要你补充资料。',
    'proposal_unknown': '有一项办理结果不明，请核对原记录，勿重复提交。',
    'proposal_failed': '有一项办理未完成，请查看原卡的实际结果。',
    'plan_input': '有一件事项需要你确认或补充资料。',
    'plan_unknown': '有一件事项的办理结果需要你核对。',
    'plan_failed': '有一件事项未能继续，请查看实际进度。',
    'task_assigned': '有一项原业务待办需要你处理。',
}


@dataclass(frozen=True)
class _NoticeActor:
    owner_id: int
    store_id: int
    role: str
    account_role: str
    access_version: int


@dataclass(frozen=True, eq=False)
class _EventNotifications:
    event_id: str


_notice_proofs = WeakKeyDictionary()


def _notice_actor(db, owner_id, store_id):
    """Current real employee and membership; this does not issue a login/Grant."""
    from .models import Store
    account = db.scalar(select(User).where(User.id == owner_id))
    store = db.scalar(select(Store.id).where(Store.id == store_id, Store.active.is_(True)))
    if account is None or not account.active or account.must_change_password or store is None:
        return None
    role = role_for_store(db, account, store_id)
    if role is None:
        return None
    return _NoticeActor(account.id, store_id, role, account.role, account.access_version)


def _notice_principal(db, actor):
    if _notice_actor(db, actor.owner_id, actor.store_id) != actor:
        _changed()
    account = db.scalar(select(User).where(User.id == actor.owner_id))
    return RequestPrincipal(account, actor.role, _aggregate_scope=False, _active_store_id=actor.store_id)


def _plan_notice_blocker(db, actor, plan, *, clock=utcnow):
    """Reuse the scheduler's exact outcome/resume rules, without a Run authority."""
    from .assistant_runtime_plans import _followup_activity
    user = _notice_principal(db, actor)
    # These are actual row coordinates for a fixed read projection. This is
    # not RuntimePrincipal and cannot be used to call a model or native writer.
    user.actor_id, user.store_id, user.session_id = actor.owner_id, actor.store_id, plan.session_id
    user.plan_id, user.goal_version = plan.id, plan.goal_version
    activity = _followup_activity(db, user, clock=clock)
    facts = tuple(value for value in activity['runs']
                  if value[1:4] == (plan.session_id, plan.id, plan.goal_version))
    resumes = [_time(value[8]) for value in facts if value[6] in {'user', 'manual'} and value[7] == 'login']
    blockers = [value for value in facts if value[4] in {'succeeded', 'failed', 'cancelled'}
        and (value[4] == 'failed' or value[10])
        and not any(resume > _time(value[9] or value[8]) for resume in resumes)]
    if not blockers or plan.status in {'completed', 'cancelled'}:
        return None, facts
    # A failure outranks a missing-input result; never turn this into Step or
    # business completion/state. The real blocking Run identifies the reminder.
    chosen = max(blockers, key=lambda value: (value[4] == 'failed', _time(value[9] or value[8]), value[0]))
    return {'run_id': chosen[0], 'state': 'failed' if chosen[4] == 'failed' else 'needs_input',
            'reason': chosen[11] or 'recheck_required'}, facts


def _notice_case(db, actor, ref):
    """The fixed original Case authorization, without an HTTP or business write.

    Unknown domain references are not treated as visible. Their private record
    remains available from its normal authorized page, not from a guessed URL.
    """
    from . import flow_engine as eng
    from .flow_models import Case
    value = BusinessObjectRef.model_validate(ref)
    if value.type != 'case':
        return None
    principal = _notice_principal(db, actor)
    try:
        row = eng.get_case(db, principal, value.id)
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            return None
        raise
    if (row.store_id != actor.store_id or db.scalar(eng.case_query(principal)
            .where(Case.id == row.id).with_only_columns(Case.id)) is None):
        return None
    from .flow_navigation import case_entry_route
    return {'id': row.id, 'version': row.version, 'route': case_entry_route(row)}


def _notice_card_status(card, *, clock=utcnow):
    """Exactly the original derived status boundary, with a server-only clock."""
    now = _time(clock())
    if card.status == 'pending' and _time(card.expires_at) <= now:
        return 'expired'
    if (card.status == 'executing' and card.started_at is not None
            and _time(card.started_at) < now - timedelta(minutes=3)):
        return 'uncertain'
    return card.status


def _notice_source(db, actor, family, ident, *, clock=utcnow):
    """Read one actual source under its current employee, never copied identity."""
    from .assistant_runtime_models import WorkItem
    from .assistant_runtime_plans import _card_objects, project_legacy_plan
    from .flow_models import Task
    refs, session_id, plan_id, proposal_id, task_id = [], None, None, None, None
    principal = _notice_principal(db, actor)
    if family == 'task':
        task = db.scalar(select(Task).where(Task.id == ident, Task.store_id == actor.store_id,
                                           Task.assignee_id == actor.owner_id))
        if task is None:
            return None
        refs = [{'type': 'case', 'id': task.case_id}]
        task_id = task.id
        resolved = task.status in {'done', 'cancelled'}
        kind = 'task_assigned' if task.status == 'open' else None
        signature = [task.version, task.status, task.assignee_id, task.due_date.isoformat()]
        revision = [task.version]
    else:
        model = AssistantProposal if family == 'proposal' else AssistantWorkPlan if family == 'plan' else None
        if model is None:
            return None
        row = db.scalar(select(model).join(AssistantSession, AssistantSession.id == model.session_id).where(
            model.id == ident, model.owner_id == actor.owner_id, model.store_id == actor.store_id,
            AssistantSession.owner_id == actor.owner_id, AssistantSession.store_id == actor.store_id,
            AssistantSession.owner_role == actor.role, AssistantSession.access_version == actor.access_version))
        if row is None:
            return None
        session_id = row.session_id
        if family == 'proposal':
            if (row.owner_role, row.access_version) != (actor.role, actor.access_version):
                return None
            proposal_id = row.id
            if row.source_work_item_id:
                work = db.scalar(select(WorkItem).where(WorkItem.id == row.source_work_item_id,
                    WorkItem.owner_id == actor.owner_id, WorkItem.store_id == actor.store_id,
                    WorkItem.session_id == session_id, WorkItem.item_kind == 'prepare',
                    WorkItem.operation_id == row.operation_id))
                if work is None:
                    _changed()
                plan_id = work.plan_id
                if plan_id is not None and db.scalar(select(AssistantWorkPlan.id).where(
                        AssistantWorkPlan.id == plan_id, AssistantWorkPlan.owner_id == actor.owner_id,
                        AssistantWorkPlan.store_id == actor.store_id,
                        AssistantWorkPlan.session_id == session_id)) is None:
                    _changed()
            refs = list(_card_objects(row))
            status = _notice_card_status(row, clock=clock)
            resolved = status in {'succeeded', 'cancelled', 'expired'}
            kind = ('proposal_input' if row.questions else 'proposal_ready') if status == 'pending' else {
                'uncertain': 'proposal_unknown', 'failed': 'proposal_failed'}.get(status)
            signature = [row.version, status, bool(row.questions)]
            revision = [row.version, status]
        else:
            plan_id = row.id
            projection = project_legacy_plan(db, principal, session_id, row)
            if row.engine_version == 2:
                from .assistant_runtime_plans import _plan_view, _current_grant, _plan_grants
                thread = db.scalar(select(AssistantSession).where(AssistantSession.id == session_id))
                display = _plan_view(row, projection, _current_grant(_plan_grants(db, thread, row)), now=_time(clock()))
            else:
                from .assistant_runtime_api import _legacy_view
                display = _legacy_view(row, projection)
            displayed = {step['key']: step for step in display['steps']}
            blocker, run_facts = _plan_notice_blocker(db, actor, row, clock=clock)
            states = []
            for step in projection['steps']:
                state = displayed[step['key']]['status']
                reason = displayed[step['key']]['wait_reason']
                ids = step.get('proposal_ids', []) or ([step['proposal_id']] if step.get('proposal_id') else [])
                if state in {'uncertain', 'executing'} and ids:
                    cards = list(db.scalars(select(AssistantProposal).where(AssistantProposal.id.in_(ids),
                        AssistantProposal.owner_id == actor.owner_id, AssistantProposal.store_id == actor.store_id,
                        AssistantProposal.session_id == session_id)))
                    effective = [_notice_card_status(card, clock=clock) for card in cards]
                    if len(cards) == len(ids) and 'executing' in effective and 'uncertain' not in effective:
                        # Original Plan projection conservatively blocks an
                        # in-flight confirmation; no premature unknown notice.
                        state = 'waiting'
                states.append([step['key'], state, reason, step.get('proposal_ids', []), step.get('rows', [])])
                ref = step.get('object_ref')
                if ref is None and type(step.get('case_id')) is int and step['case_id'] > 0:
                    ref = {'type': 'case', 'id': step['case_id']}
                if ref is not None and ref not in refs:
                    refs.append(ref)
            resolved = row.status in {'completed', 'cancelled'}
            kind = None
            if not resolved and row.status != 'paused':
                if blocker is not None:
                    kind = 'plan_failed' if blocker['state'] == 'failed' else 'plan_input'
                elif any(state in {'uncertain', 'executing'} for _, state, *_ in states):
                    kind = 'plan_unknown'
                elif any(state == 'failed' for _, state, *_ in states):
                    kind = 'plan_failed'
                elif any(state in {'needs_input', 'awaiting_confirmation'} or reason in _INPUT_REASONS
                         for _, state, reason, *_ in states):
                    kind = 'plan_input'
            # next_check_at, observed_at, context pointer and heartbeat versions
            # are not notification changes. Persisted real row outcomes are.
            facts_signature = [row.goal_version, row.status, states, blocker]
            # The same failed/input-blocked Run is one reminder even if an
            # unrelated Step changes. Full facts still guard concurrency.
            signature = ([row.goal_version, blocker['run_id'], blocker['state'], blocker['reason']]
                         if blocker is not None else facts_signature)
            revision = [row.version, facts_signature, run_facts]
    visible = []
    for ref in refs:
        value = _notice_case(db, actor, ref)
        if value is None:
            return None
        visible.append(value)
    return {'family': family, 'id': ident, 'kind': kind, 'resolved': resolved,
        'source_key': f'{family}:{ident}:' + _hash(signature),
        'session_id': session_id, 'plan_id': plan_id, 'proposal_id': proposal_id, 'task_id': task_id,
        'manual_route': visible[0]['route'] if len(visible) == 1 else None,
        'revision': revision, 'case_refs': [value['id'] for value in visible]}


def _event_notice_candidates(db, event):
    from .assistant_runtime_outbox import _source_facts
    from .flow_models import Task
    _source_facts(db, event)  # Exact real producer key, version and FK relationships.
    candidates = []
    if event['topic'] in {'flow', 'task'}:
        query = select(Task.id, Task.assignee_id).where(Task.store_id == event['store_id'])
        query = query.where(Task.id == event['task_id']) if event['task_id'] else query.where(
            Task.case_id == event['object_ref']['id'])
        candidates = [('task', row.id, row.assignee_id) for row in db.execute(query.order_by(Task.id))
                      if row.assignee_id is not None]
    elif event['proposal_id'] is not None:
        row = db.scalar(select(AssistantProposal).where(AssistantProposal.id == event['proposal_id'],
                                                       AssistantProposal.store_id == event['store_id']))
        if row is not None:
            candidates.append(('proposal', row.id, row.owner_id))
    elif event['plan_id'] is not None:
        row = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == event['plan_id'],
                                                       AssistantWorkPlan.store_id == event['store_id']))
        if row is not None:
            candidates.append(('plan', row.id, row.owner_id))
    return candidates


def _notice_state(db, proof, *, consumed=None):
    state = _notice_proofs.get(proof) if type(proof) is _EventNotifications else None
    if (state is None or state['db'] is not db or state['bind'] is not db.get_bind()
            or monotonic() - state['issued'] > 60
            or consumed is False and state['transaction'] is not None
            or consumed is True and (state['transaction'] is None or state['transaction'] is not db.get_transaction())):
        _changed()
    return state


async def resolve_event_notifications(db, event, *, clock=utcnow, read_session_factory=None, client_factory=None):
    """Prepare a fixed-event proof; no login, Grant, model, HTTP or writes.

    The dispatcher calls this after independent receipt coordination, and then
    saves notifications in its existing event transaction. client_factory is
    accepted for the dispatch interface; original fixed read services suffice.
    """
    from .assistant_runtime_outbox import _event_snapshot
    from .assistant_runtime_models import WakeEvent
    if not settings.assistant_notifications_enabled:
        raise HTTPException(503, '站内提醒当前未开启')
    sources = []
    with _reader(db, read_session_factory) as reader:
        row = reader.scalar(select(WakeEvent).where(WakeEvent.id == event['id']))
        if row is None or _event_snapshot(row) != event or row.state != 'pending':
            _changed()
        set_scope(reader, [event['store_id']], event['store_id'])
        for family, ident, owner_id in _event_notice_candidates(reader, event):
            actor = _notice_actor(reader, owner_id, event['store_id'])
            if actor is None:
                continue
            source = _notice_source(reader, actor, family, ident, clock=clock)
            if source is not None:
                sources.append((actor, family, ident, source['revision']))
    proof = _EventNotifications(event['id'])
    _notice_proofs[proof] = {'db': db, 'bind': db.get_bind(), 'issued': monotonic(), 'event': deepcopy(event),
        'sources': sources, 'transaction': None, 'factory': read_session_factory, 'visible': []}
    return proof


def _upsert_notice(db, actor, source, now):
    from .assistant_runtime_models import Notification
    query = select(Notification).where(Notification.owner_id == actor.owner_id,
        Notification.store_id == actor.store_id, getattr(Notification, source['family'] + '_id') == source['id'])
    if source['family'] == 'plan':
        # Ending assistant follow-up does not cancel or resolve its original
        # pending business cards, even when those notices also link this Plan.
        query = query.where(Notification.proposal_id.is_(None), Notification.task_id.is_(None))
    if source['resolved']:
        for row in db.scalars(query.where(Notification.status != 'resolved').with_for_update()):
            row.status = 'resolved'
        return
    if source['kind'] is None:
        return
    values = {'owner_id': actor.owner_id, 'store_id': actor.store_id,
        **{key: source[key] for key in ('session_id', 'plan_id', 'proposal_id', 'task_id')},
        'source_key': source['source_key'], 'kind': source['kind'],
        'safe_summary': _NOTICE_TEXT[source['kind']]}
    exact = select(Notification).where(Notification.owner_id == actor.owner_id,
        Notification.store_id == actor.store_id, Notification.source_key == source['source_key'],
        Notification.kind == source['kind'])
    prior = db.scalar(exact)
    if prior is None:
        db.flush()
        try:
            with db.begin_nested():
                prior = Notification(id=str(uuid4()), **values, status='unread', created_at=now, version=1)
                db.add(prior)
                db.flush()
        except IntegrityError:
            prior = db.scalar(exact)
            if prior is None:
                _changed()
    if any(getattr(prior, key) != value for key, value in values.items()):
        _changed()
    # Replaying an event must not turn a read notification unread again.


def persist_event_notifications(db, proof, *, clock=utcnow):
    """Flush only, in the dispatcher's same-store event transaction."""
    from .assistant_runtime_outbox import _event_snapshot
    from .assistant_runtime_models import WakeEvent
    from .assistant_runtime_queue import _scope
    state = _notice_state(db, proof, consumed=False)
    if not settings.assistant_notifications_enabled:
        raise HTTPException(503, '站内提醒当前未开启')
    _scope(db, state['event']['store_id'])
    with db.no_autoflush:
        event = db.scalar(select(WakeEvent).where(WakeEvent.id == proof.event_id).with_for_update())
        if event is None or _event_snapshot(event) != state['event']:
            _changed()
        _event_notice_candidates(db, state['event'])
        current = []
        for actor, family, ident, _ in state['sources']:
            source = _notice_source(db, actor, family, ident, clock=clock)
            if source is None:
                _changed()
            current.append((actor, source))
    state['transaction'] = db.get_transaction()
    for actor, source in current:
        _upsert_notice(db, actor, source, _time(clock()))
    db.flush()
    state['visible'] = [(actor, source['case_refs']) for actor, source in current]
    return len(current)


def validate_event_notifications(db, proof, *, clock=utcnow):
    """Independent committed-source check after flush, before caller commit."""
    state = _notice_state(db, proof, consumed=True)
    if not settings.assistant_notifications_enabled:
        raise HTTPException(503, '站内提醒当前未开启')
    with _reader(db, state['factory']) as reader:
        set_scope(reader, [state['event']['store_id']], state['event']['store_id'])
        for actor, family, ident, revision in state['sources']:
            source = _notice_source(reader, actor, family, ident, clock=clock)
            if source is None or source['revision'] != revision:
                _changed()
        for actor, refs in state['visible']:
            for ident in refs:
                if _notice_case(reader, actor, {'type': 'case', 'id': ident}) is None:
                    _changed()
    return None


def _notice_family(row):
    if row.proposal_id is not None:
        return 'proposal', row.proposal_id
    if row.task_id is not None:
        return 'task', row.task_id
    if row.plan_id is not None:
        return 'plan', row.plan_id
    return None, None


def _notice_view(db, actor, row):
    from .assistant_runtime_schemas import NotificationView
    if (row.owner_id, row.store_id) != (actor.owner_id, actor.store_id) or row.kind not in _NOTICE_TEXT:
        return None
    family, ident = _notice_family(row)
    source = _notice_source(db, actor, family, ident)
    if source is None or any(getattr(row, key) != source[key]
            for key in ('session_id', 'plan_id', 'proposal_id', 'task_id')):
        return None
    if row.status == 'resolved':
        if not source['resolved']:
            return None
    elif source['resolved'] or row.kind != source['kind'] or row.source_key != source['source_key']:
        # Stale reminders are not current work. GET never repairs their status.
        return None
    view = NotificationView.model_validate({'id': row.id, 'kind': row.kind,
        'safe_summary': _NOTICE_TEXT[row.kind], 'status': row.status,
        'created_at': row.created_at, 'read_at': row.read_at,
        **{key: source[key] for key in ('session_id', 'plan_id', 'proposal_id', 'task_id', 'manual_route')}})
    return view, (row.version, source['revision'])


def _notification_rows(db, identity):
    from .assistant_runtime_models import Notification
    actor = _NoticeActor(identity.actor_id, identity.store_id, identity.role,
                         identity.account_role, identity.access_version)
    result = []
    with _reading(db, identity) as (reader, _):
        for row in reader.scalars(select(Notification).where(Notification.owner_id == identity.actor_id,
                Notification.store_id == identity.store_id).order_by(Notification.created_at.desc(), Notification.id.desc())):
            value = _notice_view(reader, actor, row)
            if value is not None:
                result.append(value)
    return result


def _notification_position(identity, query, rows, fingerprint):
    if query.cursor is None:
        return 0
    if not query.cursor or len(query.cursor) > 4096:
        raise HTTPException(422, '通知游标无效')
    try:
        data = json.loads(urlsafe_b64decode(query.cursor + '=' * (-len(query.cursor) % 4)).decode('utf-8'))
    except (ValueError, UnicodeError):
        raise HTTPException(422, '通知游标无效') from None
    if (type(data) is not dict or set(data) != {'v', 'scope', 'limit', 'facts', 'after'}
            or type(data['v']) is not int or data['v'] != 1
            or type(data['limit']) is not int or data['limit'] != query.limit
            or data['scope'] != _scope_key(identity)):
        raise HTTPException(422, '通知游标与当前身份或门店不匹配')
    if data['facts'] != fingerprint:
        _changed()
    for index, (view, _) in enumerate(rows):
        if view.id == data['after']:
            return index + 1
    _changed()


async def read_notifications(db, request, user, query):
    """Read existing records even with notifications disabled; never generate."""
    from .assistant_runtime_schemas import NotificationQuery, NotificationList
    try:
        query = NotificationQuery.model_validate(query.model_dump() if isinstance(query, NotificationQuery) else query)
    except ValidationError:
        raise HTTPException(422, '请核对通知数量与游标') from None
    identity = _capture(db, request, user)
    if identity.aggregate:
        raise HTTPException(409, '请切换到具体门店查看本人通知')
    try:
        rows = _notification_rows(db, identity)
        fingerprint = _hash([view.model_dump(mode='json') for view, _ in rows])
        start = _notification_position(identity, query, rows, fingerprint)
        page = rows[start:start + query.limit]
        cursor = None
        if start + len(page) < len(rows):
            cursor = urlsafe_b64encode(_json({'v': 1, 'scope': _scope_key(identity), 'limit': query.limit,
                'facts': fingerprint, 'after': page[-1][0].id}).encode('utf-8')).decode('ascii').rstrip('=')
        result = NotificationList.model_validate({'items': [view for view, _ in page], 'next_cursor': cursor,
            'unread_count': sum(view.status == 'unread' for view, _ in rows)})
        if rows != _notification_rows(db, identity):
            _changed()
        _guard(db, identity)
        return result
    except (SQLAlchemyError, ValidationError):
        db.rollback()
        _unavailable()


def _notification_post_guard(db, request, identity, ident):
    from .models import LoginSession
    if (request.method != 'POST'
            or request.url.path != '/api/business-assistant/notifications/' + ident + '/read'):
        raise HTTPException(403, '请由员工本人打开通知')
    raw, csrf = request.cookies.get('dealer_session', ''), request.headers.get('x-csrf-token', '')
    if not raw or not csrf or not hmac.compare_digest(sha256(raw.encode()).hexdigest(), identity.login_ref):
        raise HTTPException(403, '请求校验失败，请刷新页面')
    with _reading(db, identity) as (reader, _):
        login = reader.scalar(select(LoginSession).where(LoginSession.id == identity.login_ref))
        if login is None or not hmac.compare_digest(login.csrf_hash, sha256(csrf.encode()).hexdigest()):
            raise HTTPException(403, '请求校验失败，请刷新页面')


async def mark_notification_read(db, request, user, notification_id):
    """Only unread→read; repeated reads and resolved records are unchanged."""
    from .assistant_runtime_models import Notification
    from .assistant_runtime_queue import _scope, _sqlite_writer
    from .business_assistant_service import commit
    identity = _capture(db, request, user)
    if identity.aggregate:
        raise HTTPException(409, '请切换到具体门店查看本人通知')
    _notification_post_guard(db, request, identity, notification_id)
    actor = _NoticeActor(identity.actor_id, identity.store_id, identity.role,
                         identity.account_role, identity.access_version)
    try:
        _sqlite_writer(db)
        _scope(db, identity.store_id)
        with db.no_autoflush:
            row = db.scalar(select(Notification).where(Notification.id == notification_id,
                Notification.owner_id == identity.actor_id, Notification.store_id == identity.store_id)
                .with_for_update().execution_options(populate_existing=True))
            projected = _notice_view(db, actor, row) if row is not None else None
            if projected is None:
                raise HTTPException(404, '通知不存在或当前不可查看')
            before = projected
            with _reading(db, identity) as (reader, _):
                current = reader.scalar(select(Notification).where(Notification.id == notification_id,
                    Notification.owner_id == identity.actor_id, Notification.store_id == identity.store_id))
                if current is None or _notice_view(reader, actor, current) != before:
                    _changed()
            if row.status == 'unread':
                row.status, row.read_at = 'read', utcnow()
        db.flush()
        if _notice_view(db, actor, row) is None:
            _changed()
        with _reading(db, identity) as (reader, _):
            original = reader.scalar(select(Notification).where(Notification.id == notification_id,
                Notification.owner_id == identity.actor_id, Notification.store_id == identity.store_id))
            if original is None or _notice_view(reader, actor, original) != before:
                _changed()
        _notification_post_guard(db, request, identity, notification_id)
        commit(db)
    except (StaleDataError, IntegrityError):
        db.rollback()
        raise HTTPException(409, '通知已变化，请刷新后继续查看') from None
    except OperationalError as exc:
        db.rollback()
        if 'locked' in str(exc).lower() or getattr(exc.orig, 'sqlstate', None) in {'40001', '40P01', '55P03'}:
            raise HTTPException(409, '通知正在更新，请刷新后继续查看') from None
        raise
    except Exception:
        db.rollback()
        raise
    # Post-commit authorization failure must not pretend the read was rolled
    # back. Return no old notification details to a revoked login.
    _notification_post_guard(db, request, identity, notification_id)
    with _reading(db, identity) as (reader, _):
        fresh = reader.scalar(select(Notification).where(Notification.id == notification_id,
            Notification.owner_id == identity.actor_id, Notification.store_id == identity.store_id))
        value = _notice_view(reader, actor, fresh) if fresh is not None else None
        if value is None:
            raise HTTPException(404, '通知当前不可查看')
        return value[0]
