"""Paid accessory evidence and clerk verification of frozen contract line items."""
import hashlib
from types import SimpleNamespace
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from .db import get_db, get_write_db, utcnow
from .security import get_user
from .services import audit
from .business_records_schemas import Command
from .business_record_pricing_models import RecordContractTerms, RecordPricingFile

router = APIRouter(prefix='/api/business-records', tags=['有偿精品凭证与核实'])
VERIFICATION_VERSION = 'v219-actual-paid-accessory-cost'
READERS = {'admin', 'finance', 'clerk', 'general_manager', 'group_deputy_manager', 'chairman', 'store_admin'}


def frozen_accessory_totals(terms):
    """Only paid selections contribute; gift selections are deliberately absent."""
    submission = terms.submission_data or {} if terms is not None else {}
    if 'accessory_snapshot' not in submission:
        return {'status': 'missing_snapshot', 'items': [], 'income_cents': None, 'cost_cents': None}
    items = submission['accessory_snapshot']
    if not isinstance(items, list):
        raise ValueError('有偿精品冻结明细格式不正确')
    income, cost, missing_cost = 0, 0, False
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('有偿精品冻结明细格式不正确')
        quantity, unit_price, amount = (item.get(name) for name in ('quantity', 'unit_price_cents', 'amount_cents'))
        if (any(type(value) is not int for value in (quantity, unit_price, amount))
                or quantity <= 0 or unit_price < 0 or amount != quantity * unit_price):
            raise ValueError('有偿精品冻结数量或售价不一致，请核对原合同')
        income += amount
        unit_cost, item_cost = item.get('unit_cost_cents'), item.get('cost_cents')
        if unit_cost is None or item_cost is None:
            missing_cost = True
        elif (type(unit_cost) is not int or type(item_cost) is not int or unit_cost < 0
                or item_cost != unit_cost * quantity):
            raise ValueError('有偿精品冻结成本不一致，请核对原合同')
        else:
            cost += item_cost
    if submission.get('accessory_total_cents') != income:
        raise ValueError('有偿精品冻结售价合计不一致，请核对原合同')
    if max(income, cost) > 999999999999:
        raise ValueError('有偿精品金额超出可记录范围')
    return {'status': 'no_paid_items' if not items else 'missing_cost' if missing_cost else 'ready',
            'items': items, 'income_cents': income, 'cost_cents': None if missing_cost else cost}


def effective_terms(db, contract):
    """A new office review follows the approved revision, not mutable catalog data."""
    from .business_record_corrections import latest_correction
    revision = latest_correction(db, contract)
    if revision is not None:
        frozen = (revision.approved_snapshot or {}).get('terms')
        if not isinstance(frozen, dict):
            raise ValueError('批准更正缺少冻结交易明细，请核对合同版本')
        return SimpleNamespace(**{**frozen, 'contract_correction_id': revision.id})
    return db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == contract.id,
                                                      RecordContractTerms.store_id == contract.store_id))


def _evidence(db, contract, file_id):
    item = db.scalar(select(RecordPricingFile).where(RecordPricingFile.id == file_id,
        RecordPricingFile.kind == 'accessory_sale', RecordPricingFile.contract_id == contract.id,
        RecordPricingFile.store_id == contract.store_id))
    if item is None:
        raise ValueError('请选择本合同财务上传的有偿精品销售凭证')
    from .business_record_invoices import _content
    _content(item)  # Same structural/scan/private-object checks as original evidence.
    return item


def apply_accessory_verification(db, contract, data, terms):
    """New office saves derive amounts, while old approved JSON stays unchanged."""
    extension = dict(data.get('extension_data') or {})
    source = frozen_accessory_totals(terms)
    actual_cost = extension.get('accessory_sales_actual_cost_cents')
    if actual_cost is not None and source['status'] == 'missing_snapshot':
        raise ValueError('历史合同缺少冻结有偿精品明细，不能由手填成本推定已售精品')
    if source['status'] == 'no_paid_items' and actual_cost not in (None, 0):
        raise ValueError('合同未选择有偿精品，不能仅填写成本；请先按合同更正流程核对有偿精品明细')
    verified = extension.get('accessory_sales_verified') is True
    file_id = extension.get('accessory_sales_file_id')
    evidence = None
    if verified and source['items']:
        evidence = _evidence(db, contract, file_id)
    elif verified and source['status'] == 'missing_snapshot':
        raise ValueError('历史合同缺少冻结有偿精品明细，不能由手填金额推定已售精品')
    ready = source['status'] == 'no_paid_items' or verified and evidence is not None
    extension['accessory_sales_income_cents'] = source['income_cents'] if ready else None
    cost = actual_cost if actual_cost is not None else source['cost_cents']
    extension['accessory_sales_cost_cents'] = cost if ready else None
    data['extension_data'] = extension
    data['contract_correction_id'] = getattr(terms, 'contract_correction_id', None)
    data['accessory_sales_verification'] = {
        'version': VERIFICATION_VERSION,
        'source_status': source['status'],
        'status': ('ready' if source['items'] and cost is not None else source['status']) if ready else 'awaiting_clerk_verification',
        'file_id': evidence.id if evidence else None, 'file_sha256': evidence.sha256 if evidence else None,
        'income_cents': extension['accessory_sales_income_cents'],
        'cost_cents': extension['accessory_sales_cost_cents'],
        'quoted_cost_cents': source['cost_cents'],
        'actual_cost_cents': actual_cost,
        'cost_source': 'clerk_actual' if actual_cost is not None else 'contract_frozen',
        'items': source['items'],
    }
    return data


def validate_accessory_evidence(db, contract, data):
    """Recheck the exact reviewed file before approval, never substitute latest."""
    verification = data.get('accessory_sales_verification') or {}
    if verification.get('version') not in {VERIFICATION_VERSION, 'v218-frozen-paid-accessories'}:
        return
    from .business_record_corrections import latest_correction
    revision = latest_correction(db, contract)
    if data.get('contract_correction_id') != (revision.id if revision else None):
        raise HTTPException(409, '合同交易内容已有批准更正，请退回内勤按最新合同重新核价')
    if verification.get('file_id') is not None:
        try:
            item = _evidence(db, contract, verification['file_id'])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if item.sha256 != verification.get('file_sha256'):
            raise HTTPException(409, '内勤核对的精品凭证已变化，请退回重新核对')


def _read(user):
    if getattr(user, '_aggregate_scope', False) or user.role not in READERS:
        raise HTTPException(403, '有偿精品凭证仅供本店财务、内勤及授权核价岗位查看')


@router.get('/contracts/{key}/accessory-sales')
def accessory_sales_state(key: int, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_pricing import _file_summary, GIFT_COST_READERS
    _read(user)
    contract = get_contract(db, user, key)
    try:
        source = frozen_accessory_totals(effective_terms(db, contract))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    files = list(db.scalars(select(RecordPricingFile).where(RecordPricingFile.contract_id == key,
        RecordPricingFile.store_id == contract.store_id, RecordPricingFile.kind == 'accessory_sale')
        .order_by(RecordPricingFile.id.desc())))
    source['files'] = [_file_summary(item) for item in files]
    from .business_record_privacy import contract_privacy
    if contract_privacy(db, user, contract)['masked']:
        for item in source['files']:
            item['available'] = False
    source['can_upload'] = user.role in {'finance', 'admin'} and contract.status == 'approved'
    if user.role not in GIFT_COST_READERS:
        source.pop('cost_cents', None)
        source['items'] = [{name: value for name, value in item.items()
                            if name not in {'unit_cost_cents', 'cost_cents', 'source_ref'}} for item in source['items']]
    from .business_record_privacy import redact_contract_data
    return redact_contract_data(db, user, contract, source)


@router.post('/contracts/{key}/accessory-sales/files', status_code=201)
def upload_accessory_sale(key: int, request: Request, file: UploadFile = File(...),
        request_id: str = Form(...), version: int = Form(...), db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    from .business_record_pricing import _save_file, _file_summary
    from .flow_documents import validate_upload
    _manual(request); _read(user); Command(request_id=request_id)
    if user.role not in {'finance', 'admin'}:
        raise HTTPException(403, '有偿精品销售凭证由财务上传')
    contract = get_contract(db, user, key)
    content = file.file.read(10 * 1024 * 1024 + 1)
    filename = file.filename or ''
    media = validate_upload(filename, content)
    if media not in {'application/pdf', 'image/png', 'image/jpeg'}:
        raise HTTPException(422, '有偿精品销售凭证支持 PDF、PNG、JPEG，最多 10 MB')
    def perform():
        _check_version(contract, version)
        if contract.status != 'approved' or contract.workflow_version != 'trial-v210':
            raise HTTPException(409, '请在新版合同批准后上传有偿精品销售凭证')
        try:
            source = frozen_accessory_totals(effective_terms(db, contract))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        if not source['items']:
            raise HTTPException(409, '本合同没有明确冻结的有偿精品项目')
        item = _save_file(db, user, 'accessory_sale', filename, content, media, contract.id)
        contract.updated_at = utcnow(); db.flush()
        result = _file_summary(item) | {'contract_version': contract.version}
        audit(db, user.id, 'record_accessory_sale_upload', 'record_contract', key,
              after={'file_id': item.id, 'sha256': item.sha256, 'store_id': contract.store_id})
        return result
    return _run(db, user, request_id, 'contract:accessory_sale',
        {'contract_id': key, 'version': version, 'filename': filename,
         'sha256': hashlib.sha256(content).hexdigest()}, perform)


@router.get('/contracts/{key}/accessory-sales/files/{file_id}/download')
def download_accessory_sale(key: int, file_id: int, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_invoices import _content
    _read(user)
    contract = get_contract(db, user, key)
    from .business_record_privacy import require_personal_export
    require_personal_export(db, user, contract)
    try:
        item = _evidence(db, contract, file_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response(_content(item), media_type=item.content_type,
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(item.filename), 'Cache-Control': 'no-store'})
