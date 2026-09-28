"""会员业务单（membership_order）适配器：原会员 Case 的只读投影。

- 只读 `GET /api/membership/orders/{key}`（reviewed catalog 内），不调用业务 command。
- **API 的 key 是原 Case.id**（`MembershipOrder.case_id` 指向它），绝不用 `MembershipOrder.id` 替代。
- 执行、退费依据、周期关联是三件不同的事实；原事件按岗位脱敏时只保留"已登记"结论，
  不因脱敏而否定事实，也不替原权限开口。
- 原 native version 取原 case 的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

MEMBERSHIP_READ = 'GET /api/membership/orders/{key}'
MEMBERSHIP_CREATE = 'POST /api/membership/orders'
MEMBERSHIP_ACTION = 'POST /api/membership/orders/{key}/actions/{action}'
MEMBERSHIP_PURPOSES = ('topup', 'benefit_issue', 'card_issue', 'card_loss', 'card_replace',
                       'renew', 'tier_change', 'renew_refund', 'points_adjust')
MEMBERSHIP_ACTIONS = ('approve', 'execute', 'cancel')
MEMBERSHIP_RESULT_OPERATIONS = frozenset({MEMBERSHIP_READ, MEMBERSHIP_CREATE, MEMBERSHIP_ACTION})
MEMBERSHIP_RECEIPT_OPERATIONS = frozenset({MEMBERSHIP_CREATE, MEMBERSHIP_ACTION})
MEMBERSHIP_FACTS = ('membership.executed', 'membership.fee_refund_basis_recorded',
                    'membership.period_linked')
EXECUTE_ACTIONS = ('execute', 'executed')
EXECUTED_STATES = ('executed', 'completed')
PERIOD_KEYS = ('period_id', 'wallet_period_id', 'membership_period_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的会员业务单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class MembershipOrderAdapter(FlowCaseAdapter):
    """`kind=membership` 的原会员 Case；key 一律取原 Case.id。"""

    name = 'membership_order'
    object_types = ('case',)

    async def _membership_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(MEMBERSHIP_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此会员业务单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        case = data.get('case') if type(data) is dict and type(data.get('case')) is dict else None
        if (case is None or data.get('truncated') or response.get('truncated')
                or not _positive_id(case.get('id')) or case.get('id') != values['id']
                or not isinstance(data.get('events'), list)
                or not isinstance(data.get('order'), dict)):
            _invalid()
        purpose = data['order'].get('purpose')
        if purpose is not None and purpose not in MEMBERSHIP_PURPOSES:
            raise HTTPException(422, '这不是原会员业务单，请到对应业务页面办理')
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._membership_detail(principal, ref)
        case = data['case']
        observed_at = _now()
        version = case.get('version') if _positive_id(case.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=case['id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=case.get('number') if type(case.get('number')) is str else None,
                state=case.get('state') if type(case.get('state')) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in MEMBERSHIP_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _events(data):
        return [item for item in (data.get('events') or []) if type(item) is dict]

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in MEMBERSHIP_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='会员业务单未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._membership_detail(principal, ref)
        case, order = data['case'], data['order']
        observed_at = _now()
        version = case.get('version') if _positive_id(case.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=case['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        events = self._events(data)

        if fact_key == 'membership.executed':
            has_event = any(str(event.get('action') or '').lower() in EXECUTE_ACTIONS for event in events)
            state = case.get('state')
            executed_state = type(state) is str and state.lower() in EXECUTED_STATES
            if has_event and executed_state:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='原执行事件与原单状态吻合')
            if has_event or executed_state:
                return _unknown(fact_key, '只看到原执行事件或原单状态之一，无法确认执行已成功，'
                                          '请在原页面核对执行结果')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原执行结果，请在原页面核对')

        if fact_key == 'membership.fee_refund_basis_recorded':
            for event in events:
                if event.get('action') == 'fee_refund_basis':
                    detail = event.get('detail') if type(event.get('detail')) is dict else {}
                    if detail.get('recorded') is True:
                        # 原权限脱敏：只保留"已登记"结论，不替原权限开口。
                        return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                            reason='原续会费退款依据已登记（原权限仅暴露登记结论）')
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='原续会费退款依据已登记')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原续会费退款依据事件，请在原页面核对')

        # membership.period_linked：本单原结果必须明确关联实际周期。
        for key in PERIOD_KEYS:
            if _positive_id(order.get(key)):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='原会员业务单已关联实际周期')
        return _unknown(fact_key, '原详情未提供实际周期关联，无法据此断言已关联周期，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in MEMBERSHIP_RESULT_OPERATIONS
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
        if snapshot.operation_id not in MEMBERSHIP_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['EXECUTE_ACTIONS', 'EXECUTED_STATES', 'MEMBERSHIP_ACTION', 'MEMBERSHIP_ACTIONS',
           'MEMBERSHIP_CREATE', 'MEMBERSHIP_FACTS', 'MEMBERSHIP_PURPOSES', 'MEMBERSHIP_READ',
           'MEMBERSHIP_RECEIPT_OPERATIONS', 'MEMBERSHIP_RESULT_OPERATIONS', 'PERIOD_KEYS',
           'MembershipOrderAdapter']
