"""No-commit original procurement funding, cash and receipt allocation hooks."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from .db import today,utcnow
from .flow_models import Task
from .procurement_models import PurchasePayment,PurchaseReceipt,PurchaseReturnPosting
from .procurement_prepayment_models import (PurchasePrepaymentFacility as Facility,PurchasePrepaymentRequest as Request,
    PurchasePrepaymentDecision as Decision,PurchasePrepaymentDisbursement as Disbursement,PurchasePaymentAllocation as Allocation)
from .procurement_prepayment_sources import digest

ROLES={'prepay_request':{'admin','manager','finance'},'prepay_approve':{'admin','manager'},'prepay_reject':{'admin','manager'},
    'prepay_cancel':{'admin','manager','finance'},'prepay_expire':{'admin','manager','finance'},'prepay_pay':{'admin','finance'}}
LABELS={'prepay_request':'申请原采购预付款','prepay_approve':'独立批准原预付款','prepay_reject':'拒绝原预付款',
    'prepay_cancel':'取消未付预付款余量','prepay_expire':'结束过期未付预付款','prepay_pay':'登记已实际支付原采购预付款'}


def services():
    from . import procurement_service
    return procurement_service


def rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def enabled(db,row):return db.scalar(select(Facility.id).where(Facility.id==row.id)) is not None
def source_rows(db,row):
    requests=rows(db,Request,case_id=row.id);ids=[r.id for r in requests]
    return {Facility.__tablename__:list(db.scalars(select(Facility).where(Facility.id==row.id))),Request.__tablename__:requests,
        Decision.__tablename__:list(db.scalars(select(Decision).where(Decision.request_id.in_(ids)))),
        Disbursement.__tablename__:list(db.scalars(select(Disbursement).where(Disbursement.request_id.in_(ids)))),
        Allocation.__tablename__:rows(db,Allocation,case_id=row.id)}
def source_ids(db,row):return {name:{r.id for r in values} for name,values in source_rows(db,row).items()}
def new_sources(db,row,before):
    return {name:[dict(id=r.id,digest=digest(name,r)) for r in values if r.id not in before[name]]
        for name,values in source_rows(db,row).items() if any(r.id not in before[name] for r in values)}
def paid_request(db,request):
    return sum(p.amount_cents for p in db.scalars(select(PurchasePayment).join(Disbursement,Disbursement.payment_id==PurchasePayment.id).where(Disbursement.request_id==request.id)))
def reserved(db,row,excluding=None):
    return sum(r.amount_cents-paid_request(db,r) for r in rows(db,Request,case_id=row.id) if r.status in {'pending','approved'} and r.id!=excluding)
def payment_available(db,row,payment):
    returned=sum(p.amount_cents for p in rows(db,PurchasePayment,case_id=row.id) if p.original_id==payment.id)
    applied=sum(a.amount_cents for a in rows(db,Allocation,case_id=row.id) if a.payment_id==payment.id)
    return payment.amount_cents-returned-applied


def adjust_totals(db,row,result):
    if not enabled(db,row):return result
    accepted=result['received_cents']-result['returned_cents'];paid=result['paid_net_cents']
    commitment=(result['received_cents'] if row.data.get('receiving_closed') else row.amount_cents)-result['returned_cents']
    refund=max(0,paid-commitment)
    allocations=rows(db,Allocation,case_id=row.id);returns=rows(db,PurchaseReturnPosting,case_id=row.id)
    due=[]
    for receipt in sorted(rows(db,PurchaseReceipt,case_id=row.id),key=lambda r:(r.due_date,r.id)):
        amount=receipt.value_cents-sum(p.value_cents for p in returns if p.receipt_id==receipt.id)-sum(a.amount_cents for a in allocations if a.receipt_id==receipt.id)
        if amount>0:due.append(dict(receipt_id=receipt.id,due_date=receipt.due_date.isoformat(),amount_cents=amount))
    result.update(commitment_cents=commitment,cancelled_commitment_cents=row.amount_cents-commitment-result['returned_cents'],
        prepaid_cents=max(0,paid-accepted-refund),supplier_refund_due_cents=refund,
        prepayment_reserved_cents=reserved(db,row),applied_cents=sum(a.amount_cents for a in allocations),due_rows=due)
    return result


def _proof(db,user,row,key,cash=False):
    asset=services()._evidence(db,user,row,key)
    if asset.generated or asset.category not in ({'receipt'} if cash else {'receipt','procurement_contract','signed_contract','invoice'}):
        raise HTTPException(422,'实际付款须使用本单真实收付款凭据' if cash else '预付款申请与复核须使用本单真实财务或采购合同凭据')
    return asset


def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or task.assignee_id!=user.id:raise HTTPException(403,'请由当前原预付款待办接手人办理，先明确交接后才能换人')


def _end(db,user,request,action,reason,evidence_id=None):
    db.add(Decision(request_id=request.id,action=action,actor_id=user.id,evidence_id=evidence_id,reason=reason))
    request.status={'cancel':'cancelled','expire':'expired','approve':'approved','reject':'rejected'}[action];request.updated_at=utcnow()


def close_unpaid(db,user,row,reason):
    for request in rows(db,Request,case_id=row.id):
        if request.status in {'pending','approved'}:_end(db,user,request,'cancel',reason)
    db.flush()


def guard_cancel(db,row):
    if reserved(db,row):raise HTTPException(409,'尚有原预付款申请，请先明确取消未付申请余量，再取消原采购')


def guard_regular_payment(db,row,amount):
    if not enabled(db,row):return
    t=services().totals(db,row)
    if amount>t['commitment_cents']-t['paid_net_cents']-t['prepayment_reserved_cents']:
        raise HTTPException(409,'本次到货付款额度已被预付款申请占用，请先核对或取消未付申请余量')


def guard_refund(db,row,original,amount):
    if enabled(db,row) and amount>payment_available(db,row,original):
        raise HTTPException(409,'超过该原付款尚未抵用且未退回额度；请选择实际形成应退的原付款')


def apply(db,user,row,action,v):
    svc=services()
    if row.flow_version!=3 or row.state not in {'receiving','completed'}:raise HTTPException(409,'预付款须从已批准的采购v3原单办理；历史版本不自动推断')
    if action=='prepay_request':
        if row.data.get('receiving_closed'):raise HTTPException(409,'原采购到货已结束，不能新增预付款')
        if not today()<=v['valid_until']<=today()+timedelta(days=365):raise HTTPException(422,'付款申请有效期须在今天起一年内')
        _proof(db,user,row,v['evidence_id'])
        if not enabled(db,row):
            if rows(db,PurchasePayment,case_id=row.id):raise HTTPException(409,'原单已有实际款项，不能把历史付款重分为预付款；保留原结算流程')
            db.add(Facility(id=row.id,actor_id=user.id,evidence_id=v['evidence_id']));db.flush()
        t=svc.totals(db,row)
        if v['amount_cents']>t['commitment_cents']-t['paid_net_cents']-reserved(db,row):raise HTTPException(409,'申请超过有效采购约定尚未支付且未占申请的额度')
        db.add(Request(case_id=row.id,requested_by=user.id,**v));db.flush();return
    request=svc._one(db,Request,v['funds_request_id'])
    if request.case_id!=row.id:raise HTTPException(404,'预付款申请不属于本采购原单')
    if request.version!=v['funds_version']:raise HTTPException(409,'原预付款申请已经变化，请刷新核对')
    if action in {'prepay_approve','prepay_reject'}:
        if request.status!='pending':raise HTTPException(409,'本版预付款已复核或结束')
        if user.id==request.requested_by:raise HTTPException(403,'预付款申请人不能独立批准或拒绝自己的申请，管理员不例外')
        _task(db,user,row,'procurement_prepay_review_'+str(request.id));_proof(db,user,row,v['evidence_id'])
        if action=='prepay_approve':
            if request.valid_until<today():raise HTTPException(409,'申请已过期，请结束原申请')
            t=svc.totals(db,row)
            if request.amount_cents>t['commitment_cents']-t['paid_net_cents']-reserved(db,row,request.id):raise HTTPException(409,'有效采购约定或可付款额度已经变化')
        _end(db,user,request,action.removeprefix('prepay_'),v['reason'],v['evidence_id'])
    elif action in {'prepay_cancel','prepay_expire'}:
        if request.status not in {'pending','approved'}:raise HTTPException(409,'原申请没有未付余量可结束')
        if action=='prepay_cancel' and user.id!=request.requested_by and user.role not in {'admin','manager'}:raise HTTPException(403,'仅原申请人或本店主管可取消未付余量')
        if action=='prepay_expire' and request.valid_until>=today():raise HTTPException(409,'原付款申请尚未过期')
        _end(db,user,request,'cancel' if action=='prepay_cancel' else 'expire',v['reason'])
    elif action=='prepay_pay':
        if request.status!='approved' or request.valid_until<today():raise HTTPException(409,'须是有效期内、尚有未付额度的获准原申请')
        if v['confirmed'] is not True:raise HTTPException(422,'请由财务明确确认实际付款，批准申请不代表银行付款')
        _task(db,user,row,'procurement_prepay_pay_'+str(request.id));_proof(db,user,row,v['evidence_id'],True)
        t=svc.totals(db,row);amount=v['amount_cents']
        if amount>request.amount_cents-paid_request(db,request) or amount>t['commitment_cents']-t['paid_net_cents']-reserved(db,row,request.id):
            raise HTTPException(409,'实际付款超过原批准余量或有效采购约定剩余额度')
        payment=svc._cash(db,user,row,v,'out');db.add(Disbursement(request_id=request.id,payment_id=payment.id,actor_id=user.id));db.flush()
        if paid_request(db,request)==request.amount_cents:request.status='paid'
        request.updated_at=utcnow()
    db.flush()


def synchronize_allocations(db,user,row):
    if not enabled(db,row):return
    current=services().totals(db,row)
    if current['prepayment_reserved_cents']>max(0,current['commitment_cents']-current['paid_net_cents']):
        close_unpaid(db,user,row,'原实际退货已减少有效采购约定，结束原未付批准余量；需要付款时重新独立申请')
    receipts=rows(db,PurchaseReceipt,case_id=row.id);returns=rows(db,PurchaseReturnPosting,case_id=row.id)
    allocations=rows(db,Allocation,case_id=row.id)
    for receipt in receipts:
        related=[a for a in allocations if a.receipt_id==receipt.id]
        returned=[r for r in returns if r.receipt_id==receipt.id]
        excess=sum(a.amount_cents for a in related)-(receipt.value_cents-sum(r.value_cents for r in returned))
        for original in reversed([a for a in related if a.amount_cents>0]):
            if excess<=0:break
            left=original.amount_cents+sum(a.amount_cents for a in related if a.original_id==original.id)
            amount=min(excess,left)
            if amount:
                db.add(Allocation(case_id=row.id,payment_id=original.payment_id,receipt_id=receipt.id,amount_cents=-amount,
                    original_id=original.id,return_posting_id=returned[-1].id,actor_id=user.id));excess-=amount
        if excess>0:raise HTTPException(409,'原到货抵用无法完整冲回，本次实退须回滚核对')
    db.flush();allocations=rows(db,Allocation,case_id=row.id)
    needs={r.id:r.value_cents-sum(p.value_cents for p in returns if p.receipt_id==r.id)-sum(a.amount_cents for a in allocations if a.receipt_id==r.id) for r in receipts}
    for payment in rows(db,PurchasePayment,case_id=row.id):
        if payment.direction!='out':continue
        available=payment_available(db,row,payment)
        if available<0:raise HTTPException(409,'原付款抵用及退款超过原实际金额')
        for receipt in sorted(receipts,key=lambda r:(r.due_date,r.id)):
            amount=min(available,needs[receipt.id])
            if amount:
                db.add(Allocation(case_id=row.id,payment_id=payment.id,receipt_id=receipt.id,amount_cents=amount,actor_id=user.id));available-=amount;needs[receipt.id]-=amount
    db.flush()


def sync_tasks(db,user,row):
    svc=services();unresolved=False
    for request in rows(db,Request,case_id=row.id):
        prefix='procurement_prepay_';desired=None;assignee=None
        if request.status in {'pending','approved'}:
            unresolved=True
            if request.valid_until<today():desired=('expire','结束过期原预付款未付余量','finance')
            elif request.status=='pending':
                eligible=[u for u in svc.flow.eligible_users(db,'manager',row.store_id) if u.id!=request.requested_by]
                if not eligible:eligible=[u for u in svc.flow.eligible_users(db,'admin',row.store_id) if u.id!=request.requested_by]
                if not eligible:raise HTTPException(409,'请配置另一名本店主管独立复核预付款，不能由申请人自批')
                desired=('review','独立核对原采购预付款申请','manager');assignee=eligible[0].id
            else:desired=('pay','核对实际银行凭据并登记原采购预付款','finance')
        for name in ('review','pay','expire'):
            key=prefix+name+'_'+str(request.id)
            if desired and name==desired[0]:
                existing=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
                if name=='review' and existing and existing.assignee_id==request.requested_by:raise HTTPException(409,'当前复核接手人不独立，请明确交接给另一名主管')
                svc.flow.ensure_task(db,row,key,desired[1],desired[2],assignee=None if existing else assignee,due=None if existing else request.valid_until,reopen=True)
            else:svc.flow.finish_task(db,row,key,user)
    if unresolved:row.state='receiving';row.completed_date=None


def describe(db,user,row):
    if not enabled(db,row):return None
    payments=rows(db,PurchasePayment,case_id=row.id)
    return dict(requests=[dict(id=r.id,version=r.version,status=r.status,amount_cents=r.amount_cents,paid_cents=paid_request(db,r),
        unpaid_cents=r.amount_cents-paid_request(db,r),valid_until=r.valid_until.isoformat(),expired=r.valid_until<today(),requested_by=r.requested_by,
        evidence_id=r.evidence_id,reason=r.reason,decisions=[dict(id=d.id,action=d.action,actor_id=d.actor_id,evidence_id=d.evidence_id,reason=d.reason) for d in rows(db,Decision,request_id=r.id)]) for r in rows(db,Request,case_id=row.id)],
        original_cash=[dict(payment_id=p.id,available_cents=payment_available(db,row,p),account_id=p.account_id) for p in payments if p.direction=='out'],
        allocations=[dict(id=a.id,payment_id=a.payment_id,receipt_id=a.receipt_id,amount_cents=a.amount_cents,original_id=a.original_id,return_posting_id=a.return_posting_id) for a in rows(db,Allocation,case_id=row.id)])
