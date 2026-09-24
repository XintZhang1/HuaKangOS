"""Strict employee-facing warehouse commands; aggregate views never become write scope."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import select,func
from .db import get_db
from .security import get_user
from .flow_models import Case,Item
from .warehouse_models import WarehouseDocument
from . import warehouse_service as svc

router=APIRouter(prefix='/api/warehouse',tags=['库位与仓储作业'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Location(Strict):
    location_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(ge=0,le=1_000_000_000,strict=True)
class Create(Request):
    operation:Literal['activate','other_in','other_in_return','consumable','consumable_return','gift','gift_return','disposal','local_move','count']
    item_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(ge=0,le=1_000_000_000,strict=True)
    source_location_id:int|None=Field(default=None,gt=0,strict=True)
    destination_location_id:int|None=Field(default=None,gt=0,strict=True)
    original_move_id:int|None=Field(default=None,gt=0,strict=True)
    reason:str=Field(min_length=2,max_length=500)
    recipient:str=Field(default='',max_length=120)
    due_date:date
    locations:list[Location]=Field(default_factory=list,max_length=100)
class Envelope(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Approve(Evidence):value_cents:int|None=Field(default=None,ge=0,le=1_000_000_000_000,strict=True)
class Capture(Evidence):counted_quantity_milli:int=Field(ge=0,le=1_000_000_000,strict=True)
class Receive(Evidence):quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class ReasonEvidence(Reason,Evidence):pass
class Assign(Reason):
    task_id:int=Field(gt=0,strict=True)
    assignee_id:int=Field(gt=0,strict=True)
    due_date:date
class Allocation(Strict):
    item_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(ge=-1_000_000_000,le=1_000_000_000,strict=True)
    purpose:str=Field(min_length=1,max_length=30)
    locations:list[Location]=Field(min_length=1,max_length=100)
SCHEMAS={'approve':Approve,'reject':Reason,'cancel':Reason,'execute':Evidence,'dispatch':Evidence,'accept':Receive,'reject_transit':ReasonEvidence,
    'return_transit':Receive,'capture':Capture,'post_count':Evidence,'assign':Assign,'void_observation':ReasonEvidence}
def parse(schema,values):
    try:return schema.model_validate(values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对仓储办理字段；数量为整数千分位、金额为整数分，不能直接修改状态或账面余额')
@router.get('/catalog')
def catalog(user=Depends(get_user)):
    allowed=user.role in svc.READ and not getattr(user,'_aggregate_scope',False)
    return {'can_read':allowed,'can_create':allowed and user.role in svc.PHYSICAL,'can_money':allowed and user.role in svc.MONEY,
        'operations':svc.NAMES if allowed else {},'external_purposes':sorted(svc.EXTERNAL_PURPOSES) if allowed else []}
@router.get('/items')
def items(page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):
        q=select(Item).where(Item.active.is_(True));total=db.scalar(select(func.count()).select_from(q.subquery()))
        return {'items':[svc.stock_view(db,user,r.id,False) for r in db.scalars(q.order_by(Item.id).offset((page-1)*page_size).limit(page_size))],'total':total,'page':page,'page_size':page_size}
@router.get('/items/{item_id}/stock')
def item_stock(item_id:int,db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):return svc.stock_view(db,user,item_id)
@router.get('/return-sources')
def return_sources(operation:Literal['other_in_return','consumable_return','gift_return'],q:str=Query('',max_length=100),
                   original_move_id:int|None=Query(None,gt=0),page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    return svc.return_sources(db,user,operation,q,original_move_id,page,page_size)
@router.get('/cases')
def cases(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):
        q=select(Case).where(Case.kind=='warehouse');total=db.scalar(select(func.count()).select_from(q.subquery()))
        return {'items':[svc.describe(db,user,r) for r in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size))],'total':total,'page':page,'page_size':page_size}
@router.post('/cases',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    return svc.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/cases/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):return svc.describe(db,user,svc.get_case(db,user,case_id)[0])
@router.post('/cases/{case_id}/commands/{action}')
def command(case_id:int,action:str,body:Envelope,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'仓储动作不存在')
    return svc.command(db,user,case_id,body.request_id,body.version,action,parse(schema,body.values))
@router.get('/allocations/{case_id}')
def allocation_options(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.PHYSICAL):return svc.allocation_options(db,user,case_id)
@router.post('/allocations/{case_id}')
def allocate(case_id:int,body:Envelope,db=Depends(get_db),user=Depends(get_user)):
    return svc.prepare_external(db,user,case_id,body.request_id,body.version,parse(Allocation,body.values))
