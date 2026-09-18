"""Timezone-pinned maintenance window plus the quant-worker guard.

The window is defined in Asia/Shanghai, but the Singapore builder host runs on
Etc/UTC. Deriving the window from host-local time would silently shift 22:00-06:00
to 06:00-14:00 Shanghai -- exactly overlapping the quant runs we must not disturb
-- so every calculation converts an explicit instant into an explicit timezone.

Inside the outer window two ranges are banned because the QuantBit traders fire
at 00:01 and 04:01 Asia/Shanghai. A time gate alone is not sufficient (a trader
run can still be in flight), so the caller also checks quant_state() and waits.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

DEFAULT_TZ = 'Asia/Shanghai'


class WindowError(RuntimeError):
    """Malformed window configuration. Always fails closed."""


def parse_hhmm(text: str) -> time:
    parts = str(text).strip().split(':')
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise WindowError('时间格式必须是 HH:MM：' + str(text))
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise WindowError('时间超出范围：' + str(text))
    return time(hour, minute)


def parse_bans(text: str) -> tuple:
    """'23:50-00:30,03:50-04:30' -> ((time(23,50), time(0,30)), ...)"""
    result = []
    for chunk in str(text or '').split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        left, separator, right = chunk.partition('-')
        if not separator:
            raise WindowError('禁运区间格式必须是 HH:MM-HH:MM：' + chunk)
        result.append((parse_hhmm(left), parse_hhmm(right)))
    return tuple(result)


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _inside(minute: int, start: int, end: int) -> bool:
    """Half-open range that may wrap past midnight."""
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


@dataclass(frozen=True)
class WindowState:
    open: bool
    reason: str
    minutes_left: int
    opens_in: int = 0

    def __bool__(self) -> bool:
        return self.open

    def wait_hint(self) -> str:
        """Operator-facing hint for a closed state."""
        if self.open:
            return ''
        return ('约 %d 分钟后进入下一段维护时间' % self.opens_in) if self.opens_in else '等待下一个维护时段'


@dataclass(frozen=True)
class QuantState:
    busy: tuple = ()
    unknown: bool = False

    @property
    def ok(self) -> bool:
        return not self.busy and not self.unknown

    def reason(self) -> str:
        if self.busy:
            return '量化任务正在运行（' + ', '.join(self.busy) + '），本次让行，稍后重试'
        if self.unknown:
            return '无法确认量化任务状态（systemctl 不可用），按让行处理'
        return ''


def window_config(cfg):
    """Read window settings off the config object with safe defaults."""
    return (
        str(getattr(cfg, 'window_tz', DEFAULT_TZ) or DEFAULT_TZ),
        parse_hhmm(getattr(cfg, 'window_start', '22:00')),
        parse_hhmm(getattr(cfg, 'window_end', '06:00')),
        tuple(getattr(cfg, 'window_bans', ()) or ()),
        int(getattr(cfg, 'min_segment_minutes', 20)),
    )


def _allowed(minute: int, start: int, end: int, bans: Sequence) -> bool:
    if not _inside(minute, start, end):
        return False
    return not any(_inside(minute, low, high) for low, high in bans)


def _minutes_until_open(minute: int, start: int, end: int, bans: Sequence) -> int:
    """How long until the next instant a new build would be allowed to start."""
    cursor = minute
    for step in range(1, 1441):
        cursor = (cursor + 1) % 1440
        if _allowed(cursor, start, end, bans):
            return step
    return 0


def window_state(cfg, now: datetime | None = None) -> WindowState:
    """Is a new build/deploy allowed to start right now?

    `now` must be timezone-aware. A naive value would be interpreted as host-local
    time, which is the exact drift this module exists to prevent, so it is
    rejected outright rather than silently guessed.
    """
    tz_name, start_at, end_at, bans_at, minimum = window_config(cfg)
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, ValueError, OSError) as exc:
        raise WindowError('未知或不可用的时区配置：' + tz_name) from exc
    if now is None:
        moment = datetime.now(timezone.utc)
    elif now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise WindowError('window_state 必须接收带时区的时刻，不接受本地时间')
    else:
        moment = now
    moment = moment.astimezone(tz)
    start, end = _minutes(start_at), _minutes(end_at)
    bans = [(_minutes(low), _minutes(high)) for low, high in bans_at]
    length = (end - start) % 1440 or 1440
    minute = moment.hour * 60 + moment.minute

    if not _inside(minute, start, end):
        return WindowState(False, '当前不在维护时段 %s-%s（%s）内'
                                  % (start_at.strftime('%H:%M'), end_at.strftime('%H:%M'), tz_name), 0,
                           _minutes_until_open(minute, start, end, bans))
    if not _allowed(minute, start, end, bans):
        return WindowState(False, '当前处于量化任务保护时段（trader 每 4 小时一次，'
                                  '00:01 与 04:01 前后让行），暂停启动新的构建与发布', 0,
                           _minutes_until_open(minute, start, end, bans))

    left, cursor = 0, minute
    for _ in range(length):
        if not _allowed(cursor, start, end, bans):
            break
        left += 1
        cursor = (cursor + 1) % 1440
    if left < minimum:
        return WindowState(False, '本段维护时间只剩 %d 分钟，不足以完成构建与发布（至少需要 %d 分钟），留到下一段'
                                  % (left, minimum), left,
                           _minutes_until_open(minute, start, end, bans))
    return WindowState(True, '', left, 0)


def _systemctl_is_active(units: Sequence[str]) -> tuple:
    try:
        proc = subprocess.run(['systemctl', 'is-active', *units], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise WindowError('systemctl 不可用，无法确认量化任务状态')
    states = proc.stdout.decode('utf-8', 'replace').split()
    return tuple(unit for unit, state in zip(units, states) if state == 'active')


def quant_state(units: Iterable[str] | None, runner: Callable | None = None) -> QuantState:
    """Which of the configured quant units are running right now?

    Fails closed: if units are configured but systemctl cannot be consulted, the
    caller is told the state is unknown rather than assuming it is idle.
    """
    watched = tuple(unit for unit in (units or ()) if unit)
    if not watched:
        return QuantState()
    try:
        busy = tuple(runner(watched) if runner else _systemctl_is_active(watched))
    except WindowError:
        return QuantState(unknown=True)
    return QuantState(busy=busy)


def wait_for_slot(cfg, units, sleep: Callable[[float], None], attempts: int | None = None,
                  now: Callable[[], datetime] | None = None, runner: Callable | None = None) -> tuple:
    """Bounded wait until the window is open and the quant units are idle.

    Returns (ready, reason). Never blocks past the attempt budget: a task that
    cannot get a slot simply stays queued for the next segment.
    """
    clock = now or (lambda: datetime.now(timezone.utc))
    budget = int(getattr(cfg, 'slot_attempts', 10) if attempts is None else attempts)
    pause = float(getattr(cfg, 'slot_pause_seconds', 60))
    last = '维护时段与量化状态均未满足'
    for attempt in range(max(1, budget)):
        state = window_state(cfg, clock())
        if not state.open:
            hint = state.wait_hint()
            last = (state.reason + '；' + hint) if hint else state.reason
        else:
            quant = quant_state(units, runner)
            if quant.ok:
                return True, ''
            last = quant.reason()
        if attempt < budget - 1:
            sleep(pause)
    return False, last
