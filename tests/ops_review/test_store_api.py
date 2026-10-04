"""Synthetic store/API/MCP boundaries; run only through the isolated review runner."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from typing import get_args
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import sessionmaker

from app import ops_feedback_api, ops_mcp, ops_store
from app.db import make_engine, utcnow
from app.models import LoginSession, Store, User, UserStore
from app.security import digest


RELEASE = 'a' * 64
OTHER_RELEASE = 'b' * 64


@pytest.fixture
def runtime_path():
    assert os.environ.get('OPS_REVIEW_ISOLATED') == '1', 'Use run_isolated.py'
    path = Path(os.environ['OPS_REVIEW_RUNTIME']) / ('store-api-' + uuid.uuid4().hex)
    path.mkdir(parents=True)
    return path


@pytest.fixture
def store(runtime_path):
    path = runtime_path / 'operations.sqlite'
    ops_store.OpsStore.initialize(path)
    return ops_store.OpsStore(path)


def feedback(store, **changes):
    payload = dict(owner_id=1, store_id=1, title='Synthetic review request',
                   description='Synthetic feedback without customer or credential data.',
                   category='improvement', request_id=str(uuid.uuid4()), route='system')
    payload.update(changes)
    return store.submit(**payload)


def report():
    return dict(release_id=RELEASE, base_sha='c' * 40, summary='Synthetic bounded proposal',
                evidence=[{'path': 'app/ops_store.py', 'line': 1, 'sha256': 'd' * 64}],
                proposed_changes=['Review this synthetic example'],
                acceptance_checks=['Run synthetic checks'], risk='low', classification='improvement')


def ready(store):
    item = feedback(store)
    lease = store.claim(RELEASE)
    assert lease['id'] == item['id']
    store.analysis_result(item['id'], lease['lease_token'], report=report())
    return item['id']


def test_active_lease_is_a_persistent_single_slot(store):
    first, second = feedback(store), feedback(store)
    lease = store.claim(RELEASE)
    assert lease['id'] == first['id']
    # Reconstructed worker instances cannot take another job while one lease lives.
    restarted = ops_store.OpsStore(store.path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: restarted.claim(RELEASE), range(2))) == [None, None]
    assert restarted.get(second['id'])['status'] == 'received'
    store.analysis_result(first['id'], lease['lease_token'], report=report())
    assert restarted.claim(RELEASE)['id'] == second['id']


def test_expired_lease_recovers_and_rejects_old_results(store, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(ops_store.time, 'time', lambda: clock[0])
    item = feedback(store)
    first = store.claim(RELEASE, lease_seconds=10)
    clock[0] = 1011.0
    restarted = ops_store.OpsStore(store.path)
    second = restarted.claim(RELEASE, lease_seconds=10)
    assert second['id'] == item['id'] and second['lease_token'] != first['lease_token']
    assert restarted.get(item['id'])['attempts'] == 2
    with pytest.raises(RuntimeError, match='lease was lost'):
        store.analysis_result(item['id'], first['lease_token'], report=report())
    with pytest.raises(RuntimeError, match='lease was lost'):
        store.model_event(item['id'], first['lease_token'], 'provider_usage', {'prompt_tokens': 1})
    restarted.analysis_result(item['id'], second['lease_token'], report=report())
    assert ops_store.OpsStore(store.path).get(item['id'])['report'] == report()


def test_explicit_retry_preserves_attempt_budget_and_source_audit(store):
    item = feedback(store)
    first = store.claim(RELEASE)
    store.analysis_result(item['id'], first['lease_token'], error='synthetic_provider_failure')
    with pytest.raises(ValueError):
        store.retry_analysis(item['id'], 'wrong_error', 'Synthetic cause has been corrected')
    store.retry_analysis(item['id'], 'synthetic_provider_failure', 'Synthetic cause has been corrected')
    second = store.claim(OTHER_RELEASE)
    assert second['release_id'] == OTHER_RELEASE
    assert store.get(item['id'])['attempts'] == 2
    store.analysis_result(item['id'], second['lease_token'], error='synthetic_provider_failure')
    store.retry_analysis(item['id'], 'synthetic_provider_failure', 'Synthetic cause has been corrected again')
    third = store.claim(OTHER_RELEASE)
    store.analysis_result(item['id'], third['lease_token'], error='synthetic_provider_failure')
    with pytest.raises(ValueError):
        store.retry_analysis(item['id'], 'synthetic_provider_failure', 'No fourth analysis may be authorized here')
    job = store.get(item['id'])
    assert job['attempts'] == 3 and job['status'] == 'needs_attention'
    retried = [json.loads(e['detail']) for e in job['events'] if e['kind'] == 'analysis_retry_requested']
    assert [e['previous_release_id'] for e in reversed(retried)] == [RELEASE, OTHER_RELEASE]


def test_crash_recovery_stops_at_three_and_never_silently_rebases(store, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(ops_store.time, 'time', lambda: clock[0])
    item = feedback(store)
    for _ in range(3):
        assert store.claim(RELEASE, lease_seconds=10)['id'] == item['id']
        clock[0] += 11
    assert store.claim(RELEASE) is None
    job = store.get(item['id'])
    assert job['attempts'] == 3 and job['error_code'] == 'analysis_attempts_exhausted'
    with pytest.raises(ValueError):
        store.retry_analysis(item['id'], job['error_code'], 'Fourth attempts must remain unavailable')
    another = feedback(store)
    store.claim(RELEASE, lease_seconds=10)
    clock[0] += 11
    assert store.claim(OTHER_RELEASE) is None
    assert store.get(another['id'])['error_code'] == 'source_release_changed'
    assert store.get(another['id'])['attempts'] == 1


def test_deduplication_and_receipts_are_owner_and_store_scoped(store):
    request_id = str(uuid.uuid4())
    first = feedback(store, request_id=request_id)
    duplicate = feedback(store, request_id=request_id)
    assert duplicate['duplicate'] and duplicate['id'] == first['id']
    with pytest.raises(ValueError):
        feedback(store, request_id=request_id, title='Different payload')
    owner = feedback(store, request_id=request_id, owner_id=2)
    branch = feedback(store, request_id=request_id, store_id=2)
    assert len({first['id'], owner['id'], branch['id']}) == 3
    assert [r['id'] for r in store.receipts(owner_id=1, store_id=1)] == [first['id']]
    assert [r['id'] for r in store.receipts(owner_id=2, store_id=1)] == [owner['id']]
    assert [r['id'] for r in store.receipts(owner_id=1, store_id=2)] == [branch['id']]


def test_unknown_notification_queries_original_event_without_resending(store, monkeypatch):
    job_id = ready(store)
    calls = []
    responses = [RuntimeError('Synthetic response unknown'), {'status': 'not_found'}]

    class FakeMail:
        async def call(self, name, args):
            calls.append((name, args))
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(ops_mcp, 'private_json', lambda _: {'token': 'synthetic-token'})
    monkeypatch.setattr(ops_mcp, 'McpClient', lambda *args: FakeMail())
    config = {'mail_client_file': 'unused', 'mail_mcp_url': 'unused'}
    result = asyncio.run(ops_mcp.deliver(config, store, job_id))
    assert result['status'] == 'uncertain'
    restarted = ops_store.OpsStore(store.path)
    assert restarted.get(job_id)['status'] == 'notifying'
    assert restarted.get(job_id)['report'] == report()
    assert asyncio.run(ops_mcp.deliver(config, restarted, job_id))['status'] == 'sending'
    assert len(calls) == 1
    with store.connect(True) as db:
        db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (job_id,))
    result = asyncio.run(ops_mcp.deliver(config, restarted, job_id))
    assert result['status'] == 'uncertain' and result['reason'] == 'notification_interrupted'
    assert [name for name, _ in calls] == ['enqueue_change_review', 'get_change_review']
    assert calls[0][1]['event_id'] == calls[1][1]['event_id'] == 'huakangos-ops:' + job_id
    job = restarted.get(job_id)
    assert job['status'] == 'needs_attention' and job['report'] == report()
    with pytest.raises(ValueError):
        restarted.retry_analysis(job_id, job['error_code'], 'An uncertain notification must never be replayed')
    assert asyncio.run(ops_mcp.deliver(config, restarted, job_id))['status'] == 'needs_attention'
    assert len(calls) == 2


def test_sent_reconciliation_preserves_report_and_review_is_append_only(store, monkeypatch):
    job_id = ready(store)
    assert store.begin_notification(job_id)
    with store.connect(True) as db:
        db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (job_id,))
    calls = []

    class FakeMail:
        async def call(self, name, args):
            calls.append((name, args))
            return {'status': 'sent', 'event_id': args['event_id'], 'provider_message_id': 'synthetic-id'}

    monkeypatch.setattr(ops_mcp, 'private_json', lambda _: {'token': 'synthetic-token'})
    monkeypatch.setattr(ops_mcp, 'McpClient', lambda *args: FakeMail())
    restarted = ops_store.OpsStore(store.path)
    asyncio.run(ops_mcp.deliver({'mail_client_file': 'unused', 'mail_mcp_url': 'unused'}, restarted, job_id))
    assert [name for name, _ in calls] == ['get_change_review']
    assert restarted.get(job_id)['status'] == 'awaiting_cutie'
    assert restarted.get(job_id)['report'] == report()
    with pytest.raises(ValueError):
        restarted.retry_analysis(job_id, None, 'A successful report must never be analyzed again')
    with pytest.raises(ValueError):
        restarted.record_review(job_id, 'pr_opened', 'Synthetic review completed', 'https://github.com/other/repo/pull/1')
    args = (job_id, 'pr_opened', 'Synthetic review completed', 'https://github.com/XintZhang1/HuaKangOS/pull/1')
    assert restarted.record_review(*args) == {'recorded': True, 'duplicate': False}
    assert restarted.record_review(*args) == {'recorded': True, 'duplicate': True}
    with pytest.raises(ValueError):
        restarted.record_review(job_id, 'declined', 'Cannot overwrite the earlier review', '')
    assert len(restarted.search_memory('Synthetic')) == 1


def test_mcp_roles_cannot_escalate_or_reveal_employee_identifiers(store, monkeypatch):
    item = feedback(store)
    config = {role + '_token': role.ljust(44, '_') for role in ('agent', 'worker', 'reviewer')}
    monkeypatch.setattr(ops_mcp, 'runtime', lambda: (config, store, SimpleNamespace()))

    def rpc(client, role, method, params=None, **headers):
        auth = {'Authorization': 'Bearer ' + config[role + '_token']} if role else {}
        return client.post('/mcp', headers=auth | headers,
                           json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})

    with TestClient(ops_mcp.app) as client:
        assert rpc(client, None, 'tools/list').status_code == 401
        assert rpc(client, 'reviewer', 'tools/list', Origin='https://synthetic.invalid').status_code == 403
        reads = {'source_snapshot', 'search_code', 'read_code', 'search_memory', 'service_health'}
        expected = {'agent': reads, 'worker': reads | {'enqueue_change_review'},
                    'reviewer': reads | {'list_change_reviews', 'get_change_review',
                                         'record_change_review', 'retry_analysis'}}
        for role, names in expected.items():
            assert {t['name'] for t in rpc(client, role, 'tools/list').json()['result']['tools']} == names
            assert 'error' in rpc(client, role, 'tools/call', {'name': 'arbitrary_shell', 'arguments': {}}).json()
        for role, name in [('agent', 'retry_analysis'), ('worker', 'record_change_review'),
                           ('reviewer', 'enqueue_change_review')]:
            assert 'error' in rpc(client, role, 'tools/call', {'name': name, 'arguments': {}}).json()
        output = rpc(client, 'reviewer', 'tools/call',
                     {'name': 'get_change_review', 'arguments': {'job_id': item['id']}}).json()['result']['structuredContent']
        assert not {'owner_id', 'store_id', 'request_id', 'payload_hash', 'lease_token'} & output.keys()
        assert store.get(item['id'])['status'] == 'received'


@pytest.fixture
def feedback_client(store, runtime_path, monkeypatch):
    # Real auth/CSRF/tenancy dependencies operate on four synthetic tables only.
    engine = make_engine('sqlite:///' + str(runtime_path / 'business.sqlite'))
    for table in (Store.__table__, User.__table__, UserStore.__table__, LoginSession.__table__):
        table.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        db.add_all([Store(id=1, code='SYN-1', name='Synthetic one'),
                    Store(id=2, code='SYN-2', name='Synthetic two')])
        db.add_all([User(id=n, username=f'synthetic-{n}', display_name=f'Synthetic {n}',
                        password_hash='unused-synthetic-password', role='sales', must_change_password=False)
                    for n in (1, 2)])
        db.flush()
        db.add_all([UserStore(user_id=1, store_id=1, role='sales'),
                    UserStore(user_id=2, store_id=1, role='sales'),
                    UserStore(user_id=2, store_id=2, role='sales')])
        db.add_all([LoginSession(id=digest(f'synthetic-session-{n}'), user_id=n,
                                csrf_hash=digest('synthetic-csrf'), expires_at=utcnow() + timedelta(hours=1))
                    for n in (1, 2)])
    api = FastAPI()
    api.include_router(ops_feedback_api.router)

    def scoped_db():
        with sessions() as db:
            yield db

    api.dependency_overrides[ops_feedback_api.get_db] = scoped_db
    monkeypatch.setenv('OPS_STATE_DB', str(store.path))
    with TestClient(api) as client:
        yield client
    engine.dispose()


def test_feedback_intake_keeps_real_auth_csrf_and_tenant_receipts(feedback_client, store):
    client = feedback_client
    payload = dict(title='Synthetic system feedback', description='Synthetic bounded feedback for review.',
                   category='bug', route='system', consent_analysis=True, request_id=str(uuid.uuid4()))
    headers = {'X-CSRF-Token': 'synthetic-csrf', 'X-Store-ID': '1'}
    assert client.post('/api/feedback', json=payload, headers=headers).status_code == 401
    client.cookies.set('dealer_session', 'synthetic-session-1')
    assert client.post('/api/feedback', json=payload, headers={'X-Store-ID': '1'}).status_code == 403
    assert client.post('/api/feedback', json=payload, headers=headers | {'X-Store-ID': '2'}).status_code == 403
    assert client.post('/api/feedback', json=payload, headers=headers | {'X-Store-ID': 'all'}).status_code == 403
    first = client.post('/api/feedback', json=payload, headers=headers)
    assert first.status_code == 201 and first.json()['status'] == 'received'
    repeated = client.post('/api/feedback', json=payload, headers=headers)
    assert repeated.status_code == 201 and repeated.json()['duplicate'] is True
    assert repeated.json()['id'] == first.json()['id']
    assert client.post('/api/feedback', json=payload | {'title': 'Changed payload'}, headers=headers).status_code == 409
    assert len(client.get('/api/feedback', headers={'X-Store-ID': '1'}).json()['items']) == 1
    client.cookies.set('dealer_session', 'synthetic-session-2')
    assert client.get('/api/feedback', headers={'X-Store-ID': '1'}).json()['items'] == []
    assert client.get('/api/feedback', headers={'X-Store-ID': '2'}).json()['items'] == []
    owner_two = client.post('/api/feedback', json=payload, headers=headers)
    assert owner_two.status_code == 201 and owner_two.json()['id'] != first.json()['id']
    assert len(store.list_jobs()) == 2


def test_feedback_route_contract_and_strict_consent(feedback_client):
    js = (Path(__file__).resolve().parents[2] / 'web' / 'feedback.js').read_text(encoding='utf-8')
    entries = re.search(r'const FEEDBACK_MODULES=\{([^}]+)\};', js).group(1)
    frontend = {quoted or plain for quoted, plain in re.findall(r"(?:^|,)(?:'([^']+)'|([a-z]+)):", entries)}
    backend = set(get_args(ops_feedback_api.FeedbackInput.model_fields['route'].annotation))
    assert frontend == backend and 'system' in backend
    client = feedback_client
    client.cookies.set('dealer_session', 'synthetic-session-1')
    headers = {'X-CSRF-Token': 'synthetic-csrf', 'X-Store-ID': '1'}
    payload = dict(title='Synthetic feedback', description='Synthetic bounded feedback for review.',
                   category='bug', route='system', consent_analysis=True, request_id=str(uuid.uuid4()))
    for changes in ({'route': 'unknown'}, {'consent_analysis': False}, {'consent_analysis': 'true'},
                    {'store_id': 2}, {'report': {'summary': 'Untrusted injected report'}}):
        assert client.post('/api/feedback', json=payload | changes, headers=headers).status_code == 422


@pytest.mark.parametrize('params', [None, []], ids=['null', 'array'])
def test_mcp_rejects_non_object_params_before_dispatch(store, monkeypatch, params):
    config = {role + '_token': role.ljust(44, '_') for role in ('agent', 'worker', 'reviewer')}
    monkeypatch.setattr(ops_mcp, 'runtime', lambda: (config, store, SimpleNamespace()))
    dispatched = []

    async def unexpected_dispatch(*args):
        dispatched.append(args)
        raise AssertionError('Malformed RPC parameters reached a tool')

    monkeypatch.setattr(ops_mcp, 'dispatch', unexpected_dispatch)
    with TestClient(ops_mcp.app) as client:
        response = client.post('/mcp', headers={'Authorization': 'Bearer ' + config['agent_token']},
                               json={'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': params})
    assert response.status_code == 200
    body = response.json()
    assert body['jsonrpc'] == '2.0' and body['id'] == 7
    assert body['error']['code'] == -32602 and 'result' not in body
    assert dispatched == [] and store.list_jobs() == []


def test_mcp_non_ascii_authorization_is_unauthorized(store, monkeypatch):
    config = {role + '_token': role.ljust(44, '_') for role in ('agent', 'worker', 'reviewer')}
    monkeypatch.setattr(ops_mcp, 'runtime', lambda: (config, store, SimpleNamespace()))
    with TestClient(ops_mcp.app) as client:
        # Bytes preserve the non-ASCII header through HTTPX into the real ASGI request.
        response = client.post('/mcp', headers=[(b'authorization', b'Bearer invalid-\xff')],
                               json={'jsonrpc': '2.0', 'id': 8, 'method': 'tools/list', 'params': {}})
    assert response.status_code == 401
    assert response.json() == {'error': 'unauthorized'}
    assert store.list_jobs() == []
