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
