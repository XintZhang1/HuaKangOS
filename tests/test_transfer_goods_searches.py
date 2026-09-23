"""Original public routes for a return shipment which cannot currently be found.

Synthetic facts only. Search, loss recognition, physical finding, stock receipt
and actual money are different records; checks never infer one from another.
"""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.backup_integrity import validate_sqlite
from app.db import SessionLocal, today
from app.main import app
from app.models import User
from app.tenancy import set_scope
from app.transfer_goods_search_integrity import validate_transfer_goods_searches
from app.transfer_goods_search_models import GoodsSearch, GoodsSearchReview
from app.transfer_goods_recovery_service import authority
from tests.conftest import TEST_DIR, login
from tests import test_transfer_goods_recovery as goods
from tests.test_transfer_goods_recovery import old


def transit(c, data=None, row=None):
    data = data or goods.original(c)
    row = row or goods.found(c, data, store=2)
    goods.match(c, data, row)
    old.switch(c, 2); login(c, 'inventory2')
    goods.physical(c, row, 'inspect', True)
    return data, goods.physical(c, row, 'ship')


def trace(c, row, action='trace_open', status=200, **kw):
    current = goods.current(c, row)
    values = dict(evidence_id=old.proof(c, current['case_id']),
        reason='本人核对原退运、实际查找记录；没有实际到货，不再重复确认损失', confirmed=True)
    if action != 'trace_open':
        values['search_id'] = current['searches'][-1]['id']
    return goods.command(c, row, action, values, status, **kw)


def end_search(c, data, row):
    old.switch(c, 2); login(c, 'inventory2'); trace(c, row)
    for sid, who in ((1, 'manager'), (2, 'manager2')):
        old.switch(c, sid); login(c, who); row = trace(c, row, 'trace_approve')
    assert row['status'] == 'unlocated'
    return row


def reappear(c, data, parent, quantity, store=1, status=201):
    old.switch(c, store); login(c, 'inventory' if store == 1 else 'inventory2')
    before = old.get(c, {'id': data['transfer_id']})
    body = dict(request_id=uuid.uuid4().hex, transfer_id=before['id'], loss_id=data['loss_id'],
        version=before['version'], case_version=before['case_version'], previous_recovery_id=parent['id'],
        quantity_milli=quantity, result='本人实际再次找到原结束查找物资，按原查找关联，不覆盖原退运记录',
        evidence_id=data['outproof'] if store == 1 else data['inproof'], due_date=today().isoformat(), confirmed=True)
    response = c.post('/api/transfer-goods-recoveries', json=body)
    assert response.status_code == status, response.text
    return response.json()


def monetary_sources():
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        return {name: db.execute('SELECT * FROM "' + name + '" ORDER BY id').fetchall()
            for name in ('cash_entries', 'flow_stock_moves', 'transfer_loss_postings',
                'transfer_goods_postings', 'transfer_goods_settlements')}


def verify(searches, reappearances=0):
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        assert validate_transfer_goods_searches(db) == {
            'found_searches': searches, 'found_reappearances': reappearances}
        assert validate_sqlite(db)['integrity'] == 'ok'


def test_independent_search_ends_without_second_loss_stock_or_cash(client):
    data, row = transit(client)
    original = monetary_sources()
    row = end_search(client, data, row)
    assert monetary_sources() == original
    assert row['custody_store_name'] is None
    assert row['searches'][-1]['status'] == 'unlocated'
    assert len(row['searches'][-1]['reviews']) == 2
    assert row['reappearance_remaining_milli'] == 1000
    assert row['actions'] == []  # A manager does not manufacture an actual finding.
    old.switch(client, 1); login(client, 'inventory')
    assert 'refind' in goods.current(client, row)['actions']
    goods.physical(client, row, 'receive', True, status=409)
    verify(1)


def test_partial_original_reappearance_restores_original_tail_only(client):
    data, row = transit(client); parent = end_search(client, data, row)
    for qty in (333, 667):
        child = reappear(client, data, parent, qty)
        assert child['previous_recovery_id'] == parent['id']
        goods.ready(client, data, child); goods.restore(client, data, child)
    reappear(client, data, parent, 1, status=409)
    previous = goods.current(client, parent)
    assert previous['status'] == 'unlocated' and previous['reappearance_remaining_milli'] == 0
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        assert db.execute('SELECT value_cents FROM transfer_goods_postings ORDER BY id').fetchall() == [(11,), (22,)]
        assert db.execute('SELECT value_cents FROM transfer_loss_postings').fetchall() == [(100,)]
        assert db.execute('SELECT COUNT(*) FROM cash_entries').fetchone()[0] == 0
    verify(1, 2)


def test_actual_arrival_closes_pending_search_but_does_not_receive_stock(client):
    data, row = transit(client); trace(client, row)
    old.switch(client, 2); login(client, 'manager2'); trace(client, row, 'trace_approve')
    original = monetary_sources()
    old.switch(client, 1); login(client, 'inventory')
    row = goods.physical(client, row, 'receive', True)
    assert row['status'] == 'preparing' and row['searches'][-1]['status'] == 'arrived'
    assert monetary_sources() == original
    goods.plan(client, data, row); goods.approve(client, data, row); goods.restore(client, data, row)
    verify(1)


def test_rejection_keeps_original_transit_and_new_review_is_append_only(client):
    data, row = transit(client); trace(client, row)
    old.switch(client, 1); login(client, 'manager')
    row = trace(client, row, 'trace_reject')
    assert row['status'] == 'transit' and row['searches'][-1]['status'] == 'rejected'
    old.switch(client, 2); login(client, 'inventory2'); trace(client, row)
    old.switch(client, 1); login(client, 'manager'); trace(client, row, 'trace_approve')
    old.switch(client, 2); login(client, 'manager2'); row = trace(client, row, 'trace_approve')
    assert [s['revision'] for s in row['searches']] == [1, 2]
    assert [s['status'] for s in row['searches']] == ['rejected', 'unlocated']
    verify(2)


def test_involved_manager_cannot_approve_own_search_or_other_store_files(client):
    data, row = transit(client)
    old.switch(client, 1); login(client, 'manager')
    before = goods.current(client, row)
    trace(client, row, status=409)  # No other local manager exists in this fixture.
    assert goods.current(client, row)['version'] == before['version']
    old.switch(client, 2); login(client, 'inventory2'); trace(client, row)
    latest = goods.current(client, row)
    trace(client, row, 'trace_approve', status=403)
    assert all(r['evidence_id'] is None for r in latest['searches'] if r['store_id'] == 1)
    old.switch(client, 1); login(client, 'manager')
    current = goods.current(client, row)
    goods.command(client, row, 'trace_approve', dict(search_id=current['searches'][-1]['id'],
        evidence_id=data['inproof'], reason='不能拿另一店的物理原件代本店复核', confirmed=True), status=422)
    old.switch(client, 3); login(client, 'admin')
    assert client.get(f"/api/transfer-goods-recoveries/{row['id']}").status_code == 404
    verify(1)


def test_nested_reappearance_keeps_each_original_branch_capacity(client):
    data, first = transit(client); first = end_search(client, data, first)
    child = reappear(client, data, first, 1000, store=2)
    data, child = transit(client, data, child); child = end_search(client, data, child)
    reappear(client, data, first, 1, status=409)
    final = reappear(client, data, child, 1000)
    goods.ready(client, data, final); goods.restore(client, data, final)
    assert goods.current(client, first)['reappearance_remaining_milli'] == 0
    assert goods.current(client, child)['reappearance_remaining_milli'] == 0
    verify(2, 2)


def test_cancelled_wrong_reappearance_releases_its_original_branch_only(client):
    data, row = transit(client); parent = end_search(client, data, row)
    child = reappear(client, data, parent, 1000)
    goods.physical(client, child, 'cancel')
    child = reappear(client, data, parent, 1000)
    goods.ready(client, data, child); goods.restore(client, data, child)
    verify(1, 2)


def test_cas_idempotency_strict_actuals_and_unrelated_original_refusal(client):
    data, row = transit(client)
    before = goods.current(client, row); request = uuid.uuid4().hex
    values = dict(evidence_id=data['inproof'], reason='本次实际退运查找原记录，重复提交只记一次', confirmed=True)
    result = goods.command(client, row, 'trace_open', values, before=before, request=request)
    assert goods.command(client, row, 'trace_open', values, before=before, request=request) == result
    goods.command(client, row, 'trace_open', values, before=before, status=409)
    goods.command(client, row, 'trace_open', dict(values, confirmed='true'), status=422)
    old.switch(client, 1); login(client, 'manager'); trace(client, row, 'trace_approve')
    old.switch(client, 2); login(client, 'manager2'); trace(client, row, 'trace_approve')
    reappear(client, data, {'id': row['id'] + 999}, 100, status=409)
    reappear(client, data, row, 1001, status=409)
    verify(1)


@pytest.mark.parametrize('sql', [
    'UPDATE transfer_goods_search_reviews SET actor_id=(SELECT requested_by FROM transfer_goods_searches LIMIT 1) WHERE store_id=1',
    'UPDATE transfer_goods_search_outcomes SET actor_id=actor_id+999',
    'UPDATE transfer_goods_reappearances SET quantity_milli=quantity_milli+1',
    'UPDATE transfer_goods_reappearances SET previous_recovery_id=recovery_id+1',
    'UPDATE transfer_goods_searches SET revision=revision+1',
])
def test_restore_rejects_relabelled_original_search_sources(client, sql):
    data, row = transit(client); parent = end_search(client, data, row)
    reappear(client, data, parent, 333)
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as source, sqlite3.connect(':memory:') as db:
        source.backup(db); validate_transfer_goods_searches(db)
        db.execute(sql)
        with pytest.raises(ValueError, match='原物资查找'):
            validate_transfer_goods_searches(db)


def test_models_require_original_authority_and_never_update_review(client):
    data, row = transit(client); end_search(client, data, row)
    with SessionLocal() as db:
        set_scope(db, [1], 1)
        user = db.scalar(select(User).where(User.username == 'manager'))
        with pytest.raises(HTTPException):
            db.scalar(select(GoodsSearch))
        with authority(db, user):
            with pytest.raises(HTTPException):
                db.execute(update(GoodsSearchReview).values(reason='尝试覆盖原复核'))
            review = db.scalar(select(GoodsSearchReview))
            review.reason = '尝试修改原审核事实'
            with pytest.raises(HTTPException):
                db.flush()
        db.rollback()


def test_actual_receipt_and_final_search_approval_serialize_original_parent(client):
    data, row = transit(client); trace(client, row)
    old.switch(client, 2); login(client, 'manager2'); trace(client, row, 'trace_approve')
    old.switch(client, 1)
    callers = [TestClient(app), TestClient(app)]
    try:
        login(callers[0], 'inventory'); login(callers[1], 'manager')
        bodies = []
        for i, c in enumerate(callers):
            latest = goods.current(c, row)
            common = dict(evidence_id=old.proof(c, latest['case_id']), confirmed=True)
            values = dict(common, passed=True, result='本人确认实际到货并复验通过') if i == 0 else dict(
                common, search_id=latest['searches'][-1]['id'], reason='本人复核仍未找到的原查找结果')
            bodies.append(dict(request_id=uuid.uuid4().hex, version=latest['version'],
                transfer_version=latest['transfer_version'], case_version=latest['case_version'], values=values))
        def perform(i):
            action = 'receive' if i == 0 else 'trace_approve'
            return callers[i].post(f"/api/transfer-goods-recoveries/{row['id']}/actions/{action}", json=bodies[i])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(perform, range(2)))
        assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
        winner = next(i for i, r in enumerate(responses) if r.status_code == 200)
        assert perform(winner).status_code == 200
        with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
            assert db.execute('SELECT COUNT(*) FROM transfer_goods_search_outcomes').fetchone()[0] == 1
            assert db.execute('SELECT COUNT(*) FROM transfer_goods_postings').fetchone()[0] == 0
        verify(1)
    finally:
        for c in callers: c.close()


def test_report_chart_table_csv_share_current_original_search_not_a_second_expense(client):
    import csv
    import io
    from tests.test_service_analytics import report
    data, row = transit(client); end_search(client, data, row)
    login(client, 'finance')  # Actual shipping store 2 owns the one physical trace.
    result = report(client); table = result['tables']['transport_found_searches']
    assert len(table['rows']) == 1 and table['rows'][0]['unlocated_remaining_milli'] == 1000
    assert result['metrics']['transport_found_unlocated_count'] == 1
    assert result['metrics']['transport_found_pending_count'] == 0
    assert result['metrics']['cash_in_cents'] == result['metrics']['cash_out_cents'] == 0
    chart = next(c for c in result['charts'] if c['id'] == table['id'])
    assert sum(chart['series'][1]['values']) == 1
    exported = client.get('/api/flow/analytics/export', params={'dataset': table['id']})
    assert exported.status_code == 200, exported.text
    rows = list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert rows[0] == table['headers']
    assert rows[1:] == [[str(v) for v in r['values']] for r in table['rows']]
    old.switch(client, 1); login(client, 'finance')
    source = report(client)
    assert source['metrics']['transport_loss_cost_cents'] == 100
    assert source['metrics']['transport_found_cost_cents'] == 0
    old.switch(client, 'all'); login(client, 'admin')
    group = report(client)
    assert group['metrics']['transport_found_unlocated_count'] == 1
    assert group['metrics']['transport_loss_cost_cents'] == 100
    assert all(r['route'] is None for r in group['tables']['transport_found_searches']['rows'])
    assert 'evidence_id' not in str(group['tables']['transport_found_searches'])
    old.switch(client, 3)
    assert not report(client)['tables']['transport_found_searches']['rows']


def test_v11_local_frozen_searches_preserve_v1_to_v10_source_sets(client, monkeypatch):
    from datetime import timedelta
    from app import reconciliation_service as service
    from app.reconciliation_v11 import CURRENT_NAMES
    from tests import test_reconciliation as monthly
    data, row = transit(client); end_search(client, data, row)
    child = reappear(client, data, row, 333)
    login(client, 'finance')
    snapshot = service.snapshot
    with SessionLocal() as db:
        set_scope(db, [1], 1)
        user = db.scalar(select(User).where(User.username == 'finance'))
        for version in range(1, 11):
            manifest, summary, _ = snapshot(db, user, today(), today(), version)
            assert not any(e['source'] in CURRENT_NAMES for e in manifest)
            assert not CURRENT_NAMES & summary.keys()
        past, summary, _ = snapshot(db, user, today()-timedelta(days=1), today()-timedelta(days=1))
        assert summary['definition_version'] == CURRENT_DEFINITION_VERSION
        assert summary['transfer_goods_reappearances']['count'] == 1  # Explicit current-source basis.
        assert all(e['basis'] == 'current' for e in past if e['source'] in CURRENT_NAMES)
        assert '_transfer_goods_authority' not in db.info
    with monkeypatch.context() as patch:
        patch.setattr(service, 'snapshot', lambda db, user, start, end, definition_version=10:
            snapshot(db, user, start, end, 10))
        original = monthly.batch(client)
    assert original['definition_version'] == 10
    assert not monthly.get(client, original)['source_changed']
    successor = monthly.cmd(client, original, 'recalculate', {'reason': '保留原10版，明确纳入本店原退运查找和再次找到来源'})
    assert successor['definition_version'] == CURRENT_DEFINITION_VERSION
    assert successor['previous_id'] == original['id']
    assert all(e['data']['store_id'] == 1 for e in successor['manifest'] if e['source'] in CURRENT_NAMES)
    assert successor['summary']['transfer_goods_reappearances']['amount_cents'] == 0
    digest = successor['digest']
    goods.ready(client, data, child); goods.restore(client, data, child)
    login(client, 'finance')
    assert monthly.get(client, successor)['digest'] == digest
    assert monthly.get(client, successor)['source_changed']
    verify(1, 1)  # Later legitimate actual stock facts do not invalidate old snapshots.


@pytest.mark.parametrize('mutation', ['actor', 'parent', 'amount', 'basis', 'summary', 'legacy'])
def test_v11_rehash_does_not_legitimize_changed_original_source(client, mutation):
    import copy
    import json
    from app import reconciliation_service as service
    from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
    from tests import test_reconciliation as monthly
    data, row = transit(client); end_search(client, data, row)
    reappear(client, data, row, 333); login(client, 'finance')
    batch = monthly.batch(client)
    manifest, summary = copy.deepcopy(batch['manifest']), copy.deepcopy(batch['summary'])
    entry = next(e for e in manifest if e['source'] == 'transfer_goods_reappearances')
    if mutation == 'actor': entry['data']['actor_id'] += 999
    elif mutation == 'parent': entry['data']['previous_recovery_id'] += 999
    elif mutation == 'amount': entry['data']['amount_cents'] = 33
    elif mutation == 'basis': entry['basis'] = 'period'
    elif mutation == 'summary': summary['transfer_goods_reappearances']['amount_cents'] = 33
    elif mutation == 'legacy': summary['definition_version'] = 10
    digest = service.digest({'manifest': manifest, 'summary': summary})
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as source, sqlite3.connect(':memory:') as db:
        source.backup(db)
        db.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
            (json.dumps(manifest), json.dumps(summary), digest, batch['id']))
        with pytest.raises(ValueError): validate_reconciliation_sqlite(db)


def test_nonempty_n46a_o57b_upgrade_preserves_originals_then_runs_real_search_commands(client, tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from app.db import Base, engine, make_engine
    from app import reconciliation_service as service
    from scripts.migrate_database import table_fingerprint
    from tests import test_reconciliation as monthly
    data, row = transit(client)
    old.switch(client, 1); login(client, 'finance')
    snapshot = service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service, 'snapshot', lambda db, user, start, end, definition_version=10:
            snapshot(db, user, start, end, 10))
        batch = monthly.batch(client)
    path = tmp_path / 'actual-n46a-original-return.sqlite'
    url = 'sqlite:///' + path.as_posix()
    config = Config('alembic.ini'); config.attributes['url_override'] = url
    command.upgrade(config, 'n46a_operations_extensions')
    migrated = make_engine(url)
    try:
        names = set(inspect(migrated).get_table_names())
        # The historical n46a schema, not today's ORM, defines what existed.
        # New nullable columns (e.g. brand_id) must not be copied into old tables.
        from sqlalchemy import MetaData, Table
        historical = MetaData()
        copied = [Table(table.name, historical, autoload_with=migrated)
                  for table in Base.metadata.sorted_tables if table.name in names]
        assert 'master_material_brands' not in names
        assert 'brand_id' not in next(t for t in copied if t.name == 'master_item_profiles').c
        with engine.connect() as source, migrated.begin() as dest:
            for table in copied:
                current = Base.metadata.tables[table.name]
                records = list(source.execute(select(*(current.c[c.name] for c in table.columns))).mappings())
                if records: dest.execute(table.insert(), [dict(r) for r in records])
        with migrated.connect() as db:
            before = {table.name: table_fingerprint(db, table) for table in copied}
        with sqlite3.connect(path) as db:
            assert validate_sqlite(db)['found_searches'] == 0
            assert validate_sqlite(db)['verified_reconciliation_batches'] == 1
        command.upgrade(config, 'head')
        with migrated.connect() as db:
            assert before == {table.name: table_fingerprint(db, table) for table in copied}
        with sqlite3.connect(path) as db:
            assert not db.execute('PRAGMA foreign_key_check').fetchone()
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == __import__('alembic.script', fromlist=['ScriptDirectory']).ScriptDirectory.from_config(config).get_current_head()
        # Run the registered HTTP routes on the genuinely migrated copy, not a
        # separate metadata-created database; every session uses this factory.
        SessionLocal.configure(bind=migrated)
        row = end_search(client, data, row)
        child = reappear(client, data, row, 333)
        goods.ready(client, data, child); goods.restore(client, data, child)
        login(client, 'finance')
        fresh = monthly.cmd(client, batch, 'recalculate', {'reason': '实际迁移库按原退运查找及原成本恢复重新核对'})
        assert fresh['definition_version'] == CURRENT_DEFINITION_VERSION
        with sqlite3.connect(path) as db:
            result = validate_sqlite(db)
            assert result['found_searches'] == 1 and result['found_reappearances'] == 1
            assert result['found_goods_postings'] == 1 and result['verified_reconciliation_batches'] == 2
            assert db.execute('SELECT value_cents FROM transfer_loss_postings').fetchall() == [(100,)]
    finally:
        SessionLocal.configure(bind=engine)
        migrated.dispose()
