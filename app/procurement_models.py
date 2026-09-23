"""Immutable purchase agreement, receipt batches, returns and cash links."""
from datetime import date
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, ForeignKey, Date, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base
from .models import StoreScoped
from .flow_models import Versioned


class PurchaseOrder(StoreScoped, Base):
    __tablename__='procurement_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    supplier_id:Mapped[int]=mapped_column(ForeignKey('master_suppliers.id'),index=True)
    supplier_name:Mapped[str]=mapped_column(String(120))
    supplier_code:Mapped[str]=mapped_column(String(60))
    supplier_tax_identifier:Mapped[str]=mapped_column(String(100),default='')
    payment_terms_days:Mapped[int]=mapped_column(Integer,default=0)


class PurchaseLine(StoreScoped, Base):
    __tablename__='procurement_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'))
    sku:Mapped[str]=mapped_column(String(60))
    item_name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    unit_cost_cents:Mapped[int]=mapped_column(BigInteger)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('case_id','item_id',name='uq_procurement_line_item'),
        CheckConstraint('quantity_milli > 0 AND unit_cost_cents >= 0 AND amount_cents >= 0',name='ck_procurement_line_value'))


class PurchaseReceipt(StoreScoped, Base):
    __tablename__='procurement_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('procurement_lines.id'),index=True)
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    due_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_procurement_receipt'),)


class PurchaseReturn(Versioned, Base):
    __tablename__='procurement_returns'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    status:Mapped[str]=mapped_column(String(20),default='requested')
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint("status IN ('requested','approved','dispatched','cancelled')",name='ck_procurement_return_state'),
        CheckConstraint("status NOT IN ('approved','dispatched') OR approved_by IS NOT NULL",name='ck_procurement_return_approval'))


class PurchaseReturnLine(StoreScoped, Base):
    __tablename__='procurement_return_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    return_id:Mapped[int]=mapped_column(ForeignKey('procurement_returns.id'),index=True)
    receipt_id:Mapped[int]=mapped_column(ForeignKey('procurement_receipts.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('return_id','receipt_id',name='uq_procurement_return_receipt'),
        CheckConstraint('quantity_milli > 0',name='ck_procurement_return_quantity'))


class PurchaseReturnPosting(StoreScoped, Base):
    __tablename__='procurement_return_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    return_line_id:Mapped[int]=mapped_column(ForeignKey('procurement_return_lines.id'),unique=True)
    receipt_id:Mapped[int]=mapped_column(ForeignKey('procurement_receipts.id'),index=True)
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_procurement_return_posting'),)


class PurchasePayment(StoreScoped, Base):
    __tablename__='procurement_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('procurement_payments.id'),nullable=True)
    direction:Mapped[str]=mapped_column(String(3))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    reference:Mapped[str]=mapped_column(String(100))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(UniqueConstraint('store_id','account_id','reference',name='uq_procurement_cash_reference'),
        CheckConstraint("amount_cents > 0 AND ((direction='out' AND original_id IS NULL) OR (direction='in' AND original_id IS NOT NULL))",name='ck_procurement_payment'))


IMMUTABLE=(PurchaseOrder,PurchaseLine,PurchaseReceipt,PurchaseReturnLine,PurchaseReturnPosting,PurchasePayment)


@event.listens_for(Session,'before_flush')
def immutable_procurement(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,IMMUTABLE):raise HTTPException(409,'采购约定、到货、退货及付款流水不可覆盖；请追加对应业务记录')
        if isinstance(row,PurchaseReturn) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','requested_by','reason','evidence_id'))):
            raise HTTPException(409,'退货申请事实不可覆盖；请撤销后重新申请')
