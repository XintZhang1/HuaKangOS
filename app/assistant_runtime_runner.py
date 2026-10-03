"""Stable inputs, fenced tool checkpoints, recovery and one bounded Run.

The caller must revalidate its principal, authorization, goal version and fence
in the same transaction before each mutation. These APIs are internal Python
contracts and are not model tools. The original input/preparation primitives
only flush; the Runtime orchestration below owns its short transactions.
``prepare_inputs`` is an internal complete-row manifest, never an executable
model tool. M4 recovery must not dispatch it; actual tool/batch-row attempts
reference the manifest ID and its stable input-item IDs.

Accept and commit the complete input manifest first. Resolve every row's native
reads before starting the preparation transaction, then pass those detached
results here. On any exception the caller must roll back and reload; never keep
locally generated IDs after losing a version/unique-constraint race.
"""
import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import func, select

from . import business_assistant_service as service
from .assistant_runtime_models import PlanStep, Run, RunItem, WorkItem
from .assistant_runtime_schemas import JsonObject, UUIDText
from .business_assistant_models import AssistantMessage, AssistantProposal, AssistantWorkPlan
from .db import utcnow


_JSON_OBJECT = TypeAdapter(JsonObject)
_UUID = TypeAdapter(UUIDText)
_MANIFEST_TOOL = 'prepare_inputs'
_ROW_OUTCOMES = {'pending', 'needs_input', 'failed', 'prepared', 'settled', 'uncertain'}


@dataclass(frozen=True)
class ReprepareAuthorization:
    """Created only by an employee-action handler after explicit authorization."""
    actor_id: int
    store_id: int
    session_id: str
    role: str
    access_version: int
    next_intent_version: int
    previous_manifest_id: str | None = None
    compatibility_proposal_id: str | None = None
    selected_input_item_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RowResolution:
    """One completed resolution, or a safe reason it could not be prepared."""
    input_item_id: str
    preparation: service.ResolvedPreparation | None = None
    outcome: str = 'pending'
    reason_code: str | None = None
    message: str = ''


def _conflict():
    raise HTTPException(409, '准备意图、行清单或关联记录已变化，请重新核对后继续') from None


def _require_authorized(value):
    if value is not True:
        raise HTTPException(403, '本次准备尚未完成员工授权核验')


def _json(value):
    try:
        return _JSON_OBJECT.validate_python(value, strict=True)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise HTTPException(422, '输入必须是完整、有限且字段明确的业务资料') from None


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _text(value, maximum):
    if type(value) is not str or not value or len(value) > maximum or service.scrub(value) != value:
        raise HTTPException(422, '输入标识或说明无效，请重新核对')
    return value


def _flush(db):
    # Preserve the read-phase guard after flush empties new/dirty collections.
    db.info['assistant_preparation_transaction'] = db.get_transaction()
    db.flush()


def _scope(thread, user):
    return user.id, thread.store_id, thread.id


def _same_scope(row, thread, user):
    if (row.owner_id, row.store_id, row.session_id) != _scope(thread, user):
        _conflict()


def _plan_step(db, thread, user, plan_id, step_id):
    if (plan_id is None) != (step_id is None):
        _conflict()
    if plan_id is None:
        return None, None
    plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == plan_id))
    if plan is None:
        _conflict()
    _same_scope(plan, thread, user)
    if plan.engine_version != 2 or plan.status != 'active':
        _conflict()
    step = db.scalar(select(PlanStep).where(PlanStep.id == step_id, PlanStep.plan_id == plan.id))
    if step is None or step.status in {'completed', 'uncertain'}:
        _conflict()
    return plan, step


def _run(db, thread, user, run_id, plan_id):
    run = db.scalar(select(Run).where(Run.id == run_id))
    if run is None:
        _conflict()
    _same_scope(run, thread, user)
    if run.plan_id is not None and run.plan_id != plan_id:
        _conflict()
    return run


def _manifest_key(scope):
    anchor = ({'plan_id': scope['plan_id'], 'step_key': scope['step_key']}
              if scope['plan_id'] is not None else
              {'session_id': scope['session_id'], 'request_id': scope['origin_request_id'],
               'tool_key': scope['tool_key']})
    return 'inputs:' + _digest({**anchor, 'intent_version': scope['intent_version']})


def _work_key(scope, input_item_id):
    anchor = ({'plan_id': scope['plan_id'], 'step_key': scope['step_key']}
              if scope['plan_id'] is not None else
              {'request_id': scope['origin_request_id']})
    return 'prepare:' + _digest({**anchor, 'input_item_id': input_item_id,
                                 'intent_version': scope['intent_version']})


def _manifest_data(item):
    if item.kind != 'tool' or item.tool_name != _MANIFEST_TOOL or item.attempt_no != 1:
        _conflict()
    data = _json(deepcopy(item.validated_arguments))
    if (data.get('schema_version') != 1 or type(data.get('scope')) is not dict
            or type(data.get('rows')) is not list or not data['rows']):
        _conflict()
    required_scope = {'session_id', 'plan_id', 'step_id', 'step_key', 'goal_version',
                      'origin_request_id', 'tool_key', 'intent_version', 'owner_id',
                      'store_id', 'role', 'access_version'}
    if set(data['scope']) != required_scope or item.item_key != _manifest_key(data['scope']):
        _conflict()
    ids = set()
    for position, row in enumerate(data['rows']):
        if (type(row) is not dict or row.get('position') != position
                or type(row.get('input')) is not dict or row.get('outcome') not in _ROW_OUTCOMES):
            _conflict()
        try:
            ident = _UUID.validate_python(row.get('input_item_id'), strict=True)
        except (ValueError, TypeError):
            _conflict()
        if ident in ids or row.get('input_digest') != _digest(row['input']):
            _conflict()
        ids.add(ident)
    if data.get('input_digest') != _digest([row['input'] for row in data['rows']]):
        _conflict()
    return data


def _owned_manifest(db, user, session_id, manifest_id):
    thread = service.owned_session(db, user, session_id)
    item = db.scalar(select(RunItem).join(Run, Run.id == RunItem.run_id).where(
        RunItem.id == manifest_id, Run.owner_id == user.id,
        Run.store_id == thread.store_id, Run.session_id == thread.id))
    if item is None:
        _conflict()
    data = _manifest_data(item)
    scope = data['scope']
    if ((scope['owner_id'], scope['store_id'], scope['session_id'], scope['role'], scope['access_version'])
            != (user.id, thread.store_id, thread.id, user.role, user.access_version)):
        _conflict()
    return thread, item, data


def _card(db, work, thread, user):
    cards = list(db.scalars(select(AssistantProposal).where(
        AssistantProposal.source_work_item_id == work.id)))
    if len(cards) > 1:
        _conflict()
    if not cards:
        return None
    card = cards[0]
    _same_scope(card, thread, user)
    if (card.owner_role != user.role or card.access_version != user.access_version
            or card.operation_id != work.operation_id):
        _conflict()
    return card


def _card_status(card):
    """Match the original card's effective status without rewriting its row."""
    if card.status == 'pending' and card.expires_at <= utcnow():
        return 'expired'
    if card.status == 'executing' and card.started_at and card.started_at < utcnow() - timedelta(minutes=3):
        return 'uncertain'
    return card.status


def _reprepare_rows(db, user, thread, authorization, scope, inputs, step):
    if not isinstance(authorization, ReprepareAuthorization):
        _conflict()
    if ((authorization.actor_id, authorization.store_id, authorization.session_id,
         authorization.role, authorization.access_version, authorization.next_intent_version)
            != (user.id, thread.store_id, thread.id, user.role, user.access_version,
                scope['intent_version'])):
        _conflict()
    if (authorization.previous_manifest_id is None) == (authorization.compatibility_proposal_id is None):
        _conflict()
    if authorization.compatibility_proposal_id is not None:
        if (step is None or step.proposal_id != authorization.compatibility_proposal_id
                or step.intent_version + 1 != scope['intent_version']
                or authorization.selected_input_item_ids):
            _conflict()
        card = db.scalar(select(AssistantProposal).where(AssistantProposal.id == step.proposal_id))
        if card is None:
            _conflict()
        _same_scope(card, thread, user)
        if (card.owner_role != user.role or card.access_version != user.access_version
                or _card_status(card) not in {'failed', 'cancelled', 'expired'}):
            _conflict()
        return None, None, set(), set()
    _, previous, data = _owned_manifest(db, user, thread.id, authorization.previous_manifest_id)
    old_scope = data['scope']
    if (old_scope['plan_id'] != scope['plan_id'] or old_scope['step_id'] != scope['step_id']
            or old_scope['intent_version'] + 1 != scope['intent_version'] or len(data['rows']) != len(inputs)):
        _conflict()
    selected = authorization.selected_input_item_ids
    if type(selected) not in (tuple, list) or not selected or any(type(value) is not str for value in selected):
        _conflict()
    selected = set(selected)
    if len(selected) != len(authorization.selected_input_item_ids) or not selected <= {row['input_item_id'] for row in data['rows']}:
        _conflict()
    carried = set()
    for position, row in enumerate(data['rows']):
        chosen = row['input_item_id'] in selected
        if not chosen and row['input_digest'] != _digest(inputs[position]):
            _conflict()
        work_id = row.get('work_item_id')
        if work_id is None:
            if row['outcome'] == 'uncertain' or row.get('proposal_id') is not None:
                _conflict()
            continue
        work = db.scalar(select(WorkItem).where(WorkItem.id == work_id))
        if work is None:
            _conflict()
        _same_scope(work, thread, user)
        if (work.item_kind != 'prepare' or work.input_item_id != row['input_item_id']
                or work.plan_id != old_scope['plan_id'] or work.step_id != old_scope['step_id']
                or work.intent_version > old_scope['intent_version']):
            _conflict()
        card = _card(db, work, thread, user)
        state = _card_status(card) if card is not None else None
        if work.status == 'uncertain' or state in {'executing', 'uncertain'}:
            _conflict()
        if chosen and state is not None and state not in {'failed', 'cancelled', 'expired'}:
            _conflict()
        if card is None and work.status != 'planned':
            _conflict()
        if card is not None:
            if row.get('proposal_id') != card.id:
                _conflict()
            row.update(proposal_id=card.id, proposal_status=state,
                       outcome=_result_for_card(work, card))
            if not chosen:
                carried.add(row['input_item_id'])
        elif row.get('proposal_id') is not None:
            _conflict()
    return previous, data['rows'], selected, carried


def accept_complete_input(db, user, session_id, run_id, tool_key, rows, *,
                          origin_request_id, intent_version=1, plan_id=None,
                          step_id=None, reprepare=None, execution_authorized=False):
    """Persist every accepted input row before any resolving GET can start.

    ``rows`` must be an already completely parsed list, never streamed fragments.
    The caller commits this short transaction before resolving native reads.
    ``tool_key`` is a server-validated stable call identity, not an array offset.
    """
    _require_authorized(execution_authorized)
    if type(rows) is not list or not rows:
        raise HTTPException(422, '请提供完整的业务行清单，不接受截断片段')
    clean_rows = []
    for row in rows:
        clean = _json(row)
        if service.scrub(clean) != clean or len(json.dumps(clean, ensure_ascii=False)) > 24000:
            raise HTTPException(422, '输入包含敏感、过长或不完整内容，请明确整理后再提交')
        clean_rows.append(clean)
    _text(tool_key, 100)
    _text(origin_request_id, 100)
    if type(intent_version) is not int or intent_version < 1:
        _conflict()
    with db.no_autoflush:
        thread = service.owned_session(db, user, session_id)
        plan, step = _plan_step(db, thread, user, plan_id, step_id)
        run = _run(db, thread, user, run_id, plan_id)
        if plan is not None and run.plan_id is not None and run.goal_version != plan.goal_version:
            _conflict()
        scope = {'owner_id': user.id, 'store_id': thread.store_id, 'session_id': thread.id,
                 'role': user.role, 'access_version': user.access_version,
                 'plan_id': plan_id, 'step_id': step_id, 'step_key': step.key if step else None,
                 'goal_version': plan.goal_version if plan else None,
                 'origin_request_id': origin_request_id, 'tool_key': tool_key,
                 'intent_version': intent_version}
        key = _manifest_key(scope)
        existing = list(db.scalars(select(RunItem).join(Run, Run.id == RunItem.run_id).where(
            RunItem.kind == 'tool', RunItem.item_key == key, RunItem.attempt_no == 1,
            Run.owner_id == user.id, Run.store_id == thread.store_id, Run.session_id == thread.id)))
        if len(existing) > 1:
            _conflict()
        if existing:
            data = _manifest_data(existing[0])
            old_scope = data['scope']
            # Background retries may have a different trigger/tool label. The
            # original manifest keeps the accepted origin and ordered row IDs.
            compared = ('owner_id', 'store_id', 'session_id', 'role', 'access_version',
                        'plan_id', 'step_id', 'step_key', 'intent_version')
            if (any(scope[field] != old_scope[field] for field in compared)
                    or data['input_digest'] != _digest(clean_rows)
                    or step is not None and step.intent_version != intent_version):
                _conflict()
            return existing[0]
        previous = None
        previous_rows = None
        selected = set()
        carried = set()
        if reprepare is not None:
            previous, previous_rows, selected, carried = _reprepare_rows(db, user, thread, reprepare, scope, clean_rows, step)
        elif intent_version != 1:
            _conflict()
        if step is not None:
            expected = intent_version - 1 if reprepare is not None else intent_version
            if step.intent_version != expected:
                _conflict()
            if step.proposal_id is not None:
                compatibility = db.scalar(select(AssistantProposal).where(AssistantProposal.id == step.proposal_id))
                if reprepare is None or compatibility is None:
                    _conflict()
                _same_scope(compatibility, thread, user)
                if _card_status(compatibility) not in {'failed', 'cancelled', 'expired'}:
                    _conflict()
            cas_row = step
        else:
            cas_row = thread
        records = []
        for position, raw in enumerate(clean_rows):
            old = previous_rows[position] if previous_rows is not None else None
            if old is not None and old['input_item_id'] in carried:
                records.append({**deepcopy(old), 'carry_forward': {
                    'manifest_id': previous.id,
                    'intent_version': previous.validated_arguments['scope']['intent_version']}})
                continue
            unprepared = old is not None and old['input_item_id'] not in selected
            # An unselected row with no real card has never submitted business.
            # Preserve its input/ID and missing-input result, but let its first
            # preparation occur under this current intent. Keep any old planned
            # WorkItem as supersedes instead of resetting that historical item.
            outcome = old['outcome'] if unprepared and old['outcome'] in {'pending', 'needs_input', 'failed'} else 'pending'
            records.append({'input_item_id': old['input_item_id'] if old else str(uuid4()),
                            'position': position, 'input': raw, 'input_digest': _digest(raw),
                            'outcome': outcome, 'work_item_id': None, 'proposal_id': None,
                            'proposal_status': None, 'reason_code': old.get('reason_code') if unprepared else None,
                            'message': old.get('message', '') if unprepared else '',
                            'supersedes_id': old.get('work_item_id') if old else None,
                            'carry_forward': None})
        data = {'schema_version': 1, 'scope': scope, 'input_digest': _digest(clean_rows),
                'previous_manifest_id': previous.id if previous else None,
                'previous_compatibility_proposal_id': step.proposal_id if step else None,
                'selected_input_item_ids': sorted(selected),
                'rows': records}
        # Force a real version UPDATE even if timestamps share a microsecond.
        # Concurrent first acceptance loses this CAS before its new IDs commit.
        cas_row.version += 1
        cas_row.updated_at = utcnow()
        if step is not None and reprepare is not None:
            step.intent_version = intent_version
            step.proposal_id = None
            step.status = 'waiting'
            step.wait_reason = None
        manifest = RunItem(id=str(uuid4()), run_id=run.id, kind='tool', item_key=key,
                           attempt_no=1, tool_name=_MANIFEST_TOOL, status='pending',
                           validated_arguments=data, result_refs=None, version=1,
                           created_at=utcnow())
        db.add(manifest)
        _flush(db)
        return manifest


def _intent_digest(values):
    semantic = deepcopy(values)
    for key in ('questions', 'question_fields'):
        semantic[key] = service.preparation_question_intent(semantic.get(key))
    return _digest(semantic)


def _intent(preparation):
    if not isinstance(preparation, service.ResolvedPreparation):
        raise TypeError('Expected server-resolved preparation')
    if type(preparation.generate_request_id) is not bool:
        _conflict()
    if preparation.generate_request_id and 'request_id' in preparation.body:
        _conflict()
    values = _json({
        'schema_version': 1, 'operation_id': preparation.operation_id,
        'path_args': preparation.path_args, 'query': preparation.query, 'body': preparation.body,
        'questions': preparation.questions, 'question_fields': preparation.question_fields,
        'generate_request_id': preparation.generate_request_id,
    })
    # M2.3 omitted only a server-generated request ID. Explicit native IDs,
    # versions, amounts, objects and all original employee fields remain here.
    return {**values, 'intent_digest': _intent_digest(values)}


def _same_intent(stored, current):
    values = _json(deepcopy(stored))
    digest = values.pop('intent_digest', None)
    return digest == _intent_digest(values) == current['intent_digest']


def _source_refs(preparation):
    references = _json(preparation.references)
    result = []
    for field, selection in references.items():
        _text(field, 160)
        reference = _json({'field': field, 'selection': _json(selection)})
        if service.scrub(reference) != reference:
            raise HTTPException(422, '来源引用包含敏感或过长内容，请重新核对')
        result.append(reference)
    return result


def _result_for_card(work, card):
    if card is None:
        if work.status != 'planned':
            _conflict()
        return 'pending'
    status = _card_status(card)
    if status in {'executing', 'uncertain'} or work.status == 'uncertain':
        return 'uncertain'
    if status == 'succeeded':
        work.status = 'settled'
        return 'settled'
    if status in {'failed', 'cancelled', 'expired'}:
        work.status = 'settled'
        return 'failed'
    if status == 'pending':
        return 'prepared'
    _conflict()


def _prepare_row(db, user, thread, data, row, preparation):
    scope = data['scope']
    actual = (preparation.owner_id, preparation.store_id, preparation.session_id,
              preparation.owner_role, preparation.access_version)
    if actual != (user.id, thread.store_id, thread.id, user.role, user.access_version):
        _conflict()
    intent = _intent(preparation)
    key = _work_key(scope, row['input_item_id'])
    work = db.scalar(select(WorkItem).where(WorkItem.owner_id == user.id,
        WorkItem.store_id == thread.store_id, WorkItem.intent_key == key))
    if work is not None:
        _same_scope(work, thread, user)
        if (work.plan_id != scope['plan_id'] or work.step_id != scope['step_id']
                or work.input_item_id != row['input_item_id'] or work.intent_version != scope['intent_version']
                or work.item_kind != 'prepare' or work.operation_id != preparation.operation_id
                or not _same_intent(work.validated_intent, intent) or work.supersedes_id != row.get('supersedes_id')):
            _conflict()
        card = _card(db, work, thread, user)
        if card is not None:
            verified = service.build_proposal(db, user, thread.id, preparation, source_work_item_id=work.id)
            if verified.id != card.id:
                _conflict()
            row.update(work_item_id=work.id, proposal_id=card.id, proposal_status=_card_status(card),
                       outcome=_result_for_card(work, card), reason_code=None, message='')
            return
        if work.status != 'planned':
            _conflict()
    else:
        if row.get('work_item_id') is not None or row.get('proposal_id') is not None:
            _conflict()
        previous_id = row.get('supersedes_id')
        if previous_id is not None:
            previous = db.scalar(select(WorkItem).where(WorkItem.id == previous_id))
            if previous is None:
                _conflict()
            _same_scope(previous, thread, user)
            old_card = _card(db, previous, thread, user)
            if (previous.item_kind != 'prepare' or previous.status == 'uncertain'
                    or previous.input_item_id != row['input_item_id']
                    or previous.intent_version >= scope['intent_version']
                    or previous.plan_id != scope['plan_id'] or previous.step_id != scope['step_id']
                    or old_card is None and previous.status != 'planned'
                    or old_card is not None and _card_status(old_card) not in {'failed', 'cancelled', 'expired'}):
                _conflict()
        work = WorkItem(id=str(uuid4()), owner_id=user.id, store_id=thread.store_id,
                        session_id=thread.id, plan_id=scope['plan_id'], step_id=scope['step_id'],
                        origin_request_id=scope['origin_request_id'], input_item_id=row['input_item_id'],
                        intent_version=scope['intent_version'], item_kind='prepare', intent_key=key,
                        operation_id=preparation.operation_id, validated_intent=intent,
                        source_refs=_source_refs(preparation), status='planned', supersedes_id=previous_id, version=1,
                        created_at=utcnow(), updated_at=utcnow())
        db.add(work)
        _flush(db)  # Source exists before the same-transaction proposal link.
    view = service.persist_preparation(db, user, thread.id, preparation, source_work_item_id=work.id)
    card = _card(db, work, thread, user)
    if card is None or card.id != view['id']:
        _conflict()
    work.status = 'prepared'
    row.update(work_item_id=work.id, proposal_id=card.id, proposal_status=_card_status(card),
               outcome=_result_for_card(work, card), reason_code=None, message='')


def _refresh_carried(db, user, thread, data, row, resolution):
    """Keep successful/unselected rows at their original intent and card."""
    carry = row['carry_forward']
    if type(carry) is not dict or set(carry) != {'manifest_id', 'intent_version'}:
        _conflict()
    _, _, previous = _owned_manifest(db, user, thread.id, carry['manifest_id'])
    current_scope = data['scope']
    old_scope = previous['scope']
    if (old_scope['plan_id'] != current_scope['plan_id'] or old_scope['step_id'] != current_scope['step_id']
            or carry['intent_version'] != old_scope['intent_version']
            or old_scope['intent_version'] >= current_scope['intent_version']):
        _conflict()
    old = next((item for item in previous['rows'] if item['input_item_id'] == row['input_item_id']), None)
    if (old is None or any(row.get(key) != old.get(key) for key in (
            'position', 'input_digest', 'work_item_id', 'supersedes_id'))
            or old.get('proposal_id') is not None and old['proposal_id'] != row.get('proposal_id')):
        _conflict()
    if row.get('work_item_id') is None:
        if row.get('proposal_id') is not None or resolution and resolution.preparation is not None:
            _conflict()
        return
    work = db.scalar(select(WorkItem).where(WorkItem.id == row['work_item_id']))
    if work is None:
        _conflict()
    _same_scope(work, thread, user)
    if (work.plan_id != current_scope['plan_id'] or work.step_id != current_scope['step_id']
            or work.input_item_id != row['input_item_id'] or work.item_kind != 'prepare'
            or work.intent_version >= current_scope['intent_version']):
        _conflict()
    if resolution and resolution.preparation is not None:
        preparation = resolution.preparation
        if ((preparation.owner_id, preparation.store_id, preparation.session_id,
             preparation.owner_role, preparation.access_version)
                != (user.id, thread.store_id, thread.id, user.role, user.access_version)
                or not _same_intent(work.validated_intent, _intent(preparation))):
            _conflict()
    card = _card(db, work, thread, user)
    if ((card.id if card is not None else None) != row.get('proposal_id')
            or work.status == 'uncertain' or card is not None and _card_status(card) in {'executing', 'uncertain'}):
        _conflict()
    row.update(outcome=_result_for_card(work, card),
               proposal_status=_card_status(card) if card is not None else None)


def _resolutions(rows):
    if type(rows) is not list:
        raise HTTPException(422, '需要完整且带稳定行标识的解析结果')
    result = {}
    for row in rows:
        if not isinstance(row, RowResolution) or row.input_item_id in result:
            _conflict()
        if row.preparation is not None:
            _intent(row.preparation)
            if row.outcome not in {'pending', 'prepared'}:
                _conflict()
        elif row.outcome not in {'pending', 'needs_input', 'failed'}:
            _conflict()
        if row.reason_code is not None:
            _text(row.reason_code, 80)
        if type(row.message) is not str:
            _conflict()
        result[row.input_item_id] = row
    return result


def _prepare_rows(db, user, session_id, manifest_id, resolutions, *,
                  execution_authorized, max_preparations, partial):
    _require_authorized(execution_authorized)
    resolved = _resolutions(resolutions)
    if max_preparations is not None and (type(max_preparations) is not int or max_preparations < 0):
        raise HTTPException(422, '准备预算必须是非负整数')
    with db.no_autoflush:
        thread, manifest, data = _owned_manifest(db, user, session_id, manifest_id)
        scope = data['scope']
        plan, step = _plan_step(db, thread, user, scope['plan_id'], scope['step_id'])
        if step is not None and (step.intent_version != scope['intent_version'] or step.proposal_id is not None):
            _conflict()
        known = {row['input_item_id'] for row in data['rows']}
        if set(resolved) - known or not partial and set(resolved) != known:
            _conflict()
        # Check all carried rows before creating any selected row's new card.
        # A newly executing/unknown predecessor blocks the complete reprepare.
        for row in data['rows']:
            if row.get('carry_forward') is not None:
                _refresh_carried(db, user, thread, data, row, resolved.get(row['input_item_id']))
        used = 0
        pending_count = db.scalar(select(func.count()).select_from(AssistantProposal).where(
            AssistantProposal.owner_id == user.id, AssistantProposal.store_id == thread.store_id,
            AssistantProposal.session_id == thread.id, AssistantProposal.status == 'pending',
            AssistantProposal.expires_at > utcnow())) or 0
        capacity = max(0, service.MAX_PENDING_PROPOSALS - pending_count)
        session_claimed = False
        for row in data['rows']:
            if row.get('carry_forward') is not None:
                continue
            result = resolved.get(row['input_item_id'])
            if result is None:
                continue
            if result.preparation is None:
                # A later source-resolution error must not erase a durable card
                # or pretend that a failed/unknown preparation is pending again.
                if row.get('work_item_id') is None:
                    row.update(outcome=result.outcome, reason_code=result.reason_code,
                               message=service.safe_text(result.message, 600))
                continue
            # Reusing a source card consumes neither the new-card budget nor
            # remaining pending-card capacity; retries must reach later rows.
            key = _work_key(scope, row['input_item_id'])
            prior_work = db.scalar(select(WorkItem).where(WorkItem.owner_id == user.id,
                WorkItem.store_id == thread.store_id, WorkItem.intent_key == key))
            preparation = result.preparation
            if ((preparation.owner_id, preparation.store_id, preparation.session_id,
                 preparation.owner_role, preparation.access_version)
                    != (user.id, thread.store_id, thread.id, user.role, user.access_version)):
                _conflict()
            if prior_work is not None:
                _same_scope(prior_work, thread, user)
                if (prior_work.plan_id != scope['plan_id'] or prior_work.step_id != scope['step_id']
                        or prior_work.input_item_id != row['input_item_id']
                        or prior_work.intent_version != scope['intent_version']
                        or prior_work.item_kind != 'prepare' or prior_work.operation_id != preparation.operation_id
                        or prior_work.supersedes_id != row.get('supersedes_id')):
                    _conflict()
            elif row.get('work_item_id') is not None or row.get('proposal_id') is not None:
                _conflict()
            prior_card = _card(db, prior_work, thread, user) if prior_work is not None else None
            if prior_work is not None and not _same_intent(prior_work.validated_intent, _intent(result.preparation)):
                _conflict()
            needs_card = prior_card is None
            if needs_card and prior_work is not None and prior_work.status != 'planned':
                _conflict()
            if needs_card and (capacity == 0 or max_preparations is not None and used >= max_preparations):
                row.update(outcome='pending', reason_code='pending_card_capacity' if capacity == 0 else 'preparation_budget',
                           message='待确认卡或本次准备额度已达上限，此行完整保留待继续')
                continue
            if needs_card and not session_claimed:
                # Every new-card writer uses the originally read session version
                # to protect the capacity count across different manifests/steps.
                # Losing this CAS requires caller rollback and a fresh count.
                thread.version += 1
                thread.updated_at = utcnow()
                _flush(db)
                session_claimed = True
            _prepare_row(db, user, thread, data, row, result.preparation)
            if needs_card:
                used += 1
                capacity -= 1
        manifest.validated_arguments = data
        unfinished = any(row['outcome'] == 'pending' for row in data['rows'])
        unknown = any(row['outcome'] == 'uncertain' for row in data['rows'])
        failed = any(row['outcome'] == 'failed' for row in data['rows'])
        manifest.status = 'uncertain' if unknown else 'running' if unfinished else 'failed' if failed else 'succeeded'
        if manifest.started_at is None:
            manifest.started_at = utcnow()
        manifest.finished_at = None if unfinished or unknown else utcnow()
        _flush(db)
        return [{key: deepcopy(row[key]) for key in (
            'input_item_id', 'position', 'outcome', 'work_item_id', 'proposal_id',
            'proposal_status', 'reason_code', 'message', 'carry_forward')} for row in data['rows']]


def prepare_rows(db, user, session_id, manifest_id, resolutions, *,
                 execution_authorized=False, max_preparations=None):
    """Persist a complete resolution vector; preserve every unattempted row.

    All resolving GETs must already be finished. A row-level resolution failure
    belongs in RowResolution; a transaction/intent conflict raises and requires
    caller rollback. A success here means a prepared card, never business success.
    """
    return _prepare_rows(db, user, session_id, manifest_id, resolutions,
                         execution_authorized=execution_authorized,
                         max_preparations=max_preparations, partial=False)


def prepare_work_item(db, user, session_id, manifest_id, input_item_id, preparation, *,
                      execution_authorized=False):
    """Prepare one previously accepted row, preserving the complete manifest."""
    results = _prepare_rows(db, user, session_id, manifest_id,
        [RowResolution(input_item_id=input_item_id, preparation=preparation)],
        execution_authorized=execution_authorized, max_preparations=1, partial=True)
    return next(row for row in results if row['input_item_id'] == input_item_id)


# Runtime coordination below deliberately leaves the M2 primitives flush-only.
# Every public write boundary owns a short transaction; every awaited resolver
# runs before that transaction. These functions are internal worker APIs.
@dataclass(frozen=True)
class ToolCheckpoint:
    model_item_id: str
    tool_item_ids: tuple[str, ...]


@dataclass(frozen=True)
class ToolExecution:
    principal: object
    tool_messages: tuple[dict, ...] = field(repr=False)
    needs_input: bool = False
    stop: bool = False
    new_preparations: int = 0


@dataclass(frozen=True)
class RecoveryState:
    checkpoints: tuple[ToolCheckpoint, ...]
    tool_messages: tuple[dict, ...] = field(repr=False)
    receipt_checks: tuple[dict, ...] = field(repr=False)
    needs_input: bool = False


def _runtime_now(principal, clock=None):
    from .assistant_runtime_principal import _time
    return _time((clock or principal._clock)())


def _runtime_scope(db, principal):
    from .assistant_runtime_queue import _scope
    if db.info.get('aggregate_scope'):
        raise HTTPException(403, 'Runtime 只能使用员工当前单店范围')
    _scope(db, principal.store_id)


def _finish_write(db, principal, clock=None):
    from .assistant_runtime_principal import revalidate_principal
    db.flush()
    revalidate_principal(db, principal, clock=clock)
    service.commit(db)


def _runtime_item(db, principal, item_id):
    item = db.scalar(select(RunItem).where(RunItem.id == _UUID.validate_python(item_id),
        RunItem.run_id == principal.run_id).execution_options(populate_existing=True))
    if item is None or item.kind == 'confirmation' or item.tool_name == _MANIFEST_TOOL:
        _conflict()
    return item


def _tool_data(item):
    value = _json(deepcopy(item.validated_arguments))
    required = {'schema_version', 'envelope', 'model_item_id', 'call_id', 'name',
                'arguments', 'manifest_id', 'input_item_id', 'step_id'}
    if (set(value) != required or value['schema_version'] != 1
            or value['envelope'] != 'runtime_tool' or value['name'] != item.tool_name
            or type(value['call_id']) is not str or not value['call_id']
            or type(value['arguments']) is not dict
            or item.kind not in {'tool', 'batch_row'}):
        _conflict()
    for key in ('model_item_id', 'manifest_id', 'input_item_id', 'step_id'):
        if value[key] is not None:
            _UUID.validate_python(value[key])
    if item.kind == 'batch_row' and (value['manifest_id'] is None or value['input_item_id'] is None):
        _conflict()
    return value


def _call_rows(name, args):
    if name in {'prepare_operations', 'prepare_business_batch'}:
        if name == 'prepare_business_batch' and args['form_ref'].startswith('case:'):
            raise HTTPException(409, '同一原单的动作不能当成独立批量；请按真实依赖逐项准备')
        rows = args.get('rows')
        if type(rows) is not list or not rows:
            raise HTTPException(422, '请提供完整批量行，不能保存空的准备清单')
        shared = {key: deepcopy(value) for key, value in args.items() if key != 'rows'}
        if name == 'prepare_business_batch':
            shared['step_order'] = 1  # Exact original per-row business wrapper.
        return [{**deepcopy(shared), **deepcopy(row)} for row in rows]
    return [deepcopy(args)]


def _preparation_target(name, args):
    """Only exact native mappings already defined by the original form layer."""
    ref = args.get('form_ref') if name in {'prepare_business_form', 'prepare_business_batch'} else None
    obj = None
    if name in {'prepare_case_action', 'prepare_customer_contact'}:
        obj = {'type': 'case', 'id': args.get('case_id')}
        if name == 'prepare_case_action':
            ref = f"case:{args.get('case_id')}:{args.get('action')}"
    elif name in {'prepare_operation', 'prepare_operations'}:
        op, path, body = args.get('operation_id'), args.get('path_args') or {}, args.get('body') or {}
        if op == 'POST /api/flow/cases/{case_id}/actions/{action}':
            obj = {'type': 'case', 'id': path.get('case_id')}
            ref = f"case:{path.get('case_id')}:{path.get('action')}"
        elif op == 'POST /api/flow/cases':
            values = [row.get('body', {}).get('kind') for row in args['rows']] if name == 'prepare_operations' else [body.get('kind')]
            if values and all(type(value) is str and value for value in values) and len(set(values)) == 1:
                ref = 'flow:' + values[0]
        elif op in {'POST /api/masters/{kind}', 'POST /api/flow/master/{kind}'} and type(path.get('kind')) is str and path['kind']:
            ref = ('master:' if op == 'POST /api/masters/{kind}' else 'crm:') + path['kind']
    if ref and ref.startswith('case:'):
        parts = ref.split(':')
        if len(parts) == 3 and parts[1].isascii() and parts[1].isdigit():
            obj = {'type': 'case', 'id': int(parts[1])}
    return ref, obj


def _bind_preparations(calls, evaluation, state):
    by_id = {step.step_id: step for step in evaluation.steps}
    bindings = {}
    for call in calls:
        if call.kind != 'prepare':
            continue
        form, obj = _preparation_target(call.name, call.arguments)
        candidates = [step for step in state['snapshot']['steps']
            if form is not None and step['form_ref'] == form
            and (obj is None or step['object_ref'] == obj)]
        if len(candidates) != 1 or not by_id[candidates[0]['id']].preparation_ready:
            raise HTTPException(409, '当前工具尚未对应唯一且满足前置条件的真实步骤，请先核对事项和原单')
        bindings[call.id] = (candidates[0]['id'], candidates[0]['intent_version'])
    return bindings


async def checkpoint(db, principal, config, message, *, model_key, clock=None, client_factory=None):
    """Accept one complete provider fragment, including every original batch row.

    model_key is a stable server turn key. Neither display step labels nor model
    supplied UUIDs select a PlanStep. A new plan must first be saved in a separate
    fragment, so preparation can bind its real, committed steps and conditions.
    """
    from .assistant_runtime_principal import revalidate_principal
    from .assistant_runtime_registry import registry_for_config
    from .assistant_runtime_queue import lock_for_write
    from . import assistant_runtime_plans as plans
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    _runtime_scope(db, principal)
    model_key = _text(model_key, 100)
    if type(message) is not dict or message.get('role') != 'assistant':
        raise HTTPException(422, '仅完整模型回复可进入工具检查点')
    registry = registry_for_config(config)
    raw_calls = message.get('tool_calls')
    calls = registry.validate_calls([] if raw_calls is None else raw_calls)
    from .assistant_runtime_context import _text as safe_source_text
    if any(safe_source_text(call.id) != call.id for call in calls):
        raise HTTPException(422, '工具调用标识包含敏感内容，不能保存')
    if any(call.name == 'save_work_plan' for call in calls) and any(call.kind == 'prepare' for call in calls):
        raise HTTPException(409, '请先保存事项并取得真实步骤，再单独准备完整业务清单')
    # The immutable envelope contains only validated tool inputs. Never persist
    # assistant content, provider response dumps, usage, or reasoning_content.
    entries = [{'id': call.id, 'name': call.name, 'arguments': deepcopy(call.arguments), 'kind': call.kind} for call in calls]
    envelope = _json({'schema_version': 1, 'envelope': 'runtime_model_tools', 'model_key': model_key, 'calls': entries})
    if any(service.scrub(call.arguments) != call.arguments for call in calls if call.kind != 'prepare'):
        raise HTTPException(422, '完整工具输入包含敏感或过长内容，请整理后重试，不能截断保存')
    # Preparation rows retain the original M2 per-row boundary. Wrapping them
    # inside a model envelope must not consume the legacy scrub depth budget.
    for call in calls:
        if call.kind == 'prepare' and any(service.scrub(row) != row for row in _call_rows(call.name, call.arguments)):
            raise HTTPException(422, '完整业务行包含敏感或过长内容，请整理后重试，不能截断保存')
    key = 'model:' + _digest({'run': principal.run_id, 'key': model_key})
    prior = db.scalar(select(RunItem).where(RunItem.run_id == principal.run_id,
        RunItem.item_key == key, RunItem.attempt_no == 1).execution_options(populate_existing=True))
    if prior is not None:
        if prior.kind != 'model' or prior.validated_arguments != envelope:
            _conflict()
        parents = [item for item in _latest_attempts(db, principal) if item.kind == 'tool'
                   and _tool_data(item)['model_item_id'] == prior.id]
        by_call = {_tool_data(item)['call_id']: item.id for item in parents}
        if len(by_call) != len(parents) or set(by_call) != {call.id for call in calls}:
            _conflict()
        result = ToolCheckpoint(prior.id, tuple(by_call[call.id] for call in calls))
        _checkpoint_items(db, principal, config, result)
        db.rollback()
        revalidate_principal(db, principal, clock=clock)
        return result
    evaluation = state = None
    bindings = {}
    if principal.plan_id and any(call.kind == 'prepare' for call in calls):
        evaluation = await plans.evaluate_plan_conditions(db, principal,
            clock=clock or principal._clock, client_factory=client_factory)
        state = plans._evaluations.get(evaluation)
        if state is None:
            _conflict()
        bindings = _bind_preparations(calls, evaluation, state)
    db.rollback()  # End only this clean, owned read phase before the write CAS.
    try:
        thread, plan, run = lock_for_write(db, principal, clock=clock or principal._clock)
        old = db.scalar(select(RunItem).where(RunItem.run_id == run.id, RunItem.item_key == key, RunItem.attempt_no == 1))
        if old is not None:
            if old.kind != 'model' or old.validated_arguments != envelope:
                _conflict()
            items = [item for item in _latest_attempts(db, principal) if item.kind == 'tool']
            by_call = {_tool_data(item)['call_id']: item.id for item in items
                if item.tool_name != _MANIFEST_TOOL and _tool_data(item)['model_item_id'] == old.id}
            if set(by_call) != {call.id for call in calls}:
                _conflict()
            result = ToolCheckpoint(old.id, tuple(by_call[call.id] for call in calls))
            _checkpoint_items(db, principal, config, result)
            db.rollback()
            revalidate_principal(db, principal, clock=clock)
            return result
        if state is not None:
            plans.consume_preparation_evaluation(db, principal, evaluation,
                step_ids=tuple(sorted({value[0] for value in bindings.values()})), clock=clock)
        now = _runtime_now(principal, clock)
        model = RunItem(id=str(uuid4()), run_id=run.id, kind='model', item_key=key,
            attempt_no=1, validated_arguments=envelope, status='succeeded', result_refs=None,
            started_at=now, finished_at=now, created_at=now, version=1)
        db.add(model)
        item_ids = []
        for call in calls:
            manifest = None
            step_id, intent_version = bindings.get(call.id, (None, 1))
            tool_key = 'call:' + _digest({'model': model_key, 'call': call.id})
            if call.kind == 'prepare':
                manifest = accept_complete_input(db, principal, principal.session_id, run.id, tool_key,
                    _call_rows(call.name, call.arguments), origin_request_id=run.request_id or ('run:' + run.id),
                    plan_id=principal.plan_id, step_id=step_id, intent_version=intent_version,
                    execution_authorized=True)
            data = {'schema_version': 1, 'envelope': 'runtime_tool', 'model_item_id': model.id,
                'call_id': call.id, 'name': call.name, 'arguments': deepcopy(call.arguments),
                'manifest_id': manifest.id if manifest else None, 'input_item_id': None, 'step_id': step_id}
            item = RunItem(id=str(uuid4()), run_id=run.id, kind='tool', item_key=tool_key, attempt_no=1,
                tool_name=call.name, validated_arguments=data, status='pending', version=1, created_at=now)
            db.add(item)
            item_ids.append(item.id)
            if manifest is not None and call.name in {'prepare_operations', 'prepare_business_batch'}:
                for row in _manifest_data(manifest)['rows']:
                    child = RunItem(id=str(uuid4()), run_id=run.id, kind='batch_row',
                        item_key='row:' + _digest({'tool': tool_key, 'input': row['input_item_id']}), attempt_no=1,
                        tool_name=call.name, validated_arguments={**deepcopy(data), 'input_item_id': row['input_item_id']},
                        status='pending', version=1, created_at=now)
                    db.add(child)
        _finish_write(db, principal, clock)
        return ToolCheckpoint(model.id, tuple(item_ids))
    except Exception:
        db.rollback()
        raise


async def runtime_read_tool(db, request, user, session_id, name, args, config, *, principal=None):
    """Fixed Runtime read lane, used by nested legacy resolvers as well.

    The service wrapper must select this lane only for a real private principal
    carrier. It never records an issue or commits legacy discovery bookkeeping.
    All original native operation, method, parameter and role guards still run.
    """
    from .assistant_runtime_principal import runtime_request_context, revalidate_principal, native_reader_for_principal
    from .assistant_runtime_registry import registry_for_config
    from . import business_assistant_gateway as gateway
    service.require_preparation_read_phase(db)
    context = runtime_request_context(request)
    if (context is None or context.db is not db or context.principal is not user
            or principal is not None and principal is not context.principal
            or session_id != context.principal.session_id):
        raise HTTPException(403, '内部查询身份来源不正确')
    principal = revalidate_principal(db, context.principal)
    _runtime_scope(db, principal)
    registry = registry_for_config(config)
    spec = registry.spec(name)
    if spec.kind != 'read':
        raise HTTPException(403, '内部只读通道不能保存计划或准备卡片')
    args = registry.validate_arguments(name, args)
    if name == 'inspect_operation':
        result = gateway.inspect_operation(args.get('operation_id', ''))
    elif name == 'read_data':
        if args.get('body'):
            raise HTTPException(403, '查询不能提交业务修改，请先准备待确认表单')
        operation = gateway.inspect_operation(args.get('operation_id', ''))
        if operation['method'] != 'GET' or operation.get('write'):
            raise HTTPException(403, '新增或修改需要先生成待确认操作')
        reader = native_reader_for_principal(db, principal, (operation['id'],), client_factory=context.client_factory)
        db.rollback()
        result = await reader(operation['id'], path_args=args.get('path_args') or {}, query=args.get('query') or {}, body=None)
        result = service.scrub(result)
    else:
        result = await spec.handler(db, request, principal, session_id, args, config, resolve_only=True)
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal)
    return result


def _latest_attempts(db, principal):
    items = list(db.scalars(select(RunItem).where(RunItem.run_id == principal.run_id,
        RunItem.kind.in_({'tool', 'batch_row'}), RunItem.tool_name != _MANIFEST_TOOL)
        .order_by(RunItem.created_at, RunItem.id).execution_options(populate_existing=True)))
    latest = {}
    for item in items:
        _tool_data(item)
        if item.item_key not in latest or item.attempt_no > latest[item.item_key].attempt_no:
            latest[item.item_key] = item
    return list(latest.values())


def _start_attempt(db, principal, item_id, *, retry_read=False, clock=None):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    service.require_preparation_read_phase(db)
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock or principal._clock)
        item = _runtime_item(db, principal, item_id)
        if item.status == 'succeeded':
            db.rollback()
            return None
        if item.status in {'uncertain', 'skipped'}:
            _conflict()
        now = _runtime_now(principal, clock)
        if retry_read and item.status in {'running', 'failed'}:
            latest = db.scalar(select(func.max(RunItem.attempt_no)).where(RunItem.run_id == principal.run_id, RunItem.item_key == item.item_key))
            if latest != item.attempt_no:
                _conflict()
            if item.status == 'running':
                item.status, item.finished_at, item.error_code = 'failed', now, 'runtime_unavailable'
                db.flush()
                append_event(db, principal, 'tool.finished', {'run_item_id': item.id,
                    'work_item_id': item.work_item_id, 'result_refs': item.result_refs or []}, clock=clock)
            item = RunItem(id=str(uuid4()), run_id=principal.run_id, kind=item.kind,
                item_key=item.item_key, attempt_no=item.attempt_no + 1, tool_name=item.tool_name,
                validated_arguments=deepcopy(item.validated_arguments), work_item_id=item.work_item_id,
                status='pending', version=1, created_at=now)
            db.add(item)
        elif item.status not in {'pending', 'running'}:
            _conflict()
        item.status, item.started_at, item.finished_at = 'running', now, None
        item.error_code = None
        _finish_write(db, principal, clock)
        return item.id
    except Exception:
        db.rollback()
        raise


def _message(call_id, value):
    # Kept only in the current tool chain. Persisted checkpoints never contain
    # this materialized response or any provider reasoning.
    return {'role': 'tool', 'tool_call_id': call_id,
            'content': json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)}


def _model_calls(item, registry):
    data = _json(deepcopy(item.validated_arguments))
    if (item.kind != 'model' or item.status != 'succeeded'
            or set(data) != {'schema_version', 'envelope', 'model_key', 'calls'}
            or data['schema_version'] != 1 or data['envelope'] != 'runtime_model_tools'
            or type(data['calls']) is not list):
        _conflict()
    calls = []
    for row in data['calls']:
        if type(row) is not dict or set(row) != {'id', 'name', 'arguments', 'kind'}:
            _conflict()
        calls.append({'id': row['id'], 'type': 'function', 'function': {'name': row['name'],
            'arguments': json.dumps(row['arguments'], ensure_ascii=False, separators=(',', ':'), allow_nan=False)}})
    validated = registry.validate_calls(calls)
    if any(row['kind'] != call.kind or row['arguments'] != call.arguments for row, call in zip(data['calls'], validated)):
        _conflict()
    return validated


def _checkpoint_items(db, principal, config, checkpoint_value):
    from .assistant_runtime_registry import registry_for_config
    if type(checkpoint_value) is not ToolCheckpoint:
        raise TypeError('Expected a persisted ToolCheckpoint')
    model = _runtime_item(db, principal, checkpoint_value.model_item_id)
    calls = _model_calls(model, registry_for_config(config))
    parents = {item.item_key: item for item in _latest_attempts(db, principal) if item.kind == 'tool'
               and _tool_data(item)['model_item_id'] == model.id}
    by_call = {}
    for item in parents.values():
        data = _tool_data(item)
        if data['call_id'] in by_call:
            _conflict()
        by_call[data['call_id']] = item
    if set(by_call) != {call.id for call in calls}:
        _conflict()
    # The accepted checkpoint may name attempt 1; recovery selects the latest
    # actual attempt with that same durable item_key, never an arbitrary ID.
    originals = [_runtime_item(db, principal, value) for value in checkpoint_value.tool_item_ids]
    if len(originals) != len(calls):
        _conflict()
    for original, call in zip(originals, calls):
        item = by_call[call.id]
        data = _tool_data(item)
        if (original.item_key != item.item_key or data['name'] != call.name
                or data['arguments'] != call.arguments or data['input_item_id'] is not None):
            _conflict()
        if call.kind == 'prepare':
            if data['manifest_id'] is None:
                _conflict()
            _, manifest, manifest_data = _owned_manifest(db, principal, principal.session_id, data['manifest_id'])
            scope = manifest_data['scope']
            historical = (scope['plan_id'] is None and principal.plan_id is not None
                          and _completed_unbound_manifest(db, principal, manifest, manifest_data))
            if ((scope['plan_id'] != principal.plan_id and not historical) or scope['step_id'] != data['step_id']
                    or manifest_data['input_digest'] != _digest(_call_rows(call.name, call.arguments))):
                _conflict()
            if call.name in {'prepare_operations', 'prepare_business_batch'}:
                children = [child for child in _latest_attempts(db, principal) if child.kind == 'batch_row'
                    and _tool_data(child)['model_item_id'] == model.id and _tool_data(child)['call_id'] == call.id]
                child_ids = [_tool_data(child)['input_item_id'] for child in children]
                expected = [row['input_item_id'] for row in manifest_data['rows']]
                if len(child_ids) != len(expected) or set(child_ids) != set(expected):
                    _conflict()
                for child in children:
                    value = _tool_data(child)
                    if any(value[key] != data[key] for key in ('arguments', 'manifest_id', 'step_id', 'name')):
                        _conflict()
        elif data['manifest_id'] is not None or data['input_item_id'] is not None:
            _conflict()
    return model, [(call, by_call[call.id]) for call in calls]


def _completed_unbound_manifest(db, principal, manifest, data):
    """Historical display only after this exact Run acquired its own new Plan."""
    from .assistant_runtime_queue import runtime_busy_token
    scope = data['scope']
    if (manifest.run_id != principal.run_id or scope['plan_id'] is not None
            or scope['step_id'] is not None or scope['goal_version'] is not None):
        return False
    if principal.plan_id:
        plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == principal.plan_id,
            AssistantWorkPlan.owner_id == principal.actor_id, AssistantWorkPlan.store_id == principal.store_id,
            AssistantWorkPlan.session_id == principal.session_id))
        if plan is None or plan.request_id != runtime_busy_token(principal.run_id):
            return False
    attempts = [item for item in _latest_attempts(db, principal)
                if _tool_data(item)['manifest_id'] == manifest.id]
    if not attempts or any(item.status != 'succeeded' for item in attempts) or manifest.status != 'succeeded':
        return False
    parents = [item for item in attempts if item.kind == 'tool']
    if not parents:
        return False
    for parent in parents:
        value = _tool_data(parent)
        if (value['step_id'] is not None or value['input_item_id'] is not None
                or _digest(_call_rows(parent.tool_name, value['arguments'])) != data['input_digest']):
            return False
        if parent.tool_name in {'prepare_operations', 'prepare_business_batch'}:
            children = [_tool_data(item)['input_item_id'] for item in attempts if item.kind == 'batch_row'
                and _tool_data(item)['model_item_id'] == value['model_item_id']
                and _tool_data(item)['call_id'] == value['call_id']]
            if len(children) != len(data['rows']) or set(children) != {row['input_item_id'] for row in data['rows']}:
                return False
    thread = service.owned_session(db, principal, principal.session_id)
    for row in data['rows']:
        if not row.get('work_item_id') or not row.get('proposal_id'):
            return False
        work = db.scalar(select(WorkItem).where(WorkItem.id == row['work_item_id']))
        if work is None:
            return False
        _same_scope(work, thread, principal)
        if (work.plan_id is not None or work.step_id is not None or work.item_kind != 'prepare'
                or work.input_item_id != row['input_item_id']):
            return False
        card = _card(db, work, thread, principal)
        if card is None or card.id != row['proposal_id']:
            return False
    return True


def _may_bind_new_plan(db, principal):
    """Never silently move unfinished unbound work to a newly created goal."""
    for manifest in db.scalars(select(RunItem).where(RunItem.run_id == principal.run_id,
        RunItem.kind == 'tool', RunItem.tool_name == _MANIFEST_TOOL)):
        data = _manifest_data(manifest)
        if data['scope']['plan_id'] is None and not _completed_unbound_manifest(db, principal, manifest, data):
            raise HTTPException(409, '本次执行仍有未完成或待核对的原清单，请先处理后再建立事项')
        if data['scope']['plan_id'] is None:
            for row in data['rows']:
                card = db.scalar(select(AssistantProposal).where(AssistantProposal.id == row['proposal_id']))
                if card is None or _card_status(card) in {'executing', 'uncertain'}:
                    raise HTTPException(409, '原操作结果尚待核对，请先查原回执，不能把它当作新事项重新办理')
    for item in _latest_attempts(db, principal):
        if item.work_item_id:
            work = db.scalar(select(WorkItem).where(WorkItem.id == item.work_item_id))
            if work and work.item_kind == 'read' and work.plan_id is None and item.status != 'succeeded':
                raise HTTPException(409, '本次执行仍有未完成的原查询，请先收尾后再建立事项')


def _stored_tool_result(db, principal, item):
    """Read owned references/cards; never reconstruct a native success payload."""
    from .assistant_runtime_schemas import BusinessObjectRef
    data = _tool_data(item)
    refs = [BusinessObjectRef.model_validate(value).model_dump(mode='json') for value in item.result_refs or []]
    result = {'status': item.status, 'recovered': True, 'result_refs': refs}
    if data['manifest_id'] is not None:
        thread, manifest, values = _owned_manifest(db, principal, principal.session_id, data['manifest_id'])
        rows = []
        for row in values['rows']:
            work = db.scalar(select(WorkItem).where(WorkItem.id == row['work_item_id']).execution_options(populate_existing=True)) if row['work_item_id'] else None
            card = None
            if work is not None:
                _same_scope(work, thread, principal)
                if (work.plan_id != values['scope']['plan_id'] or work.step_id != values['scope']['step_id']
                        or work.input_item_id != row['input_item_id']):
                    _conflict()
                card = _card(db, work, thread, principal)
            if (card.id if card else None) != row.get('proposal_id'):
                _conflict()
            rows.append({'input_item_id': row['input_item_id'], 'position': row['position'],
                'work_item_id': work.id if work else None, 'proposal_id': card.id if card else None,
                'proposal_status': _card_status(card) if card else None,
                'outcome': row['outcome'], 'reason_code': row.get('reason_code')})
        result.update(rows=rows, input_count=len(rows), requires_employee_confirmation=True)
    elif item.proposal_id:
        # Non-manifest legacy proposals are not a Runtime preparation result.
        _conflict()
    return result


def _recovery_snapshot(db, principal, config):
    """Read the complete accepted frames and their current owned card states."""
    from .assistant_runtime_registry import registry_for_config
    models = list(db.scalars(select(RunItem).where(RunItem.run_id == principal.run_id,
        RunItem.kind == 'model').order_by(RunItem.created_at, RunItem.id).execution_options(populate_existing=True)))
    latest = _latest_attempts(db, principal)
    checkpoints, messages, proposal_ids = [], [], set()
    needs_input = False
    for model in models:
        calls = _model_calls(model, registry_for_config(config))
        parents = [item for item in latest if item.kind == 'tool' and _tool_data(item)['model_item_id'] == model.id]
        by_call = {_tool_data(item)['call_id']: item for item in parents}
        if len(by_call) != len(parents) or set(by_call) != {call.id for call in calls}:
            _conflict()
        check = ToolCheckpoint(model.id, tuple(by_call[call.id].id for call in calls))
        _, checked = _checkpoint_items(db, principal, config, check)
        if any(item.status in {'pending', 'running', 'failed'} for _, item in checked):
            checkpoints.append(check)
        for call, item in checked:
            result = _stored_tool_result(db, principal, item)
            if item.status in {'succeeded', 'uncertain', 'skipped'}:
                messages.append(_message(call.id, result))
            if item.status in {'uncertain', 'skipped', 'failed'}:
                needs_input = True
            for row in result.get('rows', []):
                if row['proposal_status'] in {'executing', 'uncertain'}:
                    proposal_ids.add(row['proposal_id'])
                    needs_input = True
    return tuple(checkpoints), tuple(messages), proposal_ids, needs_input


async def recover_items(db, principal, config, *, clock=None, client_factory=None):
    """Reconcile accepted unknown confirmations, then rebuild recovery reads.

    Phase one proves the full model/tool/manifest links and, for a bound Run,
    checks the current Plan's complete card projection as well. The latter
    includes an earlier Run's cards when an employee explicitly continues.
    The receipt service re-reads the frozen employee confirmation and
    original GET, then may reconcile proven success under this Run's real
    lease/fence in its own short transaction. No confirmation POST is retried.
    Phase two reads every frame and card again after all reconciliation commits;
    no pre-reconciliation outcome or needs_input flag survives into the return.

    tool_messages are recovery observations, NOT a replayable provider chain.
    A caller starts a fresh context, never sends orphan role=tool messages, and
    never reconstructs old reasoning. Unfinished reads retain their existing
    execute_tools attempt rules; this function does not replay successful tools.
    """
    from .assistant_runtime_principal import revalidate_principal
    from .assistant_runtime_receipts import reconcile_confirmation, reconcile_plan_confirmations
    from .assistant_runtime_plans import _condition_snapshot
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    if principal.run_id is None:
        _conflict('执行恢复必须属于已领取的真实执行')
    _runtime_scope(db, principal)
    db.rollback()
    _, _, proposal_ids, _ = _recovery_snapshot(db, principal, config)
    checks = []
    if principal.plan_id is not None:
        checks.extend(await reconcile_plan_confirmations(db, principal,
            clock=clock, client_factory=client_factory))
    checked_ids = {value['proposal_id'] for value in checks}
    for proposal_id in sorted(proposal_ids - checked_ids):
        service.require_preparation_read_phase(db)
        db.rollback()
        revalidate_principal(db, principal, clock=clock)
        lookup = await reconcile_confirmation(db, principal, proposal_id,
            clock=clock, client_factory=client_factory)
        checks.append({'proposal_id': proposal_id, 'lookup': lookup.model_dump(mode='json')})
    service.require_preparation_read_phase(db)
    db.rollback()
    revalidate_principal(db, principal, clock=clock)
    checkpoints, messages, _, needs_input = _recovery_snapshot(db, principal, config)
    if principal.plan_id is not None:
        current_plan = _condition_snapshot(db, principal)
        needs_input = needs_input or any(row['proposal_id'] and row['status'] in {'executing', 'uncertain'}
            for step in current_plan['steps'] for row in step['rows'])
    revalidate_principal(db, principal, clock=clock)
    return RecoveryState(checkpoints, messages, tuple(checks), needs_input)


def _error_code(status):
    return ('permission_denied' if status in {401, 403} else 'not_found' if status == 404
            else 'precondition_conflict' if status == 409 else 'invalid_input' if status == 422
            else 'runtime_unavailable')


def _read_intent(name, args):
    """Only a real single original GET can be a durable read WorkItem."""
    from . import business_assistant_gateway as gateway
    if name != 'read_data':
        return None
    normalized = gateway.validate_operation(args['operation_id'], args.get('path_args') or {},
                                            args.get('query') or {}, None)
    operation = normalized['operation']
    if operation['method'] != 'GET' or operation.get('write'):
        raise HTTPException(403, '查询不能提交业务修改')
    return {'operation_id': operation['id'], 'path_args': deepcopy(normalized.get('path_args') or {}),
            'query': deepcopy(normalized.get('query') or {}), 'body': None}


def _accept_read_work(db, principal, item_id, intent, *, clock=None):
    """Freeze one authorized GET once; later read attempts retain its identity."""
    from .assistant_runtime_queue import lock_for_write
    service.require_preparation_read_phase(db)
    db.rollback()
    try:
        thread, plan, run = lock_for_write(db, principal, clock=clock or principal._clock)
        item = _runtime_item(db, principal, item_id)
        if item.status != 'running':
            _conflict()
        key = 'read:' + _digest({'run_id': run.id, 'item_key': item.item_key})
        work = db.scalar(select(WorkItem).where(WorkItem.owner_id == principal.actor_id,
            WorkItem.store_id == principal.store_id, WorkItem.intent_key == key))
        if work is not None:
            if (work.session_id != principal.session_id or work.plan_id != principal.plan_id
                    or work.item_kind != 'read' or work.validated_intent != intent
                    or work.operation_id != intent['operation_id'] or work.status == 'uncertain'
                    or item.work_item_id not in {None, work.id}):
                _conflict()
        else:
            if item.work_item_id is not None:
                _conflict()
            # A matching object does not prove that a PlanStep is a query task.
            # Keep the authorized read's real origin without silently satisfying
            # an empty business completion condition. An explicit read-step
            # contract must establish any future report_query association.
            now = _runtime_now(principal, clock)
            work = WorkItem(id=str(uuid4()), owner_id=principal.actor_id, store_id=principal.store_id,
                session_id=principal.session_id, plan_id=principal.plan_id, step_id=None,
                origin_request_id=run.request_id or ('run:' + run.id), input_item_id=str(uuid4()),
                intent_version=1, item_kind='read', intent_key=key,
                operation_id=intent['operation_id'], validated_intent=deepcopy(intent), source_refs=[],
                status='planned', version=1, created_at=now, updated_at=now)
            db.add(work)
        item.work_item_id = work.id
        _finish_write(db, principal, clock)
    except Exception:
        db.rollback()
        raise


def _save_tool_result(db, principal, item_id, *, status, result_refs=(), error_code=None,
                      operation_seen=None, clock=None):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    from .assistant_runtime_schemas import BusinessObjectRef
    if status not in {'succeeded', 'failed', 'uncertain'}:
        raise ValueError('Invalid tool checkpoint status')
    refs = [BusinessObjectRef.model_validate(value).model_dump(mode='json') for value in result_refs]
    service.require_preparation_read_phase(db)
    db.rollback()
    try:
        thread, plan, run = lock_for_write(db, principal, clock=clock or principal._clock)
        item = _runtime_item(db, principal, item_id)
        if item.status != 'running':
            _conflict()
        item.status, item.error_code = status, error_code
        item.finished_at, item.result_refs = _runtime_now(principal, clock), refs
        if item.work_item_id:
            work = db.scalar(select(WorkItem).where(WorkItem.id == item.work_item_id))
            if (work is None or work.item_kind != 'read' or work.plan_id != principal.plan_id
                    or (work.owner_id, work.store_id, work.session_id) != (principal.actor_id, principal.store_id, principal.session_id)):
                _conflict()
            if status == 'succeeded':
                work.status, work.updated_at = 'settled', item.finished_at
                if not refs:
                    refs = [{'type': 'report_query', 'id': work.id}]
                    item.result_refs = refs
        if operation_seen is not None:
            thread.recent_operation_ids = [value for value in thread.recent_operation_ids or [] if value != operation_seen][-5:] + [operation_seen]
        db.flush()
        append_event(db, principal, 'tool.finished', {'run_item_id': item.id,
            'work_item_id': item.work_item_id, 'result_refs': refs}, clock=clock)
        _finish_write(db, principal, clock)
        return refs
    except Exception:
        db.rollback()
        raise


def _record_runtime_issue(db, principal, item_id, args, config, *, clock=None):
    import re
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    from .business_assistant_models import AssistantIssue
    service.require_preparation_read_phase(db)
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock or principal._clock)
        item = _runtime_item(db, principal, item_id)
        if item.status != 'running' or item.tool_name != 'record_issue':
            _conflict()
        clean = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[电话已隐藏]', service.safe_text(args.get('summary'), 1200))
        row = AssistantIssue(store_id=principal.store_id, session_id=principal.session_id, owner_id=principal.actor_id,
            category=args.get('category') if args.get('category') in service.ISSUE_CATEGORIES else 'system',
            summary=clean, operation_id=service.safe_text(args.get('operation_id', ''), 180),
            status_code=None, synthetic=config.synthetic, created_at=_runtime_now(principal, clock))
        db.add(row)
        item.status, item.finished_at, item.result_refs = 'succeeded', _runtime_now(principal, clock), []
        db.flush()
        view = service.issue_view(row)
        append_event(db, principal, 'tool.finished', {'run_item_id': item.id, 'work_item_id': None, 'result_refs': []}, clock=clock)
        _finish_write(db, principal, clock)
        return view
    except Exception:
        db.rollback()
        raise


def _pending_preparations(db, principal, item):
    data = _tool_data(item)
    thread, manifest, values = _owned_manifest(db, principal, principal.session_id, data['manifest_id'])
    if values['scope']['plan_id'] != principal.plan_id or values['scope']['step_id'] != data['step_id']:
        _conflict()
    if principal.plan_id:
        step = db.scalar(select(PlanStep).where(PlanStep.id == data['step_id'], PlanStep.plan_id == principal.plan_id))
        if step is None or step.intent_version != values['scope']['intent_version']:
            _conflict()
    pending, blocked = [], False
    for row in values['rows']:
        work = db.scalar(select(WorkItem).where(WorkItem.id == row['work_item_id'])) if row['work_item_id'] else None
        card = None
        if work:
            _same_scope(work, thread, principal)
            if (work.plan_id != values['scope']['plan_id'] or work.step_id != values['scope']['step_id']
                    or work.input_item_id != row['input_item_id'] or work.item_kind != 'prepare'):
                _conflict()
            card = _card(db, work, thread, principal)
        if (card.id if card else None) != row.get('proposal_id'):
            _conflict()
        state = _card_status(card) if card else row['outcome']
        if state in {'executing', 'uncertain', 'failed', 'cancelled', 'expired', 'needs_input'} or card is not None and state == 'pending' and card.questions:
            blocked = True
        elif card is None:
            if row.get('carry_forward') or work and work.status != 'planned':
                _conflict()
            if row['outcome'] != 'pending':
                _conflict()
            pending.append(deepcopy(row))
    return deepcopy(values), pending, blocked


def _row_attempts(db, principal, parent):
    data = _tool_data(parent)
    return {value['input_item_id']: item for item in _latest_attempts(db, principal)
        if item.kind == 'batch_row' and (value := _tool_data(item))['model_item_id'] == data['model_item_id']
        and value['call_id'] == data['call_id']}


def _row_resolution(input_id, value):
    if isinstance(value, service.ResolvedPreparation):
        return RowResolution(input_id, preparation=value)
    if type(value) is not dict:
        raise HTTPException(502, '准备结果不完整，请核对后重试')
    code = value.get('status', 200)
    if type(code) is not int:
        raise HTTPException(502, '准备结果不完整，请核对后重试')
    unchanged = type(value.get('data')) is dict and value['data'].get('unchanged') is True
    return RowResolution(input_id, outcome='pending' if code >= 500 else 'needs_input',
        reason_code='source_unavailable' if code >= 500 else 'no_preparation_required' if unchanged else 'employee_input',
        message='原查询暂不可用，此行完整保留待继续' if code >= 500 else
                '原资料已一致，无需生成卡片' if unchanged else '此行尚未准备，请核对原工具返回的缺项或候选')


def _save_preparations(db, principal, item_id, resolutions, evaluation, *, max_preparations=None, clock=None):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    from . import assistant_runtime_plans as plans
    service.require_preparation_read_phase(db)
    db.rollback()
    try:
        thread, plan, run = lock_for_write(db, principal, clock=clock or principal._clock)
        parent = _runtime_item(db, principal, item_id)
        if parent.status != 'running':
            _conflict()
        data = _tool_data(parent)
        before, pending, blocked = _pending_preparations(db, principal, parent)
        pending_ids = {row['input_item_id'] for row in pending}
        if blocked and any(row.preparation is not None for row in resolutions):
            _conflict()
        if any(row.input_item_id not in pending_ids for row in resolutions):
            _conflict()
        if principal.plan_id and resolutions:
            permissions = plans.consume_preparation_evaluation(db, principal, evaluation,
                step_ids=(data['step_id'],), manifest_ids={data['step_id']: data['manifest_id']}, clock=clock)
            allowed = permissions[data['step_id']]
            if allowed is None or any(row.input_item_id not in allowed for row in resolutions):
                _conflict()
        old_cards = {row['proposal_id'] for row in before['rows'] if row['proposal_id']}
        if resolutions:
            _prepare_rows(db, principal, principal.session_id, data['manifest_id'], resolutions,
                execution_authorized=True, max_preparations=max_preparations, partial=True)
        thread, manifest, values = _owned_manifest(db, principal, principal.session_id, data['manifest_id'])
        children = _row_attempts(db, principal, parent)
        summaries, all_refs, new_cards = [], [], []
        now = _runtime_now(principal, clock)
        for row in values['rows']:
            work = db.scalar(select(WorkItem).where(WorkItem.id == row['work_item_id'])) if row['work_item_id'] else None
            card = _card(db, work, thread, principal) if work else None
            state = _card_status(card) if card else row['outcome']
            status = ('uncertain' if state in {'uncertain', 'executing'} else
                      'failed' if state in {'failed', 'cancelled', 'expired', 'needs_input'} else
                      'pending' if card is None else 'succeeded')
            refs = plans._card_objects(card) if card else []
            for ref in refs:
                if ref not in all_refs:
                    all_refs.append(ref)
            target = children.get(row['input_item_id']) if children else parent
            if target is None:
                _conflict()
            # Completed attempts are immutable. The card's later lifecycle is
            # displayed from the card and never rewrites the preparation result.
            if target.status != 'succeeded':
                target.work_item_id = work.id if work else None
                target.proposal_id = card.id if card else None
                target.result_refs = refs
                if status == 'pending':
                    target.status, target.finished_at = 'pending' if children else 'running', None
                else:
                    target.status, target.finished_at = status, now
                    target.error_code = 'precondition_conflict' if status != 'succeeded' else None
                    db.flush()
                    if children:
                        append_event(db, principal, 'tool.finished', {'run_item_id': target.id,
                            'work_item_id': target.work_item_id, 'result_refs': refs}, clock=clock)
            summary = {key: deepcopy(row.get(key)) for key in ('input_item_id', 'position', 'work_item_id',
                'proposal_id', 'outcome', 'reason_code', 'message')}
            summary.update(proposal_status=_card_status(card) if card else None, item_status=status)
            if card:
                summary['proposal'] = service.proposal_view(card)
                if card.id not in old_cards:
                    new_cards.append((card.id, work.id))
            summaries.append(summary)
        statuses = {row['item_status'] for row in summaries}
        parent.status = ('uncertain' if 'uncertain' in statuses else 'running' if 'pending' in statuses
                         else 'failed' if 'failed' in statuses else 'succeeded')
        parent.finished_at = None if parent.status == 'running' else now
        parent.error_code = 'precondition_conflict' if parent.status in {'failed', 'uncertain'} else None
        parent.result_refs = all_refs
        if children:
            parent.work_item_id = parent.proposal_id = None
        plan_changed = False
        if plan and values != before:
            projection = plans.project_legacy_plan(db, principal, principal.session_id, plan)
            value = next(row for row in projection['steps'] if row['key'] == values['scope']['step_key'])
            step = db.scalar(select(PlanStep).where(PlanStep.id == data['step_id'], PlanStep.plan_id == plan.id))
            if value['runtime_status'] == 'completed':
                _conflict()  # Preparation cannot manufacture business completion.
            step.status, step.wait_reason, step.updated_at = value['runtime_status'], value['wait_reason'], now
            step.version += 1
            plan.version, thread.version = plan.version + 1, thread.version + 1
            plan.updated_at = thread.updated_at = now
            plan_changed = True
        db.flush()
        for card_id, work_id in new_cards:
            append_event(db, principal, 'proposal.prepared', {'proposal_id': card_id,
                'work_item_id': work_id, 'plan_id': principal.plan_id}, clock=clock)
        if plan_changed:
            append_event(db, principal, 'plan.updated', {'plan_id': plan.id}, clock=clock)
            plans._emit_plan_signal(db, plan)
        if parent.finished_at is not None:
            append_event(db, principal, 'tool.finished', {'run_item_id': parent.id,
                'work_item_id': parent.work_item_id, 'result_refs': all_refs}, clock=clock)
        result = {'status': 200, 'items': summaries, 'input_count': len(summaries),
            'prepared_or_reused': sum(row['proposal_id'] is not None for row in summaries),
            'new_preparations': len(new_cards), 'pending': 'pending' in statuses,
            'requires_employee_confirmation': True}
        from .assistant_runtime_queue import add_preparation_usage
        add_preparation_usage(db, principal, len(new_cards), clock=clock)
        _finish_write(db, principal, clock)
        return result
    except Exception:
        db.rollback()
        raise


async def _execute_preparation(db, principal, config, item_id, *, max_preparations=None, clock=None, client_factory=None):
    from .assistant_runtime_principal import revalidate_principal, request_for_principal
    from .assistant_runtime_registry import registry_for_config
    from . import assistant_runtime_plans as plans
    service.require_preparation_read_phase(db)
    item = _runtime_item(db, principal, item_id)
    data = _tool_data(item)
    values, pending, blocked = _pending_preparations(db, principal, item)
    children = _row_attempts(db, principal, item)
    child_ids = {key: child.id for key, child in children.items()}
    db.rollback()
    if blocked:
        return _save_preparations(db, principal, item_id, [], None, clock=clock)
    selected = pending if max_preparations is None else pending[:max_preparations]
    selected_ids = {row['input_item_id'] for row in selected}
    resolutions, details = [], {}
    single = {'prepare_operations': 'prepare_operation', 'prepare_business_batch': 'prepare_business_form'}.get(data['name'], data['name'])
    registry = registry_for_config(config)
    form = None
    if data['name'] == 'prepare_business_batch' and selected:
        from . import business_assistant_business_tools as business_tools
        if data['arguments']['form_ref'].startswith('case:'):
            raise HTTPException(409, '同一原单的动作不能当成独立批量；请按真实依赖逐项准备')
        request = request_for_principal(db, principal, client_factory=client_factory)
        form = await business_tools.inspect_form(db, request, principal, principal.session_id, config, data['arguments']['form_ref'])
        if form['kind'] == 'action':
            raise HTTPException(409, '同一原单的动作不能当成独立批量；请按真实依赖逐项准备')
    for row in selected:
        if row['input_item_id'] in child_ids:
            if _start_attempt(db, principal, child_ids[row['input_item_id']], clock=clock) is None:
                # Another valid checkpoint settled this row after our read.
                # Discard every detached resolution collected so far; do not
                # persist an obsolete vector or turn the parent into a failure.
                current = _runtime_item(db, principal, item_id)
                saved = _stored_tool_result(db, principal, current)
                rows = [{**value, 'item_status': 'uncertain' if value['proposal_status'] in {'executing', 'uncertain'}
                    else 'failed' if value['proposal_status'] in {'failed', 'cancelled', 'expired'}
                    else 'succeeded' if value['proposal_id'] else 'pending'}
                        for value in saved.get('rows', [])]
                revalidate_principal(db, principal, clock=clock)
                db.rollback()
                return {'status': 409, 'items': rows, 'input_count': len(rows),
                    'prepared_or_reused': sum(value['proposal_id'] is not None for value in rows),
                    'new_preparations': 0, 'pending': any(value['proposal_id'] is None for value in rows),
                    'recheck_required': True, 'requires_employee_confirmation': True}
        revalidate_principal(db, principal, clock=clock)
        request = request_for_principal(db, principal, client_factory=client_factory)
        try:
            args = registry.validate_arguments(single, row['input'])
            if form is not None:
                resolved = await business_tools.resolve_preparation(db, request, principal, principal.session_id, config, args, form=form)
            else:
                resolved = await registry.spec(single).handler(db, request, principal, principal.session_id,
                    args, config, resolve_only=True)
        except HTTPException as exc:
            revalidate_principal(db, principal, clock=clock)
            resolved = {'status': exc.status_code, 'error': service.safe_text(exc.detail, 600)}
        resolutions.append(_row_resolution(row['input_item_id'], resolved))
        if isinstance(resolved, dict):
            details[row['input_item_id']] = service.scrub(resolved)
    resolutions.extend(RowResolution(row['input_item_id'], outcome='pending', reason_code='preparation_budget',
        message='本次准备额度已达上限，此行完整保留待继续') for row in pending if row['input_item_id'] not in selected_ids)
    evaluation = None
    if principal.plan_id and resolutions:
        evaluation = await plans.evaluate_plan_conditions(db, principal,
            clock=clock or principal._clock, client_factory=client_factory)
    result = _save_preparations(db, principal, item_id, resolutions, evaluation,
        max_preparations=max_preparations, clock=clock)
    for row in result['items']:
        if row['input_item_id'] in details:
            row['resolution'] = details[row['input_item_id']]
    revalidate_principal(db, principal, clock=clock)
    return result


async def _execute_plan(db, principal, config, item_id, args, *, clock=None, client_factory=None):
    """One fixed Plan-save transaction; never a general callback escape hatch."""
    from . import assistant_runtime_plans as plans
    from .assistant_runtime_queue import lock_for_write, _version_cas, runtime_busy_token
    from .assistant_runtime_principal import revalidate_principal, request_for_principal, principal_for_run
    from .assistant_runtime_events import _append
    service.require_preparation_read_phase(db)
    request = request_for_principal(db, principal, client_factory=client_factory)
    resolved = await plans.resolve_plan(db, request, principal, principal.session_id, config, args,
        principal=principal, clock=clock)
    db.rollback()
    try:
        thread, old_plan, run = lock_for_write(db, principal, clock=clock or principal._clock)
        item = _runtime_item(db, principal, item_id)
        if item.status != 'running' or item.tool_name != 'save_work_plan':
            _conflict()
        if principal.plan_id is None:
            _may_bind_new_plan(db, principal)
        saved = plans.persist_plan(db, principal, principal.session_id, resolved, principal=principal, clock=clock)
        plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id == saved.plan_id))
        if (plan is None or (plan.owner_id, plan.store_id, plan.session_id) !=
                (principal.actor_id, principal.store_id, principal.session_id)
                or plan.engine_version != 2 or plan.status != 'active'
                or plan.version != saved.plan_version or plan.goal_version != saved.goal_version):
            _conflict()
        rebound = False
        if principal.plan_id is None:
            if (not saved.created or saved.goal_version != 1
                    or principal.auth_kind != 'login' or run.plan_id is not None or run.goal_version is not None
                    or plan.request_id != runtime_busy_token(run.id)
                    or thread.busy_token != runtime_busy_token(run.id)
                    or thread.busy_until is None or thread.busy_until <= _runtime_now(principal, clock)
                    or run.stop_requested):
                _conflict()
            _version_cas(db, run, {'plan_id': plan.id, 'goal_version': plan.goal_version})
            rebound = True
        elif plan.id != principal.plan_id or run.plan_id != plan.id:
            _conflict()
        elif saved.structure_changed:
            # Preserve the old immutable execution/grant scope. Only the next
            # authorized run may use the newly persisted goal version.
            if plan.goal_version <= principal.goal_version or not run.stop_requested:
                _conflict()
        elif plan.goal_version != principal.goal_version:
            _conflict()
        now = _runtime_now(principal, clock)
        item.status, item.finished_at, item.result_refs, item.error_code = 'succeeded', now, [], None
        db.flush()
        # The pending Run source may just have bound a new Plan, or the existing
        # Plan goal may have advanced. The ordinary old-principal content cap
        # cannot describe either. This fixed branch publishes exactly these two
        # typed references, after the same real Run CAS and before old-source
        # fresh authorization/commit; it accepts no caller-selected event type.
        if not saved.reused:
            _append(db, run, 'plan.updated', {'plan_id': plan.id}, now)
        _append(db, run, 'tool.finished', {'run_item_id': item.id, 'work_item_id': None, 'result_refs': []}, now)
        response = deepcopy(saved.response)
        stopped = bool(saved.stopped_self or run.stop_requested)
        db.flush()
        revalidate_principal(db, principal, clock=clock)
        service.commit(db)
    except Exception:
        db.rollback()
        raise
    if rebound:
        principal = principal_for_run(db, principal.run_id, lease_owner=principal.lease_owner,
            fence=principal.fence, clock=clock or principal._clock, read_session_factory=principal._read_session_factory)
    elif not stopped:
        revalidate_principal(db, principal, clock=clock)
    else:
        # Goal-change results expose only the save's minimal IDs/versions. No
        # original business data is read with this stopped worker afterwards.
        from .assistant_runtime_principal import revalidate_control_principal
        revalidate_control_principal(db, principal, clock=clock)
    return response, principal, stopped


async def execute_tools(db, principal, config, checkpoint_value, *, max_preparations=None,
                        clock=None, client_factory=None, boundary=None):
    """Run only complete, durable tool intents; never a confirmation POST.

    Each item has a committed running checkpoint before its read phase. Native
    GETs finish before acquiring the next write fence. A successful item is
    returned from owned references instead of being executed again. A new plan
    returns a freshly issued principal; a changed goal stops this old run.
    """
    from .assistant_runtime_principal import revalidate_principal, request_for_principal
    from .assistant_runtime_registry import registry_for_config
    from .assistant_runtime_objects import resolve_result
    if max_preparations is not None and (type(max_preparations) is not int or max_preparations < 0):
        raise HTTPException(422, '准备预算必须是非负整数')
    if boundary is not None and not callable(boundary):
        raise TypeError('Tool boundary must be a server-owned async callback')
    async def reached():
        if boundary is None:
            return False
        result = await boundary(principal)
        if type(result) is not bool:
            raise TypeError('Tool boundary must return an explicit boolean')
        return result
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    _runtime_scope(db, principal)
    db.rollback()
    _, pairs = _checkpoint_items(db, principal, config, checkpoint_value)
    ordered = [(call, item.id) for call, item in pairs]
    db.rollback()
    messages, needed, used = [], False, 0
    for call, original_id in ordered:
        revalidate_principal(db, principal, clock=clock)
        item = _runtime_item(db, principal, original_id)
        if item.status in {'succeeded', 'uncertain', 'skipped'} or item.status == 'failed' and call.kind != 'read':
            result = _stored_tool_result(db, principal, item)
            messages.append(_message(call.id, result))
            needed = needed or item.status != 'succeeded'
            db.rollback()
            if await reached():
                return ToolExecution(principal, tuple(messages), needed, True, used)
            continue
        item_id = _start_attempt(db, principal, item.id, retry_read=call.kind == 'read', clock=clock)
        if item_id is None:
            current = _runtime_item(db, principal, original_id)
            messages.append(_message(call.id, _stored_tool_result(db, principal, current)))
            db.rollback()
            if await reached():
                return ToolExecution(principal, tuple(messages), needed, True, used)
            continue
        try:
            if call.kind == 'read':
                intent = _read_intent(call.name, call.arguments)
                if intent is not None:
                    _accept_read_work(db, principal, item_id, intent, clock=clock)
                request = request_for_principal(db, principal, client_factory=client_factory)
                result = await runtime_read_tool(db, request, principal, principal.session_id,
                    call.name, call.arguments, config, principal=principal)
                code = result.get('status', 200) if type(result) is dict else 502
                if type(code) is not int:
                    raise HTTPException(502, '原查询结果不完整')
                operation = intent['operation_id'] if intent else 'GET /api/flow/cases/{case_id}' if call.name == 'get_case' else None
                refs = []
                if code < 400 and operation:
                    refs = [value.model_dump(mode='json') for value in resolve_result(operation, result).object_refs]
                _save_tool_result(db, principal, item_id, status='succeeded' if code < 400 else 'failed',
                    result_refs=refs, error_code=None if code < 400 else _error_code(code),
                    operation_seen=result.get('id') if call.name == 'inspect_operation' else None, clock=clock)
                needed = needed or code >= 400
            elif call.kind == 'prepare':
                result = await _execute_preparation(db, principal, config, item_id,
                    max_preparations=None if max_preparations is None else max(0, max_preparations - used),
                    clock=clock, client_factory=client_factory)
                used += result['new_preparations']
                needed = needed or any(row['item_status'] in {'failed', 'uncertain'} for row in result['items'])
                if result['pending'] or result.get('recheck_required'):
                    messages.append(_message(call.id, result))
                    return ToolExecution(principal, tuple(messages), needed, True, used)
            elif call.name == 'record_issue':
                result = _record_runtime_issue(db, principal, item_id, call.arguments, config, clock=clock)
            elif call.name == 'save_work_plan':
                result, principal, stopped = await _execute_plan(db, principal, config, item_id, call.arguments,
                    clock=clock, client_factory=client_factory)
                if stopped:
                    messages.append(_message(call.id, result))
                    return ToolExecution(principal, tuple(messages), needed, True, used)
            else:
                raise HTTPException(422, '没有已评审的Runtime工具执行路径')
        except HTTPException as exc:
            # Loss of the run's authority/fence must escape to control cleanup;
            # never commit a late failure or disclose the old response.
            service.require_preparation_read_phase(db)
            revalidate_principal(db, principal, clock=clock)
            _save_tool_result(db, principal, item_id, status='failed', error_code=_error_code(exc.status_code), clock=clock)
            result = {'status': exc.status_code, 'error': service.safe_text(exc.detail, 600), 'prepared': False}
            needed = True
        messages.append(_message(call.id, result))
        if await reached():
            return ToolExecution(principal, tuple(messages), needed, True, used)
    revalidate_principal(db, principal, clock=clock)
    return ToolExecution(principal, tuple(messages), needed, False, used)


@dataclass(frozen=True)
class RunExecution:
    """An execution outcome, never evidence that the business goal completed."""
    run_id: str
    status: str
    reason: str | None = None
    needs_input: bool = False
    reply: str | None = field(default=None, repr=False)


class _RunHeartbeat:
    """One independently bound short Session; never borrow the work Session.

    Synchronous SQL runs only at an event-loop boundary. It cannot interleave
    with this worker's synchronous write transactions. A single-connection pool
    cannot provide the independent transaction this contract requires.
    """
    def __init__(self, db, principal, clock):
        from sqlalchemy.engine import Engine
        from sqlalchemy.pool import StaticPool, SingletonThreadPool
        bind = db.get_bind()
        if not isinstance(bind, Engine) or isinstance(bind.pool, (StaticPool, SingletonThreadPool)):
            raise HTTPException(409, '后台心跳需要独立的同库连接，不能复用内存库的事务连接')
        self.bind, self.principal, self.clock = bind, principal, clock
        self.task = None
        self.failed = asyncio.Event()
        self.failure = None

    async def _loop(self):
        from sqlalchemy.orm import Session
        from .assistant_runtime_queue import HEARTBEAT_SECONDS, heartbeat
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                with Session(bind=self.bind, autoflush=False, expire_on_commit=False) as db:
                    heartbeat(db, self.principal, clock=self.clock)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failure = exc
            self.failed.set()

    def start(self):
        self.task = asyncio.create_task(self._loop())

    async def wait(self, awaitable):
        """Abort in-flight reads/model work as soon as the lease guard fails."""
        if self.failure is not None:
            from inspect import iscoroutine
            if iscoroutine(awaitable):
                awaitable.close()
            raise self.failure
        task = asyncio.create_task(awaitable)
        failed = asyncio.create_task(self.failed.wait())
        try:
            done, _ = await asyncio.wait((task, failed), return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                return await task
            if failed in done:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise self.failure
            return await task
        finally:
            failed.cancel()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, failed, return_exceptions=True)

    def stop(self):
        if self.task is not None:
            self.task.cancel()

    async def close(self):
        if self.task is not None:
            self.stop()
            await asyncio.gather(self.task, return_exceptions=True)


def _run_snapshot(db, principal, *, clock=None):
    from .assistant_runtime_principal import revalidate_principal
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    _runtime_scope(db, principal)
    db.rollback()
    row = db.scalar(select(Run).where(Run.id == principal.run_id,
        Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
        Run.session_id == principal.session_id).execution_options(populate_existing=True))
    if row is None:
        _conflict()
    value = {key: deepcopy(getattr(row, key)) for key in
             ('id', 'trigger_kind', 'request_id', 'started_at', 'usage', 'plan_id', 'goal_version')}
    thinking = False
    if row.trigger_kind == 'user':
        message = db.scalar(select(AssistantMessage).where(AssistantMessage.session_id == row.session_id,
            AssistantMessage.store_id == row.store_id, AssistantMessage.request_id == row.request_id,
            AssistantMessage.role == 'user'))
        if message is None:
            _conflict()
        thinking = bool(message.thinking)
    value['thinking'] = thinking
    revalidate_principal(db, principal, clock=clock)
    db.rollback()
    return value


def _actual_outcomes(db, principal, *, clock=None):
    """Count this Run's real cards and every accepted row, not model prose."""
    from .assistant_runtime_principal import revalidate_principal
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    _runtime_scope(db, principal)
    db.rollback()
    items = list(db.scalars(select(RunItem).where(RunItem.run_id == principal.run_id)
                           .execution_options(populate_existing=True)))
    work_ids = {item.work_item_id for item in items if item.work_item_id}
    rows = []
    manifests = {item.id: item for item in items if item.tool_name == _MANIFEST_TOOL}
    for item in items:
        if item.kind in {'tool', 'batch_row'} and item.tool_name != _MANIFEST_TOOL:
            reference = _tool_data(item)['manifest_id']
            if reference is not None and reference not in manifests:
                linked = db.scalar(select(RunItem).where(RunItem.id == reference)
                                   .execution_options(populate_existing=True))
                if linked is None:
                    _conflict()
                manifests[reference] = linked
    for item in manifests.values():
        if item.tool_name == _MANIFEST_TOOL:
            value = _manifest_data(item)
            scope = value['scope']
            if (scope['owner_id'], scope['store_id'], scope['session_id']) != (
                    principal.actor_id, principal.store_id, principal.session_id):
                _conflict()
            rows.extend(value['rows'])
            work_ids.update(row['work_item_id'] for row in value['rows'] if row['work_item_id'])
    works = list(db.scalars(select(WorkItem).where(WorkItem.id.in_(work_ids),
        WorkItem.owner_id == principal.actor_id, WorkItem.store_id == principal.store_id,
        WorkItem.session_id == principal.session_id).execution_options(populate_existing=True)))
    if len(works) != len(work_ids):
        _conflict()
    cards = list(db.scalars(select(AssistantProposal).where(AssistantProposal.source_work_item_id.in_(work_ids),
        AssistantProposal.owner_id == principal.actor_id, AssistantProposal.store_id == principal.store_id,
        AssistantProposal.session_id == principal.session_id, AssistantProposal.owner_role == principal.role,
        AssistantProposal.access_version == principal.access_version).execution_options(populate_existing=True)))
    by_work = {card.source_work_item_id: card for card in cards}
    if len(by_work) != len(cards):
        _conflict()
    statuses = [_card_status(card) for card in cards]
    pending_rows = sum(row.get('proposal_id') is None and row['outcome'] == 'pending' for row in rows)
    blocked_rows = sum(row['outcome'] in {'needs_input', 'failed', 'uncertain'} for row in rows)
    value = {'cards': len(cards), 'pending_cards': statuses.count('pending'),
        'succeeded_cards': statuses.count('succeeded'),
        'uncertain_cards': sum(status in {'executing', 'uncertain'} for status in statuses),
        'unusable_cards': sum(status in {'failed', 'cancelled', 'expired'} for status in statuses),
        'pending_rows': pending_rows, 'blocked_rows': blocked_rows,
        'running_items': sum(item.status == 'running' for item in items),
        'questions': any(card.status == 'pending' and card.questions for card in cards),
        'row_reasons': sorted({row['reason_code'] for row in rows if row.get('reason_code')})}
    revalidate_principal(db, principal, clock=clock)
    db.rollback()
    return value


def _outcome_text(facts, reason):
    text = '本次已保留 %d 张实际确认卡，其中 %d 张待员工确认。' % (facts['cards'], facts['pending_cards'])
    if facts['pending_rows']:
        text += '原完整清单另有 %d 行尚未准备，输入已保留，不能视为全部完成。' % facts['pending_rows']
    if facts['uncertain_cards']:
        text += '有 %d 张卡的业务结果仍需到原页面核对，本次没有重放提交。' % facts['uncertain_cards']
    if facts['blocked_rows'] or facts['questions'] or facts['unusable_cards']:
        text += '仍有缺项、冲突或失效卡，请核对原卡及原业务记录。'
    messages = {
        'model_round_budget': '本次模型轮数已达到上限。',
        'time_budget': '本次执行已达到时间上限。',
        'tool_budget': '本次工具调用已达到上限。',
        'preparation_budget': '本次准备额度或待确认卡容量已满。',
        'context_budget_exceeded': '完整输入超出当前配置的上下文容量，需要明确缩小办理范围。',
        'source_message_missing': '缺少可核对的原始输入，请在此事项补充明确说明。',
        'recheck_required': '执行来源已变化，需要重新核对后继续。',
        'runtime_unavailable': '助手本次未取得完整结果，请核对已保留成果后继续。',
        'configuration_unavailable': '业务助手尚未连接，请联系管理员配置。',
        'needs_input': '请补充或核对原卡所列资料。',
    }
    return messages.get(reason, '本次执行已结束。') + text


_FOLLOWUP_OUTCOME_REASONS = frozenset({
    'model_round_budget', 'time_budget', 'tool_budget', 'preparation_budget',
    'context_budget_exceeded', 'source_message_missing', 'recheck_required',
    'runtime_unavailable', 'configuration_unavailable', 'needs_input',
})


def _finish_run(db, principal, text, *, status='succeeded', reason=None, needs_input=False, thinking=False, clock=None):
    """The only final reply path: original unique key plus terminal in one TX."""
    from .assistant_runtime_events import _safe_display, progress
    from .assistant_runtime_queue import release
    safe = _safe_display(text, final=True)
    service.require_preparation_read_phase(db)
    db.rollback()

    def save_reply(write_db, current, run_id):
        run = write_db.scalar(select(Run).where(Run.id == run_id,
            Run.owner_id == current.actor_id, Run.store_id == current.store_id,
            Run.session_id == current.session_id).execution_options(populate_existing=True))
        if run is None or run.status != ('failed' if status == 'retry' else status):
            _conflict()
        # A scheduler reads this fixed server outcome, never the assistant's
        # prose, to decide whether explicit employee input is still required.
        # Retries which remain queued do not invoke this terminal callback.
        outcome = {'schema_version': 1, 'needs_input': bool(needs_input),
                   'reason': reason if reason in _FOLLOWUP_OUTCOME_REASONS else
                             None if reason is None else 'runtime_unavailable'}
        if type(run.usage) is not dict:
            _conflict('执行资源记录不完整，不能保存收尾结果')
        previous = run.usage.get('followup_outcome_v1')
        if previous is not None and previous != outcome:
            _conflict('执行收尾结果已经存在，不能覆盖')
        run.usage = {**deepcopy(run.usage), 'followup_outcome_v1': outcome}
        key = run.request_id + ':reply' if run.trigger_kind == 'user' else 'run:' + run.id + ':reply'
        existing = write_db.scalar(select(AssistantMessage).where(AssistantMessage.session_id == run.session_id,
            AssistantMessage.request_id == key))
        if existing is not None:
            if (existing.store_id != current.store_id or existing.role != 'assistant'
                    or existing.content != safe or existing.thinking is not thinking):
                _conflict()
        else:
            write_db.add(AssistantMessage(store_id=current.store_id, session_id=current.session_id,
                request_id=key, role='assistant', content=safe, thinking=thinking))
        progress(write_db, current, safe, final=True, clock=clock)

    code = None if status == 'succeeded' else ('runtime_unavailable' if reason == 'runtime_unavailable' else 'precondition_conflict')
    handle = release(db, principal, outcome=status, error_code=code,
        clock=clock or principal._clock, before_finish=save_reply)
    if handle.status == 'queued':
        return RunExecution(handle.id, handle.status, reason)
    # No old content is returned after commit if its original authority vanished.
    # The Run is terminal, so the ordinary running-principal guard no longer fits.
    from .assistant_runtime_queue import _fresh_source
    try:
        current = _fresh_source(db, principal.run_id, clock=clock or principal._clock,
                                read_session_factory=principal._read_session_factory)
        if (current['owner_id'], current['store_id'], current['session_id'], current['role'],
                current['access_version'], current['plan_id'], current['goal_version']) != (
                principal.actor_id, principal.store_id, principal.session_id, principal.role,
                principal.access_version, principal.plan_id, principal.goal_version):
            raise HTTPException(403, '原执行身份已变化')
    except Exception as exc:
        # No private result or original exception content is returned after a
        # post-commit failure; the caller must not try to cancel this terminal Run.
        error = HTTPException(403 if isinstance(exc, HTTPException) and exc.status_code < 500 else 503,
            '执行结果已保存，当前无法核对查看权限，请重新登录后查看可访问的事项')
        error.runtime_terminal_saved = True
        raise error from None
    return RunExecution(handle.id, handle.status, reason, needs_input, safe)


def _progress_run(db, principal, text, *, clock=None):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import progress
    service.require_preparation_read_phase(db)
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock or principal._clock)
        progress(db, principal, text, clock=clock)
        _finish_write(db, principal, clock)
    except Exception:
        db.rollback()
        raise


class _LoopBudget(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _cancel_fragment(db, principal, *, clock, error_code='precondition_conflict'):
    from .assistant_runtime_queue import release
    service.require_preparation_read_phase(db)
    db.rollback()
    handle = release(db, principal, outcome='cancelled', error_code=error_code, clock=clock)
    return RunExecution(handle.id, handle.status, 'stopped')


async def _refresh_step_progress(db, principal, *, clock, client_factory):
    if principal.plan_id is None:
        return
    from .assistant_runtime_plans import evaluate_plan_conditions, apply_condition_results
    from .assistant_runtime_events import append_plan_updated
    service.require_preparation_read_phase(db)
    db.rollback()
    evaluation = await evaluate_plan_conditions(db, principal, clock=clock, client_factory=client_factory)
    db.rollback()
    apply_condition_results(db, principal, evaluation, clock=clock,
        on_plan_updated=lambda tx, p, plan_id, version: append_plan_updated(tx, p, plan_id, version, clock=clock))
    # A completed Step is evidence-backed. Ending its Plan/Grant belongs to the
    # follow-up scheduler, never to the fact that this Run returned an answer.


async def run_once(db, principal, config=None, *, stream=True, clock=None,
                   client_factory=None, context_char_budget=None, max_preparations=None):
    """Drive exactly one already claimed Run using durable, bounded checkpoints.

    Recovery starts a fresh provider chain from authorized context. Only the
    assistant/tool pairs generated in this invocation remain in memory, with
    optional reasoning used solely for that current provider chain. A worker
    must claim before calling; this API neither creates a worker nor enables a
    feature flag. All native GETs precede their short fenced write transactions.
    """
    from .assistant_runtime_principal import revalidate_principal
    from .assistant_runtime_provider import ModelProtocolError, call_model
    from .assistant_runtime_registry import registry_for_config
    from . import assistant_runtime_queue as queue
    from .assistant_runtime_events import _safe_display
    if type(stream) is not bool or max_preparations is not None and (
            type(max_preparations) is not int or max_preparations < 0):
        raise HTTPException(422, '执行配置不正确')
    if context_char_budget is not None and (type(context_char_budget) is not int or context_char_budget < 1):
        raise HTTPException(422, '上下文预算不正确')
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    if principal.run_id is None:
        raise HTTPException(409, '必须先领取真实执行租约')
    clock = clock or principal._clock
    _runtime_scope(db, principal)
    db.rollback()
    claimed = db.scalar(select(Run).where(Run.id == principal.run_id,
        Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
        Run.session_id == principal.session_id).execution_options(populate_existing=True))
    if claimed is not None and claimed.trigger_key.startswith('mcp:'):
        from .assistant_runtime_mcp import is_mcp_run, execute_mcp
        if not is_mcp_run(claimed):
            raise HTTPException(409, '原本地工具请求来源不正确，不能按模型请求执行')
        db.rollback()
        return await execute_mcp(db, principal, config, clock=clock, client_factory=client_factory)
    db.rollback()
    source = _run_snapshot(db, principal, clock=clock)
    thinking = source['thinking']
    try:
        config = service.load_config() if config is None else config
        if not config.enabled or not config.api_key:
            raise HTTPException(503, '业务助手尚未连接，请联系管理员配置')
        if config.tool_profile != 'business_v1':
            raise HTTPException(503, '持续执行需要已配置的业务助手工具目录')
    except HTTPException:
        facts = _actual_outcomes(db, principal, clock=clock)
        _finish_run(db, principal, _outcome_text(facts, 'configuration_unavailable'), status='failed',
            reason='configuration_unavailable', needs_input=True, thinking=thinking, clock=clock)
        raise
    max_rounds = max(4, min(40, config.max_rounds))
    turn_seconds = max(30, min(600, config.turn_timeout_seconds))
    limits = {'max_rounds': max_rounds, 'turn_timeout_seconds': turn_seconds,
              'call_budget': max(200, max_rounds * service.HARD_TOOLS), 'max_preparations': max_preparations}
    budget = queue.configure_budget(db, principal, **limits, clock=clock)
    heartbeat = _RunHeartbeat(db, principal, clock)
    heartbeat.start()
    chain, instructions = [], []
    needed = False
    yielded = None

    def remaining_preparations():
        snapshot = queue.budget_snapshot(db, principal, clock=clock)
        return None if max_preparations is None else max(0, max_preparations - snapshot.prepared_count)

    async def boundary(current):
        nonlocal principal, yielded
        principal = current
        heartbeat.principal = current
        revalidate_principal(db, principal, clock=clock)
        snapshot = queue.budget_snapshot(db, principal, clock=clock)
        if snapshot.remaining_seconds <= 0:
            raise _LoopBudget('time_budget')
        service.require_preparation_read_phase(db)
        db.rollback()
        yielded = queue.yield_to_user(db, principal, clock=clock)
        if yielded is not None:
            heartbeat.stop()
        return yielded is not None

    def finish_reason(reason, *, failed=True):
        facts = _actual_outcomes(db, principal, clock=clock)
        return _finish_run(db, principal, _outcome_text(facts, reason),
            status='failed' if failed else 'succeeded', reason=reason,
            needs_input=True, thinking=thinking, clock=clock)

    def stopped_execution():
        if yielded is not None:
            return RunExecution(yielded.id, yielded.status, 'yielded_to_user')
        try:
            revalidate_principal(db, principal, clock=clock)
        except HTTPException as authority_error:
            return _cancel_fragment(db, principal, clock=clock,
                error_code='permission_denied' if authority_error.status_code in {401, 403} else 'precondition_conflict')
        facts = _actual_outcomes(db, principal, clock=clock)
        reason = ('preparation_budget' if facts['pending_rows'] and
            ('preparation_budget' in facts['row_reasons'] or remaining_preparations() == 0)
            else 'recheck_required' if facts['pending_rows'] or facts['running_items'] else 'needs_input')
        return _finish_run(db, principal, _outcome_text(facts, reason),
            status='failed' if facts['pending_rows'] or facts['running_items'] else 'succeeded',
            reason=reason, needs_input=True, thinking=thinking, clock=clock)

    try:
        if budget.remaining_seconds <= 0:
            raise _LoopBudget('time_budget')
        async with asyncio.timeout(budget.remaining_seconds):
            recovery = await heartbeat.wait(recover_items(db, principal, config, clock=clock,
                                                          client_factory=client_factory))
            # These values are observations, not a provider protocol. In
            # particular, never append recovery.tool_messages as orphan tools.
            needed = recovery.needs_input
            for saved in recovery.checkpoints:
                result = await heartbeat.wait(execute_tools(db, principal, config, saved,
                    max_preparations=remaining_preparations(), clock=clock,
                    client_factory=client_factory, boundary=boundary))
                principal = result.principal
                heartbeat.principal = principal
                needed = needed or result.needs_input
                if result.stop:
                    return stopped_execution()
            if await boundary(principal):
                return stopped_execution()
            facts = _actual_outcomes(db, principal, clock=clock)
            if facts['uncertain_cards']:
                return finish_reason('needs_input', failed=False)
            while True:
                if heartbeat.failure is not None:
                    raise heartbeat.failure
                if await boundary(principal):
                    return stopped_execution()
                await heartbeat.wait(_refresh_step_progress(db, principal, clock=clock, client_factory=client_factory))
                context = await heartbeat.wait(service.build_runtime_context(db, principal, config,
                    thinking=thinking, tool_messages=tuple(chain), client_factory=client_factory,
                    clock=clock, context_char_budget=context_char_budget))
                if context.status != 'ready':
                    return finish_reason(context.reason or 'needs_input', failed=context.reason == 'context_budget_exceeded')
                messages = [deepcopy(message) for message in context.messages]
                snapshot = queue.budget_snapshot(db, principal, clock=clock)
                wrapped = snapshot.round_no >= max_rounds - 2
                if wrapped:
                    messages.append({'role': 'system', 'content':
                        '请按本轮实际工具结果收尾，集中列出缺项和依赖；不要再调用工具，不要编造办理结果。'})
                messages.extend({'role': 'system', 'content': text} for text in instructions)
                if context_char_budget is not None and len(json.dumps(messages, ensure_ascii=False,
                        separators=(',', ':'), allow_nan=False)) > context_char_budget:
                    return finish_reason('context_budget_exceeded')
                reservation = queue.reserve_model_round(db, principal, **limits, clock=clock)
                if reservation.exhausted_reason:
                    raise _LoopBudget(reservation.exhausted_reason)
                round_no = reservation.round_no
                _progress_run(db, principal, '正在核对资料并整理下一步。', clock=clock)
                last_phase = None

                async def before_request():
                    revalidate_principal(db, principal, clock=clock)
                    current = queue.budget_snapshot(db, principal, clock=clock)
                    if current.remaining_seconds <= 0:
                        raise _LoopBudget('time_budget')
                    # Round reservation includes this request; do not reject the
                    # final permitted round merely because the counter is full.
                    service.require_preparation_read_phase(db)
                    db.rollback()

                async def emit(event, data):
                    nonlocal last_phase
                    if event != 'status' or type(data) is not dict:
                        return  # Raw deltas/reasoning never become claimed facts.
                    phase = data.get('phase')
                    labels = {'thinking': '正在核对资料并整理下一步。',
                              'responding': '正在整理业务说明。', 'tool': '正在核对原业务资料。'}
                    if phase in labels and phase != last_phase:
                        revalidate_principal(db, principal, clock=clock)
                        _progress_run(db, principal, labels[phase], clock=clock)
                        last_phase = phase

                try:
                    answer = await heartbeat.wait(call_model(config, messages, thinking=thinking,
                        stream=stream, emit=emit if stream else None,
                        background=principal.auth_kind == 'grant', before_request=before_request))
                except BaseException as exc:
                    # Never store exception text, provider content or reasoning.
                    # A reserved but crashed/unreported request remains unknown.
                    db.rollback()
                    try:
                        revalidate_principal(db, principal, clock=clock)
                        queue.finish_model_round(db, principal, round_no, getattr(exc, 'runtime_usage', None), clock=clock)
                    except Exception:
                        if isinstance(exc, asyncio.CancelledError):
                            raise exc from None
                        raise
                    if isinstance(exc, service.ModelOutputTruncated):
                        if not wrapped and queue.mark_loop_flag(db, principal, 'truncation', clock=clock):
                            instructions.append('上一段输出被服务商截断，整个片段的工具均未执行。已有完整成果保留；'
                                '请用完整工具重新表达剩余原请求，不能漏行，查询不生成写入卡。')
                            continue
                    raise
                budget = queue.finish_model_round(db, principal, round_no, answer.usage, clock=clock)
                reply = answer.message
                calls = reply.get('tool_calls')
                calls = [] if calls is None else calls
                registry_for_config(config).validate_calls(calls)
                if budget.tool_count > limits['call_budget']:
                    raise _LoopBudget('tool_budget')
                text = _safe_display(reply.get('content') or '', final=True)
                if not calls:
                    facts = _actual_outcomes(db, principal, clock=clock)
                    if service.claimed_actions(text) and facts['cards'] == 0:
                        if queue.mark_loop_flag(db, principal, 'correction', clock=clock):
                            previous = {'role': 'assistant', 'content': text or None}
                            if thinking:
                                previous['reasoning_content'] = reply.get('reasoning_content', '')
                            chain.append(previous)
                            instructions.append('事实核对：本次执行实际确认卡数量为0。请纠正有关卡片的表述，'
                                '不能为使一句话成立而新增业务。查询直接说明，只有员工原明确委托且事实确定才可准备卡。')
                            continue
                        text = '本次没有实际生成确认卡；此前关于卡片已准备的表述未得到记录支持。请核对原请求及资料。'
                        needed = True
                    if facts['pending_rows'] or facts['running_items']:
                        return finish_reason('recheck_required')
                    if facts['cards']:
                        count_text = '本次实际确认卡：%d 张，其中 %d 张待员工确认。' % (facts['cards'], facts['pending_cards'])
                        candidate = (text + '\n\n' if text else '') + count_text
                        text = candidate if len(candidate) <= service.MODEL_TEXT_CHARS else (
                            '这次说明过长，未能完整展示；请指定要查看的部分。' + _outcome_text(facts, 'needs_input'))
                        needed = needed or len(candidate) > service.MODEL_TEXT_CHARS
                    needed = needed or not text or facts['questions'] or facts['blocked_rows'] > 0 or facts['unusable_cards'] > 0
                    return _finish_run(db, principal, text or '请补充要办理的业务内容。',
                        reason='needs_input' if needed else None, needs_input=needed, thinking=thinking, clock=clock)
                accepted = await heartbeat.wait(checkpoint(db, principal, config, reply,
                    model_key='round:' + str(round_no), clock=clock, client_factory=client_factory))
                result = await heartbeat.wait(execute_tools(db, principal, config, accepted,
                    max_preparations=remaining_preparations(), clock=clock,
                    client_factory=client_factory, boundary=boundary))
                principal = result.principal
                heartbeat.principal = principal
                needed = needed or result.needs_input
                if result.stop:
                    return stopped_execution()
                # Only a whole current assistant/tool pair enters the next model
                # request. A yielded or partial execution never reaches here.
                if len(result.tool_messages) != len(calls):
                    _conflict()
                current = {'role': 'assistant', 'content': text or None, 'tool_calls': deepcopy(calls)}
                if thinking:
                    current['reasoning_content'] = reply.get('reasoning_content', '')
                chain.append(current)
                chain.extend(deepcopy(result.tool_messages))
    except (TimeoutError, _LoopBudget) as exc:
        db.rollback()
        return finish_reason(exc.reason if isinstance(exc, _LoopBudget) else 'time_budget')
    except asyncio.CancelledError:
        db.rollback()
        # Shutdown does not erase accepted work or turn a partial model reply
        # into success. The normal safe-retry classifier decides any requeue.
        try:
            revalidate_principal(db, principal, clock=clock)
            facts = _actual_outcomes(db, principal, clock=clock)
            _finish_run(db, principal, _outcome_text(facts, 'runtime_unavailable'), status='retry',
                reason='runtime_unavailable', needs_input=True, thinking=thinking, clock=clock)
        except Exception:
            db.rollback()  # Lost fence: the database recovery owner must decide.
        raise
    except HTTPException as exc:
        db.rollback()
        if getattr(exc, 'runtime_terminal_saved', False):
            raise
        try:
            revalidate_principal(db, principal, clock=clock)
        except HTTPException as authority_error:
            # This path can only close its own valid lease. A lost lease raises
            # without clearing another worker's busy token or returning data.
            return _cancel_fragment(db, principal, clock=clock,
                error_code='permission_denied' if authority_error.status_code in {401, 403} else 'precondition_conflict')
        if isinstance(exc, ModelProtocolError):
            return finish_reason('runtime_unavailable')
        if exc.status_code >= 500:
            facts = _actual_outcomes(db, principal, clock=clock)
            return _finish_run(db, principal, _outcome_text(facts, 'runtime_unavailable'), status='retry',
                reason='runtime_unavailable', needs_input=True, thinking=thinking, clock=clock)
        return finish_reason('needs_input')
    except Exception:
        db.rollback()
        try:
            revalidate_principal(db, principal, clock=clock)
        except HTTPException as authority_error:
            return _cancel_fragment(db, principal, clock=clock,
                error_code='permission_denied' if authority_error.status_code in {401, 403} else 'precondition_conflict')
        # No automatic replay on programming/shape errors. If the database or
        # lease is unavailable this guarded save raises and recovery owns it.
        return finish_reason('runtime_unavailable')
    finally:
        await heartbeat.close()
        # No uncommitted assistant fragment may leak into a caller's later work.
        db.rollback()
