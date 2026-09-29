"""Persist one owned DAG and project its complete, real preparation outcomes.

Saving never executes business, enables follow-up or evaluates completion facts.
All native reads precede the versioned write transaction. Version-1 steps remain
historical JSON after an explicit upgrade; PlanStep is the version-2 source.

Forward dependency: registered non-Case adapters use M3.4's synchronous
assistant_runtime_principal.principal_for_request(db, request, user, session_id).
It returns a freshly verified RuntimePrincipal for the real login or trusted
internal Grant. No provider exists for those namespaces before that milestone;
the import is lazy and failure never falls back to a fabricated identity.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from time import monotonic
from uuid import uuid4
from weakref import WeakKeyDictionary, ref

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError

from .business_assistant_models import AssistantMessage, AssistantProposal, AssistantWorkPlan
from .assistant_runtime_models import FollowupGrant, PlanStep, Run, RunItem, WorkItem
from .assistant_runtime_labels import waiting_label
from .assistant_runtime_schemas import BusinessObjectRef
from .db import utcnow


_STEP_FIELDS = ('key', 'title', 'wait_for', 'depends_on', 'proposal_id', 'object_ref',
                'workflow_id', 'form_ref', 'conditions', 'completion_conditions', 'required')
_LABELS = {
    'awaiting_confirmation': '待你确认', 'needs_input': '请补充必要资料',
    'step_completed': '这一步已办理', 'failed': '这一步未办成',
    'uncertain': '结果待核对，不能重试', 'cancelled': '这一步已取消',
    'expired': '草稿已过期，请重新核对', 'waiting_dependency': '等待前一步',
    'needs_preparation': '待继续核对并准备', 'planned': '待准备',
    'waiting_fact': '等待实际资料或同事办理',
}


def _conflict(message='计划或关联记录已变化，请读取最新状态后再修改'):
    raise HTTPException(409, message) from None


def validate_dag(steps):
    """Return a stable topological order; never accept missing or repeated keys."""
    if type(steps) is not list or not steps:
        raise HTTPException(422, '请提供完整的计划步骤')
    keys = [step.get('key') for step in steps if type(step) is dict]
    if (len(keys) != len(steps) or any(type(key) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', key) for key in keys)
            or len(keys) != len(set(keys))):
        raise HTTPException(422, '计划步骤标识无效或重复')
    graph = {}
    for step in steps:
        deps = step.get('depends_on', [])
        if (type(deps) is not list or any(type(dep) is not str for dep in deps)
                or len(deps) != len(set(deps)) or step['key'] in deps or set(deps) - set(keys)):
            raise HTTPException(422, '步骤只能依赖本计划内其他步骤，不能重复或依赖自己')
        graph[step['key']] = set(deps)
    refs = [step['proposal_id'] for step in steps if step.get('proposal_id') is not None]
    if any(type(value) is not str for value in refs) or len(refs) != len(set(refs)):
        raise HTTPException(422, '同一张草稿不能重复关联多个步骤')
    pending = list(steps)
    done, ordered = set(), []
    while pending:
        step = next((item for item in pending if graph[item['key']] <= done), None)
        if step is None:
            raise HTTPException(422, '步骤之间形成循环，请按真实先后关系整理')
        pending.remove(step)
        ordered.append(deepcopy(step))
        done.add(step['key'])
    return ordered


def _same_scope(row, thread):
    if (row.owner_id, row.store_id, row.session_id) != (thread.owner_id, thread.store_id, thread.id):
        _conflict('关联记录不属于当前计划的员工、门店或对话')


def _authorized_thread(db, user, sid):
    from .business_assistant_service import owned_session
    from .models import Store, User, UserStore
    from .tenancy import role_for_store
    identity = (user.id, user.role, user.access_version)
    actual = db.scalar(select(User).where(User.id == identity[0]).execution_options(populate_existing=True))
    if (actual is None or not actual.active or actual.must_change_password
            or actual.access_version != identity[2]):
        raise HTTPException(404, '当前无法访问这项计划')
    thread = owned_session(db, user, sid)
    enabled = db.scalar(select(Store.id).where(Store.id == thread.store_id, Store.active.is_(True)))
    # Refresh the original membership before role_for_store; the existing helper
    # can otherwise reuse an identity-map row from before a nested native GET.
    db.scalar(select(UserStore).where(UserStore.user_id == actual.id,
        UserStore.store_id == thread.store_id).execution_options(populate_existing=True))
    if enabled is None or role_for_store(db, actual, thread.store_id) != identity[1]:
        raise HTTPException(404, '当前无法访问这项计划')
    return thread


def _owned_plan(db, thread, plan_id=None, request_id=None, *, refresh=False):
    query = select(AssistantWorkPlan).where(AssistantWorkPlan.owner_id == thread.owner_id,
        AssistantWorkPlan.store_id == thread.store_id, AssistantWorkPlan.session_id == thread.id)
    query = query.where(AssistantWorkPlan.id == plan_id) if plan_id else query.where(AssistantWorkPlan.request_id == request_id)
    if refresh:
        query = query.execution_options(populate_existing=True)
    row = db.scalar(query)
    if plan_id and row is None:
        raise HTTPException(404, '计划不存在或不可访问')
    return row


def _step_values(step):
    return {key: deepcopy(getattr(step, key)) for key in _STEP_FIELDS}


def _steps(db, plan, *, refresh=False):
    query = select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.position, PlanStep.id)
    if refresh:
        query = query.execution_options(populate_existing=True)
    return list(db.scalars(query))


def _cards(db, user, thread, ids):
    wanted = set(ids)
    if not wanted:
        return {}
    rows = list(db.scalars(select(AssistantProposal).where(AssistantProposal.id.in_(wanted),
        AssistantProposal.owner_id == user.id, AssistantProposal.store_id == thread.store_id,
        AssistantProposal.session_id == thread.id, AssistantProposal.owner_role == user.role,
        AssistantProposal.access_version == user.access_version).execution_options(populate_existing=True)))
    if {row.id for row in rows} != wanted:
        raise HTTPException(404, '草稿不属于当前对话或已不可访问')
    for card in rows:
        if card.source_work_item_id:
            work = db.scalar(select(WorkItem).where(WorkItem.id == card.source_work_item_id))
            if work is None:
                _conflict()
            _same_scope(work, thread)
            if work.item_kind != 'prepare' or work.operation_id != card.operation_id:
                _conflict()
    return {row.id: row for row in rows}


def _card_state(card):
    if card.status == 'pending' and card.expires_at <= utcnow():
        return 'expired'
    return card.status


def _card_objects(card):
    """Only registered result shapes and explicit Flow targets prove relations."""
    from .assistant_runtime_domains import FLOW_ACTION, FLOW_READ
    from .assistant_runtime_objects import resolve_result
    path = (card.payload or {}).get('path_args') or {}
    refs = []
    if card.operation_id in {FLOW_ACTION, FLOW_READ} and type(path.get('case_id')) is int and path['case_id'] > 0:
        refs.append({'type': 'case', 'id': path['case_id']})
    if card.status == 'succeeded':
        result = resolve_result(card.operation_id, card.result)
        results = [ref.model_dump(mode='json') for ref in result.object_refs]
        if refs and any(ref['type'] == 'case' and ref != refs[0] for ref in results):
            _conflict('原提交结果与明确原单引用不一致，请先核对')
        for ref in results:
            if ref not in refs:
                refs.append(ref)
    return refs


def _card_case(card):
    """Legacy display convenience; general relationships use typed objects."""
    cases = [ref['id'] for ref in _card_objects(card) if ref['type'] == 'case']
    return cases[0] if len(cases) == 1 else None


def _private_refs(db, user, thread, steps, *, plan=None, existing=None):
    ids = [step['proposal_id'] for step in steps if step.get('proposal_id')]
    conditions = [condition for step in steps for field in ('conditions', 'completion_conditions') for condition in step[field]]
    ids += [value['proposal_id'] for value in conditions if value['type'] == 'proposal_succeeded']
    cards = _cards(db, user, thread, ids)
    existing = existing or {}
    for step in steps:
        card = cards.get(step.get('proposal_id'))
        if card is not None and card.source_work_item_id:
            work = db.scalar(select(WorkItem).where(WorkItem.id == card.source_work_item_id))
            old_step = existing.get(step['key'])
            if (work.plan_id is not None and (plan is None or work.plan_id != plan.id)
                    or work.step_id is not None and (old_step is None or work.step_id != old_step.id)):
                _conflict('草稿已属于另一计划步骤，不能重新关联')
        obj = step.get('object_ref')
        if card is not None and obj is not None and obj not in _card_objects(card):
            raise HTTPException(422, '草稿与所选原单的关系尚未证实')
    for condition in conditions:
        if condition['type'] == 'due_at':
            message = db.scalar(select(AssistantMessage.id).where(
                AssistantMessage.id == condition['source_message_id'], AssistantMessage.session_id == thread.id,
                AssistantMessage.store_id == thread.store_id, AssistantMessage.role == 'user'))
            if message is None:
                raise HTTPException(404, '等待时间必须引用本对话的真实员工消息')
    return cards


async def _validate_native_refs(db, request, user, thread, config, steps):
    from . import business_assistant_service as service
    from .business_assistant_business_tools import native, inspect_form
    from .assistant_runtime_domains import FlowCaseAdapter
    from .assistant_runtime_domains.flow_case import _record, _response_data
    from .assistant_runtime_registry import domain_registry
    from .flow_models import Task
    from .workflow_guides_api import load_catalogue
    published = {entry['id'] for entry in load_catalogue()}
    records = {}
    object_snapshots = {}
    providers = domain_registry()

    def action_keys(record):
        from .assistant_runtime_schemas import BusinessObjectSnapshot
        if isinstance(record, BusinessObjectSnapshot):
            return {action.action_key for action in record.available_actions}
        from .flow_specs import FLOW_CATALOGUES
        keys = {entry if type(entry) is str else entry.get('key') for entry in record['actions']}
        spec = FLOW_CATALOGUES.get(record['flow_version'], {}).get(record['kind'])
        if spec is not None:
            keys.update(action.key for action in spec['actions'])
        # Definition proves only a legitimate reference for future waiting; it
        # never proves current permission, availability or completed business.
        return keys

    async def case_record(case_id):
        if case_id not in records:
            from .business_assistant_workboard import LIVE_CASE_PAGE
            if len(records) >= LIVE_CASE_PAGE:
                raise HTTPException(422, '一份计划最多核对10条原单；大量独立项请关联真实草稿')
            service.require_preparation_read_phase(db)
            response = await native(db, request, user, thread.id, config,
                                    'GET /api/flow/cases/{case_id}', {'case_id': case_id})
            # Reuse only the adapter's pure response projection; native() above
            # used the original request/employee. No RuntimePrincipal is forged.
            record = _record(_response_data(response), expected_id=case_id,
                             expected_store=thread.store_id, observed_at=datetime.now(timezone.utc))
            adapter = FlowCaseAdapter(native_reader=native)
            adapter.snapshot_from_record(BusinessObjectRef(type='case', id=case_id), record)
            records[case_id] = record
        return records[case_id]

    async def object_record(ref):
        if ref['type'] == 'case':
            return await case_record(ref['id'])
        if providers.spec_for_object(ref['type']) is None:
            raise HTTPException(422, '此对象类型尚未接入计划核对，请使用原业务页面')
        from .assistant_runtime_principal import principal_for_request
        key = (ref['type'], ref['id'])
        if key not in object_snapshots:
            from .assistant_runtime_objects import read_object
            from . import business_assistant_gateway as gateway

            async def registered_read(operation_id, *, path_args=None, query=None, body=None):
                service.require_preparation_read_phase(db)
                current = principal_for_request(db, request, user, thread.id)
                if type(operation_id) is not str or body not in (None, {}):
                    raise HTTPException(403, '计划适配器只能读取原业务查询')
                operation = gateway.inspect_operation(operation_id)
                if (operation['method'] != 'GET' or operation['write']
                        or gateway.role_may_read(current.role, operation) is False):
                    raise HTTPException(403, '当前身份不能使用此原业务查询')
                checked = gateway.validate_operation(operation_id, path_args, query, None)
                response = await native(db, request, user, thread.id, config, operation_id,
                                        checked['path_args'], checked['query'])
                principal_for_request(db, request, user, thread.id)
                return response

            service.require_preparation_read_phase(db)
            principal = principal_for_request(db, request, user, thread.id)
            snapshot = await read_object(principal, ref, native_reader=registered_read, registry=providers)
            object_snapshots[key] = snapshot
        principal_for_request(db, request, user, thread.id)
        return object_snapshots[key]

    def fact_provider(ref, record, fact_key):
        provider = providers.spec_for_fact(fact_key)
        native_kind = record['kind'] if ref['type'] == 'case' else None
        native_version = record['flow_version'] if ref['type'] == 'case' else None
        if not providers.supports_fact(fact_key, ref['type'], kind=native_kind, flow_version=native_version):
            raise HTTPException(422, '此业务事实尚未接入该对象的实际业务类别和流程版本')
        return provider

    for step in steps:
        if not any(step.get(key) for key in ('proposal_id', 'object_ref', 'workflow_id', 'form_ref')):
            raise HTTPException(422, '步骤必须关联真实草稿、原单、已发布工作流或原表单')
        if step.get('workflow_id') and step['workflow_id'] not in published:
            raise HTTPException(422, '请关联实际发布的工作流')
        if step.get('object_ref'):
            await object_record(step['object_ref'])
        form = step.get('form_ref')
        if form:
            match = re.fullmatch(r'case:([1-9][0-9]*):([A-Za-z0-9_]+)', form)
            if match:
                case_id, action = int(match[1]), match[2]
                record = await case_record(case_id)
                if action not in action_keys(record):
                    raise HTTPException(422, '原单没有此表单，请重新选择已返回的操作')
                if step.get('object_ref') and step['object_ref'] != {'type': 'case', 'id': case_id}:
                    raise HTTPException(422, '表单与步骤原单不一致')
            else:
                service.require_preparation_read_phase(db)
                await inspect_form(db, request, user, thread.id, config, form)
        for condition in step['conditions'] + step['completion_conditions']:
            kind = condition['type']
            if kind in {'native_action_available', 'fact_exists'}:
                record = await object_record(condition['object_ref'])
                if kind == 'native_action_available':
                    if condition['action_key'] not in action_keys(record):
                        raise HTTPException(422, '等待动作未由原单返回，不能猜测可执行动作')
                else:
                    fact_provider(condition['object_ref'], record, condition['fact_key'])
            elif kind == 'native_task_state':
                task = db.scalar(select(Task).where(Task.id == condition['task_id'], Task.store_id == thread.store_id))
                if task is None:
                    raise HTTPException(404, '任务不存在或当前门店不可查看')
                record = await case_record(task.case_id)
                if not any(row.get('id') == condition['task_id'] and row.get('case_id') == record['id'] for row in record['tasks']):
                    raise HTTPException(404, '任务未由可见原单返回')
    return records


def _manifest_index(db, user, thread, plan):
    from .assistant_runtime_runner import _manifest_data
    items = list(db.scalars(select(RunItem).join(Run, Run.id == RunItem.run_id).where(
        Run.owner_id == user.id, Run.store_id == thread.store_id, Run.session_id == thread.id,
        RunItem.kind == 'tool', RunItem.tool_name == 'prepare_inputs')))
    by_id, current = {}, {}
    for item in items:
        raw = item.validated_arguments
        if type(raw) is not dict or type(raw.get('scope')) is not dict or raw['scope'].get('plan_id') != plan.id:
            continue
        data = _manifest_data(item)
        scope = data['scope']
        if ((scope['owner_id'], scope['store_id'], scope['session_id'], scope['role'], scope['access_version'])
                != (user.id, thread.store_id, thread.id, user.role, user.access_version)):
            _conflict()
        key = (scope['step_id'], scope['intent_version'])
        if key in current:
            _conflict('计划行清单存在重复，请先核对')
        current[key] = data
        by_id[item.id] = data
    return current, by_id


def _work_for_step(db, thread, plan, step):
    rows = list(db.scalars(select(WorkItem).where(WorkItem.step_id == step.id)))
    for row in rows:
        _same_scope(row, thread)
        if row.plan_id != plan.id:
            _conflict()
    return {row.id: row for row in rows}


def _row_outcomes(db, user, thread, plan, step, manifest, manifests, works):
    """Read current cards, including explicitly carried older successful rows."""
    if manifest is None:
        if any(work.intent_version == step.intent_version and work.item_kind == 'prepare' for work in works.values()):
            _conflict('准备行缺少完整输入清单，请先核对')
        return [], {}
    if manifest['scope']['step_key'] != step.key:
        _conflict()
    if step.proposal_id is not None:
        _conflict('兼容单卡与完整批量清单不能并行计数')
    ids = [work.id for work in works.values()]
    source_cards = list(db.scalars(select(AssistantProposal).where(AssistantProposal.source_work_item_id.in_(ids)))) if ids else []
    cards = _cards(db, user, thread, [card.id for card in source_cards])
    by_work = {card.source_work_item_id: card for card in cards.values()}
    if len(by_work) != len(cards):
        _conflict()
    projected, covered = [], set()
    for row in manifest['rows']:
        work = works.get(row.get('work_item_id'))
        card = by_work.get(work.id) if work else None
        carry = row.get('carry_forward')
        if work is not None:
            if work.item_kind != 'prepare' or work.input_item_id != row['input_item_id']:
                _conflict()
            if carry is None and work.intent_version != step.intent_version:
                _conflict()
            if carry is not None:
                previous = manifests.get(carry.get('manifest_id')) if type(carry) is dict else None
                prior_row = next((item for item in previous['rows'] if item['input_item_id'] == row['input_item_id']), None) if previous else None
                if (type(carry) is not dict or set(carry) != {'manifest_id', 'intent_version'}
                        or previous is None or previous['scope']['step_id'] != step.id
                        or carry.get('intent_version') != previous['scope']['intent_version']
                        or work.intent_version >= step.intent_version or previous['scope']['intent_version'] >= step.intent_version
                        or prior_row is None or any(prior_row.get(key) != row.get(key) for key in ('position', 'input_digest', 'work_item_id', 'supersedes_id'))
                        or prior_row.get('proposal_id') is not None and prior_row['proposal_id'] != row.get('proposal_id')):
                    _conflict()
            covered.add(work.id)
            if row.get('proposal_id') != (card.id if card else None):
                _conflict()
            if card is None and work.status != 'planned':
                _conflict()
        elif row.get('work_item_id') is not None or row.get('proposal_id') is not None or carry is not None:
            _conflict()
        state = _card_state(card) if card else row['outcome']
        if work is not None and work.status == 'uncertain':
            state = 'uncertain'
        if card is None and state in {'prepared', 'settled'}:
            _conflict()
        projected.append({'input_item_id': row['input_item_id'], 'position': row['position'],
            'work_item_id': work.id if work else None, 'proposal_id': card.id if card else None,
            'status': state, 'reason_code': row.get('reason_code')})
    if any(work.item_kind == 'prepare' and work.intent_version == step.intent_version and work.id not in covered for work in works.values()):
        _conflict('存在未计入完整清单的准备行，请先核对')
    selected_ids = {row['proposal_id'] for row in projected if row['proposal_id']}
    return projected, {key: card for key, card in cards.items() if key in selected_ids}


def _stored_read_completion(db, thread, plan, step, works):
    """Project an evaluated read result; this never replaces its original GET."""
    if step.status != 'completed' or step.wait_reason != 'read_completed' or step.proposal_id:
        return False
    current = [row for row in works.values() if row.intent_version == step.intent_version]
    if not current or any(row.item_kind != 'read' or row.status != 'settled' for row in current):
        return False
    if db.scalar(select(AssistantProposal.id).where(
            AssistantProposal.source_work_item_id.in_([row.id for row in current])).limit(1)):
        return False
    if db.scalar(select(WorkItem.id).where(WorkItem.supersedes_id.in_([row.id for row in current])).limit(1)):
        return False
    try:
        from .assistant_runtime_schemas import EvidenceRef
        evidence = [EvidenceRef.model_validate(value) for value in step.last_evidence or []]
        refs = {ref.source_id.id: ref.native_version for ref in evidence
                if ref.source_type == 'object' and ref.source_id.type == 'report_query'}
    except (ValueError, TypeError, AttributeError):
        return False
    if refs != {row.id: row.version for row in current}:
        return False
    for work in current:
        item = db.scalar(select(RunItem).where(RunItem.work_item_id == work.id)
            .order_by(RunItem.created_at.desc(), RunItem.attempt_no.desc(), RunItem.id.desc()).limit(1))
        run = db.scalar(select(Run).where(Run.id == item.run_id)) if item is not None else None
        if item is None or run is None:
            return False
        if (item.status != 'succeeded' or item.kind not in {'tool', 'batch_row'}
                or item.finished_at is None or item.proposal_id is not None
                or (run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version)
                != (thread.owner_id, thread.store_id, thread.id, plan.id, plan.goal_version)):
            return False
    return True


def _step_state(step, outcomes, cards, *, read_completed=False):
    states = [row['status'] for row in outcomes]
    if any(state in {'uncertain', 'executing'} for state in states):
        return 'uncertain', 'result_unknown'
    if 'needs_input' in states or any(_card_state(card) == 'pending' and card.questions for card in cards.values()):
        return 'needs_input', 'employee_input'
    if any(_card_state(card) == 'pending' for card in cards.values()):
        return 'awaiting_confirmation', None
    if 'failed' in states:
        return 'failed', 'row_failed'
    if 'cancelled' in states:
        return 'cancelled', 'row_cancelled'
    if 'expired' in states:
        return 'waiting', 'expired'
    if any(state not in {'succeeded'} for state in states):
        return 'waiting', 'preparation_pending'
    # A failed re-read does not erase historical completion, but its pending
    # revalidation must block this projection and all dependent steps.
    if step.wait_reason and step.wait_reason.startswith('completion_recheck_'):
        return 'waiting', step.wait_reason
    if step.status == 'needs_input':
        return 'needs_input', step.wait_reason
    if states and all(state == 'succeeded' for state in states):
        if step.completion_conditions and step.status == 'completed':
            return 'completed', None
        return 'waiting', step.wait_reason or 'external_fact'
    if step.status in {'failed', 'cancelled', 'uncertain'}:
        return step.status, step.wait_reason
    if step.status == 'completed' and (step.completion_conditions or read_completed):
        return 'completed', None
    return 'waiting', 'external_fact' if step.status == 'completed' else step.wait_reason or 'not_prepared'


def project_legacy_plan(db, user, sid, plan):
    """A read-only legacy UI projection; runtime_status retains D1 vocabulary."""
    from . import business_assistant_service as service
    with db.no_autoflush:
        thread = _authorized_thread(db, user, sid)
        _same_scope(plan, thread)
        if plan.engine_version != 2:
            from .business_assistant_workboard import derive_steps
            ids = [step['proposal_id'] for step in plan.steps if step.get('proposal_id')]
            return {'id': plan.id, 'goal': plan.goal, 'version': plan.version,
                    'steps': derive_steps(plan.steps, _cards(db, user, thread, ids))}
        steps = _steps(db, plan)
        order = validate_dag([_step_values(step) for step in steps])
        by_key = {step.key: step for step in steps}
        current, manifests = _manifest_index(db, user, thread, plan)
        projected, statuses, case_by_key = [], {}, {}
        for value in order:
            step = by_key[value['key']]
            works = _work_for_step(db, thread, plan, step)
            rows, cards = _row_outcomes(db, user, thread, plan, step,
                current.get((step.id, step.intent_version)), manifests, works)
            if step.proposal_id:
                cards = _cards(db, user, thread, [step.proposal_id])
                rows = [{'input_item_id': None, 'position': 0, 'work_item_id': None,
                         'proposal_id': step.proposal_id, 'status': _card_state(cards[step.proposal_id]), 'reason_code': None}]
            status, reason = _step_state(step, rows, cards, read_completed=
                _stored_read_completion(db, thread, plan, step, works))
            if (status in {'waiting', 'completed'} and reason != 'expired'
                    and any(statuses.get(dep) != 'completed' for dep in step.depends_on)):
                status, reason = 'waiting', 'dependency'
            statuses[step.key] = status
            legacy = ('step_completed' if status == 'completed' else
                      {'dependency': 'waiting_dependency', 'external_fact': 'waiting_fact',
                       'expired': 'expired', 'preparation_pending': 'needs_preparation'}.get(reason, 'planned')
                      if status == 'waiting' else status)
            obj = deepcopy(step.object_ref)
            case_id = obj['id'] if obj and obj.get('type') == 'case' else None
            if case_id is None and len(cards) == 1:
                case_id = _card_case(next(iter(cards.values())))
            case_by_key[step.key] = case_id
            ids = [row['proposal_id'] for row in rows if row['proposal_id']]
            if len(ids) != len(set(ids)):
                _conflict()
            missing = [question.get('label', '必要资料') for card in cards.values()
                       if _card_state(card) == 'pending' for question in card.questions or []]
            projected.append({**value, 'position': step.position, 'status': legacy,
                'runtime_status': status, 'status_label': _LABELS.get(legacy, '请核对'),
                'wait_reason': reason, 'intent_version': step.intent_version,
                'proposal_ids': ids, 'case_id': case_id, 'route': f'case/{case_id}' if case_id else None,
                'manual_route': f'case/{case_id}' if case_id else None,
                'missing': missing, 'rows': rows,
                'evidence': '原卡和完整行实际结果；业务完成另按真实完成条件核对',
                'dependency_results': [{'step_key': dep, 'case_id': case_by_key.get(dep)}
                    for dep in step.depends_on if statuses.get(dep) == 'completed']})
        return {'id': plan.id, 'session_id': plan.session_id, 'goal': plan.goal,
            'version': plan.version, 'goal_version': plan.goal_version,
            'engine_version': 2, 'status': plan.status, 'steps': projected}


def _is_proven_fill(db, user, thread, plan, old, new, incoming, cards, old_by_key):
    if old is not None or new is None:
        return False
    candidate = cards.get(incoming.get('proposal_id'))
    if candidate is not None and new in _card_objects(candidate):
        return True
    own_step = old_by_key.get(incoming['key'])
    if own_step is not None and own_step.proposal_id is None:
        current, manifests = _manifest_index(db, user, thread, plan)
        works = _work_for_step(db, thread, plan, own_step)
        rows, current_cards = _row_outcomes(db, user, thread, plan, own_step,
            current.get((own_step.id, own_step.intent_version)), manifests, works)
        # A single convenient batch row cannot stand for the whole Step. Every
        # accepted row must have a real card proving one identical typed object.
        if rows and all(row['proposal_id'] is not None for row in rows):
            objects = [_card_objects(current_cards[row['proposal_id']]) for row in rows]
            if all(refs == [new] for refs in objects):
                return True
    for key in incoming['depends_on']:
        predecessor = old_by_key.get(key)
        if predecessor is None:
            continue
        if predecessor.status == 'completed' and predecessor.object_ref == new:
            return True
        predecessor_card = cards.get(predecessor.proposal_id)
        if predecessor_card is not None and predecessor_card.status == 'succeeded' and new in _card_objects(predecessor_card):
            return True
        if predecessor.proposal_id is None:
            current, manifests = _manifest_index(db, user, thread, plan)
            works = _work_for_step(db, thread, plan, predecessor)
            _, preceding_cards = _row_outcomes(db, user, thread, plan, predecessor,
                current.get((predecessor.id, predecessor.intent_version)), manifests, works)
            if any(card.status == 'succeeded' and new in _card_objects(card) for card in preceding_cards.values()):
                return True
    return False


def _protect_and_compare(db, user, thread, plan, old_steps, incoming, cards):
    old_by_key = {step.key: step for step in old_steps}
    new_by_key = {step['key']: step for step in incoming}
    structure = set(old_by_key) != set(new_by_key)
    for old in old_steps:
        prior = _step_values(old)
        new = new_by_key.get(old.key)
        works = _work_for_step(db, thread, plan, old)
        manifest_exists = db.scalar(select(RunItem.id).join(Run, Run.id == RunItem.run_id).where(
            Run.owner_id == thread.owner_id, Run.store_id == thread.store_id, Run.session_id == thread.id,
            RunItem.kind == 'tool', RunItem.tool_name == 'prepare_inputs',
            RunItem.validated_arguments['scope']['step_id'].as_string() == old.id).limit(1))
        old_card = cards.get(old.proposal_id)
        if old.proposal_id and old_card is None:
            _conflict()
        frozen = db.scalar(select(RunItem.id).where(RunItem.kind == 'confirmation',
            RunItem.proposal_id == old.proposal_id)) if old.proposal_id else None
        protected = bool(works or manifest_exists or frozen or old.status in {'completed', 'failed', 'cancelled', 'uncertain'}
                         or old_card and _card_state(old_card) != 'pending')
        if new is None:
            if protected:
                _conflict('已有准备或办理历史的步骤不能删除')
            continue
        if protected:
            for key in ('proposal_id', 'form_ref', 'workflow_id', 'required'):
                if prior[key] != new[key]:
                    _conflict('已有办理记录的步骤不能重新绑定或改变必要性')
            if prior['object_ref'] is not None and prior['object_ref'] != new['object_ref']:
                _conflict('已有办理记录的原单不能清空或更换')
            if (prior['object_ref'] is None and new['object_ref'] is not None
                    and not _is_proven_fill(db, user, thread, plan, None, new['object_ref'], new, cards, old_by_key)):
                _conflict('已有办理历史的步骤只能补入已证明关联的原单')
            if old.status == 'completed' and any(prior[key] != new[key] for key in ('depends_on', 'conditions', 'completion_conditions')):
                _conflict('已完成步骤不能通过改条件重新解释或重办')
        for key in _STEP_FIELDS:
            if prior[key] == new[key]:
                continue
            if key == 'proposal_id' and prior[key] is None:
                continue
            if key == 'object_ref' and _is_proven_fill(db, user, thread, plan, prior[key], new[key], new, cards, old_by_key):
                continue
            structure = True
    return structure


def _stop_old_runs(db, thread, plan, *, pause_grants=True, error_code='version_conflict'):
    from .assistant_runtime_runner import _manifest_data
    paused = []
    if pause_grants:
        for grant in db.scalars(select(FollowupGrant).where(FollowupGrant.plan_id == plan.id, FollowupGrant.status == 'active')):
            _same_scope(grant, thread)
            grant.status = 'paused'
            grant.stop_reason = 'goal_changed'
            paused.append(grant)
    scope = (Run.owner_id == thread.owner_id, Run.store_id == thread.store_id,
             Run.session_id == thread.id, Run.status.in_({'queued', 'running'}))
    linked_ids = set(db.scalars(select(Run.id).join(RunItem, RunItem.run_id == Run.id)
        .join(WorkItem, WorkItem.id == RunItem.work_item_id).where(*scope,
            WorkItem.plan_id == plan.id, WorkItem.owner_id == thread.owner_id,
            WorkItem.store_id == thread.store_id, WorkItem.session_id == thread.id)))
    manifests = db.scalars(select(RunItem).join(Run, Run.id == RunItem.run_id).where(*scope,
        RunItem.kind == 'tool', RunItem.tool_name == 'prepare_inputs',
        RunItem.validated_arguments['scope']['plan_id'].as_string() == plan.id))
    for item in manifests:
        accepted = _manifest_data(item)['scope']
        if ((accepted['owner_id'], accepted['store_id'], accepted['session_id'])
                != (thread.owner_id, thread.store_id, thread.id)):
            _conflict()
        linked_ids.add(item.run_id)
    for run in db.scalars(select(Run).where(*scope)):
        if run.plan_id != plan.id and run.id not in linked_ids:
            continue
        _same_scope(run, thread)
        if run.plan_id is not None and run.plan_id != plan.id:
            _conflict('执行记录与其已接受计划不一致，请先核对')
        run.stop_requested = True
        if run.status == 'queued':
            run.status = 'cancelled'
            run.finished_at = utcnow()
        run.error_code = error_code
    if paused:
        _emit_grants(db, paused)


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ResolvedPlanSave:
    """Opaque, one-use result of completed plan reads; never model authority."""


@dataclass(frozen=True)
class PlanSaveResult:
    response: dict
    plan_id: str
    plan_version: int
    goal_version: int
    created: bool
    reused: bool
    structure_changed: bool
    stopped_self: bool


_resolved_plan_saves = WeakKeyDictionary()
_PLAN_RESOLUTION_SECONDS = 60


def _plan_save_identity(user, sid, store_id):
    return (user.id, store_id, sid, user.role, user.access_version)


def _runtime_plan_source(db, principal, user, sid, plan_id, *, clock=None):
    if principal is None:
        return
    from .assistant_runtime_principal import revalidate_principal
    revalidate_principal(db, principal, clock=clock)
    if user is not principal or principal.session_id != sid or principal.run_id is None:
        _conflict('计划保存必须属于本次执行的真实事项，不能重新绑定模型提供的编号')
    if principal.plan_id == plan_id:
        return
    # A real employee MCP command may explicitly edit an owned Plan, but its
    # Run remains unbound. Saving is neither Grant control nor a continuation.
    # The immutable MCP source is checked lazily to avoid a module import cycle.
    from .assistant_runtime_mcp import is_mcp_run
    run = db.scalar(select(Run).where(Run.id == principal.run_id,
        Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
        Run.session_id == sid))
    if (principal.auth_kind != 'login' or principal.plan_id is not None
            or principal.goal_version is not None or run is None or not is_mcp_run(run)):
        _conflict('计划保存必须属于本次执行的真实事项，不能重新绑定模型提供的编号')


async def resolve_plan(db, request, user, sid, config, args, *, principal=None, clock=None):
    """Complete all original reads and issue a same-Session, one-use save token.

    Runtime callers pass their actual issued principal. No plan, step, event or
    Run is written here. The legacy wrapper retains its original request path.
    """
    from . import business_assistant_service as service
    from .business_assistant_business_tools import WorkPlan
    from .config import settings
    from .assistant_runtime_principal import RuntimePrincipal, runtime_request_context
    service.require_preparation_read_phase(db)
    context = runtime_request_context(request) if hasattr(request, 'scope') else None
    if (context is not None and (context.db is not db or context.principal is not principal)
            or principal is not None and context is None
            or type(user) is RuntimePrincipal and principal is None):
        _conflict('内部计划必须通过当前执行的受保护保存接口')
    try:
        data = WorkPlan.model_validate(args).model_dump(mode='json')
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, '计划字段不正确，请核对步骤及条件') from None
    if data['schema_version'] != 2:
        _conflict('此计划已使用结构化步骤，请按 schema_version=2 读取和修改，不能降级覆盖')
    if not settings.assistant_runtime_enabled:
        raise HTTPException(503, '结构化业务计划尚未开启')
    _runtime_plan_source(db, principal, user, sid, data['plan_id'], clock=clock)
    incoming = data['steps']
    for step in incoming:
        if step.get('case_id') is not None:
            step['object_ref'] = {'type': 'case', 'id': step['case_id']}
        step.pop('case_id', None)
    incoming = validate_dag(incoming)
    payload = {'goal': data['goal'], 'steps': incoming}
    if service.scrub(payload) != payload:
        raise HTTPException(422, '计划含隐藏信息或过长内容，请只写业务目标与必要步骤')
    with db.no_autoflush:
        thread = _authorized_thread(db, user, sid)
        initial_session_version = thread.version
        rid = thread.busy_token or 'manual-' + uuid4().hex
        if principal is not None:
            from .assistant_runtime_queue import runtime_busy_token
            if thread.busy_token != runtime_busy_token(principal.run_id):
                _conflict('计划保存必须持有本次执行的会话忙租约')
        plan = _owned_plan(db, thread, data['plan_id'], rid)
        expected = plan.version if plan else None
        if plan and data['expected_version'] != expected:
            _conflict()
        if plan is None and data['expected_version'] is not None:
            _conflict('新计划没有旧版本')
        if plan and plan.status in {'completed', 'cancelled'}:
            _conflict('事项已经结束，不能通过重新规划自动重开')
        initial_steps = _steps(db, plan) if plan and plan.engine_version == 2 else []
        initial_versions = {step.id: step.version for step in initial_steps}
        original_plan = ((plan.id, plan.version, plan.goal_version, plan.engine_version, plan.status)
                         if plan is not None else None)
        identity = _plan_save_identity(user, sid, thread.store_id)
        old_map = {step.key: step for step in initial_steps}
        _private_refs(db, user, thread, incoming, plan=plan, existing=old_map)
    await _validate_native_refs(db, request, user, thread, config, incoming)
    _runtime_plan_source(db, principal, user, sid, data['plan_id'], clock=clock)
    resolved = ResolvedPlanSave()
    _resolved_plan_saves[resolved] = {
        'session_ref': ref(db), 'bind': db.get_bind(), 'principal': principal,
        'principal_identity': _condition_identity(principal) if principal is not None else None,
        'identity': identity, 'data': deepcopy(data), 'incoming': deepcopy(incoming),
        'rid': rid, 'session_version': initial_session_version, 'plan': original_plan,
        'step_versions': initial_versions, 'issued_at': monotonic(),
    }
    return resolved


def persist_plan(db, user, sid, resolved, *, principal=None, clock=None):
    """Recheck and flush the original plan save, without commits or native I/O.

    Runtime must first call queue.lock_for_write and must own the surrounding
    rollback, Run binding, item/event writes and final authorization/commit.
    """
    state = _resolved_plan_saves.pop(resolved, None) if type(resolved) is ResolvedPlanSave else None
    if (state is None or state['session_ref']() is not db or state['bind'] is not db.get_bind()
            or state['principal'] is not principal
            or monotonic() - state['issued_at'] > _PLAN_RESOLUTION_SECONDS
            or state['identity'] != _plan_save_identity(user, sid, state['identity'][1])):
        _conflict('本轮计划核对依据已失效，请重新读取后保存')
    if db.new or db.dirty or db.deleted:
        _conflict('计划必须在其他助手记录写入前核对原版本')
    data, incoming, rid = state['data'], state['incoming'], state['rid']
    original_plan = state['plan']
    initial_session_version, initial_versions = state['session_version'], state['step_versions']
    _runtime_plan_source(db, principal, user, sid, data['plan_id'], clock=clock)
    if principal is not None:
        from .assistant_runtime_events import _capability
        from .assistant_runtime_queue import runtime_busy_token
        if state['principal_identity'] != _condition_identity(principal):
            _conflict()
        _capability(db, principal, clock=clock)
    # Reads may end their own transactions. Capture primitive versions before
    # them, then re-fetch and compare rather than accepting a refreshed version.
    with db.no_autoflush:
        thread = _authorized_thread(db, user, sid)
        if (_plan_save_identity(user, sid, thread.store_id) != state['identity']
                or principal is not None and thread.busy_token != runtime_busy_token(principal.run_id)):
            _conflict()
        from .business_assistant_models import AssistantSession
        fresh_session_version = db.scalar(select(AssistantSession.version).where(AssistantSession.id == thread.id))
        if fresh_session_version != initial_session_version:
            _conflict()
        current = _owned_plan(db, thread, data['plan_id'], rid, refresh=True)
        current_identity = ((current.id, current.version, current.goal_version, current.engine_version, current.status)
                            if current is not None else None)
        if current_identity != original_plan:
            _conflict()
        plan = current
        old_steps = _steps(db, plan, refresh=True) if plan and plan.engine_version == 2 else []
        if {step.id: step.version for step in old_steps} != initial_versions:
            _conflict()
        old_map = {step.key: step for step in old_steps}
        all_refs = incoming + [{**_step_values(step)} for step in old_steps]
        cards = _private_refs(db, user, thread, all_refs, plan=plan, existing=old_map)
        upgrading = plan is not None and plan.engine_version == 1
        if upgrading:
            legacy = {step['key']: step for step in plan.steps}
            requested = {step['key']: step for step in incoming}
            if set(legacy) - set(requested):
                _conflict('升级必须保留旧计划步骤和办理引用')
            for key, old in legacy.items():
                new = requested[key]
                if any(old.get(field, '' if field == 'wait_for' else None) != new.get(field)
                       for field in ('title', 'wait_for', 'proposal_id')):
                    _conflict('升级必须保留旧标题、等待说明和原卡引用')
                if old.get('case_id') and new.get('object_ref') != {'type': 'case', 'id': old['case_id']}:
                    _conflict('升级不能清空或更换原计划单据')
            structure = True
        else:
            graph_changed = _protect_and_compare(db, user, thread, plan, old_steps, incoming, cards) if plan else False
            structure = bool(plan and (plan.goal != data['goal'] or graph_changed))
        same = bool(plan and not upgrading and plan.goal == data['goal']
                    and [_step_values(step) for step in old_steps] == incoming)
        if same:
            response = {'status': 200, 'plan_id': plan.id, 'version': plan.version,
                        'goal_version': plan.goal_version, 'engine_version': 2, 'reused': True, 'business_executed': False}
            return PlanSaveResult(response, plan.id, plan.version, plan.goal_version,
                                  False, True, False, False)
    created = plan is None
    try:
        # Session CAS serializes changes with other assistant writes. All native
        # reads are complete; no HTTP may occur after this boundary.
        thread.version += 1
        thread.updated_at = utcnow()
        db.info['assistant_preparation_transaction'] = db.get_transaction()
        db.flush()
        if plan is None:
            plan = AssistantWorkPlan(id=str(uuid4()), owner_id=user.id, store_id=thread.store_id,
                session_id=sid, request_id=rid, goal=data['goal'], steps=[], engine_version=2,
                goal_version=1, status='active', version=1)
            db.add(plan)
            db.flush()
        else:
            plan.goal = data['goal']
            plan.engine_version = 2
            plan.version += 1
            plan.updated_at = utcnow()
            if structure:
                plan.goal_version += 1
                _stop_old_runs(db, thread, plan)
        wanted = {step['key'] for step in incoming}
        for old in old_steps:
            if old.key not in wanted:
                db.delete(old)
        for position, values in enumerate(incoming):
            row = old_map.get(values['key'])
            if row is None:
                row = PlanStep(id=str(uuid4()), plan_id=plan.id, position=position,
                    **deepcopy(values), status='waiting', wait_reason='not_prepared',
                    intent_version=1, version=1)
                db.add(row)
            else:
                row.position = position
                if row.conditions != values['conditions'] or row.completion_conditions != values['completion_conditions']:
                    row.last_evidence = None
                for key, value in values.items():
                    setattr(row, key, deepcopy(value))
                row.updated_at = utcnow()
        db.flush()
        _emit_plan_signal(db, plan)
    except (StaleDataError, IntegrityError):
        db.rollback()
        _conflict()
    except OperationalError as exc:
        db.rollback()
        if 'locked' in str(exc).lower() or getattr(exc.orig, 'sqlstate', None) in {'40001', '40P01'}:
            _conflict()
        raise
    except Exception:
        # A later scope/ref guard must not leave pending Plan/Step mutations for
        # the legacy issue logger (which commits) to accidentally persist.
        db.rollback()
        raise
    response = {'status': 200, 'plan_id': plan.id, 'version': plan.version,
        'goal_version': plan.goal_version, 'engine_version': 2, 'business_executed': False,
        'notice': '仅保存办事计划；原卡与办理记录保持，未开启跟进或执行业务。'}
    run = db.get(Run, principal.run_id) if principal is not None else None
    return PlanSaveResult(response, plan.id, plan.version, plan.goal_version,
                          created, False, structure, bool(run is not None and run.stop_requested))


async def save_plan(db, request, user, sid, config, args):
    """Original employee/MCP entry point, preserving its commit/error contract."""
    from . import business_assistant_service as service
    resolved = await resolve_plan(db, request, user, sid, config, args)
    try:
        result = persist_plan(db, user, sid, resolved)
        if not result.reused:
            service.commit(db)
        return result.response
    except (StaleDataError, IntegrityError):
        db.rollback()
        _conflict()
    except OperationalError as exc:
        db.rollback()
        if 'locked' in str(exc).lower() or getattr(exc.orig, 'sqlstate', None) in {'40001', '40P01'}:
            _conflict()
        raise
    except Exception:
        db.rollback()
        raise


def _emit_plan_signal(db, plan):
    """Reference-only source, in the caller's existing Plan/Step transaction."""
    from .config import settings
    if not (settings.assistant_runtime_enabled or settings.assistant_notifications_enabled):
        return
    from .assistant_runtime_outbox import emit_wake_event
    db.flush()
    emit_wake_event(db, f'plan:{plan.id}:{plan.version}:{plan.status}', 'plan', {
        'store_id': plan.store_id, 'plan_id': plan.id,
        'source_ref': {'type': 'plan', 'id': plan.id, 'version': plan.version}})


def _emit_grants(db, grants):
    from .assistant_runtime_outbox import emit_wake_event
    db.flush()
    for grant in grants:
        emit_wake_event(db, f'grant:{grant.id}:{grant.version}:{grant.status}', 'grant', {
            'store_id': grant.store_id, 'plan_id': grant.plan_id,
            'source_ref': {'type': 'grant', 'id': grant.id, 'version': grant.version}})


def _plan_grants(db, thread, plan, *, refresh=False):
    query = select(FollowupGrant).where(FollowupGrant.plan_id == plan.id).order_by(
        FollowupGrant.granted_at.desc(), FollowupGrant.id.desc())
    if refresh:
        query = query.execution_options(populate_existing=True)
    grants = list(db.scalars(query))
    for grant in grants:
        _same_scope(grant, thread)
        if (grant.owner_role, grant.access_version) != (thread.owner_role, thread.access_version):
            _conflict('历史授权身份不一致，不能覆盖旧授权范围')
    if sum(grant.status == 'active' for grant in grants) > 1:
        _conflict('事项存在多个启用授权，请先核对')
    return grants


def _current_grant(grants):
    return next((g for g in grants if g.status == 'active'), None) or next(
        (g for g in grants if g.status == 'paused'), None) or next(iter(grants), None)


def _plan_view(plan, projection, grant, *, now=None):
    from .assistant_runtime_schemas import PlanView
    terminal = plan.status in {'completed', 'cancelled'}
    now = utcnow() if now is None else now
    expired = grant is not None and grant.expires_at is not None and grant.expires_at <= now
    actions = [] if terminal else ['revoke']
    if not terminal:
        if grant is None:
            if plan.status == 'active':
                actions.insert(0, 'enable')
        elif grant.status == 'active' and plan.status == 'active' and not expired:
            actions.insert(0, 'pause')
        elif (grant.status == 'paused' or expired and grant.status == 'active'
              or grant.status == 'revoked' and grant.stop_reason == 'expired'):
            actions.insert(0, 'resume')
    steps = []
    for step in projection['steps']:
        reason = step['wait_reason']
        if (step['required'] and not step['completion_conditions'] and step['runtime_status'] == 'waiting'
                and reason in {None, 'not_prepared', 'external_fact'}):
            reason = 'completion_conditions_missing'
        steps.append({'key': step['key'], 'position': step['position'],
            'title': step['title'], 'wait_for': step['wait_for'],
            'status': step['runtime_status'], 'wait_reason': reason,
            'waiting_label': waiting_label(reason),
            'proposal_id': step['proposal_id'], 'proposal_ids': step['proposal_ids'],
            'object_ref': step['object_ref'], 'manual_route': step['manual_route']})
    # An expired active audit row has no effective authorization. This is a
    # read-only view; the dispatcher persists revocation separately.
    grant_status = 'paused' if expired and grant.status == 'active' else grant.status if grant else None
    return PlanView.model_validate({'id': plan.id, 'session_id': plan.session_id,
        'version': plan.version, 'goal_version': plan.goal_version, 'goal': plan.goal,
        'status': plan.status, 'steps': steps,
        'grant': {'status': grant_status,
                  'enabled': grant_status == 'active',
                  'stop_reason': 'expired' if expired and grant.status == 'active' else grant.stop_reason if grant else None},
        'allowed_actions': actions}).model_dump(mode='json')


def _new_grant(thread, plan, now):
    return FollowupGrant(id=str(uuid4()), plan_id=plan.id, owner_id=thread.owner_id,
        store_id=thread.store_id, session_id=thread.id, owner_role=thread.owner_role,
        access_version=thread.access_version, goal_version=plan.goal_version,
        status='active', granted_at=now, expires_at=None, revoked_at=None, version=1)


def _change_followup(db, thread, plan, grants, action, now):
    """Mutate only lifecycle rows, with the caller holding Session then Plan."""
    current = _current_grant(grants)
    if plan.status == 'cancelled' and action == 'revoke':
        return [], False
    if plan.status in {'completed', 'cancelled'}:
        _conflict('事项已经结束，不能重新开启跟进')
    changed = []
    if action == 'enable':
        if current is not None:
            if (current.status == 'active' and current.goal_version == plan.goal_version
                    and plan.status == 'active' and (current.expires_at is None or current.expires_at > now)):
                return [], False
            _conflict('事项已有授权历史，请核对后使用恢复或结束')
        if plan.status != 'active':
            _conflict('暂停事项不能通过开启动作绕过恢复核对')
        current = _new_grant(thread, plan, now)
        db.add(current)
        grants.insert(0, current)
        changed.append(current)
    elif action == 'pause':
        if plan.status == 'paused' and (current is None or current.status != 'active'):
            return [], False
        if current is None or current.status != 'active':
            _conflict('事项尚未开启持续跟进')
        plan.status = 'paused'
        current.status, current.stop_reason = 'paused', 'employee_paused'
        changed.append(current)
    elif action == 'resume':
        if (current is not None and current.status == 'active' and plan.status == 'active'
                and current.goal_version == plan.goal_version
                and (current.expires_at is None or current.expires_at > now)):
            return [], False
        expired_history = current is not None and current.status == 'revoked' and current.stop_reason == 'expired'
        if current is None or current.status not in {'paused', 'active'} and not expired_history:
            _conflict('没有可恢复的原授权，已撤销授权不能原地复活')
        if current.status == 'active' and (current.expires_at is None or current.expires_at > now):
            _conflict('原授权范围与事项不一致，请先核对')
        expired = current.expires_at is not None and current.expires_at <= now
        if current.goal_version == plan.goal_version and not expired and not expired_history:
            current.status, current.stop_reason = 'active', None
            changed.append(current)
        else:
            for grant in grants:
                if grant.status in {'active', 'paused'}:
                    grant.status, grant.revoked_at = 'revoked', now
                    grant.stop_reason = 'expired' if expired else 'goal_changed'
                    changed.append(grant)
            # Release the unique active slot before inserting the replacement.
            db.flush()
            current = _new_grant(thread, plan, now)
            db.add(current)
            grants.insert(0, current)
            changed.append(current)
        plan.status = 'active'
    elif action == 'revoke':
        plan.status, plan.next_check_at = 'cancelled', None
        for grant in grants:
            if grant.status in {'active', 'paused'}:
                grant.status, grant.revoked_at, grant.stop_reason = 'revoked', now, 'employee_ended'
                changed.append(grant)
    if action in {'pause', 'resume', 'revoke'}:
        _stop_old_runs(db, thread, plan, pause_grants=False, error_code='precondition_conflict')
    return changed, True


def _followup_failure(db, exc):
    db.rollback()
    if isinstance(exc, (StaleDataError, IntegrityError)):
        _conflict()
    if isinstance(exc, OperationalError) and (
            'locked' in str(exc).lower() or getattr(exc.orig, 'sqlstate', None) in {'40001', '40P01'}):
        _conflict()
    raise exc


def followup_transition(db, request, user, plan_id, args, *, clock=utcnow, read_session_factory=None):
    """Employee-only lifecycle service; no route/tool/worker is enabled here."""
    from . import business_assistant_service as service
    from .assistant_runtime_schemas import FollowupAction
    from .assistant_runtime_principal import (
        _reader, _time, _enabled, principal_for_followup_request, revalidate_principal,
    )
    from .business_assistant_models import AssistantSession
    from .tenancy import set_scope
    service.require_preparation_read_phase(db)
    try:
        command = FollowupAction.model_validate(args)
    except (ValueError, TypeError):
        raise HTTPException(422, '请核对跟进动作和事项版本') from None
    with db.no_autoflush:
        seed = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
            AssistantWorkPlan.owner_id == user.id,
            AssistantWorkPlan.store_id == getattr(user, '_active_store_id', None)))
        if seed is None:
            raise HTTPException(404, '计划不存在或不可访问')
        sid = seed.session_id
    principal = principal_for_followup_request(db, request, user, sid, plan_id,
        action=command.action, clock=clock, read_session_factory=read_session_factory)
    with _reader(db, read_session_factory) as snapshot_db:
        set_scope(snapshot_db, [principal.store_id], principal.store_id)
        thread = _authorized_thread(snapshot_db, principal, sid)
        snapshot_plan = _owned_plan(snapshot_db, thread, plan_id)
        if snapshot_plan.version != command.expected_version:
            _conflict()
        if snapshot_plan.engine_version != 2:
            _conflict('请先显式升级为结构化事项，再开启跟进')
        session_version = thread.version
        projection = project_legacy_plan(snapshot_db, principal, sid, snapshot_plan)
        step_versions = {step.id: step.version for step in _steps(snapshot_db, snapshot_plan)}
    try:
        revalidate_principal(db, principal)
        with db.no_autoflush:
            thread = db.scalar(select(AssistantSession).where(AssistantSession.id == sid,
                AssistantSession.owner_id == principal.actor_id,
                AssistantSession.store_id == principal.store_id).with_for_update()
                .execution_options(populate_existing=True))
            plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
                AssistantWorkPlan.owner_id == principal.actor_id,
                AssistantWorkPlan.store_id == principal.store_id,
                AssistantWorkPlan.session_id == sid).with_for_update().execution_options(populate_existing=True))
            if (thread is None or plan is None or thread.version != session_version
                    or plan.version != command.expected_version or plan.engine_version != 2
                    or {step.id: step.version for step in _steps(db, plan, refresh=True)} != step_versions):
                _conflict()
            grants = _plan_grants(db, thread, plan, refresh=True)
        now = _time(clock())
        with db.no_autoflush:
            changed, modified = _change_followup(db, thread, plan, grants, command.action, now)
        if not modified:
            result = _plan_view(plan, projection, _current_grant(grants), now=now)
            revalidate_principal(db, principal)
            return result
        thread.version += 1
        thread.updated_at = now
        plan.version += 1
        plan.updated_at = now
        db.info['assistant_preparation_transaction'] = db.get_transaction()
        _emit_grants(db, changed)
        # A no-grant employee end still has a real lifecycle event.
        if not changed:
            from .assistant_runtime_outbox import emit_wake_event
            emit_wake_event(db, f'plan:{plan.id}:{plan.version}:{plan.status}', 'grant', {
                'store_id': plan.store_id, 'plan_id': plan.id,
                'source_ref': {'type': 'plan', 'id': plan.id, 'version': plan.version}})
        result = _plan_view(plan, projection, _current_grant(grants), now=now)
        revalidate_principal(db, principal)
        if command.action in {'enable', 'resume'}:
            _enabled('grant')
        service.commit(db)
    except Exception as exc:
        _followup_failure(db, exc)
    try:
        revalidate_principal(db, principal)
    except HTTPException as exc:
        raise HTTPException(exc.status_code, '授权变更已记录；当前身份已失效，请重新登录查看仍可访问的事项') from None
    except Exception:
        raise HTTPException(503, '授权变更已记录；暂不能核对当前身份，请重新查询可访问的事项') from None
    return result


def _locked_control_rows(db, owner_id, store_id, session_id, plan_id):
    from .business_assistant_models import AssistantSession
    thread = db.scalar(select(AssistantSession).where(AssistantSession.id == session_id,
        AssistantSession.owner_id == owner_id, AssistantSession.store_id == store_id)
        .with_for_update().execution_options(populate_existing=True))
    plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id,
        AssistantWorkPlan.owner_id == owner_id, AssistantWorkPlan.store_id == store_id,
        AssistantWorkPlan.session_id == session_id).with_for_update().execution_options(populate_existing=True))
    if thread is None or plan is None:
        _conflict()
    return thread, plan


def _stop_grant_runs(db, thread, grant, *, error_code):
    for run in db.scalars(select(Run).where(Run.grant_id == grant.id,
            Run.status.in_({'queued', 'running'}))):
        _same_scope(run, thread)
        if run.plan_id != grant.plan_id or run.goal_version != grant.goal_version:
            _conflict()
        run.stop_requested, run.error_code = True, error_code
        if run.status == 'queued':
            run.status, run.finished_at = 'cancelled', utcnow()


def invalidate_followup_grant(db, grant_id, expected_version, *, clock=utcnow, read_session_factory=None):
    """Internal, no-Run cleanup; independently prove expiry/permission loss.

    No model/HTTP route registers this service. It cannot disable valid grants,
    expose old conversations, or overwrite a newer goal's authorization.
    """
    from . import business_assistant_service as service
    from .assistant_runtime_principal import invalid_grant_snapshot, _time
    service.require_preparation_read_phase(db)
    facts = invalid_grant_snapshot(db, grant_id, expected_version,
        clock=clock, read_session_factory=read_session_factory)
    if facts['status'] == 'revoked':
        return {'changed': False, 'grant_id': grant_id}
    try:
        with db.no_autoflush:
            thread, plan = _locked_control_rows(db, facts['owner_id'], facts['store_id'],
                facts['session_id'], facts['plan_id'])
            if thread.version != facts['session_version'] or plan.version != facts['plan_version']:
                _conflict()
            grant = db.scalar(select(FollowupGrant).where(FollowupGrant.id == grant_id)
                .with_for_update().execution_options(populate_existing=True))
            if grant is None or grant.version != expected_version:
                _conflict()
            _same_scope(grant, thread)
            active = list(db.scalars(select(FollowupGrant).where(FollowupGrant.plan_id == plan.id,
                FollowupGrant.status == 'active')))
            current_scope = plan.goal_version == grant.goal_version and all(g.id == grant.id for g in active)
            grant.status, grant.stop_reason, grant.revoked_at = 'revoked', facts['reason'], _time(clock())
            if current_scope and plan.status in {'active', 'paused'}:
                plan.status, plan.next_check_at = 'paused', None
                plan.version += 1
                plan.updated_at = _time(clock())
                _stop_old_runs(db, thread, plan, pause_grants=False, error_code='permission_denied')
            else:
                _stop_grant_runs(db, thread, grant, error_code='permission_denied')
            thread.version += 1
            thread.updated_at = _time(clock())
        # Recheck committed authority before the lifecycle write. Do not treat
        # an old failed read or a caller's reason string as revocation evidence.
        latest = invalid_grant_snapshot(db, grant_id, expected_version,
            clock=clock, read_session_factory=read_session_factory)
        grant.stop_reason = latest['reason']
        _emit_grants(db, [grant])
        service.commit(db)
    except Exception as exc:
        _followup_failure(db, exc)
    return {'changed': True, 'grant_id': grant_id}


@dataclass(frozen=True, slots=True)
class StepConditionResult:
    step_id: str
    key: str
    status: str
    wait_reason: str | None
    preparation_ready: bool
    completion_satisfied: bool
    evidence_json: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class PlanConditionEvaluation:
    plan_id: str
    goal_version: int
    fingerprint: str
    steps: tuple[StepConditionResult, ...]


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class AppliedConditionProof:
    plan_id: str
    plan_version: int
    fingerprint: str
    required_complete: bool


# Only objects issued here are accepted. Copying a dataclass, or replaying its
# JSON, cannot create authority. Tokens expire and are consumed exactly once.
_evaluations = WeakKeyDictionary()
_completion_proofs = WeakKeyDictionary()
_CONDITION_PROOF_SECONDS = 60


def _condition_scope(db, principal):
    from .tenancy import set_scope
    scope = db.info.get('store_scope')
    write_store = db.info.get('write_store')
    if scope is None and write_store is None:
        set_scope(db, [principal.store_id], principal.store_id)
    elif (scope not in {(principal.store_id,), (principal.store_id, 0), (0, principal.store_id)}
          or write_store != principal.store_id):
        _conflict('条件保存必须使用当前员工的单店范围')


def _condition_identity(principal):
    return (principal._bind, principal.actor_id, principal.store_id, principal.role,
            principal.access_version, principal.session_id, principal.run_id,
            principal.plan_id, principal.goal_version, principal.auth_kind,
            principal.grant_id, principal._login_ref, principal.lease_owner, principal.fence)


def _condition_sources(db, thread, plan, steps):
    """Version all assistant inputs, including complete manifests and read attempts."""
    works = list(db.scalars(select(WorkItem).where(WorkItem.plan_id == plan.id)
        .execution_options(populate_existing=True)))
    for work in works:
        _same_scope(work, thread)
    work_ids = [work.id for work in works]
    card_ids = {step.proposal_id for step in steps if step.proposal_id}
    for step in steps:
        card_ids.update(value['proposal_id'] for value in
            [*(step.conditions or []), *(step.completion_conditions or [])]
            if value.get('type') == 'proposal_succeeded')
    cards = list(db.scalars(select(AssistantProposal).where(or_(
        AssistantProposal.id.in_(card_ids), AssistantProposal.source_work_item_id.in_(work_ids)))
        .execution_options(populate_existing=True)))
    for card in cards:
        _same_scope(card, thread)
        if card.owner_role != thread.owner_role or card.access_version != thread.access_version:
            _conflict()
    card_ids.update(card.id for card in cards)
    items = list(db.scalars(select(RunItem).where(or_(
        RunItem.work_item_id.in_(work_ids), RunItem.proposal_id.in_(card_ids)))
        .execution_options(populate_existing=True)))
    manifests = list(db.scalars(select(RunItem).join(Run, Run.id == RunItem.run_id)
        .where(Run.owner_id == thread.owner_id, Run.store_id == thread.store_id,
               Run.session_id == thread.id, RunItem.kind == 'tool', RunItem.tool_name == 'prepare_inputs')
        .execution_options(populate_existing=True)))
    items_by_id = {item.id: item for item in items}
    for item in manifests:
        args = item.validated_arguments
        if isinstance(args, dict) and isinstance(args.get('scope'), dict) and args['scope'].get('plan_id') == plan.id:
            items_by_id[item.id] = item
    run_ids = {item.run_id for item in items_by_id.values() if item.run_id}
    runs = list(db.scalars(select(Run).where(Run.id.in_(run_ids)).execution_options(populate_existing=True)))
    for run in runs:
        _same_scope(run, thread)
    # Lease renewal may change Run.version without changing these read facts.
    return (tuple(sorted((row.id, row.version) for row in works)),
            tuple(sorted((row.id, row.version) for row in cards)),
            tuple(sorted((row.id, row.version) for row in items_by_id.values())),
            tuple(sorted((row.id, row.status, row.stop_requested, row.goal_version or 0) for row in runs)))


def _condition_snapshot(db, principal):
    thread = _authorized_thread(db, principal, principal.session_id)
    plan = _owned_plan(db, thread, principal.plan_id, refresh=True)
    if plan.engine_version != 2 or plan.status != 'active' or plan.goal_version != principal.goal_version:
        _conflict('仅当前有效执行可重新核对进行中的事项')
    steps = _steps(db, plan, refresh=True)
    projection = project_legacy_plan(db, principal, principal.session_id, plan)
    by_key = {value['key']: value for value in projection['steps']}
    values = []
    for step in steps:
        works = _work_for_step(db, thread, plan, step)
        current = [work for work in works.values() if work.intent_version == step.intent_version]
        read_ids = tuple(sorted(work.id for work in current)) if (current and not step.proposal_id
            and all(work.item_kind == 'read' for work in current)) else ()
        values.append({**_step_values(step), 'id': step.id, 'version': step.version,
            'intent_version': step.intent_version, 'status': step.status,
            'wait_reason': step.wait_reason, 'last_evidence': deepcopy(step.last_evidence),
            'read_ids': read_ids, 'rows': deepcopy(by_key[step.key]['rows']),
            'projected_status': by_key[step.key]['runtime_status'],
            'projected_reason': by_key[step.key]['wait_reason']})
    return {'plan_version': plan.version, 'session_version': thread.version,
        'goal_version': plan.goal_version, 'step_versions': tuple((step.id, step.version) for step in steps),
        'sources': _condition_sources(db, thread, plan, steps), 'steps': values}


def _snapshot_guard(snapshot):
    return (snapshot['plan_version'], snapshot['session_version'], snapshot['goal_version'],
            snapshot['step_versions'], snapshot['sources'])


def _evidence_json(values):
    from .assistant_runtime_schemas import EvidenceRef
    return tuple(sorted({json.dumps(EvidenceRef.model_validate(value).model_dump(mode='json'),
        ensure_ascii=False, sort_keys=True, separators=(',', ':')) for value in values}))


def _evaluated_step(step, preparation, completion, dependencies_complete):
    status, reason = step['projected_status'], step['projected_reason']
    row_states = {row['status'] for row in step['rows']}
    strong = (status in {'awaiting_confirmation', 'failed', 'uncertain', 'cancelled'}
              or status == 'needs_input' and (reason == 'employee_input' or 'needs_input' in row_states))
    row_pending = bool(row_states - {'succeeded'})
    current_complete = completion.satisfied and not completion.unknown and bool(completion.evidence)
    if strong or row_pending:
        current_complete = False
    elif not dependencies_complete:
        status, reason, current_complete = ('completed', 'completion_recheck_dependency', False) if step['status'] == 'completed' else ('waiting', 'dependency', False)
    elif current_complete:
        status = 'completed'
        reason = 'read_completed' if completion.reason == 'read_completed' else None
    elif (completion.unknown or not completion.evidence) and step['status'] == 'completed':
        # Preserve historical completion on transport/visibility failure; the
        # explicit recheck marker makes projection and dependencies wait.
        status, reason = 'completed', 'completion_recheck_required'
    elif (completion.reason in {'completion_conditions_missing', 'completion_evidence_missing',
                                'explicit_time_missing', 'time_source_missing'}
          or not preparation.satisfied and preparation.reason in {'explicit_time_missing', 'time_source_missing'}):
        status = 'needs_input'
        reason = (preparation.reason if not preparation.satisfied and preparation.reason in
                  {'explicit_time_missing', 'time_source_missing'} else completion.reason)
    else:
        status = 'waiting'
        reason = (completion.reason or 'external_fact') if preparation.satisfied else (preparation.reason or 'condition_unknown')
    if step['status'] == 'completed' and not current_complete:
        status = 'completed'
        reason = ('completion_recheck_dependency' if not dependencies_complete else
                  'completion_recheck_required' if completion.unknown or not completion.evidence else
                  'completion_recheck_facts_changed')
    continuable = (not step['rows'] and not step['read_ids'] or
        any(row['proposal_id'] is None and row['status'] in {'planned', 'not_executed', 'pending'}
            for row in step['rows']))
    blocking_rows = row_states & {'failed', 'cancelled', 'expired', 'executing', 'uncertain', 'needs_input'}
    # A normal pending card blocks that card, not the first preparation of the
    # remaining accepted batch rows. The write-time consumer below narrows this
    # Step-level result to the exact original manifest/input IDs without cards.
    resume_batch = (step['projected_status'] == 'awaiting_confirmation'
                    and step['proposal_id'] is None and bool(step['rows'])
                    and any(row['proposal_id'] is None and row['status'] == 'pending'
                            for row in step['rows']))
    strong_preparation = strong and not resume_batch
    ready = (dependencies_complete and preparation.satisfied and not preparation.unknown
             and not strong_preparation and not blocking_rows and continuable and not current_complete
             and step['status'] != 'completed')
    evidence = _evidence_json(completion.evidence or preparation.evidence)
    fingerprint = hashlib.sha256(json.dumps({
        'preparation': preparation.fingerprint, 'completion': completion.fingerprint,
        'intent_version': step['intent_version'], 'rows': step['rows'],
        'status': status, 'wait_reason': reason, 'preparation_ready': ready,
        'completion_satisfied': current_complete,
    }, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return StepConditionResult(step['id'], step['key'], status, reason, ready,
                               current_complete, evidence, fingerprint)


async def _evaluate_plan_facts(db, principal, *, clock, registry, client_factory, followup=False):
    """Shared read phase; its callers issue non-interchangeable proof types."""
    from . import business_assistant_service as service
    from .assistant_runtime_conditions import _Evaluator, _evaluate_with
    from .assistant_runtime_registry import domain_registry
    from .assistant_runtime_principal import _reader, _time, revalidate_principal
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    with _reader(db, principal._read_session_factory) as snapshot_db:
        _condition_scope(snapshot_db, principal)
        before = _condition_snapshot(snapshot_db, principal)
        if followup:
            before['followup'] = _followup_activity(snapshot_db, principal, clock=clock)
    # The reader never escapes this read phase. The next proof/Run/tick starts
    # afresh; shared original objects in this DAG use one consistent observation.
    evaluator = _Evaluator(db, principal, clock=clock,
        registry=domain_registry() if registry is None else registry, client_factory=client_factory)
    results, completed, due_times, checked_due = [], {}, [], set()
    for step in validate_dag(before['steps']):
        preparation = await _evaluate_with(evaluator, step['conditions'], purpose='preparation',
            plan_id=principal.plan_id, step_id=step['id'])
        completion = await _evaluate_with(evaluator, step['completion_conditions'], purpose='completion',
            read_work_item_ids=step['read_ids'] or None, plan_id=principal.plan_id, step_id=step['id'])
        result = _evaluated_step(step, preparation, completion,
            all(completed.get(key, False) for key in step['depends_on']))
        completed[step['key']] = result.completion_satisfied
        results.append(result)
        if followup:
            # A model-supplied time is not a timer source. Independently evaluate
            # each future due condition through the original explicit-message
            # validator, even when another condition in its AND set is unknown.
            for condition in step['conditions'] + step['completion_conditions']:
                if condition.get('type') != 'due_at':
                    continue
                encoded = json.dumps(condition, sort_keys=True, separators=(',', ':'))
                if encoded in checked_due:
                    continue
                checked_due.add(encoded)
                from .assistant_runtime_schemas import DueAt
                due = DueAt.model_validate(condition)
                if _time(due.at) <= _time(clock()):
                    continue
                verified = await _evaluate_with(evaluator, [condition], purpose='preparation',
                    plan_id=principal.plan_id, step_id=step['id'])
                if (not verified.unknown and verified.reason == 'due_at_pending'
                        and any(value.source_type == 'message' and value.source_id == due.source_message_id
                                for value in verified.evidence)):
                    due_times.append(_time(due.at))
    revalidate_principal(db, principal, clock=clock)
    with _reader(db, principal._read_session_factory) as snapshot_db:
        _condition_scope(snapshot_db, principal)
        after = _condition_snapshot(snapshot_db, principal)
        if followup:
            after['followup'] = _followup_activity(snapshot_db, principal, clock=clock)
    if (_snapshot_guard(before) != _snapshot_guard(after)
            or followup and before['followup'] != after['followup']):
        _conflict('求值期间计划或原执行记录已变化，请重新读取')
    fingerprint = hashlib.sha256(json.dumps({'plan_id': principal.plan_id,
        'goal_version': principal.goal_version,
        'steps': sorted((row.key, row.fingerprint) for row in results)},
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return before, tuple(results), fingerprint, tuple(due_times)


async def evaluate_plan_conditions(db, principal, *, clock=utcnow, registry=None, client_factory=None):
    """Read every Step for a real claimed Run; never accept a Grant probe here."""
    from .assistant_runtime_principal import revalidate_principal
    revalidate_principal(db, principal, clock=clock)
    if not principal.run_id or not principal.plan_id:
        _conflict('条件求值需要已认领且明确关联事项的执行')
    before, steps, fingerprint, _ = await _evaluate_plan_facts(db, principal,
        clock=clock, registry=registry, client_factory=client_factory)
    result = PlanConditionEvaluation(principal.plan_id, principal.goal_version, fingerprint, steps)
    _evaluations[result] = {'identity': _condition_identity(principal), 'snapshot': before,
                            'session_ref': ref(db), 'issued_at': monotonic()}
    return result


def _consume_condition_token(table, token, principal):
    state = table.pop(token, None) if type(token) in {PlanConditionEvaluation, AppliedConditionProof} else None
    if (state is None or state['identity'] != _condition_identity(principal)
            or monotonic() - state['issued_at'] > _CONDITION_PROOF_SECONDS):
        _conflict('本轮条件依据已失效，请重新查询，不能复用旧完成依据')
    return state


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class FollowupCheck:
    """A read-only Grant check, never authority for a Run/tool write."""
    plan_id: str
    goal_version: int
    grant_id: str
    fingerprint: str
    ready: bool
    required_complete: bool
    next_check_at: datetime


@dataclass(frozen=True, slots=True)
class FollowupPersistResult:
    plan_id: str
    goal_version: int
    grant_id: str
    plan_version: int
    session_version: int
    fingerprint: str
    ready: bool
    completed: bool
    next_check_at: datetime | None


_followup_checks = WeakKeyDictionary()
_FOLLOWUP_REASONS = frozenset({
    'model_round_budget', 'time_budget', 'tool_budget', 'preparation_budget',
    'context_budget_exceeded', 'source_message_missing', 'recheck_required',
    'runtime_unavailable', 'configuration_unavailable', 'needs_input',
})


def _followup_principal(db, principal, *, clock):
    from .assistant_runtime_principal import revalidate_principal
    revalidate_principal(db, principal, clock=clock)
    if (principal.auth_kind != 'grant' or principal.run_id is not None
            or principal.plan_id is None or principal.grant_id is None
            or type(principal._probe_grant_version) is not int
            or principal._probe_grant_version < 1
            or any(value is not None for value in
                   (principal.lease_owner, principal.fence, principal._login_ref))):
        _conflict('跟进核查必须使用当前授权的只读身份')
    return principal


def _followup_identity(principal):
    return (*_condition_identity(principal), principal._probe_grant_version)


def _followup_activity(db, principal, *, clock):
    """Only durable server outcomes and explicit same-goal employee resumes."""
    from .assistant_runtime_principal import _time
    thread = _authorized_thread(db, principal, principal.session_id)
    rows = list(db.scalars(select(Run).where(
        Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
        or_(Run.session_id == principal.session_id, Run.plan_id == principal.plan_id))
        .order_by(Run.id).execution_options(populate_existing=True)))
    facts, resumes, blockers = [], [], []
    busy = bool(thread.busy_token and thread.busy_until is not None
                and _time(thread.busy_until) > _time(clock()))
    for run in rows:
        if run.status in {'queued', 'running'}:
            busy = True
        same_goal = (run.plan_id == principal.plan_id and run.goal_version == principal.goal_version
                     and run.session_id == principal.session_id)
        if not same_goal and run.status not in {'queued', 'running'}:
            continue
        outcome = (run.usage or {}).get('followup_outcome_v1') if type(run.usage) is dict else None
        valid = (type(outcome) is dict and set(outcome) == {'schema_version', 'needs_input', 'reason'}
                 and type(outcome['schema_version']) is int and outcome['schema_version'] == 1
                 and type(outcome['needs_input']) is bool
                 and (outcome['reason'] is None or type(outcome['reason']) is str
                      and outcome['reason'] in _FOLLOWUP_REASONS))
        malformed = (type(run.usage) is not dict and run.usage is not None
                     or type(run.usage) is dict and 'followup_outcome_v1' in run.usage and not valid)
        needs_input = malformed or bool(valid and outcome['needs_input'])
        # Retain only the fixed outcome fields in the private source signature;
        # no usage ledger, output text or provider content is copied here.
        facts.append((run.id, run.session_id, run.plan_id, run.goal_version, run.status,
            run.stop_requested, run.trigger_kind, run.auth_kind, run.created_at, run.finished_at,
            needs_input, outcome['reason'] if valid else None, malformed))
        if not same_goal:
            continue
        if run.auth_kind == 'login' and run.trigger_kind in {'user', 'manual'}:
            resumes.append(_time(run.created_at))
        if run.status in {'succeeded', 'failed', 'cancelled'} and (run.status == 'failed' or needs_input):
            blockers.append(_time(run.finished_at or run.created_at))
    blocked = any(not any(resume > ended for resume in resumes) for ended in blockers)
    return {'runs': tuple(facts), 'busy_token': thread.busy_token,
            'busy_until': thread.busy_until, 'busy': busy, 'blocked': blocked}


def _followup_complete(snapshot, results):
    required = {step['id'] for step in snapshot['steps'] if step['required']}
    if not required or not all(result.completion_satisfied and result.evidence_json
                               for result in results if result.step_id in required):
        return False
    if any(result.status in {'needs_input', 'awaiting_confirmation', 'uncertain'} for result in results):
        return False
    unfinished = {'pending', 'planned', 'not_executed', 'running', 'executing', 'uncertain', 'needs_input'}
    return not any(row['status'] in unfinished for step in snapshot['steps'] for row in step['rows'])


async def resolve_followup_check(db, principal, *, clock=utcnow, registry=None, client_factory=None):
    """Evaluate an explicitly granted goal without manufacturing a Run or login."""
    principal = _followup_principal(db, principal, clock=clock)
    started = monotonic()
    before, steps, fingerprint, due_times = await _evaluate_plan_facts(db, principal,
        clock=clock, registry=registry, client_factory=client_factory, followup=True)
    from .assistant_runtime_principal import _time
    now = _time(clock())
    activity = before['followup']
    complete = not activity['busy'] and _followup_complete(before, steps)
    ready = (not activity['busy'] and not activity['blocked'] and not complete
             and any(step.preparation_ready and step.status not in
                     {'needs_input', 'failed', 'cancelled', 'uncertain'} for step in steps))
    # If a verified future deadline arrived during the remaining reads, check
    # again at the next dispatcher turn instead of postponing it five minutes.
    next_check = min([now + timedelta(minutes=5), *(max(now, due) for due in due_times)])
    check = FollowupCheck(principal.plan_id, principal.goal_version, principal.grant_id,
                          fingerprint, ready, complete, next_check)
    _followup_checks[check] = {'principal': principal, 'identity': _followup_identity(principal),
        'session_ref': ref(db), 'bind': db.get_bind(), 'issued_at': started,
        'snapshot': before, 'steps': steps, 'consumed': False, 'transaction_ref': None}
    validate_followup_check(db, check, clock=clock)
    return check


def _followup_state(db, check):
    state = _followup_checks.get(check) if type(check) is FollowupCheck else None
    if (state is None or state['session_ref']() is not db or state['bind'] is not db.get_bind()
            or not 0 <= monotonic() - state['issued_at'] <= _CONDITION_PROOF_SECONDS
            or state['identity'] != _followup_identity(state['principal'])):
        _conflict('本轮跟进核查已过期或不属于当前事务来源')
    if state['consumed'] and (db.get_transaction() is None or state['transaction_ref'] is None
            or state['transaction_ref']() is not db.get_transaction()):
        _conflict('本轮跟进核查已经消费，不能跨事务重复使用')
    return state


def validate_followup_check(db, check, *, clock=utcnow):
    """Fresh committed Grant authority, also valid just before its pending revoke."""
    state = _followup_state(db, check)
    return _followup_principal(db, state['principal'], clock=clock)


def persist_followup_checks(db, checks, *, clock=utcnow):
    """Consume the entire checked batch, flush only; queue owns the final commit.

    Lock all Sessions, all Plans, then their Grants. Validate every source before
    touching any row so several Plans in one Session cannot conflict with this
    batch's own version changes. No original GET, model call or callback occurs.
    The caller must roll back on failure and revalidate all checks after its
    own queue writes and immediately before committing.
    """
    from . import business_assistant_service as service
    from .business_assistant_models import AssistantSession
    from .assistant_runtime_principal import _time
    service.require_preparation_read_phase(db)
    if (type(checks) is not tuple or len({check.plan_id for check in checks
                                        if type(check) is FollowupCheck}) != len(checks)):
        _conflict('跟进核查必须是互不重复的服务器事项凭据')
    states = [(_followup_state(db, check), validate_followup_check(db, check, clock=clock)) for check in checks]
    if any(state['consumed'] for state, _ in states):
        _conflict('本轮跟进核查已经保存')
    if len({principal.store_id for _, principal in states}) > 1:
        _conflict('一次跟进保存只能属于同一家门店')
    if not checks:
        return ()
    _condition_scope(db, states[0][1])
    if db.info.get('aggregate_scope'):
        _conflict('跨门店汇总不能保存跟进结果')
    threads, plans, grants, step_rows = {}, {}, {}, {}
    with db.no_autoflush:
        for state, principal in sorted(states, key=lambda pair: pair[1].session_id):
            if principal.session_id in threads:
                continue
            thread = db.scalar(select(AssistantSession).where(AssistantSession.id == principal.session_id,
                AssistantSession.owner_id == principal.actor_id, AssistantSession.store_id == principal.store_id)
                .with_for_update().execution_options(populate_existing=True))
            if thread is None:
                _conflict()
            threads[thread.id] = thread
        for state, principal in sorted(states, key=lambda pair: pair[1].plan_id):
            plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == principal.plan_id,
                AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id,
                AssistantWorkPlan.session_id == principal.session_id).with_for_update()
                .execution_options(populate_existing=True))
            if plan is None:
                _conflict()
            plans[plan.id] = plan
        for state, principal in sorted(states, key=lambda pair: pair[1].grant_id):
            grant = db.scalar(select(FollowupGrant).where(FollowupGrant.id == principal.grant_id)
                .with_for_update().execution_options(populate_existing=True))
            if (grant is None or grant.version != principal._probe_grant_version
                    or (grant.owner_id, grant.store_id, grant.session_id, grant.plan_id, grant.goal_version,
                        grant.owner_role, grant.access_version, grant.status, grant.revoked_at)
                    != (principal.actor_id, principal.store_id, principal.session_id, principal.plan_id,
                        principal.goal_version, principal.role, principal.access_version, 'active', None)
                    or grant.expires_at is not None and _time(grant.expires_at) <= _time(clock())):
                _conflict('跟进授权已经变化')
            grants[grant.id] = grant
        for state, principal in states:
            fresh = _condition_snapshot(db, principal)
            activity = _followup_activity(db, principal, clock=clock)
            if (_snapshot_guard(fresh) != _snapshot_guard(state['snapshot'])
                    or activity != state['snapshot']['followup']):
                _conflict('跟进求值来源已变化，请重新核查')
            step_rows[principal.plan_id] = {row.id: row for row in _steps(db, plans[principal.plan_id], refresh=True)}
        # Lock acquisition may have waited. Recheck TTL and committed authority
        # once more before consuming anything or assigning an ORM attribute.
        for check in checks:
            validate_followup_check(db, check, clock=clock)
        transaction = db.get_transaction()
        for state, _ in states:
            state['consumed'], state['transaction_ref'] = True, ref(transaction)
        changed_sessions, changed_grants, attention_changes = set(), [], []
        now = _time(clock())
        for check, (state, principal) in zip(checks, states):
            plan, changed = plans[check.plan_id], False
            semantic_changed = False
            for result in state['steps']:
                step = step_rows[check.plan_id][result.step_id]
                evidence = [json.loads(value) for value in result.evidence_json]
                semantic_changed |= step.status != result.status or step.wait_reason != result.wait_reason
                if (step.status != result.status or step.wait_reason != result.wait_reason
                        or bool(evidence) and not _same_evidence(step.last_evidence, evidence)):
                    step.status, step.wait_reason, step.updated_at = result.status, result.wait_reason, now
                    if evidence:
                        step.last_evidence = evidence
                    step.version += 1
                    changed = True
            next_check = None if check.required_complete else check.next_check_at
            if plan.next_check_at != next_check:
                plan.next_check_at = next_check
                changed = True
            if check.required_complete:
                # No queued/running work or live Session busy lease was present
                # in the guarded source. Completion does not cancel business.
                plan.status = 'completed'
                grant = grants[check.grant_id]
                grant.status, grant.revoked_at, grant.stop_reason = 'revoked', now, 'completed'
                changed_grants.append(grant)
                changed = True
                semantic_changed = True
            if changed:
                plan.version += 1
                plan.updated_at = now
                changed_sessions.add(principal.session_id)
            if semantic_changed:
                attention_changes.append(plan)
        for sid in changed_sessions:
            threads[sid].version += 1
            threads[sid].updated_at = now
        db.flush()
        db.info['assistant_preparation_transaction'] = db.get_transaction()
        if changed_grants:
            _emit_grants(db, changed_grants)
        for plan in attention_changes:
            _emit_plan_signal(db, plan)
    for check in checks:
        validate_followup_check(db, check, clock=clock)
    return tuple(FollowupPersistResult(check.plan_id, check.goal_version, check.grant_id,
        plans[check.plan_id].version, threads[state['principal'].session_id].version, check.fingerprint,
        check.ready, check.required_complete, plans[check.plan_id].next_check_at)
        for check, (state, _) in zip(checks, states))


def consume_preparation_evaluation(db, principal, evaluation, *, step_ids, manifest_ids=None, clock=None):
    """Consume one fresh evaluation after the caller's actual fenced Run CAS.

    Return None only for a Step with no accepted manifest, otherwise return the
    exact original input IDs which have never acquired a card. This permits no
    new intent, replacement card, employee confirmation or business submission.
    All native reads precede this function; the caller owns commit/rollback.
    """
    from .assistant_runtime_events import _capability
    from .assistant_runtime_principal import revalidate_principal
    from .assistant_runtime_runner import _card, _card_status, _manifest_data, _work_key
    if (type(step_ids) is not tuple or not step_ids
            or any(type(value) is not str for value in step_ids)
            or len(set(step_ids)) != len(step_ids)
            or manifest_ids is not None and (type(manifest_ids) is not dict
                or set(manifest_ids) - set(step_ids)
                or any(type(value) is not str for value in manifest_ids.values()))):
        _conflict('准备依据必须对应明确且不重复的真实步骤')
    if db.new or db.dirty or db.deleted:
        _conflict('准备依据必须在本次助手记录写入前核对')
    _capability(db, principal, clock=clock)
    state = _consume_condition_token(_evaluations, evaluation, principal)
    if state.get('session_ref') is None or state['session_ref']() is not db:
        _conflict('准备依据必须由当前执行连接实际读取')
    before = state['snapshot']
    with db.no_autoflush:
        current = _condition_snapshot(db, principal)
        if _snapshot_guard(current) != _snapshot_guard(before):
            _conflict()
        thread = _authorized_thread(db, principal, principal.session_id)
        plan = _owned_plan(db, thread, principal.plan_id)
        steps = {step.id: step for step in _steps(db, plan)}
        results = {result.step_id: result for result in evaluation.steps}
        current_manifests, manifests = _manifest_index(db, principal, thread, plan)
        allowed = {}
        for step_id in step_ids:
            step, result = steps.get(step_id), results.get(step_id)
            if step is None or result is None or not result.preparation_ready:
                _conflict('此步骤的真实前置条件尚未满足，不能准备或重办')
            if step.status in {'completed', 'failed', 'cancelled', 'uncertain'} or step.proposal_id is not None:
                _conflict('已有办理结果或兼容原卡的步骤不能自动重新准备')
            manifest = current_manifests.get((step.id, step.intent_version))
            expected_manifest = (manifest_ids or {}).get(step.id)
            if manifest is None:
                if expected_manifest is not None:
                    _conflict()
                allowed[step.id] = None
                continue
            manifest_id = next((key for key, value in manifests.items() if value is manifest), None)
            if manifest_id is None or expected_manifest is not None and expected_manifest != manifest_id:
                _conflict()
            # Recheck the complete actual record, not caller-provided rows or a
            # convenient subset. Older goal anchors remain valid only through
            # this unchanged current Step/intent, as in the original M2 reuse.
            item = db.get(RunItem, manifest_id)
            if (item is None or item.status not in {'pending', 'running'}
                    or _manifest_data(item) != manifest):
                _conflict()
            works = _work_for_step(db, thread, plan, step)
            rows, cards = _row_outcomes(db, principal, thread, plan, step, manifest, manifests, works)
            if (any(row['status'] not in {'pending', 'succeeded'} for row in rows)
                    or any(_card_status(card) not in {'pending', 'succeeded'}
                           or _card_status(card) == 'pending' and card.questions for card in cards.values())):
                _conflict('完整清单仍有缺项、失败或待核对结果，不能自动继续准备')
            candidates = []
            for row in manifest['rows']:
                if row.get('proposal_id') is not None:
                    continue
                if (row['outcome'] != 'pending' or row.get('proposal_status') is not None
                        or row.get('carry_forward') is not None):
                    _conflict('只有原清单中从未成卡的待准备行可继续')
                key = _work_key(manifest['scope'], row['input_item_id'])
                work = db.scalar(select(WorkItem).where(WorkItem.owner_id == principal.actor_id,
                    WorkItem.store_id == principal.store_id, WorkItem.intent_key == key))
                if work is None:
                    if row.get('work_item_id') is not None:
                        _conflict()
                else:
                    _same_scope(work, thread)
                    if (work.id != row.get('work_item_id') or work.plan_id != plan.id
                            or work.step_id != step.id or work.intent_version != step.intent_version
                            or work.item_kind != 'prepare' or work.status != 'planned'
                            or work.input_item_id != row['input_item_id']
                            or work.supersedes_id != row.get('supersedes_id')
                            or _card(db, work, thread, principal) is not None):
                        _conflict('此原行已有卡片或意图已变化，不能自动重新准备')
                candidates.append(row['input_item_id'])
            if not candidates:
                _conflict('完整清单没有尚未成卡的原待准备行')
            allowed[step.id] = tuple(candidates)
    # Time spent waiting on database locks cannot extend the proof lifetime.
    if monotonic() - state['issued_at'] > _CONDITION_PROOF_SECONDS:
        _conflict('准备核对依据已过期，请重新读取')
    revalidate_principal(db, principal, clock=clock)
    return allowed


def _same_evidence(left, right):
    def facts(values):
        return sorted(json.dumps({key: value for key, value in row.items() if key != 'observed_at'},
            sort_keys=True, separators=(',', ':')) for row in values or [])
    return facts(left) == facts(right)


def _append_plan_update_event(hook, db, principal, plan):
    """Only a synchronous in-transaction appender may extend this write."""
    from inspect import isawaitable, iscoroutine
    result = hook(db, principal, plan.id, plan.version)
    if isawaitable(result):
        if iscoroutine(result):
            result.close()
        raise TypeError('Plan event hook must append synchronously without I/O')


def apply_condition_results(db, principal, evaluation, *, clock=utcnow, on_plan_updated=None):
    """Persist only Step progress with scope, source versions and fenced Run CAS.

    The returned proof is process-local, one-use and short-lived. A caller may
    pass it immediately to close_followup_control; it never confirms business.
    The optional server-owned hook synchronously appends a minimal Run event in
    this transaction. It must not commit, perform network I/O or expose content.
    """
    from . import business_assistant_service as service
    from .assistant_runtime_principal import _reader, _time, revalidate_principal
    if on_plan_updated is not None and not callable(on_plan_updated):
        raise TypeError('Plan event hook must be a server-owned callable')
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    state = _consume_condition_token(_evaluations, evaluation, principal)
    before = state['snapshot']
    _condition_scope(db, principal)
    with _reader(db, principal._read_session_factory) as snapshot_db:
        _condition_scope(snapshot_db, principal)
        fresh = _condition_snapshot(snapshot_db, principal)
    if _snapshot_guard(before) != _snapshot_guard(fresh):
        _conflict()
    try:
        with db.no_autoflush:
            thread, plan = _locked_control_rows(db, principal.actor_id, principal.store_id,
                principal.session_id, principal.plan_id)
            steps = _steps(db, plan, refresh=True)
            if (plan.status != 'active' or plan.goal_version != principal.goal_version
                    or (plan.version, thread.version, tuple((row.id, row.version) for row in steps))
                    != (before['plan_version'], before['session_version'], before['step_versions'])
                    or _condition_sources(db, thread, plan, steps) != before['sources']):
                _conflict()
            run = db.scalar(select(Run).where(Run.id == principal.run_id).with_for_update()
                .execution_options(populate_existing=True))
            if (run is None or run.status != 'running' or run.stop_requested or run.lease_until is None
                    or _time(run.lease_until) <= _time(clock())
                    or (run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version,
                        run.auth_kind, run.grant_id, run.login_session_ref, run.lease_owner, run.fence)
                    != (principal.actor_id, principal.store_id, principal.session_id, principal.plan_id,
                        principal.goal_version, principal.auth_kind, principal.grant_id, principal._login_ref,
                        principal.lease_owner, principal.fence)):
                _conflict('执行租约或当前目标已变化，不能保存条件结果')
            by_id, changed, semantic_changed = {row.id: row for row in steps}, False, False
            now = _time(clock())
            for result in evaluation.steps:
                step = by_id[result.step_id]
                evidence = [json.loads(value) for value in result.evidence_json]
                evidence_changed = bool(evidence) and not _same_evidence(step.last_evidence, evidence)
                semantic_changed |= step.status != result.status or step.wait_reason != result.wait_reason
                if step.status != result.status or step.wait_reason != result.wait_reason or evidence_changed:
                    step.status, step.wait_reason, step.updated_at = result.status, result.wait_reason, now
                    if evidence:
                        step.last_evidence = evidence
                    step.version += 1
                    changed = True
            if changed:
                thread.version += 1
                plan.version += 1
                thread.updated_at = plan.updated_at = now
            # This is an ephemeral write-time CAS, not a long-lived version in
            # RuntimePrincipal; it prevents a stale lease writing under SQLite.
            run.version += 1
            db.flush()
            if changed and on_plan_updated is not None:
                _append_plan_update_event(on_plan_updated, db, principal, plan)
            if semantic_changed:
                _emit_plan_signal(db, plan)
            versions = tuple((row.id, row.version) for row in steps)
            plan_version, session_version = plan.version, thread.version
        revalidate_principal(db, principal, clock=clock)
        service.commit(db)
    except Exception as exc:
        _followup_failure(db, exc)
    # A post-commit authorization failure must not return old private progress.
    revalidate_principal(db, principal, clock=clock)
    required = {step['id'] for step in before['steps'] if step['required']}
    complete = bool(required) and all(row.completion_satisfied for row in evaluation.steps if row.step_id in required)
    proof = AppliedConditionProof(principal.plan_id, plan_version, evaluation.fingerprint, complete)
    _completion_proofs[proof] = {'identity': _condition_identity(principal), 'issued_at': state['issued_at'],
        'session_version': session_version, 'step_versions': versions, 'sources': before['sources'],
        'steps': evaluation.steps}
    return proof


def _stored_completion(db, principal, plan, *, proof, proof_state):
    """Only this Run's fresh, applied evaluation can prove completion."""
    from .assistant_runtime_schemas import EvidenceRef
    if plan.status != 'active' or plan.goal_version != principal.goal_version:
        _conflict('只有当前有效范围的进行中事项可依据事实完成')
    steps = _steps(db, plan)
    required = [step for step in steps if step.required]
    thread = _authorized_thread(db, principal, principal.session_id)
    if (not proof.required_complete or proof.plan_id != plan.id or proof.plan_version != plan.version
            or proof_state['session_version'] != thread.version
            or proof_state['step_versions'] != tuple((step.id, step.version) for step in steps)
            or proof_state['sources'] != _condition_sources(db, thread, plan, steps)
            or monotonic() - proof_state['issued_at'] > _CONDITION_PROOF_SECONDS):
        _conflict('本轮完成依据已变化，请重新核对')
    evaluated = {value.step_id: value for value in proof_state['steps']}
    if not required or any(step.status != 'completed' or not step.last_evidence
            or not evaluated[step.id].completion_satisfied
            or not step.completion_conditions and not _stored_read_completion(
                db, thread, plan, step, _work_for_step(db, thread, plan, step)) for step in required):
        _conflict('必要步骤尚无完整的真实完成依据')
    for step in required:
        try:
            for evidence in step.last_evidence:
                EvidenceRef.model_validate(evidence)
        except (ValueError, TypeError):
            _conflict('完成依据格式不完整，不能结束事项')
    projection = project_legacy_plan(db, principal, principal.session_id, plan)
    by_key = {step['key']: step for step in projection['steps']}
    if (any(by_key[step.key]['runtime_status'] != 'completed' for step in required)
            or any(step['runtime_status'] in {'needs_input', 'awaiting_confirmation', 'uncertain'}
                   or any(row['status'] in {'pending', 'executing', 'uncertain'} for row in step['rows'])
                   for step in projection['steps'])):
        _conflict('仍有未确认、缺资料或结果待核对的行，不能结束事项')


def close_followup_control(db, principal, *, reason, expected_version, clock=utcnow,
                           completion_proof=None, on_plan_updated=None):
    """A leased worker may close only its original scope; return no private view.

    This owns a short lifecycle transaction. Existing evidence must already be
    persisted. Queue code remains responsible for fenced Run terminal writes.
    The optional synchronous server hook appends only control references in the
    same transaction, including on permission loss; it cannot commit or do I/O.
    """
    from . import business_assistant_service as service
    from .assistant_runtime_principal import (
        _reader, _time, revalidate_control_principal, identity_is_current,
        validate_completion_authority,
    )
    from .tenancy import set_scope
    if on_plan_updated is not None and not callable(on_plan_updated):
        raise TypeError('Plan event hook must be a server-owned callable')
    service.require_preparation_read_phase(db)
    if reason not in {'permission_changed', 'completed'} or type(expected_version) is not int or expected_version < 1:
        raise HTTPException(422, '控制收尾参数不正确')
    revalidate_control_principal(db, principal, clock=clock)
    if principal.plan_id is None:
        _conflict('当前执行没有可结束的授权事项')
    if reason == 'permission_changed':
        if identity_is_current(db, principal):
            _conflict('当前员工门店权限仍有效，不能通过失效路径结束事项')
    else:
        validate_completion_authority(db, principal, clock=clock)
    proof_state = (_consume_condition_token(_completion_proofs, completion_proof, principal)
                   if reason == 'completed' else None)
    with _reader(db, principal._read_session_factory) as snapshot_db:
        set_scope(snapshot_db, [principal.store_id], principal.store_id)
        from .business_assistant_models import AssistantSession
        thread = snapshot_db.scalar(select(AssistantSession).where(AssistantSession.id == principal.session_id,
            AssistantSession.owner_id == principal.actor_id, AssistantSession.store_id == principal.store_id))
        plan = snapshot_db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == principal.plan_id,
            AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id,
            AssistantWorkPlan.session_id == principal.session_id))
        if thread is None or plan is None or plan.version != expected_version:
            _conflict()
        session_version = thread.version
        step_versions = {step.id: step.version for step in _steps(snapshot_db, plan)}
        active = list(snapshot_db.scalars(select(FollowupGrant).where(
            FollowupGrant.plan_id == plan.id, FollowupGrant.status == 'active')))
        current_scope = plan.goal_version == principal.goal_version and (
            reason == 'completed' and principal.auth_kind == 'login'
            or all(g.id == principal.grant_id for g in active))
        if reason == 'completed' and current_scope:
            _stored_completion(snapshot_db, principal, plan, proof=completion_proof, proof_state=proof_state)
    try:
        with db.no_autoflush:
            thread, plan = _locked_control_rows(db, principal.actor_id, principal.store_id,
                principal.session_id, principal.plan_id)
            if (thread.version != session_version or plan.version != expected_version
                    or {step.id: step.version for step in _steps(db, plan, refresh=True)} != step_versions):
                _conflict()
            if reason == 'completed':
                _stored_completion(db, principal, plan, proof=completion_proof, proof_state=proof_state)
            run = db.scalar(select(Run).where(Run.id == principal.run_id).with_for_update()
                .execution_options(populate_existing=True))
            if (run is None or run.status != 'running' or run.lease_until is None
                    or _time(run.lease_until) <= _time(clock())
                    or (run.owner_id, run.store_id, run.session_id, run.plan_id, run.goal_version,
                        run.auth_kind, run.grant_id, run.login_session_ref, run.lease_owner, run.fence)
                    != (principal.actor_id, principal.store_id, principal.session_id, principal.plan_id,
                        principal.goal_version, principal.auth_kind, principal.grant_id, principal._login_ref,
                        principal.lease_owner, principal.fence)):
                _conflict('执行租约已失效，不能写入控制状态')
            grants = _plan_grants(db, thread, plan, refresh=True)
            current_scope = plan.goal_version == principal.goal_version and (
                reason == 'completed' and principal.auth_kind == 'login'
                or all(g.id == principal.grant_id for g in grants if g.status == 'active'))
            if reason == 'completed' and current_scope and plan.status != 'active':
                _conflict('暂停或结束事项不能由旧执行推进为完成')
            changed = []
            now = _time(clock())
            for grant in grants:
                if (grant.status in {'active', 'paused'} and grant.goal_version == principal.goal_version
                        and (current_scope or grant.id == principal.grant_id)):
                    grant.status, grant.revoked_at, grant.stop_reason = 'revoked', now, reason
                    changed.append(grant)
            plan_changed = current_scope and plan.status not in {'completed', 'cancelled'}
            if plan_changed:
                plan.status = 'completed' if reason == 'completed' else 'paused'
                plan.next_check_at, plan.updated_at = None, now
                plan.version += 1
                _stop_old_runs(db, thread, plan, pause_grants=False,
                    error_code='permission_denied' if reason == 'permission_changed' else 'precondition_conflict')
            run.stop_requested = True
            run.error_code = 'permission_denied' if reason == 'permission_changed' else 'precondition_conflict'
            # Force a current-transaction optimistic CAS even when the stop
            # fields already match; SQLite does not provide FOR UPDATE locks.
            run.version += 1
            thread.version += 1
            thread.updated_at = now
        revalidate_control_principal(db, principal, clock=clock)
        if reason == 'permission_changed':
            if identity_is_current(db, principal):
                _conflict('权限已恢复，不能继续失效清理')
        else:
            validate_completion_authority(db, principal, clock=clock)
            if monotonic() - proof_state['issued_at'] > _CONDITION_PROOF_SECONDS:
                _conflict('本轮完成依据已过期，请重新核对')
        _emit_grants(db, changed)
        if plan_changed and on_plan_updated is not None:
            _append_plan_update_event(on_plan_updated, db, principal, plan)
        if not changed and current_scope:
            from .assistant_runtime_outbox import emit_wake_event
            emit_wake_event(db, f'plan:{plan.id}:{plan.version}:{plan.status}', 'grant', {
                'store_id': plan.store_id, 'plan_id': plan.id,
                'source_ref': {'type': 'plan', 'id': plan.id, 'version': plan.version}})
        revalidate_control_principal(db, principal, clock=clock)
        if reason == 'completed':
            validate_completion_authority(db, principal, clock=clock)
        service.commit(db)
    except Exception as exc:
        _followup_failure(db, exc)
    return {'changed': True, 'run_id': principal.run_id}
