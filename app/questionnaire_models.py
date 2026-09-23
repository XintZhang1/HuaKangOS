"""Store-scoped publication, original issuance binding and immutable answers."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,ForeignKey,DateTime,JSON,UniqueConstraint,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class Protected: pass


class Fact:
    id:Mapped[int]=mapped_column(primary_key=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class QuestionnairePolicy(Protected,Versioned,Base):
    __tablename__='care_questionnaire_policies'
    active_version_id:Mapped[int|None]=mapped_column(ForeignKey('care_questionnaire_versions.id'),nullable=True)
    next_number:Mapped[int]=mapped_column(Integer,default=2)
    __table_args__=(UniqueConstraint('store_id',name='uq_questionnaire_policy_store'),
        CheckConstraint('next_number>=2',name='ck_questionnaire_next_number'))


class QuestionnaireVersion(Protected,Fact,StoreScoped,Base):
    __tablename__='care_questionnaire_versions'
    number:Mapped[int]=mapped_column(Integer)
    name:Mapped[str]=mapped_column(String(120))
    questions:Mapped[list]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(String(1000))
    proposed_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('store_id','number',name='uq_questionnaire_store_number'),
        CheckConstraint('number>=2',name='ck_questionnaire_number'))


class QuestionnaireReview(Protected,Fact,StoreScoped,Base):
    __tablename__='care_questionnaire_reviews'
    version_id:Mapped[int]=mapped_column(ForeignKey('care_questionnaire_versions.id'),unique=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    actor_role:Mapped[str]=mapped_column(String(20))
    decision:Mapped[str]=mapped_column(String(12))
    previous_version_id:Mapped[int|None]=mapped_column(ForeignKey('care_questionnaire_versions.id'),nullable=True)
    reason:Mapped[str]=mapped_column(String(1000))
    schema_digest:Mapped[str]=mapped_column(String(64))
    __table_args__=(CheckConstraint("decision IN ('approve','reject') AND actor_role IN ('admin','manager')",name='ck_questionnaire_review'),)


class QuestionnaireBinding(Protected,Fact,StoreScoped,Base):
    __tablename__='care_questionnaire_bindings'
    case_id:Mapped[int]=mapped_column(ForeignKey('care_cases.case_id'),index=True)
    version_id:Mapped[int|None]=mapped_column(ForeignKey('care_questionnaire_versions.id'),nullable=True)
    number:Mapped[int]=mapped_column(Integer)
    name:Mapped[str]=mapped_column(String(120))
    questions:Mapped[list]=mapped_column(JSON)
    schema_digest:Mapped[str]=mapped_column(String(64))
    issued_at:Mapped[datetime]=mapped_column(DateTime)
    origin:Mapped[str]=mapped_column(String(12))
    __table_args__=(UniqueConstraint('case_id',name='uq_questionnaire_binding_case'),CheckConstraint("origin IN ('runtime','migration') AND ((version_id IS NULL AND number=1) OR (version_id IS NOT NULL AND number>=2))",name='ck_questionnaire_binding'),)


class QuestionnaireResponse(Protected,Fact,StoreScoped,Base):
    __tablename__='care_questionnaire_responses'
    binding_id:Mapped[int]=mapped_column(ForeignKey('care_questionnaire_bindings.id'),unique=True)
    record_id:Mapped[int]=mapped_column(ForeignKey('care_records.id'),unique=True)
    answers:Mapped[dict]=mapped_column(JSON)
    digest:Mapped[str]=mapped_column(String(64))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    origin:Mapped[str]=mapped_column(String(12))
    __table_args__=(CheckConstraint("origin IN ('runtime','migration')",name='ck_questionnaire_response_origin'),)


@event.listens_for(Session,'before_flush')
def guard_questionnaire_facts(db,*_):
    changed=list(db.new)+list(db.dirty)+list(db.deleted)
    if any(isinstance(row,Protected) for row in changed) and not (db.info.get('_care_authority') and db.info.get('_questionnaire_write')):
        raise HTTPException(403,'问卷版本、发放和回答必须经过原客户服务流程')
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,Protected) and not isinstance(row,QuestionnairePolicy):
            raise HTTPException(409,'已登记题目、复核、原发放与回答不能覆盖或删除')
        if isinstance(row,QuestionnairePolicy) and (row in db.deleted or inspect(row).attrs.store_id.history.has_changes()):
            raise HTTPException(409,'问卷发布门店不可改写')


@event.listens_for(Session,'do_orm_execute')
def guard_questionnaire_queries(state):
    if any(issubclass(mapper.class_,Protected) for mapper in state.all_mappers):
        if not state.session.info.get('_care_authority'):raise HTTPException(403,'问卷须在获权的客户服务范围查询')
        if state.is_update or state.is_delete:raise HTTPException(409,'问卷不允许批量覆盖或删除')
