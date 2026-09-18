"""Maintenance-only full transfer to an EMPTY database. Preserves IDs and audit data.
Never run while the source application is accepting writes. Sessions are not copied.
Usage: python scripts/migrate_database.py --source sqlite:///./data/dealer.db --target-env TARGET_DATABASE_URL
"""
import argparse
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, func, text
from app.db import Base, make_engine
from app import models
from app.cli import migrate


def transfer(source_url, target_url):
    if source_url == target_url: raise ValueError('Source and target must be different databases')
    source,target=make_engine(source_url),make_engine(target_url)
    migrate(target_url)
    excluded={'login_sessions','login_attempts','job_leases'}
    tables=[t for t in Base.metadata.sorted_tables if t.name not in excluded]
    counts={}
    with source.connect() as src,src.begin(),target.begin() as dst:
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
            counts[table.name]=count
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
    args=parser.parse_args()
    target=os.getenv(args.target_env)
    if not target: raise SystemExit(f'Set environment variable {args.target_env} first')
    if input('Source service must be stopped and backed up. Type TRANSFER to continue: ')!='TRANSFER': raise SystemExit('Cancelled')
    try: print('Transferred row counts:',transfer(args.source,target))
    except Exception as exc: raise SystemExit(f'Transfer failed ({type(exc).__name__}); verify target before retrying.') from None

if __name__=='__main__': main()
