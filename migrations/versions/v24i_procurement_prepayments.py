"""Explicit material procurement advance approval and original receipt allocations."""
from alembic import op
import sqlalchemy as sa
revision='v24i_procurement_prepayments'
down_revision='u13h_finance_corrections'
branch_labels=None
depends_on=None


def local():return [sa.Column('store_id',sa.Integer(),nullable=False)]
def identity():return [sa.Column('id',sa.Integer(),primary_key=True)]
def created():return [sa.Column('created_at',sa.DateTime(),nullable=False)]


def upgrade():
    op.create_table('procurement_prepayment_facilities',
        sa.Column('id',sa.Integer(),sa.ForeignKey('procurement_orders.id'),primary_key=True),*local(),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),*created())
    op.create_table('procurement_prepayment_requests',*identity(),*local(),*created(),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('procurement_prepayment_facilities.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),sa.Column('valid_until',sa.Date(),nullable=False),
        sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('reason',sa.String(500),nullable=False),sa.Column('status',sa.String(16),nullable=False),
        sa.CheckConstraint("amount_cents>0 AND status IN ('pending','approved','rejected','cancelled','expired','paid')",name='ck_purchase_prepay_request'))
    op.create_table('procurement_prepayment_decisions',*identity(),*local(),*created(),
        sa.Column('request_id',sa.Integer(),sa.ForeignKey('procurement_prepayment_requests.id'),nullable=False),
        sa.Column('action',sa.String(16),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=True),sa.Column('reason',sa.String(500),nullable=False),
        sa.UniqueConstraint('request_id','action',name='uq_purchase_prepay_decision'),
        sa.CheckConstraint("action IN ('approve','reject','cancel','expire')",name='ck_purchase_prepay_decision'))
    op.create_table('procurement_prepayment_disbursements',*identity(),*local(),*created(),
        sa.Column('request_id',sa.Integer(),sa.ForeignKey('procurement_prepayment_requests.id'),nullable=False),
        sa.Column('payment_id',sa.Integer(),sa.ForeignKey('procurement_payments.id'),nullable=False,unique=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False))
    op.create_table('procurement_payment_allocations',*identity(),*local(),*created(),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('procurement_prepayment_facilities.id'),nullable=False),
        sa.Column('payment_id',sa.Integer(),sa.ForeignKey('procurement_payments.id'),nullable=False),
        sa.Column('receipt_id',sa.Integer(),sa.ForeignKey('procurement_receipts.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('original_id',sa.Integer(),sa.ForeignKey('procurement_payment_allocations.id'),nullable=True),
        sa.Column('return_posting_id',sa.Integer(),sa.ForeignKey('procurement_return_postings.id'),nullable=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.CheckConstraint('(amount_cents>0 AND original_id IS NULL AND return_posting_id IS NULL) OR (amount_cents<0 AND original_id IS NOT NULL AND return_posting_id IS NOT NULL)',name='ck_purchase_payment_allocation'))
    for name,fields in {
        'procurement_prepayment_facilities':(), 'procurement_prepayment_requests':('case_id',),
        'procurement_prepayment_decisions':('request_id',),'procurement_prepayment_disbursements':('request_id',),
        'procurement_payment_allocations':('case_id','payment_id','receipt_id')}.items():
        for field in ('store_id',*fields):op.create_index('ix_'+name+'_'+field,name,[field])


def downgrade():raise RuntimeError('原采购付款及抵用事实不可自动删除；请使用经过验证的完整备份恢复')
