"""Registered API tests, all on independent synthetic local databases."""
from datetime import timedelta
import hashlib
import io
import json
import sqlite3
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, text
from app.db import SessionLocal, utcnow, engine
from app.models import User, UserStore, Store
from app.flow_models import Case, Customer, FileAsset, FlowEvent, Task
from app.dossier_grant_models import DossierGrant, DossierGrantFile, DossierDecision, DossierAccess, DossierReceipt
from app.dossier_grant_service import authority
from app.tenancy import set_scope
from tests.conftest import login, PASSWORD_HASH

API = '/api/dossier-grants'


def switch(c, name, sid=1):
    c.headers.pop('X-Store-ID', None)
    login(c, name)
    c.headers['X-Store-ID'] = str(sid)


def make_user(db, name, role, sid):
    u = User(username=name, display_name='合成' + name, role=role, password_hash=PASSWORD_HASH, must_change_password=False)
    db.add(u)
    db.flush()
    db.add(UserStore(user_id=u.id, store_id=sid))
    return u.id


def setup(c, *, kind='lead', file_category='evidence'):
    with SessionLocal() as db:
        db.add_all([Store(id=2, code='B', name='合成直营二店'), Store(id=3, code='C', name='合成直营三店')])
        db.flush()
        receiver = make_user(db, 'receiver', 'sales' if kind == 'lead' else 'service', 2)
        peer = make_user(db, 'peer', 'sales' if kind == 'lead' else 'service', 2)
        outsider = make_user(db, 'outsider', 'sales', 3)
        manager2 = make_user(db, 'manager2', 'manager', 2)
        owner = db.scalar(select(User).where(User.username == 'sales'))
        customer = Customer(store_id=1, name='合成客户—非真实个人', phone='13900000000', owner_id=owner.id)
        db.add(customer)
        db.flush()
        case = Case(store_id=1, number='SHARE-001', kind=kind, title='合成原业务', state='new',
            business_date=utcnow().date(), owner_id=owner.id, created_by=owner.id, customer_id=customer.id,
            amount_cents=12500, cost_cents=5100,
            data={'private_nested': {'account_number': 'DO-NOT-EXPOSE'}, 'evidence_id': 34567})
        db.add(case)
        db.flush()
        db.add(FlowEvent(store_id=1, case_id=case.id, actor_id=owner.id, action='create', label='原始办理',
                         before_state='', after_state='new', detail={'account_number': 'SECRET', 'file_id': 999999}))
        db.commit()
        cid = case.id
    switch(c, 'sales')
    # Original upload route enforces structure checks and appends original events.
    uploaded = c.post(f'/api/flow/cases/{cid}/files', files={'file': ('合成原件.txt', b'Synthetic dossier only', 'text/plain')},
                      data={'category': file_category})
    assert uploaded.status_code == 200, uploaded.text
    fid = uploaded.json()['id']
    case = c.get(f'/api/flow/cases/{cid}').json()
    return {'case': case, 'file_id': fid, 'receiver': receiver, 'peer': peer,
            'outsider': outsider, 'manager2': manager2, 'owner': case['owner_id']}


def proposal(c, setup, *, request_id=None, status=201, **changes):
    values = {'source_case_id': setup['case']['id'], 'source_case_version': setup['case']['version'],
        'to_store_id': 2, 'recipient_id': setup['receiver'], 'include_record': True,
        'include_contact': False, 'include_financials': False,
        'file_ids': [setup['file_id']], 'purpose': '本次客户跨店办理核对原单',
        'expires_at': (utcnow() + timedelta(days=3)).isoformat() + 'Z', 'confirmed': True, **changes}
    body = {'request_id': request_id or uuid.uuid4().hex, 'values': values}
    r = c.post(API, json=body)
    assert r.status_code == status, r.text
    return (r.json()['grant'] if status == 201 else r.json()), body


def decide(c, grant, action='approve', *, status=200, request_id=None, version=None):
    body = {'request_id': request_id or uuid.uuid4().hex, 'version': version or grant['version'],
            'values': {'reason': '已核对原单、指定员工和逐件范围', 'confirmed': True}}
    r = c.post(f'{API}/{grant["id"]}/actions/{action}', json=body)
    assert r.status_code == status, r.text
    return (r.json()['grant'] if status == 200 else r.json()), body


def approved(c, **options):
    data = setup(c)
    grant, body = proposal(c, data, **options)
    switch(c, 'manager')
    grant, _ = decide(c, grant)
    return data, grant, body


def test_proposal_independent_review_exact_receiver_and_native_routes_stay_closed(client):
    data = setup(client)
    before = client.get(f'/api/flow/cases/{data["case"]["id"]}').json()
    grant, _ = proposal(client, data)
    assert grant['status'] == 'pending'
    assert grant['preview']['case']['version'] == data['case']['version']
    decide(client, grant, status=403)
    switch(client, 'receiver', 2)
    meta = client.get(API + f'/{grant["id"]}').json()
    assert not meta['can_read'] and 'preview' not in meta and 'files' not in meta
    assert client.get(API + f'/{grant["id"]}/record').status_code == 403
    switch(client, 'manager')
    grant, _ = decide(client, grant)
    assert grant['status'] == 'approved' and grant['version'] == 2
    switch(client, 'sales')
    after = client.get(f'/api/flow/cases/{data["case"]["id"]}').json()
    assert before == after  # No source mutation, extra task or business event.
    switch(client, 'receiver', 2)
    response = client.get(API + f'/{grant["id"]}/record')
    assert response.status_code == 200, response.text
    record = response.json()['record']
    assert record['case']['id'] == data['case']['id']
    assert record['customer'] == {'name': '合成客户—非真实个人'}
    assert 'financials' not in record
    assert 'SECRET' not in response.text and 'DO-NOT-EXPOSE' not in response.text
    assert 'actions' not in record and 'payments' not in record and 'children' not in record
    file = client.get(API + f'/{grant["id"]}/files/{data["file_id"]}')
    assert file.status_code == 200 and file.content == b'Synthetic dossier only'
    assert file.headers['cache-control'] == 'no-store'
    assert file.headers['content-security-policy'].startswith('sandbox')
    assert client.get(f'/api/flow/cases/{data["case"]["id"]}').status_code == 404
    assert client.get(f'/api/flow/files/{data["file_id"]}').status_code == 404
    for name, sid in [('peer', 2), ('manager2', 2), ('outsider', 3)]:
        switch(client, name, sid)
        assert client.get(API + f'/{grant["id"]}').status_code == 404
        assert client.get(API + f'/{grant["id"]}/record').status_code == 404
        assert client.get(API + f'/{grant["id"]}/files/{data["file_id"]}').status_code == 404
        assert client.get(API).json()['items'] == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DossierReceipt)) == 2


def test_revocation_cancels_old_download_urls_and_replays_return_current_state(client):
    data, grant, original = approved(client)
    switch(client, 'receiver', 2)
    url = API + f'/{grant["id"]}/files/{data["file_id"]}'
    assert client.get(url).status_code == 200
    switch(client, 'manager')
    revoked, revoke_body = decide(client, grant, 'revoke')
    assert revoked['status'] == 'revoked'
    again = client.post(API + f'/{grant["id"]}/actions/revoke', json=revoke_body)
    assert again.status_code == 200 and again.json()['replayed']
    switch(client, 'sales')
    replay = client.post(API, json=original)
    assert replay.status_code == 201 and replay.json()['grant']['status'] == 'revoked'
    switch(client, 'receiver', 2)
    assert client.get(url).status_code == 403
    assert client.get(API + f'/{grant["id"]}/record').status_code == 403
    meta = client.get(API + f'/{grant["id"]}').json()
    assert 'preview' not in meta and 'files' not in meta and not meta['can_read']


def test_one_file_does_not_open_identical_bytes_source_version_or_new_upload(client):
    data, grant, _ = approved(client)
    switch(client, 'sales')
    r = client.post(f'/api/flow/cases/{data["case"]["id"]}/files', files={'file': ('same.txt', b'Synthetic dossier only', 'text/plain')}, data={'category': 'inspection'})
    assert r.status_code == 200, r.text
    other = r.json()['id']
    assert other != data['file_id']
    switch(client, 'receiver', 2)
    assert client.get(API + f'/{grant["id"]}/files/{other}').status_code == 404
    result = client.get(API + f'/{grant["id"]}/record').json()
    assert result['record'] == grant['preview']
    assert [f['id'] for f in result['files']] == [data['file_id']]
    assert client.get(API + f'/{grant["id"]}/files/{data["file_id"]}').status_code == 200


def test_file_only_grant_contains_no_record_or_customer(client):
    data, grant, _ = approved(client, include_record=False)
    switch(client, 'receiver', 2)
    assert client.get(API + f'/{grant["id"]}/record').status_code == 403
    r = client.get(API + f'/{grant["id"]}/files')
    assert r.status_code == 200 and len(r.json()['files']) == 1
    assert 'record' not in r.json() and 'customer' not in r.json()
    assert client.get(API + f'/{grant["id"]}/files/{data["file_id"]}').status_code == 200


def test_expired_at_read_time_not_just_page_open(client, monkeypatch):
    from app import dossier_grant_service as service
    data, grant, _ = approved(client)
    switch(client, 'receiver', 2)
    assert client.get(API + f'/{grant["id"]}/record').status_code == 200
    monkeypatch.setattr(service, 'utcnow', lambda: utcnow() + timedelta(days=4))
    assert client.get(API + f'/{grant["id"]}/files/{data["file_id"]}').status_code == 403
    assert client.get(API + f'/{grant["id"]}/record').status_code == 403
    assert client.get(API + f'/{grant["id"]}').json()['effective_status'] == 'expired'


@pytest.mark.parametrize('change', ['recipient_version', 'recipient_role', 'requester_version', 'reviewer_version', 'disable_store'])
def test_permission_changes_suspend_approved_grant(client, change):
    data, grant, _ = approved(client)
    with SessionLocal() as db:
        if change == 'recipient_role':
            db.scalar(select(UserStore).where(UserStore.user_id == data['receiver'], UserStore.store_id == 2)).role = 'service'
        elif change == 'disable_store':
            db.get(Store, 1).active = False
        else:
            target = data['receiver'] if change == 'recipient_version' else data['owner'] if change == 'requester_version' else db.scalar(select(User.id).where(User.username == 'manager'))
            db.get(User, target).access_version += 1
        db.commit()
    switch(client, 'receiver', 2)
    assert client.get(API + f'/{grant["id"]}/record').status_code in {403, 409}
    assert client.get(API + f'/{grant["id"]}/files/{data["file_id"]}').status_code in {403, 409}


@pytest.mark.parametrize('values', [
    {'file_ids': []}, {'file_ids': [True]}, {'file_ids': ['1']}, {'file_ids': [1, 1]},
    {'confirmed': False}, {'confirmed': 1}, {'expires_at': '2027-01-01T12:00:00'},
    {'source_case_version': True}, {'include_record': 'yes'},
])
def test_strict_request_and_empty_scope(client, values):
    data = setup(client)
    if values == {'file_ids': []}:
        values['include_record'] = False
    proposal(client, data, status=422, **values)


def test_financial_scope_cannot_elevate_role_and_contact_is_explicit(client):
    data = setup(client)
    proposal(client, data, include_financials=True, status=403)
    grant, _ = proposal(client, data, include_contact=True)
    switch(client, 'manager')
    grant, _ = decide(client, grant)
    switch(client, 'receiver', 2)
    record = client.get(API + f'/{grant["id"]}/record').json()['record']
    assert record['customer']['phone'] == '13900000000'
    assert 'financials' not in record


def test_stale_source_and_duplicate_request_are_not_silent_scope_changes(client):
    data = setup(client)
    grant, body = proposal(client, data)
    again = client.post(API, json=body)
    assert again.status_code == 201 and again.json()['replayed']
    bad = json.loads(json.dumps(body))
    bad['values']['purpose'] = '不是同一个申请范围'
    assert client.post(API, json=bad).status_code == 409
    # Changed customer dependency is rejected even if the original case version did not change.
    with SessionLocal() as db:
        db.get(Customer, data['case']['customer_id']).name = '后来纠正的名称'
        db.commit()
    switch(client, 'manager')
    decide(client, grant, status=409)
    denied, _ = decide(client, grant, 'reject')
    assert denied['status'] == 'rejected'


def test_source_and_group_scope_refusals(client):
    data, grant, _ = approved(client)
    switch(client, 'outsider', 3)
    assert client.get(API + f'/source/{data["case"]["id"]}').status_code == 404
    decide(client, grant, 'revoke', status=404)
    switch(client, 'admin')
    client.headers['X-Store-ID'] = 'all'
    assert not client.get(API + '/catalog').json()['can_read']
    assert client.get(API).status_code == 409
    assert client.get(API + f'/{grant["id"]}/record').status_code == 409


def test_immutable_tables_and_protected_queries(client):
    data, grant, _ = approved(client)
    with SessionLocal() as db:
        with pytest.raises(HTTPException):
            db.scalar(select(DossierGrant))
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == 'admin'))
        set_scope(db, [1], 1)
        with authority(db, user):
            row = db.scalar(select(DossierGrant).where(DossierGrant.id == grant['id']))
            row.recipient_id = data['peer']
            with pytest.raises(HTTPException):
                db.commit()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == 'admin'))
        set_scope(db, [1], 1)
        with authority(db, user):
            row = db.scalar(select(DossierGrantFile))
            row.file_id += 1
            with pytest.raises(HTTPException):
                db.commit()


def test_audit_failure_returns_no_record_or_bytes(client, monkeypatch):
    from app import dossier_grant_service as service
    data, grant, _ = approved(client)
    switch(client, 'receiver', 2)
    def fail(*args, **kwargs):
        raise HTTPException(503, '合成审计提交失败')
    monkeypatch.setattr(service, '_record_access', fail)
    r = client.get(API + f'/{grant["id"]}/record')
    assert r.status_code == 503 and '合成客户' not in r.text
    f = client.get(API + f'/{grant["id"]}/files/{data["file_id"]}')
    assert f.status_code == 503 and b'Synthetic dossier' not in f.content
