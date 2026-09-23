"""Original customer business is created and advanced through registered routes."""
import sqlite3
import uuid

from sqlalchemy import select
from app.db import SessionLocal, engine, today
from app.models import Store, User
from app.backup_integrity import validate_sqlite
from tests.test_dossier_grants import API, make_user, proposal, decide, switch
from tests.test_workflow import create, action


def native_source(client):
    """Only fixtures create employees; every business/file fact uses its API."""
    with SessionLocal() as db:
        db.add(Store(id=2, code='SYNTH-B', name='合成授权接收店'))
        db.flush()
        receiver = make_user(db, 'receiver', 'sales', 2)
        make_user(db, 'peer', 'sales', 2)
        make_user(db, 'independent', 'manager', 1)
        owner = db.scalar(select(User.id).where(User.username == 'sales'))
        db.commit()
    switch(client, 'admin')
    row = create(client, 'lead', {'customer_name': '合成跨店原业务客户',
        'customer_phone': '13900000771', 'confirm_new_customer': True,
        'model': '合成车型', 'source': '展厅到店'})
    row = action(client, row, 'assign', {'assignee_id': owner})
    switch(client, 'sales')
    files = []
    for category in ('evidence', 'inspection'):
        response = client.post(f'/api/flow/cases/{row["id"]}/files',
            files={'file': (f'合成逐件原件-{category}.txt', b'Synthetic exact original file', 'text/plain')},
            data={'category': category})
        assert response.status_code == 200, response.text
        files.append(response.json()['id'])
    assert files[0] != files[1]
    row = client.get(f'/api/flow/cases/{row["id"]}').json()
    return {'case': row, 'receiver': receiver, 'owner': owner,
            'file_id': files[0], 'other_file_id': files[1]}


def test_native_lead_advances_without_expanding_approved_snapshot_and_full_restore(client):
    data = native_source(client)
    grant, body = proposal(client, data)
    original = client.get(f'/api/flow/cases/{data["case"]["id"]}').json()
    switch(client, 'manager')
    grant, _ = decide(client, grant)
    switch(client, 'sales')
    after = client.get(f'/api/flow/cases/{data["case"]["id"]}').json()
    assert after == original
    later = action(client, after, 'remind', {'due_date': today().isoformat(), 'result': '此记录发生于授权批准后'})
    assert later['state'] == 'reminder' and later['version'] > original['version']
    switch(client, 'receiver', 2)
    received = client.get(f'{API}/{grant["id"]}/record')
    assert received.status_code == 200, received.text
    assert received.json()['record'] == grant['preview']
    assert '此记录发生于授权批准后' not in received.text
    assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').content == b'Synthetic exact original file'
    assert client.get(f'{API}/{grant["id"]}/files/{data["other_file_id"]}').status_code == 404
    assert client.get(f'/api/flow/cases/{original["id"]}').status_code == 404
    with sqlite3.connect(engine.url.database) as db:
        checked = validate_sqlite(db)
        assert checked['dossier_grants'] == 1 and checked['dossier_accesses'] == 2
    switch(client, 'manager')
    decide(client, grant, 'revoke')
    switch(client, 'receiver', 2)
    assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code == 403
    with sqlite3.connect(engine.url.database) as db:
        assert validate_sqlite(db)['dossier_decisions'] == 2


def test_native_source_options_do_not_offer_self_and_contact_is_independent(client):
    data = native_source(client)
    switch(client, 'admin')
    options = client.get(f'{API}/source/{data["case"]["id"]}?to_store_id=2').json()
    with SessionLocal() as db:
        admin = db.scalar(select(User.id).where(User.username == 'admin'))
    assert admin not in [r['id'] for r in options['recipients']]
    grant, _ = proposal(client, data, include_contact=True, file_ids=[])
    decide(client, grant, status=403)
    switch(client, 'manager'); grant, _ = decide(client, grant)
    switch(client, 'receiver', 2)
    response = client.get(f'{API}/{grant["id"]}/record')
    assert response.status_code == 200, response.text
    record = response.json()['record']
    assert record['customer']['phone'] == '13900000771'
    assert 'financials' not in record and not response.json()['files']
    with sqlite3.connect(engine.url.database) as db:
        assert validate_sqlite(db)['dossier_grants'] == 1
