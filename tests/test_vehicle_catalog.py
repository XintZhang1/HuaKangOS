"""Explicit hierarchy, original stock identity and current allocation bounds."""
import uuid,sqlite3
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Vehicle
from app.vehicle_catalog_service import model_snapshot
from app.tenancy import set_scope
from tests.test_master_data import create,update,SAMPLES
from tests.test_workflow import seed_car,order,action
from tests.test_multistore import second_store,switch
from tests.conftest import login,TEST_DIR
from tests.test_repair_orders import technician

API='/api/vehicle-catalog'


def setup(c):
    brand=create(c,'vehicle_brands',{'code':'CAT-B','name':'明确品牌'})
    series=create(c,'vehicle_series',{'code':'CAT-S','name':'城市车系','brand_id':brand['id']})
    model=create(c,'vehicle_models',{'code':'CAT-M','name':'测试车型',**SAMPLES['vehicle_models']})
    return brand,series,model


def list_catalog(c,**params):
    response=c.get(API,params=params);assert response.status_code==200,response.text;return response.json()


def classify(c,series,model,version=0,status=200,key=None):
    r=c.post(API+'/model-assignment',json={'request_id':key or uuid.uuid4().hex,'version':version,
        'reason':'主管逐一核对原品牌车系资料','model_id':model['id'],'model_version':model['version'],'series_id':series['id']})
    assert r.status_code==status,r.text;return r.json()


def link_car(c,car,model,version=0,status=200,**extra):
    with SessionLocal() as db:row=db.scalar(select(Vehicle).where(Vehicle.id==car));vin=row.vin;v=row.version
    response=c.post(API+'/vehicle-assignment',json={'request_id':uuid.uuid4().hex,'version':version,
        'reason':'按本库存VIN人工确认车型','vehicle_id':car,'vehicle_version':v,'vin':vin,'model_id':model['id'],**extra})
    assert response.status_code==status,response.text;return response.json()


def test_hierarchy_version_no_text_inference_and_stock_allocation_guard(client):
    brand,series,model=setup(client);car=seed_car()
    before=list_catalog(client)
    assert before['items'][0]['stock_count']==0 and len(before['unclassified'])==1
    key=uuid.uuid4().hex;first=classify(client,series,model,key=key)
    assert classify(client,series,model,key=key)==first
    classify(client,series,model,status=409)
    link_car(client,car,model);shown=list_catalog(client,brand_id=brand['id'],available_only=True)
    assert shown['items'][0]['available_count']==shown['items'][0]['stock_count']==1
    assert 'purchase_cost_cents' not in str(shown)
    row=action(client,order(client),'approve');action(client,row,'allocate',{'vehicle_id':car})
    assert list_catalog(client)['items'][0]['available_count']==0
    assert list_catalog(client,available_only=True)['items']==[]


def test_filters_roles_stale_cross_store_and_disabled_parents(client):
    brand,series,model=setup(client);classify(client,series,model)
    assert list_catalog(client,fuel_type='petrol')['items']==[]
    assert list_catalog(client,min_seats=6)['items']==[]
    assert list_catalog(client,max_price_cents=1)['items']==[]
    update(client,'vehicle_brands',brand,{'code':brand['code'],'name':brand['name'],'active':False},status=409)
    update(client,'vehicle_series',series,{'code':series['code'],'name':series['name'],'brand_id':brand['id'],'active':False},status=409)
    login(client,'sales');assert list_catalog(client)['can_manage'] is False
    classify(client,series,model,version=1,status=403)
    login(client);second_store(client);switch(client,2)
    assert list_catalog(client)['items']==[]
    classify(client,series,model,version=1,status=422)
    switch(client,'all');assert client.get(API).status_code==409
    switch(client,1);login(client,'technician');assert client.get(API).status_code==403


def test_new_quote_snapshot_preserves_explicit_brand_and_current_parameter_version(client):
    brand,series,model=setup(client);classify(client,series,model)
    with SessionLocal() as db:
        set_scope(db,[1],1);frozen=model_snapshot(db,model['id'])
    update(client,'vehicle_series',series,{'code':series['code'],'name':'经确认的新展示名称','brand_id':brand['id']})
    with SessionLocal() as db:
        set_scope(db,[1],1);fresh=model_snapshot(db,model['id'])
    assert frozen['series_name']=='城市车系' and fresh['series_name']=='经确认的新展示名称'
    assert frozen['brand_name']=='明确品牌' and fresh['series_version']>frozen['series_version']


def test_authoritative_purchase_model_cannot_be_overridden_by_free_text_mapping(client):
    from tests.test_vehicle_procurement import approved,ship,receive
    row,location=approved(client,1);row=ship(client,row,'LCATAL0G000000001')
    row=receive(client,row,location);car=row['receipts'][0]['vehicle_id']
    brand,series,wrong=setup(client)
    link_car(client,car,wrong,status=409)
    result=list_catalog(client)
    correct=next(r for r in result['items'] if r['id']==row['lines'][0]['model_id'])
    assert correct['stock_count']==1 and correct['vehicles'][0]['source']=='原入库车型'
    link_car(client,car,wrong,status=422,vin='LCATAL0G000000002')


def test_catalogue_refuses_reclassification_of_allocated_vehicle_and_rejects_cross_store_restore(client):
    import pytest
    from app.vehicle_catalog_integrity import validate_catalogue
    brand,series,model=setup(client);car=seed_car();first=link_car(client,car,model)
    another=create(client,'vehicle_models',{'code':'CAT-OTHER','name':'另一明确车型',**SAMPLES['vehicle_models']})
    row=action(client,order(client),'approve');action(client,row,'allocate',{'vehicle_id':car})
    link_car(client,car,another,version=first['version'],status=409)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_catalogue(restored)['verified_vehicle_classifications']==1
        restored.execute('UPDATE catalog_vehicle_classifications SET store_id=2')
        with pytest.raises(ValueError,match='跨店'):validate_catalogue(restored)
