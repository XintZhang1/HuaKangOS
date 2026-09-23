"""Explicit grade prices affect original quotes without rewriting prior consent."""
import json,sqlite3,uuid
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import CashEntry
from app.flow_models import Case
from app.member_pricing_models import *
from tests.conftest import login,TEST_DIR
from tests.test_workflow import evidence
from tests import test_membership_lifecycle as membership,test_group_membership as group,test_repair_orders as repair,test_retail as retail,test_addon_orders as addon

API='/api/member-pricing'

@pytest.fixture(autouse=True)
def restored_prices():
    yield
    from app.member_pricing_integrity import validate
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:validate(connection)

def member(c,customer):
    group.issue(c,{'customer_id':customer['id']});r=membership.rule(c);membership.renew(c,customer,r);login(c,'admin');return r

def body(mrule,scopes,**kw):
    result=dict(request_id=uuid.uuid4().hex,code='PRICE-'+uuid.uuid4().hex[:8],name='本店明确会员工时商品价格',enabled=True,membership_rule_id=mrule['id'],starts_on=today().isoformat(),ends_on=(today()+timedelta(days=30)).isoformat(),stack_mode='member_then_benefits',reason='按公司明确等级、项目、价格与叠用约定',scopes=scopes);result.update(kw);return result
def scope(kind,component,source,rate=9000,**kw):return dict(business_kind=kind,component=component,source_id=source['id'],basis_points=rate,**kw)
def rule(c,mrule,scopes,approve=True,**kw):
    login(c,'admin');r=c.post(API+'/rules',json=body(mrule,scopes,**kw));assert r.status_code==201,r.text;row=r.json()
    if approve:
        row=cmd(c,row,'submit');login(c,'manager');row=cmd(c,row,'approve');login(c,'admin')
    return row

def detail(c,row):
    r=c.get(API+'/rules/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def cmd(c,row,key,status=200,values=None):
    v=values or dict(reason='本人核对本次真实规则依据')
    if key!='cancel' and 'evidence_id' not in v:v['evidence_id']=evidence(c,{'id':row['case_id']})
    r=c.post(API+f"/rules/{row['id']}/actions/{key}",json=dict(request_id=uuid.uuid4().hex,version=detail(c,row)['case_version'],values=v));assert r.status_code==status,r.text;return r.json()
def selection(r):return dict(rule_id=r['id'],rule_version=r['rule_version'])
def quote(c,row,item,work,r,**kw):
    values=dict(reason='明确本次会员价格与人工授权分开',member_pricing=selection(r),discount_cents=3,lines=[dict(kind='work',source_id=work['id'],quantity_milli=1000,unit_price_cents=10000),dict(kind='part',source_id=item['id'],quantity_milli=1000,unit_price_cents=500)]);values.update(kw);return repair.cmd(c,row,'quote',values)

def test_rule_requires_another_manager_and_retail_uses_approved_member_net(client):
    items,customer,work,_=retail.setup(client,True);mrule=member(client,customer)
    r=rule(client,mrule,[scope('retail','goods',items[0]),scope('retail','installation',work,8000)],approve=False)
    assert client.get(API+'/candidates',params={'customer_id':customer['id']}).json()['items']==[]
    r=cmd(client,r,'submit');cmd(client,r,'approve',403)
    login(client,'manager');r=cmd(client,r,'approve');login(client,'admin')
    response=client.post('/api/retail/orders',json=dict(request_id=uuid.uuid4().hex,customer_id=customer['id'],member_pricing=selection(r),discount_cents=3,lines=[dict(item_id=items[0]['id'],quantity_milli=1000,unit_price_cents=1000,work_item_id=work['id'],installation_unit_price_cents=100)]))
    assert response.status_code==201,response.text;row=response.json()
    assert row['amount_cents']==977 and row['member_pricing']['member_discount_cents']==120
    row=retail.authorize(client,retail.approve(client,row))
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MemberPricingAuthorization))==1 and not db.scalar(select(CashEntry.id))

def test_repair_quote_member_and_manual_discounts_preserve_source_amount(client):
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);r=rule(client,mrule,[scope('repair','work',work,8000),scope('repair','part',item,9000)])
    row=quote(client,row,item,work,r);q=row['quotes'][-1]
    assert q['amount_cents']==8447 and q['member_pricing']['member_discount_cents']==2050 and q['discount_cents']==2053
    row=repair.authorize(client,row)
    with SessionLocal() as db:
        s=db.scalar(select(MemberPricingSnapshot));assert s.quote_id==q['id'] and s.contract['identity']['membership_rule_id']==mrule['id']
        assert sum(l.net_cents for l in db.scalars(select(MemberPricingLine)))==8447

def test_member_rule_disabled_before_authorization_refuses_without_reprice(client):
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);r=rule(client,mrule,[scope('repair','work',work,8000)])
    row=quote(client,row,item,work,r);q=row['quotes'][-1]
    values={k:mrule[k] for k in ('code','name','allowed_store_ids','validity_months','fee_cents','fee_owner','refund_policy','points_enabled','points_numerator','points_denominator_fen','points_benefit_rule_id')};membership.rule(client,**values,enabled=False)
    row=repair.cmd(client,row,'price_approve',dict(quote_id=q['id'],minimum_total_cents=0,reason='仅批准现报价，不补认已停用会员',allow_below_minimum=False))
    repair.cmd(client,row,'authorize',dict(quote_id=q['id'],evidence_id=evidence(client,row)),409)
    assert repair.detail(client,row)['quotes'][-1]['amount_cents']==8497
    with SessionLocal() as db:assert not db.scalar(select(MemberPricingAuthorization.id))

def test_addon_paid_components_member_priced_once_and_zero_rounding_refused(client):
    row,items,work,source,vin=addon.setup(client)
    with SessionLocal() as db:customer={'id':db.get(Case,row['id']).customer_id}
    mrule=member(client,customer);r=rule(client,mrule,[scope('addon','goods',items[0],9000),scope('addon','installation',work,8000)])
    row=addon.cmd(client,row,'quote',dict(reason='明确会员加装商品及施工价格',member_pricing=selection(r),discount_cents=0,lines=[dict(line_key='member1',item_id=items[0]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=1000,installation_unit_cents=100)]))
    assert row['totals']['charge_cents']==980 and row['quote']['member_pricing']['member_discount_cents']==120
    row=addon.authorized(client,addon.approved(client,row))
    low=rule(client,mrule,[scope('addon','goods',items[0],1)])
    addon.cmd(client,row,'quote',dict(reason='不能利用折扣绕过赠送',member_pricing=selection(low),discount_cents=0,lines=[dict(line_key='member1',item_id=items[0]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=1000,installation_unit_cents=100),dict(line_key='zero',item_id=items[0]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=1,installation_unit_cents=0)]),409)

technician=repair.technician

def test_increment_carries_old_grade_price_and_counts_only_current_authorized_quote(client):
    from tests.test_multistore import second_store
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);r=rule(client,mrule,[scope('repair','work',work,8000),scope('repair','part',item,9000)])
    row=repair.authorize(client,quote(client,row,item,work,r));row=repair.cmd(client,row,'start',{'result':'按原授权开始本次维修'})
    old=repair.current_quote(client,row);newrule=rule(client,mrule,[scope('repair','work',work,7000),scope('repair','part',item,8000)],code=r['code'])
    lines=[dict(line_key=l['line_key'],kind=l['kind'],source_id=l['work_item_id'] or l['item_id'],quantity_milli=l['quantity_milli']+(1000 if l['kind']=='part' else 0),unit_price_cents=l['unit_price_cents']) for l in old['lines']]
    row=repair.cmd(client,row,'quote',dict(reason='只对新增一件按新价格授权',member_pricing=selection(newrule),discount_cents=0,lines=lines))
    assert row['quotes'][-1]['amount_cents']==8847
    before=client.get('/api/flow/analytics').json();assert before['metrics']['current_authorized_member_discount_cents']==2050
    row=repair.authorize(client,row);report=client.get('/api/flow/analytics').json();assert report['metrics']['current_authorized_member_discount_cents']==2150
    rows=report['tables']['member_pricing_current_quotes']['rows'];assert len(rows)==1 and rows[0]['quote_id']==row['data']['authorized_quote_id']
    second_store(client);client.headers['X-Store-ID']='all';grouped=client.get('/api/flow/analytics').json()['tables']['member_pricing_current_quotes']['rows'];assert len(grouped)==1
    assert set(grouped[0])=={'values','amount_cents','quote_count'} and grouped[0]['amount_cents']==2150
    client.headers['X-Store-ID']='1'


def test_local_price_disable_before_consent_then_historical_price_does_not_change(client):
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);r=rule(client,mrule,[scope('repair','work',work,8000)])
    row=quote(client,row,item,work,r);pending=rule(client,mrule,[],enabled=False,code=r['code'])
    q=row['quotes'][-1];row=repair.cmd(client,row,'price_approve',dict(quote_id=q['id'],minimum_total_cents=0,reason='核对原报价价格',allow_below_minimum=False))
    repair.cmd(client,row,'authorize',dict(quote_id=q['id'],evidence_id=evidence(client,row)),409)
    repair.cmd(client,row,'quote_cancel',dict(quote_id=q['id'],reason='规则停用后撤销未授权版'))
    enabled=rule(client,mrule,[scope('repair','work',work,7000)],code=r['code']);row=repair.authorize(client,quote(client,row,item,work,enabled))
    rule(client,mrule,[],enabled=False,code=r['code']);assert repair.detail(client,row)['amount_cents']==7497
    assert client.get(API+'/candidates',params={'case_id':row['id']}).json()['items']==[]


def test_price_reference_freeze_exact_replay_stale_and_foreign_scope(client):
    from tests.test_multistore import second_store
    row,item,work,customer=repair.setup(client);mrule=member(client,customer)
    tier=repair.typed(client,'member_tiers',dict(code='PRICE-TIER',name='原本店参考九折',discount_basis_points=9000))
    values=body(mrule,[scope('repair','work',work,8500)],reference_tier_id=tier['id'],reference_tier_version=tier['version'])
    response=client.post(API+'/rules',json=values);assert response.status_code==201,response.text;r=response.json()
    assert client.post(API+'/rules',json=values).json()['id']==r['id']
    assert client.post(API+'/rules',json={**values,'name':'变造同一请求'}).status_code==409
    assert r['reference_tier_snapshot']['discount_basis_points']==9000 and r['scopes'][0]['basis_points']==8500
    v=r['case_version'];r=cmd(client,r,'submit');login(client,'manager')
    stale=client.post(API+f"/rules/{r['id']}/actions/approve",json=dict(request_id=uuid.uuid4().hex,version=v,values=dict(reason='陈旧版本不能批准',evidence_id=evidence(client,{'id':r['case_id']}))))
    assert stale.status_code==409;cmd(client,r,'approve');login(client,'sales');assert client.get(API+'/rules').status_code==403
    login(client,'admin');second_store(client);client.headers['X-Store-ID']='2'
    assert client.get(API+f"/rules/{r['id']}").status_code==404
    response=client.post(API+'/rules',json=body(mrule,[scope('repair','work',work)]));assert response.status_code in {403,404}
    client.headers['X-Store-ID']='1'


def test_independent_managers_compete_for_exact_rule_version(client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);r=cmd(client,rule(client,mrule,[scope('repair','work',work)],approve=False),'submit')
    login(client,'manager');fid=evidence(client,{'id':r['case_id']});values=dict(version=r['case_version'],values=dict(reason='独立主管本次批准',evidence_id=fid))
    clients=[TestClient(app),TestClient(app)]
    try:
        for c in clients:login(c,'manager')
        def run(c):return c.post(API+f"/rules/{r['id']}/actions/approve",json=dict(request_id=uuid.uuid4().hex,**values)).status_code
        with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(run,clients))==[200,409]
    finally:
        for c in clients:c.close()
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MemberPricingDecision).where(MemberPricingDecision.decision=='approved'))==1


def test_authorized_rework_only_customer_extra_gets_member_and_manual_discount(client):
    from tests import test_rework_extensions as rw
    d=rw.fixture(client);row=rw.converted(client,d);login(client,'admin');customer={'id':row['customer_id']}
    # The source vehicle has already established its explicit shared identity.
    from app.group_models import GroupIdentityLink,GroupMember
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        identity=db.execute("SELECT identity_id FROM group_identity_links WHERE local_kind='customer' AND local_id=? AND store_id=1",(customer['id'],)).fetchone()[0];m=db.execute('SELECT id FROM group_members WHERE identity_id=?',(identity,)).fetchone()
    if not m:
        response=client.post('/api/group/members',json=dict(request_id=uuid.uuid4().hex,identity_id=identity));assert response.status_code==201,response.text
    mrule=membership.rule(client);membership.renew(client,customer,mrule);r=rule(client,mrule,[scope('repair','work',d['work'],8000)])
    rw.switch(client,'service')
    lines=[dict(kind='work',source_id=d['work']['id'],quantity_milli=1000,unit_price_cents=600,charge_scope='original_liability',source_line_id=d['source']['lines'][0]['id']),dict(kind='work',source_id=d['work']['id'],quantity_milli=1000,unit_price_cents=300,charge_scope='customer_extra')]
    row=rw.call(client,f"/orders/{row['id']}/quote",dict(version=repair.detail(client,row)['version'],values=dict(reason='返修原责任与本次会员自费分开',discount_cents=3,member_pricing=selection(r),lines=lines)),200)
    q=row['quotes'][-1];assert q['rework_scope']==dict(original_liability_cents=600,customer_extra_cents=237)
    parts=q['member_pricing']['lines'];original=next(p for p in parts if p['charge_scope']=='original_liability');assert original['scope_id'] is None and original['member_discount_cents']==original['manual_discount_cents']==0
    rw.authorized(client,d,row)


def test_paid_package_contract_never_repriced_by_member_or_manual_distribution(client):
    from app import member_pricing_service as svc
    from tests.test_retail_group_service import actor
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);r=rule(client,mrule,[scope('repair','work',work,8000)])
    with SessionLocal() as db:
        user=actor(db);stored=db.scalar(select(Case).where(Case.id==row['id']))
        components=[dict(line_key='paid',component='work',source_id=work['id'],basis_cents=1000,price_source='package_contract',contract_rule_id=71,contract_component_id=91),dict(line_key='new',component='work',source_id=work['id'],basis_cents=300)]
        prepared=svc.prepare_quote(db,user,stored,selection(r),components,3)
        assert prepared['lines'][0]['net_cents']==1000 and prepared['lines'][0]['member_discount_cents']==prepared['lines'][0]['manual_discount_cents']==0
        assert prepared['lines'][0]['contract_component_id']==91 and prepared['lines'][1]['net_cents']==237
        db.rollback()


def test_bundle_explicit_member_scope_preserves_contract_basis_and_original_partial_return(client):
    from tests import test_retail_bundles as bundle
    items,customer,work,_=retail.setup(client,True);mrule=member(client,customer);contract=bundle.publish(client,items,work)
    ordinary=rule(client,mrule,[scope('retail','goods',items[0],8000)])
    bundle.sale(client,contract,customer,2,status=409,member_pricing=selection(ordinary))
    explicit=rule(client,mrule,[scope('retail','goods',items[0],8000,bundle_rule_id=contract['id']),scope('retail','installation',work,9000,bundle_rule_id=contract['id'])])
    row=bundle.sale(client,contract,customer,2,member_pricing=selection(explicit));assert row['amount_cents']==1619
    account=retail.bank(client);row=retail.dispatch(client,retail.authorize(client,retail.approve(client,row)));row=retail.pay(client,row,1619,account)
    row=retail.cmd(client,row,'install',dict(result='按本次会员套装真实安装',evidence_id=evidence(client,row)));row=retail.cmd(client,row,'accept',dict(evidence_id=evidence(client,row)))
    for qty in (333,667,1000):
        row,ret=retail.request_return(client,row,row['dispatches'][0],qty);row=retail.ret_cmd(client,row,ret,'return_approve');row=retail.ret_cmd(client,row,ret,'return_receive');row=retail.refund(client,row,row['payments'][0],account,row['totals']['refund_due_cents'])
    assert sum(p['goods_cents'] for p in row['return_postings'])==1453 and row['totals']['charge_cents']==166
    bundle.validate()


def test_removal_of_all_price_tables_does_not_disguise_real_rule_as_legacy(client):
    from app.member_pricing_integrity import validate
    row,item,work,customer=repair.setup(client);mrule=member(client,customer);rule(client,mrule,[scope('repair','work',work)])
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy)
        for name in ('authorizations','lines','snapshots','decisions','scopes','rules'):copy.execute('DROP TABLE member_pricing_'+name)
        with pytest.raises(ValueError,match='会员价格'):validate(copy)
    with sqlite3.connect(':memory:') as empty:assert validate(empty)['verified_member_pricing_rules']==0

@pytest.mark.parametrize('mode',['member_then_benefits','exclusive_benefits'])
def test_native_retail_coupon_stack_is_explicit_and_principal_is_always_payment(client,mode):
    from tests import test_retail_group_api as rg
    original,identity,wallet,account,_=rg.public_setup(client,authorize=False)
    login(client,'admin');customer={'id':original['customer_id']};level=membership.rule(client);membership.renew(client,customer,level);login(client,'admin')
    item={'id':original['lines'][0]['item_id']};r=rule(client,level,[scope('retail','goods',item,9000)],stack_mode=mode)
    response=client.post('/api/retail/orders',json=dict(request_id=uuid.uuid4().hex,customer_id=customer['id'],member_pricing=selection(r),discount_cents=0,lines=[dict(item_id=item['id'],quantity_milli=500,unit_price_cents=1000)]));assert response.status_code==201,response.text;row=response.json()
    row=retail.dispatch(client,retail.authorize(client,retail.approve(client,row)));row=retail.cmd(client,row,'accept',dict(evidence_id=evidence(client,row)))
    def body(selections):
        catalog=client.get(f"/api/retail-group/orders/{row['id']}/catalog").json()
        return dict(request_id=uuid.uuid4().hex,version=catalog['version'],values=dict(member_id=identity['id'],member_version=catalog['member']['version'],evidence_id=evidence(client,row,'authorization'),selections=selections))
    current=next(w for w in client.get(f"/api/retail-group/orders/{row['id']}/catalog").json()['wallets'] if w['id']==wallet['id'])
    mixed=[dict(kind='coupon',wallet_id=current['id'],wallet_version=current['version'],units=1),dict(kind='principal',amount_cents=50)]
    result=client.post(f"/api/retail-group/orders/{row['id']}/actions/authorize",json=body(mixed));assert result.status_code==(200 if mode=='member_then_benefits' else 409),result.text
    if mode=='exclusive_benefits':
        result=client.post(f"/api/retail-group/orders/{row['id']}/actions/authorize",json=body([dict(kind='principal',amount_cents=450)]));assert result.status_code==200,result.text
    rg.capture_all(client,row);current=retail.detail(client,row);assert current['totals']['receivable_cents']==0 and current['amount_cents']==450
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        assert db.execute('SELECT count(*) FROM flow_payment_links WHERE case_id=?',(row['id'],)).fetchone()[0]==0


@pytest.mark.parametrize('mode',['member_then_benefits','exclusive_benefits'])
def test_native_repair_bonus_reservation_obeys_price_stack(client,mode):
    from tests import test_group_benefits as benefits
    row,item,work,customer=repair.setup(client);level=member(client,customer);r=rule(client,level,[scope('repair','work',work,9000)],stack_mode=mode)
    row=repair.authorize(client,quote(client,row,item,work,r));row=repair.cmd(client,row,'start',dict(result='按原会员价格施工'));row=repair.issue(client,row,1000);row=repair.cmd(client,row,'finish',dict(result='实际施工完成'));row=repair.cmd(client,row,'quality',dict(passed=True,result='质检通过',evidence_id=evidence(client,row)));row=repair.allocate(client,row)
    benefit=benefits.rule(client,'bonus',allowed_store_ids=[1]);issue=membership.create(client,customer,'benefit_issue',dict(rule_id=benefit['id'],units=100,action='grant'));login(client,'manager');membership.cmd(client,issue,'execute');login(client,'finance')
    data=membership.info(client,customer);identity=data['member'];wallet=benefits.info(client,{'customer_id':customer['id']})['wallets'][-1]
    values=dict(wallet_id=wallet['id'],wallet_version=wallet['version'],case_id=row['id'],case_version=repair.detail(client,row)['version'],evidence_id=evidence(client,row),units=100,reason='按已批准会员价与赠金叠用约定')
    result=benefits.command(client,identity,'reserve',values,status=200 if mode=='member_then_benefits' else 409)
    if mode=='member_then_benefits':
        reservation=result['reservation'];wallet=benefits.info(client,{'customer_id':customer['id']})['wallets'][-1]
        benefits.command(client,identity,'capture',dict(wallet_id=wallet['id'],wallet_version=wallet['version'],reservation_id=reservation['id'],reservation_version=reservation['version'],case_version=repair.detail(client,row)['version'],evidence_id=evidence(client,row),reason='本人确认原赠金核销'))
        assert repair.detail(client,row)['customer_due_cents']==9397


def test_restore_rehash_cannot_replace_original_quote_basis(client):
    from app.member_pricing_integrity import validate
    from app.member_pricing_service import canonical
    row,item,work,customer=repair.setup(client);level=member(client,customer);r=rule(client,level,[scope('repair','work',work,8000)])
    quote(client,row,item,work,r,discount_cents=0)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy);sid,raw=copy.execute('SELECT id,contract FROM member_pricing_snapshots').fetchone();contract=json.loads(raw);part=contract['lines'][0]
        part.update(basis_cents=20000,member_discount_cents=4000,net_cents=16000)
        copy.execute('UPDATE member_pricing_snapshots SET contract=?,digest=? WHERE id=?',(json.dumps(contract),canonical(contract),sid))
        copy.execute('UPDATE member_pricing_lines SET basis_cents=20000,member_discount_cents=4000,net_cents=16000 WHERE snapshot_id=? AND component=?',(sid,'work'))
        copy.execute('UPDATE repair_lines SET amount_cents=16000 WHERE kind=?',('work',))
        with pytest.raises(ValueError,match='原基价'):validate(copy)


def test_business_day_uses_company_timezone_across_utc_midnight(monkeypatch):
    from datetime import date,datetime,timezone
    from app.member_pricing_integrity import business_day
    from types import SimpleNamespace
    from app import member_pricing_integrity as integrity
    monkeypatch.setattr(integrity,'settings',SimpleNamespace(timezone='Asia/Shanghai'))
    assert business_day(datetime(2026,9,22,15,59,59))==date(2026,9,22)
    assert business_day(datetime(2026,9,22,16,0,0,tzinfo=timezone.utc))==date(2026,9,23)
    assert business_day('2026-09-23T00:00:00+08:00')==date(2026,9,23)

def test_shared_identity_requires_each_store_own_approved_price(client):
    from tests.test_multistore import second_store,assign
    row,item,work,customer=repair.setup(client);shared=group.issue(client,{'customer_id':customer['id']});second_store(client);assign('manager',[2])
    level=membership.rule(client,allowed_store_ids=[1,2]);membership.renew(client,customer,level);first=rule(client,level,[scope('repair','work',work,8000)])
    client.headers['X-Store-ID']='2';local=retail.master(client,'customers',dict(name=customer['name'],phone=customer['phone'],contact_allowed=True,note=''));group.link(client,{'customer_id':local['id']},shared['identity_id'])
    second_work=repair.typed(client,'work_items',dict(code='LOCAL-PRICE-WORK',name='二店真实作业',billing_unit='job',standard_fee_cents=10000));second=repair.create(client,local)
    repair.cmd(client,second,'quote',dict(reason='不能借用另一店价格权限',member_pricing=selection(first),lines=[dict(kind='work',source_id=second_work['id'],quantity_milli=1000,unit_price_cents=10000)]),404)
    own=rule(client,level,[scope('repair','work',second_work,7000)]);second=repair.cmd(client,second,'quote',dict(reason='二店独立七折规则适用共享会员身份',member_pricing=selection(own),lines=[dict(kind='work',source_id=second_work['id'],quantity_milli=1000,unit_price_cents=10000)]))
    second=repair.authorize(client,second);assert second['amount_cents']==7000
    assert client.get('/api/repair-orders/'+str(row['id'])).status_code==404;client.headers['X-Store-ID']='1'


def test_real_tier_change_invalidates_pending_price_but_balance_topup_does_not(client):
    row,item,work,customer=repair.setup(client);level=member(client,customer);r=rule(client,level,[scope('repair','work',work,8000)])
    row=quote(client,row,item,work,r);account=retail.bank(client);topup=membership.create(client,customer,'topup',dict(amount_cents=100))
    login(client,'finance');membership.cmd(client,topup,'execute',dict(evidence_id=membership.proof(client,topup),account_id=account,reference=uuid.uuid4().hex,reason='本金变动不改变原有效会期'));login(client,'admin')
    row=repair.authorize(client,row);assert row['amount_cents']==8497
    second=repair.create(client,customer);second=quote(client,second,item,work,r);higher=membership.rule(client)
    login(client,'service');change=membership.create(client,customer,'tier_change',dict(rule_id=higher['id']));login(client,'manager');membership.cmd(client,change,'approve');login(client,'service');membership.cmd(client,change,'execute');login(client,'admin')
    q=second['quotes'][-1];second=repair.cmd(client,second,'price_approve',dict(quote_id=q['id'],minimum_total_cents=0,allow_below_minimum=False,reason='复核本版报价'))
    repair.cmd(client,second,'authorize',dict(quote_id=q['id'],evidence_id=evidence(client,second)),409)
    assert repair.detail(client,row)['amount_cents']==8497 and client.get(API+'/candidates',params={'case_id':second['id']}).json()['items']==[]


def test_expired_price_refused_and_current_discount_chart_table_csv_match(client):
    import csv,io
    from decimal import Decimal
    row,item,work,customer=repair.setup(client);level=member(client,customer)
    expired=rule(client,level,[scope('repair','work',work,8000)],starts_on=(today()-timedelta(days=2)).isoformat(),ends_on=(today()-timedelta(days=1)).isoformat())
    repair.cmd(client,row,'quote',dict(reason='不能使用过期批准价',member_pricing=selection(expired),lines=[dict(kind='work',source_id=work['id'],quantity_milli=1000,unit_price_cents=10000)]),409)
    r=rule(client,level,[scope('repair','work',work,8000)]);repair.authorize(client,quote(client,row,item,work,r))
    report=client.get('/api/flow/analytics').json();key='member_pricing_current_quotes';table=report['tables'][key];chart=next(c for c in report['charts'] if c['id']==key)
    response=client.get('/api/flow/analytics/export',params={'dataset':key});assert response.status_code==200,response.text
    records=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))));assert records[0]==table['headers']
    assert sum(Decimal(r[-1].removeprefix("'"))*100 for r in records[1:])==sum(r['amount_cents'] for r in table['rows'])==sum(chart['series'][0]['values'])==2000
