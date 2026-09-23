"""Old and detailed callbacks share one task cohort; restricted readers get counts."""
from collections import Counter
from sqlalchemy import select,func
from fastapi import HTTPException
from .flow_models import Case
from .customer_service_models import CareCase
from .flow_specs import STATES
from .customer_service import STATUS,RESULTS,LABELS

CALLBACKS={'sales_callback','repair_callback'}
HEADERS=['业务单号','门店','回访事项','计划日期','当前状态','结果','数量']
DEFINITION='客户回访按所选期间建立的任务统计当前进度：包含原callback及新销售/维修回访；一次任务只计一次，反复跟进不重复计数。提醒、续保跟进、问卷和投诉另按各自业务统计，不当作已经联系客户。财务或集团汇总仅显示门店、类别、状态与数量，不授权回访原文、客户或原单。'


def build_callbacks(db,user,start,end,stores,aggregate,limit=25000):
    restricted=aggregate or user.role=='finance'
    rows=[]
    def add(number,sid,topic,due,state,result,count,route=None):
        rows.append({'values':[number,stores.get(sid,''),topic,due,state,result,count],
                     'route':route,'count':count,'state':state,'result':result})
    if restricted:
        legacy=select(Case.store_id,Case.state,func.count()).where(Case.kind=='callback',Case.business_date>=start,Case.business_date<=end).group_by(Case.store_id,Case.state)
        detailed=select(Case.store_id,Case.state,CareCase.subtype,CareCase.result,func.count()).join(CareCase,CareCase.case_id==Case.id).where(Case.kind=='customer_care',CareCase.subtype.in_(CALLBACKS),Case.business_date>=start,Case.business_date<=end).group_by(Case.store_id,Case.state,CareCase.subtype,CareCase.result)
        for sid,state,count in db.execute(legacy):add('汇总',sid,'原流程回访','—',STATES.get(state,state),'原结果不展开',count)
        for sid,state,subtype,result,count in db.execute(detailed):add('汇总',sid,LABELS[subtype],'—',STATUS.get(state,state),RESULTS.get(result,'尚未结案') if state!='cancelled' else '已取消',count)
    else:
        legacy=select(Case).where(Case.kind=='callback',Case.business_date>=start,Case.business_date<=end).order_by(Case.id)
        detail=select(Case,CareCase).join(CareCase,CareCase.case_id==Case.id).where(Case.kind=='customer_care',CareCase.subtype.in_(CALLBACKS),Case.business_date>=start,Case.business_date<=end).order_by(Case.id)
        for row in db.scalars(legacy.limit(limit+1)):
            add(row.number,row.store_id,row.data.get('topic','客户回访'),row.due_date.isoformat() if row.due_date else '',STATES.get(row.state,row.state),'原结果见原单',1,{'type':'case','id':row.id})
        for row,care in db.execute(detail.limit(limit+1)):
            add(row.number,row.store_id,LABELS[care.subtype]+' · '+care.topic,row.due_date.isoformat() if row.due_date else '',STATUS.get(row.state,row.state),RESULTS.get(care.result,'尚未结案') if row.state!='cancelled' else '已取消',1,{'type':'case','id':row.id})
    if len(rows)>limit:raise HTTPException(422,'回访明细超过本版报表上限，请缩小期间；没有返回截断结果')
    states=Counter()
    for row in rows:states[row['state']]+=row['count']
    chart={'id':'callback_state','title':'本期回访任务进度','section':'customers','type':'bar','unit':'count','labels':list(states),
           'series':[{'name':'回访任务','values':list(states.values())}],'table':'callbacks','caption':DEFINITION}
    return {'tables':{'callbacks':{'title':'客户回访明细','headers':HEADERS,'rows':rows}},'charts':[chart],
            'metrics':{'callback_task_count':sum(states.values()),'callback_completed_count':states['已完成']+states['已结案'],
                       'callback_cancelled_count':states['已取消']},'definitions':[DEFINITION]}
