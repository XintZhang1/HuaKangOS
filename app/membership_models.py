"""Group membership lifecycle and attributable earned-points facts."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Boolean,Date,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,Index,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .group_models import GroupProtected,CentralVersioned


class MembershipRule(GroupProtected,Base):
    __tablename__='membership_rules'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40))
    rule_version:Mapped[int]=mapped_column(Integer)
    name:Mapped[str]=mapped_column(String(100))
    enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    allowed_store_ids:Mapped[list]=mapped_column(JSON)
    validity_months:Mapped[int]=mapped_column(Integer)
    fee_cents:Mapped[int]=mapped_column(BigInteger)
    fee_owner:Mapped[str]=mapped_column(String(30))
    refund_policy:Mapped[str]=mapped_column(String(30))
    points_enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    points_numerator:Mapped[int]=mapped_column(BigInteger)
    points_denominator_fen:Mapped[int]=mapped_column(BigInteger)
    points_benefit_rule_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_rules.id'),nullable=True)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('code','rule_version',name='uq_membership_rule_version'),
        CheckConstraint("rule_version>0 AND validity_months BETWEEN 1 AND 120 AND fee_cents>=0 AND points_numerator>0 AND points_denominator_fen>0",name='ck_membership_rule_values'),
        CheckConstraint("fee_owner='collecting_store' AND refund_policy IN ('none','before_start')",name='ck_membership_rule_policy'),
        CheckConstraint('NOT points_enabled OR points_benefit_rule_id IS NOT NULL',name='ck_membership_rule_points'))


class MembershipOrder(Versioned,Base):
    __tablename__='membership_orders'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    purpose:Mapped[str]=mapped_column(String(30))
    values:Mapped[dict]=mapped_column(JSON)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='draft')
    __table_args__=(CheckConstraint("purpose IN ('topup','benefit_issue','card_issue','card_loss','card_replace','renew','tier_change','renew_refund','points_adjust')",name='ck_membership_order_purpose'),
        CheckConstraint("status IN ('draft','review','approved','completed','cancelled')",name='ck_membership_order_status'))


class MembershipCard(CentralVersioned,Base):
    __tablename__='membership_cards'
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    number:Mapped[str]=mapped_column(String(40),unique=True)
    generation:Mapped[int]=mapped_column(Integer)
    previous_id:Mapped[int|None]=mapped_column(ForeignKey('membership_cards.id'),nullable=True,unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    issuer_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    status:Mapped[str]=mapped_column(String(20),default='active')
    __table_args__=(UniqueConstraint('member_id','generation',name='uq_membership_card_generation'),
        CheckConstraint("generation>0 AND status IN ('active','lost','replaced')",name='ck_membership_card_status'),
        Index('uq_membership_active_card','member_id',unique=True,sqlite_where=(status=='active'),postgresql_where=(status=='active')))


class MembershipPeriod(GroupProtected,Base):
    __tablename__='membership_periods'
    id:Mapped[int]=mapped_column(primary_key=True)
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    rule_id:Mapped[int]=mapped_column(ForeignKey('membership_rules.id'))
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    starts_on:Mapped[date]=mapped_column(Date)
    ends_on:Mapped[date]=mapped_column(Date)
    kind:Mapped[str]=mapped_column(String(20))
    __table_args__=(CheckConstraint("starts_on<=ends_on AND kind IN ('renew','tier_change')",name='ck_membership_period'),)


class MembershipPeriodVoid(GroupProtected,Base):
    __tablename__='membership_period_voids'
    id:Mapped[int]=mapped_column(primary_key=True)
    period_id:Mapped[int]=mapped_column(ForeignKey('membership_periods.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))


class MembershipFee(StoreScoped,Base):
    __tablename__='membership_fees'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    period_id:Mapped[int]=mapped_column(ForeignKey('membership_periods.id'))
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    reference:Mapped[str]=mapped_column(String(100))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('membership_fees.id'),nullable=True,unique=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('store_id','account_id','reference',name='uq_membership_fee_reference'),
        CheckConstraint('(original_id IS NULL AND amount_cents>0) OR (original_id IS NOT NULL AND amount_cents<0)',name='ck_membership_fee_sign'))


class MembershipEvent(StoreScoped,Base):
    __tablename__='membership_events'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(40))
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    detail:Mapped[dict]=mapped_column(JSON)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class PointsClaim(CentralVersioned,Base):
    __tablename__='membership_points_claims'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    member_id:Mapped[int|None]=mapped_column(ForeignKey('group_members.id'),nullable=True)
    rule_id:Mapped[int|None]=mapped_column(ForeignKey('membership_rules.id'),nullable=True)
    basis_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    target_units:Mapped[int]=mapped_column(BigInteger,default=0)
    __table_args__=(CheckConstraint('basis_cents>=0 AND target_units>=0',name='ck_membership_points_claim'),)


class PointsChange(GroupProtected,Base):
    __tablename__='membership_points_changes'
    id:Mapped[int]=mapped_column(primary_key=True)
    claim_id:Mapped[int]=mapped_column(ForeignKey('membership_points_claims.id'))
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    units:Mapped[int]=mapped_column(BigInteger)
    basis_cents:Mapped[int]=mapped_column(BigInteger)
    wallet_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_wallets.id'),nullable=True,unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('units!=0 AND basis_cents>=0',name='ck_membership_points_change'),)


class PointsRecovery(GroupProtected,Base):
    __tablename__='membership_points_recoveries'
    id:Mapped[int]=mapped_column(primary_key=True)
    change_id:Mapped[int]=mapped_column(ForeignKey('membership_points_changes.id'))
    benefit_entry_id:Mapped[int]=mapped_column(ForeignKey('benefit_entries.id'),unique=True)
    units:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('units>0',name='ck_membership_points_recovery'),)


class PointsDebt(GroupProtected,Base):
    __tablename__='membership_points_debts'
    id:Mapped[int]=mapped_column(primary_key=True)
    change_id:Mapped[int]=mapped_column(ForeignKey('membership_points_changes.id'),unique=True)
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    units:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('units>0',name='ck_membership_points_debt'),)


class PointsDebtPayment(GroupProtected,Base):
    __tablename__='membership_points_debt_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    debt_id:Mapped[int]=mapped_column(ForeignKey('membership_points_debts.id'))
    benefit_entry_id:Mapped[int]=mapped_column(ForeignKey('benefit_entries.id'),unique=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    units:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint('units>0',name='ck_membership_points_debt_payment'),)


@event.listens_for(Session,'before_flush')
def protect_membership(db,*_):
    immutable=(MembershipRule,MembershipPeriod,MembershipPeriodVoid,MembershipFee,MembershipEvent,PointsChange,PointsRecovery,PointsDebt,PointsDebtPayment)
    mutable={MembershipOrder:('case_id','member_id','purpose','values','requested_by'),
        MembershipCard:('member_id','number','generation','previous_id','case_id','issuer_store_id'),
        PointsClaim:('case_id','store_id','member_id','rule_id')}
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,(*immutable,*mutable)) and not db.info.get('_group_authority'):
            raise HTTPException(403,'会员卡、有效期和消费积分须通过集团服务办理')
        if row in db.dirty or row in db.deleted:
            if isinstance(row,immutable):raise HTTPException(409,'会员规则与原始账本不可覆盖，请追加关联原单的记录')
            for cls,fields in mutable.items():
                if isinstance(row,cls) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in fields)):
                    raise HTTPException(409,'会员业务来源及冻结规则不可更改')
