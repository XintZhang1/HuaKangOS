"""Cashier-controlled invoice originals and confirmation, independent of receipts."""
import hashlib
import io
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from .config import settings
from .db import get_db, get_write_db, utcnow
from .security import get_user
from .services import plain, audit
from .business_records import get_contract, _manual, _run, _check_version
from .business_records_schemas import Strict, Action, Money, Key
from .business_record_invoice_models import RecordInvoice, RecordInvoiceFile
from .business_record_invoice_recognition import recognize_invoice
from .flow_documents import validate_upload
from .file_security import policy_mode, scan_clamav, MESSAGES
from .private_files import publish, read_object, checked_bytes

router = APIRouter(prefix='/api/business-records', tags=['合同发票'])
INVOICE_ROLES = {'admin', 'finance', 'clerk', 'chairman', 'store_admin'}


class InvoiceFields(Strict):
    invoice_number: str = Field(default='', max_length=100)
    invoice_code: str = Field(default='', max_length=100)
    invoice_type: str = Field(default='', max_length=100)
    issued_on: date | None = None
    buyer_name: str = Field(default='', max_length=200)
    buyer_tax_id: str = Field(default='', max_length=100)
    seller_name: str = Field(default='', max_length=200)
    seller_tax_id: str = Field(default='', max_length=100)
    vin: str = Field(default='', max_length=100)
    vehicle_model: str = Field(default='', max_length=200)
    total_amount_cents: Money | None = None
    tax_amount_cents: Money | None = None
    net_amount_cents: Money | None = None


class InvoiceConfirm(Action):
    fields: InvoiceFields


def _access(user, write=False):
    if user.role not in ({'admin', 'finance'} if write else INVOICE_ROLES):
        raise HTTPException(403, '发票由收银核对处理；当前岗位不能访问此入口')


def _invoice(db, contract_id):
    return db.scalar(select(RecordInvoice).where(RecordInvoice.contract_id == contract_id))


def _file(db, row, file_id=None):
    item = db.scalar(select(RecordInvoiceFile).where(
        RecordInvoiceFile.id == (file_id or row.active_file_id), RecordInvoiceFile.invoice_id == row.id))
    if not item:
        raise HTTPException(404, '发票原件不存在或当前门店不可见')
    return item


def _summary(db, row):
    if row is None:
        return {'invoice': None}
    data = plain(row)
    data.pop('active_file_id', None)
    items = []
    for item in db.scalars(select(RecordInvoiceFile).where(RecordInvoiceFile.invoice_id == row.id).order_by(RecordInvoiceFile.id.desc())):
        info = {key: plain(item)[key] for key in ('id', 'filename', 'content_type', 'size', 'sha256', 'scan_state', 'created_at')}
        info['current'] = item.id == row.active_file_id
        info['available'] = _safe(item)
        items.append(info)
    return {'invoice': data, 'files': items, 'notice': '每合同保留一张当前发票，替换前原件留档；发票确认不会变更到账记录。'}


def _safe(item):
    mode = policy_mode()
    return item.scan_state == 'clean' or (mode == 'structure_only' and item.scan_state == 'structure_only')


def _content(item):
    if not _safe(item):
        raise HTTPException(409, MESSAGES.get(item.scan_code, '发票原件处于隔离状态，请联系管理员检查'))
    try:
        return (read_object(None, item.object_key, item.store_id, item.size, item.sha256)
                if item.object_key else checked_bytes(item.content, item.size, item.sha256))
    except (ValueError, OSError):
        raise HTTPException(409, '发票原件校验失败，请联系管理员核对备份；未使用不完整文件') from None


@router.get('/contracts/{key}/invoice')
def invoice_info(key: int, db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    contract = get_contract(db, user, key)
    return _summary(db, _invoice(db, contract.id))


@router.post('/contracts/{key}/invoice')
def upload_invoice(key: int, request: Request, file: UploadFile = File(...),
                   request_id: str = Form(...), version: int = Form(0),
                   db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request); _access(user, True)
    # Form input gets the same strict command validation as ordinary JSON writes.
    from .business_records_schemas import Command
    Command(request_id=request_id)
    contract = get_contract(db, user, key)
    if contract.status != 'approved':
        raise HTTPException(409, '合同批准后才能上传发票')
    content = file.file.read(10 * 1024 * 1024 + 1)
    filename = file.filename or ''
    media = validate_upload(filename, content)
    if media not in {'application/pdf', 'image/png', 'image/jpeg'}:
        raise HTTPException(422, '发票仅支持PDF、PNG或JPEG，每份最多10MB')
    digest = hashlib.sha256(content).hexdigest()
    payload = {'contract_id': key, 'version': version, 'filename': filename, 'sha256': digest}

    def perform():
        row = _invoice(db, contract.id)
        if row:
            _check_version(row, version)
        elif version != 0:
            raise HTTPException(409, '发票版本已变化，请刷新后核对')
        else:
            row = RecordInvoice(store_id=contract.store_id, contract_id=contract.id)
            db.add(row); db.flush()
        old = plain(row)
        item = db.scalar(select(RecordInvoiceFile).where(RecordInvoiceFile.invoice_id == row.id, RecordInvoiceFile.sha256 == digest))
        if item is None:
            mode = policy_mode()
            state, code = 'quarantined', 'awaiting_scan'
            if mode == 'structure_only':
                state, code = 'structure_only', 'structure_only'
            elif mode == 'clamav':
                result = scan_clamav(content, settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)
                state, code = result.state, result.code
            try:
                object_key = publish(None, contract.store_id, content, len(content), digest) if settings.file_storage_mode == 'private_local' else ''
            except (ValueError, OSError):
                raise HTTPException(503, '发票原件尚未保存，请联系管理员检查存储') from None
            item = RecordInvoiceFile(store_id=contract.store_id, invoice_id=row.id, filename=filename,
                content_type=media, size=len(content), sha256=digest, content=b'' if object_key else content,
                object_key=object_key, scan_state=state, scan_code=code, created_by=user.id)
            db.add(item); db.flush()
        elif not _safe(item) and policy_mode() == 'clamav':
            # An explicit re-upload of the same original may retry a failed
            # scan. The original bytes/hash and earlier audit remain intact.
            result = scan_clamav(content, settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)
            item.scan_state, item.scan_code = result.state, result.code
        if row.active_file_id != item.id:
            row.active_file_id = item.id
            row.fields = {}; row.confirmed_by = None; row.confirmed_at = None; row.note = ''
        row.updated_at = utcnow()
        db.flush()
        audit(db, user.id, 'record_invoice_upload', 'record_contract', contract.id,
              before={'invoice': old}, after={'store_id': contract.store_id, 'invoice_id': row.id, 'file_id': item.id, 'sha256': digest})
        return _summary(db, row)
    return _run(db, user, request_id, 'invoice_upload', payload, perform)


@router.post('/contracts/{key}/invoice/recognize')
def extract_invoice(key: int, body: Action, request: Request, db=Depends(get_db), user=Depends(get_user)):
    _manual(request); _access(user, True)
    contract = get_contract(db, user, key)
    row = _invoice(db, contract.id)
    if row is None:
        raise HTTPException(409, '请先上传发票')
    _check_version(row, body.version)
    item = _file(db, row)
    content, media, expected = _content(item), item.content_type, row.version
    # No writer reservation or transaction is held during the model request.
    db.rollback()
    result = recognize_invoice(content, media)
    current_user = get_user(request, db)
    _access(current_user, True)
    current = _invoice(db, get_contract(db, current_user, key).id)
    if current is None or current.version != expected:
        raise HTTPException(409, '识别期间发票已经更新，请刷新并识别当前原件')
    result['version'] = expected
    return result


@router.post('/contracts/{key}/invoice/confirm')
def confirm_invoice(key: int, body: InvoiceConfirm, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request); _access(user, True)
    contract = get_contract(db, user, key)
    def perform():
        row = _invoice(db, contract.id)
        if row is None:
            raise HTTPException(409, '请先上传发票原件')
        _check_version(row, body.version)
        _content(_file(db, row))
        if not body.fields.invoice_number or body.fields.total_amount_cents is None or not body.fields.issued_on:
            raise HTTPException(422, '请收银核对发票号码、开票日期及价税合计后确认')
        before = plain(row)
        row.fields = body.fields.model_dump(mode='json'); row.note = body.note
        row.confirmed_by = user.id; row.confirmed_at = utcnow()
        db.flush()
        audit(db, user.id, 'record_invoice_confirm', 'record_contract', contract.id,
              before={'invoice': before}, after={'store_id': contract.store_id, 'invoice': plain(row)})
        return _summary(db, row)
    return _run(db, user, body.request_id, 'invoice_confirm', body.model_dump(mode='json') | {'contract_id': key}, perform)


@router.get('/contracts/{key}/invoice/files/{file_id}/download')
def download_invoice(key: int, file_id: int, db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    contract = get_contract(db, user, key)
    row = _invoice(db, contract.id)
    if row is None:
        raise HTTPException(404, '没有发票原件')
    item = _file(db, row, file_id)
    return StreamingResponse(io.BytesIO(_content(item)), media_type=item.content_type,
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(item.filename)})
