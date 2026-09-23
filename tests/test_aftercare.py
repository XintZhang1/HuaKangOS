"""Post-performance corrections preserve originals and limit every original tender."""
import uuid
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import User,UserStore,Store,CashEntry
from app.flow_models import Case,PaymentLink,Task,VehicleHold
from app.aftercare_models import AftercareAdjustment,AftercareApplication,AftercarePlan,AftercareClaim,AftercareCashRefund
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import evidence,master,order as sales_order,action as sales_action,detail as sales_detail,seed_car,approved_doc
from tests.test_repair_orders import setup,ready,allocate,receive,cmd as repair_cmd,detail as repair_detail,typed
from tests.test_procurement import bank
API='/api/aftercare/orders'

@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        user=User(username='technician',display_name='售后技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit()

def detail(c,row):
    r=c.get(API+'/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def create(c,source,scenario='repair_refund',status=201,key=None):
    r=c.post(API,json={'request_id':key or uuid.uuid4().hex,'source_case_id':source['id'],
        'source_version':sales_detail(c,source)['version'],'scenario':scenario,'reason':'核对原实际履约与客户协商减免'})
    assert r.status_code==status,r.text;return r.json()
def payload(c,row,v,key=None):
    current=detail(c,row)
    return {'request_id':key or uuid.uuid4().hex,'version':current['version'],
        'source_versions':{str(s['case_id']):s['version'] for s in current['sources']},'values':v}
def cmd(c,row,action,v=None,status=200,body=None):
    r=c.post(API+f"/{row['id']}/actions/{action}",json=body or payload(c,row,v or {}));assert r.status_code==status,r.text;return r.json()
def completed_repair(c,split=False):
    row,item,work,_=setup(c);row=ready(c,row,item,work)
    if split:
        insurer=typed(c,'insurers',{'code':'AFTER-INS','name':'合成承担保险公司'})
        row=allocate(c,row,[{'payer_type':'customer','amount_cents':6000},{'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':4997}])
    else:row=allocate(c,row)
    account=bank(c);row=receive(c,row,row['allocations'][0],row['allocations'][0]['amount_cents'],account)
    row=repair_cmd(c,row,'release',{'evidence_id':evidence(c,row)})
    return row,account
def plan(c,row,credit,returns=None):
    current=detail(c,row);source=current['sources'][0]
    returns=returns if returns is not None else [{'kind':'cash','original_id':source['eligible_returns'][0]['entry_id'],'units':credit}]
    return cmd(c,row,'plan',{'reason':'逐项核对保留费用及原收款退款','lines':[{'source_id':source['id'],'credit_cents':credit,'returns':returns}]})
def approved(c,row):
    previous=c.get('/api/auth/me').json()['username']
    if previous!='manager':login(c,'manager')
    result=cmd(c,row,'approve',{'reason':'独立主管核对当前完整方案','evidence_id':evidence(c,row,'authorization')})
    if previous!='manager':login(c,previous)
    return result
def confirmed(c,row):return cmd(c,row,'customer_confirm',{'evidence_id':evidence(c,row,'authorization')})
def applied(c,row):return cmd(c,row,'apply',{'evidence_id':evidence(c,row,'receipt')})
def refund(c,row,account,amount,**kw):
    current=detail(c,row);t=next(t for p in current['plans'] if p['id']==current['plan_id'] for t in p['returns'] if t['kind']=='cash')
    return cmd(c,row,'refund',{'tender_id':t['id'],'amount_cents':amount,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')},**kw)

def test_repair_refund_partial_actual_cash_keeps_quote_delivery_and_other_payer(client):
    source,account=completed_repair(client,True);original=sales_detail(client,source);row=create(client,source)
    row=plan(client,row,1501);row=approved(client,row);row=confirmed(client,row)
    assert repair_detail(client,source)['revenue_cents']==10997
    row=applied(client,row);assert row['state']=='working' and row['sources'][0]['refund_cents']==1501
    assert repair_detail(client,source)['revenue_cents']==9496
    refund(client,row,account,1502,status=409)
    row=refund(client,row,account,1000);row=refund(client,row,account,501)
    assert row['state']=='completed' and row['sources'][0]['paid_cents']==4499
    now=repair_detail(client,source);assert now['receivable_cents']==4997 and now['data']['released_date']==source['data']['released_date']
    now=receive(client,now,now['allocations'][1],4997,account);assert now['state']=='completed'
    with SessionLocal() as db:
        assert db.get(Case,source['id']).amount_cents==original['amount_cents']
        assert db.scalar(select(func.sum(AftercareAdjustment.credit_cents)))==1501
        assert db.scalar(select(func.sum(PaymentLink.amount_cents)).where(PaymentLink.direction=='out'))==1501
        assert db.scalar(select(func.count()).select_from(AftercareClaim))==0

def test_aftercare_freezes_original_customer_but_allows_insurance_later_cash(client):
    source,account=completed_repair(client,True);row=create(client,source)
    allocations=repair_detail(client,source)['allocations'];source=receive(client,source,allocations[1],4997,account)
    repair_cmd(client,source,'receive',{'allocation_id':allocations[0]['id'],'amount_cents':1,'account_id':account,
        'reference':'不能绕过售后','evidence_id':evidence(client,source,'receipt')},409)
    create(client,source,status=409);cmd(client,row,'cancel',{'reason':'客户撤销尚未执行申请'})
    create(client,source)

def test_repeat_refunds_cumulative_original_limit_and_forgery(client):
    source,account=completed_repair(client);row=applied(client,confirmed(client,approved(client,plan(client,create(client,source),10000))))
    row=refund(client,row,account,10000)
    second=create(client,source)
    current=detail(client,second);s=current['sources'][0]
    cmd(client,second,'plan',{'reason':'不能超过尚未减免原费','lines':[{'source_id':s['id'],'credit_cents':998,'returns':[]}]},422)
    other,_=completed_repair(client);otherpayment=sales_detail(client,other)['payments'][0]['id']
    cmd(client,second,'plan',{'reason':'伪造另一原单收款','lines':[{'source_id':s['id'],'credit_cents':997,'returns':[{'kind':'cash','original_id':otherpayment,'units':997}]}]},409)
    second=applied(client,confirmed(client,approved(client,plan(client,second,997))));second=refund(client,second,account,997)
    assert second['sources'][0]['net_cents']==0 and second['sources'][0]['paid_cents']==0
    listed=client.get(API+'/sources').json();assert source['id'] not in {r['id'] for r in listed['items']} and listed['total']==len(listed['items'])

def test_request_replays_stale_source_and_same_transaction_competition(client):
    source,account=completed_repair(client);row=create(client,source)
    current=detail(client,row);s=current['sources'][0];values={'reason':'明确一元原路退款','lines':[{'source_id':s['id'],'credit_cents':100,'returns':[{'kind':'cash','original_id':s['eligible_returns'][0]['entry_id'],'units':100}]}]}
    body=payload(client,row,values);row=cmd(client,row,'plan',body=body);assert cmd(client,row,'plan',body=body)==row
    cmd(client,row,'plan',body={**body,'request_id':uuid.uuid4().hex},status=409)
    row=applied(client,confirmed(client,approved(client,row)));t=row['plans'][-1]['returns'][0]
    proof=evidence(client,row,'receipt');base=payload(client,row,{'tender_id':t['id'],'amount_cents':100,'account_id':account,'reference':'竞争原款','evidence_id':proof})
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c)
        def run(i):return clients[i].post(API+f"/{row['id']}/actions/refund",json={**base,'request_id':uuid.uuid4().hex}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(run,range(2)))
    assert sorted(statuses)==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AftercareCashRefund))==1

def test_cancel_approved_plan_leaves_ledger_and_allows_new_version(client):
    source,_=completed_repair(client);row=approved(client,plan(client,create(client,source),100));row=cmd(client,row,'cancel_plan',{'reason':'客户改为另一协商金额'})
    assert row['state']=='pending' and row['plans'][0]['cancelled']
    row=plan(client,row,200);assert row['plans'][-1]['revision']==2
    row=cmd(client,row,'reject',{'reason':'主管不同意本次费用方案'})
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AftercareApplication))==0
        assert db.scalar(select(func.count()).select_from(AftercareClaim))==0

def test_customer_confirm_and_finance_proof_bound_to_new_case_and_category(client):
    source,account=completed_repair(client);old=evidence(client,source,'receipt');row=plan(client,create(client,source),100)
    login(client,'manager');cmd(client,row,'approve',{'reason':'不能借旧业务证明','evidence_id':old},422)
    manager_proof=evidence(client,row,'authorization');row=cmd(client,row,'approve',{'reason':'主管逐项核对方案','evidence_id':manager_proof});login(client)
    cmd(client,row,'customer_confirm',{'evidence_id':manager_proof},409)
    row=confirmed(client,row);cmd(client,row,'apply',{'evidence_id':old},422)
    cmd(client,row,'apply',{'evidence_id':evidence(client,row)},422)
    row=applied(client,row);cmd(client,row,'cancel',{'reason':'不能取消实际纠正'},409)

def test_employee_roles_and_cross_store_price_permissions(client):
    source,_=completed_repair(client);login(client,'service');row=create(client,source);row=plan(client,row,100)
    cmd(client,row,'approve',{'reason':'经办不能自批','evidence_id':evidence(client,row,'authorization')},403)
    login(client,'manager');row=approved(client,row);login(client,'service');row=confirmed(client,row)
    cmd(client,row,'apply',{'evidence_id':evidence(client,row)},403)
    login(client,'finance');row=applied(client,row)
    with SessionLocal() as db:
        db.add(Store(id=2,code='OTHER',name='另一家店'));db.flush();user=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=user.id,store_id=2));db.commit()
    login(client);client.headers['X-Store-ID']='2'
    assert client.get(API+'/'+str(row['id'])).status_code==404
    assert client.get(API).json()['items']==[]

def test_undispatched_sale_termination_retained_unpaid_fee_has_own_collection(client):
    source=sales_action(client,sales_order(client,'100.00'),'approve');source=sales_action(client,source,'allocate',{'vehicle_id':seed_car()})
    row=create(client,source,'sale_termination');row=plan(client,row,8000,[]);row=applied(client,confirmed(client,approved(client,row)))
    assert row['sources'][0]['due_cents']==2000 and row['state']=='working'
    account=bank(client);row=cmd(client,row,'collect',{'source_id':row['sources'][0]['id'],'amount_cents':2000,'account_id':account,'reference':'原履约保留费','evidence_id':evidence(client,row,'receipt')})
    assert row['state']=='completed' and row['sources'][0]['paid_cents']==2000
    sales_action(client,source,'allocate',{'vehicle_id':seed_car()},409)
    with SessionLocal() as db:
        assert not db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id']))
        assert db.get(Case,source['id']).state=='executing'

def test_delivered_sale_cannot_apply_without_actual_vehicle_intake(client):
    source=sales_action(client,sales_order(client,'100.00'),'approve');source=sales_action(client,source,'allocate',{'vehicle_id':seed_car()})
    sid=approved_doc(client,source,'contract');source=sales_action(client,source,'sign',{'evidence_id':evidence(client,source,'signed_contract',sid)})
    account=bank(client);source=sales_action(client,source,'receive',{'amount':'100','account_id':account,'reference':'提车原款','evidence_id':evidence(client,source,'receipt')})
    source=sales_action(client,source,'inspect',{'outcome':'合格','result':'出库前检查正常','evidence_id':evidence(client,source,'inspection')})
    source=sales_action(client,source,'dispatch',{'evidence_id':evidence(client,source)})
    handover=approved_doc(client,source,'handover');source=sales_action(client,source,'deliver',{'evidence_id':evidence(client,source,'signed_handover',handover)})
    row=confirmed(client,approved(client,plan(client,create(client,source,'vehicle_return'),10000)))
    assert row['vehicle_return']['accepted'] is False
    cmd(client,row,'apply',{'evidence_id':evidence(client,row,'receipt')},409)
    with SessionLocal() as db:assert db.scalar(select(VehicleHold).where(VehicleHold.case_id==source['id'])).delivered is True

def test_sales_child_service_needs_real_stop_and_each_retained_fee(client):
    source=sales_action(client,sales_order(client,'100.00',addon=True,insurance=True),'approve')
    children=sales_detail(client,source)['children'];addon=next(c for c in children if c['kind']=='addon');ins=next(c for c in children if c['kind']=='insurance')
    sales_action(client,addon,'service_quote',{'amount':'20.00','work':'核对关联原服务项目'})
    sales_action(client,ins,'service_quote',{'amount':'20.00','insurer':'合成保险公司','commission':'0'})
    sales_action(client,addon,'service_finish',{'evidence_id':evidence(client,addon)})
    row=create(client,source,'sale_termination');links={s['kind']:s for s in row['sources']}
    lines=[{'source_id':s['id'],'credit_cents':s['net_cents'],'returns':[],**({'commission_credit_cents':0} if s['kind']=='insurance' else {})} for s in row['sources']]
    cmd(client,row,'plan',{'reason':'不能遗漏实际履约说明','lines':lines},409)
    cmd(client,row,'execution',{'source_id':links['addon']['id'],'outcome':'not_started','external_result':'not_required','result':'不能抹除已完成施工','evidence_id':evidence(client,row)},409)
    login(client,'technician');row=cmd(client,row,'execution',{'source_id':links['addon']['id'],'outcome':'completed','external_result':'not_required','result':'本人核对加装实际已经完成','evidence_id':evidence(client,row)})
    assert all('net_cents' not in s for s in row['sources'])
    login(client,'service');row=cmd(client,row,'execution',{'source_id':links['insurance']['id'],'outcome':'not_started','external_result':'not_required','result':'保险未实际提交外部办理','evidence_id':evidence(client,row)})
    login(client);lines[1]['credit_cents']=500
    row=cmd(client,row,'plan',{'reason':'保留已履约加装十五元，其他未执行费用全免','lines':lines});row=applied(client,confirmed(client,approved(client,row)))
    assert sum(s['due_cents'] for s in row['sources'])==1500
    sales_action(client,addon,'receive',{'amount':'15','account_id':bank(client),'reference':'不能绕过售后余款','evidence_id':evidence(client,addon,'receipt')},409)

@pytest.mark.parametrize('tamper',['source','consent','amount','refund_source','cash','claim','self_approval'])
def test_nonempty_aftercare_restore_rejects_tampering(client,tamper):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.aftercare_backup_integrity import validate
    from app.backup_integrity import validate_sqlite
    source,account=completed_repair(client);row=applied(client,confirmed(client,approved(client,plan(client,create(client,source),100))))
    row=refund(client,row,account,100)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);assert validate(restored)=={'verified_aftercare_orders':1,'verified_aftercare_refunds':1};assert validate_sqlite(restored)['verified_files']>0
        sql={'source':'UPDATE aftercare_sources SET original_cents=original_cents+1','consent':"UPDATE aftercare_consents SET plan_digest='fake'",
            'amount':'UPDATE aftercare_adjustments SET credit_cents=credit_cents+1','refund_source':'UPDATE flow_payment_links SET original_id=NULL WHERE direction=\'out\'',
            'cash':"UPDATE cash_entries SET amount_cents=amount_cents+1 WHERE direction='out'",'claim':f"INSERT INTO aftercare_claims(source_case_id,case_id,store_id) VALUES ({source['id']},{row['id']},1)",
            'self_approval':'UPDATE aftercare_approvals SET actor_id=(SELECT requested_by FROM aftercare_orders LIMIT 1)'}
        restored.execute(sql[tamper])
        with pytest.raises(ValueError,match='售后恢复'):validate(restored)

@pytest.mark.parametrize('delivered',[True,False])
def test_actual_vehicle_return_then_original_cash_refund_finishes(client,delivered):
    import sqlite3
    from tests.test_vehicle_operations import returned_sale,act
    from tests.conftest import TEST_DIR
    from app.backup_integrity import validate_sqlite
    source,row,operation,loc=returned_sale(client,delivered)
    operation=act(client,operation,'intake',{'location_id':loc});operation=act(client,operation,'inspect',{'outcome':'pass','findings':'实际原车逐项验收通过'})
    operation=act(client,operation,'disposition',{'inspection_id':operation['inspections'][-1]['id'],'decision':'release'});operation=act(client,operation,'release',{'location_id':loc})
    row=applied(client,row);original=sales_detail(client,source)['payments'][0];row=refund(client,row,original['account_id'],10000)
    assert row['state']=='completed' and row['vehicle_return']['accepted']
    assert sales_detail(client,source)['state']==('delivered' if delivered else 'executing')
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_sqlite(db)['verified_aftercare_refunds']==1

def test_admin_cannot_approve_own_refund_and_stale_source_rejected(client):
    source,_=completed_repair(client);row=plan(client,create(client,source),100)
    cmd(client,row,'approve',{'reason':'技术管理身份不能代替复核','evidence_id':evidence(client,row,'authorization')},403)
    login(client,'manager');body=payload(client,row,{'reason':'独立复核原单和方案','evidence_id':evidence(client,row,'authorization')})
    body['source_versions'][str(source['id'])]-=1;cmd(client,row,'approve',status=409,body=body)
    row=approved(client,row);assert row['plans'][-1]['approved']
