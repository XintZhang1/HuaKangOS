"""评审申请接口：员工提交、上级查看与处理。不改变权限，也不执行业务动作。"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from .db import get_db
from .escalation_service import act, create, listing
from .master_data import Strict
from .security import get_user

router = APIRouter(prefix='/api/escalations', tags=['评审申请'])


class CreateInput(Strict):
    subject: str = Field(min_length=5, max_length=160)
    case_reference: str = Field(default='', max_length=80)
    operation_id: str = Field(default='', max_length=200)
    blocked_message: str = Field(min_length=8, max_length=2000)
    reason_category: Literal['authority', 'amount', 'rule']


class ActionInput(Strict):
    version: int = Field(gt=0, strict=True)
    note: str = Field(default='', max_length=1000)


@router.get('')
def index(scope: Literal['mine', 'to_review'] = Query('mine'), status: str = Query(''),
          db: Session = Depends(get_db), user=Depends(get_user)):
    return listing(db, user, scope=scope, status=status)


@router.post('', status_code=201)
def submit(body: CreateInput, db: Session = Depends(get_db), user=Depends(get_user)):
    return create(db, user, body)


@router.post('/{escalation_id}/actions/{action}')
def command(escalation_id: int, action: Literal['claim', 'done', 'reject', 'cancel'], body: ActionInput,
            db: Session = Depends(get_db), user=Depends(get_user)):
    return act(db, user, escalation_id, action, body.version, body.note)
