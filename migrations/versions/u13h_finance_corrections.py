"""Append-only original receipt corrections and supplier return target revisions."""
from alembic import op
import sqlalchemy as sa

revision='u13h_finance_corrections'
down_revision='t02g_master_completion'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('business_finance_orders') as b:
        b.drop_constraint('ck_finance_order_purpose',type_='check')
        b.create_check_constraint('ck_finance_order_purpose',"purpose IN ('advance','advance_apply','advance_refund','statement','correction','stored_correction','other_return','other_return_adjust')")
    with op.batch_alter_table('business_finance_advances') as b:
        b.add_column(sa.Column('correction_cents',sa.BigInteger(),nullable=False,server_default='0'))
        b.drop_constraint('ck_finance_advance_available',type_='check')
        b.create_check_constraint('ck_finance_advance_available','initial_cents>0 AND 0<=reserved_cents AND reserved_cents<=balance_cents AND balance_cents<=initial_cents+correction_cents')
    with op.batch_alter_table('business_finance_advance_entries') as b:
        b.drop_constraint('ck_finance_advance_entry',type_='check')
        b.create_check_constraint('ck_finance_advance_entry',"(purpose IN ('receive','return') AND amount_cents>0) OR (purpose IN ('apply','refund') AND amount_cents<0) OR (purpose='correction' AND amount_cents!=0)")
    with op.batch_alter_table('business_finance_corrections') as b:
        b.alter_column('corrected_batch_id',existing_type=sa.Integer(),nullable=True)
    with op.batch_alter_table('group_entries') as b:
        for name in ('ck_group_entry_sign','ck_group_entry_cash','ck_group_entry_original'):b.drop_constraint(name,type_='check')
        b.create_check_constraint('ck_group_entry_sign',"(purpose IN ('topup','reverse') AND amount_cents>0) OR (purpose IN ('capture','refund') AND amount_cents<0) OR (purpose='correction' AND amount_cents!=0)")
        b.create_check_constraint('ck_group_entry_cash',"(purpose IN ('topup','refund') AND cash_id IS NOT NULL AND account_id IS NOT NULL AND reference IS NOT NULL) OR (purpose IN ('capture','reverse','correction') AND cash_id IS NULL AND account_id IS NULL AND reference IS NULL)")
        b.create_check_constraint('ck_group_entry_original',"(purpose='topup' AND original_id IS NULL) OR purpose='capture' OR (purpose IN ('refund','reverse','correction') AND original_id IS NOT NULL)")
    op.create_table('business_finance_stored_correction_requests',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),sa.Column('source_kind',sa.String(20),nullable=False),
        sa.Column('advance_id',sa.Integer(),sa.ForeignKey('business_finance_advances.id')),sa.Column('member_id',sa.Integer(),sa.ForeignKey('group_members.id')),
        sa.Column('topup_id',sa.Integer(),sa.ForeignKey('group_entries.id')),sa.Column('original_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False),
        sa.Column('original_amount_cents',sa.BigInteger(),nullable=False),sa.Column('corrected_amount_cents',sa.BigInteger(),nullable=False),sa.Column('reserved_cents',sa.BigInteger(),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.CheckConstraint("(source_kind='advance' AND advance_id IS NOT NULL AND member_id IS NULL AND topup_id IS NULL) OR (source_kind='member' AND advance_id IS NULL AND member_id IS NOT NULL AND topup_id IS NOT NULL)",name='ck_finance_stored_source'),
        sa.CheckConstraint('original_amount_cents>0 AND corrected_amount_cents>=0 AND reserved_cents>=0',name='ck_finance_stored_amount'),
        sa.CheckConstraint("status IN ('requested','reserved','applied','released')",name='ck_finance_stored_status'))
    for column in ('store_id','advance_id','member_id','topup_id'):op.create_index('ix_business_finance_stored_correction_requests_'+column,'business_finance_stored_correction_requests',[column])
    op.create_table('business_finance_stored_corrections',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('request_id',sa.Integer(),sa.ForeignKey('business_finance_stored_correction_requests.id'),nullable=False,unique=True),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),
        sa.Column('original_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False,unique=True),
        sa.Column('reversing_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=False,unique=True),
        sa.Column('corrected_cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),unique=True),
        sa.Column('advance_entry_id',sa.Integer(),sa.ForeignKey('business_finance_advance_entries.id'),unique=True),
        sa.Column('group_entry_id',sa.Integer(),sa.ForeignKey('group_entries.id'),unique=True),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('occurred_at',sa.DateTime(),nullable=False))
    op.create_index('ix_business_finance_stored_corrections_store_id','business_finance_stored_corrections',['store_id'])
    op.create_table('business_finance_return_target_revisions',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False,unique=True),
        sa.Column('receivable_id',sa.Integer(),sa.ForeignKey('business_finance_return_receivables.id'),nullable=False),
        sa.Column('revision',sa.BigInteger(),nullable=False),sa.Column('previous_id',sa.Integer(),sa.ForeignKey('business_finance_return_target_revisions.id'),unique=True),
        sa.Column('original_amount_cents',sa.BigInteger(),nullable=False),sa.Column('amount_cents',sa.BigInteger(),nullable=False),sa.Column('received_cents',sa.BigInteger(),nullable=False),sa.Column('received_payment_ids',sa.JSON(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('receivable_id','revision',name='uq_finance_return_target_revision'),
        sa.CheckConstraint('revision>0 AND original_amount_cents>=0 AND amount_cents>=received_cents AND received_cents>=0',name='ck_finance_return_target_amount'))
    for column in ('store_id','receivable_id'):op.create_index('ix_business_finance_return_target_revisions_'+column,'business_finance_return_target_revisions',[column])


def downgrade():
    raise RuntimeError('现金更正与余额和应收修订不可自动抹除；请使用已核验整库备份恢复')
