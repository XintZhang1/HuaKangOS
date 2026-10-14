"""Independent current inventory publications and retained contract VIN evidence."""
from alembic import op
import sqlalchemy as sa

revision = 'h71c_record_inventory'
down_revision = 'h70b_contract_corrections'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('business_record_inventory_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('object_key', sa.String(200), nullable=False),
        sa.Column('scan_state', sa.String(30), nullable=False),
        sa.Column('scan_code', sa.String(50), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('business_record_inventory_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('business_record_inventory_files.id'), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('sheet', sa.String(100), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('mapping', sa.JSON(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.Column('excluded_count', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('business_record_inventory_rows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('business_record_inventory_batches.id'), nullable=False),
        sa.Column('vin', sa.String(17), nullable=False),
        sa.Column('source_row', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(160), nullable=False),
        sa.Column('configuration', sa.String(300), nullable=False),
        sa.Column('exterior_color', sa.String(100), nullable=False),
        sa.Column('interior_color', sa.String(100), nullable=False),
        sa.Column('extra_configuration', sa.String(500), nullable=False),
        sa.Column('guide_price_cents', sa.BigInteger(), nullable=True),
        sa.Column('production_on', sa.Date(), nullable=True),
        sa.Column('age_days', sa.Integer(), nullable=True),
        sa.Column('funding_kind', sa.String(20), nullable=False),
        sa.Column('funding_source', sa.String(160), nullable=False),
        sa.Column('source_owner', sa.String(160), nullable=False),
        sa.Column('location', sa.String(160), nullable=False),
        sa.Column('price_reference', sa.JSON(), nullable=True),
        sa.Column('issues', sa.JSON(), nullable=False),
        sa.UniqueConstraint('batch_id', 'vin', name='uq_record_inventory_batch_vin'))
    op.create_table('business_record_inventory_current',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('business_record_inventory_batches.id'), nullable=False),
        sa.UniqueConstraint('store_id', 'brand', name='uq_record_inventory_current_store_brand'))
    op.create_table('business_record_inventory_claims',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('vin', sa.String(17), nullable=False),
        sa.Column('inventory_row_id', sa.Integer(), sa.ForeignKey('business_record_inventory_rows.id'), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id', 'contract_id', 'vin', name='uq_record_inventory_contract_vin'))
    for name in ('files', 'batches', 'rows', 'current', 'claims'):
        table = 'business_record_inventory_' + name
        op.create_index('ix_' + table + '_store_id', table, ['store_id'])
    for table, columns in (('business_record_inventory_rows', ['batch_id', 'vin']),
                           ('business_record_inventory_claims', ['contract_id', 'vin'])):
        for col in columns:
            op.create_index('ix_' + table + '_' + col, table, [col])


def downgrade():
    raise RuntimeError('库存发布及合同VIN历史不可删除，请恢复经核对的联合备份')
