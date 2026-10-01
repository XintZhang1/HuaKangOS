"""Explicit post-performance correction commands; original cases remain history."""
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError,StrictInt
from .db import get_db,get_write_db
from .security import get_user
from . import aftercare_service as service

router=APIRouter(prefix='/api/aftercare/orders',tags=['售后纠正'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Create(Request,Reason):
    source_case_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    scenario:Literal['sale_termination','vehicle_return','repair_refund']
class Command(Request):
    version:int=Field(gt=0,strict=True)
    source_versions:dict[str,StrictInt]
    values:dict=Field(default_factory=dict)
class Execution(Evidence):
    source_id:int=Field(gt=0,strict=True)
    outcome:Literal['not_started','stopped','completed']
    external_result:Literal['not_required','terminated']
    result:str=Field(min_length=2,max_length=1000)
class Tender(Strict):
    kind:Literal['cash','principal','benefit','advance','repair_package']
    original_id:int=Field(gt=0,strict=True)
    units:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class Line(Strict):
    source_id:int=Field(gt=0,strict=True)
    credit_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    returns:list[Tender]=Field(default_factory=list,max_length=200)
    commission_credit_cents:int|None=Field(default=None,ge=0,le=1_000_000_000_000,strict=True)
class Plan(Reason):lines:list[Line]=Field(min_length=1,max_length=100)
class Approval(Reason,Evidence):pass
class Money(Evidence):
    account_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Refund(Money):tender_id:int=Field(gt=0,strict=True)
class Collect(Money):source_id:int=Field(gt=0,strict=True)
SCHEMAS={'execution':Execution,'plan':Plan,'approve':Approval,'reject':Reason,'cancel_plan':Reason,'customer_confirm':Evidence,'cancel':Reason,'apply':Evidence,'refund':Refund,'collect':Collect}

@router.get('')
def orders(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.list_orders(db,user,page)
@router.get('/sources')
def sources(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.sources(db,user,page)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):return service.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):return service.describe(db,user,service.get_order(db,user,case_id))
@router.post('/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'售后动作不存在')
    try:
        if any(not k.isdigit() or type(v)!=int or v<1 for k,v in body.source_versions.items()):raise ValueError()
        values=schema.model_validate(body.values).model_dump()
    except (ValueError,ValidationError):raise HTTPException(422,'请核对售后字段、原单版本和凭据；金额为整数分，权益只能选择原整数单位')
    return service.command(db,user,case_id,body.request_id,body.version,body.source_versions,action,values)
