"""Every warehouse chart/CSV measures the same real bin and movement facts."""
import csv,io
from datetime import timedelta
from sqlalchemy import select
from app.db import SessionLocal,today
from app.flow_models import StockMove
from app.warehouse_models import WarehouseBalance,WarehouseEntry,WarehouseDocument
from tests.conftest import login
from tests.test_warehouse import setup,create,approve,command,evidence,conserved

def test_warehouse_current_and_period_tables_reconcile_original_rows_charts_and_csv(client):
    item,a,b=setup(client);move=create(client,'local_move',item,4000,src=a,dest=b);approve(client,move)
    command(client,move,'dispatch',{'evidence_id':evidence(client,move)})
    command(client,move,'accept',{'quantity_milli':1000,'evidence_id':evidence(client,move)})
    count=create(client,'count',item,0,src=a);approve(client,count);command(client,count,'capture',{'counted_quantity_milli':5500,'evidence_id':evidence(client,count)})
    command(client,count,'post_count',{'evidence_id':evidence(client,count)})
    stock=conserved(client,item);response=client.get('/api/flow/analytics');assert response.status_code==200,response.text;report=response.json()
    balances=report['tables']['warehouse_balances']['rows'];local=report['tables']['warehouse_local_moves']['rows'];counts=report['tables']['warehouse_counts']['rows']
    with SessionLocal() as db:
        source=list(db.scalars(select(WarehouseBalance).where(WarehouseBalance.item_id==item)))
        assert sum(r['quantity_milli'] for r in balances)==sum(b.quantity_milli for b in source)==stock['quantity_milli']==9500
        assert sum(r['amount_cents'] for r in balances)==sum(b.value_cents for b in source)==stock['value_cents']
        entries=list(db.scalars(select(WarehouseEntry).where(WarehouseEntry.case_id==move['id'])))
        assert sorted((r['quantity_milli'],r['amount_cents']) for r in local)==sorted((e.quantity_milli,e.value_cents) for e in entries)
        assert sum(r['quantity_milli'] for r in local)==0 and sum(r['amount_cents'] for r in local)==0
        differences=list(db.scalars(select(StockMove).where(StockMove.purpose=='wh_count')))
        assert [(r['quantity_milli'],r['amount_cents']) for r in counts]==[(m.quantity_milli,m.value_cents) for m in differences]
    chart=next(c for c in report['charts'] if c['id']=='warehouse_balances')
    assert sum(chart['series'][0]['values'])==sum(r['amount_cents'] for r in balances)
    for name in ['warehouse_balances','warehouse_local_moves','warehouse_counts']:
        exported=client.get('/api/flow/analytics/export?dataset='+name);assert exported.status_code==200,exported.text
        parsed=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))));assert parsed[0]==report['tables'][name]['headers']
        normalized=[[v[1:] if v.startswith("'-") and v[2:].replace('.','',1).isdigit() else v for v in line] for line in parsed[1:]]
        assert normalized==[[str(v) for v in r['values']] for r in report['tables'][name]['rows']]
    yesterday=(today()-timedelta(days=1)).isoformat();old=client.get('/api/flow/analytics',params={'date_from':yesterday,'date_to':yesterday}).json()
    assert old['tables']['warehouse_local_moves']['rows']==old['tables']['warehouse_counts']['rows']==[]
    assert sum(r['quantity_milli'] for r in old['tables']['warehouse_balances']['rows'])==9500
    login(client,'inventory');assert client.get('/api/flow/analytics').status_code==403

def test_warehouse_report_respects_store_scope_and_aggregate_reads_without_adding_internal_moves(client):
    i,a,b=setup(client);move=create(client,'local_move',i,2000,src=a,dest=b);approve(client,move);command(client,move,'dispatch',{'evidence_id':evidence(client,move)})
    client.post('/api/stores',json={'code':'WH-REPORT-B','name':'合成库位报表乙店'});client.headers['X-Store-ID']='2'
    local=client.get('/api/flow/analytics').json();assert local['tables']['warehouse_balances']['rows']==local['tables']['warehouse_local_moves']['rows']==[]
    setup(client,4000,800);client.headers['X-Store-ID']='all';group=client.get('/api/flow/analytics').json()
    assert sum(r['quantity_milli'] for r in group['tables']['warehouse_balances']['rows'])==14000
    assert sum(r['amount_cents'] for r in group['tables']['warehouse_balances']['rows'])==1801
    assert sum(r['quantity_milli'] for r in group['tables']['warehouse_local_moves']['rows'])==0
