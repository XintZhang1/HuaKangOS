"""字典条目（dictionary_entry）适配器：原 `flow Reference` 的受控读取面。

- 只读 `GET /api/dictionaries/{group}`（reviewed catalog 内）与 `GET /api/dictionaries/catalog`；
  写入只走已评审 `POST /api/dictionaries/{group}` 与 `PUT /api/dictionaries/{group}/{record_id}`。
- `object_type=dictionary_entry` 指**原 `flow Reference.id`**；原 `category` 与 dictionary group 是**固定映射**，
  但 `BusinessObjectRef` 只有 `(type, id)`：**group 属"由核心提供的冻结输入"**——
  核心未提供时明确报告边界并**零读取**，绝不猜 group、也不跨组扫库。
- 事实：`dictionary.record_exists`（**原指定 group** 的授权列表精确命中 `Reference.id`）、
  `dictionary.active`（该原记录 `active=true`，缺字段为 unknown）。
- **不把显示中文猜成业务 value/状态枚举**：原条目字段只有 `name`/`detail`/`active`。
"""
from datetime import datetime, timezone
import re as _re

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

DICT_OBJECT_TYPE = 'dictionary_entry'
DICT_LIST = 'GET /api/dictionaries/{group}'
DICT_CATALOG = 'GET /api/dictionaries/catalog'
DICT_CREATE = 'POST /api/dictionaries/{group}'
DICT_UPDATE = 'PUT /api/dictionaries/{group}/{record_id}'
DICT_RESULT_OPERATIONS = frozenset({DICT_CREATE, DICT_UPDATE})
DICT_RECEIPT_OPERATIONS = frozenset({DICT_CREATE, DICT_UPDATE})
DICT_FACTS = ('dictionary.record_exists', 'dictionary.active')
GROUP_PATTERN = _re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
PAGE_SIZE = 100  # 原接口 page_size 上限（Query(30, ge=1, le=100)）
MAX_PAGES = 50
PAGE_WINDOW = ('超过原列表分页窗口仍未命中，且无法确认已翻完：不判定为条目不存在，'
               '请在原页面核对')
GROUP_FROM_CORE = ('字典条目的 group 由原 category 固定映射而来，属核心运行时提供的冻结输入；'
                   '适配器不猜 group、不跨组扫描，请由核心传入 group 或回到原页面查看。')
NO_ENUM_GUESSING = ('原条目字段只有 name/detail/active：不把显示中文当成业务 value 或状态枚举')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的字典不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class DictionaryEntryAdapter(FlowCaseAdapter):
    """`object_type=dictionary_entry` 的原字典条目；group 由核心提供的冻结输入决定。"""

    name = 'dictionary_entry'
    object_types = (DICT_OBJECT_TYPE,)
    fact_keys = DICT_FACTS

    def _entry_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != DICT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原字典条目')
        return values

    @staticmethod
    def _check_group(group):
        if type(group) is not str or not GROUP_PATTERN.match(group):
            raise HTTPException(422, '字典分组不正确，请由核心按原 category 映射传入 group')
        return group

    async def read_group(self, principal, group, q='', page=1):
        """受评审的只读原语：读原指定 group 的**指定页**（不支持跨组、不支持猜 group）。"""
        self._check_group(group)
        if type(q) is not str or len(q) > 120:
            raise HTTPException(422, '查询串不正确')
        if not _positive_id(page):
            raise HTTPException(422, '页码不正确')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        query = {'page': page, 'page_size': PAGE_SIZE}
        if q:
            query['q'] = q
        try:
            response = await self._native_reader(DICT_LIST, path_args={'group': group},
                                                 query=query, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原字典不存在或当前账号不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原字典不存在或当前账号不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原字典暂不能读取，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        items = data.get('items')
        if not isinstance(items, list):
            return None
        return items

    async def read_entry(self, principal, group, entry_id):
        """受评审的只读原语：在**指定 group** 内按 page **完整分页**精确命中真实 ID。

        原分组列表带 `page`/`page_size`：只有分页信息确认翻完才能判"条目不存在"，
        否则一律未知（空页/缺 items/超出窗口都不判不存在）。
        """
        page = 1
        while page <= MAX_PAGES:
            items = await self.read_group(principal, group, page=page)
            if items is None:
                return None, '原字典未返回可核对的分组明细（items），无法确认条目是否存在'
            for item in items:
                if type(item) is dict and item.get('id') == entry_id:
                    return item, None
            if len(items) < PAGE_SIZE:
                # 不满一页即已到末页（原接口 page_size 语义）
                return None, None
            page += 1
        return None, PAGE_WINDOW

    async def read_snapshot(self, principal, ref):
        self._entry_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        # group 是核心提供的冻结输入：这里不猜、不跨组扫描。
        raise HTTPException(503, GROUP_FROM_CORE)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._entry_ref(ref)
        if fact_key not in DICT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='字典条目未登记此事实，请按对应业务能力核对；' + NO_ENUM_GUESSING)
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        return _unknown(fact_key, GROUP_FROM_CORE + '（group 未提供时零读取，不判定存在与否）')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in DICT_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        record = data.get('record') if type(data.get('record')) is dict else data
        if not _positive_id(record.get('id')):
            return []
        return [BusinessObjectRef(type=DICT_OBJECT_TYPE, id=record['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in DICT_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['DICT_CATALOG', 'DICT_CREATE', 'DICT_FACTS', 'DICT_LIST', 'DICT_OBJECT_TYPE',
           'DICT_RECEIPT_OPERATIONS', 'DICT_RESULT_OPERATIONS', 'DICT_UPDATE', 'GROUP_FROM_CORE',
           'GROUP_PATTERN', 'MAX_PAGES', 'NO_ENUM_GUESSING', 'PAGE_SIZE', 'PAGE_WINDOW', 'DictionaryEntryAdapter']
