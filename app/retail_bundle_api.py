"""Explicit rule publication and sales; the ordinary retail commands own fulfillment."""
from datetime import date
from typing import Annotated, Literal
from fastapi import APIRouter,Depends,Query
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .db import get_db,get_write_db
from .security import get_user
from . import retail_bundle_service as service
from .member_pricing_api import Selection

router=APIRouter(prefix='/api/retail-bundles',tags=['精品销售套餐'])
Key=Annotated[int,Field(gt=0,strict=True)]
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Component(Strict):
    item_id:Key
    quantity_milli_per_set:int=Field(gt=0,le=1_000_000_000,strict=True)
    goods_reference_cents:int=Field(ge=0,le=1_000_000_000,strict=True)
    work_item_id:Key|None=None
    installation_reference_cents:int=Field(default=0,ge=0,le=1_000_000_000,strict=True)
    @model_validator(mode='after')
    def work(self):
        if self.installation_reference_cents and not self.work_item_id:raise ValueError('无安装项目不能配置安装金额')
        return self
class Rule(Strict):
    code:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=120)
    enabled:bool=Field(default=False,strict=True)
    sale_starts_on:date
    sale_ends_on:date
    price_cents_per_set:int=Field(gt=0,le=1_000_000_000,strict=True)
    refund_terms:str=Field(min_length=10,max_length=1500)
    components:list[Component]=Field(min_length=1,max_length=100)
class Publish(Request):
    base_version:int=Field(ge=0,strict=True)
    values:Rule
class Sale(Request):
    member_pricing:Selection|None=None
    rule_id:Key
    rule_version:Key
    sets:int=Field(gt=0,le=10000,strict=True)
    customer_id:Key
    related_repair_id:Key|None=None
    terms_accepted:Literal[True]

@router.get('/rules')
def rules(db=Depends(get_db),user=Depends(get_user)):return service.rules(db,user)
@router.post('/rules',status_code=201)
def publish(body:Publish,db=Depends(get_write_db),user=Depends(get_user)):
    return service.create_rule(db,user,body.request_id,body.base_version,body.values.model_dump(mode='json'))
@router.get('/rules/{key}/preview')
def preview(key:int,sets:int=Query(1,ge=1,le=10000),db=Depends(get_db),user=Depends(get_user)):
    return service.preview(db,user,key,sets)
@router.post('/sales',status_code=201)
def sale(body:Sale,db=Depends(get_write_db),user=Depends(get_user)):
    return service.create_sale(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
