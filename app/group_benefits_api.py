from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .db import get_db
from .security import get_user
from . import group_benefits_service as service

router=APIRouter(prefix='/api/group/benefits',tags=['集团权益'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class RuleValues(Strict):
    code:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=120)
    kind:Literal['bonus','points','coupon','package']
    allowed_store_ids:list[Annotated[int,Field(gt=0,strict=True)]]=Field(min_length=1,max_length=100)
    credit_cents_per_unit:int=Field(gt=0,le=100000000,strict=True)
    settlement_cents_per_unit:int=Field(ge=0,le=100000000,strict=True)
    sale_cents_per_unit:int=Field(ge=0,le=100000000,strict=True)
    exchange_points_per_unit:int=Field(default=0,ge=0,le=100000000,strict=True)
    refund_policy:Literal['none','unused_before_expiry','unused_anytime']
    discount_bearer:Literal['group','service_store']
    validity_days:int=Field(gt=0,le=3650,strict=True)
    service_code:str=Field(default='',max_length=40)
class RuleRequest(Request):values:RuleValues
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Reason):
    evidence_id:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
class Grant(Evidence):
    rule_id:int=Field(gt=0,strict=True)
    case_id:int=Field(gt=0,strict=True)
    units:int=Field(gt=0,le=100000000,strict=True)
class Purchase(Grant):
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class Wallet(Reason):
    wallet_id:int=Field(gt=0,strict=True)
    wallet_version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
class Units(Wallet):
    case_id:int=Field(gt=0,strict=True)
    evidence_id:int=Field(gt=0,strict=True)
    units:int=Field(gt=0,le=100000000,strict=True)
class Exchange(Units):target_rule_id:int=Field(gt=0,strict=True)
class Reservation(Wallet):
    reservation_id:int=Field(gt=0,strict=True)
    reservation_version:int=Field(gt=0,strict=True)
class Capture(Reservation):evidence_id:int=Field(gt=0,strict=True)
class Reverse(Wallet):
    original_id:int=Field(gt=0,strict=True)
    units:int=Field(gt=0,le=100000000,strict=True)
    evidence_id:int=Field(gt=0,strict=True)
class RefundRequest(Wallet):
    units:int=Field(gt=0,le=100000000,strict=True)
    evidence_id:int=Field(gt=0,strict=True)
class RefundReview(Wallet):
    refund_id:int=Field(gt=0,strict=True)
    refund_version:int=Field(gt=0,strict=True)
class RefundPay(RefundReview):
    evidence_id:int=Field(gt=0,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)

SCHEMAS={'grant':Grant,'purchase':Purchase,'reserve':Units,'adjust':Units,'exchange':Exchange,
    'capture':Capture,'release':Reservation,'reverse':Reverse,'refund_request':RefundRequest,
    'refund_approve':RefundReview,'refund_reject':RefundReview,'refund_cancel':RefundReview,'refund':RefundPay}


@router.get('/rules')
def rules(db=Depends(get_db),user=Depends(get_user)):return service.rules(db,user)
@router.post('/rules',status_code=201)
def create_rule(body:RuleRequest,db=Depends(get_db),user=Depends(get_user)):
    return service.create_rule(db,user,body.request_id,body.values.model_dump())
@router.get('/members')
def member(customer_id:int,db=Depends(get_db),user=Depends(get_user)):
    return service.member_detail(db,user,customer_id)
@router.get('/reconciliation')
def reconciliation(db=Depends(get_db),user=Depends(get_user)):
    with service.group.authority(db,user,service.eng.MANAGEMENT):
        return service.analytics_rows(db,user)
@router.post('/members/{member_id}/actions/{action}')
def command(member_id:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'权益动作不存在')
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'权益字段无效：单位必须为正整数，请核对来源、版本和必填事实')
    return service.command(db,user,member_id,body.request_id,body.version,action,values)
