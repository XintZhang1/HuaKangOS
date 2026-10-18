"""Append-only redemption facts; approved contract entitlements remain unchanged."""
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, CheckConstraint, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow
from .models import StoreScoped


class RecordBenefitRedemption(StoreScoped, Base):
    __tablename__ = 'business_record_benefit_redemptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('business_record_contracts.id'), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[int] = mapped_column(Integer)
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_benefit_redemptions.id'), nullable=True)
    redeemed_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(Text, default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('reverses_id', name='uq_record_benefit_reversal'),
        CheckConstraint('(quantity = 1 AND reverses_id IS NULL) OR (quantity = -1 AND reverses_id IS NOT NULL)', name='ck_record_benefit_event'),
    )


@event.listens_for(RecordBenefitRedemption, 'before_update')
@event.listens_for(RecordBenefitRedemption, 'before_delete')
def preserve_redemption(mapper, connection, target):
    raise ValueError('兑换记录须保留；误录请追加撤销记录')
