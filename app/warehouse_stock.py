"""Shared physical posting adapter. No cash, approvals or business states are inferred."""
from contextlib import contextmanager
from sqlalchemy import select,func
from fastapi import HTTPException
from .db import today,utcnow
from .flow_models import Case,Item,StockMove
from .master_models import OpeningStockEntry
from .warehouse_models import (WarehouseDocument as Document,WarehouseEnrollment as Enrollment,WarehouseBalance as Balance,
    WarehouseEntry as Entry,WarehouseHold as Hold,WarehouseAllocation as Allocation,WarehouseAllocationLine as AllocationLine,
    WarehouseCountObservation as Observation)

def rows(db,cls,**kw):return list(db.scalars(select(cls).filter_by(**kw).order_by(cls.id)))
def enrolled(db,item_id):return db.scalar(select(Enrollment).where(Enrollment.item_id==item_id))
def item_lock(db,key):
    item=db.scalar(select(Item).where(Item.id==key).with_for_update())
    if not item:raise HTTPException(404,'当前门店物资不存在')
    return item
def location(db,key):
    from .master_data import require_active
    loc=require_active(db,'locations',key);warehouse=require_active(db,'warehouses',loc.warehouse_id)
    if warehouse.warehouse_type not in {'materials','mixed'}:raise HTTPException(422,'物资只能使用物资仓或混合仓的有效库位')
    return loc
def balance(db,item_id,location_id=None,transit_case_id=None):
    bucket=f'bin:{location_id}' if location_id is not None else f'transit:{transit_case_id}'
    row=db.scalar(select(Balance).where(Balance.item_id==item_id,Balance.bucket==bucket).with_for_update())
    if not row:
        row=Balance(item_id=item_id,bucket=bucket,location_id=location_id,transit_case_id=transit_case_id,quantity_milli=0,value_cents=0)
        db.add(row);db.flush()
    return row
def claim(db):return db.info.get('warehouse_verified_claim')
@contextmanager
def own_claim(db,case):
    # Only warehouse command handlers set this after current role, task and Case checks.
    if case.kind!='warehouse':raise ValueError('warehouse claim must belong to a warehouse Case')
    prior=db.info.get('warehouse_verified_claim');db.info['warehouse_verified_claim']=case.id
    try:yield
    finally:
        if prior is None:db.info.pop('warehouse_verified_claim',None)
        else:db.info['warehouse_verified_claim']=prior
def held(db,item_id,location_id=None,exclude=None):
    query=select(func.coalesce(func.sum(Hold.quantity_milli),0)).where(Hold.item_id==item_id)
    if location_id is not None:query=query.where(Hold.location_id==location_id)
    if exclude is not None:query=query.where(Hold.case_id!=exclude)
    return db.scalar(query)
def count_rows(db,item_id):
    return list(db.execute(select(Case,Document,Observation).join(Document,Document.id==Case.id).outerjoin(Observation,Observation.case_id==Case.id)
        .where(Document.item_id==item_id,Document.operation=='count',Case.state.in_(['counting','review']))))
def restrictions(db,item_id):
    """Unavailable physical transit + approved promises + observed pending shortages."""
    exclude=claim(db)
    total=held(db,item_id,exclude=exclude)+db.scalar(select(func.coalesce(func.sum(Balance.quantity_milli),0)).where(Balance.item_id==item_id,Balance.transit_case_id.is_not(None)))
    for case,doc,ob in count_rows(db,item_id):
        if case.id==exclude:continue
        if ob:total+=max(0,ob.baseline_quantity_milli-ob.counted_quantity_milli)
        else:
            b=db.scalar(select(Balance).where(Balance.item_id==item_id,Balance.location_id==doc.source_location_id))
            total+=b.quantity_milli if b else 0
    return total
def assert_bin(db,item_id,location_id,qty):
    location(db,location_id)
    for case,doc,ob in count_rows(db,item_id):
        if case.id!=claim(db) and case.state=='counting' and doc.source_location_id==location_id:
            raise HTTPException(409,'该库位正在实盘，请先提交实盘观察或取消本次盘点围栏')
    b=balance(db,item_id,location_id)
    if qty>b.quantity_milli-held(db,item_id,location_id,claim(db)):
        raise HTTPException(409,'所选库位的可用数量不足，不能占用其他已批准作业或在途物资')
    return b
def reconcile_source(db,item):
    openings=rows(db,OpeningStockEntry,item_id=item.id);moves=rows(db,StockMove,item_id=item.id)
    qty=sum(x.quantity_milli for x in openings)+sum(x.quantity_milli for x in moves)
    value=sum(x.value_cents for x in openings)+sum(x.value_cents for x in moves)
    if (qty,value)!=(item.quantity_milli,item.inventory_value_cents):
        raise HTTPException(409,'原始期初账／收发流水与当前物资不一致，不能猜测历史数量或价值后启用库位')
    return max((x.id for x in moves),default=0)
def rebalance(db,user,case,item,changes,reason,stock_move_id=None):
    """Store moving average remains authoritative; largest remainders preserve every fen.

    Quantity changes and zero-quantity revaluation entries are stored together. Local
    transit participates in the same store average; it is never available for issue.
    """
    all_rows=rows(db,Balance,item_id=item.id);before={b.id:(b.quantity_milli,b.value_cents) for b in all_rows}
    for b in all_rows:
        b.quantity_milli+=changes.get(b.id,0)
        if b.quantity_milli<0:raise HTTPException(409,'库位数量不足；本次没有更改库存')
    total=sum(b.quantity_milli for b in all_rows)
    if total!=item.quantity_milli:raise HTTPException(409,'库位和在途数量与门店库存不一致，已阻断过账')
    if not total and item.inventory_value_cents:raise HTTPException(409,'零数量不能保留库存价值')
    targets={b.id:(item.inventory_value_cents*b.quantity_milli//total if total else 0) for b in all_rows}
    remaining=item.inventory_value_cents-sum(targets.values())
    if remaining:
        ranked=sorted(all_rows,key=lambda b:(-(item.inventory_value_cents*b.quantity_milli%total),b.id))
        for b in ranked[:remaining]:targets[b.id]+=1
    for b in all_rows:
        old_qty,old_value=before[b.id];delta=b.quantity_milli-old_qty;value=targets[b.id]-old_value
        b.value_cents=targets[b.id]
        if delta or value:
            b.updated_at=utcnow();db.add(Entry(balance_id=b.id,case_id=case.id,stock_move_id=stock_move_id,quantity_milli=delta,value_cents=value,
                reason=reason if delta else 'average_revaluation',actor_id=user.id,business_date=today()))
    item.updated_at=utcnow();db.flush()
def prepare(db,user,case,item,qty,purpose,lines):
    if not enrolled(db,item.id) and purpose!='activation':raise HTTPException(409,'此物资尚未完成库位启用，请先核对期初和历史收发账')
    if len({x['location_id'] for x in lines})!=len(lines):raise HTTPException(422,'同一库位请合并为一行')
    if sum(x['quantity_milli'] for x in lines)!=abs(qty):raise HTTPException(422,'库位分配之和必须等于本次原业务收发数量')
    for line in lines:
        location(db,line['location_id'])
        if qty<0:assert_bin(db,item.id,line['location_id'],line['quantity_milli'])
    # A replacement explicitly cancels unused plans for this exact operation. It
    # never releases reservations and never reports physical completion.
    for old in rows(db,Allocation,case_id=case.id,item_id=item.id,purpose=purpose,status='prepared'):old.status='cancelled'
    a=Allocation(case_id=case.id,item_id=item.id,quantity_milli=qty,purpose=purpose,actor_id=user.id,status='prepared');db.add(a);db.flush()
    for line in lines:db.add(AllocationLine(allocation_id=a.id,**line))
    db.flush();return a
def after_stock_move(db,user,case,item,move):
    if not enrolled(db,item.id):return
    candidates=rows(db,Allocation,case_id=case.id,item_id=item.id,purpose=move.purpose,status='prepared')
    a=next((x for x in candidates if x.quantity_milli==move.quantity_milli),None)
    if not a:raise HTTPException(409,'该物资已启用真实库位，请在原单“准备物资库位”按本次精确数量分配，再确认实际收发')
    changes={}
    for line in rows(db,AllocationLine,allocation_id=a.id):
        b=assert_bin(db,item.id,line.location_id,line.quantity_milli if move.quantity_milli<0 else 0)
        changes[b.id]=line.quantity_milli*(1 if move.quantity_milli>=0 else -1)
    rebalance(db,user,case,item,changes,move.purpose,move.id)
    a.status='consumed';a.stock_move_id=move.id;db.flush()

def location_in_use(db,location_id):
    return bool(db.scalar(select(Balance.id).where(Balance.location_id==location_id,Balance.quantity_milli>0)) or
        db.scalar(select(Document.id).join(Case,Document.id==Case.id).where(Case.state.not_in(['completed','cancelled','rejected']),
            (Document.source_location_id==location_id)|(Document.destination_location_id==location_id))))


def has_location_history(db,location_id=None,warehouse_id=None):
    """A bin's warehouse is historical identity, even after its stock reaches zero.

    A zero opening still has an explicitly selected Balance. Keeping its parent
    preserves the activation bridge; renaming display labels remains possible.
    """
    from .master_models import StorageLocation
    query=select(Balance.id).where(Balance.location_id.is_not(None))
    if location_id is not None:query=query.where(Balance.location_id==location_id)
    if warehouse_id is not None:
        query=query.join(StorageLocation,StorageLocation.id==Balance.location_id).where(StorageLocation.warehouse_id==warehouse_id)
    return db.scalar(query.limit(1)) is not None
