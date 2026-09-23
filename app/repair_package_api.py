"""Separate employee actions for mixed prepaid repair components."""
from typing import Literal,Annotated
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,ValidationError
from .db import get_db
from .security import get_user
from .repair_api import Strict,Request,Command,Reason,Evidence,Line,Quote
from . import repair_package_service as service

router=APIRouter(prefix='/api/repair-packages',tags=['混合作业配件套餐'])
Positive=Annotated[int,Field(gt=0,le=1_000_000_000,strict=True)]
Fen=Annotated[int,Field(ge=0,le=1_000_000_000_000,strict=True)]
class Component(Strict):
    key:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    kind:Literal['work','part']
    name:str=Field(min_length=1,max_length=120)
    unit:str=Field(min_length=1,max_length=20)
    specification:str=Field(min_length=2,max_length=200)
    quantity_milli:Positive
    credit_cents:Positive
    paid_cents:Fen
    settlement_cents:Fen
class Rule(Request):
    code:str=Field(min_length=1,max_length=40)
    name:str=Field(min_length=2,max_length=120)
    allowed_store_ids:list[Positive]=Field(min_length=1,max_length=100)
    validity_days:int=Field(gt=0,le=3650,strict=True)
    refund_policy:Literal['none','unused_before_expiry','unused_anytime']
    discount_bearer:Literal['group','service_store']
    components:list[Component]=Field(min_length=2,max_length=50)
class Map(Request,Reason):
    component_key:str=Field(min_length=1,max_length=40)
    source_id:Positive
class Decision(Request,Reason):pass
class Purchase(Request):
    rule_id:Positive
    member_id:Positive
    case_id:Positive
    case_version:Positive
    sets:int=Field(gt=0,le=10000,strict=True)
class Source(Strict):case_version:Positive
class Authorize(Source,Evidence):pass
class Cancel(Source,Reason):pass
class Cash(Source,Evidence):
    amount_cents:Fen
    account_id:Positive
    reference:str=Field(min_length=1,max_length=100)
class RefundCash(Source,Evidence):
    amount_cents:Fen
    account_id:int|None=Field(default=None,gt=0,strict=True)
    reference:str|None=Field(default=None,min_length=1,max_length=100)
class Choice(Strict):
    lot_id:Positive
    quantity_milli:Positive
class Refund(Source,Evidence,Reason):selections:list[Choice]=Field(min_length=1,max_length=50)
class PackageLine(Line):
    package_lot_id:int|None=Field(default=None,gt=0,strict=True)
    package_lot_version:int|None=Field(default=None,gt=0,strict=True)
    charge_scope:Literal['original_liability','customer_extra']|None=None
    source_line_id:int|None=Field(default=None,gt=0,strict=True)
class Retained(Strict):
    line_key:str=Field(min_length=1,max_length=40)
    quantity_milli:int=Field(ge=0,le=1_000_000_000,strict=True)
class PackageQuote(Quote):
    lines:list[PackageLine]=Field(default_factory=list,max_length=100)
    package_retained:list[Retained]|None=Field(default=None,max_length=100)
class MaterialReturn(Request,Evidence):
    version:Positive
    source_version:Positive
    hold_id:Positive
    original_stock_id:Positive
    quantity_milli:Positive
    passed:Literal[True]
    result:str=Field(min_length=2,max_length=1000)

def values(schema,raw):
    try:return schema.model_validate(raw).model_dump(mode='json')
    except ValidationError as e:raise HTTPException(422,'请核对套餐数量、金额、当前版本及原来源字段') from e
@router.get('/rules')
def rules(db=Depends(get_db),user=Depends(get_user)):return service.rules(db,user)
@router.post('/rules',status_code=201)
def rule(body:Rule,db=Depends(get_db),user=Depends(get_user)):return service.create_rule(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.post('/rules/{key}/actions/{action}')
def decision(key:int,action:Literal['approve','reject','cancel','revoke'],body:Decision,db=Depends(get_db),user=Depends(get_user)):return service.decide_rule(db,user,body.request_id,key,action,{'reason':body.reason})
@router.post('/rules/{key}/mappings',status_code=201)
def mapping(key:int,body:Map,db=Depends(get_db),user=Depends(get_user)):return service.map_component(db,user,body.request_id,key,body.model_dump(exclude={'request_id'}))
@router.get('/members/{key}/purchases')
def purchases(key:int,db=Depends(get_db),user=Depends(get_user)):return service.purchases(db,user,key)
@router.post('/purchases',status_code=201)
def purchase(body:Purchase,db=Depends(get_db),user=Depends(get_user)):return service.create_purchase(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.post('/purchases/{key}/actions/{action}')
def purchase_action(key:int,action:Literal['authorize','issue','cancel','refund_request'],body:Command,db=Depends(get_db),user=Depends(get_user)):
    v=values({'authorize':Authorize,'issue':Cash,'cancel':Cancel,'refund_request':Refund}[action],body.values)
    if action=='refund_request':return service.refund_request(db,user,body.request_id,key,body.version,v)
    return service.purchase_action(db,user,body.request_id,key,body.version,action,v)
@router.post('/refunds/{key}/actions/{action}')
def refund_action(key:int,action:Literal['approve','reject','cancel','pay'],body:Command,db=Depends(get_db),user=Depends(get_user)):return service.refund_action(db,user,body.request_id,key,body.version,action,values(RefundCash if action=='pay' else Cancel,body.values))
@router.post('/orders/{key}/quote')
def quote(key:int,body:Command,db=Depends(get_db),user=Depends(get_user)):
    from .repair_service import command
    v=values(PackageQuote,body.values)
    for line in v['lines']:
        if bool(line.get('package_lot_id'))!=bool(line.get('package_lot_version')):raise HTTPException(422,'套餐组件和当前版本必须同时明确')
        for field in ('charge_scope','source_line_id'):
            if line.get(field) is None:line.pop(field,None)
    return command(db,user,key,body.request_id,body.version,'quote',v)
@router.post('/orders/{key}/capture')
def capture(key:int,body:Command,db=Depends(get_db),user=Depends(get_user)):return service.capture(db,user,body.request_id,key,body.version,values(Evidence,body.values))
@router.post('/aftercare/{key}/return-material')
def material_return(key:int,body:MaterialReturn,db=Depends(get_db),user=Depends(get_user)):
    from .repair_package_aftercare import return_material
    return return_material(db,user,body.request_id,key,body.model_dump(exclude={'request_id'}))
@router.get('/aftercare/{key}/return-targets')
def return_targets(key:int,db=Depends(get_db),user=Depends(get_user)):
    from .repair_package_aftercare import return_targets
    return return_targets(db,user,key)
