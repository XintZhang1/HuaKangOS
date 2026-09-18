"""维护窗口 maintenance.window 的时区、边界、最小段与量化让行测试。

所有时刻都用显式 aware datetime：测试把上海墙钟换算成 UTC，
模块再按 window_tz 换算回上海，因此断言与宿主机本地时区无关。
不调用真实 systemctl，不改动任何生产配置或业务数据库。
"""
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
import pytest
from maintenance import window
from maintenance.window import (QuantState, WindowError, WindowState, parse_bans, parse_hhmm,
    quant_state, wait_for_slot, window_config, window_state)

BANS=((time(23,50),time(0,30)),(time(3,50),time(4,30)))


def cfg(**kwargs):
    """模拟 maintenance.config 的窗口字段；duck typing，只给被测代码会读的键。"""
    fields={'window_tz':'Asia/Shanghai','window_start':'22:00','window_end':'06:00','window_bans':BANS,
        'min_segment_minutes':20}
    fields.update(kwargs);return SimpleNamespace(**fields)


def at(hh,mm):
    """上海墙钟 hh:mm -> 同一瞬间的 UTC aware datetime（模块收到 UTC，意图是上海墙上时间）。"""
    return datetime(2026,9,18,hh,mm,tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)


def test_helper_maps_shanghai_wall_clock_to_utc():
    """先自检测试助手：上海 22:00 就是 14:00Z，避免用例自己算错。"""
    assert at(22,0)==datetime(2026,9,18,14,0,tzinfo=timezone.utc)


@pytest.mark.parametrize('text,expected',[('22:00',time(22,0)),('06:00',time(6,0)),('00:00',time(0,0)),
    ('23:59',time(23,59)),(' 22:30 ',time(22,30))])
def test_parse_hhmm_accepts_clock_values(text,expected):
    assert parse_hhmm(text)==expected


@pytest.mark.parametrize('text',['25:00','abc','22','22:60','','22:00:00','-1:00','12:3a','2400'])
def test_parse_hhmm_rejects_bad_format_and_range(text):
    """格式错（'abc'/'22'）与越界（'25:00'/'22:60'）都必须 WindowError。"""
    with pytest.raises(WindowError):parse_hhmm(text)


def test_window_error_is_a_runtime_error():
    assert issubclass(WindowError,RuntimeError)


def test_parse_bans_reads_comma_separated_ranges():
    assert parse_bans('23:50-00:30,03:50-04:30')==((time(23,50),time(0,30)),(time(3,50),time(4,30)))


def test_parse_bans_treats_empty_text_as_no_bans():
    assert parse_bans('')==() and parse_bans('  ')==() and parse_bans(',,')==()


@pytest.mark.parametrize('text',['2350','23:50','23:50-','-00:30','23:50-00:30-01:00','23:70-00:30','23:50-x'])
def test_parse_bans_rejects_malformed_ranges(text):
    with pytest.raises(WindowError):parse_bans(text)


def test_window_config_reads_duck_typed_fields():
    assert window_config(cfg())==('Asia/Shanghai',time(22,0),time(6,0),BANS,20)


def test_window_config_defaults_when_fields_are_absent():
    """缺字段时的默认值：上海、22:00-06:00、无禁运、最小段 20 分钟。"""
    assert window_config(SimpleNamespace())==('Asia/Shanghai',time(22,0),time(6,0),(),20)


@pytest.mark.parametrize('hh,mm,expected',[(21,59,False),(22,0,True),(23,49,True),(23,50,False),(0,0,False),
    (0,29,False),(0,30,True),(3,49,True),(3,50,False),(4,29,False),(4,30,True),(5,59,True),(6,0,False)])
def test_window_boundaries_are_half_open_on_shanghai_wall_clock(hh,mm,expected):
    """22:00 含、06:00 不含；禁运起点含、终点不含（全部按上海墙钟）。"""
    # 本表只验证时间闸门，所以把最小段降到 1 分钟：默认 20 分钟会额外关掉每段末尾的几分钟，
    # 那属于 test_default_min_segment_closes_the_trailing_minutes 覆盖的行为。
    assert window_state(cfg(min_segment_minutes=1),at(hh,mm)).open is expected


@pytest.mark.parametrize('hh,mm',[(23,49),(3,49),(5,59)])
def test_default_min_segment_closes_the_trailing_minutes(hh,mm):
    """默认 20 分钟下限：23:49 / 03:49 / 05:59 仍在窗口内，但只剩 1 分钟，故判为关闭。"""
    state=window_state(cfg(),at(hh,mm))
    assert not state.open and state.minutes_left==1
    assert '只剩 1 分钟' in state.reason and '至少需要 20 分钟' in state.reason


def test_window_tz_drives_the_conversion_not_the_host_clock():
    """同一瞬间 14:00Z：按上海算是 22:00（开），按 UTC 算是 14:00（关）。"""
    instant=datetime(2026,9,18,14,0,tzinfo=timezone.utc)
    assert window_state(cfg(window_tz='Asia/Shanghai'),instant).open
    assert not window_state(cfg(window_tz='UTC'),instant).open


def test_same_utc_instant_is_host_timezone_independent(monkeypatch):
    """宿主机 TZ 不得影响结果：换算全部走 astimezone(ZoneInfo(window_tz))。

    这里只改 TZ 环境变量、不调用 tzset（Windows 上也没有 tzset）：换算本身是显式的，
    实现读不到宿主机本地时间，所以同一 UTC 瞬间的结果不可能随 TZ 漂移。
    """
    instant=at(23,55)
    states=[]
    for zone in ['UTC','America/New_York','Pacific/Kiritimati']:
        monkeypatch.setenv('TZ',zone)
        states.append(window_state(cfg(),instant))
    assert states[0]==states[1]==states[2]
    assert not states[0].open and states[0].minutes_left==0


def test_local_now_is_only_read_with_an_explicit_timezone(monkeypatch):
    """把模块里的 datetime 换成拒绝 now() 不带 tz 的替身：默认分支也必须显式给 UTC。"""
    calls=[]
    class Guarded(datetime):
        @classmethod
        def now(cls,tz=None):
            calls.append(tz)
            assert tz is not None,'window_state 不得读取宿主机本地时间'
            return super().now(tz)
    monkeypatch.setattr(window,'datetime',Guarded)
    state=window_state(cfg())
    assert calls and calls[0]==timezone.utc
    assert isinstance(state,WindowState) and bool(state) is state.open


@pytest.mark.parametrize('hh,mm,left',[(22,0,110),(0,30,200),(4,30,90)])
def test_minutes_left_counts_to_the_next_ban_or_window_end(hh,mm,left):
    state=window_state(cfg(),at(hh,mm))
    assert state.open and state.minutes_left==left


def test_min_segment_rule_refuses_a_too_short_segment():
    """23:40 只剩 10 分钟 < 20 分钟下限 -> 关闭，并在原因里报出剩余分钟数。"""
    state=window_state(cfg(),at(23,40))
    assert not state.open and state.minutes_left==10
    assert '只剩 10 分钟' in state.reason


def test_segment_with_enough_room_stays_open():
    state=window_state(cfg(),at(23,20))
    assert state.open and state.minutes_left==30


def test_config_without_bans_uses_the_whole_window():
    config=cfg(window_bans=())
    start=window_state(config,at(22,0))
    assert start.open and start.minutes_left==480
    assert window_state(config,at(2,0)).open and window_state(config,at(5,0)).open


def test_ban_crossing_midnight_closes_both_sides():
    """23:50-00:30 跨午夜：23:55 与 00:10 都关闭，23:45 与 00:35 仍可开工。"""
    config=cfg(min_segment_minutes=1)  # 只验证跨午夜禁运；23:45 到这里只剩 5 分钟
    assert not window_state(config,at(23,55)).open
    assert not window_state(config,at(0,10)).open
    assert window_state(config,at(23,45)).open
    assert window_state(config,at(0,35)).open


def test_window_state_bool_matches_open():
    assert bool(window_state(cfg(),at(22,0))) is True
    assert bool(window_state(cfg(),at(0,0))) is False


def test_quant_state_without_watched_units_is_ok():
    """没有配置量化单元（或全是空串）时不算让行，也不会去调用 runner。"""
    def forbidden(units):raise AssertionError('空单元列表不得触发 systemctl')
    state=quant_state((),runner=forbidden)
    assert state.ok and state==QuantState() and state.reason()==''
    assert quant_state(('',),runner=forbidden).ok


def test_quant_state_reports_active_units_by_name():
    seen=[]
    def runner(units):seen.append(units);return ('quant-b',)
    state=quant_state(('quant-a','quant-b'),runner=runner)
    assert seen==[('quant-a','quant-b')] and state.busy==('quant-b',)
    assert not state.ok and state.reason() and 'quant-b' in state.reason()


def test_quant_state_is_fail_closed_when_status_is_unknown():
    """runner 抛 WindowError（systemctl 不可用）时必须 unknown，绝不能当成空闲放行。"""
    def broken(units):raise WindowError('systemctl 不可用，无法确认量化任务状态')
    state=quant_state(('quant-a',),runner=broken)
    assert state.unknown and not state.ok and state.busy==() and state.reason()


def test_wait_for_slot_returns_ready_when_window_open_and_quant_idle():
    slept=[]
    ready,reason=wait_for_slot(cfg(),(),sleep=slept.append,attempts=3,now=lambda:at(22,30))
    assert (ready,reason)==(True,'') and slept==[]


def test_wait_for_slot_gives_up_after_the_attempt_budget_when_closed():
    slept=[]
    ready,reason=wait_for_slot(cfg(),(),sleep=slept.append,attempts=3,now=lambda:at(12,0))
    assert ready is False and reason and '维护时段' in reason
    assert len(slept)==2 and len(slept)<=3-1  # sleep 最多 attempts-1 次
    assert slept==[60,60]  # slot_pause_seconds 默认 60


def test_wait_for_slot_reads_attempts_and_pause_from_config():
    slept=[]
    ready,reason=wait_for_slot(cfg(slot_attempts=2,slot_pause_seconds=0.5),(),sleep=slept.append,now=lambda:at(12,0))
    assert ready is False and reason and slept==[0.5]


def test_wait_for_slot_will_not_start_while_a_quant_unit_runs():
    """量化任务在跑：即使窗口开着也要让行，reason 里带上单元名。"""
    slept=[]
    ready,reason=wait_for_slot(cfg(),('quant-a',),sleep=slept.append,attempts=3,now=lambda:at(22,30),
        runner=lambda units:('quant-a',))
    assert ready is False and 'quant-a' in reason and len(slept)==2


def test_window_state_rejects_a_naive_datetime():
    """不接受本地时间：窗口随时区漂移正是本模块要防的缺陷。"""
    with pytest.raises(WindowError):
        window_state(cfg(),datetime(2026,9,19,23,55))


def test_window_state_rejects_an_unknown_timezone():
    with pytest.raises(WindowError):
        window_state(cfg(window_tz='Mars/Olympus'),at(23,0))


@pytest.mark.parametrize('hh,mm,expected',[
    (20,0,120),   # 20:00 -> 22:00 开窗
    (23,55,35),   # 23:55 -> 00:30 让行结束
    (0,10,20),    # 00:10 -> 00:30 让行结束
    (3,55,35),    # 03:55 -> 04:30 让行结束
    (6,30,930),   # 06:30 -> 次日 22:00
])
def test_closed_state_reports_minutes_until_next_segment(hh,mm,expected):
    """关闭状态必须告诉调用方还要等多久，而不是只给一个 0。"""
    state=window_state(cfg(),at(hh,mm))
    assert state.open is False and state.opens_in==expected and state.minutes_left==0
    assert state.wait_hint()


def test_open_state_has_no_wait_hint():
    state=window_state(cfg(),at(22,30))
    assert state.open is True and state.opens_in==0 and state.wait_hint()==''
