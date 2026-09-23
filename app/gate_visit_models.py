"""Actual non-repair attendance, immutable origins and independently reviewed corrections.

A gate record has no ownership, inventory, revenue or cash effect. A handoff reuses
one original arrival; it is not a second physical arrival.
"""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped
from .flow_models import Versioned


class GateVisit(Versioned, Base):
    __tablename__ = 'gate_visits'
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    customer_vehicle_id: Mapped[int] = mapped_column(ForeignKey('care_customer_vehicles.id'))
    vin: Mapped[str] = mapped_column(String(17), index=True)
    purpose: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default='planned')
    __table_args__ = (CheckConstraint("purpose IN ('consultation','inspection','accessory','delivery','other') AND status IN ('planned','inside','departed','cancelled','voided','handed_over')", name='ck_gate_visit_state'),)


class GateFact(StoreScoped, Base):
    __tablename__ = 'gate_facts'
    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey('gate_visits.id'), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    actual_at: Mapped[datetime] = mapped_column(DateTime)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('visit_id', 'direction', name='uq_gate_visit_direction'), CheckConstraint("direction IN ('arrive','leave') AND actual_at<=created_at", name='ck_gate_fact'),)


class GateCorrection(Versioned, Base):
    __tablename__ = 'gate_corrections'
    visit_id: Mapped[int] = mapped_column(ForeignKey('gate_visits.id'), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    actual_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    origin_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default='pending')
    active_visit_id: Mapped[int | None] = mapped_column(ForeignKey('gate_visits.id'), nullable=True, unique=True)
    __table_args__ = (CheckConstraint("kind IN ('arrive_time','leave_time','void_visit') AND status IN ('pending','approved','rejected','cancelled') AND ((kind='void_visit' AND actual_at IS NULL) OR (kind!='void_visit' AND actual_at IS NOT NULL)) AND ((status='pending' AND active_visit_id IS NOT NULL AND active_visit_id=visit_id) OR (status!='pending' AND active_visit_id IS NULL))", name='ck_gate_correction'),)


class GateReview(StoreScoped, Base):
    __tablename__ = 'gate_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    correction_id: Mapped[int] = mapped_column(ForeignKey('gate_corrections.id'), unique=True)
    decision: Mapped[str] = mapped_column(String(12))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("decision IN ('approved','rejected')", name='ck_gate_review'),)


class GateHandoff(StoreScoped, Base):
    __tablename__ = 'gate_handoffs'
    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey('gate_visits.id'), unique=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey('intake_appointments.id'), unique=True)
    arrival_fact_id: Mapped[int] = mapped_column(ForeignKey('intake_arrivals.id'), unique=True)
    origin_fact_id: Mapped[int] = mapped_column(ForeignKey('gate_facts.id'), unique=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    origin_digest: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RepairGateExit(StoreScoped, Base):
    __tablename__ = 'gate_repair_exits'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), unique=True)
    actual_at: Mapped[datetime] = mapped_column(DateTime)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('actual_at<=created_at', name='ck_gate_repair_exit'),)


IMMUTABLE = (GateFact, GateReview, GateHandoff, RepairGateExit)


@event.listens_for(Session, 'before_flush')
def protect_gate_facts(db, *_):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, IMMUTABLE):
            raise HTTPException(409, '实际进出厂、复核及转接来源不能覆盖；请提交有据纠正')
        fields = ()
        if isinstance(row, GateVisit):
            fields = ('case_id', 'customer_vehicle_id', 'vin', 'purpose', 'description')
        elif isinstance(row, GateCorrection):
            fields = ('visit_id', 'kind', 'actual_at', 'evidence_id', 'reason', 'requested_by', 'origin_digest')
        if fields and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in fields)):
            raise HTTPException(409, '原登记身份和纠正申请不可改写；未实际进厂可取消后重建')
