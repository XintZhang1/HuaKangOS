"""Explicit store-by-store employee continuity, separate from historical credit.

Only the account archive transaction creates these grants. Queries still use the
current employee role and selected store; a handover never grants a job or access
to another store, and never delegates a former employee's assistant authority.
"""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select, or_, and_, exists, func
from .models import User, UserStore, Store
from .employee_handover_models import EmployeeHandover, EmployeeHandoverRecord
from .tenancy import account_role


def _tables():
    return EmployeeHandover.__table__, EmployeeHandoverRecord.__table__


def _record_key(model):
    from .business_records_models import RecordCustomer, SalesContract
    return 'customer_id' if model is RecordCustomer else 'contract_id' if model is SalesContract else None


def inherited_read(model, user):
    key = _record_key(model)
    if key is None:
        return False
    h, r = _tables()
    return exists(select(1).select_from(r.join(h, h.c.id == r.c.handover_id)).where(
        r.c[key] == model.id, h.c.store_id == model.store_id,
        h.c.successor_id == user.id, h.c.successor_role == user.role))


def responsible_condition(model, user_id):
    """Latest *working* handover wins; read-only history copies cannot steal work."""
    key = _record_key(model)
    owner = getattr(model, 'salesperson_id', None)
    if owner is None:
        owner = model.owner_id
    h, r = _tables()
    later = r.alias('later_employee_handover')
    newer = exists(select(1).where(later.c[key] == r.c[key], later.c.can_continue.is_(True), later.c.id > r.c.id))
    working = exists(select(1).select_from(r.join(h, h.c.id == r.c.handover_id)).where(
        r.c[key] == model.id, h.c.store_id == model.store_id, r.c.can_continue.is_(True),
        h.c.successor_id == user_id, ~newer))
    transferred = exists(select(1).where(r.c[key] == model.id, r.c.can_continue.is_(True)))
    return or_(and_(owner == user_id, ~transferred), working)


def can_continue_record(db, user, row):
    if account_role(user) == 'admin':
        return True  # Each business operation still checks its original capability.
    model = type(row)
    if _record_key(model) is None:
        return getattr(row, 'owner_id', None) == user.id
    # Current-store role and ownership/grant are checked again on each request.
    return bool(db.scalar(select(model.id).where(model.id == row.id,
        responsible_condition(model, user.id), or_(
            getattr(model, 'salesperson_id', None) == user.id if hasattr(model, 'salesperson_id') else model.owner_id == user.id,
            inherited_read(model, user)))))


def was_contract_handler(db, user, row):
    """Past handover work remains an approval conflict after a later job change."""
    if user.id in {row.salesperson_id, row.created_by}:
        return True
    from .business_records_models import RecordContractCorrection
    revisions = db.scalars(select(RecordContractCorrection).where(
        RecordContractCorrection.contract_id == row.id,
        RecordContractCorrection.store_id == row.store_id))
    if any(revision.submitted_by == user.id or any(event.get('action') == 'submitted' and
            event.get('actor_id') == user.id for event in revision.events or []) for revision in revisions):
        return True
    h, r = _tables()
    return bool(db.scalar(select(h.c.id).select_from(r.join(h, h.c.id == r.c.handover_id)).where(
        r.c.contract_id == row.id, h.c.store_id == row.store_id, h.c.successor_id == user.id,
        r.c.can_continue.is_(True)).limit(1)))


def handover_summary(db, user, row):
    key = _record_key(type(row))
    if key is None:
        return None
    h, r = _tables()
    values = db.execute(select(h.c.source_id, h.c.successor_id,
        h.c.successor_role, h.c.created_at, r.c.can_continue)
        .select_from(r.join(h, h.c.id == r.c.handover_id))
        .where(r.c[key] == row.id, h.c.store_id == row.store_id).order_by(r.c.id.desc())).mappings().all()
    if not values:
        return None
    value = values[0]
    people = {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(
        {item[key] for item in values for key in ('source_id', 'successor_id')})))}
    history = [{'source_id': item['source_id'], 'source_name': people.get(item['source_id'], ''),
        'successor_id': item['successor_id'], 'successor_name': people.get(item['successor_id'], ''),
        'successor_role': item['successor_role'],
        'at': item['created_at'].isoformat(), 'can_continue': item['can_continue']} for item in reversed(values)]
    return {'source_name': people.get(value['source_id'], ''), 'successor_name': people.get(value['successor_id'], ''),
            'can_continue': can_continue_record(db, user, row), 'history_attribution_preserved': True, 'history': history}


def can_read_contract_attachment(db, user, contract, item):
    """A sales successor inherits only prior sales attachments, never internal files."""
    if user.role != 'sales' or item.created_by == user.id:
        return True
    if item.kind != 'contract_attachment' or item.contract_id != contract.id or item.store_id != contract.store_id:
        return False
    h, r = _tables()
    inherited_at = db.scalar(select(func.max(h.c.created_at)).select_from(
        r.join(h, h.c.id == r.c.handover_id)).where(r.c.contract_id == contract.id,
        h.c.store_id == contract.store_id, h.c.successor_id == user.id, h.c.successor_role == user.role))
    if inherited_at is None or item.created_at > inherited_at:
        return False
    return bool(db.scalar(select(h.c.id).select_from(r.join(h, h.c.id == r.c.handover_id))
        .where(r.c.contract_id == contract.id, h.c.store_id == contract.store_id,
            h.c.successor_role == 'sales', h.c.source_id == item.created_by,
            h.c.created_at <= inherited_at).limit(1)))


def _roles(db, target):
    assignments = {m.store_id: m.role or target.role for m in db.scalars(select(UserStore).where(UserStore.user_id == target.id))}
    if target.role in {'admin', 'group_deputy_manager'}:
        assignments.update({s.id: target.role for s in db.scalars(select(Store).where(Store.active.is_(True)))})
    # Historical disabled-store grants remain explicit and can be handed over to
    # a peer with that same preserved grant; neither employee can enter that store.
    return assignments


def _resources(db, source_id, store_id):
    """Fixed account-management metadata projection, no business amounts/content."""
    from .business_records_models import RecordCustomer, SalesContract
    h, r = _tables()
    result = {}
    for model, key, owner in ((RecordCustomer, 'customers', 'owner_id'), (SalesContract, 'contracts', 'salesperson_id')):
        table = model.__table__
        item_key = _record_key(model)
        inherited = select(r.c[item_key]).select_from(r.join(h, h.c.id == r.c.handover_id)).where(
            h.c.successor_id == source_id, h.c.store_id == store_id)
        involved = [table.c[owner] == source_id, table.c.id.in_(inherited)]
        if model is SalesContract:
            involved.extend(table.c[name] == source_id for name in ('created_by', 'manager_approved_by',
                'general_manager_approved_by', 'deputy_approved_by', 'office_submitted_by', 'office_approved_by', 'priced_by'))
        # Core projection is intentional: global account managers can hand over
        # each explicit store while a request itself remains in one selected store.
        rows = db.execute(select(table.c.id, table.c[owner], *(
            (table.c.status, table.c.office_status) if model is SalesContract else ()))
            .where(table.c.store_id == store_id, or_(*involved)).order_by(table.c.id)).mappings().all()
        current = set(db.scalars(select(table.c.id).where(table.c.store_id == store_id,
            responsible_condition(model, source_id))))
        result[key] = [{'id': row['id'], 'can_continue': row['id'] in current and (
            model is RecordCustomer or row['status'] != 'approved' or row['office_status'] != 'approved')}
            for row in rows]
    return result


def preview(db, principal, target):
    from . import store_administration as access
    if access.is_store_admin(principal):
        access.require_target(db, principal, target, lock=False)
    if target.id == principal.id or target.archived_at is not None:
        raise HTTPException(409, '不能交接当前操作者或已删除员工，请刷新核对')
    roles = _roles(db, target)
    stores = {s.id: s for s in db.scalars(select(Store).where(Store.id.in_(roles)))}
    people = list(db.scalars(select(User).where(User.id != target.id, User.active.is_(True), User.archived_at.is_(None)).order_by(User.display_name, User.id)))
    candidates = {person.id: _roles(db, person) for person in people}
    entries = []
    for store_id, role in sorted(roles.items()):
        resources = _resources(db, target.id, store_id)
        entries.append({'store_id': store_id, 'store_name': stores[store_id].name, 'active': stores[store_id].active,
            'role': role, 'customer_count': len(resources['customers']), 'contract_count': len(resources['contracts']),
            'pending_contract_count': sum(item['can_continue'] for item in resources['contracts']),
            'candidates': [{'id': person.id, 'display_name': person.display_name, 'username': person.username,
                'access_version': person.access_version} for person in people if candidates[person.id].get(store_id) == role]})
    return {'id': target.id, 'access_version': target.access_version, 'stores': entries,
            'history_attribution_preserved': True}


def prepare(db, principal, target, body, locked):
    offered = {item.store_id: item for item in body.handovers}
    roles = _roles(db, target)
    if len(offered) != len(body.handovers) or set(offered) != set(roles):
        raise HTTPException(422, '请为该员工的每家授权门店分别指定接手人；门店不得重复或遗漏')
    if not roles:
        raise HTTPException(422, '该员工没有可交接门店，请先核对原授权')
    plan = []
    for store_id, role in sorted(roles.items()):
        item = offered[store_id]
        successor = next((person for person in locked if person.id == item.successor_id), None)
        if (not successor or successor.id == target.id or not successor.active or successor.archived_at is not None
                or _roles(db, successor).get(store_id) != role):
            raise HTTPException(422, '接手人须为对应门店相同岗位的在用员工，不能为本人或已删除员工')
        if successor.access_version != item.successor_access_version:
            raise HTTPException(409, '接手人岗位或状态已变化，请关闭窗口、刷新后重新核对')
        plan.append({'store_id': store_id, 'successor_id': successor.id, 'successor_role': role,
            'successor_access_version': successor.access_version, **_resources(db, target.id, store_id)})
    return plan


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def store_plan(db, target_id, receipt_id, plan):
    for entry in plan:
        handover = EmployeeHandover(store_id=entry['store_id'], source_id=target_id,
            successor_id=entry['successor_id'], successor_role=entry['successor_role'],
            successor_access_version=entry['successor_access_version'], receipt_id=receipt_id)
        db.add(handover); db.flush()
        for kind, key in (('customers', 'customer_id'), ('contracts', 'contract_id')):
            db.add_all([EmployeeHandoverRecord(handover_id=handover.id, **{key: item['id']},
                can_continue=item['can_continue']) for item in entry[kind]])
    db.flush()
