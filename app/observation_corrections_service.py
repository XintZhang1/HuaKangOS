"""Vehicle-controlled observation corrections; no cash, stock or external contact.

Lock protocol: CustomerVehicle first, then correction/reminder Cases in ID order,
all NOWAIT. Insurance callers may already hold their original Case; this module
only reads its immutable source facts and never locks that Case in reverse order.
"""
import hashlib,json,uuid
from contextlib import contextmanager
from datetime import date,timedelta
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import User
from .flow_models import Case,Task,FileAsset
from .customer_service_models import CustomerVehicle,VehicleObservation,CareCase,ReminderRule
from . import customer_service as care
from . import flow_engine as flow
from .tenancy import single_store,role_for_store,project_user
from .services import plain
from .file_security import require_usable
from .flow_documents import can_file
from .observation_corrections_models import *

READ=care.READ
WRITE=care.WRITE
MANAGE={'admin','manager'}
SPEC={'label':'日期里程纠正','module':'customers','create_roles':[],'fields':[],'initial':'pending','actions':[]}
STATES={'pending':'待提交依据','approval':'基准复核中','completed':'纠正已生效','rejected':'复核未通过','cancelled':'申请已撤回'}
AFFECTED={'delivery':{'first_service','maintenance'},'odometer':{'first_service','maintenance'},'first_service':{'first_service','maintenance'},'maintenance':{'maintenance'},'insurance':{'renewal'},'warranty':{'warranty'}}

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.case_id if model in {ObservationCorrection,ReminderBasis} else model.id)))
def _one(db,model,key):
    column=model.case_id if model in {ObservationCorrection,ReminderBasis} else model.id
    result=db.scalar(select(model).where(column==key))
    if not result:raise HTTPException(404,'当前门店原记录不存在')
    return result

@contextmanager
def authority(db,user,roles=READ):
    with care.authority(db,user,roles) as sid:
        old=db.info.get('_observation_authority');db.info['_observation_authority']=(sid,user.id)
        try:yield sid
        finally:
            if old is None:db.info.pop('_observation_authority',None)
            else:db.info['_observation_authority']=old

def control_vehicle(db,user,vehicle_id,version=None,*,active=False):
    """Must precede every reminder Case lock; caller commits or rolls back once."""
    sid=single_store(db);transaction=db.get_transaction();marker=db.info.get('_observation_vehicle_locks',{})
    previous=marker.get(vehicle_id)
    if previous and previous[0] is transaction:
        vehicle=previous[1]
        if version is not None and version!=previous[2]:raise HTTPException(409,'车辆资料版本已变化，请刷新后核对')
        return vehicle
    vehicle=db.scalar(select(CustomerVehicle).where(CustomerVehicle.id==vehicle_id).with_for_update(nowait=True).execution_options(populate_existing=True))
    if not vehicle:raise HTTPException(404,'当前门店客户车辆不存在')
    care._customer(db,user,vehicle.customer_id)
    if active and not vehicle.active:raise HTTPException(409,'客户车辆关系已停用')
    if version is not None and vehicle.version!=version:raise HTTPException(409,'车辆资料版本已变化，请刷新后核对')
    before=vehicle.version;vehicle.updated_at=utcnow();db.flush()
    db.info.setdefault('_observation_vehicle_locks',{})[vehicle.id]=(db.get_transaction(),vehicle,before)
    return vehicle

def _case_locks(db,ids):
    return {r.id:r for r in db.scalars(select(Case).where(Case.id.in_(sorted(set(ids)))).order_by(Case.id).with_for_update(nowait=True).execution_options(populate_existing=True))} if ids else {}

def _execute(db,user,key,action,payload,operation,roles=WRITE):
    with authority(db,user,roles):
        hashed=digest([action,payload])
        try:
            receipt=db.scalar(select(CorrectionReceipt).where(CorrectionReceipt.request_key==key))
            if receipt:
                if receipt.actor_id!=user.id or receipt.digest!=hashed:raise HTTPException(409,'请求编号已用于其他人或不同内容')
                if receipt.result.get('case'):get_case(db,user,receipt.result['case']['id'])
                return receipt.result
            result=operation();db.add(CorrectionReceipt(request_key=key,digest=hashed,result=result,actor_id=user.id));db.commit();return result
        except (IntegrityError,OperationalError,StaleDataError) as exc:
            db.rollback();raise HTTPException(409,'车辆基准或相关待办正被同时办理；本次未保存，请刷新并保留请求编号') from exc
        except Exception:db.rollback();raise
        finally:db.info.pop('_observation_vehicle_locks',None)

def can_read_case(db,user,row):
    if user.role not in READ or getattr(user,'_aggregate_scope',False):return False
    if user.role in {'sales','reception'}:
        customer=db.scalar(select(care.Customer).where(care.Customer.id==row.customer_id))
        return bool(customer and customer.owner_id==user.id)
    return True

def get_case(db,user,case_id):
    row=db.scalar(select(Case).where(Case.id==case_id,Case.kind=='observation_correction',Case.flow_version==2))
    if not row or not can_read_case(db,user,row):raise HTTPException(404,'日期里程纠正申请不存在或无权查看')
    return row

def _source_result(db,observation_id):
    from .insurance_models import InsuranceResult
    return db.scalar(select(InsuranceResult).where(InsuranceResult.observation_id==observation_id))

def _raw(row):
    return {'id':row.id,'vehicle_id':row.vehicle_id,'kind':row.kind,'observed_date':row.observed_date.isoformat(),'odometer_km':row.odometer_km,
        'valid_until':row.valid_until.isoformat() if row.valid_until else None,'source_reference':row.source_reference,'evidence_id':row.evidence_id}

def effective_observations(db,vehicle_id,*,include_inactive=False):
    result=[]
    for original in _rows(db,VehicleObservation,vehicle_id=vehicle_id):
        values=_raw(original);effects=_rows(db,CorrectionEffect,observation_id=original.id);effect=effects[-1] if effects else None
        request=_one(db,ObservationCorrection,effect.case_id) if effect else None
        if request and request.operation=='replace':values.update(request.proposed)
        ended=db.scalar(select(InsuranceBasisInvalidation.id).where(InsuranceBasisInvalidation.observation_id==original.id))
        business=_source_result(db,original.id)
        values.update(effect_id=effect.id if effect else None,active=not ended and not(request and request.operation=='retract'),
            source_type='insurance_result' if business else 'manual_observation',source_case_id=business.case_id if business else None,
            odometer_measured=not bool(business),insurance_invalidation_id=ended)
        if business:values['odometer_km']=None
        values['digest']=digest(values)
        if values['active'] or include_inactive:result.append(values)
    return result

def effective_vehicle_values(db,vehicle):
    observations=effective_observations(db,vehicle.id)
    measured=[o for o in observations if o['odometer_measured'] and o['odometer_km'] is not None]
    current=measured[-1] if measured else None
    return {'odometer_km':current['odometer_km'] if current else None,'observed_date':current['observed_date'] if current else None,
        'current_observation_id':current['id'] if current else None,'current_effect_id':current['effect_id'] if current else None,
        'observation_epoch':reminder_epoch(db)}

def guard_observation_append(db,user,vehicle,values):
    """No insertion/commit. Replace raw-history checks after control_vehicle.

    Original observe retains its own schema, source-file checks and append audit.
    Business insurance creation does not call this manual-observation helper.
    """
    control_vehicle(db,user,vehicle.id,active=True)
    if _pending(db,vehicle.id):raise HTTPException(409,'本车原观察正在复核，请先处理后再登记新的日期或里程')
    when=values['observed_date'];km=values['odometer_km'];until=values['valid_until'];kind=values['kind']
    when=date.fromisoformat(when) if isinstance(when,str) else when
    until=date.fromisoformat(until) if isinstance(until,str) else until
    if type(km) is not int or not 0<=km<=3_000_000 or not date(2000,1,1)<=when<=today():raise HTTPException(422,'请填写实际日期与整数公里数，不能填未来里程')
    observations=effective_observations(db,vehicle.id);measured=[o for o in observations if o['odometer_measured']]
    if measured and (when.isoformat()<measured[-1]['observed_date'] or km<measured[-1]['odometer_km']):raise HTTPException(409,'新观察早于仍有效实际日期或里程，请先有据纠正原记录')
    if kind in {'delivery','first_service'} and any(o['kind']==kind for o in observations):raise HTTPException(409,'已有有效交付或首保完成事实，不能重复建立周期')
    if kind in {'insurance','warranty'}:
        if not until or not when<=until<=date(2100,1,1):raise HTTPException(422,'请填写不早于本次实际日期的截止日')
        if any(o['kind']==kind and o['valid_until'] and o['valid_until']>until.isoformat() for o in observations):raise HTTPException(409,'更短期限应指向原观察办理纠正，不能假建另一周期')
    elif until is not None:raise HTTPException(422,'此观察种类不填写保险或保修截止日')
    if any(o['kind']==kind and o['observed_date']==when.isoformat() and o['odometer_km']==km and o['valid_until']==(until.isoformat() if until else None) and o['source_reference']==values['source_reference'] for o in observations):raise HTTPException(409,'本条有效原资料已登记，请查看原观察')

def _effective(db,observation_id):
    original=_one(db,VehicleObservation,observation_id)
    return next(o for o in effective_observations(db,original.vehicle_id,include_inactive=True) if o['id']==observation_id)

def _proof(db,user,row,file_id):
    file=_one(db,FileAsset,file_id)
    if file.case_id!=row.id or file.store_id!=row.store_id or file.generated or not can_file(user,row,file):
        raise HTTPException(422,'请关联本次纠正申请中获权可读的原件，不能借用旧业务附件或生成稿')
    require_usable(db,file);return file

def _proposed(db,observation,operation,values):
    current=_effective(db,observation.id)
    if current['source_type']!='manual_observation':raise HTTPException(409,'本条来自实际保险原单，客服不能改写保期或补造里程；请在原业务有据处理')
    if operation=='retract':
        if values:raise HTTPException(422,'撤销误登记不填写替代数值')
        if not current['active']:raise HTTPException(409,'该原观察已失效，无需重复撤销')
        return {}
    if set(values)!={'observed_date','odometer_km','valid_until','source_reference'}:raise HTTPException(422,'替代值仅包含原种类的实际日期、整数公里、期限和来源编号')
    try:
        when=date.fromisoformat(values['observed_date']);until=date.fromisoformat(values['valid_until']) if values['valid_until'] else None
    except (ValueError,TypeError):raise HTTPException(422,'请填写有效实际日期')
    km=values['odometer_km']
    if type(km) is not int or not 0<=km<=3_000_000 or not date(2000,1,1)<=when<=today():raise HTTPException(422,'里程须为0至300万整数公里，实际日期不得晚于今天')
    if observation.kind in {'insurance','warranty'}:
        if until is None or not when<=until<=date(2100,1,1):raise HTTPException(422,'保险或保修截止日须不早于实际登记日期')
    elif until is not None:raise HTTPException(422,'本观察种类不填写保险或保修期限')
    if not isinstance(values['source_reference'],str) or not 3<=len(values['source_reference'].strip())<=180:raise HTTPException(422,'请填写可追溯的原始资料编号')
    effective=effective_observations(db,observation.vehicle_id)
    others=[o for o in effective if o['id']!=observation.id and o['odometer_measured']]
    # Correction changes the value at the original position, never pretends a new
    # observation happened now. Meter replacement is a separate unsupported fact.
    for other in others:
        if other['id']<observation.id and (other['observed_date']>when.isoformat() or other['odometer_km']>km):raise HTTPException(409,'纠正值早于前一条仍有效实际观察，请先核对相互矛盾的原资料')
        if other['id']>observation.id and (other['observed_date']<when.isoformat() or other['odometer_km']<km):raise HTTPException(409,'纠正值超过后一条仍有效实际观察，请先核对原资料')
    if observation.kind in {'delivery','first_service'} and any(o['kind']==observation.kind for o in others):raise HTTPException(409,'不能建立第二个有效交付或首保完成基准')
    if current['active'] and all(current[k]==values[k] for k in values):raise HTTPException(409,'替代值与当前有效资料相同，无需重复纠正')
    return values

def _events(db,case_id):return _rows(db,CorrectionEvent,case_id=case_id)
def _pending(db,vehicle_id):
    return list(db.scalars(select(ObservationCorrection).join(Case,Case.id==ObservationCorrection.case_id).where(ObservationCorrection.vehicle_id==vehicle_id,Case.state=='approval')))

def _event(db,user,row,action,reason,evidence_id=None):
    item=CorrectionEvent(case_id=row.id,action=action,reason=reason,evidence_id=evidence_id,actor_id=user.id);db.add(item);db.flush()
    request=_one(db,ObservationCorrection,row.id)
    flow.log_event(db,user,row,'observation_'+action,{'create':'建立原观察纠正申请','submit':'提交日期里程复核','approve':'独立批准原观察纠正','reject':'拒绝原观察纠正','cancel':'撤回尚未生效纠正'}[action],detail={'observation_correction_id':row.id,'actor_role':user.role,
        'correction_digest':digest([request.vehicle_id,request.observation_id,request.base_digest,request.operation,request.proposed,request.reason])})
    return item

def create(db,user,key,vehicle_id,vehicle_version,observation_id,base_digest,operation,proposed,reason):
    payload=locals().copy();payload={k:v for k,v in payload.items() if k not in {'db','user','key'}}
    def apply():
        vehicle=control_vehicle(db,user,vehicle_id,vehicle_version,active=True);original=_one(db,VehicleObservation,observation_id)
        if original.vehicle_id!=vehicle.id:raise HTTPException(422,'原观察不属于本次同客户同VIN车辆')
        current=_effective(db,original.id)
        if current['digest']!=base_digest:raise HTTPException(409,'原观察有效版本已变化，请重新核对当前值')
        chosen=_proposed(db,original,operation,proposed)
        row=Case(kind='observation_correction',flow_version=2,state='pending',number='OC'+uuid.uuid4().hex[:18].upper(),title='日期与里程原观察纠正',owner_id=user.id,created_by=user.id,customer_id=vehicle.customer_id,business_date=today(),due_date=today(),data={})
        db.add(row);db.flush()
        from .business_entity_service import freeze_case_entity
        freeze_case_entity(db,user,row)
        db.add(ObservationCorrection(case_id=row.id,vehicle_id=vehicle.id,observation_id=original.id,base_digest=base_digest,original_snapshot=current,operation=operation,proposed=chosen,reason=reason));db.flush()
        _event(db,user,row,'create',reason);flow.ensure_task(db,row,'observation_submit','上传原件并提交纠正复核',user.role,assignee=user.id)
        return {'case':describe(db,user,row)}
    return _execute(db,user,key,'create',payload,apply)

def _independent_manager(db,user,row):
    options=[u for u in db.scalars(select(User).where(User.active.is_(True)).order_by(User.id)) if u.id!=row.created_by and role_for_store(db,u,row.store_id) in MANAGE]
    if not options:raise HTTPException(409,'本店缺少另一位可独立复核的主管，请先配置岗位')
    return options[0]

def _affected_care(db,vehicle_id,original):
    result=[]
    for row in db.scalars(select(CareCase).where(CareCase.vehicle_id==vehicle_id,CareCase.subtype.in_(AFFECTED[original.kind]),CareCase.rule_id.is_not(None)).order_by(CareCase.case_id)):
        basis=db.scalar(select(ReminderBasis).where(ReminderBasis.case_id==row.case_id))
        # Older tasks did not freeze the current mileage source: mark those for
        # review conservatively, without inventing a historical dependency.
        if not basis or original.id in {basis.baseline_id,basis.current_id} or original.kind=='first_service' and row.subtype=='first_service':result.append(row)
    return result

def _invalidate(db,user,vehicle_id,original,*,correction_case_id=None,insurance_id=None,locked=None):
    sources=_affected_care(db,vehicle_id,original);locked=locked or _case_locks(db,[c.case_id for c in sources]);token=('correction:'+str(correction_case_id)) if correction_case_id else 'insurance:'+str(insurance_id)
    for c in sources:
        if db.scalar(select(ReminderInvalidation.id).where(ReminderInvalidation.case_id==c.case_id,ReminderInvalidation.source_key==token)):continue
        row=locked[c.case_id];previous=row.state;open_task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='care_handle',Task.status=='open'))
        closed=previous in {'pending','working'} and bool(open_task)
        db.add(ReminderInvalidation(case_id=row.id,correction_case_id=correction_case_id,insurance_invalidation_id=insurance_id,observation_id=original.id,previous_state=previous,closed_open_task=closed,source_key=token,actor_id=user.id))
        if closed:
            row.state='cancelled';row.completed_date=today();row.updated_at=utcnow();flow.finish_task(db,row,'care_handle',user,'cancelled')
        care._record(db,user,row,'cancel' if closed else 'followup','原提醒基准已更正或原保险已实际终止；保留原跟进历史，未发送客户消息',{'basis_invalidation':token,'previous_state':previous,'closed_open_task':closed})
    db.flush()

def command(db,user,key,case_id,version,action,values):
    def apply():
        first=get_case(db,user,case_id);request=_one(db,ObservationCorrection,case_id);vehicle=control_vehicle(db,user,request.vehicle_id)
        original=_one(db,VehicleObservation,request.observation_id)
        related=_affected_care(db,vehicle.id,original) if action=='approve' else []
        locked=_case_locks(db,[first.id]+[c.case_id for c in related]);row=locked[first.id]
        if row.version!=version:raise HTTPException(409,'纠正申请已变化，请刷新核对')
        own=user.id==row.created_by or user.role in MANAGE
        if action in {'submit','cancel'} and not own:raise HTTPException(403,'请由申请人或本店主管办理')
        if action=='submit':
            if row.state!='pending':raise HTTPException(409,'当前申请不能重复提交')
            if any(r.observation_id==original.id for r in _pending(db,vehicle.id)):raise HTTPException(409,'同一原观察已有待复核申请，请先处理')
            if request.base_digest!=_effective(db,original.id)['digest']:raise HTTPException(409,'原观察有效版本已变化，请撤回后重新提出')
            _proposed(db,original,request.operation,request.proposed);_proof(db,user,row,values['evidence_id'])
            manager=_independent_manager(db,user,row);row.state='approval';flow.finish_task(db,row,'observation_submit',user)
            _event(db,user,row,action,'申请人核对本次原始资料后提交',values['evidence_id']);flow.ensure_task(db,row,'observation_review','独立复核原观察与替代值','manager',assignee=manager.id)
        elif action in {'approve','reject'}:
            if user.role not in MANAGE or user.id==row.created_by:raise HTTPException(403,'须由另一位本店主管独立复核，管理员也不能自批')
            if row.state!='approval':raise HTTPException(409,'当前申请不在待复核状态')
            _proof(db,user,row,values['evidence_id']);reason=values['reason']
            if action=='approve':
                current=_effective(db,original.id)
                if current['digest']!=request.base_digest:raise HTTPException(409,'待复核期间原基准已变化，不能批准过期替代值')
                _proposed(db,original,request.operation,request.proposed);row.state='completed'
                review=_event(db,user,row,action,reason,values['evidence_id'])
                db.add(CorrectionEffect(case_id=row.id,observation_id=original.id,parent_effect_id=current['effect_id'],parent_token=str(current['effect_id'] or 0),review_event_id=review.id,actor_id=user.id));db.flush()
                _invalidate(db,user,vehicle.id,original,correction_case_id=row.id,locked=locked)
            else:row.state='rejected';_event(db,user,row,action,reason,values['evidence_id'])
            row.completed_date=today();flow.close_tasks(db,row,user)
        elif action=='cancel':
            if row.state not in {'pending','approval'}:raise HTTPException(409,'已生效或已结案申请不可取消；请另建指向当前有效版本的纠正')
            row.state='cancelled';row.completed_date=today();_event(db,user,row,action,values['reason']);flow.close_tasks(db,row,user)
        else:raise HTTPException(404,'不存在此纠正动作')
        row.updated_at=utcnow();db.flush();return {'case':describe(db,user,row)}
    return _execute(db,user,key,action,{'case_id':case_id,'version':version,'values':values},apply)

def describe(db,user,row):
    if not can_read_case(db,user,row):raise HTTPException(404,'日期里程纠正申请不存在或无权查看')
    request=_one(db,ObservationCorrection,row.id);vehicle=_one(db,CustomerVehicle,request.vehicle_id)
    actions=[]
    if row.state=='pending' and (row.created_by==user.id or user.role in MANAGE):actions=['submit','cancel']
    if row.state=='approval':
        if row.created_by==user.id or user.role in MANAGE:actions.append('cancel')
        if user.role in MANAGE and row.created_by!=user.id:actions+=['approve','reject']
    return {'id':row.id,'number':row.number,'version':row.version,'state':row.state,'state_label':STATES[row.state],'vehicle_id':vehicle.id,'vin':vehicle.vin,'plate':vehicle.plate,
        'observation_id':request.observation_id,'operation':request.operation,'original':request.original_snapshot,'proposed':request.proposed,'reason':request.reason,'actions':actions,
        'current':_effective(db,request.observation_id),'events':[plain(e) for e in _events(db,row.id)],
        'invalidated_reminder_ids':[r.case_id for r in _rows(db,ReminderInvalidation,correction_case_id=row.id)]}

def vehicle_view(db,user,vehicle_id):
    with authority(db,user):
        vehicle=_one(db,CustomerVehicle,vehicle_id);care._customer(db,user,vehicle.customer_id)
        return {'vehicle':{**plain(vehicle),**effective_vehicle_values(db,vehicle)},'observations':effective_observations(db,vehicle_id,include_inactive=True),
            'corrections':[describe(db,user,_one(db,Case,r.case_id)) for r in _rows(db,ObservationCorrection,vehicle_id=vehicle_id)],'can_create':user.role in WRITE}

def _insurance_source(db,source,plan_id):
    """Validate the complete immutable source chain, not a workflow state label."""
    from .insurance_models import (InsuranceOrder,InsuranceQuote,InsuranceSubmission,InsuranceResult,InsuranceTermination,
        InsuranceTerminationReview,InsuranceTerminationConsent,InsuranceTerminationApplication,InsuranceTerminationCancellation)
    if source.kind!='insurance' or source.flow_version!=3:raise HTTPException(422,'仅支持有明确原保单来源的保险明细单')
    order=_one(db,InsuranceOrder,source.id);plan=_one(db,InsuranceTermination,plan_id);quote=_one(db,InsuranceQuote,plan.quote_id)
    application=db.scalar(select(InsuranceTerminationApplication).where(InsuranceTerminationApplication.plan_id==plan.id))
    review=db.scalar(select(InsuranceTerminationReview).where(InsuranceTerminationReview.plan_id==plan.id))
    consent=db.scalar(select(InsuranceTerminationConsent).where(InsuranceTerminationConsent.plan_id==plan.id))
    issued=db.scalar(select(InsuranceResult).join(InsuranceSubmission,InsuranceSubmission.id==InsuranceResult.submission_id).where(InsuranceResult.case_id==source.id,InsuranceResult.outcome=='issued',InsuranceSubmission.quote_id==quote.id))
    if (plan.case_id!=source.id or quote.case_id!=source.id or plan.external_result!='terminated' or not application or not review or review.decision!='approved'
        or review.actor_id==plan.actor_id or not consent or consent.digest!=plan.digest or not issued or not issued.observation_id
        or db.scalar(select(InsuranceTerminationCancellation.id).where(InsuranceTerminationCancellation.plan_id==plan.id))):
        raise HTTPException(409,'保险基准失效须有同原报价的实际出保、独立批准、匹配摘要客户同意及已执行终止；申请或退款不等于终止')
    expected=flow.request_digest('insurance_termination',{'quote_id':quote.id,'evidence_id':plan.evidence_id,'reason':plan.reason,'retained_cents':plan.retained_cents,'external_result':plan.external_result,'returns':plan.returns})
    if expected!=plan.digest:raise HTTPException(409,'原保险终止方案摘要不完整，不能推断基准失效')
    original=_one(db,VehicleObservation,issued.observation_id);vehicle=_one(db,CustomerVehicle,original.vehicle_id)
    if (order.customer_vehicle_id!=vehicle.id or source.customer_id!=vehicle.customer_id or order.vin!=vehicle.vin or original.kind!='insurance'
        or original.valid_until!=quote.end_date or original.observed_date!=issued.business_date or original.evidence_id!=issued.evidence_id or original.actor_id!=issued.actor_id):
        raise HTTPException(409,'保险基准与原客户、VIN、实际出保日期或原凭据不一致')
    for fact in (issued,plan,review,consent,application):
        file=_one(db,FileAsset,fact.evidence_id)
        if file.case_id!=source.id or file.generated:raise HTTPException(409,'保险终止链原件不属于原单或是生成稿')
        require_usable(db,file)
    return vehicle,original,issued,plan,application

def _sync_insurance_basis(db,user,source):
    """No commit. Call after flushing original termination_apply inside its TX."""
    from .insurance_models import InsuranceOrder,InsuranceResult,InsuranceTermination,InsuranceTerminationApplication
    with authority(db,user,READ|{'finance'}):
        if source.kind!='insurance' or source.flow_version!=3:raise HTTPException(422,'仅支持有明确原保单来源的保险明细单')
        order=_one(db,InsuranceOrder,source.id)
        if order.customer_vehicle_id is None and not db.scalar(select(InsuranceResult.id).where(InsuranceResult.case_id==source.id,InsuranceResult.observation_id.is_not(None))):return 0
        plans=list(db.scalars(select(InsuranceTermination).join(InsuranceTerminationApplication,InsuranceTerminationApplication.plan_id==InsuranceTermination.id).where(InsuranceTermination.case_id==source.id,InsuranceTermination.external_result=='terminated').order_by(InsuranceTermination.id)))
        count=0
        for plan in plans:
            vehicle,original,issued,plan,application=_insurance_source(db,source,plan.id)
            control_vehicle(db,user,vehicle.id)
            # Revalidate after the common vehicle lock. Never acquire source Case.
            vehicle,original,issued,plan,application=_insurance_source(db,source,plan.id)
            previous=db.scalar(select(InsuranceBasisInvalidation).where(InsuranceBasisInvalidation.observation_id==original.id))
            if previous:continue
            item=InsuranceBasisInvalidation(source_case_id=source.id,vehicle_id=vehicle.id,observation_id=original.id,result_id=issued.id,plan_id=plan.id,application_id=application.id,evidence_id=application.evidence_id,actor_id=user.id)
            db.add(item);db.flush();_invalidate(db,user,vehicle.id,original,insurance_id=item.id);count+=1
        return count

def sync_insurance_basis(db,user,source):
    """Authorized original insurance command; no commit or reverse Case lock."""
    if not flow.can_read(db,user,source):raise HTTPException(404,'无权核对保险原单来源')
    return _sync_insurance_basis(db,user,source)


def sync_vehicle_insurance_bases(db,user,vehicle):
    """Check pre-integration actual terminations under the vehicle control lock.

    Care staff see only their authorized vehicle's effective basis. This internal
    projection validates original insurance facts without granting file/finance
    access or executing a termination. Malformed source chains fail closed.
    """
    from .insurance_models import InsuranceOrder,InsuranceTermination,InsuranceTerminationApplication
    control_vehicle(db,user,vehicle.id)
    ids=list(db.scalars(select(InsuranceOrder.id).join(InsuranceTermination,InsuranceTermination.case_id==InsuranceOrder.id)
        .join(InsuranceTerminationApplication,InsuranceTerminationApplication.plan_id==InsuranceTermination.id)
        .where(InsuranceOrder.customer_vehicle_id==vehicle.id,InsuranceTermination.external_result=='terminated').distinct().order_by(InsuranceOrder.id)))
    return sum(_sync_insurance_basis(db,user,_one(db,Case,key)) for key in ids)


def reminder_epoch(db):
    # Both hold/release and effective changes wake an otherwise unchanged daily tick.
    from .insurance_models import InsuranceTerminationApplication
    return ':'.join(str(db.scalar(select(func.max(model.id))) or 0) for model in (CorrectionEvent,InsuranceBasisInvalidation,InsuranceTerminationApplication))

def generation_receipt_exists(db,key):
    """Worker skips its unchanged epoch using this domain's receipt table."""
    return db.scalar(select(CorrectionReceipt.id).where(CorrectionReceipt.request_key==key)) is not None

def describe_reminder_basis(db,row):
    c=db.scalar(select(CareCase).where(CareCase.case_id==row.id))
    if not c or not c.vehicle_id or not c.rule_id:return {'status':'not_rule_based','pending_correction_ids':[]}
    invalid=_rows(db,ReminderInvalidation,case_id=row.id)
    holds=[r.case_id for r in _pending(db,c.vehicle_id) if c.subtype in AFFECTED[_one(db,VehicleObservation,r.observation_id).kind]]
    replacements=_rows(db,ReminderReplacement,previous_case_id=row.id)
    return {'status':'invalidated' if invalid else 'pending_review' if holds else 'effective','pending_correction_ids':holds,
        'invalidations':[{'id':i.id,'observation_id':i.observation_id,'source_key':i.source_key,'closed_open_task':i.closed_open_task} for i in invalid],
        'replacement_case_ids':[r.replacement_case_id for r in replacements],
        'basis':plain(db.scalar(select(ReminderBasis).where(ReminderBasis.case_id==row.id))) if db.scalar(select(ReminderBasis.case_id).where(ReminderBasis.case_id==row.id)) else None}

def guard_reminder_action(db,user,row,action,values=None):
    value=describe_reminder_basis(db,row);values=values or {}
    if value['status'] in {'invalidated','pending_review'} and action not in {'handoff','cancel'} and not(action=='start' and value['status']=='pending_review') and not(action=='followup' and values.get('channel')=='internal'):
        raise HTTPException(409,'原提醒基准正在复核或已失效；请先核对，不能继续外联或按旧期限结案，可保留内部核对、转交或取消')
    if action=='close' and values.get('result')=='renewed':
        c=db.scalar(select(CareCase).where(CareCase.case_id==row.id))
        if not c or c.subtype!='renewal':return
        effective=effective_observations(db,c.vehicle_id);base=next((o for o in effective if o['id']==c.baseline_observation_id),None)
        if not any(o['kind']=='insurance' and o['valid_until'] and o['valid_until']>today().isoformat() and o['id']!=c.baseline_observation_id and (not base or o['valid_until']>base['valid_until']) for o in effective):
            raise HTTPException(409,'没有新的有效保险来源，不能用失效或被纠正的旧保期标记续保完成')

def lock_reminder_vehicle(db,user,case_id):
    c=db.scalar(select(CareCase).where(CareCase.case_id==case_id))
    if c and c.vehicle_id:
        vehicle=control_vehicle(db,user,c.vehicle_id)
        if c.rule_id:sync_vehicle_insurance_bases(db,user,vehicle)
    return c

def _candidate(db,vehicle,rule,as_of):
    if any(rule.kind in AFFECTED[_one(db,VehicleObservation,r.observation_id).kind] for r in _pending(db,vehicle.id)):return None
    observations=effective_observations(db,vehicle.id)
    if rule.kind=='first_service' and any(o['kind']=='first_service' for o in observations):return None
    kinds={'first_service':{'delivery'},'maintenance':{'delivery','maintenance','first_service'},'warranty':{'warranty'},'renewal':{'insurance'}}[rule.kind]
    baselines=[o for o in observations if o['kind'] in kinds]
    if not baselines:return None
    baseline=baselines[-1];measured=[o for o in observations if o['odometer_measured'] and o['odometer_km'] is not None];current=measured[-1] if measured else None
    if rule.kind in {'warranty','renewal'}:
        target=date.fromisoformat(baseline['valid_until']) if baseline['valid_until'] else None;triggered=target and as_of>=target-timedelta(days=rule.lead_days)
    else:
        target=date.fromisoformat(baseline['observed_date'])+timedelta(days=rule.interval_days) if rule.interval_days else None
        triggered=(target and as_of>=target-timedelta(days=rule.lead_days)) or (rule.interval_km and current and baseline['odometer_km'] is not None and current['odometer_km']>=baseline['odometer_km']+rule.interval_km-rule.lead_km)
    return (baseline,current,target) if triggered else None

def _cycle_key(vehicle,rule,baseline):return f'{vehicle.store_id}:{vehicle.id}:{rule.kind}:observation:{baseline["id"]}'

def generate_reminders(db,user,key,automatic=False):
    def apply():
        sid=single_store(db);created=[];skipped=[]
        vehicles=list(db.scalars(select(CustomerVehicle).where(CustomerVehicle.active.is_(True)).order_by(CustomerVehicle.id).limit(501)))
        if len(vehicles)>500:raise HTTPException(413,'单次提醒检查最多500台客户车辆')
        rules=list(db.scalars(select(ReminderRule).where(ReminderRule.active.is_(True)).order_by(ReminderRule.id)))
        for initial in vehicles:
            vehicle=control_vehicle(db,user,initial.id)
            sync_vehicle_insurance_bases(db,user,vehicle)
            for rule in rules:
                candidate=_candidate(db,vehicle,rule,today())
                if not candidate:continue
                baseline,current,target=candidate;cycle=_cycle_key(vehicle,rule,baseline)
                old=list(db.scalars(select(CareCase).where(CareCase.vehicle_id==vehicle.id,CareCase.subtype==rule.kind,CareCase.rule_id.is_not(None))))
                # Correcting a value does not create another real maintenance or
                # insurance cycle. Completed/manually cancelled outreach stays done.
                old=[c for c in old if c.baseline_observation_id==baseline['id'] or (rule.kind in {'renewal','warranty'} and c.baseline_observation_id and _effective(db,c.baseline_observation_id)['valid_until']==baseline['valid_until'])]
                eligible=[];stop=False
                for c in old:
                    row=_one(db,Case,c.case_id);invalid=_rows(db,ReminderInvalidation,case_id=c.case_id)
                    if row.state in {'pending','working'} or row.state=='completed' or not any(i.closed_open_task for i in invalid):stop=True;break
                    eligible.append(c.case_id)
                if stop:continue
                assignee=db.scalar(select(User).where(User.id==rule.assignee_id));approver=db.scalar(select(User).where(User.id==rule.approved_by))
                if role_for_store(db,assignee,sid) not in care.TYPE_ROLES[rule.kind] or role_for_store(db,approver,sid) not in MANAGE:
                    skipped.append({'rule_id':rule.id,'reason':'本店规则经办或批准岗位已变化，请主管复核规则'});continue
                version_token=digest([baseline['id'],baseline['effect_id'],current['id'] if current else None,current['effect_id'] if current else None,eligible])[:30]
                reminder_key=f'oc:{sid}:{vehicle.id}:{rule.kind}:{version_token}'
                if db.scalar(select(CareCase.case_id).where(CareCase.reminder_key==reminder_key)):continue
                actor=project_user(approver,role_for_store(db,approver,sid)) if automatic else user
                current_label=f"最近实际观察 {current['observed_date']}、{current['odometer_km']} 公里。" if current else '尚无独立实际里程记录；不根据保险办理推算里程。'
                values={'customer_id':vehicle.customer_id,'vehicle_id':vehicle.id,'subtype':rule.kind,'topic':rule.name,'description':f"有效来源：{baseline['source_reference']}；原观察 {baseline['id']}。"+current_label+(f'参考到期日 {target.isoformat()}。' if target else ''),'location':'','priority':'normal','assignee_id':rule.assignee_id,'due_date':today()}
                row,c=care._new_care(db,actor,sid,values,{'reminder_key':reminder_key,'rule_id':rule.id,'rule_version':rule.version,'baseline_observation_id':baseline['id'],'generation_mode':'rule_worker' if automatic else 'rule_requested','rule_approved_by':rule.approved_by})
                snapshot={'baseline':baseline,'current':current,'rule_id':rule.id,'rule_version':rule.version,'triggered_on':today().isoformat(),
                    'rule':{k:getattr(rule,k) for k in ('kind','name','interval_days','interval_km','lead_days','lead_km','assignee_id','approved_by')}}
                db.add(ReminderBasis(case_id=row.id,vehicle_id=vehicle.id,baseline_id=baseline['id'],current_id=current['id'] if current else None,
                    baseline_effect_id=baseline['effect_id'],current_effect_id=current['effect_id'] if current else None,cycle_key=cycle,snapshot=snapshot))
                flow.log_event(db,actor,row,'observation_reminder_basis','冻结本次有效提醒来源',detail={'basis_digest':digest(snapshot),'cycle_key':cycle})
                for previous in eligible:db.add(ReminderReplacement(previous_case_id=previous,replacement_case_id=row.id,actor_id=actor.id))
                created.append({'case_id':row.id,'number':row.number,'subtype':c.subtype})
        db.flush();return {'created':created,'skipped':skipped,'as_of':today().isoformat(),'automatic':automatic,'notice':'只生成当前有效基准的内部任务；没有发送客户消息，也没有新增保养或里程事实'}
    return _execute(db,user,key,'generate',{'day':today().isoformat(),'automatic':automatic},apply,care.OPS)
