"""Strict command envelopes for the dedicated retail workflow."""
from fastapi import APIRouter,Depends,HTTPException,Query
from decimal import Decimal
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator
from sqlalchemy import select,func
from .db import get_db,get_write_db
from .security import get_user
from .flow_models import Case
from . import retail_service as service
from .member_pricing_api import Selection
router=APIRouter(prefix='/api/retail',tags=['精品销售与退货'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Line(Strict):
    item_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    unit_price_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
    work_item_id:int|None=Field(default=None,gt=0,strict=True)
    installation_unit_price_cents:int=Field(default=0,ge=0,le=1_000_000_000,strict=True)
    @model_validator(mode='after')
    def install(self):
        if not self.work_item_id and self.installation_unit_price_cents:raise ValueError('无安装项目不能收费')
        return self
class Create(Request):
    member_pricing:Selection|None=None
    customer_id:int=Field(gt=0,strict=True)
    related_repair_id:int|None=Field(default=None,gt=0,strict=True)
    lines:list[Line]=Field(min_length=1,max_length=100)
    discount_cents:int=Field(default=0,ge=0,le=1_000_000_000_000,strict=True)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Approval(Reason):
    minimum_total_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    allow_below_minimum:bool=Field(default=False,strict=True)
class Authorize(Evidence):revision:int=Field(gt=0,strict=True)
class Result(Evidence):result:str=Field(min_length=2,max_length=1000)
class ReturnLine(Strict):
    dispatch_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class ReturnRequest(Evidence,Reason):lines:list[ReturnLine]=Field(min_length=1,max_length=100)
class ReturnRef(Strict):
    return_id:int=Field(gt=0,strict=True)
    return_version:int=Field(gt=0,strict=True)
class ReturnReview(ReturnRef,Reason):pass
class ReturnReceive(ReturnRef,Result):passed:bool=Field(strict=True)
class ReturnRectify(ReturnRef,Result):pass
class Pay(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Refund(Pay):original_payment_id:int=Field(gt=0,strict=True)
SCHEMAS={'approve':Approval,'authorize':Authorize,'cancel':Reason,'dispatch':Evidence,'install':Result,'accept':Evidence,'receive':Pay,
    'return_request':ReturnRequest,'return_approve':ReturnReview,'return_cancel':ReturnReview,'return_receive':ReturnReceive,'return_rectify':ReturnRectify,
    'return_reject':ReturnReview,'return_handback':ReturnRectify,'refund':Refund}
@router.get('/installations')
def installations(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    if user.role not in service.FRONT|{'manager'}:raise HTTPException(403,'当前岗位不能配置精品安装报价')
    from .master_models import WorkItem
    query=select(WorkItem).where(WorkItem.active==True)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[{'id':w.id,'code':w.code,'name':w.name,'standard_fee_cents':w.standard_fee_cents} for w in db.scalars(query.order_by(WorkItem.id).offset((page-1)*30).limit(30))],'total':total}
@router.get('/items')
def items(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    if user.role not in service.FRONT|{'manager'}:raise HTTPException(403,'当前岗位不能配置精品报价')
    from .flow_models import Item
    from .inventory_availability import available_quantity
    query=select(Item).where(Item.active==True)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[{'id':x.id,'sku':x.sku,'name':x.name,'unit':x.unit,'active':x.active,'quantity_milli':x.quantity_milli,
        'available_quantity':format(Decimal(available_quantity(db,x))/1000,'f')} for x in db.scalars(query.order_by(Item.id).offset((page-1)*30).limit(30))],'total':total}
@router.get('/orders')
def orders(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    if user.role not in service.READ_ROLES:raise HTTPException(403,'当前岗位不能查看精品销售')
    query=service.flow.case_query(user).where(Case.kind=='retail',Case.flow_version==2)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[service.describe(db,user,r) for r in db.scalars(query.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size))],'total':total,'page':page,'page_size':page_size}
@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    return service.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/orders/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):
    return service.describe(db,user,service.get_order(db,user,key))
@router.post('/orders/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'精品办理动作不存在')
    try:v=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对精品办理字段；金额为整数分、数量为整数千分位，原单与凭据必须正确关联')
    return service.command(db,user,key,body.request_id,body.version,action,v)
