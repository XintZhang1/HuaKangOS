"""Shared identity and selected customer exports must preserve the authorized population."""
import csv,io,uuid
from sqlalchemy import select
from app.db import SessionLocal,today
from app.flow_models import Case
from tests import test_customer_service as care,test_group_membership as group
from tests.test_multistore import second_store,switch
from tests.test_service_analytics import report
from tests.conftest import login


def delivered(customer,amount,store=1):
    owner=care.user_id('admin',store)
    with SessionLocal() as db:
        row=Case(store_id=store,number='CUSTOMER-'+uuid.uuid4().hex,kind='order',flow_version=2,state='delivered',
            title='合成客户 · 车辆订单',owner_id=owner,created_by=owner,customer_id=customer,amount_cents=amount,cost_cents=0,
            business_date=today(),completed_date=today(),data={})
        db.add(row);db.commit();return row.id


def test_customer_phone_is_not_identity_and_explicit_shared_link_groups_only_authorized_stores(client):
    one=care.customer(name='同名合成客户',phone='13900001111');two=care.customer(name='同名合成客户',phone='13900001111')
    delivered(one,10001);delivered(two,20002)
    data=report(client)
    assert data['metrics']['customer_period_count']==2
    assert data['metrics']['customer_period_amount_cents']==30003
    identity=group.link(client,{'customer_id':one})['identity_id']
    sid=second_store(client);switch(client,sid)
    third=care.customer(name='同名合成客户',phone='13900001111',store=sid);delivered(third,30003,sid)
    group.link(client,{'customer_id':third},identity)
    assert report(client)['metrics']['customer_period_amount_cents']==30003
    switch(client,'all');data=report(client)
    assert data['metrics']['customer_period_count']==2
    rows=data['tables']['customer_value']['rows'];shared=next(r for r in rows if r['customer_key']=='g'+str(identity))
    assert shared['amount_cents']==40004 and shared['values'][3]==2
    assert sum(r['amount_cents'] for r in data['tables']['customer_value_details']['rows'])==60006
    chart=next(c for c in data['charts'] if c['id']=='customer_value')
    assert sum(chart['series'][0]['values'])==60006
    switch(client,1);assert report(client)['metrics']['customer_period_amount_cents']==30003


def test_customer_vehicle_identity_dedup_conflicting_model_and_finance_cannot_open_private_history(client):
    care.vehicle(client,care.customer())
    sid=second_store(client);switch(client,sid)
    care.vehicle(client,care.customer(store=sid),model_name='第二店待核对车型')
    switch(client,'all');data=report(client)
    assert data['metrics']['customer_vehicle_identity_count']==1
    assert data['metrics']['customer_vehicle_relation_count']==2
    row=data['tables']['customer_vehicle_stats']['rows'][0]
    assert row['route'] is None and row['values'][1]=='车型资料待核对'
    chart=next(c for c in data['charts'] if c['id']=='customer_vehicle_stats')
    assert sum(chart['series'][0]['values'])==1
    switch(client,1);login(client,'finance');row=report(client)['tables']['customer_vehicle_stats']['rows'][0]
    assert row['route'] is None
    assert care.VIN not in str(row)


def test_selected_customer_csv_scope_and_unlinked_legacy_totals(client):
    one=care.customer();two=care.customer();a=delivered(one,12003);b=delivered(two,15004);delivered(None,22005)
    data=report(client);key='s1c'+str(one)
    assert data['metrics']['customer_period_amount_cents']+data['metrics']['customer_unlinked_amount_cents']==data['metrics']['delivery_cents']==49012
    r=client.get('/api/flow/analytics/export',params={'dataset':'customer_value_details','customer_key':key})
    assert r.status_code==200,r.text
    rows=list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
    assert len(rows)==2 and rows[1][0]==key and rows[1][-1]=='120.03'
    assert client.get('/api/flow/analytics/export',params={'dataset':'deliveries','customer_key':key}).status_code==422
    assert client.get('/api/flow/analytics/export',params={'dataset':'customer_value_details','customer_key':'g999999'}).status_code==404
    sid=second_store(client);switch(client,sid)
    assert client.get('/api/flow/analytics/export',params={'dataset':'customer_value_details','customer_key':key}).status_code==404
    switch(client,1);login(client,'inventory')
    assert client.get('/api/flow/analytics/export',params={'dataset':'customer_value_details','customer_key':key}).status_code==403
