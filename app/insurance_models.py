"""Insurance facts distinguish customer principal, insurer settlement and commission."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,BigInteger,Integer,Boolean,ForeignKey,Date,DateTime,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped

class Fact:
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
class Proof(Fact):
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
class InsuranceOrder(StoreScoped,Base):
    __tablename__='insurance_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    source_order_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,index=True)
    customer_vehicle_id:Mapped[int|None]=mapped_column(ForeignKey('care_customer_vehicles.id'),nullable=True)
    renewal_task_id:Mapped[int|None]=mapped_column(ForeignKey('care_cases.case_id'),nullable=True,index=True)
    delivery_blocking:Mapped[bool]=mapped_column(Boolean)
    customer_name:Mapped[str]=mapped_column(String(100))
    vin:Mapped[str]=mapped_column(String(17))
    vehicle_snapshot:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(String(1000))
class InsuranceQuote(Fact,StoreScoped,Base):
    __tablename__='insurance_quotes'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    insurer_id:Mapped[int]=mapped_column(ForeignKey('master_insurers.id'))
    insurer_snapshot:Mapped[dict]=mapped_column(JSON)
    lines:Mapped[list]=mapped_column(JSON)
    premium_cents:Mapped[int]=mapped_column(BigInteger)
    expected_commission_cents:Mapped[int]=mapped_column(BigInteger)
    collection_mode:Mapped[str]=mapped_column(String(20))
    start_date:Mapped[date]=mapped_column(Date)
    end_date:Mapped[date]=mapped_column(Date)
    valid_until:Mapped[date]=mapped_column(Date)
    terms:Mapped[str]=mapped_column(String(1500))
    reason:Mapped[str]=mapped_column(String(1000))
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_insurance_quote_revision'),CheckConstraint("premium_cents>0 AND expected_commission_cents>=0 AND end_date>=start_date AND collection_mode IN ('store_collect','customer_direct')",name='ck_insurance_quote_values'))
class InsuranceReview(Proof,StoreScoped,Base):
    __tablename__='insurance_reviews'
    quote_id:Mapped[int]=mapped_column(ForeignKey('insurance_quotes.id'),unique=True)
    decision:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    __table_args__=(CheckConstraint("decision IN ('approved','rejected')",name='ck_insurance_review_decision'),)
class InsuranceConsent(Proof,StoreScoped,Base):
    __tablename__='insurance_consents'
    quote_id:Mapped[int]=mapped_column(ForeignKey('insurance_quotes.id'),unique=True)
    digest:Mapped[str]=mapped_column(String(64))
class InsuranceQuoteCancellation(Fact,StoreScoped,Base):
    __tablename__='insurance_quote_cancellations'
    quote_id:Mapped[int]=mapped_column(ForeignKey('insurance_quotes.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
class InsuranceSubmission(Proof,StoreScoped,Base):
    __tablename__='insurance_submissions'
    quote_id:Mapped[int]=mapped_column(ForeignKey('insurance_quotes.id'),index=True)
    external_reference:Mapped[str]=mapped_column(String(120))
    business_date:Mapped[date]=mapped_column(Date)
class InsuranceResult(Proof,StoreScoped,Base):
    __tablename__='insurance_results'
    submission_id:Mapped[int]=mapped_column(ForeignKey('insurance_submissions.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    insurer_id:Mapped[int]=mapped_column(ForeignKey('master_insurers.id'))
    outcome:Mapped[str]=mapped_column(String(20))
    policy_number:Mapped[str|None]=mapped_column(String(120),nullable=True)
    result:Mapped[str]=mapped_column(String(1000))
    business_date:Mapped[date]=mapped_column(Date)
    observation_id:Mapped[int|None]=mapped_column(ForeignKey('care_vehicle_observations.id'),nullable=True,unique=True)
    __table_args__=(UniqueConstraint('store_id','insurer_id','policy_number',name='uq_insurance_policy_number'),CheckConstraint("outcome IN ('issued','rejected','need_documents') AND ((outcome='issued' AND policy_number IS NOT NULL) OR (outcome!='issued' AND policy_number IS NULL))",name='ck_insurance_result'),)
class InsuranceRenewalLink(Fact,StoreScoped,Base):
    __tablename__='insurance_renewal_links'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),unique=True)
    previous_policy_id:Mapped[int]=mapped_column(ForeignKey('insurance_results.id'),index=True)
class InsuranceTender(Proof,StoreScoped,Base):
    __tablename__='insurance_tenders'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    payment_link_id:Mapped[int|None]=mapped_column(ForeignKey('flow_payment_links.id'),nullable=True,unique=True)
    credit_link_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_credit_links.id'),nullable=True,unique=True)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('insurance_tenders.id'),nullable=True,index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint("amount_cents!=0 AND ((payment_link_id IS NOT NULL AND credit_link_id IS NULL) OR (payment_link_id IS NULL AND credit_link_id IS NOT NULL)) AND ((amount_cents>0 AND original_id IS NULL) OR (amount_cents<0 AND original_id IS NOT NULL))",name='ck_insurance_tender'),)
class InsurancePassEntry(Proof,StoreScoped,Base):
    __tablename__='insurance_pass_entries'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    tender_id:Mapped[int]=mapped_column(ForeignKey('insurance_tenders.id'),index=True)
    purpose:Mapped[str]=mapped_column(String(20))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('insurance_pass_entries.id'),nullable=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    reference:Mapped[str]=mapped_column(String(100))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint("amount_cents>0 AND ((purpose='disburse' AND original_id IS NULL) OR (purpose='insurer_return' AND original_id IS NOT NULL))",name='ck_insurance_pass'),)
class InsuranceDirectEntry(Proof,StoreScoped,Base):
    __tablename__='insurance_direct_entries'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    purpose:Mapped[str]=mapped_column(String(20))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('insurance_direct_entries.id'),nullable=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    external_reference:Mapped[str]=mapped_column(String(120))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('store_id','external_reference',name='uq_insurance_direct_reference'),CheckConstraint("amount_cents>0 AND ((purpose='paid' AND original_id IS NULL) OR (purpose='returned' AND original_id IS NOT NULL))",name='ck_insurance_direct'),)
class InsuranceTermination(Proof,StoreScoped,Base):
    __tablename__='insurance_terminations'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('insurance_quotes.id'))
    revision:Mapped[int]=mapped_column(Integer)
    retained_cents:Mapped[int]=mapped_column(BigInteger)
    returns:Mapped[list]=mapped_column(JSON)
    external_result:Mapped[str]=mapped_column(String(20))
    reason:Mapped[str]=mapped_column(String(1000))
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_insurance_termination_revision'),CheckConstraint("retained_cents>=0 AND external_result IN ('terminated','not_issued')",name='ck_insurance_termination'),)
class InsuranceTerminationReview(Proof,StoreScoped,Base):
    __tablename__='insurance_termination_reviews'
    plan_id:Mapped[int]=mapped_column(ForeignKey('insurance_terminations.id'),unique=True)
    decision:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    __table_args__=(CheckConstraint("decision IN ('approved','rejected')",name='ck_insurance_termination_decision'),)
class InsuranceTerminationConsent(Proof,StoreScoped,Base):
    __tablename__='insurance_termination_consents'
    plan_id:Mapped[int]=mapped_column(ForeignKey('insurance_terminations.id'),unique=True)
    digest:Mapped[str]=mapped_column(String(64))
class InsuranceTerminationCancellation(Fact,StoreScoped,Base):
    __tablename__='insurance_termination_cancellations'
    plan_id:Mapped[int]=mapped_column(ForeignKey('insurance_terminations.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
class InsuranceTerminationApplication(Proof,StoreScoped,Base):
    __tablename__='insurance_termination_applications'
    plan_id:Mapped[int]=mapped_column(ForeignKey('insurance_terminations.id'),unique=True)
    business_date:Mapped[date]=mapped_column(Date)
class InsuranceCustomerRefund(Proof,StoreScoped,Base):
    __tablename__='insurance_customer_refunds'
    plan_id:Mapped[int]=mapped_column(ForeignKey('insurance_terminations.id'),index=True)
    original_tender_id:Mapped[int]=mapped_column(ForeignKey('insurance_tenders.id'))
    reversal_tender_id:Mapped[int]=mapped_column(ForeignKey('insurance_tenders.id'),unique=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('amount_cents>0',name='ck_insurance_customer_refund'),)
class InsuranceCommission(Proof,StoreScoped,Base):
    __tablename__='insurance_commissions'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    target_cents:Mapped[int]=mapped_column(BigInteger)
    previous_cents:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(1000))
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_insurance_commission_revision'),CheckConstraint('target_cents>=0 AND previous_cents>=0',name='ck_insurance_commission'),)
class InsuranceCommissionReview(Proof,StoreScoped,Base):
    __tablename__='insurance_commission_reviews'
    confirmation_id:Mapped[int]=mapped_column(ForeignKey('insurance_commissions.id'),unique=True)
    decision:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint("decision IN ('approved','rejected')",name='ck_insurance_commission_review'),)
class InsuranceCommissionPayment(Proof,StoreScoped,Base):
    __tablename__='insurance_commission_payments'
    case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'),index=True)
    confirmation_id:Mapped[int]=mapped_column(ForeignKey('insurance_commissions.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('insurance_commission_payments.id'),nullable=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    direction:Mapped[str]=mapped_column(String(3))
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    reference:Mapped[str]=mapped_column(String(100))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint("amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))",name='ck_insurance_commission_payment'),)
class InsuranceRequest(Fact,StoreScoped,Base):
    __tablename__='insurance_requests'
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_insurance_request'),)

IMMUTABLE=tuple(v for k,v in list(globals().items()) if k.startswith('Insurance') and isinstance(v,type))
@event.listens_for(Session,'before_flush')
def protect_insurance_facts(db,*_):
    if any(isinstance(r,IMMUTABLE) for r in list(db.dirty)+list(db.deleted)):raise HTTPException(409,'保险核价、外部结果和原款账不可覆盖，请追加新版本或原单纠正')
