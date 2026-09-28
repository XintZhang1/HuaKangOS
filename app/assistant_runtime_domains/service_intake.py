"""维修预约与实际到店接待（service_intake）适配器：原预约的只读投影。

目录规则（M7 共同合同第 4 条，实测 `business_assistant_gateway._operations()`）：
写操作须在 reviewed catalog 内；GET 由活跃路由发现并受 domain/closed/denied/body 过滤与调用时授权。
本项三条 operation 均已登记。

- 只读 `GET /api/service-intake/appointments/{key}`；不调用业务 command、不占用资源。
- 到店、转维修单、取消是三件不同的事实：**资源占用不等于实际到店**，
  `no_show` 不等于 `cancelled`，有预约不等于已转维修。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

APPOINTMENT_OBJECT_TYPE = 'service_appointment'
INTAKE_READ = 'GET /api/service-intake/appointments/{key}'
INTAKE_CREATE = 'POST /api/service-intake/appointments'
INTAKE_ACTION = 'POST /api/service-intake/appointments/{key}/actions/{action}'
INTAKE_ACTIONS = ('reschedule', 'cancel', 'no_show', 'arrive', 'leave', 'convert')
INTAKE_RESULT_OPERATIONS = frozenset({INTAKE_READ, INTAKE_CREATE, INTAKE_ACTION})
INTAKE_RECEIPT_OPERATIONS = frozenset({INTAKE_CREATE, INTAKE_ACTION})
INTAKE_FACTS = ('intake.arrival_recorded', 'intake.repair_converted', 'intake.cancelled')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的预约记录不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class ServiceIntakeAdapter(FlowCaseAdapter):
    """`object_type=service_appointment` 的原维修预约；动作走已评审 POST。"""

    name = 'service_intake'
    object_types = (APPOINTMENT_OBJECT_TYPE,)

    def _appointment_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != APPOINTMENT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原维修预约')
        return values

    async def _appointment_detail(self, principal, ref):
        values = self._appointment_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(INTAKE_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此预约，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if not _positive_id(data.get('id')) or data.get('id') != values['id']:
            _invalid()
        # 未知车辆不补默认值：预约必须带真实客户车辆引用。
        if not _positive_id(data.get('customer_vehicle_id')):
            _invalid()
        for key in ('repair_case_id', 'status'):
            pass
        return data

    async def read_snapshot(self, principal, ref):
        # 预约不是 Case：直接投影统一快照 DTO。
        data = await self._appointment_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        appointment_ref = BusinessObjectRef(type=APPOINTMENT_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=appointment_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('status') if type(data.get('status')) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜，统一未知（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in INTAKE_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=appointment_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in INTAKE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='维修预约未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._appointment_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        appointment_ref = BusinessObjectRef(type=APPOINTMENT_OBJECT_TYPE, id=data['id'])
        from_appointment = EvidenceRef(source_type='object', source_id=appointment_ref,
                                       native_version=version, observed_at=observed_at)

        if fact_key == 'intake.arrival_recorded':
            # 必须由原 ArrivalFact 确证（详情里的实际到店时间）；资源占用不算。
            arrived_at = data.get('arrived_at')
            if type(arrived_at) is not str or not arrived_at.strip():
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_appointment],
                                    reason='原预约还没有实际到店事实，请在原页面核对到店登记')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_appointment],
                                reason='到店时间：' + arrived_at)

        if fact_key == 'intake.repair_converted':
            # 必须与原维修单引用吻合；有预约或有资源占用都不算已转维修。
            repair_case_id = data.get('repair_case_id')
            if not _positive_id(repair_case_id):
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_appointment],
                                    reason='原预约尚未转成维修单，请在原页面核对转单进度')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[
                EvidenceRef(source_type='object', source_id=BusinessObjectRef(type='case', id=repair_case_id),
                            native_version=None, observed_at=observed_at),
                from_appointment,
            ])

        # intake.cancelled：重读原预约状态确为已取消；no_show（未到）不是取消。
        status = data.get('status')
        if status == 'cancelled':
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_appointment])
        if status == 'no_show':
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_appointment],
                                reason='原预约记为未到（no_show），不等于已取消')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_appointment],
                            reason='原预约当前不是已取消状态，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in INTAKE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('customer_vehicle_id'))):
            return []
        return [BusinessObjectRef(type=APPOINTMENT_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in INTAKE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `IntakeReceipt`（`request_digest('intake_'+operation, payload)`）；
        # 冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['APPOINTMENT_OBJECT_TYPE', 'INTAKE_ACTION', 'INTAKE_ACTIONS', 'INTAKE_CREATE', 'INTAKE_FACTS',
           'INTAKE_READ', 'INTAKE_RECEIPT_OPERATIONS', 'INTAKE_RESULT_OPERATIONS', 'ServiceIntakeAdapter']
