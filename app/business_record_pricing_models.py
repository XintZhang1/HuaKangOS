"""Versioned store price publications and immutable contract submission evidence."""
from datetime import datetime
from sqlalchemy import String, Text, Integer, BigInteger, DateTime, ForeignKey, JSON, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
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


class RecordPriceBatch(StoreScoped, Base):
    __tablename__ = 'business_record_price_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    file_id: Mapped[int] = mapped_column(ForeignKey('business_record_pricing_files.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    row_count: Mapped[int] = mapped_column(Integer)


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
    __table_args__ = (UniqueConstraint('batch_id', 'variant_id', name='uq_record_batch_variant'),)


class RecordGiftPrice(StoreScoped, Base):
    __tablename__ = 'business_record_gift_prices'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('business_record_price_batches.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(Text, default='')
    __table_args__ = (UniqueConstraint('batch_id', 'name', name='uq_record_batch_gift'),)


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
    general_approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    general_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    general_approval_note: Mapped[str] = mapped_column(Text, default='')
