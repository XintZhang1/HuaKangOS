"""Actual insurance principal and commission, independent approvals and original returns."""
import uuid,sqlite3
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import pytest
from sqlalchemy import select,func
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal,today
from app.models import CashEntry
from app.flow_models import PaymentLink,Case
from app.insurance_models import InsuranceTender,InsurancePassEntry,InsuranceCommissionPayment
from tests.conftest import login,TEST_DIR
from tests.test_workflow import evidence
from tests.test_customer_service import vehicle,customer,care,action as care_action
from tests.test_repair_orders import typed
from tests.test_procurement import bank
API='/api/insurance-orders'
@pytest.fixture(autouse=True)
def insurance_restore():
    yield
    from app.insurance_backup_integrity import validate_insurance_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_insurance_sqlite(restored)
        if restored.execute('SELECT COUNT(*) FROM insurance_quotes').fetchone()[0]:
            restored.execute('UPDATE insurance_quotes SET premium_cents=premium_cents+1 WHERE id=(SELECT MIN(id) FROM insurance_quotes)')
            with pytest.raises(ValueError,match='保险'):validate_insurance_sqlite(restored)
def detail(c,row):
    r=c.get(API+f"/{row['id']}");assert r.status_code==200,r.text;return r.json()
def cmd(c,row,action,values=None,status=200,body=None):
    r=c.post(API+f"/{row['id']}/actions/{action}",json=body or dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values=values or {}));assert r.status_code==status,r.text;return r.json()
def proof(c,row,financial=False):return evidence(c,row,'receipt' if financial else 'authorization')
def setup(c,mode='store_collect',source=None,previous=None,renewal=None,cv=None,creator=None):
    cv=cv or vehicle(c,customer_id=source['customer_id'] if source else None)
    insurer=typed(c,'insurers',{'code':'INS-'+uuid.uuid4().hex[:8],'name':'合成保险公司','license_number':'SYNTHETIC-ONLY','settlement_days':30})
    v=dict(request_id=uuid.uuid4().hex,customer_id=cv['customer_id'],customer_vehicle_id=cv['id'],due_date=today().isoformat(),reason='客户委托门店核价及办理保险',previous_policy_id=previous,renewal_task_id=renewal['id'] if renewal else None,renewal_version=renewal['version'] if renewal else None)
    if source:v.update(source_order_id=source['id'],source_version=source['version'],delivery_blocking=True)
    if creator:login(c,creator)
    r=c.post(API,json=v);assert r.status_code==201,r.text
    q=dict(insurer_id=insurer['id'],insurer_version=insurer['version'],collection_mode=mode,payee_account_name='合成保险公司收款户',payee_account_reference='SYNTHETIC-INSURER-ACCOUNT',lines=[dict(name='交强险',premium_cents=3000),dict(name='商业险',premium_cents=7001)],expected_commission_cents=501,start_date=today().isoformat(),end_date=(today()+timedelta(days=365)).isoformat(),valid_until=(today()+timedelta(days=7)).isoformat(),terms='客户逐项核对险种；真实退保按保险公司批单另行确认',reason='依据本次保险公司报价核对')
    if previous:q['end_date']=(today()+timedelta(days=730)).isoformat()
    row=cmd(c,r.json(),'quote',q);return row,q,cv
def reviewed(c,row,decision='approved'):
    old=c.get('/api/auth/me').json()['username'];login(c,'manager');row=cmd(c,row,'review',dict(decision=decision,reason='本人独立核对本版保费及约定',evidence_id=proof(c,row)));login(c,old);return row
def authorize(c,row):return cmd(c,row,'authorize',dict(quote_id=row['quote']['id'],digest=row['quote']['digest'],evidence_id=proof(c,row)))
def ready(c,row):return authorize(c,reviewed(c,row))
def cash(c,row,action,amount,account,**kw):return cmd(c,row,action,dict(amount_cents=amount,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row,True),**kw))
def issued(c,row,outcome='issued'):
    row=cmd(c,row,'submit',dict(external_reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row)))
    return cmd(c,row,'result',dict(submission_id=row['submissions'][-1]['id'],outcome=outcome,policy_number='POL-'+uuid.uuid4().hex if outcome=='issued' else '',result='核对保险公司实际受理结果',business_date=today().isoformat(),evidence_id=proof(c,row)))
def commission(c,row,target):
    row=cmd(c,row,'commission',dict(target_cents=target,reason='按保险公司实际结算凭据确认',evidence_id=proof(c,row,True)));old=c.get('/api/auth/me').json()['username'];login(c,'manager')
    row=cmd(c,row,'commission_review',dict(confirmation_id=row['commissions'][-1]['id'],decision='approved',reason='独立复核本次实际佣金金额',business_date=today().isoformat(),evidence_id=proof(c,row,True)));login(c,old);return row
def termination(c,row,retained,returns=None):
    if returns is None:
        amount=max(0,row['summary']['customer_paid_cents']-retained);returns=[]
        for t in row['tenders']:
            part=min(amount,t['unrefunded_cents'])
            if part:returns.append(dict(tender_id=t['id'],amount_cents=part));amount-=part
    return cmd(c,row,'termination',dict(retained_cents=retained,returns=returns,external_result='terminated' if row['summary']['issued'] else 'not_issued',reason='客户与保险公司确认终止及保留保费',evidence_id=proof(c,row)))
def apply_plan(c,row):
    plan=row['plans'][-1];old=c.get('/api/auth/me').json()['username'];login(c,'manager')
    row=cmd(c,row,'termination_review',dict(plan_id=plan['id'],decision='approved',reason='独立核对实际退保和原款路径',evidence_id=proof(c,row)));login(c,old)
    row=cmd(c,row,'termination_consent',dict(plan_id=plan['id'],digest=plan['digest'],evidence_id=proof(c,row)))
    return cmd(c,row,'termination_apply',dict(plan_id=plan['id'],evidence_id=proof(c,row,True)))

def test_insurance_actual_premium_and_commission_are_separate(client):
    c=client;row,q,_=setup(c);cmd(c,row,'review',dict(decision='approved',reason='不得审批本人报价',evidence_id=proof(c,row)),409)
    row=ready(c,row);a=bank(c);row=cash(c,row,'receive',10001,a);t=row['tenders'][0]
    row=cash(c,row,'disburse',10001,a,tender_id=t['id']);row=issued(c,row)
    assert row['summary']['confirmed_commission_cents']==0 and row['summary']['expected_commission_cents']==501
    with SessionLocal() as db:assert sum(r.amount_cents*(1 if r.direction=='in' else -1) for r in db.scalars(select(CashEntry)))==0
    row=commission(c,row,499);assert row['summary']['commission_due_cents']==499
    row=cash(c,row,'commission_receive',499,a,confirmation_id=row['commissions'][-1]['id'])
    assert row['state']=='completed' and row['summary']['actual_commission_cents']==499
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PaymentLink))==1
        assert sum(r.amount_cents*(1 if r.direction=='in' else -1) for r in db.scalars(select(CashEntry)))==499

def test_original_insurer_return_customer_refund_and_commission_clawback(client):
    c=client;row,_,_=setup(c);row=ready(c,row);a=bank(c);row=cash(c,row,'receive',10001,a);row=cash(c,row,'disburse',10001,a,tender_id=row['tenders'][0]['id']);row=issued(c,row);row=commission(c,row,501);row=cash(c,row,'commission_receive',501,a,confirmation_id=row['commissions'][-1]['id'])
    row=apply_plan(c,termination(c,row,2000));plan=row['plans'][-1];t=row['tenders'][0]
    values=dict(plan_id=plan['id'],tender_id=t['id'],amount_cents=8001,account_id=a,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row,True))
    cmd(c,row,'refund',values,409)
    row=cash(c,row,'insurer_return',8001,a,original_id=row['pass_entries'][0]['id']);row=cmd(c,row,'refund',values)
    row=commission(c,row,100);row=cash(c,row,'commission_return',401,a,confirmation_id=row['commissions'][-1]['id'],original_id=row['commission_payments'][0]['id'])
    assert row['state']=='completed' and row['summary']['held_principal_cents']==0
    assert row['summary']['customer_paid_cents']==row['summary']['insurer_paid_cents']==2000
    with SessionLocal() as db:assert sum(r.amount_cents*(1 if r.direction=='in' else -1) for r in db.scalars(select(CashEntry)))==100

def test_customer_direct_premium_and_refund_create_no_store_cash(client):
    c=client;row,_,_=setup(c,'customer_direct');row=ready(c,row);a=bank(c)
    cmd(c,row,'receive',dict(amount_cents=10001,account_id=a,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row,True)),409)
    row=cmd(c,row,'direct_paid',dict(amount_cents=10001,external_reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row,True)));row=issued(c,row);row=commission(c,row,0)
    row=apply_plan(c,termination(c,row,0,[]));row=cmd(c,row,'direct_return',dict(original_id=row['direct_entries'][0]['id'],amount_cents=10001,external_reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row,True)));row=commission(c,row,0)
    assert row['state']=='completed'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==db.scalar(select(func.count()).select_from(PaymentLink))==0

def test_quote_change_reject_cancel_and_expired_same_digest_rules(client,monkeypatch):
    from app import insurance_service as service
    c=client;row,q,_=setup(c);row=reviewed(c,row,'rejected');row=cmd(c,row,'quote',{**q,'terms':'客户变更约定后本版重新核对'});row=reviewed(c,row)
    old=row['quote_history'][0]['quote'];cmd(c,row,'authorize',dict(quote_id=old['id'],digest=old['digest'],evidence_id=proof(c,row)),409)
    monkeypatch.setattr(service,'today',lambda:today()+timedelta(days=8));cmd(c,row,'authorize',dict(quote_id=row['quote']['id'],digest=row['quote']['digest'],evidence_id=proof(c,row)),409);monkeypatch.undo()
    row=cmd(c,row,'quote_cancel',{'reason':'客户不再接受当前保险方案'});row=cmd(c,row,'cancel',{'reason':'没有实际提交或资金的取消'})
    assert row['state']=='cancelled' and len(row['quote_history'])==2

def test_pending_submission_supplement_failure_and_termination_outlets(client):
    c=client;row,_,_=setup(c);row=ready(c,row);row=issued(c,row,'need_documents');row=issued(c,row,'rejected')
    cmd(c,row,'cancel',{'reason':'不得抹掉真实外部提交'},409)
    row=apply_plan(c,termination(c,row,0));row=commission(c,row,0)
    assert row['state']=='completed' and len(row['results'])==2

def test_duplicate_stale_cross_store_and_competing_original_disbursement(client):
    c=client;row,q,_=setup(c);body=dict(request_id=uuid.uuid4().hex,version=row['version'],values=q)
    new=cmd(c,row,'quote',body=body);assert cmd(c,row,'quote',body=body)['quote']['id']==new['quote']['id']
    cmd(c,row,'quote',body={**body,'request_id':uuid.uuid4().hex},status=409)
    row=ready(c,new);a=bank(c);row=cash(c,row,'receive',10001,a);proof_id=proof(c,row,True)
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for client in clients:login(client)
        def pay(i):return clients[i].post(API+f"/{row['id']}/actions/disburse",json=dict(request_id=uuid.uuid4().hex,version=row['version'],values=dict(tender_id=row['tenders'][0]['id'],amount_cents=10001,account_id=a,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof_id))).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(pay,range(2)))
    assert sorted(results)==[200,409]
    other=c.post('/api/stores',json={'code':'INS-OTHER','name':'保险隔离店','active':True}).json()['id'];c.headers['X-Store-ID']=str(other)
    assert c.get(API+f"/{row['id']}").status_code==404
    c.headers['X-Store-ID']='all';assert c.get(API).status_code==409
    c.headers['X-Store-ID']='1';login(c,'inventory');assert c.get(API+f"/{row['id']}").status_code==403
    with SessionLocal() as db:assert db.scalar(select(func.sum(InsurancePassEntry.amount_cents)))==10001

def test_renewal_task_and_new_observation_are_explicit_and_customer_scoped(client):
    c=client;row,_,cv=setup(c,'customer_direct');row=ready(c,row);row=issued(c,row);previous=row['results'][0]['id']
    task=care(c,cv['customer_id'],cv['id'],'renewal');task=care_action(c,task,'start')['case']
    renewed,_,_=setup(c,'customer_direct',previous=previous,renewal=task,cv=cv);renewed=ready(c,renewed);renewed=issued(c,renewed)
    assert renewed['order']['previous_policy_id']==previous and renewed['order']['renewal_task_id']==task['id']
    current=c.get('/api/customer-service/cases/'+str(task['id'])).json();assert current['state']=='working'
    assert c.get('/api/customer-service/vehicles/'+str(cv['id'])).json()['observations'][0]['evidence_id']==renewed['results'][0]['evidence_id']

def test_real_advance_apply_and_partial_original_return_never_fabricate_cash(client):
    from tests import test_business_finance as finance
    from app.business_finance_models import FinanceCreditLink
    c=client;row,_,cv=setup(c);row=ready(c,row);customer={'id':cv['customer_id']}
    _,a=finance.advance(c,customer,15000);finance.apply_advance(c,customer,row,10001);row=detail(c,row)
    assert row['summary']['customer_paid_cents']==10001 and row['tenders'][0]['credit_link_id']
    row=cash(c,row,'disburse',8000,a,tender_id=row['tenders'][0]['id']);login(c)
    row=apply_plan(c,termination(c,row,0));p=row['plans'][-1];t=row['tenders'][0]
    row=cmd(c,row,'refund',dict(plan_id=p['id'],tender_id=t['id'],amount_cents=2001,business_date=today().isoformat(),evidence_id=proof(c,row,True)))
    row=cash(c,row,'insurer_return',8000,a,original_id=row['pass_entries'][0]['id'])
    row=cmd(c,row,'refund',dict(plan_id=p['id'],tender_id=t['id'],amount_cents=8000,business_date=today().isoformat(),evidence_id=proof(c,row,True)));row=commission(c,row,0)
    assert row['state']=='completed' and finance.current_advance(c,customer)['balance_cents']==15000
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(FinanceCreditLink.amount_cents)))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==3
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry)))==15000
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:validate_sqlite(db)

def test_customer_monthly_receipt_one_cash_two_insurance_original_allocations(client):
    from tests import test_business_finance as finance
    c=client;one,_,cv=setup(c);one=ready(c,one);two,_,_=setup(c,cv=cv);two=ready(c,two);a=bank(c)
    statement=finance.create(c,{'id':cv['customer_id']},'statement',{'starts_on':today().isoformat(),'ends_on':today().isoformat()});statement=finance.approve(c,statement)
    amounts=[dict(source_case_id=x['source_case_id'],amount_cents=x['due_cents']) for x in statement['lines']]
    assert len(amounts)==2
    finance.command(c,statement,'collect',finance.proof(c,statement,amount_cents=20002,account_id=a,reference=uuid.uuid4().hex,allocations=amounts,source_versions=finance.versions(c,one,two)))
    assert detail(c,one)['summary']['customer_paid_cents']==detail(c,two)['summary']['customer_paid_cents']==10001
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert db.scalar(select(func.count()).select_from(PaymentLink))==2
        assert db.scalar(select(func.count()).select_from(InsuranceTender))==2
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:validate_sqlite(db)

def test_approved_termination_cancel_releases_source_for_disbursement(client):
    c=client;row,_,_=setup(c);row=ready(c,row);a=bank(c);row=cash(c,row,'receive',10001,a);row=termination(c,row,0);p=row['plans'][-1]
    login(c,'manager');row=cmd(c,row,'termination_review',dict(plan_id=p['id'],decision='approved',reason='独立核对撤保原款',evidence_id=proof(c,row)));login(c)
    cmd(c,row,'disburse',dict(tender_id=row['tenders'][0]['id'],amount_cents=10001,account_id=a,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,row,True)),409)
    row=cmd(c,row,'termination_cancel',dict(plan_id=p['id'],reason='客户保留原保险方案'));row=cash(c,row,'disburse',10001,a,tender_id=row['tenders'][0]['id'])
    assert row['summary']['insurer_paid_cents']==10001


def test_shared_bank_reference_competes_across_two_insurance_orders(client):
    c=client;one,_,cv=setup(c);one=ready(c,one);two,_,_=setup(c,cv=cv);two=ready(c,two);account=bank(c)
    rows=[one,two];proofs=[proof(c,r,True) for r in rows];reference='INS-SAME-'+uuid.uuid4().hex
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in rows]
        for other in clients:login(other)
        def receive(i):
            return clients[i].post(API+f"/{rows[i]['id']}/actions/receive",json=dict(request_id=uuid.uuid4().hex,version=rows[i]['version'],values=dict(amount_cents=10001,account_id=account,reference=reference,business_date=today().isoformat(),evidence_id=proofs[i]))).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(receive,range(2)))
    assert sorted(results)==[200,409]
    assert sum(detail(c,r)['summary']['customer_paid_cents'] for r in rows)==10001
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.voucher_no==reference))==1
        assert db.scalar(select(func.count()).select_from(InsuranceTender))==1


def test_original_proof_and_cross_case_receipt_cannot_attest_new_cash(client):
    c=client;one,_,cv=setup(c);one=ready(c,one);two,_,_=setup(c,cv=cv);two=ready(c,two);account=bank(c)
    foreign=proof(c,two,True)
    cmd(c,one,'receive',dict(amount_cents=10001,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=foreign),422)
    fid=proof(c,one,True);one=cmd(c,one,'receive',dict(amount_cents=10001,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=fid))
    cmd(c,one,'disburse',dict(tender_id=one['tenders'][0]['id'],amount_cents=10001,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=fid),409)
    one=termination(c,one,0);plan=one['plans'][-1]
    cmd(c,one,'termination_review',dict(plan_id=plan['id'],decision='approved',reason='管理员也不得审批本人撤保',evidence_id=proof(c,one)),409)
    login(c,'manager');one=cmd(c,one,'termination_review',dict(plan_id=plan['id'],decision='rejected',reason='退保实际依据不足拒绝本版',evidence_id=proof(c,one)));login(c)
    cmd(c,one,'termination_apply',dict(plan_id=plan['id'],evidence_id=proof(c,one,True)),409)
    one=cash(c,one,'disburse',10001,account,tender_id=one['tenders'][0]['id']);assert one['summary']['insurer_paid_cents']==10001


def test_parent_exclusion_uses_request_time_exact_children_and_real_cancel(client):
    from tests.test_workflow import order,action,seed_car,detail as source_detail
    from app.models import Vehicle
    from app.db import utcnow
    from app.insurance_backup_integrity import validate_parent_aftercare_exclusions
    c=client;parent=action(c,order(c),'approve');parent=action(c,parent,'allocate',{'vehicle_id':seed_car()})
    with SessionLocal() as db:vin=db.scalar(select(Vehicle.vin).where(Vehicle.id==parent['vehicle_id']))
    cv=vehicle(c,customer_id=parent['customer_id'],vin=vin);row,_,_=setup(c,source=parent,cv=cv)
    before_cancel=utcnow().isoformat();row=cmd(c,row,'cancel',{'reason':'客户尚未授权也未实际投保，取消委托'})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        with pytest.raises(ValueError,match='尚未独立终止'):validate_parent_aftercare_exclusions(db,parent['id'],[row['id']],before_cancel)
        assert validate_parent_aftercare_exclusions(db,parent['id'],[row['id']],utcnow().isoformat())
        with pytest.raises(ValueError,match='清单'):validate_parent_aftercare_exclusions(db,parent['id'],[],utcnow().isoformat())
        with pytest.raises(ValueError,match='清单'):validate_parent_aftercare_exclusions(db,parent['id'],[row['id'],row['id']],utcnow().isoformat())
    other,_,_=setup(c,'customer_direct',source=source_detail(c,parent),cv=cv);other=ready(c,other)
    other=cmd(c,other,'direct_paid',dict(amount_cents=4000,external_reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,other,True)))
    other=apply_plan(c,termination(c,other,0));other=cmd(c,other,'direct_return',dict(original_id=other['direct_entries'][0]['id'],amount_cents=4000,external_reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=proof(c,other,True)))
    before_commission=utcnow().isoformat();other=commission(c,other,0)
    assert other['state']=='completed'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        with pytest.raises(ValueError,match='实际佣金结算依据'):validate_parent_aftercare_exclusions(db,parent['id'],[row['id'],other['id']],before_commission)
        assert validate_parent_aftercare_exclusions(db,parent['id'],[row['id'],other['id']],utcnow().isoformat())


def test_restore_rejects_commission_cash_above_approved_target_even_when_cash_matches(client):
    from app.insurance_backup_integrity import validate_insurance_sqlite
    c=client;row,_,_=setup(c,'customer_direct');row=ready(c,row);row=issued(c,row);row=commission(c,row,501);account=bank(c)
    row=cash(c,row,'commission_receive',501,account,confirmation_id=row['commissions'][-1]['id']);entry=row['commission_payments'][0]
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);validate_insurance_sqlite(db)
        db.execute('UPDATE insurance_commission_payments SET amount_cents=502 WHERE id=?',(entry['id'],));db.execute('UPDATE cash_entries SET amount_cents=502 WHERE id=?',(entry['cash_id'],))
        with pytest.raises(ValueError,match='当时已批准累计金额'):validate_insurance_sqlite(db)


def test_idempotent_receipt_rechecks_current_case_read_authority(client):
    from app.models import User
    from app.flow_models import Task
    c=client;row,q,_=setup(c)
    row=cmd(c,row,'quote_cancel',{'reason':'需要另一经办人重新核对险种'})
    with SessionLocal() as db:
        sales=db.scalar(select(User).where(User.username=='sales'))
        task=db.scalar(select(Task).where(Task.case_id==row['id'],Task.key=='insurance_quote',Task.status=='open'))
        task.assignee_id=sales.id;db.commit()
    login(c,'sales');body=dict(request_id=uuid.uuid4().hex,version=detail(c,row)['version'],values=q)
    url=API+f"/{row['id']}/actions/quote";result=c.post(url,json=body);assert result.status_code==200,result.text
    # The temporary quote task has finished. This employee is neither the case
    # owner nor its creator and has no remaining open responsibility.
    assert c.get(API+f"/{row['id']}").status_code==404
    assert c.post(url,json=body).status_code==404


def test_front_desk_sees_customer_progress_but_not_commission_cash_or_event_payload(client):
    from app.insurance_finance import CASH_CATEGORIES
    c=client;cv=vehicle(c,customer_id=customer(owner='sales'));row,_,_=setup(c,cv=cv,creator='sales');row=ready(c,row);login(c);account=bank(c);row=cash(c,row,'receive',10001,account)
    row=cash(c,row,'disburse',10001,account,tender_id=row['tenders'][0]['id']);row=issued(c,row);row=commission(c,row,499)
    row=cash(c,row,'commission_receive',499,account,confirmation_id=row['commissions'][-1]['id'])
    financial_file=row['commission_payments'][0]['evidence_id']
    login(c,'service');public=detail(c,row)
    assert public['financial_visible'] is False and public['summary']['customer_paid_cents']==10001
    assert 'confirmed_commission_cents' not in public['summary'] and public['commissions']==public['commission_payments']==public['pass_entries']==[]
    assert all('account_id' not in t and 'evidence_id' not in t for t in public['tenders'])
    assert c.get(API+'/catalog',params={'customer_id':row['customer_id']}).json()['accounts']==[]
    generic=c.get('/api/flow/cases/'+str(row['id']));assert generic.status_code==200,generic.text
    event_details=[x['detail'] for x in generic.json()['events']]
    forbidden={'lines','expected_commission_cents','target_cents','amount_cents','account_id','reference','reason','terms','insurer_snapshot','payee_account_reference','evidence_id'}
    assert all(not set(x)&forbidden and not any(isinstance(v,(dict,list)) for v in x.values()) for x in event_details)
    assert all(not set(p)&{'reference','account_id'} for p in generic.json().get('payments',[]))
    assert all(f['category'] not in {'receipt','invoice','procurement_contract'} for f in generic.json()['files'])
    assert c.get('/api/flow/files/'+str(financial_file)).status_code==403
    assert all(len(category)<=CashEntry.__table__.c.category.type.length for category in CASH_CATEGORIES.values())
    login(c,'sales');sales_case=c.get('/api/flow/cases/'+str(row['id']));assert sales_case.status_code==200,sales_case.text
    assert all(f['category']!='receipt' for f in sales_case.json()['files'])
    assert c.get('/api/flow/files/'+str(financial_file)).status_code==403
    login(c,'finance');financial=detail(c,row);assert financial['summary']['actual_commission_cents']==499 and financial['commission_payments']
    assert c.get('/api/flow/files/'+str(financial_file)).status_code==200
