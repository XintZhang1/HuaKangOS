"""V2.18 actual scoped APIs against external synthetic fixtures; no model calls."""
from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json
import pytest
from sqlalchemy import select, func
from test_delivery_api import delivery_fx, fx, login_secret, command, BASE, gift_upload, invoice_upload, confirm
from app.business_records_models import SalesContract, RecordContractCorrection, ContractReceipt
from app.business_record_delivery_models import RecordDelivery, RecordReturn, RecordRefund
from synthetic import VEHICLE_ROW


def approved(fx):
    body = fx.contract_body(fx.delivery_catalog, [{'price_id': fx.delivery_catalog['gifts'][0]['id'], 'quantity': 1}])
    body['customer_phone'] = '13812345678'
    body['form_data']['buyer_id_number'] = '420101199001015678'
    body['submission_data']['is_cash_vehicle'] = True
    row = fx.call('sales', 'POST', '/contracts', 201, json=body)
    row = fx.call('manager', 'POST', f'/contracts/{row["id"]}/manager-approve', json=command(version=row['version']))
    row = fx.call('general_manager', 'POST', f'/contracts/{row["id"]}/approve', json=command(version=row['version']))
    return row, body


def delivered(fx):
    row, body = approved(fx)
    invoice = invoice_upload(fx, row)
    gift = gift_upload(fx, row)
    confirm(fx, {**row, 'version': gift['contract_version']}, invoice['invoice']['version'])
    return fx.call('general_manager', 'GET', f'/contracts/{row["id"]}'), body, invoice, gift


def request_revision(fx, row, target=4, role='sales'):
    return fx.call('general_manager', 'POST', f'/contracts/{row["id"]}/corrections', 201,
        json=command(version=row['version'], target_user_id=target, target_role=role, note='客户核对交易更正'))


def test_delivered_correction_preserves_original_facts_and_masks_every_read(delivery_fx):
    fx = delivery_fx
    row, original_body, invoice, gift = delivered(fx)
    key = row['id']
    with fx.sessions() as db:
        frozen = deepcopy(db.get(SalesContract, key).approved_snapshot)
        delivery_fact = db.scalar(select(RecordDelivery).where(RecordDelivery.contract_id == key))
        old_delivery = (delivery_fact.id, delivery_fact.invoice_amount_cents, delivery_fact.confirmed_at)
    for role in ('sales', 'manager', 'finance'):
        view = fx.call(role, 'GET', f'/contracts/{key}')
        assert view['customer_phone'] == '138****5678'
        assert view['form_data']['buyer_id_number'] == '42010119900101****'
        assert view['vin'] == row['vin'] and view['privacy']['masked']
        assert '13812345678' not in json.dumps(view, ensure_ascii=False)
    assert fx.call('clerk', 'GET', f'/contracts/{key}')['customer_phone'] == original_body['customer_phone']
    assert fx.call('sales', 'GET', f'/customers/{row["customer_id"]}')['phone'] == '138****5678'
    assert fx.call('sales', 'GET', '/contracts?q=13812345678')['total'] == 0
    replay = fx.call('sales', 'POST', '/contracts', 201, json=original_body)
    assert replay['customer_phone'] == '138****5678'
    fx.call('finance', 'GET', f'/contracts/{key}/print', 403)
    fx.call('finance', 'GET', f'/contracts/{key}/invoice/files/{invoice["files"][0]["id"]}/download', 403)
    fx.call('manager', 'GET', f'/contracts/{key}/gift-document/files/{gift["gift_document"]["id"]}/download', 403)
    inv_view = fx.call('finance', 'GET', f'/contracts/{key}/invoice')
    assert all(not item['available'] for item in inv_view['files'])
    fx.call('finance', 'POST', f'/contracts/{key}/invoice/recognize', 403,
        json=command(version=inv_view['invoice']['version']))
    revision = request_revision(fx, row)
    offered = fx.call('sales', 'GET', f'/contracts/{key}/corrections')['items'][0]
    check = fx.call('sales', 'POST', '/pricing/gift-policy-check', json={
        'contract_id': key, 'correction_id': revision['id'],
        'vehicle_price_id': offered['draft_input']['vehicle_price_id'],
        'gift_items': offered['draft_input']['gift_items']})
    assert check['status'] == 'within_limit'
    body = command(**offered['draft_input'], version=offered['version'], note='付款改为贷款，售价更正')
    body['sale_price_cents'] = 11200000
    body['submission_data'].update(payment_method='贷款', down_payment_cents=3000000)
    submitted = fx.call('sales', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/submit', json=body)
    fx.call('sales', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/manager-approve', 403,
        json=command(version=submitted['version']))
    manager = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/manager-approve',
        json=command(version=submitted['version']))
    final = fx.call('general_manager', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/approve',
        json=command(version=manager['version']))
    assert final['status'] == 'approved' and final['sale_delta_cents'] == 200000
    # Business dates use Shanghai, regardless of the CI host's local date.
    # Derive from this approval, so a test spanning midnight/month-end stays stable.
    approved_day = datetime.fromisoformat(final['approved_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).date()
    assert final['cash_delta_cents'] == 200000 and final['approved_on'] == approved_day.isoformat()
    assert final['snapshot']['customer_phone'] == original_body['customer_phone']
    assert final['snapshot']['form_data']['buyer_id_number'] == original_body['form_data']['buyer_id_number']
    assert final['snapshot']['terms']['submission_data']['payment_method'] == '贷款'
    assert final['snapshot']['print_layout_version'] == 'full-v218'
    assert final['snapshot']['terms']['gifts_snapshot'][0]['unit_cost_cents'] == 4000
    with fx.sessions() as db:
        stored = db.get(SalesContract, key)
        assert stored.approved_snapshot == frozen and stored.sale_price_cents == 11000000
        fact = db.scalar(select(RecordDelivery).where(RecordDelivery.contract_id == key))
        assert (fact.id, fact.invoice_amount_cents, fact.confirmed_at) == old_delivery
        assert db.scalar(select(func.count()).select_from(SalesContract)) == 1
        assert db.scalar(select(func.count()).select_from(RecordDelivery)) == 1
        assert db.scalar(select(func.count()).select_from(ContractReceipt)) == 0
        revision_row = db.get(RecordContractCorrection, revision['id'])
        assert revision_row.approved_snapshot['terms']['price_snapshot']['gift_policy']['standard_gift_batch_id']
        revision_row.reason = 'illegal rewrite'
        with pytest.raises(Exception, match='已完成更正'):
            db.flush()
        db.rollback()
        revision_row = db.get(RecordContractCorrection, revision['id'])
        revision_row.status = 'draft'
        with pytest.raises(Exception, match='已完成更正'):
            db.flush()
        db.rollback()
    detail = fx.call('sales', 'GET', f'/contracts/{key}')
    assert detail['effective_contract']['sale_price_cents'] == 11200000
    assert detail['effective_contract']['customer_phone'] == '138****5678'
    assert detail['progress']['stages'][0]['actor_name'] == '合成-sales'


def test_assigned_peer_manager_special_review_and_archive_restore(delivery_fx):
    fx = delivery_fx
    row, _ = approved(fx)
    key = row['id']
    rev = request_revision(fx, row, 5)
    assert fx.call('sales_peer', 'GET', f'/contracts/{key}')['id'] == key
    offer = fx.call('sales_peer', 'GET', f'/contracts/{key}/corrections')['items'][0]
    body = command(**offer['draft_input'], version=offer['version'], note='低于限价，申请重审')
    body['sale_price_cents'] = 9000000
    sent = fx.call('sales_peer', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/submit', json=body)
    returned = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/reject',
        json=command(version=sent['version'], target_user_id=2, target_role='manager', note='转经理核对'))
    body = command(**returned['draft_input'], version=returned['version'], note='经理核对低价申请')
    sent = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/submit', json=body)
    assert sent['status'] == 'manager_approved'
    gm = fx.call('general_manager', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/approve',
        json=command(version=sent['version']))
    assert gm['status'] == 'deputy_pending'
    final = fx.call('deputy', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/deputy-approve',
        json=command(version=gm['version']))
    assert final['status'] == 'approved' and final['sale_delta_cents'] == -2000000
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    archived = fx.call('general_manager', 'POST', f'/contracts/{key}/archive',
        json=command(version=current['version'], note='转历史查询'))
    assert fx.call('general_manager', 'GET', '/contracts')['total'] == 0
    assert fx.call('general_manager', 'GET', '/contracts?include_history=true')['total'] == 1
    restored = fx.call('general_manager', 'POST', f'/contracts/{key}/restore', json=command(version=archived['version']))
    assert restored['archived_at'] is None and fx.call('general_manager', 'GET', '/contracts')['total'] == 1


def test_new_model_revision_catalog_binding_cancellation_and_return_exclusion(delivery_fx):
    fx = delivery_fx
    row, _, _, _ = delivered(fx)
    key = row['id']
    rev = request_revision(fx, row, 2, 'manager')
    fx.call('other_manager', 'GET', f'/contracts/{key}/corrections', 404)
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    fx.call('general_manager', 'POST', f'/contracts/{key}/returns', 409,
        json=command(version=current['version'], note='仍在更正中，不能退车'))
    uploaded = fx.upload()
    fx.publish('general_manager', 'vehicle', uploaded, [{**VEHICLE_ROW, 'model': '更正新车型', 'gift_policy': None}])
    catalog = fx.call('manager', 'GET', f'/pricing/catalog?contract_id={key}&correction_id={rev["id"]}')
    assert len(catalog['vehicles']) == 2
    new_price = next(item for item in catalog['vehicles'] if item['model'] == '更正新车型')
    check = fx.call('manager', 'POST', '/pricing/gift-policy-check', json={
        'contract_id': key, 'correction_id': rev['id'], 'vehicle_price_id': new_price['id'], 'gift_items': []})
    assert check['status'] == 'no_policy'
    body = command(**rev['draft_input'], version=rev['version'], note='更正实际车型和VIN')
    body.update(vehicle_price_id=new_price['id'], vin='SYNTHETIC-CHANGED-VIN', gift_items=[])
    sent = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/submit', json=body)
    final = fx.call('general_manager', 'POST', f'/contracts/{key}/corrections/{rev["id"]}/approve',
        json=command(version=sent['version']))
    assert final['snapshot']['model'].endswith('更正新车型') and final['snapshot']['vin'] == 'SYNTHETIC-CHANGED-VIN'
    prefill = fx.call('clerk', 'GET', f'/report-prefill?report_key=vehicle_details&contract_id={key}')
    from app.business_record_reports import CATALOG_BY_KEY
    model_key = next(item['key'] for item in CATALOG_BY_KEY['vehicle_details']['columns'] if item['label'] == '车型')
    assert prefill['values'][model_key].endswith('更正新车型')
    latest = fx.call('clerk', 'GET', f'/contracts/{key}')
    office = fx.call('clerk', 'PUT', f'/contracts/{key}/office-review', json=command(
        version=latest['version'], report_key='vehicle_details', values=prefill['values']))
    assert office['office_data']['contract_correction_id'] == rev['id']
    submitted_office = fx.call('clerk', 'POST', f'/contracts/{key}/office-submit',
        json=command(version=office['version']))
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    price_fix = request_revision(fx, current, 2, 'manager')
    body = command(**price_fix['draft_input'], version=price_fix['version'], note='再次核对合同售价')
    body['sale_price_cents'] += 10000
    sent = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{price_fix["id"]}/submit', json=body)
    fx.call('general_manager', 'POST', f'/contracts/{key}/corrections/{price_fix["id"]}/approve',
        json=command(version=sent['version']))
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    refusal = fx.call('general_manager', 'POST', f'/contracts/{key}/office-approve', 409,
        json=command(version=current['version']))
    assert '重新核价' in refusal['detail']
    with fx.sessions() as db:
        assert db.get(SalesContract, key).vin == row['vin']
        from app.business_record_inventory import _occupied
        from app.tenancy import set_scope
        set_scope(db, [1], 1)
        assert not _occupied(db, row['vin'].upper())
        assert _occupied(db, 'SYNTHETIC-CHANGED-VIN')
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    rev2 = request_revision(fx, current)
    moved = fx.call('general_manager', 'POST', f'/contracts/{key}/corrections/{rev2["id"]}/reassign',
        json=command(version=rev2['version'], target_user_id=5, target_role='sales', note='员工变更，交接更正'))
    assert moved['assigned_to'] == 5 and moved['events'][-1]['action'] == 'reassign'
    cancelled = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{rev2["id"]}/cancel',
        json=command(version=moved['version'], note='客户撤销本次更正'))
    assert cancelled['status'] == 'cancelled'
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    returned = fx.call('general_manager', 'POST', f'/contracts/{key}/returns',
        json=command(version=current['version'], note='办理真实退车'))
    assert returned['returns'][0]['status'] == 'approved'
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    fx.call('general_manager', 'POST', f'/contracts/{key}/corrections', 409,
        json=command(version=current['version'], target_user_id=2, target_role='manager', note='退车中禁止更正'))
    with fx.sessions() as db:
        set_scope(db, [1], 1)
        assert not _occupied(db, 'SYNTHETIC-CHANGED-VIN')


def test_legacy_completed_contract_can_correct_and_manager_keeps_manual_excess(delivery_fx):
    fx = delivery_fx
    row, original_body = approved(fx)
    key = row['id']
    # An external fixture representing a historical pre-catalog approval.
    with fx.sessions() as db:
        original = db.get(SalesContract, key)
        original.workflow_version = 'legacy-v2'
        original.cost_cents, original.profit_cents, original.priced_by = 10000000, 1000000, 10
        snapshot = deepcopy(original.approved_snapshot)
        snapshot.pop('terms', None)
        snapshot['workflow_version'] = 'legacy-v2'
        original.approved_snapshot = snapshot
        db.add(ContractReceipt(store_id=1, contract_id=key, actual_amount_cents=11000000,
            received_on=date(2026, 10, 12), confirmed_by=8))
        db.commit()
    row = fx.call('general_manager', 'GET', f'/contracts/{key}')
    assert 'correction_request' in row['actions']
    assert fx.call('sales', 'GET', f'/contracts/{key}')['privacy']['masked']
    revision = request_revision(fx, row)
    catalog = fx.call('sales', 'GET', f'/pricing/catalog?contract_id={key}&correction_id={revision["id"]}')
    assert catalog['vehicles']
    body = command(**{k: v for k, v in original_body.items() if k != 'request_id'},
        version=revision['version'], note='历史合同核对交易更正')
    body['sale_price_cents'] += 10000
    submitted = fx.call('sales', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/submit', json=body)
    manager = fx.call('manager', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/manager-approve',
        json=command(version=submitted['version'], gift_excess_cents=5000, note='经理确认其他赠品超价'))
    assert manager['snapshot']['terms']['special'] and manager['snapshot']['terms']['gift_excess_cents'] == 5000
    gm = fx.call('general_manager', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/approve',
        json=command(version=manager['version']))
    assert gm['status'] == 'deputy_pending'
    final = fx.call('deputy', 'POST', f'/contracts/{key}/corrections/{revision["id"]}/deputy-approve',
        json=command(version=gm['version']))
    assert final['status'] == 'approved'
    with fx.sessions() as db:
        original = db.get(SalesContract, key)
        assert original.workflow_version == 'legacy-v2' and original.approved_snapshot == snapshot
        assert db.scalar(select(func.count()).select_from(ContractReceipt)) == 1
        assert db.scalar(select(func.count()).select_from(RecordDelivery)) == 0


def test_manager_return_finance_handoff_void_visibility_and_partial_refunds(delivery_fx):
    fx = delivery_fx
    row, original_body, _, _ = delivered(fx)
    key = row['id']
    assert fx.call('finance', 'GET', '/contracts?workbench=finance&work_status=pending')['total'] == 0
    for role in ('sales', 'manager', 'admin', 'finance', 'clerk', 'deputy', 'store_admin'):
        detail = fx.call(role, 'GET', f'/contracts/{key}')
        assert 'request_return' not in detail['delivery_state']['actions']
        assert 'archive' not in detail['actions']
        fx.call(role, 'POST', f'/contracts/{key}/returns', 403,
            json=command(version=row['version'], note='无权岗位退车'))
        fx.call(role, 'POST', f'/contracts/{key}/archive', 403,
            json=command(version=row['version'], note='无权岗位作废'))
    fx.call('other_general_manager', 'POST', f'/contracts/{key}/returns', 404,
        json=command(version=row['version'], note='跨店不可退车'))
    return_body = command(version=row['version'], requested_refund_cents=6000, note='总经理核对实际退车')
    returned = fx.call('general_manager', 'POST', f'/contracts/{key}/returns', json=return_body)
    item = returned['returns'][0]
    assert item['status'] == 'approved' and item['requested_by'] == item['reviewed_by'] == 3
    assert item['refund_registration_status'] == 'pending' and returned['pending_refund']
    assert fx.call('general_manager', 'POST', f'/contracts/{key}/returns', json=return_body) == returned
    pending = fx.call('finance', 'GET', '/contracts?workbench=finance&work_status=pending')
    assert pending['total'] == 1 and pending['items'][0]['progress']['pending_role'] == 'finance'
    assert pending['items'][0]['progress']['pending_people'] == [{'id': 8, 'name': '合成-finance'}]
    with fx.sessions() as db:
        saved = db.get(RecordReturn, item['id'])
        assert saved.reversal_snapshot['sale_price_cents'] == row['sale_price_cents']
        assert saved.reversal_snapshot['submission_data']['is_cash_vehicle'] is True
        assert db.scalar(select(func.count()).select_from(RecordDelivery)) == 1
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    fx.call('general_manager', 'POST', f'/contracts/{key}/returns', 409,
        json=command(version=current['version'], note='不得重复退车'))
    archived = fx.call('general_manager', 'POST', f'/contracts/{key}/archive',
        json=command(version=current['version'], note='作废并保留退款办理记录'))
    assert fx.call('sales', 'GET', '/contracts?include_history=true')['total'] == 0
    for path in (f'/contracts/{key}', f'/contracts/{key}/delivery-state',
                 f'/contracts/{key}/corrections', f'/pricing/catalog?contract_id={key}'):
        fx.call('sales', 'GET', path, 404)
    fx.call('sales', 'POST', '/contracts', 404, json=original_body)
    assert fx.call('sales', 'GET', f'/customers/{row["customer_id"]}')['contract_count'] == 0
    assert fx.call('finance', 'GET', '/contracts?workbench=finance&work_status=pending')['total'] == 1
    for role in ('admin', 'manager', 'deputy', 'finance'):
        fx.call(role, 'POST', f'/contracts/{key}/restore', 403,
            json=command(version=archived['version']))
    refund_path = f'/contracts/{key}/returns/{item["id"]}/refund'
    first_body = command(version=item['version'], amount_cents=1000, refunded_on=item['approved_on'])
    fx.call('general_manager', 'POST', refund_path, 403, json=first_body)
    first = fx.call('finance', 'POST', refund_path, json=first_body)
    assert fx.call('finance', 'POST', refund_path, json=first_body) == first
    assert first['returns'][0]['refund_registration_status'] == 'registered' and not first['pending_refund']
    assert first['returns'][0]['refunded_amount_cents'] == 1000
    assert fx.call('finance', 'GET', '/contracts?workbench=finance&work_status=pending')['total'] == 0
    processed = fx.call('finance', 'GET', '/contracts?workbench=finance&work_status=processed&include_history=true')
    assert processed['total'] == 1
    assert processed['items'][0]['progress']['pending_label'] == '已登记退款，可继续追加'
    assert processed['items'][0]['delivery_state']['returns'][0]['actions'] == ['refund']
    second = fx.call('finance', 'POST', refund_path, json=command(version=first['returns'][0]['version'],
        amount_cents=2000, refunded_on=item['approved_on']))
    assert second['returns'][0]['refunded_amount_cents'] == 3000
    current = fx.call('general_manager', 'GET', f'/contracts/{key}')
    fx.call('general_manager', 'POST', f'/contracts/{key}/restore', json=command(version=current['version']))
    assert fx.call('sales', 'GET', f'/contracts/{key}')['id'] == key
    with fx.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RecordReturn)) == 1
        assert db.scalar(select(func.count()).select_from(RecordRefund)) == 2
        assert db.get(SalesContract, key).approved_snapshot['sale_price_cents'] == row['sale_price_cents']


def test_historical_return_review_stays_independent_and_rejected_contract_visible(delivery_fx):
    fx = delivery_fx
    row, _, _, _ = delivered(fx)
    key = row['id']
    # Historical pending requests are preserved, not converted by migration.
    with fx.sessions() as db:
        delivery = db.scalar(select(RecordDelivery).where(RecordDelivery.contract_id == key))
        old = RecordReturn(store_id=1, contract_id=key, delivery_id=delivery.id,
            requested_by=3, note='历史本人申请不得自批')
        db.add(old); db.commit()
        old_id = old.id
    old = fx.call('general_manager', 'GET', f'/contracts/{key}/delivery-state')['returns'][0]
    assert not old['actions']
    fx.call('general_manager', 'POST', f'/contracts/{key}/returns/{old_id}/approve', 403,
        json=command(version=old['version']))
    with fx.sessions() as db:
        db.get(RecordReturn, old_id).requested_by = 4
        db.commit()
    old = fx.call('general_manager', 'GET', f'/contracts/{key}/delivery-state')['returns'][0]
    assert old['actions'] == ['approve', 'reject']
    fx.call('admin', 'POST', f'/contracts/{key}/returns/{old_id}/approve', 403,
        json=command(version=old['version']))
    approved_old = fx.call('general_manager', 'POST', f'/contracts/{key}/returns/{old_id}/approve',
        json=command(version=old['version']))
    assert approved_old['pending_refund'] and approved_old['returns'][0]['status'] == 'approved'
    body = fx.contract_body(fx.delivery_catalog, [])
    draft = fx.call('sales', 'POST', '/contracts', 201, json=body)
    rejected = fx.call('manager', 'POST', f'/contracts/{draft["id"]}/reject',
        json=command(version=draft['version'], note='请销售补充合同资料'))
    visible = fx.call('sales', 'GET', '/contracts')
    assert any(item['id'] == rejected['id'] and 'edit' in item['actions'] for item in visible['items'])
