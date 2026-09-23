"""Production customer/insurance/worker hooks and append-only correction evidence."""
import uuid,sqlite3
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import User,CashEntry
from app.flow_models import Case,Task,StockMove
from app.customer_service_models import VehicleObservation,CareCase
from app import observation_corrections_service as svc
from app.observation_corrections_models import ObservationCorrection,CorrectionEffect,CorrectionEvent,ReminderBasis,ReminderReplacement,InsuranceBasisInvalidation
from app.tenancy import set_scope
from tests.conftest import login,TEST_DIR
from tests.test_customer_service import vehicle,observe,rule,customer,user_id,API as CARE
from tests.test_multistore import second_store,switch

API='/api/observation-corrections'
@pytest.fixture(autouse=True)
def restored_domain():
    yield
    from app.observation_corrections_integrity import validate
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored);validate(restored)
        if restored.execute('SELECT COUNT(*) FROM observation_corrections').fetchone()[0]:
            restored.execute("UPDATE observation_corrections SET proposed=json_set(proposed,'$.odometer_km',coalesce(json_extract(proposed,'$.odometer_km'),0)+1)")
            with pytest.raises(ValueError):validate(restored)

def view(c,vid):
    r=c.get(API+f'/vehicles/{vid}');assert r.status_code==200,r.text;return r.json()
def detail(c,row):
    r=c.get(API+f"/cases/{row['id']}");assert r.status_code==200,r.text;return r.json()
def proposal(c,vid,oid=None,operation='replace',status=201,key=None,body=None,**changes):
    value=view(c,vid);original=next((o for o in value['observations'] if o['id']==oid),value['observations'][-1])
    proposed={k:original[k] for k in ('observed_date','odometer_km','valid_until','source_reference')};proposed.update(changes)
    payload=body or dict(request_id=key or uuid.uuid4().hex,vehicle_id=vid,vehicle_version=value['vehicle']['version'],observation_id=original['id'],base_digest=original['digest'],operation=operation,proposed=proposed if operation=='replace' else None,reason='核对本次原资料')
    r=c.post(API+'/cases',json=payload);assert r.status_code==status,r.text;return r.json().get('case',r.json())
def proof(c,row):
    r=c.post(f"/api/flow/cases/{row['id']}/files",files={'file':('original.txt','核对本次原资料'.encode(),'text/plain')});assert r.status_code==200,r.text;return r.json()['id']
def action(c,row,key,values=None,status=200,body=None):
    payload=body or dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values=values or {})
    r=c.post(API+f"/cases/{row['id']}/actions/{key}",json=payload);assert r.status_code==status,r.text;return r.json().get('case',r.json())
def submitted(c,row):return action(c,row,'submit',{'evidence_id':proof(c,row)})
def approve(c,row):
    prior=c.get('/api/auth/me').json()['username'];login(c,'manager')
    row=action(c,row,'approve',{'evidence_id':proof(c,row),'reason':'核对本次原资料'});login(c,prior);return row
def generate(c,key=None):
    r=c.post(API+'/reminders/generate',json={'request_id':key or uuid.uuid4().hex});assert r.status_code==200,r.text;return r.json()
def care_action(c,row,action,values=None):
    # Exercise the production transaction with its actual original schemas.
    with SessionLocal() as db:
        set_scope(db,{1},1);user=db.scalar(select(User).where(User.username==c.get('/api/auth/me').json()['username']))
        from app.customer_service_api import Start,Followup,Handoff,Cancel,Close
        values={'start':Start,'followup':Followup,'handoff':Handoff,'cancel':Cancel,'close':Close}[action].model_validate(values or {}).model_dump()
        return svc.care.case_action(db,user,uuid.uuid4().hex,row['id'],row['version'],action,values)

def test_independent_approval_preserves_original_and_replaces_pending_reminder(client):
    c=client;v=vehicle(c);original=observe(c,v,'maintenance',today()-timedelta(days=31),1000);v=original['vehicle']
    v=observe(c,v,km=9000)['vehicle'];rule(c)
    tick=uuid.uuid4().hex;generated=generate(c,tick);old=generated['created'][0];before=view(c,v['id']);epoch=before['vehicle']['observation_epoch']
    assert generate(c,tick)==generated and view(c,v['id'])['vehicle']['version']==before['vehicle']['version']
    with SessionLocal() as db:
        set_scope(db,{1},1);assert svc.generation_receipt_exists(db,tick)
    row=proposal(c,v['id'],odometer_km=7000);row=submitted(c,row)
    task=c.get(CARE+f"/cases/{old['case_id']}").json();task=care_action(c,task,'start')['case']
    with pytest.raises(HTTPException):care_action(c,task,'followup',{'channel':'in_person','contact_result':'contacted','note':'核对本次原资料'})
    task=care_action(c,task,'followup',{'channel':'internal','contact_result':'progress','note':'核对本次原资料'})['case']
    assert generate(c)['created']==[]
    action(c,row,'approve',{'evidence_id':proof(c,row),'reason':'核对本次原资料'},403)
    row=approve(c,row);assert row['state']=='completed';after=view(c,v['id'])
    assert after['vehicle']['odometer_km']==7000 and after['vehicle']['observation_epoch']!=epoch
    assert c.get(CARE+f"/cases/{old['case_id']}").json()['state']=='cancelled'
    new=generate(c)['created'];assert len(new)==1 and generate(c)['created']==[]
    with SessionLocal() as db:
        assert [o.odometer_km for o in db.scalars(select(VehicleObservation).order_by(VehicleObservation.id))]==[1000,9000]
        link=db.scalar(select(ReminderReplacement));assert (link.previous_case_id,link.replacement_case_id)==(old['case_id'],new[0]['case_id'])
        basis=db.scalar(select(ReminderBasis).where(ReminderBasis.case_id==new[0]['case_id']));assert basis.snapshot['current']['odometer_km']==7000 and basis.current_effect_id
        assert db.scalar(select(func.count()).select_from(CashEntry))==db.scalar(select(func.count()).select_from(StockMove))==0

def test_shorten_mistyped_expiry_reject_withdraw_retract_and_append_effect(client):
    c=client;v=observe(c,vehicle(c),'insurance',until=today()+timedelta(days=300))['vehicle'];oid=view(c,v['id'])['observations'][0]['id']
    row=submitted(c,proposal(c,v['id'],valid_until=(today()+timedelta(days=30)).isoformat()));login(c,'manager')
    row=action(c,row,'reject',{'reason':'核对本次原资料','evidence_id':proof(c,row)});login(c)
    assert view(c,v['id'])['observations'][0]['valid_until']==(today()+timedelta(days=300)).isoformat()
    row=submitted(c,proposal(c,v['id'],valid_until=(today()+timedelta(days=30)).isoformat()));row=action(c,row,'cancel',{'reason':'核对本次原资料'})
    row=approve(c,submitted(c,proposal(c,v['id'],valid_until=(today()+timedelta(days=30)).isoformat())))
    action(c,row,'cancel',{'reason':'核对本次原资料'},409)
    row=approve(c,submitted(c,proposal(c,v['id'],operation='retract')))
    assert not view(c,v['id'])['observations'][0]['active']
    row=approve(c,submitted(c,proposal(c,v['id'],valid_until=(today()+timedelta(days=20)).isoformat(),source_reference='核对本次原资料')))
    assert view(c,v['id'])['observations'][0]['active']
    with SessionLocal() as db:
        chain=list(db.scalars(select(CorrectionEffect).order_by(CorrectionEffect.id)));assert len(chain)==3 and chain[-1].parent_effect_id==chain[-2].id
        original=db.scalar(select(VehicleObservation).where(VehicleObservation.id==oid));assert original.valid_until==today()+timedelta(days=300)
        original.odometer_km=0
        with pytest.raises(HTTPException):db.commit()

def test_completed_cycle_is_not_reissued_by_same_day_mileage_correction(client):
    c=client;v=observe(c,vehicle(c),'maintenance',today()-timedelta(days=31),1000)['vehicle'];v=observe(c,v,km=8000)['vehicle'];rule(c)
    old=generate(c)['created'][0];row=c.get(CARE+f"/cases/{old['case_id']}").json();row=care_action(c,row,'start')['case']
    row=care_action(c,row,'followup',{'channel':'in_person','contact_result':'contacted','note':'核对本次原资料'})['case']
    row=care_action(c,row,'close',{'result':'resolved','note':'核对本次原资料'})['case']
    approve(c,submitted(c,proposal(c,v['id'],odometer_km=7500)))
    assert generate(c)['created']==[]
    assert c.get(CARE+f"/cases/{row['id']}").json()['state']=='completed'
    assert len(view(c,v['id'])['observations'])==2

def test_duplicate_stale_own_original_file_and_cross_store(client):
    c=client;v=observe(c,vehicle(c),km=9000)['vehicle'];key=uuid.uuid4().hex
    initial=view(c,v['id']);o=initial['observations'][0]
    body=dict(request_id=key,vehicle_id=v['id'],vehicle_version=initial['vehicle']['version'],observation_id=o['id'],base_digest=o['digest'],operation='replace',proposed={k:(8000 if k=='odometer_km' else o[k]) for k in ('observed_date','odometer_km','valid_until','source_reference')},reason='核对本次原资料')
    row=proposal(c,v['id'],body=body);assert proposal(c,v['id'],body=body)==row
    proposal(c,v['id'],body={**body,'request_id':uuid.uuid4().hex},status=409)
    p=proof(c,row);payload=dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values={'evidence_id':p})
    submitted_row=action(c,row,'submit',body=payload);assert action(c,row,'submit',body=payload)==submitted_row
    action(c,row,'submit',body={**payload,'request_id':uuid.uuid4().hex},status=409)
    other_row=proposal(c,v['id'],odometer_km=7500);foreign_proof=proof(c,other_row);login(c,'manager');action(c,row,'approve',{'evidence_id':foreign_proof,'reason':'核对本次原资料'},422);login(c)
    other=second_store(c);switch(c,other);assert c.get(API+f"/vehicles/{v['id']}").status_code==404;assert c.get(API+f"/cases/{row['id']}").status_code==404
    switch(c,'all');assert c.get(API+'/catalog').status_code==409;switch(c,1);login(c,'inventory');assert c.get(API+'/catalog').status_code==403

def test_competing_submit_and_approve_have_single_effect(client):
    c=client;v=observe(c,vehicle(c),km=9000)['vehicle'];a=proposal(c,v['id'],odometer_km=7000);b=proposal(c,v['id'],odometer_km=8000)
    payloads=[dict(request_id=uuid.uuid4().hex,version=detail(c,r)['version'],values={'evidence_id':proof(c,r)}) for r in (a,b)]
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for x in clients:login(x)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda i:clients[i].post(API+f"/cases/{[a,b][i]['id']}/actions/submit",json=payloads[i]),range(2)))
        assert sorted(r.status_code for r in results)==[200,409]
    row=next(r.json()['case'] for r in results if r.status_code==200);login(c,'manager');p=proof(c,row);version=detail(c,row)['version']
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for x in clients:login(x,'manager')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda i:clients[i].post(API+f"/cases/{row['id']}/actions/approve",json=dict(request_id=uuid.uuid4().hex,version=version,values={'evidence_id':p,'reason':'核对本次原资料'})),range(2)))
        assert sorted(r.status_code for r in results)==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CorrectionEffect))==1

def test_real_insurance_termination_excludes_carried_mileage_and_invalidates_old_task(client):
    from tests.test_insurance_orders import setup,ready,issued,termination,apply_plan,detail as insurance_detail
    c=client;source,q,cv=setup(c,'customer_direct');source=issued(c,ready(c,source));rule(c,'renewal',lead_days=365)
    current=view(c,cv['id']);assert current['vehicle']['odometer_km'] is None
    assert current['observations'][0]['odometer_measured'] is False
    proposal(c,cv['id'],valid_until=today().isoformat(),odometer_km=123,status=409)
    old=generate(c)['created'][0]
    source=termination(c,source,0,[])
    def sync():
        r=c.post(API+f"/insurance/{source['id']}/sync",json=dict(request_id=uuid.uuid4().hex,version=insurance_detail(c,source)['version']));assert r.status_code==200,r.text;return r.json()
    assert sync()['invalidated']==0
    source=apply_plan(c,source);assert sync()['invalidated']==0 and sync()['invalidated']==0
    assert c.get(CARE+f"/cases/{old['case_id']}").json()['state']=='cancelled'
    assert generate(c)['created']==[] and view(c,cv['id'])['vehicle']['odometer_km'] is None
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InsuranceBasisInvalidation))==1
        assert db.scalar(select(VehicleObservation)).odometer_km==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0

def test_customer_owner_employee_and_manager_reuses_readable_original(client):
    c=client;user_id('reception');v=observe(c,vehicle(c,customer(owner='sales')),km=5000)['vehicle'];other=vehicle(c,customer(owner='reception'))
    login(c,'sales');assert c.get(API+f"/vehicles/{other['id']}").status_code==404
    row=proposal(c,v['id'],odometer_km=4000);p=proof(c,row);row=action(c,row,'submit',{'evidence_id':p});login(c,'manager')
    row=action(c,row,'approve',{'evidence_id':p,'reason':'主管复用本单原件并独立核对'});assert row['state']=='completed'
    login(c,'reception');assert c.get(API+f"/cases/{row['id']}").status_code==404
    login(c,'auditor');assert c.get(API+f"/cases/{row['id']}").status_code==200
    proposal(c,v['id'],odometer_km=3500,status=403)

def test_rejects_cross_vehicle_inconsistent_neighbor_and_quarantined_file(client,monkeypatch):
    c=client;v=observe(c,vehicle(c),when=today()-timedelta(days=1),km=3000)['vehicle'];v=observe(c,v,km=4000)['vehicle'];prior=view(c,v['id'])['observations'][0]
    proposal(c,v['id'],oid=prior['id'],odometer_km=5000,status=409)
    proposal(c,v['id'],odometer_km=2000,status=409)
    other=observe(c,vehicle(c,customer()),km=100)['vehicle'];values=view(c,v['id'])
    body=dict(request_id=uuid.uuid4().hex,vehicle_id=v['id'],vehicle_version=values['vehicle']['version'],observation_id=view(c,other['id'])['observations'][0]['id'],base_digest='0'*64,operation='retract',reason='不能串用另一客户车辆的原观察')
    proposal(c,v['id'],body=body,status=422)
    row=proposal(c,v['id'],odometer_km=3500)
    from dataclasses import replace
    from app import file_security
    monkeypatch.setattr(file_security,'settings',replace(file_security.settings,file_scan_mode='quarantine'));p=proof(c,row)
    action(c,row,'submit',{'evidence_id':p},409)
    assert detail(c,row)['state']=='pending'

def test_append_guard_uses_effective_values_and_holds_new_observation(client):
    c=client;v=observe(c,vehicle(c),km=50000)['vehicle'];row=proposal(c,v['id'],odometer_km=5000);row=submitted(c,row)
    observe(c,view(c,v['id'])['vehicle'],km=5100,status=409)
    approve(c,row);new=observe(c,view(c,v['id'])['vehicle'],km=5100)['vehicle']
    assert new['odometer_km']==5100
    with SessionLocal() as db:assert db.scalar(select(VehicleObservation)).odometer_km==50000

def test_declining_manual_cycle_no_reissue_and_concurrent_generation(client):
    c=client;v=observe(c,vehicle(c),'maintenance',today()-timedelta(days=40),2000)['vehicle'];v=observe(c,v,km=9000)['vehicle'];rule(c)
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for x in clients:login(x)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda i:clients[i].post(API+'/reminders/generate',json={'request_id':uuid.uuid4().hex}),range(2)))
    assert all(r.status_code in {200,409} for r in results)
    ids=[r.json()['created'][0]['case_id'] for r in results if r.status_code==200 and r.json()['created']];assert len(ids)==1
    care_row=c.get(CARE+f'/cases/{ids[0]}').json();care_action(c,care_row,'cancel',{'reason':'客户明确要求取消本轮提醒'})
    approve(c,submitted(c,proposal(c,v['id'],odometer_km=8500)))
    assert generate(c)['created']==[]

def test_restore_rejects_source_baseline_effect_parent_and_reminder_forgery(client):
    from app.observation_corrections_integrity import validate
    c=client;v=observe(c,vehicle(c),'maintenance',today()-timedelta(days=31),5000)['vehicle'];v=observe(c,v,km=11000)['vehicle'];rule(c);generate(c)
    approve(c,submitted(c,proposal(c,v['id'],odometer_km=10500)));generate(c)
    statements=["UPDATE care_vehicle_observations SET odometer_km=odometer_km+1", "UPDATE observation_correction_effects SET parent_token='999'", "UPDATE observation_reminder_bases SET current_effect_id=NULL WHERE current_effect_id IS NOT NULL", "UPDATE observation_reminder_replacements SET previous_case_id=replacement_case_id", "UPDATE observation_reminder_invalidations SET store_id=999", "UPDATE observation_correction_events SET actor_id=1 WHERE action='approve'"]
    for sql in statements:
        with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
            source.backup(restored);validate(restored);restored.execute('PRAGMA ignore_check_constraints=ON');restored.execute(sql)
            with pytest.raises(ValueError):validate(restored)
    with sqlite3.connect(':memory:') as minimal:
        minimal.execute('CREATE TABLE flow_files (sha256 TEXT,content BLOB)')
        assert validate(minimal) == {'corrections':0,'effects':0,'insurance_invalidations':0,'reminder_bases':0}

def test_insurance_whole_chain_refuses_mismatched_consent_without_touching_vehicle(client):
    from tests.test_insurance_orders import setup,ready,issued,termination,apply_plan
    from app.observation_corrections_integrity import validate
    c=client;row,_,cv=setup(c,'customer_direct');row=apply_plan(c,termination(c,issued(c,ready(c,row)),0,[]))
    before=view(c,cv['id'])['vehicle']['version']
    # Fault injection in an isolated synthetic database, restored immediately.
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        original=connection.execute('SELECT digest FROM insurance_termination_consents').fetchone()[0]
        connection.execute("UPDATE insurance_termination_consents SET digest=?",('0'*64,));connection.commit()
    try:
        response=c.post(API+f"/insurance/{row['id']}/sync",json={'request_id':uuid.uuid4().hex,'version':row['version']});assert response.status_code==409,response.text
        with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(InsuranceBasisInvalidation))==1
        assert view(c,cv['id'])['vehicle']['version']==before
    finally:
        with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:connection.execute('UPDATE insurance_termination_consents SET digest=?',(original,))
    response=c.post(API+f"/insurance/{row['id']}/sync",json={'request_id':uuid.uuid4().hex,'version':row['version']});assert response.status_code==200,response.text
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate(restored);restored.execute("UPDATE insurance_termination_reviews SET decision='rejected'")
        with pytest.raises(ValueError):validate(restored)

def test_corrected_expiry_cannot_reissue_manually_cancelled_same_cycle(client):
    c=client;v=observe(c,vehicle(c),'insurance',until=today()+timedelta(days=10))['vehicle'];oid=view(c,v['id'])['observations'][0]['id'];rule(c,'renewal',lead_days=30)
    old=generate(c)['created'][0]['case_id'];care_row=c.get(CARE+f'/cases/{old}').json();care_action(c,care_row,'cancel',{'reason':'客户明确取消本期限的后续联系'})
    current=view(c,v['id'])['vehicle'];v=observe(c,current,'insurance',until=today()+timedelta(days=20))['vehicle']
    approve(c,submitted(c,proposal(c,v['id'],oid=oid,valid_until=(today()+timedelta(days=20)).isoformat())))
    assert len({o['valid_until'] for o in view(c,v['id'])['observations']})==1
    assert generate(c)['created']==[]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CareCase))==1
        assert db.scalar(select(ReminderBasis)).snapshot['baseline']['valid_until']==(today()+timedelta(days=10)).isoformat()



def test_real_customer_routes_review_hold_withdraw_and_worker_epoch(client):
    from app.reminder_worker import run
    from tests.test_customer_service import action as actual_action
    c=client;v=observe(c,vehicle(c),'maintenance',today()-timedelta(days=31),1000)['vehicle'];v=observe(c,v,km=9000)['vehicle'];rule(c)
    first=run(once=True);assert first['created']==1 and not first['errors'];assert run(once=True)['created']==0
    with SessionLocal() as db:old=db.scalar(select(CareCase.case_id))
    login(c,'service');task=c.get(CARE+f'/cases/{old}').json();task=actual_action(c,task,'start')['case']
    row=submitted(c,proposal(c,v['id'],odometer_km=7000));task=c.get(CARE+f'/cases/{old}').json()
    assert task['reminder_basis']['status']=='pending_review' and task['followup_channels']==['internal']
    actual_action(c,task,'followup',{'channel':'in_person','contact_result':'contacted','note':'此时不能按错误里程向客户联系'},status=409)
    actual_action(c,task,'close',{'result':'resolved','note':'不能按复核中的基准结案'},status=409)
    task=actual_action(c,task,'followup',{'channel':'internal','contact_result':'progress','note':'仅记录本次内部核对'})['case']
    assert run(once=True)['created']==0
    action(c,row,'cancel',{'reason':'申请人核对后撤回待复核申请'});assert run(once=True)['created']==0
    task=c.get(CARE+f'/cases/{old}').json();assert task['reminder_basis']['status']=='effective'
    task=actual_action(c,task,'followup',{'channel':'in_person','contact_result':'contacted','note':'有效基准恢复后实际当面沟通'})['case']
    row=approve(c,submitted(c,proposal(c,v['id'],odometer_km=7000)))
    assert run(once=True)['created']==1 and run(once=True)['created']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CareCase))==2
        assert db.scalar(select(func.count()).select_from(VehicleObservation))==2
    original_route=c.get(CARE+f"/vehicles/{v['id']}").json()
    assert original_route['vehicle']['odometer_km']==7000
    assert next(o for o in original_route['observations'] if o['kind']=='odometer')['odometer_km']==9000


def test_existing_terminated_insurance_reconciles_under_original_worker_without_mileage(client):
    from tests.test_insurance_orders import setup,ready,issued,termination,apply_plan
    from app.reminder_worker import run
    c=client;source,_,cv=setup(c,'customer_direct');source=apply_plan(c,termination(c,issued(c,ready(c,source)),0,[]))
    # Reproduce the exact pre-integration state: valid old insurance application,
    # with no new-domain projection. No original business or cash fact changes.
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:connection.execute('DELETE FROM observation_insurance_invalidations')
    rule(c,'renewal',lead_days=365);user_id('customer_service');login(c,'customer_service')
    assert c.get('/api/insurance-orders/'+str(source['id'])).status_code==403
    result=c.post(CARE+'/reminders/generate',json={'request_id':uuid.uuid4().hex});assert result.status_code==200,result.text
    assert result.json()['created']==[] and view(c,cv['id'])['vehicle']['odometer_km'] is None
    assert run(once=True)['created']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InsuranceBasisInvalidation))==1
        assert db.scalar(select(func.count()).select_from(CareCase))==0
        assert db.scalar(select(VehicleObservation)).odometer_km==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_original_insurance_renewal_submission_uses_current_care_basis(client):
    from tests.test_insurance_orders import setup,cmd,ready,proof as insurance_proof
    from tests.test_customer_service import action as actual_action
    c=client;v=observe(c,vehicle(c),'insurance',until=today()+timedelta(days=10))['vehicle'];rule(c,'renewal',lead_days=30)
    task_id=generate(c)['created'][0]['case_id'];task=c.get(CARE+f'/cases/{task_id}').json();task=actual_action(c,task,'start')['case']
    source,_,_=setup(c,'customer_direct',renewal=task,cv=view(c,v['id'])['vehicle']);source=ready(c,source)
    correction=submitted(c,proposal(c,v['id'],valid_until=(today()+timedelta(days=20)).isoformat()))
    values={'external_reference':uuid.uuid4().hex,'business_date':today().isoformat(),'evidence_id':insurance_proof(c,source)}
    cmd(c,source,'submit',values,409)
    action(c,correction,'cancel',{'reason':'暂撤回复核，保持原有效期限'})
    source=cmd(c,source,'submit',values)
    assert len(source['submissions'])==1
    # A later review holds future outreach, but cannot suppress an external result
    # that actually happened after an already-authorized submission.
    correction=submitted(c,proposal(c,v['id'],valid_until=(today()+timedelta(days=20)).isoformat()))
    source=cmd(c,source,'result',{'submission_id':source['submissions'][0]['id'],'outcome':'issued','policy_number':'ACTUAL-NEW-POLICY','result':'已提交后保险公司实际出保回件','business_date':today().isoformat(),'evidence_id':insurance_proof(c,source)})
    assert len(source['results'])==1 and source['results'][0]['observation_id']
    action(c,correction,'cancel',{'reason':'另有实际新出保结果，撤回本次旧观察申请'})


def test_registered_generic_case_queries_match_specialized_ownership_and_unknown_versions(client):
    c=client;user_id('reception');mine=observe(c,vehicle(c,customer(owner='sales')),km=5000)['vehicle'];other=observe(c,vehicle(c,customer(owner='reception')),km=6000)['vehicle']
    a=proposal(c,mine['id'],odometer_km=4500);b=proposal(c,other['id'],odometer_km=5500)
    login(c,'sales');items=c.get('/api/flow/cases?kind=observation_correction').json()['items'];assert {r['id'] for r in items}=={a['id']}
    assert c.get('/api/flow/cases/'+str(a['id'])).status_code==200
    assert c.get('/api/flow/cases/'+str(b['id'])).status_code==404
    # The specialized version is explicit. No ordinary API can invent/upgrade it.
    response=c.post('/api/flow/cases',json={'request_id':uuid.uuid4().hex,'kind':'observation_correction','values':{}});assert response.status_code in {403,409},response.text
    login(c);switch(c,'all');assert c.get('/api/flow/cases?kind=observation_correction').json()['items']==[]
    switch(c,1)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:connection.execute('UPDATE flow_cases SET flow_version=1 WHERE id=?',(a['id'],))
    try:
        assert c.get(API+f"/cases/{a['id']}").status_code==404
        assert c.get('/api/flow/cases/'+str(a['id'])).status_code in {404,409}
    finally:
        with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:connection.execute('UPDATE flow_cases SET flow_version=2 WHERE id=?',(a['id'],))


def test_actual_insurance_termination_keeps_finance_permission_and_single_transaction(client):
    from tests.test_insurance_orders import setup,ready,issued,termination,cmd,proof as insurance_proof,detail as insurance_detail
    c=client;source,_,cv=setup(c,'customer_direct');source=termination(c,issued(c,ready(c,source)),0,[]);plan=source['plans'][-1]
    login(c,'manager');source=cmd(c,source,'termination_review',{'plan_id':plan['id'],'decision':'approved','reason':'另一位主管核对原实际退保资料','evidence_id':insurance_proof(c,source)})
    login(c);source=cmd(c,source,'termination_consent',{'plan_id':plan['id'],'digest':plan['digest'],'evidence_id':insurance_proof(c,source)})
    evidence_id=insurance_proof(c,source,True);values={'plan_id':plan['id'],'evidence_id':evidence_id}
    login(c,'service');cmd(c,source,'termination_apply',values,403)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(InsuranceBasisInvalidation))==0
    login(c,'finance');body={'request_id':uuid.uuid4().hex,'version':insurance_detail(c,source)['version'],'values':values}
    applied=cmd(c,source,'termination_apply',body=body);assert cmd(c,source,'termination_apply',body=body)==applied
    cmd(c,source,'termination_apply',body={**body,'request_id':uuid.uuid4().hex},status=409)
    login(c);assert not view(c,cv['id'])['observations'][0]['active']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InsuranceBasisInvalidation))==1
        assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_original_generator_replays_preintegration_receipt_without_new_cycle(client):
    from app.customer_service_models import CareReceipt
    c=client;key=uuid.uuid4().hex;legacy={'created':[],'skipped':[],'as_of':today().isoformat(),'automatic':False,'notice':'只建立内部待办，未发送任何外部消息；仅依据已登记日期和里程'}
    # Recreate an old generator's immutable receipt, not a mutable case status.
    with SessionLocal() as db:
        set_scope(db,{1},1);u=db.scalar(select(User).where(User.username=='admin'))
        db.add(CareReceipt(request_key=key,actor_id=u.id,digest=svc.digest(['generate_reminders',{'day':today().isoformat(),'automatic':False}]),result=legacy));db.commit()
    v=observe(c,vehicle(c),'maintenance',today()-timedelta(days=31),1000)['vehicle'];rule(c)
    response=c.post(CARE+'/reminders/generate',json={'request_id':key});assert response.status_code==200 and response.json()==legacy
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CareCase))==0
    login(c,'manager');assert c.post(CARE+'/reminders/generate',json={'request_id':key}).status_code==409
    login(c);assert len(c.post(CARE+'/reminders/generate',json={'request_id':uuid.uuid4().hex}).json()['created'])==1
