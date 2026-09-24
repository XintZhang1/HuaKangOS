"""评审申请：只解决权限/额度不足；依据是系统自己记下的被挡记录，收件人由服务端定。"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, utcnow
from app.escalation_models import Refusal
from app.escalation_service import record_refusal
from app.main import app
from app.models import Store, User, UserStore
from app.security import hash_password
from tests.conftest import PASSWORD, login

SUBJECT = {'subject': '给这张单批准 5% 折扣', 'case_reference': 'XC-R09-01'}


def add_user(username, role, store_id=1, store_role=None):
    with SessionLocal() as db:
        user = User(username=username, display_name=username, role=role,
                    password_hash=hash_password(PASSWORD), must_change_password=False)
        db.add(user)
        db.flush()
        db.add(UserStore(user_id=user.id, store_id=store_id, role=store_role))
        db.commit()
        return user.id


def seed_refusal(username, message='没有此模块的操作权限', category_store=1, role='sales', hours_ago=0):
    """记一条被挡记录，与接口中间件写入的方式相同（用于没有真实接口可触发的岗位）。"""
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        row = record_refusal(db, store_id=category_store, user=user, method='POST',
                             path='/api/flow/cases/1/actions/approve', status_code=403, message=message)
        if hours_ago:
            row.created_at = utcnow() - timedelta(hours=hours_ago)
        db.commit()
        return row.id


def blocked(client, path='/api/audit'):
    """先按页面提示办理一次，被系统挡住——中间件就是这样记下被挡记录的。"""
    response = client.get(path)
    assert response.status_code == 403, response.text
    items = client.get('/api/escalations/refusals').json()['items']
    assert items, 'a real refusal must produce a receipt'
    return items[0]


def submit(client, refusal_id=None, **overrides):
    if refusal_id is None:
        refusal_id = blocked(client)['id']
    return client.post('/api/escalations', json={**SUBJECT, 'refusal_id': refusal_id, **overrides})


def test_employee_submits_and_only_the_store_manager_receives_it(client):
    login(client, 'sales')
    receipt = blocked(client)
    assert receipt['category'] == 'authority' and receipt['operation_id'] == 'GET /api/audit'
    created = submit(client, refusal_id=receipt['id'])
    assert created.status_code == 201, created.text
    row = created.json()
    assert row['status'] == 'open' and row['target_role'] == 'manager'
    assert row['requester_role'] == 'sales' and row['status_label'] == '待处理'
    # The server wrote the operation and the system message from its own record.
    assert row['operation_id'] == 'GET /api/audit' and row['blocked_message'] == receipt['message']
    assert [event['action'] for event in row['events']] == ['submit']
    assert [item['id'] for item in client.get('/api/escalations?scope=mine').json()['items']] == [row['id']]
    # The requester cannot see a review queue at all.
    assert client.get('/api/escalations?scope=to_review').status_code == 403
    # A group administrator does not take the store manager's queue.
    login(client, 'admin')
    assert client.get('/api/escalations?scope=to_review').json()['items'] == []
    login(client, 'manager')
    queue = client.get('/api/escalations?scope=to_review').json()['items']
    assert [item['id'] for item in queue] == [row['id']]
    # The receipt is spent: one refusal can justify one request.
    login(client, 'sales')
    assert client.get('/api/escalations/refusals').json()['items'] == []


def test_the_system_decides_the_category_not_the_submitter(client):
    login(client, 'sales')
    receipt = blocked(client)
    mismatch = submit(client, refusal_id=receipt['id'], reason_category='amount')
    assert mismatch.status_code == 422 and '请按系统记录提交' in mismatch.json()['detail']
    assert client.get('/api/escalations?scope=mine').json()['items'] == []
    ok = submit(client, refusal_id=receipt['id'], reason_category='authority')
    assert ok.status_code == 201 and ok.json()['reason_category'] == 'authority'


def test_a_business_rule_refusal_cannot_be_escalated(client):
    login(client, 'sales')
    # Refused for policy, not for authority: this must not become a review request.
    policy = client.post('/api/branding/photo', files={'file': ('x.png', b'not-an-image', 'image/png')})
    assert policy.status_code == 403 and '请联系系统管理员' in policy.json()['detail']
    receipts = client.get('/api/escalations/refusals').json()['items']
    assert receipts and receipts[0]['category'] == 'rule'
    refused = submit(client, refusal_id=receipts[0]['id'], subject='想自己更换登录图片')
    assert refused.status_code == 422
    assert '业务规则' in refused.json()['detail'] and '不能通过评审绕过' in refused.json()['detail']
    assert client.get('/api/escalations?scope=mine').json()['items'] == []


def test_a_receipt_cannot_be_borrowed_reused_or_kept_for_later(client):
    login(client, 'sales')
    first = blocked(client)['id']
    assert submit(client, refusal_id=first).status_code == 201
    reused = submit(client, refusal_id=first, subject='再用一次这条被挡记录')
    assert reused.status_code == 409 and '已经用过' in reused.json()['detail']
    # Somebody else's refusal is not evidence for me.
    login(client, 'service')
    other = submit(client, refusal_id=first, subject='拿同事的被挡记录来提交')
    assert other.status_code == 404
    # An old refusal is stale.
    stale = seed_refusal('service', hours_ago=25)
    old = submit(client, refusal_id=stale, subject='用昨天的被挡记录提交')
    assert old.status_code == 409 and '重新在页面办理' in old.json()['detail']


def test_incomplete_or_unknown_requests_are_refused(client):
    login(client, 'sales')
    receipt = blocked(client)['id']
    assert submit(client, refusal_id=receipt, subject='折扣').status_code == 422
    assert submit(client, refusal_id=999999).status_code == 404
    assert client.post('/api/escalations', json=SUBJECT).status_code == 422      # no refusal cited
    assert client.post('/api/escalations', json={**SUBJECT, 'refusal_id': 0}).status_code == 422
    assert client.get('/api/escalations?scope=mine').json()['items'] == []


def test_the_same_request_is_not_submitted_twice(client):
    login(client, 'sales')
    assert submit(client).status_code == 201
    again = submit(client)
    assert again.status_code == 409 and '已经提交过' in again.json()['detail']
    assert len(client.get('/api/escalations?scope=mine').json()['items']) == 1


def test_a_manager_request_goes_to_the_group_administrator_and_is_not_self_approved(client):
    login(client, 'manager')
    receipt = seed_refusal('manager', message='店长没有批准该额度折扣的权限')
    created = submit(client, refusal_id=receipt, subject='给这张单批准 8% 折扣')
    assert created.status_code == 201 and created.json()['target_role'] == 'admin'
    row = created.json()
    assert client.get('/api/escalations?scope=to_review').json()['items'] == []
    own = client.post('/api/escalations/%d/actions/done' % row['id'],
                      json={'version': row['version'], 'note': '自己批准自己'})
    assert own.status_code == 403 and '不能自己批准' in own.json()['detail']
    login(client, 'admin')
    assert [item['id'] for item in client.get('/api/escalations?scope=to_review').json()['items']] == [row['id']]


def test_the_store_role_decides_the_reviewer_queue(client):
    """门店岗位与账号岗位不同时，按当前门店岗位判定（权限本来就是按门店给的）。"""
    add_user('esc-account-sales-store-manager', 'sales', store_role='manager')
    add_user('esc-account-manager-store-sales', 'manager', store_role='sales')
    login(client, 'esc-account-sales-store-manager')
    # This account is the store's manager: it may review, but its own request goes to the group.
    with SessionLocal() as db:
        requester = db.query(User).filter(User.username == 'sales').one()
        mine = record_refusal(db, store_id=1, user=requester, method='GET', path='/api/audit',
                              status_code=403, message='没有查看全店审计日志的权限')
        db.commit()
        mine_id = mine.id
    login(client, 'sales')
    row = submit(client, refusal_id=mine_id).json()
    login(client, 'esc-account-sales-store-manager')
    assert client.get('/api/escalations?scope=to_review').status_code == 200
    assert [item['id'] for item in client.get('/api/escalations?scope=to_review').json()['items']] == [row['id']]
    assert client.post('/api/escalations/%d/actions/claim' % row['id'],
                       json={'version': row['version']}).status_code == 200
    # An account-level manager who is only a salesperson in this store must not take that queue,
    # and their own request is routed to the store manager, not to the group administrator.
    login(client, 'esc-account-manager-store-sales')
    assert client.get('/api/escalations?scope=to_review').status_code == 403


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


def test_the_refusal_list_only_carries_my_own_open_receipts(client):
    login(client, 'sales')
    mine = blocked(client)['id']
    login(client, 'service')
    blocked(client)
    assert [item['id'] for item in client.get('/api/escalations/refusals').json()['items']] != [mine]
    assert all(item['id'] != mine for item in client.get('/api/escalations/refusals').json()['items'])
    with SessionLocal() as db:
        assert db.query(Refusal).count() == 2


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
    # The original refusal is unchanged and still enforced.
    refused = client.post('/api/users/batch', json={'store_id': 1, 'password': 'Xc-Trial-Password-01',
                                                    'rows': [{'username': 'esc-new', 'display_name': '评审新员工',
                                                              'role': 'sales'}]})
    assert refused.status_code == 403 and '仅系统管理员' in refused.json()['detail']
