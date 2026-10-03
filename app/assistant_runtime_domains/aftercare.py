"""退订退车及维修退款纠正（aftercare）适配器：原售后单的只读投影。

- 只读原售后详情及已登记的原 Flow GET；后者核验门店、类型、流程版本和原任务。
- 方案生效（AftercareApplication）、客户确认（AftercareConsent）与实际退款（AftercareCashRefund）
  是三件不同的事：批准或生效不满足实际退款键，集团本金/权益退回也不冒充现金。
- 原 native version 取本人原 GET 的真实 version；没有可读版本时保持 None，不造版本。
- 本适配器只声明可准备的原 operation，不执行、不生成卡、不改原状态机。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import BusinessObjectRef, EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot
from .flow_case import FlowCaseAdapter, _positive_id

AFTERCARE_KIND = 'aftercare'
AFTERCARE_FLOW_VERSION = 2
AFTERCARE_SCENARIOS = ('sale_termination', 'vehicle_return', 'repair_refund')
AFTERCARE_READ = 'GET /api/aftercare/orders/{case_id}'
AFTERCARE_CREATE = 'POST /api/aftercare/orders'
AFTERCARE_ACTION = 'POST /api/aftercare/orders/{case_id}/actions/{action}'
AFTERCARE_RESULT_OPERATIONS = frozenset({AFTERCARE_READ, AFTERCARE_CREATE, AFTERCARE_ACTION})
AFTERCARE_RECEIPT_OPERATIONS = frozenset({AFTERCARE_CREATE, AFTERCARE_ACTION})
AFTERCARE_FACTS = ('aftercare.plan_applied', 'aftercare.cash_refund_recorded',
                   'aftercare.customer_consent_recorded')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的售后单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class AftercareAdapter(FlowCaseAdapter):
    """`kind == 'aftercare'`、`flow_version == 2` 的原售后单。"""

    name = 'aftercare'
    object_types = ('case',)

    async def _aftercare_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id')):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(AFTERCARE_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此售后单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if not _positive_id(data.get('id')) or data.get('id') != values['id']:
            _invalid()
        if data.get('scenario') not in AFTERCARE_SCENARIOS:
            _invalid()
        if data.get('version') is not None and not _positive_id(data['version']):
            _invalid()
        # 原售后 describe 不提供 store_id/kind/flow_version/tasks；这些事实
        # 只能取本人原 Flow GET，不向专用详情补模拟字段或猜原任务。
        record = await self.read_record(principal, ref)
        if record['kind'] != AFTERCARE_KIND or record['flow_version'] != AFTERCARE_FLOW_VERSION:
            raise HTTPException(422, '这不是原退订退车或维修退款单据，请到对应业务页面办理')
        if (data.get('version') is not None and record['version'] is not None
                and data['version'] != record['version']):
            raise HTTPException(409, '原售后单在读取期间已变化，请重新核对')
        return data, record

    async def read_snapshot(self, principal, ref):
        data, original = await self._aftercare_detail(principal, ref)
        record = dict(original, **{
            'actions': [key for key in (data.get('actions') or []) if type(key) is str],
        })
        return self.snapshot_from_record(ref, record)

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in AFTERCARE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='退订退车与维修退款未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data, _ = await self._aftercare_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        plans = data.get('plans') if isinstance(data.get('plans'), list) else []
        plan_id = data.get('plan_id')
        current = [plan for plan in plans if type(plan) is dict
                   and _positive_id(plan_id) and _positive_id(plan.get('id'))
                   and plan['id'] == plan_id]
        current_plan = current[0] if len(current) == 1 and current[0].get('cancelled') is False else None

        if fact_key == 'aftercare.plan_applied':
            # 方案已生效必须有原 AftercareApplication；已批准但未生效不算。
            if data.get('applied') is not True:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='当前方案尚未在原售后单生效，请先在原页面完成方案生效')
            if current_plan is None:
                return _unknown(fact_key, '原详情没有可引用的方案编号，请在原页面核对方案')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])

        if fact_key == 'aftercare.customer_consent_recorded':
            # 原 describe 对当前方案的布尔值来自 AftercareConsent；不要求
            # API 未披露的 consent_id，也不借旧方案或已取消方案证明当前同意。
            if current_plan is None or current_plan.get('customer_confirmed') is not True:
                return _unknown(fact_key, '需要原客户确认记录，请在原页面核对客户签署')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])

        # aftercare.cash_refund_recorded：必须本单存在原 AftercareCashRefund 及其关联现金来源；
        # 方案批准/生效、集团本金或权益退回都不能替代实际退款。
        refunds = data.get('refunds')
        if not isinstance(refunds, list) or not any(
                type(refund) is dict and _positive_id(refund.get('id'))
                and _positive_id(refund.get('tender_id')) and _positive_id(refund.get('payment_link_id'))
                and type(refund.get('amount_cents')) is int and refund['amount_cents'] > 0
                for refund in refunds):
            return _unknown(fact_key, '需要原现金退款记录及其关联来源，请在原单核对退款结果')
        return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in AFTERCARE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or data.get('scenario') not in AFTERCARE_SCENARIOS
                or data.get('kind') not in (None, AFTERCARE_KIND)):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in AFTERCARE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 售后族回执沿 aftercare_service._execute 的 operation/payload 摘要；
        # 冻结快照与 request_id 由调用方提供，这里绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['AFTERCARE_ACTION', 'AFTERCARE_CREATE', 'AFTERCARE_FACTS', 'AFTERCARE_FLOW_VERSION',
           'AFTERCARE_KIND', 'AFTERCARE_READ', 'AFTERCARE_RECEIPT_OPERATIONS',
           'AFTERCARE_RESULT_OPERATIONS', 'AFTERCARE_SCENARIOS', 'AftercareAdapter']
