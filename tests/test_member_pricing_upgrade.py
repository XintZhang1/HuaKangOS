"""Nonempty a79n to b80o: old ledgers and evidence remain byte-equivalent."""
import sqlite3
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData,select,inspect
from app.db import engine,make_engine,SessionLocal,Base
from app.member_pricing_integrity import validate
from app.backup_integrity import validate_sqlite
from scripts.migrate_database import table_fingerprint
from tests import test_repair_orders as repair,test_member_pricing as pricing
from tests.conftest import login
technician=repair.technician
TABLES=tuple('member_pricing_'+n for n in ('rules','scopes','decisions','snapshots','lines','authorizations'))

def test_nonempty_a79n_upgrade_preserves_original_stock_cash_and_evidence_then_new_rule(client,tmp_path):
    row,item,work,customer=repair.setup(client);row=repair.ready(client,row,item,work);row=repair.allocate(client,row);repair.receive(client,row,row['allocations'][0],10997,repair.bank(client))
    path=tmp_path/'historical-a79n.sqlite';url='sqlite:///'+path.as_posix();cfg=Config('alembic.ini');cfg.attributes['url_override']=url
    command.upgrade(cfg,'a79n_recharge_corrections');upgraded=make_engine(url);history=MetaData();history.reflect(upgraded);tables=[t for t in history.sorted_tables if t.name!='alembic_version']
    try:
        with upgraded.connect() as target:
            target.exec_driver_sql('PRAGMA foreign_keys=OFF');target.commit()
            with target.begin(),engine.connect() as source:
                for table in tables:
                    rows=[dict(r) for r in source.execute(select(table)).mappings()]
                    if rows:target.execute(table.insert(),rows)
                assert target.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            target.exec_driver_sql('PRAGMA foreign_keys=ON');target.commit();fingerprints={t.name:table_fingerprint(target,t) for t in tables}
        with sqlite3.connect(path) as connection:
            blobs=connection.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall();assert blobs and all(isinstance(b,bytes) for _,b in blobs);assert validate(connection)['verified_member_pricing_rules']==0
        command.upgrade(cfg,'b80o_member_pricing')
        with upgraded.connect() as connection:
            assert fingerprints=={t.name:table_fingerprint(connection,t) for t in tables};assert all(connection.exec_driver_sql('SELECT COUNT(*) FROM '+name).scalar()==0 for name in TABLES)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
        schema=inspect(upgraded)
        for name in TABLES:
            assert {c['name'] for c in schema.get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
            assert {c['name'] for c in schema.get_check_constraints(name)}=={c.name for c in Base.metadata.tables[name].constraints if c.__class__.__name__=='CheckConstraint'}
        with sqlite3.connect(path) as connection:assert validate_sqlite(connection)['integrity']=='ok'
        SessionLocal.configure(bind=upgraded);login(client);level=pricing.member(client,customer);pricing.rule(client,level,[pricing.scope('repair','work',work,8000)])
        with sqlite3.connect(path) as connection:
            assert validate(connection)['verified_member_pricing_rules']==1 and validate_sqlite(connection)['integrity']=='ok'
            assert connection.execute('SELECT id,content FROM flow_files WHERE id<=? ORDER BY id',(blobs[-1][0],)).fetchall()==blobs
    finally:SessionLocal.configure(bind=engine);upgraded.dispose()
