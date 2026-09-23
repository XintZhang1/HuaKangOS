"""Actual goods/service/original-cost conservation; no invented SKU allocation."""
import csv,io
from datetime import timedelta
import pytest
from sqlalchemy import text,select
from app.db import engine,SessionLocal,today
from app.flow_models import StockMove
from tests.conftest import login
from tests.test_workflow import evidence
from tests.test_retail import technician
from tests import test_retail as retail
from tests import test_addon_orders as addon
from tests import test_repair_orders as repair
API='/api/material-value'

def report(c,**params):
    r=c.get(API,params=params);assert r.status_code==200,r.text;return r.json()

def cashless_sale(c,install=False):
    items,customer,work,_=retail.setup(c,install);row=retail.dispatch(c,retail.authorize(c,retail.approve(c,retail.create(c,items,customer,work))))
    if install:row=retail.cmd(c,row,'install',{'evidence_id':evidence(c,row),'result':'按授权实际完成安装'})
    return row,items

def check_csv_charts(c,data,**params):
    for key,t in data['tables'].items():
        r=c.get(API+'/export/'+key,params=params);assert r.status_code==200,r.text
        assert list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))==[t['headers']]+[[str(v) for v in r['values']] for r in t['rows']]
    for chart in data['charts']:
        assert sum(chart['series'][0]['values'])==sum(r['amount_cents'] for r in data['tables'][chart['table']]['rows'])
        if chart['table']=='material_goods':assert sum(chart['series'][1]['values'])==sum(r['cost_cents'] for r in data['tables'][chart['table']]['rows'])

def check_combined(c):
    dedicated=report(c);combined=c.get('/api/flow/analytics');assert combined.status_code==200,combined.text
    combined=combined.json()
    for key,t in dedicated['tables'].items():assert combined['tables'][key]==t
    for chart in dedicated['charts']:assert next(x for x in combined['charts'] if x['id']==chart['id'])==chart

def test_actual_issue_before_acceptance_is_not_revenue_and_cash_not_required(client):
    row,items=cashless_sale(client,True);d=report(client)
    assert d['metrics']['material_source_net_cents']==0 and not d['tables']['material_goods']['rows']
    assert d['metrics']['material_unfulfilled_cost_cents']>0
    assert d['tables']['material_other_stock']['rows'] # purchase is actual inventory, never revenue
    row=retail.cmd(client,row,'accept',{'evidence_id':evidence(client,row)});d=report(client)
    assert d['metrics']['material_source_net_cents']==1200 and d['metrics']['material_unfulfilled_cost_cents']==0
    assert row['totals']['net_paid_cents']==0
    s=d['tables']['material_sources']['rows'][0]
    assert s['goods_cents']+s['service_cents']+s['unallocated_cents']==1200
    selected=report(client,item_id=items[0]['id']);assert len(selected['tables']['material_goods']['rows'])==1
    assert selected['metrics']['material_source_net_cents']==1200
    assert selected['metrics']['material_selected_goods_cents']<s['goods_cents']
    check_csv_charts(client,d)
    check_combined(client)

def test_retail_preaccept_return_and_later_cross_period_return_never_double_cost(client):
    row,items=cashless_sale(client,True);row,ret=retail.request_return(client,row,row['dispatches'][0],500)
    row=retail.ret_cmd(client,row,ret,'return_approve');row=retail.ret_cmd(client,row,ret,'return_receive')
    assert report(client)['metrics']['material_source_net_cents']==0
    row=retail.cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    yesterday=today()-timedelta(days=1)
    with engine.begin() as db:
        db.execute(text("UPDATE flow_cases SET data=json_set(data,'$.accepted_date',:day) WHERE id=:id"),dict(day=yesterday.isoformat(),id=row['id']))
        db.execute(text('UPDATE flow_stock_moves SET business_date=:day WHERE case_id=:id'),dict(day=yesterday.isoformat(),id=row['id']))
    row,ret=retail.request_return(client,row,row['dispatches'][0],500);row=retail.ret_cmd(client,row,ret,'return_approve');row=retail.ret_cmd(client,row,ret,'return_receive')
    current=report(client,date_from=today().isoformat(),date_to=today().isoformat());old=report(client,date_from=yesterday.isoformat(),date_to=yesterday.isoformat())
    assert current['metrics']['material_source_net_cents']==-row['return_postings'][-1]['goods_cents']
    assert current['metrics']['material_selected_goods_cost_cents']<0
    assert old['metrics']['material_source_net_cents']+current['metrics']['material_source_net_cents']==row['totals']['charge_cents']
    assert current['metrics']['material_unfulfilled_cost_cents']==0
    check_csv_charts(client,current,date_from=today().isoformat(),date_to=today().isoformat())

def test_addon_incremental_acceptance_and_original_return_keeps_frozen_lines(client):
    row,items,work,source,vin,account=addon.completed(client)
    extra=[dict(line_key='extra',item_id=items[1]['id'],work_item_id=work['id'],quantity_milli=1000,goods_unit_cents=100,installation_unit_cents=50)]
    row=addon.authorized(client,addon.approved(client,addon.quoted(client,row,items,work,extra=extra)))
    row=addon.accept(client,addon.quality(client,addon.install(client,addon.dispatch(client,row,vin,1000,'extra'))))
    d=report(client,source='addon');assert d['metrics']['material_source_net_cents']==1347
    assert len(d['tables']['material_goods']['rows'])==2
    row=addon.resolve(client,addon.resolve(client,addon.resolution(client,row,'return'),'resolution_approve'),'resolution_consent')
    row=addon.resolve(client,row,'return_receive',passed=True);d=report(client,source='addon')
    assert d['metrics']['material_source_net_cents']==1347-row['return_postings'][0]['goods_cents']
    assert d['metrics']['material_unfulfilled_cost_cents']==0
    check_csv_charts(client,d,source='addon')

def test_repair_internal_whole_order_never_allocated_to_material_and_current_wip(client):
    row,item,work,_=repair.setup(client);row=repair.ready(client,row,item,work)
    row=repair.allocate(client,row,[dict(payer_type='customer',amount_cents=10000,payer_name='客户'),dict(payer_type='internal',amount_cents=997,payer_name='内部责任')])
    assert report(client,source='repair')['metrics']['material_source_net_cents']==0
    assert report(client,source='repair')['metrics']['material_unfulfilled_cost_cents']>0
    row=repair.receive(client,row,row['allocations'][0],10000,retail.bank(client));row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    d=report(client,source='repair');s=d['tables']['material_sources']['rows'][0]
    assert s['goods_cents']+s['service_cents']==10997 and s['unallocated_cents']==-997 and s['amount_cents']==10000
    assert all(r['item_id'] is None for r in d['tables']['material_unallocated']['rows'])
    with SessionLocal() as db:assert s['cost_cents']==-sum(m.value_cents for m in db.scalars(select(StockMove).where(StockMove.case_id==row['id'])))
    assert d['metrics']['material_unfulfilled_cost_cents']==0
    check_csv_charts(client,d,source='repair')
    check_combined(client)

def test_role_store_aggregate_and_export_are_same_boundary(client):
    row,items=cashless_sale(client);retail.cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    for role in ('sales','service','inventory','technician'):
        login(client,role);assert client.get(API).status_code==403 and client.get(API+'/export/material_goods').status_code==403
    login(client,'admin');r=client.post('/api/stores',json={'code':'MV-OTHER','name':'物资对照另一店'});assert r.status_code==201,r.text
    client.headers['X-Store-ID']='2';assert report(client)['metrics']['material_source_net_cents']==0
    for param,value in [('case_id',row['id']),('item_id',items[0]['id'])]:assert client.get(API,params={param:value}).status_code==404
    client.headers['X-Store-ID']='all';d=report(client);assert d['metrics']['material_source_net_cents']==1000
    assert not d['options']['cases'] and all(not r.get('route') for t in d['tables'].values() for r in t['rows'])

def test_cap_date_and_inconsistent_actual_source_fail_closed(client,monkeypatch):
    row,items=cashless_sale(client)
    import app.inventory_report_common as common
    with monkeypatch.context() as m:
        m.setattr(common,'LIMIT',1);r=client.get(API);assert r.status_code==422 and '截断' in r.text
    assert client.get(API,params={'date_from':today().isoformat(),'date_to':(today()-timedelta(days=1)).isoformat()}).status_code==422
    with engine.begin() as db:db.execute(text('UPDATE retail_dispatches SET value_cents=value_cents+1 WHERE case_id=:id'),{'id':row['id']})
    r=client.get(API);assert r.status_code==409 and '原领退料' in r.text
    assert client.get(API+'/export/material_goods').status_code==409


def test_benefit_discount_and_aftercare_original_return_preserve_initial_period(client,tmp_path):
    from tests import test_group_aftercare as ga,test_group_benefits as benefits,test_aftercare as aftercare
    row,data,member,_,work=ga.source(client)
    rule=benefits.rule(client,'package',allowed_store_ids=[1],service_code=work['code'],credit_cents_per_unit=1000,sale_cents_per_unit=700,settlement_cents_per_unit=700)
    wallet=benefits.issuance(client,member,data,rule,1);held=benefits.reserve(client,member,data,wallet);capture=benefits.capture(client,member,data,wallet,held)
    row=repair.receive(client,row,repair.detail(client,row)['allocations'][0],9997,data['account_id']);row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    before=report(client,source='repair');assert before['metrics']['material_source_net_cents']==10697
    assert before['tables']['material_sources']['rows'][0]['unallocated_cents']==-300
    req=aftercare.create(client,row);req=aftercare.plan(client,req,1000,[{'kind':'benefit','original_id':capture['entry_id'],'units':1}])
    aftercare.applied(client,aftercare.confirmed(client,aftercare.approved(client,req)))
    d=report(client,source='repair');assert d['metrics']['material_source_net_cents']==9997
    assert sorted(r['amount_cents'] for r in d['tables']['material_unallocated']['rows'])==[-700,-300]
    assert before['metrics']['material_selected_goods_cents']==d['metrics']['material_selected_goods_cents']
    assert before['metrics']['material_selected_goods_cost_cents']==d['metrics']['material_selected_goods_cost_cents']
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.backup_integrity import validate_sqlite
    restored_path=tmp_path/'restored.sqlite'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(restored_path) as restored:
        original.backup(restored);validate_sqlite(restored)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from types import SimpleNamespace
    from app.tenancy import set_scope
    from app.material_value_analytics import build_material_values
    restored_engine=create_engine('sqlite:///'+restored_path.as_posix())
    try:
        with Session(restored_engine) as db:
            set_scope(db,[1],1)
            after=build_material_values(db,SimpleNamespace(role='finance'),source='repair')
            assert after['tables']==d['tables'] and after['metrics']==d['metrics']
    finally:restored_engine.dispose()
    check_csv_charts(client,d,source='repair')
    check_combined(client)


def test_actual_claim_reduction_is_unallocated_and_never_double_counts_cash_refund(client):
    from tests import test_claims as claims
    source,account,payer=claims.completed(client,True);source=claims.receive(client,source,source['allocations'][1],4997,account)
    row,_=claims.create(client,source,payer=payer);row=claims.external(client,claims.assessed(client,row,4997),3000,'partial')
    payment=next(p for p in row['source_payments'] if p['allocation_id']==source['allocations'][1]['id'])
    row=claims.cmd(client,row,'resolution',{'internal_bearer':'门店承担核赔差额','refunds':[{'original_id':payment['id'],'amount_cents':1997}],'reason':'原维修实际核赔差额','evidence_id':claims.proof(client,row)})
    row=claims.reviewed(client,row,'resolution_approve');row=claims.cash(client,row,'thirdparty_refund',1997,account,original_id=payment['id'])
    assert report(client,source='repair')['metrics']['material_source_net_cents']==10997
    claims.cmd(client,row,'resolution_apply',{'evidence_id':claims.proof(client,row,True)})
    d=report(client,source='repair');assert d['metrics']['material_source_net_cents']==9000
    assert [r['amount_cents'] for r in d['tables']['material_unallocated']['rows']]==[-1997]
    assert d['tables']['material_unallocated']['rows'][0]['source_table']=='claims_responsibility_entries'
    assert d['tables']['material_sources']['rows'][0]['goods_cents']+d['tables']['material_sources']['rows'][0]['service_cents']==10997
    check_csv_charts(client,d,source='repair')


def test_authorized_stop_fee_without_material_is_service_only(client):
    row,item,work,_=repair.setup(client);row=repair.authorize(client,repair.quote(client,row,item,work));row=repair.cmd(client,row,'start',{'result':'按授权开始检查'})
    row=repair.issue(client,row,2000);original=row['stock'][0]
    row=repair.cmd(client,row,'quote',{'purpose':'stop','retained_amount_cents':1000,'reason':'客户要求停止并同意原检查保留费','lines':[]})
    row=repair.authorize(client,row);row=repair.return_material(client,row,original,2000)
    row=repair.cmd(client,row,'finish',{'result':'实际检查完成，未用配件原退'});row=repair.cmd(client,row,'quality',{'passed':True,'result':'停工交接检查通过','evidence_id':evidence(client,row)})
    row=repair.allocate(client,row);row=repair.receive(client,row,row['allocations'][0],1000,retail.bank(client));repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    d=report(client,source='repair');assert d['metrics']['material_source_net_cents']==1000
    assert not d['tables']['material_goods']['rows'] and d['metrics']['material_selected_goods_cost_cents']==0
    assert d['tables']['material_services']['rows'][0]['amount_cents']==1000
    assert d['metrics']['material_unfulfilled_cost_cents']==0


def test_fractional_bundle_uses_frozen_allocations_not_zero_price_sentinel(client):
    from tests import test_retail_bundles as bundles
    items,customer,work,_=retail.setup(client,True);rule=bundles.publish(client,items,work)
    row=bundles.sale(client,rule,customer,2);row=retail.dispatch(client,retail.authorize(client,retail.approve(client,row)))
    row=retail.cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'真实按原套餐完成安装'})
    row=retail.cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    d=report(client);goods=d['tables']['material_goods']['rows']
    assert [r['amount_cents'] for r in goods]==[1816,2] and [r['quantity_milli'] for r in goods]==[2000,666]
    assert d['tables']['material_services']['rows'][0]['amount_cents']==182
    assert d['metrics']['material_source_net_cents']==2000
    check_combined(client)
