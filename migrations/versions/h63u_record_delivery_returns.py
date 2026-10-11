"""Append financial delivery evidence and independently recorded vehicle returns."""
from alembic import op
import sqlalchemy as sa

revision = 'h63u_record_delivery_returns'
down_revision = 'h62t_record_price_approval'
branch_labels = None
depends_on = None


def _identity():
    return [sa.Column('id', sa.Integer(), primary_key=True), sa.Column('store_id', sa.Integer(), nullable=False)]


def upgrade():
    op.add_column('business_record_invoices', sa.Column('uploaded_at', sa.DateTime(), nullable=True))
    # Historical uploads retain their original record and are not relabelled as
    # new financial delivery events; a new upload explicitly establishes a date.
    op.create_table('business_record_gift_documents', *_identity(),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False), sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False), sa.Column('object_key', sa.String(200), nullable=False),
        sa.Column('scan_state', sa.String(30), nullable=False), sa.Column('scan_code', sa.String(50), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_table('business_record_deliveries', *_identity(),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False, unique=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('business_record_invoices.id'), nullable=False),
        sa.Column('invoice_file_id', sa.Integer(), sa.ForeignKey('business_record_invoice_files.id'), nullable=False),
        sa.Column('gift_document_id', sa.Integer(), sa.ForeignKey('business_record_gift_documents.id'), nullable=True),
        sa.Column('accounting_on', sa.Date(), nullable=False),
        sa.Column('invoice_amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=False),
        sa.Column('cc_role', sa.String(40), nullable=False), sa.Column('note', sa.Text(), nullable=False))
    op.create_table('business_record_returns', *_identity(),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('delivery_id', sa.Integer(), sa.ForeignKey('business_record_deliveries.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('requested_refund_cents', sa.BigInteger(), nullable=True), sa.Column('note', sa.Text(), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True), sa.Column('approved_on', sa.Date(), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=False), sa.Column('reversal_snapshot', sa.JSON(), nullable=True),
        sa.CheckConstraint("status IN ('submitted','approved','rejected')", name='ck_record_return_status'))
    op.create_table('business_record_refunds', *_identity(),
        sa.Column('return_id', sa.Integer(), sa.ForeignKey('business_record_returns.id'), nullable=False),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('business_record_contracts.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False), sa.Column('refunded_on', sa.Date(), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('note', sa.Text(), nullable=False),
        sa.CheckConstraint('amount_cents > 0', name='ck_record_refund_positive'))
    for table in ('business_record_gift_documents', 'business_record_deliveries', 'business_record_returns', 'business_record_refunds'):
        op.create_index('ix_' + table + '_store_id', table, ['store_id'])
    for table, columns in (
        ('business_record_gift_documents', ['contract_id']), ('business_record_deliveries', ['accounting_on']),
        ('business_record_returns', ['contract_id', 'approved_on']), ('business_record_refunds', ['return_id', 'contract_id'])):
        for column in columns:
            op.create_index('ix_' + table + '_' + column, table, [column])


def downgrade():
    raise RuntimeError('交车和退车原始事实不可删除；请恢复经过核对的备份')
