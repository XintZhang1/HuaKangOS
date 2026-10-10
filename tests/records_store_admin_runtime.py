"""Persisted Runtime identity boundaries; run from the external source mirror.

These use real synthetic database rows, including an otherwise fully matching
assistant session. No HTTP service, provider or background worker is started.
"""
from pathlib import Path
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def identity_database(tmp_path):
    source = Path(__file__).resolve().parents[1]
    assert not tmp_path.resolve().is_relative_to(source), 'Keep synthetic data outside the source tree'
    from app.business_assistant_models import AssistantSession
    from app.models import Store, User, UserStore
    engine = create_engine('sqlite:///' + str(tmp_path / 'synthetic-runtime-identity.db'))
    for model in (Store, User, UserStore, AssistantSession):
        model.__table__.create(engine)
    yield engine
    engine.dispose()


def persisted_identity(engine, account_role, membership_role, effective_role):
    from app.business_assistant_models import AssistantSession
    from app.models import Store, User, UserStore
    with Session(engine) as db:
        db.add(Store(id=1, code='SYNTHETIC', name='Synthetic Store', active=True))
        db.add(User(id=1, username='synthetic-runtime-user', display_name='Synthetic User',
            password_hash='unused-synthetic-hash', role=account_role, active=True,
            can_group_summary=False, access_version=7, must_change_password=False))
        db.flush()
        db.add(UserStore(user_id=1, store_id=1, role=membership_role))
        db.add(AssistantSession(id='synthetic-session', owner_id=1, store_id=1,
            owner_role=effective_role, access_version=7, title='Synthetic Session'))
        db.commit()


@pytest.mark.parametrize('account_role,membership_role,effective_role', [
    ('store_admin', 'store_admin', 'store_admin'),
    ('store_admin', 'sales', 'sales'),
    ('sales', 'store_admin', 'store_admin'),
])
def test_runtime_rejects_store_admin_even_with_matching_persisted_identity(
        identity_database, account_role, membership_role, effective_role):
    from app.assistant_runtime_principal import _identity
    from app.business_assistant_models import AssistantSession
    from app.models import User
    from app.tenancy import role_for_store
    persisted_identity(identity_database, account_role, membership_role, effective_role)
    with Session(identity_database) as reader:
        account = reader.get(User, 1)
        thread = reader.scalar(select(AssistantSession).where(AssistantSession.id == 'synthetic-session'))
        assert account.active and not account.must_change_password
        assert role_for_store(reader, account, 1) == thread.owner_role == effective_role
        assert account.access_version == thread.access_version == 7
        with pytest.raises(HTTPException) as denied:
            _identity(reader, 1, 1, effective_role, 7, thread.id)
        assert denied.value.status_code == 403


@pytest.mark.parametrize('account_role,membership_role,effective_role', [
    ('sales', 'sales', 'sales'),
    ('sales', None, 'sales'),
    ('sales', 'manager', 'manager'),
    ('admin', 'sales', 'admin'),
])
def test_runtime_preserves_existing_account_and_membership_rules(
        identity_database, account_role, membership_role, effective_role):
    from app.assistant_runtime_principal import _identity
    persisted_identity(identity_database, account_role, membership_role, effective_role)
    with Session(identity_database) as reader:
        account = _identity(reader, 1, 1, effective_role, 7, 'synthetic-session')
        assert account.id == 1
        assert account.role == account_role


def test_role_migration_preserves_existing_users_and_memberships(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import MetaData
    from sqlalchemy.exc import IntegrityError
    source = Path(__file__).resolve().parents[1]
    assert not tmp_path.resolve().is_relative_to(source), 'Keep synthetic data outside the source tree'
    database = tmp_path / 'synthetic-store-admin-migration.db'
    cfg = Config(str(source / 'alembic.ini'))
    cfg.attributes['url_override'] = 'sqlite:///' + str(database)
    command.upgrade(cfg, 'h60r_record_deputy_approval')
    engine = create_engine('sqlite:///' + str(database))
    metadata = MetaData()
    metadata.reflect(engine, only=['stores', 'users', 'user_stores'])
    tables = metadata.tables
    now = datetime(2026, 1, 1)
    with engine.begin() as db:
        for ident in (1, 2):
            db.execute(tables['stores'].insert(), dict(id=ident, code=f'SYNTHETIC-{ident}',
                name=f'Synthetic Store {ident}', active=ident == 1, created_at=now))
        for ident, role in enumerate(('admin', 'sales', 'manager', 'clerk', 'finance',
                'general_manager', 'chairman', 'group_deputy_manager'), start=1):
            db.execute(tables['users'].insert(), dict(id=ident, username=f'synthetic-{role}',
                display_name=f'Synthetic {role}', role=role, password_hash='unused-synthetic-hash',
                active=ident != 5, must_change_password=ident % 2 == 0, access_version=1,
                can_group_summary=role in {'admin', 'general_manager'}, created_at=now))
            if role != 'admin':
                db.execute(tables['user_stores'].insert(), dict(user_id=ident, store_id=1,
                    role=None if ident % 2 == 0 else role))
        db.execute(tables['user_stores'].insert(), dict(user_id=2, store_id=2, role='manager'))
    with engine.connect() as db:
        original = {name: list(db.execute(select(table).order_by(*table.primary_key)).mappings())
                    for name, table in tables.items()}
    engine.dispose()
    command.upgrade(cfg, 'h61s_store_administration')
    engine = create_engine('sqlite:///' + str(database))
    try:
        with engine.connect() as db:
            for name, table in tables.items():
                assert list(db.execute(select(table).order_by(*table.primary_key)).mappings()) == original[name]
            assert db.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        account = dict(original['users'][0], id=20, username='synthetic-store-admin',
            role='store_admin', can_group_summary=False)
        with engine.begin() as db:
            db.execute(tables['users'].insert(), account)
            db.execute(tables['user_stores'].insert(), dict(user_id=20, store_id=1, role='store_admin'))
            for original_account in original['users']:
                ident = original_account['id'] + 100
                db.execute(tables['users'].insert(), dict(original_account, id=ident,
                    username=original_account['username'] + '-after'))
                if original_account['role'] != 'admin':
                    db.execute(tables['user_stores'].insert(), dict(user_id=ident, store_id=1,
                        role=original_account['role']))
        with pytest.raises(IntegrityError), engine.begin() as db:
            db.execute(tables['users'].insert(), dict(account, id=21,
                username='synthetic-invalid-summary', can_group_summary=True))
    finally:
        engine.dispose()
