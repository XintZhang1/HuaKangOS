"""Offline worker boundary checks; execute only from an external source mirror."""
import asyncio
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import uuid

if (Path(__file__).resolve().parents[2] / '.git').exists():
    raise RuntimeError('Mirror source outside the repository before importing app')

from app import ops_worker
from app.ops_context import SourceContext, build_manifest
from app.ops_store import OpsStore


def tool_call(identifier, name='read_code', **arguments):
    return {'id': identifier, 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(arguments)}}


def tool_response(*calls):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {
        'content': None, 'reasoning_content': 'synthetic reasoning must be discarded',
        'tool_calls': list(calls)}}], 'usage': {'prompt_tokens': 12, 'completion_tokens': 3}}


def final_response(report):
    return {'choices': [{'finish_reason': 'stop', 'message': {
        'content': json.dumps(report)}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 4}}


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        runtime = Path(os.environ.get('OPS_REVIEW_RUNTIME', tempfile.gettempdir()))
        self.root = runtime / ('huakangos-worker-fixture-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.source = self.root / 'release'
        (self.source / 'app').mkdir(parents=True)
        (self.source / 'docs').mkdir()
        (self.source / 'app/example.py').write_text('one\n\nthree\nfour\nfive\n', encoding='utf-8')
        (self.source / 'ARCHITECTURE.md').write_text('Synthetic contract.', encoding='utf-8')
        (self.source / 'docs/阿里云试运行与运维助手.md').write_text('Synthetic ops.', encoding='utf-8')
        manifest = build_manifest(self.source, 'a' * 40)
        (self.source / 'ops-source-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.context = SourceContext(self.source)
        self.key = self.root / 'synthetic-key'
        self.key.write_text('synthetic-only-never-a-live-credential', encoding='utf-8')
        self.config = {'deepseek_key_file': str(self.key), 'mcp_url': 'http://127.0.0.1:1/mcp',
                       'agent_token': 'synthetic-agent', 'worker_token': 'synthetic-worker'}
        self.job = dict(title='Synthetic feedback', description='Only fabricated source and responses.',
                        category='bug', route='work')
        self.requests, self.executed = [], []
        # A missed mock must fail before any socket reaches a real service.
        for name in ('connect', 'connect_ex'):
            blocker = patch.object(socket.socket, name, side_effect=AssertionError('Network is disabled'))
            blocker.start()
            self.addCleanup(blocker.stop)
        blocker = patch.object(socket, 'create_connection', side_effect=AssertionError('Network is disabled'))
        blocker.start()
        self.addCleanup(blocker.stop)

    def report(self, line=3):
        return {'summary': 'Synthetic review with actual bounded source evidence only.',
                'classification': 'bug', 'risk': 'low',
                'evidence': [{'path': 'app/example.py', 'line': line,
                              'sha256': self.context.files['app/example.py']}],
                'proposed_changes': ['Review the synthetic example.'],
                'acceptance_checks': ['Check only the synthetic fixture.']}

    async def analyze_responses(self, responses):
        test = self

        class FakeMcp:
            def __init__(self, *_args, **_kwargs):
                pass

            async def rpc(self, method, _params):
                test.assertEqual(method, 'tools/list')
                return {'tools': ops_worker.READ_TOOLS}

            async def call(self, name, arguments):
                if name == 'source_snapshot':
                    return test.context.snapshot()
                test.executed.append((name, arguments))
                if name == 'read_code':
                    return test.context.read(**arguments)
                return {'healthy': True}

        class FakeResponse:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload
                self.content = json.dumps(payload).encode()

            def json(self):
                return self.payload

        class FakeProvider:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            async def post(self, _url, *, headers, json):
                test.requests.append(copy.deepcopy(json))
                return FakeResponse(responses[len(test.requests) - 1])

        with patch.object(ops_worker, 'McpClient', FakeMcp), patch.object(ops_worker.httpx, 'AsyncClient', FakeProvider):
            return await ops_worker.analyze(self.config, self.job, self.context)

    async def test_multiple_calls_keep_pairing_and_real_read_windows(self):
        calls = [tool_call('a', path='app/example.py', start_line=3, line_count=2),
                 tool_call('b', path='app/not-in-manifest.py'),
                 tool_call('c', 'service_health')]
        report = await self.analyze_responses([tool_response(*calls), final_response(self.report(4))])
        messages = self.requests[1]['messages']
        assistant = next(m for m in messages if m['role'] == 'assistant')
        results = [m for m in messages if m['role'] == 'tool']
        self.assertEqual(assistant['tool_calls'], calls)
        self.assertEqual([m['tool_call_id'] for m in results], ['a', 'b', 'c'])
        self.assertIn('error', json.loads(results[1]['content']))
        self.assertNotIn('reasoning_content', assistant)
        self.assertEqual(report['tool_calls'], 3)
        self.assertEqual(report['usage'], {'calls': 2, 'prompt_tokens': 22, 'completion_tokens': 7})
        self.assertEqual(report['release_id'], self.context.release_id)

    async def test_duplicate_ids_reject_entire_batch_before_tool_execution(self):
        calls = [tool_call('duplicate', path='app/example.py'),
                 tool_call('duplicate', 'service_health')]
        with self.assertRaisesRegex(ops_worker.AnalysisError, '^invalid_tool_call$'):
            await self.analyze_responses([tool_response(*calls)])
        self.assertEqual(self.executed, [])

    async def test_unread_evidence_is_rejected_without_weakening_validation(self):
        responses = [tool_response(tool_call('a', path='app/example.py', start_line=1, line_count=2)),
                     final_response(self.report(3))]
        with self.assertRaisesRegex(ops_worker.AnalysisError, '^unread_source_evidence$'):
            await self.analyze_responses(responses)

    async def test_finalize_rejects_provider_tools_at_tool_threshold(self):
        responses = [tool_response(*[tool_call(f'first-{i}', path='app/example.py', start_line=3, line_count=1)
                                      for i in range(5)]),
                     tool_response(*[tool_call(f'second-{i}', 'service_health') for i in range(5)]),
                     tool_response(tool_call('forbidden', 'service_health')),
                     final_response(self.report())]
        with self.assertRaisesRegex(ops_worker.AnalysisError, '^tools_after_finalize$'):
            await self.analyze_responses(responses)
        self.assertEqual(len(self.executed), 10)
        self.assertEqual(self.requests[2]['tool_choice'], 'none')

    async def test_finalize_rejects_provider_tools_at_turn_threshold(self):
        responses = [tool_response(tool_call(f'turn-{i}', path='app/example.py', start_line=3, line_count=1))
                     for i in range(4)]
        responses += [tool_response(tool_call('forbidden', 'service_health')), final_response(self.report())]
        with self.assertRaisesRegex(ops_worker.AnalysisError, '^tools_after_finalize$'):
            await self.analyze_responses(responses)
        self.assertEqual(len(self.executed), 4)
        self.assertEqual(self.requests[4]['tool_choice'], 'none')

    async def test_finalize_accepts_valid_report_with_reserved_budget(self):
        responses = [tool_response(*[tool_call(f'first-{i}', path='app/example.py', start_line=3, line_count=1)
                                      for i in range(5)]),
                     tool_response(*[tool_call(f'second-{i}', 'service_health') for i in range(5)]),
                     final_response(self.report())]
        report = await self.analyze_responses(responses)
        self.assertEqual(report['tool_calls'], 10)
        self.assertEqual(report['usage']['calls'], 3)
        self.assertEqual(self.requests[-1]['response_format'], {'type': 'json_object'})

    def test_final_evidence_checks_hash_bounds_and_immutable_source(self):
        reads = {'app/example.py': [(3, 4)]}
        for line in (2, 5, True):
            with self.subTest(line=line), self.assertRaises(ops_worker.AnalysisError):
                ops_worker.validate_report(self.report(line), self.context, reads)
        wrong_hash = self.report()
        wrong_hash['evidence'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ops_worker.AnalysisError, '^unread_source_evidence$'):
            ops_worker.validate_report(wrong_hash, self.context, reads)
        (self.source / 'app/example.py').write_text('tampered source', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Source changed'):
            ops_worker.validate_report(self.report(), self.context, reads)

    async def test_analysis_timeout_leaves_lease_margin_after_old_notifications(self):
        path = self.root / 'queue.sqlite'
        OpsStore.initialize(path)
        store = OpsStore(path)
        clock = [1000.0]
        submitted = lambda: store.submit(owner_id=1, store_id=1, request_id=str(uuid.uuid4()), **self.job)['id']
        test = self
        delivered = []

        class FakeMcp:
            def __init__(self, *_args, **_kwargs):
                pass

            async def call(self, name, arguments):
                test.assertEqual(name, 'enqueue_change_review')
                test.assertTrue(store.begin_notification(arguments['job_id']))
                clock[0] += 180
                delivered.append(arguments['job_id'])
                store.notification_result(arguments['job_id'], {'status': 'sent',
                    'event_id': 'huakangos-ops:' + arguments['job_id']})

        async def simulate_timeout(coroutine, timeout):
            self.assertEqual(timeout, 720)
            coroutine.close()
            current = store.get(new_id)
            self.assertEqual(current['status'], 'analyzing')
            self.assertEqual(current['lease_until'] - clock[0], 900)
            clock[0] += timeout
            raise asyncio.TimeoutError

        with patch('app.ops_store.time.time', side_effect=lambda: clock[0]):
            old_id = submitted()
            old = store.claim(self.context.release_id)
            store.analysis_result(old_id, old['lease_token'], report={'release_id': self.context.release_id})
            new_id = submitted()
            with patch.object(ops_worker, 'McpClient', FakeMcp), patch.object(ops_worker.asyncio, 'wait_for', simulate_timeout):
                self.assertTrue(await ops_worker.tick(self.config, store, self.context))
            current = store.get(new_id)
            self.assertEqual(current['status'], 'needs_attention')
            self.assertEqual(current['error_code'], 'analysis_TimeoutError')
            self.assertIsNone(current['lease_until'])
            self.assertEqual(current['attempts'], 1)
            self.assertEqual(delivered, [old_id])
            self.assertEqual(store.get(old_id)['status'], 'awaiting_cutie')


if __name__ == '__main__':
    unittest.main()
