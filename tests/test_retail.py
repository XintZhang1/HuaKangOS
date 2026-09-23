"""Retail reservations, actual fulfillment, original returns, and cash conservation."""
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal
from app.models import User,UserStore,Store,CashEntry
from app.flow_models import Case,Item,StockMove,PaymentLink
from app.retail_models import RetailLine,RetailReservation,RetailDispatch,RetailReturnPosting
from app.retail_service import reserved_quantity
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import master,evidence
from tests.test_procurement import setup as purchase_setup,command as purchase_command,receive as purchase_receive,bank,return_request as purchase_return,return_action as purchase_return_action
from tests.test_repair_orders import typed

@pytest.fixture(autouse=True)
def technician():
    with SessionLocal() as db:
        user=User(username='technician',display_name='精品安装技师',role='technician',password_hash=PASSWORD_HASH,must_change_password=False)
        db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit()
def setup(c,install=False):
    purchase,items,_=purchase_setup(c);purchase=purchase_command(c,purchase,'approve');purchase=purchase_receive(c,purchase)
    customer=master(c,'customers',{'name':'精品合成客户','phone':'13900000091','contact_allowed':True,'note':''})
    work=typed(c,'work_items',{'code':'INSTALL-'+uuid.uuid4().hex[:8],'name':'精品安装','billing_unit':'job','standard_fee_cents':500}) if install else None
    return items,customer,work,purchase
def create(c,items,customer,work=None,qty=2000,discount=3,status=201,**extra):
    r=c.post('/api/retail/orders',json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'discount_cents':discount,
        'lines':[{'item_id':items[0]['id'],'quantity_milli':qty,'unit_price_cents':500,'work_item_id':work['id'] if work else None,'installation_unit_price_cents':100 if work else 0},
                 {'item_id':items[1]['id'],'quantity_milli':1000,'unit_price_cents':3}],**extra})
    assert r.status_code==status,r.text;return r.json()
def detail(c,row):
    r=c.get('/api/retail/orders/'+str(row['id']));assert r.status_code==200,r.text;return r.json()
def cmd(c,row,key,values=None,status=200,version=None,request_id=None):
    r=c.post(f"/api/retail/orders/{row['id']}/actions/{key}",json={'request_id':request_id or uuid.uuid4().hex,'version':detail(c,row)['version'] if version is None else version,'values':values or {}})
    assert r.status_code==status,r.text;return r.json()
def approve(c,row):return cmd(c,row,'approve',{'minimum_total_cents':0,'reason':'主管复核当前商品报价','allow_below_minimum':False})
def authorize(c,row):return cmd(c,row,'authorize',{'revision':1,'evidence_id':evidence(c,row,'authorization')})
def dispatch(c,row):return cmd(c,row,'dispatch',{'evidence_id':evidence(c,row)})
def pay(c,row,amount,account):return cmd(c,row,'receive',{'amount_cents':amount,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')})
def request_return(c,row,source,quantity):
    row=cmd(c,row,'return_request',{'reason':'客户要求退回原商品','evidence_id':evidence(c,row),'lines':[{'dispatch_id':source['id'],'quantity_milli':quantity}]})
    return row,row['returns'][-1]
def ret_cmd(c,row,ret,key,passed=True,**kw):
    current=next(x for x in detail(c,row)['returns'] if x['id']==ret['id'])
    values={'return_id':ret['id'],'return_version':current['version']}
    if key in {'return_approve','return_cancel','return_reject'}:values['reason']='核对原单退货事项'
    else:
        values.update(evidence_id=evidence(c,row,'inspection'),result='本人实际检查处理商品')
        if key=='return_receive':values['passed']=passed
    return cmd(c,row,key,values,**kw)
def refund(c,row,payment,account,amount,**kw):return cmd(c,row,'refund',{'original_payment_id':payment['id'],'account_id':account,'amount_cents':amount,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')},**kw)

def test_sale_install_partial_return_retained_service_and_original_cash(client):
    items,customer,work,purchase=setup(client,True);row=create(client,items,customer,work)
    assert row['amount_cents']==1200 and sum(l['goods_cents']+l['installation_cents'] for l in row['lines'])==1200
    with SessionLocal() as db:
        assert reserved_quantity(db,items[0]['id'])==2000
        assert db.get(Item,items[0]['id']).quantity_milli==2500
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
    row=authorize(client,approve(client,row));account=bank(client);row=pay(client,row,500,account);row=pay(client,row,700,account)
    row=dispatch(client,row);source=row['dispatches'][0]
    cmd(client,row,'accept',{'evidence_id':evidence(client,row)},409)
    row=cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'实际安装并检查通过'})
    row=cmd(client,row,'accept',{'evidence_id':evidence(client,row)});assert row['state']=='completed'
    row,ret=request_return(client,row,source,500);row=ret_cmd(client,row,ret,'return_approve')
    row=ret_cmd(client,row,ret,'return_receive',False)
    assert row['totals']['refund_due_cents']==0 and row['returns'][0]['status']=='rectification'
    with SessionLocal() as db:assert db.get(Item,items[0]['id']).quantity_milli==500
    ret_cmd(client,row,ret,'return_receive',status=409);ret_cmd(client,row,ret,'return_cancel',status=409)
    row=ret_cmd(client,row,ret,'return_rectify');row=ret_cmd(client,row,ret,'return_receive')
    assert row['return_postings'][0]['retained_cents']==50
    amount=row['totals']['refund_due_cents'];assert amount==250
    row=refund(client,row,row['payments'][0],account,amount);assert row['state']=='completed'
    row,ret=request_return(client,row,source,1500);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
    refund(client,row,row['payments'][0],account,251,status=409)
    row=refund(client,row,row['payments'][0],account,250);row=refund(client,row,row['payments'][1],account,row['totals']['refund_due_cents'])
    assert sum(p['goods_cents'] for p in row['return_postings'])==row['lines'][0]['goods_cents']
    assert sum(p['retained_cents'] for p in row['return_postings'])==row['lines'][0]['installation_cents']
    with SessionLocal() as db:
        assert (db.get(Item,items[0]['id']).quantity_milli,db.get(Item,items[0]['id']).inventory_value_cents)==(2500,308)
        assert reserved_quantity(db,items[0]['id'])==0
        assert sum(x.value_cents for x in db.scalars(select(StockMove).where(StockMove.case_id==row['id'],StockMove.item_id==items[0]['id'])))==0
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry).where(CashEntry.doc_no.like('WF-%'))))==row['totals']['charge_cents']

def test_uninstalled_return_reduces_fee_without_inventing_refund(client):
    items,customer,work,_=setup(client,True);row=dispatch(client,authorize(client,approve(client,create(client,items,customer,work))))
    row,ret=request_return(client,row,row['dispatches'][0],2000);row=ret_cmd(client,row,ret,'return_approve')
    cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'不得抢先改变费用'},409)
    row=ret_cmd(client,row,ret,'return_receive');assert row['totals']['retained_installation_cents']==0 and row['totals']['refund_due_cents']==0
    assert row['totals']['charge_cents']==row['lines'][1]['goods_cents']
    row=cmd(client,row,'accept',{'evidence_id':evidence(client,row)});row=pay(client,row,row['totals']['receivable_cents'],bank(client));assert row['state']=='completed'

def test_cancel_reserved_prepaid_order_refunds_without_stock(client):
    items,customer,_,_=setup(client);row=create(client,items,customer);row=approve(client,row);account=bank(client);row=pay(client,row,100,account)
    row=cmd(client,row,'cancel',{'reason':'未实际出库取消订单'});assert row['state']=='settling' and row['totals']['refund_due_cents']==100
    cmd(client,row,'receive',{'amount_cents':1,'account_id':account,'reference':'cancel-payment','evidence_id':evidence(client,row,'receipt')},409)
    row=refund(client,row,row['payments'][0],account,100);assert row['state']=='cancelled'
    with SessionLocal() as db:
        assert reserved_quantity(db,items[0]['id'])==0
        assert db.scalar(select(func.count()).select_from(StockMove).where(StockMove.case_id==row['id']))==0

def test_failed_return_rejection_requires_physical_handback_without_stock_or_refund(client):
    items,customer,_,_=setup(client);row=dispatch(client,authorize(client,approve(client,create(client,items,customer))))
    row,ret=request_return(client,row,row['dispatches'][0],1000);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive',False)
    row=ret_cmd(client,row,ret,'return_reject');assert row['returns'][0]['status']=='handback'
    cmd(client,row,'accept',{'evidence_id':evidence(client,row)},409)
    row=ret_cmd(client,row,ret,'return_handback');assert row['returns'][0]['status']=='rejected'
    assert not row['return_postings'] and row['totals']['refund_due_cents']==0 and row['totals']['charge_cents']==1000
    cmd(client,row,'accept',{'evidence_id':evidence(client,row)})

def test_stock_reservation_blocks_procurement_return_and_repair_issue(client):
    from tests.test_repair_orders import create as repair_create,quote as repair_quote,authorize as repair_authorize,cmd as repair_cmd,current_quote
    items,customer,work,purchase=setup(client,True);row=create(client,items,customer,work)
    purchase,ret=purchase_return(client,purchase,purchase['receipts'][0],1000)
    # V3 approval reserves actual stock, so conflict is rejected before dispatch.
    purchase_return_action(client,purchase,ret,'return_approve',status=409)
    purchase_return_action(client,purchase,ret,'return_dispatch',status=409)
    repair=repair_create(client,customer);repair=repair_authorize(client,repair_quote(client,repair,items[0],work,1000,0));repair=repair_cmd(client,repair,'start',{'result':'按授权开始维修'})
    line=next(l for l in current_quote(client,repair)['lines'] if l['kind']=='part')
    repair_cmd(client,repair,'issue',{'line_key':line['line_key'],'quantity_milli':1000,'evidence_id':evidence(client,repair)},409)
    cmd(client,row,'cancel',{'reason':'取消精品释放库存'})
    repair_cmd(client,repair,'issue',{'line_key':line['line_key'],'quantity_milli':1000,'evidence_id':evidence(client,repair)})

def test_roles_prices_customer_authorization_and_forged_original(client):
    items,customer,work,_=setup(client,True);account=bank(client);login(client,'sales');create(client,items,customer,work,status=403)
    customer=master(client,'customers',{'name':'销售本人客户','phone':'13900000567','contact_allowed':True,'note':''});row=create(client,items,customer,work)
    assert client.get('/api/retail/installations').status_code==200
    cmd(client,row,'approve',{'minimum_total_cents':0,'reason':'无权限的价格审批'},403)
    login(client,'manager');cmd(client,row,'approve',{'minimum_total_cents':1201,'reason':'明确最低价格'},409)
    row=cmd(client,row,'approve',{'minimum_total_cents':1201,'reason':'主管明确确认本次低价例外','allow_below_minimum':True})
    login(client,'inventory');r=detail(client,row);assert 'amount_cents' not in r and 'goods_cents' not in r['lines'][0]
    cmd(client,row,'dispatch',{'evidence_id':evidence(client,row)},409)
    login(client,'sales');cmd(client,row,'authorize',{'revision':2,'evidence_id':evidence(client,row)},409);row=authorize(client,row)
    login(client,'inventory');row=dispatch(client,row)
    login(client,'technician');assert 'amount_cents' not in detail(client,row);row=cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'按清单实际安装完成'})
    login(client,'sales');row=cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    login(client,'finance');row=pay(client,row,1200,account);assert row['state']=='completed'

def test_replay_stale_and_immutable_stock_agreement(client):
    items,customer,_,_=setup(client);row=create(client,items,customer);version=row['version'];request_id=uuid.uuid4().hex
    v={'minimum_total_cents':0,'reason':'复核明确价格'};row=cmd(client,row,'approve',v,version=version,request_id=request_id)
    cmd(client,row,'approve',v,version=version,request_id=request_id);cmd(client,row,'approve',v,status=409,version=version)
    row=authorize(client,row);version=row['version'];key=uuid.uuid4().hex;v={'evidence_id':evidence(client,row)}
    row=cmd(client,row,'dispatch',v,version=version,request_id=key);cmd(client,row,'dispatch',v,version=version,request_id=key)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RetailDispatch))==2
        line=db.scalar(select(RetailLine));line.goods_cents=0
        with pytest.raises(HTTPException):db.commit()

@pytest.mark.parametrize('operation',['reserve','dispatch','payment','return','refund'])
def test_competing_stock_and_finance_commands(client,operation):
    items,customer,_,_=setup(client);row=create(client,items,customer)
    if operation!='reserve':row=authorize(client,approve(client,row))
    account=bank(client)
    if operation in {'return','refund'}:row=dispatch(client,row)
    if operation=='refund':row=pay(client,row,1000,account);row,ret=request_return(client,row,row['dispatches'][0],1000);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
    clients=[TestClient(app),TestClient(app)]
    for c in clients:login(c)
    version=detail(client,row)['version'];fid=evidence(client,row,'receipt' if operation in {'payment','refund'} else 'evidence');path=f"/api/retail/orders/{row['id']}/actions/"
    if operation=='reserve':
        cmd(client,row,'cancel',{'reason':'为并发占库存准备'});path='/api/retail/orders'
        body={'customer_id':customer['id'],'lines':[{'item_id':items[0]['id'],'quantity_milli':2000,'unit_price_cents':500}]}
    else:
        key={'dispatch':'dispatch','payment':'receive','return':'return_request','refund':'refund'}[operation]
        values={'evidence_id':fid}
        if operation in {'payment','refund'}:values.update(amount_cents=500,account_id=account,reference='race-'+uuid.uuid4().hex)
        if operation=='refund':values.update(original_payment_id=row['payments'][0]['id'],amount_cents=row['totals']['refund_due_cents'])
        if operation=='return':values.update(reason='并发原单退货申请',lines=[{'dispatch_id':row['dispatches'][0]['id'],'quantity_milli':1000}])
        body={'version':version,'values':values};path+=key
    try:
        def run(c):return c.post(path,json={**body,'request_id':uuid.uuid4().hex}).status_code
        with ThreadPoolExecutor(2) as pool:codes=list(pool.map(run,clients))
        assert sorted(codes)==([201,409] if operation=='reserve' else [200,409])
    finally:
        for c in clients:c.close()

def test_approved_returns_reserve_original_quantity_and_cancel_releases(client):
    items,customer,_,_=setup(client);row=dispatch(client,authorize(client,approve(client,create(client,items,customer))))
    row,first=request_return(client,row,row['dispatches'][0],1500);row,second=request_return(client,row,row['dispatches'][0],1500)
    row=ret_cmd(client,row,first,'return_approve');ret_cmd(client,row,second,'return_approve',status=409)
    row=ret_cmd(client,row,first,'return_cancel');row=ret_cmd(client,row,second,'return_approve');row=ret_cmd(client,row,second,'return_receive')
    assert sum(p['quantity_milli'] for p in row['return_postings'])==1500

def test_cross_store_reads_create_related_and_all_actions_refused(client):
    items,customer,_,_=setup(client);row=create(client,items,customer)
    with SessionLocal() as db:
        db.add(Store(id=2,code='SECOND',name='另一门店'));u=db.scalar(select(User).where(User.username=='admin'));db.add(UserStore(user_id=u.id,store_id=2));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get('/api/retail/orders/'+str(row['id'])).status_code==404
    create(client,items,customer,status=404)
    cases={'approve':{'minimum_total_cents':0,'reason':'跨店复核'},'authorize':{'revision':1,'evidence_id':1},'cancel':{'reason':'跨店取消'},'dispatch':{'evidence_id':1},
        'install':{'evidence_id':1,'result':'跨店安装'},'accept':{'evidence_id':1},'receive':{'amount_cents':1,'account_id':1,'reference':'cross-store','evidence_id':1},
        'return_request':{'reason':'跨店退货','evidence_id':1,'lines':[{'dispatch_id':1,'quantity_milli':1}]},'return_approve':{'return_id':1,'return_version':1,'reason':'跨店批准'},
        'return_cancel':{'return_id':1,'return_version':1,'reason':'跨店撤销'},'return_receive':{'return_id':1,'return_version':1,'passed':True,'result':'跨店验收','evidence_id':1},
        'return_reject':{'return_id':1,'return_version':1,'reason':'跨店拒收'},'return_handback':{'return_id':1,'return_version':1,'result':'跨店交回','evidence_id':1},
        'return_rectify':{'return_id':1,'return_version':1,'result':'跨店整改','evidence_id':1},'refund':{'original_payment_id':1,'amount_cents':1,'account_id':1,'reference':'cross-refund','evidence_id':1}}
    for key,v in cases.items():
        response=client.post(f"/api/retail/orders/{row['id']}/actions/{key}",json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':v})
        assert response.status_code==404,(key,response.text)

def test_same_store_forged_source_account_limit_and_quarantined_evidence(client):
    items,customer,_,_=setup(client);row=authorize(client,approve(client,create(client,items,customer)));account=bank(client);row=pay(client,row,1000,account);row=dispatch(client,row)
    otheritems,othercustomer,_,_=setup(client);other=dispatch(client,authorize(client,approve(client,create(client,otheritems,othercustomer))))
    cmd(client,row,'return_request',{'reason':'伪造其他原单','evidence_id':evidence(client,row),'lines':[{'dispatch_id':other['dispatches'][0]['id'],'quantity_milli':1}]},404)
    row,ret=request_return(client,row,row['dispatches'][0],1000);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
    other=pay(client,other,1000,account)
    refund(client,row,other['payments'][0],account,100,status=404)
    refund(client,row,row['payments'][0],bank(client),100,status=409)
    refund(client,row,row['payments'][0],account,row['totals']['refund_due_cents']+1,status=409)
    from app.file_security_models import FileSecurity
    fid=evidence(client,row)
    with SessionLocal() as db:
        db.info['_file_scan_authority']=True
        state=db.scalar(select(FileSecurity).where(FileSecurity.file_id==fid));state.state='quarantined';db.commit()
    cmd(client,row,'accept',{'evidence_id':fid},409)

def test_linked_repair_is_same_customer_and_does_not_share_stock_or_cash(client):
    from tests.test_repair_orders import create as repair_create
    items,customer,_,_=setup(client);repair=repair_create(client,customer)
    row=create(client,items,customer,related_repair_id=repair['id']);assert row['related_repair_id']==repair['id']
    other=master(client,'customers',{'name':'另一精品客户','phone':'13900000092','contact_allowed':True,'note':''})
    create(client,items,other,related_repair_id=repair['id'],status=422)
    row=authorize(client,approve(client,row));row=pay(client,row,1000,bank(client));row=dispatch(client,row)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PaymentLink).where(PaymentLink.case_id==repair['id']))==0
        assert db.scalar(select(func.count()).select_from(StockMove).where(StockMove.case_id==repair['id']))==0

def test_manual_finance_handoff_survives_other_facts(client):
    from app.flow_models import Task
    items,customer,_,_=setup(client);row=authorize(client,approve(client,create(client,items,customer)));account=bank(client)
    with SessionLocal() as db:
        user=User(username='finance-two',display_name='第二财务',role='finance',password_hash=PASSWORD_HASH,must_change_password=False);db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit();uid=user.id
    task=next(t for t in client.get('/api/flow/cases/'+str(row['id'])).json()['tasks'] if t['key']=='retail_receive')
    response=client.post('/api/flow/tasks/'+str(task['id'])+'/assign',json={'version':task['version'],'assignee_id':uid,'reason':'转交当班财务'});assert response.status_code==200,response.text
    row=dispatch(client,row);login(client,'finance')
    cmd(client,row,'receive',{'amount_cents':100,'account_id':account,'reference':'old-finance','evidence_id':evidence(client,row,'receipt')},409)
    login(client,'finance-two');row=pay(client,row,100,account);row=pay(client,row,100,account)
    with SessionLocal() as db:assert db.scalar(select(Task).where(Task.case_id==row['id'],Task.key=='retail_receive')).assignee_id==uid

def test_sales_list_obeys_owner_and_dedicated_lookup_hides_cost(client):
    items,customer,work,_=setup(client,True);row=create(client,items,customer,work)
    login(client,'sales');data=client.get('/api/retail/orders').json();assert data['total']==0
    assert client.get('/api/retail/orders/'+str(row['id'])).status_code==404
    data=client.get('/api/retail/items').json();assert data['items'] and 'unit_cost_cents' not in data['items'][0] and 'inventory_value_cents' not in data['items'][0]
    data=client.get('/api/retail/installations').json();assert data['items'][0]['id']==work['id']

def test_quote_and_cash_files_require_private_categories(client):
    items,customer,_,_=setup(client);row=approve(client,create(client,items,customer));ordinary=evidence(client,row)
    cmd(client,row,'authorize',{'revision':1,'evidence_id':ordinary},422)
    authorized=evidence(client,row,'authorization');row=cmd(client,row,'authorize',{'revision':1,'evidence_id':authorized})
    cmd(client,row,'receive',{'amount_cents':100,'account_id':bank(client),'reference':'wrong-type','evidence_id':ordinary},422)
    financial=evidence(client,row,'receipt')
    login(client,'inventory')
    assert client.get('/api/flow/files/'+str(authorized)).status_code==403
    assert client.get('/api/flow/files/'+str(financial)).status_code==403
    data=client.get('/api/flow/cases/'+str(row['id'])).json()
    assert authorized not in [f['id'] for f in data['files']] and financial not in [f['id'] for f in data['files']]

def test_period_retail_chart_table_csv_and_pre_delivery_returns(client,monkeypatch):
    import csv,io
    from datetime import date
    import app.retail_service as service
    items,customer,work,_=setup(client,True);row=dispatch(client,authorize(client,approve(client,create(client,items,customer,work))))
    # A real return before installation changes the initial delivery amount.
    monkeypatch.setattr(service,'today',lambda:date(2026,1,15))
    row,ret=request_return(client,row,row['dispatches'][0],500);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
    row=cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'其余精品已实际安装'});row=cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    january_revenue=row['totals']['charge_cents'];january_cost=row['totals']['cost_cents']
    monkeypatch.setattr(service,'today',lambda:date(2026,2,15))
    row,ret=request_return(client,row,row['dispatches'][0],500);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
    last=row['return_postings'][-1];reduction=last['goods_cents']+last['installation_cents']-last['retained_cents']
    for start,end,expected,cost in [('2026-01-01','2026-01-31',january_revenue,january_cost),('2026-02-01','2026-02-28',-reduction,-last['value_cents'])]:
        query=f'date_from={start}&date_to={end}';response=client.get('/api/flow/analytics?'+query);assert response.status_code==200,response.text;data=response.json()
        assert data['metrics']['retail_revenue_cents']==expected and data['metrics']['retail_goods_cost_cents']==cost
        table=data['tables']['retail_settlements'];chart=next(c for c in data['charts'] if c['id']=='retail_settlements')
        assert sum(r['amount_cents'] for r in table['rows'])==sum(chart['series'][0]['values'])==expected
        export=client.get('/api/flow/analytics/export?dataset=retail_settlements&'+query);assert export.status_code==200,export.text
        actual=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))))
        from decimal import Decimal
        assert actual[0]==table['headers'] and [r[:5] for r in actual[1:]]==[r['values'][:5] for r in table['rows']]
        assert sum(Decimal(r[5].removeprefix("'"))*100 for r in actual[1:])==expected
        assert sum(Decimal(r[6].removeprefix("'"))*100 for r in actual[1:])==cost

@pytest.mark.parametrize('tamper',['quote','reservation','dispatch','return','fee','cash'])
def test_nonempty_sqlite_restore_checks_retail_facts_and_refuses_tamper(client,tamper):
    import sqlite3
    from tests.conftest import TEST_DIR
    from app.retail_backup_integrity import validate_retail_sqlite
    items,customer,work,_=setup(client,True);row=authorize(client,approve(client,create(client,items,customer,work)));row=pay(client,row,1200,bank(client));row=dispatch(client,row)
    row=cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'安装事实已完成'});row=cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    row,ret=request_return(client,row,row['dispatches'][0],500);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);result=validate_retail_sqlite(restored)
        assert result=={'verified_retail_orders':1,'verified_retail_dispatches':2,'verified_retail_returns':1}
        from app.backup_integrity import validate_sqlite
        assert validate_sqlite(restored)['verified_files']>0
        statement={'quote':'UPDATE retail_lines SET goods_cents=goods_cents+1 WHERE id=(SELECT MIN(id) FROM retail_lines)',
            'reservation':"UPDATE retail_reservations SET quantity_milli=quantity_milli-1 WHERE reason='reserve' AND id=(SELECT MIN(id) FROM retail_reservations)",
            'dispatch':"UPDATE flow_stock_moves SET value_cents=value_cents+1 WHERE purpose='retail_dispatch'",
            'return':'UPDATE retail_return_postings SET value_cents=value_cents-1',
            'fee':'UPDATE retail_return_postings SET retained_cents=0',
            'cash':"UPDATE cash_entries SET amount_cents=amount_cents-1 WHERE category='workflow_retail'"}[tamper]
        restored.execute(statement)
        with pytest.raises(ValueError,match='精品'):validate_retail_sqlite(restored)
