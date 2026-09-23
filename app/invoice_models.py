"""Immutable internal invoice instructions and externally attested results."""
from datetime import date
from sqlalchemy import String,BigInteger,Date,ForeignKey,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from fastapi import HTTPException
from .db import Base
from .models import StoreScoped


class InvoiceApplication(StoreScoped,Base):
    __tablename__='invoice_applications'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    original_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,index=True)
    direction:Mapped[str]=mapped_column(String(10))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    issuer_name:Mapped[str]=mapped_column(String(180))
    issuer_tax_id:Mapped[str]=mapped_column(String(30))
    buyer_name:Mapped[str]=mapped_column(String(160))
    buyer_tax_id:Mapped[str]=mapped_column(String(20),default='')
    reason:Mapped[str]=mapped_column(String(1000))
    source_version:Mapped[int]=mapped_column()
    __table_args__=(CheckConstraint("amount_cents>0 AND ((direction='blue' AND original_case_id IS NULL) OR (direction='red' AND original_case_id IS NOT NULL))",name='ck_invoice_application'),)


class InvoiceApproval(StoreScoped,Base):
    __tablename__='invoice_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('invoice_applications.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))


class InvoiceResult(StoreScoped,Base):
    __tablename__='invoice_results'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('invoice_applications.id'),unique=True)
    invoice_number:Mapped[str]=mapped_column(String(60))
    issuer_tax_id:Mapped[str]=mapped_column(String(30))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    issued_on:Mapped[date]=mapped_column(Date,index=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('issuer_tax_id','invoice_number',name='uq_invoice_issuer_number'),CheckConstraint('amount_cents>0',name='ck_invoice_result_amount'),)


IMMUTABLE=(InvoiceApplication,InvoiceApproval,InvoiceResult)
@event.listens_for(Session,'before_flush')
def immutable_invoice(db,*_):
    if any(isinstance(row,IMMUTABLE) for row in db.dirty|db.deleted):
        raise HTTPException(409,'开票申请、批准及实际票据不可覆盖；请关联原票另办冲红')
