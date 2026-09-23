"""Real registered routes and independent SQLite connections; no real payments."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from dataclasses import replace
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text, event
from app.main import app
from app.db import SessionLocal, engine
from app.models import User
from app.flow_models import Case
from app.dossier_grant_models import DossierReceipt
from app import dossier_grant_service as service, file_security, private_files as storage
from tests.test_dossier_grants import API, approved, setup, proposal, decide, switch
from tests.test_file_security import scan, scanner
from tests.test_private_files import private, reference
from tests.test_user_access import listed, body as access_body


def test_current_scan_policy_and_later_risk_block_granted_file(client, monkeypatch):
    data, grant, _ = approved(client)
    scanner(monkeypatch, file_security.ScanResult('infected','clamav','malware_detected','ClamAV-synthetic'))
    switch(client, 'manager')
    assert not scan(client, data['file_id'])['security']['can_use']
    switch(client, 'receiver', 2)
    r=client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}')
    assert r.status_code == 409 and '附件不可使用' in r.text
    assert b'Synthetic dossier only' not in r.content
    # A weaker later structure-only policy must not undo the recorded risk.
    monkeypatch.setattr(file_security,'settings',replace(file_security.settings,file_scan_mode='structure_only'))
    switch(client,'manager');scan(client,data['file_id'])
    switch(client,'receiver',2)
    assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code == 409


def test_private_object_uses_original_store_and_fails_without_original_bytes(client, private):
    data, grant, _ = approved(client)
    obj=reference({'id':data['file_id']})
    switch(client,'receiver',2)
    r=client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}')
    assert r.status_code == 200 and r.content == b'Synthetic dossier only'
    meta=client.get(f'{API}/{grant["id"]}/record')
    assert str(private) not in meta.text and obj.object_key not in meta.text
    path=storage.object_path(private,obj.object_key,1);path.unlink()
    assert client.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code == 409
    assert client.get(f'/api/flow/files/{data["file_id"]}').status_code == 404


def test_financial_source_preview_and_counts_do_not_leak_to_case_owner(client):
    data=setup(client)
    switch(client,'admin')
    with SessionLocal() as db:
        receiver=db.scalar(select(User).where(User.id==data['receiver']))
        receiver.role='finance';db.commit()
    grant,_=proposal(client,data,include_financials=True)
    switch(client,'sales')
    assert client.get(f'/api/flow/cases/{data["case"]["id"]}').status_code == 200
    assert client.get(f'{API}/{grant["id"]}').status_code == 404
    for box in ['sent']:
        result=client.get(API,params={'box':box}).json()
        assert result['items']==[] and result['total']==0


def test_account_disable_reenable_via_real_api_does_not_reactivate_old_grant(client):
    data,grant,_=approved(client)
    switch(client,'admin')
    receiver=listed(client,'receiver')
    r=client.put('/api/users/'+str(receiver['id']),json=access_body(receiver,active=False))
    assert r.status_code==200,r.text
    current=listed(client,'receiver')
    r=client.put('/api/users/'+str(receiver['id']),json=access_body(current,active=True))
    assert r.status_code==200,r.text
    switch(client,'receiver',2)
    assert client.get(f'{API}/{grant["id"]}/record').status_code==409
    meta=client.get(f'{API}/{grant["id"]}').json()
    assert meta['effective_status']=='suspended' and not meta['can_read']
    assert 'files' not in meta and 'preview' not in meta


def test_source_assignment_changes_stop_future_reads_and_hide_source_listing(client):
    data,grant,_=approved(client)
    with engine.begin() as conn:
        manager=conn.execute(text("SELECT id FROM users WHERE username='manager'")).scalar()
        conn.execute(text('UPDATE flow_cases SET owner_id=:owner, created_by=:owner, version=version+1 WHERE id=:id'),{'owner':manager,'id':data['case']['id']})
    switch(client,'receiver',2)
    assert client.get(f'{API}/{grant["id"]}/record').status_code==403
    switch(client,'sales')
    result=client.get(API,params={'box':'sent'}).json()
    assert result['total']==0 and result['items']==[]


@pytest.mark.parametrize('action',['reject','cancel'])
def test_final_pending_decisions_are_not_reopenable(client,action):
    data=setup(client);grant,_=proposal(client,data)
    switch(client,'manager' if action=='reject' else 'sales')
    current,_=decide(client,grant,action)
    assert current['status']=={'reject':'rejected','cancel':'cancelled'}[action]
    switch(client,'manager')
    decide(client,current,'approve',status=409)
    switch(client,'receiver',2)
    assert client.get(f'{API}/{grant["id"]}/record').status_code==403


def test_competing_independent_decisions_have_one_winner(client):
    data=setup(client);grant,_=proposal(client,data)
    switch(client,'manager')
    with TestClient(app) as other:
        switch(other,'admin')
        # Stop before the FIRST write; stopping at the later version UPDATE
        # would hold SQLite's writer lock and prevent the peer reaching it.
        barrier=Barrier(2)
        def pause(conn,cursor,statement,parameters,context,executemany):
            if statement.startswith('INSERT INTO dossier_decisions'):
                barrier.wait(timeout=20)
        event.listen(engine,'before_cursor_execute',pause)
        try:
            def call(c,action):
                return c.post(f'{API}/{grant["id"]}/actions/{action}',json={'request_id':uuid.uuid4().hex,
                    'version':grant['version'],'values':{'reason':'两位不同主管同时核对同一待复核原版本','confirmed':True}})
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(call,client,'approve'),pool.submit(call,other,'reject')]
                results=[f.result(timeout=40) for f in futures]
        finally:
            event.remove(engine,'before_cursor_execute',pause)
    assert sorted(r.status_code for r in results)==[200,409],[(r.status_code,r.text) for r in results]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(DossierReceipt))==2


def test_revocation_committed_before_read_audit_prevents_return(client,monkeypatch):
    data,grant,_=approved(client)
    ready,release=Event(),Event()
    original=service._record_access
    def paused(*args,**kwargs):
        ready.set()
        assert release.wait(30),'Synthetic reader was not released'
        return original(*args,**kwargs)
    monkeypatch.setattr(service,'_record_access',paused)
    with TestClient(app) as reader:
        switch(reader,'receiver',2)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(reader.get,f'{API}/{grant["id"]}/files/{data["file_id"]}')
            try:
                assert ready.wait(30),'Synthetic reader did not reach pre-audit gate'
                switch(client,'manager');decide(client,grant,'revoke')
            finally:
                release.set()
            response=future.result(timeout=30)
        assert response.status_code==409 and b'Synthetic dossier only' not in response.content
        assert reader.get(f'{API}/{grant["id"]}/files/{data["file_id"]}').status_code==403


def test_no_csrf_summary_scope_or_foreign_store_action_bypass(client):
    data=setup(client);grant,raw=proposal(client,data)
    token=client.headers.pop('X-CSRF-Token')
    assert client.post(API,json={**raw,'request_id':uuid.uuid4().hex}).status_code==403
    client.headers['X-CSRF-Token']=token
    switch(client,'admin');client.headers['X-Store-ID']='all'
    assert client.post(f'{API}/{grant["id"]}/actions/approve',json={'request_id':uuid.uuid4().hex,'version':1,'values':{'reason':'不可以从集团汇总批准','confirmed':True}}).status_code==409
    switch(client,'manager2',2)
    decide(client,grant,'approve',status=404)
