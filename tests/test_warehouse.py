"""Synthetic physical bins, original costs, approval, count bridges and competing issues."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import User
from app.flow_models import Item,StockMove,Case
from app.warehouse_models import WarehouseBalance,WarehouseEntry,WarehouseHold,WarehouseEnrollment
from app import warehouse_service as svc
from app.tenancy import set_scope,project_user
from tests.conftest import login
from tests.test_workflow import master,evidence,create as flow_create,action as flow_action
from tests.test_vehicle_procurement import typed

API='/api/warehouse'
def create(c,operation,item,qty,src=None,dest=None,original=None,locations=None,status=201,**extra):
    payload={'request_id':uuid.uuid4().hex,'operation':operation,'item_id':item,'quantity_milli':qty,'source_location_id':src,
        'destination_location_id':dest,'original_move_id':original,'reason':'合成作业真实凭据','recipient':'虚构领取班组','due_date':today().isoformat(),'locations':locations or [],**extra}
    r=c.post(API+'/cases',json=payload);assert r.status_code==status,r.text;return r.json()
def get(c,row):
    r=c.get(API+'/cases/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def command(c,row,action,v=None,status=200,version=None,key=None):
    current=get(c,row);r=c.post(API+f'/cases/{row["id"]}/commands/{action}',json={'request_id':key or uuid.uuid4().hex,'version':current['version'] if version is None else version,'values':v or {}})
    assert r.status_code==status,r.text;return r.json()
def approve(c,row,value=None,**kw):
    v={'evidence_id':evidence(c,row,'receipt' if row['operation']=='other_in' else 'evidence')}
    if value is not None:v['value_cents']=value
    return command(c,row,'approve',v,**kw)
def execute(c,row,**kw):return command(c,row,'execute',{'evidence_id':evidence(c,row)},**kw)
def stock(c,item):
    r=c.get(API+f'/items/{item}/stock');assert r.status_code==200,r.text;return r.json()
def setup(c,qty=10000,value=1001):
    item=master(c,'items',{'sku':'S'+uuid.uuid4().hex[:8],'name':'合成耗材礼品','unit':'件','reorder':'0','active':True})['id']
    wh=typed(c,'warehouses',{'code':'W'+uuid.uuid4().hex[:8],'name':'合成物资仓','warehouse_type':'materials'})
    a=typed(c,'locations',{'code':'A'+uuid.uuid4().hex[:6],'name':'甲库位','warehouse_id':wh['id']})['id']
    b=typed(c,'locations',{'code':'B'+uuid.uuid4().hex[:6],'name':'乙库位','warehouse_id':wh['id']})['id']
    activation=create(c,'activate',item,0,locations=[{'location_id':a,'quantity_milli':0}]);approve(c,activation)
    if qty:
        incoming=create(c,'other_in',item,qty,dest=a);approve(c,incoming,value);execute(c,incoming)
    return item,a,b
def conserved(c,item):
    s=stock(c,item);assert sum(b['quantity_milli'] for b in s['balances'])==s['quantity_milli']
    assert sum(b['value_cents'] for b in s['balances'])==s['value_cents']
    for b in s['balances']:
        es=[e for e in s['entries'] if e['balance_id']==b['id']]
        assert sum(e['quantity_milli'] for e in es)==b['quantity_milli'];assert sum(e['value_cents'] for e in es)==b['value_cents']
    with SessionLocal() as db:
        assert sum(m.quantity_milli for m in db.scalars(select(StockMove).where(StockMove.item_id==item)))==s['quantity_milli']
        assert sum(m.value_cents for m in db.scalars(select(StockMove).where(StockMove.item_id==item)))==s['value_cents']
    return s

def test_zero_activation_other_receipt_issue_original_partial_return_exact_fen(client):
    i,a,b=setup(client);out=create(client,'consumable',i,3000,src=a);approve(client,out);out=execute(client,out)
    original=out['stock_moves'][0];assert original['value_cents']==-300
    for qty in [1000,2000]:
        ret=create(client,'consumable_return',i,qty,dest=b,original=original['id']);approve(client,ret);execute(client,ret)
    s=conserved(client,i);assert (s['quantity_milli'],s['value_cents'])==(10000,1001)
    assert {x['location_id']:x['quantity_milli'] for x in s['balances']}=={a:7000,b:3000}
    create(client,'consumable_return',i,1,dest=b,original=original['id'],status=409)

def test_original_other_in_return_is_physical_not_cash_and_gift_has_original_return(client):
    i,a,b=setup(client,3000,1000)
    with SessionLocal() as db:original=db.scalar(select(StockMove.id).where(StockMove.item_id==i,StockMove.purpose=='wh_other_in'))
    ret=create(client,'other_in_return',i,1000,src=a,original=original);approve(client,ret);execute(client,ret)
    gift=create(client,'gift',i,1000,src=a);approve(client,gift);gift=execute(client,gift)
    back=create(client,'gift_return',i,1000,dest=b,original=gift['stock_moves'][0]['id']);approve(client,back);execute(client,back)
    s=conserved(client,i);assert (s['quantity_milli'],s['value_cents'])==(2000,667)
    with SessionLocal() as db:
        from app.models import CashEntry
        assert db.scalar(select(func.count()).select_from(CashEntry))==0

def test_local_move_partial_accept_reject_and_return_keeps_store_total(client):
    i,a,b=setup(client);move=create(client,'local_move',i,7000,src=a,dest=b);approve(client,move)
    assert stock(client,i)['available_milli']==3000
    move=command(client,move,'dispatch',{'evidence_id':evidence(client,move)});s=conserved(client,i)
    assert s['quantity_milli']==10000 and s['available_milli']==3000 and move['transit_quantity_milli']==7000
    move=command(client,move,'accept',{'quantity_milli':2000,'evidence_id':evidence(client,move)})
    command(client,move,'cancel',{'reason':'不能取消真实在途'},409)
    move=command(client,move,'reject_transit',{'reason':'接收库位包装异常','evidence_id':evidence(client,move)})
    move=command(client,move,'return_transit',{'quantity_milli':5000,'evidence_id':evidence(client,move)})
    assert move['state']=='completed';s=conserved(client,i);assert s['value_cents']==1001
    assert {x['location_id']:x['quantity_milli'] for x in s['balances'] if x['location_id']}=={a:8000,b:2000}

def test_approval_reserves_cancel_releases_and_two_approvals_cannot_oversell(client):
    i,a,b=setup(client);one=create(client,'disposal',i,7000,src=a);two=create(client,'gift',i,4000,src=a)
    approve(client,one);approve(client,two,status=409);command(client,one,'cancel',{'reason':'实际作业尚未开始'})
    approve(client,two);execute(client,two);assert conserved(client,i)['quantity_milli']==6000

def test_count_short_fence_then_period_movement_bridge_adds_delta_not_overwrite(client):
    i,a,b=setup(client);count=create(client,'count',i,0,src=a);count=approve(client,count)
    out=create(client,'disposal',i,1000,src=a);approve(client,out,status=409)
    incoming=create(client,'other_in',i,2000,dest=a);approve(client,incoming,400);execute(client,incoming,status=409)
    count=command(client,count,'capture',{'counted_quantity_milli':9000,'evidence_id':evidence(client,count)})
    execute(client,incoming);approve(client,out);execute(client,out)
    before=get(client,count)['count'];assert before['baseline_quantity_milli']==10000 and before['movement_bridge_milli']==1000
    count=command(client,count,'post_count',{'evidence_id':evidence(client,count)})
    assert count['count']['current_book_milli']==count['count']['projected_milli']==10000
    conserved(client,i)

def test_count_shortage_does_not_release_retail_promises(client):
    i,a,b=setup(client)
    with SessionLocal() as db:
        from app.retail_models import RetailReservation
        admin=db.scalar(select(User).where(User.role=='admin'));case=Case(number='R'+uuid.uuid4().hex,kind='retail',flow_version=2,state='pending',title='合成预占',created_by=admin.id,owner_id=admin.id,business_date=today(),data={})
        db.add(case);db.flush();db.add(RetailReservation(case_id=case.id,item_id=i,quantity_milli=9500,reason='reserve',actor_id=admin.id));db.commit();rid=case.id
    count=create(client,'count',i,0,src=a);approve(client,count);command(client,count,'capture',{'counted_quantity_milli':9000,'evidence_id':evidence(client,count)})
    command(client,count,'post_count',{'evidence_id':evidence(client,count)},409);assert stock(client,i)['available_milli']==0
    with SessionLocal() as db:
        from app.retail_models import RetailReservation
        db.add(RetailReservation(case_id=rid,item_id=i,quantity_milli=-9500,reason='cancel',actor_id=db.scalar(select(User.id).where(User.role=='admin'))));db.commit()
    command(client,count,'post_count',{'evidence_id':evidence(client,count)});assert conserved(client,i)['quantity_milli']==9000

def test_unknown_legacy_quantity_cannot_auto_assign_location(client):
    i,a,b=setup(client,0)
    j=master(client,'items',{'sku':'UNKNOWN','name':'历史未知库存','unit':'件','reorder':'0','active':True})['id']
    with SessionLocal() as db:
        item=db.scalar(select(Item).where(Item.id==j));item.quantity_milli=1000;item.inventory_value_cents=100;item.unit_cost_cents=100;db.commit()
    create(client,'activate',j,1000,locations=[{'location_id':a,'quantity_milli':1000}],status=409)
    assert not stock(client,j)['enabled']

def test_actual_employee_roles_cost_privacy_aggregate_and_cross_store(client):
    i,a,b=setup(client);login(client,'inventory');row=create(client,'gift',i,1000,src=a)
    assert 'value_cents' not in stock(client,i) and all('value_cents' not in x for x in stock(client,i)['entries'])
    approve(client,row,status=403);login(client,'manager');approve(client,row);execute(client,row,status=403)
    login(client,'inventory');execute(client,row);assert 'approved_value_cents' not in get(client,row)
    login(client,'finance');create(client,'disposal',i,1000,src=a,status=403)
    login(client,'sales');assert client.get(API+'/cases').status_code==403 and not client.get(API+'/catalog').json()['can_read']
    login(client,'admin');client.post('/api/stores',json={'code':'WHB','name':'仓储乙店'});client.headers['X-Store-ID']='2'
    assert client.get(API+f'/items/{i}/stock').status_code==404 and client.get(API+f'/cases/{row["id"]}').status_code==404
    client.headers['X-Store-ID']='all';assert client.get(API+'/cases').status_code==409

def test_duplicate_stale_and_competing_actual_confirmation_post_once(client):
    i,a,b=setup(client);row=create(client,'disposal',i,1000,src=a);old=row['version'];row=approve(client,row);e=evidence(client,row);key=uuid.uuid4().hex
    command(client,row,'execute',{'evidence_id':e},409,version=old)
    def act(_):
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
            try:svc.command(db,user,row['id'],uuid.uuid4().hex,row['version'],'execute',{'evidence_id':e});return 200
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(act,range(2)))==[200,409]
    assert conserved(client,i)['quantity_milli']==9000
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove).where(StockMove.case_id==row['id']))==1
    another=create(client,'gift',i,1000,src=a);approve(client,another);another=get(client,another);version=another['version'];e=evidence(client,another)
    first=command(client,another,'execute',{'evidence_id':e},version=version,key=key)
    assert command(client,another,'execute',{'evidence_id':e},version=version,key=key)==first

def test_existing_purchase_requires_exact_allocation_and_keeps_item_ledger_atomic(client):
    i,a,b=setup(client);purchase=flow_create(client,'purchase',{'item_id':i,'quantity':'1','unit_cost':'2.01','supplier':'合成供货者'})
    purchase=flow_action(client,purchase,'approve');e=evidence(client,purchase);flow_action(client,purchase,'stock_in',{'evidence_id':e},409)
    assert conserved(client,i)['quantity_milli']==10000
    options=client.get(API+f'/allocations/{purchase["id"]}');assert options.status_code==200,options.text
    def allocate(qty,items=None,status=200):
        o=client.get(API+f'/allocations/{purchase["id"]}').json()
        r=client.post(API+f'/allocations/{purchase["id"]}',json={'request_id':uuid.uuid4().hex,'version':o['version'],'values':{'item_id':i,'quantity_milli':qty,'purpose':'purchase','locations':items or [{'location_id':b,'quantity_milli':abs(qty)}]}})
        assert r.status_code==status,r.text
    allocate(-1000,status=422);allocate(999);flow_action(client,purchase,'stock_in',{'evidence_id':e},409)
    allocate(1000);flow_action(client,purchase,'stock_in',{'evidence_id':e});s=conserved(client,i)
    assert (s['quantity_milli'],s['value_cents'])==(11000,1202)

def test_immutable_bin_evidence_and_location_deactivation_guard(client):
    i,a,b=setup(client)
    with SessionLocal() as db:
        entry=db.scalar(select(WarehouseEntry));entry.quantity_milli=123
        with pytest.raises(HTTPException):db.commit()
    loc=next(l for l in client.get('/api/masters/locations').json()['items'] if l['id']==a)
    r=client.put('/api/masters/locations/'+str(a),json={'request_id':uuid.uuid4().hex,'version':loc['version'],'values':{'code':loc['code'],'name':loc['name'],'warehouse_id':loc['warehouse_id'],'active':False}})
    assert r.status_code==409,r.text

def test_nonempty_restore_and_tampered_bin_or_missing_original_allocation_refused(client,tmp_path):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.warehouse_backup_integrity import validate_warehouse_integrity
    i,a,b=setup(client);move=create(client,'local_move',i,3000,src=a,dest=b);approve(client,move)
    command(client,move,'dispatch',{'evidence_id':evidence(client,move)})
    count=create(client,'count',i,0,src=a);approve(client,count);command(client,count,'capture',{'counted_quantity_milli':6500,'evidence_id':evidence(client,count)})
    command(client,count,'post_count',{'evidence_id':evidence(client,count)})
    restore=tmp_path/'restore.sqlite'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(restore) as target:source.backup(target)
    with sqlite3.connect(restore) as db:
        result=validate_warehouse_integrity(db);assert result['verified_warehouse_items']==1 and result['verified_warehouse_entries']>=4
        from app.backup_integrity import validate_sqlite
        assert validate_sqlite(db)['verified_warehouse_items']==1
        db.execute('UPDATE warehouse_balances SET quantity_milli=quantity_milli+1 WHERE location_id=?',(a,))
        with pytest.raises(ValueError,match='不守恒'):validate_warehouse_integrity(db)
        db.rollback();db.execute("UPDATE warehouse_allocations SET status='prepared' WHERE stock_move_id IS NOT NULL")
        with pytest.raises(ValueError,match='分配'):validate_warehouse_integrity(db)

@pytest.mark.parametrize('domain',['legacy','procurement','transfer','repair','retail'])
def test_all_existing_stock_writers_consume_one_bin_allocation_atomically(client,domain):
    from app import warehouse_stock
    i,a,b=setup(client)
    with SessionLocal() as db:
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.role=='admin')),'admin')
        case=Case(number='HOOK-'+uuid.uuid4().hex,kind='purchase',flow_version=2,state='receiving',title='合成原业务',owner_id=user.id,created_by=user.id,business_date=today(),data={'item_id':i})
        db.add(case);db.commit();cid=case.id
    def post(db,user,case,item):
        if domain=='legacy':
            from app.flow_engine import stock_move
            return stock_move(db,user,case,item,1000,201,'purchase')
        if domain=='procurement':from app.procurement_service import _stock as wrapper
        elif domain=='transfer':from app.transfer_service import posting as wrapper
        elif domain=='repair':from app.repair_service import _post_stock as wrapper
        else:from app.retail_service import _stock as wrapper
        return wrapper(db,user,case,item,1000,201,'return')
    with SessionLocal() as db:
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.role=='admin')),'admin');case=db.scalar(select(Case).where(Case.id==cid));item=warehouse_stock.item_lock(db,i)
        with pytest.raises(HTTPException,match='真实库位'):post(db,user,case,item)
        db.rollback()
    assert conserved(client,i)['quantity_milli']==10000
    with SessionLocal() as db:
        set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.role=='admin')),'admin');case=db.scalar(select(Case).where(Case.id==cid));item=warehouse_stock.item_lock(db,i)
        warehouse_stock.prepare(db,user,case,item,1000,'purchase' if domain=='legacy' else 'return',[{'location_id':b,'quantity_milli':1000}]);post(db,user,case,item);db.commit()
    assert conserved(client,i)['value_cents']==1202

def test_existing_ledger_activation_no_stock_duplication_and_stale_activation_refused(client):
    i,a,b=setup(client,0)
    j=master(client,'items',{'sku':'KNOWN','name':'已核对原库存','unit':'件','reorder':'0','active':True})['id']
    purchase=flow_create(client,'purchase',{'item_id':j,'quantity':'2','unit_cost':'1.23','supplier':'合成来源'})
    flow_action(client,purchase,'approve');flow_action(client,purchase,'stock_in',{'evidence_id':evidence(client,purchase)})
    row=create(client,'activate',j,2000,locations=[{'location_id':a,'quantity_milli':1000},{'location_id':b,'quantity_milli':1000}]);approve(client,row)
    s=conserved(client,j);assert s['value_cents']==246
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove).where(StockMove.item_id==j))==1
    k=master(client,'items',{'sku':'STALE','name':'申请后变动','unit':'件','reorder':'0','active':True})['id']
    stale=create(client,'activate',k,0,locations=[{'location_id':a,'quantity_milli':0}]);purchase=flow_create(client,'purchase',{'item_id':k,'quantity':'1','unit_cost':'1','supplier':'新来源'})
    flow_action(client,purchase,'approve');flow_action(client,purchase,'stock_in',{'evidence_id':evidence(client,purchase)})
    approve(client,stale,status=409);assert not stock(client,k)['enabled']

def test_overdue_handoff_has_explicit_role_and_case_authority(client):
    from datetime import timedelta
    from app.models import UserStore
    from tests.conftest import PASSWORD_HASH
    i,a,b=setup(client)
    row=create(client,'gift',i,1000,src=a,due_date=(today()-timedelta(days=2)).isoformat())
    with SessionLocal() as db:
        replacement=User(username='inventory-b',display_name='替班库管',role='inventory',password_hash=PASSWORD_HASH,must_change_password=False);db.add(replacement);db.flush();db.add(UserStore(user_id=replacement.id,store_id=1));db.commit();uid=replacement.id
    login(client,'manager');approve(client,row)
    case=client.get('/api/flow/cases/'+str(row['id'])).json();t=next(t for t in case['tasks'] if t['status']=='open')
    command(client,row,'assign',{'task_id':t['id'],'assignee_id':uid,'due_date':today().isoformat(),'reason':'原负责人交班由替班库管接手'})
    login(client,'inventory');execute(client,row,status=403)
    login(client,'inventory-b');execute(client,row)
    login(client,'admin');assert conserved(client,i)['quantity_milli']==9000

def test_real_bin_prevents_changing_parent_warehouse_or_repurposing_as_vehicle_warehouse(client):
    i,a,b=setup(client);loc=next(l for l in client.get('/api/masters/locations').json()['items'] if l['id']==a)
    other=typed(client,'warehouses',{'code':'OTHER-W','name':'另一个物资仓','warehouse_type':'materials'})
    r=client.put('/api/masters/locations/'+str(a),json={'request_id':uuid.uuid4().hex,'version':loc['version'],'values':{'code':loc['code'],'name':loc['name'],'warehouse_id':other['id'],'active':True}})
    assert r.status_code==409,r.text
    wh=next(w for w in client.get('/api/masters/warehouses').json()['items'] if w['id']==loc['warehouse_id'])
    r=client.put('/api/masters/warehouses/'+str(wh['id']),json={'request_id':uuid.uuid4().hex,'version':wh['version'],'values':{'code':wh['code'],'name':wh['name'],'warehouse_type':'vehicles','active':True}})
    assert r.status_code==409,r.text

def test_wrong_count_observation_needs_explicit_supervisor_evidence_to_void(client):
    i,a,b=setup(client);count=create(client,'count',i,0,src=a);approve(client,count)
    command(client,count,'capture',{'counted_quantity_milli':2000,'evidence_id':evidence(client,count)})
    command(client,count,'cancel',{'reason':'不能普通取消已提交观察'},409)
    login(client,'inventory');command(client,count,'void_observation',{'reason':'无权撤销观察','evidence_id':evidence(client,count)},403)
    login(client,'manager');count=command(client,count,'void_observation',{'reason':'现场复核证实少记录一箱，原观察错误','evidence_id':evidence(client,count)})
    assert count['state']=='cancelled' and count['count']['counted_quantity_milli']==2000
    login(client,'admin');assert conserved(client,i)['quantity_milli']==10000 and stock(client,i)['available_milli']==10000

def test_frozen_warehouse_migration_matches_schema_without_importing_live_metadata(tmp_path):
    from alembic import command as migration
    from alembic.config import Config
    from sqlalchemy import create_engine,inspect,text
    from app.db import Base
    cfg=Config('alembic.ini');cfg.attributes['url_override']='sqlite:///'+(tmp_path/'synthetic-warehouse.sqlite').as_posix();migration.upgrade(cfg,'r218_warehouse')
    target=create_engine(cfg.attributes['url_override'])
    try:
        inspector=inspect(target)
        for name,table in Base.metadata.tables.items():
            if name.startswith('warehouse_'):assert {c['name'] for c in inspector.get_columns(name)}==set(table.columns.keys())
        with target.connect() as db:assert not db.execute(text('PRAGMA foreign_key_check')).first()
    finally:target.dispose()

def test_location_preparation_does_not_invalidate_legacy_count_item_snapshot(client):
    item,a,b=setup(client);original=flow_create(client,'stock_count',{'item_id':item,'counted':'9','reason':'原版本总量盘点保留语义'})
    options=client.get(API+f'/allocations/{original["id"]}').json()
    result=client.post(API+f'/allocations/{original["id"]}',json={'request_id':uuid.uuid4().hex,'version':options['version'],'values':{'item_id':item,'quantity_milli':-1000,'purpose':'count','locations':[{'location_id':a,'quantity_milli':1000}]}})
    assert result.status_code==200,result.text
    flow_action(client,original,'count_approve',{'evidence_id':evidence(client,original)})
    assert conserved(client,item)['quantity_milli']==9000

def test_count_gain_uses_existing_cost_and_zero_stock_never_guesses_value(client):
    item,a,b=setup(client,3000,1000);count=create(client,'count',item,0,src=a);approve(client,count)
    command(client,count,'capture',{'counted_quantity_milli':4000,'evidence_id':evidence(client,count)})
    command(client,count,'post_count',{'evidence_id':evidence(client,count)})
    s=conserved(client,item);assert (s['quantity_milli'],s['value_cents'])==(4000,1333)
    other,c,d=setup(client,0);unknown=create(client,'count',other,0,src=c);approve(client,unknown)
    command(client,unknown,'capture',{'counted_quantity_milli':1000,'evidence_id':evidence(client,unknown)})
    command(client,unknown,'post_count',{'evidence_id':evidence(client,unknown)},409)
    assert stock(client,other)['quantity_milli']==0 and get(client,unknown)['state']=='review'
