"""Store-owned, append-only boutique bundle definitions and sale allocations."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped


class RetailBundleRule(StoreScoped, Base):
    __tablename__ = 'retail_bundle_rules'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sale_starts_on: Mapped[date] = mapped_column(Date)
    sale_ends_on: Mapped[date] = mapped_column(Date)
    price_cents_per_set: Mapped[int] = mapped_column(BigInteger)
    refund_terms: Mapped[str] = mapped_column(String(1500))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('store_id', 'code', 'rule_version', name='uq_retail_bundle_rule'),
        CheckConstraint('rule_version>0 AND price_cents_per_set>0 AND sale_starts_on<=sale_ends_on', name='ck_retail_bundle_rule'),
    )


class RetailBundleComponent(StoreScoped, Base):
    __tablename__ = 'retail_bundle_components'
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey('retail_bundle_rules.id'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(ForeignKey('flow_items.id'))
    sku: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20))
    quantity_milli_per_set: Mapped[int] = mapped_column(BigInteger)
    goods_reference_cents: Mapped[int] = mapped_column(BigInteger)
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey('master_work_items.id'), nullable=True)
    work_code: Mapped[str] = mapped_column(String(60), default='')
    work_name: Mapped[str] = mapped_column(String(120), default='')
    installation_reference_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    goods_cents_per_set: Mapped[int] = mapped_column(BigInteger)
    installation_cents_per_set: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint('rule_id', 'sequence', name='uq_retail_bundle_sequence'),
        UniqueConstraint('rule_id', 'item_id', name='uq_retail_bundle_item'),
        CheckConstraint('sequence>0 AND quantity_milli_per_set>0 AND goods_reference_cents>=0 AND installation_reference_cents>=0 AND goods_cents_per_set>=0 AND installation_cents_per_set>=0', name='ck_retail_bundle_component'),
    )


class RetailBundleSale(StoreScoped, Base):
    __tablename__ = 'retail_bundle_sales'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('retail_orders.id'), unique=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey('retail_bundle_rules.id'), index=True)
    sets: Mapped[int] = mapped_column(Integer)
    terms_accepted: Mapped[bool] = mapped_column(Boolean)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('sets>0 AND terms_accepted', name='ck_retail_bundle_sale'),)


class RetailBundleAllocation(StoreScoped, Base):
    __tablename__ = 'retail_bundle_allocations'
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey('retail_bundle_sales.id'), index=True)
    component_id: Mapped[int] = mapped_column(ForeignKey('retail_bundle_components.id'))
    line_id: Mapped[int] = mapped_column(ForeignKey('retail_lines.id'), unique=True)
    quantity_milli: Mapped[int] = mapped_column(BigInteger)
    goods_reference_cents: Mapped[int] = mapped_column(BigInteger)
    installation_reference_cents: Mapped[int] = mapped_column(BigInteger)
    goods_cents: Mapped[int] = mapped_column(BigInteger)
    installation_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint('sale_id', 'component_id', name='uq_retail_bundle_allocation'),
        CheckConstraint('quantity_milli>0 AND goods_reference_cents>=goods_cents AND goods_cents>=0 AND installation_reference_cents>=installation_cents AND installation_cents>=0', name='ck_retail_bundle_allocation'),
    )


class RetailBundleReceipt(StoreScoped, Base):
    __tablename__ = 'retail_bundle_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    rule_id: Mapped[int] = mapped_column(ForeignKey('retail_bundle_rules.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id', 'request_id', name='uq_retail_bundle_receipt'),)


IMMUTABLE = (RetailBundleRule, RetailBundleComponent, RetailBundleSale, RetailBundleAllocation, RetailBundleReceipt)

@event.listens_for(Session, 'before_flush')
def immutable_bundles(db, *_):
    if any(isinstance(row, IMMUTABLE) for row in list(db.dirty) + list(db.deleted)):
        raise HTTPException(409, '精品套餐规则、原单组成和金额分摊不可覆盖；配置变更请发布新版本，原单按冻结规则退货')
