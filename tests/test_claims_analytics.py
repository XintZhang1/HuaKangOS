"""Original repair recognition, actual cash and external reimbursement reconcile."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import json,sqlite3
from datetime import timedelta
import pytest
from sqlalchemy import text
from app.db import SessionLocal,today
from app.backup_integrity import validate_sqlite
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app import reconciliation_service as recon
from tests import test_claims as claims,test_service_analytics as analytics,test_reconciliation as monthly
from tests.test_claims import technician
from tests.conftest import login,TEST_DIR
from tests.test_multistore import second_store,switch


def test_direct_reimbursement_is_external_fact_not_second_revenue_or_company_cash(client):
    row,source,account,payer=claims.reimbursement(client)
    row=claims.cmd(client,row,'direct_confirm',{'amount_cents':3000,'evidence_id':claims.proof(client,row,True)})
    row,plan=claims.return_plan(client,row,row['customer_payments'][0]['id'],1000)
    claims.cmd(client,row,'direct_return',{'plan_id':plan,'original_id':row['customer_payments'][0]['id'],
        'amount_cents':1000,'evidence_id':claims.proof(client,row,True)})
    data=analytics.reconciled(client,'claims_external_customer',2000)
    assert data['metrics']['cash_in_cents']==data['metrics']['recorded_business_net_cents']==10997
    assert data['metrics']['cash_out_cents']==0 and data['metrics']['claims_pass_through_balance_cents']==0
    assert not data['tables']['claims_cash']['rows']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:assert validate_sqlite(connection)['verified_claim_direct_facts']==2
    second_store(client);switch(client,2)
    assert not analytics.report(client)['tables']['claims_external_customer']['rows']
    switch(client,'all')
    grouped=analytics.report(client)
    assert grouped['metrics']['claims_external_reimbursement_net_cents']==2000
    assert all(x['route'] is None for x in grouped['tables']['claims_external_customer']['rows'])


def test_actual_unused_refund_and_pending_custody_reconcile_with_cash_once(client):
    row,source,account,payer=claims.reimbursement(client,'customer_via_store')
    row=claims.cash(client,row,'pass_receive',3000,account);incoming=row['cash'][0]
    row=claims.cash(client,row,'pass_pay',1000,account,original_id=incoming['id'])
    analytics.reconciled(client,'claims_payable',2000)
    row,plan=claims.return_plan(client,row,incoming['id'],2000)
    claims.cash(client,row,'unused_refund',2000,account,original_id=incoming['id'],plan_id=plan)
    data=analytics.reconciled(client,'claims_cash',0)
    assert data['metrics']['claims_pass_through_balance_cents']==0
    assert data['metrics']['cash_in_cents']==13997 and data['metrics']['cash_out_cents']==3000
    assert data['metrics']['recorded_business_net_cents']==10997
    assert len(data['tables']['claims_cash']['rows'])==3
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:assert validate_sqlite(connection)['verified_claim_cash']==3


def test_late_reduction_keeps_original_release_and_reconciles_actual_period(client):
    claims.test_late_thirdparty_reduction_refunds_original_then_appends_internal_responsibility(client)
    data=analytics.reconciled(client,'claims_business_adjustments',-1997)
    assert data['metrics']['repair_settlement_net_cents']==data['metrics']['recorded_business_net_cents']==9000
    analytics.reconciled(client,'claims_responsibility',0)
    analytics.reconciled(client,'claims_cash',-1997)
    with SessionLocal() as db:
        # Historical fixture changes original handover date only; APIs already
        # tested frozen immutable facts, and adjustment dates remain today.
        raw=db.execute(text("SELECT id,data FROM flow_cases WHERE kind='repair'")).one()
        values=json.loads(raw.data);values['released_date']=str(today()-timedelta(days=1))
        db.execute(text('UPDATE flow_cases SET data=:data WHERE id=:id'),{'data':json.dumps(values),'id':raw.id});db.commit()
    assert analytics.report(client,date_from=str(today()),date_to=str(today()))['metrics']['repair_settlement_net_cents']==-1997
    prior=str(today()-timedelta(days=1))
    assert analytics.report(client,date_from=prior,date_to=prior)['metrics']['repair_settlement_net_cents']==10997
    with SessionLocal() as db:
        raw=db.execute(text("SELECT id,data FROM flow_cases WHERE kind='repair'")).one()
        values=json.loads(raw.data);values['released_date']=str(today())
        db.execute(text('UPDATE flow_cases SET data=:data WHERE id=:id'),{'data':json.dumps(values),'id':raw.id})
        db.execute(text('UPDATE claims_applications SET business_date=:day'),{'day':prior});db.commit()
    assert analytics.report(client,date_from=prior,date_to=prior)['metrics']['repair_settlement_net_cents']==0
    assert analytics.report(client,date_from=str(today()),date_to=str(today()))['metrics']['repair_settlement_net_cents']==9000


def test_new_monthly_definition_keeps_four_and_detects_rehashed_claim_tampering(client,monkeypatch):
    claims.test_late_thirdparty_reduction_refunds_original_then_appends_internal_responsibility(client)
    original=recon.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(recon,'snapshot',lambda db,user,start,end,definition_version=4:original(db,user,start,end,4))
        old=monthly.batch(client)
    assert old['definition_version']==4 and not any(x['source'].startswith('claims_') for x in old['manifest'])
    new=monthly.cmd(client,old,'recalculate',{'reason':'用明确新定义核对核赔来源'})
    assert new['definition_version']==CURRENT_DEFINITION_VERSION and monthly.get(client,old)['digest']==old['digest']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        manifest=json.loads(json.dumps(new['manifest']))
        next(x for x in manifest if x['source']=='claims_responsibility_entries')['data']['amount_cents']+=1
        restored.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',
            (json.dumps(manifest),recon.digest({'manifest':manifest,'summary':new['summary']}),new['id']))
        with pytest.raises(ValueError,match='不可变原始'):validate_reconciliation_sqlite(restored)


def test_claim_reservation_blocks_customer_refund_and_cash_correction_until_closed(client):
    from tests import test_aftercare as aftercare,test_business_finance as finance
    row,source,account,payer=claims.reimbursement(client)
    original=next(x for x in row['source_payments'] if x['direction']=='in')
    aftercare.create(client,source,status=409)
    finance.create(client,{'id':source['customer_id']},'correction',{'original_cash_id':original['cash_id'],
        'amount_cents':10000,'account_id':account,'reference':'CLAIM-CORRECTION',
        'allocations':[{'source_case_id':source['id'],'amount_cents':10000}]},status=409)
    claims.cmd(client,row,'close',{'reason':'第三方未付款并已撤回批准','evidence_id':claims.proof(client,row)})
    aftercare.create(client,source)


def test_late_claim_reduction_requires_original_invoice_red_not_new_blue(client):
    from tests import test_invoices as invoices
    source,account,payer=claims.completed(client,True)
    source=claims.receive(client,source,source['allocations'][1],4997,account)
    login(client,'finance');blue=invoices.actual(client,source['id'],10997);login(client)
    row,_=claims.create(client,source,payer=payer);row=claims.external(client,claims.assessed(client,row,4997),3000,'partial')
    payment=next(x for x in row['source_payments'] if x['allocation_id']==source['allocations'][1]['id'])
    row=claims.cmd(client,row,'resolution',{'internal_bearer':'门店吸收原核赔差额','refunds':[{'original_id':payment['id'],'amount_cents':1997}],
        'reason':'核准原实际差额','evidence_id':claims.proof(client,row)})
    row=claims.reviewed(client,row,'resolution_approve')
    invoices.create(client,source['id'],1,status=409)
    row=claims.cash(client,row,'thirdparty_refund',1997,account,original_id=payment['id'])
    claims.cmd(client,row,'resolution_apply',{'evidence_id':claims.proof(client,row,True)})
    login(client,'finance')
    red=invoices.actual(client,source['id'],1997,blue['id'])
    assert red['balance']['actual_net_cents']==red['balance']['invoiceable_cents']==9000
    assert red['balance']['correction_cents']==0
