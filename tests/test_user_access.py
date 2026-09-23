"""Real account request versions; no test client silently injects missing versions."""
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, func, event
from app.db import SessionLocal, engine
from app.main import app
from app.models import User, UserStore, AuditLog, LoginSession
from app.user_access_models import UserAccessReceipt
from tests.conftest import login, PASSWORD
from tests.test_multistore import second_store


def listed(client, username):
    return next(row for row in client.get('/api/users').json()['items'] if row['username'] == username)


def body(row, **changes):
    return {'request_id':secrets.token_hex(16), 'access_version':row['access_version'],
            'role':row['account_role'], 'display_name':row['display_name'], 'active':row['active'], **changes}


def put(client, row, values):
    return client.put('/api/users/'+str(row['id']), json=values)


def second_admin(client):
    result=client.post('/api/users',json={'username':'admin-two','display_name':'第二管理员',
        'role':'admin','password':PASSWORD})
    assert result.status_code==201,result.text
    other=TestClient(app);login(other,'admin-two')
    changed=other.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':PASSWORD+'2'})
    assert changed.status_code==200,changed.text
    login(other,'admin-two',PASSWORD+'2')
    return other


@pytest.mark.parametrize('missing',['access_version','request_id'])
def test_missing_account_envelope_refused(client,missing):
    row=listed(client,'sales');values=body(row);del values[missing]
    assert put(client,row,values).status_code==422
    assert listed(client,'sales')['access_version']==row['access_version']
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(UserAccessReceipt))==0


@pytest.mark.parametrize('version',[True,'1',0,-1])
def test_account_version_is_positive_strict_integer(client,version):
    row=listed(client,'sales')
    assert put(client,row,body(row,access_version=version)).status_code==422


def test_stale_admin_page_cannot_restore_revoked_store_and_summary(client):
    two=second_store(client);other=second_admin(client)
    try:
        row=listed(client,'sales')
        allowed=put(client,row,body(row,store_roles=[{'store_id':1,'role':'manager'},
            {'store_id':two,'role':'finance'}],can_group_summary=True))
        assert allowed.status_code==200,allowed.text
        stale=listed(other,'sales');revoke=body(stale,store_roles=[{'store_id':1,'role':'sales'}],can_group_summary=False)
        with TestClient(app) as staff:
            login(staff,'sales')
            changed=put(client,stale,revoke);assert changed.status_code==200,changed.text
            assert staff.get('/api/auth/me').status_code==401
            obsolete=body(stale,display_name='旧页面改名',store_roles=stale['store_roles'],can_group_summary=True)
            obsolete['store_roles']=[{'store_id':r['store_id'],'role':r['role']} for r in stale['store_roles']]
            refused=put(other,stale,obsolete)
            assert refused.status_code==409 and '刷新员工列表' in refused.text
            current=listed(client,'sales');assert current['store_ids']==[1] and not current['can_group_summary']
            assert current['access_version']==stale['access_version']+1
            login(staff,'sales');assert staff.get('/api/auth/me',headers={'X-Store-ID':str(two)}).status_code==403
            # Exact replay does not invalidate this newly established session.
            replay=put(client,stale,revoke);assert replay.json()==changed.json()
            assert staff.get('/api/auth/me').status_code==200
        assert put(client,stale,{**revoke,'display_name':'不同内容'}).status_code==409
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(UserAccessReceipt))==2
            assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='update_user'))==2
    finally:other.close()


def test_bad_store_mapping_rolls_back_version_receipt_and_session_revocation(client):
    row=listed(client,'sales')
    with TestClient(app) as staff:
        login(staff,'sales')
        response=put(client,row,body(row,store_roles=[{'store_id':999,'role':'finance'}]))
        assert response.status_code==422,response.text
        assert listed(client,'sales')['access_version']==row['access_version']
        assert staff.get('/api/auth/me').status_code==200
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(UserAccessReceipt))==0


def test_password_reset_stays_separate_from_access_version_and_forced_change(client):
    row=listed(client,'sales')
    reset=client.post('/api/users/'+str(row['id'])+'/password',json={'password':PASSWORD+'X','reason':'合成忘记密码'})
    assert reset.status_code==200
    assert listed(client,'sales')['access_version']==row['access_version']
    changed=put(client,row,body(row,display_name='只改姓名'))
    assert changed.status_code==200 and changed.json()['must_change_password']
    with TestClient(app) as staff:
        login(staff,'sales',PASSWORD+'X')
        assert staff.get('/api/flow/tasks').status_code==403
        assert staff.post('/api/auth/password',json={'current_password':PASSWORD+'X','new_password':PASSWORD+'Y'}).status_code==200
        login(staff,'sales',PASSWORD+'Y');assert staff.get('/api/flow/tasks').status_code==200
    assert listed(client,'sales')['access_version']==row['access_version']+1


def test_current_admin_protected_and_receipt_is_immutable(client):
    admin=listed(client,'admin')
    assert put(client,admin,body(admin,active=False)).status_code==409
    assert put(client,admin,body(admin,role='manager',store_ids=[1])).status_code==409
    row=listed(client,'sales');assert put(client,row,body(row,display_name='姓名变更')).status_code==200
    with SessionLocal() as db:
        receipt=db.scalar(select(UserAccessReceipt));receipt.result={}
        with pytest.raises(HTTPException,match='不可改写'):db.commit()
        db.rollback();db.delete(db.scalar(select(UserAccessReceipt)))
        with pytest.raises(HTTPException,match='不可改写'):db.commit()


def test_non_admin_and_group_readonly_cannot_change_access(client):
    row=listed(client,'sales');values=body(row)
    assert client.put('/api/users/'+str(row['id']),json=values,headers={'X-Store-ID':'all'}).status_code==409
    login(client,'manager');assert put(client,row,values).status_code==403
    login(client,'sales');assert put(client,row,values).status_code==403


def test_receipt_does_not_bypass_actor_revocation_or_cross_actor_version(client):
    other=second_admin(client)
    try:
        row=listed(client,'sales');values=body(row,display_name='第二管理员办理')
        result=put(other,row,values);assert result.status_code==200,result.text
        # Same key is not a receipt belonging to another administrator.
        assert put(client,row,values).status_code==409
        actor=listed(client,'admin-two')
        result=put(client,actor,body(actor,role='sales',store_roles=[{'store_id':1,'role':'sales'}]))
        assert result.status_code==200,result.text
        assert other.get('/api/auth/me').status_code==401
        login(other,'admin-two',PASSWORD+'2')
        assert put(other,row,values).status_code==403
    finally:other.close()


def test_real_two_connection_competing_account_updates(client):
    other=second_admin(client)
    try:
        row=listed(client,'sales');barrier=Barrier(2)
        def pause(connection,cursor,statement,parameters,context,executemany):
            if statement.startswith('UPDATE users SET') and 'access_version' in statement:
                barrier.wait(timeout=15)
        event.listen(engine,'before_cursor_execute',pause)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(put,c,row,body(row,display_name=name)) for c,name in [(client,'甲修改'),(other,'乙修改')]]
                responses=[f.result(timeout=25) for f in futures]
        finally:event.remove(engine,'before_cursor_execute',pause)
        assert sorted(r.status_code for r in responses)==[200,409],[(r.status_code,r.text) for r in responses]
        current=listed(client,'sales');assert current['access_version']==row['access_version']+1
        winner=next(r.json() for r in responses if r.status_code==200)
        assert current['display_name']==winner['display_name']
        with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(UserAccessReceipt))==1
    finally:other.close()


def test_mutual_administrator_revocations_keep_one_authorized_actor(client):
    other=second_admin(client)
    try:
        a,b=listed(client,'admin'),listed(client,'admin-two');barrier=Barrier(2)
        def pause(connection,cursor,statement,parameters,context,executemany):
            if statement.startswith('UPDATE users SET') and 'access_version' in statement:barrier.wait(timeout=15)
        event.listen(engine,'before_cursor_execute',pause)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(put,c,target,body(target,active=False)) for c,target in [(client,b),(other,a)]]
                responses=[f.result(timeout=25) for f in futures]
        finally:event.remove(engine,'before_cursor_execute',pause)
        assert sorted(r.status_code for r in responses)==[200,409],[(r.status_code,r.text) for r in responses]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(User).where(User.role=='admin',User.active.is_(True)))==1
            assert db.scalar(select(func.count()).select_from(UserAccessReceipt))==1
    finally:other.close()


def test_demotion_cannot_leave_active_account_without_a_store(client):
    other=second_admin(client)
    try:
        row=listed(client,'admin-two')
        refused=put(client,row,body(row,role='sales'))
        assert refused.status_code==422,refused.text
        assert listed(client,'admin-two')['account_role']=='admin'
        assert listed(client,'admin-two')['access_version']==row['access_version']
        assert other.get('/api/auth/me').status_code==200
    finally:other.close()


def test_restore_checks_receipts_and_latest_authorization(client):
    from app.user_access_integrity import validate
    from tests.conftest import TEST_DIR
    import sqlite3
    row=listed(client,'sales');response=put(client,row,body(row,display_name='恢复核对员工',store_roles=[{'store_id':1,'role':'service'}]))
    assert response.status_code==200,response.text
    with sqlite3.connect(TEST_DIR/'test.sqlite') as connection:
        assert validate(connection)=={'user_access_receipts':1}
        connection.execute("UPDATE user_stores SET role='finance' WHERE user_id=?",(row['id'],))
        with pytest.raises(ValueError,match='最后一次审计'):validate(connection)
        connection.rollback()
        connection.execute('UPDATE users SET access_version=access_version+1 WHERE id=?',(row['id'],))
        with pytest.raises(ValueError,match='回执链'):validate(connection)
        connection.rollback()
        connection.execute("UPDATE user_access_receipts SET request_data='{}'")
        with pytest.raises(ValueError,match='回执不一致'):validate(connection)
        connection.rollback()


def test_frozen_access_migration_preserves_roles_and_rejects_zero_version(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.db import make_engine
    from migrations.versions import k137_user_access as migration
    from sqlalchemy.exc import IntegrityError
    target=make_engine('sqlite:///'+str(tmp_path/'access.sqlite'))
    with target.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(40), role VARCHAR(20))')
        connection.exec_driver_sql('CREATE TABLE audit_logs (id INTEGER PRIMARY KEY)')
        connection.exec_driver_sql("INSERT INTO users VALUES (1,'old-admin','admin'),(2,'old-sales','sales')")
        with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
        assert connection.exec_driver_sql('SELECT role,access_version FROM users ORDER BY id').all()==[('admin',1),('sales',1)]
        with pytest.raises(IntegrityError):connection.exec_driver_sql('UPDATE users SET access_version=0 WHERE id=2')
        connection.exec_driver_sql('UPDATE users SET access_version=2 WHERE id=2')
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError,match='不能丢弃'):migration.downgrade()
    target.dispose()
