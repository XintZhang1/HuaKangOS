"""Frozen retail reservation, fulfillment and original return ledgers."""
from alembic import op
import sqlalchemy as sa

revision="p016_retail"
down_revision="o915_vehicle_procurement"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('retail_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('goods_cents', sa.BigInteger(), nullable=False),
    sa.Column('work_item_id', sa.Integer(), nullable=True),
    sa.Column('work_code', sa.String(length=60), nullable=False),
    sa.Column('work_name', sa.String(length=120), nullable=False),
    sa.Column('installation_unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('installation_cents', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity_milli>0 AND unit_price_cents>=0 AND goods_cents>=0 AND installation_unit_price_cents>=0 AND installation_cents>=0', name='ck_retail_line'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['item_id'], ['flow_items.id'], ),
    sa.ForeignKeyConstraint(['work_item_id'], ['master_work_items.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'item_id', name='uq_retail_item')
    )
    op.create_index(op.f('ix_retail_lines_case_id'), 'retail_lines', ['case_id'], unique=False)
    op.create_index(op.f('ix_retail_lines_store_id'), 'retail_lines', ['store_id'], unique=False)
    op.create_table('retail_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('related_repair_id', sa.Integer(), nullable=True),
    sa.Column('customer_name', sa.String(length=120), nullable=False),
    sa.Column('discount_cents', sa.BigInteger(), nullable=False),
    sa.Column('installation_policy', sa.String(length=200), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['related_repair_id'], ['flow_cases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_retail_orders_store_id'), 'retail_orders', ['store_id'], unique=False)
    op.create_table('retail_reservations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('reason', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("(quantity_milli>0 AND reason='reserve') OR (quantity_milli<0 AND reason IN ('dispatch','cancel'))", name='ck_retail_reservation'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['item_id'], ['flow_items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_retail_reservations_case_id'), 'retail_reservations', ['case_id'], unique=False)
    op.create_index(op.f('ix_retail_reservations_item_id'), 'retail_reservations', ['item_id'], unique=False)
    op.create_index(op.f('ix_retail_reservations_store_id'), 'retail_reservations', ['store_id'], unique=False)
    op.create_table('retail_dispatches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('line_id', sa.Integer(), nullable=False),
    sa.Column('stock_move_id', sa.Integer(), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('value_cents', sa.BigInteger(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity_milli>0 AND value_cents>=0', name='ck_retail_dispatch'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['line_id'], ['retail_lines.id'], ),
    sa.ForeignKeyConstraint(['stock_move_id'], ['flow_stock_moves.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('line_id'),
    sa.UniqueConstraint('stock_move_id')
    )
    op.create_index(op.f('ix_retail_dispatches_case_id'), 'retail_dispatches', ['case_id'], unique=False)
    op.create_index(op.f('ix_retail_dispatches_store_id'), 'retail_dispatches', ['store_id'], unique=False)
    op.create_table('retail_returns',
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('requested_by', sa.Integer(), nullable=False),
    sa.Column('approved_by', sa.Integer(), nullable=True),
    sa.Column('retain_installation', sa.Boolean(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('requested','approved','rectification','reinspection','handback','rejected','accepted','cancelled')", name='ck_retail_return_status'),
    sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_retail_returns_case_id'), 'retail_returns', ['case_id'], unique=False)
    op.create_index(op.f('ix_retail_returns_store_id'), 'retail_returns', ['store_id'], unique=False)
    op.create_table('retail_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('payment_link_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['payment_link_id'], ['flow_payment_links.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payment_link_id')
    )
    op.create_index(op.f('ix_retail_payments_case_id'), 'retail_payments', ['case_id'], unique=False)
    op.create_index(op.f('ix_retail_payments_store_id'), 'retail_payments', ['store_id'], unique=False)
    op.create_table('retail_return_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('return_id', sa.Integer(), nullable=False),
    sa.Column('dispatch_id', sa.Integer(), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity_milli>0', name='ck_retail_return_line'),
    sa.ForeignKeyConstraint(['dispatch_id'], ['retail_dispatches.id'], ),
    sa.ForeignKeyConstraint(['return_id'], ['retail_returns.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('return_id', 'dispatch_id', name='uq_retail_return_line')
    )
    op.create_index(op.f('ix_retail_return_lines_return_id'), 'retail_return_lines', ['return_id'], unique=False)
    op.create_index(op.f('ix_retail_return_lines_store_id'), 'retail_return_lines', ['store_id'], unique=False)
    op.create_table('retail_return_postings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('return_line_id', sa.Integer(), nullable=False),
    sa.Column('dispatch_id', sa.Integer(), nullable=False),
    sa.Column('stock_move_id', sa.Integer(), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('value_cents', sa.BigInteger(), nullable=False),
    sa.Column('goods_cents', sa.BigInteger(), nullable=False),
    sa.Column('installation_cents', sa.BigInteger(), nullable=False),
    sa.Column('retained_cents', sa.BigInteger(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity_milli>0 AND value_cents>=0 AND goods_cents>=0 AND installation_cents>=0 AND retained_cents>=0 AND retained_cents<=installation_cents', name='ck_retail_return_posting'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['dispatch_id'], ['retail_dispatches.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['return_line_id'], ['retail_return_lines.id'], ),
    sa.ForeignKeyConstraint(['stock_move_id'], ['flow_stock_moves.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('return_line_id'),
    sa.UniqueConstraint('stock_move_id')
    )
    op.create_index(op.f('ix_retail_return_postings_case_id'), 'retail_return_postings', ['case_id'], unique=False)
    op.create_index(op.f('ix_retail_return_postings_dispatch_id'), 'retail_return_postings', ['dispatch_id'], unique=False)
    op.create_index(op.f('ix_retail_return_postings_store_id'), 'retail_return_postings', ['store_id'], unique=False)

def downgrade():
    op.drop_table('retail_return_postings')
    op.drop_table('retail_return_lines')
    op.drop_table('retail_payments')
    op.drop_table('retail_returns')
    op.drop_table('retail_dispatches')
    op.drop_table('retail_reservations')
    op.drop_table('retail_orders')
    op.drop_table('retail_lines')
