"""Explicit insurance actions; integer fen and frozen source versions."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .db import get_db,get_write_db
from .security import get_user
from . import insurance_service as service
router=APIRouter(prefix='/api/insurance-orders',tags=['保险核价与结算'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Create(Request,Reason):
    customer_id:int=Field(gt=0,strict=True)
    customer_vehicle_id:int|None=Field(default=None,gt=0,strict=True)
    source_order_id:int|None=Field(default=None,gt=0,strict=True)
    source_version:int|None=Field(default=None,gt=0,strict=True)
    previous_policy_id:int|None=Field(default=None,gt=0,strict=True)
    renewal_task_id:int|None=Field(default=None,gt=0,strict=True)
    renewal_version:int|None=Field(default=None,gt=0,strict=True)
    delivery_blocking:bool=Field(default=False,strict=True)
    due_date:date
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Line(Strict):
    name:str=Field(min_length=1,max_length=100)
    premium_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class Quote(Reason):
    insurer_id:int=Field(gt=0,strict=True)
    insurer_version:int=Field(gt=0,strict=True)
    collection_mode:Literal['store_collect','customer_direct']
    payee_account_name:str=Field(default='',max_length=120)
    payee_account_reference:str=Field(default='',max_length=120)
    lines:list[Line]=Field(min_length=1,max_length=40)
    expected_commission_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    start_date:date
    end_date:date
    valid_until:date
    terms:str=Field(min_length=2,max_length=1500)
class Review(Evidence,Reason):decision:Literal['approved','rejected']
class Consent(Evidence):
    quote_id:int=Field(gt=0,strict=True)
    digest:str=Field(min_length=64,max_length=64)
class Submit(Evidence):
    external_reference:str=Field(min_length=1,max_length=120)
    business_date:date
class Result(Evidence):
    submission_id:int=Field(gt=0,strict=True)
    outcome:Literal['issued','rejected','need_documents']
    policy_number:str=Field(default='',max_length=120)
    result:str=Field(min_length=2,max_length=1000)
    business_date:date
class Cash(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
    business_date:date
class Disburse(Cash):tender_id:int=Field(gt=0,strict=True)
class Returned(Cash):original_id:int=Field(gt=0,strict=True)
class Direct(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    original_id:int|None=Field(default=None,gt=0,strict=True)
    external_reference:str=Field(min_length=1,max_length=120)
    business_date:date
class Selection(Strict):
    tender_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class Termination(Evidence,Reason):
    retained_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    external_result:Literal['terminated','not_issued']
    returns:list[Selection]=Field(default_factory=list,max_length=200)
class Plan(Evidence):plan_id:int=Field(gt=0,strict=True)
class PlanReview(Plan,Review):pass
class PlanConsent(Plan):digest:str=Field(min_length=64,max_length=64)
class PlanCancel(Reason):plan_id:int=Field(gt=0,strict=True)
class Refund(Plan):
    tender_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int|None=Field(default=None,gt=0,strict=True)
    reference:str=Field(default='',max_length=100)
    business_date:date
class Commission(Evidence,Reason):target_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
class CommissionReview(Review):
    confirmation_id:int=Field(gt=0,strict=True)
    business_date:date
class CommissionCash(Cash):
    confirmation_id:int=Field(gt=0,strict=True)
    original_id:int|None=Field(default=None,gt=0,strict=True)
SCHEMAS={'quote':Quote,'review':Review,'authorize':Consent,'quote_cancel':Reason,'submit':Submit,'result':Result,'receive':Cash,
    'disburse':Disburse,'insurer_return':Returned,'direct_paid':Direct,'direct_return':Direct,'termination':Termination,
    'termination_review':PlanReview,'termination_consent':PlanConsent,'termination_apply':Plan,'termination_cancel':PlanCancel,
    'refund':Refund,'commission':Commission,'commission_review':CommissionReview,'commission_receive':CommissionCash,'commission_return':CommissionCash,'cancel':Reason}
@router.get('')
def listing(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.list_orders(db,user,page)
@router.get('/catalog')
def catalog(q:str=Query('',max_length=100),customer_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):return service.catalog(db,user,q,customer_id)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):return service.create(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.get('/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):return service.describe(db,user,service.get_order(db,user,case_id))
@router.post('/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'保险动作不存在')
    try:v=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对保险办理字段、实际原件与原版本；金额须为整数分')
    return service.command(db,user,case_id,body.request_id,body.version,action,v)
