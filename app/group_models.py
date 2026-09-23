"""Group identities and principal wallets; financial history is append-only.

Central tables intentionally do not inherit StoreScoped. They require an explicit
group-service authority, while links to store business remain tenant scoped.
"""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import (String, Integer, BigInteger, Boolean, DateTime, ForeignKey,
                        JSON, CheckConstraint, UniqueConstraint, event, inspect)
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned


class GroupProtected:
    """Central data may only be queried or changed inside group_service.authority."""


class CentralVersioned(GroupProtected):
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @declared_attr.directive
    def __mapper_args__(cls):
        return {'version_id_col': cls.version}


class GroupIdentity(CentralVersioned, Base):
    __tablename__ = 'group_identities'
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    # Customers have a random key: a phone number is never a unique person ID.
    canonical_key: Mapped[str] = mapped_column(String(80))
    search_key: Mapped[str] = mapped_column(String(100), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (
        UniqueConstraint('kind', 'canonical_key', name='uq_group_identity_key'),
        CheckConstraint("kind IN ('customer','vehicle','counterparty')", name='ck_group_identity_kind'),
    )


class GroupIdentityLink(StoreScoped, Base):
    __tablename__ = 'group_identity_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey('group_identities.id'), index=True)
    local_kind: Mapped[str] = mapped_column(String(20))
    local_id: Mapped[int] = mapped_column(Integer)
    confirmed_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('store_id', 'local_kind', 'local_id', name='uq_group_local_identity'),
        CheckConstraint("local_kind IN ('customer','vehicle','counterparty')", name='ck_group_link_kind'),
    )


class GroupMember(CentralVersioned, Base):
    __tablename__ = 'group_members'
    identity_id: Mapped[int] = mapped_column(ForeignKey('group_identities.id'), unique=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    balance_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint(
        'balance_cents >= 0 AND reserved_cents >= 0 AND reserved_cents <= balance_cents',
        name='ck_group_member_available'),)


class GroupEntry(GroupProtected, Base):
    __tablename__ = 'group_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    purpose: Mapped[str] = mapped_column(String(20))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    original_id: Mapped[int | None] = mapped_column(ForeignKey('group_entries.id'), nullable=True)
    cash_id: Mapped[int | None] = mapped_column(ForeignKey('cash_entries.id'), unique=True, nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey('flow_accounts.id'), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('store_id', 'account_id', 'reference', name='uq_group_cash_reference'),
        CheckConstraint("(purpose IN ('topup','reverse') AND amount_cents > 0) OR "
                        "(purpose IN ('capture','refund') AND amount_cents < 0) OR (purpose='correction' AND amount_cents!=0)", name='ck_group_entry_sign'),
        CheckConstraint("(purpose IN ('topup','refund') AND cash_id IS NOT NULL AND account_id IS NOT NULL "
                        "AND reference IS NOT NULL) OR (purpose IN ('capture','reverse','correction') AND cash_id IS NULL "
                        "AND account_id IS NULL AND reference IS NULL)", name='ck_group_entry_cash'),
        CheckConstraint("(purpose = 'topup' AND original_id IS NULL) OR purpose = 'capture' OR "
                        "(purpose IN ('refund','reverse','correction') AND original_id IS NOT NULL)", name='ck_group_entry_original'),
    )


class GroupReservation(Versioned, Base):
    __tablename__ = 'group_reservations'
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='reserved')
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (CheckConstraint("amount_cents > 0 AND status IN ('reserved','captured','released')",
                                       name='ck_group_reservation'),)


class GroupRefundRequest(Versioned, Base):
    __tablename__ = 'group_refund_requests'
    member_id: Mapped[int] = mapped_column(ForeignKey('group_members.id'), index=True)
    original_id: Mapped[int] = mapped_column(ForeignKey('group_entries.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='requested')
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(500))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    executed_entry_id: Mapped[int | None] = mapped_column(ForeignKey('group_entries.id'), nullable=True, unique=True)
    __table_args__ = (
        CheckConstraint("amount_cents > 0 AND status IN ('requested','approved','rejected','cancelled','executed')",
                        name='ck_group_refund_status'),
        CheckConstraint("status NOT IN ('approved','executed') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
                        name='ck_group_refund_approved'),
        CheckConstraint("(status = 'executed' AND executed_entry_id IS NOT NULL AND closed_by IS NOT NULL) OR "
                        "(status != 'executed' AND executed_entry_id IS NULL)", name='ck_group_refund_executed'),
    )


class GroupPaymentLink(StoreScoped, Base):
    __tablename__ = 'group_payment_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey('group_entries.id'), unique=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey('group_reservations.id'))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (CheckConstraint('amount_cents != 0', name='ck_group_payment_amount'),)


class GroupSettlementEntry(StoreScoped, Base):
    __tablename__ = 'group_settlement_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey('group_entries.id'), index=True)
    side: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (
        UniqueConstraint('entry_id', 'side', name='uq_group_settlement_side'),
        CheckConstraint("side IN ('center','store') AND amount_cents != 0", name='ck_group_settlement'),
    )


class GroupEvent(StoreScoped, Base):
    __tablename__ = 'group_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey('group_members.id'), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GroupReceipt(StoreScoped, Base):
    __tablename__ = 'group_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id', 'request_key', name='uq_group_request'),)


APPEND_ONLY = (GroupIdentityLink, GroupEntry, GroupPaymentLink, GroupSettlementEntry, GroupEvent, GroupReceipt)


@event.listens_for(Session, 'before_flush')
def guard_group_records(db, *_):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, APPEND_ONLY):
            raise HTTPException(409, '集团身份关联和账本不可覆盖；请追加原单冲正记录')
        if isinstance(row, GroupRefundRequest):
            immutable = ('member_id', 'original_id', 'case_id', 'amount_cents', 'requested_by', 'evidence_id', 'reason')
            if row in db.deleted or any(inspect(row).attrs[key].history.has_changes() for key in immutable):
                raise HTTPException(409, '集团退款申请事实不可覆盖；请撤销后另行申请')
    for row in list(db.new) + list(db.dirty) + list(db.deleted):
        if isinstance(row, GroupProtected) and not db.info.get('_group_authority'):
            raise HTTPException(403, '集团数据必须经集团业务服务校验')


@event.listens_for(Session, 'do_orm_execute')
def guard_group_queries(execute_state):
    mappers = execute_state.all_mappers
    if any(issubclass(m.class_, GroupProtected) for m in mappers):
        if not execute_state.session.info.get('_group_authority'):
            raise HTTPException(403, '集团数据必须经集团业务服务查询')
        if execute_state.is_update or execute_state.is_delete:
            raise HTTPException(409, '集团业务不可批量覆盖；请使用版本化动作')
