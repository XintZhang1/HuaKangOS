"""物资采购预付（procurement_prepayment）适配器：原采购 Case 的预付款只读投影。

- 只读 `GET /api/procurement/orders/{case_id}`（reviewed catalog 内），不调用业务 command；
  预付款动作挂在原采购动作上（prepay_request/prepay_approve/prepay_reject/prepay_cancel/
  prepay_expire/prepay_pay），仍由原接口校验岗位与状态。
- 批准、实际预付、过期是三件不同的事实：**当前日期过期不制造业务已过账事实**；
  每笔事实保留申请 ID，**不能串到另一申请**。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

PREPAY_READ = 'GET /api/procurement/orders/{case_id}'
PREPAY_ACTION = 'POST /api/procurement/orders/{case_id}/actions/{action}'
PREPAY_ACTIONS = ('prepay_request', 'prepay_approve', 'prepay_reject', 'prepay_cancel',
                  'prepay_expire', 'prepay_pay')
PREPAY_RESULT_OPERATIONS = frozenset({PREPAY_READ, PREPAY_ACTION})
PREPAY_RECEIPT_OPERATIONS = frozenset({PREPAY_ACTION})
PREPAY_FACTS = ('prepayment.approval_recorded', 'prepayment.disbursement_recorded',
                'prepayment.expiration_recorded')
DECISION_APPROVE = 'approve'
DECISION_EXPIRE = 'expire'


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的预付款数据不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _requests(data):
    value = data.get('requests')
    return [item for item in value if type(item) is dict] if isinstance(value, list) else []


def _decisions(request):
    value = request.get('decisions')
    return [item for item in value if type(item) is dict] if isinstance(value, list) else []


class ProcurementPrepaymentAdapter(FlowCaseAdapter):
    """`kind=procurement` 的原采购 Case；预付款事实按原申请逐笔判定。"""

    name = 'procurement_prepayment'
    object_types = ('case',)

    async def _prepay_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(PREPAY_READ, path_args={'case_id': values['id']},
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
                or not isinstance(data.get('requests'), list)):
            # 采购详情未挂预付面（原服务对未启用门店返回 None）→ 缺少申请列表即视为不完整。
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._prepay_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('state') if type(data.get('state')) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in PREPAY_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in PREPAY_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='物资采购预付未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._prepay_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        requests = _requests(data)
        if not requests:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原预付款申请，请在原页面核对申请进度')

        if fact_key == 'prepayment.approval_recorded':
            for request in requests:
                for decision in _decisions(request):
                    if decision.get('action') == DECISION_APPROVE:
                        return FactSnapshot(
                            fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                            reason='原预付款批准记录存在（申请 ' + str(request.get('id')) +
                                   '）；批准不等于已实际付款')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原预付款批准决定，请在原页面核对审批进度')

        if fact_key == 'prepayment.disbursement_recorded':
            # 实际预付必须以原 disbursement/allocations 对真实 payment_id 的占用为准。
            for request in requests:
                paid = request.get('paid_cents')
                if type(paid) is int and paid > 0 and _positive_id(request.get('id')):
                    return FactSnapshot(
                        fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                        reason='申请 ' + str(request.get('id')) + ' 已有原实际预付；'
                               '只证明该申请的一笔，不证明整单结清，也不串到另一申请')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有指向真实付款的原预付款 disbursement，请在原页面核对')

        # prepayment.expiration_recorded：必须原 expire 决定/成功结果；
        # 仅 valid_until 过期（expired=True）不构成业务已过账事实。
        for request in requests:
            for decision in _decisions(request):
                if decision.get('action') == DECISION_EXPIRE:
                    return FactSnapshot(
                        fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                        reason='原预付款过期决定存在（申请 ' + str(request.get('id')) + '）')
        if any(request.get('expired') is True for request in requests):
            return FactSnapshot(
                fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                reason='申请已过有效期（valid_until），但没有原 expire 决定/结果，'
                       '不能据此制造已过账事实')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有原预付款过期决定/结果，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in PREPAY_RESULT_OPERATIONS
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
        if snapshot.operation_id not in PREPAY_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 预付款动作挂在原采购动作上：回执继续沿采购 flow_req 族，冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['DECISION_APPROVE', 'DECISION_EXPIRE', 'PREPAY_ACTION', 'PREPAY_ACTIONS', 'PREPAY_FACTS',
           'PREPAY_READ', 'PREPAY_RECEIPT_OPERATIONS', 'PREPAY_RESULT_OPERATIONS',
           'ProcurementPrepaymentAdapter']
