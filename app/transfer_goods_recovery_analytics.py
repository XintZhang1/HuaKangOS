"""Read-only found-goods sources, separate from original loss and original cash."""
from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy import select,or_
from .transfer_models import MaterialTransfer,TransferLine
from .transfer_exception_models import TransferException
from .transfer_goods_recovery_models import GoodsRecovery,GoodsFact,GoodsPosting,GoodsSettlement


@contextmanager
def report_authority(db,user):
    ids=tuple(db.info.get('store_scope') or ())
    if user.role not in {'admin','manager','finance','auditor'} or not ids:raise HTTPException(403,'找回原成本汇总须有明确门店及财务管理权限')
    keys=('_transfer_authority','_transfer_exception_authority','_transfer_goods_authority')
    previous={key:db.info.get(key) for key in keys}
    for key in keys:db.info[key]=('report',ids)
    try:yield ids
    finally:
        for key,value in previous.items():
            if value is None:db.info.pop(key,None)
            else:db.info[key]=value


def analytics_rows(db,user):
    """restored costs are positive; burden_reversals are negative cost changes.

    clearing contains immutable signed obligations before actual clearing.
    pending is one physical custody/transit fact per finding, never available
    inventory. Existing recovery analytics already includes target revisions and
    actual refunds, so neither is repeated in these data sets.
    """
    with report_authority(db,user) as ids:
        def bounded(stmt):
            result=list(db.scalars(stmt.limit(25001)))
            if len(result)>25000:raise HTTPException(413,'找回原物资来源超过25000条，请分批查询，不能显示截断汇总')
            return result
        parents={p.id:p for p in bounded(select(MaterialTransfer).where(or_(MaterialTransfer.from_store_id.in_(ids),MaterialTransfer.to_store_id.in_(ids))))}
        found={r.id:r for r in bounded(select(GoodsRecovery).where(GoodsRecovery.transfer_id.in_(parents)))}
        exceptions={r.id:r for r in bounded(select(TransferException).where(TransferException.transfer_id.in_(parents)))}
        lines={r.id:r for r in bounded(select(TransferLine).where(TransferLine.transfer_id.in_(parents)))}
        # Header already carries original loss; matching line is available via
        # the original exception's immutable movement, without source ledgers.
        from .transfer_models import TransferMovement
        moves={r.id:r for r in bounded(select(TransferMovement).where(TransferMovement.transfer_id.in_(parents)))}
        aggregate=bool(db.info.get('aggregate_scope') or getattr(user,'_aggregate_scope',False) or len(ids)>1)
        result={key:[] for key in ('restored','burden_reversals','clearing','pending','searches')}
        def base(sid,rid):
            row=found[rid];parent=parents[row.transfer_id];line=lines[moves[exceptions[row.exception_id].original_id].line_id]
            return dict(store_id=sid,recovery_id=rid,exception_id=row.exception_id,transfer_id=parent.id,number=parent.number,
                case_id=None if aggregate else parent.from_case_id if sid==parent.from_store_id else parent.to_case_id,
                route=None if aggregate else 'transfer-goods-recoveries/'+str(rid),name=line.name,sku=line.sku,unit=line.unit)
        for p in bounded(select(GoodsPosting)):
            common=base(p.store_id,p.recovery_id);common.update(business_date=p.business_date.isoformat(),posting_id=p.id)
            result['restored'].append(dict(common,id=p.id,quantity_milli=p.restored_quantity_milli,found_quantity_milli=p.found_quantity_milli,amount_cents=p.value_cents,stock_move_id=p.stock_move_id))
            result['burden_reversals'].append(dict(common,id='source:'+str(p.id),amount_cents=-p.source_reverse_cents))
        for s in bounded(select(GoodsSettlement)):
            common=base(s.store_id,s.recovery_id);common.update(business_date=s.business_date.isoformat(),posting_id=s.posting_id)
            result['clearing'].append(dict(common,id=s.id,origin_kind='material_found',original_id=s.original_id,counterparty_store_id=s.counterparty_store_id,amount_cents=s.amount_cents))
            if s.amount_cents>0:result['burden_reversals'].append(dict(common,id='destination:'+str(s.id),amount_cents=-s.amount_cents))
        history={}
        for fact in bounded(select(GoodsFact).where(GoodsFact.recovery_id.in_(found))):history.setdefault(fact.recovery_id,[]).append(fact)
        for row in found.values():
            if row.status not in {'preparing','transit','review','approved'}:continue
            own=history.get(row.id,[]);parent=parents[row.transfer_id];received=any(f.kind=='receive' for f in own);shipped=any(f.kind=='ship' for f in own)
            sid=parent.from_store_id if received else row.found_store_id
            if sid not in ids:continue
            result['pending'].append(dict(base(sid,row.id),id=row.id,quantity_milli=row.quantity_milli,status=row.status,
                in_transit=shipped and not received,custody_store_id=None if shipped and not received else sid,due_date=row.due_date.isoformat()))
        # Attribute one return search to its actual shipping store. Two local
        # reviews do not create two physical quantities in a group aggregate.
        from .transfer_goods_search_models import GoodsSearch, GoodsSearchOutcome, GoodsReappearance
        searches=bounded(select(GoodsSearch).where(GoodsSearch.recovery_id.in_(found)))
        outcomes={r.search_id:r for r in bounded(select(GoodsSearchOutcome).where(GoodsSearchOutcome.search_id.in_([s.id for s in searches])))}
        links=bounded(select(GoodsReappearance).where(GoodsReappearance.previous_recovery_id.in_(found)))
        latest={}
        for search in searches:
            if search.recovery_id not in latest or search.revision>latest[search.recovery_id].revision:
                latest[search.recovery_id]=search
        for rid,search in latest.items():
            row=found[rid];sid=row.found_store_id
            if sid not in ids:continue
            end=outcomes.get(search.id);kind=end.kind if end else 'review'
            used=sum(link.quantity_milli for link in links if link.previous_recovery_id==rid and found[link.recovery_id].status!='cancelled')
            remaining=row.quantity_milli-used if kind=='unlocated' else 0
            if remaining<0:raise HTTPException(409,'原查找数量来源不守恒，请核对原关联')
            result['searches'].append(dict(base(sid,rid),id=search.id,search_id=search.id,
                revision=search.revision,status=kind,quantity_milli=row.quantity_milli,
                reappeared_quantity_milli=used,unlocated_remaining_milli=remaining,
                business_date=(end.business_date if end else search.business_date).isoformat()))
        return result
