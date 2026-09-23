"""Actual purchase, batch return, original refund and role/tenant conservation."""
import csv,io,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal
from app.models import CashEntry,Store,User,UserStore
from app.flow_models import Case,Item,StockMove,Account,Task
from app.procurement_models import PurchaseLine,PurchaseReceipt,PurchaseReturn,PurchaseReturnPosting,PurchasePayment
from tests.conftest import login,PASSWORD_HASH
from tests.test_workflow import master,evidence


def supplier(c):
    r=c.post('/api/masters/suppliers',json={'request_id':uuid.uuid4().hex,'values':{
        'code':'S'+uuid.uuid4().hex[:8],'name':'真实接口虚构供应商','payment_terms_days':30}})
    assert r.status_code==201,r.text;return r.json()


def setup(c,lines=None):
    s=supplier(c)
    items=[master(c,'items',{'sku':uuid.uuid4().hex,'name':'采购物资'+str(i),'unit':'件','reorder':'0','active':True}) for i in range(2)]
    values={'supplier_id':s['id'],'reason':'门店维修备货','lines':lines or [
        {'item_id':items[0]['id'],'quantity_milli':2500,'unit_cost_cents':123},
        {'item_id':items[1]['id'],'quantity_milli':1000,'unit_cost_cents':1}]}
    response=c.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,**values})
    assert response.status_code==201,response.text
    return response.json(),items,s


def detail(c,row):
    r=c.get('/api/procurement/orders/'+str(row['id']));assert r.status_code==200,r.text;return r.json()


def command(c,row,key,values=None,status=200,version=None,request_id=None):
    current=detail(c,row)
    r=c.post(f"/api/procurement/orders/{row['id']}/actions/{key}",json={'request_id':request_id or uuid.uuid4().hex,
        'version':current['version'] if version is None else version,'values':values or {}})
    assert r.status_code==status,r.text;return r.json()


def receive(c,row,amounts=None):
    row=detail(c,row)
    lines=amounts or [{'line_id':l['id'],'quantity_milli':l['quantity_milli']-l['received_milli']} for l in row['lines'] if l['quantity_milli']>l['received_milli']]
    return command(c,row,'receive',{'lines':lines,'evidence_id':evidence(c,row)})


def bank(c):return master(c,'accounts',{'name':'采购账户'+uuid.uuid4().hex[:6],'account_type':'bank','active':True})['id']


def pay(c,row,account,amount):
    return command(c,row,'pay',{'account_id':account,'amount_cents':amount,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,row,'receipt')})


def return_request(c,row,receipt,quantity):
    result=command(c,row,'return_request',{'lines':[{'receipt_id':receipt['id'],'quantity_milli':quantity}],
        'reason':'已核对需要退回原批次','evidence_id':evidence(c,row)})
    return result,result['returns'][-1]


def return_action(c,row,ret,key,**kw):
    ret=next(x for x in detail(c,row)['returns'] if x['id']==ret['id'])
    values={'return_id':ret['id'],'return_version':ret['version']}
    values.update({'evidence_id':evidence(c,row)} if key=='return_dispatch' else {'reason':'主管核对原批次'})
    return command(c,row,key,values,**kw)


def test_multiline_partial_receipts_pay_return_original_refund(client):
    row,items,s=setup(client)
    assert row['amount_cents']==309 and row['totals']['payable_cents']==0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(StockMove))==0
        assert db.scalar(select(func.count()).select_from(CashEntry))==0
    row=command(client,row,'approve')
    account=bank(client)
    command(client,row,'pay',{'account_id':account,'amount_cents':1,'reference':'no-prepay','evidence_id':evidence(client,row)},409)
    row=receive(client,row,[{'line_id':row['lines'][0]['id'],'quantity_milli':1000}])
    assert row['totals']['payable_cents']==123 and row['receipts'][0]['value_cents']==123
    row=pay(client,row,account,100);assert row['totals']['payable_cents']==23
    row=receive(client,row);row=pay(client,row,account,209)
    assert row['state']=='completed' and row['totals']['paid_net_cents']==309
    first=row['receipts'][0]
    row,ret=return_request(client,row,first,500)
    return_action(client,row,ret,'return_dispatch',status=409)
    row=return_action(client,row,ret,'return_approve')
    assert row['totals']['returned_cents']==0
    row=return_action(client,row,ret,'return_dispatch')
    assert row['totals']['supplier_refund_due_cents']==62 and row['totals']['returned_cents']==62
    original=row['payments'][0]
    row=command(client,row,'refund',{'original_payment_id':original['id'],'amount_cents':62,'account_id':account,
        'reference':'supplier-refund','evidence_id':evidence(client,row,'receipt')})
    assert row['state']=='completed' and row['totals']['supplier_refund_due_cents']==0
    with SessionLocal() as db:
        item=db.get(Item,items[0]['id']);assert item.quantity_milli==2000 and item.inventory_value_cents==246
        cash=list(db.scalars(select(CashEntry)))
        assert sum(c.amount_cents*(1 if c.direction=='out' else -1) for c in cash)==247
        assert db.scalar(select(func.sum(StockMove.value_cents)))==247
        assert db.scalar(select(func.count()).select_from(PurchasePayment))==3


def test_rounding_remainders_conserve_received_and_returned_batch_value(client,monkeypatch):
    from app import procurement_service
    monkeypatch.setattr(procurement_service,'CURRENT_FLOW_VERSION',2)
    row,_,_=setup(client);row=command(client,row,'approve');line=row['lines'][1]
    for q in (333,333,334):row=receive(client,row,[{'line_id':line['id'],'quantity_milli':q}])
    batches=[r for r in row['receipts'] if r['line_id']==line['id']]
    assert [r['value_cents'] for r in batches]==[0,0,1]
    last=batches[-1]
    for q in (111,111,112):
        row,ret=return_request(client,row,last,q);row=return_action(client,row,ret,'return_approve');row=return_action(client,row,ret,'return_dispatch')
    assert row['totals']['received_cents']==row['totals']['returned_cents']==1
    with SessionLocal() as db:
        values=list(db.scalars(select(PurchaseReturnPosting.value_cents)))
        assert sum(values)==1
        assert db.get(Item,line['item_id']).inventory_value_cents==0


def test_employee_role_chain_and_cost_hiding(client):
    row,_,_=setup(client)
    login(client,'inventory');hidden=detail(client,row)
    assert 'totals' not in hidden and 'unit_cost_cents' not in hidden['lines'][0]
    command(client,row,'approve',status=403)
    login(client,'manager');row=command(client,row,'approve')
    login(client,'inventory');row=receive(client,row)
    assert client.get('/api/procurement/payables').status_code==403
    assert client.get('/api/procurement/payables/export').status_code==403
    login(client);account=bank(client)
    login(client,'manager');command(client,row,'pay',{'amount_cents':1,'account_id':account,'reference':'manager-cannot-pay','evidence_id':evidence(client,row)},403)
    login(client,'finance');row=pay(client,row,account,309);assert row['state']=='completed'
    receipt_id=evidence(client,row,'receipt')
    login(client,'inventory')
    generic=client.get('/api/flow/cases/'+str(row['id'])).json()
    assert 'amount_cents' not in generic and 'payments' not in generic
    assert all('reference' not in event['detail'] and 'account_id' not in event['detail'] for event in generic['events'])
    assert client.get('/api/flow/files/'+str(receipt_id)).status_code==403
    row,ret=return_request(client,row,row['receipts'][0],500)
    login(client,'manager');row=return_action(client,row,ret,'return_approve')
    login(client,'inventory');row=return_action(client,row,ret,'return_dispatch')
    login(client,'finance');assert detail(client,row)['totals']['supplier_refund_due_cents']>0


def test_cancel_and_close_receiving_have_no_invented_ledger(client):
    row,_,_=setup(client);row=command(client,row,'approve');row=command(client,row,'cancel',{'reason':'供应商无法供货'})
    assert row['state']=='cancelled'
    command(client,row,'receive',{'lines':[{'line_id':row['lines'][0]['id'],'quantity_milli':1}],'evidence_id':evidence(client,row)},409)
    other,_,_=setup(client);other=command(client,other,'approve')
    other=receive(client,other,[{'line_id':other['lines'][0]['id'],'quantity_milli':1000}])
    command(client,other,'cancel',{'reason':'已经到货不应删除'},409)
    other=command(client,other,'close_receiving',{'reason':'已收到部分，其余不再供货'})
    assert other['receiving_closed'] and other['totals']['payable_cents']==123
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove))==1


def test_duplicate_stale_requests_and_no_partial_multirow_receipt(client):
    row,_,_=setup(client);old=row['version'];key=uuid.uuid4().hex
    row=command(client,row,'approve',request_id=key,version=old)
    command(client,row,'approve',request_id=key,version=old)
    command(client,row,'approve',version=old,status=409)
    fid=evidence(client,row);row=detail(client,row);version=row['version'];key=uuid.uuid4().hex
    bad={'lines':[{'line_id':row['lines'][0]['id'],'quantity_milli':1000},{'line_id':row['lines'][1]['id'],'quantity_milli':1001}],'evidence_id':fid}
    command(client,row,'receive',bad,409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove))==0
    good={**bad,'lines':bad['lines'][:1]};row=command(client,row,'receive',good,request_id=key,version=version)
    command(client,row,'receive',good,request_id=key,version=version)
    command(client,row,'receive',good,version=version,status=409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(PurchaseReceipt))==1


@pytest.mark.parametrize('key',['approve','reject','cancel','receive','pay','return_request','return_approve','return_cancel','return_dispatch','refund','close_receiving'])
def test_all_procurement_actions_and_files_are_store_scoped(client,key):
    row,_,_=setup(client);fid=evidence(client,row)
    other=client.post('/api/stores',json={'code':'OTHER','name':'另一门店','active':True}).json()['id'];client.headers['X-Store-ID']=str(other)
    assert client.get('/api/procurement/orders/'+str(row['id'])).status_code==404
    assert client.get('/api/flow/files/'+str(fid)).status_code==404
    assert client.get('/api/procurement/orders').json()['total']==0
    values={'approve':{},'reject':{'reason':'跨店操作'},'cancel':{'reason':'跨店操作'},'close_receiving':{'reason':'跨店操作'},
        'receive':{'lines':[{'line_id':row['lines'][0]['id'],'quantity_milli':1}],'evidence_id':fid},
        'return_request':{'lines':[{'receipt_id':1,'quantity_milli':1}],'evidence_id':fid,'reason':'跨店操作'},
        'return_approve':{'return_id':1,'return_version':1,'reason':'跨店操作'},'return_cancel':{'return_id':1,'return_version':1,'reason':'跨店操作'},
        'return_dispatch':{'return_id':1,'return_version':1,'evidence_id':fid},
        'pay':{'account_id':1,'amount_cents':1,'reference':'cross','evidence_id':fid},
        'refund':{'account_id':1,'amount_cents':1,'reference':'cross','evidence_id':fid,'original_payment_id':1}}[key]
    response=client.post(f"/api/procurement/orders/{row['id']}/actions/{key}",json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':values})
    assert response.status_code==404,response.text


def test_supplier_master_validation_and_unit_freeze(client):
    row,items,s=setup(client)
    response=client.put(f"/api/masters/suppliers/{s['id']}",json={'request_id':uuid.uuid4().hex,'version':s['version'],
        'values':{'code':s['code'],'name':s['name'],'active':False}})
    assert response.status_code==409,response.text
    item=items[0]
    response=client.put(f"/api/flow/master/items/{item['id']}",json={'version':item['version'],
        'values':{'sku':item['sku'],'name':item['name'],'unit':'升','reorder':'0','active':True}})
    assert response.status_code==409,response.text
    assert client.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,'supplier_id':999,'reason':'未配置供应商',
        'lines':[{'item_id':item['id'],'quantity_milli':1,'unit_cost_cents':1}]}).status_code==422


def test_return_cannot_exceed_original_batch_or_refund_other_payment(client):
    row,_,_=setup(client);row=command(client,row,'approve');row=receive(client,row);a=bank(client);row=pay(client,row,a,309)
    receipt=row['receipts'][0];row,ret=return_request(client,row,receipt,receipt['quantity_milli'])
    row=return_action(client,row,ret,'return_approve');row=return_action(client,row,ret,'return_dispatch')
    command(client,row,'return_request',{'lines':[{'receipt_id':receipt['id'],'quantity_milli':1}],'reason':'重复退货','evidence_id':evidence(client,row)},409)
    values={'original_payment_id':row['payments'][0]['id'],'amount_cents':309,'account_id':a,'reference':'too-much','evidence_id':evidence(client,row,'receipt')}
    command(client,row,'refund',values,409)
    command(client,row,'refund',{**values,'amount_cents':308,'account_id':bank(client)},409)
    row=command(client,row,'refund',{**values,'amount_cents':308})
    assert row['totals']['supplier_refund_due_cents']==0
    command(client,row,'refund',{**values,'amount_cents':1,'reference':'double-refund'},409)


def test_payables_export_matches_receipts_and_returns(client):
    row,_,_=setup(client);row=command(client,row,'approve');row=receive(client,row)
    data=client.get('/api/procurement/payables').json();assert data['payable_cents']==309
    response=client.get('/api/procurement/payables/export');rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert sum(int(r[6]) for r in rows[1:])==data['payable_cents']
    with SessionLocal() as db:assert db.scalar(select(func.sum(PurchaseReceipt.value_cents)))==data['payable_cents']


def test_competing_receipts_post_only_once(client):
    row,_,_=setup(client);row=command(client,row,'approve');fid=evidence(client,row);row=detail(client,row)
    body={'version':row['version'],'values':{'lines':[{'line_id':l['id'],'quantity_milli':l['quantity_milli']} for l in row['lines']],'evidence_id':fid}}
    def worker(c):
        return c.post(f"/api/procurement/orders/{row['id']}/actions/receive",json={**body,'request_id':uuid.uuid4().hex}).status_code
    with TestClient(app) as first,TestClient(app) as second:
        login(first);login(second)
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(worker,[first,second]))
    assert sorted(results)==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PurchaseReceipt))==2
        assert db.scalar(select(func.sum(StockMove.value_cents)))==309


def test_immutable_purchase_facts_and_unknown_version_fail_closed(client):
    row,_,_=setup(client)
    with SessionLocal() as db:
        line=db.scalar(select(PurchaseLine));line.quantity_milli=1
        with pytest.raises(HTTPException):db.commit()
        db.rollback();stored=db.get(Case,row['id']);stored.flow_version=999;db.commit();version=stored.version
    r=client.post(f"/api/procurement/orders/{row['id']}/actions/approve",json={'request_id':uuid.uuid4().hex,'version':version,'values':{}})
    assert r.status_code==409


def race(client,row,commands):
    version=detail(client,row)['version']
    def worker(args):
        c,(key,values)=args
        return c.post(f"/api/procurement/orders/{row['id']}/actions/{key}",json={
            'request_id':uuid.uuid4().hex,'version':version,'values':values}).status_code
    with TestClient(app) as first,TestClient(app) as second:
        login(first);login(second)
        with ThreadPoolExecutor(max_workers=2) as executor:
            return sorted(executor.map(worker,zip([first,second],commands)))


def test_competing_payments_and_original_refunds_conserve_cash(client):
    row,_,_=setup(client);row=command(client,row,'approve');row=receive(client,row);account=bank(client)
    values={'amount_cents':309,'account_id':account,'reference':'pay-race','evidence_id':evidence(client,row,'receipt')}
    assert race(client,row,[('pay',values),('pay',{**values,'reference':'pay-race-two'})])==[200,409]
    row=detail(client,row);row,ret=return_request(client,row,row['receipts'][0],2500)
    row=return_action(client,row,ret,'return_approve');row=return_action(client,row,ret,'return_dispatch')
    values={'amount_cents':308,'original_payment_id':row['payments'][0]['id'],'account_id':account,
        'reference':'refund-race','evidence_id':evidence(client,row,'receipt')}
    assert race(client,row,[('refund',values),('refund',{**values,'reference':'refund-race-two'})])==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry))==2
        assert db.scalar(select(func.count()).select_from(PurchasePayment))==2
    row=detail(client,row);assert row['state']=='completed' and row['totals']['paid_net_cents']==1


def test_cancellation_competes_with_receipt_without_orphan_stock(client):
    row,_,_=setup(client);row=command(client,row,'approve');fid=evidence(client,row)
    values={'lines':[{'line_id':row['lines'][0]['id'],'quantity_milli':1000}],'evidence_id':fid}
    assert race(client,row,[('receive',values),('cancel',{'reason':'取消尚未到货的申请'})])==[200,409]
    row=detail(client,row)
    with SessionLocal() as db:
        count=db.scalar(select(func.count()).select_from(StockMove))
        assert (row['state']=='cancelled' and count==0) or (row['state']=='receiving' and count==1)
        assert db.scalar(select(func.count()).select_from(CashEntry))==0


def test_approved_return_reservation_cancel_stale_and_replay(client):
    row,_,_=setup(client);row=command(client,row,'approve');row=receive(client,row);receipt=row['receipts'][0]
    row,first=return_request(client,row,receipt,2000)
    row,second=return_request(client,row,receipt,1000)
    row=return_action(client,row,first,'return_approve')
    return_action(client,row,second,'return_approve',status=409)
    row=return_action(client,row,first,'return_cancel')
    row=return_action(client,row,second,'return_approve')
    command(client,row,'return_cancel',{'return_id':second['id'],'return_version':second['version'],'reason':'过期复核不能撤销'},409)
    current=next(r for r in row['returns'] if r['id']==second['id'])
    values={'return_id':second['id'],'return_version':current['version'],'evidence_id':evidence(client,row)}
    version=detail(client,row)['version'];key=uuid.uuid4().hex
    row=command(client,row,'return_dispatch',values,request_id=key,version=version)
    command(client,row,'return_dispatch',values,request_id=key,version=version)
    command(client,row,'return_dispatch',values,status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PurchaseReturnPosting))==1
        assert db.scalar(select(func.sum(PurchaseReturnPosting.quantity_milli)))==1000


def test_manual_handoffs_survive_partial_receipt_and_payment_sync(client):
    with SessionLocal() as db:
        employees=[]
        for role in ('inventory','finance'):
            u=User(username=role+'-two',display_name='第二位'+role,role=role,password_hash=PASSWORD_HASH,must_change_password=False)
            db.add(u);db.flush();db.add(UserStore(user_id=u.id,store_id=1));employees.append(u.id)
        db.commit()
    row,_,_=setup(client);row=command(client,row,'approve')
    def handoff(task_key,user_id):
        task=next(t for t in client.get('/api/flow/cases/'+str(row['id'])).json()['tasks'] if t['key']==task_key)
        r=client.post('/api/flow/tasks/'+str(task['id'])+'/assign',json={'version':task['version'],'assignee_id':user_id,'reason':'交接给第二位在岗员工'})
        assert r.status_code==200,r.text
        return r.json()
    assigned=handoff('procurement_receive',employees[0])
    login(client,'inventory')
    command(client,row,'receive',{'lines':[{'line_id':row['lines'][0]['id'],'quantity_milli':1000}],'evidence_id':evidence(client,row)},409)
    login(client,'inventory-two')
    row=receive(client,row,[{'line_id':row['lines'][0]['id'],'quantity_milli':1000}])
    login(client);account=bank(client);handoff('procurement_pay',employees[1])
    login(client,'finance-two');row=pay(client,row,account,50)
    login(client)
    tasks=client.get('/api/flow/cases/'+str(row['id'])).json()['tasks']
    assert next(t for t in tasks if t['key']=='procurement_receive')['assignee_id']==employees[0]
    assert next(t for t in tasks if t['key']=='procurement_receive')['due_date']==assigned['due_date']
    assert next(t for t in tasks if t['key']=='procurement_pay')['assignee_id']==employees[1]
    login(client,'inventory-two');row=receive(client,row,[{'line_id':row['lines'][0]['id'],'quantity_milli':500}])
    login(client)
    tasks=client.get('/api/flow/cases/'+str(row['id'])).json()['tasks']
    assert next(t for t in tasks if t['key']=='procurement_pay')['assignee_id']==employees[1]


def test_quarantined_receipt_and_financial_evidence_never_post(client,monkeypatch):
    from tests.test_file_security import mode
    row,_,_=setup(client);row=command(client,row,'approve')
    mode(monkeypatch,'quarantine');fid=evidence(client,row)
    command(client,row,'receive',{'lines':[{'line_id':row['lines'][0]['id'],'quantity_milli':1}],'evidence_id':fid},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(StockMove))==0
    mode(monkeypatch,'structure_only');row=receive(client,row);account=bank(client)
    mode(monkeypatch,'quarantine');fid=evidence(client,row,'receipt')
    command(client,row,'pay',{'amount_cents':309,'account_id':account,'reference':'quarantine-pay','evidence_id':fid},409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(CashEntry))==0
