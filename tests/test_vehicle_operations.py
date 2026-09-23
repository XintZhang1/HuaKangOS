"""Actual vehicle movements, history generations, refusal and ledger conservation."""
import uuid,sqlite3
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today,engine
from app.models import Vehicle,User
from app.flow_models import Case,VehicleHold
from app.vehicle_operations_models import VehiclePosition,VehiclePositionEntry,VehicleOperation
from app import vehicle_operations_service as svc
from app.tenancy import set_scope,project_user
from tests.conftest import login
from tests.test_workflow import evidence
from tests.test_vehicle_procurement import approved,ship,receive,typed,command as purchase_command,get as purchase_get

API='/api/vehicle-operations'
def inventory(c):
    row,loc=approved(c,1);row=ship(c,row);row=receive(c,row,loc)
    return row,row['receipts'][0]['vehicle_id'],loc
def destination(c):
    w=typed(c,'warehouses',{'code':'V'+uuid.uuid4().hex[:5],'name':'虚构车辆二仓','warehouse_type':'vehicles'})
    return typed(c,'locations',{'code':'P'+uuid.uuid4().hex[:5],'name':'明确目的库位','warehouse_id':w['id']})['id']
def create(c,kind,vehicle=None,location=None,original=None,status=201,key=None):
    v={'request_id':key or uuid.uuid4().hex,'kind':kind,'reason':'有来源的虚构实物作业','due_date':today().isoformat()}
    if vehicle:v['vehicle_id']=vehicle
    if location:v['location_id']=location
    if original:v['original_operation_id']=original
    if kind=='other_out':v['recipient']='虚构报废处置单位'
    r=c.post(API+'/orders',json=v);assert r.status_code==status,r.text;return r.json()
def get(c,row):
    r=c.get(API+'/orders/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def act(c,row,action,values=None,status=200,key=None,version=None):
    now=get(c,row);v={'reason':'本人核对实际来源及交接'}
    if action not in {'cancel','reassign'}:v['evidence_id']=evidence(c,row)
    if action in {'locate','dispatch','accept','reject','return_receive','receive','intake','release','return_customer'}:v['vin']=row['vin']
    v.update(values or {})
    review_login=status==200 and action in {'approve','reject_request','disposition'} and c.get('/api/auth/me').json()['role']=='admin'
    if review_login:login(c,'manager')
    try:
        r=c.post(API+f'/orders/{row["id"]}/actions/{action}',json={'request_id':key or uuid.uuid4().hex,'version':now['version'] if version is None else version,'values':v})
        assert r.status_code==status,r.text;return r.json()
    finally:
        if review_login:login(c,'admin')

def test_local_move_actual_transit_reject_original_return_conserves(client):
    purchase,vid,loc=inventory(client);dest=destination(client)
    login(client,'inventory');row=create(client,'local_move',vid,dest)
    assert client.get('/api/flow/lookup/vehicle').json()['items']==[]
    act(client,row,'dispatch',status=409)
    login(client,'manager');row=act(client,row,'approve')
    login(client,'inventory');act(client,row,'dispatch',{'vin':'LHGCM82633A999999'},422)
    row=act(client,row,'dispatch');assert row['status']=='transit'
    act(client,row,'cancel',status=409)
    row=act(client,row,'reject');row=act(client,row,'return_receive');assert row['status']=='completed'
    with SessionLocal() as db:
        p=db.scalar(select(VehiclePosition).where(VehiclePosition.vehicle_id==vid));assert p.location_id==loc and p.status=='stored'
        assert sum(e.quantity for e in db.scalars(select(VehiclePositionEntry).where(VehiclePositionEntry.operation_id==row['id'])))==0
        assert sum(e.value_cents for e in db.scalars(select(VehiclePositionEntry).where(VehiclePositionEntry.operation_id==row['id'])))==0
        assert db.scalar(select(Vehicle).where(Vehicle.id==vid)).inventory_generation==1

def test_other_out_return_new_generation_original_value_and_restore(client,tmp_path):
    purchase,vid,loc=inventory(client);row=create(client,'other_out',vid);row=act(client,row,'approve');row=act(client,row,'dispatch')
    assert row['entries'][0]['inventory_delta']==-1 and row['entries'][0]['value_cents']==-10000001
    back=create(client,'other_return',location=loc,original=row['id']);back=act(client,back,'approve');back=act(client,back,'receive')
    assert back['received_vehicle_id']!=vid
    with SessionLocal() as db:
        cars=list(db.scalars(select(Vehicle).order_by(Vehicle.id)));assert [(c.store_id,c.inventory_generation,c.approval_state) for c in cars]==[(1,1,'void'),(1,2,'approved')]
        facts=list(db.scalars(select(VehiclePositionEntry).where(VehiclePositionEntry.inventory_delta!=0)));assert sum(e.quantity for e in facts)==0 and sum(e.value_cents for e in facts)==0
    create(client,'other_return',location=loc,original=row['id'],status=409)
    from app.vehicle_backup_integrity import validate_vehicle_custody
    from app.vehicle_operations_backup_integrity import validate_vehicle_operations
    target=tmp_path/'restore.sqlite'
    with sqlite3.connect(engine.url.database) as source,sqlite3.connect(target) as copy:
        source.backup(copy);assert validate_vehicle_operations(copy)['verified_vehicle_operations']==2;validate_vehicle_custody(copy)
        copy.execute('UPDATE vehicle_position_entries SET value_cents=value_cents+1 WHERE inventory_delta=1');copy.commit()
        import pytest
        with pytest.raises(ValueError,match='守恒|冲回'):validate_vehicle_operations(copy)

def test_actual_other_out_allows_empty_custody_only_with_facts(client):
    _,vid,_=inventory(client);row=create(client,'other_out',vid);row=act(client,row,'approve');row=act(client,row,'dispatch')
    from app.vehicle_backup_integrity import validate_vehicle_custody
    with sqlite3.connect(engine.url.database) as db:validate_vehicle_custody(db)

def test_pending_blocks_supplier_return_cross_store_and_roles(client):
    purchase,vid,loc=inventory(client);row=create(client,'local_move',vid,destination(client))
    purchase_command(client,purchase,'return_request',{'shipment_id':purchase['shipments'][0]['id'],'reason':'不允许绕过车辆作业','evidence_id':evidence(client,purchase)},409)
    create(client,'other_out',vid,status=409)
    login(client,'inventory');view=get(client,row);assert 'cost_cents' not in view and all('value_cents' not in e for e in view['entries'])
    act(client,row,'approve',status=403)
    login(client,'service');assert client.get(API+'/orders/'+str(row['id'])).status_code==404
    assert client.get(API+'/orders').json()['items']==[]
    login(client,'sales');assert client.get(API+'/orders').status_code==403
    login(client,'admin');client.post('/api/stores',json={'code':'VB','name':'虚构车辆乙店'});client.headers['X-Store-ID']='2'
    assert client.get(API+'/orders/'+str(row['id'])).status_code==404
    create(client,'other_out',vid,status=404)
    client.headers['X-Store-ID']='all';assert client.get(API+'/orders').status_code==409

def test_duplicate_stale_competing_actual_dispatch(client):
    _,vid,loc=inventory(client);row=create(client,'other_out',vid);row=act(client,row,'approve')
    v={'reason':'本人实际交车完成','evidence_id':evidence(client,row),'vin':row['vin']};row=get(client,row);key=uuid.uuid4().hex
    def do(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
            try:svc.command(db,user,row['id'],uuid.uuid4().hex,row['version'],'dispatch',v);return 200
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(do,range(2)))==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(VehiclePositionEntry).where(VehiclePositionEntry.kind=='other_out'))==1
    back=create(client,'other_return',location=loc,original=row['id']);back=act(client,back,'approve');v['evidence_id']=evidence(client,back);v['vin']=back['vin'];back=get(client,back)
    body={'request_id':key,'version':back['version'],'values':v};a=client.post(API+f'/orders/{back["id"]}/actions/receive',json=body);assert a.status_code==200,a.text
    b=client.post(API+f'/orders/{back["id"]}/actions/receive',json=body);assert b.json()==a.json()
    body['request_id']=uuid.uuid4().hex;assert client.post(API+f'/orders/{back["id"]}/actions/receive',json=body).status_code==409

def test_cancel_approved_and_destination_accept(client):
    _,vid,loc=inventory(client);dest=destination(client);row=create(client,'local_move',vid,dest);row=act(client,row,'approve');row=act(client,row,'cancel')
    assert row['entries']==[]
    row=create(client,'local_move',vid,dest);row=act(client,row,'approve');row=act(client,row,'dispatch');row=act(client,row,'accept')
    with SessionLocal() as db:assert db.scalar(select(VehiclePosition.location_id).where(VehiclePosition.vehicle_id==vid))==dest

def test_no_guessed_location_and_non_vehicle_warehouse(client):
    purchase,vid,loc=inventory(client)
    # Existing purchase receipt has typed source, so cannot overwrite by a locate command.
    create(client,'locate',vid,loc,status=409)
    w=typed(client,'warehouses',{'code':'PARTS','name':'配件仓','warehouse_type':'materials'})
    wrong=typed(client,'locations',{'code':'PARTL','name':'配件位','warehouse_id':w['id']})
    create(client,'local_move',vid,wrong['id'],status=422)

def returned_sale(c,delivered=True):
    from tests.test_workflow import order,action,approved_doc
    from tests.test_aftercare import create as after_create,plan,approved as after_approve,confirmed
    from tests.test_procurement import bank
    purchase,vid,loc=inventory(c)
    source=action(c,order(c,'100.00',model='虚构型号'),'approve');source=action(c,source,'allocate',{'vehicle_id':vid})
    sid=approved_doc(c,source,'contract');source=action(c,source,'sign',{'evidence_id':evidence(c,source,'signed_contract',sid)})
    source=action(c,source,'receive',{'amount':'100','account_id':bank(c),'reference':'虚构原车款','evidence_id':evidence(c,source,'receipt')})
    source=action(c,source,'inspect',{'outcome':'合格','result':'原始出库检查合格','evidence_id':evidence(c,source,'inspection')})
    source=action(c,source,'dispatch',{'evidence_id':evidence(c,source)})
    with SessionLocal() as db:assert db.scalar(select(VehiclePosition.status).where(VehiclePosition.vehicle_id==vid))=='handover'
    if delivered:
        h=approved_doc(c,source,'handover');source=action(c,source,'deliver',{'evidence_id':evidence(c,source,'signed_handover',h)})
        with SessionLocal() as db:assert db.scalar(select(VehiclePosition.status).where(VehiclePosition.vehicle_id==vid))=='exited'
    after=after_create(c,source,'vehicle_return' if delivered else 'sale_termination');after=confirmed(c,after_approve(c,plan(c,after,10000)))
    row=get(c,{'id':after['vehicle_return']['operation_case_id']})
    return source,after,row,loc

def test_delivered_customer_return_fail_rectify_pass_new_generation_preserves_hold(client):
    source,after,row,loc=returned_sale(client)
    login(client,'inventory');row=act(client,row,'intake',{'location_id':loc});assert row['status']=='quarantined'
    from tests.test_aftercare import cmd as after_cmd
    login(client,'admin');after_cmd(client,after,'apply',{'evidence_id':evidence(client,after,'receipt')},409)
    login(client,'service');row=act(client,row,'inspect',{'outcome':'fail','findings':'实测制动告警须整改'})
    login(client,'manager');act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'release'},409)
    row=act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'rectify'})
    login(client,'service');row=act(client,row,'inspect',{'outcome':'pass','findings':'整改后本次复检合格'})
    login(client,'manager');row=act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'release'})
    login(client,'inventory');row=act(client,row,'release',{'location_id':loc});assert row['status']=='accepted' and 'cost_cents' not in row
    with SessionLocal() as db:
        old=db.scalar(select(Vehicle).where(Vehicle.id==source['vehicle_id']));assert old.inventory_generation==1 and old.approval_state=='approved'
        new=db.scalar(select(Vehicle).where(Vehicle.id==row['received_vehicle_id']));assert new.inventory_generation==2 and new.purchase_cost_cents==old.purchase_cost_cents
        assert db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id'])).delivered is True
    from app.vehicle_backup_integrity import validate_vehicle_custody
    with sqlite3.connect(engine.url.database) as db:validate_vehicle_custody(db)
    login(client,'finance');after_cmd(client,after,'apply',{'evidence_id':evidence(client,after,'receipt')})

def test_dispatched_not_delivered_customer_return_uses_new_generation(client):
    source,after,row,loc=returned_sale(client,False)
    row=act(client,row,'intake',{'location_id':loc});row=act(client,row,'inspect',{'outcome':'pass','findings':'原车实退检查合格'})
    row=act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'release'});row=act(client,row,'release',{'location_id':loc})
    with SessionLocal() as db:
        assert db.scalar(select(Vehicle).where(Vehicle.id==source['vehicle_id'])).approval_state=='void'
        assert not db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id']))
        assert db.scalar(select(Vehicle).where(Vehicle.id==row['received_vehicle_id'])).inventory_generation==2
    from app.vehicle_backup_integrity import validate_vehicle_custody
    with sqlite3.connect(engine.url.database) as db:validate_vehicle_custody(db)

def test_customer_reject_actual_handover_and_cancel_before_intake(client):
    source,after,row,loc=returned_sale(client)
    from tests.test_aftercare import cmd as after_cmd
    row=act(client,row,'intake',{'location_id':loc})
    after_cmd(client,after,'cancel',{'reason':'实车已收不得删除'},409)
    row=act(client,row,'inspect',{'outcome':'fail','findings':'不符合双方约定退回条件'})
    row=act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'return_to_customer'})
    act(client,row,'release',{'location_id':loc},409)
    row=act(client,row,'return_customer');assert row['received_vehicle_id'] is None and row['entries']==[]
    after_cmd(client,after,'apply',{'evidence_id':evidence(client,after,'receipt')},409)
    after_cmd(client,after,'cancel',{'reason':'已实际交还原车，结束本次申请'})

def test_vehicle_master_location_facts_prevent_parent_change_disable(client):
    _,vid,loc=inventory(client)
    old=next(r for r in client.get('/api/masters/locations').json()['items'] if r['id']==loc);other=destination(client)
    target=next(r for r in client.get('/api/masters/locations').json()['items'] if r['id']==other)
    for changes in ({'active':False},{'warehouse_id':target['warehouse_id']}):
        r=client.put('/api/masters/locations/'+str(loc),json={'request_id':uuid.uuid4().hex,'version':old['version'],'values':{k:changes.get(k,old[k]) for k in ('code','name','active','warehouse_id')}})
        assert r.status_code==409,r.text

def test_legacy_unlocated_vehicle_requires_actual_location_and_approval(client):
    from tests.test_workflow import seed_car
    vid=seed_car();loc=destination(client)
    create(client,'other_out',vid,status=409)
    row=create(client,'locate',vid,loc);act(client,row,'locate',status=409)
    row=act(client,row,'approve');row=act(client,row,'locate')
    assert row['entries'][0]['kind']=='locate' and row['entries'][0]['inventory_delta']==0
    with SessionLocal() as db:assert db.scalar(select(VehiclePosition.location_id).where(VehiclePosition.vehicle_id==vid))==loc
    from app.vehicle_backup_integrity import validate_vehicle_custody
    with sqlite3.connect(engine.url.database) as db:validate_vehicle_custody(db)

def test_task_transfer_to_actual_technician_and_stale_inspection_refused(client):
    from tests.conftest import PASSWORD_HASH
    from app.models import UserStore
    source,after,row,loc=returned_sale(client)
    row=act(client,row,'intake',{'location_id':loc})
    with SessionLocal() as db:
        tech=User(username='vo-tech',display_name='合成实车检查技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(tech);db.flush();db.add(UserStore(user_id=tech.id,store_id=1,role='technician'));db.commit();tid=tech.id
        wrong=db.scalar(select(User.id).where(User.username=='finance'))
    task=row['tasks'][0]
    act(client,row,'reassign',{'task_id':task['id'],'assignee_id':wrong,'due_date':today().isoformat()},422)
    row=act(client,row,'reassign',{'task_id':task['id'],'assignee_id':tid,'due_date':today().isoformat()})
    login(client,'service');act(client,row,'inspect',{'outcome':'pass','findings':'非接手员工不能检查'},403)
    login(client,'vo-tech');row=act(client,row,'inspect',{'outcome':'pass','findings':'本人完整检查并记录合格'})
    assert 'cost_cents' not in row
    login(client,'manager');act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id']+100,'decision':'release'},409)

def test_cancel_customer_plan_before_receipt_releases_claim_without_stock(client):
    source,after,row,loc=returned_sale(client)
    from tests.test_aftercare import cmd as after_cmd
    after_cmd(client,after,'cancel',{'reason':'客户实车未送达，撤回本次协商'})
    now=get(client,row);assert now['status']=='cancelled' and not now['entries'] and not now['quarantine']
    with SessionLocal() as db:
        assert db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id'])).delivered
        assert db.scalar(select(func.count()).select_from(Vehicle))==1

def test_original_position_and_operation_facts_cannot_be_overwritten(client):
    import pytest
    _,vid,loc=inventory(client);row=create(client,'other_out',vid);row=act(client,row,'approve');row=act(client,row,'dispatch')
    with SessionLocal() as db:
        set_scope(db,[1],1);entry=db.scalar(select(VehiclePositionEntry).where(VehiclePositionEntry.operation_id==row['id']));entry.value_cents=-1
        with pytest.raises(HTTPException):db.flush()
        db.rollback()
        operation=db.scalar(select(VehicleOperation).where(VehicleOperation.id==row['id']));operation.cost_cents=1
        with pytest.raises(HTTPException):db.flush()

def test_admin_cannot_approve_own_request_or_dispose_own_inspection(client):
    _,vid,_=inventory(client);row=create(client,'other_out',vid)
    act(client,row,'approve',status=403)
    row=act(client,row,'cancel')
    from tests.test_workflow import order,action,approved_doc
    from tests.test_aftercare import create as ac_create,plan,approved as ac_approve,confirmed
    from tests.test_procurement import bank
    source=action(client,order(client,'100.00',model='虚构型号'),'approve');source=action(client,source,'allocate',{'vehicle_id':vid})
    sign=approved_doc(client,source,'contract');source=action(client,source,'sign',{'evidence_id':evidence(client,source,'signed_contract',sign)})
    source=action(client,source,'receive',{'amount':'100','account_id':bank(client),'reference':'实际合成车款','evidence_id':evidence(client,source,'receipt')})
    source=action(client,source,'inspect',{'outcome':'合格','result':'实际检查合格','evidence_id':evidence(client,source,'inspection')});source=action(client,source,'dispatch',{'evidence_id':evidence(client,source)})
    after=confirmed(client,ac_approve(client,plan(client,ac_create(client,source,'sale_termination'),10000)));row=get(client,{'id':after['vehicle_return']['operation_case_id']})
    loc=destination(client);row=act(client,row,'intake',{'location_id':loc});row=act(client,row,'inspect',{'outcome':'pass','findings':'管理员本人检查合格'})
    act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'release'},403)
