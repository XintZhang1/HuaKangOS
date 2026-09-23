"""Moving-average physical returns, with independently preserved supplier credit."""
from fastapi import HTTPException
from sqlalchemy import select,func
from .flow_models import StockMove
from .master_models import OpeningStockEntry


def require_recorded_balance(db,item):
    totals=[db.execute(select(func.coalesce(func.sum(m.quantity_milli),0),func.coalesce(func.sum(m.value_cents),0)).where(m.item_id==item.id)).one() for m in (StockMove,OpeningStockEntry)]
    if (sum(t[0] for t in totals),sum(t[1] for t in totals))!=(item.quantity_milli,item.inventory_value_cents):
        raise HTTPException(409,'原库存期初与收发来源不足以核对当前余额，请先核对期初及库存差异，再办理均价退货')
