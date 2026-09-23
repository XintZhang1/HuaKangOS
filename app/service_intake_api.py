"""Dedicated reception commands: reservations never assert physical attendance."""
from datetime import datetime,date
from typing import Literal,Annotated
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator
from .db import get_db,today
from .security import get_user
from . import service_intake_service as service
router=APIRouter(prefix='/api/service-intake',tags=['维修接待与返修'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Resource(Strict):
    code:str=Field(min_length=1,max_length=60)
    name:str=Field(min_length=2,max_length=120)
    resource_type:Literal['repair','wash']
class ResourceSave(Request,Resource):pass
class Active(Reason):active:bool=Field(strict=True)
class PresetLine(Strict):
    work_item_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(default=1000,gt=0,le=1_000_000,strict=True)
class PresetSave(Request):
    code:str=Field(min_length=1,max_length=60)
    name:str=Field(min_length=2,max_length=120)
    profile:Literal['wash','quick']
    lines:list[PresetLine]=Field(min_length=1,max_length=20)
class Slot(Strict):
    resource_id:int=Field(gt=0,strict=True)
    starts_at:datetime
    ends_at:datetime
    @field_validator('starts_at','ends_at')
    @classmethod
    def timezone_required(cls,v):
        if v.tzinfo is None:raise ValueError('时间必须带时区')
        return v
class AppointmentSave(Request,Slot):
    customer_vehicle_id:int=Field(gt=0,strict=True)
    mode:Literal['appointment','walk_in']='appointment'
    problem:str=Field(min_length=2,max_length=1000)
    preset_id:int|None=Field(default=None,gt=0,strict=True)
class Reschedule(Slot,Reason):pass
class Arrival(Evidence):
    checked_vin:str=Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    odometer_km:int=Field(ge=0,le=3_000_000,strict=True)
    @field_validator('checked_vin',mode='before')
    @classmethod
    def vin(cls,v):return v.strip().upper() if isinstance(v,str) else v
class Convert(Strict):
    due_date:date=Field(default_factory=today)
    @field_validator('due_date')
    @classmethod
    def date_range(cls,v):
        if not date(2000,1,1)<=v<=date(2100,1,1):raise ValueError('日期范围不支持')
        return v
class ReworkSave(Request):
    source_case_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    customer_vehicle_id:int=Field(gt=0,strict=True)
    resource_id:int=Field(gt=0,strict=True)
    source_line_ids:list[Annotated[int,Field(gt=0,strict=True)]]=Field(min_length=1,max_length=100)
    reason:str=Field(min_length=2,max_length=1000)
class Liability(Reason,Evidence):internal_name:str=Field(min_length=2,max_length=120)
class ReworkConvert(Arrival,Convert):pass
class BindingSave(Request,Evidence):
    source_case_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    customer_vehicle_id:int=Field(gt=0,strict=True)
    checked_vin:str=Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    source_reference:str=Field(min_length=3,max_length=500)
class ResourceFact(Reason,Evidence):reason:str=Field(min_length=2,max_length=500)
APPOINTMENT_ACTIONS={'reschedule':Reschedule,'cancel':Reason,'no_show':Reason,'leave':ResourceFact,'arrive':Arrival,'convert':Convert}
REWORK_ACTIONS={'approve':Liability,'reject':Reason,'cancel':Reason,'convert':ReworkConvert}
def values(schema,data):
    try:return schema.model_validate(data).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对接待字段、原单、VIN、时段和实际凭据；不能提交任意状态')
@router.get('/catalog')
def catalog(db=Depends(get_db),user=Depends(get_user)):return service.catalog(db,user)
@router.get('/sources')
def sources(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.sources(db,user,page)
@router.get('/resources')
def resources(db=Depends(get_db),user=Depends(get_user)):return service.catalog(db,user)['resources']
@router.post('/resources',status_code=201)
def resource_create(body:ResourceSave,db=Depends(get_db),user=Depends(get_user)):
    return service.resource_create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.post('/resources/{key}/active')
def resource_active(key:int,body:Command,db=Depends(get_db),user=Depends(get_user)):
    return service.master_active(db,user,'resources',key,body.request_id,body.version,values(Active,body.values))
@router.post('/presets',status_code=201)
def preset_create(body:PresetSave,db=Depends(get_db),user=Depends(get_user)):
    return service.preset_create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.post('/presets/{key}/active')
def preset_active(key:int,body:Command,db=Depends(get_db),user=Depends(get_user)):
    return service.master_active(db,user,'presets',key,body.request_id,body.version,values(Active,body.values))
@router.get('/appointments')
def appointments(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.list_records(db,user,'appointments',page)
@router.post('/appointments',status_code=201)
def appointment_create(body:AppointmentSave,db=Depends(get_db),user=Depends(get_user)):
    return service.appointment_create(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.get('/appointments/{key}')
def appointment_detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.appointment_detail(db,user,key)
@router.post('/appointments/{key}/actions/{action}')
def appointment_action(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=APPOINTMENT_ACTIONS.get(action)
    if not schema:raise HTTPException(404,'预约动作不存在')
    return service.appointment_action(db,user,key,body.request_id,body.version,action,values(schema,body.values))
@router.post('/bindings',status_code=201)
def binding(body:BindingSave,db=Depends(get_db),user=Depends(get_user)):
    return service.binding_create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/reworks')
def reworks(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.list_records(db,user,'reworks',page)
@router.post('/reworks',status_code=201)
def rework_create(body:ReworkSave,db=Depends(get_db),user=Depends(get_user)):
    return service.rework_create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/reworks/{key}')
def rework_detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.rework_detail(db,user,key)
@router.post('/reworks/{key}/actions/{action}')
def rework_action(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=REWORK_ACTIONS.get(action)
    if not schema:raise HTTPException(404,'返修申请动作不存在')
    return service.rework_action(db,user,key,body.request_id,body.version,action,values(schema,body.values))
@router.post('/orders/{key}/resource/{action}')
def resource_action(key:int,action:Literal['acquire','release'],body:Command,db=Depends(get_db),user=Depends(get_user)):
    return service.resource_action(db,user,key,body.request_id,body.version,action,values(ResourceFact,body.values))
