"""One employee-confirmed redemption per frozen gift unit, with append-only undo."""
from collections import Counter
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from .db import get_db, get_write_db, today, utcnow
from .security import get_user
from .services import audit
from .models import User
from .business_records_schemas import Action
from .business_record_benefit_models import RecordBenefitRedemption
from .business_record_delivery_models import RecordReturn

router = APIRouter(prefix='/api/business-records', tags=['赠送保养与项目兑换'])
READERS = {'finance', 'admin', 'clerk', 'general_manager', 'group_deputy_manager', 'chairman', 'store_admin'}


class RedeemBenefit(Action):
    source_key: str = Field(min_length=1, max_length=80)
    redeemed_on: date
    confirmed: Literal[True]


def _access(user, write=False):
    if getattr(user, '_aggregate_scope', False) or user.role not in ({'finance', 'admin'} if write else READERS):
        raise HTTPException(403, '赠送项目兑换由本店财务核对办理')


def _sources(db, contract):
    from .business_record_corrections import latest_correction, effective_snapshot
    revision = latest_correction(db, contract)
    snapshot = effective_snapshot(db, contract) or {}
    terms = snapshot.get('terms') or {}
    benefits = terms.get('submission_data') or {}
    sources = []
    if benefits.get('first_service_count') == 1:
        sources.append({'key': 'first_service', 'name': '免费首保', 'total': 1, 'unit': '次'})
    if benefits.get('nps_participation') is True:
        sources.append({'key': 'nps', 'name': 'NPS调研赠送保养（请核对参与条件）', 'total': 1, 'unit': '次'})
    # Staff choose the actual frozen item; no maintenance/name/amount guessing.
    for gift in terms.get('gifts_snapshot') or []:
        ident, quantity = gift.get('price_id'), gift.get('quantity')
        if type(ident) is int and ident > 0 and type(quantity) is int and quantity > 0:
            sources.append({'key': 'gift:' + str(ident), 'name': gift.get('name') or '合同赠品',
                            'total': quantity, 'unit': gift.get('unit') or '份'})
    for item in sources:
        item['correction_id'] = revision.id if revision else None
    return sources


def _events(db, contract):
    return list(db.scalars(select(RecordBenefitRedemption).where(
        RecordBenefitRedemption.contract_id == contract.id,
        RecordBenefitRedemption.store_id == contract.store_id).order_by(RecordBenefitRedemption.id)))


def _returned(db, contract):
    return db.scalar(select(RecordReturn.id).where(RecordReturn.contract_id == contract.id,
        RecordReturn.store_id == contract.store_id, RecordReturn.status == 'approved')) is not None


def _state(db, user, contract):
    events = _events(db, contract)
    used = Counter()
    for event in events:
        used[event.source_key] += event.quantity
    sources = _sources(db, contract)
    for source in sources:
        source.update(used=used[source['key']], remaining=max(0, source['total'] - used[source['key']]))
    names = dict(db.execute(select(User.id, User.display_name).where(User.id.in_({e.created_by for e in events}))).all())
    reversed_ids = {e.reverses_id for e in events if e.reverses_id}
    writable = user.role in {'finance', 'admin'}
    return {'contract_id': contract.id, 'version': contract.version, 'items': sources,
        'can_redeem': writable and contract.status == 'approved' and not contract.archived_at and not _returned(db, contract),
        'history': [{'id': e.id, 'source_key': e.source_key, 'name': e.source_snapshot['name'],
            'quantity': e.quantity, 'unit': e.source_snapshot['unit'], 'redeemed_on': e.redeemed_on.isoformat(),
            'created_by_name': names.get(e.created_by, ''), 'created_at': e.created_at.isoformat(),
            'note': e.note, 'reverses_id': e.reverses_id,
            'can_reverse': writable and e.quantity == 1 and e.id not in reversed_ids} for e in events]}


@router.get('/contracts/{key}/benefits')
def benefits(key: int, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_privacy import redact_contract_data
    _access(user)
    contract = get_contract(db, user, key)
    return redact_contract_data(db, user, contract, _state(db, user, contract))


@router.post('/contracts/{key}/benefits/redeem')
def redeem(key: int, body: RedeemBenefit, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _check_version, _run, _body
    _access(user, True)
    _manual(request)
    contract = get_contract(db, user, key)
    def perform():
        _check_version(contract, body.version)
        if contract.status != 'approved' or contract.archived_at or _returned(db, contract):
            raise HTTPException(409, '仅有效的已批准合同可兑换；已退车或作废合同不能继续兑换')
        if body.redeemed_on > today() or body.redeemed_on < contract.contract_date:
            raise HTTPException(422, '兑换日期须在合同日期至今天之间')
        source = next((item for item in _state(db, user, contract)['items'] if item['key'] == body.source_key), None)
        if source is None or source['remaining'] < 1:
            raise HTTPException(409, '本合同未赠送此项目或已兑换完毕，请核对最新权益')
        db.add(RecordBenefitRedemption(store_id=contract.store_id, contract_id=key,
            source_key=source['key'], source_snapshot={k: source[k] for k in ('name', 'unit', 'total', 'correction_id')},
            quantity=1, redeemed_on=body.redeemed_on, note=body.note, created_by=user.id))
        # Versioned contract write serializes concurrent use of the last unit;
        # the approved contract JSON and its prices/entitlements are untouched.
        contract.updated_at = utcnow()
        db.flush()
        audit(db, user.id, 'record_benefit_redeem', 'record_contract', key,
              after={'source_key': source['key'], 'quantity': 1}, reason=body.note)
        return _state(db, user, contract)
    return _run(db, user, body.request_id, f'contract:{key}:benefit_redeem', _body(body), perform)


@router.post('/contracts/{key}/benefits/{event_id}/reverse')
def reverse(key: int, event_id: int, body: Action, request: Request,
            db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _check_version, _run, _body
    _access(user, True)
    _manual(request)
    contract = get_contract(db, user, key)
    def perform():
        _check_version(contract, body.version)
        if not body.note.strip():
            raise HTTPException(422, '请填写误录撤销原因')
        events = _events(db, contract)
        original = next((e for e in events if e.id == event_id and e.quantity == 1), None)
        if original is None or any(e.reverses_id == event_id for e in events):
            raise HTTPException(409, '兑换记录不存在或已撤销，请刷新核对')
        db.add(RecordBenefitRedemption(store_id=contract.store_id, contract_id=key,
            source_key=original.source_key, source_snapshot=original.source_snapshot, quantity=-1,
            reverses_id=original.id, redeemed_on=today(), note=body.note, created_by=user.id))
        contract.updated_at = utcnow()
        db.flush()
        audit(db, user.id, 'record_benefit_reverse', 'record_contract', key,
              after={'reverses_id': event_id, 'quantity': -1}, reason=body.note)
        return _state(db, user, contract)
    return _run(db, user, body.request_id, f'contract:{key}:benefit_reverse:{event_id}', _body(body), perform)
