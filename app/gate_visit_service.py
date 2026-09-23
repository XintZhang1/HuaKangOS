"""Minimal employee actions for real gate movement; no business-state shortcut."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, func
from .db import utcnow, today
from . import flow_engine as flow
from . import service_intake_service as intake
from .flow_models import Case, Task
from .gate_visit_models import GateVisit, GateFact, GateCorrection, GateReview, GateHandoff, RepairGateExit
from .service_intake_models import ServiceAppointment, ArrivalFact
from .gate_attendance import lock_vin, effective, check_interval, departure_guard
from .tenancy import single_store

READ = intake.READ
FRONT = intake.FRONT | intake.MANAGE
PURPOSES = {'consultation': '咨询来访', 'inspection': '非维修检查', 'accessory': '精品办理', 'delivery': '客户车辆交接', 'other': '其他有据来访'}


def _execute(db, user, key, operation, payload, callback):
    return intake._execute(db, user, key, 'gate_' + operation, payload, callback)


def _visit(db, user, key):
    intake._role(user, READ)
    if getattr(user, '_aggregate_scope', False):
        raise HTTPException(409, '跨店请使用隐藏身份的同源汇总；办理原单须选择本店')
    visit = intake._one(db, GateVisit, key)
    return visit, flow.get_case(db, user, visit.case_id)


def _no_pending(db, visit):
    if db.scalar(select(GateCorrection.id).where(GateCorrection.active_visit_id == visit.id)):
        raise HTTPException(409, '本次进出厂有待独立复核的纠正，请先处理原申请')


def _digest(db, visit):
    eff = effective(db, visit)
    return flow.request_digest('gate_origin', {'visit_id': visit.id, 'case_id': visit.case_id, 'vin': visit.vin,
        'facts': [{'id': f.id, 'direction': f.direction, 'actual_at': intake._iso(f.actual_at), 'evidence_id': f.evidence_id, 'actor_id': f.actor_id, 'reason': f.reason} for f in eff['facts']],
        'reviews': [c.id for c in eff['corrections']], 'arrive': intake._iso(eff['arrive']), 'leave': intake._iso(eff['leave']), 'voided': eff['voided']})


def _actual(value):
    stamp = intake._utc(value)
    if stamp > utcnow():
        raise HTTPException(422, '只能登记已实际发生的进出厂，不能填写未来时间')
    return stamp


def _task(db, user, row, key):
    intake._task(db, user, row, key)


def detail(db, user, key):
    visit, row = _visit(db, user, key)
    eff = effective(db, visit)
    corrections = list(db.scalars(select(GateCorrection).where(GateCorrection.visit_id == key).order_by(GateCorrection.id)))
    handoff = db.scalar(select(GateHandoff).where(GateHandoff.visit_id == key))
    tasks = list(db.scalars(select(Task).where(Task.case_id == row.id, Task.status == 'open')))
    allowed = lambda k: user.role in intake.MANAGE or any(t.key == k and t.assignee_id == user.id for t in tasks)
    pending = any(c.status == 'pending' for c in corrections)
    actions = []
    if user.role in FRONT and not pending:
        if visit.status == 'planned' and allowed('gate_arrive'):
            actions += ['arrive', 'cancel']
        elif visit.status == 'inside' and allowed('gate_leave'):
            actions.append('leave')
            if user.role in intake.ADVISE:
                actions.append('handoff')
        if visit.status in {'inside', 'departed'}:
            actions.append('correct')
    return {'id': visit.id, 'version': visit.version, 'case_id': row.id, 'number': row.number, 'title': row.title,
        'customer_vehicle_id': visit.customer_vehicle_id, 'vin': visit.vin, 'purpose': visit.purpose, 'purpose_label': PURPOSES[visit.purpose],
        'description': visit.description, 'status': visit.status, 'arrived_at': intake._iso(eff['arrive']), 'left_at': intake._iso(eff['leave']), 'voided': eff['voided'],
        'actions': actions, 'handoff_appointment_id': handoff.appointment_id if handoff else None,
        'facts': [{'id': f.id, 'direction': f.direction, 'actual_at': intake._iso(f.actual_at), 'evidence_id': f.evidence_id, 'reason': f.reason, 'actor_id': f.actor_id} for f in eff['facts']],
        'corrections': [{'id': c.id, 'version': c.version, 'kind': c.kind, 'actual_at': intake._iso(c.actual_at), 'status': c.status, 'reason': c.reason,
            'evidence_id': c.evidence_id, 'requested_by': c.requested_by,
            'can_review': c.status == 'pending' and user.role in intake.MANAGE and user.id != c.requested_by and allowed('gate_review_' + str(c.id)),
            'can_cancel': c.status == 'pending' and user.id == c.requested_by} for c in corrections]}


def listing(db, user, page, status=None):
    intake._role(user, READ)
    if getattr(user, '_aggregate_scope', False):
        raise HTTPException(409, '请在同源统计中查看集团汇总；原单列表须选择本店')
    query = select(GateVisit).where(GateVisit.case_id.in_(flow.case_query(user).with_only_columns(Case.id)))
    if status:
        query = query.where(GateVisit.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items': [detail(db, user, r.id) for r in db.scalars(query.order_by(GateVisit.id.desc()).offset((page-1)*30).limit(30))], 'total': total, 'page': page}


def catalog(db, user):
    intake._role(user, READ)
    single_store(db)
    base = intake.catalog(db, user)
    return {'vehicles': base['vehicles'], 'resources': base['resources'], 'purposes': PURPOSES, 'can_create': user.role in FRONT}


def create(db, user, key, values):
    intake._role(user, FRONT)
    def run():
        vehicle, customer = intake._vehicle(db, user, values['customer_vehicle_id'])
        row = intake._case(db, user, customer, '非维修进出厂登记', 'gate')
        visit = GateVisit(case_id=row.id, customer_vehicle_id=vehicle.id, vin=vehicle.vin, purpose=values['purpose'], description=values['description'])
        db.add(visit); db.flush()
        flow.set_data(row, gate_visit_id=visit.id)
        flow.ensure_task(db, row, 'gate_arrive', '核对本车与凭据，确认实际进厂或取消安排', 'service', assignee=user.id)
        flow.log_event(db, user, row, 'gate_plan', '登记非维修来访安排；尚无实际进厂', detail={'visit_id': visit.id, 'vin': visit.vin, **values})
        db.flush()
        return detail(db, user, visit.id)
    return _execute(db, user, key, 'create', values, run)


def command(db, user, key, request_id, version, action, values):
    intake._role(user, intake.ADVISE if action == 'handoff' else FRONT)
    def run():
        visit, row = _visit(db, user, key)
        intake._version(visit, version); _no_pending(db, visit)
        lock_vin(db, visit.vin)
        before = row.state
        if action == 'cancel':
            if visit.status != 'planned':
                raise HTTPException(409, '已有实际进厂不能取消冒充离场；请确认实际离场或独立纠正')
            _task(db, user, row, 'gate_arrive')
            visit.status = 'cancelled'; row.state = 'cancelled'; row.completed_date = today()
            flow.close_tasks(db, row, user)
        elif action in {'arrive', 'leave'}:
            expected = 'planned' if action == 'arrive' else 'inside'
            if visit.status != expected:
                raise HTTPException(409, '当前登记不允许重复进出厂或倒序办理')
            _task(db, user, row, 'gate_arrive' if action == 'arrive' else 'gate_leave')
            if values['checked_vin'] != visit.vin:
                raise HTTPException(409, '现场VIN与原车辆不符；不得修改原车辆来代替核验')
            intake._evidence(db, user, row, values['evidence_id'])
            stamp = _actual(values['actual_at'])
            eff = effective(db, visit)
            check_interval(db, visit.vin, stamp if action == 'arrive' else eff['arrive'], stamp if action == 'leave' else None, row.id)
            fact = GateFact(visit_id=visit.id, direction=action, actual_at=stamp, evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason'])
            db.add(fact); db.flush()
            visit.status = 'inside' if action == 'arrive' else 'departed'
            row.state = 'working' if action == 'arrive' else 'completed'
            flow.finish_task(db, row, 'gate_arrive' if action == 'arrive' else 'gate_leave', user)
            if action == 'arrive':
                flow.ensure_task(db, row, 'gate_leave', '确认本次实际离场，或交服务顾问转维修', 'service', assignee=user.id)
            else:
                row.completed_date = intake._local_date(stamp)
        elif action == 'handoff':
            if visit.status != 'inside':
                raise HTTPException(409, '仅已实际进厂且尚未离场的车辆可转维修接待')
            _task(db, user, row, 'gate_leave')
            if values['checked_vin'] != visit.vin:
                raise HTTPException(409, '转接核验VIN与原进厂不一致')
            intake._evidence(db, user, row, values['evidence_id'])
            eff = effective(db, visit)
            arrival_origin = next(f for f in eff['facts'] if f.direction == 'arrive')
            intake._evidence(db, user, row, arrival_origin.evidence_id)
            resource = intake._resource(db, values['resource_id'])
            starts, ends = intake._utc(values['starts_at']), intake._utc(values['ends_at'])
            if ends <= utcnow():
                raise HTTPException(422, '请选择尚未结束的本次维修时段')
            intake._slot(db, resource, starts, ends)
            a = ServiceAppointment(case_id=row.id, customer_vehicle_id=visit.customer_vehicle_id, resource_id=resource.id,
                starts_at=starts, ends_at=ends, mode='walk_in', status='arrived', problem=values['problem'])
            db.add(a); db.flush()
            alias = ArrivalFact(appointment_id=a.id, customer_vehicle_id=visit.customer_vehicle_id, checked_vin=visit.vin,
                odometer_km=values['odometer_km'], evidence_id=arrival_origin.evidence_id, actor_id=arrival_origin.actor_id, occurred_at=eff['arrive'])
            db.add(alias); db.flush()
            db.add(GateHandoff(visit_id=visit.id, appointment_id=a.id, arrival_fact_id=alias.id, origin_fact_id=arrival_origin.id,
                evidence_id=values['evidence_id'], origin_digest=_digest(db, visit), actor_id=user.id))
            visit.status = 'handed_over'
            flow.set_data(row, appointment_id=a.id)
            flow.finish_task(db, row, 'gate_leave', user)
            flow.ensure_task(db, row, 'intake_convert', '沿原实际进厂建立维修明细；不要重复登记到店', 'service', assignee=user.id)
        else:
            raise HTTPException(404, '非维修进出厂动作不存在')
        row.updated_at = utcnow()
        db.flush()
        flow.log_event(db, user, row, 'gate_' + action, {'arrive': '确认实际进厂', 'leave': '确认实际离场', 'cancel': '取消尚未进厂安排', 'handoff': '沿同一实际进厂转维修接待'}[action], before,
            {'visit_id': visit.id, 'fact_id': fact.id if action in {'arrive', 'leave'} else None, **values})
        return detail(db, user, visit.id)
    return _execute(db, user, request_id, action, {'id': key, 'version': version, **values}, run)


def _project(db, visit, kind, stamp):
    eff = effective(db, visit)
    if not eff['arrive'] or eff['voided']:
        raise HTTPException(409, '没有可纠正的有效原进厂事实')
    if kind == 'void_visit':
        return 'voided'
    direction = kind.removesuffix('_time')
    if eff[direction] is None:
        raise HTTPException(409, '原记录不存在该实际方向，不能用改时凭空增加进出厂')
    eff[direction] = stamp
    check_interval(db, visit.vin, eff['arrive'], eff['leave'], visit.case_id)
    return 'departed' if eff['leave'] else 'inside'


def correct(db, user, key, request_id, version, values):
    intake._role(user, FRONT)
    def run():
        visit, row = _visit(db, user, key)
        intake._version(visit, version); _no_pending(db, visit); lock_vin(db, visit.vin)
        if visit.status not in {'inside', 'departed'}:
            raise HTTPException(409, '仅未转维修的实际记录可在此纠正；转接后原进厂已冻结')
        intake._evidence(db, user, row, values['evidence_id'])
        stamp = _actual(values['actual_at']) if values.get('actual_at') else None
        _project(db, visit, values['kind'], stamp)
        correction = GateCorrection(visit_id=visit.id, kind=values['kind'], actual_at=stamp, evidence_id=values['evidence_id'], reason=values['reason'],
            requested_by=user.id, origin_digest=_digest(db, visit), active_visit_id=visit.id)
        db.add(correction); db.flush()
        # Self-review is never allowed, including administrators. The task is
        # assigned only to another active authorized manager; absence is explicit.
        candidates = [u for u in flow.eligible_users(db, 'manager', row.store_id) if u.id != user.id]
        if not candidates:
            candidates = [u for u in flow.eligible_users(db, 'admin', row.store_id) if u.id != user.id and u.role in intake.MANAGE]
        if not candidates:
            raise HTTPException(409, '需要另一位已获本店主管权限的人员独立复核；请先完成岗位配置')
        flow.ensure_task(db, row, 'gate_review_' + str(correction.id), '独立核对原进出厂与纠正凭据', 'manager', assignee=candidates[0].id)
        flow.log_event(db, user, row, 'gate_correction_request', '提交有据纠正，原进出厂仍有效', detail={'correction_id': correction.id, 'origin_digest': correction.origin_digest, **values})
        return detail(db, user, visit.id)
    return _execute(db, user, request_id, 'correct', {'id': key, 'version': version, **values}, run)


def review(db, user, key, request_id, version, action, values):
    intake._role(user, FRONT if action == 'cancel' else intake.MANAGE)
    def run():
        correction = intake._one(db, GateCorrection, key)
        visit, row = _visit(db, user, correction.visit_id)
        intake._version(correction, version); lock_vin(db, visit.vin)
        if correction.status != 'pending':
            raise HTTPException(409, '此纠正申请已经处理')
        if action == 'cancel':
            if user.id != correction.requested_by:
                raise HTTPException(403, '仅原申请人可撤回自己的待复核纠正')
            correction.status = 'cancelled'
        else:
            if correction.requested_by == user.id:
                raise HTTPException(403, '申请人不能复核本人进出厂纠正，包括管理员')
            _task(db, user, row, 'gate_review_' + str(key))
            intake._evidence(db, user, row, values['evidence_id'])
            if _digest(db, visit) != correction.origin_digest:
                raise HTTPException(409, '原实际记录已变化，不能复用过期纠正申请')
            if action == 'approve':
                intake._evidence(db, user, row, correction.evidence_id)
                new_status = _project(db, visit, correction.kind, correction.actual_at)
                visit.status = new_status
                row.state = {'inside': 'working', 'departed': 'completed', 'voided': 'cancelled'}[new_status]
                if new_status == 'voided':
                    row.completed_date = today()
                correction.status = 'approved'
            elif action == 'reject':
                correction.status = 'rejected'
            else:
                raise HTTPException(404, '纠正复核动作不存在')
            db.add(GateReview(correction_id=correction.id, decision=correction.status, evidence_id=values['evidence_id'], reason=values['reason'], actor_id=user.id))
        correction.active_visit_id = None
        visit.updated_at = utcnow(); row.updated_at = utcnow()
        flow.finish_task(db, row, 'gate_review_' + str(key), user)
        if visit.status == 'voided':
            flow.close_tasks(db, row, user)
        db.flush()
        if visit.status == 'departed':
            row.completed_date = intake._local_date(effective(db, visit)['leave'])
        flow.log_event(db, user, row, 'gate_correction_' + action, '记录纠正独立处理结果', detail={'correction_id': key, **values})
        return detail(db, user, visit.id)
    return _execute(db, user, request_id, 'review_' + action, {'id': key, 'version': version, **values}, run)


def cancelled_repair_exit(db, user, key, request_id, version, values):
    intake._role(user, intake.ADVISE | intake.MANAGE)
    def run():
        row = flow.get_case(db, user, key)
        if row.kind != 'repair' or row.flow_version != 4 or row.state != 'cancelled' or row.data.get('released_date'):
            raise HTTPException(409, '此入口只记录已取消但确有到店来源的维修车辆实际离场')
        intake._version(row, version)
        _, binding = intake.context(db, row)
        if binding.vin != values['checked_vin']:
            raise HTTPException(409, '现场VIN与原维修车辆不一致')
        intake._evidence(db, user, row, values['evidence_id'])
        stamp = _actual(values['actual_at'])
        departure_guard(db, binding.vin, repair_case_id=row.id, actual_at=stamp)
        fact = RepairGateExit(case_id=row.id, actual_at=stamp, evidence_id=values['evidence_id'], actor_id=user.id, reason=values['reason'])
        db.add(fact); db.flush()
        flow.finish_task(db, row, 'gate_cancelled_repair_exit', user)
        flow.log_event(db, user, row, 'gate_cancelled_repair_exit', '取消维修后另行确认实际离场；不是完成维修', detail={'fact_id': fact.id, **values})
        return {'case_id': row.id, 'version': row.version, 'exit_id': fact.id, 'actual_at': intake._iso(stamp)}
    return _execute(db, user, request_id, 'repair_exit', {'id': key, 'version': version, **values}, run)
