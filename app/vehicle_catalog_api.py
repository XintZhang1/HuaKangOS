"""Model hierarchy and an employee showroom with current scoped availability."""
from fastapi import APIRouter,Depends,Query
from pydantic import Field
from typing import Literal
from .db import get_db,get_write_db
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


class CatalogueEntry(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    brand_id:int|None=Field(default=None,gt=0,strict=True)
    brand_version:int|None=Field(default=None,gt=0,strict=True)
    brand_name:str=Field(default='',max_length=80)
    series_id:int|None=Field(default=None,gt=0,strict=True)
    series_version:int|None=Field(default=None,gt=0,strict=True)
    series_name:str=Field(default='',max_length=120)
    name:str=Field(min_length=1,max_length=120)
    model_year:int=Field(ge=1990,le=2100,strict=True)
    fuel_type:Literal['petrol','diesel','electric','hybrid','plugin_hybrid']
    seats:int=Field(ge=1,le=60,strict=True)
    displacement_ml:int=Field(default=0,ge=0,le=20000,strict=True)
    battery_wh:int=Field(default=0,ge=0,le=2000000,strict=True)
    guide_price_cents:int=Field(default=0,ge=0,le=100000000000,strict=True)


@router.get('/entry-options')
def entry_options(db=Depends(get_db),user=Depends(get_user)):
    return service.entry_options(db,user)


@router.post('/entry')
def entry(body:CatalogueEntry,db=Depends(get_write_db),user=Depends(get_user)):
    values=body.model_dump();key=values.pop('request_id')
    return service.create_entry(db,user,key,values)


@router.get('')
def listing(q:str=Query('',max_length=100),brand_id:int|None=Query(None,gt=0),series_id:int|None=Query(None,gt=0),
            fuel_type:str|None=None,min_seats:int|None=Query(None,ge=1,le=60),max_price_cents:int|None=Query(None,ge=0),
            available_only:bool=False,page:int=Query(1,ge=1),unclassified_page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    return service.catalogue(db,user,q,brand_id,series_id,fuel_type,min_seats,max_price_cents,available_only,page,unclassified_page)


@router.post('/model-assignment')
def model_assignment(body:ModelAssignment,db=Depends(get_write_db),user=Depends(get_user)):
    values=body.model_dump();key=values.pop('request_id');return service.assign(db,user,key,'model',values)


@router.post('/vehicle-assignment')
def vehicle_assignment(body:VehicleAssignment,db=Depends(get_write_db),user=Depends(get_user)):
    values=body.model_dump();key=values.pop('request_id');return service.assign(db,user,key,'vehicle',values)
