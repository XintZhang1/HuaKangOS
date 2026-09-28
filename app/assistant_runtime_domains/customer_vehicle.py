"""客户档案与服务单（customer_vehicle）适配器：原客户车辆的只读投影。

- 只读 `GET /api/customer-service/vehicles/{vehicle_id}` 与同族
  `GET /api/customer-service/vehicles/{vehicle_id}/history`（reviewed catalog 内），
  不调用业务 command。
- 客户关联、观察记录、历史关联是三件不同的事实：**历史关联不证明仍能读取关联原单正文**；
  观察记录只在原详情确实提供时判定，否则未知，不猜。
- 原 native version 取原详情的 version；缺失即 None，不造版本。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

VEHICLE_OBJECT_TYPE = 'customer_vehicle'
VEHICLE_READ = 'GET /api/customer-service/vehicles/{vehicle_id}'
VEHICLE_HISTORY = 'GET /api/customer-service/vehicles/{vehicle_id}/history'
VEHICLE_CREATE = 'POST /api/customer-service/vehicles'
VEHICLE_UPDATE = 'POST /api/customer-service/vehicles'
VEHICLE_OBSERVATION = 'POST /api/customer-service/vehicles/{vehicle_id}/observations'
VEHICLE_HISTORY_LINK = 'POST /api/customer-service/vehicles/{vehicle_id}/history-links'
VEHICLE_RESULT_OPERATIONS = frozenset({VEHICLE_READ, VEHICLE_HISTORY, VEHICLE_CREATE,
                                       VEHICLE_OBSERVATION, VEHICLE_HISTORY_LINK})
VEHICLE_RECEIPT_OPERATIONS = frozenset({VEHICLE_CREATE, VEHICLE_OBSERVATION, VEHICLE_HISTORY_LINK})
VEHICLE_FACTS = ('customer_vehicle.customer_linked', 'customer_vehicle.observation_recorded',
                 'customer_vehicle.history_link_recorded')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的客户车辆记录不完整，请稍后重新核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


class CustomerVehicleAdapter(FlowCaseAdapter):
    """`object_type=customer_vehicle` 的原客户车辆。"""

    name = 'customer_vehicle'
    object_types = (VEHICLE_OBJECT_TYPE,)

    def _vehicle_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != VEHICLE_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的原客户车辆')
        return values

    async def _read(self, principal, operation_id, path_args):
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(operation_id, path_args=path_args, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此客户车辆，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        return response.get('data')

    async def _vehicle_detail(self, principal, ref):
        values = self._vehicle_ref(ref)
        data = await self._read(principal, VEHICLE_READ, {'vehicle_id': values['id']})
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or data['id'] != values['id']):
            _invalid()
        return data

    async def read_snapshot(self, principal, ref):
        data = await self._vehicle_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        vehicle_ref = BusinessObjectRef(type=VEHICLE_OBJECT_TYPE, id=data['id'])
        try:
            return BusinessObjectSnapshot(
                ref=vehicle_ref, native_version=version,
                display_number=data.get('vin') if type(data.get('vin')) is str else None,
                state=data.get('status') if type(data.get('status')) is str else None,
                tasks=[],
                # 原详情不返回动作可用性：不猜（合同第 6 条）。
                available_actions=[AvailableAction(action_key=key, availability='unknown')
                                   for key in ('update', 'observe', 'history_link')],
                evidence_refs=[EvidenceRef(source_type='object', source_id=vehicle_ref,
                                           native_version=version, observed_at=observed_at)],
                manual_route=None, observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in VEHICLE_FACTS:
            try:
                return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                    reason='客户档案未登记此事实，请按对应业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        data = await self._vehicle_detail(principal, ref)
        observed_at = _now()
        version = data.get('version') if _positive_id(data.get('version')) else None
        vehicle_ref = BusinessObjectRef(type=VEHICLE_OBJECT_TYPE, id=data['id'])
        from_vehicle = EvidenceRef(source_type='object', source_id=vehicle_ref,
                                   native_version=version, observed_at=observed_at)

        if fact_key == 'customer_vehicle.customer_linked':
            customer_id = data.get('customer_id')
            if not _positive_id(customer_id):
                return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_vehicle],
                                    reason='原车辆记录没有可读客户引用，请先在原页面关联客户')
            return FactSnapshot(fact_key=fact_key, satisfied=True, reason=None, evidence_refs=[
                EvidenceRef(source_type='object', source_id=BusinessObjectRef(type='customer', id=customer_id),
                            native_version=None, observed_at=observed_at),
                from_vehicle,
            ])

        if fact_key == 'customer_vehicle.history_link_recorded':
            history = await self._read(principal, VEHICLE_HISTORY, {'vehicle_id': data['id']})
            links = history.get('items') if type(history) is dict and isinstance(history.get('items'), list) \
                else history if isinstance(history, list) else None
            if links is None:
                return _unknown(fact_key, '原历史关联读取未返回可判定的清单，请在原页面核对')
            for link in links:
                if (type(link) is dict and _positive_id(link.get('id'))
                        and link.get('vehicle_id') in (None, data['id'])):
                    if link.get('vehicle_id') is None and not _positive_id(data.get('id')):
                        continue
                    return FactSnapshot(
                        fact_key=fact_key, satisfied=True, evidence_refs=[from_vehicle],
                        reason='存在原历史关联且与该车辆一致；**历史关联不证明仍能读取关联原单正文**')
            return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_vehicle],
                                reason='本车还没有原历史关联，请在原页面核对')

        # customer_vehicle.observation_recorded：必须原 VehicleObservation，并保留观察类型/日期/来源；
        # 车辆详情未提供观察清单时返回未知，不猜。
        observations = data.get('observations')
        if not isinstance(observations, list):
            return _unknown(fact_key, '车辆详情未提供原观察清单（需原 VehicleObservation 读取），'
                                      '请在原页面核对观察记录')
        for item in observations:
            if (type(item) is dict and _positive_id(item.get('id'))
                    and type(item.get('kind')) is str and item.get('kind').strip()
                    and type(item.get('observed_at')) is str and item['observed_at'].strip()):
                return FactSnapshot(fact_key=fact_key, satisfied=True, evidence_refs=[from_vehicle],
                                    reason='已登记原车辆观察（类型/日期保留）')
        return FactSnapshot(fact_key=fact_key, satisfied=False, evidence_refs=[from_vehicle],
                            reason='本车还没有完整的原车辆观察记录，请在原页面核对')

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in VEHICLE_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if type(data) is not dict or data.get('truncated'):
            return []
        vehicle_id = data.get('vehicle_id') if _positive_id(data.get('vehicle_id')) else data.get('id')
        if not _positive_id(vehicle_id):
            return []
        return [BusinessObjectRef(type=VEHICLE_OBJECT_TYPE, id=vehicle_id)]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in VEHICLE_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                                 reason_code='receipt_family_not_registered')
        # 客户服务族回执（原 `customer_service._execute` 摘要）；冻结快照不重新生成请求号。
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['VEHICLE_CREATE', 'VEHICLE_FACTS', 'VEHICLE_HISTORY', 'VEHICLE_HISTORY_LINK',
           'VEHICLE_OBJECT_TYPE', 'VEHICLE_OBSERVATION', 'VEHICLE_READ', 'VEHICLE_RECEIPT_OPERATIONS',
           'VEHICLE_RESULT_OPERATIONS', 'CustomerVehicleAdapter']
