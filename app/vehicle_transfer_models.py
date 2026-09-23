"""VIN identity is central; each actual receipt remains a store-owned Vehicle."""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, Date, DateTime, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped, Vehicle
from .transfer_models import TransferProtected


class VehicleCustody(TransferProtected, Base):
    __tablename__ = 'vehicle_custodies'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    vin: Mapped[str] = mapped_column(String(17), unique=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey('group_identities.id'), unique=True)
    current_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey('vehicles.id'), nullable=True, unique=True)
    current_store_id: Mapped[int | None] = mapped_column(ForeignKey('stores.id'), nullable=True)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    pending_transfer_id: Mapped[int | None] = mapped_column(ForeignKey('vehicle_transfers.id'), nullable=True, unique=True)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (CheckConstraint('generation >= 0', name='ck_vehicle_custody_generation'),
        CheckConstraint('(current_vehicle_id IS NULL AND current_store_id IS NULL) OR (current_vehicle_id IS NOT NULL AND current_store_id IS NOT NULL)', name='ck_vehicle_custody_owner'))


class VehicleTransfer(TransferProtected, Base):
    __tablename__ = 'vehicle_transfers'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    number: Mapped[str] = mapped_column(String(60), unique=True)
    from_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    to_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    from_case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    to_case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    source_vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'))
    received_vehicle_id: Mapped[int | None] = mapped_column(ForeignKey('vehicles.id'), nullable=True, unique=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    source_approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    destination_approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='requested')
    reason: Mapped[str] = mapped_column(String(500))
    due_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (CheckConstraint('from_store_id != to_store_id', name='ck_vehicle_transfer_parties'),
        CheckConstraint("status IN ('requested','approved','transit','rejected','return_transit','accepted','returned','cancelled','lost','recovered')", name='ck_vehicle_transfer_status'))


class VehicleMovement(StoreScoped, Base):
    __tablename__ = 'vehicle_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey('vehicles.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer)
    value_cents: Mapped[int] = mapped_column(BigInteger)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(500))
    business_date: Mapped[date] = mapped_column(Date)
    __table_args__ = (UniqueConstraint('transfer_id','kind',name='uq_vehicle_movement_once'),
        CheckConstraint("(kind='dispatch' AND quantity=-1 AND value_cents<=0 AND vehicle_id IS NOT NULL) OR (kind IN ('accept','return_receive') AND quantity=1 AND value_cents>=0 AND vehicle_id IS NOT NULL) OR (kind IN ('reject','return_ship') AND quantity=0 AND value_cents=0 AND vehicle_id IS NULL)",name='ck_vehicle_movement_sign'))


class VehicleTransferSettlement(StoreScoped, Base):
    __tablename__ = 'vehicle_transfer_settlements'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('vehicle_transfers.id'))
    counterparty_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint('transfer_id','store_id',name='uq_vehicle_settlement_party'),)


@event.listens_for(Session,'before_flush')
def protect_vehicle_facts(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,(VehicleMovement,VehicleTransferSettlement)):
            raise HTTPException(409,'整车交接与往来事实不可覆盖')
        if isinstance(row,VehicleCustody) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('vin','identity_id'))):
            raise HTTPException(409,'车辆共享身份不可覆盖')
        if isinstance(row,VehicleTransfer):
            frozen=('number','from_store_id','to_store_id','from_case_id','to_case_id','source_vehicle_id','vin','snapshot','requested_by','reason','due_date')
            if row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen):raise HTTPException(409,'整车调拨申请事实不可覆盖')
        if isinstance(row,Vehicle) and inspect(row).attrs.inventory_generation.history.has_changes():
            raise HTTPException(409,'整车库存批次不可修改')
        if isinstance(row,Vehicle) and row.approval_state!='draft' and inspect(row).attrs.vin.history.has_changes():
            raise HTTPException(409,'已提交车辆的VIN身份不可覆盖，请核对原库存记录')
    for row in db.new:
        if isinstance(row,Vehicle) and row.inventory_generation and not db.info.get('_transfer_authority'):
            raise HTTPException(403,'跨店接收库存只能由授权调拨服务生成')
