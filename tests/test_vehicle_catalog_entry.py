"""Atomic employee catalogue entry, without touching any existing stock identity."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import User,Vehicle
from app.master_models import VehicleModel,MasterReceipt
from app.vehicle_catalog_models import VehicleBrand,VehicleSeries,ModelClassification
from app.vehicle_catalog_api import CatalogueEntry
from app.vehicle_catalog_service import create_entry
from app.tenancy import set_scope
from tests.conftest import login
from tests.test_master_data import create,update,SAMPLES
from tests.test_multistore import second_store,switch


API='/api/vehicle-catalog'


def payload(**changes):
    return {'request_id':uuid.uuid4().hex,'brand_name':'测试品牌','series_name':'城市车系',
        'name':'长续航旗舰型','model_year':2026,'fuel_type':'electric','seats':5,
        'displacement_ml':0,'battery_wh':60501,'guide_price_cents':13980000,**changes}


def enter(client,body=None,status=200):
    response=client.post(API+'/entry',json=body or payload())
    assert response.status_code==status,response.text
    return response.json()


def counts():
    with SessionLocal() as db:
        return tuple(db.scalar(select(func.count()).select_from(model)) for model in (VehicleBrand,VehicleSeries,VehicleModel,ModelClassification,Vehicle,MasterReceipt))


def selected(brand,series):
    return {'brand_id':brand['id'],'brand_version':brand['version'],'brand_name':'',
        'series_id':series['id'],'series_version':series['version'],'series_name':''}


def test_single_entry_creates_whole_hierarchy_and_replays_without_duplicate(client):
    body=payload();first=enter(client,body)
    assert first['created']=={'brand':True,'series':True,'model':True}
    assert first['series']['brand_id']==first['brand']['id']
    assert first['classification']['model_id']==first['model']['id']
    assert first['classification']['series_id']==first['series']['id']
    assert first['model']['battery_wh']==60501
    assert enter(client,body)==first
    assert counts()==(1,1,1,1,0,1)
    same=enter(client,payload())
    assert same['model']['id']==first['model']['id']
    assert same['created']=={'brand':False,'series':False,'model':False}
    assert counts()==(1,1,1,1,0,2)
    listed=client.get(API).json()['items'][0]
    assert listed['brand_name']=='测试品牌' and listed['series_name']=='城市车系'
    enter(client,{**body,'name':'不同车型'},status=409)
    assert counts()==(1,1,1,1,0,2)


def test_existing_parents_keep_codes_and_new_series_is_created_inline(client):
    brand=create(client,'vehicle_brands',{'code':'EXISTING-B','name':'测试品牌'})
    series=create(client,'vehicle_series',{'code':'EXISTING-S','name':'城市车系','brand_id':brand['id']})
    first=enter(client,payload(**selected(brand,series)))
    assert first['created']=={'brand':False,'series':False,'model':True}
    assert first['brand']['code']=='EXISTING-B' and first['series']['code']=='EXISTING-S'
    # An exact unique existing name is reused even when entered through "new".
    second=enter(client,payload(name='另一个车型',brand_name=' 测试品牌 ',series_name=' 城市车系 '))
    assert second['brand']['id']==brand['id'] and second['series']['id']==series['id']
    third=enter(client,payload(brand_id=brand['id'],brand_version=brand['version'],brand_name='',series_name='全新车系'))
    assert third['created']=={'brand':False,'series':True,'model':True}
    options=client.get(API+'/entry-options').json()
    assert options['brands'][0]['version']==brand['version'] and len(options['series'])==2


def test_invalid_model_rolls_back_new_parents_receipt_and_classification(client):
    before=counts()
    result=enter(client,payload(battery_wh=0),status=422)
    assert '电池' in result['detail'] and counts()==before
    enter(client,payload(fuel_type='petrol',displacement_ml=1500,battery_wh=123),status=422)
    assert counts()==before
    enter(client,payload(seats=5.5),status=422)
    assert counts()==before


def test_stale_parent_and_wrong_brand_leave_no_partial_model(client):
    first=enter(client);brand,series=first['brand'],first['series']
    changed=update(client,'vehicle_brands',brand,{'code':brand['code'],'name':'调整后的品牌'})
    before=counts()
    enter(client,payload(name='另一车型',**selected(brand,series)),status=409)
    assert counts()==before
    enter(client,payload(name='另一车型',**selected(changed,series)))
    series_changed=update(client,'vehicle_series',series,{'code':series['code'],'name':'调整后的车系','brand_id':brand['id']})
    before=counts()
    enter(client,payload(name='第三车型',**selected(changed,series)),status=409)
    other=create(client,'vehicle_brands',{'code':'OTHER-B','name':'其他品牌'})
    before=counts()
    enter(client,payload(name='第三车型',**selected(other,series_changed)),status=422)
    assert counts()==before


def test_role_store_and_aggregate_guards_apply_to_new_entry_and_options(client):
    first=enter(client)
    login(client,'sales')
    enter(client,payload(name='销售不得创建'),status=403)
    assert client.get(API+'/entry-options').status_code==403
    login(client,'inventory');enter(client,payload(name='库管录入车型'))
    login(client);second_store(client);switch(client,2)
    assert client.get(API+'/entry-options').json()=={'brands':[],'series':[]}
    before=counts()
    enter(client,payload(**selected(first['brand'],first['series'])),status=422)
    assert counts()==before
    # Equal names in another store are independent, never shared IDs.
    local=enter(client)
    assert local['brand']['id']!=first['brand']['id'] and local['model']['store_id']==2
    switch(client,'all');enter(client,status=409)
    assert client.get(API+'/entry-options').status_code==403


def test_duplicate_with_different_parameters_does_not_overwrite_existing_model(client):
    original=enter(client);before=counts()
    enter(client,payload(battery_wh=70000),status=409)
    assert counts()==before
    with SessionLocal() as db:
        row=db.scalar(select(VehicleModel).where(VehicleModel.id==original['model']['id']))
        assert row.battery_wh==60501 and row.version==original['model']['version']


def test_old_unclassified_model_is_not_implicitly_attached_or_duplicated(client):
    old=create(client,'vehicle_models',{'code':'OLD-M','name':'长续航旗舰型',**SAMPLES['vehicle_models'],'brand':'测试品牌','model_year':2026})
    before=counts()
    result=enter(client,status=409)
    assert '待确认车系' in result['detail'] and counts()==before
    with SessionLocal() as db:
        assert db.scalar(select(ModelClassification).where(ModelClassification.model_id==old['id'])) is None


def test_ambiguous_or_disabled_parent_requires_explicit_resolution(client):
    brand=create(client,'vehicle_brands',{'code':'DUP-1','name':'测试品牌'})
    create(client,'vehicle_brands',{'code':'DUP-2','name':'测试品牌'})
    before=counts();enter(client,status=409);assert counts()==before
    # An explicit ID is sufficient to choose one of the identically named brands.
    first=enter(client,payload(brand_id=brand['id'],brand_version=brand['version'],brand_name=''))
    assert first['brand']['id']==brand['id']
    disabled=create(client,'vehicle_brands',{'code':'OFF','name':'停用品牌','active':False})
    before=counts();enter(client,payload(brand_name=disabled['name']),status=409);assert counts()==before


def test_parent_id_name_mixture_and_missing_selection_are_rejected(client):
    first=enter(client);before=counts()
    enter(client,payload(brand_id=first['brand']['id'],brand_version=first['brand']['version']),status=422)
    enter(client,payload(brand_name='',series_name='新车系'),status=422)
    enter(client,payload(brand_id=first['brand']['id'],brand_name=''),status=422)
    assert counts()==before


def test_competing_new_entries_cannot_leave_duplicate_or_partial_hierarchies(client):
    barrier=Barrier(2);bodies=[CatalogueEntry(**payload()).model_dump() for _ in range(2)]
    def run(body):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='admin'))
            values=dict(body);key=values.pop('request_id');barrier.wait(timeout=10)
            try:return 200,create_entry(db,user,key,values)
            except HTTPException as exc:return exc.status_code,None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,bodies))
    assert all(status in {200,409} for status,_ in results) and any(status==200 for status,_ in results)
    assert counts()[:5]==(1,1,1,1,0)
    # The losing safe retry or completed replay resolves to the same current model.
    ids={enter(client,body)['model']['id'] for body in bodies}
    assert len(ids)==1 and counts()[:5]==(1,1,1,1,0)
