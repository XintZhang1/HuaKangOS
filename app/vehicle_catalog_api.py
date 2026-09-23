"""Model hierarchy and an employee showroom with current scoped availability."""
from fastapi import APIRouter,Depends,Query
from pydantic import Field
from .db import get_db
from .security import get_user
from .master_data import Strict
from . import vehicle_catalog_service as service

router=APIRouter(prefix='/api/vehicle-catalog',tags=['车型展示与明确归属'])


class Command(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    version:int=Field(ge=0,strict=True)
    reason:str=Field(min_length=2,max_length=500)


class ModelAssignment(Command):
    model_id:int=Field(gt=0,strict=True)
    model_version:int=Field(gt=0,strict=True)
    series_id:int=Field(gt=0,strict=True)


class VehicleAssignment(Command):
    vehicle_id:int=Field(gt=0,strict=True)
    vehicle_version:int=Field(gt=0,strict=True)
    vin:str=Field(min_length=17,max_length=17)
    model_id:int=Field(gt=0,strict=True)


@router.get('')
def listing(q:str=Query('',max_length=100),brand_id:int|None=Query(None,gt=0),series_id:int|None=Query(None,gt=0),
            fuel_type:str|None=None,min_seats:int|None=Query(None,ge=1,le=60),max_price_cents:int|None=Query(None,ge=0),
            available_only:bool=False,page:int=Query(1,ge=1),unclassified_page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    return service.catalogue(db,user,q,brand_id,series_id,fuel_type,min_seats,max_price_cents,available_only,page,unclassified_page)


@router.post('/model-assignment')
def model_assignment(body:ModelAssignment,db=Depends(get_db),user=Depends(get_user)):
    values=body.model_dump();key=values.pop('request_id');return service.assign(db,user,key,'model',values)


@router.post('/vehicle-assignment')
def vehicle_assignment(body:VehicleAssignment,db=Depends(get_db),user=Depends(get_user)):
    values=body.model_dump();key=values.pop('request_id');return service.assign(db,user,key,'vehicle',values)
