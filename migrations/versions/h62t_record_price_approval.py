"""Append store price publications and frozen V2.10 contract terms."""
from alembic import op
import sqlalchemy as sa

revision = 'h62t_record_price_approval'
down_revision = 'h61s_store_administration'
branch_labels = None
depends_on = None


def _base(*, versioned=False):
    columns = [sa.Column('id', sa.Integer(), primary_key=True),
               sa.Column('store_id', sa.Integer(), nullable=False)]
    if versioned:
        columns += [sa.Column('version', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), nullable=False),
                    sa.Column('updated_at', sa.DateTime(), nullable=False)]
    return columns


def _store_index(table, *fields):
    for name in ('store_id', *fields):
        op.create_index('ix_' + table + '_' + name, table, [name])


def upgrade():
    op.create_table('business_record_pricing_settings', *_base(versioned=True),
        sa.Column('vehicle_batch_id', sa.Integer(), nullable=True),
        sa.Column('gift_batch_id', sa.Integer(), nullable=True),
        sa.Column('profile', sa.JSON(), nullable=False),
        sa.UniqueConstraint('store_id', name='uq_record_pricing_store'))
    _store_index('business_record_pricing_settings')
    op.create_table('business_record_pricing_files', *_base(),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=True),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('object_key', sa.String(200), nullable=False),
        sa.Column('scan_state', sa.String(30), nullable=False),
        sa.Column('scan_code', sa.String(50), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('vehicle','gift','contract_attachment')", name='ck_record_pricing_file_kind'))
    _store_index('business_record_pricing_files', 'contract_id')
    op.create_table('business_record_price_batches', *_base(),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('file_id', sa.Integer(), sa.ForeignKey('business_record_pricing_files.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('vehicle','gift')", name='ck_record_price_batch_kind'),
        sa.CheckConstraint('row_count > 0', name='ck_record_price_batch_count'))
    _store_index('business_record_price_batches')
    op.create_table('business_record_vehicle_variants', *_base(versioned=True),
        sa.Column('family', sa.String(100), nullable=False),
        sa.Column('series', sa.String(160), nullable=False),
        sa.Column('model', sa.String(160), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('store_id', 'family', 'series', 'model', name='uq_record_vehicle_variant'))
    _store_index('business_record_vehicle_variants')
    op.create_table('business_record_vehicle_prices', *_base(),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('business_record_price_batches.id'), nullable=False),
        sa.Column('variant_id', sa.Integer(), sa.ForeignKey('business_record_vehicle_variants.id'), nullable=False),
        sa.Column('family', sa.String(100), nullable=False),
        sa.Column('series', sa.String(160), nullable=False),
        sa.Column('model', sa.String(160), nullable=False),
        sa.Column('guide_price_cents', sa.BigInteger(), nullable=False),
        sa.Column('control_price_cents', sa.BigInteger(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.UniqueConstraint('batch_id', 'variant_id', name='uq_record_batch_variant'),
        sa.CheckConstraint('guide_price_cents > 0 AND control_price_cents > 0', name='ck_record_vehicle_prices_positive'))
    _store_index('business_record_vehicle_prices', 'batch_id')
    op.create_table('business_record_gift_prices', *_base(),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('business_record_price_batches.id'), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('unit_price_cents', sa.BigInteger(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.UniqueConstraint('batch_id', 'name', name='uq_record_batch_gift'),
        sa.CheckConstraint('unit_price_cents >= 0', name='ck_record_gift_price_nonnegative'))
    _store_index('business_record_gift_prices', 'batch_id')
    op.create_table('business_record_contract_terms', *_base(versioned=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False, unique=True),
        sa.Column('price_snapshot', sa.JSON(), nullable=False),
        sa.Column('gift_batch_id', sa.Integer(), nullable=True),
        sa.Column('gifts_snapshot', sa.JSON(), nullable=False),
        sa.Column('gift_total_cents', sa.BigInteger(), nullable=False),
        sa.Column('submission_data', sa.JSON(), nullable=False),
        sa.Column('price_below_cents', sa.BigInteger(), nullable=False),
        sa.Column('gift_excess_cents', sa.BigInteger(), nullable=False),
        sa.Column('special', sa.Boolean(), nullable=False),
        sa.Column('special_note', sa.Text(), nullable=False),
        sa.CheckConstraint('gift_total_cents >= 0 AND price_below_cents >= 0 AND gift_excess_cents >= 0', name='ck_record_terms_nonnegative'))
    _store_index('business_record_contract_terms')
    with op.batch_alter_table('business_record_contracts') as batch:
        for name in ('workflow', 'priced', 'deputy', 'general'):
            batch.drop_constraint('ck_record_contract_' + name, type_='check')
        batch.create_check_constraint('ck_record_contract_workflow', "workflow_version IN ('legacy-v2','trial-v29','trial-v30','trial-v210')")
        batch.create_check_constraint('ck_record_contract_priced', "workflow_version IN ('trial-v29','trial-v30','trial-v210') OR status NOT IN ('priced','approved') OR (expected_amount_cents IS NOT NULL AND cost_cents IS NOT NULL AND profit_cents IS NOT NULL AND gift_cost_cents IS NOT NULL AND priced_by IS NOT NULL)")
        batch.create_check_constraint('ck_record_contract_deputy', "status != 'deputy_pending' OR (workflow_version IN ('trial-v30','trial-v210') AND general_manager_approved_by IS NOT NULL)")
        batch.create_check_constraint('ck_record_contract_general', "workflow_version NOT IN ('trial-v30','trial-v210') OR status != 'approved' OR general_manager_approved_by IS NOT NULL")


def downgrade():
    raise RuntimeError('Submitted price and approval history are retained; restore a verified backup instead')
