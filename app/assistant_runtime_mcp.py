"""Fixed local MCP tools, persisted as tools rather than model messages.

Only the original employee login can enqueue this source. All original field
and business permission validation remains in the shared tool handlers. This
module owns no business POST, model call, followup grant or private payload log.
"""
from copy import deepcopy
from dataclasses import replace
import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select

from . import business_assistant_service as service
from .assistant_runtime_models import Run, RunItem, WorkItem
from .business_assistant_models import AssistantIssue, AssistantProposal, AssistantWorkPlan, AssistantSession


_PARENT = 'mcp:call'
_BATCH = {'prepare_operations', 'prepare_business_batch'}
_ROW_KEYS = {'id', 'position', 'input', 'outcome'}


def _conflict():
    raise HTTPException(409, '原工具请求或成果来源已变化，请核对原请求')


def is_mcp_run(run):
    """Recognize only the reserved source; callers reject malformed mcp: runs."""
    return (isinstance(run, Run) and type(run.request_id) is str
        and re.fullmatch(r'[A-Za-z0-9_-]{16,80}', run.request_id) is not None
        and run.trigger_key == f'mcp:{run.session_id}:{run.request_id}'
        and run.trigger_kind == 'manual' and run.auth_kind == 'login'
        and run.plan_id is None and run.goal_version is None and run.grant_id is None
        and run.entry_context is None and bool(run.login_session_ref))


def _config(config=None):
    # The tool catalogue and synthetic diagnostic marker do not require a model.
    return replace(service.load_config() if config is None else config, tool_profile='business_v1')


def _rows(name, arguments):
    from .assistant_runtime_registry import _registry_for_profile
    from .assistant_runtime_runner import _call_rows
    return _call_rows(name, arguments) if _registry_for_profile('business_v1').spec(name).kind == 'prepare' else []


def _digest(name, arguments):
    from .assistant_runtime_queue import _digest as digest
    return digest({'schema_version': 1, 'tool_profile': 'business_v1',
                   'name': name, 'arguments': arguments})


def create_request_item(db, run, name, args):
    """Called only by the real-login enqueue transaction; never commits."""
    from .assistant_runtime_registry import _registry_for_profile
    if not is_mcp_run(run):
        _conflict()
    canonical = _registry_for_profile('business_v1').validate_arguments(name, args)
    if canonical != args or service.scrub(args) != args or run.request_digest != _digest(name, args):
        _conflict()
    rows = [{'id': str(uuid4()), 'position': i, 'input': value, 'outcome': None}
            for i, value in enumerate(_rows(name, args), 1)]
    parent = RunItem(id=str(uuid4()), run_id=run.id, kind='tool', item_key=_PARENT,
        attempt_no=1, tool_name=name, status='pending', result_refs=[],
        validated_arguments={'schema_version': 1, 'source': 'mcp_tool',
            'name': name, 'arguments': deepcopy(args), 'rows': rows, 'outcome': None})
    db.add(parent)
    for row in rows:
        db.add(RunItem(id=str(uuid4()), run_id=run.id, kind='batch_row',
            item_key='mcp:row:' + row['id'], attempt_no=1, tool_name=name,
            status='pending', result_refs=[], validated_arguments={
                'schema_version': 1, 'source': 'mcp_row', 'parent_id': parent.id, 'row_id': row['id']}))
    db.flush()
    return parent


def _owned(db, run, model, record_id):
    row = db.scalar(select(model).where(model.id == record_id,
        model.owner_id == run.owner_id, model.store_id == run.store_id,
        model.session_id == run.session_id).execution_options(populate_existing=True))
    if row is None:
        _conflict()
    if isinstance(row, AssistantProposal):
        thread = db.scalar(
            select(AssistantSession).where(AssistantSession.id == run.session_id,
                AssistantSession.owner_id == run.owner_id, AssistantSession.store_id == run.store_id))
        if thread is None or (row.owner_role, row.access_version) != (thread.owner_role, thread.access_version):
            _conflict()
    return row


def _parent_outcome(db, run, item, data, spec):
    """Only fixed receipt scalars may accompany a persisted MCP outcome."""
    value = data['outcome']
    if value is None:
        if item.status == 'succeeded':
            _conflict()
        return
    if type(value) is not dict or item.status not in {'succeeded', 'failed'} or item.finished_at is None:
        _conflict()
    kind = value.get('kind')
    if kind == 'error':
        if (set(value) != {'kind', 'status'} or type(value['status']) is not int
                or not 400 <= value['status'] <= 599 or item.status != 'failed'):
            _conflict()
    elif kind in {'read', 'prepare'}:
        if set(value) != {'kind'} or spec.kind != kind:
            _conflict()
    elif kind == 'issue':
        if (data['name'] != 'record_issue' or set(value) != {'kind', 'issue_id'}
                or type(value['issue_id']) is not int or value['issue_id'] < 1):
            _conflict()
        _owned(db, run, AssistantIssue, value['issue_id'])
    elif kind == 'plan':
        receipt = value.get('receipt')
        if data['name'] != 'save_work_plan' or set(value) != {'kind', 'receipt'} or type(receipt) is not dict:
            _conflict()
        expected = {'status', 'plan_id', 'version', 'business_executed'}
        modern = data['arguments'].get('schema_version', 1) == 2
        if modern:
            expected |= {'goal_version', 'engine_version'}
        expected.add('reused' if receipt.get('reused') is True else 'notice')
        if (set(receipt) != expected or type(receipt['status']) is not int or receipt['status'] != 200
                or type(receipt['version']) is not int or receipt['version'] < 1
                or receipt['business_executed'] is not False
                or modern and (receipt['engine_version'] != 2 or type(receipt['goal_version']) is not int or receipt['goal_version'] < 1)
                or 'notice' in receipt and receipt['notice'] != (
                    '仅保存办事计划；原卡与办理记录保持，未开启跟进或执行业务。' if modern else
                    '仅保存本次办事计划；进度以草稿确认结果和实际原单为准，未自动执行业务。')):
            _conflict()
        plan = _owned(db, run, AssistantWorkPlan, receipt['plan_id'])
        if plan.version < receipt['version']:
            _conflict()
    else:
        _conflict()


def _frame(db, run):
    """Validate complete original inputs and every immutable result binding."""
    from .assistant_runtime_registry import _registry_for_profile
    from .assistant_runtime_runner import _manifest_data, _manifest_key, _work_key, _same_intent
    if not is_mcp_run(run):
        _conflict()
    thread = db.scalar(select(AssistantSession).where(AssistantSession.id == run.session_id,
        AssistantSession.owner_id == run.owner_id, AssistantSession.store_id == run.store_id))
    if thread is None:
        _conflict()
    items = list(db.scalars(select(RunItem).where(RunItem.run_id == run.id)
                           .execution_options(populate_existing=True)))
    parents = [item for item in items if item.item_key == _PARENT]
    if len(parents) != 1:
        _conflict()
    parent = parents[0]
    data = deepcopy(parent.validated_arguments)
    if (parent.kind != 'tool' or parent.attempt_no != 1 or type(data) is not dict
            or set(data) != {'schema_version', 'source', 'name', 'arguments', 'rows', 'outcome'}
            or type(data['schema_version']) is not int or data['schema_version'] != 1 or data['source'] != 'mcp_tool'
            or parent.tool_name != data['name'] or run.request_digest != _digest(data['name'], data['arguments'])):
        _conflict()
    registry = _registry_for_profile('business_v1')
    if registry.validate_arguments(data['name'], data['arguments']) != data['arguments']:
        _conflict()
    _parent_outcome(db, run, parent, data, registry.spec(data['name']))
    expected = _rows(data['name'], data['arguments'])
    if type(data['rows']) is not list or len(expected) != len(data['rows']):
        _conflict()
    covered, children, ids = {parent.id}, {}, set()
    for position, (row, value) in enumerate(zip(data['rows'], expected), 1):
        if type(row) is not dict or set(row) != _ROW_KEYS or row['position'] != position or row['input'] != value:
            _conflict()
        try:
            if str(UUID(row['id'])) != row['id'] or row['id'] in ids:
                _conflict()
        except (ValueError, TypeError, AttributeError):
            _conflict()
        ids.add(row['id'])
        matches = [item for item in items if item.item_key == 'mcp:row:' + row['id']]
        if len(matches) != 1:
            _conflict()
        child = matches[0]
        if (child.kind != 'batch_row' or child.attempt_no != 1 or child.tool_name != data['name']
                or child.validated_arguments != {'schema_version': 1, 'source': 'mcp_row',
                    'parent_id': parent.id, 'row_id': row['id']}):
            _conflict()
        children[row['id']] = child
        covered.add(child.id)
        outcome = row['outcome']
        if outcome is None:
            allowed = {'pending', 'skipped'} if parent.status in {'failed', 'skipped'} or run.status == 'cancelled' else {'pending'}
            if child.status not in allowed or child.proposal_id or child.work_item_id:
                _conflict()
            continue
        if type(outcome) is not dict or outcome.get('kind') not in {'card', 'error', 'no_card'}:
            _conflict()
        if outcome['kind'] != 'card':
            failed = outcome['kind'] == 'error'
            if (set(outcome) != {'kind', 'status'} or child.proposal_id or child.work_item_id
                    or child.status != ('failed' if failed else 'succeeded') or child.finished_at is None
                    or failed and (type(outcome['status']) is not int or not 400 <= outcome['status'] <= 599)
                    or not failed and outcome['status'] is not None):
                _conflict()
            continue
        if (set(outcome) != {'kind', 'proposal_id', 'source_work_item_id', 'manifest_id', 'input_item_id'}
                or child.status != 'succeeded' or child.finished_at is None):
            _conflict()
        card = _owned(db, run, AssistantProposal, outcome['proposal_id'])
        if (card.source_work_item_id != outcome['source_work_item_id']
                or child.proposal_id != card.id or child.work_item_id != card.source_work_item_id):
            _conflict()
        work = _owned(db, run, WorkItem, card.source_work_item_id) if card.source_work_item_id else None
        if work is not None and (work.item_kind != 'prepare' or work.operation_id != card.operation_id):
            _conflict()
        if work is not None and not _same_intent(work.validated_intent, work.validated_intent):
            _conflict()
        if outcome['manifest_id'] is None:
            if outcome['input_item_id'] is not None:
                _conflict()
            continue  # Explicit legacy-content reuse; never reparent this card.
        manifest = next((item for item in items if item.id == outcome['manifest_id']), None)
        if manifest is None:
            _conflict()
        md = _manifest_data(manifest)
        scope = md['scope']
        if ((scope['owner_id'], scope['store_id'], scope['session_id'], scope['role'], scope['access_version'])
                != (run.owner_id, run.store_id, run.session_id, thread.owner_role, thread.access_version)
                or scope['plan_id'] is not None or scope['step_id'] is not None or scope['goal_version'] is not None
                or scope['intent_version'] != 1 or scope['origin_request_id'] != run.request_id
                or scope['tool_key'] != 'mcp:row:' + row['id'] or manifest.item_key != _manifest_key(scope)
                or len(md['rows']) != 1 or work is None or manifest.status != 'succeeded'
                or md.get('previous_manifest_id') is not None or md.get('previous_compatibility_proposal_id') is not None
                or md.get('selected_input_item_ids') != []):
            _conflict()
        original = md['rows'][0]
        if (original['input'] != row['input'] or original['input_item_id'] != outcome['input_item_id']
                or original['proposal_id'] != card.id or original['work_item_id'] != work.id
                or original.get('carry_forward') is not None or work.plan_id is not None or work.step_id is not None
                or work.intent_version != 1 or work.supersedes_id is not None
                or work.origin_request_id != run.request_id
                or work.input_item_id != original['input_item_id'] or work.intent_key != _work_key(scope, original['input_item_id'])):
            _conflict()
        covered.add(manifest.id)
    if covered != {item.id for item in items}:
        _conflict()
    if parent.status == 'succeeded' and (parent.finished_at is None or any(row['outcome'] is None for row in data['rows'])):
        _conflict()
    return parent, data, children


def safe_retry(db, run, items, now):
    """Recovery may finish original tool rows; it never replays a submission."""
    try:
        from .assistant_runtime_principal import _time
        parent, data, children = _frame(db, run)
        if parent.status not in {'pending', 'running', 'succeeded'}:
            return False
        cards = []
        for row in data['rows']:
            outcome = row['outcome']
            if outcome is None:
                continue
            if outcome['kind'] != 'card':
                return False
            card = _owned(db, run, AssistantProposal, outcome['proposal_id'])
            if (card.status not in {'pending', 'succeeded'} or card.status == 'pending'
                    and (card.expires_at is None or _time(card.expires_at) <= _time(now))):
                return False
            work = _owned(db, run, WorkItem, card.source_work_item_id) if card.source_work_item_id else None
            if work and (work.status == 'uncertain' or db.scalar(select(WorkItem.id)
                    .where(WorkItem.supersedes_id == work.id).limit(1))):
                return False
            cards.append(card.id)
        if cards and db.scalar(select(RunItem.id).where(RunItem.kind == 'confirmation',
                RunItem.proposal_id.in_(cards), RunItem.status.in_({'pending', 'running', 'uncertain'})).limit(1)):
            return False
        return True
    except (HTTPException, ValueError, TypeError, KeyError):
        return False


def _load(db, principal, run_id=None):
    from .assistant_runtime_principal import revalidate_principal
    from .assistant_runtime_queue import _scope
    revalidate_principal(db, principal)
    _scope(db, principal.store_id)
    run = db.scalar(select(Run).where(Run.id == (run_id or principal.run_id),
        Run.owner_id == principal.actor_id, Run.store_id == principal.store_id,
        Run.session_id == principal.session_id).execution_options(populate_existing=True))
    if run is None:
        _conflict()
    return run, *_frame(db, run)


def _commit(db, principal, clock):
    from .assistant_runtime_principal import revalidate_principal
    db.flush()
    revalidate_principal(db, principal, clock=clock)
    service.commit(db)


def _start(db, principal, clock):
    from .assistant_runtime_queue import lock_for_write
    db.rollback()
    lock_for_write(db, principal, clock=clock)
    run, parent, data, _ = _load(db, principal)
    if parent.status == 'pending':
        parent.status, parent.started_at = 'running', clock()
    _commit(db, principal, clock)


async def _resolve_row(db, principal, data, row, config, client_factory):
    from .assistant_runtime_principal import request_for_principal
    from .assistant_runtime_registry import registry_for_config
    request = request_for_principal(db, principal, client_factory=client_factory)
    name = {'prepare_operations': 'prepare_operation',
            'prepare_business_batch': 'prepare_business_form'}.get(data['name'], data['name'])
    registry = registry_for_config(config)
    args = registry.validate_arguments(name, deepcopy(row['input']))
    if data['name'] == 'prepare_business_batch':
        from .business_assistant_business_tools import inspect_form
        form = await inspect_form(db, request, principal, principal.session_id, config, args['form_ref'])
        if args['form_ref'].startswith('case:') or form['kind'] == 'action':
            raise HTTPException(409, '同一原单的动作不能当成独立批量；请按真实依赖逐项准备')
    return await registry.spec(name).handler(db, request, principal, principal.session_id,
                                          args, config, resolve_only=True)


def _save_row(db, principal, row_id, resolved, *, clock):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_runner import accept_complete_input, prepare_work_item, _manifest_data
    from .assistant_runtime_events import append_event
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock)
        run, parent, data, children = _load(db, principal)
        row = next(value for value in data['rows'] if value['id'] == row_id)
        if row['outcome'] is not None:
            db.rollback()
            return
        child = children[row_id]
        if isinstance(resolved, service.ResolvedPreparation):
            # Original content dedupe, inside the same protected transaction.
            # A newly constructed transient card is intentionally not attached;
            # a real new intention below is created by the existing M2 writer.
            candidate = service.build_proposal(db, principal, principal.session_id, resolved)
            manifest_id = input_id = None
            if inspect(candidate).persistent:
                card = candidate
                db.flush()  # Preserve the original presentation refresh.
            else:
                manifest = accept_complete_input(db, principal, principal.session_id, run.id,
                    'mcp:row:' + row_id, [deepcopy(row['input'])],
                    origin_request_id=run.request_id, execution_authorized=True)
                manifest_id = manifest.id
                input_id = _manifest_data(manifest)['rows'][0]['input_item_id']
                result = prepare_work_item(db, principal, principal.session_id,
                    manifest_id, input_id, resolved, execution_authorized=True)
                if result['proposal_id'] is None:
                    raise HTTPException(409, '待确认卡已达容量，请先处理原卡后查询本请求')
                card = _owned(db, run, AssistantProposal, result['proposal_id'])
            row['outcome'] = {'kind': 'card', 'proposal_id': card.id,
                'source_work_item_id': card.source_work_item_id,
                'manifest_id': manifest_id, 'input_item_id': input_id}
            child.work_item_id, child.proposal_id = card.source_work_item_id, card.id
            child.status = 'succeeded'
        else:
            # Keep only safe resolution classification, not candidate/customer
            # payloads. A later replay obtains current choices by original GETs.
            error = type(resolved) is dict and type(resolved.get('status')) is int and resolved['status'] >= 400
            row['outcome'] = {'kind': 'error' if error else 'no_card',
                'status': resolved['status'] if error else None}
            child.status = 'failed' if error else 'succeeded'
            child.error_code = 'invalid_input' if error else None
        child.started_at = child.started_at or clock()
        child.finished_at = clock()
        parent.validated_arguments = data
        db.flush()
        append_event(db, principal, 'tool.finished', {'run_item_id': child.id,
            'work_item_id': child.work_item_id, 'result_refs': []}, clock=clock)
        _commit(db, principal, clock)
    except BaseException:
        db.rollback()
        raise


def _finish_item(db, principal, outcome, *, clock, failed=False, operation_seen=None):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock)
        _, item, data, children = _load(db, principal)
        if not failed and data['rows'] and any(row['outcome'] is None for row in data['rows']):
            _conflict()
        if item.status == 'succeeded':
            db.rollback()
            return
        data['outcome'] = deepcopy(outcome)
        item.validated_arguments = data
        item.status = 'failed' if failed else 'succeeded'
        item.error_code = 'invalid_input' if failed else None
        item.started_at = item.started_at or clock()
        item.finished_at = clock()
        if failed:
            for row in data['rows']:
                if row['outcome'] is None:
                    children[row['id']].status = 'skipped'
                    children[row['id']].finished_at = clock()
        if operation_seen is not None:
            if data['name'] != 'inspect_operation' or type(operation_seen) is not str:
                _conflict()
            thread = service.owned_session(db, principal, principal.session_id)
            thread.recent_operation_ids = [value for value in thread.recent_operation_ids or []
                if value != operation_seen][-5:] + [operation_seen]
        db.flush()
        append_event(db, principal, 'tool.finished', {'run_item_id': item.id,
            'work_item_id': None, 'result_refs': []}, clock=clock)
        _commit(db, principal, clock)
    except BaseException:
        db.rollback()
        raise


async def _save_plan(db, principal, data, config, clock, client_factory):
    from .assistant_runtime_principal import request_for_principal
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    from . import assistant_runtime_plans as plans
    from . import business_assistant_workboard as workboard
    request = request_for_principal(db, principal, client_factory=client_factory)
    modern = data['arguments'].get('schema_version', 1) == 2
    resolve = plans.resolve_plan if modern else workboard.resolve_legacy_plan
    persist = plans.persist_plan if modern else workboard.persist_legacy_plan
    token = await resolve(db, request, principal, principal.session_id, config,
        data['arguments'], principal=principal, clock=clock)
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock)
        # Persist must run before changing a tool row: it checks the entire
        # resolved source snapshot and then owns only flush-only plan changes.
        saved = persist(db, principal, principal.session_id, token, principal=principal, clock=clock)
        response = saved.response if modern else saved
        run, item, latest, _ = _load(db, principal)
        if item.status == 'succeeded':
            _conflict()
        allowed = {'status', 'plan_id', 'version', 'goal_version', 'engine_version',
                   'reused', 'business_executed', 'notice'}
        if set(response) - allowed:
            _conflict()
        latest['outcome'] = {'kind': 'plan', 'receipt': deepcopy(response)}
        item.validated_arguments = latest
        item.status, item.finished_at = 'succeeded', clock()
        db.flush()
        append_event(db, principal, 'tool.finished', {'run_item_id': item.id,
            'work_item_id': None, 'result_refs': []}, clock=clock)
        _commit(db, principal, clock)
    except BaseException:
        db.rollback()
        raise


def _save_issue(db, principal, data, config, clock):
    from .assistant_runtime_queue import lock_for_write
    from .assistant_runtime_events import append_event
    db.rollback()
    try:
        lock_for_write(db, principal, clock=clock)
        _, item, latest, _ = _load(db, principal)
        if item.status == 'succeeded':
            db.rollback()
            return
        args = latest['arguments']
        clean = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[电话已隐藏]', service.safe_text(args.get('summary'), 1200))
        issue = AssistantIssue(owner_id=principal.actor_id, store_id=principal.store_id,
            session_id=principal.session_id, category=args.get('category') if args.get('category') in service.ISSUE_CATEGORIES else 'system',
            summary=clean, operation_id=service.safe_text(args.get('operation_id', ''), 180), synthetic=config.synthetic)
        db.add(issue)
        db.flush()
        latest['outcome'] = {'kind': 'issue', 'issue_id': issue.id}
        item.validated_arguments, item.status, item.finished_at = latest, 'succeeded', clock()
        db.flush()
        append_event(db, principal, 'tool.finished', {'run_item_id': item.id,
            'work_item_id': None, 'result_refs': []}, clock=clock)
        _commit(db, principal, clock)
    except BaseException:
        db.rollback()
        raise


def _auth(principal):
    from .assistant_runtime_api import _LoginRead
    if principal.auth_kind != 'login' or not principal._login_ref:
        _conflict()
    return _LoginRead(principal.actor_id, principal.store_id, principal.role,
        principal.access_version, principal.session_id, principal._login_ref, principal._bind)


async def _card_view(db, principal, run_id, row_id, data, config, client_factory):
    from .assistant_runtime_principal import request_for_principal, revalidate_principal
    from .assistant_runtime_plans import _card_objects
    from .assistant_runtime_api import _native_reader, _visible_object
    run, _, current, _ = _load(db, principal, run_id)
    original = next(row for row in current['rows'] if row['id'] == row_id)
    if original['outcome'] != next(row for row in data['rows'] if row['id'] == row_id)['outcome']:
        _conflict()
    card = _owned(db, run, AssistantProposal, original['outcome']['proposal_id'])
    version, card_id = card.version, card.id
    refs = list(_card_objects(card))
    presentation = deepcopy((card.result or {}).get('business_presentation'))
    request = request_for_principal(db, principal, client_factory=client_factory)
    auth = _auth(principal)
    native = _native_reader(db, request, principal, auth)
    db.rollback()
    for ref in refs:
        if await _visible_object(db, auth, native, ref, strict_sources=True) is None:
            raise HTTPException(404, '原卡关联记录当前不可访问')
    if presentation and presentation.get('references') and original['input'].get('form_ref'):
        # Reuse the original chooser's exact selected-ID authorization. Stored
        # display labels and a readable Case cannot authorize another object.
        from .business_assistant_business_tools import inspect_form, candidates, is_relation
        form = await inspect_form(db, request, principal, principal.session_id,
                                  config, original['input']['form_ref'])
        fields = {field['key']: field for field in form['fields']}
        for key, selected in presentation['references'].items():
            if key not in fields or type(selected) is not dict or 'value' not in selected:
                raise HTTPException(404, '原卡来源目前无法核对')
            if is_relation(fields[key]) and (type(selected['value']) is not int or selected['value'] < 1):
                raise HTTPException(404, '原卡来源目前无法核对')
            options, _ = await candidates(db, request, principal, principal.session_id,
                config, form, fields[key], selected_id=selected['value'])
            if not any(type(option.get('value')) is type(selected['value'])
                       and option.get('value') == selected['value'] for option in options):
                raise HTTPException(404, '原卡来源目前无法访问')
    revalidate_principal(db, principal)
    db.rollback()
    run, _, _, _ = _load(db, principal, run_id)
    card = _owned(db, run, AssistantProposal, card_id)
    if card.version != version:
        _conflict()
    view = service.proposal_view(card)
    if original['input'].get('form_ref'):
        view.update(business_form_ref=original['input']['form_ref'], requires_employee_confirmation=True)
    prerequisites = (card.result or {}).get('prerequisites')
    if prerequisites:
        view['prerequisites'] = deepcopy(prerequisites)
        view['prerequisite_rule'] = '先核对已查询的原单和员工已提供的事实，不重复询问已知信息；确实缺少的事实集中放进当前卡片，依赖未产生的原单则等待确认后再继续。'
    db.rollback()
    return view, version


async def _project(db, principal, run_id, config, client_factory):
    """Current owned references only; never replay a stored read payload."""
    from .assistant_runtime_principal import request_for_principal, revalidate_principal
    from .assistant_runtime_registry import registry_for_config
    from .assistant_runtime_runner import runtime_read_tool
    run, item, data, _ = _load(db, principal, run_id)
    name, args = data['name'], data['arguments']
    spec = registry_for_config(config).spec(name)
    request = request_for_principal(db, principal, client_factory=client_factory)
    db.rollback()
    if spec.kind == 'read':
        if item.status != 'succeeded' or data['outcome'] != {'kind': 'read'}:
            outcome = data['outcome']
            if type(outcome) is dict and outcome.get('kind') == 'error':
                return {'status': outcome['status'], 'data': {'detail': '原查询未完成，请核对后发起新的查询'}}
            raise HTTPException(409, {'message': '原查询已停止或未完成，重发不会自动执行',
                                      'run_id': run_id, 'accepted': True})
        return await runtime_read_tool(db, request, principal, principal.session_id, name, args, config)
    if type(data['outcome']) is dict and data['outcome'].get('kind') == 'error' and not data['rows']:
        raise HTTPException(data['outcome']['status'], {'message': '原工具请求未完成，请核对输入或原业务条件',
            'run_id': run_id, 'accepted': True})
    if name == 'save_work_plan':
        outcome = data['outcome']
        if type(outcome) is not dict or outcome.get('kind') != 'plan':
            _conflict()
        from .assistant_runtime_api import shared_plan_view
        receipt = outcome['receipt']
        await shared_plan_view(db, request, principal, _auth(principal), receipt['plan_id'], strict_sources=True)
        return deepcopy(receipt)
    if name == 'record_issue':
        outcome = data['outcome']
        if type(outcome) is not dict or outcome.get('kind') != 'issue':
            _conflict()
        run, _, _, _ = _load(db, principal, run_id)
        view = service.issue_view(_owned(db, run, AssistantIssue, outcome['issue_id']))
        db.rollback()
        revalidate_principal(db, principal)
        return view
    results, versions = [], {}
    for row in data['rows']:
        outcome = row['outcome']
        if outcome is None:
            result = {'status': 409, 'error': '本行尚未完成，请使用原请求号核对原结果'}
        elif outcome['kind'] == 'card':
            try:
                result, version = await _card_view(db, principal, run_id, row['id'], data, config, client_factory)
                if result['id'] in versions and versions[result['id']] != version:
                    _conflict()
                versions[result['id']] = version
            except HTTPException as exc:
                revalidate_principal(db, principal)
                result = {'status': exc.status_code, 'error': '原卡关联记录当前无法核对，请打开原请求重查'}
        elif outcome['kind'] == 'error':
            result = {'status': outcome['status'], 'error': '本行未生成卡片，请核对资料或原业务条件'}
        else:
            try:
                db.rollback()
                refreshed = await _resolve_row(db, principal, data, row, config, client_factory)
                result = refreshed if isinstance(refreshed, dict) else {
                    'status': 200, 'prepared': False, 'outcome': 'not_prepared',
                    'notice': '此请求原来没有生成卡；请核对当前资料后明确发起新的准备请求'}
            except HTTPException as exc:
                revalidate_principal(db, principal)
                result = {'status': exc.status_code, 'error': '本行资料目前无法核对'}
        results.append(result)
    revalidate_principal(db, principal)
    db.rollback()
    run, _, _, _ = _load(db, principal, run_id)
    current_cards = {}
    for card_id, version in versions.items():
        card = _owned(db, run, AssistantProposal, card_id)
        if card.version != version:
            _conflict()
        current_cards[card_id] = service.proposal_view(card)
    for result in results:
        if result.get('id') in current_cards:
            result.update(deepcopy(current_cards[result['id']]))
    db.rollback()
    if name not in _BATCH:
        if not results:
            _conflict()
        result = results[0]
        if type(result.get('status')) is int and result['status'] >= 400:
            raise HTTPException(result['status'], result.get('error', '本请求未完成'))
        return result
    seen, output = set(), []
    for index, result in enumerate(results, 1):
        card_id = result.get('id')
        repeated = card_id in seen if card_id else False
        if card_id:
            seen.add(card_id)
        if type(result.get('status')) is int and result['status'] >= 400:
            output.append({'row' if name == 'prepare_business_batch' else 'index': index,
                'status': result['status'], 'error': result.get('error', '本行尚未准备')})
        elif name == 'prepare_business_batch':
            output.append({'row': index, 'id': card_id, 'status': result.get('status'),
                'outcome': 'reused' if repeated else 'prepared' if card_id else result.get('outcome', 'not_prepared'),
                'missing': [q['label'] for q in result.get('questions', [])],
                **({'selection': result.get('selections')} if not card_id else {})})
        else:
            output.append({'index': index, 'id': card_id, 'status': result.get('status'),
                'summary': result.get('summary', ''), 'question_count': len(result.get('questions') or [])})
    if name == 'prepare_business_batch':
        return {'status': 200, 'input_count': len(results), 'unique_prepared': len(seen), 'items': output,
            'notice': '逐项真实结果；失败/未选来源的行没有草稿。确认仍由员工在原页面执行。'}
    pending = {value['id'] for value in output if value.get('id') and value.get('status') == 'pending'}
    return {'items': output, 'requested': len(results), 'prepared_or_reused': len(pending),
        'rejected': sum(value.get('status') != 'pending' for value in output),
        'notice': '按输入序号逐项核对；只生成或复用待确认卡，未执行业务。失败项没有生成卡，不代表其他项回滚。'}


async def execute_mcp(db, principal, config=None, *, clock=None, client_factory=None):
    """The same fixed 120-second fragment applies to HTTP and worker callers."""
    import asyncio
    async with asyncio.timeout(120):
        return await _execute_mcp(db, principal, config, clock=clock, client_factory=client_factory)


async def _execute_mcp(db, principal, config=None, *, clock=None, client_factory=None):
    """Execute one claimed fixed tool with zero model calls.

    Every saved row survives timeout/disconnect. Restarted workers read the
    original complete envelope and skip all completed rows, including cards
    whose later business status changed. Cancellation never invents a new ID.
    """
    from .assistant_runtime_principal import revalidate_principal, request_for_principal
    from .assistant_runtime_registry import registry_for_config
    from .assistant_runtime_runner import _RunHeartbeat, runtime_read_tool
    from .assistant_runtime_queue import release
    service.require_preparation_read_phase(db)
    revalidate_principal(db, principal, clock=clock)
    if principal.run_id is None:
        _conflict()
    clock, config = clock or principal._clock, _config(config)
    run, item, data, _ = _load(db, principal)
    if run.status != 'running':
        _conflict()
    spec = registry_for_config(config).spec(data['name'])
    db.rollback()
    heartbeat = _RunHeartbeat(db, principal, clock)
    heartbeat.start()
    released = closed = False
    try:
        _start(db, principal, clock)
        run, item, data, _ = _load(db, principal)
        complete = item.status in {'succeeded', 'failed'}
        db.rollback()
        immediate = None
        if spec.kind == 'read':
            if complete:
                immediate = await heartbeat.wait(_project(db, principal, principal.run_id, config, client_factory))
            else:
                request = request_for_principal(db, principal, client_factory=client_factory)
                immediate = await heartbeat.wait(runtime_read_tool(db, request, principal,
                    principal.session_id, data['name'], data['arguments'], config))
                status = immediate.get('status') if isinstance(immediate, dict) else None
                failed_read = type(status) is int and status >= 400
                _finish_item(db, principal, {'kind': 'error', 'status': status} if failed_read else {'kind': 'read'},
                    clock=clock, failed=failed_read,
                    operation_seen=immediate['id'] if data['name'] == 'inspect_operation' else None)
        elif not complete and spec.kind == 'prepare':
            for row in data['rows']:
                if row['outcome'] is not None:
                    continue
                try:
                    resolved = await heartbeat.wait(_resolve_row(db, principal, data, row, config, client_factory))
                except HTTPException as exc:
                    revalidate_principal(db, principal, clock=clock)
                    resolved = {'status': exc.status_code}
                try:
                    _save_row(db, principal, row['id'], resolved, clock=clock)
                except HTTPException as exc:
                    # Each legacy batch row is independent. Losing authority
                    # still raises; a native/card rejection records this row
                    # only after rollback and a new valid fenced transaction.
                    revalidate_principal(db, principal, clock=clock)
                    _save_row(db, principal, row['id'], {'status': exc.status_code}, clock=clock)
                db.rollback()
            _, _, latest, _ = _load(db, principal)
            single_error = data['name'] not in _BATCH and latest['rows'][0]['outcome']['kind'] == 'error'
            _finish_item(db, principal, {'kind': 'prepare'}, clock=clock, failed=single_error)
        elif not complete and data['name'] == 'save_work_plan':
            await heartbeat.wait(_save_plan(db, principal, data, config, clock, client_factory))
        elif not complete and data['name'] == 'record_issue':
            _save_issue(db, principal, data, config, clock)
        elif not complete:
            raise HTTPException(403, '此工具不能通过本地工具入口执行')
        # Build current views while the real lease still authorizes native GETs.
        view_error = None
        try:
            result = immediate if spec.kind == 'read' else await heartbeat.wait(
                _project(db, principal, principal.run_id, config, client_factory))
        except HTTPException as exc:
            revalidate_principal(db, principal, clock=clock)
            view_error, result = exc, None
        db.rollback()
        _, current, _, _ = _load(db, principal)
        failed = current.status == 'failed'
        db.rollback()
        heartbeat.stop()
        release(db, principal, outcome='failed' if failed else 'succeeded',
                error_code='invalid_input' if failed else None, clock=clock)
        released = True
        await heartbeat.close()
        closed = True
        from .assistant_runtime_api import _guard
        _guard(db, _auth(principal))  # Current login, not the finished lease.
        if view_error is not None:
            raise view_error
        return service.scrub(result)
    except BaseException as exc:
        heartbeat.stop()
        db.rollback()
        if not released:
            try:
                import asyncio
                transient = isinstance(exc, (asyncio.CancelledError, TimeoutError)) or (
                    isinstance(exc, HTTPException) and exc.status_code >= 500)
                try:
                    revalidate_principal(db, principal, clock=clock)
                except HTTPException:
                    release(db, principal, outcome='cancelled', error_code='permission_denied', clock=clock)
                else:
                    if transient:
                        release(db, principal, outcome='retry', error_code='runtime_unavailable', clock=clock)
                    else:
                        code = exc.status_code if isinstance(exc, HTTPException) else 500
                        _finish_item(db, principal, {'kind': 'error', 'status': code}, clock=clock, failed=True)
                        release(db, principal, outcome='failed', error_code='invalid_input'
                                if code < 500 else 'runtime_unavailable', clock=clock)
            except BaseException:
                db.rollback()  # Lost authority/lease is left to the reclaimer.
        raise
    finally:
        db.rollback()
        if not closed:
            await heartbeat.close()


async def replay_mcp(db, request, user, sid, run_id, config=None):
    """An original-login read, never a new claim, preparation or submission."""
    from .assistant_runtime_api import _capture, _guard
    from .assistant_runtime_principal import principal_for_request, revalidate_principal
    auth = _capture(db, request, user, sid)
    _guard(db, auth)
    principal = principal_for_request(db, request, auth, sid)
    run, parent, data, _ = _load(db, principal, run_id)
    if run.status in {'queued', 'running'}:
        db.rollback()
        raise HTTPException(409, {'message': '原请求已接纳，正在等待/处理中，请使用同一请求号查询原结果',
                                  'run_id': run.id, 'accepted': True})
    partial = any(row['outcome'] is None for row in data['rows'])
    db.rollback()
    result = await _project(db, principal, run_id, _config(config), None)
    revalidate_principal(db, principal)
    db.rollback()
    _guard(db, auth)
    if partial and isinstance(result, dict):
        result = {**result, 'notice': '原请求未全部完成；以下仅是原清单的真实结果，请核对未完成行。'}
    return service.scrub(result)
