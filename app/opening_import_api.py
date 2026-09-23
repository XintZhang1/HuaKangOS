"""Store-scoped opening review endpoints; a preview never posts stock or cash."""
import csv, io, json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, ConfigDict
from sqlalchemy import select
from .db import get_db, today
from .security import get_user
from .master_data import Strict
from .opening_import_models import OpeningImport
from . import opening_import_service as service

router=APIRouter(prefix='/api/opening-import',tags=['正式期初核验'])


class Command(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')


class Preflight(Command):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    source_text:str=Field(min_length=2,max_length=120000)


class Action(Command):
    version:int=Field(gt=0,strict=True)
    source_digest:str=Field(pattern=r'^[a-f0-9]{64}$')
    values:dict


class Reason(Strict):
    reason:str=Field(min_length=3,max_length=500)


class Evidence(Reason):
    evidence_id:int=Field(gt=0,strict=True)


class Verify(Evidence):
    observed:dict


class Confirm(Reason):
    expected_totals:dict
    confirmed:Literal[True]


class Reassign(Reason):
    task_id:int=Field(gt=0,strict=True)
    assignee_id:int=Field(gt=0,strict=True)


INPUTS={'trial':Evidence,'approve':Evidence,'verify_inventory':Verify,'verify_finance':Verify,'confirm':Confirm,'cancel':Reason,'reassign':Reassign}


@router.get('/catalog')
def catalog(user=Depends(get_user),db=Depends(get_db)):
    # Boot may ask this under any role. The catalogue reveals capabilities only.
    allowed=not getattr(user,'_aggregate_scope',False) and user.role in service.READ
    return {'can_read':allowed,'can_prepare':allowed and user.role in service.MANAGE,'can_balances':allowed and user.role in service.MONEY,'actions':service.LABELS if allowed else {}}


@router.get('/example')
def example(user=Depends(get_user),db=Depends(get_db)):
    with service.authority(db,user,service.MANAGE):
        result={'notice':'全为虚构示例。先建立本店车型与整车库位编码，再按已核对资料修改；本例没有未结旧单、应收应付或预收。余额单位分，数量单位千分之一。',
            'source':{'schema_version':2,'opening_date':today().isoformat(),'source_reference':'合成期初资料-001',
                'customers':[{'name':'合成开库客户','phone':'','owner_username':user.username,'contact_allowed':False}],
                'accounts':[{'name':'合成银行账户','account_type':'bank','opening_balance_cents':500001,'source_reference':'合成银行期初核对表-001'}],
                'items':[{'sku':'OPEN-M001','name':'合成物资','unit':'件','opening_quantity_milli':2500,'opening_value_cents':10001,'source_reference':'合成实盘清单-001'}],
                'vehicles':[{'vin':'LTEST000000000101','model_code':'OPEN-MODEL','location_code':'OPEN-LOCATION','color':'白色','cost_cents':10000001,'list_price_cents':11000000,'source_reference':'合成已在店可售车清单-001','condition':'available_stock'}]}}
        result.update(service.account_options(db,user))
        if result['policy_enabled']:
            result['source']['accounts']=[]
            result['notice']='本店已启用主体策略。账户示例不预填余额或编造账号；请依据实际核对表，在 accounts 中逐行填写下表的 account_id、完全一致的 name/account_type、整数分 opening_balance_cents 和 source_reference。原期初基准日不会被解释为当日曾已批准主体。其它示例资料仍全部虚构。'
        return result


@router.get('/batches')
def batches(user=Depends(get_user),db=Depends(get_db)):
    with service.authority(db,user):
        return {'items':[service.serialize(db,user,*service._load(db,case_id)) for case_id in db.scalars(select(OpeningImport.case_id).order_by(OpeningImport.id.desc()).limit(100))]}


@router.post('/preflight')
def preflight(body:Preflight,user=Depends(get_user),db=Depends(get_db)):
    return service.preflight(db,user,body.request_id,body.source_text)


@router.get('/batches/{case_id}')
def detail(case_id:int,user=Depends(get_user),db=Depends(get_db)):
    return service.detail(db,user,case_id)


@router.get('/batches/{case_id}/source')
def source(case_id:int,user=Depends(get_user),db=Depends(get_db)):
    with service.authority(db,user,service.MANAGE):
        case,control,batch=service._load(db,case_id)
        return Response(batch.source_text,media_type='application/json',headers={'Content-Disposition':'attachment; filename="opening-source.json"','X-Source-SHA256':batch.source_digest})


@router.post('/batches/{case_id}/actions/{action_name}')
def act(case_id:int,action_name:str,body:Action,user=Depends(get_user),db=Depends(get_db)):
    from pydantic import ValidationError
    if action_name not in INPUTS:raise HTTPException(404,'期初动作不存在')
    try:values=INPUTS[action_name].model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请填写本次核验所需凭据、原因和明确核对数值')
    return service.action(db,user,case_id,body.request_id,body.version,body.source_digest,action_name,values)


@router.get('/account-balances')
def balances(user=Depends(get_user),db=Depends(get_db)):
    return service.account_balances(db,user)


@router.get('/account-balances/export')
def export_balances(user=Depends(get_user),db=Depends(get_db)):
    info=service.account_balances(db,user);out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(['账户','期初基准日','期初余额分','实际收入分','实际支出分','当前余额分','早于期初流水数'])
    def safe(value):return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else value
    for r in info['items']:writer.writerow([safe(r[k]) for k in ('account_name','opening_date','opening_cents','in_cents','out_cents','balance_cents','pre_opening_cash_count')])
    return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="opening-account-balances.csv"'})
