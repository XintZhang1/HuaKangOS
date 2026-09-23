from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, ValidationError
from .db import get_db
from .security import get_user
from .transfer_api import Request, Command, Reason, Strict
from . import vehicle_transfer_service as service

router=APIRouter(prefix='/api/vehicle-transfers',tags=['整车调拨'])

class Create(Request):
    vehicle_id:int=Field(gt=0,strict=True)
    destination_store_id:int=Field(gt=0,strict=True)
    due_date:date
    reason:str=Field(min_length=2,max_length=500)
class Handover(Reason):
    evidence_id:int=Field(gt=0,strict=True)
    vin:str=Field(min_length=17,max_length=17,pattern=r'^[A-HJ-NPR-Za-hj-npr-z0-9]{17}$')
class Receive(Handover):location_id:int=Field(gt=0,strict=True)
SCHEMAS={'approve':Reason,'reject_request':Reason,'cancel':Reason,'dispatch':Handover,'accept':Receive,'reject':Handover,'return_ship':Handover,'return_receive':Receive}

@router.get('/destinations')
def destinations(db=Depends(get_db),user=Depends(get_user)):return service.destinations(db,user)
@router.get('')
def listing(db=Depends(get_db),user=Depends(get_user)):return service.list_transfers(db,user)
@router.post('',status_code=201)
def create(body:Create,db=Depends(get_db),user=Depends(get_user)):return service.create(db,user,**body.model_dump(mode='json'))
@router.get('/{key}')
def detail(key:int,db=Depends(get_db),user=Depends(get_user)):return service.detail(db,user,key)
@router.post('/{key}/actions/{action}')
def command(key:int,action:str,body:Command,db=Depends(get_db),user=Depends(get_user)):
    schema=SCHEMAS.get(action)
    if not schema:raise HTTPException(404,'整车调拨动作不存在')
    try:values=schema.model_validate(body.values).model_dump()
    except ValidationError:raise HTTPException(422,'请核对VIN、库位及交接凭据，填写完整的调拨字段')
    return service.command(db,user,key,body.request_id,body.version,body.case_version,action,values)
