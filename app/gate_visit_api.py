"""Strict, scoped commands. Client state, money and inventory fields are rejected."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import Field, field_validator, model_validator
from .db import get_db,get_write_db
from .security import get_user
from .service_intake_api import Strict, Request, Command, Reason, Evidence, Slot, Arrival, values
from . import gate_visit_service as service

router = APIRouter(prefix='/api/gate-visits', tags=['实际非维修进出厂'])


class VisitCreate(Request):
    customer_vehicle_id: int = Field(gt=0, strict=True)
    purpose: Literal['consultation', 'inspection', 'accessory', 'delivery', 'other']
    description: str = Field(min_length=2, max_length=1000)


class Actual(Reason, Evidence):
    confirmed: bool = Field(strict=True)
    checked_vin: str = Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    actual_at: datetime

    @field_validator('confirmed')
    @classmethod
    def confirmed_fact(cls, value):
        if value is not True:
            raise ValueError('须明确确认本次实际发生的进出厂')
        return value

    @field_validator('checked_vin', mode='before')
    @classmethod
    def vin(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator('actual_at')
    @classmethod
    def time_zone(cls, value):
        if value.tzinfo is None or value.astimezone(timezone.utc).year < 2000:
            raise ValueError('实际时间须带时区且不早于2000年')
        return value


class Handoff(Slot, Arrival):
    problem: str = Field(min_length=2, max_length=1000)


class Correction(Reason, Evidence):
    kind: Literal['arrive_time', 'leave_time', 'void_visit']
    actual_at: datetime | None = None

    @model_validator(mode='after')
    def shape(self):
        if (self.kind == 'void_visit') != (self.actual_at is None):
            raise ValueError('撤销错误登记不带新时间；原时间纠正必须明确填写新时间')
        if self.actual_at is not None:
            Actual.time_zone(self.actual_at)
        return self


class Review(Reason, Evidence):
    pass


@router.get('/catalog')
def catalog(db=Depends(get_db), user=Depends(get_user)):
    return service.catalog(db, user)


@router.get('')
def listing(page: int = Query(1, ge=1), status: Literal['planned','inside','departed','cancelled','voided','handed_over'] | None = None, db=Depends(get_db), user=Depends(get_user)):
    return service.listing(db, user, page, status)


@router.post('', status_code=201)
def create(body: VisitCreate, db=Depends(get_write_db), user=Depends(get_user)):
    return service.create(db, user, body.request_id, body.model_dump(exclude={'request_id'}))


@router.get('/{key}')
def detail(key: int, db=Depends(get_db), user=Depends(get_user)):
    return service.detail(db, user, key)


@router.post('/{key}/actions/{action}')
def command(key: int, action: Literal['arrive','leave','cancel','handoff'], body: Command, db=Depends(get_write_db), user=Depends(get_user)):
    schema = Handoff if action == 'handoff' else Reason if action == 'cancel' else Actual
    return service.command(db, user, key, body.request_id, body.version, action, values(schema, body.values))


@router.post('/{key}/corrections')
def correct(key: int, body: Command, db=Depends(get_write_db), user=Depends(get_user)):
    return service.correct(db, user, key, body.request_id, body.version, values(Correction, body.values))


@router.post('/corrections/{key}/actions/{action}')
def review(key: int, action: Literal['approve','reject','cancel'], body: Command, db=Depends(get_write_db), user=Depends(get_user)):
    return service.review(db, user, key, body.request_id, body.version, action, values(Reason if action == 'cancel' else Review, body.values))


@router.post('/repair-orders/{key}/departure')
def repair_exit(key: int, body: Command, db=Depends(get_write_db), user=Depends(get_user)):
    return service.cancelled_repair_exit(db, user, key, body.request_id, body.version, values(Actual, body.values))
