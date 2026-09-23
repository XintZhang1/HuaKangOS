"""Synthetic new-store opening, independent witnesses, real source facts and rollback."""
import csv,io,json,sqlite3,uuid
from datetime import timedelta,datetime,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today,engine
from app.models import Vehicle,CashEntry,User,AppMetadata
from app.flow_models import Customer,Account,Item,Case,StockMove,FlowEvent
from app.master_models import OpeningBatch,OpeningStockEntry
from app.opening_import_models import OpeningImport,OpeningAccountEntry,OpeningVehicleEntry,OpeningAttestation
from app.opening_import_service import Source,inventory_observation,finance_observation
from app.opening_import_backup_integrity import validate_opening_import
from app.vehicle_transfer_models import VehicleCustody
from app.vehicle_operations_models import VehiclePosition,VehiclePositionEntry
from app.tenancy import set_scope
from tests.conftest import login
from tests.test_master_data import create,SAMPLES
from tests.test_workflow import evidence
from tests.test_multistore import second_store,switch


def source_data(c):
    create(c,'vehicle_models',{'code':'OPEN-MODEL','name':'合成期初纯电车',**SAMPLES['vehicle_models']})
    wh=create(c,'warehouses',{'code':'OPEN-W','name':'合成整车仓','warehouse_type':'vehicles'})
    loc=create(c,'locations',{'code':'OPEN-LOCATION','name':'合成一号库位','warehouse_id':wh['id']})
    source=c.get('/api/opening-import/example').json()['source']
    source['customers'][0]['owner_username']='sales'
    return source,loc


def preflight(c,source,key=None):
    r=c.post('/api/opening-import/preflight',json={'request_id':key or uuid.uuid4().hex,'source_text':source if isinstance(source,str) else json.dumps(source,ensure_ascii=False)})
    assert r.status_code==200,r.text
    return r.json()


def act(c,row,name,values=None,status=200,key=None):
    values=values or {};values.setdefault('reason','合成验收核对本人事项')
    response=c.post(f'/api/opening-import/batches/{row["case_id"]}/actions/{name}',json={'request_id':key or uuid.uuid4().hex,'version':row['version'],'source_digest':row['source_digest'],'values':values})
    assert response.status_code==status,response.text
    return response.json()


def proof(c,row,category='evidence'):return evidence(c,{'id':row['case_id']},category)


def reviewed(c,source=None):
    if source is None:source,_=source_data(c)
    row=preflight(c,source)['batch']
    row=act(c,row,'trial',{'evidence_id':proof(c,row)})
    login(c,'manager');row=act(c,row,'approve',{'evidence_id':proof(c,row)})
    login(c,'inventory');row=act(c,row,'verify_inventory',{'evidence_id':proof(c,row),'observed':inventory_observation(Source.model_validate(source))})
    login(c,'finance');row=act(c,row,'verify_finance',{'evidence_id':proof(c,row,'receipt'),'observed':finance_observation(Source.model_validate(source))})
    login(c,'manager');return row,source


def confirm(c,row,**kwargs):return act(c,row,'confirm',{'confirmed':True,'expected_totals':row['totals']},**kwargs)


def test_opening_trial_rolls_back_every_fact_and_confirm_conserves(client):
    source,loc=source_data(client);key=uuid.uuid4().hex
    result=preflight(client,source,key);assert preflight(client,source,key)==result;row=result['batch']
    row=act(client,row,'trial',{'evidence_id':proof(client,row)})
    with SessionLocal() as db:
        for model in (Customer,Account,Item,Vehicle,OpeningStockEntry,OpeningAccountEntry,OpeningVehicleEntry,VehicleCustody,VehiclePosition,VehiclePositionEntry):assert db.scalar(select(func.count()).select_from(model))==0,model
    login(client,'manager');row=act(client,row,'approve',{'evidence_id':proof(client,row)})
    confirm(client,row,status=403)
    login(client,'inventory');row=act(client,row,'verify_inventory',{'evidence_id':proof(client,row),'observed':inventory_observation(Source.model_validate(source))})
    assert not row['accounts'] and not row['customers'] and 'vehicle_value_cents' not in row['totals'] and 'cost_cents' not in row['vehicles'][0]
    login(client,'finance');row=act(client,row,'verify_finance',{'evidence_id':proof(client,row,'receipt'),'observed':finance_observation(Source.model_validate(source))})
    login(client,'manager');key=uuid.uuid4().hex;done=confirm(client,row,key=key);assert confirm(client,row,key=key)==done
    assert done['status']=='confirmed'
    with SessionLocal() as db:
        from app.transfer_service import authority
        set_scope(db,[1],1)
        with authority(db,db.scalar(select(User).where(User.username=='manager'))):custody=db.scalar(select(VehicleCustody))
        car=db.scalar(select(Vehicle));entry=db.scalar(select(OpeningVehicleEntry));item=db.scalar(select(Item));position=db.scalar(select(VehiclePosition))
        assert car.inventory_generation==1 and car.approval_state=='approved' and car.purchase_cost_cents==10000001
        assert (custody.current_vehicle_id,custody.generation,entry.vehicle_id,entry.value_cents)==(car.id,1,car.id,10000001)
        assert (position.location_id,position.status)==(loc['id'],'stored')
        assert (item.quantity_milli,item.inventory_value_cents)==(2500,10001)
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
        assert db.scalar(select(OpeningAccountEntry.amount_cents))==500001
        assert db.scalar(select(OpeningBatch.confirmed_store_key))==1
    assert preflight(client,source)['errors'][0]['section'] in {'vehicles','target'}


def test_opening_errors_are_row_specific_and_no_partial_preview(client):
    source,_=source_data(client);source['accounts'][0]['opening_balance_cents']=1.25
    errors=preflight(client,source)['errors'];assert errors[0]['section']=='accounts' and errors[0]['row']==1
    source['accounts'][0]['opening_balance_cents']=50;source['vehicles'][0]['vin']='BAD';source['customers'][0]['owner_username']='auditor'
    assert not preflight(client,source)['valid']
    duplicate='{"schema_version":2,"schema_version":2}'
    assert preflight(client,duplicate)['errors'][0]['section']=='source'
    with SessionLocal() as db:assert not db.scalar(select(OpeningImport.id)) and not db.scalar(select(Case.id))


def test_opening_store_role_source_and_legacy_bypass_denied(client):
    source,_=source_data(client);row=preflight(client,source)['batch'];two=second_store(client);switch(client,two)
    assert client.get(f'/api/opening-import/batches/{row["case_id"]}').status_code==404
    switch(client,'all');assert client.get('/api/opening-import/batches').status_code==409
    switch(client,1);login(client,'inventory')
    assert client.get(f'/api/opening-import/batches/{row["case_id"]}/source').status_code==403
    assert client.get('/api/opening-import/account-balances').status_code==403
    assert client.post('/api/opening-import/preflight',json={'request_id':uuid.uuid4().hex,'source_text':json.dumps(source)}).status_code==403
    login(client,'sales');assert not client.get('/api/opening-import/catalog').json()['can_read']
    assert client.get(f'/api/opening-import/batches/{row["case_id"]}').status_code==403
    login(client);r=client.post(f'/api/masters/opening/{row["batch_id"]}/trial',json={'request_id':uuid.uuid4().hex,'version':1,'digest':row['source_digest']})
    assert r.status_code==409,r.text


def test_opening_separation_conflicting_observation_stale_and_cancel(client):
    source,_=source_data(client);row=preflight(client,source)['batch'];old=row.copy();row=act(client,row,'trial',{'evidence_id':proof(client,row)})
    act(client,old,'trial',{'evidence_id':proof(client,row)},status=409)
    act(client,row,'approve',{'evidence_id':proof(client,row)},status=409)
    login(client,'manager');row=act(client,row,'approve',{'evidence_id':proof(client,row)})
    login(client,'inventory');observed=inventory_observation(Source.model_validate(source));observed['items'][0]['quantity_milli']-=1
    act(client,row,'verify_inventory',{'evidence_id':proof(client,row),'observed':observed},status=409)
    login(client,'finance');observed=finance_observation(Source.model_validate(source));observed['totals']['vehicle_count']=True
    act(client,row,'verify_finance',{'evidence_id':proof(client,row,'receipt'),'observed':observed},status=409)
    login(client,'manager');row=act(client,row,'cancel');assert row['status']=='cancelled'
    with SessionLocal() as db:assert not db.scalar(select(OpeningAccountEntry.id)) and not db.scalar(select(Vehicle.id))


def test_opening_account_current_and_csv_source_protection(client):
    row,source=reviewed(client);confirm(client,row)
    with SessionLocal() as db:
        account=db.scalar(select(Account));uid=db.scalar(select(User.id).where(User.username=='finance'))
        db.add(CashEntry(doc_no='SYNTH-CASH-IN',business_date=today(),created_by=uid,approval_state='approved',direction='in',category='synthetic_receipt',amount_cents=1099,account=account.name,payment_method='bank',voucher_no='SYNTH-IN'))
        db.add(CashEntry(doc_no='SYNTH-CASH-OUT',business_date=today(),created_by=uid,approval_state='approved',direction='out',category='synthetic_payment',amount_cents=100,account=account.name,payment_method='bank',voucher_no='SYNTH-OUT'));db.commit()
        aid=account.id;name=account.name
    balances=client.get('/api/opening-import/account-balances').json()['items'];assert balances[0]['balance_cents']==501000
    exported=list(csv.reader(io.StringIO(client.get('/api/opening-import/account-balances/export').text.lstrip('\ufeff'))));assert exported[1][2:6]==['500001','1099','100','501000']
    with SessionLocal() as db:
        set_scope(db,[1],1);db.add(CashEntry(doc_no='SYNTH-BACKDATE',business_date=today()-timedelta(days=1),created_by=uid,approval_state='approved',direction='in',category='synthetic',amount_cents=1,account=name,payment_method='bank'))
        with pytest.raises(HTTPException):db.flush()
        db.rollback();account=db.scalar(select(Account).where(Account.id==aid));account.name='不能改名'
        with pytest.raises(HTTPException):db.flush()


def test_opening_nonempty_backup_and_tamper_refused(client):
    row,_=reviewed(client);confirm(client,row)
    with engine.connect() as conn:
        target=sqlite3.connect(':memory:');conn.connection.driver_connection.backup(target)
    assert validate_opening_import(target)['verified_opening_imports']==1
    from app.backup_integrity import validate_sqlite
    validate_sqlite(target)
    target.execute('UPDATE opening_account_entries SET amount_cents=amount_cents+1');target.commit()
    with pytest.raises(ValueError,match='账户期初余额'):validate_opening_import(target)
    target.close()


def test_opening_competing_batches_cannot_double_post(client):
    source,_=source_data(client);one,_=reviewed(client,source);login(client);two,_=reviewed(client,source)
    confirm(client,one);confirm(client,two,status=409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(OpeningVehicleEntry))==1


def test_opening_existing_or_demo_store_rejected(client):
    source,_=source_data(client)
    with SessionLocal() as db:db.add(AppMetadata(key='demo',value={'enabled':True}));db.commit()
    assert preflight(client,source)['errors'][-1]['field']=='empty_store'
    with SessionLocal() as db:db.delete(db.scalar(select(AppMetadata).where(AppMetadata.key=='demo')));db.add(Account(name='已有账户'));db.commit()
    assert preflight(client,source)['errors'][-1]['field']=='empty_store'


def test_opening_accounts_exclude_superseded_collection_and_correction_entries(client):
    row,_=reviewed(client);confirm(client,row)
    login(client)
    from tests import test_business_finance as finance
    from tests import test_retail as retail
    source,_,customer=finance.ready_retail(client)
    with SessionLocal() as db:account=db.scalar(select(OpeningAccountEntry.account_id))
    source=retail.pay(client,source,700,account)
    with SessionLocal() as db:original=db.scalar(select(CashEntry.id))
    correction=finance.create(client,customer,'correction',{'original_cash_id':original,'amount_cents':500,'account_id':account,'reference':'SYNTH-CORRECTION',
        'allocations':[{'source_case_id':source['id'],'amount_cents':500}]})
    correction=finance.approve(client,correction);finance.command(client,correction,'execute',finance.proof(client,correction,source_versions=finance.versions(client,source)))
    actual=client.get('/api/opening-import/account-balances').json()['items'][0]
    assert (actual['in_cents'],actual['out_cents'],actual['balance_cents'])==(500,0,500501)
    csv_rows=list(csv.reader(io.StringIO(client.get('/api/opening-import/account-balances/export').text.lstrip('\ufeff'))))
    assert csv_rows[1][3:6]==['500','0','500501']


@pytest.mark.parametrize('hours_before_local_midnight,expected',[(7,200),(9,409)])
def test_opening_attestation_expiry_uses_configured_local_day(client,hours_before_local_midnight,expected):
    row,_=reviewed(client)
    # Shanghai 00:00 corresponds to the preceding UTC day at 16:00. UTC 17:00
    # remains today's 01:00; UTC 15:00 belongs to the previous local day.
    stamp=datetime.combine(today(),time.min)-timedelta(hours=hours_before_local_midnight)
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE opening_attestations SET occurred_at=? WHERE kind IN ('inventory','finance')",(stamp.isoformat(' '),))
    confirm(client,row,status=expected)


def test_opening_concurrent_confirmation_has_one_atomic_winner(client):
    from threading import Barrier
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from app.main import app
    source,_=source_data(client);one,_=reviewed(client,source);login(client);two,_=reviewed(client,source);barrier=Barrier(2)
    def send(pair):
        c,row=pair;barrier.wait(timeout=20)
        return c.post(f'/api/opening-import/batches/{row["case_id"]}/actions/confirm',json={'request_id':uuid.uuid4().hex,'version':row['version'],'source_digest':row['source_digest'],
            'values':{'reason':'本岗并发确认合成资料','expected_totals':row['totals'],'confirmed':True}}).status_code
    with ExitStack() as stack:
        clients=[stack.enter_context(TestClient(app)) for _ in range(2)]
        for c in clients:login(c,'manager')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,zip(clients,[one,two])))
    assert sorted(results)==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OpeningAccountEntry))==1
        assert db.scalar(select(func.count()).select_from(OpeningVehicleEntry))==1
        assert db.scalar(select(func.count()).select_from(OpeningStockEntry))==1


def test_opening_changed_typed_master_and_foreign_historical_vin_rejected(client):
    from app.master_models import VehicleModel
    source,_=source_data(client);row=preflight(client,source)['batch']
    with SessionLocal() as db:
        model=db.scalar(select(VehicleModel));model.name='已改车型名称';db.commit()
    act(client,row,'trial',{'evidence_id':proof(client,row)},status=409)
    act(client,row,'cancel')
    two=second_store(client)
    with SessionLocal() as db:
        uid=db.scalar(select(User.id).where(User.username=='admin'))
        db.add(Vehicle(store_id=two,doc_no='SYNTH-HISTORIC-VIN',business_date=today(),created_by=uid,approval_state='void',vin=source['vehicles'][0]['vin'],brand='合成历史品牌',model='合成历史车辆',purchase_cost_cents=1,list_price_cents=1));db.commit()
    result=preflight(client,source)
    assert not result['valid'] and result['errors'][0]['section']=='vehicles'
    assert '合成历史' not in json.dumps(result,ensure_ascii=False)


def test_opening_admin_cannot_replace_separate_inventory_or_finance_witness(client):
    login(client,'manager');source,_=source_data(client);row=preflight(client,source)['batch'];prepared_file=proof(client,row)
    row=act(client,row,'trial',{'evidence_id':prepared_file})
    login(client);act(client,row,'approve',{'evidence_id':prepared_file},status=409)
    row=act(client,row,'approve',{'evidence_id':proof(client,row)})
    act(client,row,'verify_inventory',{'evidence_id':proof(client,row),'observed':inventory_observation(Source.model_validate(source))},status=409)
    act(client,row,'verify_finance',{'evidence_id':proof(client,row,'receipt'),'observed':finance_observation(Source.model_validate(source))},status=409)


def test_frozen_opening_migration_on_fresh_database(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect
    from app.db import Base
    config=Config('alembic.ini');config.attributes['url_override']='sqlite:///'+(tmp_path/'fresh-opening.sqlite').as_posix()
    command.upgrade(config,'z026_opening_import');independent=create_engine(config.attributes['url_override'])
    try:
        schema=inspect(independent)
        for table in ('opening_imports','opening_attestations','opening_account_entries','opening_vehicle_entries'):
            assert {c['name'] for c in schema.get_columns(table)}==set(Base.metadata.tables[table].columns.keys())
            assert schema.get_foreign_keys(table) and schema.get_check_constraints(table)
    finally:independent.dispose()
