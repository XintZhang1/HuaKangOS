"""Versioned original-liability consent; existing full-internal rework is unchanged."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,DateTime,ForeignKey,JSON,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped

class ReworkProtected:pass

class ReworkSourceGrant(ReworkProtected,Base):
    __tablename__='rework_source_grants'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    definition_version:Mapped[int]=mapped_column(Integer,default=1)
    from_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    to_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),index=True)
    source_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    source_case_version:Mapped[int]=mapped_column(Integer)
    source_quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'))
    from_vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    to_vehicle_id:Mapped[int]=mapped_column(ForeignKey('care_customer_vehicles.id'))
    customer_identity_id:Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vehicle_identity_id:Mapped[int]=mapped_column(ForeignKey('group_identities.id'))
    vin:Mapped[str]=mapped_column(String(17))
    source_number:Mapped[str]=mapped_column(String(80))
    source_lines:Mapped[list]=mapped_column(JSON)
    original_liability_limit_cents:Mapped[int]=mapped_column(BigInteger)
    responsible_name:Mapped[str]=mapped_column(String(120))
    recipient_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    recipient_role:Mapped[str]=mapped_column(String(20))
    recipient_access_version:Mapped[int]=mapped_column(Integer)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    requester_role:Mapped[str]=mapped_column(String(20))
    requester_access_version:Mapped[int]=mapped_column(Integer)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    expires_at:Mapped[datetime]=mapped_column(DateTime)
    status:Mapped[str]=mapped_column(String(12),default='pending')
    scope_digest:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __mapper_args__={'version_id_col':version}
    __table_args__=(CheckConstraint("definition_version=1 AND version>0 AND source_case_version>0 AND original_liability_limit_cents>=0 AND recipient_access_version>0 AND requester_access_version>0 AND expires_at>created_at AND status IN ('pending','approved','rejected','cancelled','revoked','consumed')",name='ck_rework_source_grant'),)

class ReworkGrantDecision(ReworkProtected,Base):
    __tablename__='rework_grant_decisions'
    id:Mapped[int]=mapped_column(primary_key=True)
    grant_id:Mapped[int]=mapped_column(ForeignKey('rework_source_grants.id'),index=True)
    previous_version:Mapped[int]=mapped_column(Integer)
    action:Mapped[str]=mapped_column(String(12))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    actor_role:Mapped[str]=mapped_column(String(20))
    actor_access_version:Mapped[int]=mapped_column(Integer)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    scope_digest:Mapped[str]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(String(1000))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('grant_id','previous_version',name='uq_rework_grant_decision'),CheckConstraint("previous_version>0 AND actor_access_version>0 AND action IN ('approve','reject','cancel','revoke','consume')",name='ck_rework_grant_decision'),)

class ReworkGrantReceipt(StoreScoped,Base):
    __tablename__='rework_grant_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest:Mapped[str]=mapped_column(String(64))
    grant_id:Mapped[int]=mapped_column(ForeignKey('rework_source_grants.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_rework_grant_receipt'),)

class ReworkExtension(StoreScoped,Base):
    __tablename__='rework_extensions'
    request_id:Mapped[int]=mapped_column(ForeignKey('intake_rework_requests.id'),primary_key=True)
    definition_version:Mapped[int]=mapped_column(Integer,default=1)
    grant_id:Mapped[int]=mapped_column(ForeignKey('rework_source_grants.id'),unique=True)
    grant_digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('definition_version=1',name='ck_rework_extension_definition'),)

class ReworkQuoteScope(StoreScoped,Base):
    __tablename__='rework_quote_scopes'
    quote_id:Mapped[int]=mapped_column(ForeignKey('repair_quotes.id'),primary_key=True)
    request_id:Mapped[int]=mapped_column(ForeignKey('rework_extensions.request_id'),index=True)
    original_liability_cents:Mapped[int]=mapped_column(BigInteger)
    customer_extra_cents:Mapped[int]=mapped_column(BigInteger)
    digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(CheckConstraint('original_liability_cents>=0 AND customer_extra_cents>=0',name='ck_rework_quote_scope_amounts'),)

class ReworkLineScope(StoreScoped,Base):
    __tablename__='rework_line_scopes'
    line_id:Mapped[int]=mapped_column(ForeignKey('repair_lines.id'),primary_key=True)
    quote_id:Mapped[int]=mapped_column(ForeignKey('rework_quote_scopes.quote_id'),index=True)
    charge_scope:Mapped[str]=mapped_column(String(24))
    source_line_id:Mapped[int|None]=mapped_column(ForeignKey('repair_lines.id'),nullable=True)
    __table_args__=(CheckConstraint("(charge_scope='original_liability' AND source_line_id IS NOT NULL) OR (charge_scope='customer_extra' AND source_line_id IS NULL)",name='ck_rework_line_scope'),)

IMMUTABLE=(ReworkGrantDecision,ReworkGrantReceipt,ReworkExtension,ReworkQuoteScope,ReworkLineScope)
SCOPE_FIELDS=('definition_version','from_store_id','to_store_id','source_case_id','source_case_version','source_quote_id','from_vehicle_id','to_vehicle_id','customer_identity_id','vehicle_identity_id','vin','source_number','source_lines','original_liability_limit_cents','responsible_name','recipient_id','recipient_role','recipient_access_version','requested_by','requester_role','requester_access_version','evidence_id','reason','expires_at','scope_digest','created_at')

@event.listens_for(Session,'before_flush')
def protect_rework_writes(db,*_):
    for row in set(db.new)|set(db.dirty)|set(db.deleted):
        if isinstance(row,(ReworkProtected,ReworkGrantReceipt)) and not db.info.get('_rework_authority'):
            raise HTTPException(403,'原责任授权须通过指定原店和接收员工校验')
    for row in set(db.dirty)|set(db.deleted):
        if isinstance(row,IMMUTABLE) and (row in db.deleted or db.is_modified(row)):
            raise HTTPException(409,'原责任、报价分类及授权事实不能覆盖')
        if isinstance(row,ReworkSourceGrant) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in SCOPE_FIELDS)):
            raise HTTPException(409,'原责任授权范围已冻结，请撤销后重新申请')

@event.listens_for(Session,'do_orm_execute')
def protect_rework_queries(state):
    protected=any(issubclass(mapper.class_,ReworkProtected) for mapper in state.all_mappers)
    immutable=any(issubclass(mapper.class_,IMMUTABLE) for mapper in state.all_mappers)
    if protected and not state.session.info.get('_rework_authority'):raise HTTPException(403,'原责任授权仅可经限定服务查询')
    if (protected or immutable) and (state.is_update or state.is_delete):raise HTTPException(409,'不得批量改写原责任事实')
