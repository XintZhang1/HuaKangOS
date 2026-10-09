"""Append-only daily reports explicitly confirmed by a store clerk."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column
from .db import Base, utcnow
from .models import StoreScoped


class RecordDailyReport(StoreScoped, Base):
    __tablename__ = 'business_record_daily_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    report_key: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer)
    confirmed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str] = mapped_column(Text, default='')
    source_digest: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('store_id', 'day', 'report_key', 'version', name='uq_record_daily_report_version'),)


@event.listens_for(Session, 'before_flush')
def immutable_daily_reports(db, *_):
    for row in set(db.dirty) | set(db.deleted):
        if isinstance(row, RecordDailyReport) and (row in db.deleted or db.is_modified(row)):
            raise HTTPException(409, '内勤已确认日报不可改写或删除，请预览后追加更正版本')
