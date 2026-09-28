"""精品套餐核销与安装（retail_bundle）适配器：原套餐规则与套餐销售的只读投影。

- 规则侧：只读 `GET /api/retail-bundles/rules/{key}/preview`（reviewed catalog 内），
  返回真实规则与冻结组件/分摊。
- 销售侧：原接口只登记 `POST /api/retail-bundles/sales`，**没有已评审或已发现的销售详情 GET**，
  因此销售对象不编造读取路径：快照明确报告无法读取、事实返回未知，销售结果只经
  `extract_result` 绑定原 POST 成功响应。
- 未适用对象类型返回 unknown；不把规则事实用于销售，也不把销售猜测写成规则事实。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

RULE_OBJECT_TYPE = 'retail_bundle_rule'
SALE_OBJECT_TYPE = 'retail_bundle_sale'
BUNDLE_RULES = 'GET /api/retail-bundles/rules'
BUNDLE_PREVIEW = 'GET /api/retail-bundles/rules/{key}/preview'
BUNDLE_RULE_CREATE = 'POST /api/retail-bundles/rules'
BUNDLE_SALE_CREATE = 'POST /api/retail-bundles/sales'
BUNDLE_RESULT_OPERATIONS = frozenset({BUNDLE_PREVIEW, BUNDLE_RULE_CREATE, BUNDLE_SALE_CREATE})
BUNDLE_RECEIPT_OPERATIONS = frozenset({BUNDLE_RULE_CREATE, BUNDLE_SALE_CREATE})
BUNDLE_FACTS = ('retail_bundle.rule_snapshot_readable', 'retail_bundle.sale_linked')
# 规则预览需要套数参数；助手只做只读规则快照，固定取 1 套（不写任何业务）。
PREVIEW_SETS = 1
SALE_GAP = ('原套餐销售没有已评审或已发现的详情读取路径，助手不能读取该销售单；'
            '请到原页面核对套餐销售与核销进度。')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的套餐规则不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class RetailBundleAdapter(FlowCaseAdapter):
    """规则对象走预览 GET；销售对象只经 POST 结果绑定，不编造读取。"""

    name = 'retail_bundle'
    object_types = (RULE_OBJECT_TYPE, SALE_OBJECT_TYPE)

    def _ref(self, ref, expected):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != expected
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原套餐记录')
        return values

    async def _rule_preview(self, principal, ref):
        values = self._ref(ref, RULE_OBJECT_TYPE)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(BUNDLE_PREVIEW, path_args={'key': values['id']},
                                                 query={'sets': PREVIEW_SETS}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此套餐规则，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not isinstance(data.get('components'), list) or not data['components']):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if type(values) is not dict:
            raise HTTPException(422, '请选择有效的原套餐记录')
        if values.get('type') == SALE_OBJECT_TYPE:
            self._ref(ref, SALE_OBJECT_TYPE)
            raise HTTPException(503, SALE_GAP)
        data = await self._rule_preview(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        rule_ref = BusinessObjectRef(type=RULE_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=rule_ref, native_version=version,
                display_number=data.get('name') if type(data.get('name')) is str else None,
                state=data.get('status') if type(data.get('status')) is str else None,
                tasks=[],
                # 原预览不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in ('create_version', 'publish')],
                evidence_refs=[EvidenceRef(source_type='object', source_id=rule_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in BUNDLE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='精品套餐未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        ref_type = values.get('type') if type(values) is dict else None

        if fact_key == 'retail_bundle.rule_snapshot_readable':
            if ref_type != RULE_OBJECT_TYPE:
                return _unknown(fact_key, '该事实只适用于原套餐规则，请对规则读取')
            data = await self._rule_preview(principal, ref)
            observed_at = _now()
            version = data.get('version') if _positive_id(data.get('version')) else None
            rule_ref = BusinessObjectRef(type=RULE_OBJECT_TYPE, id=data['id'])
            for component in data['components']:
                if (type(component) is not dict or not _positive_id(component.get('item_id'))
                        or not _positive_id(component.get('quantity_milli_per_set'))):
                    return _unknown(fact_key, '原套餐组件不完整，请在原页面核对规则组件与分摊')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[
                EvidenceRef(source_type='object', source_id=rule_ref, native_version=version,
                            observed_at=observed_at)])

        # retail_bundle.sale_linked：需要原套餐销售详情来核对派生 retail Case；
        # 该读取路径不存在也不在目录内，故一律未知，绝不用规则事实代替。
        if ref_type != SALE_OBJECT_TYPE:
            return _unknown(fact_key, '该事实只适用于原套餐销售，请对销售读取')
        self._ref(ref, SALE_OBJECT_TYPE)
        return _unknown(fact_key, SALE_GAP)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in BUNDLE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        # 套餐销售成功结果派生原 retail Case：只绑定真实存在的派生单号。
        if operation_id == BUNDLE_SALE_CREATE:
            for key in ('case_id', 'retail_case_id', 'id'):
                if _positive_id(data.get(key)):
                    return [BusinessObjectRef(type='case', id=data[key])]
            return []
        if _positive_id(data.get('id')):
            return [BusinessObjectRef(type=RULE_OBJECT_TYPE, id=data['id'])]
        return []

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in BUNDLE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 规则版本族沿 `retail_bundle_rule` 摘要；冻结快照与 request_id 由调用方提供。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['BUNDLE_FACTS', 'BUNDLE_PREVIEW', 'BUNDLE_RECEIPT_OPERATIONS', 'BUNDLE_RESULT_OPERATIONS',
           'BUNDLE_RULE_CREATE', 'BUNDLE_RULES', 'BUNDLE_SALE_CREATE', 'PREVIEW_SETS',
           'RULE_OBJECT_TYPE', 'SALE_GAP', 'SALE_OBJECT_TYPE', 'RetailBundleAdapter']
