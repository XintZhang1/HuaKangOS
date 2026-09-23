"""Care workflow, source-based reminders and explicit, revocable vehicle history."""
from datetime import timedelta
import uuid
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,today
from app.models import User,UserStore,Store,Vehicle
from app.flow_models import Customer,Case,Task,FileAsset
from app.customer_service_models import CustomerVehicle,VehicleObservation,CareCase,CareRecord,ReminderRule,HistoryGrant,CareReceipt
from app.tenancy import set_scope
from tests.conftest import login,PASSWORD_HASH
from tests.test_multistore import second_store,switch

API='/api/customer-service'
VIN='LFV2A21K9J1234567'


def user_id(role='admin',store=1):
    with SessionLocal() as db:
        row=db.scalar(select(User).where(User.username==role))
        if not row:
            row=User(username=role,display_name='合成'+role,role=role,password_hash=PASSWORD_HASH,must_change_password=False)
            db.add(row);db.flush()
        if not db.scalar(select(UserStore).where(UserStore.user_id==row.id,UserStore.store_id==store)):
            db.add(UserStore(user_id=row.id,store_id=store))
        db.commit();return row.id


def customer(name='虚构客户',phone='',owner='admin',store=1,contact=True):
    owner_id=user_id(owner,store)
    with SessionLocal() as db:
        row=Customer(store_id=store,name=name,phone=phone,owner_id=owner_id,contact_allowed=contact)
        db.add(row);db.commit();return row.id


def post(c,path,values=None,version=None,key=None,status=200,method='post'):
    payload={'request_id':key or uuid.uuid4().hex}
    if values is not None:payload['values']=values
    if version is not None:payload['version']=version
    r=getattr(c,method)(API+path,json=payload)
    assert r.status_code==status,r.text
    return r.json()


def vehicle(c,customer_id=None,**changes):
    return post(c,'/vehicles',{'customer_id':customer_id or customer(),'vin':VIN,'plate':'合成A1234','model_name':'虚构车型',
        'source_reference':'人工核对登记凭据-001','confirmed':True,**changes},status=201)['vehicle']


def observe(c,row,kind='odometer',when=None,km=1000,until=None,key=None,status=200):
    return post(c,f'/vehicles/{row["id"]}/observations',{'kind':kind,'observed_date':(when or today()).isoformat(),
        'odometer_km':km,'valid_until':until.isoformat() if until else None,'source_reference':'合成日期里程凭据-001','confirmed':True},row['version'],key,status)


def care(c,customer_id,vehicle_id=None,subtype='consultation',assignee='admin',**changes):
    return post(c,'/cases',{'customer_id':customer_id,'vehicle_id':vehicle_id,'subtype':subtype,'topic':'合成客户诉求',
        'description':'客户提供的合成情况，供办理验证','due_date':today().isoformat(),'assignee_id':user_id(assignee),**changes},status=201)['case']


def action(c,row,key,values=None,status=200,request_id=None):
    return post(c,f'/cases/{row["id"]}/actions/{key}',values or {},row['version'],request_id,status)


def rule(c,kind='maintenance',assignee='service',**changes):
    return post(c,'/reminders/rules',{'name':'合成'+kind+'规则','kind':kind,'interval_days':30 if kind in {'maintenance','first_service'} else 0,
        'interval_km':5000 if kind in {'maintenance','first_service'} else 0,'lead_days':3,'lead_km':100 if kind in {'maintenance','first_service'} else 0,
        'assignee_id':user_id(assignee),'active':True,**changes},status=201)['rule']


def test_customer_vehicle_does_not_merge_phone_or_change_inventory(client):
    one=vehicle(client,customer(phone='13900001111'))
    two=vehicle(client,customer(phone='13900001111'))
    three=vehicle(client,customer(phone=''))
    assert one['vehicle_identity_id']==two['vehicle_identity_id']==three['vehicle_identity_id']
    assert len({one['customer_identity_id'],two['customer_identity_id'],three['customer_identity_id']})==3
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Vehicle))==0
    post(client,'/vehicles',{'customer_id':one['customer_id'],'vin':VIN,'model_name':'虚构车型','source_reference':'再次误建关系','confirmed':True},status=409)


def test_observation_source_atomic_duplicate_stale_and_no_rollback(client):
    row=vehicle(client);key=uuid.uuid4().hex
    response=observe(client,row,kind='delivery',when=today()-timedelta(days=90),km=10,key=key)
    assert observe(client,row,kind='delivery',when=today()-timedelta(days=90),km=10,key=key)==response
    observe(client,row,km=100,status=409)
    row=response['vehicle'];row=observe(client,row,km=10000)['vehicle']
    observe(client,row,when=today()-timedelta(days=1),km=10001,status=409)
    observe(client,row,km=9999,status=409)
    observe(client,row,when=today()+timedelta(days=1),km=10001,status=422)
    with SessionLocal() as db:
        obs=db.scalar(select(VehicleObservation));obs.odometer_km=0
        with pytest.raises(HTTPException):db.commit()
    assert len(client.get(API+f'/vehicles/{row["id"]}').json()['observations'])==2


@pytest.mark.parametrize('subtype',['questionnaire','consultation','complaint','rescue'])
def test_employee_care_happy_duplicate_cancel_refusal_and_stale(client,subtype):
    cid=customer(owner='customer_service');vid=vehicle(client,cid)['id']
    login(client,'customer_service')
    row=care(client,cid,vid,subtype,'customer_service',**({'location':'客户报告：合成停车区三号位'} if subtype=='rescue' else {}))
    key=uuid.uuid4().hex;started=action(client,row,'start',request_id=key)['case']
    assert action(client,row,'start',request_id=key)['case']==started
    action(client,row,'cancel',{'reason':'过期版本不能取消'},status=409)
    response=action(client,started,'followup',{'channel':'in_person','contact_result':'contacted','note':'客户当面确认已提供处理建议'})['case']
    if subtype=='questionnaire':
        action(client,response,'close',{'result':'resolved','note':'缺少问卷回答不能结案'},status=422)
    close={'result':'resolved','note':'客户当面确认问题已解决'}
    if subtype=='questionnaire':close.update(satisfaction=4,recommend=True)
    done=action(client,response,'close',close)['case'];assert done['state']=='completed'
    action(client,done,'start',status=409)
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.case_id==done['id']));assert task.status=='done'
        assert db.scalar(select(func.count()).select_from(CareRecord).where(CareRecord.case_id==done['id']))==4


def test_care_required_rescue_callback_source_and_consent(client):
    cid=customer(contact=False)
    post(client,'/cases',{'customer_id':cid,'subtype':'rescue','topic':'错误救援','description':'未提供地点','due_date':today().isoformat(),'assignee_id':user_id()},status=422)
    post(client,'/cases',{'customer_id':cid,'subtype':'sales_callback','topic':'错误回访','description':'没有已交付原单','due_date':today().isoformat(),'assignee_id':user_id()},status=422)
    row=action(client,care(client,cid),'start')['case']
    action(client,row,'followup',{'channel':'phone','contact_result':'contacted','note':'未授权不能电话跟进'},status=409)
    cancelled=action(client,row,'cancel',{'reason':'客户撤回本次诉求'})['case'];assert cancelled['state']=='cancelled'


@pytest.mark.parametrize('subtype,kind,state',[('sales_callback','order','delivered'),('repair_callback','repair','completed')])
def test_callbacks_require_matching_finished_original(client,subtype,kind,state):
    cid=customer()
    with SessionLocal() as db:
        row=Case(kind=kind,state=state,flow_version=2,number=uuid.uuid4().hex,title='合成已交付原单',owner_id=user_id(),created_by=user_id(),customer_id=cid,business_date=today(),data={})
        db.add(row);db.commit();source_id=row.id
    callback=care(client,cid,subtype=subtype,source_case_id=source_id)
    assert callback['source_case_id']==source_id
    other=customer(name='另一客户')
    post(client,'/cases',{'customer_id':other,'subtype':subtype,'topic':'拒绝串单','description':'客户不匹配','due_date':today().isoformat(),'assignee_id':user_id(),'source_case_id':source_id},status=422)


def test_store_roles_owner_visibility_handoff_and_aggregate(client):
    cid=customer(owner='sales');vid=vehicle(client,cid)
    user_id('reception');user_id('customer_service')
    login(client,'sales');row=care(client,cid,vid['id'],assignee='sales')
    login(client,'reception');assert client.get(API+f'/cases/{row["id"]}').status_code==404
    assert client.get(API+f'/vehicles/{vid["id"]}').status_code==404
    login(client,'manager')
    with SessionLocal() as db:
        case=db.scalar(select(Case).where(Case.id==row['id']));case.due_date=today()-timedelta(days=2);db.commit()
    row=client.get(API+f'/cases/{row["id"]}').json();assert row['overdue']
    row=action(client,row,'handoff',{'assignee_id':user_id('customer_service'),'due_date':today().isoformat(),'reason':'逾期后由客服接手处理'})['case']
    assert row['records'][-1]['details']['was_overdue']
    login(client,'sales');action(client,row,'start',status=409)
    login(client,'customer_service');row=action(client,row,'start')['case']
    login(client,'admin');two=second_store(client);switch(client,two)
    assert client.get(API+f'/cases/{row["id"]}').status_code==404
    assert client.get(API+f'/vehicles/{vid["id"]}').status_code==404
    switch(client,'all');assert not client.get(API+'/catalog').json()['can_read']
    post(client,'/reminders/generate',status=409)


@pytest.mark.parametrize('role',['finance','inventory','technician'])
def test_non_customer_roles_cannot_read_direct_care_or_generic_case(client,role):
    cid=customer();row=care(client,cid);user_id(role);login(client,role)
    assert client.get(API+'/vehicles').status_code==403
    assert client.get(API+f'/cases/{row["id"]}').status_code==403
    assert client.get('/api/flow/cases/'+str(row['id'])).status_code==404


def test_date_and_mileage_rules_generate_once_and_cancel_does_not_recreate(client):
    cid=customer();row=vehicle(client,cid)
    row=observe(client,row,'delivery',today()-timedelta(days=10),100)['vehicle']
    rule(client,'first_service',interval_days=90,interval_km=5000)
    rule(client,'maintenance',interval_days=30,interval_km=10000)
    assert post(client,'/reminders/generate')['created']==[]
    row=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    row=observe(client,row,km=5100)['vehicle']
    response=post(client,'/reminders/generate');assert len(response['created'])==1 and response['created'][0]['subtype']=='first_service'
    assert post(client,'/reminders/generate')['created']==[]
    case=client.get(API+'/cases/'+str(response['created'][0]['case_id'])).json()
    action(client,case,'cancel',{'reason':'客户暂不需要本次提醒'})
    assert post(client,'/reminders/generate')['created']==[]
    row=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    row=observe(client,row,'first_service',km=5100)['vehicle']
    assert post(client,'/reminders/generate')['created']==[]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CareCase))==1


def test_renewal_and_warranty_tasks_need_recorded_dates_and_new_policy_for_close(client):
    cid=customer();row=vehicle(client,cid);rule(client,'renewal');rule(client,'warranty')
    assert post(client,'/reminders/generate')['created']==[]
    row=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    row=observe(client,row,'insurance',km=100,until=today()+timedelta(days=2))['vehicle']
    row=observe(client,row,'warranty',km=100,until=today()+timedelta(days=2))['vehicle']
    created=post(client,'/reminders/generate')['created'];assert {r['subtype'] for r in created}=={'renewal','warranty'}
    row=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    # A second proof of the same policy period must not create another renewal.
    row=post(client,f'/vehicles/{row["id"]}/observations',{'kind':'insurance','observed_date':today().isoformat(),'odometer_km':100,'valid_until':(today()+timedelta(days=2)).isoformat(),'source_reference':'同一期保险另一份核验依据','confirmed':True},row['version'])['vehicle']
    assert post(client,'/reminders/generate')['created']==[]
    renewal=client.get(API+'/cases/'+str(next(r['case_id'] for r in created if r['subtype']=='renewal'))).json()
    renewal=action(client,renewal,'start')['case']
    action(client,renewal,'close',{'result':'renewed','note':'没有新保险凭据不能结案'},status=409)
    row=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    row=observe(client,row,'insurance',km=100,until=today()+timedelta(days=365))['vehicle']
    done=action(client,renewal,'close',{'result':'renewed','note':'已按客户保单核对新保险期限'})['case'];assert done['state']=='completed'
    row=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    observe(client,row,'insurance',km=100,until=today()+timedelta(days=364),status=409)


def test_reminder_tick_does_not_repeat_unmodified_data_or_external_side_effects(client):
    row=vehicle(client);row=observe(client,row,'delivery',today()-timedelta(days=40),100)['vehicle'];rule(client)
    from app.customer_service import tick_reminders
    first=tick_reminders();assert first['created']==1
    with SessionLocal() as db:
        count=db.scalar(select(func.count()).select_from(CareReceipt))
        care=db.scalar(select(CareCase));assert care.generation_mode=='rule_worker' and care.rule_approved_by==user_id()
        record=db.scalar(select(CareRecord));assert record.details['automatic'] and '不代表员工点击' in record.note
    second=tick_reminders();assert second['created']==0
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CareReceipt))==count


def history_fixture(client):
    cid=customer(phone='');a=vehicle(client,cid)
    case=care(client,cid,a['id']);case=action(client,case,'start')['case'];case=action(client,case,'close',{'result':'resolved','note':'合成客户确认检查建议已解释'})['case']
    post(client,f'/vehicles/{a["id"]}/history-links',{'case_id':case['id'],'summary':'已检查门锁并说明使用方法','source_reference':'客户确认服务记录','confirmed':True},status=201)
    two=second_store(client);switch(client,two)
    b=vehicle(client,customer(phone='',store=two),customer_identity_id=a['customer_identity_id'])
    return a,b,two,case


def test_shared_vin_does_not_grant_history_and_explicit_pair_grant_is_revocable(client):
    a,b,two,case=history_fixture(client)
    assert client.get(API+f'/vehicles/{b["id"]}/history').json()['items']==[]
    assert client.get('/api/flow/cases/'+str(case['id'])).status_code==404
    switch(client,1)
    grant_values={'from_vehicle_id':a['id'],'to_store_id':two,'to_vehicle_id':b['id'],'valid_until':today().isoformat(),'source_reference':'客户确认跨店仅共享服务摘要','confirmed':True}
    key=uuid.uuid4().hex;grant=post(client,'/history/grants',grant_values,key=key,status=201)['grant']
    assert post(client,'/history/grants',grant_values,key=key,status=201)['grant']==grant
    post(client,'/history/grants',grant_values,status=409)
    switch(client,two);history=client.get(API+f'/vehicles/{b["id"]}/history').json()['items']
    assert len(history)==1 and history[0]['summary']=='已检查门锁并说明使用方法'
    assert not {'case_id','customer_phone','files','amount_cents','data'} & history[0].keys()
    assert client.get('/api/flow/cases/'+str(case['id'])).status_code==404
    switch(client,1);post(client,f'/history/grants/{grant["id"]}/revoke',{'reason':'客户撤回跨店服务历史授权'},grant['version'])
    switch(client,two);assert client.get(API+f'/vehicles/{b["id"]}/history').json()['items']==[]


def test_grant_rejects_same_vehicle_for_different_person_and_third_store(client):
    a,b,two,case=history_fixture(client)
    other=vehicle(client,customer(name='另一人',store=two))
    switch(client,1)
    post(client,'/history/grants',{'from_vehicle_id':a['id'],'to_store_id':two,'to_vehicle_id':other['id'],'valid_until':today().isoformat(),'source_reference':'错误客户授权拒绝','confirmed':True},status=422)
    grant=post(client,'/history/grants',{'from_vehicle_id':a['id'],'to_store_id':two,'to_vehicle_id':b['id'],'valid_until':today().isoformat(),'source_reference':'仅本客户车辆服务摘要','confirmed':True},status=201)['grant']
    third=client.post('/api/stores',json={'code':'THIRD','name':'第三合成店','active':True}).json()['id'];switch(client,third)
    assert client.get(API+'/history/grants').json()['items']==[]
    post(client,f'/history/grants/{grant["id"]}/revoke',{'reason':'第三店不能撤销'},grant['version'],status=404)


@pytest.mark.parametrize('disable_source',[True,False])
def test_inactive_vehicle_relation_suspends_granted_history(client,disable_source):
    a,b,two,case=history_fixture(client);switch(client,1)
    post(client,'/history/grants',{'from_vehicle_id':a['id'],'to_store_id':two,'to_vehicle_id':b['id'],'valid_until':today().isoformat(),'source_reference':'仅启用车辆关系下的服务摘要','confirmed':True},status=201)
    switch(client,two)
    assert len(client.get(API+f'/vehicles/{b["id"]}/history').json()['items'])==1
    row=a if disable_source else b;switch(client,1 if disable_source else two)
    current=client.get(API+f'/vehicles/{row["id"]}').json()['vehicle']
    post(client,f'/vehicles/{row["id"]}',{'plate':current['plate'],'model_name':current['model_name'],'active':False,'reason':'客户车辆关系已结束'},current['version'],method='put')
    switch(client,two)
    assert client.get(API+f'/vehicles/{b["id"]}/history').json()['items']==[]


def test_rule_stale_invalid_assignee_and_failed_command_rolls_back(client,monkeypatch):
    r=rule(client)
    values={k:r[k] for k in ('name','kind','interval_days','interval_km','lead_days','lead_km','assignee_id','active')}
    saved=post(client,f'/reminders/rules/{r["id"]}',values|{'name':'更新规则名称'},r['version'],method='put')['rule']
    post(client,f'/reminders/rules/{r["id"]}',values,r['version'],status=409,method='put')
    post(client,f'/reminders/rules/{r["id"]}',values|{'assignee_id':user_id('finance')},saved['version'],status=422,method='put')
    from app import customer_service as svc
    original=svc._record
    def fail(*args,**kwargs):original(*args,**kwargs);raise HTTPException(409,'合成事务故障')
    monkeypatch.setattr(svc,'_record',fail)
    post(client,'/cases',{'customer_id':customer(),'subtype':'consultation','topic':'整次回滚','description':'验证半单不会保存','due_date':today().isoformat(),'assignee_id':user_id()},status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CareCase))==0
        assert db.scalar(select(func.count()).select_from(Task))==0


def test_expired_history_authorization_and_financial_file_route_remain_closed(client,monkeypatch):
    a,b,two,case=history_fixture(client);switch(client,1)
    uploaded=client.post('/api/flow/cases/'+str(case['id'])+'/files',files={'file':('合成服务凭据.txt','合成文件，不包含真实资料'.encode(),'text/plain')},data={'category':'evidence'})
    assert uploaded.status_code==200,uploaded.text
    file_id=uploaded.json()['id']
    grant=post(client,'/history/grants',{'from_vehicle_id':a['id'],'to_store_id':two,'to_vehicle_id':b['id'],'valid_until':today().isoformat(),'source_reference':'仅今日服务摘要授权','confirmed':True},status=201)['grant']
    switch(client,two)
    assert client.get('/api/flow/files/'+str(file_id)).status_code==404
    assert len(client.get(API+f'/vehicles/{b["id"]}/history').json()['items'])==1
    from app import customer_service as svc
    tomorrow=today()+timedelta(days=1);monkeypatch.setattr(svc,'today',lambda:tomorrow)
    assert client.get(API+f'/vehicles/{b["id"]}/history').json()['items']==[]
    post(client,f'/history/grants/{grant["id"]}/revoke',{'reason':'过期后撤回授权'},grant['version'])
    post(client,f'/history/grants/{grant["id"]}/revoke',{'reason':'旧版本拒绝重复撤销'},grant['version'],status=409)


def test_competing_reminder_generations_leave_one_task(client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    row=vehicle(client);observe(client,row,'delivery',today()-timedelta(days=90),100);rule(client)
    def run(_):
        with TestClient(app) as worker:
            worker.cookies.update(client.cookies);worker.headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
            return worker.post(API+'/reminders/generate',json={'request_id':uuid.uuid4().hex}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(run,[1,2]))
    assert all(code in {200,409} for code in codes)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CareCase))==1
        assert db.scalar(select(func.count()).select_from(Task))==1


def test_care_migration_frozen_columns_constraints_and_foreign_keys(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect,text
    from app.db import Base
    cfg=Config('alembic.ini');cfg.attributes['url_override']='sqlite:///'+(tmp_path/'synthetic-care.sqlite').as_posix()
    command.upgrade(cfg,'l612_customer_service')
    engine=create_engine(cfg.attributes['url_override'])
    try:
        inspector=inspect(engine)
        for name,table in Base.metadata.tables.items():
            if name.startswith('care_') and not name.startswith('care_questionnaire_'):assert {r['name'] for r in inspector.get_columns(name)}==set(table.columns.keys())
        assert any(r['sqltext'].startswith('from_store_id') for r in inspector.get_check_constraints('care_history_grants'))
        with engine.connect() as db:assert not db.execute(text('PRAGMA foreign_key_check')).first()
    finally:engine.dispose()
