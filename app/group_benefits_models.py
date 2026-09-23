"""Frozen fixed-unit group benefits, separate from principal stored value."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .group_models import GroupProtected, CentralVersioned


class BenefitRule(GroupProtected, Base):
    __tablename__ = 'benefit_rules'
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    code: Mapped[str] = mapped_column(String(40))
    rule_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    allowed_store_ids: Mapped[list] = mapped_column(JSON)
    credit_cents_per_unit: Mapped[int] = mapped_column(BigInteger)
    settlement_cents_per_unit: Mapped[int] = mapped_column(BigInteger)
    sale_cents_per_unit: Mapped[int] = mapped_column(BigInteger)
    exchange_points_per_unit: Mapped[int] = mapped_column(BigInteger, default=0)
    refund_policy: Mapped[str] = mapped_column(String(30))
    discount_bearer: Mapped[str] = mapped_column(String(20))
    validity_days: Mapped[int] = mapped_column(Integer)
    service_code: Mapped[str] = mapped_column(String(40), default='')
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('issuer_store_id', 'code', 'rule_version', name='uq_benefit_rule_version'),
        CheckConstraint("kind IN ('bonus','points','coupon','package')", name='ck_benefit_kind'),
        CheckConstraint('rule_version>0 AND credit_cents_per_unit>0 AND settlement_cents_per_unit>=0 AND settlement_cents_per_unit<=credit_cents_per_unit AND sale_cents_per_unit>=0 AND exchange_points_per_unit>=0 AND validity_days>0', name='ck_benefit_rule_values'),
        CheckConstraint("refund_policy IN ('none','unused_before_expiry','unused_anytime') AND discount_bearer IN ('group','service_store')", name='ck_benefit_rule_policy'),
        CheckConstraint("kind!='bonus' OR credit_cents_per_unit=1", name='ck_benefit_bonus_fen'),
        CheckConstraint("sale_cents_per_unit<=credit_cents_per_unit AND ((discount_bearer='group' AND settlement_cents_per_unit=credit_cents_per_unit) OR (discount_bearer='service_store' AND settlement_cents_per_unit=sale_cents_per_unit))", name='ck_benefit_discount_bearer'),
        CheckConstraint("kind NOT IN ('bonus','points') OR (sale_cents_per_unit=0 AND exchange_points_per_unit=0 AND refund_policy='none')", name='ck_benefit_non_cash'),
    )


class BenefitWallet(CentralVersioned, Base):
    __tablename__ = 'benefit_wallets'
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey('benefit_rules.id'))
    issuer_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    source_case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    source_kind: Mapped[str] = mapped_column(String(20))
    initial_units: Mapped[int] = mapped_column(BigInteger)
    correction_units: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0')
    balance_units: Mapped[int] = mapped_column(BigInteger)
    reserved_units: Mapped[int] = mapped_column(BigInteger, default=0)
    expires_on: Mapped[date] = mapped_column(Date)
    account_id: Mapped[int | None] = mapped_column(ForeignKey('flow_accounts.id'), nullable=True)
    cash_id: Mapped[int | None] = mapped_column(ForeignKey('cash_entries.id'), nullable=True, unique=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (
        CheckConstraint('initial_units>0 AND initial_units+correction_units>=0 AND balance_units>=0 AND reserved_units>=0 AND reserved_units<=balance_units AND balance_units<=initial_units+correction_units', name='ck_benefit_wallet_units'),
        CheckConstraint("source_kind IN ('purchase','grant','exchange')", name='ck_benefit_wallet_source'),
        CheckConstraint("(source_kind='purchase' AND cash_id IS NOT NULL AND account_id IS NOT NULL) OR (source_kind!='purchase' AND cash_id IS NULL AND account_id IS NULL)", name='ck_benefit_wallet_cash'),
    )


class BenefitEntry(GroupProtected, Base):
    __tablename__ = 'benefit_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey('benefit_wallets.id'), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    purpose: Mapped[str] = mapped_column(String(20))
    units: Mapped[int] = mapped_column(BigInteger)
    credit_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    original_id: Mapped[int | None] = mapped_column(ForeignKey('benefit_entries.id'), nullable=True)
    cash_id: Mapped[int | None] = mapped_column(ForeignKey('cash_entries.id'), nullable=True, unique=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey('flow_accounts.id'), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('store_id', 'account_id', 'reference', name='uq_benefit_cash_reference'),
        CheckConstraint("(purpose IN ('purchase','grant','exchange_in','reverse') AND units>0) OR (purpose IN ('capture','refund','adjust','exchange_out') AND units<0) OR (purpose='correction' AND units!=0)", name='ck_benefit_entry_sign'),
        CheckConstraint("(purpose='capture' AND credit_cents>0) OR (purpose='reverse' AND credit_cents<0) OR (purpose NOT IN ('capture','reverse') AND credit_cents=0)", name='ck_benefit_credit_sign'),
        CheckConstraint("(purpose IN ('purchase','refund') AND cash_id IS NOT NULL AND account_id IS NOT NULL AND reference IS NOT NULL) OR (purpose NOT IN ('purchase','refund') AND cash_id IS NULL AND account_id IS NULL AND reference IS NULL)", name='ck_benefit_entry_cash'),
    )


class BenefitReservation(Versioned, Base):
    __tablename__ = 'benefit_reservations'
    wallet_id: Mapped[int] = mapped_column(ForeignKey('benefit_wallets.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    units: Mapped[int] = mapped_column(BigInteger)
    credit_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='reserved')
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (CheckConstraint("units>0 AND credit_cents>0 AND status IN ('reserved','captured','released')", name='ck_benefit_reservation'),)


class BenefitPaymentLink(StoreScoped, Base):
    __tablename__ = 'benefit_payment_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey('benefit_entries.id'), unique=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey('benefit_reservations.id'))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (CheckConstraint('amount_cents!=0', name='ck_benefit_payment'),)


class BenefitSettlement(StoreScoped, Base):
    __tablename__ = 'benefit_settlements'
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey('benefit_entries.id'), index=True)
    side: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint('entry_id', 'side', name='uq_benefit_settlement'),
        CheckConstraint("side IN ('center','store') AND amount_cents!=0", name='ck_benefit_settlement'))


class BenefitRefund(Versioned, Base):
    __tablename__ = 'benefit_refunds'
    wallet_id: Mapped[int] = mapped_column(ForeignKey('benefit_wallets.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    units: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='requested')
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(500))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    executed_entry_id: Mapped[int | None] = mapped_column(ForeignKey('benefit_entries.id'), nullable=True, unique=True)
    __table_args__ = (
        CheckConstraint("units>0 AND status IN ('requested','approved','rejected','cancelled','executed')", name='ck_benefit_refund_status'),
        CheckConstraint("status NOT IN ('approved','executed') OR approved_by IS NOT NULL", name='ck_benefit_refund_approval'),
        CheckConstraint("(status='executed' AND executed_entry_id IS NOT NULL) OR (status!='executed' AND executed_entry_id IS NULL)", name='ck_benefit_refund_execution'),
    )


@event.listens_for(Session, 'before_flush')
def guard_benefits(db, *_):
    immutable = (BenefitRule, BenefitEntry, BenefitPaymentLink, BenefitSettlement)
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, immutable):
            raise HTTPException(409, '权益规则和账本不可覆盖，请追加新版本或原单冲正')
        frozen = ()
        if isinstance(row, BenefitWallet):
            frozen = ('member_id','rule_id','issuer_store_id','source_case_id','source_kind','initial_units','expires_on','account_id','cash_id','evidence_id','created_by')
        if isinstance(row, BenefitReservation):
            frozen = ('wallet_id','case_id','units','credit_cents','evidence_id','actor_id')
        if isinstance(row, BenefitRefund):
            frozen = ('wallet_id','case_id','units','requested_by','evidence_id','reason')
        if frozen and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen)):
            raise HTTPException(409, '权益来源和申请事实不可改写，请撤销后另行申请')
    for row in list(db.new) + list(db.dirty) + list(db.deleted):
        if isinstance(row, (BenefitWallet, BenefitReservation, BenefitRefund, *immutable)) and not db.info.get('_group_authority'):
            raise HTTPException(403, '权益变动须通过集团业务服务')
