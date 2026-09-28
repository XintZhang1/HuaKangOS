"""维修出厂与真实进出厂时间（gate_visit）适配器：原进出厂登记的只读投影。

- 只读 `GET /api/gate-visits/{key}`（reviewed catalog 内），不调用业务 command。
- 到厂、离厂、转维修接待是三件不同的事实：**计划日期、取消状态都不满足进出厂键**；
  到离厂时间一律取原纠正后的有效值（`voided` 为真即视为无效）。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

GATE_OBJECT_TYPE = 'gate_visit'
GATE_READ = 'GET /api/gate-visits/{key}'
GATE_CREATE = 'POST /api/gate-visits'
GATE_ACTION = 'POST /api/gate-visits/{key}/actions/{action}'
GATE_CORRECTION = 'POST /api/gate-visits/{key}/corrections'
GATE_CORRECTION_ACTION = 'POST /api/gate-visits/corrections/{key}/actions/{action}'
GATE_DEPARTURE = 'POST /api/gate-visits/repair-orders/{key}/departure'
GATE_ACTIONS = ('arrive', 'leave', 'cancel', 'handoff', 'correct')
GATE_RESULT_OPERATIONS = frozenset({GATE_READ, GATE_CREATE, GATE_ACTION, GATE_CORRECTION,
                                    GATE_CORRECTION_ACTION, GATE_DEPARTURE})
GATE_RECEIPT_OPERATIONS = frozenset({GATE_CREATE, GATE_ACTION, GATE_CORRECTION,
                                     GATE_CORRECTION_ACTION, GATE_DEPARTURE})
GATE_FACTS = ('gate.arrival_recorded', 'gate.departure_recorded', 'gate.handoff_recorded')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的进出厂登记不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class GateVisitAdapter(FlowCaseAdapter):
    """`object_type=gate_visit` 的原进出厂登记。"""

    name = 'gate_visit'
    object_types = (GATE_OBJECT_TYPE,)

    def _gate_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != GATE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原进出厂登记')
        return values

    async def _gate_detail(self, principal, ref):
        values = self._gate_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(GATE_READ, path_args={'key': values['id']},
                                                 query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此进出厂登记，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('customer_vehicle_id'))
                or type(data.get('status')) is not str or not data['status'].strip()):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._gate_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        gate_ref = BusinessObjectRef(type=GATE_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=gate_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data['status'],
                tasks=[],
                # 原详情只给岗位筛选后的动作名：可用性不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in (data.get('actions') or []) if type(key) is str],
                evidence_refs=[EvidenceRef(source_type='object', source_id=gate_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in GATE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='维修出厂登记未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._gate_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        gate_ref = BusinessObjectRef(type=GATE_OBJECT_TYPE, id=data['id'])
        from_gate = EvidenceRef(source_type='object', source_id=gate_ref,
                                native_version=version, observed_at=observed_at)
        voided = data.get('voided') is True

        if fact_key == 'gate.arrival_recorded':
            if not voided and type(data.get('arrived_at')) is str and data['arrived_at'].strip():
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_gate],
                                    reason='实际进厂时间：' + data['arrived_at'])
            if voided:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_gate],
                                    reason='原纠正已作废本次进厂事实，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_gate],
                                reason='原登记只有计划时间、尚无实际进厂事实，请到原页面核对到厂登记')

        if fact_key == 'gate.departure_recorded':
            if not voided and type(data.get('left_at')) is str and data['left_at'].strip():
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_gate],
                                    reason='实际离厂时间：' + data['left_at'])
            if voided:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_gate],
                                    reason='原纠正已作废本次离厂事实，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_gate],
                                reason='尚未有实际离厂事实（取消或计划都不满足），请到原页面核对')

        # gate.handoff_recorded：必须由原 GateHandoff 引用实际维修接待。
        for key in ('handoff_appointment_id', 'appointment_id'):
            if _positive_id(data.get(key)):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_gate],
                                    reason='已转维修接待（原接待引用存在）')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_gate],
                            reason='尚未转维修接待，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in GATE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('customer_vehicle_id'))):
            return []
        return [BusinessObjectRef(type=GATE_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in GATE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审的 flow receipt resolver 绑定（原 `gate_visit_service._execute` 摘要族）；
        # 冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['GATE_ACTION', 'GATE_ACTIONS', 'GATE_CORRECTION', 'GATE_CORRECTION_ACTION', 'GATE_CREATE',
           'GATE_DEPARTURE', 'GATE_FACTS', 'GATE_OBJECT_TYPE', 'GATE_READ', 'GATE_RECEIPT_OPERATIONS',
           'GATE_RESULT_OPERATIONS', 'GateVisitAdapter']
