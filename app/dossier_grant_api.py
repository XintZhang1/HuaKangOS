"""Explicit read-only dossier routes; ordinary original/file routes stay scoped."""
from datetime import datetime
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .db import get_db,get_write_db, get_audited_read_db
from .security import get_user
from . import dossier_grant_service as service
from . import dossier_grant_rules as rules

router = APIRouter(prefix='/api/dossier-grants', tags=['dossier-grants'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Values(Strict):
    source_case_id: int = Field(gt=0, strict=True)
    source_case_version: int = Field(gt=0, strict=True)
    to_store_id: int = Field(gt=0, strict=True)
    recipient_id: int = Field(gt=0, strict=True)
    include_record: bool = Field(default=True, strict=True)
    include_financials: bool = Field(default=False, strict=True)
    include_contact: bool = Field(default=False, strict=True)
    file_ids: list[int] = Field(default_factory=list, max_length=rules.MAX_FILES)
    purpose: str = Field(min_length=3, max_length=500)
    expires_at: datetime
    confirmed: bool = Field(strict=True)

    @field_validator('confirmed')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('须明确确认原单和所选文件的跨店只读范围')
        return value

    @field_validator('file_ids', mode='before')
    @classmethod
    def exact_files(cls, value):
        if not isinstance(value, list) or any(type(i) is not int or i <= 0 for i in value) or len(value) != len(set(value)):
            raise ValueError('文件编号须为不重复的正整数')
        return value

    @field_validator('expires_at')
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('到期时间必须包含时区')
        return value


class Save(Strict):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    values: Values


class ReviewValues(Strict):
    reason: str = Field(min_length=3, max_length=500)
    confirmed: bool = Field(strict=True)

    @field_validator('confirmed')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('须明确确认本次决定')
        return value


class Decision(Strict):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    version: int = Field(gt=0, strict=True)
    values: ReviewValues


@router.get('/catalog')
def catalog(db=Depends(get_db), user=Depends(get_user)):
    allowed = not getattr(user, '_aggregate_scope', False) and user.role in rules.READ
    return {'can_read': allowed, 'can_propose': allowed and user.role in rules.WRITE,
            'can_review': allowed and user.role in rules.MANAGE, 'states': rules.STATES,
            'notice': '仅指定员工可只读批准时的原单快照和逐件文件；换岗、到期或撤销后重新核验。'}


@router.get('/source/{case_id}')
def source(case_id: int, to_store_id: int | None = Query(None, gt=0), recipient_id: int | None = Query(None, gt=0),
           db=Depends(get_db), user=Depends(get_user)):
    return service.source_options(db, user, case_id, to_store_id, recipient_id)


@router.get('')
def listing(box: Literal['received', 'sent', 'review'] = 'received', state: str = '',
            page: int = Query(1, ge=1), source_case_id: int | None = Query(None, gt=0),
            db=Depends(get_db), user=Depends(get_user)):
    return service.listing(db, user, box=box, state=state, page=page, source_case_id=source_case_id)


@router.post('', status_code=201)
def propose(body: Save, db=Depends(get_write_db), user=Depends(get_user)):
    return service.propose(db, user, body.request_id, body.values.model_dump())


@router.get('/{grant_id}')
def detail(grant_id: int, db=Depends(get_db), user=Depends(get_user)):
    return service.detail(db, user, grant_id)


@router.post('/{grant_id}/actions/{action}')
def action(grant_id: int, action: str, body: Decision, db=Depends(get_write_db), user=Depends(get_user)):
    return service.decide(db, user, body.request_id, grant_id, body.version, action, body.values.model_dump())


@router.get('/{grant_id}/record')
def record(grant_id: int, db=Depends(get_audited_read_db), user=Depends(get_user)):
    return service.read_record(db, user, grant_id)


@router.get('/{grant_id}/files')
def files(grant_id: int, db=Depends(get_audited_read_db), user=Depends(get_user)):
    return service.received_files(db, user, grant_id)


@router.get('/{grant_id}/files/{file_id}')
def download(grant_id: int, file_id: int, db=Depends(get_audited_read_db), user=Depends(get_user)):
    content, name, media_type = service.download(db, user, grant_id, file_id)
    return Response(content, media_type=media_type, headers={
        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name),
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store',
        'Content-Security-Policy': "sandbox; default-src 'none'"})
