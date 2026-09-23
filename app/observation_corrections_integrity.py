"""Read-only SQLite restore checks, including effective historical reminder sources.

Run after the existing complete file/insurance/customer validators; this validates
the domain links, not file malware scanning or a database administrator signature.
"""
import hashlib,json
from datetime import datetime,timezone,date,timedelta

TABLES=('observation_corrections','observation_correction_events','observation_correction_effects','observation_insurance_invalidations',
    'observation_reminder_bases','observation_reminder_invalidations','observation_reminder_replacements','observation_correction_receipts')

def _hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
def _json(v):return json.loads(v) if isinstance(v,str) else v
def _time(v):
    t=datetime.fromisoformat(str(v).replace('Z','+00:00'))
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)
def _assert(ok,message):
    if not ok:raise ValueError('日期里程纠正恢复校验：'+message)

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(TABLES)&names:
        return {'corrections':0,'effects':0,'insurance_invalidations':0,'reminder_bases':0}
    _assert(set(TABLES)<=names,'本域表不完整')
    needed=TABLES+('flow_cases','flow_files','flow_events','flow_tasks','care_customer_vehicles','care_vehicle_observations','care_cases','care_records',
        'insurance_orders','insurance_quotes','insurance_submissions','insurance_results','insurance_terminations','insurance_termination_reviews','insurance_termination_consents','insurance_termination_applications','insurance_termination_cancellations')
    rows={}
    for name in needed:
        # Never load original BLOB bytes in a domain validator.
        sql='SELECT id,store_id,case_id,created_by,generated FROM flow_files' if name=='flow_files' else 'SELECT * FROM '+name
        cursor=connection.execute(sql);columns=[c[0] for c in cursor.description]
        rows[name]=[dict(zip(columns,r)) for r in cursor]
    def all_(table,**where):return [r for r in rows[table] if all(r.get(k)==v for k,v in where.items())]
    def one(table,key,field='id'):
        found=all_(table,**{field:key});_assert(len(found)==1,f'{table} 原记录缺失或重复');return found[0]
    def same(*rs):_assert(len({r['store_id'] for r in rs})==1,'关联来源跨门店')
    def proof(file_id,case):
        f=one('flow_files',file_id);same(f,case);_assert(f['case_id']==case['id'] and not f['generated'],'凭据不是本单原件');return f
    apps={r['case_id']:r for r in rows[TABLES[0]]};effects={r['id']:r for r in rows[TABLES[2]]}
    invalid_by_obs={r['observation_id']:r for r in rows[TABLES[3]]}
    def projection(oid,effect_id=None,as_of=None):
        o=one('care_vehicle_observations',oid);value={k:o[k] for k in ('id','vehicle_id','kind','observed_date','odometer_km','valid_until','source_reference','evidence_id')}
        effect=effects.get(effect_id) if effect_id else None;request=apps.get(effect['case_id']) if effect else None
        if effect:
            _assert(effect['observation_id']==oid and request,'有效版本未指向原观察')
            if as_of:_assert(_time(effect['created_at'])<=_time(as_of),'提醒使用未来纠正版本')
            if request['operation']=='replace':value.update(_json(request['proposed']))
        issued=all_('insurance_results',observation_id=oid);_assert(len(issued)<=1,'原观察重复出保来源')
        ended=invalid_by_obs.get(oid)
        if ended and as_of and _time(ended['created_at'])>_time(as_of):ended=None
        value.update(effect_id=effect_id,active=not bool(ended) and not(request and request['operation']=='retract'),source_type='insurance_result' if issued else 'manual_observation',
            source_case_id=issued[0]['case_id'] if issued else None,odometer_measured=not bool(issued),insurance_invalidation_id=ended['id'] if ended else None)
        if issued:value['odometer_km']=None
        value['digest']=_hash(value);return value
    for request in apps.values():
        case=one('flow_cases',request['case_id']);v=one('care_customer_vehicles',request['vehicle_id']);o=one('care_vehicle_observations',request['observation_id']);same(request,case,v,o)
        _assert(case['kind']=='observation_correction' and case['flow_version']==2 and case['customer_id']==v['customer_id'] and o['vehicle_id']==v['id'],'申请客户车辆或专用版本不符')
        snapshot=_json(request['original_snapshot']);expected=projection(o['id'],snapshot.get('effect_id'),case['created_at'])
        _assert(snapshot==expected and request['base_digest']==snapshot['digest'],'原观察快照或有效版本被改写')
        _assert(snapshot['source_type']=='manual_observation','实际保险原单不能被人工观察纠正')
        proposed=_json(request['proposed']);_assert(request['operation'] in {'replace','retract'},'未知替代方式')
        if request['operation']=='replace':
            _assert(set(proposed)=={'observed_date','odometer_km','valid_until','source_reference'},'替代字段不完整或改变种类')
            _assert(type(proposed['odometer_km']) is int and 0<=proposed['odometer_km']<=3_000_000,'替代公里数无效')
            _assert(date(2000,1,1)<=date.fromisoformat(proposed['observed_date'])<=_time(case['created_at']).date()+timedelta(days=1),'替代实际日期无效')
            if o['kind'] in {'insurance','warranty'}:_assert(proposed['valid_until'] and proposed['observed_date']<=proposed['valid_until']<='2100-01-01','期限无效')
            else:_assert(proposed['valid_until'] is None,'非期限观察伪造保期')
        else:_assert(not proposed and snapshot['active'],'无效撤销或替代值')
        events=sorted(all_(TABLES[1],case_id=case['id']),key=lambda r:r['id']);actions=[r['action'] for r in events]
        valid={'pending':['create'],'approval':['create','submit'],'completed':['create','submit','approve'],'rejected':['create','submit','reject']}
        _assert(actions in (['create','cancel'],['create','submit','cancel']) if case['state']=='cancelled' else actions==valid.get(case['state']),'状态和不可变事件链不一致')
        frozen=_hash([request['vehicle_id'],request['observation_id'],request['base_digest'],request['operation'],proposed,request['reason']])
        for event in events:
            same(event,case);matches=all_('flow_events',case_id=case['id'],action='observation_'+event['action']);_assert(len(matches)==1,'申请事件未关联唯一流程事实')
            log=matches[0];same(log,case);detail=_json(log['detail'])
            _assert(log['actor_id']==event['actor_id'] and detail.get('correction_digest')==frozen and detail.get('observation_correction_id')==case['id'],'方案或经办流程摘要不符')
            if event['action'] in {'submit','approve','reject'}:proof(event['evidence_id'],case)
            else:_assert(event['evidence_id'] is None,'创建或撤回事件凭据异常')
            if event['action'] in {'approve','reject'}:_assert(event['actor_id']!=case['created_by'] and detail.get('actor_role') in {'admin','manager'},'缺少独立主管复核')
        found=all_(TABLES[2],case_id=case['id']);_assert(len(found)==(1 if case['state']=='completed' else 0),'生效事实与批准状态不符')
        for effect in found:
            same(effect,case);review=events[-1]
            _assert(effect['review_event_id']==review['id'] and effect['actor_id']==review['actor_id'] and effect['observation_id']==o['id'] and effect['parent_effect_id']==snapshot['effect_id'] and effect['parent_token']==str(snapshot['effect_id'] or 0),'纠正链或原批准不符')
    heads=set()
    for effect in effects.values():
        key=(effect['observation_id'],effect['parent_token']);_assert(key not in heads,'同一有效版本被重复生效');heads.add(key)
        if effect['parent_effect_id']:
            parent=effects.get(effect['parent_effect_id']);_assert(parent and parent['id']<effect['id'] and parent['observation_id']==effect['observation_id'],'纠正链倒置')
    for inv in rows[TABLES[3]]:
        case=one('flow_cases',inv['source_case_id']);order=one('insurance_orders',case['id']);v=one('care_customer_vehicles',inv['vehicle_id']);o=one('care_vehicle_observations',inv['observation_id']);result=one('insurance_results',inv['result_id']);plan=one('insurance_terminations',inv['plan_id']);application=one('insurance_termination_applications',inv['application_id']);quote=one('insurance_quotes',plan['quote_id']);submission=one('insurance_submissions',result['submission_id'])
        same(inv,case,order,v,o,result,plan,application,quote,submission)
        review=one('insurance_termination_reviews',plan['id'],'plan_id');consent=one('insurance_termination_consents',plan['id'],'plan_id');same(review,consent,case)
        _assert(case['kind']=='insurance' and case['flow_version']==3 and order['customer_vehicle_id']==v['id'] and order['vin']==v['vin'] and case['customer_id']==v['customer_id'] and o['vehicle_id']==v['id'],'保险失效来源客户VIN不符')
        _assert(plan['case_id']==quote['case_id']==result['case_id']==case['id'] and submission['quote_id']==quote['id'] and result['outcome']=='issued' and result['observation_id']==o['id'],'缺少同原报价实际出保')
        _assert(o['kind']=='insurance' and o['valid_until']==quote['end_date'] and o['observed_date']==result['business_date'] and o['evidence_id']==result['evidence_id'] and o['actor_id']==result['actor_id'],'原保期登记事实被改写')
        _assert(application['plan_id']==plan['id'] and inv['evidence_id']==application['evidence_id'] and plan['external_result']=='terminated' and review['decision']=='approved' and review['actor_id']!=plan['actor_id'] and consent['digest']==plan['digest'] and not all_('insurance_termination_cancellations',plan_id=plan['id']),'保险失效不能由申请、退款或不完整审批推断')
        payload={k:plan[k] for k in ('quote_id','evidence_id','reason','retained_cents','external_result')};payload['returns']=_json(plan['returns'])
        # Existing workflow digest serializes {action,values} with its own convention.
        _assert(_hash({'operation':'insurance_termination','payload':payload})==plan['digest'],'保险终止摘要不符')
        for fact in (result,plan,review,consent,application):proof(fact['evidence_id'],case)
    for basis in rows[TABLES[4]]:
        case=one('flow_cases',basis['case_id']);care=one('care_cases',basis['case_id'],'case_id');v=one('care_customer_vehicles',basis['vehicle_id']);same(basis,case,care,v)
        snap=_json(basis['snapshot']);base=projection(basis['baseline_id'],basis['baseline_effect_id'],case['created_at']);current=projection(basis['current_id'],basis['current_effect_id'],case['created_at']) if basis['current_id'] else None
        _assert(snap['baseline']==base and snap['current']==current and base['active'] and (not current or current['active'] and current['odometer_measured']),'提醒用了失效、未来或未实测的里程来源')
        _assert(base['vehicle_id']==care['vehicle_id']==v['id'] and (not current or current['vehicle_id']==v['id']) and care['baseline_observation_id']==base['id'] and care['rule_id']==snap['rule_id'] and care['rule_version']==snap['rule_version'],'提醒来源或规则版本不符')
        cycle=f"{case['store_id']}:{v['id']}:{care['subtype']}:observation:{base['id']}";_assert(basis['cycle_key']==cycle,'提醒实际周期伪造')
        logs=all_('flow_events',case_id=case['id'],action='observation_reminder_basis');_assert(len(logs)==1 and _json(logs[0]['detail'])=={'basis_digest':_hash(snap),'cycle_key':cycle},'冻结提醒来源摘要不符')
        rule=snap['rule'];day=date.fromisoformat(snap['triggered_on']);_assert(rule['kind']==care['subtype'],'规则种类被替换')
        if rule['kind'] in {'renewal','warranty'}:due=base['valid_until'] and day>=date.fromisoformat(base['valid_until'])-timedelta(days=rule['lead_days'])
        else:due=(rule['interval_days'] and day>=date.fromisoformat(base['observed_date'])+timedelta(days=rule['interval_days']-rule['lead_days'])) or (rule['interval_km'] and current and base['odometer_km'] is not None and current['odometer_km']>=base['odometer_km']+rule['interval_km']-rule['lead_km'])
        _assert(due,'当时基准尚未触发提醒')
    for inv in rows[TABLES[5]]:
        case=one('flow_cases',inv['case_id']);care=one('care_cases',inv['case_id'],'case_id');o=one('care_vehicle_observations',inv['observation_id']);same(inv,case,care,o)
        _assert(care['vehicle_id']==o['vehicle_id'] and care['rule_id'] is not None,'非本车规则提醒被失效')
        if inv['correction_case_id']:
            source=apps.get(inv['correction_case_id']);_assert(source and source['observation_id']==o['id'] and all_(TABLES[2],case_id=source['case_id']),'失效没有原纠正批准');token='correction:'+str(source['case_id'])
        else:
            source=one(TABLES[3],inv['insurance_invalidation_id']);_assert(source['observation_id']==o['id'],'失效原保期不符');token='insurance:'+str(source['id'])
        _assert(inv['source_key']==token,'失效来源标识不符')
        logs=[r for r in all_('care_records',case_id=case['id']) if _json(r['details']).get('basis_invalidation')==token]
        _assert(len(logs)==1 and logs[0]['actor_id']==inv['actor_id'] and _json(logs[0]['details']).get('previous_state')==inv['previous_state'] and _json(logs[0]['details']).get('closed_open_task')==bool(inv['closed_open_task']),'旧提醒处理历史不符')
        if inv['closed_open_task']:
            _assert(inv['previous_state'] in {'pending','working'} and case['state']=='cancelled' and logs[0]['action']=='cancel','失效不能覆盖已完成事实')
            tasks=all_('flow_tasks',case_id=case['id'],key='care_handle');_assert(len(tasks)==1 and tasks[0]['status']=='cancelled','失效旧待办仍可办理')
    for replacement in rows[TABLES[6]]:
        old=one('care_cases',replacement['previous_case_id'],'case_id');new=one('care_cases',replacement['replacement_case_id'],'case_id');case=one('flow_cases',old['case_id']);basis=one(TABLES[4],new['case_id'],'case_id');same(replacement,old,new,case,basis)
        _assert(old['vehicle_id']==new['vehicle_id'] and old['subtype']==new['subtype'] and old['case_id']<new['case_id'] and case['state']=='cancelled' and any(r['closed_open_task'] for r in all_(TABLES[5],case_id=old['case_id'])),'替代不能重发已完成或人工取消的周期')
    for receipt in rows[TABLES[7]]:
        result=_json(receipt['result']);_assert(isinstance(result,dict) and len(receipt['digest'])==64,'幂等回执不完整')
        if result.get('case'):
            snapshot=result['case'];request=apps.get(snapshot['id']);_assert(request is not None,'回执指向不存在的纠正申请');same(receipt,request)
            _assert(snapshot['vehicle_id']==request['vehicle_id'] and snapshot['observation_id']==request['observation_id'] and snapshot['original']==_json(request['original_snapshot']) and snapshot['proposed']==_json(request['proposed']) and snapshot['operation']==request['operation'] and snapshot['reason']==request['reason'],'回执原观察／替代值被替换')
            ids=[e['id'] for e in snapshot['events']];events=sorted(all_(TABLES[1],case_id=request['case_id']),key=lambda r:r['id']);_assert(ids and ids==[e['id'] for e in events[:len(ids)]],'回执事件不是该申请的历史前缀')
            last=events[len(ids)-1];_assert(last['actor_id']==receipt['actor_id'] and snapshot['state']=={'create':'pending','submit':'approval','approve':'completed','reject':'rejected','cancel':'cancelled'}[last['action']],'回执经办或当时状态不符')
        elif 'created' in result:
            for item in result['created']:
                basis=one(TABLES[4],item['case_id'],'case_id');same(receipt,basis)
        else:_assert(type(result.get('invalidated')) is int and result['invalidated']>=0,'未知幂等回执内容')
    return {'corrections':len(apps),'effects':len(effects),'insurance_invalidations':len(rows[TABLES[3]]),'reminder_bases':len(rows[TABLES[4]])}
