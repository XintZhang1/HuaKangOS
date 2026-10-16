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
            client.headers['X-Store-ID'] = '2' if role in {'other_manager', 'other_general_manager'} else '3' if role == 'third_manager' else '1'
            self.clients[role] = client
        return self.clients[role]

    def call(self, role, method, path, expected=200, **kwargs):
        response = self.client(role).request(method, BASE + path, **kwargs)
        assert response.status_code == expected, response.text
        return response.json()

    def catalog(self, role='manager', channel='retail'):
        return self.call(role, 'GET', '/pricing/catalog?sales_channel=' + channel)

    def upload(self, role='general_manager', kind='vehicle', filename='synthetic.xlsx', content=None, expected=201, channel='retail'):
        return self.call(role, 'POST', '/pricing/uploads', expected,
            data=command(kind=kind, sales_channel=channel), files={'file': (filename, vehicle_xlsx() if content is None else content)})

    def publish(self, role, kind, uploaded, rows, expected=201, **changes):
        current = self.catalog(role, changes.get('sales_channel', 'retail'))
        # The preview's display-only source label is omitted by the real form;
        # source_ref remains part of the saved gift provenance.
        rows = [{key: value for key, value in row.items()
                 if key not in {'source', 'source_text', 'raw_values', 'review_errors'}} for row in rows]
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
        self.publish('general_manager', 'vehicle', vehicle, [{**VEHICLE_ROW,
            'gift_policy': {**VEHICLE_ROW['gift_policy'], 'standard_gifts': configured}}])
        return self.catalog('sales')

    def contract_body(self, catalog, selections):
        return command(customer_name='合成合同客户', customer_phone='', brand='合成品牌', model='合成配置',
            vin='SYNTHETIC-' + uuid.uuid4().hex[:16], salesperson_id=4,
            contract_date=date(2026, 10, 12).isoformat(), sale_price_cents=11000000,
            vehicle_price_id=catalog['vehicles'][0]['id'], gift_items=selections,
            form_data={'seller_name': '合成卖方', 'exterior_color': '白', 'interior_color': '黑', 'deposit': '2000'},
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
            ('sales_peer', 'sales', 1), ('other_manager', 'manager', 2), ('third_manager', 'manager', 3),
            ('other_general_manager', 'general_manager', 2), ('deputy', 'group_deputy_manager', 1)]
        for ident, (name, role, store) in enumerate(roles, 1):
            # Delivery fixtures reserve 8-11 for cashiers, clerk and store admin.
            ident = {'other_general_manager': 20, 'deputy': 21}.get(name, ident)
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
    fx.upload(role='manager', expected=403)
    client = fx.client('general_manager')
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
    failure = fx.call('general_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize', 503,
        json=command(version=uploaded['version']))
    assert '原件已保存' in failure['detail']
    assert fx.catalog()['vehicles'] == []
    fx.publish('general_manager', 'vehicle', uploaded, [VEHICLE_ROW], expected=422, policy_confirmed=False)
    assert fx.catalog()['vehicles'] == []
    fx.publish('general_manager', 'vehicle', uploaded, [VEHICLE_ROW])
    published = fx.catalog()
    row = published['vehicles'][0]
    assert row['control_price_cents'] == 10000000
    assert 'cost_limit_cents' not in row['gift_policy']
    assert fx.catalog('general_manager')['vehicles'][0]['gift_policy']['cost_limit_cents'] == 10000
    assert published['vehicle_batch_id'] is not None
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordPriceBatch)) == 1
        assert db.get(RecordPricingFile, uploaded['id']).content == vehicle_xlsx()


def test_only_uploader_can_publish_and_same_brand_catalog_is_shared(fx):
    uploaded = fx.upload()
    fx.publish('admin', 'vehicle', uploaded, [VEHICLE_ROW], expected=403)
    fx.publish('general_manager', 'vehicle', uploaded, [VEHICLE_ROW])
    home, sibling, other = fx.catalog(), fx.catalog('other_manager'), fx.catalog('third_manager')
    assert home['vehicles'] == sibling['vehicles']
    assert home['vehicle_batch_id'] == sibling['vehicle_batch_id']
    assert other['vehicles'] == [] and other['vehicle_batch_id'] is None
    fx.call('other_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize', 404,
        json=command(version=uploaded['version']))
    fx.call('sales', 'GET', '/pricing/catalog', 403, headers={'X-Store-ID': '2'})
    sibling_file = fx.upload('other_general_manager')
    fx.publish('other_general_manager', 'vehicle', sibling_file, [{**VEHICLE_ROW, 'control_price_cents': 10500000}])
    assert fx.catalog('general_manager')['vehicles'] == fx.catalog('other_general_manager')['vehicles']
    assert fx.catalog()['vehicles'][0]['control_price_cents'] == 10500000


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
    fx.publish('general_manager', 'vehicle', vehicle, [{**VEHICLE_ROW,
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
    preview = fx.call('general_manager', 'POST', f'/pricing/uploads/{bad["id"]}/recognize',
        json=command(version=bad['version']))
    assert preview['rows'][0]['unit_cost_cents'] is None
    assert preview['rows'][0]['raw_values']['unit_cost_cents'] == '1.001'
    assert preview['row_errors'] and preview['requires_confirmation']
    fx.upload('manager', 'gift', 'synthetic.csv', gift_csv(), expected=403)
    fx.call('manager', 'POST', f'/pricing/uploads/{bad["id"]}/recognize', 403,
        json=command(version=bad['version']))
    fx.publish('manager', 'gift', bad, [{'name': '合成成本', 'unit_cost_cents': 1}], expected=403)
    assert fx.catalog()['gifts'] == []


def test_nonstandard_recognition_candidates_allow_manual_repair(fx, monkeypatch):
    import json
    from types import SimpleNamespace
    from app import business_assistant_service, business_record_pricing_recognition as recognition
    final_answer = ['以下为识别建议：\n```json\n' + json.dumps([{'车系': '合成车系', '年款': '2026',
        '车型': '合成配置', '指导价': '120000', '销售管控价': '请人工核定',
        '赠品政策': '保养一套，条件请核对'}], ensure_ascii=False) + '\n```']

    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def iter_bytes(self):
            yield json.dumps({'choices': [{'finish_reason': 'stop', 'message': {
                'content': final_answer[0], 'reasoning_content': 'synthetic-private-reasoning'}}]}).encode()

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def stream(self, *args, **kwargs): return Response()

    monkeypatch.setattr(business_assistant_service, 'load_config', lambda: SimpleNamespace(
        enabled=True, api_key='synthetic-no-network', provider='deepseek', synthetic=False, timeout_seconds=1))
    monkeypatch.setattr(recognition.httpx, 'Client', Client)
    uploaded = fx.upload()
    preview = fx.call('general_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize',
        json=command(version=uploaded['version']))
    row = preview['rows'][0]
    assert row['model'] == '合成配置' and row['guide_price_cents'] == 12000000
    assert row['raw_values']['control_price_cents'] == '请人工核定'
    assert row['gift_policy_suggestion']['text'] == '保养一套，条件请核对'
    assert 'synthetic-private-reasoning' not in json.dumps(preview)
    assert fx.catalog()['vehicles'] == []
    final_answer[0] = '车型资料已保留，但缺少限价；请根据原表补填。'
    manual = fx.call('general_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize',
        json=command(version=uploaded['version']))
    assert len(manual['rows']) == 1 and manual['raw_output'] == final_answer[0]
    assert manual['recognition_complete'] is False
    fx.publish('general_manager', 'vehicle', uploaded, [VEHICLE_ROW])
    assert len(fx.catalog()['vehicles']) == 1

    gift = fx.upload('general_manager', 'gift', 'nonstandard.csv',
        '名称,成本,成本,售价\n合成坐垫,待定,12,20元\n,说明,,\n'.encode())
    draft = fx.call('general_manager', 'POST', f'/pricing/uploads/{gift["id"]}/recognize',
        json=command(version=gift['version']))
    assert len(draft['rows']) == 2 and draft['warnings']
    assert draft['rows'][0]['unit_cost_cents'] is None
    assert '待定' in draft['rows'][0]['source_text'] and draft['rows'][0]['raw_values']['unit_price_cents'] == '20元'
    assert fx.catalog()['gifts'] == []
    fx.publish('general_manager', 'gift', gift, [{'name': '合成坐垫', 'brand': '合成品牌',
        'unit_cost_cents': 1200, 'unit_price_cents': 2000}])
    assert fx.catalog('general_manager')['gifts'][0]['unit_cost_cents'] == 1200
    other = fx.upload('general_manager', 'gift', 'with-notes.csv',
        '首组礼包,40,60\n名称,成本,售价,备注,领取条件\n脚垫,40,60,赠品名称,交车后一年领取\n贴膜,50,70,正常,\n'.encode())
    candidates = fx.call('general_manager', 'POST', f'/pricing/uploads/{other["id"]}/recognize',
        json=command(version=other['version']))
    assert len(candidates['rows']) == 3
    assert '首组礼包' in candidates['rows'][0]['source_text']
    assert [item['name'] for item in candidates['rows'][1:]] == ['脚垫', '贴膜']
    assert '领取条件: 交车后一年领取' in candidates['rows'][1]['source_text']
    assert candidates['recognition_complete'] is False


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
    fx.publish('general_manager', 'vehicle', replacement, [{**VEHICLE_ROW, 'control_price_cents': 11500000}])
    new_gifts = fx.upload('general_manager', 'gift', 'replacement.csv', '名称,成本,售价\n合成新赠品,1,2\n'.encode())
    fx.publish('general_manager', 'gift', new_gifts, [{'name': '合成新赠品', 'unit_cost_cents': 100, 'unit_price_cents': 200}])
    frozen = fx.call('sales', 'GET', f'/pricing/catalog?contract_id={key}')
    assert 'control_price_cents' not in frozen['vehicles'][0]
    assert fx.call('general_manager', 'GET', f'/pricing/catalog?contract_id={key}')['vehicles'][0]['control_price_cents'] == 10000000
    assert [row['id'] for row in frozen['gifts']] == [row['id'] for row in catalog['gifts']]
    edit = {**body, **command(version=saved['version']), 'gift_items': choices[:1]}
    updated = fx.call('sales', 'PUT', f'/contracts/{key}', json=edit)
    readback = fx.call('sales', 'GET', f'/contracts/{key}')
    assert readback['terms']['gifts_snapshot'] == updated['terms']['gifts_snapshot']
    assert len(readback['terms']['gifts_snapshot']) == 1
    assert readback['terms']['special'] is False  # Removing a gift brings cost below budget.
    assert 'control_price_cents' not in readback['terms']['price_snapshot']
    assert fx.call('general_manager', 'GET', f'/contracts/{key}')['terms']['price_snapshot']['control_price_cents'] == 10000000
    for role in ('sales_peer', 'other_manager', 'third_manager'):
        fx.call(role, 'GET', f'/contracts/{key}', 404)
        fx.call(role, 'GET', f'/pricing/catalog?contract_id={key}', 404)
    with fx.sessions() as db:
        assert db.get(SalesContract, key).store_id == 1
        assert db.scalar(select(func.count()).select_from(RecordCustomer)) == 1
        terms = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == key))
        assert terms.gift_cost_total_cents == 4000
        assert terms.gift_batch_id == catalog['gift_batch_id']


def test_wholesale_price_approval_and_free_paid_accessories_stay_separate(fx):
    retail = fx.prepared()
    assert 'control_price_cents' not in retail['vehicles'][0]
    assert all('unit_price_cents' not in item and 'unit_cost_cents' not in item for item in retail['gifts'])
    paid = retail['accessories'][0]
    assert paid['unit_price_cents'] == 6000 and 'unit_cost_cents' not in paid
    body = fx.contract_body(retail, [{'price_id': paid['id'], 'quantity': 1}])
    body['accessory_items'] = [{'price_id': paid['id'], 'quantity': 2}]
    customer_order = fx.call('sales', 'POST', '/contracts', 201, json=body)
    terms = customer_order['terms']
    assert terms['special'] is False  # Only the free quantity consumes the gift allowance.
    assert terms['submission_data']['accessory_total_cents'] == 12000
    assert terms['submission_data']['accessory_snapshot'][0]['quantity'] == 2
    assert 'cost_cents' not in terms['submission_data']['accessory_snapshot'][0]
    with fx.sessions() as db:
        stored = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == customer_order['id']))
        assert stored.gift_cost_total_cents == 4000 and stored.gift_total_cents == 6000
        assert stored.submission_data['accessory_snapshot'][0]['cost_cents'] == 8000
    upload = fx.upload(channel='wholesale')
    fx.publish('general_manager', 'vehicle', upload, [{**VEHICLE_ROW, 'control_price_cents': 11500000,
        'gift_policy': None}], sales_channel='wholesale')
    wholesale = fx.catalog('manager', 'wholesale')
    assert wholesale['vehicle_batch_id'] != retail['vehicle_batch_id']
    assert fx.catalog()['vehicles'][0]['control_price_cents'] == 10000000
    assert wholesale['vehicles'][0]['control_price_cents'] == 11500000
    fx.call('sales', 'GET', '/pricing/catalog?sales_channel=wholesale', 403)
    channel = fx.call('manager', 'POST', '/wholesale-channels', 201, json=command(name='合成二级渠道'))
    order = fx.contract_body(wholesale, [])
    order.update(salesperson_id=2, submission_data={'sales_channel': 'wholesale',
        'wholesale_channel_id': channel['id'], 'payment_method': '全款'})
    fx.call('manager', 'POST', '/contracts', 422,
        json={**order, **command(), 'vehicle_price_id': retail['vehicles'][0]['id']})
    opened = fx.call('manager', 'POST', '/contracts', 201, json=order)
    assert opened['status'] == 'manager_approved' and opened['manager_approved_by'] is None
    assert opened['terms']['submission_data']['wholesale_channel_name'] == '合成二级渠道'
    assert opened['terms']['special'] is True
    fx.call('manager', 'POST', f'/contracts/{opened["id"]}/approve', 403,
        json=command(version=opened['version']))
    reviewed = fx.call('general_manager', 'POST', f'/contracts/{opened["id"]}/approve',
        json=command(version=opened['version'], note='合成低于二级限价核对'))
    assert reviewed['status'] == 'deputy_pending' and reviewed['general_manager_approved_by'] == 3
    fx.call('general_manager', 'POST', f'/contracts/{opened["id"]}/deputy-approve', 403,
        json=command(version=reviewed['version']))
    approved = fx.call('deputy', 'POST', f'/contracts/{opened["id"]}/deputy-approve',
        json=command(version=reviewed['version'], note='合成特殊二级合同批准'))
    assert approved['status'] == 'approved' and approved['deputy_approved_by'] == 21
    assert approved['salesperson_id'] == 2 and approved['terms']['submission_data']['sales_channel'] == 'wholesale'


def test_contract_contact_and_private_price_check_keep_frozen_basis(fx):
    catalog = fx.prepared()
    profile = fx.call('admin', 'GET', '/store-profile')
    fx.call('admin', 'PUT', '/store-profile', json=command(version=profile['version'],
        sellers=profile['sellers'], sales_contacts={'4': '0717-1234567'}))
    price_id = catalog['vehicles'][0]['id']
    for sale, below in ((10000000, False), (9999999, True), (11000000, False)):
        result = fx.call('sales', 'GET', f'/pricing/price-check?vehicle_price_id={price_id}&sale_price_cents={sale}')
        assert result == {'below_limit': below}
    body = fx.contract_body(catalog, [])
    body['form_data']['seller_phone'] = '13800001234'
    row = fx.call('sales', 'POST', '/contracts', 201, json=body)
    assert row['form_data']['seller_phone'] == '13800001234'
    defaulted = fx.call('sales', 'POST', '/contracts', 201, json=fx.contract_body(catalog, []))
    assert defaulted['form_data']['seller_phone'] == '0717-1234567'
    replacement = fx.upload()
    fx.publish('general_manager', 'vehicle', replacement, [{**VEHICLE_ROW, 'control_price_cents': 11500000}])
    current_id = fx.catalog('sales')['vehicles'][0]['id']
    assert fx.call('sales', 'GET', f'/pricing/price-check?vehicle_price_id={current_id}&sale_price_cents=11000000') == {'below_limit': True}
    assert fx.call('sales', 'GET', f'/pricing/price-check?contract_id={row["id"]}&vehicle_price_id={price_id}&sale_price_cents=11000000') == {'below_limit': False}
    fx.call('other_manager', 'GET', f'/pricing/price-check?contract_id={row["id"]}&vehicle_price_id={price_id}&sale_price_cents=11000000', 404)
    edited = deepcopy(body)
    edited.update(command(version=row['version']))
    edited['form_data']['seller_phone'] = '0717-7654321'
    updated = fx.call('sales', 'PUT', f'/contracts/{row["id"]}', json=edited)
    assert updated['form_data']['seller_phone'] == '0717-7654321'
    assert fx.call('admin', 'GET', '/store-profile')['sales_contacts']['4'] == '0717-1234567'


def test_vehicle_recognition_preserves_conditional_source_quotes_for_review(fx, monkeypatch):
    import io
    import json
    import zipfile
    from types import SimpleNamespace
    from xml.sax.saxutils import escape
    from app import business_assistant_service, business_record_pricing_recognition as recognition

    # The explicit floor is in H, while E is a discount column. H3:I4 also
    # covers a second model whose own row has no price cell.
    entries = {1: {'C': '车型', 'D': '指导价', 'E': '店内限价', 'H': '销售管控价（元）'},
        2: {'H': '100000'}, 3: {'H': '99000包牌（含置换）'}, 4: {},
        5: {'H': '10.50万元'}, 6: {'H': '全款100000；分期95000'},
        7: {}, 8: {'H': '100000', 'J': '赠品需办理分期'}}
    for row in range(2, 9):
        entries[row].update({'C': '合成配置' + str(row), 'D': '120000', 'E': '20000'})
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    xml += ''.join('<row r="%s">%s</row>' % (row, ''.join(
        '<c r="%s%s" t="inlineStr"><is><t>%s</t></is></c>' % (col, row, escape(value))
        for col, value in values.items())) for row, values in entries.items())
    xml += '</sheetData><mergeCells><mergeCell ref="H3:I4"/></mergeCells></worksheet>'
    content = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(vehicle_xlsx())) as original, zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as target:
        for item in original.infolist():
            target.writestr(item.filename, xml if item.filename == 'xl/worksheets/sheet1.xml' else original.read(item))
    uploaded = fx.upload('general_manager', 'vehicle', 'synthetic-conditions.xlsx', content.getvalue())
    model_rows = [{'family': '合成车系', 'series': '合成系列', 'model': '合成配置' + str(row),
        'guide_price': '120000', 'control_price': '105000' if row == 5 else '100000',
        'note': '按同一行指导价减明确优惠额推算，须核对' if row == 7 else '',
        'gift_policy': {'text': '合成赠品条件', 'cost_limit': None},
        'source_sheet': '合成限价', 'source_row': row} for row in range(2, 9)]

    class ModelResponse:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def iter_bytes(self):
            yield json.dumps({'choices': [{'finish_reason': 'stop', 'message': {
                'content': json.dumps({'rows': model_rows, 'warnings': []}, ensure_ascii=False)}}]}).encode()

    class ModelClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def stream(self, method, url, **kwargs):
            assert method == 'POST' and url == 'https://api.deepseek.com/chat/completions'
            return ModelResponse()

    monkeypatch.setattr(business_assistant_service, 'load_config', lambda: SimpleNamespace(
        enabled=True, api_key='synthetic-no-network', provider='deepseek', synthetic=False, timeout_seconds=1))
    monkeypatch.setattr(recognition.httpx, 'Client', ModelClient)
    preview = fx.call('general_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize',
        json=command(version=uploaded['version']))
    by_row = {int(row['source'].rsplit(':', 1)[1]): row for row in preview['rows']}
    assert len(by_row) == 7 and all(row['guide_price_cents'] == 12000000 for row in by_row.values())
    assert all(by_row[row]['control_price_cents'] is None for row in (3, 4, 6))
    assert '99000包牌（含置换）' in by_row[3]['note'] and '原表H3' in by_row[4]['note']
    assert '全款100000；分期95000' in by_row[6]['note']
    assert [by_row[row]['control_price_cents'] for row in (2, 5, 7, 8)] == [10000000, 10500000, 10000000, 10000000]
    assert '推算' in by_row[7]['note']
    assert {error['source'] for error in preview['row_errors']} == {'合成限价:3', '合成限价:4', '合成限价:6'}
    assert preview['recognition_complete'] is False and preview['requires_confirmation'] is True
    assert fx.catalog()['vehicles'] == []
