"""Original repair package purchases, with exact authorized detail and facts.

Issuance, a local capture and a real refund are distinct. Zero-price component
returns record cancellation of that component without inventing a cash refund.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id, _response_data

PACKAGE_OBJECT_TYPE = 'package_purchase'
PACKAGE_MEMBER_PURCHASES = 'GET /api/repair-packages/members/{key}/purchases'
PACKAGE_READ = 'GET /api/repair-packages/purchases/{key}'
PACKAGE_RULES = 'GET /api/repair-packages/rules'
PACKAGE_CREATE = 'POST /api/repair-packages/purchases'
PACKAGE_ORDER_CAPTURE = 'POST /api/repair-packages/orders/{key}/capture'
PACKAGE_ORDER_QUOTE = 'POST /api/repair-packages/orders/{key}/quote'
PACKAGE_ACTION = 'POST /api/repair-packages/purchases/{key}/actions/{action}'
PACKAGE_REFUND_ACTION = 'POST /api/repair-packages/refunds/{key}/actions/{action}'
PACKAGE_ACTIONS = ('authorize', 'issue', 'cancel', 'refund_request')
PACKAGE_RESULT_OPERATIONS = frozenset({PACKAGE_CREATE, PACKAGE_ORDER_CAPTURE, PACKAGE_ORDER_QUOTE,
                                       PACKAGE_ACTION, PACKAGE_REFUND_ACTION})
PACKAGE_RECEIPT_OPERATIONS = frozenset({PACKAGE_CREATE, PACKAGE_ORDER_CAPTURE, PACKAGE_ORDER_QUOTE,
                                        PACKAGE_ACTION, PACKAGE_REFUND_ACTION})
PACKAGE_FACTS = ('repair_package.issued', 'repair_package.capture_recorded',
                 'repair_package.refund_paid')
PURCHASE_STATES = ('proposed', 'authorized', 'issued', 'cancelled')
REFUND_STATES = ('requested', 'approved', 'rejected', 'cancelled', 'executed')


def _now():
    return datetime.now(timezone.utc)


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _invalid():
    raise HTTPException(502, '原业务返回的套餐记录不完整或关联不一致，请重新核对') from None


class RepairPackageAdapter(FlowCaseAdapter):
    """`package_purchase` is the original purchase ID, never a repair Case ID."""

    name = 'repair_package'
    object_types = (PACKAGE_OBJECT_TYPE,)

    def _purchase_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != PACKAGE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原套餐购买记录')
        return values

    async def _purchase_detail(self, principal, ref):
        values = self._purchase_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(PACKAGE_READ,
                path_args={'key':values['id']}, query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401,403,404}:
                raise HTTPException(404, '原业务不存在或当前账号不可查看') from None
            raise
        data = _response_data(response)
        if (not _positive_id(data.get('id')) or data['id'] != values['id']
                or not _positive_id(data.get('member_id'))
                or data.get('version') is not None and not _positive_id(data['version'])
                or data.get('status') not in PURCHASE_STATES
                or type(data.get('lots')) is not list
                or type(data.get('capture_entries')) is not list):
            _invalid()
        lot_ids = set()
        for lot in data['lots']:
            if (type(lot) is not dict or not _positive_id(lot.get('id'))
                    or lot['id'] in lot_ids or not _positive_id(lot.get('quantity_milli'))):
                _invalid()
            lot_ids.add(lot['id'])
        seen = set()
        for entry in data['capture_entries']:
            if (type(entry) is not dict or not _positive_id(entry.get('id'))
                    or entry['id'] in seen or not _positive_id(entry.get('lot_id'))
                    or entry['lot_id'] not in lot_ids or not _positive_id(entry.get('store_id'))
                    or entry['store_id'] != store_id or not _positive_id(entry.get('case_id'))
                    or entry.get('purpose') != 'capture' or not _positive_id(entry.get('hold_id'))
                    or not _positive_id(entry.get('quantity_milli'))):
                _invalid()
            seen.add(entry['id'])
        if 'refunds' in data:
            if type(data['refunds']) is not list:
                _invalid()
            seen = set()
            for refund in data['refunds']:
                if (type(refund) is not dict or not _positive_id(refund.get('id'))
                        or refund['id'] in seen or not _positive_id(refund.get('purchase_id'))
                        or refund['purchase_id'] != data['id']):
                    _invalid()
                seen.add(refund['id'])
        return data

    @staticmethod
    def _evidence(data):
        ref = BusinessObjectRef(type=PACKAGE_OBJECT_TYPE, id=data['id'])
        source = EvidenceRef(source_type='object', source_id=ref,
            native_version=data.get('version'), observed_at=_now())
        return ref, source

    async def read_snapshot(self, principal, ref):
        data = await self._purchase_detail(principal, ref)
        purchase_ref, source = self._evidence(data)
        return BusinessObjectSnapshot(ref=purchase_ref, native_version=data.get('version'),
            display_number=data.get('name') if type(data.get('name')) is str else None,
            state=data['status'], tasks=[],
            available_actions=[AvailableAction(action_key=key,availability='unknown')
                for key in PACKAGE_ACTIONS], evidence_refs=[source],
            manual_route='repair-packages', observed_at=source.observed_at)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._purchase_ref(ref)
        if fact_key not in PACKAGE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='维修套餐未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._purchase_detail(principal, ref)
        _, source = self._evidence(data)
        if fact_key == 'repair_package.issued':
            if data['status'] != 'issued':
                return FactSnapshot(fact_key=fact_key,satisfied=False,evidence_refs=[source],
                    reason='原购买尚未实际发行；授权或报价不代表发行')
            if not data['lots'] or 'cash_id' in data and not _positive_id(data['cash_id']):
                return _unknown(fact_key, '原发行状态缺少对应组件或可见原收款来源，请核对')
            return FactSnapshot(fact_key=fact_key,satisfied=True,evidence_refs=[source],
                reason='原购买已实际发行且有原组件批次；不代表组件已履约')
        if fact_key == 'repair_package.capture_recorded':
            recorded = bool(data['capture_entries'])
            return FactSnapshot(fact_key=fact_key,satisfied=recorded,evidence_refs=[source],
                reason=('已有本店原组件核销流水；仅证明至少一笔，不代表全部履约或结清'
                        if recorded else '该购买当前没有本店原组件核销流水'))
        # Other stores cannot see issuer refunds; missing money evidence stays unknown.
        refunds = data.get('refunds')
        if type(refunds) is not list:
            return _unknown(fact_key, '当前门店看不到原发行店退款事实，请回原发行店核对')
        unresolved = False
        zero_price_return = False
        for refund in refunds:
            if (refund.get('status') not in REFUND_STATES
                    or type(refund.get('amount_cents')) is not int or refund['amount_cents'] < 0):
                unresolved = True
                continue
            if refund['status'] != 'executed':
                continue
            if refund['amount_cents'] == 0 and refund.get('cash_id') is None:
                zero_price_return = True
                continue
            if refund['amount_cents'] > 0 and _positive_id(refund.get('cash_id')):
                return FactSnapshot(fact_key=fact_key,satisfied=True,evidence_refs=[source],
                    reason='已有原实际退款及对应现金来源；仅证明至少一笔，不代表整份购买已退完')
            unresolved = True
        if unresolved:
            return _unknown(fact_key, '原退款缺少当前岗位可核对的实际现金来源或完整结果，请核对')
        return FactSnapshot(fact_key=fact_key,satisfied=False,evidence_refs=[source],
            reason=('原零对价组件已退回注销，但没有实际现金退款；不满足实际退款事实'
                    if zero_price_return else '尚无原实际现金退款；申请或批准不代表实际办理'))

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in PACKAGE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        # Quote/capture return a repair Case, never a purchase object.
        if operation_id in {PACKAGE_ORDER_QUOTE, PACKAGE_ORDER_CAPTURE}:
            return []
        # refund_request on the purchase action route returns a refund, too.
        if operation_id == PACKAGE_REFUND_ACTION or operation_id == PACKAGE_ACTION and 'purchase_id' in data:
            purchase_id = data.get('purchase_id')
        else:
            if not _positive_id(data.get('member_id')) or data.get('status') not in PURCHASE_STATES:
                return []
            purchase_id = data.get('id')
        if not _positive_id(purchase_id):
            return []
        return [BusinessObjectRef(type=PACKAGE_OBJECT_TYPE, id=purchase_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in PACKAGE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, '原业务返回的套餐回执不完整，请稍后重新核对') from None


__all__ = ['PACKAGE_ACTION', 'PACKAGE_ACTIONS', 'PACKAGE_CREATE', 'PACKAGE_FACTS',
           'PACKAGE_MEMBER_PURCHASES', 'PACKAGE_OBJECT_TYPE', 'PACKAGE_ORDER_CAPTURE',
           'PACKAGE_ORDER_QUOTE', 'PACKAGE_RECEIPT_OPERATIONS', 'PACKAGE_REFUND_ACTION',
           'PACKAGE_RESULT_OPERATIONS', 'PACKAGE_READ', 'PACKAGE_RULES', 'RepairPackageAdapter']
