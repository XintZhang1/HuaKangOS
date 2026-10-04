"""Original questionnaire versions; independent review is never a model approval."""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..questionnaire_schema import digest, questions
from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef,
    BusinessObjectSnapshot, EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

QUESTIONNAIRE_OBJECT_TYPE = 'questionnaire_version'
QUESTIONNAIRE_READ = 'GET /api/customer-service/questionnaires/versions'
QUESTIONNAIRE_PROPOSE = 'POST /api/customer-service/questionnaires/versions'
QUESTIONNAIRE_REVIEW = 'POST /api/customer-service/questionnaires/versions/{version_id}/review'
QUESTIONNAIRE_FACTS = ('questionnaire.version_published',)
QUESTIONNAIRE_VERSION_STATES = ('pending', 'active', 'superseded', 'rejected')
QUESTIONNAIRE_RESULT_OPERATIONS = frozenset({QUESTIONNAIRE_READ, QUESTIONNAIRE_PROPOSE,
                                           QUESTIONNAIRE_REVIEW})
QUESTIONNAIRE_RECEIPT_OPERATIONS = frozenset({QUESTIONNAIRE_PROPOSE, QUESTIONNAIRE_REVIEW})


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原问卷版本目录不完整，请到原页面重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class QuestionnaireVersionAdapter(FlowCaseAdapter):
    name = 'questionnaire_version'
    object_types = (QUESTIONNAIRE_OBJECT_TYPE,)

    def _version_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != QUESTIONNAIRE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有真实主键的原问卷版本')
        return values

    async def _version(self, principal, ref):
        values = self._version_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(QUESTIONNAIRE_READ, path_args={}, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取问卷版本，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        catalog = response.get('data')
        if (type(catalog) is not dict or response.get('truncated') or catalog.get('truncated')
                or type(catalog.get('items')) is not list or len(catalog['items']) > 200
                or 'active_version_id' not in catalog
                or (catalog.get('active_version_id') is not None
                    and not _positive_id(catalog['active_version_id']))):
            _invalid()
        items = catalog['items']
        # The original gateway keeps the first 100 entries and appends a fixed marker.
        if (len(items) == 101 and type(items[-1]) is dict
                and items[-1] == {'more': '其余记录请缩小查询条件'}):
            items = items[:-1]
        ids = []
        for item in items:
            if (type(item) is not dict or not _positive_id(item.get('id'))
                    or 'more' in item
                    or item.get('store_id') != store_id or type(item.get('store_id')) is not int):
                _invalid()
            ids.append(item['id'])
        if len(ids) != len(set(ids)):
            _invalid()
        matches = [item for item in items if item['id'] == values['id']]
        if not matches:
            # This original directory has no pagination/completeness proof.
            raise HTTPException(503, '最近 200 份目录中无法核对该版本，不能据此认定不存在')
        item = matches[0]
        if (type(item.get('number')) is not int or item['number'] < 2
                or type(item.get('name')) is not str or not item['name'].strip()
                or not _positive_id(item.get('proposed_by'))
                or item.get('state') not in QUESTIONNAIRE_VERSION_STATES
                or type(item.get('active')) is not bool or type(item.get('can_review')) is not bool
                or item['active'] != (catalog.get('active_version_id') == item['id'])):
            _invalid()
        return item

    def _publication(self, item):
        schema = questions(item.get('questions'))
        if schema != item.get('questions') or digest(schema) != item.get('digest'):
            raise ValueError('原题目摘要不一致')
        if 'review' not in item:
            raise ValueError('原复核来源未披露')
        review = item.get('review')
        if review is None:
            if item['state'] != 'pending' or item['active']:
                raise ValueError('原发布状态缺少独立复核')
            return False
        if (type(review) is not dict or not _positive_id(review.get('id'))
                or type(review.get('version_id')) is not int or review['version_id'] != item['id']
                or type(review.get('store_id')) is not int or review['store_id'] != item['store_id']
                or not _positive_id(review.get('actor_id')) or review['actor_id'] == item['proposed_by']
                or review.get('actor_role') not in {'admin', 'manager'}
                or review.get('schema_digest') != item['digest']
                or review.get('decision') not in {'approve', 'reject'}):
            raise ValueError('原独立复核来源不完整')
        approved = review['decision'] == 'approve'
        expected_state = ('active' if item['active'] else 'superseded') if approved else 'rejected'
        if item['state'] != expected_state or (not approved and item['active']):
            raise ValueError('原复核与发布状态不一致')
        return approved

    async def read_snapshot(self, principal, ref):
        item = await self._version(principal, ref)
        try:
            self._publication(item)
            observed_at = _now()
            version_ref = BusinessObjectRef(type=QUESTIONNAIRE_OBJECT_TYPE, id=item['id'])
            return BusinessObjectSnapshot(ref=version_ref, native_version=None,
                display_number=str(item['number']), state=item['state'], tasks=[],
                available_actions=[AvailableAction(action_key='review', availability='unknown')]
                                  if item['can_review'] else [],
                evidence_refs=[EvidenceRef(source_type='object', source_id=version_ref,
                                           native_version=None, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in QUESTIONNAIRE_FACTS:
            try:
                return _unknown(fact_key, '问卷版本未登记此事实，请按原业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        try:
            item = await self._version(principal, ref)
        except HTTPException as exc:
            if exc.status_code == 503:
                return _unknown(fact_key, exc.detail)
            raise
        try:
            approved = self._publication(item)
        except (ValueError, TypeError, OverflowError):
            return _unknown(fact_key, '原题目或独立复核来源不完整，不能认定已发布')
        evidence = EvidenceRef(source_type='object',
            source_id=BusinessObjectRef(type=QUESTIONNAIRE_OBJECT_TYPE, id=item['id']),
            native_version=None, observed_at=_now())
        return FactSnapshot(fact_key=fact_key, satisfied=approved, evidence_refs=[evidence],
            reason='原独立复核已批准发布；被后续版本替代不表示当前生效' if approved
                   else '原版本尚未获独立批准发布')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in QUESTIONNAIRE_RECEIPT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        version = data.get('questionnaire_version')
        if type(version) is not dict or not _positive_id(version.get('id')):
            return []
        return [BusinessObjectRef(type=QUESTIONNAIRE_OBJECT_TYPE, id=version['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in QUESTIONNAIRE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[],
                                 evidence_refs=[], reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['QUESTIONNAIRE_FACTS', 'QUESTIONNAIRE_OBJECT_TYPE', 'QUESTIONNAIRE_PROPOSE',
           'QUESTIONNAIRE_READ', 'QUESTIONNAIRE_RECEIPT_OPERATIONS', 'QUESTIONNAIRE_RESULT_OPERATIONS',
           'QUESTIONNAIRE_REVIEW', 'QUESTIONNAIRE_VERSION_STATES', 'QuestionnaireVersionAdapter']
