from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import sqlite3
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import CashEntry,User
from app.flow_models import Case,Task
from app.membership_models import MembershipCard,MembershipPeriod,MembershipFee,PointsClaim,PointsChange,PointsDebt
from app.group_benefits_models import BenefitWallet,BenefitEntry
from tests.conftest import login
from tests.test_workflow import master,evidence
from tests import test_group_membership as g,test_group_benefits as b


def setup(c):
    customer=master(c,'customers',{'name':'会员独立办理客户','phone':'13900559922','contact_allowed':True,'note':''})
    m=g.issue(c,{'customer_id':customer['id']})
    return customer,m
def rule(c,**kw):
    v=dict(code='LV'+uuid.uuid4().hex[:8],name='配置会员级别',enabled=True,allowed_store_ids=[1],validity_months=12,
        fee_cents=0,fee_owner='collecting_store',refund_policy='before_start',points_enabled=False,points_numerator=1,points_denominator_fen=100,points_benefit_rule_id=None)
    v.update(kw);r=c.post('/api/membership/rules',json={'request_id':uuid.uuid4().hex,'values':v});assert r.status_code==201,r.text;return r.json()
def detail(c,r):
    response=c.get('/api/membership/orders/'+str(r['case']['id']));assert response.status_code==200,response.text;return response.json()
def create(c,customer,purpose,values=None,status=201,key=None):
    response=c.post('/api/membership/orders',json={'request_id':key or uuid.uuid4().hex,'customer_id':customer['id'],
        'purpose':purpose,'values':values or {},'reason':'客户已明确本次会员办理事项'})
    assert response.status_code==status,response.text;return response.json()
def proof(c,r):return evidence(c,{'id':r['case']['id']},'evidence')
def cmd(c,r,action,values=None,status=200,body=None):
    current=detail(c,r)
    if body is None:body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'member_version':current['member']['version'],'values':values or {'evidence_id':proof(c,r),'reason':'本人实际核对并确认办理'}}
    response=c.post(f"/api/membership/orders/{r['case']['id']}/actions/{action}",json=body)
    assert response.status_code==status,response.text;return response.json()
def info(c,customer):
    response=c.get('/api/membership/members',params={'customer_id':customer['id']});assert response.status_code==200,response.text;return response.json()
def renew(c,customer,r):
    login(c,'service');order=create(c,customer,'renew',{'rule_id':r['id']})
    login(c,'manager');cmd(c,order,'approve');login(c,'finance');return cmd(c,order,'execute')

def assert_report(c,**expected):
    import csv,io
    response=c.get('/api/flow/analytics');assert response.status_code==200,response.text
    report=response.json()
    for key,total in expected.items():
        table=report['tables'][key];column='amount_cents' if key=='membership_fees' else 'units'
        assert sum(r[column] for r in table['rows'])==total
        chart=next(x for x in report['charts'] if x['id']==key)
        assert sum(chart['series'][0]['values'])==total
        response=c.get('/api/flow/analytics/export',params={'dataset':key});assert response.status_code==200,response.text
        csv_rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert csv_rows[0]==table['headers']
        assert [[cell.removeprefix("'") for cell in row] for row in csv_rows[1:]]==[[str(cell) for cell in row['values']] for row in table['rows']]
    return report

def assert_points_statement_original_guard(c):
    import json
    from tests import test_reconciliation as recon
    from tests.conftest import TEST_DIR
    from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
    statement=recon.batch(c);assert statement['definition_version']==CURRENT_DEFINITION_VERSION
    assert any(r['source']=='membership_points_debts' for r in statement['manifest'])
    for field in ('debt_id','units'):
        with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
            source.backup(copy);validate_reconciliation_sqlite(copy)
            raw=copy.execute('SELECT manifest,summary FROM reconciliation_batches WHERE id=?',(statement['id'],)).fetchone()
            manifest,summary=map(json.loads,raw)
            entry=next(r for r in manifest if r['source']=='membership_points_debts')['data']
            if field=='debt_id':entry['debt_id']+=999
            else:
                entry['units']+=1;entry['values'][2]+=1;entry['values'][3]+=1
            hashed=recon.svc.digest({'manifest':manifest,'summary':summary})
            copy.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',
                (json.dumps(manifest,ensure_ascii=False),hashed,statement['id']))
            with pytest.raises(ValueError,match='积分'):validate_reconciliation_sqlite(copy)


def test_independent_topup_has_dedicated_source_no_repair_and_cash_once(client):
    customer,m=setup(client);account=master(client,'accounts',{'name':'会员独立账户','account_type':'bank','active':True})
    order=create(client,customer,'topup',{'amount_cents':12345});login(client,'finance')
    current=detail(client,order);body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],
        'case_version':current['case']['version'],'member_version':current['member']['version'],
        'values':{'evidence_id':proof(client,order),'account_id':account['id'],'reference':uuid.uuid4().hex,'reason':'本店实际收到客户充值'}}
    result=cmd(client,order,'execute',body=body);assert result['case']['state']=='completed'
    cmd(client,order,'execute',body=body)
    assert g.wallet(client,m)['balance_cents']==12345
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Case))==1
        assert db.scalar(select(func.count()).select_from(CashEntry))==1
        assert db.scalar(select(Case.kind))=='membership'
    g.cmd(client,m,'topup',{'case_id':order['case']['id'],'case_version':result['case']['version'],
        'amount_cents':1,'evidence_id':body['values']['evidence_id'],'account_id':account['id'],'reference':'forged-topup'},409)


def test_card_issue_loss_replace_and_identifier_never_expands_store_authority(client):
    customer,m=setup(client);order=create(client,customer,'card_issue');cmd(client,order,'execute')
    card=info(client,customer)['cards'][0]
    assert client.get('/api/membership/cards/lookup',params={'number':card['number']}).status_code==200
    lost=create(client,customer,'card_loss',{'card_id':card['id']});cmd(client,lost,'execute')
    assert client.get('/api/membership/cards/lookup',params={'number':card['number']}).status_code==404
    replacement=create(client,customer,'card_replace',{'card_id':card['id']});cmd(client,replacement,'execute')
    cards=info(client,customer)['cards'];assert [x['status'] for x in cards]==['active','replaced']
    assert cards[0]['generation']==2 and cards[0]['number']!=card['number']
    another=g.seed(2);g.switch(client,2)
    assert client.get('/api/membership/cards/lookup',params={'number':cards[0]['number']}).status_code==404
    assert client.get('/api/membership/orders/'+str(order['case']['id'])).status_code==404
    g.switch(client,1);assert g.wallet(client,m)['active'] is True


def test_rules_off_independent_approval_periods_fee_and_unused_original_refund(client):
    customer,m=setup(client);disabled=rule(client,enabled=False)
    create(client,customer,'renew',{'rule_id':disabled['id']},409)
    free=rule(client);first=renew(client,customer,free)
    assert info(client,customer)['active_period_id'] is not None
    login(client,'admin');paid_rule=rule(client,fee_cents=19900);account=master(client,'accounts',{'name':'续会真实账户','account_type':'bank','active':True})
    login(client,'service');order=create(client,customer,'renew',{'rule_id':paid_rule['id']})
    cmd(client,order,'approve',status=403)
    login(client,'manager');cmd(client,order,'approve');login(client,'finance')
    cmd(client,order,'execute',status=422)
    cmd(client,order,'execute',{'evidence_id':proof(client,order),'account_id':account['id'],'reference':'RENEW-ACTUAL','reason':'客户缴付未来续会费用'})
    ps=info(client,customer)['periods'];assert len(ps)==2 and ps[1]['starts_on']>str(today())
    refund=create(client,customer,'renew_refund',{'period_id':ps[1]['id']});login(client,'manager');cmd(client,refund,'approve');login(client,'finance')
    cmd(client,refund,'execute',{'evidence_id':proof(client,refund),'account_id':account['id'],'reference':'RENEW-REFUND','reason':'按原规则退还未生效续会'})
    assert len(info(client,customer)['periods'])==1
    with SessionLocal() as db:
        assert sum(x.amount_cents for x in db.scalars(select(MembershipFee)))==0
        cash=list(db.scalars(select(CashEntry)));assert len(cash)==2 and sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in cash)==0


def test_no_self_approval_stale_duplicate_wrong_file_and_same_card_competition(client):
    customer,m=setup(client);r=rule(client);order=create(client,customer,'renew',{'rule_id':r['id']});cmd(client,order,'approve',status=403)
    login(client,'manager');fid=proof(client,order);current=detail(client,order)
    body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'member_version':current['member']['version'],'values':{'evidence_id':fid,'reason':'本人独立复核'}}
    cmd(client,order,'approve',body=body);cmd(client,order,'approve',body=body)
    cmd(client,order,'approve',body={**body,'request_id':uuid.uuid4().hex},status=409)
    login(client,'admin');a=create(client,customer,'card_issue');foreign=create(client,customer,'card_issue')
    cmd(client,a,'execute',{'evidence_id':proof(client,foreign),'reason':'不能串单使用凭据'},422)
    fid=proof(client,a);current=detail(client,a)
    body={'request_id':uuid.uuid4().hex,'version':current['order']['version'],'case_version':current['case']['version'],
        'member_version':current['member']['version'],'values':{'evidence_id':fid,'reason':'本人确认客户领卡'}}
    peers=[TestClient(app),TestClient(app)]
    for c in peers:login(c)
    def compete(c):return c.post(f"/api/membership/orders/{a['case']['id']}/actions/execute",json={**body,'request_id':uuid.uuid4().hex}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(compete,peers))==[200,409]
    finally:
        for c in peers:c.close()
    cmd(client,foreign,'execute',status=409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MembershipCard))==1


def test_tier_change_freezes_approved_rule_and_cancel_reject_preserve_history(client):
    customer,member=setup(client);base=rule(client);renew(client,customer,base)
    before=info(client,customer)['periods'][0]
    login(client,'admin');next_level=rule(client,name='明确配置的新级别')
    login(client,'service');change=create(client,customer,'tier_change',{'rule_id':next_level['id']})
    cmd(client,change,'execute',status=403)
    login(client,'manager');cmd(client,change,'approve')
    login(client,'admin');rule(client,code=next_level['code'],name='停用后续申请版本',enabled=False)
    login(client,'service');cmd(client,change,'execute')
    current=info(client,customer);assert len(current['periods'])==2
    active=next(p for p in current['periods'] if p['id']==current['active_period_id'])
    assert active['rule']['id']==next_level['id'] and active['ends_on']==before['ends_on']
    create(client,customer,'tier_change',{'rule_id':next_level['id']},409)
    cancel=create(client,customer,'card_issue');cancelled=cmd(client,cancel,'cancel',{'reason':'客户本次暂不领卡'})
    assert cancelled['case']['state']=='cancelled';cmd(client,cancel,'execute',status=409)
    rejected=create(client,customer,'renew',{'rule_id':base['id']});login(client,'manager')
    cmd(client,rejected,'reject',{'reason':'申请内容与客户本次意愿不符'})
    assert len(info(client,customer)['periods'])==2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(func.count()).select_from(MembershipCard))==0
        assert db.scalar(select(func.count()).select_from(Task).where(Task.case_id.in_([cancel['case']['id'],rejected['case']['id']]),Task.status=='open'))==0


def test_completed_retail_points_freeze_rounding_refund_debt_and_future_grant(client):
    from tests import test_retail as retail
    items,customer,_,_=retail.setup(client);m=g.issue(client,{'customer_id':customer['id']})
    point_rule=b.rule(client,'points',allowed_store_ids=[1]);level=rule(client,points_enabled=True,points_benefit_rule_id=point_rule['id'],points_denominator_fen=100)
    renew(client,customer,level);login(client,'admin')
    order=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    account=retail.bank(client);order=retail.pay(client,order,101,account);order=retail.pay(client,order,899,account)
    assert not b.info(client,{'customer_id':customer['id']})['wallets']
    order=retail.dispatch(client,order);order=retail.cmd(client,order,'accept',{'evidence_id':evidence(client,order)})
    wallet=b.info(client,{'customer_id':customer['id']})['wallets'][0];assert wallet['balance_units']==10
    spare_order=create(client,customer,'benefit_issue',{'action':'grant','rule_id':point_rule['id'],'units':1});login(client,'manager')
    spare=cmd(client,spare_order,'execute')['result']['wallet'];login(client,'admin')
    updated=rule(client,code=level['code'],points_enabled=True,points_benefit_rule_id=point_rule['id'],points_numerator=9,points_denominator_fen=100)
    coupon=b.rule(client,'coupon',allowed_store_ids=[1],sale_cents_per_unit=0,settlement_cents_per_unit=0,exchange_points_per_unit=1)
    exchange=create(client,customer,'points_adjust',{'action':'exchange','wallet_id':wallet['id'],'target_rule_id':coupon['id'],'units':10})
    login(client,'finance');cmd(client,exchange,'execute',{'evidence_id':proof(client,exchange),'wallet_version':wallet['version'],'reason':'客户明确兑换原消费积分'})
    login(client,'admin');order,ret=retail.request_return(client,order,order['dispatches'][0],500);order=retail.ret_cmd(client,order,ret,'return_approve');order=retail.ret_cmd(client,order,ret,'return_receive')
    assert info(client,customer)['points_debt_units']==3
    # Actual monetary refund is never blocked by points already exchanged.
    order=retail.refund(client,order,order['payments'][1],account,order['totals']['refund_due_cents'])
    assert order['totals']['refund_due_cents']==0 and info(client,customer)['points_debt_units']==3
    report=assert_report(client,membership_points=7,membership_points_debts=3)
    assert report['metrics']['membership_points_debt_units']==3
    assert_points_statement_original_guard(client)
    blocked=create(client,customer,'points_adjust',{'action':'exchange','wallet_id':spare['id'],'target_rule_id':coupon['id'],'units':1})
    login(client,'finance');cmd(client,blocked,'execute',{'evidence_id':proof(client,blocked),'wallet_version':spare['version'],'reason':'原欠额未清不能新增兑换'},409)
    settle=create(client,customer,'points_adjust',{'action':'settle_debt','wallet_id':spare['id'],'units':1})
    cmd(client,settle,'execute',{'evidence_id':proof(client,settle),'wallet_version':spare['version'],'reason':'客户明确用现有积分抵原消费欠额'})
    assert info(client,customer)['points_debt_units']==2
    grant=create(client,customer,'benefit_issue',{'action':'grant','rule_id':point_rule['id'],'units':5});login(client,'manager')
    result=cmd(client,grant,'execute');assert result['result']['wallet']['balance_units']==3
    assert info(client,customer)['points_debt_units']==0
    report=assert_report(client,membership_points=7,membership_points_debts=0)
    assert report['metrics']['membership_points_change_units']==7
    with SessionLocal() as db:
        from app.tenancy import set_scope
        from app.group_service import authority
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with authority(db,user):
            assert db.scalar(select(PointsClaim.target_units).where(PointsClaim.case_id==order['id']))==7
            assert db.scalar(select(func.sum(PointsChange.units)).where(PointsChange.case_id==order['id']))==7


def test_membership_fee_report_is_cash_once_and_scope_safe_with_exact_csv(client):
    customer,m=setup(client);r=rule(client,fee_cents=19900)
    account=master(client,'accounts',{'name':'汇总实际收费账户','account_type':'bank','active':True})
    login(client,'service');order=create(client,customer,'renew',{'rule_id':r['id']})
    login(client,'manager');cmd(client,order,'approve');login(client,'finance')
    cmd(client,order,'execute',{'evidence_id':proof(client,order),'account_id':account['id'],'reference':'REPORT-RENEW','reason':'本店实际确认收取会员费用'})
    local=assert_report(client,membership_fees=19900)
    assert local['metrics']['cash_in_cents']==local['metrics']['membership_fee_net_cents']==19900
    assert local['tables']['membership_fees']['rows'][0]['route']['id']==order['case']['id']
    login(client,'admin');g.seed(2);g.switch(client,2)
    assert_report(client,membership_fees=0,membership_points=0,membership_points_debts=0)
    assert client.get('/api/membership/orders/'+str(order['case']['id'])).status_code==404
    g.switch(client,'all');combined=assert_report(client,membership_fees=19900)
    assert combined['metrics']['cash_in_cents']==19900
    create(client,customer,'card_issue',status=409)
    g.switch(client,1);login(client,'sales')
    assert client.get('/api/flow/analytics').status_code==403
    assert client.get('/api/flow/analytics/export',params={'dataset':'membership_fees'}).status_code==403


def test_unconfigured_or_late_enrolled_source_never_receives_retroactive_points(client):
    from tests import test_retail as retail
    items,customer,_,_=retail.setup(client)
    order=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    m=g.issue(client,{'customer_id':customer['id']});point=b.rule(client,'points',allowed_store_ids=[1]);level=rule(client,points_enabled=True,points_benefit_rule_id=point['id'])
    renew(client,customer,level);login(client,'admin');order=retail.pay(client,order,1000,retail.bank(client));order=retail.dispatch(client,order)
    retail.cmd(client,order,'accept',{'evidence_id':evidence(client,order)})
    assert b.info(client,{'customer_id':customer['id']})['wallets']==[]


def test_original_unspent_points_are_recovered_without_touching_other_awards(client):
    from tests import test_retail as retail
    from app.membership_models import PointsRecovery
    from app.membership_backup_integrity import validate_membership_sqlite
    from tests.conftest import TEST_DIR
    items,customer,_,_=retail.setup(client);g.issue(client,{'customer_id':customer['id']})
    points=b.rule(client,'points',allowed_store_ids=[1]);level=rule(client,points_enabled=True,points_benefit_rule_id=points['id'])
    renew(client,customer,level);login(client,'admin')
    sale=retail.authorize(client,retail.approve(client,retail.create(client,items,customer)))
    sale=retail.pay(client,sale,1000,retail.bank(client));sale=retail.dispatch(client,sale)
    sale=retail.cmd(client,sale,'accept',{'evidence_id':evidence(client,sale)})
    original=b.info(client,{'customer_id':customer['id']})['wallets'][0]
    other=create(client,customer,'benefit_issue',{'action':'grant','rule_id':points['id'],'units':9})
    login(client,'manager');spare=cmd(client,other,'execute')['result']['wallet'];login(client,'admin')
    sale,returned=retail.request_return(client,sale,sale['dispatches'][0],500)
    retail.ret_cmd(client,sale,returned,'return_approve');retail.ret_cmd(client,sale,returned,'return_receive')
    wallets={w['id']:w for w in b.info(client,{'customer_id':customer['id']})['wallets']}
    assert wallets[original['id']]['balance_units']==7 and wallets[spare['id']]['balance_units']==9
    assert info(client,customer)['points_debt_units']==0
    with SessionLocal() as db:
        from app.tenancy import set_scope
        from app.group_service import authority
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
        with authority(db,user):assert db.scalar(select(func.sum(PointsRecovery.units)))==3
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source:validate_membership_sqlite(source)


def test_cross_store_card_replacement_does_not_reassign_original_business_or_wallet(client):
    customer,m=setup(client);a=create(client,customer,'card_issue');cmd(client,a,'execute');original=info(client,customer)['cards'][0]
    other=g.seed(2,name=customer['name'],phone=customer['phone']);g.switch(client,2);g.link(client,other,m['identity_id'])
    card=create(client,{'id':other['customer_id']},'card_replace',{'card_id':original['id']});cmd(client,card,'execute')
    data=info(client,{'id':other['customer_id']});assert [c['status'] for c in data['cards']]==['active','replaced']
    assert client.get('/api/membership/orders/'+str(a['case']['id'])).status_code==404
    assert client.get('/api/membership/cards/lookup',params={'number':original['number']}).status_code==404
    with SessionLocal() as db:
        assert db.scalar(select(Case.store_id).where(Case.id==a['case']['id']))==1
        assert db.scalar(select(Case.store_id).where(Case.id==card['case']['id']))==2
        assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_auditor_sales_and_cross_store_fee_file_guards(client):
    customer,m=setup(client);order=create(client,customer,'card_issue');login(client,'sales')
    assert client.get('/api/membership/orders/'+str(order['case']['id'])).status_code==404
    create(client,customer,'card_issue',status=403)
    login(client,'auditor');create(client,customer,'card_issue',status=403)
    cmd(client,order,'execute',values={'evidence_id':1,'reason':'审计不能办理'},status=403)
    assert info(client,customer)['cards']==[]
    login(client,'admin');other=g.seed(2);cmd(client,order,'execute',{'evidence_id':other['evidence_id'],'reason':'外店凭据不能用作本店发行'},422)


def test_repair_completed_customer_only_points_excludes_insurer_and_internal(client):
    from tests import test_repair_orders as repair
    row,item,work,customer=repair.setup(client)
    m=g.issue(client,{'customer_id':customer['id']});point=b.rule(client,'points',allowed_store_ids=[1])
    level=rule(client,points_enabled=True,points_benefit_rule_id=point['id']);renew(client,customer,level);login(client,'admin')
    row=repair.ready(client,row,item,work)
    insurer=repair.typed(client,'insurers',{'code':'POINT-INSURER','name':'消费积分测试保险'})
    row=repair.allocate(client,row,[{'payer_type':'customer','amount_cents':5000},
        {'payer_type':'insurer','amount_cents':4000,'payer_id':insurer['id']},
        {'payer_type':'internal','amount_cents':1997,'payer_name':'门店承担'}])
    account=repair.bank(client)
    customer_allocation=next(a for a in row['allocations'] if a['payer_type']=='customer')
    row=repair.cmd(client,row,'receive',{'allocation_id':customer_allocation['id'],'amount_cents':5000,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(client,row,'receipt')})
    assert b.info(client,{'customer_id':customer['id']})['wallets']==[]
    row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    wallets=b.info(client,{'customer_id':customer['id']})['wallets'];assert sum(w['balance_units'] for w in wallets)==50
    insurance=next(a for a in row['allocations'] if a['payer_type']=='insurer')
    repair.cmd(client,row,'receive',{'allocation_id':insurance['id'],'amount_cents':4000,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(client,row,'receipt')})
    assert sum(w['balance_units'] for w in b.info(client,{'customer_id':customer['id']})['wallets'])==50


def test_nonempty_restore_validates_points_original_debt_and_immutable_lifecycle(client,tmp_path):
    test_completed_retail_points_freeze_rounding_refund_debt_and_future_grant(client)
    login(client,'admin');customer=client.get('/api/flow/master/customers').json()['items'][0]
    card=create(client,customer,'card_issue');cmd(client,card,'execute')
    from tests.conftest import TEST_DIR
    from app.membership_backup_integrity import validate_membership_sqlite
    from app.backup_integrity import validate_sqlite
    destination=tmp_path/'member-copy.sqlite'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(destination) as backup:source.backup(backup)
    with sqlite3.connect(destination) as db:
        validate_sqlite(db)
        result=validate_membership_sqlite(db);assert result['verified_membership_orders']>=4 and result['verified_points_claims']==1
    for sql in ["UPDATE membership_points_claims SET target_units=target_units+1", "UPDATE membership_points_claims SET basis_cents=basis_cents+1", "UPDATE membership_points_debts SET units=units+1",
        "UPDATE membership_points_debt_payments SET units=units+1", "UPDATE membership_cards SET generation=generation+1"]:
        with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as backup:
            source.backup(backup);backup.execute(sql)
            with pytest.raises(ValueError):validate_membership_sqlite(backup)
