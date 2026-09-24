"""Populated e13r upgrade and independent restore preserve all business facts."""
from datetime import timedelta
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import make_engine, utcnow
from app.backup_integrity import validate_sqlite
from app.business_assistant_models import AssistantSession, AssistantMessage, AssistantProposal, AssistantIssue
from app.business_assistant_service import proposal_digest
from tests.conftest import TEST_DIR
from tests import test_member_fee_corrections as fee

TABLES=('business_assistant_sessions','business_assistant_messages','business_assistant_proposals','business_assistant_issues')


def quoted(name):return '"'+name.replace('"','""')+'"'


def snapshot(connection,tables):
    return {table:connection.execute('SELECT * FROM '+quoted(table)+' ORDER BY rowid').fetchall() for table in tables}


def indexes(connection,table):
    return sorted((row[1],row[2],tuple(item[2] for item in connection.execute('PRAGMA index_info('+quoted(row[1])+')')))
                  for row in connection.execute('PRAGMA index_list('+quoted(table)+')'))


def test_nonempty_e13r_to_f24s_and_independent_restore_preserve_business_and_assistant_rows(client,tmp_path):
    data=fee.setup_paid(client)
    root=Path(__file__).resolve().parents[1];candidate=tmp_path/'nonempty-e13r-f24s.sqlite'
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
    cfg.attributes['url_override']='sqlite:///'+candidate.as_posix()
    command.upgrade(cfg,'e13r_member_fee_corrections')
    with sqlite3.connect(candidate) as old,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        tables=[row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name")]
        assert not set(TABLES)&set(tables)
        for table in tables:
            columns=[row[1] for row in old.execute('PRAGMA table_info('+quoted(table)+')')]
            names=','.join(map(quoted,columns));rows=actual.execute('SELECT '+names+' FROM '+quoted(table)).fetchall()
            if rows:old.executemany('INSERT INTO '+quoted(table)+' ('+names+') VALUES ('+','.join('?' for _ in columns)+')',rows)
        assert old.execute('SELECT COUNT(*) FROM flow_customers').fetchone()[0]>0
        assert old.execute('SELECT COUNT(*) FROM flow_cases').fetchone()[0]>0
        assert old.execute('SELECT COUNT(*),SUM(amount_cents) FROM cash_entries').fetchone()==(1,19900)
        blobs=old.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall()
        assert blobs and all(isinstance(content,bytes) and content for _,content in blobs)
        assert old.execute('PRAGMA foreign_key_check').fetchall()==[]
        before=snapshot(old,tables);old.commit()
    command.upgrade(cfg,'f24s_business_assistant')
    with sqlite3.connect(candidate) as upgraded,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        assert upgraded.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='f24s_business_assistant'
        assert snapshot(upgraded,tables)==before
        assert upgraded.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall()==blobs
        for table in TABLES:
            assert upgraded.execute('SELECT COUNT(*) FROM '+quoted(table)).fetchone()[0]==0
            current=[row[1:] for row in actual.execute('PRAGMA table_info('+quoted(table)+')') if not (table=='business_assistant_messages' and row[1]=='thinking')]
            assert sorted(row[1:] for row in upgraded.execute('PRAGMA table_info('+quoted(table)+')'))==sorted(current)
            assert sorted(row[2:] for row in upgraded.execute('PRAGMA foreign_key_list('+quoted(table)+')'))==sorted(row[2:] for row in actual.execute('PRAGMA foreign_key_list('+quoted(table)+')'))
            assert indexes(upgraded,table)==indexes(actual,table)
        assert validate_sqlite(upgraded)['integrity']=='ok'
        admin_id=upgraded.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
    engine=make_engine('sqlite:///'+candidate.as_posix())
    thread_id=str(uuid4());proposal_id=str(uuid4())
    principal=SimpleNamespace(id=admin_id,role='admin',access_version=1)
    payload={'path_args':{'kind':'customers'},'query':{},'body':{'values':{'name':'迁移合成客户'}}}
    digest=proposal_digest(principal,1,'POST /api/flow/master/{kind}',payload)
    with Session(engine) as db:
        db.add(AssistantSession(id=thread_id,store_id=1,owner_id=admin_id,owner_role='admin',access_version=1,title='合成恢复验证'));db.flush()
        # This fixture intentionally remains at the frozen f24s schema; g35t adds
        # thinking later. Do not use today's ORM defaults to write old columns.
        db.execute(text('INSERT INTO business_assistant_messages (store_id,session_id,request_id,role,content,created_at) VALUES (:store,:sid,:rid,:role,:content,:created)'),
            {'store':1,'sid':thread_id,'rid':str(uuid4()),'role':'user','content':'合成资料，请先准备','created':utcnow()})
        db.add(AssistantProposal(id=proposal_id,store_id=1,session_id=thread_id,owner_id=admin_id,owner_role='admin',access_version=1,
            operation_id='POST /api/flow/master/{kind}',label='新增客户',summary='恢复验证，仅准备未办理',payload=payload,digest=digest,
            expires_at=utcnow()+timedelta(minutes=30),idempotent=False))
        db.add(AssistantIssue(store_id=1,session_id=thread_id,owner_id=admin_id,category='input',summary='合成资料缺少客户来源',synthetic=True))
        db.commit()
    engine.dispose()
    restored=tmp_path/'independent-restored.sqlite'
    with sqlite3.connect(candidate) as source,sqlite3.connect(restored) as target:
        all_tables=tables+list(TABLES)
        expected=snapshot(source,all_tables)
        assert snapshot(source,tables)==before
        source.backup(target)
    with sqlite3.connect(restored) as restored_db:
        assert snapshot(restored_db,all_tables)==expected
        assert all(restored_db.execute('SELECT COUNT(*) FROM '+quoted(table)).fetchone()[0]==1 for table in TABLES)
        assert restored_db.execute('SELECT status,digest FROM business_assistant_proposals WHERE id=?',(proposal_id,)).fetchone()==('pending',digest)
        assert restored_db.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall()==blobs
        assert validate_sqlite(restored_db)['integrity']=='ok'
