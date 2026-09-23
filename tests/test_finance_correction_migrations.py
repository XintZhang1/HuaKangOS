"""Upgrade a populated pre-overpayment schema without changing historical facts."""
import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR,login
from tests import test_finance_corrections as correction,test_business_finance as finance


def quoted(name):return '"'+name.replace('"','""')+'"'


def snapshot(connection,tables):
    return {table:connection.execute('SELECT * FROM '+quoted(table)+' ORDER BY rowid').fetchall() for table in tables}


def test_nonempty_w35j_to_x46k_preserves_original_cash_targets_corrections_and_files(client,tmp_path):
    _,_,customer=finance.ready_retail(client);finance.advance(client,customer,1000)
    account=correction.bank(client);correction.post(client,correction.correction(client,customer,700,account=account))
    login(client);source,_=correction.supplier_target(client)
    revision=correction.approve_target(client,correction.target_adjust(client,source,300),source)
    finance.command(client,revision,'execute',finance.proof(client,revision,source_versions=finance.versions(client,source['case'])))
    root=Path(__file__).resolve().parents[1];candidate=tmp_path/'nonempty-w35j-to-x46k.sqlite'
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'migrations'))
    cfg.attributes['url_override']='sqlite:///'+candidate.as_posix()
    command.upgrade(cfg,'w35j_addon_gifts')
    with sqlite3.connect(candidate) as old,sqlite3.connect(TEST_DIR/'test.sqlite') as actual:
        tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version','sqlite_sequence') ORDER BY name")]
        for table in tables:
            columns=[r[1] for r in old.execute('PRAGMA table_info('+quoted(table)+')')]
            names=','.join(map(quoted,columns));rows=actual.execute('SELECT '+names+' FROM '+quoted(table)).fetchall()
            if rows:old.executemany('INSERT INTO '+quoted(table)+' ('+names+') VALUES ('+','.join('?' for _ in columns)+')',rows)
        assert old.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert old.execute('SELECT COUNT(*) FROM cash_entries').fetchone()[0]==3
        assert old.execute('SELECT COUNT(*) FROM flow_files').fetchone()[0]>0
        assert old.execute('SELECT COUNT(*) FROM business_finance_stored_corrections').fetchone()[0]==1
        assert old.execute('SELECT COUNT(*) FROM business_finance_return_target_revisions').fetchone()[0]==1
        before=snapshot(old,tables);old.commit()
    command.upgrade(cfg,'x46k_supplier_overpayment')
    with sqlite3.connect(candidate) as upgraded:
        assert snapshot(upgraded,tables)==before
        assert upgraded.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='x46k_supplier_overpayment'
        assert upgraded.execute('SELECT COUNT(*) FROM business_finance_supplier_refunds').fetchone()[0]==0
        assert upgraded.execute('PRAGMA foreign_key_check').fetchall()==[]
        validate_sqlite(upgraded)
