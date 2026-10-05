"""Physical vehicle custody. Requests never move goods or resurrect sold history."""
import json,uuid
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import Vehicle,Sale,User
from .flow_models import Case,VehicleHold,Task,FlowEvent
from .tenancy import single_store,role_for_store
from .transfer_service import authority,assert_task
from .vehicle_transfer_service import current_custody,register_custody,FACTS
from .vehicle_procurement_service import evidence,rows,one
from .master_data import require_active
from .group_service import authority as identity_authority
from .group_models import GroupIdentityLink
from . import flow_engine as flow
from .vehicle_operations_models import (VehiclePosition as Position,VehicleOperation as Operation,VehicleOperationClaim as Claim,
    VehiclePositionEntry as Entry,VehicleOperationReview as Review,VehicleReturnInspection as Inspection,
    VehicleQuarantineFact as Quarantine,VehicleOrderHoldRelease as HoldRelease)

READ={'admin','manager','inventory','finance','auditor','service','technician'}
MONEY={'admin','manager','finance','auditor'}
MANAGE={'admin','manager'}
INVENTORY={'admin','inventory'}
KINDS={'locate':'现场库位登记','local_move':'整车店内移库','other_out':'整车其他出库','other_return':'其他出库原车退回','customer_return':'客户退车隔离验收'}
STATUS={'requested':'待主管复核','approved':'待实际办理','transit':'店内移库在途','returning':'拒收待原位退回','completed':'已完成','cancelled':'已取消','rejected':'申请已拒绝',
    'awaiting_receipt':'等待实际收车','quarantined':'隔离待检查','inspected':'检查完成待主管判定','rectifying':'待整改复检','release_approved':'合格待实车入库','return_to_customer':'拒收待实际交还','accepted':'已合格入库','returned_to_customer':'已交还客户'}
LABELS={'approve':'批准作业','reject_request':'拒绝申请','cancel':'取消未执行作业','locate':'核对实车登记库位','dispatch':'核对实车实际发出','accept':'目的库位实际接收',
    'reject':'目的库位拒收','return_receive':'原库位实际接回','receive':'原车实际退回入库','intake':'实车接收至隔离位','inspect':'登记本次检查结果','disposition':'主管判定后续处理',
    'release':'合格实车转入可售库存','return_customer':'实车交还客户','reassign':'转交当前待办'}
ROLES={k:(MANAGE if k in {'approve','reject_request','disposition','reassign'} else {'admin','manager','inventory'} if k=='cancel' else {'admin','service','technician'} if k=='inspect' else INVENTORY) for k in LABELS}
TERMINAL={'completed','cancelled','rejected','accepted','returned_to_customer'}


def role_can_read_case(db,role,case):
    """Business-subtype permission, independent of an employee's case ownership.

    Callers must already hold the source store scope. Explicit dossier grants
    can replace individual ownership, but never this role/subtype restriction.
    """
    if case.kind!='vehicle_operations' or role not in READ:return False
    if role in {'service','technician'}:
        return db.scalar(select(Operation.id).where(Operation.id==case.id,
            Operation.store_id==case.store_id,Operation.kind=='customer_return')) is not None
    return True


def can_read_case(db,user,case):
    if getattr(user,'_aggregate_scope',False) or db.info.get('aggregate_scope'):return False
    return role_can_read_case(db,user.role,case)


def get_order(db,user,key):
    case=flow.get_case(db,user,key)
    if case.kind!='vehicle_operations' or case.flow_version!=2:raise HTTPException(404,'车辆作业不存在或流程版本不支持')
    if not can_read_case(db,user,case):raise HTTPException(403,'当前岗位不能查看此车辆作业')
    return case,one(db,Operation,key)


def typed_location(db,key):
    location=require_active(db,'locations',key);warehouse=require_active(db,'warehouses',location.warehouse_id)
    if warehouse.warehouse_type not in {'vehicles','mixed'}:raise HTTPException(422,'请选择本店启用的整车仓或混合仓库位')
    return location,warehouse


def location_name(db,key):
    if not key:return '未定位 / 在途'
    from .master_models import StorageLocation,Warehouse
    loc=flow.scoped_get(db,StorageLocation,key)
    if not loc:return '库位不可见'
    w=flow.scoped_get(db,Warehouse,loc.warehouse_id)
    return (w.name+' / ' if w else '')+loc.name


def assert_no_vehicle_operation(db,vehicle_id=None,vin=None,ignore_case=None):
    """Private central boolean guard; caller must hold custody authority."""
    if vin is None:
        car=flow.scoped_get(db,Vehicle,vehicle_id)
        if not car:return
        vin=car.vin
    q=select(Claim.id).where(Claim.active_vin==vin.upper())
    if ignore_case:q=q.where(Claim.case_id!=ignore_case)
    if db.scalar(q):raise HTTPException(409,'该VIN正在办理车辆移库、出退库或隔离验收，不能重复占用')


def unavailable_vehicle_ids(db):
    # The public lookup consumes only current-store operation identifiers.
    return set(db.scalars(select(Operation.source_vehicle_id).where(Operation.status.not_in(TERMINAL))))


def location_in_use(db,location_id=None,warehouse_id=None):
    from .master_models import StorageLocation
    ids=[location_id] if location_id else list(db.scalars(select(StorageLocation.id).where(StorageLocation.warehouse_id==warehouse_id)))
    if not ids:return False
    return bool(db.scalar(select(Position.id).where(Position.location_id.in_(ids),Position.status=='stored')) or
        db.scalar(select(Operation.id).where(Operation.status.not_in(TERMINAL),(Operation.source_location_id.in_(ids))|(Operation.destination_location_id.in_(ids)))) or
        db.scalar(select(Quarantine.id).join(Operation,Operation.id==Quarantine.operation_id).where(Quarantine.location_id.in_(ids),Operation.status.not_in(TERMINAL))))


def has_location_history(db,location_id=None,warehouse_id=None):
    """Keep historical typed location ownership stable; zero-stock deactivation is separate."""
    from .master_models import StorageLocation
    ids=[location_id] if location_id else list(db.scalars(select(StorageLocation.id).where(StorageLocation.warehouse_id==warehouse_id)))
    return bool(ids and (db.scalar(select(Entry.id).where(Entry.location_id.in_(ids))) or db.scalar(select(Quarantine.id).where(Quarantine.location_id.in_(ids)))))


def sales_committed_vehicle_ids(db,vehicle_ids):
    """Read the original sales/hold blockers under the caller's store authority."""
    ids=tuple(vehicle_ids)
    if not ids:return set()
    return (set(db.scalars(select(Sale.active_vehicle_id).where(Sale.active_vehicle_id.in_(ids)))) |
        set(db.scalars(select(VehicleHold.vehicle_id).where(VehicleHold.vehicle_id.in_(ids)))))


def _free(db,user,vehicle_id,ignore_case=None):
    car=one(db,Vehicle,vehicle_id)
    if car.approval_state!='approved':raise HTTPException(409,'车辆不是本店可用库存')
    from .vehicle_procurement_service import assert_no_purchase_return
    assert_no_purchase_return(db,car.id);assert_no_vehicle_operation(db,car.id,ignore_case=ignore_case)
    if car.id in sales_committed_vehicle_ids(db,(car.id,)):
        raise HTTPException(409,'车辆已有销售占用或已交付，不能办理库存作业')
    custody=register_custody(db,user,car)
    if custody.pending_transfer_id:raise HTTPException(409,'车辆正在跨店调拨')
    car.updated_at=utcnow();custody.version+=1
    return car,custody


def _claim(db,user,case,op):
    assert_no_vehicle_operation(db,vin=op.vin)
    custody=current_custody(db,op.vin)
    if custody:
        if custody.pending_transfer_id:raise HTTPException(409,'VIN正在办理跨店调拨')
        custody.version+=1
    db.add(Claim(case_id=case.id,store_id=single_store(db),vin=op.vin,active_vin=op.vin));db.flush()


def _unclaim(db,op):
    claim=db.scalar(select(Claim).where(Claim.case_id==op.id).with_for_update())
    if not claim or claim.active_vin!=op.vin:raise HTTPException(409,'车辆作业占用事实不一致')
    claim.active_vin=None


def record_receipt_position(db,user,case,vehicle,location_id,evidence_id,kind='purchase_receive'):
    """Called after an authoritative physical receipt, inside the same transaction."""
    loc,wh=typed_location(db,location_id)
    if db.scalar(select(Position.id).where(Position.vehicle_id==vehicle.id)):raise HTTPException(409,'该库存代次已有定位，不能重复建立入位事实')
    db.add(Position(vehicle_id=vehicle.id,location_id=loc.id,status='stored'))
    db.add(Entry(case_id=case.id,vehicle_id=vehicle.id,location_id=loc.id,kind=kind,quantity=1,inventory_delta=0,
        value_cents=vehicle.purchase_cost_cents,evidence_id=evidence_id,actor_id=user.id,business_date=today(),reason='按实际入库凭据建立明确库位'))
    vehicle.location=wh.name+' / '+loc.name


def record_exit_position(db,user,case,vehicle,evidence_id,kind='purchase_return',handover=False):
    """Source stock/cash ledgers remain their domain's facts; this is location only."""
    p=db.scalar(select(Position).where(Position.vehicle_id==vehicle.id).with_for_update())
    if not p:return # Historical unlocated inventory remains explicitly unlocated.
    if p.status not in {'stored','handover'}:raise HTTPException(409,'车辆当前不在可办理的库位状态')
    if p.status=='stored':
        db.add(Entry(case_id=case.id,vehicle_id=vehicle.id,location_id=p.location_id,kind=kind,quantity=-1,inventory_delta=0,value_cents=-vehicle.purchase_cost_cents,
            evidence_id=evidence_id,actor_id=user.id,business_date=today(),reason='依据实车出库来源减少库位数量'))
    p.location_id=None;p.status='handover' if handover else 'exited'


def _position(db,op):
    p=db.scalar(select(Position).where(Position.vehicle_id==op.source_vehicle_id).with_for_update())
    if not p or p.status!='stored' or p.location_id!=op.source_location_id:raise HTTPException(409,'实车来源库位已变化，请重新核对')
    return p


def _entry(db,user,case,op,car,location,kind,quantity,v,inventory_delta=0,original=None):
    row=Entry(case_id=case.id,operation_id=op.id,vehicle_id=car.id,location_id=location,kind=kind,quantity=quantity,inventory_delta=inventory_delta,
        value_cents=quantity*op.cost_cents,original_id=original.id if original else None,evidence_id=v['evidence_id'],actor_id=user.id,business_date=today(),reason=v['reason'])
    db.add(row);db.flush();return row


def _sync(db,user,case,op):
    case.state=('completed' if op.status in {'completed','accepted','returned_to_customer'} else 'cancelled' if op.status=='cancelled' else 'rejected' if op.status=='rejected'
        else 'approval' if op.status=='requested' else 'quality' if op.status in {'quarantined','inspected','rectifying','release_approved','return_to_customer'} else 'working')
    case.data={'operation_id':op.id,'operation_kind':op.kind,'operation_status':op.status};case.updated_at=utcnow()
    mapping={'requested':('review','manager','复核车辆作业来源与安排'),'approved':('physical','inventory','按批准安排核对实车办理'),'transit':('physical','inventory','目的库位核对VIN接收或拒收'),
        'returning':('physical','inventory','原库位核对实车退回'),'awaiting_receipt':('physical','inventory','按授权实际接收退车至隔离位'),
        'quarantined':('inspect','service','检查隔离车辆并记录实际结果'),'rectifying':('inspect','service','整改后重新检查隔离车辆'),
        'inspected':('review','manager','依据本次检查判定可售或整改或拒收'),'release_approved':('physical','inventory','将合格实车转入明确库存库位'),'return_to_customer':('physical','inventory','按拒收结果实际交还车辆')}
    wanted=mapping.get(op.status)
    for task in db.scalars(select(Task).where(Task.case_id==case.id,Task.status=='open')):
        if not wanted or task.key!='vo_'+wanted[0]:flow.finish_task(db,case,task.key,user)
    if wanted:
        existing=db.scalar(select(Task).where(Task.case_id==case.id,Task.key=='vo_'+wanted[0]))
        allowed={'admin','service','technician'} if wanted[0]=='inspect' else {'admin',wanted[1]}
        assignee=None
        if not existing or existing.status!='open' or role_for_store(db,one(db,User,existing.assignee_id),single_store(db)) not in allowed:
            people=[p for p in db.scalars(select(User).where(User.active.is_(True)).order_by(User.id)) if role_for_store(db,p,single_store(db)) in allowed]
            people.sort(key=lambda p:(role_for_store(db,p,single_store(db))=='admin',p.id))
            if not people:raise HTTPException(409,'当前门店尚未配置此车辆作业的实际经办岗位')
            assignee=people[0].id
        assigned=flow.ensure_task(db,case,'vo_'+wanted[0],wanted[2],wanted[1],assignee=assignee,due=case.due_date if not existing or existing.status!='open' else None,reopen=True)
        if wanted[0]=='inspect':assigned.role='technician' if role_for_store(db,one(db,User,assigned.assignee_id),single_store(db))=='technician' else 'service'
    if op.status in TERMINAL:case.completed_date=today()


def available_actions(user,op):
    permitted=[]
    if op.status=='requested':permitted=['approve','reject_request','cancel']
    elif op.status=='approved':permitted=['cancel',{'locate':'locate','local_move':'dispatch','other_out':'dispatch','other_return':'receive'}[op.kind]]
    elif op.status=='transit':permitted=['accept','reject']
    elif op.status=='returning':permitted=['return_receive']
    elif op.status=='awaiting_receipt':permitted=['intake']
    elif op.status in {'quarantined','rectifying'}:permitted=['inspect']
    elif op.status=='inspected':permitted=['disposition']
    elif op.status=='release_approved':permitted=['release']
    elif op.status=='return_to_customer':permitted=['return_customer']
    if op.status not in TERMINAL:permitted+=['reassign']
    return [k for k in permitted if user.role in ROLES[k]]


def describe(db,user,case):
    op=one(db,Operation,case.id)
    if not can_read_case(db,user,case):raise HTTPException(403,'当前岗位不能读取此车辆作业')
    car=one(db,Vehicle,op.source_vehicle_id)
    result={'id':case.id,'number':case.number,'version':case.version,'state':case.state,'kind':op.kind,'kind_label':KINDS[op.kind],
        'status':op.status,'status_label':STATUS[op.status],'vin':op.vin,'model':car.model,'source_vehicle_id':op.source_vehicle_id,'source_generation':op.source_generation,
        'source_location_id':op.source_location_id,'source_location':location_name(db,op.source_location_id),'destination_location_id':op.destination_location_id,
        'destination_location':location_name(db,op.destination_location_id),'received_vehicle_id':op.received_vehicle_id,'reason':op.reason,'recipient':op.recipient,
        'aftercare_case_id':op.aftercare_case_id,'original_operation_id':op.original_operation_id,'due_date':case.due_date.isoformat(),'actions':available_actions(user,op)}
    if user.role in MONEY:result['cost_cents']=op.cost_cents
    result['entries']=[{'id':r.id,'kind':r.kind,'vehicle_id':r.vehicle_id,'location':location_name(db,r.location_id),'quantity':r.quantity,'inventory_delta':r.inventory_delta,
        'original_id':r.original_id,'evidence_id':r.evidence_id,'business_date':r.business_date.isoformat(),**({'value_cents':r.value_cents} if user.role in MONEY else {})} for r in rows(db,Entry,operation_id=op.id)]
    result['inspections']=[{'id':r.id,'outcome':r.outcome,'findings':r.findings,'evidence_id':r.evidence_id,'actor_id':r.actor_id} for r in rows(db,Inspection,operation_id=op.id)]
    result['reviews']=[{'decision':r.decision,'reason':r.reason,'inspection_id':r.inspection_id,'evidence_id':r.evidence_id} for r in rows(db,Review,operation_id=op.id)]
    result['quarantine']=[{'kind':r.kind,'location':location_name(db,r.location_id),'evidence_id':r.evidence_id,'reason':r.reason} for r in rows(db,Quarantine,operation_id=op.id)]
    if op.kind=='other_return':result['source_location']='原其他出库单 #'+str(op.original_operation_id)
    if op.kind=='customer_return':
        intake=next(iter(rows(db,Quarantine,operation_id=op.id,kind='intake')),None)
        actual=next(iter(rows(db,Entry,operation_id=op.id,kind='customer_return')),None)
        result['source_location']='实际隔离位：'+location_name(db,intake.location_id) if intake else '原销售车辆，尚未实际接回'
        result['destination_location']=location_name(db,actual.location_id) if actual else '已实际交还客户' if op.status=='returned_to_customer' else '检查批准后确定可售入库位'
    result['tasks']=[{'id':t.id,'assignee_id':t.assignee_id,'role':t.role,'title':t.title,'due_date':t.due_date.isoformat(),'overdue':t.due_date<today()} for t in rows(db,Task,case_id=case.id) if t.status=='open']
    return result


def execute(db,user,key,action,payload,roles,fn):
    with authority(db,user,roles):
        digest=flow.request_digest('vehicle_operation_'+action,json.loads(json.dumps(payload,default=str)))
        try:
            old=flow.prior_request(db,user,key,digest)
            if old:return describe(db,user,get_order(db,user,old.id)[0])
            case=fn();db.flush();flow.save_receipt(db,user,key,digest,case);db.commit();return describe(db,user,case)
        except (IntegrityError,OperationalError,StaleDataError):
            db.rollback();raise HTTPException(409,'车辆或作业已被并行办理，请刷新核对；不得重复过账')
        except Exception:db.rollback();raise


def create(db,user,key,v):
    def action():
        if not today()<=v['due_date']<=today()+timedelta(days=365):raise HTTPException(422,'请填写今日至一年内的办理期限')
        kind=v['kind'];original=None
        if kind=='other_return':
            original=one(db,Operation,v['original_operation_id'])
            if original.kind!='other_out' or original.status!='completed':raise HTTPException(409,'请选择已实际完成的原其他出库单')
            if db.scalar(select(Operation.id).where(Operation.original_operation_id==original.id,Operation.status=='completed')):raise HTTPException(409,'原出库车辆已经退回')
            car=one(db,Vehicle,original.source_vehicle_id)
            from .vehicle_procurement_service import _vin_state
            if _vin_state(db,car.vin)[0]:raise HTTPException(409,'该VIN已有当前库存或在途业务，不能按原单重复退回')
            custody=current_custody(db,car.vin)
            if not custody or custody.current_vehicle_id is not None or custody.pending_transfer_id:raise HTTPException(409,'原出库车辆保管事实已变化')
        else:car,custody=_free(db,user,v['vehicle_id'])
        dest=v.get('location_id');source=None
        if kind in {'locate','local_move','other_return'}:typed_location(db,dest)
        position=db.scalar(select(Position).where(Position.vehicle_id==car.id).with_for_update())
        if kind=='locate' and position:raise HTTPException(409,'该车辆已有明确库位，请使用店内移库')
        if kind in {'local_move','other_out'}:
            if not position or position.status!='stored':raise HTTPException(409,'请先完成现场库位登记；不得猜测旧地址')
            source=position.location_id;typed_location(db,source)
        if kind=='local_move' and source==dest:raise HTTPException(422,'目的库位须与来源库位不同')
        if kind=='other_out' and not v.get('recipient'):raise HTTPException(422,'其他出库须明确实际接收方或处置去向')
        case=Case(number='HKO'+uuid.uuid4().hex[:18].upper(),kind='vehicle_operations',flow_version=2,state='approval',title=KINDS[kind],
            owner_id=user.id,created_by=user.id,vehicle_id=car.id,business_date=today(),due_date=v['due_date'],amount_cents=0,data={})
        db.add(case);db.flush()
        op=Operation(id=case.id,kind=kind,source_vehicle_id=car.id,source_generation=car.inventory_generation,vin=car.vin,
            source_location_id=source,destination_location_id=dest,original_operation_id=original.id if original else None,
            cost_cents=original.cost_cents if original else car.purchase_cost_cents,reason=v['reason'],recipient=v.get('recipient',''),requested_by=user.id)
        db.add(op);db.flush();_claim(db,user,case,op);_sync(db,user,case,op)
        from .business_entity_service import freeze_case_entity,freeze_derived_case_entity
        if original:freeze_derived_case_entity(db,user,case,one(db,Case,original.id))
        else:freeze_case_entity(db,user,case)
        flow.log_event(db,user,case,'vo_create','申请'+KINDS[kind],detail={'operation_id':op.id});return case
    return execute(db,user,key,'create',v,{'admin','manager','inventory'},action)


def _verify_original(op,car):
    if car.vin!=op.vin or car.inventory_generation!=op.source_generation or car.purchase_cost_cents!=op.cost_cents:
        raise HTTPException(409,'原车辆VIN、代次或成本已变化，须先核对来源，不得覆盖申请')


def _receive_new(db,user,case,op,location_id,v):
    from .vehicle_procurement_service import _vin_state
    loc,wh=typed_location(db,location_id);old=one(db,Vehicle,op.source_vehicle_id);_verify_original(op,old)
    custody=current_custody(db,op.vin)
    if not custody or custody.pending_transfer_id:raise HTTPException(409,'车辆保管来源不一致或正跨店调拨')
    assert_no_vehicle_operation(db,vin=op.vin,ignore_case=op.id)
    if op.kind=='customer_return':
        source=one(db,Case,op.source_order_id);hold=db.scalar(select(VehicleHold).where(VehicleHold.case_id==source.id,VehicleHold.vehicle_id==old.id))
        if hold and not hold.delivered:
            db.add(HoldRelease(source_case_id=source.id,aftercare_case_id=op.aftercare_case_id,vehicle_id=old.id,evidence_id=v['evidence_id'],
                actor_id=user.id,business_date=today(),reason='已发车原单实际退回验收，通过新代次入库释放未交付占用'))
            db.delete(hold);old.approval_state='void';old.updated_at=utcnow()
            previous_position=db.scalar(select(Position).where(Position.vehicle_id==old.id).with_for_update())
            if previous_position:previous_position.status='exited';previous_position.location_id=None
            db.flush()
    blocked,generation=_vin_state(db,op.vin)
    if blocked:raise HTTPException(409,'该VIN存在库存、销售或在途占用，不能重复入库')
    if custody.current_vehicle_id not in {None,old.id}:raise HTTPException(409,'VIN已有另一代次保管记录')
    custody.generation=max(custody.generation,generation)+1
    car=Vehicle(**{k:getattr(old,k) for k in FACTS},inventory_generation=custody.generation,doc_no=case.number+'-IN',
        business_date=today(),approval_state='approved',created_by=user.id,location=wh.name+' / '+loc.name,note='原车实退来源 '+case.number)
    db.add(car);db.flush()
    with identity_authority(db,user,INVENTORY):db.add(GroupIdentityLink(identity_id=custody.identity_id,local_kind='vehicle',local_id=car.id,confirmed_by=user.id));db.flush()
    custody.current_vehicle_id=car.id;custody.current_store_id=single_store(db);op.received_vehicle_id=car.id
    db.add(Position(vehicle_id=car.id,location_id=loc.id,status='stored'))
    original=next(iter(rows(db,Entry,operation_id=op.original_operation_id,kind='other_out')),None) if op.original_operation_id else None
    _entry(db,user,case,op,car,loc.id,'customer_return' if op.kind=='customer_return' else 'other_return',1,v,1,original)
    if op.kind=='customer_return':
        from .addon_service import finalize_vehicle_accessories
        finalize_vehicle_accessories(db,user,one(db,Case,op.aftercare_case_id),one(db,Case,op.source_order_id),car,v['evidence_id'])
    return car


def command(db,user,case_id,key,version,action,v):
    if action not in ROLES:raise HTTPException(404,'车辆作业动作不存在')
    def run():
        case,op=get_order(db,user,case_id)
        if case.version!=version:raise HTTPException(409,'车辆作业已变化，请刷新后核对')
        if action not in available_actions(user,op):raise HTTPException(409,'当前状态不能执行此动作')
        if action=='reassign':
            if not today()<=v['due_date']<=today()+timedelta(days=365):raise HTTPException(422,'交接期限须在今日至一年内')
            task=one(db,Task,v['task_id'])
            if task.case_id!=case.id or task.status!='open':raise HTTPException(409,'请选择本单当前待办')
            target=one(db,User,v['assignee_id']);target_role=role_for_store(db,target,single_store(db))
            allowed={'admin','service','technician'} if task.key=='vo_inspect' else {'admin',task.role}
            if target_role not in allowed:raise HTTPException(422,'接手员工须具有本店对应岗位')
            if task.key=='vo_inspect':task.role='technician' if target_role=='technician' else 'service'
            task.assignee_id=v['assignee_id'];task.due_date=v['due_date'];case.updated_at=utcnow()
            flow.log_event(db,user,case,'vo_reassign','转交车辆作业待办',detail={'task_id':task.id,'assignee_id':task.assignee_id,'reason':v['reason']});return case
        task='review' if action in {'approve','reject_request','disposition'} else 'inspect' if action=='inspect' else 'physical'
        if action!='cancel':assert_task(db,user,case,'vo_'+task)
        if action=='cancel':
            if user.id!=op.requested_by and user.role not in MANAGE:raise HTTPException(403,'只有原申请人或主管能取消未执行作业')
            op.status='cancelled';_unclaim(db,op)
        else:
            evidence(db,user,case,v['evidence_id'])
            if action in {'approve','reject_request'}:
                if user.id==op.requested_by:raise HTTPException(403,'车辆申请与审批须由不同员工办理')
                db.add(Review(operation_id=op.id,decision='approve' if action=='approve' else 'reject',evidence_id=v['evidence_id'],actor_id=user.id,reason=v['reason'],business_date=today()))
                op.status='approved' if action=='approve' else 'rejected'
                if action=='reject_request':_unclaim(db,op)
            elif action in {'inspect','disposition'}:
                if action=='inspect':
                    db.add(Inspection(operation_id=op.id,outcome=v['outcome'],findings=v['findings'],evidence_id=v['evidence_id'],actor_id=user.id,business_date=today()));op.status='inspected'
                else:
                    inspection=rows(db,Inspection,operation_id=op.id)[-1]
                    if v['inspection_id']!=inspection.id:raise HTTPException(409,'须依据最近一次检查，不能引用旧的合格结果')
                    if v['decision']=='release' and inspection.outcome!='pass':raise HTTPException(409,'检查不合格必须整改并复检通过后才能放行')
                    if user.id==inspection.actor_id:raise HTTPException(403,'检查人与放行判定人须不同')
                    db.add(Review(operation_id=op.id,inspection_id=inspection.id,decision=v['decision'],evidence_id=v['evidence_id'],actor_id=user.id,reason=v['reason'],business_date=today()))
                    op.status={'release':'release_approved','rectify':'rectifying','return_to_customer':'return_to_customer'}[v['decision']]
            else:
                if v['vin']!=op.vin:raise HTTPException(422,'现场VIN与本单原车不一致，不能确认实物动作')
                car=one(db,Vehicle,op.source_vehicle_id);_verify_original(op,car)
                if action=='locate':
                    _free(db,user,car.id,op.id)
                    record_receipt_position(db,user,case,car,op.destination_location_id,v['evidence_id'],'locate')
                    # Attach the fact to this operation at creation, never edit an immutable entry.
                    entry=next(e for e in db.new if isinstance(e,Entry) and e.case_id==case.id);entry.operation_id=op.id
                    op.status='completed';_unclaim(db,op)
                elif action=='dispatch':
                    car,custody=_free(db,user,car.id,op.id);p=_position(db,op)
                    _entry(db,user,case,op,car,p.location_id,'local_dispatch' if op.kind=='local_move' else 'other_out',-1,v,-1 if op.kind=='other_out' else 0)
                    p.location_id=None;p.status='transit' if op.kind=='local_move' else 'exited'
                    if op.kind=='other_out':car.approval_state='void';custody.current_vehicle_id=None;custody.current_store_id=None;op.status='completed';_unclaim(db,op)
                    else:op.status='transit'
                elif action in {'accept','reject','return_receive'}:
                    p=one(db,Position,db.scalar(select(Position.id).where(Position.vehicle_id==car.id)))
                    if p.status!='transit':raise HTTPException(409,'车辆不在本单移库在途')
                    if action=='reject':
                        _entry(db,user,case,op,car,None,'local_reject',0,v);op.status='returning'
                    else:
                        loc=op.destination_location_id if action=='accept' else op.source_location_id;location,wh=typed_location(db,loc)
                        original=rows(db,Entry,operation_id=op.id,kind='local_dispatch')[0]
                        _entry(db,user,case,op,car,loc,'local_accept' if action=='accept' else 'local_return',1,v,original=original)
                        p.location_id=loc;p.status='stored';car.location=wh.name+' / '+location.name;op.status='completed';_unclaim(db,op)
                elif action=='receive':
                    _receive_new(db,user,case,op,op.destination_location_id,v);op.status='completed';_unclaim(db,op)
                elif action=='intake':
                    loc,_=typed_location(db,v['location_id'])
                    if v['evidence_id']==op.authorization_evidence_id:raise HTTPException(422,'授权凭据不能替代实际收车凭据')
                    db.add(Quarantine(operation_id=op.id,kind='intake',location_id=loc.id,evidence_id=v['evidence_id'],actor_id=user.id,reason=v['reason'],business_date=today()));op.status='quarantined'
                elif action in {'release','return_customer'}:
                    received=rows(db,Quarantine,operation_id=op.id,kind='intake')[0]
                    if action=='release':
                        _receive_new(db,user,case,op,v['location_id'],v);op.status='accepted'
                    else:op.status='returned_to_customer'
                    db.add(Quarantine(operation_id=op.id,kind='release' if action=='release' else 'return_to_customer',location_id=received.location_id,evidence_id=v['evidence_id'],actor_id=user.id,reason=v['reason'],business_date=today()));_unclaim(db,op)
        _sync(db,user,case,op);flow.log_event(db,user,case,'vo_'+action,LABELS[action],detail={'operation_id':op.id,'evidence_id':v.get('evidence_id'),'reason':v.get('reason','')});return case
    return execute(db,user,key,action,{'case_id':case_id,'version':version,**v},ROLES[action],run)


def prepare_customer_return(db,user,aftercare_case,source_order,evidence_id):
    from .aftercare_service import require_vehicle_return_authorization
    require_vehicle_return_authorization(db,user,aftercare_case,source_order,evidence_id)
    with authority(db,user,READ|{'sales','reception'}):
        existing=db.scalar(select(Operation).where(Operation.aftercare_case_id==aftercare_case.id))
        if existing:return existing.id
        if source_order.kind!='order' or not source_order.vehicle_id or not source_order.data.get('dispatched_at'):raise HTTPException(409,'客户实退须关联已实际出库的原销售车辆')
        if not db.scalar(select(FlowEvent.id).where(FlowEvent.case_id==source_order.id,FlowEvent.action=='dispatch')) or not db.scalar(select(VehicleHold.vehicle_id).where(VehicleHold.case_id==source_order.id,VehicleHold.vehicle_id==source_order.vehicle_id)):
            raise HTTPException(409,'原销售实际出库事件或车辆占用来源不完整，不能推断旧单状态')
        car=one(db,Vehicle,source_order.vehicle_id);custody=current_custody(db,car.vin)
        if custody and (custody.pending_transfer_id or custody.current_vehicle_id not in {None,car.id}):raise HTTPException(409,'原VIN已有另一笔保管或调拨业务')
        if not custody:
            # Confirmed sales source, never a guessed migration of old unfinished data.
            with authority(db,user,READ|{'sales','reception'}):
                with identity_authority(db,user,READ|{'sales','reception'}):
                    from .group_models import GroupIdentity
                    from .vehicle_transfer_models import VehicleCustody
                    identity=db.scalar(select(GroupIdentity).where(GroupIdentity.kind=='vehicle',GroupIdentity.canonical_key==car.vin))
                    if not identity:identity=GroupIdentity(kind='vehicle',name=car.model,canonical_key=car.vin,search_key=car.vin,created_by=user.id);db.add(identity);db.flush()
                    custody=VehicleCustody(vin=car.vin,identity_id=identity.id,current_vehicle_id=car.id,current_store_id=car.store_id,generation=car.inventory_generation);db.add(custody);db.flush()
                    if not db.scalar(select(GroupIdentityLink.id).where(GroupIdentityLink.local_kind=='vehicle',GroupIdentityLink.local_id==car.id)):db.add(GroupIdentityLink(identity_id=identity.id,local_kind='vehicle',local_id=car.id,confirmed_by=user.id))
        case=Case(number='HKQ'+uuid.uuid4().hex[:18].upper(),kind='vehicle_operations',flow_version=2,state='working',title=KINDS['customer_return'],
            owner_id=aftercare_case.owner_id,created_by=user.id,parent_id=aftercare_case.id,vehicle_id=car.id,business_date=today(),due_date=aftercare_case.due_date or today(),amount_cents=0,data={})
        db.add(case);db.flush()
        op=Operation(id=case.id,kind='customer_return',status='awaiting_receipt',source_vehicle_id=car.id,source_generation=car.inventory_generation,vin=car.vin,
            aftercare_case_id=aftercare_case.id,source_order_id=source_order.id,authorization_evidence_id=evidence_id,cost_cents=car.purchase_cost_cents,reason='经原销售售后方案与客户授权安排实车隔离验收',recipient='',requested_by=user.id)
        db.add(op);db.flush();_claim(db,user,case,op);_sync(db,user,case,op)
        from .business_entity_service import freeze_derived_case_entity
        freeze_derived_case_entity(db,user,case,aftercare_case)
        flow.log_event(db,user,case,'vo_return_plan','按售后授权建立实车验收待办，尚未收车',detail={'aftercare_case_id':aftercare_case.id,'authorization_evidence_id':evidence_id});return case.id


def get_customer_return_proof(db,user,aftercare_case_id):
    single_store(db)
    op=db.scalar(select(Operation).where(Operation.aftercare_case_id==aftercare_case_id))
    if not op:return {'operation_case_id':None,'status':None,'physically_received':False,'accepted':False,'new_vehicle_id':None,'inspection_outcome':None,'returned_to_customer':False}
    inspection=rows(db,Inspection,operation_id=op.id)
    return {'operation_case_id':op.id,'status':op.status,'physically_received':bool(rows(db,Quarantine,operation_id=op.id,kind='intake')),
        'accepted':op.status=='accepted' and op.received_vehicle_id is not None,'new_vehicle_id':op.received_vehicle_id,
        'inspection_outcome':inspection[-1].outcome if inspection else None,'returned_to_customer':op.status=='returned_to_customer','rejected':op.status in {'return_to_customer','returned_to_customer'}}


def cancel_customer_return_plan(db,user,aftercare_case,reason):
    with authority(db,user,READ|{'sales','reception'}):
        op=db.scalar(select(Operation).where(Operation.aftercare_case_id==aftercare_case.id))
        if not op or op.status in {'cancelled','returned_to_customer'}:return
        if op.status!='awaiting_receipt':raise HTTPException(409,'车辆已实际接收，须完成隔离处理或实际交还，不能取消抹除实物事实')
        case=one(db,Case,op.id);op.status='cancelled';_unclaim(db,op);_sync(db,user,case,op)
        flow.log_event(db,user,case,'vo_cancel_authorization','售后授权撤回，取消未收车计划',detail={'aftercare_case_id':aftercare_case.id,'reason':reason})


def release_undispatched_order_hold(db,user,source_order,aftercare_case,evidence_id):
    from .aftercare_service import require_vehicle_return_authorization
    # The aftercare helper proves the approved frozen source and client consent;
    # its apply command must call this before changing its state to completed.
    require_vehicle_return_authorization(db,user,aftercare_case,source_order,evidence_id)
    from .aftercare_models import AftercareApplication
    if not db.scalar(select(AftercareApplication.id).where(AftercareApplication.case_id==aftercare_case.id)):
        raise HTTPException(409,'未发车占用只能随售后纠正实际生效同事务释放')
    # 2026-09-27 实测：读保管/占用事实（current_custody、VehicleHold）也走调拨保护守卫，
    # 原先把权威上下文只开在写分支，正常路径一进来就被 403“调拨协调记录须通过授权调拨服务办理”
    # 打断。这里把读取与写入放进同一个上下文，保证售后纠正的实际生效不依赖调用顺序。
    with authority(db,user,READ|{'sales','reception'}):
        if source_order.data.get('dispatched_at'):raise HTTPException(409,'已实际出库车辆须实退验收，不可直接释放原单占用')
        existing=db.scalar(select(HoldRelease).where(HoldRelease.source_case_id==source_order.id))
        if existing:
            if existing.aftercare_case_id!=aftercare_case.id:raise HTTPException(409,'原单已有其他生效释放来源')
            return
        hold=db.scalar(select(VehicleHold).where(VehicleHold.case_id==source_order.id))
        if not hold:return
        if hold.delivered:raise HTTPException(409,'已交付历史占用不可删除或重新激活')
        car=one(db,Vehicle,hold.vehicle_id)
        assert_no_vehicle_operation(db,car.id)
        custody=current_custody(db,car.vin)
        if custody:custody.version+=1
        car.updated_at=utcnow()
        db.add(HoldRelease(source_case_id=source_order.id,aftercare_case_id=aftercare_case.id,vehicle_id=car.id,evidence_id=evidence_id,
            actor_id=user.id,business_date=today(),reason='原销售未发车，按已批准且客户同意的生效终止释放未交付占用'));db.delete(hold)
        # 保管记录在上下文内被改动，但真正落库可能发生在退出上下文之后（后续查询触发 autoflush），
        # 那时守卫已恢复，flush 会再抛 403。这里在仍持有权威的当下把改动落库。
        db.flush()
