"""Freeze procurement v3 original credit versus average inventory cost."""
from alembic import op
import sqlalchemy as sa

revision='h834_procurement_cost'
down_revision='g733_sales_quotes'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('procurement_return_valuations',
        sa.Column('id',sa.Integer(),sa.ForeignKey('procurement_return_postings.id'),primary_key=True,autoincrement=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('quantity_before_milli',sa.BigInteger(),nullable=False),
        sa.Column('value_before_cents',sa.BigInteger(),nullable=False),
        sa.Column('inventory_cost_cents',sa.BigInteger(),nullable=False),
        sa.Column('supplier_credit_cents',sa.BigInteger(),nullable=False),
        sa.Column('variance_cents',sa.BigInteger(),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint('quantity_before_milli > 0 AND value_before_cents >= 0 AND inventory_cost_cents >= 0 AND supplier_credit_cents >= 0 AND inventory_cost_cents <= value_before_cents',name='ck_procurement_return_cost'),
        sa.CheckConstraint('variance_cents = supplier_credit_cents - inventory_cost_cents',name='ck_procurement_return_variance'))
    op.create_index('ix_procurement_return_valuations_store_id','procurement_return_valuations',['store_id'])


def downgrade():
    op.drop_table('procurement_return_valuations')
