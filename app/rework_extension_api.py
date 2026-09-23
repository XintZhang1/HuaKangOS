"""Explicit opt-in rework contract; no generic case mutation or archive access."""
from datetime import datetime
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,field_validator
from .db import get_db
from .security import get_user
from .service_intake_api import Strict,Request,Command,Reason,values
from .repair_api import Line,Quote
from . import rework_extension_service as service
from . import repair_service

router=APIRouter(prefix='/api/rework-extensions',tags=['原责任返修与新增自费'])
class Proposal(Request):
    source_case_id:int=Field(gt=0,strict=True)
    source_case_version:int=Field(gt=0,strict=True)
    source_line_ids:list[Annotated[int,Field(gt=0,strict=True)]]=Field(min_length=1,max_length=100)
    to_store_id:int=Field(gt=0,strict=True)
    to_vehicle_id:int=Field(gt=0,strict=True)
    recipient_id:int=Field(gt=0,strict=True)
    original_liability_limit_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    evidence_id:int=Field(gt=0,strict=True)
    reason:str=Field(min_length=2,max_length=1000)
    expires_at:datetime
    @field_validator('expires_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError('请提供明确时区')
        return value
class Accept(Request):
    grant_id:int=Field(gt=0,strict=True)
    grant_version:int=Field(gt=0,strict=True)
    resource_id:int=Field(gt=0,strict=True)
    reason:str=Field(min_length=2,max_length=1000)
class ScopeLine(Line):
    charge_scope:Literal['original_liability','customer_extra']
    source_line_id:int|None=Field(default=None,gt=0,strict=True)
class ScopeQuote(Quote):lines:list[ScopeLine]=Field(default_factory=list,max_length=100)

@router.get('/grants')
def grants(db=Depends(get_db),user=Depends(get_user)):return service.list_grants(db,user)
@router.get('/targets/{source_id}')
def targets(source_id:int,db=Depends(get_db),user=Depends(get_user)):return service.targets(db,user,source_id)
@router.post('/grants',status_code=201)
def propose(body:Proposal,db=Depends(get_db),user=Depends(get_user)):
    return service.propose(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.get('/grants/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.detail(db,user,key)
@router.post('/grants/{key}/actions/{action}')
def decide(key:int,action:Literal['approve','reject','cancel','revoke'],body:Command,db=Depends(get_db),user=Depends(get_user)):
    return service.decide(db,user,key,body.request_id,body.version,action,values(Reason,body.values))
@router.post('/requests',status_code=201)
def accept(body:Accept,db=Depends(get_db),user=Depends(get_user)):
    return service.request_create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.post('/orders/{key}/quote')
def quote(key:int,body:Command,db=Depends(get_db),user=Depends(get_user)):
    return repair_service.command(db,user,key,body.request_id,body.version,'quote',values(ScopeQuote,body.values))
