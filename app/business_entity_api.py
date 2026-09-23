"""Typed reviewed configuration, intentionally no arbitrary metadata editor."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,ValidationError,model_validator
from sqlalchemy import select,func
from .db import get_db
from .security import get_user
from .flow_models import Case
from . import business_entity_service as svc

router=APIRouter(prefix='/api/business-entities',tags=['经营主体与资金账户归属'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Revision(Strict):
    entity_id:int|None=Field(default=None,gt=0,strict=True)
    expected_entity_version:int|None=Field(default=None,gt=0,strict=True)
    code:str=Field(min_length=2,max_length=50,pattern=r'^[A-Z0-9_-]+$')
    tax_identifier:str=Field(min_length=15,max_length=30,pattern=r'^[A-Z0-9]+$')
    legal_name:str=Field(min_length=2,max_length=180)
    registered_address:str=Field(min_length=2,max_length=300)
    contact_phone:str=Field(default='',max_length=40)
    @model_validator(mode='after')
    def version(self):
        if bool(self.entity_id)!=bool(self.expected_entity_version):raise ValueError('修订必须指定原主体与版本')
        return self
class StoreBinding(Strict):
    revision_id:int=Field(gt=0,strict=True)
    effective_from:date
class AccountBinding(StoreBinding):
    account_id:int=Field(gt=0,strict=True)
    expected_account_version:int=Field(gt=0,strict=True)
    holder_name:str=Field(min_length=2,max_length=180)
    channel_type:Literal['bank','cash','wallet']
    channel_identifier:str=Field(min_length=2,max_length=100)
    institution_name:str=Field(min_length=2,max_length=180)
class Policy(Strict):
    binding_id:int=Field(gt=0,strict=True)
    policy_version:Literal[1]=1
class Create(Request):
    operation:Literal['revision','store_binding','account_binding','policy']
    reason:str=Field(min_length=2,max_length=1000)
    due_date:date
    details:dict
class Command(Request):
    version:int=Field(gt=0,strict=True)
    values:dict=Field(default_factory=dict)
class Evidence(Strict):evidence_id:int=Field(gt=0,strict=True)
class Reason(Strict):reason:str=Field(min_length=2,max_length=1000)
class Reassign(Reason):
    task_id:int=Field(gt=0,strict=True)
    assignee_id:int=Field(gt=0,strict=True)
    due_date:date
SCHEMAS={'revision':Revision,'store_binding':StoreBinding,'account_binding':AccountBinding,'policy':Policy}
ACTIONS={'submit':Evidence,'approve':Evidence,'reject':Reason,'cancel':Reason,'reassign':Reassign}

@router.get('/catalog')
def catalog(user=Depends(get_user)):
    allowed=user.role in svc.READ and not getattr(user,'_aggregate_scope',False)
    return {'can_read':allowed,'can_create':allowed and user.role=='admin','operations':svc.OPERATIONS if allowed else {},'actions':svc.LABELS if allowed else {},'limitation':svc.LIMITATION if allowed else ''}

@router.get('/configuration')
def configuration(db=Depends(get_db),user=Depends(get_user)):return svc.configuration(db,user)

@router.get('/applications')
def listing(page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):
        q=select(Case).where(Case.kind=='business_entity',Case.flow_version==1)
        return {'items':[svc.describe(db,user,r) for r in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size))],
                'total':db.scalar(select(func.count()).select_from(q.subquery())),'page':page,'page_size':page_size}

@router.post('/applications',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    try:details=SCHEMAS[body.operation].model_validate(body.details).model_dump()
    except ValidationError:raise HTTPException(422,'请核对主体标识、法定名称、批准版本、实际账户字段和日期；不支持任意状态或历史归属编辑')
    return svc.create(db,user,body.request_id,{**body.model_dump(exclude={'request_id'}),'details':details})

@router.get('/applications/{case_id}')
def detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    with svc.authority(db,user,svc.READ):return svc.describe(db,user,svc._get(db,case_id)[0])

@router.post('/applications/{case_id}/actions/{action}')
def command(case_id:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    if action not in ACTIONS:raise HTTPException(404,'主体配置动作不存在')
    try:values=ACTIONS[action].model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对实际凭据、处理说明和当前待办责任人')
    return svc.command(db,user,case_id,body.request_id,body.version,action,values)
