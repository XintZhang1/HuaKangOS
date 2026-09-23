"""Commission-only invoice coordination through registered employee APIs."""
import csv
import io
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db import SessionLocal, today
from app.models import CashEntry, User
from app.flow_models import Case, Task, PaymentLink
from app.invoice_models import InvoiceApplication, InvoiceResult
from app.invoice_backup_integrity import validate_invoices_sqlite
from tests.conftest import login, TEST_DIR
from tests import test_insurance_orders as insurance
from tests import test_invoices as invoice
from tests.test_multistore import second_store, switch


def prepare(client, target=501, confirmed=True):
    row, _, _ = insurance.setup(client, 'customer_direct')
    row = insurance.issued(client, insurance.ready(client, row))
    if confirmed:
        login(client, 'finance')
        row = insurance.commission(client, row, target)
    login(client, 'finance')
    return row


def body(client, row, amount=501, original=None):
    values = invoice.request_body(client, row['id'], amount, original)
    values.update(buyer_name='合成保险公司', buyer_tax_id='TESTINSURER000001')
    return values


def request(client, row, amount=501, original=None, status=201):
    response = client.post('/api/invoices/orders', json=body(client, row, amount, original))
    assert response.status_code == status, response.text
    return response.json()


def actual(client, row, amount=501, original=None):
    return invoice.record(client, invoice.submit(client, invoice.approve(client, request(client, row, amount, original))))


def totals():
    with SessionLocal() as db:
        return [db.scalar(select(func.count()).select_from(model)) for model in (CashEntry, PaymentLink, InvoiceResult)]


def test_premium_and_expected_or_pending_commission_never_become_invoice_basis(client):
    row = prepare(client, confirmed=False)
    source = client.get('/api/invoices/sources/' + str(row['id'])).json()
    assert source['invoiceable_cents'] == 0
    request(client, row, 1, status=409)
    row = insurance.cmd(client, row, 'commission', dict(target_cents=499, reason='实际结算确认待独立批准', evidence_id=insurance.proof(client, row, True)))
    request(client, row, 1, status=409)
    login(client, 'manager')
    row = insurance.cmd(client, row, 'commission_review', dict(confirmation_id=row['commissions'][-1]['id'], decision='approved', reason='复核实际佣金', business_date=today().isoformat(), evidence_id=insurance.proof(client, row, True)))
    login(client, 'finance')
    source = client.get('/api/invoices/sources/' + str(row['id'])).json()
    assert source['invoiceable_cents'] == 499
    assert source['source_basis']['buyer_name'] == '合成保险公司'
    request(client, row, 500, status=409)
    request(client, row, 10001, status=409)
    blue = actual(client, row, 499)
    assert blue['balance']['actual_net_cents'] == 499
    assert totals() == [0, 0, 1]


@pytest.mark.parametrize('change', [{'buyer_name':'投保客户'}, {'buyer_tax_id':''}])
def test_insurer_is_the_commission_buyer_not_the_customer(client, change):
    row = prepare(client)
    response = client.post('/api/invoices/orders', json={**body(client,row), **change})
    assert response.status_code == 422, response.text
    assert totals() == [0,0,0]


def test_partial_red_after_commission_reduction_keeps_premium_and_cash_separate(client):
    row = prepare(client)
    blue = actual(client, row)
    row = insurance.commission(client, row, 200)
    with SessionLocal() as db:
        assert db.scalar(select(Task.status).where(Task.case_id==row['id'],Task.key=='invoice_adjust'))=='open'
    red = request(client, row, 301, blue['id'])
    assert red['balance']['available_cents']==0 and red['balance']['correction_cents']==301
    request(client, row, 1, status=409)
    red = invoice.record(client, invoice.submit(client, invoice.approve(client, red)))
    assert red['balance']['actual_net_cents']==200 and red['balance']['correction_cents']==0
    assert red['source_basis']==blue['source_basis']
    with SessionLocal() as db:
        assert db.scalar(select(Task.status).where(Task.case_id==row['id'],Task.key=='invoice_adjust'))=='done'
    assert insurance.detail(client,row)['summary']['quoted_premium_cents']==10001
    assert totals()==[0,0,2]
    report=client.get('/api/flow/analytics').json()
    table=report['tables']['invoices'];chart=next(c for c in report['charts'] if c['id']=='invoices')
    assert report['metrics']['invoice_net_cents']==sum(r['amount_cents'] for r in table['rows'])==sum(chart['series'][0]['values'])==200
    exported=client.get('/api/flow/analytics/export',params={'dataset':'invoices'})
    rows=list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert rows[0]==table['headers'] and sum(Decimal(r[-1].removeprefix("'"))*100 for r in rows[1:])==200


@pytest.mark.parametrize('stage', ['approve','submit'])
def test_changed_confirmation_requires_new_unsubmitted_application(client, stage):
    row=prepare(client);blue=request(client,row,400)
    if stage=='submit':blue=invoice.approve(client,blue)
    row=insurance.commission(client,row,450)
    if stage=='approve':
        login(client,'manager')
        invoice.cmd(client,blue,'approve',dict(reason='不能沿旧佣金依据批准',evidence_id=invoice.proof(client,blue)),409)
        login(client,'finance')
    else:
        invoice.cmd(client,blue,'submit',dict(reason='不能沿旧佣金依据提交',reference='SYNTHETIC',evidence_id=invoice.proof(client,blue)),409)
    invoice.cmd(client,blue,'cancel')
    assert request(client,row,450)['state']=='approval'


def test_real_result_after_commission_change_is_retained_with_independent_review(client):
    row=prepare(client);blue=invoice.submit(client,invoice.approve(client,request(client,row)))
    row=insurance.commission(client,row,100)
    blue=invoice.record(client,blue)
    assert blue['state']=='resolving' and blue['balance']['correction_cents']==401
    login(client,'manager')
    invoice.cmd(client,blue,'review_result',dict(reason='核对实际外部票据，另办原票冲红',evidence_id=invoice.proof(client,blue)))
    login(client,'finance');red=actual(client,row,401,blue['id'])
    assert red['balance']['actual_net_cents']==100 and totals()==[0,0,2]


def test_replay_stale_and_cross_store_cannot_duplicate_or_expose_commission(client):
    row=prepare(client);payload=body(client,row,300)
    first=client.post('/api/invoices/orders',json=payload);assert first.status_code==201
    replay=client.post('/api/invoices/orders',json=payload);assert replay.status_code==201 and replay.json()['id']==first.json()['id']
    assert client.post('/api/invoices/orders',json={**payload,'request_id':uuid.uuid4().hex}).status_code==409
    login(client,'sales');assert client.get('/api/invoices/sources/'+str(row['id'])).status_code==403
    login(client);other=second_store(client);switch(client,other)
    assert client.get('/api/invoices/sources/'+str(row['id'])).status_code==404
    assert client.get('/api/invoices/orders/'+str(first.json()['id'])).status_code==404
    assert client.post('/api/invoices/orders',json={**payload,'request_id':uuid.uuid4().hex}).status_code==404
    assert client.get('/api/invoices/orders').json()['total']==0


def test_competing_partial_applications_reserve_only_confirmed_commission(client):
    from app import invoice_service as service
    from app.tenancy import set_scope, project_user
    row=prepare(client);payload=body(client,row,400);payload.pop('request_id');payload['due_date']=today()
    def attempt(_):
        with SessionLocal() as db:
            set_scope(db,[1],1)
            actor=project_user(db.scalar(select(User).where(User.username=='finance')),'finance')
            try:service.create(db,actor,uuid.uuid4().hex,payload);return 201
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,range(2)))==[201,409]
    source=client.get('/api/invoices/sources/'+str(row['id'])).json()
    assert source['pending_blue_cents']==400 and source['available_cents']==101


@pytest.mark.parametrize('tamper', ['basis','buyer','approval','amount'])
def test_independent_restore_checks_original_approved_commission_basis(client,tamper):
    row=prepare(client);blue=actual(client,row)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source,sqlite3.connect(':memory:') as restored:
        source.backup(restored)
        assert validate_invoices_sqlite(restored)=={'verified_invoices':1}
        if tamper=='basis':
            key,raw=restored.execute("SELECT id,detail FROM flow_events WHERE action='invoice_v3_create'").fetchone()
            details=json.loads(raw);details['source_basis']['confirmed_cents']+=1
            restored.execute('UPDATE flow_events SET detail=? WHERE id=?',(json.dumps(details),key))
        elif tamper=='buyer':restored.execute("UPDATE invoice_applications SET buyer_name='投保客户'")
        elif tamper=='approval':restored.execute("UPDATE insurance_commission_reviews SET decision='rejected'")
        else:restored.execute('UPDATE insurance_commissions SET target_cents=target_cents+1')
        with pytest.raises(ValueError,match='佣金'):validate_invoices_sqlite(restored)
