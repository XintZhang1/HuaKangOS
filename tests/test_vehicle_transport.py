"""Original registered routes, isolated synthetic cars, no company database."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import uuid
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db import SessionLocal, today
from app.models import User, UserStore, Vehicle, CashEntry
from app.flow_models import Task
from app.vehicle_transfer_models import VehicleMovement, VehicleTransfer, VehicleCustody
from app.vehicle_transport_models import (VehicleTransportException, VehicleTransportLoss, VehicleTransportLossSettlement,
    VehicleTransportFoundReceipt, VehicleTransportFoundSettlement, VehicleTransportObservation)
from app import vehicle_transport_service as service
from app.tenancy import set_scope, project_user
from tests.conftest import login, PASSWORD_HASH
from tests import test_vehicle_transfers as old

API='/api/vehicle-transport-exceptions'
COST=10000001


def seed():
    car, locations=old.seed()
    with SessionLocal() as db:
        reviewer=User(username='transport_manager2', display_name='另一店独立主管', role='manager', password_hash=PASSWORD_HASH, must_change_password=False)
        db.add(reviewer); db.flush(); db.add(UserStore(user_id=reviewer.id, store_id=2, role='manager')); db.commit()
    return car,locations


def as_user(client, name, sid):
    old.switch(client,sid);login(client,name)


def get(client, row):
    response=client.get(API+'/'+str(row['id']));assert response.status_code==200,response.text
    return response.json()


def evidence(client, row, financial=False):
    case=get(client,row)['case_id']
    response=client.post(f'/api/flow/cases/{case}/files',files={'file':('原VIN合成凭据.txt','仅用于独立测试的实物或财务凭据'.encode(),'text/plain')},data={'category':'receipt' if financial else 'evidence'})
    assert response.status_code==200,response.text
    return response.json()['id']


def act(client,row,action,values=None,status=200,financial=False,key=None,previous=None):
    current=previous or get(client,row)
    if values is None:values={'evidence_id':evidence(client,row,financial),'reason':'本人依据实际原车来源核对'}
    payload={'request_id':key or uuid.uuid4().hex,'version':current['version'],'case_version':current['case_version'],
        'exception_version':current['exception_version'],'values':values}
    response=client.post(API+f"/{row['id']}/actions/{action}",json=payload)
    assert response.status_code==status,response.text
    return response.json()


def start(client,kind='missing',leg='transit'):
    car,locations=seed();parent=old.approved(client,car)
    old.command(client,parent,'dispatch',old.proof_values(client,parent))
    if leg in {'rejected','return_transit'}:
        old.switch(client,2);old.command(client,parent,'reject',old.proof_values(client,parent))
        if leg=='return_transit':old.command(client,parent,'return_ship',old.proof_values(client,parent))
    as_user(client,'inventory',1);current=old.get(client,parent)
    response=client.post(API,json={'request_id':uuid.uuid4().hex,'transfer_id':parent['id'],'version':current['version'],
        'case_version':current['case_version'],'kind':kind,'evidence_id':old.upload(client,parent),'reason':'现场发现原VIN运输异常，需要双方核对'})
    assert response.status_code==201,response.text
    return parent,response.json(),car,locations


def observe(client,row,kind,vin=old.VIN,action='observe'):
    values={'confirmed':True,'vin':vin,'actual_at':datetime.now(timezone.utc).isoformat(),
        'evidence_id':evidence(client,row),'reason':'本人已按凭据核对原VIN实际情况'}
    if action=='observe':values['kind']=kind
    return act(client,row,action,values)


def observations(client,row,receiver='not_located'):
    returning=get(client,row)['origin_status']=='return_transit'
    for sid,kind in ((1,receiver if returning else 'dispatch_verified'),(2,'dispatch_verified' if returning else receiver)):
        as_user(client,'inventory',sid);observe(client,row,kind)
    as_user(client,'finance',1)
    return get(client,row)


def propose_loss(client,row,method='missing',target=4000001):
    as_user(client,'finance',1)
    return act(client,row,'plan_loss',{'source_bearer_cents':COST-target,'destination_bearer_cents':target,'loss_method':method,
        'evidence_id':evidence(client,row,True),'reason':'按原车原成本确认双方实际承担'})


def approve_both(client,row,financial=True):
    plan=get(client,row)['plans'][-1]['id']
    for sid,name in ((1,'manager'),(2,'transport_manager2')):
        as_user(client,name,sid)
        act(client,row,'approve',{'plan_id':plan,'evidence_id':evidence(client,row,financial),'reason':'独立核对本版原观察与双方安排'})
    return get(client,row)


def posted(client,leg='transit'):
    parent,row,car,locations=start(client,leg=leg)
    observations(client,row);propose_loss(client,row);approve_both(client,row)
    as_user(client,'finance',1)
    row=act(client,row,'post_loss',{'confirmed':True,'evidence_id':evidence(client,row,True),'reason':'依据双方批准实际确认本笔原在途损失'})
    return parent,row,car,locations


def found_plan(client,row,sid):
    as_user(client,'inventory',sid)
    observed=observe(client,row,None,action='observe_found')['observations'][-1]['id']
    as_user(client,'finance',1)
    act(client,row,'plan_found',{'found_observation_id':observed,'evidence_id':evidence(client,row,True),'reason':'按原VIN与原损失成本恢复实际接收安排'})
    return approve_both(client,row)


def test_loss_keeps_original_exit_and_no_double_stock_or_cash(client):
    parent,row,car,_=posted(client)
    assert row['status']=='posted' and row['loss']['value_cents']==COST
    assert old.get(client,parent)['status']=='lost'
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(VehicleMovement.quantity)))==-1
        assert db.scalar(select(func.sum(VehicleMovement.value_cents)))==-COST
        assert db.scalar(select(func.count()).select_from(Vehicle))==1
        assert db.scalar(select(func.count()).select_from(VehicleTransportLoss))==1
        assert db.scalar(select(func.sum(VehicleTransportLossSettlement.amount_cents)))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(Vehicle).where(Vehicle.id==car)).approval_state=='void'
    as_user(client,'inventory',2)
    old.command(client,parent,'accept',old.proof_values(client,parent,location_id=1),409)


@pytest.mark.parametrize('sid,net_amount',[(1,-4000001),(2,COST-4000001)])
def test_found_original_vin_receipt_generation_and_net_obligation(client,sid,net_amount):
    parent,row,car,locations=posted(client)
    found_plan(client,row,sid)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Vehicle))==1
        assert db.scalar(select(func.count()).select_from(VehicleTransportFoundReceipt))==0
    as_user(client,'inventory',sid)
    result=act(client,row,'found_receive',{'confirmed':True,'vin':old.VIN,'location_id':locations[sid],
        'evidence_id':evidence(client,row),'reason':'本人实际核对原VIN合格入库'})
    assert result['status']=='recovered' and result['found_received']
    assert old.get(client,parent)['status']=='recovered'
    with SessionLocal() as db:
        cars=list(db.scalars(select(Vehicle).order_by(Vehicle.id)))
        assert [(v.store_id,v.inventory_generation,v.approval_state,v.purchase_cost_cents) for v in cars]==[(1,0,'void',COST),(sid,1,'approved',COST)]
        settlements=list(db.scalars(select(VehicleTransportFoundSettlement)))
        assert {(s.store_id,s.amount_cents) for s in settlements}=={(1,net_amount),(2,-net_amount)}
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(func.sum(VehicleMovement.quantity)))==-1  # Found receipt is not a fake ordinary accept.
    as_user(client,'finance',1)
    row=get(client,row);assert row['loss_recorded'] and row['loss']['value_cents']==COST


@pytest.mark.parametrize('leg',['transit','rejected','return_transit'])
def test_each_physical_leg_remains_distinct(client,leg):
    parent,row,_,_=posted(client,leg)
    assert row['origin_status']==leg
    with SessionLocal() as db:
        expected={'dispatch'}|({'reject'} if leg!='transit' else set())|({'return_ship'} if leg=='return_transit' else set())
        assert set(db.scalars(select(VehicleMovement.kind)))==expected


def test_wrong_vin_never_receives_other_car_and_resolution_is_not_receipt(client):
    parent,row,_,locations=start(client,'vin_mismatch')
    observe(client,row,'dispatch_verified')
    as_user(client,'inventory',2);observe(client,row,'other_vin_seen','LHGCM82633A654321')
    as_user(client,'inventory',1);act(client,row,'plan_resume',status=409)
    as_user(client,'inventory',2);observe(client,row,'original_seen')
    as_user(client,'inventory',1);act(client,row,'plan_resume')
    approve_both(client,row,False)
    assert get(client,row)['status']=='resolved'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Vehicle))==1
        assert db.scalar(select(func.count()).select_from(VehicleTransportLoss))==0
    as_user(client,'inventory',2);old.command(client,parent,'accept',old.proof_values(client,parent,location_id=locations[2]))


def test_damaged_car_needs_actual_disposal_before_loss_and_cannot_be_found(client):
    parent,row,_,_=start(client,'damage')
    observations(client,row,'unusable_held');propose_loss(client,row,'destroyed');approve_both(client,row)
    as_user(client,'finance',1)
    act(client,row,'post_loss',{'confirmed':True,'evidence_id':evidence(client,row,True),'reason':'尚未实际销毁不得记损失'},409)
    as_user(client,'inventory',2)
    act(client,row,'dispose',{'confirmed':True,'vin':old.VIN,'evidence_id':evidence(client,row),'reason':'本人依据真实销毁凭据确认原车处置'})
    as_user(client,'finance',1)
    act(client,row,'post_loss',{'confirmed':True,'evidence_id':evidence(client,row,True),'reason':'原车实际处置完成后确认原损失'})
    as_user(client,'inventory',2)
    act(client,row,'observe_found',{'confirmed':True,'vin':old.VIN,'actual_at':datetime.now(timezone.utc).isoformat(),
        'evidence_id':evidence(client,row),'reason':'实际销毁原车不能假称重新找到'},409)


@pytest.mark.parametrize('confirmed',[False,1,'true',None])
def test_actual_confirmations_are_not_coerced(client,confirmed):
    _,row,_,_=start(client)
    act(client,row,'observe',{'confirmed':confirmed,'kind':'dispatch_verified','vin':old.VIN,
        'actual_at':datetime.now(timezone.utc).isoformat(),'evidence_id':evidence(client,row),'reason':'不能默认替员工确认实际发生'},422)


def test_active_investigation_blocks_ordinary_receipt_and_all_replays_are_original(client):
    parent,row,_,locations=start(client)
    as_user(client,'inventory',2)
    old.command(client,parent,'accept',old.proof_values(client,parent,location_id=locations[2]),409)
    before=get(client,row);key=uuid.uuid4().hex
    values={'kind':'not_located','vin':old.VIN,'confirmed':True,'actual_at':datetime.now(timezone.utc).isoformat(),
        'evidence_id':evidence(client,row),'reason':'本人仍未找到该原VIN'}
    result=act(client,row,'observe',values,key=key,previous=before)
    assert act(client,row,'observe',values,key=key,previous=before)==result
    act(client,row,'observe',values,409,previous=before)
    act(client,row,'observe',{**values,'reason':'相同编号不允许改内容'},409,key=key,previous=before)


def test_independent_review_same_person_cannot_approve_both_stores(client):
    _,row,_,_=start(client);observations(client,row);propose_loss(client,row)
    plan=get(client,row)['plans'][-1]['id']
    as_user(client,'manager',1)
    act(client,row,'approve',{'plan_id':plan,'evidence_id':evidence(client,row,True),'reason':'原店独立复核批准本版'})
    as_user(client,'manager',2)
    act(client,row,'approve',{'plan_id':plan,'evidence_id':evidence(client,row,True),'reason':'同一个人不能替另一门店再批准'},403)


def test_only_original_store_and_role_can_see_evidence_or_write(client):
    _,row,_,_=start(client)
    source_evidence=evidence(client,row)
    as_user(client,'inventory',2)
    act(client,row,'observe',{'kind':'not_located','vin':old.VIN,'confirmed':True,'actual_at':datetime.now(timezone.utc).isoformat(),
        'evidence_id':source_evidence,'reason':'不得借用另一店原凭据'},422)
    as_user(client,'finance',2)
    act(client,row,'observe',{'kind':'not_located','vin':old.VIN,'confirmed':True,'actual_at':datetime.now(timezone.utc).isoformat(),
        'evidence_id':source_evidence,'reason':'财务不得替实车岗位确认'},403)
    as_user(client,'admin',3);assert client.get(API+'/'+str(row['id'])).status_code==404
    as_user(client,'admin','all');assert client.get(API+'/'+str(row['id'])).status_code==409
    as_user(client,'sales',1);assert client.get(API+'/'+str(row['id'])).status_code==403


def verify_transport(losses=1,found=0):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.vehicle_transport_integrity import validate_vehicle_transport
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        result=validate_vehicle_transport(db)
        assert result['verified_vehicle_transport_losses']==losses
        assert result['verified_vehicle_transport_found']==found
        assert validate_sqlite(db)['integrity']=='ok'


@pytest.mark.parametrize('sid',[1,2])
def test_full_restore_replays_loss_and_same_original_found_receipt(client,sid):
    _,row,_,locations=posted(client);verify_transport()
    found_plan(client,row,sid);verify_transport()
    as_user(client,'inventory',sid)
    act(client,row,'found_receive',{'confirmed':True,'vin':old.VIN,'location_id':locations[sid],
        'evidence_id':evidence(client,row),'reason':'本人确认找到同一原车并实际恢复原成本入库'})
    verify_transport(found=1)


@pytest.mark.parametrize('kind',['missing_again','not_usable'])
def test_found_plan_cannot_reuse_car_which_is_no_longer_available(client,kind):
    _,row,_,locations=posted(client);found_plan(client,row,2)
    as_user(client,'inventory',2)
    act(client,row,'found_unavailable',{'confirmed':True,'vin':old.VIN,'kind':kind,
        'evidence_id':evidence(client,row),'reason':'原在场记录后实车已经无法按本版接收，保留原损失'})
    verify_transport()
    as_user(client,'finance',1)
    act(client,row,'plan_found',{'found_observation_id':get(client,row)['observations'][-1]['id'],
        'evidence_id':evidence(client,row,True),'reason':'不得复用已经失效的原在场记录'},409)
    found_plan(client,row,1)
    as_user(client,'inventory',1)
    act(client,row,'found_receive',{'confirmed':True,'vin':old.VIN,'location_id':locations[1],
        'evidence_id':evidence(client,row),'reason':'本人后来重新找到原车并实际恢复原成本入库'})
    verify_transport(found=1)
