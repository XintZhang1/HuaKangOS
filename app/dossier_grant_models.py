"""Explicit, versioned, read-only original-record/per-file grants.

Central rows are not ordinary cross-store queryable resources. Immutable scope,
independent decisions, exact file identities and minimal receipts are retained.
"""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import (String, Integer, Boolean, DateTime, ForeignKey, JSON,
                        UniqueConstraint, CheckConstraint, event, inspect)
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, utcnow
from .models import StoreScoped


class DossierProtected:
    pass


class DossierGrant(DossierProtected, Base):
    __tablename__ = 'dossier_grants'
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    from_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    to_store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    source_case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'), index=True)
    source_case_version: Mapped[int] = mapped_column(Integer)
    recipient_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    recipient_role: Mapped[str] = mapped_column(String(20))
    recipient_access_version: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    requester_role: Mapped[str] = mapped_column(String(20))
    requester_access_version: Mapped[int] = mapped_column(Integer)
    include_record: Mapped[bool] = mapped_column(Boolean)
    include_financials: Mapped[bool] = mapped_column(Boolean)
    include_contact: Mapped[bool] = mapped_column(Boolean)
    record_snapshot: Mapped[dict] = mapped_column(JSON)
    scope_digest: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(12), default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (
        CheckConstraint("from_store_id != to_store_id AND source_case_version > 0 "
                        "AND recipient_access_version > 0 AND requester_access_version > 0 "
                        "AND version > 0 AND expires_at > created_at "
                        "AND status IN ('pending','approved','rejected','cancelled','revoked')",
                        name='ck_dossier_grant'),
        CheckConstraint('(include_financials = false OR include_record = true) AND '
                        '(include_contact = false OR include_record = true)', name='ck_dossier_record_scope'),
    )


class DossierGrantFile(DossierProtected, Base):
    __tablename__ = 'dossier_grant_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey('dossier_grants.id'), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    metadata_snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('grant_id', 'file_id', name='uq_dossier_grant_file'),)


class DossierDecision(DossierProtected, Base):
    __tablename__ = 'dossier_decisions'
    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey('dossier_grants.id'), index=True)
    previous_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(12))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    actor_role: Mapped[str] = mapped_column(String(20))
    actor_access_version: Mapped[int] = mapped_column(Integer)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    scope_digest: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        UniqueConstraint('grant_id', 'previous_version', name='uq_dossier_decision_version'),
        CheckConstraint("previous_version > 0 AND actor_access_version > 0 AND "
                        "action IN ('approve','reject','cancel','revoke')", name='ck_dossier_decision'),
    )


class DossierAccess(DossierProtected, Base):
    __tablename__ = 'dossier_accesses'
    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey('dossier_grants.id'), index=True)
    grant_version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    actor_role: Mapped[str] = mapped_column(String(20))
    actor_access_version: Mapped[int] = mapped_column(Integer)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'))
    action: Mapped[str] = mapped_column(String(10))
    file_id: Mapped[int | None] = mapped_column(ForeignKey('flow_files.id'), nullable=True)
    scope_digest: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (
        CheckConstraint("grant_version > 0 AND actor_access_version > 0 AND "
                        "((action IN ('record','directory') AND file_id IS NULL) OR (action='file' AND file_id IS NOT NULL))",
                        name='ck_dossier_access'),
    )


class DossierReceipt(StoreScoped, Base):
    __tablename__ = 'dossier_receipts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(12))
    request_data: Mapped[dict] = mapped_column(JSON)
    grant_id: Mapped[int] = mapped_column(ForeignKey('dossier_grants.id'))
    scope_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('store_id', 'request_key', name='uq_dossier_receipt'),)


IMMUTABLE = (DossierGrantFile, DossierDecision, DossierAccess, DossierReceipt)
SCOPE_FIELDS = ('from_store_id', 'to_store_id', 'source_case_id', 'source_case_version',
    'recipient_id', 'recipient_role', 'recipient_access_version', 'requested_by',
    'requester_role', 'requester_access_version', 'include_record', 'include_financials',
    'include_contact', 'record_snapshot', 'scope_digest', 'purpose', 'expires_at', 'created_at')


@event.listens_for(Session, 'before_flush')
def protect_dossier_writes(db, *_):
    rows = set(db.new) | set(db.dirty) | set(db.deleted)
    if any(isinstance(row, (DossierProtected, DossierReceipt)) for row in rows):
        if not db.info.get('_dossier_authority'):
            raise HTTPException(403, '原单档案授权必须经过独立权限校验')
    for row in set(db.dirty) | set(db.deleted):
        if isinstance(row, IMMUTABLE) and (row in db.deleted or db.is_modified(row)):
            raise HTTPException(409, '授权范围、复核与读取记录不能改写，请另建授权或撤销')
        if isinstance(row, DossierGrant) and (row in db.deleted or any(
                inspect(row).attrs[k].history.has_changes() for k in SCOPE_FIELDS)):
            raise HTTPException(409, '已提交的原单和逐件文件范围不能修改，请撤销后重新申请')


@event.listens_for(Session, 'do_orm_execute')
def protect_dossier_queries(state):
    if any(issubclass(mapper.class_, DossierProtected) for mapper in state.all_mappers):
        if not state.session.info.get('_dossier_authority'):
            raise HTTPException(403, '原单档案授权仅可通过指定门店和员工查询')
        if state.is_update or state.is_delete:
            raise HTTPException(409, '不能批量改写原单档案授权')
