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
class Confirmation(Strict):digest:str=Field(pattern=r'^[a-f0-9]{64}$')
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
    return await service.confirm_proposal(db,request,user,session_id,proposal_id,body.digest)


@router.post('/sessions/{session_id}/proposals/{proposal_id}/cancel')
async def cancel(session_id:str,proposal_id:str,body:Confirmation,request:Request,db=Depends(get_db),user=Depends(get_user)):
    return await service.confirm_proposal(db,request,user,session_id,proposal_id,body.digest,True)


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
