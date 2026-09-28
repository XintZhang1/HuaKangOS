"""Add durable assistant Runtime records without changing native business data.

This revision contains fixed schema definitions and never imports app models.
Existing assistant tables are reflected by Alembic batch operations so their
historical columns, constraints and indexes are retained.
"""
from alembic import context, op
import sqlalchemy as sa

revision = 'h53k_assistant_runtime'
down_revision = 'h52j_assistant_work_plans'
branch_labels = None
depends_on = None

_EMPTY_SYNTHETIC_DOWNGRADE = 'huakangos_empty_synthetic_downgrade'


def upgrade():
    # Existing WorkPlan/Proposal primary keys already exist at h52j.
    # Build their new dependants first, then add each back-reference once.
    op.create_table('business_assistant_plan_steps',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_step_plan'), nullable=False),
        sa.Column('key', sa.String(50), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('title', sa.String(160), nullable=False),
        sa.Column('wait_for', sa.String(500), nullable=False, server_default=''),
        sa.Column('depends_on', sa.JSON(), nullable=False),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('business_assistant_proposals.id', name='fk_assistant_step_proposal'), nullable=True),
        sa.Column('object_ref', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('workflow_id', sa.String(100), nullable=True),
        sa.Column('form_ref', sa.String(160), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=False),
        sa.Column('completion_conditions', sa.JSON(), nullable=False),
        sa.Column('required', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('status', sa.String(24), nullable=False, server_default='waiting'),
        sa.Column('wait_reason', sa.String(100), nullable=True),
        sa.Column('last_evidence', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('intent_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('plan_id', 'key', name='uq_assistant_step_plan_key'),
        sa.UniqueConstraint('plan_id', 'proposal_id', name='uq_assistant_step_plan_proposal'),
        sa.CheckConstraint('position >= 0', name='ck_assistant_step_position'),
        sa.CheckConstraint('intent_version >= 1', name='ck_assistant_step_intent_version'),
        sa.CheckConstraint('version >= 1', name='ck_assistant_step_version'),
        sa.CheckConstraint("status IN ('waiting','needs_input','awaiting_confirmation','completed','failed','uncertain','cancelled')", name='ck_assistant_step_status'),
    )
    op.create_index('ix_assistant_step_plan_position', 'business_assistant_plan_steps', ['plan_id', 'position'])
    op.create_index('ix_assistant_step_proposal', 'business_assistant_plan_steps', ['proposal_id'])

    op.create_table('business_assistant_work_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_assistant_work_item_owner'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id', name='fk_assistant_work_item_store'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('business_assistant_sessions.id', name='fk_assistant_work_item_session'), nullable=False),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_work_item_plan'), nullable=True),
        sa.Column('step_id', sa.String(36), sa.ForeignKey('business_assistant_plan_steps.id', name='fk_assistant_work_item_step'), nullable=True),
        sa.Column('origin_request_id', sa.String(100), nullable=False),
        sa.Column('input_item_id', sa.String(100), nullable=False),
        sa.Column('intent_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('item_kind', sa.String(12), nullable=False),
        sa.Column('intent_key', sa.String(255), nullable=False),
        sa.Column('operation_id', sa.String(180), nullable=False),
        sa.Column('validated_intent', sa.JSON(), nullable=False),
        sa.Column('source_refs', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
        sa.Column('supersedes_id', sa.String(36), sa.ForeignKey('business_assistant_work_items.id', name='fk_assistant_work_item_supersedes'), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('owner_id', 'store_id', 'intent_key', name='uq_assistant_work_item_intent'),
        sa.CheckConstraint("item_kind IN ('read','prepare')", name='ck_assistant_work_item_kind'),
        sa.CheckConstraint("status IN ('planned','prepared','settled','uncertain')", name='ck_assistant_work_item_status'),
        sa.CheckConstraint('intent_version >= 1', name='ck_assistant_work_item_intent_version'),
        sa.CheckConstraint('version >= 1', name='ck_assistant_work_item_version'),
        sa.CheckConstraint('step_id IS NULL OR plan_id IS NOT NULL', name='ck_assistant_work_item_step_plan'),
        sa.CheckConstraint('supersedes_id IS NULL OR supersedes_id <> id', name='ck_assistant_work_item_not_self_supersedes'),
    )
    op.create_index('ix_assistant_work_item_session', 'business_assistant_work_items', ['session_id'])
    op.create_index('ix_assistant_work_item_plan', 'business_assistant_work_items', ['plan_id'])
    op.create_index('ix_assistant_work_item_step_intent', 'business_assistant_work_items', ['step_id', 'intent_version'])
    op.create_index('ix_assistant_work_item_supersedes', 'business_assistant_work_items', ['supersedes_id'])

    op.create_table('business_assistant_context_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_assistant_context_owner'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id', name='fk_assistant_context_store'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('business_assistant_sessions.id', name='fk_assistant_context_session'), nullable=False),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_context_plan'), nullable=True),
        sa.Column('goal_version', sa.Integer(), nullable=True),
        sa.Column('through_message_id', sa.Integer(), sa.ForeignKey('business_assistant_messages.id', name='fk_assistant_context_message'), nullable=False),
        sa.Column('goal', sa.String(300), nullable=False),
        sa.Column('constraints', sa.JSON(), nullable=False),
        sa.Column('confirmed_selections', sa.JSON(), nullable=False),
        sa.Column('open_questions', sa.JSON(), nullable=False),
        sa.Column('evidence_refs', sa.JSON(), nullable=False),
        sa.Column('unverified_notes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('(plan_id IS NULL AND goal_version IS NULL) OR (plan_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version >= 1)', name='ck_assistant_context_goal_version'),
    )
    op.create_index('ix_assistant_context_owner_store', 'business_assistant_context_snapshots', ['owner_id', 'store_id'])
    op.create_index('ix_assistant_context_session', 'business_assistant_context_snapshots', ['session_id'])
    op.create_index('ix_assistant_context_plan', 'business_assistant_context_snapshots', ['plan_id'])
    op.create_index('ix_assistant_context_message', 'business_assistant_context_snapshots', ['through_message_id'])

    op.create_table('business_assistant_followup_grants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_grant_plan'), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_assistant_grant_owner'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id', name='fk_assistant_grant_store'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('business_assistant_sessions.id', name='fk_assistant_grant_session'), nullable=False),
        sa.Column('owner_role', sa.String(20), nullable=False),
        sa.Column('access_version', sa.Integer(), nullable=False),
        sa.Column('goal_version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('stop_reason', sa.String(160), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active','paused','revoked')", name='ck_assistant_grant_status'),
        sa.CheckConstraint('access_version >= 1 AND goal_version >= 1 AND version >= 1', name='ck_assistant_grant_versions'),
    )
    op.create_index('uq_assistant_grant_active_plan', 'business_assistant_followup_grants', ['plan_id'], unique=True, sqlite_where=sa.text("status = 'active'"), postgresql_where=sa.text("status = 'active'"))
    op.create_index('ix_assistant_grant_owner_store', 'business_assistant_followup_grants', ['owner_id', 'store_id'])
    op.create_index('ix_assistant_grant_session', 'business_assistant_followup_grants', ['session_id'])
    op.create_index('ix_assistant_grant_plan', 'business_assistant_followup_grants', ['plan_id'])

    op.create_table('business_assistant_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_assistant_run_owner'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id', name='fk_assistant_run_store'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('business_assistant_sessions.id', name='fk_assistant_run_session'), nullable=False),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_run_plan'), nullable=True),
        sa.Column('trigger_kind', sa.String(12), nullable=False),
        sa.Column('trigger_key', sa.String(255), nullable=False),
        sa.Column('request_id', sa.String(100), nullable=True),
        sa.Column('request_digest', sa.String(64), nullable=False),
        sa.Column('entry_context', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('auth_kind', sa.String(12), nullable=False),
        sa.Column('login_session_ref', sa.String(64), nullable=True),
        sa.Column('grant_id', sa.String(36), sa.ForeignKey('business_assistant_followup_grants.id', name='fk_assistant_run_grant'), nullable=True),
        sa.Column('goal_version', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('next_run_at', sa.DateTime(), nullable=False),
        sa.Column('lease_owner', sa.String(80), nullable=True),
        sa.Column('lease_until', sa.DateTime(), nullable=True),
        sa.Column('fence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stop_requested', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('display_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('display_revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('event_seq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('usage', sa.JSON(), nullable=False),
        sa.Column('error_code', sa.String(80), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('owner_id', 'store_id', 'trigger_key', name='uq_assistant_run_trigger'),
        sa.CheckConstraint("trigger_kind IN ('user','signal','manual')", name='ck_assistant_run_trigger_kind'),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name='ck_assistant_run_status'),
        sa.CheckConstraint("auth_kind IN ('login','grant')", name='ck_assistant_run_auth_kind'),
        sa.CheckConstraint("(auth_kind = 'login' AND login_session_ref IS NOT NULL AND grant_id IS NULL) OR (auth_kind = 'grant' AND login_session_ref IS NULL AND grant_id IS NOT NULL AND plan_id IS NOT NULL AND goal_version IS NOT NULL)", name='ck_assistant_run_auth_source'),
        sa.CheckConstraint("trigger_kind <> 'user' OR request_id IS NOT NULL", name='ck_assistant_run_user_request'),
        sa.CheckConstraint('(plan_id IS NULL AND goal_version IS NULL) OR (plan_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version >= 1)', name='ck_assistant_run_goal_version'),
        sa.CheckConstraint('fence >= 0 AND attempt >= 0 AND display_revision >= 0 AND event_seq >= 0', name='ck_assistant_run_counters'),
        sa.CheckConstraint('version >= 1', name='ck_assistant_run_version'),
        sa.CheckConstraint('length(request_digest) = 64', name='ck_assistant_run_request_digest'),
        sa.CheckConstraint('login_session_ref IS NULL OR length(login_session_ref) = 64', name='ck_assistant_run_login_ref'),
    )
    op.create_index('ix_assistant_run_queue', 'business_assistant_runs', ['status', 'next_run_at'])
    op.create_index('ix_assistant_run_lease_until', 'business_assistant_runs', ['lease_until'])
    op.create_index('ix_assistant_run_session', 'business_assistant_runs', ['session_id'])
    op.create_index('ix_assistant_run_plan', 'business_assistant_runs', ['plan_id'])
    op.create_index('ix_assistant_run_grant', 'business_assistant_runs', ['grant_id'])
    op.create_index('ix_assistant_run_owner_store', 'business_assistant_runs', ['owner_id', 'store_id'])

    op.create_table('business_assistant_run_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('business_assistant_runs.id', name='fk_assistant_run_item_run'), nullable=True),
        sa.Column('work_item_id', sa.String(36), sa.ForeignKey('business_assistant_work_items.id', name='fk_assistant_run_item_work'), nullable=True),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('business_assistant_proposals.id', name='fk_assistant_run_item_proposal'), nullable=True),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('item_key', sa.String(255), nullable=False),
        sa.Column('attempt_no', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('tool_name', sa.String(80), nullable=True),
        sa.Column('validated_arguments', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('result_refs', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_code', sa.String(80), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('submission_snapshot', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('submission_digest', sa.String(64), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('run_id', 'item_key', 'attempt_no', name='uq_assistant_run_item_attempt'),
        sa.CheckConstraint("kind IN ('model','tool','batch_row','confirmation')", name='ck_assistant_run_item_kind'),
        sa.CheckConstraint("status IN ('pending','running','succeeded','failed','uncertain','skipped')", name='ck_assistant_run_item_status'),
        sa.CheckConstraint("(kind = 'confirmation' AND proposal_id IS NOT NULL AND submission_snapshot IS NOT NULL AND submission_digest IS NOT NULL) OR (kind <> 'confirmation' AND run_id IS NOT NULL AND submission_snapshot IS NULL AND submission_digest IS NULL)", name='ck_assistant_run_item_confirmation'),
        sa.CheckConstraint('attempt_no >= 1 AND version >= 1', name='ck_assistant_run_item_versions'),
        sa.CheckConstraint('submission_digest IS NULL OR length(submission_digest) = 64', name='ck_assistant_run_item_digest'),
    )
    op.create_index('uq_assistant_run_item_confirmation', 'business_assistant_run_items', ['proposal_id'], unique=True, sqlite_where=sa.text("kind = 'confirmation'"), postgresql_where=sa.text("kind = 'confirmation'"))
    op.create_index('ix_assistant_run_item_work', 'business_assistant_run_items', ['work_item_id'])
    op.create_index('ix_assistant_run_item_proposal', 'business_assistant_run_items', ['proposal_id'])

    op.create_table('business_assistant_run_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('business_assistant_runs.id', name='fk_assistant_run_event_run'), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(40), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('run_id', 'seq', name='uq_assistant_run_event_seq'),
        sa.CheckConstraint('seq >= 1', name='ck_assistant_run_event_seq'),
        sa.CheckConstraint("type IN ('run.queued','run.started','run.progress','tool.finished','proposal.prepared','plan.updated','run.completed','run.failed','run.cancelled')", name='ck_assistant_run_event_type'),
    )

    op.create_table('business_assistant_wake_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('signal_key', sa.String(255), nullable=False),
        sa.Column('topic', sa.String(80), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id', name='fk_assistant_wake_store'), nullable=False),
        sa.Column('object_ref', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('business_assistant_proposals.id', name='fk_assistant_wake_proposal'), nullable=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('flow_tasks.id', name='fk_assistant_wake_task'), nullable=True),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_wake_plan'), nullable=True),
        sa.Column('source_ref', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('state', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('signal_key', name='uq_assistant_wake_signal'),
        sa.CheckConstraint("state IN ('pending','dispatched')", name='ck_assistant_wake_state'),
        sa.CheckConstraint('attempt >= 0 AND version >= 1', name='ck_assistant_wake_counters'),
    )
    op.create_index('ix_assistant_wake_dispatch', 'business_assistant_wake_events', ['state', 'next_attempt_at'])
    op.create_index('ix_assistant_wake_store', 'business_assistant_wake_events', ['store_id'])
    op.create_index('ix_assistant_wake_proposal', 'business_assistant_wake_events', ['proposal_id'])
    op.create_index('ix_assistant_wake_task', 'business_assistant_wake_events', ['task_id'])
    op.create_index('ix_assistant_wake_plan', 'business_assistant_wake_events', ['plan_id'])

    op.create_table('business_assistant_notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_assistant_notification_owner'), nullable=False),
        sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id', name='fk_assistant_notification_store'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('business_assistant_sessions.id', name='fk_assistant_notification_session'), nullable=True),
        sa.Column('plan_id', sa.String(36), sa.ForeignKey('business_assistant_work_plans.id', name='fk_assistant_notification_plan'), nullable=True),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('business_assistant_proposals.id', name='fk_assistant_notification_proposal'), nullable=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('flow_tasks.id', name='fk_assistant_notification_task'), nullable=True),
        sa.Column('source_key', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(80), nullable=False),
        sa.Column('safe_summary', sa.String(600), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='unread'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('owner_id', 'store_id', 'source_key', 'kind', name='uq_assistant_notification_source'),
        sa.CheckConstraint("status IN ('unread','read','resolved')", name='ck_assistant_notification_status'),
        sa.CheckConstraint('version >= 1', name='ck_assistant_notification_version'),
    )
    op.create_index('ix_assistant_notification_owner_status', 'business_assistant_notifications', ['owner_id', 'store_id', 'status'])
    op.create_index('ix_assistant_notification_session', 'business_assistant_notifications', ['session_id'])
    op.create_index('ix_assistant_notification_plan', 'business_assistant_notifications', ['plan_id'])
    op.create_index('ix_assistant_notification_proposal', 'business_assistant_notifications', ['proposal_id'])
    op.create_index('ix_assistant_notification_task', 'business_assistant_notifications', ['task_id'])

    # Reflect the h52j table; never use current ORM metadata as copy_from.
    with op.batch_alter_table('business_assistant_work_plans') as batch:
        batch.add_column(sa.Column('engine_version', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('goal_version', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('status', sa.String(20), nullable=False, server_default='active'))
        batch.add_column(sa.Column('next_check_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('context_snapshot_id', sa.String(36), nullable=True))
        batch.create_check_constraint('ck_assistant_plan_engine', 'engine_version IN (1,2)')
        batch.create_check_constraint('ck_assistant_plan_versions', 'goal_version >= 1 AND version >= 1')
        batch.create_check_constraint('ck_assistant_plan_status', "status IN ('active','paused','completed','cancelled')")
        batch.create_foreign_key('fk_assistant_plan_context', 'business_assistant_context_snapshots', ['context_snapshot_id'], ['id'])
        batch.create_index('ix_assistant_plan_owner_store', ['owner_id', 'store_id'])
        batch.create_index('ix_assistant_plan_next_check', ['status', 'next_check_at'])

    # NULL preserves every legacy card; no WorkItem or snapshot is fabricated.
    with op.batch_alter_table('business_assistant_proposals') as batch:
        batch.add_column(sa.Column('source_work_item_id', sa.String(36), nullable=True))
        batch.create_unique_constraint('uq_assistant_proposal_work_item', ['source_work_item_id'])
        batch.create_foreign_key('fk_assistant_proposal_work_item', 'business_assistant_work_items', ['source_work_item_id'], ['id'])


def _require_empty_synthetic_database():
    # The flag is an explicit programmatic Alembic test-fixture marker. A string
    # from an environment variable or -x argument is intentionally insufficient.
    if context.config.attributes.get(_EMPTY_SYNTHETIC_DOWNGRADE) is not True:
        raise RuntimeError('Runtime downgrade is restricted to explicitly marked empty synthetic databases; restore a verified backup instead')
    if context.is_offline_mode():
        raise RuntimeError('Empty synthetic downgrade requires online emptiness checks')
    bind = op.get_bind()
    if bind.dialect.name not in {'sqlite', 'postgresql'}:
        raise RuntimeError('Empty synthetic downgrade supports only SQLite and PostgreSQL')
    # At REPEATABLE READ a post-lock SELECT could still use an earlier snapshot
    # and miss rows inserted before the lock. Never weaken the app's normal
    # isolation here; an optional PostgreSQL fixture must opt into READ COMMITTED
    # before its migration transaction begins, otherwise downgrade is refused.
    if bind.dialect.name == 'postgresql' and bind.get_isolation_level().upper() != 'READ COMMITTED':
        raise RuntimeError('Empty synthetic PostgreSQL downgrade requires a READ COMMITTED test transaction')
    inspector = sa.inspect(bind)
    default_schema = inspector.default_schema_name
    version_schema = context.get_context().opts.get('version_table_schema') or default_schema
    version_table = context.get_context().opts.get('version_table', 'alembic_version')
    tables = []
    for schema in inspector.get_schema_names():
        if bind.dialect.name == 'postgresql' and (schema == 'information_schema' or schema.startswith('pg_')):
            continue
        for name in inspector.get_table_names(schema=schema):
            if schema == version_schema and name == version_table:
                continue
            tables.append(sa.Table(name, sa.MetaData(), schema=schema))

    def reject_rows():
        for table in tables:
            query = sa.select(sa.literal(1)).select_from(table).limit(1)
            if bind.execute(query).first() is not None:
                raise RuntimeError('Synthetic downgrade requires every non-version table to be empty; retained data found in ' + table.fullname)

    # Check all tables, including unrelated original business tables. No DDL or
    # deletion happens until this succeeds. PostgreSQL locks close the gap
    # between checking an empty synthetic fixture and removing its schema.
    reject_rows()
    if bind.dialect.name == 'postgresql':
        preparer = bind.dialect.identifier_preparer
        for table in tables:
            bind.exec_driver_sql('LOCK TABLE ' + preparer.format_table(table) + ' IN ACCESS EXCLUSIVE MODE')
        reject_rows()


def downgrade():
    _require_empty_synthetic_database()
    # Break both old-table back-references before dropping Runtime tables.
    with op.batch_alter_table('business_assistant_proposals') as batch:
        batch.drop_constraint('fk_assistant_proposal_work_item', type_='foreignkey')
        batch.drop_constraint('uq_assistant_proposal_work_item', type_='unique')
        batch.drop_column('source_work_item_id')
    with op.batch_alter_table('business_assistant_work_plans') as batch:
        batch.drop_constraint('fk_assistant_plan_context', type_='foreignkey')
        batch.drop_constraint('ck_assistant_plan_engine', type_='check')
        batch.drop_constraint('ck_assistant_plan_versions', type_='check')
        batch.drop_constraint('ck_assistant_plan_status', type_='check')
        batch.drop_index('ix_assistant_plan_owner_store')
        batch.drop_index('ix_assistant_plan_next_check')
        batch.drop_column('context_snapshot_id')
        batch.drop_column('next_check_at')
        batch.drop_column('status')
        batch.drop_column('goal_version')
        batch.drop_column('engine_version')

    op.drop_table('business_assistant_notifications')
    op.drop_table('business_assistant_wake_events')
    op.drop_table('business_assistant_run_events')
    op.drop_table('business_assistant_run_items')
    op.drop_table('business_assistant_runs')
    op.drop_table('business_assistant_followup_grants')
    op.drop_table('business_assistant_context_snapshots')
    op.drop_table('business_assistant_work_items')
    op.drop_table('business_assistant_plan_steps')
