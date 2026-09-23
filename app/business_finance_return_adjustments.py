"""Independently approved append-only supplier return target changes."""
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .flow_models import Case,PaymentLink,Task
from .business_finance_models import FinanceOrder,FinanceReturnReceivable,FinanceReturnTargetRevision


def latest_revision(db,receivable):
    return db.scalar(select(FinanceReturnTargetRevision).where(FinanceReturnTargetRevision.receivable_id==receivable.id).order_by(FinanceReturnTargetRevision.revision.desc()))


def effective_target(db,receivable):
    revision=latest_revision(db,receivable)
    return revision.amount_cents if revision else receivable.amount_cents


def received(db,receivable):
    return sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in db.scalars(select(PaymentLink).where(PaymentLink.case_id==receivable.case_id)))


def guard_collection(db,receivable,own_case=None):
    rows=db.scalars(select(FinanceOrder).where(FinanceOrder.purpose=='other_return_adjust',FinanceOrder.status=='approved',
        FinanceOrder.values['receivable_id'].as_integer()==receivable.id))
    if any(r.case_id!=own_case for r in rows):raise HTTPException(409,'供应方应退目标正在独立批准更正，请先完成或取消该更正再登记回款')


def prepare(db,user,values):
    from . import business_finance_service as finance
    receivable=finance._one(db,FinanceReturnReceivable,values['receivable_id'])
    source,order=finance._order(db,user,receivable.case_id)
    finance._version(source,values['source_version'])
    if order.status not in {'approved','completed'}:raise HTTPException(409,'只有已独立批准的其他入库退货应收可以追加目标更正')
    guard_collection(db,receivable)
    from .business_finance_supplier_refunds import guard_target_adjustment
    guard_target_adjustment(db,receivable)
    previous=latest_revision(db,receivable);amount=effective_target(db,receivable)
    if values['amount_cents']==amount:raise HTTPException(409,'本次应退目标未变化')
    return {**values,'source_case_id':source.id,'original_amount_cents':amount,'previous_revision_id':previous.id if previous else None,'target_policy':'supplier_overpayment_v1'}


def validate(db,user,row,order,values):
    from . import business_finance_service as finance
    receivable=finance._one(db,FinanceReturnReceivable,order.values['receivable_id'])
    source,source_order=finance._order(db,user,receivable.case_id)
    finance._version(source,values['source_versions'].get(str(source.id)))
    previous=latest_revision(db,receivable)
    if (previous.id if previous else None)!=order.values['previous_revision_id'] or effective_target(db,receivable)!=order.values['original_amount_cents']:
        raise HTTPException(409,'原应退目标已有后继修订，请取消当前申请后重新核对')
    guard_collection(db,receivable,row.id)
    from .business_finance_supplier_refunds import guard_target_adjustment
    guard_target_adjustment(db,receivable)
    source.updated_at=utcnow();db.flush()
    return receivable,source,source_order,previous


def post(db,user,row,order,values):
    from . import business_finance_service as finance
    receivable,source,source_order,previous=validate(db,user,row,order,values)
    paid=received(db,receivable);target=order.values['amount_cents']
    revision=FinanceReturnTargetRevision(case_id=row.id,receivable_id=receivable.id,revision=previous.revision+1 if previous else 1,
        previous_id=previous.id if previous else None,original_amount_cents=order.values['original_amount_cents'],amount_cents=target,
        received_cents=paid,received_payment_ids=list(db.scalars(select(PaymentLink.id).where(PaymentLink.case_id==source.id).order_by(PaymentLink.id))),evidence_id=values['evidence_id'],actor_id=user.id)
    db.add(revision);source.amount_cents=target
    if paid==target:finance._done(db,user,source,source_order)
    else:
        source_order.status='approved';source.state='pending';source.completed_date=None
        task=db.scalar(select(Task).where(Task.case_id==source.id,Task.key=='business_finance_execute'))
        finance.flow.ensure_task(db,source,'business_finance_execute','核对供应方超收原款退款' if paid>target else '核对修订后的供应方实际回款','finance',
            reopen=True,due=None if task and task.status=='open' else source.due_date)
    finance._event(db,user,source,'return_target_adjust',values['reason'],detail={'adjustment_case_id':row.id,'old_target_cents':revision.original_amount_cents,'target_cents':target,'received_cents':paid})
    finance._done(db,user,row,order)


def describe(db,receivable):
    from .business_finance_service import clean
    from .business_finance_supplier_refunds import overpayment,reserved
    return {'receivable_id':receivable.id,'source_case_id':receivable.case_id,'original_amount_cents':receivable.amount_cents,
        'target_cents':effective_target(db,receivable),'received_cents':received(db,receivable),
        'overpayment_cents':overpayment(db,receivable),'refund_reserved_cents':reserved(db,receivable.id),
        'revisions':[clean(r) for r in db.scalars(select(FinanceReturnTargetRevision).where(FinanceReturnTargetRevision.receivable_id==receivable.id).order_by(FinanceReturnTargetRevision.revision))]}
