"""Synthetic entitlement units, original refunds, scope and competing settlement."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import User, CashEntry
from app.flow_models import Case, Task
from app.group_models import GroupMember
from app.group_benefits_models import BenefitRule, BenefitWallet, BenefitEntry, BenefitReservation, BenefitSettlement, BenefitPaymentLink, BenefitRefund
from app import group_benefits_service as svc
from app import group_service as group
from app.tenancy import set_scope, project_user
from tests.conftest import login
from tests import test_group_membership as g


def rule(c,kind='coupon',**changes):
    values=dict(code='R'+uuid.uuid4().hex[:12],name='合成'+kind,kind=kind,allowed_store_ids=[1,2],
        credit_cents_per_unit=1000,settlement_cents_per_unit=800,sale_cents_per_unit=800,
        exchange_points_per_unit=100,refund_policy='unused_anytime',discount_bearer='service_store',validity_days=365,service_code='')
    if kind in {'bonus','points'}:
        values.update(credit_cents_per_unit=1 if kind=='bonus' else 2,settlement_cents_per_unit=0,sale_cents_per_unit=0,exchange_points_per_unit=0,refund_policy='none')
    if kind=='package':values['service_code']='SERVICE-JOB'
    values.update(changes)
    response=c.post('/api/group/benefits/rules',json={'request_id':uuid.uuid4().hex,'values':values})
    assert response.status_code==201,response.text
    return response.json()


def setup(c):
    a,b=g.seed(),g.seed(2)
    member=g.issue(c,a)
    g.switch(c,2);g.link(c,b,member['identity_id']);g.switch(c,1)
    return a,b,member


def info(c,setup):
    r=c.get('/api/group/benefits/members',params={'customer_id':setup['customer_id']})
    assert r.status_code==200,r.text
    return r.json()


def command(c,member,action,values,status=200,key=None,version=None):
    response=c.post(f"/api/group/benefits/members/{member['id']}/actions/{action}",json={
        'request_id':key or uuid.uuid4().hex,'version':version or g.wallet(c,member)['version'],'values':values})
    assert response.status_code==status,response.text
    return response.json()


def source(setup):
    return {'case_id':setup['case_id'],'case_version':g.case_version(setup['case_id']),
        'evidence_id':setup['evidence_id'],'reason':'合成客户已核对权益事实'}


def issuance(c,member,setup,rule,units=5,action='purchase'):
    values=source(setup)|{'rule_id':rule['id'],'units':units}
    if action=='purchase':values|={'account_id':setup['account_id'],'reference':uuid.uuid4().hex}
    return command(c,member,action,values)['wallet']


def wvalues(c,setup,wallet):
    current=next(w for w in info(c,setup)['wallets'] if w['id']==wallet['id'])
    return {'wallet_id':current['id'],'wallet_version':current['version'],
            'case_version':g.case_version(setup['case_id']),'reason':'合成权益核对'}


def reserve(c,m,setup,wallet,units=1):
    return command(c,m,'reserve',wvalues(c,setup,wallet)|source(setup)|{'units':units})


def capture(c,m,setup,wallet,reservation):
    r=reservation['reservation']
    return command(c,m,'capture',wvalues(c,setup,wallet)|{'reservation_id':r['id'],
        'reservation_version':r['version'],'evidence_id':setup['evidence_id']})


def refund_request(c,m,setup,wallet,units=1):
    return command(c,m,'refund_request',wvalues(c,setup,wallet)|{'units':units,'evidence_id':setup['evidence_id']})


def refund_values(c,setup,wallet,result):
    return wvalues(c,setup,wallet)|{'refund_id':result['refund']['id'],'refund_version':result['refund']['version']}


def test_coupon_cross_store_capture_reverse_partial_original_refund_cash_once(client):
    a,b,m=setup(client);r=rule(client);wallet=issuance(client,m,a,r)
    login(client,'finance');g.switch(client,2)
    held=reserve(client,m,b,wallet,2);spent=capture(client,m,b,wallet,held)
    reverse=command(client,m,'reverse',wvalues(client,b,wallet)|{'original_id':spent['entry_id'],'units':1,'evidence_id':b['evidence_id']})
    assert reverse['wallet']['balance_units']==4
    g.switch(client,1)
    requested=refund_request(client,m,a,wallet)
    login(client,'manager');approved=command(client,m,'refund_approve',refund_values(client,a,wallet,requested))
    login(client,'finance');paid=command(client,m,'refund',refund_values(client,a,wallet,approved)|{
        'account_id':a['account_id'],'reference':uuid.uuid4().hex,'evidence_id':a['evidence_id']})
    assert paid['wallet']['balance_units']==3 and paid['wallet']['reserved_units']==0
    with SessionLocal() as db:
        cash=list(db.scalars(select(CashEntry)))
        assert len(cash)==2 and sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in cash)==3200
        assert {x.category for x in cash}=={'benefit_purchase','benefit_refund'}
        assert db.scalar(select(func.sum(BenefitSettlement.amount_cents)))==0
        assert db.scalar(select(func.sum(BenefitPaymentLink.amount_cents)))==1000
        set_scope(db,[1],1);u=db.scalar(select(User).where(User.username=='admin'))
        with group.authority(db,u):
            assert db.scalar(select(GroupMember.balance_cents).where(GroupMember.id==m['id']))==0
            assert db.scalar(select(func.sum(BenefitEntry.units)).where(BenefitEntry.wallet_id==wallet['id']))==3


@pytest.mark.parametrize('kind,units,credit',[('bonus',200,200),('points',100,200),('coupon',1,1000)])
def test_gift_types_keep_independent_units_and_never_create_cash(client,kind,units,credit):
    a,b,m=setup(client);r=rule(client,kind,sale_cents_per_unit=0,settlement_cents_per_unit=0);wallet=issuance(client,m,a,r,units,action='grant')
    held=reserve(client,m,a,wallet,units);capture(client,m,a,wallet,held)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert svc.case_paid_amount(db,a['case_id'])==credit
        assert svc.case_reserved_amount(db,a['case_id'])==0


def test_points_adjust_exchange_and_frozen_rate(client):
    a,b,m=setup(client);points=rule(client,'points');coupon=rule(client,'coupon',sale_cents_per_unit=0,settlement_cents_per_unit=0)
    wallet=issuance(client,m,a,points,350,'grant')
    command(client,m,'adjust',wvalues(client,a,wallet)|source(a)|{'units':50})
    command(client,m,'exchange',wvalues(client,a,wallet)|source(a)|{'units':99,'target_rule_id':coupon['id']},422)
    exchanged=command(client,m,'exchange',wvalues(client,a,wallet)|source(a)|{'units':200,'target_rule_id':coupon['id']})
    assert exchanged['wallet']['initial_units']==2 and exchanged['wallet']['source_kind']=='exchange'
    assert next(w for w in info(client,a)['wallets'] if w['id']==wallet['id'])['balance_units']==100
    command(client,m,'refund_request',wvalues(client,a,exchanged['wallet'])|{'units':1,'evidence_id':a['evidence_id']},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_rule_version_frozen_and_old_version_cannot_issue(client):
    a,b,m=setup(client);r=rule(client);w=issuance(client,m,a,r)
    new=rule(client,code=r['code'],credit_cents_per_unit=2000,settlement_cents_per_unit=1500,sale_cents_per_unit=1500)
    assert new['rule_version']==2
    command(client,m,'purchase',source(a)|{'rule_id':r['id'],'units':1,'account_id':a['account_id'],'reference':uuid.uuid4().hex},409)
    captured=capture(client,m,a,w,reserve(client,m,a,w))
    assert captured['reservation']['credit_cents']==1000
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with group.authority(db,user):
            row=db.scalar(select(BenefitRule).where(BenefitRule.id==r['id']));row.sale_cents_per_unit=1
            with pytest.raises(HTTPException):db.flush()


def test_refund_holds_block_consumption_and_cancel_releases_only_refund(client):
    a,b,m=setup(client);w=issuance(client,m,a,rule(client),3)
    held=reserve(client,m,a,w,1)
    requested=refund_request(client,m,a,w,2)
    approved=command(client,m,'refund_approve',refund_values(client,a,w,requested))
    assert approved['wallet']['reserved_units']==3
    command(client,m,'reserve',wvalues(client,a,w)|source(a)|{'units':1},409)
    cancelled=command(client,m,'refund_cancel',refund_values(client,a,w,approved))
    assert cancelled['wallet']['reserved_units']==1
    capture(client,m,a,w,held)


def test_refund_requires_distinct_approval_exact_original_and_replay(client):
    a,b,m=setup(client);w=issuance(client,m,a,rule(client))
    login(client,'finance');request=refund_request(client,m,a,w)
    command(client,m,'refund',refund_values(client,a,w,request)|{'account_id':a['account_id'],'reference':'before-approval','evidence_id':a['evidence_id']},409)
    command(client,m,'refund_approve',refund_values(client,a,w,request),403)
    login(client,'manager');approved=command(client,m,'refund_approve',refund_values(client,a,w,request))
    login(client,'finance');values=refund_values(client,a,w,approved)|{'account_id':a['account_id'],'reference':'real-original','evidence_id':a['evidence_id']}
    command(client,m,'refund',values|{'units':2},422)
    version=g.wallet(client,m)['version'];key=uuid.uuid4().hex
    first=command(client,m,'refund',values,key=key,version=version)
    assert command(client,m,'refund',values,key=key,version=version)==first
    command(client,m,'refund',values,409)


def test_store_roles_file_source_case_and_member_scope_are_enforced(client):
    a,b,m=setup(client);r=rule(client);w=issuance(client,m,a,r)
    g.switch(client,2)
    command(client,m,'purchase',source(b)|{'rule_id':r['id'],'units':1,'account_id':b['account_id'],'reference':'wrong-issuer'},403)
    command(client,m,'reserve',wvalues(client,b,w)|source(b)|{'units':1,'evidence_id':a['evidence_id']},422)
    command(client,m,'refund_request',wvalues(client,b,w)|{'units':1,'evidence_id':b['evidence_id']},409)
    g.switch(client,1);login(client,'sales')
    command(client,m,'reserve',{'wallet_id':w['id'],'wallet_version':w['version'],**source(a),'units':1},403,version=1)
    login(client,'auditor')
    command(client,m,'grant',source(a)|{'rule_id':r['id'],'units':1},403)
    login(client,'manager')
    values={k:v for k,v in r.items() if k not in {'id','issuer_store_id','rule_version'}}
    response=client.post('/api/group/benefits/rules',json={'request_id':uuid.uuid4().hex,'values':values})
    assert response.status_code==403


def test_expired_and_store_restricted_rights_cannot_redeem_but_release_possible(client):
    a,b,m=setup(client);r=rule(client,allowed_store_ids=[1]);w=issuance(client,m,a,r)
    held=reserve(client,m,a,w)
    g.switch(client,2);command(client,m,'reserve',wvalues(client,b,w)|source(b)|{'units':1},409)
    g.switch(client,1)
    # Date moves, bytes/rules/issued expiry remain immutable.
    import app.group_benefits_service as benefits
    from unittest.mock import patch
    from datetime import timedelta
    with patch.object(benefits,'today',return_value=g.today()+timedelta(days=366)):
        command(client,m,'capture',wvalues(client,a,w)|{'reservation_id':held['reservation']['id'],
            'reservation_version':held['reservation']['version'],'evidence_id':a['evidence_id']},409)
        released=command(client,m,'release',wvalues(client,a,w)|{'reservation_id':held['reservation']['id'],
            'reservation_version':held['reservation']['version']})
        assert released['wallet']['reserved_units']==0


def test_competing_benefit_reservations_do_not_overspend(client):
    a,b,m=setup(client);w=issuance(client,m,a,rule(client),1)
    version=g.wallet(client,m)['version'];values=wvalues(client,a,w)|source(a)|{'units':1}
    def run(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
            try:
                svc.command(db,user,m['id'],uuid.uuid4().hex,version,'reserve',values);return 200
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(run,range(2)))==[200,409]
    assert info(client,a)['wallets'][0]['reserved_units']==1


def test_existing_cash_and_principal_holds_share_customer_due(client):
    a,b,m=setup(client);w=issuance(client,m,a,rule(client),15)
    g.cmd(client,m,'topup',g.topup_values(a))
    g.cmd(client,m,'reserve',g.reserve_values(a,9000))
    command(client,m,'reserve',wvalues(client,a,w)|source(a)|{'units':2},409)
    held=reserve(client,m,a,w,1)
    g.cmd(client,m,'reserve',g.reserve_values(a,1),409)
    with SessionLocal() as db:
        assert svc.case_reserved_amount(db,a['case_id'])==1000
        assert group.case_reserved_amount(db,a['case_id'])==9000


def test_unit_precision_large_products_and_direct_central_crud_are_rejected(client):
    a,b,m=setup(client);r=rule(client)
    for units in [1.1,'1',True]:
        command(client,m,'grant',source(a)|{'rule_id':r['id'],'units':units},422)
    large=rule(client,credit_cents_per_unit=100000000,sale_cents_per_unit=100000000,settlement_cents_per_unit=100000000)
    command(client,m,'purchase',source(a)|{'rule_id':large['id'],'units':100000000,'account_id':a['account_id'],'reference':'too-big'},422)
    with SessionLocal() as db:
        with pytest.raises(HTTPException):db.scalar(select(BenefitRule))


def test_benefit_backup_preserves_cash_credit_refund_holds_and_detects_tampering(client):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.benefit_backup_integrity import validate_benefits_sqlite
    a,b,m=setup(client);w=issuance(client,m,a,rule(client),5)
    held=reserve(client,m,a,w,1);capture(client,m,a,w,held)
    reserve(client,m,a,w,1)
    requested=refund_request(client,m,a,w,1)
    command(client,m,'refund_approve',refund_values(client,a,w,requested))
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored)
        result=validate_benefits_sqlite(restored)
        assert result=={'verified_benefit_wallets':1,'verified_benefit_entries':2}
        restored.execute('UPDATE benefit_wallets SET reserved_units=1')
        with pytest.raises(ValueError,match='占额'):validate_benefits_sqlite(restored)
        restored.rollback()
        restored.execute('UPDATE benefit_settlements SET amount_cents=1 WHERE id=(SELECT MIN(id) FROM benefit_settlements)')
        with pytest.raises(ValueError,match='往来'):validate_benefits_sqlite(restored)


@pytest.mark.parametrize('bearer,settlement,group_discount,service_discount',[
    ('service_store',800,0,200),('group',1000,200,0)])
def test_external_recognition_discount_and_internal_clearing_are_distinct(client,bearer,settlement,group_discount,service_discount):
    a,b,m=setup(client);r=rule(client,discount_bearer=bearer,settlement_cents_per_unit=settlement)
    w=issuance(client,m,a,r,2)
    g.switch(client,2);captured=capture(client,m,b,w,reserve(client,m,b,w))
    rows=client.get('/api/group/benefits/reconciliation').json()
    e=next(e for e in rows['entries'] if e['purpose']=='capture')
    assert (e['credit_cents'],e['recognized_cents'],e['external_discount_cents'])==(1000,800,200)
    assert e['group_discount_cents']==group_discount and e['service_discount_cents']==service_discount
    assert sum(s['amount_cents'] for s in rows['settlements'])==0
    command(client,m,'reverse',wvalues(client,b,w)|{'original_id':captured['entry_id'],'units':1,'evidence_id':b['evidence_id']})
    rows=client.get('/api/group/benefits/reconciliation').json()['entries']
    for key in ['credit_cents','recognized_cents','external_discount_cents','group_discount_cents','service_discount_cents']:
        assert sum(e[key] for e in rows)==0


def test_quarantined_evidence_and_unknown_flow_version_cannot_issue(client,monkeypatch):
    from app.config import settings
    from dataclasses import replace
    from app import file_security
    a,b,m=setup(client);r=rule(client)
    status=client.get(f"/api/flow/files/{a['evidence_id']}/security").json()['security']
    monkeypatch.setattr(file_security,'settings',replace(settings,file_scan_mode='quarantine'))
    response=client.post(f"/api/flow/files/{a['evidence_id']}/scan",json={'request_id':uuid.uuid4().hex,'version':status['version']})
    assert response.status_code==200
    command(client,m,'purchase',source(a)|{'rule_id':r['id'],'units':1,'account_id':a['account_id'],'reference':'quarantine'},409)
    with SessionLocal() as db:
        row=db.scalar(select(Case).where(Case.id==a['case_id']));row.flow_version=999;db.commit()
    command(client,m,'purchase',source(a)|{'rule_id':r['id'],'units':1,'account_id':a['account_id'],'reference':'unknown-version'},409)


def test_refund_pending_task_survives_case_completion_and_remains_actionable(client):
    a,b,m=setup(client);w=issuance(client,m,a,rule(client),3)
    requested=refund_request(client,m,a,w)
    approved=command(client,m,'refund_approve',refund_values(client,a,w,requested))
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        row=db.scalar(select(Case).where(Case.id==a['case_id']));row.state='completed'
        from app.flow_engine import close_tasks
        close_tasks(db,row,user);db.commit()
    result=command(client,m,'refund',refund_values(client,a,w,approved)|{
        'account_id':a['account_id'],'reference':'after-case-finish','evidence_id':a['evidence_id']})
    assert result['refund']['status']=='executed'


def test_package_actual_authorized_job_and_mixed_customer_payers_share_capacity(client):
    from tests import test_repair_orders as repair
    row,item,work,customer=repair.setup(client)
    row=repair.ready(client,row,item,work)
    insurer=repair.typed(client,'insurers',{'code':'BEN-INS','name':'权益混合承担合成保险公司'})
    row=repair.allocate(client,row,[{'payer_type':'customer','amount_cents':6000},
        {'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':4997}])
    a={'case_id':row['id'],'customer_id':customer['id'],'account_id':repair.bank(client),
       'evidence_id':repair.evidence(client,row),'store_id':1}
    m=g.issue(client,a)
    package=rule(client,'package',allowed_store_ids=[1],service_code=work['code'],
        credit_cents_per_unit=3000,settlement_cents_per_unit=2400,sale_cents_per_unit=2400)
    w=issuance(client,m,a,package,2)
    command(client,m,'reserve',wvalues(client,a,w)|source(a)|{'units':2},409)
    wrong=rule(client,'package',allowed_store_ids=[1],service_code='OTHER-JOB')
    wrong_wallet=issuance(client,m,a,wrong,1)
    command(client,m,'reserve',wvalues(client,a,wrong_wallet)|source(a)|{'units':1},409)
    held=reserve(client,m,a,w,1)
    g.cmd(client,m,'topup',g.topup_values(a,1000))
    principal=g.cmd(client,m,'reserve',g.reserve_values(a,1000))
    coupon=rule(client,allowed_store_ids=[1],credit_cents_per_unit=2000,sale_cents_per_unit=1600,settlement_cents_per_unit=1600)
    coupon_wallet=issuance(client,m,a,coupon,2)
    coupon_held=reserve(client,m,a,coupon_wallet,1)
    command(client,m,'reserve',wvalues(client,a,coupon_wallet)|source(a)|{'units':1},409)
    capture(client,m,a,w,held)
    capture(client,m,a,coupon_wallet,coupon_held)
    g.cmd(client,m,'capture',g.reservation_values(a,principal))
    current=repair.detail(client,row)
    assert current['customer_due_cents']==0 and current['receivable_cents']==4997
    with SessionLocal() as db:
        assert svc.case_paid_amount(db,row['id'])==5000
        assert group.case_paid_amount(db,row['id'])==1000


def test_package_cannot_pay_other_parts_when_credit_exceeds_its_authorized_job(client):
    from tests import test_repair_orders as repair
    row,item,work,customer=repair.setup(client)
    row=repair.ready(client,row,item,work)
    row=repair.allocate(client,row,[{'payer_type':'customer','amount_cents':10997}])
    a={'case_id':row['id'],'customer_id':customer['id'],'account_id':repair.bank(client),
       'evidence_id':repair.evidence(client,row),'store_id':1}
    m=g.issue(client,a)
    package=rule(client,'package',allowed_store_ids=[1],service_code=work['code'],
        credit_cents_per_unit=10500,settlement_cents_per_unit=9000,sale_cents_per_unit=9000)
    w=issuance(client,m,a,package,1)
    result=command(client,m,'reserve',wvalues(client,a,w)|source(a)|{'units':1},409)
    assert '对应作业金额' in result['detail']
    assert info(client,a)['wallets'][0]['reserved_units']==0


def test_benefit_reports_reconcile_units_discounts_clearing_csv_and_external_amount(client):
    import csv,io
    from decimal import Decimal
    a,b=g.seed(amount=0),g.seed(2,amount=1000)
    m=g.issue(client,a);w=issuance(client,m,a,rule(client),2)
    g.switch(client,2);g.link(client,b,m['identity_id'])
    capture(client,m,b,w,reserve(client,m,b,w))
    with SessionLocal() as db:
        set_scope(db,[2],2)
        row=db.scalar(select(Case).where(Case.id==b['case_id']))
        row.data={**row.data,'released_date':g.today().isoformat()};db.commit()
    local=client.get('/api/flow/analytics').json()
    assert local['metrics']['cash_in_cents']==0
    assert local['metrics']['receivable_cents']==0
    assert local['metrics']['repair_cents']==800
    g.switch(client,'all')
    report=client.get('/api/flow/analytics').json()
    assert report['metrics']['cash_in_cents']==1600
    assert report['metrics']['repair_cents']==800
    assert report['metrics']['receivable_cents']==0
    for dataset in ['benefit_coupon','benefit_redemptions','benefit_clearing']:
        table=report['tables'][dataset]
        export=client.get('/api/flow/analytics/export',params={'dataset':dataset})
        assert export.status_code==200,export.text
        exported=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))))
        assert exported[0]==table['headers']
        assert [[x.removeprefix("'") for x in row] for row in exported[1:]]==[[str(x) for x in r['values']] for r in table['rows']]
        chart=next(c for c in report['charts'] if c['id']==dataset)
        if dataset=='benefit_coupon':
            assert sum(chart['series'][0]['values'])==sum(r['units'] for r in table['rows'])==1
        elif dataset=='benefit_redemptions':
            assert [sum(s['values']) for s in chart['series']]==[800,0,200]
            assert [sum(int(Decimal(r['values'][col])*100) for r in table['rows']) for col in [5,6,7]]==[800,0,200]
        else:
            assert len(chart['labels'])==len(table['rows'])==2
            assert sum(sum(s['values']) for s in chart['series'])==0
            for i,row in enumerate(table['rows']):
                assert [int(Decimal(row['values'][col])*100) for col in [1,2]]==[s['values'][i] for s in chart['series']]
                assert Decimal(row['values'][3])==0
