"""Approved business identities and immutable store/account/source attribution.

These tables do not make unconnected business domains entity-aware. Central
registry reads require service authority; case/cash links remain store scoped.
"""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,ForeignKey,Date,DateTime,Boolean,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped


class EntityProtected:pass


class BusinessEntity(EntityProtected,Base):
    __tablename__='business_entities'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    tax_identifier:Mapped[str]=mapped_column(String(30),unique=True)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __mapper_args__={'version_id_col':version}


class EntityRevision(EntityProtected,Base):
    __tablename__='business_entity_revisions'
    id:Mapped[int]=mapped_column(primary_key=True)
    entity_id:Mapped[int]=mapped_column(ForeignKey('business_entities.id'),index=True)
    revision:Mapped[int]=mapped_column(Integer)
    legal_name:Mapped[str]=mapped_column(String(180))
    registered_address:Mapped[str]=mapped_column(String(300))
    contact_phone:Mapped[str]=mapped_column(String(40),default='')
    application_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    source_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    source_evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    approved_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('entity_id','revision',name='uq_business_entity_revision'),CheckConstraint('revision>0',name='ck_business_entity_revision'))


class EntityStoreControl(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_store_controls'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    __mapper_args__={'version_id_col':version}
    __table_args__=(UniqueConstraint('store_id',name='uq_business_entity_store_control'),)


class EntityApplication(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_applications'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    operation:Mapped[str]=mapped_column(String(25))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(String(1000))
    __table_args__=(CheckConstraint("operation IN ('revision','store_binding','account_binding','policy')",name='ck_business_entity_operation'),)


class EntityRevisionProposal(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_revision_proposals'
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),primary_key=True)
    entity_id:Mapped[int|None]=mapped_column(ForeignKey('business_entities.id'),nullable=True)
    expected_entity_version:Mapped[int|None]=mapped_column(Integer,nullable=True)
    code:Mapped[str]=mapped_column(String(50))
    tax_identifier:Mapped[str]=mapped_column(String(30))
    legal_name:Mapped[str]=mapped_column(String(180))
    registered_address:Mapped[str]=mapped_column(String(300))
    contact_phone:Mapped[str]=mapped_column(String(40),default='')
    __table_args__=(CheckConstraint('(entity_id IS NULL AND expected_entity_version IS NULL) OR (entity_id IS NOT NULL AND expected_entity_version>0)',name='ck_entity_proposal_version'),)


class StoreEntityProposal(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_store_proposals'
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),primary_key=True)
    revision_id:Mapped[int]=mapped_column(ForeignKey('business_entity_revisions.id'))
    effective_from:Mapped[date]=mapped_column(Date)


class AccountEntityProposal(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_account_proposals'
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),primary_key=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    expected_account_version:Mapped[int]=mapped_column(Integer)
    revision_id:Mapped[int]=mapped_column(ForeignKey('business_entity_revisions.id'))
    effective_from:Mapped[date]=mapped_column(Date)
    holder_name:Mapped[str]=mapped_column(String(180))
    channel_type:Mapped[str]=mapped_column(String(15))
    channel_identifier:Mapped[str]=mapped_column(String(100))
    institution_name:Mapped[str]=mapped_column(String(180))
    __table_args__=(CheckConstraint("expected_account_version>0 AND channel_type IN ('bank','cash','wallet')",name='ck_entity_account_proposal'),)


class EntityPolicyProposal(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_policy_proposals'
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),primary_key=True)
    binding_id:Mapped[int]=mapped_column(ForeignKey('business_entity_store_bindings.id'))
    policy_version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint('policy_version=1',name='ck_entity_policy_proposal'),)


class EntitySubmission(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_submissions'
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),primary_key=True)
    control_version:Mapped[int]=mapped_column(Integer)
    source_evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class EntityDecision(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_decisions'
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),primary_key=True)
    decision:Mapped[str]=mapped_column(String(15))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    reason:Mapped[str]=mapped_column(String(1000))
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("(decision='approved' AND evidence_id IS NOT NULL) OR decision IN ('rejected','cancelled')",name='ck_entity_decision'),)


class StoreEntityBinding(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_store_bindings'
    id:Mapped[int]=mapped_column(primary_key=True)
    revision_id:Mapped[int]=mapped_column(ForeignKey('business_entity_revisions.id'))
    effective_from:Mapped[date]=mapped_column(Date)
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),unique=True)
    approved_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class EntityAccountChannel(EntityProtected,Base):
    __tablename__='business_entity_account_channels'
    id:Mapped[int]=mapped_column(primary_key=True)
    digest:Mapped[str]=mapped_column(String(64),unique=True)
    owner_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'),unique=True)


class AccountEntityBinding(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_account_bindings'
    id:Mapped[int]=mapped_column(primary_key=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'),index=True)
    revision_id:Mapped[int]=mapped_column(ForeignKey('business_entity_revisions.id'))
    channel_id:Mapped[int]=mapped_column(ForeignKey('business_entity_account_channels.id'))
    effective_from:Mapped[date]=mapped_column(Date)
    holder_name:Mapped[str]=mapped_column(String(180))
    channel_type:Mapped[str]=mapped_column(String(15))
    channel_identifier:Mapped[str]=mapped_column(String(100))
    institution_name:Mapped[str]=mapped_column(String(180))
    account_name:Mapped[str]=mapped_column(String(100))
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),unique=True)
    approved_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("channel_type IN ('bank','cash','wallet')",name='ck_entity_account_binding'),)


class EntityPolicy(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_policies'
    id:Mapped[int]=mapped_column(primary_key=True)
    policy_version:Mapped[int]=mapped_column(Integer)
    binding_id:Mapped[int]=mapped_column(ForeignKey('business_entity_store_bindings.id'))
    case_cursor:Mapped[int]=mapped_column(Integer)
    cash_cursor:Mapped[int]=mapped_column(Integer)
    application_id:Mapped[int]=mapped_column(ForeignKey('business_entity_applications.id'),unique=True)
    approved_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(UniqueConstraint('store_id',name='uq_entity_policy_store'),CheckConstraint('policy_version=1 AND case_cursor>=0 AND cash_cursor>=0',name='ck_entity_policy'),)


class CaseEntityContext(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_case_contexts'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    policy_id:Mapped[int]=mapped_column(ForeignKey('business_entity_policies.id'))
    binding_id:Mapped[int]=mapped_column(ForeignKey('business_entity_store_bindings.id'))
    revision_id:Mapped[int]=mapped_column(ForeignKey('business_entity_revisions.id'))
    source_case_id:Mapped[int|None]=mapped_column(ForeignKey('business_entity_case_contexts.case_id'),nullable=True)
    derived_kind:Mapped[str|None]=mapped_column(String(30),nullable=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    frozen_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint("(source_case_id IS NULL AND derived_kind IS NULL) OR (source_case_id IS NOT NULL AND derived_kind IS NOT NULL AND source_case_id<case_id AND derived_kind IN ('aftercare','invoice','vehicle_return','claim','advance_refund','finance_correction','other_return','vehicle_income','membership_refund'))",name='ck_entity_case_derivation'),)


class CashEntityContext(StoreScoped,EntityProtected,Base):
    __tablename__='business_entity_cash_contexts'
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('business_entity_case_contexts.case_id'))
    account_binding_id:Mapped[int]=mapped_column(ForeignKey('business_entity_account_bindings.id'))
    original_cash_id:Mapped[int|None]=mapped_column(ForeignKey('business_entity_cash_contexts.cash_id'),nullable=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    frozen_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


FACTS=(EntityRevision,EntityApplication,EntityRevisionProposal,StoreEntityProposal,AccountEntityProposal,EntityPolicyProposal,
       EntitySubmission,EntityDecision,StoreEntityBinding,EntityAccountChannel,AccountEntityBinding,EntityPolicy,CaseEntityContext,CashEntityContext)


@event.listens_for(Session,'before_flush')
def entity_write_guard(db,*_):
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,EntityProtected) and not db.info.get('_business_entity_authority'):
            raise HTTPException(403,'经营主体记录须经受控主体服务办理')
        if isinstance(row,FACTS) and (row in db.dirty or row in db.deleted):
            raise HTTPException(409,'主体资料版本、批准、绑定及原账归属不可覆盖；请追加有据申请')
        if isinstance(row,BusinessEntity) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('code','tax_identifier','created_by')) and row not in db.new):
            raise HTTPException(409,'主体稳定标识不可改写或删除；资料变更另建版本')


@event.listens_for(Session,'do_orm_execute')
def entity_query_guard(execution):
    if any(issubclass(m.class_,EntityProtected) for m in execution.all_mappers):
        if not execution.session.info.get('_business_entity_authority'):raise HTTPException(403,'经营主体资料须经获权主体服务查询')
        if execution.is_update or execution.is_delete:raise HTTPException(409,'经营主体记录不可批量覆盖')
