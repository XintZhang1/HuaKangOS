"""Single-instance lock for the build agent.

Two candidates must never build at the same time: the box has one vCPU and the
quant jobs need the headroom. A second invocation is refused rather than queued.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import GateError


class BuildLock:
    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0)
                self.handle.write(b'0')
                self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            self.handle.close()
            self.handle = None
            raise GateError('构建机正忙：已有另一个构建或测试在运行，请稍后重试') from exc
        return self

    def __exit__(self, *exc_info):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        return False