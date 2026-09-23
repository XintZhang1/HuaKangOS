"""Read-only, source-backed C/P/S adjustments for native retail reporting.

Quoted face C settles customer debt, issuance consideration P is external
revenue, and S is internal settlement. Physical returns reduce C/P/S before
indivisible units are restored. The restoration offset is deliberately NOT a
second fulfillment fact. Cash remains exclusively in the native cash ledger.
"""
from collections import defaultdict
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import select

from .flow_models import Case, StockMove
from .group_models import GroupEntry
from .group_benefits_models import BenefitEntry
from .inventory_report_common import MONEY_ROLES, bounded, local_date
from .retail_models import RetailReturnPosting
from .retail_group_models import (
    RetailGroupPlan as Plan, RetailGroupTender as Tender, RetailGroupUnit as Unit,
    RetailGroupAllocation as Allocation, RetailGroupCapture as Capture,
    RetailGroupReturn as Return, RetailGroupReturnPart as Part,
    RetailGroupRestore as Restore, RetailGroupSettlement as Settlement,
)


@contextmanager
def read_authority(db, user):
    if user.role not in MONEY_ROLES:
        raise HTTPException(403, '原支付对价与内部往来需要经营查询权限')
    ids = tuple(i for i in db.info.get('store_scope', ()) if i)
    previous = db.info.get('_group_authority')
    db.info['_group_authority'] = ('retail_report', ids)
    try:
        yield ids
    finally:
        if previous is None:
            db.info.pop('_group_authority', None)
        else:
            db.info['_group_authority'] = previous


def report_data(db, user, case_ids=None):
    """Return normalized facts from only the caller's explicitly scoped stores."""
    empty = {'discounts': [], 'adjustments': [], 'settlements': [], 'pending': []}
    with read_authority(db, user) as ids:
        query = select(Plan).where(Plan.store_id.in_(ids))
        if case_ids is not None:
            query = query.where(Plan.case_id.in_(case_ids))
        plans = {p.id: p for p in bounded(db, Plan, query)}
        if not plans:
            return empty
        cases = {r.id: r for r in bounded(db, Case, select(Case).where(
            Case.id.in_([p.case_id for p in plans.values()]), Case.store_id.in_(ids)))}
        tenders = {t.id: t for t in bounded(db, Tender, select(Tender).where(Tender.plan_id.in_(plans)))}
        units = {u.id: u for u in bounded(db, Unit, select(Unit).where(Unit.tender_id.in_(tenders)))}
        allocations = {a.id: a for a in bounded(db, Allocation, select(Allocation).where(Allocation.unit_id.in_(units)))}
        captures = {c.tender_id: c for c in bounded(db, Capture, select(Capture).where(Capture.tender_id.in_(tenders)))}
        returns = {r.id: r for r in bounded(db, Return, select(Return).where(Return.plan_id.in_(plans)))}
        parts = {p.id: p for p in bounded(db, Part, select(Part).where(Part.return_id.in_(returns)))}
        restores = {r.id: r for r in bounded(db, Restore, select(Restore).where(Restore.unit_id.in_(units)))}
        entries = {}
        for model, field in ((GroupEntry, 'principal_id'), (BenefitEntry, 'benefit_id')):
            keys = {getattr(r, field) for r in [*captures.values(), *restores.values()] if getattr(r, field)}
            for entry in bounded(db, model, select(model).where(model.id.in_(keys), model.store_id.in_(ids))):
                entries[(field, entry.id)] = entry
        postings = {p.id: p for p in bounded(db, RetailReturnPosting, select(RetailReturnPosting).where(
            RetailReturnPosting.id.in_([r.posting_id for r in returns.values()])))}
        moves = {m.id: m for m in bounded(db, StockMove, select(StockMove).where(
            StockMove.id.in_([p.stock_move_id for p in postings.values()])))}
        settlements = bounded(db, Settlement, select(Settlement).where(
            Settlement.return_part_id.in_(parts) | Settlement.restore_id.in_(restores)))

        def tender_case(tender):
            plan = plans[tender.plan_id]
            row = cases.get(plan.case_id)
            if row is None or row.store_id != tender.store_id or row.kind != 'retail':
                raise HTTPException(409, '精品原付款来源缺失或门店不一致，请核对原账')
            return row

        def actual_entry(record, tender):
            field = 'principal_id' if record.principal_id else 'benefit_id'
            entry = entries.get((field, getattr(record, field)))
            row = tender_case(tender)
            if entry is None or entry.case_id != row.id or entry.store_id != row.store_id:
                raise HTTPException(409, '原核销或恢复缺少本店实际流水，不能推算统计')
            return entry

        def meta(tender, source, source_id, day):
            row = tender_case(tender)
            return dict(case_id=row.id, store_id=row.store_id, kind=tender.kind,
                tender_id=tender.id, source=source, source_id=source_id,
                business_date=day.isoformat())

        result = {k: [] for k in empty}
        returned = defaultdict(lambda: [0, 0, 0])
        restored = defaultdict(lambda: [0, 0, 0])
        for allocation in allocations.values():
            tender = tenders[units[allocation.unit_id].tender_id]
            captured = captures.get(tender.id)
            if not captured:
                continue
            entry = actual_entry(captured, tender)
            discount = allocation.credit_cents - allocation.consideration_cents
            if discount:
                result['discounts'].append(meta(tender, Allocation.__tablename__, allocation.id, local_date(entry.occurred_at)) |
                    dict(capture_id=captured.id, line_id=allocation.line_id, component=allocation.component,
                        label='原集团核销履约优惠', amount_cents=-discount))
        for part in parts.values():
            if not part.capture_id:
                continue
            allocation = allocations[part.allocation_id]
            tender = tenders[units[allocation.unit_id].tender_id]
            captured = captures.get(tender.id)
            if captured is None or captured.id != part.capture_id:
                raise HTTPException(409, '实际退货的原支付批次不一致')
            posting = postings[returns[part.return_id].posting_id]
            move = moves[posting.stock_move_id]
            base = meta(tender, Part.__tablename__, part.id, move.business_date)
            if (move.case_id, move.store_id) != (base['case_id'], base['store_id']):
                raise HTTPException(409, '原实退的库存来源或门店不一致')
            values = (part.credit_cents, part.consideration_cents, part.settlement_cents)
            for i, v in enumerate(values):
                returned[allocation.unit_id][i] += v
            result['adjustments'].append(base | dict(unit_id=allocation.unit_id,
                label='精品实际退货：先减履约与待恢复负债',
                credit_cents=-values[0], recognized_cents=-values[1],
                group_discount_cents=values[1]-values[2], service_discount_cents=values[2]-values[0]))
            if values[0] != values[1]:
                result['discounts'].append(base | dict(line_id=allocation.line_id, component=allocation.component,
                    label='原实退对应优惠冲回', amount_cents=values[0]-values[1]))
        for restore in restores.values():
            tender = tenders[units[restore.unit_id].tender_id]
            entry = actual_entry(restore, tender)
            values = (restore.credit_cents, restore.consideration_cents, restore.settlement_cents)
            for i, v in enumerate(values):
                restored[restore.unit_id][i] += v
            result['adjustments'].append(meta(tender, Restore.__tablename__, restore.id, local_date(entry.occurred_at)) |
                dict(unit_id=restore.unit_id, label='原单位恢复对冲：不二次冲减履约',
                    credit_cents=values[0], recognized_cents=values[1],
                    group_discount_cents=values[2]-values[1], service_discount_cents=values[0]-values[2]))
        for settlement in settlements:
            unit_id = (allocations[parts[settlement.return_part_id].allocation_id].unit_id
                if settlement.return_part_id else restores[settlement.restore_id].unit_id)
            tender = tenders[units[unit_id].tender_id]
            result['settlements'].append(dict(id=settlement.id, store_id=settlement.store_id, kind=tender.kind,
                side=settlement.side, amount_cents=settlement.amount_cents,
                return_part_id=settlement.return_part_id, restore_id=settlement.restore_id))
        for unit_id, values in returned.items():
            pending = [v-b for v, b in zip(values, restored[unit_id])]
            if min(pending) < 0:
                raise HTTPException(409, '原权益恢复超过实退负债')
            if not pending[0]:
                continue
            unit = units[unit_id]
            tender = tenders[unit.tender_id]
            row = tender_case(tender)
            result['pending'].append(dict(case_id=row.id, store_id=row.store_id, unit_id=unit_id,
                tender_id=tender.id, kind=tender.kind, credit_cents=pending[0],
                consideration_cents=pending[1], settlement_cents=pending[2],
                spendable_cents=0, expires_on=str(tender.expires_on) if tender.expires_on else None,
                restorable=tender.kind not in {'coupon', 'package'} or values[0] == unit.credit_cents))
        return result
