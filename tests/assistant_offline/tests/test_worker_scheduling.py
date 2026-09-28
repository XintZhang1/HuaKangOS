"""Worker orchestration tests; fake only scheduler dependencies, no application writes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from app import assistant_worker as module


class WorkerScheduling(unittest.TestCase):
    def setUp(self):
        self.sessions=[]
        self.closed=[]
        @contextmanager
        def factory():
            session=object();self.sessions.append(session)
            try: yield session
            finally: self.closed.append(session)
        self.queue=SimpleNamespace(reclaim_expired=Mock(return_value=None),claim_next=Mock(return_value=None))
        self.outbox=SimpleNamespace(dispatch_one=AsyncMock(return_value=SimpleNamespace(state='dispatched')),
                                    poll_due_plan=AsyncMock(return_value=SimpleNamespace(state='checked')))
        self.runner=AsyncMock(return_value=SimpleNamespace(status='succeeded'))
        self.worker=module.Worker(session_factory=factory,queue=self.queue,outbox=self.outbox,runner=self.runner,
                                  clock=lambda:datetime(2026,9,29,4,0,0))
        self.worker._maintain=Mock()
        self.worker.beat_now=Mock()

    def flags(self, runtime=True,followup=True,notifications=True):
        return patch.object(module,'settings',replace(module.settings,assistant_runtime_enabled=runtime,
                   assistant_followup_enabled=followup,assistant_notifications_enabled=notifications))

    def tick(self):return asyncio.run(self.worker.tick())

    def test_each_scheduler_check_and_claim_has_a_separate_closed_session(self):
        with self.flags():result=self.tick()
        self.assertIsNone(result['error'],result)
        self.assertEqual(self.outbox.dispatch_one.await_count,1)
        self.assertEqual(self.outbox.poll_due_plan.await_count,1)
        self.assertEqual(len(self.sessions),4)
        self.assertEqual(len(set(map(id,self.sessions))),4)
        self.assertEqual(self.sessions,self.closed)
        self.assertFalse(result['claimed'])

    def test_disabled_switches_have_no_lazy_side_effects(self):
        with self.flags(False,False,False):result=self.tick()
        self.assertEqual(result['reason'],'runtime_disabled')
        self.assertEqual(self.sessions,[])
        self.outbox.dispatch_one.assert_not_awaited()
        self.outbox.poll_due_plan.assert_not_awaited()
        self.queue.claim_next.assert_not_called()

    def test_notifications_remain_read_only_when_runtime_disabled(self):
        with self.flags(False,False,True):result=self.tick()
        self.assertEqual(result['reason'],'runtime_disabled')
        self.outbox.dispatch_one.assert_awaited_once()
        self.outbox.poll_due_plan.assert_not_awaited()
        self.queue.claim_next.assert_not_called()
        self.runner.assert_not_awaited()

    def test_runtime_without_followup_does_not_poll_plans(self):
        with self.flags(True,False,False):result=self.tick()
        self.outbox.dispatch_one.assert_not_awaited()
        self.outbox.poll_due_plan.assert_not_awaited()
        self.queue.claim_next.assert_called_once()

    def test_followup_without_notifications_still_drives_signals(self):
        with self.flags(True,True,False):result=self.tick()
        self.outbox.dispatch_one.assert_awaited_once()
        self.outbox.poll_due_plan.assert_awaited_once()

    def test_scheduler_failure_does_not_starve_employee_run_or_leak_error_body(self):
        self.outbox.dispatch_one.side_effect=RuntimeError('SENSITIVE-MODEL-BODY-PASSWORD')
        self.queue.claim_next.return_value=SimpleNamespace(run_id='owned-interactive-run')
        with self.flags():result=self.tick()
        self.assertEqual(result['maintenance_errors'],{'dispatch':'RuntimeError'})
        self.assertNotIn('SENSITIVE',str(result))
        self.outbox.poll_due_plan.assert_awaited_once()
        self.runner.assert_awaited_once()
        self.assertTrue(result['claimed'])
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(self.worker.executed,1)

    def test_deferred_event_still_allows_due_plan_and_one_claim(self):
        self.outbox.dispatch_one.return_value=SimpleNamespace(state='pending')
        self.queue.claim_next.return_value=SimpleNamespace(run_id='one-run')
        with self.flags():result=self.tick()
        self.assertEqual(result['dispatch'],'pending')
        self.assertEqual(result['poll'],'checked')
        self.queue.claim_next.assert_called_once()
        self.runner.assert_awaited_once()

    def test_stop_requested_before_cycle_never_reads_or_claims(self):
        self.worker._stop.set()
        with self.flags():result=self.tick()
        self.assertEqual(result['reason'],'stopping')
        self.assertEqual(self.sessions,[])

    def test_stop_during_dispatch_prevents_poll_and_claim(self):
        async def stop(*args,**kwargs):
            self.worker._stop.set()
            return SimpleNamespace(state='dispatched')
        self.outbox.dispatch_one.side_effect=stop
        with self.flags():result=self.tick()
        self.assertEqual(result['reason'],'stopping')
        self.outbox.poll_due_plan.assert_not_awaited()
        self.queue.claim_next.assert_not_called()

    def test_cancellation_is_not_swallowed_into_scheduler_retry(self):
        self.outbox.dispatch_one.side_effect=asyncio.CancelledError
        with self.flags(),self.assertRaises(asyncio.CancelledError):self.tick()
        self.outbox.poll_due_plan.assert_not_awaited()
        self.queue.claim_next.assert_not_called()
        self.assertEqual(self.sessions,self.closed)

    def loop_delays(self, outcomes):
        values=iter(outcomes);delays=[]
        async def tick():return next(values)
        async def pause(seconds):
            delays.append(seconds)
            return len(delays)==len(outcomes)
        self.worker.tick=tick;self.worker._pause=pause
        asyncio.run(self.worker._serve())
        return delays

    def test_backlog_is_drained_without_idle_delay_between_events(self):
        delays=self.loop_delays([{'dispatch':'dispatched'},{'dispatch':'pending'},{'poll':'checked'},{}])
        self.assertEqual(delays[:3],[0,0,0])
        self.assertGreater(delays[3],0)

    def test_failed_scheduler_keeps_idle_backoff_instead_of_busy_loop(self):
        delays=self.loop_delays([{'error':'OperationalError'},{}])
        self.assertTrue(all(delay>0 for delay in delays))

    def test_executed_or_recovered_run_rechecks_queue_without_idle_sleep(self):
        self.assertEqual(self.loop_delays([{'claimed':True},{'recovered':'run'}]),[0,0])

    def test_stop_after_recovery_does_not_claim(self):
        def recover(*args,**kwargs):self.worker._stop.set()
        self.queue.reclaim_expired.side_effect=recover
        with self.flags():result=self.tick()
        self.queue.claim_next.assert_not_called()
        self.assertEqual(result['reason'],'stopping')

if __name__=='__main__':unittest.main()
