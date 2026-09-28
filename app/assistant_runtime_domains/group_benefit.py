"""集团权益（group_benefit）适配器：原会员权益面的受控投影。

**接口不匹配（如实登记，不猜内部 ID）**：本项登记的对象类型是 `group_member`（原 `GroupMember.id`），
但已评审的权益读取 `GET /api/group/benefits/members` 的必填参数是 **`customer_id`**（原 API 签名
`def member(customer_id:int, ...)`）。仅凭 `group_member` id 无法建立该读取路径，
而助手不得自行拼接/猜测客户 ID 或改用未评审的映射读取。

因此本适配器：
- `read_snapshot` 明确报告"无法从该对象建立已评审读取"（503 + 原页面入口），**不发起任何读取**；
- 三条权益事实一律返回未知并说明原因；
- `extract_result` 仍按原动作响应绑定原 `GroupMember` 引用（写结果本身可判定）；
- `read_receipt` 由已评审 resolver 绑定，保持冻结 `request_id`。
评审补一条"member_id → customer_id"的已评审只读映射（或把对象类型改为 customer 维度）后，
本项即可按原 KINDS（bonus/points/coupon/package）实现真实快照与事实。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

BENEFIT_OBJECT_TYPE = 'group_member'
BENEFIT_MEMBERS = 'GET /api/group/benefits/members'
BENEFIT_RULES = 'GET /api/group/benefits/rules'
BENEFIT_ACTION = 'POST /api/group/benefits/members/{member_id}/actions/{action}'
BENEFIT_KINDS = ('bonus', 'points', 'coupon', 'package')
BENEFIT_RESULT_OPERATIONS = frozenset({BENEFIT_MEMBERS, BENEFIT_RULES, BENEFIT_ACTION})
BENEFIT_RECEIPT_OPERATIONS = frozenset({BENEFIT_ACTION})
BENEFIT_FACTS = ('group_benefit.wallet_recorded', 'group_benefit.entry_recorded',
                 'group_benefit.reservation_recorded')
# 原权益读取按客户维度；与登记的对象类型（member 维度）不一致。
MEMBER_KEY_MISMATCH = ('已评审的会员权益读取按客户维度（必填 customer_id），'
                       '不能用 group_member id 或自行拼接的客户 ID 代替；'
                       '请到原页面核对该会员的权益，或由评审补一条 member→customer 的只读映射。')


def _now():
    return datetime.now(timezone.utc)


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class GroupBenefitAdapter(FlowCaseAdapter):
    """`object_type=group_member`；权益读取按客户维度，故不建立读取路径。"""

    name = 'group_benefit'
    object_types = (BENEFIT_OBJECT_TYPE,)

    def _member_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != BENEFIT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原集团会员')
        return values

    async def read_snapshot(self, principal, ref):
        self._member_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        # 不发起任何读取：原权益读取需要 customer_id，本项只有 member id。
        raise HTTPException(503, MEMBER_KEY_MISMATCH)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._member_ref(ref)
        if fact_key not in BENEFIT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='集团权益未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        # 可用余额与是否足够以原查询为准；在映射补齐前一律未知，不猜。
        return _unknown(fact_key, MEMBER_KEY_MISMATCH)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in BENEFIT_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        if operation_id == BENEFIT_MEMBERS or operation_id == BENEFIT_RULES:
            return []
        member_id = data.get('member_id')
        if not _positive_id(member_id):
            member = data.get('member') if type(data.get('member')) is dict else {}
            member_id = member.get('id')
        if not _positive_id(member_id):
            return []
        return [BusinessObjectRef(type=BENEFIT_OBJECT_TYPE, id=member_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in BENEFIT_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, '原业务返回的权益回执不完整，请稍后重新核对') from None


__all__ = ['BENEFIT_ACTION', 'BENEFIT_FACTS', 'BENEFIT_KINDS', 'BENEFIT_MEMBERS',
           'BENEFIT_OBJECT_TYPE', 'BENEFIT_RECEIPT_OPERATIONS', 'BENEFIT_RESULT_OPERATIONS',
           'BENEFIT_RULES', 'MEMBER_KEY_MISMATCH', 'GroupBenefitAdapter']
