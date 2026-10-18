"""Frozen gifts, single redemption, correction history and both print copies."""
import io
import json
import os
from pathlib import Path
import sys
from pypdf import PdfReader
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_delivery_api import command, fx, login_secret, delivery_fx, invoice_upload
from app.business_records_models import SalesContract
from app.business_record_benefit_models import RecordBenefitRedemption


def approved(fx):
    catalog = fx.delivery_catalog
    body = fx.contract_body(catalog, [{'price_id': catalog['gifts'][0]['id'], 'quantity': 3}])
    body['submission_data'].update(first_service_count=1, nps_participation=True,
        payment_method='贷款', down_payment_cents=0)
    body['form_data'].update(payment_institution_type='厂家金融', payment_bank='合成汽金')
    row = fx.call('sales', 'POST', '/contracts', 201, json=body)
    row = fx.call('manager', 'POST', f'/contracts/{row["id"]}/manager-approve', json=command(version=row['version'], note='合成超额赠品审批说明'))
    row = fx.call('general_manager', 'POST', f'/contracts/{row["id"]}/approve', json=command(version=row['version'], note='合成批准'))
    if row['status'] == 'deputy_pending':
        row = fx.call('deputy', 'POST', f'/contracts/{row["id"]}/deputy-approve', json=command(version=row['version'], note='合成批准'))
    assert row['status'] == 'approved'
    return row


def test_single_redemption_replay_exhaustion_and_append_only_undo(delivery_fx):
    fx = delivery_fx
    row = approved(fx)
    path = f'/contracts/{row["id"]}/benefits'
    state = fx.call('finance', 'GET', path)
    with fx.sessions() as db:
        frozen = json.dumps(db.get(SalesContract, row['id']).approved_snapshot, sort_keys=True)
    sources = {item['key']: item for item in state['items']}
    assert sources['first_service']['remaining'] == sources['nps']['remaining'] == 1
    gift_key = next(key for key in sources if key.startswith('gift:'))
    assert sources[gift_key]['remaining'] == 3
    request = command(version=state['version'], source_key=gift_key,
        redeemed_on='2026-10-18', note='合成一次服务', confirmed=True)
    first = fx.call('finance', 'POST', path + '/redeem', json=request)
    assert fx.call('finance', 'POST', path + '/redeem', json=request) == first
    assert next(i for i in first['items'] if i['key'] == gift_key)['remaining'] == 2
    fx.call('finance', 'POST', path + '/redeem', 409, json={**request, **command()})
    current = first
    for _ in range(2):
        current = fx.call('finance', 'POST', path + '/redeem', json={**request, **command(version=current['version'])})
    fx.call('finance', 'POST', path + '/redeem', 409, json={**request, **command(version=current['version'])})
    event_id = current['history'][0]['id']
    current = fx.call('finance', 'POST', path + f'/{event_id}/reverse',
        json=command(version=current['version'], note='合成误录更正'))
    assert len(current['history']) == 4 and current['history'][-1]['quantity'] == -1
    assert next(i for i in current['items'] if i['key'] == gift_key)['remaining'] == 1
    fx.call('finance', 'POST', path + f'/{event_id}/reverse', 409,
        json=command(version=current['version'], note='重复撤销'))
    with fx.sessions() as db:
        assert json.dumps(db.get(SalesContract, row['id']).approved_snapshot, sort_keys=True) == frozen
        assert len(list(db.scalars(select(RecordBenefitRedemption)))) == 4


def test_redemption_permissions_explicit_confirmation_and_dates(delivery_fx):
    fx = delivery_fx
    row = approved(fx)
    path = f'/contracts/{row["id"]}/benefits'
    request = command(version=row['version'], source_key='nps', redeemed_on='2026-10-18', confirmed=True)
    fx.call('sales', 'GET', path, 403)
    fx.call('other_finance', 'GET', path, 404)
    fx.call('clerk', 'POST', path + '/redeem', 403, json=request)
    fx.call('finance', 'POST', path + '/redeem', 422, json={**request, 'confirmed': False})
    fx.call('finance', 'POST', path + '/redeem', 422, json={**request, 'redeemed_on': '2099-01-01'})
    fx.call('finance', 'POST', path + '/redeem', 409, json={**request, 'source_key': 'gift:999999'})
    state = fx.call('finance', 'POST', path + '/redeem', json=request)
    assert next(i for i in state['items'] if i['key'] == 'nps')['remaining'] == 0
    fx.call('finance', 'POST', path + '/redeem', 409, json={**request, **command(version=state['version'])})


def test_print_customer_internal_and_loan_category_roundtrip(delivery_fx):
    fx = delivery_fx
    row = approved(fx)
    assert row['form_data']['payment_institution_type'] == '厂家金融'
    assert row['form_data']['payment_bank'] == '合成汽金'
    for endpoint in ('print', 'gift-document/print'):
        for copy_kind in ('customer', 'internal'):
            for mode in ('full', 'overprint'):
                response = fx.client('finance').get(f'/api/business-records/contracts/{row["id"]}/{endpoint}',
                    params={'copy_kind': copy_kind, 'mode': mode})
                assert response.status_code == 200, response.text
                text = ''.join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
                assert '首次保养' not in text
                assert ('NPS' in text) == (copy_kind == 'internal')
                output = Path(os.environ['RECORD_PRICING_EVIDENCE']) / (endpoint.replace('/', '-') + '-' + copy_kind + '-' + mode + '.pdf')
                output.write_bytes(response.content)
    state = fx.call('finance', 'GET', f'/contracts/{row["id"]}/benefits')
    assert not state['history'] and all(item['remaining'] == item['total'] for item in state['items'])
    invoice = invoice_upload(fx, row)
    Path(os.environ['RECORD_PRICING_EVIDENCE'], 'frontend-data.json').write_text(json.dumps({
        'detail': fx.call('finance', 'GET', f'/contracts/{row["id"]}'),
        'benefits': state, 'invoice': invoice,
        'signed': fx.call('finance', 'GET', f'/contracts/{row["id"]}/signed-documents'),
        'catalog': fx.call('finance', 'GET', '/catalog'),
        'pricing': fx.catalog('sales'), 'sales_catalog': fx.call('sales', 'GET', '/catalog'),
    }, ensure_ascii=False), encoding='utf-8')
