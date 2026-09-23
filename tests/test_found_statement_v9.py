"""Registered routes: local found-goods frozen sources, original cash, old versions."""
from app.reconciliation_service import CURRENT_DEFINITION_VERSION
import copy
from datetime import timedelta
import json
import sqlite3
import uuid

import pytest
from sqlalchemy import select
from app.db import SessionLocal, today
from app.models import User
from app.tenancy import set_scope, project_user
from app import reconciliation_service as service
from app.reconciliation_backup_integrity import validate_reconciliation_sqlite
from app.backup_integrity import validate_sqlite
from app.reconciliation_v9 import PERIOD_NAMES, CURRENT_NAMES
from tests.conftest import login, TEST_DIR
from tests import test_transfer_goods_recovery as goods, test_reconciliation as rec

NAMES = PERIOD_NAMES | CURRENT_NAMES


def restored(client, quantity=1000):
    data = goods.original(client)
    row = goods.found(client, data, quantity)
    goods.ready(client, data, row)
    goods.restore(client, data, row)
    login(client, 'finance')
    return data, row


def test_frozen_local_sources_scope_period_and_later_facts(client):
    data, row = restored(client)
    batch = rec.batch(client)
    assert batch['definition_version'] == CURRENT_DEFINITION_VERSION
    selected = [r for r in batch['manifest'] if r['source'] in NAMES]
    assert selected and all(r['data']['store_id'] == 1 for r in selected)
    assert {r['data']['kind'] for r in selected if r['source'] == 'transfer_goods_facts'} == {'found', 'inspect'}
    assert batch['summary']['transfer_goods_postings']['value_cents'] == 33
    assert batch['summary']['transfer_goods_settlements']['amount_cents'] == -16
    assert batch['summary']['transfer_goods_reviews']['count'] == 1
    assert batch['summary']['period_cash_in_cents'] == batch['summary']['period_cash_out_cents'] == 0
    assert not rec.get(client, batch)['source_changed']
    # Period movements exclude today's findings; current positions do not.
    with SessionLocal() as db:
        set_scope(db, [1], 1)
        user = project_user(db.scalar(select(User).where(User.username == 'finance')), 'finance')
        _, summary, _ = service.snapshot(db, user, today() - timedelta(days=1), today() - timedelta(days=1))
        assert summary['transfer_goods_postings']['count'] == summary['transfer_goods_facts']['count'] == 0
        assert summary['transfer_goods_settlements']['amount_cents'] == -16
        assert '_transfer_goods_authority' not in db.info
    goods.old.switch(client, 2)
    login(client, 'finance')
    other = rec.batch(client)
    assert other['summary']['transfer_goods_postings']['count'] == 0
    assert other['summary']['transfer_goods_settlements']['amount_cents'] == 16
    assert {r['data']['kind'] for r in other['manifest'] if r['source'] == 'transfer_goods_facts'} == {'match'}
    assert all(r['data']['store_id'] == 2 for r in other['manifest'] if r['source'] in NAMES)
    assert client.get('/api/reconciliation/batches/' + str(batch['id'])).status_code == 404
    goods.old.switch(client, 3)
    login(client, 'admin')
    empty = rec.batch(client)
    assert all(empty['summary'][name]['count'] == 0 for name in NAMES)
    goods.old.switch(client, 1)
    login(client, 'inventory')
    assert client.get('/api/reconciliation/batches/' + str(batch['id'])).status_code == 403
    later = goods.found(client, data, 1000)
    goods.ready(client, data, later)
    goods.restore(client, data, later)
    login(client, 'finance')
    assert rec.get(client, batch)['source_changed']
    assert rec.get(client, batch)['digest'] == batch['digest']
    # New legitimate originals never retroactively expand a frozen batch.
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        assert validate_sqlite(db)['verified_reconciliation_batches'] == 3
    client.headers['X-Store-ID'] = 'all'
    assert client.post('/api/reconciliation/batches', json={
        'request_id': uuid.uuid4().hex, 'start': today().isoformat(),
        'end': today().isoformat(), 'reason': '集团汇总不能生成跨店可写月结'}).status_code in {403, 409}


def test_version_eight_is_preserved_and_explicit_successor_adopts_nine(client, monkeypatch):
    restored(client)
    original = service.snapshot
    with monkeypatch.context() as patch:
        patch.setattr(service, 'snapshot', lambda db, user, start, end, definition_version=8:
                      original(db, user, start, end, 8))
        old = rec.batch(client)
    assert old['definition_version'] == 8
    assert not any(r['source'] in NAMES for r in old['manifest'])
    assert not rec.get(client, old)['source_changed']
    successor = rec.cmd(client, old, 'recalculate', {'reason': '明确保留旧版并补核对原物资找回来源'})
    assert successor['definition_version'] == CURRENT_DEFINITION_VERSION and successor['previous_id'] == old['id']
    assert successor['summary']['transfer_goods_postings']['value_cents'] == 33
    assert rec.get(client, old)['digest'] == old['digest']
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        assert validate_sqlite(db)['verified_reconciliation_batches'] == 2


def test_rehashed_tampering_rejects_originals_basis_scope_and_summary(client):
    restored(client)
    batch = rec.batch(client)
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as original, sqlite3.connect(':memory:') as db:
        original.backup(db)
        assert validate_sqlite(db)['verified_reconciliation_batches'] == 1
        for mutation in ('origin', 'reviewer', 'amount', 'basis', 'date', 'scope', 'omit', 'unknown', 'legacy'):
            manifest, summary = copy.deepcopy(batch['manifest']), copy.deepcopy(batch['summary'])
            post = next(r for r in manifest if r['source'] == 'transfer_goods_postings')
            if mutation == 'origin': post['data']['loss_id'] += 999
            elif mutation == 'reviewer':
                next(r for r in manifest if r['source'] == 'transfer_goods_reviews')['data']['actor_id'] += 999
            elif mutation == 'amount': summary['transfer_goods_postings']['value_cents'] += 1
            elif mutation == 'basis': post['basis'] = 'current'
            elif mutation == 'date': post['data']['business_date'] = '2000-01-01'
            elif mutation == 'scope': post['data']['store_id'] = 2
            elif mutation == 'omit': manifest.remove(post)
            elif mutation == 'unknown':
                post['source'] = 'transfer_goods_unregistered'
                post['key'] = post['source'] + ':' + str(post['source_id'])
            elif mutation == 'legacy': summary['definition_version'] = 8
            digest = service.digest({'manifest': manifest, 'summary': summary})
            db.execute('UPDATE reconciliation_batches SET manifest=?,summary=?,digest=? WHERE id=?',
                       (json.dumps(manifest), json.dumps(summary), digest, batch['id']))
            with pytest.raises(ValueError): validate_reconciliation_sqlite(db)
            db.rollback()
            assert validate_reconciliation_sqlite(db)['verified_reconciliation_batches'] == 1


def test_original_compensation_refund_is_link_only_not_duplicate_cash(client):
    from app.transfer_exception_models import TransferLossPosting
    old = goods.old
    data, ex, carrier, account, proof = old.recoverable(client)
    claim = old.approve_claim(client, ex, old.create_claim(client, ex, carrier, proof), proof)
    old.recovery(client, ex, 'recovery_receive', claim, amount_cents=40, account_id=account,
                 reference=uuid.uuid4().hex, business_date=today().isoformat(), confirmed=True, evidence_id=proof)
    with SessionLocal() as db: data['loss_id'] = db.scalar(select(TransferLossPosting.id))
    row = goods.found(client, data)
    goods.ready(client, data, row)
    goods.restore(client, data, row)
    login(client, 'finance')
    def financial(action, **values):
        source = goods.current(client, row)['claims'][0]
        return goods.command(client, row, action, dict(claim_id=source['id'], claim_version=source['version'],
                                                      evidence_id=proof, **values))
    financial('terms', target_cents=30, due_date=today().isoformat(), reason='承运方原件明确找到后的累计赔付30分')
    login(client, 'manager')
    financial('terms_approve', plan_id=goods.current(client, row)['claims'][0]['pending_plan_id'], reason='本人独立确认原新赔付条件')
    login(client, 'finance')
    incoming = next(p for p in goods.current(client, row)['claims'][0]['payments'] if p['direction'] == 'in')
    financial('refund', original_id=incoming['id'], amount_cents=10, account_id=account,
              reference=uuid.uuid4().hex, business_date=today().isoformat(), confirmed=True)
    batch = rec.batch(client)
    assert batch['summary']['transfer_goods_terms']['count'] == batch['summary']['transfer_goods_refunds']['count'] == 1
    assert batch['summary']['transfer_goods_refunds']['amount_cents'] == 0
    assert batch['summary']['transfer_recovery_payments']['amount_cents'] == 30
    assert (batch['summary']['period_cash_in_cents'], batch['summary']['period_cash_out_cents']) == (40, 10)
    with sqlite3.connect(TEST_DIR / 'test.sqlite') as db:
        assert validate_sqlite(db)['verified_reconciliation_batches'] == 1
        assert db.execute('SELECT count(*) FROM cash_entries').fetchone()[0] == 2


def test_orm_clearing_constraint_accepts_the_migrated_reverse_origin():
    from app.reconciliation_models import ClearingBucket
    clause = next(c for c in ClearingBucket.__table__.constraints if c.name == 'ck_clearing_parties')
    assert "'material_found'" in str(clause.sqltext)


def test_absent_legacy_observation_tables_return_mapping_but_partial_schema_rejects():
    from app.observation_corrections_integrity import validate, TABLES
    with sqlite3.connect(':memory:') as db:
        assert validate(db) == {'corrections': 0, 'effects': 0, 'insurance_invalidations': 0, 'reminder_bases': 0}
        db.execute('CREATE TABLE ' + TABLES[0] + ' (id INTEGER PRIMARY KEY)')
        with pytest.raises(ValueError, match='本域表不完整'): validate(db)
