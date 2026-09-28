"""经营报表与日报（management_report）适配器：只读面 + 明确的安全边界。

**已核对的事实（如实登记，不猜也不越界）**：
- 计划点名的 `GET /api/dashboard`、`GET /api/reports`、`GET /api/reports/{report_id}` **都不在 reviewed
  catalog 内**（`dashboard`/`reports` 属原网关的 CLOSED 域，GET 也被过滤），因此**没有已评审读取可用**；
- 唯一可用的已评审只读是 `GET /api/flow/analytics`；
- **日报生成 POST 属 `CLASSIFIED_BLOCKED_WRITES`**（原清单为 `POST /api/reports/generate` 与
  `POST /api/reports/preview`）：这是安全边界本身，助手**不得准备也不得调用**。

因此本适配器：
- `object_types=('report_query', 'daily_report')`；
- `report_query`：`read_snapshot` 明确"冻结查询由核心运行时提供"（503 + 零读取），
  并提供受控只读原语 `read_flow_analytics(principal)`（仅此一条已评审读取）；
- `daily_report`：`read_snapshot` 报告"既无已评审读取、生成写又属被挡写入"（503 + 零读取）；
- `fact_keys=()`：不注册任何事实键——报表/日报数字不生成经营、收款或结清事实。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

MGMT_QUERY_TYPE = 'report_query'
MGMT_DAILY_TYPE = 'daily_report'
MGMT_ANALYTICS = 'GET /api/flow/analytics'
MGMT_UNREGISTERED = (
    'GET /api/dashboard',
    'GET /api/reports',
    'GET /api/reports/{report_id}',
)
MGMT_BLOCKED_WRITE = 'POST /api/reports/generate'
MGMT_BLOCKED_PREVIEW = 'POST /api/reports/preview'
MGMT_RESULT_OPERATIONS = frozenset()
MGMT_RECEIPT_OPERATIONS = frozenset()
MGMT_FACTS = ()
QUERY_FROM_CORE = ('冻结的报表查询由核心运行时按员工本人的查询对象提供；适配器不读助手自己的对象表，'
                   '也不猜参数，请由核心传入查询参数或回到原页面查看。')
NO_REGISTERED_READ = ('原 dashboard/reports 属封闭域、不在已评审 catalog 内，没有可用的已评审读取；'
                      '日报生成写又属 CLASSIFIED_BLOCKED_WRITES（安全边界本身），助手不得准备或调用，'
                      '请到原页面查看经营报表与日报。')
BLOCKED_NOTE = ('日报生成属于被挡写入（CLASSIFIED_BLOCKED_WRITES）：助手不得准备、不得调用，'
                '也不得把报表数字当成日报已生成或经营已结清的事实。')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的报表数据不完整，请稍后重新核对') from None


class ManagementReportAdapter(FlowCaseAdapter):
    """经营报表/日报适配器：只暴露一条已评审只读，写路径按安全边界拒绝。"""

    name = 'management_report'
    object_types = (MGMT_QUERY_TYPE, MGMT_DAILY_TYPE)
    fact_keys = ()

    def _ref(self, ref, expected):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != expected
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的报表对象')
        return values

    async def read_flow_analytics(self, principal):
        """唯一已评审的只读原语；无参数、无筛选，结果口径由原 API 裁定。"""
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(MGMT_ANALYTICS, path_args={}, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此统计，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        ref_type = values.get('type') if type(values) is dict else None
        if ref_type == MGMT_DAILY_TYPE:
            self._ref(ref, MGMT_DAILY_TYPE)
            store_id = getattr(principal, 'store_id', None)
            if not _positive_id(store_id):
                raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
            raise HTTPException(503, NO_REGISTERED_READ)
        self._ref(ref, MGMT_QUERY_TYPE)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        raise HTTPException(503, QUERY_FROM_CORE)

    async def fact_snapshot(self, principal, ref, fact_key):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        ref_type = values.get('type') if type(values) is dict else None
        self._ref(ref, MGMT_DAILY_TYPE if ref_type == MGMT_DAILY_TYPE else MGMT_QUERY_TYPE)
        try:
            return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                reason='经营报表不注册任何事实键（报表/日报数字不生成经营、收款或结清事实）；'
                                       + BLOCKED_NOTE)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '事实标识不正确') from None

    def extract_result(self, operation_id, response):
        # 本领域没有可用的写 operation：任何响应都不绑定业务结果。
        return []

    async def read_receipt(self, principal, submission):
        try:
            SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                             reason_code='read_only_report')


__all__ = ['BLOCKED_NOTE', 'MGMT_ANALYTICS', 'MGMT_BLOCKED_PREVIEW', 'MGMT_BLOCKED_WRITE', 'MGMT_DAILY_TYPE', 'MGMT_FACTS',
           'MGMT_QUERY_TYPE', 'MGMT_RECEIPT_OPERATIONS', 'MGMT_RESULT_OPERATIONS', 'MGMT_UNREGISTERED',
           'NO_REGISTERED_READ', 'QUERY_FROM_CORE', 'ManagementReportAdapter']
