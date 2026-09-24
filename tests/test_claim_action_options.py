"""Read-only claim action candidates reconcile plans, original cash and permission scope."""
import uuid
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import CashEntry,Store
from app.flow_models import PaymentLink
from tests.conftest import login
from tests.test_claims import (technician,reimbursement,cash,cmd,payload,proof,detail,create,assessed,external,completed,reviewed,return_plan)


def options(client,row,action,plan=None,status=200):
    response=client.get(f"/api/claims/{row['id']}/options/{action}",params={'plan_id':plan} if plan else {})
    assert response.status_code==status,response.text
    return response.json()


def counts():
    with SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(CashEntry)),db.scalar(select(func.count()).select_from(PaymentLink)))


def mixed_plan(client,row,selections):
    row=cmd(client,row,'return_plan',{'reason':'混合原款分别返还','selections':selections,'evidence_id':proof(client,row)})
    plan=row['return_plans'][-1]['id']
    login(client,'manager');row=cmd(client,row,'return_approve',{'plan_id':plan,'evidence_id':proof(client,row)});login(client)
    return row,plan


def test_claim_candidates_point_to_missing_cash_without_mutating_business(client):
    row,_,_,_=reimbursement(client,'customer_via_store')
    before=counts();version=detail(client,row)['version']
    login(client,'finance')
    result=options(client,row,'pass_pay')
    assert not result['items'] and not result['can_continue']
    assert result['next_action']=='pass_receive' and '尚未登记报销款到店' in result['message']
    assert counts()==before and detail(client,row)['version']==version
    options(client,row,'return_plan',status=403)


def test_mixed_claim_return_candidates_follow_action_and_other_approved_holds(client):
    row,_,account,_=reimbursement(client,'customer_via_store')
    row=cash(client,row,'pass_receive',3000,account);incoming=row['cash'][-1]['id']
    row=cash(client,row,'pass_pay',1000,account,original_id=incoming);payout=row['cash'][-1]['id']
    row,plan=mixed_plan(client,row,[{'original_id':incoming,'amount_cents':1200},{'original_id':payout,'amount_cents':600}])
    row,other=return_plan(client,row,incoming,500)
    before=counts();current=detail(client,row)
    assert next(p for p in current['cash'] if p['id']==incoming)['remaining_cents']==2000
    assert [(p['id'],p['remaining_cents']) for p in options(client,row,'pass_pay')['items']]==[(incoming,300)]
    assert [(p['id'],p['remaining_cents']) for p in options(client,row,'customer_return',plan)['items']]==[(payout,600)]
    unused=options(client,row,'unused_refund',plan)['items']
    assert [(p['id'],p['remaining_cents']) for p in unused]==[(incoming,1200)]
    assert unused[0]['reference'] and unused[0]['business_date'] and unused[0]['account_id']==account and unused[0]['account_name']
    missing=options(client,row,'party_return',plan)
    assert missing['next_action']=='customer_return' and missing['next_plan_id']==plan
    assert counts()==before and detail(client,row)['version']==current['version']
    cmd(client,row,'customer_return',{'plan_id':plan,'original_id':incoming,'amount_cents':1,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':proof(client,row,True)},409)
    cmd(client,row,'unused_refund',{'plan_id':plan,'original_id':payout,'amount_cents':1,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':proof(client,row,True)},409)
    assert counts()==before
    row=cash(client,row,'unused_refund',400,account,plan_id=plan,original_id=incoming)
    assert options(client,row,'unused_refund',plan)['items'][0]['remaining_cents']==800
    assert options(client,row,'pass_pay')['items'][0]['remaining_cents']==300
    row=cash(client,row,'customer_return',200,account,plan_id=plan,original_id=payout);returned=row['cash'][-1]['id']
    assert options(client,row,'customer_return',plan)['items'][0]['remaining_cents']==400
    assert [(p['id'],p['remaining_cents']) for p in options(client,row,'party_return',plan)['items']]==[(returned,200)]
    assert options(client,row,'party_return',other)['items']==[]
    body=payload(client,row,{'plan_id':plan,'original_id':returned,'amount_cents':100,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':proof(client,row,True)})
    row=cmd(client,row,'party_return',body=body);assert cmd(client,row,'party_return',body=body)==row
    cmd(client,row,'party_return',body={**body,'request_id':uuid.uuid4().hex},status=409)
    assert options(client,row,'party_return',plan)['items'][0]['remaining_cents']==100
    with SessionLocal() as db:
        links=list(db.scalars(select(PaymentLink).where(PaymentLink.case_id==row['id'])))
        assert sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in links)==1700


def test_claim_projection_keeps_account_read_role_store_and_plan_boundaries(client):
    row,source,account,payer=reimbursement(client,'customer_via_store')
    row=cash(client,row,'pass_receive',3000,account);incoming=row['cash'][-1]['id'];row,plan=return_plan(client,row,incoming,500)
    login(client,'service');result=options(client,row,'return_plan')
    assert result['items'] and all('account_name' not in p and 'account_id' not in p for p in result['items'])
    options(client,row,'unused_refund',plan,status=403)
    login(client,'inventory');options(client,row,'return_plan',status=403)
    login(client);other,_=create(client,source,'customer_direct',payer=payer)
    options(client,other,'direct_return',plan,status=409)
    with SessionLocal() as db:db.add(Store(id=2,code='CLAIM-OPTIONS-B',name='合成乙店'));db.commit()
    assert client.get(f"/api/claims/{row['id']}/options/pass_pay",headers={'X-Store-ID':'2'}).status_code==404
    assert client.get(f"/api/claims/{row['id']}/options/pass_pay",headers={'X-Store-ID':'all'}).status_code==409


def test_no_cash_resolution_still_requires_original_application_evidence(client):
    source,_,payer=completed(client,True);row,_=create(client,source,payer=payer)
    row=external(client,assessed(client,row,4997),3000,'partial')
    projection=options(client,row,'resolution')
    assert projection['can_continue'] and projection['required_amount_cents']==0 and projection['items']==[]
    row=cmd(client,row,'resolution',{'internal_bearer':'本店承担','refunds':[],'reason':'未到账差额转内部承担','evidence_id':proof(client,row)})
    row=reviewed(client,row,'resolution_approve');before=counts()
    result=options(client,row,'thirdparty_refund')
    assert not result['can_continue'] and result['next_action']=='resolution_apply' and '无需退款' in result['message']
    cmd(client,row,'resolution_apply',{},422)
    assert counts()==before and detail(client,row)['phase']=='resolution_execute'
    row=cmd(client,row,'resolution_apply',{'evidence_id':proof(client,row,True)})
    assert row['phase']=='completed' and counts()==before


def test_direct_return_projection_subtracts_other_plan_and_actual_returns(client):
    row,_,_,_=reimbursement(client)
    row=cmd(client,row,'direct_confirm',{'amount_cents':3000,'evidence_id':proof(client,row,True)});original=row['customer_payments'][0]['id']
    row,plan=return_plan(client,row,original,1200);row,other=return_plan(client,row,original,800)
    assert options(client,row,'return_plan')['items'][0]['remaining_cents']==1000
    item=options(client,row,'direct_return',plan)['items'][0]
    assert item['remaining_cents']==1200 and 'account_id' not in item
    before=counts();row=cmd(client,row,'direct_return',{'plan_id':plan,'original_id':original,'amount_cents':400,'evidence_id':proof(client,row,True)})
    assert options(client,row,'direct_return',plan)['items'][0]['remaining_cents']==800
    assert options(client,row,'direct_return',other)['items'][0]['remaining_cents']==800
    assert counts()==before


def test_original_thirdparty_refund_candidates_shrink_by_actual_partial_refunds(client):
    from tests.test_repair_orders import receive
    source,account,payer=completed(client,True)
    source=receive(client,source,source['allocations'][1],4997,account)
    row,_=create(client,source,payer=payer);row=external(client,assessed(client,row,4997),3000,'partial')
    originals=options(client,row,'resolution')
    assert originals['required_amount_cents']==1997 and len(originals['items'])==1
    original=originals['items'][0]['id']
    row=cmd(client,row,'resolution',{'internal_bearer':'本店承担','refunds':[{'original_id':original,'amount_cents':1997}],'reason':'原实收款部分退回','evidence_id':proof(client,row)})
    row=reviewed(client,row,'resolution_approve')
    assert options(client,row,'thirdparty_refund')['items'][0]['remaining_cents']==1997
    row=cash(client,row,'thirdparty_refund',1000,account,original_id=original)
    assert options(client,row,'thirdparty_refund')['items'][0]['remaining_cents']==997
    row=cash(client,row,'thirdparty_refund',997,account,original_id=original)
    result=options(client,row,'thirdparty_refund')
    assert result['items']==[] and result['next_action']=='resolution_apply'
