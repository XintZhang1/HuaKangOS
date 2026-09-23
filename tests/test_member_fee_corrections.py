"""Real fee sources; recording corrections do not change membership contracts."""
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal
from app.models import CashEntry
from app.flow_models import Case,Account
from app.membership_models import MembershipFee,MembershipPeriod,MembershipPeriodVoid
from app.membership_fee_correction_models import MembershipFeeCorrectionRequest,MembershipFeeCorrection,MembershipFeeRefundBasis
from tests.conftest import login,TEST_DIR
from tests.test_workflow import master,evidence
from tests import test_membership_lifecycle as m,test_group_membership as g


@pytest.fixture(autouse=True)
def independent_restore():
    yield
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source_db,sqlite3.connect(':memory:') as copied:
        source_db.backup(copied);validate_sqlite(copied)


def setup_paid(c,*,accounts=None):
    login(c,'admin');customer,member=m.setup(c);free=m.rule(c);m.renew(c,customer,free)
    login(c,'admin');rule=m.rule(c,fee_cents=19900)
    account=accounts[0] if accounts else master(c,'accounts',{'name':'续会原实际账户','account_type':'bank','active':True})
    alternate=accounts[1] if accounts else master(c,'accounts',{'name':'续会核对实际账户','account_type':'bank','active':True})
    login(c,'service');order=m.create(c,customer,'renew',{'rule_id':rule['id']})
    login(c,'manager');m.cmd(c,order,'approve');login(c,'finance')
    order=m.cmd(c,order,'execute',{'evidence_id':m.proof(c,order),'account_id':account['id'],'reference':'FEE-'+uuid.uuid4().hex,'reason':'本人确认实际收到未来续会费'})
    period=m.info(c,customer)['periods'][-1]
    with SessionLocal() as db:
        fee=db.scalar(select(MembershipFee).where(MembershipFee.case_id==order['case']['id']))
        return dict(customer=customer,member=member,account=account,alternate=alternate,period=period,fee_id=fee.id,original_cash_id=fee.cash_id,order=order)


def source(c,s):
    r=c.get('/api/business-finance/receipts',params={'customer_id':s['customer']['id']});assert r.status_code==200,r.text
    return next(x for x in r.json()['items'] if x.get('fee_id')==s['fee_id'])


def detail(c,r):
    response=c.get('/api/business-finance/orders/'+str(r['case']['id']));assert response.status_code==200,response.text
    return response.json()


def create_body(c,s,account=None,reference=None):
    current=source(c,s)
    return {'request_id':uuid.uuid4().hex,'customer_id':s['customer']['id'],'purpose':'fee_correction',
        'values':{'fee_id':s['fee_id'],'original_cash_id':current['cash_id'],'source_version':current['source_version'],
            'account_id':(account or s['alternate'])['id'],'reference':reference or 'FIX-'+uuid.uuid4().hex},'reason':'核对原会费账户及凭证录入错误，原会期不变'}


def correction(c,s,*,account=None,reference=None):
    login(c,'finance');r=c.post('/api/business-finance/orders',json=create_body(c,s,account,reference))
    assert r.status_code==201,r.text;return r.json()


def action_body(c,r,action,values=None):
    current=detail(c,r)
    return {'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'values':values or {'evidence_id':evidence(c,{'id':r['case']['id']},'receipt' if action=='execute' else 'evidence'),'reason':'本人核对冻结同额账户凭证更正'}}


def act(c,r,action,*,body=None,status=200):
    response=c.post(f"/api/business-finance/orders/{r['case']['id']}/actions/{action}",json=body or action_body(c,r,action))
    assert response.status_code==status,response.text;return response.json()


def approve(c,r):
    login(c,'manager');return act(c,r,'approve')


def post(c,r):
    login(c,'finance');return act(c,r,'execute')


def refund(c,s,*,account=None):
    login(c,'finance')
    if account is None:
        with SessionLocal() as db:
            from app.membership_fee_corrections import effective_fee
            fee=db.scalar(select(MembershipFee).where(MembershipFee.id==s['fee_id']))
            account={'id':effective_fee(db,fee).account_id}
    r=m.create(c,s['customer'],'renew_refund',{'period_id':s['period']['id']})
    login(c,'manager');m.cmd(c,r,'approve');login(c,'finance')
    return m.cmd(c,r,'execute',{'account_id':account['id'],'reference':'REFUND-'+uuid.uuid4().hex,'evidence_id':m.proof(c,r),'reason':'本次实际退还未生效原续会费'})


def test_fee_account_reference_chain_keeps_original_period_and_real_refund(client):
    s=setup_paid(client);before=m.info(client,s['customer'])
    r=correction(client,s);approve(client,r);done=post(client,r)
    assert done['fee_correction_fact']['original_cash_id']==s['original_cash_id'] and done['fee_correction_fact']['corrected_cash_id']!=s['original_cash_id']
    assert m.info(client,s['customer'])==before
    current=source(client,s);assert current['account']==s['alternate']['name'] and current['amount_cents']==19900
    r=correction(client,s,reference=current['reference']);approve(client,r);post(client,r)
    with SessionLocal() as db:
        original=db.scalar(select(MembershipFee).where(MembershipFee.id==s['fee_id']))
        assert original.account_id==s['account']['id'] and original.cash_id==s['original_cash_id']
        assert db.scalar(select(func.count()).select_from(MembershipFee))==1
        assert db.scalar(select(func.count()).select_from(MembershipPeriod))==2
        assert db.scalar(select(func.count()).select_from(MembershipFeeCorrection))==2
    refund(client,s)
    with SessionLocal() as db:
        actual=db.scalar(select(MembershipFee).where(MembershipFee.original_id==s['fee_id']))
        assert actual.account_id==s['alternate']['id'] and actual.amount_cents==-19900
        assert db.scalar(select(func.count()).select_from(MembershipPeriodVoid))==1


def test_fee_same_amount_correction_after_actual_refund_keeps_refund_unchanged(client):
    s=setup_paid(client);refund(client,s)
    with SessionLocal() as db:
        old=db.scalar(select(MembershipFee).where(MembershipFee.original_id==s['fee_id']))
        frozen=(old.id,old.cash_id,old.account_id,old.reference,old.amount_cents)
    r=correction(client,s);assert r['fee_correction_request']['refunded_fee_id']==frozen[0]
    approve(client,r);post(client,r)
    with SessionLocal() as db:
        old=db.scalar(select(MembershipFee).where(MembershipFee.original_id==s['fee_id']))
        assert frozen==(old.id,old.cash_id,old.account_id,old.reference,old.amount_cents)
        assert db.scalar(select(func.count()).select_from(MembershipPeriodVoid))==1
    m.create(client,s['customer'],'renew_refund',{'period_id':s['period']['id']},409)


@pytest.mark.parametrize('forbidden', [{'amount_cents':1},{'business_date':'2025-01-01'},{'period_id':999},{'member_id':999}])
def test_fee_no_client_amount_period_member_or_date_override(client,forbidden):
    s=setup_paid(client);body=create_body(client,s);body['values'].update(forbidden)
    assert client.post('/api/business-finance/orders',json=body).status_code==422
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MembershipFeeCorrectionRequest))==0


def test_fee_independent_approval_duplicate_stale_and_frozen_execution(client):
    s=setup_paid(client);login(client,'admin');body=create_body(client,s)
    r=client.post('/api/business-finance/orders',json=body);assert r.status_code==201,r.text;r=r.json()
    assert client.post('/api/business-finance/orders',json=body).json()==r
    act(client,r,'approve',status=403)
    login(client,'manager');approval=action_body(client,r,'approve');act(client,r,'approve',body=approval)
    act(client,r,'approve',body=approval)
    act(client,r,'approve',body={**approval,'request_id':uuid.uuid4().hex},status=409)
    login(client,'finance');execution=action_body(client,r,'execute')
    bad={**execution,'values':{**execution['values'],'amount_cents':1}}
    act(client,r,'execute',body=bad,status=422)
    done=act(client,r,'execute',body=execution);assert act(client,r,'execute',body=execution)==done
    act(client,r,'execute',body={**execution,'request_id':uuid.uuid4().hex},status=409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MembershipFeeCorrection))==1


def test_fee_foreign_files_quarantine_wrong_customer_and_stale_source(client):
    s=setup_paid(client);a=correction(client,s);stale=create_body(client,s);b=correction(client,s)
    assert client.post('/api/business-finance/orders',json=stale).status_code==409
    login(client,'manager');bad=action_body(client,a,'approve');bad['values']['evidence_id']=evidence(client,{'id':b['case']['id']})
    act(client,a,'approve',body=bad,status=422)
    good=action_body(client,a,'approve');fid=good['values']['evidence_id']
    from app.file_security import _authority
    from app.file_security_models import FileSecurity
    with SessionLocal() as db:
        with _authority(db):
            scan=db.scalar(select(FileSecurity).where(FileSecurity.file_id==fid));old_state=scan.state;scan.state='quarantined';db.commit()
    act(client,a,'approve',body=good,status=409)
    with SessionLocal() as db:
        with _authority(db):db.scalar(select(FileSecurity).where(FileSecurity.file_id==fid)).state=old_state;db.commit()
    login(client,'admin');other=master(client,'customers',{'name':'另一本地客户','phone':'13900774466','contact_allowed':True,'note':''})
    body=create_body(client,s);body['customer_id']=other['id'];assert client.post('/api/business-finance/orders',json=body).status_code==409
    approve(client,a);post(client,a)
    login(client,'manager');act(client,b,'approve',status=409)
    act(client,b,'cancel',body=action_body(client,b,'cancel',{'reason':'原款已由另一申请更正，取消旧申请'}))


def test_fee_financial_projection_cross_store_and_readonly_group(client):
    s=setup_paid(client);r=correction(client,s);login(client,'finance');fid=evidence(client,{'id':r['case']['id']})
    from app.models import User,UserStore
    from tests.conftest import PASSWORD_HASH
    with SessionLocal() as db:
        for role in ('reception','customer_service'):
            user=User(username=role,display_name='原款岗位测试'+role,role=role,password_hash=PASSWORD_HASH,must_change_password=False)
            db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1,role=role))
        db.commit()
    for role in ('sales','service','reception','inventory','customer_service'):
        login(client,role)
        assert client.get('/api/business-finance/orders/'+str(r['case']['id'])).status_code in {403,404}
        assert client.get('/api/flow/cases/'+str(r['case']['id'])).status_code in {403,404}
        assert client.get('/api/flow/files/'+str(fid)).status_code in {403,404}
        listing=client.get('/api/business-finance/orders')
        if listing.status_code==200:assert r['case']['id'] not in {v['case_id'] for v in listing.json()['items']}
        else:assert listing.status_code==403
        assert client.get('/api/business-finance/receipts',params={'customer_id':s['customer']['id']}).status_code==403
    login(client,'admin');g.seed(2);g.switch(client,2)
    assert client.get('/api/business-finance/orders/'+str(r['case']['id'])).status_code==404
    g.switch(client,'all');assert client.get('/api/business-finance/orders/'+str(r['case']['id'])).status_code==409
    g.switch(client,1)


def test_fee_pending_refund_and_correction_are_mutually_exclusive_and_cancel_releases(client):
    s=setup_paid(client);r=correction(client,s)
    pending=m.create(client,s['customer'],'renew_refund',{'period_id':s['period']['id']})
    login(client,'manager');act(client,r,'approve',status=409)
    m.cmd(client,pending,'cancel',{'reason':'尚未支付，取消原实际退款申请'})
    approve(client,r);login(client,'finance')
    m.create(client,s['customer'],'renew_refund',{'period_id':s['period']['id']},409)
    act(client,r,'cancel',body=action_body(client,r,'cancel',{'reason':'取消尚未执行的登记更正'}))
    refund(client,s)


def test_fee_parallel_corrections_single_original_source_and_refund_competition(client):
    s=setup_paid(client);a=correction(client,s);b=correction(client,s)
    peers=[TestClient(app),TestClient(app)]
    try:
        bodies=[]
        for c,r in zip(peers,(a,b)):
            login(c,'manager');bodies.append(action_body(c,r,'approve'))
        def compete(i):return peers[i].post(f"/api/business-finance/orders/{(a,b)[i]['case']['id']}/actions/approve",json=bodies[i]).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(compete,(0,1)))
        assert sorted(results)==[200,409]
        selected=(a,b)[results.index(200)];login(peers[0],'finance');execution=action_body(peers[0],selected,'execute');login(peers[1],'finance')
        refund_body={'request_id':uuid.uuid4().hex,'customer_id':s['customer']['id'],'purpose':'renew_refund','values':{'period_id':s['period']['id']},'reason':'同时核对原会费实际退款'}
        def cash_compete(i):
            if i==0:return peers[0].post(f"/api/business-finance/orders/{selected['case']['id']}/actions/execute",json=execution).status_code
            return peers[1].post('/api/membership/orders',json=refund_body).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(cash_compete,(0,1)))
        # If the correction committed first, the later request may legitimately
        # start against its now-current original account; it never pays at create.
        assert results[0]==200 and results[1] in {201,409}
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(MembershipFeeCorrection))==1
            assert db.scalar(select(func.count()).select_from(MembershipFee))==1
    finally:
        for c in peers:c.close()


def test_fee_known_entity_original_inheritance(client):
    from tests import test_business_entities as be
    from app.business_entity_models import CaseEntityContext,CashEntityContext
    from app import business_entity_service as entities
    revision,bank=be.setup_policy(client);alternate=be.account(client,'另一已批准原主体账户')
    be.approved(client,'account_binding',be.account_details(alternate,revision,'SYNTH-SECOND-ACCOUNT'))
    s=setup_paid(client,accounts=(bank,alternate));r=correction(client,s);approve(client,r);post(client,r);actual=refund(client,s)
    with SessionLocal() as db:
        user=be.actor(db)
        with entities.authority(db,user):
            contexts={r.case_id:r for r in db.scalars(select(CaseEntityContext))}
            assert contexts[r['case']['id']].source_case_id==s['order']['case']['id']
            assert contexts[actual['case']['id']].source_case_id==s['order']['case']['id']
            assert contexts[actual['case']['id']].derived_kind=='membership_refund'
            assert contexts[actual['case']['id']].revision_id==revision['revision_id']
            refund_fee=db.scalar(select(MembershipFee).where(MembershipFee.original_id==s['fee_id']))
            cash_context=db.scalar(select(CashEntityContext).where(CashEntityContext.cash_id==refund_fee.cash_id))
            fact=db.scalar(select(MembershipFeeCorrection));assert cash_context.original_cash_id==fact.corrected_cash_id


def test_fee_unknown_historical_cash_cannot_inherit_current_policy(client):
    s=setup_paid(client);refund(client,s);login(client,'admin')
    from tests import test_business_entities as be
    revision=be.revision(client);be.store_binding(client,revision)
    for index,bank in enumerate((s['account'],s['alternate'])):
        with SessionLocal() as db:current={**bank,'version':db.scalar(select(Account.version).where(Account.id==bank['id']))}
        be.approved(client,'account_binding',be.account_details(current,revision,'HISTORIC-FEE-'+str(index)))
    be.approved(client,'policy',{'binding_id':be.config(client)['store_binding']['id'],'policy_version':1});login(client,'finance')
    body=create_body(client,s,account=bank)
    response=client.post('/api/business-finance/orders',json=body)
    assert response.status_code==409 and '主体未知' in response.json()['detail']
    m.create(client,s['customer'],'renew_refund',{'period_id':s['period']['id']},409)
