"""发票（invoice）适配器：原发票申请 Case 的只读投影。

- 只读 `GET /api/invoices/orders/{key}`（reviewed catalog 内），不调用业务 command。
- 提交、外部结果、结果复核是三件不同的事实：**failure/difference 仍是原结果，不能当作发票已开**；
  未在详情暴露的键返回 unknown，不用文字或日期自行断言。
- 原 native version 取原 case 的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

INVOICE_READ = 'GET /api/invoices/orders/{key}'
INVOICE_CREATE = 'POST /api/invoices/orders'
INVOICE_ACTION = 'POST /api/invoices/orders/{key}/actions/{action}'
INVOICE_SOURCES = 'GET /api/invoices/sources'
INVOICE_SOURCE = 'GET /api/invoices/sources/{key}'
INVOICE_ACTIONS = ('approve', 'submit', 'failure', 'difference', 'record', 'review_result')
INVOICE_RESULT_OPERATIONS = frozenset({INVOICE_READ, INVOICE_CREATE, INVOICE_ACTION})
INVOICE_RECEIPT_OPERATIONS = frozenset({INVOICE_CREATE, INVOICE_ACTION})
INVOICE_FACTS = ('invoice.submission_recorded', 'invoice.result_recorded', 'invoice.result_reviewed')
SUBMISSION_KEYS = ('submission', 'submissions', 'submitted_at', 'external_submission')
REVIEW_KEYS = ('review', 'reviewed_at', 'review_result', 'result_review')
NOT_ISSUED_OUTCOMES = ('failure', 'difference', 'failed', 'rejected')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的发票单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class InvoiceAdapter(FlowCaseAdapter):
    """`kind=invoice` 的原 Case（`InvoiceApplication.id` 与原 Case.id 相同）。"""

    name = 'invoice'
    object_types = ('case',)

    async def _invoice_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(INVOICE_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此发票单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('source_case_id'))
                or not isinstance(data.get('actions'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._invoice_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('state') if type(data.get('state')) is str else None,
                tasks=[],
                # 原详情只给岗位筛选后的动作名：可用性不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in (data.get('actions') or []) if type(key) is str],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in INVOICE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='发票未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._invoice_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        result = data.get('result') if type(data.get('result')) is dict else None

        if fact_key == 'invoice.result_recorded':
            if result is None:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='本单还没有原开票结果，请在原页面核对')
            outcome = None
            for key in ('outcome', 'status', 'kind'):
                value = result.get(key)
                if type(value) is str and value.strip():
                    outcome = value.strip().lower()
                    break
            if outcome in NOT_ISSUED_OUTCOMES:
                # failure/difference 仍是原结果，但不能当作发票已开。
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已登记原开票结果（原结果：' + str(outcome) +
                                           '）；失败/差异仍是原结果，不代表发票已开具')
            if type(result.get('invoice_number')) is str and result['invoice_number'].strip():
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                reason='已登记原开票结果（未标注发票号）；是否已开具以原结果为准')

        if fact_key == 'invoice.submission_recorded':
            for key in SUBMISSION_KEYS:
                if data.get(key):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原对外提交记录；提交不等于开票成功')
            return _unknown(fact_key, '原详情未提供对外提交记录（submit 结果），'
                                      '不能据文字或日期自行断言，请在原页面核对')

        # invoice.result_reviewed：必须原 review_result 成功回执与原结果复核事实一致。
        for key in REVIEW_KEYS:
            if data.get(key):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已登记原结果复核；复核不改变原开票结果本身')
        return _unknown(fact_key, '原详情未提供结果复核事实（review_result），请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in INVOICE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in INVOICE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['INVOICE_ACTION', 'INVOICE_ACTIONS', 'INVOICE_CREATE', 'INVOICE_FACTS', 'INVOICE_READ',
           'INVOICE_RECEIPT_OPERATIONS', 'INVOICE_RESULT_OPERATIONS', 'INVOICE_SOURCE',
           'INVOICE_SOURCES', 'NOT_ISSUED_OUTCOMES', 'REVIEW_KEYS', 'SUBMISSION_KEYS', 'InvoiceAdapter']
