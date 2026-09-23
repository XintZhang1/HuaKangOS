"""Append-only customer aftercare agreements and original-source corrections."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,ForeignKey,Date,DateTime,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped

class AftercareOrder(StoreScoped,Base):
    __tablename__='aftercare_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    scenario:Mapped[str]=mapped_column(String(30))
    reason:Mapped[str]=mapped_column(String(1000))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("scenario IN ('sale_termination','vehicle_return','repair_refund')",name='ck_aftercare_scenario'),)

class AftercareSource(StoreScoped,Base):
    __tablename__='aftercare_sources'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),index=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    allocation_id:Mapped[int|None]=mapped_column(ForeignKey('repair_allocations.id'),nullable=True)
    original_cents:Mapped[int]=mapped_column(BigInteger)
    snapshot:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('case_id','source_case_id',name='uq_aftercare_source'),CheckConstraint('original_cents>=0',name='ck_aftercare_source_amount'),)

class AftercareClaim(StoreScoped,Base):
    __tablename__='aftercare_claims'
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),index=True)

class AftercareExecution(StoreScoped,Base):
    __tablename__='aftercare_execution_facts'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),index=True)
    source_id:Mapped[int]=mapped_column(ForeignKey('aftercare_sources.id'),index=True)
    outcome:Mapped[str]=mapped_column(String(20))
    external_result:Mapped[str]=mapped_column(String(30))
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("outcome IN ('not_started','stopped','completed') AND external_result IN ('not_required','terminated')",name='ck_aftercare_execution'),)

class AftercarePlan(StoreScoped,Base):
    __tablename__='aftercare_plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    reason:Mapped[str]=mapped_column(String(1000))
    digest:Mapped[str]=mapped_column(String(64))
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_aftercare_plan_revision'),)

class AftercarePlanLine(StoreScoped,Base):
    __tablename__='aftercare_plan_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),index=True)
    source_id:Mapped[int]=mapped_column(ForeignKey('aftercare_sources.id'))
    execution_id:Mapped[int|None]=mapped_column(ForeignKey('aftercare_execution_facts.id'),nullable=True)
    base_cents:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    retained_cents:Mapped[int]=mapped_column(BigInteger)
    refund_cents:Mapped[int]=mapped_column(BigInteger)
    revenue_credit_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('plan_id','source_id',name='uq_aftercare_plan_source'),CheckConstraint('credit_cents>=0 AND retained_cents>=0 AND refund_cents>=0 AND base_cents=credit_cents+retained_cents',name='ck_aftercare_plan_amount'),)

class AftercareTender(StoreScoped,Base):
    __tablename__='aftercare_tenders'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),index=True)
    source_id:Mapped[int]=mapped_column(ForeignKey('aftercare_sources.id'))
    kind:Mapped[str]=mapped_column(String(20))
    original_id:Mapped[int]=mapped_column(Integer)
    units:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    __table_args__=(UniqueConstraint('plan_id','kind','original_id',name='uq_aftercare_tender_origin'),CheckConstraint("((kind IN ('cash','principal','benefit','advance') AND credit_cents>0) OR (kind='repair_package' AND credit_cents>=0)) AND units>0",name='ck_aftercare_tender'),)

class AftercareApproval(StoreScoped,Base):
    __tablename__='aftercare_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))

class AftercareConsent(StoreScoped,Base):
    __tablename__='aftercare_consents'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    plan_digest:Mapped[str]=mapped_column(String(64))

class AftercarePlanCancellation(StoreScoped,Base):
    __tablename__='aftercare_plan_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(1000))

class AftercareApplication(StoreScoped,Base):
    __tablename__='aftercare_applications'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    business_date:Mapped[date]=mapped_column(Date)

class AftercareAdjustment(StoreScoped,Base):
    __tablename__='aftercare_adjustments'
    id:Mapped[int]=mapped_column(primary_key=True)
    application_id:Mapped[int]=mapped_column(ForeignKey('aftercare_applications.id'),index=True)
    plan_line_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plan_lines.id'),unique=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    allocation_id:Mapped[int|None]=mapped_column(ForeignKey('repair_allocations.id'),nullable=True)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    revenue_credit_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('credit_cents>=0',name='ck_aftercare_adjustment'),)

class AftercareCashRefund(StoreScoped,Base):
    __tablename__='aftercare_cash_refunds'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),index=True)
    tender_id:Mapped[int]=mapped_column(ForeignKey('aftercare_tenders.id'),index=True)
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))

class AftercareReceipt(StoreScoped,Base):
    __tablename__='aftercare_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_aftercare_receipt'),)

class AftercareCashCollection(StoreScoped,Base):
    __tablename__='aftercare_cash_collections'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'),index=True)
    source_id:Mapped[int]=mapped_column(ForeignKey('aftercare_sources.id'))
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))

IMMUTABLE=(AftercareOrder,AftercareSource,AftercareExecution,AftercarePlan,AftercarePlanLine,AftercareTender,AftercareApproval,AftercareConsent,AftercarePlanCancellation,AftercareApplication,AftercareAdjustment,AftercareCashRefund,AftercareCashCollection,AftercareReceipt)
@event.listens_for(Session,'before_flush')
def protect_aftercare(db,*_):
    if any(isinstance(r,IMMUTABLE) for r in list(db.dirty)+list(db.deleted)):raise HTTPException(409,'售后方案、原单、批准和纠正流水不能覆盖；请追加新方案或后续处理记录')
