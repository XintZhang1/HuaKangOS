"""Original authorized Flow reads projected into assistant object contracts.

An available action is not a submitted business operation. Case/task state and
receipt success never stand in for payment, handover or another domain fact.
"""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (
    AvailableAction, BusinessObjectRef, BusinessObjectSnapshot, EvidenceRef,
    FactSnapshot, ReceiptLookup, SubmissionSnapshot, TaskSnapshot,
)


FLOW_READ = 'GET /api/flow/cases/{case_id}'
FLOW_CREATE = 'POST /api/flow/cases'
FLOW_ACTION = 'POST /api/flow/cases/{case_id}/actions/{action}'
_RESULT_OPERATIONS = frozenset({FLOW_READ, FLOW_CREATE, FLOW_ACTION})
_RECEIPT_OPERATIONS = frozenset({FLOW_CREATE, FLOW_ACTION})
_NAVIGATION_KEYS = frozenset({
    'vehicle_transfer_id', 'transfer_id', 'reconciliation_id', 'clearing_id',
    'gate_visit_id', 'rework_id', 'appointment_id',
})
_TASK_FIELDS = ('id', 'case_id', 'key', 'title', 'role', 'assignee_id',
                'status', 'due_date', 'version')


def _invalid_record():
    raise HTTPException(502, '原业务返回的记录不完整或关联不一致，请稍后重新核对') from None


def _case_ref(ref):
    try:
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        result = BusinessObjectRef.model_validate(values)
    except (ValueError, TypeError):
        raise HTTPException(422, '请选择有效的原业务记录') from None
    if result.type != 'case':
        raise HTTPException(422, '此适配器只读取原 Case 记录')
    return result


def _positive_id(value):
    return type(value) is int and value > 0


def _optional_version(value):
    if value is not None and not _positive_id(value):
        _invalid_record()
    return value


def _optional_text(value):
    if value is not None:
        if type(value) is not str:
            _invalid_record()
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            _invalid_record()
    return value


def _response_data(response):
    if type(response) is not dict or type(response.get('status')) is not int:
        _invalid_record()
    status = response['status']
    if status in {401, 403, 404}:
        raise HTTPException(404, '原业务不存在或当前账号不可查看')
    if 400 <= status < 500:
        raise HTTPException(status, '原业务暂不能读取此记录，请到原页面核对')
    if not 200 <= status < 300:
        raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
    data = response.get('data')
    if type(data) is not dict or data.get('truncated') or response.get('truncated'):
        _invalid_record()
    return data


def _record(data, *, expected_id=None, expected_store=None, observed_at=None):
    if (expected_store is not None and type(data) is dict
            and data.get('store_id') != expected_store):
        raise HTTPException(404, '原业务不存在或当前账号不可查看')
    if (type(data) is not dict or not _positive_id(data.get('id'))
            or not _positive_id(data.get('store_id'))
            or type(data.get('kind')) is not str or not data['kind'].strip()
            or expected_id is not None and data['id'] != expected_id
            or expected_store is not None and data['store_id'] != expected_store):
        _invalid_record()
    _optional_text(data['kind'])
    actions, tasks = data.get('actions'), data.get('tasks')
    if type(actions) is not list or type(tasks) is not list:
        _invalid_record()
    native_data = data.get('data')
    if native_data is not None and type(native_data) is not dict:
        _invalid_record()
    # Only the original navigation helper's named, positive linked IDs survive.
    # This does not turn any case.data field into evidence of business completion.
    navigation = {key: value for key, value in (native_data or {}).items()
                  if key in _NAVIGATION_KEYS and _positive_id(value)}
    return {
        'id': data['id'], 'store_id': data['store_id'], 'kind': data['kind'],
        'flow_version': _optional_version(data.get('flow_version')),
        'version': _optional_version(data.get('version')),
        'number': _optional_text(data.get('number')),
        'state': _optional_text(data.get('state')),
        'tasks': deepcopy(tasks), 'actions': deepcopy(actions), 'data': navigation,
        'observed_at': observed_at,
    }


def _manual_route(record):
    from ..flow_navigation import case_entry_route
    from ..flow_specs import FLOW_CATALOGUES
    fallback = f"case/{record['id']}"
    if record['kind'] not in FLOW_CATALOGUES.get(record['flow_version'], {}):
        return fallback
    return case_entry_route(SimpleNamespace(
        id=record['id'], kind=record['kind'], flow_version=record['flow_version'], data=record['data']))


class FlowCaseAdapter:
    def __init__(self, *, native_reader, receipt_reader=None):
        if not callable(native_reader) or receipt_reader is not None and not callable(receipt_reader):
            raise TypeError('FlowCaseAdapter requires controlled readers')
        self._native_reader = native_reader
        self._receipt_reader = receipt_reader

    async def read_record(self, principal, ref):
        """Read once through the caller's controlled original-identity GET.

        The returned internal record proves kind/version for static dispatch;
        it is not a public response or a substitute for principal revalidation.
        """
        ref = _case_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(FLOW_READ, path_args={'case_id': ref.id}, query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原业务不存在或当前账号不可查看') from None
            raise
        data = _response_data(response)
        return _record(data, expected_id=ref.id, expected_store=store_id,
                       observed_at=datetime.now(timezone.utc))

    def snapshot_from_record(self, ref, record):
        """Project an internal record from read_record; this method grants no access."""
        ref = _case_ref(ref)
        if type(record) is not dict or not isinstance(record.get('observed_at'), datetime):
            _invalid_record()
        checked = _record(record, expected_id=ref.id, observed_at=record['observed_at'])
        observed_at = checked['observed_at']
        try:
            source = EvidenceRef(source_type='object', source_id=ref,
                                 native_version=checked['version'], observed_at=observed_at)
            tasks = []
            task_ids = set()
            for raw in checked['tasks']:
                if (type(raw) is not dict or not _positive_id(raw.get('id'))
                        or type(raw.get('case_id')) is not int or raw['case_id'] != ref.id
                        or raw['id'] in task_ids):
                    _invalid_record()
                task_ids.add(raw['id'])
                # Original task_info does not expose completion actor/time.
                # In particular updated_at is not a completion timestamp.
                tasks.append(TaskSnapshot.model_validate({key: deepcopy(raw[key]) for key in _TASK_FIELDS if key in raw}))
            actions = []
            action_keys = set()
            for raw in checked['actions']:
                if type(raw) is str:
                    key, availability, reason = raw, 'unknown', None
                elif type(raw) is dict and type(raw.get('key')) is str:
                    key = raw['key']
                    enabled = raw.get('enabled')
                    availability = ('enabled' if enabled else 'disabled') if type(enabled) is bool else 'unknown'
                    reason = _optional_text(raw.get('reason'))
                else:
                    _invalid_record()
                _optional_text(key)
                if not key.strip() or key in action_keys:
                    _invalid_record()
                action_keys.add(key)
                actions.append(AvailableAction(action_key=key, availability=availability,
                                               reason=reason, evidence_refs=[source]))
            return BusinessObjectSnapshot(
                ref=ref, native_version=checked['version'], display_number=checked['number'],
                state=checked['state'], tasks=tasks, available_actions=actions,
                evidence_refs=[source] + [EvidenceRef(source_type='task', source_id=task.id,
                    native_version=task.version, observed_at=observed_at) for task in tasks],
                manual_route=_manual_route(checked), observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid_record()

    async def read_snapshot(self, principal, ref):
        return self.snapshot_from_record(ref, await self.read_record(principal, ref))

    def extract_result(self, operation_id, response):
        """Only native top-level case responses can bind a result reference."""
        if (type(operation_id) is not str or operation_id not in _RESULT_OPERATIONS or type(response) is not dict
                or type(response.get('status')) is not int or not 200 <= response['status'] < 300
                or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('store_id'))
                or type(data.get('kind')) is not str or not data['kind'].strip()
                or any(data.get(key) is not None and not _positive_id(data[key])
                       for key in ('version', 'flow_version'))):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def fact_snapshot(self, principal, ref, fact_key):
        _case_ref(ref)
        # Generic Case has no registered domain fact keys. State text, an empty
        # task list and action availability are never promoted to fact evidence.
        try:
            return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                reason='通用原单未登记此事实，请按对应业务能力核对')
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '事实标识不正确') from None

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in _RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=datetime.now(timezone.utc),
                                 object_refs=[], evidence_refs=[], reason_code='receipt_family_not_registered')
        # The bound reader must resolve the owned durable Proposal/confirmation;
        # this DTO never permits a free actor/request_id database query.
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid_record()
