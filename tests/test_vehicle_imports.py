"""Batch imports preserve original actions, custody, privacy and atomicity."""
import csv,io,uuid,hashlib,sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db import SessionLocal,today,engine
from app.models import Vehicle,CashEntry,User
from app.flow_models import FileAsset,Task
from app.vehicle_imports_models import VehicleImportBatch as Batch,VehicleImportRow as Row,VehicleImportResult as Result,VehicleImportClaim as Claim
from app.vehicle_procurement_models import VehiclePurchaseFundsRequest as Funds,VehiclePurchaseShipment as Shipment,VehiclePurchaseReceipt as Receipt
from app import vehicle_imports_service as svc
from app.vehicle_imports_csv import HEADERS
from app.tenancy import set_scope,project_user
from tests.conftest import login
from tests.test_vehicle_procurement import approved,get,command as native

API='/api/vehicle-imports';VINS=['LTEST000000000301','LTEST000000000302']
def content(kind,rows):
    s=io.StringIO(newline='');w=csv.writer(s);w.writerow(HEADERS[kind]);w.writerows(rows);return s.getvalue().encode()
def funding(row,n=1,amount=10000001):return [[f'ROW-{i}',row['lines'][0]['id'],VINS[i],amount] for i in range(n)]
def prepare(c,row,kind,rows,reference=None,replacement=None,key=None,status=201,raw=None):
    v={'kind':kind,'request_id':key or uuid.uuid4().hex,'version':get(c,row)['version'],'source_reference':reference or uuid.uuid4().hex}
    if replacement:v['replacement_batch_id']=replacement
    r=c.post(API+f'/orders/{row["id"]}/batches',data=v,files={'file':('original.csv',raw or content(kind,rows),'text/csv')});assert r.status_code==status,r.text;return r.json()
def detail(c,b):
    r=c.get(API+'/batches/'+str(b['id']));assert r.status_code==200,r.text;return r.json()
def act(c,b,action,status=200,key=None,version=None,values=None):
    current=detail(c,b);v={'request_id':key or uuid.uuid4().hex,'version':current['version'] if version is None else version,'source_case_version':current['case_version'],'values':values or {'reason':'已核对合成原始资料',**({'confirmed':True} if action=='confirm' else {})}}
    r=c.post(API+f'/batches/{b["id"]}/actions/{action}',json=v);assert r.status_code==status,r.text;return r.json()
def done(c,b,actor='admin'):
    b=act(c,b,'trial');login(c,'manager');b=act(c,b,'review');login(c,actor);return act(c,b,'confirm')
def manifest(c,row,n=1):return done(c,prepare(c,row,'funds',funding(row,n)))


def test_funds_shipping_receipt_are_separate_atomic_facts_and_trial_rolls_back(client):
    row,loc=approved(client,2);b=prepare(client,row,'funds',funding(row,2));sha=hashlib.sha256(content('funds',funding(row,2))).hexdigest();assert b['source_digest']==sha
    b=act(client,b,'trial')
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Funds))==0 and db.scalar(select(func.count()).select_from(Result))==0
    login(client,'manager');b=act(client,b,'review');login(client,'admin');b=act(client,b,'confirm')
    assert b['amount_cents']==20000002 and len(get(client,row)['funds_requests'])==2 and get(client,row)['payments']==[]
    login(client,'inventory');rows=[[f'S-{i}',r['id'],r['values']['vin'],today().isoformat(),today().isoformat()] for i,r in enumerate(b['rows'])]
    ship=prepare(client,row,'ship',rows);ship=act(client,ship,'trial')
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Shipment))==0 and db.scalar(select(func.count()).select_from(Vehicle))==0
    login(client,'manager');ship=act(client,ship,'review');login(client,'inventory');ship=act(client,ship,'confirm')
    assert len(get(client,row)['shipments'])==2 and not get(client,row)['receipts']
    receive=prepare(client,row,'receive',[[f'R-{i}',r['id'],r['values']['vin'],today().isoformat(),loc] for i,r in enumerate(b['rows'])]);receive=done(client,receive,'inventory')
    assert receive['status']=='confirmed' and len(get(client,row)['receipts'])==2
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Vehicle))==2 and db.scalar(select(func.count()).select_from(CashEntry))==0
        assert sum(r.value_cents for r in db.scalars(select(Receipt)))==20000002


def test_row_errors_and_invalid_csv_never_partially_post(client):
    row,loc=approved(client);bad=funding(row,2);bad[1][3]='1.01';b=prepare(client,row,'funds',bad)
    assert b['status']=='invalid' and b['errors'][0]['row_number']==3
    act(client,b,'trial',409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Funds))==0 and db.scalar(select(func.count()).select_from(Claim))==0
    prepare(client,row,'funds',[],raw=b'wrong,headers\n1,2\n',status=422)
    prepare(client,row,'funds',[],raw=b'\xff\xfe invalid',status=422)
    prepare(client,row,'funds',[],raw=b'a'*(128*1024+1),status=413)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Batch))==1


def test_self_review_permissions_and_financial_source_privacy(client):
    row,loc=approved(client);b=act(client,prepare(client,row,'funds',funding(row)),'trial');act(client,b,'review',403)
    login(client,'manager');b=act(client,b,'review');act(client,b,'confirm',403)
    login(client,'admin');b=act(client,b,'confirm');login(client,'inventory')
    assert client.get(API+'/batches/'+str(b['id'])).status_code==403
    assert client.get('/api/flow/files/'+str(b['file']['id'])).status_code==403
    rows=client.get(API+f'/orders/{row["id"]}/manifest').json()['items'];assert set(rows[0])=={'id','batch_id','line_id','vin','source_row'}
    prepare(client,row,'funds',funding(row),status=403)
    login(client,'sales');assert client.get(API+f'/orders/{row["id"]}/manifest').status_code==403
    login(client,'admin');client.headers['X-Store-ID']='all';assert client.get(API+f'/orders/{row["id"]}/batches').status_code==409


def test_idempotency_cancelled_history_requires_explicit_replacement(client):
    row,loc=approved(client);k=uuid.uuid4().hex;reference='SUP-001';rows=funding(row)
    b=prepare(client,row,'funds',rows,reference,key=k);again=prepare(client,row,'funds',rows,reference,key=k);assert again['id']==b['id']
    prepare(client,row,'funds',funding(row,amount=1),reference,key=k,status=409)
    duplicate=prepare(client,row,'funds',rows,reference);assert duplicate['status']=='invalid'
    act(client,duplicate,'cancel');b=act(client,b,'cancel')
    replacement=prepare(client,row,'funds',rows,reference,replacement=duplicate['id']);assert replacement['status']=='prepared'
    replacement=done(client,replacement);act(client,replacement,'cancel',409)
    duplicate=prepare(client,row,'funds',rows,reference,replacement=b['id']);assert duplicate['status']=='invalid'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Funds))==1


def test_stale_case_and_batch_versions_require_recheck(client):
    from tests.test_workflow import evidence
    row,loc=approved(client);b=prepare(client,row,'funds',funding(row));old=b['version'];b=act(client,b,'trial')
    login(client,'manager');act(client,b,'review',409,version=old);b=act(client,b,'review')
    login(client,'admin');native(client,row,'request_funds',{'amount_cents':1,'reason':'期间另行请款','evidence_id':evidence(client,row,'receipt')});act(client,b,'confirm',409)
    act(client,b,'cancel')


def test_late_row_native_guard_rolls_back_all_prior_rows_and_source_objects(client):
    row,loc=approved(client,2);m=manifest(client,row,2);login(client,'inventory')
    rows=[[f'S-{i}',r['id'],r['values']['vin'],today().isoformat(),today().isoformat()] for i,r in enumerate(m['rows'])]
    b=prepare(client,row,'ship',rows)
    # Existing VIN in another store is checked by the native global custody guard; nothing from the other store is exposed.
    login(client,'admin');client.post('/api/stores',json={'code':'VIB','name':'合成乙店'});client.headers['X-Store-ID']='2'
    other,otherloc=approved(client,1)
    from tests.test_vehicle_procurement import ship
    ship(client,other,VINS[1]);client.headers['X-Store-ID']='1';login(client,'inventory');act(client,b,'trial',409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Shipment).where(Shipment.store_id==1))==0
        assert db.scalar(select(func.count()).select_from(Result).join(Row,Row.id==Result.row_id).where(Row.batch_id==b['id']))==0


def test_date_vin_location_and_manifest_boundaries(client):
    from datetime import timedelta
    row,loc=approved(client,1);m=manifest(client,row);r=m['rows'][0];login(client,'inventory')
    future=(today()+timedelta(days=1)).isoformat()
    b=prepare(client,row,'ship',[['S1',r['id'],VINS[0],future,future]]);assert b['status']=='invalid'
    b=act(client,b,'cancel')
    ship=prepare(client,row,'ship',[['S1',r['id'],VINS[0],today().isoformat(),today().isoformat()]],replacement=b['id']);ship=done(client,ship,'inventory')
    invalid=prepare(client,row,'receive',[['R1',r['id'],VINS[0],future,loc]]);assert invalid['status']=='invalid'
    invalid=act(client,invalid,'cancel')
    receive=prepare(client,row,'receive',[['R1',r['id'],VINS[0],today().isoformat(),loc]],replacement=invalid['id']);receive=done(client,receive,'inventory')
    duplicate=prepare(client,row,'receive',[['R2',r['id'],VINS[0],today().isoformat(),loc]]);assert duplicate['status']=='invalid'


def test_concurrent_confirmation_only_posts_once(client):
    row,loc=approved(client,1);b=act(client,prepare(client,row,'funds',funding(row)),'trial');login(client,'manager');b=act(client,b,'review')
    def worker(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
            try:svc.command(db,user,uuid.uuid4().hex,b['id'],b['version'],b['case_version'],'confirm',{'reason':'并发合成确认','confirmed':True});return 200
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(worker,range(2)))==[200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Funds))==1


def test_cross_store_and_immutable_source(client):
    row,loc=approved(client);b=prepare(client,row,'funds',funding(row));client.post('/api/stores',json={'code':'OTHER','name':'合成其他店'});client.headers['X-Store-ID']='2'
    assert client.get(API+'/batches/'+str(b['id'])).status_code==404
    assert client.get(API+f'/orders/{row["id"]}/manifest').status_code==404
    with SessionLocal() as db:
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
        with svc.access(db,user):
            target=db.scalar(select(Row).where(Row.batch_id==b['id']));target.values={'vin':'TAMPER'}
            with pytest.raises(HTTPException):db.flush()
            db.rollback()


def test_confirm_after_successful_trial_still_rolls_back_all_rows_on_new_vin_conflict(client):
    row,loc=approved(client,2);m=manifest(client,row,2);login(client,'inventory')
    rows=[[f'S-{i}',r['id'],r['values']['vin'],today().isoformat(),today().isoformat()] for i,r in enumerate(m['rows'])]
    b=act(client,prepare(client,row,'ship',rows),'trial');login(client,'manager');b=act(client,b,'review')
    login(client,'admin');client.post('/api/stores',json={'code':'RACE','name':'合成竞争店'});client.headers['X-Store-ID']='2'
    other,otherloc=approved(client,1)
    from tests.test_vehicle_procurement import ship
    ship(client,other,VINS[1]);client.headers['X-Store-ID']='1';login(client,'inventory');act(client,b,'confirm',409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Shipment).where(Shipment.store_id==1))==0
        assert db.scalar(select(Batch.status).where(Batch.id==b['id']))=='reviewed'


def test_quarantined_csv_cannot_trial_until_scanned(client,monkeypatch):
    from tests.test_file_security import mode,scan
    row,loc=approved(client,1);mode(monkeypatch,'quarantine');b=prepare(client,row,'funds',funding(row))
    assert not b['file']['security']['can_use'];act(client,b,'trial',409)
    mode(monkeypatch,'structure_only');scan(client,b['file']['id']);b=act(client,b,'trial');assert b['status']=='trial_passed'


def test_nonempty_backup_links_source_and_rejects_tampered_facts(client,tmp_path):
    from app.vehicle_imports_integrity import validate_vehicle_imports
    row,loc=approved(client,1);b=manifest(client,row)
    login(client,'inventory');r=b['rows'][0]
    ship=done(client,prepare(client,row,'ship',[['S1',r['id'],VINS[0],today().isoformat(),today().isoformat()]]),'inventory')
    receipt=done(client,prepare(client,row,'receive',[['R1',r['id'],VINS[0],today().isoformat(),loc]]),'inventory')
    raw=engine.raw_connection()
    try:
        with sqlite3.connect(tmp_path/'restored.sqlite') as restored:
            raw.driver_connection.backup(restored)
            assert validate_vehicle_imports(restored)=={'verified_vehicle_import_batches':3,'verified_vehicle_import_results':3}
            restored.execute('UPDATE vehicle_import_rows SET vin=? WHERE id=?',('LTEST000000000999',r['id']))
            with pytest.raises(ValueError):validate_vehicle_imports(restored)
    finally:raw.close()


def test_frozen_vehicle_import_migration_matches_model(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect
    from app.db import Base
    config=Config('alembic.ini');config.attributes['url_override']='sqlite:///'+(tmp_path/'fresh.sqlite').as_posix();command.upgrade(config,'c329_vehicle_imports')
    independent=create_engine(config.attributes['url_override'])
    try:
        schema=inspect(independent)
        for table in ('vehicle_import_batches','vehicle_import_rows','vehicle_import_claims','vehicle_import_results','vehicle_import_requests'):
            assert {r['name'] for r in schema.get_columns(table)}==set(Base.metadata.tables[table].columns.keys())
            assert schema.get_foreign_keys(table)
    finally:independent.dispose()


def test_actual_manager_prepares_and_separate_admin_reviews_with_handoff(client):
    row,loc=approved(client,1);login(client,'manager');b=act(client,prepare(client,row,'funds',funding(row)),'trial')
    login(client,'admin');b=act(client,b,'review');login(client,'manager');b=act(client,b,'confirm');assert b['status']=='confirmed'
    login(client,'inventory');generic=client.get('/api/flow/cases/'+str(row['id'])).json()
    assert all('cost_review_note' not in e['detail'] for e in generic['events'])


def test_cancelled_unposted_handoff_preserves_source_uploader_and_new_actor(client):
    row,loc=approved(client,1);b=prepare(client,row,'funds',funding(row),reference='ORIGINAL-SOURCE');b=act(client,b,'cancel')
    login(client,'manager');new=prepare(client,row,'funds',funding(row),reference='ORIGINAL-SOURCE',replacement=b['id'])
    assert new['file']['id']==b['file']['id'] and new['prepared_by']!=b['prepared_by']
    new=act(client,new,'trial');login(client,'admin');new=act(client,new,'review');login(client,'manager');new=act(client,new,'confirm')
    with SessionLocal() as db:
        assert db.scalar(select(FileAsset.created_by).where(FileAsset.id==b['file']['id']))==b['prepared_by']
        assert db.scalar(select(Funds.requested_by))==new['prepared_by']


def test_replacement_chain_can_correct_a_vin_back_without_permanently_locking_source(client):
    row,loc=approved(client,1);a=act(client,prepare(client,row,'funds',funding(row),reference='CHAIN'),'cancel')
    changed=funding(row);changed[0][2]=VINS[1]
    b=prepare(client,row,'funds',changed,reference='CHAIN',replacement=a['id']);assert b['status']=='prepared';b=act(client,b,'cancel')
    c=prepare(client,row,'funds',funding(row),reference='CHAIN',replacement=b['id']);assert c['status']=='prepared'
    assert done(client,c)['status']=='confirmed'
