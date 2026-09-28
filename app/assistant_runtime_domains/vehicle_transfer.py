"""整车调拨（vehicle_transfer）适配器：原调拨单的只读投影。

- 只读 `GET /api/vehicle-transfers/{key}`（reviewed catalog 内），不调用业务 command；
  **key 即原 `VehicleTransfer.id`**（与登记的对象类型一致）。
- 接收、退回、丢失是三件不同的事实：**rejected 不能满足 returned**；
  接收/退回必须**状态 **与**同 VIN 的原车移动事实**同时吻合，缺一即未知。
- 原 native version 取原单 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

VT_OBJECT_TYPE = 'vehicle_transfer'
VT_READ = 'GET /api/vehicle-transfers/{key}'
VT_CREATE = 'POST /api/vehicle-transfers'
VT_ACTION = 'POST /api/vehicle-transfers/{key}/actions/{action}'
VT_DESTINATIONS = 'GET /api/vehicle-transfers/destinations'
VT_ACTIONS = ('dispatch', 'accept', 'return_ship', 'return_receive')
VT_STATES = ('requested', 'approved', 'transit', 'rejected', 'return_transit', 'accepted',
             'returned', 'cancelled', 'lost', 'recovered')
VT_RESULT_OPERATIONS = frozenset({VT_READ, VT_CREATE, VT_ACTION})
VT_RECEIPT_OPERATIONS = frozenset({VT_CREATE, VT_ACTION})
VT_FACTS = ('vehicle_transfer.accepted', 'vehicle_transfer.returned', 'vehicle_transfer.lost')
MOVEMENT_KINDS = {'vehicle_transfer.accepted': ('accept', 'receive'),
                  'vehicle_transfer.returned': ('return_receive',)}
MOVEMENT_KEYS = ('kind', 'movement', 'source', 'action')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的整车调拨单不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class VehicleTransferAdapter(FlowCaseAdapter):
    """`object_type=vehicle_transfer` 的原整车调拨单；key 即原单 id。"""

    name = 'vehicle_transfer'
    object_types = (VT_OBJECT_TYPE,)

    def _transfer_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != VT_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原整车调拨单')
        return values

    async def _detail(self, principal, ref):
        values = self._transfer_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(VT_READ, path_args={'key': values['id']},
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
                or not _positive_id(data.get('id')) or data.get('id') != values['id']):
            _invalid()
        state = data.get('status') or data.get('state')
        if state is not None and state not in VT_STATES:
            raise HTTPException(422, '这不是原整车调拨单，请到对应业务页面办理')
        vin = data.get('vin')
        if vin is not None and (type(vin) is not str or not vin.strip()):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        transfer_ref = BusinessObjectRef(type=VT_OBJECT_TYPE, id=data['id'])
        state = data.get('status') or data.get('state')
        try:
            return BusinessObjectSnapshot(
                ref=transfer_ref, native_version=version,
                display_number=(data.get('number') if type(data.get('number')) is str else
                                (data.get('vin') if type(data.get('vin')) is str else None)),
                state=state if type(state) is str else None,
                tasks=[],
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in VT_ACTIONS],
                evidence_refs=[EvidenceRef(source_type='object', source_id=transfer_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in VT_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='整车调拨未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        transfer_ref = BusinessObjectRef(type=VT_OBJECT_TYPE, id=data['id'])
        from_transfer = EvidenceRef(source_type='object', source_id=transfer_ref,
                                    native_version=version, observed_at=observed_at)
        state = data.get('status') or data.get('state')
        vin = data.get('vin') if type(data.get('vin')) is str else None

        if fact_key == 'vehicle_transfer.lost':
            # 丢失只看原状态；不推断找回或赔偿。
            if state == 'lost':
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_transfer],
                                    reason='原状态为 lost；找回或赔偿以原单后续事实为准')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_transfer],
                                reason='原整车调拨单当前不是丢失状态，请在原页面核对')

        want_state = 'accepted' if fact_key == 'vehicle_transfer.accepted' else 'returned'
        if state != want_state:
            note = ''
            if fact_key == 'vehicle_transfer.returned' and state == 'rejected':
                note = '；rejected（已拒绝）不能满足 returned'
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_transfer],
                                reason='原状态不是 ' + want_state + '，请在原页面核对' + note)

        # 状态吻合还不够：必须同 VIN 的原车移动事实吻合。
        if vin is None:
            return _unknown(fact_key, '原详情未提供 VIN，无法与车移动事实核对，请在原页面核对')
        movements = data.get('movements')
        if not isinstance(movements, list):
            return _unknown(fact_key, '原详情未提供车移动流水（VehicleMovement），'
                                      '无法确证同 VIN 的实际移动，请在原页面核对')
        wanted = MOVEMENT_KINDS[fact_key]
        for movement in movements:
            if type(movement) is not dict:
                continue
            kind = None
            for key in MOVEMENT_KEYS:
                value = movement.get(key)
                if type(value) is str and value.strip():
                    kind = value.strip().lower()
                    break
            if kind is None or kind not in wanted:
                continue
            movement_vin = movement.get('vin')
            if type(movement_vin) is not str or movement_vin.strip() != vin:
                return _unknown(fact_key, '原车移动与本单 VIN 不一致，请在原页面核对')
            if not _positive_id(movement.get('id')):
                return _unknown(fact_key, '原车移动缺少可识别标识，请在原页面核对')
            return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_transfer],
                                reason='原状态与原车移动事实吻合（同 VIN）')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_transfer],
                            reason='原状态已是 ' + want_state + '，但还没有对应的原车移动事实，'
                                   '请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in VT_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id')):
            return []
        return [BusinessObjectRef(type=VT_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in VT_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 回执由已评审 resolver 绑定（原整车调拨请求摘要）；冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['MOVEMENT_KINDS', 'MOVEMENT_KEYS', 'VT_ACTION', 'VT_ACTIONS', 'VT_CREATE',
           'VT_DESTINATIONS', 'VT_FACTS', 'VT_OBJECT_TYPE', 'VT_READ', 'VT_RECEIPT_OPERATIONS',
           'VT_RESULT_OPERATIONS', 'VT_STATES', 'VehicleTransferAdapter']
