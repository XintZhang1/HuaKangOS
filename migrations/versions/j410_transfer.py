"""Frozen paired material transfer coordination, physical postings and settlement links."""
from alembic import op
import sqlalchemy as sa

revision = "j410_transfer"
down_revision = "i309_procurement"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('material_transfers',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=60), nullable=False),
        sa.Column('from_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('to_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('from_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('to_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('destination_approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('from_case_id', name=None),
        sa.UniqueConstraint('number', name=None),
        sa.UniqueConstraint('to_case_id', name=None),
        sa.CheckConstraint("status IN ('requested','approved','transit','completed','cancelled')", name='ck_material_transfer_status'),
        sa.CheckConstraint('from_store_id != to_store_id', name='ck_material_transfer_stores'))
    op.create_index('ix_material_transfers_from_store_id', 'material_transfers', ['from_store_id'])
    op.create_index('ix_material_transfers_to_store_id', 'material_transfers', ['to_store_id'])
    op.create_table('material_transfer_lines',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('source_item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('sku', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('quantity_milli > 0', name='ck_material_transfer_quantity'),
        sa.UniqueConstraint('transfer_id', 'source_item_id', name='uq_material_transfer_item'))
    op.create_index('ix_material_transfer_lines_transfer_id', 'material_transfer_lines', ['transfer_id'])
    op.create_table('material_transfer_movements',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('line_id', sa.Integer(), sa.ForeignKey('material_transfer_lines.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('stock_move_id', sa.Integer(), sa.ForeignKey('flow_stock_moves.id'), nullable=True),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('material_transfer_movements.id'), nullable=True),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.UniqueConstraint('stock_move_id', name=None),
        sa.CheckConstraint('quantity_milli > 0 AND value_cents >= 0', name='ck_transfer_movement_amount'),
        sa.CheckConstraint("kind IN ('dispatch','accept','reject','return_ship','return_receive')", name='ck_transfer_movement_kind'))
    op.create_index('ix_material_transfer_movements_line_id', 'material_transfer_movements', ['line_id'])
    op.create_index('ix_material_transfer_movements_transfer_id', 'material_transfer_movements', ['transfer_id'])
    op.create_table('material_transfer_settlements',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('movement_id', sa.Integer(), sa.ForeignKey('material_transfer_movements.id'), nullable=False),
        sa.Column('counterparty_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('movement_id', 'store_id', name='uq_transfer_settlement_party'))
    op.create_index('ix_material_transfer_settlements_store_id', 'material_transfer_settlements', ['store_id'])
    op.create_index('ix_material_transfer_settlements_transfer_id', 'material_transfer_settlements', ['transfer_id'])
    op.create_table('material_transfer_receipts',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('store_id', 'request_key', name='uq_material_transfer_request'))
    op.create_index('ix_material_transfer_receipts_store_id', 'material_transfer_receipts', ['store_id'])


def downgrade():
    raise RuntimeError("调拨实物和往来记录不可删除降级，请恢复经过验证的备份")
