"""Historical nonempty upgrade, untouched cash/files, and independent recovery rejection."""
import sqlite3
import pytest
from alembic import command as migration
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData,select,inspect
from app.db import Base,engine,make_engine,SessionLocal
from app.procurement_prepayment_integrity import validate,TABLES
from app.backup_integrity import validate_sqlite
from scripts.migrate_database import table_fingerprint
from tests.conftest import login
from tests import test_procurement as p
from tests import test_procurement_prepayments as a


def test_nonempty_u13h_upgrade_preserves_original_cash_stock_files_then_explicit_new_prepayment(client,tmp_path):
    old,_,_=p.setup(client);old=p.command(client,old,'approve');old=p.receive(client,old)
    account=p.bank(client);old=p.pay(client,old,account,309)
    target,_,_=p.setup(client);target=p.command(client,target,'approve')
    path=tmp_path/'old-u13h.sqlite';url='sqlite:///'+path.as_posix()
    cfg=Config('alembic.ini');cfg.attributes['url_override']=url;migration.upgrade(cfg,'u13h_finance_corrections')
    upgraded=make_engine(url);meta=MetaData();meta.reflect(upgraded)
    history=[t for t in meta.sorted_tables if t.name!='alembic_version']
    try:
        with upgraded.connect() as db:
            db.exec_driver_sql('PRAGMA foreign_keys=OFF');db.commit()
            with db.begin(),engine.connect() as source:
                for table in history:
                    records=[dict(r) for r in source.execute(select(table)).mappings()]
                    if records:db.execute(table.insert(),records)
                assert db.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            db.exec_driver_sql('PRAGMA foreign_keys=ON');db.commit()
            originals={t.name:table_fingerprint(db,t) for t in history}
            assert db.exec_driver_sql('SELECT SUM(amount_cents) FROM cash_entries').scalar()==309
            assert db.exec_driver_sql('SELECT SUM(value_cents) FROM flow_stock_moves').scalar()==309
        with sqlite3.connect(path) as db:
            assert validate(db)['verified_procurement_prepayments']==0
            assert validate_sqlite(db)['integrity']=='ok'
            original_files=db.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall()
            assert original_files and all(isinstance(content,bytes) for _,content in original_files)
        migration.upgrade(cfg,'head')
        with upgraded.connect() as db:
            assert originals=={t.name:table_fingerprint(db,t) for t in history}
            assert db.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()==ScriptDirectory.from_config(cfg).get_current_head()
            assert all(db.exec_driver_sql('SELECT COUNT(*) FROM '+table).scalar()==0 for table in TABLES)
        for table in TABLES:
            assert {c['name'] for c in inspect(upgraded).get_columns(table)}==set(Base.metadata.tables[table].columns.keys())
        SessionLocal.configure(bind=upgraded)
        login(client,'finance');a.request(client,old,1,status=409)
        target=a.request(client,target,200)
        login(client,'manager');target=a.decide(client,target)
        login(client,'finance');target=a.advance(client,target,account,200)
        login(client,'inventory');p.receive(client,target,[{'line_id':target['lines'][0]['id'],'quantity_milli':1000}])
        login(client,'manager');target=p.command(client,target,'close_receiving',{'reason':'明确终止未到采购余量'})
        login(client,'finance');a.refund(client,target,target['payments'][0]['id'],77,account)
        with sqlite3.connect(path) as db:
            assert validate(db)['verified_procurement_prepayments']==1
            assert validate_sqlite(db)['integrity']=='ok'
            assert db.execute('PRAGMA foreign_key_check').fetchone() is None
            assert db.execute('SELECT id,content FROM flow_files WHERE id<=? ORDER BY id',(original_files[-1][0],)).fetchall()==original_files
            assert db.execute("SELECT SUM(amount_cents*(CASE direction WHEN 'out' THEN 1 ELSE -1 END)) FROM cash_entries").fetchone()[0]==432
            assert db.execute('SELECT SUM(value_cents) FROM flow_stock_moves').fetchone()[0]==432
    finally:
        SessionLocal.configure(bind=engine);upgraded.dispose()


def test_procurement_prepayment_restore_detects_original_source_missing_and_tampered(client):
    row,_,account=a.approved(client);a.advance(client,row,account,200)
    login(client,'inventory');p.receive(client,row)
    login(client,'finance');row=p.detail(client,row)
    with sqlite3.connect(engine.url.database) as source:
        assert validate(source)['verified_procurement_prepayments']==1
        for statement in [
            'UPDATE procurement_prepayment_requests SET amount_cents=amount_cents+1',
            'UPDATE procurement_prepayment_requests SET store_id=2',
            "UPDATE procurement_prepayment_requests SET reason='改写原申请'",
            'UPDATE procurement_prepayment_decisions SET actor_id=(SELECT requested_by FROM procurement_prepayment_requests LIMIT 1)',
            'DELETE FROM procurement_prepayment_disbursements',
            'UPDATE procurement_prepayment_disbursements SET payment_id=999',
            'DELETE FROM procurement_payment_allocations',
            'UPDATE procurement_payment_allocations SET amount_cents=amount_cents+1',
            'UPDATE procurement_payments SET amount_cents=amount_cents+1',
            "DELETE FROM flow_events WHERE action='procurement_prepay_pay'",
            'DROP TABLE procurement_prepayment_requests',
        ]:
            with sqlite3.connect(':memory:') as copied:
                source.backup(copied);copied.execute(statement)
                with pytest.raises(ValueError,match='采购预付款恢复检查'):validate(copied)


def test_procurement_prepayment_partial_schema_fails_closed():
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE procurement_prepayment_requests(id INTEGER)')
        with pytest.raises(ValueError,match='来源表不完整'):validate(db)
