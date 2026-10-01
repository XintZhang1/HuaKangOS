"""Explicit actions on original vehicle transfers; never raw status or ledger writes."""
from datetime import date, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from .db import get_db,get_write_db
from .security import get_user
from . import vehicle_transport_service as service

router = APIRouter(prefix='/api/vehicle-transport-exceptions', tags=['整车运输差异与原车找回'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Request(Strict):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')


class Create(Request):
    transfer_id: int = Field(gt=0, strict=True)
    version: int = Field(gt=0, strict=True)
    case_version: int = Field(gt=0, strict=True)
    kind: Literal['missing', 'vin_mismatch', 'damage']
    evidence_id: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=4, max_length=1000)


class Command(Request):
    version: int = Field(gt=0, strict=True)
    case_version: int = Field(gt=0, strict=True)
    exception_version: int = Field(gt=0, strict=True)
    values: dict


class Proof(Strict):
    evidence_id: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=4, max_length=1000)


class Confirmation(Proof):
    confirmed: bool = Field(strict=True)
    @field_validator('confirmed')
    @classmethod
    def must_be_confirmed(cls, value):
        if value is not True: raise ValueError('须本人明确确认已实际发生')
        return value


class Physical(Confirmation):
    vin: str = Field(min_length=17, max_length=17, pattern=r'^[A-HJ-NPR-Za-hj-npr-z0-9]{17}$')


class Observation(Physical):
    kind: Literal['dispatch_verified', 'not_located', 'original_seen', 'unusable_held', 'other_vin_seen']
    actual_at: datetime


class FoundObservation(Physical):
    actual_at: datetime


class LossPlan(Proof):
    loss_method: Literal['missing', 'destroyed']
    source_bearer_cents: int = Field(ge=0, le=1_000_000_000_000, strict=True)
    destination_bearer_cents: int = Field(ge=0, le=1_000_000_000_000, strict=True)


class FoundPlan(Proof):
    found_observation_id: int = Field(gt=0, strict=True)


class Review(Proof):
    plan_id: int = Field(gt=0, strict=True)


class FoundUnavailable(Physical):
    kind: Literal['missing_again', 'not_usable']


class FoundReceive(Physical):
    location_id: int = Field(gt=0, strict=True)


class ClaimTarget(Proof):
    target_cents: int = Field(ge=0, le=1_000_000_000_000, strict=True)
    due_date: date


class ClaimCreate(ClaimTarget):
    counterparty_kind: Literal['carrier', 'insurer']
    counterparty_id: int = Field(gt=0, strict=True)


class ClaimKey(Proof):
    claim_id: int = Field(gt=0, strict=True)
    claim_version: int = Field(gt=0, strict=True)


class ClaimPlan(ClaimKey, ClaimTarget): pass


class ClaimReview(ClaimKey):
    plan_id: int = Field(gt=0, strict=True)


class ClaimCash(ClaimKey, Confirmation):
    amount_cents: int = Field(gt=0, le=1_000_000_000_000, strict=True)
    account_id: int = Field(gt=0, strict=True)
    reference: str = Field(min_length=2, max_length=100)
    business_date: date


class ClaimRefund(ClaimCash):
    original_id: int = Field(gt=0, strict=True)


SCHEMAS = {'observe': Observation, 'observe_found': FoundObservation, 'plan_resume': Proof, 'plan_loss': LossPlan,
    'plan_found': FoundPlan, 'approve': Review, 'reject': Review, 'withdraw': Review, 'post_loss': Confirmation,
    'dispose': Physical, 'found_receive': FoundReceive, 'found_unavailable': FoundUnavailable, 'recovery_create': ClaimCreate, 'recovery_plan': ClaimPlan,
    'recovery_approve': ClaimReview, 'recovery_reject': ClaimReview, 'recovery_cancel': ClaimReview,
    'recovery_receive': ClaimCash, 'recovery_refund': ClaimRefund}


@router.post('', status_code=201)
def create(body: Create, db=Depends(get_write_db), user=Depends(get_user)):
    return service.create(db, user, **body.model_dump())


@router.get('/{key}')
def detail(key: int, db=Depends(get_db), user=Depends(get_user)):
    return service.detail(db, user, key)


@router.post('/{key}/actions/{action}')
def command(key: int, action: str, body: Command, db=Depends(get_write_db), user=Depends(get_user)):
    schema = SCHEMAS.get(action)
    if schema is None: raise HTTPException(404, '原整车差异动作不存在')
    try: values = schema.model_validate(body.values).model_dump()
    except ValidationError: raise HTTPException(422, '请核对原VIN、实际确认、凭据与明确金额；不接受额外状态或账务字段')
    return service.command(db, user, key, body.request_id, body.version, body.case_version, body.exception_version, action, values)
