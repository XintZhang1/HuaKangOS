"""Real original refunds stay immutable across gross-cash/net-payment corrections."""
import sqlite3,uuid
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import CashEntry
from app.flow_models import PaymentLink,Case
from app.business_finance_models import FinanceCorrectionBasis,FinanceCorrectionRefundSlice,FinanceCashBatch
from tests.conftest import login,TEST_DIR
from tests import test_business_finance as f,test_aftercare as care,test_retail as retail
from tests.test_procurement import bank as create_bank


def bank(c):
    login(c);key=create_bank(c);login(c,'finance');return key


def restore(tamper=None):
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy)
        if tamper:copy.execute(tamper)
        return validate_sqlite(copy)


@pytest.fixture(autouse=True)
def recovered():
    yield
    restore()


def refunded_repair(c,amount=2000):
    source,account=care.completed_repair(c)
    row=care.applied(c,care.confirmed(c,care.approved(c,care.plan(c,care.create(c,source),amount))))
    row=care.refund(c,row,account,amount)
    with SessionLocal() as db:
        p=db.scalar(select(PaymentLink).where(PaymentLink.case_id==source['id'],PaymentLink.direction=='in'))
        origin=p.cash_id
        old_refund=db.scalar(select(PaymentLink).where(PaymentLink.original_id==p.id))
        refund=(old_refund.id,old_refund.cash_id,old_refund.account_id,old_refund.amount_cents)
    login(c,'finance')
    return source,{'id':source['customer_id']},account,origin,refund


def create_fix(c,customer,origin,gross,allocations,account,**extra):
    return f.create(c,customer,'correction',{'original_cash_id':origin,'amount_cents':gross,
        'account_id':account,'reference':uuid.uuid4().hex,'allocations':allocations,'allocation_basis':'remaining_after_refunds',**extra})


def apply_fix(c,customer,origin,gross,sources,account,allocations=None):
    if allocations is None:allocations=[{'source_case_id':sources[0]['id'],'amount_cents':gross-2000}] if gross>2000 else []
    row=f.approve(c,create_fix(c,customer,origin,gross,allocations,account))
    return f.command(c,row,'execute',f.proof(c,row,source_versions=f.versions(c,*sources)))


@pytest.mark.parametrize('gross',[2000,9000,10997])
def test_partial_refund_keeps_real_cash_and_replaces_only_remaining_allocation(client,gross):
    source,customer,old_account,origin,refund=refunded_repair(client);new_account=bank(client)
    row=apply_fix(client,customer,origin,gross,[source],new_account)
    projected=row['partial_correction'];assert projected['refunded_cents']==2000 and projected['corrected_net_cents']==gross-2000
    assert projected['refunds'][0]['payment_id']==refund[0]
    with SessionLocal() as db:
        assert db.scalar(select(CashEntry).where(CashEntry.id==origin)).amount_cents==10997
        old=db.scalar(select(PaymentLink).where(PaymentLink.id==refund[0]));assert (old.id,old.cash_id,old.account_id,old.amount_cents)==refund
        links=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==source['id'])))
        assert sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in links)==gross-2000
        reverse=next(b for b in row['batches'] if b['kind']=='correction_reverse');correct=next(b for b in row['batches'] if b['kind']=='correction_record')
        assert reverse['amount_cents']==10997 and correct['amount_cents']==gross
        assert sum(p.amount_cents for p in links if p.cash_id==reverse['cash_id'])==8997
        assert sum(p.amount_cents for p in links if p.cash_id==correct['cash_id'])==gross-2000
        assert all(p.amount_cents>0 for p in links)
    assert care.repair_detail(client,source)['receivable_cents']==10997-gross


def test_second_correction_inherits_old_refunds_and_later_refund_uses_new_account(client):
    source,customer,old_account,origin,refund=refunded_repair(client);second_account=bank(client)
    first=apply_fix(client,customer,origin,9000,[source],second_account)
    successor=next(b['cash_id'] for b in first['batches'] if b['kind']=='correction_record')
    second=apply_fix(client,customer,successor,9500,[source],second_account)
    assert second['partial_correction']['refunded_cents']==2000
    login(client)
    # A further original price reduction yields a real refund from the successor only.
    after=care.create(client,source);eligible=care.detail(client,after)['sources'][0]['eligible_returns'][0]['entry_id']
    after=care.applied(client,care.confirmed(client,care.approved(client,care.plan(client,after,2000,[{'kind':'cash','original_id':eligible,'units':503}]))))
    after=care.refund(client,after,second_account,503)
    with SessionLocal() as db:
        actual=[p for p in db.scalars(select(PaymentLink).where(PaymentLink.direction=='out')) if db.scalar(select(CashEntry.category).where(CashEntry.id==p.cash_id))!='business_finance_correction_reverse']
        assert [(p.account_id,p.amount_cents) for p in actual]==[(old_account,2000),(second_account,503)]
    login(client,'finance');successor=next(b['cash_id'] for b in second['batches'] if b['kind']=='correction_record')
    third=apply_fix(client,customer,successor,9000,[source],second_account,[{'source_case_id':source['id'],'amount_cents':6497}])
    assert third['partial_correction']['refunded_cents']==2503


def test_explicit_basis_and_actual_refund_floor_required(client):
    source,customer,account,origin,_=refunded_repair(client)
    base={'original_cash_id':origin,'amount_cents':9000,'account_id':account,'reference':'explicit','allocations':[{'source_case_id':source['id'],'amount_cents':7000}]}
    f.create(client,customer,'correction',base,409)
    f.create(client,customer,'correction',{**base,'allocation_basis':'remaining_after_refunds','amount_cents':1999,'allocations':[]},409)
    f.create(client,customer,'correction',{**base,'allocation_basis':'remaining_after_refunds','allocations':[{'source_case_id':source['id'],'amount_cents':9000}]},422)


@pytest.mark.parametrize('kind',['agency','other_income'])
def test_completed_service_original_fee_and_refund_stay_after_partial_correction(client,kind):
    from tests import test_service_orders as service
    row,project,_=service.setup(client,kind);row=service.authorized(client,service.approved(client,service.quoted(client,row,project)))
    account=create_bank(client);row=service.cash(client,row,'receive',997,account)
    row=service.complete_line(client,row,'fee1');row=service.apply_termination(client,service.termination(client,row,{'fee1':600}))
    plan=row['plans'][-1];row=service.cash(client,row,'refund',397,account,plan_id=plan['id'],tender_id=plan['returns'][0]['tender_id'])
    with SessionLocal() as db:
        origin=db.scalar(select(PaymentLink.cash_id).where(PaymentLink.case_id==row['id'],PaymentLink.direction=='in'))
        customer_id=db.scalar(select(Case.customer_id).where(Case.id==row['id']))
    login(client,'finance');fixed=apply_fix(client,{'id':customer_id},origin,897,[row],account,[{'source_case_id':row['id'],'amount_cents':500}])
    actual=service.detail(client,row)
    assert actual['summary']['fee_charge_cents']==600 and actual['summary']['customer_paid_cents']==500
    assert fixed['partial_correction']['refunded_cents']==397


def test_ended_vehicle_sale_reopens_only_original_aftercare_collection(client):
    source=care.sales_action(client,care.sales_order(client,'100.00'),'approve')
    source=care.sales_action(client,source,'allocate',{'vehicle_id':care.seed_car()})
    account=create_bank(client)
    source=care.sales_action(client,source,'receive',{'amount':'100.00','account_id':account,'reference':'original-sale-cash','evidence_id':care.evidence(client,source,'receipt')})
    after=care.applied(client,care.confirmed(client,care.approved(client,care.plan(client,care.create(client,source,'sale_termination'),8000))))
    after=care.refund(client,after,account,8000)
    with SessionLocal() as db:origin=db.scalar(select(PaymentLink.cash_id).where(PaymentLink.case_id==source['id'],PaymentLink.direction=='in'))
    login(client,'finance')
    fixed=apply_fix(client,{'id':source['customer_id']},origin,9500,[source],account,[{'source_case_id':source['id'],'amount_cents':1500}])
    after=care.detail(client,after);assert after['state']=='working' and after['applied'] and after['sources'][0]['due_cents']==500
    care.cmd(client,after,'apply',{'evidence_id':care.evidence(client,after,'receipt')},409)
    after=care.cmd(client,after,'collect',{'source_id':after['sources'][0]['id'],'amount_cents':500,'account_id':account,'reference':'retained-actual-balance','evidence_id':care.evidence(client,after,'receipt')})
    assert after['state']=='completed'
    assert fixed['partial_correction']['refunded_cents']==8000


def multi_retail_refund(c):
    one,items,customer=f.ready_retail(c);other_items,_,_,_=retail.setup(c)
    two=retail.authorize(c,retail.approve(c,retail.create(c,other_items,customer,qty=500)))
    account=create_bank(c);from app.db import today
    row=f.approve(c,f.create(c,customer,'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()}))
    allocations=[{'source_case_id':l['source_case_id'],'amount_cents':l['due_cents']} for l in row['lines']];total=sum(a['amount_cents'] for a in allocations)
    row=f.command(c,row,'collect',f.proof(c,row,amount_cents=total,account_id=account,reference='two-original-sales-one-cash',allocations=allocations,source_versions=f.versions(c,one,two)))
    original=row['batches'][0]['cash_id'];login(c);one=retail.dispatch(c,one);one=retail.cmd(c,one,'accept',{'evidence_id':care.evidence(c,one)})
    one,ret=retail.request_return(c,one,one['dispatches'][0],1000);one=retail.ret_cmd(c,one,ret,'return_approve');one=retail.ret_cmd(c,one,ret,'return_receive')
    amount=one['totals']['refund_due_cents'];one=retail.refund(c,one,one['payments'][0],account,amount)
    login(c,'finance');return one,two,customer,account,original,total,amount


def test_one_cash_multiple_original_sales_preserves_one_real_refund(client):
    one,two,customer,account,original,total,refunded=multi_retail_refund(client)
    amounts=[{'source_case_id':one['id'],'amount_cents':200},{'source_case_id':two['id'],'amount_cents':200}]
    fixed=apply_fix(client,customer,original,refunded+400,[one,two],account,amounts)
    assert fixed['partial_correction']['refunded_cents']==refunded
    assert retail.detail(client,one)['totals']['cash_paid_cents']==retail.detail(client,two)['totals']['cash_paid_cents']==200
    with SessionLocal() as db:
        reverse=next(b['cash_id'] for b in fixed['batches'] if b['kind']=='correction_reverse')
        assert sum(db.scalars(select(PaymentLink.amount_cents).where(PaymentLink.cash_id==reverse)))==total-refunded


@pytest.mark.parametrize('action',['cancel','reject'])
def test_pending_partial_correction_releases_exclusive_original_claim(client,action):
    source,customer,account,origin,_=refunded_repair(client)
    amounts=[{'source_case_id':source['id'],'amount_cents':7000}]
    first=create_fix(client,customer,origin,9000,amounts,account);second=create_fix(client,customer,origin,9000,amounts,account)
    first=f.approve(client,first);login(client,'manager');f.command(client,second,'approve',f.proof(client,second),409)
    f.command(client,first,action);second=f.approve(client,second)
    f.command(client,second,'execute',f.proof(client,second,source_versions=f.versions(client,source)))


@pytest.mark.parametrize('tamper',[
    'UPDATE business_finance_correction_refund_slices SET amount_cents=amount_cents+1',
    'DELETE FROM business_finance_correction_refund_slices',
    'UPDATE business_finance_correction_bases SET refunded_cents=refunded_cents+1',
    'UPDATE business_finance_correction_bases SET previous_id=id',
    "UPDATE flow_tasks SET status='done' WHERE key LIKE 'repair_receive_%'",
])
def test_full_restore_rejects_refund_slice_or_responsibility_tamper(client,tamper):
    source,customer,account,origin,_=refunded_repair(client)
    apply_fix(client,customer,origin,9000,[source],account)
    with pytest.raises(ValueError):restore(tamper)


def test_zero_remaining_successor_can_be_corrected_again_without_fabricating_payment(client):
    source,customer,account,origin,_=refunded_repair(client)
    first=apply_fix(client,customer,origin,2000,[source],account)
    cash=next(b['cash_id'] for b in first['batches'] if b['kind']=='correction_record')
    with SessionLocal() as db:assert not list(db.scalars(select(PaymentLink).where(PaymentLink.cash_id==cash)))
    second=apply_fix(client,customer,cash,9000,[source],account)
    assert second['partial_correction']['refunded_cents']==2000
    assert care.repair_detail(client,source)['receivable_cents']==1997


def test_addon_partial_return_correction_preserves_stock_and_installation(client):
    from tests import test_addon_orders as a
    from app.flow_models import StockMove
    from app.addon_models import AddonAcceptance,AddonInstallation
    row,items,work,source,vin,account=a.completed(client)
    row=a.resolve(client,a.resolve(client,a.resolution(client,row,'return'),'resolution_approve'),'resolution_consent')
    row=a.resolve(client,row,'return_receive',passed=True);refunded=row['return_postings'][0]['goods_cents']
    row=a.refund(client,row,account,refunded)
    with SessionLocal() as db:
        original=db.scalar(select(PaymentLink.cash_id).where(PaymentLink.case_id==row['id'],PaymentLink.direction=='in'))
        before=[list(db.scalars(select(m.id))) for m in (StockMove,AddonAcceptance,AddonInstallation)]
        customer=db.scalar(select(Case.customer_id).where(Case.id==row['id']))
    login(client,'finance');fixed=apply_fix(client,{'id':customer},original,1097,[row],account,[{'source_case_id':row['id'],'amount_cents':1097-refunded}])
    assert fixed['partial_correction']['refunded_cents']==refunded
    assert a.detail(client,row)['totals']['receivable_cents']==100
    with SessionLocal() as db:assert before==[list(db.scalars(select(m.id))) for m in (StockMove,AddonAcceptance,AddonInstallation)]


@pytest.mark.parametrize('retained',[0,2000])
def test_insurance_original_return_requires_all_external_principal_returned(client,retained):
    from tests import test_insurance_orders as i
    row,_,cv=i.setup(client);row=i.ready(client,row);account=create_bank(client)
    row=i.cash(client,row,'receive',10001,account);row=i.cash(client,row,'disburse',10001,account,tender_id=row['tenders'][0]['id'])
    row=i.issued(client,row);row=i.apply_plan(client,i.termination(client,row,retained))
    row=i.cash(client,row,'insurer_return',10001-retained,account,original_id=row['pass_entries'][0]['id'])
    row=i.cash(client,row,'refund',10001-retained,account,plan_id=row['plans'][-1]['id'],tender_id=row['tenders'][0]['id'])
    row=i.commission(client,row,0)
    with SessionLocal() as db:original=db.scalar(select(PaymentLink.cash_id).where(PaymentLink.case_id==row['id'],PaymentLink.direction=='in'))
    login(client,'finance')
    if retained:
        f.create(client,{'id':cv['customer_id']},'correction',{'original_cash_id':original,'amount_cents':10001,'account_id':account,'reference':'cannot-move-spent-premium','allocations':[{'source_case_id':row['id'],'amount_cents':retained}],'allocation_basis':'remaining_after_refunds'},409)
    else:
        fixed=apply_fix(client,{'id':cv['customer_id']},original,10001,[row],bank(client),[])
        assert fixed['partial_correction']['corrected_net_cents']==0
        assert i.detail(client,row)['summary']['customer_paid_cents']==0


def test_partial_correction_duplicate_stale_roles_and_cross_store(client):
    from app.models import Store,User,UserStore
    source,customer,account,origin,_=refunded_repair(client)
    row=create_fix(client,customer,origin,9000,[{'source_case_id':source['id'],'amount_cents':7000}],account)
    f.command(client,row,'approve',f.proof(client,row),403)
    row=f.approve(client,row);current=f.detail(client,row)
    values=f.proof(client,row,source_versions=f.versions(client,source))
    login(client,'service');f.command(client,row,'execute',values,403);login(client,'finance')
    body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':values}
    result=f.command(client,row,'execute',body=body);assert f.command(client,row,'execute',body=body)==result
    f.command(client,row,'execute',body={**body,'request_id':uuid.uuid4().hex},status=409)
    with SessionLocal() as db:
        db.add(Store(id=2,code='PARTIAL-B',name='合成部分原款乙店'));db.flush()
        db.add(UserStore(user_id=db.scalar(select(User.id).where(User.username=='finance')),store_id=2));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get(f.API+'/'+str(row['case']['id'])).status_code==404
    assert client.get('/api/business-finance/receipts',params={'customer_id':customer['id']}).status_code==404
    f.create(client,customer,'correction',{'original_cash_id':origin,'amount_cents':9000,'account_id':account,'reference':'cross-store','allocations':[{'source_case_id':source['id'],'amount_cents':7000}],'allocation_basis':'remaining_after_refunds'},404)


def test_two_partial_correction_approvals_compete_for_same_original_slice(client):
    from contextlib import ExitStack
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    source,customer,account,origin,_=refunded_repair(client)
    requests=[create_fix(client,customer,origin,9000,[{'source_case_id':source['id'],'amount_cents':7000}],account) for _ in range(2)]
    login(client,'manager');bodies=[]
    for row in requests:
        current=f.detail(client,row);bodies.append({'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':f.proof(client,row)})
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'manager')
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda n:clients[n].post(f.API+f"/{requests[n]['case']['id']}/actions/approve",json=bodies[n]).status_code,range(2)))
    assert sorted(statuses)==[200,409]


@pytest.mark.parametrize('approved',[False,True])
def test_later_actual_refund_invalidates_draft_but_cannot_consume_approved_slice(client,approved):
    one,two,customer,account,origin,total,refunded=multi_retail_refund(client)
    row=create_fix(client,customer,origin,refunded+400,[{'source_case_id':one['id'],'amount_cents':200},{'source_case_id':two['id'],'amount_cents':200}],account)
    if approved:row=f.approve(client,row)
    login(client);one,ret=retail.request_return(client,one,one['dispatches'][0],1000)
    one=retail.ret_cmd(client,one,ret,'return_approve');one=retail.ret_cmd(client,one,ret,'return_receive')
    payment=next(p for p in one['payments'] if p['direction']=='in')
    values={'original_payment_id':payment['id'],'account_id':account,'amount_cents':one['totals']['refund_due_cents'],'reference':'LATER-ACTUAL-REFUND','evidence_id':care.evidence(client,one,'receipt')}
    if approved:
        retail.cmd(client,one,'refund',values,409)
        f.command(client,row,'cancel')
        retail.cmd(client,one,'refund',values)
    else:
        retail.cmd(client,one,'refund',values)
        login(client,'manager');f.command(client,row,'approve',f.proof(client,row),409)
