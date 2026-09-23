"""Versioned flow, failed PDI and cancellation conservation regressions."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.db import SessionLocal
from app.models import User, CashEntry
from app.flow_models import Case, Task, StockMove, Item, Member, MemberEntry, PaymentLink, FlowEvent
from app.flow_specs import flow_spec
from app import flow_engine as eng
from app.tenancy import set_scope
from tests.conftest import login
from tests.test_workflow import create, action, detail, master, evidence, order, account, seed_car, approved_doc
from tests.test_workflow_extended import member, repair, add_user


def ready_except_pdi(c):
    row=action(c,order(c,amount='100'),'approve')
    row=action(c,row,'allocate',{'vehicle_id':seed_car()})
    signed=approved_doc(c,row,'contract')
    row=action(c,row,'sign',{'evidence_id':evidence(c,row,'signed_contract',signed)})
    return action(c,row,'receive',{'amount':'100','account_id':account(c),'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row)})


def inspect(c,row,outcome='不合格',key='inspect',**kwargs):
    return action(c,row,key,{'outcome':outcome,'result':'检查结论及发现','evidence_id':evidence(c,row,'inspection')},**kwargs)


def purchase(c):
    item=master(c,'items',{'sku':uuid.uuid4().hex,'name':'取消采购物资','unit':'件','reorder':'0','active':True})
    row=create(c,'purchase',{'item_id':item['id'],'quantity':'2','unit_cost':'12.34','supplier':'测试供应商'})
    return action(c,row,'approve'),item


def post(c,row,key,values,version=None,request_id=None):
    return c.post(f"/api/flow/cases/{row['id']}/actions/{key}",json={
        'version':row['version'] if version is None else version,'request_id':request_id or uuid.uuid4().hex,'values':values})


def test_new_catalogue_v2_and_client_cannot_select_version(client):
    assert client.get('/api/flow/catalog').json()['flow_version']==2
    row=order(client)
    assert row['flow_version']==2
    assert post(client,row,'approve',{'flow_version':1}).status_code==422
    assert client.post('/api/flow/cases',json={'kind':'order','flow_version':1,'request_id':uuid.uuid4().hex,'values':{}}).status_code==422
    assert 'outcome' not in {f['key'] for a in flow_spec('order',1)['actions'] if a.key=='inspect' for f in a.fields}
    assert 'outcome' in {f['key'] for a in flow_spec('order',2)['actions'] if a.key=='inspect' for f in a.fields}


def test_existing_v1_case_keeps_history_version_but_blocks_unsafe_delivery(client):
    row=order(client,addon=True)
    with SessionLocal() as db:
        persisted=db.get(Case,row['id']);persisted.flow_version=1;db.commit()
    row=action(client,row,'approve');row=action(client,row,'allocate',{'vehicle_id':seed_car()})
    assert all(c['flow_version']==1 for c in detail(client,row)['children'])
    refused=action(client,row,'inspect',{'result':'原流程文本检查结论','evidence_id':evidence(client,row)},409)
    assert '评审流程升级' in refused['detail']
    assert next(t for t in detail(client,row)['tasks'] if t['key']=='inspect')['status']=='open'
    assert 'inspection_status' not in row['data']
    assert post(client,row,'rectify',{}).status_code==404
    assert '评审流程升级' in action(client,row,'dispatch',{'evidence_id':evidence(client,row)},409)['detail']
    assert '评审流程升级' in action(client,row,'deliver',{'evidence_id':evidence(client,row)},409)['detail']


def test_unknown_flow_version_fails_closed(client):
    row=order(client)
    with SessionLocal() as db:
        persisted=db.get(Case,row['id']);persisted.flow_version=999;db.commit();version=persisted.version
    response=post(client,row,'approve',{},version)
    assert response.status_code==409 and '流程版本' in response.json()['detail']
    with SessionLocal() as db:
        assert db.get(Case,row['id']).state=='reserved'
        assert not db.scalar(select(FlowEvent.id).where(FlowEvent.case_id==row['id'],FlowEvent.action=='approve'))


def test_pdi_failure_rectification_reinspection_blocks_dispatch(client):
    row=ready_except_pdi(client)
    row=inspect(client,row)
    assert row['data']['inspection_status']=='failed'
    assert next(t for t in detail(client,row)['tasks'] if t['key']=='rectify')['status']=='open'
    action(client,row,'dispatch',{'evidence_id':evidence(client,row)},409)
    inspect(client,row,'合格','reinspect',status=409)
    row=action(client,row,'rectify',{'result':'已处理全部缺陷','evidence_id':evidence(client,row)})
    action(client,row,'dispatch',{'evidence_id':evidence(client,row)},409)
    row=inspect(client,row,'不合格','reinspect')
    assert row['data']['inspection']['round']==2
    row=action(client,row,'rectify',{'result':'处理复检发现的问题','evidence_id':evidence(client,row)})
    row=inspect(client,row,'合格','reinspect')
    assert row['data']['inspection']['round']==3
    row=action(client,row,'dispatch',{'evidence_id':evidence(client,row)})
    assert row['data']['dispatched_at']
    assert all(not t['blocked'] for t in detail(client,row)['tasks'] if t['status']=='done')
    with SessionLocal() as db:
        events=list(db.scalars(select(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action.in_(['inspect','reinspect']))))
        assert [e.detail['outcome'] for e in events]==['不合格','不合格','合格']


def test_pdi_requires_structured_result_and_inspection_file(client):
    row=action(client,action(client,order(client),'approve'),'allocate',{'vehicle_id':seed_car()})
    fid=evidence(client,row,'inspection')
    action(client,row,'inspect',{'result':'文字合格不能代替结构化结果','evidence_id':fid},422)
    action(client,row,'inspect',{'outcome':'已检查','result':'错误结果','evidence_id':fid},422)
    action(client,row,'inspect',{'outcome':'合格','result':'无检测类凭据','evidence_id':evidence(client,row)},422)
    assert 'inspection' not in detail(client,row)['data']


def test_pdi_employee_permissions_duplicate_stale_and_cross_store(client):
    row=action(client,action(client,order(client),'approve'),'allocate',{'vehicle_id':seed_car()})
    fid=evidence(client,row,'inspection');row=detail(client,row)
    values={'outcome':'不合格','result':'有外观缺陷','evidence_id':fid}
    login(client,'inventory');assert post(client,row,'inspect',values).status_code==403
    login(client,'service');key=uuid.uuid4().hex
    assert post(client,row,'inspect',values,request_id=key).status_code==200
    assert post(client,row,'inspect',values,request_id=key).status_code==200
    assert post(client,row,'inspect',values).status_code==409
    login(client)
    store=client.post('/api/stores',json={'code':'PDI-OTHER','name':'检查隔离门店','active':True}).json()['id']
    client.headers['X-Store-ID']=str(store)
    assert post(client,row,'rectify',{'result':'跨店处理','evidence_id':fid}).status_code==404
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='inspect'))==1


def test_pdi_rectification_cannot_rewrite_passed_result(client):
    row=action(client,action(client,order(client),'approve'),'allocate',{'vehicle_id':seed_car()})
    row=inspect(client,row,'合格')
    action(client,row,'rectify',{'result':'试图重新打开','evidence_id':evidence(client,row)},409)
    inspect(client,row,'不合格','reinspect',status=409)
    assert detail(client,row)['data']['inspection']['outcome']=='合格'


def test_purchase_cancel_closes_tasks_without_postings(client):
    row,item=purchase(client);version=row['version'];key=uuid.uuid4().hex
    row=action(client,row,'cancel',{'reason':'供应商无法供货'},request_id=key,version=version)
    assert row['state']=='cancelled' and row['completed_date']
    assert post(client,row,'cancel',{'reason':'供应商无法供货'},version,key).status_code==200
    assert post(client,row,'cancel',{'reason':'重复取消'},version).status_code==409
    action(client,row,'stock_in',{'evidence_id':evidence(client,row)},409)
    with SessionLocal() as db:
        stored=db.get(Item,item['id']);assert stored.quantity_milli==0 and stored.inventory_value_cents==0
        assert not db.scalar(select(StockMove.id).where(StockMove.case_id==row['id']))
        assert not db.scalar(select(Task.id).where(Task.case_id==row['id'],Task.status=='open'))


def test_purchase_cannot_cancel_after_receipt_and_unauthorized(client):
    row,item=purchase(client)
    login(client,'inventory');assert post(client,row,'cancel',{'reason':'不具备主管权限'}).status_code==403
    row=action(client,row,'stock_in',{'evidence_id':evidence(client,row)})
    login(client);assert post(client,row,'cancel',{'reason':'实物已经到货'}).status_code==409
    with SessionLocal() as db:
        assert db.get(Item,item['id']).inventory_value_cents==2468


@pytest.mark.parametrize('kind',['purchase','member_refund'])
def test_new_cancel_actions_are_tenant_scoped(client,kind):
    if kind=='purchase':row,_=purchase(client)
    else:
        wallet,_=member(client)
        row=action(client,create(client,kind,{'member_id':wallet['id'],'amount':'100','reason':'申请退款'}),'approve')
    other=client.post('/api/stores',json={'code':'CANCEL-OTHER','name':'取消隔离门店','active':True}).json()['id']
    client.headers['X-Store-ID']=str(other)
    assert post(client,row,'cancel',{'reason':'跨店取消'}).status_code==404


def test_member_refund_cancel_releases_hold_without_cash_or_ledger(client):
    wallet,aid=member(client)
    row=action(client,create(client,'member_refund',{'member_id':wallet['id'],'amount':'950','reason':'客户要求退款'}),'approve')
    job=repair(client)
    action(client,job,'apply_balance',{'member_id':wallet['id'],'amount':'100','evidence_id':evidence(client,job)},409)
    with SessionLocal() as db:
        cash_count=db.scalar(select(func.count()).select_from(CashEntry))
        ledger_count=db.scalar(select(func.count()).select_from(MemberEntry))
    old=row['version'];key=uuid.uuid4().hex
    login(client,'finance')
    row=action(client,row,'cancel',{'reason':'客户撤回退款'},request_id=key,version=old)
    assert row['state']=='cancelled'
    assert post(client,row,'cancel',{'reason':'客户撤回退款'},old,key).status_code==200
    assert post(client,row,'cancel',{'reason':'再次撤销'},old).status_code==409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==cash_count
        assert db.scalar(select(func.count()).select_from(MemberEntry))==ledger_count
        assert db.get(Member,wallet['id']).balance_cents==100000
        assert eng.member_available(db,db.get(Member,wallet['id']))==100000
    action(client,job,'apply_balance',{'member_id':wallet['id'],'amount':'100','evidence_id':evidence(client,job)})
    with SessionLocal() as db:assert db.get(Member,wallet['id']).balance_cents==90000


def test_member_refund_paid_cannot_cancel_and_staff_cannot_cancel(client):
    wallet,aid=member(client)
    row=action(client,create(client,'member_refund',{'member_id':wallet['id'],'amount':'500','reason':'客户申请'}),'approve')
    login(client,'service');assert post(client,row,'cancel',{'reason':'无退款撤销权限'}).status_code==403
    login(client)
    row=action(client,row,'member_refund_pay',{'account_id':aid,'reference':'refund-final','evidence_id':evidence(client,row)})
    assert post(client,row,'cancel',{'reason':'退款已经真实发生'}).status_code==409
    with SessionLocal() as db:
        assert db.get(Member,wallet['id']).balance_cents==50000
        assert db.scalar(select(func.count()).select_from(MemberEntry).where(MemberEntry.case_id==row['id'],MemberEntry.purpose=='refund'))==1


def test_member_refund_cancel_releases_only_its_hold_even_if_member_disabled(client):
    wallet,_=member(client)
    first=action(client,create(client,'member_refund',{'member_id':wallet['id'],'amount':'400','reason':'首笔退款申请'}),'approve')
    second=action(client,create(client,'member_refund',{'member_id':wallet['id'],'amount':'500','reason':'第二笔退款申请'}),'approve')
    current=client.get('/api/flow/master/members').json()['items'][0]
    response=client.put(f"/api/flow/master/members/{wallet['id']}",json={'version':current['version'],
        'values':{'customer_id':current['customer_id'],'active':False}})
    assert response.status_code==200,response.text
    action(client,first,'cancel',{'reason':'撤回首笔未支付退款'})
    with SessionLocal() as db:
        persisted=db.get(Member,wallet['id'])
        assert persisted.balance_cents==100000 and eng.member_available(db,persisted)==50000
        assert db.get(Case,second['id']).state=='refund_pending'


@pytest.mark.parametrize('kind',['purchase','member_refund'])
def test_v1_catalogue_does_not_offer_v2_cancellation(kind):
    assert 'cancel' not in {a.key for a in flow_spec(kind,1)['actions']}
    assert 'cancel' in {a.key for a in flow_spec(kind,2)['actions']}


@pytest.mark.parametrize('cancel_first',[True,False])
@pytest.mark.parametrize('kind',['purchase','member_refund'])
def test_competing_cancel_and_posting_are_atomic(client,kind,cancel_first):
    if kind=='purchase':
        row,item=purchase(client);posting='stock_in';values={'evidence_id':evidence(client,row)}
    else:
        wallet,aid=member(client)
        row=action(client,create(client,'member_refund',{'member_id':wallet['id'],'amount':'500','reason':'退款申请'}),'approve')
        posting='member_refund_pay';values={'account_id':aid,'reference':'competing-refund','evidence_id':evidence(client,row)}
    first_action,first_values=('cancel',{'reason':'取消未执行申请'}) if cancel_first else (posting,values)
    second_action,second_values=(posting,values) if cancel_first else ('cancel',{'reason':'竞争中的取消'})
    with SessionLocal() as first,SessionLocal() as second:
        set_scope(first,[1],1);set_scope(second,[1],1)
        one=first.scalar(select(Case).where(Case.id==row['id']))
        two=second.scalar(select(Case).where(Case.id==row['id']))
        user1=first.scalar(select(User).where(User.username=='admin'))
        user2=second.scalar(select(User).where(User.username=='admin'))
        eng.process_action(first,user1,one,first_action,first_values,one.version);first.commit()
        # Both sessions originally observed the same version. SQLite rejects the
        # older WAL snapshot; other supported DBs reject the optimistic version.
        with pytest.raises((StaleDataError,OperationalError,HTTPException)):
            eng.process_action(second,user2,two,second_action,second_values,two.version);second.commit()
        second.rollback()
    with SessionLocal() as db:
        assert db.get(Case,row['id']).state==('cancelled' if cancel_first else 'completed')
        if kind=='purchase':
            assert db.get(Item,item['id']).quantity_milli==(0 if cancel_first else 2000)
            assert db.get(Item,item['id']).inventory_value_cents==(0 if cancel_first else 2468)
            assert db.scalar(select(func.count()).select_from(StockMove).where(StockMove.case_id==row['id']))==(0 if cancel_first else 1)
        else:
            assert db.get(Member,wallet['id']).balance_cents==(100000 if cancel_first else 50000)
            assert db.scalar(select(func.count()).select_from(PaymentLink).where(PaymentLink.case_id==row['id']))==(0 if cancel_first else 1)
            assert eng.member_available(db,db.get(Member,wallet['id']))==db.get(Member,wallet['id']).balance_cents
