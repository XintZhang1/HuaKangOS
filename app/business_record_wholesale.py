"""Real wholesale channels and frozen contract attribution, separate from retail."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from .db import get_db, get_write_db, utcnow
from .security import get_user
from .tenancy import single_store
from .services import plain, audit
from .business_records_models import RecordWholesaleChannel
from .business_records_schemas import Command

router = APIRouter(prefix='/api/business-records', tags=['二级批发渠道'])


class ChannelInput(Command):
    name: str = Field(min_length=1, max_length=160)
    active: bool = Field(default=True, strict=True)
    version: int = Field(default=0, ge=0, strict=True)


def _access(user, write=False):
    from .business_records import require_read
    require_read(user)
    if getattr(user, '_aggregate_scope', False) or user.role == 'sales':
        raise HTTPException(403, '请由本店销售经理维护二级批发渠道')
    if write and user.role not in {'admin', 'manager', 'general_manager', 'group_deputy_manager'}:
        raise HTTPException(403, '二级批发渠道由销售经理、总经理或集团副总经理维护')


@router.get('/wholesale-channels')
def channels(db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    return {'items': [plain(row) for row in db.scalars(select(RecordWholesaleChannel)
        .order_by(RecordWholesaleChannel.name, RecordWholesaleChannel.id))],
        'can_manage': user.role in {'admin', 'manager', 'general_manager', 'group_deputy_manager'}}


def _save(key, body, request, db, user):
    from .business_records import _manual, _run, _body, _check_version, _lock_customer_scope
    _manual(request); _access(user, True)
    def perform():
        _lock_customer_scope(db)
        row = db.get(RecordWholesaleChannel, key) if key else None
        if key and row is None:
            raise HTTPException(404, '渠道不存在或不属于当前门店')
        if row:
            _check_version(row, body.version)
        elif body.version != 0:
            raise HTTPException(409, '新建渠道版本不正确')
        duplicate = db.scalar(select(RecordWholesaleChannel).where(RecordWholesaleChannel.name == body.name))
        if duplicate and (row is None or row.id != duplicate.id):
            raise HTTPException(409, '本店已有同名渠道，请使用原渠道或修改名称')
        before = plain(row) if row else None
        if row is None:
            row = RecordWholesaleChannel(store_id=single_store(db), created_by=user.id, name=body.name)
            db.add(row)
        row.name, row.active, row.updated_at = body.name, body.active, utcnow()
        db.flush()
        result = plain(row)
        audit(db, user.id, 'record_wholesale_channel', 'record_wholesale_channel', row.id, before, result)
        return result
    return _run(db, user, body.request_id, f'wholesale-channel:{key or "new"}', _body(body), perform)


@router.post('/wholesale-channels', status_code=201)
def create_channel(body: ChannelInput, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _save(None, body, request, db, user)


@router.put('/wholesale-channels/{key}')
def edit_channel(key: int, body: ChannelInput, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _save(key, body, request, db, user)


def submission_channel(db, user, submission, prior=None):
    channel = submission.sales_channel
    if prior:
        previous = prior.submission_data
        if channel != previous.get('sales_channel', 'retail') or submission.wholesale_channel_id != previous.get('wholesale_channel_id'):
            raise HTTPException(409, '已提交合同的展厅或二级渠道归属已冻结；变更请新建合同')
        return {key: previous[key] for key in ('sales_channel', 'wholesale_channel_id', 'wholesale_channel_name') if key in previous}
    if channel == 'retail':
        if submission.wholesale_channel_id is not None:
            raise HTTPException(422, '展厅合同不能关联二级批发渠道')
        return {'sales_channel': 'retail'}
    _access(user, True)
    row = db.get(RecordWholesaleChannel, submission.wholesale_channel_id) if submission.wholesale_channel_id else None
    if row is None or not row.active:
        raise HTTPException(422, '请选择本店已维护且启用的真实二级批发渠道')
    return {'sales_channel': 'wholesale', 'wholesale_channel_id': row.id, 'wholesale_channel_name': row.name}


def is_wholesale(db, contract):
    from .business_record_pricing import get_terms
    terms = get_terms(db, contract)
    return bool(terms and terms.submission_data.get('sales_channel') == 'wholesale')
