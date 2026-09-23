"""Same-amount membership renewal receipt corrections and original refund basis."""
from alembic import op
import sqlalchemy as sa

revision='e13r_member_fee_corrections'
down_revision='d02q_partial_corrections'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('business_entity_case_contexts') as batch:
        batch.drop_constraint('ck_entity_case_derivation',type_='check')
        batch.create_check_constraint('ck_entity_case_derivation',"(source_case_id IS NULL AND derived_kind IS NULL) OR (source_case_id IS NOT NULL AND derived_kind IS NOT NULL AND source_case_id<case_id AND derived_kind IN ('aftercare','invoice','vehicle_return','claim','advance_refund','finance_correction','other_return','vehicle_income','membership_refund'))")
    with op.batch_alter_table('business_finance_orders') as batch:
        batch.drop_constraint('ck_finance_order_purpose',type_='check')
        batch.create_check_constraint('ck_finance_order_purpose',"purpose IN ('advance','advance_apply','advance_refund','statement','correction','stored_correction','fee_correction','other_return','other_return_adjust','other_return_refund')")
    op.create_table('membership_fee_correction_requests',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),
        sa.Column('fee_id',sa.Integer(),sa.ForeignKey('membership_fees.id'),nullable=False),
        sa.Column('original_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False),
        sa.Column('original_account_id',sa.Integer(),sa.ForeignKey('flow_accounts.id'),nullable=False),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('flow_accounts.id'),nullable=False),
        sa.Column('reference',sa.String(100),nullable=False),sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('business_date',sa.Date(),nullable=False),sa.Column('source_version',sa.BigInteger(),nullable=False),
        sa.Column('refunded_fee_id',sa.Integer(),sa.ForeignKey('membership_fees.id'),nullable=True),sa.Column('status',sa.String(20),nullable=False),
        sa.CheckConstraint('amount_cents>0 AND source_version>0',name='ck_member_fee_correction_amount'),
        sa.CheckConstraint("status IN ('requested','reserved','applied','released')",name='ck_member_fee_correction_status'))
    op.create_table('membership_fee_corrections',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('request_id',sa.Integer(),sa.ForeignKey('membership_fee_correction_requests.id'),nullable=False,unique=True),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),
        sa.Column('fee_id',sa.Integer(),sa.ForeignKey('membership_fees.id'),nullable=False),
        sa.Column('original_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False,unique=True),
        sa.Column('reversing_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False,unique=True),
        sa.Column('corrected_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False,unique=True),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('occurred_at',sa.DateTime(),nullable=False))
    op.create_table('membership_fee_refund_bases',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('refund_fee_id',sa.Integer(),sa.ForeignKey('membership_fees.id'),nullable=False,unique=True),
        sa.Column('original_fee_id',sa.Integer(),sa.ForeignKey('membership_fees.id'),nullable=False),
        sa.Column('original_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    for name in ('membership_fee_correction_requests','membership_fee_corrections','membership_fee_refund_bases'):
        op.create_index('ix_'+name+'_store_id',name,['store_id'])
        if name!='membership_fee_refund_bases':op.create_index('ix_'+name+'_fee_id',name,['fee_id'])


def downgrade():raise RuntimeError('续会费更正及真实退款依据不可自动删除，请用核验备份恢复')
