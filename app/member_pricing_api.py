"""Explicit price configuration and scoped quote candidates; never arbitrary case price edits."""
from datetime import date
from typing import Literal
from types import SimpleNamespace
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from sqlalchemy import select,func
from .security import get_user
from .db import get_db
from .flow_models import Case,Customer,Item
from .master_models import WorkItem,MemberTier
from .membership_models import MembershipRule
from .member_pricing_models import MemberPricingRule
from . import member_pricing_service as s

router=APIRouter(prefix='/api/member-pricing',tags=['会员价格'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Scope(Strict):
    business_kind:Literal['repair','retail','addon']
    component:Literal['work','part','goods','installation']
    source_id:int=Field(gt=0,strict=True)
    basis_points:int=Field(ge=1,le=10000,strict=True)
    bundle_rule_id:int|None=Field(default=None,gt=0,strict=True)
    allow_contract_pricing:bool=False
class Create(Request,Reason):
    code:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=120)
    enabled:bool
    membership_rule_id:int=Field(gt=0,strict=True)
    reference_tier_id:int|None=Field(default=None,gt=0,strict=True)
    reference_tier_version:int|None=Field(default=None,gt=0,strict=True)
    starts_on:date
    ends_on:date
    stack_mode:Literal['member_then_benefits','exclusive_benefits']
    scopes:list[Scope]=Field(max_length=200)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Proof(Reason):evidence_id:int=Field(gt=0,strict=True)
class Selection(Strict):
    rule_id:int=Field(gt=0,strict=True)
    rule_version:int=Field(gt=0,strict=True)

@router.get('/catalog')
def catalog(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    s.single_store(db);s._role(user,s.READ);sid=s.single_store(db)
    with s.group.authority(db,user,s.READ):
        memberships=[s.plain(r) for r in db.scalars(select(MembershipRule).order_by(MembershipRule.id)) if sid in r.allowed_store_ids]
    from .retail_bundle_models import RetailBundleRule
    result={'memberships':memberships,'stack_modes':s.STACKS,'reference_notice':'会员等级主档中的比例仅为参考，必须在本店独立批准会员价格规则后才影响新报价。'}
    for key,model in [('tiers',MemberTier),('items',Item),('works',WorkItem),('bundles',RetailBundleRule)]:
        rows=db.scalars(select(model).order_by(model.id).offset((page-1)*50).limit(50))
        result[key]=[{k:getattr(r,k) for k in ('id','version','name','discount_basis_points') if hasattr(r,k)}|({'code':r.code} if hasattr(r,'code') else {'code':r.sku}) for r in rows]
        result[key+'_total']=db.scalar(select(func.count()).select_from(model))
    return result

@router.get('/candidates')
def candidates(case_id:int|None=Query(None,gt=0),customer_id:int|None=Query(None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    s.single_store(db);s._role(user,s.FRONT)
    if case_id:
        row=s.flow.get_case(db,user,case_id)
        if row.kind not in s.COMPONENTS:raise HTTPException(409,'本业务不支持会员价格')
    elif customer_id:
        customer=s._one(db,Customer,customer_id)
        if user.role=='sales' and customer.owner_id!=user.id:raise HTTPException(403,'只可查本人负责客户的适用会员价格')
        row=SimpleNamespace(kind='retail',flow_version=2,customer_id=customer.id,store_id=customer.store_id)
    else:raise HTTPException(422,'请选择本店原业务或真实客户')
    return {'items':s.candidates(db,user,row)}

@router.get('/rules')
def rules(page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    s.single_store(db);s._role(user,s.READ)
    return dict(items=[s.describe(db,user,r) for r in db.scalars(select(MemberPricingRule).order_by(MemberPricingRule.id.desc()).offset((page-1)*30).limit(30))],total=db.scalar(select(func.count()).select_from(MemberPricingRule)))
@router.post('/rules',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):return s.create_rule(db,user,body.request_id,body.model_dump(exclude={'request_id'},mode='json'))
@router.get('/rules/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):
    rule,row=s.get_rule(db,user,key);return s.describe(db,user,rule)
@router.post('/rules/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    if action not in {'submit','approve','reject','cancel'}:raise HTTPException(404,'不存在此会员价格办理动作')
    try:values=(Reason if action=='cancel' else Proof).model_validate(body.values).model_dump(mode='json')
    except ValidationError:raise HTTPException(422,'请核对本次依据、办理原因和价格版本')
    return s.command(db,user,key,body.request_id,body.version,action,values)
