"""M8.1 item 5: a slow model turn must not become a duplicate or a silent retry.

The slow turn is injected on a real confirmed business card: the model answers
the preparation turn after a genuine delay, and the assertions are the ones that
can actually be proved - one model round per step, no second write, and no
automatic retry once the run has reached a terminal state.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import time
import unittest
from sqlalchemy import func, select
import test_runtime_integration as baseline
from app.db import SessionLocal
from app.assistant_runtime_models import Run
from app.assistant_worker import Worker
from app.flow_models import Customer
from fake_provider import Provider, customer_steps, reply, tool


class DelayInjection(unittest.TestCase):
    setUp = baseline.RuntimeIntegration.setUp
    login = baseline.RuntimeIntegration.login
    count = baseline.RuntimeIntegration.count
    new_run = baseline.RuntimeIntegration.new_run
    session = baseline.RuntimeIntegration.session
    confirm = baseline.RuntimeIntegration.confirm

    def slow_provider(self, steps, seconds, from_request=2):
        """The same deterministic steps, answered after a real delay."""
        def before_response(request_no, body):
            if request_no >= from_request:
                time.sleep(seconds)
        return Provider(steps, before_response=before_response)

    def run_tick(self, provider):
        import asyncio
        with provider.installed():
            return asyncio.run(Worker().tick())

    def test_a_slow_preparation_turn_completes_once_without_a_duplicate_round(self):
        name = '合成延迟' + str(id(self))[-6:]
        sid, run, _ = self.new_run('新建客户' + name + '，暂不允许联系。')
        before = self.count(Customer)
        steps = customer_steps(name)
        provider = self.slow_provider(steps, 1.5)
        result = self.run_tick(provider)
        self.assertIsNone(result['error'], result)
        self.assertEqual(result['status'], 'succeeded', result)
        # The delay must not be turned into an extra model round or a replay.
        self.assertEqual(len(provider.requests), len(steps), provider.requests)
        # Preparing still writes nothing; only the employee click does.
        self.assertEqual(self.count(Customer), before)
        with SessionLocal() as db:
            row = db.get(Run, run['id'])
            self.assertEqual(row.status, 'succeeded')
        card = self.session(sid)['proposals'][0]
        confirmed = self.confirm(sid, card)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(self.count(Customer), before + 1)
        # The click is idempotent even after the slow turn.
        again = self.confirm(sid, card)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(self.count(Customer), before + 1)

    def test_a_terminal_run_is_never_re_executed_by_another_tick(self):
        name = '合成不重试' + str(id(self))[-6:]
        sid, run, _ = self.new_run('新建客户' + name + '，暂不允许联系。')
        provider = self.slow_provider(customer_steps(name), 0.8)
        self.assertEqual(self.run_tick(provider)['status'], 'succeeded')
        rounds = len(provider.requests)
        self.assertGreaterEqual(rounds, 1)
        with SessionLocal() as db:
            status, attempt, fence = db.execute(select(Run.status, Run.attempt, Run.fence)
                                                .where(Run.id == run['id'])).one()
        self.assertEqual(status, 'succeeded')
        # Two further ticks: no new claim, no new model call, no new run row.
        runs_before = self.count(Run)
        for _ in range(2):
            idle = Provider([reply('不应被调用')])
            self.run_tick(idle)
            self.assertEqual(len(idle.requests), 0, 'a terminal run must not be retried')
        self.assertEqual(len(provider.requests), rounds, 'the finished run must not be re-asked')
        self.assertEqual(self.count(Run), runs_before)
        with SessionLocal() as db:
            after = db.execute(select(Run.status, Run.attempt, Run.fence)
                               .where(Run.id == run['id'])).one()
        self.assertEqual(tuple(after), (status, attempt, fence),
                         'an idle tick must not change the finished run')


if __name__ == '__main__':
    unittest.main()