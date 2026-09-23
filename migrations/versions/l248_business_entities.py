"""Reviewed business identity versions and scoped attribution. Frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = 'l248_business_entities'
down_revision = 'k137_user_access'
branch_labels = None
depends_on = None


def upgrade():
    # Keep original invoice migrations frozen; widen actual issuer fields here.
    with op.batch_alter_table('invoice_applications') as batch:
        batch.alter_column('issuer_name',existing_type=sa.String(160),type_=sa.String(180),existing_nullable=False)
        batch.alter_column('issuer_tax_id',existing_type=sa.String(20),type_=sa.String(30),existing_nullable=False)
    with op.batch_alter_table('invoice_results') as batch:
        batch.alter_column('issuer_tax_id',existing_type=sa.String(20),type_=sa.String(30),existing_nullable=False)
    op.create_table('business_entity_store_controls',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('store_id', name='uq_business_entity_store_control'),
    )
    op.create_index('ix_business_entity_store_controls_store_id', 'business_entity_store_controls', ['store_id'], unique=False)
    op.create_table('business_entities',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('tax_identifier', sa.String(length=30), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('tax_identifier', name=None),
        sa.UniqueConstraint('code', name=None),
    )
    op.create_table('business_entity_account_channels',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('digest', sa.String(length=64), nullable=False),
        sa.Column('owner_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=False),
        sa.UniqueConstraint('digest', name=None),
        sa.UniqueConstraint('account_id', name=None),
    )
    op.create_table('business_entity_applications',
        sa.Column('id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False, primary_key=True),
        sa.Column('operation', sa.String(length=25), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("operation IN ('revision','store_binding','account_binding','policy')", name='ck_business_entity_operation'),
    )
    op.create_index('ix_business_entity_applications_store_id', 'business_entity_applications', ['store_id'], unique=False)
    op.create_table('business_entity_decisions',
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False, primary_key=True),
        sa.Column('decision', sa.String(length=15), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=True),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("(decision='approved' AND evidence_id IS NOT NULL) OR decision IN ('rejected','cancelled')", name='ck_entity_decision'),
    )
    op.create_index('ix_business_entity_decisions_store_id', 'business_entity_decisions', ['store_id'], unique=False)
    op.create_table('business_entity_revision_proposals',
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False, primary_key=True),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('business_entities.id'), nullable=True),
        sa.Column('expected_entity_version', sa.Integer(), nullable=True),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('tax_identifier', sa.String(length=30), nullable=False),
        sa.Column('legal_name', sa.String(length=180), nullable=False),
        sa.Column('registered_address', sa.String(length=300), nullable=False),
        sa.Column('contact_phone', sa.String(length=40), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('(entity_id IS NULL AND expected_entity_version IS NULL) OR (entity_id IS NOT NULL AND expected_entity_version>0)', name='ck_entity_proposal_version'),
    )
    op.create_index('ix_business_entity_revision_proposals_store_id', 'business_entity_revision_proposals', ['store_id'], unique=False)
    op.create_table('business_entity_revisions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('entity_id', sa.Integer(), sa.ForeignKey('business_entities.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('legal_name', sa.String(length=180), nullable=False),
        sa.Column('registered_address', sa.String(length=300), nullable=False),
        sa.Column('contact_phone', sa.String(length=40), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False),
        sa.Column('source_store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False),
        sa.Column('source_evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('application_id', name=None),
        sa.CheckConstraint('revision>0', name='ck_business_entity_revision'),
        sa.UniqueConstraint('entity_id', 'revision', name='uq_business_entity_revision'),
    )
    op.create_index('ix_business_entity_revisions_entity_id', 'business_entity_revisions', ['entity_id'], unique=False)
    op.create_table('business_entity_submissions',
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False, primary_key=True),
        sa.Column('control_version', sa.Integer(), nullable=False),
        sa.Column('source_evidence_id', sa.Integer(), sa.ForeignKey('flow_files.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
    )
    op.create_index('ix_business_entity_submissions_store_id', 'business_entity_submissions', ['store_id'], unique=False)
    op.create_table('business_entity_account_bindings',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=False),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('business_entity_revisions.id'), nullable=False),
        sa.Column('channel_id', sa.Integer(), sa.ForeignKey('business_entity_account_channels.id'), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('holder_name', sa.String(length=180), nullable=False),
        sa.Column('channel_type', sa.String(length=15), nullable=False),
        sa.Column('channel_identifier', sa.String(length=100), nullable=False),
        sa.Column('institution_name', sa.String(length=180), nullable=False),
        sa.Column('account_name', sa.String(length=100), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('application_id', name=None),
        sa.CheckConstraint("channel_type IN ('bank','cash','wallet')", name='ck_entity_account_binding'),
    )
    op.create_index('ix_business_entity_account_bindings_account_id', 'business_entity_account_bindings', ['account_id'], unique=False)
    op.create_index('ix_business_entity_account_bindings_store_id', 'business_entity_account_bindings', ['store_id'], unique=False)
    op.create_table('business_entity_account_proposals',
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False, primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('flow_accounts.id'), nullable=False),
        sa.Column('expected_account_version', sa.Integer(), nullable=False),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('business_entity_revisions.id'), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('holder_name', sa.String(length=180), nullable=False),
        sa.Column('channel_type', sa.String(length=15), nullable=False),
        sa.Column('channel_identifier', sa.String(length=100), nullable=False),
        sa.Column('institution_name', sa.String(length=180), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("expected_account_version>0 AND channel_type IN ('bank','cash','wallet')", name='ck_entity_account_proposal'),
    )
    op.create_index('ix_business_entity_account_proposals_store_id', 'business_entity_account_proposals', ['store_id'], unique=False)
    op.create_table('business_entity_store_bindings',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('business_entity_revisions.id'), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('application_id', name=None),
    )
    op.create_index('ix_business_entity_store_bindings_store_id', 'business_entity_store_bindings', ['store_id'], unique=False)
    op.create_table('business_entity_store_proposals',
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False, primary_key=True),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('business_entity_revisions.id'), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
    )
    op.create_index('ix_business_entity_store_proposals_store_id', 'business_entity_store_proposals', ['store_id'], unique=False)
    op.create_table('business_entity_policies',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('policy_version', sa.Integer(), nullable=False),
        sa.Column('binding_id', sa.Integer(), sa.ForeignKey('business_entity_store_bindings.id'), nullable=False),
        sa.Column('case_cursor', sa.Integer(), nullable=False),
        sa.Column('cash_cursor', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.UniqueConstraint('application_id', name=None),
        sa.CheckConstraint('policy_version=1 AND case_cursor>=0 AND cash_cursor>=0', name='ck_entity_policy'),
        sa.UniqueConstraint('store_id', name='uq_entity_policy_store'),
    )
    op.create_index('ix_business_entity_policies_store_id', 'business_entity_policies', ['store_id'], unique=False)
    op.create_table('business_entity_policy_proposals',
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('business_entity_applications.id'), nullable=False, primary_key=True),
        sa.Column('binding_id', sa.Integer(), sa.ForeignKey('business_entity_store_bindings.id'), nullable=False),
        sa.Column('policy_version', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('policy_version=1', name='ck_entity_policy_proposal'),
    )
    op.create_index('ix_business_entity_policy_proposals_store_id', 'business_entity_policy_proposals', ['store_id'], unique=False)
    op.create_table('business_entity_case_contexts',
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('flow_cases.id'), nullable=False, primary_key=True),
        sa.Column('policy_id', sa.Integer(), sa.ForeignKey('business_entity_policies.id'), nullable=False),
        sa.Column('binding_id', sa.Integer(), sa.ForeignKey('business_entity_store_bindings.id'), nullable=False),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('business_entity_revisions.id'), nullable=False),
        sa.Column('source_case_id', sa.Integer(), sa.ForeignKey('business_entity_case_contexts.case_id'), nullable=True),
        sa.Column('derived_kind', sa.String(length=30), nullable=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('frozen_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("(source_case_id IS NULL AND derived_kind IS NULL) OR (source_case_id IS NOT NULL AND derived_kind IS NOT NULL AND source_case_id<case_id AND derived_kind IN ('aftercare','invoice','vehicle_return','claim','advance_refund','finance_correction','other_return'))", name='ck_entity_case_derivation'),
    )
    op.create_index('ix_business_entity_case_contexts_store_id', 'business_entity_case_contexts', ['store_id'], unique=False)
    op.create_table('business_entity_cash_contexts',
        sa.Column('cash_id', sa.Integer(), sa.ForeignKey('cash_entries.id'), nullable=False, primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('business_entity_case_contexts.case_id'), nullable=False),
        sa.Column('account_binding_id', sa.Integer(), sa.ForeignKey('business_entity_account_bindings.id'), nullable=False),
        sa.Column('original_cash_id', sa.Integer(), sa.ForeignKey('business_entity_cash_contexts.cash_id'), nullable=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('frozen_at', sa.DateTime(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
    )
    op.create_index('ix_business_entity_cash_contexts_store_id', 'business_entity_cash_contexts', ['store_id'], unique=False)


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text('SELECT COUNT(*) FROM invoice_applications WHERE length(issuer_name)>160 OR length(issuer_tax_id)>20')) or bind.scalar(sa.text('SELECT COUNT(*) FROM invoice_results WHERE length(issuer_tax_id)>20')):
        raise RuntimeError('已有超出旧版长度的实际开票主体资料，不可降级截断原记录')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_store_controls')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entities')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_account_channels')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_applications')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_decisions')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_revision_proposals')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_revisions')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_submissions')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_account_bindings')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_account_proposals')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_store_bindings')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_store_proposals')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_policies')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_policy_proposals')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_case_contexts')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    if bind.scalar(sa.text('SELECT COUNT(*) FROM business_entity_cash_contexts')):
        raise RuntimeError('已有主体资料及归属事实，不可直接降级丢弃历史')
    op.drop_table('business_entity_cash_contexts')
    op.drop_table('business_entity_case_contexts')
    op.drop_table('business_entity_policy_proposals')
    op.drop_table('business_entity_policies')
    op.drop_table('business_entity_store_proposals')
    op.drop_table('business_entity_store_bindings')
    op.drop_table('business_entity_account_proposals')
    op.drop_table('business_entity_account_bindings')
    op.drop_table('business_entity_submissions')
    op.drop_table('business_entity_revisions')
    op.drop_table('business_entity_revision_proposals')
    op.drop_table('business_entity_decisions')
    op.drop_table('business_entity_applications')
    op.drop_table('business_entity_account_channels')
    op.drop_table('business_entities')
    op.drop_table('business_entity_store_controls')
    with op.batch_alter_table('invoice_results') as batch:
        batch.alter_column('issuer_tax_id',existing_type=sa.String(30),type_=sa.String(20),existing_nullable=False)
    with op.batch_alter_table('invoice_applications') as batch:
        batch.alter_column('issuer_name',existing_type=sa.String(180),type_=sa.String(160),existing_nullable=False)
        batch.alter_column('issuer_tax_id',existing_type=sa.String(30),type_=sa.String(20),existing_nullable=False)
