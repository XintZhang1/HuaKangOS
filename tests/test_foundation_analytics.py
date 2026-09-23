"""Reconcile opening and bundle facts without counting them as business income."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import csv,io,json,sqlite3
import pytest
from sqlalchemy import select
from app.db import SessionLocal,today
from app.flow_models import Customer,Account
from app.backup_integrity import validate_sqlite
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app import reconciliation_service as service
from tests import test_recharge_bundles as bundle,test_opening_import as opening,test_business_finance as finance
from tests import test_service_analytics as analytics,test_business_finance_analytics as monthly,test_reconciliation as rec
from tests.conftest import login,TEST_DIR


def test_combination_cash_and_each_gift_unit_match_chart_rows_and_csv(client):
    a,_,_,_,purchase=bundle.setup(client)
    refund=bundle.approve(client,bundle.refund(client,a,purchase,1))
    bundle.command(client,refund,'execute',bundle.proof(client,refund,account_id=a['account_id'],reference='COMBO-REPORT-REFUND'))
    data=analytics.reconciled(client,'recharge_bundle_cash',2000)
    assert data['metrics']['cash_in_cents']==3000 and data['metrics']['cash_out_cents']==1000
    assert data['metrics']['recorded_business_net_cents']==0
    for kind,units in [('bonus',200),('points',100),('coupon',4),('package',2)]:
        key='recharge_bundle_'+kind;table=data['tables'][key];chart=next(c for c in data['charts'] if c['id']==key)
        assert sum(r['units'] for r in table['rows'])==sum(chart['series'][0]['values'])==units
        response=client.get('/api/flow/analytics/export',params={'dataset':key});assert response.status_code==200
        exported=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert exported[0]==table['headers']
        assert [[v.removeprefix("'") for v in r] for r in exported[1:]]==[[str(v) for v in r['values']] for r in table['rows']]
    login(client);client.headers['X-Store-ID']='all'
    grouped=analytics.report(client)
    assert grouped['metrics']['cash_net_cents']==2000
    assert all(r['route'] is None for r in grouped['tables']['recharge_bundle_cash']['rows'])
    client.headers['X-Store-ID']='2'
    assert not analytics.report(client)['tables']['recharge_bundle_cash']['rows']


def test_opening_balance_is_baseline_plus_actual_cash_not_period_receipts(client):
    row,_=opening.reviewed(client);opening.confirm(client,row);login(client)
    data=analytics.reconciled(client,'opening_account_balances',500001)
    assert data['metrics']['cash_in_cents']==0 and data['metrics']['recorded_business_net_cents']==0
    with SessionLocal() as db:
        customer={'id':db.scalar(select(Customer.id))};account=db.scalar(select(Account.id))
    finance.advance(client,customer,123,account)
    data=analytics.reconciled(client,'opening_account_balances',500124)
    assert data['metrics']['cash_in_cents']==123 and data['metrics']['recorded_business_net_cents']==0
    current=client.get('/api/opening-import/account-balances').json()['items'][0]
    assert current['opening_cents']==500001 and current['balance_cents']==500124


def test_definition_three_keeps_original_scope_four_tracks_new_immutable_sources(client,monkeypatch):
    a,_,_,_,purchase=bundle.setup(client)
    real=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=3:real(db,user,start,end,3))
        old=monthly.batch(client,today(),today())
    assert old['definition_version']==3 and not any(e['source'].startswith('recharge_bundle') for e in old['manifest'])
    fresh=rec.cmd(client,old,'recalculate',{'reason':'建立含原组合来源的明确新定义'})
    assert fresh['definition_version']==CURRENT_DEFINITION_VERSION
    assert fresh['summary']['period_cash_in_cents']==old['summary']['period_cash_in_cents']==3000
    assert rec.get(client,old)['digest']==old['digest']
    with sqlite3.connect(TEST_DIR/'test.sqlite') as src,sqlite3.connect(':memory:') as copy:
        src.backup(copy);validate_sqlite(copy)
        manifest=json.loads(json.dumps(fresh['manifest']))
        entry=next(e for e in manifest if e['source']=='recharge_bundle_purchases');entry['data']['shares']+=1
        hashed=service.digest({'manifest':manifest,'summary':fresh['summary']})
        copy.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',(json.dumps(manifest),hashed,fresh['id']))
        with pytest.raises(ValueError,match='不可变原始'):validate_reconciliation_sqlite(copy)
