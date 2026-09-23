"""Immutable receipts for global account configuration, containing no credentials."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, UniqueConstraint, CheckConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow


class UserAccessReceipt(Base):
    __tablename__ = 'user_access_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    request_key: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str] = mapped_column(String(64))
    request_data: Mapped[dict] = mapped_column(JSON)
    previous_version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON)
    audit_id: Mapped[int] = mapped_column(ForeignKey('audit_logs.id'), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('actor_id', 'request_key', name='uq_user_access_request'),
                     UniqueConstraint('target_id', 'previous_version', name='uq_user_access_target_version'),
                     CheckConstraint('previous_version >= 1', name='ck_user_access_previous'))


@event.listens_for(Session, 'before_flush')
def immutable_access_receipts(db, *_):
    if any(isinstance(row, UserAccessReceipt) and (row in db.deleted or db.is_modified(row))
           for row in set(db.dirty) | set(db.deleted)):
        raise HTTPException(409, '账号修改回执不可改写或删除，请按最新版本重新办理')
