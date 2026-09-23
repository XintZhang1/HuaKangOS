"""Frozen service fees and pass-through principal with attributable original paths."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Boolean,ForeignKey,Date,DateTime,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class ServicePayee(Versioned,Base):
    __tablename__='service_payees'
    code:Mapped[str]=mapped_column(String(40))
    name:Mapped[str]=mapped_column(String(120))
    account_name:Mapped[str]=mapped_column(String(120))
    account_reference:Mapped[str]=mapped_column(String(120))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(UniqueConstraint('store_id','code',name='uq_service_payee_code'),)


class ServiceIncomeItem(Versioned,Base):
    __tablename__='service_income_items'
    code:Mapped[str]=mapped_column(String(40))
    name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    standard_fee_cents:Mapped[int]=mapped_column(BigInteger)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(UniqueConstraint('store_id','code',name='uq_service_income_code'),CheckConstraint('standard_fee_cents>=0',name='ck_service_income_fee'))


class ServiceOrder(StoreScoped,Base):
    __tablename__='service_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    subtype:Mapped[str]=mapped_column(String(20))
    source_order_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,index=True)
    delivery_blocking:Mapped[bool]=mapped_column(Boolean,default=False)
    customer_name:Mapped[str]=mapped_column(String(100))
    vehicle_snapshot:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("subtype IN ('agency','other_income')",name='ck_service_order_subtype'),)


class ServiceQuote(StoreScoped,Base):
    __tablename__='service_quotes'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    fee_cents:Mapped[int]=mapped_column(BigInteger)
    pass_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger)
    digest:Mapped[str]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_service_quote_revision'),CheckConstraint('fee_cents>=0 AND pass_cents>=0 AND discount_cents>=0 AND fee_cents+pass_cents>0',name='ck_service_quote_amount'))


class ServiceLine(StoreScoped,Base):
    __tablename__='service_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('service_quotes.id'),index=True)
    line_key:Mapped[str]=mapped_column(String(40))
    bucket:Mapped[str]=mapped_column(String(10))
    agency_project_id:Mapped[int|None]=mapped_column(ForeignKey('master_agency_projects.id'),nullable=True)
    income_item_id:Mapped[int|None]=mapped_column(ForeignKey('service_income_items.id'),nullable=True)
    payee_id:Mapped[int|None]=mapped_column(ForeignKey('service_payees.id'),nullable=True)
    code:Mapped[str]=mapped_column(String(40))
    name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    payee_snapshot:Mapped[dict]=mapped_column(JSON)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    unit_price_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    due_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('quote_id','line_key',name='uq_service_quote_line'),CheckConstraint("bucket IN ('fee','pass') AND quantity_milli>0 AND unit_price_cents>=0 AND discount_cents>=0 AND amount_cents>=0",name='ck_service_line_values'))


class ServicePriceApproval(StoreScoped,Base):
    __tablename__='service_price_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('service_quotes.id'),unique=True)
    minimum_fee_cents:Mapped[int]=mapped_column(BigInteger)
    allow_below_minimum:Mapped[bool]=mapped_column(Boolean)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ServiceAuthorization(StoreScoped,Base):
    __tablename__='service_authorizations'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('service_quotes.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ServiceQuoteCancellation(StoreScoped,Base):
    __tablename__='service_quote_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('service_quotes.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class ServiceSubmission(StoreScoped,Base):
    __tablename__='service_submissions'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('service_quotes.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    supplement_result_id:Mapped[int|None]=mapped_column(Integer,nullable=True,unique=True)
    external_reference:Mapped[str]=mapped_column(String(120))
    submitted_on:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class ServiceExternalResult(StoreScoped,Base):
    __tablename__='service_external_results'
    id:Mapped[int]=mapped_column(primary_key=True)
    submission_id:Mapped[int]=mapped_column(ForeignKey('service_submissions.id'),unique=True)
    outcome:Mapped[str]=mapped_column(String(20))
    result:Mapped[str]=mapped_column(String(1000))
    business_date:Mapped[date]=mapped_column(Date)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("outcome IN ('approved','rejected','need_documents')",name='ck_service_external_outcome'),)


class ServiceFulfillment(StoreScoped,Base):
    __tablename__='service_fulfillments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('service_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('case_id','line_key',name='uq_service_fulfillment_line'),)


class ServiceTenderSlice(StoreScoped,Base):
    __tablename__='service_tender_slices'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('service_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    bucket:Mapped[str]=mapped_column(String(10))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    payment_link_id:Mapped[int|None]=mapped_column(ForeignKey('flow_payment_links.id'),nullable=True,index=True)
    credit_link_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_credit_links.id'),nullable=True,index=True)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('service_tender_slices.id'),nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("bucket IN ('fee','pass') AND amount_cents!=0 AND ((payment_link_id IS NOT NULL AND credit_link_id IS NULL) OR (payment_link_id IS NULL AND credit_link_id IS NOT NULL))",name='ck_service_tender_source'),)


class ServicePassEntry(StoreScoped,Base):
    __tablename__='service_pass_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('service_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    purpose:Mapped[str]=mapped_column(String(20))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    tender_id:Mapped[int]=mapped_column(ForeignKey('service_tender_slices.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('service_pass_entries.id'),nullable=True)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    reference:Mapped[str]=mapped_column(String(100))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    business_date:Mapped[date]=mapped_column(Date)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("purpose IN ('disburse','thirdparty_return') AND amount_cents>0",name='ck_service_pass_amount'),)


class ServiceTermination(StoreScoped,Base):
    __tablename__='service_terminations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('service_quotes.id'))
    revision:Mapped[int]=mapped_column(Integer)
    lines:Mapped[list]=mapped_column(JSON)
    returns:Mapped[list]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_service_termination_revision'),)


class ServiceTerminationApproval(StoreScoped,Base):
    __tablename__='service_termination_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('service_terminations.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class ServiceTerminationConsent(StoreScoped,Base):
    __tablename__='service_termination_consents'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('service_terminations.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class ServiceTerminationCancellation(StoreScoped,Base):
    __tablename__='service_termination_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('service_terminations.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class ServiceTerminationApplication(StoreScoped,Base):
    __tablename__='service_termination_applications'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('service_terminations.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    business_date:Mapped[date]=mapped_column(Date)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class ServiceChargeAdjustment(StoreScoped,Base):
    __tablename__='service_charge_adjustments'
    id:Mapped[int]=mapped_column(primary_key=True)
    application_id:Mapped[int]=mapped_column(ForeignKey('service_termination_applications.id'))
    case_id:Mapped[int]=mapped_column(ForeignKey('service_orders.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('service_lines.id'))
    line_key:Mapped[str]=mapped_column(String(40))
    bucket:Mapped[str]=mapped_column(String(10))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint("bucket IN ('fee','pass') AND amount_cents<0",name='ck_service_adjustment_sign'),)


class ServiceRefund(StoreScoped,Base):
    __tablename__='service_refunds'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('service_terminations.id'))
    original_tender_id:Mapped[int]=mapped_column(ForeignKey('service_tender_slices.id'))
    reversal_tender_id:Mapped[int]=mapped_column(ForeignKey('service_tender_slices.id'),unique=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('amount_cents>0',name='ck_service_refund_amount'),)


class ServiceRequest(StoreScoped,Base):
    __tablename__='service_requests'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_service_request'),)


IMMUTABLE=(ServiceOrder,ServiceQuote,ServiceLine,ServicePriceApproval,ServiceAuthorization,ServiceQuoteCancellation,
    ServiceSubmission,ServiceExternalResult,ServiceFulfillment,ServiceTenderSlice,ServicePassEntry,ServiceTermination,
    ServiceTerminationApproval,ServiceTerminationConsent,ServiceTerminationCancellation,ServiceTerminationApplication,ServiceChargeAdjustment,ServiceRefund,ServiceRequest)
@event.listens_for(Session,'before_flush')
def protect_service_facts(db,*_):
    if any(isinstance(r,IMMUTABLE) for r in list(db.dirty)+list(db.deleted)):raise HTTPException(409,'服务报价、实际办理和资金分配不可覆盖，请追加当前版本或原单纠正')
