"""Synthetic store-account receipt and wake-source regression checks.

Run in the same external source mirror as the feedback suites. These tests do
not start a server, execute a worker, call a model, or read any deployment data.
"""
from copy import deepcopy
from dataclasses import replace
import sqlite3
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    from app import config, main
    from app import assistant_runtime_access_signals as signals
    from app.db import Base, make_engine
    from app.models import Store, User, UserStore
    from app.tenancy import RequestPrincipal, set_scope
    cfg = replace(config.settings, assistant_runtime_enabled=True)
    monkeypatch.setattr(config, 'settings', cfg)
    monkeypatch.setattr(signals, 'settings', cfg)
    monkeypatch.setattr(main, 'settings', cfg)
    path = tmp_path / 'synthetic-store-accounts.db'
    engine = make_engine('sqlite:///' + str(path))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([Store(id=1, code='SYNTH-A', name='Synthetic A'),
                    Store(id=2, code='SYNTH-B', name='Synthetic B')])
        db.flush()
        for ident, role in ((1, 'store_admin'), (2, 'sales'), (3, 'admin')):
            db.add(User(id=ident, username='synthetic-' + role, display_name='Synthetic ' + role,
                        role=role, active=True, must_change_password=False,
                        password_hash='unused-synthetic-hash', can_group_summary=False))
        db.flush()
        db.add_all([UserStore(user_id=1, store_id=1, role='store_admin'),
                    UserStore(user_id=2, store_id=1, role='sales')])
        db.commit()
        set_scope(db, [1], 1)
        actor = RequestPrincipal(db.get(User, 1), 'store_admin', _active_store_id=1, _aggregate_scope=False)
        yield db, actor, path
    engine.dispose()


def change(db, actor):
    from app.main import account_info, assign_stores
    from app.schemas import UserUpdate
    from app.user_access_service import change_access
    body = UserUpdate(request_id='synthetic_' + uuid.uuid4().hex, access_version=1,
        role='clerk', display_name='Synthetic local employee', active=True,
        store_ids=[1], store_roles=[{'store_id': 1, 'role': 'clerk'}], can_group_summary=False)
    result = change_access(db, actor, 2, body, account_info, assign_stores)
    return body, result


def wakes(db):
    from app.assistant_runtime_models import WakeEvent
    from app.services import plain
    return [plain(row) for row in db.scalars(select(WakeEvent).order_by(WakeEvent.id))]


def test_local_access_receipt_integrity_replay_and_current_scope(accounts):
    from app.main import account_info, assign_stores
    from app.models import AuditLog, UserStore
    from app.user_access_service import change_access
    from app.user_access_integrity import validate
    from app.assistant_runtime_outbox import _access_source_facts
    db, actor, path = accounts
    body, result = change(db, actor)
    assert result['store_ids'] == [1] and result['account_role'] == 'clerk'
    assert change_access(db, actor, 2, body, account_info, assign_stores) == result
    audit = db.scalar(select(AuditLog).where(AuditLog.action == 'update_user'))
    assert audit.entity_type == 'store_account' and audit.store_id == 1
    assert audit.after_data == result
    with sqlite3.connect(path) as connection:
        assert validate(connection) == {'user_access_receipts': 1}
    events = wakes(db)
    assert len(events) == 1 and events[0]['store_id'] == 1
    assert _access_source_facts(db, events[0])['owner_id'] == 2
    forged = dict(events[0], store_id=2, signal_key=events[0]['signal_key'].replace(':store:1', ':store:2'))
    with pytest.raises(HTTPException) as error:
        _access_source_facts(db, forged)
    assert error.value.status_code == 422
    # A later global administrator may share this ordinary account with another
    # store. The former local administrator must not recover the old receipt.
    db.add(UserStore(user_id=2, store_id=2, role='sales'))
    db.commit()
    with pytest.raises(HTTPException) as error:
        change_access(db, actor, 2, body, account_info, assign_stores)
    assert error.value.status_code == 404


@pytest.mark.parametrize('corruption', ['wrong_store', 'wrong_family', 'foreign_membership', 'higher_role'])
def test_corrupt_local_receipt_scope_is_rejected(accounts, corruption):
    from app.models import AuditLog
    from app.user_access_integrity import receipt_scope, receipt_digest
    from app.user_access_models import UserAccessReceipt
    db, actor, _ = accounts
    change(db, actor)
    receipt = db.scalar(select(UserAccessReceipt))
    audit = db.get(AuditLog, receipt.audit_id)
    scope = {'entity_type': audit.entity_type, 'store_id': audit.store_id}
    result, before = deepcopy(receipt.result), deepcopy(audit.before_data)
    if corruption == 'wrong_store': scope['store_id'] = 2
    elif corruption == 'wrong_family': scope.update(entity_type='users', store_id=0)
    elif corruption == 'foreign_membership': result['store_roles'].append({'store_id': 2, 'role': 'sales'})
    elif corruption == 'higher_role': result['account_role'] = 'admin'
    try:
        store_id = receipt_scope(scope, receipt.request_data, result, before)
    except ValueError:
        pass
    else:
        # Retagging a local receipt as a global one cannot preserve its digest.
        assert receipt.digest != receipt_digest(receipt.target_id, receipt.request_data, store_id)


def test_local_reset_wake_accepts_only_its_original_store(accounts):
    from app.main import reset_password
    from app.schemas import ResetPasswordInput
    from app.assistant_runtime_outbox import _access_source_facts
    from app.models import AuditLog, User
    db, actor, _ = accounts
    result = reset_password(2, ResetPasswordInput(password='synthetic-' + uuid.uuid4().hex,
        reason='Synthetic local recovery'), db, actor)
    assert result == {'ok': True} and db.get(User, 2).must_change_password is True
    audit = db.scalar(select(AuditLog).where(AuditLog.action == 'reset_password'))
    assert audit.entity_type == 'store_account' and audit.store_id == 1
    assert audit.after_data['store_ids'] == [1]
    events = wakes(db)
    assert len(events) == 1 and _access_source_facts(db, events[0])['owner_id'] == 2
    forged = dict(events[0], store_id=2, signal_key=events[0]['signal_key'].replace(':store:1', ':store:2'))
    with pytest.raises(HTTPException) as error:
        _access_source_facts(db, forged)
    assert error.value.status_code == 422
