"""Explicit store price authority and immutable membership quotation provenance."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Boolean,Date,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped

class Fact:
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class MemberPricingRule(Fact,StoreScoped,Base):
    __tablename__='member_pricing_rules'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    code:Mapped[str]=mapped_column(String(40))
    rule_version:Mapped[int]=mapped_column(Integer)
    name:Mapped[str]=mapped_column(String(120))
    enabled:Mapped[bool]=mapped_column(Boolean)
    membership_rule_id:Mapped[int]=mapped_column(ForeignKey('membership_rules.id'))
    membership_snapshot:Mapped[dict]=mapped_column(JSON)
    reference_tier_id:Mapped[int|None]=mapped_column(ForeignKey('master_member_tiers.id'),nullable=True)
    reference_tier_snapshot:Mapped[dict]=mapped_column(JSON)
    starts_on:Mapped[date]=mapped_column(Date)
    ends_on:Mapped[date]=mapped_column(Date)
    stack_mode:Mapped[str]=mapped_column(String(30))
    reason:Mapped[str]=mapped_column(String(1000))
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('store_id','code','rule_version',name='uq_member_price_rule_version'),CheckConstraint("rule_version>0 AND starts_on<=ends_on AND stack_mode IN ('member_then_benefits','exclusive_benefits')",name='ck_member_price_rule'),)

class MemberPricingScope(StoreScoped,Base):
    __tablename__='member_pricing_scopes'
    id:Mapped[int]=mapped_column(primary_key=True)
    rule_id:Mapped[int]=mapped_column(ForeignKey('member_pricing_rules.id'),index=True)
    sequence:Mapped[int]=mapped_column(Integer)
    business_kind:Mapped[str]=mapped_column(String(12))
    component:Mapped[str]=mapped_column(String(20))
    source_id:Mapped[int]=mapped_column(Integer)
    source_snapshot:Mapped[dict]=mapped_column(JSON)
    basis_points:Mapped[int]=mapped_column(Integer)
    bundle_rule_id:Mapped[int|None]=mapped_column(ForeignKey('retail_bundle_rules.id'),nullable=True)
    bundle_snapshot:Mapped[dict]=mapped_column(JSON)
    allow_contract_pricing:Mapped[bool]=mapped_column(Boolean,default=False)
    __table_args__=(UniqueConstraint('rule_id','sequence',name='uq_member_price_scope_sequence'),CheckConstraint("sequence>0 AND basis_points BETWEEN 1 AND 10000 AND ((business_kind='repair' AND component IN ('work','part')) OR (business_kind IN ('retail','addon') AND component IN ('goods','installation')))",name='ck_member_price_scope'),)

class MemberPricingDecision(Fact,StoreScoped,Base):
    __tablename__='member_pricing_decisions'
    rule_id:Mapped[int]=mapped_column(ForeignKey('member_pricing_rules.id'),index=True)
    decision:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    __table_args__=(UniqueConstraint('rule_id','decision',name='uq_member_price_decision'),CheckConstraint("decision IN ('submitted','approved','rejected','cancelled') AND (decision='cancelled' OR evidence_id IS NOT NULL)",name='ck_member_price_decision'),)

class MemberPricingSnapshot(Fact,StoreScoped,Base):
    __tablename__='member_pricing_snapshots'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    quote_kind:Mapped[str]=mapped_column(String(12))
    quote_id:Mapped[int]=mapped_column(Integer)
    rule_id:Mapped[int]=mapped_column(ForeignKey('member_pricing_rules.id'))
    customer_id:Mapped[int]=mapped_column(ForeignKey('flow_customers.id'))
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'))
    period_id:Mapped[int]=mapped_column(ForeignKey('membership_periods.id'))
    definition_version:Mapped[int]=mapped_column(Integer,default=1)
    contract:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('store_id','quote_kind','quote_id',name='uq_member_price_quote'),CheckConstraint("definition_version=1 AND quote_kind IN ('repair','retail','addon')",name='ck_member_price_snapshot'),)

class MemberPricingLine(StoreScoped,Base):
    __tablename__='member_pricing_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    snapshot_id:Mapped[int]=mapped_column(ForeignKey('member_pricing_snapshots.id'),index=True)
    line_key:Mapped[str]=mapped_column(String(80))
    component:Mapped[str]=mapped_column(String(20))
    source_id:Mapped[int]=mapped_column(Integer)
    scope_id:Mapped[int|None]=mapped_column(ForeignKey('member_pricing_scopes.id'),nullable=True)
    charge_scope:Mapped[str]=mapped_column(String(30))
    basis_cents:Mapped[int]=mapped_column(BigInteger)
    member_discount_cents:Mapped[int]=mapped_column(BigInteger)
    manual_discount_cents:Mapped[int]=mapped_column(BigInteger)
    net_cents:Mapped[int]=mapped_column(BigInteger)
    carry_cents:Mapped[int]=mapped_column(BigInteger)
    basis_points:Mapped[int]=mapped_column(Integer)
    __table_args__=(UniqueConstraint('snapshot_id','line_key','component',name='uq_member_price_line'),CheckConstraint('basis_cents>=0 AND member_discount_cents>=0 AND manual_discount_cents>=0 AND net_cents>=0 AND carry_cents>=0 AND basis_points BETWEEN 1 AND 10000 AND member_discount_cents+manual_discount_cents+net_cents=basis_cents',name='ck_member_price_line_money'),)

class MemberPricingAuthorization(Fact,StoreScoped,Base):
    __tablename__='member_pricing_authorizations'
    snapshot_id:Mapped[int]=mapped_column(ForeignKey('member_pricing_snapshots.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    snapshot_digest:Mapped[str]=mapped_column(String(64))

@event.listens_for(Session,'before_flush')
def immutable_member_prices(db,*_):
    kinds=(MemberPricingRule,MemberPricingScope,MemberPricingDecision,MemberPricingSnapshot,MemberPricingLine,MemberPricingAuthorization)
    if any(isinstance(r,kinds) for r in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'会员价格批准、原会期与原报价不得覆盖，请追加规则或业务报价版本')
