"""Append-only same-amount fee recording corrections, never member entitlements."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,BigInteger,Date,DateTime,ForeignKey,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class MembershipFeeCorrectionRequest(Versioned,Base):
    __tablename__='membership_fee_correction_requests'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    fee_id:Mapped[int]=mapped_column(ForeignKey('membership_fees.id'),index=True)
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'))
    original_account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    reference:Mapped[str]=mapped_column(String(100))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    source_version:Mapped[int]=mapped_column(BigInteger)
    refunded_fee_id:Mapped[int|None]=mapped_column(ForeignKey('membership_fees.id'),nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='requested')
    __table_args__=(CheckConstraint('amount_cents>0 AND source_version>0',name='ck_member_fee_correction_amount'),
        CheckConstraint("status IN ('requested','reserved','applied','released')",name='ck_member_fee_correction_status'))


class MembershipFeeCorrection(StoreScoped,Base):
    __tablename__='membership_fee_corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('membership_fee_correction_requests.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    fee_id:Mapped[int]=mapped_column(ForeignKey('membership_fees.id'),index=True)
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    reversing_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    corrected_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class MembershipFeeRefundBasis(StoreScoped,Base):
    __tablename__='membership_fee_refund_bases'
    id:Mapped[int]=mapped_column(primary_key=True)
    refund_fee_id:Mapped[int]=mapped_column(ForeignKey('membership_fees.id'),unique=True)
    original_fee_id:Mapped[int]=mapped_column(ForeignKey('membership_fees.id'))
    original_cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


@event.listens_for(Session,'before_flush')
def protect_fee_corrections(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,(MembershipFeeCorrectionRequest,MembershipFeeCorrection,MembershipFeeRefundBasis)):continue
        authority=db.info.get('_group_authority') if isinstance(row,MembershipFeeRefundBasis) else db.info.get('_business_finance_authority')
        if not authority:raise HTTPException(403,'续会费原款只能通过本店授权动作更正')
        if row in db.new:continue
        if not isinstance(row,MembershipFeeCorrectionRequest) or row in db.deleted:raise HTTPException(409,'续会费原款更正和退款依据不能覆盖')
        frozen=[c.name for c in row.__table__.columns if c.name not in {'status','version','updated_at'}]
        if any(inspect(row).attrs[k].history.has_changes() for k in frozen):raise HTTPException(409,'已提交续会费更正内容不能改写')
