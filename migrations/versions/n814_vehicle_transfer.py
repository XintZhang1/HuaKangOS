"""Frozen VIN custody and paired physical vehicle transfers; old records stay owned by their store."""
from alembic import op
import sqlalchemy as sa

revision = 'n814_vehicle_transfer'
down_revision = 'm713_group_benefits'
branch_labels = None
depends_on = None


def upgrade():
    old = next(c for c in sa.inspect(op.get_bind()).get_unique_constraints('vehicles') if c['column_names'] == ['vin'])
    with op.batch_alter_table('vehicles', naming_convention={'uq':'uq_%(table_name)s_%(column_0_name)s'}) as batch:
        batch.add_column(sa.Column('inventory_generation', sa.Integer(), nullable=False, server_default='0'))
        batch.drop_constraint(old['name'] or 'uq_vehicles_vin', type_='unique')
        batch.create_unique_constraint('uq_vehicle_vin_generation', ['vin','inventory_generation'])
        batch.create_check_constraint('ck_vehicle_generation', 'inventory_generation >= 0')
    op.create_table('vehicle_transfers',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=60), nullable=False),
        sa.Column('from_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('to_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('from_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('to_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('source_vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('received_vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=True),
        sa.Column('vin', sa.String(length=17), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
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
        sa.UniqueConstraint('received_vehicle_id', name=None),
        sa.UniqueConstraint('to_case_id', name=None),
        sa.CheckConstraint('from_store_id != to_store_id', name='ck_vehicle_transfer_parties'),
        sa.CheckConstraint("status IN ('requested','approved','transit','rejected','return_transit','accepted','returned','cancelled')", name='ck_vehicle_transfer_status'))
    op.create_index('ix_vehicle_transfers_vin', 'vehicle_transfers', ['vin'])
    op.create_table('vehicle_custodies',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('vin', sa.String(length=17), nullable=False),
        sa.Column('identity_id', sa.Integer(), sa.ForeignKey('group_identities.id'), nullable=False),
        sa.Column('current_vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=True),
        sa.Column('current_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=True),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('pending_transfer_id', sa.Integer(), sa.ForeignKey('vehicle_transfers.id'), nullable=True),
        sa.UniqueConstraint('current_vehicle_id', name=None),
        sa.UniqueConstraint('identity_id', name=None),
        sa.UniqueConstraint('pending_transfer_id', name=None),
        sa.UniqueConstraint('vin', name=None),
        sa.CheckConstraint('generation >= 0', name='ck_vehicle_custody_generation'),
        sa.CheckConstraint('(current_vehicle_id IS NULL AND current_store_id IS NULL) OR (current_vehicle_id IS NOT NULL AND current_store_id IS NOT NULL)', name='ck_vehicle_custody_owner'))
    op.create_table('vehicle_movements',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('vehicle_transfers.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("(kind='dispatch' AND quantity=-1 AND value_cents<=0 AND vehicle_id IS NOT NULL) OR (kind IN ('accept','return_receive') AND quantity=1 AND value_cents>=0 AND vehicle_id IS NOT NULL) OR (kind IN ('reject','return_ship') AND quantity=0 AND value_cents=0 AND vehicle_id IS NULL)", name='ck_vehicle_movement_sign'),
        sa.UniqueConstraint('transfer_id', 'kind', name='uq_vehicle_movement_once'))
    op.create_index('ix_vehicle_movements_store_id', 'vehicle_movements', ['store_id'])
    op.create_index('ix_vehicle_movements_transfer_id', 'vehicle_movements', ['transfer_id'])
    op.create_table('vehicle_transfer_settlements',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('vehicle_transfers.id'), nullable=False),
        sa.Column('counterparty_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('transfer_id', 'store_id', name='uq_vehicle_settlement_party'))
    op.create_index('ix_vehicle_transfer_settlements_store_id', 'vehicle_transfer_settlements', ['store_id'])


def downgrade():
    raise RuntimeError("Vehicle transfer facts require a reviewed export; automatic downgrade is disabled")
