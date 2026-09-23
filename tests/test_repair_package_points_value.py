"""Actual package P, signed tails, original returns and material/CSV conservation."""
import sqlite3,uuid
from datetime import timedelta
import pytest
from sqlalchemy import select,text
from app.db import SessionLocal,engine,today
from app.models import User,UserStore
from app.membership_backup_integrity import validate_membership_sqlite
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR,login
from tests.test_repair_packages import technician
from tests.test_workflow import evidence
from tests import test_repair_packages as package,test_repair_orders as repair,test_aftercare as aftercare
from tests import test_membership_lifecycle as membership,test_group_benefits as benefits,test_material_value_analytics as material


def enroll(c,d,denominator=100,stores=None):
    stores=stores or [1]
    login(c,'admin');points=benefits.rule(c,'points',allowed_store_ids=stores)
    rule=membership.rule(c,allowed_store_ids=stores,points_enabled=True,points_benefit_rule_id=points['id'],points_denominator_fen=denominator)
    membership.renew(c,d['customer'],rule)


def claim(row):
    # Raw read is intentional independent evidence, without central ORM access.
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        return db.execute('SELECT basis_cents,target_units FROM membership_points_claims WHERE case_id=?',(row['id'],)).fetchone()


def restore():
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);return validate_sqlite(copy)


def capture(c,row):
    login(c,'finance');package.post(c,'/orders/'+str(row['id'])+'/capture',{'version':repair.detail(c,row)['version'],'values':{'evidence_id':evidence(c,row)}})
    return repair.detail(c,row)


def release(c,row):
    login(c,'admin');return repair.cmd(c,row,'release',{'evidence_id':evidence(c,row)})


def return_component(c,row,quantity,face):
    login(c,'admin');request=aftercare.create(c,row)
    original=next(x for x in request['sources'][0]['eligible_returns'] if x['kind']=='repair_package')
    request=aftercare.plan(c,request,face,[{'kind':'repair_package','original_id':original['entry_id'],'units':quantity}])
    request=aftercare.confirmed(c,aftercare.approved(c,request));login(c,'inventory')
    target=c.get(package.API+'/aftercare/'+str(request['id'])+'/return-targets').json();h=target['items'][0]
    body={'version':target['version'],'source_version':h['source_version'],'hold_id':h['hold_id'],
          'original_stock_id':h['original_stocks'][0]['id'],'quantity_milli':quantity,'passed':True,
          'result':'实际收到原配件且检查可按原成本入库','evidence_id':evidence(c,request,'inspection')}
    package.post(c,'/aftercare/'+str(request['id'])+'/return-material',body)
    login(c,'admin');return aftercare.applied(c,request)


def test_actual_package_paid_consumption_then_original_partial_return_points_and_material_value(client):
    d=package.fixture(client);enroll(client,d);row=package.quoted(client,d,extra=True)
    assert claim(row) is None  # Before the first customer authorization.
    row=package.finished(client,d,row);row=capture(client,row)
    assert claim(row)==(0,0)  # Actual capture still lacks delivery.
    row=repair.receive(client,row,row['allocations'][0],200,d['account']);row=release(client,row)
    assert claim(row)==(1302,13)
    report=material.report(client,source='repair');source=report['tables']['material_sources']['rows'][0]
    assert (source['goods_cents'],source['service_cents'],source['unallocated_cents'],source['amount_cents'])==(1000,801,-499,1302)
    material.check_csv_charts(client,report,source='repair');material.check_combined(client)
    assert restore()['verified_points_claims']==1
    return_component(client,row,1500,500)
    assert claim(row)==(952,9)
    report=material.report(client,source='repair');assert report['metrics']['material_source_net_cents']==952
    assert report['metrics']['material_unfulfilled_cost_cents']==0
    assert len(report['tables']['material_goods']['rows'])==2
    assert sum(r['amount_cents'] for r in report['tables']['material_unallocated']['rows'])==-849
    material.check_csv_charts(client,report,source='repair');material.check_combined(client)
    assert restore()['verified_points_claims']==1
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy)
        copy.execute("UPDATE repair_package_payment_links SET recognized_cents=recognized_cents+1 WHERE purpose='capture'")
        with pytest.raises(ValueError,match='套餐积分原对价'):validate_membership_sqlite(copy)


def test_package_stock_return_cost_uses_actual_return_period(client):
    d=package.fixture(client);row=release(client,capture(client,package.finished(client,d,package.quoted(client,d))))
    before=material.report(client,source='repair');cost=before['metrics']['material_selected_goods_cost_cents'];yesterday=today()-timedelta(days=1)
    # Synthetic clock separation only; this test verifies period projections,
    # while the previous test validates the untouched source database restore.
    with engine.begin() as db:
        db.execute(text("UPDATE flow_cases SET data=json_set(data,'$.released_date',:day) WHERE id=:id"),dict(day=yesterday.isoformat(),id=row['id']))
        db.execute(text('UPDATE flow_stock_moves SET business_date=:day WHERE case_id=:id'),dict(day=yesterday.isoformat(),id=row['id']))
    return_component(client,row,1500,500)
    old=material.report(client,source='repair',date_from=yesterday.isoformat(),date_to=yesterday.isoformat())
    now=material.report(client,source='repair',date_from=today().isoformat(),date_to=today().isoformat())
    assert old['metrics']['material_source_net_cents']==1102 and old['metrics']['material_selected_goods_cost_cents']==cost
    assert now['metrics']['material_source_net_cents']==-350 and now['metrics']['material_selected_goods_cost_cents']<0
    assert now['tables']['material_goods']['rows'][0]['amount_cents']==0
    assert now['metrics']['material_unfulfilled_cost_cents']==0
    material.check_csv_charts(client,now,source='repair',date_from=today().isoformat(),date_to=today().isoformat())


@pytest.mark.parametrize('extra',[False,True])
def test_package_stop_actual_retained_goods_and_paid_basis(client,extra):
    d=package.fixture(client);enroll(client,d);row=package.quoted(client,d,extra=extra);login(client,'admin');row=repair.authorize(client,row)
    row=repair.cmd(client,row,'start',{'result':'实际开始检查及用料'});row=repair.issue(client,row,3000)
    row=repair.cmd(client,row,'return_material',{'original_id':row['stock'][0]['id'],'quantity_milli':1500,'evidence_id':evidence(client,row)})
    q=repair.current_quote(client,row);retained=[{'line_key':l['line_key'],'quantity_milli':1500 if l['kind']=='part' else 0} for l in q['lines'][:2]]
    fee=100 if extra else 0
    row=package.post(client,'/orders/'+str(row['id'])+'/quote',{'version':repair.detail(client,row)['version'],'values':{'purpose':'stop','reason':'未做工时取消并保留实际净用材料','retained_amount_cents':500+fee,'package_retained':retained}})
    row=repair.authorize(client,row);row=repair.cmd(client,row,'finish',{'result':'已完成实际停工保留材料交接'})
    row=repair.cmd(client,row,'quality',{'passed':True,'result':'停工实物交接质检合格','evidence_id':evidence(client,row,'inspection')})
    row=capture(client,repair.allocate(client,row))
    if fee:row=repair.receive(client,row,row['allocations'][0],fee,d['account'])
    row=release(client,row)
    assert claim(row)==(350+fee,(350+fee)//100)
    report=material.report(client,source='repair');assert report['metrics']['material_source_net_cents']==350+fee
    goods=report['tables']['material_goods']['rows'];assert len(goods)==1 and goods[0]['quantity_milli']==1500 and goods[0]['amount_cents']==500
    assert report['metrics']['material_unfulfilled_cost_cents']==0
    material.check_csv_charts(client,report,source='repair');material.check_combined(client)
    assert restore()['verified_points_claims']==1


def zero_tail_settled(client,insurer_cents=0):
    d=package.fixture(client,False);p=d['purchase'];row=d['row']
    package.action(client,p,'cancel',{'case_version':package.version(client,row),'reason':'另选明确尾差测试合同'})
    rule=package.post(client,'/rules',{'code':'TAIL-'+uuid.uuid4().hex[:8],'name':'独立分摊尾差合同','allowed_store_ids':[1],
        'validity_days':365,'refund_policy':'unused_anytime','discount_bearer':'service_store','components':[
        {'key':'labor','kind':'work','name':'未用检查','unit':'job','specification':'真实作业独立次数','quantity_milli':1000,'credit_cents':1,'paid_cents':1,'settlement_cents':1},
        {'key':'material','kind':'part','name':'尾差原配件','unit':d['item']['unit'],'specification':'真实原采购同规格','quantity_milli':5000,'credit_cents':3,'paid_cents':2,'settlement_cents':2}]},201)
    login(client,'manager');package.post(client,'/rules/'+str(rule['id'])+'/actions/approve',{'reason':'独立批准整体及区间原对价'})
    for key,source in [('labor',d['work']['id']),('material',d['item']['id'])]:
        package.post(client,'/rules/'+str(rule['id'])+'/mappings',{'component_key':key,'source_id':source,'reason':'真实规格与本店源一致'},201)
    login(client,'service');p=package.post(client,'/purchases',{'rule_id':rule['id'],'member_id':d['member']['id'],'case_id':row['id'],'case_version':package.version(client,row),'sets':1},201)
    p=package.action(client,p,'authorize',{'case_version':package.version(client,row),'evidence_id':evidence(client,row,'authorization')})
    login(client,'finance');p=package.action(client,p,'issue',{'case_version':package.version(client,row),'amount_cents':3,'account_id':d['account'],'reference':uuid.uuid4().hex,'evidence_id':evidence(client,row,'receipt')})
    d['purchase']=p;d['rule']=rule
    refund=package.request_refund(client,d,2000);assert refund['amount_cents']==0
    login(client,'manager');refund=package.refund_action(client,d,refund,'approve')
    login(client,'finance');package.refund_action(client,d,refund,'pay',amount_cents=0,account_id=d['account'],reference=uuid.uuid4().hex,evidence_id=evidence(client,row,'receipt'))
    enroll(client,d,1);login(client,'service');lot=package.info(client,d)['lots'][1]
    lines=[{'kind':'part','source_id':d['item']['id'],'quantity_milli':1000,'unit_price_cents':0,'package_lot_id':lot['id'],'package_lot_version':lot['version']}]
    if insurer_cents:lines.append({'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':insurer_cents})
    row=package.post(client,'/orders/'+str(row['id'])+'/quote',{'version':package.version(client,row),'values':{'reason':'本次仅使用原区间两千至三千，面值零原对价一分','lines':lines}})
    login(client,'admin');row=repair.authorize(client,row);row=repair.cmd(client,row,'start',{'result':'实际开始使用原尾数组件'})
    row=repair.issue(client,row,1000);row=repair.cmd(client,row,'finish',{'result':'真实原配件已完成施工'})
    row=repair.cmd(client,row,'quality',{'passed':True,'result':'真实检查合格','evidence_id':evidence(client,row,'inspection')})
    allocations=[]
    if insurer_cents:
        insurer=repair.typed(client,'insurers',{'code':'PKG-INS-'+uuid.uuid4().hex[:8],'name':'独立承担保险公司'})
        allocations=[{'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':insurer_cents}]
    row=repair.allocate(client,row,allocations);assert not any(a['payer_type']=='customer' for a in row['allocations'])
    row=capture(client,row)
    if insurer_cents:row=repair.receive(client,row,row['allocations'][0],insurer_cents,d['account'])
    row=release(client,row);assert claim(row)==(1,1)
    return d,row


def test_zero_face_original_one_fen_tail_is_consumption_and_original_return(client):
    d,row=zero_tail_settled(client)
    report=material.report(client,source='repair');assert report['metrics']['material_source_net_cents']==1
    assert report['tables']['material_unallocated']['rows'][0]['amount_cents']==1
    material.check_csv_charts(client,report,source='repair');material.check_combined(client)
    assert restore()['verified_points_claims']==1
    return_component(client,row,1000,0);assert claim(row)==(0,0)
    report=material.report(client,source='repair');assert report['metrics']['material_source_net_cents']==0
    assert report['metrics']['material_unfulfilled_cost_cents']==0
    material.check_combined(client);assert restore()['verified_points_claims']==1


def test_zero_face_package_return_never_accesses_other_insurer_customer_cash(client):
    d,row=zero_tail_settled(client,100)
    request=aftercare.create(client,row);source=request['sources'][0]
    assert all(e['kind']!='cash' for e in source['eligible_returns'])
    original=next(x for x in source['eligible_returns'] if x['kind']=='repair_package')
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        insurer_cash=db.execute("SELECT id FROM flow_payment_links WHERE case_id=? AND direction='in'",(row['id'],)).fetchone()[0]
    aftercare.cmd(client,request,'plan',{'reason':'不能把保险到账转作客户原退','lines':[{'source_id':source['id'],'credit_cents':0,
        'returns':[{'kind':'repair_package','original_id':original['entry_id'],'units':1000},{'kind':'cash','original_id':insurer_cash,'units':100}]}]},409)
    aftercare.cmd(client,request,'cancel',{'reason':'拒绝混用原资金后重新按套餐办理'})
    assert claim(row)==(1,1)
    return_component(client,row,1000,0);assert claim(row)==(0,0)
    report=material.report(client,source='repair');assert report['metrics']['material_source_net_cents']==100
    now=repair.detail(client,row)
    assert len(now['allocations'])==1 and now['allocations'][0]['payer_type']=='insurer' and now['allocations'][0]['amount_cents']==100
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        assert db.execute('SELECT sum(CASE direction WHEN \'in\' THEN amount_cents ELSE -amount_cents END) FROM flow_payment_links WHERE case_id=?',(row['id'],)).fetchone()[0]==100
    material.check_combined(client);assert restore()['verified_points_claims']==1


def test_spent_package_consumption_points_become_debt_without_blocking_original_cash_refund(client):
    d=package.fixture(client);enroll(client,d)
    row=release(client,capture(client,package.finished(client,d,package.quoted(client,d))))
    assert claim(row)==(1102,11)
    wallet=benefits.info(client,{'customer_id':d['customer']['id']})['wallets'][0]
    coupon=benefits.rule(client,'coupon',allowed_store_ids=[1],sale_cents_per_unit=0,settlement_cents_per_unit=0,exchange_points_per_unit=1)
    request=membership.create(client,d['customer'],'points_adjust',{'action':'exchange','wallet_id':wallet['id'],'target_rule_id':coupon['id'],'units':11})
    login(client,'finance');membership.cmd(client,request,'execute',{'evidence_id':membership.proof(client,request),'wallet_version':wallet['version'],'reason':'客户实际兑换原套餐履约积分'})
    return_component(client,row,1000,333)
    assert claim(row)==(869,8) and membership.info(client,d['customer'])['points_debt_units']==3
    # The returned original component is unused again; actual original purchase
    # refund must not be blocked or count as a second consumption reversal.
    request=package.request_refund(client,d,1000);assert request['amount_cents']==233
    login(client,'manager');request=package.refund_action(client,d,request,'approve')
    login(client,'finance');package.refund_action(client,d,request,'pay',amount_cents=233,account_id=d['account'],reference=uuid.uuid4().hex,evidence_id=evidence(client,row,'receipt'))
    assert claim(row)==(869,8) and membership.info(client,d['customer'])['points_debt_units']==3
    assert restore()['verified_points_claims']==1


def test_cross_store_actual_package_paid_basis_stays_with_fulfillment_store(client):
    login(client,'admin');response=client.post('/api/stores',json={'code':'PKG-POINTS-B','name':'独立履约积分乙店'});assert response.status_code==201,response.text
    sid=response.json()['id']
    with SessionLocal() as db:
        db.add(UserStore(user_id=db.scalar(select(User.id).where(User.username=='finance')),store_id=sid,role='finance'));db.commit()
    d=package.fixture(client,allowed_store_ids=[1,sid]);enroll(client,d,stores=[1,sid])
    login(client,'admin');client.headers['X-Store-ID']=str(sid)
    row,item,work,customer=repair.setup(client);package.group.link(client,{'customer_id':customer['id']},d['member']['identity_id'])
    for key,source in [('labor',work['id']),('material',item['id'])]:
        package.post(client,'/rules/'+str(d['rule']['id'])+'/mappings',{'component_key':key,'source_id':source,'reason':'乙店核对真实规格与原组件一致'},201)
    p=package.info(client,d);lots=p['lots']
    row=package.post(client,'/orders/'+str(row['id'])+'/quote',{'version':row['version'],'values':{'reason':'乙店使用真实原组件并独立确认消费','lines':[
        {'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':601,'package_lot_id':lots[0]['id'],'package_lot_version':lots[0]['version']},
        {'kind':'part','source_id':item['id'],'quantity_milli':2000,'unit_price_cents':333,'package_lot_id':lots[1]['id'],'package_lot_version':lots[1]['version']}]}})
    row=release(client,capture(client,package.finished(client,d,row)))
    assert claim(row)==(868,8) and claim(d['row']) is None
    assert client.get('/api/flow/cases/'+str(d['row']['id'])).status_code==404
    report=material.report(client,source='repair');assert report['metrics']['material_source_net_cents']==868
    assert {r['case_id'] for r in report['tables']['material_sources']['rows']}=={row['id']}
    material.check_csv_charts(client,report,source='repair')
    client.headers['X-Store-ID']='1'
    assert client.get('/api/flow/cases/'+str(row['id'])).status_code==404
    assert material.report(client,source='repair')['metrics']['material_source_net_cents']==0
    client.headers['X-Store-ID']='all';response=client.get('/api/flow/analytics');assert response.status_code==200,response.text
    report=response.json();assert report['metrics']['repair_cents']==868 and report['metrics']['repair_package_purchase_cash_cents']==1102
    assert report['metrics']['membership_points_change_units']==8
    assert restore()['verified_points_claims']==1


def test_zero_face_tail_actual_one_fen_blue_and_original_red_remain_conserved(client):
    from tests import test_invoices as invoices
    d,row=zero_tail_settled(client);login(client,'finance')
    blue=invoices.actual(client,row['id'],1)
    assert blue['balance']['invoiceable_cents']==blue['balance']['actual_net_cents']==1
    assert restore()['verified_points_claims']==1
    return_component(client,row,1000,0);login(client,'finance')
    balance=invoices.read(client,blue['id'])['balance']
    assert balance['invoiceable_cents']==0 and balance['actual_net_cents']==1
    red=invoices.actual(client,row['id'],1,blue['id'])
    assert red['balance']['invoiceable_cents']==red['balance']['actual_net_cents']==0
    assert claim(row)==(0,0) and restore()['verified_points_claims']==1
