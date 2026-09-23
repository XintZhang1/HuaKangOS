"""Explicit standalone report process; no business writes or code deployment.

Web and worker use SCHEDULER_MODE=worker; only this entry point runs ticks.
Report generation retains the existing database lease and unique day/store key.
"""
import argparse
import logging
import threading

from .config import settings
from .scheduler import tick

log = logging.getLogger(__name__)


def run(*, once=False, stop_event=None):
    if not settings.scheduler_enabled or settings.scheduler_mode != 'worker':
        raise SystemExit('独立日报进程需要 SCHEDULER_ENABLED=true 和 SCHEDULER_MODE=worker')
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        tick()
        if once or stop_event.wait(30):
            break


def main():
    parser = argparse.ArgumentParser(description='huakangos 独立日报进程')
    parser.add_argument('--once', action='store_true', help='只检查一次到期或漏跑日报')
    args = parser.parse_args()
    try:
        run(once=args.once)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
