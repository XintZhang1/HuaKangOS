"""Extend the existing same-row attendance report, never add a second gate count."""
from sqlalchemy import select
from sqlalchemy.orm import load_only
from .flow_models import FlowEvent,FileAsset
from .gate_visit_models import GateVisit,GateFact,GateCorrection,GateReview,GateHandoff,RepairGateExit
from .gate_visit_integrity import check_bundle,check_cancelled_exit
from .service_intake_models import RepairVehicleBinding
from .customer_service_models import CustomerVehicle
from .gate_visit_service import PURPOSES
from .inventory_report_common import bounded


def _row(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}


def extend_sessions(db,cases,sessions,aggregate,case_id):
    ids=list(cases)
    visits=bounded(db,GateVisit,select(GateVisit).where(GateVisit.case_id.in_(ids)))
    keys=[v.id for v in visits]
    facts=bounded(db,GateFact,select(GateFact).where(GateFact.visit_id.in_(keys)))
    corrections=bounded(db,GateCorrection,select(GateCorrection).where(GateCorrection.visit_id.in_(keys)))
    reviews={r.correction_id:_row(r) for r in bounded(db,GateReview,select(GateReview).where(GateReview.correction_id.in_([c.id for c in corrections])))}
    handoffs={h.visit_id:h for h in bounded(db,GateHandoff,select(GateHandoff).where(GateHandoff.visit_id.in_(keys)))}
    events=[_row(e) for e in bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.case_id.in_(ids),((FlowEvent.action.like('gate_%')) | (FlowEvent.action.in_(['repair_v4_cancel','repair_v4_release'])))))]
    files={f.id:{k:getattr(f,k) for k in ('id','store_id','case_id','generated')} for f in bounded(db,FileAsset,select(FileAsset).options(load_only(FileAsset.id,FileAsset.store_id,FileAsset.case_id,FileAsset.generated)).where(FileAsset.case_id.in_(ids)))}
    issues=[];changes=[];bycase={s['case_id']:s for s in sessions}
    for visit in visits:
        fs=[_row(f) for f in facts if f.visit_id==visit.id];cs=[_row(c) for c in corrections if c.visit_id==visit.id]
        selected=not case_id or case_id==visit.case_id or (visit.case_id in bycase and bycase[visit.case_id].get('repair_case_id')==case_id)
        if not selected:continue
        try: eff=check_bundle(_row(visit),fs,cs,reviews,events,files)
        except ValueError as error:
            issues.append({'case_id':visit.case_id,'source_id':visit.id,'message':str(error)})
            if visit.case_id in bycase:sessions.remove(bycase[visit.case_id])
            continue
        for c in cs:
            changes.append({'case_id':visit.case_id,'id':c['id'],'kind':c['kind'],'status':c['status'],'actual_at':c['actual_at'],'requested_at':c['created_at']})
        if not eff['arrive'] or eff['voided']:continue
        arrival=next(f for f in fs if f['direction']=='arrive');departure=next((f for f in fs if f['direction']=='leave'),None)
        if visit.id in handoffs:
            current=bycase.get(visit.case_id)
            if not current or current['arrived_at']!=eff['arrive'] or current['arrival_source_id']!=handoffs[visit.id].arrival_fact_id:
                issues.append({'case_id':visit.case_id,'source_id':visit.id,'message':'转接原进厂与维修接待的来源不一致；不重复计数'})
                if current:sessions.remove(current)
                continue
            current.update(arrival_source='gate_facts',arrival_source_id=arrival['id'],profile=PURPOSES[visit.purpose]+'转维修；沿原进厂')
        else:
            sessions.append({'case_id':visit.case_id,'repair_case_id':None,'store_id':visit.store_id,'vin':None if aggregate else visit.vin,
                'arrived_at':eff['arrive'],'arrival_source_id':arrival['id'],'arrival_source':'gate_facts','profile':PURPOSES[visit.purpose],
                'left_at':eff['leave'],'departure_source_id':departure['id'] if departure else None,'departure_kind':'非维修实际离场','departure_source':'gate_facts'})
    exits=bounded(db,RepairGateExit,select(RepairGateExit).where(RepairGateExit.case_id.in_(ids)))
    bindings={b.case_id:_row(b) for b in bounded(db,RepairVehicleBinding,select(RepairVehicleBinding).where(RepairVehicleBinding.case_id.in_([x.case_id for x in exits])))}
    vehicles={v.id:_row(v) for v in bounded(db,CustomerVehicle,select(CustomerVehicle).where(CustomerVehicle.id.in_([b['customer_vehicle_id'] for b in bindings.values()])))}
    for exit in exits:
        current=next((s for s in sessions if s.get('repair_case_id')==exit.case_id),None)
        try:
            if not current or current['left_at']:
                raise ValueError('取消维修实际离场缺少唯一仍未离场的原到店')
            actual=check_cancelled_exit(_row(cases[exit.case_id]),_row(exit),bindings.get(exit.case_id),vehicles.get(bindings.get(exit.case_id,{}).get('customer_vehicle_id')),current['arrived_at'],events,files)
        except ValueError as error:
            issues.append({'case_id':exit.case_id,'source_id':exit.id,'message':str(error)})
            continue
        current.update(left_at=actual,departure_source_id=exit.id,departure_kind='取消维修后实际离场；不是维修完工',departure_source='gate_repair_exits')
    return issues,changes
