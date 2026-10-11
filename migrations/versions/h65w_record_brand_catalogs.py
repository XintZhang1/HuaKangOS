"""Explicit single-brand stores and shared immutable price publications."""
from alembic import op
import sqlalchemy as sa

revision = 'h65w_record_brand_catalogs'
down_revision = 'h64v_record_gift_costs'
branch_labels = None
depends_on = None


def upgrade():
    # No legacy profiles or price pointers are inferred or merged. An admin
    # sets store brands; a reviewed publication explicitly starts sharing.
    for table in ('stores', 'business_record_pricing_files', 'business_record_price_batches'):
        op.add_column(table, sa.Column('brand', sa.String(100), nullable=False, server_default=''))
    op.create_table('business_record_brand_pricing',
        sa.Column('brand', sa.String(100), primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('vehicle_batch_id', sa.Integer(), sa.ForeignKey('business_record_price_batches.id'), nullable=True),
        sa.Column('gift_batch_id', sa.Integer(), sa.ForeignKey('business_record_price_batches.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False))
    op.create_table('business_record_brand_variants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('family', sa.String(100), nullable=False),
        sa.Column('series', sa.String(160), nullable=False),
        sa.Column('model', sa.String(160), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('brand', 'family', 'series', 'model', name='uq_record_brand_variant'))
    op.create_index('ix_business_record_brand_variants_brand', 'business_record_brand_variants', ['brand'])


def downgrade():
    raise RuntimeError('品牌目录及发布依据不可删除；请恢复经过核对的备份')
