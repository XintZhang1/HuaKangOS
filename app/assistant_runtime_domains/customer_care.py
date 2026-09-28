"""客户关怀服务单（customer_care）适配器：原关怀 Case 的只读投影。

- 只读 `GET /api/customer-service/cases/{case_id}`（reviewed catalog 内），不调用业务 command。
- 跟进、交接、结案是三件不同的事实：**联系不到/拒绝联系保留原 contact_result，不能冒充成功联系**；
  跟进/交接记录只在原详情确实带可识别记录时判定，否则未知，不猜。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

CARE_OBJECT_TYPE = 'care_case'
CARE_READ = 'GET /api/customer-service/cases/{case_id}'
CARE_CREATE = 'POST /api/customer-service/cases'
CARE_ACTION = 'POST /api/customer-service/cases/{case_id}/actions/{action}'
CARE_SUBTYPES = ('questionnaire', 'consultation', 'complaint', 'rescue', 'sales_callback',
                 'repair_callback', 'renewal')
CARE_ACTIONS = ('start', 'followup', 'handoff', 'close', 'cancel')
CARE_RESULT_OPERATIONS = frozenset({CARE_READ, CARE_CREATE, CARE_ACTION})
CARE_RECEIPT_OPERATIONS = frozenset({CARE_CREATE, CARE_ACTION})
CARE_FACTS = ('care.followup_recorded', 'care.handoff_recorded', 'care.closed')
RECORD_DISCRIMINATORS = ('action', 'kind', 'type')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的关怀服务单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class CustomerCareAdapter(FlowCaseAdapter):
    """`object_type=care_case` 的原关怀服务单。"""

    name = 'customer_care'
    object_types = (CARE_OBJECT_TYPE,)

    def _care_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != CARE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原关怀服务单')
        return values

    async def _care_detail(self, principal, ref):
        values = self._care_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(CARE_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此关怀服务单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or data.get('subtype') not in CARE_SUBTYPES
                or not isinstance(data.get('records'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._care_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=CARE_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('state') if type(data.get('state')) is str else None,
                tasks=[],
                # 原详情只给岗位筛选后的动作名：可用性不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in (data.get('actions') or []) if type(key) is str],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    def _record_kind(self, record):
        for key in RECORD_DISCRIMINATORS:
            value = record.get(key)
            if type(value) is str and value.strip():
                return value.strip().lower()
        return None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in CARE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='客户关怀未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._care_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=CARE_OBJECT_TYPE, id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        records = [item for item in (data.get('records') or []) if type(item) is dict]
        contact = data.get('result')
        contact_note = ('原联系结果：' + contact) if type(contact) is str and contact.strip() else \
            '原联系结果未标注'

        if fact_key == 'care.closed':
            if data.get('state') == 'closed':
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='原关怀服务单当前不是已结案状态，请在原页面核对')

        want = 'followup' if fact_key == 'care.followup_recorded' else 'handoff'
        if not records:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原跟进/交接记录，请在原页面核对；' + contact_note)
        identified = 0
        for record in records:
            kind = self._record_kind(record)
            if kind is None:
                continue
            identified += 1
            if kind == want:
                if want == 'handoff' and not _positive_id(data.get('assignee_id')):
                    return _unknown(fact_key, '原交接记录存在但当前没有可读负责人，请在原页面核对')
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason=('已登记原' + ('跟进' if want == 'followup' else '交接') +
                                            '记录；' + contact_note +
                                            ('；联系不到或拒绝联系不等于成功联系' if want == 'followup' else '')))
        if identified == 0:
            return _unknown(fact_key, '原记录缺少可识别的动作类型，无法确认'
                                      + ('跟进' if want == 'followup' else '交接') + '，请在原页面核对')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有原' + ('跟进' if want == 'followup' else '交接') +
                                   '记录，请在原页面核对；' + contact_note)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in CARE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        # 创建响应把案件放在 case 键下；动作响应直接返回案件。
        case = data.get('case') if type(data.get('case')) is dict else data
        if not _positive_id(case.get('id')):
            return []
        return [BusinessObjectRef(type=CARE_OBJECT_TYPE, id=case['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in CARE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `CareReceipt`（原 `customer_service._execute` 摘要）；冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['CARE_ACTION', 'CARE_ACTIONS', 'CARE_CREATE', 'CARE_FACTS', 'CARE_OBJECT_TYPE',
           'CARE_READ', 'CARE_RECEIPT_OPERATIONS', 'CARE_RESULT_OPERATIONS', 'CARE_SUBTYPES',
           'CustomerCareAdapter']
