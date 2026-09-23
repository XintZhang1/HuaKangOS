"""Original prepayment/top-up recording corrections; never actual refunds.

The original receipt and issuance remain immutable. Only the difference changes
unused principal; existing consumption, refunds and reservations stay attached.
"""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import utcnow
from .flow_models import Case,Account,PaymentLink
from .models import CashEntry
from .business_finance_models import (FinanceOrder,FinanceAdvance,FinanceAdvanceEntry,
    FinanceStoredCorrectionRequest,FinanceStoredCorrection)


def effective_cash(db,root_cash_id,account_id):
    """Return current recording without replacing the immutable issuance source."""
    cursor=root_cash_id;seen=set()
    while cursor:
        if cursor in seen or len(seen)>=1000:raise HTTPException(409,'原款更正链异常，请核对原始凭据')
        seen.add(cursor)
        correction=db.scalar(select(FinanceStoredCorrection).where(FinanceStoredCorrection.original_cash_id==cursor))
        if not correction:break
        order=db.scalar(select(FinanceOrder).where(FinanceOrder.case_id==correction.case_id))
        cursor=correction.corrected_cash_id
        if cursor:account_id=order.values['account_id']
    cash=db.scalar(select(CashEntry).where(CashEntry.id==cursor)) if cursor else None
    return cash,account_id


def effective_group_topup(db,original):
    cash,account_id=effective_cash(db,original.cash_id,original.account_id)
    return SimpleNamespace(**{**{c.name:getattr(original,c.name) for c in original.__table__.columns},
        'amount_cents':cash.amount_cents if cash else 0,'cash_id':cash.id if cash else None,
        'account_id':account_id,'reference':cash.voucher_no if cash else None})


def pending_group_reduction(db,topup_id):
    return db.scalar(select(func.coalesce(func.sum(FinanceStoredCorrectionRequest.reserved_cents),0)).where(
        FinanceStoredCorrectionRequest.topup_id==topup_id,FinanceStoredCorrectionRequest.status=='reserved')) or 0


@contextmanager
def source(db,user,cash_id,customer_id,version=None,*,allow_bundle=False):
    from . import group_service as group
    from .group_models import GroupEntry,GroupRefundRequest
    from . import business_finance_service as finance
    with group.authority(db,user,group.READ_ROLES) as sid:
        cash=finance._one(db,CashEntry,cash_id)
        if cash.direction!='in' or cash.approval_state!='approved':raise HTTPException(409,'只可更正本店原实际收款的误记')
        if db.scalar(select(FinanceStoredCorrection.id).where(FinanceStoredCorrection.original_cash_id==cash.id)):
            raise HTTPException(409,'这笔原款已经更正，请从后继有效原款申请')
        cursor=cash.id;seen=set()
        while True:
            if cursor in seen or len(seen)>=1000:raise HTTPException(409,'原款更正链异常')
            seen.add(cursor)
            prior=db.scalar(select(FinanceStoredCorrection).where(FinanceStoredCorrection.corrected_cash_id==cursor))
            if not prior:break
            cursor=prior.original_cash_id
        advance=db.scalar(select(FinanceAdvance).where(FinanceAdvance.cash_id==cursor).with_for_update())
        topup=db.scalar(select(GroupEntry).where(GroupEntry.cash_id==cursor,GroupEntry.store_id==sid,GroupEntry.purpose=='topup'))
        if not advance and not topup:raise HTTPException(409,'原款不是本店独立预收或普通会员充值')
        origin=finance._one(db,Case,advance.case_id if advance else topup.case_id)
        if origin.customer_id!=customer_id:raise HTTPException(409,'原款不属于所选本店客户')
        bundle=None
        if advance:
            wallet=advance;kind='advance';account_id=advance.account_id
            refunded=-sum(e.amount_cents for e in db.scalars(select(FinanceAdvanceEntry).where(FinanceAdvanceEntry.advance_id==advance.id,FinanceAdvanceEntry.purpose=='refund')))
        else:
            from .recharge_bundle_service import guard_principal_refund
            from .recharge_bundle_models import RechargeBundlePurchase
            bundle=db.scalar(select(RechargeBundlePurchase).where(RechargeBundlePurchase.principal_entry_id==topup.id))
            if bundle and not allow_bundle:guard_principal_refund(db,topup.id)
            wallet=group._member(db,topup.member_id,sid);kind='member';account_id=topup.account_id
            refunded=-sum(e.amount_cents for e in db.scalars(select(GroupEntry).where(GroupEntry.original_id==topup.id,GroupEntry.purpose=='refund',GroupEntry.store_id==sid)))
        current,account_id=effective_cash(db,cursor,account_id)
        if not current or current.id!=cash.id:raise HTTPException(409,'请重新核对当前有效原款')
        if version is not None:finance._version(wallet,version)
        yield {'cash':cash,'root_cash_id':cursor,'wallet':wallet,'kind':kind,'advance':advance,'topup':topup,
            'case':origin,'account_id':account_id,'refunded_cents':refunded,'bundle':bundle}
        # Group authority must remain in force until its balance/ledger flush.
        db.flush()


def _available(db,s,amount,own=None):
    if amount<s['refunded_cents']:raise HTTPException(409,'正确原款不能少于已经实际退回的原款；请另行追偿，不能覆盖已发生退款')
    pending=list(db.scalars(select(FinanceStoredCorrectionRequest).where(
        FinanceStoredCorrectionRequest.original_cash_id==s['cash'].id,FinanceStoredCorrectionRequest.status=='reserved')))
    if any(not own or r.id!=own.id for r in pending):raise HTTPException(409,'这笔原款已有批准的更正，请先完成或取消原申请')
    reduction=max(0,s['cash'].amount_cents-amount)
    available=s['wallet'].balance_cents-s['wallet'].reserved_cents+(own.reserved_cents if own and own.status=='reserved' else 0)
    if reduction>available:raise HTTPException(409,'更正差额超过尚未消费且未占用的本金；已履约抵用须先走原单退回或另行追偿')
    if s['topup']:
        from .group_models import GroupRefundRequest
        held=db.scalar(select(func.coalesce(func.sum(GroupRefundRequest.amount_cents),0)).where(
            GroupRefundRequest.original_id==s['topup'].id,GroupRefundRequest.status=='approved')) or 0
        if amount<s['refunded_cents']+held:raise HTTPException(409,'更正后的原充值不足以履行已批准退款，请先核对或撤销未支付申请')
    return reduction


def prepare(db,user,customer,values):
    from . import business_finance_service as finance
    with source(db,user,values['original_cash_id'],customer.id,values['source_version'],allow_bundle=bool(values.get('bundle_purchase_id'))) as s:
        reduction=_available(db,s,values['amount_cents'])
        actual_date=finance._correction_date(values,s['cash'])
        if values['amount_cents']:
            account=finance._one(db,Account,values['account_id'])
            if not account.active:raise HTTPException(409,'正确原收款账户已经停用')
        extra={}
        if s['bundle']:
            from .business_finance_bundle_corrections import prepare as prepare_bundle
            extra=prepare_bundle(db,user,s,values)
        elif values.get('bundle_purchase_id'):raise HTTPException(409,'所选原款不属于明确的充值组合批次')
        return {**values,**extra,'actual_business_date':actual_date.isoformat(),'source_kind':s['kind'],
            'source_case_id':s['case'].id,'advance_id':s['advance'].id if s['advance'] else None,
            'member_id':s['wallet'].id if s['topup'] else None,'topup_id':s['topup'].id if s['topup'] else None,
            'original_amount_cents':s['cash'].amount_cents,'reserved_cents':reduction}


def create_request(db,row,values):
    request=FinanceStoredCorrectionRequest(case_id=row.id,source_kind=values['source_kind'],advance_id=values['advance_id'],
        member_id=values['member_id'],topup_id=values['topup_id'],original_cash_id=values['original_cash_id'],
        original_amount_cents=values['original_amount_cents'],corrected_amount_cents=values['amount_cents'],reserved_cents=values['reserved_cents'])
    db.add(request);db.flush()
    if values.get('bundle_purchase_id'):
        from .business_finance_bundle_corrections import create
        create(db,request,values)


def request_for(db,row):
    return db.scalar(select(FinanceStoredCorrectionRequest).where(FinanceStoredCorrectionRequest.case_id==row.id).with_for_update())


def approve(db,user,row,order):
    request=request_for(db,row)
    with source(db,user,request.original_cash_id,row.customer_id,allow_bundle=bool(order.values.get('bundle_purchase_id'))) as s:
        _available(db,s,request.corrected_amount_cents)
        if s['bundle']:
            from .business_finance_bundle_corrections import approve as approve_bundle
            approve_bundle(db,request,s)
        s['wallet'].reserved_cents+=request.reserved_cents;s['wallet'].updated_at=utcnow();request.status='reserved'


def release(db,user,row):
    request=request_for(db,row)
    if request.status=='reserved':
        from .business_finance_bundle_corrections import correction_for,release as release_bundle
        with source(db,user,request.original_cash_id,row.customer_id,allow_bundle=bool(correction_for(db,request))) as s:
            if s['bundle']:release_bundle(db,request,s)
            s['wallet'].reserved_cents-=request.reserved_cents;s['wallet'].updated_at=utcnow();request.status='released'
    else:request.status='released'


def post(db,user,row,order,values):
    import uuid
    from . import business_finance_service as finance
    from . import group_service as group
    request=request_for(db,row)
    if request.status!='reserved':raise HTTPException(409,'更正必须独立批准并保留原款占额')
    with source(db,user,request.original_cash_id,row.customer_id,allow_bundle=bool(order.values.get('bundle_purchase_id'))) as s:
        _available(db,s,request.corrected_amount_cents,request)
        if s['bundle']:
            from .business_finance_bundle_corrections import post as post_bundle
            post_bundle(db,user,row,request,s,values)
        delta=request.corrected_amount_cents-request.original_amount_cents
        contra,_=finance._cash(db,user,row,{'account_id':s['account_id'],'reference':'CORRECTION-'+uuid.uuid4().hex,'evidence_id':values['evidence_id']},
            s['cash'].amount_cents,'out','business_finance_stored_reverse',original_cash_id=s['cash'].id)
        corrected=None
        if request.corrected_amount_cents:
            corrected,_=finance._cash(db,user,row,{**order.values,'evidence_id':values['evidence_id']},request.corrected_amount_cents,
                'in','business_finance_stored_corrected',exclude_original=s['cash'].id,actual_date=date.fromisoformat(order.values['actual_business_date']))
        entry=None
        if delta and s['advance']:
            entry=FinanceAdvanceEntry(advance_id=s['advance'].id,case_id=row.id,purpose='correction',amount_cents=delta,
                original_id=db.scalar(select(FinanceAdvanceEntry.id).where(FinanceAdvanceEntry.advance_id==s['advance'].id,FinanceAdvanceEntry.purpose=='receive')),
                evidence_id=values['evidence_id'],actor_id=user.id)
            db.add(entry);s['advance'].correction_cents+=delta
        elif delta:
            entry=group._entry(db,user,s['wallet'],row,'correction',delta,values['evidence_id'],s['topup'])
        s['wallet'].balance_cents+=delta;s['wallet'].reserved_cents-=request.reserved_cents;s['wallet'].updated_at=utcnow()
        request.status='applied';db.flush()
        db.add(FinanceStoredCorrection(request_id=request.id,case_id=row.id,original_cash_id=s['cash'].id,reversing_cash_id=contra.id,
            corrected_cash_id=corrected.id if corrected else None,advance_entry_id=entry.id if entry and s['advance'] else None,
            group_entry_id=entry.id if entry and s['topup'] else None,evidence_id=values['evidence_id'],actor_id=user.id))
        finance._done(db,user,row,order)


def sources(db,user,customer_id):
    from . import business_finance_service as finance
    from . import group_service as group
    from .group_models import GroupEntry
    with group.authority(db,user) as sid:
        keys=list(db.scalars(select(FinanceAdvance.cash_id).where(FinanceAdvance.customer_id==customer_id)))
        keys+=list(db.scalars(select(GroupEntry.cash_id).join(Case,Case.id==GroupEntry.case_id).where(
            Case.customer_id==customer_id,GroupEntry.store_id==sid,GroupEntry.purpose=='topup')))
        result=[]
        for root in keys:
            current,_=effective_cash(db,root,None)
            if not current:continue
            try:
                with source(db,user,current.id,customer_id,allow_bundle=True) as s:
                    bundle_values={}
                    if s['bundle']:
                        from .recharge_bundle_service import _rule
                        rule=_rule(db,s['bundle'].rule_id)
                        bundle_values={'bundle_purchase_id':s['bundle'].id,'bundle_name':rule.name,'bundle_principal_per_share':rule.principal_cents_per_share}
                    result.append({'cash_id':current.id,'business_date':current.business_date.isoformat(),'amount_cents':current.amount_cents,
                        'account':current.account,'reference':current.voucher_no,'source_kind':'bundle' if s['bundle'] else s['kind'],'source_version':s['wallet'].version,
                        **bundle_values,
                        'balance_cents':s['wallet'].balance_cents,'reserved_cents':s['wallet'].reserved_cents,
                        'sources':[{'case_id':s['case'].id,'number':s['case'].number,'amount_cents':current.amount_cents}]})
            except HTTPException as error:
                if error.status_code not in {403,404,409}:raise
        return result
