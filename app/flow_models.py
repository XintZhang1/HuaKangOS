"""Workflow v1. Financial facts and stock movements are append-only.
All money is integer CNY fen; material quantity is integer milli-units.
"""
from datetime import datetime, date
from sqlalchemy import String, Text, Integer, BigInteger, Boolean, Date, DateTime, ForeignKey, JSON, LargeBinary, CheckConstraint, UniqueConstraint, Index, event
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, Session
from fastapi import HTTPException
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


class Customer(Versioned, Base):
    __tablename__ = 'flow_customers'
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(30), default='')
    contact_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    note: Mapped[str] = mapped_column(Text, default='')


class Case(Versioned, Base):
    __tablename__ = 'flow_cases'
    number: Mapped[str] = mapped_column(String(60), unique=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    flow_version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(180))
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('flow_customers.id'), nullable=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('flow_cases.id'), nullable=True, index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey('vehicles.id'), nullable=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (CheckConstraint('amount_cents >= 0 AND (cost_cents IS NULL OR cost_cents >= 0)', name='ck_flow_case_amount'),)


class Task(Versioned, Base):
    __tablename__ = 'flow_tasks'
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    key: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(25))
    assignee_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='open', index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    done_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('case_id','key',name='uq_flow_task_key'),
                     CheckConstraint("status IN ('open','done','cancelled')",name='ck_flow_task_status'))


class FlowEvent(StoreScoped, Base):
    __tablename__ = 'flow_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    before_state: Mapped[str] = mapped_column(String(30), default='')
    after_state: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class RequestReceipt(StoreScoped, Base):
    __tablename__ = 'flow_request_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id','request_key',name='uq_flow_request_key'),)


class VehicleHold(StoreScoped, Base):
    __tablename__ = 'flow_vehicle_holds'
    vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'), primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)


class PaymentLink(StoreScoped, Base):
    __tablename__ = 'flow_payment_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    cash_id: Mapped[int] = mapped_column(ForeignKey('cash_entries.id'), index=True)
    original_id: Mapped[int | None] = mapped_column(ForeignKey('flow_payment_links.id'), nullable=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('flow_accounts.id'))
    direction: Mapped[str] = mapped_column(String(5))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str] = mapped_column(String(100))
    business_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (CheckConstraint("amount_cents > 0 AND direction IN ('in','out')",name='ck_flow_payment'),
                     Index('ix_flow_payment_reference','store_id','account_id','reference'))


class Account(Versioned, Base):
    __tablename__ = 'flow_accounts'
    name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(20), default='bank')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('store_id','name',name='uq_flow_account_name'),)


class Item(Versioned, Base):
    __tablename__ = 'flow_items'
    sku: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20), default='件')
    quantity_milli: Mapped[int] = mapped_column(BigInteger, default=0)
    unit_cost_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    inventory_value_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    reorder_milli: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('store_id','sku',name='uq_flow_item_sku'),
        CheckConstraint('quantity_milli >= 0 AND unit_cost_cents >= 0 AND reorder_milli >= 0 AND inventory_value_cents >= 0', name='ck_flow_stock_nonnegative'))


class StockMove(StoreScoped, Base):
    __tablename__ = 'flow_stock_moves'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('flow_items.id'), index=True)
    quantity_milli: Mapped[int] = mapped_column(BigInteger)
    unit_cost_cents: Mapped[int] = mapped_column(BigInteger)
    value_cents: Mapped[int] = mapped_column(BigInteger)
    purpose: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    original_id: Mapped[int | None] = mapped_column(ForeignKey('flow_stock_moves.id'), nullable=True)


class Member(Versioned, Base):
    __tablename__ = 'flow_members'
    customer_id: Mapped[int] = mapped_column(ForeignKey('flow_customers.id'), unique=True)
    number: Mapped[str] = mapped_column(String(60), unique=True)
    balance_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint('balance_cents >= 0 AND points >= 0',name='ck_flow_member_balance'),)


class MemberEntry(StoreScoped, Base):
    __tablename__ = 'flow_member_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey('flow_members.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    purpose: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Reference(Versioned, Base):
    __tablename__ = 'flow_references'
    category: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('store_id','category','name',name='uq_flow_reference'),)


class DocTemplate(Versioned, Base):
    __tablename__ = 'flow_doc_templates'
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(120))
    clauses: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    __table_args__ = (UniqueConstraint('store_id','kind',name='uq_flow_template'),)


class FileAsset(StoreScoped, Base):
    __tablename__ = 'flow_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    category: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(150))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), default='')
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey('flow_files.id'), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


APPEND_ONLY = (FlowEvent, RequestReceipt, PaymentLink, StockMove, MemberEntry, FileAsset)


@event.listens_for(Session, 'before_flush')
def no_history_overwrite(db, *_):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, APPEND_ONLY):
            raise HTTPException(409, '已记录的业务凭据不可覆盖；请新增补充或冲正记录')
