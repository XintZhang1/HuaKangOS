"""Supplier originals, moving-average residuals and competing stock consumers."""
import uuid,sqlite3
import pytest
from sqlalchemy import select,func
from app.db import SessionLocal
from app.flow_models import Item,StockMove
from app.models import CashEntry
from app.procurement_cost_models import PurchaseReturnValuation
from app.procurement_cost_integrity import validate
from app.backup_integrity import validate_sqlite
from tests.conftest import TEST_DIR,login
from tests import test_procurement as purchase,test_retail as retail
from tests.test_workflow import master,evidence


def ordered(c,item,cost,quantity=1000,supplier=None):
    supplier=supplier or purchase.supplier(c)
    r=c.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,'supplier_id':supplier['id'],'reason':'核对不同进货价格的同类备货','lines':[{'item_id':item,'quantity_milli':quantity,'unit_cost_cents':cost}]})
    assert r.status_code==201,r.text
    return purchase.receive(c,purchase.command(c,r.json(),'approve'))


def mixed(c):
    item=master(c,'items',{'sku':uuid.uuid4().hex,'name':'可追原采购的同规格精品','unit':'件','reorder':'0','active':True})['id']
    return item,ordered(c,item,1000),ordered(c,item,100)


def retail_take(c,item,quantity=1000,dispatch=True,status=201):
    customer=master(c,'customers',{'name':'原材料实际领取客户','phone':'','contact_allowed':True,'note':''})
    r=c.post('/api/retail/orders',json={'request_id':uuid.uuid4().hex,'customer_id':customer['id'],'discount_cents':0,'lines':[{'item_id':item,'quantity_milli':quantity,'unit_price_cents':1000}]})
    assert r.status_code==status,r.text
    if status!=201:return r.json()
    row=retail.authorize(c,retail.approve(c,r.json()))
    return retail.dispatch(c,row) if dispatch else row


def returned(c,row,q=1000):
    row,request=purchase.return_request(c,row,row['receipts'][0],q)
    row=purchase.return_action(c,row,request,'return_approve')
    return purchase.return_action(c,row,request,'return_dispatch')


def test_expensive_original_after_mixed_issue_clears_physical_stock_but_refunds_original_cash(client):
    c=client;item,expensive,cheap=mixed(c);account=purchase.bank(c);expensive=purchase.pay(c,expensive,account,1000)
    retail_take(c,item)
    result=returned(c,expensive)
    cost=result['return_costs'][0]
    assert (cost['supplier_credit_cents'],cost['inventory_cost_cents'],cost['variance_cents'])==(1000,550,450)
    assert result['totals']['supplier_refund_due_cents']==1000
    with SessionLocal() as db:
        row=db.get(Item,item);assert (row.quantity_milli,row.inventory_value_cents)==(0,0)
        assert db.scalar(select(func.sum(StockMove.value_cents)).where(StockMove.item_id==item))==0
        assert db.scalar(select(PurchaseReturnValuation)).variance_cents==450
    result=purchase.command(c,result,'refund',{'original_payment_id':result['payments'][0]['id'],'amount_cents':1000,'account_id':account,'reference':uuid.uuid4().hex,'evidence_id':evidence(c,result,'receipt')})
    assert result['totals']['supplier_refund_due_cents']==0
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate_sqlite(db)['verified_purchase_return_valuations']==1
    with SessionLocal() as db:
        assert sum(r.amount_cents*(1 if r.direction=='out' else -1) for r in db.scalars(select(CashEntry)))==0


def test_cheap_original_returns_current_cost_with_negative_difference_and_v2_keeps_original_rule(client,monkeypatch):
    c=client;item,expensive,cheap=mixed(c);retail_take(c,item)
    row=returned(c,cheap);assert row['return_costs'][0]['variance_cents']==-450
    with SessionLocal() as db:assert db.get(Item,item).inventory_value_cents==0
    from app import procurement_service
    monkeypatch.setattr(procurement_service,'CURRENT_FLOW_VERSION',2)
    other,old_expensive,old_cheap=mixed(c);retail_take(c,other)
    old_expensive,request=purchase.return_request(c,old_expensive,old_expensive['receipts'][0],1000)
    old_expensive=purchase.return_action(c,old_expensive,request,'return_approve')
    purchase.return_action(c,old_expensive,request,'return_dispatch',status=409)
    with SessionLocal() as db:
        row=db.get(Item,other);assert (row.quantity_milli,row.inventory_value_cents)==(1000,550)


def test_rounding_original_credit_and_remaining_inventory_value_are_independently_conserved(client):
    c=client;row,_,_=purchase.setup(c);row=purchase.command(c,row,'approve');line=row['lines'][1]
    for q in (333,333,334):row=purchase.receive(c,row,[{'line_id':line['id'],'quantity_milli':q}])
    receipts=list(row['receipts'])
    for q in (111,111,112):
        row,request=purchase.return_request(c,row,receipts[-1],q);row=purchase.return_action(c,row,request,'return_approve');row=purchase.return_action(c,row,request,'return_dispatch')
    assert row['totals']['returned_cents']==1 and row['totals']['return_cost_variance_cents']==1
    for receipt in receipts[:-1]:
        row,request=purchase.return_request(c,row,receipt,333);row=purchase.return_action(c,row,request,'return_approve');row=purchase.return_action(c,row,request,'return_dispatch')
    assert row['totals']['return_cost_variance_cents']==0
    with SessionLocal() as db:
        item=db.get(Item,line['item_id']);assert (item.quantity_milli,item.inventory_value_cents)==(0,0)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as db:assert validate(db)['verified_purchase_return_valuations']==5


def test_approved_v3_return_reserves_real_stock_and_cancel_releases_it(client):
    c=client;item,first,second=mixed(c)
    first,request=purchase.return_request(c,first,first['receipts'][0],1000);first=purchase.return_action(c,first,request,'return_approve')
    retail_take(c,item,2000,status=409)
    first=purchase.return_action(c,first,request,'return_cancel')
    retail_take(c,item,2000)
    first,new=purchase.return_request(c,first,first['receipts'][0],1000)
    purchase.return_action(c,first,new,'return_approve',status=409)


def test_cost_snapshot_and_original_link_cannot_be_rehashed_or_edited_on_restore(client):
    c=client;item,first,second=mixed(c);row=returned(c,first)
    login(c,'inventory');hidden=purchase.detail(c,row)
    assert 'return_costs' not in hidden and 'totals' not in hidden
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source:
        for sql in ['UPDATE procurement_return_valuations SET store_id=999',
                    'UPDATE procurement_return_valuations SET value_before_cents=value_before_cents+1',
                    'DELETE FROM procurement_return_valuations']:
            with sqlite3.connect(':memory:') as copy:
                source.backup(copy);copy.execute(sql)
                with pytest.raises(ValueError):validate(copy)
    with SessionLocal() as db:
        row=db.scalar(select(PurchaseReturnValuation));row.value_before_cents+=1
        from fastapi import HTTPException
        with pytest.raises(HTTPException):db.commit()
        db.rollback()



def test_cost_report_chart_csv_and_actual_period_share_one_original_population(client):
    import csv,io
    from datetime import timedelta
    from app.db import today
    from tests.test_service_analytics import report
    from tests.test_multistore import second_store,switch
    c=client;item,first,second=mixed(c);retail_take(c,item);returned(c,first)
    data=report(c);table=data['tables']['procurement_return_costs']
    assert len(table['rows'])==1
    assert sum(r['amount_cents'] for r in table['rows'])==450
    assert sum(r['inventory_cost_cents'] for r in table['rows'])==550
    assert data['metrics']['purchase_return_supplier_credit_cents']==1000
    chart=next(ch for ch in data['charts'] if ch['id']=='procurement_return_cost_variance')
    assert sum(chart['series'][0]['values'])==450
    response=c.get('/api/flow/analytics/export',params={'dataset':'procurement_return_costs'})
    assert response.status_code==200,response.text
    csvrows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert csvrows[0]==table['headers']
    assert [[v.removeprefix("'") for v in row] for row in csvrows[1:]]==[[str(v) for v in row['values']] for row in table['rows']]
    past=(today()-timedelta(days=1)).isoformat()
    assert report(c,date_from=past,date_to=past)['tables']['procurement_return_costs']['rows']==[]
    second_store(c);switch(c,2)
    assert report(c)['tables']['procurement_return_costs']['rows']==[]
    switch(c,1);login(c,'inventory')
    assert c.get('/api/flow/analytics/export',params={'dataset':'procurement_return_costs'}).status_code==403


def test_competing_original_return_approvals_cannot_both_hold_same_remaining_item(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from app.main import app
    from app.procurement_models import PurchaseReturn
    c=client;item,first,second=mixed(c);retail_take(c,item)
    requests=[]
    for row in (first,second):
        row,request=purchase.return_request(c,row,row['receipts'][0],1000)
        requests.append((row['id'],dict(request_id=uuid.uuid4().hex,version=row['version'],values={'return_id':request['id'],'return_version':request['version'],'reason':'核对同物资可用量'})))
    barrier=Barrier(2)
    def worker(pair):
        browser,request=pair;barrier.wait(timeout=10)
        return browser.post('/api/procurement/orders/'+str(request[0])+'/actions/return_approve',json=request[1]).status_code
    with TestClient(app) as one,TestClient(app) as two:
        login(one);login(two)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,zip((one,two),requests)))
    assert sorted(results)==[200,409]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PurchaseReturn).where(PurchaseReturn.status=='approved'))==1
        stored=db.get(Item,item);assert (stored.quantity_milli,stored.inventory_value_cents)==(1000,550)


def test_unexplained_inventory_value_refuses_new_cost_posting(client):
    from sqlalchemy import text
    c=client;item,first,second=mixed(c)
    first,request=purchase.return_request(c,first,first['receipts'][0],1000)
    first=purchase.return_action(c,first,request,'return_approve')
    with SessionLocal() as db:
        db.execute(text('UPDATE flow_items SET inventory_value_cents=inventory_value_cents+1 WHERE id=:id'),{'id':item});db.commit()
    purchase.return_action(c,first,request,'return_dispatch',status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PurchaseReturnValuation))==0
        assert db.get(Item,item).quantity_milli==2000
