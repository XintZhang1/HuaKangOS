"""Synthetic multi-store principal-wallet acceptance and refusal scenarios."""
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import hashlib
import sqlite3
from decimal import Decimal
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db import SessionLocal, today
from app.main import app
from app.models import Store, User, UserStore, CashEntry, Vehicle
from app.flow_models import Customer, Case, Account, FileAsset, Member, Task, Reference
from app.group_models import (GroupMember, GroupEntry, GroupSettlementEntry,
    GroupIdentity, GroupIdentityLink, GroupPaymentLink, GroupRefundRequest)
from app.group_service import authority, case_paid_amount, case_reserved_amount
from app.tenancy import set_scope
from tests.conftest import login, TEST_DIR


def seed(store=1, name='集团测试客户', phone='13912345678', amount=10000):
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == 'admin'))
        finance = db.scalar(select(User).where(User.username == 'finance'))
        if not db.scalar(select(Store.id).where(Store.id == store)):
            db.add(Store(id=store, code='S'+str(store), name='模拟门店'+str(store)))
            db.flush()
            db.add(UserStore(user_id=finance.id, store_id=store))
        customer = Customer(store_id=store, name=name, phone=phone, owner_id=admin.id)
        account = Account(store_id=store, name='模拟收款'+uuid.uuid4().hex[:8])
        db.add_all([customer, account])
        db.flush()
        case = Case(store_id=store, number='TEST-'+uuid.uuid4().hex, kind='repair', state='settling',
            title='集团会员测试维修', owner_id=admin.id, created_by=admin.id, customer_id=customer.id,
            amount_cents=amount, business_date=today(), data={'payer': '客户'})
        db.add(case)
        db.flush()
        asset = FileAsset(store_id=store, case_id=case.id, category='receipt', name='模拟凭据.txt',
            media_type='text/plain', sha256=hashlib.sha256(b'test').hexdigest(), size=4, content=b'test', created_by=admin.id)
        db.add(asset)
        db.add(Task(store_id=store, case_id=case.id, key='receive', title='登记维修款到账', role='finance',
                    assignee_id=finance.id, due_date=today()))
        db.flush()
        from app.file_security import initialize_file_security
        set_scope(db, [store], store)
        initialize_file_security(db, admin, case, asset)
        db.commit()
        return {'case_id': case.id, 'customer_id': customer.id, 'account_id': account.id,
                'evidence_id': asset.id, 'store_id': store}


def switch(c, store):
    c.headers['X-Store-ID'] = str(store)


def link(c, setup, target=None, status=201):
    response = c.post('/api/group/identities/link', json={'request_id': uuid.uuid4().hex,
        'kind': 'customer', 'local_id': setup['customer_id'], 'identity_id': target})
    assert response.status_code == status, response.text
    return response.json()


def issue(c, setup):
    identity = link(c, setup)
    response = c.post('/api/group/members', json={'request_id': uuid.uuid4().hex, 'identity_id': identity['identity_id']})
    assert response.status_code == 201, response.text
    return response.json()['member']


def wallet(c, member):
    r = c.get('/api/group/members/'+str(member['id']))
    assert r.status_code == 200, r.text
    return r.json()['member']


def case_version(case_id):
    with SessionLocal() as db:
        return db.scalar(select(Case.version).where(Case.id == case_id))


def cmd(c, member, action, values, status=200, key=None, version=None):
    request = {'request_id': key or uuid.uuid4().hex,
               'version': version if version is not None else wallet(c, member)['version'], 'values': values}
    response = c.post(f"/api/group/members/{member['id']}/actions/{action}", json=request)
    assert response.status_code == status, response.text
    return response.json()


def topup_values(setup, amount=10000, reference=None):
    return {k: setup[k] for k in ('case_id', 'account_id', 'evidence_id')} | {
        'case_version': case_version(setup['case_id']), 'amount_cents': amount,
        'reference': reference or uuid.uuid4().hex}


def reserve_values(setup, amount=5000):
    return {k: setup[k] for k in ('case_id', 'evidence_id')} | {
        'case_version': case_version(setup['case_id']), 'amount_cents': amount}


def reservation_values(setup, reserved):
    return {'case_version': case_version(setup['case_id']), 'reservation_id': reserved['reservation']['id'],
            'reservation_version': reserved['reservation']['version'], 'evidence_id': setup['evidence_id']}


def refund_request_values(setup, original, amount=5000):
    return {'original_id': original['entry_id'], 'amount_cents': amount,
            'case_version': case_version(setup['case_id']), 'evidence_id': setup['evidence_id'], 'reason': '客户申请退还本金'}


def refund_review_values(setup, request):
    return {'refund_request_id': request['refund_request']['id'],
            'refund_request_version': request['refund_request']['version'],
            'case_version': case_version(setup['case_id']), 'reason': '核对客户申请与原充值'}


def refund_payment_values(setup, approved):
    values = refund_review_values(setup, approved)
    values.pop('reason')
    return values | {'account_id': setup['account_id'], 'reference': uuid.uuid4().hex,
                     'evidence_id': setup['evidence_id']}


def test_group_cross_store_principal_conservation_and_original_refund(client):
    a, b = seed(), seed(2)
    member = issue(client, a)
    topup = cmd(client, member, 'topup', topup_values(a))
    switch(client, 2)
    assert client.get(f"/api/group/members/{member['id']}").status_code == 404
    candidates = client.get('/api/group/identities', params={'kind': 'customer', 'q': '13912345678'}).json()['items']
    assert candidates == [{'id': member['identity_id'], 'kind': 'customer', 'name': '集＊＊＊＊＊', 'linked': False}]
    link(client, b, member['identity_id'])
    assert wallet(client, member)['balance_cents'] == 10000
    assert client.get(f"/api/group/members/{member['id']}").json()['entries'] == []
    login(client, 'finance')
    held = cmd(client, member, 'reserve', reserve_values(b, 7000))
    assert held['member']['available_cents'] == 3000
    captured = cmd(client, member, 'capture', reservation_values(b, held))
    assert captured['member']['balance_cents'] == 3000
    cmd(client, member, 'reverse', {'original_id': captured['entry_id'], 'amount_cents': 2000,
        'case_version': case_version(b['case_id']), 'evidence_id': b['evidence_id'], 'reason': '客户确认扣款更正'})
    # Group receipts are not cross-store authority to refund A's money from B.
    bad_refund = refund_request_values(b, topup)
    cmd(client, member, 'refund_request', bad_refund, 404)
    switch(client, 1)
    requested = cmd(client, member, 'refund_request', refund_request_values(a, topup))
    login(client, 'manager')
    approved = cmd(client, member, 'refund_approve', refund_review_values(a, requested))
    login(client, 'finance')
    cmd(client, member, 'refund', refund_payment_values(a, approved))
    assert wallet(client, member)['balance_cents'] == 0
    with SessionLocal() as db:
        cash = list(db.scalars(select(CashEntry)))
        assert len(cash) == 2
        net_cash = sum(r.amount_cents*(1 if r.direction == 'in' else -1) for r in cash)
        assert net_cash == 5000 == case_paid_amount(db, b['case_id'])
        assert case_reserved_amount(db, b['case_id']) == 0
        assert db.scalar(select(func.count()).select_from(Member)) == 0
        assert db.scalar(select(func.sum(GroupSettlementEntry.amount_cents))) == 0
        assert db.scalar(select(func.count()).select_from(GroupSettlementEntry)) == 8
    rec = client.get('/api/group/reconciliation').json()
    assert rec['purpose_totals_cents'] == {'refund': -5000, 'topup': 10000}
    assert rec['center_receivable_cents'] == 5000 and rec['clearing_sum_cents'] == 0


def test_group_same_phone_is_not_automatic_identity_merge(client):
    a, b = seed(), seed()
    first = issue(client, a)
    second = issue(client, b)
    assert first['identity_id'] != second['identity_id']
    assert len(client.get('/api/group/identities', params={'kind': 'customer', 'q': '13912345678'}).json()['items']) == 2
    assert client.get('/api/group/identities', params={'kind': 'customer', 'q': '139'}).status_code == 422
    link(client, a, second['identity_id'], 409)
    mismatch = seed(name='另一位客户')
    link(client, mismatch, first['identity_id'], 409)


def test_group_duplicate_and_stale_commands_do_not_repeat_cash(client):
    a = seed()
    member = issue(client, a)
    key = uuid.uuid4().hex
    values = topup_values(a)
    one = cmd(client, member, 'topup', values, key=key, version=1)
    two = cmd(client, member, 'topup', values, key=key, version=1)
    assert one == two
    cmd(client, member, 'topup', values | {'amount_cents': 20000}, 409, key=key, version=1)
    cmd(client, member, 'topup', topup_values(a), 409, version=1)
    cmd(client, member, 'topup', topup_values(a, reference=values['reference']), 409)
    stale_case = topup_values(a) | {'case_version': 1}
    cmd(client, member, 'topup', stale_case, 409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry)) == 1


def test_group_release_restores_availability_and_refund_is_capped(client):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    held = cmd(client, member, 'reserve', reserve_values(a, 9000))
    refund = cmd(client, member, 'refund_request', refund_request_values(a, original, 2000))
    cmd(client, member, 'refund_approve', refund_review_values(a, refund), 409)
    vals = reservation_values(a, held)
    vals.pop('evidence_id')
    released = cmd(client, member, 'release', vals | {'reason': '客户改用银行付款'})
    assert released['member']['reserved_cents'] == 0 and released['member']['available_cents'] == 10000
    cmd(client, member, 'capture', reservation_values(a, held), 409)
    cmd(client, member, 'refund_cancel', refund_review_values(a, refund))
    refund = cmd(client, member, 'refund_request', refund_request_values(a, original, 10000))
    approved = cmd(client, member, 'refund_approve', refund_review_values(a, refund))
    cmd(client, member, 'refund', refund_payment_values(a, approved))
    cmd(client, member, 'topup', topup_values(a, 5000))
    cmd(client, member, 'refund_request', refund_request_values(a, original, 1), 409)
    assert wallet(client, member)['available_cents'] == 5000


def test_group_permissions_cross_store_facts_and_strict_amounts(client):
    a, b = seed(), seed(2)
    member = issue(client, a)
    vals = topup_values(a)
    login(client, 'service')
    cmd(client, member, 'topup', vals, 403)
    login(client, 'finance')
    cmd(client, member, 'topup', vals | {'account_id': b['account_id']}, 404)
    cmd(client, member, 'topup', vals | {'evidence_id': b['evidence_id']}, 422)
    cmd(client, member, 'topup', vals | {'case_id': b['case_id']}, 404)
    for amount in [0, -1, 1.01, '100', True]:
        cmd(client, member, 'topup', vals | {'amount_cents': amount}, 422)
    login(client, 'admin')
    switch(client, 'all')
    assert client.get(f"/api/group/members/{member['id']}").status_code == 409
    switch(client, 1)
    assert wallet(client, member)['balance_cents'] == 0


def test_group_wrong_customer_or_unexecuted_service_cannot_redeem(client):
    a, wrong = seed(), seed(name='别人', phone='13811112222')
    member = issue(client, a)
    cmd(client, member, 'topup', topup_values(a))
    cmd(client, member, 'reserve', reserve_values(wrong), 409)
    for state, payer in [('working', '客户'), ('settling', '保险'), ('completed', '客户')]:
        with SessionLocal() as db:
            row = db.scalar(select(Case).where(Case.id == a['case_id']))
            row.state = state
            row.data = {'payer': payer}
            db.commit()
        cmd(client, member, 'reserve', reserve_values(a), 409)


def test_group_unscoped_access_and_history_overwrite_are_rejected(client):
    a = seed()
    member = issue(client, a)
    topup = cmd(client, member, 'topup', topup_values(a))
    with SessionLocal() as db:
        with pytest.raises(HTTPException):
            db.scalar(select(GroupMember))
        admin = db.scalar(select(User).where(User.username == 'admin'))
        set_scope(db, [1], 1)
        with authority(db, admin):
            entry = db.scalar(select(GroupEntry).where(GroupEntry.id == topup['entry_id']))
            entry.amount_cents = 9999
            with pytest.raises(HTTPException):
                db.flush()
            db.rollback()
            row = db.scalar(select(GroupMember).where(GroupMember.id == member['id']))
            row.reserved_cents = row.balance_cents+1
            with pytest.raises(IntegrityError):
                db.flush()
            db.rollback()


def test_group_competing_reservations_cannot_overspend(client):
    a = seed()
    member = issue(client, a)
    cmd(client, member, 'topup', topup_values(a))
    # Both callers hold the same observed versions before either command starts.
    body = {'version': wallet(client, member)['version'], 'values': reserve_values(a, 7000)}
    with TestClient(app) as other:
        login(other)
        def run(c):
            return c.post(f"/api/group/members/{member['id']}/actions/reserve",
                          json=body | {'request_id': uuid.uuid4().hex}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, [client, other]))
    assert sorted(results) == [200, 409]
    balance = wallet(client, member)
    assert balance['reserved_cents'] == 7000 and balance['available_cents'] == 3000


def test_group_reservation_blocks_cash_and_local_wallet_double_collection(client):
    a = seed()
    member = issue(client, a)
    cmd(client, member, 'topup', topup_values(a))
    held = cmd(client, member, 'reserve', reserve_values(a, 10000))
    body = {'version': case_version(a['case_id']), 'request_id': uuid.uuid4().hex,
            'values': {'amount': '100', 'account_id': a['account_id'], 'evidence_id': a['evidence_id'], 'reference': 'duplicate-cash'}}
    response = client.post(f"/api/flow/cases/{a['case_id']}/actions/receive", json=body)
    assert response.status_code == 409, response.text
    completed = cmd(client, member, 'capture', reservation_values(a, held))
    assert completed['member']['balance_cents'] == 0
    assert client.get(f"/api/flow/cases/{a['case_id']}").json()['paid_cents'] == 10000


def test_group_vin_and_counterparty_exact_identity_links(client):
    a = seed()
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.username == 'admin'))
        vehicle = Vehicle(store_id=1, doc_no='VIN-IDENTITY', business_date=today(), created_by=uid,
            vin='LHK12345678901234', brand='合成品牌', model='合成车型', purchase_cost_cents=100, list_price_cents=200)
        db.add(vehicle)
        db.commit()
        vid = vehicle.id
    response = client.post('/api/flow/master/references', json={'values': {
        'category': '供应商', 'name': '合成供应商', 'detail': '测试专用', 'active': True}})
    assert response.status_code == 201, response.text
    sid = response.json()['id']
    for kind, local_id, identifier, query in [('vehicle', vid, '', 'LHK12345678901234'),
                                              ('counterparty', sid, '911101010000000001', '911101010000000001')]:
        response = client.post('/api/group/identities/link', json={'request_id': uuid.uuid4().hex,
            'kind': kind, 'local_id': local_id, 'identifier': identifier})
        assert response.status_code == 201, response.text
        items = client.get('/api/group/identities', params={'kind': kind, 'q': query}).json()['items']
        assert items[0]['id'] == response.json()['identity_id'] and items[0]['linked']


def test_group_cash_cannot_be_voided_and_analytics_do_not_double_count(client):
    a = seed()
    member = issue(client, a)
    cmd(client, member, 'topup', topup_values(a))
    held = cmd(client, member, 'reserve', reserve_values(a, 7000))
    captured = cmd(client, member, 'capture', reservation_values(a, held))
    analytics = client.get('/api/flow/analytics').json()
    assert analytics['metrics']['cash_in_cents'] == 10000
    assert analytics['metrics']['cash_out_cents'] == 0
    assert analytics['metrics']['receivable_cents'] == 3000
    assert len(analytics['tables']['cash']['rows']) == 1
    assert sum(r['amount_cents'] for r in analytics['tables']['receivables']['rows']) == 3000
    assert analytics['metrics']['member_balance_cents'] == 0  # Existing metric is LOCAL membership only.
    with SessionLocal() as db:
        cash = db.scalar(select(CashEntry))
        cash_id, version = cash.id, cash.version
    response = client.post(f'/api/records/cash/{cash_id}/actions/void',
                           json={'version': version, 'reason': '尝试绕过集团本金账本'})
    assert response.status_code == 409, response.text
    assert captured['member']['balance_cents'] == 3000


def test_group_role_is_current_store_role_not_account_default(client):
    a = seed()
    member = issue(client, a)
    with SessionLocal() as db:
        finance_id = db.scalar(select(User.id).where(User.username == 'finance'))
        relation = db.scalar(select(UserStore).where(UserStore.user_id == finance_id, UserStore.store_id == 1))
        relation.role = 'service'
        db.commit()
    login(client, 'finance')
    cmd(client, member, 'topup', topup_values(a), 403)


def test_group_competing_cross_store_reserve_and_refund_approval_conserve_principal(client):
    a, b = seed(), seed(2)
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    switch(client, 2)
    link(client, b, member['identity_id'])
    switch(client, 1)
    request = cmd(client, member, 'refund_request', refund_request_values(a, original, 7000))
    version = wallet(client, member)['version']
    refund = refund_review_values(a, request)
    reserve = reserve_values(b, 7000)
    with TestClient(app) as second:
        login(second)
        switch(second, 2)
        def run(args):
            c, action, values = args
            return c.post(f"/api/group/members/{member['id']}/actions/{action}",
                json={'version': version, 'values': values, 'request_id': uuid.uuid4().hex}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(run, [(client, 'refund_approve', refund), (second, 'reserve', reserve)]))
    assert sorted(result) == [200, 409]
    current = wallet(client, member)
    assert current['available_cents'] == 3000
    assert (current['balance_cents'], current['reserved_cents']) == (10000, 7000)


def test_group_topup_refuses_terminal_and_legacy_member_source(client):
    a = seed()
    member = issue(client, a)
    for state, kind in [('completed', 'repair'), ('cancelled', 'order'), ('pending', 'member_topup')]:
        with SessionLocal() as db:
            case = db.scalar(select(Case).where(Case.id == a['case_id']))
            case.state, case.kind = state, kind
            db.commit()
        cmd(client, member, 'topup', topup_values(a), 409)
    assert wallet(client, member)['balance_cents'] == 0


def test_group_issue_requires_local_customer_ownership_for_sales(client):
    a = seed()
    identity = link(client, a)
    login(client, 'sales')
    response = client.post('/api/group/members', json={'request_id': uuid.uuid4().hex,
                                                     'identity_id': identity['identity_id']})
    assert response.status_code == 403, response.text


def test_group_financial_actions_fail_closed_for_unknown_workflow_version(client):
    a = seed()
    member = issue(client, a)
    cmd(client, member, 'topup', topup_values(a))
    held = cmd(client, member, 'reserve', reserve_values(a))
    with SessionLocal() as db:
        row = db.scalar(select(Case).where(Case.id == a['case_id']))
        row.flow_version = 999
        db.commit()
    cmd(client, member, 'capture', reservation_values(a, held), 409)
    cmd(client, member, 'reserve', reserve_values(a, 100), 409)
    assert wallet(client, member)['balance_cents'] == 10000


def test_group_clearing_chart_table_and_csv_share_two_store_population(client):
    a, b = seed(amount=0), seed(2)
    member = issue(client, a)
    cmd(client, member, 'topup', topup_values(a))
    switch(client, 2)
    link(client, b, member['identity_id'])
    held = cmd(client, member, 'reserve', reserve_values(b, 6000))
    cmd(client, member, 'capture', reservation_values(b, held))
    store_report = client.get('/api/flow/analytics').json()
    assert store_report['metrics']['cash_in_cents'] == 0
    assert store_report['metrics']['receivable_cents'] == 4000
    switch(client, 'all')
    report = client.get('/api/flow/analytics').json()
    assert report['metrics']['cash_in_cents'] == 10000
    assert report['metrics']['receivable_cents'] == 4000
    assert report['metrics']['repair_cents'] == 0  # No completed service yet.
    chart = next(c for c in report['charts'] if c['id'] == 'group_clearing')
    rows = report['tables']['group_clearing']['rows']
    assert len(rows) == len(chart['labels']) == 2
    for index, row in enumerate(rows):
        assert row['values'][0] == chart['labels'][index]
        assert int(Decimal(row['values'][1])*100) == chart['series'][0]['values'][index]
        assert int(Decimal(row['values'][2])*100) == chart['series'][1]['values'][index]
        assert Decimal(row['values'][3]) == 0
    assert sum(sum(s['values']) for s in chart['series']) == 0
    exported = client.get('/api/flow/analytics/export?dataset=group_clearing')
    assert exported.status_code == 200, exported.text
    csv_rows = list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert csv_rows[0] == report['tables']['group_clearing']['headers']
    assert len(csv_rows)-1 == len(rows)
    for csv_row, table_row in zip(csv_rows[1:], rows):
        assert [x.removeprefix("'") for x in csv_row] == table_row['values']


def test_group_refund_requires_separate_review_and_exact_approved_execution(client):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    login(client, 'service')
    request = cmd(client, member, 'refund_request', refund_request_values(a, original, 4000))
    assert request['refund_request']['status'] == 'requested'
    assert request['member']['reserved_cents'] == 0
    login(client, 'finance')
    cmd(client, member, 'refund', refund_payment_values(a, request), 409)
    cmd(client, member, 'refund_approve', refund_review_values(a, request), 403)
    old_direct = topup_values(a, 4000) | {'original_id': original['entry_id'], 'reason': '尝试绕过审核'}
    old_direct.pop('case_id')
    cmd(client, member, 'refund', old_direct, 422)
    login(client, 'manager')
    approved = cmd(client, member, 'refund_approve', refund_review_values(a, request))
    assert approved['member']['reserved_cents'] == 4000
    assert approved['member']['balance_cents'] == 10000
    cmd(client, member, 'refund', refund_payment_values(a, approved), 403)
    login(client, 'finance')
    payment = refund_payment_values(a, approved)
    cmd(client, member, 'refund', payment | {'amount_cents': 1000}, 422)
    cmd(client, member, 'refund', payment | {'original_id': original['entry_id']}, 422)
    key, version = uuid.uuid4().hex, wallet(client, member)['version']
    paid = cmd(client, member, 'refund', payment, key=key, version=version)
    replay = cmd(client, member, 'refund', payment, key=key, version=version)
    assert paid == replay
    assert paid['refund_request']['status'] == 'executed'
    assert paid['member']['balance_cents'] == 6000 and paid['member']['reserved_cents'] == 0
    cmd(client, member, 'refund_cancel', refund_review_values(a, paid), 409)
    with SessionLocal() as db:
        tasks = list(db.scalars(select(Task).where(Task.case_id == a['case_id'], Task.key.startswith('group_refund_'))))
        assert len(tasks) == 2 and all(t.status == 'done' for t in tasks)
        assert db.scalar(select(func.count()).select_from(CashEntry)) == 2


@pytest.mark.parametrize('approved_first', [False, True])
@pytest.mark.parametrize('action', ['refund_cancel', 'refund_reject'])
def test_group_refund_cancellation_or_rejection_releases_only_its_hold(client, approved_first, action):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    consumption = cmd(client, member, 'reserve', reserve_values(a, 1000))
    request = cmd(client, member, 'refund_request', refund_request_values(a, original, 4000))
    if approved_first:
        request = cmd(client, member, 'refund_approve', refund_review_values(a, request))
        assert request['member']['reserved_cents'] == 5000
    result = cmd(client, member, action, refund_review_values(a, request))
    assert result['member']['reserved_cents'] == 1000
    assert result['member']['balance_cents'] == 10000
    cmd(client, member, 'refund', refund_payment_values(a, result), 409)
    cmd(client, member, 'refund_approve', refund_review_values(a, result), 409)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CashEntry)) == 1
        assert db.scalar(select(func.count()).select_from(Task).where(Task.case_id == a['case_id'],
            Task.key.startswith('group_refund_'), Task.status == 'open')) == 0


def test_group_refund_rejects_self_approval_after_role_change(client):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    login(client, 'service')
    request = cmd(client, member, 'refund_request', refund_request_values(a, original))
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.username == 'service'))
        assignment = db.scalar(select(UserStore).where(UserStore.user_id == user_id, UserStore.store_id == 1))
        assignment.role = 'manager'
        db.commit()
    cmd(client, member, 'refund_approve', refund_review_values(a, request), 403)
    login(client, 'manager')
    approved = cmd(client, member, 'refund_approve', refund_review_values(a, request))
    assert approved['refund_request']['approved_by'] != approved['refund_request']['requested_by']


def test_group_refund_approval_cross_store_stale_and_source_cap(client):
    a, b = seed(), seed(2)
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    first = cmd(client, member, 'refund_request', refund_request_values(a, original, 7000))
    second = cmd(client, member, 'refund_request', refund_request_values(a, original, 7000))
    switch(client, 2)
    link(client, b, member['identity_id'])
    cmd(client, member, 'refund_approve', refund_review_values(a, first), 404)
    switch(client, 1)
    old = refund_review_values(a, first)
    approved = cmd(client, member, 'refund_approve', old)
    cmd(client, member, 'refund_cancel', old, 409)
    cmd(client, member, 'refund_approve', refund_review_values(a, second), 409)
    # A second recharge restores global availability but cannot enlarge the first source's refund cap.
    cmd(client, member, 'topup', topup_values(a, 10000))
    cmd(client, member, 'refund_approve', refund_review_values(a, second), 409)
    cmd(client, member, 'refund', refund_payment_values(a, approved) | {'account_id': b['account_id']}, 404)
    assert wallet(client, member)['reserved_cents'] == 7000


def test_group_refund_pending_task_survives_source_service_completion(client):
    a = seed(amount=0)
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    request = cmd(client, member, 'refund_request', refund_request_values(a, original, 5000))
    approved = cmd(client, member, 'refund_approve', refund_review_values(a, request))
    response = client.post(f"/api/flow/cases/{a['case_id']}/actions/release", json={
        'request_id': uuid.uuid4().hex, 'version': case_version(a['case_id']), 'values': {'evidence_id': a['evidence_id']}})
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'completed'
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.case_id == a['case_id'],
                         Task.key == 'group_refund_pay_'+str(approved['refund_request']['id'])))
        assert task.status == 'open'
    assert wallet(client, member)['reserved_cents'] == 5000
    paid = cmd(client, member, 'refund', refund_payment_values(a, approved))
    assert paid['member']['balance_cents'] == 5000 and paid['member']['reserved_cents'] == 0


def test_group_refund_competing_approvals_do_not_double_reserve(client):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    first = cmd(client, member, 'refund_request', refund_request_values(a, original, 7000))
    second = cmd(client, member, 'refund_request', refund_request_values(a, original, 7000))
    version = wallet(client, member)['version']
    first_values, second_values = refund_review_values(a, first), refund_review_values(a, second)
    with TestClient(app) as other:
        login(other)
        def run(args):
            c, values = args
            return c.post(f"/api/group/members/{member['id']}/actions/refund_approve", json={
                'request_id': uuid.uuid4().hex, 'version': version, 'values': values}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(run, [(client, first_values), (other, second_values)]))
    assert sorted(statuses) == [200, 409]
    assert wallet(client, member)['reserved_cents'] == 7000


def test_group_refund_request_facts_cannot_be_overwritten(client):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    request = cmd(client, member, 'refund_request', refund_request_values(a, original))
    with SessionLocal() as db:
        row = db.scalar(select(GroupRefundRequest).where(GroupRefundRequest.id == request['refund_request']['id']))
        row.amount_cents = 1
        with pytest.raises(HTTPException):
            db.flush()
        db.rollback()


def test_group_refund_request_and_approval_replay_do_not_duplicate_tasks_or_hold(client):
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    key, version = uuid.uuid4().hex, wallet(client, member)['version']
    values = refund_request_values(a, original)
    requested = cmd(client, member, 'refund_request', values, key=key, version=version)
    replay = cmd(client, member, 'refund_request', values, key=key, version=version)
    assert requested == replay
    key, version = uuid.uuid4().hex, wallet(client, member)['version']
    values = refund_review_values(a, requested)
    approved = cmd(client, member, 'refund_approve', values, key=key, version=version)
    replay = cmd(client, member, 'refund_approve', values, key=key, version=version)
    assert approved == replay
    assert wallet(client, member)['reserved_cents'] == 5000
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GroupRefundRequest)) == 1
        assert db.scalar(select(func.count()).select_from(Task).where(Task.key.startswith('group_refund_'))) == 2


def test_group_approved_refund_and_service_hold_backup_and_empty_transfer(client, tmp_path):
    from app.backup_integrity import validate_sqlite
    from scripts.migrate_database import transfer
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    cmd(client, member, 'reserve', reserve_values(a, 1000))
    request = cmd(client, member, 'refund_request', refund_request_values(a, original, 4000))
    approved = cmd(client, member, 'refund_approve', refund_review_values(a, request))
    assert approved['member']['reserved_cents'] == 5000
    backup_path, restored_path = tmp_path/'group-backup.sqlite', tmp_path/'group-restored.sqlite'
    with sqlite3.connect(TEST_DIR/'test.sqlite') as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
        assert validate_sqlite(backup)['verified_files'] == 1
    # Transfer from the offline synthetic backup, never from a company DB.
    counts = transfer('sqlite:///'+str(backup_path), 'sqlite:///'+str(restored_path))
    assert counts['group_refund_requests'] == counts['group_reservations'] == 1
    assert counts['group_entries'] == counts['cash_entries'] == 1
    assert counts['group_settlement_entries'] == 2
    with sqlite3.connect(restored_path) as restored:
        assert validate_sqlite(restored)['verified_files'] == 1
        assert restored.execute('SELECT balance_cents,reserved_cents FROM group_members').fetchone() == (10000, 5000)
        assert restored.execute('SELECT status FROM group_refund_requests').fetchone() == ('approved',)


def test_group_refund_request_preserves_source_case_and_financial_file_permissions(client):
    from tests.test_workflow import create, evidence
    a = seed()
    member = issue(client, a)
    original = cmd(client, member, 'topup', topup_values(a))
    with SessionLocal() as db:
        service_id = db.scalar(select(User.id).where(User.username == 'service'))
        assignment = db.scalar(select(UserStore).where(UserStore.user_id == service_id, UserStore.store_id == 1))
        assignment.role = 'customer_service'
        db.commit()
    login(client, 'service')
    cmd(client, member, 'refund_request', refund_request_values(a, original), 403)
    login(client, 'admin')
    lead = create(client, 'lead', {'customer_name': '集团测试客户', 'customer_phone': '13912345678', 'source': '展厅到店'})
    lead_setup = {'case_id': lead['id'], 'account_id': a['account_id'], 'evidence_id': evidence(client, lead, 'receipt')}
    topup = cmd(client, member, 'topup', topup_values(lead_setup, 1000))
    authorized_evidence = evidence(client, lead, 'evidence')
    login(client, 'service')
    cmd(client, member, 'refund_request', refund_request_values(lead_setup, topup, 500), 403)
    # The same employee can request against an authorized neutral evidence file.
    values = refund_request_values(lead_setup, topup, 500) | {'evidence_id': authorized_evidence}
    requested = cmd(client, member, 'refund_request', values)
    assert requested['refund_request']['status'] == 'requested'
