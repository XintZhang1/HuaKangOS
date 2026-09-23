"""Nonempty b80o history survives literal c91p schema then actual new purchase."""
import sqlite3
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData,select,inspect
from app.db import engine,make_engine,SessionLocal,Base
from app.repair_package_integrity import validate,TABLES
from app.backup_integrity import validate_sqlite
from scripts.migrate_database import table_fingerprint
from tests import test_repair_orders as repair,test_repair_packages as package
from tests.conftest import login
technician=repair.technician

def test_nonempty_b80o_upgrade_retains_original_cash_stock_evidence_then_issues_real_package(client,tmp_path):
    row,item,work,customer=repair.setup(client);row=repair.allocate(client,repair.ready(client,row,item,work));repair.receive(client,row,row['allocations'][0],10997,repair.bank(client))
    path=tmp_path/'historical-b80o.sqlite';url='sqlite:///'+path.as_posix();cfg=Config('alembic.ini');cfg.attributes['url_override']=url
    command.upgrade(cfg,'b80o_member_pricing');upgraded=make_engine(url);history=MetaData();history.reflect(upgraded);tables=[t for t in history.sorted_tables if t.name!='alembic_version']
    try:
        with upgraded.connect() as target:
            target.exec_driver_sql('PRAGMA foreign_keys=OFF');target.commit()
            with target.begin(),engine.connect() as source:
                for table in tables:
                    rows=[dict(r) for r in source.execute(select(table)).mappings()]
                    if rows:target.execute(table.insert(),rows)
                assert target.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            target.exec_driver_sql('PRAGMA foreign_keys=ON');target.commit();before={t.name:table_fingerprint(target,t) for t in tables}
        with sqlite3.connect(path) as connection:
            blobs=connection.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall();assert blobs and all(isinstance(b,bytes) for _,b in blobs)
            assert validate(connection)['verified_repair_package_purchases']==0
        command.upgrade(cfg,'c91p_repair_packages')
        with upgraded.connect() as connection:
            assert before=={t.name:table_fingerprint(connection,t) for t in tables}
            assert all(connection.exec_driver_sql('SELECT COUNT(*) FROM '+name).scalar()==0 for name in TABLES)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
        schema=inspect(upgraded)
        for name in TABLES:
            assert {c['name'] for c in schema.get_columns(name)}==set(Base.metadata.tables[name].columns.keys()),name
            assert {c['name'] for c in schema.get_check_constraints(name)}=={c.name for c in Base.metadata.tables[name].constraints if c.__class__.__name__=='CheckConstraint'},name
        with sqlite3.connect(path) as connection:assert validate_sqlite(connection)['integrity']=='ok'
        SessionLocal.configure(bind=upgraded);login(client);data=package.fixture(client)
        assert package.info(client,data)['status']=='issued'
        with sqlite3.connect(path) as connection:
            assert validate_sqlite(connection)['verified_repair_package_purchases']==1
            assert connection.execute('SELECT id,content FROM flow_files WHERE id<=? ORDER BY id',(blobs[-1][0],)).fetchall()==blobs
    finally:SessionLocal.configure(bind=engine);upgraded.dispose()
