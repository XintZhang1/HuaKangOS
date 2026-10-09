"""V2 manual business records, isolated from inventory and accounting workflows."""
import csv
import hashlib
import io
import json
import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, func, or_, update
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy.orm import aliased
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


def get_customer(db, user, key):
    row = db.scalar(visible_query(user, RecordCustomer).where(RecordCustomer.id == key))
    if row is None:
        raise HTTPException(404, '客户档案不存在或不可访问')
    return row


def _lock_customer_scope(db):
    # SQLite already reserves its writer in get_write_db. At PostgreSQL's
    # REPEATABLE READ, a lock alone could leave an older matching snapshot.
    # A no-value-change row update instead makes a concurrent old snapshot fail
    # with 40001. Store has no onupdate/version columns or schema triggers.
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(update(Store).where(Store.id == single_store(db)).values(id=Store.id)
                   .execution_options(synchronize_session=False))


def _record_customer(db, owner_id, name, phone):
    """Link only a unique exact identity; never edit or guess an existing file."""
    _lock_customer_scope(db)
    store = single_store(db)
    if phone.strip():
        candidates = db.scalars(select(RecordCustomer).where(
            RecordCustomer.store_id == store, RecordCustomer.owner_id == owner_id,
            RecordCustomer.name == name, RecordCustomer.phone == phone).limit(2)).all()
        if len(candidates) == 1:
            return candidates[0].id
    row = RecordCustomer(store_id=store, owner_id=owner_id, name=name, phone=phone, note='')
    db.add(row)
    db.flush()
    return row.id


def _customer_rows(db, user, rows):
    """Counts use the same scope as each related list, and only the current page."""
    if not rows:
        return []
    ids = [row.id for row in rows]
    counts = {}
    for model, key in ((SalesContract, 'contract_count'), (AfterSalesRecord, 'after_sales_count')):
        if model is SalesContract and user.role == 'service' and not getattr(user, '_aggregate_scope', False):
            counts[key] = {}
            continue
        query = visible_query(user, model).where(model.customer_id.in_(ids))
        query = query.with_only_columns(model.customer_id, func.count()).group_by(model.customer_id)
        counts[key] = dict(db.execute(query).all())
    owners = {row.id: row.display_name for row in db.scalars(select(User).where(
        User.id.in_({row.owner_id for row in rows})))}
    stores = {row.id: row.name for row in db.scalars(select(Store).where(
        Store.id.in_({row.store_id for row in rows})))}
    result = []
    for row in rows:
        data = plain(row)
        data.update(owner_name=owners.get(row.owner_id, ''), store_name=stores.get(row.store_id, ''),
                    **{key: values.get(row.id, 0) for key, values in counts.items()})
        result.append(data)
    return result


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
    try:
        result = perform()
        db.add(RecordCommand(store_id=store, actor_id=user.id, request_id=request_id,
                             digest=digest, result=result))
        db.commit()
    except OperationalError as exc:
        sqlstate = getattr(exc.orig, 'sqlstate', getattr(exc.orig, 'pgcode', None))
        if sqlstate != '40001':
            raise
        db.rollback()
        raise HTTPException(409, '其他操作已更新相关记录，本次未保存；请刷新核对后再操作') from exc
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
def catalog(report_key: str = Query('', max_length=80), db=Depends(get_db), user=Depends(get_user)):
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
    if report_key:
        reports = [item for item in reports if item['key'] == report_key]
        if not reports:
            raise HTTPException(404, '报表不存在或不可访问')
    return {'capabilities': capabilities(user), 'sales_people': people,
            'service_types': SERVICE_TYPES, 'reports': reports,
            'statuses': STATUS_LABELS, 'today': today().isoformat(),
            'approval_required': True, 'standard_pricing_mode': 'manual',
            'stores': [item for item in getattr(user, '_stores', [])
                       if not getattr(user, '_aggregate_scope', False) or item['id'] in _group_ids(user)]}


@router.get('/contracts')
def contracts(q: str = Query('', max_length=120), status: str = '',
              customer_id: int | None = Query(None, gt=0),
              page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200),
              db=Depends(get_db), user=Depends(get_user)):
    query = visible_query(user, SalesContract)
    if customer_id is not None:
        customer = get_customer(db, user, customer_id)
        query = query.where(SalesContract.customer_id == customer.id, SalesContract.store_id == customer.store_id)
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
        customer_id = _record_customer(db, body.salesperson_id, body.customer_name, body.customer_phone)
        row = SalesContract(**values, store_id=single_store(db), created_by=user.id,
                            customer_id=customer_id,
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
        if row.customer_id is None or (row.customer_name, row.customer_phone) != (body.customer_name, body.customer_phone):
            row.customer_id = _record_customer(db, row.salesperson_id, body.customer_name, body.customer_phone)
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
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(RecordCustomer.id.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': _customer_rows(db, user, rows), 'total': total, 'page': page, 'page_size': page_size}


@router.get('/customers/{key}')
def customer_detail(key: int, db=Depends(get_db), user=Depends(get_user)):
    return _customer_rows(db, user, [get_customer(db, user, key)])[0]


@router.post('/customers', status_code=201)
def create_customer(body: CustomerInput, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'manage_customers')
    def perform():
        _lock_customer_scope(db)
        row = RecordCustomer(**body.model_dump(exclude={'request_id'}),
                             store_id=single_store(db), owner_id=user.id)
        db.add(row)
        db.flush()
        data = _customer_rows(db, user, [row])[0]
        audit(db, user.id, 'record_create', 'record_customer', row.id, after=data)
        return data
    return _run(db, user, body.request_id, 'customer:create', _body(body), perform)


@router.get('/after-sales')
def after_sales(q: str = Query('', max_length=120), service_type: str = '',
                customer_id: int | None = Query(None, gt=0),
                page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200),
                db=Depends(get_db), user=Depends(get_user)):
    query = visible_query(user, AfterSalesRecord)
    if customer_id is not None:
        customer = get_customer(db, user, customer_id)
        query = query.where(AfterSalesRecord.customer_id == customer.id, AfterSalesRecord.store_id == customer.store_id)
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
        customer_id = _record_customer(db, user.id, body.customer_name, body.customer_phone)
        row = AfterSalesRecord(**body.model_dump(exclude={'request_id'}),
            customer_id=customer_id,
            store_id=single_store(db), owner_id=user.id, number='SH-' + uuid.uuid4().hex[:20].upper())
        db.add(row)
        db.flush()
        data = plain(row)
        audit(db, user.id, 'record_create', 'record_service', row.id, after=data)
        return data
    return _run(db, user, body.request_id, 'after_sales:create', _body(body), perform)


def _manual_report_query(user, include_history=False):
    query = visible_query(user, ManualReportRecord)
    if user.role == 'finance':
        query = query.where(ManualReportRecord.report_key.in_(FINANCE_REPORTS))
    if not include_history:
        successor = aliased(ManualReportRecord)
        query = query.where(~select(successor.id).where(
            successor.supersedes_id == ManualReportRecord.id,
            successor.store_id == ManualReportRecord.store_id).exists())
    return query


def _get_manual_report(db, user, key):
    row = db.scalar(_manual_report_query(user, True).where(ManualReportRecord.id == key))
    if row is None:
        raise HTTPException(404, '统计记录不存在或不可访问')
    _report_allowed(user, row.report_key)
    return row


def _manual_report_rows(db, user, rows):
    if not rows:
        return []
    identifiers = {row.id for row in rows}
    # Determine replacement status before employee visibility. A correction may
    # fix the responsible salesperson; the previous owner's row is still old.
    successors = dict(db.execute(select(ManualReportRecord.supersedes_id, ManualReportRecord.id).where(
        ManualReportRecord.supersedes_id.in_(identifiers),
        ManualReportRecord.store_id.in_({row.store_id for row in rows}))).all())
    contract_ids = {row.contract_id for row in rows if row.contract_id is not None}
    contracts = {row.id: row.number for row in db.scalars(
        visible_query(user, SalesContract).where(SalesContract.id.in_(contract_ids)))} if contract_ids else {}
    writable = capabilities(user)['record_statistics']
    result = []
    for row in rows:
        item = plain(row)
        current = row.id not in successors
        item.update(is_current=current, is_effective=current,
                    superseded_by_id=successors.get(row.id),
                    can_correct=writable and current and row.entry_mode != 'legacy',
                    contract_number=contracts.get(row.contract_id, ''))
        result.append(item)
    return result


@router.get('/manual-reports')
def manual_reports(report_key: str = '', include_history: bool = False,
                   page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200),
                   db=Depends(get_db), user=Depends(get_user)):
    query = _manual_report_query(user, include_history)
    if report_key:
        _report_allowed(user, report_key)
        query = query.where(ManualReportRecord.report_key == report_key)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(ManualReportRecord.id.desc())
                     .offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': _manual_report_rows(db, user, rows), 'total': total,
            'page': page, 'page_size': page_size}


@router.get('/manual-reports/{key}')
def manual_report_detail(key: int, db=Depends(get_db), user=Depends(get_user)):
    row = _get_manual_report(db, user, key)
    history, current = [row], row
    while current.supersedes_id is not None:
        current = db.scalar(_manual_report_query(user, True).where(
            ManualReportRecord.id == current.supersedes_id))
        if current is None:
            break  # A reassigned record must not reveal the former owner's data.
        history.insert(0, current)
    current = row
    while True:
        successor = db.scalar(_manual_report_query(user, True).where(
            ManualReportRecord.supersedes_id == current.id))
        if successor is None:
            break
        history.append(successor)
        current = successor
    result = _manual_report_rows(db, user, [row])[0]
    result['history'] = _manual_report_rows(db, user, history)
    return result


def _report_prefill(db, user, report_key, contract):
    _report_allowed(user, report_key)
    from .business_record_reports import prefill_contract_values
    salesperson = db.get(User, contract.salesperson_id)
    try:
        data = prefill_contract_values(report_key, contract,
                                      salesperson.display_name if salesperson else '')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    data.update(contract_id=contract.id, contract_version=contract.version,
                contract_number=contract.number, period=contract.contract_date.isoformat(),
                brand=contract.brand, salesperson_id=contract.salesperson_id,
                locked_metadata=['period', 'brand', 'salesperson_id'], entry_mode='detail')
    return data


@router.get('/report-prefill')
def report_prefill(report_key: str = Query(..., max_length=80),
                   contract_id: int = Query(..., gt=0), db=Depends(get_db), user=Depends(get_user)):
    require_capability(user, 'record_statistics')
    return _report_prefill(db, user, report_key, get_contract(db, user, contract_id))


@router.post('/manual-reports', status_code=201)
def create_manual_report(body: ManualReportInput, request: Request,
                         db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'record_statistics')
    _report_allowed(user, body.report_key)
    def perform():
        from .business_record_reports import validate_manual_values, CATALOG_BY_KEY
        from decimal import Decimal
        previous = None
        if body.supersedes_id is not None:
            previous = _get_manual_report(db, user, body.supersedes_id)
            _check_version(previous, body.supersedes_version)
            if previous.entry_mode == 'legacy':
                raise HTTPException(422, '历史独立统计仅供追溯，不能通过更正转成当前业绩')
            successor = db.scalar(_manual_report_query(user, True).where(
                ManualReportRecord.supersedes_id == previous.id))
            if successor:
                raise HTTPException(409, '这份统计已有更新的更正记录，请打开最新记录')
            if previous.report_key != body.report_key or previous.contract_id != body.contract_id:
                raise HTTPException(422, '更正须保留原统计表和关联合同，请在原记录中修改数据')
        source_key = None
        source_values = dict(body.values)
        if body.contract_id is not None:
            contract = get_contract(db, user, body.contract_id)
            _check_version(contract, body.contract_version)
            prefill = _report_prefill(db, user, body.report_key, contract)
            if (body.brand != prefill['brand'] or body.salesperson_id != prefill['salesperson_id']
                    or body.period.isoformat() != prefill['period']):
                raise HTTPException(422, '关联合同的日期、品牌和销售归属由原合同提供，请重新核对')
            columns = {column['key']: column for column in CATALOG_BY_KEY[body.report_key]['columns']}
            for field in prefill['locked_fields']:
                original = prefill['values'].get(field)
                offered = source_values.get(field)
                if offered not in (None, '') and str(offered) != str(original):
                    equal = False
                    if columns[field]['type'] not in {'text', 'date'} and original is not None:
                        try:
                            equal = Decimal(str(offered)) == Decimal(str(original))
                        except (ArithmeticError, ValueError):
                            pass
                    if not equal:
                        raise HTTPException(422, columns[field]['label'] + '来自原合同，不能在统计补充中改写')
                source_values[field] = original
            if previous is None:
                source_key = f'contract:{contract.id}:{body.report_key}'
                existing = db.scalar(_manual_report_query(user, True).where(
                    ManualReportRecord.source_key == source_key))
                if existing:
                    raise HTTPException(409, '这份合同已有该统计补充，请使用原记录的更正入口')
        elif body.salesperson_id is not None:
            _salesperson(db, user, body.salesperson_id)
        try:
            values = validate_manual_values(body.report_key, source_values)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        data = body.model_dump(exclude={'request_id'})
        data['values'] = values
        row = ManualReportRecord(**data, source_key=source_key,
                                 store_id=single_store(db), created_by=user.id)
        db.add(row)
        db.flush()
        result = _manual_report_rows(db, user, [row])[0]
        audit(db, user.id, 'record_correct' if previous else 'record_create',
              'record_manual', row.id, after=result, reason=body.note)
        return result
    try:
        return _run(db, user, body.request_id, 'manual_report:create', _body(body), perform)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, '该来源或统计更正已由其他操作保存，请刷新并核对最新记录') from exc


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


def _build_report(db, user, report, date_from, date_to, brand, salesperson_id, group_by,
                  category_field='', category_value='', service_type='', handler_name='', source_mode='combined'):
    _report_allowed(user, report)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    if user.role == 'sales' and salesperson_id is not None and salesperson_id != user.id:
        raise HTTPException(403, '销售只能查看自己的数据')
    from .business_record_reports import build_report
    try:
        return build_report(db, user, report, date_from=date_from, date_to=date_to,
                            brand=brand, salesperson_id=salesperson_id, group_by=group_by,
                            category_field=category_field, category_value=category_value,
                            service_type=service_type, handler_name=handler_name, source_mode=source_mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get('/reports')
def reports(report: str = 'profit', date_from: date | None = None, date_to: date | None = None,
            brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
            group_by: str = 'salesperson', category_field: str = Query('', max_length=80),
            category_value: str = Query('', max_length=1000), service_type: str = Query('', max_length=30),
            handler_name: str = Query('', max_length=100), source_mode: str = 'combined',
            db=Depends(get_db), user=Depends(get_user)):
    return _build_report(db, user, report, date_from, date_to, brand, salesperson_id, group_by,
                         category_field, category_value, service_type, handler_name, source_mode)


@router.get('/reports/export')
def export_report(report: str = 'profit', date_from: date | None = None, date_to: date | None = None,
                  brand: str = Query('', max_length=100), salesperson_id: int | None = Query(None, gt=0),
                  group_by: str = 'salesperson', category_field: str = Query('', max_length=80),
                  category_value: str = Query('', max_length=1000), service_type: str = Query('', max_length=30),
                  handler_name: str = Query('', max_length=100), source_mode: str = 'combined', view: str = 'details',
                  db=Depends(get_db), user=Depends(get_user)):
    if view not in {'summary', 'details', 'detail'}:
        raise HTTPException(422, '请选择导出统计表或来源明细')
    result = _build_report(db, user, report, date_from, date_to, brand, salesperson_id, group_by,
                           category_field, category_value, service_type, handler_name, source_mode)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    columns = result['summary_columns'] if view == 'summary' else result['columns']
    writer.writerow([column['label'] for column in columns])
    rows = result['summary_rows'] + [result['grand_total']] if view == 'summary' else result['rows']
    for row in rows:
        values = [row.get(column['key'], '') for column in columns]
        writer.writerow(["'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@'))
                         else value for value in values])
    return Response(('\ufeff' + output.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="business-records.csv"'})
