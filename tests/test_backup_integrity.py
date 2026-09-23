import hashlib
import sqlite3

import pytest
from sqlalchemy import MetaData, Table, Column, Integer, LargeBinary, JSON, create_engine
from app.backup_integrity import validate_sqlite
from scripts.migrate_database import table_fingerprint


def test_backup_verifies_original_file_bytes():
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE flow_files(sha256 TEXT,size INTEGER,content BLOB)')
        content='虚构附件'.encode('utf-8')
        db.execute('INSERT INTO flow_files VALUES(?,?,?)',(hashlib.sha256(content).hexdigest(),len(content),content))
        assert validate_sqlite(db)['verified_files']==1
        db.execute('UPDATE flow_files SET content=?',(b'corrupt',))
        with pytest.raises(ValueError,match='附件'):
            validate_sqlite(db)


def test_backup_refuses_unpaired_internal_settlement():
    with sqlite3.connect(':memory:') as db:
        db.executescript('CREATE TABLE group_entries(id INTEGER); CREATE TABLE group_settlement_entries(id INTEGER,entry_id INTEGER,side TEXT,amount_cents INTEGER); INSERT INTO group_entries VALUES(1); INSERT INTO group_settlement_entries VALUES(1,1,"center",100);')
        with pytest.raises(ValueError,match='配对'):
            validate_sqlite(db)
        db.execute('INSERT INTO group_settlement_entries VALUES(2,1,"store",-100)')
        assert validate_sqlite(db)['integrity']=='ok'


def test_transfer_fingerprint_detects_same_count_different_values_and_files():
    metadata=MetaData()
    table=Table('facts',metadata,Column('id',Integer,primary_key=True),Column('amount',Integer),Column('evidence',LargeBinary),Column('detail',JSON))
    engine=create_engine('sqlite://')
    metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(table.insert(),{'id':1,'amount':100,'evidence':b'original','detail':{'a':1,'b':2}})
        original=table_fingerprint(db,table)
        db.execute(table.update().values(detail={'b':2,'a':1}))
        assert table_fingerprint(db,table)==original
        db.execute(table.update().values(amount=101))
        assert table_fingerprint(db,table)!=original
        db.execute(table.update().values(amount=100,evidence=b'changed!'))
        assert table_fingerprint(db,table)!=original
    engine.dispose()


def test_backup_counts_approved_refund_and_service_holds_together():
    with sqlite3.connect(':memory:') as db:
        db.executescript('''CREATE TABLE group_members(id INTEGER,balance_cents INTEGER,reserved_cents INTEGER);
            CREATE TABLE group_entries(member_id INTEGER,amount_cents INTEGER);
            CREATE TABLE group_reservations(member_id INTEGER,amount_cents INTEGER,status TEXT);
            CREATE TABLE group_refund_requests(member_id INTEGER,amount_cents INTEGER,status TEXT);
            INSERT INTO group_members VALUES(1,100,55); INSERT INTO group_entries VALUES(1,100);
            INSERT INTO group_reservations VALUES(1,30,'reserved');
            INSERT INTO group_refund_requests VALUES(1,25,'approved');''')
        assert validate_sqlite(db)['integrity']=='ok'
        db.execute("UPDATE group_refund_requests SET status='cancelled'")
        with pytest.raises(ValueError,match='占额'):
            validate_sqlite(db)
