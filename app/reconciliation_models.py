"""Store statements and original-linked internal clearing; never a general ledger."""
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,BigInteger,Date,DateTime,ForeignKey,JSON,UniqueConstraint,CheckConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session,declared_attr
from .db import Base,utcnow
from .models import StoreScoped
from .flow_models import Versioned


class ReconciliationProtected:pass
class CentralVersioned(ReconciliationProtected):
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow,onupdate=utcnow)
    @declared_attr.directive
    def __mapper_args__(cls):return {'version_id_col':cls.version}


class ReconciliationBatch(Versioned,Base):
    __tablename__='reconciliation_batches'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    start:Mapped[date]=mapped_column(Date)
    end:Mapped[date]=mapped_column(Date)
    revision:Mapped[int]=mapped_column(Integer)
    previous_id:Mapped[int|None]=mapped_column(ForeignKey('reconciliation_batches.id'),nullable=True,unique=True)
    status:Mapped[str]=mapped_column(String(20),default='draft')
    prepared_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    submitted_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    sealed_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    sealed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    reason:Mapped[str]=mapped_column(String(500))
    digest:Mapped[str]=mapped_column(String(64))
    manifest:Mapped[list]=mapped_column(JSON)
    summary:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','start','end','revision',name='uq_reconciliation_period_revision'),
        CheckConstraint('"start"<="end" AND revision>0',name='ck_reconciliation_period'),
        CheckConstraint("status IN ('draft','review','sealed','superseded')",name='ck_reconciliation_status'),
        CheckConstraint("status!='sealed' OR (sealed_by IS NOT NULL AND sealed_at IS NOT NULL)",name='ck_reconciliation_sealed'))


class ReconciliationIssue(Versioned,Base):
    __tablename__='reconciliation_issues'
    batch_id:Mapped[int]=mapped_column(ForeignKey('reconciliation_batches.id'),index=True)
    line_key:Mapped[str]=mapped_column(String(100))
    difference_cents:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(500))
    opened_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    status:Mapped[str]=mapped_column(String(20),default='open')
    resolved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    resolution:Mapped[str|None]=mapped_column(String(500),nullable=True)
    resolution_evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    __table_args__=(CheckConstraint("status IN ('open','resolved')",name='ck_reconciliation_issue'),
        CheckConstraint("status!='resolved' OR (resolved_by IS NOT NULL AND resolution_evidence_id IS NOT NULL AND resolution IS NOT NULL)",name='ck_reconciliation_resolution'))


class ClearingBucket(CentralVersioned,Base):
    __tablename__='interstore_clearing_buckets'
    origin_kind:Mapped[str]=mapped_column(String(20))
    debtor_origin_id:Mapped[int]=mapped_column(Integer)
    creditor_origin_id:Mapped[int]=mapped_column(Integer)
    payer_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    receiver_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    total_cents:Mapped[int]=mapped_column(BigInteger)
    reserved_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    settled_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    __table_args__=(UniqueConstraint('origin_kind','debtor_origin_id',name='uq_clearing_original'),
        CheckConstraint("origin_kind IN ('material','material_loss','material_found','vehicle','vehicle_loss','vehicle_found') AND payer_store_id!=receiver_store_id",name='ck_clearing_parties'),
        CheckConstraint('total_cents>0 AND reserved_cents>=0 AND settled_cents>=0 AND reserved_cents+settled_cents<=total_cents',name='ck_clearing_bucket'))


class ClearingOrder(CentralVersioned,Base):
    __tablename__='interstore_clearing_orders'
    bucket_id:Mapped[int]=mapped_column(ForeignKey('interstore_clearing_buckets.id'),index=True)
    payer_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    receiver_store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'))
    payer_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    receiver_case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),unique=True)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    due_date:Mapped[date]=mapped_column(Date)
    reason:Mapped[str]=mapped_column(String(500))
    status:Mapped[str]=mapped_column(String(20),default='requested')
    __table_args__=(CheckConstraint('amount_cents>0 AND payer_store_id!=receiver_store_id',name='ck_clearing_amount'),
        CheckConstraint("status IN ('requested','paid','settled','cancelled')",name='ck_clearing_status'))


class ClearingCash(StoreScoped,Base):
    __tablename__='interstore_clearing_cash'
    id:Mapped[int]=mapped_column(primary_key=True)
    order_id:Mapped[int]=mapped_column(ForeignKey('interstore_clearing_orders.id'),index=True)
    cash_id:Mapped[int]=mapped_column(ForeignKey('cash_entries.id'),unique=True)
    account_id:Mapped[int]=mapped_column(ForeignKey('flow_accounts.id'))
    direction:Mapped[str]=mapped_column(String(3))
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    reference:Mapped[str]=mapped_column(String(100))
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('order_id','direction',name='uq_clearing_cash_side'),
        UniqueConstraint('store_id','account_id','reference',name='uq_clearing_cash_reference'),
        CheckConstraint("amount_cents>0 AND direction IN ('in','out')",name='ck_clearing_cash'))


class ClearingOffset(StoreScoped,Base):
    __tablename__='interstore_clearing_offsets'
    id:Mapped[int]=mapped_column(primary_key=True)
    order_id:Mapped[int]=mapped_column(ForeignKey('interstore_clearing_orders.id'),index=True)
    origin_kind:Mapped[str]=mapped_column(String(20))
    origin_id:Mapped[int]=mapped_column(Integer)
    amount_cents:Mapped[int]=mapped_column(BigInteger)
    business_date:Mapped[date]=mapped_column(Date)
    __table_args__=(UniqueConstraint('order_id','store_id',name='uq_clearing_offset_party'),CheckConstraint('amount_cents!=0',name='ck_clearing_offset'))


class ReconciliationEvent(StoreScoped,Base):
    __tablename__='reconciliation_events'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(30))
    reason:Mapped[str]=mapped_column(String(500))
    evidence_id:Mapped[int|None]=mapped_column(ForeignKey('flow_files.id'),nullable=True)
    detail:Mapped[dict]=mapped_column(JSON,default=dict)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)


class ReconciliationReceipt(StoreScoped,Base):
    __tablename__='reconciliation_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    digest:Mapped[str]=mapped_column(String(64))
    result:Mapped[dict]=mapped_column(JSON)
    __table_args__=(UniqueConstraint('store_id','request_key',name='uq_reconciliation_request'),)


@event.listens_for(Session,'before_flush')
def protect_reconciliation(db,*_):
    immutable=(ClearingCash,ClearingOffset,ReconciliationEvent,ReconciliationReceipt)
    frozen={ReconciliationBatch:('case_id','start','end','revision','previous_id','prepared_by','reason','digest','manifest','summary'),
        ReconciliationIssue:('batch_id','line_key','difference_cents','reason','opened_by','evidence_id'),
        ClearingBucket:('origin_kind','debtor_origin_id','creditor_origin_id','payer_store_id','receiver_store_id','total_cents'),
        ClearingOrder:('bucket_id','payer_store_id','receiver_store_id','payer_case_id','receiver_case_id','amount_cents','requested_by','due_date','reason')}
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,immutable):raise HTTPException(409,'对账、现金和往来核销事实不可覆盖')
        for model,keys in frozen.items():
            if isinstance(row,model) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in keys)):
                raise HTTPException(409,'原对账版本及清算申请不可覆盖，请追加后继记录')
    for row in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(row,(ReconciliationBatch,ReconciliationIssue,ReconciliationProtected,*immutable)) and not db.info.get('_reconciliation_authority'):
            raise HTTPException(403,'对账与清算只能通过受权动作办理')


@event.listens_for(Session,'do_orm_execute')
def protect_clearing_reads(state):
    if any(issubclass(m.class_,ReconciliationProtected) for m in state.all_mappers):
        if not state.session.info.get('_reconciliation_authority'):raise HTTPException(403,'跨店清算仅由授权服务查询')
        if state.is_update or state.is_delete:raise HTTPException(409,'清算记录不得批量改写')
