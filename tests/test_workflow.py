import io
import uuid
from datetime import timedelta
from sqlalchemy import select
from app.db import today,SessionLocal
from app.models import Vehicle,Store,User,UserStore,CashEntry
from app.flow_models import Case,Task,FileAsset,DocTemplate,Item,PaymentLink,Member,StockMove,RequestReceipt,VehicleHold
from tests.conftest import login


def create(c,kind,values,status=201,key=None):
    # Synthetic business fixtures explicitly reuse their one known, authorized
    # customer. Production must never perform this selection implicitly.
    if status==201 and key is None and values.get('customer_name') and values.get('customer_phone') and not values.get('customer_id') and not values.get('confirm_new_customer'):
        found=c.get('/api/customer-choice/matches',params={'phone':values['customer_phone']})
        assert found.status_code==200,found.text
        exact=[r for r in found.json()['items'] if r['name']==values['customer_name']]
        assert len(exact)<=1,'Fixture must specify customer_id when multiple authorized names match'
        if exact:values={**values,'customer_id':exact[0]['id']}
    r=c.post('/api/flow/cases',json={'kind':kind,'values':values,'request_id':key or uuid.uuid4().hex})
    assert r.status_code==status,r.text
    return r.json()

def detail(c,x):
    r=c.get('/api/flow/cases/'+str(x['id']));assert r.status_code==200,r.text;return r.json()

def action(c,x,key,values=None,status=200,request_id=None,version=None):
    x=detail(c,x)
    r=c.post(f"/api/flow/cases/{x['id']}/actions/{key}",json={'version':version or x['version'],'request_id':request_id or uuid.uuid4().hex,'values':values or {}})
    assert r.status_code==status,r.text;return r.json()

def master(c,kind,values):
    # A master-create fixture deliberately requests a new independent record.
    if kind=='customers':values={'confirm_new_customer':True,**values}
    r=c.post('/api/flow/master/'+kind,json={'values':values});assert r.status_code==201,r.text;return r.json()

def evidence(c,x,category='evidence',source=None):
    data={'category':category}
    if source:data['source_file_id']=str(source)
    r=c.post(f"/api/flow/cases/{x['id']}/files",files={'file':('业务凭据.txt',('测试凭据'+uuid.uuid4().hex).encode(),'text/plain')},data=data)
    assert r.status_code==200,r.text;return r.json()['id']

def order(c,amount='100000.00',**extra):
    return create(c,'order',{'customer_name':'测试客户','customer_phone':'13900000001','model':'测试车型','amount':amount,'delivery_due':today().isoformat(),**extra})

def account(c):return master(c,'accounts',{'name':'收款账户','account_type':'bank','active':True})['id']

def seed_car():
    with SessionLocal() as db:
        admin=db.scalar(select(User).where(User.role=='admin'))
        car=Vehicle(doc_no='CAR-'+uuid.uuid4().hex[:8],business_date=today(),approval_state='approved',created_by=admin.id,
            vin='LDD'+uuid.uuid4().hex[:14].upper().replace('I','1').replace('O','0').replace('Q','0'),brand='测试品牌',model='测试车型',purchase_cost_cents=8000000,list_price_cents=10000000)
        db.add(car);db.commit();return car.id

def approved_doc(c,x,kind):
    templates=c.get('/api/flow/master/templates').json()['items'];t=next(t for t in templates if t['kind']==kind)
    r=c.put(f"/api/flow/master/templates/{t['id']}",json={'version':t['version'],'values':{'title':t['title'],'clauses':t['clauses'],'approved':True}})
    assert r.status_code==200,r.text
    r=c.post(f"/api/flow/cases/{x['id']}/documents",json={'kind':kind});assert r.status_code==200,r.text;return r.json()['id']

def test_order_end_to_end(client):
    c=client;x=order(c);assert detail(c,x)['files'];x=action(c,x,'approve')
    action(c,x,'dispatch',{'evidence_id':evidence(c,x)},409)
    x=action(c,x,'allocate',{'vehicle_id':seed_car()})
    sid=approved_doc(c,x,'contract');x=action(c,x,'sign',{'evidence_id':evidence(c,x,'signed_contract',sid)})
    aid=account(c);x=action(c,x,'receive',{'amount':'100000.00','account_id':aid,'reference':'付款001','evidence_id':evidence(c,x,'receipt')})
    x=action(c,x,'inspect',{'outcome':'合格','result':'检测正常','evidence_id':evidence(c,x,'inspection')})
    x=action(c,x,'dispatch',{'evidence_id':evidence(c,x)})
    did=approved_doc(c,x,'handover');x=action(c,x,'deliver',{'evidence_id':evidence(c,x,'signed_handover',did)})
    assert x['state']=='delivered'
    assert any(r['kind']=='callback' for r in detail(c,x)['children'])
    assert c.get('/api/flow/lookup/vehicle').json()['items']==[]

def test_reception_reminder_intent_order(client):
    c=client;x=create(c,'lead',{'customer_name':'接待客户','customer_phone':'13900000002','source':'展厅到店'})
    with SessionLocal() as db:uid=db.scalar(select(User.id).where(User.username=='sales'))
    x=action(c,x,'assign',{'assignee_id':uid});login(c,'sales')
    x=action(c,x,'remind',{'due_date':today().isoformat(),'result':'暂时没有明确需求'})
    assert x['state']=='reminder'
    x=action(c,x,'intent',{'need':'准备买车','due_date':today().isoformat()})
    x=action(c,x,'reserve',{'model':'测试车型','amount':'100000','delivery_due':today().isoformat()})
    d=detail(c,x);assert x['state']=='converted' and len(d['children'])==1
    assert d['children'][0]['customer_id']==x['customer_id']

def test_idempotent_create_and_actions(client):
    key=uuid.uuid4().hex;values={'customer_name':'客户','model':'测试车型','amount':'100','delivery_due':today().isoformat()}
    one=create(client,'order',values,key=key);two=create(client,'order',values,key=key);assert one['id']==two['id']
    create(client,'order',{**values,'amount':'200'},409,key=key)
    payload={'version':one['version'],'request_id':uuid.uuid4().hex,'values':{}}
    url=f"/api/flow/cases/{one['id']}/actions/approve"
    assert client.post(url,json=payload).status_code==200
    assert client.post(url,json=payload).status_code==200
    with SessionLocal() as db:assert len(list(db.scalars(select(Task).where(Task.case_id==one['id'],Task.key=='allocate'))))==1

def test_stale_block_double_allocation_and_legacy_bypass(client):
    x=order(client);old=x['version'];x=action(client,x,'approve')
    action(client,x,'allocate',{'vehicle_id':seed_car()},409,version=old)
    car=seed_car();x=action(client,x,'allocate',{'vehicle_id':car})
    y=order(client);y=action(client,y,'approve');action(client,y,'allocate',{'vehicle_id':car},409)
    r=client.post('/api/records/sales',json={'doc_no':'绕过','business_date':today().isoformat(),'vehicle_id':car,'customer_name':'客户','salesperson':'销售','contract_amount':'100'})
    assert r.status_code==409

def test_partial_payment_refund_and_no_legacy_void(client):
    x=order(client);x=action(client,x,'approve');a=account(client)
    x=action(client,x,'receive',{'amount':'1000','account_id':a,'reference':'流水1','evidence_id':evidence(client,x)})
    d=detail(client,x);p=d['payments'][0]
    cash=client.get('/api/records/cash/'+str(p['cash_id'])).json()
    assert client.post(f"/api/records/cash/{cash['id']}/actions/void",json={'version':cash['version'],'reason':'不能绕过'}).status_code==409
    x=action(client,x,'cancel_request',{'reason':'客户取消'});x=action(client,x,'cancel_approve');assert x['state']=='refund_pending'
    action(client,x,'refund',{'original_id':p['id'],'amount':'1001','account_id':a,'reference':'退款1','evidence_id':evidence(client,x)},409)
    x=action(client,x,'refund',{'original_id':p['id'],'amount':'1000','account_id':a,'reference':'退款1','evidence_id':evidence(client,x)})
    assert x['state']=='cancelled' and x['paid_cents']==0

def test_contract_draft_cannot_serve_as_signed_final(client):
    x=order(client);x=action(client,x,'approve');x=action(client,x,'allocate',{'vehicle_id':seed_car()})
    source=detail(client,x)['files'][0]['id'];asset=evidence(client,x,'signed_contract',source)
    action(client,x,'sign',{'evidence_id':asset},409)

def test_parallel_service_blocks_dispatch(client):
    x=order(client,addon=True);x=action(client,x,'approve')
    children=detail(client,x)['children'];assert any(r['kind']=='addon' for r in children)
    action(client,x,'dispatch',{'evidence_id':evidence(client,x)},409)

def test_inventory_and_repair_chain(client):
    c=client;item=master(c,'items',{'sku':'机油','name':'机油','unit':'升','reorder':'2','active':True})
    p=create(c,'purchase',{'item_id':item['id'],'quantity':'10','unit_cost':'30','supplier':'供应商'});p=action(c,p,'approve');action(c,p,'stock_in',{'evidence_id':evidence(c,p)})
    r=create(c,'repair',{'customer_name':'车主','customer_phone':'13900000003','plate':'沪A12345','repair_type':'保养','problem':'更换机油','due_date':today().isoformat()})
    r=action(c,r,'quote',{'labor':'100','parts':'200','discount':'0','labor_cost':'30','payer':'客户','work':'更换机油'})
    r=action(c,r,'authorize',{'evidence_id':evidence(c,r)});r=action(c,r,'start')
    action(c,r,'material',{'item_id':item['id'],'quantity':'4'})
    req=next(x for x in detail(c,r)['children'] if x['kind']=='material_issue')
    action(c,r,'finish',{'result':'完成'},409)
    action(c,req,'issue',{'evidence_id':evidence(c,req)})
    r=action(c,r,'finish',{'result':'完成'});r=action(c,r,'quality',{'evidence_id':evidence(c,r)})
    a=account(c);r=action(c,r,'receive',{'amount':'300','account_id':a,'reference':'修理收款','evidence_id':evidence(c,r)})
    r=action(c,r,'release',{'evidence_id':evidence(c,r)});assert r['state']=='completed'
    current=c.get('/api/flow/master/items').json()['items'][0];assert current['quantity_milli']==6000 and current['inventory_value_cents']==18000

def test_tenant_file_case_and_scope_isolation(client):
    c=client;x=order(c);fid=evidence(c,x)
    store=c.post('/api/stores',json={'code':'SECOND','name':'另一门店','active':True}).json()['id']
    c.headers['X-Store-ID']=str(store)
    assert c.get(f"/api/flow/cases/{x['id']}").status_code==404
    assert c.get('/api/flow/files/'+str(fid)).status_code==404
    assert c.get('/api/flow/cases').json()['total']==0
    c.headers['X-Store-ID']='all'
    create(c,'order',{'customer_name':'客户','model':'车','amount':'100','delivery_due':today().isoformat()},409)

def test_permissions_and_removed_maintenance(client):
    x=order(client);login(client,'inventory')
    d=detail(client,x);assert 'amount_cents' not in d and 'amount' not in d['data']
    assert client.get('/api/flow/analytics').status_code==403
    assert client.post(f"/api/flow/cases/{x['id']}/actions/approve",json={'version':x['version'],'request_id':uuid.uuid4().hex,'values':{}}).status_code==403
    assert client.get('/api/maintenance/status').status_code==404
    assert client.post('/api/feedback',json={}).status_code==404

def test_analytics_empty_and_bad_dates(client):
    r=client.get('/api/flow/analytics');assert r.status_code==200,r.text
    assert r.json()['metrics']['cohort_rate'] is None
    assert client.get('/api/flow/analytics?date_from=2000-01-01').status_code==422
