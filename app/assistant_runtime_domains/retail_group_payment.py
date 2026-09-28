"""零售集团与门店规则（retail_group_payment）适配器：原集团混合支付单的只读投影。

- 只读 `GET /api/retail-group/orders/{case_id}`（reviewed catalog 内），不调用业务 command。
- 占用、核销、恢复是三件不同的事实：每条只证明**实际一笔**占用/核销/恢复，
  **不证明整单现金到账**；券与套餐待凑整额度不可消费。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

GROUP_READ = 'GET /api/retail-group/orders/{case_id}'
GROUP_CATALOG = 'GET /api/retail-group/orders/{case_id}/catalog'
GROUP_ACTION = 'POST /api/retail-group/orders/{case_id}/actions/{action}'
GROUP_ACTIONS = ('authorize', 'reserve', 'capture', 'release', 'restore', 'reassign')
GROUP_RESULT_OPERATIONS = frozenset({GROUP_READ, GROUP_ACTION})
GROUP_RECEIPT_OPERATIONS = frozenset({GROUP_ACTION})
GROUP_FACTS = ('retail_group.reservation_recorded', 'retail_group.capture_recorded',
               'retail_group.restore_recorded')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的集团混合支付单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _tenders(data):
    value = data.get('tenders')
    return [item for item in value if type(item) is dict] if isinstance(value, list) else []


class RetailGroupPaymentAdapter(FlowCaseAdapter):
    """`kind=retail`（集团混合支付）的原 Case；事实按原 tender 逐笔判定。"""

    name = 'retail_group_payment'
    object_types = ('case',)

    async def _group_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(GROUP_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此集团支付单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('case_id')) or data.get('case_id') != values['id']
                or not _positive_id(data.get('plan_id')) or not isinstance(data.get('tenders'), list)):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._group_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['case_id'])
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=None,
                tasks=[],
                # 原详情只给岗位筛选后的动作名；可用性不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in GROUP_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in GROUP_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='零售集团与门店规则未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._group_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['case_id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)
        tenders = _tenders(data)
        if not tenders:
            return _unknown(fact_key, '原详情未提供集团支付明细（可能岗位不可见），请在原单核对')

        if fact_key == 'retail_group.reservation_recorded':
            for tender in tenders:
                if _positive_id(tender.get('reservation_version')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原占用（tender; 单笔）；整单是否齐备以原单为准，'
                                               '且不证明现金到账')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原集团占用记录，请在原页面核对')

        if fact_key == 'retail_group.capture_recorded':
            for tender in tenders:
                if tender.get('status') == 'captured':
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原核销（单笔）；只证明该笔实际核销，不证明整单现金到账')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='本单还没有原核销记录，请在原页面核对')

        # retail_group.restore_recorded：以原恢复读法为准（原详情把已结束的 tender 标为 released）。
        for tender in tenders:
            if tender.get('status') == 'released':
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已存在原恢复（单笔）；恢复保留原批次有效期，'
                                           '原发行退款须由原发行店另行办理')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                            reason='本单还没有原恢复记录，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in GROUP_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('case_id')):
            return []
        return [BusinessObjectRef(type='case', id=data['case_id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in GROUP_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审的 flow receipt resolver 绑定；冻结快照与 request_id 由调用方提供。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['GROUP_ACTION', 'GROUP_ACTIONS', 'GROUP_CATALOG', 'GROUP_FACTS', 'GROUP_READ',
           'GROUP_RECEIPT_OPERATIONS', 'GROUP_RESULT_OPERATIONS', 'RetailGroupPaymentAdapter']
