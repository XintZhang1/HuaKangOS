"""Physical bin balances and attributable, append-only warehouse observations."""
from datetime import date,datetime
from sqlalchemy import String,BigInteger,Integer,Date,DateTime,ForeignKey,UniqueConstraint,CheckConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from fastapi import HTTPException
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class WarehouseDocument(StoreScoped,Base):
    __tablename__='warehouse_documents'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    operation:Mapped[str]=mapped_column(String(24))
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),index=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    source_location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    destination_location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    original_move_id:Mapped[int|None]=mapped_column(ForeignKey('flow_stock_moves.id'),nullable=True)
    reason:Mapped[str]=mapped_column(String(500))
    recipient:Mapped[str]=mapped_column(String(120),default='')
    baseline_quantity_milli:Mapped[int]=mapped_column(BigInteger,default=0)
    baseline_value_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    baseline_item_version:Mapped[int]=mapped_column(Integer)
    __table_args__=(CheckConstraint("operation IN ('activate','other_in','other_in_return','consumable','consumable_return','gift','gift_return','disposal','local_move','count')",name='ck_warehouse_operation'),CheckConstraint('quantity_milli>=0',name='ck_warehouse_doc_qty'))


class WarehouseApproval(StoreScoped,Base):
    __tablename__='warehouse_approvals'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    value_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('value_cents>=0',name='ck_warehouse_approval_value'),)


class WarehouseEnrollment(StoreScoped,Base):
    __tablename__='warehouse_enrollments'
    id:Mapped[int]=mapped_column(primary_key=True)
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),unique=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    baseline_quantity_milli:Mapped[int]=mapped_column(BigInteger)
    baseline_value_cents:Mapped[int]=mapped_column(BigInteger)
    stock_move_cursor:Mapped[int]=mapped_column(Integer)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))


class WarehouseBalance(Versioned,Base):
    __tablename__='warehouse_balances'
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),index=True)
    bucket:Mapped[str]=mapped_column(String(60))
    location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    transit_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger,default=0)
    value_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    __table_args__=(UniqueConstraint('store_id','item_id','bucket',name='uq_warehouse_bucket'),CheckConstraint('quantity_milli>=0 AND value_cents>=0 AND (quantity_milli>0 OR value_cents=0)',name='ck_warehouse_balance'),CheckConstraint('(location_id IS NOT NULL AND transit_case_id IS NULL) OR (location_id IS NULL AND transit_case_id IS NOT NULL)',name='ck_warehouse_bucket_kind'))


class WarehouseEntry(StoreScoped,Base):
    __tablename__='warehouse_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    balance_id:Mapped[int]=mapped_column(ForeignKey('warehouse_balances.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    stock_move_id:Mapped[int|None]=mapped_column(ForeignKey('flow_stock_moves.id'),nullable=True,index=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(30))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class WarehouseHold(StoreScoped,Base):
    __tablename__='warehouse_holds'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),index=True)
    location_id:Mapped[int]=mapped_column(ForeignKey('master_locations.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(20))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("quantity_milli!=0 AND reason IN ('reserve','release')",name='ck_warehouse_hold'),)


class WarehouseAllocation(Versioned,Base):
    __tablename__='warehouse_allocations'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),index=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    purpose:Mapped[str]=mapped_column(String(30))
    status:Mapped[str]=mapped_column(String(20),default='prepared')
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    stock_move_id:Mapped[int|None]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True,nullable=True)
    __table_args__=(CheckConstraint("status IN ('prepared','consumed','cancelled')",name='ck_warehouse_allocation_state'),)


class WarehouseAllocationLine(StoreScoped,Base):
    __tablename__='warehouse_allocation_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    allocation_id:Mapped[int]=mapped_column(ForeignKey('warehouse_allocations.id'),index=True)
    location_id:Mapped[int]=mapped_column(ForeignKey('master_locations.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('allocation_id','location_id',name='uq_warehouse_allocation_location'),CheckConstraint('quantity_milli>=0',name='ck_warehouse_allocation_qty'))


class WarehouseCountObservation(StoreScoped,Base):
    __tablename__='warehouse_count_observations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    balance_id:Mapped[int]=mapped_column(ForeignKey('warehouse_balances.id'))
    baseline_quantity_milli:Mapped[int]=mapped_column(BigInteger)
    counted_quantity_milli:Mapped[int]=mapped_column(BigInteger)
    entry_cursor:Mapped[int]=mapped_column(Integer)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    observed_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('counted_quantity_milli>=0',name='ck_warehouse_count_observation'),)


APPEND_ONLY=(WarehouseDocument,WarehouseApproval,WarehouseEnrollment,WarehouseEntry,WarehouseHold,WarehouseAllocationLine,WarehouseCountObservation)
@event.listens_for(Session,'before_flush')
def immutable_warehouse_facts(db,context,instances):
    for obj in list(db.dirty)+list(db.deleted):
        if isinstance(obj,APPEND_ONLY) and (obj in db.deleted or db.is_modified(obj,include_collections=False)):
            raise HTTPException(409,'仓储原始记录不可覆盖或删除，请追加原单退回或差异处理记录')
