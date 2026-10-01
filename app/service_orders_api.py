"""Commands for agency v3 and other customer service income v2."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .db import get_db,get_write_db
from .security import get_user
from . import service_orders_service as service

router=APIRouter(prefix='/api/service-orders',tags=['代办与其它客户服务'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Create(Request,Reason):
    subtype:Literal['agency','other_income']
    customer_id:int=Field(gt=0,strict=True)
    source_order_id:int|None=Field(default=None,gt=0,strict=True)
    source_version:int|None=Field(default=None,gt=0,strict=True)
    customer_vehicle_id:int|None=Field(default=None,gt=0,strict=True)
    delivery_blocking:bool=Field(default=False,strict=True)
    due_date:date
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Line(Strict):
    line_key:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    bucket:Literal['fee','pass']
    agency_project_id:int|None=Field(default=None,gt=0,strict=True)
    income_item_id:int|None=Field(default=None,gt=0,strict=True)
    payee_id:int|None=Field(default=None,gt=0,strict=True)
    name:str=Field(default='',max_length=120)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    unit_price_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    due_date:date
class Quote(Reason):
    lines:list[Line]=Field(min_length=1,max_length=100)
    discount_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
class Approval(Evidence,Reason):
    minimum_fee_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    allow_below_minimum:bool=Field(strict=True)
class Authorization(Evidence):quote_id:int=Field(gt=0,strict=True)
class LineEvidence(Evidence):line_key:str=Field(min_length=1,max_length=40)
class Submit(LineEvidence):
    external_reference:str=Field(min_length=1,max_length=120)
    submitted_on:date
    supplement_result_id:int|None=Field(default=None,gt=0,strict=True)
class Result(LineEvidence):
    submission_id:int=Field(gt=0,strict=True)
    outcome:Literal['approved','rejected','need_documents']
    result:str=Field(min_length=2,max_length=1000)
class Fulfillment(LineEvidence):result:str=Field(min_length=2,max_length=1000)
class Cash(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Disbursement(Cash):tender_id:int=Field(gt=0,strict=True)
class Returned(Cash):original_id:int=Field(gt=0,strict=True)
class Retained(Strict):
    line_key:str=Field(min_length=1,max_length=40)
    retained_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
class Selection(Strict):
    tender_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class Termination(Evidence,Reason):
    lines:list[Retained]=Field(min_length=1,max_length=100)
    returns:list[Selection]=Field(default_factory=list,max_length=200)
class Plan(Evidence):plan_id:int=Field(gt=0,strict=True)
class PlanCancel(Reason):plan_id:int=Field(gt=0,strict=True)
class Refund(Plan):
    tender_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int|None=Field(default=None,gt=0,strict=True)
    reference:str=Field(default='',max_length=100)
class Payee(Request):
    code:str=Field(min_length=1,max_length=40)
    name:str=Field(min_length=1,max_length=120)
    account_name:str=Field(min_length=1,max_length=120)
    account_reference:str=Field(min_length=1,max_length=120)
    active:bool=Field(default=True,strict=True)
class Income(Request):
    code:str=Field(min_length=1,max_length=40)
    name:str=Field(min_length=1,max_length=120)
    unit:str=Field(min_length=1,max_length=20)
    standard_fee_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    active:bool=Field(default=True,strict=True)
SCHEMAS={'quote':Quote,'approve':Approval,'authorize':Authorization,'submit':Submit,'external_result':Result,'fulfill':Fulfillment,
    'receive':Cash,'disburse':Disbursement,'thirdparty_return':Returned,'termination':Termination,'termination_approve':Plan,
    'consent':Plan,'termination_apply':Plan,'refund':Refund,'termination_cancel':PlanCancel,'cancel':Reason}

@router.get('')
def listing(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.list_orders(db,user,page)
@router.get('/catalog')
def catalog(db=Depends(get_db),user=Depends(get_user)):return service.catalog(db,user)
@router.post('/payees',status_code=201)
def payee(body:Payee,db=Depends(get_write_db),user=Depends(get_user)):return service.master(db,user,body.request_id,'payees',body.model_dump(exclude={'request_id'}))
@router.post('/income-items',status_code=201)
def income(body:Income,db=Depends(get_write_db),user=Depends(get_user)):return service.master(db,user,body.request_id,'income-items',body.model_dump(exclude={'request_id'}))
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):return service.create(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.get('/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):return service.describe(db,user,service.get_order(db,user,case_id))
@router.post('/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'服务动作不存在')
    try:v=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对本次服务字段与原件；金额为整数分，数量为整数千分位')
    return service.command(db,user,case_id,body.request_id,body.version,action,v)
