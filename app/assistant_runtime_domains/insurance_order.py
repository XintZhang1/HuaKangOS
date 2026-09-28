"""保险单（insurance_order）适配器：原保险订单的只读投影。

- 只读 `GET /api/insurance-orders/{case_id}`（reviewed catalog 内）；**key 即原 `Case.id`**
  （源码核对：`get_order` → `flow.get_case(db,user,key)` → `_one(db, InsuranceOrder, row.id)`）。
- 写入只走已评审 `POST /api/insurance-orders` 与 `POST /api/insurance-orders/{case_id}/actions/{action}`。
- 三条事实（**附件存在不等于业务事实**，附件不参与判定）：
  - `insurance.current_quote_consented`：**当前报价**（`row.data.insurance_quote_id` 指向的那条）
    在其 `history` 条目中 `authorized=True`，且摘要与当前报价一致；缺字段/摘要不符 **未知**；
  - `insurance.external_result_recorded`：本单原 `InsuranceResult` 及原 `submission_id`/`outcome`；
  - `insurance.policy_issued`：原结果 **`outcome=issued` 且真实 `policy_number` 存在**；
    **任意外部结果不能满足已出保**；保费/佣金保持各自原资金事实。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

INS_OBJECT_TYPE = 'case'
INS_READ = 'GET /api/insurance-orders/{case_id}'
INS_CREATE = 'POST /api/insurance-orders'
INS_ACTION = 'POST /api/insurance-orders/{case_id}/actions/{action}'
INS_SYNC_UNREGISTERED = 'POST /api/observation-corrections/insurance/{case_id}/sync'
INS_ACTIONS = ('quote', 'review', 'authorize', 'submit', 'result', 'receive', 'disburse',
               'direct_paid', 'termination', 'refund', 'commission_review')
INS_RESULT_OPERATIONS = frozenset({INS_READ, INS_CREATE, INS_ACTION})
INS_RECEIPT_OPERATIONS = frozenset({INS_CREATE, INS_ACTION})
INS_FACTS = ('insurance.current_quote_consented', 'insurance.external_result_recorded',
             'insurance.policy_issued')
RESULT_KEYS = ('result', 'insurance_result', 'external_result')
OUTCOME_KEYS = ('outcome', 'status', 'result_code')
POLICY_KEYS = ('policy_number', 'policy_no')
NOT_INSURED = '任意外部结果不能满足已出保；保费与佣金保持各自原资金事实'


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的保险单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class InsuranceOrderAdapter(FlowCaseAdapter):
    """`object_type=case`（原 Case.id 即保险单 id）；事实不引用附件。"""

    name = 'insurance_order'
    object_types = (INS_OBJECT_TYPE,)

    def _case_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != INS_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原保险业务单')
        return values

    async def _detail(self, principal, ref):
        values = self._case_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(INS_READ, path_args={'case_id': values['id']},
                                                 query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原业务不存在或当前岗位不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原业务不存在或当前岗位不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取此保险单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=INS_OBJECT_TYPE, id=data['id'])
        state = data.get('status') or data.get('state') or data.get('stage')
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=state if type(state) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in INS_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _current_quote(data):
        row_data = data.get('data') if isinstance(data.get('data'), dict) else {}
        quote_id = row_data.get('insurance_quote_id') or data.get('insurance_quote_id')
        if not _positive_id(quote_id):
            return None, 'INVALID_QUOTE_REF'
        history = data.get('history')
        if not isinstance(history, list):
            return None, 'NO_HISTORY'
        for entry in history:
            if type(entry) is not dict:
                continue
            quote = entry.get('quote')
            if type(quote) is not dict or quote.get('id') != quote_id:
                continue
            return entry, None
        return None, 'QUOTE_NOT_IN_HISTORY'

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in INS_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='保险单未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=INS_OBJECT_TYPE, id=data['id'])
        evidence = [EvidenceRef(source_type='object', source_id=case_ref, native_version=version,
                                observed_at=observed_at)]

        if fact_key == 'insurance.current_quote_consented':
            entry, why = self._current_quote(data)
            if why == 'INVALID_QUOTE_REF':
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                    reason='本单没有当前报价引用（insurance_quote_id），请在原页面核对')
            if why in ('NO_HISTORY', 'QUOTE_NOT_IN_HISTORY'):
                return _unknown(fact_key, '原详情未提供可核对的报价历史（history）或其中不含当前报价，'
                                          '无法确证同意，请在原页面核对')
            authorized = entry.get('authorized')
            if authorized is None:
                return _unknown(fact_key, '原详情未提供该报价的同意标记（authorized），'
                                          '附件也不作为同意证据，请在原页面核对')
            if authorized is not True:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                    reason='当前报价还没有原同意记录，请在原页面核对')
            quote = entry.get('quote')
            digest = quote.get('digest') if isinstance(quote, dict) else None
            if digest is not None and type(digest) is not str:
                return _unknown(fact_key, '当前报价摘要不可判，无法确证同意指向同一报价，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                reason='当前报价存在原同意记录且引用同一 quote_id'
                                       + ('与摘要' if isinstance(digest, str) and digest.strip() else ''))

        result = None
        for key in RESULT_KEYS:
            candidate = data.get(key)
            if isinstance(candidate, dict):
                result = candidate
                break
        if result is None:
            return _unknown(fact_key, '原详情未提供保险公司实际结果（InsuranceResult），'
                                      '无法确证；' + NOT_INSURED)
        outcome = None
        for key in OUTCOME_KEYS:
            value = result.get(key)
            if type(value) is str and value.strip():
                outcome = value.strip().lower()
                break
        submission_id = result.get('submission_id') or data.get('submission_id')
        if fact_key == 'insurance.external_result_recorded':
            if outcome is None or not _positive_id(submission_id):
                return _unknown(fact_key, '原结果缺少 submission_id 或 outcome，'
                                          '无法确证外部结果已回；' + NOT_INSURED)
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                reason='已登记原保险公司实际结果（submission_id/outcome）；' + NOT_INSURED)
        if outcome is None:
            return _unknown(fact_key, '原结果缺少 outcome，无法确证是否已出保；' + NOT_INSURED)
        if outcome != 'issued':
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='原结果 outcome 不是 issued；' + NOT_INSURED)
        policy_number = None
        for key in POLICY_KEYS:
            value = result.get(key) if key in result else data.get(key)
            if type(value) is str and value.strip():
                policy_number = value.strip()
                break
        if policy_number is None:
            return _unknown(fact_key, 'outcome 为 issued 但缺少真实保单号（policy_number），'
                                      '不判定为已出保；' + NOT_INSURED)
        return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                            reason='原结果 outcome=issued 且存在真实保单号；' + NOT_INSURED)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in INS_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        record = data.get('record') if type(data.get('record')) is dict else data
        if not _positive_id(record.get('id')):
            return []
        return [BusinessObjectRef(type=INS_OBJECT_TYPE, id=record['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in INS_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['INS_ACTION', 'INS_ACTIONS', 'INS_CREATE', 'INS_FACTS', 'INS_OBJECT_TYPE', 'INS_READ',
           'INS_RECEIPT_OPERATIONS', 'INS_RESULT_OPERATIONS', 'INS_SYNC_UNREGISTERED', 'NOT_INSURED',
           'OUTCOME_KEYS', 'POLICY_KEYS', 'RESULT_KEYS', 'InsuranceOrderAdapter']
