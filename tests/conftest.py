import os
import tempfile
from pathlib import Path
# Isolated DB; NEVER run tests against the user's configured business database.
TEST_DIR=Path(tempfile.mkdtemp(prefix='dealerdesk-tests-'))
os.environ['DATABASE_URL']='sqlite:///'+str(TEST_DIR/'test.sqlite')
os.environ['SCHEDULER_ENABLED']='false'
os.environ['FILE_SCAN_MODE']='structure_only'
os.environ['FILE_STORAGE_MODE']='blob'
os.environ['PRIVATE_FILE_ROOT']=''
os.environ['APP_ENV']='test'
# Exercise preserved legacy service regressions; production forbids this import-only switch.
os.environ['LEGACY_BUSINESS_WRITE']='true'
os.environ['ALLOW_AI_EXTERNAL']='false'
os.environ['DEEPSEEK_API_KEY']=''
os.environ['COOKIE_SECURE']='false'
os.environ['ALLOWED_HOSTS']='testserver,localhost,127.0.0.1'
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app.models import User, Store, UserStore
from app.security import hash_password
from app.main import app

PASSWORD='TestingOnly!LongPassword2026'
PASSWORD_HASH=hash_password(PASSWORD)


def login(client, username='admin', password=PASSWORD):
    r=client.post('/api/auth/login',json={'username':username,'password':password},headers={'X-App-Request':'1'})
    assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=client.cookies.get('dealer_csrf')
    return r.json()


@pytest.fixture(autouse=True)
def isolated_database():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with sqlite3.connect(TEST_DIR/'test.sqlite') as c: c.execute('PRAGMA journal_mode=WAL')
    with SessionLocal() as db:
        db.add(Store(id=1,code='MAIN',name='默认门店')); db.flush()
        for role in ('admin','manager','sales','inventory','service','finance','auditor'):
            db.add(User(username=role,display_name=role,role=role,password_hash=PASSWORD_HASH,must_change_password=False))
        db.flush()
        for u in db.query(User).all(): db.add(UserStore(user_id=u.id,store_id=1))
        db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        login(client)
        yield client
