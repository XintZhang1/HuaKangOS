"""Found goods do not edit the original loss, physical movements or cash. Both
stores share narrow coordination facts; stock and financial ledgers stay local.
"""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import Integer,BigInteger,String,Date,DateTime,Boolean,ForeignKey,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .transfer_models import TransferProtected


class GoodsRecovery(TransferProtected,Base):
    __tablename__='transfer_goods_recoveries'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('material_transfers.id'),index=True)
    active_transfer_id:Mapped[int|None]=mapped_column(ForeignKey('material_transfers.id'),unique=True,nullable=True)
    loss_id:Mapped[int]=mapped_column(ForeignKey('transfer_loss_postings.id'),index=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),index=True)
    found_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(1000))
    due_date:Mapped[date]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),default='preparing')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow,onupdate=utcnow)
    __mapper_args__={'version_id_col':version}
    __table_args__=(CheckConstraint('quantity_milli>0',name='ck_found_quantity'),
        CheckConstraint("status IN ('preparing','transit','review','approved','financial','closed','cancelled','unlocated')",name='ck_found_state'),
        CheckConstraint("(status IN ('closed','cancelled','unlocated') AND active_transfer_id IS NULL) OR (status NOT IN ('closed','cancelled','unlocated') AND active_transfer_id=transfer_id AND active_transfer_id IS NOT NULL)",name='ck_found_active'))


class GoodsFact(TransferProtected,Base):
    __tablename__='transfer_goods_facts'
    id:Mapped[int]=mapped_column(primary_key=True)
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'),index=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    kind:Mapped[str]=mapped_column(String(15))
    passed:Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("quantity_milli>0 AND kind IN ('found','match','inspect','ship','receive','dispose','cancel')",name='ck_found_fact'),
        CheckConstraint("(kind IN ('inspect','receive') AND passed IS NOT NULL) OR (kind NOT IN ('inspect','receive') AND passed IS NULL)",name='ck_found_quality'))


class GoodsPlan(TransferProtected,Base):
    __tablename__='transfer_goods_plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    match_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_facts.id'))
    inspection_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_facts.id'))
    restored_quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    source_reverse_cents:Mapped[int]=mapped_column(BigInteger)
    destination_reverse_cents:Mapped[int]=mapped_column(BigInteger)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('recovery_id','revision',name='uq_found_plan'),
        CheckConstraint('revision>0 AND restored_quantity_milli>=0 AND value_cents>=0 AND source_reverse_cents>=0 AND destination_reverse_cents>=0 AND source_reverse_cents+destination_reverse_cents=value_cents',name='ck_found_plan_amount'))


class GoodsReview(TransferProtected,Base):
    __tablename__='transfer_goods_reviews'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_plans.id'),index=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    decision:Mapped[str]=mapped_column(String(10))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('plan_id','store_id',name='uq_found_review'),CheckConstraint("decision IN ('approve','reject')",name='ck_found_review'))


class GoodsPosting(StoreScoped,Base):
    __tablename__='transfer_goods_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'),unique=True)
    loss_id:Mapped[int]=mapped_column(ForeignKey('transfer_loss_postings.id'),index=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_plans.id'),unique=True)
    found_quantity_milli:Mapped[int]=mapped_column(BigInteger)
    restored_quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    source_reverse_cents:Mapped[int]=mapped_column(BigInteger)
    destination_reverse_cents:Mapped[int]=mapped_column(BigInteger)
    stock_move_id:Mapped[int|None]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True,nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('found_quantity_milli>0 AND restored_quantity_milli>=0 AND restored_quantity_milli<=found_quantity_milli AND value_cents>=0 AND source_reverse_cents>=0 AND destination_reverse_cents>=0 AND source_reverse_cents+destination_reverse_cents=value_cents',name='ck_found_posting_amount'),
        CheckConstraint('(restored_quantity_milli>0 AND stock_move_id IS NOT NULL) OR (restored_quantity_milli=0 AND stock_move_id IS NULL AND value_cents=0)',name='ck_found_stock'))


class GoodsSettlement(StoreScoped,Base):
    __tablename__='transfer_goods_settlements'
    id:Mapped[int]=mapped_column(primary_key=True)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('material_transfers.id'),index=True)
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'),index=True)
    posting_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_postings.id'),index=True)
    original_id:Mapped[int]=mapped_column(ForeignKey('transfer_loss_settlements.id'))
    counterparty_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('posting_id','store_id',name='uq_found_settlement'),CheckConstraint('amount_cents!=0',name='ck_found_settlement'))


class GoodsTerms(StoreScoped,Base):
    __tablename__='transfer_goods_terms'
    id:Mapped[int]=mapped_column(primary_key=True)
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'),index=True)
    claim_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_claims.id'),index=True)
    previous_plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_plans.id'))
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_plans.id'),unique=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class GoodsRefund(StoreScoped,Base):
    __tablename__='transfer_goods_refunds'
    id:Mapped[int]=mapped_column(primary_key=True)
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'),index=True)
    terms_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_terms.id'))
    payment_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_payments.id'),unique=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class GoodsReceipt(StoreScoped,Base):
    __tablename__='transfer_goods_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest:Mapped[str]=mapped_column(String(64))
    recovery_id:Mapped[int]=mapped_column(ForeignKey('transfer_goods_recoveries.id'))
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_found_request'),)


FACTS=(GoodsFact,GoodsPlan,GoodsReview,GoodsPosting,GoodsSettlement,GoodsTerms,GoodsRefund,GoodsReceipt)
TABLES=(GoodsRecovery,*FACTS)


@event.listens_for(Session,'before_flush')
def protect_goods(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,TABLES):continue
        if not db.info.get('_transfer_goods_authority'):raise HTTPException(403,'找回原物资须通过专用授权动作')
        if row in db.deleted or isinstance(row,FACTS) and row in db.dirty:raise HTTPException(409,'找回、复验、原成本及原款记录不可覆盖')
        if isinstance(row,GoodsRecovery) and row in db.dirty:
            if any(inspect(row).attrs[c.name].history.has_changes() for c in row.__table__.columns if c.name not in {'version','status','active_transfer_id','updated_at'}):
                raise HTTPException(409,'原损失与本次找到数量不能覆盖')


@event.listens_for(Session,'do_orm_execute')
def protect_goods_queries(state):
    if any(issubclass(m.class_,TABLES) for m in state.all_mappers):
        if not state.session.info.get('_transfer_goods_authority'):raise HTTPException(403,'找回原物资仅限专用授权查询')
        if state.is_update or state.is_delete:raise HTTPException(409,'找回原物资不得批量覆盖')
