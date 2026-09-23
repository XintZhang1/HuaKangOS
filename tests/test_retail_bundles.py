"""Boutique packages preserve original component price, quantity, cost and cash."""
import sqlite3,uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.db import SessionLocal,today
from app.models import Store,CashEntry
from app.flow_models import Item,Case,StockMove
from app.retail_models import RetailReservation
from app.retail_bundle_models import RetailBundleRule,RetailBundleAllocation,RetailBundleSale
from tests.conftest import login,TEST_DIR
from tests.test_workflow import master,evidence
from tests.test_retail import technician,setup as stock_setup,cmd,approve,authorize,dispatch,pay,bank,request_return,ret_cmd,refund,detail

API='/api/retail-bundles'
def publish(c,items,work=None,*,base=0,status=201,request_id=None,**extra):
    values={'code':'KIT'+uuid.uuid4().hex[:8],'name':'精品原价分摊套餐','enabled':True,'sale_starts_on':str(today()),'sale_ends_on':str(today()+timedelta(days=30)),
        'price_cents_per_set':1000,'refund_terms':'已向客户说明按每个原商品冻结分摊金额退货，已履约安装费保留。',
        'components':[{'item_id':items[0]['id'],'quantity_milli_per_set':1000,'goods_reference_cents':1000,'work_item_id':work['id'] if work else None,'installation_reference_cents':100 if work else 0},
            {'item_id':items[1]['id'],'quantity_milli_per_set':333,'goods_reference_cents':1}],**extra}
    r=c.post(API+'/rules',json={'request_id':request_id or uuid.uuid4().hex,'base_version':base,'values':values});assert r.status_code==status,r.text
    return r.json()
def sale(c,rule,customer,sets=1,status=201,request_id=None,**extra):
    r=c.post(API+'/sales',json={'request_id':request_id or uuid.uuid4().hex,'rule_id':rule['id'],'rule_version':rule['rule_version'],
        'sets':sets,'customer_id':customer['id'],'terms_accepted':True,**extra});assert r.status_code==status,r.text;return r.json()
def validate():
    from app.backup_integrity import validate_sqlite
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as dst:src.backup(dst);return validate_sqlite(dst)


def test_fractional_quantity_stable_per_set_cents_and_ordinary_retail_fulfillment(client):
    items,customer,work,_=stock_setup(client,True);rule=publish(client,items,work)
    assert [(p['goods_cents_per_set'],p['installation_cents_per_set']) for p in rule['components']]==[(908,91),(1,0)]
    row=sale(client,rule,customer,2)
    assert row['amount_cents']==2000 and [l['goods_cents'] for l in row['lines']]==[1816,2]
    assert row['lines'][1]['quantity_milli']==666 and all('unit_price_cents' not in l for l in row['lines'])
    assert all(l['pricing_mode']=='frozen_bundle' for l in row['lines'])
    account=bank(client);row=dispatch(client,authorize(client,approve(client,row)));row=pay(client,row,2000,account)
    row=cmd(client,row,'install',{'evidence_id':evidence(client,row),'result':'安装已实际完成'})
    row=cmd(client,row,'accept',{'evidence_id':evidence(client,row)})
    source=row['dispatches'][0]
    for qty in (333,667,1000):
        row,ret=request_return(client,row,source,qty);row=ret_cmd(client,row,ret,'return_approve');row=ret_cmd(client,row,ret,'return_receive')
        if row['totals']['refund_due_cents']:row=refund(client,row,row['payments'][0],account,row['totals']['refund_due_cents'])
    assert sum(p['goods_cents'] for p in row['return_postings'])==1816
    assert row['totals']['retained_installation_cents']==182 and row['totals']['charge_cents']==184
    assert row['lines'][1]['goods_cents']==2
    with SessionLocal() as db:
        assert db.get(Item,items[0]['id']).quantity_milli==2500 and db.get(Item,items[0]['id']).inventory_value_cents==308
        assert sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in db.scalars(select(CashEntry)))==184
    validate()


def test_publication_versions_duplicate_request_disabled_and_frozen_old_sale(client):
    items,customer,_,_=stock_setup(client);first=publish(client,items);row=sale(client,first,customer)
    request=uuid.uuid4().hex
    disabled=publish(client,items,code=first['code'],enabled=False,base=1,request_id=request)
    assert publish(client,items,code=first['code'],enabled=False,base=1,request_id=request)['id']==disabled['id']
    publish(client,items,code=first['code'],enabled=False,base=1,status=409)
    sale(client,first,customer,status=409);sale(client,disabled,customer,status=409)
    row=authorize(client,approve(client,row));assert row['bundle']['rule_version']==1
    cmd(client,row,'revise',{'price_cents':1},status=404)
    r=client.post('/api/flow/cases/'+str(row['id'])+'/actions/revise',json={'request_id':uuid.uuid4().hex,'version':row['version'],'values':{'amount':'0.01'}})
    assert r.status_code in (404,409,422),r.text
    with SessionLocal() as db:
        original=db.get(RetailBundleRule,first['id']);original.price_cents_per_set=1
        with pytest.raises(HTTPException):db.commit()
    validate()


def test_repeated_sku_bad_installation_and_reference_totals_rejected(client):
    items,customer,_,_=stock_setup(client)
    same={'item_id':items[0]['id'],'quantity_milli_per_set':1,'goods_reference_cents':1}
    publish(client,items,components=[same,same],price_cents_per_set=1,status=422)
    publish(client,items,price_cents_per_set=1002,status=422)
    publish(client,items,components=[{**same,'installation_reference_cents':1}],status=422)
    publish(client,items,sale_ends_on=str(today()-timedelta(days=1)),status=422)
    rule=publish(client,items,sale_starts_on=str(today()+timedelta(days=1)))
    sale(client,rule,customer,status=409)
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(RetailBundleSale))==0


def test_sales_authority_roles_cross_store_stale_and_exact_replay(client):
    items,customer,_,_=stock_setup(client);rule=publish(client,items)
    login(client,'sales');publish(client,items,status=403);sale(client,rule,customer,status=403)
    own=master(client,'customers',{'name':'本人套餐客户','phone':'13900000802','note':'','contact_allowed':True})
    key=uuid.uuid4().hex;row=sale(client,rule,own,request_id=key)
    assert sale(client,rule,own,request_id=key)['id']==row['id'];sale(client,rule,own,request_id=key,sets=2,status=409)
    sale(client,rule,own,rule_version=2,status=409)
    login(client,'inventory');read=detail(client,row)
    assert 'price_cents_per_set' not in read['bundle'] and 'allocations' not in read['bundle'] and 'goods_cents' not in read['lines'][0]
    assert client.get(API+'/rules').status_code==403
    login(client,'admin')
    with SessionLocal() as db:db.add(Store(id=2,code='BUNDLE-B',name='其他套餐店'));db.commit()
    client.headers['X-Store-ID']='2'
    assert client.get(API+f"/rules/{rule['id']}/preview").status_code==404
    sale(client,rule,own,status=404);assert client.get('/api/retail/orders/'+str(row['id'])).status_code==404
    client.headers['X-Store-ID']='all';sale(client,rule,own,status=409)


def test_unperformed_installation_returns_and_cancel_release_original_stock(client):
    items,customer,work,_=stock_setup(client,True);rule=publish(client,items,work);row=sale(client,rule,customer)
    row=cmd(client,row,'cancel',{'reason':'客户未批准套餐，取消原占用'})
    assert row['state']=='cancelled'
    row=sale(client,rule,customer);row=dispatch(client,authorize(client,approve(client,row)))
    row,ret=request_return(client,row,row['dispatches'][0],1000);row=ret_cmd(client,row,ret,'return_approve')
    row=ret_cmd(client,row,ret,'return_receive');assert row['totals']['charge_cents']==1 and row['totals']['refund_due_cents']==0
    assert row['totals']['retained_installation_cents']==0
    validate()


def test_two_connections_compete_for_component_stock_without_partial_reservation(client):
    items,customer,_,_=stock_setup(client);rule=publish(client,items)
    clients=[TestClient(app),TestClient(app)]
    for c in clients:login(c)
    try:
        def run(c):return c.post(API+'/sales',json={'request_id':uuid.uuid4().hex,'rule_id':rule['id'],'rule_version':1,'sets':2,'customer_id':customer['id'],'terms_accepted':True}).status_code
        with ThreadPoolExecutor(2) as pool:codes=list(pool.map(run,clients))
        assert sorted(codes)==[201,409]
    finally:
        for c in clients:c.close()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RetailBundleSale))==1
        assert db.scalar(select(func.sum(RetailReservation.quantity_milli)).where(RetailReservation.item_id==items[0]['id']))==2000
        assert db.scalar(select(func.sum(RetailReservation.quantity_milli)).where(RetailReservation.item_id==items[1]['id']))==666
    validate()


def test_failure_after_original_case_and_reservation_rolls_back_every_fact(client,monkeypatch):
    items,customer,_,_=stock_setup(client);rule=publish(client,items)
    from app import retail_bundle_service as service
    original=service.retail.flow.log_event
    def fail(db,user,row,action,*args,**kw):
        if action=='retail_bundle_create':raise HTTPException(409,'合成模拟最后一步冲突')
        return original(db,user,row,action,*args,**kw)
    monkeypatch.setattr(service.retail.flow,'log_event',fail)
    sale(client,rule,customer,status=409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Case).where(Case.kind=='retail'))==0
        assert db.scalar(select(func.count()).select_from(RetailReservation))==0
        assert db.scalar(select(func.count()).select_from(RetailBundleSale))==0
        assert db.scalar(select(func.count()).select_from(RetailBundleAllocation))==0


def test_restored_allocation_cannot_be_repriced_or_removed(client):
    from app.retail_bundle_integrity import validate_retail_bundles_sqlite
    items,customer,_,_=stock_setup(client);row=sale(client,publish(client,items),customer)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as dst:
        src.backup(dst);validate_retail_bundles_sqlite(dst)
        dst.execute('UPDATE retail_bundle_allocations SET goods_cents=goods_cents+1 WHERE id=(SELECT min(id) FROM retail_bundle_allocations)')
        with pytest.raises(ValueError,match='金额或数量'):validate_retail_bundles_sqlite(dst)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as dst:
        src.backup(dst);dst.execute('DELETE FROM retail_bundle_allocations');dst.execute('DELETE FROM retail_bundle_sales')
        with pytest.raises(ValueError,match='来源被删除'):validate_retail_bundles_sqlite(dst)


def test_quote_snapshot_generation_is_not_customer_authorization_and_hides_private_price(client,tmp_path):
    import io,zipfile,hashlib
    items,customer,work,_=stock_setup(client,True);rule=publish(client,items,work);row=sale(client,rule,customer)
    response=client.post(f"/api/flow/cases/{row['id']}/documents",json={'kind':'retail_quote'})
    assert response.status_code==200,response.text
    file=response.json();assert file['generated'] and not file['template_approved'] and file['security']['can_use']
    data=client.get('/api/flow/files/'+str(file['id']));assert data.status_code==200
    with zipfile.ZipFile(io.BytesIO(data.content)) as archive:text=archive.read('word/document.xml').decode()
    assert '套餐商品分摊' in text and '套餐安装分摊' in text and '9.08' in text and '0.333' in text and '单价' not in text
    assert '尚未经门店确认' in text and not detail(client,row)['data'].get('authorized')
    (tmp_path/'retail-bundle-quotation.docx').write_bytes(data.content)
    assert client.post(f"/api/flow/cases/{row['id']}/documents",json={'kind':'retail_quote'}).json()['id']==file['id']
    row=approve(client,row);cmd(client,row,'authorize',{'revision':1,'evidence_id':file['id']},status=422)
    login(client,'inventory');assert client.get('/api/flow/files/'+str(file['id'])).status_code==403
    assert client.post(f"/api/flow/cases/{row['id']}/documents",json={'kind':'retail_quote'}).status_code==403
    login(client,'admin');publish(client,items,work,code=rule['code'],base=1,price_cents_per_set=1)
    assert hashlib.sha256(client.get('/api/flow/files/'+str(file['id'])).content).digest()==hashlib.sha256(data.content).digest()
    print('DOCX_QA',str(tmp_path/'retail-bundle-quotation.docx'))


def test_long_quote_keeps_each_component_as_separate_frozen_row(client,tmp_path):
    import io,zipfile
    from tests.test_procurement import supplier,command as pcommand,receive as preceive
    source=supplier(client)
    items=[master(client,'items',{'sku':'LONG-KIT-'+str(n),'name':'逐项冻结的长清单精品商品 '+str(n),'unit':'件','reorder':'0','active':True}) for n in range(24)]
    r=client.post('/api/procurement/orders',json={'request_id':uuid.uuid4().hex,'supplier_id':source['id'],'reason':'合成长报价的实际采购来源',
        'lines':[{'item_id':i['id'],'quantity_milli':1000,'unit_cost_cents':100} for i in items]})
    assert r.status_code==201,r.text
    preceive(client,pcommand(client,r.json(),'approve'))
    customer=master(client,'customers',{'name':'长报价合成客户','phone':'13900000803','contact_allowed':True,'note':''})
    rule=publish(client,items,price_cents_per_set=2300,components=[{'item_id':i['id'],'quantity_milli_per_set':333,'goods_reference_cents':100} for i in items])
    row=sale(client,rule,customer)
    result=client.post(f"/api/flow/cases/{row['id']}/documents",json={'kind':'retail_quote'});assert result.status_code==200,result.text
    data=client.get('/api/flow/files/'+str(result.json()['id'])).content
    from lxml import etree
    with zipfile.ZipFile(io.BytesIO(data)) as archive:root=etree.fromstring(archive.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    component_rows=[tr for tr in root.findall('.//w:tr',ns) if '套餐商品分摊' in ''.join(tr.itertext())]
    assert len(component_rows)==24 and all(len(''.join(tr.itertext()))<250 for tr in component_rows)
    (tmp_path/'retail-bundle-long-quotation.docx').write_bytes(data)
    print('DOCX_QA',str(tmp_path/'retail-bundle-long-quotation.docx'))
    validate()
