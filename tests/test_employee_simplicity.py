import io
import uuid
from PIL import Image
from sqlalchemy import select
from app.db import SessionLocal,today
from app.flow_models import Customer,Task
from app.models import User
from tests.conftest import login
from tests.test_workflow import create,action,detail

def lead(c):
    x=create(c,'lead',{'customer_name':'补电话测试','source':'展厅到店'})
    with SessionLocal() as db:uid=db.scalar(select(User.id).where(User.username=='sales'))
    return action(c,x,'assign',{'assignee_id':uid})

def test_callback_phone_recovery_and_replay(client):
    x=lead(client);login(client,'sales');x=detail(client,x)
    values={'due_date':today().isoformat(),'result':'客户希望明天联系'}
    action(client,x,'remind',values,409)
    values['customer_phone']='13900008888'
    body={'version':x['version'],'request_id':uuid.uuid4().hex,'values':values}
    url=f"/api/flow/cases/{x['id']}/actions/remind"
    r=client.post(url,json=body);assert r.status_code==200,r.text
    assert client.post(url,json=body).status_code==200
    assert detail(client,x)['customer']['phone']=='13900008888'
    body['request_id']=uuid.uuid4().hex
    assert client.post(url,json=body).status_code==409
    action(client,x,'remind',{**values,'customer_phone':'13900009999'},409)
    assert detail(client,x)['customer']['phone']=='13900008888'

def test_callback_phone_optout_and_invalid(client):
    x=lead(client);login(client,'sales')
    values={'due_date':today().isoformat(),'result':'回访','customer_phone':'bad'}
    action(client,x,'remind',values,422)
    with SessionLocal() as db:
        customer=db.get(Customer,detail(client,x)['customer']['id']);customer.contact_allowed=False;db.commit()
    action(client,x,'remind',{**values,'customer_phone':'13900008888'},409)
    assert detail(client,x)['customer']['phone']==''

def test_callback_wrong_role(client):
    x=lead(client);login(client,'inventory')
    response=client.post(f"/api/flow/cases/{x['id']}/actions/remind",json={'version':x['version'],'request_id':uuid.uuid4().hex,'values':{'customer_phone':'13900008888','due_date':today().isoformat(),'result':'回访'}})
    assert response.status_code in (403,404)

def test_callback_api_fields_request_phone_only_when_missing(client):
    from app.flow_specs import flow_spec
    missing=lead(client);login(client,'sales')
    info=detail(client,missing)
    def phone_required(data):
        action=next(a for a in data['actions'] if a['key']=='remind')
        return next(f for f in action['fields'] if f['key']=='customer_phone')['required']
    assert phone_required(info) is True
    # Reading one customer's action cannot change another customer's form or
    # frozen workflow version metadata.
    declared=next(a for a in flow_spec('lead',info['flow_version'])['actions'] if a.key=='remind')
    assert next(f for f in declared.fields if f['key']=='customer_phone')['required'] is False
    with SessionLocal() as db:
        row=db.get(Customer,info['customer']['id']);row.phone='13900008888';db.commit()
    assert phone_required(detail(client,missing)) is False

def photo():
    stream=io.BytesIO();Image.new('RGB',(800,600),'red').save(stream,format='PNG');return stream.getvalue()

def test_photo_admin_replace_public_reset(client):
    original=client.get('/api/branding/photo');assert original.status_code==200
    r=client.post('/api/branding/photo',files={'file':('photo.png',photo(),'image/png')});assert r.status_code==200,r.text
    image=client.get('/api/branding/photo');assert image.headers['content-type']=='image/jpeg'
    assert Image.open(io.BytesIO(image.content)).size==(800,600)
    login(client,'sales')
    assert client.post('/api/branding/photo',files={'file':('photo.png',photo(),'image/png')}).status_code==403
    assert client.delete('/api/branding/photo',headers={'Content-Type':'application/json'}).status_code==403
    assert client.get('/api/branding/photo').content==image.content
    login(client)
    assert client.post('/api/branding/photo',files={'file':('x.svg',b'<svg/>','image/svg+xml')}).status_code==422
    assert client.get('/api/branding/photo').content==image.content
    assert client.delete('/api/branding/photo',headers={'Content-Type':'application/json'}).status_code==200
    assert client.get('/api/branding/photo').content==original.content

def test_callback_other_store_is_hidden(client):
    from app.models import Store,UserStore
    x=lead(client)
    with SessionLocal() as db:
        store=Store(code='SECOND',name='第二店');db.add(store);db.flush()
        user=db.scalar(select(User).where(User.username=='sales'))
        db.add(UserStore(user_id=user.id,store_id=store.id));db.commit();sid=store.id
    login(client,'sales');client.headers['X-Store-ID']=str(sid)
    r=client.post(f"/api/flow/cases/{x['id']}/actions/remind",json={'version':x['version'],'request_id':uuid.uuid4().hex,'values':{'customer_phone':'13900008888','due_date':today().isoformat(),'result':'回访'}})
    assert r.status_code in (403,404)
    client.headers['X-Store-ID']='1'
    assert detail(client,x)['customer']['phone']==''
