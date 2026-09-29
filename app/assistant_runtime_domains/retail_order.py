"""精品销售与套餐（retail_order）适配器：原精品 Case 的只读投影。

- 只读 `GET /api/retail/orders/{key}`（reviewed catalog 内），不调用业务 command。
- 出库、客户接收、退回过账是三件不同的事实：**存在一行不表示整单全部出退完毕**，
  接收必须有原单实际接收事实，退回必须有原 `RetailReturnPosting` 确证的退回数量。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

RETAIL_READ = 'GET /api/retail/orders/{key}'
RETAIL_CREATE = 'POST /api/retail/orders'
RETAIL_ACTION = 'POST /api/retail/orders/{key}/actions/{action}'
RETAIL_ACTIONS = ('approve', 'authorize', 'dispatch', 'install', 'accept', 'receive',
                  'return_request', 'return_approve', 'return_handback', 'return_rectify', 'return_receive')
RETAIL_RESULT_OPERATIONS = frozenset({RETAIL_READ, RETAIL_CREATE, RETAIL_ACTION})
RETAIL_RECEIPT_OPERATIONS = frozenset({RETAIL_CREATE, RETAIL_ACTION})
RETAIL_FACTS = ('retail.dispatch_recorded', 'retail.accept_recorded', 'retail.return_posted')
# 原单实际接收事实的登记键；未登记或岗位不可见时返回未知，不猜。
ACCEPT_KEYS = ('accepted_at', 'accepted_date', 'accepted', 'received_at')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的精品单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class RetailOrderAdapter(FlowCaseAdapter):
    """`kind=retail` 的原精品 Case；快照与事实只经单次受控 GET。"""

    name = 'retail_order'
    object_types = ('case',)

    async def _retail_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(RETAIL_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此精品单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('store_id')) or data['store_id'] != store_id
                or not isinstance(data.get('lines'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._retail_detail(principal, ref)
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
                                   for key in RETAIL_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in RETAIL_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='精品销售与套餐未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._retail_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        dispatches = [item for item in (data.get('dispatches') or []) if type(item) is dict]

        if fact_key == 'retail.dispatch_recorded':
            # 只证明至少一行已实际出库；不代表整单出库完毕。
            for item in dispatches:
                if _positive_id(item.get('id')) and _positive_id(item.get('line_id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原出库记录（至少一行）；整单是否出齐以原单逐行为准')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原出库记录，请在原页面核对出库进度')

        if fact_key == 'retail.accept_recorded':
            native = data.get('data') if type(data.get('data')) is dict else {}
            for key in ACCEPT_KEYS:
                if native.get(key):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='原单已登记实际接收事实；安装与收款状态以原单为准')
            return _unknown(fact_key, '需要原单实际接收事实，该详情未提供或当前岗位不可见，请到原页面核对')

        # retail.return_posted：必须由原 RetailReturnPosting 确证的退回数量（详情 returned_milli）为准。
        for item in dispatches:
            returned = item.get('returned_milli')
            if type(returned) is int and returned > 0:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已存在原退回过账（至少一行）；整单退回以原单逐行为准')
        if dispatches:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单出库行还没有原退回过账，请在原页面核对退回进度')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有出库行，无法确证退回，请到原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in RETAIL_RESULT_OPERATIONS
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
        if snapshot.operation_id not in RETAIL_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族沿 `retail_` 前缀摘要；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['ACCEPT_KEYS', 'RETAIL_ACTION', 'RETAIL_ACTIONS', 'RETAIL_CREATE', 'RETAIL_FACTS',
           'RETAIL_READ', 'RETAIL_RECEIPT_OPERATIONS', 'RETAIL_RESULT_OPERATIONS', 'RetailOrderAdapter']
