"""Explicit customer service commands; reminders create tasks, never messages or invoices."""
from contextlib import contextmanager
from datetime import date,timedelta
import hashlib
import json
import re
import uuid
from fastapi import HTTPException
from sqlalchemy import select,or_,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow,SessionLocal
from .models import User,Store,Vehicle
from .flow_models import Customer,Case,Task,FileAsset
from .group_models import GroupIdentity,GroupIdentityLink,GroupEvent
from .customer_service_models import (CustomerVehicle,VehicleObservation,CareCase,CareRecord,
    ReminderRule,ServiceHistoryLink,HistoryGrant,CareReceipt)
from .tenancy import single_store,role_for_store,set_scope,project_user
from .services import plain,audit
from .group_service import authority as group_authority
from . import flow_engine as eng
from .file_security import require_usable
from .flow_documents import can_file

READ={'admin','manager','auditor','service','sales','reception','customer_service'}
WRITE=READ-{'auditor'}
MANAGE={'admin','manager'}
OPS=MANAGE|{'service','customer_service'}
LABELS={'questionnaire':'客户问卷','consultation':'客户咨询','complaint':'客户投诉','rescue':'客户救援',
    'sales_callback':'销售回访','repair_callback':'维修回访','first_service':'首保提醒','maintenance':'保养提醒','warranty':'保修到期提醒','renewal':'续保跟进'}
OBS_LABELS={'delivery':'交付登记','odometer':'里程登记','maintenance':'保养完成','first_service':'首保完成','insurance':'保险期限','warranty':'保修期限'}
TYPE_ROLES={kind:(WRITE if kind in {'questionnaire','consultation','sales_callback'} else OPS) for kind in LABELS}
STATUS={'pending':'待接手','working':'跟进中','completed':'已结案','cancelled':'已取消'}
RESULTS={'resolved':'已解决','appointment':'已约定后续办理','declined':'客户不需要','no_response':'多次联系未回应','renewed':'续保已完成'}


@contextmanager
def authority(db,user,roles=READ):
    with group_authority(db,user,roles) as sid:
        old=db.info.get('_care_authority');db.info['_care_authority']=(user.id,sid)
        try:yield sid
        finally:
            if old is None:db.info.pop('_care_authority',None)
            else:db.info['_care_authority']=old


@contextmanager
def _history_scope(db,sid):
    """Read-only scope, used only after a matched vehicle-pair grant is checked."""
    if not db.info.get('_care_authority'):raise HTTPException(403,'没有服务历史读取权限')
    previous={key:db.info.get(key) for key in ('store_scope','write_store')}
    with db.no_autoflush:
        set_scope(db,[sid],None)
        try:yield
        finally:
            for key,value in previous.items():
                if value is None:db.info.pop(key,None)
                else:db.info[key]=value


def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'当前门店记录不存在')
    return row


def _customer(db,user,key):
    row=_one(db,Customer,key)
    if user.role in {'sales','reception'} and row.owner_id!=user.id:
        raise HTTPException(404,'客户不存在或不由当前员工负责')
    return row


def _vehicle(db,user,key,active=True):
    row=db.scalar(select(CustomerVehicle).where(CustomerVehicle.id==key).with_for_update())
    if not row:raise HTTPException(404,'当前门店客户车辆不存在')
    _customer(db,user,row.customer_id)
    if active and not row.active:raise HTTPException(409,'客户车辆关系已停用')
    return row


def _version(row,value):
    if row.version!=value:raise HTTPException(409,'记录已变化，请刷新核对，不能覆盖他人的办理结果')


def _execute(db,user,key,action,payload,operation,roles=WRITE):
    with authority(db,user,roles) as sid:
        digest=hashlib.sha256(json.dumps([action,payload],sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
        try:
            old=db.scalar(select(CareReceipt).where(CareReceipt.request_key==key))
            if old:
                if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'请求编号已用于其他操作或内容')
                if old.result.get('case'):_care(db,user,old.result['case']['id'])
                if old.result.get('vehicle'):_vehicle(db,user,old.result['vehicle']['id'],False)
                return old.result
            result=operation(sid)
            db.add(CareReceipt(request_key=key,actor_id=user.id,digest=digest,result=result));db.commit()
            return result
        except (IntegrityError,OperationalError,StaleDataError) as exc:
            db.rollback();raise HTTPException(409,'资料重复或有同时办理；本次未保存，请刷新核对并保留请求编号') from exc
        except Exception:
            db.rollback();raise
        finally:db.info.pop('_observation_vehicle_locks',None)


def _vehicle_info(db,row):
    customer=_one(db,Customer,row.customer_id)
    from .observation_corrections_service import effective_vehicle_values
    result=plain(row);result.update(customer_name=customer.name,customer_phone=customer.phone,contact_allowed=customer.contact_allowed,**effective_vehicle_values(db,row))
    return result


def vehicle_create(db,user,key,v):
    def op(sid):
        customer=_customer(db,user,v['customer_id'])
        link=db.scalar(select(GroupIdentityLink).where(GroupIdentityLink.local_kind=='customer',GroupIdentityLink.local_id==customer.id))
        identity_id=v.get('customer_identity_id')
        if link:
            if identity_id and identity_id!=link.identity_id:raise HTTPException(409,'本店客户已关联其他身份，不能覆盖合并')
            identity_id=link.identity_id
        else:
            phone=re.sub(r'[\s()+-]','',customer.phone)
            if identity_id:
                identity=db.scalar(select(GroupIdentity).where(GroupIdentity.id==identity_id,GroupIdentity.kind=='customer'))
                if not identity or identity.name!=customer.name or (identity.search_key and phone and identity.search_key!=phone):
                    raise HTTPException(409,'客户身份资料不一致，不能按电话或姓名猜测合并')
            else:
                identity=GroupIdentity(kind='customer',name=customer.name,canonical_key=uuid.uuid4().hex,search_key=phone,created_by=user.id)
                db.add(identity);db.flush();identity_id=identity.id
            db.add(GroupIdentityLink(identity_id=identity_id,local_kind='customer',local_id=customer.id,confirmed_by=user.id))
            db.add(GroupEvent(actor_id=user.id,action='care_identity_confirm',detail={'identity_id':identity_id,'local_id':customer.id,'source':v['source_reference']}))
        vehicle_identity=db.scalar(select(GroupIdentity).where(GroupIdentity.kind=='vehicle',GroupIdentity.canonical_key==v['vin']))
        if not vehicle_identity:
            vehicle_identity=GroupIdentity(kind='vehicle',name=v['model_name'],canonical_key=v['vin'],search_key=v['vin'],created_by=user.id)
            db.add(vehicle_identity);db.flush()
        row=CustomerVehicle(customer_id=customer.id,customer_identity_id=identity_id,vehicle_identity_id=vehicle_identity.id,
            vin=v['vin'],plate=v['plate'],model_name=v['model_name'],identity_source=v['source_reference'],created_by=user.id)
        db.add(row);db.flush();audit(db,user.id,'care_vehicle_create','customer_vehicle',row.id,reason='人工核对客户及 VIN 关系')
        return {'vehicle':_vehicle_info(db,row)}
    return _execute(db,user,key,'vehicle_create',v,op)


def vehicle_update(db,user,key,row_id,version,v):
    def op(sid):
        row=_vehicle(db,user,row_id,False);_version(row,version)
        if not v['active'] and db.scalar(select(Case.id).join(CareCase,CareCase.case_id==Case.id).where(CareCase.vehicle_id==row.id,Case.state.in_(['pending','working'])).limit(1)):
            raise HTTPException(409,'仍有未结束服务任务，先转交或取消后再停用车辆关系')
        row.plate=v['plate'];row.model_name=v['model_name'];row.active=v['active'];row.updated_at=utcnow();db.flush()
        audit(db,user.id,'care_vehicle_update','customer_vehicle',row.id,reason=v['reason'])
        return {'vehicle':_vehicle_info(db,row)}
    return _execute(db,user,key,'vehicle_update',{'id':row_id,'version':version,**v},op)


def observe(db,user,key,vehicle_id,version,v):
    def op(sid):
        from .observation_corrections_service import control_vehicle,guard_observation_append
        vehicle=control_vehicle(db,user,vehicle_id,version,active=True);guard_observation_append(db,user,vehicle,v)
        if v['evidence_id']:
            asset=_one(db,FileAsset,v['evidence_id']);case=eng.get_case(db,user,asset.case_id)
            if case.customer_id!=vehicle.customer_id or not can_file(user,case,asset):raise HTTPException(403,'凭据不属于该客户可见的本店业务')
            require_usable(db,asset)
        row=VehicleObservation(vehicle_id=vehicle.id,actor_id=user.id,**{k:value for k,value in v.items() if k!='confirmed'})
        db.add(row);db.flush()
        audit(db,user.id,'care_observe','customer_vehicle',vehicle.id,reason=OBS_LABELS[v['kind']],after={'observation_id':row.id,'source':row.source_reference})
        return {'vehicle':_vehicle_info(db,vehicle),'observation':plain(row)}
    return _execute(db,user,key,'observe',{'id':vehicle_id,'version':version,**v},op)


def can_read_case(db,user,row):
    if user.role not in READ or getattr(user,'_aggregate_scope',False):return False
    if user.role in {'sales','reception'}:
        return row.owner_id==user.id or row.created_by==user.id or db.scalar(select(Task.id).where(Task.case_id==row.id,Task.assignee_id==user.id,Task.status=='open')) is not None
    return True


def _care(db,user,key,*,nowait=False):
    row=db.scalar(select(Case).where(Case.id==key,Case.kind=='customer_care',Case.flow_version==2).with_for_update(nowait=nowait))
    if not row or not can_read_case(db,user,row):raise HTTPException(404,'客户服务单不存在或无权查看')
    care=db.scalar(select(CareCase).where(CareCase.case_id==row.id))
    if not care:raise HTTPException(409,'客户服务记录不完整，请联系管理员核对')
    return row,care


def _assignee(db,user_id,sid,subtype):
    user=db.scalar(select(User).where(User.id==user_id))
    if role_for_store(db,user,sid) not in TYPE_ROLES[subtype]:raise HTTPException(422,'经办人不是本店启用且匹配此服务的岗位')
    return user


def _record(db,user,row,action,note,details=None):
    record=CareRecord(case_id=row.id,actor_id=user.id,action=action,note=note,details=details or {});db.add(record)
    label={'create':'建立客户服务','start':'接手客户服务','followup':'记录跟进','handoff':'转交客户服务','close':'客户服务结案','cancel':'取消客户服务'}[action]
    if action=='create' and details and details.get('generation_mode')=='rule_worker':label='系统按规则自动生成内部任务'
    elif action=='create' and details and details.get('generation_mode')=='rule_requested':label='员工触发规则生成内部任务'
    eng.log_event(db,user,row,'care_'+action,label,detail={'action':action,**(details or {})})
    return record


def _new_care(db,user,sid,v,reminder=None):
    customer=_customer(db,user,v['customer_id'])
    from .observation_corrections_service import control_vehicle
    vehicle=control_vehicle(db,user,v['vehicle_id'],active=True) if v.get('vehicle_id') else None
    if vehicle and vehicle.customer_id!=customer.id:raise HTTPException(422,'车辆关系不属于当前客户')
    subtype=v['subtype']
    if user.role not in TYPE_ROLES[subtype]:raise HTTPException(403,'当前岗位不能建立此类客户服务')
    assignee=_assignee(db,v['assignee_id'],sid,subtype)
    if user.role in {'sales','reception'} and assignee.id!=user.id:raise HTTPException(403,'销售与前台只能建立自己办理的客户服务，转交由主管处理')
    if not today()<=v['due_date']<=today()+timedelta(days=365):raise HTTPException(422,'办理期限须从今天起且不超过一年')
    if subtype=='rescue' and not v.get('location'):raise HTTPException(422,'救援须记录客户提供的位置及需要的协助')
    if subtype in {'sales_callback','repair_callback'}:
        # Callback staff may select this customer's completed source number without
        # gaining access to its prices, files or unrestricted business detail.
        source=db.scalar(select(Case).where(Case.id==v.get('source_case_id'),Case.customer_id==customer.id)) if v.get('source_case_id') else None
        if not source or source.customer_id!=customer.id or source.kind!=('order' if subtype=='sales_callback' else 'repair') or source.state not in {'delivered','completed','credit_open'}:
            raise HTTPException(422,'回访须关联该客户已交付或完工的本店原单')
        if vehicle and source.vehicle_id and _one(db,Vehicle,source.vehicle_id).vin!=vehicle.vin:
            raise HTTPException(422,'原单 VIN 与所选客户车辆不一致')
    elif v.get('source_case_id'):raise HTTPException(422,'只有销售或维修回访可以在此关联原单')
    row=Case(kind='customer_care',flow_version=2,state='pending',number='CC'+uuid.uuid4().hex[:18].upper(),
        title=LABELS[subtype],owner_id=assignee.id,created_by=user.id,customer_id=customer.id,business_date=today(),due_date=v['due_date'],data={'subtype':subtype,**({'questionnaire_version':1} if subtype=='questionnaire' else {})})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row)
    care=CareCase(case_id=row.id,subtype=subtype,vehicle_id=vehicle.id if vehicle else None,source_case_id=v.get('source_case_id'),
        topic=v['topic'],description=v['description'],location=v.get('location',''),priority=v.get('priority','normal'),**(reminder or {}))
    db.add(care);db.flush()
    from .questionnaire_service import bind
    questionnaire=bind(db,user,row,care)
    eng.ensure_task(db,row,'care_handle',LABELS[subtype]+'：接手并记录办理','customer_service',assignee=assignee.id,due=row.due_date)
    _record(db,user,row,'create',('系统按规则自动生成；创建者表示规则批准责任归属，不代表员工点击或已联系客户。' if care.generation_mode=='rule_worker' else '员工触发规则生成内部任务，尚未联系客户。') if reminder else '员工登记客户服务',
        {'automatic':care.generation_mode=='rule_worker','generation_mode':care.generation_mode,'rule_id':care.rule_id,'rule_version':care.rule_version,'rule_approved_by':care.rule_approved_by,**({'questionnaire_binding_id':questionnaire.id,'questionnaire_version':questionnaire.number,'questionnaire_schema_digest':questionnaire.schema_digest} if questionnaire else {})})
    db.flush();return row,care


def case_info(db,user,row,care,detail=True):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='care_handle'))
    customer=_one(db,Customer,row.customer_id)
    result={'id':row.id,'number':row.number,'version':row.version,'subtype':care.subtype,'subtype_label':LABELS[care.subtype],
        'state':row.state,'state_label':STATUS[row.state],'customer_id':customer.id,'customer_name':customer.name,
        'vehicle_id':care.vehicle_id,'topic':care.topic,'priority':care.priority,'due_date':row.due_date.isoformat(),
        'overdue':row.state in {'pending','working'} and row.due_date<today(),'assignee_id':task.assignee_id,
        'assignee_name':_one(db,User,task.assignee_id).display_name,'result':care.result,'result_label':RESULTS.get(care.result,''),
        'source_case_id':care.source_case_id,'rule_id':care.rule_id,'actions':[]}
    result['generation_mode']=care.generation_mode;result['rule_approved_by']=care.rule_approved_by
    if row.state in {'pending','working'}:
        own=user.id==task.assignee_id or user.role in MANAGE
        if own and user.role in TYPE_ROLES[care.subtype]:
            result['actions']=['start'] if row.state=='pending' else ['followup','close']
            result['actions']+=['cancel']
        if user.role in MANAGE or own and user.role in OPS:result['actions']+=['handoff']
    from .observation_corrections_service import describe_reminder_basis
    result['reminder_basis']=describe_reminder_basis(db,row)
    if result['reminder_basis']['status'] in {'pending_review','invalidated'}:
        result['actions']=[a for a in result['actions'] if a!='close']
        result['followup_channels']=['internal']
    else:result['followup_channels']=['internal','in_person','phone']
    if detail:
        if care.subtype=='questionnaire':
            from .questionnaire_service import info
            result['questionnaire']=info(db,row)
        result.update(description=care.description,location=care.location,customer_phone=customer.phone,contact_allowed=customer.contact_allowed,
            records=[plain(r) for r in db.scalars(select(CareRecord).where(CareRecord.case_id==row.id).order_by(CareRecord.id))])
    return result


def case_create(db,user,key,v):
    def op(sid):
        row,care=_new_care(db,user,sid,v);return {'case':case_info(db,user,row,care)}
    return _execute(db,user,key,'care_create',v,op)


def case_action(db,user,key,case_id,version,action,v):
    # Preserve the exact legacy receipt digest when no new answers field was sent.
    if v.get('answers') is None:v={k:value for k,value in v.items() if k!='answers'}
    def op(sid):
        details=v.copy();questionnaire=None
        from .observation_corrections_service import lock_reminder_vehicle,guard_reminder_action
        lock_reminder_vehicle(db,user,case_id)
        row,care=_care(db,user,case_id,nowait=True);_version(row,version)
        guard_reminder_action(db,user,row,action,v)
        available=case_info(db,user,row,care,False)['actions']
        if action not in available:raise HTTPException(409,'当前岗位、责任人或办理状态不允许此动作')
        task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='care_handle'))
        if action=='start':row.state='working';note='经办人已接手'
        elif action=='followup':
            customer=_one(db,Customer,row.customer_id)
            if v['channel']=='phone' and (not customer.contact_allowed or not customer.phone):raise HTTPException(409,'客户未允许后续联系或没有电话，请使用已有当面反馈或内部跟进')
            if v['next_due_date']:
                if not today()<=v['next_due_date']<=today()+timedelta(days=365):raise HTTPException(422,'下一次办理日期应从今天起且不超过一年')
                row.due_date=v['next_due_date'];task.due_date=v['next_due_date']
            note=v['note']
        elif action=='handoff':
            target=_assignee(db,v['assignee_id'],sid,care.subtype)
            if not today()<=v['due_date']<=today()+timedelta(days=365):raise HTTPException(422,'交接期限应从今天起且不超过一年')
            v['from_assignee_id']=task.assignee_id;v['previous_due_date']=row.due_date.isoformat();v['was_overdue']=row.due_date<today()
            task.assignee_id=target.id;row.owner_id=target.id;task.due_date=v['due_date'];row.due_date=v['due_date'];note=v['reason']
        elif action=='cancel':
            row.state='cancelled';eng.finish_task(db,row,'care_handle',user,'cancelled');row.completed_date=today();note=v['reason']
        elif action=='close':
            from .questionnaire_service import normalize_close
            details,questionnaire=normalize_close(db,row,care,v)
            if v['result']=='renewed':
                if care.subtype!='renewal' or not care.vehicle_id:raise HTTPException(422,'续保完成只适用于车辆续保任务')
                # The effective-source guard above checked the renewed policy;
                # raw historical observations must not override that decision.
            care.result=v['result'];row.state='completed';row.completed_date=today();eng.finish_task(db,row,'care_handle',user);note=v['note']
        else:raise HTTPException(404,'客户服务动作不存在')
        # Handoff adds attributable previous values to v; keep those original facts.
        if action!='close':details=v
        row.updated_at=utcnow();record=_record(db,user,row,action,note,{k:(value.isoformat() if isinstance(value,date) else value) for k,value in details.items() if k not in {'note','reason'}})
        from .questionnaire_service import record_response
        record_response(db,user,questionnaire,record,details)
        db.flush();return {'case':case_info(db,user,row,care)}
    return _execute(db,user,key,'care_'+action,{'case_id':case_id,'version':version,**v},op)


def rule_save(db,user,key,v,rule_id=None,version=None):
    def op(sid):
        _assignee(db,v['assignee_id'],sid,v['kind'])
        if v['kind'] in {'first_service','maintenance'}:
            if not v['interval_days'] and not v['interval_km']:raise HTTPException(422,'首保或保养规则至少填写日期间隔或里程间隔')
            if v['interval_days'] and v['lead_days']>=v['interval_days'] or v['interval_km'] and v['lead_km']>=v['interval_km']:
                raise HTTPException(422,'提前量必须小于对应周期')
        elif v['interval_days'] or v['interval_km'] or v['lead_km']:raise HTTPException(422,'保险和保修按已登记截止日期提醒，只配置提前天数')
        if rule_id:
            row=_one(db,ReminderRule,rule_id);_version(row,version)
            if row.kind!=v['kind']:raise HTTPException(409,'规则类型不能更换，请维护对应规则')
            for name,value in v.items():setattr(row,name,value)
            row.approved_by=user.id
            row.updated_at=utcnow()
        else:row=ReminderRule(created_by=user.id,approved_by=user.id,**v);db.add(row)
        db.flush();audit(db,user.id,'care_rule_save','care_rule',row.id,after={'kind':row.kind,'version':row.version,'active':row.active},reason='配置内部提醒任务')
        return {'rule':plain(row)}
    return _execute(db,user,key,'rule_save',{'id':rule_id,'version':version,**v},op,MANAGE)


def generate_reminders(db,user,key,automatic=False):
    # Original endpoint keeps its immutable pre-integration request receipts.
    # A historical request must never become a fresh check of another cycle.
    with authority(db,user,OPS):
        old=db.scalar(select(CareReceipt).where(CareReceipt.request_key==key))
        if old:
            payload={'day':today().isoformat(),'automatic':automatic}
            expected=hashlib.sha256(json.dumps(['generate_reminders',payload],sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
            if old.actor_id!=user.id or old.digest!=expected:raise HTTPException(409,'原请求编号已用于其他人员、日期或内容，请核对历史回执')
            for item in old.result.get('created',[]):_care(db,user,item['case_id'])
            return old.result
    from .observation_corrections_service import generate_reminders as generate_effective
    return generate_effective(db,user,key,automatic)


def history_link(db,user,key,vehicle_id,v):
    def op(sid):
        vehicle=_vehicle(db,user,vehicle_id);case=eng.get_case(db,user,v['case_id'])
        if case.customer_id!=vehicle.customer_id or case.kind not in {'order','repair','addon','insurance','agency','customer_care'}:
            raise HTTPException(422,'只能关联该客户的本店销售、维修或服务原单')
        if case.vehicle_id:
            stock=_one(db,Vehicle,case.vehicle_id)
            if stock.vin!=vehicle.vin:raise HTTPException(422,'原单 VIN 与客户车辆不一致')
        own=db.scalar(select(CareCase).where(CareCase.case_id==case.id)) if case.kind=='customer_care' else None
        if own and own.vehicle_id!=vehicle.id:raise HTTPException(422,'服务原单不属于该客户车辆')
        row=ServiceHistoryLink(vehicle_id=vehicle.id,case_id=case.id,summary=v['summary'],source_reference=v['source_reference'],confirmed_by=user.id)
        db.add(row);db.flush();audit(db,user.id,'care_history_link','customer_vehicle',vehicle.id,reason='核对客户及车辆后关联最小服务摘要')
        return {'link_id':row.id,'vehicle':_vehicle_info(db,vehicle)}
    return _execute(db,user,key,'history_link',{'vehicle_id':vehicle_id,**v},op)


def grant_history(db,user,key,v):
    def op(sid):
        source=_vehicle(db,user,v['from_vehicle_id'])
        if v['to_store_id']==sid or not db.scalar(select(Store.id).where(Store.id==v['to_store_id'],Store.active.is_(True))):raise HTTPException(422,'请选择另一家启用门店')
        if not today()<=v['valid_until']<=today()+timedelta(days=365):raise HTTPException(422,'授权期限须从今天起且不超过一年')
        with _history_scope(db,v['to_store_id']):
            target=db.scalar(select(CustomerVehicle).where(CustomerVehicle.id==v['to_vehicle_id'],CustomerVehicle.active.is_(True)))
            if not target or target.customer_identity_id!=source.customer_identity_id or target.vehicle_identity_id!=source.vehicle_identity_id:
                raise HTTPException(422,'对方门店客户车辆关系不匹配；相同 VIN 不能代替同一客户身份确认')
        existing=db.scalar(select(HistoryGrant).where(HistoryGrant.from_vehicle_id==source.id,HistoryGrant.to_vehicle_id==target.id,HistoryGrant.status=='active').with_for_update())
        if existing and existing.valid_until>=today():raise HTTPException(409,'此客户车辆已有有效授权，请先撤销再变更范围')
        if existing:
            existing.status='revoked';existing.active_pair=None;existing.revoked_by=user.id;existing.revoke_reason='已过期，由主管重新授权';db.flush()
        row=HistoryGrant(from_store_id=sid,to_store_id=v['to_store_id'],from_vehicle_id=source.id,to_vehicle_id=target.id,
            customer_identity_id=source.customer_identity_id,vehicle_identity_id=source.vehicle_identity_id,valid_until=v['valid_until'],source_reference=v['source_reference'],granted_by=user.id,active_pair=f'{source.id}:{target.id}')
        db.add(row);db.flush();audit(db,user.id,'care_history_grant','care_grant',row.id,reason=v['source_reference'])
        return {'grant':plain(row)}
    return _execute(db,user,key,'grant_history',v,op,MANAGE)


def revoke_grant(db,user,key,grant_id,version,reason):
    def op(sid):
        row=db.scalar(select(HistoryGrant).where(HistoryGrant.id==grant_id,or_(HistoryGrant.from_store_id==sid,HistoryGrant.to_store_id==sid)).with_for_update())
        if not row:raise HTTPException(404,'授权不存在或当前门店不是授权双方')
        _version(row,version)
        if row.status!='active':raise HTTPException(409,'此授权已经撤销')
        row.status='revoked';row.active_pair=None;row.revoked_by=user.id;row.revoke_reason=reason;db.flush()
        audit(db,user.id,'care_history_revoke','care_grant',row.id,reason=reason)
        return {'grant':plain(row)}
    return _execute(db,user,key,'revoke_history',{'id':grant_id,'version':version,'reason':reason},op,MANAGE)


def _history_rows(db,vehicle_id,store_name,external=False):
    result=[]
    for link in db.scalars(select(ServiceHistoryLink).where(ServiceHistoryLink.vehicle_id==vehicle_id).order_by(ServiceHistoryLink.id.desc()).limit(100)):
        case=db.scalar(select(Case).where(Case.id==link.case_id))
        if case:
            result.append({'number':case.number,'kind':case.kind,'business_date':case.business_date.isoformat(),
                'completed_date':case.completed_date.isoformat() if case.completed_date else None,'state':case.state,
                'summary':link.summary,'store_name':store_name,'external':external,**({} if external else {'case_id':case.id})})
    return result


def service_history(db,user,vehicle_id):
    with authority(db,user) as sid:
        vehicle=_vehicle(db,user,vehicle_id,False)
        rows=_history_rows(db,vehicle.id,_one(db,Store,sid).name)
        notice='只显示明确关联的服务摘要；跨店授权不开放金额、客户联系资料、原单办理或任何附件'
        if not vehicle.active:return {'items':rows,'notice':notice}
        grants=list(db.scalars(select(HistoryGrant).where(HistoryGrant.to_store_id==sid,HistoryGrant.to_vehicle_id==vehicle.id,
            HistoryGrant.customer_identity_id==vehicle.customer_identity_id,HistoryGrant.vehicle_identity_id==vehicle.vehicle_identity_id,
            HistoryGrant.status=='active',HistoryGrant.valid_until>=today())))
        for grant in grants:
            source_store=db.scalar(select(Store).where(Store.id==grant.from_store_id,Store.active.is_(True)))
            if not source_store:continue
            source_name=source_store.name
            with _history_scope(db,grant.from_store_id):
                source=db.scalar(select(CustomerVehicle).where(CustomerVehicle.id==grant.from_vehicle_id,CustomerVehicle.active.is_(True),
                    CustomerVehicle.customer_identity_id==vehicle.customer_identity_id,CustomerVehicle.vehicle_identity_id==vehicle.vehicle_identity_id))
                if source:rows.extend(_history_rows(db,source.id,source_name,True))
        return {'items':rows,'notice':notice}


def tick_reminders():
    """One bounded external worker tick. Unique reminder keys make repeated ticks safe."""
    result={'stores':0,'created':0,'skipped':0,'errors':[]}
    with SessionLocal() as db:store_ids=list(db.scalars(select(Store.id).where(Store.active.is_(True))))
    for sid in store_ids:
        with SessionLocal() as db:
            set_scope(db,[sid],sid)
            rules=list(db.scalars(select(ReminderRule).where(ReminderRule.active.is_(True)).order_by(ReminderRule.id)))
            if not rules:continue
            last_observation=db.scalar(select(func.max(VehicleObservation.id))) or 0
            from .observation_corrections_service import reminder_epoch,generation_receipt_exists
            fingerprint=[sid,today().isoformat(),last_observation,reminder_epoch(db),[(r.id,r.version,role_for_store(db,db.scalar(select(User).where(User.id==r.assignee_id)),sid),role_for_store(db,db.scalar(select(User).where(User.id==r.approved_by)),sid)) for r in rules]]
            tick_key='tick_'+hashlib.sha256(json.dumps(fingerprint).encode()).hexdigest()
            if generation_receipt_exists(db,tick_key):
                result['stores']+=1;continue
            users=list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.id)))
            approver_ids={r.approved_by for r in rules}
            actor=next((u for u in users if u.id in approver_ids and role_for_store(db,u,sid) in MANAGE),None)
            if actor is None:result['errors'].append({'store_id':sid,'reason':'缺少启用的管理岗位'});continue
            try:
                data=generate_reminders(db,project_user(actor,role_for_store(db,actor,sid)),tick_key,True)
                result['stores']+=1;result['created']+=len(data['created']);result['skipped']+=len(data['skipped'])
            except HTTPException as error:result['errors'].append({'store_id':sid,'status':error.status_code,'reason':error.detail})
    return result
