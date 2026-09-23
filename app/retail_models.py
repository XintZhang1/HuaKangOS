"""Frozen retail agreement and immutable reservation, stock, and cash evidence."""
from fastapi import HTTPException
from sqlalchemy import String,BigInteger,Integer,Boolean,ForeignKey,CheckConstraint,UniqueConstraint,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base
from .models import StoreScoped
from .flow_models import Versioned

class RetailOrder(StoreScoped,Base):
    __tablename__='retail_orders'
    id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),primary_key=True)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    related_repair_id:Mapped[int|None]=mapped_column(ForeignKey('flow_cases.id'),nullable=True)
    customer_name:Mapped[str]=mapped_column(String(120))
    discount_cents:Mapped[int]=mapped_column(BigInteger)
    installation_policy:Mapped[str]=mapped_column(String(200),default='已实际完成安装的对应安装费保留；未施工的对应安装费随验收退货减免')

class RetailLine(StoreScoped,Base):
    __tablename__='retail_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'))
    sku:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    unit:Mapped[str]=mapped_column(String(20))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    unit_price_cents:Mapped[int]=mapped_column(BigInteger)
    goods_cents:Mapped[int]=mapped_column(BigInteger)
    work_item_id:Mapped[int|None]=mapped_column(ForeignKey('master_work_items.id'),nullable=True)
    work_code:Mapped[str]=mapped_column(String(60),default='')
    work_name:Mapped[str]=mapped_column(String(120),default='')
    installation_unit_price_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    installation_cents:Mapped[int]=mapped_column(BigInteger,default=0)
    __table_args__=(UniqueConstraint('case_id','item_id',name='uq_retail_item'),CheckConstraint('quantity_milli>0 AND unit_price_cents>=0 AND goods_cents>=0 AND installation_unit_price_cents>=0 AND installation_cents>=0',name='ck_retail_line'),)

class RetailReservation(StoreScoped,Base):
    __tablename__='retail_reservations'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    item_id:Mapped[int]=mapped_column(ForeignKey('flow_items.id'),index=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    reason:Mapped[str]=mapped_column(String(20))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("(quantity_milli>0 AND reason='reserve') OR (quantity_milli<0 AND reason IN ('dispatch','cancel'))",name='ck_retail_reservation'),)

class RetailDispatch(StoreScoped,Base):
    __tablename__='retail_dispatches'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    line_id:Mapped[int]=mapped_column(ForeignKey('retail_lines.id'),unique=True)
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint('quantity_milli>0 AND value_cents>=0',name='ck_retail_dispatch'),)

class RetailReturn(Versioned,Base):
    __tablename__='retail_returns'
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    status:Mapped[str]=mapped_column(String(30),default='requested')
    reason:Mapped[str]=mapped_column(String(1000))
    requested_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    approved_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    retain_installation:Mapped[bool]=mapped_column(Boolean,default=False)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint("status IN ('requested','approved','rectification','reinspection','handback','rejected','accepted','cancelled')",name='ck_retail_return_status'),)

class RetailReturnLine(StoreScoped,Base):
    __tablename__='retail_return_lines'
    id:Mapped[int]=mapped_column(primary_key=True)
    return_id:Mapped[int]=mapped_column(ForeignKey('retail_returns.id'),index=True)
    dispatch_id:Mapped[int]=mapped_column(ForeignKey('retail_dispatches.id'))
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    __table_args__=(UniqueConstraint('return_id','dispatch_id',name='uq_retail_return_line'),CheckConstraint('quantity_milli>0',name='ck_retail_return_line'),)

class RetailReturnPosting(StoreScoped,Base):
    __tablename__='retail_return_postings'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    return_line_id:Mapped[int]=mapped_column(ForeignKey('retail_return_lines.id'),unique=True)
    dispatch_id:Mapped[int]=mapped_column(ForeignKey('retail_dispatches.id'),index=True)
    stock_move_id:Mapped[int]=mapped_column(ForeignKey('flow_stock_moves.id'),unique=True)
    quantity_milli:Mapped[int]=mapped_column(BigInteger)
    value_cents:Mapped[int]=mapped_column(BigInteger)
    goods_cents:Mapped[int]=mapped_column(BigInteger)
    installation_cents:Mapped[int]=mapped_column(BigInteger)
    retained_cents:Mapped[int]=mapped_column(BigInteger)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))
    __table_args__=(CheckConstraint('quantity_milli>0 AND value_cents>=0 AND goods_cents>=0 AND installation_cents>=0 AND retained_cents>=0 AND retained_cents<=installation_cents',name='ck_retail_return_posting'),)

class RetailPayment(StoreScoped,Base):
    __tablename__='retail_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    case_id:Mapped[int]=mapped_column(ForeignKey('flow_cases.id'),index=True)
    payment_link_id:Mapped[int]=mapped_column(ForeignKey('flow_payment_links.id'),unique=True)
    evidence_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'))

IMMUTABLE=(RetailOrder,RetailLine,RetailReservation,RetailDispatch,RetailReturnLine,RetailReturnPosting,RetailPayment)
@event.listens_for(Session,'before_flush')
def immutable_retail(db,*_):
    for row in list(db.dirty)+list(db.deleted):
        if isinstance(row,IMMUTABLE):raise HTTPException(409,'精品报价、占用、实物及现金链接不可覆盖；请办理关联原单的撤销或退货')
        if isinstance(row,RetailReturn) and (row in db.deleted or any(inspect(row).attrs[k].history.has_changes() for k in ('case_id','reason','requested_by','evidence_id'))):
            raise HTTPException(409,'退货申请原始事实不可修改')
