"""Narrow original-liability authority and immutable per-quote responsibility."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib,json
from fastapi import HTTPException
from sqlalchemy import select,or_,and_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import utcnow
from .models import User,Store
from .tenancy import single_store,role_for_store,project_user
from .flow_models import Case,Task,FlowEvent
from .customer_service_models import CustomerVehicle
from .repair_models import RepairQuote,RepairLine
from .service_intake_models import ReworkRequest,ReworkSourceLine,RepairIntake,RepairVehicleBinding,ServiceAppointment
from .rework_extension_models import ReworkSourceGrant,ReworkGrantDecision,ReworkGrantReceipt,ReworkExtension,ReworkQuoteScope,ReworkLineScope,SCOPE_FIELDS
from . import service_intake_service as intake
from . import flow_engine as flow

MANAGE={'admin','manager'}
ADVISE={'admin','service'}
READ=ADVISE|MANAGE|{'finance','auditor'}

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=lambda v:v.isoformat() if isinstance(v,datetime) else str(v))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def grant_digest(g):return digest({k:getattr(g,k) for k in SCOPE_FIELDS if k!='scope_digest'})

@contextmanager
def authority(db):
    old=db.info.get('_rework_authority');db.info['_rework_authority']=True
    try:yield
    finally:
        if old is None:db.info.pop('_rework_authority',None)
        else:db.info['_rework_authority']=old

@contextmanager
def _read_scope(db,sid):
    """Exact grant/vehicle target only; no writes or implicit broad store access."""
    old={k:db.info.get(k) for k in ('store_scope','write_store')}
    with db.no_autoflush:
        db.info['store_scope']=(sid,);db.info['write_store']=None
        try:yield
        finally:
            for k,v in old.items():
                if v is None:db.info.pop(k,None)
                else:db.info[k]=v

def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理原责任返修授权')

def _party(db,key,sid,role,access):
    user=db.scalar(select(User).where(User.id==key))
    store=db.scalar(select(Store).where(Store.id==sid,Store.active.is_(True)))
    if not user or not store or role_for_store(db,user,sid)!=role or user.access_version!=access:
        raise HTTPException(409,'授权人员的门店、岗位或访问版本已变化，请重新申请')
    return project_user(user,role)

def _parties(db,g):
    sender=_party(db,g.requested_by,g.from_store_id,g.requester_role,g.requester_access_version)
    _party(db,g.recipient_id,g.to_store_id,g.recipient_role,g.recipient_access_version)
    approvals=list(db.scalars(select(ReworkGrantDecision).where(ReworkGrantDecision.grant_id==g.id,ReworkGrantDecision.action=='approve')))
    for a in approvals:_party(db,a.actor_id,a.store_id,a.actor_role,a.actor_access_version)
    return sender

def _grant(db,user,key,source=False):
    sid=single_store(db);_role(user,READ)
    conditions=[ReworkSourceGrant.from_store_id==sid]
    if not source:conditions.append(and_(ReworkSourceGrant.to_store_id==sid,ReworkSourceGrant.recipient_id==user.id))
    g=db.scalar(select(ReworkSourceGrant).where(ReworkSourceGrant.id==key,or_(*conditions)).with_for_update())
    if not g:raise HTTPException(404,'当前门店或指定员工没有此原责任授权')
    if g.definition_version!=1 or grant_digest(g)!=g.scope_digest:raise HTTPException(409,'原责任授权范围不完整')
    _parties(db,g)
    return g

def _source_facts(db,user,source,selected):
    original,settlement=intake._source(db,user,source.id)
    binding=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==source.id))
    if not binding:raise HTTPException(409,'原维修须先按原凭据核验同客户及 VIN')
    vehicle,_=intake._vehicle(db,user,binding.customer_vehicle_id)
    if any(getattr(binding,k)!=getattr(vehicle,k) for k in ('vin','customer_identity_id','vehicle_identity_id')) or vehicle.customer_id!=source.customer_id:
        raise HTTPException(409,'原维修车辆身份不一致')
    if source.flow_version==3:intake._evidence(db,user,source,binding.evidence_id)
    else:
        context,_=intake.context(db,source)
        original_intake=intake._one(db,ServiceAppointment,context.appointment_id) if context.appointment_id else intake._one(db,ReworkRequest,context.rework_id)
        intake._evidence(db,user,flow.get_case(db,user,original_intake.case_id),binding.evidence_id)
    if len(set(selected))!=len(selected) or not selected:raise HTTPException(422,'请选择不重复的原责任项目')
    lines=[]
    for key in sorted(selected):
        line=db.scalar(select(RepairLine).where(RepairLine.id==key,RepairLine.quote_id==settlement.quote_id))
        if not line:raise HTTPException(404,'责任项目不在原最终结算报价')
        lines.append({k:getattr(line,k) for k in ('id','code','name','quantity_milli')})
    return settlement,binding,vehicle,lines

def _check_original(db,g):
    sender=_parties(db,g)
    with _read_scope(db,g.from_store_id):
        source=flow.get_case(db,sender,g.source_case_id)
        db.scalar(select(Case).where(Case.id==source.id,Case.store_id==g.from_store_id).with_for_update())
        settlement,binding,vehicle,lines=_source_facts(db,sender,source,[v['id'] for v in g.source_lines])
        if source.version!=g.source_case_version or source.number!=g.source_number or settlement.quote_id!=g.source_quote_id or vehicle.id!=g.from_vehicle_id or lines!=g.source_lines or any(getattr(binding,k)!=getattr(g,k) for k in ('vin','customer_identity_id','vehicle_identity_id')):
            raise HTTPException(409,'原责任来源已有变化，请原店重新核对授权')
        intake._evidence(db,sender,source,g.evidence_id)
    with _read_scope(db,g.to_store_id):
        target=db.scalar(select(CustomerVehicle).where(CustomerVehicle.id==g.to_vehicle_id,CustomerVehicle.active.is_(True)))
        if not target or any(getattr(target,k)!=getattr(g,k) for k in ('vin','customer_identity_id','vehicle_identity_id')):
            raise HTTPException(409,'接收店客户车辆身份不再匹配')

def _public(db,user,g):
    source=single_store(db)==g.from_store_id
    active=g.status=='consumed' or (g.status=='approved' and g.expires_at>utcnow())
    result={k:getattr(g,k) for k in ('id','version','definition_version','from_store_id','to_store_id','recipient_id','status')}
    result['expires_at']=g.expires_at.isoformat()+'Z';result['can_receive']=active and g.status=='approved' and user.id==g.recipient_id and single_store(db)==g.to_store_id
    if source or active:
        result.update(source_number=g.source_number,vin=g.vin,source_lines=g.source_lines,to_vehicle_id=g.to_vehicle_id,
            responsible_name=g.responsible_name,original_liability_limit_cents=g.original_liability_limit_cents,reason=g.reason)
    if source:result.update(source_case_id=g.source_case_id,source_case_version=g.source_case_version,requested_by=g.requested_by,evidence_id=g.evidence_id)
    return result

def detail(db,user,key):
    with authority(db):return _public(db,user,_grant(db,user,key))

def list_grants(db,user):
    _role(user,READ);sid=single_store(db)
    with authority(db):
        keys=list(db.scalars(select(ReworkSourceGrant.id).where(or_(ReworkSourceGrant.from_store_id==sid,and_(ReworkSourceGrant.to_store_id==sid,ReworkSourceGrant.recipient_id==user.id))).order_by(ReworkSourceGrant.id.desc()).limit(501)))
        if len(keys)>500:raise HTTPException(422,'原责任授权超过本次目录上限，请按部署规模扩展检索')
        result=[]
        for key in keys:
            try:result.append(_public(db,user,_grant(db,user,key)))
            except HTTPException as e:
                if e.status_code!=409:raise
        return {'items':result}

def targets(db,user,source_id):
    _role(user,ADVISE);single_store(db)
    source=flow.get_case(db,user,source_id)
    original,settlement=intake._source(db,user,source_id)
    binding=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==source_id))
    if not binding:raise HTTPException(409,'原维修须先核验 VIN 与客户身份')
    result=[]
    for store in db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.id)):
        with _read_scope(db,store.id):
            vehicles=list(db.scalars(select(CustomerVehicle).where(CustomerVehicle.active.is_(True),CustomerVehicle.vin==binding.vin,
                CustomerVehicle.customer_identity_id==binding.customer_identity_id,CustomerVehicle.vehicle_identity_id==binding.vehicle_identity_id).limit(101)))
        if len(vehicles)>100:raise HTTPException(422,'同身份车辆关系超过选择上限，请核对主档')
        if not vehicles:continue
        people=[{'id':u.id,'name':u.display_name} for u in db.scalars(select(User).where(User.active.is_(True))) if role_for_store(db,u,store.id) in ADVISE]
        result.append({'store_id':store.id,'store_name':store.name,'vehicles':[{'id':v.id,'vin':v.vin,'plate':v.plate} for v in vehicles],'recipients':people})
    return {'items':result}

def _execute(db,user,key,action,payload,operation):
    single_store(db);fingerprint=digest([action,payload])
    with authority(db):
        try:
            prior=db.scalar(select(ReworkGrantReceipt).where(ReworkGrantReceipt.request_key==key))
            if prior:
                if prior.actor_id!=user.id or prior.digest!=fingerprint:raise HTTPException(409,'原请求编号已用于其他办理')
                g=_grant(db,user,prior.grant_id)
            else:
                g=operation();db.flush();db.add(ReworkGrantReceipt(request_key=key,actor_id=user.id,digest=fingerprint,grant_id=g.id));db.flush()
            result=_public(db,user,g);db.commit();return result
        except (IntegrityError,OperationalError,StaleDataError):
            db.rollback();raise HTTPException(409,'原责任授权或原单占用同时变化，请刷新核对并保留请求编号')
        except Exception:db.rollback();raise

def propose(db,user,key,v):
    _role(user,ADVISE)
    def run():
        sid=single_store(db);now=utcnow();expires=datetime.fromisoformat(v['expires_at'].replace('Z','+00:00')).astimezone(timezone.utc).replace(tzinfo=None)
        if not now<expires<=now+timedelta(days=90):raise HTTPException(422,'本次原责任授权须在未来九十天内到期')
        source=flow.get_case(db,user,v['source_case_id'])
        db.scalar(select(Case).where(Case.id==source.id,Case.store_id==sid).with_for_update())
        if source.version!=v['source_case_version']:raise HTTPException(409,'原单已有变化，请刷新后核对')
        settlement,binding,vehicle,lines=_source_facts(db,user,source,v['source_line_ids'])
        intake._evidence(db,user,source,v['evidence_id'])
        recipient=db.scalar(select(User).where(User.id==v['recipient_id']))
        target_store=db.scalar(select(Store).where(Store.id==v['to_store_id'],Store.active.is_(True)))
        recipient_role=role_for_store(db,recipient,v['to_store_id'])
        if not target_store or recipient_role not in ADVISE:raise HTTPException(422,'请选择接收店当前可接待维修的指定员工')
        with _read_scope(db,v['to_store_id']):
            target=db.scalar(select(CustomerVehicle).where(CustomerVehicle.id==v['to_vehicle_id'],CustomerVehicle.active.is_(True)))
            if not target or any(getattr(target,k)!=getattr(vehicle,k) for k in ('vin','customer_identity_id','vehicle_identity_id')):
                raise HTTPException(422,'接收车辆须为同一共享客户身份及 VIN，不能按电话或车牌推断')
        store=db.scalar(select(Store).where(Store.id==sid))
        g=ReworkSourceGrant(definition_version=1,version=1,from_store_id=sid,to_store_id=v['to_store_id'],source_case_id=source.id,source_case_version=source.version,
            source_quote_id=settlement.quote_id,from_vehicle_id=vehicle.id,to_vehicle_id=target.id,customer_identity_id=vehicle.customer_identity_id,
            vehicle_identity_id=vehicle.vehicle_identity_id,vin=vehicle.vin,source_number=source.number,source_lines=lines,
            original_liability_limit_cents=v['original_liability_limit_cents'],responsible_name=store.name+'原维修责任',
            recipient_id=recipient.id,recipient_role=recipient_role,recipient_access_version=recipient.access_version,
            requested_by=user.id,requester_role=user.role,requester_access_version=user.access_version,evidence_id=v['evidence_id'],reason=v['reason'],
            expires_at=expires,status='pending',created_at=now,updated_at=now,scope_digest='')
        g.scope_digest=grant_digest(g);db.add(g);db.flush();return g
    return _execute(db,user,key,'propose',v,run)

def _decision(db,user,g,action,reason):
    db.add(ReworkGrantDecision(grant_id=g.id,previous_version=g.version,action=action,actor_id=user.id,actor_role=user.role,actor_access_version=user.access_version,
        store_id=single_store(db),scope_digest=g.scope_digest,reason=reason))
    g.status={'approve':'approved','reject':'rejected','cancel':'cancelled','revoke':'revoked','consume':'consumed'}[action];g.updated_at=utcnow()

def decide(db,user,key,request_id,version,action,v):
    def run():
        g=_grant(db,user,key,True)
        if g.version!=version:raise HTTPException(409,'授权已变化，请刷新核对')
        if action in {'approve','reject'}:
            if user.role not in MANAGE or user.id==g.requested_by:raise HTTPException(403,'须原店另一名主管独立核对，不可自批')
            if g.status!='pending':raise HTTPException(409,'仅待批准原责任授权可复核')
        elif action in {'cancel','revoke'}:
            if user.id!=g.requested_by and user.role not in MANAGE:raise HTTPException(403,'只有发起人或原店主管可撤回')
            if g.status!=('pending' if action=='cancel' else 'approved'):raise HTTPException(409,'授权已被承接或已结束；已有返修须回原申请办理退出')
        else:raise HTTPException(404,'原责任授权动作不存在')
        if action=='approve':
            if utcnow()>=g.expires_at:raise HTTPException(409,'原责任授权已到期')
            _check_original(db,g)
        _decision(db,user,g,action,v['reason']);return g
    return _execute(db,user,request_id,action,{'id':key,'version':version,**v},run)

def request_create(db,user,key,v):
    _role(user,ADVISE)
    with authority(db):
        # Replays still check the recipient's current role/access version before
        # intake's immutable receipt can return any previous business result.
        g=_grant(db,user,v['grant_id'])
        if g.to_store_id!=single_store(db) or g.recipient_id!=user.id:raise HTTPException(404,'仅授权指定接收人可承接')
        def run():
            if g.version!=v['grant_version'] or g.status!='approved' or utcnow()>=g.expires_at:raise HTTPException(409,'原责任授权已变化、到期、撤销或已使用')
            _check_original(db,g)
            vehicle,customer=intake._vehicle(db,user,g.to_vehicle_id);resource=intake._resource(db,v['resource_id'])
            if resource.resource_type!='repair':raise HTTPException(422,'返修须选择本店维修工位')
            row=intake._case(db,user,customer,'原责任及新增项目返修申请','rework')
            r=ReworkRequest(case_id=row.id,source_case_id=g.source_case_id,source_quote_id=g.source_quote_id,customer_vehicle_id=vehicle.id,resource_id=resource.id,
                reason=v['reason'],requested_by=user.id,active_source_id=g.source_case_id)
            db.add(r);db.flush()
            db.add_all([ReworkSourceLine(request_id=r.id,source_line_id=line['id']) for line in g.source_lines])
            db.add(ReworkExtension(request_id=r.id,definition_version=1,grant_id=g.id,grant_digest=g.scope_digest,actor_id=user.id))
            _decision(db,user,g,'consume','指定接收店领用本次原责任授权');flow.set_data(row,rework_id=r.id)
            flow.ensure_task(db,row,'intake_liability','核对原授权并确认承接原责任与新增自费分离','manager')
            flow.log_event(db,user,row,'intake_rework_request','领用原责任授权建立关联返修',detail={'rework_definition':1,'grant_id':g.id,'grant_digest':g.scope_digest})
            db.flush();return intake.rework_detail(db,user,r.id)
        return intake._execute(db,user,key,'rework_extension_create',v,run)

def extension(db,request_id):
    return db.scalar(select(ReworkExtension).where(ReworkExtension.request_id==request_id)) if request_id else None

def extension_grant(db,ext,live=False):
    """A legally consumed scope belongs to the local case as frozen evidence.

    Current grant directory/source access still uses _grant/_parties. Local
    tasks may be explicitly reassigned after staff changes without reopening
    the original store's records or re-expanding this immutable scope.
    """
    with authority(db):
        g=db.scalar(select(ReworkSourceGrant).where(ReworkSourceGrant.id==ext.grant_id,ReworkSourceGrant.to_store_id==ext.store_id))
        if ext.definition_version!=1 or not g or g.status!='consumed' or ext.grant_digest!=g.scope_digest or grant_digest(g)!=g.scope_digest:raise HTTPException(409,'返修原责任扩展来源不完整')
        if live:_parties(db,g)
        return g

def repair_extension(db,row):
    ctx=db.scalar(select(RepairIntake).where(RepairIntake.case_id==row.id))
    return extension(db,ctx.rework_id) if ctx else None

def info(db,ext):
    g=extension_grant(db,ext)
    return {'definition_version':1,'grant_id':g.id,'source_number':g.source_number,'from_store_id':g.from_store_id,'source_lines':g.source_lines,
        'responsible_name':g.responsible_name,'original_liability_limit_cents':g.original_liability_limit_cents}

def prepare_quote(db,row,v,old):
    ext=repair_extension(db,row)
    if not ext:
        if any('charge_scope' in line or 'source_line_id' in line for line in v['lines']):raise HTTPException(409,'普通或旧全内部工单不能冒充新原责任返修')
        return None
    g=extension_grant(db,ext);allowed={line['id'] for line in g.source_lines}
    prior={line.line_key:(scope.charge_scope,scope.source_line_id) for line,scope in db.execute(select(RepairLine,ReworkLineScope).join(ReworkLineScope,ReworkLineScope.line_id==RepairLine.id).where(RepairLine.quote_id==old.id))} if old else {}
    result=[]
    if v['purpose']=='stop':return {'extension':ext,'grant':g,'scopes':prior,'stop':True}
    for spec in v['lines']:
        scope=spec.get('charge_scope');source=spec.get('source_line_id')
        if scope not in {'original_liability','customer_extra'} or (scope=='original_liability' and source not in allowed) or (scope=='customer_extra' and source is not None):
            raise HTTPException(422,'每行须明确原责任或新增自费；原责任须来自已批准项目')
        original=prior.get(spec.get('line_key'))
        if original and original!=(scope,source):raise HTTPException(409,'已授权明细不能改换原责任与客户自费类别')
        result.append({'charge_scope':scope,'source_line_id':source})
    if not any(s['charge_scope']=='original_liability' for s in result):raise HTTPException(422,'关联返修至少保留一个获批原责任项目，普通自费不能冒充返修')
    return {'extension':ext,'grant':g,'scopes':result,'stop':False}

def quote_scopes(contract,specs):
    if contract is None:return None
    if contract['stop']:
        result=[{'charge_scope':contract['scopes'][s['line_key']][0],'source_line_id':contract['scopes'][s['line_key']][1]} for s in specs]
    else:result=contract['scopes']
    original=sum(s['amount_cents'] for s,p in zip(specs,result) if p['charge_scope']=='original_liability')
    if original>contract['grant'].original_liability_limit_cents:raise HTTPException(409,'原责任行合计超过原店本次批准额度，请重新申请授权')
    return result

def freeze_quote(db,quote,lines,contract,scopes):
    if contract is None:return
    db.add(ReworkQuoteScope(quote_id=quote.id,request_id=contract['extension'].request_id,
        original_liability_cents=sum(l.amount_cents for l,s in zip(lines,scopes) if s['charge_scope']=='original_liability'),
        customer_extra_cents=sum(l.amount_cents for l,s in zip(lines,scopes) if s['charge_scope']=='customer_extra'),
        digest=digest({'quote_digest':quote.digest,'scopes':scopes})))
    db.flush()
    db.add_all([ReworkLineScope(line_id=line.id,quote_id=quote.id,**scope) for line,scope in zip(lines,scopes)])

def allocation_guard(db,row,ext,allocations):
    g=extension_grant(db,ext);q=db.scalar(select(ReworkQuoteScope).where(ReworkQuoteScope.quote_id==row.data.get('authorized_quote_id'),ReworkQuoteScope.request_id==ext.request_id))
    if not q:raise HTTPException(409,'返修当前报价缺少冻结原责任分类')
    expected={}
    if q.original_liability_cents:expected['internal']=(q.original_liability_cents,g.responsible_name)
    if q.customer_extra_cents:expected['customer']=(q.customer_extra_cents,None)
    if len(allocations)!=len(expected) or len({a['payer_type'] for a in allocations})!=len(allocations):raise HTTPException(409,'承担方须由冻结原责任与新增自费行计算')
    for a in allocations:
        wanted=expected.get(a['payer_type'])
        if not wanted or a['amount_cents']!=wanted[0] or (wanted[1] is not None and a['payer_name']!=wanted[1]):raise HTTPException(409,'原责任与新增自费金额必须分别等于冻结行合计，不能转嫁原责任')

def quote_description(db,quote_id):
    q=db.scalar(select(ReworkQuoteScope).where(ReworkQuoteScope.quote_id==quote_id))
    return {'original_liability_cents':q.original_liability_cents,'customer_extra_cents':q.customer_extra_cents} if q else None

def customer_line(db,line):
    scope=db.scalar(select(ReworkLineScope).where(ReworkLineScope.line_id==line.id))
    return scope is None or scope.charge_scope=='customer_extra'

def service_assignee(db,row):
    """Honor explicit local service handoffs when creating the next task.

    No cross-store authorization is revived; existing open tasks still need
    their own ordinary manager handoff. A newly created exit task can use the
    existing local role router when its historical owner is no longer valid.
    """
    if not repair_extension(db,row):return row.owner_id
    for event in db.scalars(select(FlowEvent).where(FlowEvent.case_id==row.id,FlowEvent.action=='reassign').order_by(FlowEvent.id.desc())):
        task=db.scalar(select(Task).where(Task.id==(event.detail or {}).get('task_id'),Task.case_id==row.id,Task.role=='service'))
        target=db.scalar(select(User).where(User.id==(event.detail or {}).get('to')))
        if task and target and role_for_store(db,target,row.store_id) in ADVISE|MANAGE:return target.id
    owner=db.scalar(select(User).where(User.id==row.owner_id))
    return row.owner_id if owner and role_for_store(db,owner,row.store_id) in ADVISE|MANAGE else None
