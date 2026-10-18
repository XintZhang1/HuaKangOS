"""Human-published inventory, scoped candidates and atomic contract VIN claims."""
import hashlib
import re
from datetime import date
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select, func
from .config import settings
from .db import get_db, get_write_db, utcnow
from .models import Store
from .security import get_user
from .tenancy import single_store
from .services import audit
from .business_records_schemas import Command
from .business_records_models import SalesContract
from .business_record_inventory_models import (RecordInventoryFile, RecordInventoryBatch,
    RecordInventoryRow, RecordInventoryCurrent, RecordInventoryClaim)
from .business_record_inventory_schemas import InventoryPreview, InventoryPublish
from .business_record_inventory_parser import read_inventory_workbook, sheet_proposals, mapped_preview, VIN
from .business_record_brand_catalog import store_brand, catalog_state, catalog_rows
from .business_record_gift_import import canonical_brand
from .file_security import policy_mode, scan_clamav
from .private_files import publish

router = APIRouter(prefix='/api/business-records/inventory', tags=['业务记录车辆库存'])
WRITERS = {'admin', 'clerk', 'general_manager', 'group_deputy_manager'}
MANAGEMENT_READERS = WRITERS | {'group_deputy_manager', 'chairman', 'store_admin'}
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _access(user, *, write=False):
    from .business_records import require_read
    require_read(user)
    if getattr(user, '_aggregate_scope', False):
        raise HTTPException(403, '请切换到具体授权门店查看或上传库存')
    if write and user.role not in WRITERS:
        raise HTTPException(403, '库存表由本店内勤、总经理、集团副总经理或系统管理员上传并核对')


def current_inventory(db):
    return db.scalar(select(RecordInventoryCurrent).where(
        RecordInventoryCurrent.store_id == single_store(db), RecordInventoryCurrent.brand == store_brand(db)))


def _batch_summary(batch):
    return {'id': batch.id, 'sheet': batch.sheet, 'brand': batch.brand,
            'as_of_date': batch.as_of_date.isoformat(), 'row_count': batch.row_count,
            'pending_count': len(batch.mapping.get('_pending_rows', [])),
            'excluded_count': batch.excluded_count, 'created_at': batch.created_at.isoformat() + 'Z'}


@router.get('/catalog')
def inventory_catalog(db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    current = current_inventory(db)
    batch = db.get(RecordInventoryBatch, current.batch_id) if current else None
    return {'brand': store_brand(db), 'store_id': single_store(db),
            'version': current.version if current else 0, 'enabled': current is not None,
            'current': _batch_summary(batch) if batch else None,
            'can_upload': user.role in WRITERS, 'can_manage': user.role in MANAGEMENT_READERS,
            'notice': '按最新已发布库存查找车辆；原合同及旧库存版本保留历史。'}


def _file(db, user, key):
    _access(user, write=True)
    item = db.scalar(select(RecordInventoryFile).where(RecordInventoryFile.id == key,
        RecordInventoryFile.store_id == single_store(db)))
    if item is None:
        raise HTTPException(404, '库存原件不存在或不属于当前门店')
    if item.created_by != user.id:
        raise HTTPException(403, '请由本次原表上传者核对映射并确认发布')
    if item.brand != store_brand(db, required=True):
        raise HTTPException(409, '门店品牌已变化，请重新上传当前品牌库存')
    return item


@router.post('/uploads', status_code=201)
def upload_inventory(request: Request, file: UploadFile = File(...), request_id: str = Form(...),
                     db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run
    from .business_record_invoices import _safe
    _manual(request); _access(user, write=True); Command(request_id=request_id)
    filename = file.filename or ''
    if len(filename) > 180 or re.search(r'[\\/\x00-\x1f:]', filename) or not filename.lower().endswith('.xlsx'):
        raise HTTPException(422, '请上传名称有效的xlsx库存表')
    content = file.file.read(10 * 1024 * 1024 + 1)
    proposals = sheet_proposals(read_inventory_workbook(content))
    digest = hashlib.sha256(content).hexdigest()
    def perform():
        mode = policy_mode()
        state, code = ('structure_only', 'structure_only') if mode == 'structure_only' else ('quarantined', 'awaiting_scan')
        if mode == 'clamav':
            result = scan_clamav(content, settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)
            state, code = result.state, result.code
        try:
            object_key = publish(None, single_store(db), content, len(content), digest) if settings.file_storage_mode == 'private_local' else ''
        except (ValueError, OSError):
            raise HTTPException(503, '库存原件尚未保存，请联系管理员检查存储') from None
        row = RecordInventoryFile(store_id=single_store(db), filename=filename, brand=store_brand(db, required=True),
            content_type=XLSX, size=len(content), sha256=digest, content=b'' if object_key else content,
            object_key=object_key, scan_state=state, scan_code=code, created_by=user.id)
        db.add(row); db.flush()
        result = {'id': row.id, 'filename': filename, 'brand': row.brand, 'available': _safe(row),
                  'scan_state': row.scan_state, 'sheets': proposals}
        audit(db, user.id, 'record_inventory_upload', 'record_inventory_file', row.id,
              after={'sha256': digest, 'size': len(content), 'brand': row.brand})
        return result
    return _run(db, user, request_id, 'inventory:upload', {'filename': filename, 'sha256': digest}, perform)


def _mapped(db, user, item, mapping):
    from .business_record_invoices import _content
    sheets = read_inventory_workbook(_content(item))
    known_brands = {'启源', '长安启源', '引力', '凯程', '长安凯程', '比亚迪', '深蓝', '深蓝汽车'}
    if mapping.sheet in known_brands and canonical_brand(mapping.sheet) != item.brand:
        raise HTTPException(422, '选择的库存工作表品牌与当前门店不符，请切换正确授权门店')
    current_store = db.get(Store, single_store(db))
    # A source label matching another registered store cannot be remapped here.
    other_stores = db.scalars(select(Store).where(Store.id != current_store.id)).all()
    other_labels = {v for store in other_stores for v in (store.name, store.code)}
    own_labels = {current_store.name, current_store.code}
    if (set(mapping.source_owners) - own_labels) & other_labels:
        raise HTTPException(403, '所选来源属于另一个系统门店，请切换该授权门店分别核对发布')
    preview = mapped_preview(sheets, mapping)
    if set(mapping.source_owners) - set(preview['source_owners']):
        raise HTTPException(422, '来源所属店选择不在原表中，请重新预览核对')
    prices = catalog_rows(db, 'vehicle', catalog_state(db)['vehicle_batch_id'])
    by_id = {v['id']: v for v in prices}
    for row in preview['rows'] + preview['pending']:
        price_id = row.pop('vehicle_price_id')
        price = by_id.get(price_id) if price_id else None
        if price_id and price is None:
            preview['errors'].append({'source_row': row['source_row'], 'message': '关联限价已更新或不可见，请重新选择当前车型'})
        row['price_reference'] = {key: price[key] for key in ('family', 'series', 'model')} if price else None
        row['vehicle_price_id'] = price['id'] if price else None
        if price is None:
            row['issues'].append('尚未关联本品牌限价车型，暂不能用于新合同')
    preview['publishable'] = bool(mapping.source_owners) and not preview['errors'] and bool(preview['rows'] or preview['excluded'])
    preview['prices'] = [{key: row[key] for key in ('id', 'family', 'series', 'model')} for row in prices]
    preview['review_defaults'] = _review_defaults(db, mapping, preview, prices, other_labels - own_labels)
    preview['publication_blockers'] = [f"原表第 {error['source_row']} 行：{error['message']}" for error in preview['errors']]
    if not mapping.source_owners:
        preview['publication_blockers'].insert(0, '请勾选本次归入当前门店的原表所属店')
    elif not preview['rows'] and not preview['excluded']:
        preview['publication_blockers'].append('本批没有可发布或可确认排除的车辆；请补齐生产日期后重新预览')
    return preview


def _review_defaults(db, mapping, preview, prices, foreign_labels):
    """Suggest only previously published choices; the uploader submits them anew.

    Never infer a bank's funding type or fuzzy-match a model. A changed field
    layout, conflicting prior group, or removed price keeps the choice blank.
    """
    result = {'source_owners': [], 'funding_map': {}, 'model_groups': [], 'version': None}
    current = current_inventory(db)
    if current is None:
        return result
    batch = db.get(RecordInventoryBatch, current.batch_id)
    prior = batch.mapping
    result['version'] = current.version
    if batch.sheet == mapping.sheet:
        if prior.get('columns', {}).get('owner') == mapping.columns.get('owner'):
            result['source_owners'] = [value for value in prior.get('source_owners', [])
                if value in preview['source_owners'] and value not in foreign_labels]
        if prior.get('columns', {}).get('funding') == mapping.columns.get('funding'):
            result['funding_map'] = {value: kind for value, kind in prior.get('funding_map', {}).items()
                if value in preview['funding_values'] and kind in {'cash', 'third_party'}}
    price_ids = {}
    for price in prices:
        key = tuple(price[field] for field in ('family', 'series', 'model'))
        price_ids.setdefault(key, []).append(price['id'])
    groups = {}
    previous_rows = db.scalars(select(RecordInventoryRow).where(
        RecordInventoryRow.store_id == single_store(db), RecordInventoryRow.batch_id == batch.id)).all()
    for row in previous_rows:
        reference = tuple(row.price_reference[field] for field in ('family', 'series', 'model')) if row.price_reference else None
        groups.setdefault((row.model, row.configuration), set()).add(reference)
    present_groups = {(row['model'], row['configuration']) for row in preview['rows'] + preview['pending']}
    for (model, configuration), references in groups.items():
        if (model, configuration) not in present_groups or len(references) != 1:
            continue
        ids = price_ids.get(next(iter(references)), [])
        if len(ids) == 1:
            result['model_groups'].append({'model': model, 'configuration': configuration, 'vehicle_price_id': ids[0]})
    return result


@router.post('/uploads/{key}/preview')
def preview_inventory(key: int, body: InventoryPreview, request: Request, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import _manual
    _manual(request)
    return _mapped(db, user, _file(db, user, key), body)


@router.post('/uploads/{key}/publish')
def publish_inventory(key: int, body: InventoryPublish, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run, _lock_customer_scope
    _manual(request); _access(user, write=True)
    if body.confirmed_store_id != single_store(db) or canonical_brand(body.confirmed_brand) != store_brand(db, required=True):
        raise HTTPException(409, '确认的门店或品牌已变化，请刷新后重新核对')
    item = _file(db, user, key)
    def perform():
        _lock_customer_scope(db)
        current = current_inventory(db)
        if (current.version if current else 0) != body.version:
            raise HTTPException(409, '当前库存已被其他员工更新，请重新预览本批差异')
        result = _mapped(db, user, item, body.mapping)
        if not result['publishable']:
            raise HTTPException(422, '库存包含未解决的来源或VIN错误，请核对预览后发布')
        batch = RecordInventoryBatch(store_id=single_store(db), file_id=item.id, brand=item.brand,
            sheet=body.mapping.sheet, as_of_date=body.mapping.as_of_date,
            mapping={**body.mapping.model_dump(mode='json'), '_pending_rows': [row['source_row'] for row in result['pending']]}, row_count=result['row_count'],
            excluded_count=result['excluded_count'], created_by=user.id)
        db.add(batch); db.flush()
        for values in result['rows']:
            values = dict(values); values.pop('vehicle_price_id', None)
            if values['production_on']:
                values['production_on'] = date.fromisoformat(values['production_on'])
            db.add(RecordInventoryRow(store_id=single_store(db), batch_id=batch.id, **values))
        if current is None:
            current = RecordInventoryCurrent(store_id=single_store(db), brand=item.brand, batch_id=batch.id)
            db.add(current)
        else:
            current.batch_id = batch.id; current.updated_at = utcnow()
        db.flush()
        response = {'current': _batch_summary(batch), 'version': current.version,
                    'notice': '当前库存已更新；旧库存、已售合同及占用历史均保留。'}
        audit(db, user.id, 'record_inventory_publish', 'record_inventory_batch', batch.id, after=response)
        return response
    return _run(db, user, body.request_id, 'inventory:publish', {'file_id': key, **body.model_dump(mode='json')}, perform)


def _price_for_row(db, row, channel):
    if not row.price_reference:
        return None
    prices = catalog_rows(db, 'vehicle', catalog_state(db, channel)['vehicle_batch_id'], sales_channel=channel)
    matches = [v for v in prices if all(v[k] == row.price_reference[k] for k in ('family', 'series', 'model'))]
    return matches[0] if len(matches) == 1 else None


def _occupied(db, vin, exclude_contract_id=None):
    from .business_record_delivery_models import RecordReturn
    from .business_records_models import RecordContractCorrection
    from .business_record_corrections import effective_snapshot
    claims = select(RecordInventoryClaim.contract_id).where(RecordInventoryClaim.store_id == single_store(db), RecordInventoryClaim.vin == vin)
    contracts = select(SalesContract.id).where(SalesContract.store_id == single_store(db), func.upper(SalesContract.vin) == vin)
    revisions = select(RecordContractCorrection.contract_id).where(
        RecordContractCorrection.store_id == single_store(db), RecordContractCorrection.status == 'approved',
        func.upper(RecordContractCorrection.approved_snapshot['vin'].as_string()) == vin)
    if exclude_contract_id is not None:
        claims = claims.where(RecordInventoryClaim.contract_id != exclude_contract_id)
        contracts = contracts.where(SalesContract.id != exclude_contract_id)
        revisions = revisions.where(RecordContractCorrection.contract_id != exclude_contract_id)
    candidate_ids = set(db.scalars(claims).all()) | set(db.scalars(contracts).all()) | set(db.scalars(revisions).all())
    for key in candidate_ids:
        contract = db.get(SalesContract, key)
        if contract is None:
            continue
        # A completed physical return releases the car, while a correction
        # only moves its claim when the new transaction version is approved.
        returned = db.scalar(select(RecordReturn.id).where(RecordReturn.contract_id == key,
            RecordReturn.status == 'approved').limit(1))
        if returned is not None:
            continue
        snapshot = effective_snapshot(db, contract) or {}
        if str(snapshot.get('vin') or contract.vin).strip().upper() == vin:
            return True
    return False


def _row_public(db, row, channel='retail', contract_id=None):
    price = _price_for_row(db, row, channel)
    occupied = _occupied(db, row.vin, contract_id)
    issues = list(row.issues)
    if not price:
        issues.append('当前渠道限价目录未找到已核定车型，请联系内勤核对关联')
    if occupied:
        issues.append('该车已有合同或销售历史，请核对原业务')
    return {'id': row.id, 'batch_id': row.batch_id, 'vin': row.vin, 'model': row.model,
            'configuration': row.configuration, 'exterior_color': row.exterior_color,
            'interior_color': row.interior_color, 'extra_configuration': row.extra_configuration,
            'guide_price_cents': row.guide_price_cents, 'location': row.location,
            'is_cash_vehicle': True if row.funding_kind == 'cash' else False if row.funding_kind == 'third_party' else None,
            'vehicle_price_id': price['id'] if price else None, 'occupied': occupied,
            'selectable': not occupied and bool(price and row.exterior_color and row.interior_color and row.funding_kind != 'unknown'),
            'issues': list(dict.fromkeys(issues))}


@router.get('/candidates')
def inventory_candidates(q: str = Query('', max_length=100), sales_channel: str = 'retail',
                         contract_id: int | None = Query(None, gt=0), page: int = Query(1, ge=1),
                         db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    _access(user)
    if sales_channel not in {'retail', 'wholesale'}:
        raise HTTPException(422, '销售渠道不正确')
    if contract_id is not None:
        get_contract(db, user, contract_id)
    current = current_inventory(db)
    if current is None:
        return {'items': [], 'total': 0, 'enabled': False, 'page': page, 'page_size': 50}
    query = select(RecordInventoryRow).where(RecordInventoryRow.store_id == single_store(db), RecordInventoryRow.batch_id == current.batch_id)
    search = q.strip().upper()
    if search:
        if len(search) not in {6, 17} or not re.fullmatch(r'[A-HJ-NPR-Z0-9]+', search):
            raise HTTPException(422, '请输入完整17位VIN或后6位查询')
        query = query.where(RecordInventoryRow.vin == search if len(search) == 17 else RecordInventoryRow.vin.endswith(search))
    elif user.role not in MANAGEMENT_READERS:
        return {'items': [], 'total': 0, 'enabled': True, 'page': page, 'page_size': 50, 'notice': '请输入VIN或后6位查找车辆'}
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(RecordInventoryRow.id).offset((page - 1) * 50).limit(50)).all()
    return {'items': [_row_public(db, row, sales_channel, contract_id) for row in rows], 'total': total,
            'enabled': True, 'page': page, 'page_size': 50, 'version': current.version}


@router.get('/history')
def inventory_history(db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    if user.role not in MANAGEMENT_READERS:
        raise HTTPException(403, '库存版本由本店内勤和管理岗位核对')
    rows = db.scalars(select(RecordInventoryBatch).where(RecordInventoryBatch.store_id == single_store(db))
                      .order_by(RecordInventoryBatch.id.desc()).limit(100)).all()
    return {'items': [_batch_summary(row) for row in rows]}


def prepare_contract_inventory(db, user, body, existing=None, *, allow_vehicle_change=False):
    """Validate again inside the contract transaction, never trust UI prefill."""
    from .business_records import _lock_customer_scope
    _access(user); _lock_customer_scope(db)
    row_id = getattr(body, 'inventory_row_id', None)
    contract_id = existing.id if existing is not None else None
    vin = str(body.vin).strip().upper()
    existing_vin = existing.vin.upper() if existing is not None else None
    if existing is not None and existing.status == 'approved':
        from .business_record_corrections import effective_snapshot
        existing_vin = str((effective_snapshot(db, existing) or {}).get('vin') or existing.vin).strip().upper()
    if existing is not None and not allow_vehicle_change and vin != existing_vin:
        # Existing editable contracts may change VIN through the normal form;
        # approved revisions pass allow_vehicle_change explicitly.
        if existing.status not in {'submitted', 'rejected', 'manager_approved'}:
            raise HTTPException(409, '已审批合同变更车辆请发起更正申请')
    claim = db.scalar(select(RecordInventoryClaim).where(RecordInventoryClaim.contract_id == contract_id,
        RecordInventoryClaim.vin == vin)) if contract_id else None
    current = current_inventory(db)
    if row_id is None and claim is not None:
        if _occupied(db, vin, contract_id):
            raise HTTPException(409, '该车另有合同占用，请核对原业务')
        return {'snapshot': dict(claim.snapshot), 'actor_id': user.id, 'inventory_row_id': claim.inventory_row_id}
    if row_id is None:
        # Existing unfrozen contracts can retain their original vehicle while
        # a store onboards inventory. New contracts must select the publication.
        if current is not None and (existing is None or vin != existing_vin):
            raise HTTPException(422, '请从当前已发布库存按VIN选择车辆')
        if VIN.fullmatch(vin) and _occupied(db, vin, contract_id):
            raise HTTPException(409, '该VIN已有合同或销售历史，不能重复提交')
        return None
    row = db.scalar(select(RecordInventoryRow).where(RecordInventoryRow.id == row_id,
        RecordInventoryRow.store_id == single_store(db)))
    if row is None or row.vin != vin:
        raise HTTPException(422, '选择的库存车辆与VIN不一致，请重新查询')
    if claim is not None and claim.inventory_row_id == row_id:
        return {'snapshot': dict(claim.snapshot), 'actor_id': user.id, 'inventory_row_id': row_id}
    if current is None or row.batch_id != current.batch_id:
        raise HTTPException(409, '库存版本已更新，请重新查询车辆后提交')
    channel = body.submission_data.sales_channel
    public = _row_public(db, row, channel, contract_id)
    if public['occupied']:
        raise HTTPException(409, '该车已有合同或销售历史，不能重复提交')
    if not public['selectable']:
        raise HTTPException(422, '库存车型、颜色或资金性质尚未核对齐全，请由内勤重新核对发布')
    if body.vehicle_price_id != public['vehicle_price_id']:
        raise HTTPException(422, '合同车型与库存已核定的限价车型不同，请重新选择')
    batch = db.get(RecordInventoryBatch, row.batch_id)
    snapshot = {key: public[key] for key in ('vin', 'model', 'configuration', 'exterior_color',
        'interior_color', 'extra_configuration', 'guide_price_cents', 'is_cash_vehicle', 'vehicle_price_id')}
    snapshot.update(inventory_row_id=row.id, batch_id=batch.id, as_of_date=batch.as_of_date.isoformat(),
                    brand=batch.brand, source_row=row.source_row)
    return {'snapshot': snapshot, 'actor_id': user.id, 'inventory_row_id': row.id}


def save_contract_inventory(db, contract, prepared):
    if not prepared:
        return
    snapshot = dict(prepared['snapshot']); vin = snapshot['vin']
    if _occupied(db, vin, contract.id):
        raise HTTPException(409, '该车已被其他合同占用，请重新查询')
    claim = db.scalar(select(RecordInventoryClaim).where(RecordInventoryClaim.contract_id == contract.id,
        RecordInventoryClaim.vin == vin, RecordInventoryClaim.store_id == contract.store_id))
    if claim is None:
        db.add(RecordInventoryClaim(store_id=contract.store_id, contract_id=contract.id, vin=vin,
            inventory_row_id=prepared['inventory_row_id'], snapshot=snapshot, created_by=prepared['actor_id']))
        db.flush()
