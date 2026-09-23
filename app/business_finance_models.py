"""Store business finance: immutable source allocations, no accounting general ledger."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,BigInteger,Date,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class FinanceOrder(Versioned,Base):
    __tablename__='business_finance_orders'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    purpose:Mapped[str]=mapped_column(String(30))
    values:Mapped[dict]=mapped_column(JSON)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='draft')
    __table_args__=(CheckConstraint("purpose IN ('advance','advance_apply','advance_refund','statement','correction','stored_correction','fee_correction','other_return','other_return_adjust','other_return_refund')",name='ck_finance_order_purpose'),
        CheckConstraint("status IN ('draft','approved','completed','cancelled','superseded')",name='ck_finance_order_status'))


class FinanceAdvance(Versioned,Base):
    __tablename__='business_finance_advances'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    customer_id:Mapped[int]=mapped_column(ForeignKey('flow_customers.id'),index=True)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    initial_cents:Mapped[int]=mapped_column(BigInteger)
    correction_cents:Mapped[int]=mapped_column(BigInteger,default=0,server_default='0')
    balance_cents:Mapped[int]=mapped_column(BigInteger)
    reserved_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    __table_args__=(CheckConstraint('initial_cents>0 AND 0<=reserved_cents AND reserved_cents<=balance_cents AND balance_cents<=initial_cents+correction_cents',name='ck_finance_advance_available'),)


class FinanceAdvanceEntry(StoreScoped,Base):
    __tablename__='business_finance_advance_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    advance_id:Mapped[int]=mapped_column(ForeignKey('business_finance_advances.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    purpose:Mapped[str]=mapped_column(String(20))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_advance_entries.id'),nullable=True)
    cash_id:Mapped[int|None]=mapped_column(ForeignKey('cash_entries.id'),nullable=True,unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("(purpose IN ('receive','return') AND amount_cents>0) OR (purpose IN ('apply','refund') AND amount_cents<0) OR (purpose='correction' AND amount_cents!=0)",name='ck_finance_advance_entry'),)


class FinanceApplication(Versioned,Base):
    __tablename__='business_finance_applications'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    advance_id:Mapped[int]=mapped_column(ForeignKey('business_finance_advances.id'),index=True)
    target_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    kind:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(20),default='requested')
    __table_args__=(CheckConstraint("kind IN ('apply','refund') AND amount_cents>0",name='ck_finance_application_value'),
        CheckConstraint("status IN ('requested','reserved','applied','released')",name='ck_finance_application_status'))


class FinanceCreditLink(StoreScoped,Base):
    __tablename__='business_finance_credit_links'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    entry_id:Mapped[int]=mapped_column(ForeignKey('business_finance_advance_entries.id'),unique=True)
    application_id:Mapped[int]=mapped_column(ForeignKey('business_finance_applications.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_credit_links.id'),nullable=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('amount_cents!=0',name='ck_finance_credit_nonzero'),)


class FinanceStatement(StoreScoped,Base):
    __tablename__='business_finance_statements'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    customer_id:Mapped[int]=mapped_column(ForeignKey('flow_customers.id'))
    starts_on:Mapped[date]=mapped_column(Date)
    ends_on:Mapped[date]=mapped_column(Date)
    revision:Mapped[int]=mapped_column(BigInteger)
    previous_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_statements.id'),nullable=True,unique=True)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('store_id','customer_id','starts_on','ends_on','revision',name='uq_finance_statement_version'),
        CheckConstraint('starts_on<=ends_on AND revision>0',name='ck_finance_statement_period'))


class FinanceStatementLine(StoreScoped,Base):
    __tablename__='business_finance_statement_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    statement_id:Mapped[int]=mapped_column(ForeignKey('business_finance_statements.id'),index=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    snapshot:Mapped[dict]=mapped_column(JSON)
    due_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('statement_id','source_case_id',name='uq_finance_statement_source'),CheckConstraint('due_cents>0',name='ck_finance_statement_due'))


class FinanceCashBatch(StoreScoped,Base):
    __tablename__='business_finance_cash_batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    kind:Mapped[str]=mapped_column(String(30))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("kind IN ('collection','correction_reverse','correction_record','supplier_refund') AND amount_cents>0",name='ck_finance_cash_batch'),)


class FinanceCashAllocation(StoreScoped,Base):
    __tablename__='business_finance_cash_allocations'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('business_finance_cash_batches.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),unique=True)
    statement_line_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_statement_lines.id'),nullable=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('amount_cents>0',name='ck_finance_cash_allocation'),)


class FinanceCorrection(StoreScoped,Base):
    __tablename__='business_finance_corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    reversing_batch_id:Mapped[int]=mapped_column(ForeignKey('business_finance_cash_batches.id'),unique=True)
    corrected_batch_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_cash_batches.id'),unique=True,nullable=True)


class FinanceCorrectionBasis(StoreScoped,Base):
    """Version two separates gross original cash from already refunded slices."""
    __tablename__='business_finance_correction_bases'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),index=True)
    previous_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_correction_bases.id'),nullable=True)
    original_amount_cents:Mapped[int]=mapped_column(BigInteger)
    corrected_amount_cents:Mapped[int]=mapped_column(BigInteger)
    refunded_cents:Mapped[int]=mapped_column(BigInteger)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('original_amount_cents>=refunded_cents AND corrected_amount_cents>=refunded_cents AND refunded_cents>0',name='ck_finance_correction_basis'),)


class FinanceCorrectionRefundSlice(StoreScoped,Base):
    __tablename__='business_finance_correction_refund_slices'
    id:Mapped[int]=mapped_column(primary_key=True)
    basis_id:Mapped[int]=mapped_column(ForeignKey('business_finance_correction_bases.id'),index=True)
    refund_payment_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'))
    original_payment_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'))
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('basis_id','refund_payment_id',name='uq_finance_correction_refund_slice'),CheckConstraint('amount_cents>0',name='ck_finance_correction_refund_slice'))


class FinanceStoredCorrectionRequest(Versioned,Base):
    __tablename__='business_finance_stored_correction_requests'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    source_kind:Mapped[str]=mapped_column(String(20))
    advance_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_advances.id'),nullable=True,index=True)
    member_id:Mapped[int|None]=mapped_column(ForeignKey('group_members.id'),nullable=True,index=True)
    topup_id:Mapped[int|None]=mapped_column(ForeignKey('group_entries.id'),nullable=True,index=True)
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'))
    original_amount_cents:Mapped[int]=mapped_column(BigInteger)
    corrected_amount_cents:Mapped[int]=mapped_column(BigInteger)
    reserved_cents:Mapped[int]=mapped_column(BigInteger)
    status:Mapped[str]=mapped_column(String(20),default='requested')
    __table_args__=(CheckConstraint("(source_kind='advance' AND advance_id IS NOT NULL AND member_id IS NULL AND topup_id IS NULL) OR (source_kind='member' AND advance_id IS NULL AND member_id IS NOT NULL AND topup_id IS NOT NULL)",name='ck_finance_stored_source'),
        CheckConstraint('original_amount_cents>0 AND corrected_amount_cents>=0 AND reserved_cents>=0',name='ck_finance_stored_amount'),
        CheckConstraint("status IN ('requested','reserved','applied','released')",name='ck_finance_stored_status'))


class FinanceStoredCorrection(StoreScoped,Base):
    __tablename__='business_finance_stored_corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('business_finance_stored_correction_requests.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    reversing_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    corrected_cash_id:Mapped[int|None]=mapped_column(ForeignKey('cash_entries.id'),unique=True,nullable=True)
    advance_entry_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_advance_entries.id'),unique=True,nullable=True)
    group_entry_id:Mapped[int|None]=mapped_column(ForeignKey('group_entries.id'),unique=True,nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class FinanceReturnTargetRevision(StoreScoped,Base):
    __tablename__='business_finance_return_target_revisions'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    receivable_id:Mapped[int]=mapped_column(ForeignKey('business_finance_return_receivables.id'),index=True)
    revision:Mapped[int]=mapped_column(BigInteger)
    previous_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_return_target_revisions.id'),unique=True,nullable=True)
    original_amount_cents:Mapped[int]=mapped_column(BigInteger)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    received_cents:Mapped[int]=mapped_column(BigInteger)
    received_payment_ids:Mapped[list]=mapped_column(JSON)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('receivable_id','revision',name='uq_finance_return_target_revision'),
        CheckConstraint('revision>0 AND original_amount_cents>=0 AND amount_cents>=0 AND received_cents>=0',name='ck_finance_return_target_amount'))


class FinanceSupplierRefund(Versioned,Base):
    __tablename__='business_finance_supplier_refunds'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    receivable_id:Mapped[int]=mapped_column(ForeignKey('business_finance_return_receivables.id'),index=True)
    original_payment_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    status:Mapped[str]=mapped_column(String(20),default='requested')
    applied_batch_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_cash_batches.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint("amount_cents>0 AND status IN ('requested','reserved','applied','released')",name='ck_finance_supplier_refund_status'),
        CheckConstraint("(status='applied' AND applied_batch_id IS NOT NULL) OR (status!='applied' AND applied_batch_id IS NULL)",name='ck_finance_supplier_refund_applied'))


class FinanceBundleCorrection(StoreScoped,Base):
    __tablename__='business_finance_bundle_corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('business_finance_stored_correction_requests.id'),unique=True)
    purchase_id:Mapped[int]=mapped_column(ForeignKey('recharge_bundle_purchases.id'),index=True)
    rule_id:Mapped[int]=mapped_column(ForeignKey('recharge_bundle_rules.id'))
    original_shares:Mapped[int]=mapped_column(BigInteger)
    corrected_shares:Mapped[int]=mapped_column(BigInteger)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('original_shares>0 AND corrected_shares>=0',name='ck_finance_bundle_correction_shares'),)


class FinanceBundleCorrectionComponent(StoreScoped,Base):
    __tablename__='business_finance_bundle_correction_components'
    id:Mapped[int]=mapped_column(primary_key=True)
    correction_id:Mapped[int]=mapped_column(ForeignKey('business_finance_bundle_corrections.id'),index=True)
    component_id:Mapped[int]=mapped_column(ForeignKey('recharge_bundle_components.id'))
    wallet_id:Mapped[int]=mapped_column(ForeignKey('benefit_wallets.id'))
    grant_entry_id:Mapped[int]=mapped_column(ForeignKey('benefit_entries.id'))
    units_per_share:Mapped[int]=mapped_column(BigInteger)
    delta_units:Mapped[int]=mapped_column(BigInteger)
    expires_on:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('correction_id','component_id',name='uq_finance_bundle_correction_component'),CheckConstraint('units_per_share>0',name='ck_finance_bundle_correction_units'))


class FinanceBundleCorrectionPosting(StoreScoped,Base):
    __tablename__='business_finance_bundle_correction_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    component_id:Mapped[int]=mapped_column(ForeignKey('business_finance_bundle_correction_components.id'),unique=True)
    benefit_entry_id:Mapped[int]=mapped_column(ForeignKey('benefit_entries.id'),unique=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class FinanceReturnReceivable(StoreScoped,Base):
    __tablename__='business_finance_return_receivables'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    supplier_id:Mapped[int]=mapped_column(ForeignKey('master_suppliers.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    approved_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint('amount_cents>0 AND quantity_milli>0 AND value_cents>=0',name='ck_finance_return_receivable'),)


class FinanceAdvanceReturn(Versioned,Base):
    __tablename__='business_finance_advance_returns'
    aftercare_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'))
    original_credit_id:Mapped[int]=mapped_column(ForeignKey('business_finance_credit_links.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    status:Mapped[str]=mapped_column(String(20),default='reserved')
    returned_credit_id:Mapped[int|None]=mapped_column(ForeignKey('business_finance_credit_links.id'),nullable=True,unique=True)
    __table_args__=(UniqueConstraint('plan_id','original_credit_id',name='uq_finance_advance_return'),
        CheckConstraint("amount_cents>0 AND status IN ('reserved','applied','released')",name='ck_finance_advance_return'))


class FinanceEvent(StoreScoped,Base):
    __tablename__='business_finance_events'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(40))
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    detail:Mapped[dict]=mapped_column(JSON,default=dict)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class FinanceReceipt(StoreScoped,Base):
    __tablename__='business_finance_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_business_finance_request'),)


IMMUTABLE=(FinanceAdvanceEntry,FinanceCreditLink,FinanceStatement,FinanceStatementLine,FinanceCashBatch,FinanceCashAllocation,FinanceCorrection,FinanceCorrectionBasis,FinanceCorrectionRefundSlice,FinanceReturnReceivable,FinanceStoredCorrection,FinanceReturnTargetRevision,FinanceBundleCorrection,FinanceBundleCorrectionComponent,FinanceBundleCorrectionPosting,FinanceEvent,FinanceReceipt)
FROZEN={FinanceOrder:('case_id','purpose','values','requested_by'),FinanceAdvance:('case_id','customer_id','cash_id','account_id','initial_cents'),
    FinanceSupplierRefund:('case_id','receivable_id','original_payment_id','amount_cents'),
    FinanceStoredCorrectionRequest:('case_id','source_kind','advance_id','member_id','topup_id','original_cash_id','original_amount_cents','corrected_amount_cents','reserved_cents'),
    FinanceApplication:('case_id','advance_id','target_case_id','amount_cents','kind'),FinanceAdvanceReturn:('aftercare_case_id','source_case_id','plan_id','original_credit_id','amount_cents')}

@event.listens_for(Session,'before_flush')
def protect_finance(db,*_):
    from .flow_models import PaymentLink
    from .business_finance_partial_corrections import guard_refund
    for payment in list(db.new):
        if isinstance(payment,PaymentLink) and payment.direction=='out':guard_refund(db,payment.original_id)
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,(*IMMUTABLE,*FROZEN)):continue
        if not db.info.get('_business_finance_authority'):raise HTTPException(403,'业务财务只能通过本店授权动作办理')
        if row in db.new:continue
        if isinstance(row,IMMUTABLE) or row in db.deleted:raise HTTPException(409,'原现金、抵用、账单和更正依据不得覆盖')
        for model,columns in FROZEN.items():
            if isinstance(row,model) and any(inspect(row).attrs[k].history.has_changes() for k in columns):raise HTTPException(409,'已提交财务申请的原始内容不可改写')
