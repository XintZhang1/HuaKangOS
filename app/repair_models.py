"""Version-three repair quotes, authorizations, physical facts and settlement."""
from datetime import datetime,date
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,ForeignKey,Date,DateTime,Boolean,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped


class RepairQuote(StoreScoped,Base):
    __tablename__='repair_quotes'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    purpose:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger)
    digest:Mapped[str]=mapped_column(String(64))
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_repair_quote_revision'),
        CheckConstraint("purpose IN ('service','stop') AND amount_cents >= 0 AND discount_cents >= 0",name='ck_repair_quote_amount'))


class RepairLine(StoreScoped,Base):
    __tablename__='repair_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),index=True)
    line_key:Mapped[str]=mapped_column(String(40))
    kind:Mapped[str]=mapped_column(String(10))
    work_item_id:Mapped[int|None]=mapped_column(ForeignKey('master_work_items.id'),nullable=True)
    item_id:Mapped[int|None]=mapped_column(ForeignKey('flow_items.id'),nullable=True)
    code:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    standard_fee_cents:Mapped[int]=mapped_column(BigInteger)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    unit_price_cents:Mapped[int]=mapped_column(BigInteger)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('quote_id','line_key',name='uq_repair_line_key'),
        CheckConstraint("quantity_milli > 0 AND unit_price_cents >= 0 AND amount_cents >= 0 AND discount_cents >= 0 AND ((kind='work' AND work_item_id IS NOT NULL AND item_id IS NULL) OR (kind='part' AND item_id IS NOT NULL AND work_item_id IS NULL))",name='ck_repair_line'))


class RepairPriceApproval(StoreScoped,Base):
    __tablename__='repair_price_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),unique=True)
    minimum_total_cents:Mapped[int]=mapped_column(BigInteger)
    allow_below_minimum:Mapped[bool]=mapped_column(Boolean)
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('minimum_total_cents >= 0',name='ck_repair_price_floor'),)


class RepairAuthorization(StoreScoped,Base):
    __tablename__='repair_authorizations'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'),unique=True)
    quote_digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RepairQuoteCancellation(StoreScoped,Base):
    __tablename__='repair_quote_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RepairStock(StoreScoped,Base):
    __tablename__='repair_stock'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('repair_stock.id'),nullable=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint("(original_id IS NULL AND quantity_milli > 0 AND value_cents >= 0) OR (original_id IS NOT NULL AND quantity_milli < 0 AND value_cents <= 0)",name='ck_repair_stock_sign'),)


class RepairQuality(StoreScoped,Base):
    __tablename__='repair_quality'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    passed:Mapped[bool]=mapped_column(Boolean)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RepairSettlement(StoreScoped,Base):
    __tablename__='repair_settlements'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    labor_cost_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('labor_cost_cents >= 0',name='ck_repair_labor_cost'),)


class RepairAllocation(StoreScoped,Base):
    __tablename__='repair_allocations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    settlement_id:Mapped[int]=mapped_column(ForeignKey('repair_settlements.id'))
    payer_type:Mapped[str]=mapped_column(String(20))
    payer_name:Mapped[str]=mapped_column(String(120))
    insurer_id:Mapped[int|None]=mapped_column(ForeignKey('master_insurers.id'),nullable=True)
    manufacturer_id:Mapped[int|None]=mapped_column(ForeignKey('flow_references.id'),nullable=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    due_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('case_id','payer_type',name='uq_repair_payer'),
        CheckConstraint("payer_type IN ('customer','insurer','manufacturer','internal') AND amount_cents > 0",name='ck_repair_allocation'))


class RepairPayment(StoreScoped,Base):
    __tablename__='repair_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    allocation_id:Mapped[int]=mapped_column(ForeignKey('repair_allocations.id'),index=True)
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))


IMMUTABLE=(RepairQuote,RepairLine,RepairPriceApproval,RepairAuthorization,RepairQuoteCancellation,RepairStock,
    RepairQuality,RepairSettlement,RepairAllocation,RepairPayment)


@event.listens_for(Session,'before_flush')
def immutable_repair(db,*_):
    if any(isinstance(row,IMMUTABLE) for row in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'维修报价、授权、领退料和结算事实不可覆盖；请追加对应业务记录')
