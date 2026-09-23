"""Registered API synthetic purchases, component quantities and original refunds."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal
from app.models import CashEntry
from app.flow_models import Case,PaymentLink,StockMove,Item
from app.repair_package_models import PackagePurchase,PackageLot,PackageEntry,PackageHold,PackageRefundClaim
from tests.conftest import login
from tests.test_repair_orders import technician,setup as repair_setup,cmd,detail,authorize,issue,current_quote,allocate
from tests.test_workflow import evidence
from tests.test_procurement import bank
from tests import test_group_membership as group

API='/api/repair-packages'
def post(c,path,data,status=200,key=None):
    r=c.post(API+path,json={'request_id':key or uuid.uuid4().hex,**data});assert r.status_code==status,r.text;return r.json()
def version(c,row):return c.get('/api/flow/cases/'+str(row['id'])).json()['version']
def action(c,p,name,values,status=200,key=None,ver=None):return post(c,'/purchases/'+str(p['id'])+'/actions/'+name,{'version':p['version'] if ver is None else ver,'values':values},status,key)
def info(c,d):
    r=c.get(API+'/members/'+str(d['member']['id'])+'/purchases');assert r.status_code==200,r.text
    return next(p for p in r.json()['items'] if p['id']==d['purchase']['id'])
def fixture(c,issue_purchase=True,allowed_store_ids=None):
    row,item,work,customer=repair_setup(c)
    # The old repair fixture receives 2.5 units; buy one more real unit for this
    # three-unit component contract instead of directly changing stock totals.
    from tests.test_procurement import supplier,command as purchase_command,receive as purchase_receive
    vendor=supplier(c);r=c.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,'supplier_id':vendor['id'],'reason':'合成套餐实际足量备货','lines':[{'item_id':item['id'],'quantity_milli':1000,'unit_cost_cents':127}]});assert r.status_code==201,r.text
    order=purchase_command(c,r.json(),'approve');purchase_receive(c,order)
    account=bank(c);member=group.issue(c,{'customer_id':customer['id']})
    login(c,'service');rule=post(c,'/rules',{'code':'MIXED-'+uuid.uuid4().hex[:8],'name':'合成工时与实际耗材套餐','allowed_store_ids':allowed_store_ids or [1],'validity_days':365,'refund_policy':'unused_anytime','discount_bearer':'service_store','components':[
        {'key':'labor','kind':'work','name':'合成按次检查','unit':'job','specification':'实际检查工时项目','quantity_milli':1000,'credit_cents':601,'paid_cents':401,'settlement_cents':401},
        {'key':'material','kind':'part','name':'合成真实耗材','unit':item['unit'],'specification':'原采购同规格耗材','quantity_milli':3000,'credit_cents':1000,'paid_cents':701,'settlement_cents':701}]},201)
    login(c,'manager');post(c,'/rules/'+str(rule['id'])+'/actions/approve',{'reason':'不同主管核对冻结组件与价格'})
    for key,source in [('labor',work['id']),('material',item['id'])]:post(c,'/rules/'+str(rule['id'])+'/mappings',{'component_key':key,'source_id':source,'reason':'本店确认具体作业及物料规格单位'},201)
    login(c,'service');p=post(c,'/purchases',{'rule_id':rule['id'],'member_id':member['id'],'case_id':row['id'],'case_version':version(c,row),'sets':1},201)
    d={'row':row,'item':item,'work':work,'customer':customer,'account':account,'member':member,'rule':rule,'purchase':p}
    if issue_purchase:
        p=action(c,p,'authorize',{'case_version':version(c,row),'evidence_id':evidence(c,row,'authorization')})
        login(c,'finance');p=action(c,p,'issue',{'case_version':version(c,row),'amount_cents':1102,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')});d['purchase']=p
    return d

def request_refund(c,d,quantity=1000,lot_key='material'):
    login(c,'service');p=info(c,d);lot=next(l for l in p['lots'] if l['component_key']==lot_key)
    return action(c,p,'refund_request',{'case_version':version(c,d['row']),'selections':[{'lot_id':lot['id'],'quantity_milli':quantity}],'reason':'客户未用组件明确原款退款','evidence_id':evidence(c,d['row'])})

def refund_action(c,d,r,name,**kwargs):
    v={'case_version':version(c,d['row']),'reason':'核对原组件区间与实际退款',**kwargs}
    if name=='pay':v.pop('reason')
    return post(c,'/refunds/'+str(r['id'])+'/actions/'+name,{'version':r['version'],'values':v})

def test_purchase_once_unused_components_and_exact_original_partial_refund(client):
    d=fixture(client);p=info(client,d)
    assert p['status']=='issued' and [l['available_milli'] for l in p['lots']]==[1000,3000]
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(CashEntry.amount_cents)).where(CashEntry.category=='repair_package_purchase'))==1102
        assert db.scalar(select(func.count()).select_from(PaymentLink).where(PaymentLink.case_id==d['row']['id']))==0
        before=db.scalar(select(func.count()).select_from(StockMove))
    refund=request_refund(client,d);assert refund['amount_cents']==233
    login(client,'manager');refund=refund_action(client,d,refund,'approve')
    login(client,'finance');refund=refund_action(client,d,refund,'pay',amount_cents=233,account_id=d['account'],reference=uuid.uuid4().hex,evidence_id=evidence(client,d['row'],'receipt'))
    assert refund['status']=='executed'
    p=info(client,d);assert p['lots'][1]['available_milli']==2000
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(CashEntry.amount_cents)).where(CashEntry.category=='repair_package_refund'))==233
        assert db.scalar(select(func.count()).select_from(StockMove))==before

def test_rule_independence_purchase_duplicate_stale_and_cancel(client):
    d=fixture(client,False);p=d['purchase'];row=d['row']
    proof=evidence(client,row,'authorization');v={'case_version':version(client,row),'evidence_id':proof};key=uuid.uuid4().hex
    result=action(client,p,'authorize',v,key=key);assert action(client,p,'authorize',v,key=key)==result
    action(client,p,'authorize',v,409)
    p=action(client,result,'cancel',{'case_version':version(client,row),'reason':'尚未实际付款，取消原合同'})
    assert p['status']=='cancelled' and p['lots']==[]
    login(client,'finance');action(client,p,'issue',{'case_version':version(client,row),'amount_cents':1102,'account_id':d['account'],'reference':uuid.uuid4().hex,'evidence_id':evidence(client,row,'receipt')},409)

def test_refund_approval_holds_exact_component_then_cancel_releases(client):
    d=fixture(client);a=request_refund(client,d,2000);b=request_refund(client,d,2000)
    login(client,'manager');a=refund_action(client,d,a,'approve')
    post(client,'/refunds/'+str(b['id'])+'/actions/approve',{'version':b['version'],'values':{'case_version':version(client,d['row']),'reason':'竞争退款不能重复批准'}},409)
    assert info(client,d)['lots'][1]['available_milli']==1000
    a=refund_action(client,d,a,'cancel');assert a['status']=='cancelled'
    assert info(client,d)['lots'][1]['available_milli']==3000

def test_interval_fen_conservation_for_arbitrary_splits_and_original_restore():
    from types import SimpleNamespace
    from app.repair_package_service import amounts,subtract,take
    lot=SimpleNamespace(quantity_milli=3000,credit_cents=1000,paid_cents=701,settlement_cents=701)
    pieces=[[[0,1]],[[1,500]],[[500,1000]],[[1000,2019]],[[2019,3000]]]
    assert {k:sum(amounts(lot,p)[k] for p in pieces) for k in ('quantity_milli','credit_cents','paid_cents','settlement_cents')}=={'quantity_milli':3000,'credit_cents':1000,'paid_cents':701,'settlement_cents':701}
    assert take(subtract([[0,3000]],[[500,1000],[2019,3000]]),600)==[[0,500],[1000,1100]]
    tricky=SimpleNamespace(quantity_milli=5000,credit_cents=3,paid_cents=2,settlement_cents=2)
    assert amounts(tricky,[[2000,3000]])=={'quantity_milli':1000,'credit_cents':0,'paid_cents':1,'settlement_cents':1}

def quoted(c,d,part_quantity=3000,extra=False):
    login(c,'service');p=info(c,d);work,part=p['lots'];qty=part_quantity;face=part['credit_cents']*qty//part['quantity_milli']
    lines=[{'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':601,'package_lot_id':work['id'],'package_lot_version':work['version']},
           {'kind':'part','source_id':d['item']['id'],'quantity_milli':qty,'unit_price_cents':(face*1000+qty-1)//qty,'package_lot_id':part['id'],'package_lot_version':part['version']}]
    if extra:lines.append({'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':200})
    return post(c,'/orders/'+str(d['row']['id'])+'/quote',{'version':detail(c,d['row'])['version'],'values':{'reason':'按真实合同分别报价和冻结原组件','lines':lines}})

def finished(c,d,row):
    login(c,'admin');row=authorize(c,row);row=cmd(c,row,'start',{'result':'实际开始本次已授权作业'})
    line=next(l for l in current_quote(c,row)['lines'] if l['kind']=='part');row=issue(c,row,line['quantity_milli'])
    row=cmd(c,row,'finish',{'result':'本次作业及净领配件实际施工完成'})
    row=cmd(c,row,'quality',{'passed':True,'result':'本次检查实际合格','evidence_id':evidence(c,row,'inspection')});return allocate(c,row)

def test_real_component_quote_stock_capture_and_extra_cash_once(client):
    d=fixture(client);row=quoted(client,d,extra=True)
    assert row['quotes'][-1]['amount_cents']==1801
    assert [l['amount_cents'] for l in row['quotes'][-1]['lines']]==[601,1000,200]
    row=finished(client,d,row)
    assert row['customer_due_cents']==200
    result=post(client,'/orders/'+str(row['id'])+'/capture',{'version':row['version'],'values':{'evidence_id':evidence(client,row)}})
    row=detail(client,row);assert row['customer_due_cents']==200
    from tests.test_repair_orders import receive
    row=receive(client,row,row['allocations'][0],200,d['account']);row=cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='completed'
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.case_id==row['id']))==200
        assert db.scalar(select(func.sum(CashEntry.amount_cents)).where(CashEntry.category=='repair_package_purchase'))==1102
        assert db.scalar(select(func.sum(StockMove.quantity_milli)).where(StockMove.case_id==row['id']))==-3000
    assert [l['available_milli'] for l in info(client,d)['lots']]==[0,0]

def test_unstarted_cancel_releases_components_and_does_not_refund_purchase(client):
    d=fixture(client);row=quoted(client,d)
    assert [l['available_milli'] for l in info(client,d)['lots']]==[0,0]
    row=cmd(client,row,'cancel',{'reason':'本次未开工，客户取消维修预约'})
    assert row['state']=='cancelled' and [l['available_milli'] for l in info(client,d)['lots']]==[1000,3000]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.category=='repair_package_refund'))==0

def test_partial_material_return_and_cancel_single_work_keep_exact_contract(client):
    d=fixture(client);row=quoted(client,d);login(client,'admin');row=authorize(client,row);row=cmd(client,row,'start',{'result':'实际开始检查用料'})
    row=issue(client,row,3000);original=row['stock'][0]
    row=cmd(client,row,'return_material',{'original_id':original['id'],'quantity_milli':1500,'evidence_id':evidence(client,row)})
    q=current_quote(client,row);retained=[{'line_key':l['line_key'],'quantity_milli':0 if l['kind']=='work' else 1500} for l in q['lines']]
    row=post(client,'/orders/'+str(row['id'])+'/quote',{'version':detail(client,row)['version'],'values':{'purpose':'stop','reason':'单项作业未执行取消，仅保留实际净用材料','retained_amount_cents':500,'package_retained':retained}})
    row=authorize(client,row);row=cmd(client,row,'finish',{'result':'确认已停工及实际保留的材料'})
    row=cmd(client,row,'quality',{'passed':True,'result':'停工交接实际质检合格','evidence_id':evidence(client,row)});row=allocate(client,row)
    post(client,'/orders/'+str(row['id'])+'/capture',{'version':row['version'],'values':{'evidence_id':evidence(client,row)}})
    p=info(client,d);assert [l['available_milli'] for l in p['lots']]==[1000,1500]
    from app.repair_package_service import analytics_rows
    from app.tenancy import set_scope,project_user
    from app.models import User
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'));report=analytics_rows(db,user)
        assert sum(e['credit_cents'] for e in report['entries'])==500
        assert sum(e['recognized_cents'] for e in report['entries'])==350

def test_completed_original_component_return_requires_actual_stock_and_restores_original_value(client):
    from tests import test_aftercare as aftercare
    from app.repair_package_models import PackagePaymentLink,PackageStockReturn
    from app.backup_integrity import validate_sqlite
    from tests.conftest import TEST_DIR
    import sqlite3
    d=fixture(client);row=finished(client,d,quoted(client,d));proof=evidence(client,row)
    payload={'version':row['version'],'values':{'evidence_id':proof}};key=uuid.uuid4().hex
    captured=post(client,'/orders/'+str(row['id'])+'/capture',payload,key=key)
    assert post(client,'/orders/'+str(row['id'])+'/capture',payload,key=key)==captured
    row=cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    request=aftercare.create(client,row);original=next(x for x in request['sources'][0]['eligible_returns'] if x['kind']=='repair_package')
    request=aftercare.plan(client,request,333,[{'kind':'repair_package','original_id':original['entry_id'],'units':1000}])
    request=aftercare.confirmed(client,aftercare.approved(client,request))
    aftercare.cmd(client,request,'apply',{'evidence_id':evidence(client,request,'receipt')},409)
    login(client,'inventory');target=client.get(API+'/aftercare/'+str(request['id'])+'/return-targets').json();h=target['items'][0]
    assert not {'paid_cents','settlement_cents','member_id','cash_id'}&h.keys()
    proof=evidence(client,request,'inspection');body={'version':target['version'],'source_version':h['source_version'],'hold_id':h['hold_id'],'original_stock_id':h['original_stocks'][0]['id'],'quantity_milli':1000,'passed':True,'result':'实际收到原配件，检查可按原成本入库','evidence_id':proof};key=uuid.uuid4().hex
    returned=post(client,'/aftercare/'+str(request['id'])+'/return-material',body,key=key)
    assert post(client,'/aftercare/'+str(request['id'])+'/return-material',body,key=key)==returned
    login(client,'admin');aftercare.cmd(client,request,'cancel_plan',{'reason':'已有实际入库不可抹除'},409)
    request=aftercare.applied(client,request);assert request['state']=='completed'
    p=info(client,d);assert [l['available_milli'] for l in p['lots']]==[0,1000]
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(PackagePaymentLink.amount_cents)))==1268
        assert db.scalar(select(func.sum(PackagePaymentLink.recognized_cents)))==869
        assert db.scalar(select(func.sum(StockMove.quantity_milli)).where(StockMove.case_id==row['id']))==-2000
        assert db.scalar(select(func.count()).select_from(PackageStockReturn))==1
        assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.category.like('repair_package%')))==1
    refund=request_refund(client,d);assert refund['amount_cents']==233
    login(client,'manager');refund=refund_action(client,d,refund,'approve')
    login(client,'finance');refund_action(client,d,refund,'pay',amount_cents=233,account_id=d['account'],reference=uuid.uuid4().hex,evidence_id=evidence(client,d['row'],'receipt'))
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_repair_package_entries']==4

def test_cross_store_explicit_identity_mapping_local_actual_stock_without_original_cash_access(client):
    login(client,'admin');r=client.post('/api/stores',json={'code':'PACKAGE-B','name':'合成套餐履约乙店'});assert r.status_code==201,r.text;sid=r.json()['id']
    d=fixture(client,allowed_store_ids=[1,sid]);login(client,'admin');client.headers['X-Store-ID']=str(sid)
    assert client.get(API+'/members/'+str(d['member']['id'])+'/purchases').status_code==404
    row,item,work,customer=repair_setup(client);group.link(client,{'customer_id':customer['id']},d['member']['identity_id'])
    p=info(client,d);assert not {'case_id','cash_id','account_id','refunds','amount_cents'}&p.keys()
    assert client.get('/api/flow/cases/'+str(d['row']['id'])).status_code==404
    for key,source in [('labor',work['id']),('material',item['id'])]:post(client,'/rules/'+str(d['rule']['id'])+'/mappings',{'component_key':key,'source_id':source,'reason':'乙店明确同规格实际作业与物料'},201)
    p=info(client,d);lots=p['lots'];lines=[{'kind':'work','source_id':work['id'],'quantity_milli':1000,'unit_price_cents':601,'package_lot_id':lots[0]['id'],'package_lot_version':lots[0]['version']},{'kind':'part','source_id':item['id'],'quantity_milli':2000,'unit_price_cents':333,'package_lot_id':lots[1]['id'],'package_lot_version':lots[1]['version']}]
    row=post(client,'/orders/'+str(row['id'])+'/quote',{'version':row['version'],'values':{'reason':'乙店原权益实际履约独立报价','lines':lines}})
    row=finished(client,d,row);post(client,'/orders/'+str(row['id'])+'/capture',{'version':row['version'],'values':{'evidence_id':evidence(client,row)}})
    row=cmd(client,row,'release',{'evidence_id':evidence(client,row)});assert row['state']=='completed'
    p=info(client,d);action(client,p,'refund_request',{'case_version':version(client,row),'selections':[{'lot_id':lots[1]['id'],'quantity_milli':1000}],'reason':'乙店不得退甲原款','evidence_id':evidence(client,row)},404)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.store_id==sid,CashEntry.category.like('repair_package%')))==0
        assert db.scalar(select(func.sum(StockMove.quantity_milli)).where(StockMove.case_id==row['id']))==-2000
    client.headers['X-Store-ID']='1';assert info(client,d)['lots'][1]['available_milli']==1000
    assert client.get('/api/flow/cases/'+str(row['id'])).status_code==404

def test_two_real_orders_compete_for_one_original_component(client):
    from tests.test_repair_orders import create
    d=fixture(client);login(client,'service');second=create(client,d['customer']);p=info(client,d);lot=p['lots'][0]
    bodies=[{'request_id':uuid.uuid4().hex,'version':detail(client,r)['version'],'values':{'reason':'并发争用同一原作业次数','lines':[{'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':601,'package_lot_id':lot['id'],'package_lot_version':lot['version']}]}} for r in (d['row'],second)]
    a=TestClient(app);b=TestClient(app);login(a,'service');login(b,'service')
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(c.post,API+'/orders/'+str(r['id'])+'/quote',json=body) for c,r,body in zip((a,b),(d['row'],second),bodies)]
        results=[j.result() for j in jobs]
    a.close();b.close();assert sorted(r.status_code for r in results)==[200,409],[r.text for r in results]
    assert info(client,d)['lots'][0]['available_milli']==0
    winner=(d['row'],second)[next(i for i,r in enumerate(results) if r.status_code==200)]
    cmd(client,winner,'cancel',{'reason':'未开工原工单明确取消释放'});assert info(client,d)['lots'][0]['available_milli']==1000

def test_two_authorized_stores_compete_for_last_original_work_quantity(client):
    login(client,'admin');r=client.post('/api/stores',json={'code':'PACKAGE-RACE','name':'合成跨店争用原套餐'});assert r.status_code==201,r.text;sid=r.json()['id']
    d=fixture(client,allowed_store_ids=[1,sid]);login(client,'admin');client.headers['X-Store-ID']=str(sid)
    row,item,work,customer=repair_setup(client);group.link(client,{'customer_id':customer['id']},d['member']['identity_id']);post(client,'/rules/'+str(d['rule']['id'])+'/mappings',{'component_key':'labor','source_id':work['id'],'reason':'乙店明确同单位实际作业'},201)
    lot=info(client,d)['lots'][0];client.headers['X-Store-ID']='1'
    a,b=TestClient(app),TestClient(app);login(a);login(b);b.headers['X-Store-ID']=str(sid)
    jobs=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for c,r,w in ((a,d['row'],d['work']),(b,row,work)):
            body={'request_id':uuid.uuid4().hex,'version':detail(c,r)['version'],'values':{'reason':'两个授权门店竞争原最后作业次数','lines':[{'kind':'work','source_id':w['id'],'quantity_milli':1000,'unit_price_cents':601,'package_lot_id':lot['id'],'package_lot_version':lot['version']}]}}
            jobs.append(pool.submit(c.post,API+'/orders/'+str(r['id'])+'/quote',json=body))
        results=[j.result() for j in jobs]
    a.close();b.close();assert sorted(r.status_code for r in results)==[200,409],[r.text for r in results]
    assert info(client,d)['lots'][0]['available_milli']==0
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.category=='repair_package_purchase'))==1

def test_expiry_wrong_customer_and_roles_refuse_without_new_facts(client,monkeypatch):
    from datetime import timedelta
    from app.db import today
    from app import repair_package_service as service
    from tests.test_repair_orders import create
    from tests.test_workflow import master
    d=fixture(client);login(client,'admin');other=master(client,'customers',{'name':'不同实际客户','phone':'13900000299','contact_allowed':True,'note':''});other_row=create(client,other);p=info(client,d);lot=p['lots'][0]
    values={'reason':'不得核销其他客户合同','lines':[{'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':601,'package_lot_id':lot['id'],'package_lot_version':lot['version']}]}
    post(client,'/orders/'+str(other_row['id'])+'/quote',{'version':other_row['version'],'values':values},409)
    login(client,'inventory');assert client.get(API+'/members/'+str(d['member']['id'])+'/purchases').status_code==403
    login(client,'service')
    with monkeypatch.context() as patch:
        patch.setattr(service,'today',lambda:today()+timedelta(days=366))
        post(client,'/orders/'+str(d['row']['id'])+'/quote',{'version':detail(client,d['row'])['version'],'values':values},409)
    assert info(client,d)['lots'][0]['available_milli']==1000

@pytest.mark.parametrize('authorized',[False,True])
def test_source_cancellation_closes_unpaid_contract_in_same_transaction(client,authorized):
    from app.flow_models import Task
    d=fixture(client,False);p=d['purchase']
    if authorized:p=action(client,p,'authorize',{'case_version':version(client,d['row']),'evidence_id':evidence(client,d['row'],'authorization')})
    cmd(client,d['row'],'cancel',{'reason':'客户撤销原尚未开工业务'})
    p=info(client,d);assert p['status']=='cancelled' and not p['lots']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Task).where(Task.case_id==d['row']['id'],Task.key.like('repair_package_%'),Task.status=='open'))==0
        assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.category=='repair_package_purchase'))==0
    login(client,'finance');action(client,p,'issue',{'case_version':version(client,d['row']),'amount_cents':1102,'account_id':d['account'],'reference':uuid.uuid4().hex,'evidence_id':evidence(client,d['row'],'receipt')},409)

def test_purchase_sum_limit_and_service_internal_projection(client):
    d=fixture(client);login(client,'service');rules=client.get(API+'/rules').json()['items'];r=next(r for r in rules if r['id']==d['rule']['id'])
    assert 'discount_bearer' not in r['contract'] and all('settlement_cents' not in c for c in r['contract']['components'])
    assert all('settlement_cents' not in lot for lot in info(client,d)['lots'])
    refund=request_refund(client,d);assert all('settlement_cents' not in s for s in refund['selections'])
    components=[dict(c,credit_cents=1_000_000_000,paid_cents=1_000_000_000,settlement_cents=1_000_000_000) for c in r['contract']['components']]
    huge=post(client,'/rules',dict(code='LIMIT-'+uuid.uuid4().hex,name='明确总和上限测试',allowed_store_ids=[1],validity_days=365,refund_policy='unused_anytime',discount_bearer='service_store',components=components),201)
    login(client,'manager');post(client,'/rules/'+str(huge['id'])+'/actions/approve',{'reason':'独立批准可按合理套数购买'})
    login(client,'service');post(client,'/purchases',{'rule_id':huge['id'],'member_id':d['member']['id'],'case_id':d['row']['id'],'case_version':version(client,d['row']),'sets':10000},422)
    assert len(client.get(API+'/members/'+str(d['member']['id'])+'/purchases').json()['items'])==1

def test_zero_consideration_original_interval_closes_without_account_or_cash(client):
    from app.backup_integrity import validate_sqlite
    from tests.conftest import TEST_DIR
    import sqlite3
    d=fixture(client);r=request_refund(client,d,1);assert r['amount_cents']==0
    login(client,'manager');r=refund_action(client,d,r,'approve')
    login(client,'finance');r=refund_action(client,d,r,'pay',amount_cents=0,evidence_id=evidence(client,d['row']))
    assert r['status']=='executed' and r['cash_id'] is None
    assert info(client,d)['lots'][1]['available_milli']==2999
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.category.like('repair_package%')))==1
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_repair_package_refunds']==1

def test_cancel_pending_amendment_restores_original_authorized_component_claims(client):
    d=fixture(client);row=quoted(client,d);login(client,'admin');row=authorize(client,row);old=current_quote(client,row);p=info(client,d)
    lines=[{'kind':l['kind'],'source_id':l['work_item_id'] or l['item_id'],'line_key':l['line_key'],'quantity_milli':l['quantity_milli'],'unit_price_cents':l['unit_price_cents'],'package_lot_id':lot['id'],'package_lot_version':lot['version']} for l,lot in zip(old['lines'],p['lots'])]
    lines.append({'kind':'work','source_id':d['work']['id'],'quantity_milli':1000,'unit_price_cents':200})
    row=post(client,'/orders/'+str(row['id'])+'/quote',{'version':row['version'],'values':{'reason':'待批新增自费，保留旧授权组件','lines':lines}})
    assert row['quotes'][-1]['amount_cents']==1801
    row=cmd(client,row,'quote_cancel',{'quote_id':row['quotes'][-1]['id'],'reason':'客户撤回尚未授权增项'})
    assert row['data']['quote_id']==old['id'] and [l['available_milli'] for l in info(client,d)['lots']]==[0,0]
    row=cmd(client,row,'cancel',{'reason':'原工单尚未开工明确取消'})
    assert [l['available_milli'] for l in info(client,d)['lots']]==[1000,3000]

@pytest.mark.parametrize('sql',[
    'UPDATE repair_package_payment_links SET recognized_cents=recognized_cents+1',
    "UPDATE repair_package_entries SET spans='[[0,999]]' WHERE purpose='capture'",
    'UPDATE repair_package_purchases SET amount_cents=amount_cents+1',
    "UPDATE repair_package_holds SET status='reserved' WHERE status='captured'",
    'UPDATE repair_package_settlements SET amount_cents=amount_cents+1 WHERE amount_cents>0',
])
def test_independent_restore_recomputes_original_components_and_local_links(client,sql):
    import sqlite3
    from app.repair_package_integrity import validate
    from tests.conftest import TEST_DIR
    d=fixture(client);row=finished(client,d,quoted(client,d));post(client,'/orders/'+str(row['id'])+'/capture',{'version':row['version'],'values':{'evidence_id':evidence(client,row)}})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate(restored)['verified_repair_package_entries']==2
        restored.execute(sql)
        with pytest.raises(ValueError,match='混合维修套餐恢复检查'):validate(restored)
