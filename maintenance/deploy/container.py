"""Docker CLI wrapper for the application container.

The application container is the only process that writes the business database.
It is deliberately boxed in: non-root, no capabilities, read-only root filesystem,
bounded memory/CPU/PIDs, and published on loopback (or an explicitly configured
public port) only. Its lifecycle belongs to the controller alone, so it is created
with --restart=no; nothing else may resurrect it behind the controller's back.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import GateError

CONTAINER_UID = '10001:10001'
DOCKER_TIMEOUT = 120

# Passed through to the container. An allowlist, not a denylist: build/approval
# credentials (FEISHU_*, DEEPSEEK_CODE_*, MAINT_REPO_*, MAINT_SG_*) must never
# reach the application process.
APP_ENV_KEYS = (
    'APP_ENV', 'APP_TIMEZONE', 'ALLOWED_HOSTS', 'COOKIE_SECURE', 'SESSION_HOURS',
    'SCHEDULER_ENABLED', 'DAILY_REPORT_HOUR', 'DAILY_REPORT_MINUTE', 'REPORT_CATCHUP_DAYS',
    'ALLOW_AI_EXTERNAL', 'DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL',
    'DEEPSEEK_TIMEOUT_SECONDS', 'AI_MAX_RECORDS', 'INVENTORY_AGING_DAYS', 'REPAIR_OVERDUE_DAYS',
    'RECEIVABLE_GRACE_DAYS', 'LOW_GROSS_MARGIN_PERCENT', 'LARGE_CASH_AMOUNT_YUAN',
    'DISCOUNT_REVIEW_PERCENT', 'MAINTENANCE_ENABLED', 'API_DOCS_ENABLED', 'PORT',
    'FORWARDED_ALLOW_IPS',
)


def app_environment(cfg, release, source=None) -> dict:
    """Environment for the application container, derived from this process."""
    source = source if source is not None else __import__('os').environ
    env = {key: source[key] for key in APP_ENV_KEYS if source.get(key)}
    env['DATABASE_URL'] = 'sqlite:////app/data/dealer.db'
    env['DEALER_RELEASE_SHA'] = release['sha']
    env['MAINT_RUNTIME_DIR'] = '/maint'
    env['DEALER_DEPLOYMENT_GATE'] = '/maint/switching.lock'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    return env


def container_run_argv(cfg, release, source_info=None) -> list:
    image = release.get('image') or ''
    if not image:
        raise GateError('运行版本缺少镜像标签')
    argv = ['docker', 'run', '--detach', '--name', cfg.app_container, '--restart', 'no',
            '--user', CONTAINER_UID, '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=67108864',
            '--pids-limit', '256', '--memory', cfg.app_memory, '--memory-swap', cfg.app_memory,
            '--cpus', cfg.app_cpus,
            '--publish', '%s:%d:%d' % (cfg.app_publish_host, cfg.app_publish_port, cfg.app_port),
            '--volume', '%s:/app/data' % cfg.app_data_dir,
            '--volume', '%s:/maint:ro' % Path(cfg.runtime).as_posix()]
    for key, value in sorted(app_environment(cfg, release, source_info).items()):
        argv += ['--env', '%s=%s' % (key, value)]
    argv.append(image)
    return argv


class Docker:
    def __init__(self, runner=subprocess.run, timeout=DOCKER_TIMEOUT):
        self._run = runner
        self.timeout = timeout

    def call(self, argv, timeout=None, check=True) -> str:
        try:
            done = self._run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=int(timeout or self.timeout), check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GateError('docker 不可用或超时：' + ' '.join(argv[:3])) from exc
        out = (done.stdout or b'').decode('utf-8', 'replace').strip()
        if check and done.returncode:
            err = (done.stderr or b'').decode('utf-8', 'replace').strip()
            raise GateError('docker 命令失败（%s）：%s' % (argv[1] if len(argv) > 1 else '?', (err or out)[-400:]))
        return out

    def image_id(self, tag) -> str:
        return self.call(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], check=False)

    def require_image(self, tag) -> str:
        found = self.image_id(tag)
        if not found:
            raise GateError('本机缺少镜像 %s；请先由构建机传输' % tag)
        return found

    def container_state(self, name) -> str:
        return self.call(['docker', 'inspect', '--format', '{{.State.Status}}', name], check=False)

    def remove(self, name) -> None:
        state = self.container_state(name)
        if not state:
            return
        if state == 'running':
            self.call(['docker', 'stop', '--time', '20', name], timeout=60)
        self.call(['docker', 'rm', '--force', name], timeout=60)

    def run_detached(self, argv) -> str:
        return self.call(argv, timeout=180)