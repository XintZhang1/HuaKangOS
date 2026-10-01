"""Chinese typed master maintenance and reviewed opening import endpoints."""
import csv
import io
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field,ConfigDict
from sqlalchemy import select, func, or_
from .security import get_user
from .db import get_db, get_write_db, today
from .tenancy import single_store, role_for_store
from .models import User
from .flow_models import Item
from .master_models import OpeningBatch
from . import master_data as service

router=APIRouter(prefix='/api/masters',tags=['主数据与期初导入'])


class Command(service.Strict):
    request_id: str = Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')


class Save(Command):
    values: dict


class Update(Save):
    version: int = Field(gt=0,strict=True)


class Preflight(Command):
    # The reviewed digest binds the exact source, including trailing line endings.
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    source_text: str = Field(min_length=2,max_length=85000)


class Review(Command):
    version: int = Field(gt=0,strict=True)
    digest: str = Field(pattern=r'^[a-f0-9]{64}$')


class Totals(service.Strict):
    customer_count: int = Field(ge=0,strict=True)
    account_count: int = Field(ge=0,strict=True)
    item_count: int = Field(ge=0,strict=True)
    stock_row_count: int = Field(ge=0,strict=True)
    quantity_milli: int = Field(ge=0,strict=True)
    inventory_value_cents: int = Field(ge=0,strict=True)


class Confirm(Review):
    expected_totals: Totals
    confirmed: Literal[True]


@router.get('/catalog')
def catalog(user=Depends(get_user)):
    return service.public_catalog(user)


@router.get('/opening/example')
def example(user=Depends(get_user)):
    service._ensure_role(user,service.MANAGE)
    source={'opening_date':today().isoformat(),'source_reference':'合成演示期初清单-001',
        'customers':[{'name':'虚构期初客户','phone':'13900001111','contact_allowed':False,'owner_username':user.username}],
        'accounts':[{'name':'虚构经营账户','account_type':'bank'}],
        'items':[{'sku':'TEST-OIL','name':'虚构维修耗材','unit':'升','reorder_milli':1000,
                  'opening_quantity_milli':2500,'opening_value_cents':12345,'source_reference':'合成盘点表-第1行'},
                 {'sku':'TEST-ZERO','name':'虚构零库存配件','unit':'件'}]}
    return {'source_text':json.dumps(source,ensure_ascii=False,indent=2),
        'notice':'此示例全部为虚构资料。正式期初须使用公司核对的清单；数量为整数千分位，金额为整数分。账户这里只建立主档，不导入现金余额。'}


@router.get('/opening/batches')
def batches(db=Depends(get_db),user=Depends(get_user)):
    service._ensure_role(user,service.MANAGE|{'finance','auditor'})
    return {'items':[service.batch_info(r) for r in db.scalars(select(OpeningBatch).order_by(OpeningBatch.id.desc()).limit(100))]}


@router.post('/opening/preflight')
def preflight(body:Preflight,db=Depends(get_db),user=Depends(get_user)):
    return service.preflight(db,user,body.request_id,body.source_text)


@router.get('/opening/{batch_id}/source')
def opening_source(batch_id:int,db=Depends(get_db),user=Depends(get_user)):
    service._ensure_role(user,service.MANAGE)
    store=single_store(db)
    row=db.scalar(select(OpeningBatch).where(OpeningBatch.id==batch_id,OpeningBatch.store_id==store))
    if not row:raise HTTPException(404,'当前门店预检批次不存在')
    return {'source_text':row.source_text,'source_digest':row.source_digest}


@router.post('/opening/{batch_id}/trial')
def trial(batch_id:int,body:Review,db=Depends(get_db),user=Depends(get_user)):
    return service.opening_action(db,user,batch_id,body.request_id,body.version,body.digest)


@router.post('/opening/{batch_id}/confirm')
def confirm(batch_id:int,body:Confirm,db=Depends(get_db),user=Depends(get_user)):
    return service.opening_action(db,user,batch_id,body.request_id,body.version,body.digest,True,body.expected_totals.model_dump())


@router.get('/opening/stockflow')
def stockflow(item_id:int|None=Query(default=None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    return service.stockflow(db,user,item_id)


@router.get('/opening/stockflow/export')
def stockflow_export(item_id:int|None=Query(default=None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    data=service.stockflow(db,user,item_id)
    buffer=io.StringIO(newline='');writer=csv.writer(buffer)
    labels=['物资编码','名称','日期','来源','凭据','变动数量（千分位）','变动价值（分）','结存数量（千分位）','结存价值（分）']
    keys=['sku','name','date','source','reference','quantity_milli','value_cents','running_quantity_milli','running_value_cents']
    if not data['can_money']:
        pairs=[(k,label) for k,label in zip(keys,labels) if 'value_cents' not in k]
        keys,labels=zip(*pairs)
    writer.writerow(labels)
    for row in data['rows']:
        values=[row[k] for k in keys]
        writer.writerow(["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) and isinstance(v,str) else v for v in values])
    return Response(content=('\ufeff'+buffer.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="huakangos-stockflow.csv"'})


@router.get('/lookup/{kind}')
def lookup(kind:str,q:str=Query('',max_length=100),selected_id:int|None=Query(default=None,gt=0),db=Depends(get_db),user=Depends(get_user)):
    store=single_store(db)
    if kind=='employees':
        service.ensure_read(user,'teams')
        users=list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.id)))
        return {'items':[{'id':u.id,'label':u.display_name} for u in users
            if role_for_store(db,u,store) in {'admin','manager','service','technician'} and (not q or q in u.display_name)]}
    service.ensure_read(user,'item_profiles' if kind=='items' else kind)
    if kind=='item_profiles':raise HTTPException(404,'物资归类不是可选择的主档，请通过物资查找')
    model=Item if kind=='items' else service.kind_config(kind)[0]
    stmt=select(model).where(model.active.is_(True))
    if q:stmt=stmt.where(model.name.contains(q))
    rows=list(db.scalars(stmt.order_by(model.id).limit(101)))
    has_more=len(rows)>100;rows=rows[:100]
    if selected_id and not any(r.id==selected_id for r in rows):
        selected=db.scalar(select(model).where(model.id==selected_id,model.active.is_(True)))
        if selected:rows.insert(0,selected)
    return {'items':[{'id':r.id,'label':getattr(r,'code',getattr(r,'sku',''))+' · '+r.name} for r in rows],'has_more':has_more}


@router.get('/{kind}')
def list_master(kind:str,q:str=Query('',max_length=100),active:bool|None=None,fuel_type:str|None=None,
                min_seats:int|None=Query(default=None,ge=1,le=60),max_price_cents:int|None=Query(default=None,ge=0),
                page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    service.ensure_read(user,kind)
    model=service.kind_config(kind)[0];stmt=select(model)
    if q and hasattr(model,'name'):stmt=stmt.where(or_(model.name.contains(q),model.code.contains(q)))
    elif q and kind=='item_profiles':stmt=stmt.join(Item,Item.id==model.item_id).where(or_(Item.name.contains(q),Item.sku.contains(q)))
    if active is not None:stmt=stmt.where(model.active==active)
    if any(v is not None for v in (fuel_type,min_seats,max_price_cents)):
        if kind!='vehicle_models':raise HTTPException(422,'车型筛选条件只能用于车型资料')
        if fuel_type is not None:stmt=stmt.where(model.fuel_type==fuel_type)
        if min_seats is not None:stmt=stmt.where(model.seats>=min_seats)
        if max_price_cents is not None:stmt=stmt.where(model.guide_price_cents<=max_price_cents)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=list(db.scalars(stmt.order_by(model.id.desc()).offset((page-1)*30).limit(30)))
    labels={}
    for field in service.kind_config(kind)[4]:
        if field['type']!='ref' or field['key'] in service.hidden_fields(user,kind):continue
        target=User if field['ref_kind']=='employees' else Item if field['ref_kind']=='items' else service.kind_config(field['ref_kind'])[0]
        ids={getattr(row,field['key']) for row in rows if getattr(row,field['key'])}
        labels[field['key']]={r.id:getattr(r,'display_name',None) or r.name for r in db.scalars(select(target).where(target.id.in_(ids)))}
    values=[]
    for row in rows:
        value=service.visible_master(user,kind,row)
        value['reference_labels']={field:mapping.get(getattr(row,field),'—') for field,mapping in labels.items()}
        values.append(value)
    return {'items':values,'total':total,'page':page}


@router.post('/{kind}',status_code=201)
def add_master(kind:str,body:Save,db=Depends(get_write_db),user=Depends(get_user)):
    return service.save_master(db,user,kind,body.request_id,body.values)


@router.put('/{kind}/{record_id}')
def update_master(kind:str,record_id:int,body:Update,db=Depends(get_write_db),user=Depends(get_user)):
    return service.save_master(db,user,kind,body.request_id,body.values,record_id,body.version)
