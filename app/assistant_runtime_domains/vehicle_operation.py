"""整车库位及出退库作业（vehicle_operation）适配器：原车辆作业单的只读投影。

- 只读 `GET /api/vehicle-operations/orders/{case_id}`（reviewed catalog 内），不调用业务 command。
- 发出、接收、检查是三件不同的事实：检查记录存在不等于检查合格；
  未知库位或不可配车辆不补默认值，也不改 `Vehicle.store_id`。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import BusinessObjectRef, EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot
from .flow_case import FlowCaseAdapter, _positive_id

OPERATION_KIND = 'vehicle_operations'
OPERATION_FLOW_VERSION = 2
OPERATION_KINDS = ('locate', 'local_move', 'other_out', 'other_return', 'customer_return')
OPERATION_READ = 'GET /api/vehicle-operations/orders/{case_id}'
OPERATION_CREATE = 'POST /api/vehicle-operations/orders'
OPERATION_ACTION = 'POST /api/vehicle-operations/orders/{case_id}/actions/{action}'
OPERATION_RESULT_OPERATIONS = frozenset({OPERATION_READ, OPERATION_CREATE, OPERATION_ACTION})
OPERATION_RECEIPT_OPERATIONS = frozenset({OPERATION_CREATE, OPERATION_ACTION})
OPERATION_FACTS = ('vehicle_operation.dispatch_recorded', 'vehicle_operation.accept_recorded',
                   'vehicle_operation.inspection_recorded')
# 原位置流水用 inventory_delta 的正负表示实物进出；不按名称猜动作。
OPERATION_ACTIONS = ('approve', 'reject_request', 'cancel', 'locate', 'dispatch',
                     'accept', 'inspect', 'disposition', 'intake')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的车辆作业单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class VehicleOperationAdapter(FlowCaseAdapter):
    """`kind == 'vehicle_operations'`、`flow_version == 2` 的原车辆作业单。"""

    name = 'vehicle_operation'
    object_types = ('case',)

    async def _operation_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id')):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(OPERATION_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此作业单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if data.get('kind') not in (None,) + OPERATION_KINDS:
            raise HTTPException(422, '这不是原整车库位或出入库作业单，请到对应业务页面办理')
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or data.get('kind') not in OPERATION_KINDS):
            _invalid()
        # 未知库位或不可配车辆不补默认值：缺少来源车辆即视为记录不可用。
        if not _positive_id(data.get('source_vehicle_id')):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._operation_detail(principal, ref)
        record = {
            'id': data['id'], 'store_id': getattr(principal, 'store_id', None), 'kind': OPERATION_KIND,
            'flow_version': OPERATION_FLOW_VERSION, 'version': data.get('version'),
            'number': data.get('number'), 'state': data.get('state'),
            'tasks': data.get('tasks') or [],
            'actions': [key for key in (data.get('actions') or []) if type(key) is str],
            'data': {}, 'observed_at': _now(),
        }
        if not isinstance(record['tasks'], list):
            _invalid()
        return self.snapshot_from_record(ref, record)

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in OPERATION_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='整车库位与出入库未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._operation_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        entries = data.get('entries') if isinstance(data.get('entries'), list) else []
        inspections = data.get('inspections') if isinstance(data.get('inspections'), list) else []

        if fact_key == 'vehicle_operation.dispatch_recorded':
            # 实际发出必须由本单原位置流水的负数库存变化确证；状态或动作可用性都不算。
            for entry in entries:
                if (type(entry) is dict and type(entry.get('inventory_delta')) is int
                        and entry['inventory_delta'] < 0):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有实际发出的位置流水，请在原页面核对发车进度')

        if fact_key == 'vehicle_operation.accept_recorded':
            # 接收必须有目的库位的正数库存变化流水。
            for entry in entries:
                if (type(entry) is dict and type(entry.get('inventory_delta')) is int
                        and entry['inventory_delta'] > 0):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='目的库位还没有实际接收流水，请在原页面核对接收进度')

        # vehicle_operation.inspection_recorded：只证明已登记实车检查，绝不解释为合格。
        for inspection in inspections:
            if type(inspection) is dict and _positive_id(inspection.get('id')):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已登记实车检查；是否合格以原检查结论与处置决定为准')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有实车检查记录，请在原页面核对检查进度')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in OPERATION_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or data.get('kind') not in OPERATION_KINDS):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in OPERATION_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执沿 `vehicle_operation_` 前缀摘要；冻结快照与 request_id 由调用方提供。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['OPERATION_ACTION', 'OPERATION_ACTIONS', 'OPERATION_CREATE', 'OPERATION_FACTS',
           'OPERATION_FLOW_VERSION', 'OPERATION_KIND', 'OPERATION_KINDS', 'OPERATION_READ',
           'OPERATION_RECEIPT_OPERATIONS', 'OPERATION_RESULT_OPERATIONS', 'VehicleOperationAdapter']
