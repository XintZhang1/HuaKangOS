"""Actual two-store loss → source reports → paired cash clearing → frozen restore."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import json,sqlite3,uuid
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.db import today,SessionLocal
from app.flow_models import Item,Task
from app import reconciliation_service as reconciliation
from app.backup_integrity import validate_sqlite
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from tests import test_transfer_exception_workflow as exc,test_transfers as transfer,test_reconciliation as monthly
from tests.test_service_analytics import report,reconciled
from tests.conftest import login,TEST_DIR


def partial_loss(c):
    data=exc.initialize(c);row=exc.new(c,data,1000);exc.observed(c,data,row)
    exc.planned(c,data,row,16);exc.approved(c,data,row);exc.posted(c,data,row)
    return data,row


def test_transport_loss_removes_exact_in_transit_cost_and_store_burdens_only_once(client):
    data,row=partial_loss(client)
    result=reconciled(client,'transport_loss_cost',33)
    assert result['metrics']['material_in_transit_cents']==67
    assert result['metrics']['transport_loss_burden_cents']==17
    assert result['metrics']['interstore_material_net_cents']==16
    assert result['metrics']['cash_in_cents']==result['metrics']['recorded_business_net_cents']==0
    past=(today()-timedelta(days=1)).isoformat();prior=report(client,date_from=past,date_to=past)
    assert not prior['tables']['transport_loss_cost']['rows'] and prior['metrics']['material_in_transit_cents']==67
    transfer.switch(client,2);login(client,'finance')
    assert reconciled(client,'transport_loss_burden',16)['metrics']['transport_loss_cost_cents']==0
    login(client,'inventory2');current=transfer.get(client,{'id':data['transfer_id']})
    done=transfer.command(client,current,'receive',{'evidence_id':data['inproof'],'reason':'余下两件逐件实际验收合格',
        'lines':[{'line_id':current['lines'][0]['id'],'item_id':data['destination_item'],'accept_milli':2000,'reject_milli':0}]})
    assert done['status']=='completed'
    login(client,'admin');transfer.switch(client,'all');group=report(client)
    assert group['metrics']['material_in_transit_cents']==0
    assert group['metrics']['material_cost_cents']==67
    assert group['metrics']['transport_loss_burden_cents']==group['metrics']['transport_loss_cost_cents']==33
    assert group['metrics']['interstore_material_net_cents']==0
    assert all(r['route'] is None for key,t in group['tables'].items() if key.startswith('transport_') for r in t['rows'])
    with SessionLocal() as db:assert sum(x.inventory_value_cents for x in db.scalars(select(Item)))+33==100
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_sqlite(db)['transport_losses']==1


def test_transport_loss_original_liability_clears_only_after_both_actual_cash_confirmations(client):
    data,row,carrier,account,fp=exc.recoverable(client)
    transfer.switch(client,2);login(client,'finance')
    origins=client.get('/api/reconciliation/origins').json()['items'];origin=next(x for x in origins if x['origin_kind']=='material_loss')
    assert origin['available_cents']==50
    clearing=monthly.clear(client,origin,30);monthly.clear(client,origin,21,409)
    values=monthly.payvalues(client,clearing);before=monthly.get(client,clearing,'clearing');request=uuid.uuid4().hex
    paid=monthly.cmd(client,clearing,'pay',values,kind='clearing',old=before,key=request)
    assert monthly.cmd(client,clearing,'pay',values,kind='clearing',old=before,key=request)==paid
    monthly.cmd(client,clearing,'pay',values,409,kind='clearing',old=before)
    assert reconciled(client,'transport_loss_clearing',-50)['metrics']['internal_cash_in_transit_cents']==30
    transfer.switch(client,1);login(client,'finance')
    monthly.cmd(client,clearing,'receive',monthly.payvalues(client,clearing),kind='clearing')
    result=reconciled(client,'transport_loss_clearing',20)
    assert result['metrics']['interstore_material_net_cents']==20 and result['metrics']['internal_cash_in_transit_cents']==0
    assert result['metrics']['cash_in_cents']==result['metrics']['internal_cash_in_cents']==30
    transfer.switch(client,2);result=reconciled(client,'transport_loss_clearing',-20)
    assert result['metrics']['cash_out_cents']==result['metrics']['internal_cash_out_cents']==30
    login(client,'admin');transfer.switch(client,'all');group=report(client)
    assert group['metrics']['cash_in_cents']==group['metrics']['cash_out_cents']==group['metrics']['transport_loss_internal_net_cents']==0
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_sqlite(db)['verified_clearing_orders']==1


def test_recovery_actual_cash_and_approved_target_reconcile_without_sales_income(client):
    data,row,carrier,account,fp=exc.recoverable(client)
    claim=exc.approve_claim(client,row,exc.create_claim(client,row,carrier,fp),fp)
    result=exc.recovery(client,row,'recovery_receive',claim,amount_cents=30,account_id=account,
        reference=uuid.uuid4().hex,business_date=today().isoformat(),confirmed=True,evidence_id=fp)
    totals=reconciled(client,'transport_recovery_cash',30)['metrics']
    assert totals['transport_recovery_confirmed_cents']==40 and totals['transport_recovery_due_cents']==10
    assert totals['cash_in_cents']==30 and totals['recorded_business_net_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(Task.id).where(Task.case_id==data['source'],Task.status=='open',Task.key.like('transfer_recovery_%')))
    transfer.switch(client,2);assert not report(client)['tables']['transport_recovery_balances']['rows']
    transfer.switch(client,3);login(client,'admin');assert not report(client)['tables']['transport_loss_cost']['rows']
    transfer.switch(client,1);login(client,'inventory');assert client.get('/api/flow/analytics/export',params={'dataset':'transport_loss_cost'}).status_code==403


def test_monthly_v8_freezes_transport_originals_and_v7_keeps_its_scope(client,monkeypatch):
    data,row,carrier,account,fp=exc.recoverable(client);original=reconciliation.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(reconciliation,'snapshot',lambda db,user,start,end,definition_version=7:original(db,user,start,end,7))
        old=monthly.batch(client)
    assert old['definition_version']==7 and not any(x['source'].startswith('transfer_') for x in old['manifest'])
    claim=exc.create_claim(client,row,carrier,fp)
    assert not monthly.get(client,old)['source_changed']
    fresh=monthly.cmd(client,old,'recalculate',{'reason':'纳入本店运输原损失和追偿逐项核对'})
    assert fresh['definition_version']==CURRENT_DEFINITION_VERSION and fresh['summary']['transfer_loss_postings']['value_cents']==100
    assert fresh['summary']['transfer_loss_settlements']['amount_cents']==50
    assert fresh['summary']['period_cash_in_cents']==0 and not monthly.get(client,fresh)['source_changed']
    exc.approve_claim(client,row,claim,fp);assert monthly.get(client,fresh)['source_changed']
    fresh=monthly.cmd(client,fresh,'recalculate',{'reason':'独立确认已经完成，冻结原确认来源'})
    monthly.cmd(client,fresh,'submit');login(client,'manager');monthly.cmd(client,fresh,'seal',{'reason':'本人逐项核对原损失和独立赔付确认','evidence_id':monthly.proof(client,fresh)})
    assert monthly.get(client,old)['digest']==old['digest']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);assert validate_sqlite(db)['transport_recoveries']==1
        manifest=json.loads(json.dumps(fresh['manifest']))
        loss=next(x for x in manifest if x['source']=='transfer_loss_postings');loss['data']['original_id']+=999
        db.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',(json.dumps(manifest),reconciliation.digest({'manifest':manifest,'summary':fresh['summary']}),fresh['id']))
        with pytest.raises(ValueError,match='不可变原始'):validate_reconciliation_sqlite(db)
        db.rollback();summary=json.loads(json.dumps(fresh['summary']));summary['transfer_loss_postings']['value_cents']+=1
        db.execute('UPDATE reconciliation_batches SET summary=?,digest=? WHERE id=?',(json.dumps(summary),reconciliation.digest({'manifest':fresh['manifest'],'summary':summary}),fresh['id']))
        with pytest.raises(ValueError,match='摘要与原条目'):validate_reconciliation_sqlite(db)


def test_clearing_restore_rejects_swapped_loss_origin_even_when_amounts_match(client):
    data,row,carrier,account,fp=exc.recoverable(client)
    transfer.switch(client,2);login(client,'finance')
    origin=next(x for x in client.get('/api/reconciliation/origins').json()['items'] if x['origin_kind']=='material_loss')
    monthly.clear(client,origin)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as db:
        source.backup(db);validate_sqlite(db)
        db.execute('UPDATE transfer_loss_settlements SET posting_id=posting_id+999 WHERE amount_cents>0')
        with pytest.raises(ValueError,match='原核销与差异'):validate_reconciliation_sqlite(db)


def test_postgres_source_graph_uses_actual_damage_disposal_recovery_refund_and_loss_clearing(client):
    from tests.postgres_wave12 import seed
    seed(client)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:
        result=validate_sqlite(db)
        assert result['transport_losses']==result['transport_recoveries']==result['verified_clearing_orders']==1


def test_nonempty_l248_m359_n46a_upgrade_preserves_v2_cash_and_clearing(client,tmp_path,monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import MetaData,inspect
    from app.db import engine,make_engine
    from app import transfer_service
    from scripts.migrate_database import table_fingerprint
    with monkeypatch.context() as patch:
        patch.setattr(transfer_service,'NEW_TRANSFER_VERSION',2)
        origin=monthly.origin(client)
    order=monthly.clear(client,origin,60)
    monthly.cmd(client,order,'pay',monthly.payvalues(client,order),kind='clearing')
    transfer.switch(client,1);monthly.cmd(client,order,'receive',monthly.payvalues(client,order),kind='clearing')
    target=tmp_path/'nonempty-l248.sqlite';url='sqlite:///'+target.as_posix()
    config=Config('alembic.ini');config.attributes['url_override']=url
    command.upgrade(config,'l248_business_entities')
    old=make_engine(url)
    try:
        existing=set(inspect(old).get_table_names())
        historical=MetaData();historical.reflect(old)
        # Freeze the old columns for both copying and every later comparison.
        copied=[table for table in historical.sorted_tables if table.name!='alembic_version']
        with engine.connect() as source,old.begin() as destination:
            for table in copied:
                rows=list(source.execute(select(table)).mappings())
                if rows:destination.execute(table.insert(),[dict(row) for row in rows])
        with old.connect() as connection:before={table.name:table_fingerprint(connection,table) for table in copied}
        with sqlite3.connect(target) as db:
            assert validate_sqlite(db)['verified_clearing_orders']==1
            assert 'transfer_exceptions' not in existing
            assert db.execute('SELECT status,amount_cents FROM interstore_clearing_orders').fetchall()==[('settled',60)]
            assert db.execute("SELECT direction,amount_cents FROM cash_entries WHERE category='interstore_clearing' ORDER BY direction").fetchall()==[('in',60),('out',60)]
        command.upgrade(config,'m359_transfer_exceptions')
        with old.connect() as connection:assert before=={table.name:table_fingerprint(connection,table) for table in copied}
        assert 'material_loss' in next(row['sqltext'] for row in inspect(old).get_check_constraints('interstore_clearing_buckets') if row['name']=='ck_clearing_parties')
        with sqlite3.connect(target) as db:
            result=validate_sqlite(db)
            assert result['verified_clearing_orders']==1 and result['transport_losses']==0
            assert db.execute('SELECT COUNT(*) FROM transfer_exceptions').fetchone()[0]==0
            assert not db.execute('PRAGMA foreign_key_check').fetchone()
        command.upgrade(config,'head')
        with old.connect() as connection:
            assert before=={table.name:table_fingerprint(connection,table) for table in copied}
        check=next(row['sqltext'] for row in inspect(old).get_check_constraints('interstore_clearing_buckets') if row['name']=='ck_clearing_parties')
        assert 'material_loss' in check and 'material_found' in check
        with sqlite3.connect(target) as db:
            result=validate_sqlite(db)
            assert result['verified_clearing_orders']==1 and result['found_goods_postings']==0
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]==__import__('alembic.script', fromlist=['ScriptDirectory']).ScriptDirectory.from_config(config).get_current_head()
            assert not db.execute('PRAGMA foreign_key_check').fetchone()
    finally:old.dispose()
