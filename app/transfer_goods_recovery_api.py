"""Explicit commands for found goods and associated original compensation."""
from datetime import date
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,StrictBool,ValidationError
from .db import get_db,get_write_db
from .security import get_user
from . import transfer_goods_recovery_service as s

router=APIRouter(prefix='/api/transfer-goods-recoveries',tags=['损失后找到原物资'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Proof(Strict):evidence_id:int=Field(gt=0,strict=True)
class Actual(Proof):
    confirmed:StrictBool
class Physical(Actual):result:str=Field(min_length=4,max_length=1000)
class Quality(Physical):passed:StrictBool
class Reason(Proof):reason:str=Field(min_length=4,max_length=1000)
class Review(Reason):plan_id:int=Field(gt=0,strict=True)
class Create(Request,Physical):
    transfer_id:int=Field(gt=0,strict=True)
    loss_id:int=Field(gt=0,strict=True)
    version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    due_date:date
    previous_recovery_id:int|None=Field(default=None,gt=0,strict=True)
class TraceReason(Reason):
    confirmed:StrictBool
class TraceReview(TraceReason):
    search_id:int=Field(gt=0,strict=True)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    transfer_version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    values:dict
class Claim(Proof):
    claim_id:int=Field(gt=0,strict=True)
    claim_version:int=Field(gt=0,strict=True)
class Terms(Claim,Reason):
    target_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    due_date:date
class TermsReview(Claim,Review):pass
class Refund(Claim,Actual):
    original_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=2,max_length=100)
    business_date:date

SCHEMAS=dict(match=Physical,inspect=Quality,ship=Physical,receive=Quality,plan=Reason,approve=Review,reject=Review,
             dispose=Physical,restore=Actual,finish_bad=Actual,cancel=Physical,terms=Terms,terms_approve=TermsReview,
             terms_reject=TermsReview,terms_cancel=TermsReview,pending_cancel=TermsReview,refund=Refund,
             trace_open=TraceReason,trace_approve=TraceReview,trace_reject=TraceReview)


@router.get('/origins/{transfer_id}')
def origins(transfer_id:int,db=Depends(get_db),user=Depends(get_user)):return s.available_origins(db,user,transfer_id)
@router.get('')
def listing(transfer_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):return s.listing(db,user,transfer_id)
@router.get('/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return s.detail(db,user,key)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    if body.confirmed is not True:raise HTTPException(422,'须本人确认实际找到物资，不能把猜测当事实')
    return s.create(db,user,body.request_id,**body.model_dump(exclude={'request_id','confirmed'}))
@router.post('/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'没有此找回原物资动作')
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对本店原件、整数金额数量和本人实际确认')
    if 'confirmed' in values and values['confirmed'] is not True:raise HTTPException(422,'须本人确认本次实际事实')
    return s.command(db,user,key,body.request_id,body.version,body.transfer_version,body.case_version,action,values)
