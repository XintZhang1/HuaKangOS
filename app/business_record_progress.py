"""Display actual contract stages and current eligible employees, without tasks."""
from sqlalchemy import select
from .models import User
from .tenancy import role_for_store


def contract_progress(db, user, row, data):
    terms = data.get('terms') or {}
    wholesale = terms.get('submission_data', {}).get('sales_channel') == 'wholesale'
    special = terms.get('special', False)
    delivery = data.get('delivery_state', {}).get('delivery')
    approved = row.status == 'approved'
    stages = [{'label': '销售经理批发开单' if wholesale else '销售顾问预填', 'done': True}]
    if not wholesale:
        stages.append({'label': '销售经理审批', 'done': bool(row.manager_approved_at)})
    stages.append({'label': '总经理审批', 'done': bool(row.general_manager_approved_at) or approved})
    if special:
        stages.append({'label': '集团副总经理审批', 'done': bool(row.deputy_approved_at)})
    stages.extend([{'label': '财务打印、材料与交车', 'done': bool(delivery)},
        {'label': '内勤延伸资料与核价', 'done': row.office_status in {'submitted', 'approved'}},
        {'label': '总经理审核资料', 'done': row.office_status == 'approved'}])
    # Names describe the employee who actually acted, even after departure.
    actors = [(row.created_by, row.created_at)]
    if not wholesale:
        actors.append((row.manager_approved_by, row.manager_approved_at))
    actors.append((row.general_manager_approved_by or row.approved_by,
        row.general_manager_approved_at or row.approved_at))
    if special:
        actors.append((row.deputy_approved_by, row.deputy_approved_at))
    actors.extend([((delivery or {}).get('confirmed_by'), (delivery or {}).get('confirmed_at')),
        (row.office_submitted_by, row.office_submitted_at), (row.office_approved_by, row.office_approved_at)])
    names = {person.id: person.display_name for person in db.scalars(select(User).where(
        User.id.in_({ident for ident, _ in actors if ident is not None})))}
    for stage, (ident, timestamp) in zip(stages, actors):
        stage.update(actor_id=ident, actor_name=names.get(ident, ''),
            at=timestamp.isoformat() if hasattr(timestamp, 'isoformat') else timestamp)
    role, label = (None, '流程已完成')
    if row.status == 'rejected':
        role, label = ('manager' if wholesale else 'sales', '经办人修改合同')
    elif row.status == 'submitted':
        role, label = ('manager', '销售经理审批')
    elif row.status == 'manager_approved':
        role, label = ('general_manager', '总经理审批')
    elif row.status == 'deputy_pending':
        role, label = ('group_deputy_manager', '集团副总经理审批')
    elif approved and not delivery:
        role, label = ('finance', '财务打印合同、核实材料并交车')
    elif approved and row.office_status == 'submitted':
        role, label = ('general_manager', '总经理审核内勤资料')
    elif approved and row.office_status != 'approved':
        role, label = ('clerk', '内勤填写延伸资料与核价')
    candidates = []
    if role:
        from .employee_handover import can_continue_record, was_contract_handler
        excluded = {row.salesperson_id, row.created_by}
        if role == 'general_manager':
            excluded.add(row.office_submitted_by if row.office_status == 'submitted' and approved else row.manager_approved_by)
        if role == 'group_deputy_manager':
            excluded.update({row.manager_approved_by, row.general_manager_approved_by})
        for person in db.scalars(select(User).where(User.active.is_(True), User.archived_at.is_(None)).order_by(User.display_name, User.id)):
            if role_for_store(db, person, row.store_id) != role:
                continue
            if row.status == 'rejected':
                from types import SimpleNamespace
                actor = SimpleNamespace(id=person.id, role=role)
                if not can_continue_record(db, actor, row):
                    continue
            elif role in {'manager', 'general_manager', 'group_deputy_manager'} and (
                    person.id in excluded or was_contract_handler(db, person, row)):
                continue
            candidates.append({'id': person.id, 'name': person.display_name})
    from .business_record_corrections import correction_rows, correction_view, ACTIVE
    active = next((item for item in correction_rows(db, row) if item.status in ACTIVE), None)
    correction = correction_view(db, user, row, active) if active else None
    return {'stages': stages, 'pending_label': label, 'pending_role': role, 'pending_people': candidates,
        'active_correction': correction}
