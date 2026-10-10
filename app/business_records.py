"""V2 manual business records, isolated from inventory and accounting workflows."""
import csv
import hashlib
import io
import json
import re
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
    AfterSalesRecord, ManualReportRecord, RecordSettings, RecordCommand,
    StandardRecordPrice)
from .business_records_schemas import (ContractInput, ContractUpdate, Action, PriceReview,
    Reject, ReceiptInput, CustomerInput, AfterSalesInput, ManualReportInput, SettingsInput,
    OfficeReview, StandardPriceImport, StandardPriceEstimate, ManagerApproval)

router = APIRouter(prefix='/api/business-records', tags=['业务记录'])
MANAGERS = {'admin', 'manager', 'general_manager'}
GROUP_MANAGERS = {'admin', 'general_manager'}
READERS = MANAGERS | {'sales', 'clerk', 'finance', 'chairman', 'group_deputy_manager'}
TRIAL_WORKFLOWS = {'trial-v29', 'trial-v30'}
SENSITIVE_ROLES = {'admin', 'clerk', 'chairman'}
INTERNAL_READERS = SENSITIVE_ROLES
CAPABILITY_ROLES = {
    'create_sales': {'admin', 'sales'},
    'price': {'admin', 'clerk'},
    'manager_approve': {'admin', 'manager'},
    'approve': GROUP_MANAGERS,
    'deputy_approve': {'admin', 'group_deputy_manager'},
    'manage_targets': {'admin', 'manager', 'general_manager', 'chairman', 'group_deputy_manager'},
    'confirm_receipt': {'admin', 'finance'},
    'upload_invoice': {'admin', 'finance'},
    'manage_settings': {'admin', 'general_manager'},
    'record_statistics': {'admin', 'clerk'},
    'create_after_sales': {'admin', 'clerk'},
    'manage_customers': {'admin', 'clerk', 'sales'},
    'read_internal': SENSITIVE_ROLES,
}
SERVICE_TYPES = [{'value': key, 'label': label} for key, label in (
    ('repair', '维修'), ('maintenance', '保养'), ('accident', '事故维修'),
    ('renewal', '续保'), ('extended_warranty', '延保'), ('accessories', '精品销售'))]
STATUS_LABELS = {'submitted': '待销售经理审批', 'manager_approved': '待总经理审批',
                 'deputy_pending': '待集团副总经理审批',
                 'priced': '历史合同待管理审批', 'approved': '合同审批通过，可打印', 'rejected': '已退回'}
OFFICE_STATUS_LABELS = {'not_started': '待销售内勤填报', 'draft': '销售内勤填报中',
    'submitted': '待总经理审批附带信息', 'approved': '附带信息已批准', 'rejected': '附带信息已退回'}
FINANCE_REPORTS = {'expected_receipts', 'actual_receipts', 'insurance_settlement',
                   'insurance_resources', 'insurance_renewal', 'bank_finance'}


def _group_ids(user):
    return [item['id'] for item in getattr(user, '_stores', [])
            if item.get('role') in GROUP_MANAGERS | {'chairman'}]


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
    label = '历史合同待内勤核价' if row.workflow_version == 'legacy-v2' and row.status == 'submitted' else STATUS_LABELS[row.status]
    data.update(salesperson_name=sales.display_name if sales else '',
                store_name=store.name if store else '', status_label=STATUS_LABELS[row.status],
                actual_amount_cents=receipt.actual_amount_cents if receipt else None,
                received_on=receipt.received_on.isoformat() if receipt else None,
                receipt=plain(receipt) if receipt else None)
    data['status_label'] = label
    data['office_status_label'] = OFFICE_STATUS_LABELS[row.office_status]
    caps = capabilities(user)
    actions = []
    trial = row.workflow_version in TRIAL_WORKFLOWS
    independent = user.id not in {row.salesperson_id, row.created_by}
    if row.status in {'submitted', 'rejected'}:
        if caps['create_sales'] and (user.role != 'sales' or row.salesperson_id == user.id):
            actions.append('edit')
        if not trial and caps['price'] and row.status == 'submitted':
            actions.extend(['price_review', 'reject'])
        if trial and row.status == 'submitted' and caps['manager_approve'] and independent:
            actions.extend(['manager_approve', 'reject'])
    if (row.status == 'priced' or (trial and row.status == 'manager_approved')) and caps['approve'] and independent and row.manager_approved_by != user.id:
        actions.extend(['approve', 'reject'])
    if row.status == 'deputy_pending' and caps['deputy_approve'] and independent and user.id not in {row.manager_approved_by, row.general_manager_approved_by}:
        actions.extend(['deputy_approve', 'reject'])
    if row.status == 'approved':
        actions.append('print')
        if caps['confirm_receipt'] and not receipt:
            actions.append('receipt')
        if caps['upload_invoice']:
            actions.append('upload_invoice')
        if caps['price'] and row.office_status != 'submitted':
            actions.append('office_edit')
            if row.office_status in {'draft', 'rejected'} and row.office_data:
                actions.append('office_submit')
        if row.office_status == 'submitted' and caps['approve'] and independent and row.office_submitted_by != user.id:
            actions.extend(['office_approve', 'office_reject'])
    if user.role not in SENSITIVE_ROLES:
        # Cashiers and sales see the customer-facing contract, not internal
        # costs, commissions, review notes or a nested copy of those fields.
        for field in ('cost_cents', 'profit_cents', 'gift_cost_cents', 'price_note',
                      'office_data', 'office_approved_data', 'office_approval_note'):
            data.pop(field, None)
    from .business_record_office_view import office_review_view
    for field in ('office_data', 'office_approved_data'):
        source = getattr(row, field)
        if source and (user.role in SENSITIVE_ROLES or user.role == 'general_manager'):
            data[field] = office_review_view(source, user.role in SENSITIVE_ROLES)
    data['actions'] = actions
    return data


def _list(db, query, serializer, page, page_size):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {'items': [serializer(row) for row in rows], 'total': total,
            'page': page, 'page_size': page_size}


def _report_allowed(user, report):
    require_read(user)
    from .business_record_report_specs import assert_report_access
    assert_report_access(user, report)


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
    reports = []
    for item in REPORT_CATALOG:
        try:
            _report_allowed(user, item['key'])
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
        else:
            reports.append(item)
    if report_key:
        reports = [item for item in reports if item['key'] == report_key]
        if not reports:
            raise HTTPException(404, '报表不存在或不可访问')
    return {'capabilities': capabilities(user), 'sales_people': people,
            'service_types': SERVICE_TYPES, 'reports': reports,
            'statuses': STATUS_LABELS, 'office_statuses': OFFICE_STATUS_LABELS, 'today': today().isoformat(),
            'approval_required': True, 'standard_pricing_mode': 'optional_reference',
            'stores': [item for item in getattr(user, '_stores', [])
                       if not getattr(user, '_aggregate_scope', False) or item['id'] in _group_ids(user)]}


@router.get('/contracts')
def contracts(q: str = Query('', max_length=120), status: str = '', office_status: str = '',
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
    if office_status:
        if office_status not in OFFICE_STATUS_LABELS:
            raise HTTPException(422, '内勤资料状态无效')
        query = query.where(SalesContract.office_status == office_status)
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
                            number='XS-' + uuid.uuid4().hex[:20].upper(), status='submitted',
                            workflow_version='trial-v30')
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
            raise HTTPException(409, '已审批合同不可修改；有变更请重新预填一份新合同，原合同保留归档')
        before = _contract_data(db, user, row)
        if row.customer_id is None or (row.customer_name, row.customer_phone) != (body.customer_name, body.customer_phone):
            row.customer_id = _record_customer(db, row.salesperson_id, body.customer_name, body.customer_phone)
        for name, value in body.model_dump(exclude={'request_id', 'version'}).items():
            setattr(row, name, value)
        row.status = 'submitted'
        row.manager_approved_by = row.manager_approved_at = None
        row.manager_approval_note = row.approval_note = ''
        row.approval_limits = None
        row.general_manager_approved_by = row.general_manager_approved_at = None
        row.general_manager_approval_note = ''
        row.deputy_approved_by = row.deputy_approved_at = None
        if row.workflow_version == 'legacy-v2':
            row.expected_amount_cents = row.cost_cents = row.profit_cents = row.gift_cost_cents = None
            row.priced_by = row.priced_at = None
            row.price_note = ''
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
        if row.workflow_version in TRIAL_WORKFLOWS:
            raise HTTPException(409, '新版合同先由销售经理、总经理审批；内勤请使用独立的附带信息核对入口')
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


def _verified_limits(sale_price_cents, limits):
    """Compare explicit sales allowances; missing facts never imply compliance.

    The business owner must confirm the allowance policy before rollout. This
    draft supports per-contract manual verification with a recorded source; it
    never guesses a default vehicle price or uses private actual gift costs.
    """
    keys = ('minimum_sale_price_cents', 'gift_limit_cents', 'offered_gift_value_cents')
    if (not isinstance(limits, dict)
            or any(type(limits.get(key)) is not int or not 0 <= limits[key] <= 999999999999 for key in keys)
            or not isinstance(limits.get('approval_basis'), str)
            or not limits['approval_basis'].strip()):
        raise HTTPException(409, '本合同尚无完整额度核对，不能按正常额度批准；请退回销售经理重新核对')
    result = {key: limits[key] for key in (*keys, 'approval_basis')}
    result['price_exceeded'] = sale_price_cents < limits['minimum_sale_price_cents']
    result['gift_exceeded'] = limits['offered_gift_value_cents'] > limits['gift_limit_cents']
    result['requires_deputy'] = result['price_exceeded'] or result['gift_exceeded']
    return result


def _finish_contract_approval(db, user, row, note, template_version):
    row.status, row.approved_by, row.approved_at = 'approved', user.id, utcnow()
    if row.workflow_version in TRIAL_WORKFLOWS:
        row.expected_amount_cents = row.sale_price_cents
    row.approval_note, row.template_version = note, template_version
    # Freeze before a SELECT could autoflush the approval constraint.
    with db.no_autoflush:
        snapshot = _contract_data(db, user, row)
    snapshot['version'] = row.version + 1
    snapshot.pop('actions', None)
    row.approved_snapshot = snapshot


@router.post('/contracts/{key}/manager-approve')
def manager_approve_contract(key: int, body: ManagerApproval, request: Request,
                             db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'manager_approve')
    row = get_contract(db, user, key)
    if user.id in {row.salesperson_id, row.created_by}:
        raise HTTPException(403, '合同销售或填单本人不能审批自己的合同')
    def perform():
        _check_version(row, body.version)
        if row.workflow_version not in TRIAL_WORKFLOWS or row.status != 'submitted':
            raise HTTPException(409, '仅待销售经理审批的新版合同可办理此操作')
        before = _contract_data(db, user, row)
        if row.workflow_version == 'trial-v30':
            fields = ('minimum_sale_price_cents', 'gift_limit_cents', 'offered_gift_value_cents', 'approval_basis')
            limits = {name: getattr(body, name) for name in fields}
            if any(value is None for value in limits.values()):
                raise HTTPException(422, '请由销售经理核对最低成交限价、赠送额度上限、本单赠送金额（非成本）及额度依据；不能将未填额度视为正常')
            row.approval_limits = _verified_limits(row.sale_price_cents, limits)
        row.status = 'manager_approved'
        row.manager_approved_by, row.manager_approved_at = user.id, utcnow()
        row.manager_approval_note = body.note
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_manager_approve', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:manager_approve',
                body.model_dump(mode='json', exclude={'request_id'}, exclude_none=True), perform)


@router.post('/contracts/{key}/approve')
def approve_contract(key: int, body: Action, request: Request,
                     db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'approve')
    row = get_contract(db, user, key)
    if user.id in {row.salesperson_id, row.created_by, row.manager_approved_by}:
        raise HTTPException(403, '销售、填单人及本合同销售经理审批人不能办理总经理审批')
    def perform():
        _check_version(row, body.version)
        trial = row.workflow_version in TRIAL_WORKFLOWS
        if row.status != ('manager_approved' if trial else 'priced'):
            raise HTTPException(409, '请先由销售经理审批合同' if trial else '历史合同须先完成内勤核价')
        from .business_record_pdf import TEMPLATE_VERSION, validate_contract_print_data
        before = _contract_data(db, user, row)
        try:
            validate_contract_print_data(before)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if row.workflow_version == 'trial-v30':
            limits = _verified_limits(row.sale_price_cents, row.approval_limits)
            row.general_manager_approved_by, row.general_manager_approved_at = user.id, utcnow()
            row.general_manager_approval_note = body.note
            if limits['requires_deputy']:
                row.status = 'deputy_pending'
                row.approval_note = body.note
            else:
                _finish_contract_approval(db, user, row, body.note, TEMPLATE_VERSION)
        else:
            _finish_contract_approval(db, user, row, body.note, TEMPLATE_VERSION)
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_approve', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:approve', _body(body), perform)


@router.post('/contracts/{key}/deputy-approve')
def deputy_approve_contract(key: int, body: Action, request: Request,
                            db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'deputy_approve')
    row = get_contract(db, user, key)
    if user.id in {row.salesperson_id, row.created_by, row.manager_approved_by, row.general_manager_approved_by}:
        raise HTTPException(403, '销售、填单人及前序审批人不能办理本合同集团副总经理审批')
    def perform():
        _check_version(row, body.version)
        if row.workflow_version != 'trial-v30' or row.status != 'deputy_pending':
            raise HTTPException(409, '仅总经理已批准的超限价或超赠送合同可办理集团副总经理审批')
        if not _verified_limits(row.sale_price_cents, row.approval_limits)['requires_deputy']:
            raise HTTPException(409, '本合同不属于超限审批，请核对合同状态')
        from .business_record_pdf import TEMPLATE_VERSION, validate_contract_print_data
        before = _contract_data(db, user, row)
        try:
            validate_contract_print_data(before)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        row.deputy_approved_by, row.deputy_approved_at = user.id, utcnow()
        _finish_contract_approval(db, user, row, body.note, TEMPLATE_VERSION)
        db.flush()
        data = _contract_data(db, user, row)
        audit(db, user.id, 'record_deputy_approve', 'record_contract', row.id, before, data, body.note)
        return data
    return _run(db, user, body.request_id, f'contract:{key}:deputy_approve', _body(body), perform)


@router.post('/contracts/{key}/reject')
def reject_contract(key: int, body: Reject, request: Request,
                    db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_read(user)
    if not (capabilities(user)['price'] or capabilities(user)['manager_approve'] or capabilities(user)['approve'] or capabilities(user)['deputy_approve']):
        raise HTTPException(403, '当前岗位不能退回合同')
    row = get_contract(db, user, key)
    if user.id in {row.salesperson_id, row.created_by}:
        raise HTTPException(403, '合同销售本人不能办理审核退回')
    def perform():
        _check_version(row, body.version)
        if row.workflow_version in TRIAL_WORKFLOWS:
            allowed = set()
            if capabilities(user)['manager_approve']:
                allowed.add('submitted')
            if capabilities(user)['approve'] and user.id != row.manager_approved_by:
                allowed.add('manager_approved')
            if capabilities(user)['deputy_approve'] and user.id not in {row.manager_approved_by, row.general_manager_approved_by}:
                allowed.add('deputy_pending')
        else:
            allowed = {'submitted'} if user.role == 'clerk' else ({'submitted', 'priced'} if capabilities(user)['approve'] or capabilities(user)['manager_approve'] else set())
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
            raise HTTPException(409, '请先完成合同审批')
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
        raise HTTPException(409, '合同须经销售经理、总经理审批；超限价或超赠送时还须集团副总经理审批通过后才能打印；历史合同沿用原审批')
    from .business_record_pdf import render_contract_pdf
    try:
        pdf = render_contract_pdf(row.approved_snapshot)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return Response(pdf, media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{row.number}.pdf"', 'Cache-Control': 'no-store'})


def _office_values(db, user, row, body):
    """Contract identity is fixed; every external cost remains a manual fact."""
    from decimal import Decimal
    from .business_record_reports import CATALOG_BY_KEY, validate_manual_values
    definition = CATALOG_BY_KEY[body.report_key]
    prefill = _report_prefill(db, user, body.report_key, row)
    columns = {field['key']: field for field in definition['columns']}
    editable = {'精品成本（赠送）', '单车利润', '核定单车利润', '单车利润2', '单车利润22'}
    values = dict(body.values)
    for key in prefill['locked_fields']:
        if columns[key]['label'] in editable:
            continue
        expected, offered = prefill['values'].get(key), values.get(key)
        if offered not in (None, '') and str(offered) != str(expected):
            equal = False
            if columns[key]['type'] not in {'text', 'date'} and expected is not None:
                try:
                    equal = Decimal(str(offered)) == Decimal(str(expected))
                except (ArithmeticError, ValueError):
                    pass
            if not equal:
                raise HTTPException(422, columns[key]['label'] + '来自合同，请先更正合同后再核对')
        values[key] = expected
    data = body.model_dump(mode='json', exclude={'request_id', 'version'})
    data['period'] = (body.period or today()).isoformat()
    # The top-level final profit is one fact, also shown in the original sheet.
    profit_label = {'vehicle_details': '核定单车利润', 'hail_vehicle_details': '单车利润22',
                    'secondary_vehicle_details': '单车利润', 'vehicle_details_sheet2': '单车利润'}[body.report_key]
    for field_name, label in (('profit_cents', profit_label), ('gift_cost_cents', '精品成本（赠送）')):
        key = next((key for key, field in columns.items() if field['label'] == label), None)
        amount = getattr(body, field_name)
        if key and amount is not None:
            text = format(Decimal(amount) / 100, '.2f')
            if values.get(key) not in (None, ''):
                try:
                    equal = Decimal(str(values[key])) == Decimal(text)
                except (ArithmeticError, ValueError):
                    equal = False
                if not equal:
                    raise HTTPException(422, label + '与核价区金额不一致，请核对后保存')
            values[key] = text
    try:
        data['values'] = validate_manual_values(body.report_key, values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    for field_name, label in (('profit_cents', profit_label), ('gift_cost_cents', '精品成本（赠送）')):
        key = next((key for key, field in columns.items() if field['label'] == label), None)
        if key and data[field_name] is None and data['values'].get(key) is not None:
            amount = int(Decimal(data['values'][key]) * 100)
            if abs(amount) > 999999999999 or (field_name != 'profit_cents' and amount < 0):
                raise HTTPException(422, label + '超出可核定金额范围')
            data[field_name] = amount
    return data


@router.put('/contracts/{key}/office-review')
def save_office_review(key: int, body: OfficeReview, request: Request,
                      db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'price')
    row = get_contract(db, user, key)
    def perform():
        _check_version(row, body.version)
        if row.status != 'approved':
            raise HTTPException(409, '合同通过两级审批后，内勤再填写核价及附带信息')
        if row.office_status == 'submitted':
            raise HTTPException(409, '附带信息正在审批，请总经理退回后再修改')
        previous = row.office_data or row.office_approved_data or {}
        if previous and previous.get('report_key') != body.report_key:
            raise HTTPException(422, '同一车辆已选定明细表，更正须沿用原表，避免重复计数')
        before = _contract_data(db, user, row)
        data = _office_values(db, user, row, body)
        row.office_data, row.office_status = data, 'draft'
        row.office_revision += 1
        row.office_approval_note = ''
        db.flush()
        result = _contract_data(db, user, row)
        audit(db, user.id, 'record_office_save', 'record_contract', row.id, before, result, body.note)
        return result
    return _run(db, user, body.request_id, f'contract:{key}:office_save', _body(body), perform)


@router.post('/contracts/{key}/office-submit')
def submit_office_review(key: int, body: Action, request: Request,
                        db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'price')
    row = get_contract(db, user, key)
    def perform():
        _check_version(row, body.version)
        if row.status != 'approved' or row.office_status not in {'draft', 'rejected'} or not row.office_data:
            raise HTTPException(409, '请先保存已批准合同的内勤核价及附带信息')
        # Re-check against the current contract after a contract correction.
        candidate = OfficeReview(**row.office_data, version=row.version, request_id=body.request_id)
        _office_values(db, user, row, candidate)
        before = _contract_data(db, user, row)
        row.office_status = 'submitted'
        row.office_submitted_by, row.office_submitted_at = user.id, utcnow()
        db.flush()
        result = _contract_data(db, user, row)
        audit(db, user.id, 'record_office_submit', 'record_contract', row.id, before, result, body.note)
        return result
    return _run(db, user, body.request_id, f'contract:{key}:office_submit', _body(body), perform)


@router.post('/contracts/{key}/office-approve')
def approve_office_review(key: int, body: Action, request: Request,
                         db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'approve')
    row = get_contract(db, user, key)
    if user.id in {row.salesperson_id, row.created_by, row.office_submitted_by}:
        raise HTTPException(403, '销售、填单人或内勤提交人不能审批自己的附带信息')
    def perform():
        _check_version(row, body.version)
        if row.status != 'approved' or row.office_status != 'submitted' or not row.office_data:
            raise HTTPException(409, '仅已提交的内勤资料可以审批')
        before = plain(row)
        before.pop('approved_snapshot', None)
        data = dict(row.office_data)
        # An approval appends a replacement, including when an existing legacy
        # contract already had a manually recorded detail. Never double-count it.
        successor = aliased(ManualReportRecord)
        previous = db.scalar(visible_query(user, ManualReportRecord).where(
            ManualReportRecord.contract_id == row.id,
            ManualReportRecord.report_key == data['report_key'],
            ~select(successor.id).where(successor.supersedes_id == ManualReportRecord.id,
                                       successor.store_id == row.store_id).exists()).order_by(ManualReportRecord.id.desc()))
        source_key = None if previous else f'contract:{row.id}:{data["report_key"]}'
        entry = ManualReportRecord(store_id=row.store_id, created_by=user.id,
            report_key=data['report_key'], period=date.fromisoformat(data['period']),
            brand=row.brand, salesperson_id=row.salesperson_id, values=data['values'],
            contract_id=row.id, contract_version=row.version + 1, entry_mode='detail',
            supersedes_id=previous.id if previous else None,
            supersedes_version=previous.version if previous else None,
            source_key=source_key, note=data.get('note', ''))
        db.add(entry)
        db.flush()
        data['manual_report_id'] = entry.id
        data['contract_version'] = row.version + 1
        row.office_approved_data, row.office_status = data, 'approved'
        row.office_approved_by, row.office_approved_at = user.id, utcnow()
        row.office_approval_note = body.note
        if row.workflow_version in TRIAL_WORKFLOWS:
            for field in ('cost_cents', 'profit_cents', 'gift_cost_cents'):
                setattr(row, field, data.get(field))
            if data.get('expected_amount_cents') is not None:
                row.expected_amount_cents = data['expected_amount_cents']
            row.priced_by, row.priced_at = row.office_submitted_by, row.office_submitted_at
            row.price_note = data.get('note', '')
        db.flush()
        result = _contract_data(db, user, row)
        after = plain(row)
        after.pop('approved_snapshot', None)
        audit(db, user.id, 'record_office_approve', 'record_contract', row.id, before, after, body.note)
        audit(db, user.id, 'record_create_from_office', 'record_manual', entry.id, after=plain(entry), reason=body.note)
        return result
    return _run(db, user, body.request_id, f'contract:{key}:office_approve', _body(body), perform)


@router.post('/contracts/{key}/office-reject')
def reject_office_review(key: int, body: Reject, request: Request,
                        db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'approve')
    row = get_contract(db, user, key)
    if user.id in {row.salesperson_id, row.created_by, row.office_submitted_by}:
        raise HTTPException(403, '销售、填单人或内勤提交人不能审核自己的附带信息')
    def perform():
        _check_version(row, body.version)
        if row.status != 'approved' or row.office_status != 'submitted':
            raise HTTPException(409, '仅待审批的内勤资料可以退回')
        before = _contract_data(db, user, row)
        row.office_status, row.office_approval_note = 'rejected', body.note
        db.flush()
        result = _contract_data(db, user, row)
        audit(db, user.id, 'record_office_reject', 'record_contract', row.id, before, result, body.note)
        return result
    return _run(db, user, body.request_id, f'contract:{key}:office_reject', _body(body), perform)


@router.get('/standard-prices')
def standard_prices(q: str = Query('', max_length=160), page: int = Query(1, ge=1),
                    page_size: int = Query(100, ge=1, le=500),
                    db=Depends(get_db), user=Depends(get_user)):
    require_read(user)
    if user.role not in INTERNAL_READERS:
        raise HTTPException(403, '标准价格及成本仅供内勤和管理人员核对')
    query = visible_query(user, StandardRecordPrice)
    if q:
        query = query.where(StandardRecordPrice.name.contains(q, autoescape=True))
    return _list(db, query.order_by(StandardRecordPrice.name, StandardRecordPrice.id), plain, page, page_size)


@router.post('/standard-prices/import')
def import_standard_prices(body: StandardPriceImport, request: Request,
                           db=Depends(get_write_db), user=Depends(get_user)):
    _manual(request)
    require_capability(user, 'price')
    names = [item.name for item in body.rows]
    if len(names) != len(set(names)):
        raise HTTPException(422, '本次导入含同名物品，请核对后再提交')
    def perform():
        existing = {row.name: row for row in db.scalars(visible_query(user, StandardRecordPrice).where(
            StandardRecordPrice.name.in_(names)))}
        result = []
        for item in body.rows:
            row = existing.get(item.name)
            before = plain(row) if row else None
            if row is None:
                if item.version is not None:
                    raise HTTPException(409, '价格记录已变化，请刷新最新价格后重新核对')
                row = StandardRecordPrice(store_id=single_store(db), created_by=user.id, **item.model_dump(exclude={'version'}))
                db.add(row)
            else:
                if item.version is None:
                    raise HTTPException(409, '已有同名价格，请先读取并核对最新版本后再更新')
                _check_version(row, item.version)
                for key, value in item.model_dump(exclude={'version'}).items():
                    setattr(row, key, value)
            db.flush()
            data = plain(row)
            audit(db, user.id, 'record_price_reference_import', 'record_standard_price', row.id, before, data)
            result.append(data)
        return {'items': result, 'count': len(result)}
    return _run(db, user, body.request_id, 'standard_price:import', _body(body), perform)


@router.post('/standard-prices/estimate')
def estimate_standard_prices(body: StandardPriceEstimate, db=Depends(get_db), user=Depends(get_user)):
    require_capability(user, 'price')
    ids = {item.price_id for item in body.items}
    prices = {row.id: row for row in db.scalars(visible_query(user, StandardRecordPrice).where(
        StandardRecordPrice.id.in_(ids)))}
    if len(prices) != len(ids):
        raise HTTPException(422, '部分标准物品不存在或不属于当前门店，请刷新核对')
    result, sale, cost = [], 0, 0
    for item in body.items:
        row = prices[item.price_id]
        item_sale = None if row.sale_price_cents is None else row.sale_price_cents * item.quantity
        item_cost = None if row.cost_cents is None else row.cost_cents * item.quantity
        sale = None if sale is None or item_sale is None else sale + item_sale
        cost = None if cost is None or item_cost is None else cost + item_cost
        if any(value is not None and value > 999999999999 for value in (item_sale, item_cost, sale, cost)):
            raise HTTPException(422, '参考价格合计超出可记录金额范围，请拆分核对')
        result.append({'price_id': row.id, 'version': row.version, 'name': row.name,
            'quantity': item.quantity, 'sale_price_cents': item_sale, 'cost_cents': item_cost})
    return {'items': result, 'sale_price_cents': sale, 'cost_cents': cost,
            'requires_manual_review': True, 'note': '仅为参考预算，未知价格保留为空；请内勤核对后填写合同附带信息'}


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
    def serialize_service(row):
        data = plain(row)
        if user.role not in SENSITIVE_ROLES:
            data.pop('cost_cents', None)
        return data
    return _list(db, query.order_by(AfterSalesRecord.id.desc()), serialize_service, page, page_size)


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
    if user.role not in INTERNAL_READERS:
        raise HTTPException(403, '统计原始明细仅供内勤和管理人员核对')
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
    contract_rows = list(db.scalars(
        visible_query(user, SalesContract).where(SalesContract.id.in_(contract_ids)))) if contract_ids else []
    contracts = {row.id: row.number for row in contract_rows}
    office_contracts = {row.id for row in contract_rows if row.workflow_version in TRIAL_WORKFLOWS or row.office_approved_data}
    writable = capabilities(user)['record_statistics']
    result = []
    for row in rows:
        item = plain(row)
        current = row.id not in successors
        item.update(is_current=current, is_effective=current,
                    superseded_by_id=successors.get(row.id),
                    can_correct=writable and current and row.entry_mode not in {'legacy', 'target'} and row.contract_id not in office_contracts,
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
            if previous.entry_mode == 'target':
                raise HTTPException(422, '月度目标须使用管理者月度目标入口更正，不能转成实绩')
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
            if contract.workflow_version in TRIAL_WORKFLOWS or contract.office_approved_data:
                raise HTTPException(409, '此合同附带信息须在合同内由内勤填报、总经理审批后生成，不能直接写入统计')
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
