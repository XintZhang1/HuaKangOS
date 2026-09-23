"""Dossier approval cannot bypass the original vehicle-operation role boundary."""
import sqlite3
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.db import SessionLocal, engine
from app.models import Store
from app.tenancy import set_scope
from app import dossier_grant_rules as rules
from app.dossier_grant_integrity import validate as validate_dossier_restore
from app.vehicle_operations_service import role_can_read_case
from tests.test_dossier_grants import API, make_user, proposal, decide, switch
from tests.test_vehicle_operations import (
    API as VEHICLE_API, inventory, destination, create, act, returned_sale,
)
from tests.test_workflow import evidence, seed_car
from tests.test_dossier_grant_restore import copied_database, change_json


def source(client, role, kind='other_out'):
    """Only employee fixtures and an explicitly unlocated historic car are seeded.

    New procurement, physical operations and original files use registered APIs.
    """
    with SessionLocal() as db:
        db.add(Store(id=2, code='DOSSIER-B', name='合成档案接收店'))
        db.flush()
        receiver = make_user(db, 'receiver', role, 2)
        make_user(db, 'peer', role, 2)
        make_user(db, 'source_worker', role, 1)
        db.commit()
    if kind == 'customer_return':
        _, _, row, _ = returned_sale(client)
    elif kind == 'locate':
        row = create(client, kind, seed_car(), destination(client))
    else:
        _, vehicle_id, location = inventory(client)
        if kind == 'other_return':
            original = act(client, create(client, 'other_out', vehicle_id), 'approve')
            original = act(client, original, 'dispatch')
            row = create(client, kind, location=location, original=original['id'])
        else:
            row = create(client, kind, vehicle_id,
                         destination(client) if kind == 'local_move' else None)
    file_id = evidence(client, row)
    case = client.get(f'/api/flow/cases/{row["id"]}')
    assert case.status_code == 200, case.text
    return {'case': case.json(), 'receiver': receiver, 'file_id': file_id}


@pytest.mark.parametrize('role', ['service', 'technician'])
@pytest.mark.parametrize('kind', ['locate', 'local_move', 'other_out', 'other_return'])
def test_native_restricted_subtypes_cannot_be_offered_or_granted(client, role, kind):
    data = source(client, role, kind)
    case_id = data['case']['id']
    switch(client, 'source_worker')
    assert client.get(f'{VEHICLE_API}/orders/{case_id}').status_code == 404
    assert client.get(f'{API}/source/{case_id}?to_store_id=2').status_code == 404
    switch(client, 'admin')
    options = client.get(f'{API}/source/{case_id}?to_store_id=2')
    assert options.status_code == 200, options.text
    assert data['receiver'] not in [r['id'] for r in options.json()['recipients']]
    assert client.get(f'{API}/source/{case_id}', params={
        'to_store_id': 2, 'recipient_id': data['receiver'],
    }).status_code == 403
    # An explicitly selected file is not an alternative route around the subtype.
    for include_record in (True, False):
        proposal(client, data, include_record=include_record, status=403)
    with sqlite3.connect(engine.url.database) as db:
        assert db.execute('SELECT count(*) FROM dossier_grants').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM dossier_receipts').fetchone()[0] == 0


@pytest.mark.parametrize('role', ['service', 'technician'])
@pytest.mark.parametrize('approved', [False, True])
def test_pre_fix_restricted_grants_cannot_approve_or_return_bytes(client, monkeypatch, role, approved):
    data = source(client, role)
    current_rule = rules.role_allows

    def pre_fix_rule(db, candidate_role, case):
        if case.kind == 'vehicle_operations' and candidate_role in {'service', 'technician'}:
            return True
        return current_rule(db, candidate_role, case)

    # Create a pre-fix stored grant through real commands, including independent
    # review. Never mutate its immutable scope or forge a decision row directly.
    with monkeypatch.context() as old:
        old.setattr(rules, 'role_allows', pre_fix_rule)
        grant, _ = proposal(client, data)
        if approved:
            switch(client, 'manager')
            grant, _ = decide(client, grant)
    with sqlite3.connect(engine.url.database) as db:
        before = db.execute('SELECT * FROM dossier_grants WHERE id=?', (grant['id'],)).fetchone()
    switch(client, 'receiver', 2)
    meta = client.get(f'{API}/{grant["id"]}')
    assert meta.status_code == 200, meta.text
    item = meta.json()
    assert item['effective_status'] == ('suspended' if approved else 'pending')
    assert not item['can_read'] and 'preview' not in item and 'files' not in item
    listed = client.get(API).json()['items']
    assert len(listed) == 1 and listed[0]['effective_status'] == item['effective_status']
    for suffix in ('record', 'files', f'files/{data["file_id"]}'):
        response = client.get(f'{API}/{grant["id"]}/{suffix}')
        assert response.status_code == 403, response.text
        assert 'scope_digest' not in response.text
    with sqlite3.connect(engine.url.database) as db:
        assert db.execute('SELECT * FROM dossier_grants WHERE id=?', (grant['id'],)).fetchone() == before
        assert db.execute('SELECT count(*) FROM dossier_accesses').fetchone()[0] == 0
        assert validate_dossier_restore(db)['dossier_grants'] == 1
    switch(client, 'manager')
    if not approved:
        decide(client, grant, status=409)
    ended, _ = decide(client, grant, 'revoke' if approved else 'reject')
    assert ended['status'] == ('revoked' if approved else 'rejected')


@pytest.mark.parametrize('role,kind', [
    ('service', 'customer_return'), ('technician', 'customer_return'),
    ('inventory', 'other_out'), ('finance', 'other_out'),
])
def test_allowed_subtypes_keep_exact_named_cross_store_access(client, role, kind):
    data = source(client, role, kind)
    case_id = data['case']['id']
    switch(client, 'source_worker')
    assert client.get(f'{VEHICLE_API}/orders/{case_id}').status_code == 200
    switch(client, 'admin')
    options = client.get(f'{API}/source/{case_id}?to_store_id=2').json()
    assert data['receiver'] in [r['id'] for r in options['recipients']]
    if role != 'finance':
        proposal(client, data, include_financials=True, status=403)
    grant, body = proposal(client, data, include_financials=role == 'finance')
    replay = client.post(API, json=body)
    assert replay.status_code == 201 and replay.json()['replayed']
    assert replay.json()['grant']['id'] == grant['id']
    original_version = grant['version']
    switch(client, 'manager')
    grant, _ = decide(client, grant)
    decide(client, grant, version=original_version, status=409)
    switch(client, 'receiver', 2)
    record = client.get(f'{API}/{grant["id"]}/record')
    assert record.status_code == 200, record.text
    assert record.json()['record'] == grant['preview']
    assert ('financials' in record.json()['record']) == (role == 'finance')
    if role == 'finance':
        assert record.json()['record']['financials']['cost_cents'] is None
    directory = client.get(f'{API}/{grant["id"]}/files')
    assert directory.status_code == 200, directory.text
    assert [f['id'] for f in directory.json()['files']] == [data['file_id']]
    download = client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}')
    assert download.status_code == 200 and download.content.startswith('测试凭据'.encode())
    assert client.get(f'{VEHICLE_API}/orders/{case_id}').status_code == 404
    assert client.get(f'/api/flow/cases/{case_id}').status_code == 404
    assert client.get(f'/api/flow/files/{data["file_id"]}').status_code == 404
    switch(client, 'peer', 2)
    assert client.get(f'{API}/{grant["id"]}/record').status_code == 404
    assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code == 404


@pytest.mark.parametrize('role', ['service', 'technician'])
def test_subtype_check_requires_existing_original_store_operation(client, role):
    data = source(client, role, 'customer_return')
    case = SimpleNamespace(id=data['case']['id'], kind='vehicle_operations', store_id=1)
    with SessionLocal() as db:
        set_scope(db, [1], 1)
        assert role_can_read_case(db, role, case)
        assert not role_can_read_case(db, role, SimpleNamespace(
            id=case.id, kind=case.kind, store_id=2))
        assert not role_can_read_case(db, role, SimpleNamespace(
            id=999999999, kind=case.kind, store_id=1))
        set_scope(db, [2], 2)
        assert not role_can_read_case(db, role, case)


def test_unknown_original_cost_is_preserved_by_financial_grant_and_restore(client):
    data = source(client, 'finance')
    grant, _ = proposal(client, data, include_financials=True)
    assert grant['preview']['financials']['cost_cents'] is None
    switch(client, 'manager')
    grant, _ = decide(client, grant)
    switch(client, 'receiver', 2)
    response = client.get(f'{API}/{grant["id"]}/record')
    assert response.status_code == 200, response.text
    record = response.json()['record']
    assert record['financials'] == {
        'amount_cents': 0, 'paid_cents': 0, 'cost_cents': None,
        'basis': '批准前原单记账快照，不是实际资金划付',
    }
    with copied_database() as restored:
        assert validate_dossier_restore(restored)['dossier_accesses'] == 1
        # Replacing unknown with zero is a change to the frozen original fact.
        change_json(restored, 'dossier_grants', 'record_snapshot',
                    lambda value: value['financials'].update(cost_cents=0))
        with pytest.raises(ValueError, match='摘要不一致'):
            validate_dossier_restore(restored)
    for invalid in (False, True, '0', 0.0, [], {}):
        malformed = deepcopy(record)
        malformed['financials']['cost_cents'] = invalid
        with pytest.raises(ValueError, match='整数分'):
            rules.validate_record(malformed, True, False, True)
    # Only cost is nullable; missing actual amount values are still invalid.
    for field in ('amount_cents', 'paid_cents'):
        malformed = deepcopy(record)
        malformed['financials'][field] = None
        with pytest.raises(ValueError, match='整数分'):
            rules.validate_record(malformed, True, False, True)
