"""Batch staff creation: administrator-only, atomic, and never a second permission path."""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import User
from app.db import SessionLocal
from tests.conftest import PASSWORD


ROWS = [{'username': 'batch-sales', 'display_name': '批量销售', 'role': 'sales'},
        {'username': 'batch-stock', 'display_name': '批量库管', 'role': 'inventory'},
        {'username': 'batch-finance', 'display_name': '批量财务', 'role': 'finance'}]
NEW_PASSWORD = 'BatchOnly!LongPassword2026'


@contextmanager
def as_role(username):
    """A separate session for one seeded role; the admin fixture stays untouched."""
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'username': username, 'password': PASSWORD},
                              headers={'X-App-Request': '1'})
        assert response.status_code == 200, response.text
        client.headers['X-CSRF-Token'] = client.cookies.get('dealer_csrf')
        yield client


def batch(client, rows=None, store_id=1, password=NEW_PASSWORD, **extra):
    body = {'store_id': store_id, 'password': password, 'rows': rows if rows is not None else ROWS, **extra}
    return client.post('/api/users/batch', json=body)


def users_named(*names):
    with SessionLocal() as db:
        return {row.username: row for row in db.query(User).filter(User.username.in_(names)).all()}


def test_an_administrator_creates_several_staff_accounts_in_one_request(client):
    response = batch(client)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload['count'] == 3 and payload['store']['name'] == '默认门店'
    listing = {row['username']: row for row in client.get('/api/users').json()['items']}
    for row in ROWS:
        created = listing[row['username']]
        assert created['display_name'] == row['display_name']
        assert created['role'] == row['role']
        assert created['stores'] and created['stores'][0]['name'] == '默认门店'
        assert created['store_roles'][0]['role'] == row['role']
        assert created['active'] is True
        assert created['can_group_summary'] is False


def test_every_batched_account_is_audited_and_must_change_password(client):
    assert batch(client).status_code == 201
    audit = client.get('/api/audit?page=1').json()['items']
    assert sum(1 for row in audit if row['action'] == 'create_user') == 3
    assert all(account.must_change_password for account in users_named(*[r['username'] for r in ROWS]).values())


def test_a_new_account_can_log_in_but_cannot_act_before_changing_the_password(client):
    assert batch(client, rows=ROWS[:1]).status_code == 201
    with TestClient(app) as fresh:
        login = fresh.post('/api/auth/login', json={'username': 'batch-sales', 'password': NEW_PASSWORD},
                           headers={'X-App-Request': '1'})
        assert login.status_code == 200, login.text
        assert login.json()['must_change_password'] is True
        fresh.headers['X-CSRF-Token'] = fresh.cookies.get('dealer_csrf')
        blocked = fresh.post('/api/users/batch', json={'store_id': 1, 'password': NEW_PASSWORD, 'rows': ROWS})
        assert blocked.status_code == 403


@pytest.mark.parametrize('username', ['manager', 'sales', 'inventory', 'service', 'finance', 'auditor'])
def test_only_the_system_administrator_may_batch_create(username):
    with as_role(username) as other:
        response = batch(other)
        assert response.status_code == 403, response.text
        assert '仅系统管理员' in response.json()['detail']
    assert users_named(*[r['username'] for r in ROWS]) == {}


def test_a_request_without_a_session_or_csrf_token_is_refused(client):
    del client.headers['X-CSRF-Token']
    assert batch(client).status_code == 403
    with TestClient(app) as anonymous:
        assert anonymous.post('/api/users/batch', json={'store_id': 1, 'password': NEW_PASSWORD}).status_code in (401, 403)
    assert users_named(*[r['username'] for r in ROWS]) == {}


def test_the_aggregate_view_is_read_only(client):
    response = client.post('/api/users/batch', json={'store_id': 1, 'password': NEW_PASSWORD, 'rows': ROWS},
                           headers={'X-Store-ID': 'all'})
    assert response.status_code in (403, 409), response.text
    assert users_named(*[r['username'] for r in ROWS]) == {}


def test_a_duplicate_login_inside_the_paste_writes_nothing(client):
    rows = [ROWS[0], dict(ROWS[1], username=ROWS[0]['username'].upper())]
    response = batch(client, rows=rows)
    assert response.status_code == 422 and '第 2 行' in response.json()['detail']
    assert users_named('batch-sales', 'batch-stock') == {}


def test_an_existing_login_aborts_the_whole_batch(client):
    response = batch(client, rows=[ROWS[0], dict(ROWS[1], username='manager')])
    assert response.status_code == 422 and '第 2 行' in response.json()['detail']
    assert set(users_named('batch-sales', 'batch-stock', 'manager')) == {'manager'}


@pytest.mark.parametrize('row,expected', [
    ({'username': 'ab', 'display_name': '姓名', 'role': 'sales'}, '登录账号'),
    ({'username': 'has space', 'display_name': '姓名', 'role': 'sales'}, '登录账号'),
    ({'username': 'batch-ok', 'display_name': '   ', 'role': 'sales'}, '员工姓名'),
    ({'username': 'batch-ok', 'display_name': '姓名', 'role': 'admin'}, '系统管理员'),
    ({'username': 'batch-ok', 'display_name': '姓名', 'role': 'store_manager'}, '岗位'),
])
def test_a_bad_row_reports_its_line_and_writes_nothing(client, row, expected):
    response = batch(client, rows=[ROWS[0], row])
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert '第 2 行' in detail and expected in detail
    assert users_named('batch-sales', 'batch-ok') == {}


def test_the_batch_cannot_create_a_second_system_administrator(client):
    response = batch(client, rows=[{'username': 'batch-admin', 'display_name': '第二个管理员', 'role': 'admin'}])
    assert response.status_code == 422 and '系统管理员' in response.json()['detail']
    assert users_named('batch-admin') == {}


def test_a_short_initial_password_or_empty_paste_is_refused(client):
    assert batch(client, password='short').status_code == 422
    assert batch(client, rows=[]).status_code == 422
    assert batch(client, rows=[ROWS[0]] * 51).status_code == 422
    assert users_named('batch-sales') == {}


def test_an_unknown_or_disabled_store_is_refused(client):
    assert batch(client, store_id=999).status_code == 422
    closed = client.post('/api/stores', json={'code': 'CLOSED', 'name': '停用门店', 'active': False})
    assert closed.status_code == 201
    assert batch(client, store_id=closed.json()['id']).status_code == 422
    assert users_named(*[r['username'] for r in ROWS]) == {}


def test_roles_use_the_same_store_role_catalogue_as_the_single_form(client):
    for role in ('manager', 'sales', 'inventory', 'service', 'finance', 'auditor',
                 'reception', 'technician', 'customer_service'):
        response = batch(client, rows=[{'username': 'role-' + role[:8], 'display_name': '岗位' + role, 'role': role}])
        assert response.status_code == 201, (role, response.text)
    listing = {row['role'] for row in client.get('/api/users').json()['items'] if row['username'].startswith('role-')}
    assert listing == {'manager', 'sales', 'inventory', 'service', 'finance', 'auditor',
                       'reception', 'technician', 'customer_service'}
