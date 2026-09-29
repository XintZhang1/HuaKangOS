"""Offline runner selection cannot silently discard newly added regression files."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture_env
import tempfile
import unittest
from run_validation import selected_suites


class ValidationSelection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=fixture_env.VALIDATION)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'tests').mkdir()
        for name in ('test_z.py', 'test_a.py', 'test_browser_ui.py', 'helper.py'):
            (self.root / 'tests' / name).write_text('')

    def test_default_discovers_every_backend_suite(self):
        self.assertEqual(selected_suites(self.root), ['test_a.py', 'test_z.py'])
        (self.root / 'tests' / 'test_new_domain.py').write_text('')
        self.assertIn('test_new_domain.py', selected_suites(self.root))

    def test_explicit_selection_preserves_order(self):
        self.assertEqual(selected_suites(self.root, ['test_z.py', 'test_a.py']),
                         ['test_z.py', 'test_a.py'])

    def test_duplicates_unknown_paths_and_browser_are_rejected(self):
        for selected in (['test_a.py', 'test_a.py'], ['missing.py'],
                         ['../test_a.py'], ['test_browser_ui.py']):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                selected_suites(self.root, selected)

    def test_empty_backend_suite_is_not_success(self):
        for path in (self.root / 'tests').glob('test_[az].py'):
            path.unlink()
        with self.assertRaises(ValueError):
            selected_suites(self.root)

    def test_node_summary_markers_are_accepted_across_versions(self):
        # The executed-test-count guard must not turn a green Node run into a
        # failure (or a silent skip) just because the summary marker changed.
        import re
        pattern = re.compile(r'^[#\u2139] tests (\d+)$', re.M)
        for marker in ('#', '\u2139'):
            with self.subTest(marker=marker):
                log = marker + ' tests 55\n' + marker + ' fail 0\n'
                match = pattern.search(log)
                self.assertIsNotNone(match)
                self.assertEqual(int(match.group(1)), 55)
                self.assertEqual(int(re.search(r'^[#\u2139] fail (\d+)$', log, re.M).group(1)), 0)
        self.assertIsNone(pattern.search('tests 55\n'))
