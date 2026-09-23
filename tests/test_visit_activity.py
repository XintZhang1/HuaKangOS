"""Actual events, local periods, paired visits, missing history and scoped export."""
import csv,io,uuid
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select,text
from app.db import SessionLocal,engine,today
from app.config import settings
from app.models import User,Store,UserStore
from app.flow_models import Case,FlowEvent
from tests.conftest import login
from tests.test_workflow import create,action,evidence
from tests.test_repair_orders import technician,cmd as repair_cmd,setup as repair_setup,ready,allocate,receive
from tests.test_service_intake import customer_vehicle,resource,appointment,arrive,convert,normal,work_quote,released,request_rework,approve_rework,convert_rework,cmd as intake_cmd,proof
from tests.test_procurement import bank
API='/api/visit-activity-reports'

def report(c,**params):
    r=c.get(API,params=params);assert r.status_code==200,r.text;return r.json()

def csv_same(c,d,key,**params):
    r=c.get(API+'/export/'+key,params=params);assert r.status_code==200,r.text
    actual=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))));t=d['tables'][key]
    assert actual==[t['headers']]+[[str(v) for v in row['values']] for row in t['rows']]

def lead(c,assignee='sales'):
    row=create(c,'lead',{'customer_name':'合成实际跟进客户','customer_phone':'13900000992','source':'展厅到店'})
    with SessionLocal() as db:uid=db.scalar(select(User.id).where(User.username==assignee))
    return action(c,row,'assign',{'assignee_id':uid})

def test_real_contact_events_not_tasks_or_current_conversion_and_csv(client):
    row=lead(client);assert report(client)['metrics']['presales_contact_events']==0
    login(client,'sales');row=action(client,row,'remind',{'result':'实际沟通预算与车型，下周再联系','due_date':today().isoformat()})
    row=action(client,row,'intent',{'need':'明确家庭用车需求','due_date':today().isoformat()})
    key=uuid.uuid4().hex;version=row['version'];v={'result':'本次确认到店看车时间','due_date':today().isoformat()}
    row=action(client,row,'follow',v,request_id=key,version=version)
    assert action(client,row,'follow',v,request_id=key,version=version)==row
    action(client,row,'follow',v,status=409,version=version)
    row=action(client,row,'close',{'reason':'客户本次暂缓购车','no_contact':False});row=action(client,row,'reopen',{'reason':'客户主动再次咨询','due_date':today().isoformat()})
    d=report(client);assert d['metrics']['presales_contact_events']==3 and d['metrics']['presales_contact_cases']==1
    assert len(d['tables']['presales_transitions']['rows'])==2
    assert sum(d['charts'][0]['series'][0]['values'])==sum(r['count'] for r in d['tables']['presales_activity']['rows'])==3
    for name in d['tables']:csv_same(client,d,name)
    assert '员工排行' not in str(d) and 'actual_cash' not in str(d)

def test_booking_no_show_and_cancel_not_arrival_actual_leave_is_once(client):
    v,_=customer_vehicle(client);res=resource(client);a=appointment(client,v,res)
    assert report(client)['metrics']['service_actual_arrivals']==0
    a=intake_cmd(client,'appointments',a,'cancel',{'reason':'客户尚未到店明确取消'})
    assert report(client)['tables']['service_gate_movements']['rows']==[]
    a=arrive(client,appointment(client,v,res));d=report(client);assert d['metrics']['service_actual_arrivals']==1 and d['metrics']['service_actual_departures']==0
    version=a['version'];key=uuid.uuid4().hex;v={'reason':'客户未开单实际离场','evidence_id':proof(client,a)}
    ended=intake_cmd(client,'appointments',a,'leave',v,version=version,key=key)
    assert intake_cmd(client,'appointments',a,'leave',v,version=version,key=key)==ended
    intake_cmd(client,'appointments',a,'leave',v,version=version,status=409)
    d=report(client);assert d['complete'] and d['metrics']['service_actual_departures']==1
    assert d['tables']['service_visit_cohort']['rows'][0]['closed']
    for name in ('service_gate_movements','service_visit_cohort'):csv_same(client,d,name)

def test_convert_and_cancel_repair_never_fabricate_departure(client):
    row,_,_,_,_=normal(client);repair_cmd(client,row,'cancel',{'reason':'实际到店后未开工取消，离场尚无事实'})
    d=report(client);assert d['metrics']['service_actual_arrivals']==1 and d['metrics']['service_actual_departures']==0
    assert d['metrics']['service_arrival_cohort_without_departure']==1
    assert '尚无实际离场' in str(d['tables']['service_visit_cohort'])
    assert report(client,case_id=row['id'])['metrics']['service_actual_arrivals']==1

def test_local_month_boundary_does_not_rewrite_arrival_cohort(client):
    row,_,_,a,_=normal(client);row,_=work_quote(client,row);row=repair_cmd(client,row,'start',{'result':'真实开工'})
    row=released(client,row);day=today().replace(day=1)-timedelta(days=1)
    local=datetime.combine(day,datetime.min.time()).replace(hour=0,minute=30,tzinfo=ZoneInfo(settings.timezone));stamp=local.astimezone(timezone.utc).replace(tzinfo=None)
    with engine.begin() as db:db.execute(text('UPDATE intake_arrivals SET occurred_at=:at WHERE appointment_id=:id'),{'at':stamp,'id':a['id']})
    old=report(client,date_from=day.isoformat(),date_to=day.isoformat());assert old['metrics']['service_actual_arrivals']==1 and old['metrics']['service_actual_departures']==0
    assert old['tables']['service_visit_cohort']['rows'][0]['values'][4]=='无记录'
    current=report(client,date_from=today().isoformat(),date_to=today().isoformat());assert current['metrics']['service_actual_arrivals']==0 and current['metrics']['service_actual_departures']==1
    assert current['tables']['service_visit_cohort']['rows']==[] and current['complete']
    csv_same(client,old,'service_visit_cohort',date_from=day.isoformat(),date_to=day.isoformat())

def test_rework_actual_arrival_has_distinct_source_not_duplicate_convert(client):
    original,v,res,_,_=normal(client);original,_=work_quote(client,original);original=repair_cmd(client,original,'start',{'result':'原单实际开工'});original=released(client,original)
    r=approve_rework(client,request_rework(client,original,v,res));row=convert_rework(client,r)
    row,_=work_quote(client,row,500);row=repair_cmd(client,row,'start',{'result':'原责任项目再次实际施工'});row=released(client,row,True)
    d=report(client);assert d['complete'] and d['metrics']['service_actual_arrivals']==d['metrics']['service_actual_departures']==2
    assert len(d['tables']['service_visit_cohort']['rows'])==2
    assert sum(d['charts'][1]['series'][0]['values'])==4
    assert '原单返修' in str(d['tables']['service_gate_movements'])

def test_older_repair_actual_release_without_arrival_stays_explicit_gap(client):
    row,item,work,_=repair_setup(client);row=ready(client,row,item,work);row=allocate(client,row);row=receive(client,row,row['allocations'][0],row['amount_cents'],bank(client));row=repair_cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    d=report(client);assert not d['complete'] and d['metrics']['service_actual_arrivals']==0 and d['metrics']['service_actual_departures']==1
    assert '不推算进厂或停留时长' in str(d['tables']['visit_source_issues']) and not d['tables']['service_visit_cohort']['rows']

def test_proof_or_binding_tamper_is_visible_and_not_counted(client):
    row,vehicle,_,a,_=normal(client)
    with engine.begin() as db:db.execute(text("UPDATE intake_vehicle_bindings SET vin='LFV2A21K9J9999999' WHERE case_id=:id"),{'id':row['id']})
    d=report(client,case_id=row['id']);assert not d['complete'] and d['metrics']['service_actual_arrivals']==0
    assert '绑定不一致' in str(d['tables']['visit_source_issues'])
    with engine.begin() as db:db.execute(text('UPDATE intake_vehicle_bindings SET vin=:vin WHERE case_id=:id'),{'vin':vehicle['vin'],'id':row['id']})
    row,_=work_quote(client,row);row=repair_cmd(client,row,'start',{'result':'实际开工'});row=released(client,row)
    assert report(client,case_id=row['id'])['metrics']['service_actual_departures']==1
    with engine.begin() as db:db.execute(text("DELETE FROM flow_events WHERE case_id=:id AND action='repair_v4_release'"),{'id':row['id']})
    d=report(client,case_id=row['id']);assert not d['complete'] and d['metrics']['service_actual_departures']==0
    assert '缺少该版本唯一实际接车事件' in str(d['tables']['visit_source_issues'])

def test_roles_scope_aggregate_privacy_and_invalid_period(client):
    row=lead(client);login(client,'sales');action(client,row,'remind',{'result':'私有沟通内容，不能集团明细披露','due_date':today().isoformat()})
    login(client);repair,_,_,_,_=normal(client)
    assert '私有沟通内容' in str(report(client)['tables']['presales_activity'])
    with SessionLocal() as db:
        db.add(Store(id=2,code='SECOND',name='第二合成门店'));db.flush();admin=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=admin.id,store_id=2));db.commit()
    client.headers['X-Store-Id']='2';assert report(client)['metrics']['presales_contact_events']==0
    assert client.get(API,params={'case_id':row['id']}).status_code==404
    assert client.get(API+'/export/presales_activity',params={'case_id':row['id']}).status_code==404
    second=lead(client,'admin');action(client,second,'remind',{'result':'另店真实记录','due_date':today().isoformat()})
    client.headers['X-Store-Id']='all';d=report(client);assert d['metrics']['presales_contact_events']==2
    assert '私有沟通内容' not in str(d) and 'LFV2A21K9J1234567' not in str(d)
    assert all(not r.get('route') for t in d['tables'].values() for r in t['rows'])
    client.headers['X-Store-Id']='1';login(client,'sales');d=report(client);assert d['metrics']['presales_contact_events']==1 and d['metrics']['service_actual_arrivals']==0
    login(client,'technician');assert client.get(API).status_code==403 and client.get(API+'/export/service_gate_movements').status_code==403
    login(client);assert client.get(API,params={'date_from':today().isoformat(),'date_to':(today()-timedelta(days=1)).isoformat()}).status_code==422
    assert client.get(API,params={'date_to':(today()+timedelta(days=1)).isoformat()}).status_code==422
    assert client.get(API+'/export/no_such_table').status_code==404

def test_csv_formula_and_source_limit_are_explicit(client,monkeypatch):
    row=lead(client);login(client,'sales');action(client,row,'remind',{'result':'=1+2','due_date':today().isoformat()})
    response=client.get(API+'/export/presales_activity');assert response.status_code==200 and "'=1+2" in response.content.decode('utf-8-sig')
    import app.inventory_report_common as common
    monkeypatch.setattr(common,'LIMIT',0)
    response=client.get(API);assert response.status_code==422 and '未返回截断统计' in response.text
