"""Original supplier credit and physical inventory cost are distinct facts."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import BigInteger,CheckConstraint,DateTime,ForeignKey,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped


class PurchaseReturnValuation(StoreScoped,Base):
    __tablename__='procurement_return_valuations'
    id:Mapped[int]=mapped_column(ForeignKey('procurement_return_postings.id'),primary_key=True,autoincrement=False)
    quantity_before_milli:Mapped[int]=mapped_column(BigInteger)
    value_before_cents:Mapped[int]=mapped_column(BigInteger)
    inventory_cost_cents:Mapped[int]=mapped_column(BigInteger)
    supplier_credit_cents:Mapped[int]=mapped_column(BigInteger)
    variance_cents:Mapped[int]=mapped_column(BigInteger)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('quantity_before_milli > 0 AND value_before_cents >= 0 AND inventory_cost_cents >= 0 AND supplier_credit_cents >= 0 AND inventory_cost_cents <= value_before_cents',name='ck_procurement_return_cost'),
        CheckConstraint('variance_cents = supplier_credit_cents - inventory_cost_cents',name='ck_procurement_return_variance'))


@event.listens_for(Session,'before_flush')
def immutable_return_valuation(db,*_):
    if any(isinstance(r,PurchaseReturnValuation) for r in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'采购原款冲减、库存成本和退货差额不可改写；请保留原事实另办纠正')
