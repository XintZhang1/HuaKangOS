"""Employee feedback intake only; operational analysis is a separate service."""
import os
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from .config import ROOT
from .db import get_db
from .ops_store import OpsStore
from .security import get_user
from .tenancy import single_store


router = APIRouter(prefix='/api/feedback', tags=['意见反馈'])


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=12000)
    category: Literal['bug', 'improvement', 'feature'] = 'improvement'
    request_id: str = Field(min_length=36, max_length=36)
    route: Literal['business-assistant', 'work', 'sales', 'inventory', 'repair',
                   'materials', 'finance', 'customers', 'members', 'system', 'other'] = 'other'
    consent_analysis: bool

    @field_validator('request_id')
    @classmethod
    def request_uuid(cls, value):
        if str(UUID(value)) != value:
            raise ValueError('请求编号格式无效')
        return value

    @field_validator('consent_analysis')
    @classmethod
    def analysis_consent(cls, value):
        if value is not True:
            raise ValueError('提交前请确认意见将交给 DeepSeek 分析及 Cutie 审阅')
        return value


def _store():
    """Only the deployment CLI creates the external operations database."""
    name = os.environ.get('OPS_STATE_DB', '').strip()
    try:
        path = Path(name)
        if not name or not path.is_absolute() or path.is_symlink():
            raise RuntimeError('configuration')
        path = path.resolve(strict=True)
        if not path.is_file() or path.is_relative_to(ROOT.resolve()):
            raise RuntimeError('configuration')
        return OpsStore(str(path))
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(503, '意见收集暂时不可用，请稍后再试或联系管理员') from None


def _receipt(row, *, submission=False):
    # A receipt confirms collection, never a fix, deployment, or model outcome.
    result = {'id': row['id'], 'created_at': row['created_at'], 'status': 'received'}
    if submission:
        result['duplicate'] = bool(row.get('duplicate', False))
    else:
        result['title'] = row['title']
    return result


@router.get('')
def index(db: Session = Depends(get_db), user=Depends(get_user)):
    store_id = single_store(db)
    try:
        rows = _store().receipts(owner_id=user.id, store_id=store_id, limit=20)
        return {'items': [_receipt(row) for row in rows]}
    except (RuntimeError, sqlite3.Error, OSError):
        raise HTTPException(503, '意见收集暂时不可用，请稍后再试或联系管理员') from None


@router.post('', status_code=201)
def submit(body: FeedbackInput, db: Session = Depends(get_db), user=Depends(get_user)):
    store_id = single_store(db)
    try:
        row = _store().submit(owner_id=user.id, store_id=store_id, title=body.title,
                              description=body.description, category=body.category,
                              request_id=body.request_id, route=body.route)
        return _receipt(row, submission=True)
    except ValueError:
        raise HTTPException(409, '此请求编号已提交过其他内容，请先核对本人提交回执') from None
    except (RuntimeError, sqlite3.Error, OSError):
        raise HTTPException(503, '意见收集暂时不可用，请稍后再试或联系管理员') from None
