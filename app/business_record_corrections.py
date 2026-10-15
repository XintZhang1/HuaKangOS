"""Append contract revisions without replaying an order, delivery or payment."""
from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db, get_write_db, utcnow, today
from .models import User
from .security import get_user
from .services import plain, audit
from .tenancy import role_for_store
from .business_records_models import RecordContractCorrection
from .business_records_schemas import Action, CorrectionRequest, CorrectionSubmit, CorrectionManagerApproval

router = APIRouter(prefix='/api/business-records', tags=['合同更正与重审'])
ACTIVE = {'draft', 'submitted', 'manager_approved', 'deputy_pending'}
LABELS = {'draft': '待指定经办人更正', 'submitted': '更正待销售经理审批',
    'manager_approved': '更正待总经理审批', 'deputy_pending': '更正待集团副总经理审批',
    'approved': '更正已批准', 'cancelled': '更正已撤销'}


def correction_rows(db, contract):
    return list(db.scalars(select(RecordContractCorrection).where(
        RecordContractCorrection.contract_id == contract.id,
        RecordContractCorrection.store_id == contract.store_id).order_by(RecordContractCorrection.id.desc())))


def latest_correction(db, contract):
    return db.scalar(select(RecordContractCorrection).where(
        RecordContractCorrection.contract_id == contract.id,
        RecordContractCorrection.store_id == contract.store_id,
        RecordContractCorrection.status == 'approved').order_by(RecordContractCorrection.id.desc()))


def effective_snapshot(db, contract):
    latest = latest_correction(db, contract)
    if latest:
        return deepcopy(latest.approved_snapshot)
    snapshot = deepcopy(contract.approved_snapshot)
    if snapshot and contract.workflow_version == 'trial-v210':
        # Earlier approvals froze a role-filtered response. Recover its exact
        # submission evidence, never today's catalog and never rewrite history.
        from .business_record_pricing import get_terms
        terms = get_terms(db, contract)
        if terms is not None:
            snapshot['terms'] = deepcopy(plain(terms))
    return snapshot


def correction_print_snapshot(db, user, contract, revision_id):
    from .business_record_privacy import require_personal_export
    require_personal_export(db, user, contract)
    revision = _revision(db, contract, revision_id)
    if revision.status != 'approved' or not revision.approved_snapshot:
        raise HTTPException(409, '更正须按原岗位完成独立重审后才能打印')
    return deepcopy(revision.approved_snapshot)


def _revision(db, contract, ident):
    row = db.scalar(select(RecordContractCorrection).where(RecordContractCorrection.id == ident,
        RecordContractCorrection.contract_id == contract.id, RecordContractCorrection.store_id == contract.store_id))
    if row is None:
        raise HTTPException(404, '更正记录不存在或不属于本合同')
    return row


def _target(db, contract, user_id, role):
    person = db.get(User, user_id)
    if not person or not person.active or person.archived_at or role_for_store(db, person, contract.store_id) != role:
        raise HTTPException(422, '请选择当前门店在用的销售顾问或销售经理')
    return person


def targets(db, contract):
    result = []
    for person in db.scalars(select(User).where(User.active.is_(True), User.archived_at.is_(None)).order_by(User.display_name, User.id)):
        role = role_for_store(db, person, contract.store_id)
        if role not in {'sales', 'manager'}:
            continue
        try:
            _target(db, contract, person.id, role)
        except HTTPException:
            continue
        result.append({'id': person.id, 'name': person.display_name, 'role': role})
    return result


def _event(row, user, action, note=''):
    row.events = [*(row.events or []), {'action': action, 'actor_id': user.id,
        'actor_name': user.display_name, 'role': user.role, 'at': utcnow().isoformat(),
        'note': note, 'status': row.status, 'assigned_to': row.assigned_to, 'assigned_role': row.assigned_role}]


def _input(snapshot):
    terms = snapshot.get('terms') or {}
    submission = terms.get('submission_data') or {}
    from .business_records_schemas import ContractSubmission
    result = {key: deepcopy(snapshot.get(key)) for key in ('customer_name', 'customer_phone', 'brand',
        'model', 'vin', 'salesperson_id', 'contract_date', 'sale_price_cents', 'gift_description', 'form_data')}
    result.update(vehicle_price_id=(terms.get('price_snapshot') or {}).get('id'),
        inventory_row_id=(terms.get('inventory_snapshot') or submission.get('inventory_snapshot') or {}).get('inventory_row_id'),
        gift_items=[{'price_id': item['price_id'], 'quantity': item['quantity']} for item in terms.get('gifts_snapshot', [])],
        accessory_items=[{'price_id': item['price_id'], 'quantity': item['quantity']} for item in submission.get('accessory_snapshot', [])],
        submission_data={key: value for key, value in submission.items() if key in ContractSubmission.model_fields})
    return result


def _public_snapshot(db, user, contract, snapshot):
    from .business_records import SENSITIVE_ROLES
    from .business_record_pricing import GIFT_READERS, GIFT_COST_READERS, _policy_view
    from .business_record_privacy import redact_contract_data
    data = deepcopy(snapshot)
    for key in ('approved_snapshot', 'corrections', 'events', 'actions', 'progress', 'handover', 'effective_contract'):
        data.pop(key, None)
    if user.role not in SENSITIVE_ROLES:
        for key in ('office_data', 'office_approved_data', 'office_approval_note', 'cost_cents', 'profit_cents', 'gift_cost_cents', 'price_note'):
            data.pop(key, None)
    terms = data.get('terms') or {}
    if user.role not in GIFT_COST_READERS:
        terms.pop('gift_cost_total_cents', None)
        for item in [*terms.get('gifts_snapshot', []), *(terms.get('submission_data') or {}).get('accessory_snapshot', [])]:
            for key in ('unit_cost_cents', 'cost_cents', 'source_ref'):
                item.pop(key, None)
        terms.get('submission_data', {}).pop('towing_cost_cents', None)
    if user.role not in GIFT_READERS:
        for key in ('manager_approval_note', 'general_manager_approval_note', 'approval_note'):
            data.pop(key, None)
        for key in ('gift_total_cents', 'gift_excess_cents', 'price_below_cents', 'special_note'):
            terms.pop(key, None)
        for key in ('control_price_cents', 'note'):
            terms.get('price_snapshot', {}).pop(key, None)
        for item in terms.get('gifts_snapshot', []):
            for key in ('unit_price_cents', 'amount_cents'):
                item.pop(key, None)
    price = terms.get('price_snapshot') or {}
    if price.get('gift_policy'):
        price['gift_policy'] = _policy_view(price['gift_policy'], user, terms.get('gift_batch_id'))
    return redact_contract_data(db, user, contract, data)


def correction_view(db, user, contract, row):
    from .business_records import capabilities
    from .employee_handover import was_contract_handler
    from .business_record_privacy import contract_privacy, redact_personal_values
    caps = capabilities(user)
    independent = user.id not in {row.assigned_to, row.submitted_by} and not was_contract_handler(db, user, contract)
    actions = []
    if row.status == 'draft' and user.id == row.assigned_to and user.role == row.assigned_role:
        actions.append('submit')
    if row.status in ACTIVE and user.role in {'admin', 'manager', 'general_manager', 'group_deputy_manager'} and not getattr(user, '_aggregate_scope', False):
        actions += ['cancel', 'reassign']
    if row.status == 'submitted' and caps['manager_approve'] and independent:
        actions += ['manager_approve', 'reject']
    if row.status == 'manager_approved' and caps['approve'] and independent and user.id != row.manager_approved_by:
        actions += ['approve', 'reject']
    if row.status == 'deputy_pending' and caps['deputy_approve'] and independent and user.id not in {row.manager_approved_by, row.general_manager_approved_by}:
        actions += ['deputy_approve', 'reject']
    if row.status == 'approved' and user.role in {'finance', 'admin'} and not contract_privacy(db, user, contract)['masked']:
        actions.append('print')
    person = db.get(User, row.assigned_to)
    snapshot = row.approved_snapshot or row.draft.get('snapshot') or row.previous_snapshot
    public_snapshot = _public_snapshot(db, user, contract, snapshot)
    draft_input = _input(public_snapshot)
    if contract_privacy(db, user, contract)['masked']:
        draft_input = redact_personal_values(draft_input)
    data = {key: plain(row)[key] for key in ('id', 'version', 'contract_id', 'previous_id', 'status', 'reason',
        'assigned_to', 'assigned_role', 'created_at', 'approved_at', 'approved_on', 'sale_delta_cents', 'cash_delta_cents', 'events')}
    data.update(status_label=LABELS[row.status], assigned_name=person.display_name if person else '', actions=actions,
        draft_input=draft_input, snapshot=public_snapshot,
        notice='合同更正独立留档；原交车、发票、收款及已核价事实保留，不再计一笔订单或交车。')
    return redact_personal_values(data, [row.previous_snapshot, row.draft, row.approved_snapshot]) if contract_privacy(db, user, contract)['masked'] else data


def correction_summary(db, user, contract):
    rows = correction_rows(db, contract)
    return {'items': [correction_view(db, user, contract, row) for row in rows],
        'latest_effective_id': next((row.id for row in rows if row.status == 'approved'), None),
        'active_id': next((row.id for row in rows if row.status in ACTIVE), None)}


@router.get('/contracts/{key}/corrections')
def list_corrections(key: int, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    contract = get_contract(db, user, key)
    result = correction_summary(db, user, contract)
    snapshot = effective_snapshot(db, contract)
    result.update(targets=targets(db, contract), latest_effective_snapshot=_public_snapshot(db, user, contract, snapshot) if snapshot else None)
    return result


@router.post('/contracts/{key}/corrections', status_code=201)
def request_correction(key: int, body: CorrectionRequest, request: Request,
        db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version, require_read
    _manual(request); require_read(user)
    if user.role not in {'admin', 'manager', 'general_manager', 'group_deputy_manager'}:
        raise HTTPException(403, '请由销售经理、总经理或集团副总经理发起合同更正')
    contract = get_contract(db, user, key)
    def perform():
        _check_version(contract, body.version)
        if contract.status != 'approved' or not contract.approved_snapshot:
            raise HTTPException(409, '只有已批准合同走独立更正；未批准合同请使用原退回修改入口')
        if contract.archived_at:
            raise HTTPException(409, '请先恢复归档合同再发起更正')
        from .business_record_delivery import _returns
        if any(item.status in {'submitted', 'approved'} for item in _returns(db, contract)):
            raise HTTPException(409, '合同已有办理中或批准的退车，不能同时更正交易')
        if any(row.status in ACTIVE for row in correction_rows(db, contract)):
            raise HTTPException(409, '本合同已有办理中的更正，请先完成或退回该更正')
        _target(db, contract, body.target_user_id, body.target_role)
        previous = latest_correction(db, contract)
        source = effective_snapshot(db, contract)
        row = RecordContractCorrection(store_id=contract.store_id, contract_id=key,
            previous_id=previous.id if previous else None, status='draft', requested_by=user.id,
            assigned_to=body.target_user_id, assigned_role=body.target_role, reason=body.note,
            previous_snapshot=source, draft={}, events=[])
        _event(row, user, 'requested', body.note)
        db.add(row); contract.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_correction_request', 'record_contract', key,
            after={'correction_id': row.id, 'assigned_to': row.assigned_to, 'assigned_role': row.assigned_role}, reason=body.note)
        return correction_view(db, user, contract, row)
    return _run(db, user, body.request_id, f'contract:{key}:correction_request', body.model_dump(mode='json'), perform)


def _frozen_selected(db, source, selections):
    """A trusted correction snapshot authorizes only its original exact gift batch."""
    from .business_record_pricing_models import RecordGiftPrice, RecordPriceBatch
    batch_id = source['terms'].get('gift_batch_id')
    if not selections:
        return [], 0, 0
    batch = RecordPriceBatch.__table__
    metadata = db.execute(select(batch.c.store_id, batch.c.brand).where(batch.c.id == batch_id, batch.c.kind == 'gift')).mappings().one_or_none()
    if not metadata or not (metadata['brand'] == source['brand'] or not metadata['brand'] and metadata['store_id'] == source['store_id']):
        raise HTTPException(409, '更正的冻结赠品批次来源不匹配')
    table = RecordGiftPrice.__table__
    available = {row['id']: dict(row) for row in db.execute(select(table).where(table.c.batch_id == batch_id,
        table.c.store_id == metadata['store_id'])).mappings()}
    result, total, cost_total, seen = [], 0, 0, set()
    for choice in selections:
        item = available.get(choice.price_id)
        if item is None or choice.price_id in seen:
            raise HTTPException(422, '请选择更正版本冻结目录内的项目，每个项目合并数量')
        seen.add(choice.price_id)
        amount = None if item['unit_price_cents'] is None else item['unit_price_cents'] * choice.quantity
        cost = None if item['unit_cost_cents'] is None else item['unit_cost_cents'] * choice.quantity
        if any(value is not None and value > 999999999999 for value in (amount, cost)):
            raise HTTPException(422, '精品金额超出范围')
        total = None if total is None or amount is None else total + amount
        cost_total = None if cost_total is None or cost is None else cost_total + cost
        if any(value is not None and value > 999999999999 for value in (total, cost_total)):
            raise HTTPException(422, '精品合计金额超出范围')
        result.append({'price_id': choice.price_id, 'name': item['name'], 'quantity': choice.quantity,
            'unit_price_cents': item['unit_price_cents'], 'amount_cents': amount,
            'unit_cost_cents': item['unit_cost_cents'], 'cost_cents': cost,
            **{key: item[key] for key in ('brand', 'unit', 'applicable_models', 'source_ref')}})
    return result, total, cost_total


def _prepare(db, user, contract, revision, body):
    from .business_record_pricing import prepare_submission, _validate_vehicle_gifts, gift_policy_assessment, pricing_settings
    from .business_record_inventory import prepare_contract_inventory
    source = revision.previous_snapshot
    old_terms = source.get('terms') or {}
    old_channel = (old_terms.get('submission_data') or {}).get('sales_channel', 'retail')
    if body.salesperson_id != contract.salesperson_id or body.submission_data.sales_channel != old_channel:
        raise HTTPException(422, '更正保留原经办业绩及销售渠道归属，不可转为另一笔销售')
    if body.submission_data.wholesale_channel_id != (old_terms.get('submission_data') or {}).get('wholesale_channel_id'):
        raise HTTPException(422, '更正保留原二级渠道归属')
    from .business_record_privacy import contract_privacy, mask_phone, mask_id, ID_KEYS, PHONE_KEYS
    from .business_record_pricing import GIFT_COST_READERS
    if user.role not in GIFT_COST_READERS:
        original_cost = (old_terms.get('submission_data') or {}).get('towing_cost_cents')
        if body.submission_data.towing_cost_cents not in (None, original_cost):
            raise HTTPException(403, '当前岗位不可更改隐藏的拖车成本')
        body.submission_data.towing_cost_cents = original_cost
    if contract_privacy(db, user, contract)['masked']:
        if body.customer_phone == mask_phone(source.get('customer_phone')):
            body.customer_phone = source.get('customer_phone', '')
        elif '*' in body.customer_phone:
            raise HTTPException(422, '更改客户电话时请填写完整新号码；原脱敏号码保持不变即可')
        form = dict(body.form_data)
        for key in ID_KEYS | PHONE_KEYS:
            original = (source.get('form_data') or {}).get(key, '')
            masked = mask_phone(original) if key in PHONE_KEYS else mask_id(original)
            if form.get(key) == masked:
                form[key] = original
            elif '*' in form.get(key, ''):
                raise HTTPException(422, '更改电话或证件时请填写完整新信息；原脱敏信息保持不变即可')
        body.form_data = form
    if body.vehicle_price_id != (old_terms.get('price_snapshot') or {}).get('id'):
        return prepare_submission(db, user, body, inventory_existing=contract, allow_vehicle_change=True)
    if not old_terms.get('price_snapshot'):
        raise HTTPException(409, '原合同缺少冻结价格，请选择当前真实车型重新核对更正')
    inventory = prepare_contract_inventory(db, user, body, existing=contract, allow_vehicle_change=True)
    price = deepcopy(old_terms['price_snapshot'])
    batch = old_terms.get('gift_batch_id')
    _validate_vehicle_gifts(price, batch, body.gift_items, old_terms.get('gifts_snapshot', []))
    gifts, total, costs = _frozen_selected(db, source, body.gift_items)
    accessories, accessory_total, _ = _frozen_selected(db, source, body.accessory_items)
    if accessories and accessory_total is None:
        raise HTTPException(422, '有偿精品缺少冻结售价，请重新核对目录')
    form = dict(body.form_data)
    settings = pricing_settings(db)
    sellers = [item for item in (settings.profile if settings else {}).get('sellers', []) if item['name'] == form.get('seller_name')]
    if len(sellers) != 1:
        raise HTTPException(422, '请从本店有效卖方公司中选择')
    if inventory:
        form.update({key: inventory['snapshot'][key] for key in ('exterior_color', 'interior_color')})
    if any(not form.get(key) or len(form[key]) > 100 for key in ('exterior_color', 'interior_color')):
        raise HTTPException(422, '请填写经核对的厂家内外饰颜色（最多100字）')
    if form.get('buyer_document_name', '身份证') not in {'身份证', '护照', '驾照'}:
        raise HTTPException(422, '请核对买方证件类型')
    person = db.get(User, contract.salesperson_id)
    form.setdefault('seller_phone', settings.profile.get('sales_contacts', {}).get(str(person.id), ''))
    form.update(seller_address=sellers[0].get('address') or settings.profile.get('address', ''),
        seller_agent=person.display_name, quantity='1')
    submission = body.submission_data.model_dump()
    if submission.get('wholesale_channel_id') != (old_terms.get('submission_data') or {}).get('wholesale_channel_id'):
        raise HTTPException(422, '更正保留原二级渠道归属')
    for key in ('wholesale_channel_name',):
        if key in (old_terms.get('submission_data') or {}):
            submission[key] = old_terms['submission_data'][key]
    submission.update(accessory_snapshot=accessories, accessory_total_cents=accessory_total)
    if inventory:
        submission['is_cash_vehicle'] = inventory['snapshot']['is_cash_vehicle']
        submission['inventory_snapshot'] = deepcopy(inventory['snapshot'])
    return {'price': price, 'gifts': gifts, 'gift_batch_id': batch, 'gift_total_cents': total,
        'gift_cost_total_cents': costs, 'gift_pricing_basis': old_terms.get('gift_pricing_basis', 'separate-cost-v1'),
        'gift_policy_check': gift_policy_assessment(price.get('gift_policy'), costs), 'form_data': form,
        'brand': source['brand'], 'model': price['series'] + ' ' + price['model'], 'submission_data': submission,
        'price_below_cents': max(0, price['control_price_cents'] - body.sale_price_cents), 'inventory': inventory}


@router.post('/contracts/{key}/corrections/{correction_id}/submit')
def submit_correction(key: int, correction_id: int, body: CorrectionSubmit, request: Request,
        db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    _manual(request)
    contract = get_contract(db, user, key)
    payload = body.model_dump(mode='json')
    def perform():
        row = _revision(db, contract, correction_id)
        _check_version(row, body.version)
        if row.status != 'draft' or user.id != row.assigned_to or user.role != row.assigned_role:
            raise HTTPException(403, '仅本次指定岗位经办人可以修改并提交待更正版本')
        _target(db, contract, row.assigned_to, row.assigned_role)
        prepared = _prepare(db, user, contract, row, body)
        snapshot = deepcopy(row.previous_snapshot)
        values = body.model_dump(mode='json', exclude={'request_id', 'version', 'vehicle_price_id', 'inventory_row_id',
            'gift_items', 'accessory_items', 'submission_data', 'gift_excess_cents', 'note'})
        snapshot.update(values)
        snapshot.update(brand=prepared['brand'], model=prepared['model'], form_data=prepared['form_data'],
            gift_description='；'.join(item['name'] + ' × ' + str(item['quantity']) for item in prepared['gifts']))
        special = bool((row.previous_snapshot.get('terms') or {}).get('special') or prepared['price_below_cents'] or body.gift_excess_cents or prepared['gift_policy_check']['requires_special'])
        if special and not body.note.strip():
            raise HTTPException(422, '超限价或超赠送更正须填写特殊申请说明')
        terms = {'price_snapshot': prepared['price'], 'gift_batch_id': prepared['gift_batch_id'],
            'gifts_snapshot': prepared['gifts'], 'gift_total_cents': prepared['gift_total_cents'],
            'gift_cost_total_cents': prepared['gift_cost_total_cents'], 'gift_pricing_basis': prepared['gift_pricing_basis'],
            'submission_data': prepared['submission_data'], 'price_below_cents': prepared['price_below_cents'],
            'gift_excess_cents': body.gift_excess_cents, 'special': special, 'special_note': body.note if special else ''}
        if prepared.get('inventory'):
            inventory = prepared['inventory']
            snapshot['vin'] = inventory['snapshot']['vin']
            terms['inventory_snapshot'] = deepcopy(inventory.get('snapshot') or {})
        snapshot['terms'] = terms
        from .business_record_pdf import validate_contract_print_data
        try:
            validate_contract_print_data(snapshot)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        row.draft = {'snapshot': snapshot, 'inventory': prepared.get('inventory'),
            'inventory_row_id': body.inventory_row_id, 'note': body.note}
        row.submitted_by, row.submitted_at = user.id, utcnow()
        row.status = 'manager_approved' if row.assigned_role == 'manager' else 'submitted'
        if row.assigned_role == 'manager':
            row.manager_approved_by, row.manager_approved_at = user.id, utcnow()
        contract.updated_at = utcnow(); _event(row, user, 'submitted', body.note); db.flush()
        audit(db, user.id, 'record_correction_submit', 'record_contract', key, after={'correction_id': row.id, 'status': row.status})
        return correction_view(db, user, contract, row)
    return _run(db, user, body.request_id, f'contract:{key}:correction:{correction_id}:submit', payload, perform)


def _review(key, correction_id, body, request, db, user, action):
    from .business_records import get_contract, _manual, _run, _check_version
    _manual(request)
    contract = get_contract(db, user, key)
    def perform():
        row = _revision(db, contract, correction_id)
        _check_version(row, body.version)
        if action not in correction_view(db, user, contract, row)['actions']:
            raise HTTPException(403, '当前岗位、经办关系或更正状态不允许此审批；不能自批')
        if action == 'cancel':
            if not body.note.strip():
                raise HTTPException(422, '请填写撤销更正原因')
            row.status = 'cancelled'
        elif action in {'reject', 'reassign'}:
            _target(db, contract, body.target_user_id, body.target_role)
            row.assigned_to, row.assigned_role, row.status = body.target_user_id, body.target_role, 'draft'
            row.manager_approved_by = row.manager_approved_at = None
            row.general_manager_approved_by = row.general_manager_approved_at = None
            row.deputy_approved_by = row.deputy_approved_at = None
        elif action == 'manager_approve':
            from types import SimpleNamespace
            from .business_record_pricing import gift_policy_assessment, frozen_gift_cost
            draft = deepcopy(row.draft)
            terms = draft['snapshot']['terms']
            terms['gift_excess_cents'] = body.gift_excess_cents
            policy = gift_policy_assessment(terms['price_snapshot'].get('gift_policy'), frozen_gift_cost(SimpleNamespace(**terms)))
            terms['special'] = bool((row.previous_snapshot.get('terms') or {}).get('special')
                or terms['price_below_cents'] or body.gift_excess_cents or policy['requires_special'])
            if terms['special'] and not body.note.strip():
                raise HTTPException(422, '超限价或超赠送更正须填写特殊申请说明')
            terms['special_note'] = body.note if terms['special'] else ''
            row.draft = draft
            row.manager_approved_by, row.manager_approved_at, row.status = user.id, utcnow(), 'manager_approved'
        elif action == 'approve':
            row.general_manager_approved_by, row.general_manager_approved_at = user.id, utcnow()
            if row.draft['snapshot']['terms']['special']:
                row.status = 'deputy_pending'
            else:
                _finish(db, user, contract, row)
        else:
            row.deputy_approved_by, row.deputy_approved_at = user.id, utcnow()
            _finish(db, user, contract, row)
        _event(row, user, action, body.note); contract.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_correction_' + action, 'record_contract', key,
            after={'correction_id': row.id, 'status': row.status, 'sale_delta_cents': row.sale_delta_cents}, reason=body.note)
        return correction_view(db, user, contract, row)
    return _run(db, user, body.request_id, f'contract:{key}:correction:{correction_id}:{action}', body.model_dump(mode='json'), perform)


def _finish(db, user, contract, row):
    from .business_record_inventory import prepare_contract_inventory, save_contract_inventory
    from .business_record_pdf import TEMPLATE_VERSION
    snapshot = deepcopy(row.draft['snapshot'])
    from .business_record_delivery import _returns
    if any(item.status in {'submitted', 'approved'} for item in _returns(db, contract)):
        raise HTTPException(409, '合同已有办理中或批准的退车，请先处理退车状态')
    offered = _input(snapshot)
    offered['inventory_row_id'] = row.draft.get('inventory_row_id')
    # This rechecks current VIN occupancy without regenerating any frozen price.
    body = CorrectionSubmit(request_id='revision-validation', version=row.version, **offered)
    inventory = prepare_contract_inventory(db, user, body, existing=contract, allow_vehicle_change=True)
    if inventory:
        save_contract_inventory(db, contract, inventory)
    original = row.previous_snapshot
    row.sale_delta_cents = snapshot['sale_price_cents'] - original['sale_price_cents']
    def cash_value(value):
        cash = ((value.get('terms') or {}).get('submission_data') or {}).get('is_cash_vehicle')
        return value['sale_price_cents'] if cash is True else 0 if cash is False else None
    old_cash, new_cash = cash_value(original), cash_value(snapshot)
    row.cash_delta_cents = None if None in (old_cash, new_cash) else new_cash - old_cash
    row.status, row.approved_at, row.approved_on = 'approved', utcnow(), today()
    snapshot.update(status='approved', approved_at=row.approved_at.isoformat(), approved_by=user.id,
        correction_id=row.id, correction_previous_id=row.previous_id, template_version=TEMPLATE_VERSION,
        correction_reason=row.reason, print_layout_version='full-v218')
    for name in ('manager', 'general_manager', 'deputy'):
        snapshot[name + '_approved_by'] = getattr(row, name + '_approved_by')
        timestamp = getattr(row, name + '_approved_at')
        snapshot[name + '_approved_at'] = timestamp.isoformat() if timestamp else None
    # Existing financial facts deliberately remain attached to the original sale.
    row.approved_snapshot = snapshot


@router.post('/contracts/{key}/corrections/{correction_id}/manager-approve')
def manager_approve(key: int, correction_id: int, body: CorrectionManagerApproval, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review(key, correction_id, body, request, db, user, 'manager_approve')


@router.post('/contracts/{key}/corrections/{correction_id}/approve')
def approve(key: int, correction_id: int, body: Action, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review(key, correction_id, body, request, db, user, 'approve')


@router.post('/contracts/{key}/corrections/{correction_id}/deputy-approve')
def deputy_approve(key: int, correction_id: int, body: Action, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review(key, correction_id, body, request, db, user, 'deputy_approve')


@router.post('/contracts/{key}/corrections/{correction_id}/reject')
def reject(key: int, correction_id: int, body: CorrectionRequest, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review(key, correction_id, body, request, db, user, 'reject')


@router.post('/contracts/{key}/corrections/{correction_id}/cancel')
def cancel(key: int, correction_id: int, body: Action, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review(key, correction_id, body, request, db, user, 'cancel')


@router.post('/contracts/{key}/corrections/{correction_id}/reassign')
def reassign(key: int, correction_id: int, body: CorrectionRequest, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _review(key, correction_id, body, request, db, user, 'reassign')
