"""Original requirement masters/dictionaries: real APIs, store scope and old clients."""
import json
import sqlite3
import uuid
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.flow_models import Item,Reference
from app.master_models import MaterialBrand,ItemProfile
from app.material_brand_integrity import validate
from app.dictionary_api import DICTIONARIES
from tests.conftest import login,TEST_DIR
from tests.test_master_data import create,update
from tests.test_multistore import second_store,switch


def setup_brand(client):
    brand=create(client,'material_brands',{'code':'TEST-BRAND','name':'合成物资品牌'})
    category=create(client,'material_categories',{'code':'TEST-C','name':'合成耗材'})
    warehouse=create(client,'warehouses',{'code':'TEST-W','name':'合成物资库','warehouse_type':'materials'})
    location=create(client,'locations',{'code':'TEST-L','name':'合成库位','warehouse_id':warehouse['id']})
    # Use the original directory endpoint, not direct inventory writes.
    res=client.post('/api/flow/master/items',json={'values':{'sku':'TEST-ITEM','name':'合成配件','unit':'件','reorder':'0','active':True}})
    assert res.status_code==201,res.text
    values={'item_id':res.json()['id'],'category_id':category['id'],'location_id':location['id'],'brand_id':brand['id']}
    profile=create(client,'item_profiles',values)
    return brand,profile,values


def test_brand_native_directory_optional_reference_old_client_and_stop_guard(client):
    brand,profile,values=setup_brand(client)
    catalog=client.get('/api/masters/catalog').json()['kinds']
    assert catalog['material_brands']['can_write']
    assert next(f for f in catalog['item_profiles']['fields'] if f['key']=='brand_id')['ref_kind']=='material_brands'
    rows=client.get('/api/flow/master/items').json()['items']
    assert rows[0]['brand_id']==brand['id'] and rows[0]['brand_name']==brand['name']
    labelled=client.get('/api/masters/item_profiles').json()['items'][0]
    assert labelled['reference_labels']['brand_id']==brand['name']
    old={k:v for k,v in values.items() if k!='brand_id'}
    profile=update(client,'item_profiles',profile,old)
    assert profile['brand_id']==brand['id']
    update(client,'material_brands',brand,{'code':brand['code'],'name':brand['name'],'active':False},status=409)
    profile=update(client,'item_profiles',profile,old|{'brand_id':None})
    assert profile['brand_id'] is None
    brand=update(client,'material_brands',brand,{'code':brand['code'],'name':brand['name'],'active':False})
    update(client,'item_profiles',profile,values,status=422)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as conn:
        assert validate(conn)=={'material_brands':1,'material_brand_bindings':0}


def test_brand_idempotency_stale_duplicates_local_codes_and_foreign_reference(client):
    body={'code':'SAME','name':'本店品牌'};key=uuid.uuid4().hex
    row=create(client,'material_brands',body,key)
    assert create(client,'material_brands',body,key)==row
    create(client,'material_brands',body,status=409)
    create(client,'material_brands',body|{'name':'变造请求'},key,status=409)
    changed=update(client,'material_brands',row,body|{'name':'新名'})
    update(client,'material_brands',row,body,status=409)
    two=second_store(client);switch(client,two)
    assert client.get('/api/masters/material_brands').json()['items']==[]
    update(client,'material_brands',changed,body,status=404)
    create(client,'material_brands',body)
    _,profile,values=setup_brand(client)
    update(client,'item_profiles',profile,values|{'brand_id':row['id']},status=422)
    switch(client,'all');create(client,'material_brands',body|{'code':'NEW'},status=409)


@pytest.mark.parametrize('username,read,write',[('admin',True,True),('manager',True,True),('inventory',True,True),('finance',True,False),('service',True,False),('auditor',True,False),('sales',False,False)])
def test_brand_exact_role_permissions(client,username,read,write):
    login(client,username)
    assert client.get('/api/masters/material_brands').status_code==(200 if read else 403)
    create(client,'material_brands',{'code':'ROLE','name':'合成角色品牌'},status=201 if write else 403)


def test_brand_independent_restore_rejects_foreign_store_inactive_and_missing_domain(client):
    brand,profile,_=setup_brand(client);two=second_store(client)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as conn:
        assert validate(conn)['material_brand_bindings']==1
        conn.execute('UPDATE master_material_brands SET store_id=? WHERE id=?',(two,brand['id']))
        with pytest.raises(ValueError):validate(conn)
        conn.rollback()
        conn.execute('UPDATE master_material_brands SET active=0 WHERE id=?',(brand['id'],))
        with pytest.raises(ValueError):validate(conn)
        conn.execute('UPDATE master_item_profiles SET active=0 WHERE id=?',(profile['id'],))
        assert validate(conn)['material_brand_bindings']==1
        conn.rollback()
    with sqlite3.connect(':memory:') as conn:
        assert validate(conn)=={'material_brands':0,'material_brand_bindings':0}
        conn.execute('CREATE TABLE master_item_profiles(id INTEGER,brand_id INTEGER)')
        with pytest.raises(ValueError):validate(conn)


def dict_create(client,group,values,key=None,status=201):
    result=client.post('/api/dictionaries/'+group,json={'request_id':key or uuid.uuid4().hex,'values':values})
    assert result.status_code==status,result.text
    return result.json()


@pytest.mark.parametrize('group',DICTIONARIES)
def test_seven_dictionary_groups_native_crud_replay_stale_scoping(client,group):
    key=uuid.uuid4().hex;values={'name':'合成字典名','detail':'<script>不应执行</script>','active':True}
    row=dict_create(client,group,values,key)
    assert row['category']==DICTIONARIES[group]['category']
    assert dict_create(client,group,values,key)==row
    dict_create(client,group,values,status=409)
    listing=client.get('/api/dictionaries/'+group+'?q=合成').json()
    assert listing['total']==1 and listing['items'][0]['id']==row['id']
    other='finance' if group!='finance' else 'repair'
    assert client.get('/api/dictionaries/'+other).json()['items']==[]
    changed={'request_id':uuid.uuid4().hex,'version':row['version'],'values':values|{'active':False}}
    r=client.put(f'/api/dictionaries/{group}/{row["id"]}',json=changed)
    assert r.status_code==200 and not r.json()['active'],r.text
    assert client.put(f'/api/dictionaries/{group}/{row["id"]}',json=changed).json()==r.json()
    assert client.put(f'/api/dictionaries/{group}/{row["id"]}',json=changed|{'request_id':uuid.uuid4().hex}).status_code==409
    assert client.put(f'/api/dictionaries/{other}/{row["id"]}',json=changed|{'request_id':uuid.uuid4().hex}).status_code==404
    two=second_store(client);switch(client,two)
    assert client.get('/api/dictionaries/'+group).json()['items']==[]
    dict_create(client,group,values)
    switch(client,'all');dict_create(client,group,values,status=409)
    assert client.get('/api/dictionaries/'+group).status_code==409


def test_dictionary_legacy_category_guard_strict_values_and_writer_permissions(client):
    row=dict_create(client,'repair',{'name':'维修分类','detail':'旧表复用','active':True})
    result=client.put('/api/flow/master/references/'+str(row['id']),json={'version':row['version'],
        'values':{'category':'财务字典','name':'维修分类','detail':'换类','active':True}})
    assert result.status_code==409,result.text
    for values in ({'name':'','active':True},{'name':'坏类型','active':'true'},{'name':'混入状态','state':'approved'}):
        dict_create(client,'repair',values,status=422)
    dict_create(client,'arbitrary',{'name':'任意'},status=404)
    login(client,'sales')
    assert not client.get('/api/dictionaries/catalog').json()['can_write']
    assert client.get('/api/dictionaries/repair').json()['total']==1
    dict_create(client,'repair',{'name':'不应维护'},status=403)


def test_parameter_catalog_fixed_routes_safe_projection_and_no_write_endpoint(client):
    data=client.get('/api/parameters/catalog').json()
    assert data['password_action']=='password' and data['deployment_read_only']
    assert data['deployment']['session_hours']>0
    routes={e['route']:e for e in data['entries']}
    assert routes['membership-rules']['can_write'] and routes['recharge-bundle-rules']['can_write']
    assert routes['service-intake/resources']['can_write']
    forbidden=('deepseek','database_url','private_file_root','password_hash','clamav_host','allowed_hosts','api_key','sqlite:///')
    assert not any(x in json.dumps(data).lower() for x in forbidden)
    assert client.post('/api/parameters/catalog',json={'database_url':'https://invalid'}).status_code==405
    login(client,'manager');manager=client.get('/api/parameters/catalog').json()
    routes={e['route']:e for e in manager['entries']}
    assert not routes['membership-rules']['can_write'] and not routes['recharge-bundle-rules']['can_write']
    assert routes['customer-reminders']['can_write']
    login(client,'sales');sales=client.get('/api/parameters/catalog').json()
    assert sales['deployment'] is None and not any(e['can_write'] for e in sales['entries'])
    assert not any(e['route']=='master/templates' for e in sales['entries'])
    login(client,'admin');two=second_store(client);switch(client,'all')
    aggregate=client.get('/api/parameters/catalog').json()
    assert aggregate['entries']==[] and aggregate['deployment'] is None


def test_master_completion_static_registration_and_node_rendering(client):
    import shutil,subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for name in ['dictionaries','parameters']:
        assert client.get('/static/'+name+'.js').status_code==200
        assert '/static/'+name+'.js' in client.get('/').text
    app=client.get('/static/app.js').text
    assert "type==='dictionaries'" in app and "type==='parameters'" in app
    assert 'clearDictionariesSession' in app and "['brand_name','物资品牌']" in app
    node=shutil.which('node')
    if not node:pytest.skip('Node rendering tests need Node; not real-browser acceptance')
    result=subprocess.run([node,'--test','tests/js/master_completion.test.cjs'],cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('role',['admin','manager','finance','sales','service','inventory','auditor'])
def test_parameter_links_point_to_native_readable_editors(client,role):
    login(client,role)
    paths={'customer-reminders':'/api/customer-service/reminders/rules',
        'customer-questionnaires':'/api/customer-service/questionnaires/versions',
        'service-intake/resources':'/api/service-intake/catalog',
        'membership-rules':'/api/membership/rules','benefits':'/api/group/benefits/rules',
        'recharge-bundle-rules':'/api/recharge-bundles/rules',
        'retail-bundle-rules':'/api/retail-bundles/rules','retail-group-rules':'/api/retail-group/rules',
        'masters':'/api/masters/catalog','dictionaries':'/api/dictionaries/catalog',
        'master/templates':'/api/flow/master/templates'}
    entries=client.get('/api/parameters/catalog').json()['entries']
    for entry in entries:
        response=client.get(paths[entry['route']])
        assert response.status_code==200,(role,entry,response.text)
