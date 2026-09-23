"""Nonempty r80e upgrades without changing original rows, bytes or old receipts."""
import sqlite3
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData,select,inspect
from app.db import Base,engine,make_engine,SessionLocal
from app.dossier_grant_integrity import validate,TABLES
from scripts.migrate_database import table_fingerprint
from tests.test_dossier_grants import API,setup,proposal,decide,switch


def test_nonempty_r80e_to_current_preserves_originals_then_grants_and_restores(client,tmp_path):
    data=setup(client)
    path=tmp_path/'nonempty-original-r80e.sqlite';url='sqlite:///'+path.as_posix()
    cfg=Config('alembic.ini');cfg.attributes['url_override']=url;command.upgrade(cfg,'r80e_vehicle_transport')
    target=make_engine(url);metadata=MetaData();metadata.reflect(target)
    originals=[t for t in metadata.sorted_tables if t.name!='alembic_version']
    try:
        with target.connect() as conn:
            conn.exec_driver_sql('PRAGMA foreign_keys=OFF');conn.commit()
            with conn.begin(),engine.connect() as source:
                for table in originals:
                    records=[dict(r) for r in source.execute(select(table)).mappings()]
                    if records:conn.execute(table.insert(),records)
                assert conn.exec_driver_sql('PRAGMA foreign_key_check').fetchone() is None
            conn.exec_driver_sql('PRAGMA foreign_keys=ON');conn.commit()
        with target.connect() as conn:
            fingerprints={t.name:table_fingerprint(conn,t) for t in originals}
        with sqlite3.connect(path) as conn:
            assert validate(conn)['dossier_grants']==0
            assert conn.execute('SELECT typeof(content) FROM flow_files LIMIT 1').fetchone()[0]=='blob'
        command.upgrade(cfg,'head')
        with target.connect() as conn:
            assert fingerprints=={t.name:table_fingerprint(conn,t) for t in originals}
            assert conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()==ScriptDirectory.from_config(cfg).get_current_head()
        schema=inspect(target)
        for name in TABLES:
            assert {c['name'] for c in schema.get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
            assert {c['name'] for c in schema.get_check_constraints(name)}=={c.name for c in Base.metadata.tables[name].constraints if c.__class__.__name__=='CheckConstraint'}
        SessionLocal.configure(bind=target)
        switch(client,'sales')
        grant,body=proposal(client,data)
        replay=client.post(API,json=body);assert replay.status_code==201 and replay.json()['replayed']
        switch(client,'manager');grant,_=decide(client,grant)
        switch(client,'receiver',2)
        response=client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}')
        assert response.status_code==200 and response.content==b'Synthetic dossier only'
        with sqlite3.connect(path) as conn:
            assert conn.execute('PRAGMA foreign_key_check').fetchone() is None
            assert validate(conn)=={'dossier_grants':1,'dossier_files':1,'dossier_decisions':1,'dossier_accesses':1}
        switch(client,'manager');decide(client,grant,'revoke')
        with sqlite3.connect(path) as conn:
            assert validate(conn)['dossier_decisions']==2
    finally:
        SessionLocal.configure(bind=engine);target.dispose()
