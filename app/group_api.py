"""Authenticated explicit commands for shared identity and group principal wallets."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .db import get_db
from .security import get_user
from . import group_service as service

router = APIRouter(prefix='/api/group', tags=['集团身份与会员'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Request(Strict):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')


class LinkInput(Request):
    kind: Literal['customer', 'vehicle', 'counterparty']
    local_id: int = Field(gt=0, strict=True)
    identity_id: int | None = Field(default=None, gt=0, strict=True)
    identifier: str = Field(default='', max_length=100)


class IssueInput(Request):
    identity_id: int = Field(gt=0, strict=True)


class CommandInput(Request):
    version: int = Field(gt=0, strict=True)
    values: dict


class Amount(Strict):
    amount_cents: int = Field(gt=0, le=100_000_000_000, strict=True)


class CaseVersion(Strict):
    case_version: int = Field(gt=0, strict=True)


class Evidence(Strict):
    evidence_id: int = Field(gt=0, strict=True)


class Cash(Strict):
    account_id: int = Field(gt=0, strict=True)
    reference: str = Field(min_length=1, max_length=100)


class Reserve(Amount, CaseVersion, Evidence):
    case_id: int = Field(gt=0, strict=True)


class Topup(Reserve, Cash):
    pass


class Reservation(CaseVersion):
    reservation_id: int = Field(gt=0, strict=True)
    reservation_version: int = Field(gt=0, strict=True)


class Capture(Reservation, Evidence):
    pass


class Release(Reservation):
    reason: str = Field(min_length=2, max_length=500)


class Reverse(Amount, CaseVersion, Evidence):
    original_id: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=2, max_length=500)


class RefundRequest(Reverse):
    pass


class RefundReference(CaseVersion):
    refund_request_id: int = Field(gt=0, strict=True)
    refund_request_version: int = Field(gt=0, strict=True)


class RefundReview(RefundReference):
    reason: str = Field(min_length=2, max_length=500)


class Refund(RefundReference, Cash, Evidence):
    pass


ACTION_INPUTS = {'topup': Topup, 'reserve': Reserve, 'capture': Capture,
                 'release': Release, 'refund': Refund, 'reverse': Reverse,
                 'refund_request': RefundRequest, 'refund_approve': RefundReview,
                 'refund_reject': RefundReview, 'refund_cancel': RefundReview}


@router.get('/identities')
def identities(kind: str, q: str = Query(min_length=1, max_length=100), db=Depends(get_db), user=Depends(get_user)):
    return service.search_identities(db, user, kind, q)


@router.post('/identities/link', status_code=201)
def link_identity(body: LinkInput, db=Depends(get_db), user=Depends(get_user)):
    return service.link_identity(db, user, **body.model_dump())


@router.post('/members', status_code=201)
def issue_member(body: IssueInput, db=Depends(get_db), user=Depends(get_user)):
    return service.issue_member(db, user, **body.model_dump())


@router.get('/members')
def member_lookup(customer_id: int = Query(gt=0), db=Depends(get_db), user=Depends(get_user)):
    return service.member_for_customer(db, user, customer_id)


@router.get('/members/{member_id}')
def member_detail(member_id: int, db=Depends(get_db), user=Depends(get_user)):
    return service.member_detail(db, user, member_id)


@router.post('/members/{member_id}/actions/{action}')
def member_action(member_id: int, action: str, body: CommandInput, db=Depends(get_db), user=Depends(get_user)):
    schema = ACTION_INPUTS.get(action)
    if schema is None:
        raise HTTPException(404, '集团会员动作不存在')
    try:
        values = schema.model_validate(body.values).model_dump()
    except ValidationError as error:
        fields = '、'.join('.'.join(str(x) for x in issue['loc']) for issue in error.errors())
        raise HTTPException(422, '集团会员办理字段无效，请核对：'+fields+'；金额使用整数分')
    return service.member_command(db, user, member_id, body.request_id, body.version, action, values)


@router.get('/reconciliation')
def reconciliation(db=Depends(get_db), user=Depends(get_user)):
    return service.reconciliation(db, user)
