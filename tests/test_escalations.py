"""评审申请：只解决权限/额度不足，收件人由服务端定，上级本人在原页面办理。"""
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Store, User, UserStore
from app.security import hash_password
from tests.conftest import PASSWORD, login

BODY = {'subject': '给这张单批准 5% 折扣', 'case_reference': 'XC-R09-01',
        'blocked_message': '没有该模块的操作权限，请联系店长', 'reason_category': 'authority'}


def submit(client, **overrides):
    return client.post('/api/escalations', json={**BODY, **overrides})


def add_user(username, role, store_id=1):
    with SessionLocal() as db:
        user = User(username=username, display_name=username, role=role,
                    password_hash=hash_password(PASSWORD), must_change_password=False)
        db.add(user)
        db.flush()
        db.add(UserStore(user_id=user.id, store_id=store_id))
        db.commit()
        return user.id


def test_employee_submits_and_the_store_manager_receives_it(client):
    login(client, 'sales')
    created = submit(client)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row['status'] == 'open' and row['target_role'] == 'manager'
    assert row['requester_role'] == 'sales' and row['status_label'] == '待处理'
    assert [event['action'] for event in row['events']] == ['submit']
    assert [item['id'] for item in client.get('/api/escalations?scope=mine').json()['items']] == [row['id']]
    # The requester cannot see a review queue at all.
    assert client.get('/api/escalations?scope=to_review').status_code == 403
    login(client, 'manager')
    queue = client.get('/api/escalations?scope=to_review').json()['items']
    assert [item['id'] for item in queue] == [row['id']]
    assert queue[0]['blocked_message'] == BODY['blocked_message']


def test_a_business_rule_refusal_cannot_be_escalated(client):
    login(client, 'sales')
    refused = submit(client, subject='想跳过质检直接交车', blocked_message='检查不合格，禁止出库', reason_category='rule')
    assert refused.status_code == 422
    assert '不能通过评审绕过' in refused.json()['detail']
    assert client.get('/api/escalations?scope=mine').json()['items'] == []


@pytest.mark.parametrize('overrides', [
    {'subject': '折扣'},
    {'blocked_message': '没有权限'},
    {'operation_id': 'POST https://example.org/steal'},
])
def test_incomplete_or_unsafe_requests_are_refused(client, overrides):
    login(client, 'sales')
    assert submit(client, **overrides).status_code == 422
    assert client.get('/api/escalations?scope=mine').json()['items'] == []


def test_the_same_request_is_not_submitted_twice(client):
    login(client, 'sales')
    assert submit(client).status_code == 201
    again = submit(client)
    assert again.status_code == 409 and '已经提交过' in again.json()['detail']
    assert len(client.get('/api/escalations?scope=mine').json()['items']) == 1


def test_a_manager_request_goes_to_the_group_administrator_and_is_not_self_approved(client):
    login(client, 'manager')
    created = submit(client, subject='给这张单批准 8% 折扣')
    assert created.status_code == 201 and created.json()['target_role'] == 'admin'
    row = created.json()
    assert client.get('/api/escalations?scope=to_review').json()['items'] == []
    own = client.post('/api/escalations/%d/actions/done' % row['id'],
                      json={'version': row['version'], 'note': '自己批准自己'})
    assert own.status_code == 403 and '不能自己批准' in own.json()['detail']
    login(client, 'admin')
    assert [item['id'] for item in client.get('/api/escalations?scope=to_review').json()['items']] == [row['id']]


def test_only_the_reviewer_role_can_claim_and_decide(client):
    login(client, 'sales')
    row = submit(client).json()
    assert client.post('/api/escalations/%d/actions/claim' % row['id'],
                       json={'version': row['version']}).status_code == 403
    login(client, 'service')
    assert client.get('/api/escalations?scope=to_review').status_code == 403
    login(client, 'manager')
    claimed = client.post('/api/escalations/%d/actions/claim' % row['id'], json={'version': row['version']})
    assert claimed.status_code == 200 and claimed.json()['status'] == 'claimed'
    version = claimed.json()['version']
    assert client.post('/api/escalations/%d/actions/claim' % row['id'],
                       json={'version': version}).status_code == 409
    assert client.post('/api/escalations/%d/actions/done' % row['id'],
                       json={'version': version, 'note': '好'}).status_code == 422
    done = client.post('/api/escalations/%d/actions/done' % row['id'],
                       json={'version': version, 'note': '已在原单批准并办理'})
    assert done.status_code == 200
    body = done.json()
    assert body['status'] == 'done' and body['decision_note'] == '已在原单批准并办理'
    assert [event['action'] for event in body['events']] == ['submit', 'claim', 'done']
    # Finished requests refuse further decisions.
    assert client.post('/api/escalations/%d/actions/reject' % row['id'],
                       json={'version': body['version'], 'note': '再驳回一次'}).status_code == 409


def test_reject_and_cancel_flows(client):
    login(client, 'sales')
    row = submit(client).json()
    login(client, 'manager')
    rejected = client.post('/api/escalations/%d/actions/reject' % row['id'],
                           json={'version': row['version'], 'note': '金额在店长权限内，请直接按规则办理'})
    assert rejected.status_code == 200 and rejected.json()['status'] == 'rejected'
    login(client, 'sales')
    cancelled = client.post('/api/escalations/%d/actions/cancel' % row['id'],
                            json={'version': rejected.json()['version']})
    assert cancelled.status_code == 409                      # already decided
    fresh = submit(client, subject='另一张单需要店长批准').json()
    assert client.post('/api/escalations/%d/actions/cancel' % fresh['id'],
                       json={'version': fresh['version']}).status_code == 200
    assert client.get('/api/escalations?scope=mine&status=cancelled').json()['items']
    # Nobody else may cancel somebody else's request.
    other = submit(client, subject='第三张单需要店长批准').json()
    login(client, 'service')
    assert client.post('/api/escalations/%d/actions/cancel' % other['id'],
                       json={'version': other['version']}).status_code == 403


def test_a_stale_version_is_reported_instead_of_overwriting(client):
    login(client, 'sales')
    row = submit(client).json()
    login(client, 'manager')
    assert client.post('/api/escalations/%d/actions/claim' % row['id'],
                       json={'version': row['version']}).status_code == 200
    login(client, 'admin')
    stale = client.post('/api/escalations/%d/actions/reject' % row['id'],
                        json={'version': row['version'], 'note': '用旧版本处理'})
    assert stale.status_code == 409 and '刷新' in stale.json()['detail']


def test_another_store_cannot_see_or_touch_the_request(client):
    login(client, 'sales')
    row = submit(client).json()
    with SessionLocal() as db:
        db.add(Store(id=9, code='ESC2', name='评审第二店'))
        db.commit()
    add_user('esc-manager-two', 'manager', store_id=9)
    with TestClient(app) as other:
        login(other, 'esc-manager-two', PASSWORD)
        other.headers['X-Store-ID'] = '9'
        assert other.get('/api/escalations?scope=to_review').json()['items'] == []
        assert other.post('/api/escalations/%d/actions/claim' % row['id'],
                          json={'version': row['version']}).status_code == 404


def test_an_escalation_never_changes_permissions_or_business_data(client):
    from app.flow_models import Case, StockMove
    from app.models import CashEntry
    login(client, 'sales')
    before = client.get('/api/auth/me').json()
    row = submit(client).json()
    login(client, 'manager')
    client.post('/api/escalations/%d/actions/done' % row['id'],
                json={'version': row['version'], 'note': '已在原页面办理'})
    login(client, 'sales')
    after = client.get('/api/auth/me').json()
    assert after['role'] == before['role'] and after['write_modules'] == before['write_modules']
    with SessionLocal() as db:
        assert db.query(Case).count() == 0
        assert db.query(CashEntry).count() == 0
        assert db.query(StockMove).count() == 0
    # The queue is empty for the requester and the original refusal is unchanged.
    refused = client.post('/api/users/batch', json={'store_id': 1, 'password': 'Xc-Trial-Password-01',
                                                    'rows': [{'username': 'esc-new', 'display_name': '评审新员工',
                                                              'role': 'sales'}]})
    assert refused.status_code == 403 and '仅系统管理员' in refused.json()['detail']
