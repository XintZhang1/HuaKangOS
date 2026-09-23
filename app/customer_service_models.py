"""Customer-owned vehicles and attributable service observations, never stock ownership."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,Boolean,Date,DateTime,Text,ForeignKey,JSON,UniqueConstraint,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session,declared_attr
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class CustomerVehicle(Versioned,Base):
    __tablename__='care_customer_vehicles'
    customer_id: Mapped[int]=mapped_column(ForeignKey('flow_customers.id'),index=True)
    customer_identity_id: Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vehicle_identity_id: Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vin: Mapped[str]=mapped_column(String(17))
    plate: Mapped[str]=mapped_column(String(30),default='')
    model_name: Mapped[str]=mapped_column(String(120))
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    identity_source: Mapped[str]=mapped_column(String(180))
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('store_id','customer_id','vehicle_identity_id',name='uq_care_customer_vehicle'),)


class VehicleObservation(StoreScoped,Base):
    __tablename__='care_vehicle_observations'
    id: Mapped[int]=mapped_column(primary_key=True)
    vehicle_id: Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'),index=True)
    kind: Mapped[str]=mapped_column(String(20))
    observed_date: Mapped[date]=mapped_column(Date)
    odometer_km: Mapped[int]=mapped_column(Integer)
    valid_until: Mapped[date|None]=mapped_column(Date,nullable=True)
    source_reference: Mapped[str]=mapped_column(String(180))
    evidence_id: Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("kind IN ('delivery','odometer','maintenance','first_service','insurance','warranty') AND odometer_km BETWEEN 0 AND 3000000",name='ck_care_observation'),)


class CareCase(StoreScoped,Base):
    __tablename__='care_cases'
    case_id: Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    subtype: Mapped[str]=mapped_column(String(25))
    vehicle_id: Mapped[int|None]=mapped_column(ForeignKey('care_customer_vehicles.id'),nullable=True,index=True)
    source_case_id: Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True)
    topic: Mapped[str]=mapped_column(String(120))
    description: Mapped[str]=mapped_column(Text)
    location: Mapped[str]=mapped_column(String(250),default='')
    priority: Mapped[str]=mapped_column(String(10),default='normal')
    reminder_key: Mapped[str|None]=mapped_column(String(120),nullable=True,unique=True)
    rule_id: Mapped[int|None]=mapped_column(ForeignKey('care_reminder_rules.id'),nullable=True)
    rule_version: Mapped[int|None]=mapped_column(Integer,nullable=True)
    baseline_observation_id: Mapped[int|None]=mapped_column(ForeignKey('care_vehicle_observations.id'),nullable=True)
    generation_mode: Mapped[str]=mapped_column(String(20),default='manual')
    rule_approved_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    result: Mapped[str]=mapped_column(String(25),default='')
    __table_args__=(CheckConstraint("subtype IN ('questionnaire','consultation','complaint','rescue','sales_callback','repair_callback','first_service','maintenance','warranty','renewal') AND priority IN ('normal','urgent')",name='ck_care_case_type'),)


class CareRecord(StoreScoped,Base):
    __tablename__='care_records'
    id: Mapped[int]=mapped_column(primary_key=True)
    case_id: Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    action: Mapped[str]=mapped_column(String(25))
    note: Mapped[str]=mapped_column(Text)
    details: Mapped[dict]=mapped_column(JSON,default=dict)
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ReminderRule(Versioned,Base):
    __tablename__='care_reminder_rules'
    name: Mapped[str]=mapped_column(String(120))
    kind: Mapped[str]=mapped_column(String(20))
    interval_days: Mapped[int]=mapped_column(Integer,default=0)
    interval_km: Mapped[int]=mapped_column(Integer,default=0)
    lead_days: Mapped[int]=mapped_column(Integer,default=0)
    lead_km: Mapped[int]=mapped_column(Integer,default=0)
    assignee_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('store_id','kind',name='uq_care_rule_kind'),CheckConstraint("kind IN ('first_service','maintenance','warranty','renewal') AND interval_days BETWEEN 0 AND 3650 AND interval_km BETWEEN 0 AND 1000000 AND lead_days BETWEEN 0 AND 365 AND lead_km BETWEEN 0 AND 100000",name='ck_care_reminder_rule'),)


class ServiceHistoryLink(StoreScoped,Base):
    __tablename__='care_history_links'
    id: Mapped[int]=mapped_column(primary_key=True)
    vehicle_id: Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'),index=True)
    case_id: Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    summary: Mapped[str]=mapped_column(String(600))
    source_reference: Mapped[str]=mapped_column(String(180))
    confirmed_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('vehicle_id','case_id',name='uq_care_history_case'),)


class CareProtected:
    """Explicit two-party grants; no generic scope bypass is exposed."""


class HistoryGrant(CareProtected,Base):
    __tablename__='care_history_grants'
    id: Mapped[int]=mapped_column(primary_key=True)
    version: Mapped[int]=mapped_column(Integer,default=1)
    from_store_id: Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    to_store_id: Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    from_vehicle_id: Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    to_vehicle_id: Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    customer_identity_id: Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vehicle_identity_id: Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    valid_until: Mapped[date]=mapped_column(Date)
    status: Mapped[str]=mapped_column(String(12),default='active')
    active_pair: Mapped[str|None]=mapped_column(String(80),nullable=True,unique=True)
    source_reference: Mapped[str]=mapped_column(String(180))
    granted_by: Mapped[int]=mapped_column(ForeignKey('users.id'))
    revoked_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    revoke_reason: Mapped[str]=mapped_column(String(250),default='')
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __mapper_args__={'version_id_col':version}
    __table_args__=(CheckConstraint("from_store_id != to_store_id AND status IN ('active','revoked')",name='ck_care_history_grant'),)


class CareReceipt(StoreScoped,Base):
    __tablename__='care_receipts'
    id: Mapped[int]=mapped_column(primary_key=True)
    request_key: Mapped[str]=mapped_column(String(80))
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest: Mapped[str]=mapped_column(String(64))
    result: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_care_request'),)


@event.listens_for(Session,'before_flush')
def protect_care_facts(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,(VehicleObservation,CareRecord,ServiceHistoryLink,CareReceipt)):
            raise HTTPException(409,'里程日期来源、服务记录与回执不可覆盖，请追加新的事实记录')
        if isinstance(row,CustomerVehicle) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('customer_id','customer_identity_id','vehicle_identity_id','vin','identity_source','created_by'))):
            raise HTTPException(409,'客户车辆身份与归属关系不可覆盖，请另建经确认的关系')
        if isinstance(row,HistoryGrant) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('from_store_id','to_store_id','from_vehicle_id','to_vehicle_id','customer_identity_id','vehicle_identity_id','valid_until','source_reference','granted_by'))):
            raise HTTPException(409,'服务历史授权范围不可覆盖，请撤销后重新授权')
    if any(isinstance(row,CareProtected) for row in list(db.new)+list(db.dirty)+list(db.deleted)) and not db.info.get('_care_authority'):
        raise HTTPException(403,'服务历史授权必须经过客户服务权限校验')


@event.listens_for(Session,'do_orm_execute')
def protect_care_queries(state):
    if any(issubclass(m.class_,CareProtected) for m in state.all_mappers):
        if not state.session.info.get('_care_authority'):raise HTTPException(403,'服务历史授权必须经过客户服务权限查询')
        if state.is_update or state.is_delete:raise HTTPException(409,'服务历史授权不允许批量覆盖')
