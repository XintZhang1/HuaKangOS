"""版本报价与车辆交付（sales_order）适配器：原销售 Case 的报价/交付只读投影。

- 只读 `GET /api/sales-quotes/orders/{key}`（reviewed catalog 内）与同族的 vehicles GET。
- 只登记原 sales_quote 事实键；报价批准、客户同意、真实交付是三件不同的事，
  不以 dispatch、金额结清或状态文字互相替代。
- 原 native version 取原详情的 version/flow_version；缺失即 None，不造版本。
- 本适配器只声明可准备的原 operation，不执行、不生成卡、不改原状态机。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import BusinessObjectRef, EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot
from .flow_case import FlowCaseAdapter, _positive_id

SALES_KIND = 'order'
SALES_FLOW_VERSIONS = (3,)
SALES_READ = 'GET /api/sales-quotes/orders/{key}'
SALES_VEHICLES = 'GET /api/sales-quotes/orders/{key}/vehicles'
SALES_CREATE = 'POST /api/sales-quotes/orders'
SALES_PROPOSE = 'POST /api/sales-quotes/orders/{key}/quotes'
SALES_RESULT_OPERATIONS = frozenset({SALES_READ, SALES_CREATE, SALES_PROPOSE})
SALES_RECEIPT_OPERATIONS = frozenset({SALES_CREATE, SALES_PROPOSE})
SALES_FACTS = ('sales.active_quote_approved', 'sales.active_quote_consented', 'sales.delivery_recorded')
_DELIVERY_KEYS = ('delivered_at', 'delivery_recorded_at', 'delivery_receipt_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的报价记录不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class SalesOrderAdapter(FlowCaseAdapter):
    """`kind == 'order'` 的原销售 Case；报价版本是它的子事实。"""

    name = 'sales_order'
    object_types = ('case',)

    async def _sales_detail(self, principal, ref):
        if not isinstance(ref, BusinessObjectRef) and type(ref) is not dict:
            raise HTTPException(422, '请选择有效的原业务记录')
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if values.get('type') != 'case' or not _positive_id(values.get('id')):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(SALES_READ, path_args={'key': values['id']}, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此单据，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        # 跨店或不可见：按原页面口径当作不存在，不暴露旧快照。
        if not _positive_id(data.get('store_id')) or data['store_id'] != store_id:
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        if data.get('kind') not in (None, SALES_KIND):
            raise HTTPException(422, '这不是原车辆报价与交付单据，请到对应业务页面办理')
        if not _positive_id(data.get('id')) or data.get('id') != values['id'] or data.get('kind') != SALES_KIND:
            _invalid()
        if data.get('flow_version') is not None and not _positive_id(data.get('flow_version')):
            _invalid()
        return data

    def snapshot_from_record(self, ref, record):
        return FlowCaseAdapter.snapshot_from_record(self, ref, record)

    async def read_snapshot(self, principal, ref):
        data = await self._sales_detail(principal, ref)
        store_id = getattr(principal, 'store_id', None)
        record = {
            'id': data['id'], 'store_id': data['store_id'], 'kind': data['kind'],
            'flow_version': data.get('flow_version'), 'version': data.get('version'),
            'number': data.get('number'), 'state': data.get('state'),
            'tasks': data.get('tasks') or [], 'actions': data.get('actions') or [],
            'data': {key: value for key, value in (data.get('data') or {}).items()
                     if key.endswith('_id') and _positive_id(value)},
            'observed_at': _now(),
        }
        if not isinstance(record['tasks'], list) or not isinstance(record['actions'], list):
            _invalid()
        return self.snapshot_from_record(ref, record)

    def _active_quote(self, data):
        quotes = data.get('quotes')
        active_id = data.get('active_quote_id')
        if not isinstance(quotes, list) or not _positive_id(active_id):
            return None
        for quote in quotes:
            if type(quote) is dict and quote.get('id') == active_id:
                return quote
        return None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in SALES_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='车辆报价与交付未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._sales_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else data.get('flow_version')
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'sales.active_quote_approved':
            quote = self._active_quote(data)
            if quote is None:
                return _unknown(fact_key, '原单据还没有生效报价版本，请在原页面核对报价进度')
            review = quote.get('review') if type(quote.get('review')) is dict else {}
            resolution = quote.get('resolution') if type(quote.get('resolution')) is dict else {}
            if review.get('decision') != 'approved':
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='当前生效报价版本尚未获批，请先由原审批人处理')
            if resolution.get('withdrawn_at') or resolution.get('state') == 'withdrawn':
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='当前生效报价的批准已被撤回，请重新核对报价')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])

        if fact_key == 'sales.active_quote_consented':
            active_id = data.get('active_quote_id')
            consent_id = (data.get('data') or {}).get('sales_consent_id')
            if not _positive_id(active_id) or not _positive_id(consent_id):
                return _unknown(fact_key, '需要原客户签回证据与生效报价版本，请在原页面核对签署进度')
            signed = (data.get('data') or {}).get('signed_file')
            if not _positive_id(signed):
                return _unknown(fact_key, '原签回证据尚未登记，请在原页面核对客户签署')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])

        # sales.delivery_recorded：必须由原 deliver 成功回执与重读交付事实吻合证明；
        # dispatch、金额结清或状态文字都不能替代。
        native = data.get('data') if type(data.get('data')) is dict else {}
        recorded = any(native.get(key) for key in _DELIVERY_KEYS)
        if not recorded:
            return _unknown(fact_key, '需要原交付完成回执并重读原交付事实，请在原单核对后再继续')
        return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_case])

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in SALES_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('store_id')) or data.get('kind') != SALES_KIND):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in SALES_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 报价版本族用原 sales_quote_service._execute 的 operation/payload 摘要；
        # 冻结快照与 request_id 由调用方提供，这里绝不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['SALES_CREATE', 'SALES_FACTS', 'SALES_KIND', 'SALES_PROPOSE', 'SALES_READ',
           'SALES_RECEIPT_OPERATIONS', 'SALES_RESULT_OPERATIONS', 'SALES_VEHICLES', 'SalesOrderAdapter']
