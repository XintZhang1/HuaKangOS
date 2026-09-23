"""Typed references, opening rollback, immutable source and stock conservation."""
import csv
import io
import json
import uuid
import pytest
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db import SessionLocal, today
from app.models import User, Store, AppMetadata
from app.flow_models import Customer, Account, Item, Case, StockMove
from app.master_models import OpeningBatch, OpeningStockEntry
from app.master_data import require_active
from app.tenancy import set_scope
from tests.conftest import login
from tests.test_multistore import second_store, switch


def create(c,kind,values,key=None,status=201):
    r=c.post('/api/masters/'+kind,json={'request_id':key or uuid.uuid4().hex,'values':values})
    assert r.status_code==status,r.text
    return r.json()


def update(c,kind,row,values,key=None,status=200):
    r=c.put(f'/api/masters/{kind}/{row["id"]}',json={'request_id':key or uuid.uuid4().hex,'version':row['version'],'values':values})
    assert r.status_code==status,r.text
    return r.json()


SAMPLES={
    'suppliers':{'payment_terms_days':30,'tax_identifier':'TEST-0001'},
    'insurers':{'license_number':'TEST-I','settlement_days':15},
    'warehouses':{'warehouse_type':'materials'},
    'material_categories':{},
    'work_items':{'billing_unit':'hour','standard_minutes':60,'standard_fee_cents':15000},
    'teams':{},
    'agency_projects':{'service_fee_cents':30000,'expected_days':3},
    'vehicle_models':{'brand':'虚构牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':12000000},
    'member_tiers':{'annual_fee_cents':10000,'validity_months':12,'discount_basis_points':9000},
}


@pytest.mark.parametrize('kind',SAMPLES)
def test_typed_master_happy_duplicate_stale_and_scope(client,kind):
    key=uuid.uuid4().hex;body={'code':'DEMO','name':'虚构资料',**SAMPLES[kind]}
    row=create(client,kind,body,key)
    assert create(client,kind,body,key)==row
    assert len(client.get('/api/masters/'+kind).json()['items'])==1
    changed=update(client,kind,row,body|{'name':'已核对虚构资料'})
    assert changed['version']==row['version']+1
    update(client,kind,row,body,status=409)
    two=second_store(client);switch(client,two)
    assert client.get('/api/masters/'+kind).json()['items']==[]
    update(client,kind,changed,body,status=404)
    create(client,kind,body)  # code is store scoped
    switch(client,'all');create(client,kind,body,status=409)


def test_typed_reference_and_deactivation_guards(client):
    warehouse=create(client,'warehouses',{'code':'W','name':'物资库','warehouse_type':'materials'})
    loc=create(client,'locations',{'code':'L','name':'一号库位','warehouse_id':warehouse['id']})
    category=create(client,'material_categories',{'code':'C','name':'耗材'})
    supplier=create(client,'suppliers',{'code':'S','name':'虚构供应商'})
    with SessionLocal() as db:
        item=Item(sku='I',name='测试物资');db.add(item);db.commit();item_id=item.id
    profile=create(client,'item_profiles',{'item_id':item_id,'category_id':category['id'],'location_id':loc['id'],'supplier_id':supplier['id']})
    shown=client.get('/api/masters/item_profiles?q=测试物资').json()['items'][0]
    assert shown['reference_labels']['item_id']=='测试物资' and shown['reference_labels']['location_id']=='一号库位'
    assert client.get('/api/masters/item_profiles?q=不匹配').json()['items']==[]
    update(client,'warehouses',warehouse,{'code':'W','name':'物资库','warehouse_type':'vehicles'},status=409)
    other=create(client,'warehouses',{'code':'W2','name':'另一个库','warehouse_type':'materials'})
    update(client,'locations',loc,{'code':'L','name':'一号库位','warehouse_id':other['id']},status=409)
    for kind,row,body in [('warehouses',warehouse,{'warehouse_type':'materials'}),('locations',loc,{'warehouse_id':warehouse['id']}),('material_categories',category,{}),('suppliers',supplier,{})]:
        update(client,kind,row,{'code':row['code'],'name':row['name'],'active':False,**body},status=409)
    two=second_store(client);switch(client,two)
    create(client,'locations',{'code':'BAD','name':'越店库位','warehouse_id':warehouse['id']},status=422)
    with SessionLocal() as db:
        set_scope(db,[two],two)
        with pytest.raises(HTTPException):require_active(db,'suppliers',supplier['id'])
    switch(client,1)
    profile=update(client,'item_profiles',profile,{k:profile[k] for k in ['item_id','category_id','location_id','supplier_id']}|{'active':False})
    supplier=update(client,'suppliers',supplier,{'code':'S','name':'虚构供应商','active':False})
    update(client,'item_profiles',profile,{k:profile[k] for k in ['item_id','category_id','location_id','supplier_id']}|{'active':True},status=422)


def test_category_cycles_and_employee_roles_refused(client):
    parent=create(client,'material_categories',{'code':'P','name':'上级'})
    child=create(client,'material_categories',{'code':'C','name':'下级','parent_id':parent['id']})
    update(client,'material_categories',parent,{'code':'P','name':'上级','parent_id':child['id']},status=422)
    with SessionLocal() as db:
        finance=db.scalar(select(User).where(User.username=='finance'))
        finance_id=finance.id
    create(client,'teams',{'code':'T','name':'错误班组','leader_user_id':finance_id},status=422)
    login(client,'inventory')
    create(client,'warehouses',{'code':'W','name':'物资仓','warehouse_type':'materials'})
    create(client,'suppliers',{'code':'S','name':'不允许供应商'},status=403)


@pytest.mark.parametrize('kind,extra',[
    ('suppliers',{'payment_terms_days':-1}),('work_items',{'standard_fee_cents':1.01}),
    ('vehicle_models',{'fuel_type':'electric','displacement_ml':1000}),
    ('vehicle_models',{'fuel_type':'petrol','battery_wh':0,'displacement_ml':0}),
    ('member_tiers',{'discount_basis_points':10001}),('suppliers',{'arbitrary_json':{'state':'approved'}}),
])
def test_strict_business_master_values(client,kind,extra):
    create(client,kind,{'code':'INVALID','name':'错误资料',**SAMPLES[kind],**extra},status=422)


def test_vehicle_parameters_filter_actual_population(client):
    create(client,'vehicle_models',{'code':'E','name':'纯电车型',**SAMPLES['vehicle_models']})
    create(client,'vehicle_models',{'code':'P','name':'燃油车型',**SAMPLES['vehicle_models'],'fuel_type':'petrol','displacement_ml':1500,'battery_wh':0,'guide_price_cents':8000000})
    data=client.get('/api/masters/vehicle_models?fuel_type=electric&min_seats=5&max_price_cents=13000000').json()
    assert data['total']==1 and data['items'][0]['code']=='E'


def source(**changes):
    value={'opening_date':today().isoformat(),'source_reference':'虚构盘点与主档清单-001',
        'customers':[{'name':'合成客户','phone':'13900000000','owner_username':'sales'}],
        'accounts':[{'name':'合成账户','account_type':'bank'}],
        'items':[{'sku':'OPEN','name':'合成耗材','unit':'升','opening_quantity_milli':2500,
                  'opening_value_cents':12345,'source_reference':'虚构盘点表第1行'},
                 {'sku':'ZERO','name':'零库存物资'}]}
    return value|changes


def preflight(c,data=None,key=None):
    r=c.post('/api/masters/opening/preflight',json={'request_id':key or uuid.uuid4().hex,
        'source_text':json.dumps(data or source(),ensure_ascii=False)})
    assert r.status_code==200,r.text
    return r.json()


def review(c,batch,confirm=False,key=None,status=200,**changes):
    body={'request_id':key or uuid.uuid4().hex,'version':batch['version'],'digest':batch['source_digest']}
    if confirm:body|={'confirmed':True,'expected_totals':batch['totals']}
    body|=changes
    r=c.post(f'/api/masters/opening/{batch["id"]}/'+('confirm' if confirm else 'trial'),json=body)
    assert r.status_code==status,r.text
    return r.json()


def count_business():
    with SessionLocal() as db:
        return [db.scalar(select(func.count()).select_from(m)) for m in (Customer,Account,Item,OpeningStockEntry)]


def test_opening_preflight_trial_rollback_confirm_idempotent_and_stockflow(client):
    key=uuid.uuid4().hex;body=source()
    checked=preflight(client,body,key);batch=checked['batch']
    assert checked['valid'] and count_business()==[0,0,0,0]
    review(client,batch,confirm=True,status=409)
    review(client,batch,status=409,digest='0'*64)
    tested=review(client,batch)['batch']
    assert tested['status']=='trial_passed' and count_business()==[0,0,0,0]
    review(client,batch,status=409)
    wrong=tested['totals']|{'inventory_value_cents':12346}
    review(client,tested,confirm=True,status=409,expected_totals=wrong)
    request_id=uuid.uuid4().hex
    confirmed=review(client,tested,confirm=True,key=request_id)
    assert confirmed==review(client,tested,confirm=True,key=request_id)
    assert preflight(client,body,key)==checked  # exact old reply, never import again
    assert count_business()==[1,1,2,1]
    rows=client.get('/api/masters/opening/stockflow').json()
    assert rows['all_reconciled'] and rows['rows'][0]['value_cents']==12345
    csv_rows=list(csv.DictReader(io.StringIO(client.get('/api/masters/opening/stockflow/export').content.decode('utf-8-sig'))))
    assert len(csv_rows)==len(rows['rows']) and int(csv_rows[0]['变动价值（分）'])==12345
    assert not preflight(client)['valid']


def test_opening_errors_are_row_specific_and_do_not_write_business(client):
    body=source(customers=[{'name':'合成客户','owner_username':'finance'}],accounts=[{'name':'重复','account_type':'bank'},{'name':'重复','account_type':'cash'}],
                items=[{'sku':'BAD','name':'有库存没来源','opening_quantity_milli':1}])
    checked=preflight(client,body)
    assert not checked['valid'] and checked['errors'][0]['section']=='items' and checked['errors'][0]['row']==1
    assert count_business()==[0,0,0,0]
    body['items']=[]
    checked=preflight(client,body)
    assert {e['section'] for e in checked['errors']}=={'accounts','customers'}
    assert count_business()==[0,0,0,0]


@pytest.mark.parametrize('changes',[
    {'items':[{'sku':'M','name':'坏金额','opening_value_cents':1}]},
    {'items':[{'sku':'M','name':'坏精度','opening_quantity_milli':1.5}]},
    {'opening_date':'2999-01-01'},
])
def test_opening_rejects_precision_and_future_dates(client,changes):
    assert not preflight(client,source(**changes))['valid']
    assert count_business()==[0,0,0,0]


def test_opening_source_immutable_and_scope_checks(client):
    batch=preflight(client)['batch']
    original=client.get(f'/api/masters/opening/{batch["id"]}/source')
    assert original.status_code==200 and original.json()['source_digest']==batch['source_digest']
    two=second_store(client);switch(client,two)
    assert client.get(f'/api/masters/opening/{batch["id"]}/source').status_code==404
    review(client,batch,status=404)
    switch(client,1);login(client,'inventory')
    assert client.get(f'/api/masters/opening/{batch["id"]}/source').status_code==403
    r=client.post('/api/masters/opening/preflight',json={'request_id':uuid.uuid4().hex,'source_text':json.dumps(source())})
    assert r.status_code==403
    with SessionLocal() as db:
        row=db.get(OpeningBatch,batch['id']);row.source_text='{}'
        with pytest.raises(HTTPException):db.commit()


def test_opening_digest_preserves_original_source_whitespace(client):
    import hashlib
    raw=' \n'+json.dumps(source(),ensure_ascii=False,indent=2)+'\r\n'
    response=client.post('/api/masters/opening/preflight',json={'request_id':uuid.uuid4().hex,'source_text':raw})
    assert response.status_code==200 and response.json()['valid']
    batch=response.json()['batch']
    assert batch['source_digest']==hashlib.sha256(raw.encode('utf-8')).hexdigest()
    assert client.get(f'/api/masters/opening/{batch["id"]}/source').json()['source_text']==raw
    review(client,batch)


def test_opening_confirm_revalidates_new_business_and_demo_marker(client):
    batch=review(client,preflight(client)['batch'])['batch']
    with SessionLocal() as db:
        db.add(Account(name='中途新增账户'));db.commit()
    review(client,batch,confirm=True,status=409)
    assert count_business()==[0,1,0,0]
    with SessionLocal() as db:
        db.add(AppMetadata(key='demo',value={'enabled':True}));db.commit()
    assert any('演示' in e['message'] for e in preflight(client)['errors'])


def test_opening_inventory_issue_return_conserves_every_fen(client):
    batch=review(client,preflight(client)['batch'])['batch'];review(client,batch,confirm=True)
    from app.flow_engine import stock_move
    with SessionLocal() as db:
        set_scope(db,[1],1)
        user=db.scalar(select(User).where(User.username=='admin'))
        item=db.scalar(select(Item).where(Item.sku=='OPEN'))
        case=Case(kind='repair',state='working',number='SYNTHETIC-STOCK',title='合成库存验证',owner_id=user.id,created_by=user.id,business_date=today())
        db.add(case);db.flush()
        issued=stock_move(db,user,case,item,-1000,item.unit_cost_cents,'issue')
        stock_move(db,user,case,item,400,issued.unit_cost_cents,'return',issued)
        stock_move(db,user,case,item,600,issued.unit_cost_cents,'return',issued)
        db.commit()
    result=client.get('/api/masters/opening/stockflow').json()
    assert result['all_reconciled']
    assert result['totals'][0]['value_cents']==12345 and result['totals'][0]['quantity_milli']==2500


def test_opening_import_failure_rolls_back_every_fact(client,monkeypatch):
    from app import master_data
    batch=review(client,preflight(client)['batch'])['batch']
    original=master_data._apply_opening
    def fail_after_postings(*args):
        original(*args)
        raise HTTPException(409,'合成故障：验证整批回滚')
    monkeypatch.setattr(master_data,'_apply_opening',fail_after_postings)
    review(client,batch,confirm=True,status=409)
    assert count_business()==[0,0,0,0]
    with SessionLocal() as db:assert db.get(OpeningBatch,batch['id']).status=='trial_passed'


def test_competing_opening_confirmations_post_once(client):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    first=review(client,preflight(client)['batch'])['batch']
    second=review(client,preflight(client)['batch'])['batch']
    def confirm(batch):
        with TestClient(app) as worker:
            worker.cookies.update(client.cookies)
            worker.headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
            return worker.post(f'/api/masters/opening/{batch["id"]}/confirm',json={
                'request_id':uuid.uuid4().hex,'version':batch['version'],'digest':batch['source_digest'],
                'confirmed':True,'expected_totals':batch['totals']}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(confirm,[first,second]))
    assert sorted(codes)==[200,409]
    assert count_business()==[1,1,2,1]


@pytest.mark.parametrize('role,allowed',[
    ('sales',{'agency_projects','vehicle_models','vehicle_brands','vehicle_series','member_tiers'}),
    ('service',{'insurers','warehouses','locations','material_brands','material_categories','work_items','teams','agency_projects','vehicle_models','vehicle_brands','vehicle_series','member_tiers','item_profiles'}),
    ('inventory',{'suppliers','warehouses','locations','material_brands','material_categories','teams','vehicle_models','vehicle_brands','vehicle_series','item_profiles'}),
    ('reception',set()),('customer_service',set()),
    ('technician',{'warehouses','locations','material_brands','material_categories','work_items','teams','item_profiles'}),
])
def test_master_catalog_list_lookup_have_same_read_boundary(client,role,allowed):
    from app.models import UserStore
    from tests.conftest import PASSWORD_HASH
    from app.master_data import CATALOG
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.username==role)):
            row=User(username=role,display_name=role,role=role,password_hash=PASSWORD_HASH,must_change_password=False)
            db.add(row);db.flush();db.add(UserStore(user_id=row.id,store_id=1));db.commit()
    login(client,role)
    assert set(client.get('/api/masters/catalog').json()['kinds'])==allowed
    for kind in CATALOG:
        assert client.get('/api/masters/'+kind).status_code==(200 if kind in allowed else 403)
        # Item profiles are bindings, not a selectable named master.
        if kind!='item_profiles':assert client.get('/api/masters/lookup/'+kind).status_code==(200 if kind in allowed else 403)
    assert client.get('/api/masters/lookup/employees').status_code==(200 if 'teams' in allowed else 403)


def test_inventory_and_technician_sensitive_master_fields_not_serialized(client):
    create(client,'suppliers',{'code':'S','name':'供应商','tax_identifier':'TEST-SECRET','payment_terms_days':30})
    create(client,'work_items',{'code':'W','name':'作业','billing_unit':'job','standard_fee_cents':12345})
    batch=review(client,preflight(client)['batch'])['batch'];review(client,batch,confirm=True)
    login(client,'inventory')
    row=client.get('/api/masters/suppliers').json()['items'][0]
    assert not {'tax_identifier','payment_terms_days'} & row.keys()
    fields=client.get('/api/masters/catalog').json()['kinds']['suppliers']['fields']
    assert not {'tax_identifier','payment_terms_days'} & {r['key'] for r in fields}
    ledger=client.get('/api/masters/opening/stockflow').json()
    assert not ledger['can_money'] and ledger['all_reconciled']
    assert 'value_cents' not in ledger['rows'][0] and 'current_value_cents' not in ledger['totals'][0]
    assert '价值' not in client.get('/api/masters/opening/stockflow/export').text
    from app.models import UserStore
    from tests.conftest import PASSWORD_HASH
    with SessionLocal() as db:
        u=User(username='technician',role='technician',display_name='技师',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));db.commit()
    login(client,'technician')
    assert 'standard_fee_cents' not in client.get('/api/masters/work_items').json()['items'][0]
    assert 'standard_fee_cents' not in {r['key'] for r in client.get('/api/masters/catalog').json()['kinds']['work_items']['fields']}


def test_frozen_master_migration_has_constraints_and_expected_columns(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect,text
    from sqlalchemy.exc import IntegrityError
    from app.db import Base
    config=Config('alembic.ini');path=tmp_path/'independent-migration.sqlite'
    config.attributes['url_override']='sqlite:///'+path.as_posix()
    command.upgrade(config,'h208_master_data')
    engine=create_engine(config.attributes['url_override'])
    try:
        inspector=inspect(engine)
        for name in Base.metadata.tables:
            if name=='master_material_brands':
                assert name not in inspector.get_table_names()  # Added only by t02g; h208 stays frozen.
                continue
            if name.startswith('master_') or name in {'opening_batches','opening_stock_entries'}:
                expected=set(Base.metadata.tables[name].columns.keys())
                if name=='master_item_profiles':expected-= {'brand_id'}
                assert {r['name'] for r in inspector.get_columns(name)}==expected
        with engine.begin() as db:
            assert db.execute(text('PRAGMA foreign_key_check')).first() is None
            db.execute(text("INSERT OR IGNORE INTO stores(id,code,name,active,created_at) VALUES (1,'T','合成店',1,CURRENT_TIMESTAMP)"))
            with pytest.raises(IntegrityError):
                db.execute(text("INSERT INTO master_suppliers(store_id,version,code,name,active,tax_identifier,contact_name,phone,payment_terms_days,created_at,updated_at) VALUES (1,1,'BAD','错误供货商',1,'','','',366,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    finally:engine.dispose()
