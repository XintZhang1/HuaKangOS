"""库存期间报表（stock_period_report）适配器：原只读期间报表的受控读取面。

- 只读 `GET /api/stock-reports/period`（reviewed catalog 内）；**本领域只有这一条只读 operation**，
  原 `/period/export` 未登记，适配器不得使用。
- `object_type=report_query` 指员工本人的查询对象：**冻结期间与筛选由核心运行时提供**，
  适配器不读助手自己的表、不猜参数（核心未传时明确报告边界）。
- `fact_keys=()`：按计划**不注册任何事实键**——**期末数字不生成库存交接完成事实**。
- 已核对的参数：`date_from` / `date_to` / `item_id`（原签名 `item_id: int | None = Query(None, gt=0)`）；
  如需更多原筛选，须由评审扩展本适配器参数，不在运行时臆造。
"""
from datetime import datetime, timezone
import re as _re

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

PERIOD_OBJECT_TYPE = 'report_query'
PERIOD_READ = 'GET /api/stock-reports/period'
PERIOD_UNREGISTERED_EXPORT = 'GET /api/stock-reports/period/export'
PERIOD_RESULT_OPERATIONS = frozenset()
PERIOD_RECEIPT_OPERATIONS = frozenset()
PERIOD_FACTS = ()
PERIOD_PARAMS = ('date_from', 'date_to', 'item_id')
_DATE_PATTERN = _re.compile(r'^\d{4}-\d{2}-\d{2}$')
QUERY_FROM_CORE = ('冻结的期间与原筛选由核心运行时按员工本人的查询对象提供；'
                   '适配器不读助手自己的对象表，也不猜参数，请由核心传入查询参数或回到原页面查看报表。')
READ_ONLY = ('本领域只有只读期间报表 operation（原 export 未登记）：没有可准备的写动作，'
             '也没有可绑定的回执族。')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的报表不完整，请稍后重新核对') from None


class StockPeriodReportAdapter(FlowCaseAdapter):
    """只读期间报表适配器：暴露受控读取原语，不注册事实、不绑定写结果。"""

    name = 'stock_period_report'
    object_types = (PERIOD_OBJECT_TYPE,)
    fact_keys = ()

    def _query_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != PERIOD_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的报表查询对象')
        return values

    @staticmethod
    def _check_window(date_from, date_to):
        for value in (date_from, date_to):
            if value is not None and (type(value) is not str or not _DATE_PATTERN.match(value)):
                raise HTTPException(422, '报表日期格式不正确（应为 YYYY-MM-DD）')
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, '报表起止日期顺序不正确')
        return date_from, date_to

    @staticmethod
    def _check_item(item_id):
        if item_id is not None and not _positive_id(item_id):
            raise HTTPException(422, '物资 ID 必须是正整数')
        return item_id

    async def read_period_report(self, principal, date_from=None, date_to=None, item_id=None):
        """受评审的只读期间报表读取原语；参数只做形状校验，语义由原 API 裁定。"""
        self._check_window(date_from, date_to)
        self._check_item(item_id)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        query = {}
        if date_from:
            query['date_from'] = date_from
        if date_to:
            query['date_to'] = date_to
        if item_id is not None:
            query['item_id'] = item_id
        try:
            response = await self._native_reader(PERIOD_READ, path_args={}, query=query, body=None)
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
        self._query_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        raise HTTPException(503, QUERY_FROM_CORE)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._query_ref(ref)
        try:
            return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                reason='库存期间报表不注册任何事实键（期末数字不生成库存交接完成事实），'
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


__all__ = ['PERIOD_FACTS', 'PERIOD_OBJECT_TYPE', 'PERIOD_PARAMS', 'PERIOD_READ',
           'PERIOD_RECEIPT_OPERATIONS', 'PERIOD_RESULT_OPERATIONS', 'PERIOD_UNREGISTERED_EXPORT',
           'QUERY_FROM_CORE', 'READ_ONLY', 'StockPeriodReportAdapter']
