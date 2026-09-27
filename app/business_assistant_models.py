"""Private, owner/store-scoped conversations and immutable operation proposals."""
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint, CheckConstraint, false
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow
from .models import StoreScoped


class AssistantSession(StoreScoped, Base):
    __tablename__ = 'business_assistant_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    owner_role: Mapped[str] = mapped_column(String(20))
    access_version: Mapped[int] = mapped_column(Integer)
    recent_operation_ids: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    busy_token: Mapped[str | None] = mapped_column(String(80), nullable=True)
    busy_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {'version_id_col': version}


class AssistantMessage(StoreScoped, Base):
    __tablename__ = 'business_assistant_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('business_assistant_sessions.id'), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    thinking: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('session_id', 'request_id', name='uq_assistant_message_request'),
                     CheckConstraint("role IN ('user','assistant')", name='ck_assistant_message_role'))


class AssistantProposal(StoreScoped, Base):
    __tablename__ = 'business_assistant_proposals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('business_assistant_sessions.id'), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    owner_role: Mapped[str] = mapped_column(String(20))
    access_version: Mapped[int] = mapped_column(Integer)
    operation_id: Mapped[str] = mapped_column(String(180))
    label: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(600))
    # 这一轮对话的消息编号：同一轮准备出来的几十张卡据此在页面上折叠成一组可翻页
    # （业主 2026-09-25 试用反馈：卡片一张一张铺开、看不出属于同一轮、也没法翻页）。
    request_id: Mapped[str] = mapped_column(String(100), default='')
    # 这一张卡属于员工目标里的第几步：本轮事实已齐备的步骤可一起准备，页面按步骤分组展示、
    # 逐步确认；依赖尚未产生编号/版本的后续卡必须等真实前序完成。
    step_order: Mapped[int] = mapped_column(Integer, default=0)
    step_label: Mapped[str] = mapped_column(String(120), default='')
    # 这张卡需要员工先回答的必填项（分派给谁、选哪台车、日期、金额…）。员工在卡片上填，
    # 没有填完不能确认（业主 2026-09-25）。
    questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    idempotent: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (CheckConstraint("status IN ('pending','executing','succeeded','failed','uncertain','cancelled','expired')", name='ck_assistant_proposal_status'),)


class AssistantIssue(StoreScoped, Base):
    __tablename__ = 'business_assistant_issues'
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('business_assistant_sessions.id'), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    category: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(String(1200))
    operation_id: Mapped[str] = mapped_column(String(180), default='')
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("category IN ('input','rule','system','model','unsupported')", name='ck_assistant_issue_category'),)


class AssistantWorkPlan(StoreScoped, Base):
    """An employee goal and its references, never a replacement business state machine."""
    __tablename__ = 'business_assistant_work_plans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('business_assistant_sessions.id'), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    goal: Mapped[str] = mapped_column(String(300))
    steps: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (UniqueConstraint('session_id','request_id',name='uq_assistant_work_plan_turn'),)
