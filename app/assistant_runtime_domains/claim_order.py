"""理赔核赔受理（claim_order）适配器：原理赔 Case 的只读投影。

- 只读 `GET /api/claims/{case_id}`（reviewed catalog 内），不调用业务 command。
- 传送、外部结果、承担绑定是三件不同的事实：**任何外部结果都不能当作批准**，
  核赔通过也不证明现金已收。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

CLAIM_READ = 'GET /api/claims/{case_id}'
CLAIM_OPTIONS = 'GET /api/claims/{case_id}/options/{action}'
CLAIM_CREATE = 'POST /api/claims'
CLAIM_ACTION = 'POST /api/claims/{case_id}/actions/{action}'
CLAIM_ACTIONS = ('assess', 'approve', 'transmit', 'result', 'bind', 'resolution')
CLAIM_RESULT_OPERATIONS = frozenset({CLAIM_READ, CLAIM_CREATE, CLAIM_ACTION})
CLAIM_RECEIPT_OPERATIONS = frozenset({CLAIM_CREATE, CLAIM_ACTION})
CLAIM_FACTS = ('claim.transmission_recorded', 'claim.external_result_recorded', 'claim.binding_recorded')
PAYMENT_ROUTES = ('customer_direct', 'customer_via_store', 'repair_shop', 'insurer', 'store')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的理赔单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _rows_of(data, name):
    value = data.get(name)
    return value if isinstance(value, list) else []


class ClaimOrderAdapter(FlowCaseAdapter):
    """`kind=claim` 的原理赔 Case；快照与事实只经单次受控 GET。"""

    name = 'claim_order'
    object_types = ('case',)

    async def _claim_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(CLAIM_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此理赔单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('source_id')) or not isinstance(data.get('order'), dict)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._claim_detail(principal, ref)
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
        if fact_key not in CLAIM_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='理赔核赔未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._claim_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'claim.transmission_recorded':
            for item in _rows_of(data, 'transmissions'):
                if type(item) is dict and _positive_id(item.get('id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原对外传送记录，请在原页面核对传送进度')

        if fact_key == 'claim.external_result_recorded':
            # 只保留原 outcome：任何结果都不等于批准。
            for item in _rows_of(data, 'results'):
                if type(item) is dict and _positive_id(item.get('id')):
                    outcome = item.get('outcome')
                    return FactSnapshot(
                        fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                        reason='外部结果：' + (outcome if type(outcome) is str and outcome.strip()
                                              else '未标注') + '；结果本身不代表已批准或已收款')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原外部核赔结果，请在原页面核对')

        # claim.binding_recorded：原 ClaimBinding 必须指明维修承担与 payment_route；
        # 核赔通过不等于现金已收。
        for item in _rows_of(data, 'bindings'):
            if type(item) is not dict or not _positive_id(item.get('id')):
                continue
            route = item.get('payment_route')
            if type(route) is not str or not route.strip():
                return _unknown(fact_key, '原承担绑定缺少付款去向（payment_route），请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                reason='付款去向：' + route + '；核赔或绑定不代表现金已收')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有原承担绑定，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in CLAIM_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('source_id'))):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in CLAIM_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `ClaimReceipt`（`request_digest('claims_'+operation, payload)`）；
        # 冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['CLAIM_ACTION', 'CLAIM_ACTIONS', 'CLAIM_CREATE', 'CLAIM_FACTS', 'CLAIM_OPTIONS', 'CLAIM_READ',
           'CLAIM_RECEIPT_OPERATIONS', 'CLAIM_RESULT_OPERATIONS', 'PAYMENT_ROUTES', 'ClaimOrderAdapter']
