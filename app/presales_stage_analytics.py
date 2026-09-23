"""Replay presales stage residence from original state-transition events.

Residence is elapsed calendar time, not employee labour, performance or a sales
prediction. Ended stages and right-censored open stages are separate populations.
No source is synthesized from mutable current status or a next-contact due date.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from .config import settings
from .db import utcnow

STAGES = {'unassigned': '待分派接待', 'contacting': '接待沟通',
    'reminder': '接待后回访', 'intent': '意向跟进'}
TERMINAL = {'closed', 'converted'}
ACTIONS = {'create', 'assign', 'intent', 'remind', 'follow', 'reserve',
    'close', 'reopen', 'callback_intent'}
DEFINITIONS = [
    '售前阶段停留按原状态迁移事件计算自然经过时间，不是员工工时、工作量或绩效。重复回访及意向跟进没有改变阶段时，不重置起点。结束后重新开启另记轮次；结束期间不计入下一轮。',
    '已结束阶段按实际结束日纳入期间均值，包含此前开始、在本期结束的阶段。截至期间末尚未结束的阶段单列，不把观察时长混入已结束阶段均值；本期未结束不代表今天仍未结束。',
    '缺少建立事件、迁移前后状态不连续或旧回访转意向没有明确子单迁移来源时，列为待核对，不从当前状态、任务日期或计划联系日期补造历史。',
]


def local(stamp):
    return stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone))


def microseconds(start, end):
    delta = end-start
    return (delta.days*86400+delta.seconds)*1_000_000+delta.microseconds


def minutes(value):
    return format((Decimal(value)/Decimal(60_000_000)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'f')


def replay(case, events, cutoff, check_current=False):
    """Return attributable intervals, or omit this case with an explicit issue."""
    history = sorted((e for e in events if e.case_id == case.id and e.action in ACTIONS
        and e.occurred_at < cutoff), key=lambda e: (e.occurred_at, e.id))
    if not history:
        if case.created_at < cutoff:
            return [], '售前阶段缺少原建立及迁移事件，不能按当前状态推算'
        return [], None
    if history[0].action != 'create' or history[0].before_state not in {'', None} or history[0].after_state != 'unassigned':
        return [], '售前阶段没有唯一有效的原建立事件'
    state = 'unassigned'; start = history[0]; cycle = 1; intervals = []
    for event in history:
        if event.store_id != case.store_id or event.case_id != case.id:
            return [], '售前阶段事件与原门店或原单不一致'
        if event is history[0]:
            continue
        before, after, action = event.before_state, event.after_state, event.action
        if action == 'create' or before != state or after not in STAGES.keys() | TERMINAL:
            return [], '售前阶段前后状态不连续或建立事件重复，不能推算停留时长'
        allowed = {
            'assign': before=='unassigned' and after=='contacting',
            'intent': before in {'contacting','reminder'} and after=='intent',
            'remind': before in {'contacting','reminder'} and after=='reminder',
            'follow': before=='intent' and after=='intent',
            'reserve': before=='intent' and after=='converted',
            'close': before in {'contacting','reminder','intent'} and after=='closed',
            'reopen': before=='closed' and after=='intent',
            'callback_intent': before=='unassigned' and after=='intent'
                and (event.detail or {}).get('callback_case_id') == case.parent_id and case.parent_id is not None,
        }.get(action, False)
        if not allowed:
            return [], '售前阶段动作与原迁移类型不一致，不能按当前资料补算'
        if before == after:
            continue
        if state in STAGES:
            elapsed = microseconds(start.occurred_at, event.occurred_at)
            if elapsed < 0:
                return [], '售前阶段原事件时间先后冲突'
            intervals.append({'stage': state, 'cycle': cycle, 'started_at': start.occurred_at,
                'start_event_id': start.id, 'ended_at': event.occurred_at, 'end_event_id': event.id,
                'elapsed_microseconds': elapsed, 'end_action': action})
        if state in TERMINAL and after in STAGES:
            cycle += 1
        state = after; start = event
    if check_current and state != case.state:
        return [], '售前当前状态与最后一条原迁移不一致；旧无来源方向不反推阶段'
    if state in STAGES:
        intervals.append({'stage': state, 'cycle': cycle, 'started_at': start.occurred_at,
            'start_event_id': start.id, 'ended_at': None, 'end_event_id': None,
            'elapsed_microseconds': None, 'observed_microseconds': microseconds(start.occurred_at, cutoff)})
    return intervals, None


def build(cases, events, start, end, aggregate=False, now=None):
    now = now or utcnow()
    zone = ZoneInfo(settings.timezone)
    utc = lambda value: value.astimezone(timezone.utc).replace(tzinfo=None)
    left = utc(datetime.combine(start, time.min, tzinfo=zone))
    next_day = utc(datetime.combine(end+timedelta(days=1), time.min, tzinfo=zone))
    cutoff = min(next_day, now)
    closed, open_rows, issues = [], [], []
    for case in cases.values():
        if case.kind != 'lead': continue
        history, issue = replay(case, events, cutoff, check_current=getattr(case, 'updated_at', case.created_at) < cutoff)
        if issue:
            issues.append({'case_id':case.id, 'source_id':None, 'message':issue})
            continue
        for item in history:
            row = dict(item, case_id=case.id, store_id=case.store_id, number=case.number)
            if item['ended_at'] is None:
                open_rows.append(row)
            elif left <= item['ended_at'] < cutoff:
                closed.append(row)
    tables = {}; charts = []
    def table(key, title, headers):
        result={'id':key,'title':title,'headers':headers,'rows':[]};tables[key]=result;return result
    def put(target, row, values, **facts):
        target['rows'].append({'values':values, 'case_id':row['case_id'], 'store_id':row['store_id'],
            'route':None if aggregate else {'type':'case','id':row['case_id']}, **facts})
    finished=table('presales_stage_durations','期间实际结束的售前阶段',
        ['原单','轮次','阶段','原进入时间','原结束时间','自然停留（分钟）'])
    for row in closed:
        put(finished,row,[row['number'],row['cycle'],STAGES[row['stage']],
            local(row['started_at']).strftime('%Y-%m-%d %H:%M:%S'),
            local(row['ended_at']).strftime('%Y-%m-%d %H:%M:%S'),minutes(row['elapsed_microseconds'])],
            stage=row['stage'],cycle=row['cycle'],start_event_id=row['start_event_id'],end_event_id=row['end_event_id'],
            elapsed_microseconds=row['elapsed_microseconds'],count=1)
    pending=table('presales_open_stages','截至期间末尚未结束的售前阶段',
        ['原单','轮次','当前观察阶段','原进入时间','所选截止日期','耗时口径'])
    for row in open_rows:
        put(pending,row,[row['number'],row['cycle'],STAGES[row['stage']],
            local(row['started_at']).strftime('%Y-%m-%d %H:%M:%S'),
            end.isoformat(),'未结束，不参与已结束阶段均值'],
            stage=row['stage'],cycle=row['cycle'],start_event_id=row['start_event_id'],end_event_id=None,
            elapsed_microseconds=None,count=1)
    summary=table('presales_stage_summary','已结束阶段均值与未结束量分别核对',
        ['阶段','期间实际结束段数','实际结束段总停留（分钟）','实际结束段平均停留（分钟）','截至期末未结束段数'])
    averages=[];closed_counts=defaultdict(int);open_counts=defaultdict(int)
    for stage, label in STAGES.items():
        selected=[r for r in closed if r['stage']==stage]
        total=sum(r['elapsed_microseconds'] for r in selected)
        count=len(selected);active=sum(r['stage']==stage for r in open_rows)
        avg=minutes(Decimal(total)/count) if count else None
        summary['rows'].append({'values':[label,count,minutes(total),avg if avg is not None else '无已结束样本',active],
            'stage':stage,'completed_count':count,'open_count':active,'total_microseconds':total,'mean_minutes':avg,'route':None})
        closed_counts[stage]=count;open_counts[stage]=active
        if count:averages.append((label,float(avg)))
    charts.append({'id':'presales_stage_summary','title':'已结束售前阶段平均自然停留',
        'section':'sales','type':'bar','unit':'minutes','labels':[r[0] for r in averages],
        'series':[{'name':'已结束阶段平均分钟','values':[r[1] for r in averages]}],
        'table':'presales_stage_summary','caption':DEFINITIONS[0]+' '+DEFINITIONS[1]})
    return {'tables':tables,'charts':charts,'issues':issues,'definitions':DEFINITIONS,
        'metrics':{'presales_ended_stage_count':len(closed),'presales_open_stage_count':len(open_rows),
            'presales_stage_source_issues':len(issues)},'observed_until':local(cutoff).isoformat()}
