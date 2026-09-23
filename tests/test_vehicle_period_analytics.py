"""Synthetic immutable sources; historical fixture dating is explicit test SQL only."""
import csv, io
from datetime import timedelta, datetime
import pytest
from sqlalchemy import select, text
from app.db import SessionLocal, engine, today
from app.models import Vehicle
from app.flow_models import FlowEvent
from tests.conftest import login
from tests.test_vehicle_operations import inventory, create, act, destination, returned_sale
from tests.test_vehicle_procurement import approved, ship, receive, command, ret, VIN
from tests.test_workflow import evidence, seed_car

API = '/api/inventory-reports/vehicles'


def report(c, **params):
    r = c.get(API, params=params); assert r.status_code == 200, r.text
    return r.json()


def assert_csv(c, result, key, **params):
    response = c.get(API+'/export/'+key, params=params); assert response.status_code == 200, response.text
    actual = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    expected = [result['tables'][key]['headers']]+[[str(v) for v in row['values']] for row in result['tables'][key]['rows']]
    assert actual == expected


def test_actual_purchase_other_return_generation_period_not_current(client):
    purchase, vid, loc = inventory(client)
    out = act(client, act(client, create(client, 'other_out', vid), 'approve'), 'dispatch')
    back = act(client, act(client, create(client, 'other_return', location=loc, original=out['id']), 'approve'), 'receive')
    # These are new synthetic facts dated to prove a previous closing, not an application edit path.
    with engine.begin() as db:
        day = (today()-timedelta(days=10)).isoformat()
        db.execute(text('UPDATE vehicle_purchase_movements SET business_date=:day'), {'day':day})
        db.execute(text('UPDATE vehicle_purchase_receipts SET business_date=:day'), {'day':day})
        db.execute(text('UPDATE vehicle_position_entries SET business_date=:day WHERE kind=:kind'), {'day':(today()-timedelta(days=4)).isoformat(),'kind':'other_out'})
        db.execute(text('UPDATE vehicle_position_entries SET business_date=:day WHERE kind=:kind'), {'day':(today()-timedelta(days=2)).isoformat(),'kind':'other_return'})
    params = {'date_from':(today()-timedelta(days=5)).isoformat(),'date_to':(today()-timedelta(days=3)).isoformat()}
    data = report(client, **params)
    assert data['complete'] and data['transit_complete']
    first = next(r for r in data['rows'] if r['vehicle_id']==vid)
    assert first['opening']=={'quantity':1,'value_cents':10000001} and first['out']==first['opening']
    assert first['closing']=={'quantity':0,'value_cents':0}
    assert data['charts'][0]['series'][0]['values']==[1,0,1,0]
    assert len(data['details'])==1 and data['details'][0]['kind']=='other_out'
    current=report(client);assert current['metrics']['vehicle_period_closing_count']==1
    assert {r['generation'] for r in current['rows']}=={1,2}
    assert_csv(client,data,'vehicle_period_balances',**params);assert_csv(client,data,'vehicle_period_movements',**params)
    combined=client.get('/api/flow/analytics',params=params);assert combined.status_code==200,combined.text
    assert combined.json()['tables']['vehicle_period_movements']==data['tables']['vehicle_period_movements']
    common_csv=client.get('/api/flow/analytics/export',params={'dataset':'vehicle_period_movements',**params})
    dedicated_csv=client.get(API+'/export/vehicle_period_movements',params=params)
    def cells(response):
        # Existing general export prefixes formatted negative strings as Excel
        # text; both exports must still contain the identical signed amounts.
        return [[v[1:] if v.startswith("'-") and v[2:].replace('.', '', 1).isdigit() else v for v in row]
                for row in csv.reader(io.StringIO(response.content.decode('utf-8-sig')))]
    assert cells(common_csv)==cells(dedicated_csv)


def test_purchase_return_and_supplier_transit_are_separate(client):
    row, loc=approved(client,2);row=ship(client,row);row=receive(client,row,loc)
    row=ship(client,row,'LHGCM82633A123457')
    row=command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'实际原车退货','evidence_id':evidence(client,row)})
    row=ret(client,row,'return_approve');ret(client,row,'return_dispatch')
    data=report(client);assert data['complete'] and data['charts'][0]['series'][0]['values']==[0,1,1,0]
    assert [r['kind'] for r in data['details']]==['purchase_receive','purchase_return']
    assert len(data['transit'])==1 and data['transit'][0]['kind']=='supplier' and data['transit'][0]['quantity']==1
    assert_csv(client,data,'vehicle_period_transit')


def test_sales_dispatch_counted_once_and_customer_return_new_generation(client):
    source, after, row, loc=returned_sale(client)
    data=report(client);assert data['complete'],data
    assert [f['kind'] for f in data['details']].count('sale_dispatch')==1
    assert data['metrics']['vehicle_period_closing_count']==0
    row=act(client,row,'intake',{'location_id':loc});row=act(client,row,'inspect',{'outcome':'pass','findings':'本次实测验收通过'})
    row=act(client,row,'disposition',{'inspection_id':row['inspections'][-1]['id'],'decision':'release'})
    act(client,row,'release',{'location_id':loc})
    data=report(client);assert data['complete']
    assert [f['kind'] for f in data['details']].count('customer_return')==1
    assert data['charts'][0]['series'][0]['values']==[0,2,1,1]
    assert sum(f['value_cents'] for f in data['details'])==10000001


def test_approved_local_move_does_not_create_inventory_or_date_movements(client):
    _,vid,_=inventory(client);row=act(client,create(client,'local_move',vid,destination(client)),'approve')
    act(client,row,'dispatch');data=report(client)
    assert data['complete'] and data['metrics']['vehicle_period_closing_count']==1
    assert len(data['details'])==1 and data['details'][0]['kind']=='purchase_receive'


def test_opening_source_not_double_counted_with_position(client):
    from tests.test_opening_import import reviewed,confirm
    row,_=reviewed(client);confirm(client,row)
    data=report(client);assert data['complete'] and len(data['details'])==1
    assert data['details'][0]['kind']=='opening' and data['metrics']['vehicle_period_closing_count']==1


def transfer_fixture(c):
    from app.models import Store,User,UserStore
    from app.master_models import Warehouse,StorageLocation
    from tests.test_vehicle_transfers import approved as transfer_approved
    _,vid,loc=inventory(c)
    with SessionLocal() as db:
        db.add(Store(id=2,code='REPORT-B',name='授权调入店'));db.flush()
        for u in db.scalars(select(User)):db.add(UserStore(user_id=u.id,store_id=2,role=None if u.role=='admin' else u.role))
        w=Warehouse(store_id=2,code='VC',name='乙车辆仓',warehouse_type='vehicles');db.add(w);db.flush()
        l=StorageLocation(store_id=2,code='VP',name='乙车辆位',warehouse_id=w.id);db.add(l);db.commit();other=l.id
    return transfer_approved(c,vid),other,loc


def test_group_transfer_in_transit_internal_pairs_and_partial_scope(client):
    from tests.test_vehicle_transfers import command as tc,proof_values,switch
    row,other,_=transfer_fixture(client);tc(client,row,'dispatch',proof_values(client,row))
    data=report(client);assert data['complete'] and not data['transit_complete']
    assert data['transit'][0]['quantity'] is None and '授权范围' in data['transit'][0]['status']
    login(client,'admin');switch(client,'all');data=report(client)
    assert data['complete'] and data['transit_complete'] and data['transit'][0]['quantity']==1
    assert data['metrics']['vehicle_period_closing_count']==0 and all(r['route'] is None for r in data['tables']['vehicle_period_movements']['rows'])
    switch(client,2);tc(client,row,'accept',proof_values(client,row,location_id=other))
    switch(client,'all');data=report(client)
    assert data['complete'] and data['transit_complete'] and not data['transit']
    assert data['metrics']['vehicle_period_closing_count']==1
    assert sum(r['value_cents'] for r in data['details'] if r['internal']=='授权范围内双边调拨')==0
    assert_csv(client,data,'vehicle_period_movements')


def test_legacy_without_source_is_not_invented_and_known_rows_remain(client):
    inventory(client)
    with SessionLocal() as db:
        original=db.scalar(select(Vehicle));uid=original.created_by
        db.add(Vehicle(vin='LHGCM82633A123459',brand='合成旧车',model='缺原始来源',color='白',supplier='原始未知',purchase_cost_cents=999,list_price_cents=1999,doc_no='OLD-SOURCE',business_date=today(),approval_state='approved',created_by=uid));db.commit()
    data=report(client);assert not data['complete'] and data['charts']==[]
    assert data['metrics']['vehicle_period_closing_count'] is None
    assert len(data['details'])==1 and sum(r['reconciled'] for r in data['rows'])==1
    missing=next(r for r in data['rows'] if not r['reconciled'])
    assert missing['opening']['quantity'] is None and missing['closing']['value_cents'] is None


def test_report_and_csv_role_scope_date_and_no_write(client,monkeypatch):
    inventory(client);login(client,'inventory');data=report(client)
    assert not data['can_money'] and 'value_cents' not in data['details'][0] and 'value_cents' not in data['rows'][0]['in']
    assert '原成本' not in str(data['tables']) and '10000001' not in str(data)
    assert client.get(API+'/export/vehicle_period_movements').status_code==200
    login(client,'sales');assert client.get(API).status_code==403 and client.get(API+'/export/vehicle_period_balances').status_code==403
    login(client,'admin');client.post('/api/stores',json={'code':'BLANK','name':'合成空店'});client.headers['X-Store-ID']='2'
    assert report(client)['rows']==[] and client.get(API,params={'vin':VIN}).status_code==404
    assert client.get(API,params={'date_to':(today()+timedelta(days=1)).isoformat()}).status_code==422
    client.headers['X-Store-ID']='1';monkeypatch.setattr('app.inventory_report_common.LIMIT',0)
    assert client.get(API).status_code==422


def test_local_midnight_event_business_day_is_not_utc_day():
    from app.inventory_report_common import local_date
    assert local_date(datetime(2026,9,20,16,1)).isoformat()=='2026-09-21'


def test_same_snapshot_during_concurrent_physical_posting(client):
    from app.vehicle_period_analytics import build_vehicle_period
    from app.tenancy import set_scope,project_user
    from app.models import User
    _,vid,_=inventory(client);out=act(client,create(client,'other_out',vid),'approve')
    with SessionLocal() as old:
        set_scope(old,[1],1);user=project_user(old.scalar(select(User).where(User.username=='admin')),'admin')
        # Open the read transaction before another HTTP command commits an exit.
        assert old.scalar(select(Vehicle.id).where(Vehicle.id==vid))==vid
        act(client,out,'dispatch')
        snapshot=build_vehicle_period(old,user)
        assert snapshot['complete'] and snapshot['metrics']['vehicle_period_closing_count']==1
    fresh=report(client);assert fresh['complete'] and fresh['metrics']['vehicle_period_closing_count']==0


def test_immutable_sales_event_fallback_and_missing_original_cost(client):
    source,_,_,_=returned_sale(client,False)
    with engine.begin() as db:db.execute(text("DELETE FROM vehicle_position_entries WHERE kind='sale_dispatch'"))
    data=report(client);assert data['complete']
    sale=next(f for f in data['details'] if f['kind']=='sale_dispatch')
    assert sale['source']=='flow_events' and sale['value_cents']==-10000001
    with engine.begin() as db:db.execute(text("DELETE FROM vehicle_purchase_movements WHERE kind='receive'"))
    data=report(client);assert not data['complete'] and not data['charts']
    assert '入库成本来源不足' in str(data['rows'][0]['issues'])
