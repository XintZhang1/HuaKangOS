"""Original manufacturer/supplier vehicle income and frozen source identity."""
from alembic import op
import sqlalchemy as sa
revision='y57l_vehicle_income'
down_revision='x46k_supplier_overpayment'
branch_labels=None
depends_on=None

def local():return [sa.Column('store_id',sa.Integer(),nullable=False)]
def fact():return [sa.Column('id',sa.Integer(),primary_key=True),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False)]

def upgrade():
    op.create_table('vehicle_income_orders',*local(),sa.Column('id',sa.Integer(),sa.ForeignKey('flow_cases.id'),primary_key=True),
        sa.Column('supplier_id',sa.Integer(),sa.ForeignKey('master_suppliers.id'),nullable=False),sa.Column('supplier_snapshot',sa.JSON(),nullable=False),
        sa.Column('external_reference',sa.String(120),nullable=False),sa.Column('primary_source_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.UniqueConstraint('store_id','supplier_id','external_reference',name='uq_vehicle_income_external'))
    op.create_table('vehicle_income_sources',*local(),sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('vehicle_income_orders.id'),nullable=False),sa.Column('source_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('source_version',sa.Integer(),nullable=False),sa.Column('vehicle_id',sa.Integer(),sa.ForeignKey('vehicles.id'),nullable=True),
        sa.Column('snapshot',sa.JSON(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),sa.UniqueConstraint('case_id','source_case_id','vehicle_id',name='uq_vehicle_income_source'))
    op.create_table('vehicle_income_revisions',*local(),*fact(),sa.Column('case_id',sa.Integer(),sa.ForeignKey('vehicle_income_orders.id'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('previous_id',sa.Integer(),sa.ForeignKey('vehicle_income_revisions.id'),nullable=True),
        sa.Column('previous_cents',sa.BigInteger(),nullable=False),sa.Column('target_cents',sa.BigInteger(),nullable=False),sa.Column('invoice_mode',sa.String(25),nullable=False),
        sa.Column('due_date',sa.Date(),nullable=False),sa.Column('source_versions',sa.JSON(),nullable=False),sa.Column('reason',sa.String(1000),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),sa.Column('digest',sa.String(64),nullable=False),
        sa.UniqueConstraint('case_id','revision',name='uq_vehicle_income_revision'),sa.CheckConstraint("target_cents>=0 AND previous_cents>=0 AND invoice_mode IN ('store_invoice','external_document')",name='ck_vehicle_income_revision'))
    op.create_table('vehicle_income_decisions',*local(),*fact(),sa.Column('revision_id',sa.Integer(),sa.ForeignKey('vehicle_income_revisions.id'),nullable=False,unique=True),
        sa.Column('decision',sa.String(12),nullable=False),sa.Column('reason',sa.String(1000),nullable=False),sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=True),
        sa.Column('business_date',sa.Date(),nullable=False),sa.CheckConstraint("decision IN ('approved','rejected','withdrawn') AND (decision='withdrawn' OR evidence_id IS NOT NULL)",name='ck_vehicle_income_decision'))
    op.create_table('vehicle_income_cash',*local(),*fact(),sa.Column('case_id',sa.Integer(),sa.ForeignKey('vehicle_income_orders.id'),nullable=False),
        sa.Column('revision_id',sa.Integer(),sa.ForeignKey('vehicle_income_revisions.id'),nullable=False),sa.Column('original_id',sa.Integer(),sa.ForeignKey('vehicle_income_cash.id'),nullable=True),
        sa.Column('direction',sa.String(3),nullable=False),sa.Column('amount_cents',sa.BigInteger(),nullable=False),sa.Column('cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False,unique=True),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('flow_accounts.id'),nullable=False),sa.Column('account_snapshot',sa.JSON(),nullable=False),sa.Column('reference',sa.String(100),nullable=False),sa.Column('business_date',sa.Date(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),sa.CheckConstraint("amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))",name='ck_vehicle_income_cash'))
    op.create_table('vehicle_income_receipts',*local(),*fact(),sa.Column('request_key',sa.String(80),nullable=False),sa.Column('digest',sa.String(64),nullable=False),sa.Column('result',sa.JSON(),nullable=False),sa.UniqueConstraint('store_id','request_key',name='uq_vehicle_income_request'))
    for name,fields in {'vehicle_income_orders':('supplier_id',),'vehicle_income_sources':('case_id','source_case_id'),
        'vehicle_income_revisions':('case_id',),'vehicle_income_decisions':(),'vehicle_income_cash':('case_id','original_id'),'vehicle_income_receipts':()}.items():
        for field in ('store_id',*fields):op.create_index('ix_'+name+'_'+field,name,[field])
    with op.batch_alter_table('business_entity_case_contexts') as batch:
        batch.drop_constraint('ck_entity_case_derivation',type_='check')
        batch.create_check_constraint('ck_entity_case_derivation',"(source_case_id IS NULL AND derived_kind IS NULL) OR (source_case_id IS NOT NULL AND derived_kind IS NOT NULL AND source_case_id<case_id AND derived_kind IN ('aftercare','invoice','vehicle_return','claim','advance_refund','finance_correction','other_return','vehicle_income'))")

def downgrade():raise RuntimeError('原收入、现金与主体事实不可自动删除；请使用已验证的完整备份恢复')
