"""预收与结算（business_finance_order）适配器：原财务 Case 的只读投影。

- 只读 `GET /api/business-finance/orders/{key}`（reviewed catalog 内），不调用业务 command。
- **API 的 key 是原 `Case.id`**（`FinanceOrder.case_id` 指向它），绝不用 `FinanceOrder.id` 替代。
- 执行、现金批次、更正是三件不同的事实：**执行成功不能跨 purpose 推断所有款项完成**；
  依 purpose 选择实际存在的原事实，**不适用/未提供的键返回 unknown 而不是 False**。
- 原 native version 取原 case 的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

FINANCE_READ = 'GET /api/business-finance/orders/{key}'
FINANCE_CREATE = 'POST /api/business-finance/orders'
FINANCE_ACTION = 'POST /api/business-finance/orders/{key}/actions/{action}'
FINANCE_SOURCES = 'GET /api/business-finance/sources'
FINANCE_ADVANCES = 'GET /api/business-finance/advances'
FINANCE_RECEIPTS = 'GET /api/business-finance/receipts'
FINANCE_RESULT_OPERATIONS = frozenset({FINANCE_READ, FINANCE_CREATE, FINANCE_ACTION})
FINANCE_RECEIPT_OPERATIONS = frozenset({FINANCE_CREATE, FINANCE_ACTION})
FINANCE_FACTS = ('finance.executed', 'finance.cash_batch_recorded', 'finance.correction_recorded')
EXECUTE_ACTIONS = ('execute', 'executed', 'recalculate_and_execute')
EXECUTED_STATES = ('executed', 'completed', 'settled')
CASH_BATCH_KEYS = ('cash_batch', 'cash_batch_id', 'batch_id')
CORRECTION_KEYS = ('correction', 'correction_id', 'stored_correction_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的财务单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class BusinessFinanceOrderAdapter(FlowCaseAdapter):
    """`kind=business_finance` 的原 Case；key 一律取原 Case.id。"""

    name = 'business_finance_order'
    object_types = ('case',)

    async def _finance_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(FINANCE_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此财务单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        case = data.get('case') if type(data) is dict and type(data.get('case')) is dict else None
        if (case is None or data.get('truncated') or response.get('truncated')
                or not _positive_id(case.get('id')) or case.get('id') != values['id']
                or not isinstance(data.get('events'), list) or not isinstance(data.get('order'), dict)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._finance_detail(principal, ref)
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
                                   for key in ('recalculate', 'approve', 'execute', 'cancel')],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in FINANCE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='预收与结算未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._finance_detail(principal, ref)
        case, order = data['case'], data['order']
        observed_at = _now()
        version = case.get('version') if _positive_id(case.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=case['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        purpose = order.get('purpose')
        purpose_note = ('原 purpose：' + purpose) if type(purpose) is str and purpose.strip() else '原 purpose 未标注'
        events = [item for item in (data.get('events') or []) if type(item) is dict]

        if fact_key == 'finance.executed':
            has_event = any(str(event.get('action') or '').lower() in EXECUTE_ACTIONS for event in events)
            state = case.get('state')
            executed_state = type(state) is str and state.lower() in EXECUTED_STATES
            if has_event and executed_state:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='原执行事件与原状态吻合；' + purpose_note +
                                           '；执行成功不代表所有款项完成')
            if has_event or executed_state:
                return _unknown(fact_key, '只看到原执行事件或原状态之一，无法确认执行成功，'
                                          '请在原页面核对；' + purpose_note)
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原执行结果，请在原页面核对；' + purpose_note)

        # 现金批次与更正：依 purpose 选择实际存在的原事实；不适用或原详情未提供时返回 unknown。
        keys = CASH_BATCH_KEYS if fact_key == 'finance.cash_batch_recorded' else CORRECTION_KEYS
        label = '原现金批次及分配' if fact_key == 'finance.cash_batch_recorded' else '原更正记录/明确更正结果'
        for key in keys:
            value = data.get(key)
            if type(value) is dict and _positive_id(value.get('id')):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已登记' + label + '；' + purpose_note)
            if _positive_id(value):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已登记' + label + '；' + purpose_note)
        return _unknown(fact_key, '原详情未提供' + label + '（可能不适用于本 purpose 或岗位不可见）；'
                                  + purpose_note + '；不适用键不推断为未完成，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in FINANCE_RESULT_OPERATIONS
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
        if snapshot.operation_id not in FINANCE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['CASH_BATCH_KEYS', 'CORRECTION_KEYS', 'EXECUTED_STATES', 'EXECUTE_ACTIONS',
           'FINANCE_ACTION', 'FINANCE_ADVANCES', 'FINANCE_CREATE', 'FINANCE_FACTS', 'FINANCE_READ',
           'FINANCE_RECEIPTS', 'FINANCE_RECEIPT_OPERATIONS', 'FINANCE_RESULT_OPERATIONS',
           'FINANCE_SOURCES', 'BusinessFinanceOrderAdapter']
