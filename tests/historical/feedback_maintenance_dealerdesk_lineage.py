"""历史遗留：DealerDesk 反馈/维护线的测试，**不参与本目录测试集**。

为什么不能跑：它请求 `GET/POST /api/feedback` 与 `GET /api/maintenance/status`，而这两个接口在
huakangos 线里根本不存在（`app/` 下没有 feedback/maintenance 的 API 模块；`maintenance/` 目录是
另一套开发维护工具，不是这里的路由）。它此前让全量回归出现 11 项失败，因此按业主决定
（2026-09-24：标注历史遗留并移出测试集）改名并移入 `tests/historical/`。

恢复条件：如果确实要在本线做“员工反馈/维护开关”，需要单独设计（接口、岗位、状态机、审计、
与现有 business-assistant 问题清单的关系），再把本文件改回 `test_` 名称。
""""""意见收集必须在「自动维护关闭」时完全可用，并且绝不外发。

这些端点此前没有任何测试覆盖，而它们正是暂缓自动维护时唯一继续使用的功能。
关键安全属性：只要 MAINTENANCE_ENABLED 不为 true，即便员工勾选了外发授权，
意见也只能停留在 new，不会入队、不会调用模型、不会产生任何外发记录。
"""
import json
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app.db import SessionLocal
from app.main import app
from app.models import Feedback, MaintenanceEvent
from tests.conftest import login


@pytest.fixture
def sales():
    with TestClient(app) as client:
        login(client, 'sales')
        yield client


def payload(title='库存超龄提示不明显', description='希望超龄库存能有更醒目的提示', consent=False):
    return {'title': title, 'description': description, 'category': 'improvement',
            'consent_code_review': consent}


def test_submitting_feedback_works_with_maintenance_disabled(sales):
    """暂缓自动维护时，收集意见本身必须照常可用。"""
    response = sales.post('/api/feedback', json=payload())
    assert response.status_code == 201
    assert response.json()['status'] == 'new'
    assert sales.get('/api/feedback').json()['items'][0]['title'] == '库存超龄提示不明显'


def test_consent_never_queues_while_maintenance_disabled(client, monkeypatch):
    """勾选外发授权也不得入队；模型与维护进程不得被触发。"""
    monkeypatch.setenv('MAINTENANCE_ENABLED', 'false')
    response = client.post('/api/feedback', json=payload(consent=True))
    assert response.status_code == 201
    assert response.json()['status'] == 'new'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MaintenanceEvent)) == 0
        assert db.scalar(select(func.count()).select_from(Feedback)) == 1


def test_queue_requires_both_switch_and_consent(client, monkeypatch):
    monkeypatch.setenv('MAINTENANCE_ENABLED', 'true')
    with_consent = client.post('/api/feedback', json=payload(title='勾选授权的意见', consent=True))
    without_consent = client.post('/api/feedback', json=payload(title='未勾选授权的意见', consent=False))
    assert with_consent.json()['status'] == 'queued'
    assert without_consent.json()['status'] == 'new'


def test_employee_sees_only_own_feedback(client, sales):
    mine = sales.post('/api/feedback', json=payload()).json()
    owners = client.post('/api/feedback', json=payload(title='管理员提交的意见')).json()
    admin_ids = {r['id'] for r in client.get('/api/feedback').json()['items']}
    sales_ids = {r['id'] for r in sales.get('/api/feedback').json()['items']}
    assert {mine['id'], owners['id']} <= admin_ids
    assert mine['id'] in sales_ids and owners['id'] not in sales_ids


def test_only_admin_can_authorise_ai_processing(client, sales):
    row = sales.post('/api/feedback', json=payload()).json()
    assert sales.post(f"/api/feedback/{row['id']}/queue", json={}).status_code == 403
    assert client.post(f"/api/feedback/{row['id']}/queue", json={}).status_code == 200
    # 已入队的任务不能重复入队，避免重复计费
    assert client.post(f"/api/feedback/{row['id']}/queue", json={}).status_code == 409


def test_queue_refuses_rows_at_the_attempt_ceiling(client):
    row = client.post('/api/feedback', json=payload()).json()
    with SessionLocal() as db:
        stored = db.get(Feedback, row['id'])
        stored.status = 'manual'
        stored.attempts = 3
        db.commit()
    assert client.post(f"/api/feedback/{row['id']}/queue", json={}).status_code == 409


def test_daily_submission_limit_is_enforced(sales):
    for index in range(10):
        assert sales.post('/api/feedback', json=payload(title=f'意见{index}')).status_code == 201
    assert sales.post('/api/feedback', json=payload(title='第十一条')).status_code == 429


def test_feedback_response_hides_approval_token_and_container_output(client):
    """接口只回传派生后的摘要与通过标记，不回传令牌、原始补丁或容器输出。"""
    row = client.post('/api/feedback', json=payload(consent=True)).json()
    with SessionLocal() as db:
        stored = db.get(Feedback, row['id'])
        stored.approval_token_hash = 'deadbeef' * 8
        stored.approved_by = 'ou_approver_secret'
        stored.test_result = {'passed': True, 'tail': 'CONTAINER-STDOUT-MARKER', 'head_sha': 'b' * 40}
        stored.proposal = {'summary': '扩大卡片间距', 'files': ['web/style.css']}
        db.commit()
    body = next(r for r in client.get('/api/feedback').json()['items'] if r['id'] == row['id'])
    serialized = json.dumps(body, ensure_ascii=False)
    assert 'deadbeef' not in serialized
    assert 'CONTAINER-STDOUT-MARKER' not in serialized
    assert not isinstance(body.get('proposal'), dict) and not isinstance(body.get('test_result'), dict)
    # 只需要展示的部分是刻意保留的
    assert body['summary'] == '扩大卡片间距' and body['files'] == ['web/style.css']
    assert body['tests_passed'] is True


def test_maintenance_status_is_admin_only(client, sales, tmp_path, monkeypatch):
    monkeypatch.setenv('MAINT_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('MAINTENANCE_ENABLED', 'false')
    assert sales.get('/api/maintenance/status').status_code == 403
    body = client.get('/api/maintenance/status').json()
    assert body['enabled'] is False
    assert body['ready'] is False and body['paused'] is False and body['worker_running'] is False
    assert body['message']


def test_maintenance_status_survives_missing_stale_and_malformed_state(client, tmp_path, monkeypatch):
    monkeypatch.setenv('MAINT_RUNTIME_DIR', str(tmp_path))
    # 状态文件不存在：返回默认值，不能 500
    assert client.get('/api/maintenance/status').status_code == 200
    # 内容损坏：同样降级
    (tmp_path / 'status.json').write_text('not json at all', encoding='utf-8')
    assert client.get('/api/maintenance/status').status_code == 200
    # 启动器已停止更新：必须提示，不能继续显示「已就绪」
    (tmp_path / 'status.json').write_text(
        json.dumps({'ready': True, 'worker_running': True, 'updated_at': time.time() - 3600}), encoding='utf-8')
    body = client.get('/api/maintenance/status').json()
    assert body['ready'] is False and body['worker_running'] is False
    assert '超过30秒' in body['message']


def test_feedback_events_are_visible_to_owner_and_admin_only(client, sales):
    row = sales.post('/api/feedback', json=payload()).json()
    assert sales.get(f"/api/feedback/{row['id']}/events").status_code == 200
    assert client.get(f"/api/feedback/{row['id']}/events").status_code == 200
    with TestClient(app) as colleague:
        login(colleague, 'service')
        assert colleague.get(f"/api/feedback/{row['id']}/events").status_code == 404
        assert colleague.get('/api/feedback').json()['items'] == []
