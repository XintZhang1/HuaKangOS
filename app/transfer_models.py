"""Paired inter-store material workflows. Central coordination is explicitly authorized."""
from datetime import datetime, date
from fastapi import HTTPException
from sqlalchemy import String, Integer, BigInteger, DateTime, Date, ForeignKey, JSON, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped


class TransferProtected:
    pass


class MaterialTransfer(TransferProtected, Base):
    __tablename__ = 'material_transfers'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    number: Mapped[str] = mapped_column(String(60), unique=True)
    from_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    to_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    from_case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    to_case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    source_approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    destination_approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='requested')
    reason: Mapped[str] = mapped_column(String(500))
    due_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (CheckConstraint('from_store_id != to_store_id', name='ck_material_transfer_stores'),
        CheckConstraint("status IN ('requested','approved','transit','completed','cancelled')", name='ck_material_transfer_status'))


class TransferLine(TransferProtected, Base):
    __tablename__ = 'material_transfer_lines'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('material_transfers.id'), index=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey('flow_items.id'))
    sku: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20))
    quantity_milli: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint('transfer_id','source_item_id',name='uq_material_transfer_item'),
                     CheckConstraint('quantity_milli > 0', name='ck_material_transfer_quantity'))


class TransferMovement(TransferProtected, Base):
    __tablename__ = 'material_transfer_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('material_transfers.id'), index=True)
    line_id: Mapped[int] = mapped_column(ForeignKey('material_transfer_lines.id'), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    kind: Mapped[str] = mapped_column(String(20))
    quantity_milli: Mapped[int] = mapped_column(BigInteger)
    value_cents: Mapped[int] = mapped_column(BigInteger)
    stock_move_id: Mapped[int | None] = mapped_column(ForeignKey('flow_stock_moves.id'), nullable=True, unique=True)
    original_id: Mapped[int | None] = mapped_column(ForeignKey('material_transfer_movements.id'), nullable=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(500), default='')
    __table_args__ = (CheckConstraint('quantity_milli > 0 AND value_cents >= 0',name='ck_transfer_movement_amount'),
        CheckConstraint("kind IN ('dispatch','accept','reject','return_ship','return_receive')",name='ck_transfer_movement_kind'))


class TransferSettlement(StoreScoped, Base):
    __tablename__ = 'material_transfer_settlements'
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey('material_transfers.id'), index=True)
    movement_id: Mapped[int] = mapped_column(ForeignKey('material_transfer_movements.id'))
    counterparty_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (UniqueConstraint('movement_id','store_id',name='uq_transfer_settlement_party'),)


class TransferReceipt(StoreScoped, Base):
    __tablename__ = 'material_transfer_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('store_id','request_key',name='uq_material_transfer_request'),)


@event.listens_for(Session, 'before_flush')
def protect_transfers(db, *_):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row,(TransferLine,TransferMovement,TransferSettlement,TransferReceipt)):
            raise HTTPException(409,'调拨事实与往来记录不可覆盖，请通过退回追加记录')
        if isinstance(row,MaterialTransfer):
            frozen=('from_store_id','to_store_id','from_case_id','to_case_id','requested_by','reason','due_date','number')
            if row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen):
                raise HTTPException(409,'调拨申请事实不可覆盖；未发出前可撤销另行申请')
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,TransferProtected) and not db.info.get('_transfer_authority'):
            raise HTTPException(403,'调拨协调记录须通过授权调拨服务办理')


@event.listens_for(Session, 'do_orm_execute')
def protect_transfer_queries(state):
    if any(issubclass(m.class_,TransferProtected) for m in state.all_mappers):
        if not state.session.info.get('_transfer_authority'):
            raise HTTPException(403,'调拨记录须通过授权调拨服务查询')
        if state.is_update or state.is_delete:
            raise HTTPException(409,'调拨不得绕过版本动作批量修改')
