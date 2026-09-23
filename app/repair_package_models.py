"""Explicit mixed repair contracts. Scalar legacy benefit wallets remain unchanged."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Date,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .group_models import GroupProtected,CentralVersioned

class Fact:
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class PackageRule(Fact,GroupProtected,Base):
    __tablename__='repair_package_rules'
    issuer_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    definition_version:Mapped[int]=mapped_column(Integer,default=1)
    code:Mapped[str]=mapped_column(String(40))
    rule_version:Mapped[int]=mapped_column(Integer)
    name:Mapped[str]=mapped_column(String(120))
    contract:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('issuer_store_id','code','rule_version',name='uq_repair_package_rule'),CheckConstraint('definition_version=1 AND rule_version>0',name='ck_repair_package_rule'),)

class PackageRuleDecision(Fact,GroupProtected,Base):
    __tablename__='repair_package_rule_decisions'
    rule_id:Mapped[int]=mapped_column(ForeignKey('repair_package_rules.id'),index=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    action:Mapped[str]=mapped_column(String(12))
    reason:Mapped[str]=mapped_column(String(1000))
    __table_args__=(UniqueConstraint('rule_id','action',name='uq_repair_package_decision'),CheckConstraint("action IN ('approve','reject','cancel','revoke')",name='ck_repair_package_decision'),)

class PackageMapping(Fact,GroupProtected,Base):
    __tablename__='repair_package_mappings'
    rule_id:Mapped[int]=mapped_column(ForeignKey('repair_package_rules.id'),index=True)
    component_key:Mapped[str]=mapped_column(String(40))
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    kind:Mapped[str]=mapped_column(String(10))
    source_id:Mapped[int]=mapped_column(Integer)
    snapshot:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('rule_id','component_key','store_id',name='uq_repair_package_mapping'),CheckConstraint("kind IN ('work','part') AND source_id>0",name='ck_repair_package_mapping'),)

class PackagePurchase(CentralVersioned,Base):
    __tablename__='repair_package_purchases'
    rule_id:Mapped[int]=mapped_column(ForeignKey('repair_package_rules.id'))
    member_id:Mapped[int]=mapped_column(ForeignKey('group_members.id'),index=True)
    issuer_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    sets:Mapped[int]=mapped_column(Integer)
    contract:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    expires_on:Mapped[date]=mapped_column(Date)
    valid_until:Mapped[date]=mapped_column(Date)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    status:Mapped[str]=mapped_column(String(12),default='proposed')
    cash_id:Mapped[int|None]=mapped_column(ForeignKey('cash_entries.id'),nullable=True,unique=True)
    account_id:Mapped[int|None]=mapped_column(ForeignKey('flow_accounts.id'),nullable=True)
    __table_args__=(CheckConstraint("sets>0 AND amount_cents>0 AND status IN ('proposed','authorized','issued','cancelled')",name='ck_repair_package_purchase'),CheckConstraint("(status='issued' AND cash_id IS NOT NULL AND account_id IS NOT NULL) OR (status!='issued' AND cash_id IS NULL AND account_id IS NULL)",name='ck_repair_package_purchase_cash'),)

class PackagePurchaseEvent(Fact,StoreScoped,Base):
    __tablename__='repair_package_purchase_events'
    purchase_id:Mapped[int]=mapped_column(ForeignKey('repair_package_purchases.id'),index=True)
    action:Mapped[str]=mapped_column(String(12))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('purchase_id','action',name='uq_repair_package_purchase_event'),CheckConstraint("action IN ('propose','authorize','issue','cancel')",name='ck_repair_package_purchase_event'),)

class PackageLot(CentralVersioned,Base):
    __tablename__='repair_package_lots'
    purchase_id:Mapped[int]=mapped_column(ForeignKey('repair_package_purchases.id'),index=True)
    component_key:Mapped[str]=mapped_column(String(40))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    paid_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    snapshot:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('purchase_id','component_key',name='uq_repair_package_lot'),CheckConstraint('quantity_milli>0 AND credit_cents>0 AND paid_cents>=0 AND settlement_cents>=paid_cents AND credit_cents>=settlement_cents',name='ck_repair_package_lot'),)

class PackageHold(CentralVersioned,Base):
    __tablename__='repair_package_holds'
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    lot_id:Mapped[int]=mapped_column(ForeignKey('repair_package_lots.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('repair_lines.id'),unique=True)
    line_key:Mapped[str]=mapped_column(String(40))
    spans:Mapped[list]=mapped_column(JSON)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    paid_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    digest:Mapped[str]=mapped_column(String(64))
    status:Mapped[str]=mapped_column(String(12),default='reserved')
    __table_args__=(CheckConstraint("quantity_milli>0 AND credit_cents>=0 AND paid_cents>=0 AND settlement_cents>=0 AND status IN ('reserved','released','captured')",name='ck_repair_package_hold'),)

class PackageEntry(Fact,GroupProtected,Base):
    __tablename__='repair_package_entries'
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    lot_id:Mapped[int]=mapped_column(ForeignKey('repair_package_lots.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    purpose:Mapped[str]=mapped_column(String(12))
    hold_id:Mapped[int|None]=mapped_column(ForeignKey('repair_package_holds.id'),nullable=True)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('repair_package_entries.id'),nullable=True,index=True)
    refund_id:Mapped[int|None]=mapped_column(ForeignKey('repair_package_refunds.id'),nullable=True)
    spans:Mapped[list]=mapped_column(JSON)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    paid_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint("quantity_milli>0 AND credit_cents>=0 AND paid_cents>=0 AND settlement_cents>=0 AND purpose IN ('capture','reverse','refund')",name='ck_repair_package_entry'),CheckConstraint("(purpose='capture' AND hold_id IS NOT NULL AND original_id IS NULL AND refund_id IS NULL) OR (purpose='reverse' AND original_id IS NOT NULL AND hold_id IS NOT NULL AND refund_id IS NULL) OR (purpose='refund' AND refund_id IS NOT NULL AND hold_id IS NULL AND original_id IS NULL)",name='ck_repair_package_entry_origin'),)

class PackageReservationLink(Versioned,Base):
    __tablename__='repair_package_reservation_links'
    hold_id:Mapped[int]=mapped_column(ForeignKey('repair_package_holds.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    recognized_cents:Mapped[int]=mapped_column(BigInteger)
    status:Mapped[str]=mapped_column(String(12),default='reserved')
    __table_args__=(CheckConstraint("amount_cents>=0 AND recognized_cents>=0 AND status IN ('reserved','released','captured')",name='ck_repair_package_reservation_link'),)

class PackageQuoteSnapshot(Fact,StoreScoped,Base):
    __tablename__='repair_package_quote_snapshots'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),unique=True)
    contract:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))

class PackagePaymentLink(Fact,StoreScoped,Base):
    __tablename__='repair_package_payment_links'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    entry_id:Mapped[int]=mapped_column(ForeignKey('repair_package_entries.id'),unique=True)
    purpose:Mapped[str]=mapped_column(String(12))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    recognized_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(CheckConstraint("(purpose='capture' AND amount_cents>=0 AND recognized_cents>=0) OR (purpose='reverse' AND amount_cents<=0 AND recognized_cents<=0)",name='ck_repair_package_payment'),)

class PackageSettlement(Fact,StoreScoped,Base):
    __tablename__='repair_package_settlements'
    entry_id:Mapped[int]=mapped_column(ForeignKey('repair_package_entries.id'),index=True)
    side:Mapped[str]=mapped_column(String(10))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('entry_id','side',name='uq_repair_package_settlement'),CheckConstraint("side IN ('center','store') AND amount_cents!=0",name='ck_repair_package_settlement'),)

class PackageRefund(Versioned,Base):
    __tablename__='repair_package_refunds'
    purchase_id:Mapped[int]=mapped_column(ForeignKey('repair_package_purchases.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'))
    selections:Mapped[list]=mapped_column(JSON)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    status:Mapped[str]=mapped_column(String(12),default='requested')
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    cash_id:Mapped[int|None]=mapped_column(ForeignKey('cash_entries.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint("amount_cents>=0 AND status IN ('requested','approved','rejected','cancelled','executed')",name='ck_repair_package_refund'),CheckConstraint("status NOT IN ('approved','executed') OR approved_by IS NOT NULL",name='ck_repair_package_refund_approval'),CheckConstraint("(status='executed' AND ((amount_cents>0 AND cash_id IS NOT NULL) OR (amount_cents=0 AND cash_id IS NULL))) OR (status!='executed' AND cash_id IS NULL)",name='ck_repair_package_refund_cash'),)

class PackageRefundClaim(CentralVersioned,Base):
    __tablename__='repair_package_refund_claims'
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    refund_id:Mapped[int]=mapped_column(ForeignKey('repair_package_refunds.id'),index=True)
    lot_id:Mapped[int]=mapped_column(ForeignKey('repair_package_lots.id'),index=True)
    spans:Mapped[list]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(12),default='reserved')
    __table_args__=(UniqueConstraint('refund_id','lot_id',name='uq_repair_package_refund_claim'),CheckConstraint("status IN ('reserved','released','applied')",name='ck_repair_package_refund_claim'),)

class PackageAftercareHold(Versioned,Base):
    __tablename__='repair_package_aftercare_holds'
    aftercare_case_id:Mapped[int]=mapped_column(ForeignKey('aftercare_orders.id'))
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('aftercare_plans.id'),index=True)
    original_id:Mapped[int]=mapped_column(ForeignKey('repair_package_entries.id'),index=True)
    spans:Mapped[list]=mapped_column(JSON)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    credit_cents:Mapped[int]=mapped_column(BigInteger)
    paid_cents:Mapped[int]=mapped_column(BigInteger)
    settlement_cents:Mapped[int]=mapped_column(BigInteger)
    status:Mapped[str]=mapped_column(String(12),default='reserved')
    __table_args__=(UniqueConstraint('plan_id','original_id',name='uq_repair_package_aftercare'),CheckConstraint("quantity_milli>0 AND status IN ('reserved','released','applied')",name='ck_repair_package_aftercare'),)

class PackageStockReturn(Fact,StoreScoped,Base):
    __tablename__='repair_package_stock_returns'
    hold_id:Mapped[int]=mapped_column(ForeignKey('repair_package_aftercare_holds.id'),index=True)
    original_stock_id:Mapped[int]=mapped_column(ForeignKey('repair_stock.id'))
    stock_fact_id:Mapped[int]=mapped_column(ForeignKey('repair_stock.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    result:Mapped[str]=mapped_column(String(1000))
    __table_args__=(CheckConstraint('quantity_milli>0 AND value_cents>=0',name='ck_repair_package_stock_return'),)

IMMUTABLE=(PackageRule,PackageRuleDecision,PackageMapping,PackagePurchaseEvent,PackageEntry,PackagePaymentLink,PackageSettlement,PackageStockReturn,PackageQuoteSnapshot)
FROZEN={PackagePurchase:('rule_id','member_id','issuer_store_id','case_id','sets','contract','digest','amount_cents','expires_on','valid_until','requested_by'),PackageLot:('purchase_id','component_key','quantity_milli','credit_cents','paid_cents','settlement_cents','snapshot'),PackageHold:('store_id','lot_id','case_id','quote_id','line_id','line_key','spans','quantity_milli','credit_cents','paid_cents','settlement_cents','digest'),PackageRefund:('store_id','purchase_id','case_id','selections','amount_cents','requested_by','evidence_id','reason'),PackageAftercareHold:('store_id','aftercare_case_id','source_case_id','plan_id','original_id','spans','quantity_milli','credit_cents','paid_cents','settlement_cents')}
FROZEN[PackageReservationLink]=('store_id','hold_id','case_id','quote_id','amount_cents','recognized_cents')
FROZEN[PackageRefundClaim]=('store_id','refund_id','lot_id','spans')
@event.listens_for(Session,'before_flush')
def guard_packages(db,*_):
    for row in set(db.dirty)|set(db.deleted):
        if isinstance(row,IMMUTABLE) and (row in db.deleted or db.is_modified(row)):raise HTTPException(409,'套餐合同和实际账本不可覆盖，请追加原单更正')
        for kind,keys in FROZEN.items():
            if isinstance(row,kind) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in keys)):raise HTTPException(409,'套餐原来源和数量分摊已经冻结')
    for row in set(db.new)|set(db.dirty)|set(db.deleted):
        if isinstance(row,(*IMMUTABLE,*FROZEN)) and not db.info.get('_package_authority'):raise HTTPException(403,'混合套餐须通过原合同服务办理')

@event.listens_for(Session,'do_orm_execute')
def guard_package_bulk(state):
    if (state.is_update or state.is_delete) and any(issubclass(m.class_,(*IMMUTABLE,*FROZEN)) for m in state.all_mappers):raise HTTPException(409,'套餐事实不允许批量覆盖')
