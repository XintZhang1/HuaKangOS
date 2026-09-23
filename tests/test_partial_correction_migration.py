"""The c91p original refund data survives d02q without invented correction slices."""
import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR
from tests.test_finance_correction_migrations import quoted
from tests.test_partial_receipt_corrections import refunded_repair


def test_nonempty_c91p_to_d02q_preserves_all_original_cash_and_business_fields(client,tmp_path):
    refunded_repair(client)
    root=Path(__file__).resolve().parents[1];candidate=tmp_path/'nonempty-c91p-d02q.sqlite'
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
    cfg.attributes['url_override']='sqlite:///'+candidate.as_posix();command.upgrade(cfg,'c91p_repair_packages')
    with sqlite3.connect(candidate) as old,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name")]
        columns={t:[r[1] for r in old.execute('PRAGMA table_info('+quoted(t)+')')] for t in tables}
        for table,names in columns.items():
            fields=','.join(map(quoted,names));values=actual.execute('SELECT '+fields+' FROM '+quoted(table)).fetchall()
            if values:old.executemany('INSERT INTO '+quoted(table)+' ('+fields+') VALUES ('+','.join('?' for _ in names)+')',values)
        assert old.execute('SELECT COUNT(*) FROM aftercare_cash_refunds').fetchone()[0]==1
        assert old.execute('SELECT COUNT(*) FROM cash_entries').fetchone()[0]==2
        assert old.execute('PRAGMA foreign_key_check').fetchall()==[]
        before={t:old.execute('SELECT '+','.join(map(quoted,names))+' FROM '+quoted(t)+' ORDER BY rowid').fetchall() for t,names in columns.items()};old.commit()
    command.upgrade(cfg,'d02q_partial_corrections')
    with sqlite3.connect(candidate) as upgraded:
        assert {t:upgraded.execute('SELECT '+','.join(map(quoted,names))+' FROM '+quoted(t)+' ORDER BY rowid').fetchall() for t,names in columns.items()}==before
        assert upgraded.execute('SELECT COUNT(*) FROM business_finance_correction_bases').fetchone()[0]==0
        assert upgraded.execute('SELECT COUNT(*) FROM business_finance_correction_refund_slices').fetchone()[0]==0
        assert upgraded.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='d02q_partial_corrections'
        assert upgraded.execute('PRAGMA foreign_key_check').fetchall()==[];validate_sqlite(upgraded)
