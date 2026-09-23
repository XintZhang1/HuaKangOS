"""Append-only transport findings, reviewed loss and actual recovery facts.

These tables extend new material-transfer version 3 only. The original five
movement kinds remain immutable; a loss never pretends to be a stock receipt.
"""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .transfer_models import TransferProtected


class TransferException(TransferProtected, Base):
    __tablename__='transfer_exceptions'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('material_transfers.id'),index=True)
    active_transfer_id:Mapped[int|None]=mapped_column(ForeignKey('material_transfers.id'),nullable=True,unique=True)
    original_id:Mapped[int]=mapped_column(ForeignKey('material_transfer_movements.id'),index=True)
    stage:Mapped[str]=mapped_column(String(15))
    finding:Mapped[str]=mapped_column(String(15))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    request_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    due_date:Mapped[date]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),default='investigating')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow,onupdate=utcnow)
    __mapper_args__={'version_id_col':version}
    __table_args__=(CheckConstraint("stage IN ('outbound','rejected','returning') AND finding IN ('missing','damaged')",name='ck_transfer_exception_origin'),
        CheckConstraint('quantity_milli>0 AND value_cents>=0',name='ck_transfer_exception_amount'),
        CheckConstraint("status IN ('investigating','review','approved','disposed','posted','cancelled')",name='ck_transfer_exception_status'),
        CheckConstraint("(status IN ('posted','cancelled') AND active_transfer_id IS NULL) OR (status NOT IN ('posted','cancelled') AND active_transfer_id IS NOT NULL AND active_transfer_id=transfer_id)",name='ck_transfer_exception_active'))


class TransferExceptionObservation(TransferProtected, Base):
    __tablename__='transfer_exception_observations'
    id:Mapped[int]=mapped_column(primary_key=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),index=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    observation:Mapped[str]=mapped_column(String(30))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    result:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("observation IN ('dispatch_verified','return_dispatch_verified','missing','held_damaged') AND quantity_milli>0",name='ck_transfer_exception_observation'),)


class TransferExceptionPlan(TransferProtected, Base):
    __tablename__='transfer_exception_plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    source_observation_id:Mapped[int]=mapped_column(ForeignKey('transfer_exception_observations.id'))
    destination_observation_id:Mapped[int]=mapped_column(ForeignKey('transfer_exception_observations.id'))
    source_bearer_cents:Mapped[int]=mapped_column(BigInteger)
    destination_bearer_cents:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('exception_id','revision',name='uq_transfer_exception_plan_revision'),
        CheckConstraint('revision>0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0',name='ck_transfer_exception_plan_amount'))


class TransferExceptionReview(TransferProtected, Base):
    __tablename__='transfer_exception_reviews'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_exception_plans.id'),index=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    decision:Mapped[str]=mapped_column(String(10))
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('plan_id','store_id',name='uq_transfer_exception_review_party'),
        CheckConstraint("decision IN ('approve','reject')",name='ck_transfer_exception_review_decision'))


class TransferExceptionDisposal(TransferProtected, Base):
    __tablename__='transfer_exception_disposals'
    id:Mapped[int]=mapped_column(primary_key=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),unique=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_exception_plans.id'))
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    method:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('quantity_milli>0',name='ck_transfer_exception_disposal_quantity'),)


class TransferLossPosting(StoreScoped, Base):
    __tablename__='transfer_loss_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),unique=True)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('material_transfers.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('material_transfer_lines.id'),index=True)
    original_id:Mapped[int]=mapped_column(ForeignKey('material_transfer_movements.id'))
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_exception_plans.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    source_bearer_cents:Mapped[int]=mapped_column(BigInteger)
    destination_bearer_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('quantity_milli>0 AND value_cents>=0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0 AND source_bearer_cents+destination_bearer_cents=value_cents',name='ck_transfer_loss_conservation'),)


class TransferLossSettlement(StoreScoped, Base):
    __tablename__='transfer_loss_settlements'
    id:Mapped[int]=mapped_column(primary_key=True)
    transfer_id:Mapped[int]=mapped_column(ForeignKey('material_transfers.id'),index=True)
    posting_id:Mapped[int]=mapped_column(ForeignKey('transfer_loss_postings.id'),index=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),index=True)
    counterparty_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('posting_id','store_id',name='uq_transfer_loss_settlement_party'),CheckConstraint('amount_cents!=0',name='ck_transfer_loss_settlement_amount'))


class TransferExceptionCancellation(TransferProtected, Base):
    __tablename__='transfer_exception_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),unique=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class TransferExceptionReceipt(StoreScoped, Base):
    __tablename__='transfer_exception_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_transfer_exception_request'),)


class TransferRecoveryClaim(Versioned, Base):
    __tablename__='transfer_recovery_claims'
    exception_id:Mapped[int]=mapped_column(ForeignKey('transfer_exceptions.id'),index=True)
    counterparty_kind:Mapped[str]=mapped_column(String(12))
    supplier_id:Mapped[int|None]=mapped_column(ForeignKey('master_suppliers.id'),nullable=True)
    insurer_id:Mapped[int|None]=mapped_column(ForeignKey('master_insurers.id'),nullable=True)
    counterparty_snapshot:Mapped[dict]=mapped_column(JSON)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("(counterparty_kind='carrier' AND supplier_id IS NOT NULL AND insurer_id IS NULL) OR (counterparty_kind='insurer' AND insurer_id IS NOT NULL AND supplier_id IS NULL)",name='ck_transfer_recovery_party'),)


class TransferRecoveryPlan(StoreScoped, Base):
    __tablename__='transfer_recovery_plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    claim_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_claims.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    target_cents:Mapped[int]=mapped_column(BigInteger)
    due_date:Mapped[date]=mapped_column(Date)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('claim_id','revision',name='uq_transfer_recovery_revision'),CheckConstraint('target_cents>=0',name='ck_transfer_recovery_target'))


class TransferRecoveryReview(StoreScoped, Base):
    __tablename__='transfer_recovery_reviews'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_plans.id'),unique=True)
    decision:Mapped[str]=mapped_column(String(10))
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("decision IN ('approve','reject')",name='ck_transfer_recovery_review'),)


class TransferRecoveryCancellation(StoreScoped, Base):
    __tablename__='transfer_recovery_cancellations'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_plans.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class TransferRecoveryPayment(StoreScoped, Base):
    __tablename__='transfer_recovery_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    claim_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_claims.id'),index=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('transfer_recovery_plans.id'))
    original_id:Mapped[int|None]=mapped_column(ForeignKey('transfer_recovery_payments.id'),nullable=True)
    direction:Mapped[str]=mapped_column(String(3))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    reference:Mapped[str]=mapped_column(String(100))
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))",name='ck_transfer_recovery_payment'),)


IMMUTABLE=(TransferExceptionObservation,TransferExceptionPlan,TransferExceptionReview,TransferExceptionDisposal,
           TransferLossPosting,TransferLossSettlement,TransferExceptionCancellation,TransferExceptionReceipt,
           TransferRecoveryPlan,TransferRecoveryReview,TransferRecoveryCancellation,TransferRecoveryPayment)


@event.listens_for(Session,'before_flush')
def protect_exception_facts(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if not isinstance(row,(TransferException,TransferRecoveryClaim,*IMMUTABLE)):continue
        if not db.info.get('_transfer_exception_authority'):raise HTTPException(403,'调拨差异只能由明确的差异动作办理')
        if row in db.dirty or row in db.deleted:
            if isinstance(row,IMMUTABLE):raise HTTPException(409,'调拨观察、批准、真实处置、损失及往来不可覆盖')
            if isinstance(row,TransferException):
                mutable={'status','active_transfer_id','version','updated_at'}
                if row in db.deleted or any(inspect(row).attrs[c.name].history.has_changes() for c in row.__table__.columns if c.name not in mutable):
                    raise HTTPException(409,'调拨差异原批次、数量及成本不可覆盖；未生效差异可有据取消后重建')
            if isinstance(row,TransferRecoveryClaim):
                mutable={'version','updated_at'}
                if row in db.deleted or any(inspect(row).attrs[c.name].history.has_changes() for c in row.__table__.columns if c.name not in mutable):
                    raise HTTPException(409,'追偿往来方与来源不可覆盖；金额变化须追加原往来方确认的目标版本')


@event.listens_for(Session,'do_orm_execute')
def protect_exception_bulk(state):
    if (state.is_update or state.is_delete) and any(issubclass(m.class_,(TransferException,TransferRecoveryClaim,*IMMUTABLE)) for m in state.all_mappers):
        raise HTTPException(409,'差异及追偿事实不得批量覆盖')
