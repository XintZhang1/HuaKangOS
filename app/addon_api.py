"""Typed envelopes for sales-bound accessory work."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import select,func
from .db import get_db,get_write_db
from .security import get_user
from .flow_models import Case,Item
from . import addon_service as service
router=APIRouter(prefix='/api/addon-orders',tags=['销售加装明细'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Create(Request):
    source_order_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    due_date:date
    delivery_blocking:bool=Field(default=True,strict=True)
    reason:str=Field(min_length=2,max_length=1000)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Result(Evidence):result:str=Field(min_length=2,max_length=1000)
class QuoteLine(Strict):
    line_key:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    item_id:int=Field(gt=0,strict=True)
    work_item_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    goods_unit_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
    installation_unit_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
    gift_reason:str=Field(default='',max_length=1000)
    gift_cost_bearer:Literal['selling_store']|None=None
from .member_pricing_api import Selection
class Quote(Reason):
    member_pricing:Selection|None=None
    lines:list[QuoteLine]=Field(min_length=1,max_length=100)
    discount_cents:int=Field(default=0,ge=0,le=1_000_000_000_000,strict=True)
class Approve(Reason,Evidence):
    minimum_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    allow_below_minimum:bool=Field(default=False,strict=True)
    confirm_gift:bool=Field(default=False,strict=True)
class Authorize(Evidence):quote_id:int=Field(gt=0,strict=True)
class Pick(Strict):
    line_key:str=Field(min_length=1,max_length=40)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class Dispatch(Evidence):
    checked_vin:str=Field(min_length=17,max_length=17)
    lines:list[Pick]=Field(min_length=1,max_length=100)
class Install(Result):
    dispatch_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class Quality(Result):
    installation_id:int=Field(gt=0,strict=True)
    passed:bool=Field(strict=True)
class Rectify(Result):inspection_id:int=Field(gt=0,strict=True)
class ResolutionLine(Strict):
    line_key:str|None=Field(default=None,max_length=40)
    dispatch_id:int|None=Field(default=None,gt=0,strict=True)
    installation_id:int|None=Field(default=None,gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class Resolution(Reason,Evidence):
    kind:Literal['return','cancel','vehicle_gift']
    lines:list[ResolutionLine]=Field(min_length=1,max_length=100)
    confirm_no_goods_refund:bool=Field(default=False,strict=True)
class Resolve(Result):
    resolution_id:int=Field(gt=0,strict=True)
    confirm_no_goods_refund:bool=Field(default=False,strict=True)
class ReturnCheck(Resolve):passed:bool=Field(strict=True)
class Receive(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Refund(Evidence):
    resolution_id:int=Field(gt=0,strict=True)
    kind:Literal['cash','advance']
    original_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int|None=Field(default=None,gt=0,strict=True)
    reference:str=Field(default='',max_length=100)
SCHEMAS=dict(quote=Quote,approve=Approve,authorize=Authorize,dispatch=Dispatch,install=Install,quality=Quality,rectify=Rectify,accept=Authorize,receive=Receive,resolution=Resolution,refund=Refund,cancel=Reason,
    resolution_approve=Resolve,resolution_consent=Resolve,resolution_cancel=Resolve,resolution_reject=Resolve,return_receive=ReturnCheck,return_rectify=Resolve,return_handback=Resolve)
@router.get('/catalog')
def catalog(page:int=Query(1,ge=1),source_page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    service.single_store(db);service._role(user,service.FRONT|service.MANAGE)
    from .master_models import WorkItem
    from .inventory_availability import available_quantity
    items=list(db.scalars(select(Item).where(Item.active==True).order_by(Item.id).offset((page-1)*30).limit(30)))
    works=list(db.scalars(select(WorkItem).where(WorkItem.active==True).order_by(WorkItem.id)))
    q=service.flow.case_query(user).where(Case.kind=='order',Case.flow_version.in_([2,3,4]),Case.state!='cancelled')
    return dict(items=[dict(id=x.id,sku=x.sku,name=x.name,unit=x.unit,available_milli=available_quantity(db,x)) for x in items],item_total=db.scalar(select(func.count()).select_from(Item).where(Item.active==True)),
        work_items=[dict(id=x.id,name=x.name,code=x.code,standard_fee_cents=x.standard_fee_cents) for x in works],source_total=db.scalar(select(func.count()).select_from(q.subquery())),orders=[dict(id=x.id,number=x.number,title=x.title,version=x.version) for x in db.scalars(q.order_by(Case.id.desc()).offset((source_page-1)*100).limit(100))])
@router.get('')
def orders(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    service._role(user,service.READ);q=service.flow.case_query(user).where(Case.kind=='addon',Case.flow_version==3)
    return dict(items=[service.describe(db,user,r) for r in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*30).limit(30))],total=db.scalar(select(func.count()).select_from(q.subquery())))
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):return service.create(db,user,body.request_id,body.model_dump(exclude={'request_id'},mode='json'))
@router.get('/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.describe(db,user,service.get_order(db,user,key))
@router.post('/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'加装办理动作不存在')
    try:v=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对加装字段；金额为整数分、数量为整数千分位，项目、版本与凭据必须关联正确')
    return service.command(db,user,key,body.request_id,body.version,action,v)
