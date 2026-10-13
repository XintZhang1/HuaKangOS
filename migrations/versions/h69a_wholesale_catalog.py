"""Independent wholesale prices and named channels; existing facts stay retail."""
from alembic import op
import sqlalchemy as sa

revision = 'h69a_wholesale_catalog'
down_revision = 'h68z_employee_handover'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('business_record_pricing_files', 'business_record_price_batches'):
        op.add_column(table, sa.Column('sales_channel', sa.String(20), nullable=False, server_default='retail'))
    op.add_column('business_record_brand_pricing', sa.Column('wholesale_vehicle_batch_id', sa.Integer(), nullable=True))
    op.create_table('business_record_wholesale_channels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.UniqueConstraint('store_id', 'name', name='uq_record_wholesale_channel_name'))
    op.create_index('ix_business_record_wholesale_channels_store_id', 'business_record_wholesale_channels', ['store_id'])


def downgrade():
    raise RuntimeError('二级价格与渠道保留合同依据，请恢复经过核对的备份')
