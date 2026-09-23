"""Produce review-only DDL outside migrations/versions, never apply it.

This is a one-time draft aid for the unpublished transport exception schema.
The eventual Alembic revision must contain frozen declarations, not import this
generator or mutable model metadata at migration time.
"""
from pathlib import Path
from sqlalchemy.schema import CreateTable,CreateIndex
from sqlalchemy import UniqueConstraint,CheckConstraint
from sqlalchemy.dialects import sqlite,postgresql
from app.db import Base
from app import models
from app import transfer_exception_models as exception_models


def main():
    owned={value.__table__.name for value in vars(exception_models).values()
        if isinstance(value,type) and getattr(value,'__module__','')==exception_models.__name__ and hasattr(value,'__table__')}
    destination=Path(__file__).parent/'drafts';destination.mkdir(exist_ok=True)
    for name,dialect in (('sqlite',sqlite.dialect()),('postgresql',postgresql.dialect())):
        blocks=['-- REVIEW DRAFT ONLY. Not registered or applied.\n-- Separate append-only Alembic revision required before enabling transfer v3.']
        for table in Base.metadata.sorted_tables:
            if table.name not in owned:continue
            blocks.append(str(CreateTable(table).compile(dialect=dialect)).strip()+';')
            for index in sorted(table.indexes,key=lambda index:index.name):blocks.append(str(CreateIndex(index).compile(dialect=dialect))+';')
        (destination/('transfer_exceptions_'+name+'.sql')).write_text('\n\n'.join(blocks)+'\n',encoding='utf-8')
    print('Draft only: '+str(len(owned))+' tables; no database or migration changes.')


def freeze_new_revision():
    """One-time authorized generation. Refuse to overwrite any saved revision."""
    destination=Path(__file__).resolve().parents[1]/'migrations'/'versions'/'m359_transfer_exceptions.py'
    if destination.exists():raise RuntimeError('Revision already exists; never regenerate a saved migration')
    owned={value.__table__.name for value in vars(exception_models).values()
        if isinstance(value,type) and getattr(value,'__module__','')==exception_models.__name__ and hasattr(value,'__table__')}
    lines=['"""Frozen v3 transport loss, independent recovery and original clearing sources."""',
        'from alembic import op','import sqlalchemy as sa','',"revision='m359_transfer_exceptions'", "down_revision='l248_business_entities'",'branch_labels=None','depends_on=None','','','def upgrade():',
        "    check_names={c['name'] for c in sa.inspect(op.get_bind()).get_check_constraints('interstore_clearing_buckets')}",
        "    if 'ck_clearing_parties' not in check_names:raise RuntimeError('Expected original clearing-party constraint; inspect the isolated migration copy')",
        "    with op.batch_alter_table('interstore_clearing_buckets') as batch:",
        "        batch.drop_constraint('ck_clearing_parties',type_='check')",
        "        batch.create_check_constraint('ck_clearing_parties',\"origin_kind IN ('material','vehicle','material_loss') AND payer_store_id!=receiver_store_id\")"]
    for table in Base.metadata.sorted_tables:
        if table.name not in owned:continue
        lines.append('    op.create_table('+repr(table.name)+',')
        for col in table.columns:
            pieces=[repr(col.name),'sa.'+repr(col.type)]
            pieces.extend('sa.ForeignKey('+repr(fk.target_fullname)+')' for fk in col.foreign_keys)
            pieces.append('nullable='+repr(col.nullable))
            if col.primary_key:pieces.append('primary_key=True')
            lines.append('        sa.Column('+', '.join(pieces)+'),')
        for constraint in sorted(table.constraints,key=lambda c:(type(c).__name__,str(c.name))):
            if isinstance(constraint,UniqueConstraint):
                args=[repr(c.name) for c in constraint.columns]
                if constraint.name:args.append('name='+repr(constraint.name))
                lines.append('        sa.UniqueConstraint('+', '.join(args)+'),')
            if isinstance(constraint,CheckConstraint):lines.append('        sa.CheckConstraint('+repr(str(constraint.sqltext))+', name='+repr(constraint.name)+'),')
        lines.append('    )')
        for index in sorted(table.indexes,key=lambda index:index.name):lines.append('    op.create_index('+repr(index.name)+', '+repr(table.name)+', '+repr([c.name for c in index.columns])+', unique='+repr(index.unique)+')')
    lines+=['','','def downgrade():',"    raise RuntimeError('Transport loss and original recovery facts require a reviewed backup restore; no destructive downgrade')"]
    destination.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Created new static m359 revision: '+str(len(owned))+' tables; no model imports in revision.')


if __name__=='__main__':main()
