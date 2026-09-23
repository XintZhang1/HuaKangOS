"""Frozen principal-plus-gift recharge bundles; cash remains in GroupEntry only."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .group_models import GroupProtected


class RechargeBundleRule(GroupProtected, Base):
    __tablename__ = 'recharge_bundle_rules'
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    code: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    principal_cents_per_share: Mapped[int] = mapped_column(BigInteger)
    allowed_store_ids: Mapped[list] = mapped_column(JSON)
    sale_starts_on: Mapped[date] = mapped_column(Date)
    sale_ends_on: Mapped[date] = mapped_column(Date)
    refund_policy: Mapped[str] = mapped_column(String(40))
    refund_terms: Mapped[str] = mapped_column(String(1000))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('issuer_store_id', 'code', 'rule_version', name='uq_recharge_bundle_rule'),
        CheckConstraint('rule_version>0 AND principal_cents_per_share>0 AND sale_starts_on<=sale_ends_on', name='ck_recharge_bundle_rule_value'),
        CheckConstraint("refund_policy IN ('whole_unused_before_expiry','whole_unused_anytime')", name='ck_recharge_bundle_refund_policy'),
    )


class RechargeBundleRuleComponent(GroupProtected, Base):
    __tablename__ = 'recharge_bundle_rule_components'
    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_rule_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_rules.id'), index=True)
    benefit_rule_id: Mapped[int] = mapped_column(ForeignKey('benefit_rules.id'))
    units_per_share: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint('bundle_rule_id', 'benefit_rule_id', name='uq_recharge_bundle_rule_component'),
                     CheckConstraint('units_per_share>0', name='ck_recharge_bundle_component_units'))


class RechargeBundleOrder(Versioned, Base):
    __tablename__ = 'recharge_bundle_orders'
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    values: Mapped[dict] = mapped_column(JSON)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    __table_args__ = (CheckConstraint("purpose IN ('purchase','refund') AND status IN ('draft','approved','completed','cancelled')", name='ck_recharge_bundle_order'),)


class RechargeBundlePurchase(StoreScoped, Base):
    __tablename__ = 'recharge_bundle_purchases'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_rules.id'))
    shares: Mapped[int] = mapped_column(Integer)
    principal_entry_id: Mapped[int] = mapped_column(ForeignKey('group_entries.id'), unique=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('shares>0', name='ck_recharge_bundle_purchase_shares'),)


class RechargeBundleComponent(GroupProtected, Base):
    __tablename__ = 'recharge_bundle_components'
    id: Mapped[int] = mapped_column(primary_key=True)
    # Minimal central funding origin: needed to reject a standalone adjustment
    # in another authorized store without exposing that store's business files.
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_purchases.id'), index=True)
    rule_component_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_rule_components.id'))
    wallet_id: Mapped[int] = mapped_column(ForeignKey('benefit_wallets.id'), unique=True)
    grant_entry_id: Mapped[int] = mapped_column(ForeignKey('benefit_entries.id'), unique=True)
    __table_args__ = (UniqueConstraint('purchase_id', 'rule_component_id', name='uq_recharge_bundle_purchase_component'),)


class RechargeBundleRefund(Versioned, Base):
    __tablename__ = 'recharge_bundle_refunds'
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_purchases.id'), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    shares: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='requested')
    executed_entry_id: Mapped[int | None] = mapped_column(ForeignKey('group_entries.id'), unique=True, nullable=True)
    __table_args__ = (
        CheckConstraint("shares>0 AND amount_cents>0 AND status IN ('requested','reserved','applied','released')", name='ck_recharge_bundle_refund'),
        CheckConstraint("(status='applied' AND executed_entry_id IS NOT NULL) OR (status!='applied' AND executed_entry_id IS NULL)", name='ck_recharge_bundle_refund_post'),
    )


class RechargeBundleRefundComponent(StoreScoped, Base):
    __tablename__ = 'recharge_bundle_refund_components'
    id: Mapped[int] = mapped_column(primary_key=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_refunds.id'), index=True)
    component_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_components.id'))
    units: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint('refund_id', 'component_id', name='uq_recharge_bundle_refund_component'),
                     CheckConstraint('units>0', name='ck_recharge_bundle_refund_units'))


class RechargeBundleRefundPosting(StoreScoped, Base):
    __tablename__ = 'recharge_bundle_refund_postings'
    id: Mapped[int] = mapped_column(primary_key=True)
    refund_component_id: Mapped[int] = mapped_column(ForeignKey('recharge_bundle_refund_components.id'), unique=True)
    benefit_entry_id: Mapped[int] = mapped_column(ForeignKey('benefit_entries.id'), unique=True)


IMMUTABLE = (RechargeBundleRule, RechargeBundleRuleComponent, RechargeBundlePurchase,
             RechargeBundleComponent, RechargeBundleRefundComponent, RechargeBundleRefundPosting)
ALL = (*IMMUTABLE, RechargeBundleOrder, RechargeBundleRefund)


@event.listens_for(Session, 'before_flush')
def guard_recharge_bundles(db, *_):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, IMMUTABLE):
            raise HTTPException(409, '充值组合规则与分账凭据不可覆盖，请追加新版本或原组合退款')
        frozen = ('case_id', 'member_id', 'purpose', 'values', 'requested_by') if isinstance(row, RechargeBundleOrder) else (
            ('case_id', 'purchase_id', 'member_id', 'shares', 'amount_cents') if isinstance(row, RechargeBundleRefund) else ())
        if frozen and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen)):
            raise HTTPException(409, '组合申请的来源、金额及份数不可覆盖，请撤销后重新申请')
    if any(isinstance(row, ALL) for row in list(db.new) + list(db.dirty) + list(db.deleted)) and not db.info.get('_group_authority'):
        raise HTTPException(403, '充值组合必须通过集团会员业务服务办理')
    for row in db.new:
        if isinstance(row, RechargeBundleComponent) and row.store_id != db.info.get('write_store'):
            raise HTTPException(403, '组合赠品来源只能由当前发行门店追加')
