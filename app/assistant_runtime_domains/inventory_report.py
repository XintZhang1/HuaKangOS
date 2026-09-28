"""库存报表查询（inventory_report）适配器：原只读报表的受控读取面。

- 只读 `GET /api/inventory-reports/{kind}`（reviewed catalog 内，可带 `date_from`/`date_to`）
  与 `GET /api/inventory-reports/warehouses/options/{kind}`；**本领域没有任何写 operation**。
- `object_type=report_query` 指员工本人的查询对象（WorkItem）：**冻结的 kind 与筛选由核心运行时提供**，
  适配器不读助手自己的表、不猜 kind、也不把报表结果当成库存或交车事实。
- `fact_keys=()`：按计划**不注册任何事实键**（不注册库存完成、交车或入出库事实）。
"""
from datetime import datetime, timezone
import re as _re

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

REPORT_OBJECT_TYPE = 'report_query'
REPORT_READ = 'GET /api/inventory-reports/{kind}'
REPORT_OPTIONS = 'GET /api/inventory-reports/warehouses/options/{kind}'
REPORT_RESULT_OPERATIONS = frozenset()
REPORT_RECEIPT_OPERATIONS = frozenset()
REPORT_FACTS = ()
# 原 API 自己裁定 kind 是否存在；适配器只做形状校验，不枚举、不猜业务类别。
_KIND_PATTERN = _re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
QUERY_FROM_CORE = ('冻结的报表 kind 与筛选由核心运行时按员工本人的查询对象提供；'
                   '适配器不读助手自己的对象表，也不猜 kind，请由核心传入查询参数或回到原页面查看报表。')
READ_ONLY = ('本领域只有只读报表 operation：没有可准备的写动作，也没有可绑定的回执族。')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的报表不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class InventoryReportAdapter(FlowCaseAdapter):
    """只读报表适配器：暴露受控读取原语，不注册事实、不绑定写结果。"""

    name = 'inventory_report'
    object_types = (REPORT_OBJECT_TYPE,)
    fact_keys = ()

    def _query_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != REPORT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的报表查询对象')
        return values

    @staticmethod
    def _check_kind(kind):
        if type(kind) is not str or not _KIND_PATTERN.match(kind):
            raise HTTPException(422, '报表类别不正确，请由核心传入原查询的 kind')
        return kind

    @staticmethod
    def _check_window(date_from, date_to):
        for value in (date_from, date_to):
            if value is not None and type(value) is not str:
                raise HTTPException(422, '报表日期筛选不正确')
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, '报表起止日期顺序不正确')
        return date_from, date_to

    async def read_report(self, principal, kind, date_from=None, date_to=None):
        """受评审的只读报表读取原语；kind 只做形状校验，存在性由原 API 裁定。"""
        self._check_kind(kind)
        self._check_window(date_from, date_to)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        query = {}
        if date_from:
            query['date_from'] = date_from
        if date_to:
            query['date_to'] = date_to
        try:
            response = await self._native_reader(REPORT_READ, path_args={'kind': kind},
                                                 query=query, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原报表不存在或当前账号不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原报表不存在或当前账号不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原报表暂不能读取，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        # 查询对象是助手自己的 WorkItem：适配器不读该表，冻结参数须由核心提供。
        self._query_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        raise HTTPException(503, QUERY_FROM_CORE)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._query_ref(ref)
        try:
            return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                reason='库存报表不注册任何事实键（不注册库存完成、交车或入出库事实），'
                                       '请按对应业务能力核对')
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '事实标识不正确') from None

    def extract_result(self, operation_id, response):
        # 本领域没有写 operation：任何响应都不绑定业务结果。
        return []

    async def read_receipt(self, principal, submission):
        try:
            SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                             reason_code='read_only_report')


__all__ = ['QUERY_FROM_CORE', 'READ_ONLY', 'REPORT_FACTS', 'REPORT_OBJECT_TYPE', 'REPORT_OPTIONS',
           'REPORT_READ', 'REPORT_RECEIPT_OPERATIONS', 'REPORT_RESULT_OPERATIONS',
           'InventoryReportAdapter']
