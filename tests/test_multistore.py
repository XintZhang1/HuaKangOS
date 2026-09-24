"""Cross-store authorization and reporting regression tests."""
from datetime import timedelta
import json
import pytest
from sqlalchemy import select
from app.db import SessionLocal, today
from app.models import Store, User, UserStore, Feedback, DailyReport
from app.reports import generate_report
from app.tenancy import set_scope
from tests.conftest import login, PASSWORD
from tests.test_app import create, car, vehicle_body, cash_body, sale_body, approve


def second_store(client):
    r=client.post('/api/stores',json={'code':'EAST','name':'东店测试','active':True})
    assert r.status_code==201,r.text
    return r.json()['id']


def assign(username,ids):
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.username==username))
        for i in ids:
            if not db.get(UserStore,(u.id,i)):db.add(UserStore(user_id=u.id,store_id=i))
        db.commit()


def switch(client,id):client.headers['X-Store-ID']=str(id)


def test_multistore_separate_records_and_combined_readonly(client):
    two=second_store(client)
    first=car(client)
    switch(client,two)
    second=car(client,vin='LDD00000000000002')  # same document no allowed in another store
    assert second['store_id']==two and first['store_id']==1
    assert client.get('/api/records/vehicles').json()['total']==1
    assert client.get(f'/api/records/vehicles/{first["id"]}').status_code==404
    assert 'LDD00000000000001' not in client.get('/api/export/vehicles').text
    switch(client,'all')
    assert client.get('/api/records/vehicles').json()['total']==2
    r=client.post('/api/records/vehicles',json=vehicle_body(doc_no='third',vin='LDD00000000000003'))
    assert r.status_code==409,r.text
    assert client.post('/api/reports/generate',json={'business_date':str(today()),'use_ai':False}).status_code==409
    assert client.get('/api/dashboard').json()['store_ids']==[1,two]


@pytest.mark.parametrize('path',['/api/records/vehicles','/api/lookup/vehicles','/api/export/vehicles','/api/dashboard','/api/reports','/api/findings','/api/audit','/api/flow/cases'])
def test_explicit_unauthorized_store_is_denied(client,path):
    two=second_store(client);login(client,'manager');switch(client,two)
    assert client.get(path).status_code==403


@pytest.mark.parametrize('header',['0','-1','9999','nan','1 OR 1=1','1,2'])
def test_invalid_or_unknown_store_headers(client,header):
    switch(client,header);response=client.get('/api/records/vehicles')
    if header in {'0','-1','9999'}:
        # A store that does not exist is a stale page context, not a permission problem: the page
        # has to tell the employee to pick another store (XC-ISSUE-002).
        assert response.status_code==409,response.text
        assert '当前门店已停用或不存在' in response.json()['detail']
    else:
        assert response.status_code in {403,422}


def test_staff_cannot_forge_store_or_use_all(client):
    two=second_store(client);assign('inventory',[two]);login(client,'inventory')
    assert client.post('/api/records/vehicles',json=vehicle_body(store_id=two)).status_code==422
    switch(client,'all');assert client.get('/api/records/vehicles').status_code==403


def test_cross_store_sale_and_cash_links_denied(client):
    first=car(client);two=second_store(client);switch(client,two)
    assert client.post('/api/records/sales',json=sale_body(first['id'])).status_code==422
    switch(client,1);s=approve(client,'sales',sale_body(first['id']))
    switch(client,two)
    body=cash_body(direction='in',category='sale_collection',related_type='sales',related_id=s['id'])
    assert client.post('/api/records/cash',json=body).status_code==422


def test_granted_store_switch_does_not_leak_previous_scope(client):
    one=car(client);two=second_store(client);switch(client,two);other=car(client,vin='LDD00000000000002')
    assign('manager',[two]);switch(client,1);login(client,'manager')
    for _ in range(4):
        switch(client,1);assert [r['id'] for r in client.get('/api/records/vehicles').json()['items']]==[one['id']]
        switch(client,two);assert [r['id'] for r in client.get('/api/records/vehicles').json()['items']]==[other['id']]


def test_reports_per_store_and_api_visibility(client):
    car(client);two=second_store(client);switch(client,two);car(client,vin='LDD00000000000002')
    a=generate_report(today(),False,store_id=1);b=generate_report(today(),False,store_id=two)
    assert a!=b
    assert generate_report(today(),False,store_id=1)==a
    assert client.get(f'/api/reports/{a}').status_code==404
    assert client.get('/api/reports').json()['total']==1
    assert client.get(f'/api/reports/{b}').json()['store_id']==two
    switch(client,'all');assert client.get('/api/reports').json()['total']==2


def test_empty_store_report_keys_do_not_collide(client):
    two=second_store(client)
    a=generate_report(today(),False,store_id=1);b=generate_report(today(),False,store_id=two)
    with SessionLocal() as db:
        assert db.get(DailyReport,a).store_id==1
        assert db.get(DailyReport,b).store_id==two


def test_dashboard_comparison_uses_each_store_not_union(client):
    approve(client,'cash',cash_body(amount='100.00'))
    two=second_store(client);switch(client,two);approve(client,'cash',cash_body(amount='200.00'))
    switch(client,'all');data=client.get('/api/dashboard').json()
    metrics=[item['metrics'] for item in data['by_store']]
    assert len(metrics)==2 and metrics[0]!=metrics[1]
    assert '10000' in json.dumps(metrics[0]) and '20000' in json.dumps(metrics[1])


def test_nonadmin_cannot_see_global_account_audit(client):
    second_store(client);login(client,'manager')
    assert all(r['entity_type'] not in {'users','stores','feedback','maintenance'} for r in client.get('/api/audit').json()['items'])


def test_create_employee_with_multiple_stores(client):
    two=second_store(client)
    body={'username':'new-sales','display_name':'测试员工','password':PASSWORD,'role':'sales','store_ids':[1,two]}
    r=client.post('/api/users',json=body);assert r.status_code==201,r.text
    assert r.json()['store_ids']==[1,two] and r.json()['must_change_password']
    assert 'password_hash' not in r.text


@pytest.mark.parametrize('ids',[[],[9999],[-1]])
def test_invalid_employee_membership_rejected(client,ids):
    r=client.post('/api/users',json={'username':'bad-membership','display_name':'测试','password':PASSWORD,'role':'sales','store_ids':ids})
    assert r.status_code==422
    assert all(u['username']!='bad-membership' for u in client.get('/api/users').json()['items'])


def test_role_membership_change_revokes_session(client):
    two=second_store(client);assign('manager',[two])
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as staff:
        login(staff,'manager')
        u=next(u for u in client.get('/api/users').json()['items'] if u['username']=='manager')
        r=client.put('/api/users/'+str(u['id']),json={'request_id':'membership-change-1','access_version':u['access_version'],'display_name':'店长','role':'manager','active':True,'store_ids':[two]})
        assert r.status_code==200
        assert staff.get('/api/dashboard').status_code==401
        info=login(staff,'manager');assert info['active_store_id']==two


def test_store_disable_denies_assigned_staff_and_last_store_guard(client):
    assert client.put('/api/stores/1',json={'code':'MAIN','name':'门店','active':False}).status_code==409
    two=second_store(client)
    assert client.put('/api/stores/1',json={'code':'MAIN','name':'门店','active':False}).status_code==200
    client.headers.pop('X-Store-ID',None);login(client,'manager')
    assert client.get('/api/records/vehicles').status_code==403


def test_staff_cannot_create_stores_accounts_or_read_controller_status(client):
    login(client,'sales')
    assert client.post('/api/stores',json={'code':'NO','name':'非法','active':True}).status_code==403
    assert client.get('/api/users').status_code==403
    assert client.get('/api/maintenance/status').status_code==404


def test_removed_feedback_routes_all_scopes(client):
    for sid in (1, "all"):
        switch(client,sid)
        assert client.get("/api/feedback").status_code==404
        assert client.post("/api/feedback",json={}).status_code==404

def test_removed_maintenance_endpoint(client):
    assert client.get("/api/maintenance/status").status_code==404
