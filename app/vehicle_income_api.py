"""Strict dedicated commands for real noncustomer vehicle income."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import select,func
from .db import get_db
from .security import get_user
from .flow_models import Case
from .master_models import Supplier
from . import vehicle_income_service as s

router=APIRouter(prefix='/api/vehicle-income',tags=['厂家及供应商整车其他收入'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Proof(Reason):evidence_id:int=Field(gt=0,strict=True)
class Source(Strict):
    source_case_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    vehicle_id:int|None=Field(default=None,gt=0,strict=True)
class Create(Request,Reason):
    supplier_id:int=Field(gt=0,strict=True)
    supplier_version:int=Field(gt=0,strict=True)
    external_reference:str=Field(min_length=1,max_length=120)
    sources:list[Source]=Field(min_length=1,max_length=100)
    due_date:date
class Propose(Proof):
    target_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
    invoice_mode:Literal['store_invoice','external_document']
    due_date:date
class Decision(Proof):revision_id:int=Field(gt=0,strict=True)
class Withdraw(Reason):revision_id:int=Field(gt=0,strict=True)
class Receive(Proof):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
    business_date:date
class Refund(Receive):original_id:int=Field(gt=0,strict=True)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
SCHEMAS={'propose':Propose,'approve':Decision,'reject':Decision,'withdraw':Withdraw,'receive':Receive,'refund':Refund,'cancel':Reason}

@router.get('/catalog')
def catalog(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    s.single_store(db);s._role(user,s.READ)
    suppliers=list(db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.id).offset((page-1)*50).limit(50)))
    return dict(suppliers=[dict(id=x.id,version=x.version,name=x.name,code=x.code,tax_identifier=x.tax_identifier) for x in suppliers],supplier_total=db.scalar(select(func.count()).select_from(Supplier).where(Supplier.active.is_(True))),**s.source_candidates(db,user,page))
@router.get('/source/{key}')
def source(key:int,vehicle_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    s.single_store(db);s._role(user,s.READ);row,snapshot=s._source_snapshot(db,user,key,vehicle_id);return snapshot
@router.get('')
def orders(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    s.single_store(db);s._role(user,s.READ);q=s.flow.case_query(user).where(Case.kind=='vehicle_income',Case.flow_version==1)
    return dict(items=[s.describe(db,user,r) for r in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*30).limit(30))],total=db.scalar(select(func.count()).select_from(q.subquery())))
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):return s.create(db,user,body.request_id,body.model_dump(exclude={'request_id'},mode='json'))
@router.get('/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return s.describe(db,user,s.get_order(db,user,key))
@router.post('/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'不存在此非客户整车收入步骤')
    try:values=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对原来源版本、真实凭据、整数分金额及实际日期')
    return s.command(db,user,key,body.request_id,body.version,action,values)
