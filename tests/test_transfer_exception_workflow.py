"""Actual transfer v3 APIs, physical findings, independent review and recovery."""
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,today,engine
from app.models import User,UserStore,CashEntry
from app.flow_models import Case,StockMove,Item,Task
from app.tenancy import set_scope,project_user
from app.transfer_models import MaterialTransfer
from app import transfer_service as base
from app import transfer_exception_service as svc
from app.transfer_exception_models import TransferLossPosting,TransferLossSettlement,TransferException,TransferExceptionReceipt
from tests.conftest import login,PASSWORD_HASH,TEST_DIR
from tests.test_transfers import seed,switch,create,command,get

def proof(c,cid,financial=False):
    r=c.post(f'/api/flow/cases/{cid}/files',files={'file':('事实凭据.txt','独立合成事实凭据'.encode(),'text/plain')},data={'category':'receipt' if financial else 'evidence'})
    assert r.status_code==200,r.text
    return r.json()['id']


def initialize(c,mode='missing'):
    a,b=seed()
    with SessionLocal() as db:
        for role in ('inventory','manager'):
            old=db.scalar(select(User).where(User.username==role))
            relationship=db.scalar(select(UserStore).where(UserStore.user_id==old.id,UserStore.store_id==2))
            db.delete(relationship)
            u=User(username=role+'2',display_name='调入方'+role,role=role,password_hash=PASSWORD_HASH,must_change_password=False)
            db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=2,role=role))
        db.commit()
    login(c,'inventory');t=create(c,a)
    login(c,'manager');command(c,t,'approve')
    switch(c,2);login(c,'manager2');command(c,t,'approve')
    switch(c,1);login(c,'inventory');current=get(c,t);outproof=proof(c,current['case_id'])
    current=command(c,t,'dispatch',{'evidence_id':outproof,'reason':'实际交承运人发出'})
    original=current['movements'][0]['id'];source=current['case_id']
    switch(c,2);login(c,'inventory2');current=get(c,t);dest=current['case_id'];inproof=proof(c,dest)
    if mode in {'rejected','returning'}:
        current=command(c,t,'receive',{'evidence_id':inproof,'reason':'部分合格与实际坏件分别验收',
            'lines':[{'line_id':current['lines'][0]['id'],'item_id':b,'accept_milli':2000,'reject_milli':1000}]})
        original=next(m['id'] for m in current['movements'] if m['kind']=='reject')
        if mode=='returning':
            current=command(c,t,'return_ship',{'evidence_id':inproof,'reason':'坏件独立包装实际退回发运','rejection_id':original})
            original=next(m['id'] for m in current['movements'] if m['kind']=='return_ship')
            switch(c,1);login(c,'inventory')
            command(c,t,'return_receive',{'evidence_id':outproof,'reason':'先到部分已核对可用入库','shipment_id':original,'quantity_milli':333})
    switch(c,2);login(c,'inventory2')
    return dict(transfer_id=t['id'],original_id=original,source=source,destination=dest,outproof=outproof,inproof=inproof,item=a,destination_item=b)


def current(c,row):
    r=c.get(f"/api/transfer-exceptions/{row['id']}");assert r.status_code==200,r.text;return r.json()


def new(c,data,quantity=3000,finding='missing',status=201,request=None):
    sid=int(c.headers.get('X-Store-ID','1'))
    with SessionLocal() as db:
        set_scope(db,[sid],sid);u=db.scalar(select(User).where(User.username=='admin'))
        with base.authority(db,u):
            p=base.get_transfer(db,data['transfer_id'],sid);case=db.scalar(select(Case).where(Case.id==(p.from_case_id if sid==p.from_store_id else p.to_case_id)))
            body=dict(request_id=request or uuid.uuid4().hex,transfer_id=p.id,version=p.version,case_version=case.version,
                original_id=data['original_id'],quantity_milli=quantity,finding=finding,result='本人逐一核对本店实际交接结果',
                evidence_id=data['outproof'] if sid==1 else data['inproof'],due_date=today().isoformat(),confirmed=True)
    r=c.post('/api/transfer-exceptions',json=body);assert r.status_code==status,r.text;return r.json()


def action(c,row,name,values,status=200,before=None,key=None):
    before=before or current(c,row)
    body=dict(request_id=key or uuid.uuid4().hex,version=before['version'],transfer_version=before['transfer_version'],case_version=before['case_version'],values=values)
    r=c.post(f"/api/transfer-exceptions/{row['id']}/actions/{name}",json=body)
    assert r.status_code==status,r.text
    return r.json()


def observed(c,data,row):
    switch(c,1);login(c,'inventory')
    return action(c,row,'observe',dict(evidence_id=data['outproof'],result='调出方本人核对已交付数量与包装',confirmed=True))


def planned(c,data,row,dest_share=None):
    login(c,'finance');latest=current(c,row);fp=proof(c,latest['case_id'],True)
    value=latest['value_cents'];dest_share=value//2 if dest_share is None else dest_share
    return action(c,row,'plan',dict(source_bearer_cents=value-dest_share,destination_bearer_cents=dest_share,reason='双方依据原成本明确承担，不等于承运人赔款',evidence_id=fp))


def approved(c,data,row):
    for sid,who in ((1,'manager'),(2,'manager2')):
        switch(c,sid);login(c,who);latest=current(c,row);fp=proof(c,latest['case_id'],True)
        row=action(c,row,'approve',dict(plan_id=latest['plans'][-1]['id'],reason='本人独立复核双方原事实与原成本承担',evidence_id=fp))
    return row


def posted(c,data,row):
    switch(c,1);login(c,'finance');latest=current(c,row);fp=proof(c,latest['case_id'],True)
    return action(c,row,'post_loss',dict(evidence_id=fp,confirmed=True))


def test_missing_loss_is_two_store_reviewed_without_stock_or_cash(client):
    data=initialize(client);row=new(client,data);observed(client,data,row);row=planned(client,data,row);row=approved(client,data,row)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(TransferLossPosting))==0
    row=posted(client,data,row);assert row['status']=='posted' and not row['paused']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(func.count()).select_from(StockMove))==1
        loss=db.scalar(select(TransferLossPosting));assert (loss.quantity_milli,loss.value_cents)==(3000,100)
        assert db.scalar(select(func.sum(TransferLossSettlement.amount_cents)))==0
        assert db.scalar(select(func.count()).select_from(TransferLossSettlement))==2
        assert set(db.scalars(select(Case.state)))=={'completed'}
    switch(client,2);login(client,'inventory2');read=current(client,row)
    assert 'value_cents' not in read and 'source_bearer_cents' not in read['plans'][0]
    assert 'evidence_id' not in read['observations'][1]


def test_rejected_damage_requires_actual_custodian_disposal_and_no_cancel(client):
    data=initialize(client,'rejected');row=new(client,data,1000,'damaged');observed(client,data,row);planned(client,data,row);row=approved(client,data,row)
    switch(client,1);login(client,'finance');fp=proof(client,data['source'],True)
    action(client,row,'post_loss',dict(evidence_id=fp,confirmed=True),409)
    login(client,'inventory');action(client,row,'dispose',dict(evidence_id=data['outproof'],confirmed=True,result='错误门店不能代替确认实际处置'),409)
    switch(client,2);login(client,'inventory2')
    row=action(client,row,'dispose',dict(evidence_id=data['inproof'],confirmed=True,result='已按双方批准将原在手不可用件实际处置'))
    action(client,row,'cancel',dict(evidence_id=data['inproof'],reason='已经真实处置不能抹掉事实'),409)
    row=posted(client,data,row)
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(Item.inventory_value_cents)))==66
        assert db.scalar(select(TransferLossPosting.value_cents))==34
        assert db.scalar(select(func.count()).select_from(StockMove))==2


def test_partial_actual_return_then_residual_loss_uses_original_batch_tail(client):
    data=initialize(client,'returning');row=new(client,data,667,'missing');observed(client,data,row);planned(client,data,row);approved(client,data,row);posted(client,data,row)
    with SessionLocal() as db:
        loss=db.scalar(select(TransferLossPosting));assert (loss.quantity_milli,loss.value_cents)==(667,23)
        assert db.scalar(select(func.sum(Item.quantity_milli)))+loss.quantity_milli==3000
        assert db.scalar(select(func.sum(Item.inventory_value_cents)))+loss.value_cents==100


def test_cancel_stale_duplicate_crossstore_and_paused_guard(client):
    data=initialize(client);row=new(client,data);old=current(client,row)
    with SessionLocal() as db:
        set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='inventory2')),'inventory')
        with svc.authority(db,user):
            parent=base.get_transfer(db,data['transfer_id'],2)
            with pytest.raises(HTTPException) as error:svc.guard_transfer_command(db,user,parent,'receive')
            assert error.value.status_code==409
    values=dict(evidence_id=data['inproof'],reason='实际复核确认无差异，本申请有据取消');key=uuid.uuid4().hex
    cancelled=action(client,row,'cancel',values,before=old,key=key)
    assert cancelled['status']=='cancelled'
    assert action(client,row,'cancel',values,before=old,key=key)==cancelled
    action(client,row,'cancel',values,before=old,status=409)
    new(client,data)
    login(client,'admin');switch(client,3)
    assert client.get(f"/api/transfer-exceptions/{row['id']}").status_code==404
    switch(client,'all');assert client.get('/api/transfer-exceptions').status_code==409
    switch(client,2);login(client,'sales');assert client.get('/api/transfer-exceptions').status_code==403


def test_two_competing_investigations_reserve_original_remaining_once(client):
    data=initialize(client)
    with SessionLocal() as db:
        set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='inventory2')),'inventory')
        with svc.authority(db,user):
            parent=base.get_transfer(db,data['transfer_id'],2);version=parent.version
            cv=db.scalar(select(Case.version).where(Case.id==parent.to_case_id))
    def compete(_):
        with SessionLocal() as db:
            set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='inventory2')),'inventory')
            try:
                svc.create(db,user,uuid.uuid4().hex,data['transfer_id'],version,cv,data['original_id'],3000,'missing','实际核对同一尚未验收批次',data['inproof'],today())
                return 201
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(compete,range(2)))==[201,409]
    with SessionLocal() as db:
        set_scope(db,[2],2);user=db.scalar(select(User).where(User.username=='admin'))
        with svc.authority(db,user):
            assert db.scalar(select(func.count()).select_from(TransferException))==1
            assert db.scalar(select(func.count()).select_from(TransferExceptionReceipt))==1


def recoverable(c):
    data=initialize(c);row=new(c,data);observed(c,data,row);planned(c,data,row);approved(c,data,row);posted(c,data,row)
    login(c,'admin')
    from tests.test_repair_orders import typed
    from tests.test_procurement import bank
    carrier=typed(c,'suppliers',dict(code='CARRIER',name='合成承运单位',payment_terms_days=30))
    account=bank(c);login(c,'finance');fp=proof(c,data['source'],True)
    return data,row,carrier,account,fp


def recovery(c,row,action_name,claim=None,**values):
    if claim:
        live=next(x for x in current(c,row)['recoveries'] if x['id']==claim['id'])
        values.update(claim_id=live['id'],claim_version=live['version'])
    return action(c,row,action_name,values)


def create_claim(c,row,carrier,fp,amount=40):
    return recovery(c,row,'recovery_create',counterparty_kind='carrier',counterparty_id=carrier['id'],target_cents=amount,
        reason='承运人已经以本店凭据明确同意的原损失赔付额',due_date=today().isoformat(),evidence_id=fp)['recoveries'][-1]


def approve_claim(c,row,claim,fp):
    login(c,'manager');result=recovery(c,row,'recovery_approve',claim,plan_id=claim['pending_plan_id'],reason='独立复核往来方原确认而非假定赔偿',evidence_id=fp)
    login(c,'finance');return next(x for x in result['recoveries'] if x['id']==claim['id'])


def test_external_recovery_target_review_cash_and_original_return_are_distinct(client):
    data,row,carrier,account,fp=recoverable(client);claim=create_claim(client,row,carrier,fp)
    assert claim['target_cents']==claim['paid_cents']==0 and claim['pending_plan_id']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
    claim=approve_claim(client,row,claim,fp);assert claim['target_cents']==40 and claim['due_cents']==40
    result=recovery(client,row,'recovery_receive',claim,amount_cents=30,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    claim=result['recoveries'][0];assert claim['paid_cents']==30 and claim['due_cents']==10
    result=recovery(client,row,'recovery_plan',claim,target_cents=10,due_date=today().isoformat(),reason='原往来方有据更正赔偿目标，需要退回超出原款',evidence_id=fp)
    claim=approve_claim(client,row,result['recoveries'][0],fp);assert claim['refund_cents']==20
    original=claim['payments'][0]
    result=recovery(client,row,'recovery_refund',claim,amount_cents=20,account_id=account,reference=uuid.uuid4().hex,
        business_date=today().isoformat(),confirmed=True,evidence_id=fp,original_id=original['id'])
    claim=result['recoveries'][0];assert claim['target_cents']==claim['paid_cents']==10 and claim['refund_cents']==0
    with SessionLocal() as db:
        cash=list(db.scalars(select(CashEntry)));assert [(c.direction,c.amount_cents) for c in cash]==[('in',30),('out',20)]
        assert db.scalar(select(func.count()).select_from(StockMove))==1
        assert db.scalar(select(TransferLossPosting.value_cents))==100


def test_recovery_burden_cap_pending_cancel_and_independent_approval(client):
    data,row,carrier,account,fp=recoverable(client);claim=create_claim(client,row,carrier,fp,40)
    action(client,row,'recovery_create',dict(counterparty_kind='carrier',counterparty_id=carrier['id'],target_cents=11,
        reason='不得超过本店五十分原承担余额',due_date=today().isoformat(),evidence_id=fp),409)
    values=dict(claim_id=claim['id'],claim_version=claim['version'],plan_id=claim['pending_plan_id'],reason='申请人不允许自己批准真实追偿',evidence_id=fp)
    action(client,row,'recovery_approve',values,403)
    recovery(client,row,'recovery_cancel',claim,plan_id=claim['pending_plan_id'],reason='未生效目标撤回重新核对往来方事实',evidence_id=fp)
    other=create_claim(client,row,carrier,fp,50);assert other['pending_plan_id']
    # Even a global administrator cannot approve their own target revision.
    login(client,'manager');recovery(client,row,'recovery_reject',other,plan_id=other['pending_plan_id'],reason='确认凭据不充分，本版拒绝',evidence_id=fp)
    login(client,'admin');own=create_claim(client,row,carrier,fp,20)
    action(client,row,'recovery_approve',dict(claim_id=own['id'],claim_version=own['version'],plan_id=own['pending_plan_id'],reason='管理员也不能批准自己申请',evidence_id=fp),403)


def test_recovery_same_cash_reference_duplicate_stale_foreign_file_and_store_are_refused(client):
    data,row,carrier,account,fp=recoverable(client);claim=approve_claim(client,row,create_claim(client,row,carrier,fp),fp)
    ref=uuid.uuid4().hex;values=dict(claim_id=claim['id'],claim_version=claim['version'],amount_cents=20,account_id=account,
        reference=ref,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    before=current(client,row);key=uuid.uuid4().hex
    first=action(client,row,'recovery_receive',values,before=before,key=key)
    assert action(client,row,'recovery_receive',values,before=before,key=key)==first
    action(client,row,'recovery_receive',values,before=before,status=409)
    claim=first['recoveries'][0];values.update(claim_version=claim['version'])
    action(client,row,'recovery_receive',values,409)
    values.update(reference=uuid.uuid4().hex,evidence_id=data['inproof'])
    action(client,row,'recovery_receive',values,422)
    switch(client,2);assert current(client,row)['recoveries']==[]
    destfp=proof(client,data['destination'],True);values.update(evidence_id=destfp)
    action(client,row,'recovery_receive',values,404)
    login(client,'inventory2');assert current(client,row)['recoveries']==[]
    assert client.get(f'/api/flow/files/{destfp}').status_code==403
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==1


def test_recovery_competing_receipts_cannot_overcollect_original_obligation(client):
    data,row,carrier,account,fp=recoverable(client);claim=approve_claim(client,row,create_claim(client,row,carrier,fp),fp)
    current_row=current(client,row)
    def compete(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
            try:
                svc.command(db,user,row['id'],uuid.uuid4().hex,current_row['version'],current_row['transfer_version'],current_row['case_version'],
                    'recovery_receive',dict(claim_id=claim['id'],claim_version=claim['version'],amount_cents=40,account_id=account,
                        reference=uuid.uuid4().hex,business_date=today(),confirmed=True,evidence_id=fp))
                return 200
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(compete,range(2)))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(CashEntry.amount_cents)))==40
        assert db.scalar(select(func.count()).select_from(CashEntry))==1


def test_recovery_reduced_target_does_not_release_unreturned_original_cash(client):
    data,row,carrier,account,fp=recoverable(client);claim=approve_claim(client,row,create_claim(client,row,carrier,fp,50),fp)
    result=recovery(client,row,'recovery_receive',claim,amount_cents=50,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    claim=result['recoveries'][0]
    result=recovery(client,row,'recovery_plan',claim,target_cents=0,due_date=today().isoformat(),reason='往来方有据撤销赔付，必须退回实际原款',evidence_id=fp)
    claim=approve_claim(client,row,result['recoveries'][0],fp);assert claim['refund_cents']==50
    action(client,row,'recovery_create',dict(counterparty_kind='carrier',counterparty_id=carrier['id'],target_cents=1,
        reason='前笔未退现金仍占用原损失承担',due_date=today().isoformat(),evidence_id=fp),409)


def test_nonempty_loss_recovery_restore_and_recomputed_source_tampering(client):
    from app.transfer_exception_integrity import validate_transfer_exceptions_sqlite
    data,row,carrier,account,fp=recoverable(client);claim=approve_claim(client,row,create_claim(client,row,carrier,fp),fp)
    recovery(client,row,'recovery_receive',claim,amount_cents=30,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored)
        result=validate_transfer_exceptions_sqlite(restored)
        assert result==dict(transport_exceptions=1,transport_losses=1,transport_recoveries=1)
        restored.execute('UPDATE transfer_loss_settlements SET amount_cents=amount_cents+1 WHERE amount_cents>0')
        with pytest.raises(ValueError,match='往来'):validate_transfer_exceptions_sqlite(restored)
        restored.rollback()
        restored.execute("UPDATE transfer_recovery_reviews SET actor_id=(SELECT actor_id FROM transfer_recovery_plans WHERE id=plan_id)")
        with pytest.raises(ValueError,match='独立'):validate_transfer_exceptions_sqlite(restored)
        restored.rollback()
        restored.execute('UPDATE transfer_recovery_payments SET amount_cents=amount_cents+1')
        restored.execute('UPDATE cash_entries SET amount_cents=amount_cents+1')
        # The cash/source agree, but a forged 41 fen would exceed the approved
        # original recovery target. Merely recomputing summaries cannot pass.
        restored.execute('UPDATE transfer_recovery_payments SET amount_cents=41')
        restored.execute('UPDATE cash_entries SET amount_cents=41')
        with pytest.raises(ValueError,match='超过当时应收'):validate_transfer_exceptions_sqlite(restored)


def test_damage_posting_and_partial_return_restore_preserve_nested_original_batches(client):
    from app.transfer_exception_integrity import validate_transfer_exceptions_sqlite
    data=initialize(client,'returning');row=new(client,data,667,'missing');observed(client,data,row);planned(client,data,row);approved(client,data,row);posted(client,data,row)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored)
        assert validate_transfer_exceptions_sqlite(restored)['transport_losses']==1
        restored.execute('UPDATE transfer_exceptions SET value_cents=24')
        restored.execute('UPDATE transfer_exception_plans SET source_bearer_cents=source_bearer_cents+1')
        restored.execute('UPDATE transfer_loss_postings SET source_bearer_cents=source_bearer_cents+1,value_cents=value_cents+1')
        with pytest.raises(ValueError,match='原成本不守恒'):validate_transfer_exceptions_sqlite(restored)


def test_rejected_plan_new_observations_and_latest_two_independent_reviews(client):
    data=initialize(client);row=new(client,data);observed(client,data,row);row=planned(client,data,row)
    login(client,'manager');fp=proof(client,data['source'],True);first_plan=row['plans'][-1]['id']
    row=action(client,row,'reject_plan',dict(plan_id=first_plan,evidence_id=fp,reason='本版事实不清楚，退回两方核对'))
    assert row['status']=='investigating'
    login(client,'inventory');row=action(client,row,'observe',dict(evidence_id=data['outproof'],result='重新核对本人原发运清点记录',confirmed=True))
    row=planned(client,data,row);assert len(row['plans'])==2 and len(row['observations'])==3
    login(client,'manager');action(client,row,'approve',dict(plan_id=first_plan,evidence_id=fp,reason='旧版方案不能代替当前重新批准'),409)
    # Administrator may act for an assigned manager, but cannot be both parties.
    login(client,'admin');latest=current(client,row);row=action(client,row,'approve',dict(plan_id=latest['plans'][-1]['id'],evidence_id=fp,reason='独立管理员复核调出方方案'))
    switch(client,2);infinance=proof(client,data['destination'],True)
    action(client,row,'approve',dict(plan_id=row['plans'][-1]['id'],evidence_id=infinance,reason='同一管理员不能代两方复核'),403)
    login(client,'manager2');row=action(client,row,'approve',dict(plan_id=row['plans'][-1]['id'],evidence_id=infinance,reason='调入方主管独立核对本版方案'))
    assert row['status']=='approved'


def test_report_original_loss_vs_store_burden_recovery_cash_and_readonly_scope(client):
    from types import SimpleNamespace
    from app.transfer_exception_analytics import analytics_rows
    data,row,carrier,account,fp=recoverable(client);claim=approve_claim(client,row,create_claim(client,row,carrier,fp),fp)
    recovery(client,row,'recovery_receive',claim,amount_cents=30,account_id=account,reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    with SessionLocal() as db:
        user=SimpleNamespace(role='finance',_aggregate_scope=False)
        set_scope(db,[1],1);source=analytics_rows(db,user)
        assert sum(r['amount_cents'] for r in source['losses'])==100
        assert sum(r['amount_cents'] for r in source['burdens'])==50
        assert sum(r['amount_cents'] for r in source['recovery_confirmations'])==40
        assert sum(r['amount_cents'] for r in source['recovery_cash'])==30
        assert source['recovery_balances'][0]['due_cents']==10
        set_scope(db,[2],2);destination=analytics_rows(db,user)
        assert not destination['losses'] and not destination['recovery_cash']
        assert sum(r['amount_cents'] for r in destination['burdens'])==50
        assert not db.info.get('_transfer_authority')
        set_scope(db,[1,2],None);user._aggregate_scope=True;group=analytics_rows(db,user)
        assert sum(r['amount_cents'] for r in group['burdens'])==100
        assert sum(r['amount_cents'] for r in group['clearing'])==0
        assert all(r['case_id'] is None and r['route'] is None for values in group.values() for r in values)
        user._aggregate_scope=False;inferred=analytics_rows(db,user)
        assert all(r['case_id'] is None and r['route'] is None for values in inferred.values() for r in values)
        assert all(r.get('counterparty')!='合成承运单位' for values in inferred.values() for r in values)
        user.role='inventory'
        with pytest.raises(HTTPException) as exc:analytics_rows(db,user)
        assert exc.value.status_code==403


def test_origins_available_remaining_private(client):
    data=initialize(client,'returning')
    r=client.get('/api/transfer-exceptions/origins/'+str(data['transfer_id']));assert r.status_code==200,r.text
    assert len(r.json()['origins'])==1
    assert r.json()['origins'][0]['remaining_milli']==667 and 'remaining_cents' not in r.json()['origins'][0]
    assert client.get('/api/transfer-exceptions/recovery-catalog').status_code==403
def test_old_second_version_does_not_gain_new_exception_actions(client,monkeypatch):
    monkeypatch.setattr(base,'NEW_TRANSFER_VERSION',2)
    data=initialize(client,'returning')
    assert client.get('/api/transfer-exceptions/origins/'+str(data['transfer_id'])).status_code==409
    new(client,data,667,status=409)


def test_new_default_three_loss_then_original_return_uses_remaining_not_original_total(client):
    data=initialize(client,'rejected');assert get(client,{'id':data['transfer_id']})['flow_version']==3
    row=new(client,data,667,'damaged');observed(client,data,row);planned(client,data,row);approved(client,data,row)
    switch(client,2);login(client,'inventory2');row=action(client,row,'dispose',dict(evidence_id=data['inproof'],confirmed=True,result='本店真实处置本批剩余不可用坏件'))
    posted(client,data,row);switch(client,2);login(client,'inventory2')
    latest=get(client,{'id':data['transfer_id']});assert latest['lines'][0]['return_pending_milli']==333
    shipped=command(client,latest,'return_ship',dict(evidence_id=data['inproof'],reason='只退剩余实际物资，已处置不重复发运',rejection_id=data['original_id']))
    shipment=next(m for m in shipped['movements'] if m['kind']=='return_ship');assert shipment['quantity_milli']==333
    switch(client,1);login(client,'inventory');latest=get(client,shipped)
    values=dict(evidence_id=data['outproof'],reason='质量不合格不可伪装可用库存',shipment_id=shipment['id'],quantity_milli=333,passed=False)
    command(client,latest,'return_receive',values,409)
    values.update(reason='原退实到质量合格后实际入库',passed=True)
    complete=command(client,latest,'return_receive',values);assert complete['status']=='completed'
    assert complete['lines'][0]['lost_milli']==667 and complete['lines'][0]['return_in_transit_milli']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(Item.inventory_value_cents)))==78
        assert db.scalar(select(TransferLossPosting.value_cents))==22


def test_normal_receiver_and_investigation_share_one_original_lock(client):
    data=initialize(client);latest=get(client,{'id':data['transfer_id']})
    def compete(which):
        with SessionLocal() as db:
            set_scope(db,[2],2);user=project_user(db.scalar(select(User).where(User.username=='inventory2')),'inventory')
            try:
                if which==0:
                    base.command(db,user,data['transfer_id'],uuid.uuid4().hex,latest['version'],latest['case_version'],'receive',
                        dict(evidence_id=data['inproof'],reason='本人实际验收同一剩余原批次',lines=[dict(line_id=latest['lines'][0]['id'],item_id=data['destination_item'],accept_milli=3000,reject_milli=0)]))
                else:svc.create(db,user,uuid.uuid4().hex,data['transfer_id'],latest['version'],latest['case_version'],data['original_id'],3000,'missing','同一原批次尚未收到需双方核对',data['inproof'],today())
                return 200
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(compete,range(2)))==[200,409]
    with SessionLocal() as db:
        set_scope(db,[2],2);user=db.scalar(select(User).where(User.username=='admin'))
        with svc.authority(db,user):
            count=db.scalar(select(func.count()).select_from(TransferException))
            quantity=db.scalar(select(Item.quantity_milli).where(Item.id==data['destination_item']))
            assert (count,quantity) in {(1,0),(0,3000)}


def test_later_physical_completion_preserves_prior_recovery_receipt_task(client):
    data=initialize(client);row=new(client,data,1000);observed(client,data,row);planned(client,data,row);approved(client,data,row);posted(client,data,row)
    login(client,'admin');from tests.test_repair_orders import typed
    carrier=typed(client,'suppliers',dict(code='EX-ACTUAL',name='本店合成承运方'));login(client,'finance');fp=proof(client,data['source'],True)
    claim=approve_claim(client,row,create_claim(client,row,carrier,fp,10),fp)
    switch(client,2);login(client,'inventory2');second=new(client,data,2000);observed(client,data,second);planned(client,data,second);approved(client,data,second);posted(client,data,second)
    with SessionLocal() as db:
        task=db.scalar(select(Task).where(Task.key==f"transfer_recovery_{claim['id']}_receive"))
        assert task.status=='open' and db.scalar(select(Case.state).where(Case.id==task.case_id))=='completed'
    assert current(client,row)['recoveries'][0]['due_cents']==10


def test_same_bank_reference_competes_with_ordinary_original_case_receipt(client):
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.test_workflow import order,action as flow_action,evidence as flow_evidence
    data,row,carrier,account,fp=recoverable(client);claim=approve_claim(client,row,create_claim(client,row,carrier,fp),fp)
    login(client,'admin');sale=flow_action(client,order(client,'0.40'),'approve');file_id=flow_evidence(client,sale,'receipt')
    login(client,'finance');before=current(client,row);reference='SAME-ACTUAL-'+uuid.uuid4().hex
    callers=[TestClient(app),TestClient(app)]
    for c in callers:login(c,'finance')
    requests=[
        (f"/api/transfer-exceptions/{row['id']}/actions/recovery_receive",dict(request_id=uuid.uuid4().hex,version=before['version'],transfer_version=before['transfer_version'],case_version=before['case_version'],values=dict(claim_id=claim['id'],claim_version=claim['version'],amount_cents=40,account_id=account,reference=reference,business_date=today().isoformat(),evidence_id=fp,confirmed=True))),
        (f"/api/flow/cases/{sale['id']}/actions/receive",dict(request_id=uuid.uuid4().hex,version=sale['version'],values=dict(amount='0.40',account_id=account,reference=reference,evidence_id=file_id)))]
    def compete(which):
        path,payload=requests[which];return callers[which].post(path,json=payload)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(compete,range(2)))
        codes=[r.status_code for r in responses]
        assert sorted(codes) in ([200,409],[200,503])
        loser=next(i for i,code in enumerate(codes) if code!=200)
        if codes[loser]==503:
            # The existing generic flow endpoint reports SQLite's busy snapshot
            # via its global 503 handler. Keep the original request, then verify
            # the committed other source makes the same bank reference refuse.
            assert loser==1 and '数据库暂时忙' in responses[loser].json()['detail']
        assert compete(loser).status_code==409
    finally:
        for c in callers:c.close()
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==1


def test_frozen_transport_migration_preserves_nonempty_clearing_and_has_current_constraints(tmp_path):
    from alembic import command as migration
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect
    from app.db import Base
    cfg=Config('alembic.ini');path=tmp_path/'only-synthetic-transport-migration.sqlite';cfg.attributes['url_override']='sqlite:///'+path.as_posix()
    migration.upgrade(cfg,'l248_business_entities')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO stores(id,code,name,active,created_at) VALUES(100,'LOSS-A','合成迁移甲店',1,CURRENT_TIMESTAMP),(101,'LOSS-B','合成迁移乙店',1,CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO interstore_clearing_buckets(id,version,updated_at,origin_kind,debtor_origin_id,creditor_origin_id,payer_store_id,receiver_store_id,total_cents,reserved_cents,settled_cents) VALUES(1,1,CURRENT_TIMESTAMP,'material',99,98,100,101,100,40,20)")
        db.commit()
    migration.upgrade(cfg,'m359_transfer_exceptions');eng=create_engine(cfg.attributes['url_override'])
    try:
        inspector=inspect(eng)
        for table in Base.metadata.tables.values():
            if table.name.startswith(('transfer_exception','transfer_loss','transfer_recovery')):
                assert {c['name'] for c in inspector.get_columns(table.name)}==set(table.columns.keys())
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT total_cents,reserved_cents,settled_cents FROM interstore_clearing_buckets WHERE id=1').fetchone()==(100,40,20)
            db.execute("UPDATE interstore_clearing_buckets SET origin_kind='material_loss' WHERE id=1")
            assert db.execute('PRAGMA foreign_key_check').fetchone() is None
    finally:eng.dispose()
