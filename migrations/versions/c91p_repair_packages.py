"""Mixed repair component contracts; legacy scalar benefits stay frozen."""
from alembic import op
import sqlalchemy as sa
revision='c91p_repair_packages'
down_revision='b80o_member_pricing'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('repair_package_quote_snapshots',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('store_id',sa.Integer(),nullable=False),sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('occurred_at',sa.DateTime(),nullable=False),sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),sa.Column('quote_id',sa.Integer(),sa.ForeignKey('repair_quotes.id'),nullable=False),sa.Column('contract',sa.JSON(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),sa.UniqueConstraint('quote_id'))
    op.create_index('ix_repair_package_quote_snapshots_case_id','repair_package_quote_snapshots',['case_id'])
    op.create_table('repair_package_rules',
        sa.Column('issuer_store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('definition_version',sa.Integer(),nullable=False),
        sa.Column('code',sa.String(length=40),nullable=False),
        sa.Column('rule_version',sa.Integer(),nullable=False),
        sa.Column('name',sa.String(length=120),nullable=False),
        sa.Column('contract',sa.JSON(),nullable=False),
        sa.Column('digest',sa.String(length=64),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('issuer_store_id','code','rule_version',name='uq_repair_package_rule'),
        sa.CheckConstraint('definition_version=1 AND rule_version>0',name='ck_repair_package_rule'))
    op.create_index('ix_repair_package_rules_issuer_store_id','repair_package_rules',['issuer_store_id'],unique=False)
    op.create_table('repair_package_mappings',
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('repair_package_rules.id'),nullable=False),
        sa.Column('component_key',sa.String(length=40),nullable=False),
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('kind',sa.String(length=10),nullable=False),
        sa.Column('source_id',sa.Integer(),nullable=False),
        sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("kind IN ('work','part') AND source_id>0",name='ck_repair_package_mapping'),
        sa.UniqueConstraint('rule_id','component_key','store_id',name='uq_repair_package_mapping'))
    op.create_index('ix_repair_package_mappings_rule_id','repair_package_mappings',['rule_id'],unique=False)
    op.create_index('ix_repair_package_mappings_store_id','repair_package_mappings',['store_id'],unique=False)
    op.create_table('repair_package_rule_decisions',
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('repair_package_rules.id'),nullable=False),
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('action',sa.String(length=12),nullable=False),
        sa.Column('reason',sa.String(length=1000),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('rule_id','action',name='uq_repair_package_decision'),
        sa.CheckConstraint("action IN ('approve','reject','cancel','revoke')",name='ck_repair_package_decision'))
    op.create_index('ix_repair_package_rule_decisions_rule_id','repair_package_rule_decisions',['rule_id'],unique=False)
    op.create_table('repair_package_purchases',
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('repair_package_rules.id'),nullable=False),
        sa.Column('member_id',sa.Integer(),sa.ForeignKey('group_members.id'),nullable=False),
        sa.Column('issuer_store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('sets',sa.Integer(),nullable=False),
        sa.Column('contract',sa.JSON(),nullable=False),
        sa.Column('digest',sa.String(length=64),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('expires_on',sa.Date(),nullable=False),
        sa.Column('valid_until',sa.Date(),nullable=False),
        sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=True),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('flow_accounts.id'),nullable=True),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("sets>0 AND amount_cents>0 AND status IN ('proposed','authorized','issued','cancelled')",name='ck_repair_package_purchase'),
        sa.UniqueConstraint('cash_id',name=None),
        sa.CheckConstraint("(status='issued' AND cash_id IS NOT NULL AND account_id IS NOT NULL) OR (status!='issued' AND cash_id IS NULL AND account_id IS NULL)",name='ck_repair_package_purchase_cash'))
    op.create_index('ix_repair_package_purchases_issuer_store_id','repair_package_purchases',['issuer_store_id'],unique=False)
    op.create_index('ix_repair_package_purchases_member_id','repair_package_purchases',['member_id'],unique=False)
    op.create_table('repair_package_lots',
        sa.Column('purchase_id',sa.Integer(),sa.ForeignKey('repair_package_purchases.id'),nullable=False),
        sa.Column('component_key',sa.String(length=40),nullable=False),
        sa.Column('quantity_milli',sa.BigInteger(),nullable=False),
        sa.Column('credit_cents',sa.BigInteger(),nullable=False),
        sa.Column('paid_cents',sa.BigInteger(),nullable=False),
        sa.Column('settlement_cents',sa.BigInteger(),nullable=False),
        sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('purchase_id','component_key',name='uq_repair_package_lot'),
        sa.CheckConstraint('quantity_milli>0 AND credit_cents>0 AND paid_cents>=0 AND settlement_cents>=paid_cents AND credit_cents>=settlement_cents',name='ck_repair_package_lot'))
    op.create_index('ix_repair_package_lots_purchase_id','repair_package_lots',['purchase_id'],unique=False)
    op.create_table('repair_package_purchase_events',
        sa.Column('purchase_id',sa.Integer(),sa.ForeignKey('repair_package_purchases.id'),nullable=False),
        sa.Column('action',sa.String(length=12),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=True),
        sa.Column('digest',sa.String(length=64),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('purchase_id','action',name='uq_repair_package_purchase_event'),
        sa.CheckConstraint("action IN ('propose','authorize','issue','cancel')",name='ck_repair_package_purchase_event'))
    op.create_index('ix_repair_package_purchase_events_purchase_id','repair_package_purchase_events',['purchase_id'],unique=False)
    op.create_index('ix_repair_package_purchase_events_store_id','repair_package_purchase_events',['store_id'],unique=False)
    op.create_table('repair_package_refunds',
        sa.Column('purchase_id',sa.Integer(),sa.ForeignKey('repair_package_purchases.id'),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('selections',sa.JSON(),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('requested_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('reason',sa.String(length=1000),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('approved_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=True),
        sa.Column('cash_id',sa.Integer(),sa.ForeignKey('cash_entries.id'),nullable=True),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("(status='executed' AND ((amount_cents>0 AND cash_id IS NOT NULL) OR (amount_cents=0 AND cash_id IS NULL))) OR (status!='executed' AND cash_id IS NULL)",name='ck_repair_package_refund_cash'),
        sa.UniqueConstraint('cash_id',name=None),
        sa.CheckConstraint("amount_cents>=0 AND status IN ('requested','approved','rejected','cancelled','executed')",name='ck_repair_package_refund'),
        sa.CheckConstraint("status NOT IN ('approved','executed') OR approved_by IS NOT NULL",name='ck_repair_package_refund_approval'))
    op.create_index('ix_repair_package_refunds_purchase_id','repair_package_refunds',['purchase_id'],unique=False)
    op.create_index('ix_repair_package_refunds_store_id','repair_package_refunds',['store_id'],unique=False)
    op.create_table('repair_package_holds',
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('lot_id',sa.Integer(),sa.ForeignKey('repair_package_lots.id'),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('quote_id',sa.Integer(),sa.ForeignKey('repair_quotes.id'),nullable=False),
        sa.Column('line_id',sa.Integer(),sa.ForeignKey('repair_lines.id'),nullable=False),
        sa.Column('line_key',sa.String(length=40),nullable=False),
        sa.Column('spans',sa.JSON(),nullable=False),
        sa.Column('quantity_milli',sa.BigInteger(),nullable=False),
        sa.Column('credit_cents',sa.BigInteger(),nullable=False),
        sa.Column('paid_cents',sa.BigInteger(),nullable=False),
        sa.Column('settlement_cents',sa.BigInteger(),nullable=False),
        sa.Column('digest',sa.String(length=64),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('line_id',name=None),
        sa.CheckConstraint("quantity_milli>0 AND credit_cents>=0 AND paid_cents>=0 AND settlement_cents>=0 AND status IN ('reserved','released','captured')",name='ck_repair_package_hold'))
    op.create_index('ix_repair_package_holds_case_id','repair_package_holds',['case_id'],unique=False)
    op.create_index('ix_repair_package_holds_lot_id','repair_package_holds',['lot_id'],unique=False)
    op.create_index('ix_repair_package_holds_quote_id','repair_package_holds',['quote_id'],unique=False)
    op.create_index('ix_repair_package_holds_store_id','repair_package_holds',['store_id'],unique=False)
    op.create_table('repair_package_refund_claims',
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('refund_id',sa.Integer(),sa.ForeignKey('repair_package_refunds.id'),nullable=False),
        sa.Column('lot_id',sa.Integer(),sa.ForeignKey('repair_package_lots.id'),nullable=False),
        sa.Column('spans',sa.JSON(),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("status IN ('reserved','released','applied')",name='ck_repair_package_refund_claim'),
        sa.UniqueConstraint('refund_id','lot_id',name='uq_repair_package_refund_claim'))
    op.create_index('ix_repair_package_refund_claims_lot_id','repair_package_refund_claims',['lot_id'],unique=False)
    op.create_index('ix_repair_package_refund_claims_refund_id','repair_package_refund_claims',['refund_id'],unique=False)
    op.create_table('repair_package_entries',
        sa.Column('store_id',sa.Integer(),sa.ForeignKey('stores.id'),nullable=False),
        sa.Column('lot_id',sa.Integer(),sa.ForeignKey('repair_package_lots.id'),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('purpose',sa.String(length=12),nullable=False),
        sa.Column('hold_id',sa.Integer(),sa.ForeignKey('repair_package_holds.id'),nullable=True),
        sa.Column('original_id',sa.Integer(),sa.ForeignKey('repair_package_entries.id'),nullable=True),
        sa.Column('refund_id',sa.Integer(),sa.ForeignKey('repair_package_refunds.id'),nullable=True),
        sa.Column('spans',sa.JSON(),nullable=False),
        sa.Column('quantity_milli',sa.BigInteger(),nullable=False),
        sa.Column('credit_cents',sa.BigInteger(),nullable=False),
        sa.Column('paid_cents',sa.BigInteger(),nullable=False),
        sa.Column('settlement_cents',sa.BigInteger(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.CheckConstraint("(purpose='capture' AND hold_id IS NOT NULL AND original_id IS NULL AND refund_id IS NULL) OR (purpose='reverse' AND original_id IS NOT NULL AND hold_id IS NOT NULL AND refund_id IS NULL) OR (purpose='refund' AND refund_id IS NOT NULL AND hold_id IS NULL AND original_id IS NULL)",name='ck_repair_package_entry_origin'),
        sa.CheckConstraint("quantity_milli>0 AND credit_cents>=0 AND paid_cents>=0 AND settlement_cents>=0 AND purpose IN ('capture','reverse','refund')",name='ck_repair_package_entry'))
    op.create_index('ix_repair_package_entries_case_id','repair_package_entries',['case_id'],unique=False)
    op.create_index('ix_repair_package_entries_lot_id','repair_package_entries',['lot_id'],unique=False)
    op.create_index('ix_repair_package_entries_original_id','repair_package_entries',['original_id'],unique=False)
    op.create_index('ix_repair_package_entries_store_id','repair_package_entries',['store_id'],unique=False)
    op.create_table('repair_package_reservation_links',
        sa.Column('recognized_cents',sa.BigInteger(),nullable=False),
        sa.Column('hold_id',sa.Integer(),sa.ForeignKey('repair_package_holds.id'),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('quote_id',sa.Integer(),sa.ForeignKey('repair_quotes.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('hold_id',name=None),
        sa.CheckConstraint("amount_cents>=0 AND recognized_cents>=0 AND status IN ('reserved','released','captured')",name='ck_repair_package_reservation_link'))
    op.create_index('ix_repair_package_reservation_links_case_id','repair_package_reservation_links',['case_id'],unique=False)
    op.create_index('ix_repair_package_reservation_links_store_id','repair_package_reservation_links',['store_id'],unique=False)
    op.create_table('repair_package_aftercare_holds',
        sa.Column('aftercare_case_id',sa.Integer(),sa.ForeignKey('aftercare_orders.id'),nullable=False),
        sa.Column('source_case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('plan_id',sa.Integer(),sa.ForeignKey('aftercare_plans.id'),nullable=False),
        sa.Column('original_id',sa.Integer(),sa.ForeignKey('repair_package_entries.id'),nullable=False),
        sa.Column('spans',sa.JSON(),nullable=False),
        sa.Column('quantity_milli',sa.BigInteger(),nullable=False),
        sa.Column('credit_cents',sa.BigInteger(),nullable=False),
        sa.Column('paid_cents',sa.BigInteger(),nullable=False),
        sa.Column('settlement_cents',sa.BigInteger(),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('plan_id','original_id',name='uq_repair_package_aftercare'),
        sa.CheckConstraint("quantity_milli>0 AND status IN ('reserved','released','applied')",name='ck_repair_package_aftercare'))
    op.create_index('ix_repair_package_aftercare_holds_original_id','repair_package_aftercare_holds',['original_id'],unique=False)
    op.create_index('ix_repair_package_aftercare_holds_plan_id','repair_package_aftercare_holds',['plan_id'],unique=False)
    op.create_index('ix_repair_package_aftercare_holds_source_case_id','repair_package_aftercare_holds',['source_case_id'],unique=False)
    op.create_index('ix_repair_package_aftercare_holds_store_id','repair_package_aftercare_holds',['store_id'],unique=False)
    op.create_table('repair_package_payment_links',
        sa.Column('purpose',sa.String(length=12),nullable=False),
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('entry_id',sa.Integer(),sa.ForeignKey('repair_package_entries.id'),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('recognized_cents',sa.BigInteger(),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("(purpose='capture' AND amount_cents>=0 AND recognized_cents>=0) OR (purpose='reverse' AND amount_cents<=0 AND recognized_cents<=0)",name='ck_repair_package_payment'),
        sa.UniqueConstraint('entry_id',name=None))
    op.create_index('ix_repair_package_payment_links_case_id','repair_package_payment_links',['case_id'],unique=False)
    op.create_index('ix_repair_package_payment_links_store_id','repair_package_payment_links',['store_id'],unique=False)
    op.create_table('repair_package_settlements',
        sa.Column('entry_id',sa.Integer(),sa.ForeignKey('repair_package_entries.id'),nullable=False),
        sa.Column('side',sa.String(length=10),nullable=False),
        sa.Column('amount_cents',sa.BigInteger(),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('entry_id','side',name='uq_repair_package_settlement'),
        sa.CheckConstraint("side IN ('center','store') AND amount_cents!=0",name='ck_repair_package_settlement'))
    op.create_index('ix_repair_package_settlements_entry_id','repair_package_settlements',['entry_id'],unique=False)
    op.create_index('ix_repair_package_settlements_store_id','repair_package_settlements',['store_id'],unique=False)
    op.create_table('repair_package_stock_returns',
        sa.Column('result',sa.String(length=1000),nullable=False),
        sa.Column('hold_id',sa.Integer(),sa.ForeignKey('repair_package_aftercare_holds.id'),nullable=False),
        sa.Column('original_stock_id',sa.Integer(),sa.ForeignKey('repair_stock.id'),nullable=False),
        sa.Column('stock_fact_id',sa.Integer(),sa.ForeignKey('repair_stock.id'),nullable=False),
        sa.Column('quantity_milli',sa.BigInteger(),nullable=False),
        sa.Column('value_cents',sa.BigInteger(),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('stock_fact_id',name=None),
        sa.CheckConstraint('quantity_milli>0 AND value_cents>=0',name='ck_repair_package_stock_return'))
    op.create_index('ix_repair_package_stock_returns_hold_id','repair_package_stock_returns',['hold_id'],unique=False)
    op.create_index('ix_repair_package_stock_returns_store_id','repair_package_stock_returns',['store_id'],unique=False)
    with op.batch_alter_table('aftercare_tenders') as batch:
        batch.drop_constraint('ck_aftercare_tender',type_='check')
        batch.create_check_constraint('ck_aftercare_tender',"((kind IN ('cash','principal','benefit','advance') AND credit_cents>0) OR (kind='repair_package' AND credit_cents>=0)) AND units>0")

def downgrade():
    raise RuntimeError('Mixed component purchases and original returns cannot be destructively downgraded')
