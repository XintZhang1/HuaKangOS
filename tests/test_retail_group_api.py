"""Registered HTTP acceptance of original retail, native issuance and refunds.

Fixtures use only synthetic master data. Monetary actions go through the actual
membership/retail/group/invoice routes, not a replacement handler or a manual
post-commit hook. Standalone arithmetic/domain tests remain separate.
"""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import csv
import io
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.db import SessionLocal, today
from app.main import app
from app.models import CashEntry, Store, User, UserStore
from app.flow_models import Case, FlowEvent, PaymentLink, StockMove, Task
from app.retail_group_models import RetailGroupPlan, RetailGroupCapture, RetailGroupWallet
from app.retail_group_api import SCHEMAS
from app.backup_integrity import validate_sqlite
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app import reconciliation_service as reconciliation
from tests.conftest import login, TEST_DIR
from tests import test_retail as retail, test_group_membership as group
from tests import test_group_benefits as benefit, test_membership_lifecycle as membership
from tests import test_invoices as invoices, test_reconciliation as monthly
technician = retail.technician


def read(c, row):
    r = c.get(f"/api/retail-group/orders/{row['id']}")
    assert r.status_code == 200, r.text
    return r.json()


def action(c, row, key, tender_id=None, unit_id=None, *, status=200,
           values=None, body=None, return_body=False):
    if body is None:
        current = read(c, row)
        tender = next((t for t in current['tenders'] if t['id'] == tender_id
            or any(u['id'] == unit_id for u in t['units_detail'])), None)
        v = {'plan_version': current['plan_version'], 'member_version': current['member_version'],
             'evidence_id': retail.evidence(c, row)}
        if tender_id is not None: v['tender_id'] = tender_id
        if unit_id is not None: v['unit_id'] = unit_id
        if tender and tender.get('wallet_version'): v['wallet_version'] = tender['wallet_version']
        if key == 'capture' and tender: v['reservation_version'] = tender['reservation_version']
        v.update(values or {})
        body = {'request_id': uuid.uuid4().hex, 'version': current['version'], 'values': v}
    r = c.post(f"/api/retail-group/orders/{row['id']}/actions/{key}", json=body)
    assert r.status_code == status, r.text
    return (r.json(), body) if return_body else r.json()


def rule_action(c, row, action_name, values, status=200):
    r = c.get('/api/retail-group/rules/' + str(row['case_id']))
    assert r.status_code == 200, r.text
    r = c.post(f"/api/retail-group/rules/{row['case_id']}/actions/{action_name}", json={
        'request_id': uuid.uuid4().hex, 'version': r.json()['version'], 'values': values})
    assert r.status_code == status, r.text
    return r.json()


def public_setup(c, kind='coupon', *, authorize=True, points=False, store=1):
    """Native original issuance, actual fulfillment, then customer authorization."""
    login(c)
    if store != 1:
        with SessionLocal() as db:
            db.add(Store(id=store, code='TEST-S2', name='独立合成第二店'))
            db.flush()
            for u in db.scalars(select(User)):
                db.add(UserStore(user_id=u.id, store_id=store))
            db.commit()
        issuer_customer = retail.master(c, 'customers', {'name': '精品合成客户',
            'phone': '13900000091', 'contact_allowed': True, 'note': ''})
        member = group.issue(c, {'customer_id': issuer_customer['id']})
        group.switch(c, store)
    items, customer, work, purchase = retail.setup(c, True)
    if store == 1:
        issuer_customer = customer
        member = group.issue(c, {'customer_id': customer['id']})
    else:
        group.link(c, {'customer_id': customer['id']}, member['identity_id'])
        group.switch(c, 1)
    issuer_account = retail.bank(c)
    topup = membership.create(c, issuer_customer, 'topup', {'amount_cents': 2000})
    login(c, 'finance')
    topup = membership.cmd(c, topup, 'execute', {'evidence_id': membership.proof(c, topup),
        'account_id': issuer_account, 'reference': uuid.uuid4().hex, 'reason': '仅合成原发行店实际到账'})
    login(c)
    wallet = rule = annex = None
    if kind:
        prices = dict(credit_cents_per_unit=400, sale_cents_per_unit=321, settlement_cents_per_unit=321)
        if kind == 'bonus': prices = dict(credit_cents_per_unit=1, sale_cents_per_unit=0, settlement_cents_per_unit=0)
        if kind == 'package': prices = dict(credit_cents_per_unit=100, sale_cents_per_unit=81,
            settlement_cents_per_unit=81, service_code=work['code'])
        rule = benefit.rule(c, kind, allowed_store_ids=sorted({1, store}), **prices)
        created = c.post('/api/retail-group/rules', json={'request_id': uuid.uuid4().hex, 'rule_id': rule['id']})
        assert created.status_code == 201, created.text
        annex = created.json()
        proof = retail.evidence(c, {'id': annex['case_id']}, 'authorization')
        scope = {'store_id': store, 'item_id': items[0]['id'],
            'component': 'installation' if kind == 'package' else 'goods',
            'work_item_id': work['id'] if kind == 'package' else None}
        values = {'evidence_id': proof, 'partial_return_mode': 'accumulate_original_unit',
            'expiry_mode': 'original_expiry', 'pending_claim_expiry': 'none', 'scopes': [scope]}
        annex = rule_action(c, annex, 'submit', values)
        rule_action(c, annex, 'approve', {'evidence_id': proof, 'reason': '不得由申请者批准自己'}, 403)
        login(c, 'manager')
        annex = rule_action(c, annex, 'approve', {'evidence_id': proof, 'reason': '独立复核明确商品与原退约定'})
        login(c)
        issuance = membership.create(c, issuer_customer, 'benefit_issue', {
            'rule_id': rule['id'], 'units': 300 if kind == 'bonus' else 3,
            'action': 'grant' if kind == 'bonus' else 'purchase'})
        login(c, 'manager' if kind == 'bonus' else 'finance')
        v = {'evidence_id': membership.proof(c, issuance), 'reason': '实际原批次发行，禁止重标旧批次'}
        if kind != 'bonus': v.update(account_id=issuer_account, reference=uuid.uuid4().hex)
        issued = membership.cmd(c, issuance, 'execute', v)
        wallet = benefit.info(c, {'customer_id': issuer_customer['id']})['wallets'][-1]
        with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
            # Independent read-only oracle: only the HTTP issuance wrote it.
            assert db.execute('SELECT id FROM retail_group_wallets WHERE wallet_id=?',
                (wallet['id'],)).fetchone() is not None
        login(c)
    if store != 1: group.switch(c, store)
    if points:
        point_rule = benefit.rule(c, 'points', allowed_store_ids=[store])
        level = membership.rule(c, allowed_store_ids=[store], points_enabled=True,
            points_numerator=1, points_denominator_fen=100, points_benefit_rule_id=point_rule['id'])
        membership.renew(c, customer, level)
        login(c)
    account = issuer_account if store == 1 else retail.bank(c)
    row = retail.create(c, items, customer, work)
    row = retail.authorize(c, retail.approve(c, row))
    login(c, 'inventory'); row = retail.dispatch(c, row)
    login(c, 'technician'); row = retail.cmd(c, row, 'install', {
        'evidence_id': retail.evidence(c, row), 'result': '技师本人实际完成并核对安装'})
    login(c); row = retail.cmd(c, row, 'accept', {'evidence_id': retail.evidence(c, row)})
    catalog = c.get(f"/api/retail-group/orders/{row['id']}/catalog")
    assert catalog.status_code == 200, catalog.text
    selections = [{'kind': 'principal', 'amount_cents': 300}]
    if kind:
        w = next(w for w in catalog.json()['wallets'] if w['id'] == wallet['id'])
        assert w['usable'] is True
        selections.insert(0, {'kind': kind, 'wallet_id': w['id'], 'wallet_version': w['version'],
            'units': 100 if kind == 'bonus' else 1})
    auth = {'request_id': uuid.uuid4().hex, 'version': catalog.json()['version'], 'values': {
        'member_id': member['id'], 'member_version': catalog.json()['member']['version'],
        'evidence_id': retail.evidence(c, row, 'authorization'), 'selections': selections}}
    if authorize:
        r = c.post(f"/api/retail-group/orders/{row['id']}/actions/authorize", json=auth)
        assert r.status_code == 200, r.text
    return row, member, wallet, account, auth


def capture_all(c, row):
    login(c, 'finance')
    for tender in read(c, row)['tenders']:
        if tender['kind'] == 'cash': continue
        action(c, row, 'reserve', tender['id'])
        action(c, row, 'capture', tender['id'])


def actual_return(c, row, quantity=500):
    login(c)
    current = retail.detail(c, row)
    current, ret = retail.request_return(c, current, current['dispatches'][0], quantity)
    login(c, 'manager'); current = retail.ret_cmd(c, current, ret, 'return_approve')
    login(c, 'inventory'); current = retail.ret_cmd(c, current, ret, 'return_receive')
    return current


def settle_original_refunds(c, row, account):
    login(c, 'finance')
    current = read(c, row)
    for original in current['original_cash_refundable']:
        retail.refund(c, row, {'id': original['payment_link_id']}, account, original['amount_cents'])
    for tender in read(c, row)['tenders']:
        for unit in tender['units_detail']:
            if unit['restorable']: action(c, row, 'restore', unit_id=unit['id'])
    return retail.detail(c, row)


def assert_reports(c, row):
    current = retail.detail(c, row)['totals']
    r = c.get('/api/flow/analytics'); assert r.status_code == 200, r.text
    report = r.json()
    assert report['metrics']['retail_revenue_cents'] == current['net_price_cents']
    assert report['metrics']['retail_goods_cost_cents'] == current['cost_cents']
    for key in ('retail_settlements', 'retail_group_pending', 'benefit_redemptions'):
        rows = report['tables'][key]
        r = c.get('/api/flow/analytics/export', params={'dataset': key})
        assert r.status_code == 200, r.text
        export = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
        assert export[0] == rows['headers']
        assert [[v.removeprefix("'") for v in line] for line in export[1:]] == [
            [str(v) for v in line['values']] for line in rows['rows']]
    chart = next(c for c in report['charts'] if c['id'] == 'retail_settlements')
    assert sum(chart['series'][0]['values']) == current['net_price_cents']
    return report


def assert_restore_integrity():
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        return validate_sqlite(db)


def test_native_original_routes_cash_return_invoice_points_and_monthly_once(client, monkeypatch):
    from dataclasses import replace
    from app import main as main_module, security
    native_settings = replace(main_module.settings, legacy_business_write=False)
    monkeypatch.setattr(main_module, 'settings', native_settings)
    monkeypatch.setattr(security, 'settings', native_settings)
    row, member, wallet, account, body = public_setup(client, points=True)
    capture_all(client, row)
    before = retail.detail(client, row)
    assert before['totals']['cash_collectable_cents'] == 500
    retail.cmd(client, row, 'receive', {'amount_cents': 501, 'account_id': account,
        'reference': uuid.uuid4().hex, 'evidence_id': retail.evidence(client, row, 'receipt')}, 409)
    retail.pay(client, row, 201, account); retail.pay(client, row, 299, account)
    assert retail.detail(client, row)['state'] == 'completed'
    original = retail.detail(client, row)['totals']
    assert original['net_price_cents'] == 1121
    invoices.create(client, row['id'], 1122, status=409)
    blue = invoices.actual(client, row['id'], 1121)
    assert_reports(client, row)
    current = actual_return(client, row)
    login(client, 'finance')
    snapshot_before_restore = retail.detail(client, row)['totals']
    report_before = assert_reports(client, row)
    invoice_state = invoices.read(client, blue['id'])
    assert invoice_state['balance']['correction_cents'] == 1121 - snapshot_before_restore['net_price_cents']
    plan = read(client, row)
    coupon = next(t for t in plan['tenders'] if t['kind'] == 'coupon')
    assert coupon['units_detail'][0]['pending_credit_cents'] > 0
    assert not coupon['units_detail'][0]['restorable']
    action(client, row, 'restore', unit_id=coupon['units_detail'][0]['id'], status=409)
    statement = monthly.batch(client)
    assert statement['definition_version'] == CURRENT_DEFINITION_VERSION
    assert statement['summary']['retail_group_pending_original_units']
    assert any(x['source'] == 'retail_group_cash_allocations' for x in statement['manifest'])
    assert_restore_integrity()
    after_partial = settle_original_refunds(client, row, account)
    assert after_partial['totals']['net_price_cents'] == snapshot_before_restore['net_price_cents']
    assert after_partial['state'] == 'settling'  # Original indivisible liability remains.
    assert not any(t['key'] == 'retail_group_restore' for t in read(client, row)['tasks'])
    actual_return(client, row, 1500)
    final = settle_original_refunds(client, row, account)
    assert sum(final['totals']['group_return_pending_cents'].values()) == 0
    assert_reports(client, row)
    # Later lawful restores do not rewrite the earlier frozen subset.
    assert monthly.get(client, statement)['digest'] == statement['digest']
    assert monthly.get(client, statement)['source_changed'] is True
    assert_restore_integrity()
    from app.membership_models import PointsChange
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FlowEvent).where(
            FlowEvent.case_id == row['id'], FlowEvent.action == 'retail_group_authorize')) == 1
        links = list(db.scalars(select(PaymentLink).where(PaymentLink.case_id == row['id'])))
        assert len({p.cash_id for p in links}) == len(links)
        actual_cash = sum(p.amount_cents * (1 if p.direction == 'in' else -1) for p in links)
        assert actual_cash == final['totals']['cash_paid_cents']
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as oracle:
        assert oracle.execute('SELECT SUM(units) FROM membership_points_changes WHERE case_id=?',
            (row['id'],)).fetchone()[0] == (
                min(final['totals']['net_price_cents'], actual_cash + final['totals']['group_recognized_cents']) // 100)


@pytest.mark.parametrize('kind', ['bonus', 'package', None])
def test_native_issuance_variants_and_original_scoped_prices(client, kind):
    row, member, wallet, account, _ = public_setup(client, kind)
    capture_all(client, row)
    amount = read(client, row)['totals']['cash_collectable_cents']
    retail.pay(client, row, amount, account)
    totals = retail.detail(client, row)['totals']
    expected = 1100 if kind == 'bonus' else 1181 if kind == 'package' else 1200
    assert totals['net_price_cents'] == expected
    assert totals['cash_paid_cents'] + totals['group_recognized_cents'] == expected
    assert_reports(client, row)
    assert_restore_integrity()


def test_public_authorization_retries_strict_values_stale_versions_and_legacy_bypass(client):
    row, member, wallet, account, body = public_setup(client, None, authorize=False)
    url = f"/api/retail-group/orders/{row['id']}/actions/authorize"
    one = client.post(url, json=body); assert one.status_code == 200, one.text
    again = client.post(url, json=body); assert again.json() == one.json()
    other = {**body, 'request_id': uuid.uuid4().hex}
    assert client.post(url, json=other).status_code == 409
    wrong = json.loads(json.dumps(body)); wrong['values']['selections'][0]['amount_cents'] = 301
    assert client.post(url, json=wrong).status_code == 409
    login(client, 'finance')
    tender = next(t for t in read(client, row)['tenders'] if t['kind'] == 'principal')
    current, reserve_body = action(client, row, 'reserve', tender['id'], return_body=True)
    assert action(client, row, 'reserve', body=reserve_body) == current
    changed = json.loads(json.dumps(reserve_body)); changed['values']['member_version'] += 1
    action(client, row, 'reserve', body=changed, status=409)
    legacy = {'request_id': uuid.uuid4().hex, 'version': current['member_version'], 'values': {
        'case_id': row['id'], 'case_version': current['version'], 'amount_cents': 1,
        'evidence_id': retail.evidence(client, row)}}
    bypass = client.post(f"/api/group/members/{member['id']}/actions/reserve", json=legacy)
    assert bypass.status_code == 409, bypass.text
    action(client, row, 'capture', tender['id'])
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RetailGroupPlan)) == 1
        assert db.scalar(select(func.count()).select_from(RetailGroupCapture)) == 1


def test_actual_return_wins_over_reserved_uncharged_tender_then_explicit_release(client):
    row, member, wallet, account, _ = public_setup(client, None)
    login(client, 'finance')
    principal = next(t for t in read(client, row)['tenders'] if t['kind'] == 'principal')
    action(client, row, 'reserve', principal['id'])
    actual_return(client, row)
    login(client, 'finance')
    action(client, row, 'capture', principal['id'], status=409)
    result = action(client, row, 'release', principal['id'], values={'reason': '实际退货后释放未核销原占额'})
    assert result['totals']['group_paid_cents'] == 0
    assert not any(result['totals']['group_return_pending_cents'].values())
    retail.pay(client, row, result['totals']['cash_collectable_cents'], account)
    assert_reports(client, row)
    assert_restore_integrity()


def test_public_cross_store_roles_original_issuer_files_and_aggregate_are_scoped(client):
    row, member, wallet, account, _ = public_setup(client, store=2)
    capture_all(client, row)
    current = read(client, row)
    coupon = next(t for t in current['tenders'] if t['kind'] == 'coupon')
    assert coupon['issuer_store_id'] == 1 and 'original_issuance_case_id' not in coupon
    retail.pay(client, row, current['totals']['cash_collectable_cents'], account)
    assert_reports(client, row)
    login(client, 'inventory')
    assert client.get(f"/api/retail-group/orders/{row['id']}").status_code == 403
    assert 'totals' not in retail.detail(client, row) or 'group_recognized_cents' not in retail.detail(client, row)['totals']
    login(client, 'sales')
    assert client.get(f"/api/retail-group/orders/{row['id']}").status_code == 404
    login(client, 'service')
    current = read(client, row)
    assert all('consideration_cents' not in t for t in current['tenders'])
    assert 'group_recognized_cents' not in current['totals']
    login(client, 'finance'); group.switch(client, 1)
    assert client.get(f"/api/retail-group/orders/{row['id']}").status_code == 404
    group.switch(client, 'all')
    assert client.get(f"/api/retail-group/orders/{row['id']}").status_code in {403, 409}
    assert client.get('/api/flow/analytics').status_code == 403
    login(client)  # Only explicitly authorized group-summary accounts can aggregate.
    report = client.get('/api/flow/analytics')
    assert report.status_code == 200, report.text
    assert report.json()['metrics']['retail_revenue_cents'] == 1121
    group.switch(client, 2)
    statement = monthly.batch(client)
    assert all(e['data'].get('store_id', 2) == 2 for e in statement['manifest'])
    assert_restore_integrity()


def test_rehashed_original_allocation_and_pending_summary_mutations_are_rejected(client):
    row, member, wallet, account, _ = public_setup(client)
    capture_all(client, row)
    retail.pay(client, row, 500, account)
    actual_return(client, row)
    login(client, 'finance'); batch = monthly.batch(client)
    for mutation in ('amount', 'unit', 'summary', 'legacy'):
        with sqlite3.connect(TEST_DIR / 'test.sqlite') as source, sqlite3.connect(':memory:') as copy:
            source.backup(copy); validate_reconciliation_sqlite(copy)
            manifest, summary = map(json.loads, copy.execute(
                'SELECT manifest,summary FROM reconciliation_batches WHERE id=?', (batch['id'],)).fetchone())
            if mutation in {'amount', 'unit'}:
                data = next(e['data'] for e in manifest if e['source'] == 'retail_group_allocations')
                data['consideration_cents' if mutation == 'amount' else 'unit_id'] += 1
            elif mutation == 'summary':
                summary['retail_group_pending_original_units'][0]['spendable_cents'] = 1
            else: summary['definition_version'] = 9
            hashed = reconciliation.digest({'manifest': manifest, 'summary': summary})
            copy.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                (json.dumps(manifest), json.dumps(summary), hashed, batch['id']))
            with pytest.raises(ValueError): validate_reconciliation_sqlite(copy)


def test_preserved_explicit_legacy_source_definitions_do_not_gain_v10_links(client):
    row, member, wallet, account, _ = public_setup(client, None)
    login(client, 'finance')
    from tests.test_retail_group_service import actor
    with SessionLocal() as db:
        user = actor(db, 'finance')
        for version in range(1, 10):
            manifest, summary, digest = reconciliation.snapshot(db, user, today(), today(), version)
            assert not any(e['source'].startswith('retail_group_') for e in manifest)
            assert 'retail_group_pending_original_units' not in summary
        manifest, summary, _ = reconciliation.snapshot(db, user, today(), today(), 10)
        assert any(e['source'] == 'retail_group_plans' for e in manifest)


def test_rule_request_does_not_default_company_policy_or_accept_fractional_units():
    from app.retail_group_api import Submit, Selection
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Submit.model_validate({'evidence_id': 1, 'scopes': [{'store_id': 1, 'item_id': 1, 'component': 'goods'}]})
    for value in (True, 1.01, '100'):
        with pytest.raises(ValidationError): Selection.model_validate({'kind': 'principal', 'amount_cents': value})
    for value in (True, 1.01, '1'):
        with pytest.raises(ValidationError): Selection.model_validate({
            'kind': 'coupon', 'wallet_id': 1, 'wallet_version': 1, 'units': value})


@pytest.mark.parametrize('operation', ['authorize', 'capture', 'cash_receive'])
def test_two_real_http_callers_cannot_duplicate_original_plan_capture_or_cash(client, operation):
    row, member, wallet, account, authorization = public_setup(client, None,
        authorize=operation != 'authorize')
    if operation == 'authorize':
        user = 'admin'
        endpoint = f"/api/retail-group/orders/{row['id']}/actions/authorize"
        original = authorization
    elif operation == 'capture':
        user = 'finance'; login(client, user)
        tender = next(t for t in read(client, row)['tenders'] if t['kind'] == 'principal')
        action(client, row, 'reserve', tender['id'])
        current = read(client, row)
        t = next(t for t in current['tenders'] if t['kind'] == 'principal')
        endpoint = f"/api/retail-group/orders/{row['id']}/actions/capture"
        original = {'version': current['version'], 'values': {
            'plan_version': current['plan_version'], 'member_version': current['member_version'],
            'tender_id': t['id'], 'reservation_version': t['reservation_version'],
            'evidence_id': retail.evidence(client, row)}}
    else:
        user = 'finance'; capture_all(client, row)
        current = retail.detail(client, row)
        endpoint = f"/api/retail/orders/{row['id']}/actions/receive"
        original = {'version': current['version'], 'values': {
            'amount_cents': current['totals']['cash_collectable_cents'],
            'account_id': account, 'reference': uuid.uuid4().hex,
            'evidence_id': retail.evidence(client, row, 'receipt')}}
    callers = [TestClient(app), TestClient(app)]
    bodies = [dict(original, request_id=uuid.uuid4().hex) for _ in callers]
    try:
        for caller in callers: login(caller, user)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda i: callers[i].post(endpoint, json=bodies[i]), range(2)))
        assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
        winner = next(i for i, r in enumerate(responses) if r.status_code == 200)
        replay = callers[winner].post(endpoint, json=bodies[winner])
        assert replay.status_code == 200 and replay.json() == responses[winner].json()
        with sqlite3.connect(TEST_DIR / 'test.sqlite') as oracle:
            if operation == 'authorize':
                assert oracle.execute('SELECT COUNT(*) FROM retail_group_plans WHERE case_id=?',
                    (row['id'],)).fetchone()[0] == 1
            elif operation == 'capture':
                assert oracle.execute('SELECT COUNT(*) FROM retail_group_captures c JOIN retail_group_tenders t ON t.id=c.tender_id JOIN retail_group_plans p ON p.id=t.plan_id WHERE p.case_id=?',
                    (row['id'],)).fetchone()[0] == 1
            else:
                assert oracle.execute("SELECT COUNT(*) FROM flow_payment_links WHERE case_id=? AND direction='in'",
                    (row['id'],)).fetchone()[0] == 1
        assert_restore_integrity()
    finally:
        for caller in callers: caller.close()
