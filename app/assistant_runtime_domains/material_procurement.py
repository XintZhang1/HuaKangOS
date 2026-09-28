"""物资采购、预付与仓储（material_procurement）适配器：原采购 Case 的只读投影。

- 只读 `GET /api/procurement/orders/{case_id}`（reviewed catalog 内），不调用业务 command。
- 实收、退回过账、实际付款是三件不同的事实：**关闭收货余量不满足实收键**，
  **一笔不等于全部行完成**；付款必须有原实际付款来源，金额可见性受限时返回未知。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

PROC_READ = 'GET /api/procurement/orders/{case_id}'
PROC_CREATE = 'POST /api/procurement/orders'
PROC_ACTION = 'POST /api/procurement/orders/{case_id}/actions/{action}'
PROC_ACTIONS = ('approve', 'close_receiving', 'receive', 'pay', 'return_request',
                'return_approve', 'return_dispatch', 'refund')
PROC_RESULT_OPERATIONS = frozenset({PROC_READ, PROC_CREATE, PROC_ACTION})
PROC_RECEIPT_OPERATIONS = frozenset({PROC_CREATE, PROC_ACTION})
PROC_FACTS = ('procurement.receipt_recorded', 'procurement.return_posted',
              'procurement.payment_recorded')
# 原退货 posting 指向原收货批次的引用键（未登记形状一律未知，不猜）。
RETURN_REFERENCE_KEYS = ('receipt_id', 'dispatch_id', 'source_receipt_id', 'original_id')
PAYMENT_SOURCE_KEYS = ('cash_id', 'account_id', 'reference', 'original_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的采购单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _items(data, name):
    value = data.get(name)
    return [item for item in value if type(item) is dict] if isinstance(value, list) else []


class MaterialProcurementAdapter(FlowCaseAdapter):
    """`kind=procurement` 的原采购 Case；事实只经单次受控 GET。"""

    name = 'material_procurement'
    object_types = ('case',)

    async def _proc_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(PROC_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此采购单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('store_id')) or data['store_id'] != store_id
                or not isinstance(data.get('lines'), list)
                or not isinstance(data.get('receipts'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._proc_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('state') if type(data.get('state')) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in PROC_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in PROC_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='物资采购未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._proc_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'procurement.receipt_recorded':
            # 必须同时有原 PurchaseReceipt 与原 StockMove；关闭收货余量不算实收。
            for receipt in _items(data, 'receipts'):
                if _positive_id(receipt.get('id')) and _positive_id(receipt.get('stock_move_id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原实收（收货 + 库存移动）；一笔不等于全部行完成')
            if data.get('receiving_closed'):
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='原单已关闭收货余量但尚未有实收入库，关闭收货不满足实收键')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原实收入库记录，请在原页面核对收货进度')

        if fact_key == 'procurement.return_posted':
            returns = _items(data, 'returns')
            if not returns:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='本单还没有原退货记录，请在原页面核对退货进度')
            for posting in returns:
                if any(_positive_id(posting.get(key)) for key in RETURN_REFERENCE_KEYS):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原退货过账且指向原收货批次；一笔不等于全部行完成')
            return _unknown(fact_key, '原退货记录未提供指向原收货批次的引用，请在原页面核对')

        # procurement.payment_recorded：必须有原 PurchasePayment 的实际付款来源；
        # 应付金额或收货都不满足本键；金额岗位不可见时未知。
        payments = _items(data, 'payments')
        if not payments:
            return _unknown(fact_key, '原详情未提供付款明细（需财务岗位可见性），请在原单核对实际付款')
        for payment in payments:
            if _positive_id(payment.get('id')) and any(
                    payment.get(key) for key in PAYMENT_SOURCE_KEYS):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已存在原实际付款来源（单笔）；一笔不等于整单付清')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有带实际付款来源的原付款记录，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in PROC_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('store_id'))):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in PROC_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族沿 `procurement_` 前缀摘要；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['PAYMENT_SOURCE_KEYS', 'PROC_ACTION', 'PROC_ACTIONS', 'PROC_CREATE', 'PROC_FACTS',
           'PROC_READ', 'PROC_RECEIPT_OPERATIONS', 'PROC_RESULT_OPERATIONS', 'RETURN_REFERENCE_KEYS',
           'MaterialProcurementAdapter']
