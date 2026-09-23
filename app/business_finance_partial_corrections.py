"""Gross cash corrections retain actual refunds and replace only net allocations."""
from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .flow_models import Case,PaymentLink
from .models import CashEntry
from .business_finance_models import (FinanceCorrection,FinanceCashBatch,FinanceOrder,
    FinanceCorrectionBasis,FinanceCorrectionRefundSlice)

SOURCE_TABLES=('business_finance_correction_bases','business_finance_correction_refund_slices')


def partial_correction_case_ids(db):
    return set(db.scalars(select(FinanceCorrectionBasis.case_id)))


def basis_for_cash(db,cash_id):
    return db.scalar(select(FinanceCorrectionBasis).join(FinanceCorrection,FinanceCorrection.case_id==FinanceCorrectionBasis.case_id)
        .join(FinanceCashBatch,FinanceCashBatch.id==FinanceCorrection.corrected_batch_id).where(FinanceCashBatch.cash_id==cash_id))


def state(db,cash,links):
    previous=basis_for_cash(db,cash.id)
    inherited=list(db.scalars(select(FinanceCorrectionRefundSlice).where(FinanceCorrectionRefundSlice.basis_id==previous.id))) if previous else []
    refunds={s.refund_payment_id:db.scalar(select(PaymentLink).where(PaymentLink.id==s.refund_payment_id)) for s in inherited}
    current={p.id:0 for p in links}
    for refund in db.scalars(select(PaymentLink).where(PaymentLink.original_id.in_(current)).order_by(PaymentLink.id)):
        fact=db.scalar(select(CashEntry).where(CashEntry.id==refund.cash_id))
        if not fact or fact.category=='business_finance_correction_reverse':raise HTTPException(409,'原业务分配已被更正，须核对有效后继原款')
        refunds[refund.id]=refund;current[refund.original_id]+=refund.amount_cents
    if any(not p or p.direction!='out' for p in refunds.values()):raise HTTPException(409,'原实际退款切片不完整')
    if any(current[p.id]>p.amount_cents for p in links):raise HTTPException(409,'原退款已超过原分配')
    inherited_total=sum(s.amount_cents for s in inherited)
    if sum(p.amount_cents for p in links)+inherited_total!=cash.amount_cents:raise HTTPException(409,'原总收款、业务分配与历史退款不守恒')
    total=sum(p.amount_cents for p in refunds.values())
    return dict(previous_id=previous.id if previous else None,refunded_cents=total,
        refunds=sorted(refunds.values(),key=lambda p:p.id),remaining={p.id:p.amount_cents-current[p.id] for p in links})


def source_ids(links,current):return {p.case_id for p in links}|{p.case_id for p in current['refunds']}


def freeze(db,row,original,values,current):
    basis=FinanceCorrectionBasis(case_id=row.id,original_cash_id=original.id,previous_id=current['previous_id'],
        original_amount_cents=original.amount_cents,corrected_amount_cents=values['amount_cents'],refunded_cents=current['refunded_cents'])
    db.add(basis);db.flush()
    for p in current['refunds']:
        db.add(FinanceCorrectionRefundSlice(basis_id=basis.id,refund_payment_id=p.id,original_payment_id=p.original_id,
            source_case_id=p.case_id,amount_cents=p.amount_cents))
    db.flush();return basis


def validate(db,user,row,order,*,touch=False):
    from . import business_finance_service as f
    cash,links=f._correction_origin(db,user,order.values['original_cash_id'],row.customer_id,allow_partial=True)
    current=state(db,cash,links)
    basis=db.scalar(select(FinanceCorrectionBasis).where(FinanceCorrectionBasis.case_id==row.id))
    frozen=list(db.scalars(select(FinanceCorrectionRefundSlice).where(FinanceCorrectionRefundSlice.basis_id==basis.id))) if basis else []
    if not basis or (basis.original_amount_cents,basis.corrected_amount_cents,basis.refunded_cents,basis.previous_id)!=(cash.amount_cents,order.values['amount_cents'],current['refunded_cents'],current['previous_id']):
        raise HTTPException(409,'原款或实际退款已变化，请取消未执行申请后按原事实重新核对')
    if {(s.refund_payment_id,s.original_payment_id,s.source_case_id,s.amount_cents) for s in frozen}!={(p.id,p.original_id,p.case_id,p.amount_cents) for p in current['refunds']}:
        raise HTTPException(409,'原实际退款切片已变化，请重新核对申请')
    f._check_correction_allocations(order.values['allocations'],basis.corrected_amount_cents-basis.refunded_cents)
    # All competing commands share each original Case version and the cash lock.
    for key in sorted(source_ids(links,current)|{a['source_case_id'] for a in order.values['allocations']}):
        source=f._one(db,Case,key)
        if source.customer_id!=row.customer_id:raise HTTPException(409,'剩余原款分配属于其他客户')
        guard_source(db,key,own=row.id)
        f.source_details(db,user,key,False,True)
        if touch:source.updated_at=utcnow()
    db.flush();return cash,links,current


def guard_source(db,case_id,own=None):
    """Block a second original refund/correction while its net slice is approved."""
    own=own or db.info.get('_partial_finance_case')
    approved=list(db.scalars(select(FinanceCorrectionBasis).join(FinanceOrder,FinanceOrder.case_id==FinanceCorrectionBasis.case_id)
        .where(FinanceOrder.status=='approved')))
    for basis in approved:
        if basis.case_id==own:continue
        original_cases=set(db.scalars(select(PaymentLink.case_id).where(PaymentLink.cash_id==basis.original_cash_id)))
        original_cases.update(db.scalars(select(FinanceCorrectionRefundSlice.source_case_id).where(FinanceCorrectionRefundSlice.basis_id==basis.id)))
        order=db.scalar(select(FinanceOrder).where(FinanceOrder.case_id==basis.case_id))
        original_cases.update(v['source_case_id'] for v in order.values['allocations'])
        if case_id in original_cases:raise HTTPException(409,'原单剩余收款已有批准的误记更正，请先完成或取消该更正')


def guard_refund(db,original_payment_id):
    if not original_payment_id:return
    original=db.scalar(select(PaymentLink).where(PaymentLink.id==original_payment_id))
    if not original:return
    held=db.scalar(select(FinanceCorrectionBasis).join(FinanceOrder,FinanceOrder.case_id==FinanceCorrectionBasis.case_id)
        .where(FinanceCorrectionBasis.original_cash_id==original.cash_id,FinanceOrder.status=='approved'))
    if held and held.case_id!=db.info.get('_partial_finance_case'):
        raise HTTPException(409,'本笔原款已有批准的剩余款更正，请先完成或取消；不能同时实际退款')


@contextmanager
def execution(db,case_id):
    old=db.info.get('_partial_finance_case');db.info['_partial_finance_case']=case_id
    try:yield
    finally:
        if old is None:db.info.pop('_partial_finance_case',None)
        else:db.info['_partial_finance_case']=old


def describe(db,case_id):
    basis=db.scalar(select(FinanceCorrectionBasis).where(FinanceCorrectionBasis.case_id==case_id))
    if not basis:return None
    refunds=[]
    for s in db.scalars(select(FinanceCorrectionRefundSlice).where(FinanceCorrectionRefundSlice.basis_id==basis.id).order_by(FinanceCorrectionRefundSlice.id)):
        p=db.scalar(select(PaymentLink).where(PaymentLink.id==s.refund_payment_id));c=db.scalar(select(CashEntry).where(CashEntry.id==p.cash_id));source=db.scalar(select(Case).where(Case.id==s.source_case_id))
        refunds.append(dict(payment_id=p.id,case_id=p.case_id,number=source.number,amount_cents=p.amount_cents,account=c.account,reference=p.reference,business_date=p.business_date.isoformat()))
    return dict(basis_version=2,original_amount_cents=basis.original_amount_cents,corrected_amount_cents=basis.corrected_amount_cents,
        refunded_cents=basis.refunded_cents,original_net_cents=basis.original_amount_cents-basis.refunded_cents,
        corrected_net_cents=basis.corrected_amount_cents-basis.refunded_cents,refunds=refunds)


def ended_sale(db,user,row):
    """A finished sale may correct its retained money, never reopen its fulfillment."""
    if not db.info.get('_partial_finance_case') or row.kind!='order':return None
    from . import aftercare_service as care
    from .aftercare_models import AftercareSource,AftercareApplication,AftercareClaim,AftercareTender
    if not care.is_source_ended(db,row):return None
    if db.scalar(select(AftercareClaim.source_case_id).where(AftercareClaim.source_case_id==row.id)):
        raise HTTPException(409,'原销售售后尚在办理，须先完成或撤回原方案')
    link=db.scalar(select(AftercareSource).join(AftercareApplication,AftercareApplication.case_id==AftercareSource.case_id)
        .where(AftercareSource.source_case_id==row.id).order_by(AftercareApplication.id.desc()))
    if not link:raise HTTPException(409,'已结束销售缺少可验证的原售后来源')
    after=care.get_order(db,user,link.case_id);application=care._applied(db,after)
    if after.state not in {'completed','working'} or not application:raise HTTPException(409,'原售后已失效或尚未实际生效')
    for tender in care._rows(db,AftercareTender,plan_id=application.plan_id):
        if tender.kind=='cash' and tender.credit_cents!=care._tender_paid(db,tender):raise HTTPException(409,'原售后还有批准待退现金，请先完成原实际退款')
    return after,link


def fully_returned_insurance(db,row):
    """Only completely returned external/customer principal permits a closed-policy correction."""
    from . import insurance_service as s
    if not s.is_detailed(row) or not s._applied(db,row):return False
    from .insurance_models import InsuranceTender,InsuranceCustomerRefund
    plans=s._applied(db,row)
    if s._active_plan(db,row) or plans[-1].retained_cents or row.state=='cancelled':
        raise HTTPException(409,'原撤保仍有在办方案或保留保费；须先按原保险资金路径核对，不能挪动已代缴本金')
    if any(s._spent(db,t) for t in s._rows(db,InsuranceTender,case_id=row.id) if t.amount_cents>0):
        raise HTTPException(409,'保险原款仍在第三方，须先实际追回，不能用误记更正代替')
    for plan in plans:
        for selected in plan.returns:
            paid=sum(r.amount_cents for r in s._rows(db,InsuranceCustomerRefund,plan_id=plan.id,original_tender_id=selected['tender_id']))
            if paid!=selected['amount_cents']:raise HTTPException(409,'原撤保还有批准待退金额，须先完成实际退款')
    return True
