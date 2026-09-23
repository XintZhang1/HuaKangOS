"""Explicit local roles must never persist as the account's global role."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, make_engine
from app.main import app
from app.models import User, UserStore, Store
from app.flow_engine import eligible_users, assignable
from tests.conftest import login, PASSWORD
from tests.test_app import vehicle_body
from tests.test_multistore import second_store, switch


def assign_roles(username, roles, summary=False):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        user.can_group_summary = summary
        for sid, role in roles.items():
            member = db.get(UserStore, (user.id, sid))
            if member:
                member.role = role
            else:
                db.add(UserStore(user_id=user.id, store_id=sid, role=role))
        db.commit()
        return user.id


def test_active_role_switch_refresh_and_write_use_local_role(client):
    two = second_store(client)
    uid = assign_roles('sales', {1:'inventory', two:'sales'})
    info = login(client, 'sales')
    assert info['account_role'] == 'sales' and info['role'] == 'inventory'
    assert client.post('/api/records/vehicles', json=vehicle_body()).status_code == 201
    switch(client, two)
    info = client.get('/api/auth/me').json()
    assert info['role'] == 'sales' and info['active_store_id'] == two
    assert client.post('/api/records/vehicles', json=vehicle_body()).status_code == 403
    for sid, role in [(1, 'inventory'), (two, 'sales'), (1, 'inventory')]:
        switch(client, sid)
        assert client.get('/api/auth/me').json()['role'] == role
    with SessionLocal() as db:
        assert db.get(User, uid).role == 'sales'
        assert db.get(UserStore, (uid, 1)).role == 'inventory'


def test_local_manager_cannot_administer_accounts(client):
    assign_roles('sales', {1:'manager'})
    info = login(client, 'sales')
    assert info['role'] == 'manager' and not info['can_users']
    assert client.get('/api/users').status_code == 403
    assert client.post('/api/stores', json={'code':'NO', 'name':'越权店'}).status_code == 403
    assert client.post('/api/users', json={'username':'no-admin','display_name':'测试','role':'admin','password':PASSWORD}).status_code == 403


def test_explicit_summary_grant_filters_lower_privilege_store(client):
    two = second_store(client)
    assign_roles('sales', {1:'manager', two:'sales'}, summary=True)
    login(client, 'sales')
    switch(client, 'all')
    info = client.get('/api/auth/me').json()
    assert info['aggregate_scope'] and info['role'] == 'auditor'
    assert info['group_store_ids'] == [1] and info['write_modules'] == []
    assert info['account_role'] == 'sales'
    assert client.get('/api/dashboard').json()['store_ids'] == [1]
    assert client.post('/api/records/vehicles', json=vehicle_body()).status_code == 409
    switch(client, two)
    assert client.get('/api/dashboard').status_code == 403


@pytest.mark.parametrize('role,grant', [('manager',False), ('sales',True)])
def test_summary_requires_grant_and_eligible_role(client, role, grant):
    assign_roles('sales', {1:role}, summary=grant)
    login(client, 'sales')
    switch(client, 'all')
    assert client.get('/api/dashboard').status_code == 403


@pytest.mark.parametrize('endpoint,payload', [
    ('/api/stores', {'code':'READONLY','name':'只读检查'}),
    ('/api/users', {'username':'readonly','display_name':'只读检查','role':'admin','password':PASSWORD}),
    ('/api/records/vehicles', vehicle_body()),
])
def test_aggregate_mode_blocks_all_business_and_account_writes(client, endpoint, payload):
    switch(client, 'all')
    assert client.post(endpoint, json=payload).status_code == 409


def test_password_change_updates_account_not_projection(client):
    uid = assign_roles('sales', {1:'inventory'})
    login(client, 'sales')
    changed = PASSWORD + '!'
    assert client.post('/api/auth/password', json={'current_password':PASSWORD,'new_password':changed}).status_code == 200
    assert login(client, 'sales', changed)['role'] == 'inventory'
    with SessionLocal() as db:
        assert db.get(User, uid).role == 'sales'


def test_assignment_uses_store_specific_role_without_mutation(client):
    two = second_store(client)
    uid = assign_roles('sales', {1:'finance', two:'technician'})
    with SessionLocal() as db:
        assert uid in [u.id for u in eligible_users(db, 'finance', 1)]
        assert uid not in [u.id for u in eligible_users(db, 'finance', two)]
        assert assignable(db, uid, 1, {'finance'}).role == 'finance'
        with pytest.raises(HTTPException) as refused:
            assignable(db, uid, two, {'finance'})
        assert refused.value.status_code == 422
        with pytest.raises(HTTPException):
            assignable(db, uid, two + 100, {'technician'})
        db.commit()
        assert db.get(User, uid).role == 'sales'


def test_account_api_role_mapping_updates_and_revokes_sessions(client):
    two = second_store(client)
    body = {'username':'local-role','display_name':'多岗位员工','role':'sales','password':PASSWORD,
            'store_roles':[{'store_id':1,'role':'manager'},{'store_id':two,'role':'inventory'}], 'can_group_summary':True}
    created = client.post('/api/users', json=body)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data['store_ids'] == [1,two]
    assert data['can_group_summary'] and not data['store_roles'][0]['legacy_fallback']
    with SessionLocal() as db:
        db.get(User, data['id']).must_change_password = False
        db.commit()
    with TestClient(app) as staff:
        assert login(staff, 'local-role')['role'] == 'manager'
        update = {'display_name':'多岗位员工','role':'sales','active':True,
                  'request_id':'store-role-edit-1','access_version':data['access_version'],
                  'store_roles':[{'store_id':two,'role':'technician'}], 'can_group_summary':False}
        changed = client.put(f'/api/users/{data["id"]}', json=update)
        assert changed.status_code == 200, changed.text
        assert changed.json()['store_ids'] == [two]
        assert not changed.json()['can_group_summary']
        assert staff.get('/api/auth/me').status_code == 401
        assert login(staff, 'local-role')['role'] == 'technician'
        switch(staff, 1)
        assert staff.get('/api/auth/me').status_code == 403


@pytest.mark.parametrize('extra', [
    {'store_roles':[{'store_id':1,'role':'admin'}]},
    {'store_roles':[{'store_id':1,'role':'sales'},{'store_id':1,'role':'finance'}]},
    {'store_ids':[1], 'store_roles':[{'store_id':999,'role':'sales'}]},
    {'store_roles':[{'store_id':999,'role':'sales'}]},
    {'store_roles':[]},
])
def test_bad_role_assignments_are_atomic(client, extra):
    body = {'username':'invalid-role','display_name':'错误岗位','role':'sales','password':PASSWORD, **extra}
    response = client.post('/api/users', json=body)
    assert response.status_code == 422, response.text
    assert all(row['username'] != 'invalid-role' for row in client.get('/api/users').json()['items'])


def test_membership_constraint_rejects_global_admin(client):
    with SessionLocal() as db:
        member = db.scalar(select(UserStore))
        member.role = 'admin'
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_legacy_membership_compatibility_is_explicit(client):
    login(client, 'finance')
    info = client.get('/api/auth/me').json()
    assert info['role'] == 'finance'
    login(client, 'admin')
    finance = next(u for u in client.get('/api/users').json()['items'] if u['username'] == 'finance')
    assert finance['store_roles'] == [{'store_id':1,'role':'finance','legacy_fallback':True}]


def test_role_migration_preserves_accounts_and_fallback(tmp_path):
    from alembic import command
    from alembic.config import Config
    target = 'sqlite:///' + str(tmp_path / 'roles.sqlite')
    cfg = Config('alembic.ini')
    cfg.attributes['url_override'] = target
    command.upgrade(cfg, 'c803_workflow')
    engine = make_engine(target)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO stores(id,code,name,active,created_at) VALUES (1,'ONE','测试门店',1,CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO users(id,username,display_name,password_hash,role,active,must_change_password,created_at) VALUES (1,'legacy','测试账户','synthetic','manager',1,0,CURRENT_TIMESTAMP)"))
        conn.execute(text('INSERT INTO user_stores(user_id,store_id) VALUES (1,1)'))
    command.upgrade(cfg, 'd904_store_roles')
    with engine.begin() as conn:
        assert conn.execute(text('SELECT role,can_group_summary FROM users')).one() == ('manager', 1)
        assert conn.scalar(text('SELECT role FROM user_stores')) is None
        assert not conn.exec_driver_sql('PRAGMA foreign_key_check').all()
        conn.execute(text("UPDATE user_stores SET role='inventory'"))
    with pytest.raises(RuntimeError, match='不能直接降级'):
        command.downgrade(cfg, 'c803_workflow')
    engine.dispose()
