"""Stamped gift originals and invoice delivery gates, in an isolated source mirror."""
import hashlib
import io
import os
from datetime import date
from pathlib import Path
import sys

import pytest
from PIL import Image
from sqlalchemy import func, select

assert os.environ.get('RECORD_PRICING_ISOLATED') == '1', 'Use the external run_isolated.py runner'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'record_pricing'))
from test_pricing_api import BASE, command, fx, login_secret
from app.models import User, UserStore
from app.business_record_delivery_models import RecordDelivery, RecordGiftDocument
from app.business_record_invoice_models import RecordInvoice, RecordInvoiceFile
from app.business_records_models import SalesContract


def image_bytes(color='white', kind='PNG'):
    output = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(output, format=kind)
    return output.getvalue()


@pytest.fixture
def delivery_fx(fx):
    with fx.sessions() as db:
        secret = db.get(User, 1).password_hash
        for ident, name, role, store in ((8, 'finance', 'finance', 1),
                (9, 'other_finance', 'finance', 2), (10, 'clerk', 'clerk', 1),
                (11, 'store_admin', 'store_admin', 1)):
            db.add(User(id=ident, username='synthetic_' + name, display_name='合成-' + name,
                role=role, password_hash=secret, must_change_password=False, active=True))
            db.flush()
            db.add(UserStore(user_id=ident, store_id=store, role=role))
        db.commit()
    fx.client('other_finance').headers['X-Store-ID'] = '2'
    fx.delivery_catalog = fx.prepared()
    return fx


def contract(fx, approve=True):
    catalog = fx.delivery_catalog
    body = fx.contract_body(catalog, [{'price_id': catalog['gifts'][0]['id'], 'quantity': 1}])
    row = fx.call('sales', 'POST', '/contracts', 201, json=body)
    if approve:
        row = fx.call('manager', 'POST', f'/contracts/{row["id"]}/manager-approve',
            json=command(version=row['version']))
        row = fx.call('general_manager', 'POST', f'/contracts/{row["id"]}/approve',
            json=command(version=row['version']))
        assert row['status'] == 'approved'
    return row


def gift_upload(fx, row, *, role='finance', content=None, filename='synthetic-gift.png', expected=200, request_id=None):
    data = command(version=row['version'])
    if request_id:
        data['request_id'] = request_id
    return fx.call(role, 'POST', f'/contracts/{row["id"]}/gift-document', expected,
        data=data, files={'file': (filename, image_bytes() if content is None else content)})


def invoice_upload(fx, row, confirm=True):
    result = fx.call('finance', 'POST', f'/contracts/{row["id"]}/invoice',
        data=command(version=0), files={'file': ('synthetic-invoice.png', image_bytes('blue'))})
    if confirm:
        result = fx.call('finance', 'POST', f'/contracts/{row["id"]}/invoice/confirm',
            json=command(version=result['invoice']['version'], fields={
                'invoice_number': 'SYNTHETIC-INVOICE-' + str(row['id']), 'issued_on': '2026-10-12',
                'total_amount_cents': 11000000}))
    return result


def confirm(fx, row, invoice_version=1, expected=200, **changes):
    return fx.call('finance', 'POST', f'/contracts/{row["id"]}/delivery-confirm', expected,
        json=command(version=row['version'], invoice_version=invoice_version, **changes))


def test_upload_download_binding_readback_and_append_only_correction(delivery_fx):
    fx = delivery_fx
    row = contract(fx)
    initial = fx.call('finance', 'GET', f'/contracts/{row["id"]}/delivery-state')
    assert initial['gift_document'] is None
    assert initial['actions'] == ['upload_gift_document']
    invoice = invoice_upload(fx, row)
    uploaded = gift_upload(fx, row)
    original = uploaded['gift_document']
    assert original['filename'] == 'synthetic-gift.png'
    assert original['sha256'] == hashlib.sha256(image_bytes()).hexdigest()
    assert original['available'] is True
    assert 'confirm_delivery' in uploaded['actions']
    readback = fx.call('finance', 'GET', f'/contracts/{row["id"]}')
    assert readback['delivery_state']['gift_document'] == original
    assert readback['version'] == uploaded['contract_version']
    download = fx.client('finance').get(BASE + f'/contracts/{row["id"]}/gift-document/files/{original["id"]}/download')
    assert download.status_code == 200 and download.content == image_bytes()
    assert download.headers['cache-control'] == 'no-store'
    confirm(fx, {**row, 'version': uploaded['contract_version']}, invoice['invoice']['version'] + 1, expected=409)
    delivered = confirm(fx, {**row, 'version': uploaded['contract_version']}, invoice['invoice']['version'])
    assert delivered['delivery']['gift_document_id'] == original['id']
    assert delivered['delivery']['invoice_file_id'] == invoice['files'][0]['id']
    assert delivered['materials_ready'] is True
    replacement = gift_upload(fx, {**row, 'version': delivered['contract_version']},
        content=image_bytes('red'), filename='synthetic-correction.png')
    assert replacement['gift_document']['id'] != original['id']
    assert replacement['delivery']['gift_document_id'] == original['id']
    assert 'confirm_delivery' not in replacement['actions']
    with fx.sessions() as db:
        stored = db.get(RecordGiftDocument, original['id'])
        assert (stored.contract_id, stored.store_id, stored.created_by, stored.content) == (row['id'], 1, 8, image_bytes())
        assert db.scalar(select(func.count()).select_from(RecordGiftDocument)) == 2
        delivery = db.scalar(select(RecordDelivery).where(RecordDelivery.contract_id == row['id']))
        assert delivery.gift_document_id == original['id']
        assert db.get(RecordInvoiceFile, delivery.invoice_file_id).invoice_id == delivery.invoice_id


def test_both_verified_invoice_and_stamped_gift_are_required(delivery_fx):
    fx = delivery_fx
    row = contract(fx)
    assert '发票' in confirm(fx, row, expected=409)['detail']
    invoice = invoice_upload(fx, row, confirm=False)
    uploaded = gift_upload(fx, row)
    current = {**row, 'version': uploaded['contract_version']}
    assert 'confirm_delivery' not in uploaded['actions']
    assert '发票' in confirm(fx, current, invoice['invoice']['version'], expected=409)['detail']
    second = contract(fx)
    verified = invoice_upload(fx, second)
    failure = confirm(fx, second, verified['invoice']['version'], expected=409)
    assert '盖章赠品单' in failure['detail']
    assert 'confirm_delivery' not in fx.call('finance', 'GET', f'/contracts/{second["id"]}/delivery-state')['actions']
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordDelivery)) == 0


def test_invalid_files_stale_version_and_replay_keep_originals(delivery_fx):
    fx = delivery_fx
    row = contract(fx)
    for filename, content, status in [('empty.png', b'', 413), ('broken.png', b'broken', 422),
            ('synthetic.csv', b'name,value\nsynthetic,1\n', 422)]:
        gift_upload(fx, row, content=content, filename=filename, expected=status)
    token = command()['request_id']
    uploaded = gift_upload(fx, row, request_id=token)
    replay = gift_upload(fx, row, request_id=token)
    assert uploaded == replay
    gift_upload(fx, row, content=image_bytes('red'), expected=409)
    latest = fx.call('finance', 'GET', f'/contracts/{row["id"]}/delivery-state')
    assert latest['gift_document'] == uploaded['gift_document']
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordGiftDocument)) == 1


def test_gift_upload_finance_permissions_and_contract_store_isolation(delivery_fx):
    fx = delivery_fx
    row, second = contract(fx), contract(fx)
    for role in ('sales', 'manager', 'general_manager', 'clerk'):
        gift_upload(fx, row, role=role, expected=403)
        assert 'upload_gift_document' not in fx.call(role, 'GET', f'/contracts/{row["id"]}/delivery-state')['actions']
    gift_upload(fx, row, role='other_finance', expected=404)
    uploaded = gift_upload(fx, row)
    file_id = uploaded['gift_document']['id']
    route = f'/contracts/{row["id"]}/gift-document/files/{file_id}/download'
    fx.call('other_finance', 'GET', route, 404)
    fx.call('sales', 'GET', route, 403)
    fx.call('finance', 'GET', f'/contracts/{second["id"]}/gift-document/files/{file_id}/download', 404)
    fx.call('finance', 'GET', f'/contracts/{row["id"]}/delivery-state', 403, headers={'X-Store-ID': '2'})
    for role in ('general_manager', 'clerk'):
        response = fx.client(role).get(BASE + route)
        assert response.status_code == 200 and response.content == image_bytes()
    caps = fx.call('clerk', 'GET', '/catalog')['capabilities']
    assert caps['read_invoice'] is True and caps['upload_invoice'] is False
    aggregate = fx.call('admin', 'GET', f'/contracts/{row["id"]}/delivery-state', headers={'X-Store-ID': 'all'})
    assert aggregate['actions'] == []
    fx.call('admin', 'POST', f'/contracts/{row["id"]}/gift-document', 409,
        data=command(version=uploaded['contract_version']), files={'file': ('synthetic.png', image_bytes())},
        headers={'X-Store-ID': 'all'})


def test_unapproved_contract_rejects_upload_without_file_creation(delivery_fx):
    fx = delivery_fx
    row = contract(fx, approve=False)
    gift_upload(fx, row, expected=409)
    fx.call('finance', 'POST', f'/contracts/{row["id"]}/invoice', 409,
        data=command(version=0), files={'file': ('synthetic-invoice.png', image_bytes())})
    state = fx.call('finance', 'GET', f'/contracts/{row["id"]}/delivery-state')
    assert state['gift_document'] is None and state['actions'] == []
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordGiftDocument)) == 0
        assert db.scalar(select(func.count()).select_from(RecordInvoice)) == 0


def test_quarantined_gift_cannot_be_downloaded_or_used_for_delivery(delivery_fx, monkeypatch):
    fx = delivery_fx
    row = contract(fx)
    invoice = invoice_upload(fx, row)
    from app import file_security
    monkeypatch.setattr(file_security, 'policy_mode', lambda: 'quarantine')
    uploaded = gift_upload(fx, row)
    assert uploaded['gift_document']['available'] is False
    assert 'confirm_delivery' not in uploaded['actions']
    key = uploaded['gift_document']['id']
    fx.call('finance', 'GET', f'/contracts/{row["id"]}/gift-document/files/{key}/download', 409)
    confirm(fx, {**row, 'version': uploaded['contract_version']}, invoice['invoice']['version'], expected=409)
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordDelivery)) == 0


@pytest.mark.parametrize('workflow', ['legacy-v2', 'trial-v29'])
def test_historical_approved_workflow_cannot_upload_new_delivery_gift(delivery_fx, workflow):
    fx = delivery_fx
    # Historical rows are synthetic fixture facts, not new approvals fabricated
    # through a modern route. All attempted uploads still use the real API.
    with fx.sessions() as db:
        old = SalesContract(store_id=1, number='SYNTHETIC-OLD-' + workflow,
            salesperson_id=4, created_by=4, customer_name='合成旧合同', brand='合成品牌',
            model='合成旧车型', vin='SYNTHETIC-OLD-' + workflow, contract_date=date(2026, 1, 1),
            sale_price_cents=10000000, workflow_version=workflow, status='approved',
            expected_amount_cents=10000000, cost_cents=8000000, profit_cents=2000000,
            gift_cost_cents=0, priced_by=3, approved_by=3, approved_snapshot={'synthetic': True})
        db.add(old)
        db.commit()
        row = {'id': old.id, 'version': old.version}
    gift_upload(fx, row, expected=409)
    state = fx.call('finance', 'GET', f'/contracts/{row["id"]}/delivery-state')
    assert state['gift_document'] is None and state['actions'] == []


def test_store_admin_can_read_contract_gift_summary_but_cannot_upload(delivery_fx):
    fx = delivery_fx
    row = contract(fx)
    uploaded = gift_upload(fx, row)
    key = uploaded['gift_document']['id']
    detail = fx.call('store_admin', 'GET', f'/contracts/{row["id"]}')
    state = detail['delivery_state']
    assert state['gift_document']['id'] == key and state['actions'] == []
    gift_upload(fx, {**row, 'version': uploaded['contract_version']}, role='store_admin', expected=403)
    fx.call('store_admin', 'GET', f'/contracts/{row["id"]}', 403, headers={'X-Store-ID': '2'})


def test_actual_accessory_cost_preview_review_approval_and_report(delivery_fx):
    from copy import deepcopy
    from decimal import Decimal
    import re
    from app.business_record_profit import FORMULAS, column_key
    from app.business_record_pricing_models import RecordContractTerms
    from pypdf import PdfReader
    fx = delivery_fx
    catalog = fx.delivery_catalog
    body = fx.contract_body(catalog, [{'price_id': catalog['gifts'][0]['id'], 'quantity': 1}])
    body['accessory_items'] = [{'price_id': catalog['accessories'][0]['id'], 'quantity': 2}]
    row = fx.call('sales', 'POST', '/contracts', 201, json=body)
    key = row['id']
    row = fx.call('manager', 'POST', f'/contracts/{key}/manager-approve', json=command(version=row['version']))
    row = fx.call('general_manager', 'POST', f'/contracts/{key}/approve', json=command(version=row['version']))
    printed = fx.client('finance').get(BASE + f'/contracts/{key}/gift-document/print')
    assert printed.status_code == 200 and printed.headers['content-type'] == 'application/pdf'
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(printed.content)).pages)
    assert '客户赠送券' in text and catalog['gifts'][0]['name'] in text and '赠送数量：1 套' in text
    assert not any(term in text for term in ('60.00', '40.00', '成本', '单价', '售价'))
    fx.call('sales', 'GET', f'/contracts/{key}/gift-document/print', 403)
    invoice = invoice_upload(fx, row)
    gift = gift_upload(fx, row)
    state = confirm(fx, {**row, 'version': gift['contract_version']}, invoice['invoice']['version'])
    fx.call('finance', 'GET', f'/contracts/{key}/gift-document/print', 403)
    evidence = fx.call('finance', 'POST', f'/contracts/{key}/accessory-sales/files', 201,
        data=command(version=state['contract_version']), files={'file': ('synthetic-paid.png', image_bytes('green'))})
    prefill = fx.call('clerk', 'GET', f'/report-prefill?report_key=vehicle_details&contract_id={key}')
    values = {column_key(letter): '0.00' for letter in re.findall('[A-Z]+', FORMULAS['vehicle_details'][0])}
    values.update(prefill['values'])
    values.update(c23='110000.00', c11='100000.00')
    data = {'report_key': 'vehicle_details', 'values': values, 'extension_data': {}}
    pending = fx.call('clerk', 'POST', f'/contracts/{key}/profit-preview', json=data)
    assert pending['extension_data']['accessory_sales_cost_cents'] is None
    assert pending['accessory_sales_verification']['quoted_cost_cents'] == 8000
    data['extension_data'] = {'accessory_sales_verified': True, 'accessory_sales_file_id': evidence['id']}
    automatic = fx.call('clerk', 'POST', f'/contracts/{key}/profit-preview', json=data)
    assert automatic['extension_data']['accessory_sales_cost_cents'] == 8000
    assert automatic['accessory_sales_verification']['cost_source'] == 'contract_frozen'
    data['extension_data']['accessory_sales_actual_cost_cents'] = 1234
    actual = fx.call('clerk', 'POST', f'/contracts/{key}/profit-preview', json=data)
    assert actual['profit_cents'] == automatic['profit_cents'] + 8000 - 1234
    zero = deepcopy(data)
    zero['extension_data']['accessory_sales_actual_cost_cents'] = 0
    checked_zero = fx.call('clerk', 'POST', f'/contracts/{key}/profit-preview', json=zero)
    assert checked_zero['extension_data']['accessory_sales_cost_cents'] == 0
    assert checked_zero['accessory_sales_verification']['cost_source'] == 'clerk_actual'
    saved = fx.call('clerk', 'PUT', f'/contracts/{key}/office-review', json=command(version=evidence['contract_version'], **data))
    submitted = fx.call('clerk', 'POST', f'/contracts/{key}/office-submit', json=command(version=saved['version']))
    approved = fx.call('general_manager', 'POST', f'/contracts/{key}/office-approve', json=command(version=submitted['version']))
    checked = approved['office_approved_data']
    assert checked['extension_data']['accessory_sales_cost_cents'] == 1234
    assert checked['profit_cents'] == actual['profit_cents']
    report = fx.call('clerk', 'GET', '/reports?report=operating_profit_v218:accessory_sales_cost&date_from=' + checked['period'] + '&date_to=' + checked['period'])
    assert Decimal(report['grand_total']['accessory_sales_cost']) == Decimal('12.34')
    with fx.sessions() as db:
        terms = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == key))
        assert terms.submission_data['accessory_snapshot'][0]['cost_cents'] == 8000
        assert db.get(SalesContract, key).approved_snapshot['terms']['submission_data']['accessory_snapshot'][0]['cost_cents'] == 8000
    no_paid = contract(fx)
    denied = fx.call('clerk', 'POST', f'/contracts/{no_paid["id"]}/profit-preview', 422, json=data)
    assert '未选择有偿精品' in denied['detail']
