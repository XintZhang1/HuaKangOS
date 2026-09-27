"""Evidence-based claims commands. Uploaded documents are not authenticity certification."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator
from .db import get_db
from .security import get_user
from . import claims_service as service

router=APIRouter(prefix='/api/claims',tags=['理赔索赔与客户报销'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Create(Request,Reason):
    source_case_id:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    party_type:Literal['insurer','manufacturer','internal']
    payment_route:Literal['repair_receivable','customer_direct','customer_via_store','internal']
    payer_id:int|None=Field(default=None,gt=0,strict=True,validate_default=True,description='保险或厂家核赔必填，须选真实保险公司或厂家档案')
    payer_name:str=Field(default='',max_length=120,validate_default=True,description='内部核价必填实际承担主体；外部核赔名称来自所选档案')
    @field_validator('payer_id')
    @classmethod
    def external_payer(cls,value,info):
        if info.data.get('party_type') in {'insurer','manufacturer'} and value is None:
            raise ValueError('保险或厂家核赔须选择真实核赔单位')
        return value
    @field_validator('payer_name')
    @classmethod
    def internal_payer(cls,value,info):
        if info.data.get('party_type')=='internal' and not value:
            raise ValueError('内部核价须明确实际承担主体')
        return value
class Command(Request):
    version:int=Field(gt=0,strict=True)
    source_version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Line(Strict):
    line_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
    amount_cents:int=Field(ge=0,le=1_000_000_000_000,strict=True)
class Assessment(Reason):lines:list[Line]=Field(min_length=1,max_length=200)
class Approval(Evidence,Reason):pass
class Transmission(Evidence):
    external_reference:str=Field(min_length=1,max_length=120)
    submitted_on:date
    supplement_result_id:int|None=Field(default=None,gt=0,strict=True)
class Result(Evidence):
    transmission_id:int=Field(gt=0,strict=True)
    outcome:Literal['approved','partial','rejected','need_documents']
    lines:list[Line]=Field(default_factory=list,max_length=200)
    result_on:date
    result:str=Field(min_length=2,max_length=1000)
class Selection(Strict):
    original_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class Resolution(Evidence,Reason):
    internal_bearer:str=Field(min_length=1,max_length=120)
    refunds:list[Selection]=Field(default_factory=list,max_length=100)
class Cash(Evidence):
    amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class LinkedCash(Cash):original_id:int=Field(gt=0,strict=True)
class Direct(Evidence):amount_cents:int=Field(gt=0,le=1_000_000_000_000,strict=True)
class ReturnPlan(Evidence,Reason):selections:list[Selection]=Field(min_length=1,max_length=100)
class PlanEvidence(Evidence):plan_id:int=Field(gt=0,strict=True)
class PlanCancel(PlanEvidence,Reason):pass
class DirectReturn(PlanEvidence,Direct):original_id:int=Field(gt=0,strict=True)
class CashReturn(PlanEvidence,LinkedCash):pass
SCHEMAS={'assess':Assessment,'approve':Approval,'transmit':Transmission,'result':Result,'bind':Evidence,
    'resolution':Resolution,'resolution_approve':Approval,'thirdparty_refund':LinkedCash,'resolution_apply':Evidence,
    'reimbursement_approve':Approval,'direct_confirm':Direct,'pass_receive':Cash,'pass_pay':LinkedCash,
    'return_plan':ReturnPlan,'return_approve':PlanEvidence,'return_cancel':PlanCancel,'direct_return':DirectReturn,
    'customer_return':CashReturn,'party_return':CashReturn,'unused_refund':CashReturn,'close':Approval,'cancel':Approval}

@router.get('')
def listing(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.list_orders(db,user,page)
@router.get('/sources')
def sources(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):return service.sources(db,user,page)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    return service.create(db,user,body.request_id,body.model_dump(exclude={'request_id'}))
@router.get('/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    return service.describe(db,user,service.get_order(db,user,case_id))
@router.get('/{case_id}/options/{action}')
def action_options(case_id:int,action:str,plan_id:int|None=Query(default=None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    return service.action_options(db,user,service.get_order(db,user,case_id),action,plan_id)
@router.post('/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'理赔动作不存在')
    try:values=schema.model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对本次理赔字段、原单版本和凭据；金额为整数分、数量为整数千分位')
    return service.command(db,user,case_id,body.request_id,body.version,body.source_version,action,values)
