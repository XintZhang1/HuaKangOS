"""会员价格规则（member_price）适配器：原会员定价规则的只读投影。

- 只读 `GET /api/member-pricing/rules/{key}`（reviewed catalog 内），不调用业务 command；
  **key 即原 `MemberPricingRule.id`**（与登记的对象类型一致）。
- 批准、取消、授权是三件不同的事实：**规则候选存在不证明已应用/已授权**；
  授权事实只在原详情确实提供冻结报价快照关联时判定，否则未知。
- 原 native version 取原规则 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

PRICE_OBJECT_TYPE = 'member_pricing_rule'
PRICE_READ = 'GET /api/member-pricing/rules/{key}'
PRICE_CANDIDATES = 'GET /api/member-pricing/candidates'
PRICE_CREATE = 'POST /api/member-pricing/rules'
PRICE_ACTION = 'POST /api/member-pricing/rules/{key}/actions/{action}'
PRICE_ACTIONS = ('submit', 'approve', 'reject', 'cancel')
PRICE_RESULT_OPERATIONS = frozenset({PRICE_READ, PRICE_CREATE, PRICE_ACTION})
PRICE_RECEIPT_OPERATIONS = frozenset({PRICE_CREATE, PRICE_ACTION})
PRICE_FACTS = ('member_price.approved', 'member_price.cancelled',
               'member_price.authorization_recorded')
DECISION_APPROVE = ('approve', 'approved')
DECISION_KEYS = ('action', 'decision', 'kind')
AUTHORIZATION_KEYS = ('authorization_id', 'member_pricing_authorization_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的会员价格规则不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class MemberPriceAdapter(FlowCaseAdapter):
    """`object_type=member_pricing_rule` 的原会员价格规则；key 即规则 id。"""

    name = 'member_price'
    object_types = (PRICE_OBJECT_TYPE,)

    def _rule_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != PRICE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原会员价格规则')
        return values

    async def _rule_detail(self, principal, ref):
        values = self._rule_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(PRICE_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此会员价格规则，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not isinstance(data.get('decisions'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._rule_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        rule_ref = BusinessObjectRef(type=PRICE_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=rule_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('state') if type(data.get('state')) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in PRICE_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=rule_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in PRICE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='会员价格未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._rule_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        rule_ref = BusinessObjectRef(type=PRICE_OBJECT_TYPE, id=data['id'])
        from_rule = EvidenceRef(source_type='object', source_id=rule_ref,
                                native_version=version, observed_at=observed_at)
        decisions = [item for item in (data.get('decisions') or []) if type(item) is dict]

        if fact_key == 'member_price.approved':
            unidentified = 0
            for decision in decisions:
                value = None
                for key in DECISION_KEYS:
                    candidate = decision.get(key)
                    if type(candidate) is str and candidate.strip():
                        value = candidate.strip().lower()
                        break
                if value is None:
                    unidentified += 1
                    continue
                if value in DECISION_APPROVE:
                    return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_rule])
            if not decisions:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_rule],
                                    reason='本规则还没有原批准决定，请在原页面核对审批进度')
            if unidentified == len(decisions):
                return _unknown(fact_key, '原决定记录缺少可识别的动作类型，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_rule],
                                reason='本规则尚无批准决定（可能为提交/驳回），请在原页面核对')

        if fact_key == 'member_price.cancelled':
            if data.get('state') == 'cancelled':
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_rule])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_rule],
                                reason='原会员价格规则当前不是已取消状态，请在原页面核对')

        # member_price.authorization_recorded：必须原 MemberPricingAuthorization 明确关联本规则的
        # 冻结报价快照；候选存在不证明已应用/已授权，该详情未提供关联时一律未知。
        for key in AUTHORIZATION_KEYS:
            if _positive_id(data.get(key)):
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_rule])
        return _unknown(fact_key, '原详情未提供会员价格授权（MemberPricingAuthorization）与冻结报价快照关联，'
                                  '候选存在不证明已应用/已授权，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in PRICE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=PRICE_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in PRICE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['AUTHORIZATION_KEYS', 'DECISION_APPROVE', 'DECISION_KEYS', 'PRICE_ACTION', 'PRICE_ACTIONS',
           'PRICE_CANDIDATES', 'PRICE_CREATE', 'PRICE_FACTS', 'PRICE_OBJECT_TYPE', 'PRICE_READ',
           'PRICE_RECEIPT_OPERATIONS', 'PRICE_RESULT_OPERATIONS', 'MemberPriceAdapter']
