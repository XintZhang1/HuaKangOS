"""Original procurement funding authority and immutable cash/receipt associations."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, BigInteger, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned


class PurchasePrepaymentFacility(StoreScoped, Base):
    __tablename__='procurement_prepayment_facilities'
    id:Mapped[int]=mapped_column(ForeignKey('procurement_orders.id'),primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class PurchasePrepaymentRequest(Versioned, Base):
    __tablename__='procurement_prepayment_requests'
    case_id:Mapped[int]=mapped_column(ForeignKey('procurement_prepayment_facilities.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    valid_until:Mapped[date]=mapped_column(Date)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(500))
    status:Mapped[str]=mapped_column(String(16),default='pending')
    __table_args__=(CheckConstraint("amount_cents>0 AND status IN ('pending','approved','rejected','cancelled','expired','paid')",name='ck_purchase_prepay_request'),)


class PurchasePrepaymentDecision(StoreScoped, Base):
    __tablename__='procurement_prepayment_decisions'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('procurement_prepayment_requests.id'),index=True)
    action:Mapped[str]=mapped_column(String(16))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    reason:Mapped[str]=mapped_column(String(500))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('request_id','action',name='uq_purchase_prepay_decision'),
        CheckConstraint("action IN ('approve','reject','cancel','expire')",name='ck_purchase_prepay_decision'))


class PurchasePrepaymentDisbursement(StoreScoped, Base):
    __tablename__='procurement_prepayment_disbursements'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('procurement_prepayment_requests.id'),index=True)
    payment_id:Mapped[int]=mapped_column(ForeignKey('procurement_payments.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class PurchasePaymentAllocation(StoreScoped, Base):
    __tablename__='procurement_payment_allocations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('procurement_prepayment_facilities.id'),index=True)
    payment_id:Mapped[int]=mapped_column(ForeignKey('procurement_payments.id'),index=True)
    receipt_id:Mapped[int]=mapped_column(ForeignKey('procurement_receipts.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('procurement_payment_allocations.id'),nullable=True)
    return_posting_id:Mapped[int|None]=mapped_column(ForeignKey('procurement_return_postings.id'),nullable=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('(amount_cents>0 AND original_id IS NULL AND return_posting_id IS NULL) OR (amount_cents<0 AND original_id IS NOT NULL AND return_posting_id IS NOT NULL)',name='ck_purchase_payment_allocation'),)


IMMUTABLE=(PurchasePrepaymentFacility,PurchasePrepaymentDecision,PurchasePrepaymentDisbursement,PurchasePaymentAllocation)


@event.listens_for(Session,'before_flush')
def protect_originals(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,IMMUTABLE):raise HTTPException(409,'原预付款申请依据、决定、实际付款及到货抵用不可覆盖')
        if isinstance(row,PurchasePrepaymentRequest) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','amount_cents','valid_until','requested_by','evidence_id','reason'))):
            raise HTTPException(409,'原预付款申请不可改写，请取消未付余量后重新申请')
