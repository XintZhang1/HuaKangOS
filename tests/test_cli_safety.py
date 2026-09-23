import os
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.mark.parametrize('environment,mode,message',[
    ('local','quarantine','尚未写入数据'),
    ('production','clamav','正式环境禁止灌入演示数据'),
])
def test_unsafe_demo_initialization_refuses_before_creating_database(tmp_path,environment,mode,message):
    target=tmp_path/'must-not-create.sqlite'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+target.as_posix(),'APP_ENV':environment,
         'FILE_SCAN_MODE':mode,'COOKIE_SECURE':'true','ALLOWED_HOSTS':'localhost',
         'LEGACY_BUSINESS_WRITE':'false','ALLOW_AI_EXTERNAL':'false','SCHEDULER_ENABLED':'false',
         'HUAKANGOS_INITIAL_PASSWORD':'SyntheticOnly!NoBusiness2026','PYTHONUTF8':'1'}
    result=subprocess.run([sys.executable,'-m','app.cli','init','--demo'],cwd=Path(__file__).resolve().parents[1],env=env,
                          capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode!=0 and message in result.stderr
    assert not target.exists()
