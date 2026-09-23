"""Real registered bootstrap API; isolated fresh SQLite, never the user's preview."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import secrets
from types import SimpleNamespace
import time
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.db import Base, get_db
from app.main import app
from app.models import AppMetadata, Store, User, UserStore
from app.local_preview import MARKER_KEY, marker_from_disk, preview_root
from app import local_preview_api as api
from app.security import verify_password


@pytest.fixture
def preview(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    root = tmp_path / 'huakangos' / 'test-preview'; root.mkdir(parents=True)
    url = 'sqlite:///' + str(root / 'preview.sqlite')
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 10})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    instance = {'instance_id': str(uuid.uuid4()), 'schema': 1}
    (root / 'preview.json').write_text(json.dumps(instance), encoding='utf-8')
    token = secrets.token_urlsafe(32)
    ticket = {'instance_id': instance['instance_id'], 'token_hash': hashlib.sha256(token.encode()).hexdigest(), 'expires_at': time.time()+900}
    (root / 'bootstrap.json').write_text(json.dumps(ticket), encoding='utf-8')
    with factory() as db:
        db.add(AppMetadata(key=MARKER_KEY, value={**instance, 'setup_complete': False})); db.commit()
    def dependency():
        with factory() as db:
            try: yield db
            finally: db.rollback()
    app.dependency_overrides[get_db] = dependency
    monkeypatch.setenv('HUAKANGOS_LOCAL_PREVIEW', '1')
    monkeypatch.setenv('HUAKANGOS_PREVIEW_ROOT', str(root))
    monkeypatch.setattr(api, 'settings', SimpleNamespace(environment='local', database_url=url))
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 51111)) as client:
        yield SimpleNamespace(root=root, client=client, factory=factory, token=token, ticket=ticket, instance=instance,
                              password=secrets.token_urlsafe(24), headers={'X-App-Request':'1','X-Local-Preview-Token':token})
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def submit(p, username='previewadmin', **kwargs):
    return p.client.post('/api/local-preview/bootstrap', json={'username':username, 'password':kwargs.pop('password',p.password)}, headers=kwargs.pop('headers',p.headers), **kwargs)


def test_first_admin_login_then_replay_never_resets(preview):
    p=preview
    assert p.client.get('/api/local-preview/status').json()['bootstrap_required'] is True
    r=submit(p); assert r.status_code==200,r.text
    assert p.token not in r.text and p.password not in r.text
    assert p.client.get('/api/local-preview/status').json()['bootstrap_required'] is False
    assert submit(p,username='secondadmin').status_code==409
    r=p.client.post('/api/auth/login',json={'username':'previewadmin','password':p.password},headers={'X-App-Request':'1'})
    assert r.status_code==200,r.text
    assert r.json()['role']=='admin'
    assert p.client.get('/api/auth/me').status_code==200
    with p.factory() as db:
        user=db.scalar(select(User)); assert verify_password(p.password,user.password_hash)
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.scalar(select(func.count()).select_from(UserStore))==1
        assert db.scalar(select(Store)).code=='PREVIEW'
    assert marker_from_disk(p.root)[1]==1


@pytest.mark.parametrize('failure',['missing','wrong','expired','future','instance','header'])
def test_invalid_ticket_refused_without_data(preview,failure):
    p=preview; headers=dict(p.headers)
    if failure=='missing':headers.pop('X-Local-Preview-Token')
    if failure=='wrong':headers['X-Local-Preview-Token']=secrets.token_urlsafe(32)
    if failure=='expired':p.ticket['expires_at']=time.time()-1
    if failure=='future':p.ticket['expires_at']=time.time()+3600
    if failure=='instance':p.ticket['instance_id']=str(uuid.uuid4())
    if failure=='header':headers.pop('X-App-Request')
    (p.root/'bootstrap.json').write_text(json.dumps(p.ticket),encoding='utf-8')
    r=submit(p,headers=headers);assert r.status_code==403,r.text
    assert p.token not in r.text
    with p.factory() as db:assert db.scalar(select(func.count()).select_from(User))==0


@pytest.mark.parametrize('environment',['test','production'])
def test_never_active_in_test_or_production(preview,environment):
    api.settings.environment=environment
    assert submit(preview).status_code==404


def test_flag_remote_origin_and_ordinary_login(preview,monkeypatch):
    p=preview
    with TestClient(app,base_url='http://127.0.0.1',client=('192.168.1.10',1234)) as remote:
        assert remote.get('/api/local-preview/status').status_code==403
        assert remote.post('/api/local-preview/bootstrap',json={'username':'admin','password':p.password},headers={**p.headers,'X-Forwarded-For':'127.0.0.1'}).status_code==403
    assert submit(p,headers={**p.headers,'Origin':'https://example.org'}).status_code==403
    assert submit(p,headers={**p.headers,'Sec-Fetch-Site':'cross-site'}).status_code==403
    monkeypatch.delenv('HUAKANGOS_LOCAL_PREVIEW')
    assert p.client.get('/api/local-preview/status').status_code==404
    assert p.client.post('/api/auth/login',json={'username':'admin','password':p.password},headers={'X-App-Request':'1'}).status_code==401


def test_password_and_username_validation_no_echo(preview):
    p=preview
    for password in ('short',secrets.token_urlsafe(128)):
        r=submit(p,password=password);assert r.status_code==422
        assert password not in r.text
    assert submit(p,username='<script>').status_code==422


def test_existing_user_unmarked_db_and_wrong_path_never_adopted(preview):
    p=preview
    with p.factory() as db:
        db.add(User(username='existing',role='admin',display_name='existing',password_hash='untouched',must_change_password=False));db.commit()
    assert submit(p).status_code==409
    with p.factory() as db:
        assert db.scalar(select(User)).password_hash=='untouched'
        db.delete(db.scalar(select(AppMetadata)));db.commit()
    assert submit(p).status_code==409
    with pytest.raises(ValueError,match='没有本地预览标记'):marker_from_disk(p.root)
    api.settings.database_url='sqlite:///'+str(p.root.parent/'company.sqlite')
    assert submit(p).status_code==409
    with pytest.raises(ValueError):preview_root(p.root.parent.parent/'company')


def test_competing_first_admin_requests_only_one_wins(preview):
    p=preview
    def run(name):
        with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as client:
            return client.post('/api/local-preview/bootstrap',json={'username':name,'password':p.password},headers=p.headers).status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(run,['firstadmin','secondadmin']))
    assert sorted(results)==[200,409],results
    with p.factory() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.scalar(select(func.count()).select_from(Store))==1


def test_rotated_link_invalidates_old_but_reuses_instance(preview):
    p=preview;old=p.client.get('/api/local-preview/status').json()
    new=secrets.token_urlsafe(32);p.ticket['token_hash']=hashlib.sha256(new.encode()).hexdigest()
    (p.root/'bootstrap.json').write_text(json.dumps(p.ticket),encoding='utf-8')
    assert submit(p).status_code==403
    assert submit(p,headers={**p.headers,'X-Local-Preview-Token':new}).status_code==200
    now=p.client.get('/api/local-preview/status').json()
    assert (now['pid'],now['instance_id'])==(old['pid'],old['instance_id'])


def test_health_reports_startup_source_not_changed_files(preview, monkeypatch):
    before = preview.client.get('/api/local-preview/status').json()
    monkeypatch.setattr(api, 'source_identity', lambda: {'repository_id': 'new-place', 'source_fingerprint': 'new-code'})
    after = preview.client.get('/api/local-preview/status').json()
    assert after['repository_id'] == before['repository_id']
    assert after['source_fingerprint'] == before['source_fingerprint']
    assert 'repository' not in after


def test_database_bound_to_other_repository_is_not_adopted(preview):
    manifest = {**preview.instance, 'repository_id': 'another-source'}
    (preview.root / 'preview.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='另一份源码'):
        marker_from_disk(preview.root)
