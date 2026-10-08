"""Independent V2 records: no inventory, ERP, membership or legacy flow writes."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Text, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, Session
from .db import Base, utcnow
from .models import StoreScoped


class Versioned(StoreScoped):
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @declared_attr.directive
    def __mapper_args__(cls):
        return {'version_id_col': cls.version}


class RecordCustomer(Versioned, Base):
    __tablename__ = 'business_record_customers'
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(40), default='')
    note: Mapped[str] = mapped_column(Text, default='')


class SalesContract(Versioned, Base):
    __tablename__ = 'business_record_contracts'
    number: Mapped[str] = mapped_column(String(60), unique=True)
    salesperson_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_customers.id'), nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_phone: Mapped[str] = mapped_column(String(40), default='')
    brand: Mapped[str] = mapped_column(String(100), index=True)
    model: Mapped[str] = mapped_column(String(160))
    vin: Mapped[str] = mapped_column(String(40))
    contract_date: Mapped[date] = mapped_column(Date, index=True)
    sale_price_cents: Mapped[int] = mapped_column(BigInteger)
    form_data: Mapped[dict] = mapped_column(JSON, default=dict)
    gift_description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='submitted', index=True)
    expected_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    profit_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gift_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    price_note: Mapped[str] = mapped_column(Text, default='')
    priced_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    priced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_note: Mapped[str] = mapped_column(Text, default='')
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    template_version: Mapped[str] = mapped_column(String(100), default='')
    __table_args__ = (
        CheckConstraint("status IN ('submitted','priced','approved','rejected')", name='ck_record_contract_status'),
        CheckConstraint('sale_price_cents > 0', name='ck_record_contract_price'),
        CheckConstraint('expected_amount_cents IS NULL OR expected_amount_cents >= 0', name='ck_record_contract_expected'),
        CheckConstraint('cost_cents IS NULL OR cost_cents >= 0', name='ck_record_contract_cost'),
        CheckConstraint('gift_cost_cents IS NULL OR gift_cost_cents >= 0', name='ck_record_contract_gift'),
        CheckConstraint("status NOT IN ('priced','approved') OR (expected_amount_cents IS NOT NULL AND cost_cents IS NOT NULL AND profit_cents IS NOT NULL AND gift_cost_cents IS NOT NULL AND priced_by IS NOT NULL)", name='ck_record_contract_priced'),
        CheckConstraint("status != 'approved' OR (approved_by IS NOT NULL AND approved_snapshot IS NOT NULL)", name='ck_record_contract_approved'),
    )


class ContractReceipt(StoreScoped, Base):
    __tablename__ = 'business_record_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), unique=True)
    actual_amount_cents: Mapped[int] = mapped_column(BigInteger)
    received_on: Mapped[date] = mapped_column(Date, index=True)
    confirmed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('actual_amount_cents > 0', name='ck_record_receipt_amount'),)


class AfterSalesRecord(Versioned, Base):
    __tablename__ = 'business_record_after_sales'
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_customers.id'), nullable=True, index=True)
    number: Mapped[str] = mapped_column(String(60), unique=True)
    service_type: Mapped[str] = mapped_column(String(30), index=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_phone: Mapped[str] = mapped_column(String(40), default='')
    vehicle: Mapped[str] = mapped_column(String(160))
    brand: Mapped[str] = mapped_column(String(100), default='', index=True)
    service_items: Mapped[str] = mapped_column(Text)
    materials_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    labor_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    handler_name: Mapped[str] = mapped_column(String(100))
    business_date: Mapped[date] = mapped_column(Date, index=True)
    __table_args__ = (
        CheckConstraint("service_type IN ('repair','maintenance','accident','renewal','extended_warranty','accessories')", name='ck_record_service_type'),
        CheckConstraint('materials_cents >= 0 AND labor_cents >= 0 AND (cost_cents IS NULL OR cost_cents >= 0)', name='ck_record_service_money'),
    )


class ManualReportRecord(Versioned, Base):
    __tablename__ = 'business_record_manual_reports'
    report_key: Mapped[str] = mapped_column(String(80), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    brand: Mapped[str] = mapped_column(String(100), default='')
    salesperson_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    values: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))


class RecordSettings(Versioned, Base):
    __tablename__ = 'business_record_settings'
    approval_mode: Mapped[str] = mapped_column(String(15), default='all')
    threshold_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    threshold_basis_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        UniqueConstraint('store_id', name='uq_record_settings_store'),
        CheckConstraint("approval_mode IN ('all','fixed','ratio')", name='ck_record_settings_mode'),
        CheckConstraint('threshold_amount_cents IS NULL OR threshold_amount_cents >= 0', name='ck_record_settings_amount'),
        CheckConstraint('threshold_basis_points IS NULL OR (threshold_basis_points >= 0 AND threshold_basis_points <= 10000)', name='ck_record_settings_ratio'),
    )


class RecordCommand(StoreScoped, Base):
    __tablename__ = 'business_record_commands'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    request_id: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id', 'actor_id', 'request_id', name='uq_record_command'),)


@event.listens_for(Session, 'before_flush')
def immutable_record_facts(db, *_):
    for row in set(db.dirty) | set(db.deleted):
        if isinstance(row, (ContractReceipt, RecordCommand)) and (row in db.deleted or db.is_modified(row)):
            raise HTTPException(409, '已确认的到账记录及操作回执不可改写或删除')
