"""M8.1 补验：维修交车、仓储盘点过账、跨店授权的真实原接口事实与中文等待文案。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from uuid import uuid4
from fastapi import HTTPException
from app.main import app  # 与原 HTTP 应用相同的模型初始化顺序，再导入领域适配器
from app.db import SessionLocal
from app.assistant_runtime_labels import WAIT_REASONS, waiting_label
from app.assistant_runtime_schemas import BusinessObjectRef, PlanStepView, WorkspaceItem
from app.assistant_runtime_domains.customer_care import CustomerCareAdapter
from app.assistant_runtime_domains.dossier_grant import DossierGrantAdapter
from app.assistant_runtime_domains.repair_order import RepairOrderAdapter
from app.assistant_runtime_domains.warehouse_document import (WH_FACTS, WarehouseDocumentAdapter,
                                                             count_purpose)
import test_procurement_repair_facts as shared


GRANT = BusinessObjectRef(type='dossier_grant', id=9)
CASE = BusinessObjectRef(type='case', id=7)


def run_fact(adapter, ref, key, principal=None):
    return asyncio.run(adapter.fact_snapshot(principal or SimpleNamespace(store_id=1), ref, key))


def reader(data, status=200):
    async def read(operation, **kwargs):
        return {'status': status, 'data': data}
    return read


class WaitLabelText(unittest.TestCase):
    """内部等待标识必须有固定中文文案，且由服务器下发而不是前端翻译。"""

    def test_every_registered_wait_reason_has_chinese_text(self):
        for reason, label in WAIT_REASONS.items():
            with self.subTest(reason=reason):
                self.assertEqual(waiting_label(reason), label)
                self.assertTrue(label)
                self.assertNotEqual(label, reason)
                self.assertFalse(any('a' <= ch.lower() <= 'z' for ch in label), label)

    def test_known_runtime_codes_are_covered(self):
        for reason in ('employee_continue', 'native_prerequisite', 'external_fact',
                       'completion_conditions_missing', 'source_inaccessible',
                       'employee_paused', 'result_unknown', 'not_prepared'):
            with self.subTest(reason=reason):
                self.assertIsNotNone(waiting_label(reason))

    def test_completion_recheck_prefix_is_covered(self):
        for reason in ('completion_recheck_required', 'completion_recheck_dependency',
                       'completion_recheck_facts_changed'):
            with self.subTest(reason=reason):
                self.assertTrue(waiting_label(reason))

    def test_unknown_or_empty_reason_returns_none_instead_of_guessing(self):
        for reason in (None, '', 'x' * 100, 'employee_continue ', 7, True):
            with self.subTest(reason=reason):
                self.assertIsNone(waiting_label(reason))

    def test_workspace_item_carries_the_server_label_but_keeps_the_reason(self):
        item = WorkspaceItem.model_validate({
            'key': 'task:1', 'kind': 'native_task', 'task_id': 1, 'title': '原业务待办',
            'status': 'open', 'status_label': '我的待办', 'waiting_reason': 'native_prerequisite',
            'waiting_label': waiting_label('native_prerequisite'), 'updated_at': '2026-09-29T00:00:00Z'})
        dumped = item.model_dump(mode='json')
        self.assertEqual(dumped['waiting_reason'], 'native_prerequisite')
        self.assertEqual(dumped['waiting_label'], '等同一原单前序步骤完成')

    def test_plan_step_view_accepts_and_defaults_the_label(self):
        base = {'key': 's1', 'position': 0, 'title': '准备第一张卡', 'wait_for': '',
                'status': 'waiting', 'wait_reason': 'employee_continue'}
        step = PlanStepView.model_validate(dict(base, waiting_label=waiting_label('employee_continue')))
        self.assertEqual(step.model_dump()['waiting_label'], '等你继续办理')
        # 未提供时保持缺省，不猜文案。
        self.assertIsNone(PlanStepView.model_validate(base).waiting_label)


class WarehouseCountPosted(unittest.TestCase):
    """盘差过账键必须认原仓储真实库存流水用途，不能认一个不存在的标记名。"""

    def base(self, operation='count'):
        return {'id': 7, 'store_id': 1, 'version': 4, 'number': 'WH-7', 'state': 'review',
                'operation': operation, 'item_id': 1, 'quantity_milli': 0,
                'source_location_id': 3, 'destination_location_id': None,
                'actions': [{'key': 'post_count', 'label': '批准盘点差异'}],
                'stock_moves': [], 'count': {'baseline_quantity_milli': 10000,
                                             'counted_quantity_milli': 9000,
                                             'difference_milli': -1000}}

    def fact(self, data, key='warehouse.count_posted'):
        return run_fact(WarehouseDocumentAdapter(native_reader=reader(data)), CASE, key)

    def test_adapter_uses_the_original_warehouse_count_purpose(self):
        from app.warehouse_service import PURPOSES
        self.assertEqual(count_purpose(), PURPOSES['count'])
        self.assertEqual(count_purpose(), 'wh_count')
        for invented in ('count_adjust', 'count', 'wh_count_adjust', 'wh_count '):
            with self.subTest(invented=invented):
                data = self.base()
                data['stock_moves'] = [{'id': 11, 'purpose': invented, 'quantity_milli': -1000}]
                self.assertIsNone(self.fact(data).satisfied)

    def test_posted_count_move_satisfies_the_key(self):
        data = self.base()
        data['stock_moves'] = [{'id': 11, 'purpose': count_purpose(), 'quantity_milli': -1000,
                                'original_id': None, 'business_date': '2026-09-29'}]
        result = self.fact(data)
        self.assertIs(result.satisfied, True, result)

    def test_observation_and_approval_alone_do_not_post(self):
        self.assertIsNone(self.fact(self.base()).satisfied)

    def test_zero_difference_needs_no_posting(self):
        data = self.base()
        data['count']['counted_quantity_milli'] = data['count']['baseline_quantity_milli']
        data['count']['difference_milli'] = 0
        self.assertIs(self.fact(data).satisfied, False)

    def test_incomplete_observation_is_unknown_not_false(self):
        data = self.base()
        data['count'].pop('counted_quantity_milli')
        self.assertIsNone(self.fact(data).satisfied)

    def test_non_count_document_never_claims_posted(self):
        data = self.base(operation='other_in')
        data.pop('count')
        self.assertIsNone(self.fact(data).satisfied)

    def test_observation_is_its_own_fact_and_still_works(self):
        data = self.base()
        result = self.fact(data, 'warehouse.count_observed')
        self.assertIs(result.satisfied, True, result)
        data.pop('count')
        self.assertIs(self.fact(data, 'warehouse.count_observed').satisfied, False)

    def test_registered_facts_are_the_only_known_keys(self):
        self.assertEqual(set(WH_FACTS), {'warehouse.entry_recorded', 'warehouse.count_observed',
                                         'warehouse.count_posted'})
        self.assertIsNone(self.fact(self.base(), 'warehouse.invented').satisfied)


class GrantDecisionActions(unittest.TestCase):
    """原决定动作是受约束的状态值；大小写变体不能把读取打成 500。"""

    def base(self):
        return {'id': 9, 'version': 2, 'status': 'approved', 'effective_status': 'approved',
                'source_side': True, 'can_read': False,
                'decisions': [{'action': 'approve', 'actor_id': 2, 'reason': '独立复核', 'occurred_at': 'x'}]}

    def fact(self, data, key='dossier.approval_recorded'):
        return run_fact(DossierGrantAdapter(native_reader=reader(data)), GRANT, key)

    def test_normalised_original_action_values_are_decided(self):
        for action in ('approve', 'reject', 'revoke', 'cancel'):
            with self.subTest(action=action):
                data = self.base()
                data['decisions'] = [dict(data['decisions'][0], action=action)]
                expected = action == 'approve'
                self.assertIs(self.fact(data).satisfied, expected)

    def test_recognised_action_variants_still_decide(self):
        for action in ('Approved', 'APPROVE', ' approve '):
            with self.subTest(action=action):
                data = self.base()
                data['decisions'] = [dict(data['decisions'][0], action=action)]
                self.assertIs(self.fact(data).satisfied, True)

    def test_unknown_action_value_is_false_not_a_crash(self):
        # 已识别的决定动作不是批准就是未批准；未知动作不会当成批准。
        data = self.base()
        data['decisions'] = [dict(data['decisions'][0], action='escalated')]
        self.assertIs(self.fact(data).satisfied, False)

    def test_non_string_action_is_not_read_as_a_decision(self):
        for action in (True, 1, None, {'action': 'approve'}):
            with self.subTest(action=action):
                data = self.base()
                data['decisions'] = [dict(data['decisions'][0], action=action)]
                self.assertIsNone(self.fact(data).satisfied)

    def test_missing_decision_list_is_unknown_without_the_source_side(self):
        data = self.base()
        data.pop('decisions')
        self.assertIsNone(self.fact(data).satisfied)

    def test_empty_decision_list_is_false(self):
        data = self.base()
        data['decisions'] = []
        self.assertIs(self.fact(data).satisfied, False)

    def test_revocation_fact_uses_the_same_decision_values(self):
        data = self.base()
        data['decisions'] = [dict(data['decisions'][0], action='revoke')]
        self.assertIs(self.fact(data, 'dossier.revocation_recorded').satisfied, True)


class GrantReceiverSide(unittest.TestCase):
    """接收店由原详情有效状态得到等价事实；批准历史本身不等于现在仍可读。"""

    def base(self, effective='approved', can_read=True):
        return {'id': 9, 'version': 2, 'status': effective, 'effective_status': effective,
                'source_side': False, 'can_read': can_read}

    def fact(self, data, key='dossier.approval_recorded'):
        return run_fact(DossierGrantAdapter(native_reader=reader(data)), GRANT, key)

    def test_receiver_learns_the_original_approval_from_the_effective_state(self):
        result = self.fact(self.base())
        self.assertIs(result.satisfied, True, result)

    def test_receiver_never_claims_approval_for_unapproved_states(self):
        for effective in ('pending', 'rejected', 'cancelled', 'revoked', 'expired', 'suspended'):
            with self.subTest(effective=effective):
                self.assertIs(self.fact(self.base(effective=effective)).satisfied, False)

    def test_receiver_revocation_fact_only_for_ended_grants(self):
        for effective, expected in (('revoked', True), ('cancelled', True), ('approved', False),
                                    ('pending', False), ('expired', False), ('suspended', False)):
            with self.subTest(effective=effective):
                self.assertIs(self.fact(self.base(effective=effective),
                                        'dossier.revocation_recorded').satisfied, expected)

    def test_unknown_effective_state_is_unknown_not_invented(self):
        data = self.base()
        data['effective_status'] = 'something_new'
        self.assertIsNone(self.fact(data).satisfied)
        data['effective_status'] = None
        self.assertIsNone(self.fact(data).satisfied)

    def test_receiver_record_readability_is_still_its_own_probe(self):
        adapter = DossierGrantAdapter(native_reader=reader({'grant_id': 9, 'read_only': True}))
        result = run_fact(adapter, GRANT, 'dossier.record_readable')
        self.assertIs(result.satisfied, True, result)

    def test_indistinguishable_receiver_read_stays_unknown(self):
        adapter = DossierGrantAdapter(native_reader=reader(None, status=404))
        result = run_fact(adapter, GRANT, 'dossier.record_readable')
        self.assertIsNone(result.satisfied)
        self.assertIn('403/404', result.reason)


class CareClosedFact(unittest.TestCase):
    """结案键必须认原状态机的 `completed`；取消不是结案。"""

    def base(self, state='working'):
        return {'id': 7, 'version': 3, 'subtype': 'consultation', 'state': state,
                'records': [], 'actions': [], 'assignee_id': 2, 'result': ''}

    def fact(self, data, key='care.closed'):
        return run_fact(CustomerCareAdapter(native_reader=reader(data)),
                        BusinessObjectRef(type='care_case', id=7), key)

    def test_original_completed_state_closes_the_case(self):
        from app import customer_service
        self.assertEqual(customer_service.STATUS['completed'], '已结案')
        self.assertIs(self.fact(self.base('completed')).satisfied, True)

    def test_cancelled_is_not_closed(self):
        result = self.fact(self.base('cancelled'))
        self.assertIs(result.satisfied, False, result)
        self.assertIn('取消', result.reason)

    def test_pending_and_working_are_false(self):
        for state in ('pending', 'working'):
            with self.subTest(state=state):
                self.assertIs(self.fact(self.base(state)).satisfied, False)

    def test_unregistered_state_is_unknown_not_a_denial(self):
        for state in ('closed', 'completed ', None, 7):
            with self.subTest(state=state):
                data = self.base()
                data['state'] = state
                self.assertIsNone(self.fact(data).satisfied)


class RepairReleaseFacts(unittest.TestCase):
    """交车键必须来自原 data 的 released_date 与 release_evidence_id 两件事实。"""

    def base(self):
        return {'id': 7, 'store_id': 1, 'version': 5, 'number': 'HKR7', 'state': 'completed',
                'quotes': [{'id': 21, 'revision': 1, 'authorized': True, 'cancelled': False}],
                'quality': [{'id': 31, 'quote_id': 21, 'passed': True, 'result': '合格', 'evidence_id': 41}],
                'actions': [], 'data': {'released_date': '2026-09-29', 'release_evidence_id': 51}}

    def fact(self, data, key='repair.release_recorded'):
        return run_fact(RepairOrderAdapter(native_reader=reader(data)), CASE, key)

    def test_both_original_release_facts_are_required(self):
        self.assertIs(self.fact(self.base()).satisfied, True)
        # 只留下其中一个键时，原交车事实不完整：不得当作已交车。
        for missing in ('released_date', 'release_evidence_id'):
            with self.subTest(missing=missing):
                data = self.base()
                data['data'] = {k: v for k, v in data['data'].items() if k != missing}
                result = self.fact(data)
                self.assertIs(result.satisfied, False, result)
                self.assertIn('不完整', result.reason)

    def test_absent_release_facts_are_unknown_not_a_denial(self):
        data = self.base()
        data['data'] = {}
        self.assertIsNone(self.fact(data).satisfied)

    def test_partial_release_evidence_is_false_not_success(self):
        data = self.base()
        data['data'] = {'released_date': '2026-09-29', 'release_evidence_id': None}
        result = self.fact(data)
        self.assertIs(result.satisfied, False, result)
        self.assertIn('不完整', result.reason)

    def test_settled_or_collected_does_not_prove_handover(self):
        data = self.base()
        data['data'] = {}
        data['settled'] = True
        data['customer_due_cents'] = 0
        self.assertIsNone(self.fact(data).satisfied)


    def test_authorized_quote_and_quality_remain_separate_facts(self):
        data = self.base()
        data['data'] = {}
        self.assertIs(self.fact(data, 'repair.current_quote_authorized').satisfied, True)
        self.assertIs(self.fact(data, 'repair.passed_quality_recorded').satisfied, True)
        self.assertIsNone(self.fact(data, 'repair.release_recorded').satisfied)


class DossierNativeGrant(unittest.TestCase):
    """跨店授权走原 /api/dossier-grants：接收店必须得到与批准一致的等价事实。"""

    setUpClass = classmethod(shared.ProcurementNativeFlow.setUpClass.__func__)
    setUp = shared.ProcurementNativeFlow.setUp
    login = shared.ProcurementNativeFlow.login
    new_run = shared.ProcurementNativeFlow.new_run

    def employee(self, role, store_id=1, label=None):
        from fastapi.testclient import TestClient
        password = fixture_env.PASSWORD.read_text()
        name = 'dg_' + (label or role) + '_' + uuid4().hex[:8]
        response = self.client.post('/api/users', json={
            'username': name, 'display_name': '合成跨店' + (label or role), 'role': role,
            'password': password + 'Initial', 'store_ids': [store_id],
            'store_roles': [{'store_id': store_id, 'role': role}]})
        self.assertEqual(response.status_code, 201, response.text)
        client = TestClient(app); client.__enter__(); self.addCleanup(client.__exit__, None, None, None)
        client.headers.update({'X-App-Request': '1', 'X-Store-ID': str(store_id)})
        response = client.post('/api/auth/login', json={'username': name, 'password': password + 'Initial'})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers['X-CSRF-Token'] = client.cookies.get('dealer_csrf')
        response = client.post('/api/auth/password', json={'current_password': password + 'Initial',
                                                           'new_password': password})
        self.assertEqual(response.status_code, 200, response.text)
        response = client.post('/api/auth/login', json={'username': name, 'password': password})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers['X-CSRF-Token'] = client.cookies.get('dealer_csrf')
        me = client.get('/api/auth/me')
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()['active_store_id'], store_id, '合成账号必须落在指定门店')
        return client

    def request_id(self):
        return 'dg_' + uuid4().hex

    def source_case(self):
        from sqlalchemy import select as sa_select
        from app.flow_models import Case
        with SessionLocal() as db:
            row = db.scalar(sa_select(Case).where(Case.store_id == 1, Case.kind == 'repair')
                            .order_by(Case.id))
            if row is None:
                row = db.scalar(sa_select(Case).where(Case.store_id == 1).order_by(Case.id))
            return row.id, row.version

    def propose(self, receiver_id, days=5):
        case_id, version = self.source_case()
        expires = datetime.now(timezone.utc) + timedelta(days=days)
        me = self.client.get('/api/auth/me')
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()['active_store_id'], 1, '发起方必须在原店门店 1')
        response = self.client.post('/api/dossier-grants', json={
            'request_id': self.request_id(),
            'values': {'source_case_id': case_id, 'source_case_version': version, 'to_store_id': 2,
                       'recipient_id': receiver_id, 'include_record': True, 'include_financials': False,
                       'include_contact': False, 'file_ids': [], 'purpose': '合成跨店只读档案核对',
                       'expires_at': expires.isoformat(), 'confirmed': True}})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['grant']

    def decide(self, grant_id, version, action, client, reason='合成独立复核决定'):
        response = client.post(f'/api/dossier-grants/{grant_id}/actions/{action}', json={
            'request_id': self.request_id(), 'version': version,
            'values': {'reason': reason, 'confirmed': True}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['grant']

    def fact(self, grant_id, key, store_id=1, outcome='succeeded'):
        from app.db import SessionLocal as Session
        from app.assistant_runtime_queue import claim_next, release
        from app.assistant_runtime_principal import native_reader_for_principal
        from app.assistant_runtime_domains.dossier_grant import DG_READ, DG_RECORD
        from app.assistant_runtime_schemas import BusinessObjectRef as Ref
        _, run, _ = self.new_run('核对跨店授权事实')
        with Session() as db:
            principal = claim_next(db, 'dossier-facts-' + self.request_id())
        self.assertIsNotNone(principal, 'The previous fact check must release its worker slot')
        try:
            with Session() as db:
                native = native_reader_for_principal(db, principal, (DG_READ, DG_RECORD))
                # 接收店与发起店的可见范围不同：同一读取器按声明门店核对事实。
                actor = SimpleNamespace(store_id=store_id)
                return asyncio.run(DossierGrantAdapter(native_reader=native).fact_snapshot(
                    actor, Ref(type='dossier_grant', id=grant_id), key))
        finally:
            with Session() as db:
                self.assertEqual(release(db, principal, outcome=outcome).status, outcome)

    def test_source_side_detail_proves_the_original_approval(self):
        receiver = self.employee('manager', store_id=2, label='receiver')
        reviewer = self.employee('manager', store_id=1, label='reviewer')
        grant = self.propose(receiver.get('/api/auth/me').json()['id'])
        pending = self.fact(grant['id'], 'dossier.approval_recorded')
        self.assertIs(pending.satisfied, False, pending)
        self.decide(grant['id'], grant['version'], 'approve', reviewer)
        approved = self.fact(grant['id'], 'dossier.approval_recorded')
        self.assertIs(approved.satisfied, True, approved)
        self.assertIs(self.fact(grant['id'], 'dossier.revocation_recorded').satisfied, False)

    def test_receiver_store_reads_the_same_original_approval(self):
        """接收店详情不给原决定明细，但有效状态必须是可读的原批准证据。"""
        receiver = self.employee('manager', store_id=2, label='reader')
        reviewer = self.employee('manager', store_id=1, label='approver')
        grant = self.propose(receiver.get('/api/auth/me').json()['id'])
        self.decide(grant['id'], grant['version'], 'approve', reviewer)
        detail = receiver.get(f"/api/dossier-grants/{grant['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertFalse(detail.json()['source_side'])
        self.assertNotIn('decisions', detail.json())
        self.assertEqual(detail.json()['effective_status'], 'approved')
        self.assertTrue(detail.json()['can_read'])
        # 接收店真实读取同一授权：这是它唯一能得到的原接口证据。
        record = receiver.get(f"/api/dossier-grants/{grant['id']}/record")
        self.assertEqual(record.status_code, 200, record.text)
        # 换一个不是本授权接收人的原身份时，同一读取按合同保持未知而不是假装可读。
        denied = self.fact(grant['id'], 'dossier.record_readable', store_id=2)
        self.assertIsNone(denied.satisfied, denied)
        self.assertIn('403/404', denied.reason)

    def test_revoked_grant_records_both_decisions_and_stops_receiver_reads(self):
        """原批准与撤销分别留事实；撤销后接收店不得再读到档案。"""
        receiver = self.employee('manager', store_id=2, label='revoked')
        reviewer = self.employee('manager', store_id=1, label='revoker')
        grant = self.propose(receiver.get('/api/auth/me').json()['id'])
        self.assertIs(self.fact(grant['id'], 'dossier.revocation_recorded').satisfied, False)
        approved = self.decide(grant['id'], grant['version'], 'approve', reviewer)
        self.assertEqual(receiver.get(f"/api/dossier-grants/{grant['id']}/record").status_code, 200)
        self.decide(grant['id'], approved['version'], 'revoke', reviewer, reason='合成结束跨店授权')
        # 批准历史仍在，但已经结束；撤销事实成立，接收店不再可读。
        self.assertIs(self.fact(grant['id'], 'dossier.approval_recorded').satisfied, True)
        self.assertIs(self.fact(grant['id'], 'dossier.revocation_recorded').satisfied, True)
        stopped = receiver.get(f"/api/dossier-grants/{grant['id']}/record")
        self.assertEqual(stopped.status_code, 403, stopped.text)
        detail = receiver.get(f"/api/dossier-grants/{grant['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()['effective_status'], 'revoked')
        self.assertFalse(detail.json()['can_read'])


if __name__ == '__main__':
    unittest.main()
