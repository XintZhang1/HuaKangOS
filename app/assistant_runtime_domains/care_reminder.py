"""客户提醒来源（care_reminder）适配器：原提醒规则的只读投影。

- 只读 `GET /api/customer-service/reminders/rules`（reviewed catalog 内），
  **集合读取按真实 ID 精确匹配**，不按名称或日期猜；不调用业务 command。
- 原规则 kind 固定为 first_service/maintenance/warranty/renewal；规则是否生效只看原 `active`。
- 原读法不暴露"已生成"与周期/来源关联时一律未知：**不从文字/日期自行断言已生成**。
- 原 native version 取原规则的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

REMINDER_OBJECT_TYPE = 'reminder_rule'
REMINDER_RULES = 'GET /api/customer-service/reminders/rules'
REMINDER_RULE_SAVE = 'POST /api/customer-service/reminders/rules'
REMINDER_GENERATE = 'POST /api/customer-service/reminders/generate'
REMINDER_KINDS = ('first_service', 'maintenance', 'warranty', 'renewal')
REMINDER_RESULT_OPERATIONS = frozenset({REMINDER_RULES, REMINDER_RULE_SAVE, REMINDER_GENERATE})
REMINDER_RECEIPT_OPERATIONS = frozenset({REMINDER_RULE_SAVE, REMINDER_GENERATE})
REMINDER_FACTS = ('reminder.rule_active', 'reminder.generated_case_recorded')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的提醒规则不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class CareReminderAdapter(FlowCaseAdapter):
    """`object_type=reminder_rule` 的原提醒规则；只读规则清单并按 ID 精确匹配。"""

    name = 'care_reminder'
    object_types = (REMINDER_OBJECT_TYPE,)

    def _rule_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != REMINDER_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原提醒规则')
        return values

    async def _rules(self, principal):
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(REMINDER_RULES, path_args={}, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取提醒规则，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        items = data.get('items') if type(data) is dict and isinstance(data.get('items'), list) else None
        if data is None or data.get('truncated') or response.get('truncated') or items is None:
            _invalid()
        return items

    async def _rule(self, principal, ref):
        values = self._rule_ref(ref)
        for item in await self._rules(principal):
            if type(item) is dict and item.get('id') == values['id']:
                if item.get('kind') not in REMINDER_KINDS:
                    _invalid()
                return item
        # 原清单按真实 ID 精确匹配；找不到即视为不可查看（含已停用但不在清单的情况）。
        raise HTTPException(404, '原业务不存在或当前账号不可查看')

    async def read_snapshot(self, principal, ref):
        rule = await self._rule(principal, ref)
        observed_at = _now()
        version = rule.get('version') if _positive_id(rule.get('version')) else None
        rule_ref = BusinessObjectRef(type=REMINDER_OBJECT_TYPE, id=rule['id'])
        try:
            return BusinessObjectSnapshot(
                ref=rule_ref, native_version=version,
                display_number=rule.get('name') if type(rule.get('name')) is str else None,
                state='active' if rule.get('active') is True else 'inactive',
                tasks=[],
                # 原规则清单不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in ('save', 'generate')],
                evidence_refs=[EvidenceRef(source_type='object', source_id=rule_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in REMINDER_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='客户提醒来源未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        rule = await self._rule(principal, ref)
        observed_at = _now()
        version = rule.get('version') if _positive_id(rule.get('version')) else None
        rule_ref = BusinessObjectRef(type=REMINDER_OBJECT_TYPE, id=rule['id'])
        from_rule = EvidenceRef(source_type='object', source_id=rule_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'reminder.rule_active':
            if rule.get('active') is True:
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_rule])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_rule],
                                reason='原提醒规则当前未生效（active 非真），请在原页面核对')

        # reminder.generated_case_recorded：需要原 generate 成功结果或带同规则、同车辆/周期与
        # care case 引用的已生成记录；规则清单读法不暴露该关联，故一律未知。
        return _unknown(fact_key, '原规则清单不暴露周期/来源与已生成案件关联，'
                                  '无法据此断言已生成；请到原页面核对生成结果')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in REMINDER_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        if operation_id == REMINDER_RULES:
            items = data.get('items')
            return [] if not isinstance(items, list) else []
        rule_id = data.get('id') if _positive_id(data.get('id')) else data.get('rule_id')
        if not _positive_id(rule_id):
            return []
        return [BusinessObjectRef(type=REMINDER_OBJECT_TYPE, id=rule_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in REMINDER_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 规则保存/生成属业务写接口：回执由已评审 resolver 绑定，冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['REMINDER_FACTS', 'REMINDER_GENERATE', 'REMINDER_KINDS', 'REMINDER_OBJECT_TYPE',
           'REMINDER_RECEIPT_OPERATIONS', 'REMINDER_RESULT_OPERATIONS', 'REMINDER_RULE_SAVE',
           'REMINDER_RULES', 'CareReminderAdapter']
