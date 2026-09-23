"""Exact source rows for losses, allocated burdens and real external recovery.

The root analytics catalogue supplies period filters and chart/CSV definitions.
Original physical cost, store burden, confirmed recovery and cash are separate
measures and must never be added as if they were four copies of sales income.
"""
from sqlalchemy import select,or_
from fastapi import HTTPException
from .transfer_models import MaterialTransfer,TransferLine,TransferMovement
from .transfer_exception_models import (TransferException,TransferLossPosting,TransferLossSettlement,
    TransferRecoveryClaim,TransferRecoveryPlan,TransferRecoveryReview,TransferRecoveryCancellation,TransferRecoveryPayment)


def analytics_rows(db,user):
    if user.role not in {'admin','manager','finance','auditor'}:raise HTTPException(403,'运输损失与追偿金额仅供财务管理岗位查看')
    ids=tuple(db.info.get('store_scope') or ())
    if not ids:raise HTTPException(403,'运输损失汇总缺少明确授权门店')
    old=db.info.get('_transfer_authority');db.info['_transfer_authority']=('report',ids)
    def bounded(stmt):
        result=list(db.scalars(stmt.limit(25001)))
        if len(result)>25000:raise HTTPException(413,'运输损失来源超过25000条，请分批查询，不能显示截断汇总')
        return result
    try:
        parents={p.id:p for p in bounded(select(MaterialTransfer).where(or_(MaterialTransfer.from_store_id.in_(ids),MaterialTransfer.to_store_id.in_(ids))))}
        exceptions={e.id:e for e in bounded(select(TransferException).where(TransferException.transfer_id.in_(parents)))}
        lines={l.id:l for l in bounded(select(TransferLine).where(TransferLine.transfer_id.in_(parents)))}
        origins={m.id:m for m in bounded(select(TransferMovement).where(TransferMovement.transfer_id.in_(parents)))}
        aggregate=bool(getattr(user,'_aggregate_scope',False) or db.info.get('aggregate_scope') or len(ids)>1)
        result={k:[] for k in ('losses','burdens','recovery_confirmations','recovery_cash','recovery_balances','clearing')}
        def base(sid,eid):
            e=exceptions[eid];parent=parents[e.transfer_id];cid=parent.from_case_id if sid==parent.from_store_id else parent.to_case_id
            line=lines[origins[e.original_id].line_id]
            return dict(exception_id=eid,transfer_id=parent.id,store_id=sid,number=parent.number,
                case_id=None if aggregate else cid,route=None if aggregate else 'transfer-exceptions/'+str(eid),
                item_id=line.source_item_id if sid==parent.from_store_id else None,name=line.name,sku=line.sku,unit=line.unit)
        for p in bounded(select(TransferLossPosting)):
            common=base(p.store_id,p.exception_id)
            result['losses'].append(dict(common,id=p.id,business_date=p.business_date.isoformat(),quantity_milli=p.quantity_milli,amount_cents=p.value_cents))
            result['burdens'].append(dict(common,id='source:'+str(p.id),business_date=p.business_date.isoformat(),amount_cents=p.source_bearer_cents))
        for x in bounded(select(TransferLossSettlement)):
            common=base(x.store_id,x.exception_id)
            result['clearing'].append(dict(common,id=x.id,origin_kind='material_loss',posting_id=x.posting_id,counterparty_store_id=x.counterparty_store_id,business_date=x.business_date.isoformat(),amount_cents=x.amount_cents))
            if x.amount_cents<0:result['burdens'].append(dict(common,id='destination:'+str(x.id),business_date=x.business_date.isoformat(),amount_cents=-x.amount_cents))
        claims=bounded(select(TransferRecoveryClaim));plans=bounded(select(TransferRecoveryPlan));reviews=bounded(select(TransferRecoveryReview));cancellations=bounded(select(TransferRecoveryCancellation));payments=bounded(select(TransferRecoveryPayment))
        plan_by={};review_by={r.plan_id:r for r in reviews};cancelled={r.plan_id for r in cancellations};payment_by={}
        for p in plans:plan_by.setdefault(p.claim_id,[]).append(p)
        for p in payments:payment_by.setdefault(p.claim_id,[]).append(p)
        for c in claims:
            common=base(c.store_id,c.exception_id);common.update(claim_id=c.id,counterparty='追偿往来方'+str(c.id) if aggregate else c.counterparty_snapshot['name'])
            latest=0;pending=0
            for p in sorted(plan_by.get(c.id,[]),key=lambda p:p.revision):
                review=review_by.get(p.id)
                if review and review.decision=='approve':
                    result['recovery_confirmations'].append(dict(common,id=review.id,plan_id=p.id,business_date=review.business_date.isoformat(),amount_cents=p.target_cents-latest));latest=p.target_cents
                elif not review and p.id not in cancelled:pending=p.target_cents
            net=0
            for p in payment_by.get(c.id,[]):
                amount=p.amount_cents*(1 if p.direction=='in' else -1);net+=amount
                result['recovery_cash'].append(dict(common,id=p.id,cash_id=p.cash_id,direction=p.direction,business_date=p.business_date.isoformat(),amount_cents=amount))
            result['recovery_balances'].append(dict(common,id=c.id,target_cents=latest,paid_cents=net,due_cents=max(0,latest-net),refund_cents=max(0,net-latest),occupied_cents=max(latest,net,pending)))
        for values in result.values():values.sort(key=lambda r:(r['store_id'],str(r['id'])))
        return result
    finally:
        if old is None:db.info.pop('_transfer_authority',None)
        else:db.info['_transfer_authority']=old
