"""Append-only order v3 quote, approval, customer consent and adjustment facts."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Date, DateTime, JSON, ForeignKey, CheckConstraint, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped


class SalesQuote(StoreScoped, Base):
    __tablename__ = 'sales_quotes'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    prior_id: Mapped[int | None] = mapped_column(ForeignKey('sales_quotes.id'), nullable=True)
    model_id: Mapped[int] = mapped_column(ForeignKey('master_vehicle_models.id'))
    model_snapshot: Mapped[dict] = mapped_column(JSON)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    delivery_due: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    services: Mapped[dict] = mapped_column(JSON)
    terms: Mapped[str] = mapped_column(String(1500))
    reason: Mapped[str] = mapped_column(String(500))
    digest: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('case_id', 'revision', name='uq_sales_quote_revision'),
                     CheckConstraint('revision>0 AND amount_cents>0', name='ck_sales_quote_amount'))


class SalesQuoteReview(StoreScoped, Base):
    __tablename__ = 'sales_quote_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey('sales_quotes.id'), unique=True)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("decision IN ('approved','rejected')", name='ck_sales_quote_review'),)


class SalesQuoteResolution(StoreScoped, Base):
    __tablename__ = 'sales_quote_resolutions'
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey('sales_quotes.id'), unique=True)
    outcome: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("outcome IN ('activated','withdrawn','rejected')", name='ck_sales_quote_resolution'),)


class SalesQuoteConsent(StoreScoped, Base):
    __tablename__ = 'sales_quote_consents'
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey('sales_quotes.id'), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'), unique=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    fingerprint: Mapped[str] = mapped_column(String(64))
    paid_before_cents: Mapped[int] = mapped_column(BigInteger)
    advance_before_cents: Mapped[int] = mapped_column(BigInteger)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('paid_before_cents>=0 AND advance_before_cents>=0 AND advance_before_cents<=paid_before_cents', name='ck_sales_quote_consent_paid'),)


class SalesVehicleRelease(StoreScoped, Base):
    __tablename__ = 'sales_vehicle_releases'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey('sales_quotes.id'))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SalesQuoteAdjustment(StoreScoped, Base):
    __tablename__ = 'sales_quote_adjustments'
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey('sales_quotes.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey('flow_payment_links.id'), nullable=True, unique=True)
    credit_id: Mapped[int | None] = mapped_column(ForeignKey('business_finance_credit_links.id'), nullable=True, unique=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("amount_cents>0 AND ((kind='cash_refund' AND payment_id IS NOT NULL AND credit_id IS NULL) OR (kind='advance_return' AND payment_id IS NULL AND credit_id IS NOT NULL))", name='ck_sales_quote_adjustment'),)


IMMUTABLE = (SalesQuote, SalesQuoteReview, SalesQuoteResolution, SalesQuoteConsent, SalesVehicleRelease, SalesQuoteAdjustment)

@event.listens_for(Session, 'before_flush')
def immutable_sales_quotes(db, *_):
    if any(isinstance(row, IMMUTABLE) for row in list(db.dirty) + list(db.deleted)):
        raise HTTPException(409, '报价、审批、签回及原款调整凭据不可覆盖；请新增报价版本或追加原单调整')
