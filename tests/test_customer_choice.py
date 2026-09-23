"""A telephone match is a suggestion, never customer identity or permission."""
import uuid
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import User,Store,UserStore
from app.flow_models import Customer,Case
from app.group_models import GroupIdentityLink
from app.tenancy import set_scope,project_user
from tests.conftest import login

PHONE='13900007654'
def create(c,values=None,status=201,key=None):
    v={'model':'纯合成测试车型','amount':'10.00','delivery_due':today().isoformat(),**(values or {})}
    r=c.post('/api/flow/cases',json={'request_id':key or uuid.uuid4().hex,'kind':'order','values':v});assert r.status_code==status,r.text;return r.json()
def matches(c,phone=PHONE):
    r=c.get('/api/customer-choice/matches',params={'phone':phone});assert r.status_code==200,r.text;return r.json()['items']

def test_same_name_and_phone_requires_explicit_existing_or_independent_new(client):
    first=create(client,{'customer_name':'同名测试客户','customer_phone':PHONE})
    create(client,{'customer_name':'同名测试客户','customer_phone':PHONE},409)
    candidates=matches(client);assert len(candidates)==1 and candidates[0]['id']==first['customer_id']
    again=create(client,{'customer_id':first['customer_id']});assert again['customer_id']==first['customer_id']
    separate=create(client,{'customer_name':'同名测试客户','customer_phone':PHONE,'confirm_new_customer':True});assert separate['customer_id']!=first['customer_id']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Customer))==2
        assert db.scalar(select(func.count()).select_from(Case))==3
        # New local records are not automatically assigned shared identities.
        from app.group_service import authority
        u=project_user(db.scalar(select(User).where(User.username=='admin')),'admin');set_scope(db,[1],1)
        with authority(db,u,{'admin'}):assert db.scalar(select(func.count()).select_from(GroupIdentityLink))==0

def test_selected_customer_rejects_conflicting_name_phone_and_preserves_preferences(client):
    first=create(client,{'customer_name':'准确原客户','customer_phone':PHONE})
    with SessionLocal() as db:
        row=db.scalar(select(Customer).where(Customer.id==first['customer_id']));row.contact_allowed=False;row.note='客户明确不希望后续联系';db.commit()
    for v in ({'customer_name':'另一个人'},{'customer_phone':'13999991234'},{'confirm_new_customer':True}):create(client,{'customer_id':first['customer_id'],**v},422)
    again=create(client,{'customer_id':first['customer_id'],'customer_name':'准确原客户','customer_phone':PHONE})
    with SessionLocal() as db:
        row=db.scalar(select(Customer).where(Customer.id==again['customer_id']));assert row.contact_allowed is False and row.note=='客户明确不希望后续联系'

def test_no_phone_same_name_creates_independent_customers_and_no_prompt(client):
    first=create(client,{'customer_name':'无电话同名'});second=create(client,{'customer_name':'无电话同名'})
    assert first['customer_id']!=second['customer_id'] and matches(client,'')==[]
    create(client,{'customer_phone':PHONE},422)

def test_owner_restriction_hides_other_employee_even_same_phone(client):
    hidden=create(client,{'customer_name':'不属于销售的客户','customer_phone':PHONE})
    login(client,'sales');assert matches(client)==[]
    create(client,{'customer_id':hidden['customer_id']},404)
    own=create(client,{'customer_name':'销售本人核对新客户','customer_phone':PHONE})
    assert [r['id'] for r in matches(client)]==[own['customer_id']]
    assert client.get('/api/customer-choice/matches',params={'q':'不属于销售'}).json()['items']==[]
    login(client,'admin');assert len(matches(client))==2

def test_cross_store_and_aggregate_and_non_customer_roles_rejected(client):
    first=create(client,{'customer_name':'甲店客户','customer_phone':PHONE})
    client.post('/api/stores',json={'code':'CHOICE-B','name':'合成客户乙店'});client.headers['X-Store-ID']='2'
    assert matches(client)==[];create(client,{'customer_id':first['customer_id']},404)
    client.headers['X-Store-ID']='all';assert client.get('/api/customer-choice/matches',params={'phone':PHONE}).status_code==409
    client.headers['X-Store-ID']='1';login(client,'inventory');assert client.get('/api/customer-choice/matches',params={'phone':PHONE}).status_code==403

def test_explicit_selection_case_request_is_idempotent_without_new_customer(client):
    first=create(client,{'customer_name':'重复请求客户','customer_phone':PHONE});key=uuid.uuid4().hex
    one=create(client,{'customer_id':first['customer_id']},key=key);two=create(client,{'customer_id':first['customer_id']},key=key);assert one['id']==two['id']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Customer))==1

def test_master_create_never_overwrites_existing_customer_preferences(client):
    values={'name':'原档案客户','phone':PHONE,'contact_allowed':False,'note':'原先明确不联系'}
    r=client.post('/api/flow/master/customers',json={'values':values});assert r.status_code==201,r.text;original=r.json()['id']
    r=client.post('/api/flow/master/customers',json={'values':{**values,'contact_allowed':True,'note':'另一独立档案'}});assert r.status_code==409,r.text
    r=client.post('/api/flow/master/customers',json={'values':{**values,'confirm_new_customer':True,'contact_allowed':True,'note':'另一独立档案'}});assert r.status_code==201,r.text
    assert r.json()['id']!=original
    with SessionLocal() as db:
        row=db.scalar(select(Customer).where(Customer.id==original));assert row.contact_allowed is False and row.note=='原先明确不联系'

def test_v1_resolution_keeps_its_historical_version_dispatch(client):
    from app.flow_engine import customer_for,new_case
    from app.flow_specs import flow_spec
    with SessionLocal() as db:
        set_scope(db,[1],1);u=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
        one=customer_for(db,u,{'customer_name':'历史明确v1','customer_phone':PHONE},flow_version=1)
        two=customer_for(db,u,{'customer_name':'历史明确v1','customer_phone':PHONE},flow_version=1);assert one.id==two.id
    assert next(f for f in flow_spec('order',1)['fields'] if f['key']=='customer_name')['required']
    assert 'customer_id' not in {f['key'] for f in flow_spec('order',1)['fields']}

def test_reception_matches_and_selected_ids_are_owner_scoped(client):
    from tests.conftest import PASSWORD_HASH
    hidden=create(client,{'customer_name':'主管负责的客户','customer_phone':PHONE})
    with SessionLocal() as db:
        user=User(username='choice-reception',display_name='合成接待',role='reception',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1,role='reception'));db.commit()
    login(client,'choice-reception');assert matches(client)==[]
    values={'customer_id':hidden['customer_id'],'source':'展厅到店'}
    r=client.post('/api/flow/cases',json={'request_id':uuid.uuid4().hex,'kind':'lead','values':values});assert r.status_code==404,r.text
    values={'customer_name':'接待本人新客户','customer_phone':PHONE,'source':'展厅到店'}
    r=client.post('/api/flow/cases',json={'request_id':uuid.uuid4().hex,'kind':'lead','values':values});assert r.status_code==201,r.text
    assert [m['id'] for m in matches(client)]==[r.json()['customer_id']]
