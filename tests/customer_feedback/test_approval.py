"""Focused persistence checks; run from an external source mirror with synthetic data.

The loopback HTTP suite owns the user paths. These checks cover old-schema data
preservation, pre-upgrade idempotency receipts, and the mapper's lost-update guard.
"""
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import shutil

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from starlette.requests import Request


@pytest.fixture(scope='module')
def upgraded_database(tmp_path_factory):
    root = tmp_path_factory.mktemp('approval-migration')
    source = Path(__file__).resolve().parents[2]
    assert not root.is_relative_to(source), 'Runtime data must remain outside the source tree'
    database = root / 'synthetic.db'
    cfg = Config(str(source / 'alembic.ini'))
    cfg.attributes['url_override'] = 'sqlite:///' + str(database)
    command.upgrade(cfg, 'h59q_record_daily_reports')
    engine = create_engine('sqlite:///' + str(database))
    metadata = MetaData()
    metadata.reflect(engine, only=['stores', 'users', 'user_stores',
        'business_record_contracts', 'business_record_commands'])
    tables = metadata.tables
    now = datetime(2026, 1, 1)
    with engine.begin() as db:
        db.execute(tables['stores'].insert(), {'id': 1, 'code': 'TEST', 'name': 'Synthetic Store',
            'active': True, 'created_at': now})
        for ident, role in ((1, 'sales'), (2, 'manager'), (3, 'general_manager')):
            db.execute(tables['users'].insert(), {'id': ident, 'username': 'synthetic-' + role,
                'display_name': role, 'password_hash': 'unused-synthetic-hash', 'role': role,
                'active': True, 'must_change_password': True, 'created_at': now,
                'access_version': 1, 'can_group_summary': False})
            db.execute(tables['user_stores'].insert(), {'user_id': ident, 'store_id': 1, 'role': role})
        contracts = tables['business_record_contracts']
        common = {'store_id': 1, 'version': 2, 'created_at': now, 'updated_at': now,
            'salesperson_id': 1, 'created_by': 1, 'customer_name': 'Synthetic Customer',
            'customer_phone': '', 'brand': 'Test Brand', 'model': 'Test Model', 'vin': 'TEST0000000000001',
            'contract_date': date(2026, 1, 1), 'sale_price_cents': 12340000,
            'gift_description': '', 'form_data': {}, 'office_status': 'not_started', 'office_revision': 0,
            'office_approval_note': '', 'price_note': '', 'approval_note': '', 'template_version': '',
            'manager_approval_note': ''}
        db.execute(contracts.insert(), dict(common, id=1, number='SYNTHETIC-V29',
            workflow_version='trial-v29', status='manager_approved', manager_approved_by=2,
            manager_approved_at=now))
        db.execute(contracts.insert(), dict(common, id=2, number='SYNTHETIC-LEGACY',
            workflow_version='legacy-v2', status='approved', expected_amount_cents=12340000,
            cost_cents=10000000, profit_cents=2340000, gift_cost_cents=0,
            priced_by=2, approved_by=3, approved_at=now,
            approved_snapshot={'synthetic': 'historical snapshot', 'profit_cents': 2340000}))
        payload = {'action': 'contract:1:manager_approve', 'payload': {'version': 1, 'note': 'Synthetic approval'}}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()
        old_result = {'id': 1, 'version': 2, 'status': 'manager_approved', 'synthetic': 'old immutable receipt'}
        db.execute(tables['business_record_commands'].insert(), {'id': 1, 'store_id': 1,
            'actor_id': 2, 'request_id': 'historical-request-0001', 'digest': digest,
            'result': old_result, 'created_at': now})
    with engine.connect() as db:
        original = {name: [dict(row) for row in db.execute(select(table).order_by(*table.primary_key)).mappings()]
                    for name, table in tables.items()}
    engine.dispose()
    command.upgrade(cfg, 'h60r_record_deputy_approval')
    return database, metadata, original, old_result


@pytest.fixture
def migrated_copy(upgraded_database, tmp_path):
    database, metadata, original, old_result = upgraded_database
    destination = tmp_path / 'synthetic.db'
    shutil.copy2(database, destination)
    engine = create_engine('sqlite:///' + str(destination))
    yield engine, metadata, original, old_result
    engine.dispose()


def test_upgrade_preserves_every_original_column_and_receipt(migrated_copy):
    engine, metadata, original, _ = migrated_copy
    with engine.connect() as db:
        for name, table in metadata.tables.items():
            assert [dict(row) for row in db.execute(select(table).order_by(*table.primary_key)).mappings()] == original[name]
        assert db.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        assert db.exec_driver_sql('SELECT approval_limits, general_manager_approved_by, deputy_approved_by FROM business_record_contracts').all() == [(None, None, None)] * 2
    current = MetaData()
    current.reflect(engine, only=['users', 'user_stores'])
    with engine.begin() as db:
        values = dict(original['users'][0], id=4, username='synthetic-deputy', role='group_deputy_manager')
        db.execute(current.tables['users'].insert(), values)
        db.execute(current.tables['user_stores'].insert(), {'user_id': 4, 'store_id': 1, 'role': 'group_deputy_manager'})


def test_pre_upgrade_manager_request_replays_exact_original_result(migrated_copy):
    from app.business_records import manager_approve_contract
    from app.business_records_schemas import ManagerApproval
    from app.models import User
    from app.business_records_models import RecordCommand, SalesContract
    from app.tenancy import set_scope
    engine, _, _, old_result = migrated_copy
    with Session(engine) as db:
        set_scope(db, [1], 1)
        manager = db.get(User, 2)
        body = ManagerApproval(request_id='historical-request-0001', version=1, note='Synthetic approval')
        result = manager_approve_contract(1, body, Request({'type': 'http', 'method': 'POST'}), db, manager)
        assert result == old_result
        assert db.scalar(select(func.count()).select_from(RecordCommand)) == 1
        assert db.get(SalesContract, 1).version == 2


def test_mapper_cas_rejects_a_stale_contract_write(migrated_copy):
    from app.business_records_models import SalesContract
    engine, _, _, _ = migrated_copy
    # End the initial read transaction but deliberately retain the old object;
    # another independent writer commits first, as after a stale browser read.
    with Session(engine, expire_on_commit=False) as stale, Session(engine) as writer:
        original = stale.get(SalesContract, 1)
        stale.commit()
        newer = writer.get(SalesContract, 1)
        newer.manager_approval_note = 'Synthetic newer review'
        writer.commit()
        original.manager_approval_note = 'Synthetic stale review'
        with pytest.raises(StaleDataError):
            stale.commit()
        stale.rollback()
    with Session(engine) as db:
        persisted = db.get(SalesContract, 1)
        assert persisted.version == 3
        assert persisted.manager_approval_note == 'Synthetic newer review'
