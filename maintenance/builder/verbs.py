"""Verb implementations for the Singapore build agent.

Everything reaching this module is untrusted request data: the caller is the
Aliyun controller, but the payloads it forwards originate from model output and
from operator input. A proposal is therefore re-validated here with the very same
policy code the controller used -- the controller's verdict is never trusted.

Verb contract
-------------
Contract, as implemented: a *polite refusal* (``Refused`` -- closed window, busy
quant job) prints one JSON document on stdout and exits 0, because retrying later
is a normal outcome. A malformed or hostile request, and any hard failure, exits
non-zero with a readable reason on stderr and nothing on stdout; the caller in
transport.py turns both into an exception. The `image` verb streams a gzipped
`docker save` tarball on stdout, so all of its diagnostics go to stderr.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import BuilderConfig, GateError
from ..gitops import Repository, SHA, tree_matches
from ..images import (LABEL_KEY, app_image_tag, build_image, disk_free_gb, image_id,
                      image_label, prune_images, trusted_test_image, CANDIDATE_TAG)
from ..policy import EDITABLE, Proposal, apply_proposal, change_tier, context_files
from ..sandbox import test_candidate
from ..window import quant_state, window_state

BRANCH_RE = re.compile(r'^dealerdesk/change-\d+-\d+$')


class Refused(RuntimeError):
    """An expected refusal that the caller should retry later or report as-is."""

    def __init__(self, detail: str, code: str = 'refused'):
        super().__init__(detail)
        self.code = code


def _sha(payload, key) -> str:
    value = str(payload.get(key) or '')
    if not SHA.fullmatch(value):
        raise GateError('%s 必须是完整的 40 位提交号' % key)
    return value


def _job_id(payload) -> int:
    """Malformed input must read as a refusal, not as an internal crash."""
    raw = payload.get('job_id')
    try:
        value = int(raw if raw is not None else 0)
    except (TypeError, ValueError) as exc:
        raise GateError('job_id 必须是整数') from exc
    if value <= 0:
        raise GateError('job_id 无效')
    return value


class Builder:
    def __init__(self, cfg: BuilderConfig, repo: Repository | None = None):
        self.cfg = cfg
        self.repo = repo or Repository(cfg)

    # -- shared guards ----------------------------------------------------
    def guard(self) -> None:
        """Fail closed unless we are inside the window and the quant jobs are idle."""
        state = window_state(self.cfg)
        if not state.open:
            raise Refused(state.reason, 'not_now')
        quant = quant_state(self.cfg.quant_units)
        if not quant.ok:
            raise Refused(quant.reason(), 'not_now')

    def sync_main(self) -> str:
        return self.repo.sync()

    def remote_main(self) -> str:
        """Remote base-branch head, without a full fetch. Empty when unknown."""
        try:
            if not self.repo.path.exists():
                return ''
            return self.repo.remote_head(self.cfg.base_branch)
        except GateError:
            return ''

    def require_trusted_image(self) -> None:
        usable, detail = trusted_test_image(self.cfg)
        if not usable:
            raise GateError(detail)

    def require_disk(self) -> None:
        free = disk_free_gb(self.cfg.root if self.cfg.root.exists() else '/')
        if free < self.cfg.min_free_gb:
            raise GateError('构建机磁盘余量不足（%.1fGB < %dGB），先清理再重试' % (free, self.cfg.min_free_gb))

    # -- verbs ------------------------------------------------------------
    def status(self, payload=None) -> dict:
        """Read-only report. Deliberately NOT window-gated: doctor needs it any time."""
        win = window_state(self.cfg)
        quant = quant_state(self.cfg.quant_units)
        usable, detail = trusted_test_image(self.cfg)
        head = ''
        try:
            if self.repo.path.exists():
                head = self.repo.git('rev-parse', 'HEAD')
        except GateError:
            head = ''
        return {'ok': True, 'host': socket.gethostname(), 'request_from': os.getenv('SSH_CONNECTION', ''),
                'now': datetime.now(ZoneInfo(self.cfg.window_tz)).isoformat(timespec='seconds'),
                'window': {'open': win.open, 'reason': win.reason, 'minutes_left': win.minutes_left},
                'quant': {'busy': list(quant.busy), 'unknown': quant.unknown, 'reason': quant.reason()},
                'docker': self._docker_version(),
                'test_image': {'tag': self.cfg.test_image, 'id': image_id(self.cfg.test_image),
                               'usable': usable, 'detail': detail,
                               'trusted_label': image_label(self.cfg.test_image)},
                'clone': {'present': self.repo.path.exists(), 'head': head},
                'disk_free_gb': round(disk_free_gb(self.cfg.root if self.cfg.root.exists() else '/'), 1),
                'trusted_sha': self.cfg.trusted_sha,
                'main_sha': self.remote_main()}

    def context(self, payload) -> dict:
        base = _sha(payload, 'base_sha')
        self.guard()
        remote = self.sync_main()
        if base != remote:
            raise Refused('请求的基线 %s 不是当前远程主分支 %s；请重新排队生成'
                          % (base[:12], remote[:12]))
        self.require_trusted_image()
        self.repo.checkout_detached(base)
        return {'ok': True, 'base_sha': base, 'files': context_files(self.repo.path)}

    def candidate(self, payload) -> dict:
        job_id = _job_id(payload)
        base = _sha(payload, 'base_sha')
        branch = str(payload.get('branch') or '')
        if not BRANCH_RE.fullmatch(branch):
            raise GateError('候选分支名称无效')
        try:
            proposal = Proposal.model_validate(payload.get('proposal') or {})
        except Exception as exc:
            raise GateError('候选补丁结构无效：' + type(exc).__name__) from exc
        # Veto protected paths before any git work, so a hostile patch never even
        # causes a fetch or a checkout. apply_proposal re-checks this later.
        outside = sorted({edit.path for edit in proposal.edits if edit.path not in EDITABLE})
        if outside:
            raise GateError('补丁包含白名单外的文件，拒绝处理：' + ', '.join(outside))

        self.guard()
        self.require_disk()
        self.require_trusted_image()
        remote = self.sync_main()
        if base != remote:
            raise Refused('请求的基线 %s 不是当前远程主分支 %s；请重新排队生成'
                          % (base[:12], remote[:12]))

        self.repo.checkout(base, branch)
        # Re-validated here, with the same policy code, on the machine that writes.
        changed = apply_proposal(self.repo.path, proposal)
        head = self.repo.commit(changed, job_id)
        self.repo.verify_candidate(base, head)
        tier = change_tier(changed)
        # Computed before any push/build: a failure in the last line of this method
        # must not turn a candidate that already shipped into a reported crash.
        compare_url = self.repo.compare_url(base, head)

        with tempfile.TemporaryDirectory(prefix='candidate-', dir=str(self.cfg.runtime)) as tmp:
            source = self.repo.export(head, Path(tmp)/'source')
            result = dict(test_candidate(source, self.cfg))
            result['head_sha'] = head
            image_tag, digest = '', ''
            if result.get('passed'):
                image_tag = app_image_tag(self.cfg.app_image_prefix, head)
                digest = build_image(source, image_tag, self.cfg.build_timeout)
                self.repo.push_candidate(branch)
        prune_images(self.cfg)
        return {'ok': True, 'head_sha': head, 'branch': branch, 'changed': changed, 'tier': tier,
                'test': result, 'image_tag': image_tag, 'image_id': digest,
                'pushed': bool(image_tag), 'compare_url': compare_url}

    def publish(self, payload) -> dict:
        base = _sha(payload, 'base_sha')
        head = _sha(payload, 'head_sha')
        branch = str(payload.get('branch') or '')
        if not BRANCH_RE.fullmatch(branch):
            raise GateError('候选分支名称无效')
        self.guard()
        self.repo.sync()
        self.repo.publish(base, head, branch)
        return {'ok': True, 'main_sha': self.repo.remote_head(self.cfg.base_branch)}

    def revert(self, payload) -> dict:
        base = _sha(payload, 'base_sha')
        head = _sha(payload, 'head_sha')
        job_id = _job_id(payload)
        self.guard()
        reverted = self.repo.revert_published(base, head, job_id)
        return {'ok': True, 'reverted_sha': reverted}

    def prune(self, payload=None) -> dict:
        self.guard()
        return {'ok': True, **prune_images(self.cfg)}

    def stream_image(self, payload) -> int:
        """Write `docker save | gzip -1` to stdout. Returns a process exit code."""
        tag = str(payload.get('image_tag') or '')
        if not re.fullmatch(CANDIDATE_TAG, tag) or not tag.startswith(self.cfg.app_image_prefix + ':'):
            raise GateError('拒绝导出非本机构建的应用镜像：' + tag[:80])
        self.guard()
        if not image_id(tag):
            raise Refused('镜像 %s 不存在或已被清理，请重新生成候选' % tag)
        gzip_bin = '/usr/bin/gzip' if Path('/usr/bin/gzip').is_file() else 'gzip'
        saver = subprocess.Popen(['docker', 'save', tag], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            packer = subprocess.Popen([gzip_bin, '-1', '-c'], stdin=saver.stdout,
                                      stdout=sys.stdout.buffer, stderr=subprocess.PIPE)
        except OSError as exc:
            saver.kill()
            raise GateError('压缩工具不可用，无法导出镜像') from exc
        saver.stdout.close()
        packer.communicate()
        saver.wait()
        if saver.returncode:
            raise GateError('docker save 失败：' + (saver.stderr.read() or b'').decode('utf-8', 'replace')[-400:])
        if packer.returncode:
            raise GateError('镜像压缩失败（退出码 %d）' % packer.returncode)
        return 0

    def _docker_version(self) -> str:
        try:
            proc = subprocess.run(['docker', 'version', '--format', '{{.Server.Version}}'],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return ''
        return proc.stdout.decode('utf-8', 'replace').strip()