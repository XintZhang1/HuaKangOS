"""Append-only tracing of already-lost goods sent back but not received.

Ending a search is not a second inventory loss. A later physical reappearance
is a new attributed finding; original custody facts and approvals remain intact.
"""
from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column
from .db import Base, utcnow
from .transfer_models import TransferProtected


class GoodsSearch(TransferProtected, Base):
    __tablename__ = 'transfer_goods_searches'
    id: Mapped[int] = mapped_column(primary_key=True)
    recovery_id: Mapped[int] = mapped_column(ForeignKey('transfer_goods_recoveries.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    requested_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('recovery_id', 'revision', name='uq_found_search_revision'),
        CheckConstraint('revision>0', name='ck_found_search_revision'))


class GoodsSearchReview(TransferProtected, Base):
    __tablename__ = 'transfer_goods_search_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey('transfer_goods_searches.id'), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    decision: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    reason: Mapped[str] = mapped_column(String(1000))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('search_id', 'store_id', name='uq_found_search_review_store'),
        UniqueConstraint('search_id', 'actor_id', name='uq_found_search_review_actor'),
        CheckConstraint("decision IN ('end_search','keep_searching')", name='ck_found_search_review'))


class GoodsSearchOutcome(TransferProtected, Base):
    __tablename__ = 'transfer_goods_search_outcomes'
    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey('transfer_goods_searches.id'), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    kind: Mapped[str] = mapped_column(String(20))
    review_id: Mapped[int | None] = mapped_column(ForeignKey('transfer_goods_search_reviews.id'), nullable=True)
    receive_fact_id: Mapped[int | None] = mapped_column(ForeignKey('transfer_goods_facts.id'), nullable=True, unique=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint("(kind='arrived' AND receive_fact_id IS NOT NULL AND review_id IS NULL) OR "
        "(kind IN ('unlocated','rejected') AND review_id IS NOT NULL AND receive_fact_id IS NULL)", name='ck_found_search_outcome'),)


class GoodsReappearance(TransferProtected, Base):
    __tablename__ = 'transfer_goods_reappearances'
    id: Mapped[int] = mapped_column(primary_key=True)
    previous_recovery_id: Mapped[int] = mapped_column(ForeignKey('transfer_goods_recoveries.id'), index=True)
    search_id: Mapped[int] = mapped_column(ForeignKey('transfer_goods_searches.id'), index=True)
    recovery_id: Mapped[int] = mapped_column(ForeignKey('transfer_goods_recoveries.id'), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey('stores.id'), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('flow_cases.id'))
    quantity_milli: Mapped[int] = mapped_column(BigInteger)
    evidence_id: Mapped[int] = mapped_column(ForeignKey('flow_files.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (CheckConstraint('quantity_milli>0 AND previous_recovery_id!=recovery_id', name='ck_found_reappearance'),)


TABLES = (GoodsSearch, GoodsSearchReview, GoodsSearchOutcome, GoodsReappearance)


@event.listens_for(Session, 'before_flush')
def protect_search_facts(db, *_):
    for row in list(db.new) + list(db.dirty) + list(db.deleted):
        if not isinstance(row, TABLES):
            continue
        if not db.info.get('_transfer_goods_authority'):
            raise HTTPException(403, '原物资查找须先通过本店专用授权')
        if row in db.dirty or row in db.deleted:
            raise HTTPException(409, '原退运查找、独立复核及再次找到的来源不可覆盖')


@event.listens_for(Session, 'do_orm_execute')
def protect_search_queries(state):
    if any(issubclass(mapper.class_, TABLES) for mapper in state.all_mappers):
        if not state.session.info.get('_transfer_goods_authority'):
            raise HTTPException(403, '原物资查找须先通过本店专用授权')
        if state.is_update or state.is_delete:
            raise HTTPException(409, '原退运查找不得批量修改或删除')
