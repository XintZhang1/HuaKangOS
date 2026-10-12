"""Store-scoped price publication, contract evidence and submission snapshots."""
import hashlib
import io
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from .db import get_db, get_write_db, utcnow
from .config import settings
from .security import get_user
from .models import User
from .tenancy import single_store, role_for_store
from .services import plain, audit
from .business_records_schemas import Action, Command
from .business_record_pricing_models import (RecordPricingSettings, RecordPricingFile,
    RecordPriceBatch, RecordVehicleVariant, RecordVehiclePrice, RecordGiftPrice, RecordContractTerms)
from .business_record_pricing_models import RecordBrandVariant
from .business_record_brand_catalog import (store_brand, profile_view, catalog_state, lock_brand_catalog,
    allowed_batch, catalog_rows, published_brand_file)
from .business_record_pricing_schemas import VehiclePriceImport, GiftPriceImport, StoreProfileInput, VehicleVariantInput, GiftPolicyCheck
from .business_record_pricing_recognition import validate_price_file, recognize_price_file
from .file_security import policy_mode, scan_clamav
from .private_files import publish

router = APIRouter(prefix='/api/business-records', tags=['门店价格与特殊审批'])
GIFT_READERS = {'admin', 'manager', 'general_manager', 'group_deputy_manager', 'finance', 'clerk', 'chairman', 'store_admin'}
GIFT_COST_READERS = {'admin', 'clerk', 'general_manager', 'chairman', 'store_admin'}
PRICE_WRITERS = {'admin', 'manager', 'general_manager'}
PROFILE_WRITERS = {'admin', 'clerk'}
BASIC_COLORS = {'红', '橙', '黄', '绿', '青', '蓝', '紫', '白', '灰', '黑'}


def _access(user, kind=None, write=False):
    from .business_records import require_read
    require_read(user)
    if getattr(user, '_aggregate_scope', False):
        raise HTTPException(403, '请切换到具体授权门店查看或维护本店目录')
    if write and user.role not in PRICE_WRITERS:
        raise HTTPException(403, '车型限价和赠品表由本店销售经理、总经理或系统管理员上传')


def gift_policy_assessment(policy, cost_total):
    """Compare frozen actual costs; unknown costs cannot pass a budget check."""
    if policy is None:
        return {'status': 'no_policy', 'requires_special': False, 'has_cost_limit': False,
            'text': '本车型未设置赠品成本额度'}
    limit = policy.get('cost_limit_cents')
    if 'cost_limit_cents' in policy and limit is None:
        # An explicitly unlimited policy may still name optional defaults.
        # It has the same cost-rule meaning as the earlier null policy.
        return {'status': 'no_policy', 'requires_special': False, 'has_cost_limit': False,
            'text': policy.get('text') or '本车型未设置赠品成本额度'}
    if type(limit) is not int or limit < 0:
        raise HTTPException(409, '冻结赠品政策缺少已核定成本额度，请联系管理员核对')
    status = 'unknown_cost' if cost_total is None else 'exceeded' if cost_total > limit else 'within_limit'
    return {'status': status, 'requires_special': status in {'unknown_cost', 'exceeded'},
        'has_cost_limit': True, 'text': policy.get('text') or '按已确认赠品成本额度核对',
        'cost_limit_cents': limit, 'gift_cost_total_cents': cost_total,
        'excess_cost_cents': None if cost_total is None else max(0, cost_total - limit)}


def _policy_view(policy, user, gift_batch_id=None):
    if policy is None:
        return None
    configured = policy.get('standard_gifts') or []
    current = bool(gift_batch_id) and policy.get('standard_gift_batch_id') == gift_batch_id
    standards = [{key: item[key] for key in ('price_id', 'quantity', 'name', 'unit', 'applicable_models')
                  if key in item} for item in configured] if current else []
    public = {'has_cost_limit': policy.get('cost_limit_cents') is not None,
        # This separate, employee-confirmed public field is never populated from
        # internal policy text or the uploaded vehicle note.
        'standard_gift_note': policy.get('standard_gift_note') or '',
        'standard_gifts': standards,
        'standard_gifts_status': 'current' if configured and current else 'outdated' if configured else 'none'}
    if user.role not in GIFT_READERS:
        # Original policy prose can itself contain amounts. A fixed public
        # explanation is safer than trying to redact every way to write money.
        return {**public, 'text': '本车型赠品按已确认政策核对，超出政策须提交特殊申请。'
            if public['has_cost_limit'] else '本车型未设置赠品成本额度，标准赠品可调整或取消。'}
    return {**public, **{key: policy[key] for key in
        ('text', 'cost_limit_cents', 'confirmed_by', 'confirmed_at') if key in policy}}


def _freeze_standard_gifts(db, policy, gift_batch_id):
    """Freeze only a manager's explicit choices from this brand's live catalog."""
    selections = policy.get('standard_gifts') or []
    available = {item['id']: item for item in catalog_rows(db, 'gift', gift_batch_id)} if selections else {}
    frozen = []
    for selection in selections:
        gift = available.get(selection['price_id'])
        if gift is None:
            raise HTTPException(422, '标准赠品不在本品牌当前有效目录中，请刷新并重新选择')
        frozen.append({**selection, **{key: gift[key] for key in ('name', 'unit', 'applicable_models')}})
    return {**policy, 'standard_gifts': frozen, 'standard_gift_batch_id': gift_batch_id if frozen else None}


def _policy_result_view(result, user):
    result = dict(result)
    if user.role not in GIFT_COST_READERS:
        result.pop('gift_cost_total_cents', None); result.pop('excess_cost_cents', None)
    if user.role not in GIFT_READERS:
        result.pop('cost_limit_cents', None)
        result['text'] = ('本车型赠品按已确认政策核对，超出政策须提交特殊申请。'
            if result['has_cost_limit'] else '本车型未设置赠品成本额度')
    return result


def pricing_settings(db):
    return db.scalar(select(RecordPricingSettings).where(RecordPricingSettings.store_id == single_store(db)))


def _write_settings(db, expected):
    from .business_records import _lock_customer_scope, _check_version
    _lock_customer_scope(db)
    row = pricing_settings(db)
    if row is None:
        if expected != 0:
            raise HTTPException(409, '门店资料已变化，请刷新后核对')
        row = RecordPricingSettings(store_id=single_store(db), profile={})
        db.add(row); db.flush()
    else:
        _check_version(row, expected)
    return row


def _file_summary(item):
    from .business_record_invoices import _safe
    return {'id': item.id, 'version': item.version, 'kind': item.kind, 'filename': item.filename,
        'content_type': item.content_type, 'size': item.size, 'sha256': item.sha256,
        'scan_state': item.scan_state, 'available': _safe(item), 'created_at': item.created_at.isoformat()}


def _file(db, key, kind=None):
    item = db.scalar(select(RecordPricingFile).where(RecordPricingFile.id == key,
                                                   RecordPricingFile.store_id == single_store(db)))
    if item is None or (kind and item.kind != kind):
        raise HTTPException(404, '原件不存在或不属于当前门店及用途')
    return item


def _save_file(db, user, kind, filename, content, media, contract_id=None):
    brand = store_brand(db, required=True) if kind in {'vehicle', 'gift'} else ''
    digest = hashlib.sha256(content).hexdigest()
    mode = policy_mode()
    state, code = ('structure_only', 'structure_only') if mode == 'structure_only' else ('quarantined', 'awaiting_scan')
    if mode == 'clamav':
        result = scan_clamav(content, settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)
        state, code = result.state, result.code
    try:
        object_key = publish(None, single_store(db), content, len(content), digest) if settings.file_storage_mode == 'private_local' else ''
    except (ValueError, OSError):
        raise HTTPException(503, '原件尚未保存，请联系管理员检查存储') from None
    item = RecordPricingFile(store_id=single_store(db), kind=kind, brand=brand, contract_id=contract_id,
        filename=filename, content_type=media, size=len(content), sha256=digest,
        object_key=object_key, content=b'' if object_key else content,
        scan_state=state, scan_code=code, created_by=user.id)
    db.add(item); db.flush()
    return item


@router.get('/pricing/catalog')
def price_catalog(contract_id: int | None = Query(None, gt=0), db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    current = pricing_settings(db)
    shared = catalog_state(db)
    vehicle_batch, gift_batch = shared['vehicle_batch_id'], shared['gift_batch_id']
    contract = None
    frozen = None
    if contract_id is not None:
        from .business_records import get_contract
        contract = get_contract(db, user, contract_id)
        frozen = get_terms(db, contract)
        if frozen is None:
            raise HTTPException(409, '该历史合同没有本版提交目录快照')
        vehicle_batch, gift_batch = frozen.price_snapshot['batch_id'], frozen.gift_batch_id
    vehicles = [dict(frozen.price_snapshot)] if frozen else catalog_rows(db, 'vehicle', vehicle_batch)
    for item in vehicles:
        item['gift_policy'] = _policy_view(item.get('gift_policy'), user, gift_batch)
    if user.role not in GIFT_READERS:
        # Uploaded annotations can contain internal package/gift amounts too.
        for item in vehicles:
            item.pop('note', None)
    gifts = []
    if gift_batch:
        for item in catalog_rows(db, 'gift', gift_batch, contract=contract):
            value = {key: item[key] for key in ('id', 'name', 'brand', 'unit', 'applicable_models')}
            if user.role in GIFT_READERS:
                value.update(unit_price_cents=item['unit_price_cents'])
            if user.role in GIFT_COST_READERS:
                value.update(unit_cost_cents=item['unit_cost_cents'], note=item['note'], source_ref=item['source_ref'])
            gifts.append(value)
    profile = profile_view(db, current)
    if contract is not None:
        profile['brand'] = contract.brand
    return {'version': current.version if current else 0, 'profile': profile,
        'brand': shared['brand'], 'brand_version': shared['brand_version'], 'shared_by_brand': True,
        'vehicle_batch_id': vehicle_batch, 'gift_batch_id': gift_batch, 'vehicles': vehicles, 'gifts': gifts,
        'frozen_for_contract': contract_id,
        'can_import_vehicle': user.role in PRICE_WRITERS,
        'can_import_gifts': user.role in PRICE_WRITERS,
        'can_manage_profile': user.role in PROFILE_WRITERS,
        'can_view_gift_amounts': user.role in GIFT_READERS,
        'can_view_gift_costs': user.role in GIFT_COST_READERS}


@router.get('/store-profile')
def store_profile(db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    row = pricing_settings(db)
    return {'version': row.version if row else 0, **profile_view(db, row)}


@router.put('/store-profile')
def save_store_profile(body: StoreProfileInput, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run, _body
    _manual(request); _access(user)
    if user.role not in PROFILE_WRITERS:
        raise HTTPException(403, '本店卖方及联系资料由内勤或维护管理员维护；品牌由系统管理员在门店设置中维护')
    names = [item.name for item in body.sellers]
    if len(names) != len(set(names)):
        raise HTTPException(422, '卖方列表包含重复名称')
    for ident, phone in body.sales_contacts.items():
        if not ident.isdecimal() or len(phone) > 40:
            raise HTTPException(422, '销售联系电话格式不正确')
        person = db.get(User, int(ident))
        if person is None or role_for_store(db, person, single_store(db)) != 'sales':
            raise HTTPException(422, '联系资料只能关联本店销售顾问')
    def perform():
        row = _write_settings(db, body.version)
        from .business_record_gift_import import canonical_brand
        brand = store_brand(db)
        if body.brand is not None and canonical_brand(body.brand) != brand:
            raise HTTPException(403, '门店品牌须由系统管理员在门店设置中修改')
        before = dict(row.profile)
        row.profile = body.model_dump(exclude={'request_id', 'version', 'brand'})
        # Preserve an existing legacy directory's provenance key only. It can
        # never set the store brand or replace the authoritative output brand.
        if before.get('brand'):
            row.profile = {**row.profile, 'brand': before['brand']}
        row.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_store_profile', 'record_pricing_settings', row.id, before, row.profile)
        return {'version': row.version, **profile_view(db, row)}
    return _run(db, user, body.request_id, 'pricing:profile', _body(body), perform)


@router.get('/vehicle-variants')
def variants(db=Depends(get_db), user=Depends(get_user)):
    _access(user)
    brand = store_brand(db, required=True)
    return {'brand': brand, 'brand_version': catalog_state(db)['brand_version'],
        'items': [{key: getattr(row, key) for key in ('id', 'brand', 'family', 'series', 'model', 'active')}
            for row in db.scalars(select(RecordBrandVariant).where(
            RecordBrandVariant.brand == brand).order_by(RecordBrandVariant.id))]}


@router.post('/vehicle-variants', status_code=201)
def add_variant(body: VehicleVariantInput, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run, _body, _lock_customer_scope
    _manual(request); _access(user)
    if user.role not in PROFILE_WRITERS:
        raise HTTPException(403, '车型目录由本店内勤或维护管理员维护')
    def perform():
        shared = lock_brand_catalog(db, body.brand_version, body.brand)
        row = db.scalar(select(RecordBrandVariant).where(RecordBrandVariant.brand == shared.brand,
            RecordBrandVariant.family == body.family, RecordBrandVariant.series == body.series, RecordBrandVariant.model == body.model))
        if row:
            raise HTTPException(409, '该车型配置已在目录中')
        row = RecordBrandVariant(brand=shared.brand, created_by=user.id,
            **body.model_dump(exclude={'version', 'brand_version', 'brand', 'request_id'}))
        db.add(row); shared.updated_at = utcnow(); db.flush()
        audit(db, user.id, 'record_vehicle_variant', 'record_vehicle_variant', row.id, after=plain(row))
        return {**plain(row), 'brand_version': shared.version}
    return _run(db, user, body.request_id, 'pricing:variant', _body(body), perform)


@router.post('/pricing/uploads', status_code=201)
def upload_price_file(request: Request, kind: str = Form(...), file: UploadFile = File(...),
                      request_id: str = Form(...), db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import _manual, _run
    _manual(request)
    if kind not in {'vehicle', 'gift'}:
        raise HTTPException(422, '价格表用途不正确')
    _access(user, kind, True); Command(request_id=request_id)
    content = file.file.read(10 * 1024 * 1024 + 1)
    media = validate_price_file(file.filename or '', content)
    if kind == 'vehicle' and media != 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        raise HTTPException(422, '车价限价表请上传Excel（.xlsx）')
    def perform():
        item = _save_file(db, user, kind, file.filename, content, media)
        result = _file_summary(item)
        audit(db, user.id, 'record_price_upload', 'record_pricing_file', item.id, after=result)
        return result
    return _run(db, user, request_id, 'pricing:upload', {'kind': kind, 'filename': file.filename,
        'sha256': hashlib.sha256(content).hexdigest()}, perform)


@router.post('/pricing/uploads/{key}/recognize')
def recognize_prices(key: int, body: Action, request: Request, db=Depends(get_db), user=Depends(get_user)):
    from .business_records import _manual, _check_version
    from .business_record_invoices import _content
    _manual(request)
    item = _file(db, key)
    if item.kind not in {'vehicle', 'gift'}:
        raise HTTPException(422, '该原件不是价格表')
    _access(user, item.kind, True); _check_version(item, body.version)
    if item.brand != store_brand(db, required=True):
        raise HTTPException(409, '上传原表的品牌与本店当前品牌不同，请重新上传核对')
    if item.created_by != user.id:
        raise HTTPException(403, '请由本次原表上传者核对识别结果并确认导入')
    content, media, kind = _content(item), item.content_type, item.kind
    db.rollback()
    if kind == 'gift':
        from .business_record_gift_import import preview_gift_file
        result = preview_gift_file(content, media, store_brand(db, required=True))
        if user.role not in GIFT_COST_READERS and any(row.get('unit_cost_cents') is not None for row in result['rows']):
            raise HTTPException(403, '此表包含赠品成本，请由总经理或维护管理员核对导入')
    else:
        result = recognize_price_file(content, media, kind)
    current_user = get_user(request, db)
    _access(current_user, kind, True)
    current_file = _file(db, key, kind)
    if current_file.brand != store_brand(db, required=True):
        raise HTTPException(409, '识别期间门店品牌已变化，请重新上传当前品牌原表')
    if kind == 'gift' and current_user.role not in GIFT_COST_READERS:
        for row in result['rows']:
            row.pop('unit_cost_cents', None); row.pop('note', None); row.pop('source_ref', None)
    result.update(file_id=key, version=body.version)
    return result


def _import(body, request, db, user, kind):
    from .business_records import _manual, _run, _body
    from .business_record_invoices import _content
    _manual(request); _access(user, kind, True)
    item = _file(db, body.file_id, kind)
    if item.created_by != user.id:
        raise HTTPException(403, '请由本次原表上传者逐行核对后确认整批生效')
    _content(item)
    keys = [(x.family, x.series, x.model) if kind == 'vehicle' else x.name for x in body.rows]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, '本批包含重复车系配置或赠品名称，请核对后整批导入')
    def perform():
        current = _write_settings(db, body.version)
        shared = lock_brand_catalog(db, body.brand_version, body.brand)
        if item.brand != shared.brand:
            raise HTTPException(409, '上传时的品牌已变化，请为当前品牌重新上传原表')
        if kind == 'gift':
            from .business_record_gift_import import canonical_brand
            expected = shared.brand
            if not expected or canonical_brand(body.brand) != expected or any(x.brand and canonical_brand(x.brand) != expected for x in body.rows):
                raise HTTPException(422, '赠品品牌须与当前门店品牌一致，请拆分品牌并核对本店资料')
            if user.role not in GIFT_COST_READERS and any(x.unit_cost_cents is not None for x in body.rows):
                raise HTTPException(403, '此批包含赠品成本，请由总经理或维护管理员核对导入')
        batch = RecordPriceBatch(store_id=single_store(db), kind=kind, brand=shared.brand, file_id=item.id,
            created_by=user.id, row_count=len(body.rows))
        db.add(batch); db.flush()
        for source in body.rows:
            if kind == 'vehicle':
                shared_variant = db.scalar(select(RecordBrandVariant).where(RecordBrandVariant.brand == shared.brand,
                    RecordBrandVariant.family == source.family, RecordBrandVariant.series == source.series,
                    RecordBrandVariant.model == source.model))
                if shared_variant is None:
                    db.add(RecordBrandVariant(brand=shared.brand, family=source.family, series=source.series,
                        model=source.model, created_by=user.id))
                variant = db.scalar(select(RecordVehicleVariant).where(
                    RecordVehicleVariant.store_id == single_store(db), RecordVehicleVariant.family == source.family,
                    RecordVehicleVariant.series == source.series, RecordVehicleVariant.model == source.model))
                if variant is None:
                    variant = RecordVehicleVariant(store_id=single_store(db), family=source.family, series=source.series, model=source.model)
                    db.add(variant); db.flush()
                values = source.model_dump()
                if values['gift_policy'] is not None:
                    values['gift_policy'] = {**_freeze_standard_gifts(db, values['gift_policy'], catalog_state(db)['gift_batch_id']), 'confirmed_by': user.id,
                        'confirmed_at': utcnow().isoformat() + 'Z'}
                row = RecordVehiclePrice(store_id=single_store(db), batch_id=batch.id, variant_id=variant.id, **values)
            else:
                values = source.model_dump()
                values['brand'] = expected
                row = RecordGiftPrice(store_id=single_store(db), batch_id=batch.id, **values)
            db.add(row)
        setattr(current, 'vehicle_batch_id' if kind == 'vehicle' else 'gift_batch_id', batch.id)
        setattr(shared, 'vehicle_batch_id' if kind == 'vehicle' else 'gift_batch_id', batch.id)
        current.updated_at = shared.updated_at = utcnow(); db.flush()
        result = {'batch_id': batch.id, 'kind': kind, 'count': len(body.rows), 'version': current.version,
            'brand': shared.brand, 'brand_version': shared.version, 'shared_by_brand': True}
        if kind == 'vehicle':
            result['policy_confirmed'] = True
        audit(db, user.id, 'record_price_publish', 'record_price_batch', batch.id, after=result)
        return result
    return _run(db, user, body.request_id, 'pricing:publish:' + kind, _body(body), perform)


@router.post('/pricing/vehicle/import', status_code=201)
def import_vehicle_prices(body: VehiclePriceImport, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _import(body, request, db, user, 'vehicle')


@router.post('/pricing/gifts/import', status_code=201)
def import_gift_prices(body: GiftPriceImport, request: Request, db=Depends(get_write_db), user=Depends(get_user)):
    return _import(body, request, db, user, 'gift')


def get_terms(db, contract):
    return db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == contract.id,
                                                     RecordContractTerms.store_id == contract.store_id))


def frozen_gift_cost(terms):
    """Legacy accounting is preserved explicitly, never backfilled as actual cost."""
    return terms.gift_total_cents if terms.gift_pricing_basis == 'legacy-single-price' else terms.gift_cost_total_cents


def _selected_gifts(db, gift_batch_id, selections, existing=None):
    from types import SimpleNamespace
    available = {item['id']: SimpleNamespace(**item) for item in
        catalog_rows(db, 'gift', gift_batch_id, contract=existing)}
    gifts, total, cost_total, seen = [], 0, 0, set()
    for selection in selections:
        if selection.price_id in seen:
            raise HTTPException(422, '同一赠品请合并数量，不要重复勾选')
        seen.add(selection.price_id)
        gift = available.get(selection.price_id)
        if gift is None:
            raise HTTPException(422, '赠品不在本合同冻结的目录中，请重新核对；新目录项目须新建合同')
        amount = None if gift.unit_price_cents is None else gift.unit_price_cents * selection.quantity
        cost = None if gift.unit_cost_cents is None else gift.unit_cost_cents * selection.quantity
        total = None if amount is None or total is None else total + amount
        cost_total = None if cost is None or cost_total is None else cost_total + cost
        if any(value is not None and value > 999999999999 for value in (amount, cost, total, cost_total)):
            raise HTTPException(422, '赠品金额超出可记录范围')
        gifts.append({'price_id': gift.id, 'name': gift.name, 'quantity': selection.quantity,
            'unit_price_cents': gift.unit_price_cents, 'amount_cents': amount,
            'unit_cost_cents': gift.unit_cost_cents, 'cost_cents': cost,
            'brand': gift.brand, 'unit': gift.unit, 'applicable_models': gift.applicable_models, 'source_ref': gift.source_ref})
    return gifts, total, cost_total


@router.post('/pricing/gift-policy-check')
def check_gift_policy(body: GiftPolicyCheck, db=Depends(get_db), user=Depends(get_user)):
    """Read-only selection preview; no command, audit, lock or publication."""
    _access(user)
    contract = None
    if body.contract_id is not None:
        from .business_records import get_contract
        contract = get_contract(db, user, body.contract_id)
        terms = get_terms(db, contract)
        if terms is None or terms.price_snapshot['id'] != body.vehicle_price_id:
            raise HTTPException(409, '请选择本合同冻结的车型价格')
        price, gift_batch = terms.price_snapshot, terms.gift_batch_id
    else:
        shared = catalog_state(db)
        price = next((item for item in catalog_rows(db, 'vehicle', shared['vehicle_batch_id'])
            if item['id'] == body.vehicle_price_id), None)
        if price is None:
            raise HTTPException(422, '请选择本店当前品牌已发布的车型价格')
        gift_batch = shared['gift_batch_id']
    _, _, cost_total = _selected_gifts(db, gift_batch, body.gift_items, contract)
    return _policy_result_view(gift_policy_assessment(price.get('gift_policy'), cost_total), user)


def prepare_submission(db, user, body, existing=None):
    """Use current published prices once. Subsequent edits retain that exact batch."""
    current = pricing_settings(db)
    if current is None:
        raise HTTPException(422, '请先由内勤维护本店卖方资料')
    prior = get_terms(db, existing) if existing is not None else None
    if existing is not None and prior is None:
        raise HTTPException(409, '合同提交快照缺失，不能按新价格补造原依据，请联系管理员核对')
    if prior:
        price = prior.price_snapshot
        if body.vehicle_price_id != price['id']:
            raise HTTPException(409, '已提交合同冻结车型限价；更换车型请另建合同')
        gift_batch_id = prior.gift_batch_id
        brand = existing.brand
    else:
        brand = store_brand(db, required=True)
        shared = catalog_state(db)
        price_row = next((item for item in catalog_rows(db, 'vehicle', shared['vehicle_batch_id'])
            if item['id'] == body.vehicle_price_id), None)
        if price_row is None:
            raise HTTPException(422, '请选择当前门店已发布限价中的车型；价格表更新后请重新核对')
        price = dict(price_row)
        batch = allowed_batch(db, 'vehicle', price['batch_id'])
        if batch is None:
            raise HTTPException(409, '价格批次来源缺失，请联系管理员核对')
        price.update(source_file_id=batch.file_id, published_at=batch.created_at.isoformat(), brand=brand)
        gift_batch_id = shared['gift_batch_id']
    gifts, total, cost_total = _selected_gifts(db, gift_batch_id, body.gift_items, existing if prior else None)
    policy_check = gift_policy_assessment(price.get('gift_policy'), cost_total)
    form = dict(body.form_data)
    sellers = [seller for seller in current.profile.get('sellers', []) if seller['name'] == form.get('seller_name')]
    if len(sellers) != 1:
        raise HTTPException(422, '请从本店卖方公司列表中选择合同卖方')
    for key in ('exterior_color', 'interior_color'):
        if form.get(key) not in BASIC_COLORS:
            raise HTTPException(422, '请从十种基础色中选择车身及内饰颜色')
    if form.get('buyer_document_name', '身份证') not in {'身份证', '护照', '驾照'}:
        raise HTTPException(422, '买方证件类型须选择身份证、护照或驾照')
    person = db.get(User, body.salesperson_id)
    form.update(seller_address=sellers[0].get('address') or current.profile.get('address', ''),
        seller_agent=person.display_name, seller_phone=current.profile.get('sales_contacts', {}).get(str(person.id), ''),
        quantity='1', payment_method=body.submission_data.payment_method)
    form.setdefault('buyer_document_name', '身份证')
    if not form.get('buyer_agent'):
        form['buyer_agent'] = body.customer_name
    return {'price': price, 'gifts': gifts, 'gift_batch_id': gift_batch_id, 'gift_total_cents': total,
        'gift_cost_total_cents': cost_total,
        'gift_policy_check': policy_check,
        'gift_pricing_basis': prior.gift_pricing_basis if prior else 'separate-cost-v1',
        'form_data': form, 'brand': brand, 'model': price['series'] + ' ' + price['model'],
        'submission_data': body.submission_data.model_dump(),
        'price_below_cents': max(0, price['control_price_cents'] - body.sale_price_cents)}


def save_submission(db, row, prepared):
    terms = get_terms(db, row)
    if terms is None:
        terms = RecordContractTerms(store_id=row.store_id, contract_id=row.id, price_snapshot=prepared['price'])
        db.add(terms)
    terms.gift_batch_id, terms.gifts_snapshot = prepared['gift_batch_id'], prepared['gifts']
    terms.gift_total_cents, terms.submission_data = prepared['gift_total_cents'], prepared['submission_data']
    terms.gift_pricing_basis = prepared['gift_pricing_basis']
    terms.gift_cost_total_cents = prepared['gift_cost_total_cents'] if terms.gift_pricing_basis != 'legacy-single-price' else None
    terms.price_below_cents, terms.gift_excess_cents = prepared['price_below_cents'], 0
    terms.special = prepared['price_below_cents'] > 0 or prepared['gift_policy_check']['requires_special']
    terms.special_note = ''
    row.gift_cost_cents = frozen_gift_cost(terms)
    row.gift_description = '；'.join(item['name'] + ' × ' + str(item['quantity']) for item in prepared['gifts'])
    db.flush()
    return terms


def contract_terms_view(db, user, row):
    terms = get_terms(db, row)
    if terms is None:
        return None
    data = plain(terms)
    data['discount_cents'] = terms.price_snapshot['guide_price_cents'] - row.sale_price_cents
    files = db.scalars(select(RecordPricingFile).where(RecordPricingFile.contract_id == row.id,
        RecordPricingFile.store_id == row.store_id).order_by(RecordPricingFile.id)).all()
    data['attachments'] = [_file_summary(item) for item in files if user.role != 'sales' or item.created_by == user.id]
    if user.role not in GIFT_COST_READERS:
        data.pop('gift_cost_total_cents', None)
        data['gifts_snapshot'] = [{key: value for key, value in item.items()
            if key not in {'unit_cost_cents', 'cost_cents', 'source_ref'}} for item in data['gifts_snapshot']]
    if user.role not in GIFT_READERS:
        data.pop('gift_total_cents', None); data.pop('gift_excess_cents', None); data.pop('special_note', None)
        data['price_snapshot'] = {key: value for key, value in terms.price_snapshot.items() if key != 'note'}
        data['gifts_snapshot'] = [{key: value for key, value in item.items() if key in {'price_id', 'name', 'quantity', 'unit', 'applicable_models', 'brand'}} for item in terms.gifts_snapshot]
    data['price_snapshot'] = {**data['price_snapshot'],
        'gift_policy': _policy_view(terms.price_snapshot.get('gift_policy'), user, terms.gift_batch_id)}
    data['gift_policy_check'] = _policy_result_view(gift_policy_assessment(
        terms.price_snapshot.get('gift_policy'), frozen_gift_cost(terms)), user)
    return data


@router.post('/contracts/{key}/attachments', status_code=201)
def upload_attachment(key: int, request: Request, file: UploadFile = File(...), request_id: str = Form(...),
                      version: int = Form(...), db=Depends(get_write_db), user=Depends(get_user)):
    from .business_records import get_contract, _manual, _run, _check_version
    from .flow_documents import validate_upload
    _manual(request); _access(user); Command(request_id=request_id)
    row = get_contract(db, user, key)
    if user.role not in {'admin', 'sales', 'manager', 'general_manager', 'group_deputy_manager'}:
        raise HTTPException(403, '当前岗位不能补充审批附件')
    content = file.file.read(10 * 1024 * 1024 + 1)
    media = validate_upload(file.filename or '', content)
    def perform():
        _check_version(row, version)
        if row.status not in {'submitted', 'rejected'}:
            raise HTTPException(409, '审批附件须在销售经理审批前补齐；已有审批结论时请先按原流程退回核对')
        item = _save_file(db, user, 'contract_attachment', file.filename, content, media, row.id)
        row.updated_at = utcnow(); db.flush()
        result = _file_summary(item); result['contract_version'] = row.version
        audit(db, user.id, 'record_approval_attachment', 'record_contract', row.id, after=result)
        return result
    return _run(db, user, request_id, 'contract:attachment', {'contract_id': key, 'version': version,
        'filename': file.filename, 'sha256': hashlib.sha256(content).hexdigest()}, perform)


@router.get('/pricing/files/{key}/download')
def download_pricing_file(key: int, contract_id: int | None = Query(None, gt=0),
                          db=Depends(get_db), user=Depends(get_user)):
    from .business_records import get_contract
    from .business_record_invoices import _content
    _access(user)
    contract = get_contract(db, user, contract_id) if contract_id is not None else None
    item = db.scalar(select(RecordPricingFile).where(RecordPricingFile.id == key,
        RecordPricingFile.store_id == single_store(db)))
    if item is None:
        item = published_brand_file(db, key, contract=contract)
    if item.kind == 'gift' and user.role not in GIFT_COST_READERS:
        raise HTTPException(403, '赠品原表可能包含成本，仅向成本核价岗位开放')
    if item.contract_id:
        get_contract(db, user, item.contract_id)
        if user.role == 'sales' and item.created_by != user.id:
            raise HTTPException(403, '审批内部附件不向销售顾问开放')
    elif user.role not in GIFT_READERS:
        raise HTTPException(403, '价格原表仅供有权限的员工核对')
    return StreamingResponse(io.BytesIO(_content(item)), media_type=item.content_type,
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(item.filename), 'Cache-Control': 'no-store'})
