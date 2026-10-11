"""One current invoice per contract; every uploaded original remains archived."""
from datetime import datetime
from sqlalchemy import String, Text, Integer, BigInteger, DateTime, ForeignKey, JSON, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow
from .models import StoreScoped
from .business_records_models import Versioned


class RecordInvoice(Versioned, Base):
    __tablename__ = 'business_record_invoices'
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), unique=True)
    active_file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Business upload event, independent of deduplicated original object age.
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default='')


class RecordInvoiceFile(StoreScoped, Base):
    __tablename__ = 'business_record_invoice_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey('business_record_invoices.id'), index=True)
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
    __table_args__ = (UniqueConstraint('invoice_id', 'sha256', name='uq_record_invoice_file_hash'),)
