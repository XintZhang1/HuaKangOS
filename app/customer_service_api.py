"""Store-scoped customer service UI API. No endpoint sends external messages."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import select,or_,func
from .db import get_db,get_write_db,get_audited_read_db,today
from .security import get_user
from .tenancy import role_for_store
from .models import User,Store
from .flow_models import Customer,Case
from .customer_service_models import CustomerVehicle,VehicleObservation,CareCase,ReminderRule,HistoryGrant
from .services import plain
from . import customer_service as service

router=APIRouter(prefix='/api/customer-service',tags=['客户车辆与客户服务'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Save(Request):values:dict
class Update(Save):version:int=Field(gt=0,strict=True)
class VehicleInput(Strict):
    customer_id:int=Field(gt=0,strict=True)
    customer_identity_id:int|None=Field(default=None,gt=0,strict=True)
    vin:str=Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    plate:str=Field(default='',max_length=30)
    model_name:str=Field(min_length=1,max_length=120)
    source_reference:str=Field(min_length=3,max_length=180)
    confirmed:Literal[True]
    @field_validator('vin',mode='before')
    @classmethod
    def uppercase(cls,value):return value.strip().upper() if isinstance(value,str) else value
class VehicleEdit(Strict):
    plate:str=Field(default='',max_length=30)
    model_name:str=Field(min_length=1,max_length=120)
    active:bool
    reason:str=Field(min_length=3,max_length=250)
class Observation(Strict):
    kind:Literal['delivery','odometer','maintenance','first_service','insurance','warranty']
    observed_date:date
    odometer_km:int=Field(ge=0,le=3000000,strict=True)
    valid_until:date|None=None
    source_reference:str=Field(min_length=3,max_length=180)
    evidence_id:int|None=Field(default=None,gt=0,strict=True)
    confirmed:Literal[True]
class NewCare(Strict):
    customer_id:int=Field(gt=0,strict=True)
    vehicle_id:int|None=Field(default=None,gt=0,strict=True)
    subtype:Literal['questionnaire','consultation','complaint','rescue','sales_callback','repair_callback','renewal']
    source_case_id:int|None=Field(default=None,gt=0,strict=True)
    topic:str=Field(min_length=2,max_length=120)
    description:str=Field(min_length=3,max_length=3000)
    location:str=Field(default='',max_length=250)
    priority:Literal['normal','urgent']='normal'
    assignee_id:int=Field(gt=0,strict=True)
    due_date:date
class Start(Strict):pass
class Followup(Strict):
    channel:Literal['internal','in_person','phone']
    contact_result:Literal['progress','contacted','unreachable','declined']
    note:str=Field(min_length=3,max_length=2000)
    next_due_date:date|None=None
class Handoff(Strict):
    assignee_id:int=Field(gt=0,strict=True)
    due_date:date
    reason:str=Field(min_length=3,max_length=500)
class Cancel(Strict):reason:str=Field(min_length=3,max_length=500)
class Close(Strict):
    result:Literal['resolved','appointment','declined','no_response','renewed']
    note:str=Field(min_length=3,max_length=2000)
    satisfaction:int|None=Field(default=None,ge=1,le=5,strict=True)
    recommend:bool|None=Field(default=None,strict=True)
    answers:dict|None=None
class Rule(Strict):
    name:str=Field(min_length=2,max_length=120)
    kind:Literal['first_service','maintenance','warranty','renewal']
    interval_days:int=Field(default=0,ge=0,le=3650,strict=True)
    interval_km:int=Field(default=0,ge=0,le=1000000,strict=True)
    lead_days:int=Field(default=0,ge=0,le=365,strict=True)
    lead_km:int=Field(default=0,ge=0,le=100000,strict=True)
    assignee_id:int=Field(gt=0,strict=True)
    active:bool=True
class HistoryLink(Strict):
    case_id:int=Field(gt=0,strict=True)
    summary:str=Field(min_length=3,max_length=600)
    source_reference:str=Field(min_length=3,max_length=180)
    confirmed:Literal[True]
class Grant(Strict):
    from_vehicle_id:int=Field(gt=0,strict=True)
    to_store_id:int=Field(gt=0,strict=True)
    to_vehicle_id:int=Field(gt=0,strict=True)
    valid_until:date
    source_reference:str=Field(min_length=3,max_length=180)
    confirmed:Literal[True]


def parse(schema,values):
    from pydantic import ValidationError
    try:return schema.model_validate(values).model_dump()
    except ValidationError as error:
        raise HTTPException(422,'填写资料有误，请核对必填项、整数范围、日期及确认选项') from error


@router.get('/catalog')
def catalog(db=Depends(get_db),user=Depends(get_user)):
    allowed=user.role in service.READ and not getattr(user,'_aggregate_scope',False)
    return {'can_read':allowed,'can_write':allowed and user.role in service.WRITE,'can_manage':allowed and user.role in service.MANAGE,
        'can_reminders':allowed and user.role in service.OPS|{'auditor'},
        'can_generate':allowed and user.role in service.OPS,'types':{k:v for k,v in service.LABELS.items() if allowed},
        'create_types':{k:service.LABELS[k] for k in NewCare.model_fields['subtype'].annotation.__args__ if allowed and user.role in service.TYPE_ROLES[k]},
        'observation_types':service.OBS_LABELS if allowed else {},'states':service.STATUS,'results':service.RESULTS}


@router.get('/lookup/{kind}')
def lookup(kind:str,subtype:str='consultation',q:str=Query('',max_length=100),customer_id:int|None=Query(default=None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user) as sid:
        if kind=='customers':
            stmt=select(Customer)
            if user.role in {'sales','reception'}:stmt=stmt.where(Customer.owner_id==user.id)
            if q:stmt=stmt.where(or_(Customer.name.contains(q),Customer.phone.contains(q)))
            return {'items':[{'id':r.id,'label':r.name+' · '+(r.phone or '未留电话')} for r in db.scalars(stmt.order_by(Customer.id).limit(100))]}
        if kind=='vehicles':
            stmt=select(CustomerVehicle).join(Customer,Customer.id==CustomerVehicle.customer_id).where(CustomerVehicle.active.is_(True))
            if user.role in {'sales','reception'}:stmt=stmt.where(Customer.owner_id==user.id)
            if customer_id:stmt=stmt.where(CustomerVehicle.customer_id==customer_id)
            if q:stmt=stmt.where(or_(CustomerVehicle.vin.contains(q),CustomerVehicle.plate.contains(q)))
            return {'items':[{'id':r.id,'label':r.plate+' · '+r.vin,'customer_id':r.customer_id} for r in db.scalars(stmt.order_by(CustomerVehicle.id).limit(100))]}
        if kind=='employees':
            if subtype not in service.TYPE_ROLES:raise HTTPException(422,'客户服务类型无效')
            return {'items':[{'id':r.id,'label':r.display_name} for r in db.scalars(select(User).where(User.active.is_(True)).order_by(User.id))
                if role_for_store(db,r,sid) in service.TYPE_ROLES[subtype] and (user.role not in {'sales','reception'} or r.id==user.id)]}
        if kind=='stores':
            if user.role not in service.MANAGE:raise HTTPException(403,'历史授权需要主管办理')
            return {'items':[{'id':r.id,'label':r.name} for r in db.scalars(select(Store).where(Store.active.is_(True),Store.id!=sid).order_by(Store.id))]}
        if kind=='source_cases':
            callback=subtype in {'sales_callback','repair_callback'}
            if callback and not customer_id:return {'items':[]}
            if customer_id:service._customer(db,user,customer_id)
            stmt=(select(Case) if callback else service.eng.case_query(user)).where(Case.kind.in_(['order','repair','addon','insurance','agency','customer_care']))
            if customer_id:stmt=stmt.where(Case.customer_id==customer_id)
            if subtype in {'sales_callback','repair_callback'}:stmt=stmt.where(Case.kind==('order' if subtype=='sales_callback' else 'repair'),Case.state.in_(['delivered','completed','credit_open']))
            if q:stmt=stmt.where(Case.number.contains(q))
            return {'items':[{'id':r.id,'label':r.number+' · '+r.title} for r in db.scalars(stmt.order_by(Case.id.desc()).limit(100))]}
        raise HTTPException(404,'查找类别不存在')


@router.get('/vehicles')
def vehicles(q:str=Query('',max_length=100),page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user):
        stmt=select(CustomerVehicle).join(Customer,Customer.id==CustomerVehicle.customer_id)
        if user.role in {'sales','reception'}:stmt=stmt.where(Customer.owner_id==user.id)
        if q:stmt=stmt.where(or_(Customer.name.contains(q),CustomerVehicle.vin.contains(q),CustomerVehicle.plate.contains(q)))
        total=db.scalar(select(func.count()).select_from(stmt.subquery()))
        return {'items':[service._vehicle_info(db,r) for r in db.scalars(stmt.order_by(CustomerVehicle.id.desc()).offset((page-1)*30).limit(30))],'total':total,'page':page}


@router.post('/vehicles',status_code=201)
def new_vehicle(body:Save,db=Depends(get_write_db),user=Depends(get_user)):return service.vehicle_create(db,user,body.request_id,parse(VehicleInput,body.values))


@router.get('/vehicles/{vehicle_id}')
def vehicle_detail(vehicle_id:int,db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user):
        from .observation_corrections_service import effective_observations
        row=service._vehicle(db,user,vehicle_id,False)
        return {'vehicle':service._vehicle_info(db,row),'observations':[plain(r) for r in db.scalars(select(VehicleObservation).where(VehicleObservation.vehicle_id==row.id).order_by(VehicleObservation.id.desc()))],
            'effective_observations':effective_observations(db,row.id,include_inactive=True)}


@router.put('/vehicles/{vehicle_id}')
def edit_vehicle(vehicle_id:int,body:Update,db=Depends(get_write_db),user=Depends(get_user)):return service.vehicle_update(db,user,body.request_id,vehicle_id,body.version,parse(VehicleEdit,body.values))


@router.post('/vehicles/{vehicle_id}/observations')
def observation(vehicle_id:int,body:Update,db=Depends(get_write_db),user=Depends(get_user)):return service.observe(db,user,body.request_id,vehicle_id,body.version,parse(Observation,body.values))


@router.get('/vehicles/{vehicle_id}/history')
def history(vehicle_id:int,db=Depends(get_db),user=Depends(get_user)):return service.service_history(db,user,vehicle_id)


@router.post('/vehicles/{vehicle_id}/history-links',status_code=201)
def link_history(vehicle_id:int,body:Save,db=Depends(get_write_db),user=Depends(get_user)):return service.history_link(db,user,body.request_id,vehicle_id,parse(HistoryLink,body.values))


@router.get('/cases')
def cases(subtype:str='',status:str='',q:str=Query('',max_length=100),page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user):
        stmt=select(Case).join(CareCase,CareCase.case_id==Case.id).where(Case.kind=='customer_care',Case.flow_version==2)
        if subtype:stmt=stmt.where(CareCase.subtype==subtype)
        if status=='open':stmt=stmt.where(Case.state.in_(['pending','working']))
        elif status:stmt=stmt.where(Case.state==status)
        if q:stmt=stmt.where(or_(Case.number.contains(q),CareCase.topic.contains(q)))
        if user.role in {'sales','reception'}:stmt=stmt.where(or_(Case.owner_id==user.id,Case.created_by==user.id))
        total=db.scalar(select(func.count()).select_from(stmt.subquery()))
        items=[]
        for row in db.scalars(stmt.order_by(Case.id.desc()).offset((page-1)*30).limit(30)):
            items.append(service.case_info(db,user,row,db.scalar(select(CareCase).where(CareCase.case_id==row.id)),False))
        return {'items':items,'total':total,'page':page}


@router.post('/cases',status_code=201)
def new_case(body:Save,db=Depends(get_write_db),user=Depends(get_user)):return service.case_create(db,user,body.request_id,parse(NewCare,body.values))


@router.get('/cases/{case_id}')
def case_detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user):
        row,care=service._care(db,user,case_id);return service.case_info(db,user,row,care)


@router.post('/cases/{case_id}/actions/{action}')
def action(case_id:int,action:str,body:Update,db=Depends(get_write_db),user=Depends(get_user)):
    schema={'start':Start,'followup':Followup,'handoff':Handoff,'cancel':Cancel,'close':Close}.get(action)
    if not schema:raise HTTPException(404,'客户服务动作不存在')
    return service.case_action(db,user,body.request_id,case_id,body.version,action,parse(schema,body.values))


@router.get('/reminders/rules')
def rules(db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user,service.OPS|{'auditor'}):return {'items':[plain(r) for r in db.scalars(select(ReminderRule).order_by(ReminderRule.id))]}


@router.post('/reminders/rules',status_code=201)
def new_rule(body:Save,db=Depends(get_write_db),user=Depends(get_user)):return service.rule_save(db,user,body.request_id,parse(Rule,body.values))


@router.put('/reminders/rules/{rule_id}')
def update_rule(rule_id:int,body:Update,db=Depends(get_write_db),user=Depends(get_user)):return service.rule_save(db,user,body.request_id,parse(Rule,body.values),rule_id,body.version)


@router.post('/reminders/generate')
def generate(body:Request,db=Depends(get_write_db),user=Depends(get_user)):return service.generate_reminders(db,user,body.request_id)


@router.get('/history/grants')
def grants(db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user,service.MANAGE) as sid:
        return {'items':[plain(r) for r in db.scalars(select(HistoryGrant).where(or_(HistoryGrant.from_store_id==sid,HistoryGrant.to_store_id==sid)).order_by(HistoryGrant.id.desc()).limit(100))]}


@router.post('/history/grants',status_code=201)
def new_grant(body:Save,db=Depends(get_write_db),user=Depends(get_user)):return service.grant_history(db,user,body.request_id,parse(Grant,body.values))


@router.post('/history/grants/{grant_id}/revoke')
def revoke(grant_id:int,body:Update,db=Depends(get_write_db),user=Depends(get_user)):return service.revoke_grant(db,user,body.request_id,grant_id,body.version,parse(Cancel,body.values)['reason'])


class QuestionnaireProposal(Strict):
    policy_version:int=Field(ge=0,strict=True)
    name:str=Field(min_length=2,max_length=120)
    questions:list[dict]=Field(min_length=1,max_length=30)
    reason:str=Field(min_length=3,max_length=1000)


class QuestionnaireDecision(Strict):
    policy_version:int=Field(gt=0,strict=True)
    decision:Literal['approve','reject']
    reason:str=Field(min_length=3,max_length=1000)
    confirmed:Literal[True]


@router.get('/questionnaires/versions')
def questionnaire_versions(db=Depends(get_db),user=Depends(get_user)):
    from .questionnaire_service import catalog
    return catalog(db,user)


@router.post('/questionnaires/versions',status_code=201)
def questionnaire_propose(body:Save,db=Depends(get_write_db),user=Depends(get_user)):
    from .questionnaire_service import propose
    return propose(db,user,body.request_id,parse(QuestionnaireProposal,body.values))


@router.post('/questionnaires/versions/{version_id}/review')
def questionnaire_review(version_id:int,body:Save,db=Depends(get_write_db),user=Depends(get_user)):
    from .questionnaire_service import review
    return review(db,user,body.request_id,version_id,parse(QuestionnaireDecision,body.values))


@router.get('/questionnaires/report')
def questionnaire_report(date_from:date|None=None,date_to:date|None=None,db=Depends(get_db),user=Depends(get_user)):
    from .questionnaire_analytics import report
    return report(db,user,date_from,date_to)


@router.get('/questionnaires/export/{table_key}')
def questionnaire_export(table_key:str,date_from:date|None=None,date_to:date|None=None,
    version_number:str|None=None,schema_digest:str|None=None,question_key:str|None=None,
    db=Depends(get_audited_read_db),user=Depends(get_user)):
    import csv,io
    from urllib.parse import quote
    from fastapi import Response
    from .questionnaire_analytics import report,select_table
    from .services import audit
    data=report(db,user,date_from,date_to)
    table=select_table(data,table_key,version_number,schema_digest,question_key)
    buffer=io.StringIO(newline='');writer=csv.writer(buffer)
    def safe(value):
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r','\n')) and not text.replace('-','',1).replace('.','',1).isdigit() else text
    writer.writerow(table['headers'])
    writer.writerows([[safe(v) for v in row['values']] for row in table['rows']])
    scope='' if version_number is None else ' v'+version_number+' '+schema_digest+' '+question_key
    audit(db,user.id,'export','questionnaire_report',None,reason=data['date_from']+'至'+data['date_to']+' '+table_key+scope);db.commit()
    return Response(('\ufeff'+buffer.getvalue()).encode(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('huakangos_'+table['title']+'.csv')})
