"""整车批量导入批次（vehicle_import_batch）适配器。

common contract 第 4 条：只有 reviewed catalog 内登记的 operation 才能读取或准备；
原路由存在不等于助手获准准备。本模块因此**不**调用未登记的
`GET /api/vehicle-imports/batches/{batch_id}`，而是明确报告能力缺口，
让员工回到原页面完成批次审阅与逐行恢复。

已登记（唯一）：`POST /api/vehicle-imports/batches/{batch_id}/actions/{action}`。
批次与逐行结果的分页/完整性无法由当前 reviewed 目录证明，因此三条事实键一律
返回 `satisfied=None` 并说明原因，绝不把状态文字当成业务事实。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import BusinessObjectRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot
from .flow_case import FlowCaseAdapter, _positive_id

IMPORT_OBJECT_TYPE = 'vehicle_import_batch'
IMPORT_ACTION = 'POST /api/vehicle-imports/batches/{batch_id}/actions/{action}'
IMPORT_ACTIONS = ('trial', 'review', 'confirm', 'cancel', 'reassign')
IMPORT_RESULT_OPERATIONS = frozenset({IMPORT_ACTION})
IMPORT_RECEIPT_OPERATIONS = frozenset({IMPORT_ACTION})
IMPORT_FACTS = ('vehicle_import.reviewed', 'vehicle_import.confirmed',
                'vehicle_import.all_rows_result_recorded')
# 原批次详情读取尚未纳入 reviewed catalog（能力缺口），因此不能用于 snapshot/事实。
UNREGISTERED_DETAIL_READ = 'GET /api/vehicle-imports/batches/{batch_id}'
GAP_MESSAGE = ('原批次详情读取尚未纳入已评审能力目录，助手不能读取或续办该批次；'
               '请到原页面完成批次审阅与逐行恢复。')


def _now():
    return datetime.now(timezone.utc)


def _batch_ref(ref):
    values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
    if type(values) is not dict or values.get('type') != IMPORT_OBJECT_TYPE or not _positive_id(values.get('id')):
        raise HTTPException(422, '请选择有效的原导入批次')
    return values


class VehicleImportBatchAdapter(FlowCaseAdapter):
    """只注册已评审的批次动作；批次详情未登记时明确报告能力缺口。"""

    name = 'vehicle_import_batch'
    object_types = (IMPORT_OBJECT_TYPE,)

    async def read_snapshot(self, principal, ref):
        _batch_ref(ref)
        # 不调用未登记的原详情 GET：宁可报告缺口，也不越权读取。
        raise HTTPException(503, GAP_MESSAGE)

    async def fact_snapshot(self, principal, ref, fact_key):
        _batch_ref(ref)
        if fact_key not in IMPORT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='整车导入批次未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        # 行级完整性需要未登记的原详情；在目录补齐前一律未知，不猜 reviewed/confirmed。
        return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                            reason='批次状态与逐行结果需要原详情，但该读取尚未纳入已评审能力目录；'
                                   '请到原页面核对批次与每一行结果')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in IMPORT_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=IMPORT_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in IMPORT_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `VehicleImportRequest`；冻结快照与 request_id 由调用方提供。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, '原业务返回的批次回执不完整，请稍后重新核对') from None


__all__ = ['GAP_MESSAGE', 'IMPORT_ACTION', 'IMPORT_ACTIONS', 'IMPORT_FACTS', 'IMPORT_OBJECT_TYPE',
           'IMPORT_RECEIPT_OPERATIONS', 'IMPORT_RESULT_OPERATIONS', 'UNREGISTERED_DETAIL_READ',
           'VehicleImportBatchAdapter']
