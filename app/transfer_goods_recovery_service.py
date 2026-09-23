"""Dedicated commands for goods found after an immutable loss.

Parent/case CAS serializes commands. Only the local actor receives stock or
returns cash; coordination creates only explicit paired obligations and tasks.
"""
from contextlib import contextmanager
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,or_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import utcnow,today
from .tenancy import single_store
from .flow_models import Case,Item,Task
from .models import Store
from .transfer_models import MaterialTransfer,TransferLine,TransferMovement
from .transfer_exception_models import TransferException,TransferLossPosting,TransferLossSettlement,TransferRecoveryClaim
from . import transfer_service as transfer,transfer_exception_service as exc
from .transfer_goods_recovery_models import GoodsRecovery,GoodsFact,GoodsPlan,GoodsReview,GoodsPosting,GoodsSettlement,GoodsReceipt
from .transfer_goods_recovery_math import allocation

LABELS={'preparing':'核对找回物资','transit':'找回物资实际退运中','review':'双方独立复核中','approved':'已批准待实际处理','financial':'实物已处理，原赔付仍需核对','closed':'找回已结清，赔付按确认条件办理','cancelled':'误关联已撤回','unlocated':'双方已结束本次查找，原物资仍未找到'}


@contextmanager
def authority(db,user,roles=exc.READ):
    with exc.authority(db,user,roles) as sid:
        previous=db.info.get('_transfer_goods_authority');db.info['_transfer_goods_authority']=(user.id,sid)
        try:yield sid
        finally:
            if previous is None:db.info.pop('_transfer_goods_authority',None)
            else:db.info['_transfer_goods_authority']=previous


@contextmanager
def original_authority(db):
    """Narrow internal read adapter for an already authenticated exception call."""
    if not db.info.get('_transfer_authority') or not db.info.get('_transfer_exception_authority'):
        raise HTTPException(403,'须先完成原调拨差异授权')
    sid=single_store(db);previous=db.info.get('_transfer_goods_authority')
    db.info['_transfer_goods_authority']=('original',sid)
    try:yield sid
    finally:
        if previous is None:db.info.pop('_transfer_goods_authority',None)
        else:db.info['_transfer_goods_authority']=previous


@contextmanager
def settlement_read_authority(db):
    """Immutable local settlement rows, under the clearing service's authority."""
    if not db.info.get('_reconciliation_authority'):raise HTTPException(403,'原找回往来须先通过清算授权')
    old=db.info.get('_transfer_goods_authority');db.info['_transfer_goods_authority']=('clearing',tuple(db.info.get('store_scope') or ()))
    try:yield
    finally:
        if old is None:db.info.pop('_transfer_goods_authority',None)
        else:db.info['_transfer_goods_authority']=old


def lock_clearing_parent(db,user,transfer_id,action):
    """Call before locking a clearing order/bucket/account; no commit here."""
    with authority(db,user,exc.FINANCE|exc.MANAGER) as sid:
        parent=transfer.get_transfer(db,transfer_id,sid)
        parent=db.scalar(select(MaterialTransfer).where(MaterialTransfer.id==parent.id).with_for_update().execution_options(populate_existing=True))
        if transfer.local_case(db,user,parent,sid).flow_version!=3:return
        parent.updated_at=utcnow();db.flush();guard_original_action(db,user,parent,action)


def clearing_pause_info(db,user,transfer_id):
    with authority(db,user,exc.FINANCE|exc.MANAGER|{'auditor'}) as sid:
        parent=transfer.get_transfer(db,transfer_id,sid)
        return db.scalar(select(GoodsRecovery.id).where(GoodsRecovery.active_transfer_id==parent.id))


def entity_has_unsettled(db,offsets):
    """Only a boolean leaves the already authorized local entity review."""
    if not db.info.get('_business_entity_authority'):raise HTTPException(403,'须先完成经营主体配置授权')
    sid=single_store(db);old=db.info.get('_transfer_goods_authority');db.info['_transfer_goods_authority']=('entity',sid)
    try:return any(row.amount_cents+offsets.get(('material_found',row.id),0) for row in db.scalars(select(GoodsSettlement)))
    finally:
        if old is None:db.info.pop('_transfer_goods_authority',None)
        else:db.info['_transfer_goods_authority']=old


def rows(db,model,**where):return exc._rows(db,model,**where)
def facts(db,row):return rows(db,GoodsFact,recovery_id=row.id)
def latest(db,row):return next(iter(reversed(rows(db,GoodsPlan,recovery_id=row.id))),None)


def original(db,parent,loss_id):
    # Deliberately read only this authenticated transfer's source loss. No
    # source-store history query and no file identity leaves the local DTO.
    with transfer.coordination_scope(db,parent.from_store_id,(parent.from_store_id,parent.to_store_id)):
        loss=db.scalar(select(TransferLossPosting).where(TransferLossPosting.id==loss_id,TransferLossPosting.transfer_id==parent.id))
        if not loss:raise HTTPException(404,'不是本调拨已确认的原损失')
        return loss


def totals(db,parent,loss):
    with transfer.coordination_scope(db,parent.from_store_id,(parent.from_store_id,parent.to_store_id)):
        completed=rows(db,GoodsPosting,loss_id=loss.id)
        return {k:sum(getattr(x,k) for x in completed) for k in ('found_quantity_milli','restored_quantity_milli','value_cents','source_reverse_cents','destination_reverse_cents')}


def portion(db,parent,loss,quantity,usable):
    p=totals(db,parent,loss)
    try:return allocation(loss.quantity_milli,loss.value_cents,loss.destination_bearer_cents,p['found_quantity_milli'],p['restored_quantity_milli'],p['value_cents'],p['destination_reverse_cents'],quantity,usable)
    except ValueError as error:raise HTTPException(409,str(error)) from error


def local_burden(db,parent,loss,sid):
    t=totals(db,parent,loss)
    return (loss.source_bearer_cents-t['source_reverse_cents']) if sid==parent.from_store_id else (loss.destination_bearer_cents-t['destination_reverse_cents'])


def guard_original_action(db,user,parent,action):
    """All dependent original commands check this after the shared Transfer CAS."""
    with authority(db,user):
        active=db.scalar(select(GoodsRecovery.id).where(GoodsRecovery.active_transfer_id==parent.id))
        # Dedicated compensation commands must be able to resolve the very
        # hold which blocks ordinary commands. The marker is set only around a
        # validated current finding/claim action, never from request fields.
        delegated=db.info.get('_found_original_action')
        if active and isinstance(delegated,tuple) and len(delegated)==3 and delegated[:2]==(active,action) and action in {'recovery_plan','recovery_approve','recovery_reject','recovery_cancel','recovery_refund'}:return
        # Recording already-paid incoming cash and cancelling an unexecuted
        # request remain factual exits; they do not create a new payment.
        if active and action in {'clearing_receive','clearing_cancel','clearing_reject','clearing_difference'}:return
        if active:
            raise HTTPException(409,'原物资找回尚在处理，请从找回专用入口核对实物或原赔付，不能绕过原批次锁')


def effective_burden(db,user,original_exception,parent,sid):
    """Effective original burden, including completed found batches."""
    with authority(db,user):
        with transfer.coordination_scope(db,parent.from_store_id,(parent.from_store_id,parent.to_store_id)):
            loss=db.scalar(select(TransferLossPosting).where(TransferLossPosting.exception_id==original_exception.id,TransferLossPosting.transfer_id==parent.id))
        if not loss:raise HTTPException(409,'原损失过账不存在')
        return local_burden(db,parent,loss,sid)


def original_remaining_burden(db,original_exception,parent,sid):
    with original_authority(db) as current:
        if current!=sid:raise HTTPException(403,'只能核对本店原追偿额度')
        with transfer.coordination_scope(db,parent.from_store_id,(parent.from_store_id,parent.to_store_id)):
            loss=db.scalar(select(TransferLossPosting).where(TransferLossPosting.exception_id==original_exception.id,TransferLossPosting.transfer_id==parent.id))
        if not loss:raise HTTPException(409,'原损失过账不存在')
        return local_burden(db,parent,loss,sid)


def permit_original_capacity_reduction(db,original_exception,parent,sid,claim,target):
    """First check in old _capacity, before the ordinary aggregate cap.

    Other claims' unreturned cash must not deadlock a strictly decreasing,
    explicitly confirmed original obligation. This permits no new claim, cash,
    increased target, or alternate claim under a delegated command.
    """
    delegated=db.info.get('_found_original_action')
    if not (db.info.get('_transfer_goods_authority') and isinstance(delegated,tuple) and len(delegated)==3
            and delegated[1] in {'recovery_plan','recovery_approve'} and claim and delegated[2]==claim.id):return False
    row=db.scalar(select(GoodsRecovery).where(GoodsRecovery.id==delegated[0],GoodsRecovery.active_transfer_id==parent.id,
        GoodsRecovery.exception_id==original_exception.id,GoodsRecovery.status=='financial'))
    if not row or sid!=single_store(db) or claim.store_id!=sid or claim.exception_id!=row.exception_id:return False
    from .transfer_exception_recovery import position
    pos=position(db,claim);loss=original(db,parent,row.loss_id)
    if not pos['current'] or type(target) is not int or not 0<=target<=min(pos['target_cents'],local_burden(db,parent,loss,sid)):return False
    if delegated[1]=='recovery_approve':
        from .transfer_goods_recovery_models import GoodsTerms
        if not pos['pending'] or pos['pending'].target_cents!=target or not db.scalar(select(GoodsTerms.id).where(
            GoodsTerms.recovery_id==row.id,GoodsTerms.claim_id==claim.id,GoodsTerms.plan_id==pos['pending'].id)):return False
    return True


def available_origins(db,user,transfer_id):
    with authority(db,user) as sid:
        parent=transfer.get_transfer(db,transfer_id,sid);case=exc._case(db,user,parent,sid)
        active=db.scalar(select(GoodsRecovery.id).where(GoodsRecovery.active_transfer_id==parent.id));result=[]
        with transfer.coordination_scope(db,parent.from_store_id,(parent.from_store_id,parent.to_store_id)):
            originals=rows(db,TransferLossPosting,transfer_id=parent.id)
        for loss in originals:
            done=totals(db,parent,loss);line=exc._one(db,TransferLine,loss.line_id)
            entry=dict(loss_id=loss.id,exception_id=loss.exception_id,name=line.name,sku=line.sku,unit=line.unit,
                available_quantity_milli=loss.quantity_milli-done['found_quantity_milli'])
            from .transfer_goods_search_service import prior_searches
            entry['prior_recoveries']=prior_searches(db,parent,loss)
            if user.role in exc.flow.MANAGEMENT:entry.update(original_value_cents=loss.value_cents,restored_value_cents=done['value_cents'])
            result.append(entry)
        return dict(transfer_id=parent.id,version=parent.version,case_id=case.id,case_version=case.version,active_recovery_id=active,items=result)


def _get(db,user,key,sid):
    row=db.scalar(select(GoodsRecovery).join(MaterialTransfer,MaterialTransfer.id==GoodsRecovery.transfer_id).where(GoodsRecovery.id==key,
        or_(MaterialTransfer.from_store_id==sid,MaterialTransfer.to_store_id==sid)))
    if not row:raise HTTPException(404,'本店找回原物资记录不存在')
    parent=transfer.get_transfer(db,row.transfer_id,sid);exc._case(db,user,parent,sid)
    return row,parent,original(db,parent,row.loss_id)


def custody(row,parent,history):
    if any(f.kind=='receive' for f in history):return parent.from_store_id
    if any(f.kind=='ship' for f in history):return None
    return row.found_store_id


def inspection(row,parent,history):
    sid=custody(row,parent,history)
    return next((f for f in reversed(history) if f.store_id==sid and f.kind in {'inspect','receive'}),None)


def _fact(db,user,row,case,kind,v):
    exc._proof(db,user,case,v['evidence_id'])
    f=GoodsFact(recovery_id=row.id,store_id=case.store_id,kind=kind,quantity_milli=row.quantity_milli,passed=v.get('passed') if kind in {'inspect','receive'} else None,
        result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id,business_date=today())
    db.add(f);db.flush();return f


def _independent(db,row,parent,plan,sid,prior=()):
    blocked={row.requested_by,plan.actor_id}|{f.actor_id for f in facts(db,row)}|{r.actor_id for r in prior}
    candidates=[u for u in exc.flow.eligible_users(db,'manager',sid) if u.id not in blocked]
    if not candidates:raise HTTPException(409,'请配置未参与本次找回、实物或方案的另一名本店主管，双方主管必须不同')
    return candidates[0].id


def sync(db,user,row,parent):
    history=facts(db,row);plan=latest(db,row);prefix=f'transfer_found_{row.id}_'
    match=next((f for f in history if f.kind=='match'),None);quality=inspection(row,parent,history)
    for sid,cid in ((parent.from_store_id,parent.from_case_id),(parent.to_store_id,parent.to_case_id)):
        with transfer.coordination_scope(db,sid,(parent.from_store_id,parent.to_store_id)):
            case=exc.flow.scoped_get(db,Case,cid);desired={}
            def add(key,title,role,actor=None):desired[prefix+key]=(title,role,actor)
            if row.status=='preparing':
                if not match and sid!=row.found_store_id:add('match','本人核对找到物资与原损失关联','inventory')
                if sid==custody(row,parent,history) and not quality:add('inspect','本人实际复验找到的物资','inventory')
                if quality and match:
                    if quality.passed and sid==row.found_store_id and sid!=parent.from_store_id:add('ship','实际将找回物资发回原店','inventory')
                    elif (not quality.passed or quality.store_id==parent.from_store_id) and sid==parent.from_store_id:add('plan','核对原损失可恢复成本与承担','finance')
            elif row.status=='transit' and sid==parent.from_store_id:add('receive','实际收到找回物资并复验','inventory')
            elif row.status=='review':
                reviewed=rows(db,GoodsReview,plan_id=plan.id)
                if not any(r.store_id==sid for r in reviewed):add('review_'+str(plan.id),'独立复核本版原物资找回处理','manager',_independent(db,row,parent,plan,sid,reviewed))
            elif row.status=='approved':
                if plan.restored_quantity_milli and sid==parent.from_store_id:add('restore','确认合格原物资入库','inventory')
                elif not plan.restored_quantity_milli:
                    if not any(f.kind=='dispose' for f in history) and sid==custody(row,parent,history):add('dispose','确认本店在手坏件实际处置','inventory')
                    elif any(f.kind=='dispose' for f in history) and sid==parent.from_store_id:add('finish_bad','核对坏件处置，保留原损失','finance')
            elif row.status=='financial':
                from .transfer_goods_recovery_finance import local_complete
                loss=original(db,parent,row.loss_id)
                if not local_complete(db,row,parent,loss,sid):add('finance','核对找到物资后的往来方原赔付','finance')
            from .transfer_goods_search_service import task_desires
            for key,(title,role,actor) in task_desires(db,row,parent,sid).items():add(key,title,role,actor)
            for task in rows(db,Task,case_id=case.id,status='open'):
                if task.key.startswith(prefix) and task.key not in desired:exc.flow.finish_task(db,case,task.key,user)
            for key,(title,role,actor) in desired.items():exc.flow.ensure_task(db,case,key,title,role,assignee=actor,due=row.due_date,reopen=True)


def describe(db,user,row,parent,loss,sid):
    case=exc._case(db,user,parent,sid);history=facts(db,row);line=exc._one(db,TransferLine,loss.line_id);plan=latest(db,row)
    quality=inspection(row,parent,history);match=next((f for f in history if f.kind=='match'),None)
    names={x.id:x.name for x in db.scalars(select(Store).where(Store.id.in_((parent.from_store_id,parent.to_store_id))))}
    result=dict(id=row.id,version=row.version,transfer_id=parent.id,transfer_number=parent.number,
        transfer_version=parent.version,case_id=case.id,case_version=case.version,loss_id=loss.id,exception_id=row.exception_id,
        status=row.status,status_label=LABELS[row.status],quantity_milli=row.quantity_milli,found_store_id=row.found_store_id,
        item_name=line.name,sku=line.sku,unit=line.unit,source_store_name=names[parent.from_store_id],destination_store_name=names[parent.to_store_id],
        found_store_name=names[row.found_store_id],custody_store_name=names.get(custody(row,parent,history)),due_date=row.due_date.isoformat(),
        reason=row.reason,actions=[],plans=[],facts=[dict(id=f.id,kind=f.kind,store_id=f.store_id,store_name=names[f.store_id],quantity_milli=f.quantity_milli,passed=f.passed,result=f.result,
            evidence_id=f.evidence_id if f.store_id==sid else None,business_date=f.business_date.isoformat()) for f in history])
    for p in rows(db,GoodsPlan,recovery_id=row.id):
        result['plans'].append(dict(id=p.id,revision=p.revision,restored_quantity_milli=p.restored_quantity_milli,
            reviews=[dict(store_name=names[r.store_id],decision=r.decision) for r in rows(db,GoodsReview,plan_id=p.id)]))
        if user.role in exc.flow.MANAGEMENT:result['plans'][-1].update(value_cents=p.value_cents,source_reverse_cents=p.source_reverse_cents,destination_reverse_cents=p.destination_reverse_cents,reason=p.reason)
    assigned={t.key for t in rows(db,Task,case_id=case.id,status='open') if t.assignee_id==user.id or user.role=='admin'}
    def offer(action,role,task=None):
        if user.role in role and (task is None or f'transfer_found_{row.id}_'+task in assigned):result['actions'].append(action)
    if row.status=='preparing':
        if sid!=row.found_store_id and not match:offer('match',exc.PHYSICAL,'match')
        if sid==custody(row,parent,history) and (not quality or quality.actor_id==user.id):offer('inspect',exc.PHYSICAL,None if quality else 'inspect')
        if quality and match:
            if quality.passed and sid==row.found_store_id and sid!=parent.from_store_id:offer('ship',exc.PHYSICAL,'ship')
            elif (not quality.passed or quality.store_id==parent.from_store_id) and sid==parent.from_store_id:offer('plan',exc.FINANCE,'plan')
    elif row.status=='transit' and sid==parent.from_store_id:offer('receive',exc.PHYSICAL,'receive')
    elif row.status=='review':
        reviews=rows(db,GoodsReview,plan_id=plan.id);blocked={f.actor_id for f in history}|{row.requested_by,plan.actor_id}|{r.actor_id for r in reviews}
        if user.id not in blocked and not any(r.store_id==sid for r in reviews):
            offer('approve',exc.MANAGER,'review_'+str(plan.id));offer('reject',exc.MANAGER,'review_'+str(plan.id))
    elif row.status=='approved':
        if plan.restored_quantity_milli and sid==parent.from_store_id:offer('restore',exc.PHYSICAL,'restore')
        elif not plan.restored_quantity_milli:
            if not any(f.kind=='dispose' for f in history) and sid==custody(row,parent,history):offer('dispose',exc.PHYSICAL,'dispose')
            elif any(f.kind=='dispose' for f in history) and sid==parent.from_store_id:offer('finish_bad',exc.FINANCE,'finish_bad')
    if row.status in {'preparing','review'} and not any(f.kind in {'ship','receive','dispose'} for f in history) and (user.id==row.requested_by or user.role in exc.MANAGER):offer('cancel',exc.PHYSICAL|exc.MANAGER)
    from .transfer_goods_search_service import append_view
    append_view(db,user,row,parent,sid,result,assigned)
    if user.role in exc.flow.MANAGEMENT:
        result['remaining_burden_cents']=local_burden(db,parent,loss,sid)
        from .transfer_goods_recovery_finance import describe as financial
        result['claims']=financial(db,user,row,parent,loss,sid)
    return result


def detail(db,user,key):
    with authority(db,user) as sid:
        row,parent,loss=_get(db,user,key,sid);return describe(db,user,row,parent,loss,sid)


def listing(db,user,transfer_id=None):
    with authority(db,user) as sid:
        query=select(GoodsRecovery).join(MaterialTransfer,MaterialTransfer.id==GoodsRecovery.transfer_id).where(or_(MaterialTransfer.from_store_id==sid,MaterialTransfer.to_store_id==sid))
        if transfer_id:query=query.where(GoodsRecovery.transfer_id==transfer_id)
        found=list(db.scalars(query.order_by(GoodsRecovery.id.desc()).limit(501)))
        if len(found)>500:raise HTTPException(413,'找回记录超过500条，请按原调拨查询，不能显示截断结果')
        if not found:return {'items':[]}
        parent_ids={row.transfer_id for row in found}
        parents={p.id:p for p in db.scalars(select(MaterialTransfer).where(MaterialTransfer.id.in_(parent_ids)))}
        exceptions={e.id:e for e in db.scalars(select(TransferException).where(TransferException.id.in_({r.exception_id for r in found})))}
        moves={m.id:m for m in db.scalars(select(TransferMovement).where(TransferMovement.id.in_({e.original_id for e in exceptions.values()})))}
        lines={line.id:line for line in db.scalars(select(TransferLine).where(TransferLine.id.in_({m.line_id for m in moves.values()})))}
        result=[]
        for row in found:
            parent=parents[row.transfer_id];line=lines[moves[exceptions[row.exception_id].original_id].line_id]
            result.append(dict(id=row.id,transfer_id=parent.id,transfer_number=parent.number,case_id=parent.from_case_id if sid==parent.from_store_id else parent.to_case_id,
                item_name=line.name,sku=line.sku,unit=line.unit,quantity_milli=row.quantity_milli,found_store_id=row.found_store_id,
                status=row.status,status_label=LABELS[row.status],due_date=row.due_date.isoformat()))
        return {'items':result}


def execute(db,user,request,action,payload,operation):
    with authority(db,user,exc.PHYSICAL|exc.FINANCE|exc.MANAGER) as sid:
        digest=hashlib.sha256(json.dumps([action,payload],sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()).hexdigest()
        try:
            old=db.scalar(select(GoodsReceipt).where(GoodsReceipt.request_key==request))
            if old:
                if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'请求编号已用于其他找回操作')
                row,parent,loss=_get(db,user,old.recovery_id,sid);return describe(db,user,row,parent,loss,sid)
            row,parent,loss=operation(sid);row.updated_at=utcnow();db.flush();sync(db,user,row,parent)
            db.add(GoodsReceipt(request_key=request,actor_id=user.id,digest=digest,recovery_id=row.id));db.flush()
            result=describe(db,user,row,parent,loss,sid);db.commit();return result
        except (IntegrityError,OperationalError,StaleDataError):
            db.rollback();raise HTTPException(409,'原调拨、找到数量或原资金已变化；请刷新核对并保留原请求编号')
        except Exception:db.rollback();raise


def create(db,user,request,transfer_id,loss_id,version,case_version,quantity_milli,result,evidence_id,due_date,previous_recovery_id=None):
    def run(sid):
        if user.role not in exc.PHYSICAL:raise HTTPException(403,'找到物资由本店库管核对')
        parent=transfer.get_transfer(db,transfer_id,sid);parent,case=exc._lock(db,user,parent,sid,version,case_version)
        loss=original(db,parent,loss_id);original_exception=exc._one(db,TransferException,loss.exception_id)
        if original_exception.status!='posted':raise HTTPException(409,'须关联已经确认的原损失')
        if exc._active(db,parent) or db.scalar(select(GoodsRecovery.id).where(GoodsRecovery.active_transfer_id==parent.id)):
            raise HTTPException(409,'原调拨尚有未结差异或找到物资待处理')
        portion(db,parent,loss,quantity_milli,False);exc._proof(db,user,case,evidence_id)
        from .transfer_goods_search_service import validate_reappearance,attach_reappearance
        prior_search=validate_reappearance(db,parent,loss,previous_recovery_id,quantity_milli)
        row=GoodsRecovery(transfer_id=parent.id,active_transfer_id=parent.id,loss_id=loss.id,exception_id=loss.exception_id,found_store_id=sid,
            requested_by=user.id,quantity_milli=quantity_milli,reason=result,due_date=due_date)
        db.add(row);db.flush();_fact(db,user,row,case,'found',dict(result=result,evidence_id=evidence_id))
        attach_reappearance(db,user,row,case,prior_search,evidence_id)
        return row,parent,loss
    payload=dict(transfer_id=transfer_id,loss_id=loss_id,version=version,case_version=case_version,quantity_milli=quantity_milli,result=result,evidence_id=evidence_id,due_date=due_date)
    if previous_recovery_id is not None:payload['previous_recovery_id']=previous_recovery_id
    return execute(db,user,request,'create',payload,run)


def _post(db,user,row,parent,loss,case,plan,v):
    expected=portion(db,parent,loss,row.quantity_milli,bool(plan.restored_quantity_milli))
    if any(getattr(plan,k)!=value for k,value in expected.items() if k!='found_quantity_milli'):raise HTTPException(409,'原批次可恢复成本已变化')
    stock=None
    if plan.restored_quantity_milli:
        line=exc._one(db,TransferLine,loss.line_id)
        item=db.scalar(select(Item).where(Item.id==line.source_item_id).with_for_update())
        if not item or item.unit!=line.unit:raise HTTPException(409,'原店原物资档案不能接收，不能改用其他物资替代')
        dispatch=next(m for m in transfer.movements_for(db,parent) if m.line_id==line.id and m.kind=='dispatch')
        stock=transfer.posting(db,user,case,item,plan.restored_quantity_milli,plan.value_cents,'transfer_found',dispatch.stock_move_id)
    posting=GoodsPosting(recovery_id=row.id,loss_id=loss.id,plan_id=plan.id,**expected,stock_move_id=stock.id if stock else None,
        evidence_id=v['evidence_id'],actor_id=user.id,business_date=today())
    db.add(posting);db.flush()
    if plan.destination_reverse_cents:
        for sid,other,amount in ((parent.from_store_id,parent.to_store_id,-plan.destination_reverse_cents),(parent.to_store_id,parent.from_store_id,plan.destination_reverse_cents)):
            with transfer.coordination_scope(db,sid,(parent.from_store_id,parent.to_store_id)):
                old=db.scalar(select(TransferLossSettlement).where(TransferLossSettlement.posting_id==loss.id))
                if not old:raise HTTPException(409,'原损失承担配对缺失，不能生成猜测的冲回')
                db.add(GoodsSettlement(transfer_id=parent.id,recovery_id=row.id,posting_id=posting.id,original_id=old.id,counterparty_store_id=other,amount_cents=amount,business_date=today()))
    row.status='financial';db.flush()
    from .transfer_goods_recovery_finance import maybe_complete
    maybe_complete(db,user,row,parent,loss)


def command(db,user,key,request,version,transfer_version,case_version,action,v):
    def run(sid):
        row,parent,loss=_get(db,user,key,sid);parent,case=exc._lock(db,user,parent,sid,transfer_version,case_version)
        if row.version!=version:raise HTTPException(409,'本次找到物资已经变化，请刷新核对')
        if row.status in {'closed','cancelled','unlocated'}:raise HTTPException(409,'本次找回已经结清，不可覆盖历史')
        from .transfer_goods_recovery_finance import ACTIONS,act
        if action in ACTIONS:
            act(db,user,row,parent,loss,case,action,v);return row,parent,loss
        from .transfer_goods_search_service import ACTIONS as SEARCH_ACTIONS,apply as apply_search
        if action in SEARCH_ACTIONS:
            apply_search(db,user,row,parent,case,action,v)
            exc.flow.log_event(db,user,case,'transfer_found_search','追加原退运查找的本人事实或独立复核',detail={'recovery_id':row.id,'action':action,'stage':row.status})
            return row,parent,loss
        physical={'match','inspect','ship','receive','dispose','restore'}
        roles=exc.PHYSICAL if action in physical else exc.FINANCE if action in {'plan','finish_bad'} else exc.MANAGER if action in {'approve','reject'} else exc.PHYSICAL|exc.MANAGER
        if user.role not in roles:raise HTTPException(403,'当前门店岗位不能办理本找回动作')
        history=facts(db,row);plan=latest(db,row);quality=inspection(row,parent,history)
        match=next((f for f in history if f.kind=='match'),None)
        if action in {'match','inspect'}:
            if row.status!='preparing':raise HTTPException(409,'当前不能追加未送审实物核对')
            if action=='match' and (sid==row.found_store_id or match or user.id==row.requested_by):raise HTTPException(403,'原损失关联由另一门店另一位库管核对')
            if action=='inspect' and sid!=custody(row,parent,history):raise HTTPException(403,'只能复验本店实际保管的物资')
            if action=='match' or not quality:exc._assert_task(db,user,case,f'transfer_found_{row.id}_'+action)
            elif quality.actor_id!=user.id:raise HTTPException(403,'追加本人复验由原复验经办人办理，不能覆盖其他人的检查')
            _fact(db,user,row,case,action,v)
        elif action=='ship':
            if row.status!='preparing' or sid!=row.found_store_id or sid==parent.from_store_id or not match or not quality or not quality.passed:
                raise HTTPException(409,'双方核对且本店复验后，由找到物资的调入店实际发回')
            exc._assert_task(db,user,case,f'transfer_found_{row.id}_ship')
            _fact(db,user,row,case,'ship',v);row.status='transit'
        elif action=='receive':
            if row.status!='transit' or sid!=parent.from_store_id:raise HTTPException(409,'原店实际收到整份找到物资后分别复验')
            exc._assert_task(db,user,case,f'transfer_found_{row.id}_receive')
            fact=_fact(db,user,row,case,'receive',v)
            from .transfer_goods_search_service import actual_arrival
            actual_arrival(db,user,row,parent,case,fact)
            row.status='preparing'
        elif action=='plan':
            if row.status!='preparing' or sid!=parent.from_store_id or not match or not quality or quality.passed and quality.store_id!=parent.from_store_id:
                raise HTTPException(409,'双方关联核对、当前保管复验完成后，由原店财务核对恢复；合格件须实际回到原店')
            exc._assert_task(db,user,case,f'transfer_found_{row.id}_plan')
            exc._proof(db,user,case,v['evidence_id'],True);values=portion(db,parent,loss,row.quantity_milli,quality.passed)
            values.pop('found_quantity_milli');plan=GoodsPlan(recovery_id=row.id,revision=len(rows(db,GoodsPlan,recovery_id=row.id))+1,
                match_id=match.id,inspection_id=quality.id,**values,actor_id=user.id,evidence_id=v['evidence_id'],reason=v['reason'])
            db.add(plan);db.flush()
            for party in (parent.from_store_id,parent.to_store_id):_independent(db,row,parent,plan,party)
            row.status='review'
        elif action in {'approve','reject'}:
            if row.status!='review' or v['plan_id']!=plan.id:raise HTTPException(409,'只能复核当前找回方案')
            exc._proof(db,user,case,v['evidence_id'],True);reviewed=rows(db,GoodsReview,plan_id=plan.id)
            blocked={f.actor_id for f in history}|{plan.actor_id,row.requested_by}|{r.actor_id for r in reviewed}
            if user.id in blocked or any(r.store_id==sid for r in reviewed):raise HTTPException(403,'两店主管必须独立于本次事实、方案及彼此，管理员无例外')
            exc._assert_task(db,user,case,f'transfer_found_{row.id}_review_{plan.id}')
            db.add(GoodsReview(plan_id=plan.id,store_id=sid,decision='approve' if action=='approve' else 'reject',actor_id=user.id,evidence_id=v['evidence_id'],reason=v['reason']))
            row.status='preparing' if action=='reject' else 'approved' if len(reviewed)==1 else 'review'
        elif action=='dispose':
            if row.status!='approved' or plan.restored_quantity_milli or sid!=custody(row,parent,history) or any(f.kind=='dispose' for f in history):raise HTTPException(409,'只有批准后的在手坏件由实际保管店处置')
            exc._assert_task(db,user,case,f'transfer_found_{row.id}_dispose')
            _fact(db,user,row,case,'dispose',v)
        elif action in {'restore','finish_bad'}:
            if row.status!='approved' or sid!=parent.from_store_id:raise HTTPException(409,'当前方案须批准后在原调出店完成')
            if action=='restore' and not plan.restored_quantity_milli or action=='finish_bad' and (plan.restored_quantity_milli or not any(f.kind=='dispose' for f in history)):
                raise HTTPException(409,'合格原物资与已经实际处置坏件不能混同')
            exc._assert_task(db,user,case,f'transfer_found_{row.id}_'+action)
            exc._proof(db,user,case,v['evidence_id'],action=='finish_bad');_post(db,user,row,parent,loss,case,plan,v)
        elif action=='cancel':
            if row.status not in {'preparing','review'} or any(f.kind in {'ship','receive','dispose'} for f in history):raise HTTPException(409,'实际退运、接收、处置后不能撤销事实；应完成原找回处理')
            if user.id!=row.requested_by and user.role not in exc.MANAGER:raise HTTPException(403,'仅原申报人或本店主管可撤回误关联')
            _fact(db,user,row,case,'cancel',v);row.status='cancelled';row.active_transfer_id=None
        else:raise HTTPException(404,'找回动作不存在')
        exc.flow.log_event(db,user,case,'transfer_found_progress','找回原物资事实已追加',detail={'recovery_id':row.id,'stage':row.status})
        return row,parent,loss
    return execute(db,user,request,str(key)+':'+action,dict(version=version,transfer_version=transfer_version,case_version=case_version,values=v),run)
