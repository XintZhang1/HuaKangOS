"""Shared presentation helpers; all queries retain the caller's tenant scope."""
from datetime import timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from .config import settings
from .db import today, utcnow

READ_ROLES = {'admin', 'manager', 'finance', 'auditor', 'inventory'}
MONEY_ROLES = {'admin', 'manager', 'finance', 'auditor'}
LIMIT = 25000


def period(user, start, end):
    if user.role not in READ_ROLES:
        raise HTTPException(403, '当前岗位不能查询库存与采购报表')
    end = end or today()
    start = start or end.replace(day=1)
    if start > end: raise HTTPException(422, '开始日期不能晚于结束日期，请修改后重新查询')
    if end > today(): raise HTTPException(422, '结束日期不能晚于今天，请修改后重新查询')
    if (end-start).days > 365: raise HTTPException(422, '查询期间跨度不能超过一年，请缩小期间')
    return start, end


def bounded(db, model, stmt=None):
    rows = list(db.scalars((stmt if stmt is not None else select(model)).limit(LIMIT+1)))
    if len(rows) > LIMIT:
        raise HTTPException(422, '相关来源超过报表上限，本次未返回截断统计；请缩小查询范围')
    return rows


def local_date(stamp):
    return stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()


def yuan(value):
    return '—' if value is None else format(Decimal(value)/100, '.2f')


def qty(value):
    return format(Decimal(value)/1000, 'f')


def as_of():
    return utcnow().isoformat()+'Z'


def route(db, case_id):
    return None if db.info.get('aggregate_scope') or len([i for i in db.info.get('store_scope', ()) if i]) > 1 else {'type': 'case', 'id': case_id}


def table(title, headers):
    return {'title': title, 'headers': headers, 'rows': []}
