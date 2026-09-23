"""Frozen repair v3 quotation, authorization, stock and multi-payer facts."""
from alembic import op
import sqlalchemy as sa

revision="k511_repair"
down_revision="j410_transfer"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('repair_quotes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=12), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('discount_cents', sa.BigInteger(), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("purpose IN ('service','stop') AND amount_cents >= 0 AND discount_cents >= 0", name='ck_repair_quote_amount'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'revision', name='uq_repair_quote_revision')
    )
    op.create_index(op.f('ix_repair_quotes_case_id'), 'repair_quotes', ['case_id'], unique=False)
    op.create_index(op.f('ix_repair_quotes_store_id'), 'repair_quotes', ['store_id'], unique=False)
    op.create_table('repair_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('line_key', sa.String(length=40), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('work_item_id', sa.Integer(), nullable=True),
    sa.Column('item_id', sa.Integer(), nullable=True),
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('standard_fee_cents', sa.BigInteger(), nullable=False),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('discount_cents', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("quantity_milli > 0 AND unit_price_cents >= 0 AND amount_cents >= 0 AND discount_cents >= 0 AND ((kind='work' AND work_item_id IS NOT NULL AND item_id IS NULL) OR (kind='part' AND item_id IS NOT NULL AND work_item_id IS NULL))", name='ck_repair_line'),
    sa.ForeignKeyConstraint(['item_id'], ['flow_items.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.ForeignKeyConstraint(['work_item_id'], ['master_work_items.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('quote_id', 'line_key', name='uq_repair_line_key')
    )
    op.create_index(op.f('ix_repair_lines_quote_id'), 'repair_lines', ['quote_id'], unique=False)
    op.create_index(op.f('ix_repair_lines_store_id'), 'repair_lines', ['store_id'], unique=False)
    op.create_table('repair_price_approvals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('minimum_total_cents', sa.BigInteger(), nullable=False),
    sa.Column('allow_below_minimum', sa.Boolean(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('minimum_total_cents >= 0', name='ck_repair_price_floor'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('quote_id')
    )
    op.create_index(op.f('ix_repair_price_approvals_store_id'), 'repair_price_approvals', ['store_id'], unique=False)
    op.create_table('repair_authorizations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('quote_digest', sa.String(length=64), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('evidence_id'),
    sa.UniqueConstraint('quote_id')
    )
    op.create_index(op.f('ix_repair_authorizations_store_id'), 'repair_authorizations', ['store_id'], unique=False)
    op.create_table('repair_quote_cancellations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('quote_id')
    )
    op.create_index(op.f('ix_repair_quote_cancellations_store_id'), 'repair_quote_cancellations', ['store_id'], unique=False)
    op.create_table('repair_stock',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('line_key', sa.String(length=40), nullable=False),
    sa.Column('stock_move_id', sa.Integer(), nullable=False),
    sa.Column('original_id', sa.Integer(), nullable=True),
    sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
    sa.Column('value_cents', sa.BigInteger(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('(original_id IS NULL AND quantity_milli > 0 AND value_cents >= 0) OR (original_id IS NOT NULL AND quantity_milli < 0 AND value_cents <= 0)', name='ck_repair_stock_sign'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['original_id'], ['repair_stock.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.ForeignKeyConstraint(['stock_move_id'], ['flow_stock_moves.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stock_move_id')
    )
    op.create_index(op.f('ix_repair_stock_case_id'), 'repair_stock', ['case_id'], unique=False)
    op.create_index(op.f('ix_repair_stock_store_id'), 'repair_stock', ['store_id'], unique=False)
    op.create_table('repair_quality',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('result', sa.String(length=1000), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_repair_quality_case_id'), 'repair_quality', ['case_id'], unique=False)
    op.create_index(op.f('ix_repair_quality_store_id'), 'repair_quality', ['store_id'], unique=False)
    op.create_table('repair_settlements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('quote_id', sa.Integer(), nullable=False),
    sa.Column('labor_cost_cents', sa.BigInteger(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('labor_cost_cents >= 0', name='ck_repair_labor_cost'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['quote_id'], ['repair_quotes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id')
    )
    op.create_index(op.f('ix_repair_settlements_store_id'), 'repair_settlements', ['store_id'], unique=False)
    op.create_table('repair_allocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('settlement_id', sa.Integer(), nullable=False),
    sa.Column('payer_type', sa.String(length=20), nullable=False),
    sa.Column('payer_name', sa.String(length=120), nullable=False),
    sa.Column('insurer_id', sa.Integer(), nullable=True),
    sa.Column('manufacturer_id', sa.Integer(), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("payer_type IN ('customer','insurer','manufacturer','internal') AND amount_cents > 0", name='ck_repair_allocation'),
    sa.ForeignKeyConstraint(['case_id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['insurer_id'], ['master_insurers.id'], ),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['flow_references.id'], ),
    sa.ForeignKeyConstraint(['settlement_id'], ['repair_settlements.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'payer_type', name='uq_repair_payer')
    )
    op.create_index(op.f('ix_repair_allocations_case_id'), 'repair_allocations', ['case_id'], unique=False)
    op.create_index(op.f('ix_repair_allocations_store_id'), 'repair_allocations', ['store_id'], unique=False)
    op.create_table('repair_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('allocation_id', sa.Integer(), nullable=False),
    sa.Column('payment_link_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['allocation_id'], ['repair_allocations.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['payment_link_id'], ['flow_payment_links.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payment_link_id')
    )
    op.create_index(op.f('ix_repair_payments_allocation_id'), 'repair_payments', ['allocation_id'], unique=False)
    op.create_index(op.f('ix_repair_payments_store_id'), 'repair_payments', ['store_id'], unique=False)

def downgrade():
    raise RuntimeError("维修报价、授权与结算事实不可删除降级；请恢复经过验证的一致备份")
