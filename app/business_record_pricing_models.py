"""Versioned store price publications and immutable contract submission evidence."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String, Text, Integer, BigInteger, DateTime, ForeignKey, JSON, LargeBinary, UniqueConstraint, CheckConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .business_records_models import Versioned


class RecordPricingSettings(Versioned, Base):
    __tablename__ = 'business_record_pricing_settings'
    vehicle_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gift_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('store_id', name='uq_record_pricing_store'),)


class RecordPricingFile(StoreScoped, Base):
    __tablename__ = 'business_record_pricing_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(30))
    contract_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_contracts.id'), nullable=True, index=True)
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
    __table_args__ = (CheckConstraint("kind IN ('vehicle','gift','contract_attachment')", name='ck_record_pricing_file_kind'),)


class RecordPriceBatch(StoreScoped, Base):
    __tablename__ = 'business_record_price_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    file_id: Mapped[int] = mapped_column(ForeignKey('business_record_pricing_files.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    row_count: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        CheckConstraint("kind IN ('vehicle','gift')", name='ck_record_price_batch_kind'),
        CheckConstraint('row_count > 0', name='ck_record_price_batch_count'),)


class RecordVehicleVariant(Versioned, Base):
    __tablename__ = 'business_record_vehicle_variants'
    family: Mapped[str] = mapped_column(String(100))
    series: Mapped[str] = mapped_column(String(160))
    model: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint('store_id', 'family', 'series', 'model', name='uq_record_vehicle_variant'),)


class RecordVehiclePrice(StoreScoped, Base):
    __tablename__ = 'business_record_vehicle_prices'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('business_record_price_batches.id'), index=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey('business_record_vehicle_variants.id'))
    family: Mapped[str] = mapped_column(String(100))
    series: Mapped[str] = mapped_column(String(160))
    model: Mapped[str] = mapped_column(String(160))
    guide_price_cents: Mapped[int] = mapped_column(BigInteger)
    control_price_cents: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (UniqueConstraint('batch_id', 'variant_id', name='uq_record_batch_variant'),
        CheckConstraint('guide_price_cents > 0 AND control_price_cents > 0', name='ck_record_vehicle_prices_positive'))


class RecordGiftPrice(StoreScoped, Base):
    __tablename__ = 'business_record_gift_prices'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('business_record_price_batches.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (UniqueConstraint('batch_id', 'name', name='uq_record_batch_gift'),
        CheckConstraint('unit_price_cents >= 0', name='ck_record_gift_price_nonnegative'))


class RecordContractTerms(Versioned, Base):
    __tablename__ = 'business_record_contract_terms'
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), unique=True)
    price_snapshot: Mapped[dict] = mapped_column(JSON)
    gift_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gifts_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    gift_total_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    submission_data: Mapped[dict] = mapped_column(JSON, default=dict)
    price_below_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    gift_excess_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    special: Mapped[bool] = mapped_column(default=False)
    special_note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (CheckConstraint('gift_total_cents >= 0 AND price_below_cents >= 0 AND gift_excess_cents >= 0', name='ck_record_terms_nonnegative'),)


@event.listens_for(Session, 'before_flush')
def immutable_price_publications(db, *_):
    """New publications replace only pointers; submitted price versions never move."""
    for row in set(db.dirty) | set(db.deleted):
        if isinstance(row, (RecordPriceBatch, RecordVehiclePrice, RecordGiftPrice)):
            if row in db.deleted or db.is_modified(row):
                raise HTTPException(409, '已发布价格批次保留追溯，不可改写或删除')
        if isinstance(row, RecordContractTerms):
            if row in db.deleted or any(inspect(row).attrs[key].history.has_changes()
                    for key in ('contract_id', 'store_id', 'price_snapshot', 'gift_batch_id')):
                raise HTTPException(409, '合同提交时的价格版本已冻结，不可改写或删除')
