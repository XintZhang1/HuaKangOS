"""Explicit store membership price approvals and frozen quotation basis."""
from alembic import op
import sqlalchemy as sa
revision='b80o_member_pricing'
down_revision='a79n_recharge_corrections'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('member_pricing_rules',
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('code',sa.String(40),nullable=False),
        sa.Column('rule_version',sa.Integer(),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('membership_rule_id',sa.Integer(),sa.ForeignKey('membership_rules.id'),nullable=False),
        sa.Column('membership_snapshot',sa.JSON(),nullable=False),
        sa.Column('reference_tier_id',sa.Integer(),sa.ForeignKey('master_member_tiers.id'),nullable=True),
        sa.Column('reference_tier_snapshot',sa.JSON(),nullable=False),
        sa.Column('starts_on',sa.Date(),nullable=False),
        sa.Column('ends_on',sa.Date(),nullable=False),
        sa.Column('stack_mode',sa.String(30),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('case_id',name=None),
        sa.CheckConstraint("rule_version>0 AND starts_on<=ends_on AND stack_mode IN ('member_then_benefits','exclusive_benefits')",name='ck_member_price_rule'),
        sa.UniqueConstraint('store_id','code','rule_version',name='uq_member_price_rule_version'))
    op.create_index('ix_member_pricing_rules_store_id','member_pricing_rules',['store_id'],unique=False)
    op.create_table('member_pricing_scopes',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('member_pricing_rules.id'),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False),
        sa.Column('business_kind',sa.String(12),nullable=False),
        sa.Column('component',sa.String(20),nullable=False),
        sa.Column('source_id',sa.Integer(),nullable=False),
        sa.Column('source_snapshot',sa.JSON(),nullable=False),
        sa.Column('basis_points',sa.Integer(),nullable=False),
        sa.Column('bundle_rule_id',sa.Integer(),sa.ForeignKey('retail_bundle_rules.id'),nullable=True),
        sa.Column('bundle_snapshot',sa.JSON(),nullable=False),
        sa.Column('allow_contract_pricing',sa.Boolean(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("sequence>0 AND basis_points BETWEEN 1 AND 10000 AND ((business_kind='repair' AND component IN ('work','part')) OR (business_kind IN ('retail','addon') AND component IN ('goods','installation')))",name='ck_member_price_scope'),
        sa.UniqueConstraint('rule_id','sequence',name='uq_member_price_scope_sequence'))
    op.create_index('ix_member_pricing_scopes_rule_id','member_pricing_scopes',['rule_id'],unique=False)
    op.create_index('ix_member_pricing_scopes_store_id','member_pricing_scopes',['store_id'],unique=False)
    op.create_table('member_pricing_decisions',
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('member_pricing_rules.id'),nullable=False),
        sa.Column('decision',sa.String(12),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=True),
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("decision IN ('submitted','approved','rejected','cancelled') AND (decision='cancelled' OR evidence_id IS NOT NULL)",name='ck_member_price_decision'),
        sa.UniqueConstraint('rule_id','decision',name='uq_member_price_decision'))
    op.create_index('ix_member_pricing_decisions_rule_id','member_pricing_decisions',['rule_id'],unique=False)
    op.create_index('ix_member_pricing_decisions_store_id','member_pricing_decisions',['store_id'],unique=False)
    op.create_table('member_pricing_snapshots',
        sa.Column('case_id',sa.Integer(),sa.ForeignKey('flow_cases.id'),nullable=False),
        sa.Column('quote_kind',sa.String(12),nullable=False),
        sa.Column('quote_id',sa.Integer(),nullable=False),
        sa.Column('rule_id',sa.Integer(),sa.ForeignKey('member_pricing_rules.id'),nullable=False),
        sa.Column('customer_id',sa.Integer(),sa.ForeignKey('flow_customers.id'),nullable=False),
        sa.Column('member_id',sa.Integer(),sa.ForeignKey('group_members.id'),nullable=False),
        sa.Column('period_id',sa.Integer(),sa.ForeignKey('membership_periods.id'),nullable=False),
        sa.Column('definition_version',sa.Integer(),nullable=False),
        sa.Column('contract',sa.JSON(),nullable=False),
        sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint("definition_version=1 AND quote_kind IN ('repair','retail','addon')",name='ck_member_price_snapshot'),
        sa.UniqueConstraint('store_id','quote_kind','quote_id',name='uq_member_price_quote'))
    op.create_index('ix_member_pricing_snapshots_case_id','member_pricing_snapshots',['case_id'],unique=False)
    op.create_index('ix_member_pricing_snapshots_store_id','member_pricing_snapshots',['store_id'],unique=False)
    op.create_table('member_pricing_lines',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('snapshot_id',sa.Integer(),sa.ForeignKey('member_pricing_snapshots.id'),nullable=False),
        sa.Column('line_key',sa.String(80),nullable=False),
        sa.Column('component',sa.String(20),nullable=False),
        sa.Column('source_id',sa.Integer(),nullable=False),
        sa.Column('scope_id',sa.Integer(),sa.ForeignKey('member_pricing_scopes.id'),nullable=True),
        sa.Column('charge_scope',sa.String(30),nullable=False),
        sa.Column('basis_cents',sa.BigInteger(),nullable=False),
        sa.Column('member_discount_cents',sa.BigInteger(),nullable=False),
        sa.Column('manual_discount_cents',sa.BigInteger(),nullable=False),
        sa.Column('net_cents',sa.BigInteger(),nullable=False),
        sa.Column('carry_cents',sa.BigInteger(),nullable=False),
        sa.Column('basis_points',sa.Integer(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.CheckConstraint('basis_cents>=0 AND member_discount_cents>=0 AND manual_discount_cents>=0 AND net_cents>=0 AND carry_cents>=0 AND basis_points BETWEEN 1 AND 10000 AND member_discount_cents+manual_discount_cents+net_cents=basis_cents',name='ck_member_price_line_money'),
        sa.UniqueConstraint('snapshot_id','line_key','component',name='uq_member_price_line'))
    op.create_index('ix_member_pricing_lines_snapshot_id','member_pricing_lines',['snapshot_id'],unique=False)
    op.create_index('ix_member_pricing_lines_store_id','member_pricing_lines',['store_id'],unique=False)
    op.create_table('member_pricing_authorizations',
        sa.Column('snapshot_id',sa.Integer(),sa.ForeignKey('member_pricing_snapshots.id'),nullable=False),
        sa.Column('evidence_id',sa.Integer(),sa.ForeignKey('flow_files.id'),nullable=False),
        sa.Column('snapshot_digest',sa.String(64),nullable=False),
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('store_id',sa.Integer(),nullable=False),
        sa.UniqueConstraint('snapshot_id',name=None))
    op.create_index('ix_member_pricing_authorizations_store_id','member_pricing_authorizations',['store_id'],unique=False)

def downgrade():
    raise RuntimeError('会员价格原依据与独立批准不得自动删除；请按备份恢复流程办理')
