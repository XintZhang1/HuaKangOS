"""Original phase transitions, repeated contacts, closed gaps and local cutoffs."""
from datetime import datetime, timedelta, time, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.db import SessionLocal, engine, today
from app.flow_models import FlowEvent
from app.presales_stage_analytics import replay, build, STAGES
from tests.conftest import login
from tests.test_repair_orders import technician
from tests import test_visit_activity as visit
from tests.test_workflow import action, create


def example(transitions, final=None, parent=None):
    start=datetime(2026,1,10,0,0)
    events=[SimpleNamespace(id=i+1,case_id=1,store_id=1,action=kind,before_state=before,
        after_state=after,occurred_at=start+timedelta(minutes=minute),detail=detail)
        for i,(minute,kind,before,after,detail) in enumerate(transitions)]
    case=SimpleNamespace(id=1,store_id=1,kind='lead',number='合成阶段原单',created_at=start,
        updated_at=events[-1].occurred_at if events else start,
        state=final or (events[-1].after_state if events else 'intent'),parent_id=parent)
    return case,events,start


def standard():
    return [(0,'create','','unassigned',{}),(10,'assign','unassigned','contacting',{}),
        (20,'remind','contacting','reminder',{}),(40,'remind','reminder','reminder',{}),
        (60,'intent','reminder','intent',{}),(80,'follow','intent','intent',{}),
        (100,'close','intent','closed',{}),(200,'reopen','closed','intent',{}),
        (230,'follow','intent','intent',{})]


def test_repeated_contacts_do_not_reset_start_and_reopen_does_not_count_closed_gap():
    case,events,start=example(standard())
    rows,issue=replay(case,events,start+timedelta(minutes=300),check_current=True)
    assert issue is None
    assert [r['elapsed_microseconds'] for r in rows[:-1]]==[10*60_000_000,10*60_000_000,40*60_000_000,40*60_000_000]
    assert [r['stage'] for r in rows]==['unassigned','contacting','reminder','intent','intent']
    assert rows[-1]['cycle']==2 and rows[-1]['start_event_id']==8
    assert rows[-1]['elapsed_microseconds'] is None
    assert rows[-1]['observed_microseconds']==100*60_000_000


def test_historical_end_is_right_censored_even_if_later_closed():
    case,events,start=example(standard()[:7])
    rows,issue=replay(case,events,start+timedelta(minutes=70))
    assert issue is None and rows[-1]['stage']=='intent' and rows[-1]['ended_at'] is None
    assert rows[-1]['observed_microseconds']==10*60_000_000


@pytest.mark.parametrize('mutation',['missing_create','duplicate_create','wrong_before','wrong_action','wrong_store','unlogged_current'])
def test_missing_or_inconsistent_sources_are_not_guessed_from_current_state(mutation):
    case,events,start=example(standard())
    if mutation=='missing_create':events=events[1:]
    elif mutation=='duplicate_create':events[3].action='create'
    elif mutation=='wrong_before':events[2].before_state='intent'
    elif mutation=='wrong_action':events[2].action='reserve'
    elif mutation=='wrong_store':events[2].store_id=2
    elif mutation=='unlogged_current':case.state='converted'
    rows,issue=replay(case,events,start+timedelta(minutes=300),check_current=True)
    assert rows==[] and issue


def test_callback_intent_needs_original_parent_attribution():
    case,events,start=example([(0,'create','','unassigned',{}),
        (1,'callback_intent','unassigned','intent',{'callback_case_id':77})],parent=77)
    rows,issue=replay(case,events,start+timedelta(minutes=10),True)
    assert issue is None and rows[-1]['stage']=='intent' and rows[-1]['start_event_id']==2
    events[1].detail={'callback_case_id':78}
    assert replay(case,events,start+timedelta(minutes=10),True)[1]


def test_closed_cohort_by_local_end_day_open_not_in_mean_and_group_no_routes():
    zone=ZoneInfo(settings.timezone)
    local_start=datetime(2026,1,9,23,0,tzinfo=zone)
    utc_start=local_start.astimezone(timezone.utc).replace(tzinfo=None)
    case,events,_=example(standard())
    for e in events:e.occurred_at=utc_start+timedelta(minutes=(e.occurred_at-datetime(2026,1,10)).total_seconds()/60)
    case.created_at=utc_start;case.updated_at=events[-1].occurred_at
    report=build({1:case},events,datetime(2026,1,10).date(),datetime(2026,1,10).date(),True,
        now=utc_start+timedelta(days=2))
    assert report['metrics']['presales_ended_stage_count']==2  # Midnight reminder exit, then intent close.
    assert report['metrics']['presales_open_stage_count']==1
    finished=report['tables']['presales_stage_durations']['rows']
    assert [r['elapsed_microseconds'] for r in finished]==[40*60_000_000,40*60_000_000]
    summary=next(r for r in report['tables']['presales_stage_summary']['rows'] if r['stage']=='intent')
    assert summary['completed_count']==1 and summary['open_count']==1 and summary['mean_minutes']=='40.00'
    assert all(r['route'] is None for t in report['tables'].values() for r in t['rows'])


def test_real_registered_lead_actions_phase_tables_chart_csv_and_role_scope(client):
    row=visit.lead(client);login(client,'sales')
    row=action(client,row,'remind',{'due_date':today().isoformat(),'result':'第一次明确接待后回访，保留原进入阶段'})
    row=action(client,row,'remind',{'due_date':today().isoformat(),'result':'再次沟通仍在同一阶段，不重新开始计时'})
    row=action(client,row,'intent',{'due_date':today().isoformat(),'need':'客户明确提出新的实际购车需求'})
    row=action(client,row,'follow',{'due_date':today().isoformat(),'result':'意向跟进不重置阶段起点'})
    row=action(client,row,'close',{'reason':'客户本次暂时停止购车，保留原终止事件','no_contact':False})
    row=action(client,row,'reopen',{'due_date':today().isoformat(),'reason':'客户主动重新发起本轮购车沟通'})
    with SessionLocal() as db:
        events=list(db.scalars(select(FlowEvent).where(FlowEvent.case_id==row['id']).order_by(FlowEvent.id)))
    assert [e.action for e in events]==['create','assign','remind','remind','intent','follow','close','reopen']
    # Synthetic time fixture changes only timestamps, preserving the exact
    # production-created source IDs, users, state transitions and payloads.
    local=datetime.combine(today()-timedelta(days=1),time(8),tzinfo=ZoneInfo(settings.timezone))
    base=local.astimezone(timezone.utc).replace(tzinfo=None)
    for event,minute in zip(events,[0,10,20,40,60,80,100,200]):
        with engine.begin() as db:
            db.execute(text('UPDATE flow_events SET occurred_at=:stamp WHERE id=:id'),
                {'stamp':base+timedelta(minutes=minute),'id':event.id})
    params={'date_from':(today()-timedelta(days=1)).isoformat(),'date_to':today().isoformat()}
    result=visit.report(client,**params)
    assert result['complete'] and result['metrics']['presales_ended_stage_count']==4
    assert result['metrics']['presales_open_stage_count']==1
    assert result['tables']['presales_open_stages']['rows'][0]['cycle']==2
    for key in ['presales_stage_durations','presales_open_stages','presales_stage_summary']:
        visit.csv_same(client,result,key,**params)
    chart=next(c for c in result['charts'] if c['id']=='presales_stage_summary')
    assert chart['unit']=='minutes' and chart['series'][0]['values']==[10.0,10.0,40.0,40.0]
    login(client,'technician')
    assert client.get(visit.API+'/export/presales_stage_durations').status_code==403


def test_reopen_clears_current_completed_date_without_erasing_original_close(client):
    from app.flow_models import Case
    row=visit.lead(client);login(client,'sales')
    action(client,row,'close',{'reason':'本人记录本次实际结束的原因','no_contact':False})
    with SessionLocal() as db:assert db.get(Case,row['id']).completed_date==today()
    action(client,row,'reopen',{'reason':'客户主动提出另一次沟通需求','due_date':today().isoformat()})
    with SessionLocal() as db:
        assert db.get(Case,row['id']).completed_date is None
        assert len(list(db.scalars(select(FlowEvent).where(FlowEvent.case_id==row['id'],FlowEvent.action=='close'))))==1
