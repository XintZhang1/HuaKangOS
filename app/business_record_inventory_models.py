"""Published inventory snapshots are independent of legacy procurement ledgers."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, LargeBinary, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .business_records_models import Versioned


class RecordInventoryFile(StoreScoped, Base):
    __tablename__ = 'business_record_inventory_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(180))
    brand: Mapped[str] = mapped_column(String(100))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, default=b'')
    object_key: Mapped[str] = mapped_column(String(200), default='')
    scan_state: Mapped[str] = mapped_column(String(30))
    scan_code: Mapped[str] = mapped_column(String(50))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecordInventoryBatch(StoreScoped, Base):
    __tablename__ = 'business_record_inventory_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey('business_record_inventory_files.id'))
    brand: Mapped[str] = mapped_column(String(100))
    sheet: Mapped[str] = mapped_column(String(100))
    as_of_date: Mapped[date] = mapped_column(Date)
    mapping: Mapped[dict] = mapped_column(JSON)
    row_count: Mapped[int] = mapped_column(Integer)
    excluded_count: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecordInventoryRow(StoreScoped, Base):
    __tablename__ = 'business_record_inventory_rows'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('business_record_inventory_batches.id'), index=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    source_row: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(160))
    configuration: Mapped[str] = mapped_column(String(300))
    exterior_color: Mapped[str] = mapped_column(String(100), default='')
    interior_color: Mapped[str] = mapped_column(String(100), default='')
    extra_configuration: Mapped[str] = mapped_column(String(500), default='')
    guide_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    production_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    funding_kind: Mapped[str] = mapped_column(String(20), default='unknown')
    funding_source: Mapped[str] = mapped_column(String(160), default='')
    source_owner: Mapped[str] = mapped_column(String(160), default='')
    location: Mapped[str] = mapped_column(String(160), default='')
    price_reference: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint('batch_id', 'vin', name='uq_record_inventory_batch_vin'),)


class RecordInventoryCurrent(Versioned, Base):
    __tablename__ = 'business_record_inventory_current'
    brand: Mapped[str] = mapped_column(String(100))
    batch_id: Mapped[int] = mapped_column(ForeignKey('business_record_inventory_batches.id'))
    __table_args__ = (UniqueConstraint('store_id', 'brand', name='uq_record_inventory_current_store_brand'),)


class RecordInventoryClaim(StoreScoped, Base):
    """A contract/VIN history is retained even after a later vehicle correction."""
    __tablename__ = 'business_record_inventory_claims'
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), index=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    inventory_row_id: Mapped[int] = mapped_column(ForeignKey('business_record_inventory_rows.id'))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id', 'contract_id', 'vin', name='uq_record_inventory_contract_vin'),)


@event.listens_for(Session, 'before_flush')
def immutable_inventory_evidence(db, *_):
    for row in set(db.dirty) | set(db.deleted):
        if isinstance(row, (RecordInventoryBatch, RecordInventoryRow, RecordInventoryClaim)):
            if row in db.deleted or db.is_modified(row):
                raise HTTPException(409, '已发布库存及合同车辆依据保留历史，不可覆盖或删除')
