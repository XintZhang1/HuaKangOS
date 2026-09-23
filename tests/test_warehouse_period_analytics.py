"""Warehouse bridge, signed moving-average revaluation, scope and export facts."""
import csv,io,uuid
from datetime import timedelta
from sqlalchemy import select,text
from app.db import SessionLocal,engine,today
from app.flow_models import Item,StockMove
from app.master_models import StorageLocation
from app.warehouse_models import WarehouseEnrollment,WarehouseBalance,WarehouseEntry
from tests.conftest import login
from tests.test_warehouse import setup,create,approve,execute,command,evidence,stock
from tests.test_vehicle_procurement import typed
from tests.test_workflow import master

API='/api/inventory-reports/warehouses'
def report(c,**params):
    r=c.get(API,params=params);assert r.status_code==200,r.text;return r.json()
def prior_day():return (today()-timedelta(days=1)).isoformat()
def historical_bridge():
    # Date complete original synthetic sources before today's query; no public
    # endpoint may edit these append-only facts.
    with engine.begin() as db:
        db.execute(text("UPDATE flow_events SET occurred_at=:stamp WHERE action='warehouse_approve' AND case_id IN (SELECT case_id FROM warehouse_enrollments)"),{'stamp':prior_day()+' 04:00:00'})
        db.execute(text('UPDATE warehouse_entries SET business_date=:day'),{'day':prior_day()})
        db.execute(text('UPDATE flow_stock_moves SET business_date=:day'),{'day':prior_day()})
def today_query():return {'date_from':today().isoformat(),'date_to':today().isoformat()}
def csv_matches(c,data,key,**params):
    result=c.get(API+'/export/'+key,params=params);assert result.status_code==200,result.text
    parsed=list(csv.reader(io.StringIO(result.content.decode('utf-8-sig'))))
    expected=[data['tables'][key]['headers']]+[[str(v) for v in r['values']] for r in data['tables'][key]['rows']]
    assert parsed==expected


def test_new_activation_day_has_unknown_midnight_but_known_closing(client):
    item,a,b=setup(client);d=report(client,**today_query())
    assert not d['complete'] and d['closing_complete'] and len(d['rows'])==1
    r=d['rows'][0];assert r['opening'] is None and r['in'] is None and r['out'] is None
    assert r['closing']=={'quantity_milli':10000,'value_cents':1001}
    assert d['baselines'][0]['quantity_milli']==0 and r['known_in_milli']==10000
    assert d['charts'][0]['series'][0]['values']==[1001]
    assert '不代表全期间' not in str(d['charts']) # Chart itself names known closing, not whole period.
    old=report(client,date_from=prior_day(),date_to=prior_day());assert not old['closing_complete'] and old['charts']==[] and old['rows'][0]['closing'] is None


def test_nonzero_bridge_is_baseline_not_receipt_and_period_starts_after_bridge(client):
    from tests.test_stock_reports import source
    item=source();w=typed(client,'warehouses',{'code':'WB','name':'合成桥接仓','warehouse_type':'materials'})
    a=typed(client,'locations',{'code':'BA','name':'桥接甲','warehouse_id':w['id']})['id']
    b=typed(client,'locations',{'code':'BB','name':'桥接乙','warehouse_id':w['id']})['id']
    initial=create(client,'activate',item,2000,locations=[{'location_id':a,'quantity_milli':1000},{'location_id':b,'quantity_milli':1000}]);approve(client,initial)
    d=report(client,**today_query());assert not d['complete'] and d['closing_complete']
    assert sum(r['quantity_milli'] for r in d['baselines'])==2000
    assert sum(r['known_in_milli'] for r in d['rows'])==0 and all(e['is_baseline'] for e in d['details'])
    historical_bridge();d=report(client,**today_query());assert d['complete']
    assert sum(r['opening']['quantity_milli'] for r in d['rows'])==2000
    assert sum(r['opening']['value_cents'] for r in d['rows'])==203
    assert d['details']==[]


def test_partial_move_transit_and_past_closing_are_not_current_snapshot(client):
    i,a,b=setup(client);historical_bridge()
    move=create(client,'local_move',i,4000,src=a,dest=b);approve(client,move);command(client,move,'dispatch',{'evidence_id':evidence(client,move)})
    command(client,move,'accept',{'quantity_milli':1000,'evidence_id':evidence(client,move)})
    d=report(client,**today_query());assert d['complete'] and d['closing_complete']
    assert sorted(r['closing']['quantity_milli'] for r in d['rows'])==[1000,3000,6000]
    assert sum(r['closing']['value_cents'] for r in d['rows'])==1001
    assert sum(r['quantity_milli'] for r in d['details'])==0 and sum(r['value_cents'] for r in d['details'])==0
    for key in d['tables']:csv_matches(client,d,key,**today_query())
    old=report(client,date_from=prior_day(),date_to=prior_day());assert old['closing_complete'] and sum(r['closing']['quantity_milli'] for r in old['rows'])==10000
    assert sum(r['closing']['quantity_milli'] for r in old['rows'] if r.get('transit_case_id'))==0


def test_store_average_zero_quantity_revaluation_is_separate(client):
    i,a,b=setup(client);move=create(client,'local_move',i,5000,src=a,dest=b);approve(client,move)
    command(client,move,'dispatch',{'evidence_id':evidence(client,move)});command(client,move,'accept',{'quantity_milli':5000,'evidence_id':evidence(client,move)})
    historical_bridge()
    incoming=create(client,'other_in',i,1000,dest=a);approve(client,incoming,1000);execute(client,incoming)
    d=report(client,**today_query());assert d['complete']
    zero=[e for e in d['details'] if not e['quantity_milli'] and e['value_cents']]
    assert zero and all(e['label']=='均价分摊调整' for e in zero)
    for r in d['rows']:
        assert r['closing']['value_cents']==r['opening']['value_cents']+r['in']['value_cents']+r['out']['value_cents']+r['revaluation_cents']
        assert r['closing']['quantity_milli']==r['opening']['quantity_milli']+r['in']['quantity_milli']-r['out']['quantity_milli']
    assert sum(r['closing']['value_cents'] for r in d['rows'])==2001


def test_outbound_bin_value_can_increase_while_original_return_conserves(client,monkeypatch):
    # Preserve the published V2 original-cost return and its signed bin values.
    from app import procurement_service
    monkeypatch.setattr(procurement_service,'CURRENT_FLOW_VERSION',2)
    from tests.test_procurement import supplier,command as pc,receive as pr,return_request,return_action
    s=supplier(client);i=master(client,'items',{'sku':'SIGNED','name':'有符号原退物资','unit':'件','reorder':'0','active':True})['id'];orders=[]
    for q,cost in [(1000,10),(9000,110)]:
        response=client.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,'supplier_id':s['id'],'reason':'合成不同原批次','lines':[{'item_id':i,'quantity_milli':q,'unit_cost_cents':cost}]});assert response.status_code==201,response.text
        row=pc(client,response.json(),'approve');orders.append(pr(client,row))
    w=typed(client,'warehouses',{'code':'SIGNED-W','name':'原成本分配仓','warehouse_type':'materials'})
    a=typed(client,'locations',{'code':'SIGNED-A','name':'原退甲','warehouse_id':w['id']})['id'];b=typed(client,'locations',{'code':'SIGNED-B','name':'原退乙','warehouse_id':w['id']})['id']
    en=create(client,'activate',i,10000,locations=[{'location_id':a,'quantity_milli':9000},{'location_id':b,'quantity_milli':1000}]);approve(client,en);historical_bridge()
    row,ret=return_request(client,orders[0],orders[0]['receipts'][0],1000);return_action(client,row,ret,'return_approve')
    options=client.get('/api/warehouse/allocations/'+str(row['id'])).json()
    result=client.post('/api/warehouse/allocations/'+str(row['id']),json={'request_id':uuid.uuid4().hex,'version':options['version'],'values':{'item_id':i,'quantity_milli':-1000,'purpose':'procurement_return','locations':[{'location_id':a,'quantity_milli':1},{'location_id':b,'quantity_milli':999}]}});assert result.status_code==200,result.text
    return_action(client,row,ret,'return_dispatch')
    d=report(client,**today_query());assert d['complete']
    positive=next(e for e in d['details'] if e['quantity_milli']<0 and e['value_cents']>0)
    assert positive['quantity_milli']==-1 and positive['value_cents']==90
    assert sum(e['quantity_milli'] for e in d['details'])==-1000 and sum(e['value_cents'] for e in d['details'])==-10
    assert sum(r['out']['value_cents'] for r in d['rows'])==-10


def test_source_gap_scope_cost_mask_filters_and_empty_bin_parent_guard(client):
    i,a,b=setup(client);out=create(client,'disposal',i,10000,src=a);approve(client,out);execute(client,out)
    row=next(r for r in client.get('/api/masters/locations').json()['items'] if r['id']==a)
    old_wh=row['warehouse_id'];new=typed(client,'warehouses',{'code':'FRESH-W','name':'无历史新仓','warehouse_type':'materials'})
    body={'request_id':uuid.uuid4().hex,'version':row['version'],'values':{k:row[k] for k in ('code','name','warehouse_id','active')}};body['values']['warehouse_id']=new['id']
    assert client.put('/api/masters/locations/'+str(a),json=body).status_code==409
    wh=next(w for w in client.get('/api/masters/warehouses').json()['items'] if w['id']==old_wh)
    assert client.put('/api/masters/warehouses/'+str(old_wh),json={'request_id':uuid.uuid4().hex,'version':wh['version'],'values':{'code':wh['code'],'name':wh['name'],'warehouse_type':'mixed','active':True}}).status_code==409
    fresh=next(r for r in client.get('/api/masters/locations').json()['items'] if r['id']==b)
    assert client.put('/api/masters/locations/'+str(b),json={'request_id':uuid.uuid4().hex,'version':fresh['version'],'values':{'code':fresh['code'],'name':fresh['name'],'warehouse_id':new['id'],'active':True}}).status_code==200
    login(client,'inventory');d=report(client,item_id=i,warehouse_id=old_wh);assert not d['can_money'] and 'value_cents' not in str(d['rows']) and 'revaluation_cents' not in str(d['rows'])
    assert '价值' not in str(d['tables']) and d['charts']==[]
    login(client,'sales');assert client.get(API).status_code==403 and client.get(API+'/options/items').status_code==403
    login(client,'admin');client.post('/api/stores',json={'code':'WP-B','name':'合成乙店'});client.headers['X-Store-ID']='2'
    assert report(client)['rows']==[] and client.get(API,params={'item_id':i}).status_code==404 and client.get(API,params={'warehouse_id':old_wh}).status_code==404


def test_tampered_source_and_unenrolled_item_never_get_false_zero(client):
    i,_,_=setup(client);historical_bridge()
    with engine.begin() as db:db.execute(text('UPDATE warehouse_entries SET value_cents=value_cents+1 WHERE id=1'))
    d=report(client,**today_query());assert not d['complete'] and not d['closing_complete'] and d['charts']==[]
    assert d['rows'][0]['closing'] is None and '不守恒' in str(d['rows'][0]['issues'])
    with SessionLocal() as db:db.add(Item(sku='NO-BIN',name='未有实际库位',unit='件',quantity_milli=0,inventory_value_cents=0));db.commit()
    d=report(client);unlocated=next(r for r in d['rows'] if r['sku']=='NO-BIN');assert unlocated['closing'] is None and unlocated['opening'] is None


def test_warehouse_filter_keeps_origin_transit_once_and_group_has_no_business_links(client):
    i,a,b=setup(client);historical_bridge()
    first=next(r['warehouse_id'] for r in client.get('/api/masters/locations').json()['items'] if r['id']==a)
    second=typed(client,'warehouses',{'code':'SECOND-W','name':'合成店内另一仓','warehouse_type':'materials'})['id']
    dest=typed(client,'locations',{'code':'SECOND-L','name':'合成另一仓实际库位','warehouse_id':second})['id']
    row=create(client,'local_move',i,4000,src=a,dest=dest);approve(client,row);command(client,row,'dispatch',{'evidence_id':evidence(client,row)})
    command(client,row,'accept',{'quantity_milli':1000,'evidence_id':evidence(client,row)})
    one=report(client,warehouse_id=first,**today_query());two=report(client,warehouse_id=second,**today_query())
    assert sum(r['closing']['quantity_milli'] for r in one['rows'])==9000
    assert sum(r['closing']['quantity_milli'] for r in two['rows'])==1000
    assert len([r for r in one['rows'] if r.get('transit_case_id')])==1 and not any(r.get('transit_case_id') for r in two['rows'])
    for d in (one,two):assert sum(d['charts'][0]['series'][0]['values'])==sum(r['closing']['value_cents'] for r in d['rows'])
    csv_matches(client,one,'warehouse_period_entries',warehouse_id=first,**today_query())
    client.headers['X-Store-ID']='all';group=report(client,**today_query())
    assert all(not r.get('route') for t in group['tables'].values() for r in t['rows'])


def test_recorded_old_parent_change_cannot_disappear_when_old_warehouse_is_filtered(client):
    from app.models import AuditLog
    i,a,b=setup(client);historical_bridge()
    first=next(r['warehouse_id'] for r in client.get('/api/masters/locations').json()['items'] if r['id']==a)
    second=typed(client,'warehouses',{'code':'HISTORY-W','name':'合成历史新仓','warehouse_type':'materials'})['id']
    # Reproduce an audit left by the old parent-change policy, only in this
    # synthetic DB. The current public master endpoint refuses this operation.
    with engine.begin() as db:db.execute(text('UPDATE master_locations SET warehouse_id=:wid WHERE id=:id'),{'wid':second,'id':a})
    with SessionLocal() as db:
        db.add(AuditLog(actor_id=None,action='master_update',entity_type='typed_master',entity_id=a,before_data={'warehouse_id':first},after_data={'warehouse_id':second}));db.commit()
    d=report(client,**today_query());assert not d['closing_complete'] and '历史仓库归属待核对' in str(d['rows'])
    for wid in (first,second):
        response=client.get(API,params={'warehouse_id':wid,**today_query()});assert response.status_code==409,response.text
        assert '历史库位' in response.text


def test_general_analytics_reuses_exact_warehouse_tables_and_readonly_options(client):
    i,a,b=setup(client);historical_bridge();d=report(client,**today_query())
    response=client.get('/api/flow/analytics',params=today_query());assert response.status_code==200,response.text
    combined=response.json()
    for key,t in d['tables'].items():assert combined['tables'][key]==t
    options=client.get(API+'/options/items',params={'q':'合成耗材礼品'});assert options.status_code==200 and options.json()['items'][0]['id']==i
    assert 'cost' not in options.text and 'value_cents' not in options.text
    assert client.get(API+'/options/unknown').status_code==404
    assert client.get(API,params={'date_from':today().isoformat(),'date_to':prior_day()}).status_code==422


def test_period_snapshot_does_not_mix_concurrent_actual_warehouse_postings(client):
    from app.warehouse_period_analytics import build_warehouse_period
    from app.models import User
    from app.tenancy import set_scope,project_user
    i,a,b=setup(client);historical_bridge()
    outgoing=create(client,'disposal',i,1000,src=a);approve(client,outgoing)
    with SessionLocal() as old:
        set_scope(old,[1],1);user=project_user(old.scalar(select(User).where(User.username=='admin')),'admin')
        assert old.scalar(select(Item.quantity_milli).where(Item.id==i))==10000
        execute(client,outgoing)
        original=build_warehouse_period(old,user,today(),today())
        assert original['complete'] and sum(r['closing']['quantity_milli'] for r in original['rows'])==10000
    current=report(client,**today_query())
    assert current['complete'] and sum(r['closing']['quantity_milli'] for r in current['rows'])==9000
