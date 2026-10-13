"""Append-only employee handovers; original business ownership never changes."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import ForeignKey, Integer, String, Boolean, DateTime, UniqueConstraint, CheckConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow


class EmployeeHandover(Base):
    __tablename__ = 'employee_handovers'
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    successor_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    successor_role: Mapped[str] = mapped_column(String(30))
    successor_access_version: Mapped[int] = mapped_column(Integer)
    receipt_id: Mapped[int] = mapped_column(ForeignKey('user_access_receipts.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('receipt_id', 'store_id', name='uq_employee_handover_store'),
        CheckConstraint('source_id != successor_id', name='ck_employee_handover_distinct'),
        CheckConstraint('successor_access_version >= 1', name='ck_employee_handover_version'))


class EmployeeHandoverRecord(Base):
    __tablename__ = 'employee_handover_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    handover_id: Mapped[int] = mapped_column(ForeignKey('employee_handovers.id'), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_customers.id'), nullable=True, index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey('business_record_contracts.id'), nullable=True, index=True)
    can_continue: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (UniqueConstraint('handover_id', 'customer_id', name='uq_employee_handover_customer'),
        UniqueConstraint('handover_id', 'contract_id', name='uq_employee_handover_contract'),
        CheckConstraint('(customer_id IS NULL) != (contract_id IS NULL)', name='ck_employee_handover_one_record'))


@event.listens_for(Session, 'before_flush')
def immutable_handovers(db, *_):
    if any(isinstance(row, (EmployeeHandover, EmployeeHandoverRecord)) and
           (row in db.deleted or db.is_modified(row)) for row in set(db.dirty) | set(db.deleted)):
        raise HTTPException(409, '员工交接历史不可改写或删除；再次交接请按当前接手人办理')
