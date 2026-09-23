"""Nonempty y57l upgrade preserves every old row and private BLOB source."""
import sqlite3
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData,select,inspect
from app.db import engine,make_engine,SessionLocal,Base
from app.rework_extension_integrity import validate,TABLES
from app.backup_integrity import validate_sqlite
from scripts.migrate_database import table_fingerprint
from tests.test_rework_extensions import employee,fixture,converted,quoted
from tests.test_service_intake import normal,work_quote,released
from tests.test_repair_orders import cmd
from tests.conftest import login

def test_nonempty_y57l_upgrade_preserves_cash_vin_original_receipts_and_blob_then_new_contract(client,tmp_path):
    employee('technician','technician',1)
    row,_,_,_,_=normal(client);row,_=work_quote(client,row,1000);row=cmd(client,row,'start',{'result':'升级前真实合成维修开工'});row=released(client,row)
    path=tmp_path/'historical-y57l.sqlite';url='sqlite:///'+path.as_posix();cfg=Config('alembic.ini');cfg.attributes['url_override']=url
    command.upgrade(cfg,'y57l_vehicle_income');upgraded=make_engine(url);history=MetaData();history.reflect(upgraded)
    tables=[t for t in history.sorted_tables if t.name!='alembic_version']
    try:
        with upgraded.connect() as target:
            target.exec_driver_sql('PRAGMA foreign_keys=OFF');target.commit()
            with target.begin(),engine.connect() as source:
                for table in tables:
                    rows=[dict(r) for r in source.execute(select(table)).mappings()]
                    if rows:target.execute(table.insert(),rows)
                assert target.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            target.exec_driver_sql('PRAGMA foreign_keys=ON');target.commit()
            fingerprints={t.name:table_fingerprint(target,t) for t in tables}
            assert target.exec_driver_sql('SELECT SUM(amount_cents) FROM cash_entries').scalar()==1000
        with sqlite3.connect(path) as connection:
            blobs=connection.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall();assert blobs and all(isinstance(v,bytes) for _,v in blobs)
            assert validate(connection)['verified_rework_extensions']==0
        command.upgrade(cfg,'z68m_rework_extensions')
        with upgraded.connect() as connection:
            assert fingerprints=={t.name:table_fingerprint(connection,t) for t in tables}
            assert all(connection.exec_driver_sql('SELECT COUNT(*) FROM '+t).scalar()==0 for t in TABLES)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
        inspector=inspect(upgraded)
        for name in TABLES:
            assert {c['name'] for c in inspector.get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
            assert {c['name'] for c in inspector.get_check_constraints(name)}=={c.name for c in Base.metadata.tables[name].constraints if c.__class__.__name__=='CheckConstraint'}
        with sqlite3.connect(path) as connection:assert validate_sqlite(connection)['integrity']=='ok'
        # The historical z68m checkpoint above is validated independently.
        # Current repair APIs also use later member-pricing/package tables;
        # exercise them only after the copied history reaches the current head.
        command.upgrade(cfg,'head')
        with upgraded.connect() as connection:
            assert fingerprints=={t.name:table_fingerprint(connection,t) for t in tables}
            assert all(connection.exec_driver_sql('SELECT COUNT(*) FROM '+t).scalar()==0 for t in TABLES)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
        with sqlite3.connect(path) as connection:assert validate_sqlite(connection)['integrity']=='ok'
        SessionLocal.configure(bind=upgraded);login(client)
        data=fixture(client,True);repair=converted(client,data);quoted(client,data,repair)
        with sqlite3.connect(path) as connection:
            assert validate(connection)['verified_rework_extensions']==1
            assert validate_sqlite(connection)['integrity']=='ok'
            assert connection.execute('SELECT id,content FROM flow_files WHERE id<=? ORDER BY id',(blobs[-1][0],)).fetchall()==blobs
    finally:SessionLocal.configure(bind=engine);upgraded.dispose()
