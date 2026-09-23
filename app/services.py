from datetime import date, datetime
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from .models import MODULES, Vehicle, Sale, Repair, Policy, CashEntry, AuditLog, User
from .schemas import INPUTS, ActionInput
from .security import require_module
from .db import today, utcnow

LINK_FIELDS = {'sales':'sale_id','repairs':'repair_id','policies':'policy_id','vehicles':'vehicle_id'}
PREFIXES = {'vehicles':'V','sales':'S','repairs':'R','policies':'P','cash':'C'}


def plain(row) -> dict:
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime): value = value.isoformat()+'Z'
        elif isinstance(value, date): value = value.isoformat()
        result[column.name] = value
    return result


def audit(db, user_id, action, module, record_id, before=None, after=None, reason=''):
    store = (after or before or {}).get('store_id', db.info.get('write_store', 1))
    if module in {'users','stores'}: store = 0
    db.add(AuditLog(store_id=store or 0, actor_id=user_id, action=action, entity_type=module, entity_id=record_id,
                    before_data=before, after_data=after, reason=reason))


def serialize(row, module: str, user: User | None = None, db: Session | None = None):
    data = plain(row)
    for key, value in list(data.items()):
        if key.endswith('_cents'):
            data[key[:-6]] = format(Decimal(value)/100, '.2f') if value is not None else None
    if module == 'vehicles':
        sale = db.scalar(select(Sale).where(Sale.active_vehicle_id == row.id)) if db is not None else None
        data['stock_state'] = ('sold' if sale.sale_stage == 'delivered' else 'reserved') if sale else 'available'
        if db is not None:
            from .flow_models import VehicleHold
            hold = db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id == row.id))
            if hold: data['stock_state'] = 'sold' if hold.delivered else 'reserved'
            from .vehicle_transfer_analytics import availability_flags
            flag=availability_flags(db).get(row.id)
            if flag:data['stock_state']=flag
        if row.approval_state != 'approved': data['stock_state'] = 'inactive'
        data['stock_age_days'] = max(0, (today()-row.business_date).days) if data['stock_state'] not in {'sold','inactive'} else 0
        if user and user.role in {'sales','inventory'}:
            for field in ('purchase_cost_cents','purchase_cost','supplier','note'):
                data.pop(field, None)
            if user.role=='inventory':
                data.pop('list_price',None);data.pop('list_price_cents',None)
    if module == 'sales' and db is not None:
        vehicle = db.get(Vehicle, row.vehicle_id)
        data['vehicle_label'] = f'{vehicle.vin} · {vehicle.model}' if vehicle else ''
        if user and user.role == 'sales':
            data.pop('purchase_cost_snapshot', None)
            data.pop('purchase_cost_snapshot_cents', None)
    if module == 'repairs':
        data['billed_amount_cents'] = row.labor_amount_cents + row.parts_amount_cents - row.discount_cents
        data['billed_amount'] = format(Decimal(data['billed_amount_cents'])/100, '.2f')
    if module == 'cash':
        data['related_type'], data['related_id'] = 'none', None
        for key, field in LINK_FIELDS.items():
            if data[field] is not None:
                data['related_type'], data['related_id'] = key, data[field]
    data['ref'] = f'{PREFIXES[module]}-{row.id}'
    return data


def readable_query(user: User, module: str):
    require_module(user, module)
    query = select(MODULES[module])
    if module == 'vehicles' and user.role == 'sales':
        query = query.where(Vehicle.approval_state == 'approved')
    return query


def get_record(db, user, module, record_id, write=False):
    require_module(user, module, write)
    row = db.scalar(readable_query(user, module).where(MODULES[module].id == record_id))
    if row is None:
        raise HTTPException(404, '记录不存在或不可访问')
    return row


def validate_relations(db: Session, module: str, values: dict, approving=False):
    links = []
    if module == 'sales':
        links.append(('vehicles',values['vehicle_id']))
    if module == 'repairs' and values.get('policy_id'):
        links.append(('policies',values['policy_id']))
    if module == 'cash':
        links.extend((key,values[field]) for key,field in LINK_FIELDS.items() if values.get(field))
    for target, record_id in links:
        row = db.get(MODULES[target], record_id)
        if row and db.info.get('write_store') and row.store_id != db.info['write_store']:
            raise HTTPException(422, '关联记录必须属于同一家门店')
        if not row or row.approval_state == 'void':
            raise HTTPException(422, '关联记录不存在或已作废')
        if (approving or module == 'sales') and row.approval_state != 'approved':
            raise HTTPException(422, '关联业务必须先审核通过')
        if module == 'sales':
            from .flow_models import VehicleHold
            if db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id == row.id)):
                raise HTTPException(409, '该车辆已由流程订单占用，不可重复销售')
        if module == 'sales' and row.business_date > values['business_date']:
            raise HTTPException(422, '订单日期不能早于该车入库日期')


def input_values(module: str, body: dict) -> dict:
    parsed = INPUTS[module].model_validate(body)
    values = parsed.model_dump()
    for key, value in list(values.items()):
        if isinstance(value, Decimal):
            values.pop(key)
            values[key+'_cents'] = int(value*100)
    if module == 'cash':
        related_type = values.pop('related_type')
        related_id = values.pop('related_id')
        for field in LINK_FIELDS.values(): values[field] = None
        if related_type != 'none': values[LINK_FIELDS[related_type]] = related_id
    return values


def create_record(db, user, module, body):
    require_module(user, module, True)
    values = input_values(module, body)
    validate_relations(db, module, values)
    row = MODULES[module](**values, created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user.id, 'create', module, row.id, after=plain(row))
    db.commit()
    return row


def check_version(row, version):
    if row.version != version:
        raise HTTPException(409, '此记录已被其他人修改，请刷新后重试；未覆盖他人的修改')


def may_edit(user, row):
    if user.role not in {'admin','manager'} and row.created_by != user.id:
        raise HTTPException(403, '只能修改或提交自己录入的单据')


def update_record(db, user, module, record_id, version, body):
    row = get_record(db, user, module, record_id, True)
    may_edit(user, row)
    check_version(row, version)
    if row.approval_state not in {'draft','rejected'}:
        raise HTTPException(409, '仅草稿或退回单据可以修改；审核通过的单据不可直接改账')
    values = input_values(module, body)
    validate_relations(db, module, values)
    before = plain(row)
    for key,value in values.items(): setattr(row,key,value)
    db.flush()
    audit(db,user.id,'update',module,row.id,before,plain(row))
    db.commit()
    return row


def act_record(db, user, module, record_id, action, request: ActionInput):
    row = get_record(db, user, module, record_id)
    check_version(row, request.version)
    before = plain(row)
    from .flow_models import VehicleHold, PaymentLink
    if module == 'cash' and (row.category.startswith(('group_member_','procurement_','benefit_','vehicle_procurement_','interstore_clearing','business_finance_','service_')) or db.scalar(select(PaymentLink.id).where(PaymentLink.cash_id == row.id))):
        raise HTTPException(409, '此款项由业务流程确认，不可从旧入口修改或作废')
    if module == 'vehicles' and action=='void':
        from .transfer_service import authority
        from .vehicle_transfer_models import VehicleCustody
        with authority(db,user,{'admin','manager','inventory'}):
            if db.scalar(select(VehicleCustody.id).where(VehicleCustody.vin==row.vin.upper())):
                raise HTTPException(409,'此VIN已有采购或跨店保管事实，须由原业务退货或调拨处理，不可从旧入口作废')
    if module == 'vehicles' and action == 'void' and db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id == row.id)):
        raise HTTPException(409, '该车辆已由流程订单占用，不能作废')
    if action == 'submit':
        require_module(user, module, True)
        may_edit(user,row)
        if row.approval_state not in {'draft','rejected'}:
            raise HTTPException(409, '仅草稿或退回状态可以提交')
        row.approval_state = 'submitted'
    elif action in {'approve','reject'}:
        if user.role not in {'admin','manager'}:
            raise HTTPException(403, '需要店长或管理员审核')
        if row.approval_state != 'submitted':
            raise HTTPException(409, '只能审核已提交的单据')
        if row.created_by == user.id and user.role != 'admin':
            raise HTTPException(403, '不能审核自己录入的单据，请另一位店长或管理员复核')
        if action == 'approve':
            validate_relations(db,module,{column.name:getattr(row,column.name) for column in row.__table__.columns},True)
            if module == 'sales':
                # Lock where available; UNIQUE active_vehicle_id is the final concurrency invariant.
                vehicle = db.scalar(select(Vehicle).where(Vehicle.id == row.vehicle_id).with_for_update())
                if vehicle.approval_state != 'approved':
                    raise HTTPException(409, '该车辆尚未审核入库')
                from .vehicle_transfer_service import assert_vehicle_available
                assert_vehicle_available(db,user,vehicle)
                occupied = db.scalar(select(Sale.id).where(Sale.active_vehicle_id == row.vehicle_id))
                if occupied or db.scalar(select(VehicleHold).where(VehicleHold.vehicle_id==vehicle.id)):
                    raise HTTPException(409, '该车已有生效订单，不能重复占用库存')
                vehicle.updated_at=utcnow()
                row.active_vehicle_id = row.vehicle_id
                row.purchase_cost_snapshot_cents = vehicle.purchase_cost_cents
            row.approval_state = 'approved'
        else:
            row.approval_state = 'rejected'
    elif action == 'advance':
        require_module(user, module, True)
        may_edit(user,row)
        if row.approval_state != 'approved' or module not in {'sales','repairs'}:
            raise HTTPException(409, '仅已审核销售/维修单据能确认交付/完工')
        effective = request.effective_date
        if not effective or not row.business_date <= effective <= today():
            raise HTTPException(422, '请填写不早于业务日期且不晚于今天的完成日期')
        if module == 'sales':
            if row.sale_stage != 'ordered': raise HTTPException(409,'该单已交车')
            row.sale_stage, row.delivery_date = 'delivered', effective
        else:
            if row.repair_stage != 'open': raise HTTPException(409,'该单已完工')
            row.repair_stage, row.completion_date = 'completed', effective
    elif action == 'void':
        if user.role not in {'admin','manager'}:
            raise HTTPException(403, '仅店长或管理员可以作废，必须注明原因')
        if row.approval_state == 'void': raise HTTPException(409,'已经作废')
        if module == 'vehicles' and db.scalar(select(Sale.id).where(Sale.active_vehicle_id == row.id)):
            raise HTTPException(409,'该车已有生效订单，不能作废入库记录')
        if module in LINK_FIELDS and db.scalar(select(CashEntry.id).where(getattr(CashEntry,LINK_FIELDS[module]) == row.id, CashEntry.approval_state == 'approved')):
            raise HTTPException(409,'存在已审核的关联收付款，须先复核处理关联流水，不能直接作废业务')
        if module == 'policies' and db.scalar(select(Repair.id).where(Repair.policy_id == row.id, Repair.approval_state == 'approved')):
            raise HTTPException(409,'保单关联有效维修单，不能直接作废')
        row.approval_state = 'void'
        if module == 'sales': row.active_vehicle_id = None
    else:
        raise HTTPException(404, '未知工作流操作')
    db.flush()
    reason = request.reason + (' [管理员自审]' if action == 'approve' and row.created_by == user.id else '')
    audit(db,user.id,action,module,row.id,before,plain(row),reason)
    db.commit()
    return row
