"""维修工单接车与施工进度（repair_order）适配器：原维修 Case 的只读投影。

- 只读 `GET /api/repair-orders/{case_id}`（reviewed catalog 内），不调用业务 command。
- 客户授权、质检通过、实际交车是三件不同的事实：报价批准不等于授权，施工完成不等于质检通过，
  收款或旧版质检都不能满足交车键。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

REPAIR_READ = 'GET /api/repair-orders/{case_id}'
REPAIR_CREATE = 'POST /api/repair-orders'
REPAIR_ACTION = 'POST /api/repair-orders/{case_id}/actions/{action}'
REPAIR_ACTIONS = ('quote', 'price_approve', 'authorize', 'start', 'issue', 'return_material',
                  'finish', 'quality', 'allocate', 'receive', 'release')
REPAIR_RESULT_OPERATIONS = frozenset({REPAIR_READ, REPAIR_CREATE, REPAIR_ACTION})
REPAIR_RECEIPT_OPERATIONS = frozenset({REPAIR_CREATE, REPAIR_ACTION})
REPAIR_FACTS = ('repair.current_quote_authorized', 'repair.passed_quality_recorded',
                'repair.release_recorded')
RELEASE_KEYS = ('released_date', 'release_evidence_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的维修单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class RepairOrderAdapter(FlowCaseAdapter):
    """`kind=repair` 的原维修 Case；快照与事实只经单次受控 GET。"""

    name = 'repair_order'
    object_types = ('case',)

    async def _repair_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(REPAIR_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此维修单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('store_id')) or data['store_id'] != store_id):
            _invalid()
        if not isinstance(data.get('quotes'), list):
            _invalid()
        return data

    def _current_quote(self, data):
        """当前报价 = 未取消报价中 revision 最大者；无法判定即返回 None（不猜）。"""
        candidates = []
        for quote in data.get('quotes') or []:
            if type(quote) is not dict or not _positive_id(quote.get('id')) or quote.get('cancelled') is True:
                continue
            revision = quote.get('revision')
            candidates.append((revision if _positive_id(revision) else 0, quote['id'], quote))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[-1][2]

    async def read_snapshot(self, principal, ref):
        # 维修 Case 直接投影统一快照 DTO；动作只保留原返回的岗位筛选名字（可用性未知）。
        data = await self._repair_detail(principal, ref)
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
                                   for key in (data.get('actions') or []) if type(key) is str],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in REPAIR_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='维修工单未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._repair_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        quote = self._current_quote(data)

        if fact_key == 'repair.current_quote_authorized':
            if quote is None:
                return _unknown(fact_key, '原详情没有可判定的当前报价，请到原页面核对报价版本')
            if quote.get('authorized') is True:
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='当前报价还没有客户授权事实，请在原页面核对授权进度')

        if fact_key == 'repair.passed_quality_recorded':
            if quote is None:
                return _unknown(fact_key, '无法判定当前报价，不能据此核对质检，请在原页面核对')
            rows = [item for item in (data.get('quality') or [])
                    if type(item) is dict and item.get('quote_id') == quote['id']]
            if not rows:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='当前报价还没有质检记录，请在原页面核对质检进度')
            latest = rows[-1]
            if latest.get('passed') is True:
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='当前报价质检未通过，请在原页面核对整改与复检')

        # repair.release_recorded：必须以原 data.released_date 与 release_evidence_id 为准；
        # 质检通过、收款完成或旧版记录都不能替代实际交车。
        native = data.get('data') if type(data.get('data')) is dict else {}
        if all(native.get(key) for key in RELEASE_KEYS):
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
        if any(native.get(key) for key in RELEASE_KEYS):
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='原交车事实不完整（日期或凭据缺失），请到原页面核对')
        return _unknown(fact_key, '原详情未提供交车事实（可能岗位不可见），请在原单核对交付结果')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in REPAIR_RESULT_OPERATIONS
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
        if snapshot.operation_id not in REPAIR_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族沿 `repair_v3_` 前缀摘要；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['RELEASE_KEYS', 'REPAIR_ACTION', 'REPAIR_ACTIONS', 'REPAIR_CREATE', 'REPAIR_FACTS',
           'REPAIR_READ', 'REPAIR_RECEIPT_OPERATIONS', 'REPAIR_RESULT_OPERATIONS', 'RepairOrderAdapter']
