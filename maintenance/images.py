"""Docker image helpers used by the Singapore builder.

Only the builder host ever builds images. The trusted test image is built once by
the install script from a reviewed baseline and carries a label recording that
baseline SHA; the builder refuses to test a candidate against an image whose
label does not match the configured trusted SHA. The application image is built
from the candidate tree -- its Dockerfile is not model-editable, so the recipe
stays trusted even though the content it copies does not.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import GateError
from .gitops import SHA, run

LABEL_KEY = 'dealerdesk.trusted.sha'
CANDIDATE_TAG = r'^[A-Za-z0-9][A-Za-z0-9._/-]*:[0-9a-f]{40}$'


def app_image_tag(prefix: str, sha: str) -> str:
    if not SHA.fullmatch(sha or ''):
        raise GateError('镜像标签必须绑定完整的 40 位提交号')
    return '%s:%s' % (prefix, sha)


def image_id(tag: str, timeout: int = 30) -> str:
    try:
        return run(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], timeout=timeout)
    except GateError:
        return ''


def image_label(tag: str, key: str = LABEL_KEY, timeout: int = 30) -> str:
    try:
        value = run(['docker', 'image', 'inspect', tag, '--format',
                     '{{index .Config.Labels "%s"}}' % key], timeout=timeout)
    except GateError:
        return ''
    return '' if value in {'<no value>', 'null'} else value


def trusted_test_image(cfg) -> tuple:
    """(usable, detail) for the isolated test image on this host."""
    if not image_id(cfg.test_image):
        return False, '隔离测试镜像 %s 不存在，请先由安装脚本从可信基线构建' % cfg.test_image
    expected = (getattr(cfg, 'trusted_sha', '') or '').strip()
    if not expected:
        return True, '未配置 HKB_TRUSTED_SHA，跳过镜像基线标签校验'
    actual = image_label(cfg.test_image)
    if actual != expected:
        return False, ('隔离测试镜像的基线标签为 %r，与 HKB_TRUSTED_SHA %s 不一致；'
                       '拒绝用它测试候选' % (actual or '', expected))
    return True, ''


def build_image(source: Path, tag: str, timeout: int, dockerfile: str = 'Dockerfile'):
    source = Path(source).resolve()
    if not (source/dockerfile).is_file():
        raise GateError('候选目录缺少 %s，拒绝构建镜像' % dockerfile)
    argv = ['docker', 'build', '--pull=false', '--quiet', '-f', dockerfile, '-t', tag, str(source)]
    try:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError('镜像构建启动失败或超时；未推送任何分支') from exc
    if proc.returncode:
        tail = proc.stdout.decode('utf-8', 'replace')[-3000:]
        raise GateError('镜像构建失败（未推送分支）：' + tail)
    built = image_id(tag)
    if not built:
        raise GateError('镜像构建结束但无法确认镜像；拒绝继续')
    return built


def disk_free_gb(path) -> float:
    try:
        return shutil.disk_usage(str(path)).free / 1_000_000_000
    except OSError:
        return 0.0


def prune_images(cfg, keep: int = 3, protect=(), timeout: int = 300) -> dict:
    """Drop dangling layers and stale application images. Never touches the test image.

    Two rules learned the hard way:

    * `protect` is never removed. The freshly built candidate must survive its own
      prune step -- otherwise the controller is told to deploy an image that the
      builder has already deleted.
    * Pruning is ordered by creation time, never by tag. Application tags are commit
      SHAs, so sorting them by name is meaningless: an earlier version kept the
      "largest" three tags and thereby deleted the image it had just built.
    """
    protected = {str(tag) for tag in (protect or ()) if tag}
    removed = []
    try:
        run(['docker', 'image', 'prune', '-f'], timeout=timeout)
    except GateError:
        pass
    try:
        listing = run(['docker', 'images', '--format', '{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}',
                       '--no-trunc'], timeout=60)
    except GateError:
        listing = ''
    entries = []
    for line in listing.splitlines():
        tag, _, created = line.partition('\t')
        if not tag.startswith(cfg.app_image_prefix + ':') or tag in protected:
            continue
        entries.append((created, tag))
    entries.sort()  # oldest first
    doomed = entries[:-keep] if keep else entries
    for _, tag in doomed:
        try:
            run(['docker', 'rmi', tag], timeout=timeout)
            removed.append(tag)
        except GateError:
            pass
    try:
        run(['docker', 'builder', 'prune', '-f'], timeout=timeout)
    except GateError:
        pass
    return {'removed': removed}