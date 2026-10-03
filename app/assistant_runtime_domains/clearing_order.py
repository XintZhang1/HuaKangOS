"""Current-party clearing orders projected from their original authorized GETs."""
from datetime import date, datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (
    BusinessObjectRef, BusinessObjectSnapshot, EvidenceRef, FactSnapshot,
    ReceiptLookup, SubmissionSnapshot,
)
from .flow_case import FlowCaseAdapter, _positive_id

CLEARING_OBJECT_TYPE = 'clearing_order'
CLEARING_READ = 'GET /api/reconciliation/clearing/{key}'
CLEARING_CREATE = 'POST /api/reconciliation/clearing'
CLEARING_ACTION = 'POST /api/reconciliation/clearing/{key}/actions/{action}'
CLEARING_FACTS = ('clearing.local_cash_recorded', 'clearing.settled',
                  'clearing.difference_recorded')
CLEARING_KIND = 'interstore_clearing'
CLEARING_FLOW_VERSION = 2
CLEARING_STATES = ('requested', 'paid', 'settled', 'cancelled')
CLEARING_RESULT_OPERATIONS = frozenset({CLEARING_CREATE, CLEARING_ACTION})
CLEARING_RECEIPT_OPERATIONS = CLEARING_RESULT_OPERATIONS
_ORIGIN_KINDS = ('material', 'material_loss', 'material_found', 'vehicle',
                 'vehicle_loss', 'vehicle_found')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原内部清算详情不完整或关联不一致，请到原页面核对') from None


def _unknown(fact_key, reason):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[], reason=reason)


def _calendar_date(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        raise ValueError('原业务日期不完整')


class ClearingOrderAdapter(FlowCaseAdapter):
    name = 'clearing_order'
    object_types = (CLEARING_OBJECT_TYPE,)

    async def _clearing_detail(self, principal, ref):
        try:
            order_ref = BusinessObjectRef.model_validate(
                ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '请选择有真实主键的原内部清算单') from None
        if order_ref.type != CLEARING_OBJECT_TYPE:
            raise HTTPException(422, '此适配器只读取原内部清算单')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(CLEARING_READ,
                path_args={'key': order_ref.id}, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此清算单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if (type(data) is not dict or response.get('truncated') or data.get('truncated')
                or not _positive_id(data.get('id')) or data['id'] != order_ref.id
                or not _positive_id(data.get('payer_store_id'))
                or not _positive_id(data.get('receiver_store_id'))
                or data['payer_store_id'] == data['receiver_store_id']
                or not _positive_id(data.get('case_id'))):
            _invalid()
        if store_id not in (data['payer_store_id'], data['receiver_store_id']):
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        side = 'payer' if store_id == data['payer_store_id'] else 'receiver'
        if data.get('side') != side or data.get('status') not in CLEARING_STATES:
            _invalid()
        for key in ('version', 'case_version'):
            if data.get(key) is not None and not _positive_id(data[key]):
                _invalid()
        # This separate local Case read is already owned by flow_case. The order
        # row's version is never compared with the independent Case version.
        case_ref = BusinessObjectRef(type='case', id=data['case_id'])
        record = await self.read_record(principal, case_ref)
        if (record['kind'] != CLEARING_KIND or record['flow_version'] != CLEARING_FLOW_VERSION
                or record['data'].get('clearing_id') != order_ref.id):
            _invalid()
        if (data.get('case_version') is not None and record['version'] is not None
                and data['case_version'] != record['version']):
            raise HTTPException(409, '原本店清算单在读取期间已变化，请重新核对')
        return order_ref, data, record

    def _sources(self, order_ref, data, record):
        observed_at = record['observed_at']
        return [EvidenceRef(source_type='object', source_id=order_ref,
                            native_version=data.get('version'), observed_at=observed_at),
                EvidenceRef(source_type='object',
                            source_id=BusinessObjectRef(type='case', id=record['id']),
                            native_version=record['version'], observed_at=observed_at)]

    async def read_snapshot(self, principal, ref):
        order_ref, data, record = await self._clearing_detail(principal, ref)
        local = self.snapshot_from_record(BusinessObjectRef(type='case', id=record['id']), record)
        # Original clearing detail exposes no actions/tasks. Only the original
        # local Flow GET can supply those; an open task is not a business fact.
        return BusinessObjectSnapshot(ref=order_ref, native_version=data.get('version'),
            display_number=None, state=data['status'], tasks=local.tasks,
            available_actions=local.available_actions,
            evidence_refs=self._sources(order_ref, data, record) +
                [item for item in local.evidence_refs if item.source_type == 'task'],
            manual_route=local.manual_route, observed_at=local.observed_at)

    def _fact_source(self, data, record):
        if (not _positive_id(data.get('version')) or not _positive_id(data.get('case_version'))
                or not _positive_id(record['version'])
                or not _positive_id(data.get('bucket_id'))
                or not _positive_id(data.get('origin_id'))
                or not _positive_id(data.get('transfer_id'))
                or data.get('origin_kind') not in _ORIGIN_KINDS
                or not _positive_id(data.get('requested_by'))
                or type(data.get('amount_cents')) is not int or data['amount_cents'] <= 0):
            raise ValueError('原清算金额、版本或往来来源不完整')
        expected = {'requested': 'pending', 'paid': 'pending',
                    'settled': 'completed', 'cancelled': 'cancelled'}
        if record['state'] != expected[data['status']]:
            raise ValueError('原本店 Case 与清算状态不一致')
        rows = data.get('events')
        if type(rows) is not list:
            raise ValueError('原本店完整事件未披露')
        events, ids = [], set()
        allowed = ({'clearing_create', 'clearing_pay', 'clearing_cancel', 'clearing_difference'}
                   if data['side'] == 'payer'
                   else {'clearing_receive', 'clearing_reject', 'clearing_difference'})
        for row in rows:
            if (type(row) is not dict or not _positive_id(row.get('id')) or row['id'] in ids
                    or type(row.get('case_id')) is not int or row['case_id'] != record['id']
                    or type(row.get('store_id')) is not int or row['store_id'] != record['store_id']
                    or not _positive_id(row.get('actor_id')) or row.get('action') not in allowed
                    or type(row.get('detail')) is not dict
                    or type(row['detail'].get('clearing_id')) is not int
                    or row['detail']['clearing_id'] != data['id']
                    or type(row.get('reason')) is not str or not row['reason'].strip()
                    or type(row.get('occurred_at')) is not str):
                raise ValueError('原清算事件来源不完整或不属于本店本单')
            datetime.fromisoformat(row['occurred_at'])
            if (row['action'] in {'clearing_pay', 'clearing_receive', 'clearing_difference'}
                    and not _positive_id(row.get('evidence_id'))):
                raise ValueError('原清算事件凭据不完整')
            ids.add(row['id'])
            events.append(row)
        counts = {action: sum(row['action'] == action for row in events) for action in allowed}
        if data['side'] == 'payer':
            created = [row for row in events if row['action'] == 'clearing_create']
            if (len(created) != 1 or created[0]['actor_id'] != data['requested_by']
                    or counts['clearing_pay'] != int(data['status'] in {'paid', 'settled'})
                    or counts['clearing_cancel'] > 1
                    or counts['clearing_cancel'] and data['status'] != 'cancelled'):
                raise ValueError('原付款方创建或确认事件缺失')
        elif (counts['clearing_receive'] != int(data['status'] == 'settled')
                or counts['clearing_reject'] > 1
                or counts['clearing_reject'] and data['status'] != 'cancelled'):
            raise ValueError('原收款方确认事件不完整')
        return events

    def _local_cash(self, data, record, events):
        rows = data.get('cash')
        if type(rows) is not list or len(rows) > 1:
            raise ValueError('原本店完整现金来源不完整')
        direction = 'out' if data['side'] == 'payer' else 'in'
        action = 'clearing_pay' if data['side'] == 'payer' else 'clearing_receive'
        local_events = [row for row in events if row['action'] == action]
        for row in rows:
            if (type(row) is not dict
                    or any(not _positive_id(row.get(key)) for key in
                           ('id', 'order_id', 'cash_id', 'account_id', 'evidence_id', 'actor_id'))
                    or row['order_id'] != data['id']
                    or type(row.get('store_id')) is not int or row['store_id'] != record['store_id']
                    or row.get('direction') != direction
                    or type(row.get('amount_cents')) is not int
                    or row['amount_cents'] != data['amount_cents']
                    or type(row.get('reference')) is not str or not row['reference'].strip()):
                raise ValueError('原本店现金与清算单关联不完整')
            _calendar_date(row.get('business_date'))
            if (len(local_events) != 1 or local_events[0]['actor_id'] != row['actor_id']
                    or local_events[0]['evidence_id'] != row['evidence_id']):
                raise ValueError('原本店现金缺少同次实际确认来源')
        expected = (data['status'] in {'paid', 'settled'} if data['side'] == 'payer'
                    else data['status'] == 'settled')
        if bool(rows) != expected or bool(local_events) != expected:
            raise ValueError('原状态与本店实际现金记录不一致')
        return bool(rows)

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in CLEARING_FACTS:
            try:
                return _unknown(fact_key, '内部清算未登记此事实，请按原业务能力核对')
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        order_ref, data, record = await self._clearing_detail(principal, ref)
        try:
            events = self._fact_source(data, record)
            if fact_key == 'clearing.difference_recorded':
                satisfied = any(row['action'] == 'clearing_difference' for row in events)
                reason = '本店已留原差异凭据，仍须核对实际收付款' if satisfied else '本店尚未留原差异事件'
            else:
                local_cash = self._local_cash(data, record, events)
                if fact_key == 'clearing.local_cash_recorded':
                    satisfied = local_cash
                    reason = '本店已登记实际付款' if data['side'] == 'payer' else '本店已登记实际收款'
                    if not satisfied:
                        reason = '本店尚未登记实际现金，不代表另一门店未支付'
                else:
                    satisfied = data['status'] == 'settled' and record['state'] == 'completed' and local_cash
                    reason = '原清算已结清且本店现金和原单完成事实齐全' if satisfied else '付款已记不等于到账或结清'
        except (ValueError, TypeError, OverflowError):
            return _unknown(fact_key, '本店原清算、现金或事件来源不完整，请到原单核对')
        return FactSnapshot(fact_key=fact_key, satisfied=satisfied, reason=reason,
                            evidence_refs=self._sources(order_ref, data, record))

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in CLEARING_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated')
                or any(not _positive_id(data.get(key)) for key in
                       ('id', 'payer_store_id', 'receiver_store_id', 'case_id', 'version', 'case_version'))
                or data['payer_store_id'] == data['receiver_store_id']
                or data.get('side') not in {'payer', 'receiver'}
                or data.get('status') not in CLEARING_STATES):
            return []
        return [BusinessObjectRef(type=CLEARING_OBJECT_TYPE, id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in CLEARING_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[],
                                 evidence_refs=[], reason_code='receipt_family_not_registered')
        # Original ReconciliationReceipt hashes clearing_create values or the
        # exact clearing:<id>:<action>/two-version payload; never mint a request.
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['CLEARING_ACTION', 'CLEARING_CREATE', 'CLEARING_FACTS', 'CLEARING_FLOW_VERSION',
           'CLEARING_KIND', 'CLEARING_OBJECT_TYPE', 'CLEARING_READ', 'CLEARING_RECEIPT_OPERATIONS',
           'CLEARING_RESULT_OPERATIONS', 'CLEARING_STATES', 'ClearingOrderAdapter']
