"""Frozen physical warehouse ledger, activation and count observations."""
from alembic import op
import sqlalchemy as sa
revision = 'r218_warehouse'
down_revision = 'q117_reconciliation'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('warehouse_balances',
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('bucket', sa.String(length=60), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('master_locations.id'), nullable=True),
        sa.Column('transit_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=True),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(location_id IS NOT NULL AND transit_case_id IS NULL) OR (location_id IS NULL AND transit_case_id IS NOT NULL)', name='ck_warehouse_bucket_kind'),
        sa.CheckConstraint('quantity_milli>=0 AND value_cents>=0 AND (quantity_milli>0 OR value_cents=0)', name='ck_warehouse_balance'),
        sa.UniqueConstraint('store_id','item_id','bucket', name='uq_warehouse_bucket'))
    op.create_index('ix_warehouse_balances_item_id','warehouse_balances',['item_id'],unique=False)
    op.create_index('ix_warehouse_balances_store_id','warehouse_balances',['store_id'],unique=False)
    op.create_table('warehouse_enrollments',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('baseline_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('baseline_value_cents', sa.BigInteger(), nullable=False),
        sa.Column('stock_move_cursor', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('item_id', name=None),
        sa.UniqueConstraint('case_id', name=None))
    op.create_index('ix_warehouse_enrollments_store_id','warehouse_enrollments',['store_id'],unique=False)
    op.create_table('warehouse_holds',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('master_locations.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity_milli!=0 AND reason IN ('reserve','release')", name='ck_warehouse_hold'))
    op.create_index('ix_warehouse_holds_case_id','warehouse_holds',['case_id'],unique=False)
    op.create_index('ix_warehouse_holds_item_id','warehouse_holds',['item_id'],unique=False)
    op.create_index('ix_warehouse_holds_store_id','warehouse_holds',['store_id'],unique=False)
    op.create_table('warehouse_allocations',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('purpose', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('stock_move_id', sa.Integer(), sa.ForeignKey('flow_stock_moves.id'), nullable=True),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('prepared','consumed','cancelled')", name='ck_warehouse_allocation_state'),
        sa.UniqueConstraint('stock_move_id', name=None))
    op.create_index('ix_warehouse_allocations_item_id','warehouse_allocations',['item_id'],unique=False)
    op.create_index('ix_warehouse_allocations_store_id','warehouse_allocations',['store_id'],unique=False)
    op.create_index('ix_warehouse_allocations_case_id','warehouse_allocations',['case_id'],unique=False)
    op.create_table('warehouse_approvals',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('value_cents>=0', name='ck_warehouse_approval_value'),
        sa.UniqueConstraint('case_id', name=None))
    op.create_index('ix_warehouse_approvals_store_id','warehouse_approvals',['store_id'],unique=False)
    op.create_table('warehouse_count_observations',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('balance_id', sa.Integer(), sa.ForeignKey('warehouse_balances.id'), nullable=False),
        sa.Column('baseline_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('counted_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('entry_cursor', sa.Integer(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('counted_quantity_milli>=0', name='ck_warehouse_count_observation'),
        sa.UniqueConstraint('case_id', name=None))
    op.create_index('ix_warehouse_count_observations_store_id','warehouse_count_observations',['store_id'],unique=False)
    op.create_table('warehouse_documents',
        sa.Column('id', sa.Integer(), sa.ForeignKey('flow_cases.id'), primary_key=True, nullable=False),
        sa.Column('operation', sa.String(length=24), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('source_location_id', sa.Integer(), sa.ForeignKey('master_locations.id'), nullable=True),
        sa.Column('destination_location_id', sa.Integer(), sa.ForeignKey('master_locations.id'), nullable=True),
        sa.Column('original_move_id', sa.Integer(), sa.ForeignKey('flow_stock_moves.id'), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('recipient', sa.String(length=120), nullable=False),
        sa.Column('baseline_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('baseline_value_cents', sa.BigInteger(), nullable=False),
        sa.Column('baseline_item_version', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("operation IN ('activate','other_in','other_in_return','consumable','consumable_return','gift','gift_return','disposal','local_move','count')", name='ck_warehouse_operation'),
        sa.CheckConstraint('quantity_milli>=0', name='ck_warehouse_doc_qty'))
    op.create_index('ix_warehouse_documents_item_id','warehouse_documents',['item_id'],unique=False)
    op.create_index('ix_warehouse_documents_store_id','warehouse_documents',['store_id'],unique=False)
    op.create_table('warehouse_entries',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('balance_id', sa.Integer(), sa.ForeignKey('warehouse_balances.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('stock_move_id', sa.Integer(), sa.ForeignKey('flow_stock_moves.id'), nullable=True),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=30), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False))
    op.create_index('ix_warehouse_entries_stock_move_id','warehouse_entries',['stock_move_id'],unique=False)
    op.create_index('ix_warehouse_entries_balance_id','warehouse_entries',['balance_id'],unique=False)
    op.create_index('ix_warehouse_entries_store_id','warehouse_entries',['store_id'],unique=False)
    op.create_index('ix_warehouse_entries_case_id','warehouse_entries',['case_id'],unique=False)
    op.create_table('warehouse_allocation_lines',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('allocation_id', sa.Integer(), sa.ForeignKey('warehouse_allocations.id'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('master_locations.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('quantity_milli>=0', name='ck_warehouse_allocation_qty'),
        sa.UniqueConstraint('allocation_id','location_id', name='uq_warehouse_allocation_location'))
    op.create_index('ix_warehouse_allocation_lines_store_id','warehouse_allocation_lines',['store_id'],unique=False)
    op.create_index('ix_warehouse_allocation_lines_allocation_id','warehouse_allocation_lines',['allocation_id'],unique=False)

def downgrade():
    op.drop_table('warehouse_allocation_lines')
    op.drop_table('warehouse_entries')
    op.drop_table('warehouse_documents')
    op.drop_table('warehouse_count_observations')
    op.drop_table('warehouse_approvals')
    op.drop_table('warehouse_allocations')
    op.drop_table('warehouse_holds')
    op.drop_table('warehouse_enrollments')
    op.drop_table('warehouse_balances')
