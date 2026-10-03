"""Original approved supplier targets and separately recorded vehicle-income cash."""
import hashlib
import json
from datetime import date, datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (
    AvailableAction, BusinessObjectRef, BusinessObjectSnapshot, EvidenceRef,
    FactSnapshot, ReceiptLookup, SubmissionSnapshot, TaskSnapshot,
)
from .flow_case import FlowCaseAdapter, _positive_id

VINC_KIND = 'vehicle_income'
VINC_FLOW_VERSION = 1
VINC_READ = 'GET /api/vehicle-income/{key}'
VINC_CREATE = 'POST /api/vehicle-income'
VINC_ACTION = 'POST /api/vehicle-income/{key}/actions/{action}'
VINC_FACTS = ('vehicle_income.target_approved', 'vehicle_income.receipt_recorded',
              'vehicle_income.refund_recorded')
VINC_ACTIONS = ('propose', 'approve', 'reject', 'withdraw', 'receive', 'refund', 'cancel')
VINC_STATES = ('pending', 'approval', 'credit_open', 'refund_pending', 'completed', 'cancelled')
VINC_RESULT_OPERATIONS = frozenset({VINC_READ, VINC_CREATE, VINC_ACTION})
VINC_RECEIPT_OPERATIONS = frozenset({VINC_CREATE, VINC_ACTION})
_REVISION_FIELDS = ('previous_id', 'previous_cents', 'target_cents', 'invoice_mode',
                    'due_date', 'source_versions', 'reason', 'evidence_id')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原整车其他收入详情不完整或关联不一致，请到原页面核对') from None


def _unknown(fact_key):
    return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                        reason='本单原目标、独立决定或资金来源不完整，请到原页面核对')


def _day(value):
    if type(value) is not str:
        raise ValueError('原业务日期缺失')
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError('原业务日期格式不正确')
    return result


def _time(value):
    if type(value) is not str or 'T' not in value:
        raise ValueError('原事实时间缺失')
    result = datetime.fromisoformat(value)
    return result.astimezone(timezone.utc).replace(tzinfo=None) if result.tzinfo else result


def _cents(value):
    return type(value) is int and value >= 0


def _text(value):
    return type(value) is str and bool(value.strip())


class VehicleIncomeAdapter(FlowCaseAdapter):
    name = 'vehicle_income'
    object_types = ('case',)

    async def _income_detail(self, principal, ref):
        try:
            case_ref = BusinessObjectRef.model_validate(
                ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '请选择有真实主键的原整车其他收入单') from None
        if case_ref.type != 'case':
            raise HTTPException(422, '此适配器只读取原整车收入 Case')
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(VINC_READ,
                path_args={'key': case_ref.id}, query={}, body=None)
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
            raise HTTPException(status, '原业务暂不能读取此收入单，请到原页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is dict and data.get('store_id') != store_id:
            raise HTTPException(404, '原业务不存在或当前账号不可查看')
        if (type(data) is not dict or response.get('truncated') or data.get('truncated')
                or not _positive_id(data.get('id')) or data['id'] != case_ref.id
                or not _positive_id(data.get('store_id'))
                or data.get('kind') != VINC_KIND
                or type(data.get('flow_version')) is not int or data['flow_version'] != VINC_FLOW_VERSION
                or data.get('state') not in VINC_STATES
                or data.get('version') is not None and not _positive_id(data['version'])):
            _invalid()
        return case_ref, data

    async def read_snapshot(self, principal, ref):
        case_ref, data = await self._income_detail(principal, ref)
        try:
            rows, actions = data.get('tasks'), data.get('actions')
            if (type(rows) is not list or type(actions) is not list
                    or any(type(key) is not str or key not in VINC_ACTIONS for key in actions)
                    or len(actions) != len(set(actions))):
                _invalid()
            tasks, ids = [], set()
            for row in rows:
                if (type(row) is not dict or not _positive_id(row.get('id')) or row['id'] in ids
                        or 'case_id' in row and (type(row['case_id']) is not int or row['case_id'] != case_ref.id)):
                    _invalid()
                ids.add(row['id'])
                # Dedicated describe returns only compact open Task fields.
                # The proved same-Case relation supplies case_id, not status or version.
                tasks.append(TaskSnapshot.model_validate(dict(case_id=case_ref.id,
                    **{key: row[key] for key in ('id', 'key', 'title', 'assignee_id', 'due_date') if key in row})))
            observed_at = _now()
            source = EvidenceRef(source_type='object', source_id=case_ref,
                                 native_version=data.get('version'), observed_at=observed_at)
            return BusinessObjectSnapshot(ref=case_ref, native_version=data.get('version'),
                display_number=data.get('number') if type(data.get('number')) is str else None,
                state=data['state'], tasks=tasks,
                available_actions=[AvailableAction(action_key=key, availability='unknown', evidence_refs=[source])
                                   for key in actions],
                evidence_refs=[source] + [EvidenceRef(source_type='task', source_id=task.id,
                    native_version=None, observed_at=observed_at) for task in tasks],
                manual_route='vehicle-income/' + str(case_ref.id), observed_at=observed_at)
        except (ValidationError, ValueError, TypeError, OverflowError):
            _invalid()

    def _revisions(self, data):
        if not _positive_id(data.get('version')):
            raise ValueError('原版本未披露')
        sources, supplier = data.get('sources'), data.get('supplier')
        if (type(sources) is not list or not sources or type(supplier) is not dict
                or not _positive_id(supplier.get('id')) or not _positive_id(supplier.get('version'))
                or not _text(supplier.get('name'))):
            raise ValueError('原往来单位或车辆业务依据缺失')
        source_ids, source_rows, identities = {}, set(), set()
        for source in sources:
            if (type(source) is not dict or not _positive_id(source.get('id'))
                    or source['id'] in source_rows or not _positive_id(source.get('case_id'))
                    or not _positive_id(source.get('version'))
                    or source.get('kind') not in {'order', 'vehicle_procurement', 'vehicle_operations', 'opening_import'}
                    or source.get('vehicle_id') is not None and not _positive_id(source['vehicle_id'])):
                raise ValueError('原车辆业务依据关联不完整')
            identity = (source['case_id'], source.get('vehicle_id'))
            if identity in identities:
                raise ValueError('原车辆业务依据重复')
            identities.add(identity)
            source_rows.add(source['id'])
            source_ids[str(source['case_id'])] = max(source_ids.get(str(source['case_id']), 0), source['version'])
        rows = data.get('revisions')
        if type(rows) is not list or any(type(row) is not dict for row in rows):
            raise ValueError('原完整目标修订未披露')
        revisions, decisions, pending = {}, set(), []
        prior = None
        for number, row in enumerate(sorted(rows, key=lambda item: item.get('id', 0)), 1):
            if (not _positive_id(row.get('id')) or row['id'] in revisions
                    or type(row.get('revision')) is not int or row['revision'] != number
                    or type(row.get('case_id')) is not int or row['case_id'] != data['id']
                    or type(row.get('store_id')) is not int or row['store_id'] != data['store_id']
                    or not _positive_id(row.get('actor_id')) or not _positive_id(row.get('evidence_id'))
                    or not _cents(row.get('previous_cents')) or not _cents(row.get('target_cents'))
                    or row.get('invoice_mode') not in {'store_invoice', 'external_document'}
                    or not _text(row.get('reason')) or any(key not in row for key in _REVISION_FIELDS)
                    or row.get('previous_id') is not None and not _positive_id(row['previous_id'])
                    or row['previous_id'] != (prior['id'] if prior else None)
                    or row['previous_cents'] != (prior['target_cents'] if prior else 0)
                    or prior is None and row['target_cents'] == 0):
                raise ValueError('原目标修订没有沿批准版本追加')
            _day(row['due_date'])
            proposed_at = _time(row.get('created_at'))
            versions = row['source_versions']
            if (type(versions) is not dict or set(versions) != set(source_ids)
                    or any(not _positive_id(value) or value < source_ids[key] for key, value in versions.items())):
                raise ValueError('原修订来源版本不完整')
            payload = {key: row[key] for key in _REVISION_FIELDS}
            digest = hashlib.sha256(json.dumps({'operation': 'vehicle_income_revision', 'payload': payload},
                sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            if row.get('digest') != digest:
                raise ValueError('原八字段目标摘要不一致')
            if 'decision' not in row:
                raise ValueError('原决定来源未披露')
            decision = row['decision']
            if decision is None:
                pending.append(row['id'])
                if number != len(rows):
                    raise ValueError('原待复核版本不是最后修订')
            else:
                if (type(decision) is not dict or not _positive_id(decision.get('id'))
                        or decision['id'] in decisions
                        or type(decision.get('revision_id')) is not int or decision['revision_id'] != row['id']
                        or type(decision.get('store_id')) is not int or decision['store_id'] != data['store_id']
                        or not _positive_id(decision.get('actor_id'))
                        or decision.get('decision') not in {'approved', 'rejected', 'withdrawn'}
                        or not _text(decision.get('reason')) or _time(decision.get('created_at')) < proposed_at):
                    raise ValueError('原独立决定不属于本版目标')
                _day(decision.get('business_date'))
                if (decision['decision'] in {'approved', 'rejected'}
                        and (decision['actor_id'] == row['actor_id'] or not _positive_id(decision.get('evidence_id')))):
                    raise ValueError('原主管决定缺少独立提出人或凭据')
                # Native describe does not disclose Case.created_by/order.actor_id.
                # Do not substitute owner_id for the original service's creator guard.
                decisions.add(decision['id'])
                if decision['decision'] == 'approved':
                    prior = row
            revisions[row['id']] = row
        if (any(key not in data for key in ('current_revision_id', 'pending_revision_id'))
                or any(data.get(key) is not None and not _positive_id(data[key])
                       for key in ('current_revision_id', 'pending_revision_id'))
                or data['current_revision_id'] != (prior['id'] if prior else None)
                or data['pending_revision_id'] != (pending[0] if pending else None)
                or data['state'] == 'cancelled' and (prior is not None or pending)):
            raise ValueError('原当前批准或待复核目标不一致')
        return revisions, prior

    def _cash(self, data, revisions, current):
        rows = data.get('payments')
        if type(rows) is not list or any(type(row) is not dict for row in rows):
            raise ValueError('原完整资金来源未披露')
        payments, cash_ids, references, returned = {}, set(), set(), {}
        received, refunded, net = 0, 0, 0
        for row in sorted(rows, key=lambda item: item.get('id', 0)):
            if (any(not _positive_id(row.get(key)) for key in
                    ('id', 'cash_id', 'account_id', 'revision_id', 'evidence_id', 'actor_id'))
                    or row['id'] in payments or row['cash_id'] in cash_ids
                    or type(row.get('case_id')) is not int or row['case_id'] != data['id']
                    or type(row.get('store_id')) is not int or row['store_id'] != data['store_id']
                    or not _cents(row.get('amount_cents')) or row['amount_cents'] <= 0
                    or not _text(row.get('reference')) or 'original_id' not in row):
                raise ValueError('原资金主键、门店或整数分关系不完整')
            at, day = _time(row.get('created_at')), _day(row.get('business_date'))
            revision = revisions.get(row['revision_id'])
            decision = revision.get('decision') if revision else None
            approved = [r for r in revisions.values() if type(r.get('decision')) is dict
                        and r['decision']['decision'] == 'approved' and _time(r['decision']['created_at']) <= at]
            pending_at = [r for r in revisions.values() if _time(r['created_at']) <= at
                          and (r['decision'] is None or _time(r['decision']['created_at']) > at)]
            if (not revision or not decision or decision['decision'] != 'approved'
                    or not approved or approved[-1]['id'] != revision['id'] or pending_at
                    or day < _day(decision['business_date'])):
                raise ValueError('原资金没有当时有效的独立批准目标')
            account = row.get('account_snapshot')
            if (type(account) is not dict or type(account.get('id')) is not int
                    or account['id'] != row['account_id'] or not _positive_id(account.get('version'))
                    or not _text(account.get('name')) or not _text(account.get('account_type'))
                    or (row['account_id'], row['reference']) in references):
                raise ValueError('原资金账户快照或流水号来源不完整')
            if row.get('direction') == 'in':
                if row['original_id'] is not None or row['amount_cents'] > revision['target_cents'] - net:
                    raise ValueError('原到账超过当时批准目标')
                received += row['amount_cents']
                net += row['amount_cents']
            elif row.get('direction') == 'out':
                original = payments.get(row['original_id']) if _positive_id(row['original_id']) else None
                if (not original or original['direction'] != 'in' or original['account_id'] != row['account_id']
                        or day < _day(original['business_date'])
                        or row['amount_cents'] > net - revision['target_cents']):
                    raise ValueError('原退款没有同单原款、原账户或批准超收')
                returned[original['id']] = returned.get(original['id'], 0) + row['amount_cents']
                if returned[original['id']] > original['amount_cents']:
                    raise ValueError('累计退款超过原实际到账')
                refunded += row['amount_cents']
                net -= row['amount_cents']
            else:
                raise ValueError('原资金方向不正确')
            payments[row['id']] = row
            cash_ids.add(row['cash_id'])
            references.add((row['account_id'], row['reference']))
        for row in payments.values():
            available = row['amount_cents'] - returned.get(row['id'], 0) if row['direction'] == 'in' else 0
            if type(row.get('available_cents')) is not int or row['available_cents'] != available:
                raise ValueError('原款可退整数分不一致')
        target = current['target_cents'] if current else 0
        expected = dict(target_cents=target, received_cents=received, refunded_cents=refunded,
                        net_received_cents=net, receivable_cents=max(0, target-net), refund_due_cents=max(0, net-target))
        totals = data.get('totals')
        if (type(totals) is not dict or any(type(totals.get(key)) is not int or totals[key] != value
                                          for key, value in expected.items())
                or data['state'] == 'cancelled' and payments):
            raise ValueError('原收入资金合计整数分不一致')
        return payments

    async def fact_snapshot(self, principal, ref, fact_key):
        if fact_key not in VINC_FACTS:
            try:
                return _unknown(fact_key)
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, '事实标识不正确') from None
        case_ref, data = await self._income_detail(principal, ref)
        try:
            revisions, current = self._revisions(data)
            payments = self._cash(data, revisions, current)
        except (ValueError, TypeError, OverflowError, KeyError):
            return _unknown(fact_key)
        if fact_key == 'vehicle_income.target_approved':
            satisfied = current is not None
            reason = '原当前目标已有独立批准；待复核修订不代替该批准' if satisfied else '本单尚无原独立批准目标'
        else:
            direction = 'in' if fact_key == 'vehicle_income.receipt_recorded' else 'out'
            satisfied = any(row['direction'] == direction for row in payments.values())
            reason = ('本单至少一笔原实际到账已登记，不代表全部应收结清' if direction == 'in'
                      else '本单至少一笔原款已按原账户实际退回') if satisfied else '本单尚无对应原资金记录'
        source = EvidenceRef(source_type='object', source_id=case_ref,
                             native_version=data['version'], observed_at=_now())
        return FactSnapshot(fact_key=fact_key, satisfied=satisfied, evidence_refs=[source], reason=reason)

    def extract_result(self, operation_id, response):
        if (type(operation_id) is not str or operation_id not in VINC_RESULT_OPERATIONS
                or type(response) is not dict or type(response.get('status')) is not int
                or not 200 <= response['status'] < 300 or response.get('truncated')):
            return []
        data = response.get('data')
        if (type(data) is not dict or data.get('truncated') or not _positive_id(data.get('id'))
                or not _positive_id(data.get('store_id')) or data.get('kind') != VINC_KIND
                or type(data.get('flow_version')) is not int or data['flow_version'] != VINC_FLOW_VERSION):
            return []
        return [BusinessObjectRef(type='case', id=data['id'])]

    async def read_receipt(self, principal, submission):
        try:
            snapshot = SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        if snapshot.operation_id not in VINC_RECEIPT_OPERATIONS or self._receipt_reader is None:
            return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[],
                                 evidence_refs=[], reason_code='receipt_family_not_registered')
        # The original family resolves frozen Create/Command DTO defaults, dates
        # and native request_digest. This provider never writes or replays a POST.
        result = await self._receipt_reader(principal, snapshot)
        try:
            return ReceiptLookup.model_validate(result.model_dump() if isinstance(result, ReceiptLookup) else result)
        except (ValidationError, ValueError, TypeError):
            _invalid()


__all__ = ['VINC_ACTION', 'VINC_ACTIONS', 'VINC_CREATE', 'VINC_FACTS', 'VINC_FLOW_VERSION',
           'VINC_KIND', 'VINC_READ', 'VINC_RECEIPT_OPERATIONS', 'VINC_RESULT_OPERATIONS',
           'VINC_STATES', 'VehicleIncomeAdapter']
