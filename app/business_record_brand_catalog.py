"""Narrow brand catalog projections; never widen the request's store scope.

The only Core reads below are immutable price batches, their price rows and
published price files. Business records and unpublished files remain scoped.
"""
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .models import Store
from .tenancy import single_store
from .business_record_gift_import import canonical_brand
from .business_record_pricing_models import (RecordPricingSettings, RecordBrandPricing,
    RecordPriceBatch, RecordVehiclePrice, RecordGiftPrice, RecordPricingFile, RecordContractTerms)


def store_brand(db, *, required=False):
    store = db.scalar(select(Store).where(Store.id == single_store(db), Store.active.is_(True)))
    if store is None:
        raise HTTPException(409, '当前门店已停用或不存在')
    brand = canonical_brand(store.brand)
    if required and not brand:
        raise HTTPException(422, '请先由系统管理员在门店设置中指定本店唯一品牌')
    return brand


def profile_view(db, settings):
    return {**(settings.profile if settings else {}), 'brand': store_brand(db)}


def catalog_state(db, sales_channel='retail'):
    brand = store_brand(db)
    shared = db.get(RecordBrandPricing, brand) if brand else None
    local = db.scalar(select(RecordPricingSettings).where(RecordPricingSettings.store_id == single_store(db)))
    state = {'brand': brand, 'brand_version': shared.version if shared else 0}
    for kind in ('vehicle', 'gift'):
        key = kind + '_batch_id'
        pointer = 'wholesale_vehicle_batch_id' if kind == 'vehicle' and sales_channel == 'wholesale' else key
        chosen = getattr(shared, pointer) if shared else None
        # An explicit matching old profile may retain its own old publication.
        # Never copy it to the brand pointer or expose it to another store.
        if chosen is None and (sales_channel == 'retail' or kind == 'gift') and brand and local and getattr(local, key):
            old = db.scalar(select(RecordPriceBatch).where(RecordPriceBatch.id == getattr(local, key),
                RecordPriceBatch.store_id == single_store(db), RecordPriceBatch.kind == kind))
            if old and (old.brand == brand or not old.brand and canonical_brand(local.profile.get('brand')) == brand):
                chosen = old.id
        state[key] = chosen
    return state


def lock_brand_catalog(db, expected_version, expected_brand=None):
    from .business_records import _lock_customer_scope
    _lock_customer_scope(db)
    brand = store_brand(db, required=True)
    if expected_brand is not None and canonical_brand(expected_brand) != brand:
        raise HTTPException(409, '门店品牌已变化，请刷新后重新核对品牌目录')
    row = db.scalar(select(RecordBrandPricing).where(RecordBrandPricing.brand == brand).with_for_update())
    if row is None:
        if expected_version != 0:
            raise HTTPException(409, '品牌目录已变化，请刷新后核对')
        row = RecordBrandPricing(brand=brand)
        db.add(row); db.flush()
    elif row.version != expected_version:
        raise HTTPException(409, '同品牌另一门店已更新目录，请刷新后核对，未覆盖其发布')
    return row


def allowed_batch(db, kind, batch_id, *, contract=None, sales_channel='retail'):
    if not batch_id:
        return None
    brand = store_brand(db)
    if contract is None:
        if catalog_state(db, sales_channel)[kind + '_batch_id'] != batch_id:
            raise HTTPException(404, '该价格批次不属于本店当前品牌目录')
    else:
        if contract.store_id != single_store(db):
            raise HTTPException(404, '合同不存在或不可访问')
        terms = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == contract.id,
            RecordContractTerms.store_id == single_store(db)))
        frozen_id = (terms.price_snapshot.get('batch_id') if kind == 'vehicle' else terms.gift_batch_id) if terms else None
        if frozen_id != batch_id:
            raise HTTPException(404, '该价格批次不属于本合同冻结目录')
        sales_channel = terms.submission_data.get('sales_channel', 'retail')
        brand = canonical_brand(contract.brand)
    table = RecordPriceBatch.__table__
    data = db.execute(select(table.c.id, table.c.store_id, table.c.kind, table.c.brand, table.c.sales_channel,
        table.c.file_id, table.c.created_at, table.c.created_by, table.c.row_count).where(
            table.c.id == batch_id, table.c.kind == kind)).mappings().one_or_none()
    if data is None or not (data['brand'] == brand and bool(brand) or
            not data['brand'] and data['store_id'] == single_store(db)):
        raise HTTPException(404, '价格批次品牌或来源不匹配')
    if kind == 'vehicle' and data['sales_channel'] != sales_channel:
        raise HTTPException(404, '零售与二级限价来源不匹配')
    return SimpleNamespace(**dict(data))


def catalog_rows(db, kind, batch_id, *, contract=None, sales_channel='retail'):
    batch = allowed_batch(db, kind, batch_id, contract=contract, sales_channel=sales_channel)
    if batch is None:
        return []
    if kind == 'vehicle':
        table = RecordVehiclePrice.__table__
        names = ('id', 'store_id', 'batch_id', 'variant_id', 'family', 'series', 'model',
                 'guide_price_cents', 'control_price_cents', 'note', 'gift_policy')
    elif kind == 'gift':
        table = RecordGiftPrice.__table__
        names = ('id', 'store_id', 'batch_id', 'name', 'unit_price_cents', 'unit_cost_cents',
                 'brand', 'unit', 'applicable_models', 'source_ref', 'note')
    else:
        raise ValueError('Unsupported catalog projection')
    return [dict(row) for row in db.execute(select(*(table.c[name] for name in names)).where(
        table.c.batch_id == batch.id, table.c.store_id == batch.store_id).order_by(table.c.id)).mappings()]


def published_brand_file(db, key, *, contract=None):
    brand = store_brand(db)
    batches, files = RecordPriceBatch.__table__, RecordPricingFile.__table__
    query = select(batches.c.id, batches.c.kind).where(batches.c.file_id == key,
        batches.c.kind.in_(('vehicle', 'gift')))
    if contract is None:
        if not brand:
            raise HTTPException(404, '价格原表不存在或不可访问')
        query = query.where(batches.c.brand == brand)
    else:
        if contract.store_id != single_store(db):
            raise HTTPException(404, '合同不存在或不可访问')
        terms = db.scalar(select(RecordContractTerms).where(RecordContractTerms.contract_id == contract.id,
            RecordContractTerms.store_id == single_store(db)))
        ids = [terms.price_snapshot.get('batch_id'), terms.gift_batch_id] if terms else []
        query = query.where(batches.c.id.in_([value for value in ids if value]))
    candidate = db.execute(query.limit(1)).mappings().one_or_none()
    if candidate is None:
        raise HTTPException(404, '价格原表尚未发布或不属于本店品牌')
    if contract is not None:
        batch = allowed_batch(db, candidate['kind'], candidate['id'], contract=contract)
    else:
        batch = None
    names = ('id', 'version', 'store_id', 'brand', 'kind', 'contract_id', 'filename', 'content_type',
             'size', 'sha256', 'content', 'object_key', 'scan_state', 'scan_code', 'created_by', 'created_at')
    data = db.execute(select(*(files.c[name] for name in names)).join(batches,
        (batches.c.file_id == files.c.id) & (batches.c.store_id == files.c.store_id) &
        (batches.c.kind == files.c.kind) & (batches.c.brand == files.c.brand)).where(
            batches.c.id == candidate['id'], files.c.id == key, files.c.contract_id.is_(None))).mappings().one_or_none()
    if data is None or (batch is None and data['brand'] != brand):
        raise HTTPException(404, '价格原表品牌或发布来源不匹配')
    return SimpleNamespace(**dict(data))
