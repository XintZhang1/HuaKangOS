"""Typed combination recharge commands; no component amount overrides."""
from datetime import date
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .db import get_db,get_write_db
from .security import get_user
from . import recharge_bundle_service as service

router = APIRouter(prefix='/api/recharge-bundles', tags=['会员充值组合套餐'])
Key = Annotated[int, Field(gt=0, strict=True)]
class Strict(BaseModel): model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Request(Strict): request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
class Component(Strict):
    benefit_rule_id: Key
    units_per_share: int = Field(gt=0, le=100000000, strict=True)
class Rule(Strict):
    code: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=2, max_length=120)
    enabled: bool = Field(default=False, strict=True)
    principal_cents_per_share: int = Field(gt=0, le=100000000000, strict=True)
    allowed_store_ids: list[Key] = Field(min_length=1, max_length=100)
    sale_starts_on: date
    sale_ends_on: date
    refund_policy: Literal['whole_unused_before_expiry','whole_unused_anytime']
    refund_terms: str = Field(min_length=10, max_length=1000)
    components: list[Component] = Field(min_length=1, max_length=4)
class RuleRequest(Request): values: Rule
class Shares(Strict):
    shares: int = Field(gt=0, le=10000, strict=True)
    terms_accepted: Literal[True]
class Purchase(Shares): rule_id: Key
class Refund(Shares): purchase_id: Key
class Create(Request):
    customer_id: Key
    purpose: Literal['purchase','refund']
    values: dict
    reason: str = Field(min_length=2, max_length=500)
class Command(Request):
    version: Key
    case_version: Key
    member_version: Key
    values: dict
class Reason(Strict): reason: str = Field(min_length=2, max_length=500)
class Evidence(Reason): evidence_id: Key
class Execute(Evidence):
    account_id: Key
    reference: str = Field(min_length=1, max_length=100)

def validate(schema, values):
    try: return schema.model_validate(values).model_dump(mode='json')
    except ValidationError: raise HTTPException(422, '充值组合字段无效；份数须为正整数，并明确确认冻结的整份退款条款')

@router.get('/rules')
def rules(db=Depends(get_db), user=Depends(get_user)): return service.rules(db,user)
@router.post('/rules', status_code=201)
def create_rule(body: RuleRequest, db=Depends(get_write_db), user=Depends(get_user)):
    return service.create_rule(db,user,body.request_id,body.values.model_dump(mode='json'))
@router.get('/purchases')
def purchases(customer_id: int=Query(gt=0), db=Depends(get_db), user=Depends(get_user)):
    return service.purchases(db,user,customer_id)
@router.get('/orders')
def orders(db=Depends(get_db), user=Depends(get_user)): return service.orders(db,user)
@router.get('/orders/{key}')
def order(key: int, db=Depends(get_db), user=Depends(get_user)): return service.describe(db,user,key)
@router.post('/orders', status_code=201)
def create(body: Create, db=Depends(get_write_db), user=Depends(get_user)):
    values=validate(Purchase if body.purpose=='purchase' else Refund,body.values)
    return service.create_order(db,user,body.request_id,body.customer_id,body.purpose,values,body.reason)
@router.post('/orders/{key}/actions/{action}')
def command(key: int, action: str, body: Command, db=Depends(get_write_db), user=Depends(get_user)):
    schema={'approve':Evidence,'execute':Execute,'cancel':Reason,'reject':Reason}.get(action)
    if not schema: raise HTTPException(404,'充值组合办理动作不存在')
    return service.command(db,user,key,body.request_id,body.version,body.case_version,body.member_version,action,validate(schema,body.values))
