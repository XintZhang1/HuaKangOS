"""Aliyun -> Singapore builder transport over one restricted SSH forced command.

Every request is `ssh -i KEY user@host '<verb> <base64-json>'`. The remote side
runs a fixed forced command that re-parses $SSH_ORIGINAL_COMMAND itself, so no
verb or argument ever reaches a shell -- neither here nor there. Nothing is
interpolated into a command string: arguments travel as one opaque base64 token.

JSON verbs answer with a JSON document on stdout and exit 0 even when they
refuse a request (refusal is a normal outcome: the window may be closed). They
exit non-zero only on an internal failure. The `image` verb streams a compressed
`docker save` tarball on stdout instead.
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from .config import GateError

VERBS = frozenset({'status', 'context', 'candidate', 'publish', 'revert', 'prune', 'image'})
MAX_PAYLOAD = 512 * 1024
STDERR_TAIL = 600


class NotNow(RuntimeError):
    """The builder declined politely: outside the window or a quant job is running.

    Callers must leave the task queued and retry later -- this is never a failure.
    """


def encode(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_PAYLOAD:
        raise GateError('发给构建机的请求超过 %d 字节，已拒绝' % MAX_PAYLOAD)
    return base64.b64encode(raw).decode('ascii')


def decode(token: str):
    """Builder side: strict base64(JSON) decoding. Never eval, never shell."""
    if not isinstance(token, str) or not token or len(token) > MAX_PAYLOAD * 2:
        raise GateError('请求载荷为空或过长')
    try:
        raw = base64.b64decode(token.encode('ascii'), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise GateError('请求载荷不是合法的 base64') from exc
    if len(raw) > MAX_PAYLOAD:
        raise GateError('请求载荷过大')
    try:
        return json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise GateError('请求载荷不是合法的 JSON') from exc


def _tail(raw: bytes) -> str:
    text = (raw or b'').decode('utf-8', 'replace').strip()
    return text[-STDERR_TAIL:]


class BuilderClient:
    """Thin, fail-closed client for the builder's verb interface."""

    def __init__(self, cfg, runner=subprocess.run, popen=subprocess.Popen):
        self.cfg = cfg
        self._run = runner
        self._popen = popen

    def argv(self, verb, token=None) -> list:
        if verb not in VERBS:
            raise GateError('未知的构建机动词：' + str(verb))
        command = verb if token is None else verb + ' ' + token
        return ['ssh', '-i', str(self.cfg.sg_key), '-p', str(self.cfg.sg_port),
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=8',
                '-o', 'LogLevel=ERROR',
                '%s@%s' % (self.cfg.sg_user, self.cfg.sg_host), command]

    def call(self, verb, payload=None, timeout=None):
        argv = self.argv(verb, None if payload is None else encode(payload))
        budget = int(timeout or self.cfg.sg_timeout)
        try:
            done = self._run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=budget, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GateError('构建机不可达或超时（%s）；未执行任何发布动作' % verb) from exc
        if done.returncode:
            raise GateError('构建机拒绝或失败（%s）：%s' % (verb, _tail(done.stderr) or '退出码 %d' % done.returncode))
        text = (done.stdout or b'').decode('utf-8', 'replace').strip()
        if not text:
            raise GateError('构建机未返回结果（%s）' % verb)
        try:
            result = json.loads(text)
        except ValueError as exc:
            raise GateError('构建机返回了非 JSON 结果（%s）' % verb) from exc
        if not isinstance(result, dict):
            raise GateError('构建机返回了意外的结果类型（%s）' % verb)
        if not result.get('ok'):
            if result.get('code') == 'not_now':
                raise NotNow(str(result.get('detail') or '当前不允许执行构建或发布'))
            raise GateError('构建机拒绝了请求（%s）：%s' % (verb, result.get('detail') or result.get('code')))
        return result

    def status(self):
        return self.call('status', timeout=60)

    def context(self, base_sha):
        return self.call('context', {'base_sha': base_sha})

    def candidate(self, job_id, base_sha, branch, proposal):
        return self.call('candidate', {'job_id': int(job_id), 'base_sha': base_sha,
                                       'branch': branch, 'proposal': proposal})

    def publish(self, base_sha, head_sha, branch):
        return self.call('publish', {'base_sha': base_sha, 'head_sha': head_sha, 'branch': branch})

    def revert(self, base_sha, head_sha, job_id):
        return self.call('revert', {'base_sha': base_sha, 'head_sha': head_sha, 'job_id': int(job_id)})

    def prune(self):
        return self.call('prune', timeout=300)

    def stream_image_into(self, image_tag, load_argv=('docker', 'load'), timeout=None):
        """Pipe `docker save` from the builder straight into local `docker load`.

        The image never lands in memory or on disk here: two processes are wired
        together, and docker verifies its own content digests on load.
        """
        token = encode({'image_tag': image_tag})
        argv = self.argv('image', token)
        budget = int(timeout or self.cfg.sg_timeout * 4)
        try:
            source = self._popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            raise GateError('无法启动镜像传输') from exc
        try:
            sink = self._popen(list(load_argv), stdin=source.stdout, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
        except OSError:
            source.kill()
            raise GateError('本机 docker load 不可用')
        source.stdout.close()
        try:
            loaded = sink.communicate(timeout=budget)[0]
        except subprocess.TimeoutExpired:
            source.kill(); sink.kill()
            raise GateError('镜像传输超时；未切换运行版本')
        finally:
            try: source.wait(timeout=30)
            except subprocess.TimeoutExpired: source.kill()
        if source.returncode:
            raise GateError('构建机未能提供镜像 %s：%s' % (image_tag, _tail(source.stderr.read() if source.stderr else b'')))
        if sink.returncode:
            raise GateError('本机加载镜像失败：%s' % _tail(loaded))
        return _tail(loaded)


def load_config_from(path):
    """Small helper so deploy scripts can reuse the same parsing."""
    return json.loads(Path(path).read_text(encoding='utf-8'))