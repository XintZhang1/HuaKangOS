"""Registered-router synthetic acceptance for one actual VIN arrival across domains."""
import copy
import sqlite3
import uuid
from datetime import timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text
from app.main import app
from app.db import engine, SessionLocal, utcnow, today
from app.flow_models import Case, StockMove, PaymentLink, FlowEvent, FileAsset, Task
from app.models import CashEntry, Store, UserStore, User
from app.gate_visit_models import GateVisit, GateFact, GateCorrection, GateReview, GateHandoff, RepairGateExit
from app.gate_visit_integrity import validate
from app.tenancy import set_scope
from tests.conftest import login
from tests.test_customer_service import vehicle, customer, user_id
from tests.test_workflow import evidence
from tests.test_service_intake import resource, appointment, arrive, convert, normal, work_quote, released, slot, cmd as intake_cmd, proof, technician
from tests.test_repair_orders import cmd as repair_cmd, detail as repair_detail
from tests.test_visit_activity import report, csv_same

API='/api/gate-visits'


def at(minutes=-1):
    return (utcnow()+timedelta(minutes=minutes)).replace(tzinfo=timezone.utc).isoformat()


def make(c, v=None):
    v=v or vehicle(c)
    r=c.post(API,json={'request_id':uuid.uuid4().hex,'customer_vehicle_id':v['id'],'purpose':'consultation','description':'有据咨询来访，不涉及库存或现金'})
    assert r.status_code==201,r.text
    return r.json()


def get(c,r):
    response=c.get(API+'/'+str(r['id']));assert response.status_code==200,response.text;return response.json()


def actual(c,r,when=None,**changes):
    return {'confirmed':True,'checked_vin':r['vin'],'actual_at':when or at(), 'evidence_id':evidence(c,{'id':r['case_id']}),'reason':'本人现场核对原车辆及实际发生时间',**changes}


def cmd(c,r,action,v=None,status=200,key=None,version=None):
    r=get(c,r)
    response=c.post(API+f'/{r["id"]}/actions/{action}',json={'request_id':key or uuid.uuid4().hex,'version':version or r['version'],'values':v or {}})
    assert response.status_code==status,response.text
    return response.json()


def entered(c,r=None):
    r=r or make(c);return cmd(c,r,'arrive',actual(c,r,at(-5)))


def correction(c,r,kind='arrive_time',when=None,status=200):
    r=get(c,r)
    response=c.post(API+f'/{r["id"]}/corrections',json={'request_id':uuid.uuid4().hex,'version':r['version'],'values':{
        'kind':kind,'actual_at':None if kind=='void_visit' else when or at(-10),'evidence_id':evidence(c,{'id':r['case_id']}),'reason':'核对原门岗凭据发现登记时间有误'}})
    assert response.status_code==status,response.text;return response.json()


def review(c,r,decision='approve',status=200,key=None,version=None):
    r=get(c,r);cr=r['corrections'][-1]
    values={'reason':'复核原进出厂记录和独立凭据后的处理'}
    if decision!='cancel':values['evidence_id']=evidence(c,{'id':r['case_id']})
    response=c.post(API+f'/corrections/{cr["id"]}/actions/{decision}',json={'request_id':key or uuid.uuid4().hex,'version':version or cr['version'],'values':values})
    assert response.status_code==status,response.text;return response.json()


def valid():
    with sqlite3.connect(engine.url.database) as connection:
        result=validate(connection)
        from app.backup_integrity import validate_sqlite
        assert validate_sqlite(connection)['integrity']=='ok'
        return result


def test_plan_actual_leave_no_cash_no_stock_and_same_source_csv(client):
    r=make(client)
    assert report(client)['metrics']['service_actual_arrivals']==0
    cmd(client,r,'leave',actual(client,r),409)
    r=entered(client,r);d=report(client)
    assert d['complete'] and d['metrics']['service_actual_arrivals']==1 and d['metrics']['service_actual_departures']==0
    r=cmd(client,r,'leave',actual(client,r))
    d=report(client);assert d['complete'] and d['metrics']['service_actual_departures']==1
    for name in ('service_gate_movements','service_visit_cohort','gate_corrections'):csv_same(client,d,name)
    assert sum(d['charts'][1]['series'][0]['values'])==len(d['tables']['service_gate_movements']['rows'])==2
    with SessionLocal() as db:
        for model in (StockMove,PaymentLink,CashEntry):assert db.scalar(select(func.count()).select_from(model))==0
    assert valid()['verified_gate_visits']==1


def test_cancel_only_unarrived_and_repeat_requests_are_not_new_facts(client):
    planned=make(client);cmd(client,planned,'cancel',{'reason':'未实际进厂取消安排'})
    assert report(client)['metrics']['service_actual_arrivals']==0
    r=make(client);v=actual(client,r);key=uuid.uuid4().hex;version=r['version']
    first=cmd(client,r,'arrive',v,key=key,version=version)
    assert cmd(client,r,'arrive',v,key=key,version=version)==first
    cmd(client,r,'arrive',v,key=key,status=409,version=version+1)
    cmd(client,r,'arrive',v,status=409,version=version)
    cmd(client,r,'cancel',{'reason':'不得用取消抹除实际进厂'},409)
    assert valid()['verified_gate_visits']==2


@pytest.mark.parametrize('change',[
    {'confirmed':False},{'confirmed':'true'},{'confirmed':1},{'actual_at':'2026-09-22T12:00:00'},
    {'actual_at':'1999-01-01T00:00:00Z'},{'actual_at':'2099-01-01T00:00:00Z'},
    {'state':'departed'},{'cash_cents':1},{'checked_vin':'BADVIN'},
])
def test_explicit_facts_strict_types_no_state_or_finance_shortcuts(client,change):
    r=make(client);cmd(client,r,'arrive',actual(client,r,**change),422)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(GateFact))==0


def test_wrong_vin_wrong_case_evidence_and_backwards_time_are_rejected(client):
    r=make(client);other=make(client,vehicle(client,vin='LFV2A21K9J7654321'))
    cmd(client,r,'arrive',actual(client,r,checked_vin=other['vin']),409)
    cmd(client,r,'arrive',actual(client,r,evidence_id=evidence(client,{'id':other['case_id']})),422)
    r=entered(client,r);cmd(client,r,'leave',actual(client,r,at(-20)),409)
    assert valid()['verified_gate_visits']==2


def test_same_vin_other_customer_relation_cannot_bypass_active_arrival(client):
    first=entered(client)
    second=make(client,vehicle(client,customer()))
    assert second['customer_vehicle_id']!=first['customer_vehicle_id'] and second['vin']==first['vin']
    cmd(client,second,'arrive',actual(client,second),409)
    first=cmd(client,first,'leave',actual(client,first,at(-1)))
    second=cmd(client,second,'arrive',actual(client,second,at(0)))
    assert second['status']=='inside' and valid()['verified_gate_visits']==2


def test_gate_and_original_intake_share_arrival_lock_and_real_departure(client):
    v=vehicle(client);gate=entered(client,make(client,v));a=appointment(client,v,resource(client))
    intake_cmd(client,'appointments',a,'arrive',{'checked_vin':v['vin'],'odometer_km':1,'evidence_id':proof(client,a)},409)
    cmd(client,gate,'leave',actual(client,gate));a=arrive(client,a)
    other=make(client,v);cmd(client,other,'arrive',actual(client,other,at(0)),409)
    intake_cmd(client,'appointments',a,'leave',{'reason':'实际未开单离場','evidence_id':proof(client,a)})
    cmd(client,other,'arrive',actual(client,other,at(0)))
    assert valid()['verified_gate_visits']==2


def test_actual_handoff_reuses_original_gate_no_new_arrival(client):
    v=vehicle(client);r=entered(client,make(client,v));resource_row=resource(client)
    values={'checked_vin':r['vin'],'odometer_km':30,'evidence_id':evidence(client,{'id':r['case_id']}),'resource_id':resource_row['id'],'problem':'转维修检查实际异响',**slot()}
    r=cmd(client,r,'handoff',values)
    assert r['status']=='handed_over'
    a=client.get('/api/service-intake/appointments/'+str(r['handoff_appointment_id'])).json()
    assert a['arrived_at']==r['arrived_at'] and a['case_id']==r['case_id']
    repair=convert(client,a);repair,_=work_quote(client,repair);repair=repair_cmd(client,repair,'start',{'result':'核对后实际开工'});released(client,repair)
    d=report(client);assert d['complete'] and d['metrics']['service_actual_arrivals']==d['metrics']['service_actual_departures']==1
    assert d['tables']['service_gate_movements']['rows'][0]['source_table']=='gate_facts'
    correction(client,r,status=409)
    cmd(client,r,'arrive',actual(client,r),409)
    assert valid()['verified_gate_handoffs']==1


def test_independent_correction_not_self_approval_and_original_fact_preserved(client):
    r=entered(client);original=r['facts'][0]['actual_at'];r=correction(client,r)
    review(client,r,status=403)
    cmd(client,r,'leave',actual(client,r),409)
    login(client,'manager');r=review(client,r)
    assert r['facts'][0]['actual_at']==original and r['arrived_at']!=original
    assert r['corrections'][0]['status']=='approved'
    assert valid()['verified_gate_corrections']==1
    assert report(client)['complete']


@pytest.mark.parametrize('decision',['reject','cancel'])
def test_rejected_or_withdrawn_correction_does_not_change_source(client,decision):
    r=entered(client);original=r['arrived_at'];r=correction(client,r)
    if decision=='reject':login(client,'manager')
    r=review(client,r,decision)
    assert r['arrived_at']==original
    login(client);cmd(client,r,'leave',actual(client,r))
    assert valid()['verified_gate_corrections']==1


def test_void_wrong_record_is_reviewed_not_fake_departure_and_frees_vin(client):
    r=entered(client);r=correction(client,r,'void_visit')
    login(client,'manager');r=review(client,r)
    assert r['status']=='voided' and len(r['facts'])==1
    tasks=client.get('/api/flow/cases/'+str(r['case_id'])).json()['tasks']
    assert next(t['status'] for t in tasks if t['key'].startswith('gate_review_'))=='done'
    assert report(client)['metrics']['service_actual_arrivals']==report(client)['metrics']['service_actual_departures']==0
    login(client);entered(client,make(client,vehicle(client,customer())))
    assert valid()['verified_gate_visits']==2


def test_cancelled_repair_needs_independent_actual_exit_not_cancel_state(client):
    repair,v,_,_,_=normal(client);repair=repair_cmd(client,repair,'cancel',{'reason':'到店后未开工取消维修'})
    gate=make(client,v);cmd(client,gate,'arrive',actual(client,gate,at(0)),409)
    values=actual(client,{'vin':v['vin'],'case_id':repair['id']},at(0))
    r=client.post(API+f'/repair-orders/{repair["id"]}/departure',json={'request_id':uuid.uuid4().hex,'version':repair['version'],'values':values})
    assert r.status_code==200,r.text
    cmd(client,gate,'arrive',actual(client,gate,at(0)))
    d=report(client);assert d['complete'] and d['metrics']['service_actual_arrivals']==2 and d['metrics']['service_actual_departures']==1
    assert valid()['verified_cancelled_repair_exits']==1


def test_scope_read_write_and_aggregate_vin_remains_private(client):
    gate=entered(client)
    with SessionLocal() as db:db.add(Store(id=2,code='GATE2',name='合成门店二'));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get(API+f'/{gate["id"]}').status_code==404
    assert client.get(API).json()['total']==0
    response=client.post(API+f'/{gate["id"]}/actions/cancel',json={'request_id':uuid.uuid4().hex,'version':gate['version'],'values':{'reason':'越店操作'}})
    assert response.status_code==404
    client.headers['X-Store-ID']='all';d=report(client)
    assert d['metrics']['service_actual_arrivals']==1 and gate['vin'] not in str(d)
    assert all(not r.get('route') for t in d['tables'].values() for r in t['rows'])
    assert client.get(API).status_code==409
    client.headers['X-Store-ID']='1';login(client,'inventory')
    assert client.get(API+f'/{gate["id"]}').status_code==403
    login(client,'finance');assert client.get(API+f'/{gate["id"]}').status_code==200
    r=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_vehicle_id':gate['customer_vehicle_id'],'purpose':'other','description':'财务不得登记实际来访'})
    assert r.status_code==403


def test_competing_gate_and_native_arrivals_only_one_commits(client):
    v=vehicle(client);g=make(client,v);a=appointment(client,v,resource(client))
    gv=actual(client,g,at(0));av={'checked_vin':v['vin'],'odometer_km':1,'evidence_id':proof(client,a)}
    clients=[]
    for _ in range(2):
        c=TestClient(app);login(c);clients.append(c)
    def send(which):
        if which==0:return clients[0].post(API+f'/{g["id"]}/actions/arrive',json={'request_id':uuid.uuid4().hex,'version':g['version'],'values':gv}).status_code
        return clients[1].post('/api/service-intake/appointments/'+str(a['id'])+'/actions/arrive',json={'request_id':uuid.uuid4().hex,'version':a['version'],'values':av}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,[0,1]))
        assert sorted(results)==[200,409]
    finally:
        for c in clients:c.close()
    assert report(client)['metrics']['service_actual_arrivals']==1
    valid()


@pytest.mark.parametrize('target',[GateFact,GateVisit,GateCorrection,GateReview,GateHandoff,RepairGateExit])
def test_immutable_fact_classes_are_registered(target):
    # Full persisted mutation cases below cover facts/reviews; this protects
    # accidental omissions from model registration / migration metadata.
    assert target.__tablename__ in target.metadata.tables


@pytest.mark.parametrize('sql',[
    "UPDATE gate_facts SET reason='被篡改的原事实'",
    "UPDATE gate_visits SET description='被篡改的来访用途'",
    "UPDATE gate_visits SET status='departed'",
    "DELETE FROM flow_events WHERE action='gate_arrive'",
])
def test_restore_and_report_refuse_inconsistent_originals(client,sql):
    entered(client);assert valid()['verified_gate_visits']==1
    with engine.begin() as db:db.execute(text(sql))
    with sqlite3.connect(engine.url.database) as db:
        with pytest.raises(ValueError,match='进出厂'):validate(db)
    d=report(client);assert not d['complete'] and d['metrics']['service_actual_arrivals']==0


def test_orm_cannot_overwrite_actual_fact(client):
    entered(client)
    with SessionLocal() as db:
        row=db.scalar(select(GateFact));row.reason='不能覆盖'
        with pytest.raises(HTTPException):db.commit()


def test_legacy_missing_domain_is_zero_but_partial_schema_rejected():
    with sqlite3.connect(':memory:') as db:
        assert validate(db)['verified_gate_visits']==0
        db.execute('CREATE TABLE gate_visits (id INTEGER PRIMARY KEY)')
        with pytest.raises(ValueError,match='部分新表'):validate(db)


def test_corrected_earlier_arrival_then_real_departure_before_original_error(client):
    r=entered(client);original=r['arrived_at'];r=correction(client,r,when=at(-20))
    login(client,'manager');r=review(client,r);login(client)
    r=cmd(client,r,'leave',actual(client,r,at(-10)))
    assert r['left_at']<original and r['arrived_at']<r['left_at']
    assert valid()['verified_gate_visits']==1 and report(client)['complete']
    # A later correction still binds the history that includes the earlier approval.
    r=correction(client,r,'leave_time',at(-8));login(client,'manager');review(client,r)
    assert valid()['verified_gate_corrections']==2 and report(client)['complete']


def test_gate_page_routes_strict_declaration_and_cancelled_repair_exit_controls(client):
    script=client.get('/static/gatevisits.js');assert script.status_code==200
    assert 'gateVisitsPage' in script.text and 'gateRepairExit' in script.text
    assert 'name="confirmed" required' in script.text and 'name="confirmed" checked' not in script.text
    assert "confirmed:form.elements.confirmed.checked" in script.text
    assert '/static/gatevisits.js' in client.get('/').text
    application=client.get('/static/app.js').text
    assert "data-route=\"gate-visits/${r.data.gate_visit_id}" in application
    assert "r.kind==='service_intake'&&(r.data.rework_id||r.data.appointment_id)" in application
    assert "gate-repair-exit" in client.get('/static/serviceintake.js').text


def test_nonempty_p68c_upgrade_preserves_all_originals_and_continues_native_work(client,tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import MetaData,inspect
    from app.db import make_engine,Base
    from scripts.migrate_database import table_fingerprint
    # Produce genuine typed old-domain facts and a replayable receipt, including binary evidence.
    v=vehicle(client);a=appointment(client,v,resource(client))
    key=uuid.uuid4().hex;version=a['version'];values={'checked_vin':v['vin'],'odometer_km':2,'evidence_id':proof(client,a)}
    old_result=intake_cmd(client,'appointments',a,'arrive',values,key=key,version=version)
    path=tmp_path/'actual-p68c.sqlite';url='sqlite:///'+path.as_posix()
    cfg=Config('alembic.ini');cfg.attributes['url_override']=url;command.upgrade(cfg,'p68c_questionnaire_versions')
    migrated=make_engine(url);metadata=MetaData();metadata.reflect(migrated)
    originals=[t for t in metadata.sorted_tables if t.name!='alembic_version']
    try:
        # Deferred fixture loading accommodates real circular original-case links;
        # the explicit full FK check below must pass before accepting this copy.
        with migrated.connect() as target:
            target.exec_driver_sql('PRAGMA foreign_keys=OFF');target.commit()
            with target.begin(),engine.connect() as source:
                for table in originals:
                    data=[dict(r) for r in source.execute(select(table)).mappings()]
                    if data:target.execute(table.insert(),data)
                assert target.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            target.exec_driver_sql('PRAGMA foreign_keys=ON');target.commit()
        with migrated.connect() as db:before={t.name:table_fingerprint(db,t) for t in originals}
        with sqlite3.connect(path) as db:
            assert validate(db)['verified_gate_visits']==0
            assert db.execute('SELECT typeof(content) FROM flow_files LIMIT 1').fetchone()[0]=='blob'
        command.upgrade(cfg,'head')
        with migrated.connect() as db:assert before=={t.name:table_fingerprint(db,t) for t in originals}
        for name in ('gate_visits','gate_facts','gate_corrections','gate_reviews','gate_handoffs','gate_repair_exits'):
            assert {c['name'] for c in inspect(migrated).get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
        SessionLocal.configure(bind=migrated);login(client)
        assert intake_cmd(client,'appointments',a,'arrive',values,key=key,version=version)==old_result
        intake_cmd(client,'appointments',a,'leave',{'reason':'升级后据实办理原到店离场','evidence_id':proof(client,a)})
        r=make(client,v);r=cmd(client,r,'arrive',actual(client,r,at(0)))
        r=cmd(client,r,'leave',actual(client,r,at(0)))
        with sqlite3.connect(path) as db:
            from app.backup_integrity import validate_sqlite
            assert validate(db)['verified_gate_visits']==1
            assert validate_sqlite(db)['integrity']=='ok'
        assert report(client)['metrics']['service_actual_arrivals']==2
    finally:
        SessionLocal.configure(bind=engine);migrated.dispose()


@pytest.mark.parametrize('field,value', [('checked_vin','LFV2A21K9J7654321'),('confirmed',False),('reason','被改写的额外离场')])
def test_cancelled_repair_exit_source_tampering_refused_in_restore_and_report(client,field,value):
    import json
    repair,v,_,_,_=normal(client);repair=repair_cmd(client,repair,'cancel',{'reason':'未开工取消，另记真实离场'})
    response=client.post(API+f'/repair-orders/{repair["id"]}/departure',json={'request_id':uuid.uuid4().hex,'version':repair['version'],'values':actual(client,{'vin':v['vin'],'case_id':repair['id']},at(0))})
    assert response.status_code==200,response.text;valid()
    with engine.begin() as db:
        row=db.execute(text("SELECT id, detail FROM flow_events WHERE case_id=:id AND action='gate_cancelled_repair_exit'"),{'id':repair['id']}).first()
        detail=__import__('json').loads(row.detail);detail[field]=value
        db.execute(text('UPDATE flow_events SET detail=:detail WHERE id=:id'),{'detail':json.dumps(detail),'id':row.id})
    with sqlite3.connect(engine.url.database) as db:
        with pytest.raises(ValueError,match='进出厂'):validate(db)
    assert not report(client)['complete'] and report(client)['metrics']['service_actual_departures']==0


def test_multiple_review_chain_corrected_handoff_and_cross_period_same_sources(client):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.config import settings
    r=entered(client)
    start=datetime.combine(today().replace(day=1),datetime.min.time(),ZoneInfo(settings.timezone))
    previous=(start-timedelta(minutes=10)).isoformat()
    r=correction(client,r,when=previous);login(client,'manager');r=review(client,r);login(client)
    rid=resource(client)['id']
    r=cmd(client,r,'handoff',{'checked_vin':r['vin'],'odometer_km':15,'evidence_id':evidence(client,{'id':r['case_id']}),'resource_id':rid,'problem':'沿纠正后原进厂转接检查',**slot()})
    a=client.get('/api/service-intake/appointments/'+str(r['handoff_appointment_id'])).json()
    assert a['arrived_at']==r['arrived_at']
    intake_cmd(client,'appointments',a,'leave',{'reason':'转维修接待后尚未开单实际离场','evidence_id':proof(client,a)})
    d=report(client,date_from=today().replace(day=1).isoformat(),date_to=today().isoformat())
    assert d['complete'] and d['metrics']['service_actual_arrivals']==0 and d['metrics']['service_actual_departures']==1
    csv_same(client,d,'service_gate_movements',date_from=today().replace(day=1).isoformat(),date_to=today().isoformat())
    assert valid()['verified_gate_handoffs']==1


def test_correction_cannot_extend_original_interval_over_a_subsequent_visit(client):
    v=vehicle(client);first=entered(client,make(client,v));first=cmd(client,first,'leave',actual(client,first,at(-3)))
    second=make(client,v)
    second=cmd(client,second,'arrive',actual(client,second,at(-2)))
    correction(client,first,'leave_time',at(-1),409)
    assert valid()['verified_gate_visits']==2


def test_two_distinct_reviewers_cannot_both_process_same_pending_correction(client):
    from tests.conftest import PASSWORD_HASH
    with SessionLocal() as db:
        user=User(username='gate-manager-two',display_name='另一独立复核主管',role='manager',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit()
    r=correction(client,entered(client));c=r['corrections'][-1]
    keyproof=evidence(client,{'id':r['case_id']})
    callers=[TestClient(app),TestClient(app)]
    try:
        login(callers[0],'manager');login(callers[1],'gate-manager-two')
        def run(caller):
            return caller.post(API+f'/corrections/{c["id"]}/actions/approve',json={'request_id':uuid.uuid4().hex,'version':c['version'],'values':{'reason':'本人独立核对原记录及新时点','evidence_id':keyproof}}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(run,callers))
        assert sorted(statuses)==[200,409],statuses
        assert valid()['verified_gate_corrections']==1
    finally:
        for caller in callers:caller.close()


def test_pending_correction_needs_nonnull_unique_database_reservation(client):
    from sqlalchemy.exc import IntegrityError
    r=correction(client,entered(client));c=r['corrections'][-1]
    with pytest.raises(IntegrityError):
        with engine.begin() as db:
            db.execute(text('UPDATE gate_corrections SET active_visit_id=NULL WHERE id=:id'),{'id':c['id']})
    assert valid()['verified_gate_corrections']==1
