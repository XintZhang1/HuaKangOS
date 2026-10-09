"""Append invoice records without changing receipt facts or prior contracts."""
from alembic import op
import sqlalchemy as sa

revision = 'h58p_record_invoices'
down_revision = 'h57o_record_trial_flow'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('business_record_invoices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False, unique=True),
        sa.Column('active_file_id', sa.Integer(), nullable=True),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False))
    op.create_table('business_record_invoice_files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('business_record_invoices.id'), nullable=False),
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
        sa.UniqueConstraint('invoice_id', 'sha256', name='uq_record_invoice_file_hash'))
    for table in ('business_record_invoices', 'business_record_invoice_files'):
        op.create_index('ix_' + table + '_store_id', table, ['store_id'])
    op.create_index('ix_business_record_invoice_files_invoice_id', 'business_record_invoice_files', ['invoice_id'])


def downgrade():
    raise RuntimeError('Uploaded originals are retained; restore a verified backup instead')
