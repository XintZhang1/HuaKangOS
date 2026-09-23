"""Original noncustomer vehicle income: immutable target and actual cash facts."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Date,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped


class Fact:
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class VehicleIncomeOrder(StoreScoped,Base):
    __tablename__='vehicle_income_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    supplier_id:Mapped[int]=mapped_column(ForeignKey('master_suppliers.id'),index=True)
    supplier_snapshot:Mapped[dict]=mapped_column(JSON)
    external_reference:Mapped[str]=mapped_column(String(120))
    primary_source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('store_id','supplier_id','external_reference',name='uq_vehicle_income_external'),)


class VehicleIncomeSource(StoreScoped,Base):
    __tablename__='vehicle_income_sources'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('vehicle_income_orders.id'),index=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    source_version:Mapped[int]=mapped_column(Integer)
    vehicle_id:Mapped[int|None]=mapped_column(ForeignKey('vehicles.id'),nullable=True)
    snapshot:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('case_id','source_case_id','vehicle_id',name='uq_vehicle_income_source'),)


class VehicleIncomeRevision(Fact,StoreScoped,Base):
    __tablename__='vehicle_income_revisions'
    case_id:Mapped[int]=mapped_column(ForeignKey('vehicle_income_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    previous_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_income_revisions.id'),nullable=True)
    previous_cents:Mapped[int]=mapped_column(BigInteger)
    target_cents:Mapped[int]=mapped_column(BigInteger)
    invoice_mode:Mapped[str]=mapped_column(String(25))
    due_date:Mapped[date]=mapped_column(Date)
    source_versions:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_vehicle_income_revision'),CheckConstraint("target_cents>=0 AND previous_cents>=0 AND invoice_mode IN ('store_invoice','external_document')",name='ck_vehicle_income_revision'),)


class VehicleIncomeDecision(Fact,StoreScoped,Base):
    __tablename__='vehicle_income_decisions'
    revision_id:Mapped[int]=mapped_column(ForeignKey('vehicle_income_revisions.id'),unique=True)
    decision:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint("decision IN ('approved','rejected','withdrawn') AND (decision='withdrawn' OR evidence_id IS NOT NULL)",name='ck_vehicle_income_decision'),)


class VehicleIncomeCash(Fact,StoreScoped,Base):
    __tablename__='vehicle_income_cash'
    case_id:Mapped[int]=mapped_column(ForeignKey('vehicle_income_orders.id'),index=True)
    revision_id:Mapped[int]=mapped_column(ForeignKey('vehicle_income_revisions.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_income_cash.id'),nullable=True,index=True)
    direction:Mapped[str]=mapped_column(String(3))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    account_snapshot:Mapped[dict]=mapped_column(JSON)
    reference:Mapped[str]=mapped_column(String(100))
    business_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint("amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))",name='ck_vehicle_income_cash'),)


class VehicleIncomeReceipt(Fact,StoreScoped,Base):
    __tablename__='vehicle_income_receipts'
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_vehicle_income_request'),)


@event.listens_for(Session,'before_flush')
def immutable_vehicle_income(db,*_):
    models=(VehicleIncomeOrder,VehicleIncomeSource,VehicleIncomeRevision,VehicleIncomeDecision,VehicleIncomeCash,VehicleIncomeReceipt)
    if any(isinstance(r,models) for r in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'非客户整车收入原来源、批准和现金事实不可覆盖，请追加目标修订或原款退款')
