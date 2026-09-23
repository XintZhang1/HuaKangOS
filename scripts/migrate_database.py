"""Maintenance-only full transfer to an EMPTY database. Preserves IDs and audit data.
Never run while the source application is accepting writes. Sessions are not copied.
Usage: python scripts/migrate_database.py --source sqlite:///./data/dealer.db --target-env TARGET_DATABASE_URL
"""
import argparse
import os
import sys
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, func, text
from app.db import Base, make_engine
from app import models, flow_models
from app.cli import migrate


def table_fingerprint(connection, table):
    """Compare typed values and binary evidence, not only row counts."""
    def value(item):
        if isinstance(item, (bytes, bytearray, memoryview)):
            return {'bytes':len(item),'sha256':hashlib.sha256(item).hexdigest()}
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return format(item, 'f')
        return item
    digest=hashlib.sha256()
    rows=connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
    for row in rows:
        data={key:value(item) for key,item in row.items()}
        digest.update(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        digest.update(b'\n')
    return digest.hexdigest()


def transfer(source_url, target_url,source_object_root=None,target_object_root=None):
    if source_url == target_url: raise ValueError('Source and target must be different databases')
    source,target=make_engine(source_url),make_engine(target_url)
    migrate(target_url)
    excluded={'login_sessions','login_attempts','job_leases'}
    tables=[t for t in Base.metadata.sorted_tables if t.name not in excluded]
    counts={}
    with source.connect() as src,src.begin(),target.begin() as dst:
        from app.private_file_backup import validate_connection_files
        validate_connection_files(src,source_object_root)
        # Refuse to merge records or overwrite a partially used target.
        if any(dst.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables):
            raise ValueError('Target is not empty. Refusing to merge/overwrite any business data.')
        for table in tables:
            rows=src.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            count=0
            for chunk in rows.partitions(500):
                dst.execute(table.insert(),[dict(row) for row in chunk]); count+=len(chunk)
            actual=dst.scalar(select(func.count()).select_from(table))
            if actual != count: raise ValueError(f'Row count mismatch for {table.name}')
            if table_fingerprint(src,table) != table_fingerprint(dst,table):
                raise ValueError(f'Row content or evidence mismatch for {table.name}')
            counts[table.name]=count
        # Explicitly verify the matching copied/shared objects before committing
        # database references. Empty BLOBs never prove external bytes survived.
        validate_connection_files(dst,target_object_root)
        if dst.dialect.name=='postgresql':
            # Names come only from static ORM metadata, never from a user request.
            for table in tables:
                if 'id' in table.c and isinstance(table.c.id.type,__import__('sqlalchemy').Integer):
                    sequence=dst.scalar(text('SELECT pg_get_serial_sequence(:name, :col)'),{'name':table.name,'col':'id'})
                    if sequence:
                        maximum=dst.scalar(select(func.max(table.c.id)))
                        dst.execute(text('SELECT setval(CAST(:sequence AS regclass), :value, :used)'),
                                    {'sequence':sequence,'value':maximum or 1,'used':maximum is not None})
    source.dispose();target.dispose()
    return counts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--target-env',default='TARGET_DATABASE_URL',help='Environment variable holding the target URL; keep passwords out of shell history')
    parser.add_argument('--source-object-root',help='Private source objects, when referenced by the database')
    parser.add_argument('--target-object-root',help='Explicit matching copied/shared target objects; verified before database commit')
    args=parser.parse_args()
    target=os.getenv(args.target_env)
    if not target: raise SystemExit(f'Set environment variable {args.target_env} first')
    if input('Source service must be stopped and backed up. Type TRANSFER to continue: ')!='TRANSFER': raise SystemExit('Cancelled')
    try: print('Transferred row counts:',transfer(args.source,target,args.source_object_root,args.target_object_root))
    except Exception as exc: raise SystemExit(f'Transfer failed ({type(exc).__name__}); verify target before retrying.') from None

if __name__=='__main__': main()
