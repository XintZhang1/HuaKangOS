"""Regression guards where new workflows meet existing entry points and reports."""
from dataclasses import replace
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User
from app.flow_models import Case,Task,Item
from tests.conftest import login
from tests.test_app import car,vehicle_body
from tests.test_multistore import switch


def test_default_vehicle_entry_is_read_only_in_api_and_employee_metadata(client,monkeypatch):
    vehicle=car(client)
    import app.main as main
    import app.security as security
    monkeypatch.setattr(main,'settings',replace(main.settings,legacy_business_write=False))
    monkeypatch.setattr(security,'settings',replace(security.settings,legacy_business_write=False))
    assert 'vehicles' not in client.get('/api/auth/me').json()['write_modules']
    assert client.post('/api/records/vehicles',json=vehicle_body(doc_no='DUP',vin='LDD00000000000002')).status_code==409
    assert client.put('/api/records/vehicles/'+str(vehicle['id']),json={'version':vehicle['version'],'data':vehicle_body()}).status_code==409
    assert client.post('/api/records/vehicles/'+str(vehicle['id'])+'/actions/void',json={'version':vehicle['version'],'reason':'原事实不能裸作废'}).status_code==409
    assert client.get('/api/records/vehicles/'+str(vehicle['id'])).status_code==200


def test_inventory_legacy_and_master_views_cannot_bypass_cost_redaction(client):
    vehicle=car(client)
    with SessionLocal() as db:
        item=Item(sku='PRIVATE-COST',name='合成物资',quantity_milli=1000,inventory_value_cents=101);db.add(item);db.commit()
    login(client,'inventory')
    detail=client.get('/api/records/vehicles/'+str(vehicle['id'])).json()
    assert all(k not in detail for k in ['purchase_cost','purchase_cost_cents','list_price','list_price_cents','note'])
    entry=client.get('/api/flow/master/items').json()['items'][0]
    assert 'inventory_value_cents' not in entry and 'unit_cost_cents' not in entry
    assert entry['quantity']==entry['available_quantity']=='1' and entry['reserved_quantity']=='0'


def case(kind='repair',version=3):
    with SessionLocal() as db:
        actor=db.scalar(select(User.id).where(User.username=='admin'))
        row=Case(number='CASE-PRIVATE',kind=kind,flow_version=version,title='客户服务私密内容',state='pending',
            owner_id=actor,created_by=actor,business_date=today(),due_date=today())
        db.add(row);db.flush()
        if kind=='customer_care':db.add(Task(case_id=row.id,key='care_private',title='私密服务跟进',role='manager',assignee_id=actor,due_date=today()))
        db.commit();return row.id


def test_external_procurement_contract_category_is_private_and_not_a_generated_signature(client):
    key=case()
    response=client.post(f'/api/flow/cases/{key}/files',data={'category':'procurement_contract'},files={'file':('合成采购核价.txt','虚构核价记录'.encode(),'text/plain')})
    assert response.status_code==200,response.text
    file_id=response.json()['id']
    login(client,'service')
    response=client.get('/api/flow/files/'+str(file_id));assert response.status_code in {403,404}
    assert client.post(f'/api/flow/cases/{key}/files',data={'category':'procurement_contract'},files={'file':('低岗尝试.txt',b'test','text/plain')}).status_code==403
    login(client,'finance');assert client.get('/api/flow/files/'+str(file_id)).status_code==200


def test_finance_and_group_charts_do_not_leak_private_care_task_titles(client):
    key=case('customer_care',2)
    local=client.get('/api/flow/analytics').json();assert local['metrics']['task_count']==1
    login(client,'finance')
    report=client.get('/api/flow/analytics');assert report.status_code==200
    assert '私密服务' not in report.text and '客户服务私密内容' not in report.text
    assert report.json()['metrics']['task_count']==len(report.json()['tables']['tasks']['rows'])==0
    assert client.get('/api/flow/cases/'+str(key)).status_code==404
    login(client);switch(client,'all')
    report=client.get('/api/flow/analytics');assert report.status_code==200
    assert '私密服务' not in report.text and report.json()['metrics']['task_count']==0
