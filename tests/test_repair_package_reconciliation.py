"""Component consideration reaches original invoice/report sources exactly once."""
import copy,csv,io,json,sqlite3,uuid
from decimal import Decimal
import pytest
from app import reconciliation_service as service
from app.backup_integrity import validate_sqlite
from app.reconciliation_v19 import SOURCE_FIELDS
from tests.conftest import TEST_DIR,login
from tests.test_repair_packages import technician
from tests import test_repair_packages as package,test_repair_orders as repair,test_reconciliation as monthly,test_invoices as invoices
from tests.test_workflow import evidence


def settled(client):
    data=package.fixture(client);row=package.quoted(client,data,extra=True)
    login(client,'finance');invoices.create(client,row['id'],1,status=409)
    row=package.finished(client,data,row)
    login(client,'finance');invoices.create(client,row['id'],1303,status=409)
    package.post(client,'/orders/'+str(row['id'])+'/capture',{'version':repair.detail(client,row)['version'],'values':{'evidence_id':evidence(client,row)}})
    row=repair.detail(client,row);row=repair.receive(client,row,row['allocations'][0],200,data['account'])
    login(client,'admin');row=repair.cmd(client,row,'release',{'evidence_id':evidence(client,row)})
    login(client,'finance');invoice=invoices.create(client,row['id'],1302)
    assert invoice['balance']['invoiceable_cents']==1302
    return data,row


def test_package_original_consideration_report_invoice_and_statement(client,monkeypatch):
    data,row=settled(client);original=service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service,'snapshot',lambda db,user,start,end,definition_version=18:original(db,user,start,end,18))
        old=monthly.batch(client)
    new=monthly.cmd(client,old,'recalculate',{'reason':'按原套餐组件对价与实际现金分别核对'})
    assert old['definition_version']==18 and not set(SOURCE_FIELDS)&old['summary'].keys()
    assert new['definition_version']==21 and new['summary']['period_cash_in_cents']==1302
    for name in SOURCE_FIELDS:assert new['summary'][name]['amount_cents']==new['summary'][name]['value_cents']==0
    assert new['summary']['repair_package_quote_snapshots']['count']==1
    assert new['summary']['repair_package_payment_links']['count']==2
    assert monthly.get(client,old)['manifest']==old['manifest']
    response=client.get('/api/flow/analytics');assert response.status_code==200,response.text
    report=response.json();assert report['metrics']['repair_cents']==report['metrics']['cash_in_cents']==1302
    assert report['metrics']['repair_package_purchase_cash_cents']==1102
    assert report['metrics']['repair_package_unconsumed_paid_cents']==report['metrics']['receivable_cents']==0
    for key,column,total in [('repair_settlements',4,1302),('repair_package_cash',4,1102),('benefit_redemptions',5,1102)]:
        response=client.get('/api/flow/analytics/export',params={'dataset':key});assert response.status_code==200,response.text
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))));assert rows[0]==report['tables'][key]['headers']
        assert sum(Decimal(r[column].removeprefix("'"))*100 for r in rows[1:])==total
    assert sum(next(c for c in report['charts'] if c['id']=='repair_value')['series'][0]['values'])==1302
    assert sum(next(c for c in report['charts'] if c['id']=='benefit_redemptions')['series'][0]['values'])==1102
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);result=validate_sqlite(restored)
        assert result['verified_repair_package_entries']==2 and result['verified_reconciliation_batches']==2


@pytest.mark.parametrize('tamper',['recognized','contract','old_definition','summary','central_source'])
def test_package_monthly_rehash_cannot_change_component_or_expose_central_source(client,tamper):
    data,row=settled(client);batch=monthly.batch(client)
    manifest=copy.deepcopy(batch['manifest']);summary=copy.deepcopy(batch['summary'])
    if tamper=='recognized':next(e for e in manifest if e['source']=='repair_package_payment_links')['data']['recognized_cents']+=1
    elif tamper=='contract':next(e for e in manifest if e['source']=='repair_package_quote_snapshots')['data']['digest']='0'*64
    elif tamper=='old_definition':summary['definition_version']=18
    elif tamper=='summary':summary['repair_package_payment_links']['amount_cents']=1601
    else:manifest.append({'key':'repair_package_purchases:1','source':'repair_package_purchases','source_id':1,'case_id':row['id'],'basis':'current','data':{'id':1,'store_id':1,'case_id':row['id']}})
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);validate_sqlite(restored)
        restored.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                         (json.dumps(manifest),json.dumps(summary),service.digest({'manifest':manifest,'summary':summary}),batch['id']))
        with pytest.raises(ValueError):validate_sqlite(restored)


def test_unused_package_refund_holds_reconcile_without_rewriting_frozen_batches(client):
    data=package.fixture(client);login(client,'finance');old=monthly.batch(client)
    refund=package.request_refund(client,data)
    login(client,'manager');refund=package.refund_action(client,data,refund,'approve')
    login(client,'finance');held=monthly.cmd(client,old,'recalculate',{'reason':'核对已批退款只占用原未用组件'})
    report=client.get('/api/flow/analytics').json()
    assert report['metrics']['repair_package_unconsumed_paid_cents']==1102
    liability=report['tables']['repair_package_liability']['rows'][0]['values']
    assert liability[1:]==['8.69','0.00','2.33']
    refund=package.refund_action(client,data,refund,'pay',amount_cents=233,account_id=data['account'],reference=uuid.uuid4().hex,evidence_id=evidence(client,data['row'],'receipt'))
    current=monthly.cmd(client,held,'recalculate',{'reason':'核对原账户真实退款及剩余原组件'})
    assert current['summary']['period_cash_in_cents']==1102 and current['summary']['period_cash_out_cents']==233
    assert monthly.get(client,held)['manifest']==held['manifest']
    report=client.get('/api/flow/analytics').json()
    assert report['metrics']['repair_package_unconsumed_paid_cents']==869
    assert report['metrics']['repair_package_refund_cash_cents']==233
    assert report['metrics']['repair_cents']==0
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);assert validate_sqlite(restored)['verified_reconciliation_batches']==3
    login(client,'admin');response=client.post('/api/stores',json={'code':'PACKAGE-REPORT','name':'套餐统计隔离门店'});assert response.status_code==201,response.text
    client.headers['X-Store-ID']='all';response=client.get('/api/flow/analytics');assert response.status_code==200,response.text
    report=response.json()
    for name in ('repair_package_cash','repair_package_components','repair_package_liability'):
        assert all(not r.get('route') and 'lot_id' not in r and 'source_id' not in r for r in report['tables'][name]['rows'])
    assert report['metrics']['repair_package_unconsumed_paid_cents']==869
