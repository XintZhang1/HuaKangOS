"""Registered original-retail mixed-tender and independently approved rule APIs."""
from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator
from .db import get_db
from .security import get_user
from . import retail_group_service as service,retail_group_rules as rules
def ready(value):
    result=dict(value)
    result.update(write_enabled=True,readiness_reason='')
    return result
router=APIRouter(prefix='/api/retail-group',tags=['精品集团混合支付'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Envelope(Request):
    version:int=Field(gt=0,strict=True)
    values:dict
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Selection(Strict):
    kind:str=Field(pattern=r'^(principal|bonus|coupon|package)$')
    amount_cents:int|None=Field(default=None,gt=0,le=1_000_000_000_000,strict=True)
    wallet_id:int|None=Field(default=None,gt=0,strict=True)
    wallet_version:int|None=Field(default=None,gt=0,strict=True)
    units:int|None=Field(default=None,gt=0,le=1_000_000_000,strict=True)
    @model_validator(mode='after')
    def source(self):
        if self.kind=='principal':
            if self.amount_cents is None or any(x is not None for x in (self.wallet_id,self.wallet_version,self.units)):raise ValueError('本金只填写整数分')
        elif self.amount_cents is not None or any(x is None for x in (self.wallet_id,self.wallet_version,self.units)):raise ValueError('权益须明确原钱包、版本和整数单位')
        return self
class Authorize(Evidence):
    member_id:int=Field(gt=0,strict=True)
    member_version:int=Field(gt=0,strict=True)
    selections:list[Selection]=Field(min_length=1,max_length=20)
class Act(Evidence):
    plan_version:int=Field(gt=0,strict=True)
    member_version:int=Field(gt=0,strict=True)
    wallet_version:int|None=Field(default=None,gt=0,strict=True)
class TenderAct(Act):tender_id:int=Field(gt=0,strict=True)
class Capture(TenderAct):reservation_version:int=Field(gt=0,strict=True)
class Release(TenderAct):reason:str=Field(min_length=2,max_length=1000)
class Restore(Act):unit_id:int=Field(gt=0,strict=True)
class Reassign(Strict):
    plan_version:int=Field(gt=0,strict=True)
    task_key:str=Field(pattern=r'^retail_group_(payment|restore)$')
    assignee_id:int=Field(gt=0,strict=True)
    due_date:date
    reason:str=Field(min_length=2,max_length=1000)
class RuleCreate(Request):rule_id:int=Field(gt=0,strict=True)
class Scope(Strict):
    store_id:int=Field(gt=0,strict=True)
    item_id:int=Field(gt=0,strict=True)
    component:str=Field(pattern=r'^(goods|installation)$')
    work_item_id:int|None=Field(default=None,gt=0,strict=True)
class Submit(Evidence):
    partial_return_mode:str=Field(pattern=r'^accumulate_original_unit$')
    expiry_mode:str=Field(pattern=r'^original_expiry$')
    pending_claim_expiry:str=Field(pattern=r'^none$')
    scopes:list[Scope]=Field(min_length=1,max_length=200)
class Decision(Evidence):reason:str=Field(min_length=2,max_length=1000)
class Cancel(Strict):
    reason:str=Field(min_length=2,max_length=1000)
    evidence_id:int|None=Field(default=None,gt=0,strict=True)
SCHEMAS={'authorize':Authorize,'reserve':TenderAct,'capture':Capture,'release':Release,'restore':Restore,'reassign':Reassign}


def values(schema,body):
    if schema is None:raise HTTPException(404,'精品集团办理动作不存在')
    try:return schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对原单、原批次和版本；金额为整数分，券与套餐为整数份，公司规则须明确选择')


@router.get('/orders/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    return ready(service.describe(db,user,service.retail.get_order(db,user,case_id)))


@router.get('/orders/{case_id}/catalog')
def catalog(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    return ready(service.catalogue(db,user,service.retail.get_order(db,user,case_id)))


@router.post('/orders/{case_id}/actions/{action}')
def action(case_id:int,action:str,body:Envelope,db=Depends(get_db),user=Depends(get_user)):
    return service.command(db,user,case_id,body.request_id,body.version,action,values(SCHEMAS.get(action),body))


@router.post('/rules',status_code=201)
def create_rule(body:RuleCreate,db=Depends(get_db),user=Depends(get_user)):
    return rules.create(db,user,body.request_id,body.rule_id)


@router.get('/rules')
def rule_list(db=Depends(get_db),user=Depends(get_user)):
    return ready(rules.list_rules(db,user))


@router.get('/rules/{case_id}')
def rule_detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    return ready(rules.describe(db,user,case_id))


@router.get('/rule-items/{store_id}')
def rule_items(store_id:int,db=Depends(get_db),user=Depends(get_user)):
    return rules.item_catalogue(db,user,store_id)


@router.post('/rules/{case_id}/actions/{action}')
def rule_action(case_id:int,action:str,body:Envelope,db=Depends(get_db),user=Depends(get_user)):
    return rules.command(db,user,case_id,body.request_id,body.version,action,values({'submit':Submit,'approve':Decision,'reject':Decision,'cancel':Cancel}.get(action),body))
