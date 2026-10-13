"""Actual ASGI routes, login, CSRF, persistence and scoped synthetic catalogs."""
from copy import deepcopy
from datetime import date
import hashlib
import os
from pathlib import Path
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

assert os.environ.get('RECORD_PRICING_ISOLATED') == '1', 'Use run_isolated.py; never load app in the repository'

from app import db as database
from app.main import app
from app.models import Store, User, UserStore
from app.business_record_pricing_models import RecordPriceBatch, RecordPricingFile, RecordContractTerms
from app.business_records_models import SalesContract, RecordCustomer
from app.security import hash_password
from synthetic import VEHICLE_ROW, vehicle_xlsx, gift_csv

BASE = '/api/business-records'


def command(**values):
    return {'request_id': uuid.uuid4().hex, **values}


@pytest.fixture(scope='module')
def login_secret():
    password = secrets.token_urlsafe(24)
    return password, hash_password(password)


class Fixture:
    def __init__(self, sessions, password):
        self.sessions, self.password, self.clients = sessions, password, {}

    def client(self, role):
        if role not in self.clients:
            client = TestClient(app, headers={'X-App-Request': '1'})
            response = client.post('/api/auth/login', json={'username': 'synthetic_' + role, 'password': self.password})
            assert response.status_code == 200, response.text
            client.headers['X-CSRF-Token'] = client.cookies['dealer_csrf']
            client.headers['X-Store-ID'] = '2' if role == 'other_manager' else '3' if role == 'third_manager' else '1'
            self.clients[role] = client
        return self.clients[role]

    def call(self, role, method, path, expected=200, **kwargs):
        response = self.client(role).request(method, BASE + path, **kwargs)
        assert response.status_code == expected, response.text
        return response.json()

    def catalog(self, role='manager'):
        return self.call(role, 'GET', '/pricing/catalog')

    def upload(self, role='manager', kind='vehicle', filename='synthetic.xlsx', content=None, expected=201):
        return self.call(role, 'POST', '/pricing/uploads', expected,
            data=command(kind=kind), files={'file': (filename, vehicle_xlsx() if content is None else content)})

    def publish(self, role, kind, uploaded, rows, expected=201, **changes):
        current = self.catalog(role)
        # The preview's display-only source label is omitted by the real form;
        # source_ref remains part of the saved gift provenance.
        rows = [{key: value for key, value in row.items() if key != 'source'} for row in rows]
        body = command(version=current['version'], brand_version=current['brand_version'],
            brand=current['brand'], file_id=uploaded['id'], rows=deepcopy(rows))
        if kind == 'vehicle':
            body['policy_confirmed'] = True
        body.update(changes)
        return self.call(role, 'POST', '/pricing/' + ('gifts' if kind == 'gift' else 'vehicle') + '/import',
            expected, json=body)

    def prepared(self):
        self.call('admin', 'PUT', '/store-profile', json=command(version=0,
            sellers=[{'name': '合成卖方', 'address': '合成地址'}]))
        gifts = self.upload('general_manager', 'gift', 'synthetic.csv', gift_csv())
        preview = self.call('general_manager', 'POST', f'/pricing/uploads/{gifts["id"]}/recognize',
            json=command(version=gifts['version']))
        self.publish('general_manager', 'gift', gifts, preview['rows'])
        configured = [{'price_id': item['id'], 'quantity': 1} for item in self.catalog()['gifts'][:2]]
        vehicle = self.upload()
        self.publish('manager', 'vehicle', vehicle, [{**VEHICLE_ROW,
            'gift_policy': {**VEHICLE_ROW['gift_policy'], 'standard_gifts': configured}}])
        return self.catalog('sales')

    def contract_body(self, catalog, selections):
        return command(customer_name='合成合同客户', customer_phone='', brand='合成品牌', model='合成配置',
            vin='SYNTHETIC-' + uuid.uuid4().hex[:16], salesperson_id=4,
            contract_date=date(2026, 10, 12).isoformat(), sale_price_cents=11000000,
            vehicle_price_id=catalog['vehicles'][0]['id'], gift_items=selections,
            form_data={'seller_name': '合成卖方', 'exterior_color': '白', 'interior_color': '黑', 'deposit': '0'},
            submission_data={'payment_method': '全款'})


@pytest.fixture
def fx(tmp_path, monkeypatch, login_secret):
    assert tmp_path.is_relative_to(Path(os.environ['RECORD_PRICING_RUNTIME']))
    engine = database.make_engine('sqlite:///' + str(tmp_path / 'synthetic.sqlite'))
    database.Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, 'SessionLocal', sessions)
    password, password_hash = login_secret
    with sessions() as db:
        db.add_all([Store(id=i, code='SYNTHETIC-' + str(i), name='合成门店' + str(i),
            brand='合成品牌' if i != 3 else '隔离品牌') for i in (1, 2, 3)])
        db.flush()
        roles = [('admin', 'admin', 1), ('manager', 'manager', 1),
            ('general_manager', 'general_manager', 1), ('sales', 'sales', 1),
            ('sales_peer', 'sales', 1), ('other_manager', 'manager', 2), ('third_manager', 'manager', 3)]
        for ident, (name, role, store) in enumerate(roles, 1):
            db.add(User(id=ident, username='synthetic_' + name, display_name='合成-' + name,
                role=role, password_hash=password_hash, must_change_password=False, active=True))
            db.flush()
            if role != 'admin':
                db.add(UserStore(user_id=ident, store_id=store, role=role))
        db.commit()
    fixture = Fixture(sessions, password)
    yield fixture
    for client in fixture.clients.values():
        client.close()
    engine.dispose()


@pytest.mark.parametrize(('filename', 'content', 'status'), [
    ('empty.xlsx', b'', 413), ('broken.xlsx', b'not an Excel archive', 422),
    ('prices.csv', b'name,price\nsynthetic,1\n', 422),
    ('../prices.xlsx', vehicle_xlsx(), 422), ('huge.xlsx', b'x' * (10 * 1024 * 1024 + 1), 413),
], ids=['empty', 'broken', 'csv-not-xlsx', 'bad-filename', 'too-large'])
def test_invalid_vehicle_upload_is_rejected_without_persistence(fx, filename, content, status):
    fx.upload(filename=filename, content=content, expected=status)
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordPricingFile)) == 0
        assert db.scalar(select(func.count()).select_from(RecordPriceBatch)) == 0


def test_upload_requires_writer_and_csrf(fx):
    fx.upload(role='sales', expected=403)
    client = fx.client('manager')
    client.headers.pop('X-CSRF-Token')
    response = client.post(BASE + '/pricing/uploads', data=command(kind='vehicle'),
        files={'file': ('synthetic.xlsx', vehicle_xlsx())})
    assert response.status_code == 403
    assert '校验' in response.json()['detail']
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordPricingFile)) == 0


def test_vehicle_upload_failed_recognition_and_manual_publication(fx):
    uploaded = fx.upload()
    assert uploaded['sha256'] == hashlib.sha256(vehicle_xlsx()).hexdigest()
    assert uploaded['available'] is True
    assert fx.catalog()['vehicles'] == []
    failure = fx.call('manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize', 503,
        json=command(version=uploaded['version']))
    assert '原件已保存' in failure['detail']
    assert fx.catalog()['vehicles'] == []
    fx.publish('manager', 'vehicle', uploaded, [VEHICLE_ROW], expected=422, policy_confirmed=False)
    assert fx.catalog()['vehicles'] == []
    fx.publish('manager', 'vehicle', uploaded, [VEHICLE_ROW])
    published = fx.catalog()
    row = published['vehicles'][0]
    assert row['control_price_cents'] == 10000000
    assert row['gift_policy']['cost_limit_cents'] == 10000
    assert published['vehicle_batch_id'] is not None
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordPriceBatch)) == 1
        assert db.get(RecordPricingFile, uploaded['id']).content == vehicle_xlsx()


def test_only_uploader_can_publish_and_same_brand_catalog_is_shared(fx):
    uploaded = fx.upload()
    fx.publish('general_manager', 'vehicle', uploaded, [VEHICLE_ROW], expected=403)
    fx.publish('manager', 'vehicle', uploaded, [VEHICLE_ROW])
    home, sibling, other = fx.catalog(), fx.catalog('other_manager'), fx.catalog('third_manager')
    assert home['vehicles'] == sibling['vehicles']
    assert home['vehicle_batch_id'] == sibling['vehicle_batch_id']
    assert other['vehicles'] == [] and other['vehicle_batch_id'] is None
    fx.call('other_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize', 404,
        json=command(version=uploaded['version']))
    fx.call('sales', 'GET', '/pricing/catalog', 403, headers={'X-Store-ID': '2'})


def test_gift_csv_preview_actual_import_and_price_projection(fx):
    uploaded = fx.upload('general_manager', 'gift', 'synthetic.csv', gift_csv())
    preview = fx.call('general_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize',
        json=command(version=uploaded['version']))
    assert len(preview['rows']) == 3
    assert fx.catalog()['gifts'] == []
    fx.publish('general_manager', 'gift', uploaded, preview['rows'])
    assert fx.catalog('sales')['gifts'] == []  # No model has an explicit gift configuration yet.
    configured = [{'price_id': item['id'], 'quantity': 1} for item in fx.catalog()['gifts'][:2]]
    vehicle = fx.upload()
    fx.publish('manager', 'vehicle', vehicle, [{**VEHICLE_ROW,
        'gift_policy': {**VEHICLE_ROW['gift_policy'], 'standard_gifts': configured}}])
    sales, manager, gm = (fx.catalog(role) for role in ('sales', 'manager', 'general_manager'))
    assert len(sales['gifts']) == 2
    assert all('unit_price_cents' not in row and 'unit_cost_cents' not in row for row in sales['gifts'])
    assert manager['gifts'][0]['unit_price_cents'] == 6000
    assert 'unit_cost_cents' not in manager['gifts'][0]
    assert gm['gifts'][0]['unit_cost_cents'] == 4000
    assert fx.catalog('other_manager')['gifts'] == manager['gifts']
    assert fx.catalog('third_manager')['gifts'] == []


def test_invalid_gift_preview_and_cost_permissions_do_not_publish(fx):
    bad = fx.upload('general_manager', 'gift', 'invalid.csv', '名称,成本\n合成错误,1.001\n'.encode())
    fx.call('general_manager', 'POST', f'/pricing/uploads/{bad["id"]}/recognize', 422,
        json=command(version=bad['version']))
    restricted = fx.upload('manager', 'gift', 'synthetic.csv', gift_csv())
    fx.call('manager', 'POST', f'/pricing/uploads/{restricted["id"]}/recognize', 403,
        json=command(version=restricted['version']))
    fx.publish('manager', 'gift', restricted, [{'name': '合成成本', 'unit_cost_cents': 1}], expected=403)
    assert fx.catalog()['gifts'] == []


def test_contract_gift_save_readback_remove_and_frozen_catalog(fx):
    catalog = fx.prepared()
    first, second = catalog['gifts'][:2]
    choices = [{'price_id': first['id'], 'quantity': 1}, {'price_id': second['id'], 'quantity': 2}]
    body = fx.contract_body(catalog, choices)
    unconfigured = fx.catalog()['gifts'][2]
    denied = fx.call('sales', 'POST', '/contracts', 422,
        json={**body, **command(), 'gift_items': [{'price_id': unconfigured['id'], 'quantity': 1}]})
    assert '本车型明确配置' in denied['detail']
    created = fx.call('sales', 'POST', '/contracts', 201, json=body)
    key = created['id']
    saved = fx.call('sales', 'GET', f'/contracts/{key}')
    assert [(x['price_id'], x['quantity']) for x in saved['terms']['gifts_snapshot']] == [(first['id'], 1), (second['id'], 2)]
    assert all('unit_cost_cents' not in item and 'unit_price_cents' not in item for item in saved['terms']['gifts_snapshot'])
    assert saved['terms']['special'] is True  # Total cost 190 exceeds the frozen 100 budget.
    assert saved['terms']['gift_policy_check']['status'] == 'exceeded'
    assert 'cost_limit_cents' not in saved['terms']['gift_policy_check']
    replacement = fx.upload()
    fx.publish('manager', 'vehicle', replacement, [{**VEHICLE_ROW, 'control_price_cents': 11500000}])
    new_gifts = fx.upload('general_manager', 'gift', 'replacement.csv', '名称,成本,售价\n合成新赠品,1,2\n'.encode())
    fx.publish('general_manager', 'gift', new_gifts, [{'name': '合成新赠品', 'unit_cost_cents': 100, 'unit_price_cents': 200}])
    frozen = fx.call('sales', 'GET', f'/pricing/catalog?contract_id={key}')
    assert frozen['vehicles'][0]['control_price_cents'] == 10000000
    assert [row['id'] for row in frozen['gifts']] == [row['id'] for row in catalog['gifts']]
    edit = {**body, **command(version=saved['version']), 'gift_items': choices[:1]}
    updated = fx.call('sales', 'PUT', f'/contracts/{key}', json=edit)
    readback = fx.call('sales', 'GET', f'/contracts/{key}')
    assert readback['terms']['gifts_snapshot'] == updated['terms']['gifts_snapshot']
    assert len(readback['terms']['gifts_snapshot']) == 1
    assert readback['terms']['special'] is False  # Removing a gift brings cost below budget.
    assert readback['terms']['price_snapshot']['control_price_cents'] == 10000000
    for role in ('sales_peer', 'other_manager', 'third_manager'):
        fx.call(role, 'GET', f'/contracts/{key}', 404)
        fx.call(role, 'GET', f'/pricing/catalog?contract_id={key}', 404)
    with fx.sessions() as db:
        assert db.get(SalesContract, key).store_id == 1
        assert db.scalar(select(func.count()).select_from(RecordCustomer)) == 1
        terms = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == key))
        assert terms.gift_cost_total_cents == 4000
        assert terms.gift_batch_id == catalog['gift_batch_id']
