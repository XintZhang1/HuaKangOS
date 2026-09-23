from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError,StrictBool
from .db import get_db
from .security import get_user
from . import transfer_service as service

router=APIRouter(prefix='/api/transfers',tags=['跨店物资调拨'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Request(Strict):request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
class Line(Strict):
    item_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class Create(Request):
    destination_store_id:int=Field(gt=0,strict=True)
    due_date:date
    reason:str=Field(min_length=2,max_length=500)
    lines:list[Line]=Field(min_length=1,max_length=80)
class Command(Request):
    version:int=Field(gt=0,strict=True)
    case_version:int=Field(gt=0,strict=True)
    values:dict
class Reason(Strict):reason:str=Field(min_length=2,max_length=500)
class Evidence(Reason):evidence_id:int=Field(gt=0,strict=True)
class ReceiveLine(Strict):
    line_id:int=Field(gt=0,strict=True)
    item_id:int|None=Field(default=None,gt=0,strict=True)
    accept_milli:int=Field(ge=0,le=1_000_000_000,strict=True)
    reject_milli:int=Field(ge=0,le=1_000_000_000,strict=True)
class Receive(Evidence):lines:list[ReceiveLine]=Field(min_length=1,max_length=80)
class ReturnShip(Evidence):rejection_id:int=Field(gt=0,strict=True)
class ReturnReceive(Evidence):
    shipment_id:int=Field(gt=0,strict=True)
    quantity_milli:int=Field(gt=0,le=1_000_000_000,strict=True)
class ReturnReceiveV3(ReturnReceive):passed:StrictBool

SCHEMAS={'approve':Reason,'reject_request':Reason,'cancel':Reason,'dispatch':Evidence,
         'receive':Receive,'return_ship':ReturnShip,'return_receive':ReturnReceive}


@router.get('/destinations')
def destinations(db=Depends(get_db),user=Depends(get_user)):return service.destinations(db,user)
@router.get('')
def list_transfers(db=Depends(get_db),user=Depends(get_user)):return service.list_transfers(db,user)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):
    return service.create_transfer(db,user,**body.model_dump(mode='json'))
@router.get('/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.transfer_detail(db,user,key)
@router.post('/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'调拨动作不存在')
    if action=='return_receive' and service.action_version(db,user,key)==3:schema=ReturnReceiveV3
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'调拨字段无效；数量使用整数千分位，请核对必填内容')
    return service.command(db,user,key,body.request_id,body.version,body.case_version,action,values)
