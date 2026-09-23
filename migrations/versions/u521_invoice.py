"""Frozen internal invoice applications, independent approval and actual results."""
from alembic import op
import sqlalchemy as sa

revision='u521_invoice'
down_revision='t420_service_intake'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('invoice_applications',
        sa.Column('id',sa.Integer(),sa.ForeignKey('flow_cases.id'),primary_key=True),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('source_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('original_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=True),
        sa.Column('direction',sa.String(10),nullable=False),sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('issuer_name',sa.String(160),nullable=False),sa.Column('issuer_tax_id',sa.String(20),nullable=False),
        sa.Column('buyer_name',sa.String(160),nullable=False),sa.Column('buyer_tax_id',sa.String(20),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),sa.Column('source_version',sa.Integer(),nullable=False),
        sa.CheckConstraint("amount_cents>0 AND ((direction='blue' AND original_case_id IS NULL) OR (direction='red' AND original_case_id IS NOT NULL))",name='ck_invoice_application'))
    for field in ('store_id','source_case_id','original_case_id'):op.create_index('ix_invoice_applications_'+field,'invoice_applications',[field])
    op.create_table('invoice_approvals',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('invoice_applications.id'),nullable=False,unique=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False))
    op.create_index('ix_invoice_approvals_store_id','invoice_approvals',['store_id'])
    op.create_table('invoice_results',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('invoice_applications.id'),nullable=False,unique=True),
        sa.Column('invoice_number',sa.String(60),nullable=False),sa.Column('issuer_tax_id',sa.String(20),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),sa.Column('issued_on',sa.Date(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.UniqueConstraint('issuer_tax_id','invoice_number',name='uq_invoice_issuer_number'),
        sa.CheckConstraint('amount_cents>0',name='ck_invoice_result_amount'))
    for field in ('store_id','issued_on'):op.create_index('ix_invoice_results_'+field,'invoice_results',[field])

def downgrade():
    for name in ('invoice_results','invoice_approvals','invoice_applications'):op.drop_table(name)
