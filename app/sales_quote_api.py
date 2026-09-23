"""Commercial changes use their own strict inputs; physical actions retain the engine API."""
from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends
from pydantic import BaseModel,ConfigDict,Field
from .db import get_db
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
    customer_id:Key
    lead_id:Key|None=None
    lead_version:Key|None=None
    quote:Quote
class Revise(Request):
    version:Key
    quote:Quote

@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    return service.create(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.get('/orders/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.detail(db,user,key)
@router.get('/orders/{key}/vehicles')
def vehicles(key:int,db=Depends(get_db),user=Depends(get_user)):return service.vehicles(db,user,key)
@router.post('/orders/{key}/quotes',status_code=201)
def revise(key:int,body:Revise,db=Depends(get_db),user=Depends(get_user)):
    return service.propose(db,user,key,body.request_id,body.version,body.quote.model_dump(mode='json'))
