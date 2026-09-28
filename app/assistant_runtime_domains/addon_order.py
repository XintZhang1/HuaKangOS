"""加装单（addon_order）适配器：原加装订单的只读投影。

- 只读 `GET /api/addon-orders/{key}`（reviewed catalog 内）；**key 即原 `Case.id`**
  （注册合同：`AddonOrder.id` 与原 `Case.id` 相同）。
- 写结果只绑定 `POST /api/addon-orders` 与 `POST /api/addon-orders/{key}/actions/{action}`；
  回执族 **AddonReceipt**（原 `addon_service._execute`），**使用冻结的最终提交快照，不能重新生成请求号；
  无回执不得猜成功**。
- 三条事实（字段名逐字取自原 `describe()` 投影）：
  - `addon.installation_recorded`：`installations[]` 中存在关联**真实 `dispatch_id`** 的安装记录；
  - `addon.passed_inspection_recorded`：`inspections[]` 中 `passed=true` **且对应实际安装**；
  - `addon.current_quote_accepted`：**当前报价**（`data.addon_quote_id` 指向的 `quote.id`）
    存在原 `AddonAcceptance`（`acceptances[]` 中 `quote_id` 相同）；
- 边界：**单批合格不能冒充整版全部完成**；**处置变更后必须重读原事实**（每次事实读取都重新调用原详情）。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

ADDON_OBJECT_TYPE = 'case'
ADDON_READ = 'GET /api/addon-orders/{key}'
ADDON_CREATE = 'POST /api/addon-orders'
ADDON_ACTION = 'POST /api/addon-orders/{key}/actions/{action}'
ADDON_ACTIONS = ('quote', 'approve', 'authorize', 'dispatch', 'install', 'quality', 'rectify',
                 'accept', 'receive', 'resolution', 'return_receive', 'refund')
ADDON_RESULT_OPERATIONS = frozenset({ADDON_READ, ADDON_CREATE, ADDON_ACTION})
ADDON_RECEIPT_OPERATIONS = frozenset({ADDON_CREATE, ADDON_ACTION})
ADDON_FACTS = ('addon.installation_recorded', 'addon.passed_inspection_recorded',
               'addon.current_quote_accepted')
BATCH_ONLY = '单批合格不能冒充整版全部完成；处置变更后必须重读原事实'


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的加装单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class AddonOrderAdapter(FlowCaseAdapter):
    """`object_type=case`（原 Case.id 即加装单 id）；事实只认原投影字段。"""

    name = 'addon_order'
    object_types = (ADDON_OBJECT_TYPE,)

    def _case_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != ADDON_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原加装业务单')
        return values

    async def _detail(self, principal, ref):
        values = self._case_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(ADDON_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此加装单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']):
            _invalid()
        if data.get('kind') is not None and data.get('kind') != 'addon':
            raise HTTPException(422, '这不是原加装业务单，请到对应业务页面办理')
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=ADDON_OBJECT_TYPE, id=data['id'])
        state = data.get('state') or data.get('status')
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=state if type(state) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in ADDON_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _container(data, name):
        value = data.get(name)
        return value if isinstance(value, list) else None

    @staticmethod
    def _current_quote_id(data):
        row_data = data.get('data') if isinstance(data.get('data'), dict) else {}
        quote_id = row_data.get('addon_quote_id') or data.get('addon_quote_id')
        if not _positive_id(quote_id):
            quote = data.get('quote')
            quote_id = quote.get('id') if isinstance(quote, dict) else None
        return quote_id if _positive_id(quote_id) else None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in ADDON_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='加装单未登记此事实，请按对应业务能力核对；' + BATCH_ONLY)
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        # 处置变更后必须重读原事实：每次调用都重新读原详情（不缓存）。
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type=ADDON_OBJECT_TYPE, id=data['id'])
        evidence = [EvidenceRef(source_type='object', source_id=case_ref, native_version=version,
                                observed_at=observed_at)]

        if fact_key == 'addon.installation_recorded':
            installations = self._container(data, 'installations')
            if installations is None:
                return _unknown(fact_key, '原详情未提供安装明细（installations），'
                                          '无法确证实际安装；' + BATCH_ONLY)
            for item in installations:
                if type(item) is not dict:
                    continue
                if _positive_id(item.get('dispatch_id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                        reason='已登记原安装记录且关联真实 dispatch_id；' + BATCH_ONLY)
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='本单还没有关联真实 dispatch_id 的原安装记录，请在原页面核对；'
                                       + BATCH_ONLY)

        if fact_key == 'addon.passed_inspection_recorded':
            inspections = self._container(data, 'inspections')
            installations = self._container(data, 'installations')
            if inspections is None or installations is None:
                return _unknown(fact_key, '原详情未提供质检或安装明细（inspections/installations），'
                                          '无法确证质检对应实际安装；' + BATCH_ONLY)
            installed = {item.get('id') for item in installations
                         if type(item) is dict and _positive_id(item.get('id'))}
            for item in inspections:
                if type(item) is not dict or item.get('passed') is not True:
                    continue
                installation_id = item.get('installation_id')
                if _positive_id(installation_id) and installation_id in installed:
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                        reason='已登记 passed=true 的原质检且对应实际安装；' + BATCH_ONLY)
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='本单还没有"合格且对应实际安装"的质检记录，请在原页面核对；'
                                       + BATCH_ONLY)

        acceptances = self._container(data, 'acceptances')
        if acceptances is None:
            return _unknown(fact_key, '原详情未提供接受明细（acceptances，可能岗位不可见），'
                                      '无法确证当前报价已被接受；' + BATCH_ONLY)
        quote_id = self._current_quote_id(data)
        if quote_id is None:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                reason='本单没有当前报价引用（addon_quote_id），请在原页面核对；' + BATCH_ONLY)
        for item in acceptances:
            if type(item) is not dict:
                continue
            if item.get('quote_id') == quote_id:
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                    reason='当前报价存在原接受记录（同 quote_id）；' + BATCH_ONLY)
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                            reason='当前报价还没有原接受记录（acceptances 里无同 quote_id 条目），'
                                   '请在原页面核对；' + BATCH_ONLY)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in ADDON_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        record = data.get('record') if type(data.get('record')) is dict else data
        if not _positive_id(record.get('id')):
            return []
        return [BusinessObjectRef(type=ADDON_OBJECT_TYPE, id=record['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in ADDON_RECEIPT_OPERATIONS or self._receipt_reader is None:
            # 回执族 AddonReceipt：无回执不得猜成功（未绑定即 unsupported）。
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 使用冻结的最终提交快照；request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['ADDON_ACTION', 'ADDON_ACTIONS', 'ADDON_CREATE', 'ADDON_FACTS', 'ADDON_OBJECT_TYPE',
           'ADDON_READ', 'ADDON_RECEIPT_OPERATIONS', 'ADDON_RESULT_OPERATIONS', 'BATCH_ONLY',
           'AddonOrderAdapter']
