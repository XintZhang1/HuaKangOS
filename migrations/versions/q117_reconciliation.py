"""Frozen business reconciliation snapshots and two-store cash clearing."""
from alembic import op
import sqlalchemy as sa

revision = 'q117_reconciliation'
down_revision = 'p016_retail'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('interstore_clearing_buckets',
        sa.Column('origin_kind', sa.String(length=20), nullable=False),
        sa.Column('debtor_origin_id', sa.Integer(), nullable=False),
        sa.Column('creditor_origin_id', sa.Integer(), nullable=False),
        sa.Column('payer_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('receiver_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('total_cents', sa.BigInteger(), nullable=False),
        sa.Column('reserved_cents', sa.BigInteger(), nullable=False),
        sa.Column('settled_cents', sa.BigInteger(), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('total_cents>0 AND reserved_cents>=0 AND settled_cents>=0 AND reserved_cents+settled_cents<=total_cents', name='ck_clearing_bucket'),
        sa.CheckConstraint("origin_kind IN ('material','vehicle') AND payer_store_id!=receiver_store_id", name='ck_clearing_parties'),
        sa.UniqueConstraint('origin_kind','debtor_origin_id', name='uq_clearing_original'))
    op.create_table('reconciliation_receipts',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('store_id','request_key', name='uq_reconciliation_request'))
    op.create_index('ix_reconciliation_receipts_store_id','reconciliation_receipts',['store_id'], unique=False)
    op.create_table('interstore_clearing_orders',
        sa.Column('bucket_id', sa.Integer(), sa.ForeignKey('interstore_clearing_buckets.id'), nullable=False),
        sa.Column('payer_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('receiver_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('payer_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('receiver_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('payer_case_id', name=None),
        sa.UniqueConstraint('receiver_case_id', name=None),
        sa.CheckConstraint('amount_cents>0 AND payer_store_id!=receiver_store_id', name='ck_clearing_amount'),
        sa.CheckConstraint("status IN ('requested','paid','settled','cancelled')", name='ck_clearing_status'))
    op.create_index('ix_interstore_clearing_orders_bucket_id','interstore_clearing_orders',['bucket_id'], unique=False)
    op.create_table('reconciliation_batches',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('start', sa.Date(), nullable=False),
        sa.Column('end', sa.Date(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('previous_id', sa.Integer(), sa.ForeignKey('reconciliation_batches.id'), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('prepared_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('submitted_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('sealed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('sealed_at', sa.DateTime(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('previous_id', name=None),
        sa.UniqueConstraint('case_id', name=None),
        sa.CheckConstraint('"start"<="end" AND revision>0', name='ck_reconciliation_period'),
        sa.CheckConstraint("status!='sealed' OR (sealed_by IS NOT NULL AND sealed_at IS NOT NULL)", name='ck_reconciliation_sealed'),
        sa.CheckConstraint("status IN ('draft','review','sealed','superseded')", name='ck_reconciliation_status'),
        sa.UniqueConstraint('store_id','start','end','revision', name='uq_reconciliation_period_revision'))
    op.create_index('ix_reconciliation_batches_store_id','reconciliation_batches',['store_id'], unique=False)
    op.create_table('interstore_clearing_cash',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('interstore_clearing_orders.id'), nullable=False),
        sa.Column('cash_id', sa.Integer(), sa.ForeignKey('cash_entries.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=False),
        sa.Column('direction', sa.String(length=3), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('cash_id', name=None),
        sa.CheckConstraint("amount_cents>0 AND direction IN ('in','out')", name='ck_clearing_cash'),
        sa.UniqueConstraint('store_id','account_id','reference', name='uq_clearing_cash_reference'),
        sa.UniqueConstraint('order_id','direction', name='uq_clearing_cash_side'))
    op.create_index('ix_interstore_clearing_cash_order_id','interstore_clearing_cash',['order_id'], unique=False)
    op.create_index('ix_interstore_clearing_cash_store_id','interstore_clearing_cash',['store_id'], unique=False)
    op.create_table('interstore_clearing_offsets',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('interstore_clearing_orders.id'), nullable=False),
        sa.Column('origin_kind', sa.String(length=20), nullable=False),
        sa.Column('origin_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('amount_cents!=0', name='ck_clearing_offset'),
        sa.UniqueConstraint('order_id','store_id', name='uq_clearing_offset_party'))
    op.create_index('ix_interstore_clearing_offsets_order_id','interstore_clearing_offsets',['order_id'], unique=False)
    op.create_index('ix_interstore_clearing_offsets_store_id','interstore_clearing_offsets',['store_id'], unique=False)
    op.create_table('reconciliation_events',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False))
    op.create_index('ix_reconciliation_events_case_id','reconciliation_events',['case_id'], unique=False)
    op.create_index('ix_reconciliation_events_store_id','reconciliation_events',['store_id'], unique=False)
    op.create_table('reconciliation_issues',
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('reconciliation_batches.id'), nullable=False),
        sa.Column('line_key', sa.String(length=100), nullable=False),
        sa.Column('difference_cents', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('opened_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolution', sa.String(length=500), nullable=True),
        sa.Column('resolution_evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=True),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('open','resolved')", name='ck_reconciliation_issue'),
        sa.CheckConstraint("status!='resolved' OR (resolved_by IS NOT NULL AND resolution_evidence_id IS NOT NULL AND resolution IS NOT NULL)", name='ck_reconciliation_resolution'))
    op.create_index('ix_reconciliation_issues_batch_id','reconciliation_issues',['batch_id'], unique=False)
    op.create_index('ix_reconciliation_issues_store_id','reconciliation_issues',['store_id'], unique=False)


def downgrade():
    op.drop_table('reconciliation_issues')
    op.drop_table('reconciliation_events')
    op.drop_table('interstore_clearing_offsets')
    op.drop_table('interstore_clearing_cash')
    op.drop_table('reconciliation_batches')
    op.drop_table('interstore_clearing_orders')
    op.drop_table('reconciliation_receipts')
    op.drop_table('interstore_clearing_buckets')
