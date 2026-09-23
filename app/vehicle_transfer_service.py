"""Explicit single-vehicle handoffs; an in-transit car is unavailable at both stores."""
from datetime import date
import re
import uuid
from fastapi import HTTPException
from sqlalchemy import select, or_
from .db import today, utcnow
from .models import Vehicle, Sale, Store
from .flow_models import Case, VehicleHold
from .group_models import GroupIdentity, GroupIdentityLink
from .group_service import authority as identity_authority
from .transfer_service import authority, coordination_scope, execute, evidence, assert_task, destinations
from .vehicle_transfer_models import VehicleCustody, VehicleTransfer, VehicleMovement, VehicleTransferSettlement
from . import flow_engine as eng
from . import business_entity_service as entities
from .tenancy import single_store

LABELS={'requested':'待双方批准','approved':'待发出','transit':'调拨在途','rejected':'拒收待退回','return_transit':'退回在途','accepted':'已验收入库','returned':'已退回原店','cancelled':'已取消','lost':'原在途损失已确认','recovered':'原车已找回入库'}
FACTS=('vin','brand','model','color','supplier','purchase_cost_cents','list_price_cents')


def current_custody(db,vin):
    return db.scalar(select(VehicleCustody).where(VehicleCustody.vin==vin.upper()).with_for_update())


def assert_vehicle_available(db,user,vehicle):
    """Used inside allocation's Vehicle lock. Does not create/infer legacy state."""
    from .vehicle_procurement_service import assert_no_purchase_return
    assert_no_purchase_return(db,vehicle.id)
    with authority(db,user,{'admin','manager','inventory','sales'}):
        from .vehicle_operations_service import assert_no_vehicle_operation
        assert_no_vehicle_operation(db,vehicle.id)
        record=current_custody(db,vehicle.vin)
        if record:
            if record.pending_transfer_id or record.current_vehicle_id!=vehicle.id or record.current_store_id!=vehicle.store_id:
                raise HTTPException(409,'车辆正办理调拨或已不在本店库存，不能占用')
            record.version+=1
            db.flush()


def free_vehicle(db,key):
    row=db.scalar(select(Vehicle).where(Vehicle.id==key).with_for_update())
    if not row or row.approval_state!='approved':raise HTTPException(409,'请选择本店已确认入库且可用的车辆')
    from .vehicle_procurement_service import assert_no_purchase_return
    assert_no_purchase_return(db,row.id)
    from .vehicle_operations_service import assert_no_vehicle_operation
    assert_no_vehicle_operation(db,row.id)
    if db.scalar(select(Sale.id).where(Sale.active_vehicle_id==row.id)) or db.scalar(select(VehicleHold.case_id).where(VehicleHold.vehicle_id==row.id)):
        raise HTTPException(409,'车辆已有销售占用，不能办理调拨')
    return row


def register_custody(db,user,vehicle):
    vin=vehicle.vin.upper()
    if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}',vin):raise HTTPException(422,'调拨前请核对有效的17位VIN')
    row=current_custody(db,vin)
    if row:
        if row.pending_transfer_id or row.current_vehicle_id!=vehicle.id or row.current_store_id!=single_store(db):
            raise HTTPException(409,'同一VIN已有调拨占用或另一份当前库存，不能重复申请')
        return row
    # Registration follows the employee's explicit transfer request. Historical
    # unfinished cases are neither converted nor assigned inferred states.
    with identity_authority(db,user,{'admin','manager','inventory'}):
        identity=db.scalar(select(GroupIdentity).where(GroupIdentity.kind=='vehicle',GroupIdentity.canonical_key==vin))
        if not identity:
            identity=GroupIdentity(kind='vehicle',name=vehicle.model,canonical_key=vin,search_key=vin,created_by=user.id)
            db.add(identity);db.flush()
        link=db.scalar(select(GroupIdentityLink).where(GroupIdentityLink.local_kind=='vehicle',GroupIdentityLink.local_id==vehicle.id))
        if link and link.identity_id!=identity.id:raise HTTPException(409,'库存VIN与已关联共享身份不一致')
        if not link:db.add(GroupIdentityLink(identity_id=identity.id,local_kind='vehicle',local_id=vehicle.id,confirmed_by=user.id))
        row=VehicleCustody(vin=vin,identity_id=identity.id,current_vehicle_id=vehicle.id,current_store_id=vehicle.store_id,generation=vehicle.inventory_generation)
        db.add(row);db.flush()
    return row


def transfer(db,key,sid):
    row=db.scalar(select(VehicleTransfer).where(VehicleTransfer.id==key,or_(VehicleTransfer.from_store_id==sid,VehicleTransfer.to_store_id==sid)))
    if not row:raise HTTPException(404,'整车调拨不存在或不属于当前门店')
    return row


def local_case(db,user,row,sid):
    case=eng.get_case(db,user,row.from_case_id if row.from_store_id==sid else row.to_case_id)
    if case.kind!='vehicle_transfer' or case.flow_version!=2:raise HTTPException(409,'整车调拨流程版本不受支持')
    return case


def serialize(db,user,row,sid):
    case=local_case(db,user,row,sid);source=row.from_store_id==sid
    result={'id':row.id,'number':row.number,'version':row.version,'case_id':case.id,'case_version':case.version,
        'status':row.status,'status_label':LABELS[row.status],'side':'source' if source else 'destination',
        'from_store_name':db.get(Store,row.from_store_id).name,'to_store_name':db.get(Store,row.to_store_id).name,
        'source_approved':bool(row.source_approved_by),'destination_approved':bool(row.destination_approved_by),
        'due_date':row.due_date.isoformat(),'reason':row.reason,'lines':[{'vin':row.vin,'brand':row.snapshot['brand'],'model':row.snapshot['model'],'color':row.snapshot['color']}],
        'movements':[],'actions':[]}
    if user.role in eng.MANAGEMENT:result['lines'][0]['cost_cents']=row.snapshot['purchase_cost_cents']
    for move in db.scalars(select(VehicleMovement).where(VehicleMovement.transfer_id==row.id).order_by(VehicleMovement.id)):
        item={'id':move.id,'kind':move.kind,'quantity':move.quantity,'vehicle_id':move.vehicle_id,
            'evidence_id':move.evidence_id,'business_date':move.business_date.isoformat(),'reason':move.reason}
        if user.role in eng.MANAGEMENT:item['value_cents']=move.value_cents
        result['movements'].append(item)
    if row.status in {'requested','approved'}:
        if user.role in {'admin','manager'} and not (row.source_approved_by if source else row.destination_approved_by):result['actions']+=['approve','reject_request']
        if source and (user.id==row.requested_by or user.role in {'admin','manager'}):result['actions']+=['cancel']
        if source and row.status=='approved' and user.role in {'admin','inventory'}:result['actions']+=['dispatch']
    if user.role in {'admin','inventory'}:
        if not source and row.status=='transit':result['actions']+=['accept','reject']
        if not source and row.status=='rejected':result['actions']+=['return_ship']
        if source and row.status=='return_transit':result['actions']+=['return_receive']
    from .vehicle_transport_service import active as active_exception
    from .vehicle_transport_models import VehicleTransportException
    exception=active_exception(db,row)
    result['active_exception_id']=exception.id if exception else None
    result['exception_ids']=list(db.scalars(select(VehicleTransportException.id).where(VehicleTransportException.transfer_id==row.id).order_by(VehicleTransportException.id)))
    result['can_open_exception']=not exception and row.status in {'transit','rejected','return_transit'} and user.role in {'admin','inventory'}
    if exception:result['actions']=[]
    return result


def detail(db,user,key):
    with authority(db,user) as sid:return serialize(db,user,transfer(db,key,sid),sid)


def list_transfers(db,user):
    with authority(db,user) as sid:
        rows=list(db.scalars(select(VehicleTransfer).where(or_(VehicleTransfer.from_store_id==sid,VehicleTransfer.to_store_id==sid)).order_by(VehicleTransfer.id.desc()).limit(501)))
        if len(rows)>500:raise HTTPException(413,'整车调拨超过500条，请使用具体单号查询')
        return {'items':[serialize(db,user,row,sid) for row in rows]}


def create(db,user,request_id,vehicle_id,destination_store_id,reason,due_date):
    def operation(sid):
        if destination_store_id==sid or not db.scalar(select(Store.id).where(Store.id==destination_store_id,Store.active.is_(True))):raise HTTPException(422,'请选择另一家启用门店')
        vehicle=free_vehicle(db,vehicle_id);custody=register_custody(db,user,vehicle)
        number='HKV'+uuid.uuid4().hex[:16].upper();cases={}
        for party in (sid,destination_store_id):
            with coordination_scope(db,party,(sid,destination_store_id)):
                managers=eng.eligible_users(db,'manager',party)
                if not managers:raise HTTPException(409,'调拨门店尚未配置主管')
                case=Case(number=number+('-OUT' if party==sid else '-IN'),kind='vehicle_transfer',flow_version=2,state='approval',
                    title='整车调拨 · '+('调出' if party==sid else '调入'),owner_id=managers[0].id,created_by=user.id,
                    business_date=today(),due_date=date.fromisoformat(due_date),amount_cents=0,data={})
                db.add(case);entities.note_coordinated_case(db,user,case);db.flush();eng.ensure_task(db,case,'vehicle_approve','确认本店整车调拨安排','manager')
                cases[party]=case.id
        row=VehicleTransfer(number=number,from_store_id=sid,to_store_id=destination_store_id,from_case_id=cases[sid],to_case_id=cases[destination_store_id],
            source_vehicle_id=vehicle.id,vin=vehicle.vin.upper(),snapshot={k:getattr(vehicle,k) for k in FACTS},requested_by=user.id,reason=reason,due_date=date.fromisoformat(due_date))
        db.add(row);db.flush();custody.pending_transfer_id=row.id;vehicle.updated_at=utcnow()
        for party,cid in cases.items():
            with coordination_scope(db,party,(sid,destination_store_id)):
                case=eng.scoped_get(db,Case,cid);case.data={'vehicle_transfer_id':row.id}
                entities.freeze_coordinated_case(db,user,case,row)
                eng.log_event(db,user,case,'vehicle_request','整车调拨申请',detail={'number':number,'vin':row.vin})
        db.flush();return serialize(db,user,row,sid)
    return execute(db,user,request_id,'vehicle:create',dict(vehicle_id=vehicle_id,destination_store_id=destination_store_id,reason=reason,due_date=due_date),operation)


def receipt_vehicle(db,user,row,custody,location_id,case,evidence_id):
    from .master_models import Warehouse, StorageLocation
    location=eng.scoped_get(db,StorageLocation,location_id)
    warehouse=eng.scoped_get(db,Warehouse,location.warehouse_id) if location else None
    if not location or not location.active or not warehouse or not warehouse.active or warehouse.warehouse_type not in {'vehicles','mixed'}:
        raise HTTPException(422,'请选择本店启用的整车库或混合仓库库位')
    if custody.current_vehicle_id is not None:raise HTTPException(409,'该VIN已有当前库存，不能重复接收')
    custody.generation+=1
    vehicle=Vehicle(**row.snapshot,inventory_generation=custody.generation,doc_no=row.number+('-IN' if single_store(db)==row.to_store_id else '-RETURN'),
        business_date=today(),approval_state='approved',created_by=user.id,location=warehouse.name+' / '+location.name,
        note='实物验收来源 '+row.number)
    db.add(vehicle);db.flush()
    with identity_authority(db,user,{'admin','inventory'}):
        db.add(GroupIdentityLink(identity_id=custody.identity_id,local_kind='vehicle',local_id=vehicle.id,confirmed_by=user.id));db.flush()
    custody.current_vehicle_id=vehicle.id;custody.current_store_id=single_store(db);custody.pending_transfer_id=None
    row.received_vehicle_id=vehicle.id;case.vehicle_id=vehicle.id
    from .vehicle_operations_service import record_receipt_position
    record_receipt_position(db,user,case,vehicle,location_id,evidence_id,'transfer_receive')
    return vehicle


def synchronize(db,user,row,action,reason):
    for sid,cid in ((row.from_store_id,row.from_case_id),(row.to_store_id,row.to_case_id)):
        with coordination_scope(db,sid,(row.from_store_id,row.to_store_id)):
            case=eng.scoped_get(db,Case,cid);case.updated_at=utcnow()
            case.state='completed' if row.status in {'accepted','returned','lost','recovered'} else 'cancelled' if row.status=='cancelled' else 'approval' if row.status=='requested' else 'pending' if row.status=='approved' else 'working'
            active=None
            if row.status=='approved' and sid==row.from_store_id:active=('vehicle_dispatch','核对实车并发出调拨')
            elif row.status=='transit' and sid==row.to_store_id:active=('vehicle_receive','核对VIN并验收或拒收')
            elif row.status=='rejected' and sid==row.to_store_id:active=('vehicle_return_ship','确认拒收车辆退回发运')
            elif row.status=='return_transit' and sid==row.from_store_id:active=('vehicle_return_receive','核对VIN并接收退回车辆')
            # Preserve any current assignee; close a task only after its stage ends.
            for key in ('vehicle_dispatch','vehicle_receive','vehicle_return_ship','vehicle_return_receive'):
                if not active or key!=active[0]:eng.finish_task(db,case,key,user)
            if active:eng.ensure_task(db,case,active[0],active[1],'inventory',reopen=True)
            if row.status in {'accepted','returned','cancelled','lost','recovered'}:case.completed_date=today();eng.close_tasks(db,case,user)
            eng.log_event(db,user,case,'vehicle_'+action,'整车调拨：'+LABELS[row.status],detail={'vehicle_transfer_id':row.id,'reason':reason})


def command(db,user,key,request_id,version,case_version,action,values):
    def operation(sid):
        row=transfer(db,key,sid)
        row=db.scalar(select(VehicleTransfer).where(VehicleTransfer.id==row.id).with_for_update())
        case=local_case(db,user,row,sid)
        if row.version!=version or case.version!=case_version:raise HTTPException(409,'调拨已变化，请刷新核对后重新办理')
        row.updated_at=utcnow();case.updated_at=utcnow();db.flush()
        from .vehicle_transport_service import guard_original
        guard_original(db,row)
        custody=current_custody(db,row.vin)
        if not custody or custody.pending_transfer_id!=row.id:raise HTTPException(409,'车辆调拨占用已变化或此单已结束')
        source=row.from_store_id==sid
        if action in {'approve','reject_request'}:
            if user.role not in {'admin','manager'}:raise HTTPException(403,'整车调拨须本店主管批准')
            if row.status not in {'requested','approved'}:raise HTTPException(409,'车辆已经发出，不能撤销审批')
            assert_task(db,user,case,'vehicle_approve')
            if user.id==row.requested_by and user.role!='admin':raise HTTPException(403,'申请人不能自行批准整车调拨')
            if action=='reject_request':row.status='cancelled';custody.pending_transfer_id=None
            else:
                field='source_approved_by' if source else 'destination_approved_by'
                if getattr(row,field):raise HTTPException(409,'本店已经批准')
                setattr(row,field,user.id);eng.finish_task(db,case,'vehicle_approve',user)
                if row.source_approved_by and row.destination_approved_by:row.status='approved'
        elif action=='cancel':
            if not source or (user.id!=row.requested_by and user.role not in {'admin','manager'}):raise HTTPException(403,'仅调出方申请人或主管可取消')
            if row.status not in {'requested','approved'}:raise HTTPException(409,'已经发出的车辆须实际验收或退回')
            row.status='cancelled';custody.pending_transfer_id=None
        else:
            if user.role not in {'admin','inventory'}:raise HTTPException(403,'实车交接须本店库管确认')
            evidence(db,user,case,values['evidence_id'])
            if values['vin'].upper()!=row.vin:raise HTTPException(409,'现场核对VIN与调拨车辆不一致，未做库存变更')
            vehicle=None;quantity=0;value=0
            if action=='dispatch':
                if not source or row.status!='approved':raise HTTPException(409,'须双方批准后由调出方发车')
                assert_task(db,user,case,'vehicle_dispatch');vehicle=free_vehicle(db,row.source_vehicle_id)
                if custody.current_vehicle_id!=vehicle.id or any(getattr(vehicle,k)!=row.snapshot[k] for k in FACTS):raise HTTPException(409,'车辆资料或库存归属已变化，请取消后重新核对')
                vehicle.approval_state='void';vehicle.updated_at=utcnow();custody.current_vehicle_id=None;custody.current_store_id=None
                from .vehicle_operations_service import record_exit_position
                record_exit_position(db,user,case,vehicle,values['evidence_id'],'transfer_dispatch')
                row.status='transit';quantity=-1;value=-row.snapshot['purchase_cost_cents']
            elif action in {'accept','reject'}:
                if source or row.status!='transit':raise HTTPException(409,'调入方只能验收在途车辆')
                assert_task(db,user,case,'vehicle_receive')
                if action=='accept':
                    vehicle=receipt_vehicle(db,user,row,custody,values['location_id'],case,values['evidence_id']);quantity=1;value=row.snapshot['purchase_cost_cents'];row.status='accepted'
                    for party,other,amount in ((row.from_store_id,row.to_store_id,value),(row.to_store_id,row.from_store_id,-value)):
                        with coordination_scope(db,party,(row.from_store_id,row.to_store_id)):
                            db.add(VehicleTransferSettlement(transfer_id=row.id,counterparty_store_id=other,amount_cents=amount))
                else:row.status='rejected'
            elif action=='return_ship':
                if source or row.status!='rejected':raise HTTPException(409,'拒收车辆由调入方确认退回发运')
                assert_task(db,user,case,'vehicle_return_ship');row.status='return_transit'
            elif action=='return_receive':
                if not source or row.status!='return_transit':raise HTTPException(409,'退回在途车辆由原店验收入库')
                assert_task(db,user,case,'vehicle_return_receive');vehicle=receipt_vehicle(db,user,row,custody,values['location_id'],case,values['evidence_id'])
                quantity=1;value=row.snapshot['purchase_cost_cents'];row.status='returned'
            else:raise HTTPException(404,'整车调拨动作不存在')
            db.add(VehicleMovement(transfer_id=row.id,case_id=case.id,vehicle_id=vehicle.id if vehicle else None,kind=action,quantity=quantity,value_cents=value,
                evidence_id=values['evidence_id'],actor_id=user.id,reason=values['reason'],business_date=today()))
        row.updated_at=utcnow();custody.version+=1
        synchronize(db,user,row,action,values['reason']);db.flush();return serialize(db,user,row,sid)
    return execute(db,user,request_id,f'vehicle:{key}:{action}',dict(version=version,case_version=case_version,values=values),operation)
