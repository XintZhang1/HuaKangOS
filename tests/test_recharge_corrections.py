"""Original bundle correction: one principal fact and all original gift units."""
import sqlite3,uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date,timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import CashEntry
from app.backup_integrity import validate_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_recharge_bundles as rb,test_finance_corrections as fc,test_business_finance as f,test_group_benefits as benefits,test_group_membership as g


@pytest.fixture(autouse=True)
def restored():
    yield
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);validate_sqlite(copy)


def fix(c,a,amount,account=None,status=201,**extra):
    source=fc.recorded(c,{'id':a['customer_id']},'bundle')
    return fc.correction(c,{'id':a['customer_id']},amount,'bundle',account or a['account_id'],status=status,
        bundle_purchase_id=source['bundle_purchase_id'],**extra)


@pytest.mark.parametrize('amount',[0,2000,3000,4000])
def test_original_bundle_zero_down_same_up_principal_and_each_frozen_unit(client,amount):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance')
    before=benefits.info(client,a)['wallets'];row=fc.post(client,fix(client,a,amount))
    current=rb.detail(client,purchase)
    assert current['member']['balance_cents']==amount and current['purchase']['shares']==3
    assert current['purchase']['effective_shares']==amount//1000
    assert current['purchase']['refundable_shares']==amount//1000
    after=benefits.info(client,a)['wallets']
    for old,new in zip(sorted(before,key=lambda w:w['id']),sorted(after,key=lambda w:w['id'])):
        assert new['initial_units']==old['initial_units'] and new['expires_on']==old['expires_on']
        assert new['balance_units']==new['effective_issued_units']==old['initial_units']//3*(amount//1000)
        assert new['correction_units']==old['initial_units']//3*(amount//1000-3) and new['reserved_units']==0
    assert len(row['bundle_correction']['components'])==4
    with SessionLocal() as db:
        facts=list(db.scalars(select(CashEntry)));assert len(facts)==(2 if not amount else 3)
        assert facts[0].amount_cents==3000 and sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in facts)==amount


def test_partial_used_gift_preserved_while_complete_unused_share_can_be_corrected(client):
    a,z,member,rule,purchase=rb.setup(client,kinds=('coupon','points'))
    wallet=next(w for w in benefits.info(client,a)['wallets'] if w['rule']['kind']=='coupon')
    g.switch(client,2);login(client,'finance');hold=benefits.reserve(client,member,z,wallet,1);benefits.capture(client,member,z,wallet,hold)
    g.switch(client,1);fix(client,a,0,status=409)
    fc.post(client,fix(client,a,2000))
    after=next(w for w in benefits.info(client,a)['wallets'] if w['id']==wallet['id'])
    assert after['initial_units']==6 and after['correction_units']==-2 and after['balance_units']==3
    assert rb.detail(client,purchase)['purchase']['refundable_shares']==1


def test_existing_real_refund_survives_correction_and_later_refund_uses_effective_account(client):
    a,z,member,rule,purchase=rb.setup(client,kinds=('coupon','points'));login(client,'finance')
    refund=rb.approve(client,rb.refund(client,a,purchase));rb.command(client,refund,'execute',rb.proof(client,refund,account_id=a['account_id'],reference='ACTUAL-OLD-REFUND'))
    fix(client,a,0,status=409)
    other=fc.bank(client);fc.post(client,fix(client,a,2000,account=other))
    current=rb.detail(client,purchase);assert current['purchase']['refunded_shares']==1 and current['purchase']['effective_shares']==2
    assert current['purchase']['refundable_shares']==1 and current['member']['balance_cents']==1000
    refund=rb.approve(client,rb.refund(client,a,purchase))
    rb.command(client,refund,'execute',rb.proof(client,refund,account_id=a['account_id'],reference='WRONG-OLD-ACCOUNT'),409)
    rb.command(client,refund,'execute',rb.proof(client,refund,account_id=other,reference='ACTUAL-EFFECTIVE-REFUND'))
    assert rb.detail(client,purchase)['member']['balance_cents']==0


@pytest.mark.parametrize('action',['cancel','reject'])
def test_cancel_or_reject_releases_principal_and_all_gift_holds(client,action):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance');row=f.approve(client,fix(client,a,1000))
    assert g.wallet(client,member)['reserved_cents']==2000
    assert all(w['reserved_units']==w['initial_units']//3*2 for w in benefits.info(client,a)['wallets'])
    login(client,'manager');f.command(client,row,action,{'reason':'取消未实际应用的原组合误记更正'})
    assert g.wallet(client,member)['reserved_cents']==0
    assert all(w['reserved_units']==0 and w['balance_units']==w['initial_units'] for w in benefits.info(client,a)['wallets'])


def test_bundle_requires_explicit_origin_and_integral_original_share_price(client):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance')
    fc.correction(client,{'id':a['customer_id']},2000,'bundle',a['account_id'],status=409)
    fix(client,a,2500,status=422)
    origin=fc.recorded(client,{'id':a['customer_id']},'bundle')
    f.create(client,{'id':a['customer_id']},'stored_correction',{'original_cash_id':origin['cash_id'],'source_version':origin['source_version'],'bundle_purchase_id':99999,'amount_cents':0},409)


def test_same_amount_bank_change_preserves_every_original_unit_and_lifecycle(client):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance')
    before=benefits.info(client,a)['wallets'];other=fc.bank(client);fc.post(client,fix(client,a,3000,other))
    current=rb.detail(client,purchase)['purchase']
    assert current['original_account']['id']==a['account_id'] and current['effective_account']['id']==other
    assert current['corrected_share_delta']==0
    for old,new in zip(sorted(before,key=lambda r:r['id']),sorted(benefits.info(client,a)['wallets'],key=lambda r:r['id'])):
        assert all(new[k]==old[k] for k in ('initial_units','balance_units','expires_on','correction_units'))
    login(client,'service');data=rb.detail(client,purchase)['purchase']
    assert all(k not in data for k in ('original_account','original_reference','effective_account','effective_reference'))


def test_duplicate_execute_stale_foreign_store_and_wrong_role_keep_single_gift_correction(client):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance');row=f.approve(client,fix(client,a,2000))
    d=f.detail(client,row);body={'request_id':uuid.uuid4().hex,'version':d['order']['version'],'case_version':d['case']['version'],'values':f.proof(client,row)}
    login(client,'service');f.command(client,row,'execute',body=body,status=403)
    login(client,'finance');g.switch(client,2)
    assert client.get(f.API+'/'+str(row['case']['id'])).status_code==404
    g.switch(client,1);f.command(client,row,'execute',body={**body,'case_version':body['case_version']-1},status=409)
    result=f.command(client,row,'execute',body=body);assert f.command(client,row,'execute',body=body)==result
    f.command(client,row,'execute',body={**body,'request_id':uuid.uuid4().hex},status=409)
    from app.business_finance_models import FinanceBundleCorrectionPosting
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(FinanceBundleCorrectionPosting))==4


@pytest.mark.parametrize('competitor',['refund','correction','cross_store_gift'])
def test_competing_approval_or_cross_store_gift_use_cannot_double_spend_bundle(client,competitor):
    a,z,member,rule,purchase=rb.setup(client,kinds=('coupon',));login(client,'finance')
    row=fix(client,a,0 if competitor=='cross_store_gift' else 1000);d=f.detail(client,row)
    paths=[f.API+f"/{row['case']['id']}/actions/approve"]
    bodies=[{'request_id':uuid.uuid4().hex,'version':d['order']['version'],'case_version':d['case']['version'],'values':f.proof(client,row)}]
    if competitor=='refund':
        other=rb.refund(client,a,purchase,2);d2=rb.detail(client,other)
        paths.append(rb.API+f"/orders/{other['case']['id']}/actions/approve")
        bodies.append({'request_id':uuid.uuid4().hex,'version':d2['order']['version'],'case_version':d2['case']['version'],'member_version':d2['member']['version'],'values':rb.proof(client,other)})
    elif competitor=='correction':
        other=fix(client,a,1000);d2=f.detail(client,other)
        paths.append(f.API+f"/{other['case']['id']}/actions/approve")
        bodies.append({'request_id':uuid.uuid4().hex,'version':d2['order']['version'],'case_version':d2['case']['version'],'values':f.proof(client,other)})
    else:
        wallet=benefits.info(client,a)['wallets'][0];g.switch(client,2)
        values=benefits.wvalues(client,z,wallet)|benefits.source(z)|{'units':1};g.switch(client,1)
        paths.append(f"/api/group/benefits/members/{member['id']}/actions/reserve")
        bodies.append({'request_id':uuid.uuid4().hex,'version':g.wallet(client,member)['version'],'values':values})
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for i,c in enumerate(clients):
            login(c,'finance' if competitor=='cross_store_gift' and i==1 else 'manager')
        if competitor=='cross_store_gift':g.switch(clients[1],2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda i:clients[i].post(paths[i],json=bodies[i]).status_code,range(2)))
    assert sorted(statuses)==[200,409]


@pytest.mark.parametrize('stopped',['expired','disabled'])
def test_stopped_original_offer_cannot_add_units_but_can_correct_bank_or_recover_unused(client,monkeypatch,stopped):
    from app.db import today
    a,z,member,rule,purchase=rb.setup(client,sale_ends_on=str(today()+timedelta(days=800)))
    if stopped=='expired':
        from app import recharge_bundle_service as bundle_service,business_finance_bundle_corrections as adapter
        future=date.fromisoformat(benefits.info(client,a)['wallets'][0]['expires_on'])+timedelta(days=1)
        monkeypatch.setattr(bundle_service,'today',lambda:future);monkeypatch.setattr(adapter,'today',lambda:future)
    else:
        values={k:rule[k] for k in ('code','name','principal_cents_per_share','allowed_store_ids','sale_starts_on','sale_ends_on','refund_policy','refund_terms')}
        values['components']=[{'benefit_rule_id':x['benefit_rule']['id'],'units_per_share':x['units_per_share']} for x in rule['components']]
        result=client.post(rb.API+'/rules',json={'request_id':uuid.uuid4().hex,'values':values});assert result.status_code==201,result.text
    login(client,'finance');fix(client,a,4000,status=409)
    fc.post(client,fix(client,a,3000,fc.bank(client)))
    fc.post(client,fix(client,a,2000))
    assert rb.detail(client,purchase)['purchase']['effective_shares']==2


@pytest.mark.parametrize('tamper',['units','expiry','cached','missing_part','missing_tables'])
def test_restore_rejects_bundle_correction_units_expiry_cache_and_missing_component(client,tamper):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance');fc.post(client,fix(client,a,2000))
    sql={'units':'UPDATE business_finance_bundle_correction_components SET delta_units=delta_units-1',
        'expiry':"UPDATE business_finance_bundle_correction_components SET expires_on='2099-01-01'",
        'cached':'UPDATE benefit_wallets SET correction_units=correction_units+1',
        'missing_part':'DELETE FROM business_finance_bundle_correction_components WHERE id=(SELECT MIN(id) FROM business_finance_bundle_correction_components)',
        'missing_tables':None}[tamper]
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);validate_sqlite(copy)
        if sql:copy.execute(sql)
        else:
            for table in ('business_finance_bundle_correction_postings','business_finance_bundle_correction_components','business_finance_bundle_corrections'):copy.execute('DROP TABLE '+table)
        with pytest.raises(ValueError):validate_sqlite(copy)
