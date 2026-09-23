"""Deferred real-PostgreSQL dossier acceptance in an OWNED synthetic cluster.

Owner: python tests/postgres_dossier_grants.py --pg-bin <trusted PostgreSQL bin>
Optional: --prepare-only validates ONLY synthetic SQLite preparation, not PG.
Never accepts a company's existing URL/database, and starts nothing on import.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def synthetic_source(work):
    # Bind the isolated fixture BEFORE importing any application setting or DB.
    from tests import conftest as cf
    from fastapi.testclient import TestClient
    from tests.test_dossier_grant_native import native_source
    from tests.test_dossier_grants import proposal, decide, switch, API
    from app.db import engine
    from app.backup_integrity import validate_sqlite
    import sqlite3
    fixture = cf.isolated_database.__wrapped__()
    next(fixture)
    try:
        with TestClient(cf.app) as client:
            cf.login(client)
            data = native_source(client)
            grant, body = proposal(client, data)
            switch(client, 'manager'); grant, _ = decide(client, grant)
            switch(client, 'receiver', 2)
            assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code == 200
            switch(client, 'sales')
            pending, _ = proposal(client, data)
            switch(client, 'admin')
            from tests.test_master_completion import setup_brand, dict_create
            brand, profile, _ = setup_brand(client)
            dictionary = dict_create(client,'repair',{'name':'合成PG维修字典','detail':'原资料表，不改流程'})
            with sqlite3.connect(engine.url.database) as db:
                checked = validate_sqlite(db)
                assert checked['dossier_grants'] == 2 and checked['dossier_decisions'] == 1
            return str(engine.url), {
                'grant_id': grant['id'], 'pending_id': pending['id'], 'pending_version': pending['version'],
                'source_case_id': data['case']['id'], 'file_id': data['file_id'],
                'brand_id':brand['id'],'profile_id':profile['id'],'dictionary_id':dictionary['id'],
                'other_file_id': data['other_file_id'], 'original_request': body,
                'password': cf.PASSWORD, 'synthetic_only': True,
                'source_checks': checked,
            }
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass


def run_native_target(state_file):
    """Private subprocess entry for the generated cluster; never import conftest."""
    from sqlalchemy.engine import make_url
    state = json.loads(Path(state_file).read_text(encoding='utf-8'))
    url = make_url(os.environ['DATABASE_URL'])
    if (not state.get('synthetic_only') or not state.get('worker_nonce')
            or os.environ.get('HUAKANGOS_OWNED_ACCEPTANCE') != state['worker_nonce']
            or url.host != '127.0.0.1' or url.database != 'hk_transfer'
            or not (url.username or '').startswith('hk_') or url.get_backend_name() != 'postgresql'):
        raise ValueError('Not the generated synthetic acceptance target')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from sqlalchemy import text
    from app.main import app
    from app.db import engine
    api = '/api/dossier-grants'

    def login(client, name, store):
        response = client.post('/api/auth/login', json={'username': name, 'password': state['password']},
                               headers={'X-App-Request': '1'})
        assert response.status_code == 200, response.text
        client.headers['X-CSRF-Token'] = client.cookies['dealer_csrf']
        client.headers['X-Store-ID'] = str(store)

    def get(client, path, status=200):
        response = client.get(path)
        assert response.status_code == status, response.text
        return response

    with TestClient(app) as receiver, TestClient(app) as manager, TestClient(app) as independent:
        login(receiver, 'receiver', 2); login(manager, 'manager', 1); login(independent, 'independent', 1)
        brands=get(manager,'/api/masters/material_brands').json()['items']
        assert any(b['id']==state['brand_id'] for b in brands)
        profile=get(manager,'/api/masters/item_profiles').json()['items'][0]
        assert profile['id']==state['profile_id'] and profile['brand_id']==state['brand_id']
        assert get(manager,'/api/dictionaries/repair').json()['items'][0]['id']==state['dictionary_id']
        get(receiver,'/api/masters/material_brands',403)  # Sales cannot view stock masters.
        assert get(manager,'/api/parameters/catalog').json()['deployment_read_only']
        row = get(receiver, f'{api}/{state["grant_id"]}/record').json()
        assert row['record']['case']['id'] == state['source_case_id']
        assert 'financials' not in row['record'] and 'phone' not in row['record']['customer']
        file_url = f'{api}/{state["grant_id"]}/files/{state["file_id"]}'
        assert get(receiver, file_url).content == b'Synthetic exact original file'
        get(receiver, f'{api}/{state["grant_id"]}/files/{state["other_file_id"]}', 404)
        get(receiver, f'/api/flow/cases/{state["source_case_id"]}', 404)
        get(receiver, f'/api/flow/files/{state["file_id"]}', 404)
        with TestClient(app) as peer:
            login(peer, 'peer', 2); get(peer, file_url, 404)
        barrier = Barrier(2)

        def decide(args):
            client, action = args
            barrier.wait(timeout=15)
            return client.post(f'{api}/{state["pending_id"]}/actions/{action}', json={
                'request_id': uuid.uuid4().hex, 'version': state['pending_version'],
                'values': {'reason': '实际PG两个独立会话竞争同一待复核版本', 'confirmed': True}})

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, ((manager, 'approve'), (independent, 'reject'))))
        assert sorted(r.status_code for r in results) == [200, 409], [(r.status_code, r.text) for r in results]
        current = get(manager, f'{api}/{state["grant_id"]}').json()
        revoke_body = {'request_id': uuid.uuid4().hex, 'version': current['version'],
                       'values': {'reason': '原店决定撤销后不得再返回旧文件', 'confirmed': True}}
        response = manager.post(f'{api}/{current["id"]}/actions/revoke', json=revoke_body)
        assert response.status_code == 200, response.text
        # Revocation is committed in one PG connection before a distinct receiver
        # session tries the old URL. We do not promise remote deletion of copies.
        get(receiver, file_url, 403)
        get(receiver, f'{api}/{current["id"]}/record', 403)
        replay = manager.post(f'{api}/{current["id"]}/actions/revoke', json=revoke_body)
        assert replay.status_code == 200 and replay.json()['replayed']
        with TestClient(app) as sender:
            login(sender, 'sales', 1)
            replay = sender.post(api, json=state['original_request'])
            assert replay.status_code == 201 and replay.json()['grant']['status'] == 'revoked'
        with engine.connect() as db:
            assert db.scalar(text('SELECT count(*) FROM dossier_grants')) == 2
            assert db.scalar(text('SELECT count(*) FROM dossier_decisions')) == 3
            assert db.scalar(text('SELECT count(*) FROM dossier_receipts')) == 5
            assert db.scalar(text('SELECT count(*) FROM dossier_accesses')) == 3
    (Path(state_file).parent / 'native-result.json').write_text(json.dumps({
        'status': 'passed', 'mode': 'actual-generated-postgresql', 'synthetic_only': True,
        'checks': ['material_brand_profile_and_dictionary_roundtrip','parameter_catalog_remains_nonsecret',
                   'registered_API_exact_named_receiver_and_original_bytes',
                   'same_bytes_different_file_id_not_authorized', 'ordinary_cross_store_routes_closed',
                   'two_PG_sessions_one_decision_per_version', 'committed_revocation_blocks_old_URL',
                   'request_replay_does_not_resurrect_grant']}, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--pg-bin', type=Path)
    mode.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='huakangos-dossier-pg-')).resolve()
    if work.is_relative_to(ROOT):
        raise ValueError('Acceptance files must be outside the repository')
    report = {'status': 'running', 'synthetic_only': True,
              'actual_postgresql': False, 'temporary_directory': str(work)}
    print('Acceptance artifacts: ' + str(work), flush=True)
    try:
        source, state = synthetic_source(work)
        report['sqlite_source_prepared'] = True
        if args.prepare_only:
            report.update(status='prepared_only', note='SQLite source only; NOT PostgreSQL acceptance')
            return 0
        from tests.postgres_acceptance import temporary_postgres, run_binary, database_manifest, verify_sequences
        from scripts.migrate_database import transfer
        from app.db import make_engine
        with temporary_postgres(args.pg_bin.resolve(), work) as (exe, env, urls, version):
            report['server_version'] = version
            report['copied_rows'] = transfer(source, urls['hk_transfer'])
            state['worker_nonce'] = uuid.uuid4().hex
            state_file = work / 'owned-synthetic-state.json'
            state_file.write_text(json.dumps(state), encoding='utf-8'); state_file.chmod(0o600)
            child_env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PG')}
            child_env.update(DATABASE_URL=urls['hk_transfer'], APP_ENV='test', FILE_SCAN_MODE='structure_only',
                ALLOW_AI_EXTERNAL='false', DEEPSEEK_API_KEY='', SCHEDULER_ENABLED='false', COOKIE_SECURE='false',
                ALLOWED_HOSTS='testserver,localhost,127.0.0.1', LEGACY_BUSINESS_WRITE='false',
                HUAKANGOS_OWNED_ACCEPTANCE=state['worker_nonce'])
            code = 'from tests.postgres_dossier_grants import run_native_target; import sys; run_native_target(sys.argv[1])'
            with (work / 'native.log').open('wb') as log:
                completed = subprocess.run([sys.executable, '-c', code, str(state_file)], cwd=ROOT, env=child_env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=300,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            state_file.unlink(missing_ok=True)
            if completed.returncode:
                raise RuntimeError('Native PostgreSQL API verification failed; see native.log')
            report['native'] = json.loads((work / 'native-result.json').read_text(encoding='utf-8'))
            target = make_engine(urls['hk_transfer'])
            try:
                expected, files = database_manifest(target)
            finally:
                target.dispose()
            dump = work / 'dossier-original.dump'
            run_binary(exe['pg_dump'], ['-Fc', '-d', 'hk_transfer', '-f', dump], work, env)
            run_binary(exe['pg_restore'], ['--exit-on-error', '-d', 'hk_restored', dump], work, env)
            restored = make_engine(urls['hk_restored'])
            try:
                actual, restored_files = database_manifest(restored)
                assert actual == expected and restored_files == files
                report['restored_tables'] = len(actual)
                report['verified_sequences'] = verify_sequences(restored)
            finally:
                restored.dispose()
            # Full business-origin validation after typed round-trip; the target
            # SQLite is new/empty, not a rewrite of the pre-command source.
            back = work / 'post-pg-restored.sqlite'
            transfer(urls['hk_restored'], 'sqlite:///' + back.as_posix())
            import sqlite3
            from app.backup_integrity import validate_sqlite
            with sqlite3.connect(back) as db:
                checks = validate_sqlite(db)
                assert checks['dossier_grants'] == 2 and checks['dossier_decisions'] == 3
                report['roundtrip_business_checks'] = checks
            report.update(status='passed', actual_postgresql=True)
    except Exception as error:
        report.update(status='failed', failure_type=type(error).__name__)
        (work / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        (work / 'owned-synthetic-state.json').unlink(missing_ok=True)
        (work / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('status', 'actual_postgresql', 'temporary_directory')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
