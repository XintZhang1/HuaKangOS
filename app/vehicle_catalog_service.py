"""Scoped showroom catalogue; identities are linked explicitly, never by name."""
from fastapi import HTTPException
from sqlalchemy import select,or_
import hashlib
import unicodedata
from pydantic import ValidationError
from .db import utcnow
from .models import Vehicle,Sale
from .flow_models import VehicleHold
from .master_models import VehicleModel
from .vehicle_catalog_models import VehicleBrand,VehicleSeries,ModelClassification,VehicleClassification
from . import master_data as masters
from .tenancy import single_store
from .services import plain,audit

READ={'admin','manager','sales','service','inventory','finance','auditor'}
WRITE={'admin','manager','inventory'}


def entry_options(db,user):
    masters._ensure_role(user,WRITE);sid=single_store(db)
    brands=bounded(db,VehicleBrand,select(VehicleBrand).where(VehicleBrand.store_id==sid,VehicleBrand.active.is_(True)))
    brand_ids={r.id for r in brands}
    series=bounded(db,VehicleSeries,select(VehicleSeries).where(VehicleSeries.store_id==sid,VehicleSeries.active.is_(True)))
    return {'brands':[{'id':r.id,'name':r.name,'code':r.code,'version':r.version} for r in brands],
        'series':[{'id':r.id,'brand_id':r.brand_id,'name':r.name,'code':r.code,'version':r.version} for r in series if r.brand_id in brand_ids]}


def _entry_name(value):
    return ' '.join(unicodedata.normalize('NFKC',value).split()).casefold()


def _entry_code(kind,*parts):
    # The existing per-store code constraint also protects concurrent submissions.
    digest=hashlib.sha256('\x1f'.join(str(p) for p in parts).encode()).hexdigest()[:28]
    return 'Q'+kind+'_'+digest


def _entry_parent(db,user,sid,kind,values,parent=None):
    model,_,label,_,_=masters.kind_config(kind)
    prefix='brand' if kind=='vehicle_brands' else 'series'
    record_id=values[prefix+'_id'];version=values[prefix+'_version'];name=values[prefix+'_name']
    if record_id is not None:
        if name or version is None:raise HTTPException(422,'请重新选择'+label)
        row=masters.require_active(db,kind,record_id)
        if row.version!=version:raise HTTPException(409,label+'已更新，请重新打开表单选择')
        if parent is not None and row.brand_id!=parent.id:raise HTTPException(422,'车系不属于所选品牌，请重新选择车系')
        return row,False
    if version is not None or not _entry_name(name):raise HTTPException(422,'请填写'+label+'名称或选择已有资料')
    statement=select(model).where(model.store_id==sid)
    if parent is not None:statement=statement.where(model.brand_id==parent.id)
    matches=[r for r in bounded(db,model,statement) if _entry_name(r.name)==_entry_name(name)]
    if len(matches)>1:raise HTTPException(409,'已有多个同名'+label+'，请从列表选择')
    if matches:
        if not matches[0].active:raise HTTPException(409,'同名'+label+'已停用，请先在资料中核对')
        return matches[0],False
    fields={'name':name,'code':_entry_code(prefix.upper(),parent.id if parent else '',_entry_name(name)),'active':True}
    if parent is not None:fields['brand_id']=parent.id
    row=model(store_id=sid,**fields);db.add(row);db.flush()
    audit(db,user.id,'master_create','typed_master',row.id,None,plain(row),reason='新增车型时填写'+label)
    return row,True


def create_entry(db,user,key,values):
    """One explicit hierarchy submission; no stock, historical link, or price edits."""
    masters._ensure_role(user,WRITE)
    def operation(sid):
        # PostgreSQL serializes quick entries per store; SQLite/unique codes fail
        # closed on competing writers. A conflict rolls the entire entry back.
        from .models import Store
        if not db.scalar(select(Store).where(Store.id==sid,Store.active.is_(True)).with_for_update()):
            raise HTTPException(409,'当前门店不可用')
        brand,brand_created=_entry_parent(db,user,sid,'vehicle_brands',values)
        series,series_created=_entry_parent(db,user,sid,'vehicle_series',values,brand)
        model_fields={k:values[k] for k in ('name','model_year','fuel_type','seats','displacement_ml','battery_wh','guide_price_cents')}
        model_fields.update(brand=brand.name,active=True,code=_entry_code('MODEL',series.id,values['model_year'],_entry_name(values['name'])))
        try:parsed=masters.VehicleModelInput.model_validate(model_fields).model_dump()
        except ValidationError as exc:
            errors=exc.errors();detail=str(errors[0].get('ctx',{}).get('error',''))
            raise HTTPException(422,detail or '请检查车型名称、品牌、年款和动力参数') from exc
        all_models=bounded(db,VehicleModel,select(VehicleModel).where(VehicleModel.store_id==sid,VehicleModel.model_year==values['model_year']))
        named=[r for r in all_models if _entry_name(r.name)==_entry_name(values['name'])]
        relations={r.model_id:r for r in bounded(db,ModelClassification,select(ModelClassification).where(ModelClassification.store_id==sid))}
        matches=[r for r in named if r.id in relations and relations[r.id].series_id==series.id]
        unassigned=[r for r in named if r.id not in relations and _entry_name(r.brand)==_entry_name(brand.name)]
        if len(matches)>1:raise HTTPException(409,'同一车系已有多个同名年款，请先在车型目录核对')
        if unassigned:raise HTTPException(409,'已有同名年款待确认车系，请在车型目录确认归属后再使用')
        model_created=not matches
        if matches:
            model=matches[0];relation=relations[model.id]
            if not model.active:raise HTTPException(409,'该车型已停用，请先在车型资料中核对')
            if any(getattr(model,k)!=parsed[k] for k in model_fields if k not in {'code','brand'}):
                raise HTTPException(409,'该车系已有同名年款，但参数不同，请打开已有车型核对')
        else:
            model=VehicleModel(store_id=sid,**parsed);db.add(model);db.flush()
            audit(db,user.id,'master_create','typed_master',model.id,None,plain(model),reason='新增车型')
            relation=ModelClassification(store_id=sid,model_id=model.id,series_id=series.id);db.add(relation);db.flush()
            audit(db,user.id,'classify','vehicle_catalog',relation.id,None,plain(relation),reason='新增车型时选择所属品牌和车系')
        return {'model':plain(model),'brand':plain(brand),'series':plain(series),'classification':plain(relation),
            'created':{'brand':brand_created,'series':series_created,'model':model_created}}
    try:return masters._command(db,user,key,'vehicle_catalog:entry',values,operation)
    except HTTPException:
        db.rollback()
        raise


def bounded(db,model,statement=None):
    rows=list(db.scalars((statement if statement is not None else select(model)).limit(25001)))
    if len(rows)>25000:raise HTTPException(409,'车型或库存资料超过查询上限，请先缩小管理范围')
    return rows


def known_vehicle_models(db):
    from .opening_import_models import OpeningVehicleEntry
    from .vehicle_procurement_models import VehiclePurchaseReceipt,VehiclePurchaseLine,VehiclePurchaseShipment
    values={r.vehicle_id:r.model_id for r in bounded(db,OpeningVehicleEntry)}
    stmt=select(VehiclePurchaseReceipt.vehicle_id,VehiclePurchaseLine.model_id).join(
        VehiclePurchaseShipment,VehiclePurchaseShipment.id==VehiclePurchaseReceipt.shipment_id).join(
        VehiclePurchaseLine,VehiclePurchaseLine.id==VehiclePurchaseShipment.line_id).limit(25001)
    pairs=list(db.execute(stmt))
    if len(pairs)>25000:raise HTTPException(409,'车型来源超过核对上限')
    for key,model in pairs:
        if key in values and values[key]!=model:raise HTTPException(409,'车辆车型原始来源不一致，请核对原入库资料')
        values[key]=model
    return values


def model_snapshot(db,model_id):
    """New quotes freeze this value; subsequent master edits do not alter it."""
    model=masters.require_active(db,'vehicle_models',model_id)
    value={key:getattr(model,key) for key in ('id','version','code','name','brand','model_year','fuel_type',
        'seats','displacement_ml','battery_wh','guide_price_cents')}
    relation=db.scalar(select(ModelClassification).where(ModelClassification.model_id==model.id))
    if relation:
        series=masters.require_active(db,'vehicle_series',relation.series_id)
        brand=masters.require_active(db,'vehicle_brands',series.brand_id)
        value.update(classification_id=relation.id,classification_version=relation.version,series_id=series.id,
            series_code=series.code,series_name=series.name,series_version=series.version,
            brand_id=brand.id,brand_code=brand.code,brand_name=brand.name,brand_version=brand.version)
    return value


def assign(db,user,key,kind,v):
    masters._ensure_role(user,WRITE)
    def operation(sid):
        if kind=='model':
            model=masters.require_active(db,'vehicle_models',v['model_id'])
            if model.version!=v['model_version']:raise HTTPException(409,'车型参数已变化，请重新核对')
            series=masters.require_active(db,'vehicle_series',v['series_id'])
            masters.require_active(db,'vehicle_brands',series.brand_id)
            klass=ModelClassification;condition=klass.model_id==model.id
            fields={'model_id':model.id,'series_id':series.id}
        else:
            car=db.scalar(select(Vehicle).where(Vehicle.id==v['vehicle_id']).with_for_update())
            if not car:raise HTTPException(404,'当前门店车辆不存在')
            if car.version!=v['vehicle_version']:raise HTTPException(409,'车辆记录已变化，请重新核对')
            if car.vin!=v['vin'].upper():raise HTTPException(422,'实车VIN与当前库存记录不一致')
            masters.require_active(db,'vehicle_models',v['model_id'])
            origin=known_vehicle_models(db).get(car.id)
            if origin is not None and origin!=v['model_id']:
                raise HTTPException(409,'此车已有明确期初或采购车型来源，不能用目录分类覆盖原车型')
            existing=db.scalar(select(VehicleClassification).where(VehicleClassification.vehicle_id==car.id))
            if existing and existing.model_id!=v['model_id']:
                from .vehicle_operations_models import VehiclePosition
                from .vehicle_operations_service import unavailable_vehicle_ids
                busy=db.scalar(select(VehicleHold.case_id).where(VehicleHold.vehicle_id==car.id)) or db.scalar(select(Sale.id).where(Sale.active_vehicle_id==car.id))
                exited=db.scalar(select(VehiclePosition.id).where(VehiclePosition.vehicle_id==car.id,VehiclePosition.status!='stored'))
                if busy or exited or car.id in unavailable_vehicle_ids(db):
                    raise HTTPException(409,'车辆已有销售占用或实际出入库作业，不能更换已确认车型')
            klass=VehicleClassification;condition=klass.vehicle_id==car.id
            fields={'vehicle_id':car.id,'model_id':v['model_id']}
        row=db.scalar(select(klass).where(condition).with_for_update())
        if (row.version if row else 0)!=v['version']:raise HTTPException(409,'归属版本已变化，请刷新核对')
        before=plain(row) if row else None
        if row:
            for name,value in fields.items():setattr(row,name,value)
            row.updated_at=utcnow()
        else:row=klass(store_id=sid,**fields);db.add(row)
        db.flush();result=plain(row)
        audit(db,user.id,'classify','vehicle_catalog',row.id,before,result,reason=v['reason'])
        return result
    return masters._command(db,user,key,'vehicle_catalog:'+kind,v,operation)


def catalogue(db,user,q='',brand_id=None,series_id=None,fuel_type=None,min_seats=None,max_price_cents=None,available_only=False,page=1,unclassified_page=1,model_id=None,include_inactive=False):
    masters._ensure_role(user,READ);single_store(db)
    if include_inactive and model_id is None:raise HTTPException(409,'历史车型仅能按已冻结的明确型号引用')
    model_query=select(VehicleModel)
    if model_id is not None:model_query=model_query.where(VehicleModel.id==model_id)
    models={r.id:r for r in bounded(db,VehicleModel,model_query)}
    brands={r.id:r for r in bounded(db,VehicleBrand)}
    series={r.id:r for r in bounded(db,VehicleSeries)}
    mapping={r.model_id:r for r in bounded(db,ModelClassification)}
    explicit={r.vehicle_id:r for r in bounded(db,VehicleClassification)}
    known=known_vehicle_models(db)
    cars=bounded(db,Vehicle,select(Vehicle).where(Vehicle.approval_state=='approved'))
    held=set(db.scalars(select(VehicleHold.vehicle_id)))
    held.update(db.scalars(select(Sale.active_vehicle_id).where(Sale.active_vehicle_id.is_not(None))))
    excluded=set(db.scalars(select(VehicleHold.vehicle_id).where(VehicleHold.delivered.is_(True))))
    excluded.update(db.scalars(select(Sale.active_vehicle_id).where(Sale.sale_stage=='delivered',Sale.active_vehicle_id.is_not(None))))
    from .vehicle_operations_models import VehiclePosition
    excluded.update(db.scalars(select(VehiclePosition.vehicle_id).where(VehiclePosition.status.in_(['handover','exited']))))
    from .vehicle_operations_service import unavailable_vehicle_ids
    held.update(unavailable_vehicle_ids(db))
    from .vehicle_procurement_models import VehiclePurchaseReceipt,VehiclePurchaseReturn
    held.update(db.scalars(select(VehiclePurchaseReceipt.vehicle_id).join(VehiclePurchaseReturn,
        VehiclePurchaseReturn.shipment_id==VehiclePurchaseReceipt.shipment_id).where(VehiclePurchaseReturn.status.in_(['requested','approved']))))
    from .transfer_service import authority
    from .vehicle_transfer_models import VehicleCustody
    with authority(db,user,READ):
        custody={r.vin:r for r in bounded(db,VehicleCustody,select(VehicleCustody).where(VehicleCustody.vin.in_([c.vin for c in cars])))}
    stock={};unclassified=[]
    for car in cars:
        if car.id in excluded:continue
        current=custody.get(car.vin)
        if current and (current.current_vehicle_id!=car.id or current.current_store_id!=car.store_id):continue
        if current and current.pending_transfer_id:held.add(car.id)
        link=explicit.get(car.id);assigned_model_id=known.get(car.id) or (link.model_id if link else None)
        if model_id is not None and assigned_model_id!=model_id:continue
        if link and car.id in known and link.model_id!=known[car.id]:raise HTTPException(409,'已确认车型归属与原始入库车型冲突')
        vehicle={'id':car.id,'version':car.version,'vin':car.vin,'model_text':car.model,'color':car.color,
            'available':car.id not in held,'classification_version':link.version if link else 0,
            'source':'原入库车型' if car.id in known else '员工明确归属' if link else '待人工确认'}
        if assigned_model_id in models:stock.setdefault(assigned_model_id,[]).append(vehicle)
        else:unclassified.append(vehicle)
    records=[]
    for model in models.values():
        relation=mapping.get(model.id);family=series.get(relation.series_id) if relation else None
        brand=brands.get(family.brand_id) if family else None
        if not include_inactive and (not model.active or (family and not family.active) or (brand and not brand.active)):continue
        if brand_id is not None and (not brand or brand.id!=brand_id):continue
        if series_id is not None and (not family or family.id!=series_id):continue
        if fuel_type and model.fuel_type!=fuel_type:continue
        if min_seats is not None and model.seats<min_seats:continue
        if max_price_cents is not None and model.guide_price_cents>max_price_cents:continue
        if q and not any(q.casefold() in str(v).casefold() for v in (model.code,model.name,model.brand,family.name if family else '',brand.name if brand else '')):continue
        inventory=stock.get(model.id,[]);available=sum(r['available'] for r in inventory)
        if available_only and not available:continue
        records.append({'id':model.id,'version':model.version,'code':model.code,'name':model.name,
            'brand_id':brand.id if brand else None,'brand_name':brand.name if brand else model.brand,
            'series_id':family.id if family else None,'series_name':family.name if family else '未确认车系',
            'classification_version':relation.version if relation else 0,
            'model_year':model.model_year,'fuel_type':model.fuel_type,'seats':model.seats,
            'displacement_ml':model.displacement_ml,'battery_wh':model.battery_wh,'guide_price_cents':model.guide_price_cents,
            'stock_count':len(inventory),'available_count':available,'vehicles':inventory})
    records.sort(key=lambda r:(r['brand_name'],r['series_name'],r['name'],r['id']))
    return {'items':records[(page-1)*12:page*12],'total':len(records),'page':page,'can_manage':user.role in WRITE,
        'brands':[{'id':r.id,'name':r.name} for r in brands.values() if r.active],
        'series':[{'id':r.id,'brand_id':r.brand_id,'name':r.name} for r in series.values() if r.active and brands.get(r.brand_id) and brands[r.brand_id].active],
        'unclassified':unclassified[(unclassified_page-1)*12:unclassified_page*12],
        'unclassified_total':len(unclassified),'unclassified_page':unclassified_page,
        'unclassified_available_count':sum(vehicle['available'] for vehicle in unclassified),
        'scope':{'view':'current_vehicle_catalog','items_unit':'车型','total_unit':'车型',
            'filters':{'q':q,'brand_id':brand_id,'series_id':series_id,'fuel_type':fuel_type,
                'min_seats':min_seats,'max_price_cents':max_price_cents,'available_only':available_only,
                'model_id':model_id,'include_inactive':include_inactive},
            'items_page_size':12,'unclassified_page_size':12,'unclassified_unit':'当前在库VIN',
            'unclassified_paging':'独立使用unclassified_page；total和page仅属于车型列表',
            'unclassified_filtering':'未分类车辆不按q、品牌、车系、动力、座位、价格或available_only筛选；明确model_id时仍按该原车型筛选',
            'availability':'available_only只筛有可配车辆的车型组，不裁剪组内vehicles或unclassified；每车是否可配以原available为准。未分类在库及可配总数分别为unclassified_total和unclassified_available_count'},
        'notice':'展示本店已确认车型及在库车辆，已出库待交接和已交付车辆不计入在库。品牌与车系是不同层级的筛选目录；未分类车辆仅保留原车型文字，尚未确认所属品牌、车系或车型，不能按目录中的名称推定归属。未分类描述车型归属，available描述原占用提示，二者分开；不能把归属确认说成所有版本配车的普遍前提，也不能据available保证某张原单可配。实际配车按选定原单的flow_version、当前actions及原提交守卫核对。指导价是主档参考，不是本单核准售价。'}
