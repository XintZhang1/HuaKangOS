"""Commercial changes use their own strict inputs; physical actions retain the engine API."""
from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends
from pydantic import BaseModel,ConfigDict,Field
from .db import get_db,get_write_db
from .security import get_user
from . import sales_quote_service as service

router=APIRouter(prefix='/api/sales-quotes',tags=['车辆报价与变更'])
Key=Annotated[int,Field(gt=0,strict=True)]
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Quote(Strict):
    model_id:Key
    model_version:Key
    amount_cents:int=Field(gt=0,le=999999999999,strict=True)
    delivery_due:date
    valid_until:date
    addon:bool=Field(default=False,strict=True)
    insurance:bool=Field(default=False,strict=True)
    agency:bool=Field(default=False,strict=True)
    terms:str=Field(min_length=2,max_length=1500)
    reason:str=Field(min_length=2,max_length=500)
class Create(Request):
    customer_id:Key|None=None
    customer_name:str=Field(default='',max_length=100)
    customer_phone:str=Field(default='',max_length=30)
    confirm_new_customer:bool=Field(default=False,strict=True)
    lead_id:Key|None=None
    lead_version:Key|None=None
    quote:Quote
class Revise(Request):
    version:Key
    quote:Quote

@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    # Keep the existing-customer envelope identical for old request receipts.
    values=body.model_dump(mode='json',exclude={'request_id','customer_name','customer_phone','confirm_new_customer'})
    if not body.customer_id or body.customer_name or body.customer_phone or body.confirm_new_customer:
        values.update(customer_name=body.customer_name,customer_phone=body.customer_phone,
                      confirm_new_customer=body.confirm_new_customer)
    return service.create(db,user,body.request_id,values)
@router.get('/orders/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.detail(db,user,key)
@router.get('/orders/{key}/vehicles')
def vehicles(key:int,db=Depends(get_db),user=Depends(get_user)):return service.vehicles(db,user,key)
@router.post('/orders/{key}/quotes',status_code=201)
def revise(key:int,body:Revise,db=Depends(get_write_db),user=Depends(get_user)):
    return service.propose(db,user,key,body.request_id,body.version,body.quote.model_dump(mode='json'))
