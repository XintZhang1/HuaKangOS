"""Statement definition upgrades preserve old snapshots and capture new fact sources."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User
from app.tenancy import set_scope,project_user
from app import reconciliation_service as service
from tests import test_reconciliation as rec,test_warehouse as wh,test_invoices as inv
from tests.conftest import login


def test_new_statement_contains_actual_blue_minus_red_not_pending_or_cash(client):
    source=inv.source(1000);login(client,'finance');blue=inv.actual(client,source,1000)
    inv.actual(client,source,300,blue['id']);inv.create(client,source,200,blue['id'])
    batch=rec.batch(client)
    assert batch['definition_version']==CURRENT_DEFINITION_VERSION
    assert batch['summary']['invoice_results']['count']==2
    assert batch['summary']['invoice_results']['amount_cents']==700
    assert batch['summary']['period_cash_in_cents']==batch['summary']['period_cash_out_cents']==0
    records=[r for r in batch['manifest'] if r['source']=='invoice_results']
    assert len(records)==2 and {r['basis'] for r in records}=={'period'}
    assert not rec.get(client,batch)['source_changed']


def test_old_statement_definition_remains_stable_then_explicit_successor_observes_bins(client,monkeypatch):
    item,a,b=wh.setup(client);move=wh.create(client,'local_move',item,2000,src=a,dest=b);wh.approve(client,move)
    login(client,'finance');original=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=1:original(db,user,start,end,1))
        old=rec.batch(client)
    assert old['definition_version']==1 and 'warehouse_entries' not in old['summary']
    assert not rec.get(client,old)['source_changed']
    login(client,'admin');wh.command(client,move,'dispatch',{'evidence_id':wh.evidence(client,move)})
    login(client,'finance');assert not rec.get(client,old)['source_changed']
    successor=rec.cmd(client,old,'recalculate',{'reason':'明确采用新来源范围补核对库位及会员票据'})
    assert successor['definition_version']==CURRENT_DEFINITION_VERSION and successor['previous_id']==old['id']
    assert successor['summary']['warehouse_entries']['count']>0
    assert not rec.get(client,successor)['source_changed']
    login(client,'admin');wh.command(client,move,'accept',{'quantity_milli':1000,'evidence_id':wh.evidence(client,move)})
    login(client,'finance');assert rec.get(client,successor)['source_changed']
    rec.cmd(client,successor,'submit',status=409)
    assert rec.get(client,old)['digest']==old['digest']


def test_unknown_statement_definition_is_refused(client):
    import pytest
    from fastapi import HTTPException
    with SessionLocal() as db:
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
        with pytest.raises(HTTPException) as error:service.snapshot(db,user,today(),today(),999)
        assert error.value.status_code==409


def test_nonempty_invoice_difference_restore_and_rehashed_derived_tamper(client,tmp_path):
    import sqlite3,json,pytest
    from tests.conftest import TEST_DIR
    from app.flow_models import Case
    from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
    source=inv.source(1000);login(client,'finance');inv.actual(client,source,1000)
    with SessionLocal() as db:
        row=db.scalar(select(Case).where(Case.id==source));row.amount_cents=700;db.commit()
    batch=rec.batch(client);assert next(x for x in batch['manifest'] if x['source']=='invoice_corrections')['data']['amount_cents']==300
    for field in ('amount','route','definition'):
        path=tmp_path/(field+'.sqlite')
        with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(path) as copied:original.backup(copied)
        with sqlite3.connect(path) as copy:
            validate_reconciliation_sqlite(copy)
            manifest=json.loads(json.dumps(batch['manifest']));summary=dict(batch['summary'])
            entry=next(x for x in manifest if x['source']=='invoice_corrections')
            if field=='amount':entry['data']['amount_cents']+=1
            elif field=='route':entry['data']['route']['id']=batch['case_id']
            else:summary['definition_version']=1
            hashed=service.digest({'manifest':manifest,'summary':summary})
            copy.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                (json.dumps(manifest),json.dumps(summary),hashed,batch['id']));copy.commit()
            with pytest.raises(ValueError):validate_reconciliation_sqlite(copy)
