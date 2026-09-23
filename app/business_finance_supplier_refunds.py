"""Actual supplier overpayment refunds after immutable target revisions."""
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .flow_models import PaymentLink,Account
from .business_finance_models import FinanceSupplierRefund,FinanceReturnReceivable
from .business_finance_return_adjustments import effective_target,received,guard_collection


def reserved(db,receivable_id,original_payment_id=None,exclude=None):
    query=select(FinanceSupplierRefund).where(FinanceSupplierRefund.receivable_id==receivable_id,FinanceSupplierRefund.status=='reserved')
    if original_payment_id is not None:query=query.where(FinanceSupplierRefund.original_payment_id==original_payment_id)
    if exclude is not None:query=query.where(FinanceSupplierRefund.id!=exclude)
    return sum(r.amount_cents for r in db.scalars(query))


def overpayment(db,receivable):return max(0,received(db,receivable)-effective_target(db,receivable))


def guard_target_adjustment(db,receivable):
    if reserved(db,receivable.id):raise HTTPException(409,'原供应方超收退款已独立批准占额，请先完成或取消退款，再更正应退目标')


def original_capacity(db,receivable,payment,exclude=None):
    if payment.case_id!=receivable.case_id or payment.direction!='in' or payment.original_id is not None:
        raise HTTPException(409,'请选择本店原应收单的实际正向收款来源')
    returned=sum(p.amount_cents for p in db.scalars(select(PaymentLink).where(PaymentLink.original_id==payment.id,PaymentLink.direction=='out')))
    return min(payment.amount_cents-returned-reserved(db,receivable.id,payment.id,exclude),
        overpayment(db,receivable)-reserved(db,receivable.id,exclude=exclude))


def prepare(db,user,values):
    from . import business_finance_service as finance
    receivable=finance._one(db,FinanceReturnReceivable,values['receivable_id'])
    source,_=finance._order(db,user,receivable.case_id);finance._version(source,values['source_version'])
    guard_collection(db,receivable)
    original=finance._one(db,PaymentLink,values['original_payment_id'])
    if values['amount_cents']>original_capacity(db,receivable,original):raise HTTPException(409,'退款超过本次供应方超收待退或本笔原收款尚未退回额度')
    return {**values,'source_case_id':source.id,'target_cents':effective_target(db,receivable),'original_cash_id':original.cash_id,'original_account_id':original.account_id}


def create_request(db,row,values):
    db.add(FinanceSupplierRefund(case_id=row.id,receivable_id=values['receivable_id'],original_payment_id=values['original_payment_id'],amount_cents=values['amount_cents']))


def request_for(db,row):return db.scalar(select(FinanceSupplierRefund).where(FinanceSupplierRefund.case_id==row.id).with_for_update())


def validate(db,user,row,order,values,*,reserved_own=False):
    from . import business_finance_service as finance
    request=request_for(db,row);receivable=finance._one(db,FinanceReturnReceivable,request.receivable_id)
    source,source_order=finance._order(db,user,receivable.case_id)
    finance._version(source,values['source_versions'].get(str(source.id)))
    guard_collection(db,receivable)
    if effective_target(db,receivable)!=order.values['target_cents']:raise HTTPException(409,'原应退目标已修订，请取消当前退款申请并重新核对')
    original=finance._one(db,PaymentLink,request.original_payment_id)
    if request.amount_cents>original_capacity(db,receivable,original,request.id if reserved_own else None):raise HTTPException(409,'原款退款额度或其他已批准退款占额已变化')
    source.updated_at=utcnow();db.flush()
    return request,receivable,source,source_order,original


def approve(db,user,row,order,values):
    request,*_=validate(db,user,row,order,values);request.status='reserved'


def release(db,user,row):
    from . import business_finance_service as finance
    request=request_for(db,row);receivable=finance._one(db,FinanceReturnReceivable,request.receivable_id)
    source,_=finance._order(db,user,receivable.case_id);source.updated_at=utcnow();request.status='released';db.flush()


def post(db,user,row,order,values):
    from . import business_finance_service as finance
    request,receivable,source,source_order,original=validate(db,user,row,order,values,reserved_own=True)
    if request.status!='reserved':raise HTTPException(409,'供应方原款实退须先独立批准并占额')
    if values['account_id']!=original.account_id:raise HTTPException(409,'供应方超收须按这笔原收款账户实际退回')
    cash,account=finance._cash(db,user,row,values,request.amount_cents,'out','business_finance_other_return_refund',original_cash_id=original.cash_id)
    batch=finance._batch(db,user,row,cash,'supplier_refund',values['evidence_id'])
    finance._allocate(db,user,batch,cash,account,source,request.amount_cents,values['evidence_id'],original=original)
    request.status='applied';request.applied_batch_id=batch.id;db.flush()
    if received(db,receivable)==effective_target(db,receivable):finance._done(db,user,source,source_order)
    finance._event(db,user,source,'supplier_overpayment_refund',values['reason'],detail={'refund_case_id':row.id,'amount_cents':request.amount_cents,'original_payment_id':original.id,'cash_id':cash.id})
    finance._done(db,user,row,order)


def sources(db,receivable):
    result=[]
    for p in db.scalars(select(PaymentLink).where(PaymentLink.case_id==receivable.case_id,PaymentLink.direction=='in').order_by(PaymentLink.id)):
        available=original_capacity(db,receivable,p)
        if available>0:
            account=db.scalar(select(Account).where(Account.id==p.account_id))
            result.append({'original_payment_id':p.id,'amount_cents':p.amount_cents,'available_cents':available,'account_id':p.account_id,
                'account_name':account.name,'reference':p.reference,'business_date':p.business_date.isoformat()})
    return result
