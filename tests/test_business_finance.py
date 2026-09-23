"""Actual customer advances and one receipt allocated to guarded original orders."""
import uuid,sqlite3
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import CashEntry,Store,User,UserStore
from app.flow_models import Case,PaymentLink
from app.business_finance_models import FinanceAdvance,FinanceAdvanceEntry,FinanceCreditLink,FinanceCashAllocation,FinanceCashBatch
from tests.conftest import login,TEST_DIR
from tests.test_workflow import evidence,master,detail as source_detail
from tests.test_procurement import bank
from tests import test_retail as retail

API='/api/business-finance/orders'
def assert_restore():
    from app.business_finance_integrity import validate_business_finance_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate_business_finance_sqlite(restored)
        if restored.execute('SELECT COUNT(*) FROM business_finance_advances').fetchone()[0]:
            restored.execute('UPDATE business_finance_advances SET initial_cents=initial_cents+1,balance_cents=balance_cents+1')
            with pytest.raises(ValueError,match='预收'):validate_business_finance_sqlite(restored)
@pytest.fixture(autouse=True)
def restored_finance():
    yield
    assert_restore()
def detail(c,row):
    key=row['case']['id'] if 'case' in row else row['id']
    r=c.get(API+'/'+str(key));assert r.status_code==200,r.text;return r.json()
def create(c,customer,purpose,values,status=201,key=None):
    r=c.post(API,json={'request_id':key or uuid.uuid4().hex,'customer_id':customer['id'] if customer else None,'purpose':purpose,'values':values,'reason':'按实际业务核对办理'})
    assert r.status_code==status,r.text;return r.json()
def command(c,row,action,values=None,status=200,body=None):
    current=detail(c,row)
    body=body or {'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':values or {'reason':'明确取消原申请'}}
    r=c.post(API+f"/{current['case']['id']}/actions/{action}",json=body);assert r.status_code==status,r.text;return r.json()
def proof(c,row,**extra):return {'reason':'本人核对已发生事实','evidence_id':evidence(c,row['case'],'receipt'),**extra}
def versions(c,*rows):return {str(r['id']):source_detail(c,r)['version'] for r in rows}
def approve(c,row,*sources):
    login(c,'manager');row=command(c,row,'approve',proof(c,row,source_versions=versions(c,*sources)));login(c,'finance');return row
def advance(c,customer,amount,account=None):
    account=account or bank(c);row=create(c,customer,'advance',{'amount_cents':amount})
    return command(c,row,'execute',proof(c,row,account_id=account,reference=uuid.uuid4().hex)),account
def current_advance(c,customer):
    r=c.get('/api/business-finance/advances',params={'customer_id':customer['id']});assert r.status_code==200,r.text;return r.json()['items'][0]
def apply_advance(c,customer,source,amount,execute=True):
    a=current_advance(c,customer);row=create(c,customer,'advance_apply',{'amount_cents':amount,'advance_id':a['id'],'advance_version':a['version'],'target_case_id':source['id'],'target_version':source_detail(c,source)['version']})
    row=approve(c,row,source)
    return command(c,row,'execute',proof(c,row,source_versions=versions(c,source))) if execute else row
def ready_retail(c,customer=None,items=None):
    if items is None:items,customer,_,_=retail.setup(c)
    row=retail.authorize(c,retail.approve(c,retail.create(c,items,customer)))
    return row,items,customer

def test_advance_approved_hold_apply_unused_refund_and_cancel(client):
    source,_,customer=ready_retail(client);prepaid,account=advance(client,customer,1500)
    application=apply_advance(client,customer,source,600,False)
    assert current_advance(client,customer)['reserved_cents']==600
    retail.cmd(client,source,'receive',{'amount_cents':401,'account_id':account,'reference':'cannot-overcollect','evidence_id':evidence(client,source,'receipt')},409)
    application=command(client,application,'execute',proof(client,application,source_versions=versions(client,source)))
    assert current_advance(client,customer)['balance_cents']==900
    assert retail.detail(client,source)['totals']['receivable_cents']==400
    a=current_advance(client,customer);refund=create(client,customer,'advance_refund',{'amount_cents':300,'advance_id':a['id'],'advance_version':a['version']})
    refund=approve(client,refund);assert current_advance(client,customer)['reserved_cents']==300
    login(client,'manager');command(client,refund,'cancel');assert current_advance(client,customer)['reserved_cents']==0
    login(client,'finance');a=current_advance(client,customer);refund=create(client,customer,'advance_refund',{'amount_cents':900,'advance_id':a['id'],'advance_version':a['version']})
    refund=approve(client,refund);refund=command(client,refund,'execute',proof(client,refund,account_id=account,reference='unused-original-refund'))
    assert current_advance(client,customer)['balance_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(FinanceCreditLink.amount_cents)))==600
        assert db.scalar(select(func.count()).select_from(CashEntry))==2
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in db.scalars(select(CashEntry)))==600

def test_monthly_one_real_cash_multiple_sources_and_frozen_late_change(client):
    one,items,customer=ready_retail(client);items2,_,_,_=retail.setup(client);two=retail.authorize(client,retail.approve(client,retail.create(client,items2,customer,qty=500)))
    account=bank(client);statement=create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()})
    statement=approve(client,statement);assert len(statement['lines'])==2
    amounts=[{'source_case_id':l['source_case_id'],'amount_cents':l['due_cents']} for l in statement['lines']]
    statement=command(client,statement,'collect',proof(client,statement,amount_cents=sum(a['amount_cents'] for a in amounts),account_id=account,reference='ONE-ACTUAL-RECEIPT',allocations=amounts,source_versions=versions(client,one,two)))
    assert statement['order']['status']=='completed'
    with SessionLocal() as db:
        cash=list(db.scalars(select(CashEntry)));links=list(db.scalars(select(PaymentLink)))
        assert len(cash)==1 and len(links)==2 and len({l.cash_id for l in links})==1 and sum(l.amount_cents for l in links)==cash[0].amount_cents

def test_monthly_late_receipt_requires_new_snapshot_and_invalid_date(client):
    source,_,customer=ready_retail(client);account=bank(client)
    create(client,customer,'statement',{'starts_on':'2026-02-30','ends_on':today().isoformat()},422)
    statement=create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()})
    retail.pay(client,source,100,account);login(client,'manager');command(client,statement,'approve',proof(client,statement),409)
    login(client,'finance');new=command(client,statement,'recalculate')
    assert new['statement']['revision']==2 and new['statement']['previous_id']==statement['statement']['id'] and new['lines'][0]['due_cents']==900
    assert detail(client,statement)['lines'][0]['due_cents']==1000

def test_receipt_correction_append_only_and_original_business_date(client):
    source,_,customer=ready_retail(client);account=bank(client);source=retail.pay(client,source,700,account)
    with SessionLocal() as db:
        old=db.scalar(select(CashEntry));original_id=old.id;past=today().replace(day=1)-timedelta(days=1)
        # Synthetic historical source, before the correction is requested.
        db.connection().exec_driver_sql('UPDATE cash_entries SET business_date=? WHERE id=?',(past.isoformat(),old.id))
        db.connection().exec_driver_sql('UPDATE flow_payment_links SET business_date=? WHERE cash_id=?',(past.isoformat(),old.id));db.commit()
    row=create(client,customer,'correction',{'original_cash_id':original_id,'amount_cents':500,'account_id':account,'reference':'corrected-bank-reference','allocations':[{'source_case_id':source['id'],'amount_cents':500}]})
    row=approve(client,row);row=command(client,row,'execute',proof(client,row,source_versions=versions(client,source)))
    assert retail.detail(client,source)['totals']['cash_paid_cents']==500
    from app.business_finance_service import superseded_cash_ids,adjustment_cash_ids
    from app.tenancy import set_scope
    with SessionLocal() as db:
        set_scope(db,[1])
        facts=list(db.scalars(select(CashEntry)));excluded=superseded_cash_ids(db)|adjustment_cash_ids(db)
        assert len(facts)==3 and original_id in excluded
        actual=[c for c in facts if c.id not in excluded];assert len(actual)==1 and actual[0].amount_cents==500 and actual[0].business_date==past
        assert next(c for c in facts if c.id==original_id).amount_cents==700

def test_retail_partial_return_returns_original_advance_before_cash_refund(client):
    source,_,customer=ready_retail(client);prepaid,account=advance(client,customer,600);apply_advance(client,customer,source,600)
    source=retail.pay(client,source,400,account);login(client);source=retail.dispatch(client,source);source=retail.cmd(client,source,'accept',{'evidence_id':evidence(client,source)})
    source,ret=retail.request_return(client,source,source['dispatches'][0],1000);source=retail.ret_cmd(client,source,ret,'return_approve');source=retail.ret_cmd(client,source,ret,'return_receive')
    assert current_advance(client,customer)['balance_cents']==499 and source['totals']['advance_credit_cents']==101 and source['totals']['refund_due_cents']==0
    retail.refund(client,source,source['payments'][0],account,1,status=409)
    source,ret=retail.request_return(client,source,source['dispatches'][0],1000);source=retail.ret_cmd(client,source,ret,'return_approve');source=retail.ret_cmd(client,source,ret,'return_receive')
    assert current_advance(client,customer)['balance_cents']==600 and source['totals']['refund_due_cents']==397
    source=retail.refund(client,source,source['payments'][0],account,397)
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(FinanceCreditLink.amount_cents)))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==3
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in db.scalars(select(CashEntry)))==603


def test_other_inbound_return_approval_creates_receivable_before_actual_collection(client):
    from tests import test_warehouse as wh
    from app.flow_models import StockMove
    item,a,_=wh.setup(client,3000,1000)
    with SessionLocal() as db:original=db.scalar(select(StockMove.id).where(StockMove.item_id==item,StockMove.purpose=='wh_other_in'))
    returned=wh.create(client,'other_in_return',item,1000,src=a,original=original);wh.approve(client,returned);returned=wh.execute(client,returned)
    supplier=wh.typed(client,'suppliers',{'code':'OTHER-RETURN','name':'合成其他入库原供应方'})
    account=bank(client);values={'stock_move_id':returned['stock_moves'][0]['id'],'source_version':returned['version'],'supplier_id':supplier['id'],'amount_cents':400}
    row=create(client,None,'other_return',values);row=approve(client,row)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
    create(client,None,'other_return',values,409)
    row=command(client,row,'collect',proof(client,row,amount_cents=250,account_id=account,reference='other-return-part1'));assert row['order']['status']=='approved'
    command(client,row,'collect',proof(client,row,amount_cents=151,account_id=account,reference='other-overpaid'),409)
    row=command(client,row,'collect',proof(client,row,amount_cents=150,account_id=account,reference='other-return-part2'));assert row['order']['status']=='completed'


def test_independent_approval_roles_replay_stale_and_cross_store(client):
    customer=master(client,'customers',{'name':'本店客户','phone':'13900000987','contact_allowed':True,'note':''});account=bank(client)
    row=create(client,customer,'advance',{'amount_cents':600});p=proof(client,row,account_id=account,reference='not-finance');login(client,'service');command(client,row,'execute',p,403)
    login(client,'finance');command(client,row,'execute',{'reason':'普通凭据不能当真实到账','evidence_id':evidence(client,row['case']),'account_id':account,'reference':'NOT-A-RECEIPT'},422)
    current=detail(client,row);body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':proof(client,row,account_id=account,reference='ONCE')}
    result=command(client,row,'execute',body=body);assert command(client,row,'execute',body=body)==result
    command(client,row,'execute',body={**body,'request_id':uuid.uuid4().hex},status=409)
    a=current_advance(client,customer);refund=create(client,customer,'advance_refund',{'amount_cents':600,'advance_id':a['id'],'advance_version':a['version']})
    command(client,refund,'approve',proof(client,refund),403)
    login(client,'auditor');create(client,customer,'advance',{'amount_cents':1},403)
    login(client)
    with SessionLocal() as db:
        db.add(Store(id=2,code='FIN-B',name='合成财务乙店'));db.flush();db.add(UserStore(user_id=db.scalar(select(User.id).where(User.username=='admin')),store_id=2));db.commit()
    client.headers['X-Store-ID']='2';assert client.get(API+'/'+str(row['case']['id'])).status_code==404
    assert client.get('/api/business-finance/advances',params={'customer_id':customer['id']}).status_code==404


@pytest.mark.parametrize('conflict',['approval','bank_reference'])
def test_competing_approvals_and_old_new_cash_reference_serialize(client,conflict):
    source,_,customer=ready_retail(client);prepaid,account=advance(client,customer,600)
    if conflict=='approval':
        a=current_advance(client,customer);requests=[create(client,customer,'advance_refund',{'amount_cents':400,'advance_id':a['id'],'advance_version':a['version']}) for _ in range(2)]
        login(client,'manager');bodies=[]
        for row in requests:
            current=detail(client,row);bodies.append({'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':proof(client,row)})
        paths=[API+f"/{r['case']['id']}/actions/approve" for r in requests];role='manager'
    else:
        row=create(client,customer,'advance',{'amount_cents':100});current=detail(client,row);reference='COMPETING-ACTUAL-BANK'
        bodies=[{'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':proof(client,row,account_id=account,reference=reference)},
            {'request_id':uuid.uuid4().hex,'version':source_detail(client,source)['version'],'values':{'amount_cents':100,'account_id':account,'reference':reference,'evidence_id':evidence(client,source,'receipt')}}]
        paths=[API+f"/{row['case']['id']}/actions/execute",f"/api/retail/orders/{source['id']}/actions/receive"];role='finance'
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,role)
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(lambda i:clients[i].post(paths[i],json=bodies[i]).status_code,range(2)))
    assert sorted(statuses)==[200,409]
    if conflict=='approval':assert current_advance(client,customer)['reserved_cents']==400
    else:
        with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.voucher_no==reference))==1


@pytest.mark.parametrize('kind',['order','repair'])
def test_ordinary_original_customer_settlement_preserves_flow_gate(client,kind):
    from tests import test_workflow as flow,test_group_membership as group
    if kind=='order':source=flow.action(client,flow.order(client,'10.00'),'approve');customer={'id':source['customer_id']}
    else:
        data=group.seed(amount=1000);source=flow.detail(client,{'id':data['case_id']});customer={'id':data['customer_id']}
    prepaid,account=advance(client,customer,700);application=apply_advance(client,customer,source,600)
    assert source_detail(client,source)['paid_cents']==600
    sources=client.get('/api/business-finance/sources',params={'customer_id':customer['id']}).json()['items'];assert next(s for s in sources if s['case_id']==source['id'])['due_cents']==400
    flow.action(client,source,'receive',{'amount':'4.01','account_id':account,'reference':'ordinary-overcollection','evidence_id':evidence(client,source,'receipt')},409)
    flow.action(client,source,'receive',{'amount':'4.00','account_id':account,'reference':'ordinary-balance','evidence_id':evidence(client,source,'receipt')})
    assert source_detail(client,source)['paid_cents']==1000


def test_single_customer_statement_allocates_repair_customer_and_retail_not_insurance(client):
    from tests import test_repair_orders as repair
    from app.repair_models import RepairPayment
    from app.retail_models import RetailPayment
    repair_source,item,work,customer=repair.setup(client);repair_source=repair.ready(client,repair_source,item,work)
    insurer=repair.typed(client,'insurers',{'code':'FIN-INSURER','name':'独立保险承担方'})
    repair_source=repair.allocate(client,repair_source,[{'payer_type':'customer','amount_cents':6000},{'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':4997}])
    items,_,_,_=retail.setup(client);retail_source=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    account=bank(client);row=approve(client,create(client,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()}))
    allocations=[{'source_case_id':l['source_case_id'],'amount_cents':l['due_cents']} for l in row['lines']];assert sum(a['amount_cents'] for a in allocations)==7000
    row=command(client,row,'collect',proof(client,row,amount_cents=7000,account_id=account,reference='mixed-customer-one-cash',allocations=allocations,source_versions=versions(client,repair_source,retail_source)))
    assert repair.detail(client,repair_source)['receivable_cents']==4997
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert db.scalar(select(func.count()).select_from(RepairPayment))==1 and db.scalar(select(func.count()).select_from(RetailPayment))==1


def test_further_correction_reuses_only_its_original_bank_reference_chain(client):
    source,_,customer=ready_retail(client);account=bank(client);retail.pay(client,source,700,account)
    with SessionLocal() as db:original=db.scalar(select(CashEntry));original_id=original.id;reference=original.voucher_no
    for amount in [600,500]:
        row=create(client,customer,'correction',{'original_cash_id':original_id,'amount_cents':amount,'account_id':account,'reference':reference,'allocations':[{'source_case_id':source['id'],'amount_cents':amount}]})
        row=approve(client,row);row=command(client,row,'execute',proof(client,row,source_versions=versions(client,source)))
        original_id=next(b['cash_id'] for b in row['batches'] if b['kind']=='correction_record')
    assert retail.detail(client,source)['totals']['cash_paid_cents']==500
    row=create(client,customer,'advance',{'amount_cents':1});command(client,row,'execute',proof(client,row,account_id=account,reference=reference),409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==5


def test_advance_cash_without_payment_link_cannot_use_legacy_void(client):
    customer=master(client,'customers',{'name':'旧入口拒绝预收客户','phone':'13900000764','contact_allowed':True,'note':''});row,_=advance(client,customer,700)
    with SessionLocal() as db:
        cash=db.scalar(select(CashEntry));key,version=cash.id,cash.version
        assert not db.scalar(select(PaymentLink.id).where(PaymentLink.cash_id==key))
    response=client.post(f'/api/records/cash/{key}/actions/void',json={'version':version,'reason':'不能绕过原预收账本'})
    assert response.status_code==409,response.text
    assert current_advance(client,customer)['balance_cents']==700
