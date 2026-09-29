"""The real-browser pipeline must refuse to look green when it is not native.

These tests exercise the pipeline's own contract. They never launch a browser,
so they run in the default `off` regression and can never be mistaken for the
M8.4 real-browser evidence itself.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env                                            # noqa: F401  (isolation first)
import browser_evidence
import run_browser_pipeline as pipeline


def page(name, *, api=('GET', '/api/stores', 200), errors=()):
    return {name + '.json': {'page_errors': list(errors),
                             'requests': [{'method': api[0], 'path': api[1], 'status': api[2]}]}}


class EvidenceBundle(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=fixture_env.VALIDATION)
        self.addCleanup(temp.cleanup)
        self.evidence = Path(temp.name)
        self.summary = {'complete': True, 'scope': 'full', 'browser_transport': 'native'}

    def write(self, name, record, png=False):
        (self.evidence / (name + '.json')).write_text(json.dumps(record), encoding='utf-8')
        if png:
            (self.evidence / (name + '.png')).write_bytes(b'\x89PNG\r\n\x1a\n')

    def test_bundle_counts_pages_errors_and_api_traffic(self):
        self.write('test_a', {'page_errors': [], 'requests': [
            {'method': 'GET', 'path': '/api/auth/me', 'status': 401},
            {'method': 'GET', 'path': '/static/app.js', 'status': 200}]}, png=True)
        self.write('test_b', {'page_errors': ['boom'], 'requests': [
            {'method': 'POST', 'path': '/api/business-assistant/sessions', 'status': 201}]})
        bundle = browser_evidence.collect(self.evidence, self.summary, mode='native',
                                          expected_tests=['test_a', 'test_b'])
        self.assertEqual(bundle['page_count'], 2)
        self.assertEqual(bundle['page_errors_total'], 1)
        self.assertTrue(bundle['native_transport'])
        self.assertEqual(bundle['real_model_calls'], 0)
        self.assertEqual(bundle['pages'][0]['api_requests'], 1)
        self.assertEqual(bundle['pages'][0]['screenshot'], 'test_a.png')
        self.assertEqual(bundle['pages'][1]['api_statuses'], [201])

    def test_missing_page_evidence_is_a_failure(self):
        self.write('test_a', {'page_errors': [], 'requests': [{'path': '/api/x', 'status': 200}]})
        with self.assertRaises(ValueError):
            browser_evidence.collect(self.evidence, self.summary, mode='native',
                                     expected_tests=['test_a', 'test_b'])

    def test_native_bundle_requires_original_api_traffic(self):
        # A "native" run whose pages never reached the service is a bridge run
        # wearing a native label; the bundle must reject it.
        self.write('test_a', {'page_errors': [], 'requests': [
            {'method': 'GET', 'path': '/static/app.js', 'status': 200}]})
        with self.assertRaises(ValueError):
            browser_evidence.collect(self.evidence, self.summary, mode='native',
                                     expected_tests=['test_a'])

    def test_fixture_mode_is_never_reported_as_native(self):
        self.write('test_a', {'page_errors': [], 'requests': []})
        bundle = browser_evidence.collect(self.evidence, self.summary, mode='fixture',
                                          expected_tests=['test_a'])
        self.assertFalse(bundle['native_transport'])
        self.assertEqual(bundle['mode'], 'fixture')

    def test_incomplete_page_records_are_rejected(self):
        self.write('test_a', {'requests': []})
        with self.assertRaises(ValueError):
            browser_evidence.collect(self.evidence, self.summary, mode='native',
                                     expected_tests=['test_a'])


class ValidationWiring(unittest.TestCase):
    def test_expected_pages_come_from_the_evidence_directory(self):
        import run_validation
        temp = tempfile.TemporaryDirectory(dir=fixture_env.VALIDATION)
        self.addCleanup(temp.cleanup)
        evidence = Path(temp.name)
        with self.assertRaises(RuntimeError):
            run_validation.expected_browser_tests(evidence)
        for name in ('test_b', 'test_a'):
            (evidence / (name + '.json')).write_text('{}', encoding='utf-8')
        self.assertEqual(run_validation.expected_browser_tests(evidence), ['test_a', 'test_b'])

    def test_transport_label_follows_the_requested_mode(self):
        import run_validation
        temp = tempfile.TemporaryDirectory(dir=fixture_env.VALIDATION)
        self.addCleanup(temp.cleanup)
        evidence = Path(temp.name)
        (evidence / 'test_a.json').write_text(
            json.dumps({'page_errors': [], 'requests': [{'path': '/api/x', 'status': 200}]}),
            encoding='utf-8')
        (evidence / 'source-and-suite.json').write_text(json.dumps(
            {'source_sha256': 's', 'suite_sha256': 't'}), encoding='utf-8')
        summary = {'complete': True, 'scope': 'full', 'browser_transport': 'native'}
        run_validation.write_browser_bundle(evidence, summary, 'native', 1)
        bundle = json.loads((evidence / 'browser-evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(bundle['run']['browser_transport'], 'native')
        self.assertEqual(bundle['fingerprints'], {'source_sha256': 's', 'suite_sha256': 't'})

    def test_page_count_must_match_the_executed_tests(self):
        import run_validation
        temp = tempfile.TemporaryDirectory(dir=fixture_env.VALIDATION)
        self.addCleanup(temp.cleanup)
        evidence = Path(temp.name)
        (evidence / 'test_a.json').write_text(
            json.dumps({'page_errors': [], 'requests': [{'path': '/api/x', 'status': 200}]}),
            encoding='utf-8')
        (evidence / 'source-and-suite.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            run_validation.write_browser_bundle(
                evidence, {'complete': True, 'browser_transport': 'native'}, 'native', 2)


class PipelinePreflight(unittest.TestCase):
    def test_missing_explicit_browser_is_refused(self):
        with self.assertRaises(ValueError):
            pipeline.find_browser(str(fixture_env.VALIDATION / 'no-such-browser.exe'))

    def test_explicit_browser_is_used_verbatim(self):
        target = fixture_env.VALIDATION / 'synthetic-browser.bin'
        target.write_bytes(b'not a browser')
        self.addCleanup(target.unlink)
        self.assertEqual(pipeline.find_browser(str(target)), str(target))

    def test_environment_browser_is_accepted_only_when_it_exists(self):
        import os
        target = fixture_env.VALIDATION / 'synthetic-browser-env.bin'
        target.write_bytes(b'not a browser')
        self.addCleanup(target.unlink)
        previous = os.environ.get('HUAKANGOS_CHROMIUM')
        self.addCleanup(lambda: os.environ.__setitem__('HUAKANGOS_CHROMIUM', previous)
                        if previous is not None else os.environ.pop('HUAKANGOS_CHROMIUM', None))
        os.environ['HUAKANGOS_CHROMIUM'] = str(target)
        self.assertEqual(pipeline.find_browser(None), str(target))

    def test_default_output_stays_outside_the_source_and_names_the_transport(self):
        for mode, bucket in (('native', 'browser-native'), ('fixture', 'browser-fixture')):
            with self.subTest(mode=mode):
                output = pipeline.default_output(mode)
                self.assertNotIn('HuaKangOS', output.name)
                self.assertIn(bucket, str(output))
                self.assertFalse(output == fixture_env.ROOT)

    def test_source_fingerprint_tracks_file_content(self):
        temp = tempfile.TemporaryDirectory(dir=fixture_env.VALIDATION)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for folder in ('app', 'web', 'migrations'):
            (root / folder).mkdir()
        (root / 'app' / 'main.py').write_text('print(1)', encoding='utf-8')
        first = pipeline.source_fingerprint(root)
        (root / 'app' / 'main.py').write_text('print(2)', encoding='utf-8')
        self.assertNotEqual(first, pipeline.source_fingerprint(root))


if __name__ == '__main__':
    unittest.main()