"""类型化主数据（typed_master）适配器：原 `CATALOG` 十四类主数据的受控读取面。

- 只读 `GET /api/masters/{kind}`（reviewed catalog 内），按 `page` **完整分页**精确命中真实 ID；
  `GET /api/masters/catalog`、`GET /api/masters/lookup/{kind}` 属候选读取，**不绑定结果**。
- 写入只走已评审 `POST /api/masters/{kind}` 与 `PUT /api/masters/{kind}/{record_id}`（按 CATALOG schema）。
- 类型与 kind 为**固定字典映射**（14 类，逐字核对 `app/master_data.py` 的 `CATALOG` 顶层键）：
  **原业务作业 WorkItem 映射为 `master_work_item`（kind `work_items`），不混为 Runtime WorkItem**。
- 事实：`master.record_exists`（**完整分页**精确命中该 ID 才算存在）、`master.active`
  （只认命中记录的 `active` 字段；**缺字段为 unknown**，不用过滤参数反推）。
- 计划未为本项登记回执族：写 operation 的 `read_receipt` 返回 `unsupported`（不臆造回执）。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

MASTER_OBJECT_TYPES = ('vehicle_brand', 'vehicle_series', 'supplier', 'insurer', 'warehouse',
                       'storage_location', 'material_brand', 'material_category',
                       'master_work_item', 'team', 'agency_project', 'vehicle_model',
                       'member_tier', 'item_profile')
MASTER_KINDS = {'vehicle_brand': 'vehicle_brands', 'vehicle_series': 'vehicle_series',
                'supplier': 'suppliers', 'insurer': 'insurers', 'warehouse': 'warehouses',
                'storage_location': 'locations', 'material_brand': 'material_brands',
                'material_category': 'material_categories', 'master_work_item': 'work_items',
                'team': 'teams', 'agency_project': 'agency_projects',
                'vehicle_model': 'vehicle_models', 'member_tier': 'member_tiers',
                'item_profile': 'item_profiles'}
KIND_TO_TYPE = {kind: object_type for object_type, kind in MASTER_KINDS.items()}
MASTER_LIST = 'GET /api/masters/{kind}'
MASTER_CATALOG = 'GET /api/masters/catalog'
MASTER_LOOKUP = 'GET /api/masters/lookup/{kind}'
MASTER_CREATE = 'POST /api/masters/{kind}'
MASTER_UPDATE = 'PUT /api/masters/{kind}/{record_id}'
MASTER_RESULT_OPERATIONS = frozenset({MASTER_CREATE, MASTER_UPDATE})
MASTER_RECEIPT_OPERATIONS = frozenset()
MASTER_FACTS = ('master.record_exists', 'master.active')
MAX_PAGES = 50
EMPTY_PAGE_UNCONFIRMED = ('原列表返回空页但没有可确认的分页信息（total/page_size/has_next），'
                         '无法确认已翻完：不判定为记录不存在，请在原页面核对')
PAGE_WINDOW = '原列表分页窗口内未命中，且无法确认已翻完：不判定为记录不存在，请在原页面核对'


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的主数据不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class TypedMasterAdapter(FlowCaseAdapter):
    """`object_type` ∈ 计划登记的 14 类主数据；key 即对应原实体主键。"""

    name = 'typed_master'
    object_types = MASTER_OBJECT_TYPES
    fact_keys = MASTER_FACTS

    def _master_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') not in MASTER_KINDS
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原主数据记录')
        return values

    async def _page(self, kind, page):
        store_id = None
        return await self._native_reader(MASTER_LIST, path_args={'kind': kind},
                                         query={'page': page}, body=None)

    async def _lookup(self, principal, kind, record_id):
        """按 page 完整分页精确命中；返回 (record, reason)。record 为 None 时 reason 说明原因。"""
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        page = 1
        while page <= MAX_PAGES:
            response = await self._native_reader(MASTER_LIST, path_args={'kind': kind},
                                                 query={'page': page}, body=None)
            if type(response) is not dict or type(response.get('status')) is not int:
                _invalid()
            status = response['status']
            if status in {401, 403, 404}:
                raise HTTPException(404, '原主数据不存在或当前账号不可查看')
            if 400 <= status < 500:
                raise HTTPException(status, '原主数据暂不能读取，请到原页面核对')
            if not 200 <= status < 300:
                raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
            payload = response.get('data')
            if type(payload) is not dict or payload.get('truncated') or response.get('truncated'):
                _invalid()
            items = payload.get('items')
            if not isinstance(items, list):
                return None, '原列表未返回可核对的分页明细（items），无法确认记录是否存在'
            for item in items:
                if type(item) is dict and item.get('id') == record_id:
                    return item, None
            confirmed_end = (payload.get('has_next') is False)
            total = payload.get('total')
            size = payload.get('page_size')
            if type(total) is int and type(size) is int and size > 0 and page * size >= total:
                confirmed_end = True
            if not items:
                # 空页只有在分页信息确认翻完时才能判定“不存在”，否则必须未知
                return (None, None) if confirmed_end else (None, EMPTY_PAGE_UNCONFIRMED)
            if confirmed_end:
                return None, None
            page += 1
        return None, PAGE_WINDOW

    async def read_snapshot(self, principal, ref):
        values = self._master_ref(ref)
        kind = MASTER_KINDS[values['type']]
        record, reason = await self._lookup(principal, kind, values['id'])
        if record is None:
            if reason is None:
                raise HTTPException(404, '原主数据不存在或当前账号不可查看')
            raise HTTPException(503, reason)
        observed_at = _now()
        record_ref = BusinessObjectRef(type=values['type'], id=values['id'])
        state = record.get('active')
        try:
            return BusinessObjectSnapshot(
                ref=record_ref, native_version=None,
                display_number=(record.get('name') if type(record.get('name')) is str else None),
                state=('active' if state is True else 'inactive' if state is False else None),
                tasks=[],
                # 主数据没有业务动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key='edit', availability='unknown')],
                evidence_refs=[EvidenceRef(source_type='object', source_id=record_ref,
                                           native_version=None, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        values = self._master_ref(ref)
        if fact_key not in MASTER_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='类型化主数据未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        kind = MASTER_KINDS[values['type']]
        record, reason = await self._lookup(principal, kind, values['id'])
        observed_at = _now()
        record_ref = BusinessObjectRef(type=values['type'], id=values['id'])
        evidence = [EvidenceRef(source_type='object', source_id=record_ref, native_version=None,
                                observed_at=observed_at)]
        if record is None:
            if reason is None:
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=evidence,
                                    reason='原' + kind + '列表完整翻完后没有该 ID 的记录，请在原页面核对')
            return _unknown(fact_key, reason)
        if fact_key == 'master.record_exists':
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=evidence,
                                reason='已在本类原列表（完整分页）中按真实 ID 精确命中')
        active = record.get('active')
        if active is None or type(active) is not bool:
            return _unknown(fact_key, '原记录未提供 active 字段（或类型不可判），'
                                      '无法确认启用状态，不用过滤参数反推')
        return FactSnapshot(fact_key=fact_key, satisfied=active, evidence_refs=evidence,
                            reason='按原记录 active 字段判定' +
                                   ('（启用）' if active else '（停用）'))

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in MASTER_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        kind = data.get('kind') if type(data.get('kind')) is str else None
        record = data.get('record') if type(data.get('record')) is dict else data
        if not _positive_id(record.get('id')):
            return []
        object_type = KIND_TO_TYPE.get(kind)
        if object_type is None:
            return []
        return [BusinessObjectRef(type=object_type, id=record['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in MASTER_RECEIPT_OPERATIONS or self._receipt_reader is None:
            # 计划未为本项登记回执族：不臆造回执，也不冒充成功。
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['KIND_TO_TYPE', 'MASTER_CATALOG', 'MASTER_CREATE', 'MASTER_FACTS', 'MASTER_KINDS',
           'MASTER_LIST', 'MASTER_LOOKUP', 'MASTER_OBJECT_TYPES', 'MASTER_RECEIPT_OPERATIONS',
           'MASTER_RESULT_OPERATIONS', 'EMPTY_PAGE_UNCONFIRMED', 'MASTER_UPDATE', 'MAX_PAGES', 'PAGE_WINDOW',
           'TypedMasterAdapter']
