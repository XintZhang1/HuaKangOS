"""Dedicated correction endpoints used alongside original customer and insurance routes."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import select
from .db import get_db
from .security import get_user
from .flow_models import FileAsset
from .customer_service_models import CustomerVehicle
from .flow_documents import file_info
from . import observation_corrections_service as service

router=APIRouter(prefix='/api/observation-corrections',tags=['日期里程原观察纠正'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Replacement(Strict):
    observed_date:date
    odometer_km:int=Field(ge=0,le=3_000_000,strict=True)
    valid_until:date|None=None
    source_reference:str=Field(min_length=3,max_length=180)
class Create(Request):
    vehicle_id:int=Field(gt=0,strict=True)
    vehicle_version:int=Field(gt=0,strict=True)
    observation_id:int=Field(gt=0,strict=True)
    base_digest:str=Field(min_length=64,max_length=64)
    operation:Literal['replace','retract']
    proposed:Replacement|None=None
    reason:str=Field(min_length=3,max_length=1000)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Proof(Strict):evidence_id:int=Field(gt=0,strict=True)
class Reason(Strict):reason:str=Field(min_length=3,max_length=1000)
class Review(Proof,Reason):pass
class SourceSync(Request):version:int=Field(gt=0,strict=True)

@router.get('/catalog')
def catalog(db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user):
        vehicles=list(db.scalars(select(CustomerVehicle).order_by(CustomerVehicle.id).limit(501)))
        if len(vehicles)>500:raise HTTPException(413,'客户车辆超过单次范围，请从明确车辆页办理')
        vehicles=[v for v in vehicles if user.role not in {'sales','reception'} or service._one(db,service.care.Customer,v.customer_id).owner_id==user.id]
        return {'can_create':user.role in service.WRITE,'can_generate':user.role in service.care.OPS,'vehicles':[{'id':v.id,'label':v.plate+' / '+v.vin} for v in vehicles],
            'notice':'纠正原观察，不改仪表数值、不补造保养或保险里程；批准保留原记录和旧提醒历史。'}

@router.get('/vehicles/{vehicle_id}')
def vehicle(vehicle_id:int,db=Depends(get_db),user=Depends(get_user)):return service.vehicle_view(db,user,vehicle_id)

@router.get('/cases/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with service.authority(db,user):
        row=service.get_case(db,user,case_id);value=service.describe(db,user,row)
        value['files']=[file_info(f,db) for f in db.scalars(select(FileAsset).where(FileAsset.case_id==row.id).order_by(FileAsset.id)) if service.can_file(user,row,f)]
        return value

@router.post('/cases',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    return service.create(db,user,body.request_id,body.vehicle_id,body.vehicle_version,body.observation_id,body.base_digest,body.operation,body.proposed.model_dump(mode='json') if body.proposed else {},body.reason)

@router.post('/cases/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema={'submit':Proof,'approve':Review,'reject':Review,'cancel':Reason}.get(action)
    if not schema:raise HTTPException(404,'不存在此日期里程纠正动作')
    try:values=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对本次原件、原因和当前版本；不能填写任意状态或更换客户车辆')
    return service.command(db,user,body.request_id,case_id,body.version,action,values)

@router.post('/reminders/generate')
def generate(body:Request,db=Depends(get_db),user=Depends(get_user)):return service.generate_reminders(db,user,body.request_id)

@router.post('/insurance/{case_id}/sync')
def sync(case_id:int,body:SourceSync,db=Depends(get_db),user=Depends(get_user)):
    def apply():
        row=service.flow.get_case(db,user,case_id)
        if row.version!=body.version:raise HTTPException(409,'原保险版本已变化，请刷新确认终止事实')
        count=service.sync_insurance_basis(db,user,row)
        return {'invalidated':count,'notice':'仅核对已执行的完整保险终止链；未新增现金或实际里程'}
    return service._execute(db,user,body.request_id,'insurance_sync',{'case_id':case_id,'version':body.version},apply,{'admin','manager','finance','service'})
