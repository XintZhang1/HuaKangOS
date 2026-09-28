"""集团本金与权益（group_principal）适配器：原集团会员的只读投影。

- 只读 `GET /api/group/members/{member_id}`（reviewed catalog 内），不调用业务 command。
- 入账、占用、退回是三件不同的事实：**任意一笔流水只证明存在，不能当作某单已结清**。
- 原详情按 100 条截断（`limit(100)`）：达到上限时按"存在性只证明"处理并在理由中说明，不虚报总数。
- 原 native version 缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

MEMBER_OBJECT_TYPE = 'group_member'
MEMBER_READ = 'GET /api/group/members/{member_id}'
MEMBER_ACTION = 'POST /api/group/benefits/members/{member_id}/actions/{action}'
MEMBER_COMMANDS = ('topup', 'reserve', 'capture', 'release', 'reverse',
                   'refund_request', 'refund_approve', 'refund')
MEMBER_RESULT_OPERATIONS = frozenset({MEMBER_READ, MEMBER_ACTION})
MEMBER_RECEIPT_OPERATIONS = frozenset({MEMBER_ACTION})
MEMBER_FACTS = ('group_principal.entry_recorded', 'group_principal.reservation_recorded',
                'group_principal.refund_recorded')
# 原详情对流水使用 limit(100)：达到上限即视为可能截断。
DETAIL_PAGE_LIMIT = 100
REFUND_DONE_STATES = ('refunded', 'completed', 'approved', 'executed')
CASH_KEYS = ('cash_id', 'settlement_id', 'entry_id', 'payment_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的集团会员数据不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class GroupPrincipalAdapter(FlowCaseAdapter):
    """`object_type=group_member` 的原集团会员；事实按原流水逐笔判定。"""

    name = 'group_principal'
    object_types = (MEMBER_OBJECT_TYPE,)

    def _member_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != MEMBER_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原集团会员')
        return values

    async def _member_detail(self, principal, ref):
        values = self._member_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(MEMBER_READ, path_args={'member_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此集团会员，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        member = data.get('member') if type(data.get('member')) is dict else data
        if not _positive_id(member.get('id')) or member.get('id') != values['id']:
            _invalid()
        return data

    @staticmethod
    def _rows(data, name):
        value = data.get(name)
        return [item for item in value if type(item) is dict] if isinstance(value, list) else []

    async def read_snapshot(self, principal, ref):
        data = await self._member_detail(principal, ref)
        member = data.get('member') if type(data.get('member')) is dict else data
        observed_at = _now()
        version = member.get('version') if _positive_id(member.get('version')) else None
        member_ref = BusinessObjectRef(type=MEMBER_OBJECT_TYPE, id=member['id'])
        try:
            return BusinessObjectSnapshot(
                ref=member_ref, native_version=version,
                display_number=member.get('name') if type(member.get('name')) is str else None,
                state=None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in MEMBER_COMMANDS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=member_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in MEMBER_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='集团本金与权益未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._member_detail(principal, ref)
        member = data.get('member') if type(data.get('member')) is dict else data
        observed_at = _now()
        version = member.get('version') if _positive_id(member.get('version')) else None
        member_ref = BusinessObjectRef(type=MEMBER_OBJECT_TYPE, id=member['id'])
        from_member = EvidenceRef(source_type='object', source_id=member_ref,
                                  native_version=version, observed_at=observed_at)

        if fact_key == 'group_principal.entry_recorded':
            entries = self._rows(data, 'entries')
            if not entries:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_member],
                                    reason='本会员还没有原集团入账流水，请在原页面核对')
            for entry in entries:
                if (_positive_id(entry.get('id')) and type(entry.get('kind')) is str
                        and entry.get('kind').strip()):
                    reason = '已存在原集团入账流水（至少一笔，保留 kind/金额与来源）；一笔不代表某单已结清'
                    if len(entries) >= DETAIL_PAGE_LIMIT:
                        reason += '；原详情按 %d 条截断，仅证明存在' % DETAIL_PAGE_LIMIT
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_member],
                                        reason=reason)
            return _unknown(fact_key, '原入账流水缺少可识别的类型，请在原页面核对')

        if fact_key == 'group_principal.reservation_recorded':
            reservations = self._rows(data, 'reservations')
            if not reservations:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_member],
                                    reason='本会员还没有原集团占用记录，请在原页面核对')
            for item in reservations:
                if _positive_id(item.get('id')):
                    reason = '已存在原集团占用（至少一笔）；占用不代表已核销或已结清'
                    if len(reservations) >= DETAIL_PAGE_LIMIT:
                        reason += '；原详情按 %d 条截断，仅证明存在' % DETAIL_PAGE_LIMIT
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_member],
                                        reason=reason)
            return _unknown(fact_key, '原占用记录缺少可识别标识，请在原页面核对')

        # group_principal.refund_recorded：必须原 refund 成功回执与原资金退回账目一致；
        # 仅有申请或审批不满足本键。
        refunds = self._rows(data, 'refunds') or self._rows(data, 'refund_requests')
        if not refunds:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_member],
                                reason='本会员还没有原退款记录，请在原页面核对')
        requested_only = False
        for item in refunds:
            status = item.get('status')
            cash_linked = any(_positive_id(item.get(key)) for key in CASH_KEYS)
            if type(status) is str and status.lower() in REFUND_DONE_STATES and cash_linked:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_member],
                                    reason='原退款成功结果与原资金退回账目一致（单笔）；'
                                           '一笔不代表某单已结清')
            if type(status) is str and status.lower() in REFUND_DONE_STATES and not cash_linked:
                requested_only = True
        if requested_only:
            return _unknown(fact_key, '原退款已批准但没有可见的资金退回账目，无法确认实际退回，'
                                      '请在原页面核对')
        return _unknown(fact_key, '原退款记录状态不明确（可能仅在申请/审批中），请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in MEMBER_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        member = data.get('member') if type(data.get('member')) is dict else data
        member_id = member.get('id') if _positive_id(member.get('id')) else data.get('member_id')
        if not _positive_id(member_id):
            return []
        return [BusinessObjectRef(type=MEMBER_OBJECT_TYPE, id=member_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in MEMBER_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 集团回执族 `GroupReceipt`（原 `_digest` 摘要）；冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['CASH_KEYS', 'DETAIL_PAGE_LIMIT', 'MEMBER_ACTION', 'MEMBER_COMMANDS', 'MEMBER_FACTS',
           'MEMBER_OBJECT_TYPE', 'MEMBER_READ', 'MEMBER_RECEIPT_OPERATIONS',
           'MEMBER_RESULT_OPERATIONS', 'REFUND_DONE_STATES', 'GroupPrincipalAdapter']
