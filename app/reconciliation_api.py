from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .db import get_db
from .security import get_user
from . import reconciliation_service as svc

router=APIRouter(prefix='/api/reconciliation',tags=['业务对账与店间清算'])
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class BatchCreate(Request,Reason):
    start:date
    end:date
class Command(Request):
    version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    values:dict
class Proof(Reason):evidence_id:int=Field(gt=0,strict=True)
class Issue(Proof):
    line_key:str=Field(min_length=1,max_length=100)
    difference_cents:int=Field(ge=-100000000000,le=100000000000,strict=True)
class Resolve(Proof):
    issue_id:int=Field(gt=0,strict=True)
    issue_version:int=Field(gt=0,strict=True)
class Payment(Proof):
    account_id:int=Field(gt=0,strict=True)
    reference:str=Field(min_length=1,max_length=100)
class ClearingCreate(Request,Reason):
    origin_kind:Literal['material','material_loss','material_found','vehicle','vehicle_loss','vehicle_found']
    origin_id:int=Field(gt=0,strict=True)
    amount_cents:int=Field(gt=0,le=100000000000,strict=True)
    due_date:date


def values(body,action,schemas):
    if action not in schemas:raise HTTPException(404,'业务动作不存在')
    try:return schemas[action].model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对必填事实、整数分金额、凭据及版本')


@router.get('/batches')
def batches(db=Depends(get_db),user=Depends(get_user)):return svc.list_batches(db,user)
@router.get('/batches/{key}')
def batch(key:int,db=Depends(get_db),user=Depends(get_user)):return svc.get_batch(db,user,key)
@router.get('/batches/{key}/export')
def export_batch(key:int,db=Depends(get_db),user=Depends(get_user)):
    import csv,io,json
    row=svc.get_batch(db,user,key);out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['对账版本','源条目','来源','期间或时点','原单','金额分','数量千分位','权益单位','冻结来源内容'])
    for entry in row['manifest']:
        data=entry['data'];values=[row['revision'],entry['key'],entry['source'],entry['basis'],entry['case_id'] or '',
            data.get('amount_cents',data.get('value_cents','')),data.get('quantity_milli',''),data.get('units',''),json.dumps(data,ensure_ascii=False,sort_keys=True)]
        writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for v in values])
    return Response(out.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="huakangos-reconciliation-{key}.csv"'})
@router.post('/batches',status_code=201)
def create(body:BatchCreate,db=Depends(get_db),user=Depends(get_user)):
    return svc.create_batch(db,user,body.request_id,body.start,body.end,body.reason)
@router.post('/batches/{key}/actions/{action}')
def batch_action(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    v=values(body,action,{'issue':Issue,'resolve':Resolve,'submit':Reason,'seal':Proof,'recalculate':Reason,'reopen':Reason})
    return svc.batch_command(db,user,key,body.request_id,body.version,body.case_version,action,v)
@router.get('/origins')
def origins(db=Depends(get_db),user=Depends(get_user)):return svc.origins(db,user)
@router.get('/clearing')
def clearing(db=Depends(get_db),user=Depends(get_user)):return svc.list_clearing(db,user)
@router.get('/clearing/{key}')
def clearing_detail(key:int,db=Depends(get_db),user=Depends(get_user)):return svc.list_clearing(db,user,key)
@router.post('/clearing',status_code=201)
def clearing_create(body:ClearingCreate,db=Depends(get_db),user=Depends(get_user)):
    return svc.create_clearing(db,user,body.request_id,body.model_dump(mode='json',exclude={'request_id'}))
@router.post('/clearing/{key}/actions/{action}')
def clearing_action(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    v=values(body,action,{'pay':Payment,'receive':Payment,'difference':Proof,'cancel':Reason,'reject':Reason})
    return svc.clearing_command(db,user,key,body.request_id,body.version,body.case_version,action,v)
