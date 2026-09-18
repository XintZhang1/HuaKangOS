"""Application runtime adapters.

Two shapes behind one interface, so the supervisor's release state machine does
not care which one it is driving:

* LocalProcessRuntime -- the development path on Windows. Spawns uvicorn from a
  release directory. Behaviour is unchanged from the original supervisor.
* ContainerRuntime -- the production path. Runs the application as a docker
  container whose image was built from a tested commit on the builder host.

Both expose start / stop / healthy / alive.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy.engine import make_url

from ..config import GateError
from .container import Docker, container_run_argv


def absolute_database_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.get_backend_name() == 'sqlite' and parsed.database and parsed.database != ':memory:':
        parsed = parsed.set(database=str(Path(parsed.database).resolve()))
    return parsed.render_as_string(hide_password=False)


def _loopback(host: str) -> str:
    if host == '0.0.0.0':
        return '127.0.0.1'
    if host in {'::', '::1'}:
        return '[::1]'
    return host


class LocalProcessRuntime:
    def __init__(self, host, port, cfg):
        self.host = host
        self.port = port
        self.cfg = cfg
        self.process = None

    def release_description(self, release) -> str:
        return str(release.get('path', ''))

    def start(self, release):
        if self.alive():
            raise GateError('旧服务尚未停止，拒绝启动第二个写库进程')
        env = os.environ.copy()
        env['DATABASE_URL'] = absolute_database_url(os.environ.get('DATABASE_URL', ''))
        env['DEALER_DEPLOYMENT_GATE'] = str(self.cfg.runtime/'switching.lock')
        env['DEALER_RELEASE_SHA'] = release['sha']
        env['MAINT_RUNTIME_DIR'] = str(self.cfg.runtime)
        env['PYTHONPATH'] = str(Path(release['path']).resolve())
        # The business service has no need for code-push or approval credentials.
        for key in list(env):
            if key.startswith(('FEISHU_', 'DEEPSEEK_CODE_', 'MAINT_REPO_', 'MAINT_SG_')): env.pop(key, None)
        self.process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                         '--host', self.host, '--port', str(self.port), '--workers', '1'],
                                        cwd=release['path'], env=env, stdin=subprocess.DEVNULL)

    def stop(self):
        if self.alive():
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        self.process = None

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def healthy(self, sha, timeout=25) -> bool:
        return _poll_health(_loopback(self.host), self.port, sha, timeout, self.alive)

    def adopt(self, release) -> bool:
        return self.alive()


class ContainerRuntime:
    def __init__(self, cfg, docker: Docker | None = None, env_source=None):
        self.cfg = cfg
        self.docker = docker or Docker()
        self.env_source = env_source

    def release_description(self, release) -> str:
        return str(release.get('image', ''))

    def container_image(self) -> str:
        return self.docker.call(['docker', 'inspect', '--format', '{{.Config.Image}}',
                                 self.cfg.app_container], check=False)

    def start(self, release):
        self.docker.require_image(release['image'])
        self.docker.remove(self.cfg.app_container)
        self.docker.run_detached(container_run_argv(self.cfg, release, self.env_source))

    def stop(self):
        self.docker.remove(self.cfg.app_container)

    def alive(self) -> bool:
        return self.docker.container_state(self.cfg.app_container) == 'running'

    def healthy(self, sha, timeout=25) -> bool:
        return _poll_health(_loopback(self.cfg.app_publish_host), self.cfg.app_publish_port,
                            sha, timeout, self.alive)

    def adopt(self, release) -> bool:
        """True when the running container already is the verified release."""
        if not self.alive():
            return False
        if self.container_image() != release.get('image'):
            return False
        return self.healthy(release['sha'], timeout=5)


def _poll_health(host, port, sha, timeout, alive) -> bool:
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=2, trust_env=False) as client:
        while time.monotonic() < deadline:
            if not alive():
                return False
            try:
                response = client.get('http://%s:%d/api/health' % (host, port))
                data = response.json()
                if response.status_code == 200 and data.get('status') == 'ok' and data.get('release') == sha:
                    return True
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(.4)
    return False


def build_runtime(cfg, host, port):
    """Pick the runtime for the configured deploy target."""
    if cfg.split:
        return ContainerRuntime(cfg)
    return LocalProcessRuntime(host, port, cfg)