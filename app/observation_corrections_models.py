"""Append-only corrections and reminder lineage; no original observation is edited."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String,Text,Integer,Boolean,ForeignKey,DateTime,JSON,CheckConstraint,UniqueConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped

class Fact:
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class Protected:pass

class ObservationCorrection(Protected,StoreScoped,Base):
    __tablename__='observation_corrections'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'),index=True)
    observation_id:Mapped[int]=mapped_column(ForeignKey('care_vehicle_observations.id'),index=True)
    base_digest:Mapped[str]=mapped_column(String(64))
    original_snapshot:Mapped[dict]=mapped_column(JSON)
    operation:Mapped[str]=mapped_column(String(12))
    proposed:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str]=mapped_column(Text)
    __table_args__=(CheckConstraint("operation IN ('replace','retract')",name='ck_observation_correction_operation'),)

class CorrectionEvent(Protected,Fact,StoreScoped,Base):
    __tablename__='observation_correction_events'
    case_id:Mapped[int]=mapped_column(ForeignKey('observation_corrections.case_id'),index=True)
    action:Mapped[str]=mapped_column(String(15))
    reason:Mapped[str]=mapped_column(Text)
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    __table_args__=(UniqueConstraint('case_id','action',name='uq_observation_correction_event'),CheckConstraint("action IN ('create','submit','approve','reject','cancel')",name='ck_observation_correction_event'),)

class CorrectionEffect(Protected,Fact,StoreScoped,Base):
    __tablename__='observation_correction_effects'
    case_id:Mapped[int]=mapped_column(ForeignKey('observation_corrections.case_id'),unique=True)
    observation_id:Mapped[int]=mapped_column(ForeignKey('care_vehicle_observations.id'),index=True)
    parent_effect_id:Mapped[int|None]=mapped_column(ForeignKey('observation_correction_effects.id'),nullable=True)
    parent_token:Mapped[str]=mapped_column(String(40))
    review_event_id:Mapped[int]=mapped_column(ForeignKey('observation_correction_events.id'),unique=True)
    __table_args__=(UniqueConstraint('observation_id','parent_token',name='uq_observation_correction_head'),)

class InsuranceBasisInvalidation(Protected,Fact,StoreScoped,Base):
    __tablename__='observation_insurance_invalidations'
    source_case_id:Mapped[int]=mapped_column(ForeignKey('insurance_orders.id'))
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'),index=True)
    observation_id:Mapped[int]=mapped_column(ForeignKey('care_vehicle_observations.id'),unique=True)
    result_id:Mapped[int]=mapped_column(ForeignKey('insurance_results.id'),unique=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('insurance_terminations.id'))
    application_id:Mapped[int]=mapped_column(ForeignKey('insurance_termination_applications.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))

class ReminderBasis(Protected,StoreScoped,Base):
    __tablename__='observation_reminder_bases'
    case_id:Mapped[int]=mapped_column(ForeignKey('care_cases.case_id'),primary_key=True)
    vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'),index=True)
    baseline_id:Mapped[int]=mapped_column(ForeignKey('care_vehicle_observations.id'))
    current_id:Mapped[int|None]=mapped_column(ForeignKey('care_vehicle_observations.id'),nullable=True)
    baseline_effect_id:Mapped[int|None]=mapped_column(ForeignKey('observation_correction_effects.id'),nullable=True)
    current_effect_id:Mapped[int|None]=mapped_column(ForeignKey('observation_correction_effects.id'),nullable=True)
    cycle_key:Mapped[str]=mapped_column(String(120),index=True)
    snapshot:Mapped[dict]=mapped_column(JSON)

class ReminderInvalidation(Protected,Fact,StoreScoped,Base):
    __tablename__='observation_reminder_invalidations'
    case_id:Mapped[int]=mapped_column(ForeignKey('care_cases.case_id'),index=True)
    correction_case_id:Mapped[int|None]=mapped_column(ForeignKey('observation_corrections.case_id'),nullable=True)
    insurance_invalidation_id:Mapped[int|None]=mapped_column(ForeignKey('observation_insurance_invalidations.id'),nullable=True)
    observation_id:Mapped[int]=mapped_column(ForeignKey('care_vehicle_observations.id'))
    previous_state:Mapped[str]=mapped_column(String(30))
    closed_open_task:Mapped[bool]=mapped_column(Boolean)
    source_key:Mapped[str]=mapped_column(String(80))
    __table_args__=(UniqueConstraint('case_id','source_key',name='uq_observation_reminder_invalidation'),CheckConstraint('(correction_case_id IS NULL) != (insurance_invalidation_id IS NULL)',name='ck_observation_reminder_source'),)

class ReminderReplacement(Protected,Fact,StoreScoped,Base):
    __tablename__='observation_reminder_replacements'
    previous_case_id:Mapped[int]=mapped_column(ForeignKey('care_cases.case_id'))
    replacement_case_id:Mapped[int]=mapped_column(ForeignKey('care_cases.case_id'))
    __table_args__=(UniqueConstraint('previous_case_id','replacement_case_id',name='uq_observation_reminder_replacement'),CheckConstraint('previous_case_id!=replacement_case_id',name='ck_observation_reminder_replacement'),)

class CorrectionReceipt(Protected,Fact,StoreScoped,Base):
    __tablename__='observation_correction_receipts'
    request_key:Mapped[str]=mapped_column(String(80))
    digest:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_observation_correction_receipt'),)

@event.listens_for(Session,'before_flush')
def protect_observation_corrections(db,*_):
    if any(isinstance(r,Protected) for r in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'观察纠正、原业务失效与提醒来源不可覆盖，请另行有据纠正')
    if any(isinstance(r,Protected) for r in db.new) and not db.info.get('_observation_authority'):
        raise HTTPException(403,'观察纠正须通过获权的原单办理入口')
