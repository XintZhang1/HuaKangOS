"""One-screen customer and reservation entry retains native transaction guards."""
import uuid
from datetime import timedelta
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.flow_models import Customer,Case
from tests.conftest import login
from tests.test_vehicle_catalog import setup as catalog_setup,classify

API='/api/sales-quotes/orders'

def quote(client):
    _,series,model=catalog_setup(client);classify(client,series,model)
    return {'model_id':model['id'],'model_version':model['version'],'amount_cents':180001,
            'delivery_due':today().isoformat(),'valid_until':(today()+timedelta(days=7)).isoformat(),
            'terms':'试用客户确认的车辆约定','reason':'首次录入客户预订'}

def counts():
    with SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(Customer)),
                db.scalar(select(func.count()).select_from(Case)))

def test_new_customer_and_quote_commit_once_and_remain_unapproved(client):
    q=quote(client);login(client,'sales')
    body={'request_id':uuid.uuid4().hex,'customer_name':'预订试用客户','customer_phone':'','quote':q}
    first=client.post(API,json=body);assert first.status_code==201,first.text
    row=first.json();assert row['pending_quote_id'] and not row['active_quote_id']
    assert counts()==(1,1)
    replay=client.post(API,json=body);assert replay.status_code==201 and replay.json()['id']==row['id']
    assert counts()==(1,1)
    conflict=client.post(API,json={**body,'customer_name':'另一个客户'});assert conflict.status_code==409
    assert counts()==(1,1)
    with SessionLocal() as db:
        customer=db.scalar(select(Customer));assert customer.id==row['customer_id'] and customer.owner_id==row['owner_id']

def test_failed_or_stale_quote_does_not_leave_customer(client):
    q=quote(client);before=counts()
    r=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_name':'不应留存','quote':{**q,'model_version':q['model_version']+1}})
    assert r.status_code==409 and counts()==before
    r=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_name':'日期错误','quote':{**q,'valid_until':(today()-timedelta(days=1)).isoformat()}})
    assert r.status_code==422 and counts()==before

def test_duplicate_phone_requires_explicit_choice_and_never_overwrites(client):
    q=quote(client);base={'customer_name':'原客户','customer_phone':'13900009624','quote':q}
    r=client.post(API,json={'request_id':uuid.uuid4().hex,**base});assert r.status_code==201,r.text
    cid=r.json()['customer_id'];before=counts()
    body={'request_id':uuid.uuid4().hex,**base,'customer_name':'另建客户'}
    assert client.post(API,json=body).status_code==409 and counts()==before
    chosen=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_id':cid,'quote':q})
    assert chosen.status_code==201 and counts()[0]==1
    explicit=client.post(API,json={**body,'confirm_new_customer':True})
    assert explicit.status_code==201 and counts()[0]==2
    with SessionLocal() as db:assert db.get(Customer,cid).name=='原客户'

def test_wrong_role_and_other_store_model_refuse_without_orphan(client):
    q=quote(client);before=counts();login(client,'inventory')
    assert client.post(API,json={'request_id':uuid.uuid4().hex,'customer_name':'越权客户','quote':q}).status_code==403
    login(client);sid=client.post('/api/stores',json={'code':'NEW-SIMPLE','name':'独立测试店','active':True}).json()['id']
    client.headers['X-Store-ID']=str(sid)
    r=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_name':'跨店客户','quote':q})
    assert r.status_code in (404,409,422) and counts()==before

def test_cannot_select_another_salespersons_customer(client):
    q=quote(client)
    r=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_name':'管理员负责客户','quote':q});assert r.status_code==201
    before=counts();login(client,'sales')
    r=client.post(API,json={'request_id':uuid.uuid4().hex,'customer_id':r.json()['customer_id'],'customer_name':'管理员负责客户','quote':q})
    assert r.status_code in (403,404) and counts()==before

def test_case_customer_filter_intersects_employee_scope(client):
    q=quote(client)
    rows=[client.post(API,json={'request_id':uuid.uuid4().hex,'customer_name':name,'quote':q}).json() for name in ['甲客户','乙客户']]
    result=client.get('/api/flow/cases',params={'customer_id':rows[0]['customer_id'],'kind':'order'}).json()
    assert [r['id'] for r in result['items']]==[rows[0]['id']]
    login(client,'sales');result=client.get('/api/flow/cases',params={'customer_id':rows[0]['customer_id']}).json()
    assert result['items']==[] and result['total']==0
