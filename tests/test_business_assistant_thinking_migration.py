"""Append-only f24s to g35t upgrade preserves messages and independent restores."""
from pathlib import Path
import sqlite3
from alembic import command
from alembic.config import Config
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR
from tests.test_business_assistant_migration import quoted,indexes


def test_new_boolean_default_compiles_for_postgresql_without_connecting(monkeypatch):
    import importlib.util
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateColumn
    from app.business_assistant_models import AssistantMessage
    path=Path(__file__).resolve().parents[1]/'migrations/versions/g35t_assistant_thinking.py'
    spec=importlib.util.spec_from_file_location('assistant_thinking_migration_check',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    captured=[];monkeypatch.setattr(module.op,'add_column',lambda table,column:captured.append((table,column)))
    module.upgrade()
    assert captured[0][0]=='business_assistant_messages'
    for column in (captured[0][1],AssistantMessage.__table__.c.thinking):
        ddl=str(CreateColumn(column).compile(dialect=postgresql.dialect()))
        assert 'BOOLEAN DEFAULT false NOT NULL' in ddl


def test_nonempty_f24s_thinking_default_and_independent_restore(client,tmp_path):
    root=Path(__file__).resolve().parents[1];path=tmp_path/'thinking-upgrade.sqlite'
    config=Config(str(root/'alembic.ini'));config.set_main_option('script_location',str(root/'migrations'))
    config.attributes['url_override']='sqlite:///'+path.as_posix();command.upgrade(config,'f24s_business_assistant')
    with sqlite3.connect(path) as old,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        for table in ('stores','users','user_stores'):
            cols=[r[1] for r in old.execute('PRAGMA table_info('+quoted(table)+')')]
            names=','.join(map(quoted,cols));rows=actual.execute('SELECT '+names+' FROM '+quoted(table)).fetchall()
            old.executemany('INSERT INTO '+quoted(table)+' ('+names+') VALUES ('+','.join('?' for _ in cols)+')',rows)
        admin=old.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        old.execute("INSERT INTO business_assistant_sessions (id,store_id,owner_id,owner_role,access_version,recent_operation_ids,title,created_at,updated_at,version) VALUES ('synthetic-history',1,?,'admin',1,'[]','原对话','2026-09-24','2026-09-24',1)",(admin,))
        old.execute("INSERT INTO business_assistant_messages (store_id,session_id,request_id,role,content,created_at) VALUES (1,'synthetic-history','synthetic-request-0001','user','原消息保留','2026-09-24')")
        old.execute("INSERT INTO business_assistant_messages (store_id,session_id,request_id,role,content,created_at) VALUES (1,'synthetic-history','synthetic-request-0001:reply','assistant','原回复保留','2026-09-24')")
        tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence')")]
        columns={t:[r[1] for r in old.execute('PRAGMA table_info('+quoted(t)+')')] for t in tables}
        before={t:old.execute('SELECT '+','.join(map(quoted,cols))+' FROM '+quoted(t)+' ORDER BY rowid').fetchall() for t,cols in columns.items()}
        old.commit()
    command.upgrade(config,'g35t_assistant_thinking')
    restored=tmp_path/'thinking-independent.sqlite'
    with sqlite3.connect(path) as upgraded,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        after={t:upgraded.execute('SELECT '+','.join(map(quoted,cols))+' FROM '+quoted(t)+' ORDER BY rowid').fetchall() for t,cols in columns.items()}
        assert after==before
        assert upgraded.execute('SELECT thinking FROM business_assistant_messages').fetchall()==[(0,),(0,)]
        assert sorted(row[1:] for row in upgraded.execute('PRAGMA table_info(business_assistant_messages)'))==sorted(row[1:] for row in actual.execute('PRAGMA table_info(business_assistant_messages)'))
        assert indexes(upgraded,'business_assistant_messages')==indexes(actual,'business_assistant_messages')
        upgraded.execute("INSERT INTO business_assistant_messages (store_id,session_id,request_id,role,content,created_at,thinking) VALUES (1,'synthetic-history','synthetic-request-0002','user','开启思考','2026-09-24',1)");upgraded.commit()
        assert validate_sqlite(upgraded)['integrity']=='ok'
        with sqlite3.connect(restored) as target:upgraded.backup(target)
    with sqlite3.connect(restored) as copy:
        assert copy.execute('SELECT content,thinking FROM business_assistant_messages ORDER BY id').fetchall()==[('原消息保留',0),('原回复保留',0),('开启思考',1)]
        assert validate_sqlite(copy)['integrity']=='ok'
