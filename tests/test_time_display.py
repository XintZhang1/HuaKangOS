"""Run the actual JavaScript UTC display contract from full pytest discovery."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_api_timestamp_display_across_browser_timezones():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for this local formatter contract, not to run the app')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/js/time_display.test.cjs'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
