"""Nonempty historical-head upgrade and offline source corruption checks."""
import copy,json,sqlite3,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import select,text,MetaData,inspect
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db import engine,SessionLocal,make_engine,Base,today
from app.backup_integrity import validate_sqlite
from app.vehicle_transport_integrity import validate_vehicle_transport,DOMAIN_TABLES
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
from tests import test_vehicle_transport as v
from tests import test_vehicle_transport_finance as f
from tests import test_gate_visits as g
from tests import test_reconciliation as m


def test_nonempty_q79d_to_current_preserves_originals_replays_then_real_loss_found(client,tmp_path):
    gate=g.entered(client)
    car,locations=v.seed();parent=v.old.approved(client,car)
    values=v.old.proof_values(client,parent);before_version=v.old.get(client,parent);request_id=uuid.uuid4().hex
    dispatched=v.old.command(client,parent,'dispatch',values,key=request_id,original=before_version)
    path=tmp_path/'old-q79d.sqlite';url='sqlite:///'+path.as_posix()
    cfg=Config('alembic.ini');cfg.attributes['url_override']=url;command.upgrade(cfg,'q79d_gate_visits')
    upgraded=make_engine(url);meta=MetaData();meta.reflect(upgraded)
    old_tables=[t for t in meta.sorted_tables if t.name!='alembic_version']
    from scripts.migrate_database import table_fingerprint
    try:
        with upgraded.connect() as target:
            target.exec_driver_sql('PRAGMA foreign_keys=OFF');target.commit()
            with target.begin(),engine.connect() as source:
                for table in old_tables:
                    records=[dict(row) for row in source.execute(select(table)).mappings()]
                    if records:target.execute(table.insert(),records)
                assert target.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            target.exec_driver_sql('PRAGMA foreign_keys=ON');target.commit()
        with upgraded.connect() as db:originals={t.name:table_fingerprint(db,t) for t in old_tables}
        with sqlite3.connect(path) as db:
            assert validate_vehicle_transport(db)['verified_vehicle_transport_exceptions']==0
            assert db.execute('SELECT typeof(content) FROM flow_files LIMIT 1').fetchone()[0]=='blob'
            assert validate_sqlite(db)['integrity']=='ok'
        command.upgrade(cfg,'head')
        with upgraded.connect() as db:
            assert originals=={t.name:table_fingerprint(db,t) for t in old_tables}
            assert db.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()==ScriptDirectory.from_config(cfg).get_current_head()
        for name in DOMAIN_TABLES:
            assert {c['name'] for c in inspect(upgraded).get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
        SessionLocal.configure(bind=upgraded);v.as_user(client,'inventory',1)
        assert v.old.command(client,parent,'dispatch',values,key=request_id,original=before_version)==dispatched
        current=v.old.get(client,parent)
        response=client.post(v.API,json={'request_id':uuid.uuid4().hex,'transfer_id':parent['id'],'version':current['version'],
            'case_version':current['case_version'],'kind':'missing','evidence_id':v.old.upload(client,parent),'reason':'升级后本人发现原车失联按原调拨核对'})
        assert response.status_code==201,response.text;row=response.json()
        v.observations(client,row);v.propose_loss(client,row);v.approve_both(client,row)
        v.as_user(client,'finance',1);v.act(client,row,'post_loss',{'confirmed':True,'evidence_id':v.evidence(client,row,True),'reason':'依据双方核实的原成本确认本笔实际损失'})
        v.found_plan(client,row,2);v.as_user(client,'inventory',2)
        v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[2],'evidence_id':v.evidence(client,row),'reason':'升级后原车后来实际找到并按原VIN验收入库'})
        v.as_user(client,'finance',1);batch=m.batch(client);assert batch['definition_version']==CURRENT_DEFINITION_VERSION
        with sqlite3.connect(path) as db:
            checks=validate_sqlite(db);assert checks['integrity']=='ok'
            assert checks['verified_vehicle_transport_losses']==checks['verified_vehicle_transport_found']==1
            assert checks['verified_gate_visits']==1
            assert db.execute('PRAGMA foreign_key_check').fetchone() is None
        v.as_user(client,'admin',1);g.cmd(client,gate,'leave',g.actual(client,gate,g.at(0)))
        with sqlite3.connect(path) as db:assert validate_sqlite(db)['integrity']=='ok'
    finally:
        SessionLocal.configure(bind=engine);upgraded.dispose()


def _damaged_copy(tmp_path,statement,params=None):
    path=tmp_path/'damaged.sqlite'
    with sqlite3.connect(engine.url.database) as source,sqlite3.connect(path) as target:source.backup(target)
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA ignore_check_constraints=ON')
        db.execute(statement,params or {});db.commit()
        db.execute('PRAGMA ignore_check_constraints=OFF')
        with pytest.raises(ValueError):validate_vehicle_transport(db)
        with pytest.raises(ValueError):validate_sqlite(db)


@pytest.mark.parametrize('statement',[
 "UPDATE vehicle_transport_losses SET value_cents=value_cents+1",
 "UPDATE vehicle_transport_losses SET source_bearer_cents=source_bearer_cents+1",
 "UPDATE vehicle_transport_losses SET store_id=2",
 "UPDATE vehicle_transport_loss_settlements SET amount_cents=amount_cents+1 WHERE store_id=2",
 "UPDATE vehicle_transport_plans SET source_observation_id=destination_observation_id",
 "UPDATE vehicle_transport_plans SET origin_digest='tampered-original-digest'",
 "UPDATE vehicle_transport_observations SET vin='LFV2A21K9J7654321' WHERE kind='dispatch_verified'",
 "UPDATE vehicle_transport_observations SET actual_at='2999-01-01T00:00:00'",
 "UPDATE vehicle_transport_reviews SET actor_id=(SELECT requested_by FROM vehicle_transport_exceptions LIMIT 1)",
 "UPDATE vehicle_transport_reviews SET evidence_id=(SELECT evidence_id FROM vehicle_transport_reviews WHERE store_id=1) WHERE store_id=2",
 "UPDATE vehicle_transport_exceptions SET status='resolved',active_transfer_id=NULL",
 "DELETE FROM vehicle_transport_loss_settlements WHERE store_id=2",
 "DELETE FROM flow_events WHERE action='vehicle_transport_post_loss'",
])
def test_loss_original_attribution_or_independent_fact_tampering_rejected(client,tmp_path,statement):
    v.posted(client);v.verify_transport();_damaged_copy(tmp_path,statement)


@pytest.mark.parametrize('statement',[
 "UPDATE vehicle_transport_found_receipts SET value_cents=value_cents+1",
 "UPDATE vehicle_transport_found_receipts SET location_id=(SELECT id FROM master_locations WHERE store_id=3 LIMIT 1)",
 "UPDATE vehicle_transport_found_receipts SET vehicle_id=(SELECT source_vehicle_id FROM vehicle_transfers LIMIT 1)",
 "UPDATE vehicle_transport_found_settlements SET amount_cents=amount_cents+1 WHERE store_id=1",
 "UPDATE vehicles SET purchase_cost_cents=purchase_cost_cents+1 WHERE inventory_generation=1",
 "UPDATE vehicle_transport_found_receipts SET evidence_id=(SELECT evidence_id FROM vehicle_transport_losses LIMIT 1)",
 "DELETE FROM vehicle_position_entries WHERE kind='transfer_receive'",
 "DELETE FROM flow_events WHERE action='vehicle_transport_found_receive'",
])
def test_found_original_generation_cost_evidence_tampering_rejected(client,tmp_path,statement):
    _,row,_,locations=v.posted(client);v.found_plan(client,row,2);v.as_user(client,'inventory',2)
    v.act(client,row,'found_receive',{'confirmed':True,'vin':v.old.VIN,'location_id':locations[2],'evidence_id':v.evidence(client,row),'reason':'本人按原VIN核对找回实车并入库'})
    v.verify_transport(found=1);_damaged_copy(tmp_path,statement)


@pytest.mark.parametrize('statement',[
 "UPDATE vehicle_transport_claim_plans SET target_cents=target_cents+1",
 "UPDATE vehicle_transport_claim_payments SET amount_cents=amount_cents-1",
 "UPDATE vehicle_transport_claim_payments SET account_id=999999",
 "UPDATE vehicle_transport_claim_payments SET business_date='1999-01-01'",
 "UPDATE vehicle_transport_claims SET counterparty_snapshot='{}'",
 "UPDATE vehicle_transport_claim_reviews SET actor_id=(SELECT actor_id FROM vehicle_transport_claim_plans LIMIT 1)",
 "DELETE FROM flow_events WHERE action='vehicle_transport_recovery_receive'",
 "UPDATE cash_entries SET amount_cents=amount_cents-1 WHERE category='workflow_vehicle_loss_recovery'",
])
def test_claim_money_targets_and_full_original_fact_events_are_checked(client,tmp_path,statement):
    _,row,_,_=v.posted(client);account=f.account(client,1);claim=f.claim(client,row)
    f.approve(client,row,claim['id']);f.cash(client,row,claim['id'],account)
    v.verify_transport();_damaged_copy(tmp_path,statement)


def test_partially_missing_vehicle_extension_is_not_an_empty_old_database(client,tmp_path):
    path=tmp_path/'partial.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE vehicle_transport_exceptions(id INTEGER)')
        with pytest.raises(ValueError,match='不完整'):validate_vehicle_transport(db)


def test_vehicle_pages_original_links_explicit_confirmation_and_scope_reset(client):
    home=client.get('/').text;script=client.get('/static/vehicletransport.js').text
    assert '/static/vehicletransport.js' in home
    assert 'name="confirmed" required' in script and 'name="confirmed" checked' not in script
    assert 'v.confirmed=form.elements.confirmed.checked' in script and 'autocomplete="off"' in script
    assert 'exception_version:r.exception_version' in script and 'claim_version:c.version' in script
    assert 'original_id:original.id,account_id:original.account_id' in script
    application=client.get('/static/app.js').text
    assert "type==='vehicle-transport-exceptions'" in application
    assert application.count('clearVehicleTransportSession();')>=2
    assert 'vt-new' in client.get('/static/vehicletransfers.js').text
    reconcile=client.get('/static/reconciliation.js').text
    assert 'active_vehicle_exception_id' in reconcile and 'vehicle_transport_claim_payments' in reconcile
