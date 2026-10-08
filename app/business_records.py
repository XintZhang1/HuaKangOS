"""V2 manual business records, isolated from inventory and accounting workflows."""
import csv
import hashlib
import io
import json
import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, func, or_
from .db import get_db, get_write_db, utcnow, today
from .models import User, Store
from .security import get_user
from .tenancy import single_store, role_for_store
from .services import plain, audit
from .business_records_models import (SalesContract, ContractReceipt, RecordCustomer,
    AfterSalesRecord, ManualReportRecord, RecordSettings, RecordCommand)
from .business_records_schemas import (ContractInput, ContractUpdate, Action, PriceReview,
    Reject, ReceiptInput, CustomerInput, AfterSalesInput, ManualReportInput, SettingsInput)

router = APIRouter(prefix='/api/business-records', tags=['业务记录'])
MANAGERS = {'admin', 'manager', 'general_manager', 'chairman'}
GROUP_MANAGERS = {'admin', 'general_manager', 'chairman'}
READERS = MANAGERS | {'sales', 'clerk', 'finance', 'service'}
CAPABILITY_ROLES = {
    'create_sales': MANAGERS | {'sales'},
    'price': {'admin', 'clerk'},
    'approve': GROUP_MANAGERS,
    'confirm_receipt': {'admin', 'finance'},
    'manage_settings': {'admin', 'general_manager', 'chairman'},
    'record_statistics': MANAGERS | {'clerk', 'finance'},
    'create_after_sales': MANAGERS | {'clerk', 'service', 'sales'},
    'manage_customers': MANAGERS | {'clerk', 'sales', 'service'},
}
SERVICE_TYPES = [{'value': key, 'label': label} for key, label in (
    ('repair', '维修'), ('maintenance', '保养'), ('accident', '事故维修'),
    ('renewal', '续保'), ('extended_warranty', '延保'), ('accessories', '精品销售'))]
STATUS_LABELS = {'submitted': '待内勤核价', 'priced': '待管理审批',
                 'approved': '审批通过', 'rejected': '已退回'}
FINANCE_REPORTS = {'expected_receipts', 'actual_receipts', 'insurance_settlement',
                   'insurance_resources', 'insurance_renewal', 'bank_finance'}


def _group_ids(user):
    return [item['id'] for item in getattr(user, '_stores', [])
            if item.get('role') in GROUP_MANAGERS]


def require_read(user):
    if getattr(user, '_aggregate_scope', False):
        if not _group_ids(user):
            raise HTTPException(403, '经营记录集团汇总仅向获授权的总经理或董事长开放')
    elif user.role not in READERS:
        raise HTTPException(403, '当前岗位没有业务记录访问权限')


def capabilities(user):
    writable = not getattr(user, '_aggregate_scope', False)
    return {key: writable and user.role in roles for key, roles in CAPABILITY_ROLES.items()}


def require_capability(user, key):
    require_read(user)
    if not capabilities(user)[key]:
        raise HTTPException(403, '当前岗位不能办理此操作，请由相应岗位人工处理')


def _manual(request):
    # Runtime tools must never turn background model execution into a manual act.
    if '_huakang_runtime' in request.scope:
        raise HTTPException(403, '业务记录须由员工在页面核对并确认，后台助手不能提交')


def visible_query(user, model):
    """The only V2 query entry: current-store criteria also apply via tenancy."""
    require_read(user)
    query = select(model)
    if getattr(user, '_aggregate_scope', False):
        query = query.where(model.store_id.in_(_group_ids(user)))
    elif user.role == 'sales':
        owner = getattr(model, 'salesperson_id', None)
        if owner is None:
            owner = getattr(model, 'owner_id', None)
        if owner is None:
            raise HTTPException(403, '当前岗位不可直接读取该数据')
        query = query.where(owner == user.id)
    elif user.role == 'service':
        if model not in {AfterSalesRecord, RecordCustomer}:
            raise HTTPException(403, '售后岗位仅可读取本人售后记录与客户档案')
        query = query.where(model.owner_id == user.id)
    return query


def get_contract(db, user, key):
    row = db.scalar(visible_query(user, SalesContract).where(SalesContract.id == key))
    if row is None:
        raise HTTPException(404, '合同不存在或不可访问')
    return row


def _salesperson(db, user, ident):
    store = single_store(db)
    if user.role == 'sales' and ident != user.id:
        raise HTTPException(403, '销售只能登记归属自己的合同')
    target = db.scalar(select(User).where(User.id == ident, User.active.is_(True)))
    if not target or role_for_store(db, target, store) != 'sales':
        raise HTTPException(422, '请选择当前门店已启用的销售员工')
    return target


def _check_version(row, version):
    if row.version != version:
        raise HTTPException(409, '记录已更新，请刷新并核对最新版本后重新操作')


def _run(db, user, request_id, action, payload, perform):
    """One short transaction owns business fact, audit and immutable request receipt."""
    store = single_store(db)
    digest = hashlib.sha256(json.dumps({'action': action, 'payload': payload},
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    prior = db.scalar(select(RecordCommand).where(RecordCommand.store_id == store,
        RecordCommand.actor_id == user.id, RecordCommand.request_id == request_id))
    if prior:
        if prior.digest != digest:
            raise HTTPException(409, '本次请求号已用于不同内容，请核对原操作结果')
        return prior.result
    result = perform()
    db.add(RecordCommand(store_id=store, actor_id=user.id, request_id=request_id,
                         digest=digest, result=result))
    db.commit()
    return result


def _body(body):
    return body.model_dump(mode='json', exclude={'request_id'})


def _receipt(db, row):
    return db.scalar(select(ContractReceipt).where(ContractReceipt.contract_id == row.id,
                                                   ContractReceipt.store_id == row.store_id))


def _contract_data(db, user, row):
    data = plain(row)
    # The snapshot duplicates personal details and is used only by the approved renderer.
    data.pop('approved_snapshot', None)
    sales = db.get(User, row.salesperson_id)
    store = db.get(Store, row.store_id)
    receipt = _receipt(db, row)
    data.update(salesperson_name=sales.display_name if sales else '',
                store_name=store.name if store else '', status_label=STATUS_LABELS[row.status],
                actual_amount_cents=receipt.actual_amount_cents if receipt else None,
                received_on=receipt.received_on.isoformat() if receipt else None,
                receipt=plain(receipt) if receipt else None)
    caps = capabilities(user)
    actions = []
    if row.status in {'submitted', 'rejected'}:
        if caps['create_sales'] and (user.role != 'sales' or row.salesperson_id == user.id):
            actions.append('edit')
        if caps['price'] and row.status == 'submitted':
            actions.extend(['price_review', 'reject'])
    if row.status == 'priced' and caps['approve'] and row.salesperson_id != user.id:
        actions.extend(['approve', 'reject'])
    if row.status == 'approved':
        actions.append('print')
        if caps['confirm_receipt'] and not receipt:
            actions.append('receipt')
    data['actions'] = actions
    return data


def _list(db, query, serializer, page, page_size):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': [serializer(row) for row in rows], 'total': total,
            'page': page, 'page_size': page_size}


def _report_allowed(user, report):
    require_read(user)
    key = report.split(':', 1)[0]
    if user.role == 'service' and key != 'after_sales_revenue':
        raise HTTPException(403, '售后岗位仅查看本人售后统计')
    if user.role == 'finance' and key not in FINANCE_REPORTS:
        raise HTTPException(403, '财务岗位仅查看到账及对账统计')


@router.get('/catalog')
def catalog(db=Depends(get_db), user=Depends(get_user)):
    require_read(user)
    from .business_record_reports import REPORT_CATALOG
    active = getattr(user, '_active_store_id', None)
    people = []
    if user.role == 'sales':
        people = [{'id': user.id, 'label': user.display_name}]
    else:
        stores = _group_ids(user) if getattr(user, '_aggregate_scope', False) else [active]
        for target in db.scalars(select(User).where(User.active.is_(True)).order_by(User.display_name, User.id)):
            if any(role_for_store(db, target, store) == 'sales' for store in stores):
                people.append({'id': target.id, 'label': target.display_name})
    reports = [item for item in REPORT_CATALOG
               if (user.role != 'service' or item.get('key') == 'after_sales_revenue')
               and (user.role != 'finance' or item.get('key') in FINANCE_REPORTS)]
    return {'capabilities': capabilities(user), 'sales_people': people,
            'service_types': SERVICE_TYPES, 'reports': reports,
            'statuses': STATUS_LABELS, 'today': today().isoformat(),
            'approval_required': True, 'standard_pricing_mode': 'manual',
            'stores': [item for item in getattr(user, '_stores', [])
                       if not getattr(user, '_aggregate_scope', False) or item['id'] in _group_ids(user)]}


@router.get('/contracts')
def contracts(q: str = Query('', max_length=120), status: str = '',
              page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200),
              db=Depends(get_db), user=Depends(get_user)):
    query = visible_query(user, SalesContract)
    if status:
        if status not in STATUS_LABELS:
            raise HTTPException(422, '合同状态无效')
        query = query.where(SalesContract.status == status)
    if q:
        query = query.where(or_(*(field.contains(q, autoescape=True) for field in
            (SalesContract.number, SalesContract.customer_name, SalesContract.customer_phone,
             SalesContract.brand, SalesContract.model, SalesContract.vin))))
    return _list(db, query.order_by(SalesContract.id.desc()),
                 lambda row: _contract_data(db, user, row), page, page_size)


@router.post('/contracts', status_code=201)
def create_contract(body: ContractInput, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'create_sales')
    _salesperson(db, user, body.salesperson_id)
    def perform():
        values = body.model_dump(exclude={'request_id'})
        row = SalesContract(**values, store_id=single_store(db), created_by=user.id,
                            number='XS-' + uuid.uuid4().hex[:20].upper(), status='submitted')
        db.add(row)
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_create', 'record_contract', row.id, after=data)
        return data
    return _run(db, user, body.request_id, 'contract:create', _body(body), perform)


@router.get('/contracts/{key}')
def contract_detail(key: int, db=Depends(get_db), user=Depends(get_user)):
    return _contract_data(db, user, get_contract(db, user, key))


@router.put('/contracts/{key}')
def edit_contract(key: int, body: ContractUpdate, request: Request,
                  db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'create_sales')
    row = get_contract(db, user, key)
    _salesperson(db, user, body.salesperson_id)
    if body.salesperson_id != row.salesperson_id:
        raise HTTPException(422, '本版合同销售归属固定，不支持转交或分摊')
    def perform():
        _check_version(row, body.version)
        if row.status not in {'submitted', 'rejected'}:
            raise HTTPException(409, '核价完成后的合同须由管理人员退回后再修改')
        before = _contract_data(db, user, row)
        for name, value in body.model_dump(exclude={'request_id', 'version'}).items():
            setattr(row, name, value)
        row.status = 'submitted'
        row.expected_amount_cents = row.cost_cents = row.profit_cents = row.gift_cost_cents = None
        row.priced_by = row.priced_at = None
        row.price_note = row.approval_note = ''
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_edit', 'record_contract', row.id, before, data)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:edit', _body(body), perform)


@router.post('/contracts/{key}/price-review')
def price_contract(key: int, body: PriceReview, request: Request,
                   db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'price')
    row = get_contract(db, user, key)
    def perform():
        _check_version(row, body.version)
        if row.status != 'submitted':
            raise HTTPException(409, '仅待核价合同可完成内勤核价；退回合同须先修改重提')
        before = _contract_data(db, user, row)
        for name in ('expected_amount_cents', 'cost_cents', 'profit_cents', 'gift_cost_cents'):
            setattr(row, name, getattr(body, name))
        row.price_note = body.note
        row.priced_by, row.priced_at, row.status = user.id, utcnow(), 'priced'
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_price', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:price', _body(body), perform)


@router.post('/contracts/{key}/approve')
def approve_contract(key: int, body: Action, request: Request,
                     db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'approve')
    row = get_contract(db, user, key)
    if row.salesperson_id == user.id:
        raise HTTPException(403, '合同销售本人不能审批自己的合同')
    def perform():
        _check_version(row, body.version)
        if row.status != 'priced':
            raise HTTPException(409, '必须先完成内勤核价，再由管理人员审批')
        from .business_record_pdf import TEMPLATE_VERSION, validate_contract_print_data
        before = _contract_data(db, user, row)
        try:
            validate_contract_print_data(before)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        row.status, row.approved_by, row.approved_at = 'approved', user.id, utcnow()
        row.approval_note, row.template_version = body.note, TEMPLATE_VERSION
        # Freeze approved form before any SELECT could autoflush the approval constraint.
        with db.no_autoflush:
            snapshot = _contract_data(db, user, row)
        snapshot['version'] = row.version + 1
        snapshot.pop('actions', None)
        row.approved_snapshot = snapshot
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_approve', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:approve', _body(body), perform)


@router.post('/contracts/{key}/reject')
def reject_contract(key: int, body: Reject, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_read(user)
    if user.role not in (CAPABILITY_ROLES['price'] | CAPABILITY_ROLES['approve']):
        raise HTTPException(403, '仅内勤或管理人员可以退回合同')
    row = get_contract(db, user, key)
    if row.salesperson_id == user.id:
        raise HTTPException(403, '合同销售本人不能办理审核退回')
    def perform():
        _check_version(row, body.version)
        allowed = {'submitted'} if user.role == 'clerk' else {'submitted', 'priced'}
        if row.status not in allowed:
            raise HTTPException(409, '当前状态不可退回；批准合同不能在本版改写')
        before = _contract_data(db, user, row)
        row.status, row.approval_note = 'rejected', body.note
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_reject', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:reject', _body(body), perform)


@router.post('/contracts/{key}/receipt')
def confirm_receipt(key: int, body: ReceiptInput, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'confirm_receipt')
    row = get_contract(db, user, key)
    def perform():
        _check_version(row, body.version)
        if row.status != 'approved':
            raise HTTPException(409, '请先完成合同核价和管理审批')
        if _receipt(db, row):
            raise HTTPException(409, '此合同已有财务到账确认，请核对原记录，不能重复记入')
        if body.received_on > today():
            raise HTTPException(422, '实际到账日期不能晚于今天')
        before = _contract_data(db, user, row)
        receipt = ContractReceipt(store_id=row.store_id, contract_id=row.id,
            actual_amount_cents=body.actual_amount_cents, received_on=body.received_on,
            confirmed_by=user.id, note=body.note)
        db.add(receipt)
        row.updated_at = utcnow()
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_receipt', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:receipt', _body(body), perform)


@router.get('/contracts/{key}/print')
def print_contract(key: int, db=Depends(get_db), user=Depends(get_user)):
    row = get_contract(db, user, key)
    if row.status != 'approved' or not row.approved_snapshot:
        raise HTTPException(409, '合同须经内勤核价及管理审批通过后才能打印')
    from .business_record_pdf import render_contract_pdf
    try:
        pdf = render_contract_pdf(row.approved_snapshot)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return Response(pdf, media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{row.number}.pdf"', 'Cache-Control': 'no-store'})


@router.get('/customers')
def customers(q: str = Query('', max_length=120), page: int = Query(1, ge=1),
              page_size: int = Query(30, ge=1, le=200), db=Depends(get_db), user=Depends(get_user)):
    query = visible_query(user, RecordCustomer)
    if q:
        query = query.where(or_(RecordCustomer.name.contains(q, autoescape=True),
                               RecordCustomer.phone.contains(q, autoescape=True)))
    return _list(db, query.order_by(RecordCustomer.id.desc()), plain, page, page_size)


@router.post('/customers', status_code=201)
def create_customer(body: CustomerInput, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'manage_customers')
    def perform():
        row = RecordCustomer(**body.model_dump(exclude={'request_id'}),
                             store_id=single_store(db), owner_id=user.id)
        db.add(row)
        db.flush()
        data = plain(row)
        audit(db, user.id, 'record_create', 'record_customer', row.id, after=data)
        return data
    return _run(db, user, body.request_id, 'customer:create', _body(body), perform)


@router.get('/after-sales')
def after_sales(q: str = Query('', max_length=120), service_type: str = '',
                page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200),
                db=Depends(get_db), user=Depends(get_user)):
    query = visible_query(user, AfterSalesRecord)
    if q:
        query = query.where(or_(AfterSalesRecord.customer_name.contains(q, autoescape=True),
                               AfterSalesRecord.vehicle.contains(q, autoescape=True),
                               AfterSalesRecord.number.contains(q, autoescape=True)))
    if service_type:
        query = query.where(AfterSalesRecord.service_type == service_type)
    return _list(db, query.order_by(AfterSalesRecord.id.desc()), plain, page, page_size)


@router.post('/after-sales', status_code=201)
def create_after_sales(body: AfterSalesInput, request: Request,
                       db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'create_after_sales')
    def perform():
        row = AfterSalesRecord(**body.model_dump(exclude={'request_id'}),
            store_id=single_store(db), owner_id=user.id, number='SH-' + uuid.uuid4().hex[:20].upper())
        db.add(row)
        db.flush()
        data = plain(row)
        audit(db, user.id, 'record_create', 'record_service', row.id, after=data)
        return data
    return _run(db, user, body.request_id, 'after_sales:create', _body(body), perform)


@router.get('/manual-reports')
def manual_reports(report_key: str = '', page: int = Query(1, ge=1),
                   page_size: int = Query(30, ge=1, le=200), db=Depends(get_db), user=Depends(get_user)):
    query = visible_query(user, ManualReportRecord)
    if user.role == 'finance':
        query = query.where(ManualReportRecord.report_key.in_(FINANCE_REPORTS))
    if report_key:
        _report_allowed(user, report_key)
        query = query.where(ManualReportRecord.report_key == report_key)
    return _list(db, query.order_by(ManualReportRecord.id.desc()), plain, page, page_size)


@router.post('/manual-reports', status_code=201)
def create_manual_report(body: ManualReportInput, request: Request,
                         db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'record_statistics')
    _report_allowed(user, body.report_key)
    from .business_record_reports import validate_manual_values
    try:
        values = validate_manual_values(body.report_key, body.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if body.salesperson_id is not None:
        _salesperson(db, user, body.salesperson_id)
    def perform():
        data = body.model_dump(exclude={'request_id'})
        data['values'] = values
        row = ManualReportRecord(**data, store_id=single_store(db), created_by=user.id)
        db.add(row)
        db.flush()
        result = plain(row)
        audit(db, user.id, 'record_create', 'record_manual', row.id, after=result)
        return result
    return _run(db, user, body.request_id, 'manual_report:create', _body(body), perform)


def _settings_data(row):
    data = plain(row) if row else {'version': 0, 'approval_mode': 'all',
        'threshold_amount_cents': None, 'threshold_basis_points': None}
    data.update(approval_required=True, price_upload_available=False, standard_pricing_mode='manual',
        notice='当前全部合同仍须人工核价和管理审批；阈值只作核对参考。标准价格上传预留。')
    return data


@router.get('/settings')
def get_settings(db=Depends(get_db), user=Depends(get_user)):
    require_read(user)
    store = single_store(db)
    return _settings_data(db.scalar(select(RecordSettings).where(RecordSettings.store_id == store)))


@router.put('/settings')
def update_settings(body: SettingsInput, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'manage_settings')
    def perform():
        store = single_store(db)
        row = db.scalar(select(RecordSettings).where(RecordSettings.store_id == store))
        if (row.version if row else 0) != body.version:
            raise HTTPException(409, '审批参考设置已变化，请刷新后重新核对')
        before = _settings_data(row)
        values = body.model_dump(exclude={'request_id', 'version'})
        if row is None:
            row = RecordSettings(store_id=store, **values)
            db.add(row)
        else:
            for name, value in values.items():
                setattr(row, name, value)
        db.flush()
        result = _settings_data(row)
        audit(db, user.id, 'record_settings', 'record_settings', row.id, before, result)
        return result
    return _run(db, user, body.request_id, 'settings:update', _body(body), perform)


def _build_report(db, user, report, date_from, date_to, brand, salesperson_id, group_by):
    _report_allowed(user, report)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    if user.role == 'sales' and salesperson_id is not None and salesperson_id != user.id:
        raise HTTPException(403, '销售只能查看自己的数据')
    from .business_record_reports import build_report
    try:
        return build_report(db, user, report, date_from=date_from, date_to=date_to,
                            brand=brand, salesperson_id=salesperson_id, group_by=group_by)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get('/reports')
def reports(report: str = 'profit', date_from: date | None = None, date_to: date | None = None,
            brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
            group_by: str = 'salesperson', db=Depends(get_db), user=Depends(get_user)):
    return _build_report(db, user, report, date_from, date_to, brand, salesperson_id, group_by)


@router.get('/reports/export')
def export_report(report: str = 'profit', date_from: date | None = None, date_to: date | None = None,
                  brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
                  group_by: str = 'salesperson', db=Depends(get_db), user=Depends(get_user)):
    result = _build_report(db, user, report, date_from, date_to, brand, salesperson_id, group_by)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    columns = result['columns']
    writer.writerow([column['label'] for column in columns])
    for row in result['rows']:
        values = [row.get(column['key'], '') for column in columns]
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@'))
                         else value for value in values])
    return Response(('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="business-records.csv"'})
