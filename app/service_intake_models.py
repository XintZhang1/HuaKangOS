"""Service reservations, verified vehicle identity, and explicit rework liability."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Boolean,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned

class ServiceResource(Versioned,Base):
    __tablename__='intake_resources'
    code:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    resource_type:Mapped[str]=mapped_column(String(20))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    active_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,unique=True)
    __table_args__=(UniqueConstraint('store_id','code',name='uq_intake_resource_code'),CheckConstraint("resource_type IN ('repair','wash')",name='ck_intake_resource_type'),)

class QuickPreset(Versioned,Base):
    __tablename__='intake_presets'
    code:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    profile:Mapped[str]=mapped_column(String(20))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('store_id','code',name='uq_intake_preset_code'),CheckConstraint("profile IN ('wash','quick')",name='ck_intake_preset_profile'),)

class QuickPresetLine(StoreScoped,Base):
    __tablename__='intake_preset_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    preset_id:Mapped[int]=mapped_column(ForeignKey('intake_presets.id'),index=True)
    work_item_id:Mapped[int]=mapped_column(ForeignKey('master_work_items.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('preset_id','work_item_id',name='uq_intake_preset_work'),CheckConstraint('quantity_milli>0',name='ck_intake_preset_quantity'),)

class ServiceAppointment(Versioned,Base):
    __tablename__='intake_appointments'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    customer_vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    resource_id:Mapped[int]=mapped_column(ForeignKey('intake_resources.id'),index=True)
    starts_at:Mapped[datetime]=mapped_column(DateTime)
    ends_at:Mapped[datetime]=mapped_column(DateTime)
    mode:Mapped[str]=mapped_column(String(15),default='appointment')
    status:Mapped[str]=mapped_column(String(20),default='scheduled')
    problem:Mapped[str]=mapped_column(String(1000))
    preset_id:Mapped[int|None]=mapped_column(ForeignKey('intake_presets.id'),nullable=True)
    repair_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint("mode IN ('appointment','walk_in') AND status IN ('scheduled','arrived','converted','cancelled','no_show') AND ends_at>starts_at",name='ck_intake_appointment'),)

class ArrivalFact(StoreScoped,Base):
    __tablename__='intake_arrivals'
    id:Mapped[int]=mapped_column(primary_key=True)
    appointment_id:Mapped[int]=mapped_column(ForeignKey('intake_appointments.id'),unique=True)
    customer_vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    checked_vin:Mapped[str]=mapped_column(String(17))
    odometer_km:Mapped[int]=mapped_column(Integer)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('odometer_km BETWEEN 0 AND 3000000',name='ck_intake_arrival_mileage'),)

class RepairVehicleBinding(StoreScoped,Base):
    __tablename__='intake_vehicle_bindings'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    customer_vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    customer_identity_id:Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vehicle_identity_id:Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vin:Mapped[str]=mapped_column(String(17))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    source_reference:Mapped[str]=mapped_column(String(500))
    reviewed_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class ReworkRequest(Versioned,Base):
    __tablename__='intake_rework_requests'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    source_quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    customer_vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    resource_id:Mapped[int]=mapped_column(ForeignKey('intake_resources.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    status:Mapped[str]=mapped_column(String(20),default='requested')
    active_source_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,unique=True)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    repair_case_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True,unique=True)
    __table_args__=(CheckConstraint("status IN ('requested','approved','rejected','cancelled','converted','completed')",name='ck_intake_rework_status'),)

class ReworkSourceLine(StoreScoped,Base):
    __tablename__='intake_rework_source_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('intake_rework_requests.id'),index=True)
    source_line_id:Mapped[int]=mapped_column(ForeignKey('repair_lines.id'))
    __table_args__=(UniqueConstraint('request_id','source_line_id',name='uq_intake_rework_line'),)

class ReworkLiability(StoreScoped,Base):
    __tablename__='intake_rework_liabilities'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('intake_rework_requests.id'),unique=True)
    reason:Mapped[str]=mapped_column(String(1000))
    internal_name:Mapped[str]=mapped_column(String(120))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    approved_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class RepairIntake(StoreScoped,Base):
    __tablename__='intake_repair_contexts'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    profile:Mapped[str]=mapped_column(String(20))
    resource_id:Mapped[int]=mapped_column(ForeignKey('intake_resources.id'))
    appointment_id:Mapped[int|None]=mapped_column(ForeignKey('intake_appointments.id'),nullable=True,unique=True)
    rework_id:Mapped[int|None]=mapped_column(ForeignKey('intake_rework_requests.id'),nullable=True,unique=True)
    preset_id:Mapped[int|None]=mapped_column(ForeignKey('intake_presets.id'),nullable=True)
    __table_args__=(CheckConstraint("profile IN ('regular','wash','quick','rework') AND ((rework_id IS NOT NULL AND appointment_id IS NULL AND profile='rework') OR (appointment_id IS NOT NULL AND rework_id IS NULL AND profile!='rework'))",name='ck_intake_context'),)

class ResourceUse(StoreScoped,Base):
    __tablename__='intake_resource_uses'
    id:Mapped[int]=mapped_column(primary_key=True)
    resource_id:Mapped[int]=mapped_column(ForeignKey('intake_resources.id'),index=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    action:Mapped[str]=mapped_column(String(10))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    reason:Mapped[str]=mapped_column(String(500))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("action IN ('acquire','release')",name='ck_intake_resource_use'),)

class IntakeReceipt(StoreScoped,Base):
    __tablename__='intake_command_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_intake_request_key'),)

IMMUTABLE=(QuickPresetLine,ArrivalFact,RepairVehicleBinding,ReworkSourceLine,ReworkLiability,RepairIntake,ResourceUse,IntakeReceipt)
@event.listens_for(Session,'before_flush')
def protect_intake_facts(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,IMMUTABLE):raise HTTPException(409,'到店、车辆绑定、返修责任和资源实际交接事实不能覆盖；请追加处理记录')
        if isinstance(row,ServiceAppointment) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','customer_vehicle_id','mode'))):raise HTTPException(409,'预约身份不能覆盖；请取消后重新登记')
        if isinstance(row,ReworkRequest) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','source_case_id','source_quote_id','customer_vehicle_id','requested_by','reason'))):raise HTTPException(409,'返修原单与申请事实不能覆盖')
