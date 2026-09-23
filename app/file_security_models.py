"""Separate mutable scan status and immutable scan evidence; file bytes stay frozen."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned

STATES = ('quarantined', 'clean', 'structure_only', 'infected', 'error', 'rejected')


class FileScanEvent(StoreScoped, Base):
    __tablename__ = 'file_scan_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(20))
    request_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(20))
    engine: Mapped[str] = mapped_column(String(30))
    engine_version: Mapped[str] = mapped_column(String(200), default='')
    code: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('store_id', 'request_key', name='uq_file_scan_request'),
        CheckConstraint("state IN ('quarantined','clean','structure_only','infected','error','rejected')", name='ck_file_scan_state'),
        CheckConstraint("action IN ('initial','rescan') AND size >= 0", name='ck_file_scan_action'),
    )


class FileSecurity(Versioned, Base):
    __tablename__ = 'file_security'
    file_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'), unique=True)
    state: Mapped[str] = mapped_column(String(20), default='quarantined')
    last_scan_id: Mapped[int | None] = mapped_column(ForeignKey('file_scan_events.id'), nullable=True)
    __table_args__ = (CheckConstraint("state IN ('quarantined','clean','structure_only','infected','error','rejected')",
                                       name='ck_file_security_state'),)


@event.listens_for(Session, 'before_flush')
def protect_file_scan_history(db, *_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row, FileScanEvent):
            raise HTTPException(409, '扫描记录不可覆盖；请新增重扫记录')
        if isinstance(row, FileSecurity) and (row in db.deleted or inspect(row).attrs.file_id.history.has_changes()):
            raise HTTPException(409, '附件扫描关联不可覆盖或删除')
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row, (FileSecurity, FileScanEvent)) and not db.info.get('_file_scan_authority'):
            raise HTTPException(403, '附件扫描状态只能由扫描服务写入')
