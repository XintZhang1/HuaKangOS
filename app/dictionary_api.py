"""Typed navigation over existing store dictionaries, never executable workflow rules."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select,func,or_
from .db import get_db,utcnow
from .security import get_user
from .tenancy import single_store
from .flow_models import Reference
from .master_data import Strict,_command
from .master_api import Command
from .services import plain,audit

router=APIRouter(prefix='/api/dictionaries',tags=['领域字典'])
DICTIONARIES={
    'public':{'category':'公共字典','label':'公共字典'},
    'repair':{'category':'维修字典','label':'维修字典'},
    'vehicle':{'category':'整车字典','label':'整车字典'},
    'materials':{'category':'物资字典','label':'物资字典'},
    'finance':{'category':'财务字典','label':'财务字典'},
    'customer':{'category':'客户字典','label':'客户字典'},
    'member':{'category':'会员字典','label':'会员字典'},
}
WRITERS={'admin','manager'}
NOTICE='维护本店名称与说明。不会改变业务状态、岗位权限、计价规则或历史单据；这些由对应业务规则控制。'

class Values(Strict):
    name: str=Field(min_length=1,max_length=120)
    detail: str=Field(default='',max_length=2000)
    active: bool=Field(default=True,strict=True)
class Save(Command):
    values: Values
class Update(Save):
    version: int=Field(gt=0,strict=True)

def category(group):
    if group not in DICTIONARIES:raise HTTPException(404,'字典类别不存在')
    return DICTIONARIES[group]['category']

def writable(user):
    return user.role in WRITERS and not getattr(user,'_aggregate_scope',False)

@router.get('/catalog')
def catalog(user=Depends(get_user)):
    return {'groups':DICTIONARIES,'can_write':writable(user),'notice':NOTICE}

@router.get('/{group}')
def listing(group:str,q:str=Query('',max_length=120),active:bool|None=None,
            page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),
            db=Depends(get_db),user=Depends(get_user)):
    # Individual dictionaries are operational; no cross-store write/read editor in summaries.
    store=single_store(db)
    query=select(Reference).where(Reference.store_id==store,Reference.category==category(group))
    if active is not None:query=query.where(Reference.active==active)
    if q.strip():query=query.where(or_(Reference.name.contains(q.strip(),autoescape=True),Reference.detail.contains(q.strip(),autoescape=True)))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(Reference.active.desc(),Reference.id.desc()).offset((page-1)*page_size).limit(page_size))
    return {'items':[plain(r) for r in rows],'total':total,'page':page,'page_size':page_size,
            'label':category(group),'can_write':writable(user),'notice':NOTICE}

def save(db,user,group,body,record_id=None):
    group_category=category(group)
    if not writable(user):raise HTTPException(403,'当前门店岗位不能维护字典')
    values=body.values.model_dump();version=getattr(body,'version',None)
    def perform(store):
        row=None
        if record_id:
            row=db.scalar(select(Reference).where(Reference.id==record_id,Reference.store_id==store,
                Reference.category==group_category).with_for_update())
            if not row:raise HTTPException(404,'此类别的本店条目不存在')
            if row.version!=version:raise HTTPException(409,'字典条目已修改，请刷新核对')
        before=plain(row) if row else None
        if row:
            for key,value in values.items():setattr(row,key,value)
            row.updated_at=utcnow()
        else:
            row=Reference(store_id=store,category=group_category,**values);db.add(row)
        db.flush();result=plain(row)
        audit(db,user.id,'dictionary_update' if before else 'dictionary_create','flow_master',row.id,
              before,result,reason=group_category)
        return result
    return _command(db,user,body.request_id,'dictionary:'+group,
                    {'id':record_id,'version':version,'values':values},perform)

@router.post('/{group}',status_code=201)
def create(group:str,body:Save,db=Depends(get_db),user=Depends(get_user)):
    return save(db,user,group,body)

@router.put('/{group}/{record_id}')
def update(group:str,record_id:int,body:Update,db=Depends(get_db),user=Depends(get_user)):
    if record_id<1:raise HTTPException(422,'条目编号须为正整数')
    return save(db,user,group,body,record_id)
