"""Current-version customer consent, original money and physical vehicle conservation."""
import uuid,sqlite3
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from fastapi.testclient import TestClient
from app.db import SessionLocal,today
from app.main import app
from app.models import Vehicle,CashEntry
from app.flow_models import Case,PaymentLink,VehicleHold,Task,FileAsset
from app.sales_quote_models import SalesQuote,SalesQuoteReview,SalesQuoteResolution,SalesQuoteConsent,SalesQuoteAdjustment
from tests.conftest import login,TEST_DIR
from tests.test_workflow import action,evidence,approved_doc,seed_car,master,detail as flow_detail
from tests.test_vehicle_catalog import setup as catalog_setup,link_car,classify
from tests.test_procurement import bank

API='/api/sales-quotes/orders'
@pytest.fixture(autouse=True)
def restore_quotes():
    yield
    from app.sales_quote_integrity import validate_sales_quotes_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sales_quotes_sqlite(restored)
        if restored.execute('SELECT COUNT(*) FROM sales_quotes').fetchone()[0]:
            restored.execute('UPDATE sales_quotes SET amount_cents=amount_cents+1 WHERE id=(SELECT MIN(id) FROM sales_quotes)')
            with pytest.raises(ValueError,match='报价'):validate_sales_quotes_sqlite(restored)
def detail(c,row):
    response=c.get(API+'/'+str(row['id']));assert response.status_code==200,response.text;return response.json()
def setup(c,amount=10000):
    brand,series,model=catalog_setup(c);classify(c,series,model)
    customer=master(c,'customers',{'name':'整车报价客户','phone':'13900005222','contact_allowed':True,'note':''})
    car=seed_car();link_car(c,car,model)
    quote={'model_id':model['id'],'model_version':model['version'],'amount_cents':amount,'delivery_due':today().isoformat(),
        'valid_until':(today()+timedelta(days=7)).isoformat(),'addon':False,'insurance':False,'agency':False,'terms':'车辆价款与配套服务分单结算，变更须本版确认','reason':'客户确认车型和购车预算'}
    response=c.post(API,json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'quote':quote})
    assert response.status_code==201,response.text
    return response.json(),quote,car,customer
def approve(c,row):
    old=c.get('/api/auth/me').json()['username'];login(c,'manager')
    row=action(c,row,'quote_approve',{'reason':'独立核对车型版本及本单约定价格'});login(c,old);return row
def sign(c,row):
    login(c);source=approved_doc(c,row,'contract');file=evidence(c,row,'signed_contract',source)
    row=action(c,row,'sign',{'evidence_id':file});return detail(c,row)
def ready(c,row,car):
    row=approve(c,row);row=action(c,row,'allocate',{'vehicle_id':car});return sign(c,row)
def propose(c,row,quote,status=201,key=None,version=None):
    row=detail(c,row);response=c.post(API+f"/{row['id']}/quotes",json={'request_id':key or uuid.uuid4().hex,'version':version or row['version'],'quote':quote})
    assert response.status_code==status,response.text;return response.json()
def pay(c,row,amount,account=None):
    account=account or bank(c)
    return action(c,row,'receive',{'amount':str(amount/100),'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')}),account
def inspect(c,row):return action(c,row,'inspect',{'outcome':'合格','result':'本VIN交车检查合格','evidence_id':evidence(c,row,'inspection')})

def test_current_quote_approval_signature_and_v2_physical_delivery(client):
    c=client;row,quote,car,_=setup(c)
    assert row['flow_version']==4 and row['quotes'][0]['model_snapshot']['series_name']=='城市车系'
    action(c,row,'quote_approve',{'reason':'本人不得自批'},409)
    action(c,row,'allocate',{'vehicle_id':car},409)
    row=approve(c,row);row=action(c,row,'allocate',{'vehicle_id':car})
    row=sign(c,row);row,account=pay(c,row,10000);row=inspect(c,row)
    row=action(c,row,'dispatch',{'evidence_id':evidence(c,row)})
    source=approved_doc(c,row,'handover');row=action(c,row,'deliver',{'evidence_id':evidence(c,row,'signed_handover',source)})
    assert row['state']=='delivered'
    assert next(c for c in flow_detail(client,row)['children'] if c['kind']=='callback')['flow_version']==2
    propose(c,row,{**quote,'amount_cents':9000},409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SalesQuoteConsent))==1
        assert db.scalar(select(VehicleHold).where(VehicleHold.case_id==row['id'])).delivered

def test_paid_price_revision_freezes_dispatch_rejects_stale_signature_and_refunds_exact_original(client):
    c=client;row,quote,car,_=setup(c);row=ready(c,row,car);old_file=row['data']['signed_file']
    row,account=pay(c,row,10000);row=inspect(c,row)
    row=propose(c,row,{**quote,'amount_cents':9001,'reason':'客户要求修改车辆价款，保留原车型'})
    assert row['amount_cents']==10000 and row['active_quote_id']!=row['pending_quote_id']
    action(c,row,'dispatch',{'evidence_id':evidence(c,row)},409)
    row=approve(c,row);action(c,row,'sign',{'evidence_id':old_file},409);row=sign(c,row)
    assert row['amount_cents']==9001 and row['excess_cents']==999
    action(c,row,'dispatch',{'evidence_id':evidence(c,row)},409)
    original=next(p for p in row['payments'] if p['direction']=='in')
    values={'original_id':original['id'],'amount':'10.00','account_id':account,'reference':'price-refund','evidence_id':evidence(c,row,'receipt')}
    action(c,row,'refund_excess',values,409)
    values['amount']='9.99';row=action(c,row,'refund_excess',values)
    row=action(c,row,'dispatch',{'evidence_id':evidence(c,row)})
    with SessionLocal() as db:
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry)))==9001
        assert db.scalar(select(func.count()).select_from(SalesQuoteAdjustment))==1
        assert db.scalar(select(func.count()).select_from(SalesQuote))==2

def test_rejected_and_withdrawn_quote_keep_approved_original_facts(client):
    c=client;row,quote,car,_=setup(c);row=ready(c,row,car);old=row['active_quote_id'];oldsign=row['data']['signed_file']
    row=propose(c,row,{**quote,'amount_cents':10100});login(c,'manager');row=action(c,row,'quote_reject',{'reason':'客户条件尚未谈妥'});login(c)
    row=detail(c,row);assert row['active_quote_id']==old and row['amount_cents']==10000 and row['data']['signed_file']==oldsign
    row=propose(c,row,{**quote,'amount_cents':9999});row=approve(c,row);row=action(c,row,'quote_withdraw',{'reason':'客户保留原合同'});row=detail(c,row)
    assert row['active_quote_id']==old and not row['pending_quote_id'] and row['amount_cents']==10000
    assert [q['resolution']['outcome'] for q in row['quotes']]==['activated','rejected','withdrawn']

def test_new_vin_requires_explicit_inventory_release_new_pdi_and_new_customer_signature(client):
    from tests.test_master_data import create,SAMPLES
    c=client;row,quote,car,_=setup(c);row=ready(c,row,car);row=inspect(c,row)
    model=create(c,'vehicle_models',{'code':'QUOTE-N','name':'新车型',**SAMPLES['vehicle_models']});newcar=seed_car();link_car(c,newcar,model)
    row=propose(c,row,{**quote,'model_id':model['id'],'model_version':model['version'],'reason':'客户明确改订新车型'})
    row=approve(c,row)
    action(c,row,'sign',{'evidence_id':row['data']['signed_file']},409)
    row=action(c,row,'release_vehicle',{'reason':'已核对原车仍未出库','evidence_id':evidence(c,row)})
    assert row['vehicle_id'] is None and not row['data']['inspection_status']
    row=action(c,row,'allocate',{'vehicle_id':newcar});row=sign(c,row)
    row,_=pay(c,row,10000);action(c,row,'dispatch',{'evidence_id':evidence(c,row)},409);row=inspect(c,row)
    row=action(c,row,'dispatch',{'evidence_id':evidence(c,row)})
    with SessionLocal() as db:
        assert not db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id==car))
        assert db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id==newcar)).case_id==row['id']

def test_revision_idempotency_stale_roles_tenant_and_expiry(client):
    c=client;row,quote,car,_=setup(c);row=ready(c,row,car);key=uuid.uuid4().hex;v=row['version']
    changed=propose(c,row,quote,key=key,version=v);assert propose(c,row,quote,key=key,version=v)['pending_quote_id']==changed['pending_quote_id']
    propose(c,row,{**quote,'amount_cents':1},409,key=key,version=v);propose(c,row,quote,409,version=v)
    login(c,'finance');propose(c,row,quote,403);login(c)
    store=c.post('/api/stores',json={'code':'QUOTE-OTHER','name':'报价隔离门店','active':True}).json()['id'];c.headers['X-Store-ID']=str(store)
    assert c.get(API+'/'+str(row['id'])).status_code==404
    c.headers['X-Store-ID']='all';assert c.get(API+'/'+str(row['id'])).status_code==409
    c.headers['X-Store-ID']='1';row=action(c,changed,'quote_withdraw',{'reason':'需重新核对有效期'})
    propose(c,row,{**quote,'valid_until':(today()-timedelta(days=1)).isoformat()},422)

def test_advance_repricing_returns_only_original_excess_without_cash(client):
    from tests import test_business_finance as finance
    from app.business_finance_models import FinanceCreditLink
    c=client;row,quote,car,customer=setup(c);row=ready(c,row,car)
    prepaid,account=finance.advance(c,customer,15000);finance.apply_advance(c,customer,row,10000)
    login(c);row=propose(c,row,{**quote,'amount_cents':6000});row=approve(c,row);row=sign(c,row)
    assert row['paid_cents']==6000 and row['excess_cents']==0
    login(c,'finance');assert finance.current_advance(c,customer)['balance_cents']==9000
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert db.scalar(select(func.sum(FinanceCreditLink.amount_cents)).where(FinanceCreditLink.case_id==row['id']))==6000
        adjustment=db.scalar(select(SalesQuoteAdjustment));assert adjustment.amount_cents==4000 and adjustment.kind=='advance_return'

def test_competing_quote_revisions_and_competing_vehicle_allocation_are_atomic(client):
    from contextlib import ExitStack
    c=client;row,quote,car,customer=setup(c);row=ready(c,row,car)
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for p in clients:login(p)
        values={'version':row['version'],'quote':quote}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda i:clients[i].post(API+f"/{row['id']}/quotes",json={**values,'request_id':uuid.uuid4().hex}).status_code,range(2)))
    assert sorted(results)==[201,409]
    row=detail(c,row);row=action(c,row,'quote_withdraw',{'reason':'本次并发验证后恢复原版'})
    row=propose(c,row,quote);row=approve(c,row);row=action(c,row,'release_vehicle',{'reason':'退回未出库占用后重新分派','evidence_id':evidence(c,row)})
    response=c.post(API,json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'quote':quote});assert response.status_code==201,response.text
    second=approve(c,response.json());row=detail(c,row)
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for p in clients:login(p)
        def allocate(i):
            value=[row,second][i]
            return clients[i].post(f"/api/flow/cases/{value['id']}/actions/allocate",json={'request_id':uuid.uuid4().hex,'version':value['version'],'values':{'vehicle_id':car}}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(allocate,range(2)))
    assert sorted(results)==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(VehicleHold).where(VehicleHold.vehicle_id==car))==1

def test_original_service_started_and_unclassified_car_cannot_be_hidden_by_quote(client,monkeypatch):
    from app import sales_quote_service
    monkeypatch.setattr(sales_quote_service,'CURRENT_ORDER_VERSION',3)
    c=client;row,quote,car,_=setup(c)
    unclassified=seed_car();row=approve(c,row);action(c,row,'allocate',{'vehicle_id':unclassified},409)
    row=action(c,row,'allocate',{'vehicle_id':car});row=sign(c,row)
    row=propose(c,row,{**quote,'addon':True});row=approve(c,row);row=sign(c,row)
    child=next(x for x in row['children'] if x['kind']=='addon');assert child['flow_version']==2
    child=action(c,child,'service_quote',{'amount':'0','work':'开始加装原配车设备'})
    propose(c,row,quote,409)
    row=propose(c,row,{**quote,'addon':True,'amount_cents':9900});row=approve(c,row)
    action(c,row,'release_vehicle',{'reason':'不得忽略已经开始的加装','evidence_id':evidence(c,row)},409)
    action(c,child,'service_finish',{'evidence_id':evidence(c,child)},409)
    row=sign(c,row);action(c,child,'service_finish',{'evidence_id':evidence(c,child)})

def test_confirmed_quote_expiry_and_inventory_financial_visibility(client,monkeypatch):
    from app import sales_quote_service as service
    c=client;row,quote,car,_=setup(c);row=approve(c,row)
    tomorrow=today()+timedelta(days=8);monkeypatch.setattr(service,'today',lambda:tomorrow)
    action(c,row,'allocate',{'vehicle_id':car},409)
    row=action(c,row,'quote_withdraw',{'reason':'有效期已过，保留原报价历史'})
    monkeypatch.undo();row=propose(c,row,quote);row=approve(c,row)
    login(c,'manager');action(c,row,'allocate',{'vehicle_id':car},409)
    login(c,'inventory');shown=detail(c,row)
    assert 'amount_cents' not in shown and all('amount_cents' not in q and 'guide_price_cents' not in q['model_snapshot'] for q in shown['quotes'])
    assert c.get('/api/flow/files/'+str(shown['quotes'][0]['id'])).status_code in {403,404}
    row=action(c,row,'allocate',{'vehicle_id':car});login(c);row=sign(c,row)

def test_prepaid_order_termination_uses_aftercare_original_advance_not_cash(client):
    from tests import test_business_finance as finance,test_aftercare as aftercare
    from app.aftercare_models import AftercareSource
    c=client;row,quote,car,customer=setup(c);row=ready(c,row,car)
    prepaid,account=finance.advance(c,customer,15000);finance.apply_advance(c,customer,row,10000)
    login(c);action(c,row,'cancel_request',{'reason':'已抵用预收不能直接当现金退'},409)
    new=aftercare.create(c,row,'sale_termination');source=new['sources'][0];tender=next(x for x in source['eligible_returns'] if x['kind']=='advance')
    new=aftercare.plan(c,new,10000,[{'kind':'advance','original_id':tender['entry_id'],'units':10000}]);new=aftercare.approved(c,new);new=aftercare.confirmed(c,new);new=aftercare.applied(c,new)
    assert new['state']=='completed'
    login(c,'finance');assert finance.current_advance(c,customer)['balance_cents']==15000
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        link=db.scalar(select(AftercareSource));assert link.snapshot['sales_quote_id']==row['active_quote_id']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        from app.backup_integrity import validate_sqlite
        validate_sqlite(db)

def test_quote_documents_bind_same_price_new_terms_and_preserve_bytes(client,tmp_path):
    import os,hashlib
    from pathlib import Path
    c=client;row,quote,car,_=setup(c,12345678);row=approve(c,row);row=action(c,row,'allocate',{'vehicle_id':car})
    response=c.post(f"/api/flow/cases/{row['id']}/documents",json={'kind':'contract'});assert response.status_code==200,response.text
    draft=response.json();assert not draft['template_approved']
    folder=Path(os.environ.get('SALES_QUOTE_QA_DIR',tmp_path));folder.mkdir(parents=True,exist_ok=True)
    short=c.get('/api/flow/files/'+str(draft['id'])).content;(folder/'vehicle-quote-short.docx').write_bytes(short)
    row=sign(c,row);oldsignature=row['data']['signed_file']
    terms='\n'.join(f'第{i}项补充确认：客户和门店对照本次车辆型号、交期与约定资料逐项核对，发生实际变更时保留原记录并另行确认；配套服务及款项按对应原业务独立办理。' for i in range(1,19))
    assert len(terms)<=1500
    row=propose(c,row,{**quote,'terms':terms,'reason':'仅补充约定条款，原车型与售价保持'});row=approve(c,row)
    action(c,row,'sign',{'evidence_id':oldsignature},409)
    response=c.post(f"/api/flow/cases/{row['id']}/documents",json={'kind':'contract'});assert response.status_code==200,response.text
    long=response.json();(folder/'vehicle-quote-long.docx').write_bytes(c.get('/api/flow/files/'+str(long['id'])).content)
    assert c.get('/api/flow/files/'+str(draft['id'])).content==short
    with SessionLocal() as db:
        original=db.scalar(select(FileAsset).where(FileAsset.id==draft['id']));later=db.scalar(select(FileAsset).where(FileAsset.id==long['id']))
        assert original.sha256==hashlib.sha256(short).hexdigest() and original.source_fingerprint!=later.source_fingerprint
        assert original.snapshot['车辆约定金额（元）']==later.snapshot['车辆约定金额（元）']=='123456.78'
        assert original.snapshot['报价校验摘要']!=later.snapshot['报价校验摘要']

def test_partial_excess_refund_duplicate_stale_and_competing_payment_conserve_original(client):
    from contextlib import ExitStack
    c=client;row,quote,car,_=setup(c);row=ready(c,row,car);row,account=pay(c,row,10000)
    row=propose(c,row,{**quote,'amount_cents':9000});row=approve(c,row);row=sign(c,row)
    original=next(p for p in row['payments'] if p['direction']=='in')
    proof=evidence(c,row,'receipt');path=f"/api/flow/cases/{row['id']}/actions/refund_excess"
    body={'request_id':uuid.uuid4().hex,'version':row['version'],'values':{'original_id':original['id'],'amount':'4.00',
        'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':proof}}
    login(c,'finance');first=c.post(path,json=body);assert first.status_code==200,first.text
    assert c.post(path,json=body).status_code==200
    assert c.post(path,json={**body,'request_id':uuid.uuid4().hex}).status_code==409
    row=detail(c,row);assert row['excess_cents']==600
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for p in clients:login(p,'finance')
        def refund(i):
            return clients[i].post(path,json={'request_id':uuid.uuid4().hex,'version':row['version'],
                'values':{**body['values'],'amount':'6.00','reference':uuid.uuid4().hex}}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(refund,range(2)))
    assert sorted(results)==[200,409]
    assert detail(c,row)['excess_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==row['id'],PaymentLink.direction=='out'))==1000
        assert db.scalar(select(func.count()).select_from(SalesQuoteAdjustment))==2
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry)))==9000

def test_quote_approval_preserves_handoff_and_confirmed_delivery_date_updates_default_tasks(client):
    from app.models import User
    c=client;row,quote,car,_=setup(c);row=ready(c,row,car)
    task=next(t for t in row['tasks'] if t['key']=='deliver')
    with SessionLocal() as db:sales=db.scalar(select(User.id).where(User.username=='sales'))
    transferred=c.post(f"/api/flow/tasks/{task['id']}/assign",json={'version':task['version'],'assignee_id':sales,'reason':'后续提车由已交接同事办理'})
    assert transferred.status_code==200,transferred.text
    future=(today()+timedelta(days=3)).isoformat()
    row=propose(c,row,{**quote,'delivery_due':future,'reason':'客户确认延后交期，已交接办理人保持'})
    row=approve(c,row);row=detail(c,row)
    task=next(t for t in row['tasks'] if t['key']=='deliver')
    assert task['assignee_id']==sales and task['due_date']==quote['delivery_due']
    row=sign(c,row);task=next(t for t in row['tasks'] if t['key']=='deliver')
    assert task['assignee_id']==sales and task['due_date']==future

def test_frozen_model_vehicle_choice_survives_catalogue_pages(client):
    from tests.test_master_data import create,update,SAMPLES
    c=client;row,quote,car,_=setup(c);row=approve(c,row)
    for n in range(13):
        create(c,'vehicle_models',{'code':'CAT-M'+str(n),'name':'前置目录 '+str(n),'brand':'AAA',**{k:v for k,v in SAMPLES['vehicle_models'].items() if k!='brand'}})
    response=c.get(API+f"/{row['id']}/vehicles");assert response.status_code==200,response.text
    assert [v['id'] for v in response.json()['items']]==[car]
    model=next(m for m in c.get('/api/masters/vehicle_models',params={'q':'CAT-M'}).json()['items'] if m['id']==quote['model_id'])
    updated=update(c,'vehicle_models',model,{**SAMPLES['vehicle_models'],'code':'RETIRED-ORIGINAL','name':'已停用但原承诺履约车型','active':False})
    response=c.get(API+f"/{row['id']}/vehicles");assert response.status_code==200,response.text
    assert [v['id'] for v in response.json()['items']]==[car]
    row=action(c,row,'allocate',{'vehicle_id':car});row=sign(c,row)
    assert row['quotes'][0]['model_snapshot']['code']=='CAT-M'
    propose(c,row,{**quote,'model_version':updated['version']},422)
