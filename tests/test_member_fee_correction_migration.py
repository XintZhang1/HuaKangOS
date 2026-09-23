"""A populated d02q upgrade preserves original renewal contracts and receipts."""
import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR
from tests import test_member_fee_corrections as fee


TABLES=('membership_fee_correction_requests','membership_fee_corrections','membership_fee_refund_bases')


def quoted(name):return '"'+name.replace('"','""')+'"'


def snapshot(connection,tables):
    return {table:connection.execute('SELECT * FROM '+quoted(table)+' ORDER BY rowid').fetchall() for table in tables}


def test_nonempty_d02q_to_e13r_preserves_original_fee_period_cash_and_blob(client,tmp_path):
    data=fee.setup_paid(client)
    root=Path(__file__).resolve().parents[1];candidate=tmp_path/'nonempty-d02q-to-e13r.sqlite'
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
    cfg.attributes['url_override']='sqlite:///'+candidate.as_posix()
    command.upgrade(cfg,'d02q_partial_corrections')
    with sqlite3.connect(candidate) as old,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name")]
        assert not set(TABLES)&set(tables)
        # Reuse real API facts, projecting only columns available in the old schema.
        for table in tables:
            columns=[r[1] for r in old.execute('PRAGMA table_info('+quoted(table)+')')]
            actual_columns={r[1] for r in actual.execute('PRAGMA table_info('+quoted(table)+')')}
            assert set(columns)<=actual_columns
            names=','.join(map(quoted,columns));entries=actual.execute('SELECT '+names+' FROM '+quoted(table)).fetchall()
            if entries:old.executemany('INSERT INTO '+quoted(table)+' ('+names+') VALUES ('+','.join('?' for _ in columns)+')',entries)
        assert old.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert old.execute('SELECT COUNT(*) FROM membership_periods').fetchone()[0]==2
        assert old.execute('SELECT COUNT(*) FROM membership_fees').fetchone()[0]==1
        assert old.execute('SELECT cash_id,amount_cents FROM membership_fees WHERE id=?',(data['fee_id'],)).fetchone()==(data['original_cash_id'],19900)
        assert old.execute('SELECT COUNT(*),SUM(amount_cents) FROM cash_entries').fetchone()==(1,19900)
        blobs=old.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall()
        assert blobs and all(isinstance(content,bytes) and content for _,content in blobs)
        before=snapshot(old,tables);old.commit()
    command.upgrade(cfg,'e13r_member_fee_corrections')
    with sqlite3.connect(candidate) as upgraded:
        assert upgraded.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='e13r_member_fee_corrections'
        assert snapshot(upgraded,tables)==before
        assert upgraded.execute('SELECT id,content FROM flow_files ORDER BY id').fetchall()==blobs
        assert all(upgraded.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]==0 for name in TABLES)
        assert upgraded.execute('PRAGMA foreign_key_check').fetchall()==[]
        order_ddl=upgraded.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='business_finance_orders'").fetchone()[0]
        context_ddl=upgraded.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='business_entity_case_contexts'").fetchone()[0]
        assert "'fee_correction'" in order_ddl and "'membership_refund'" in context_ddl
        with sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
            for table in TABLES:
                assert sorted(row[1:] for row in upgraded.execute('PRAGMA table_info('+quoted(table)+')'))==sorted(row[1:] for row in actual.execute('PRAGMA table_info('+quoted(table)+')'))
                assert sorted(row[2:] for row in upgraded.execute('PRAGMA foreign_key_list('+quoted(table)+')'))==sorted(row[2:] for row in actual.execute('PRAGMA foreign_key_list('+quoted(table)+')'))
        assert validate_sqlite(upgraded)['integrity']=='ok'
