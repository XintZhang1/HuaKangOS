"""Persist goals; derive progress from actual proposals and authorized native records.

A plan never executes an operation and its free text is not business evidence.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4
from datetime import timedelta
from weakref import WeakKeyDictionary, ref
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


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class ResolvedLegacyPlan:
    """Opaque completed reads, consumed once by this same database Session."""


_legacy_plan_saves=WeakKeyDictionary()


def _legacy_conflict():
    raise HTTPException(409,'计划或关联记录已变化，请重新核对后保存')


def _legacy_identity(user,sid,store_id):
    return (user.id,store_id,sid,user.role,user.access_version)


def _legacy_runtime_source(db,principal,user,sid,*,clock=None):
    if principal is None:return
    from .assistant_runtime_models import Run
    from .assistant_runtime_mcp import is_mcp_run
    from .assistant_runtime_plans import _runtime_plan_source
    _runtime_plan_source(db,principal,user,sid,None,clock=clock)
    run=db.scalar(select(Run).where(Run.id==principal.run_id,
        Run.owner_id==principal.actor_id,Run.store_id==principal.store_id,Run.session_id==sid))
    if (principal.auth_kind!='login' or principal.plan_id is not None
            or principal.goal_version is not None or run is None or not is_mcp_run(run)):
        _legacy_conflict()


def _legacy_plan(db,thread,plan_id,rid,*,lock=False):
    query=select(AssistantWorkPlan).where(AssistantWorkPlan.session_id==thread.id,
        AssistantWorkPlan.owner_id==thread.owner_id,AssistantWorkPlan.store_id==thread.store_id)
    query=query.where(AssistantWorkPlan.id==plan_id) if plan_id else query.where(AssistantWorkPlan.request_id==rid)
    if lock:query=query.with_for_update()
    row=db.scalar(query.execution_options(populate_existing=True))
    if plan_id and row is None:raise HTTPException(404,'计划不存在或不可访问')
    if row is not None and row.engine_version!=1:
        raise HTTPException(409,'此计划已使用结构化步骤，请按 schema_version=2 读取和修改，不能降级覆盖')
    return row


def _legacy_plan_revision(row):
    return (row.id,row.version,row.engine_version) if row is not None else None


def _legacy_card_refs(db,user,thread,steps):
    ids=[step['proposal_id'] for step in steps if step.get('proposal_id')]
    cards={row.id:row for row in db.scalars(select(AssistantProposal).where(
        AssistantProposal.session_id==thread.id,AssistantProposal.owner_id==user.id,
        AssistantProposal.store_id==thread.store_id,AssistantProposal.owner_role==user.role,
        AssistantProposal.access_version==user.access_version,AssistantProposal.id.in_(ids))
        .execution_options(populate_existing=True))} if ids else {}
    if len(cards)!=len(ids):raise HTTPException(404,'草稿不属于当前对话或已不可访问')
    for step in steps:
        card=cards.get(step.get('proposal_id'))
        if card and step.get('case_id') and proposal_case_id(card)!=step['case_id']:
            raise HTTPException(422,'草稿与所选原单的关系尚未证实，请勿混合关联')
    return tuple(sorted((row.id,row.version,proposal_case_id(row)) for row in cards.values()))


async def resolve_legacy_plan(db,request,user,sid,config,args,*,principal=None,clock=None):
    """Resolve the original schema-1 references without saving a Plan or result."""
    from . import business_assistant_service as s
    from .business_assistant_business_tools import native,checked,validate
    from .assistant_runtime_plans import _authorized_thread
    from .assistant_runtime_principal import RuntimePrincipal,runtime_request_context
    from .workflow_guides_api import load_catalogue
    s.require_preparation_read_phase(db)
    context=runtime_request_context(request) if hasattr(request,'scope') else None
    if (context is not None and (context.db is not db or context.principal is not principal)
            or principal is not None and context is None
            or type(user) is RuntimePrincipal and principal is None):
        _legacy_conflict()
    _legacy_runtime_source(db,principal,user,sid,clock=clock)
    data=validate('save_work_plan',deepcopy(args))
    if data.get('schema_version',1)!=1:_legacy_conflict()
    steps=deepcopy(data['steps']);validate_graph(steps)
    ordered=[];pending=list(steps);done=set()
    while pending:
        step=next(x for x in pending if set(x.get('depends_on',[]))<=done)
        pending.remove(step);ordered.append(step);done.add(step['key'])
    steps=ordered
    # Do not persist credentials or silently mutate reference identifiers.
    if s.scrub({'goal':data['goal'],'steps':steps})!={'goal':data['goal'],'steps':steps}:
        raise HTTPException(422,'计划含隐藏信息或过长内容，请只写业务目标与必要步骤')
    thread=_authorized_thread(db,user,sid)
    identity=_legacy_identity(user,sid,thread.store_id)
    session_version,busy_token=thread.version,thread.busy_token
    rid=busy_token or ('manual-'+uuid4().hex)
    plan=_legacy_plan(db,thread,data.get('plan_id'),rid)
    original_plan=_legacy_plan_revision(plan)
    cards=_legacy_card_refs(db,user,thread,steps)
    case_ids={x['case_id'] for x in steps if x.get('case_id')}
    if len(case_ids)>LIVE_CASE_PAGE:
        raise HTTPException(422,'一份计划最多关联10条原单；大量独立项请关联真实草稿，避免每次刷新遍历全库')
    for case_id in case_ids:
        checked(await native(db,request,user,sid,config,'GET /api/flow/cases/{case_id}',{'case_id':case_id}))
    published={row['id'] for row in load_catalogue()}
    for step in steps:
        if not step.get('proposal_id') and not step.get('case_id') and not step.get('workflow_id'):
            raise HTTPException(422,'尚未关联原单的计划步骤必须注明真实发布的工作流')
        wf=step.get('workflow_id')
        if wf:
            if wf not in published:
                raise HTTPException(422,'请关联实际发布的工作流，不要编造说明编号')
    # A nested original GET can finish its read transaction. Keep primitives,
    # then recheck the real identity; never adopt a refreshed caller identity.
    thread=_authorized_thread(db,user,sid)
    if _legacy_identity(user,sid,thread.store_id)!=identity:_legacy_conflict()
    _legacy_runtime_source(db,principal,user,sid,clock=clock)
    resolved=ResolvedLegacyPlan()
    from .assistant_runtime_plans import _condition_identity
    _legacy_plan_saves[resolved]={'session_ref':ref(db),'bind':db.get_bind(),
        'principal':principal,'principal_identity':_condition_identity(principal) if principal is not None else None,
        'identity':identity,'issued_at':monotonic(),'data':deepcopy(data),'steps':steps,
        'rid':rid,'busy_token':busy_token,'session_version':session_version,'plan':original_plan,'cards':cards}
    return resolved


def persist_legacy_plan(db,user,sid,resolved,*,principal=None,clock=None):
    """Flush only. The MCP caller owns the fenced checkpoint and commit/rollback."""
    from .assistant_runtime_plans import _authorized_thread,_condition_identity
    from .assistant_runtime_principal import _time
    from .business_assistant_models import AssistantSession
    state=_legacy_plan_saves.pop(resolved,None) if type(resolved) is ResolvedLegacyPlan else None
    if (state is None or state['session_ref']() is not db or state['bind'] is not db.get_bind()
            or state['principal'] is not principal or monotonic()-state['issued_at']>60
            or state['identity']!=_legacy_identity(user,sid,state['identity'][1])
            or db.new or db.dirty or db.deleted):
        _legacy_conflict()
    _legacy_runtime_source(db,principal,user,sid,clock=clock)
    if principal is not None:
        from .assistant_runtime_events import _capability
        if state['principal_identity']!=_condition_identity(principal):_legacy_conflict()
        _capability(db,principal,clock=clock)
    data,steps,rid=state['data'],state['steps'],state['rid']
    thread=_authorized_thread(db,user,sid)
    locked=db.scalar(select(AssistantSession).where(AssistantSession.id==sid,
        AssistantSession.owner_id==user.id,AssistantSession.store_id==thread.store_id)
        .with_for_update().execution_options(populate_existing=True))
    if (locked is None or locked.version!=state['session_version'] or locked.busy_token!=state['busy_token']
            or _legacy_identity(user,sid,locked.store_id)!=state['identity']):
        _legacy_conflict()
    row=_legacy_plan(db,locked,data.get('plan_id'),rid,lock=True)
    if (_legacy_plan_revision(row)!=state['plan']
            or _legacy_card_refs(db,user,locked,steps)!=state['cards']):
        _legacy_conflict()
    if row:
        if row.goal==data['goal'] and row.steps==steps:
            return {'status':200,'plan_id':row.id,'version':row.version,'reused':True,'business_executed':False}
        if data.get('expected_version')!=row.version:raise HTTPException(409,'计划已更新，请读取最新版本后修改')
        row.goal=data['goal'];row.steps=deepcopy(steps);row.updated_at=_time((clock or utcnow)())
    else:
        if data.get('expected_version') not in (None,0):raise HTTPException(409,'新计划没有旧版本')
        row=AssistantWorkPlan(id=str(uuid4()),store_id=locked.store_id,session_id=sid,owner_id=user.id,
            request_id=rid,goal=data['goal'],steps=deepcopy(steps))
        db.add(row)
    db.info['assistant_preparation_transaction']=db.get_transaction()
    db.flush()
    from .assistant_runtime_plans import _emit_plan_signal
    _emit_plan_signal(db,row)
    return {'status':200,'plan_id':row.id,'version':row.version,'business_executed':False,
            'notice':'仅保存本次办事计划；进度以草稿确认结果和实际原单为准，未自动执行业务。'}


async def save_plan(db,request,user,sid,config,args):
    from . import business_assistant_service as s
    thread=s.owned_session(db,user,sid)
    current=None
    if args.get('plan_id'):
        current=db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.id==args['plan_id'],
            AssistantWorkPlan.session_id==sid,AssistantWorkPlan.owner_id==user.id,
            AssistantWorkPlan.store_id==thread.store_id))
    elif thread.busy_token:
        # A retried same-turn legacy call must not downgrade a structured Plan.
        current=db.scalar(select(AssistantWorkPlan).where(AssistantWorkPlan.request_id==thread.busy_token,
            AssistantWorkPlan.session_id==sid,AssistantWorkPlan.owner_id==user.id,
            AssistantWorkPlan.store_id==thread.store_id))
    if args.get('schema_version',1)==2 or current is not None and current.engine_version==2:
        from .assistant_runtime_plans import save_plan as save_runtime_plan
        return await save_runtime_plan(db,request,user,sid,config,args)
    try:
        resolved=await resolve_legacy_plan(db,request,user,sid,config,args)
        result=persist_legacy_plan(db,user,sid,resolved)
        if result.get('reused'):
            db.rollback()  # No writes; do not retain the new short row locks.
        else:
            s.commit(db)
        return result
    except Exception as exc:
        # Flush now happens before the original commit wrapper. Preserve its
        # optimistic/unique/serialization conflict mapping at that boundary.
        from .assistant_runtime_plans import _followup_failure
        _followup_failure(db,exc)


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
    def step_count(plan):
        if plan.engine_version==1:return len(plan.steps)
        from .assistant_runtime_models import PlanStep
        from sqlalchemy import func
        return db.scalar(select(func.count()).select_from(PlanStep).where(PlanStep.plan_id==plan.id))
    return [{'id':p.id,'goal':p.goal,'version':p.version,'step_count':step_count(p),
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
    if plan.engine_version==2:
        from .assistant_runtime_plans import project_legacy_plan
        plan_view=project_legacy_plan(db,user,sid,plan)
        steps=plan_view['steps']
    else:
        proposals=owned_proposals(db,user,sid,[x['proposal_id'] for x in plan.steps if x.get('proposal_id')])
        steps=derive_steps(plan.steps,proposals)
        plan_view={'id':plan.id,'goal':plan.goal,'version':plan.version,'steps':steps}
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
    if plan_view.get('engine_version')==2:
        from .assistant_runtime_plans import _authorized_thread
        _authorized_thread(db,user,sid)
    return {'status':200,'plan':{**plan_view,'steps':steps},
        'plans':plan_briefs(db,user,sid),'cases':records,'case_page':page,'case_total':len(case_ids),
        'next_case_page':page+1 if offset+LIVE_CASE_PAGE<len(case_ids) else None,
        'checked_at':s.stamp(utcnow()),'business_executed':False,
        'notice':'刷新只读取实际状态，不调用模型、不自动确认或创建后续业务。计划中的等待原因来自办事说明，不替代原单条件。'}
