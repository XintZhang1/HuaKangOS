"""Forced-command entry point on the builder host.

sshd runs this with no arguments; the requested verb arrives in
SSH_ORIGINAL_COMMAND, which is untrusted request data. It is split with shlex and
dispatched against a fixed allowlist, and the single argument travels as an
opaque base64(JSON) token. Nothing is ever handed to a shell, here or upstream.

Exit codes: 0 = handled (including a polite refusal, which is a normal outcome),
1 = refused/failed with a readable reason on stderr, 3 = unexpected internal
error. The `image` verb streams a binary tarball on stdout, so its diagnostics
always go to stderr.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
import traceback
from datetime import datetime, timezone

from ..config import BuilderConfig, GateError
from ..transport import decode
from .lock import BuildLock
from .verbs import Builder, Refused

ACTIONS = {'status': 'status', 'context': 'context', 'candidate': 'candidate', 'image': 'stream_image',
           'publish': 'publish', 'revert': 'revert', 'prune': 'prune'}
ALLOWED = tuple(sorted(ACTIONS))
LOCKED = frozenset(ALLOWED) - {'status'}
LOG_LIMIT = 2_000_000
CRASH_MESSAGE = '构建机内部错误；已记录到本地 crash.log，未推送任何分支'


def emit(result) -> int:
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + '\n')
    sys.stdout.flush()
    return 0


def refuse(detail, code='refused') -> int:
    return emit({'ok': False, 'code': code, 'detail': str(detail)[:2000]})


def audit(cfg, verb, outcome, detail='') -> None:
    try:
        cfg.state.mkdir(parents=True, exist_ok=True)
        path = cfg.state/'audit.log'
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            path.replace(cfg.state/'audit.log.1')
        record = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'verb': verb,
                  'outcome': outcome, 'detail': str(detail)[:400], 'from': os.getenv('SSH_CONNECTION', '')}
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError:
        pass


def record_crash(cfg) -> None:
    try:
        cfg.state.mkdir(parents=True, exist_ok=True)
        with (cfg.state/'crash.log').open('a', encoding='utf-8') as handle:
            handle.write(datetime.now(timezone.utc).isoformat() + '\n' + traceback.format_exc() + '\n')
    except OSError:
        pass


def main() -> int:
    raw = os.environ.get('SSH_ORIGINAL_COMMAND', '').strip()
    cfg = BuilderConfig()
    try:
        parts = shlex.split(raw)
    except ValueError:
        return refuse('请求无法解析', 'bad_request')
    if not parts or parts[0] not in ACTIONS:
        return refuse('未知动词；允许：' + ', '.join(ALLOWED), 'bad_request')
    verb, args = parts[0], parts[1:]
    if len(args) > 1:
        return refuse('参数过多', 'bad_request')
    try:
        cfg.validate()
    except GateError as exc:
        return refuse('构建机配置无效：' + str(exc), 'misconfigured')

    binary = verb == 'image'
    try:
        payload = decode(args[0]) if args else None
        if payload is not None and not isinstance(payload, dict):
            raise GateError('请求载荷必须是 JSON 对象')
        builder = Builder(cfg)
        action = getattr(builder, ACTIONS[verb])
        if verb in LOCKED:
            with BuildLock(cfg.state/'build.lock'):
                result = action(payload)
        else:
            result = action(payload)
    except Refused as exc:
        audit(cfg, verb, exc.code, exc)
        print(str(exc), file=sys.stderr)
        return refuse(str(exc), exc.code) if not binary else 1
    except GateError as exc:
        audit(cfg, verb, 'gate_error', exc)
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        audit(cfg, verb, 'crash')
        record_crash(cfg)
        print(CRASH_MESSAGE, file=sys.stderr)
        return 3
    audit(cfg, verb, 'ok')
    if binary:
        return 0 if result in (0, None) else 1
    return emit(result)


if __name__ == '__main__':
    raise SystemExit(main())