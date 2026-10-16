"""GM/deputy parity through scoped APIs; approval identities remain independent."""
from test_delivery_api import delivery_fx, fx, login_secret, command, BASE, gift_upload, invoice_upload, confirm
from app.models import User, UserStore


def _open(fx, *, sale_price=11000000):
    body = fx.contract_body(fx.delivery_catalog,
        [{'price_id': fx.delivery_catalog['gifts'][0]['id'], 'quantity': 1}])
    body['sale_price_cents'] = sale_price
    row = fx.call('sales', 'POST', '/contracts', 201, json=body)
    return fx.call('manager', 'POST', f'/contracts/{row["id"]}/manager-approve',
        json=command(version=row['version'], note='合成销售经理核对'))


def test_deputy_has_general_manager_reads_writes_and_current_store_scope(delivery_fx):
    fx = delivery_fx
    gm = fx.call('general_manager', 'GET', '/catalog')
    deputy = fx.call('deputy', 'GET', '/catalog')
    assert {k: v for k, v in gm['capabilities'].items() if k != 'deputy_approve'} == {
        k: v for k, v in deputy['capabilities'].items() if k != 'deputy_approve'}
    assert deputy['capabilities']['deputy_approve'] is True
    assert deputy['reports'] == gm['reports']
    assert fx.catalog('deputy')['gifts'] == fx.catalog('general_manager')['gifts']
    assert fx.call('deputy', 'GET', '/inventory/catalog')['can_upload'] is True
    assert fx.call('deputy', 'GET', '/wholesale-channels')['can_manage'] is True
    # Upload permission does not bypass the original uploader's publication gate.
    uploaded = fx.upload('deputy')
    fx.call('general_manager', 'POST', f'/pricing/uploads/{uploaded["id"]}/recognize', 403,
        json=command(version=uploaded['version']))
    settings = fx.call('deputy', 'GET', '/settings')
    fx.call('deputy', 'PUT', '/settings', json=command(version=settings['version']))
    row = _open(fx)
    key = row['id']
    view = fx.call('deputy', 'GET', f'/contracts/{key}')
    assert 21 in {person['id'] for person in view['progress']['pending_people']}
    assert 'approve' in view['actions'] and 'office_data' in view
    assert view['terms']['gifts_snapshot'][0]['unit_cost_cents'] == 4000
    approved = fx.call('deputy', 'POST', f'/contracts/{key}/approve',
        json=command(version=row['version']))
    assert approved['status'] == 'approved' and approved['general_manager_approved_by'] == 21
    assert fx.call('deputy', 'GET', f'/contracts/{key}/accessory-sales') == fx.call(
        'general_manager', 'GET', f'/contracts/{key}/accessory-sales')
    invoice = invoice_upload(fx, approved)
    assert fx.call('deputy', 'GET', f'/contracts/{key}/invoice')['invoice']['id'] == invoice['invoice']['id']
    gift = gift_upload(fx, approved)
    delivered = confirm(fx, {**approved, 'version': gift['contract_version']}, invoice['invoice']['version'])
    assert len(fx.call('deputy', 'GET', '/delivery-notices')['items']) == 1
    saved = fx.call('clerk', 'PUT', f'/contracts/{key}/office-review',
        json=command(version=delivered['contract_version'], report_key='vehicle_details', values={}))
    submitted = fx.call('clerk', 'POST', f'/contracts/{key}/office-submit',
        json=command(version=saved['version']))
    reviewed = fx.call('deputy', 'POST', f'/contracts/{key}/office-approve',
        json=command(version=submitted['version']))
    assert reviewed['office_status'] == 'approved' and reviewed['office_approved_by'] == 21
    # Both jobs receive the same full dashboard and source report projection.
    path = '/dashboard-panels?mode=monthly&day=2026-10-16'
    deputy_dashboard, gm_dashboard = fx.call('deputy', 'GET', path), fx.call('general_manager', 'GET', path)
    # This field is response generation time, not a business-source timestamp.
    assert {k: v for k, v in deputy_dashboard.items() if k != 'updated_at'} == {
        k: v for k, v in gm_dashboard.items() if k != 'updated_at'}
    assert fx.call('deputy', 'GET', '/reports?report=operating_profit_v218') == fx.call(
        'general_manager', 'GET', '/reports?report=operating_profit_v218')
    returned = fx.call('deputy', 'POST', f'/contracts/{key}/returns',
        json=command(version=reviewed['version'], requested_refund_cents=10000, note='合成退车确认'))
    assert returned['returns'][0]['status'] == 'approved'
    archived = fx.call('deputy', 'POST', f'/contracts/{key}/archive',
        json=command(version=returned['contract_version'], note='合成作废核对'))
    assert archived['actions'] == ['restore']
    fx.call('deputy', 'POST', f'/contracts/{key}/restore', json=command(version=archived['version']))
    # Global deputy retains all enabled-store membership; IDs never cross the selected store.
    fx.call('deputy', 'GET', f'/contracts/{key}', 404, headers={'X-Store-ID': '2'})
    blocked = fx.call('deputy', 'POST', f'/contracts/{key}/archive', 409,
        headers={'X-Store-ID': 'all'}, json=command(version=archived['version'], note='不可集团写入'))
    assert '汇总为只读' in blocked['detail']
    # Account default never grants deputy powers where the current store job is sales.
    with fx.sessions() as db:
        db.add(User(id=22, username='synthetic_local_deputy', display_name='合成门店副总', role='sales',
            password_hash=db.get(User, 1).password_hash, must_change_password=False, active=True))
        db.flush()
        db.add_all([UserStore(user_id=22, store_id=1, role='group_deputy_manager'),
                    UserStore(user_id=22, store_id=2, role='sales')])
        db.commit()
    assert fx.call('local_deputy', 'GET', '/catalog')['capabilities']['approve'] is True
    other = fx.call('local_deputy', 'GET', '/catalog', headers={'X-Store-ID': '2'})
    assert other['capabilities']['approve'] is False and other['capabilities']['read_internal'] is False


def test_deputy_cannot_approve_two_contract_or_correction_stages(delivery_fx):
    fx = delivery_fx
    opened = _open(fx, sale_price=9900000)
    key = opened['id']
    gm_stage = fx.call('deputy', 'POST', f'/contracts/{key}/approve',
        json=command(version=opened['version']))
    assert gm_stage['status'] == 'deputy_pending'
    assert 'deputy_approve' not in gm_stage['actions'] and 'reject' not in gm_stage['actions']
    assert 21 not in {person['id'] for person in gm_stage['progress']['pending_people']}
    fx.call('deputy', 'POST', f'/contracts/{key}/deputy-approve', 403,
        json=command(version=gm_stage['version']))
    fx.call('deputy', 'POST', f'/contracts/{key}/reject', 409,
        json=command(version=gm_stage['version'], note='不可自审退回'))
    approved = fx.call('admin', 'POST', f'/contracts/{key}/deputy-approve',
        json=command(version=gm_stage['version']))
    assert approved['general_manager_approved_by'] == 21 and approved['deputy_approved_by'] == 1
    revision = fx.call('deputy', 'POST', f'/contracts/{key}/corrections', 201,
        json=command(version=approved['version'], target_user_id=4, target_role='sales', note='合成更正核对'))
    draft = fx.call('sales', 'GET', f'/contracts/{key}/corrections')['items'][0]
    body = command(**draft['draft_input'], version=draft['version'], note='合成低价更正')
    body['sale_price_cents'] = 9800000
    path = f'/contracts/{key}/corrections/{revision["id"]}'
    submitted = fx.call('sales', 'POST', path + '/submit', json=body)
    manager = fx.call('manager', 'POST', path + '/manager-approve',
        json=command(version=submitted['version'], note='合成特殊更正核对'))
    gm_stage = fx.call('deputy', 'POST', path + '/approve', json=command(version=manager['version']))
    assert gm_stage['status'] == 'deputy_pending' and 'deputy_approve' not in gm_stage['actions']
    fx.call('deputy', 'POST', path + '/deputy-approve', 403, json=command(version=gm_stage['version']))
    final = fx.call('admin', 'POST', path + '/deputy-approve', json=command(version=gm_stage['version']))
    assert final['status'] == 'approved'
