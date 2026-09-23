"""Claim facts never turn an external approval into cash or rewrite repair history."""
import uuid
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import User,UserStore,Store,CashEntry
from app.flow_models import PaymentLink,Case
from app.claims_models import ClaimCustomerPayment,ClaimCash,ClaimResponsibility,ClaimAssessment
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import evidence,master
from tests.test_repair_orders import setup,ready,allocate,receive,typed,quote,authorize,cmd as repair_cmd,detail as repair_detail
from tests.test_procurement import bank

API='/api/claims'
@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        u=User(username='technician',display_name='理赔维修技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));db.commit()
def detail(c,row):
    r=c.get(API+'/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def create(c,source,route='repair_receivable',party='insurer',payer=None,status=201):
    if not payer:
        payer=typed(c,'insurers',{'code':'CL-'+uuid.uuid4().hex[:8],'name':'合成理赔保险公司'}) if party=='insurer' else master(c,'references',{'category':'厂家','name':'合成理赔厂家','active':True,'detail':'测试专用'})
    r=c.post(API,json={'request_id':uuid.uuid4().hex,'source_case_id':source['id'],'source_version':repair_detail(c,source)['version'],
        'party_type':party,'payment_route':route,'payer_id':payer['id'] if party!='internal' else None,'payer_name':'门店内部承担' if party=='internal' else '', 'reason':'合成核损核赔办理'})
    assert r.status_code==status,r.text;return r.json(),payer
def payload(c,row,values,key=None):
    current=detail(c,row);return {'request_id':key or uuid.uuid4().hex,'version':current['version'],'source_version':current['source_version'],'values':values}
def cmd(c,row,action,values=None,status=200,body=None):
    r=c.post(API+f"/{row['id']}/actions/{action}",json=body or payload(c,row,values or {}));assert r.status_code==status,r.text;return r.json()
def proof(c,row,financial=False):return evidence(c,row,'receipt' if financial else 'authorization')
def reviewed(c,row,action='approve',values=None):
    previous=c.get('/api/auth/me').json()['username'];login(c,'manager')
    values=values or {'reason':'独立主管实际核对本次原件','evidence_id':proof(c,row)}
    row=cmd(c,row,action,values);login(c,previous);return row
def assessed(c,row,amount=3000):
    line=detail(c,row)['source_lines'][0]
    row=cmd(c,row,'assess',{'lines':[{'line_id':line['id'],'quantity_milli':line['quantity_milli'],'amount_cents':amount}],'reason':'按原实际维修明细核损定价'})
    return reviewed(c,row)
def external(c,row,approved=3000,outcome='approved'):
    row=cmd(c,row,'transmit',{'submitted_on':today().isoformat(),'external_reference':uuid.uuid4().hex,'evidence_id':proof(c,row)})
    a=row['assessments'][-1];lines=[{'line_id':a['lines'][0]['line_id'],'quantity_milli':a['lines'][0]['quantity_milli'],'amount_cents':approved}] if approved else []
    return cmd(c,row,'result',{'transmission_id':row['transmissions'][-1]['id'],'outcome':outcome,'lines':lines,'result_on':today().isoformat(),'result':'经办人核对实际外部通知结果','evidence_id':proof(c,row)})
def completed(c,split=False):
    row,item,work,_=setup(c);row=ready(c,row,item,work);payer=typed(c,'insurers',{'code':'CL-SOURCE','name':'原维修保险公司'})
    splits=[{'payer_type':'customer','amount_cents':6000},{'payer_type':'insurer','payer_id':payer['id'],'amount_cents':4997}] if split else None
    row=allocate(c,row,splits);account=bank(c);row=receive(c,row,row['allocations'][0],row['allocations'][0]['amount_cents'],account)
    row=repair_cmd(c,row,'release',{'evidence_id':evidence(c,row)});return row,account,payer
def reimbursement(c,route='customer_direct',amount=3000):
    source,account,payer=completed(c);row,_=create(c,source,route,payer=payer);row=external(c,assessed(c,row,amount),amount)
    return reviewed(c,row,'reimbursement_approve'),source,account,payer
def cash(c,row,action,amount,account,**extra):
    return cmd(c,row,action,{'amount_cents':amount,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':proof(c,row,True),**extra})
def return_plan(c,row,original,amount):
    row=cmd(c,row,'return_plan',{'reason':'客户与第三方协商原路径返还','selections':[{'original_id':original,'amount_cents':amount}],'evidence_id':proof(c,row)})
    plan=row['return_plans'][-1]
    previous=c.get('/api/auth/me').json()['username'];login(c,'manager');row=cmd(c,row,'return_approve',{'plan_id':plan['id'],'evidence_id':proof(c,row)});login(c,previous)
    return row,plan['id']

def test_external_approval_no_cash_supplement_and_allocate_binding(client):
    source,item,work,_=setup(client);source=ready(client,source,item,work);row,payer=create(client,source);row=assessed(client,row)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(CashEntry))
    row=external(client,row,0,'need_documents');first=row['results'][-1]
    cmd(client,row,'transmit',{'submitted_on':today().isoformat(),'external_reference':'bad','evidence_id':proof(client,row)},409)
    row=cmd(client,row,'transmit',{'submitted_on':today().isoformat(),'external_reference':'补件外部单号','supplement_result_id':first['id'],'evidence_id':proof(client,row)})
    a=row['assessments'][-1];row=cmd(client,row,'result',{'transmission_id':row['transmissions'][-1]['id'],'outcome':'partial','lines':[{'line_id':a['lines'][0]['line_id'],'quantity_milli':1000,'amount_cents':2500}], 'result_on':today().isoformat(),'result':'实际部分核准','evidence_id':proof(client,row)})
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==before
    repair_cmd(client,source,'allocate',{'labor_cost_cents':0,'evidence_id':evidence(client,source),'allocations':[{'payer_type':'customer','amount_cents':10997}]},409)
    source=allocate(client,source,[{'payer_type':'customer','amount_cents':8497},{'payer_type':'insurer','payer_id':payer['id'],'amount_cents':2500}])
    row=detail(client,row);assert row['phase']=='bound' and row['bindings'][0]['approved_cents']==2500
    source=receive(client,source,source['allocations'][1],2500,bank(client));assert detail(client,row)['phase']=='completed'

def test_rejected_claim_preserves_result_and_no_external_receivable(client):
    source,item,work,_=setup(client);source=ready(client,source,item,work);row,_=create(client,source);row=external(client,assessed(client,row),0,'rejected')
    source=allocate(client,source);assert detail(client,row)['phase']=='completed';assert source['allocations'][0]['payer_type']=='customer'

def test_direct_customer_reimbursement_and_partial_original_return_no_company_cash(client):
    row,source,account,payer=reimbursement(client)
    with SessionLocal() as db:cash_before=db.scalar(select(func.count()).select_from(CashEntry))
    row=cmd(client,row,'direct_confirm',{'amount_cents':3000,'evidence_id':proof(client,row,True)});assert row['phase']=='completed'
    payment=row['customer_payments'][0];row,plan=return_plan(client,row,payment['id'],1000)
    cmd(client,row,'direct_return',{'plan_id':plan,'original_id':payment['id'],'amount_cents':1001,'evidence_id':proof(client,row,True)},409)
    row=cmd(client,row,'direct_return',{'plan_id':plan,'original_id':payment['id'],'amount_cents':400,'evidence_id':proof(client,row,True)})
    cmd(client,row,'return_cancel',{'plan_id':plan,'reason':'不能取消实际返还','evidence_id':proof(client,row)},409)
    row=cmd(client,row,'direct_return',{'plan_id':plan,'original_id':payment['id'],'amount_cents':600,'evidence_id':proof(client,row,True)})
    assert row['reimbursement_usage_cents']==2000 and row['return_plans'][0]['returned_external_cents']==1000
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==cash_before
    assert repair_detail(client,source)['amount_cents']==10997 and repair_detail(client,source)['state']=='completed'

def test_via_store_cash_is_pass_through_and_returns_original_path_in_two_steps(client):
    row,source,account,payer=reimbursement(client,'customer_via_store')
    row=cash(client,row,'pass_receive',3000,account);incoming=row['cash'][0]
    row=cash(client,row,'pass_pay',2000,account,original_id=incoming['id']);row=cash(client,row,'pass_pay',1000,account,original_id=incoming['id'])
    payout=next(x for x in row['cash'] if x['purpose']=='pass_pay');row,plan=return_plan(client,row,payout['id'],2000)
    other=master(client,'accounts',{'name':'另一报销测试银行','account_type':'bank','active':True})['id']
    cmd(client,row,'customer_return',{'plan_id':plan,'original_id':payout['id'],'amount_cents':2000,'account_id':other,'reference':uuid.uuid4().hex,'evidence_id':proof(client,row,True)},409)
    row=cash(client,row,'customer_return',2000,account,plan_id=plan,original_id=payout['id']);returned=row['cash'][-1]
    assert row['reimbursement_usage_cents']==3000
    row=cash(client,row,'party_return',1200,account,plan_id=plan,original_id=returned['id'])
    row=cash(client,row,'party_return',800,account,plan_id=plan,original_id=returned['id']);assert row['reimbursement_usage_cents']==1000
    with SessionLocal() as db:
        payments=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==row['id'])))
        assert sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in payments)==0
        assert len({p.cash_id for p in payments})==6
    assert repair_detail(client,source)['customer_due_cents']==0

def test_late_thirdparty_reduction_refunds_original_then_appends_internal_responsibility(client):
    source,account,payer=completed(client,True);source=receive(client,source,source['allocations'][1],4997,account)
    row,_=create(client,source,payer=payer);row=external(client,assessed(client,row,4997),3000,'partial');payment=next(p for p in row['source_payments'] if p['allocation_id']==source['allocations'][1]['id'])
    row=cmd(client,row,'resolution',{'internal_bearer':'门店承担核赔差额','refunds':[{'original_id':payment['id'],'amount_cents':1997}],'reason':'实际核准调减后由门店承担差额','evidence_id':proof(client,row)})
    row=reviewed(client,row,'resolution_approve');cmd(client,row,'resolution_apply',{'evidence_id':proof(client,row,True)},409)
    row=cash(client,row,'thirdparty_refund',1000,account,original_id=payment['id']);row=cash(client,row,'thirdparty_refund',997,account,original_id=payment['id'])
    row=cmd(client,row,'resolution_apply',{'evidence_id':proof(client,row,True)})
    source=repair_detail(client,source);assert source['amount_cents']==10997 and source['revenue_cents']==9000 and source['receivable_cents']==0
    with SessionLocal() as db:
        adjustments=list(db.scalars(select(ClaimResponsibility)));assert sorted(x.amount_cents for x in adjustments)==[-1997,1997]
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==source['id'],PaymentLink.direction=='out'))==1997

def test_admin_self_approval_stale_replay_and_foreign_original_refused(client):
    source,item,work,_=setup(client);source=ready(client,source,item,work);row,_=create(client,source);line=row['source_lines'][0]
    values={'lines':[{'line_id':line['id'],'quantity_milli':1000,'amount_cents':3000}],'reason':'测试稳定核价请求'};body=payload(client,row,values)
    result=cmd(client,row,'assess',body=body);assert cmd(client,row,'assess',body=body)==result
    stale={**body,'request_id':uuid.uuid4().hex};cmd(client,row,'assess',status=409,body=stale)
    cmd(client,row,'approve',{'reason':'管理员不得自己批准','evidence_id':proof(client,row)},403)
    row=reviewed(client,result);row=external(client,row)
    cmd(client,row,'direct_confirm',{'amount_cents':3000,'evidence_id':proof(client,row,True)},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(ClaimAssessment))==1

def test_two_paths_cannot_reimburse_same_customer_cash_twice(client):
    row,source,account,payer=reimbursement(client,amount=9000)
    other,_=create(client,source,'customer_via_store',payer=payer);other=external(client,assessed(client,other,3000),3000)
    login(client,'manager');cmd(client,other,'reimbursement_approve',{'reason':'核对跨案件剩余额度','evidence_id':proof(client,other)},409);login(client)
    row=cmd(client,row,'close',{'reason':'第三方已撤回尚未付款的额度','evidence_id':proof(client,row)})
    other=reviewed(client,other,'reimbursement_approve');assert other['reimbursement_usage_cents']==3000

def test_cross_store_and_employee_price_scope_refused(client):
    row,source,account,payer=reimbursement(client)
    login(client,'inventory');assert client.get(API+'/'+str(row['id'])).status_code==403
    login(client,'technician');assert client.get(API+'/'+str(row['id'])).status_code==403
    login(client)
    with SessionLocal() as db:db.add(Store(id=2,code='CLAIM-B',name='核赔乙店'));db.commit()
    assert client.get(API+'/'+str(row['id']),headers={'X-Store-ID':'2'}).status_code==404
    assert client.get(API,headers={'X-Store-ID':'all'}).status_code==409

def test_competing_actual_reimbursements_only_one_can_consume_version(client):
    row,source,account,payer=reimbursement(client)
    bodies=[payload(client,row,{'amount_cents':2000,'evidence_id':proof(client,row,True)}) for _ in range(2)]
    # Uploading another proof can touch the Case; take one fresh common version.
    current=detail(client,row)
    for b in bodies:b.update(version=current['version'],source_version=current['source_version'])
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c)
        def post(pair):
            c,body=pair;return c.post(API+f"/{row['id']}/actions/direct_confirm",json=body).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(post,zip(clients,bodies)))
    assert sorted(codes)==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.sum(ClaimCustomerPayment.amount_cents)))==2000

def test_cancel_approved_resolution_before_actual_refund_releases_reservations(client):
    source,account,payer=completed(client,True);source=receive(client,source,source['allocations'][1],4997,account)
    row,_=create(client,source,payer=payer);row=external(client,assessed(client,row,4997),3000,'partial');p=next(p for p in row['source_payments'] if p['allocation_id']==source['allocations'][1]['id'])
    row=cmd(client,row,'resolution',{'internal_bearer':'合成门店','refunds':[{'original_id':p['id'],'amount_cents':1997}],'reason':'核对原核准与原收款差额','evidence_id':proof(client,row)})
    row=reviewed(client,row,'resolution_approve');row=cmd(client,row,'cancel',{'reason':'第三方书面撤回调减结果，保留原承担','evidence_id':proof(client,row)})
    assert row['phase']=='cancelled' and next(x for x in row['source_payments'] if x['id']==p['id'])['remaining_cents']==4997
    assert repair_detail(client,source)['revenue_cents']==10997

def test_partly_paid_customer_unused_thirdparty_cash_refund_and_full_return_chain(client):
    row,source,account,payer=reimbursement(client,'customer_via_store')
    row=cash(client,row,'pass_receive',3000,account);incoming=row['cash'][0]
    row=cash(client,row,'pass_pay',1000,account,original_id=incoming['id']);payout=row['cash'][-1]
    row,unused_plan=return_plan(client,row,incoming['id'],2000)
    cmd(client,row,'pass_pay',{'amount_cents':1,'account_id':account,'reference':uuid.uuid4().hex,'original_id':incoming['id'],'evidence_id':proof(client,row,True)},409)
    row=cash(client,row,'unused_refund',1200,account,plan_id=unused_plan,original_id=incoming['id'])
    cmd(client,row,'return_cancel',{'plan_id':unused_plan,'reason':'实际退款不能删除','evidence_id':proof(client,row)},409)
    row=cash(client,row,'unused_refund',800,account,plan_id=unused_plan,original_id=incoming['id'])
    row=cmd(client,row,'close',{'reason':'未转付部分已实际原路退回第三方','evidence_id':proof(client,row)})
    assert row['reimbursement_usage_cents']==1000 and row['closures'][0]['unused_cents']==2000
    row,paid_plan=return_plan(client,row,payout['id'],1000)
    row=cash(client,row,'customer_return',1000,account,plan_id=paid_plan,original_id=payout['id']);incoming_return=row['cash'][-1]
    row=cash(client,row,'party_return',1000,account,plan_id=paid_plan,original_id=incoming_return['id']);assert row['reimbursement_usage_cents']==0
    with SessionLocal() as db:
        payments=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==row['id'])))
        assert sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in payments)==0
    from app.claims_backup_integrity import validate
    from tests.conftest import TEST_DIR
    import sqlite3
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        assert validate(connection)['verified_claim_cash']==6
        connection.execute('UPDATE claims_closures SET unused_cents=1999')
        with pytest.raises(ValueError,match='不守恒'):validate(connection)
        connection.rollback()

def test_cancel_unused_return_reservation_allows_real_customer_transfer(client):
    row,source,account,payer=reimbursement(client,'customer_via_store')
    row=cash(client,row,'pass_receive',3000,account);incoming=row['cash'][0];row,plan=return_plan(client,row,incoming['id'],3000)
    row=cmd(client,row,'return_cancel',{'plan_id':plan,'reason':'第三方与客户确认继续原转付','evidence_id':proof(client,row)})
    row=cash(client,row,'pass_pay',3000,account,original_id=incoming['id']);assert row['phase']=='completed'

def test_restore_nonempty_responsibility_and_detect_original_cash_or_amount_tamper(client):
    test_late_thirdparty_reduction_refunds_original_then_appends_internal_responsibility(client)
    from app.claims_backup_integrity import validate
    from tests.conftest import TEST_DIR
    import sqlite3
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);assert validate(restored)['verified_claim_cash']==2
        from app.backup_integrity import validate_sqlite
        assert validate_sqlite(restored)['verified_claims']==1
        restored.execute('UPDATE claims_responsibility_entries SET amount_cents=amount_cents+1 WHERE amount_cents>0')
        with pytest.raises(ValueError,match='不守恒'):validate(restored)
        restored.rollback();restored.execute("UPDATE claims_cash SET purpose='pass_pay'")
        with pytest.raises(ValueError):validate(restored)

def test_other_case_evidence_and_reused_actual_proof_refused(client):
    row,source,account,payer=reimbursement(client)
    cmd(client,row,'direct_confirm',{'amount_cents':1000,'evidence_id':evidence(client,source,'receipt')},422)
    fid=proof(client,row,True);row=cmd(client,row,'direct_confirm',{'amount_cents':1000,'evidence_id':fid})
    cmd(client,row,'direct_confirm',{'amount_cents':1000,'evidence_id':fid},409)
    login(client,'service');cmd(client,row,'direct_confirm',{'amount_cents':1000,'evidence_id':fid},403)

def test_quote_replacement_requires_new_assessment_and_actual_old_result_kept(client):
    source,item,work,_=setup(client);source=quote(client,source,item,work);row,_=create(client,source);row=assessed(client,row)
    source=repair_cmd(client,source,'quote_cancel',{'quote_id':repair_detail(client,source)['data']['quote_id'],'reason':'客户调整维修方案'})
    source=quote(client,source,item,work,1000,0)
    cmd(client,row,'transmit',{'submitted_on':today().isoformat(),'external_reference':'旧核价不得发送','evidence_id':proof(client,row)},409)
    row=assessed(client,row,2000);assert len(row['assessments'])==2

def test_manufacturer_and_internal_assessments_bind_only_matching_party(client):
    source,item,work,_=setup(client);source=ready(client,source,item,work);maker=master(client,'references',{'category':'厂家','name':'原单合成厂家','detail':'核价','active':True})
    manufacturer,_=create(client,source,party='manufacturer',payer=maker);manufacturer=external(client,assessed(client,manufacturer,3000),3000)
    internal,_=create(client,source,'internal','internal',payer={'id':0});internal=assessed(client,internal,2000)
    repair_cmd(client,source,'allocate',{'labor_cost_cents':0,'evidence_id':evidence(client,source),'allocations':[{'payer_type':'customer','amount_cents':5997},{'payer_type':'manufacturer','payer_id':maker['id'],'amount_cents':3000},{'payer_type':'internal','payer_name':'另一责任主体','amount_cents':2000}]},409)
    source=allocate(client,source,[{'payer_type':'customer','amount_cents':5997},{'payer_type':'manufacturer','payer_id':maker['id'],'amount_cents':3000},{'payer_type':'internal','payer_name':'门店内部承担','amount_cents':2000}])
    assert detail(client,internal)['phase']=='completed' and detail(client,manufacturer)['phase']=='bound'

def test_manufacturer_rejection_and_other_party_original_allocation_refused(client):
    source,item,work,_=setup(client);source=ready(client,source,item,work)
    maker=master(client,'references',{'category':'厂家','name':'原生产厂家','detail':'真实原核价主体','active':True})
    other=master(client,'references',{'category':'厂家','name':'另一家生产厂家','detail':'不能顶替原主体','active':True})
    source=allocate(client,source,[{'payer_type':'customer','amount_cents':5997},{'payer_type':'manufacturer','payer_id':maker['id'],'amount_cents':5000}])
    account=bank(client);source=receive(client,source,source['allocations'][0],5997,account);source=repair_cmd(client,source,'release',{'evidence_id':evidence(client,source)})
    wrong,_=create(client,source,party='manufacturer',payer=other);wrong=external(client,assessed(client,wrong,5000),5000)
    cmd(client,wrong,'bind',{'evidence_id':proof(client,wrong)},409)
    cmd(client,wrong,'resolution',{'internal_bearer':'门店核对差额','refunds':[],'reason':'不能借另一厂家承担','evidence_id':proof(client,wrong)},409)
    wrong=cmd(client,wrong,'cancel',{'reason':'单位错误撤回，保留原申请历史','evidence_id':proof(client,wrong)})
    row,_=create(client,source,party='manufacturer',payer=maker);row=external(client,assessed(client,row,5000),0,'rejected')
    row=cmd(client,row,'resolution',{'internal_bearer':'门店承担厂家拒赔','refunds':[],'reason':'厂家实际拒赔，客户不追加付款','evidence_id':proof(client,row)})
    row=reviewed(client,row,'resolution_approve');row=cmd(client,row,'resolution_apply',{'evidence_id':proof(client,row,True)})
    current=repair_detail(client,source);assert current['state']=='completed' and current['revenue_cents']==5997 and current['customer_due_cents']==0
    assert current['claims_internal_absorption']==[{'payer_name':'门店承担厂家拒赔','amount_cents':5000}]

def test_two_claims_competing_reimbursement_approvals_share_source_version(client):
    source,account,payer=completed(client);a,_=create(client,source,'customer_direct',payer=payer);a=external(client,assessed(client,a,8000),8000)
    b,_=create(client,source,'customer_via_store',payer=payer);b=external(client,assessed(client,b,8000),8000)
    login(client,'manager');bodies=[payload(client,row,{'reason':'独立核对跨案件原款额度','evidence_id':proof(client,row)}) for row in (a,b)]
    current=repair_detail(client,source)
    for body in bodies:body['source_version']=current['version']
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'manager')
        def post(pair):
            index,c=pair;return c.post(API+f"/{(a,b)[index]['id']}/actions/reimbursement_approve",json=bodies[index]).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(post,enumerate(clients)))
    assert sorted(codes)==[200,409]

def test_restore_rejects_return_using_unselected_same_case_payout(client):
    row,source,account,payer=reimbursement(client)
    row=cmd(client,row,'direct_confirm',{'amount_cents':1500,'evidence_id':proof(client,row,True)})
    row=cmd(client,row,'direct_confirm',{'amount_cents':1500,'evidence_id':proof(client,row,True)})
    first,second=row['customer_payments'];row,plan=return_plan(client,row,first['id'],500)
    cmd(client,row,'direct_return',{'plan_id':plan,'original_id':second['id'],'amount_cents':500,'evidence_id':proof(client,row,True)},409)
    row=cmd(client,row,'direct_return',{'plan_id':plan,'original_id':first['id'],'amount_cents':500,'evidence_id':proof(client,row,True)})
    from app.claims_backup_integrity import validate
    from tests.conftest import TEST_DIR
    import sqlite3
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        assert validate(connection)['verified_claim_direct_facts']==3
        connection.execute("UPDATE claims_customer_payments SET original_id=? WHERE purpose='return'",(second['id'],))
        with pytest.raises(ValueError,match='方案之外'):validate(connection)
