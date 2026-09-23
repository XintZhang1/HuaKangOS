"""Synthetic account receipt seed and real PostgreSQL two-connection CAS."""
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import User,UserStore,Store
from app.schemas import UserUpdate
from app.user_access_models import UserAccessReceipt
from app.user_access_service import change_access
from app.main import account_info,assign_stores
from app.tenancy import set_scope


def seed(client):
    """Call after all synthetic fixture assignments; no actual company user is read."""
    from tests.conftest import login,PASSWORD
    login(client)
    client.headers['X-Store-ID']='1'
    created=client.post('/api/users',json={'username':'pg-access-'+secrets.token_hex(4),
        'display_name':'合成授权恢复员工','role':'sales','password':PASSWORD,
        'store_roles':[{'store_id':1,'role':'sales'}]})
    assert created.status_code==201,created.text
    row=created.json()
    result=client.put('/api/users/'+str(row['id']),json={'request_id':secrets.token_hex(16),
        'access_version':row['access_version'],'display_name':'合成授权恢复已核对',
        'role':'sales','active':True,'store_roles':[{'store_id':1,'role':'service'}],
        'can_group_summary':False})
    assert result.status_code==200,result.text
    return result.json()['id']


def concurrency_checks(engine):
    """Engine must belong to postgres_acceptance's owned temporary instance."""
    assert engine.dialect.name=='postgresql'
    with Session(engine) as db:
        sid=db.scalar(select(Store.id).where(Store.active.is_(True)).order_by(Store.id))
        # Unique synthetic accounts isolate this check from earlier fixture roles.
        users=[User(username='pg-cas-'+secrets.token_hex(5),display_name='合成并发管理员' if i<2 else '合成并发员工',
            role='admin' if i<2 else 'sales',password_hash='synthetic-no-login',must_change_password=False) for i in range(3)]
        db.add_all(users);db.flush();db.add(UserStore(user_id=users[2].id,store_id=sid,role='sales'))
        ids=[u.id for u in users];db.commit()
    barrier=Barrier(2)
    def attempt(actor_id,label):
        with Session(engine,expire_on_commit=False) as db:
            set_scope(db,[sid],sid,global_audit=True)
            actor=db.scalar(select(User).where(User.id==actor_id))
            target=db.scalar(select(User).where(User.id==ids[2]));version=target.access_version
            body=UserUpdate(request_id=secrets.token_hex(16),access_version=version,
                display_name=label,role='sales',active=True)
            barrier.wait(timeout=15)
            try:
                result=change_access(db,actor,ids[2],body,account_info,assign_stores)
                return 200,result['display_name']
            except HTTPException as error:return error.status_code,error.detail
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(attempt,ids[i],'合成并发结果'+str(i)) for i in range(2)]
        outcomes=[j.result(timeout=30) for j in jobs]
    assert sorted(r[0] for r in outcomes)==[200,409],outcomes
    with Session(engine) as db:
        target=db.get(User,ids[2]);assert target.access_version==2
        assert target.display_name==next(label for code,label in outcomes if code==200)
        assert db.scalar(select(func.count()).select_from(UserAccessReceipt).where(UserAccessReceipt.target_id==target.id))==1
    return ['account_access_two_connection_cas_refuses_stale_grant']
