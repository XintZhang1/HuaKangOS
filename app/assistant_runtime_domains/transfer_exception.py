"""调拨差异处置（transfer_exception）适配器：原差异单的只读投影。

- 只读 `GET /api/transfer-exceptions/{key}`（reviewed catalog 内），不调用业务 command；
  **key 即原 `TransferException.id`**（与登记的对象类型一致）。
- 观察、处置、损失过账是三件不同的事实：**方案批准不等于处置或过账**；
  只在原详情确实提供对应记录时判定，未提供一律未知。
- 原 native version 取原单 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

EXC_OBJECT_TYPE = 'transfer_exception'
EXC_READ = 'GET /api/transfer-exceptions/{key}'
EXC_CREATE = 'POST /api/transfer-exceptions'
EXC_ACTION = 'POST /api/transfer-exceptions/{key}/actions/{action}'
EXC_ORIGINS = 'GET /api/transfer-exceptions/origins/{transfer_id}'
EXC_ACTIONS = ('observe', 'plan', 'approve', 'reject_plan', 'dispose', 'post_loss', 'cancel')
EXC_RESULT_OPERATIONS = frozenset({EXC_READ, EXC_CREATE, EXC_ACTION})
EXC_RECEIPT_OPERATIONS = frozenset({EXC_CREATE, EXC_ACTION})
EXC_FACTS = ('transfer_exception.observation_recorded', 'transfer_exception.disposal_recorded',
             'transfer_exception.loss_posted')
RECORD_KEYS = {'transfer_exception.observation_recorded': ('observations', 'observation'),
               'transfer_exception.disposal_recorded': ('disposals', 'disposal'),
               'transfer_exception.loss_posted': ('loss_postings', 'loss_posting', 'posting')}


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的差异单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class TransferExceptionAdapter(FlowCaseAdapter):
    """`object_type=transfer_exception` 的原调拨差异单；key 即原单 id。"""

    name = 'transfer_exception'
    object_types = (EXC_OBJECT_TYPE,)

    def _exception_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != EXC_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原调拨差异单')
        return values

    async def _detail(self, principal, ref):
        values = self._exception_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(EXC_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此差异单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('transfer_id'))):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        exception_ref = BusinessObjectRef(type=EXC_OBJECT_TYPE, id=data['id'])
        state = data.get('status') or data.get('state')
        try:
            return BusinessObjectSnapshot(
                ref=exception_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=state if type(state) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in EXC_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=exception_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _has_record(data, keys):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                for item in value:
                    if type(item) is dict and _positive_id(item.get('id')):
                        return True
            elif isinstance(value, dict) and _positive_id(value.get('id')):
                return True
            elif _positive_id(value):
                return True
        return False

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in EXC_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='调拨差异未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        exception_ref = BusinessObjectRef(type=EXC_OBJECT_TYPE, id=data['id'])
        from_exception = EvidenceRef(source_type='object', source_id=exception_ref,
                                     native_version=version, observed_at=observed_at)
        keys = RECORD_KEYS[fact_key]

        if self._has_record(data, keys):
            note = ('；方案批准不等于处置或过账'
                    if fact_key != 'transfer_exception.observation_recorded' else '')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_exception],
                                reason='已登记原' + ('观察' if fact_key.endswith('observation_recorded')
                                                    else '处置' if fact_key.endswith('disposal_recorded')
                                                    else '损失过账') + '记录' + note)
        if data.get('plan') or data.get('plan_id'):
            return _unknown(fact_key, '原详情只看到方案（plan），没有'
                                      + ('观察' if fact_key.endswith('observation_recorded')
                                         else '处置' if fact_key.endswith('disposal_recorded')
                                         else '损失过账')
                                      + '记录；方案批准不等于处置或过账，请在原页面核对')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_exception],
                            reason='本单还没有对应的原' + ('观察' if fact_key.endswith('observation_recorded')
                                                          else '处置' if fact_key.endswith('disposal_recorded')
                                                          else '损失过账') + '记录，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in EXC_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=EXC_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in EXC_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `TransferExceptionReceipt`；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['EXC_ACTION', 'EXC_ACTIONS', 'EXC_CREATE', 'EXC_FACTS', 'EXC_OBJECT_TYPE', 'EXC_ORIGINS',
           'EXC_READ', 'EXC_RECEIPT_OPERATIONS', 'EXC_RESULT_OPERATIONS', 'RECORD_KEYS',
           'TransferExceptionAdapter']
