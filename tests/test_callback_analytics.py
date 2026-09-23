"""Registered old/new callbacks reconcile cohort, privacy, charts and CSV."""
import csv,io,uuid
from datetime import timedelta
from sqlalchemy import select
from app.db import SessionLocal,today
from app.flow_models import Case
from tests.conftest import login
from tests import test_customer_service as care
from tests import test_workflow as flow
from tests.test_multistore import second_store,switch


def callback(client,subtype='sales_callback',store=1,topic='私密回访主题-SECRET'):
    actor=care.user_id('customer_service',store)
    customer=care.customer(name='私密回访客户-NAME',phone='13900007878',owner='customer_service',store=store)
    with SessionLocal() as db:
        source=Case(store_id=store,kind='order' if subtype=='sales_callback' else 'repair',flow_version=2,
                    state='delivered' if subtype=='sales_callback' else 'completed',number='CALLBACK-SOURCE-'+uuid.uuid4().hex,
                    title='已完成合成原单',owner_id=actor,created_by=actor,customer_id=customer,business_date=today(),data={})
        db.add(source);db.commit();source_id=source.id
    login(client,'customer_service')
    return care.care(client,customer,subtype=subtype,assignee='customer_service',source_case_id=source_id,topic=topic)


def report(client,**params):
    response=client.get('/api/flow/analytics',params=params);assert response.status_code==200,response.text
    data=response.json();table=data['tables']['callbacks'];chart=next(c for c in data['charts'] if c['id']=='callback_state')
    count=sum(row['count'] for row in table['rows'])
    assert count==sum(chart['series'][0]['values'])==data['metrics']['callback_task_count']
    response=client.get('/api/flow/analytics/export',params={**params,'dataset':'callbacks'});assert response.status_code==200,response.text
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers'] and sum(int(row[-1]) for row in rows[1:])==count
    return data,table


def test_new_sales_repair_and_old_callbacks_share_one_cohort_not_followup_count(client):
    sale=callback(client);sale=care.action(client,sale,'start')['case']
    for _ in range(3):sale=care.action(client,sale,'followup',{'channel':'internal','contact_result':'progress','note':'仅虚构跟进原文-SECRET'})['case']
    sale=care.action(client,sale,'close',{'result':'resolved','note':'客户当面确认结果'})['case']
    repair=callback(client,'repair_callback');repair=care.action(client,repair,'cancel',{'reason':'客户暂不需要本次回访'})['case']
    legacy=flow.create(client,'callback',{'customer_name':'虚构旧回访客户','customer_phone':'13900007676','topic':'旧流程回访','due_date':today().isoformat()})
    flow.action(client,legacy,'callback_done',{'result':'虚构客户已核对'})
    care.care(client,care.customer(),subtype='consultation',assignee='customer_service')
    login(client,'manager');data,table=report(client)
    assert data['metrics']['callback_task_count']==3
    assert data['metrics']['callback_completed_count']==2 and data['metrics']['callback_cancelled_count']==1
    assert {r['route']['id'] for r in table['rows']}=={sale['id'],repair['id'],legacy['id']}
    assert all(client.get('/api/flow/cases/'+str(r['route']['id'])).status_code==200 for r in table['rows'])
    assert any('销售回访' in r['values'][2] and r['values'][-2]=='已解决' for r in table['rows'])
    # Date selects the creation cohort, not the latest followup/close date.
    with SessionLocal() as db:
        original=db.scalar(select(Case).where(Case.id==sale['id']));original.business_date=today()-timedelta(days=40);db.commit()
    assert report(client)[0]['metrics']['callback_task_count']==2
    assert report(client,date_from=(today()-timedelta(days=40)).isoformat(),date_to=(today()-timedelta(days=40)).isoformat())[0]['metrics']['callback_task_count']==1


def test_finance_and_group_summary_count_new_callbacks_without_granting_records(client):
    first=callback(client);login(client);other=second_store(client);switch(client,other)
    second=callback(client,'repair_callback',other);login(client);switch(client,1)
    assert report(client)[0]['metrics']['callback_task_count']==1
    login(client,'finance');data,table=report(client)
    assert data['metrics']['callback_task_count']==1 and all(r['route'] is None for r in table['rows'])
    for secret in ['私密回访主题-SECRET','私密回访客户-NAME','13900007878',first['number']]:assert secret not in str(table)
    assert client.get('/api/customer-service/cases/'+str(first['id'])).status_code==403
    assert client.get('/api/flow/cases/'+str(first['id'])).status_code==404
    login(client);switch(client,'all');data,table=report(client)
    assert data['metrics']['callback_task_count']==2 and all(r['route'] is None for r in table['rows'])
    assert first['number'] not in str(table) and second['number'] not in str(table)
    switch(client,other);data,table=report(client)
    assert data['metrics']['callback_task_count']==1 and table['rows'][0]['route']['id']==second['id']
    switch(client,1);login(client,'sales');assert client.get('/api/flow/analytics').status_code==403


def test_callback_command_replay_counts_once_and_stale_action_does_not_change_chart(client):
    row=callback(client);request_id=uuid.uuid4().hex
    started=care.action(client,row,'start',request_id=request_id)['case']
    assert care.action(client,row,'start',request_id=request_id)['case']==started
    care.action(client,row,'cancel',{'reason':'旧版本取消必须拒绝'},status=409)
    login(client,'manager');data,_=report(client)
    assert data['metrics']['callback_task_count']==1 and data['metrics']['callback_cancelled_count']==0
