"""Production-router tests on an independent synthetic database."""
import sqlite3,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,Base,engine,today
from app.models import CashEntry,User
from app.flow_models import Item,StockMove,Task
from app.tenancy import set_scope
from tests.conftest import login,TEST_DIR
from tests import test_transfer_exception_workflow as old
from app.transfer_goods_recovery_math import allocation


def original(c):
    data=old.initialize(c);row=old.new(c,data);old.observed(c,data,row);old.planned(c,data,row);old.approved(c,data,row);old.posted(c,data,row)
    from app.transfer_exception_models import TransferLossPosting
    with SessionLocal() as db:loss=db.scalar(select(TransferLossPosting.id))
    data['loss_id']=loss;data['exception']=row
    return data


def current(c,row):
    response=c.get('/api/transfer-goods-recoveries/'+str(row['id']));assert response.status_code==200,response.text;return response.json()


def found(c,data,quantity=1000,store=1,status=201,request=None):
    old.switch(c,store);login(c,'inventory' if store==1 else 'inventory2')
    before=old.get(c,{'id':data['transfer_id']})
    body=dict(request_id=request or uuid.uuid4().hex,transfer_id=before['id'],loss_id=data['loss_id'],version=before['version'],case_version=before['case_version'],
        quantity_milli=quantity,result='本人实际找到并暂时保管原批物资',evidence_id=data['outproof'] if store==1 else data['inproof'],due_date=today().isoformat(),confirmed=True)
    response=c.post('/api/transfer-goods-recoveries',json=body);assert response.status_code==status,response.text;return response.json()


def command(c,row,action,values,status=200,before=None,request=None):
    before=before or current(c,row)
    body=dict(request_id=request or uuid.uuid4().hex,version=before['version'],transfer_version=before['transfer_version'],case_version=before['case_version'],values=values)
    response=c.post(f"/api/transfer-goods-recoveries/{row['id']}/actions/{action}",json=body)
    assert response.status_code==status,response.text;return response.json()


def physical(c,row,action,passed=None,**kw):
    latest=current(c,row);proof=old.proof(c,latest['case_id'])
    values=dict(evidence_id=proof,result='本人核对原实物与本店实际动作',confirmed=True)
    if passed is not None:values['passed']=passed
    return command(c,row,action,values,**kw)


def match(c,data,row):
    sid=2 if row['found_store_id']==1 else 1;old.switch(c,sid);login(c,'inventory2' if sid==2 else 'inventory')
    return physical(c,row,'match')


def plan(c,data,row):
    old.switch(c,1);login(c,'finance');proof=old.proof(c,data['source'],True)
    return command(c,row,'plan',dict(evidence_id=proof,reason='按原损失原成本及累计尾差核对，不重新估价'))


def approve(c,data,row):
    for sid,who in ((1,'manager'),(2,'manager2')):
        old.switch(c,sid);login(c,who);latest=current(c,row);proof=old.proof(c,latest['case_id'],True)
        row=command(c,row,'approve',dict(plan_id=latest['plans'][-1]['id'],evidence_id=proof,reason='本人独立复核本版实际找到、复验和原承担'))
    return row


def ready(c,data,row,usable=True):
    match(c,data,row);old.switch(c,row['found_store_id']);login(c,'inventory' if row['found_store_id']==1 else 'inventory2')
    physical(c,row,'inspect',usable)
    if row['found_store_id']==2 and usable:
        physical(c,row,'ship');old.switch(c,1);login(c,'inventory');physical(c,row,'receive',True)
    plan(c,data,row);return approve(c,data,row)


def restore(c,data,row):
    old.switch(c,1);login(c,'inventory');return command(c,row,'restore',dict(evidence_id=data['outproof'],confirmed=True))


def test_original_cost_and_internal_burden_are_appended_without_editing_loss(client):
    from app.transfer_goods_recovery_models import GoodsPosting,GoodsSettlement
    from app.transfer_goods_recovery_service import authority
    from app.transfer_exception_models import TransferLossPosting
    data=original(client);row=found(client,data);ready(client,data,row);row=restore(client,data,row)
    assert row['status']=='closed'
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='inventory'))
        with authority(db,user):
            posting=db.scalar(select(GoodsPosting));assert (posting.found_quantity_milli,posting.restored_quantity_milli,posting.value_cents)==(1000,1000,33)
            assert db.scalar(select(GoodsSettlement.amount_cents))==-16
        assert db.scalar(select(Item.quantity_milli).where(Item.id==data['item']))==1000
        assert db.scalar(select(Item.inventory_value_cents).where(Item.id==data['item']))==33
        assert db.scalar(select(TransferLossPosting.value_cents))==100
        assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_found_at_destination_requires_actual_return_and_source_quality(client):
    data=original(client);row=found(client,data,store=2);match(client,data,row)
    old.switch(client,2);login(client,'inventory2');physical(client,row,'inspect',True)
    old.switch(client,1);login(client,'finance');command(client,row,'plan',dict(evidence_id=old.proof(client,data['source'],True),reason='不能凭乙店说已找到就恢复原店库存'),409)
    old.switch(client,2);login(client,'inventory2');physical(client,row,'ship')
    physical(client,row,'cancel',status=409)
    old.switch(client,1);login(client,'inventory');physical(client,row,'receive',False)
    plan(client,data,row);approve(client,data,row)
    old.switch(client,1);login(client,'inventory');command(client,row,'restore',dict(evidence_id=data['outproof'],confirmed=True),409)
    physical(client,row,'dispose');login(client,'finance')
    row=command(client,row,'finish_bad',dict(evidence_id=old.proof(client,data['source'],True),confirmed=True))
    assert row['status']=='closed'
    with SessionLocal() as db:assert db.scalar(select(Item.quantity_milli).where(Item.id==data['item']))==0


def test_bad_found_at_destination_needs_its_actual_disposal_and_no_reverse_value(client):
    data=original(client);row=found(client,data,store=2);ready(client,data,row,False)
    old.switch(client,1);login(client,'finance');values=dict(evidence_id=old.proof(client,data['source'],True),confirmed=True)
    command(client,row,'finish_bad',values,409)
    old.switch(client,2);login(client,'inventory2');physical(client,row,'dispose')
    old.switch(client,1);login(client,'finance');row=command(client,row,'finish_bad',values)
    assert row['status']=='closed' and row['remaining_burden_cents']==50


def test_actual_find_cancel_duplicate_stale_crossstore_and_independent_review(client):
    data=original(client);row=found(client,data);before=current(client,row);request=uuid.uuid4().hex
    values=dict(evidence_id=data['outproof'],result='核对发现本次原物资关联录错，保留观察撤回调查',confirmed=True)
    cancelled=command(client,row,'cancel',values,before=before,request=request)
    assert command(client,row,'cancel',values,before=before,request=request)==cancelled
    command(client,row,'cancel',values,409,before=before)
    row=found(client,data);match(client,data,row);old.switch(client,1);login(client,'inventory');physical(client,row,'inspect',True);plan(client,data,row)
    old.switch(client,3);login(client,'admin');assert client.get(f"/api/transfer-goods-recoveries/{row['id']}").status_code==404
    old.switch(client,1);login(client,'finance');latest=current(client,row)
    command(client,row,'approve',dict(plan_id=latest['plans'][-1]['id'],evidence_id=old.proof(client,data['source'],True),reason='不能由方案财务自己复核'),403)
    login(client,'inventory');assert all(not {'value_cents','source_reverse_cents','destination_reverse_cents','reason'}&set(p) for p in current(client,row)['plans'])
    command(client,row,'inspect',dict(passed='true',evidence_id=data['outproof'],result='字符串不是明确布尔实物判断',confirmed=True),422)


def test_partial_restoration_final_tail_and_found_quantity_cannot_repeat(client):
    from app.transfer_goods_recovery_models import GoodsPosting
    from app.transfer_goods_recovery_service import authority
    data=original(client)
    for qty in (333,667,2000):
        row=found(client,data,qty);ready(client,data,row);restore(client,data,row)
    found(client,data,1,status=409)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        with authority(db,user):
            ps=list(db.scalars(select(GoodsPosting).order_by(GoodsPosting.id)))
            assert [p.value_cents for p in ps]==[11,22,67]
            assert sum(p.destination_reverse_cents for p in ps)==50


def test_found_goods_does_not_assume_external_refund_and_has_its_own_exit(client):
    from app.transfer_exception_models import TransferLossPosting
    data,ex,carrier,account,fp=old.recoverable(client);claim=old.approve_claim(client,ex,old.create_claim(client,ex,carrier,fp),fp)
    claim_result=old.recovery(client,ex,'recovery_receive',claim,amount_cents=40,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    with SessionLocal() as db:data['loss_id']=db.scalar(select(TransferLossPosting.id))
    row=found(client,data);ready(client,data,row);row=restore(client,data,row);assert row['status']=='financial'
    login(client,'finance');latest=current(client,row);claim=latest['claims'][0]
    def financial(action,extra,status=200):
        claim=current(client,row)['claims'][0]
        return command(client,row,action,dict(claim_id=claim['id'],claim_version=claim['version'],evidence_id=fp,**extra),status)
    incoming=next(p for p in claim['payments'] if p['direction']=='in')
    refund=dict(original_id=incoming['id'],amount_cents=10,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True)
    financial('refund',refund,409)
    financial('terms',dict(target_cents=30,due_date=today().isoformat(),reason='原承运方实际确认找到后累计仅30分，此为其明确原件'))
    login(client,'manager');claim=current(client,row)['claims'][0]
    financial('terms_approve',dict(plan_id=claim['pending_plan_id'],reason='本人独立核对原承运方确认的新累计赔付条件'))
    assert current(client,row)['status']=='financial'
    login(client,'finance');closed=financial('refund',refund);assert closed['status']=='closed'
    with SessionLocal() as db:
        cash=list(db.scalars(select(CashEntry)))
        assert [(c.direction,c.amount_cents) for c in cash]==[('in',40),('out',10)]
        assert db.scalar(select(Item.inventory_value_cents).where(Item.id==data['item']))==33
    from app.transfer_goods_recovery_integrity import validate_transfer_goods_recovery_sqlite
    from app.transfer_exception_integrity import validate_transfer_exceptions_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        assert validate_transfer_goods_recovery_sqlite(db)['found_goods_postings']==1
        assert validate_transfer_exceptions_sqlite(db)['transport_recoveries']==1


def test_concurrent_found_batches_share_original_parent_version(client):
    from fastapi.testclient import TestClient
    from app.main import app
    data=original(client);old.switch(client,1);login(client,'inventory');before=old.get(client,{'id':data['transfer_id']})
    callers=[TestClient(app),TestClient(app)]
    for c in callers:login(c,'inventory')
    body=dict(transfer_id=before['id'],loss_id=data['loss_id'],version=before['version'],case_version=before['case_version'],quantity_milli=2000,
        result='本人实际找到本批原物资，两设备不能占两次',evidence_id=data['outproof'],due_date=today().isoformat(),confirmed=True)
    try:
        def perform(i):return callers[i].post('/api/transfer-goods-recoveries',json=dict(request_id=uuid.uuid4().hex,**body)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(perform,range(2)))==[201,409]
    finally:
        for c in callers:c.close()


def test_zero_value_and_bad_goods_still_conserve_physical_quantities():
    assert allocation(3000,0,0,0,0,0,0,333,True)['restored_quantity_milli']==333
    assert allocation(3000,0,0,0,0,0,0,333,True)['value_cents']==0
    assert allocation(3000,100,50,500,0,0,0,2500,True)['value_cents']==83
    with pytest.raises(ValueError):allocation(3000,100,50,3000,3000,100,50,1,True)
    with pytest.raises(ValueError):allocation(3000,100,50,1000,1000,34,17,1,True)


def test_nonempty_restore_preserves_prior_loss_and_rejects_recomputed_recovery_facts(client):
    from app.transfer_goods_recovery_integrity import validate_transfer_goods_recovery_sqlite
    from app.transfer_exception_integrity import validate_transfer_exceptions_sqlite
    data=original(client);row=found(client,data);ready(client,data,row);restore(client,data,row)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);assert validate_transfer_exceptions_sqlite(db)['transport_losses']==1
        assert validate_transfer_goods_recovery_sqlite(db)=={'found_goods':1,'found_goods_postings':1}
        db.execute('UPDATE transfer_goods_postings SET value_cents=value_cents+1,source_reverse_cents=source_reverse_cents+1')
        with pytest.raises(ValueError,match='批准不符'):validate_transfer_goods_recovery_sqlite(db)
        db.rollback()
        db.execute('UPDATE transfer_goods_settlements SET original_id=original_id+999')
        with pytest.raises(ValueError,match='反向往来'):validate_transfer_goods_recovery_sqlite(db)
        db.rollback()
        db.execute('UPDATE transfer_goods_reviews SET actor_id=(SELECT requested_by FROM transfer_goods_recoveries LIMIT 1) WHERE store_id=1')
        with pytest.raises(ValueError,match='不独立'):validate_transfer_goods_recovery_sqlite(db)


def test_already_settled_original_liability_gets_new_reverse_entries_not_fake_cash(client):
    from tests import test_reconciliation as monthly
    from app.transfer_goods_recovery_integrity import validate_transfer_goods_recovery_sqlite
    data=original(client);old.switch(client,2);login(client,'finance')
    origin=next(o for o in client.get('/api/reconciliation/origins').json()['items'] if o['origin_kind']=='material_loss')
    clearing=monthly.clear(client,origin);monthly.cmd(client,clearing,'pay',monthly.payvalues(client,clearing),kind='clearing')
    old.switch(client,1);login(client,'finance');monthly.cmd(client,clearing,'receive',monthly.payvalues(client,clearing),kind='clearing')
    with SessionLocal() as db:before=[(c.id,c.direction,c.amount_cents) for c in db.scalars(select(CashEntry))]
    row=found(client,data);ready(client,data,row);restore(client,data,row)
    with SessionLocal() as db:assert [(c.id,c.direction,c.amount_cents) for c in db.scalars(select(CashEntry))]==before
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        assert validate_transfer_goods_recovery_sqlite(db)['found_goods_postings']==1
        assert db.execute('SELECT settled_cents FROM interstore_clearing_buckets').fetchone()[0]==50
        assert sorted(db.execute('SELECT store_id,amount_cents FROM transfer_goods_settlements').fetchall())==[(1,-16),(2,16)]


def test_rejected_goods_plan_is_append_only_and_local_financial_proof_is_required(client):
    data=original(client);row=found(client,data);match(client,data,row);old.switch(client,1);login(client,'inventory');physical(client,row,'inspect',True);plan(client,data,row)
    login(client,'manager');latest=current(client,row);fp=old.proof(client,data['source'],True)
    command(client,row,'reject',dict(plan_id=latest['plans'][-1]['id'],evidence_id=fp,reason='原复验记录尚需补充，由本人原复验者追加'),200)
    login(client,'inventory');physical(client,row,'inspect',False);latest=plan(client,data,row)
    assert [p['revision'] for p in latest['plans']]==[1,2]
    login(client,'manager');command(client,row,'approve',dict(plan_id=latest['plans'][0]['id'],evidence_id=fp,reason='旧方案不能拿来批准当前坏件处理'),409)
    old.switch(client,2);login(client,'manager2');command(client,row,'approve',dict(plan_id=latest['plans'][1]['id'],evidence_id=fp,reason='不能借用另一门店财务原件'),422)


def test_zero_cost_original_loss_supports_actual_found_stock(client):
    # Explicitly configure a zero-cost synthetic source before actual dispatch;
    # never change a recorded loss or movement after it has been posted.
    from unittest.mock import patch
    real=old.seed
    def zero_seed():
        a,b=real()
        with SessionLocal() as db:
            item=db.scalar(select(Item).where(Item.id==a));item.inventory_value_cents=0;item.unit_cost_cents=0;db.commit()
        return a,b
    with patch.object(old,'seed',zero_seed):data=original(client)
    row=found(client,data,3000);ready(client,data,row);assert restore(client,data,row)['status']=='closed'
    with SessionLocal() as db:
        item=db.scalar(select(Item).where(Item.id==data['item']));assert (item.quantity_milli,item.inventory_value_cents)==(3000,0)


def test_draft_hooks_pause_dependencies_but_not_actual_refund_resolution(client):
    from app import transfer_goods_recovery_service as s
    from app.transfer_exception_models import TransferException
    data=original(client)
    old.switch(client,1);login(client,'inventory')
    origins=client.get(f"/api/transfer-goods-recoveries/origins/{data['transfer_id']}").json()
    assert origins['items'][0]['available_quantity_milli']==3000 and 'original_value_cents' not in origins['items'][0]
    row=found(client,data)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        with s.authority(db,user):
            parent=s.transfer.get_transfer(db,data['transfer_id'],1)
            for action in ('receive','recovery_create','recovery_receive','clearing_pay'):
                with pytest.raises(HTTPException) as error:s.guard_original_action(db,user,parent,action)
                assert error.value.status_code==409
            s.guard_original_action(db,user,parent,'clearing_receive')
            assert '_found_original_action' not in db.info
    ready(client,data,row);restore(client,data,row)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        with s.authority(db,user):
            parent=s.transfer.get_transfer(db,data['transfer_id'],1);ex=db.scalar(select(TransferException))
            assert s.effective_burden(db,user,ex,parent,1)==33
            s.guard_original_action(db,user,parent,'recovery_create')


def test_effective_zero_burden_still_allows_two_original_compensations_to_reduce_then_refund(client):
    from app import transfer_goods_recovery_service as s,transfer_exception_recovery as original_finance
    from app.transfer_exception_models import TransferLossPosting
    from app.transfer_goods_recovery_integrity import validate_transfer_goods_recovery_sqlite
    data,ex,carrier,account,fp=old.recoverable(client)
    for amount in (25,25):
        claim=old.approve_claim(client,ex,old.create_claim(client,ex,carrier,fp,amount),fp)
        old.recovery(client,ex,'recovery_receive',claim,amount_cents=amount,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    with SessionLocal() as db:data['loss_id']=db.scalar(select(TransferLossPosting.id))
    row=found(client,data,3000);ready(client,data,row);assert restore(client,data,row)['status']=='financial'
    # Uses the production remaining-burden and original-capacity hooks.
    claim_ids=[];login(client,'finance')
    for claim in current(client,row)['claims']:
        claim_ids.append(claim['id'])
        command(client,row,'terms',dict(claim_id=claim['id'],claim_version=claim['version'],target_cents=0,due_date=today().isoformat(),evidence_id=fp,reason='该原往来方已实际确认本条25分全部退回，另一条分别核对'))
        login(client,'manager');claim=next(c for c in current(client,row)['claims'] if c['id']==claim['id'])
        if len(claim_ids)==1:
            command(client,row,'terms_reject',dict(claim_id=claim['id'],claim_version=claim['version'],plan_id=claim['pending_plan_id'],evidence_id=fp,reason='原往来方条件原件需补核，另一条未退现金不能阻断拒绝'))
            login(client,'finance');claim=next(c for c in current(client,row)['claims'] if c['id']==claim['id'])
            command(client,row,'terms',dict(claim_id=claim['id'],claim_version=claim['version'],target_cents=0,due_date=today().isoformat(),evidence_id=fp,reason='已补充原往来方明确全部退回条件，保留前版拒绝'))
            login(client,'manager');claim=next(c for c in current(client,row)['claims'] if c['id']==claim['id'])
        command(client,row,'terms_approve',dict(claim_id=claim['id'],claim_version=claim['version'],plan_id=claim['pending_plan_id'],evidence_id=fp,reason='本人独立确认该原条目减为0，其它原赔款不视为已退'))
        login(client,'finance')
    assert current(client,row)['status']=='financial'
    # A new/increased target has no delegated exemption and remains refused.
    first=next(c for c in current(client,row)['claims'] if c['id']==claim_ids[0])
    command(client,row,'terms',dict(claim_id=first['id'],claim_version=first['version'],target_cents=1,due_date=today().isoformat(),evidence_id=fp,reason='剩余承担为零不能又增加新赔款'),409)
    for claim_id in claim_ids:
        claim=next(c for c in current(client,row)['claims'] if c['id']==claim_id);incoming=next(p for p in claim['payments'] if p['direction']=='in')
        command(client,row,'refund',dict(claim_id=claim['id'],claim_version=claim['version'],original_id=incoming['id'],amount_cents=25,
            account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=fp,confirmed=True))
    assert current(client,row)['status']=='closed'
    with SessionLocal() as db:assert [(c.direction,c.amount_cents) for c in db.scalars(select(CashEntry).order_by(CashEntry.id))]==[('in',25),('in',25),('out',25),('out',25)]
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_transfer_goods_recovery_sqlite(db)['found_goods_postings']==1


def test_production_original_recovery_and_transfer_pause_until_found_cancel(client):
    data=original(client);row=found(client,data)
    local=old.get(client,{'id':data['transfer_id']});assert local['active_goods_recovery_id']==row['id'] and local['actions']==[]
    login(client,'finance');original_row=old.current(client,data['exception'])
    assert original_row['active_goods_recovery_id']==row['id'] and original_row['actions']==[]
    values=dict(evidence_id=old.proof(client,data['source'],True),counterparty_kind='carrier',counterparty_id=1,target_cents=0,due_date=today().isoformat(),reason='当前找到原物资在办，不能新建原追偿')
    old.action(client,data['exception'],'recovery_create',values,409)
    login(client,'inventory');physical(client,row,'cancel')
    assert old.get(client,{'id':data['transfer_id']})['active_goods_recovery_id'] is None
    login(client,'finance');assert 'recovery_create' in old.current(client,data['exception'])['actions']


def test_found_analytics_exact_scope_original_cost_and_no_duplicate_cash(client):
    from app.transfer_goods_recovery_analytics import analytics_rows
    from app.tenancy import project_user
    data=original(client);row=found(client,data)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
        before=analytics_rows(db,user);assert len(before['pending'])==1 and before['restored']==[]
    ready(client,data,row);restore(client,data,row)
    with SessionLocal() as db:
        user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
        set_scope(db,[1],1);a=analytics_rows(db,user)
        assert sum(r['amount_cents'] for r in a['restored'])==33 and sum(r['amount_cents'] for r in a['burden_reversals'])==-17
        assert a['clearing'][0]['amount_cents']==-16 and a['clearing'][0]['case_id']==data['source'] and a['pending']==[]
        set_scope(db,[2],2);b=analytics_rows(db,user)
        assert b['restored']==[] and sum(r['amount_cents'] for r in b['burden_reversals'])==-16 and b['clearing'][0]['case_id']==data['destination']
        set_scope(db,[1,2],None);both=analytics_rows(db,user)
        assert sum(r['amount_cents'] for r in both['restored'])==33 and sum(r['amount_cents'] for r in both['burden_reversals'])==-33
        assert sum(r['amount_cents'] for r in both['clearing'])==0 and all(r['case_id'] is None and r['route'] is None for values in both.values() for r in values)
        user=project_user(user,'inventory')
        with pytest.raises(HTTPException) as error:analytics_rows(db,user)
        assert error.value.status_code==403


def test_competing_partial_original_refunds_replay_once_and_release_after_tail(client):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.transfer_exception_models import TransferLossPosting
    data,ex,carrier,account,fp=old.recoverable(client);claim=old.approve_claim(client,ex,old.create_claim(client,ex,carrier,fp),fp)
    old.recovery(client,ex,'recovery_receive',claim,amount_cents=40,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    with SessionLocal() as db:data['loss_id']=db.scalar(select(TransferLossPosting.id))
    row=found(client,data,3000);ready(client,data,row);restore(client,data,row);login(client,'finance')
    claim=current(client,row)['claims'][0]
    command(client,row,'terms',dict(claim_id=claim['id'],claim_version=claim['version'],target_cents=0,due_date=today().isoformat(),reason='原承运人确认全部退原款，可按实际银行分笔完成',evidence_id=fp))
    login(client,'manager');claim=current(client,row)['claims'][0]
    command(client,row,'terms_approve',dict(claim_id=claim['id'],claim_version=claim['version'],plan_id=claim['pending_plan_id'],reason='本人独立核对原承运人全部退回条件',evidence_id=fp))
    login(client,'finance');before=current(client,row);claim=before['claims'][0];incoming=claim['payments'][0]
    callers=[TestClient(app),TestClient(app)]
    for caller in callers:login(caller,'finance')
    bodies=[dict(request_id=uuid.uuid4().hex,version=before['version'],transfer_version=before['transfer_version'],case_version=before['case_version'],values=dict(
        claim_id=claim['id'],claim_version=claim['version'],original_id=incoming['id'],amount_cents=25,account_id=account,reference=uuid.uuid4().hex,
        business_date=today().isoformat(),evidence_id=fp,confirmed=True)) for _ in range(2)]
    endpoint=f"/api/transfer-goods-recoveries/{row['id']}/actions/refund"
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda i:callers[i].post(endpoint,json=bodies[i]),range(2)))
        assert sorted(r.status_code for r in responses)==[200,409],[r.text for r in responses]
        winner=next(i for i,r in enumerate(responses) if r.status_code==200)
        assert callers[winner].post(endpoint,json=bodies[winner]).status_code==200
    finally:
        for caller in callers:caller.close()
    r=current(client,row);assert r['status']=='financial';claim=r['claims'][0];assert claim['refund_cents']==15
    command(client,row,'refund',dict(claim_id=claim['id'],claim_version=claim['version'],original_id=incoming['id'],amount_cents=15,account_id=account,
        reference=uuid.uuid4().hex,business_date=today().isoformat(),evidence_id=fp,confirmed=True))
    assert current(client,row)['status']=='closed'
    with SessionLocal() as db:assert [(c.direction,c.amount_cents) for c in db.scalars(select(CashEntry).order_by(CashEntry.id))]==[('in',40),('out',25),('out',15)]
