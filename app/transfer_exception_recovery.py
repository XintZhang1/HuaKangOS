"""Local external recovery: accepted obligation, review and cash are separate.

No commits. The exception command owns parent/case version and receipt.
No cross-store files, bank accounts, cash or customer payment allocation.
"""
from datetime import date
import uuid
from sqlalchemy import select
from fastapi import HTTPException
from .db import today,utcnow
from .models import CashEntry
from .flow_models import Task,Account,PaymentLink
from .master_models import Supplier,Insurer
from .transfer_exception_models import (TransferRecoveryClaim,TransferRecoveryPlan,TransferRecoveryReview,
    TransferRecoveryCancellation,TransferRecoveryPayment)
from . import transfer_exception_service as s

ACTIONS={'recovery_create','recovery_plan','recovery_approve','recovery_reject','recovery_cancel','recovery_receive','recovery_refund'}
CATEGORIES={'in':'workflow_transfer_recovery','out':'workflow_transfer_rec_return'}


def rows(db,model,**where):return s._rows(db,model,**where)
def _first(db,model,**where):return next(iter(rows(db,model,**where)),None)
def _plan_rows(db,model,ids):
    if not ids:return []
    result=list(db.scalars(select(model).where(model.plan_id.in_(ids)).order_by(model.id).limit(25001)))
    if len(result)>25000:raise HTTPException(413,'追偿来源超过上限，不能返回截断结果')
    return result


def position(db,claim):
    plans=rows(db,TransferRecoveryPlan,claim_id=claim.id)
    ids={p.id for p in plans}
    review={r.plan_id:r for r in _plan_rows(db,TransferRecoveryReview,ids)}
    cancelled={r.plan_id for r in _plan_rows(db,TransferRecoveryCancellation,ids)}
    approved=[p for p in plans if p.id in review and review[p.id].decision=='approve']
    pending=[p for p in plans if p.id not in review and p.id not in cancelled]
    if len(pending)>1:raise HTTPException(409,'追偿存在多个在办版本，请核对原记录')
    current=approved[-1] if approved else None;active=pending[0] if pending else None
    payments=rows(db,TransferRecoveryPayment,claim_id=claim.id)
    paid=sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in payments)
    target=current.target_cents if current else 0
    return dict(current=current,pending=active,plans=plans,reviews=review,cancelled=cancelled,payments=payments,
        target_cents=target,paid_cents=paid,due_cents=max(0,target-paid),refund_cents=max(0,paid-target),
        # A reduced target does not release cash still held pending original
        # refund; otherwise a second claim could collect the same loss twice.
        occupied_cents=max(target,paid,active.target_cents if active else 0))


def burden(db,row,parent,sid):
    from .transfer_goods_recovery_service import original_remaining_burden
    return original_remaining_burden(db,row,parent,sid)


def _capacity(db,row,parent,sid,claim,target):
    from .transfer_goods_recovery_service import permit_original_capacity_reduction
    if permit_original_capacity_reduction(db,row,parent,sid,claim,target):return
    other=sum(position(db,c)['occupied_cents'] for c in rows(db,TransferRecoveryClaim,exception_id=row.id) if not claim or c.id!=claim.id)
    if target<0 or target+other>burden(db,row,parent,sid):
        raise HTTPException(409,'追偿确认额超过本店本次原损失承担未占用额；不以另一门店承担或假定赔款补足')


def _approved_task_actor(db,user,case,plan):
    if plan.actor_id==user.id:raise HTTPException(403,'本次追偿目标须由另一名本店主管复核，管理员不能自批')
    s._assert_task(db,user,case,f'transfer_recovery_{plan.claim_id}_review_{plan.id}')


def sync_tasks(db,user,row,parent,case):
    for claim in rows(db,TransferRecoveryClaim,exception_id=row.id):
        p=position(db,claim);desired={};prefix=f'transfer_recovery_{claim.id}_';active=p['pending'];current=p['current']
        if active:
            candidates=[u for u in s.flow.eligible_users(db,'manager',case.store_id) if u.id!=active.actor_id]
            if not candidates:raise HTTPException(409,'请先配置一名不同于本次追偿申请人的本店主管')
            desired[prefix+'review_'+str(active.id)]=('复核往来方真实确认的赔付目标','manager',candidates[0].id,active.due_date)
        elif p['due_cents']:desired[prefix+'receive']=('核对追偿实际到账凭据','finance',None,current.due_date)
        elif p['refund_cents']:desired[prefix+'refund']=('按减少后的追偿目标退回原实际赔款','finance',None,current.due_date)
        for task in list(db.scalars(select(Task).where(Task.case_id==case.id,Task.status=='open'))):
            if task.key.startswith(prefix) and task.key not in desired:s.flow.finish_task(db,case,task.key,user)
        for key,(label,role,assignee,due) in desired.items():
            task=s.flow.ensure_task(db,case,key,label,role,assignee=assignee,due=due,reopen=True)
            if active and task.assignee_id==active.actor_id:raise HTTPException(409,'当前追偿复核待办负责人不独立，请明确转交')


def describe(db,user,row,parent,sid):
    if user.role not in s.flow.MANAGEMENT:return []
    result=[]
    for c in rows(db,TransferRecoveryClaim,exception_id=row.id):
        p=position(db,c)
        item={'id':c.id,'version':c.version,'counterparty_kind':c.counterparty_kind,'counterparty_name':c.counterparty_snapshot['name'],
            'target_cents':p['target_cents'],'paid_cents':p['paid_cents'],'due_cents':p['due_cents'],'refund_cents':p['refund_cents'],
            'pending_plan_id':p['pending'].id if p['pending'] else None,'plans':[],'payments':[],'actions':[]}
        for plan in p['plans']:
            review=p['reviews'].get(plan.id)
            item['plans'].append(dict(id=plan.id,revision=plan.revision,target_cents=plan.target_cents,reason=plan.reason,evidence_id=plan.evidence_id,
                due_date=plan.due_date.isoformat(),status='cancelled' if plan.id in p['cancelled'] else review.decision if review else 'pending',
                reviewer_id=review.actor_id if review else None))
        for payment in p['payments']:
            returned=sum(v.amount_cents for v in p['payments'] if v.original_id==payment.id)
            item['payments'].append(dict(id=payment.id,direction=payment.direction,amount_cents=payment.amount_cents,account_id=payment.account_id,
                reference=payment.reference,business_date=payment.business_date.isoformat(),evidence_id=payment.evidence_id,
                unreturned_cents=payment.amount_cents-returned if payment.direction=='in' else 0))
        if p['pending']:
            if user.role in s.MANAGER:item['actions']+=['recovery_approve','recovery_reject']
            if user.id==p['pending'].actor_id or user.role in s.MANAGER:item['actions'].append('recovery_cancel')
        elif user.role in s.FINANCE:
            item['actions'].append('recovery_plan')
            if p['due_cents']:item['actions'].append('recovery_receive')
            if p['refund_cents']:item['actions'].append('recovery_refund')
        result.append(item)
    return result


def _cash(db,user,case,claim,plan,v,direction,original=None):
    account=db.scalar(select(Account).where(Account.id==v['account_id']).with_for_update())
    if not account or not account.active or original and original.account_id!=account.id:raise HTTPException(409,'请选择本店实际账户；退款必须使用该原款账户')
    account.updated_at=utcnow();db.flush()
    if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==v['reference'])) or db.scalar(select(PaymentLink.id).where(PaymentLink.account_id==account.id,PaymentLink.reference==v['reference'])):
        raise HTTPException(409,'该账户实际银行流水已被登记，不能再次作为追偿现金')
    actual=date.fromisoformat(v['business_date']) if isinstance(v['business_date'],str) else v['business_date']
    if actual>today() or actual<date(2000,1,1):raise HTTPException(422,'实际到账或退款日期须在允许范围内且不能晚于今天')
    if original and actual<original.business_date:raise HTTPException(422,'原款退回日期不得早于原实际到账')
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,case,account.id,actual,original_cash_id=original.cash_id if original else None)
    cash=CashEntry(doc_no='TRC-'+uuid.uuid4().hex[:20],business_date=actual,created_by=user.id,approval_state='approved',direction=direction,
        category=CATEGORIES[direction],amount_cents=v['amount_cents'],account=account.name,counterparty=claim.counterparty_snapshot['name'],
        payment_method=account.account_type,voucher_no=v['reference'],note='调拨损失追偿 '+case.number)
    db.add(cash);db.flush();record_cash_entity(db,user,case,cash,account.id,original_cash_id=original.cash_id if original else None)
    db.add(TransferRecoveryPayment(claim_id=claim.id,plan_id=plan.id,original_id=original.id if original else None,direction=direction,
        amount_cents=cash.amount_cents,account_id=account.id,reference=v['reference'],cash_id=cash.id,evidence_id=v['evidence_id'],actor_id=user.id,business_date=actual))


def act(db,user,row,parent,case,sid,action,v):
    if row.status!='posted':raise HTTPException(409,'先由双方确认实际损失及本店承担，再独立确认外部追偿')
    from .transfer_goods_recovery_service import guard_original_action
    guard_original_action(db,user,parent,action)
    managers={'recovery_approve','recovery_reject','recovery_cancel'}
    if user.role not in (s.MANAGER|s.FINANCE if action=='recovery_cancel' else s.MANAGER if action in managers else s.FINANCE):
        raise HTTPException(403,'本店财务办理真实追偿，主管独立复核；库管不办理资金')
    s._proof(db,user,case,v['evidence_id'],True)
    if action=='recovery_create':
        model=Supplier if v['counterparty_kind']=='carrier' else Insurer
        party=db.scalar(select(model).where(model.id==v['counterparty_id'],model.active.is_(True)))
        if not party:raise HTTPException(404,'本店启用的承运供应商或保险公司不存在')
        if v['target_cents']<=0:raise HTTPException(422,'首次确认追偿须为明确的正金额')
        _capacity(db,row,parent,sid,None,v['target_cents'])
        claim=TransferRecoveryClaim(exception_id=row.id,counterparty_kind=v['counterparty_kind'],
            supplier_id=party.id if model is Supplier else None,insurer_id=party.id if model is Insurer else None,
            counterparty_snapshot={'id':party.id,'code':party.code,'name':party.name,'version':party.version},requested_by=user.id)
        db.add(claim);db.flush();p=None
    else:
        claim=s._one(db,TransferRecoveryClaim,v['claim_id'])
        if claim.exception_id!=row.id:raise HTTPException(404,'不是本店本次损失的原追偿记录')
        if claim.version!=v['claim_version']:raise HTTPException(409,'原追偿目标或到账已变化，请刷新')
        p=position(db,claim)
    if action in {'recovery_create','recovery_plan'}:
        if p and p['pending']:raise HTTPException(409,'请先复核或取消当前追偿目标版本')
        _capacity(db,row,parent,sid,claim,v['target_cents'])
        db.add(TransferRecoveryPlan(claim_id=claim.id,revision=len(p['plans'])+1 if p else 1,target_cents=v['target_cents'],due_date=v['due_date'],
            reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
    elif action in {'recovery_approve','recovery_reject','recovery_cancel'}:
        plan=p['pending']
        if not plan or plan.id!=v['plan_id']:raise HTTPException(409,'只能复核或取消当前尚未生效目标，已批准版本保留历史')
        if action=='recovery_cancel':
            if user.id!=plan.actor_id and user.role not in s.MANAGER:raise HTTPException(403,'只允许本版申请人或本店主管取消未生效追偿版本')
            db.add(TransferRecoveryCancellation(plan_id=plan.id,reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
        else:
            _approved_task_actor(db,user,case,plan)
            # A rejected proposal never allocates an amount. In particular an
            # actual asset recovery can lower the remaining burden while old
            # compensation is still held; that must not block rejecting a new
            # original condition and recording a corrected proposal.
            if action=='recovery_approve':_capacity(db,row,parent,sid,claim,plan.target_cents)
            db.add(TransferRecoveryReview(plan_id=plan.id,decision='approve' if action=='recovery_approve' else 'reject',reason=v['reason'],
                evidence_id=v['evidence_id'],actor_id=user.id,business_date=today()))
    elif action in {'recovery_receive','recovery_refund'}:
        if p['pending'] or not p['current']:raise HTTPException(409,'须先完成当前追偿目标的独立复核，再登记真实收退款')
        incoming=action=='recovery_receive';limit=p['due_cents'] if incoming else p['refund_cents']
        if not 0<v['amount_cents']<=limit:raise HTTPException(409,'实际款项超过当前已确认应收或原款应退额')
        s._assert_task(db,user,case,f'transfer_recovery_{claim.id}_'+('receive' if incoming else 'refund'))
        original=None
        if not incoming:
            original=s._one(db,TransferRecoveryPayment,v['original_id'])
            returned=sum(x.amount_cents for x in p['payments'] if x.original_id==original.id)
            if original.claim_id!=claim.id or original.direction!='in' or v['amount_cents']>original.amount_cents-returned:raise HTTPException(409,'超过本追偿该笔原实际到账尚未退回额')
        _cash(db,user,case,claim,p['current'],v,'in' if incoming else 'out',original)
    claim.updated_at=utcnow();db.flush();sync_tasks(db,user,row,parent,case)
    s.flow.log_event(db,user,case,'transfer_recovery_progress','调拨追偿事实已追加',detail={'exception_id':row.id,'claim_id':claim.id})
