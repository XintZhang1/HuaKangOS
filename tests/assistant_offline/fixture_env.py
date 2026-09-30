"""Synthetic, explicitly isolated environment. Import before any application module."""
from pathlib import Path
import json
import os
import secrets
import sys

if not os.environ.get('HUAKANGOS_SOURCE'):
    raise RuntimeError('Use run_isolated.py with an explicit disposable source checkout')
ROOT = Path(os.environ['HUAKANGOS_SOURCE']).resolve()
VALIDATION = Path(__file__).resolve().parent
# Synthetic state never lives in the application source, and the application
# itself refuses to read an assistant config from inside its own checkout
# (business_assistant_service.load_config). So the runtime directory - the
# synthetic database, the random password and the synthetic config - stays
# outside the repository, while the suites, the run record and the evidence
# live in one place inside it. HUAKANGOS_RUNTIME names that directory.
if VALIDATION == ROOT or any(VALIDATION.is_relative_to(ROOT / folder)
                             for folder in ('app', 'web', 'migrations')):
    raise RuntimeError('Validation must remain outside the application source')
RUNTIME = Path(os.environ.get('HUAKANGOS_RUNTIME') or (VALIDATION / 'runtime')).resolve()
if RUNTIME.is_relative_to(ROOT):
    raise RuntimeError('Synthetic runtime must stay outside the source checkout')
if not (ROOT / 'app/main.py').is_file():
    raise RuntimeError('Source checkout is incomplete')
if (ROOT / '.env').exists():
    raise RuntimeError('Refuse to import a source tree with a .env file')
RUNTIME.mkdir(exist_ok=True)
CONFIG = RUNTIME / 'synthetic-assistant.json'
CONFIG.write_text(json.dumps({'enabled': True, 'api_key': 'SYNTHETIC-NOT-A-CREDENTIAL',
                             'model': 'deepseek-flash', 'provider': 'deepseek',
                             'synthetic': True, 'tool_profile': 'business_v1',
                             'max_rounds': 8, 'turn_timeout_seconds': 60}))
PASSWORD = RUNTIME / 'fixture-password'
if not PASSWORD.exists():
    PASSWORD.write_text(secrets.token_urlsafe(22))
    PASSWORD.chmod(0o600)
os.environ.update({
    'APP_ENV':'test', 'DATABASE_URL': 'sqlite:///' + str(RUNTIME / 'synthetic.sqlite'),
    'SCHEDULER_ENABLED':'false', 'SCHEDULER_MODE':'off', 'ALLOW_AI_EXTERNAL':'false',
    'DEEPSEEK_API_KEY':'', 'COOKIE_SECURE':'false', 'LEGACY_BUSINESS_WRITE':'false',
    'FILE_SCAN_MODE':'structure_only', 'FILE_STORAGE_MODE':'blob',
    'ASSISTANT_HOME_ENABLED':'true', 'ASSISTANT_RUNTIME_ENABLED':'true',
    'ASSISTANT_FOLLOWUP_ENABLED':'true', 'ASSISTANT_NOTIFICATIONS_ENABLED':'true',
    'ALLOWED_HOSTS':'localhost,127.0.0.1,testserver',
    'BUSINESS_ASSISTANT_CONFIG': str(CONFIG), 'HUAKANGOS_INITIAL_PASSWORD':PASSWORD.read_text(),
    'HUAKANGOS_LOCAL_PREVIEW':'0',
})
sys.path.insert(0, str(ROOT))
