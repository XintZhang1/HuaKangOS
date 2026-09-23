"""VIN acquisition, prepayment, physical return and original cash conserve independently."""
import csv,io,uuid,sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today,engine
from app.models import User,Vehicle,Store,UserStore,CashEntry
from app.flow_models import Case,Account,VehicleHold,Task
from app.vehicle_procurement_models import VehiclePurchaseReceipt,VehiclePurchaseMovement,VehiclePurchasePayment,VehiclePurchasePrice
from app import vehicle_procurement_service as svc
from app.tenancy import set_scope,project_user
from tests.conftest import login
from tests.test_workflow import evidence,master

API='/api/vehicle-procurement';VIN='LHGCM82633A123456'
def typed(c,kind,values):
    r=c.post('/api/masters/'+kind,json={'request_id':uuid.uuid4().hex,'values':values});assert r.status_code==201,r.text;return r.json()
def setup(c,quantity=2):
    s=typed(c,'suppliers',{'code':'S'+uuid.uuid4().hex[:6],'name':'虚构整车供货商','payment_terms_days':30})
    model=typed(c,'vehicle_models',{'code':'M'+uuid.uuid4().hex[:6],'name':'虚构型号','brand':'合成品牌','model_year':2026,'fuel_type':'electric','seats':5,'battery_wh':60000,'guide_price_cents':12000001})
    w=typed(c,'warehouses',{'code':'W'+uuid.uuid4().hex[:6],'name':'整车仓','warehouse_type':'vehicles'})
    loc=typed(c,'locations',{'code':'L'+uuid.uuid4().hex[:6],'name':'验收位','warehouse_id':w['id']})
    v={'supplier_id':s['id'],'contracting_party':'虚构门店经营主体','reason':'合成整车补库','due_date':today().isoformat(),'lines':[{'model_id':model['id'],'color':'白','quantity':quantity}]}
    return v,loc['id']
def create(c,v):
    r=c.post(API+'/orders',json={'request_id':uuid.uuid4().hex,**v});assert r.status_code==201,r.text;return r.json()
def get(c,row):
    r=c.get(API+'/orders/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def command(c,row,action,v=None,status=200,version=None,key=None):
    current=get(c,row);r=c.post(API+f'/orders/{row["id"]}/actions/{action}',json={'request_id':key or uuid.uuid4().hex,'version':current['version'] if version is None else version,'values':v or {}})
    assert r.status_code==status,r.text;return r.json()
def approved(c,quantity=2):
    v,loc=setup(c,quantity);row=create(c,v)
    row=command(c,row,'approve',{'prices':[{'line_id':row['lines'][0]['id'],'unit_cost_cents':10000001,'list_price_cents':12000000}],'evidence_id':evidence(c,row,'invoice')})
    return row,loc
def ship(c,row,vin=VIN):return command(c,row,'ship',{'line_id':get(c,row)['lines'][0]['id'],'vin':vin,'shipped_date':today().isoformat(),'expected_date':today().isoformat(),'evidence_id':evidence(c,row)})
def receive(c,row,loc,shipment=None):
    s=shipment or get(c,row)['shipments'][-1];return command(c,row,'receive',{'shipment_id':s['id'],'vin':s['vin'],'location_id':loc,'evidence_id':evidence(c,row)})
def funds(c,row,amount):return command(c,row,'request_funds',{'amount_cents':amount,'reason':'依据真实合同请款','evidence_id':evidence(c,row,'receipt')})
def bank(c):return master(c,'accounts',{'name':'实际账户'+uuid.uuid4().hex[:8],'account_type':'bank','active':True})['id']
def pay(c,row,account,amount):return command(c,row,'pay',{'funds_request_id':get(c,row)['funds_requests'][-1]['id'],'amount_cents':amount,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')})
def ret(c,row,action,**extra):
    r=get(c,row)['returns'][-1];v={'return_id':r['id'],'return_version':r['version'],'reason':'已核对实际退车原因'}
    if action=='return_dispatch':v['evidence_id']=evidence(c,row)
    return command(c,row,action,v,**extra)

def test_prepaid_partial_receipt_unshipped_cancel_return_cash_conserves(client):
    row,loc=approved(client);assert row['totals']['approved_cents']==20000002
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Vehicle))==0
    row=funds(client,row,20000002);account=bank(client);row=pay(client,row,account,5000000);row=pay(client,row,account,15000002)
    assert row['totals']['prepaid_cents']==20000002 and row['totals']['payable_cents']==0
    row=ship(client,row);assert row['totals']['in_transit_quantity']==1 and not row['receipts']
    row=receive(client,row,loc);assert row['totals']['prepaid_cents']==10000001
    row=command(client,row,'cancel_remaining',{'reason':'供货方确认取消未发运余量','evidence_id':evidence(client,row)})
    assert row['totals']['supplier_refund_due_cents']==10000001
    original=row['payments'][1]
    row=command(client,row,'refund',{'original_payment_id':original['id'],'amount_cents':10000001,'account_id':account,'reference':'FIRST-RETURN','evidence_id':evidence(client,row,'receipt')})
    assert row['state']=='completed' and row['totals']['paid_net_cents']==10000001
    row=command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'确认原车存在供应原因需退回','evidence_id':evidence(client,row)})
    assert client.get('/api/flow/lookup/vehicle').json()['items']==[]
    ret(client,row,'return_dispatch',status=403)
    row=ret(client,row,'return_approve');row=ret(client,row,'return_dispatch')
    assert row['totals']['returned_cents']==10000001 and row['totals']['supplier_refund_due_cents']==10000001
    for original,amount in [(row['payments'][0],5000000),(row['payments'][1],5000001)]:
        row=command(client,row,'refund',{'original_payment_id':original['id'],'amount_cents':amount,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(client,row,'receipt')})
    assert row['state']=='completed' and row['totals']['paid_net_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(Vehicle)).approval_state=='void'
        assert sum(m.quantity for m in db.scalars(select(VehiclePurchaseMovement)))==0
        assert sum(m.value_cents for m in db.scalars(select(VehiclePurchaseMovement)))==0
        assert sum(c.amount_cents*(1 if c.direction=='in' else -1) for c in db.scalars(select(CashEntry)))==0
    report=client.get(API+'/reconciliation').json();csv_rows=list(csv.reader(io.StringIO(client.get(API+'/reconciliation/export').content.decode('utf-8-sig'))))
    assert list(map(int,csv_rows[1][3:]))==[report['totals'][k] for k in ['commitment_cents','received_cents','returned_cents','paid_net_cents','payable_cents','prepaid_cents','supplier_refund_due_cents']]

def test_employee_roles_price_privacy_and_actual_duties(client):
    v,loc=setup(client,1);login(client,'inventory');row=create(client,v)
    assert 'totals' not in row
    command(client,row,'approve',{'prices':[{'line_id':row['lines'][0]['id'],'unit_cost_cents':123,'list_price_cents':300}],'evidence_id':evidence(client,row)},status=403)
    login(client,'manager');row=command(client,row,'approve',{'prices':[{'line_id':row['lines'][0]['id'],'unit_cost_cents':123,'list_price_cents':300}],'evidence_id':evidence(client,row,'invoice')})
    row=funds(client,row,123);account=bank(client);login(client,'finance');row=pay(client,row,account,123)
    login(client,'inventory');row=ship(client,row);row=receive(client,row,loc)
    assert not {'unit_cost_cents','list_price_cents'}&row['lines'][0].keys() and 'value_cents' not in row['receipts'][0]
    assert not row['funds_requests'] and not row['payments']
    assert client.get(API+'/reconciliation').status_code==403
    generic=client.get('/api/flow/cases/'+str(row['id'])).json();assert generic.get('amount_cents') is None
    login(client,'sales');assert client.get(API+'/orders').status_code==403
    assert client.get(API+'/orders/'+str(row['id'])).status_code==403
    login(client,'admin');client.headers['X-Store-ID']='all';assert client.get(API+'/orders').status_code==409

def test_duplicate_stale_and_failed_multi_price_approval_rollback(client):
    v,loc=setup(client);row=create(client,v);key=uuid.uuid4().hex;version=row['version'];e=evidence(client,row,'invoice')
    p={'line_id':row['lines'][0]['id'],'unit_cost_cents':123,'list_price_cents':456}
    command(client,row,'approve',{'prices':[p,p],'evidence_id':e},422)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(VehiclePurchasePrice))==0
    result=command(client,row,'approve',{'prices':[p],'evidence_id':e},key=key,version=version)
    assert command(client,row,'approve',{'prices':[p],'evidence_id':e},key=key,version=version)==result
    command(client,row,'cancel_remaining',{'reason':'旧版拒绝','evidence_id':e},409,version=version)

def test_global_vin_conflict_cross_store_and_terminal_return_reentry(client):
    row,loc=approved(client,1);row=ship(client,row);row=receive(client,row,loc);first=row['receipts'][0]['vehicle_id']
    client.post('/api/stores',json={'code':'VP-B','name':'采购乙店'});client.headers['X-Store-ID']='2';other,otherloc=approved(client,1)
    command(client,other,'ship',{'line_id':other['lines'][0]['id'],'vin':VIN,'shipped_date':today().isoformat(),'expected_date':today().isoformat(),'evidence_id':evidence(client,other)},409)
    assert client.get(API+'/orders/'+str(row['id'])).status_code==404
    client.headers['X-Store-ID']='1';row=command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'供应商退回原车','evidence_id':evidence(client,row)});ret(client,row,'return_approve');ret(client,row,'return_dispatch')
    client.headers['X-Store-ID']='2';other=ship(client,other);other=receive(client,other,otherloc)
    with SessionLocal() as db:
        cars=list(db.scalars(select(Vehicle).order_by(Vehicle.id)));assert [(c.store_id,c.inventory_generation,c.approval_state) for c in cars]==[(1,1,'void'),(2,2,'approved')]
        assert cars[0].id==first

def test_in_transit_reject_return_never_posts_stock_or_cancels_as_wish(client):
    row,loc=approved(client,1);row=funds(client,row,10000001);account=bank(client);row=pay(client,row,account,10000001);row=ship(client,row)
    command(client,row,'cancel_remaining',{'reason':'在途不能直接取消','evidence_id':evidence(client,row)},409)
    row=command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'到货现场拒收按原车退回','evidence_id':evidence(client,row)})
    ret(client,row,'return_approve');row=ret(client,row,'return_dispatch')
    assert row['totals']['supplier_refund_due_cents']==10000001 and row['movements'][0]['quantity']==0
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Vehicle))==0

def test_original_refund_limit_and_financial_evidence_class(client):
    row,loc=approved(client,1)
    command(client,row,'request_funds',{'amount_cents':1,'reason':'错误凭据类别','evidence_id':evidence(client,row)},422)
    row=funds(client,row,10000001);account=bank(client);row=pay(client,row,account,10000001)
    row=command(client,row,'cancel_remaining',{'reason':'全部未发运取消','evidence_id':evidence(client,row)})
    v={'original_payment_id':row['payments'][0]['id'],'amount_cents':10000002,'account_id':account,'reference':'OVER','evidence_id':evidence(client,row,'receipt')}
    command(client,row,'refund',v,409);v['amount_cents']=10000001;v['account_id']=bank(client);command(client,row,'refund',v,409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(VehiclePurchasePayment))==1

def test_competing_receivers_create_one_inventory_and_original_movement(client):
    row,loc=approved(client,1);row=ship(client,row);s=row['shipments'][0];v={'shipment_id':s['id'],'vin':VIN,'location_id':loc,'evidence_id':evidence(client,row)};row=get(client,row)
    def act(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);u=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
            try:svc.command(db,u,row['id'],uuid.uuid4().hex,row['version'],'receive',v);return 200
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(act,range(2)))==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Vehicle))==1
        assert db.scalar(select(func.count()).select_from(VehiclePurchaseMovement))==1

def test_sold_or_reserved_receipt_vehicle_cannot_supplier_return(client):
    row,loc=approved(client,1);row=ship(client,row);row=receive(client,row,loc)
    assert row['totals']['payable_cents']==sum(r['amount_cents'] for r in row['totals']['due_rows'])==10000001
    with SessionLocal() as db:
        db.add(VehicleHold(vehicle_id=row['receipts'][0]['vehicle_id'],case_id=row['id'],delivered=True));db.commit()
    command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'已交付拒绝供应退回','evidence_id':evidence(client,row)},409)


def test_cancel_partly_paid_funds_releases_only_unpaid_request(client):
    row,loc=approved(client,1);row=funds(client,row,10000001);account=bank(client);row=pay(client,row,account,100)
    f=row['funds_requests'][0]
    row=command(client,row,'cancel_funds',{'funds_request_id':f['id'],'funds_version':f['version'],'reason':'变更尚未支付安排'})
    assert row['totals']['paid_net_cents']==100 and row['funds_requests'][0]['status']=='cancelled'
    command(client,row,'pay',{'funds_request_id':f['id'],'amount_cents':1,'account_id':account,'reference':'CANCELLED-FUNDS','evidence_id':evidence(client,row,'receipt')},403)
    row=funds(client,row,9999901);assert row['funds_requests'][-1]['amount_cents']==9999901


def test_conflicting_procurement_shipments_only_one_vin_claim(client):
    first,loc=approved(client,1);second,_=approved(client,1)
    proofs=[evidence(client,r) for r in (first,second)]
    def act(index):
        row=[first,second][index]
        with SessionLocal() as db:
            set_scope(db,[1],1);u=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
            try:
                svc.command(db,u,row['id'],uuid.uuid4().hex,row['version'],'ship',{'line_id':row['lines'][0]['id'],'vin':VIN,'shipped_date':today(),'expected_date':today(),'evidence_id':proofs[index]});return 200
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(act,range(2)))==[200,409]


def test_explicit_new_acquisition_after_confirmed_customer_delivery_new_generation(client,tmp_path):
    first,loc=approved(client,1);first=ship(client,first);first=receive(client,first,loc)
    with SessionLocal() as db:
        uid=db.scalar(select(User.id).where(User.username=='admin'))
        sale=Case(number='ACTUAL-SALE-DELIVERY',kind='order',flow_version=2,state='delivered',title='合成已提车单',owner_id=uid,created_by=uid,business_date=today(),completed_date=today(),vehicle_id=first['receipts'][0]['vehicle_id'],data={})
        db.add(sale);db.flush();db.add(VehicleHold(vehicle_id=sale.vehicle_id,case_id=sale.id,delivered=True));db.commit()
    second,_=approved(client,1);second=ship(client,second);second=receive(client,second,loc)
    with SessionLocal() as db:assert [c.inventory_generation for c in db.scalars(select(Vehicle).order_by(Vehicle.id))]==[1,2]
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(engine.url.database) as db:assert validate_sqlite(db)['verified_vehicle_purchases']==2


def test_foreign_file_and_location_refused_without_partial_receipt(client):
    first,loc=approved(client,1);second,_=approved(client,1);first=ship(client,first);s=first['shipments'][0]
    v={'shipment_id':s['id'],'vin':VIN,'location_id':loc,'evidence_id':evidence(client,second)}
    command(client,first,'receive',v,422)
    client.post('/api/stores',json={'code':'LOC-B','name':'另一合成库门店'});client.headers['X-Store-ID']='2';_,foreign_loc=setup(client,1)
    client.headers['X-Store-ID']='1';v['evidence_id']=evidence(client,first);v['location_id']=foreign_loc
    command(client,first,'receive',v,422)
    assert not get(client,first)['receipts']


@pytest.mark.parametrize('returned',[False,True])
def test_purchase_inventory_old_bare_writes_closed_by_default(client,monkeypatch,returned):
    from dataclasses import replace
    import app.main as module
    row,loc=approved(client,1);row=ship(client,row);row=receive(client,row,loc);car_id=row['receipts'][0]['vehicle_id']
    if returned:
        command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'原车有据退回','evidence_id':evidence(client,row)})
        ret(client,row,'return_approve');ret(client,row,'return_dispatch')
    monkeypatch.setattr(module,'settings',replace(module.settings,legacy_business_write=False))
    assert client.post('/api/records/vehicles',json={}).status_code==409
    assert client.put('/api/records/vehicles/'+str(car_id),json={'version':1,'data':{}}).status_code==409
    for action in ['submit','approve','void']:
        assert client.post(f'/api/records/vehicles/{car_id}/actions/{action}',json={'version':1,'reason':'不得绕过实物事实'}).status_code==409
    with SessionLocal() as db:assert db.scalar(select(Vehicle).where(Vehicle.id==car_id)).approval_state==('void' if returned else 'approved')
    login(client,'inventory');data=client.get('/api/records/vehicles/'+str(car_id)).json()
    assert not {'purchase_cost_cents','list_price_cents','purchase_cost','list_price'}&data.keys()


def test_supplier_and_account_master_guards_keep_open_purchase_and_original_cash(client):
    row,loc=approved(client,1)
    supplier=next(s for s in client.get('/api/masters/suppliers').json()['items'] if s['id']==row['supplier_id'])
    values={k:supplier[k] for k in ['code','name','tax_identifier','contact_name','phone','payment_terms_days','active']};values['active']=False
    denied=client.put('/api/masters/suppliers/'+str(supplier['id']),json={'request_id':uuid.uuid4().hex,'version':supplier['version'],'values':values})
    assert denied.status_code==409,denied.text
    account_id=bank(client);row=funds(client,row,10000001);row=pay(client,row,account_id,100)
    account=next(a for a in client.get('/api/flow/master/accounts').json()['items'] if a['id']==account_id)
    payload={'version':account['version'],'values':{'name':'不得覆盖已付款账户名','account_type':'bank','active':True}}
    denied=client.put('/api/flow/master/accounts/'+str(account_id),json=payload);assert denied.status_code==409,denied.text
    # Stopping an account never changes old cash. A further payment must reject its inactive status.
    account=next(a for a in client.get('/api/flow/master/accounts').json()['items'] if a['id']==account_id)
    changed=client.put('/api/flow/master/accounts/'+str(account_id),json={'version':account['version'],'values':{'name':account['name'],'account_type':'bank','active':False}})
    assert changed.status_code==200,changed.text
    command(client,row,'pay',{'funds_request_id':row['funds_requests'][0]['id'],'amount_cents':1,'account_id':account_id,'reference':'STOPPED-ACCOUNT','evidence_id':evidence(client,row,'receipt')},409)
    with SessionLocal() as db:assert sum(p.amount_cents for p in db.scalars(select(VehiclePurchasePayment)))==100


def test_commercial_current_transit_movement_chart_source_csv_and_cash_single_count(client):
    from datetime import timedelta
    row,loc=approved(client,2);row=funds(client,row,20000002);row=pay(client,row,bank(client),20000002)
    row=ship(client,row);row=ship(client,row,'LHGCM82633A123457')
    first=row['shipments'][0];row=receive(client,row,loc,first)
    command(client,row,'return_request',{'shipment_id':first['id'],'reason':'返回原供应商的第一台车','evidence_id':evidence(client,row)})
    ret(client,row,'return_approve');row=ret(client,row,'return_dispatch')
    response=client.get('/api/flow/analytics');assert response.status_code==200,response.text;report=response.json()
    t=row['totals'];metrics=report['metrics']
    assert metrics['vehicle_procurement_prepaid_cents']==t['prepaid_cents']==10000001
    assert metrics['vehicle_procurement_refund_due_cents']==t['supplier_refund_due_cents']==10000001
    assert metrics['vehicle_procurement_payable_cents']==t['payable_cents']==0
    assert metrics['cash_out_cents']==20000002 and metrics['cash_in_cents']==0
    chart=next(c for c in report['charts'] if c['id']=='vehicle_procurement_transit')
    transit=report['tables']['vehicle_procurement_transit']['rows']
    assert sum(chart['series'][0]['values'])==sum(r['amount_cents'] for r in transit)==metrics['vehicle_procurement_in_transit_cents']==10000001
    current=report['tables']['vehicle_procurement']['rows'][0]
    assert current['values'][3:]==['100000.01','0.00','200000.02','100000.01','0.00','100000.01']
    movement=report['tables']['vehicle_procurement_movements']['rows']
    with SessionLocal() as db:
        source=list(db.scalars(select(VehiclePurchaseMovement)))
        assert sorted(r['amount_cents'] for r in movement)==sorted(m.value_cents for m in source)==[-10000001,10000001]
        assert sorted(r['values'][4] for r in movement)==sorted(m.quantity for m in source)==[-1,1]
    for name in ['vehicle_procurement','vehicle_procurement_transit','vehicle_procurement_movements']:
        exported=client.get('/api/flow/analytics/export?dataset='+name);assert exported.status_code==200,exported.text
        parsed=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
        assert parsed[0]==report['tables'][name]['headers']
        # The shared exporter neutralizes string-leading '-' as a spreadsheet formula prefix.
        # Known negative decimal money retains its value after removing that CSV safety marker.
        normalized=[[v[1:] if v.startswith("'-") and v[2:].replace('.','',1).isdigit() else v for v in line] for line in parsed[1:]]
        assert normalized==[[str(v) for v in r['values']] for r in report['tables'][name]['rows']]
    previous=(today()-timedelta(days=1)).isoformat();historic=client.get('/api/flow/analytics',params={'date_from':previous,'date_to':previous}).json()
    assert historic['tables']['vehicle_procurement_movements']['rows']==[]
    assert historic['metrics']['vehicle_procurement_in_transit_cents']==10000001
    login(client,'inventory');assert client.get('/api/flow/analytics').status_code==403

def test_vehicle_purchase_migration(tmp_path):
    from alembic import command as migration
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect,text
    from app.db import Base
    cfg=Config('alembic.ini');cfg.attributes['url_override']='sqlite:///'+(tmp_path/'synthetic-vpurchase.sqlite').as_posix();migration.upgrade(cfg,'o915_vehicle_procurement')
    target=create_engine(cfg.attributes['url_override'])
    try:
        inspector=inspect(target)
        for name,table in Base.metadata.tables.items():
            if name.startswith('vehicle_purchase_'):assert {c['name'] for c in inspector.get_columns(name)}==set(table.columns.keys())
        with target.connect() as db:assert not db.execute(text('PRAGMA foreign_key_check')).first()
    finally:target.dispose()


@pytest.mark.parametrize('state',['transit','received','returned','transit_return'])
def test_backup_checks_purchase_custody_receipts_cash_and_tamper(client,tmp_path,state):
    from app.backup_integrity import validate_sqlite
    row,loc=approved(client,1);row=funds(client,row,10000001);row=pay(client,row,bank(client),10000001);row=ship(client,row)
    if state in {'received','returned'}:row=receive(client,row,loc)
    if state in {'returned','transit_return'}:
        command(client,row,'return_request',{'shipment_id':row['shipments'][0]['id'],'reason':'有据原车退回','evidence_id':evidence(client,row)})
        ret(client,row,'return_approve');ret(client,row,'return_dispatch')
    backup=tmp_path/'purchase-backup.sqlite'
    with sqlite3.connect(engine.url.database) as source,sqlite3.connect(backup) as target:source.backup(target)
    with sqlite3.connect(backup) as target:
        assert validate_sqlite(target)['verified_vehicle_purchases']==1
        if state in {'received','returned'}:target.execute('UPDATE vehicle_purchase_receipts SET value_cents=value_cents+1')
        elif state=='transit':target.execute("UPDATE vehicle_purchase_shipments SET evidence_id=999999")
        else:target.execute('UPDATE vehicle_purchase_movements SET return_id=NULL')
        with pytest.raises(ValueError):validate_sqlite(target)
