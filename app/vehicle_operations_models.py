"""Typed vehicle positions, physical operations and immutable return inspections."""
from datetime import date
from sqlalchemy import String,Integer,BigInteger,Date,ForeignKey,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from fastapi import HTTPException
from .db import Base
from .models import StoreScoped
from .flow_models import Versioned
from .transfer_models import TransferProtected


class VehiclePosition(Versioned,Base):
    __tablename__='vehicle_positions'
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'),unique=True)
    location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    status:Mapped[str]=mapped_column(String(20),default='stored')
    __table_args__=(CheckConstraint("status IN ('stored','transit','handover','exited')",name='ck_vposition_status'),
        CheckConstraint("(status='stored' AND location_id IS NOT NULL) OR (status!='stored' AND location_id IS NULL)",name='ck_vposition_location'))


class VehicleOperation(StoreScoped,Base):
    __tablename__='vehicle_operations'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    kind:Mapped[str]=mapped_column(String(25))
    status:Mapped[str]=mapped_column(String(30),default='requested')
    source_vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'),index=True)
    source_generation:Mapped[int]=mapped_column(Integer)
    vin:Mapped[str]=mapped_column(String(17),index=True)
    source_location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    destination_location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    original_operation_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_operations.id'),nullable=True)
    aftercare_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,unique=True)
    source_order_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True)
    authorization_evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    received_vehicle_id:Mapped[int|None]=mapped_column(ForeignKey('vehicles.id'),nullable=True,unique=True)
    cost_cents:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(500))
    recipient:Mapped[str]=mapped_column(String(180),default='')
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("kind IN ('locate','local_move','other_out','other_return','customer_return')",name='ck_voperation_kind'),
        CheckConstraint('source_generation >= 0 AND cost_cents >= 0',name='ck_voperation_value'),
        CheckConstraint("status IN ('requested','approved','transit','returning','completed','cancelled','rejected','awaiting_receipt','quarantined','inspected','rectifying','release_approved','return_to_customer','accepted','returned_to_customer')",name='ck_voperation_status'))


class VehicleOperationClaim(TransferProtected,Base):
    # A global boolean conflict check is necessary across stores. Never serialize
    # a foreign claim; custody's shared authority also protects this table.
    __tablename__='vehicle_operation_claims'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('vehicle_operations.id'),unique=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    vin:Mapped[str]=mapped_column(String(17))
    active_vin:Mapped[str|None]=mapped_column(String(17),nullable=True,unique=True)
    __table_args__=(CheckConstraint('active_vin IS NULL OR active_vin=vin',name='ck_voperation_claim'),)


class VehiclePositionEntry(StoreScoped,Base):
    __tablename__='vehicle_position_entries'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    operation_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_operations.id'),nullable=True,index=True)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'),index=True)
    location_id:Mapped[int|None]=mapped_column(ForeignKey('master_locations.id'),nullable=True)
    kind:Mapped[str]=mapped_column(String(35))
    quantity:Mapped[int]=mapped_column(Integer)
    inventory_delta:Mapped[int]=mapped_column(Integer,default=0)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    original_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_position_entries.id'),nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    reason:Mapped[str]=mapped_column(String(500))
    __table_args__=(UniqueConstraint('case_id','vehicle_id','kind',name='uq_vposition_entry_once'),
        CheckConstraint('quantity BETWEEN -1 AND 1 AND inventory_delta BETWEEN -1 AND 1',name='ck_vposition_entry_qty'),
        CheckConstraint('(quantity=1 AND value_cents>=0) OR (quantity=-1 AND value_cents<=0) OR (quantity=0 AND value_cents=0)',name='ck_vposition_entry_value'))


class VehicleOperationReview(StoreScoped,Base):
    __tablename__='vehicle_operation_reviews'
    id:Mapped[int]=mapped_column(primary_key=True)
    operation_id:Mapped[int]=mapped_column(ForeignKey('vehicle_operations.id'),index=True)
    decision:Mapped[str]=mapped_column(String(25))
    inspection_id:Mapped[int|None]=mapped_column(ForeignKey('vehicle_return_inspections.id'),nullable=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(500))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint("decision IN ('approve','reject','release','rectify','return_to_customer')",name='ck_voperation_review'),)


class VehicleReturnInspection(StoreScoped,Base):
    __tablename__='vehicle_return_inspections'
    id:Mapped[int]=mapped_column(primary_key=True)
    operation_id:Mapped[int]=mapped_column(ForeignKey('vehicle_operations.id'),index=True)
    outcome:Mapped[str]=mapped_column(String(10))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    findings:Mapped[str]=mapped_column(String(1000))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(CheckConstraint("outcome IN ('pass','fail')",name='ck_vreturn_inspection'),)


class VehicleQuarantineFact(StoreScoped,Base):
    __tablename__='vehicle_quarantine_facts'
    id:Mapped[int]=mapped_column(primary_key=True)
    operation_id:Mapped[int]=mapped_column(ForeignKey('vehicle_operations.id'),index=True)
    kind:Mapped[str]=mapped_column(String(25))
    location_id:Mapped[int]=mapped_column(ForeignKey('master_locations.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(500))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('operation_id','kind',name='uq_vquarantine_fact'),CheckConstraint("kind IN ('intake','release','return_to_customer')",name='ck_vquarantine_kind'))


class VehicleOrderHoldRelease(StoreScoped,Base):
    __tablename__='vehicle_order_hold_releases'
    id:Mapped[int]=mapped_column(primary_key=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    aftercare_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('vehicles.id'))
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)


@event.listens_for(Session,'before_flush')
def protect_vehicle_operations(db,*_):
    facts=(VehiclePositionEntry,VehicleOperationReview,VehicleReturnInspection,VehicleQuarantineFact,VehicleOrderHoldRelease)
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,facts):raise HTTPException(409,'车辆定位、交接、检查与释放事实不可覆盖')
        if isinstance(row,VehicleOperation):
            frozen=set(row.__table__.columns.keys())-{'status','received_vehicle_id'}
            if row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in frozen):raise HTTPException(409,'车辆作业来源与原成本不可覆盖')
        if isinstance(row,VehicleOperationClaim) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','store_id','vin'))):
            raise HTTPException(409,'车辆作业占用来源不可覆盖')
