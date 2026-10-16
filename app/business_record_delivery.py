"""Cashier delivery, stamped gifts, manager return review and separate refunds."""
import hashlib
import io
from datetime import date, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, Response
from pydantic import Field
from sqlalchemy import select
from .config import settings
from .db import get_db, get_write_db, today, utcnow
from .security import get_user
from .services import plain, audit
from .business_records_schemas import Action, Command, Money, Key
from .business_record_delivery_models import RecordDelivery, RecordGiftDocument, RecordReturn, RecordRefund

router = APIRouter(prefix='/api/business-records', tags=['财务交车与退车'])


def _write(user, roles):
    if getattr(user, '_aggregate_scope', False) or user.role not in roles:
        raise HTTPException(403, '请由当前门店相应岗位在业务页面核对办理')


def _delivery(db, contract):
    return db.scalar(select(RecordDelivery).where(RecordDelivery.contract_id == contract.id))


def _gift(db, contract):
    return db.scalar(select(RecordGiftDocument).where(RecordGiftDocument.contract_id == contract.id)
                     .order_by(RecordGiftDocument.id.desc()).limit(1))


def _returns(db, contract):
    return list(db.scalars(select(RecordReturn).where(RecordReturn.contract_id == contract.id)
                           .order_by(RecordReturn.id.desc())))


def pending_refund_clause(contract_model):
    """A registered payment is not a claim that every refund has settled."""
    registered = select(RecordRefund.id).where(RecordRefund.return_id == RecordReturn.id).exists()
    return select(RecordReturn.id).where(RecordReturn.contract_id == contract_model.id,
        RecordReturn.store_id == contract_model.store_id, RecordReturn.status == 'approved', ~registered).exists()


def _file_info(item):
    from .business_record_invoices import _safe
    if item is None:
        return None
    return {key: plain(item)[key] for key in ('id', 'filename', 'content_type', 'size', 'sha256', 'created_at')} | {'available': _safe(item)}


def delivery_summary(db, user, contract):
    from .business_record_invoices import _invoice, _file, _safe
    from .employee_handover import was_contract_handler
    delivery, gift, invoice = _delivery(db, contract), _gift(db, contract), _invoice(db, contract.id)
    invoice_ready = bool(invoice and invoice.confirmed_at and invoice.uploaded_at and invoice.active_file_id and _safe(_file(db, invoice)))
    gift_ready = bool(gift and _safe(gift))
    bound_gift = db.scalar(select(RecordGiftDocument).where(RecordGiftDocument.id == delivery.gift_document_id,
        RecordGiftDocument.contract_id == contract.id)) if delivery else None
    bound_invoice_ready = bool(delivery and invoice and _safe(_file(db, invoice, delivery.invoice_file_id)))
    writable = not getattr(user, '_aggregate_scope', False)
    returns, actions = [], []
    for row in _returns(db, contract):
        refunds = list(db.scalars(select(RecordRefund).where(RecordRefund.return_id == row.id)))
        item = plain(row)
        item.pop('reversal_snapshot', None)
        item['refunds'] = [plain(refund) for refund in refunds]
        item['refunded_amount_cents'] = sum(refund.amount_cents for refund in refunds)
        item['refund_registration_status'] = ('registered' if refunds else 'pending') if row.status == 'approved' else None
        item['actions'] = []
        if (writable and row.status == 'submitted' and user.role in {'general_manager', 'group_deputy_manager'}
                and user.id != row.requested_by and not was_contract_handler(db, user, contract)):
            item['actions'] += ['approve', 'reject']
        if writable and row.status == 'approved' and user.role in {'finance', 'admin'}:
            item['actions'].append('refund')
        returns.append(item)
    if writable and contract.status == 'approved' and contract.workflow_version == 'trial-v210':
        if user.role in {'finance', 'admin'}:
            actions.append('upload_gift_document')
            if not delivery and invoice_ready and gift_ready:
                actions.append('confirm_delivery')
        if (delivery and not contract.archived_at and user.role in {'general_manager', 'group_deputy_manager'}
                and not any(r['status'] in {'submitted', 'approved'} for r in returns)):
            actions.append('request_return')
    data = {'delivery': plain(delivery) if delivery else None, 'invoice_ready': invoice_ready,
            'invoice_version': invoice.version if invoice else None,
            'gift_document': _file_info(gift), 'materials_ready': bool(bound_invoice_ready and bound_gift and _safe(bound_gift)),
            'returns': returns, 'actions': actions,
            'pending_refund': any(item['refund_registration_status'] == 'pending' for item in returns)}
    from .business_record_privacy import sanitize_command_result
    return sanitize_command_result(db, user, data, payload={'contract_id': contract.id})


def require_office_materials(db, contract):
    from .business_record_invoices import _invoice, _file, _content
    delivery = _delivery(db, contract)
    if delivery is None:
        raise HTTPException(409, '财务须上传并核实发票及盖章赠品单，确认交车后再填写内勤延伸资料')
    invoice = _invoice(db, contract.id)
    if not invoice:
        raise HTTPException(409, '交车关联发票尚待财务核对')
    _content(_file(db, invoice, delivery.invoice_file_id))
    gift = db.scalar(select(RecordGiftDocument).where(RecordGiftDocument.id == delivery.gift_document_id,
                                                    RecordGiftDocument.contract_id == contract.id))
    if not gift or gift.contract_id != contract.id:
        raise HTTPException(409, '交车关联盖章赠品单不存在')
    _content(gift)
    return delivery


@router.get('/contracts/{key}/delivery-state')
def delivery_state(key: int, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    return delivery_summary(db, user, get_contract(db, user, key))


@router.post('/contracts/{key}/gift-document')
def upload_gift_document(key: int, request: Request, file: UploadFile = File(...),
        request_id: str = Form(...), version: int = Form(...), db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    from .business_record_invoices import _safe
    from .flow_documents import validate_upload
    from .file_security import policy_mode, scan_clamav
    from .private_files import publish
    _manual(request); _write(user, {'finance', 'admin'})
    Command(request_id=request_id)
    contract = get_contract(db, user, key)
    content = file.file.read(10 * 1024 * 1024 + 1)
    filename = file.filename or ''
    media = validate_upload(filename, content)
    if media not in {'application/pdf', 'image/png', 'image/jpeg'}:
        raise HTTPException(422, '盖章赠品单仅支持 PDF、PNG、JPEG，每份最多 10 MB')
    digest = hashlib.sha256(content).hexdigest()
    def perform():
        _check_version(contract, version)
        if contract.status != 'approved' or contract.workflow_version != 'trial-v210':
            raise HTTPException(409, '请在新版合同批准后上传盖章赠品单')
        mode = policy_mode()
        state, code = 'quarantined', 'awaiting_scan'
        if mode == 'structure_only':
            state = code = 'structure_only'
        elif mode == 'clamav':
            result = scan_clamav(content, settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)
            state, code = result.state, result.code
        try:
            object_key = publish(None, contract.store_id, content, len(content), digest) if settings.file_storage_mode == 'private_local' else ''
        except (ValueError, OSError):
            raise HTTPException(503, '赠品单原件尚未保存，请核对附件存储') from None
        row = RecordGiftDocument(store_id=contract.store_id, contract_id=key, filename=filename,
            content_type=media, size=len(content), sha256=digest, object_key=object_key,
            content=b'' if object_key else content, scan_state=state, scan_code=code, created_by=user.id)
        db.add(row)
        contract.updated_at = utcnow()
        db.flush()
        audit(db, user.id, 'record_gift_document_upload', 'record_contract', key,
              after={'store_id': contract.store_id, 'file_id': row.id, 'sha256': digest})
        return delivery_summary(db, user, contract) | {'contract_version': contract.version}
    return _run(db, user, request_id, 'gift_document_upload',
                {'contract_id': key, 'version': version, 'filename': filename, 'sha256': digest}, perform)


@router.get('/contracts/{key}/gift-document/files/{file_id}/download')
def download_gift_document(key: int, file_id: int, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_invoices import _content
    contract = get_contract(db, user, key)
    from .business_record_privacy import require_personal_export
    require_personal_export(db, user, contract)
    if user.role not in {'admin', 'finance', 'clerk', 'manager', 'general_manager', 'group_deputy_manager', 'chairman', 'store_admin'}:
        raise HTTPException(403, '盖章赠品单原件仅供相应审核及财务岗位查看')
    row = db.scalar(select(RecordGiftDocument).where(RecordGiftDocument.id == file_id,
                                                    RecordGiftDocument.contract_id == contract.id))
    if row is None:
        raise HTTPException(404, '赠品单原件不存在或不属于本合同')
    return Response(_content(row), media_type=row.content_type,
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row.filename), 'Cache-Control': 'no-store'})


@router.get('/contracts/{key}/gift-document/print')
def print_gift_document(key: int, mode: str = Query('full', pattern='^(full|overprint)$'),
        paper_width_mm: float = Query(280, ge=150, le=400), paper_height_mm: float = Query(95, ge=60, le=210),
        offset_x_mm: float = Query(0, ge=-20, le=20), offset_y_mm: float = Query(0, ge=-20, le=20),
        db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_corrections import effective_snapshot
    from .business_record_gift_pdf import render_gift_vouchers
    from .business_record_privacy import require_personal_export
    contract = get_contract(db, user, key)
    require_personal_export(db, user, contract)
    if user.role not in {'finance', 'admin'}:
        raise HTTPException(403, '赠送通知单仅可由财务下载或打印')
    if contract.status != 'approved':
        raise HTTPException(409, '合同批准后才能打印赠送通知单')
    snapshot = effective_snapshot(db, contract)
    if not snapshot or not snapshot.get('terms'):
        raise HTTPException(409, '历史合同没有逐项赠品快照，请使用原签署赠品单')
    try:
        content = render_gift_vouchers(snapshot, output_mode=mode,
            paper_width_mm=paper_width_mm, paper_height_mm=paper_height_mm,
            offset_x_mm=offset_x_mm, offset_y_mm=offset_y_mm)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return Response(content, media_type='application/pdf',
        headers={'Content-Disposition': 'inline; filename="decoration-gift-notice.pdf"', 'Cache-Control': 'no-store'})


@router.get('/gift-print-calibration')
def gift_print_calibration(paper_width_mm: float = Query(280, ge=150, le=400),
        paper_height_mm: float = Query(95, ge=60, le=210), offset_x_mm: float = Query(0, ge=-20, le=20),
        offset_y_mm: float = Query(0, ge=-20, le=20), user=Depends(get_user)):
    from .business_record_gift_pdf import render_gift_calibration
    if user.role not in {'finance', 'admin'}:
        raise HTTPException(403, '赠送通知单套打校准仅供财务使用')
    try:
        content = render_gift_calibration(paper_width_mm=paper_width_mm, paper_height_mm=paper_height_mm,
            offset_x_mm=offset_x_mm, offset_y_mm=offset_y_mm)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return Response(content, media_type='application/pdf',
        headers={'Content-Disposition': 'inline; filename="gift-notice-calibration.pdf"', 'Cache-Control': 'no-store'})


class DeliveryConfirm(Action):
    invoice_version: Key


@router.post('/contracts/{key}/delivery-confirm')
def confirm_delivery(key: int, body: DeliveryConfirm, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    from .business_record_invoices import _file, _content
    from .business_record_invoice_models import RecordInvoice
    _manual(request); _write(user, {'finance', 'admin'})
    contract = get_contract(db, user, key)
    def perform():
        _check_version(contract, body.version)
        if contract.status != 'approved' or contract.workflow_version != 'trial-v210' or _delivery(db, contract):
            raise HTTPException(409, '合同尚未批准或已经确认交车，请刷新核对')
        # Hold the same original/version through confirmation; concurrent invoice
        # replacement cannot move the document after the employee reviewed it.
        invoice = db.scalar(select(RecordInvoice).where(RecordInvoice.contract_id == key).with_for_update())
        gift = _gift(db, contract)
        if not invoice or not invoice.confirmed_at or not invoice.uploaded_at:
            raise HTTPException(409, '请先上传核实发票，再人工确认交车')
        if gift is None:
            raise HTTPException(409, '请先上传盖章赠品单，再人工确认交车')
        _content(gift)
        _check_version(invoice, body.invoice_version)
        invoice_file = _file(db, invoice)
        _content(invoice_file)
        uploaded_at = invoice.uploaded_at
        accounting_on = uploaded_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()
        row = RecordDelivery(store_id=contract.store_id, contract_id=key, invoice_id=invoice.id,
            invoice_file_id=invoice_file.id, gift_document_id=gift.id, accounting_on=accounting_on,
            invoice_amount_cents=invoice.fields['total_amount_cents'], confirmed_by=user.id, note=body.note)
        db.add(row); contract.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_delivery_confirm', 'record_contract', key,
              after={'store_id': contract.store_id, 'delivery_id': row.id, 'accounting_on': str(accounting_on),
                     'cc_role': 'general_manager'})
        return delivery_summary(db, user, contract) | {'contract_version': contract.version}
    return _run(db, user, body.request_id, 'delivery_confirm', body.model_dump(mode='json') | {'contract_id': key}, perform)


@router.get('/delivery-notices')
def delivery_notices(db=Depends(get_db), user=Depends(get_user)):
    from .business_records import visible_query, require_read
    from .business_records_models import SalesContract
    require_read(user)
    if user.role not in {'general_manager', 'group_deputy_manager', 'admin', 'store_admin'}:
        raise HTTPException(403, '交车抄送供总经理查看')
    contracts = list(db.scalars(visible_query(user, SalesContract)))
    lookup = {row.id: row for row in contracts}
    items = list(db.scalars(select(RecordDelivery).where(RecordDelivery.contract_id.in_(lookup))
                           .order_by(RecordDelivery.confirmed_at.desc()))) if lookup else []
    return {'items': [plain(row) | {'number': lookup[row.contract_id].number,
                                  'model': lookup[row.contract_id].model} for row in items]}


class ReturnRequest(Action):
    note: str = Field(min_length=1, max_length=2000)
    requested_refund_cents: Money | None = None


class RefundInput(Action):
    amount_cents: int = Field(gt=0, le=999999999999, strict=True)
    refunded_on: date


@router.post('/contracts/{key}/returns')
def request_return(key: int, body: ReturnRequest, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    _manual(request); _write(user, {'general_manager', 'group_deputy_manager'})
    contract = get_contract(db, user, key)
    def perform():
        _check_version(contract, body.version)
        if contract.archived_at or contract.status != 'approved' or contract.workflow_version != 'trial-v210':
            raise HTTPException(409, '请在未作废的新版已批准合同办理退车')
        from .business_record_corrections import correction_rows, ACTIVE
        if any(item.status in ACTIVE for item in correction_rows(db, contract)):
            raise HTTPException(409, '请先完成或撤销办理中的合同更正，再办理真实退车')
        delivery = _delivery(db, contract)
        if not delivery or any(row.status in {'submitted', 'approved'} for row in _returns(db, contract)):
            raise HTTPException(409, '退车须关联已交车合同，且不能重复申请已受理或批准的退车')
        row = RecordReturn(store_id=contract.store_id, contract_id=key, delivery_id=delivery.id,
            requested_by=user.id, requested_refund_cents=body.requested_refund_cents, note=body.note)
        # This is the general manager's explicit business confirmation, not
        # self-approval of the historical salesperson-request workflow.
        row.reviewed_by, row.reviewed_at, row.review_note = user.id, utcnow(), body.note
        _approve_return(db, contract, row)
        db.add(row); contract.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_return_confirm', 'record_contract', key,
              after={'store_id': contract.store_id, 'return_id': row.id, 'approved_on': str(row.approved_on),
                     'next_role': 'finance', 'refund_registration_status': 'pending'})
        return delivery_summary(db, user, contract) | {'contract_version': contract.version}
    return _run(db, user, body.request_id, 'return_confirm', body.model_dump(mode='json') | {'contract_id': key}, perform)


def _return(db, contract, return_id):
    row = db.scalar(select(RecordReturn).where(RecordReturn.id == return_id, RecordReturn.contract_id == contract.id))
    if row is None:
        raise HTTPException(404, '退车申请不存在或不属于本合同')
    return row


def _approve_return(db, contract, row):
    """Freeze the same reversal facts for new confirmations and old requests."""
    from copy import deepcopy
    from .business_record_corrections import effective_snapshot
    effective = effective_snapshot(db, contract) or {}
    submission = (effective.get('terms') or {}).get('submission_data') or {}
    row.status, row.approved_on = 'approved', today()
    row.reversal_snapshot = {'original_accounting_on': str(_delivery(db, contract).accounting_on),
        'sale_price_cents': effective.get('sale_price_cents', contract.sale_price_cents),
        'submission_data': {'is_cash_vehicle': submission.get('is_cash_vehicle')},
        'office_approved_data': deepcopy(contract.office_approved_data),
        # V2.20 counts include explicitly filled pending quantities. Freeze
        # their source too so a later office edit cannot change the reversal.
        'office_data': deepcopy(contract.office_data) if contract.office_status != 'approved' else None,
        'office_status': contract.office_status}


def _review_return(key, return_id, body, request, db, user, approved):
    from .business_records import get_contract, _manual, _run, _check_version
    from .employee_handover import was_contract_handler
    _manual(request); _write(user, {'general_manager', 'group_deputy_manager'})
    contract = get_contract(db, user, key)
    def perform():
        row = _return(db, contract, return_id)
        _check_version(row, body.version)
        if row.status != 'submitted':
            raise HTTPException(409, '退车申请已处理，请刷新核对')
        if user.id == row.requested_by or was_contract_handler(db, user, contract):
            raise HTTPException(403, '退车须由独立的总经理审核，不能自批')
        row.status = 'approved' if approved else 'rejected'
        row.reviewed_by, row.reviewed_at, row.review_note = user.id, utcnow(), body.note
        if approved:
            _approve_return(db, contract, row)
        contract.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_return_approve' if approved else 'record_return_reject', 'record_contract', key,
              after={'store_id': contract.store_id, 'return_id': row.id, 'approved_on': str(row.approved_on) if approved else None,
                     'revision_note': '退车批准当月冲减，原日报保留；需内勤预览后追加修订' if approved else body.note})
        return delivery_summary(db, user, contract) | {'contract_version': contract.version}
    return _run(db, user, body.request_id, 'return_approve' if approved else 'return_reject',
                body.model_dump(mode='json') | {'contract_id': key, 'return_id': return_id}, perform)


@router.post('/contracts/{key}/returns/{return_id}/approve')
def approve_return(key: int, return_id: int, body: Action, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review_return(key, return_id, body, request, db, user, True)


@router.post('/contracts/{key}/returns/{return_id}/reject')
def reject_return(key: int, return_id: int, body: Action, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review_return(key, return_id, body, request, db, user, False)


@router.post('/contracts/{key}/returns/{return_id}/refund')
def record_refund(key: int, return_id: int, body: RefundInput, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    _manual(request); _write(user, {'finance', 'admin'})
    contract = get_contract(db, user, key)
    def perform():
        row = _return(db, contract, return_id)
        _check_version(row, body.version)
        if row.status != 'approved' or body.refunded_on > today():
            raise HTTPException(409, '退车批准后可另录实际退款，实际日期不能晚于今天')
        refund = RecordRefund(store_id=contract.store_id, contract_id=key, return_id=row.id,
            amount_cents=body.amount_cents, refunded_on=body.refunded_on, confirmed_by=user.id, note=body.note)
        db.add(refund); row.updated_at = utcnow(); contract.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_return_refund', 'record_contract', key,
              after={'store_id': contract.store_id, 'return_id': row.id, 'refund_id': refund.id, 'amount_cents': body.amount_cents})
        return delivery_summary(db, user, contract) | {'contract_version': contract.version}
    return _run(db, user, body.request_id, 'return_refund',
                body.model_dump(mode='json') | {'contract_id': key, 'return_id': return_id}, perform)
