"""Append customer links and backfill V2 records without rewriting their facts.

Customer columns intentionally stay nullable so a verified h54 source rollback
can still write its original shape. Current V2 endpoints always supply a link.
This revision uses fixed Core tables, never application ORM update defaults.
"""
from alembic import op
import sqlalchemy as sa

revision = 'h55m_record_customer_links'
down_revision = 'h54l_business_records'
branch_labels = None
depends_on = None


def upgrade():
    customer_table = 'business_record_customers'
    sources = (('business_record_contracts', 'salesperson_id'),
               ('business_record_after_sales', 'owner_id'))
    for table, _ in sources:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
            batch.create_foreign_key('fk_' + table + '_customer', customer_table, ['customer_id'], ['id'])
            batch.create_index('ix_' + table + '_customer_id', ['customer_id'])

    bind = op.get_bind()
    metadata = sa.MetaData()
    customers = sa.Table(customer_table, metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer()), sa.Column('owner_id', sa.Integer()),
        sa.Column('name', sa.String(100)), sa.Column('phone', sa.String(40)),
        sa.Column('note', sa.Text()), sa.Column('version', sa.Integer()),
        sa.Column('created_at', sa.DateTime()), sa.Column('updated_at', sa.DateTime()))

    # None means ambiguous. Never choose one of several existing identities.
    matches = {}

    def remember(store, owner, name, phone, ident):
        if phone.strip():
            key = (store, owner, name, phone)
            matches[key] = None if key in matches else ident

    for row in bind.execute(sa.select(customers.c.id, customers.c.store_id,
            customers.c.owner_id, customers.c.name, customers.c.phone)).mappings():
        remember(row['store_id'], row['owner_id'], row['name'], row['phone'], row['id'])

    for table, owner_column in sources:
        records = sa.Table(table, metadata,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('store_id', sa.Integer()), sa.Column(owner_column, sa.Integer()),
            sa.Column('customer_id', sa.Integer()), sa.Column('customer_name', sa.String(100)),
            sa.Column('customer_phone', sa.String(40)), sa.Column('created_at', sa.DateTime()))
        # Materialize only linking facts before updates; do not read amounts or
        # approved JSON into Python or rewrite any original record column.
        rows = bind.execute(sa.select(records).where(records.c.customer_id.is_(None))
                            .order_by(records.c.id)).mappings().all()
        for row in rows:
            owner = row[owner_column]
            name, phone = row['customer_name'], row['customer_phone']
            key = (row['store_id'], owner, name, phone)
            customer_id = matches.get(key) if phone.strip() else None
            if customer_id is None:
                result = bind.execute(customers.insert().values(
                    store_id=row['store_id'], owner_id=owner, name=name, phone=phone,
                    note='', version=1, created_at=row['created_at'], updated_at=row['created_at']))
                customer_id = result.inserted_primary_key[0]
                remember(row['store_id'], owner, name, phone, customer_id)
            bind.execute(records.update().where(records.c.id == row['id'])
                         .values(customer_id=customer_id))


def downgrade():
    raise RuntimeError('Customer links and archives are retained; restore a verified backup instead of deleting business data')
