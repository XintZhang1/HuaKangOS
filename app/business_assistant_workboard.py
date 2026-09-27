"""Persist goals; derive progress from actual proposals and authorized native records.

A plan never executes an operation and its free text is not business evidence.
"""
from __future__ import annotations
from copy import deepcopy
from uuid import uuid4
from datetime import timedelta
import re
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .business_assistant_models import AssistantWorkPlan, AssistantProposal

LIVE_CASE_PAGE = 10
STATUS_LABELS = {
    'awaiting_confirmation':'待你确认', 'needs_input':'请补充必要资料', 'executing':'正在办理，请勿重复提交',
    'step_completed':'这一步已办理', 'failed':'这一步未办成', 'uncertain':'结果待核对，不能重试',
    'cancelled':'这一步已取消', 'expired':'草稿已过期，请重新核对', 'waiting_dependency':'等待前一步',
    'needs_preparation':'前序已办理，请核对下一步条件', 'planned':'待准备', 'waiting_fact':'等待实际资料或同事办理',
    'following_case':'查看原单当前进度', 'unavailable':'引用已不可访问，请重新核对',
}


def validate_graph(steps):
    keys=[x['key'] for x in steps]
    if len(keys)!=len(set(keys)): raise HTTPException(422,'计划步骤的标识不能重复')
    graph={x['key']:x.get('depends_on',[]) for x in steps};all_keys=set(keys)
    for key,deps in graph.items():
        if key in deps or len(deps)!=len(set(deps)) or set(deps)-all_keys:
            raise HTTPException(422,'步骤只能依赖本计划内其他步骤，不能重复或依赖自己')
    visiting=set();done=set()
    def visit(key):
        if key in visiting: raise HTTPException(422,'步骤之间形成循环，请按真实先后关系整理')
        if key in done:return
        visiting.add(key)
        for dep in graph[key]:visit(dep)
        visiting.remove(key);done.add(key)
    for key in keys:visit(key)
    refs=[x['proposal_id'] for x in steps if x.get('proposal_id')]
    if len(refs)!=len(set(refs)): raise HTTPException(422,'同一张草稿不能重复计为多个已办步骤')


def owned_proposals(db,user,sid,ids):
    from .business_assistant_service import owned_session
    thread=owned_session(db,user,sid)
    return {p.id:p for p in db.scalars(select(AssistantProposal).where(
        AssistantProposal.session_id==sid,AssistantProposal.owner_id==user.id,
        AssistantProposal.owner_role==user.role,AssistantProposal.access_version==user.access_version,
        AssistantProposal.store_id==thread.store_id,AssistantProposal.id.in_(ids)))} if ids else {}


async def save_plan(db,request,user,sid,config,args):
    from . import business_assistant_service as s
    from .business_assistant_business_tools import native, checked
    from .workflow_guides_api import load_catalogue
    thread=s.owned_session(db,user,sid)
    steps=deepcopy(args['steps']);validate_graph(steps)
    ordered=[];pending=list(steps);done=set()
    while pending:
        step=next(x for x in pending if set(x.get('depends_on',[]))<=done)
        pending.remove(step);ordered.append(step);done.add(step['key'])
    steps=ordered
    # Do not persist credentials or silently mutate reference identifiers.
    if s.scrub({'goal':args['goal'],'steps':steps})!={'goal':args['goal'],'steps':steps}:
        raise HTTPException(422,'计划含隐藏信息或过长内容，请只写业务目标与必要步骤')
    refs=[x['proposal_id'] for x in steps if x.get('proposal_id')]
    proposals=owned_proposals(db,user,sid,refs)
    if len(proposals)!=len(refs):raise HTTPException(404,'草稿不属于当前对话或已不可访问')
    case_ids={x['case_id'] for x in steps if x.get('case_id')}
    if len(case_ids)>LIVE_CASE_PAGE:
        raise HTTPException(422,'一份计划最多关联10条原单；大量独立项请关联真实草稿，避免每次刷新遍历全库')
    for case_id in case_ids:
        checked(await native(db,request,user,sid,config,'GET /api/flow/cases/{case_id}',{'case_id':case_id}))
    published={row['id'] for row in load_catalogue()}
    for step in steps:
        if not step.get('proposal_id') and not step.get('case_id') and not step.get('workflow_id'):
            raise HTTPException(422,'尚未关联原单的计划步骤必须注明真实发布的工作流')
        p=proposals.get(step.get('proposal_id'))
        if p and step.get('case_id') and proposal_case_id(p)!=step['case_id']:
            raise HTTPException(422,'草稿与所选原单的关系尚未证实，请勿混合关联')
        wf=step.get('workflow_id')
        if wf:
            if wf not in published:
                raise HTTPException(422,'请关联实际发布的工作流，不要编造说明编号')
    # Nested native calls commit their reader transactions; re-authorize afterwards.
    thread=s.owned_session(db,user,sid)
    rid=thread.busy_token or ('manual-'+uuid4().hex)
    row=None
    if args.get('plan_id'):
        row=db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id==args['plan_id'],
            AssistantWorkPlan.session_id==sid,AssistantWorkPlan.owner_id==user.id,AssistantWorkPlan.store_id==thread.store_id))
        if not row:raise HTTPException(404,'计划不存在或不可访问')
    else:
        row=db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.session_id==sid,AssistantWorkPlan.request_id==rid))
    if row:
        if row.goal==args['goal'] and row.steps==steps:
            return {'status':200,'plan_id':row.id,'version':row.version,'reused':True,'business_executed':False}
        if args.get('expected_version')!=row.version:raise HTTPException(409,'计划已更新，请读取最新版本后修改')
        row.goal=args['goal'];row.steps=steps;row.updated_at=utcnow()
    else:
        if args.get('expected_version') not in (None,0):raise HTTPException(409,'新计划没有旧版本')
        row=AssistantWorkPlan(id=str(uuid4()),store_id=thread.store_id,session_id=sid,owner_id=user.id,
            request_id=rid,goal=args['goal'],steps=steps)
        db.add(row)
    s.commit(db)
    return {'status':200,'plan_id':row.id,'version':row.version,'business_executed':False,
            'notice':'仅保存本次办事计划；进度以草稿确认结果和实际原单为准，未自动执行业务。'}


def proposal_case_id(proposal):
    path=(proposal.payload or {}).get('path_args') or {}
    # Only the canonical case endpoint path or explicit canonical route proves the type.
    if '/api/flow/cases/{case_id}' in proposal.operation_id and type(path.get('case_id')) is int:
        return path['case_id']
    result=proposal.result or {};route=result.get('route')
    match=re.fullmatch(r'(?:#)?case/([1-9][0-9]*)',route) if isinstance(route,str) else None
    return int(match[1]) if match else None


def derive_steps(steps,proposals):
    states={};by_key={x['key']:x for x in steps}
    def state(key):
        if key in states:return states[key]
        step=by_key[key];p=proposals.get(step.get('proposal_id'));deps=step.get('depends_on',[])
        if step.get('proposal_id') and not p: value='unavailable'
        elif p:
            value=({'pending':'expired' if p.expires_at<=utcnow() else 'needs_input' if p.questions else 'awaiting_confirmation',
                    'succeeded':'step_completed'}).get(p.status,p.status)
            if value=='executing' and p.started_at and p.started_at<utcnow()-timedelta(minutes=3):value='uncertain'
        elif deps and any(state(dep)!='step_completed' for dep in deps):value='waiting_dependency'
        elif step.get('case_id'):value='following_case'
        elif step.get('wait_for'):value='waiting_fact'
        elif deps:value='needs_preparation'
        else:value='planned'
        states[key]=value;return value
    result=[]
    for step in steps:
        p=proposals.get(step.get('proposal_id'));status=state(step['key'])
        cid=step.get('case_id') or (proposal_case_id(p) if p else None)
        result.append({**step,'status':status,'status_label':STATUS_LABELS.get(status,'请核对'),
            'case_id':cid,'route':f'case/{cid}' if cid else None,
            'missing':[q.get('label','必要资料') for q in (p.questions or [])] if p and status=='needs_input' else [],
            'evidence':'草稿实际结果' if p else '计划说明，尚不是业务完成证据',
            'dependency_results':[{'step_key':dep,'case_id':proposal_case_id(proposals[by_key[dep]['proposal_id']])}
                for dep in step.get('depends_on',[]) if by_key[dep].get('proposal_id') in proposals
                and proposals[by_key[dep]['proposal_id']].status=='succeeded']})
    return result


def plan_briefs(db,user,sid):
    from .business_assistant_service import owned_session, stamp
    thread=owned_session(db,user,sid)
    rows=list(db.scalars(select(AssistantWorkPlan).where(AssistantWorkPlan.session_id==sid,
        AssistantWorkPlan.owner_id==user.id,AssistantWorkPlan.store_id==thread.store_id)
        .order_by(AssistantWorkPlan.updated_at.desc(),AssistantWorkPlan.id).limit(20)))
    return [{'id':p.id,'goal':p.goal,'version':p.version,'step_count':len(p.steps),
             'updated_at':stamp(p.updated_at)} for p in rows]


async def work_status(db,request,user,sid,config,args):
    from . import business_assistant_service as s
    from .business_assistant_business_tools import native, checked
    thread=s.owned_session(db,user,sid)
    stmt=select(AssistantWorkPlan).where(AssistantWorkPlan.session_id==sid,
        AssistantWorkPlan.owner_id==user.id,AssistantWorkPlan.store_id==thread.store_id)
    if args.get('plan_id'):stmt=stmt.where(AssistantWorkPlan.id==args['plan_id'])
    plan=db.scalar(stmt.order_by(AssistantWorkPlan.updated_at.desc(),AssistantWorkPlan.id).limit(1))
    if not plan:
        if args.get('plan_id'):raise HTTPException(404,'计划不存在或不可访问')
        return {'status':200,'plan':None,'plans':plan_briefs(db,user,sid),'notice':'当前对话没有保存的多步计划；单项业务直接核对原卡片。'}
    proposals=owned_proposals(db,user,sid,[x['proposal_id'] for x in plan.steps if x.get('proposal_id')])
    steps=derive_steps(plan.steps,proposals)
    from .workflow_guides_api import load_catalogue
    published={r['id']:r for r in load_catalogue()}
    for step in steps:
        guide=published.get(step.get('workflow_id'))
        step['workflow_route']=guide['entry']['route'] if guide else None
    case_ids=sorted({x['case_id'] for x in steps if x.get('case_id')})
    page=args.get('case_page',1);offset=(page-1)*LIVE_CASE_PAGE;current_ids=case_ids[offset:offset+LIVE_CASE_PAGE]
    records=[]
    for cid in current_ids:
        try:
            data=checked(await native(db,request,user,sid,config,'GET /api/flow/cases/{case_id}',{'case_id':cid}))
            tasks=[t for t in data.get('tasks',[]) if t.get('status')=='open']
            def task(t):return {k:t.get(k) for k in ('id','title','assignee_id','assignee_name','due_date')}
            mine=[task(t) for t in tasks if t.get('assignee_id')==user.id]
            others=[task(t) for t in tasks if t.get('assignee_id') not in (None,user.id)]
            unassigned=[task(t) for t in tasks if t.get('assignee_id') is None]
            records.append({'case_id':cid,'route':f'case/{cid}','number':data.get('number'),'title':data.get('title'),
                'state':data.get('state'),'state_label':data.get('state_label'),
                'mine':mine,'others':others,'unassigned':unassigned,
                'actions':[{'form_ref':f"case:{cid}:{a['key']}",'label':a.get('label'),
                    'enabled':bool(a.get('enabled')),'reason':a.get('reason')}
                    for a in data.get('actions',[]) if a.get('key')],
                'notice':'可操作不等于本人必须办理；没有待办也不等于已经到账、到货或完成外部手续。'})
        except HTTPException as exc:
            records.append({'case_id':cid,'status':exc.status_code,'error':'原单进度未读取成功或已不可访问，请重试或到原页面核对。'})
    # Recheck access before exposing a result after nested calls.
    s.owned_session(db,user,sid)
    return {'status':200,'plan':{'id':plan.id,'goal':plan.goal,'version':plan.version,'steps':steps},
        'plans':plan_briefs(db,user,sid),'cases':records,'case_page':page,'case_total':len(case_ids),
        'next_case_page':page+1 if offset+LIVE_CASE_PAGE<len(case_ids) else None,
        'checked_at':s.stamp(utcnow()),'business_executed':False,
        'notice':'刷新只读取实际状态，不调用模型、不自动确认或创建后续业务。计划中的等待原因来自办事说明，不替代原单条件。'}
