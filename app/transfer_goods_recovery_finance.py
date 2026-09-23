"""Dedicated escape from a found-goods lock: explicit original-party terms.

The finder never decides compensation law. These commands append the actual
counterparty's terms and independent approval to the original recovery ledger;
only an explicit actual refund writes cash. No commit inside these helpers.
"""
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .transfer_exception_models import TransferException,TransferRecoveryClaim,TransferRecoveryPlan,TransferRecoveryPayment
from .transfer_goods_recovery_models import GoodsTerms,GoodsRefund,GoodsPosting
from . import transfer_exception_recovery as recovery
from . import transfer_goods_recovery_service as s

ACTIONS={'terms','terms_approve','terms_reject','terms_cancel','pending_cancel','refund'}


def _claims(db,row):return s.rows(db,TransferRecoveryClaim,exception_id=row.exception_id)


def _original_action(db,user,row,original_exception,parent,case,action,v):
    previous=db.info.get('_found_original_action');db.info['_found_original_action']=(row.id,action,v['claim_id'])
    try:
        # The draft calls its guard as well as exposing the future hook, so
        # tests prove the dedicated exit remains usable with a live pause.
        s.guard_original_action(db,user,parent,action)
        recovery.act(db,user,original_exception,parent,case,case.store_id,action,v)
    finally:
        if previous is None:db.info.pop('_found_original_action',None)
        else:db.info['_found_original_action']=previous


def local_complete(db,row,parent,loss,sid):
    posting=None
    with s.transfer.coordination_scope(db,parent.from_store_id,(parent.from_store_id,parent.to_store_id)):
        posting=db.scalar(select(GoodsPosting).where(GoodsPosting.recovery_id==row.id))
    if not posting:return False
    if not posting.restored_quantity_milli:return True
    total=0;terms=s.rows(db,GoodsTerms,recovery_id=row.id)
    for claim in _claims(db,row):
        pos=recovery.position(db,claim)
        if pos['pending']:return False
        if pos['current']:
            if not any(t.claim_id==claim.id and t.plan_id==pos['current'].id for t in terms):return False
            if pos['paid_cents']>pos['target_cents']:return False
            total+=pos['occupied_cents']
        elif pos['paid_cents']:return False
    return total<=s.local_burden(db,parent,loss,sid)


def maybe_complete(db,user,row,parent,loss):
    if row.status!='financial':return
    complete=True
    for sid in (parent.from_store_id,parent.to_store_id):
        with s.transfer.coordination_scope(db,sid,(parent.from_store_id,parent.to_store_id)):
            complete=local_complete(db,row,parent,loss,sid) and complete
    if complete:row.status='closed';row.active_transfer_id=None


def describe(db,user,row,parent,loss,sid):
    result=[];terms=s.rows(db,GoodsTerms,recovery_id=row.id)
    for claim in _claims(db,row):
        pos=recovery.position(db,claim)
        item=dict(id=claim.id,version=claim.version,counterparty=claim.counterparty_snapshot['name'],
            target_cents=pos['target_cents'],paid_cents=pos['paid_cents'],refund_cents=pos['refund_cents'],
            pending_plan_id=pos['pending'].id if pos['pending'] else None,
            terms=[],actions=[],payments=[])
        own=[t for t in terms if t.claim_id==claim.id]
        for t in own:
            p=next(p for p in pos['plans'] if p.id==t.plan_id);review=pos['reviews'].get(p.id)
            item['terms'].append(dict(id=t.id,plan_id=t.plan_id,revision=p.revision,target_cents=p.target_cents,reason=p.reason,
                status='cancelled' if p.id in pos['cancelled'] else review.decision if review else 'pending'))
        for payment in pos['payments']:
            returned=sum(p.amount_cents for p in pos['payments'] if p.original_id==payment.id)
            item['payments'].append(dict(id=payment.id,direction=payment.direction,amount_cents=payment.amount_cents,account_id=payment.account_id,
                business_date=payment.business_date.isoformat(),unreturned_cents=payment.amount_cents-returned if payment.direction=='in' else 0))
        if row.status=='financial':
            if pos['pending']:
                is_own=any(t.plan_id==pos['pending'].id for t in own)
                if is_own and user.role in s.exc.MANAGER and user.id!=pos['pending'].actor_id:item['actions']+=['terms_approve','terms_reject']
                if user.id==pos['pending'].actor_id or user.role in s.exc.MANAGER:item['actions'].append('terms_cancel' if is_own else 'pending_cancel')
            elif pos['current'] and user.role in s.exc.FINANCE:
                item['actions'].append('terms')
                if pos['refund_cents'] and any(t.plan_id==pos['current'].id for t in own):item['actions'].append('refund')
        result.append(item)
    return result


def act(db,user,row,parent,loss,case,action,v):
    if row.status!='financial':raise HTTPException(409,'实际复验和原物资处理后，再按往来方原确认办理赔付变化')
    required=s.exc.MANAGER if action in {'terms_approve','terms_reject'} else s.exc.MANAGER|s.exc.FINANCE if action in {'terms_cancel','pending_cancel'} else s.exc.FINANCE
    if user.role not in required:raise HTTPException(403,'实际赔付由本店财务办理、另一主管独立确认')
    claim=db.scalar(select(TransferRecoveryClaim).where(TransferRecoveryClaim.id==v['claim_id']).with_for_update())
    if not claim or claim.exception_id!=row.exception_id:raise HTTPException(404,'不是本店原损失的赔付条目')
    if claim.version!=v['claim_version']:raise HTTPException(409,'原赔付目标或实际现金已变化')
    original_exception=s.exc._one(db,TransferException,row.exception_id);pos=recovery.position(db,claim)
    cap=s.local_burden(db,parent,loss,case.store_id)
    if action=='terms':
        if pos['pending'] or not pos['current']:raise HTTPException(409,'请先从专用入口撤回原未批准目标；只有原有效目标才能追加实际处理条件')
        if not 0<=v['target_cents']<=min(cap,pos['target_cents']):
            raise HTTPException(409,'新累计目标不能超过找回后本店剩余承担或原已确认目标；不能猜测额外赔偿')
        previous=pos['current'].id
        _original_action(db,user,row,original_exception,parent,case,'recovery_plan',v)
        current=recovery.position(db,claim)['pending']
        db.add(GoodsTerms(recovery_id=row.id,claim_id=claim.id,previous_plan_id=previous,plan_id=current.id));db.flush()
    elif action in {'terms_approve','terms_reject','terms_cancel','pending_cancel'}:
        plan=pos['pending']
        if not plan or plan.id!=v['plan_id']:raise HTTPException(409,'只能办理当前尚未生效的原赔付目标')
        own=db.scalar(select(GoodsTerms).where(GoodsTerms.recovery_id==row.id,GoodsTerms.plan_id==plan.id))
        if action=='pending_cancel':
            if own:raise HTTPException(409,'本次找到后的目标请使用本版撤回动作')
        elif not own:raise HTTPException(409,'本目标不是本次找到物资后的实际确认')
        if action=='terms_approve' and plan.target_cents>cap:raise HTTPException(409,'当前剩余承担已变化，不能批准旧目标')
        mapped={'terms_approve':'recovery_approve','terms_reject':'recovery_reject','terms_cancel':'recovery_cancel','pending_cancel':'recovery_cancel'}[action]
        _original_action(db,user,row,original_exception,parent,case,mapped,v)
    elif action=='refund':
        if not pos['current'] or pos['pending']:raise HTTPException(409,'须有原往来方明确的当前赔付条件和独立批准')
        terms=db.scalar(select(GoodsTerms).where(GoodsTerms.recovery_id==row.id,GoodsTerms.plan_id==pos['current'].id))
        if not terms:raise HTTPException(409,'不能用旧条件猜测找到物资后应退赔款')
        existing={p.id for p in pos['payments']}
        _original_action(db,user,row,original_exception,parent,case,'recovery_refund',v)
        payments=[p for p in recovery.position(db,claim)['payments'] if p.id not in existing]
        if len(payments)!=1:raise HTTPException(409,'原退款记录数量异常')
        db.add(GoodsRefund(recovery_id=row.id,terms_id=terms.id,payment_id=payments[0].id));db.flush()
    else:raise HTTPException(404,'不存在此原赔付动作')
    claim.updated_at=utcnow();db.flush();maybe_complete(db,user,row,parent,loss)
