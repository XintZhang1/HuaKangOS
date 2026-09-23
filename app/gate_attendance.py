"""One local VIN lock and one interval model across gate and original intake.

The lock uses the earliest local VIN relation, including inactive relations; it
is therefore common to different customer links and service resources. The
versioned update is flushed before inspecting intervals. PostgreSQL repeatable
read/SQLite conflicts are mapped by the outer command to a non-retried 409.
"""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .customer_service_models import CustomerVehicle
from .flow_models import Case, FlowEvent
from .service_intake_models import ServiceAppointment, ArrivalFact, ReworkRequest
from .gate_visit_models import GateVisit, GateFact, GateCorrection, GateHandoff, RepairGateExit
from .inventory_report_common import bounded


def lock_vin(db, vin):
    row = db.scalar(select(CustomerVehicle).where(CustomerVehicle.vin == vin).order_by(CustomerVehicle.id).limit(1))
    if row is None:
        raise HTTPException(409, '本店核验车辆来源缺失，不能登记进出厂')
    row.updated_at = utcnow()
    db.flush()


def effective(db, visit):
    facts = list(db.scalars(select(GateFact).where(GateFact.visit_id == visit.id).order_by(GateFact.id)))
    result = {'arrive': None, 'leave': None, 'voided': False, 'facts': facts, 'corrections': []}
    for fact in facts:
        result[fact.direction] = fact.actual_at
    for correction in db.scalars(select(GateCorrection).where(GateCorrection.visit_id == visit.id, GateCorrection.status == 'approved').order_by(GateCorrection.id)):
        result['corrections'].append(correction)
        if correction.kind == 'void_visit':
            result['voided'] = True
        else:
            result[correction.kind.removesuffix('_time')] = correction.actual_at
    return result


def intervals(db, vin):
    """Authoritative local source intervals; never infer departure from state."""
    output = []
    gates = bounded(db, GateVisit, select(GateVisit).where(GateVisit.vin == vin))
    handed = {h.visit_id for h in db.scalars(select(GateHandoff).where(GateHandoff.visit_id.in_([v.id for v in gates])))}
    for visit in gates:
        if visit.id in handed:
            continue
        eff = effective(db, visit)
        if eff['arrive'] and not eff['voided']:
            output.append({'case_id': visit.case_id, 'arrive': eff['arrive'], 'leave': eff['leave'], 'source': 'gate'})
    appointments = bounded(db, ServiceAppointment, select(ServiceAppointment).where(ServiceAppointment.id.in_(select(ArrivalFact.appointment_id).where(ArrivalFact.checked_vin == vin))))
    rows = {a.appointment_id: a for a in db.scalars(select(ArrivalFact).where(ArrivalFact.appointment_id.in_([a.id for a in appointments])))}
    for appointment in appointments:
        arrival = rows[appointment.id]
        output.append({'case_id': appointment.case_id, 'repair_case_id': appointment.repair_case_id, 'arrive': arrival.occurred_at, 'leave': None, 'source': 'intake'})
    conversions = bounded(db, FlowEvent, select(FlowEvent).where(FlowEvent.action == 'intake_rework_convert', FlowEvent.detail['checked_vin'].as_string() == vin))
    for event in conversions:
        request = db.scalar(select(ReworkRequest).where(ReworkRequest.case_id == event.case_id))
        if not request or not request.repair_case_id:
            raise HTTPException(409, '原返修到店来源不完整，请先核对，不能另记进厂')
        output.append({'case_id': request.case_id, 'repair_case_id': request.repair_case_id, 'arrive': event.occurred_at, 'leave': None, 'source': 'rework'})
    for record in output:
        if record['source'] == 'gate':
            continue
        repair_id = record.get('repair_case_id')
        if repair_id:
            repair = db.scalar(select(Case).where(Case.id == repair_id))
            if not repair:
                raise HTTPException(409, '原接待关联维修不在本店，不能推断已离场')
            releases = list(db.scalars(select(FlowEvent).where(FlowEvent.case_id == repair_id, FlowEvent.action == 'repair_v' + str(repair.flow_version) + '_release')))
            exits = list(db.scalars(select(RepairGateExit).where(RepairGateExit.case_id == repair_id)))
            if len(releases) + len(exits) > 1:
                raise HTTPException(409, '原维修存在多条离场来源，请核对后办理')
            if releases:
                record['leave'] = releases[0].occurred_at
            elif exits:
                record['leave'] = exits[0].actual_at
        else:
            leaves = list(db.scalars(select(FlowEvent).where(FlowEvent.case_id == record['case_id'], FlowEvent.action == 'intake_leave')))
            if len(leaves) > 1:
                raise HTTPException(409, '原接待离场来源重复，请核对后办理')
            if leaves:
                record['leave'] = leaves[0].occurred_at
    return output


def check_interval(db, vin, arrival, departure=None, exclude_case=None):
    if not arrival or (departure is not None and departure < arrival):
        raise HTTPException(409, '实际离场不能早于本次进厂')
    for old in intervals(db, vin):
        if old['case_id'] == exclude_case:
            continue
        # Adjacent intervals may share an exact boundary. Equal *open* arrivals
        # are not adjacent and are rejected. Missing departure remains unknown.
        if old['leave'] is not None and old['leave'] <= arrival:
            continue
        if departure is not None and departure <= old['arrive']:
            continue
        raise HTTPException(409, '同一VIN已有重叠进厂或尚无实际离场的来源；请回原记录核对，不能重复登记')


def arrive_guard(db, vin):
    lock_vin(db, vin)
    check_interval(db, vin, utcnow())


def departure_guard(db, vin, repair_case_id=None, intake_case_id=None, actual_at=None):
    lock_vin(db, vin)
    matches = [r for r in intervals(db, vin) if (repair_case_id and r.get('repair_case_id') == repair_case_id) or (intake_case_id and r['case_id'] == intake_case_id)]
    if len(matches) != 1 or matches[0]['leave'] is not None:
        raise HTTPException(409, '本次实际到店来源缺失、重复或已离场，请核对原记录')
    current = matches[0]
    check_interval(db, vin, current['arrive'], actual_at or utcnow(), current['case_id'])
    return current
