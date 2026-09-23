"""Version-three transport exceptions on the existing two transfer cases.

One active investigation serializes the entire transfer. Own-store employees
attest physical facts; only paired tasks and internal obligations cross scope.
"""
from contextlib import contextmanager
from datetime import date
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,or_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .tenancy import single_store,role_for_store
from .flow_models import Case,Task
from . import flow_engine as flow
from . import transfer_service as transfer
from .transfer_models import MaterialTransfer,TransferMovement,TransferLine
from .transfer_exception_models import (TransferException,TransferExceptionObservation,TransferExceptionPlan,
    TransferExceptionReview,TransferExceptionDisposal,TransferLossPosting,TransferLossSettlement,
    TransferExceptionCancellation,TransferExceptionReceipt)
from .transfer_exception_math import bucket_position,original_portion

READ={'admin','manager','inventory','finance','auditor'}
PHYSICAL={'admin','inventory'}
FINANCE={'admin','finance'}
MANAGER={'admin','manager'}
STAGES={'dispatch':'outbound','reject':'rejected','return_ship':'returning'}
LABELS={'investigating':'双方实物核对中','review':'等待两店独立复核','approved':'已批准待实际处置或损失确认',
        'disposed':'已实际处置待确认损失','posted':'损失已确认','cancelled':'未生效差异已取消'}


@contextmanager
def authority(db,user,roles=READ):
    with transfer.authority(db,user,roles) as sid:
        old=db.info.get('_transfer_exception_authority');db.info['_transfer_exception_authority']=(sid,user.id)
        try:yield sid
        finally:
            if old is None:db.info.pop('_transfer_exception_authority',None)
            else:db.info['_transfer_exception_authority']=old


def _rows(db,model,**where):
    stmt=select(model)
    for key,value in where.items():stmt=stmt.where(getattr(model,key)==value)
    rows=list(db.scalars(stmt.order_by(model.id).limit(25001)))
    if len(rows)>25000:raise HTTPException(413,'调拨差异来源超过当前上限，不能返回截断结果')
    return rows


def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if row is None:raise HTTPException(404,'本次调拨差异记录不存在')
    return row


def _case(db,user,parent,sid):
    row=flow.get_case(db,user,parent.from_case_id if sid==parent.from_store_id else parent.to_case_id)
    if row.kind!='material_transfer' or row.flow_version!=3:
        raise HTTPException(409,'运输差异只用于新建第3版调拨；旧第2版不自动升级')
    return row


def _lock(db,user,parent,sid,version,case_version):
    row=db.scalar(select(MaterialTransfer).where(MaterialTransfer.id==parent.id).with_for_update())
    case=_case(db,user,row,sid)
    if row.version!=version or case.version!=case_version:raise HTTPException(409,'调拨或本店原单已经变化，请刷新核对')
    # Shared lock/touch must precede all bucket reads and is used by ordinary v3 commands too.
    row.updated_at=utcnow();case.updated_at=utcnow();db.flush()
    return row,case


def _proof(db,user,case,key,financial=False):
    asset=transfer.evidence(db,user,case,key)
    if asset.generated:raise HTTPException(409,'自动生成的草稿不能代替本店实际观察、处置或财务凭据')
    if financial and asset.category not in {'receipt','procurement_contract'}:
        raise HTTPException(422,'成本承担与损失确认需本店财务凭据或明确协议')
    if not financial and asset.category not in {'evidence','inspection','authorization'}:
        raise HTTPException(422,'实物核对与处置需本店业务、检测或授权凭据')
    return asset


def _get(db,user,key,sid):
    row=db.scalar(select(TransferException).join(MaterialTransfer,MaterialTransfer.id==TransferException.transfer_id).where(
        TransferException.id==key,or_(MaterialTransfer.from_store_id==sid,MaterialTransfer.to_store_id==sid)))
    if row is None:raise HTTPException(404,'本店本次调拨差异记录不存在')
    parent=transfer.get_transfer(db,row.transfer_id,sid)
    _case(db,user,parent,sid)
    return row,parent


def _active(db,parent):
    return db.scalar(select(TransferException).where(TransferException.active_transfer_id==parent.id))


def guard_transfer_command(db,user,parent,action):
    """Root calls after locking/touching the shared parent, on v3 only."""
    sid=single_store(db)
    case=flow.scoped_get(db,Case,parent.from_case_id if sid==parent.from_store_id else parent.to_case_id)
    if not case or case.flow_version!=3:return
    from .transfer_goods_recovery_service import guard_original_action
    guard_original_action(db,user,parent,action)
    active=_active(db,parent)
    if active:raise HTTPException(409,f'调拨差异 {active.id} 尚未结清，本批收发暂停；请先完成或有据取消差异')


def handled_for(db,parent,original):
    if original.transfer_id!=parent.id or original.kind not in STAGES:raise HTTPException(409,'不是本次调拨的可核对原批次')
    kinds={'dispatch':{'accept','reject'},'reject':{'return_ship'},'return_ship':{'return_receive'}}[original.kind]
    normal=[(m.quantity_milli,m.value_cents) for m in transfer.movements_for(db,parent)
            if m.original_id==original.id and m.kind in kinds]
    lost=[(e.quantity_milli,e.value_cents) for e in _rows(db,TransferException,transfer_id=parent.id,original_id=original.id,status='posted')]
    return normal+lost


def bucket_remaining(db,parent,original):
    try:return bucket_position(original.quantity_milli,original.value_cents,handled_for(db,parent,original))
    except ValueError as exc:raise HTTPException(409,str(exc))


def portion(db,parent,original,quantity_milli):
    try:return original_portion(original.quantity_milli,original.value_cents,handled_for(db,parent,original),quantity_milli)
    except ValueError as exc:raise HTTPException(409,str(exc))


def loss_totals(db,parent):
    totals={}
    origins={m.id:m for m in transfer.movements_for(db,parent)}
    for e in _rows(db,TransferException,transfer_id=parent.id,status='posted'):
        original=origins[e.original_id];v=totals.setdefault(original.line_id,{'quantity_milli':0,'value_cents':0,'outbound_milli':0,'rejected_milli':0,'returning_milli':0})
        v['quantity_milli']+=e.quantity_milli;v['value_cents']+=e.value_cents;v[e.stage+'_milli']+=e.quantity_milli
    return totals


def _expected_observation(row,parent,sid):
    if row.stage=='returning':return 'return_dispatch_verified' if sid==parent.to_store_id else 'held_damaged' if row.finding=='damaged' else 'missing'
    return 'dispatch_verified' if sid==parent.from_store_id else 'held_damaged' if row.finding=='damaged' else 'missing'


def _custodian(row,parent):return parent.from_store_id if row.stage=='returning' else parent.to_store_id
def _plan(db,row):
    plans=_rows(db,TransferExceptionPlan,exception_id=row.id)
    if not plans:raise HTTPException(409,'尚未形成明确成本承担方案')
    return plans[-1]


def _observations(db,row):
    return {o.store_id:o for o in _rows(db,TransferExceptionObservation,exception_id=row.id)}


def _reviewers(db,row,parent,plan):
    observations=[_one(db,TransferExceptionObservation,plan.source_observation_id),_one(db,TransferExceptionObservation,plan.destination_observation_id)]
    excluded={row.requested_by,plan.actor_id}|{o.actor_id for o in observations}
    reviewed={r.store_id:r for r in _rows(db,TransferExceptionReview,plan_id=plan.id)}
    selected={sid:r.actor_id for sid,r in reviewed.items() if r.decision=='approve'}
    for sid in (parent.from_store_id,parent.to_store_id):
        if sid in selected:continue
        candidates=[u.id for u in flow.eligible_users(db,'manager',sid) if u.id not in excluded|set(selected.values())]
        if not candidates:raise HTTPException(409,'两店需要配置两名独立主管，且不能是差异申请、实物观察或方案经办人')
        selected[sid]=candidates[0]
    return selected


def sync_exception_tasks(db,user,row,parent):
    observations=_observations(db,row);plan=None;reviewers={};reviews={}
    if row.status in {'review','approved','disposed'}:
        plan=_plan(db,row);reviews={r.store_id:r for r in _rows(db,TransferExceptionReview,plan_id=plan.id)}
        if row.status=='review':reviewers=_reviewers(db,row,parent,plan)
    for sid,cid in ((parent.from_store_id,parent.from_case_id),(parent.to_store_id,parent.to_case_id)):
        with transfer.coordination_scope(db,sid,(parent.from_store_id,parent.to_store_id)):
            case=flow.scoped_get(db,Case,cid);case.updated_at=utcnow();desired={};prefix=f'transfer_exception_{row.id}_'
            if row.status=='investigating':
                if sid not in observations:desired[prefix+'observe']=('本人核对本店发运、短缺或在手坏件','inventory',None)
                elif len(observations)==2 and sid==parent.from_store_id:desired[prefix+'plan']=('拟定明确在途损失及双方承担','finance',None)
            elif row.status=='review' and sid not in reviews:
                desired[prefix+'review_'+str(plan.id)]=('独立复核本版实物与损失承担','manager',reviewers[sid])
            elif row.status=='approved':
                if row.finding=='damaged' and sid==_custodian(row,parent):desired[prefix+'dispose']=('实际处置本店在手不可用坏件','inventory',None)
                elif row.finding=='missing' and sid==parent.from_store_id:desired[prefix+'post']=('依据双方实物与批准方案确认在途损失','finance',None)
            elif row.status=='disposed' and sid==parent.from_store_id:desired[prefix+'post']=('依据真实处置与双方批准确认损失','finance',None)
            for task in list(db.scalars(select(Task).where(Task.case_id==cid,Task.status=='open'))):
                if task.key.startswith(prefix) and task.key not in desired:flow.finish_task(db,case,task.key,user)
            for key,(title,role,assignee) in desired.items():
                task=flow.ensure_task(db,case,key,title,role,assignee=assignee,due=row.due_date,reopen=True)
                if assignee is not None and task.assignee_id!=assignee:
                    # Do not silently change an existing assignment. A reviewed action
                    # must wait for the supervisor's explicit reassignment.
                    excluded={row.requested_by,plan.actor_id}|{_one(db,TransferExceptionObservation,key).actor_id for key in (plan.source_observation_id,plan.destination_observation_id)}
                    if task.assignee_id in excluded:
                        raise HTTPException(409,'当前复核待办负责人不独立，请明确转交后再办理')
            flow.log_event(db,user,case,'transfer_exception_progress','调拨差异：'+LABELS[row.status],detail={'exception_id':row.id,'status':row.status})


def _assert_task(db,user,case,key):transfer.assert_task(db,user,case,key)


def describe(db,user,row,parent,sid):
    case=_case(db,user,parent,sid);money=user.role in flow.MANAGEMENT
    original=_one(db,TransferMovement,row.original_id);line=_one(db,TransferLine,original.line_id)
    data={'id':row.id,'transfer_id':parent.id,'transfer_number':parent.number,'version':row.version,'transfer_version':parent.version,
          'case_id':case.id,'case_version':case.version,'stage':row.stage,'finding':row.finding,'original_id':row.original_id,
          'quantity_milli':row.quantity_milli,'status':row.status,'status_label':LABELS[row.status],'reason':row.reason,
          'due_date':row.due_date.isoformat(),'side':'source' if sid==parent.from_store_id else 'destination',
          'paused':row.active_transfer_id is not None,'observations':[],'plans':[],'disposals':[],'actions':[]}
    data.update(item_name=line.name,item_sku=line.sku,unit=line.unit)
    if money:data['value_cents']=row.value_cents
    for o in _rows(db,TransferExceptionObservation,exception_id=row.id):
        item={k:getattr(o,k) for k in ('id','store_id','observation','quantity_milli','result','actor_id')}
        item['business_date']=o.business_date.isoformat()
        if o.store_id==sid:item['evidence_id']=o.evidence_id
        data['observations'].append(item)
    for p in _rows(db,TransferExceptionPlan,exception_id=row.id):
        item={'id':p.id,'revision':p.revision,'reviews':[]}
        if money:item.update(source_bearer_cents=p.source_bearer_cents,destination_bearer_cents=p.destination_bearer_cents,reason=p.reason)
        if money and sid==parent.from_store_id:item['evidence_id']=p.evidence_id
        for r in _rows(db,TransferExceptionReview,plan_id=p.id):
            info={'id':r.id,'store_id':r.store_id,'decision':r.decision,'actor_id':r.actor_id}
            if money:info['reason']=r.reason
            if money and r.store_id==sid:info['evidence_id']=r.evidence_id
            item['reviews'].append(info)
        data['plans'].append(item)
    for d in _rows(db,TransferExceptionDisposal,exception_id=row.id):
        item={'id':d.id,'store_id':d.store_id,'quantity_milli':d.quantity_milli,'business_date':d.business_date.isoformat(),'method':d.method}
        if d.store_id==sid:item['evidence_id']=d.evidence_id
        data['disposals'].append(item)
    role=role_for_store(db,user,sid)
    if row.status=='investigating':
        if role in PHYSICAL:data['actions'].append('observe')
        if sid==parent.from_store_id and role in FINANCE and len(_observations(db,row))==2:data['actions'].append('plan')
    if row.status=='review' and role in MANAGER:data['actions']+=['approve','reject_plan']
    if row.status=='approved' and row.finding=='damaged' and sid==_custodian(row,parent) and role in PHYSICAL:data['actions'].append('dispose')
    if (row.status=='disposed' or row.status=='approved' and row.finding=='missing') and sid==parent.from_store_id and role in FINANCE:data['actions'].append('post_loss')
    if row.status in {'investigating','review','approved'} and (user.id==row.requested_by or role in MANAGER):data['actions'].append('cancel')
    from . import transfer_exception_recovery as recovery
    data['recoveries']=recovery.describe(db,user,row,parent,sid)
    if row.status=='posted' and money:
        data['recovery_cap_cents']=recovery.burden(db,row,parent,sid)
        if role in FINANCE:data['actions'].append('recovery_create')
    from .transfer_goods_recovery_models import GoodsRecovery
    from .transfer_goods_recovery_service import original_authority
    with original_authority(db):
        found=list(db.scalars(select(GoodsRecovery).where(GoodsRecovery.transfer_id==parent.id).order_by(GoodsRecovery.id)))
        active=next((g for g in found if g.active_transfer_id is not None),None)
        data['active_goods_recovery_id']=active.id if active else None
        data['goods_recovery_ids']=[g.id for g in found if g.exception_id==row.id]
        if active:
            data['actions']=[]
            for claim in data['recoveries']:claim['actions']=[]
    return data


def detail(db,user,key):
    with authority(db,user) as sid:
        row,parent=_get(db,user,key,sid);return describe(db,user,row,parent,sid)


def list_exceptions(db,user,transfer_id=None):
    with authority(db,user) as sid:
        stmt=select(TransferException).join(MaterialTransfer,MaterialTransfer.id==TransferException.transfer_id).where(or_(MaterialTransfer.from_store_id==sid,MaterialTransfer.to_store_id==sid))
        if transfer_id is not None:transfer.get_transfer(db,transfer_id,sid);stmt=stmt.where(TransferException.transfer_id==transfer_id)
        rows=list(db.scalars(stmt.order_by(TransferException.id.desc()).limit(501)))
        if len(rows)>500:raise HTTPException(413,'差异记录超过500条，请按原调拨查询')
        return {'items':[describe(db,user,r,transfer.get_transfer(db,r.transfer_id,sid),sid) for r in rows]}


def available_origins(db,user,transfer_id):
    with authority(db,user) as sid:
        parent=transfer.get_transfer(db,transfer_id,sid);case=_case(db,user,parent,sid);active=_active(db,parent)
        result=dict(transfer_id=parent.id,number=parent.number,version=parent.version,case_id=case.id,case_version=case.version,
            status=parent.status,active_exception_id=active.id if active else None,origins=[])
        if parent.status!='transit':return result
        line_map={l.id:l for l in transfer.lines_for(db,parent)}
        for m in transfer.movements_for(db,parent):
            if m.kind not in STAGES:continue
            p=bucket_remaining(db,parent,m)
            if p['remaining_milli']<=0:continue
            line=line_map[m.line_id]
            item=dict(id=m.id,stage=STAGES[m.kind],name=line.name,sku=line.sku,unit=line.unit,
                remaining_milli=p['remaining_milli'],findings=['missing'] if m.kind=='dispatch' else ['missing','damaged'])
            if user.role in flow.MANAGEMENT:item['remaining_cents']=p['remaining_cents']
            result['origins'].append(item)
        return result


def recovery_catalog(db,user):
    from .master_models import Supplier,Insurer
    from .flow_models import Account
    with authority(db,user,flow.MANAGEMENT):
        result={'parties':[],'accounts':[]}
        for kind,model in (('carrier',Supplier),('insurer',Insurer)):
            for p in _rows(db,model,active=True):result['parties'].append(dict(id=p.id,name=p.name,code=p.code,kind=kind))
        result['accounts']=[dict(id=a.id,name=a.name) for a in _rows(db,Account,active=True)]
        return result


def _execute(db,user,key,action,payload,operation):
    with authority(db,user,PHYSICAL|MANAGER|FINANCE) as sid:
        digest=hashlib.sha256(json.dumps([action,payload],sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
        try:
            old=db.scalar(select(TransferExceptionReceipt).where(TransferExceptionReceipt.request_key==key))
            if old:
                if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'请求编号已用于其他内容或其他经办人')
                row,parent=_get(db,user,old.result['id'],sid);return describe(db,user,row,parent,sid)
            row,parent=operation(sid);db.flush()
            db.add(TransferExceptionReceipt(request_key=key,actor_id=user.id,digest=digest,result={'id':row.id}));db.flush()
            result=describe(db,user,row,parent,sid);db.commit();return result
        except (IntegrityError,OperationalError,StaleDataError):
            db.rollback();raise HTTPException(409,'调拨、差异或岗位待办已变化，请刷新核对；重试保留原请求编号')
        except Exception:db.rollback();raise


def create(db,user,request_id,transfer_id,version,case_version,original_id,quantity_milli,finding,result,evidence_id,due_date):
    if user.role not in PHYSICAL:raise HTTPException(403,'差异由本店实际库管核对发起')
    payload=locals().copy();payload={k:v for k,v in payload.items() if k not in {'db','user','request_id'}}
    def run(sid):
        parent=transfer.get_transfer(db,transfer_id,sid);parent,case=_lock(db,user,parent,sid,version,case_version)
        from .transfer_goods_recovery_service import guard_original_action
        guard_original_action(db,user,parent,'exception_create')
        if parent.status!='transit':raise HTTPException(409,'只有尚有在途实物的调拨可以发起运输差异')
        if _active(db,parent):raise HTTPException(409,'本调拨已有未结差异，请先完成或有据取消')
        original=next((m for m in transfer.movements_for(db,parent) if m.id==original_id and m.kind in STAGES),None)
        if not original:raise HTTPException(404,'不是本调拨可核对的原发出、拒收或退回发运批次')
        stage=STAGES[original.kind]
        if finding=='damaged' and stage=='outbound':raise HTTPException(409,'已到达坏件请先由调入方实际拒收，再核对拒收待退批次')
        _proof(db,user,case,evidence_id)
        value=portion(db,parent,original,quantity_milli)
        row=TransferException(transfer_id=parent.id,active_transfer_id=parent.id,original_id=original.id,stage=stage,finding=finding,
            quantity_milli=quantity_milli,value_cents=value,request_store_id=sid,requested_by=user.id,reason=result,due_date=due_date)
        db.add(row);db.flush()
        db.add(TransferExceptionObservation(exception_id=row.id,store_id=sid,observation=_expected_observation(row,parent,sid),quantity_milli=quantity_milli,
            result=result,evidence_id=evidence_id,actor_id=user.id,business_date=today()))
        db.flush();sync_exception_tasks(db,user,row,parent);return row,parent
    return _execute(db,user,request_id,'create',payload,run)


def command(db,user,key,request_id,version,transfer_version,case_version,action,v):
    def run(sid):
        row,parent=_get(db,user,key,sid);parent,case=_lock(db,user,parent,sid,transfer_version,case_version)
        from .transfer_goods_recovery_service import guard_original_action
        guard_original_action(db,user,parent,action)
        if row.version!=version:raise HTTPException(409,'差异已经有新观察或处理，请刷新核对')
        from . import transfer_exception_recovery as recovery
        if action in recovery.ACTIONS:
            recovery.act(db,user,row,parent,case,sid,action,v)
            row.updated_at=utcnow();db.flush();return row,parent
        if row.status in {'posted','cancelled'}:raise HTTPException(409,'已结束差异不可再次办理或覆盖')
        roles={'observe':PHYSICAL,'plan':FINANCE,'approve':MANAGER,'reject_plan':MANAGER,'dispose':PHYSICAL,'post_loss':FINANCE,'cancel':PHYSICAL|MANAGER|FINANCE}
        if action not in roles:raise HTTPException(404,'调拨差异动作不存在')
        if role_for_store(db,user,sid) not in roles[action]:raise HTTPException(403,'当前门店岗位不能办理本动作')
        prefix=f'transfer_exception_{row.id}_';financial=action in {'plan','approve','reject_plan','post_loss'}
        _proof(db,user,case,v['evidence_id'],financial)
        if action=='observe':
            if row.status!='investigating':raise HTTPException(409,'当前版本已送审，须先退回核对后才能追加观察')
            observations=_observations(db,row)
            if any(o.actor_id==user.id for store,o in observations.items() if store!=sid):raise HTTPException(403,'双方实际核对须由不同经办人分别确认')
            if sid not in observations:_assert_task(db,user,case,prefix+'observe')
            db.add(TransferExceptionObservation(exception_id=row.id,store_id=sid,observation=_expected_observation(row,parent,sid),quantity_milli=row.quantity_milli,
                result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id,business_date=today()))
        elif action=='plan':
            if sid!=parent.from_store_id or row.status!='investigating':raise HTTPException(409,'双方实物核对后由原调出店财务拟定承担')
            _assert_task(db,user,case,prefix+'plan');observations=_observations(db,row)
            if set(observations)!={parent.from_store_id,parent.to_store_id}:raise HTTPException(409,'双方尚未分别提交实际核对')
            if observations[parent.from_store_id].actor_id==observations[parent.to_store_id].actor_id:raise HTTPException(409,'双方观察经办人不能相同')
            if v['source_bearer_cents']+v['destination_bearer_cents']!=row.value_cents:raise HTTPException(422,'两店承担必须恰好等于本批原成本，不含假定赔款')
            plan=TransferExceptionPlan(exception_id=row.id,revision=len(_rows(db,TransferExceptionPlan,exception_id=row.id))+1,
                source_observation_id=observations[parent.from_store_id].id,destination_observation_id=observations[parent.to_store_id].id,
                source_bearer_cents=v['source_bearer_cents'],destination_bearer_cents=v['destination_bearer_cents'],reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id)
            db.add(plan);db.flush();_reviewers(db,row,parent,plan);row.status='review'
        elif action in {'approve','reject_plan'}:
            if row.status!='review':raise HTTPException(409,'没有等待本店独立复核的当前方案')
            plan=_plan(db,row)
            if v['plan_id']!=plan.id:raise HTTPException(409,'请选择当前承担方案，旧版不得复核')
            _assert_task(db,user,case,prefix+'review_'+str(plan.id))
            observations=[_one(db,TransferExceptionObservation,i) for i in (plan.source_observation_id,plan.destination_observation_id)]
            reviews=_rows(db,TransferExceptionReview,plan_id=plan.id)
            if user.id in {row.requested_by,plan.actor_id}|{o.actor_id for o in observations}|{r.actor_id for r in reviews}:
                raise HTTPException(403,'两位主管须相互独立，且不得复核本人申请、观察或承担方案；管理员也不例外')
            if any(r.store_id==sid for r in reviews):raise HTTPException(409,'本店已复核本版方案')
            db.add(TransferExceptionReview(plan_id=plan.id,store_id=sid,decision='approve' if action=='approve' else 'reject',reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id));db.flush()
            if action=='reject_plan':row.status='investigating'
            elif len(reviews)==1:row.status='approved'
        elif action=='dispose':
            if row.status!='approved' or row.finding!='damaged' or sid!=_custodian(row,parent):raise HTTPException(409,'仅已批准的在手坏件由实际保管店确认处置')
            _assert_task(db,user,case,prefix+'dispose');plan=_plan(db,row)
            db.add(TransferExceptionDisposal(exception_id=row.id,plan_id=plan.id,store_id=sid,quantity_milli=row.quantity_milli,method=v['result'],evidence_id=v['evidence_id'],actor_id=user.id,business_date=today()))
            row.status='disposed'
        elif action=='post_loss':
            if sid!=parent.from_store_id or not (row.status=='disposed' or row.status=='approved' and row.finding=='missing'):
                raise HTTPException(409,'双方批准且坏件实际处置后，由调出店财务确认原在途损失')
            _assert_task(db,user,case,prefix+'post');plan=_plan(db,row);original=_one(db,TransferMovement,row.original_id)
            if portion(db,parent,original,row.quantity_milli)!=row.value_cents:raise HTTPException(409,'原批次已变化，不能按旧差异成本确认')
            loss=TransferLossPosting(exception_id=row.id,transfer_id=parent.id,line_id=original.line_id,original_id=original.id,plan_id=plan.id,
                quantity_milli=row.quantity_milli,value_cents=row.value_cents,source_bearer_cents=plan.source_bearer_cents,destination_bearer_cents=plan.destination_bearer_cents,
                evidence_id=v['evidence_id'],actor_id=user.id,business_date=today())
            db.add(loss);db.flush()
            if plan.destination_bearer_cents:
                for party,other,amount in ((parent.from_store_id,parent.to_store_id,plan.destination_bearer_cents),(parent.to_store_id,parent.from_store_id,-plan.destination_bearer_cents)):
                    with transfer.coordination_scope(db,party,(parent.from_store_id,parent.to_store_id)):
                        db.add(TransferLossSettlement(transfer_id=parent.id,posting_id=loss.id,exception_id=row.id,counterparty_store_id=other,amount_cents=amount,business_date=loss.business_date))
            row.status='posted';row.active_transfer_id=None;db.flush()
            posted=loss_totals(db,parent);moves=transfer.movements_for(db,parent);complete=True
            for line in transfer.lines_for(db,parent):
                physical=[m for m in moves if m.line_id==line.id and m.kind in {'accept','return_receive'}]
                origin=next(m for m in moves if m.line_id==line.id and m.kind=='dispatch');lost=posted.get(line.id,{})
                quantities=sum(m.quantity_milli for m in physical)+lost.get('quantity_milli',0)
                value=sum(m.value_cents for m in physical)+lost.get('value_cents',0)
                if quantities>origin.quantity_milli or value>origin.value_cents:raise HTTPException(409,'实收、原退与损失超过原发出批次')
                complete=complete and quantities==origin.quantity_milli and value==origin.value_cents
            if complete:parent.status='completed'
            transfer.synchronize(db,user,parent,'loss','按双方原事实确认运输差异，未生成库存或现金')
        elif action=='cancel':
            if row.status=='disposed' or _rows(db,TransferExceptionDisposal,exception_id=row.id):raise HTTPException(409,'已有真实处置不得取消或抹除')
            if user.id!=row.requested_by and role_for_store(db,user,sid) not in MANAGER:raise HTTPException(403,'仅原申请人或本店主管可有据取消未生效差异')
            db.add(TransferExceptionCancellation(exception_id=row.id,store_id=sid,reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
            row.status='cancelled';row.active_transfer_id=None
        row.updated_at=utcnow();db.flush();sync_exception_tasks(db,user,row,parent);return row,parent
    return _execute(db,user,request_id,str(key)+':'+action,dict(version=version,transfer_version=transfer_version,case_version=case_version,values=v),run)
