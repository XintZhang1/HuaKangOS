"""Read-only validation of gate origins, independent corrections and intake aliases.

Digests detect inconsistent stored sources. They are not external signatures and
cannot resist an administrator rewriting all matching origins and metadata.
"""
import json
from datetime import datetime, timezone

TABLES = {'gate_visits','gate_facts','gate_corrections','gate_reviews','gate_handoffs','gate_repair_exits'}


def stamp(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value,str):
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    else:
        raise ValueError('进出厂恢复检查：原时间字段不是有效时间')
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def iso(value):
    return stamp(value).isoformat() + 'Z' if value is not None else None


def digest(payload):
    # This is the exact flow_engine.request_digest operation envelope.
    from .flow_engine import request_digest
    return request_digest('gate_origin', payload)


def check_bundle(visit, facts, corrections, reviews, events, files):
    """Replay recorded facts and independent reviews in their original order.

    A corrected arrival may legitimately precede a later-recorded departure
    whose time is earlier than the erroneous raw arrival. Comparing all raw
    timestamps before replaying corrections would wrongly reject that history.
    """
    def fail(message):
        raise ValueError('进出厂恢复检查：' + message)
    def proof(key):
        f = files.get(key)
        if not f or f['store_id'] != visit['store_id'] or f['case_id'] != visit['case_id'] or f['generated']:
            fail('实际凭据不是本门店原登记的上传文件')
    def original(action, key, value):
        matching = [e for e in events if e['case_id'] == visit['case_id'] and e['action'] == action and e['detail'].get(key) == value]
        if len(matching) != 1 or matching[0]['store_id'] != visit['store_id']:
            fail('原不可变动作缺失、重复或跨店')
        return matching[0]
    def chronology(eff):
        if eff['leave'] is not None and (eff['arrive'] is None or eff['leave'] < eff['arrive']):
            fail('该次原动作生效时的先后关系不成立')
    if any(not isinstance(e['detail'],dict) for e in events if e['case_id']==visit['case_id']):
        fail('原事件事实字段形状损坏')
    plan = original('gate_plan', 'visit_id', visit['id'])
    if any(plan['detail'].get(k) != visit[k] for k in ('customer_vehicle_id','vin','purpose','description')):
        fail('来访身份或原用途被改写')
    tape = []
    seen = set()
    for f in facts:
        if f['store_id'] != visit['store_id'] or f['direction'] in seen or f['direction'] not in {'arrive','leave'}:
            fail('原进出方向重复、未知或跨店')
        seen.add(f['direction']); proof(f['evidence_id'])
        if stamp(f['actual_at']) > stamp(f['created_at']) or stamp(f['actual_at']).year < 2000:
            fail('原事实时间晚于登记时间或早于支持范围')
        event = original('gate_' + f['direction'], 'fact_id', f['id']); detail = event['detail']
        if (event['actor_id'] != f['actor_id'] or detail.get('confirmed') is not True or detail.get('checked_vin') != visit['vin']
            or detail.get('evidence_id') != f['evidence_id'] or detail.get('reason') != f['reason'] or not detail.get('actual_at')
            or stamp(detail['actual_at']) != stamp(f['actual_at']) or stamp(event['occurred_at']) < stamp(f['created_at'])):
            fail('进出厂事实与原经办确认、时间或凭据不一致')
        tape.append((stamp(f['created_at']), 0, f['id'], 'fact', f))
    for c in corrections:
        if c['store_id'] != visit['store_id']:
            fail('纠正申请跨店')
        proof(c['evidence_id'])
        if c['kind'] not in {'void_visit','arrive_time','leave_time'} or c['status'] not in {'pending','approved','rejected','cancelled'}:
            fail('纠正类型或状态未知')
        if (c['kind'] == 'void_visit') != (c['actual_at'] is None):
            fail('纠正时间的原始形状不一致')
        if c['actual_at'] and (stamp(c['actual_at']) > stamp(c['created_at']) or stamp(c['actual_at']).year < 2000):
            fail('纠正目标是尚未发生或不受支持的时间')
        event = original('gate_correction_request', 'correction_id', c['id']); d = event['detail']
        if (event['actor_id'] != c['requested_by'] or d.get('origin_digest') != c['origin_digest'] or any(d.get(k) != c[k] for k in ('kind','evidence_id','reason'))
            or iso(d.get('actual_at')) != iso(c['actual_at']) or stamp(event['occurred_at']) < stamp(c['created_at'])):
            fail('纠正申请与原经办来源不一致')
        tape.append((stamp(c['created_at']), 1, c['id'], 'request', c))
        review = reviews.get(c['id'])
        if c['status'] == 'pending':
            if c['active_visit_id'] != visit['id'] or review:
                fail('待复核占用不一致')
            continue
        if c['active_visit_id'] is not None:
            fail('已处理申请仍占用待办')
        action = {'approved':'approve','rejected':'reject','cancelled':'cancel'}[c['status']]
        evt = original('gate_correction_' + action, 'correction_id', c['id'])
        if c['status'] == 'cancelled':
            if review or evt['actor_id'] != c['requested_by']:
                fail('撤回并非原申请人或伪造独立复核')
            processed_at = stamp(evt['occurred_at'])
        else:
            if not review or review['store_id'] != visit['store_id'] or review['decision'] != c['status'] or review['actor_id'] == c['requested_by']:
                fail('独立复核缺失、结果不一致或自批')
            proof(review['evidence_id'])
            if review['actor_id'] != evt['actor_id'] or any(evt['detail'].get(k) != review[k] for k in ('reason','evidence_id')):
                fail('复核事实与原经办事件不一致')
            processed_at = stamp(review['created_at'])
            if stamp(evt['occurred_at']) < processed_at:
                fail('复核经办事件早于实际复核记录')
        if processed_at < stamp(c['created_at']):
            fail('复核或撤回早于申请')
        tape.append((processed_at, 2, c['id'], 'process', c))
    eff = {'arrive': None, 'leave': None, 'voided': False}
    approved, recorded = [], []
    pending = None
    def current_digest():
        return digest({'visit_id': visit['id'], 'case_id': visit['case_id'], 'vin': visit['vin'],
            'facts': [{'id': f['id'], 'direction': f['direction'], 'actual_at': iso(f['actual_at']), 'evidence_id': f['evidence_id'], 'actor_id': f['actor_id'], 'reason': f['reason']} for f in sorted(recorded,key=lambda r:r['id'])],
            'reviews': approved[:], 'arrive': iso(eff['arrive']), 'leave': iso(eff['leave']), 'voided': eff['voided']})
    for when, _, _, kind, entry in sorted(tape, key=lambda r:r[:3]):
        if when < stamp(plan['occurred_at']):
            fail('实际登记或纠正发生在原来访安排之前')
        if kind == 'fact':
            if pending is not None or eff['voided']:
                fail('未决纠正或已撤销事实之后又追加实际进出厂')
            eff[entry['direction']] = stamp(entry['actual_at'])
            chronology(eff); recorded.append(entry)
        elif kind == 'request':
            if pending is not None:
                fail('同一次进出厂存在同时未决的纠正')
            if not eff['arrive'] or eff['voided'] or (entry['kind'] != 'void_visit' and eff[entry['kind'].removesuffix('_time')] is None):
                fail('纠正试图凭空创建不存在的实际方向')
            if entry['origin_digest'] != current_digest():
                fail('纠正未绑定提出时的原事实与此前已批记录')
            proposed = dict(eff)
            if entry['kind'] != 'void_visit':
                proposed[entry['kind'].removesuffix('_time')] = stamp(entry['actual_at'])
                chronology(proposed)
            pending = entry['id']
        else:
            if pending != entry['id'] or entry['origin_digest'] != current_digest():
                fail('复核不对应仍有效的原待处理申请')
            if entry['status'] == 'approved':
                if entry['kind'] == 'void_visit':
                    eff['voided'] = True
                else:
                    eff[entry['kind'].removesuffix('_time')] = stamp(entry['actual_at'])
                    chronology(eff)
                approved.append(entry['id'])
            pending = None
    expected_state = 'voided' if eff['voided'] else 'departed' if eff['leave'] else 'inside' if eff['arrive'] else 'planned'
    status = visit['status']
    if status == 'handed_over':
        if expected_state != 'inside' or pending is not None:
            fail('转接必须有未离场且无未决纠正的原进厂')
    elif status == 'cancelled':
        if expected_state != 'planned' or not any(e['case_id']==visit['case_id'] and e['action']=='gate_cancel' for e in events):
            fail('取消掩盖实际进厂或缺少取消来源')
    elif status != expected_state:
        fail('当前办理状态与不可变事实不一致')
    eff['digest'] = current_digest()
    return eff

def check_cancelled_exit(row, fact, binding, vehicle, arrived_at, events, files):
    """Verify the extra physical exit against the original cancelled repair."""
    def fail(message): raise ValueError('进出厂恢复检查：' + message)
    data = json.loads(row['data']) if row and isinstance(row['data'],str) else row['data'] if row else {}
    if (not row or row['store_id'] != fact['store_id'] or row['kind'] != 'repair' or row['flow_version'] != 4
        or row['state'] != 'cancelled' or data.get('released_date')):
        fail('额外离场并非原取消维修')
    if (not binding or binding['store_id'] != fact['store_id'] or binding['case_id'] != row['id']
        or not vehicle or vehicle['id']!=binding['customer_vehicle_id'] or vehicle['store_id']!=fact['store_id']
        or vehicle['customer_id']!=row['customer_id'] or vehicle['vin']!=binding['vin']
        or vehicle['customer_identity_id']!=binding['customer_identity_id'] or vehicle['vehicle_identity_id']!=binding['vehicle_identity_id'] or arrived_at is None):
        fail('取消维修离场没有同店原客户车辆及实际到店来源')
    proof = files.get(fact['evidence_id'])
    if not proof or proof['generated'] or proof['store_id'] != fact['store_id'] or proof['case_id'] != fact['case_id']:
        fail('取消维修离场凭据不属原单')
    local = [e for e in events if e['case_id'] == fact['case_id']]
    if any(not isinstance(e['detail'],dict) for e in local):fail('原取消及离场事件形状损坏')
    ev = [e for e in local if e['action'] == 'gate_cancelled_repair_exit']
    if (len(ev) != 1 or ev[0]['store_id'] != fact['store_id'] or ev[0]['actor_id'] != fact['actor_id']
        or ev[0]['detail'].get('fact_id') != fact['id'] or ev[0]['detail'].get('confirmed') is not True
        or ev[0]['detail'].get('checked_vin') != binding['vin'] or iso(ev[0]['detail'].get('actual_at')) != iso(fact['actual_at'])
        or any(ev[0]['detail'].get(k) != fact[k] for k in ('reason','evidence_id'))):
        fail('额外离场与原岗位确认、VIN或实际时间不一致')
    if (stamp(fact['actual_at']) < stamp(arrived_at) or stamp(fact['actual_at']) > stamp(fact['created_at'])
        or stamp(fact['actual_at']).year < 2000 or stamp(ev[0]['occurred_at']) < stamp(fact['created_at'])):
        fail('额外离场早于原实际进厂或是未来事实')
    cancellation = [e for e in local if e['action'] == 'repair_v4_cancel']
    if (len(cancellation) != 1 or cancellation[0]['store_id'] != fact['store_id']
        or stamp(cancellation[0]['occurred_at']) > stamp(fact['created_at'])
        or any(e['action'] == 'repair_v4_release' for e in local)):
        fail('取消维修的原取消来源缺失或重复记离场')
    return stamp(fact['actual_at'])


def validate_intervals(visits, effective_by, handoffs, appointments, arrivals, reworks, cases, events, exits):
    """Rebuild physical intervals; only new gate/extra-exit conflicts block here.

    Old intake-only histories remain the responsibility of their old validator;
    this does not silently manufacture exits to make historical overlaps fit.
    """
    def fail(message): raise ValueError('进出厂恢复检查：' + message)
    handed = {h['visit_id'] for h in handoffs}
    gate_cases = {v['case_id'] for v in visits.values()}
    output = []
    for v in visits.values():
        eff = effective_by[v['id']]
        if v['id'] not in handed and eff['arrive'] and not eff['voided']:
            output.append({'store_id':v['store_id'],'vin':v['vin'],'case_id':v['case_id'],'arrive':eff['arrive'],'leave':eff['leave'],'new':True})
    for f in arrivals.values():
        a = appointments.get(f['appointment_id'])
        if not a: fail('原到店事实缺少接待来源')
        output.append({'store_id':a['store_id'],'vin':f['checked_vin'],'case_id':a['case_id'],'repair_case_id':a['repair_case_id'],
            'arrive':stamp(f['occurred_at']),'leave':None,'new':a['case_id'] in gate_cases})
    rework_cases = {r['case_id']:r for r in reworks.values()}
    for e in events:
        if e['action'] != 'intake_rework_convert': continue
        r = rework_cases.get(e['case_id'])
        if not r or not r['repair_case_id']: fail('返修实际到店缺少原返修明细')
        output.append({'store_id':r['store_id'],'vin':e['detail'].get('checked_vin'),'case_id':r['case_id'],'repair_case_id':r['repair_case_id'],
            'arrive':stamp(e['occurred_at']),'leave':None,'new':False})
    exits_by = {x['case_id']:x for x in exits}
    for item in output:
        rid = item.get('repair_case_id')
        if rid:
            repair = cases.get(rid)
            if not repair: fail('原实际进厂对应的维修缺失')
            releases = [e for e in events if e['case_id']==rid and e['action']=='repair_v'+str(repair['flow_version'])+'_release']
            x = exits_by.get(rid)
            if len(releases) + int(x is not None)>1: fail('同一次维修重复记实际离场')
            if x: item.update(leave=stamp(x['actual_at']),new=True)
            elif releases: item['leave']=stamp(releases[0]['occurred_at'])
        elif 'repair_case_id' in item:
            leaves = [e for e in events if e['case_id']==item['case_id'] and e['action']=='intake_leave']
            if len(leaves)>1: fail('未开单接待重复记实际离场')
            if leaves: item['leave']=stamp(leaves[0]['occurred_at'])
    groups={}
    for item in output:
        if item['new'] and item['leave'] is not None and item['leave'] < item['arrive']:
            fail('原进出厂先后关系被改写')
        groups.setdefault((item['store_id'],item['vin']),[]).append(item)
    # A sweep avoids quadratic work on long-lived VIN histories. Exact touching
    # boundaries are allowed; zero-duration records sort before other same-start
    # intervals, matching the command's original disjointness predicate.
    for group in groups.values():
        any_end=new_end=None
        for item in sorted(group,key=lambda r:(r['arrive'],r['leave'] or datetime.max)):
            previous=any_end if item['new'] else new_end
            if previous is not None and previous>item['arrive']:
                fail('同店同VIN的实际在厂区间重叠；不得推测缺失的实际离场')
            end=item['leave'] or datetime.max
            any_end=max(any_end,end) if any_end is not None else end
            if item['new']:new_end=max(new_end,end) if new_end is not None else end
    return output


def validate(connection):
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not TABLES & names:
        return {'verified_gate_visits':0,'verified_gate_corrections':0,'verified_gate_handoffs':0,'verified_cancelled_repair_exits':0}
    if not TABLES <= names:
        raise ValueError('进出厂恢复检查：仅存在部分新表，不能按旧空域接受')
    def rows(name):
        cur=connection.execute('SELECT * FROM '+name); cols=[c[0] for c in cur.description]
        return [dict(zip(cols,r)) for r in cur]
    def by(name): return {r['id']:r for r in rows(name)}
    def fail(message): raise ValueError('进出厂恢复检查：'+message)
    visits=by('gate_visits'); facts=rows('gate_facts'); corrections=rows('gate_corrections'); reviews={r['correction_id']:r for r in rows('gate_reviews')}
    cases=by('flow_cases'); vehicles=by('care_customer_vehicles'); events=rows('flow_events')
    files={r[0]:dict(zip(('id','store_id','case_id','generated'),r)) for r in connection.execute('SELECT id,store_id,case_id,generated FROM flow_files')}
    for e in events:e['detail']=json.loads(e['detail']) if isinstance(e['detail'],str) else e['detail']
    handoffs=rows('gate_handoffs'); appointments=by('intake_appointments'); arrivals=by('intake_arrivals'); exits=rows('gate_repair_exits')
    effective_by={}
    for v in visits.values():
        row=cases.get(v['case_id']); vehicle=vehicles.get(v['customer_vehicle_id'])
        if not row or not vehicle or row['kind']!='service_intake' or row['flow_version']!=2 or row['store_id']!=v['store_id'] or vehicle['store_id']!=v['store_id'] or row['customer_id']!=vehicle['customer_id'] or vehicle['vin']!=v['vin']:
            fail('原客户、车辆或本店接待关联不一致')
        if (json.loads(row['data']) if isinstance(row['data'],str) else row['data']).get('gate_visit_id')!=v['id']:fail('原业务未关联本次进出厂')
        effective_by[v['id']]=check_bundle(v,[f for f in facts if f['visit_id']==v['id']],[c for c in corrections if c['visit_id']==v['id']],reviews,events,files)
        if v['status']!='handed_over':
            expected={'planned':'pending','inside':'working','departed':'completed','voided':'cancelled','cancelled':'cancelled'}[v['status']]
            if row['state']!=expected:fail('原单状态与门岗办理状态不一致')
        if (v['status']=='handed_over')!=(sum(h['visit_id']==v['id'] for h in handoffs)==1):fail('转接标记与唯一真实转接不一致')
    facts_by={f['id']:f for f in facts}
    for h in handoffs:
        v=visits.get(h['visit_id']); a=appointments.get(h['appointment_id']); alias=arrivals.get(h['arrival_fact_id']); original=facts_by.get(h['origin_fact_id'])
        if not v or not a or not alias or not original or h['store_id']!=v['store_id'] or a['store_id']!=v['store_id'] or a['case_id']!=v['case_id'] or a['customer_vehicle_id']!=v['customer_vehicle_id']:
            fail('转维修并非同门店同一原接待')
        if original['visit_id']!=v['id'] or original['direction']!='arrive' or alias['appointment_id']!=a['id'] or alias['store_id']!=v['store_id'] or alias['checked_vin']!=v['vin'] or alias['customer_vehicle_id']!=v['customer_vehicle_id']:
            fail('转接来源并非原实际进厂')
        eff=effective_by[v['id']]
        if h['origin_digest']!=eff['digest'] or stamp(alias['occurred_at'])!=eff['arrive'] or alias['evidence_id']!=original['evidence_id'] or alias['actor_id']!=original['actor_id']:
            fail('转接改写原时间、人员、凭据或已批准原来源')
        proof=files.get(h['evidence_id'])
        if not proof or proof['generated'] or proof['case_id']!=v['case_id'] or proof['store_id']!=v['store_id']:fail('转接缺少本次核验凭据')
        ev=[e for e in events if e['case_id']==v['case_id'] and e['action']=='gate_handoff']
        if len(ev)!=1 or ev[0]['actor_id']!=h['actor_id'] or ev[0]['detail'].get('evidence_id')!=h['evidence_id'] or ev[0]['detail'].get('odometer_km')!=alias['odometer_km']:
            fail('转接经办事件与车辆现场里程不一致')
    contexts={r['case_id']:r for r in rows('intake_repair_contexts')}
    bindings={r['case_id']:r for r in rows('intake_vehicle_bindings')}
    reworks=by('intake_rework_requests')
    for x in exits:
        row=cases.get(x['case_id']); context=contexts.get(x['case_id']); binding=bindings.get(x['case_id'])
        arrived_at=None
        if context and context['store_id']==x['store_id']:
            if context['appointment_id']:
                a=appointments.get(context['appointment_id'])
                sources=[f for f in arrivals.values() if f['appointment_id']==context['appointment_id']]
                if a and a['store_id']==x['store_id'] and a['repair_case_id']==x['case_id'] and len(sources)==1 and binding and sources[0]['checked_vin']==binding['vin']:
                    arrived_at=sources[0]['occurred_at']
            elif context['rework_id']:
                r=reworks.get(context['rework_id'])
                sources=[e for e in events if r and e['case_id']==r['case_id'] and e['action']=='intake_rework_convert']
                if r and r['store_id']==x['store_id'] and r['repair_case_id']==x['case_id'] and len(sources)==1 and binding and sources[0]['detail'].get('checked_vin')==binding['vin']:
                    arrived_at=sources[0]['occurred_at']
        check_cancelled_exit(row,x,binding,vehicles.get(binding['customer_vehicle_id']) if binding else None,arrived_at,events,files)
    validate_intervals(visits,effective_by,handoffs,appointments,arrivals,reworks,cases,events,exits)
    # FK checks are also run by the full backup validator. Reject orphans when
    # this validator is used independently as a user's focused diagnosis.
    if any(f['visit_id'] not in visits for f in facts) or any(c['visit_id'] not in visits for c in corrections) or any(r['correction_id'] not in {c['id'] for c in corrections} for r in reviews.values()):
        fail('存在孤立进出厂、纠正或复核来源')
    return {'verified_gate_visits':len(visits),'verified_gate_corrections':len(corrections),'verified_gate_handoffs':len(handoffs),'verified_cancelled_repair_exits':len(exits)}
