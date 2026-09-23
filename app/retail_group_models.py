"""Native retail/group domain with immutable original sources and scoped writes. No existing rule or wallet is relabelled.

Central eligibility contains only approved product scopes. Store cases, source
files, allocations and original-return liabilities remain tenant scoped.
"""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, BigInteger, Integer, Boolean, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .group_models import GroupProtected


class RetailGroupEligibility(GroupProtected, Base):
    __tablename__='retail_group_eligibility'
    id:Mapped[int]=mapped_column(primary_key=True)
    rule_id:Mapped[int]=mapped_column(ForeignKey('benefit_rules.id'),unique=True)
    issuer_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    partial_return_mode:Mapped[str]=mapped_column(String(40))
    expiry_mode:Mapped[str]=mapped_column(String(40))
    pending_claim_expiry:Mapped[str]=mapped_column(String(20))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("partial_return_mode='accumulate_original_unit' AND expiry_mode='original_expiry' AND pending_claim_expiry='none'",name='ck_retail_group_modes'),)


class RetailGroupScope(GroupProtected, Base):
    __tablename__='retail_group_scopes'
    id:Mapped[int]=mapped_column(primary_key=True)
    eligibility_id:Mapped[int]=mapped_column(ForeignKey('retail_group_eligibility.id'),index=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'))
    component:Mapped[str]=mapped_column(String(20))
    work_item_id:Mapped[int|None]=mapped_column(ForeignKey('master_work_items.id'),nullable=True)
    sku:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    work_code:Mapped[str]=mapped_column(String(60),default='')
    __table_args__=(UniqueConstraint('eligibility_id','store_id','item_id','component',name='uq_retail_group_scope'),
        CheckConstraint("(component='goods' AND work_item_id IS NULL) OR (component='installation' AND work_item_id IS NOT NULL)",name='ck_retail_group_scope'),)


class RetailGroupDecision(GroupProtected, Base):
    __tablename__='retail_group_decisions'
    id:Mapped[int]=mapped_column(primary_key=True)
    eligibility_id:Mapped[int]=mapped_column(ForeignKey('retail_group_eligibility.id'),unique=True)
    approved:Mapped[bool]=mapped_column(Boolean)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RetailGroupWallet(GroupProtected, Base):
    __tablename__='retail_group_wallets'
    id:Mapped[int]=mapped_column(primary_key=True)
    wallet_id:Mapped[int]=mapped_column(ForeignKey('benefit_wallets.id'),unique=True)
    eligibility_id:Mapped[int]=mapped_column(ForeignKey('retail_group_eligibility.id'))
    decision_id:Mapped[int]=mapped_column(ForeignKey('retail_group_decisions.id'))
    origin_id:Mapped[int]=mapped_column(ForeignKey('benefit_entries.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RetailGroupPlan(Versioned, Base):
    __tablename__='retail_group_plans'
    case_id:Mapped[int]=mapped_column(ForeignKey('retail_orders.id'),unique=True)
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest:Mapped[str]=mapped_column(String(64))


class RetailGroupTender(StoreScoped, Base):
    __tablename__='retail_group_tenders'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('retail_group_plans.id'),index=True)
    sequence:Mapped[int]=mapped_column(Integer)
    kind:Mapped[str]=mapped_column(String(20))
    wallet_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_wallets.id'),nullable=True)
    eligibility_id:Mapped[int|None]=mapped_column(ForeignKey('retail_group_eligibility.id'),nullable=True)
    units:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    consideration_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    expires_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    __table_args__=(UniqueConstraint('plan_id','sequence',name='uq_retail_group_tender'),
        CheckConstraint("kind IN ('cash','principal','bonus','coupon','package') AND sequence>0 AND units>0 AND credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents",name='ck_retail_group_tender_value'),
        CheckConstraint("(kind IN ('cash','principal') AND wallet_id IS NULL AND eligibility_id IS NULL AND expires_on IS NULL) OR (kind IN ('bonus','coupon','package') AND wallet_id IS NOT NULL AND eligibility_id IS NOT NULL AND expires_on IS NOT NULL)",name='ck_retail_group_tender_source'))


class RetailGroupUnit(StoreScoped, Base):
    __tablename__='retail_group_units'
    id:Mapped[int]=mapped_column(primary_key=True)
    tender_id:Mapped[int]=mapped_column(ForeignKey('retail_group_tenders.id'),index=True)
    sequence:Mapped[int]=mapped_column(Integer)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    consideration_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('tender_id','sequence',name='uq_retail_group_unit'),
        CheckConstraint('sequence>0 AND credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents',name='ck_retail_group_unit'))


class RetailGroupAllocation(StoreScoped, Base):
    __tablename__='retail_group_allocations'
    id:Mapped[int]=mapped_column(primary_key=True)
    unit_id:Mapped[int]=mapped_column(ForeignKey('retail_group_units.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('retail_lines.id'),index=True)
    component:Mapped[str]=mapped_column(String(20))
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    consideration_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('unit_id','line_id','component',name='uq_retail_group_allocation'),
        CheckConstraint("component IN ('goods','installation') AND credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents",name='ck_retail_group_allocation'))


class RetailGroupReservation(StoreScoped, Base):
    __tablename__='retail_group_reservations'
    id:Mapped[int]=mapped_column(primary_key=True)
    tender_id:Mapped[int]=mapped_column(ForeignKey('retail_group_tenders.id'),index=True)
    principal_id:Mapped[int|None]=mapped_column(ForeignKey('group_reservations.id'),nullable=True,unique=True)
    benefit_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_reservations.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint('(principal_id IS NOT NULL AND benefit_id IS NULL) OR (principal_id IS NULL AND benefit_id IS NOT NULL)',name='ck_retail_group_reservation_source'),)


class RetailGroupCapture(StoreScoped, Base):
    __tablename__='retail_group_captures'
    id:Mapped[int]=mapped_column(primary_key=True)
    tender_id:Mapped[int]=mapped_column(ForeignKey('retail_group_tenders.id'),unique=True)
    reservation_id:Mapped[int]=mapped_column(ForeignKey('retail_group_reservations.id'),unique=True)
    principal_id:Mapped[int|None]=mapped_column(ForeignKey('group_entries.id'),nullable=True,unique=True)
    benefit_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_entries.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint('(principal_id IS NOT NULL AND benefit_id IS NULL) OR (principal_id IS NULL AND benefit_id IS NOT NULL)',name='ck_retail_group_capture_source'),)


class RetailGroupClosure(StoreScoped, Base):
    __tablename__='retail_group_closures'
    id:Mapped[int]=mapped_column(primary_key=True)
    tender_id:Mapped[int]=mapped_column(ForeignKey('retail_group_tenders.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RetailGroupReturn(StoreScoped, Base):
    __tablename__='retail_group_returns'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('retail_group_plans.id'),index=True)
    posting_id:Mapped[int]=mapped_column(ForeignKey('retail_return_postings.id'),unique=True)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class RetailGroupReturnPart(StoreScoped, Base):
    __tablename__='retail_group_return_parts'
    id:Mapped[int]=mapped_column(primary_key=True)
    return_id:Mapped[int]=mapped_column(ForeignKey('retail_group_returns.id'),index=True)
    allocation_id:Mapped[int]=mapped_column(ForeignKey('retail_group_allocations.id'),index=True)
    capture_id:Mapped[int|None]=mapped_column(ForeignKey('retail_group_captures.id'),nullable=True)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    consideration_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('return_id','allocation_id',name='uq_retail_group_return_part'),
        CheckConstraint('credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents',name='ck_retail_group_return_part'))


class RetailGroupRestore(StoreScoped, Base):
    __tablename__='retail_group_restores'
    id:Mapped[int]=mapped_column(primary_key=True)
    unit_id:Mapped[int]=mapped_column(ForeignKey('retail_group_units.id'),index=True)
    capture_id:Mapped[int]=mapped_column(ForeignKey('retail_group_captures.id'))
    principal_id:Mapped[int|None]=mapped_column(ForeignKey('group_entries.id'),nullable=True,unique=True)
    benefit_id:Mapped[int|None]=mapped_column(ForeignKey('benefit_entries.id'),nullable=True,unique=True)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    consideration_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('(principal_id IS NOT NULL AND benefit_id IS NULL) OR (principal_id IS NULL AND benefit_id IS NOT NULL)',name='ck_retail_group_restore_source'),
        CheckConstraint('credit_cents>0 AND consideration_cents>=0 AND consideration_cents<=credit_cents AND settlement_cents>=0 AND settlement_cents<=credit_cents',name='ck_retail_group_restore_value'))


class RetailGroupSettlement(StoreScoped, Base):
    __tablename__='retail_group_settlements'
    id:Mapped[int]=mapped_column(primary_key=True)
    return_part_id:Mapped[int|None]=mapped_column(ForeignKey('retail_group_return_parts.id'),nullable=True)
    restore_id:Mapped[int|None]=mapped_column(ForeignKey('retail_group_restores.id'),nullable=True)
    side:Mapped[str]=mapped_column(String(10))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('return_part_id','side',name='uq_retail_group_return_settlement'),
        UniqueConstraint('restore_id','side',name='uq_retail_group_restore_settlement'),
        CheckConstraint("side IN ('center','store') AND amount_cents!=0 AND ((return_part_id IS NOT NULL AND restore_id IS NULL) OR (return_part_id IS NULL AND restore_id IS NOT NULL))",name='ck_retail_group_settlement'))


class RetailGroupCashAllocation(StoreScoped, Base):
    __tablename__='retail_group_cash_allocations'
    id:Mapped[int]=mapped_column(primary_key=True)
    allocation_id:Mapped[int]=mapped_column(ForeignKey('retail_group_allocations.id'),index=True)
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('retail_group_cash_allocations.id'),nullable=True)
    __table_args__=(UniqueConstraint('allocation_id','payment_link_id','original_id',name='uq_retail_group_cash_allocation'),
        CheckConstraint('(amount_cents>0 AND original_id IS NULL) OR (amount_cents<0 AND original_id IS NOT NULL)',name='ck_retail_group_cash_allocation'))


IMMUTABLE=(RetailGroupEligibility,RetailGroupScope,RetailGroupDecision,RetailGroupWallet,RetailGroupTender,RetailGroupUnit,RetailGroupAllocation,
    RetailGroupReservation,RetailGroupCapture,RetailGroupClosure,RetailGroupReturn,RetailGroupReturnPart,RetailGroupRestore,RetailGroupSettlement,RetailGroupCashAllocation)


@event.listens_for(Session,'before_flush')
def protect_retail_group(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,IMMUTABLE+(RetailGroupPlan,)):continue
        if not db.info.get('_retail_group_authority'):
            raise HTTPException(403,'精品集团支付须经原单专用服务校验')
        if isinstance(row,IMMUTABLE) and row not in db.new:
            raise HTTPException(409,'商品适用规则、原支付分摊和原退负债不可覆盖')
        if isinstance(row,RetailGroupPlan) and row not in db.new:
            from sqlalchemy import inspect
            if row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','member_id','evidence_id','actor_id','digest')):
                raise HTTPException(409,'原精品支付授权不可覆盖')
