"""Typed commands for store advances, source statements and real cash allocation."""
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from fastapi import APIRouter,Depends,HTTPException,Query
from .db import get_db
from .security import get_user
from . import business_finance_service as service

router=APIRouter(prefix='/api/business-finance',tags=['业务财务结算'])
Fen=Annotated[int,Field(gt=0,le=100000000000,strict=True)]
NonnegativeFen=Annotated[int,Field(ge=0,le=100000000000,strict=True)]
Key=Annotated[int,Field(gt=0,strict=True)]
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Allocation(Strict):
    source_case_id:Key
    amount_cents:Fen
class Advance(Strict):amount_cents:Fen
class Apply(Advance):
    advance_id:Key
    advance_version:Key
    target_case_id:Key
    target_version:Key
class Refund(Advance):
    advance_id:Key
    advance_version:Key
class Statement(Strict):
    starts_on:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    ends_on:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
class Correction(Strict):
    amount_cents:NonnegativeFen
    original_cash_id:Key
    account_id:Key|None=None
    reference:str|None=Field(default=None,min_length=1,max_length=100)
    allocations:list[Allocation]=Field(default_factory=list,max_length=100)
    allocation_basis:Literal['remaining_after_refunds']|None=None
    actual_business_date:str|None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
class StoredCorrection(Strict):
    amount_cents:NonnegativeFen
    original_cash_id:Key
    source_version:Key
    bundle_purchase_id:Key|None=None
    account_id:Key|None=None
    reference:str|None=Field(default=None,min_length=1,max_length=100)
    actual_business_date:str|None=Field(default=None,pattern=r'^\d{4}-\d{2}-\d{2}$')
class FeeCorrection(Strict):
    fee_id:Key
    original_cash_id:Key
    source_version:Key
    account_id:Key
    reference:str=Field(min_length=1,max_length=100)
class ReturnAdjustment(Strict):
    amount_cents:NonnegativeFen
    receivable_id:Key
    source_version:Key
class SupplierRefund(Advance):
    receivable_id:Key
    original_payment_id:Key
    source_version:Key
class OtherReturn(Advance):
    stock_move_id:Key
    source_version:Key
    supplier_id:Key
class Create(Request):
    customer_id:Key|None=None
    purpose:Literal['advance','advance_apply','advance_refund','statement','correction','stored_correction','fee_correction','other_return','other_return_adjust','other_return_refund']
    values:dict
    reason:str=Field(min_length=2,max_length=500)
class Command(Request):
    version:Key
    case_version:Key
    values:dict
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Reason):
    evidence_id:Key
    source_versions:dict[str,Key]=Field(default_factory=dict)
class Posting(Evidence):
    amount_cents:Fen|None=None
    account_id:Key|None=None
    reference:str|None=Field(default=None,min_length=1,max_length=100)
    allocations:list[Allocation]|None=Field(default=None,min_length=1,max_length=100)

def validate(schema,values):
    try:return schema.model_validate(values).model_dump(exclude_none=True)
    except ValidationError:raise HTTPException(422,'财务办理字段不完整或类型无效；金额须为整数分，分配须明确原单')
@router.get('/sources')
def sources(customer_id:int=Query(gt=0),db=Depends(get_db),user=Depends(get_user)):return service.sources(db,user,customer_id)
@router.get('/advances')
def advances(customer_id:int=Query(gt=0),db=Depends(get_db),user=Depends(get_user)):return service.advances(db,user,customer_id)
@router.get('/receipts')
def receipts(customer_id:int=Query(gt=0),db=Depends(get_db),user=Depends(get_user)):return service.receipt_sources(db,user,customer_id)
@router.get('/other-returns')
def other_returns(db=Depends(get_db),user=Depends(get_user)):return service.other_return_sources(db,user)
@router.get('/orders')
def orders(db=Depends(get_db),user=Depends(get_user)):return service.orders(db,user)
@router.get('/orders/{key}')
def order(key:int,db=Depends(get_db),user=Depends(get_user)):return service.describe(db,user,key)
@router.post('/orders',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    values=validate({'advance':Advance,'advance_apply':Apply,'advance_refund':Refund,'statement':Statement,'correction':Correction,'stored_correction':StoredCorrection,'fee_correction':FeeCorrection,'other_return':OtherReturn,'other_return_adjust':ReturnAdjustment,'other_return_refund':SupplierRefund}[body.purpose],body.values)
    if body.purpose in {'correction','stored_correction'} and values['amount_cents'] and any(k not in values for k in ('account_id','reference')):
        raise HTTPException(422,'正确重记为正金额时须填写实际账户和原收款凭证；完全未到账可明确填零撤错')
    return service.create_order(db,user,body.request_id,body.customer_id,body.purpose,values,body.reason)
@router.post('/orders/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema={'approve':Evidence,'execute':Posting,'collect':Posting,'cancel':Reason,'reject':Reason,'recalculate':Reason}.get(action)
    if not schema:raise HTTPException(404,'业务财务动作不存在')
    values=validate(schema,body.values)
    # Required monetary fields depend on the frozen purpose, not a client state.
    if action in {'execute','collect'}:
        row,order=service._order(db,user,key)
        required={'advance':['account_id','reference'],'advance_refund':['account_id','reference'],'other_return_refund':['account_id','reference'],
            'statement':['account_id','reference','amount_cents','allocations'],'other_return':['account_id','reference','amount_cents']}.get(order.purpose,[])
        if any(k not in values for k in required):raise HTTPException(422,'请填写本次实际账户、凭证号、金额与必要的逐单分配')
    return service.command(db,user,key,body.request_id,body.version,body.case_version,action,values)
