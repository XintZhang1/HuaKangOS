"""Explicit arrival, resource ownership, verified VIN and internal-only rework."""
import uuid
from datetime import datetime,date,timezone,timedelta
from zoneinfo import ZoneInfo
from .config import settings
from fastapi import HTTPException
from sqlalchemy import select,func,or_,and_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import utcnow,today
from .flow_models import Case,Customer,Task
from .flow_documents import can_file
from .tenancy import single_store
from .master_models import WorkItem
from .customer_service_models import CustomerVehicle
from .repair_models import RepairQuote,RepairLine,RepairSettlement
from . import flow_engine as flow
from .service_intake_models import (ServiceResource,QuickPreset,QuickPresetLine,ServiceAppointment,ArrivalFact,
    RepairVehicleBinding,ReworkRequest,ReworkSourceLine,ReworkLiability,RepairIntake,ResourceUse,IntakeReceipt)

MANAGE={'admin','manager'};FRONT={'admin','service','reception','customer_service'};ADVISE={'admin','service'}
READ=FRONT|MANAGE|{'finance','auditor'}
def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此接待步骤')
def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'当前门店记录不存在')
    return row
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _version(row,version):
    if row.version!=version:raise HTTPException(409,'记录已经变化，请刷新核对后办理')
    row.updated_at=utcnow()
def _utc(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).replace(tzinfo=None)
def _iso(value):return value.isoformat()+'Z' if value else None
def _local_date(value):return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()
def _vehicle(db,user,key):
    row=_one(db,CustomerVehicle,key);customer=_one(db,Customer,row.customer_id)
    if not row.active:raise HTTPException(409,'客户车辆关系已停用')
    if user.role=='reception' and customer.owner_id!=user.id:raise HTTPException(404,'此客户车辆不在本人可读范围')
    return row,customer
def _resource(db,key,active=True):
    row=_one(db,ServiceResource,key)
    if active and not row.active:raise HTTPException(409,'服务工位已停用')
    return row
def _evidence(db,user,row,key):
    asset=flow.file_exists(db,row,key)
    if not can_file(user,row,asset):raise HTTPException(403,'当前岗位不能引用该凭据')
    if asset.generated:raise HTTPException(409,'系统生成文件不代表实际到店或责任批准，请上传本次核验凭据')
    return asset
def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role not in MANAGE):raise HTTPException(409,'步骤待办未开放或已交给其他员工')
def _execute(db,user,key,operation,payload,callback):
    single_store(db);digest=flow.request_digest('intake_'+operation,payload)
    try:
        prior=db.scalar(select(IntakeReceipt).where(IntakeReceipt.request_key==key))
        if prior:
            if prior.actor_id!=user.id or prior.digest!=digest:raise HTTPException(409,'请求编号已用于其他办理，请核对原请求结果')
            return prior.result
        result=callback();db.flush();db.add(IntakeReceipt(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'时段、车辆或业务同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise
def _case(db,user,customer,title,subtype):
    row=Case(number='HKS'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='service_intake',flow_version=2,state='pending',
        title=customer.name+' · '+title,customer_id=customer.id,owner_id=user.id,created_by=user.id,business_date=today(),due_date=today(),data={'subtype':subtype})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);return row
def _slot(db,resource,starts,ends,excluding=None):
    if ends<=starts or ends-starts>timedelta(hours=12):raise HTTPException(422,'预约结束须晚于开始，单次时段最多十二小时')
    live_repairs=select(Case.id).where(Case.state.notin_(['completed','credit_open','cancelled']))
    query=select(ServiceAppointment.id).where(ServiceAppointment.resource_id==resource.id,
        or_(ServiceAppointment.status.in_(['scheduled','arrived']),and_(ServiceAppointment.status=='converted',ServiceAppointment.repair_case_id.in_(live_repairs))),
        ServiceAppointment.starts_at<ends,ServiceAppointment.ends_at>starts)
    if excluding:query=query.where(ServiceAppointment.id!=excluding)
    if db.scalar(query.limit(1)):raise HTTPException(409,'该工位时段已被预约，请选择其他时段或工位')
    resource.updated_at=utcnow();db.flush()
def _preset(db,key,resource=None):
    row=_one(db,QuickPreset,key)
    if not row.active:raise HTTPException(409,'快捷项目预填已停用')
    if resource and (row.profile=='wash')!=(resource.resource_type=='wash'):raise HTTPException(422,'洗车项目需洗车工位，维修快捷项目需维修工位')
    return row
def catalog(db,user):
    _role(user,READ)
    vehicles=[]
    for v in db.scalars(select(CustomerVehicle).where(CustomerVehicle.active==True).order_by(CustomerVehicle.id).limit(1001)):
        c=_one(db,Customer,v.customer_id)
        if user.role=='reception' and c.owner_id!=user.id:continue
        vehicles.append({'id':v.id,'customer_id':c.id,'customer_name':c.name,'customer_phone':c.phone,'plate':v.plate,'vin':v.vin})
    if len(vehicles)>1000:raise HTTPException(422,'客户车辆超过本版选择上限，请按部署规模扩展检索，不返回截断选择')
    resources=[{'id':r.id,'version':r.version,'code':r.code,'name':r.name,'resource_type':r.resource_type,'active':r.active,'in_use':r.active_case_id is not None} for r in _rows(db,ServiceResource)]
    presets=[{'id':p.id,'version':p.version,'code':p.code,'name':p.name,'profile':p.profile,'active':p.active,
        'lines':[{'work_item_id':l.work_item_id,'quantity_milli':l.quantity_milli} for l in _rows(db,QuickPresetLine,preset_id=p.id)]} for p in _rows(db,QuickPreset)]
    return {'vehicles':vehicles,'resources':resources,'presets':presets,
        'appointment_requirements':'预约和现场来访都必须选择真实客户车辆、启用工位及开始和结束时段。没有工位时应等待有工位维护权限的岗位配置或启用；不能改为现场来访绕过工位要求，也不能只补车牌和到店时间就承诺可以办理。'}
def resource_create(db,user,key,v):
    _role(user,MANAGE)
    def run():
        row=ServiceResource(**v);db.add(row);db.flush();return {'id':row.id,'version':row.version,'name':row.name}
    return _execute(db,user,key,'resource_create',v,run)
def sources(db,user,page):
    _role(user,ADVISE|MANAGE)
    query=flow.case_query(user).where(Case.kind=='repair',Case.flow_version.in_([3,4]),Case.data['released_date'].as_string().is_not(None),Case.id.in_(select(RepairSettlement.case_id)))
    total=db.scalar(select(func.count()).select_from(query.subquery()));items=[]
    for row in db.scalars(query.order_by(Case.id.desc()).offset((page-1)*30).limit(30)):
        settlement=db.scalar(select(RepairSettlement).where(RepairSettlement.case_id==row.id));binding=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==row.id))
        items.append({'id':row.id,'version':row.version,'number':row.number,'customer_id':row.customer_id,'title':row.title,'vin':binding.vin if binding else None,
            'binding_customer_vehicle_id':binding.customer_vehicle_id if binding else None,'lines':[{'id':l.id,'name':l.name,'code':l.code,'quantity_milli':l.quantity_milli} for l in _rows(db,RepairLine,quote_id=settlement.quote_id)]})
    return {'items':items,'total':total,'page':page}
def preset_create(db,user,key,v):
    _role(user,MANAGE)
    def run():
        from .master_data import require_active
        if len({l['work_item_id'] for l in v['lines']})!=len(v['lines']):raise HTTPException(422,'快捷组合中相同作业请合并')
        for l in v['lines']:require_active(db,'work_items',l['work_item_id'])
        row=QuickPreset(code=v['code'],name=v['name'],profile=v['profile'],created_by=user.id);db.add(row);db.flush()
        for l in v['lines']:db.add(QuickPresetLine(preset_id=row.id,**l))
        return {'id':row.id,'version':row.version,'name':row.name}
    return _execute(db,user,key,'preset_create',v,run)
def master_active(db,user,kind,key,request_id,version,v):
    _role(user,MANAGE)
    def run():
        row=_one(db,ServiceResource if kind=='resources' else QuickPreset,key);_version(row,version)
        if not v['active']:
            criterion=ServiceAppointment.resource_id==key if kind=='resources' else ServiceAppointment.preset_id==key
            if db.scalar(select(ServiceAppointment.id).where(criterion,ServiceAppointment.status.in_(['scheduled','arrived'])).limit(1)):raise HTTPException(409,'尚有预约或已到店接待，请先处理后停用')
            if kind=='resources':
                if row.active_case_id or db.scalar(select(RepairIntake.case_id).join(Case,Case.id==RepairIntake.case_id).where(RepairIntake.resource_id==key,Case.state.notin_(['cancelled','completed','credit_open'])).limit(1)):
                    raise HTTPException(409,'工位仍有实际占用或待执行维修，不能停用')
        row.active=v['active'];db.flush();return {'id':row.id,'version':row.version,'active':row.active}
    return _execute(db,user,request_id,kind+'_active',{'id':key,'version':version,**v},run)
def _appointment(db,user,key):
    _role(user,READ);a=_one(db,ServiceAppointment,key);return a,flow.get_case(db,user,a.case_id)
def appointment_detail(db,user,key):
    a,row=_appointment(db,user,key);vehicle=_one(db,CustomerVehicle,a.customer_vehicle_id);resource=_resource(db,a.resource_id,False)
    arrival=db.scalar(select(ArrivalFact).where(ArrivalFact.appointment_id==a.id))
    return {'id':a.id,'version':a.version,'case_id':row.id,'number':row.number,'title':row.title,'status':a.status,'mode':a.mode,'problem':a.problem,
        'customer_vehicle_id':vehicle.id,'vin':vehicle.vin,'plate':vehicle.plate,'resource_id':resource.id,'resource_name':resource.name,
        'starts_at':_iso(a.starts_at),'ends_at':_iso(a.ends_at),'preset_id':a.preset_id,'repair_case_id':a.repair_case_id,'arrived_at':_iso(arrival.occurred_at) if arrival else None}
def appointment_create(db,user,key,v):
    _role(user,FRONT)
    def run():
        vehicle,customer=_vehicle(db,user,v['customer_vehicle_id']);resource=_resource(db,v['resource_id']);starts,ends=_utc(v['starts_at']),_utc(v['ends_at'])
        if v['mode']=='appointment' and starts<utcnow():raise HTTPException(422,'预约开始时间不能早于现在；现场来访请使用到店登记')
        if v['mode']=='walk_in' and (starts<utcnow()-timedelta(minutes=15) or starts>utcnow()+timedelta(days=1)):raise HTTPException(422,'现场来访时段须在当前附近或当天排队范围')
        if v.get('preset_id'):_preset(db,v['preset_id'],resource)
        _slot(db,resource,starts,ends);row=_case(db,user,customer,'维修预约' if v['mode']=='appointment' else '现场维修接待','appointment')
        a=ServiceAppointment(case_id=row.id,customer_vehicle_id=vehicle.id,resource_id=resource.id,starts_at=starts,ends_at=ends,
            mode=v['mode'],problem=v['problem'],preset_id=v.get('preset_id'));db.add(a);db.flush();flow.set_data(row,appointment_id=a.id)
        flow.ensure_task(db,row,'intake_arrive','核对客户车辆并记录实际到店','service',due=_local_date(starts))
        flow.log_event(db,user,row,'intake_book','登记预约或现场排队',detail={'starts_at':_iso(starts),'ends_at':_iso(ends),'resource_id':resource.id})
        return appointment_detail(db,user,a.id)
    return _execute(db,user,key,'appointment_create',v,run)
def _bind(db,user,row,vehicle,evidence,reference):
    existing=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==row.id))
    if existing:raise HTTPException(409,'本维修车辆身份已经冻结，不能重新绑定')
    binding=RepairVehicleBinding(case_id=row.id,customer_vehicle_id=vehicle.id,customer_identity_id=vehicle.customer_identity_id,
        vehicle_identity_id=vehicle.vehicle_identity_id,vin=vehicle.vin,evidence_id=evidence,source_reference=reference,reviewed_by=user.id)
    db.add(binding);db.flush()
    # Append at the actual binding transaction. A later master-name correction
    # must not relabel historical material consumption; old bindings stay unknown.
    flow.log_event(db,user,row,'repair_vehicle_model_snapshot','冻结本维修车辆车型来源',detail={
        'schema_version':1,'customer_vehicle_id':vehicle.id,'customer_vehicle_version':vehicle.version,
        'model_name':vehicle.model_name,'vin':vehicle.vin})
    return binding
def _build_repair(db,user,vehicle,problem,due,resource,evidence,profile,appointment=None,rework=None,preset=None):
    customer=_one(db,Customer,vehicle.customer_id)
    row=Case(number='HKR'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='repair',flow_version=4,state='assessment',
        title=customer.name+' · '+('责任返修' if rework else '洗车明细' if profile=='wash' else '维修明细'),customer_id=customer.id,
        owner_id=user.id,created_by=user.id,business_date=today(),due_date=date.fromisoformat(due),data={'plate':vehicle.plate,'problem':problem})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(RepairIntake(case_id=row.id,profile=profile,resource_id=resource.id,appointment_id=appointment.id if appointment else None,
        rework_id=rework.id if rework else None,preset_id=preset.id if preset else None));_bind(db,user,row,vehicle,evidence,'员工现场核对VIN并记录实际到店')
    flow.ensure_task(db,row,'repair_quote','核对本次项目配件并报价','service',assignee=user.id);db.flush()
    if preset:
        from .master_data import require_active
        from .repair_service import _new_quote
        lines=[]
        for l in _rows(db,QuickPresetLine,preset_id=preset.id):
            work=require_active(db,'work_items',l.work_item_id)
            lines.append({'kind':'work','source_id':work.id,'line_key':None,'quantity_milli':l.quantity_milli,'unit_price_cents':work.standard_fee_cents})
        _new_quote(db,user,row,{'purpose':'service','reason':'按主管配置的快捷项目预填；仍须价格审批与客户确认','lines':lines,'discount_cents':0,'retained_amount_cents':None})
    flow.log_event(db,user,row,'intake_convert','从实际接待建立明细工单',detail={'profile':profile});return row
def appointment_action(db,user,key,request_id,version,action,v):
    _role(user,ADVISE if action=='convert' else FRONT|MANAGE)
    def run():
        a,row=_appointment(db,user,key);_version(a,version);row.updated_at=utcnow();resource=_resource(db,a.resource_id,False)
        if action=='reschedule':
            if a.status!='scheduled':raise HTTPException(409,'已到店或结束的预约不能改约')
            starts,ends=_utc(v['starts_at']),_utc(v['ends_at'])
            if starts<utcnow():raise HTTPException(422,'改约时间不能早于现在')
            new=_resource(db,v['resource_id']);_slot(db,new,starts,ends,a.id);resource.updated_at=utcnow()
            if a.preset_id:_preset(db,a.preset_id,new)
            a.resource_id=new.id;a.starts_at=starts;a.ends_at=ends
            flow.ensure_task(db,row,'intake_arrive','按新预约核对实际到店','service',due=_local_date(starts))
        elif action in {'cancel','no_show'}:
            if a.status!='scheduled':raise HTTPException(409,'已记录实际到店或已转工单，不能用预约取消抹除事实')
            if action=='no_show' and utcnow()<a.ends_at:raise HTTPException(409,'预约尚未结束，不能记为未到')
            a.status='cancelled' if action=='cancel' else 'no_show';row.state='cancelled';resource.updated_at=utcnow();flow.close_tasks(db,row,user)
        elif action=='arrive':
            if a.status!='scheduled':raise HTTPException(409,'预约已到店或结束，不能重复登记')
            _task(db,user,row,'intake_arrive');vehicle,_=_vehicle(db,user,a.customer_vehicle_id)
            if v['checked_vin']!=vehicle.vin:raise HTTPException(409,'现场VIN与客户车辆档案不符，不能转本预约')
            _evidence(db,user,row,v['evidence_id'])
            from .gate_attendance import arrive_guard
            arrive_guard(db,vehicle.vin)
            db.add(ArrivalFact(appointment_id=a.id,customer_vehicle_id=vehicle.id,checked_vin=vehicle.vin,
                odometer_km=v['odometer_km'],evidence_id=v['evidence_id'],actor_id=user.id));a.status='arrived';row.state='working'
            flow.finish_task(db,row,'intake_arrive',user);flow.ensure_task(db,row,'intake_convert','核对到店诉求并建立维修明细','service')
        elif action=='leave':
            if a.status!='arrived':raise HTTPException(409,'只有已到店且未转工单的接待可以记录离场')
            _task(db,user,row,'intake_convert');_evidence(db,user,row,v['evidence_id'])
            from .gate_attendance import departure_guard
            departure_guard(db,_one(db,CustomerVehicle,a.customer_vehicle_id).vin,intake_case_id=row.id)
            a.status='cancelled';row.state='cancelled';resource.updated_at=utcnow();flow.close_tasks(db,row,user)
        elif action=='convert':
            if a.status!='arrived' or a.repair_case_id:raise HTTPException(409,'须先记录实际到店，且每次接待只能转一张工单')
            _task(db,user,row,'intake_convert');vehicle,_=_vehicle(db,user,a.customer_vehicle_id);resource=_resource(db,a.resource_id)
            arrival=db.scalar(select(ArrivalFact).where(ArrivalFact.appointment_id==a.id));_evidence(db,user,row,arrival.evidence_id)
            preset=_preset(db,a.preset_id,resource) if a.preset_id else None
            repair=_build_repair(db,user,vehicle,a.problem,v['due_date'],resource,arrival.evidence_id,preset.profile if preset else 'regular',appointment=a,preset=preset)
            a.repair_case_id=repair.id;a.status='converted';row.state='completed';flow.finish_task(db,row,'intake_convert',user)
        else:raise HTTPException(404,'预约步骤不存在')
        db.flush();flow.log_event(db,user,row,'intake_'+action,{'reschedule':'记录预约变更','cancel':'取消未到店预约','no_show':'确认本次预约未到','leave':'确认已到店客户未开单离场','arrive':'确认实际到店','convert':'实际接待转明细工单'}[action],detail=v)
        return appointment_detail(db,user,a.id)
    return _execute(db,user,request_id,'appointment_'+action,{'id':key,'version':version,**v},run)
def _source(db,user,key,version=None):
    from .repair_service import is_detailed
    row=flow.get_case(db,user,key)
    if not is_detailed(row) or not row.data.get('released_date'):raise HTTPException(409,'首版售后返修只接受已实际接车的维修明细原单')
    settlement=db.scalar(select(RepairSettlement).where(RepairSettlement.case_id==row.id))
    if not settlement:raise HTTPException(409,'原维修尚无已冻结结算事实')
    if version is not None:_version(row,version)
    return row,settlement
def binding_create(db,user,key,v):
    _role(user,MANAGE)
    def run():
        source,_=_source(db,user,v['source_case_id'],v['source_version']);vehicle,_=_vehicle(db,user,v['customer_vehicle_id'])
        if source.customer_id!=vehicle.customer_id or v['checked_vin']!=vehicle.vin:raise HTTPException(409,'原客户、现场核验VIN与车辆主档不一致')
        _evidence(db,user,source,v['evidence_id']);_bind(db,user,source,vehicle,v['evidence_id'],v['source_reference'])
        flow.log_event(db,user,source,'intake_review_vehicle','主管根据原始凭据审核车辆身份',detail={'vin':vehicle.vin,'source_reference':v['source_reference']})
        db.flush();return {'case_id':source.id,'case_version':source.version,'vin':vehicle.vin}
    return _execute(db,user,key,'binding',v,run)
def _rework(db,user,key):
    _role(user,ADVISE|MANAGE|{'finance','auditor'});r=_one(db,ReworkRequest,key);return r,flow.get_case(db,user,r.case_id)
def rework_detail(db,user,key):
    r,row=_rework(db,user,key);vehicle=_one(db,CustomerVehicle,r.customer_vehicle_id);liability=db.scalar(select(ReworkLiability).where(ReworkLiability.request_id==r.id))
    from . import rework_extension_service as extensions
    extension=extensions.extension(db,r.id)
    contract=extensions.info(db,extension) if extension else None
    source=None if contract else flow.get_case(db,user,r.source_case_id)
    return {'id':r.id,'version':r.version,'case_id':row.id,'number':row.number,'title':row.title,'status':r.status,'reason':r.reason,
        **({'source_case_id':source.id} if source else {}),'source_number':contract['source_number'] if contract else source.number,'customer_vehicle_id':vehicle.id,'vin':vehicle.vin,'plate':vehicle.plate,
        'resource_id':r.resource_id,'repair_case_id':r.repair_case_id,'internal_name':liability.internal_name if liability else None,
        **({'rework_extension':contract} if contract else {}),
        'source_lines':contract['source_lines'] if contract else [{'id':l.source_line_id,'name':_one(db,RepairLine,l.source_line_id).name} for l in _rows(db,ReworkSourceLine,request_id=r.id)]}
def rework_create(db,user,key,v):
    _role(user,ADVISE)
    def run():
        source,settlement=_source(db,user,v['source_case_id'],v['source_version']);vehicle,customer=_vehicle(db,user,v['customer_vehicle_id']);resource=_resource(db,v['resource_id'])
        if resource.resource_type!='repair':raise HTTPException(422,'责任返修需选择维修工位')
        binding=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==source.id))
        if not binding:raise HTTPException(409,'原维修仅有车牌，须主管依据原始凭据核验VIN并追加身份绑定')
        if source.customer_id!=customer.id or binding.vin!=vehicle.vin or binding.customer_identity_id!=vehicle.customer_identity_id or binding.vehicle_identity_id!=vehicle.vehicle_identity_id:
            raise HTTPException(409,'返修必须为原单同一客户、同一VIN及已确认身份')
        if source.flow_version==3:_evidence(db,user,source,binding.evidence_id)
        else:
            source_context,_=context(db,source)
            intake=_one(db,ServiceAppointment,source_context.appointment_id) if source_context.appointment_id else _one(db,ReworkRequest,source_context.rework_id)
            _evidence(db,user,flow.get_case(db,user,intake.case_id),binding.evidence_id)
        if len(set(v['source_line_ids']))!=len(v['source_line_ids']):raise HTTPException(422,'原项目不能重复选择')
        for lid in v['source_line_ids']:
            line=_one(db,RepairLine,lid)
            if line.quote_id!=settlement.quote_id:raise HTTPException(404,'所选项目不属于原单最终结算版本')
        if db.scalar(select(ReworkRequest.id).where(ReworkRequest.active_source_id==source.id)):raise HTTPException(409,'原维修已有未结束返修，请先处理原申请')
        row=_case(db,user,customer,'售后责任返修申请','rework');r=ReworkRequest(case_id=row.id,source_case_id=source.id,source_quote_id=settlement.quote_id,
            customer_vehicle_id=vehicle.id,resource_id=resource.id,reason=v['reason'],requested_by=user.id,active_source_id=source.id)
        db.add(r);db.flush()
        for lid in v['source_line_ids']:db.add(ReworkSourceLine(request_id=r.id,source_line_id=lid))
        flow.set_data(row,rework_id=r.id);flow.ensure_task(db,row,'intake_liability','核对原单并确认是否承担返修责任','manager')
        flow.log_event(db,user,row,'intake_rework_request','申请原单售后返修责任');return rework_detail(db,user,r.id)
    return _execute(db,user,key,'rework_create',v,run)
def rework_action(db,user,key,request_id,version,action,v):
    _role(user,ADVISE if action=='convert' else MANAGE)
    def run():
        r,row=_rework(db,user,key);_version(r,version);row.updated_at=utcnow()
        from . import rework_extension_service as extensions
        extension=extensions.extension(db,r.id)
        grant=extensions.extension_grant(db,extension) if extension else None
        if action in {'approve','reject'}:
            if r.status!='requested':raise HTTPException(409,'该返修责任已复核')
            _task(db,user,row,'intake_liability')
            if r.requested_by==user.id and (extension or user.role!='admin'):raise HTTPException(403,'申请人不能批准本人返修责任')
            if action=='approve':
                if grant and v['internal_name']!=grant.responsible_name:raise HTTPException(409,'本次原责任主体须与原店冻结授权一致')
                _evidence(db,user,row,v['evidence_id']);db.add(ReworkLiability(request_id=r.id,reason=v['reason'],internal_name=v['internal_name'],evidence_id=v['evidence_id'],approved_by=user.id))
                r.approved_by=user.id;r.status='approved';row.state='working';flow.ensure_task(db,row,'intake_rework_convert','现场核对车辆后建立内部责任返修','service')
            else:r.status='rejected';r.active_source_id=None;row.state='cancelled'
            flow.finish_task(db,row,'intake_liability',user)
        elif action=='cancel':
            if r.status not in {'requested','approved'}:raise HTTPException(409,'已有实际返修工单须在工单办理退出，不可抹除申请')
            r.status='cancelled';r.active_source_id=None;row.state='cancelled';flow.close_tasks(db,row,user)
        elif action=='convert':
            if r.status!='approved' or r.repair_case_id:raise HTTPException(409,'责任尚未批准或已经转单')
            _task(db,user,row,'intake_rework_convert');vehicle,_=_vehicle(db,user,r.customer_vehicle_id)
            if v['checked_vin']!=vehicle.vin:raise HTTPException(409,'现场VIN与返修原车辆不一致')
            _evidence(db,user,row,v['evidence_id']);resource=_resource(db,r.resource_id)
            from .gate_attendance import arrive_guard
            arrive_guard(db,vehicle.vin)
            repair=_build_repair(db,user,vehicle,r.reason,v['due_date'],resource,v['evidence_id'],'rework',rework=r)
            r.repair_case_id=repair.id;r.status='converted';row.state='working';flow.finish_task(db,row,'intake_rework_convert',user)
        else:raise HTTPException(404,'返修申请步骤不存在')
        db.flush();flow.log_event(db,user,row,'intake_rework_'+action,{'approve':'主管确认原责任及新增自费分离' if extension else '主管确认全额内部返修责任','reject':'主管拒绝本次责任申请','cancel':'取消未执行返修申请','convert':'核对实际到店并建立返修工单'}[action],detail=v)
        return rework_detail(db,user,r.id)
    return _execute(db,user,request_id,'rework_'+action,{'id':key,'version':version,**v},run)
def list_records(db,user,kind,page):
    _role(user,READ if kind=='appointments' else ADVISE|MANAGE|{'finance','auditor'});model=ServiceAppointment if kind=='appointments' else ReworkRequest;describe=appointment_detail if kind=='appointments' else rework_detail
    query=select(model).where(model.case_id.in_(flow.case_query(user).with_only_columns(Case.id)));total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[describe(db,user,r.id) for r in db.scalars(query.order_by(model.id.desc()).offset((page-1)*30).limit(30))],'total':total,'page':page}
def context(db,row):
    ctx=db.scalar(select(RepairIntake).where(RepairIntake.case_id==row.id));binding=db.scalar(select(RepairVehicleBinding).where(RepairVehicleBinding.case_id==row.id))
    if row.flow_version!=4 or not ctx or not binding:raise HTTPException(409,'新接待维修缺少冻结来源或车辆核验事实，不能套用其他版本规则')
    return ctx,binding
def repair_info(db,user,row):
    ctx,binding=context(db,row);resource=_resource(db,ctx.resource_id,False)
    from . import rework_extension_service as extensions
    extension=extensions.extension(db,ctx.rework_id)
    liability=db.scalar(select(ReworkLiability).where(ReworkLiability.request_id==ctx.rework_id)) if ctx.rework_id else None
    from .gate_visit_models import RepairGateExit
    gate_exit=db.scalar(select(RepairGateExit).where(RepairGateExit.case_id==row.id))
    return {'cancelled_gate_exit_id':gate_exit.id if gate_exit else None,'profile':ctx.profile,'vin':binding.vin,'customer_vehicle_id':binding.customer_vehicle_id,'resource_id':resource.id,'resource_name':resource.name,
        'resource_occupied':resource.active_case_id==row.id,'resource_busy':resource.active_case_id is not None and resource.active_case_id!=row.id,
        'appointment_id':ctx.appointment_id,'rework_id':ctx.rework_id,'internal_only':ctx.profile=='rework' and not extension,'internal_name':liability.internal_name if liability else None,
        **({'rework_extension':extensions.info(db,extension)} if extension and user.role in {'admin','manager','service','finance','auditor'} else {})}
def _use(db,user,row,action,reason,evidence=None):
    ctx,binding=context(db,row);resource=_resource(db,ctx.resource_id,action=='acquire')
    if action=='acquire':
        vehicle=db.scalar(select(CustomerVehicle).where(CustomerVehicle.vin==binding.vin).order_by(CustomerVehicle.id))
        if not vehicle:raise HTTPException(409,'冻结车辆档案缺失')
        vehicle.updated_at=utcnow()
        occupied=db.scalar(select(ServiceResource.id).where(ServiceResource.active_case_id.in_(select(RepairVehicleBinding.case_id).where(RepairVehicleBinding.vin==binding.vin))).limit(1))
        if occupied:raise HTTPException(409,'同一VIN车辆仍在本店其他工位施工，不能同时开工')
        if resource.active_case_id is not None:raise HTTPException(409,'工位仍有实际占用；须确认原车辆实际移出，不能按计划时间自动释放')
        now=utcnow()
        live_repairs=select(Case.id).where(Case.state.notin_(['completed','credit_open','cancelled']))
        overlapping=db.scalar(select(ServiceAppointment.id).where(ServiceAppointment.resource_id==resource.id,
            or_(ServiceAppointment.status.in_(['scheduled','arrived']),and_(ServiceAppointment.status=='converted',ServiceAppointment.repair_case_id.in_(live_repairs))),ServiceAppointment.starts_at<=now,ServiceAppointment.ends_at>now,
            ServiceAppointment.id!=(ctx.appointment_id or 0)).limit(1))
        if overlapping:raise HTTPException(409,'当前时段已保留给其他预约，请先调整工位安排')
        resource.active_case_id=row.id
    else:
        if resource.active_case_id!=row.id:raise HTTPException(409,'本工单当前没有该工位的实际占用')
        resource.active_case_id=None
    resource.updated_at=utcnow();db.add(ResourceUse(resource_id=resource.id,case_id=row.id,action=action,reason=reason,evidence_id=evidence,actor_id=user.id));db.flush()
def before_repair_command(db,user,row,action,v):
    if row.flow_version!=4:return
    ctx,binding=context(db,row)
    from . import rework_extension_service as extensions
    extension=extensions.extension(db,ctx.rework_id)
    if extension:extensions.extension_grant(db,extension)
    if action=='release':
        from .gate_attendance import departure_guard
        departure_guard(db,binding.vin,repair_case_id=row.id)
    if action=='quote' and row.state=='assessment':_task(db,user,row,'repair_quote')
    if action=='authorize':_task(db,user,row,'repair_authorize_'+str(v['quote_id']))
    if action=='start':_use(db,user,row,'acquire','技师确认实际开工并占用工位')
    if action=='finish':
        resource=_resource(db,ctx.resource_id,False)
        if resource.active_case_id!=row.id:raise HTTPException(409,'本工单已移出工位；继续施工须先记录实际重新进位')
    if action=='allocate' and ctx.profile=='rework':
        liability=db.scalar(select(ReworkLiability).where(ReworkLiability.request_id==ctx.rework_id))
        if not liability:raise HTTPException(409,'返修责任尚未冻结')
        allocations=v['allocations']
        if extension:
            extensions.allocation_guard(db,row,extension,allocations)
            return
        if row.amount_cents:
            if len(allocations)!=1 or allocations[0]['payer_type']!='internal' or allocations[0]['amount_cents']!=row.amount_cents or allocations[0]['payer_name']!=liability.internal_name:
                raise HTTPException(409,'责任返修本次全部费用必须由批准的内部主体承担；新收费项目请另立普通工单')
        elif allocations:raise HTTPException(409,'零金额责任返修不应生成收费承担')
def after_repair_command(db,user,row,action):
    if row.flow_version!=4:return
    ctx,_=context(db,row)
    if action=='cancel':
        from .rework_extension_service import service_assignee
        flow.ensure_task(db,row,'gate_cancelled_repair_exit','核对车辆是否实际离场；取消维修不代表出厂','service',assignee=service_assignee(db,row))
    if action in {'release','cancel'}:
        resource=_resource(db,ctx.resource_id,False)
        if resource.active_case_id==row.id:_use(db,user,row,'release','客户实际接车或未开工取消释放工位')
    if ctx.rework_id and (row.data.get('released_date') or row.state=='cancelled'):
        r=_one(db,ReworkRequest,ctx.rework_id);r.status='completed' if row.data.get('released_date') else 'cancelled';r.active_source_id=None;r.updated_at=utcnow()
        parent=_one(db,Case,r.case_id);parent.state='completed' if row.data.get('released_date') else 'cancelled';parent.updated_at=utcnow();flow.close_tasks(db,parent,user)
def resource_action(db,user,key,request_id,version,action,v):
    _role(user,{'admin','technician'})
    def run():
        from .repair_service import get_order,describe
        row=get_order(db,user,key);_version(row,version);ctx,_=context(db,row)
        _evidence(db,user,row,v['evidence_id'])
        if action=='acquire':
            if row.state!='working' or not row.data.get('started') or row.data.get('stopping'):raise HTTPException(409,'只有已开工且仍待施工的工单才能记录重新进位')
            _task(db,user,row,'repair_work')
        elif row.state not in {'quality','settling','credit_open','completed'}:raise HTTPException(409,'提交完工后才能确认移出工位；未完成施工不能仅靠移位结束任务')
        _use(db,user,row,action,v['reason'],v['evidence_id']);flow.log_event(db,user,row,'intake_resource_'+action,'确认实际进位' if action=='acquire' else '确认实际移出工位',detail=v)
        db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,'resource_'+action,{'case_id':key,'version':version,**v},run)
