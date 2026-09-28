"""整车批量导入批次（vehicle_import_batch）适配器：原批次的只读投影。

目录规则（M7 共同合同第 4 条，与 `app/business_assistant_gateway._operations()` 一致）：
**写操作必须已在 reviewed catalog 内；GET 由活跃路由发现**，并仍受原 domain/closed/denied/body
过滤与调用时授权。`GET /api/vehicle-imports/batches/{batch_id}` 属后者，因此可用于快照与事实；
`POST /api/vehicle-imports/batches/{batch_id}/actions/{action}` 属前者，已在 JSON 目录内。

- 只读原批次详情，不调用任何业务 command；上传仍是原封闭面。
- 逐行完整性以原 `row_count` 与完整 `rows[]` 为准：任何缺行即 unknown，不用状态文字推断。
- 原 native version 取原详情的 `version`；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot, EvidenceRef,
                                         FactSnapshot, ReceiptLookup, SubmissionSnapshot, TaskSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

IMPORT_OBJECT_TYPE = 'vehicle_import_batch'
IMPORT_READ = 'GET /api/vehicle-imports/batches/{batch_id}'
IMPORT_ACTION = 'POST /api/vehicle-imports/batches/{batch_id}/actions/{action}'
IMPORT_ACTIONS = ('trial', 'review', 'confirm', 'cancel', 'reassign')
IMPORT_RESULT_OPERATIONS = frozenset({IMPORT_READ, IMPORT_ACTION})
IMPORT_RECEIPT_OPERATIONS = frozenset({IMPORT_ACTION})
IMPORT_FACTS = ('vehicle_import.reviewed', 'vehicle_import.confirmed',
                'vehicle_import.all_rows_result_recorded')
# 行结果字段按原批次 kind 确定；未登记的 kind 一律未知。
IMPORT_ROW_RESULT_FIELDS = {'funds': 'funds_request_id', 'shipment': 'shipment_id', 'receipt': 'receipt_id'}


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的导入批次不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class VehicleImportBatchAdapter(FlowCaseAdapter):
    """`object_type=vehicle_import_batch` 的原批次；详情走已发现的 GET，动作走已评审的 POST。"""

    name = 'vehicle_import_batch'
    object_types = (IMPORT_OBJECT_TYPE,)

    def _batch_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != IMPORT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原导入批次')
        return values

    async def _batch_detail(self, principal, ref):
        values = self._batch_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(IMPORT_READ, path_args={'batch_id': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此导入批次，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        if not _positive_id(data.get('id')) or data.get('id') != values['id']:
            _invalid()
        if not isinstance(data.get('rows'), list) or not _positive_id(data.get('row_count')):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        # 批次对象不是 Case：直接投影统一快照 DTO，不复用只接受 case 的父类助手。
        data = await self._batch_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        batch_ref = BusinessObjectRef(type=IMPORT_OBJECT_TYPE, id=data['id'])
        tasks = []
        seen = set()
        for raw in data.get('tasks') or []:
            if type(raw) is not dict or not _positive_id(raw.get('id')) or raw['id'] in seen:
                _invalid()
            seen.add(raw['id'])
            fields = {key: raw[key] for key in
                      ('id', 'key', 'title', 'role', 'assignee_id', 'status', 'due_date', 'version')
                      if raw.get(key) is not None}
            try:
                tasks.append(TaskSnapshot.model_validate(fields))
            except (ValidationError, ValueError, TypeError, OverflowError):
                _invalid()
        try:
            return BusinessObjectSnapshot(
                ref=batch_ref, native_version=version,
                display_number=data.get('source_reference') or None,
                state=data.get('status') if type(data.get('status')) is str else None,
                tasks=tasks,
                # 原批次只返回岗位筛选后的动作名字符串列表：不能当作已验证可用。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in (data.get('actions') or []) if type(key) is str],
                evidence_refs=[EvidenceRef(source_type='object', source_id=batch_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in IMPORT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='整车导入批次未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._batch_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        batch_ref = BusinessObjectRef(type=IMPORT_OBJECT_TYPE, id=data['id'])
        from_batch = EvidenceRef(source_type='object', source_id=batch_ref,
                                 native_version=version, observed_at=observed_at)

        if fact_key == 'vehicle_import.reviewed':
            if data.get('status') == 'reviewed':
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_batch])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_batch],
                                reason='原批次状态不是已审阅，请在原页面核对审阅进度')

        if fact_key == 'vehicle_import.confirmed':
            if data.get('status') == 'confirmed':
                return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_batch])
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_batch],
                                reason='原批次尚未确认，请在原页面核对确认进度')

        # vehicle_import.all_rows_result_recorded：行数与完整 rows 一致，且每一稳定 row.id
        # 都有该 batch.kind 对应的真实结果字段；任何缺行、分页或字段缺失一律未知。
        rows = data.get('rows') or []
        field = IMPORT_ROW_RESULT_FIELDS.get(data.get('kind'))
        if field is None:
            return _unknown(fact_key, '本批次类别未登记逐行结果字段，请到原页面核对每一行结果')
        if len(rows) != data['row_count']:
            return _unknown(fact_key, '原批次行数与本页返回不一致（可能分页或缺行），请重新读取后核对')
        ids = set()
        result_rows = 0
        for row in rows:
            if type(row) is not dict or not _positive_id(row.get('id')):
                return _unknown(fact_key, '原批次存在无法识别的行，请到原页面逐行核对')
            if row['id'] in ids:
                return _unknown(fact_key, '原批次存在重复行标识，请到原页面核对')
            ids.add(row['id'])
            result = row.get('result')
            if isinstance(result, dict) and _positive_id(result.get(field)):
                result_rows += 1
        if result_rows != data['row_count']:
            return _unknown(fact_key, '还有行没有原业务结果，请到原页面核对未完成行')
        return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[from_batch])

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
        # 回执族 `VehicleImportRequest`；冻结快照与 request_id 由调用方提供，绝不重新生成。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['IMPORT_ACTION', 'IMPORT_ACTIONS', 'IMPORT_FACTS', 'IMPORT_OBJECT_TYPE', 'IMPORT_READ',
           'IMPORT_RECEIPT_OPERATIONS', 'IMPORT_RESULT_OPERATIONS', 'IMPORT_ROW_RESULT_FIELDS',
           'VehicleImportBatchAdapter']
