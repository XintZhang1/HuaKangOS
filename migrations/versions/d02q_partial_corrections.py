"""Keep actual original refunds while correcting only remaining allocations."""
from alembic import op
import sqlalchemy as sa

revision='d02q_partial_corrections'
down_revision='c91p_repair_packages'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('business_finance_correction_bases',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),
        sa.Column('original_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False),
        sa.Column('previous_id',sa.Integer(),sa.ForeignKey('business_finance_correction_bases.id'),nullable=True),
        sa.Column('original_amount_cents',sa.BigInteger(),nullable=False),sa.Column('corrected_amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('refunded_cents',sa.BigInteger(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint('original_amount_cents>=refunded_cents AND corrected_amount_cents>=refunded_cents AND refunded_cents>0',name='ck_finance_correction_basis'))
    for column in ('store_id','original_cash_id'):op.create_index('ix_business_finance_correction_bases_'+column,'business_finance_correction_bases',[column])
    op.create_table('business_finance_correction_refund_slices',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('basis_id',sa.Integer(),sa.ForeignKey('business_finance_correction_bases.id'),nullable=False),
        sa.Column('refund_payment_id',sa.Integer(),sa.ForeignKey('flow_payment_links.id'),nullable=False),
        sa.Column('original_payment_id',sa.Integer(),sa.ForeignKey('flow_payment_links.id'),nullable=False),
        sa.Column('source_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('basis_id','refund_payment_id',name='uq_finance_correction_refund_slice'),
        sa.CheckConstraint('amount_cents>0',name='ck_finance_correction_refund_slice'))
    for column in ('store_id','basis_id'):op.create_index('ix_business_finance_correction_refund_slices_'+column,'business_finance_correction_refund_slices',[column])


def downgrade():raise RuntimeError('原实退款及其更正切片不可自动抹除，请使用核验备份恢复')
