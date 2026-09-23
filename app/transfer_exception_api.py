"""Explicit, versioned transport exception actions; no arbitrary state endpoint."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .db import get_db
from .security import get_user
from . import transfer_exception_service as service

router=APIRouter(prefix='/api/transfer-exceptions',tags=['物资调拨运输差异'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Create(Request):
    transfer_id:int=Field(gt=0,strict=True)
    version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    original_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    finding:Literal['missing','damaged']
    result:str=Field(min_length=4,max_length=1000)
    evidence_id:int=Field(gt=0,strict=True)
    due_date:date
    confirmed:Literal[True]
class Command(Request):
    version:int=Field(gt=0,strict=True)
    transfer_version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    values:dict
class Proof(Strict):evidence_id:int=Field(gt=0,strict=True)
class Physical(Proof):
    result:str=Field(min_length=4,max_length=1000)
    confirmed:Literal[True]
class Reason(Proof):reason:str=Field(min_length=4,max_length=1000)
class Plan(Reason):
    source_bearer_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    destination_bearer_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
class Review(Reason):plan_id:int=Field(gt=0,strict=True)
class Post(Proof):confirmed:Literal[True]
class RecoveryTarget(Reason):
    target_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    due_date:date
class RecoveryCreate(RecoveryTarget):
    counterparty_kind:Literal['carrier','insurer']
    counterparty_id:int=Field(gt=0,strict=True)
class RecoveryKey(Proof):
    claim_id:int=Field(gt=0,strict=True)
    claim_version:int=Field(gt=0,strict=True)
class RecoveryPlan(RecoveryKey,RecoveryTarget):pass
class RecoveryReview(RecoveryKey,Reason):plan_id:int=Field(gt=0,strict=True)
class RecoveryCash(RecoveryKey):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=2,max_length=100)
    business_date:date
    confirmed:Literal[True]
class RecoveryRefund(RecoveryCash):original_id:int=Field(gt=0,strict=True)

SCHEMAS={'observe':Physical,'plan':Plan,'approve':Review,'reject_plan':Review,'dispose':Physical,'post_loss':Post,'cancel':Reason}
SCHEMAS.update(recovery_create=RecoveryCreate,recovery_plan=RecoveryPlan,recovery_approve=RecoveryReview,
    recovery_reject=RecoveryReview,recovery_cancel=RecoveryReview,recovery_receive=RecoveryCash,recovery_refund=RecoveryRefund)


@router.get('')
def listing(transfer_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    return service.list_exceptions(db,user,transfer_id)
@router.get('/origins/{transfer_id}')
def origins(transfer_id:int,db=Depends(get_db),user=Depends(get_user)):return service.available_origins(db,user,transfer_id)
@router.get('/recovery-catalog')
def recovery_catalog(db=Depends(get_db),user=Depends(get_user)):return service.recovery_catalog(db,user)
@router.get('/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.detail(db,user,key)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    return service.create(db,user,**body.model_dump(exclude={'confirmed'}))
@router.post('/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if schema is None:raise HTTPException(404,'没有此调拨差异动作')
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对本店实际凭据、整数数量与金额，并明确本人确认')
    return service.command(db,user,key,body.request_id,body.version,body.transfer_version,body.case_version,action,values)
