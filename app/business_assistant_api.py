"""Employee-scoped conversational business assistant, separate from daily AI reports."""
import json
from typing import Literal
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .db import get_db
from .security import get_user
from .tenancy import single_store
from .models import User
from .business_assistant_models import AssistantSession, AssistantIssue
from . import business_assistant_service as service

router=APIRouter(prefix='/api/business-assistant',tags=['业务助手'])


@router.post('/file-preview')
async def file_preview(request:Request,db=Depends(get_db),user=Depends(get_user)):
    # The caller explicitly uploads bytes. No path, model, persistence or business write.
    single_store(db)
    from .business_assistant_files import LIMITS, preview_multipart
    from fastapi import HTTPException
    body=bytearray()
    async for block in request.stream():
        body.extend(block)
        if len(body)>LIMITS['request_bytes']:
            raise HTTPException(413,'本次文件总大小超过 20 MiB，请分批选择')
    return await run_in_threadpool(preview_multipart,bytes(body),request.headers.get('content-type',''))


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class NewSession(Strict):title:str=Field(default='新对话',max_length=100)
class Message(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    content:str=Field(min_length=1,max_length=service.MAX_MESSAGE)
    thinking:bool=Field(default=False,strict=True)
class Confirmation(Strict):
    digest:str=Field(pattern=r'^[a-f0-9]{64}$')
    # 员工在卡片必填项里填的值（键只能是这张卡自己声明的 key）；没填完服务端不放行。
    answers:dict[str,str]|None=Field(default=None)
class BatchCard(Strict):
    id:str=Field(min_length=1,max_length=64)
    digest:str=Field(pattern=r'^[a-f0-9]{64}$')
    answers:dict[str,str]|None=Field(default=None)
class BatchDecision(Strict):
    # 员工在页面上核对一组卡片后的那一次点击：逐张照办，每张仍是它自己的办理。
    items:list[BatchCard]=Field(min_length=1,max_length=service.BATCH_LIMIT)
    action:Literal['confirm','cancel']='confirm'
class Issue(Strict):
    category:Literal['input','rule','system','model','unsupported']
    summary:str=Field(min_length=1,max_length=1200)
    operation_id:str=Field(default='',max_length=180)


@router.get('/status')
def assistant_status(db=Depends(get_db),user=Depends(get_user)):
    single_store(db)
    return service.status()


@router.get('/sessions')
def sessions(db=Depends(get_db),user=Depends(get_user)):
    store=single_store(db)
    rows=db.scalars(select(AssistantSession).join(User,User.id==AssistantSession.owner_id).where(
        AssistantSession.owner_id==user.id,AssistantSession.store_id==store,
        AssistantSession.owner_role==user.role,AssistantSession.access_version==user.access_version,
        User.access_version==AssistantSession.access_version,User.active.is_(True)).order_by(AssistantSession.updated_at.desc()).limit(80))
    return {'items':[service.session_brief(row) for row in rows]}


@router.post('/sessions',status_code=201)
def new_session(body:NewSession,db=Depends(get_db),user=Depends(get_user)):
    return service.create_session(db,user,body.title)


@router.get('/sessions/{session_id}')
def session(session_id:str,db=Depends(get_db),user=Depends(get_user)):
    return service.session_view(db,user,session_id)


@router.post('/sessions/{session_id}/messages')
async def message(session_id:str,body:Message,request:Request,db=Depends(get_db),user=Depends(get_user)):
    return await service.conversation(db,request,user,session_id,body.request_id,body.content,thinking=body.thinking)


@router.post('/sessions/{session_id}/messages/stream')
async def stream_message(session_id:str,body:Message,request:Request,db=Depends(get_db),user=Depends(get_user)):
    from .business_assistant_stream import streaming_response
    return await streaming_response(db,request,user,session_id,body.request_id,body.content,body.thinking)


@router.post('/sessions/{session_id}/proposals/{proposal_id}/confirm')
async def confirm(session_id:str,proposal_id:str,body:Confirmation,request:Request,db=Depends(get_db),user=Depends(get_user)):
    return await service.confirm_proposal(db,request,user,session_id,proposal_id,body.digest,answers=body.answers)


@router.post('/sessions/{session_id}/proposals/{proposal_id}/cancel')
async def cancel(session_id:str,proposal_id:str,body:Confirmation,request:Request,db=Depends(get_db),user=Depends(get_user)):
    return await service.confirm_proposal(db,request,user,session_id,proposal_id,body.digest,True,body.answers)


@router.post('/sessions/{session_id}/proposals/batch')
async def batch(session_id:str,body:BatchDecision,request:Request,db=Depends(get_db),user=Depends(get_user)):
    return await service.batch_decide(db,request,user,session_id,[item.model_dump() for item in body.items],
                                      cancel=body.action=='cancel')


@router.post('/sessions/{session_id}/issues',status_code=201)
def add_issue(session_id:str,body:Issue,db=Depends(get_db),user=Depends(get_user)):
    return service.record_issue(db,user,session_id,body.category,body.summary,body.operation_id,synthetic=service.load_config().synthetic)


@router.get('/issues')
def issues(db=Depends(get_db),user=Depends(get_user)):
    store=single_store(db)
    rows=db.scalars(select(AssistantIssue).join(AssistantSession,AssistantSession.id==AssistantIssue.session_id).join(User,User.id==AssistantSession.owner_id).where(
        AssistantIssue.owner_id==user.id,AssistantIssue.store_id==store,AssistantSession.owner_id==user.id,
        AssistantSession.store_id==store,AssistantSession.owner_role==user.role,AssistantSession.access_version==user.access_version,
        User.access_version==AssistantSession.access_version,User.active.is_(True)
    ).order_by(AssistantIssue.id.desc()).limit(500))
    return {'items':[service.issue_view(row) for row in rows]}


@router.get('/issues/export')
def export_issues(db=Depends(get_db),user=Depends(get_user)):
    data=issues(db,user)
    return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="huakangos-assistant-issues.json"'})


class ToolCall(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=1,max_length=80)
    arguments:dict=Field(default_factory=dict)


@router.get('/tools')
def business_tools(db=Depends(get_db),user=Depends(get_user)):
    """Bound to the ordinary employee session; never exposes a confirmation tool."""
    from dataclasses import replace
    single_store(db)
    config=replace(service.load_config(),tool_profile='business_v1')
    return {'profile':'business_v1','tools':service.tools_for_config(config),
            'notice':'仅查询、计划与准备草稿；确认仍在原业务界面由当前员工点击。'}


@router.get('/sessions/{session_id}/work-status')
async def work_status(session_id:str,request:Request,plan_id:str|None=None,case_page:int=1,
                      db=Depends(get_db),user=Depends(get_user)):
    from .business_assistant_business_tools import validate
    from .business_assistant_workboard import work_status as read_status
    args=validate('get_work_status',{'plan_id':plan_id,'case_page':case_page})
    return await read_status(db,request,user,session_id,service.load_config(),args)


@router.post('/sessions/{session_id}/tools/call')
async def call_business_tool(session_id:str,body:ToolCall,request:Request,db=Depends(get_db),user=Depends(get_user)):
    """MCP/application adapter: same actor and same draft-only service, no model call."""
    import asyncio
    from dataclasses import replace
    from datetime import timedelta
    from fastapi import HTTPException
    from .db import utcnow
    if len(json.dumps(body.arguments,ensure_ascii=False))>service.MODEL_ARGUMENT_CHARS:
        raise HTTPException(413,'工具参数过长，请按完整事项分批处理')
    config=replace(service.load_config(),tool_profile='business_v1')
    if body.name not in {t['function']['name'] for t in service.tools_for_config(config)}:
        raise HTTPException(422,'不是受支持的业务工具；不能通过工具确认或执行任意操作')
    thread=service.owned_session(db,user,session_id)
    if thread.busy_token and thread.busy_until and thread.busy_until>utcnow():
        raise HTTPException(409,'本对话正在处理其他事项，请稍后读取状态再操作')
    thread.busy_token=body.request_id;thread.busy_until=utcnow()+timedelta(seconds=180)
    service.commit(db)
    try:
        async with asyncio.timeout(120):
            result=await service.run_tools(db,request,user,session_id,body.name,body.arguments,config)
            service.owned_session(db,user,session_id)
            return service.scrub(result)
    except TimeoutError:
        raise HTTPException(504,'本次工具调用未完整结束；请先刷新原草稿和计划，不能把部分结果当成全部完成') from None
    finally:
        db.rollback()
        row=db.scalar(select(AssistantSession).where(AssistantSession.id==session_id,
            AssistantSession.owner_id==user.id).execution_options(populate_existing=True))
        if row and row.busy_token==body.request_id:
            row.busy_token=None;row.busy_until=None;row.updated_at=utcnow();service.commit(db)
