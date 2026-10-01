"""Typed dedicated API for repair version three; historical workflows unchanged."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator,model_validator
from sqlalchemy import select,func,or_
from .db import get_db,get_write_db,today
from .security import get_user
from .flow_models import Case
from . import repair_service as service
from .member_pricing_api import Selection

router=APIRouter(prefix='/api/repair-orders',tags=['维修明细工单'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Due(Strict):
    due_date:date=Field(default_factory=today)
    @field_validator('due_date')
    @classmethod
    def valid_day(cls,value):
        if not date(2000,1,1)<=value<=date(2100,1,1):raise ValueError('日期超出业务范围')
        return value
class Create(Request,Due):
    customer_id:int=Field(gt=0,strict=True)
    plate:str=Field(min_length=1,max_length=30)
    problem:str=Field(min_length=2,max_length=1000)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Result(Strict):result:str=Field(min_length=2,max_length=1000)
class QuoteRef(Strict):quote_id:int=Field(gt=0,strict=True)
class Line(Strict):
    kind:Literal['work','part']
    source_id:int=Field(gt=0,strict=True)
    line_key:str|None=Field(default=None,min_length=1,max_length=40)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    unit_price_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
class Quote(Reason):
    member_pricing:Selection|None=None
    purpose:Literal['service','stop']='service'
    lines:list[Line]=Field(default_factory=list,max_length=100)
    discount_cents:int=Field(default=0,ge=0,le=1_000_000_000_000,strict=True)
    retained_amount_cents:int|None=Field(default=None,ge=0,le=1_000_000_000_000,strict=True)
    @model_validator(mode='after')
    def stop_fields(self):
        if self.purpose=='stop' and self.discount_cents:raise ValueError('停工填写保留费用，不另填折扣')
        return self
class Price(QuoteRef,Reason):
    minimum_total_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    allow_below_minimum:bool=Field(default=False,strict=True)
class Authorize(QuoteRef,Evidence):pass
class QuoteCancel(QuoteRef,Reason):pass
class Quantity(Evidence):quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class Issue(Quantity):line_key:str=Field(min_length=1,max_length=40)
class Return(Quantity):original_id:int=Field(gt=0,strict=True)
class Quality(Result,Evidence):passed:bool=Field(strict=True)
class Allocation(Due):
    payer_type:Literal['customer','insurer','manufacturer','internal']
    payer_id:int|None=Field(default=None,gt=0,strict=True)
    payer_name:str=Field(default='',max_length=120)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    @model_validator(mode='after')
    def identity(self):
        if self.payer_type in {'insurer','manufacturer'} and not self.payer_id:raise ValueError('请选择承担方档案')
        if self.payer_type in {'customer','internal'} and self.payer_id:raise ValueError('客户由原单确定，内部承担填写主体')
        return self
class Allocate(Evidence):
    allocations:list[Allocation]=Field(max_length=4)
    labor_cost_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
class Receive(Evidence):
    allocation_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
SCHEMAS={'quote':Quote,'quote_cancel':QuoteCancel,'price_approve':Price,'authorize':Authorize,'start':Result,
    'issue':Issue,'return_material':Return,'finish':Result,'quality':Quality,'allocate':Allocate,'receive':Receive,'release':Evidence,'cancel':Reason}

@router.get('')
def orders(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),q:str=Query('',max_length=100),db=Depends(get_db),user=Depends(get_user)):
    if user.role not in service.READ_ROLES:raise HTTPException(403,'当前岗位不能查看维修明细')
    query=service.flow.case_query(user).where(Case.kind=='repair',Case.flow_version.in_([3,4]))
    if q:query=query.where(or_(Case.number.contains(q,autoescape=True),Case.title.contains(q,autoescape=True),Case.data['plate'].as_string().contains(q,autoescape=True)))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size))
    return {'items':[service.describe(db,user,row) for row in rows],'total':total,'page':page,'page_size':page_size}
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    return service.create(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.get('/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    return service.describe(db,user,service.get_order(db,user,case_id))
@router.post('/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'维修动作不存在')
    try:values=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对维修办理字段；金额需为整数分，数量为整数千分位，报价和承担方须正确关联')
    return service.command(db,user,case_id,body.request_id,body.version,action,values)
