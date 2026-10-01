from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .db import get_db,get_write_db
from .security import get_user
from . import invoice_service as svc

router=APIRouter(prefix='/api/invoices',tags=['发票协同'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Proof(Reason):evidence_id:int=Field(gt=0,strict=True)
class Create(Request,Reason):
    source_case_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    direction:Literal['blue','red']='blue'
    original_case_id:int|None=Field(default=None,gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=100000000000,strict=True)
    issuer_name:str=Field(min_length=2,max_length=180)
    issuer_tax_id:str=Field(min_length=15,max_length=30,pattern=r'^[A-Z0-9]+$')
    buyer_name:str=Field(min_length=2,max_length=160)
    buyer_tax_id:str=Field(default='',max_length=20,pattern=r'^[A-Z0-9]*$')
    due_date:date
class Submit(Proof):reference:str=Field(min_length=1,max_length=160)
class Actual(Proof):
    invoice_number:str=Field(min_length=1,max_length=60,pattern=r'^[A-Za-z0-9-]+$')
    issued_on:date
    amount_cents:int=Field(gt=0,le=100000000000,strict=True)
class Difference(Proof):
    external_number:str=Field(default='',max_length=160)
    observed_amount_cents:int|None=Field(default=None,ge=0,le=100000000000,strict=True)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    values:dict

@router.get('/sources')
def sources(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):return svc.sources(db,user,page,page_size)
@router.get('/sources/{key}')
def source(key:int,db=Depends(get_db),user=Depends(get_user)):
    row=svc._source(db,user,key)
    from .business_entity_service import case_entity_snapshot
    snapshot=case_entity_snapshot(db,user,row)
    entity=snapshot.get('entity')
    issuer={'legal_name':entity['legal_name'],'tax_identifier':entity['tax_identifier']} if entity else None
    return {'id':row.id,'number':row.number,'title':row.title,'version':row.version,'issuer':issuer,'source_basis':svc.source_basis(db,row),**svc.balance(db,row)}
@router.get('/orders')
def orders(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):return svc.list_orders(db,user,page,page_size)
@router.get('/orders/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return svc.describe(db,user,svc._order(db,user,key))
@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_write_db),user=Depends(get_user)):
    return svc.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.post('/orders/{key}/actions/{action}')
def action(key:int,action:str,body:Command,db=Depends(get_write_db),user=Depends(get_user)):
    schemas={'approve':Proof,'reject':Reason,'cancel':Reason,'submit':Submit,'failure':Proof,'difference':Difference,'record':Actual,'review_result':Proof}
    if action not in schemas:raise HTTPException(404,'发票动作不存在')
    try:v=schemas[action].model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对必要事实、整数分金额、实际日期和本单凭据')
    return svc.command(db,user,key,body.request_id,body.version,body.source_version,action,v)
