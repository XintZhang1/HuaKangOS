"""Approved source-capture returns, separate from ordinary pre-delivery reversals."""
from sqlalchemy import String,BigInteger,ForeignKey,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from fastapi import HTTPException
from .db import Base
from .models import StoreScoped
from .flow_models import Versioned


class GroupAftercareHold(Versioned,Base):
    __tablename__='group_aftercare_holds'
    aftercare_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'))
    kind:Mapped[str]=mapped_column(String(20))
    original_id:Mapped[int]=mapped_column(BigInteger)
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    wallet_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_wallets.id'),nullable=True)
    units:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    discount_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    status:Mapped[str]=mapped_column(String(20),default='reserved')
    __table_args__=(UniqueConstraint('plan_id','kind','original_id',name='uq_group_aftercare_origin'),
        CheckConstraint("kind IN ('principal','benefit') AND units>0 AND credit_cents>0 AND discount_cents>=0",name='ck_group_aftercare_hold_value'),
        CheckConstraint("status IN ('reserved','released','applied')",name='ck_group_aftercare_hold_status'))


class GroupAftercarePosting(StoreScoped,Base):
    __tablename__='group_aftercare_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    hold_id:Mapped[int]=mapped_column(ForeignKey('group_aftercare_holds.id'),unique=True)
    kind:Mapped[str]=mapped_column(String(20))
    entry_id:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('kind','entry_id',name='uq_group_aftercare_posting'),
        CheckConstraint("kind IN ('principal','benefit')",name='ck_group_aftercare_posting_kind'))


@event.listens_for(Session,'before_flush')
def protect_group_aftercare(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,(GroupAftercareHold,GroupAftercarePosting)):continue
        if not db.info.get('_group_aftercare_authority'):raise HTTPException(403,'原核销退回只可由已授权售后方案办理')
        if isinstance(row,GroupAftercarePosting) and row not in db.new:raise HTTPException(409,'原核销退回事实不可改写')
        if isinstance(row,GroupAftercareHold) and row not in db.new:
            frozen=('aftercare_case_id','source_case_id','plan_id','kind','original_id','member_id','wallet_id','units','credit_cents','discount_cents','evidence_id')
            if row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen):raise HTTPException(409,'已批准的原核销退回额度不可改写')
