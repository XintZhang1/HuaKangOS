"""Attributable presales activity and actual service arrival/departure facts.

No task, booking, completed state or payment is treated as a physical visit.
The arrival cohort is evaluated at the requested local end date, never now.
"""
from collections import defaultdict
from datetime import timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select,or_
from sqlalchemy.orm import load_only
from .config import settings
from .db import today
from .models import Store
from .flow_models import Case, FlowEvent, FileAsset
from .service_intake_models import ServiceAppointment, ArrivalFact, ReworkRequest, RepairIntake, RepairVehicleBinding
from .inventory_report_common import bounded, as_of, route, table

READ_ROLES={'admin','manager','finance','auditor','sales','service','reception','customer_service'}
CONTACTS={'remind':'接待沟通并安排回访','intent':'记录购车需求','follow':'记录意向沟通'}
TRANSITIONS={'reserve':'转车辆预订','sales_quote_convert':'转车辆预订','close':'结束本次跟进','reopen':'重新开启跟进'}
RELEASES={1:'release',2:'release',3:'repair_v3_release',4:'repair_v4_release'}
DEFINITIONS=[
 '非维修登记安排不计进厂，转维修沿用同一原实际进厂而不重复计算。已独立批准的纠正按当前查询快照重算有效时间，原事实和提出记录另表保留；不是当年已封存账簿的改写。',
 '售前实际记录按沟通结果或购车需求的不可变事件及当地发生日统计；安排下一次回访不代表下一次已沟通，改派、任务完成和当前状态不增加次数。转预订、结束与重开另列，不是接待批次转化率。',
 '进厂只计实际到店凭据或原单返修现场核验；出厂只计未开单实际离场、维修客户实际接车。预约、转单、工位移出、完工和付款均不替代进出厂。另含有据非维修来访和取消维修后的独立实际离场；不是整车或物资库存变动。',
 '到店批次按所选期间的实际到店记录选择，离场只观察至期间末；未记录离场不表示车辆仍在厂内。旧工单没有到店来源时显示待核对，不反推到店时间或停留时长。',
 '上传原件及岗位确认提供可追溯的办理来源，不构成文件真实性认证；集团汇总隐藏VIN和沟通内容，原单、文件继续按各店授权访问。']


def _local(stamp):
    return stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone))


def build_visit_activity(db,user,start=None,end=None,case_id=None):
    if user.role not in READ_ROLES:raise HTTPException(403,'当前岗位不能查询售前跟进与维修进出厂统计')
    end=end or today();start=start or end.replace(day=1)
    if start>end:raise HTTPException(422,'开始日期不能晚于结束日期，请修改后重新查询')
    if end>today():raise HTTPException(422,'结束日期不能晚于今天，请修改后重新查询')
    if (end-start).days>365:raise HTTPException(422,'查询期间跨度不能超过一年，请缩小期间')
    from .flow_engine import case_query
    statement=case_query(user).where(Case.kind.in_(['lead','repair','service_intake']))
    if case_id:
        statement=statement.where(or_(Case.id==case_id,
            Case.id.in_(select(ServiceAppointment.case_id).where(ServiceAppointment.repair_case_id==case_id)),
            Case.id.in_(select(ServiceAppointment.repair_case_id).where(ServiceAppointment.case_id==case_id)),
            Case.id.in_(select(ReworkRequest.case_id).where(ReworkRequest.repair_case_id==case_id)),
            Case.id.in_(select(ReworkRequest.repair_case_id).where(ReworkRequest.case_id==case_id))))
    cases={c.id:c for c in bounded(db,Case,statement)}
    if case_id and case_id not in cases:raise HTTPException(404,'当前授权范围没有该接待、售前或维修原单')
    ids=list(cases);stores=dict(db.execute(select(Store.id,Store.name)).all())
    aggregate=bool(db.info.get('aggregate_scope') or getattr(user,'_aggregate_scope',False) or len([i for i in db.info.get('store_scope',()) if i])>1)
    events=bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.case_id.in_(ids),FlowEvent.action.in_(list(CONTACTS)+list(TRANSITIONS)+list(RELEASES.values())+['intake_leave','intake_rework_convert','create','assign','callback_intent'])).order_by(FlowEvent.occurred_at,FlowEvent.id))
    by_action=defaultdict(list)
    for e in events:by_action[e.case_id,e.action].append(e)
    issues=[];related={case_id} if case_id else set()
    def selected(*cids):return not case_id or case_id in cids
    def inside(stamp):return start<=_local(stamp).date()<=end
    def issue(cid,message,source=None):
        if cid in cases and (not case_id or cid in related):issues.append({'case_id':cid,'source_id':source,'message':message})
    def event_valid(e):
        if e.store_id!=cases[e.case_id].store_id:issue(e.case_id,'事件与原业务门店不一致',e.id);return False
        return True
    contact_rows=[];transition_rows=[]
    for e in events:
        c=cases[e.case_id]
        if c.kind!='lead' or not selected(c.id) or not inside(e.occurred_at):continue
        if e.action not in CONTACTS and e.action not in TRANSITIONS:continue
        if not event_valid(e):continue
        field='need' if e.action=='intent' else 'result' if e.action in CONTACTS else 'reason' if e.action in {'close','reopen'} else 'model'
        content=(e.detail or {}).get(field)
        if not isinstance(content,str) or not content.strip():issue(c.id,'售前事件缺少本次明确事实，不能按当前资料补记',e.id);continue
        item={'case_id':c.id,'store_id':c.store_id,'source_id':e.id,'date':_local(e.occurred_at).date().isoformat(),
              'time':_local(e.occurred_at).strftime('%Y-%m-%d %H:%M:%S'),'action':e.action,'label':(CONTACTS|TRANSITIONS)[e.action],
              'content':'集团汇总隐藏沟通内容' if aggregate else content}
        (contact_rows if e.action in CONTACTS else transition_rows).append(item)
    appointments={a.id:a for a in bounded(db,ServiceAppointment,select(ServiceAppointment).where(ServiceAppointment.case_id.in_(ids)))}
    arrivals=bounded(db,ArrivalFact,select(ArrivalFact).where(ArrivalFact.appointment_id.in_(appointments)))
    reworks={r.id:r for r in bounded(db,ReworkRequest,select(ReworkRequest).where(ReworkRequest.case_id.in_(ids)))}
    if case_id:
        related.update(a.case_id for a in appointments.values() if a.repair_case_id==case_id)
        related.update(r.case_id for r in reworks.values() if r.repair_case_id==case_id)
    contexts={r.case_id:r for r in bounded(db,RepairIntake,select(RepairIntake).where(RepairIntake.case_id.in_(ids)))}
    bindings={b.case_id:b for b in bounded(db,RepairVehicleBinding,select(RepairVehicleBinding).where(RepairVehicleBinding.case_id.in_(ids)))}
    proof_ids={a.evidence_id for a in arrivals}
    proof_ids.update((e.detail or {}).get('evidence_id') for e in events if e.action in {'intake_leave','intake_rework_convert','release'})
    proof_ids.update(c.data.get('release_evidence_id') for c in cases.values() if c.kind=='repair')
    files={f.id:f for f in bounded(db,FileAsset,select(FileAsset).options(load_only(FileAsset.id,FileAsset.case_id,FileAsset.store_id)).where(FileAsset.id.in_([i for i in proof_ids if type(i) is int])))}
    def proof(cid,fid):
        f=files.get(fid);return bool(f and f.case_id==cid and f.store_id==cases[cid].store_id)
    sessions=[];known_repair=set()
    def add_session(cid,rid,vin,stamp,source_id,source_kind,profile):
        rid=rid if rid in cases else None
        if not selected(cid,rid):return
        s={'case_id':cid,'repair_case_id':rid,'store_id':cases[cid].store_id,'vin':None if aggregate else vin,
           'arrived_at':stamp,'arrival_source_id':source_id,'arrival_source':source_kind,'profile':profile,'left_at':None,'departure_source_id':None,'departure_kind':None}
        if rid:
            if rid in known_repair:issue(cid,'同一维修工单关联多条到店来源，不能重复计算',source_id);return
            known_repair.add(rid)
        sessions.append(s)
    for a in arrivals:
        ap=appointments[a.appointment_id];cid=ap.case_id;rid=ap.repair_case_id
        if not selected(cid,rid):continue
        ctx=contexts.get(rid);binding=bindings.get(rid)
        valid=a.store_id==ap.store_id==cases[cid].store_id and a.customer_vehicle_id==ap.customer_vehicle_id and proof(cid,a.evidence_id)
        if rid in cases:valid=valid and cases[rid].store_id==ap.store_id and bool(ctx and ctx.appointment_id==ap.id and binding and binding.customer_vehicle_id==a.customer_vehicle_id and binding.vin==a.checked_vin)
        if not valid:issue(cid,'实际到店与本店原预约、凭据或维修车辆绑定不一致',a.id);continue
        add_session(cid,rid,a.checked_vin,a.occurred_at,a.id,'intake_arrivals',{'regular':'普通维修','wash':'洗车','quick':'快捷项目'}.get(ctx.profile if ctx else '', '预约到店' if ap.mode=='appointment' else '现场到店'))
    for r in reworks.values():
        cid=r.case_id;rid=r.repair_case_id;found=by_action[cid,'intake_rework_convert']
        if not found or not selected(cid,rid):continue
        ctx=contexts.get(rid);binding=bindings.get(rid);e=found[0];v=e.detail or {}
        if len(found)!=1 or not event_valid(e) or not proof(cid,v.get('evidence_id')) or rid not in cases or not ctx or ctx.rework_id!=r.id or not binding or binding.customer_vehicle_id!=r.customer_vehicle_id or binding.vin!=v.get('checked_vin'):
            issue(cid,'返修现场核验与原责任申请、凭据或维修绑定不一致',e.id);continue
        add_session(cid,rid,binding.vin,e.occurred_at,e.id,'flow_events','原单返修')
    departures={}
    for c in cases.values():
        if c.kind!='repair':continue
        found=by_action[c.id,RELEASES.get(c.flow_version,'__unknown__')]
        if not found:
            released=c.data.get('released_date')
            if isinstance(released,str) and start.isoformat()<=released<=end.isoformat():issue(c.id,'工单记载已接车，但缺少该版本唯一实际接车事件，不能补算出厂')
            continue
        e=found[0];fid=c.data.get('release_evidence_id') if c.flow_version in {3,4} else (e.detail or {}).get('evidence_id')
        if len(found)!=1 or not event_valid(e) or not proof(c.id,fid) or c.data.get('released_date')!=_local(e.occurred_at).date().isoformat():
            if inside(e.occurred_at):issue(c.id,'客户接车事件与原接车凭据或实际日期不一致',e.id)
            continue
        departures[c.id]=e
    for s in sessions:
        cid=s['case_id'];rid=s['repair_case_id'];leaves=by_action[cid,'intake_leave'];release=departures.get(rid)
        e=release or (leaves[0] if len(leaves)==1 else None)
        if leaves and (len(leaves)!=1 or rid or not proof(cid,(leaves[0].detail or {}).get('evidence_id')) or not event_valid(leaves[0])):
            issue(cid,'未开单离场与原到店或独立离场凭据冲突',leaves[0].id);e=None
        if e and e.occurred_at<s['arrived_at']:issue(cid,'实际离场时间早于到店，需核对原事实',e.id);e=None
        if e:s.update(left_at=e.occurred_at,departure_source_id=e.id,departure_kind='维修客户接车' if release else '未开单实际离场')
    from .gate_visit_reporting import extend_sessions
    gate_issues,gate_changes=extend_sessions(db,cases,sessions,aggregate,case_id)
    issues.extend(gate_issues)
    movements=[];cohort=[]
    for s in sessions:
        if inside(s['arrived_at']):
            movements.append({**s,'direction':'进厂','occurred_at':s['arrived_at'],'source_id':s['arrival_source_id'],'source_table':s['arrival_source'],'label':s['profile']})
            at_end=bool(s['left_at'] and _local(s['left_at']).date()<=end)
            cohort.append({**s,'left_by_end':at_end,'elapsed_minutes':int((s['left_at']-s['arrived_at']).total_seconds()//60) if at_end else None})
        if s['left_at'] and inside(s['left_at']):movements.append({**s,'direction':'出厂','occurred_at':s['left_at'],'source_id':s['departure_source_id'],'source_table':s.get('departure_source','flow_events'),'label':s['departure_kind']})
    for cid,e in departures.items():
        if cid in known_repair or not selected(cid) or not inside(e.occurred_at):continue
        binding=bindings.get(cid)
        movements.append({'case_id':cid,'repair_case_id':cid,'store_id':cases[cid].store_id,'vin':None if aggregate else binding.vin if binding else None,
                          'direction':'出厂','occurred_at':e.occurred_at,'source_id':e.id,'source_table':'flow_events','label':'客户接车；到店来源不足'})
        issue(cid,'已有实际接车凭据，但没有获权的可配对到店来源；不推算进厂或停留时长',e.id)
    for c in cases.values():
        if c.kind=='repair' and selected(c.id) and c.id not in known_repair and c.id not in departures and start<=c.business_date<=end:
            issue(c.id,'该维修工单没有获权的实际到店来源；建立、完工或付款日期不能替代进厂')
    movements.sort(key=lambda r:(r['occurred_at'],r['source_table'],r['source_id']))
    tables={};charts=[]
    def new(key,title,headers):tables[key]=table(title,headers);return tables[key]
    def put(t,values,cid=None,**extra):t['rows'].append({'values':values,**({'route':route(db,cid)} if cid else {}),**extra})
    lead=new('presales_activity','期间售前实际沟通与需求记录',['门店','售前原单','实际记录时间','本次动作','本次事实','原事件'])
    for r in contact_rows:put(lead,[stores.get(r['store_id'],''),cases[r['case_id']].number,r['time'],r['label'],r['content'],r['source_id']],r['case_id'],count=1,source_id=r['source_id'])
    transition=new('presales_transitions','期间售前转预订与结束重开',['门店','售前原单','实际事件时间','动作','原事件'])
    for r in transition_rows:put(transition,[stores.get(r['store_id'],''),cases[r['case_id']].number,r['time'],r['label'],r['source_id']],r['case_id'],count=1,source_id=r['source_id'])
    gates=new('service_gate_movements','期间实际进出厂原始行',['门店','接待或维修原单','关联维修单','实际时间','方向','实际事实','核对VIN','来源类型','来源编号'])
    for r in movements:put(gates,[stores.get(r['store_id'],''),cases[r['case_id']].number,cases[r['repair_case_id']].number if r.get('repair_case_id') in cases else '未开单或未获权',_local(r['occurred_at']).strftime('%Y-%m-%d %H:%M:%S'),r['direction'],r['label'],r['vin'] or ('集团隐藏' if aggregate else '来源不足'),{'intake_arrivals':'实际到店记录','gate_facts':'非维修原实际记录','gate_repair_exits':'取消维修独立离场'}.get(r['source_table'],'原业务事件'),r['source_id']],r.get('repair_case_id') or r['case_id'],count=1,direction=r['direction'],source_id=r['source_id'],source_table=r['source_table'])
    visits=new('service_visit_cohort','本期间到店批次截至期间末的离场记录',['门店','接待原单','关联维修单','实际到店时间','截至期间末离场时间','事实状态','已闭合记录时长（分钟）'])
    for s in cohort:
        state='已有实际离场记录' if s['left_by_end'] else '尚无实际离场记录，不能据此认定仍在厂'
        put(visits,[stores.get(s['store_id'],''),cases[s['case_id']].number,cases[s['repair_case_id']].number if s['repair_case_id'] else '未开单或未获权',_local(s['arrived_at']).strftime('%Y-%m-%d %H:%M:%S'),_local(s['left_at']).strftime('%Y-%m-%d %H:%M:%S') if s['left_by_end'] else '无记录',state,s['elapsed_minutes'] if s['elapsed_minutes'] is not None else '未知'],s.get('repair_case_id') or s['case_id'],count=1,closed=s['left_by_end'])
    changes=new('gate_corrections','原进出厂有据纠正（期间提出）',['门店','原接待','纠正编号','纠正范围','处理状态','核对后实际时间'])
    for change in gate_changes:
        if inside(change['requested_at']):
            put(changes,[stores.get(cases[change['case_id']].store_id,''),cases[change['case_id']].number,change['id'],{'arrive_time':'原进厂时间','leave_time':'原离场时间','void_visit':'撤销错误登记'}[change['kind']],{'pending':'待独立复核','approved':'已独立批准','rejected':'未通过','cancelled':'原申请撤回'}[change['status']],_local(change['actual_at']).strftime('%Y-%m-%d %H:%M:%S') if change['actual_at'] else '不新增实际时间'],change['case_id'])
    from .presales_stage_analytics import build as build_stages
    stages=build_stages(cases,events,start,end,aggregate)
    tables.update(stages['tables']);issues.extend(stages['issues'])
    gap=new('visit_source_issues','接待与跟进来源待核对',['原单','原来源编号','需要核对的事实'])
    for r in issues:put(gap,[cases[r['case_id']].number,r['source_id'] or '缺失',r['message']],r['case_id'])
    def chart(key,title,counts,section,caption):
        labels=sorted(counts);charts.append({'id':key,'title':title,'section':section,'type':'bar','unit':'count','labels':labels,'series':[{'name':'实际记录次数','values':[counts[k] for k in labels]}],'table':key,'caption':caption})
    contact_counts=defaultdict(int)
    for r in contact_rows:contact_counts[r['date']]+=1
    chart('presales_activity','期间售前实际记录次数',contact_counts,'sales','同一售前单可有多次真实记录；不按员工排名，不将未来计划算成沟通。')
    move_counts=defaultdict(int)
    for r in movements:move_counts[_local(r['occurred_at']).date().isoformat()+' '+r['direction']]+=1
    chart('service_gate_movements','期间实际进出厂次数',move_counts,'repair','进、出分别按实际发生日；不能相减后当作当前在厂数量。')
    charts.extend(stages['charts'])
    return {'stage_observed_until':stages['observed_until'],'date_from':start.isoformat(),'date_to':end.isoformat(),'as_of':as_of(),'complete':not issues,'definitions':DEFINITIONS+stages['definitions'],'tables':tables,'charts':charts,
            'metrics':{**stages['metrics'],'presales_contact_events':len(contact_rows),'presales_contact_cases':len({r['case_id'] for r in contact_rows}),
                       'service_actual_arrivals':sum(r['direction']=='进厂' for r in movements),'service_actual_departures':sum(r['direction']=='出厂' for r in movements),
                       'service_arrival_cohort_without_departure':sum(not s['left_by_end'] for s in cohort),'visit_source_issues':len(issues)},
            'options':{'cases':[{'id':c.id,'label':c.number} for c in cases.values()]},'filters':{'case_id':case_id}}
