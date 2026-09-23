import csv
import io
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User
from app.flow_models import Item,Case,StockMove
from app.master_models import OpeningBatch,OpeningStockEntry
from tests.conftest import login
from tests.test_multistore import second_store,switch


def source():
    """Only synthetic ledger facts in conftest's new temporary database."""
    with SessionLocal() as db:
        actor=db.scalar(select(User.id).where(User.username=='admin'))
        item=Item(sku='PERIOD',name='期间验收物资',unit='升',quantity_milli=2000,inventory_value_cents=203)
        batch=OpeningBatch(source_text='合成已核对期初',source_digest='a'*64,source_reference='TEST',
            opening_date=today()-timedelta(days=8),totals={},prepared_by=actor)
        case=Case(number='PERIOD-FACTS',kind='purchase',flow_version=2,title='合成库存来源',state='completed',created_by=actor,owner_id=actor,business_date=today()-timedelta(days=8))
        db.add_all([item,batch,case]);db.flush()
        db.add(OpeningStockEntry(batch_id=batch.id,item_id=item.id,quantity_milli=2000,value_cents=203,
            business_date=today()-timedelta(days=8),source_reference='合成盘点',actor_id=actor))
        for days,qty,value,purpose in [(7,1000,101,'purchase'),(5,-500,-50,'issue'),(3,250,25,'return'),(1,-750,-76,'issue')]:
            db.add(StockMove(case_id=case.id,item_id=item.id,quantity_milli=qty,value_cents=value,unit_cost_cents=101,
                business_date=today()-timedelta(days=days),purpose=purpose,actor_id=actor))
        db.commit();return item.id


def query(item=None):
    result={'date_from':(today()-timedelta(days=5)).isoformat(),'date_to':(today()-timedelta(days=2)).isoformat()}
    if item:result['item_id']=item
    return result


def test_period_reconstructs_past_not_current_and_chart_csv_reconcile(client):
    key=source();report=client.get('/api/stock-reports/period',params=query(key)).json();row=report['rows'][0]
    assert report['complete'] and row['opening']=={'quantity_milli':3000,'value_cents':304}
    assert row['in']=={'quantity_milli':250,'value_cents':25}
    assert row['out']=={'quantity_milli':500,'value_cents':50}
    assert row['closing']=={'quantity_milli':2750,'value_cents':279}
    assert report['chart']['series'][0]['values']==[304,25,50,279]
    assert len(report['details'])==2 and sum(x['value_cents'] for x in report['details'])==-25
    response=client.get('/api/stock-reports/period/export',params=query(key));assert response.status_code==200
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows==[report['table']['headers'],report['table']['rows'][0]['values']]
    assert 'huakangos' in response.headers['content-disposition']


def test_missing_opening_does_not_invent_period_balances(client):
    with SessionLocal() as db:
        item=Item(sku='NO-SOURCE',name='无来源合成物资',quantity_milli=1000,inventory_value_cents=100);db.add(item);db.commit();key=item.id
    report=client.get('/api/stock-reports/period',params=query(key)).json();row=report['rows'][0]
    assert not report['complete'] and report['chart'] is None
    assert row['closing']=={'quantity_milli':None,'value_cents':None}
    assert row['quantity_variance_milli']==1000 and row['value_variance_cents']==100
    assert '差异' in row['status']


def test_period_stock_and_export_enforce_role_and_store(client):
    key=source();other=second_store(client);switch(client,other)
    assert client.get('/api/stock-reports/period',params=query(key)).status_code==404
    assert client.get('/api/stock-reports/period/export',params=query(key)).status_code==404
    assert client.get('/api/stock-reports/period').json()['rows']==[]
    switch(client,'all');assert len(client.get('/api/stock-reports/period',params=query()).json()['rows'])==1
    switch(client,1);login(client,'inventory')
    report=client.get('/api/stock-reports/period',params=query(key)).json()
    assert report['complete'] and not report['can_money'] and report['chart'] is None
    assert 'value_cents' not in report['rows'][0]['closing'] and 'value_cents' not in report['details'][0]
    exported=client.get('/api/stock-reports/period/export',params=query(key));assert '价值' not in exported.text
    login(client,'sales')
    assert client.get('/api/stock-reports/period').status_code==403
    assert client.get('/api/stock-reports/period/export').status_code==403


@pytest.mark.parametrize('params',[{'date_from':'2020-01-01'},{'date_to':(today()+timedelta(days=1)).isoformat()},
    {'date_from':today().isoformat(),'date_to':(today()-timedelta(days=1)).isoformat()}])
def test_period_boundaries_refused(client,params):
    assert client.get('/api/stock-reports/period',params=params).status_code==422


def test_oversize_source_is_not_silently_truncated(client,monkeypatch):
    key=source();monkeypatch.setattr('app.stock_reports.LIMIT',3)
    assert client.get('/api/stock-reports/period',params=query(key)).status_code==422


def test_csv_formula_cell_is_neutralized(client):
    with SessionLocal() as db:
        item=Item(sku='=1+2',name='@SUM(1,2)',unit='件');db.add(item);db.commit()
    response=client.get('/api/stock-reports/period/export')
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[1][1:3]==["'=1+2","'@SUM(1,2)"]
