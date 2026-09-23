"""Frozen original-source aftercare agreements, offsets and actual refunds."""
from alembic import op
import sqlalchemy as sa
revision="w723_aftercare"
down_revision="v622_vehicle_operations"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('aftercare_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_case_id', sa.Integer(), nullable=False),
    sa.Column('scenario', sa.String(length=30), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('requested_by', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("scenario IN ('sale_termination','vehicle_return','repair_refund')", name='ck_aftercare_scenario'),
    sa.ForeignKeyConstraint(['id'], ['flow_cases.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['source_case_id'], ['flow_cases.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aftercare_orders_source_case_id'), 'aftercare_orders', ['source_case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_orders_store_id'), 'aftercare_orders', ['store_id'], unique=False)
    op.create_table('aftercare_receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('request_key', sa.String(length=80), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('store_id', 'request_key', name='uq_aftercare_receipt')
    )
    op.create_index(op.f('ix_aftercare_receipts_store_id'), 'aftercare_receipts', ['store_id'], unique=False)
    op.create_table('aftercare_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('source_case_id', sa.Integer(), nullable=False),
    sa.Column('allocation_id', sa.Integer(), nullable=True),
    sa.Column('original_cents', sa.BigInteger(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('original_cents>=0', name='ck_aftercare_source_amount'),
    sa.ForeignKeyConstraint(['allocation_id'], ['repair_allocations.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['source_case_id'], ['flow_cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'source_case_id', name='uq_aftercare_source')
    )
    op.create_index(op.f('ix_aftercare_sources_case_id'), 'aftercare_sources', ['case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_sources_source_case_id'), 'aftercare_sources', ['source_case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_sources_store_id'), 'aftercare_sources', ['store_id'], unique=False)
    op.create_table('aftercare_claims',
    sa.Column('source_case_id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['source_case_id'], ['flow_cases.id'], ),
    sa.PrimaryKeyConstraint('source_case_id')
    )
    op.create_index(op.f('ix_aftercare_claims_case_id'), 'aftercare_claims', ['case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_claims_store_id'), 'aftercare_claims', ['store_id'], unique=False)
    op.create_table('aftercare_plans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id', 'revision', name='uq_aftercare_plan_revision')
    )
    op.create_index(op.f('ix_aftercare_plans_case_id'), 'aftercare_plans', ['case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_plans_store_id'), 'aftercare_plans', ['store_id'], unique=False)
    op.create_table('aftercare_execution_facts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('external_result', sa.String(length=30), nullable=False),
    sa.Column('result', sa.String(length=1000), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("outcome IN ('not_started','stopped','completed') AND external_result IN ('not_required','terminated')", name='ck_aftercare_execution'),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['aftercare_sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_aftercare_execution_facts_case_id'), 'aftercare_execution_facts', ['case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_execution_facts_source_id'), 'aftercare_execution_facts', ['source_id'], unique=False)
    op.create_index(op.f('ix_aftercare_execution_facts_store_id'), 'aftercare_execution_facts', ['store_id'], unique=False)
    op.create_table('aftercare_tenders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('original_id', sa.Integer(), nullable=False),
    sa.Column('units', sa.BigInteger(), nullable=False),
    sa.Column('credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('discount_cents', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("kind IN ('cash','principal','benefit','advance') AND units>0 AND credit_cents>0", name='ck_aftercare_tender'),
    sa.ForeignKeyConstraint(['plan_id'], ['aftercare_plans.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['aftercare_sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_id', 'kind', 'original_id', name='uq_aftercare_tender_origin')
    )
    op.create_index(op.f('ix_aftercare_tenders_plan_id'), 'aftercare_tenders', ['plan_id'], unique=False)
    op.create_index(op.f('ix_aftercare_tenders_store_id'), 'aftercare_tenders', ['store_id'], unique=False)
    op.create_table('aftercare_approvals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['aftercare_plans.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_id')
    )
    op.create_index(op.f('ix_aftercare_approvals_store_id'), 'aftercare_approvals', ['store_id'], unique=False)
    op.create_table('aftercare_consents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('plan_digest', sa.String(length=64), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['aftercare_plans.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_id')
    )
    op.create_index(op.f('ix_aftercare_consents_store_id'), 'aftercare_consents', ['store_id'], unique=False)
    op.create_table('aftercare_plan_cancellations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['aftercare_plans.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_id')
    )
    op.create_index(op.f('ix_aftercare_plan_cancellations_store_id'), 'aftercare_plan_cancellations', ['store_id'], unique=False)
    op.create_table('aftercare_applications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('business_date', sa.Date(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['aftercare_plans.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('case_id'),
    sa.UniqueConstraint('plan_id')
    )
    op.create_index(op.f('ix_aftercare_applications_store_id'), 'aftercare_applications', ['store_id'], unique=False)
    op.create_table('aftercare_cash_collections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('payment_link_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['payment_link_id'], ['flow_payment_links.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['aftercare_sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payment_link_id')
    )
    op.create_index(op.f('ix_aftercare_cash_collections_case_id'), 'aftercare_cash_collections', ['case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_cash_collections_store_id'), 'aftercare_cash_collections', ['store_id'], unique=False)
    op.create_table('aftercare_plan_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('execution_id', sa.Integer(), nullable=True),
    sa.Column('base_cents', sa.BigInteger(), nullable=False),
    sa.Column('credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('retained_cents', sa.BigInteger(), nullable=False),
    sa.Column('refund_cents', sa.BigInteger(), nullable=False),
    sa.Column('revenue_credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('credit_cents>=0 AND retained_cents>=0 AND refund_cents>=0 AND base_cents=credit_cents+retained_cents', name='ck_aftercare_plan_amount'),
    sa.ForeignKeyConstraint(['execution_id'], ['aftercare_execution_facts.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['aftercare_plans.id'], ),
    sa.ForeignKeyConstraint(['source_id'], ['aftercare_sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_id', 'source_id', name='uq_aftercare_plan_source')
    )
    op.create_index(op.f('ix_aftercare_plan_lines_plan_id'), 'aftercare_plan_lines', ['plan_id'], unique=False)
    op.create_index(op.f('ix_aftercare_plan_lines_store_id'), 'aftercare_plan_lines', ['store_id'], unique=False)
    op.create_table('aftercare_cash_refunds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('payment_link_id', sa.Integer(), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['case_id'], ['aftercare_orders.id'], ),
    sa.ForeignKeyConstraint(['evidence_id'], ['flow_files.id'], ),
    sa.ForeignKeyConstraint(['payment_link_id'], ['flow_payment_links.id'], ),
    sa.ForeignKeyConstraint(['tender_id'], ['aftercare_tenders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payment_link_id')
    )
    op.create_index(op.f('ix_aftercare_cash_refunds_case_id'), 'aftercare_cash_refunds', ['case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_cash_refunds_store_id'), 'aftercare_cash_refunds', ['store_id'], unique=False)
    op.create_index(op.f('ix_aftercare_cash_refunds_tender_id'), 'aftercare_cash_refunds', ['tender_id'], unique=False)
    op.create_table('aftercare_adjustments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('plan_line_id', sa.Integer(), nullable=False),
    sa.Column('source_case_id', sa.Integer(), nullable=False),
    sa.Column('allocation_id', sa.Integer(), nullable=True),
    sa.Column('credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('revenue_credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('store_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('credit_cents>=0', name='ck_aftercare_adjustment'),
    sa.ForeignKeyConstraint(['allocation_id'], ['repair_allocations.id'], ),
    sa.ForeignKeyConstraint(['application_id'], ['aftercare_applications.id'], ),
    sa.ForeignKeyConstraint(['plan_line_id'], ['aftercare_plan_lines.id'], ),
    sa.ForeignKeyConstraint(['source_case_id'], ['flow_cases.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('plan_line_id')
    )
    op.create_index(op.f('ix_aftercare_adjustments_application_id'), 'aftercare_adjustments', ['application_id'], unique=False)
    op.create_index(op.f('ix_aftercare_adjustments_source_case_id'), 'aftercare_adjustments', ['source_case_id'], unique=False)
    op.create_index(op.f('ix_aftercare_adjustments_store_id'), 'aftercare_adjustments', ['store_id'], unique=False)

def downgrade():
    op.drop_table('aftercare_adjustments')
    op.drop_table('aftercare_cash_refunds')
    op.drop_table('aftercare_plan_lines')
    op.drop_table('aftercare_cash_collections')
    op.drop_table('aftercare_applications')
    op.drop_table('aftercare_plan_cancellations')
    op.drop_table('aftercare_consents')
    op.drop_table('aftercare_approvals')
    op.drop_table('aftercare_tenders')
    op.drop_table('aftercare_execution_facts')
    op.drop_table('aftercare_plans')
    op.drop_table('aftercare_claims')
    op.drop_table('aftercare_sources')
    op.drop_table('aftercare_receipts')
    op.drop_table('aftercare_orders')
