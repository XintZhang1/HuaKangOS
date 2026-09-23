"""One availability definition across stock consumers; facts stay in StockMove.

The caller must load Item in its authorized store and change its version in the
same transaction. A reservation never changes quantity or inventory value.
"""
from fastapi import HTTPException


def reserved_quantity(db, item_id, excluding_retail_case_id=None, excluding_procurement_return_id=None, excluding_addon_case_id=None):
    from .retail_service import reserved_quantity as retail_reserved
    from .warehouse_stock import restrictions
    from .addon_service import reserved_quantity as addon_reserved
    from .procurement_service import reserved_return_quantity
    return retail_reserved(db, item_id, excluding_case_id=excluding_retail_case_id)+restrictions(db,item_id)+reserved_return_quantity(db,item_id,excluding_procurement_return_id)+addon_reserved(db,item_id,excluding_addon_case_id)


def available_quantity(db, item, excluding_retail_case_id=None, excluding_procurement_return_id=None, excluding_addon_case_id=None):
    return max(0, item.quantity_milli-reserved_quantity(db, item.id, excluding_retail_case_id,excluding_procurement_return_id,excluding_addon_case_id))


def assert_can_issue(db, item, quantity, excluding_retail_case_id=None, excluding_procurement_return_id=None, excluding_addon_case_id=None):
    if quantity < 0:
        raise ValueError('issue quantity must be nonnegative')
    if quantity > available_quantity(db, item, excluding_retail_case_id,excluding_procurement_return_id,excluding_addon_case_id):
        raise HTTPException(409, '当前可用库存不足；已占用数量不能重复发出，请核对或先取消原占用')
