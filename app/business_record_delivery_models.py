"""Delivery evidence, approved returns and independent refund facts."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Text, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, LargeBinary, CheckConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .business_records_models import Versioned


class RecordGiftDocument(StoreScoped, Base):
    __tablename__ = 'business_record_gift_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), index=True)
    filename: Mapped[str] = mapped_column(String(180))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, default=b'')
    object_key: Mapped[str] = mapped_column(String(200), default='')
    scan_state: Mapped[str] = mapped_column(String(30))
    scan_code: Mapped[str] = mapped_column(String(50))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecordDelivery(StoreScoped, Base):
    __tablename__ = 'business_record_deliveries'
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey('business_record_invoices.id'))
    invoice_file_id: Mapped[int] = mapped_column(ForeignKey('business_record_invoice_files.id'))
    gift_document_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_gift_documents.id'), nullable=True)
    accounting_on: Mapped[date] = mapped_column(Date, index=True)
    invoice_amount_cents: Mapped[int] = mapped_column(BigInteger)
    confirmed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    cc_role: Mapped[str] = mapped_column(String(40), default='general_manager')
    note: Mapped[str] = mapped_column(Text, default='')


class RecordReturn(Versioned, Base):
    __tablename__ = 'business_record_returns'
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey('business_record_deliveries.id'))
    status: Mapped[str] = mapped_column(String(20), default='submitted')
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    requested_refund_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    review_note: Mapped[str] = mapped_column(Text, default='')
    reversal_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('submitted','approved','rejected')", name='ck_record_return_status'),)


class RecordRefund(StoreScoped, Base):
    __tablename__ = 'business_record_refunds'
    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey('business_record_returns.id'), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    refunded_on: Mapped[date] = mapped_column(Date)
    confirmed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (CheckConstraint('amount_cents > 0', name='ck_record_refund_positive'),)


@event.listens_for(Session, 'before_flush')
def preserve_delivery_facts(db, *_):
    for row in set(db.dirty) | set(db.deleted):
        if isinstance(row, (RecordDelivery, RecordRefund, RecordGiftDocument)) and (row in db.deleted or db.is_modified(row)):
            raise HTTPException(409, '已保存交车、退款和赠品单原件不得覆盖删除')
