"""A deactivated current store must read as "pick another store", not as a permission error."""
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Store, User, UserStore
from app.security import hash_password
from tests.conftest import PASSWORD, login


def add_store(code, name, active=True):
    with SessionLocal() as db:
        row = Store(code=code, name=name, active=active)
        db.add(row); db.commit()
        return row.id


def add_staff(username, role, store_ids):
    with SessionLocal() as db:
        user = User(username=username, display_name=username, role=role,
                    password_hash=hash_password(PASSWORD), must_change_password=False)
        db.add(user); db.flush()
        for store_id in store_ids:
            db.add(UserStore(user_id=user.id, store_id=store_id))
        db.commit()
        return user.id


def open_store(store_id, active):
    with SessionLocal() as db:
        row = db.get(Store, store_id)
        row.active = active
        db.commit()


def test_an_administrator_working_in_a_deactivated_store_is_told_to_pick_another_one(client):
    second = add_store('CD2', '合成的第二家门店')
    client.headers['X-Store-ID'] = str(second)
    assert client.get('/api/flow/tasks').status_code == 200
    assert client.put('/api/stores/%d' % second,
                      json={'code': 'CD2', 'name': '合成的第二家门店', 'active': False}).status_code == 200
    response = client.get('/api/flow/tasks')
    assert response.status_code == 409, response.text
    assert '当前门店已停用' in response.json()['detail']
    assert '重新选择门店' in response.json()['detail']


def test_the_same_session_recovers_by_asking_without_a_store_or_with_an_active_one(client):
    second = add_store('CD3', '合成的第三家门店')
    client.headers['X-Store-ID'] = str(second)
    open_store(second, False)
    assert client.get('/api/flow/tasks').status_code == 409
    del client.headers['X-Store-ID']
    assert client.get('/api/flow/tasks').status_code == 200
    assert client.get('/api/auth/me').json()['active_store_id'] == 1


def test_a_deleted_store_reads_the_same_way(client):
    client.headers['X-Store-ID'] = '4242'
    response = client.get('/api/flow/tasks')
    assert response.status_code == 409 and '当前门店已停用或不存在' in response.json()['detail']


def test_an_active_store_the_employee_cannot_access_stays_a_permission_error(client):
    other = add_store('CD4', '合成的第四家门店')
    staff = add_staff('stale-sales', 'sales', [1])
    with TestClient(app) as sales:
        login(sales, 'stale-sales', PASSWORD)
        sales.headers['X-Store-ID'] = str(other)
        response = sales.get('/api/flow/tasks')
        assert response.status_code == 403
        assert response.json()['detail'] == '没有该门店的访问权限'
        assert '停用' not in response.json()['detail']
        sales.headers['X-Store-ID'] = str(1)
        assert sales.get('/api/flow/tasks').status_code == 200
    assert staff


def test_an_employee_whose_only_store_is_closed_is_told_to_ask_an_administrator(client):
    second = add_store('CD5', '合成的第五家门店')
    add_staff('stale-service', 'service', [second])
    open_store(second, False)
    with TestClient(app) as staff:
        login(staff, 'stale-service', PASSWORD)
        response = staff.get('/api/flow/tasks')
        assert response.status_code == 403
        assert '尚未分配可用门店' in response.json()['detail']


def test_the_aggregate_read_only_rule_is_unchanged(client):
    client.headers['X-Store-ID'] = 'all'
    assert client.get('/api/auth/me').status_code == 200
    client.headers['X-Store-ID'] = 'all'
    response = client.post('/api/stores', json={'code': 'CD6', 'name': '合成的第六家门店', 'active': True})
    assert response.status_code == 409


def test_a_deactivated_store_outside_the_employees_assignments_is_not_disclosed(client):
    other = add_store('CD7', '合成的第七家门店')
    add_staff('stale-inventory', 'inventory', [1])
    open_store(other, False)
    with TestClient(app) as staff:
        login(staff, 'stale-inventory', PASSWORD)
        staff.headers['X-Store-ID'] = str(other)
        response = staff.get('/api/flow/tasks')
        assert response.status_code == 403, response.text
        assert response.json()['detail'] == '没有该门店的访问权限'
        assert '停用' not in response.json()['detail'] and '不存在' not in response.json()['detail']
        # An id that was never a store behaves the same way: no existence probing.
        staff.headers['X-Store-ID'] = '98765'
        probe = staff.get('/api/flow/tasks')
        assert probe.status_code == 403 and probe.json()['detail'] == '没有该门店的访问权限'


def test_an_employee_keeps_the_actionable_message_for_their_own_closed_store(client):
    second = add_store('CD8', '合成的第八家门店')
    add_staff('stale-reception', 'reception', [second])
    open_store(second, False)
    with TestClient(app) as staff:
        login(staff, 'stale-reception', PASSWORD)
        staff.headers['X-Store-ID'] = str(second)
        response = staff.get('/api/flow/tasks')
        assert response.status_code == 409, response.text
        assert '当前门店已停用' in response.json()['detail']
        # Without the store header the session has nothing to work in and says so.
        staff.headers.pop('X-Store-ID')
        assert '尚未分配可用门店' in staff.get('/api/flow/tasks').json()['detail']
