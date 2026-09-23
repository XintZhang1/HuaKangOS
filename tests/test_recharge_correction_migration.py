"""Nonempty z68m upgrade preserves original gifts and actual refunds."""
import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR,login
from tests import test_recharge_bundles as rb
from tests.test_finance_correction_migrations import quoted


def test_nonempty_z68m_to_a79n_keeps_old_wallet_units_and_cash_exactly(client,tmp_path):
    a,z,member,rule,purchase=rb.setup(client);login(client,'finance')
    refund=rb.approve(client,rb.refund(client,a,purchase))
    rb.command(client,refund,'execute',rb.proof(client,refund,account_id=a['account_id'],reference='MIGRATION-ORIGINAL-ACTUAL-REFUND'))
    root=Path(__file__).resolve().parents[1];candidate=tmp_path/'nonempty-z68m-a79n.sqlite'
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
    cfg.attributes['url_override']='sqlite:///'+candidate.as_posix();command.upgrade(cfg,'z68m_rework_extensions')
    with sqlite3.connect(candidate) as old,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name")]
        columns={table:[r[1] for r in old.execute('PRAGMA table_info('+quoted(table)+')')] for table in tables}
        for table,names in columns.items():
            fields=','.join(map(quoted,names));values=actual.execute('SELECT '+fields+' FROM '+quoted(table)).fetchall()
            if values:old.executemany('INSERT INTO '+quoted(table)+' ('+fields+') VALUES ('+','.join('?' for _ in names)+')',values)
        assert old.execute('SELECT COUNT(*) FROM benefit_wallets').fetchone()[0]==4
        assert old.execute('SELECT COUNT(*) FROM cash_entries').fetchone()[0]==2
        assert old.execute('PRAGMA foreign_key_check').fetchall()==[]
        before={t:old.execute('SELECT '+','.join(map(quoted,names))+' FROM '+quoted(t)+' ORDER BY rowid').fetchall() for t,names in columns.items()};old.commit()
    command.upgrade(cfg,'a79n_recharge_corrections')
    with sqlite3.connect(candidate) as upgraded:
        assert {t:upgraded.execute('SELECT '+','.join(map(quoted,names))+' FROM '+quoted(t)+' ORDER BY rowid').fetchall() for t,names in columns.items()}==before
        assert upgraded.execute('SELECT DISTINCT correction_units FROM benefit_wallets').fetchall()==[(0,)]
        assert upgraded.execute('SELECT COUNT(*) FROM business_finance_bundle_corrections').fetchone()[0]==0
        assert upgraded.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='a79n_recharge_corrections'
        assert upgraded.execute('PRAGMA foreign_key_check').fetchall()==[];validate_sqlite(upgraded)
