"""Frozen v3 transport loss, independent recovery and original clearing sources."""
from alembic import op
import sqlalchemy as sa

revision='m359_transfer_exceptions'
down_revision='l248_business_entities'
branch_labels=None
depends_on=None


def upgrade():
    check_names={c['name'] for c in sa.inspect(op.get_bind()).get_check_constraints('interstore_clearing_buckets')}
    if 'ck_clearing_parties' not in check_names:raise RuntimeError('Expected original clearing-party constraint; inspect the isolated migration copy')
    with op.batch_alter_table('interstore_clearing_buckets') as batch:
        batch.drop_constraint('ck_clearing_parties',type_='check')
        batch.create_check_constraint('ck_clearing_parties',"origin_kind IN ('material','vehicle','material_loss') AND payer_store_id!=receiver_store_id")
    op.create_table('transfer_exception_receipts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('store_id', 'request_key', name='uq_transfer_exception_request'),
    )
    op.create_index('ix_transfer_exception_receipts_store_id', 'transfer_exception_receipts', ['store_id'], unique=False)
    op.create_table('transfer_exceptions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('active_transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=True),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('material_transfer_movements.id'), nullable=False),
        sa.Column('stage', sa.String(length=15), nullable=False),
        sa.Column('finding', sa.String(length=15), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('request_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("(status IN ('posted','cancelled') AND active_transfer_id IS NULL) OR (status NOT IN ('posted','cancelled') AND active_transfer_id IS NOT NULL AND active_transfer_id=transfer_id)", name='ck_transfer_exception_active'),
        sa.CheckConstraint('quantity_milli>0 AND value_cents>=0', name='ck_transfer_exception_amount'),
        sa.CheckConstraint("stage IN ('outbound','rejected','returning') AND finding IN ('missing','damaged')", name='ck_transfer_exception_origin'),
        sa.CheckConstraint("status IN ('investigating','review','approved','disposed','posted','cancelled')", name='ck_transfer_exception_status'),
        sa.UniqueConstraint('active_transfer_id'),
    )
    op.create_index('ix_transfer_exceptions_original_id', 'transfer_exceptions', ['original_id'], unique=False)
    op.create_index('ix_transfer_exceptions_transfer_id', 'transfer_exceptions', ['transfer_id'], unique=False)
    op.create_table('transfer_exception_cancellations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('exception_id'),
    )
    op.create_table('transfer_exception_observations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('observation', sa.String(length=30), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('result', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("observation IN ('dispatch_verified','return_dispatch_verified','missing','held_damaged') AND quantity_milli>0", name='ck_transfer_exception_observation'),
    )
    op.create_index('ix_transfer_exception_observations_exception_id', 'transfer_exception_observations', ['exception_id'], unique=False)
    op.create_table('transfer_recovery_claims',
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('counterparty_kind', sa.String(length=12), nullable=False),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('master_suppliers.id'), nullable=True),
        sa.Column('insurer_id', sa.Integer(), sa.ForeignKey('master_insurers.id'), nullable=True),
        sa.Column('counterparty_snapshot', sa.JSON(), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("(counterparty_kind='carrier' AND supplier_id IS NOT NULL AND insurer_id IS NULL) OR (counterparty_kind='insurer' AND insurer_id IS NOT NULL AND supplier_id IS NULL)", name='ck_transfer_recovery_party'),
    )
    op.create_index('ix_transfer_recovery_claims_exception_id', 'transfer_recovery_claims', ['exception_id'], unique=False)
    op.create_index('ix_transfer_recovery_claims_store_id', 'transfer_recovery_claims', ['store_id'], unique=False)
    op.create_table('transfer_exception_plans',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('source_observation_id', sa.Integer(), sa.ForeignKey('transfer_exception_observations.id'), nullable=False),
        sa.Column('destination_observation_id', sa.Integer(), sa.ForeignKey('transfer_exception_observations.id'), nullable=False),
        sa.Column('source_bearer_cents', sa.BigInteger(), nullable=False),
        sa.Column('destination_bearer_cents', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('revision>0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0', name='ck_transfer_exception_plan_amount'),
        sa.UniqueConstraint('exception_id', 'revision', name='uq_transfer_exception_plan_revision'),
    )
    op.create_index('ix_transfer_exception_plans_exception_id', 'transfer_exception_plans', ['exception_id'], unique=False)
    op.create_table('transfer_recovery_plans',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('claim_id', sa.Integer(), sa.ForeignKey('transfer_recovery_claims.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('target_cents', sa.BigInteger(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('target_cents>=0', name='ck_transfer_recovery_target'),
        sa.UniqueConstraint('claim_id', 'revision', name='uq_transfer_recovery_revision'),
    )
    op.create_index('ix_transfer_recovery_plans_claim_id', 'transfer_recovery_plans', ['claim_id'], unique=False)
    op.create_index('ix_transfer_recovery_plans_store_id', 'transfer_recovery_plans', ['store_id'], unique=False)
    op.create_table('transfer_exception_disposals',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_exception_plans.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('method', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('quantity_milli>0', name='ck_transfer_exception_disposal_quantity'),
        sa.UniqueConstraint('exception_id'),
    )
    op.create_table('transfer_exception_reviews',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_exception_plans.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('decision', sa.String(length=10), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('approve','reject')", name='ck_transfer_exception_review_decision'),
        sa.UniqueConstraint('plan_id', 'store_id', name='uq_transfer_exception_review_party'),
    )
    op.create_index('ix_transfer_exception_reviews_plan_id', 'transfer_exception_reviews', ['plan_id'], unique=False)
    op.create_table('transfer_loss_postings',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('line_id', sa.Integer(), sa.ForeignKey('material_transfer_lines.id'), nullable=False),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('material_transfer_movements.id'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_exception_plans.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('source_bearer_cents', sa.BigInteger(), nullable=False),
        sa.Column('destination_bearer_cents', sa.BigInteger(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('quantity_milli>0 AND value_cents>=0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0 AND source_bearer_cents+destination_bearer_cents=value_cents', name='ck_transfer_loss_conservation'),
        sa.UniqueConstraint('exception_id'),
        sa.UniqueConstraint('plan_id'),
    )
    op.create_index('ix_transfer_loss_postings_line_id', 'transfer_loss_postings', ['line_id'], unique=False)
    op.create_index('ix_transfer_loss_postings_store_id', 'transfer_loss_postings', ['store_id'], unique=False)
    op.create_index('ix_transfer_loss_postings_transfer_id', 'transfer_loss_postings', ['transfer_id'], unique=False)
    op.create_table('transfer_recovery_cancellations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_recovery_plans.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('plan_id'),
    )
    op.create_index('ix_transfer_recovery_cancellations_store_id', 'transfer_recovery_cancellations', ['store_id'], unique=False)
    op.create_table('transfer_recovery_payments',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('claim_id', sa.Integer(), sa.ForeignKey('transfer_recovery_claims.id'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_recovery_plans.id'), nullable=False),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('transfer_recovery_payments.id'), nullable=True),
        sa.Column('direction', sa.String(length=3), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=False),
        sa.Column('cash_id', sa.Integer(), sa.ForeignKey('cash_entries.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))", name='ck_transfer_recovery_payment'),
        sa.UniqueConstraint('cash_id'),
    )
    op.create_index('ix_transfer_recovery_payments_claim_id', 'transfer_recovery_payments', ['claim_id'], unique=False)
    op.create_index('ix_transfer_recovery_payments_store_id', 'transfer_recovery_payments', ['store_id'], unique=False)
    op.create_table('transfer_recovery_reviews',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_recovery_plans.id'), nullable=False),
        sa.Column('decision', sa.String(length=10), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("decision IN ('approve','reject')", name='ck_transfer_recovery_review'),
        sa.UniqueConstraint('plan_id'),
    )
    op.create_index('ix_transfer_recovery_reviews_store_id', 'transfer_recovery_reviews', ['store_id'], unique=False)
    op.create_table('transfer_loss_settlements',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('posting_id', sa.Integer(), sa.ForeignKey('transfer_loss_postings.id'), nullable=False),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('counterparty_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('amount_cents!=0', name='ck_transfer_loss_settlement_amount'),
        sa.UniqueConstraint('posting_id', 'store_id', name='uq_transfer_loss_settlement_party'),
    )
    op.create_index('ix_transfer_loss_settlements_exception_id', 'transfer_loss_settlements', ['exception_id'], unique=False)
    op.create_index('ix_transfer_loss_settlements_posting_id', 'transfer_loss_settlements', ['posting_id'], unique=False)
    op.create_index('ix_transfer_loss_settlements_store_id', 'transfer_loss_settlements', ['store_id'], unique=False)
    op.create_index('ix_transfer_loss_settlements_transfer_id', 'transfer_loss_settlements', ['transfer_id'], unique=False)


def downgrade():
    raise RuntimeError('Transport loss and original recovery facts require a reviewed backup restore; no destructive downgrade')
