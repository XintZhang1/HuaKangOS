"""月结冻结（reconciliation_batch）适配器：原对账批次的只读投影。

- 只读 `GET /api/reconciliation/batches/{key}`（reviewed catalog 内），不调用业务 command。
- **key 即原 `ReconciliationBatch.id`**（原 `get_batch` 读法），与登记的对象类型一致。
- 封存、被重算取代、差异登记是三件不同的事实：**原 issue 存在不等于差异已解决**，
  封存/重算都不冲销原差异记录。
- 写路径已登记（create 与批次动作）：回执由已评审 resolver 绑定，冻结快照不重新生成请求号。
- 原 native version 取原批次的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

BATCH_OBJECT_TYPE = 'reconciliation_batch'
BATCH_READ = 'GET /api/reconciliation/batches/{key}'
BATCH_CLEARING = 'GET /api/reconciliation/clearing'
BATCH_ORIGINS = 'GET /api/reconciliation/origins'
BATCH_CREATE = 'POST /api/reconciliation/batches'
BATCH_ACTION = 'POST /api/reconciliation/batches/{key}/actions/{action}'
BATCH_RESULT_OPERATIONS = frozenset({BATCH_READ, BATCH_CREATE, BATCH_ACTION})
BATCH_RECEIPT_OPERATIONS = frozenset({BATCH_CREATE, BATCH_ACTION})
BATCH_FACTS = ('reconciliation.sealed', 'reconciliation.superseded', 'reconciliation.issue_recorded')
UNRESOLVED_STATES = ('open', 'pending', 'unresolved', 'draft')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的对账批次不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class ReconciliationBatchAdapter(FlowCaseAdapter):
    """`object_type=reconciliation_batch` 的原对账批次；key 即批次 id。"""

    name = 'reconciliation_batch'
    object_types = (BATCH_OBJECT_TYPE,)

    def _batch_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != BATCH_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原对账批次')
        return values

    async def _batch_detail(self, principal, ref):
        values = self._batch_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(BATCH_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此对账批次，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not isinstance(data.get('issues'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._batch_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        batch_ref = BusinessObjectRef(type=BATCH_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=batch_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('status') if type(data.get('status')) is str else None,
                tasks=[],
                # 原批次的对象层没有 reviewed 写 operation：动作一律未知，由原页面裁定。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in ('issue', 'resolve', 'submit', 'reopen', 'recalculate')],
                evidence_refs=[EvidenceRef(source_type='object', source_id=batch_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in BATCH_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='月结冻结未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._batch_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        batch_ref = BusinessObjectRef(type=BATCH_OBJECT_TYPE, id=data['id'])
        from_batch = EvidenceRef(source_type='object', source_id=batch_ref,
                                 native_version=version, observed_at=observed_at)
        status = data.get('status')

        if fact_key == 'reconciliation.sealed':
            if status == 'sealed':
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_batch])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_batch],
                                reason='原对账批次当前不是已封存状态，请在原页面核对')

        if fact_key == 'reconciliation.superseded':
            if status == 'superseded':
                successor = data.get('successor_id')
                note = ('；后继批次 ' + str(successor)) if _positive_id(successor) else ''
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_batch],
                                    reason='原批次已被重算版本取代' + note +
                                           '；取代不冲销原差异记录')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_batch],
                                reason='原对账批次当前不是被取代状态，请在原页面核对')

        # reconciliation.issue_recorded：本批原 ReconciliationIssue；issue 存在不等于差异已解决。
        issues = [item for item in (data.get('issues') or []) if type(item) is dict]
        if not issues:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_batch],
                                reason='本批还没有原差异记录，请在原页面核对')
        unresolved = 0
        for issue in issues:
            state = issue.get('status')
            if type(state) is str and state.strip().lower() in UNRESOLVED_STATES:
                unresolved += 1
        note = ('；其中未解决 ' + str(unresolved) + ' 条') if unresolved else ''
        return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_batch],
                            reason='已登记原差异记录（' + str(len(issues)) + ' 条）' + note +
                                   '；原 issue 存在不等于差异已解决')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in BATCH_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))):
            return []
        return [BusinessObjectRef(type=BATCH_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in BATCH_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['BATCH_ACTION', 'BATCH_CREATE', 'BATCH_CLEARING', 'BATCH_FACTS', 'BATCH_OBJECT_TYPE', 'BATCH_ORIGINS', 'BATCH_READ',
           'BATCH_RECEIPT_OPERATIONS', 'BATCH_RESULT_OPERATIONS', 'UNRESOLVED_STATES',
           'ReconciliationBatchAdapter']
