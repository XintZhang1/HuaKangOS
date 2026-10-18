"""Cashier price review and append-only signed evidence through real scoped APIs."""
import os
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

assert os.environ.get('RECORD_PRICING_ISOLATED') == '1', 'Use the external run_isolated.py runner'
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_delivery_api import (BASE, command, fx, login_secret, delivery_fx, contract,
    image_bytes, invoice_upload, gift_upload, confirm)
from app.business_record_delivery_models import RecordSignedDocument


def upload(fx, row, kind='signed_contract', *, role='finance', expected=200, request_id=None, **changes):
    data = command(version=row['version'], kind=kind)
    if request_id:
        data['request_id'] = request_id
    return fx.call(role, 'POST', f'/contracts/{row["id"]}/signed-documents', expected,
        data=data, files={'file': (changes.get('filename', 'synthetic-signed.png'),
            changes.get('content', image_bytes()))})


def test_invoice_price_review_preserves_omitted_historical_tax_values(delivery_fx):
    fx = delivery_fx
    row = contract(fx)
    invoice = invoice_upload(fx, row, confirm=False)
    fields = {'invoice_number': 'SYNTHETIC-PRICE', 'issued_on': '2026-10-18',
        'total_amount_cents': 11290000, 'tax_amount_cents': 1298850, 'net_amount_cents': 9991150}
    saved = fx.call('finance', 'POST', f'/contracts/{row["id"]}/invoice/confirm',
        json=command(version=invoice['invoice']['version'], fields=fields))
    updated = fx.call('finance', 'POST', f'/contracts/{row["id"]}/invoice/confirm',
        json=command(version=saved['invoice']['version'], fields={
            'invoice_number': fields['invoice_number'], 'issued_on': fields['issued_on'],
            'total_amount_cents': 11300000}))
    assert updated['invoice']['fields']['total_amount_cents'] == 11300000
    assert updated['invoice']['fields']['tax_amount_cents'] == 1298850
    assert updated['invoice']['fields']['net_amount_cents'] == 9991150
    cleared = fx.call('finance', 'POST', f'/contracts/{row["id"]}/invoice/confirm',
        json=command(version=updated['invoice']['version'], fields={
            'invoice_number': fields['invoice_number'], 'issued_on': fields['issued_on'],
            'total_amount_cents': 11300000, 'tax_amount_cents': None}))
    assert cleared['invoice']['fields']['tax_amount_cents'] is None
    assert cleared['invoice']['fields']['net_amount_cents'] == 9991150
    gift = gift_upload(fx, row)
    delivered = confirm(fx, {**row, 'version': gift['contract_version']}, cleared['invoice']['version'])
    assert delivered['delivery']['invoice_amount_cents'] == 11300000
    assert fx.call('finance', 'GET', f'/contracts/{row["id"]}/signed-documents')['files'] == []


def test_signed_originals_append_download_replay_and_completed_privacy(delivery_fx):
    fx = delivery_fx
    row = contract(fx)
    token = command()['request_id']
    first = upload(fx, row, request_id=token)
    assert upload(fx, row, request_id=token) == first
    current = {**row, 'version': first['contract_version']}
    second = upload(fx, current, 'signed_delivery')
    current['version'] = second['contract_version']
    third = upload(fx, current, content=image_bytes('red'))
    assert len(third['files']) == 3
    assert [item['kind'] for item in third['files']] == ['signed_contract', 'signed_delivery', 'signed_contract']
    assert all(item['available'] for item in third['files'])
    first_id = first['files'][0]['id']
    route = f'/contracts/{row["id"]}/signed-documents/files/{first_id}/download'
    response = fx.client('finance').get(BASE + route)
    assert response.status_code == 200 and response.content == image_bytes()
    assert response.headers['cache-control'] == 'no-store'
    upload(fx, row, expected=409)
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordSignedDocument)) == 3
        original = db.get(RecordSignedDocument, first_id)
        assert original.contract_version == row['version'] and original.created_by == 8
        original.filename = 'must-not-overwrite.png'
        with pytest.raises(HTTPException, match='409'):
            db.flush()
        db.rollback()
    invoice = invoice_upload(fx, row)
    gift = gift_upload(fx, {**row, 'version': third['contract_version']})
    delivered = confirm(fx, {**row, 'version': gift['contract_version']}, invoice['invoice']['version'])
    assert delivered['delivery']
    restricted = fx.call('finance', 'GET', f'/contracts/{row["id"]}/signed-documents')
    assert all(not item['available'] for item in restricted['files'])
    fx.call('finance', 'GET', route, 403)
    assert fx.client('clerk').get(BASE + route).content == image_bytes()
    appended = upload(fx, {**row, 'version': delivered['contract_version']}, 'signed_delivery')
    assert len(appended['files']) == 4 and not appended['files'][0]['available']


def test_signed_upload_scope_and_scan_guards(delivery_fx, monkeypatch):
    fx = delivery_fx
    row = contract(fx)
    for role in ('sales', 'manager', 'general_manager', 'clerk', 'store_admin'):
        upload(fx, row, role=role, expected=403)
    upload(fx, row, role='other_finance', expected=404)
    upload(fx, contract(fx, approve=False), expected=409)
    upload(fx, row, kind='unknown', expected=422)
    upload(fx, row, filename='broken.png', content=b'broken', expected=422)
    fx.call('admin', 'POST', f'/contracts/{row["id"]}/signed-documents', 409,
        headers={'X-Store-ID': 'all'}, data=command(version=row['version'], kind='signed_contract'),
        files={'file': ('synthetic.png', image_bytes())})
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordSignedDocument)) == 0
    from app import file_security
    monkeypatch.setattr(file_security, 'policy_mode', lambda: 'quarantine')
    quarantined = upload(fx, row)
    assert quarantined['files'][0]['available'] is False
    file_id = quarantined['files'][0]['id']
    fx.call('finance', 'GET', f'/contracts/{row["id"]}/signed-documents/files/{file_id}/download', 409)
    fx.call('other_finance', 'GET', f'/contracts/{row["id"]}/signed-documents/files/{file_id}/download', 404)
    second = contract(fx)
    fx.call('finance', 'GET', f'/contracts/{second["id"]}/signed-documents/files/{file_id}/download', 404)
