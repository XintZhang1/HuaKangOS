"""Original observation correction Cases and their append-only decision facts."""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef,
    BusinessObjectSnapshot, EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

CORRECTION_OBJECT_TYPE = 'observation_correction'
CORRECTION_READ = 'GET /api/observation-corrections/cases/{case_id}'
CORRECTION_CREATE = 'POST /api/observation-corrections/cases'
CORRECTION_ACTION = 'POST /api/observation-corrections/cases/{case_id}/actions/{action}'
CORRECTION_FACTS = ('correction.submitted', 'correction.approved')
CORRECTION_STATES = ('pending', 'approval', 'completed', 'rejected', 'cancelled')
CORRECTION_ACTIONS = ('submit', 'approve', 'reject', 'cancel')
CORRECTION_RESULT_OPERATIONS = frozenset({CORRECTION_CREATE, CORRECTION_ACTION})
CORRECTION_RECEIPT_OPERATIONS = CORRECTION_RESULT_OPERATIONS


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原日期里程纠正详情不完整，请到原页面重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class ObservationCorrectionAdapter(FlowCaseAdapter):
    name = 'observation_correction'
    object_types = (CORRECTION_OBJECT_TYPE,)

    def _correction_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != CORRECTION_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有真实主键的原日期里程纠正申请')
        return values

    async def _correction_detail(self, principal, ref):
        values = self._correction_ref(ref)
        if not _positive_id(getattr(principal, 'store_id', None)):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(CORRECTION_READ,
                path_args={'case_id': values['id']}, query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原业务不存在或当前账号不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取此纠正申请，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or response.get('truncated') or data.get('truncated')
                or not _positive_id(data.get('id')) or data['id'] != values['id']):
            _invalid()
        # The dedicated native GET checks Case kind/version and current visibility.
        # Its flat response has no generic kind/store_id/tasks to invent here.
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._correction_detail(principal, ref)
        try:
            actions = data.get('actions')
            if (data.get('state') not in CORRECTION_STATES or type(actions) is not list
                    or any(type(key) is not str or key not in CORRECTION_ACTIONS for key in actions)
                    or len(actions) != len(set(actions))):
                _invalid()
            observed_at = _now()
            native_version = data.get('version') if _positive_id(data.get('version')) else None
            case_ref = BusinessObjectRef(type=CORRECTION_OBJECT_TYPE, id=data['id'])
            return BusinessObjectSnapshot(ref=case_ref, native_version=native_version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data['state'], tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in actions],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                    native_version=native_version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    def _source_events(self, data, store_id):
        if not _positive_id(data.get('version')):
            raise ValueError('原版本无法核对')
        rows = data.get('events')
        if type(rows) is not list:
            raise ValueError('原完整纠正事件未披露')
        events, ids = {}, set()
        for row in rows:
            if (type(row) is not dict or not _positive_id(row.get('id'))
                    or row['id'] in ids or type(row.get('case_id')) is not int
                    or row['case_id'] != data['id'] or not _positive_id(row.get('actor_id'))
                    or type(row.get('store_id')) is not int or row['store_id'] != store_id
                    or row.get('action') not in {'create', *CORRECTION_ACTIONS}
                    or row['action'] in events):
                raise ValueError('原纠正事件来源不完整或不属于本单')
            if row['action'] in {'submit', 'approve', 'reject'} and not _positive_id(row.get('evidence_id')):
                raise ValueError('原提交或独立复核凭据缺失')
            ids.add(row['id'])
            events[row['action']] = row
        # Original API states and the unique append-only actions must agree before
        # complete absence can mean false. Missing/corrupt source remains unknown.
        expected = {
            'pending': ({'create'},),
            'approval': ({'create', 'submit'},),
            'completed': ({'create', 'submit', 'approve'},),
            'rejected': ({'create', 'submit', 'reject'},),
            'cancelled': ({'create', 'cancel'}, {'create', 'submit', 'cancel'}),
        }
        if data.get('state') not in expected or set(events) not in expected[data['state']]:
            raise ValueError('原状态与完整纠正事件不一致')
        if ('approve' in events
                and events['approve']['actor_id'] == events['create']['actor_id']):
            raise ValueError('原批准缺少独立经办来源')
        return events

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in CORRECTION_FACTS:
            try:
                return _unknown(fact_key, '日期里程纠正未登记此事实，请按原业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._correction_detail(principal, ref)
        try:
            events = self._source_events(data, getattr(principal, 'store_id', None))
        except (ValueError, TypeError, OverflowError):
            return _unknown(fact_key, '本单原提交或独立批准来源不完整，请到原纠正申请核对')
        evidence = EvidenceRef(source_type='object',
            source_id=BusinessObjectRef(type=CORRECTION_OBJECT_TYPE, id=data['id']),
            native_version=data.get('version') if _positive_id(data.get('version')) else None,
            observed_at=_now())
        if fact_key == 'correction.submitted':
            submitted = 'submit' in events
            return FactSnapshot(fact_key=fact_key, satisfied=submitted, evidence_refs=[evidence],
                reason='本单已按原凭据提交复核' if submitted else '本单尚未登记原提交复核事件')
        approved = 'approve' in events and data['state'] == 'completed'
        # The historical approval TX creates an Effect, but current.effect_id may
        # now belong to a later correction or insurance invalidation. Do not bind it.
        return FactSnapshot(fact_key=fact_key, satisfied=approved, evidence_refs=[evidence],
            reason='本单已独立批准，原观察保留历史；当前有效值以原车辆页为准' if approved
                   else '本单尚未登记原独立批准完成事实')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in CORRECTION_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        case = data.get('case')
        if type(case) is not dict or not _positive_id(case.get('id')):
            return []
        return [BusinessObjectRef(type=CORRECTION_OBJECT_TYPE, id=case['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in CORRECTION_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[],
                                 evidence_refs=[], reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['CORRECTION_ACTION', 'CORRECTION_ACTIONS', 'CORRECTION_CREATE', 'CORRECTION_FACTS',
           'CORRECTION_OBJECT_TYPE', 'CORRECTION_READ', 'CORRECTION_RECEIPT_OPERATIONS',
           'CORRECTION_RESULT_OPERATIONS', 'CORRECTION_STATES', 'ObservationCorrectionAdapter']
