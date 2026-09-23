"""Original-VIN transport investigation, loss and later actual recovery.

The dispatch remains the only original inventory exit. Loss removes its transit
asset; a found observation is not a receipt. All cross-store facts are readable
only through authenticated transfer coordination, never ordinary ORM queries.
"""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import (String, Integer, BigInteger, Date, DateTime, ForeignKey,
    JSON, CheckConstraint, UniqueConstraint, event, inspect)
from sqlalchemy.orm import Mapped, mapped_column, Session, declared_attr
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned
from .transfer_models import TransferProtected


class TransportVersioned(TransferProtected):
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    @declared_attr.directive
    def __mapper_args__(cls): return {'version_id_col': cls.version}


class VehicleTransportException(TransportVersioned, Base):
    __tablename__ = 'vehicle_transport_exceptions'
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'), index=True)
    active_transfer_id: Mapped[int | None] = mapped_column(ForeignKey('vehicle_transfers.id'), nullable=True, unique=True)
    original_id: Mapped[int] = mapped_column(ForeignKey('vehicle_movements.id'))
    origin_status: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='investigating')
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    __table_args__ = (CheckConstraint(
        "origin_status IN ('transit','rejected','return_transit') AND kind IN ('missing','vin_mismatch','damage') "
        "AND status IN ('investigating','review','approved','posted','resolved','recovered') "
        "AND ((status IN ('resolved','recovered') AND active_transfer_id IS NULL) OR "
        "(status NOT IN ('resolved','recovered') AND active_transfer_id IS NOT NULL AND active_transfer_id=transfer_id))",
        name='ck_vehicle_transport_exception'),)


class VehicleTransportObservation(TransferProtected, Base):
    __tablename__ = 'vehicle_transport_observations'
    id: Mapped[int] = mapped_column(primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    kind: Mapped[str] = mapped_column(String(24))
    vin: Mapped[str] = mapped_column(String(17))
    actual_at: Mapped[datetime] = mapped_column(DateTime)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint(
        "kind IN ('dispatch_verified','not_located','original_seen','unusable_held','other_vin_seen','found_usable') AND actual_at<=created_at",
        name='ck_vehicle_transport_observation'),)


class VehicleTransportPlan(TransferProtected, Base):
    __tablename__ = 'vehicle_transport_plans'
    id: Mapped[int] = mapped_column(primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    source_observation_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_observations.id'))
    destination_observation_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_observations.id'))
    found_observation_id: Mapped[int | None] = mapped_column(ForeignKey('vehicle_transport_observations.id'), nullable=True)
    receiving_store_id: Mapped[int | None] = mapped_column(ForeignKey('stores.id'), nullable=True)
    source_bearer_cents: Mapped[int] = mapped_column(BigInteger)
    destination_bearer_cents: Mapped[int] = mapped_column(BigInteger)
    loss_method: Mapped[str] = mapped_column(String(12))
    origin_digest: Mapped[str] = mapped_column(String(64))
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('exception_id', 'revision', name='uq_vehicle_transport_plan_revision'),
        CheckConstraint("revision>0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0 AND "
        "((kind='resume' AND loss_method='none' AND source_bearer_cents=0 AND destination_bearer_cents=0 AND found_observation_id IS NULL AND receiving_store_id IS NULL) OR "
        "(kind='loss' AND loss_method IN ('missing','destroyed') AND found_observation_id IS NULL AND receiving_store_id IS NULL) OR "
        "(kind='found_receive' AND loss_method='none' AND source_bearer_cents=0 AND destination_bearer_cents=0 AND found_observation_id IS NOT NULL AND receiving_store_id IS NOT NULL))",
        name='ck_vehicle_transport_plan'),)


class VehicleTransportReview(TransferProtected, Base):
    __tablename__ = 'vehicle_transport_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_plans.id'), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    decision: Mapped[str] = mapped_column(String(10))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('plan_id', 'store_id', name='uq_vehicle_transport_review_party'),
        CheckConstraint("decision IN ('approve','reject')", name='ck_vehicle_transport_review'),)


class VehicleTransportWithdrawal(TransferProtected, Base):
    __tablename__ = 'vehicle_transport_withdrawals'
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_plans.id'), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VehicleTransportDisposal(TransferProtected, Base):
    __tablename__ = 'vehicle_transport_disposals'
    id: Mapped[int] = mapped_column(primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), unique=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_plans.id'), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    vin: Mapped[str] = mapped_column(String(17))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VehicleTransportFoundUnavailable(TransferProtected, Base):
    __tablename__ = 'vehicle_transport_found_unavailable'
    id: Mapped[int] = mapped_column(primary_key=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_plans.id'), unique=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_observations.id'), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    vin: Mapped[str] = mapped_column(String(17))
    kind: Mapped[str] = mapped_column(String(20))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("kind IN ('missing_again','not_usable')", name='ck_vehicle_transport_found_unavailable'),)


class VehicleTransportLoss(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_losses'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'), unique=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), unique=True)
    original_id: Mapped[int] = mapped_column(ForeignKey('vehicle_movements.id'))
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_plans.id'), unique=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    value_cents: Mapped[int] = mapped_column(BigInteger)
    source_bearer_cents: Mapped[int] = mapped_column(BigInteger)
    destination_bearer_cents: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(12))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("value_cents>=0 AND source_bearer_cents>=0 AND destination_bearer_cents>=0 AND "
        "source_bearer_cents+destination_bearer_cents=value_cents AND kind IN ('missing','destroyed')", name='ck_vehicle_transport_loss'),)


class VehicleTransportLossSettlement(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_loss_settlements'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'), index=True)
    loss_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_losses.id'))
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'))
    counterparty_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    business_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (UniqueConstraint('loss_id', 'store_id', name='uq_vehicle_transport_loss_settlement'),
        CheckConstraint('amount_cents!=0', name='ck_vehicle_transport_loss_settlement'),)


class VehicleTransportFoundReceipt(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_found_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'), unique=True)
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), unique=True)
    loss_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_losses.id'), unique=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_plans.id'), unique=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_observations.id'))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'), unique=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    value_cents: Mapped[int] = mapped_column(BigInteger)
    location_id: Mapped[int] = mapped_column(ForeignKey('master_locations.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('value_cents>=0', name='ck_vehicle_transport_found_receipt'),)


class VehicleTransportFoundSettlement(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_found_settlements'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'), index=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_found_receipts.id'))
    loss_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_losses.id'))
    counterparty_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    business_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (UniqueConstraint('receipt_id', 'store_id', name='uq_vehicle_transport_found_settlement'),
        CheckConstraint('amount_cents!=0', name='ck_vehicle_transport_found_settlement'),)


class VehicleTransportReceipt(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_requests'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('store_id', 'request_key', name='uq_vehicle_transport_request'),)


class VehicleTransportClaim(Versioned, Base):
    __tablename__ = 'vehicle_transport_claims'
    exception_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_exceptions.id'), index=True)
    counterparty_kind: Mapped[str] = mapped_column(String(12))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey('master_suppliers.id'), nullable=True)
    insurer_id: Mapped[int | None] = mapped_column(ForeignKey('master_insurers.id'), nullable=True)
    counterparty_snapshot: Mapped[dict] = mapped_column(JSON)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (CheckConstraint("(counterparty_kind='carrier' AND supplier_id IS NOT NULL AND insurer_id IS NULL) OR "
        "(counterparty_kind='insurer' AND insurer_id IS NOT NULL AND supplier_id IS NULL)", name='ck_vehicle_transport_claim_party'),)


class VehicleTransportClaimPlan(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_claim_plans'
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_claims.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    target_cents: Mapped[int] = mapped_column(BigInteger)
    due_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(1000))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('claim_id', 'revision', name='uq_vehicle_transport_claim_revision'),
        CheckConstraint('revision>0 AND target_cents>=0', name='ck_vehicle_transport_claim_target'),)


class VehicleTransportClaimReview(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_claim_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_claim_plans.id'), unique=True)
    decision: Mapped[str] = mapped_column(String(10))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("decision IN ('approve','reject')", name='ck_vehicle_transport_claim_review'),)


class VehicleTransportClaimWithdrawal(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_claim_withdrawals'
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_claim_plans.id'), unique=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VehicleTransportClaimPayment(StoreScoped, Base):
    __tablename__ = 'vehicle_transport_claim_payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_claims.id'), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transport_claim_plans.id'))
    original_id: Mapped[int | None] = mapped_column(ForeignKey('vehicle_transport_claim_payments.id'), nullable=True)
    direction: Mapped[str] = mapped_column(String(3))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    account_id: Mapped[int] = mapped_column(ForeignKey('flow_accounts.id'))
    reference: Mapped[str] = mapped_column(String(100))
    cash_id: Mapped[int] = mapped_column(ForeignKey('cash_entries.id'), unique=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id', 'account_id', 'reference', name='uq_vehicle_transport_claim_cash_reference'),
        CheckConstraint("amount_cents>0 AND ((direction='in' AND original_id IS NULL) OR (direction='out' AND original_id IS NOT NULL))", name='ck_vehicle_transport_claim_cash'),)


IMMUTABLE = (VehicleTransportObservation, VehicleTransportPlan, VehicleTransportReview,
    VehicleTransportWithdrawal, VehicleTransportDisposal, VehicleTransportFoundUnavailable, VehicleTransportLoss,
    VehicleTransportLossSettlement, VehicleTransportFoundReceipt, VehicleTransportFoundSettlement,
    VehicleTransportReceipt, VehicleTransportClaimPlan, VehicleTransportClaimReview,
    VehicleTransportClaimWithdrawal, VehicleTransportClaimPayment)
FROZEN = {
    VehicleTransportException: ('transfer_id', 'original_id', 'origin_status', 'kind', 'store_id', 'requested_by', 'evidence_id', 'reason', 'created_at'),
    VehicleTransportClaim: ('exception_id', 'counterparty_kind', 'supplier_id', 'insurer_id', 'counterparty_snapshot', 'requested_by', 'created_at'),
}


@event.listens_for(Session, 'before_flush')
def protect_vehicle_transport_facts(db, *_):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, IMMUTABLE):
            raise HTTPException(409, '整车运输观察、批准、损失、找回与真实收退款不可覆盖')
        for model, fields in FROZEN.items():
            if isinstance(row, model) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in fields)):
                raise HTTPException(409, '原整车差异和追偿身份不可覆盖，请追加后继事实')
