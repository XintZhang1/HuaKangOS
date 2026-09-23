"""Same-source questionnaire tables and distribution charts, grouped by issued schema."""
from collections import defaultdict
from datetime import timezone
import re
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from .config import settings
from .db import today
from .flow_models import Case
from .customer_service_models import CareCase,CareRecord
from .questionnaire_models import QuestionnaireBinding as Binding,QuestionnaireResponse as Response
from .inventory_report_common import bounded
from .questionnaire_schema import KEY


def select_table(data,table_key,version_number=None,schema_digest=None,question_key=None):
    """Narrow the already authorized report, never query a supplied schema directly."""
    if table_key not in data['tables']:raise HTTPException(404,'问卷统计没有该表')
    table=data['tables'][table_key]
    supplied=(version_number,schema_digest,question_key)
    if all(value is None for value in supplied):return table
    if any(value is None or value=='' for value in supplied):
        raise HTTPException(422,'单题筛选须同时填写问卷版本、原题摘要和题目编号')
    if not re.fullmatch(r'[1-9][0-9]{0,9}',version_number):
        raise HTTPException(422,'问卷版本须为有效的正整数')
    if not re.fullmatch(r'[a-f0-9]{64}',schema_digest):
        raise HTTPException(422,'原题摘要须为完整的64位小写摘要')
    if not KEY.fullmatch(question_key):raise HTTPException(422,'题目编号须为有效的小写英文编号')
    if table_key not in {'questionnaire_distribution','questionnaire_answers'}:
        raise HTTPException(422,'单题筛选仅用于回答分布或原题答案明细')
    filters={'version_number':int(version_number),'schema_digest':schema_digest,'question_key':question_key}
    return {**table,'rows':[row for row in table['rows'] if all(row.get(key)==value for key,value in filters.items())]}


def report(db,user,start=None,end=None):
    from .customer_service import authority,can_read_case,RESULTS
    from .flow_engine import case_query
    end=end or today();start=start or end.replace(day=1)
    if start>end or end>today() or (end-start).days>365:raise HTTPException(422,'查询须为不晚于今天且跨度不超过一年的有效期间')
    with authority(db,user):
        # The native care relation/owner rules remain authoritative; the report
        # cannot grant access to other employees' original customer records.
        candidates=bounded(db,Case,case_query(user).where(Case.kind=='customer_care'))
        cases={r.id:r for r in candidates if can_read_case(db,user,r)}
        bindings=bounded(db,Binding,select(Binding).where(Binding.case_id.in_(cases)))
        responses={r.binding_id:r for r in bounded(db,Response,select(Response).where(Response.binding_id.in_([b.id for b in bindings])))}
        records={r.id:r for r in bounded(db,CareRecord,select(CareRecord).where(CareRecord.id.in_([r.record_id for r in responses.values()])))}
        def local(stamp):return stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone))
        def selected(stamp):return start<=local(stamp).date()<=end
        tables={};charts=[];totals=defaultdict(lambda:{'count':0,'missing':0,'choices':defaultdict(int),'required':False})
        tables['questionnaire_issued']={'title':'期间实际发放的原题版本','headers':['原单','版本','名称','发放时间','来源'],'rows':[]}
        tables['questionnaire_answers']={'title':'期间实际结案的原题答案','headers':['原单','版本','结案日期','实际结果','题目编号','原题','回答状态','原回答'],'rows':[]}
        issued=closed=0
        for binding in bindings:
            case=cases[binding.case_id];route={'type':'case','id':case.id}
            if selected(binding.issued_at):
                issued+=1;tables['questionnaire_issued']['rows'].append({'values':[case.number,binding.number,binding.name,local(binding.issued_at).strftime('%Y-%m-%d %H:%M:%S'),'原版本迁移' if binding.origin=='migration' else '实际发放'],'route':route})
            response=responses.get(binding.id);record=records.get(response.record_id) if response else None
            if not record or not selected(record.created_at):continue
            if record.case_id!=case.id or response.store_id!=case.store_id or record.store_id!=case.store_id:raise HTTPException(409,'问卷来源关系不完整，请核对后统计')
            closed+=1;result=(record.details or {}).get('result');answered=response.answers
            for question in binding.questions:
                key=question['key'];present=key in answered;value=answered.get(key)
                rendered='未回答' if not present else ('是' if value else '否') if question['kind']=='boolean' else next(o['label'] for o in question['choices'] if o['key']==value) if question['kind']=='choice' else str(value)
                tables['questionnaire_answers']['rows'].append({'values':[case.number,binding.number,local(record.created_at).date().isoformat(),RESULTS.get(result,result or '来源待核对'),key,question['label'],'已回答' if present else '未回答',rendered],'route':route,'binding_id':binding.id,'record_id':record.id,'version_number':binding.number,'schema_digest':binding.schema_digest,'question_key':key,'answered':present,'answer':value})
                token=(binding.number,binding.schema_digest,key,question['label'],question['kind'])
                t=totals[token];t['count']+=1;t['required']=question['required']
                if not present:t['missing']+=1
                elif question['kind']!='text':t['choices'][rendered]+=1
        tables['questionnaire_distribution']={'title':'按原题版本分开的回答分布','headers':['版本','原题摘要','题目编号','原题','回答','记录数'],'rows':[]}
        for token,counts in sorted(totals.items()):
            number,hash_,key,label,kind=token
            values=dict(counts['choices'])
            if kind=='text':values={'有文字回答':counts['count']-counts['missing']}
            values['未回答']=counts['missing']
            labels=list(values);numbers=[values[k] for k in labels]
            filters={'version_number':number,'schema_digest':hash_,'question_key':key}
            for choice,count in values.items():tables['questionnaire_distribution']['rows'].append({'values':[number,hash_,key,label,choice,count],'route':None,'count':count,**filters})
            charts.append({'id':'questionnaire_'+str(number)+'_'+key,'title':'v'+str(number)+' · '+label,'type':'bar','unit':'count','labels':labels,'series':[{'name':'实际结案回答数','values':numbers}],'table':'questionnaire_distribution','table_filters':filters,'caption':'按发放时原题及期间结案记录统计；未回答单列，不当作否或0。不同题目版本不混算。'})
        return {'date_from':start.isoformat(),'date_to':end.isoformat(),'tables':tables,'charts':charts,
            'metrics':{'questionnaires_issued':issued,'questionnaires_closed':closed},
            'definitions':['发放按原绑定时间，回答按原结案时间；两个集合不是同一批次，不能相除当回收率。',
                '保留当前获权原客户服务范围，不以统计接口扩大客户或跨店权限。文字答复仅在原表展示，不自动分析或外发。',
                '否、0与未回答分别记录。不同发放版本不自动合并题意，即使题目编号相同。']}
