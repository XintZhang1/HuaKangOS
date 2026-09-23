"""Fee revenue, customer principal, charts and frozen original finance sources."""
import csv,io,json,sqlite3
from decimal import Decimal
import pytest
from app.db import today
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app.backup_integrity import validate_sqlite
from app import reconciliation_service as reconciliation
from tests.conftest import TEST_DIR
from tests import test_service_orders as service,test_reconciliation as monthly
from tests.test_service_analytics import report

def test_fee_facts_and_pass_principal_do_not_duplicate_cash_or_revenue(client):
    row,p,payee=service.setup(client)
    row=service.authorized(client,service.approved(client,service.quoted(client,row,p,payee)))
    data=report(client)
    assert data['metrics']['receivable_cents']==2997
    assert data['metrics']['service_fee_net_cents']==data['metrics']['cash_in_cents']==0
    assert data['metrics']['service_fee_receivable_cents']==997 and data['metrics']['service_pass_receivable_cents']==2000
    row=service.cash(client,row,'receive',2997,service.bank(client));row=service.complete_line(client,row,'fee1')
    data=report(client)
    assert data['metrics']['recorded_business_net_cents']==data['metrics']['service_fee_net_cents']==997
    assert data['metrics']['cash_in_cents']==2997 and data['metrics']['receivable_cents']==0
    assert data['tables']['agency_completed']['rows']==[]
    table=data['tables']['service_fee_facts']
    chart=next(x for x in data['charts'] if x['id']=='service_fee_facts')
    assert sum(sum(s['values']) for s in chart['series'])==sum(r['amount_cents'] for r in table['rows'])==997
    response=client.get('/api/flow/analytics/export',params={'dataset':'service_fee_facts'})
    assert response.status_code==200
    rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers'] and Decimal(rows[1][-1])*100==997
    assert data['metrics']['customer_period_amount_cents']==997
    # Blue invoice capacity is the fee, never the customer principal.
    from app.invoice_service import source_amount
    from app.db import SessionLocal
    from app.flow_models import Case
    with SessionLocal() as db:assert source_amount(db,db.get(Case,row['id']))==997

def test_service_original_advance_restore_passes_whole_backup_and_frozen_version_six(client,monkeypatch):
    service.test_advance_allocation_and_original_restore_no_fake_cash(client)
    original=reconciliation.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(reconciliation,'snapshot',lambda db,user,start,end,definition_version=5:original(db,user,start,end,5))
        old=monthly.batch(client)
    assert old['definition_version']==5 and not any(x['source'].startswith('service_') for x in old['manifest'])
    with monkeypatch.context() as patch:
        patch.setattr(reconciliation,'snapshot',lambda db,user,start,end,definition_version=6:original(db,user,start,end,6))
        new=monthly.cmd(client,old,'recalculate',{'reason':'明确增加服务原件及原款来源'})
    assert new['definition_version']==6
    selected=next(x for x in new['manifest'] if x['source']=='service_lines')
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored);checked=validate_sqlite(restored)
        assert checked['verified_service_orders']==1
        manifest=json.loads(json.dumps(new['manifest']))
        next(x for x in manifest if x['key']==selected['key'])['data']['name']='覆盖后的报价项目'
        restored.execute('UPDATE reconciliation_batches SET manifest=?,digest=? WHERE id=?',
            (json.dumps(manifest),reconciliation.digest({'manifest':manifest,'summary':new['summary']}),new['id']))
        with pytest.raises(ValueError,match='不可变原始'):validate_reconciliation_sqlite(restored)

def test_uncompleted_service_kept_actual_fee_is_recognized_only_when_termination_applied(client):
    row,p,_=service.setup(client,'other_income');row=service.authorized(client,service.approved(client,service.quoted(client,row,p)))
    row=service.termination(client,row,{'fee1':200})
    assert report(client)['metrics']['service_fee_net_cents']==0
    row=service.apply_termination(client,row)
    data=report(client)
    assert data['metrics']['service_fee_net_cents']==data['metrics']['recorded_business_net_cents']==200
    assert data['metrics']['cash_in_cents']==0 and data['metrics']['receivable_cents']==200
