"""Retained real refunds, current cash and old statement definitions stay distinct."""
import copy,csv,io,json,sqlite3
from decimal import Decimal
import pytest
from app import reconciliation_service as service
from app.backup_integrity import validate_sqlite
from app.reconciliation_v20 import SOURCE_FIELDS
from tests.conftest import TEST_DIR,login
from tests import test_partial_receipt_corrections as partial,test_reconciliation as monthly


def fixture(client,monkeypatch,gross=9000):
    source,customer,account,origin,refund=partial.refunded_repair(client)
    original=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=19:original(db,user,start,end,19))
        old=monthly.batch(client)
    corrected=partial.apply_fix(client,customer,origin,gross,[source],account)
    login(client,'finance');new=monthly.cmd(client,old,'recalculate',{'reason':'原实际退款保留，按后继更正总收款与剩余分配核对'})
    return source,old,new,corrected


@pytest.mark.parametrize('gross',[2000,9000])
def test_partial_correction_monthly_cash_and_csv_retain_real_refund_once(client,monkeypatch,gross):
    source,old,new,fixed=fixture(client,monkeypatch,gross)
    assert old['definition_version']==19 and not set(SOURCE_FIELDS)&old['summary'].keys()
    assert old['summary']['period_cash_in_cents']==10997 and old['summary']['period_cash_out_cents']==2000
    assert new['definition_version']==21 and new['summary']['period_cash_in_cents']==gross
    assert new['summary']['period_cash_out_cents']==2000
    assert monthly.get(client,old)['manifest']==old['manifest']
    for name in SOURCE_FIELDS:
        assert new['summary'][name]['count']==1 and new['summary'][name]['amount_cents']==0
    result=client.get('/api/flow/analytics');assert result.status_code==200,result.text
    report=result.json();assert report['metrics']['cash_in_cents']==gross and report['metrics']['cash_out_cents']==2000
    assert report['metrics']['receivable_cents']==10997-gross
    response=client.get('/api/flow/analytics/export',params={'dataset':'cash'});assert response.status_code==200,response.text
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]==report['tables']['cash']['headers'] and len(rows[1:])==2
    assert sum(Decimal(r[5].removeprefix("'"))*100 for r in rows[1:])==gross+2000
    chart=next(c for c in report['charts'] if c['id']=='cash_trend')
    assert sum(chart['series'][0]['values'])==gross and sum(chart['series'][1]['values'])==2000
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_reconciliation_batches']==2


@pytest.mark.parametrize('tamper',['refund_amount','gross_amount','old_definition','summary','unknown_source'])
def test_partial_correction_monthly_rehash_cannot_invent_original_refund(client,monkeypatch,tamper):
    source,old,new,fixed=fixture(client,monkeypatch)
    manifest=copy.deepcopy(new['manifest']);summary=copy.deepcopy(new['summary'])
    if tamper=='refund_amount':next(e for e in manifest if e['source']=='business_finance_correction_refund_slices')['data']['amount_cents']+=1
    elif tamper=='gross_amount':next(e for e in manifest if e['source']=='business_finance_correction_bases')['data']['corrected_amount_cents']+=1
    elif tamper=='old_definition':summary['definition_version']=19
    elif tamper=='summary':summary['business_finance_correction_bases']['amount_cents']=9000
    else:manifest.append({'key':'business_finance_correction_refund_secret:1','source':'business_finance_correction_refund_secret','source_id':1,'case_id':None,'basis':'current','data':{'id':1,'store_id':1}})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                         (json.dumps(manifest),json.dumps(summary),service.digest({'manifest':manifest,'summary':summary}),new['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)
