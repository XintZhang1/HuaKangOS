"""Original noncustomer income ties target, actual cash, invoice and statement facts."""
import copy,csv,io,json,sqlite3
from decimal import Decimal
import pytest
from sqlalchemy import select
from app import reconciliation_service as monthly_service
from app.backup_integrity import validate_sqlite
from app.db import SessionLocal,today
from app.models import User
from app.tenancy import set_scope
from app.reconciliation_v15 import SOURCE_FIELDS
from tests.conftest import login,TEST_DIR
from tests import test_vehicle_income as income,test_invoices as inv,test_reconciliation as monthly


def invoice(client,row,supplier,amount,original=None):
    body=inv.request_body(client,row['id'],amount,original)
    body.update(buyer_name=supplier['name'],buyer_tax_id=supplier['tax_identifier'])
    response=client.post('/api/invoices/orders',json=body)
    assert response.status_code==201,response.text
    return response.json()


def restored():
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as dest:
        source.backup(dest);return validate_sqlite(dest)


def test_income_receivable_cash_invoice_and_old_statement_scope(client,monkeypatch):
    row,supplier,_,account,_=income.ready(client,1000)
    row=income.receive(client,row,account,600)
    original=monthly_service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(monthly_service,'snapshot',lambda db,user,start,end,definition_version=14:original(db,user,start,end,14))
        old=monthly.batch(client)
    original_customer_due=old['summary']['current_receivable_cents']
    assert original_customer_due>0  # The independently unpaid original car sale remains unchanged.
    assert not set(SOURCE_FIELDS)&old['summary'].keys()
    current=monthly.cmd(client,old,'recalculate',{'reason':'按新增整车收入来源独立核对应收和原款'})
    assert current['definition_version']==monthly_service.CURRENT_DEFINITION_VERSION
    assert current['summary']['current_receivable_cents']==original_customer_due+400
    assert current['summary']['period_cash_in_cents']==current['summary']['vehicle_income_cash']['amount_cents']==600
    assert current['summary']['vehicle_income_revisions']['amount_cents']==0
    saved=copy.deepcopy(current['manifest'])
    blue=inv.record(client,inv.submit(client,inv.approve(client,invoice(client,row,supplier,1000))))
    row=income.approve(client,income.propose(client,income.detail(client,row),450))
    row=income.refund(client,row,account,row['payments'][0]['id'],150)
    assert row['totals']['receivable_cents']==row['totals']['refund_due_cents']==0
    report=client.get('/api/flow/analytics');assert report.status_code==200,report.text
    report=report.json()
    assert report['metrics']['vehicle_other_income_recognized_cents']==450
    assert report['metrics']['vehicle_other_income_cash_net_cents']==report['metrics']['cash_net_cents']==450
    assert report['metrics']['invoice_correction_cents']==550
    for name in ('vehicle_other_income_facts','vehicle_other_income_cash'):
        table=report['tables'][name];chart=next(c for c in report['charts'] if c['id']==name)
        assert sum(r['amount_cents'] for r in table['rows'])==sum(chart['series'][0]['values'])==450
        export=client.get('/api/flow/analytics/export',params={'dataset':name});assert export.status_code==200
        records=list(csv.reader(io.StringIO(export.content.decode('utf-8-sig'))))
        column=6 if name.endswith('facts') else 5
        assert records[0]==table['headers'] and sum(Decimal(r[column].removeprefix("'"))*100 for r in records[1:])==450
    assert all(r['route']=={'type':'case','id':row['id']} for r in report['tables']['cash']['rows'])
    changed=monthly.cmd(client,current,'recalculate',{'reason':'应收修订和原退款已发生，冻结当前原票待冲差额'})
    assert changed['summary']['current_receivable_cents']==original_customer_due
    assert changed['summary']['period_cash_in_cents']-changed['summary']['period_cash_out_cents']==450
    assert any(e['source']=='invoice_corrections' and e['case_id']==row['id'] for e in changed['manifest'])
    assert monthly.get(client,current)['manifest']==saved
    with SessionLocal() as db:
        set_scope(db,[1],1);user=db.scalar(select(User).where(User.username=='finance'))
        manifest,summary,_=original(db,user,today(),today(),14)
        assert not any(e['source'].startswith('vehicle_income_') or e['source']=='invoice_corrections' and e['case_id']==row['id'] for e in manifest)
        assert summary['current_receivable_cents']==original_customer_due
    assert restored()['verified_reconciliation_batches']==3
    red=inv.record(client,inv.submit(client,inv.approve(client,invoice(client,row,supplier,550,blue['id']))))
    assert red['source_basis']==blue['source_basis'] and red['balance']['actual_net_cents']==450
    assert restored()['verified_invoices']==2


@pytest.mark.parametrize('tamper',['original','summary','old_definition','invoice_basis'])
def test_income_restore_rejects_rehashed_wrong_source_or_invoice_basis(client,tamper):
    row,supplier,_,account,_=income.ready(client,1000)
    income.receive(client,row,account,1000)
    blue=inv.record(client,inv.submit(client,inv.approve(client,invoice(client,row,supplier,1000))))
    batch=monthly.batch(client)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as dest:
        source.backup(dest);validate_sqlite(dest)
        if tamper=='invoice_basis':
            event=dest.execute("SELECT id,detail FROM flow_events WHERE case_id=? AND action='invoice_v3_create'",(blue['id'],)).fetchone()
            detail=json.loads(event[1]);detail['source_basis']['buyer_name']='不能换成伪造来源'
            dest.execute('UPDATE flow_events SET detail=? WHERE id=?',(json.dumps(detail),event[0]))
        else:
            manifest=copy.deepcopy(batch['manifest']);summary=copy.deepcopy(batch['summary'])
            if tamper=='original':next(e for e in manifest if e['source']=='vehicle_income_orders')['data']['external_reference']='伪造原结算编号'
            elif tamper=='summary':summary['vehicle_income_cash']['amount_cents']+=1
            else:summary['definition_version']=14
            dest.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',(json.dumps(manifest),json.dumps(summary),monthly_service.digest({'manifest':manifest,'summary':summary}),batch['id']))
        with pytest.raises(ValueError):validate_sqlite(dest)


@pytest.mark.parametrize('step',['approve','submit'])
def test_unsubmitted_income_invoice_requires_frozen_current_approval(client,step):
    row,supplier,_,_,_=income.ready(client,1000)
    blue=invoice(client,row,supplier,400)
    if step=='submit':blue=inv.approve(client,blue)
    row=income.propose(client,income.detail(client,row),900)
    if step=='approve':login(client,'manager')
    values={'reason':'原应收正在修订，不能沿用旧开票申请','evidence_id':inv.proof(client,blue)}
    if step=='submit':values['reference']='SYNTHETIC-UNSUBMITTED'
    inv.cmd(client,blue,step,values,409)
    login(client,'finance');row=income.approve(client,row)
    if step=='approve':login(client,'manager')
    inv.cmd(client,blue,step,values,409)
    login(client,'finance');inv.cmd(client,blue,'cancel')
    assert invoice(client,row,supplier,900)['state']=='approval'
    assert restored()['verified_vehicle_income_orders']==1
