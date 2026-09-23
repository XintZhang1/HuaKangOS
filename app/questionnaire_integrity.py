"""Read-only restoration replay against original care/flow/audit source facts.

Digests detect internal mismatch, not an administrator rewriting all original
sources together. Historical absence of the complete domain is a legacy schema;
a partially present domain or missing bindings in an upgraded schema is damage.
"""
import json
from datetime import datetime,timezone
from .questionnaire_schema import questions,answers,digest,LEGACY_QUESTIONS,LEGACY_NAME

TABLES=('care_questionnaire_policies','care_questionnaire_versions','care_questionnaire_reviews',
        'care_questionnaire_bindings','care_questionnaire_responses')


def _json(value):return json.loads(value) if isinstance(value,str) else value

def _time(value):
    stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def validate(connection):
    def require(ok,message):
        if not ok:raise ValueError('问卷版本恢复校验：'+message)
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    empty={'questionnaire_versions':0,'questionnaire_bindings':0,'questionnaire_responses':0}
    if not set(TABLES)&names:return empty
    require(set(TABLES)<=names,'新域表不完整')
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name)
        columns=[x[0] for x in cursor.description]
        return [dict(zip(columns,row)) for row in cursor]
    policies=rows(TABLES[0]);versions=rows(TABLES[1]);reviews=rows(TABLES[2]);bindings=rows(TABLES[3]);responses=rows(TABLES[4])
    cases={r['id']:r for r in rows('flow_cases')};cares={r['case_id']:r for r in rows('care_cases')}
    records=rows('care_records');events=rows('flow_events');audits=rows('audit_logs')
    byversion={r['id']:r for r in versions};bybinding={r['id']:r for r in bindings}
    byreview={r['version_id']:r for r in reviews};byresponse={r['binding_id']:r for r in responses}
    require(len(byreview)==len(reviews) and len(byresponse)==len(responses),'复核或回答来源重复')
    def same(*rs):require(len({r['store_id'] for r in rs})==1,'来源跨门店')
    def audit(row,action,actor,expected):
        found=[a for a in audits if a['action']==action and a['entity_type']=='questionnaire_version' and a['entity_id']==row['id']]
        require(len(found)==1,'发布操作缺少唯一审计事实');a=found[0];same(row,a)
        require(a['actor_id']==actor and _json(a['after_data'])==expected,'版本、摘要或经办人与原审计不一致')
    for row in versions:
        try:normalized=questions(_json(row['questions']))
        except (ValueError,TypeError) as exc:raise ValueError('问卷版本恢复校验：题目结构损坏') from exc
        require(normalized==_json(row['questions']) and digest(normalized)==row['digest'],'题目快照或摘要不一致')
        require(type(row['number']) is int and row['number']>=2 and 2<=len(row['name'])<=120 and 3<=len(row['reason'])<=1000,'版本编号、名称或理由无效')
        audit(row,'questionnaire_propose',row['proposed_by'],{'number':row['number'],'digest':row['digest']})
    policy_by_store={r['store_id']:r for r in policies}
    require(len(policy_by_store)==len(policies),'每店发布目录不唯一')
    for sid,head in policy_by_store.items():
        local=sorted([v for v in versions if v['store_id']==sid],key=lambda v:v['number'])
        require([v['number'] for v in local]==list(range(2,2+len(local))) and head['next_number']==2+len(local),'发布编号不是连续原版本')
        active=None;number=1;last_time=None
        local_reviews=sorted([r for r in reviews if r['store_id']==sid],key=lambda r:r['id'])
        for review in local_reviews:
            version=byversion.get(review['version_id']);require(version is not None,'原题版本缺失');same(head,version,review)
            require(review['actor_id']!=version['proposed_by'] and review['actor_role'] in {'admin','manager'},'问卷没有独立主管复核')
            require(review['schema_digest']==version['digest'] and review['previous_version_id']==active,'复核未绑定原题或发布链断裂')
            require(_time(review['created_at'])>=_time(version['created_at']) and (last_time is None or _time(review['created_at'])>=last_time),'复核时间倒置')
            require(review['decision'] in {'approve','reject'},'未知复核决定')
            audit(version,'questionnaire_'+review['decision'],review['actor_id'],{'number':version['number'],'digest':version['digest'],'review_id':review['id']})
            if review['decision']=='approve':
                require(version['number']>number,'早期问卷被重新激活');active=version['id'];number=version['number']
            last_time=_time(review['created_at'])
        require(head['active_version_id']==active,'当前题目不是最后批准版本')
        require(head['version']==1+len(local)+len(local_reviews),'目录版本与原提出/复核次数不一致')
    require(all(r['store_id'] in policy_by_store for r in versions+reviews+bindings),'版本或发放没有本店目录')
    boundcases={b['case_id'] for b in bindings}
    require(len(boundcases)==len(bindings) and boundcases=={c['case_id'] for c in cares.values() if c['subtype']=='questionnaire'},'原问卷缺失或重复题目绑定')
    for fact in bindings:
        case=cases.get(fact['case_id']);care=cares.get(fact['case_id'])
        require(case and care and case['kind']=='customer_care' and care['subtype']=='questionnaire','发放不是原客户问卷');same(fact,case,care)
        data=_json(case['data']) or {};schema=_json(fact['questions'])
        require(fact['origin'] in {'runtime','migration'},'未知发放来源')
        if fact['version_id'] is None:
            require(fact['number']==1 and fact['name']==LEGACY_NAME and schema==LEGACY_QUESTIONS,'原v1题目被更换')
        else:
            version=byversion.get(fact['version_id']);require(version is not None,'发放的原版本不存在');same(fact,version)
            approved=byreview.get(version['id']);require(approved and approved['decision']=='approve','发放使用未批准题目')
            require(fact['number']==version['number'] and fact['name']==version['name'] and schema==_json(version['questions']),'发放快照没有锁定原题')
        require(digest(schema)==fact['schema_digest'] and data.get('questionnaire_version',1)==fact['number'],'问卷当前标识和原发放不一致')
        require(_time(case['created_at'])<=_time(fact['issued_at'])<=_time(fact['created_at']),'原发放时间不在登记范围内')
        if fact['origin']=='migration':
            require(fact['version_id'] is None and _time(fact['issued_at'])==_time(case['created_at']) and 'questionnaire_binding_id' not in data and 'questionnaire_schema_digest' not in data,'迁移不能将旧问卷改为新题或伪装新发放')
        else:
            prior=[r for r in reviews if r['store_id']==fact['store_id'] and r['decision']=='approve' and _time(r['created_at'])<=_time(fact['issued_at'])]
            active=max(prior,key=lambda r:r['id'])['version_id'] if prior else None
            require(fact['version_id']==active,'发放未按当时批准版本，或套用了未来题目')
            expected={'questionnaire_binding_id':fact['id'],'questionnaire_version':fact['number'],'questionnaire_schema_digest':fact['schema_digest']}
            require(all(data.get(k)==v for k,v in expected.items()),'原单发放标识被替换')
            originals=[r for r in records if r['case_id']==case['id'] and r['action']=='create']
            create_events=[e for e in events if e['case_id']==case['id'] and e['action']=='care_create']
            require(len(originals)==len(create_events)==1,'缺少原发放记录/流程事件')
            for source,field in [(originals[0],'details'),(create_events[0],'detail')]:
                same(source,fact);detail=_json(source[field]);require(all(detail.get(k)==v for k,v in expected.items()),'原发放事件未绑定题目摘要')
        closed=[r for r in records if r['case_id']==case['id'] and r['action']=='close']
        response=byresponse.get(fact['id'])
        require(len(closed)==(1 if case['state']=='completed' else 0),'结案状态和原结案事实不一致')
        require(bool(response)==bool(closed),'原结案和回答绑定不完整')
        if response:
            record=closed[0];same(response,record,fact);detail=_json(record['details']) or {}
            require(response['record_id']==record['id'] and response['actor_id']==record['actor_id'],'回答没有关联原经办结案')
            require(detail.get('result')==care['result'],'问卷结果被改写')
            value=_json(response['answers'])
            try:normalized=answers(schema,value,completed=care['result']=='resolved')
            except (ValueError,TypeError) as exc:raise ValueError('问卷版本恢复校验：原题回答缺失或类型不符') from exc
            require(normalized==value,'回答没有保持原题类型')
            if response['origin']=='migration':
                require(fact['origin']=='migration','新发放不能伪装为旧回答迁移')
                expected={key:detail[key] for key in ('satisfaction','recommend') if detail.get(key) is not None}
            else:
                require(response['origin']=='runtime','未知回答来源')
                require(detail.get('questionnaire_binding_id')==fact['id'] and detail.get('questionnaire_version')==fact['number'] and detail.get('questionnaire_schema_digest')==fact['schema_digest'],'回答未指向原题版本')
                expected=detail.get('answers')
                close_events=[e for e in events if e['case_id']==case['id'] and e['action']=='care_close']
                require(len(close_events)==1,'回答没有唯一原流程结案');event=close_events[0];same(event,fact)
                event_details=_json(event['detail']);require(event['actor_id']==record['actor_id'] and event_details=={'action':'close',**detail},'结案事件和回答记录不一致')
            require(expected==value,'回答与原结案内容不一致')
            require(_time(record['created_at'])>=_time(fact['issued_at']) and _time(response['created_at'])>=_time(record['created_at']),'回答时间早于原发放或结案')
            require(digest({'binding_id':fact['id'],'record_id':record['id'],'schema_digest':fact['schema_digest'],'answers':value})==response['digest'],'回答摘要不符')
    require(all(r['binding_id'] in bybinding for r in responses),'有回答没有原发放')
    return {'questionnaire_versions':len(versions),'questionnaire_bindings':len(bindings),'questionnaire_responses':len(responses)}
