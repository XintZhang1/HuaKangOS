"""代办与其他客户服务单（service_order）适配器：原服务订单的只读投影。

- 只读 `GET /api/service-orders/{case_id}`（reviewed catalog 内，`subtype=agency/other_income`）；
  **key 即原 `Case.id`**（注册合同：`ServiceOrder.id` 与原 `Case.id` 相同）。
- 写结果只绑定本单族 operation：`POST /api/service-orders` 与
  `POST /api/service-orders/{case_id}/actions/{action}`；回执族 **ServiceRequest**（原 service 层）。
  `POST /api/service-orders/income-items` 与 `POST /api/service-orders/payees` 虽已评审但**非本单作用域**，
  本适配器**不调用**（收入项/收款方由对应能力负责）。
- 三条事实（字段名逐字取自原 `describe()` 投影）：
  - `service.submission_recorded`：本单原 `ServiceSubmission`（`submissions[]`）；
  - `service.external_approved`：原 `ServiceExternalResult.outcome=approved` **且对应当前原项目最新提交**；
  - `service.fulfillment_recorded`：本单原 `ServiceFulfillment` 及 `line_key`（`lines[].fulfilled`）；
- 边界：**至少一项履约不代表全部项目或款项完成**。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

SVC_OBJECT_TYPE = 'case'
SVC_READ = 'GET /api/service-orders/{case_id}'
SVC_CREATE = 'POST /api/service-orders'
SVC_ACTION = 'POST /api/service-orders/{case_id}/actions/{action}'
SVC_INCOME_ITEMS = 'POST /api/service-orders/income-items'
SVC_PAYEES = 'POST /api/service-orders/payees'
SVC_SUBTYPES = ('agency', 'other_income')
SVC_ACTIONS = ('quote', 'approve', 'authorize', 'submit', 'external_result', 'fulfill', 'receive',
               'disburse', 'termination', 'refund')
SVC_RESULT_OPERATIONS = frozenset({SVC_READ, SVC_CREATE, SVC_ACTION})
SVC_RECEIPT_OPERATIONS = frozenset({SVC_CREATE, SVC_ACTION})
SVC_FACTS = ('service.submission_recorded', 'service.external_approved',
             'service.fulfillment_recorded')
PARTIAL = '至少一项履约不代表全部项目或款项完成'
OUTCOMES = ('outcome', 'result', 'status')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的服务单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class ServiceOrderAdapter(FlowCaseAdapter):
    """`object_type=case`（原 Case.id 即服务单 id）；事实不缓存、不推断整单完成。"""

    name = 'service_order'
    object_types = (SVC_OBJECT_TYPE,)

    def _case_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != SVC_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原客户服务单')
        return values

    async def _detail(self, principal, ref):
        values = self._case_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(SVC_READ, path_args={'case_id': values['id']},
                                                 query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此服务单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=SVC_OBJECT_TYPE, id=data['id'])
        state = data.get('state') or data.get('status')
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=state if type(state) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in SVC_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _rows(data, name):
        value = data.get(name)
        return value if isinstance(value, list) else None

    @staticmethod
    def _outcome(record):
        if type(record) is not dict:
            return None
        for key in OUTCOMES:
            value = record.get(key)
            if type(value) is str and value.strip():
                return value.strip().lower()
        return None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in SVC_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='客户服务单未登记此事实，请按对应业务能力核对；' + PARTIAL)
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=SVC_OBJECT_TYPE, id=data['id'])
        evidence = [EvidenceRef(source_type='object', source_id=case_ref, native_version=version,
                                observed_at=observed_at)]

        if fact_key == 'service.submission_recorded':
            submissions = self._rows(data, 'submissions')
            if submissions is None:
                return _unknown(fact_key, '原详情未提供提交明细（submissions），'
                                          '无法确证外部提交；' + PARTIAL)
            for item in submissions:
                if type(item) is dict and _positive_id(item.get('id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                        reason='已登记原外部提交记录（ServiceSubmission）；' + PARTIAL)
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='本单还没有原外部提交记录，请在原页面核对；' + PARTIAL)

        if fact_key == 'service.external_approved':
            submissions = self._rows(data, 'submissions')
            if submissions is None:
                return _unknown(fact_key, '原详情未提供提交明细（submissions），'
                                          '无法判断最新提交及其结果；' + PARTIAL)
            known = [item for item in submissions if type(item) is dict and _positive_id(item.get('id'))]
            if not known:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                    reason='本单还没有可判断的原外部提交，请在原页面核对；' + PARTIAL)
            latest = max(known, key=lambda item: item['id'])
            results = None
            for key in ('results', 'external_results', 'result'):
                value = latest.get(key)
                if isinstance(value, list):
                    results = value
                    break
                if isinstance(value, dict):
                    results = [value]
                    break
            if results is None:
                return _unknown(fact_key, '最新提交未提供外部结果明细，无法确证审批结论；' + PARTIAL)
            for item in results:
                if self._outcome(item) == 'approved':
                    if item.get('submission_id') is not None and item.get('submission_id') != latest['id']:
                        return _unknown(fact_key, '外部结果的 submission_id 与最新提交不一致，'
                                                  '无法确证对应当前项目；' + PARTIAL)
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                        reason='最新原提交的外部结果为 approved；' + PARTIAL)
            for item in results:
                if self._outcome(item) is not None:
                    return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                        reason='最新原提交的外部结果不是 approved，请在原页面核对；'
                                               + PARTIAL)
            return _unknown(fact_key, '外部结果缺少可识别的 outcome，无法确证；' + PARTIAL)

        lines = self._rows(data, 'lines')
        if lines is None:
            return _unknown(fact_key, '原详情未提供服务行明细（lines），'
                                      '无法确证实际履约；' + PARTIAL)
        for item in lines:
            if type(item) is not dict or item.get('fulfilled') is not True:
                continue
            line_key = item.get('line_key')
            if type(line_key) is not str or not line_key.strip():
                return _unknown(fact_key, '原履约行缺少可识别的 line_key，无法确证；' + PARTIAL)
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                reason='已登记原履约记录（ServiceFulfillment，line_key=' + line_key.strip()
                                       + '）；' + PARTIAL)
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                            reason='本单还没有任何已履约行，请在原页面核对；' + PARTIAL)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in SVC_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        record = data.get('record') if type(data.get('record')) is dict else data
        if not _positive_id(record.get('id')):
            return []
        return [BusinessObjectRef(type=SVC_OBJECT_TYPE, id=record['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in SVC_RECEIPT_OPERATIONS or self._receipt_reader is None:
            # 回执族 ServiceRequest：无回执不得猜成功。
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 使用冻结的最终提交快照；request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['OUTCOMES', 'PARTIAL', 'SVC_ACTION', 'SVC_ACTIONS', 'SVC_CREATE', 'SVC_FACTS',
           'SVC_INCOME_ITEMS', 'SVC_OBJECT_TYPE', 'SVC_PAYEES', 'SVC_READ',
           'SVC_RECEIPT_OPERATIONS', 'SVC_RESULT_OPERATIONS', 'SVC_SUBTYPES', 'ServiceOrderAdapter']
