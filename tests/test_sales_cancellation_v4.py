"""Explicit child cancellation and parent serialization for the new sales version."""
import sqlite3,uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import CashEntry,Vehicle
from app.flow_models import Case,VehicleHold,StockMove
from app.backup_integrity import validate_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_sales_quotes as quotes
from tests.test_workflow import action,evidence,detail

DOMAINS={'insurance':'insurance-orders','addon':'addon-orders','agency':'service-orders'}


@pytest.fixture(autouse=True)
def restored():
    yield
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as copy:
        source.backup(copy);validate_sqlite(copy)


def sales(c,services=True,paid=0):
    row,quote,car,customer=quotes.setup(c);row=quotes.ready(c,row,car)
    if services:
        row=quotes.propose(c,row,{**quote,'addon':True,'insurance':True,'agency':True});row=quotes.approve(c,row);row=quotes.sign(c,row)
    account=None
    if paid:row,account=quotes.pay(c,row,paid)
    row=detail(c,row)
    return row,{r['kind']:r for r in row['children'] if r['kind'] in DOMAINS},account


def cancel_child(c,child):
    url='/api/'+DOMAINS[child['kind']]+'/'+str(child['id'])
    current=c.get(url);assert current.status_code==200,current.text
    result=c.post(url+'/actions/cancel',json={'request_id':uuid.uuid4().hex,'version':current.json()['version'],'values':{'reason':'客户未执行独立服务，明确取消本服务委托'}})
    assert result.status_code==200,result.text
    assert result.json()['state']=='cancelled'
    return result.json()


def child_request(kind,row):
    common={'request_id':uuid.uuid4().hex,'source_order_id':row['id'],'source_version':row['version'],'due_date':today().isoformat(),'delivery_blocking':False,'reason':'明确新增原销售关联服务'}
    if kind!='addon':common['customer_id']=row['customer_id']
    if kind=='agency':common['subtype']='agency'
    return common


def test_all_three_explicit_child_cancellations_unlock_no_cash_sales_exit(client):
    c=client;row,children,_=sales(c)
    with SessionLocal() as db:original= db.scalar(select(Vehicle).where(Vehicle.id==row['vehicle_id']));original_value=original.purchase_cost_cents
    for kind in ('insurance','addon','agency'):
        action(c,row,'cancel_request',{'reason':'各服务还未明确取消，不应进入退订'},409)
        cancel_child(c,children[kind])
    request=uuid.uuid4().hex;old=detail(c,row)['version'];row=action(c,row,'cancel_request',{'reason':'三个独立服务均取消，申请车辆退订'},request_id=request,version=old)
    again=action(c,row,'cancel_request',{'reason':'三个独立服务均取消，申请车辆退订'},request_id=request,version=old)
    # The exact duplicate uses the original envelope, independent of today's state.
    assert again['id']==row['id']
    login(c,'manager');row=action(c,row,'cancel_approve');assert row['state']=='cancelled'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VehicleHold).where(VehicleHold.case_id==row['id']))==0
        assert db.scalar(select(Vehicle.purchase_cost_cents).where(Vehicle.id==row['vehicle_id']))==original_value
        assert db.scalar(select(func.count()).select_from(CashEntry))==db.scalar(select(func.count()).select_from(StockMove))==0
    assert all(r['state']=='cancelled' for r in detail(c,row)['children'] if r['kind'] in DOMAINS)


def test_review_and_refund_wait_reject_new_children_even_with_current_parent_version(client):
    c=client;row,children,account=sales(c,paid=5000)
    for child in children.values():cancel_child(c,child)
    row=action(c,row,'cancel_request',{'reason':'未执行服务均取消，退回实际车辆订金'})
    for kind in DOMAINS:
        current=detail(c,row);response=c.post('/api/'+DOMAINS[kind],json=child_request(kind,current))
        assert response.status_code==409 and '退订' in response.json()['detail'],response.text
    login(c,'manager');row=action(c,row,'cancel_approve');assert row['state']=='refund_pending';login(c)
    for kind in DOMAINS:
        current=detail(c,row);response=c.post('/api/'+DOMAINS[kind],json=child_request(kind,current))
        assert response.status_code==409 and '退订' in response.json()['detail'],response.text
    payment=detail(c,row)['payments'][0]
    row=action(c,row,'refund',{'original_id':payment['id'],'amount':'50.00','account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')})
    assert row['state']=='cancelled'
    for kind in DOMAINS:
        response=c.post('/api/'+DOMAINS[kind],json=child_request(kind,detail(c,row)))
        assert response.status_code==409,response.text
    with SessionLocal() as db:
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry)))==0
        assert db.scalar(select(func.count()).select_from(VehicleHold).where(VehicleHold.case_id==row['id']))==0


def test_cancel_request_stale_duplicate_and_cross_store_are_guarded(client):
    c=client;row,_,_=sales(c,services=False);before=row['version'];request=uuid.uuid4().hex
    payload={'request_id':request,'version':before,'values':{'reason':'客户明确申请取消尚未执行车辆订单'}};url='/api/flow/cases/'+str(row['id'])+'/actions/cancel_request'
    first=c.post(url,json=payload);assert first.status_code==200,first.text
    duplicate=c.post(url,json=payload);assert duplicate.status_code==200 and duplicate.json()['version']==first.json()['version']
    stale=c.post(url,json={**payload,'request_id':uuid.uuid4().hex});assert stale.status_code==409
    store=c.post('/api/stores',json={'code':'CANCEL-OTHER','name':'退订隔离店','active':True}).json()['id'];c.headers['X-Store-ID']=str(store)
    assert c.post(url,json=payload).status_code==404
    c.headers['X-Store-ID']='all';assert c.post(url,json=payload).status_code==409
    c.headers['X-Store-ID']='1';login(c,'manager');row=action(c,row,'cancel_reject',{'reason':'客户决定保留原销售，恢复原办理'})
    assert row['state'] not in {'cancel_review','refund_pending','cancelled'}
    login(c);created=c.post('/api/insurance-orders',json=child_request('insurance',detail(c,row)));assert created.status_code==201,created.text


def test_child_creation_and_parent_cancellation_compete_for_one_parent_version(client):
    c=client;row,_,_=sales(c,services=False)
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for other in clients:login(other)
        def race(i):
            if i==0:return clients[i].post('/api/insurance-orders',json=child_request('insurance',row)).status_code
            return clients[i].post('/api/flow/cases/'+str(row['id'])+'/actions/cancel_request',json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':{'reason':'与新关联服务竞争的明确退订'}}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(race,range(2)))
    assert results in ([201,409],[409,200]),results
    current=detail(c,row);live=[x for x in current['children'] if x['kind'] in DOMAINS and x['state'] not in {'cancelled','rejected'}]
    assert bool(live)==(current['state']!='cancel_review')


def test_executed_and_independently_terminated_insurance_requires_aftercare(client):
    from datetime import timedelta
    from tests import test_insurance_orders as ins
    from tests.test_repair_orders import typed
    c=client;row,_,_=sales(c,services=False)
    response=c.post('/api/insurance-orders',json=child_request('insurance',row));assert response.status_code==201,response.text
    insurer=typed(c,'insurers',{'code':'CANCEL-INS','name':'退订验证合成保险公司','license_number':'SYNTHETIC','settlement_days':0})
    child=ins.cmd(c,response.json(),'quote',dict(insurer_id=insurer['id'],insurer_version=insurer['version'],collection_mode='customer_direct',lines=[{'name':'合成险种','premium_cents':100}],expected_commission_cents=0,start_date=today().isoformat(),end_date=(today()+timedelta(days=365)).isoformat(),valid_until=today().isoformat(),terms='实际保险已独立办理，销售退订不能覆盖',reason='客户明确委托实际投保'))
    child=ins.ready(c,child);child=ins.issued(c,child);child=ins.apply_plan(c,ins.termination(c,child,0));child=ins.commission(c,child,0)
    assert child['state']=='completed' and child['summary']['terminated']
    result=action(c,row,'cancel_request',{'reason':'已实际办理保险应转原单售后'},409)
    assert '原单售后' in result['detail']


def test_independent_cancellation_approval_uses_latest_request_actor_not_creator(client):
    from app.models import User,UserStore
    from tests.conftest import PASSWORD_HASH
    c=client;row,_,_=sales(c,services=False)
    with SessionLocal() as db:
        other=User(username='cancel-other-admin',display_name='退订独立管理员',role='admin',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(other);db.flush();db.add(UserStore(user_id=other.id,store_id=1));db.commit()
    login(c,'cancel-other-admin');row=action(c,row,'cancel_request',{'reason':'另一创建者的订单由本人提出退订'})
    denied=action(c,row,'cancel_approve',{},409);assert '本人申请' in denied['detail']
    login(c,'manager');row=action(c,row,'cancel_reject',{'reason':'客户暂时保留交易，退回本次申请'})
    login(c);row=action(c,row,'cancel_request',{'reason':'重新核对后由另一经办人再次申请'})
    denied=action(c,row,'cancel_approve',{},409);assert '本人申请' in denied['detail']
    login(c,'cancel-other-admin');row=action(c,row,'cancel_approve');assert row['state']=='cancelled'
