import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db import SessionLocal, today
from app.models import Vehicle, Store, User, UserStore, CashEntry
from app.flow_models import Case, VehicleHold, Task
from app.master_models import Warehouse, StorageLocation
from app.vehicle_transfer_models import VehicleCustody, VehicleTransfer, VehicleMovement, VehicleTransferSettlement
from app import vehicle_transfer_service as svc
from app.tenancy import set_scope, project_user
from .conftest import login

VIN='LHGCM82633A123456'


def seed():
    with SessionLocal() as db:
        db.add_all([Store(id=2,code='VSECOND',name='调入店'),Store(id=3,code='VTHIRD',name='无关门店')]);db.flush()
        for user in db.scalars(select(User)):
            db.add(UserStore(user_id=user.id,store_id=2,role=user.role if user.role!='admin' else None))
        uid=db.scalar(select(User.id).where(User.username=='inventory'))
        car=Vehicle(vin=VIN,brand='测试品牌',model='测试车型',color='白',supplier='测试供应方',purchase_cost_cents=10000001,list_price_cents=12000000,
            store_id=1,doc_no='CAR-1',business_date=today(),approval_state='approved',created_by=uid)
        db.add(car);locations={}
        for sid in (1,2,3):
            warehouse=Warehouse(store_id=sid,code='CARS',name='整车仓',warehouse_type='vehicles');db.add(warehouse);db.flush()
            loc=StorageLocation(store_id=sid,code='L1',name='A区',warehouse_id=warehouse.id);db.add(loc);db.flush();locations[sid]=loc.id
        db.commit();return car.id,locations


def switch(client,sid):client.headers['X-Store-ID']=str(sid)
def get(client,row):
    r=client.get('/api/vehicle-transfers/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def create(client,car,status=201):
    r=client.post('/api/vehicle-transfers',json={'request_id':uuid.uuid4().hex,'vehicle_id':car,'destination_store_id':2,'due_date':today().isoformat(),'reason':'调剂门店整车库存'})
    assert r.status_code==status,r.text;return r.json()
def command(client,row,action,values=None,status=200,key=None,original=None):
    latest=original or get(client,row)
    r=client.post(f"/api/vehicle-transfers/{row['id']}/actions/{action}",json={'request_id':key or uuid.uuid4().hex,'version':latest['version'],
        'case_version':latest['case_version'],'values':values or {'reason':'本店核对确认'}})
    assert r.status_code==status,r.text;return r.json()
def upload(client,row):
    case=get(client,row)['case_id'];r=client.post(f'/api/flow/cases/{case}/files',files={'file':('VIN核对.txt','模拟交接凭据'.encode(),'text/plain')},data={'category':'evidence'})
    assert r.status_code==200,r.text;return r.json()['id']
def approved(client,car):
    login(client,'inventory');row=create(client,car);login(client,'manager');command(client,row,'approve');switch(client,2);command(client,row,'approve')
    switch(client,1);login(client,'inventory');return row
def proof_values(client,row,**more):return {'evidence_id':upload(client,row),'vin':VIN,'reason':'按现场实车核对',**more}


def test_vehicle_transfer_receive_preserves_store_history_and_value(client):
    car,loc=seed();row=approved(client,car)
    command(client,row,'dispatch',proof_values(client,row))
    with SessionLocal() as db:assert db.scalar(select(Vehicle).where(Vehicle.id==car)).approval_state=='void'
    switch(client,2);final=command(client,row,'accept',proof_values(client,row,location_id=loc[2]));assert final['status']=='accepted'
    with SessionLocal() as db:
        vehicles=list(db.scalars(select(Vehicle).order_by(Vehicle.id)));assert len(vehicles)==2
        assert vehicles[0].store_id==1 and vehicles[1].store_id==2 and vehicles[0].vin==vehicles[1].vin
        assert vehicles[1].approval_state=='approved' and vehicles[1].inventory_generation==1
        assert vehicles[1].purchase_cost_cents==10000001 and vehicles[0].id==car
        assert db.scalar(select(func.sum(VehicleMovement.quantity)))==0
        assert db.scalar(select(func.sum(VehicleMovement.value_cents)))==0
        assert db.scalar(select(func.sum(VehicleTransferSettlement.amount_cents)))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.approval_state=='approved'))==1
    available=client.get('/api/flow/lookup/vehicle').json();assert len(available['items'])==1


def test_vehicle_reject_requires_physical_return_and_creates_new_local_receipt(client):
    car,loc=seed();row=approved(client,car);command(client,row,'dispatch',proof_values(client,row))
    switch(client,2);command(client,row,'reject',proof_values(client,row));command(client,row,'cancel',status=403)
    command(client,row,'return_ship',proof_values(client,row))
    switch(client,1);final=command(client,row,'return_receive',proof_values(client,row,location_id=loc[1]));assert final['status']=='returned'
    with SessionLocal() as db:
        cars=list(db.scalars(select(Vehicle)));assert len(cars)==2 and all(v.store_id==1 for v in cars)
        assert sum(v.approval_state=='approved' for v in cars)==1
        assert db.scalar(select(func.sum(VehicleMovement.value_cents)))==0
        assert db.scalar(select(func.count()).select_from(VehicleTransferSettlement))==0


def test_vehicle_transfer_guards_scopes_vin_locations_and_evidence(client):
    car,loc=seed();login(client,'sales');create(client,car,403)
    row=approved(client,car);source_proof=upload(client,row)
    command(client,row,'dispatch',{'vin':'LHGCM82633A999999','evidence_id':source_proof,'reason':'VIN错车不得发出'},409)
    login(client,'admin');switch(client,3);assert client.get(f"/api/vehicle-transfers/{row['id']}").status_code==404
    switch(client,1);login(client,'finance');command(client,row,'dispatch',{'vin':VIN,'evidence_id':source_proof,'reason':'财务不得确认实物'},403)
    login(client,'inventory');command(client,row,'dispatch',{'vin':VIN,'evidence_id':source_proof,'reason':'已核对VIN发出'})
    switch(client,2);command(client,row,'accept',{'vin':VIN,'evidence_id':source_proof,'reason':'不能借用别店凭据','location_id':loc[2]},422)
    command(client,row,'accept',proof_values(client,row,location_id=loc[1]),422)
    login(client,'admin');switch(client,'all');assert client.get('/api/vehicle-transfers').status_code==409


def test_pending_transfer_blocks_allocation_duplicate_transfer_and_cancel_releases(client):
    car,_=seed();login(client,'inventory');row=create(client,car)
    create(client,car,409);assert client.get('/api/flow/lookup/vehicle').json()['items']==[]
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='inventory'));vehicle=db.scalar(select(Vehicle).where(Vehicle.id==car))
        with pytest.raises(HTTPException) as error:svc.assert_vehicle_available(db,user,vehicle)
        assert error.value.status_code==409
    command(client,row,'cancel');assert len(client.get('/api/flow/lookup/vehicle').json()['items'])==1
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='inventory'));svc.assert_vehicle_available(db,user,db.scalar(select(Vehicle).where(Vehicle.id==car)));db.commit()


def test_duplicate_stale_and_concurrent_receivers_never_double_stock(client):
    car,loc=seed();row=approved(client,car);before=get(client,row);key=uuid.uuid4().hex;values=proof_values(client,row)
    first=command(client,row,'dispatch',values,key=key,original=before)
    assert command(client,row,'dispatch',values,key=key,original=before)==first
    command(client,row,'dispatch',values,status=409,original=before)
    switch(client,2);values=proof_values(client,row,location_id=loc[2]);latest=get(client,row)
    def receive(_):
        with SessionLocal() as db:
            set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='inventory')),'inventory')
            try:svc.command(db,user,row['id'],uuid.uuid4().hex,latest['version'],latest['case_version'],'accept',values);return 200
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(receive,range(2)))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.store_id==2))==1
        assert db.scalar(select(func.count()).select_from(VehicleMovement).where(VehicleMovement.kind=='accept'))==1


def test_vehicle_records_cannot_rewrite_generation_or_post_history(client):
    car,loc=seed();row=approved(client,car);command(client,row,'dispatch',proof_values(client,row))
    with SessionLocal() as db:
        vehicle=db.scalar(select(Vehicle).where(Vehicle.id==car));vehicle.inventory_generation=12
        with pytest.raises(HTTPException):db.commit()
        db.rollback();move=db.scalar(select(VehicleMovement));move.value_cents=0
        with pytest.raises(HTTPException):db.commit()
        db.rollback()
        with pytest.raises(HTTPException):db.scalar(select(VehicleCustody))


def test_actual_order_allocate_refuses_pending_transfer_then_succeeds_after_cancel(client):
    from tests.test_workflow import order,action
    car,_=seed();login(client,'inventory');row=create(client,car)
    login(client,'admin');sale=action(client,order(client),'approve')
    refused=action(client,sale,'allocate',{'vehicle_id':car},409);assert '调拨' in refused['detail']
    command(client,row,'cancel');sale=action(client,sale,'allocate',{'vehicle_id':car})
    assert sale['vehicle_id']==car
    create(client,car,409)


def test_vehicle_report_table_csv_reconciles_in_transit_and_paired_receipt(client):
    car,loc=seed();row=approved(client,car);command(client,row,'dispatch',proof_values(client,row))
    login(client,'manager');data=client.get('/api/flow/analytics').json()
    chart=next(c for c in data['charts'] if c['id']=='vehicle_transit')
    assert sum(chart['series'][0]['values'])==10000001==sum(r['amount_cents'] for r in data['tables']['vehicle_transit']['rows'])
    csv=client.get('/api/flow/analytics/export?dataset=vehicle_transit');assert csv.status_code==200 and VIN in csv.text and '100000.01' in csv.text
    switch(client,2);login(client,'inventory');command(client,row,'accept',proof_values(client,row,location_id=loc[2]))
    login(client,'admin');switch(client,'all');data=client.get('/api/flow/analytics').json()
    assert data['metrics']['vehicle_in_transit_cents']==0 and data['metrics']['interstore_vehicle_net_cents']==0
    assert data['metrics']['inventory_cost_cents']==10000001 and data['metrics']['inventory_count']==1


def test_vehicle_restore_checks_reject_lost_or_wrong_custody_and_wrong_value(client):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.backup_integrity import validate_sqlite
    car,loc=seed();row=approved(client,car);command(client,row,'dispatch',proof_values(client,row))
    switch(client,2);command(client,row,'accept',proof_values(client,row,location_id=loc[2]))
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_vehicle_transfers']==1
        restored.execute('UPDATE vehicle_transfer_settlements SET amount_cents=999 WHERE store_id=1')
        with pytest.raises(ValueError,match='往来不配对'):validate_sqlite(restored)
        restored.rollback();restored.execute('UPDATE vehicle_custodies SET current_vehicle_id=NULL,current_store_id=NULL')
        with pytest.raises(ValueError,match='在途车辆'):validate_sqlite(restored)
