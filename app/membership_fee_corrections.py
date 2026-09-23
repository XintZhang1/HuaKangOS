"""Same original fee and period, independently approved recording corrections."""
from contextlib import contextmanager
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from .db import utcnow
from .models import CashEntry
from .flow_models import Case,Account,FileAsset
from .membership_models import MembershipFee,MembershipOrder
from .membership_fee_correction_models import MembershipFeeCorrectionRequest,MembershipFeeCorrection,MembershipFeeRefundBasis


def excluded_cash_ids(db):
    return set(db.scalars(select(MembershipFeeCorrection.original_cash_id)))|set(db.scalars(select(MembershipFeeCorrection.reversing_cash_id)))


def previous_cash_id(db,cash_id):
    return db.scalar(select(MembershipFeeCorrection.original_cash_id).where(MembershipFeeCorrection.corrected_cash_id==cash_id))


def effective_fee(db,fee):
    cursor=fee.cash_id;account=fee.account_id;seen=set()
    while True:
        if cursor in seen or len(seen)>=1000:raise HTTPException(409,'续会费原款更正链异常')
        seen.add(cursor)
        fact=db.scalar(select(MembershipFeeCorrection).where(MembershipFeeCorrection.original_cash_id==cursor))
        if not fact:break
        request=db.scalar(select(MembershipFeeCorrectionRequest).where(MembershipFeeCorrectionRequest.id==fact.request_id))
        if fact.fee_id!=fee.id or not request or request.status!='applied':raise HTTPException(409,'续会费原款更正来源异常')
        cursor=fact.corrected_cash_id;account=request.account_id
    cash=db.scalar(select(CashEntry).where(CashEntry.id==cursor))
    if not cash or cash.amount_cents!=fee.amount_cents or cash.direction!='in':raise HTTPException(409,'续会费有效原款金额不符')
    return SimpleNamespace(**{**{c.name:getattr(fee,c.name) for c in fee.__table__.columns},
        'cash_id':cursor,'account_id':account,'reference':cash.voucher_no})


def _root(db,fee):
    row=db.scalar(select(Case).where(Case.id==fee.case_id).with_for_update())
    if not row or row.kind!='membership' or row.state!='completed':raise HTTPException(409,'续会费缺少本店已完成原业务')
    return row


def _touch(db,root):
    # Both corrections and actual renew refunds update this same versioned row.
    # SELECT FOR UPDATE alone is not a write/CAS lock on SQLite.
    root.updated_at=utcnow();db.flush()


def _reserved(db,fee,own=None):
    if db.scalar(select(MembershipFeeCorrectionRequest.id).where(MembershipFeeCorrectionRequest.fee_id==fee.id,
        MembershipFeeCorrectionRequest.status=='reserved',MembershipFeeCorrectionRequest.id!=(own.id if own else -1))):
        raise HTTPException(409,'原续会费已有批准的登记更正，请先完成或取消')


def _pending_refund(db,fee):
    orders=db.scalars(select(MembershipOrder).where(MembershipOrder.purpose=='renew_refund',MembershipOrder.status.in_(['draft','approved'])))
    if any(o.values.get('period_id')==fee.period_id for o in orders):raise HTTPException(409,'原续会已有在办实际退款，请先完成或取消，再更正原款登记')


@contextmanager
def source(db,user,fee_id,customer_id,*,cash_id=None,version=None,own=None,touch=False):
    from . import business_finance_service as finance
    fee=finance._one(db,MembershipFee,fee_id)
    if fee.original_id or fee.amount_cents<=0:raise HTTPException(409,'请选择本店原正数续会费，不可更正实际退款或免费会期')
    root=_root(db,fee)
    if root.customer_id!=customer_id:raise HTTPException(409,'原续会费不属于所选本店客户')
    if version is not None:finance._version(root,version)
    current=effective_fee(db,fee)
    if cash_id is not None and current.cash_id!=cash_id:raise HTTPException(409,'原续会费已经更正，请刷新当前有效原款')
    _reserved(db,fee,own);_pending_refund(db,fee)
    proof=db.scalar(select(FileAsset).where(FileAsset.id==fee.evidence_id))
    if not proof or proof.case_id!=root.id:raise HTTPException(409,'原续会收款凭据缺失')
    from .file_security import require_usable
    require_usable(db,proof)
    cash=finance._one(db,CashEntry,current.cash_id)
    if touch:_touch(db,root)
    yield fee,current,root,cash


def prepare(db,user,customer,values):
    from . import business_finance_service as finance
    with source(db,user,values['fee_id'],customer.id,cash_id=values['original_cash_id'],version=values['source_version'],touch=True) as (fee,current,root,cash):
        account=finance._one(db,Account,values['account_id'])
        if not account.active:raise HTTPException(409,'正确原收款账户已经停用')
        finance.entities.cash_source_case(db,user,cash.id)
        finance.entities.require_account_entity(db,user,root,account.id,cash.business_date)
        refund=db.scalar(select(MembershipFee).where(MembershipFee.original_id==fee.id))
        return {**values,'source_version':root.version,'source_case_id':root.id,'original_account_id':current.account_id,
            'amount_cents':fee.amount_cents,'business_date':cash.business_date.isoformat(),
            'refunded_fee_id':refund.id if refund else None}


def create_request(db,row,values):
    from datetime import date
    fields={k:values[k] for k in ('fee_id','original_cash_id','original_account_id','account_id','reference','amount_cents','source_version','refunded_fee_id')}
    request=MembershipFeeCorrectionRequest(case_id=row.id,business_date=date.fromisoformat(values['business_date']),**fields)
    db.add(request);db.flush()


def request_for(db,row):
    request=db.scalar(select(MembershipFeeCorrectionRequest).where(MembershipFeeCorrectionRequest.case_id==row.id).with_for_update())
    if not request:raise HTTPException(409,'续会费更正缺少原来源申请')
    return request


def _unchanged_refund(db,fee,request):
    refund=db.scalar(select(MembershipFee.id).where(MembershipFee.original_id==fee.id))
    if refund!=request.refunded_fee_id:raise HTTPException(409,'原续会实际退款事实已变化，请取消申请后重新核对')


def approve(db,user,row,order):
    request=request_for(db,row)
    with source(db,user,request.fee_id,row.customer_id,cash_id=request.original_cash_id,touch=True) as (fee,current,root,cash):
        _unchanged_refund(db,fee,request);request.status='reserved'


def release(db,user,row):
    request=request_for(db,row);fee=db.scalar(select(MembershipFee).where(MembershipFee.id==request.fee_id))
    _touch(db,_root(db,fee));request.status='released'


def post(db,user,row,order,values):
    import uuid
    from . import business_finance_service as finance
    request=request_for(db,row)
    if request.status!='reserved':raise HTTPException(409,'续会费更正须先独立批准')
    if any(k in values for k in ('amount_cents','account_id','reference','allocations')):raise HTTPException(422,'续会费更正仅执行已批准内容，不能临时变更金额或账户凭证')
    with source(db,user,request.fee_id,row.customer_id,cash_id=request.original_cash_id,own=request,touch=True) as (fee,current,root,cash):
        _unchanged_refund(db,fee,request)
        contra,_=finance._cash(db,user,row,{'account_id':current.account_id,'reference':'FEE-CORRECTION-'+uuid.uuid4().hex,'evidence_id':values['evidence_id']},
            fee.amount_cents,'out','business_finance_member_fee_reverse',original_cash_id=current.cash_id)
        corrected,_=finance._cash(db,user,row,{'account_id':request.account_id,'reference':request.reference,'evidence_id':values['evidence_id']},
            fee.amount_cents,'in','business_finance_member_fee_corrected',exclude_original=current.cash_id,actual_date=request.business_date)
        request.status='applied'
        db.add(MembershipFeeCorrection(request_id=request.id,case_id=row.id,fee_id=fee.id,original_cash_id=current.cash_id,
            reversing_cash_id=contra.id,corrected_cash_id=corrected.id,evidence_id=values['evidence_id'],actor_id=user.id))
        finance._done(db,user,row,order)


def guard_refund(db,fee,*,touch=True):
    _reserved(db,fee)
    if touch:_touch(db,_root(db,fee))
    return effective_fee(db,fee)


def record_refund_basis(db,refund,original):
    db.add(MembershipFeeRefundBasis(refund_fee_id=refund.id,original_fee_id=original.id,original_cash_id=original.cash_id))


def sources(db,user,customer_id):
    from . import business_finance_service as finance
    rows=list(db.scalars(select(MembershipFee).join(Case,Case.id==MembershipFee.case_id).where(
        Case.customer_id==customer_id,MembershipFee.amount_cents>0).order_by(MembershipFee.id).limit(1001)))
    if len(rows)>1000:raise HTTPException(422,'本客户续会费超过本次1000笔核对范围')
    result=[]
    for fee in rows:
        try:
            with source(db,user,fee.id,customer_id) as (original,current,root,cash):
                refund=db.scalar(select(MembershipFee).where(MembershipFee.original_id==fee.id))
                result.append({'source_kind':'membership_fee','fee_id':fee.id,'cash_id':cash.id,'source_version':root.version,
                    'business_date':str(cash.business_date),'amount_cents':fee.amount_cents,'account':cash.account,'reference':cash.voucher_no,
                    'refunded_cents':fee.amount_cents if refund else 0,'net_amount_cents':0 if refund else fee.amount_cents,
                    'sources':[{'case_id':root.id,'number':root.number,'amount_cents':fee.amount_cents}]})
        except HTTPException as error:
            if error.status_code not in {403,404,409}:raise
    return result
