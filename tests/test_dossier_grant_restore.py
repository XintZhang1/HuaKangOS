"""Offline restore accepts historical changes but refuses scope/receipt drift."""
import json
from contextlib import contextmanager
import sqlite3

import pytest
from sqlalchemy import select, text
from app.db import engine, SessionLocal
from app.models import User
from app.dossier_grant_integrity import validate, TABLES
from tests.test_dossier_grants import API, approved, setup, proposal, decide, switch


@contextmanager
def copied_database():
    conn = sqlite3.connect(':memory:')
    source = sqlite3.connect(engine.url.database)
    try:
        source.backup(conn)
        yield conn
    finally:
        source.close()
        conn.close()


def one(conn, table):
    c = conn.execute('SELECT * FROM ' + table + ' LIMIT 1')
    return dict(zip([d[0] for d in c.description], c.fetchone()))


def change_json(conn, table, key, mutate):
    row = one(conn, table)
    value = json.loads(row[key])
    mutate(value)
    conn.execute(f'UPDATE {table} SET {key}=? WHERE id=?', (json.dumps(value), row['id']))


def test_independent_restore_of_proposal_approved_reads_and_revocation(client):
    data = setup(client)
    grant, _ = proposal(client, data)
    with copied_database() as conn:
        assert validate(conn) == {'dossier_grants': 1, 'dossier_files': 1, 'dossier_decisions': 0, 'dossier_accesses': 0}
    switch(client, 'manager')
    grant, _ = decide(client, grant)
    switch(client, 'receiver', 2)
    for suffix in ['/record', '/files', f'/files/{data["file_id"]}']:
        r = client.get(f'{API}/{grant["id"]}' + suffix)
        assert r.status_code == 200, r.text
    with copied_database() as conn:
        assert validate(conn)['dossier_accesses'] == 3
    switch(client, 'manager')
    decide(client, grant, 'revoke')
    with copied_database() as conn:
        assert validate(conn)['dossier_decisions'] == 2


def test_later_legitimate_source_and_permission_changes_do_not_invalidate_history(client):
    data, grant, _ = approved(client)
    switch(client, 'receiver', 2)
    assert client.get(f'{API}/{grant["id"]}/record').status_code == 200
    # Later mutations of editable source fields need not equal a frozen snapshot.
    # Raw updates here simulate historical changes, not a production editing path.
    with engine.begin() as conn:
        conn.execute(text('UPDATE flow_cases SET title=:t, version=version+1 WHERE id=:id'), {'t': '后来合法改名', 'id': data['case']['id']})
        conn.execute(text('UPDATE users SET access_version=access_version+1, active=0 WHERE id=:id'), {'id': data['receiver']})
    with copied_database() as conn:
        assert validate(conn)['dossier_grants'] == 1


def test_file_only_directory_is_not_a_record_read(client):
    data, grant, _ = approved(client, include_record=False)
    switch(client, 'receiver', 2)
    assert client.get(f'{API}/{grant["id"]}/files').status_code == 200
    with copied_database() as conn:
        assert conn.execute('SELECT action FROM dossier_accesses').fetchone()[0] == 'directory'
        assert validate(conn)['dossier_accesses'] == 1
        conn.execute("UPDATE dossier_accesses SET action='record'")
        with pytest.raises(ValueError):
            validate(conn)


@pytest.mark.parametrize('mutation', [
    'extra_source_field', 'hidden_customer_phone', 'nested_event_detail', 'scope_digest',
    'file_category', 'file_id_only', 'case_id', 'source_store', 'recipient', 'source_version',
    'missing_receipt', 'receipt_payload', 'receipt_digest', 'independent_reviewer',
    'missing_decision', 'decision_scope', 'decision_version', 'access_user', 'access_file',
    'access_time', 'access_role', 'scope_financial', 'source_event_label', 'scope_expiry',
])
def test_restore_refuses_specific_scope_or_evidence_tampering(client, mutation):
    data, grant, _ = approved(client)
    switch(client, 'receiver', 2)
    assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code == 200
    with copied_database() as conn:
        assert validate(conn)['dossier_grants'] == 1
        if mutation == 'extra_source_field':
            change_json(conn, 'dossier_grants', 'record_snapshot', lambda x: x.update(raw_case_data={'bank': 'leak'}))
        elif mutation == 'hidden_customer_phone':
            change_json(conn, 'dossier_grants', 'record_snapshot', lambda x: x['customer'].update(phone='13900000001'))
        elif mutation == 'nested_event_detail':
            change_json(conn, 'dossier_grants', 'record_snapshot', lambda x: x['events'][0].update(detail={'private': 'leak'}))
        elif mutation == 'scope_digest':
            conn.execute("UPDATE dossier_grants SET scope_digest='fake'")
        elif mutation == 'file_category':
            change_json(conn, 'dossier_grant_files', 'metadata_snapshot', lambda x: x.update(category='business'))
        elif mutation == 'file_id_only':
            change_json(conn, 'dossier_grant_files', 'metadata_snapshot', lambda x: x.update(id=123456))
        elif mutation == 'case_id':
            conn.execute('UPDATE dossier_grants SET source_case_id=123456')
        elif mutation == 'source_store':
            conn.execute('UPDATE dossier_grants SET from_store_id=3')
        elif mutation == 'recipient':
            conn.execute('UPDATE dossier_grants SET recipient_id=?', (data['peer'],))
        elif mutation == 'source_version':
            conn.execute('UPDATE dossier_grants SET source_case_version=99999')
        elif mutation == 'missing_receipt':
            conn.execute("DELETE FROM dossier_receipts WHERE action='approve'")
        elif mutation == 'receipt_payload':
            change_json(conn, 'dossier_receipts', 'request_data', lambda x: x.update(confirmed=False))
        elif mutation == 'receipt_digest':
            conn.execute("UPDATE dossier_receipts SET digest='fake'")
        elif mutation == 'independent_reviewer':
            conn.execute('UPDATE dossier_decisions SET actor_id=?', (data['owner'],))
        elif mutation == 'missing_decision':
            conn.execute('DELETE FROM dossier_decisions')
        elif mutation == 'decision_scope':
            conn.execute("UPDATE dossier_decisions SET scope_digest='fake'")
        elif mutation == 'decision_version':
            conn.execute('UPDATE dossier_decisions SET previous_version=10')
        elif mutation == 'access_user':
            conn.execute('UPDATE dossier_accesses SET actor_id=?', (data['peer'],))
        elif mutation == 'access_file':
            conn.execute('UPDATE dossier_accesses SET file_id=999999')
        elif mutation == 'access_time':
            conn.execute("UPDATE dossier_accesses SET occurred_at='2000-01-01 00:00:00'")
        elif mutation == 'access_role':
            conn.execute("UPDATE dossier_accesses SET actor_role='admin'")
        elif mutation == 'scope_financial':
            conn.execute('UPDATE dossier_grants SET include_financials=1')
        elif mutation == 'source_event_label':
            conn.execute("UPDATE flow_events SET label='后来伪造的说明'")
        elif mutation == 'scope_expiry':
            conn.execute("UPDATE dossier_grants SET expires_at='2099-01-01 00:00:00'")
        with pytest.raises(ValueError):
            validate(conn)


def test_legacy_absent_domain_and_partial_domain_are_distinguished():
    with sqlite3.connect(':memory:') as conn:
        assert validate(conn) == {'dossier_grants': 0, 'dossier_files': 0, 'dossier_decisions': 0, 'dossier_accesses': 0}
        conn.execute('CREATE TABLE dossier_grants (id INTEGER)')
        with pytest.raises(ValueError, match='一部分'):
            validate(conn)


def test_empty_current_domain_validates_and_is_wired_to_complete_backup(client):
    from app.backup_integrity import validate_sqlite
    with copied_database() as conn:
        assert validate(conn)['dossier_grants'] == 0
        result = validate_sqlite(conn)
        assert result['dossier_grants'] == 0
