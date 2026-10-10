"""Manager-issued monthly targets, stored as append-only report sources.

Targets use their own entry mode so a clerk's cumulative actuals cannot replace
them. No business facts or previously approved records are updated here.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from .db import get_db, get_write_db
from .models import Store, User
from .security import get_user
from .services import audit
from .tenancy import single_store
from .business_records_models import ManualReportRecord
from .business_records_schemas import Command, Key, Money

router = APIRouter(prefix='/api/business-records', tags=['月度目标'])
TARGET_ROLES = frozenset({'admin', 'manager', 'general_manager', 'chairman', 'group_deputy_manager'})
TargetCount = Annotated[int, Field(ge=0, le=999999999, strict=True)]


def month_date(month):
    try:
        return date.fromisoformat(month + '-01')
    except (TypeError, ValueError):
        raise ValueError('请选择有效月份（YYYY-MM）。') from None


class MonthlyTargetInput(Command):
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    brand: str = Field(default='', max_length=100)
    series: str = Field(min_length=1, max_length=100)
    sales_units: TargetCount | Literal['/'] | None = None
    mechanical_cents: Money | Literal['/'] | None = None
    accident_cents: Money | Literal['/'] | None = None
    after_sales_cents: Money | Literal['/'] | None = None
    supersedes_id: Key | None = None
    supersedes_version: Key | None = None
    note: str = Field(default='', max_length=2000)

    @field_validator('month')
    @classmethod
    def valid_month(cls, value):
        month_date(value)
        return value

    @model_validator(mode='after')
    def complete_revision(self):
        if (self.supersedes_id is None) != (self.supersedes_version is None):
            raise ValueError('修订时须同时提供原目标及其版本。')
        return self


def can_manage_targets(user):
    return not getattr(user, '_aggregate_scope', False) and user.role in TARGET_ROLES


def _query(user, history=False):
    from .business_records import visible_query
    from .business_record_report_specs import assert_report_access
    assert_report_access(user, 'sales_targets')
    query = visible_query(user, ManualReportRecord).where(
        ManualReportRecord.report_key == 'sales_targets', ManualReportRecord.entry_mode == 'target')
    if not history:
        successor = aliased(ManualReportRecord)
        query = query.where(~select(successor.id).where(
            successor.store_id == ManualReportRecord.store_id,
            successor.supersedes_id == ManualReportRecord.id).exists())
    return query


def _amount(value, money=False):
    if value is None or value == '/':
        return value
    return int(Decimal(str(value)) * (100 if money else 1))


def target_data(row, *, current=True):
    values = row.values
    return {'id': row.id, 'version': row.version, 'store_id': row.store_id,
        'month': str(row.period)[:7], 'brand': row.brand, 'series': values.get('c01', ''),
        'sales_units': _amount(values.get('c02')),
        'mechanical_cents': _amount(values.get('c03'), True),
        'accident_cents': _amount(values.get('c04'), True),
        'after_sales_cents': _amount(values.get('c05'), True),
        'supersedes_id': row.supersedes_id, 'is_current': current, 'note': row.note,
        'created_by': row.created_by, 'created_at': row.created_at.isoformat()}


def target_values(body):
    def amount(value):
        return value if value is None or value == '/' else format(Decimal(value) / 100, '.2f')
    return {'c01': body.series,
        'c02': body.sales_units if body.sales_units in (None, '/') else str(body.sales_units),
        'c03': amount(body.mechanical_cents), 'c04': amount(body.accident_cents),
        'c05': amount(body.after_sales_cents)}


@router.get('/monthly-targets')
def monthly_targets(month: str = Query(..., pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),
                    include_history: bool = False, db=Depends(get_db), user=Depends(get_user)):
    try:
        period = month_date(month)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    rows = list(db.scalars(_query(user, include_history).where(
        ManualReportRecord.period == period).order_by(ManualReportRecord.brand, ManualReportRecord.id)))
    ids = {row.id for row in rows}
    retired = set(db.scalars(select(ManualReportRecord.supersedes_id).where(
        ManualReportRecord.supersedes_id.in_(ids)))) if ids else set()
    stores = {row.id: row.name for row in db.scalars(select(Store).where(Store.id.in_({r.store_id for r in rows})))}
    issuers = {row.id: row.display_name for row in db.scalars(select(User).where(User.id.in_({r.created_by for r in rows})))}
    return {'month': month, 'can_write': can_manage_targets(user), 'items': [
        dict(target_data(row, current=row.id not in retired), store=stores.get(row.store_id, ''),
             issued_by=issuers.get(row.created_by, ''), can_correct=can_manage_targets(user) and row.id not in retired)
        for row in rows], 'notice': '每个门店、月份、品牌和系列只采用当前目标。空白表示未知，/ 表示不适用，两者均不按零统计；明确填写 0 才表示零目标。售后合计按管理者下达的总目标填写，不从未知分项推算。'}


@router.post('/monthly-targets', status_code=201)
def issue_monthly_target(body: MonthlyTargetInput, request: Request,
                         db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run, _body, _check_version, require_read
    _manual(request)
    require_read(user)
    if not can_manage_targets(user):
        raise HTTPException(403, '月度目标仅由当前门店的管理者人工下达；集团汇总只读。')
    store = single_store(db)
    period = month_date(body.month)
    dimension = [store, body.month, body.brand, body.series]
    source_key = 'monthly-target:' + hashlib.sha256(json.dumps(
        dimension, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

    def perform():
        previous = None
        if body.supersedes_id is not None:
            previous = db.scalar(_query(user, True).where(ManualReportRecord.id == body.supersedes_id))
            if previous is None:
                raise HTTPException(404, '原月度目标不存在或不可访问。')
            _check_version(previous, body.supersedes_version)
            if [previous.store_id, str(previous.period)[:7], previous.brand, previous.values.get('c01')] != dimension:
                raise HTTPException(422, '修订须保留原目标的门店、月份、品牌和系列。')
            if db.scalar(_query(user, True).where(ManualReportRecord.supersedes_id == previous.id)):
                raise HTTPException(409, '月度目标已有新版本，请刷新后打开当前版本。')
        elif db.scalar(_query(user, True).where(ManualReportRecord.source_key == source_key)):
            raise HTTPException(409, '该月份、品牌和系列已有目标，请从当前记录修订。')
        row = ManualReportRecord(store_id=store, report_key='sales_targets', period=period,
            brand=body.brand, salesperson_id=None, values=target_values(body), created_by=user.id,
            entry_mode='target', supersedes_id=body.supersedes_id, supersedes_version=body.supersedes_version,
            source_key=source_key if previous is None else None, note=body.note)
        db.add(row)
        db.flush()
        result = target_data(row)
        audit(db, user.id, 'record_monthly_target_revise' if previous else 'record_monthly_target_issue',
            'record_monthly_target', row.id, before=target_data(previous) if previous else None,
            after=result, reason=body.note)
        return result

    try:
        return _run(db, user, body.request_id, 'monthly_target:issue', _body(body), perform)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '该目标已被其他操作保存或修订，请刷新核对当前版本。') from exc
