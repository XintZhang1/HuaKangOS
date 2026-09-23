"""Immutable claim assessments, external facts, responsibility changes and cash links."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,ForeignKey,Date,DateTime,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped


class ClaimOrder(StoreScoped,Base):
    __tablename__='claims_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    party_type:Mapped[str]=mapped_column(String(20))
    payment_route:Mapped[str]=mapped_column(String(30))
    party_name:Mapped[str]=mapped_column(String(120))
    insurer_id:Mapped[int|None]=mapped_column(ForeignKey('master_insurers.id'),nullable=True)
    manufacturer_id:Mapped[int|None]=mapped_column(ForeignKey('flow_references.id'),nullable=True)
    source_snapshot:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    __table_args__=(CheckConstraint("party_type IN ('insurer','manufacturer','internal') AND payment_route IN ('repair_receivable','customer_direct','customer_via_store','internal')",name='ck_claim_order_kind'),)


class ClaimAssessment(StoreScoped,Base):
    __tablename__='claims_assessments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    quote_digest:Mapped[str]=mapped_column(String(64))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    lines:Mapped[list]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_claim_assessment_revision'),CheckConstraint('amount_cents > 0',name='ck_claim_assessment_amount'))


class ClaimApproval(StoreScoped,Base):
    __tablename__='claims_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    assessment_id:Mapped[int]=mapped_column(ForeignKey('claims_assessments.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ClaimTransmission(StoreScoped,Base):
    __tablename__='claims_transmissions'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),index=True)
    assessment_id:Mapped[int]=mapped_column(ForeignKey('claims_assessments.id'))
    # The reverse link is checked against the immutable result at every use and
    # restore; avoiding a schema cycle keeps SQLite/PostgreSQL creation ordered.
    supplement_result_id:Mapped[int|None]=mapped_column(Integer,nullable=True,unique=True)
    external_reference:Mapped[str]=mapped_column(String(120))
    submitted_on:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ClaimResult(StoreScoped,Base):
    __tablename__='claims_results'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),index=True)
    assessment_id:Mapped[int]=mapped_column(ForeignKey('claims_assessments.id'))
    transmission_id:Mapped[int]=mapped_column(ForeignKey('claims_transmissions.id'),unique=True)
    outcome:Mapped[str]=mapped_column(String(20))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    lines:Mapped[list]=mapped_column(JSON)
    result_on:Mapped[date]=mapped_column(Date)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("outcome IN ('approved','partial','rejected','need_documents') AND amount_cents >= 0",name='ck_claim_result'),)


class ClaimBinding(StoreScoped,Base):
    __tablename__='claims_bindings'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),unique=True)
    allocation_id:Mapped[int]=mapped_column(ForeignKey('repair_allocations.id'))
    assessment_id:Mapped[int]=mapped_column(ForeignKey('claims_assessments.id'))
    result_id:Mapped[int|None]=mapped_column(ForeignKey('claims_results.id'),nullable=True)
    approved_cents:Mapped[int]=mapped_column(BigInteger)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('approved_cents >= 0',name='ck_claim_binding_amount'),)


class ClaimResolution(StoreScoped,Base):
    __tablename__='claims_resolutions'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),unique=True)
    allocation_id:Mapped[int]=mapped_column(ForeignKey('repair_allocations.id'))
    result_id:Mapped[int]=mapped_column(ForeignKey('claims_results.id'))
    original_cents:Mapped[int]=mapped_column(BigInteger)
    reduction_cents:Mapped[int]=mapped_column(BigInteger)
    refund_cents:Mapped[int]=mapped_column(BigInteger)
    internal_bearer:Mapped[str]=mapped_column(String(120))
    refunds:Mapped[list]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('original_cents >= reduction_cents AND reduction_cents > 0 AND refund_cents >= 0',name='ck_claim_resolution_amount'),)


class ClaimResolutionApproval(StoreScoped,Base):
    __tablename__='claims_resolution_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    resolution_id:Mapped[int]=mapped_column(ForeignKey('claims_resolutions.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ClaimApplication(StoreScoped,Base):
    __tablename__='claims_applications'
    id:Mapped[int]=mapped_column(primary_key=True)
    resolution_id:Mapped[int]=mapped_column(ForeignKey('claims_resolutions.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)


class ClaimResponsibility(StoreScoped,Base):
    __tablename__='claims_responsibility_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    application_id:Mapped[int]=mapped_column(ForeignKey('claims_applications.id'),index=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    allocation_id:Mapped[int|None]=mapped_column(ForeignKey('repair_allocations.id'),nullable=True)
    payer_type:Mapped[str]=mapped_column(String(20))
    payer_name:Mapped[str]=mapped_column(String(120))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint("(payer_type IN ('insurer','manufacturer') AND allocation_id IS NOT NULL AND amount_cents<0) OR (payer_type='internal' AND allocation_id IS NULL AND amount_cents>0)",name='ck_claim_responsibility_sign'),)


class ClaimReimbursementApproval(StoreScoped,Base):
    __tablename__='claims_reimbursement_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),unique=True)
    result_id:Mapped[int]=mapped_column(ForeignKey('claims_results.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('amount_cents > 0',name='ck_claim_reimbursement_amount'),)


class ClaimCash(StoreScoped,Base):
    __tablename__='claims_cash'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),index=True)
    purpose:Mapped[str]=mapped_column(String(30))
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),unique=True)
    resolution_id:Mapped[int|None]=mapped_column(ForeignKey('claims_resolutions.id'),nullable=True)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('claims_cash.id'),nullable=True)
    return_plan_id:Mapped[int|None]=mapped_column(ForeignKey('claims_return_plans.id'),nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("purpose IN ('thirdparty_refund','pass_receive','pass_pay','customer_return','party_return','unused_refund')",name='ck_claim_cash_purpose'),)


class ClaimCustomerPayment(StoreScoped,Base):
    __tablename__='claims_customer_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    purpose:Mapped[str]=mapped_column(String(20))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('claims_customer_payments.id'),nullable=True)
    return_plan_id:Mapped[int|None]=mapped_column(ForeignKey('claims_return_plans.id'),nullable=True)
    business_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("amount_cents > 0 AND purpose IN ('reimbursement','return')",name='ck_claim_customer_payment_amount'),)


class ClaimReturnPlan(StoreScoped,Base):
    __tablename__='claims_return_plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    selections:Mapped[list]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('amount_cents > 0',name='ck_claim_return_plan_amount'),)


class ClaimReturnApproval(StoreScoped,Base):
    __tablename__='claims_return_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('claims_return_plans.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ClaimReturnCancellation(StoreScoped,Base):
    __tablename__='claims_return_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('claims_return_plans.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ClaimClosure(StoreScoped,Base):
    __tablename__='claims_closures'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('claims_orders.id'),unique=True)
    unused_cents:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('unused_cents >= 0',name='ck_claim_closure_amount'),)


class ClaimReceipt(StoreScoped,Base):
    __tablename__='claims_request_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_claim_request'),)


IMMUTABLE=(ClaimOrder,ClaimAssessment,ClaimApproval,ClaimTransmission,ClaimResult,ClaimBinding,ClaimResolution,
    ClaimResolutionApproval,ClaimApplication,ClaimResponsibility,ClaimReimbursementApproval,ClaimCash,ClaimCustomerPayment,
    ClaimReturnPlan,ClaimReturnApproval,ClaimReturnCancellation,ClaimClosure,ClaimReceipt)


@event.listens_for(Session,'before_flush')
def protect_claim_facts(db,*_):
    if any(isinstance(row,IMMUTABLE) for row in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'核价、外部结果、责任调整和报销事实不可覆盖；请追加对应处理记录')
