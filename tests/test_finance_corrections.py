"""Registered API simulations of recording errors, not fabricated cash refunds."""
import sqlite3,uuid
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal
from app.models import CashEntry,User,UserStore,Store
from app.flow_models import PaymentLink,StockMove
from app.business_finance_models import FinanceStoredCorrection,FinanceAdvanceEntry,FinanceStoredCorrectionRequest,FinanceReturnReceivable
from app.business_finance_integrity import validate_business_finance_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_business_finance as f,test_retail as retail,test_group_membership as g,test_membership_lifecycle as membership,test_warehouse as wh,test_service_analytics as reports


@pytest.fixture(autouse=True)
def restore_after_simulation():
    yield
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        from app.backup_integrity import validate_sqlite
        original.backup(restored);validate_business_finance_sqlite(restored);validate_sqlite(restored)


def recorded(c,customer,kind='advance'):
    response=c.get('/api/business-finance/receipts',params={'customer_id':customer['id']})
    assert response.status_code==200,response.text
    return next(r for r in response.json()['items'] if r.get('source_kind')==kind)


def bank(c):
    login(c);account=f.bank(c);login(c,'finance');return account


def correction(c,customer,amount,kind='advance',account=None,reference=None,status=201,**extra):
    origin=recorded(c,customer,kind)
    values={'original_cash_id':origin['cash_id'],'source_version':origin['source_version'],'amount_cents':amount,**extra}
    if amount:values.update(account_id=account,reference=reference or uuid.uuid4().hex)
    return f.create(c,customer,'stored_correction',values,status)


def member_topup(c,amount=1000):
    customer,member=membership.setup(c);account=bank(c)
    order=membership.create(c,customer,'topup',{'amount_cents':amount});login(c,'finance')
    order=membership.cmd(c,order,'execute',{'evidence_id':membership.proof(c,order),'account_id':account,'reference':uuid.uuid4().hex,'reason':'完整API登记合成原充值'})
    return customer,member,order,account


def post(c,row):
    row=f.approve(c,row)
    return f.command(c,row,'execute',f.proof(c,row))


@pytest.mark.parametrize('amount',[0,700,1500])
def test_advance_correction_preserves_original_and_current_cash_once(client,amount):
    _,_,customer=f.ready_retail(client);original,account=f.advance(client,customer,1000)
    origin=recorded(client,customer);row=post(client,correction(client,customer,amount,account=account))
    current=f.current_advance(client,customer)
    assert current['initial_cents']==1000 and current['correction_cents']==amount-1000
    assert current['balance_cents']==current['effective_initial_cents']==amount and current['reserved_cents']==0
    assert row['order']['status']=='completed'
    with SessionLocal() as db:
        facts=list(db.scalars(select(CashEntry)));assert len(facts)==(2 if not amount else 3)
        assert db.scalar(select(CashEntry.amount_cents).where(CashEntry.id==origin['cash_id']))==1000
        assert all(c.amount_cents>0 for c in facts)
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in facts)==amount
    report=reports.reconciled(client,'finance_corrections',amount-1000)
    assert report['metrics']['cash_in_cents']==amount and report['metrics']['cash_out_cents']==0
    reports.reconciled(client,'finance_advances',amount)


def test_spent_advance_is_preserved_and_later_refund_uses_corrected_original_account(client):
    source,_,customer=f.ready_retail(client);original,account=f.advance(client,customer,1000)
    f.apply_advance(client,customer,source,400)
    correction(client,customer,399,account=account,status=409)
    other=bank(client);row=post(client,correction(client,customer,800,account=other))
    assert f.current_advance(client,customer)['balance_cents']==400
    assert retail.detail(client,source)['totals']['advance_credit_cents']==400
    a=f.current_advance(client,customer);refund=f.approve(client,f.create(client,customer,'advance_refund',{'advance_id':a['id'],'advance_version':a['version'],'amount_cents':400}))
    f.command(client,refund,'execute',f.proof(client,refund,account_id=account,reference='wrong-old-account'),409)
    f.command(client,refund,'execute',f.proof(client,refund,account_id=other,reference='actual-corrected-account-refund'))
    assert f.current_advance(client,customer)['balance_cents']==0


@pytest.mark.parametrize('kind',['advance','member'])
def test_same_amount_account_correction_and_second_correction_chain(client,kind):
    if kind=='advance':
        _,_,customer=f.ready_retail(client);_,account=f.advance(client,customer,1000)
    else:customer,member,_,account=member_topup(client)
    other=bank(client);post(client,correction(client,customer,1000,kind,other,reference='same-bank-reference'))
    post(client,correction(client,customer,1200,kind,other,reference='same-bank-reference'))
    source=recorded(client,customer,kind);assert source['amount_cents']==source['balance_cents']==1200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FinanceStoredCorrection))==2
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in db.scalars(select(CashEntry)))==1200


@pytest.mark.parametrize('amount',[0,700,1500])
def test_independent_member_topup_correction_appends_principal_and_internal_pairs(client,amount):
    customer,member,original,account=member_topup(client)
    post(client,correction(client,customer,amount,'member',account))
    assert g.wallet(client,member)['balance_cents']==amount
    from app.group_models import GroupEntry,GroupSettlementEntry
    from app.group_service import authority
    from app.tenancy import set_scope
    with SessionLocal() as db:
        set_scope(db,[1],1);actor=db.scalar(select(User).where(User.username=='finance'))
        with authority(db,actor):
            entries=list(db.scalars(select(GroupEntry)));assert [e.purpose for e in entries]==['topup','correction']
            assert entries[0].amount_cents==1000 and entries[1].amount_cents==amount-1000
        assert db.scalar(select(func.sum(GroupSettlementEntry.amount_cents)))==0
    report=reports.reconciled(client,'finance_corrections',amount-1000)
    assert report['metrics']['cash_in_cents']==amount and report['metrics']['cash_out_cents']==0


def test_member_cross_store_spend_and_correction_hold_do_not_destroy_consumption(client):
    a,b=g.seed(amount=5000),g.seed(2,amount=5000)
    member=g.issue(client,a);g.cmd(client,member,'topup',g.topup_values(a,1000))
    g.switch(client,2);g.link(client,b,member['identity_id']);login(client,'finance')
    hold=g.cmd(client,member,'reserve',g.reserve_values(b,400));g.cmd(client,member,'capture',g.reservation_values(b,hold))
    g.switch(client,1);customer={'id':a['customer_id']}
    correction(client,customer,399,'member',a['account_id'],status=409)
    row=f.approve(client,correction(client,customer,700,'member',a['account_id']))
    assert g.wallet(client,member)['reserved_cents']==300
    g.switch(client,2)
    g.cmd(client,member,'reserve',g.reserve_values(b,301),409)
    assert client.get(f.API+'/'+str(row['case']['id'])).status_code==404
    g.switch(client,1);f.command(client,row,'execute',f.proof(client,row))
    assert g.wallet(client,member)['balance_cents']==300
    with SessionLocal() as db:
        from app.group_models import GroupPaymentLink
        assert db.scalar(select(func.sum(GroupPaymentLink.amount_cents)))==400


def test_member_corrected_original_account_and_amount_control_real_refund(client):
    a=g.seed();member=g.issue(client,a);topup=g.cmd(client,member,'topup',g.topup_values(a,1000));login(client,'finance')
    other=bank(client);post(client,correction(client,{'id':a['customer_id']},700,'member',other))
    g.cmd(client,member,'refund_request',g.refund_request_values(a,topup,701),409)
    request=g.cmd(client,member,'refund_request',g.refund_request_values(a,topup,700));login(client,'manager')
    approved=g.cmd(client,member,'refund_approve',g.refund_review_values(a,request));login(client,'finance')
    g.cmd(client,member,'refund',g.refund_payment_values(a,approved),409)
    g.cmd(client,member,'refund',{**g.refund_payment_values(a,approved),'account_id':other})
    assert g.wallet(client,member)['balance_cents']==0


@pytest.mark.parametrize('kind',['advance','member'])
def test_already_partly_refunded_principal_can_correct_remaining_record_without_erasing_real_refund(client,kind):
    if kind=='advance':
        _,_,customer=f.ready_retail(client);original,account=f.advance(client,customer,1000)
        a=f.current_advance(client,customer);refund=f.approve(client,f.create(client,customer,'advance_refund',{'advance_id':a['id'],'advance_version':a['version'],'amount_cents':200}))
        f.command(client,refund,'execute',f.proof(client,refund,account_id=account,reference='ACTUAL-PARTIAL-BEFORE-FIX'))
    else:
        a=g.seed();member=g.issue(client,a);original=g.cmd(client,member,'topup',g.topup_values(a,1000));customer={'id':a['customer_id']};account=a['account_id'];login(client,'finance')
        request=g.cmd(client,member,'refund_request',g.refund_request_values(a,original,200));login(client,'manager')
        refund=g.cmd(client,member,'refund_approve',g.refund_review_values(a,request));login(client,'finance')
        g.cmd(client,member,'refund',g.refund_payment_values(a,refund))
    correction(client,customer,199,kind,account,status=409)
    other=bank(client);post(client,correction(client,customer,600,kind,other))
    assert recorded(client,customer,kind)['balance_cents']==400
    if kind=='advance':
        a=f.current_advance(client,customer);refund=f.approve(client,f.create(client,customer,'advance_refund',{'advance_id':a['id'],'advance_version':a['version'],'amount_cents':400}))
        f.command(client,refund,'execute',f.proof(client,refund,account_id=other,reference='ACTUAL-CORRECTED-REMAINDER'))
    else:
        request=g.cmd(client,member,'refund_request',g.refund_request_values(a,original,400));login(client,'manager')
        refund=g.cmd(client,member,'refund_approve',g.refund_review_values(a,request));login(client,'finance')
        g.cmd(client,member,'refund',{**g.refund_payment_values(a,refund),'account_id':other})
    with SessionLocal() as db:
        cash=list(db.scalars(select(CashEntry)));assert len(cash)==5
        assert cash[1].direction=='out' and cash[1].amount_cents==200 and cash[1].account!=cash[-1].account
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in cash)==0


def test_effective_member_refund_projection_keeps_history_and_hides_accounts_from_service(client):
    customer,member,_,account=member_topup(client);other=bank(client)
    post(client,correction(client,customer,700,'member',other))
    data=client.get('/api/group/members/'+str(member['id'])).json()
    original=next(e for e in data['entries'] if e['purpose']=='topup')
    assert original['amount_cents']==1000 and original['account_id']==account
    effective=data['effective_topups'][0]
    assert effective['effective_amount_cents']==effective['available_refund_cents']==700 and effective['account_id']==other and effective['corrected']
    login(client,'service');data=client.get('/api/group/members/'+str(member['id'])).json()
    assert data['effective_topups'][0]['effective_amount_cents']==700
    assert all(k not in data['effective_topups'][0] for k in ('account_id','account_name','reference','cash_id'))
    assert all('account_id' not in e for e in data['entries'])


def test_formal_original_entity_and_cash_context_survive_repeated_corrections(client):
    from tests import test_business_entities as be,test_business_entity_domains as domains
    rev,account=be.setup_policy(client)
    customer=f.master(client,'customers',{'name':'完全合成更正主体客户','phone':'13900446655','contact_allowed':True,'note':''})
    prepaid,_=f.advance(client,customer,1000,account['id'])
    row=post(client,correction(client,customer,700,account=account['id']))
    second=post(client,correction(client,customer,600,account=account['id']))
    contexts,cash=domains.contexts()
    assert contexts[row['case']['id']]['source_case_id']==prepaid['case']['id']
    assert contexts[second['case']['id']]['source_case_id']==row['case']['id']
    assert {c['revision_id'] for c in contexts.values()}=={rev['revision_id']}
    assert len(cash)==5 and domains.restore()['verified_entity_cash']==5


@pytest.mark.parametrize('action',['cancel','reject'])
def test_correction_approval_holds_and_releases_without_cash(client,action):
    _,_,customer=f.ready_retail(client);_,account=f.advance(client,customer,1000)
    row=correction(client,customer,400,account=account)
    f.command(client,row,'approve',f.proof(client,row),403)
    row=f.approve(client,row);assert f.current_advance(client,customer)['reserved_cents']==600
    a=f.current_advance(client,customer)
    f.create(client,customer,'advance_refund',{'advance_id':a['id'],'advance_version':a['version'],'amount_cents':401},409)
    login(client,'manager');f.command(client,row,action,{'reason':'复核未完成更正并明确释放'})
    assert f.current_advance(client,customer)['reserved_cents']==0
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==1


def test_duplicate_stale_role_cross_store_and_conflicting_request_are_rejected(client):
    _,_,customer=f.ready_retail(client);_,account=f.advance(client,customer,1000)
    origin=recorded(client,customer);values={'original_cash_id':origin['cash_id'],'source_version':origin['source_version']-1,'amount_cents':0}
    # The public schema rejects version zero; use a legitimately stale positive version.
    row=correction(client,customer,400,account=account);row=f.approve(client,row)
    values['source_version']=origin['source_version'];f.create(client,customer,'stored_correction',values,409)
    login(client,'sales');f.create(client,customer,'stored_correction',values,403);login(client,'finance')
    current=f.detail(client,row);body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],'values':f.proof(client,row)}
    result=f.command(client,row,'execute',body=body);assert f.command(client,row,'execute',body=body)==result
    f.command(client,row,'execute',body={**body,'request_id':uuid.uuid4().hex},status=409)
    f.command(client,row,'execute',body={**body,'values':{**body['values'],'reason':'同请求号不同内容必须拒绝'}},status=409)
    login(client)
    with SessionLocal() as db:
        db.add(Store(id=2,code='CORRECTION-B',name='合成更正乙店'));db.flush();db.add(UserStore(user_id=db.scalar(select(User.id).where(User.username=='admin')),store_id=2));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get(f.API+'/'+str(row['case']['id'])).status_code==404
    f.create(client,customer,'stored_correction',values,404)


def test_competing_correction_approvals_reserve_original_once(client):
    _,_,customer=f.ready_retail(client);_,account=f.advance(client,customer,1000)
    rows=[correction(client,customer,300,account=account) for _ in range(2)];bodies=[]
    for row in rows:
        d=f.detail(client,row);bodies.append({'request_id':uuid.uuid4().hex,'version':d['order']['version'],'case_version':d['case']['version'],'values':f.proof(client,row)})
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'manager')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda i:clients[i].post(f.API+f"/{rows[i]['case']['id']}/actions/approve",json=bodies[i]).status_code,range(2)))
    assert sorted(results)==[200,409]
    assert f.current_advance(client,customer)['reserved_cents']==700


def test_member_correction_and_original_refund_approvals_cannot_reserve_same_principal(client):
    a=g.seed();member=g.issue(client,a);topup=g.cmd(client,member,'topup',g.topup_values(a,1000))
    login(client,'finance');fix=correction(client,{'id':a['customer_id']},300,'member',a['account_id'])
    refund=g.cmd(client,member,'refund_request',g.refund_request_values(a,topup,800))
    d=f.detail(client,fix)
    bodies=[{'request_id':uuid.uuid4().hex,'version':d['order']['version'],'case_version':d['case']['version'],'values':f.proof(client,fix)},
        {'request_id':uuid.uuid4().hex,'version':g.wallet(client,member)['version'],'values':g.refund_review_values(a,refund)}]
    urls=[f.API+f"/{fix['case']['id']}/actions/approve",f"/api/group/members/{member['id']}/actions/refund_approve"]
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'manager')
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda i:clients[i].post(urls[i],json=bodies[i]).status_code,range(2)))
    assert sorted(statuses)==[200,409]
    assert g.wallet(client,member)['reserved_cents'] in {700,800}
    assert g.wallet(client,member)['balance_cents']==1000


def supplier_target(c,amount=400):
    item,loc,_=wh.setup(c,3000,1000)
    with SessionLocal() as db:original=db.scalar(select(StockMove.id).where(StockMove.item_id==item,StockMove.purpose=='wh_other_in'))
    returned=wh.create(c,'other_in_return',item,1000,src=loc,original=original);wh.approve(c,returned);returned=wh.execute(c,returned)
    supplier=wh.typed(c,'suppliers',{'code':'TARGET-REVISION','name':'合成应退目标供应方'})
    row=f.approve(c,f.create(c,None,'other_return',{'stock_move_id':returned['stock_moves'][0]['id'],'source_version':returned['version'],'supplier_id':supplier['id'],'amount_cents':amount}))
    return row,bank(c)


def target_adjust(c,row,amount,status=201):
    d=f.detail(c,row)
    return f.create(c,None,'other_return_adjust',{'receivable_id':d['return_target']['receivable_id'],'source_version':d['case']['version'],'amount_cents':amount},status)


def approve_target(c,row,source):return f.approve(c,row,source['case'])


def test_supplier_target_revision_blocks_collection_until_applied_and_keeps_original(client):
    source,account=supplier_target(client)
    source=f.command(client,source,'collect',f.proof(client,source,amount_cents=150,account_id=account,reference='original-supplier-part'))
    from app.flow_models import Task
    from datetime import timedelta
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.case_id==source['case']['id'],Task.key=='business_finance_execute'))
        task.due_date+=timedelta(days=7);handed_due,handed_owner=task.due_date,task.assignee_id;db.commit()
    # Lowering below actual receipts is handled by the explicit supplier refund branch.
    adjustment=approve_target(client,target_adjust(client,source,250),source)
    f.command(client,source,'collect',f.proof(client,source,amount_cents=1,account_id=account,reference='paused-during-correction'),409)
    f.command(client,adjustment,'execute',f.proof(client,adjustment,source_versions=f.versions(client,source['case'])))
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.case_id==source['case']['id'],Task.key=='business_finance_execute'))
        assert (task.due_date,task.assignee_id)==(handed_due,handed_owner)
    source=f.detail(client,source);assert source['return_target']['original_amount_cents']==400 and source['return_target']['target_cents']==250
    f.command(client,source,'collect',f.proof(client,source,amount_cents=100,account_id=account,reference='supplier-final'))
    with SessionLocal() as db:assert db.scalar(select(FinanceReturnReceivable.amount_cents))==400
    reports.reconciled(client,'finance_other_returns',0)
    # A later approved upward revision reopens only the remaining original target.
    higher=approve_target(client,target_adjust(client,source,300),source)
    f.command(client,higher,'execute',f.proof(client,higher,source_versions=f.versions(client,source['case'])))
    assert f.detail(client,source)['order']['status']=='approved'
    reports.reconciled(client,'finance_other_returns',50)
    # Reopening a fully paid source must give the actual finance employee a task.
    f.command(client,source,'collect',f.proof(client,source,amount_cents=50,account_id=account,reference='actual-newly-confirmed-target'))
    assert f.detail(client,source)['order']['status']=='completed'


def test_zero_supplier_target_and_cancelled_adjustment_do_not_create_cash(client):
    source,account=supplier_target(client)
    cancelled=approve_target(client,target_adjust(client,source,0),source)
    f.command(client,cancelled,'cancel',{'reason':'取消尚未应用的目标更正'})
    assert f.detail(client,source)['return_target']['target_cents']==400
    applied=approve_target(client,target_adjust(client,source,0),source)
    f.command(client,applied,'execute',f.proof(client,applied,source_versions=f.versions(client,source['case'])))
    assert f.detail(client,source)['order']['status']=='completed'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_generic_false_receipt_can_be_voided_without_zero_cash_or_actual_refund(client):
    source,_,customer=f.ready_retail(client);account=f.bank(client);retail.pay(client,source,600,account)
    with SessionLocal() as db:cash_id=db.scalar(select(CashEntry.id))
    row=f.approve(client,f.create(client,customer,'correction',{'original_cash_id':cash_id,'amount_cents':0,'allocations':[]}))
    f.command(client,row,'execute',f.proof(client,row,source_versions=f.versions(client,source)))
    assert retail.detail(client,source)['totals']['cash_paid_cents']==0
    with SessionLocal() as db:
        facts=list(db.scalars(select(CashEntry)));assert len(facts)==2 and all(c.amount_cents==600 for c in facts)
    report=reports.reconciled(client,'finance_corrections',-600)
    assert report['metrics']['cash_in_cents']==report['metrics']['cash_out_cents']==0


@pytest.mark.parametrize('kind',['agency','insurance','addon'])
def test_typed_business_false_receipt_void_preserves_original_tender_sources(client,kind):
    if kind=='agency':
        from tests import test_service_orders as domain
        row,item,payee=domain.setup(client);row=domain.authorized(client,domain.approved(client,domain.quoted(client,row,item)))
        account=f.bank(client);row=domain.cash(client,row,'receive',100,account)
    elif kind=='insurance':
        from tests import test_insurance_orders as domain
        row,_,_=domain.setup(client);row=domain.ready(client,row);account=f.bank(client);row=domain.cash(client,row,'receive',100,account)
    else:
        from tests import test_addon_orders as domain
        row,items,work,_,_=domain.setup(client);row=domain.authorized(client,domain.approved(client,domain.quoted(client,row,items,work)))
        account=f.bank(client);row=domain.pay(client,row,100,account)
    with SessionLocal() as db:cash_id=db.scalar(select(PaymentLink.cash_id).where(PaymentLink.case_id==row['id'],PaymentLink.direction=='in'))
    customer_id=f.source_detail(client,row)['customer_id']
    login(client,'finance');fix=f.approve(client,f.create(client,{'id':customer_id},'correction',{'original_cash_id':cash_id,'amount_cents':0,'allocations':[]}))
    f.command(client,fix,'execute',f.proof(client,fix,source_versions=f.versions(client,row)))
    with SessionLocal() as db:
        links=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==row['id'])))
        assert len(links)==2 and sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in links)==0
        assert next(p for p in links if p.direction=='out').original_id==next(p for p in links if p.direction=='in').id


@pytest.mark.parametrize('tamper',['principal','corrected_cash','request','target'])
def test_offline_restore_refuses_rewritten_correction_facts(client,tamper):
    if tamper=='target':
        source,_=supplier_target(client);row=approve_target(client,target_adjust(client,source,300),source)
        f.command(client,row,'execute',f.proof(client,row,source_versions=f.versions(client,source['case'])))
    else:
        _,_,customer=f.ready_retail(client);_,account=f.advance(client,customer,1000)
        post(client,correction(client,customer,700,account=account))
    sql={'principal':"UPDATE business_finance_advance_entries SET amount_cents=amount_cents-1 WHERE purpose='correction'",
        'corrected_cash':"UPDATE cash_entries SET amount_cents=amount_cents+1 WHERE category='business_finance_stored_corrected'",
        'request':"UPDATE business_finance_stored_correction_requests SET corrected_amount_cents=corrected_amount_cents+1",
        'target':"UPDATE business_finance_return_target_revisions SET original_amount_cents=original_amount_cents+1"}[tamper]
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);validate_business_finance_sqlite(restored);restored.execute(sql)
        with pytest.raises(ValueError,match='财务'):validate_business_finance_sqlite(restored)
