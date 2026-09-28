"""仓储单据（warehouse_document）适配器：原仓储 Case 的只读投影。

- 只读 `GET /api/warehouse/cases/{case_id}`（reviewed catalog 内），不调用 business command。
- 入库、盘点观察、实际盘差过账是三件不同的事实：**实盘观察/批准/准备分配都不满足实际过账键**。
- 只在原详情确实提供对应事实时判定；未登记的读法一律未知，不猜。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

WH_READ = 'GET /api/warehouse/cases/{case_id}'
WH_CREATE = 'POST /api/warehouse/cases'
WH_COMMAND = 'POST /api/warehouse/cases/{case_id}/commands/{action}'
WH_OPERATIONS = ('activate', 'other_in', 'other_in_return', 'consumable', 'consumable_return',
                 'gift', 'gift_return', 'disposal', 'local_move', 'count')
WH_RESULT_OPERATIONS = frozenset({WH_READ, WH_CREATE, WH_COMMAND})
WH_RECEIPT_OPERATIONS = frozenset({WH_CREATE, WH_COMMAND})
WH_FACTS = ('warehouse.entry_recorded', 'warehouse.count_observed', 'warehouse.count_posted')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的仓储单据不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _items(data, name):
    value = data.get(name)
    return [item for item in value if type(item) is dict] if isinstance(value, list) else []


class WarehouseDocumentAdapter(FlowCaseAdapter):
    """`operation` 由原仓储业务详情给出的原 Case；事实按原单据逐项判定。"""

    name = 'warehouse_document'
    object_types = ('case',)

    async def _wh_detail(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != 'case' or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原业务记录')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(WH_READ, path_args={'case_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此仓储单据，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if (not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not _positive_id(data.get('store_id')) or data['store_id'] != store_id
                or data.get('operation') not in WH_OPERATIONS):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._wh_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        # 原详情给出动作 key 与 label，但不给可用性：统一 unknown（合同第 6 条）。
        actions = []
        for item in _items(data, 'actions'):
            key = item.get('key')
            if type(key) is str and key:
                actions.append(AvailableAction(action_key=key, availability='unknown'))
        try:
            return BusinessObjectSnapshot(
                ref=case_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data.get('state') if type(data.get('state')) is str else None,
                tasks=[],
                available_actions=actions,
                evidence_refs=[EvidenceRef(source_type='object', source_id=case_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in WH_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='仓储单据未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._wh_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        case_ref = BusinessObjectRef(type='case', id=data['id'])
        from_case = EvidenceRef(source_type='object', source_id=case_ref,
                                native_version=version, observed_at=observed_at)

        if fact_key == 'warehouse.entry_recorded':
            entries = _items(data, 'entries')
            if not entries:
                return _unknown(fact_key, '原详情未提供本单出入库流水（entry），请在原单核对实际出入库')
            for entry in entries:
                if _positive_id(entry.get('id')):
                    return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                        reason='已存在原出入库流水（至少一笔）；整单是否完成以原单为准')
            return _unknown(fact_key, '原出入库流水缺少可识别标识，请在原页面对账')

        if fact_key == 'warehouse.count_observed':
            count = data.get('count') if type(data.get('count')) is dict else None
            if count is None:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                    reason='本单还没有原盘点观察（count observation），请在原页面核对')
            counted = count.get('counted_quantity_milli')
            baseline = count.get('baseline_quantity_milli')
            if type(counted) is not int or type(baseline) is not int:
                return _unknown(fact_key, '原盘点观察数据不完整，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                reason='已登记原盘点观察（实盘 ' + str(counted) + '，账 ' + str(baseline) +
                                       '）；实盘观察不等于已过账')

        # warehouse.count_posted：必须原 post_count 成功回执且存在实际盘差 StockMove；
        # 实盘观察、批准、准备分配都不满足本键。该详情未提供盘差过账标记时返回未知。
        moves = _items(data, 'stock_moves')
        count = data.get('count') if type(data.get('count')) is dict else None
        difference = count.get('difference_milli') if count else None
        if difference == 0 and count is not None:
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_case],
                                reason='原盘点无差异，无需盘差过账')
        for move in moves:
            if move.get('purpose') == 'count_adjust' and _positive_id(move.get('id')):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_case],
                                    reason='已存在原盘差过账（StockMove）；实盘观察或批准本身不满足本键')
        return _unknown(fact_key, '需要原 post_count 成功回执与实际盘差 StockMove，'
                                  '该详情未提供该标记，请在原单核对过账结果')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in WH_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('store_id'))):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in WH_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族沿原 `digest(action, values)` 摘要；冻结快照与 request_id 由调用方提供。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['WH_COMMAND', 'WH_CREATE', 'WH_FACTS', 'WH_OPERATIONS', 'WH_READ',
           'WH_RECEIPT_OPERATIONS', 'WH_RESULT_OPERATIONS', 'WarehouseDocumentAdapter']
