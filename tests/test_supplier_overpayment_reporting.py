"""Current liability, actual original cash and versioned statements use one source."""
import copy,csv,io,json,sqlite3
from decimal import Decimal
import pytest
from sqlalchemy import select
from app.db import SessionLocal,today
from app.models import User
from app.tenancy import set_scope
from app import reconciliation_service as svc
from app.backup_integrity import validate_sqlite
from tests.conftest import login,TEST_DIR
from tests import test_finance_corrections as corrections,test_business_finance as finance,test_reconciliation as monthly


def overpaid(client):
    source,account=corrections.supplier_target(client)
    finance.command(client,source,'collect',finance.proof(client,source,amount_cents=350,account_id=account,reference='synthetic-original-supplier-receipt'))
    adjusted=corrections.approve_target(client,corrections.target_adjust(client,source,100),source)
    finance.command(client,adjusted,'execute',finance.proof(client,adjusted,source_versions=finance.versions(client,source['case'])))
    return finance.detail(client,source),account


def refund_request(client,source,amount):
    current=finance.detail(client,source)
    return finance.create(client,None,'other_return_refund',{'receivable_id':current['return_target']['receivable_id'],
        'source_version':current['case']['version'],'original_payment_id':current['supplier_refund_sources'][0]['original_payment_id'],'amount_cents':amount})


def report(client,amount,reserved=0):
    response=client.get('/api/flow/analytics');assert response.status_code==200,response.text
    data=response.json();name='finance_supplier_overpayments';table=data['tables'][name]
    chart=next(r for r in data['charts'] if r['id']==name)
    assert data['metrics']['business_finance_supplier_overpayment_cents']==sum(r['amount_cents'] for r in table['rows'])==sum(chart['series'][0]['values'])==amount
    assert sum(r['reserved_cents'] for r in table['rows'])==reserved
    exported=client.get('/api/flow/analytics/export',params={'dataset':name});assert exported.status_code==200,exported.text
    rows=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers'] and sum(Decimal(r[5])*100 for r in rows[1:])==amount
    assert data['metrics']['business_finance_other_return_due_cents']==0
    return data


def test_supplier_overpayment_not_negative_receivable_and_real_refund_once(client,monkeypatch):
    source,account=overpaid(client)
    data=report(client,250);assert data['metrics']['cash_in_cents']==350 and data['metrics']['cash_out_cents']==0
    original_snapshot=svc.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(svc,'snapshot',lambda db,user,start,end,definition_version=13:original_snapshot(db,user,start,end,13))
        old=monthly.batch(client)
    request=refund_request(client,source,100);request=finance.approve(client,request,source['case'])
    data=report(client,250,100);assert data['metrics']['cash_out_cents']==0
    held=monthly.cmd(client,old,'recalculate',{'reason':'单独冻结批准供应方超收原退及占额'})
    assert held['definition_version']==svc.CURRENT_DEFINITION_VERSION
    assert 'business_finance_supplier_refunds' not in old['summary']
    assert held['summary']['business_finance_supplier_refunds']['amount_cents']==100
    saved=copy.deepcopy(held['manifest'])
    finance.command(client,request,'execute',finance.proof(client,request,account_id=account,reference='synthetic-actual-supplier-refund',source_versions=finance.versions(client,source['case'])))
    data=report(client,150);assert data['metrics']['cash_in_cents']==350 and data['metrics']['cash_out_cents']==100
    assert sum(r['amount_cents'] for r in data['tables']['finance_allocations']['rows'])==350
    cash=data['tables']['cash']['rows'];assert len(cash)==2 and any('供应方超收原款实际退回' in r['values'] for r in cash)
    assert monthly.get(client,held)['manifest']==saved and monthly.get(client,held)['source_changed']
    after=monthly.cmd(client,held,'recalculate',{'reason':'原银行退款已实际发生，追加当前核对版本'})
    assert after['summary']['period_cash_out_cents']==100
    with sqlite3.connect(TEST_DIR/'test.sqlite') as original,sqlite3.connect(':memory:') as restored:
        original.backup(restored);assert validate_sqlite(restored)['verified_reconciliation_batches']==3
        manifest=copy.deepcopy(after['manifest']);entry=next(e for e in manifest if e['source']=='business_finance_supplier_refunds')
        entry['data']['amount_cents']+=1
        summary=copy.deepcopy(after['summary']);summary['business_finance_supplier_refunds']['amount_cents']+=1
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                         (json.dumps(manifest),json.dumps(summary),svc.digest({'manifest':manifest,'summary':summary}),after['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)


def test_current_supplier_liability_is_local_group_readonly_and_period_independent(client):
    from tests.test_multistore import second_store,switch
    source,account=overpaid(client);login(client);other=second_store(client)
    switch(client,other);assert report(client,0)['tables']['finance_supplier_overpayments']['rows']==[]
    switch(client,'all');data=report(client,250)
    assert all(r['route'] is None for r in data['tables']['finance_supplier_overpayments']['rows'])
    assert source['case']['number'] not in str(data['tables']['finance_supplier_overpayments'])
    switch(client,1);login(client,'sales');assert client.get('/api/flow/analytics/export',params={'dataset':'finance_supplier_overpayments'}).status_code==403
