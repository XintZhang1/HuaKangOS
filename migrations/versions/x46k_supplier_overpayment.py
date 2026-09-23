"""Supplier return overpayments remain actual cash until separately refunded."""
from alembic import op
import sqlalchemy as sa

revision='x46k_supplier_overpayment'
down_revision='w35j_addon_gifts'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('business_finance_orders') as b:
        b.drop_constraint('ck_finance_order_purpose',type_='check')
        b.create_check_constraint('ck_finance_order_purpose',"purpose IN ('advance','advance_apply','advance_refund','statement','correction','stored_correction','other_return','other_return_adjust','other_return_refund')")
    with op.batch_alter_table('business_finance_cash_batches') as b:
        b.drop_constraint('ck_finance_cash_batch',type_='check')
        b.create_check_constraint('ck_finance_cash_batch',"kind IN ('collection','correction_reverse','correction_record','supplier_refund') AND amount_cents>0")
    with op.batch_alter_table('business_finance_return_target_revisions') as b:
        b.drop_constraint('ck_finance_return_target_amount',type_='check')
        b.create_check_constraint('ck_finance_return_target_amount','revision>0 AND original_amount_cents>=0 AND amount_cents>=0 AND received_cents>=0')
    op.create_table('business_finance_supplier_refunds',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),
        sa.Column('receivable_id',sa.Integer(),sa.ForeignKey('business_finance_return_receivables.id'),nullable=False),
        sa.Column('original_payment_id',sa.Integer(),sa.ForeignKey('flow_payment_links.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('applied_batch_id',sa.Integer(),sa.ForeignKey('business_finance_cash_batches.id'),unique=True),
        sa.CheckConstraint("amount_cents>0 AND status IN ('requested','reserved','applied','released')",name='ck_finance_supplier_refund_status'),
        sa.CheckConstraint("(status='applied' AND applied_batch_id IS NOT NULL) OR (status!='applied' AND applied_batch_id IS NULL)",name='ck_finance_supplier_refund_applied'))
    for column in ('store_id','receivable_id','original_payment_id'):op.create_index('ix_business_finance_supplier_refunds_'+column,'business_finance_supplier_refunds',[column])


def downgrade():raise RuntimeError('供应方实际原款退款及已批准应退责任不可自动抹除；请使用核验备份恢复')
