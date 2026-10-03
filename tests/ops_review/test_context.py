"""Synthetic source and evidence boundaries; no service, model or private data."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from app.ops_context import SourceContext, allowed_name, build_manifest
from app.ops_worker import AnalysisError, validate_report


BASE_SHA = 'a' * 40
SOURCE_PATH = 'app/example.py'


class SourceContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture_parent = Path(tempfile.gettempdir()).resolve()
        self.root = self.fixture_parent / ('huakangos-ops-context-' + uuid.uuid4().hex)
        # Inherit the test runner's directory permissions on Windows. Python
        # 3.13's private 0700 temp directories are inaccessible to this sandbox.
        self.root.mkdir()
        self.addCleanup(self.cleanup_source)
        self.source = self.root / SOURCE_PATH
        self.source.parent.mkdir()
        self.source.write_text('alpha = 1\nbeta = 2\ngamma = 3\ndelta = 4\n', encoding='utf-8')

    def cleanup_source(self):
        if (self.root.is_symlink() or self.root.resolve().parent != self.fixture_parent
                or not self.root.name.startswith('huakangos-ops-context-')):
            raise RuntimeError('Refusing cleanup outside the synthetic fixture directory')
        shutil.rmtree(self.root)

    def context(self):
        manifest = build_manifest(self.root, BASE_SHA)
        (self.root / 'ops-source-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return SourceContext(self.root)

    def report(self, context, line=2):
        return {
            'summary': 'Synthetic investigation with source evidence; no actual defect claimed.',
            'classification': 'needs_information', 'risk': 'low',
            'evidence': [{'path': SOURCE_PATH, 'line': line,
                          'sha256': context.files[SOURCE_PATH]}],
            'proposed_changes': ['Review the synthetic source first.'],
            'acceptance_checks': ['Check only the synthetic source evidence.'],
        }

    def test_inventory_excludes_runtime_private_and_escaping_paths(self):
        forbidden = ['.env', 'app/.env', 'app/.private.json', 'data/trial.sqlite',
                     '../app/example.py', 'app/../../outside.py', '/app/example.py',
                     'C:/app/example.py', 'app\\example.py', 'docs/unapproved.md',
                     'web/workflow-guides.json', 'web/workflow-handbook.html']
        for name in forbidden:
            with self.subTest(path=name):
                self.assertFalse(allowed_name(name))
        (self.root / '.env').write_text('SYNTHETIC_ONLY=1', encoding='utf-8')
        (self.root / 'data').mkdir()
        (self.root / 'data' / 'trial.sqlite').write_bytes(b'synthetic non-database bytes')
        (self.root / 'app' / 'oversized.py').write_bytes(b'x' * 512_001)
        context = self.context()
        self.assertEqual(set(context.files), {SOURCE_PATH})
        for name in forbidden:
            with self.subTest(read=name), self.assertRaises(ValueError):
                context.read(name)

    def test_manifest_rejects_escape_even_with_matching_fingerprint(self):
        files = {'app/../../outside.py': hashlib.sha256(b'synthetic').hexdigest()}
        manifest = {'base_sha': BASE_SHA, 'files': files,
                    'release_id': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}
        (self.root / 'ops-source-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Invalid source inventory'):
            SourceContext(self.root)

    def test_manifest_and_source_hashes_are_reverified(self):
        context = self.context()
        self.source.write_text('changed synthetic source\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Source changed after deployment'):
            context.read(SOURCE_PATH)
        with self.assertRaisesRegex(RuntimeError, 'Source changed after deployment'):
            context.search('changed')
        manifest_path = self.root / 'ops-source-manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['release_id'] = '0' * 64
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Invalid source fingerprint'):
            SourceContext(self.root)

    def test_read_window_preserves_exact_lines_and_rejects_invalid_budget(self):
        context = self.context()
        result = context.read(SOURCE_PATH, start_line=2, line_count=2)
        self.assertEqual(result['content'], '2: beta = 2\n3: gamma = 3')
        self.assertEqual(result['start_line'], 2)
        self.assertEqual(result['total_lines'], 4)
        self.assertEqual(result['release_id'], context.release_id)
        self.assertEqual(result['sha256'], context.files[SOURCE_PATH])
        for start, count in [(0, 1), (-1, 1), (True, 1), (1, False), (1, 0), (1, 101), (1, 1.0)]:
            with self.subTest(start=start, count=count), self.assertRaises(ValueError):
                context.read(SOURCE_PATH, start, count)
        self.assertEqual(context.read(SOURCE_PATH, 5, 1)['content'], '')

    def test_oversized_rendered_window_requires_smaller_read(self):
        self.source.write_text('x' * 12_000 + '\nsmall\n', encoding='utf-8')
        context = self.context()
        with self.assertRaisesRegex(ValueError, 'context budget'):
            context.read(SOURCE_PATH, 1, 1)
        self.assertEqual(context.read(SOURCE_PATH, 2, 1)['content'], '2: small')

    def test_evidence_requires_actual_read_window_and_matching_hash(self):
        context = self.context()
        reads = {SOURCE_PATH: [(2, 3)]}
        accepted = validate_report(self.report(context, 3), context, reads)
        self.assertEqual(accepted['release_id'], context.release_id)
        self.assertEqual(accepted['base_sha'], BASE_SHA)
        for line in (1, 4, True):
            with self.subTest(line=line), self.assertRaises(AnalysisError):
                validate_report(self.report(context, line), context, reads)
        with self.assertRaises(AnalysisError):
            validate_report(self.report(context), context, {})
        bad_hash = self.report(context)
        bad_hash['evidence'][0]['sha256'] = '0' * 64
        with self.assertRaises(AnalysisError):
            validate_report(bad_hash, context, reads)

    def test_evidence_cannot_claim_eof_or_changed_source(self):
        context = self.context()
        with self.assertRaises(AnalysisError):
            validate_report(self.report(context, 5), context, {SOURCE_PATH: [(1, 100)]})
        report = copy.deepcopy(self.report(context))
        self.source.write_text('modified after read\n', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            validate_report(report, context, {SOURCE_PATH: [(2, 3)]})


if __name__ == '__main__':
    unittest.main()
