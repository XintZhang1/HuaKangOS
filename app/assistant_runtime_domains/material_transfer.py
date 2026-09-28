"""物资调拨（material_transfer）适配器：原调拨单的只读投影。

- 只读 `GET /api/transfers/{key}`（reviewed catalog 内），不调用业务 command；
  **key 即原 `MaterialTransfer.id`**（与登记的对象类型一致）。
- 发出、接收、退回接收是三件不同的事实：**至少一行记录不代表整批齐收**；
  只认原 `TransferMovement`（保留 `line_id`/数量与双方店），未提供时返回未知。
- 原 native version 取原单 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

TRANSFER_OBJECT_TYPE = 'material_transfer'
TRANSFER_READ = 'GET /api/transfers/{key}'
TRANSFER_CREATE = 'POST /api/transfers'
TRANSFER_ACTION = 'POST /api/transfers/{key}/actions/{action}'
TRANSFER_DESTINATIONS = 'GET /api/transfers/destinations'
TRANSFER_ACTIONS = ('dispatch', 'receive', 'return_ship', 'return_receive')
TRANSFER_STATES = ('requested', 'approved', 'transit', 'completed', 'cancelled')
TRANSFER_RESULT_OPERATIONS = frozenset({TRANSFER_READ, TRANSFER_CREATE, TRANSFER_ACTION})
TRANSFER_RECEIPT_OPERATIONS = frozenset({TRANSFER_CREATE, TRANSFER_ACTION})
TRANSFER_FACTS = ('material_transfer.dispatch_recorded', 'material_transfer.receive_recorded',
                  'material_transfer.return_receive_recorded')
MOVEMENT_KINDS = {'material_transfer.dispatch_recorded': ('dispatch', 'ship'),
                  'material_transfer.receive_recorded': ('receive',),
                  'material_transfer.return_receive_recorded': ('return_receive',)}
MOVEMENT_KEYS = ('kind', 'movement', 'source', 'action')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的调拨单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class MaterialTransferAdapter(FlowCaseAdapter):
    """`object_type=material_transfer` 的原调拨单；key 即原单 id。"""

    name = 'material_transfer'
    object_types = (TRANSFER_OBJECT_TYPE,)

    def _transfer_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != TRANSFER_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原物资调拨单')
        return values

    async def _transfer_detail(self, principal, ref):
        values = self._transfer_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(TRANSFER_READ, path_args={'key': values['id']},
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
            raise HTTPException(status, '原业务暂不能读取此调拨单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or response.get('truncated')
                or not _positive_id(data.get('id')) or data.get('id') != values['id']
                or not isinstance(data.get('lines'), list)):
            _invalid()
        state = data.get('status') or data.get('state')
        if state is not None and state not in TRANSFER_STATES:
            raise HTTPException(422, '这不是原物资调拨单，请到对应业务页面办理')
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._transfer_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        transfer_ref = BusinessObjectRef(type=TRANSFER_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=transfer_ref, native_version=version,
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=(data.get('status') or data.get('state')) if type(data.get('status') or data.get('state')) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in TRANSFER_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=transfer_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    @staticmethod
    def _movements(data):
        value = data.get('movements')
        return [item for item in value if type(item) is dict] if isinstance(value, list) else None

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in TRANSFER_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='物资调拨未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._transfer_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        transfer_ref = BusinessObjectRef(type=TRANSFER_OBJECT_TYPE, id=data['id'])
        from_transfer = EvidenceRef(source_type='object', source_id=transfer_ref,
                                    native_version=version, observed_at=observed_at)
        movements = self._movements(data)
        if movements is None:
            return _unknown(fact_key, '原详情未提供调拨流水（TransferMovement），'
                                      '无法确证发出/接收/退回接收，请在原页面核对')

        wanted = MOVEMENT_KINDS[fact_key]
        for movement in movements:
            kind = None
            for key in MOVEMENT_KEYS:
                value = movement.get(key)
                if type(value) is str and value.strip():
                    kind = value.strip().lower()
                    break
            if kind is None or kind not in wanted:
                continue
            if not _positive_id(movement.get('line_id')):
                return _unknown(fact_key, '原调拨流水缺少行引用（line_id），请在原页面核对')
            quantity = movement.get('quantity_milli')
            if not (type(quantity) is int and quantity > 0):
                return _unknown(fact_key, '原调拨流水数量不完整，请在原页面核对')
            from_store = movement.get('from_store_id')
            to_store = movement.get('to_store_id')
            stores = []
            for label, value in (('from', from_store), ('to', to_store)):
                if value is not None:
                    if not _positive_id(value):
                        return _unknown(fact_key, '原调拨流水的双方门店引用不完整，请在原页面核对')
                    stores.append(label + '=' + str(value))
            note = ('；双方店：' + '/' .join(stores)) if stores else ''
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_transfer],
                                reason='已登记原调拨流水（保留 line_id/数量）' + note +
                                       '；至少一行记录不代表整批齐收')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_transfer],
                            reason='本单还没有对应的原调拨流水，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in TRANSFER_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=TRANSFER_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in TRANSFER_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执族 `TransferReceipt`（原 `execute` 的 action/payload 摘要）；冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['MOVEMENT_KINDS', 'MOVEMENT_KEYS', 'TRANSFER_ACTION', 'TRANSFER_ACTIONS',
           'TRANSFER_CREATE', 'TRANSFER_DESTINATIONS', 'TRANSFER_FACTS', 'TRANSFER_OBJECT_TYPE',
           'TRANSFER_READ', 'TRANSFER_RECEIPT_OPERATIONS', 'TRANSFER_RESULT_OPERATIONS',
           'TRANSFER_STATES', 'MaterialTransferAdapter']
