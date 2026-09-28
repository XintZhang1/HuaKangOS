"""HTTP/worker/SQLite follow-up contracts. No real model or original business mocks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import test_runtime_integration as baseline
import asyncio, json, unittest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select, func
from app.db import SessionLocal, utcnow
from app.flow_models import Case, Task, Customer, StockMove
from app.models import CashEntry, User
from app.business_assistant_models import AssistantWorkPlan, AssistantProposal
from app.assistant_runtime_models import FollowupGrant, PlanStep, Run, WorkItem, WakeEvent, Notification
from app.assistant_worker import Worker
from app.config import settings
from fake_provider import Provider, tool, reply

BASE = baseline.BASE

class FollowupIntegration(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    new_run = baseline.RuntimeIntegration.new_run
    tick = baseline.RuntimeIntegration.tick
    session = baseline.RuntimeIntegration.session
    count = baseline.RuntimeIntegration.count
    confirm = baseline.RuntimeIntegration.confirm

    def create_plan(self, kind='lead'):
        if kind == 'lead':
            # Exercise the actual native creation API as explicit fixture setup;
            # never invent tasks or change the original business state machine.
            for index in range(2):
                response = self.client.post('/api/flow/cases', json={
                    'request_id': 'seed_' + uuid4().hex, 'kind': 'lead',
                    'values': {'customer_name': '合成接待' + str(index), 'source': '展厅到店'}})
                self.assertEqual(response.status_code, 201, response.text)
            native_state, task_key, action = 'unassigned', 'assign', 'assign'
        else:
            native_state, task_key, action = 'pending', 'callback', 'callback_done'
        with SessionLocal() as db:
            pairs = db.execute(select(Case.id, Task.id).join(Task, Task.case_id == Case.id).where(
                Case.kind == kind, Case.state == native_state, Case.store_id == 1,
                Task.key == task_key, Task.status == 'open').order_by(Case.id.desc()).limit(2)).all()
            self.assignee_id = db.scalar(select(User.id).where(User.username == 'demo_sales'))
        self.assertEqual(len(pairs), 2)
        steps = [{
            'key': 'call_' + str(index), 'title': ('分派接待' if kind == 'lead' else '记录回访') + str(index + 1),
            'object_ref': {'type': 'case', 'id': case_id},
            'form_ref': f'case:{case_id}:{action}',
            'depends_on': ['call_0'] if index else [],
            'conditions': [{'type': 'native_action_available', 'object_ref': {'type': 'case', 'id': case_id},
                            'action_key': action}],
            'completion_conditions': [{'type': 'native_task_state', 'task_id': task_id, 'expected_status': 'done'}],
        } for index, (case_id, task_id) in enumerate(pairs)]
        sid, run, _ = self.new_run('依次完成两项' + ('接待分派，接手员工为演示销售' if kind == 'lead' else '回访，结果为客户满意') + '。每一步都请我确认。')
        provider = Provider([tool('save_work_plan', {'schema_version': 2, 'goal': '依次办理两项' + ('接待分派' if kind == 'lead' else '回访'), 'steps': steps}),
                             reply('已保存回访事项。')])
        outcome = self.tick(provider)
        self.assertEqual(outcome['status'], 'succeeded', outcome)
        with SessionLocal() as db:
            plan = db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.session_id == sid))
            self.assertIsNotNone(plan, [r['messages'] for r in provider.requests])
            plan_id = plan.id
        view = self.plan(plan_id)
        self.assertEqual(view['status'], 'active')
        self.assertEqual(self.session(sid)['proposals'], [])
        return sid, plan_id, steps

    def plan(self, plan_id):
        response = self.client.get(BASE + '/plans/' + plan_id)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def followup(self, plan_id, action):
        view = self.plan(plan_id)
        response = self.client.post(BASE + '/plans/' + plan_id + '/followup',
            json={'action': action, 'expected_version': view['version']})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def tick_until_run(self, provider):
        # Each documented cycle consumes at most one committed event. Allow the
        # current finite backlog; this is not a time/ordering assumption.
        with SessionLocal() as db:
            pending = db.scalar(select(func.count()).select_from(WakeEvent).where(WakeEvent.state == 'pending'))
        for _ in range(pending + 1):
            result = self.tick(provider)
            self.assertIsNone(result['error'], result)
            if result['claimed']:
                return result
        return result

    def preparation(self, step):
        return Provider([tool('prepare_business_form', {
            'form_ref': step['form_ref'], 'values': {'assignee_id': self.assignee_id} if step['form_ref'].endswith(':assign') else {'result': '客户满意'}, 'summary': step['title']}),
            reply('操作已准备，请核对后确认。')])

    def test_worker_drives_granted_plan_and_requires_each_human_confirmation(self):
        sid, plan_id, steps = self.create_plan()
        self.followup(plan_id, 'enable')
        before = [self.count(t) for t in (Customer, Case, CashEntry, StockMove)]
        first = self.tick_until_run(self.preparation(steps[0]))
        self.assertTrue(first['claimed'], first)
        self.assertEqual(first['status'], 'succeeded', first)
        cards = self.session(sid)['proposals']
        self.assertEqual(len(cards), 1, cards)
        self.assertEqual(cards[0]['status'], 'pending')
        with SessionLocal() as db:
            self.assertEqual(db.get(Task, steps[0]['completion_conditions'][0]['task_id']).status, 'open')
            self.assertEqual(db.get(Task, steps[1]['completion_conditions'][0]['task_id']).status, 'open')
        quiet = Provider([AssertionError('Pending confirmation must not call model')])
        for _ in range(3):
            self.assertFalse(self.tick(quiet)['claimed'])
        self.assertEqual(quiet.requests, [])
        confirmed = self.confirm(sid, cards[0])
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        second = self.tick_until_run(self.preparation(steps[1]))
        self.assertTrue(second['claimed'], second)
        self.assertEqual(second['status'], 'succeeded', second)
        cards = self.session(sid)['proposals']
        self.assertEqual(len(cards), 2, cards)
        pending = next(c for c in cards if c['status'] == 'pending')
        confirmed = self.confirm(sid, pending)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        for _ in range(12):
            result = self.tick(quiet)
            self.assertIsNone(result['error'], result)
            self.assertFalse(result['claimed'], result)
            if self.plan(plan_id)['status'] == 'completed':
                break
        self.assertEqual(self.plan(plan_id)['status'], 'completed')
        self.assertEqual(self.plan(plan_id)['grant']['status'], 'revoked')
        self.assertEqual([self.count(t) for t in (Customer, Case, CashEntry, StockMove)], before)
        with SessionLocal() as db:
            self.assertEqual(db.get(Task, steps[1]['completion_conditions'][0]['task_id']).status, 'done')
            self.assertEqual(db.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.plan_id == plan_id,
                    WorkItem.item_kind == 'prepare')), 2)

    def test_cancelled_task_does_not_prove_completion_or_unblock_successor(self):
        sid, pid, steps = self.create_plan(kind='callback')
        self.followup(pid, 'enable')
        self.assertTrue(self.tick_until_run(self.preparation(steps[0]))['claimed'])
        card = self.session(sid)['proposals'][0]
        response = self.confirm(sid, card)
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            self.assertEqual(db.get(Task, steps[0]['completion_conditions'][0]['task_id']).status, 'cancelled')
        quiet = Provider([AssertionError('Cancelled task is not a completion fact')])
        result = self.tick_until_run(quiet)
        self.assertFalse(result['claimed'], result)
        self.assertEqual(quiet.requests, [])
        self.assertNotEqual(self.plan(pid)['status'], 'completed')
        self.assertEqual(len(self.session(sid)['proposals']), 1)

    def test_ungranted_plan_never_starts_automatically(self):
        sid, plan_id, _ = self.create_plan()
        quiet = Provider([AssertionError('No grant: never call model')])
        for _ in range(3):
            self.assertFalse(self.tick(quiet)['claimed'])
        self.assertEqual(self.session(sid)['proposals'], [])
        self.assertEqual(quiet.requests, [])
        self.assertEqual(self.plan(plan_id)['grant']['enabled'], False)


# Keep these methods on a separate class without inheriting collected test cases.
class FollowupAuthority(unittest.TestCase):
    setUp = FollowupIntegration.setUp
    login = FollowupIntegration.login
    new_run = FollowupIntegration.new_run
    tick = FollowupIntegration.tick
    session = FollowupIntegration.session
    count = FollowupIntegration.count
    confirm = FollowupIntegration.confirm
    create_plan = FollowupIntegration.create_plan
    plan = FollowupIntegration.plan
    followup = FollowupIntegration.followup
    preparation = FollowupIntegration.preparation
    tick_until_run = FollowupIntegration.tick_until_run

    def manager(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self.admin_client = self.client
        original = fixture_env.PASSWORD.read_text()
        response = self.admin_client.post('/api/users', json={
            'username':'followup_manager', 'display_name':'合成跟进主管', 'role':'manager',
            'password':original + 'Initial', 'store_ids':[1], 'store_roles':[{'store_id':1,'role':'manager'}]})
        self.assertEqual(response.status_code, 201, response.text)
        manager_id = response.json()['id']
        self.client = TestClient(app)
        self.client.__enter__(); self.addCleanup(self.client.__exit__,None,None,None)
        self.client.headers.update({'X-App-Request':'1','X-Store-ID':'1'})
        r = self.client.post('/api/auth/login',json={'username':'followup_manager','password':original + 'Initial'})
        self.assertEqual(r.status_code,200,r.text)
        self.client.headers['X-CSRF-Token'] = self.client.cookies.get('dealer_csrf')
        r = self.client.post('/api/auth/password',json={'current_password':original + 'Initial','new_password':original})
        self.assertEqual(r.status_code,200,r.text)
        self.login(self.client,'followup_manager')
        return manager_id

    def quiet(self):
        return Provider([AssertionError('No model request is authorized here')])

    def test_granted_plan_survives_logout_but_cannot_confirm(self):
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        r = self.client.post('/api/auth/logout',json={})
        self.assertEqual(r.status_code,200,r.text)
        provider = self.preparation(steps[0])
        outcome = self.tick_until_run(provider)
        self.assertTrue(outcome['claimed'],outcome)
        self.assertEqual(outcome['status'],'succeeded',outcome)
        with SessionLocal() as db:
            card = db.scalar(select(AssistantProposal).where(AssistantProposal.session_id == sid))
            self.assertEqual(card.status,'pending')
            ident, digest = card.id, card.digest
            self.assertEqual(db.get(Task,steps[0]['completion_conditions'][0]['task_id']).status,'open')
        r = self.client.post(BASE+f'/sessions/{sid}/proposals/{ident}/confirm',json={'digest':digest})
        self.assertIn(r.status_code,(401,403),r.text)
        self.login(self.client)
        self.assertEqual(self.plan(pid)['grant']['status'],'active')
        self.assertEqual(self.session(sid)['proposals'][0]['status'],'pending')

    def test_pause_resume_preserves_grant_and_does_not_repeat_preparation(self):
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        self.assertTrue(self.tick_until_run(self.preparation(steps[0]))['claimed'])
        first = self.session(sid)['proposals'][0]
        with SessionLocal() as db: grant_id = db.scalar(select(FollowupGrant.id).where(FollowupGrant.plan_id == pid))
        self.followup(pid,'pause')
        r = self.confirm(sid,first)
        self.assertEqual(r.status_code,200,r.text)
        quiet = self.quiet()
        self.assertFalse(self.tick_until_run(quiet)['claimed'])
        self.assertEqual(quiet.requests,[])
        self.assertEqual(len(self.session(sid)['proposals']),1)
        self.followup(pid,'resume')
        second = self.tick_until_run(self.preparation(steps[1]))
        self.assertTrue(second['claimed'],second)
        self.assertEqual(second['status'],'succeeded',second)
        self.assertEqual(len(self.session(sid)['proposals']),2)
        with SessionLocal() as db:
            self.assertEqual(list(db.scalars(select(FollowupGrant.id).where(FollowupGrant.plan_id==pid))),[grant_id])

    def test_revoke_keeps_prepared_card_but_prevents_successor(self):
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        self.assertTrue(self.tick_until_run(self.preparation(steps[0]))['claimed'])
        card = self.session(sid)['proposals'][0]
        self.followup(pid,'revoke')
        # Stopping follow-up does not retract an already issued human card.
        self.assertEqual(self.session(sid)['proposals'][0]['status'],'pending')
        r = self.confirm(sid,card)
        self.assertEqual(r.status_code,200,r.text)
        quiet = self.quiet()
        self.assertFalse(self.tick_until_run(quiet)['claimed'])
        self.assertEqual(quiet.requests,[])
        self.assertEqual(self.plan(pid)['status'],'cancelled')
        self.assertEqual(self.plan(pid)['grant']['status'],'revoked')
        self.assertEqual(len(self.session(sid)['proposals']),1)
        version = self.plan(pid)['version']
        r = self.client.post(BASE+'/plans/'+pid+'/followup',json={'action':'resume','expected_version':version})
        self.assertEqual(r.status_code,409,r.text)

    def test_original_user_access_change_revokes_grant_before_model(self):
        manager_id = self.manager()
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        user = next(u for u in self.admin_client.get('/api/users').json()['items'] if u['id']==manager_id)
        r = self.admin_client.put('/api/users/'+str(manager_id),json={
            'request_id':'revoke_'+uuid4().hex, 'access_version':user['access_version'],
            'role':'manager','display_name':user['display_name'],'active':False})
        self.assertEqual(r.status_code,200,r.text)
        with SessionLocal() as db:
            signals = list(db.scalars(select(WakeEvent).where(WakeEvent.topic=='access.changed')))
            self.assertTrue(any(s.source_ref['type']=='user_access_receipt' for s in signals))
        quiet = self.quiet()
        self.assertFalse(self.tick_until_run(quiet)['claimed'])
        self.assertEqual(quiet.requests,[])
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(FollowupGrant).where(FollowupGrant.plan_id==pid)).status,'revoked')
            self.assertEqual(db.scalar(select(func.count()).select_from(AssistantProposal).where(AssistantProposal.session_id==sid)),0)
        r = self.client.get(BASE+'/plans/'+pid)
        self.assertIn(r.status_code,(401,403),r.text)

    def test_original_store_disable_revokes_grant_before_model(self):
        self.manager()
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        store = next(s for s in self.admin_client.get('/api/stores').json()['items'] if s['id']==1)
        r = self.admin_client.put('/api/stores/1',json={'code':store['code'],'name':store['name'],'active':False})
        self.assertEqual(r.status_code,200,r.text)
        with SessionLocal() as db:
            self.assertTrue(db.scalar(select(WakeEvent).where(WakeEvent.topic=='store.access_changed')))
        quiet = self.quiet()
        self.assertFalse(self.tick_until_run(quiet)['claimed'])
        self.assertEqual(quiet.requests,[])
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(FollowupGrant).where(FollowupGrant.plan_id==pid)).status,'revoked')
            self.assertEqual(db.get(Task,steps[0]['completion_conditions'][0]['task_id']).status,'open')
        r = self.client.get(BASE+'/plans/'+pid)
        self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(r.json(),{'detail':'当前门店已停用或不存在，请重新选择门店后再办理'})

    def test_late_model_after_grant_pause_cannot_publish_card(self):
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        provider = self.preparation(steps[0])
        def pause_before_response(number,body):
            if number == 1: self.followup(pid,'pause')
        provider.before_response = pause_before_response
        outcome = self.tick_until_run(provider)
        self.assertTrue(outcome['claimed'],outcome)
        self.assertEqual(len(provider.requests),1)
        self.assertEqual(self.session(sid)['proposals'],[])
        self.assertEqual(self.plan(pid)['status'],'paused')
        with SessionLocal() as db:
            self.assertIn(db.get(Run,outcome['run_id']).status,('cancelled','failed'))
            self.assertEqual(db.get(Task,steps[0]['completion_conditions'][0]['task_id']).status,'open')

    def test_duplicate_signal_and_due_poll_never_duplicate_card(self):
        from datetime import timedelta
        from app.assistant_runtime_outbox import emit_wake_event
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        self.assertTrue(self.tick_until_run(self.preparation(steps[0]))['claimed'])
        quiet = self.quiet()
        self.assertFalse(self.tick_until_run(quiet)['claimed'])
        before = (self.count(WakeEvent),self.count(Run),self.count(AssistantProposal),self.count(WorkItem))
        with SessionLocal() as db:
            event = db.scalar(select(WakeEvent).where(WakeEvent.state=='dispatched',WakeEvent.topic=='flow'))
            self.assertIsNotNone(event)
            old = (event.id,event.state,event.attempt,event.next_attempt_at,event.version)
            refs = {key:getattr(event,key) for key in ('store_id','object_ref','proposal_id','task_id','plan_id','source_ref')}
            for _ in range(3):
                same = emit_wake_event(db,event.signal_key,event.topic,refs)
                self.assertEqual((same.id,same.state,same.attempt,same.next_attempt_at,same.version),old)
            db.commit()
        with quiet.installed():
            for _ in range(3):
                outcome = asyncio.run(Worker(clock=lambda:utcnow()+timedelta(minutes=6)).tick())
                self.assertFalse(outcome['claimed'],outcome)
                self.assertIsNone(outcome['error'],outcome)
        self.assertEqual(quiet.requests,[])
        self.assertEqual((self.count(WakeEvent),self.count(Run),self.count(AssistantProposal),self.count(WorkItem)),before)

    def test_manager_can_complete_granted_native_actions_without_admin_identity(self):
        self.manager()
        sid,pid,steps = self.create_plan()
        self.followup(pid,'enable')
        result = self.tick_until_run(self.preparation(steps[0]))
        self.assertEqual(result['status'],'succeeded',result)
        cards = self.session(sid)['proposals']
        self.assertEqual(len(cards),1,cards)
        r = self.confirm(sid,cards[0]);self.assertEqual(r.status_code,200,r.text)
        with SessionLocal() as db:
            self.assertEqual(db.get(Task,steps[0]['completion_conditions'][0]['task_id']).status,'done')
            run = db.get(Run,result['run_id'])
            self.assertEqual(db.get(FollowupGrant,run.grant_id).owner_role,'manager')
            self.assertEqual(run.auth_kind,'grant')

if __name__ == "__main__": unittest.main()
