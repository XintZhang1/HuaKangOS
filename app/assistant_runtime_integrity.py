"""Read-only SQLite/SQLAlchemy backup checks for Runtime private references.

This module imports only pure contracts. It neither authorizes current business
actions nor repairs historical or interrupted work. Errors contain no row data.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from functools import lru_cache
import json
from uuid import UUID

from pydantic import TypeAdapter

from . import assistant_runtime_schemas as schema


PREFIX = 'business_assistant_'
_COLUMNS = {
    'plan_steps': '''id plan_id key position title wait_for depends_on proposal_id
        object_ref workflow_id form_ref conditions completion_conditions required
        status wait_reason last_evidence intent_version version created_at updated_at''',
    'work_items': '''id owner_id store_id session_id plan_id step_id origin_request_id
        input_item_id intent_version item_kind intent_key operation_id validated_intent
        source_refs status supersedes_id version created_at updated_at''',
    'runs': '''id owner_id store_id session_id plan_id trigger_kind trigger_key request_id
        request_digest entry_context auth_kind login_session_ref grant_id goal_version
        status next_run_at lease_owner lease_until fence attempt stop_requested priority
        display_text display_revision event_seq usage error_code started_at finished_at
        version created_at''',
    'run_items': '''id run_id work_item_id proposal_id kind item_key attempt_no tool_name
        validated_arguments result_refs status error_code started_at finished_at
        submission_snapshot submission_digest version created_at''',
    'context_snapshots': '''id owner_id store_id session_id plan_id goal_version
        through_message_id goal constraints confirmed_selections open_questions
        evidence_refs unverified_notes created_at''',
    'run_events': 'id run_id seq type payload created_at',
    'followup_grants': '''id plan_id owner_id store_id session_id owner_role access_version
        goal_version status granted_at expires_at revoked_at stop_reason version created_at''',
    'wake_events': '''id signal_key topic store_id object_ref proposal_id task_id plan_id
        source_ref state attempt next_attempt_at created_at dispatched_at version''',
    'notifications': '''id owner_id store_id session_id plan_id proposal_id task_id
        source_key kind safe_summary status created_at read_at version''',
}
_COLUMNS = {PREFIX + key: value.split() for key, value in _COLUMNS.items()}
_BASE_COLUMNS = {
    PREFIX + 'sessions': 'id owner_id store_id',
    PREFIX + 'messages': 'id session_id store_id request_id role',
    PREFIX + 'proposals': '''id session_id owner_id store_id owner_role access_version
        operation_id source_work_item_id status''',
    PREFIX + 'work_plans': '''id session_id owner_id store_id engine_version goal_version
        status context_snapshot_id next_check_at version''',
    'flow_tasks': 'id store_id', 'users': 'id', 'stores': 'id',
}
_BASE_COLUMNS = {key: value.split() for key, value in _BASE_COLUMNS.items()}
_PLAN_EXTENSIONS = {'engine_version', 'goal_version', 'status',
                    'context_snapshot_id', 'next_check_at'}
_JSON_COLUMNS = {
    'depends_on', 'object_ref', 'conditions', 'completion_conditions', 'last_evidence',
    'validated_intent', 'source_refs', 'entry_context', 'usage', 'validated_arguments',
    'result_refs', 'submission_snapshot', 'constraints', 'confirmed_selections',
    'open_questions', 'evidence_refs', 'unverified_notes', 'payload', 'source_ref',
}
_DATE_COLUMNS = {
    'created_at', 'updated_at', 'next_check_at', 'next_run_at', 'lease_until',
    'started_at', 'finished_at', 'granted_at', 'expires_at', 'revoked_at',
    'next_attempt_at', 'dispatched_at', 'read_at',
}
_NULLABLE_JSON = {'object_ref', 'last_evidence', 'entry_context', 'validated_arguments',
                  'result_refs', 'submission_snapshot', 'source_ref'}


def _fail(table, ident, code):
    safe_id = 'invalid-id'
    if type(ident) is int and ident > 0:
        safe_id = str(ident)
    elif type(ident) is str:
        try:
            if str(UUID(ident)) == ident:
                safe_id = ident
        except ValueError:
            pass
    raise ValueError(f'Runtime integrity: table={table} id={safe_id} code={code}') from None


def _execute(connection, sql, parameters=None):
    # All statements and identifiers here are fixed by this module, not row data.
    if hasattr(connection, 'exec_driver_sql'):
        if parameters is not None:
            from sqlalchemy import text
            return connection.execute(text(sql), parameters)
        return connection.exec_driver_sql(sql)
    return connection.execute(sql) if parameters is None else connection.execute(sql, parameters)


def _names(connection):
    if hasattr(connection, 'dialect'):
        from sqlalchemy import inspect
        return set(inspect(connection).get_table_names())
    return {row[0] for row in _execute(connection, "SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(connection, table):
    if hasattr(connection, 'dialect'):
        from sqlalchemy import inspect
        return {column['name'] for column in inspect(connection).get_columns(table)}
    return {row[1] for row in _execute(connection, f'PRAGMA table_info("{table}")')}


@lru_cache(maxsize=None)
def _adapter(annotation):
    return TypeAdapter(annotation)


def _typed(annotation, value, table, ident, code='invalid_structure'):
    try:
        return _adapter(annotation).validate_python(value, strict=True)
    except (ValueError, TypeError, OverflowError, RecursionError):
        _fail(table, ident, code)


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _rows(connection, table, columns):
    postgres = getattr(getattr(connection, 'dialect', None), 'name', None) == 'postgresql'
    # The JSON driver decoder would lose duplicate keys and conflate JSON null
    # with SQL NULL. Select text only for these fixed, known JSON columns.
    query = 'SELECT ' + ','.join(
        'CAST("' + column + '" AS TEXT) AS "' + column + '"'
        if postgres and column in _JSON_COLUMNS else '"' + column + '"'
        for column in columns)
    query += ' FROM "' + table + '"'
    rows = {}
    for values in _execute(connection, query):
        row = dict(zip(columns, values))
        ident = row['id']
        if ident in rows:
            _fail(table, ident, 'duplicate_id')
        for column in _JSON_COLUMNS.intersection(row):
            value = row[column]
            if value is None and column in _NULLABLE_JSON:
                continue
            try:
                if type(value) is str:
                    value = json.loads(value, object_pairs_hook=_json_pairs)
            except (ValueError, TypeError, RecursionError):
                _fail(table, ident, 'invalid_json')
            row[column] = _typed(schema.JsonValue, value, table, ident, 'invalid_json')
            if row[column] is None:
                # JSON null cannot stand in for a required object/list, or for
                # a nullable SQL column whose CHECK relies on SQL NULL.
                _fail(table, ident, 'invalid_json_null')
        for column in _DATE_COLUMNS.intersection(row):
            value = row[column]
            if value is None:
                continue
            try:
                if type(value) is str:
                    value = datetime.fromisoformat(value)
            except (ValueError, TypeError):
                _fail(table, ident, 'invalid_database_time')
            row[column] = _typed(schema.UTCDateTime, value, table, ident,
                                 'invalid_database_time')
        rows[ident] = row
    return rows


def _ref(records, ident, table, row_id, code='missing_reference'):
    try:
        value = records.get(ident)
    except TypeError:
        value = None
    if value is None:
        _fail(table, row_id, code)
    return value


def _scope(row):
    return row['owner_id'], row['store_id'], row['session_id']


def _same_scope(row, target, table):
    if _scope(row) != _scope(target):
        _fail(table, row['id'], 'scope_mismatch')


def _unique(rows, columns, table, nullable=False):
    seen = set()
    for row in rows.values():
        key = tuple(row[column] for column in columns)
        if nullable and any(value is None for value in key):
            continue
        if key in seen:
            _fail(table, row['id'], 'duplicate_key')
        seen.add(key)


def _acyclic(graph, table):
    # Kahn's algorithm also handles deep graphs without recursive call limits.
    indegree = {key: len(deps) for key, deps in graph.items()}
    successors = defaultdict(list)
    for key, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                _fail(table, key, 'dangling_dependency')
            successors[dep].append(key)
    pending = [key for key, count in indegree.items() if count == 0]
    visited = 0
    while pending:
        key = pending.pop()
        visited += 1
        for successor in successors[key]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                pending.append(successor)
    if visited != len(graph):
        _fail(table, next(key for key, count in indegree.items() if count),
              'dependency_cycle')


def validate(connection):
    """Validate raw SQLite or SQLAlchemy SQLite/PG without modifying records."""
    names = _names(connection)
    plan_table = PREFIX + 'work_plans'
    proposal_table = PREFIX + 'proposals'
    plan_columns = _columns(connection, plan_table) if plan_table in names else set()
    proposal_columns = _columns(connection, proposal_table) if proposal_table in names else set()
    revisions = set()
    if 'alembic_version' in names:
        if 'version_num' not in _columns(connection, 'alembic_version'):
            _fail('alembic_version', '-', 'missing_column')
        revisions = {row[0] for row in _execute(connection, 'SELECT version_num FROM alembic_version')}
    runtime_present = (bool(set(_COLUMNS) & names)
                       or bool(_PLAN_EXTENSIONS & plan_columns)
                       or 'source_work_item_id' in proposal_columns
                       or 'h53k_assistant_runtime' in revisions)
    if not runtime_present:
        return {'assistant_runtime': 0}
    for table, required in {**_BASE_COLUMNS, **_COLUMNS}.items():
        if table not in names:
            _fail(table, '-', 'missing_table')
        if not set(required) <= _columns(connection, table):
            _fail(table, '-', 'missing_column')
    data = {table: _rows(connection, table, columns)
            for table, columns in {**_BASE_COLUMNS, **_COLUMNS}.items()}
    sessions = data[PREFIX + 'sessions']
    messages = data[PREFIX + 'messages']
    proposals = data[proposal_table]
    plans = data[plan_table]
    tasks = data['flow_tasks']
    steps = data[PREFIX + 'plan_steps']
    work = data[PREFIX + 'work_items']
    runs = data[PREFIX + 'runs']
    items = data[PREFIX + 'run_items']
    snapshots = data[PREFIX + 'context_snapshots']
    events = data[PREFIX + 'run_events']
    grants = data[PREFIX + 'followup_grants']

    # Validate literal types/check constraints even in a damaged backup whose
    # original indexes or constraints are no longer present.
    statuses = {'plan_steps': schema.StepStatus, 'work_items': schema.WorkItemStatus,
                'runs': schema.RunStatus, 'run_items': schema.RunItemStatus,
                'followup_grants': schema.GrantStatus,
                'notifications': schema.NotificationStatus}
    for table in _COLUMNS:
        for row in data[table].values():
            _typed(schema.UUIDText, row['id'], table, row['id'], 'invalid_id')
            for field in ('version', 'intent_version', 'access_version', 'attempt_no'):
                if field in row:
                    _typed(schema.Version, row[field], table, row['id'], 'invalid_version')
            for field in ('position', 'fence', 'attempt', 'display_revision', 'event_seq'):
                if field in row:
                    _typed(schema.Counter, row[field], table, row['id'], 'invalid_counter')
            if table.removeprefix(PREFIX) in statuses:
                _typed(statuses[table.removeprefix(PREFIX)], row['status'], table, row['id'])
            for field in ('required', 'stop_requested'):
                if field in row and not (type(row[field]) in (bool, int) and row[field] in (0, 1)):
                    _fail(table, row['id'], 'invalid_boolean')
            if 'store_id' in row:
                _ref(data['stores'], row['store_id'], table, row['id'])
            if 'owner_id' in row:
                _ref(data['users'], row['owner_id'], table, row['id'])
            if 'session_id' in row and row['session_id'] is not None:
                session = _ref(sessions, row['session_id'], table, row['id'])
                if (row['owner_id'], row['store_id']) != (session['owner_id'], session['store_id']):
                    _fail(table, row['id'], 'scope_mismatch')
            if 'plan_id' in row and row['plan_id'] is not None and 'session_id' in row:
                plan = _ref(plans, row['plan_id'], table, row['id'])
                if row['session_id'] is not None:
                    _same_scope(row, plan, table)
                elif (row['owner_id'], row['store_id']) != (plan['owner_id'], plan['store_id']):
                    _fail(table, row['id'], 'scope_mismatch')

    for table, rows in ((plan_table, plans), (proposal_table, proposals)):
        for row in rows.values():
            session = _ref(sessions, row['session_id'], table, row['id'])
            if (row['owner_id'], row['store_id']) != (session['owner_id'], session['store_id']):
                _fail(table, row['id'], 'scope_mismatch')

    def private_ref(records, ident, scope_row, table):
        target = _ref(records, ident, table, scope_row['id'])
        _same_scope(scope_row, target, table)
        return target

    def message_ref(ident, scope_row, table):
        message = _ref(messages, ident, table, scope_row['id'])
        if (message['session_id'], message['store_id']) != (scope_row['session_id'], scope_row['store_id']):
            _fail(table, scope_row['id'], 'message_scope_mismatch')
        return message

    def task_ref(ident, scope_row, table):
        task = _ref(tasks, ident, table, scope_row['id'])
        if task['store_id'] != scope_row['store_id']:
            _fail(table, scope_row['id'], 'task_store_mismatch')
        return task

    def object_ref(value, scope_row, table):
        checked = _typed(schema.BusinessObjectRef, value, table, scope_row['id'])
        if checked.type == 'report_query':
            item = private_ref(work, checked.id, scope_row, table)
            if (item['item_kind'] != 'read' or type(item['operation_id']) is not str
                    or not item['operation_id'].startswith('GET ')):
                _fail(table, scope_row['id'], 'report_query_not_read')

    def evidence_refs(value, scope_row, table):
        refs = _typed(list[schema.EvidenceRef], value, table, scope_row['id'])
        for evidence in refs:
            if evidence.source_type == 'message':
                message_ref(evidence.source_id, scope_row, table)
            elif evidence.source_type == 'proposal':
                private_ref(proposals, evidence.source_id, scope_row, table)
            elif evidence.source_type == 'task':
                task_ref(evidence.source_id, scope_row, table)
            elif evidence.source_type == 'object':
                object_ref(evidence.source_id, scope_row, table)
        # Native object/receipt truth and authorization stay with native services.

    steps_by_plan = defaultdict(dict)
    for plan in plans.values():
        _typed(schema.PlanStatus, plan['status'], plan_table, plan['id'])
        _typed(schema.Version, plan['goal_version'], plan_table, plan['id'])
        _typed(schema.Version, plan['version'], plan_table, plan['id'])
        if type(plan['engine_version']) is not int or plan['engine_version'] not in (1, 2):
            _fail(plan_table, plan['id'], 'invalid_engine_version')
        if plan['context_snapshot_id'] is not None:
            snapshot = private_ref(snapshots, plan['context_snapshot_id'], plan, plan_table)
            if snapshot['plan_id'] is not None and snapshot['plan_id'] != plan['id']:
                _fail(plan_table, plan['id'], 'context_plan_mismatch')

    table = PREFIX + 'plan_steps'
    _unique(steps, ('plan_id', 'key'), table)
    _unique(steps, ('plan_id', 'proposal_id'), table, nullable=True)
    for step in steps.values():
        plan = _ref(plans, step['plan_id'], table, step['id'])
        scope_row = {**plan, 'id': step['id']}
        _typed(schema.StepKey, step['key'], table, step['id'])
        deps = _typed(list[schema.StepKey], step['depends_on'], table, step['id'])
        if len(deps) != len(set(deps)) or step['key'] in deps:
            _fail(table, step['id'], 'invalid_dependency')
        steps_by_plan[step['plan_id']][step['key']] = step
        if step['proposal_id'] is not None:
            private_ref(proposals, step['proposal_id'], scope_row, table)
        if step['object_ref'] is not None:
            object_ref(step['object_ref'], scope_row, table)
        for field in ('conditions', 'completion_conditions'):
            for condition in _typed(list[schema.Condition], step[field], table, step['id']):
                if condition.type == 'proposal_succeeded':
                    private_ref(proposals, condition.proposal_id, scope_row, table)
                elif condition.type == 'native_task_state':
                    task_ref(condition.task_id, scope_row, table)
                elif condition.type == 'due_at':
                    message_ref(condition.source_message_id, scope_row, table)
                else:
                    object_ref(condition.object_ref, scope_row, table)
        if step['last_evidence'] is not None:
            evidence_refs(step['last_evidence'], scope_row, table)
    for plan in plans.values():
        graph = steps_by_plan[plan['id']]
        if plan['engine_version'] == 2 and not graph:
            _fail(plan_table, plan['id'], 'missing_steps')
        for step in graph.values():
            if any(dep not in graph for dep in step['depends_on']):
                _fail(table, step['id'], 'dangling_dependency')
        _acyclic({step['id']: [graph[dep]['id'] for dep in step['depends_on']]
                  for step in graph.values()}, table)

    table = PREFIX + 'work_items'
    _unique(work, ('owner_id', 'store_id', 'intent_key'), table)
    cards_by_work = {}
    for proposal in proposals.values():
        work_id = proposal['source_work_item_id']
        if work_id is None:
            continue  # Legacy proposals need neither a WorkItem nor a snapshot.
        item = private_ref(work, work_id, proposal, proposal_table)
        if work_id in cards_by_work:
            _fail(proposal_table, proposal['id'], 'duplicate_work_item_card')
        cards_by_work[work_id] = proposal
        if item['item_kind'] != 'prepare' or item['operation_id'] != proposal['operation_id']:
            _fail(proposal_table, proposal['id'], 'work_item_operation_mismatch')
    for item in work.values():
        _typed(schema.WorkItemKind, item['item_kind'], table, item['id'])
        _typed(schema.OperationId, item['operation_id'], table, item['id'])
        _typed(schema.JsonObject, item['validated_intent'], table, item['id'])
        # B3 preparation references are not yet the EvidenceRef wire contract.
        # Persisted source references must remain finite JSON object arrays;
        # explicit evidence_refs/last_evidence use the stricter typed contract.
        _typed(list[schema.JsonObject], item['source_refs'], table, item['id'])
        if item['step_id'] is not None:
            step = _ref(steps, item['step_id'], table, item['id'])
            if item['plan_id'] is None or step['plan_id'] != item['plan_id']:
                _fail(table, item['id'], 'step_plan_mismatch')
            if item['intent_version'] > step['intent_version']:
                _fail(table, item['id'], 'future_intent_version')
        if item['item_kind'] == 'prepare' and item['status'] != 'planned' and item['id'] not in cards_by_work:
            _fail(table, item['id'], 'missing_prepared_card')
        if item['item_kind'] == 'read' and item['status'] == 'prepared':
            _fail(table, item['id'], 'invalid_read_status')
        if item['supersedes_id'] is not None:
            previous = private_ref(work, item['supersedes_id'], item, table)
            if any(item[field] != previous[field] for field in ('plan_id', 'step_id', 'input_item_id', 'item_kind')):
                _fail(table, item['id'], 'supersedes_intent_mismatch')
            if item['intent_version'] <= previous['intent_version']:
                _fail(table, item['id'], 'supersedes_version_mismatch')
    _acyclic({item['id']: [item['supersedes_id']] if item['supersedes_id'] is not None else []
              for item in work.values()}, table)

    table = PREFIX + 'followup_grants'
    active_plans = set()
    for grant in grants.values():
        plan = _ref(plans, grant['plan_id'], table, grant['id'])
        _typed(schema.Version, grant['goal_version'], table, grant['id'])
        if grant['status'] == 'active':
            if grant['plan_id'] in active_plans:
                _fail(table, grant['id'], 'duplicate_active_grant')
            active_plans.add(grant['plan_id'])
            if grant['goal_version'] != plan['goal_version'] or plan['engine_version'] != 2:
                _fail(table, grant['id'], 'active_goal_version_mismatch')

    table = PREFIX + 'runs'
    _unique(runs, ('owner_id', 'store_id', 'trigger_key'), table)
    message_keys = {(row['session_id'], row['request_id']): row for row in messages.values()}
    for run in runs.values():
        _typed(schema.TriggerKind, run['trigger_kind'], table, run['id'])
        _typed(schema.AuthKind, run['auth_kind'], table, run['id'])
        _typed(schema.SHA256Text, run['request_digest'], table, run['id'])
        _typed(schema.JsonObject, run['usage'], table, run['id'])
        if (run['plan_id'] is None) != (run['goal_version'] is None):
            _fail(table, run['id'], 'plan_goal_mismatch')
        if run['goal_version'] is not None:
            _typed(schema.Version, run['goal_version'], table, run['id'])
            if run['goal_version'] > plans[run['plan_id']]['goal_version']:
                _fail(table, run['id'], 'future_goal_version')
        if run['auth_kind'] == 'login':
            if run['grant_id'] is not None:
                _fail(table, run['id'], 'invalid_auth_source')
            _typed(schema.SHA256Text, run['login_session_ref'], table, run['id'], 'invalid_login_reference')
            # LoginSession may have been deleted on logout; it is not an FK.
        else:
            if run['login_session_ref'] is not None or run['plan_id'] is None:
                _fail(table, run['id'], 'invalid_auth_source')
            grant = private_ref(grants, run['grant_id'], run, table)
            if grant['plan_id'] != run['plan_id']:
                _fail(table, run['id'], 'grant_plan_mismatch')
            if grant['goal_version'] != run['goal_version']:
                _fail(table, run['id'], 'grant_goal_version_mismatch')
            # An old Run and its old Grant can both predate the current Plan.
            # Resuming a changed goal creates a new Grant, never rewrites this one.
        if run['trigger_kind'] == 'user':
            message = _ref(message_keys, (run['session_id'], run['request_id']), table,
                           run['id'], 'missing_user_message')
            if message['role'] != 'user' or message['store_id'] != run['store_id']:
                _fail(table, run['id'], 'user_message_mismatch')
        if run['entry_context'] is not None:
            entry = _typed(schema.EntryContext, run['entry_context'], table, run['id'])
            if entry.source_type == 'task':
                task_ref(entry.task_id, run, table)
            elif entry.source_type == 'object':
                object_ref(entry.object_ref, run, table)

    table = PREFIX + 'context_snapshots'
    for snapshot in snapshots.values():
        if (snapshot['plan_id'] is None) != (snapshot['goal_version'] is None):
            _fail(table, snapshot['id'], 'plan_goal_mismatch')
        if snapshot['goal_version'] is not None:
            _typed(schema.Version, snapshot['goal_version'], table, snapshot['id'])
            if snapshot['goal_version'] > plans[snapshot['plan_id']]['goal_version']:
                _fail(table, snapshot['id'], 'future_goal_version')
        message_ref(snapshot['through_message_id'], snapshot, table)
        for field in ('constraints', 'open_questions', 'unverified_notes'):
            _typed(list[schema.JsonValue], snapshot[field], table, snapshot['id'])
        _typed(schema.JsonObject, snapshot['confirmed_selections'], table, snapshot['id'])
        evidence_refs(snapshot['evidence_refs'], snapshot, table)

    table = PREFIX + 'run_items'
    _unique(items, ('run_id', 'item_key', 'attempt_no'), table, nullable=True)
    confirmation_ids = set()
    for item in items.values():
        checked = _typed(schema.RunItemRecord, item, table, item['id'], 'invalid_run_item')
        parent = (_ref(runs, item['run_id'], table, item['id']) if item['run_id'] is not None
                  else _ref(proposals, item['proposal_id'], table, item['id']))
        scope_row = {**parent, 'id': item['id']}
        if item['work_item_id'] is not None:
            private_ref(work, item['work_item_id'], scope_row, table)
        if item['proposal_id'] is not None:
            proposal = private_ref(proposals, item['proposal_id'], scope_row, table)
            if (item['work_item_id'] is not None and proposal['source_work_item_id'] is not None
                    and item['work_item_id'] != proposal['source_work_item_id']):
                _fail(table, item['id'], 'proposal_work_item_mismatch')
        for result_ref in checked.result_refs or []:
            object_ref(result_ref, scope_row, table)
        if item['kind'] == 'confirmation':
            if item['proposal_id'] in confirmation_ids:
                _fail(table, item['id'], 'duplicate_confirmation')
            confirmation_ids.add(item['proposal_id'])
            snapshot = checked.submission_snapshot
            expected = (proposal['operation_id'], proposal['owner_id'], proposal['store_id'],
                        proposal['owner_role'], proposal['access_version'])
            actual = (snapshot.operation_id, snapshot.actor_id, snapshot.store_id,
                      snapshot.role, snapshot.access_version)
            if actual != expected:
                _fail(table, item['id'], 'frozen_proposal_mismatch')
            # RunItemRecord uses the shared M1.1 canonical SHA256 implementation.
            # Final employee answers need not equal the proposal's earlier draft.

    for proposal in proposals.values():
        # New execution enters executing in the same transaction as freezing.
        # Old cards have no Runtime source; pending/cancelled/expired new cards
        # can legitimately have never entered the confirmation transaction.
        if (proposal['source_work_item_id'] is not None
                and proposal['status'] in ('executing', 'succeeded', 'failed', 'uncertain')
                and proposal['id'] not in confirmation_ids):
            _fail(proposal_table, proposal['id'], 'missing_confirmation')

    table = PREFIX + 'run_events'
    sequences = defaultdict(set)
    for event in events.values():
        run = _ref(runs, event['run_id'], table, event['id'])
        view = {key: event[key] for key in ('run_id', 'seq', 'type', 'payload', 'created_at')}
        checked = _typed(schema.RunEventView, view, table, event['id'], 'invalid_event')
        if event['seq'] in sequences[run['id']]:
            _fail(table, event['id'], 'duplicate_event_seq')
        sequences[run['id']].add(event['seq'])
        payload = checked.payload.model_dump(mode='python')
        scope_row = {**run, 'id': event['id']}
        for field, records in (('plan_id', plans), ('work_item_id', work), ('proposal_id', proposals)):
            if payload.get(field) is not None:
                private_ref(records, payload[field], scope_row, table)
        if payload.get('run_item_id') is not None:
            item = _ref(items, payload['run_item_id'], table, event['id'])
            if item['run_id'] != run['id']:
                _fail(table, event['id'], 'event_item_run_mismatch')
            if payload.get('work_item_id') is not None and payload['work_item_id'] != item['work_item_id']:
                _fail(table, event['id'], 'event_item_work_mismatch')
        if payload.get('proposal_id') is not None and payload.get('work_item_id') is not None:
            if proposals[payload['proposal_id']]['source_work_item_id'] != payload['work_item_id']:
                _fail(table, event['id'], 'event_proposal_work_mismatch')
        for result_ref in payload.get('result_refs', []):
            object_ref(result_ref, scope_row, table)
    for run in runs.values():
        seqs = sequences[run['id']]
        # Unique positive seq values, count == max == event_seq imply 1..N.
        if len(seqs) != run['event_seq'] or max(seqs, default=0) != run['event_seq']:
            _fail(PREFIX + 'runs', run['id'], 'event_sequence_gap')

    for suffix, key_fields in (
        ('wake_events', ('signal_key',)),
        ('notifications', ('owner_id', 'store_id', 'source_key', 'kind')),
    ):
        table = PREFIX + suffix
        _unique(data[table], key_fields, table)
        for row in data[table].values():
            linked = []
            for field, records in (('plan_id', plans), ('proposal_id', proposals)):
                if row[field] is not None:
                    target = _ref(records, row[field], table, row['id'])
                    if target['store_id'] != row['store_id']:
                        _fail(table, row['id'], 'scope_mismatch')
                    if 'owner_id' in row and target['owner_id'] != row['owner_id']:
                        _fail(table, row['id'], 'scope_mismatch')
                    if row.get('session_id') is not None and row['session_id'] != target['session_id']:
                        _fail(table, row['id'], 'scope_mismatch')
                    linked.append(_scope(target))
            if len(set(linked)) > 1:
                _fail(table, row['id'], 'linked_scope_mismatch')
            if row['task_id'] is not None:
                task_ref(row['task_id'], row, table)
                # Historical task reassignment does not invalidate notifications.
            if suffix == 'wake_events':
                _typed(schema.WakeEventStatus, row['state'], table, row['id'])
                if row['object_ref'] is not None:
                    _typed(schema.BusinessObjectRef, row['object_ref'], table, row['id'])
                if row['source_ref'] is not None:
                    _typed(schema.JsonObject, row['source_ref'], table, row['id'])

    return {'assistant_runtime': 1,
            **{table.removeprefix('business_'): len(data[table]) for table in _COLUMNS}}
