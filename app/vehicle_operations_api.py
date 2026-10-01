"""Explicit vehicle operation actions; no general status, location or cost editor."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator,field_validator
from sqlalchemy import select,func
from .db import get_db,get_write_db
from .security import get_user
from .flow_models import Case
from .models import Vehicle
from . import vehicle_operations_service as svc
from .vehicle_operations_models import VehicleOperation,VehiclePosition

router=APIRouter(prefix='/api/vehicle-operations',tags=['整车库位与出退库'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Create(Request):
    kind:Literal['locate','local_move','other_out','other_return']
    vehicle_id:int|None=Field(default=None,gt=0,strict=True)
    original_operation_id:int|None=Field(default=None,gt=0,strict=True)
    location_id:int|None=Field(default=None,gt=0,strict=True)
    reason:str=Field(min_length=2,max_length=500)
    recipient:str=Field(default='',max_length=180)
    due_date:date
    @model_validator(mode='after')
    def typed(self):
        if self.kind=='other_return':
            if not self.original_operation_id or self.vehicle_id:raise ValueError('原单退回须指定原出库单')
        elif not self.vehicle_id or self.original_operation_id:raise ValueError('请选择当前库存车辆')
        if (self.kind in {'locate','local_move','other_return'})!=bool(self.location_id):raise ValueError('请核对目的库位')
        if self.kind=='other_out' and not self.recipient:raise ValueError('请填写实际接收或处置去向')
        return self
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Reason):evidence_id:int=Field(gt=0,strict=True)
class Physical(Evidence):
    vin:str=Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    @field_validator('vin',mode='before')
    @classmethod
    def upper(cls,v):return v.upper() if isinstance(v,str) else v
class LocationPhysical(Physical):location_id:int=Field(gt=0,strict=True)
class Inspect(Evidence):
    outcome:Literal['pass','fail']
    findings:str=Field(min_length=2,max_length=1000)
class Disposition(Evidence):
    inspection_id:int=Field(gt=0,strict=True)
    decision:Literal['release','rectify','return_to_customer']
class Reassign(Reason):
    task_id:int=Field(gt=0,strict=True)
    assignee_id:int=Field(gt=0,strict=True)
    due_date:date
SCHEMAS={k:Physical for k in {'locate','dispatch','accept','reject','return_receive','receive','return_customer'}}|{'approve':Evidence,'reject_request':Evidence,'cancel':Reason,'intake':LocationPhysical,'release':LocationPhysical,'inspect':Inspect,'disposition':Disposition,'reassign':Reassign}

@router.get('/catalog')
def catalog(user=Depends(get_user)):
    allowed=user.role in svc.READ and not getattr(user,'_aggregate_scope',False)
    return {'can_read':allowed,'can_create':allowed and user.role in {'admin','manager','inventory'},'can_money':allowed and user.role in svc.MONEY,
        'kinds':svc.KINDS if allowed else {},'actions':svc.LABELS if allowed else {}}

@router.get('/orders')
def listing(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),q:str=Query('',max_length=80),db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):
        query=select(Case).join(VehicleOperation,VehicleOperation.id==Case.id)
        if user.role in {'service','technician'}:query=query.where(VehicleOperation.kind=='customer_return')
        if q:query=query.where(Case.number.contains(q,autoescape=True)|VehicleOperation.vin.contains(q,autoescape=True))
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        rows=db.scalars(query.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size))
        return {'items':[svc.describe(db,user,r) for r in rows],'total':total,'page':page,'page_size':page_size}

@router.get('/vehicles')
def vehicles(db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,{'admin','manager','inventory'}):
        unavailable=svc.unavailable_vehicle_ids(db)
        rows=list(db.scalars(select(Vehicle).where(Vehicle.approval_state=='approved').order_by(Vehicle.id.desc()).limit(1001)))
        if len(rows)>1000:raise HTTPException(413,'车辆超过本版一千台上限，请使用车辆编号办理')
        result=[]
        for r in rows:
            if r.id in unavailable:continue
            p=db.scalar(select(VehiclePosition).where(VehiclePosition.vehicle_id==r.id))
            result.append({'id':r.id,'vin':r.vin,'model':r.model,'generation':r.inventory_generation,'location_id':p.location_id if p else None,
                'location':svc.location_name(db,p.location_id) if p else '尚无明确库位','position_status':p.status if p else 'unlocated'})
        return {'items':result}

@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    return svc.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))

@router.get('/orders/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):return svc.describe(db,user,svc.get_order(db,user,case_id)[0])

@router.post('/orders/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'车辆作业动作不存在')
    try:v=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对车辆作业字段、17位VIN、实际凭据与本次检查结果；不能提交任意状态或成本')
    return svc.command(db,user,case_id,body.request_id,body.version,action,v)
