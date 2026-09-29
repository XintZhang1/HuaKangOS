"""Service results must match current lines and each line's latest native submission."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio
from copy import deepcopy
from types import SimpleNamespace
import unittest
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.main import app  # Use the same model initialization order as the HTTP application.
from app.db import SessionLocal, today
from app.flow_models import Customer, Task
from app.master_models import AgencyProject
from app.assistant_runtime_domains.service_order import ServiceOrderAdapter, SVC_READ
from app.assistant_runtime_schemas import BusinessObjectRef
from app.assistant_runtime_principal import native_reader_for_principal
from app.assistant_runtime_conditions import evaluate_conditions
from app.assistant_runtime_queue import claim_next, release
import test_procurement_repair_facts as shared

KEY = 'service.external_approved'


class ServiceResultFacts(unittest.TestCase):
    """Projection tests only. Real authority and original commands are exercised below."""
    def base(self):
        return {'id':7, 'version':3, 'lines':[{'line_key':'a'}],
                'submissions':[{'id':11, 'case_id':7, 'quote_id':21, 'line_key':'a'}],
                'results':[{'id':31, 'submission_id':11, 'outcome':'approved'}]}

    def fact(self, data):
        async def read(operation, **kwargs):
            self.assertEqual(operation, SVC_READ)
            self.assertEqual(kwargs['path_args'], {'case_id':7})
            return {'status':200, 'data':data}
        return asyncio.run(ServiceOrderAdapter(native_reader=read).fact_snapshot(
            SimpleNamespace(store_id=1), BusinessObjectRef(type='case', id=7), KEY))

    def test_top_level_native_result_proves_approval(self):
        result = self.fact(self.base())
        self.assertIs(result.satisfied, True, result)
        self.assertEqual(result.evidence_refs[0].source_id.id, 7)

    def test_pending_rejected_and_supplement_request_are_not_approval(self):
        for results in ([], [{'id':31, 'submission_id':11, 'outcome':'rejected'}],
                        [{'id':31, 'submission_id':11, 'outcome':'need_documents', 'result':'approved'}]):
            with self.subTest(results=results):
                data = self.base(); data['results'] = results
                self.assertIs(self.fact(data).satisfied, False)

    def test_latest_is_selected_per_current_line_not_for_whole_order(self):
        data = self.base(); data['lines'].append({'line_key':'b'})
        data['submissions'].append({'id':12, 'case_id':7, 'quote_id':21, 'line_key':'b'})
        result = self.fact(data)
        self.assertIs(result.satisfied, True, result)
        self.assertIn('至少一项', result.reason)

    def test_older_result_never_proves_a_newer_submission(self):
        data = self.base()
        data['submissions'].append({'id':12, 'case_id':7, 'quote_id':21, 'line_key':'a'})
        self.assertIs(self.fact(data).satisfied, False)

    def test_supplement_latest_result_is_stable_under_response_order(self):
        data = self.base()
        data['results'][0]['outcome'] = 'need_documents'
        data['submissions'].insert(0, {'id':12, 'case_id':7, 'quote_id':21, 'line_key':'a', 'supplement_result_id':31})
        data['results'].insert(0, {'id':32, 'submission_id':12, 'outcome':'approved'})
        self.assertIs(self.fact(data).satisfied, True)

    def test_result_for_a_noncurrent_line_does_not_prove_approval(self):
        data = self.base(); data['lines'] = [{'line_key':'b'}]
        self.assertIs(self.fact(data).satisfied, False)

    def test_carried_line_keeps_original_submission_across_quote_revisions(self):
        data = self.base(); data['quote'] = {'id':22}
        data['lines'][0]['quote_id'] = 22
        # Original commands carry immutable line_key facts across quote additions.
        self.assertIs(self.fact(data).satisfied, True)

    def test_missing_top_level_result_list_is_unknown_not_nested_fallback(self):
        data = self.base(); data['submissions'][0]['results'] = data.pop('results')
        self.assertIsNone(self.fact(data).satisfied)

    def test_malformed_or_ambiguous_linkage_never_proves_approval(self):
        base = self.base()
        variants = []
        data = deepcopy(base); data['results'][0]['submission_id'] = 999; variants.append(data)
        data = deepcopy(base); data['results'].append({'id':32, 'submission_id':11, 'outcome':'rejected'}); variants.append(data)
        data = deepcopy(base); data['results'][0].pop('outcome'); data['results'][0]['result'] = 'approved'; variants.append(data)
        data = deepcopy(base); data['submissions'][0]['case_id'] = 8; variants.append(data)
        data = deepcopy(base); data['submissions'][0]['id'] = True; variants.append(data)
        data = deepcopy(base); data['submissions'].append({'id':11, 'case_id':7, 'quote_id':21, 'line_key':'b'}); variants.append(data)
        data = deepcopy(base); data['lines'] = None; variants.append(data)
        for data in variants:
            with self.subTest(data=data):
                self.assertIsNone(self.fact(data).satisfied)

    def test_truncated_original_detail_is_rejected(self):
        data = self.base(); data['truncated'] = True
        with self.assertRaises(HTTPException) as error:
            self.fact(data)
        self.assertEqual(error.exception.status_code, 502)


class ServiceNativeFlow(unittest.TestCase):
    setUpClass = classmethod(shared.ProcurementNativeFlow.setUpClass.__func__)
    setUp = shared.ProcurementNativeFlow.setUp
    login = shared.ProcurementNativeFlow.login
    new_run = shared.ProcurementNativeFlow.new_run
    login_employee = shared.ProcurementNativeFlow.login_employee

    def post(self, path, body, client=None, status=200):
        response = (client or self.client).post(path, json=body)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def detail(self, ident):
        response = self.client.get(f'/api/service-orders/{ident}')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def evidence(self, ident, client=None):
        response = (client or self.client).post(f'/api/flow/cases/{ident}/files',
            data={'category':'authorization'}, files={'file':('synthetic.txt',
                ('合成代办凭据，非真实客户文件 '+uuid4().hex).encode(), 'text/plain')})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['id']

    def action(self, ident, action, values, client=None):
        return self.post(f'/api/service-orders/{ident}/actions/{action}',
            {'request_id':'svc_'+uuid4().hex, 'version':self.detail(ident)['version'], 'values':values}, client)

    def fact(self, ident, key=KEY, *, public=False):
        _, run, _ = self.new_run('核对原代办事实')
        with SessionLocal() as db:
            principal = claim_next(db, 'service-facts-'+uuid4().hex)
        self.assertIsNotNone(principal)
        self.assertEqual(principal.run_id, run['id'])
        outcome = 'failed'
        try:
            with SessionLocal() as db:
                ref = BusinessObjectRef(type='case', id=ident)
                if public:
                    value = asyncio.run(evaluate_conditions(db, principal,
                        [{'type':'fact_exists', 'object_ref':ref.model_dump(), 'fact_key':key}], purpose='completion'))
                else:
                    native = native_reader_for_principal(db, principal, (SVC_READ,))
                    value = asyncio.run(ServiceOrderAdapter(native_reader=native).fact_snapshot(principal, ref, key))
            outcome = 'succeeded'
            return value
        finally:
            with SessionLocal() as db:
                release(db, principal, outcome=outcome)

    def order(self, subtype='agency'):
        manager = self.login_employee('manager')
        manager_id = manager.get('/api/auth/me').json()['id']
        with SessionLocal() as db:
            customer = db.scalar(select(Customer.id).where(Customer.store_id == 1))
            project = AgencyProject(store_id=1, code='SYN-AGENCY', name='合成代办项目',
                                    active=True, service_fee_cents=1000, expected_days=1)
            db.add(project); db.commit(); project_id = project.id
        body = {'request_id':'svc_'+uuid4().hex, 'subtype':subtype, 'customer_id':customer,
                'reason':'合成外部结果回归', 'due_date':today().isoformat()}
        ident = self.post('/api/service-orders', body, status=201)['id']
        source = {'agency_project_id':project_id}
        if subtype == 'other_income':
            item = self.post('/api/service-orders/income-items', {'request_id':'svc_'+uuid4().hex,
                'code':'SYN-INCOME', 'name':'合成其它服务', 'unit':'项', 'standard_fee_cents':1000}, status=201)
            source = {'income_item_id':item['id']}
        self.action(ident, 'quote', {'reason':'合成服务报价', 'discount_cents':0,
            'lines':[{'line_key':key, 'bucket':'fee', **source, 'quantity_milli':1000,
                      'unit_price_cents':1000, 'due_date':today().isoformat()} for key in ('a', 'b')]})
        # The original application assigns a genuine independent manager task.
        # Transfer it through the original API to this newly created test manager.
        with SessionLocal() as db:
            task = db.scalar(select(Task).where(Task.case_id == ident, Task.key == 'serviceorder_approve'))
            task_id, version = task.id, task.version
        self.post(f'/api/flow/tasks/{task_id}/assign', {'version':version, 'assignee_id':manager_id,
                                                     'reason':'合成独立审批交接'})
        self.action(ident, 'approve', {'evidence_id':self.evidence(ident, manager), 'reason':'合成独立审核',
            'minimum_fee_cents':2000, 'allow_below_minimum':False}, manager)
        self.action(ident, 'authorize', {'quote_id':self.detail(ident)['quote']['id'], 'evidence_id':self.evidence(ident)})
        return ident

    def submit(self, ident, key='a', supplement=None):
        data = {'line_key':key, 'external_reference':'SYN-'+uuid4().hex,
                'submitted_on':today().isoformat(), 'evidence_id':self.evidence(ident)}
        if supplement is not None:
            data['supplement_result_id'] = supplement
        result = self.action(ident, 'submit', data)
        return result['submissions'][-1]['id']

    def external_result(self, ident, submission, outcome, key='a'):
        result = self.action(ident, 'external_result', {'line_key':key, 'submission_id':submission,
            'outcome':outcome, 'result':'合成外部结论 '+outcome, 'evidence_id':self.evidence(ident)})
        return result['results'][-1]['id']

    def test_original_supplement_and_partial_approval_are_distinct_from_fulfillment(self):
        ident = self.order()
        self.assertIs(self.fact(ident, 'service.submission_recorded').satisfied, False)
        first = self.submit(ident)
        self.assertIs(self.fact(ident, 'service.submission_recorded').satisfied, True)
        self.assertFalse(self.fact(ident, public=True).satisfied)
        need = self.external_result(ident, first, 'need_documents')
        self.assertIs(self.fact(ident).satisfied, False)
        second = self.submit(ident, supplement=need)
        self.assertFalse(self.fact(ident, public=True).satisfied)
        self.external_result(ident, second, 'approved')
        self.assertTrue(self.fact(ident, public=True).satisfied)
        self.submit(ident, 'b')
        self.assertIs(self.fact(ident).satisfied, True)
        self.assertIs(self.fact(ident, 'service.fulfillment_recorded').satisfied, False)
        self.action(ident, 'fulfill', {'line_key':'a', 'result':'合成项目实际办结', 'evidence_id':self.evidence(ident)})
        self.assertIs(self.fact(ident, 'service.fulfillment_recorded').satisfied, True)
        current = self.detail(ident)
        self.assertEqual(current['state'], 'working')
        self.assertFalse(next(line for line in current['lines'] if line['line_key'] == 'b')['fulfilled'])

    def test_granted_watch_uses_native_external_result_without_model_or_fulfillment(self):
        from app.business_assistant_models import AssistantWorkPlan
        from app.assistant_runtime_models import FollowupGrant
        from app.assistant_worker import Worker
        from fake_provider import Provider, tool, reply
        ident = self.order()
        submission = self.submit(ident)
        condition = {'type':'fact_exists', 'object_ref':{'type':'case', 'id':ident}, 'fact_key':KEY}
        sid, _, _ = self.new_run('仅跟进本单是否已有项目获外部批准，不替我办结或收款。')
        provider = Provider([tool('save_work_plan', {'schema_version':2, 'goal':'等待至少一项外部批准',
            'steps':[{'key':'external', 'title':'核对外部结果', 'object_ref':{'type':'case', 'id':ident},
                      'conditions':[condition], 'completion_conditions':[condition]}]}), reply('跟进事项已保存。')])
        with provider.installed():
            result = asyncio.run(Worker().tick())
        self.assertEqual(result['status'], 'succeeded', result)
        with SessionLocal() as db:
            pid = db.scalar(select(AssistantWorkPlan.id).where(AssistantWorkPlan.session_id == sid))
        self.assertIsNotNone(pid)
        view = self.client.get('/api/business-assistant/plans/'+pid).json()
        self.post('/api/business-assistant/plans/'+pid+'/followup', {'action':'enable', 'expected_version':view['version']})
        quiet = Provider([AssertionError('A factual approval watch must not prepare or write business')])
        with quiet.installed():
            result = asyncio.run(Worker().tick())
        self.assertIsNone(result['error'], result)
        self.assertFalse(result['claimed'], result)
        with SessionLocal() as db:
            plan = db.get(AssistantWorkPlan, pid)
            self.assertEqual(plan.status, 'active')
            due = plan.next_check_at
        self.assertIsNotNone(due)
        self.external_result(ident, submission, 'approved')
        # Use the persisted scheduled deadline, not sleeps or a fabricated wake
        # row. The scheduler and original fact reads remain real.
        with quiet.installed():
            result = asyncio.run(Worker(clock=lambda:due).tick())
        self.assertIsNone(result['error'], result)
        self.assertFalse(result['claimed'], result)
        with SessionLocal() as db:
            self.assertEqual(db.get(AssistantWorkPlan, pid).status, 'completed')
            grant = db.scalar(select(FollowupGrant).where(FollowupGrant.plan_id == pid))
            self.assertEqual(grant.status, 'revoked')
        current = self.detail(ident)
        self.assertEqual(current['state'], 'working')
        self.assertEqual(current['fulfillments'], [])
        self.assertEqual(self.client.get('/api/business-assistant/sessions/'+sid).json()['proposals'], [])
        self.assertEqual(quiet.requests, [])

    def test_other_service_can_fulfill_without_invented_external_submission(self):
        ident = self.order('other_income')
        self.assertIs(self.fact(ident).satisfied, False)
        self.action(ident, 'fulfill', {'line_key':'a', 'result':'合成服务实际履行', 'evidence_id':self.evidence(ident)})
        self.assertIs(self.fact(ident, 'service.fulfillment_recorded').satisfied, True)
        self.assertEqual(self.detail(ident)['submissions'], [])


if __name__ == '__main__':
    unittest.main()
