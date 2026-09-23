"""Frozen retail benefit allocation, corrected reminders and original goods recovery."""
from alembic import op
import sqlalchemy as sa

revision='n46a_operations_extensions'
down_revision='m359_transfer_exceptions'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('interstore_clearing_buckets') as batch:
        batch.drop_constraint('ck_clearing_parties',type_='check')
        batch.create_check_constraint('ck_clearing_parties',"origin_kind IN ('material','vehicle','material_loss','material_found') AND payer_store_id!=receiver_store_id")
    op.create_table('observation_correction_receipts',
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('store_id', 'request_key', name='uq_observation_correction_receipt'),
    )
    op.create_index('ix_observation_correction_receipts_store_id', 'observation_correction_receipts', ['store_id'], unique=False)
    op.create_table('retail_group_eligibility',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('rule_id', sa.Integer(), sa.ForeignKey('benefit_rules.id'), nullable=False),
        sa.Column('issuer_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('partial_return_mode', sa.String(length=40), nullable=False),
        sa.Column('expiry_mode', sa.String(length=40), nullable=False),
        sa.Column('pending_claim_expiry', sa.String(length=20), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("partial_return_mode='accumulate_original_unit' AND expiry_mode='original_expiry' AND pending_claim_expiry='none'", name='ck_retail_group_modes'),
        sa.UniqueConstraint('rule_id'),
        sa.UniqueConstraint('case_id'),
    )
    op.create_table('retail_group_plans',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('retail_orders.id'), nullable=False),
        sa.Column('member_id', sa.Integer(), sa.ForeignKey('group_members.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('case_id'),
    )
    op.create_index('ix_retail_group_plans_store_id', 'retail_group_plans', ['store_id'], unique=False)
    op.create_table('observation_corrections',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False, primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('care_customer_vehicles.id'), nullable=False),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('care_vehicle_observations.id'), nullable=False),
        sa.Column('base_digest', sa.String(length=64), nullable=False),
        sa.Column('original_snapshot', sa.JSON(), nullable=False),
        sa.Column('operation', sa.String(length=12), nullable=False),
        sa.Column('proposed', sa.JSON(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("operation IN ('replace','retract')", name='ck_observation_correction_operation'),
    )
    op.create_index('ix_observation_corrections_observation_id', 'observation_corrections', ['observation_id'], unique=False)
    op.create_index('ix_observation_corrections_store_id', 'observation_corrections', ['store_id'], unique=False)
    op.create_index('ix_observation_corrections_vehicle_id', 'observation_corrections', ['vehicle_id'], unique=False)
    op.create_table('retail_group_decisions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('eligibility_id', sa.Integer(), sa.ForeignKey('retail_group_eligibility.id'), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('eligibility_id'),
    )
    op.create_table('retail_group_scopes',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('eligibility_id', sa.Integer(), sa.ForeignKey('retail_group_eligibility.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('flow_items.id'), nullable=False),
        sa.Column('component', sa.String(length=20), nullable=False),
        sa.Column('work_item_id', sa.Integer(), sa.ForeignKey('master_work_items.id'), nullable=True),
        sa.Column('sku', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('work_code', sa.String(length=60), nullable=False),
        sa.CheckConstraint("(component='goods' AND work_item_id IS NULL) OR (component='installation' AND work_item_id IS NOT NULL)", name='ck_retail_group_scope'),
        sa.UniqueConstraint('eligibility_id', 'store_id', 'item_id', 'component', name='uq_retail_group_scope'),
    )
    op.create_index('ix_retail_group_scopes_eligibility_id', 'retail_group_scopes', ['eligibility_id'], unique=False)
    op.create_table('retail_group_tenders',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('retail_group_plans.id'), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('benefit_wallets.id'), nullable=True),
        sa.Column('eligibility_id', sa.Integer(), sa.ForeignKey('retail_group_eligibility.id'), nullable=True),
        sa.Column('units', sa.BigInteger(), nullable=False),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('consideration_cents', sa.BigInteger(), nullable=False),
        sa.Column('settlement_cents', sa.BigInteger(), nullable=False),
        sa.Column('expires_on', sa.Date(), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("(kind IN ('cash','principal') AND wallet_id IS NULL AND eligibility_id IS NULL AND expires_on IS NULL) OR (kind IN ('bonus','coupon','package') AND wallet_id IS NOT NULL AND eligibility_id IS NOT NULL AND expires_on IS NOT NULL)", name='ck_retail_group_tender_source'),
        sa.CheckConstraint("kind IN ('cash','principal','bonus','coupon','package') AND sequence>0 AND units>0 AND credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents", name='ck_retail_group_tender_value'),
        sa.UniqueConstraint('plan_id', 'sequence', name='uq_retail_group_tender'),
    )
    op.create_index('ix_retail_group_tenders_plan_id', 'retail_group_tenders', ['plan_id'], unique=False)
    op.create_index('ix_retail_group_tenders_store_id', 'retail_group_tenders', ['store_id'], unique=False)
    op.create_table('observation_correction_events',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('observation_corrections.case_id'), nullable=False),
        sa.Column('action', sa.String(length=15), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("action IN ('create','submit','approve','reject','cancel')", name='ck_observation_correction_event'),
        sa.UniqueConstraint('case_id', 'action', name='uq_observation_correction_event'),
    )
    op.create_index('ix_observation_correction_events_case_id', 'observation_correction_events', ['case_id'], unique=False)
    op.create_index('ix_observation_correction_events_store_id', 'observation_correction_events', ['store_id'], unique=False)
    op.create_table('observation_reminder_replacements',
        sa.Column('previous_case_id', sa.Integer(), sa.ForeignKey('care_cases.case_id'), nullable=False),
        sa.Column('replacement_case_id', sa.Integer(), sa.ForeignKey('care_cases.case_id'), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('previous_case_id!=replacement_case_id', name='ck_observation_reminder_replacement'),
        sa.UniqueConstraint('previous_case_id', 'replacement_case_id', name='uq_observation_reminder_replacement'),
    )
    op.create_index('ix_observation_reminder_replacements_store_id', 'observation_reminder_replacements', ['store_id'], unique=False)
    op.create_table('retail_group_closures',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tender_id', sa.Integer(), sa.ForeignKey('retail_group_tenders.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('tender_id'),
    )
    op.create_index('ix_retail_group_closures_store_id', 'retail_group_closures', ['store_id'], unique=False)
    op.create_table('retail_group_reservations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tender_id', sa.Integer(), sa.ForeignKey('retail_group_tenders.id'), nullable=False),
        sa.Column('principal_id', sa.Integer(), sa.ForeignKey('group_reservations.id'), nullable=True),
        sa.Column('benefit_id', sa.Integer(), sa.ForeignKey('benefit_reservations.id'), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(principal_id IS NOT NULL AND benefit_id IS NULL) OR (principal_id IS NULL AND benefit_id IS NOT NULL)', name='ck_retail_group_reservation_source'),
        sa.UniqueConstraint('principal_id'),
        sa.UniqueConstraint('benefit_id'),
    )
    op.create_index('ix_retail_group_reservations_store_id', 'retail_group_reservations', ['store_id'], unique=False)
    op.create_index('ix_retail_group_reservations_tender_id', 'retail_group_reservations', ['tender_id'], unique=False)
    op.create_table('retail_group_units',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tender_id', sa.Integer(), sa.ForeignKey('retail_group_tenders.id'), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('consideration_cents', sa.BigInteger(), nullable=False),
        sa.Column('settlement_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('sequence>0 AND credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents', name='ck_retail_group_unit'),
        sa.UniqueConstraint('tender_id', 'sequence', name='uq_retail_group_unit'),
    )
    op.create_index('ix_retail_group_units_store_id', 'retail_group_units', ['store_id'], unique=False)
    op.create_index('ix_retail_group_units_tender_id', 'retail_group_units', ['tender_id'], unique=False)
    op.create_table('retail_group_wallets',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('benefit_wallets.id'), nullable=False),
        sa.Column('eligibility_id', sa.Integer(), sa.ForeignKey('retail_group_eligibility.id'), nullable=False),
        sa.Column('decision_id', sa.Integer(), sa.ForeignKey('retail_group_decisions.id'), nullable=False),
        sa.Column('origin_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('origin_id'),
        sa.UniqueConstraint('wallet_id'),
    )
    op.create_table('observation_correction_effects',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('observation_corrections.case_id'), nullable=False),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('care_vehicle_observations.id'), nullable=False),
        sa.Column('parent_effect_id', sa.Integer(), sa.ForeignKey('observation_correction_effects.id'), nullable=True),
        sa.Column('parent_token', sa.String(length=40), nullable=False),
        sa.Column('review_event_id', sa.Integer(), sa.ForeignKey('observation_correction_events.id'), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('case_id'),
        sa.UniqueConstraint('review_event_id'),
        sa.UniqueConstraint('observation_id', 'parent_token', name='uq_observation_correction_head'),
    )
    op.create_index('ix_observation_correction_effects_observation_id', 'observation_correction_effects', ['observation_id'], unique=False)
    op.create_index('ix_observation_correction_effects_store_id', 'observation_correction_effects', ['store_id'], unique=False)
    op.create_table('retail_group_allocations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('retail_group_units.id'), nullable=False),
        sa.Column('line_id', sa.Integer(), sa.ForeignKey('retail_lines.id'), nullable=False),
        sa.Column('component', sa.String(length=20), nullable=False),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('consideration_cents', sa.BigInteger(), nullable=False),
        sa.Column('settlement_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("component IN ('goods','installation') AND credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents", name='ck_retail_group_allocation'),
        sa.UniqueConstraint('unit_id', 'line_id', 'component', name='uq_retail_group_allocation'),
    )
    op.create_index('ix_retail_group_allocations_line_id', 'retail_group_allocations', ['line_id'], unique=False)
    op.create_index('ix_retail_group_allocations_store_id', 'retail_group_allocations', ['store_id'], unique=False)
    op.create_index('ix_retail_group_allocations_unit_id', 'retail_group_allocations', ['unit_id'], unique=False)
    op.create_table('retail_group_captures',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tender_id', sa.Integer(), sa.ForeignKey('retail_group_tenders.id'), nullable=False),
        sa.Column('reservation_id', sa.Integer(), sa.ForeignKey('retail_group_reservations.id'), nullable=False),
        sa.Column('principal_id', sa.Integer(), sa.ForeignKey('group_entries.id'), nullable=True),
        sa.Column('benefit_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(principal_id IS NOT NULL AND benefit_id IS NULL) OR (principal_id IS NULL AND benefit_id IS NOT NULL)', name='ck_retail_group_capture_source'),
        sa.UniqueConstraint('principal_id'),
        sa.UniqueConstraint('tender_id'),
        sa.UniqueConstraint('benefit_id'),
        sa.UniqueConstraint('reservation_id'),
    )
    op.create_index('ix_retail_group_captures_store_id', 'retail_group_captures', ['store_id'], unique=False)
    op.create_table('retail_group_returns',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('retail_group_plans.id'), nullable=False),
        sa.Column('posting_id', sa.Integer(), sa.ForeignKey('retail_return_postings.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('posting_id'),
    )
    op.create_index('ix_retail_group_returns_plan_id', 'retail_group_returns', ['plan_id'], unique=False)
    op.create_index('ix_retail_group_returns_store_id', 'retail_group_returns', ['store_id'], unique=False)
    op.create_table('observation_reminder_bases',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('care_cases.case_id'), nullable=False, primary_key=True),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('care_customer_vehicles.id'), nullable=False),
        sa.Column('baseline_id', sa.Integer(), sa.ForeignKey('care_vehicle_observations.id'), nullable=False),
        sa.Column('current_id', sa.Integer(), sa.ForeignKey('care_vehicle_observations.id'), nullable=True),
        sa.Column('baseline_effect_id', sa.Integer(), sa.ForeignKey('observation_correction_effects.id'), nullable=True),
        sa.Column('current_effect_id', sa.Integer(), sa.ForeignKey('observation_correction_effects.id'), nullable=True),
        sa.Column('cycle_key', sa.String(length=120), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
    )
    op.create_index('ix_observation_reminder_bases_cycle_key', 'observation_reminder_bases', ['cycle_key'], unique=False)
    op.create_index('ix_observation_reminder_bases_store_id', 'observation_reminder_bases', ['store_id'], unique=False)
    op.create_index('ix_observation_reminder_bases_vehicle_id', 'observation_reminder_bases', ['vehicle_id'], unique=False)
    op.create_table('retail_group_cash_allocations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('allocation_id', sa.Integer(), sa.ForeignKey('retail_group_allocations.id'), nullable=False),
        sa.Column('payment_link_id', sa.Integer(), sa.ForeignKey('flow_payment_links.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('retail_group_cash_allocations.id'), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(amount_cents>0 AND original_id IS NULL) OR (amount_cents<0 AND original_id IS NOT NULL)', name='ck_retail_group_cash_allocation'),
        sa.UniqueConstraint('allocation_id', 'payment_link_id', 'original_id', name='uq_retail_group_cash_allocation'),
    )
    op.create_index('ix_retail_group_cash_allocations_allocation_id', 'retail_group_cash_allocations', ['allocation_id'], unique=False)
    op.create_index('ix_retail_group_cash_allocations_payment_link_id', 'retail_group_cash_allocations', ['payment_link_id'], unique=False)
    op.create_index('ix_retail_group_cash_allocations_store_id', 'retail_group_cash_allocations', ['store_id'], unique=False)
    op.create_table('retail_group_restores',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('unit_id', sa.Integer(), sa.ForeignKey('retail_group_units.id'), nullable=False),
        sa.Column('capture_id', sa.Integer(), sa.ForeignKey('retail_group_captures.id'), nullable=False),
        sa.Column('principal_id', sa.Integer(), sa.ForeignKey('group_entries.id'), nullable=True),
        sa.Column('benefit_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=True),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('consideration_cents', sa.BigInteger(), nullable=False),
        sa.Column('settlement_cents', sa.BigInteger(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(principal_id IS NOT NULL AND benefit_id IS NULL) OR (principal_id IS NULL AND benefit_id IS NOT NULL)', name='ck_retail_group_restore_source'),
        sa.CheckConstraint('credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents', name='ck_retail_group_restore_value'),
        sa.UniqueConstraint('principal_id'),
        sa.UniqueConstraint('benefit_id'),
    )
    op.create_index('ix_retail_group_restores_store_id', 'retail_group_restores', ['store_id'], unique=False)
    op.create_index('ix_retail_group_restores_unit_id', 'retail_group_restores', ['unit_id'], unique=False)
    op.create_table('retail_group_return_parts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('return_id', sa.Integer(), sa.ForeignKey('retail_group_returns.id'), nullable=False),
        sa.Column('allocation_id', sa.Integer(), sa.ForeignKey('retail_group_allocations.id'), nullable=False),
        sa.Column('capture_id', sa.Integer(), sa.ForeignKey('retail_group_captures.id'), nullable=True),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('consideration_cents', sa.BigInteger(), nullable=False),
        sa.Column('settlement_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents', name='ck_retail_group_return_part'),
        sa.UniqueConstraint('return_id', 'allocation_id', name='uq_retail_group_return_part'),
    )
    op.create_index('ix_retail_group_return_parts_allocation_id', 'retail_group_return_parts', ['allocation_id'], unique=False)
    op.create_index('ix_retail_group_return_parts_return_id', 'retail_group_return_parts', ['return_id'], unique=False)
    op.create_index('ix_retail_group_return_parts_store_id', 'retail_group_return_parts', ['store_id'], unique=False)
    op.create_table('retail_group_settlements',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('return_part_id', sa.Integer(), sa.ForeignKey('retail_group_return_parts.id'), nullable=True),
        sa.Column('restore_id', sa.Integer(), sa.ForeignKey('retail_group_restores.id'), nullable=True),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("side IN ('center','store') AND amount_cents!=0 AND ((return_part_id IS NOT NULL AND restore_id IS NULL) OR (return_part_id IS NULL AND restore_id IS NOT NULL))", name='ck_retail_group_settlement'),
        sa.UniqueConstraint('restore_id', 'side', name='uq_retail_group_restore_settlement'),
        sa.UniqueConstraint('return_part_id', 'side', name='uq_retail_group_return_settlement'),
    )
    op.create_index('ix_retail_group_settlements_store_id', 'retail_group_settlements', ['store_id'], unique=False)
    op.create_table('observation_insurance_invalidations',
        sa.Column('source_case_id', sa.Integer(), sa.ForeignKey('insurance_orders.id'), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('care_customer_vehicles.id'), nullable=False),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('care_vehicle_observations.id'), nullable=False),
        sa.Column('result_id', sa.Integer(), sa.ForeignKey('insurance_results.id'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('insurance_terminations.id'), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('insurance_termination_applications.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('observation_id'),
        sa.UniqueConstraint('result_id'),
        sa.UniqueConstraint('application_id'),
    )
    op.create_index('ix_observation_insurance_invalidations_store_id', 'observation_insurance_invalidations', ['store_id'], unique=False)
    op.create_index('ix_observation_insurance_invalidations_vehicle_id', 'observation_insurance_invalidations', ['vehicle_id'], unique=False)
    op.create_table('transfer_goods_recoveries',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('active_transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=True),
        sa.Column('loss_id', sa.Integer(), sa.ForeignKey('transfer_loss_postings.id'), nullable=False),
        sa.Column('exception_id', sa.Integer(), sa.ForeignKey('transfer_exceptions.id'), nullable=False),
        sa.Column('found_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("(status IN ('closed','cancelled') AND active_transfer_id IS NULL) OR (status NOT IN ('closed','cancelled') AND active_transfer_id=transfer_id AND active_transfer_id IS NOT NULL)", name='ck_found_active'),
        sa.CheckConstraint('quantity_milli>0', name='ck_found_quantity'),
        sa.CheckConstraint("status IN ('preparing','transit','review','approved','financial','closed','cancelled')", name='ck_found_state'),
        sa.UniqueConstraint('active_transfer_id'),
    )
    op.create_index('ix_transfer_goods_recoveries_exception_id', 'transfer_goods_recoveries', ['exception_id'], unique=False)
    op.create_index('ix_transfer_goods_recoveries_loss_id', 'transfer_goods_recoveries', ['loss_id'], unique=False)
    op.create_index('ix_transfer_goods_recoveries_transfer_id', 'transfer_goods_recoveries', ['transfer_id'], unique=False)
    op.create_table('observation_reminder_invalidations',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('care_cases.case_id'), nullable=False),
        sa.Column('correction_case_id', sa.Integer(), sa.ForeignKey('observation_corrections.case_id'), nullable=True),
        sa.Column('insurance_invalidation_id', sa.Integer(), sa.ForeignKey('observation_insurance_invalidations.id'), nullable=True),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('care_vehicle_observations.id'), nullable=False),
        sa.Column('previous_state', sa.String(length=30), nullable=False),
        sa.Column('closed_open_task', sa.Boolean(), nullable=False),
        sa.Column('source_key', sa.String(length=80), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(correction_case_id IS NULL) != (insurance_invalidation_id IS NULL)', name='ck_observation_reminder_source'),
        sa.UniqueConstraint('case_id', 'source_key', name='uq_observation_reminder_invalidation'),
    )
    op.create_index('ix_observation_reminder_invalidations_case_id', 'observation_reminder_invalidations', ['case_id'], unique=False)
    op.create_index('ix_observation_reminder_invalidations_store_id', 'observation_reminder_invalidations', ['store_id'], unique=False)
    op.create_table('transfer_goods_facts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('kind', sa.String(length=15), nullable=False),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('result', sa.String(length=1000), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("quantity_milli>0 AND kind IN ('found','match','inspect','ship','receive','dispose','cancel')", name='ck_found_fact'),
        sa.CheckConstraint("(kind IN ('inspect','receive') AND passed IS NOT NULL) OR (kind NOT IN ('inspect','receive') AND passed IS NULL)", name='ck_found_quality'),
    )
    op.create_index('ix_transfer_goods_facts_recovery_id', 'transfer_goods_facts', ['recovery_id'], unique=False)
    op.create_table('transfer_goods_receipts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('store_id', 'request_key', name='uq_found_request'),
    )
    op.create_index('ix_transfer_goods_receipts_store_id', 'transfer_goods_receipts', ['store_id'], unique=False)
    op.create_table('transfer_goods_terms',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('claim_id', sa.Integer(), sa.ForeignKey('transfer_recovery_claims.id'), nullable=False),
        sa.Column('previous_plan_id', sa.Integer(), sa.ForeignKey('transfer_recovery_plans.id'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_recovery_plans.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('plan_id'),
    )
    op.create_index('ix_transfer_goods_terms_claim_id', 'transfer_goods_terms', ['claim_id'], unique=False)
    op.create_index('ix_transfer_goods_terms_recovery_id', 'transfer_goods_terms', ['recovery_id'], unique=False)
    op.create_index('ix_transfer_goods_terms_store_id', 'transfer_goods_terms', ['store_id'], unique=False)
    op.create_table('transfer_goods_plans',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), sa.ForeignKey('transfer_goods_facts.id'), nullable=False),
        sa.Column('inspection_id', sa.Integer(), sa.ForeignKey('transfer_goods_facts.id'), nullable=False),
        sa.Column('restored_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('source_reverse_cents', sa.BigInteger(), nullable=False),
        sa.Column('destination_reverse_cents', sa.BigInteger(), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('revision>0 AND restored_quantity_milli>=0 AND value_cents>=0 AND source_reverse_cents>=0 AND destination_reverse_cents>=0 AND source_reverse_cents+destination_reverse_cents=value_cents', name='ck_found_plan_amount'),
        sa.UniqueConstraint('recovery_id', 'revision', name='uq_found_plan'),
    )
    op.create_index('ix_transfer_goods_plans_recovery_id', 'transfer_goods_plans', ['recovery_id'], unique=False)
    op.create_table('transfer_goods_refunds',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('terms_id', sa.Integer(), sa.ForeignKey('transfer_goods_terms.id'), nullable=False),
        sa.Column('payment_id', sa.Integer(), sa.ForeignKey('transfer_recovery_payments.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('payment_id'),
    )
    op.create_index('ix_transfer_goods_refunds_recovery_id', 'transfer_goods_refunds', ['recovery_id'], unique=False)
    op.create_index('ix_transfer_goods_refunds_store_id', 'transfer_goods_refunds', ['store_id'], unique=False)
    op.create_table('transfer_goods_postings',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('loss_id', sa.Integer(), sa.ForeignKey('transfer_loss_postings.id'), nullable=False),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_goods_plans.id'), nullable=False),
        sa.Column('found_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('restored_quantity_milli', sa.BigInteger(), nullable=False),
        sa.Column('value_cents', sa.BigInteger(), nullable=False),
        sa.Column('source_reverse_cents', sa.BigInteger(), nullable=False),
        sa.Column('destination_reverse_cents', sa.BigInteger(), nullable=False),
        sa.Column('stock_move_id', sa.Integer(), sa.ForeignKey('flow_stock_moves.id'), nullable=True),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('found_quantity_milli>0 AND restored_quantity_milli>=0 AND restored_quantity_milli<=found_quantity_milli AND value_cents>=0 AND source_reverse_cents>=0 AND destination_reverse_cents>=0 AND source_reverse_cents+destination_reverse_cents=value_cents', name='ck_found_posting_amount'),
        sa.CheckConstraint('(restored_quantity_milli>0 AND stock_move_id IS NOT NULL) OR (restored_quantity_milli=0 AND stock_move_id IS NULL AND value_cents=0)', name='ck_found_stock'),
        sa.UniqueConstraint('plan_id'),
        sa.UniqueConstraint('stock_move_id'),
        sa.UniqueConstraint('recovery_id'),
    )
    op.create_index('ix_transfer_goods_postings_loss_id', 'transfer_goods_postings', ['loss_id'], unique=False)
    op.create_index('ix_transfer_goods_postings_store_id', 'transfer_goods_postings', ['store_id'], unique=False)
    op.create_table('transfer_goods_reviews',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), sa.ForeignKey('transfer_goods_plans.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('decision', sa.String(length=10), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('approve','reject')", name='ck_found_review'),
        sa.UniqueConstraint('plan_id', 'store_id', name='uq_found_review'),
    )
    op.create_index('ix_transfer_goods_reviews_plan_id', 'transfer_goods_reviews', ['plan_id'], unique=False)
    op.create_table('transfer_goods_settlements',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('material_transfers.id'), nullable=False),
        sa.Column('recovery_id', sa.Integer(), sa.ForeignKey('transfer_goods_recoveries.id'), nullable=False),
        sa.Column('posting_id', sa.Integer(), sa.ForeignKey('transfer_goods_postings.id'), nullable=False),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('transfer_loss_settlements.id'), nullable=False),
        sa.Column('counterparty_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('amount_cents!=0', name='ck_found_settlement'),
        sa.UniqueConstraint('posting_id', 'store_id', name='uq_found_settlement'),
    )
    op.create_index('ix_transfer_goods_settlements_posting_id', 'transfer_goods_settlements', ['posting_id'], unique=False)
    op.create_index('ix_transfer_goods_settlements_recovery_id', 'transfer_goods_settlements', ['recovery_id'], unique=False)
    op.create_index('ix_transfer_goods_settlements_store_id', 'transfer_goods_settlements', ['store_id'], unique=False)
    op.create_index('ix_transfer_goods_settlements_transfer_id', 'transfer_goods_settlements', ['transfer_id'], unique=False)

def downgrade():
    raise RuntimeError('Immutable business facts require a reviewed consistent backup restore; no destructive downgrade')
