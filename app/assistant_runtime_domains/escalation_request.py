"""评审升级申请（escalation_request）适配器：只准备、绝不代办人工处理。

- reviewed catalog 内本域只有三条：`GET /api/escalations`、`GET /api/escalations/refusals`、
  `POST /api/escalations`（**只准备**）。
- 原 `POST /api/escalations/{escalation_id}/actions/{action}`（claim/done/reject/cancel）虽存在，
  **不在已评审目录内**：助手**不得调用**这些人工处理动作，也不得借用管理员身份。
- 对象：`escalation`（原 `Escalation.id`）与 `refusal`（原 `Refusal.id`）。
- 事实（按类型适用，**不适用类型返回未知**）：
  - `escalation.request_recorded`（仅 escalation）：原授权列表精确匹配 `Escalation.id` 与服务器 `refusal_id`；
  - `escalation.done`（仅 escalation）：原人工 done 动作**及**当前原申请状态吻合；
    **评审 done 不满足业务成功或权限已授予**；
  - `escalation.refusal_recorded`（仅 refusal）：原 `/refusals` 精确匹配 `Refusal.id`/`classification`。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

ESC_TYPE = 'escalation'
REFUSAL_TYPE = 'refusal'
ESC_INDEX = 'GET /api/escalations'
ESC_REFUSALS = 'GET /api/escalations/refusals'
ESC_CREATE = 'POST /api/escalations'
ESC_UNREGISTERED_ACTION = 'POST /api/escalations/{escalation_id}/actions/{action}'
ESC_SCOPES = ('mine', 'to_review')
ESC_ACTIONS = ('claim', 'done', 'reject', 'cancel')
ESC_RESULT_OPERATIONS = frozenset({ESC_CREATE})
ESC_RECEIPT_OPERATIONS = frozenset({ESC_CREATE})
ESC_FACTS = ('escalation.request_recorded', 'escalation.done', 'escalation.refusal_recorded')
ESCALATION_ONLY = ('escalation.request_recorded', 'escalation.done')
REFUSAL_ONLY = ('escalation.refusal_recorded',)
MANUAL_ONLY = ('claim/done/reject/cancel 是原人工处理动作，未在已评审目录内：'
               '助手不得代办，也不得借用管理员身份')
DONE_NOT_PERMISSION = '评审 done 不满足业务成功或权限已授予'


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的申请数据不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class EscalationRequestAdapter(FlowCaseAdapter):
    """`escalation` / `refusal` 的只读投影 + 只准备写入；人工处理动作绝不代办。"""

    name = 'escalation_request'
    object_types = (ESC_TYPE, REFUSAL_TYPE)
    fact_keys = ESC_FACTS

    def _ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') not in (ESC_TYPE, REFUSAL_TYPE)
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原申请或拒绝记录')
        return values

    async def _read(self, principal, operation_id, query):
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(operation_id, path_args={}, query=query, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原业务不存在或当前岗位不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原业务不存在或当前岗位不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        return data

    async def read_scope(self, principal, scope='mine'):
        """受评审只读：原申请列表的指定范围（原接口默认 mine）。"""
        if scope not in ESC_SCOPES:
            raise HTTPException(422, '申请范围不正确')
        return await self._read(principal, ESC_INDEX, {'scope': scope})

    async def read_refusals(self, principal):
        """受评审只读：原拒绝记录列表（含分类与服务器 refusal 标识）。"""
        return await self._read(principal, ESC_REFUSALS, {})

    async def _find(self, principal, ref):
        values = self._ref(ref)
        if values['type'] == REFUSAL_TYPE:
            data = await self.read_refusals(principal)
            items = data.get('items')
            if not isinstance(items, list):
                return None, values, '原拒绝记录未返回可核对明细（items），无法确认'
            for item in items:
                if type(item) is dict and item.get('id') == values['id']:
                    return item, values, None
            return None, values, None
        for scope in ESC_SCOPES:
            data = await self.read_scope(principal, scope)
            items = data.get('items')
            if not isinstance(items, list):
                return None, values, '原申请列表未返回可核对明细（items），无法确认'
            for item in items:
                if type(item) is dict and item.get('id') == values['id']:
                    return item, values, None
        return None, values, None

    async def read_snapshot(self, principal, ref):
        record, values, unclear = await self._find(principal, ref)
        if record is None:
            if unclear:
                raise HTTPException(503, unclear)
            raise HTTPException(404, '原申请不存在或当前岗位不可查看')
        observed_at = _now()
        object_ref = BusinessObjectRef(type=values['type'], id=values['id'])
        state = record.get('status') or record.get('state')
        try:
            return BusinessObjectSnapshot(
                ref=object_ref, native_version=None,
                display_number=(record.get('number') if type(record.get('number')) is str else None),
                state=state if type(state) is str else None,
                tasks=[],
                # 人工处理动作不在已评审目录内：可用性一律 unknown，且不准备。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in ESC_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=object_ref,
                                           native_version=None, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        values = self._ref(ref)
        if fact_key not in ESC_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='评审升级未登记此事实，请按对应业务能力核对；' + MANUAL_ONLY)
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        # 按计划：前两键仅适用 escalation，末键仅适用 refusal。
        if fact_key in ESCALATION_ONLY and values['type'] != ESC_TYPE:
            return _unknown(fact_key, '本事实只适用于原评审升级申请（escalation），'
                                      '对拒绝记录不适用；' + MANUAL_ONLY)
        if fact_key in REFUSAL_ONLY and values['type'] != REFUSAL_TYPE:
            return _unknown(fact_key, '本事实只适用于原拒绝记录（refusal），'
                                      '对升级申请不适用；' + MANUAL_ONLY)
        record, values, unclear = await self._find(principal, ref)
        observed_at = _now()
        object_ref = BusinessObjectRef(type=values['type'], id=values['id'])
        evidence = [EvidenceRef(source_type='object', source_id=object_ref, native_version=None,
                                observed_at=observed_at)]
        if record is None:
            if unclear:
                return _unknown(fact_key, unclear)
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='原授权列表（mine 与 to_review 两个范围）完整读取后没有该记录，'
                                       '请在原页面核对')

        if fact_key == 'escalation.refusal_recorded':
            classification = record.get('classification') or record.get('class')
            if type(classification) is not str or not classification.strip():
                return _unknown(fact_key, '原拒绝记录缺少可识别的 classification，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                reason='已在原 /refusals 中精确匹配该拒绝记录与其 classification')

        refusal_id = record.get('refusal_id')
        if fact_key == 'escalation.request_recorded':
            if not _positive_id(refusal_id):
                return _unknown(fact_key, '原申请未回带服务器 refusal_id，'
                                          '无法确证申请已按服务器拒绝记录登记，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                reason='原授权列表中精确匹配该申请与其服务器 refusal_id')

        # escalation.done：必须同时有原人工 done 动作与原申请状态吻合
        state = record.get('status') or record.get('state')
        events = record.get('events')
        actions = []
        if isinstance(events, list):
            for item in events:
                if type(item) is dict:
                    value = item.get('action') or item.get('kind')
                    if type(value) is str and value.strip():
                        actions.append(value.strip().lower())
        if state != 'done':
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='原申请当前状态不是 done，请在原页面核对；' + DONE_NOT_PERMISSION)
        if not actions:
            return _unknown(fact_key, '原申请状态为 done，但原详情未提供人工 done 动作明细，'
                                      '不判定为完成；' + DONE_NOT_PERMISSION)
        if 'done' not in actions:
            return _unknown(fact_key, '原详情的事件里没有人工 done 动作，不判定为完成；' + DONE_NOT_PERMISSION)
        return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                            reason='原人工 done 动作与当前原申请状态吻合；' + DONE_NOT_PERMISSION)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in ESC_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        record = data.get('record') if type(data.get('record')) is dict else data
        if not _positive_id(record.get('id')):
            return []
        return [BusinessObjectRef(type=ESC_TYPE, id=record['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in ESC_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['DONE_NOT_PERMISSION', 'ESC_ACTIONS', 'ESC_CREATE', 'ESC_FACTS', 'ESC_INDEX',
           'ESC_REFUSALS', 'ESC_RESULT_OPERATIONS', 'ESC_RECEIPT_OPERATIONS', 'ESC_SCOPES',
           'ESC_TYPE', 'ESC_UNREGISTERED_ACTION', 'ESCALATION_ONLY', 'MANUAL_ONLY',
           'REFUSAL_ONLY', 'REFUSAL_TYPE', 'EscalationRequestAdapter']
