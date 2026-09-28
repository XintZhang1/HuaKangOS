"""整车采购逐 VIN 进度（vehicle_purchase）适配器：原采购单的只读投影。

- 只读 `GET /api/vehicle-procurement/orders/{case_id}`（reviewed catalog 内），不调用业务 command。
- 发运、验收入库、付款是三件不同的事实：一张总卡成功不代表整批齐套，
  三个事实键都只证明“至少一笔对应事实”，不声明整批完成。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import BusinessObjectRef, EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot
from .flow_case import FlowCaseAdapter, _positive_id

PURCHASE_KIND = 'vehicle_procurement'
PURCHASE_FLOW_VERSION = 2
PURCHASE_READ = 'GET /api/vehicle-procurement/orders/{case_id}'
PURCHASE_CREATE = 'POST /api/vehicle-procurement/orders'
PURCHASE_ACTION = 'POST /api/vehicle-procurement/orders/{case_id}/actions/{action}'
PURCHASE_RESULT_OPERATIONS = frozenset({PURCHASE_READ, PURCHASE_CREATE, PURCHASE_ACTION})
PURCHASE_RECEIPT_OPERATIONS = frozenset({PURCHASE_CREATE, PURCHASE_ACTION})
PURCHASE_FACTS = ('vehicle_purchase.shipment_recorded', 'vehicle_purchase.receipt_recorded',
                  'vehicle_purchase.payment_recorded')
PURCHASE_ACTIONS = ('approve', 'request_funds', 'pay', 'ship', 'receive',
                    'return_request', 'return_approve', 'return_dispatch', 'refund')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的采购单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class VehiclePurchaseAdapter(FlowCaseAdapter):
    """`kind == 'vehicle_procurement'`、`flow_version == 2` 的原采购单。"""

    name = 'vehicle_purchase'
    object_types = ('case',)

    async def _purchase_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id')):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(PURCHASE_READ, path_args={'case_id': values['id']},
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
        if status == 403:
            raise HTTPException(403, '当前岗位不能读取整车采购，请到原页面办理')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取此采购单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if not _positive_id(data.get('store_id')) or data['store_id'] != store_id:
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        if data.get('flow_version') != PURCHASE_FLOW_VERSION:
            raise HTTPException(404, '整车采购单不存在或版本不支持')
        if not _positive_id(data.get('id')) or data.get('id') != values['id']:
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._purchase_detail(principal, ref)
        record = {
            'id': data['id'], 'store_id': data['store_id'], 'kind': PURCHASE_KIND,
            'flow_version': PURCHASE_FLOW_VERSION, 'version': data.get('version'),
            'number': data.get('number'), 'state': data.get('state'),
            'tasks': data.get('tasks') or [],
            'actions': [key for key in (data.get('actions') or []) if type(key) is str],
            'data': {}, 'observed_at': _now(),
        }
        if not isinstance(record['tasks'], list):
            _invalid()
        return self.snapshot_from_record(ref, record)

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in PURCHASE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='整车采购未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._purchase_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        shipments = data.get('shipments') if isinstance(data.get('shipments'), list) else []
        receipts = data.get('receipts') if isinstance(data.get('receipts'), list) else []
        payments = data.get('payments') if isinstance(data.get('payments'), list) else []

        if fact_key == 'vehicle_purchase.shipment_recorded':
            # 至少一笔原 VehiclePurchaseShipment；不代表整批已发运。
            for shipment in shipments:
                if type(shipment) is dict and _positive_id(shipment.get('id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None,
                                        evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原发运记录，请在原页面核对发运进度')

        if fact_key == 'vehicle_purchase.receipt_recorded':
            # 必须有原 VehiclePurchaseReceipt 且带 shipment/vehicle 引用；逐 VIN 验收，不合并成一张总卡。
            for receipt in receipts:
                if (type(receipt) is dict and _positive_id(receipt.get('id'))
                        and _positive_id(receipt.get('shipment_id')) and _positive_id(receipt.get('vehicle_id'))):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None,
                                        evidence_refs=[from_case])
            if receipts:
                return _unknown(fact_key, '原验收记录缺少发运或车辆引用，请在原页面逐 VIN 核对')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原验收入库记录，请在原页面逐 VIN 核对')

        # vehicle_purchase.payment_recorded：必须有 direction=out 的原付款记录；
        # 付款申请或价格版本都不满足本键。岗位看不到金额时按未知处理，不猜。
        for payment in payments:
            if (type(payment) is dict and _positive_id(payment.get('id'))
                    and payment.get('direction') == 'out'):
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
        if not payments and data.get('funds_requests'):
            return _unknown(fact_key, '原付款明细需要财务或管理岗位可见性，请在原单核对实际付款')
        if not payments:
            return _unknown(fact_key, '原详情未提供付款明细，请在原单核对实际付款')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有原实际付款记录，请在原页面核对付款进度')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in PURCHASE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('store_id'))
                or data.get('flow_version') != PURCHASE_FLOW_VERSION):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in PURCHASE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执沿 vehicle_procurement_service.execute 的 `vehicle_purchase_` 前缀摘要；
        # VehiclePurchaseReceipt 只是实物事实，不当作提交回执。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['PURCHASE_ACTION', 'PURCHASE_ACTIONS', 'PURCHASE_CREATE', 'PURCHASE_FACTS',
           'PURCHASE_FLOW_VERSION', 'PURCHASE_KIND', 'PURCHASE_READ',
           'PURCHASE_RECEIPT_OPERATIONS', 'PURCHASE_RESULT_OPERATIONS', 'VehiclePurchaseAdapter']
