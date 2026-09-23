"""Frozen recharge combinations: one cash source, original gifts, integer shares."""
import uuid, sqlite3
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from sqlalchemy import select, func
from app.db import SessionLocal, today
from app.models import CashEntry, User
from app.flow_models import Case
from app.group_models import GroupMember, GroupEntry
from app.group_benefits_models import BenefitWallet, BenefitEntry
from app.recharge_bundle_models import RechargeBundleRule, RechargeBundleRefund
from app import group_service as group
from app import recharge_bundle_service as service
from app.tenancy import set_scope, project_user
from tests.conftest import login, TEST_DIR
from tests.test_workflow import evidence
from tests import test_group_membership as g, test_group_benefits as b

API='/api/recharge-bundles'

def setup(c, kinds=('bonus','points','coupon','package'), shares=3, **changes):
    a,z,m=b.setup(c)
    gifts=[b.rule(c,kind,sale_cents_per_unit=0,settlement_cents_per_unit=0,refund_policy='none') for kind in kinds]
    unit_counts={'bonus':100,'points':50,'coupon':2,'package':1}
    values={'code':'RB'+uuid.uuid4().hex[:12],'name':'合成组合充值','enabled':True,'principal_cents_per_share':1000,
        'allowed_store_ids':[1,2],'sale_starts_on':str(today()),'sale_ends_on':str(today()+timedelta(days=30)),
        'refund_policy':'whole_unused_anytime','refund_terms':'已核对原批次完整赠品后只按整数份退原本金',
        'components':[{'benefit_rule_id':r['id'],'units_per_share':unit_counts[r['kind']]} for r in gifts],**changes}
    r=c.post(API+'/rules',json={'request_id':uuid.uuid4().hex,'values':values});assert r.status_code==201,r.text
    rule=r.json()
    row=create(c,a,'purchase',{'rule_id':rule['id'],'shares':shares,'terms_accepted':True})
    row=command(c,row,'execute',proof(c,row,account_id=a['account_id'],reference=uuid.uuid4().hex))
    return a,z,m,rule,row

def create(c,a,purpose,values,status=201):
    r=c.post(API+'/orders',json={'request_id':uuid.uuid4().hex,'customer_id':a['customer_id'],'purpose':purpose,'values':values,'reason':'客户明确确认原组合条款'})
    assert r.status_code==status,r.text;return r.json()
def detail(c,row):
    r=c.get(API+'/orders/'+str(row['case']['id']));assert r.status_code==200,r.text;return r.json()
def command(c,row,action,values=None,status=200,body=None):
    current=detail(c,row)
    body=body or {'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'member_version':current['member']['version'],'values':values or {'reason':'明确取消原组合申请'}}
    r=c.post(API+f"/orders/{row['case']['id']}/actions/{action}",json=body);assert r.status_code==status,r.text;return r.json()
def proof(c,row,**extra):return {'reason':'本人核对客户条款和实际到账','evidence_id':evidence(c,row['case'],'receipt'),**extra}
def refund(c,a,purchase,shares=1):return create(c,a,'refund',{'purchase_id':purchase['purchase']['id'],'shares':shares,'terms_accepted':True})
def approve(c,row):
    login(c,'manager');row=command(c,row,'approve',proof(c,row));login(c,'finance');return row
def assert_restore():
    from app.recharge_bundle_integrity import validate_recharge_bundles_sqlite
    from app.benefit_backup_integrity import validate_benefits_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy);validate_recharge_bundles_sqlite(copy);validate_benefits_sqlite(copy)


def test_one_actual_receipt_five_independent_ledgers_and_whole_partial_refund(client):
    a,z,m,rule,row=setup(client)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with group.authority(db,user):
            assert db.scalar(select(func.sum(GroupEntry.amount_cents)))==3000
            assert len(list(db.scalars(select(BenefitWallet))))==4
            assert all(w.source_kind=='grant' and w.cash_id is None for w in db.scalars(select(BenefitWallet)))
    login(client,'finance');r=refund(client,a,row,1);r=approve(client,r)
    assert r['member']['reserved_cents']==1000 and all(p['reserved_units']==p['units_per_share'] for p in r['purchase']['components'])
    r=command(client,r,'execute',proof(client,r,account_id=a['account_id'],reference='one-original-combination-refund'))
    assert r['member']['balance_cents']==2000 and r['member']['reserved_cents']==0
    assert r['purchase']['refunded_shares']==1 and r['purchase']['refundable_shares']==2
    with SessionLocal() as db:
        facts=list(db.scalars(select(CashEntry)))
        assert len(facts)==2 and sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in facts)==2000
        assert {c.category for c in facts}=={'group_member_topup','group_member_refund'}
    assert_restore()


def test_original_partial_use_cannot_borrow_same_rule_gifts_or_bypass_refund(client):
    a,z,m,rule,row=setup(client,kinds=('coupon','points'))
    w=next(w for w in b.info(client,a)['wallets'] if w['rule_id']==rule['components'][0]['benefit_rule']['id'])
    # Three shares carry six coupons; consuming one makes only two shares refundable.
    g.switch(client,2);login(client,'finance');b.capture(client,m,z,w,b.reserve(client,m,z,w,1))
    g.switch(client,1);assert detail(client,row)['purchase']['refundable_shares']==2
    login(client,'admin');gift_rule=rule['components'][0]['benefit_rule'];b.issuance(client,m,a,gift_rule,10,'grant')
    create(client,a,'refund',{'purchase_id':row['purchase']['id'],'shares':3,'terms_accepted':True},409)
    original={'entry_id':row['purchase']['principal_entry_id']}
    g.cmd(client,m,'refund_request',g.refund_request_values(a,original,1000),409)
    points=next(w for w in b.info(client,a)['wallets'] if w['rule_id']==rule['components'][1]['benefit_rule']['id'])
    g.switch(client,2)
    b.command(client,m,'adjust',b.wvalues(client,z,points)|b.source(z)|{'units':1},409)
    g.switch(client,1);r=approve(client,refund(client,a,row,2))
    command(client,r,'execute',proof(client,r,account_id=a['account_id'],reference='two-intact-shares'))
    assert detail(client,row)['purchase']['refundable_shares']==0
    assert_restore()


def test_approval_is_independent_and_cancellation_releases_all_original_holds(client):
    a,z,m,rule,row=setup(client,kinds=('bonus','points'))
    r=refund(client,a,row,2);values=proof(client,r)
    command(client,r,'approve',values,403)  # Admin cannot approve own request.
    login(client,'service');command(client,r,'execute',values|{'account_id':a['account_id'],'reference':'bad-role'},403)
    login(client,'manager');r=command(client,r,'approve',values)
    login(client,'finance');g.switch(client,2)
    g.cmd(client,m,'reserve',g.reserve_values(z,1001),409)
    g.switch(client,1);login(client,'manager');r=command(client,r,'cancel')
    assert r['member']['reserved_cents']==0 and all(c['reserved_units']==0 for c in r['purchase']['components'])
    assert r['member']['balance_cents']==3000
    command(client,r,'approve',values,409)
    assert_restore()


def test_duplicate_stale_cross_store_and_original_account_are_refused(client):
    a,z,m,rule,row=setup(client,kinds=('coupon',))
    login(client,'finance');r=approve(client,refund(client,a,row))
    value=proof(client,r,account_id=a['account_id'],reference='actual-refund-reference')
    current=detail(client,r);body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'member_version':current['member']['version'],'values':value}
    command(client,r,'execute',status=409,body={**body,'case_version':body['case_version']-1})
    from tests.test_procurement import bank
    login(client,'admin');other_account=bank(client);login(client,'finance')
    command(client,r,'execute',value|{'account_id':other_account},409)
    paid=command(client,r,'execute',body=body)
    assert command(client,r,'execute',body=body)==paid
    command(client,r,'execute',value,409)
    g.switch(client,2)
    response=client.get(API+'/orders/'+str(r['case']['id']));assert response.status_code==404
    create(client,z,'refund',{'purchase_id':row['purchase']['id'],'shares':1,'terms_accepted':True},404)
    g.switch(client,1);assert_restore()


def test_disabled_and_frozen_versions_explicit_dates_and_terms(client):
    a,z,m,rule,row=setup(client,kinds=('coupon',))
    values={k:rule[k] for k in ['code','name','principal_cents_per_share','allowed_store_ids','sale_starts_on','sale_ends_on','refund_policy','refund_terms']}
    values['components']=[{'benefit_rule_id':x['benefit_rule']['id'],'units_per_share':x['units_per_share']} for x in rule['components']]
    r=client.post(API+'/rules',json={'request_id':uuid.uuid4().hex,'values':values});assert r.status_code==201,r.text
    assert r.json()['enabled'] is False and r.json()['rule_version']==2
    create(client,a,'purchase',{'rule_id':rule['id'],'shares':1,'terms_accepted':True},409)
    create(client,a,'purchase',{'rule_id':r.json()['id'],'shares':1,'terms_accepted':True},409)
    create(client,a,'refund',{'purchase_id':row['purchase']['id'],'shares':1,'terms_accepted':False},422)
    invalid=client.post(API+'/rules',json={'request_id':uuid.uuid4().hex,'values':values|{'sale_ends_on':'2020-02-30'}});assert invalid.status_code==422
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with group.authority(db,user):
            frozen=db.scalar(select(RechargeBundleRule).where(RechargeBundleRule.id==rule['id']));frozen.enabled=False
            with pytest.raises(HTTPException):db.flush()
    assert_restore()


def test_refund_expiry_rechecked_after_approval_cancellation_still_releases(client,monkeypatch):
    a,z,m,rule,row=setup(client,kinds=('coupon',),refund_policy='whole_unused_before_expiry')
    login(client,'finance');r=approve(client,refund(client,a,row))
    monkeypatch.setattr(service,'today',lambda:today()+timedelta(days=400))
    command(client,r,'execute',proof(client,r,account_id=a['account_id'],reference='expired-approved-refund'),409)
    login(client,'manager');r=command(client,r,'cancel')
    assert r['member']['reserved_cents']==0 and r['purchase']['refundable_shares']==0
    assert_restore()


@pytest.mark.parametrize('competing',['principal','gift','refund'])
def test_two_connection_competing_refund_and_other_store_use_conserve_all_units(client,competing):
    a,z,m,rule,row=setup(client,kinds=('coupon',))
    login(client,'finance');r=refund(client,a,row,2)
    other=refund(client,a,row,2) if competing=='refund' else None
    login(client,'manager');approval_evidence=proof(client,r)
    current=detail(client,r)
    approve_body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'member_version':current['member']['version'],'values':approval_evidence}
    with TestClient(app) as second:
        if competing=='refund':
            login(second,'manager');other_values=proof(second,other);second_current=detail(second,other)
            # Both request snapshots use the same member version, after all evidence uploads.
            approve_body['member_version']=second_current['member']['version']
            second_url=API+f"/orders/{other['case']['id']}/actions/approve"
            second_body={'request_id':uuid.uuid4().hex,'version':second_current['order']['version'],'case_version':second_current['case']['version'],
                'member_version':second_current['member']['version'],'values':other_values}
        else:
            login(second,'finance');g.switch(second,2)
            if competing=='principal':
                second_url=f"/api/group/members/{m['id']}/actions/reserve"
                second_body={'request_id':uuid.uuid4().hex,'version':current['member']['version'],'values':g.reserve_values(z,2000)}
            else:
                wallet=b.info(second,z)['wallets'][0]
                second_url=f"/api/group/benefits/members/{m['id']}/actions/reserve"
                second_body={'request_id':uuid.uuid4().hex,'version':current['member']['version'],
                    'values':b.wvalues(second,z,wallet)|b.source(z)|{'units':3}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(client.post,API+f"/orders/{r['case']['id']}/actions/approve",json=approve_body),pool.submit(second.post,second_url,json=second_body)]
            responses=[f.result() for f in futures]
    assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
    actual=detail(client,row)
    assert actual['member']['balance_cents']==3000
    assert actual['member']['reserved_cents'] in ({0,2000} if competing=='gift' else {2000})
    assert actual['purchase']['components'][0]['reserved_units'] in ({3,4} if competing=='gift' else {0,4})
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy);validate_sqlite(copy)


def test_restore_rejects_frozen_gift_quantity_and_approval_proof_tampering(client):
    a,z,m,rule,row=setup(client,kinds=('coupon',))
    login(client,'finance');r=approve(client,refund(client,a,row))
    from app.recharge_bundle_integrity import validate_recharge_bundles_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy);validate_recharge_bundles_sqlite(copy)
        copy.execute('UPDATE recharge_bundle_refund_components SET units=units+1')
        with pytest.raises(ValueError,match='赠品'):validate_recharge_bundles_sqlite(copy)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy)
        copy.execute("UPDATE group_events SET detail=json_remove(detail,'$.evidence_id') WHERE action='bundle_approve'")
        with pytest.raises(ValueError,match='批准缺少凭据'):validate_recharge_bundles_sqlite(copy)


def test_component_issuance_failure_rolls_back_cash_principal_gifts_and_receipt(client,monkeypatch):
    a,z,m,rule,row=setup(client,kinds=('bonus','points'))
    other=create(client,a,'purchase',{'rule_id':rule['id'],'shares':2,'terms_accepted':True})
    value=proof(client,other,account_id=a['account_id'],reference='rollback-whole-combination')
    current=detail(client,other)
    body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
          'member_version':current['member']['version'],'values':value}
    original=b.svc._issue;calls=[]
    def fail_second(*args,**kwargs):
        calls.append(True)
        if len(calls)==2:raise HTTPException(409,'合成第二赠品失败，整笔事务应回滚')
        return original(*args,**kwargs)
    monkeypatch.setattr(b.svc,'_issue',fail_second)
    command(client,other,'execute',body=body,status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
    current=detail(client,other)
    assert current['member']['balance_cents']==3000 and current['order']['status']=='draft' and current['purchase'] is None
    monkeypatch.setattr(b.svc,'_issue',original)
    done=command(client,other,'execute',body=body)
    assert done['member']['balance_cents']==5000 and done['purchase']['shares']==2
    assert_restore()


def test_new_bundle_points_repay_original_consumption_debt_and_reduce_refund_shares(client):
    from tests import test_retail as retail, test_membership_lifecycle as lifecycle
    items,customer,_,_=retail.setup(client);g.issue(client,{'customer_id':customer['id']})
    point_rule=b.rule(client,'points',allowed_store_ids=[1]);level=lifecycle.rule(client,points_enabled=True,points_benefit_rule_id=point_rule['id'],points_denominator_fen=100)
    lifecycle.renew(client,customer,level);login(client,'admin')
    sale=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)));account=retail.bank(client)
    sale=retail.pay(client,sale,1000,account);sale=retail.dispatch(client,sale);sale=retail.cmd(client,sale,'accept',{'evidence_id':evidence(client,sale)})
    wallet=b.info(client,{'customer_id':customer['id']})['wallets'][0]
    coupon=b.rule(client,'coupon',allowed_store_ids=[1],sale_cents_per_unit=0,settlement_cents_per_unit=0,exchange_points_per_unit=1)
    exchange=lifecycle.create(client,customer,'points_adjust',{'action':'exchange','wallet_id':wallet['id'],'target_rule_id':coupon['id'],'units':10})
    login(client,'finance');lifecycle.cmd(client,exchange,'execute',{'evidence_id':lifecycle.proof(client,exchange),'wallet_version':wallet['version'],'reason':'明确使用全部原消费积分'})
    login(client,'admin');sale,ret=retail.request_return(client,sale,sale['dispatches'][0],500);sale=retail.ret_cmd(client,sale,ret,'return_approve');sale=retail.ret_cmd(client,sale,ret,'return_receive')
    assert lifecycle.info(client,customer)['points_debt_units']==3
    values={'code':'DEBT-COMBO','name':'积分追原组合','enabled':True,'principal_cents_per_share':1000,'allowed_store_ids':[1],
        'sale_starts_on':str(today()),'sale_ends_on':str(today()+timedelta(days=30)),'refund_policy':'whole_unused_anytime',
        'refund_terms':'已确认逐项原赠品完整回收后退还对应本金','components':[{'benefit_rule_id':point_rule['id'],'units_per_share':2}]}
    response=client.post(API+'/rules',json={'request_id':uuid.uuid4().hex,'values':values});assert response.status_code==201,response.text
    assert '须先抵扣' in response.json()['refund_terms']
    a={'customer_id':customer['id']};purchase=create(client,a,'purchase',{'rule_id':response.json()['id'],'shares':2,'terms_accepted':True})
    purchase=command(client,purchase,'execute',proof(client,purchase,account_id=account,reference='points-debt-bundle-original'))
    assert lifecycle.info(client,customer)['points_debt_units']==0
    assert purchase['purchase']['components'][0]['balance_units']==1 and purchase['purchase']['refundable_shares']==0
    create(client,a,'refund',{'purchase_id':purchase['purchase']['id'],'shares':1,'terms_accepted':True},409)
    assert_restore()


@pytest.mark.parametrize('policy',['whole_unused_anytime','whole_unused_before_expiry'])
def test_post_delivery_return_restores_same_bundle_batch_without_extending_expiry(client,monkeypatch,policy):
    from app.models import UserStore
    from tests.conftest import PASSWORD_HASH
    from tests import test_repair_orders as repair, test_aftercare as aftercare
    from tests.test_procurement import bank
    with SessionLocal() as db:
        tech=User(username='technician',display_name='组合测试技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(tech);db.flush();db.add(UserStore(user_id=tech.id,store_id=1));db.commit()
    source,item,work,customer=repair.setup(client);member=g.issue(client,{'customer_id':customer['id']})
    a={'customer_id':customer['id'],'case_id':source['id'],'account_id':bank(client),'evidence_id':evidence(client,source),'store_id':1}
    gift=b.rule(client,'package',allowed_store_ids=[1],service_code=work['code'],sale_cents_per_unit=0,settlement_cents_per_unit=0,refund_policy='none')
    values={'code':'AFTER-COMBO','name':'售后原赠品组合','enabled':True,'principal_cents_per_share':10000,'allowed_store_ids':[1],
        'sale_starts_on':str(today()),'sale_ends_on':str(today()+timedelta(days=10)),'refund_policy':policy,
        'refund_terms':'仅按原购买完整份额同时回收原赠品与本金','components':[{'benefit_rule_id':gift['id'],'units_per_share':1}]}
    response=client.post(API+'/rules',json={'request_id':uuid.uuid4().hex,'values':values});assert response.status_code==201,response.text
    purchase=create(client,a,'purchase',{'rule_id':response.json()['id'],'shares':2,'terms_accepted':True})
    purchase=command(client,purchase,'execute',proof(client,purchase,account_id=a['account_id'],reference='aftercare-bundle-topup'))
    wallet=b.info(client,a)['wallets'][0];expiry=wallet['expires_on']
    source=repair.allocate(client,repair.ready(client,source,item,work))
    benefit_capture=b.capture(client,member,a,wallet,b.reserve(client,member,a,wallet))
    reserved=g.cmd(client,member,'reserve',g.reserve_values(a,9997));principal_capture=g.cmd(client,member,'capture',g.reservation_values(a,reserved))
    source=repair.cmd(client,source,'release',{'evidence_id':evidence(client,source)})
    b.command(client,member,'reverse',b.wvalues(client,a,wallet)|{'original_id':benefit_capture['entry_id'],'units':1,'evidence_id':a['evidence_id']},409)
    assert detail(client,purchase)['purchase']['refundable_shares']==1
    # Clock advancement is scoped to entitlement eligibility; original bytes,
    # expiry fields and performed-service evidence are never rewritten.
    monkeypatch.setattr(b.svc,'today',lambda:today()+timedelta(days=400));monkeypatch.setattr(service,'today',lambda:today()+timedelta(days=400))
    request=aftercare.create(client,source)
    request=aftercare.plan(client,request,10997,[{'kind':'principal','original_id':principal_capture['entry_id'],'units':9997},
                                               {'kind':'benefit','original_id':benefit_capture['entry_id'],'units':1}])
    aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,request)))
    restored=b.info(client,a)['wallets'][0]
    assert restored['id']==wallet['id'] and restored['expires_on']==expiry and restored['balance_units']==2 and restored['expired']
    assert detail(client,purchase)['purchase']['refundable_shares']==(2 if policy=='whole_unused_anytime' else 0)
    if policy=='whole_unused_anytime':
        login(client,'finance');r=approve(client,refund(client,a,purchase,1))
        command(client,r,'execute',proof(client,r,account_id=a['account_id'],reference='return-one-restored-share'))
        assert detail(client,purchase)['member']['balance_cents']==10000
    else:create(client,a,'refund',{'purchase_id':purchase['purchase']['id'],'shares':1,'terms_accepted':True},409)
    assert_restore()
