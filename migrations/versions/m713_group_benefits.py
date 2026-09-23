"""Frozen group benefit rules, unit ledgers, reservations and approved refunds."""
from alembic import op
import sqlalchemy as sa

revision = 'm713_group_benefits'
down_revision = 'l612_customer_service'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('benefit_rules',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('issuer_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('rule_version', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('allowed_store_ids', sa.JSON(), nullable=False),
        sa.Column('credit_cents_per_unit', sa.BigInteger(), nullable=False),
        sa.Column('settlement_cents_per_unit', sa.BigInteger(), nullable=False),
        sa.Column('sale_cents_per_unit', sa.BigInteger(), nullable=False),
        sa.Column('exchange_points_per_unit', sa.BigInteger(), nullable=False),
        sa.Column('refund_policy', sa.String(length=30), nullable=False),
        sa.Column('discount_bearer', sa.String(length=20), nullable=False),
        sa.Column('validity_days', sa.Integer(), nullable=False),
        sa.Column('service_code', sa.String(length=40), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("refund_policy IN ('none','unused_before_expiry','unused_anytime') AND discount_bearer IN ('group','service_store')", name='ck_benefit_rule_policy'),
        sa.UniqueConstraint('issuer_store_id','code','rule_version', name='uq_benefit_rule_version'),
        sa.CheckConstraint("kind NOT IN ('bonus','points') OR (sale_cents_per_unit=0 AND exchange_points_per_unit=0 AND refund_policy='none')", name='ck_benefit_non_cash'),
        sa.CheckConstraint("kind IN ('bonus','points','coupon','package')", name='ck_benefit_kind'),
        sa.CheckConstraint('rule_version>0 AND credit_cents_per_unit>0 AND settlement_cents_per_unit>=0 AND settlement_cents_per_unit<=credit_cents_per_unit AND sale_cents_per_unit>=0 AND exchange_points_per_unit>=0 AND validity_days>0', name='ck_benefit_rule_values'),
        sa.CheckConstraint("sale_cents_per_unit<=credit_cents_per_unit AND ((discount_bearer='group' AND settlement_cents_per_unit=credit_cents_per_unit) OR (discount_bearer='service_store' AND settlement_cents_per_unit=sale_cents_per_unit))", name='ck_benefit_discount_bearer'),
        sa.CheckConstraint("kind!='bonus' OR credit_cents_per_unit=1", name='ck_benefit_bonus_fen'))
    op.create_table('benefit_wallets',
        sa.Column('member_id', sa.Integer(), sa.ForeignKey('group_members.id'), nullable=False),
        sa.Column('rule_id', sa.Integer(), sa.ForeignKey('benefit_rules.id'), nullable=False),
        sa.Column('issuer_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('source_case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('source_kind', sa.String(length=20), nullable=False),
        sa.Column('initial_units', sa.BigInteger(), nullable=False),
        sa.Column('balance_units', sa.BigInteger(), nullable=False),
        sa.Column('reserved_units', sa.BigInteger(), nullable=False),
        sa.Column('expires_on', sa.Date(), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=True),
        sa.Column('cash_id', sa.Integer(), sa.ForeignKey('cash_entries.id'), nullable=True),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('cash_id', name=None),
        sa.CheckConstraint("(source_kind='purchase' AND cash_id IS NOT NULL AND account_id IS NOT NULL) OR (source_kind!='purchase' AND cash_id IS NULL AND account_id IS NULL)", name='ck_benefit_wallet_cash'),
        sa.CheckConstraint('initial_units>0 AND balance_units>=0 AND reserved_units>=0 AND reserved_units<=balance_units AND balance_units<=initial_units', name='ck_benefit_wallet_units'),
        sa.CheckConstraint("source_kind IN ('purchase','grant','exchange')", name='ck_benefit_wallet_source'))
    op.create_index('ix_benefit_wallets_member_id','benefit_wallets',['member_id'])
    op.create_table('benefit_entries',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('benefit_wallets.id'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('units', sa.BigInteger(), nullable=False),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('original_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=True),
        sa.Column('cash_id', sa.Integer(), sa.ForeignKey('cash_entries.id'), nullable=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('store_id','account_id','reference', name='uq_benefit_cash_reference'),
        sa.CheckConstraint("(purpose IN ('purchase','grant','exchange_in','reverse') AND units>0) OR (purpose IN ('capture','refund','adjust','exchange_out') AND units<0)", name='ck_benefit_entry_sign'),
        sa.UniqueConstraint('cash_id', name=None),
        sa.CheckConstraint("(purpose IN ('purchase','refund') AND cash_id IS NOT NULL AND account_id IS NOT NULL AND reference IS NOT NULL) OR (purpose NOT IN ('purchase','refund') AND cash_id IS NULL AND account_id IS NULL AND reference IS NULL)", name='ck_benefit_entry_cash'),
        sa.CheckConstraint("(purpose='capture' AND credit_cents>0) OR (purpose='reverse' AND credit_cents<0) OR (purpose NOT IN ('capture','reverse') AND credit_cents=0)", name='ck_benefit_credit_sign'))
    op.create_index('ix_benefit_entries_store_id','benefit_entries',['store_id'])
    op.create_index('ix_benefit_entries_wallet_id','benefit_entries',['wallet_id'])
    op.create_table('benefit_reservations',
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('benefit_wallets.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('units', sa.BigInteger(), nullable=False),
        sa.Column('credit_cents', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("units>0 AND credit_cents>0 AND status IN ('reserved','captured','released')", name='ck_benefit_reservation'))
    op.create_index('ix_benefit_reservations_case_id','benefit_reservations',['case_id'])
    op.create_index('ix_benefit_reservations_store_id','benefit_reservations',['store_id'])
    op.create_index('ix_benefit_reservations_wallet_id','benefit_reservations',['wallet_id'])
    op.create_table('benefit_payment_links',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=False),
        sa.Column('reservation_id', sa.Integer(), sa.ForeignKey('benefit_reservations.id'), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('entry_id', name=None),
        sa.CheckConstraint('amount_cents!=0', name='ck_benefit_payment'))
    op.create_index('ix_benefit_payment_links_case_id','benefit_payment_links',['case_id'])
    op.create_index('ix_benefit_payment_links_store_id','benefit_payment_links',['store_id'])
    op.create_table('benefit_refunds',
        sa.Column('wallet_id', sa.Integer(), sa.ForeignKey('benefit_wallets.id'), nullable=False),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('units', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('executed_entry_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=True),
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('executed_entry_id', name=None),
        sa.CheckConstraint("status NOT IN ('approved','executed') OR approved_by IS NOT NULL", name='ck_benefit_refund_approval'),
        sa.CheckConstraint("(status='executed' AND executed_entry_id IS NOT NULL) OR (status!='executed' AND executed_entry_id IS NULL)", name='ck_benefit_refund_execution'),
        sa.CheckConstraint("units>0 AND status IN ('requested','approved','rejected','cancelled','executed')", name='ck_benefit_refund_status'))
    op.create_index('ix_benefit_refunds_store_id','benefit_refunds',['store_id'])
    op.create_index('ix_benefit_refunds_wallet_id','benefit_refunds',['wallet_id'])
    op.create_table('benefit_settlements',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('benefit_entries.id'), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('entry_id','side', name='uq_benefit_settlement'),
        sa.CheckConstraint("side IN ('center','store') AND amount_cents!=0", name='ck_benefit_settlement'))
    op.create_index('ix_benefit_settlements_entry_id','benefit_settlements',['entry_id'])
    op.create_index('ix_benefit_settlements_store_id','benefit_settlements',['store_id'])


def downgrade():
    raise RuntimeError('Group benefit ledgers cannot be dropped; restore a verified consistent backup instead')
