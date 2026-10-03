"""客户关怀服务单（customer_care）适配器：原关怀 Case 的只读投影。

- 只读 `GET /api/customer-service/cases/{case_id}`（reviewed catalog 内），不调用业务 command。
- 跟进、交接、结案是三件不同的事实：**联系不到/拒绝联系保留原 contact_result，不能冒充成功联系**；
  跟进/交接记录只在原详情确实带可识别记录时判定，否则未知，不猜。
- 结案状态沿用原状态机的 `completed`；取消不是结案，未登记状态返回未知。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..questionnaire_schema import (LEGACY_NAME, LEGACY_QUESTIONS, answers, digest, questions)
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
CARE_QUESTIONNAIRE_FACTS = ('questionnaire.binding_frozen', 'questionnaire.response_recorded',
                          'questionnaire.answers_completed')
RECORD_DISCRIMINATORS = ('action', 'kind', 'type')
# 原关怀服务单的结案状态沿用原业务状态机：`close` 动作置 `completed`，`cancel` 置 `cancelled`。
# 不另外发明 `closed` 这类未在原业务出现过的状态名。
CARE_STATES = ('pending', 'working', 'completed', 'cancelled')
CARE_CLOSED_STATE = 'completed'
CARE_CANCELLED_STATE = 'cancelled'


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
        if fact_key in CARE_QUESTIONNAIRE_FACTS:
            return await self._questionnaire_fact(principal, ref, fact_key)
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
            state = data.get('state')
            if state == CARE_CLOSED_STATE:
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])
            if state == CARE_CANCELLED_STATE:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='原关怀服务单已取消，不是已结案；请在原页面核对')
            if state in CARE_STATES:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='原关怀服务单当前仍是待接手或跟进中，尚未结案')
            return _unknown(fact_key, '原详情未提供可判定的关怀状态，请在原页面核对是否已结案')

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

    def _questionnaire_binding(self, data):
        binding = data.get('questionnaire')
        if (type(binding) is not dict or not _positive_id(binding.get('binding_id'))
                or 'version_id' not in binding
                or type(binding.get('number')) is not int
                or type(binding.get('name')) is not str or not binding['name'].strip()
                or type(binding.get('issued_at')) is not str):
            raise ValueError('原冻结发放来源缺失')
        self._questionnaire_time(binding['issued_at'])
        schema = questions(binding.get('questions'))
        if schema != binding.get('questions') or digest(schema) != binding.get('schema_digest'):
            raise ValueError('原冻结题目摘要不一致')
        if binding.get('version_id') is None:
            if (binding['number'] != 1 or binding['name'] != LEGACY_NAME
                    or schema != LEGACY_QUESTIONS):
                raise ValueError('原旧题目来源不一致')
        elif not _positive_id(binding['version_id']) or binding['number'] < 2:
            raise ValueError('原发放版本主键不完整')
        return binding

    def _questionnaire_time(self, value):
        if type(value) is not str or not value.strip():
            raise ValueError('原时间来源缺失')
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)

    def _questionnaire_response(self, data, binding, store_id):
        records = data['records']
        if any(type(row) is not dict for row in records):
            raise ValueError('原关怀记录不完整')
        closed = [row for row in records if row.get('action') == 'close']
        if 'response' not in binding:
            raise ValueError('原答卷来源未披露')
        response = binding.get('response')
        if response is None:
            if closed or data.get('state') not in {'pending', 'working', 'cancelled'}:
                raise ValueError('原关闭和答卷来源不一致')
            return None
        if (type(response) is not dict or not _positive_id(response.get('id'))
                or type(response.get('binding_id')) is not int
                or response['binding_id'] != binding['binding_id']
                or data.get('state') != 'completed' or len(closed) != 1
                or data.get('result') not in {'resolved', 'appointment', 'declined', 'no_response', 'renewed'}):
            raise ValueError('原答卷与本次发放不一致')
        record = closed[0]
        if (not _positive_id(record.get('id')) or type(record.get('case_id')) is not int
                or record['case_id'] != data['id'] or not _positive_id(record.get('actor_id'))
                or type(response.get('record_id')) is not int or response['record_id'] != record['id']
                or type(response.get('actor_id')) is not int or response['actor_id'] != record['actor_id']
                or type(response.get('store_id')) is not int or response['store_id'] != store_id
                or type(record.get('store_id')) is not int or record['store_id'] != store_id):
            raise ValueError('原答卷没有本单同经办结案来源')
        detail = record.get('details')
        if type(detail) is not dict or detail.get('result') != data['result']:
            raise ValueError('原结案结果来源不一致')
        value = response.get('answers')
        normalized = answers(binding['questions'], value, completed=data['result'] == 'resolved')
        if normalized != value:
            raise ValueError('原答卷值不完整')
        if response.get('origin') == 'migration':
            if binding.get('version_id') is not None or binding['number'] != 1:
                raise ValueError('新题目不能冒充旧答卷迁移')
            expected = {key: detail[key] for key in ('satisfaction', 'recommend')
                        if detail.get(key) is not None}
        elif response.get('origin') == 'runtime':
            if (type(detail.get('questionnaire_binding_id')) is not int
                    or detail['questionnaire_binding_id'] != binding['binding_id']
                    or type(detail.get('questionnaire_version')) is not int
                    or detail['questionnaire_version'] != binding['number']
                    or detail.get('questionnaire_schema_digest') != binding['schema_digest']):
                raise ValueError('原答卷未引用本次冻结发放')
            expected = detail.get('answers')
        else:
            raise ValueError('原答卷来源未知')
        answers(binding['questions'], expected, completed=data['result'] == 'resolved')
        if digest(expected) != digest(value):
            raise ValueError('原答卷与原结案回答不一致')
        frozen = {'binding_id': binding['binding_id'], 'record_id': record['id'],
                  'schema_digest': binding['schema_digest'], 'answers': value}
        if (digest(frozen) != response.get('digest')
                or self._questionnaire_time(record.get('created_at')) < self._questionnaire_time(binding['issued_at'])
                or self._questionnaire_time(response.get('created_at')) < self._questionnaire_time(record['created_at'])):
            raise ValueError('原答卷摘要或时间来源不一致')
        return response

    async def _questionnaire_fact(self, principal, ref, fact_key):
        try:
            data = await self._care_detail(principal, ref)
        except HTTPException as exc:
            if exc.status_code == 409:
                return _unknown(fact_key, '原发放来源暂不能核对，不能套用当前新题目')
            raise
        if data['subtype'] != 'questionnaire':
            return _unknown(fact_key, '本单不是问卷，不能作为问卷发放或回答事实')
        if not _positive_id(data.get('version')):
            return _unknown(fact_key, '原关怀版本暂不能核对，请到原问卷核对')
        try:
            binding = self._questionnaire_binding(data)
            response = None if fact_key == 'questionnaire.binding_frozen' else self._questionnaire_response(
                data, binding, getattr(principal, 'store_id', None))
        except (ValueError, TypeError, OverflowError):
            return _unknown(fact_key, '本次冻结题目或原答卷来源不完整，请到原问卷核对')
        evidence = EvidenceRef(source_type='object',
            source_id=BusinessObjectRef(type=CARE_OBJECT_TYPE, id=data['id']),
            native_version=data.get('version') if _positive_id(data.get('version')) else None,
            observed_at=_now())
        if fact_key == 'questionnaire.binding_frozen':
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[evidence],
                                reason='本单保留原发放冻结题目，不套用当前版本')
        if fact_key == 'questionnaire.response_recorded':
            return FactSnapshot(fact_key=fact_key, satisfied=response is not None, evidence_refs=[evidence],
                reason='已记录本次原答卷；未响应或部分回答不等于完整回答' if response is not None
                       else '本单尚无原答卷记录')
        completed = response is not None and data.get('state') == 'completed' and data.get('result') == 'resolved'
        # _questionnaire_response validates every required frozen question for resolved.
        return FactSnapshot(fact_key=fact_key, satisfied=completed, evidence_refs=[evidence],
            reason='原冻结题目已逐题真实完成' if completed else '尚未按原冻结题目完成全部必答题')

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


__all__ = ['CARE_ACTION', 'CARE_ACTIONS', 'CARE_CREATE', 'CARE_FACTS', 'CARE_QUESTIONNAIRE_FACTS', 'CARE_OBJECT_TYPE',
           'CARE_READ', 'CARE_RECEIPT_OPERATIONS', 'CARE_RESULT_OPERATIONS', 'CARE_SUBTYPES',
           'CustomerCareAdapter']
