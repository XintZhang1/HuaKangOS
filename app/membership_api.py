from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .db import get_db,get_write_db
from .security import get_user
from . import membership_service as service

router=APIRouter(prefix='/api/membership',tags=['集团会员办理'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Rule(Strict):
    code:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=100)
    enabled:bool=False
    allowed_store_ids:list[Annotated[int,Field(gt=0,strict=True)]]=Field(min_length=1,max_length=100)
    validity_months:int=Field(gt=0,le=120,strict=True)
    fee_cents:int=Field(ge=0,le=100000000000,strict=True)
    fee_owner:Literal['collecting_store']
    refund_policy:Literal['none','before_start']
    points_enabled:bool=False
    points_numerator:int=Field(gt=0,le=1000000,strict=True)
    points_denominator_fen:int=Field(gt=0,le=100000000000,strict=True)
    points_benefit_rule_id:int|None=Field(default=None,gt=0,strict=True)
class RuleRequest(Request):values:Rule
class Create(Request):
    customer_id:int=Field(gt=0,strict=True)
    purpose:Literal['topup','benefit_issue','card_issue','card_loss','card_replace','renew','tier_change','renew_refund','points_adjust']
    reason:str=Field(min_length=2,max_length=500)
    values:dict
class Empty(Strict):pass
class Topup(Strict):amount_cents:int=Field(gt=0,le=100000000000,strict=True)
class Benefit(Strict):
    action:Literal['purchase','grant']=Field(description='purchase购买券或套餐；grant按真实权益规则赠送新批次，正向积分使用kind=points且售价为零的规则。')
    rule_id:int=Field(gt=0,strict=True)
    units:int=Field(gt=0,le=100000000,strict=True)
class Card(Strict):card_id:int=Field(gt=0,strict=True)
class Tier(Strict):rule_id:int=Field(gt=0,strict=True)
class Refund(Strict):period_id:int=Field(gt=0,strict=True)
class Points(Strict):
    action:Literal['adjust','exchange','settle_debt']=Field(description='adjust扣减原积分钱包；exchange兑换券包；settle_debt用现有积分抵原欠额。正向赠送使用benefit_issue/grant。')
    wallet_id:int=Field(gt=0,strict=True)
    units:int=Field(gt=0,le=100000000,strict=True)
    target_rule_id:int|None=Field(default=None,gt=0,strict=True)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    member_version:int=Field(gt=0,strict=True)
    values:dict
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Reason):evidence_id:int=Field(gt=0,strict=True)
class Execute(Evidence):
    account_id:int|None=Field(default=None,gt=0,strict=True)
    reference:str|None=Field(default=None,min_length=1,max_length=100)
    wallet_version:int|None=Field(default=None,gt=0,strict=True)

PURPOSE_SCHEMAS={'topup':Topup,'benefit_issue':Benefit,'card_issue':Empty,'card_loss':Card,'card_replace':Card,
    'renew':Tier,'tier_change':Tier,'renew_refund':Refund,'points_adjust':Points}

def validate(schema,values):
    try:return schema.model_validate(values).model_dump(exclude_none=True)
    except ValidationError:raise HTTPException(422,'会员办理字段无效，请核对明确用途、版本和凭据；金额用整数分')

def validate_purpose_values(purpose,values):
    """Share the native values checks with read-only assistant preparation."""
    schema=PURPOSE_SCHEMAS.get(purpose)
    if schema is None:raise HTTPException(422,'会员办理用途不存在，请核对原操作目录')
    values=validate(schema,values)
    if purpose=='points_adjust' and (values['action']=='exchange')!=bool(values.get('target_rule_id')):raise HTTPException(422,'积分兑换须选目标券包；普通扣减不得附带兑换目标')
    return values
@router.get('/rules')
def rules(db=Depends(get_db),user=Depends(get_user)):return service.rules(db,user)
@router.post('/rules',status_code=201)
def rule(body:RuleRequest,db=Depends(get_write_db),user=Depends(get_user)):return service.create_rule(db,user,body.request_id,body.values.model_dump())
@router.get('/members')
def member(customer_id:int=Query(gt=0),db=Depends(get_db),user=Depends(get_user)):return service.member_detail(db,user,customer_id)
@router.get('/cards/lookup')
def card(number:str=Query(min_length=1,max_length=40),db=Depends(get_db),user=Depends(get_user)):return service.lookup_card(db,user,number)
@router.get('/orders')
def orders(db=Depends(get_db),user=Depends(get_user)):return service.orders(db,user)
@router.get('/orders/{key}')
def order(key:int,db=Depends(get_db),user=Depends(get_user)):return service.describe(db,user,key)
@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    values=validate_purpose_values(body.purpose,body.values)
    return service.create_order(db,user,body.request_id,body.customer_id,body.purpose,values,body.reason)
@router.post('/orders/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schema={'execute':Execute,'approve':Evidence,'cancel':Reason,'reject':Reason}.get(action)
    if not schema:raise HTTPException(404,'会员办理动作不存在')
    return service.command(db,user,key,body.request_id,body.version,body.case_version,body.member_version,action,validate(schema,body.values))
