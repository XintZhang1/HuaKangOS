"""Scoped original-batch lookup and unchanged real warehouse return accounting."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from sqlalchemy import select,func
from app.db import SessionLocal,today
from app.models import User,CashEntry
from app.flow_models import StockMove,Case
from app.tenancy import set_scope,project_user
from app import warehouse_service as svc
from tests.conftest import login
from tests.test_warehouse import setup,create,approve,execute,get,command,conserved
from tests.test_workflow import evidence

API='/api/warehouse/return-sources'

def candidates(c,operation,**params):
    result=c.get(API,params={'operation':operation,**params});assert result.status_code==200,result.text
    return result.json()

def completed(c,op='gift',qty=3000):
    item,a,b=setup(c,qty,1001);row=create(c,op,item,qty,src=a);approve(c,row);row=execute(c,row)
    return item,a,b,row,row['stock_moves'][0]['id']

def test_candidate_and_original_row_show_actual_date_remaining_and_no_mutation(client):
    item,a,b,row,move=completed(client)
    initial=conserved(client,item)
    with SessionLocal() as db:before=db.scalar(select(func.count()).select_from(Case))
    shown=candidates(client,'gift_return',q='合成耗材')['items'][0]
    assert shown['original_move_id']==move and shown['source_case_id']==row['id']
    assert shown['business_date']==today().isoformat() and shown['remaining_quantity_milli']==3000
    assert shown['original_value_cents']==1001 and shown['can_return']
    assert candidates(client,'gift_return',q=row['number'])['total']==1
    assert candidates(client,'consumable_return')['total']==0
    assert candidates(client,'other_in_return')['total']==1
    detail=get(client,row)['stock_moves'][0]
    assert detail['return_operation']=='gift_return' and detail['returnable_milli']==3000 and detail['returned_milli']==0
    assert detail['business_date']==shown['business_date'] and detail['return_source']==shown
    assert conserved(client,item)==initial
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Case))==before

def test_roles_cost_privacy_cross_store_and_aggregate_are_enforced(client):
    item,a,b,row,move=completed(client)
    login(client,'inventory');shown=candidates(client,'gift_return')['items'][0]
    assert shown['can_return'] and not any('value' in key or 'cost' in key for key in shown)
    detail=get(client,row)['stock_moves'][0]
    assert not any('value' in key or 'cost' in key for key in detail['return_source'])
    login(client,'finance');assert not candidates(client,'gift_return')['items'][0]['can_return']
    create(client,'gift_return',item,1000,dest=b,original=move,status=403)
    login(client,'sales');assert client.get(API,params={'operation':'gift_return'}).status_code==403
    login(client);client.post('/api/stores',json={'code':'WR-B','name':'原退乙店'});client.headers['X-Store-ID']='2'
    assert candidates(client,'gift_return')['items']==[]
    assert client.get(API,params={'operation':'gift_return','original_move_id':move}).status_code==404
    create(client,'gift_return',item,1000,dest=b,original=move,status=404)
    client.headers['X-Store-ID']='all';assert client.get(API,params={'operation':'gift_return'}).status_code==409

def test_partial_return_updates_original_remaining_and_last_part_restores_exact_value_once(client):
    item,a,b,row,move=completed(client,'consumable')
    application=uuid.uuid4().hex
    first=create(client,'consumable_return',item,1000,dest=b,original=move,request_id=application)
    duplicate=create(client,'consumable_return',item,1000,dest=b,original=move,request_id=application)
    assert first['id']==duplicate['id']
    assert candidates(client,'consumable_return')['items'][0]['remaining_quantity_milli']==3000
    approve(client,first);first=get(client,first);key=uuid.uuid4().hex;e=evidence(client,first)
    version=first['version'];first=command(client,first,'execute',{'evidence_id':e},key=key,version=version)
    assert command(client,first,'execute',{'evidence_id':e},key=key,version=version)==first
    after=candidates(client,'consumable_return')['items'][0]
    assert (after['returned_quantity_milli'],after['remaining_quantity_milli'])==(1000,2000)
    assert after['returned_value_cents']+after['remaining_value_cents']==1001
    create(client,'consumable_return',item,2001,dest=b,original=move,status=409)
    second=create(client,'consumable_return',item,2000,dest=b,original=move);approve(client,second);execute(client,second)
    assert candidates(client,'consumable_return')['items']==[]
    closed=candidates(client,'consumable_return',original_move_id=move)['items'][0]
    assert closed['remaining_quantity_milli']==closed['remaining_value_cents']==0 and not closed['can_return']
    summary=conserved(client,item);assert (summary['quantity_milli'],summary['value_cents'])==(3000,1001)
    assert next(r for r in summary['balances'] if r['location_id']==b)['quantity_milli']==3000
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0

def test_wrong_return_domain_and_other_domain_same_purpose_are_refused(client):
    item,a,b,row,move=completed(client)
    create(client,'consumable_return',item,1000,dest=b,original=move,status=422)
    assert client.get(API,params={'operation':'consumable_return','original_move_id':move}).status_code==404
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=='admin'))
        source=Case(number='WRONG-DOMAIN',kind='purchase',flow_version=2,state='completed',title='测试他域流水',owner_id=user.id,created_by=user.id,business_date=today(),data={})
        db.add(source);db.flush();fake=StockMove(case_id=source.id,item_id=item,quantity_milli=-1000,value_cents=-100,unit_cost_cents=100,purpose='wh_gift',actor_id=user.id,business_date=today())
        db.add(fake);db.commit();fake_id=fake.id
    assert client.get(API,params={'operation':'gift_return','original_move_id':fake_id}).status_code==404
    create(client,'gift_return',item,1000,dest=b,original=fake_id,status=422)

def test_incomplete_original_and_current_physical_quantity_are_rechecked(client):
    item,a,b,row,move=completed(client)
    with SessionLocal() as db:original=db.scalar(select(Case).where(Case.id==row['id']));original.state='ready';db.commit()
    assert candidates(client,'gift_return')['items']==[]
    create(client,'gift_return',item,1000,dest=b,original=move,status=422)
    with SessionLocal() as db:original=db.scalar(select(Case).where(Case.id==row['id']));original.state='completed';db.commit()
    first=create(client,'gift_return',item,3000,dest=b,original=move);second=create(client,'gift_return',item,3000,dest=b,original=move)
    approve(client,first);approve(client,second);execute(client,first);execute(client,second,status=409)
    assert conserved(client,item)['quantity_milli']==3000

def test_competing_approved_returns_share_original_limit_and_post_only_one(client):
    item,a,b,row,move=completed(client)
    entries=[]
    for _ in range(2):
        back=create(client,'gift_return',item,3000,dest=b,original=move);approve(client,back);entries.append((get(client,back),evidence(client,back)))
    def perform(entry):
        row,file=entry
        with SessionLocal() as db:
            set_scope(db,[1],1);user=project_user(db.scalar(select(User).where(User.username=='admin')),'admin')
            try:svc.command(db,user,row['id'],uuid.uuid4().hex,row['version'],'execute',{'evidence_id':file});return 200
            except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(perform,entries))==[200,409]
    result=conserved(client,item);assert (result['quantity_milli'],result['value_cents'])==(3000,1001)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove).where(StockMove.original_id==move))==1

def test_stale_actual_return_rejected_and_inbound_original_is_physical_only(client):
    item,a,b=setup(client,3000,1001);original=candidates(client,'other_in_return')['items'][0]
    back=create(client,'other_in_return',item,1000,src=a,original=original['original_move_id']);old=back['version'];approve(client,back)
    command(client,back,'execute',{'evidence_id':evidence(client,back)},status=409,version=old)
    execute(client,back);assert candidates(client,'other_in_return')['items'][0]['remaining_quantity_milli']==2000
    result=conserved(client,item);assert (result['quantity_milli'],result['value_cents'])==(2000,667)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
