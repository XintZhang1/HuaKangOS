"""Reverse original loss settlement uses independent real store cash and sources."""
import csv,io,sqlite3,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,today
from app.models import User,CashEntry
from app.tenancy import set_scope,project_user
from app.backup_integrity import validate_sqlite
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app.reconciliation_models import ClearingBucket,ClearingOffset
from app import business_entity_service as entities
from tests import test_transfer_goods_recovery as goods,test_reconciliation as rc
from tests.test_service_analytics import report,reconciled
from tests.conftest import login,TEST_DIR


def origin(c,kind='material_found'):
    response=c.get('/api/reconciliation/origins');assert response.status_code==200,response.text
    return next(r for r in response.json()['items'] if r['origin_kind']==kind)


def restore(c,data,quantity=3000):
    row=goods.found(c,data,quantity);goods.ready(c,data,row);goods.restore(c,data,row);login(c,'finance');return row


def original_paid(c,data):
    goods.old.switch(c,2);login(c,'finance');row=rc.clear(c,origin(c,'material_loss'))
    rc.cmd(c,row,'pay',rc.payvalues(c,row),kind='clearing')
    goods.old.switch(c,1);login(c,'finance');rc.cmd(c,row,'receive',rc.payvalues(c,row),kind='clearing')
    return row


def test_reverse_partial_actual_clearing_preserves_original_paid_cash_and_scope(client):
    data=goods.original(client);prior=original_paid(client,data);row=restore(client,data)
    o=origin(client);assert o['available_cents']==50 and o['active_goods_recovery_id'] is None
    clearing=rc.clear(client,o,30);rc.clear(client,o,21,409)
    before=rc.get(client,clearing,'clearing');values=rc.payvalues(client,clearing);before=rc.get(client,clearing,'clearing');key=uuid.uuid4().hex
    paid=rc.cmd(client,clearing,'pay',values,kind='clearing',old=before,key=key)
    assert rc.cmd(client,clearing,'pay',values,kind='clearing',old=before,key=key)==paid
    rc.cmd(client,clearing,'pay',values,409,kind='clearing',old=before)
    rc.cmd(client,clearing,'cancel',status=409,kind='clearing')
    result=reconciled(client,'transport_found_clearing',-50)
    assert result['metrics']['internal_cash_in_transit_cents']==30
    goods.old.switch(client,3);login(client,'admin');assert client.get(f"/api/reconciliation/clearing/{clearing['id']}").status_code==404
    goods.old.switch(client,2);login(client,'finance');rc.cmd(client,clearing,'receive',rc.payvalues(client,clearing),kind='clearing')
    assert reconciled(client,'transport_found_clearing',20)['metrics']['internal_cash_in_transit_cents']==0
    goods.old.switch(client,1);assert origin(client)['settled_cents']==30 and origin(client)['available_cents']==20
    assert rc.get(client,prior,'clearing')['status']=='settled'
    result=reconciled(client,'transport_found_clearing',-20);assert result['metrics']['material_in_transit_cents']==0
    with SessionLocal() as db:
        assert len(list(db.scalars(select(CashEntry).where(CashEntry.category=='interstore_clearing'))))==4
        assert db.scalar(select(func.sum(ClearingOffset.amount_cents)))==0
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
        with entities.authority(db,user):assert '仍有原物资找回后的反向店间往来' in entities.blockers(db)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_sqlite(db)['verified_clearing_orders']==2


def test_find_pause_retains_paid_receive_and_unpaid_cancel_reject_exits(client):
    data=goods.original(client);goods.old.switch(client,2);login(client,'finance');o=origin(client,'material_loss')
    paid=rc.clear(client,o,20);cancel=rc.clear(client,o,10);reject=rc.clear(client,o,10)
    rc.cmd(client,paid,'pay',rc.payvalues(client,paid),kind='clearing')
    found=goods.found(client,data,1000)
    goods.old.switch(client,2);login(client,'finance');assert origin(client,'material_loss')['active_goods_recovery_id']==found['id']
    rc.clear(client,o,1,409)
    values=rc.payvalues(client,cancel);rc.cmd(client,cancel,'pay',values,status=409,kind='clearing')
    rc.cmd(client,cancel,'cancel',kind='clearing')
    goods.old.switch(client,1);login(client,'finance');rc.cmd(client,reject,'reject',kind='clearing')
    rc.cmd(client,paid,'receive',rc.payvalues(client,paid),kind='clearing')
    login(client,'inventory');goods.physical(client,found,'cancel')
    goods.old.switch(client,2);login(client,'finance');o=origin(client,'material_loss');assert o['reserved_cents']==0 and o['settled_cents']==20 and o['available_cents']==30
    assert rc.clear(client,o,30)['status']=='requested'


def test_reverse_clearing_competes_with_new_found_and_does_not_deadlock(client):
    from fastapi.testclient import TestClient
    from app.main import app
    data=goods.original(client);restore(client,data,1000);o=origin(client);r=rc.clear(client,o)
    payment=rc.payvalues(client,r);clearing=rc.get(client,r,'clearing');login(client,'inventory');t=goods.old.get(client,{'id':data['transfer_id']})
    clients=[TestClient(app),TestClient(app)];login(clients[0],'finance');login(clients[1],'inventory')
    payment_body=dict(request_id=uuid.uuid4().hex,version=clearing['version'],case_version=clearing['case_version'],values=payment)
    found_body=dict(request_id=uuid.uuid4().hex,transfer_id=t['id'],loss_id=data['loss_id'],version=t['version'],case_version=t['case_version'],quantity_milli=1000,
        evidence_id=data['outproof'],result='本人实际找到另一份，原清算与找回须共用锁',due_date=today().isoformat(),confirmed=True)
    try:
        def run(i):return clients[i].post(f"/api/reconciliation/clearing/{r['id']}/actions/pay" if i==0 else '/api/transfer-goods-recoveries',json=payment_body if i==0 else found_body)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        assert sorted(x.status_code for x in results) in ([200,409],[201,409]),[x.text for x in results]
        winner=next(i for i,x in enumerate(results) if x.status_code in {200,201})
        assert run(winner).status_code==results[winner].status_code
    finally:
        for c in clients:c.close()
    with SessionLocal() as db:assert len(list(db.scalars(select(CashEntry).where(CashEntry.category=='interstore_clearing'))))<=1


def test_reverse_pair_restore_rejects_same_amount_wrong_original_and_capacity(client):
    data=goods.original(client);restore(client,data,1000);r=rc.clear(client,origin(client))
    rc.cmd(client,r,'pay',rc.payvalues(client,r),kind='clearing');goods.old.switch(client,2);login(client,'finance');rc.cmd(client,r,'receive',rc.payvalues(client,r),kind='clearing')
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);assert validate_sqlite(db)['verified_clearing_orders']==1
        db.execute('UPDATE transfer_goods_settlements SET recovery_id=recovery_id+999 WHERE amount_cents>0')
        with pytest.raises(ValueError,match='同一实际恢复'):validate_reconciliation_sqlite(db)
        db.rollback();db.execute('UPDATE transfer_goods_settlements SET original_id=original_id+999 WHERE amount_cents>0')
        with pytest.raises(ValueError,match='原找回、恢复或损失'):validate_reconciliation_sqlite(db)
        db.rollback();db.execute('UPDATE interstore_clearing_buckets SET reserved_cents=1,settled_cents=0')
        with pytest.raises(ValueError,match='额度占用'):validate_reconciliation_sqlite(db)


def test_recovered_asset_report_chart_csv_current_custody_and_original_period(client):
    data=goods.original(client);row=goods.found(client,data,1000)
    login(client,'finance');current=report(client);table=current['tables']['transport_found_custody'];assert len(table['rows'])==1
    chart=next(c for c in current['charts'] if c['id']==table['id']);assert chart['unit']=='count' and sum(chart['series'][0]['values'])==1
    goods.ready(client,data,row);goods.restore(client,data,row);login(client,'finance')
    result=reconciled(client,'transport_found_cost',33);reconciled(client,'transport_found_burden',-17);reconciled(client,'transport_asset_changes',67)
    assert result['metrics']['material_in_transit_cents']==0 and result['metrics']['cash_in_cents']==result['metrics']['cash_out_cents']==0
    assert not result['tables']['transport_found_custody']['rows']
    past=(today()-timedelta(days=1)).isoformat();prior=report(client,date_from=past,date_to=past)
    assert not prior['tables']['transport_found_cost']['rows'] and len(prior['tables']['transport_found_clearing']['rows'])==1
    goods.old.switch(client,2);reconciled(client,'transport_found_cost',0);reconciled(client,'transport_found_burden',-16)
    login(client,'admin');goods.old.switch(client,'all');aggregate=reconciled(client,'transport_found_burden',-33)
    assert all(r['route'] is None for name,t in aggregate['tables'].items() if name.startswith('transport_') for r in t['rows'])
    goods.old.switch(client,3);assert not report(client)['tables']['transport_found_cost']['rows']
    goods.old.switch(client,1);login(client,'inventory');assert client.get('/api/flow/analytics/export',params={'dataset':'transport_found_cost'}).status_code==403
