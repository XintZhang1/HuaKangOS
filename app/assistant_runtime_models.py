"""Durable assistant runtime records, separate from business facts.

These models do not enqueue work or perform native operations. Ownership across
the referenced session, plan, step and proposal is also checked by services;
individual foreign keys do not establish permission to use those records.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint, event, false, true,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow
from .models import StoreScoped


class PlanStep(Base):
    """One normalized step; dependencies refer to stable keys in the same plan."""

    __tablename__ = 'business_assistant_plan_steps'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_step_plan'), nullable=False)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    wait_for: Mapped[str] = mapped_column(
        String(500), nullable=False, default='', server_default='')
    depends_on: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Compatibility for a real legacy/single card. Current batch cards are
    # reached through WorkItem.step_id and Proposal.source_work_item_id.
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_proposals.id',
                               name='fk_assistant_step_proposal'), nullable=True)
    object_ref: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    form_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    completion_conditions: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list)
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true())
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default='waiting', server_default='waiting')
    wait_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_evidence: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    intent_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        UniqueConstraint('plan_id', 'key', name='uq_assistant_step_plan_key'),
        UniqueConstraint('plan_id', 'proposal_id',
                         name='uq_assistant_step_plan_proposal'),
        CheckConstraint('position >= 0', name='ck_assistant_step_position'),
        CheckConstraint('intent_version >= 1',
                        name='ck_assistant_step_intent_version'),
        CheckConstraint('version >= 1', name='ck_assistant_step_version'),
        CheckConstraint(
            "status IN ('waiting','needs_input','awaiting_confirmation',"
            "'completed','failed','uncertain','cancelled')",
            name='ck_assistant_step_status'),
        Index('ix_assistant_step_plan_position', 'plan_id', 'position'),
        Index('ix_assistant_step_proposal', 'proposal_id'),
    )


class WorkItem(StoreScoped, Base):
    """A server-identified read or preparation intent, stable across Runs.

The caller supplies its verified store explicitly. StoreScoped is retained for
the existing tenancy filters; this field adds no ORM default store. The original
tenancy listener is unchanged and must not be used to infer worker ownership.
"""

    __tablename__ = 'business_assistant_work_items'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id', name='fk_assistant_work_item_owner'),
        nullable=False)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id', name='fk_assistant_work_item_store'),
        nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_sessions.id',
                               name='fk_assistant_work_item_session'),
        nullable=False)
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_work_item_plan'), nullable=True)
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_plan_steps.id',
                               name='fk_assistant_work_item_step'), nullable=True)
    origin_request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    intent_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    item_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    intent_key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(180), nullable=False)
    validated_intent: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='planned', server_default='planned')
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_items.id',
                               name='fk_assistant_work_item_supersedes'),
        nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        UniqueConstraint('owner_id', 'store_id', 'intent_key',
                         name='uq_assistant_work_item_intent'),
        CheckConstraint("item_kind IN ('read','prepare')",
                        name='ck_assistant_work_item_kind'),
        CheckConstraint("status IN ('planned','prepared','settled','uncertain')",
                        name='ck_assistant_work_item_status'),
        CheckConstraint('intent_version >= 1',
                        name='ck_assistant_work_item_intent_version'),
        CheckConstraint('version >= 1', name='ck_assistant_work_item_version'),
        CheckConstraint('step_id IS NULL OR plan_id IS NOT NULL',
                        name='ck_assistant_work_item_step_plan'),
        CheckConstraint('supersedes_id IS NULL OR supersedes_id <> id',
                        name='ck_assistant_work_item_not_self_supersedes'),
        Index('ix_assistant_work_item_session', 'session_id'),
        Index('ix_assistant_work_item_plan', 'plan_id'),
        Index('ix_assistant_work_item_step_intent', 'step_id', 'intent_version'),
        Index('ix_assistant_work_item_supersedes', 'supersedes_id'),
    )


class Run(StoreScoped, Base):
    """Durable assistant execution; its identity source is checked by services."""

    __tablename__ = 'business_assistant_runs'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id', name='fk_assistant_run_owner'), nullable=False)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id', name='fk_assistant_run_store'), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_sessions.id',
                               name='fk_assistant_run_session'), nullable=False)
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_run_plan'), nullable=True)
    trigger_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    trigger_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_context: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True)
    auth_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    # Hash of the original LoginSession, not its cookie and deliberately no FK:
    # logout/expiry may delete that session while this audit record remains.
    login_session_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_followup_grants.id',
                               name='fk_assistant_run_grant'), nullable=True)
    goal_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='queued', server_default='queued')
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow)
    lease_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    stop_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false())
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    display_text: Mapped[str] = mapped_column(
        Text, nullable=False, default='', server_default='')
    display_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    event_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    usage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow)

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        UniqueConstraint('owner_id', 'store_id', 'trigger_key',
                         name='uq_assistant_run_trigger'),
        CheckConstraint("trigger_kind IN ('user','signal','manual')",
                        name='ck_assistant_run_trigger_kind'),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')",
                        name='ck_assistant_run_status'),
        CheckConstraint("auth_kind IN ('login','grant')", name='ck_assistant_run_auth_kind'),
        CheckConstraint(
            "(auth_kind = 'login' AND login_session_ref IS NOT NULL AND grant_id IS NULL) OR "
            "(auth_kind = 'grant' AND login_session_ref IS NULL AND grant_id IS NOT NULL "
            "AND plan_id IS NOT NULL AND goal_version IS NOT NULL)",
            name='ck_assistant_run_auth_source'),
        CheckConstraint("trigger_kind <> 'user' OR request_id IS NOT NULL",
                        name='ck_assistant_run_user_request'),
        CheckConstraint('(plan_id IS NULL AND goal_version IS NULL) OR '
                        '(plan_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version >= 1)',
                        name='ck_assistant_run_goal_version'),
        CheckConstraint('fence >= 0 AND attempt >= 0 AND display_revision >= 0 AND event_seq >= 0',
                        name='ck_assistant_run_counters'),
        CheckConstraint('version >= 1', name='ck_assistant_run_version'),
        CheckConstraint('length(request_digest) = 64', name='ck_assistant_run_request_digest'),
        CheckConstraint('login_session_ref IS NULL OR length(login_session_ref) = 64',
                        name='ck_assistant_run_login_ref'),
        Index('ix_assistant_run_queue', 'status', 'next_run_at'),
        Index('ix_assistant_run_lease_until', 'lease_until'),
        Index('ix_assistant_run_session', 'session_id'),
        Index('ix_assistant_run_plan', 'plan_id'),
        Index('ix_assistant_run_grant', 'grant_id'),
        Index('ix_assistant_run_owner_store', 'owner_id', 'store_id'),
    )


class RunItem(Base):
    """Execution attempt, accessible only through its authorized Run or Proposal."""

    __tablename__ = 'business_assistant_run_items'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_runs.id',
                               name='fk_assistant_run_item_run'), nullable=True)
    work_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_items.id',
                               name='fk_assistant_run_item_work'), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_proposals.id',
                               name='fk_assistant_run_item_proposal'), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    item_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    tool_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validated_arguments: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True)
    result_refs: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='pending', server_default='pending')
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submission_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True), nullable=True)
    submission_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow)

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        UniqueConstraint('run_id', 'item_key', 'attempt_no',
                         name='uq_assistant_run_item_attempt'),
        Index('uq_assistant_run_item_confirmation', 'proposal_id', unique=True,
              sqlite_where=(kind == 'confirmation'),
              postgresql_where=(kind == 'confirmation')),
        CheckConstraint("kind IN ('model','tool','batch_row','confirmation')",
                        name='ck_assistant_run_item_kind'),
        CheckConstraint("status IN ('pending','running','succeeded','failed','uncertain','skipped')",
                        name='ck_assistant_run_item_status'),
        CheckConstraint(
            "(kind = 'confirmation' AND proposal_id IS NOT NULL "
            "AND submission_snapshot IS NOT NULL AND submission_digest IS NOT NULL) OR "
            "(kind <> 'confirmation' AND run_id IS NOT NULL "
            "AND submission_snapshot IS NULL AND submission_digest IS NULL)",
            name='ck_assistant_run_item_confirmation'),
        CheckConstraint('attempt_no >= 1 AND version >= 1',
                        name='ck_assistant_run_item_versions'),
        CheckConstraint('submission_digest IS NULL OR length(submission_digest) = 64',
                        name='ck_assistant_run_item_digest'),
        Index('ix_assistant_run_item_work', 'work_item_id'),
        Index('ix_assistant_run_item_proposal', 'proposal_id'),
    )


class ContextSnapshot(StoreScoped, Base):
    """Append-only sourced context; no snapshot is created without a real message."""

    __tablename__ = 'business_assistant_context_snapshots'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id', name='fk_assistant_context_owner'), nullable=False)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id', name='fk_assistant_context_store'), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_sessions.id',
                               name='fk_assistant_context_session'), nullable=False)
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_context_plan'), nullable=True)
    goal_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    through_message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('business_assistant_messages.id',
                            name='fk_assistant_context_message'), nullable=False)
    goal: Mapped[str] = mapped_column(String(300), nullable=False)
    constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confirmed_selections: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    open_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unverified_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint('(plan_id IS NULL AND goal_version IS NULL) OR '
                        '(plan_id IS NOT NULL AND goal_version IS NOT NULL AND goal_version >= 1)',
                        name='ck_assistant_context_goal_version'),
        Index('ix_assistant_context_owner_store', 'owner_id', 'store_id'),
        Index('ix_assistant_context_session', 'session_id'),
        Index('ix_assistant_context_plan', 'plan_id'),
        Index('ix_assistant_context_message', 'through_message_id'),
    )


class RunEvent(Base):
    """Append-only minimal event; consumers authorize its parent Run first."""

    __tablename__ = 'business_assistant_run_events'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_runs.id',
                               name='fk_assistant_run_event_run'), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint('run_id', 'seq', name='uq_assistant_run_event_seq'),
        CheckConstraint('seq >= 1', name='ck_assistant_run_event_seq'),
        CheckConstraint(
            "type IN ('run.queued','run.started','run.progress','tool.finished',"
            "'proposal.prepared','plan.updated','run.completed','run.failed','run.cancelled')",
            name='ck_assistant_run_event_type'),
    )


class FollowupGrant(StoreScoped, Base):
    """A scoped employee authorization; defining this table never grants access."""

    __tablename__ = 'business_assistant_followup_grants'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_grant_plan'), nullable=False)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id', name='fk_assistant_grant_owner'), nullable=False)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id', name='fk_assistant_grant_store'), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('business_assistant_sessions.id',
                               name='fk_assistant_grant_session'), nullable=False)
    owner_role: Mapped[str] = mapped_column(String(20), nullable=False)
    access_version: Mapped[int] = mapped_column(Integer, nullable=False)
    goal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='active', server_default='active')
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        Index('uq_assistant_grant_active_plan', 'plan_id', unique=True,
              sqlite_where=(status == 'active'), postgresql_where=(status == 'active')),
        CheckConstraint("status IN ('active','paused','revoked')", name='ck_assistant_grant_status'),
        CheckConstraint('access_version >= 1 AND goal_version >= 1 AND version >= 1',
                        name='ck_assistant_grant_versions'),
        Index('ix_assistant_grant_owner_store', 'owner_id', 'store_id'),
        Index('ix_assistant_grant_session', 'session_id'),
        Index('ix_assistant_grant_plan', 'plan_id'),
    )


class WakeEvent(StoreScoped, Base):
    """Transactional signal outbox; no private conversation content is stored."""

    __tablename__ = 'business_assistant_wake_events'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    signal_key: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id', name='fk_assistant_wake_store'), nullable=False)
    object_ref: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_proposals.id',
                               name='fk_assistant_wake_proposal'), nullable=True)
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('flow_tasks.id', name='fk_assistant_wake_task'), nullable=True)
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_wake_plan'), nullable=True)
    source_ref: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default='pending', server_default='pending')
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default='0')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        UniqueConstraint('signal_key', name='uq_assistant_wake_signal'),
        CheckConstraint("state IN ('pending','dispatched')", name='ck_assistant_wake_state'),
        CheckConstraint('attempt >= 0 AND version >= 1', name='ck_assistant_wake_counters'),
        Index('ix_assistant_wake_dispatch', 'state', 'next_attempt_at'),
        Index('ix_assistant_wake_store', 'store_id'),
        Index('ix_assistant_wake_proposal', 'proposal_id'),
        Index('ix_assistant_wake_task', 'task_id'),
        Index('ix_assistant_wake_plan', 'plan_id'),
    )


class Notification(StoreScoped, Base):
    """Employee/store-scoped attention reference, separate from native tasks."""

    __tablename__ = 'business_assistant_notifications'

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id', name='fk_assistant_notification_owner'), nullable=False)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id', name='fk_assistant_notification_store'), nullable=False)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_sessions.id',
                               name='fk_assistant_notification_session'), nullable=True)
    plan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_work_plans.id',
                               name='fk_assistant_notification_plan'), nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey('business_assistant_proposals.id',
                               name='fk_assistant_notification_proposal'), nullable=True)
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('flow_tasks.id', name='fk_assistant_notification_task'), nullable=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_summary: Mapped[str] = mapped_column(String(600), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default='unread', server_default='unread')
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default='1')

    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        UniqueConstraint('owner_id', 'store_id', 'source_key', 'kind',
                         name='uq_assistant_notification_source'),
        CheckConstraint("status IN ('unread','read','resolved')",
                        name='ck_assistant_notification_status'),
        CheckConstraint('version >= 1', name='ck_assistant_notification_version'),
        Index('ix_assistant_notification_owner_status', 'owner_id', 'store_id', 'status'),
        Index('ix_assistant_notification_session', 'session_id'),
        Index('ix_assistant_notification_plan', 'plan_id'),
        Index('ix_assistant_notification_proposal', 'proposal_id'),
        Index('ix_assistant_notification_task', 'task_id'),
    )


@event.listens_for(ContextSnapshot, 'before_update')
@event.listens_for(ContextSnapshot, 'before_delete')
@event.listens_for(RunEvent, 'before_update')
@event.listens_for(RunEvent, 'before_delete')
def _reject_append_only_change(mapper, connection, target):
    """ORM protection; authorized services still control reads and all inserts."""
    raise ValueError('Runtime context snapshots and events are append-only')
