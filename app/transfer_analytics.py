"""Current outgoing in-transit assets belong to the source store until accepted."""
from collections import defaultdict
from sqlalchemy import select
from fastapi import HTTPException
from .transfer_models import MaterialTransfer, TransferLine, TransferMovement, TransferSettlement
from .transfer_exception_models import TransferLossPosting, TransferLossSettlement


def current_transfers(db,user,bounded):
    if user.role not in {'admin','manager','finance','auditor'}:raise HTTPException(403,'调拨成本报表需要经营查询权限')
    ids=tuple(x for x in db.info.get('store_scope',()) if x)
    previous=db.info.get('_transfer_authority')
    # Scheduled aggregate snapshots carry a role-only principal and an explicit
    # store scope. This is a read authority, never a posting or actor identity.
    db.info['_transfer_authority']=('report',ids)
    try:
        headers=bounded(db,MaterialTransfer,select(MaterialTransfer).where(MaterialTransfer.from_store_id.in_(ids),MaterialTransfer.status=='transit'))
        by_id={h.id:h for h in headers}
        lines=bounded(db,TransferLine,select(TransferLine).where(TransferLine.transfer_id.in_(by_id))) if headers else []
        moves=bounded(db,TransferMovement,select(TransferMovement).where(TransferMovement.transfer_id.in_(by_id))) if headers else []
        totals=defaultdict(lambda:dict(quantity_milli=0,value_cents=0))
        for move in moves:
            sign=1 if move.kind=='dispatch' else -1 if move.kind in {'accept','return_receive'} else 0
            totals[move.line_id]['quantity_milli']+=sign*move.quantity_milli
            totals[move.line_id]['value_cents']+=sign*move.value_cents
        for loss in bounded(db,TransferLossPosting,select(TransferLossPosting).where(TransferLossPosting.transfer_id.in_(by_id))):
            totals[loss.line_id]['quantity_milli']-=loss.quantity_milli
            totals[loss.line_id]['value_cents']-=loss.value_cents
        rows=[]
        for line in lines:
            total=totals[line.id]
            if total['quantity_milli']<=0:continue
            header=by_id[line.transfer_id]
            rows.append(dict(transfer_id=header.id,number=header.number,case_id=header.from_case_id,store_id=header.from_store_id,
                to_store_id=header.to_store_id,name=line.name,sku=line.sku,unit=line.unit,**total))
        settlements=defaultdict(int)
        for posting in bounded(db,TransferSettlement):settlements[posting.store_id]+=posting.amount_cents
        for posting in bounded(db,TransferLossSettlement):settlements[posting.store_id]+=posting.amount_cents
        return rows,settlements
    finally:
        if previous is None:db.info.pop('_transfer_authority',None)
        else:db.info['_transfer_authority']=previous
