"""Original B08/B09/B10/B15 report contracts from registered synthetic workflows.

Legacy null-cost/state fixtures are explicitly report-source boundary fixtures,
not claims that an employee can create those final states through current APIs.
"""
import csv,io,uuid
from datetime import timedelta,datetime,timezone
from decimal import Decimal
import pytest
from sqlalchemy import select
from app.db import today,SessionLocal
from app.models import User,Repair,Sale,Vehicle
from app.flow_models import Case,Customer,FlowEvent,Task
from tests.conftest import login
from tests.test_workflow import create,action,detail,evidence,master,order,account,approved_doc
from tests.test_workflow_extended import add_user


def report(c,start=None,end=None):
    response=c.get('/api/flow/analytics',params={'date_from':(start or today()).isoformat(),'date_to':(end or today()).isoformat()})
    assert response.status_code==200,response.text;return response.json()


def chart(data,key):return next(c for c in data['charts'] if c['id']==key)
def cents(value):return int(Decimal(str(value))*100)


def exported(c,data,key,start=None,end=None):
    response=c.get('/api/flow/analytics/export',params={'dataset':key,'date_from':(start or today()).isoformat(),'date_to':(end or today()).isoformat()})
    assert response.status_code==200,response.text
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    def safe(v):
        s='' if v is None else str(v)
        return "'"+s if not isinstance(v,(int,float)) and s.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else s
    assert rows==[data['tables'][key]['headers']]+[[safe(v) for v in r['values']] for r in data['tables'][key]['rows']]
    return rows[1:]


def lead(c,name):
    return create(c,'lead',dict(customer_name='接待'+name,customer_phone='138'+str(int(uuid.uuid4().hex[:7],16)).zfill(8)[-8:],source='展厅到店'))


def assigned(c,row):
    with SessionLocal() as db:uid=db.scalar(select(User.id).where(User.username=='sales'))
    return action(c,row,'assign',{'assignee_id':uid})


def intended(c,row):return action(c,row,'intent',{'need':'核实预算和用车需求','due_date':today().isoformat()})
def reserved(c,row):return action(c,row,'reserve',{'model':'测试车型','amount':'100.00','delivery_due':today().isoformat()})


def test_hk004_original_intent_handoff_second_sales_continues_without_rewriting_history(client):
    second=add_user('sales','second-sales-original');row=assigned(client,lead(client,'意向交接'))
    login(client,'sales');row=intended(client,row);before=detail(client,row)
    login(client,'manager');task=next(t for t in detail(client,row)['tasks'] if t['key']=='follow' and t['status']=='open')
    payload={'version':task['version'],'assignee_id':second,'reason':'本人核实交由第二销售继续原意向'}
    url=f"/api/flow/tasks/{task['id']}/assign";changed=client.post(url,json=payload)
    assert changed.status_code==200,changed.text
    assert client.post(url,json=payload).status_code==409
    row=detail(client,row);assert row['owner_id']==second and row['customer_id']==before['customer_id']
    assert row['data']['source']==before['data']['source'] and row['data']['need']==before['data']['need']
    with SessionLocal() as db:
        assert db.get(Customer,row['customer_id']).owner_id==second
        assert len(list(db.scalars(select(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='reassign'))))==1
    login(client,'sales')
    assert client.post(f"/api/flow/cases/{row['id']}/actions/follow",json={'version':row['version'],'request_id':uuid.uuid4().hex,'values':{'result':'旧负责人不能抢办','due_date':today().isoformat()}}).status_code in {403,404,409}
    login(client,'second-sales-original');row=action(client,row,'follow',{'result':'第二销售实际继续核对预算','due_date':today().isoformat()});row=reserved(client,row)
    after=detail(client,row);assert row['state']=='converted' and len(after['children'])==1
    assert after['children'][0]['customer_id']==before['customer_id'] and after['children'][0]['parent_id']==row['id']
    with SessionLocal() as db:
        events=list(db.scalars(select(FlowEvent.action).where(FlowEvent.case_id==row['id'])))
        assert events.count('intent')==events.count('reassign')==events.count('reserve')==1
    login(client);store=client.post('/api/stores',json={'code':'OTHER-INTENT','name':'其他意向门店'}).json()['id'];client.headers['X-Store-ID']=str(store)
    assert client.post(url,json={**payload,'version':changed.json()['version']}).status_code==404


def test_hk134_135_nonempty_same_reception_cohort_reopen_cross_period_and_scope_csv(client,monkeypatch):
    from app import flow_engine
    pending=lead(client,'未转');intent=intended(client,assigned(client,lead(client,'仅意向')))
    converted=reserved(client,intended(client,assigned(client,lead(client,'本期订单'))))
    reopened=intended(client,assigned(client,lead(client,'关闭重开')))
    reopened=action(client,reopened,'close',{'reason':'客户暂缓购车','no_contact':False})
    reopened=action(client,reopened,'reopen',{'reason':'客户确认继续原需求','due_date':today().isoformat()})
    action(client,reopened,'follow',{'result':'原意向再次沟通不增加分母','due_date':today().isoformat()})
    yesterday=today()-timedelta(days=1)
    with monkeypatch.context() as patch:
        patch.setattr(flow_engine,'today',lambda:yesterday);prior=lead(client,'前期接待本期转')
    prior=reserved(client,intended(client,assigned(client,prior)))
    data=report(client);assert data['metrics']['cohort_receptions']==4 and data['metrics']['cohort_orders']==1 and data['metrics']['cohort_rate']==25
    assert chart(data,'cohort')['series'][0]['values']==[4,3,1]
    rows=exported(client,data,'leads');assert len(rows)==4 and sum(r[5]=='是' for r in rows)==3 and sum(r[6]=='是' for r in rows)==1
    assert {r['route']['id'] for r in data['tables']['leads']['rows']}=={pending['id'],intent['id'],converted['id'],reopened['id']}
    old=report(client,yesterday,yesterday);assert chart(old,'cohort')['series'][0]['values']==[1,1,1]
    assert old['metrics']['cohort_rate']==100 and len(exported(client,old,'leads',yesterday,yesterday))==1
    empty=report(client,yesterday-timedelta(days=1),yesterday-timedelta(days=1));assert empty['metrics']['cohort_rate'] is None and chart(empty,'cohort')['series'][0]['values']==[0,0,0]
    store=client.post('/api/stores',json={'code':'OTHER-COHORT','name':'其他接待门店'}).json()['id'];client.headers['X-Store-ID']=str(store)
    other=lead(client,'他店');local=report(client);assert chart(local,'cohort')['series'][0]['values']==[1,0,0]
    assert exported(client,local,'leads')[0][0]==other['number']
    client.headers['X-Store-ID']='1';assert report(client)['metrics']['cohort_receptions']==4
    client.headers['X-Store-ID']='all';combined=report(client);assert chart(combined,'cohort')['series'][0]['values']==[5,3,1]
    assert len(exported(client,combined,'leads'))==5


def test_hk147_historical_repair_rows_and_progress_chart_share_population(client):
    # Explicit historical report-source fixture only, not a current workflow.
    with SessionLocal() as db:
        admin=db.scalar(select(User.id).where(User.username=='admin'))
        db.add(Repair(doc_no='ORIGINAL-LEGACY-REPAIR',business_date=today(),approval_state='approved',created_by=admin,
            plate_number='合成旧修',customer_name='合成旧历史',service_advisor='合成历史顾问',repair_type='repair',repair_stage='completed',completion_date=today(),
            labor_amount_cents=10000,parts_amount_cents=0,discount_cents=0,cost_amount_cents=3000));db.commit()
    data=report(client);rows=exported(client,data,'repairs')
    assert len(rows)==data['metrics']['new_repairs']==1
    assert sum(chart(data,'repair_state')['series'][0]['values'])==len(rows)


def test_hk157_160_report_permission_bad_period_and_untruncated_upper_bound(client,monkeypatch):
    row=order(client,'100.00');row=action(client,row,'approve')
    action(client,row,'receive',{'amount':'30.00','account_id':account(client),'reference':'SOURCE-CASH','evidence_id':evidence(client,row,'receipt')})
    data=report(client);assert data['metrics']['receivable_cents']==7000 and data['metrics']['cash_in_cents']==3000
    assert sum(r['amount_cents'] for r in data['tables']['receivables']['rows'])==7000
    assert sum(cents(r[6]) for r in exported(client,data,'receivables'))==7000
    assert sum(cents(r[5]) for r in exported(client,data,'cash'))==3000
    assert sum(chart(data,'cash_trend')['series'][0]['values'])==3000
    assert sum(chart(data,'cash_category')['series'][0]['values'])==3000
    assert client.get('/api/flow/analytics',params={'date_from':today().isoformat(),'date_to':(today()+timedelta(days=1)).isoformat()}).status_code==422
    assert client.get('/api/flow/analytics/export?dataset=missing').status_code==422
    from app import flow_analytics
    monkeypatch.setattr(flow_analytics,'LIMIT',0)
    assert client.get('/api/flow/analytics').status_code==422
    assert client.get('/api/flow/analytics/export?dataset=cash').status_code==422
    login(client,'inventory')
    assert client.get('/api/flow/analytics').status_code==403 and client.get('/api/flow/analytics/export?dataset=cash').status_code==403


def business_clock(monkeypatch,day):
    """Drive real actions on an earlier synthetic business day, no final-state SQL."""
    from app import db as database
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            stamp=datetime(day.year,day.month,day.day,4,tzinfo=timezone.utc)
            return stamp.astimezone(tz) if tz is not None else stamp.replace(tzinfo=None)
    monkeypatch.setattr(database,'datetime',Clock)


def delivered_vehicle(c):
    """Actual procurement→VIN receipt→v4 quote→signature→cash→physical delivery."""
    from tests import test_vehicle_procurement as purchase,test_vehicle_catalog as catalog,test_sales_quotes as quotes
    brand,series,model=catalog.setup(c);catalog.classify(c,series,model)
    values,location=purchase.setup(c,1);values['lines'][0]['model_id']=model['id']
    original=purchase.create(c,values)
    original=purchase.command(c,original,'approve',{'prices':[{'line_id':original['lines'][0]['id'],'unit_cost_cents':8000,'list_price_cents':10000}],'evidence_id':evidence(c,original,'invoice')})
    original=purchase.ship(c,original);original=purchase.receive(c,original,location);car=original['receipts'][0]['vehicle_id']
    customer=master(c,'customers',{'name':'车辆毛差实际路径合成客户','phone':'13900006666','contact_allowed':True,'note':''})
    quote={'model_id':model['id'],'model_version':model['version'],'amount_cents':10000,'delivery_due':today().isoformat(),
        'valid_until':(today()+timedelta(days=7)).isoformat(),'addon':False,'insurance':False,'agency':False,
        'terms':'车款独立约定，本单没有代收或服务费','reason':'客户核对实际本车及本次购车条件'}
    response=c.post('/api/sales-quotes/orders',json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'quote':quote})
    assert response.status_code==201,response.text;row=response.json()
    row=quotes.ready(c,row,car);row,account=quotes.pay(c,row,10000);row=quotes.inspect(c,row)
    row=action(c,row,'dispatch',{'evidence_id':evidence(c,row)})
    handover=approved_doc(c,row,'handover');row=action(c,row,'deliver',{'evidence_id':evidence(c,row,'signed_handover',handover)})
    return row,account,location


def test_hk137_138_142_actual_vehicle_delivery_margin_and_later_original_return_use_separate_periods(client,monkeypatch):
    from tests import test_aftercare as after,test_vehicle_operations as operations
    day=today();prior=day-timedelta(days=1)
    with monkeypatch.context() as patch:
        business_clock(patch,prior);login(client);row,bank,location=delivered_vehicle(client)
    login(client)
    old=report(client,prior,prior)
    assert old['metrics']['new_orders']==old['metrics']['delivery_count']==1
    assert old['metrics']['delivery_cents']==10000 and old['metrics']['delivery_margin_cents']==2000 and old['metrics']['delivery_missing_cost']==0
    assert sum(chart(old,'orders_trend')['series'][0]['values'])==len(exported(client,old,'orders',prior,prior))==1
    assert sum(chart(old,'delivery')['series'][0]['values'])==sum(cents(r[4]) for r in exported(client,old,'deliveries',prior,prior))==10000
    assert sum(cents(r[6]) for r in exported(client,old,'deliveries',prior,prior))==2000
    today_report=report(client);assert today_report['metrics']['delivery_cents']==today_report['metrics']['new_orders']==0
    request=after.create(client,row,'vehicle_return');request=after.confirmed(client,after.approved(client,after.plan(client,request,10000)))
    operation=operations.get(client,{'id':request['vehicle_return']['operation_case_id']})
    operation=operations.act(client,operation,'intake',{'location_id':location})
    operation=operations.act(client,operation,'inspect',{'outcome':'pass','findings':'原VIN返店实车检查合格'})
    operation=operations.act(client,operation,'disposition',{'inspection_id':operation['inspections'][-1]['id'],'decision':'release'})
    operation=operations.act(client,operation,'release',{'location_id':location})
    request=after.applied(client,request);after.refund(client,request,bank,10000)
    current=report(client);original_period=report(client,prior,prior)
    assert original_period['metrics']['delivery_cents']==10000 and original_period['metrics']['delivery_margin_cents']==2000
    assert current['metrics']['delivery_cents']==0 and current['metrics']['vehicle_delivery_net_cents']==-10000
    assert current['metrics']['cash_in_cents']==0 and current['metrics']['cash_out_cents']==10000
    assert sum(chart(current,'aftercare_adjustments')['series'][0]['values'])==-10000
    assert sum(cents(r[5].lstrip("'")) for r in exported(client,current,'business_net_facts'))==-10000
    assert sum(cents(r[5]) for r in exported(client,current,'cash'))==10000
    assert sum(chart(current,'cash_trend')['series'][1]['values'])==10000
    assert sum(chart(current,'cash_category')['series'][0]['values'])==-10000
    with SessionLocal() as db:
        original=db.get(Vehicle,row['vehicle_id']);replacement=db.get(Vehicle,operation['received_vehicle_id'])
        assert original.vin==replacement.vin and original.inventory_generation!=replacement.inventory_generation
        assert db.get(Case,row['id']).cost_cents==8000
    assert current['metrics']['inventory_cost_cents']==8000


def test_hk142_historical_unknown_cost_keeps_unknown_and_original_snapshot(client):
    # Source-boundary fixture: preserved legacy approved sales can lack a cost
    # snapshot. Current API sales above always obtain one from a real receipt.
    with SessionLocal() as db:
        admin=db.scalar(select(User.id).where(User.username=='admin'));cars=[]
        for generation,amount,cost in [(1,10000,8000),(2,20000,None)]:
            car=Vehicle(doc_no='HIST-VIN-'+str(generation),business_date=today(),approval_state='approved',created_by=admin,
                vin='LHGCM82633A12345'+str(generation),brand='合成历史品牌',model='合成历史车型',purchase_cost_cents=9999,list_price_cents=amount)
            db.add(car);db.flush();cars.append(car.id)
            db.add(Sale(doc_no='HIST-SALE-'+str(generation),business_date=today(),approval_state='approved',created_by=admin,
                vehicle_id=car.id,active_vehicle_id=car.id,customer_name='合成历史客户',salesperson='合成历史销售',sale_stage='delivered',delivery_date=today(),
                contract_amount_cents=amount,purchase_cost_snapshot_cents=cost))
        db.commit()
    data=report(client);rows=exported(client,data,'deliveries')
    assert data['metrics']['delivery_count']==2 and data['metrics']['delivery_cents']==30000
    assert data['metrics']['delivery_missing_cost']==1 and data['metrics']['delivery_margin_cents'] is None
    assert rows[0][5:] == ['80.00','20.00'] and rows[1][5:] == ['—','成本待核对']
    assert sum(chart(data,'delivery')['series'][0]['values'])==sum(cents(r[4]) for r in rows)==30000
    # Later current inventory price is not evidence for the old snapshot.
    with SessionLocal() as db:db.get(Vehicle,cars[0]).purchase_cost_cents=12345;db.commit()
    assert exported(client,report(client),'deliveries')==rows


def test_hk137_138_147_157_160_actual_repair_cohort_settlement_current_receivables_and_cash_share_csv(client,monkeypatch):
    from tests import test_repair_orders as repairs,test_retail as retail,test_procurement as purchase
    day=today();prior=day-timedelta(days=1)
    with monkeypatch.context() as patch:
        business_clock(patch,prior);login(client)
        row,item,work,customer=repairs.setup(client);row=repairs.ready(client,row,item,work)
        insurer=repairs.typed(client,'insurers',{'code':'ORIGINAL-INSURER','name':'合成原承担保险公司'})
        manufacturer=master(client,'references',{'category':'厂家','name':'合成原承担厂家','detail':'独立承担','active':True})
        row=repairs.allocate(client,row,[{'payer_type':'customer','amount_cents':1997},{'payer_type':'insurer','payer_id':insurer['id'],'amount_cents':3000},
            {'payer_type':'manufacturer','payer_id':manufacturer['id'],'amount_cents':4000},{'payer_type':'internal','payer_name':'原内部责任','amount_cents':2000}])
        bank=purchase.bank(client);row=repairs.receive(client,row,row['allocations'][0],1000,bank)
    login(client);row=repairs.receive(client,row,row['allocations'][0],997,bank)
    row=repairs.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    assert row['state']=='credit_open' and row['revenue_cents']==8997 and row['receivable_cents']==7000
    pending=repairs.create(client,customer)
    items,retail_customer,_,_=retail.setup(client);sale=retail.authorize(client,retail.approve(client,retail.create(client,items,retail_customer)))
    sale=retail.pay(client,sale,400,bank);assert sale['totals']['receivable_cents']==600
    vehicle=action(client,order(client,'100.00',customer_id=customer['id'],customer_name=customer['name'],customer_phone=customer['phone']),'approve')
    action(client,vehicle,'receive',{'amount':'25.00','account_id':bank,'reference':'ORIGINAL-VEHICLE-PARTIAL','evidence_id':evidence(client,vehicle,'receipt')})
    data=report(client);tables=data['tables'];metrics=data['metrics']
    assert metrics['new_repairs']==1 and sum(chart(data,'repair_state')['series'][0]['values'])==1
    assert exported(client,data,'repairs')[0][0]==pending['number']
    settlements=exported(client,data,'repair_settlements');assert len(settlements)==1 and settlements[0][0]==row['number']
    assert sum(cents(r[4]) for r in settlements)==metrics['repair_cents']==sum(chart(data,'repair_value')['series'][0]['values'])==8997
    current=exported(client,data,'receivables');assert sum(cents(r[6]) for r in current)==metrics['receivable_cents']==15100
    by_source={number:sum(cents(r[6]) for r in current if r[0]==number) for number in (row['number'],sale['number'],vehicle['number'])}
    assert by_source=={row['number']:7000,sale['number']:600,vehicle['number']:7500}
    assert not any(r[2]=='原内部责任' for r in current)
    cash=exported(client,data,'cash');assert sum(cents(r[5]) for r in cash)==metrics['cash_in_cents']==3897
    assert metrics['cash_out_cents']==0 and len(cash)==3
    assert sum(chart(data,'cash_trend')['series'][0]['values'])==sum(chart(data,'cash_category')['series'][0]['values'])==3897
    assert sum(chart(data,'orders_trend')['series'][0]['values'])==len(exported(client,data,'orders'))==metrics['new_orders']==1
    old=report(client,prior,prior);assert old['metrics']['new_repairs']==1 and old['metrics']['repair_cents']==0
    assert sum(chart(old,'repair_state')['series'][0]['values'])==len(exported(client,old,'repairs',prior,prior))==1
    assert exported(client,old,'repairs',prior,prior)[0][4]=='已交车待月结'
    assert exported(client,old,'repair_settlements',prior,prior)==[]
    assert old['metrics']['cash_in_cents']==sum(cents(r[5]) for r in exported(client,old,'cash',prior,prior))==1000
    # Current receivables are deliberately invariant under period selection.
    assert old['metrics']['receivable_cents']==metrics['receivable_cents']
    assert exported(client,old,'receivables',prior,prior)==current


def test_hk157_160_nonempty_store_cash_receivables_and_readonly_aggregate_same_original_population(client):
    first=action(client,order(client,'100.00'),'approve')
    first=action(client,first,'receive',{'amount':'30.00','account_id':account(client),'reference':'ORIGINAL-STORE-ONE','evidence_id':evidence(client,first,'receipt')})
    store=client.post('/api/stores',json={'code':'REPORT-SECOND','name':'报表第二门店'}).json()['id'];client.headers['X-Store-ID']=str(store)
    second=action(client,order(client,'200.00'),'approve')
    second=action(client,second,'receive',{'amount':'50.00','account_id':account(client),'reference':'ORIGINAL-STORE-TWO','evidence_id':evidence(client,second,'receipt')})
    local=report(client);assert local['metrics']['receivable_cents']==15000 and local['metrics']['cash_in_cents']==5000
    assert exported(client,local,'receivables')[0][0]==second['number']
    assert 'ORIGINAL-STORE-ONE' not in str(exported(client,local,'cash'))
    client.headers['X-Store-ID']='1';local=report(client)
    assert local['metrics']['receivable_cents']==7000 and local['metrics']['cash_in_cents']==3000
    assert exported(client,local,'receivables')[0][0]==first['number']
    assert 'ORIGINAL-STORE-TWO' not in str(exported(client,local,'cash'))
    client.headers['X-Store-ID']='all';combined=report(client)
    assert combined['metrics']['receivable_cents']==sum(cents(r[6]) for r in exported(client,combined,'receivables'))==22000
    assert combined['metrics']['cash_in_cents']==sum(cents(r[5]) for r in exported(client,combined,'cash'))==8000
    assert sum(chart(combined,'cash_trend')['series'][0]['values'])==sum(chart(combined,'cash_category')['series'][0]['values'])==8000
    assert sum(chart(combined,'orders_trend')['series'][0]['values'])==len(exported(client,combined,'orders'))==2
    assert client.post(f"/api/flow/cases/{first['id']}/actions/receive",json={'version':first['version'],'request_id':uuid.uuid4().hex,
        'values':{'amount':'1.00','account_id':1,'reference':'READONLY-MUST-REFUSE','evidence_id':1}}).status_code==409
