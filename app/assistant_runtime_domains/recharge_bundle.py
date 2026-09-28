"""组合退回与履约（recharge_bundle）适配器：原充值组合单的只读投影。

- 只读 `GET /api/recharge-bundles/orders/{key}`（reviewed catalog 内），不调用业务 command。
- **API 的 key 是原 `Case.id`**（`RechargeBundleOrder.case_id` 指向它），绝不混用订单自己的 id。
- 购买、退回过账、取消是三件不同的事实；退回过账只在原详情确实带过账标记时判定，否则未知。
- 原 native version 取原 case 的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

RECHARGE_READ = 'GET /api/recharge-bundles/orders/{key}'
RECHARGE_CREATE = 'POST /api/recharge-bundles/orders'
RECHARGE_ACTION = 'POST /api/recharge-bundles/orders/{key}/actions/{action}'
RECHARGE_PURCHASES = 'GET /api/recharge-bundles/purchases'
RECHARGE_PURPOSES = ('purchase', 'refund')
RECHARGE_ACTIONS = ('approve', 'execute', 'cancel')
RECHARGE_RESULT_OPERATIONS = frozenset({RECHARGE_READ, RECHARGE_CREATE, RECHARGE_ACTION})
RECHARGE_RECEIPT_OPERATIONS = frozenset({RECHARGE_CREATE, RECHARGE_ACTION})
RECHARGE_FACTS = ('recharge_bundle.purchase_recorded', 'recharge_bundle.refund_posted',
                  'recharge_bundle.cancelled')
POSTING_KEYS = ('posting_id', 'posting', 'postings', 'posted_at')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的组合单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class RechargeBundleAdapter(FlowCaseAdapter):
    """`kind=recharge_bundle` 的原 Case；key 一律取原 Case.id。"""

    name = 'recharge_bundle'
    object_types = ('case',)

    async def _recharge_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(RECHARGE_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此组合单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        case = data.get('case') if type(data) is dict and type(data.get('case')) is dict else None
        if (case is None or data.get('truncated') or response.get('truncated')
                or not _positive_id(case.get('id')) or case.get('id') != values['id']
                or not isinstance(data.get('order'), dict)):
            _invalid()
        purpose = data['order'].get('purpose')
        if purpose is not None and purpose not in RECHARGE_PURPOSES:
            raise HTTPException(422, '这不是原充值组合业务单，请到对应业务页面办理')
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._recharge_detail(principal, ref)
        case, order = data['case'], data['order']
        observed_at = _now()
        version = case.get('version') if _positive_id(case.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=case['id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=case.get('number') if type(case.get('number')) is str else None,
                state=case.get('state') if type(case.get('state')) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in RECHARGE_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in RECHARGE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='组合退回与履约未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._recharge_detail(principal, ref)
        case = data['case']
        observed_at = _now()
        version = case.get('version') if _positive_id(case.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=case['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'recharge_bundle.purchase_recorded':
            purchase = data.get('purchase') if type(data.get('purchase')) is dict else None
            if purchase is None:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='本单还没有原组合购买结果，请在原页面核对')
            if _positive_id(purchase.get('id')):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='原购买结果已登记（至少一笔/一次）；一笔不代表整单结清')
            return _unknown(fact_key, '原购买结果缺少可识别标识，请在原页面核对')

        if fact_key == 'recharge_bundle.refund_posted':
            refund = data.get('refund') if type(data.get('refund')) is dict else None
            if refund is None:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='本单还没有原退款记录，请在原页面核对')
            markers = [key for key in POSTING_KEYS if refund.get(key)]
            if markers:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='原退款过账已登记；一笔不代表整单结清')
            return _unknown(fact_key, '原退款记录未提供过账标记（RechargeBundleRefundPosting），'
                                      '无法确认实际过账，请在原页面核对')

        # recharge_bundle.cancelled：原 cancel 成功结果与当前原订单状态必须一致。
        if case.get('state') == 'cancelled':
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='原组合单当前不是已取消状态，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in RECHARGE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        case = data.get('case') if type(data.get('case')) is dict else data
        if not _positive_id(case.get('id')):
            return []
        return [BusinessObjectRef(type='case', id=case['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in RECHARGE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['POSTING_KEYS', 'RECHARGE_ACTION', 'RECHARGE_ACTIONS', 'RECHARGE_CREATE',
           'RECHARGE_FACTS', 'RECHARGE_PURCHASES', 'RECHARGE_PURPOSES', 'RECHARGE_READ',
           'RECHARGE_RECEIPT_OPERATIONS', 'RECHARGE_RESULT_OPERATIONS', 'RechargeBundleAdapter']
