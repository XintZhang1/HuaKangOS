"""整车运输异常（vehicle_transport_exception）适配器：原异常案的只读投影。

- 只读 `GET /api/vehicle-transport-exceptions/{key}`（reviewed catalog 内），不调用业务 command；
  **key 即原 `VehicleTransportException.id`**（与登记的对象类型一致）。
- 损失过账、实际找回接收、找回不可用是三件不同的事实：**计划找回不满足实际找到/接收键**；
  找回接收还要求**原 VIN 一致**；只在原详情确实提供对应记录时判定，否则未知。
- 原 native version 取原案 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

VTE_OBJECT_TYPE = 'vehicle_transport_exception'
VTE_READ = 'GET /api/vehicle-transport-exceptions/{key}'
VTE_CREATE = 'POST /api/vehicle-transport-exceptions'
VTE_ACTION = 'POST /api/vehicle-transport-exceptions/{key}/actions/{action}'
VTE_ACTIONS = ('observe', 'observe_found', 'plan_resume', 'plan_found', 'dispose', 'post_loss',
               'found_receive', 'found_unavailable')
VTE_RESULT_OPERATIONS = frozenset({VTE_READ, VTE_CREATE, VTE_ACTION})
VTE_RECEIPT_OPERATIONS = frozenset({VTE_CREATE, VTE_ACTION})
VTE_FACTS = ('vehicle_transport.loss_posted', 'vehicle_transport.found_received',
             'vehicle_transport.found_unavailable_recorded')
FACT_CONTAINERS = {'vehicle_transport.loss_posted': ('losses', 'loss', 'loss_postings'),
                   'vehicle_transport.found_received': ('found_receipts', 'found_receipt'),
                   'vehicle_transport.found_unavailable_recorded': ('found_unavailable',
                                                                    'found_unavailables')}
FACT_LABEL = {'vehicle_transport.loss_posted': '原运输损失过账',
              'vehicle_transport.found_received': '原实际找回接收',
              'vehicle_transport.found_unavailable_recorded': '原找回不可用登记'}
PLAN_ONLY = '原详情只看到计划（plan）：计划找回不满足实际找到或接收键，请在原页面核对'


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的运输异常案不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class VehicleTransportExceptionAdapter(FlowCaseAdapter):
    """`object_type=vehicle_transport_exception` 的原运输异常案；key 即原案 id。"""

    name = 'vehicle_transport_exception'
    object_types = (VTE_OBJECT_TYPE,)

    def _exception_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != VTE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原运输异常案')
        return values

    async def _detail(self, principal, ref):
        values = self._exception_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(VTE_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此运输异常案，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('transport_id') or data.get('case_id'))):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        exception_ref = BusinessObjectRef(type=VTE_OBJECT_TYPE, id=data['id'])
        state = data.get('status') or data.get('state')
        try:
            return BusinessObjectSnapshot(
                ref=exception_ref, native_version=version,
                display_number=(data.get('number') if type(data.get('number')) is str else
                                (data.get('vin') if type(data.get('vin')) is str else None)),
                state=state if type(state) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in VTE_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=exception_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _provided(data, containers):
        for container in containers:
            value = data.get(container)
            if isinstance(value, (list, dict)):
                return True
        return False

    @staticmethod
    def _first_record(data, containers):
        for container in containers:
            value = data.get(container)
            items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
            for item in items:
                if type(item) is dict and _positive_id(item.get('id')):
                    return item
        return None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in VTE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='整车运输异常未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        exception_ref = BusinessObjectRef(type=VTE_OBJECT_TYPE, id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=exception_ref,
                                native_version=version, observed_at=observed_at)
        containers = FACT_CONTAINERS[fact_key]

        if not self._provided(data, containers):
            if data.get('plan') or data.get('plan_id'):
                return _unknown(fact_key, PLAN_ONLY)
            return _unknown(fact_key, '原详情未提供' + FACT_LABEL[fact_key] + '明细（可能岗位不可见），'
                                      '无法确证，请在原页面核对')

        record = self._first_record(data, containers)
        if record is None:
            if data.get('plan') or data.get('plan_id'):
                # 只有计划：计划找回不满足实际找到/接收键 → 未知（不是明确未满足）
                return _unknown(fact_key, PLAN_ONLY)
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有' + FACT_LABEL[fact_key] + '记录，请在原页面核对')

        if fact_key == 'vehicle_transport.found_received':
            vin = data.get('vin')
            record_vin = record.get('vin')
            if type(vin) is not str or not vin.strip():
                return _unknown(fact_key, '原详情未提供 VIN，无法核对找回接收，请在原页面核对')
            if type(record_vin) is not str or record_vin.strip() != vin:
                return _unknown(fact_key, '原找回接收与本单 VIN 不一致，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                reason='已登记原实际找回接收（VIN 一致）；计划找回不等于实际接收')
        note = ('；过账不改变原实物状态' if fact_key == 'vehicle_transport.loss_posted'
                else '；登记找回不可用不构成找回完成')
        return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                            reason='已登记' + FACT_LABEL[fact_key] + '记录' + note)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in VTE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=VTE_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in VTE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['FACT_CONTAINERS', 'FACT_LABEL', 'PLAN_ONLY', 'VTE_ACTION', 'VTE_ACTIONS', 'VTE_CREATE',
           'VTE_FACTS', 'VTE_OBJECT_TYPE', 'VTE_READ', 'VTE_RECEIPT_OPERATIONS',
           'VTE_RESULT_OPERATIONS', 'VehicleTransportExceptionAdapter']
