import csv,io,uuid
from datetime import timedelta
from sqlalchemy import text
from app.db import engine,today
from tests.conftest import login
from tests.test_procurement import setup,command,receive,return_request,return_action

API='/api/inventory-reports/procurement'
def report(c,**params):
    response=c.get(API,params=params);assert response.status_code==200,response.text;return response.json()


def test_order_cohort_partial_close_original_return_conservation_and_csv(client):
    order,_,_=setup(client);order=command(client,order,'approve')
    order=receive(client,order,[{'line_id':order['lines'][0]['id'],'quantity_milli':1000}])
    order,ret=return_request(client,order,order['receipts'][0],500);return_action(client,order,ret,'return_approve');order=return_action(client,order,ret,'return_dispatch')
    command(client,order,'close_receiving',{'reason':'确认未到余量不再供货'})
    data=report(client);assert data['complete'],data
    row=data['rows'][0]
    assert [row[k]['quantity_milli'] for k in ['ordered','received','open','closed','pending','returned','retained']]==[2500,1000,0,1500,0,500,500]
    assert [row[k]['value_cents'] for k in ['ordered','received','closed','returned','retained']]==[308,123,185,62,61]
    assert data['metrics']['procurement_cohort_ordered_cents']==309
    assert data['charts'][0]['series'][0]['values']==[3.5,1,0,2.5,0,.5,.5]
    for key,t in data['tables'].items():
        response=client.get(API+'/export/'+key);assert response.status_code==200
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert rows==[t['headers']]+[[str(v) for v in r['values']] for r in t['rows']]


def test_cohort_uses_original_application_not_receipt_period_or_historical_status(client):
    order,_,_=setup(client);order=command(client,order,'approve');receive(client,order)
    # Only a synthetic fixture may date its immutable creation to a previous batch.
    day=today()-timedelta(days=9)
    with engine.begin() as db:
        db.execute(text("UPDATE flow_events SET occurred_at=:stamp WHERE action='procurement_create'"),{'stamp':day.isoformat()+' 04:00:00'})
        db.execute(text('UPDATE flow_cases SET business_date=:day WHERE id=:id'),{'day':day.isoformat(),'id':order['id']})
    assert report(client,date_from=today().isoformat())['rows']==[]
    data=report(client,date_from=day.isoformat(),date_to=day.isoformat())
    assert data['complete'] and data['rows'][0]['received']['quantity_milli']==2500
    assert {r['date'] for r in data['details']}=={today().isoformat()}
    assert '不是截至期间末日' in data['definition'] and data['as_of'].endswith('Z')


def test_pending_and_cancelled_order_quantities_not_approved_commitment(client):
    first,_,_=setup(client);data=report(client)
    assert sum(r['pending']['quantity_milli'] for r in data['rows'])==3500
    assert all(r['open']['quantity_milli']==0 for r in data['rows'])
    command(client,first,'cancel',{'reason':'未执行前取消本采购'})
    data=report(client);assert data['complete']
    assert sum(r['closed']['quantity_milli'] for r in data['rows'])==3500 and all(r['pending']['quantity_milli']==0 for r in data['rows'])


def test_report_tamper_source_difference_does_not_publish_whole_chart(client):
    order,_,_=setup(client);order=command(client,order,'approve');receive(client,order)
    with engine.begin() as db:db.execute(text('UPDATE procurement_receipts SET value_cents=value_cents+1 WHERE id=1'))
    data=report(client);assert not data['complete'] and not data['charts']
    assert any('原库存流水' in i['issue'] for i in data['issues'])
    assert data['metrics']['procurement_cohort_received_cents'] is None


def test_cost_visibility_store_scope_csv_and_unknown_table(client):
    setup(client);login(client,'inventory');data=report(client)
    assert not data['can_money'] and 'value_cents' not in data['rows'][0]['ordered']
    assert 'cents' not in str(data['metrics']) and '金额' not in str(data['tables'])
    assert client.get(API+'/export/procurement_cohort_lines').status_code==200
    assert client.get(API+'/export/vehicle_period_movements').status_code==404
    login(client,'service');assert client.get(API).status_code==403
    login(client,'admin');client.post('/api/stores',json={'code':'PC-OTHER','name':'其他合成店'});client.headers['X-Store-ID']='2';assert report(client)['rows']==[]
    client.headers['X-Store-ID']='all';data=report(client);assert len(data['rows'])==2 and all(r['route'] is None for r in data['tables']['procurement_cohort_lines']['rows'])
    assert client.post(API,json={}).status_code==405


def test_each_unit_chart_has_exact_population_and_formula_safe_csv(client):
    from tests.test_workflow import master
    _,_,supplier=setup(client)
    item=master(client,'items',{'sku':'=1+2','name':'@SUM(1,2)','unit':'升','reorder':'0','active':True})
    result=client.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,'supplier_id':supplier['id'],'reason':'不同单位合成订货','lines':[{'item_id':item['id'],'quantity_milli':1250,'unit_cost_cents':202}]})
    assert result.status_code==201,result.text
    data=report(client);assert data['complete'] and len(data['charts'])==2
    for chart in data['charts']:
        table=data['tables'][chart['table']]
        assert {r['values'][6] for r in table['rows']}=={chart['series'][0]['name']}
        assert chart['series'][0]['values'][0]==sum(r['ordered_milli'] for r in table['rows'])/1000
    response=client.get(API+'/export/procurement_cohort_lines')
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[-1][4:6]==["'=1+2","'@SUM(1,2)"]
