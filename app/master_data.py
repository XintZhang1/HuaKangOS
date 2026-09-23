"""Typed master validation and atomic opening imports; no inferred legacy workflow."""
from datetime import date
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from fastapi import HTTPException
from .db import today, utcnow
from .models import User, Vehicle, Sale, Repair, Policy, CashEntry, AppMetadata
from .flow_models import Customer, Account, Item, Case, StockMove, Member
from .master_models import (Supplier, Insurer, Warehouse, StorageLocation, MaterialCategory, MaterialBrand, WorkItem,
    Team, AgencyProject, VehicleModel, MemberTier, ItemProfile, MasterReceipt, OpeningBatch, OpeningStockEntry)
from .vehicle_catalog_models import VehicleBrand,VehicleSeries,ModelClassification
from .tenancy import single_store, role_for_store
from .services import plain, audit


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)


class NamedInput(Strict):
    code: str = Field(min_length=1,max_length=40,pattern=r'^[A-Za-z0-9_.-]+$')
    name: str = Field(min_length=1,max_length=120)
    active: bool = True


class SeriesInput(NamedInput):
    brand_id: int = Field(gt=0,strict=True)


class SupplierInput(NamedInput):
    tax_identifier: str = Field(default='',max_length=40,pattern=r'^[A-Za-z0-9-]*$')
    contact_name: str = Field(default='',max_length=80)
    phone: str = Field(default='',max_length=30,pattern=r'^[0-9+() \-]*$')
    payment_terms_days: int = Field(default=0,ge=0,le=365,strict=True)


class InsurerInput(NamedInput):
    license_number: str = Field(default='',max_length=60)
    claims_phone: str = Field(default='',max_length=30,pattern=r'^[0-9+() \-]*$')
    settlement_days: int = Field(default=0,ge=0,le=365,strict=True)


class WarehouseInput(NamedInput):
    warehouse_type: Literal['vehicles','materials','mixed']
    address: str = Field(default='',max_length=200)


class LocationInput(NamedInput):
    warehouse_id: int = Field(gt=0,strict=True)


class CategoryInput(NamedInput):
    parent_id: int | None = Field(default=None,gt=0,strict=True)


class WorkInput(NamedInput):
    billing_unit: Literal['job','hour']
    standard_minutes: int = Field(default=0,ge=0,le=100000,strict=True)
    standard_fee_cents: int = Field(default=0,ge=0,le=100000000000,strict=True)
    warranty_days: int = Field(default=0,ge=0,le=3650,strict=True)


class TeamInput(NamedInput):
    leader_user_id: int | None = Field(default=None,gt=0,strict=True)


class AgencyInput(NamedInput):
    service_fee_cents: int = Field(default=0,ge=0,le=100000000000,strict=True)
    expected_days: int = Field(default=0,ge=0,le=365,strict=True)


class VehicleModelInput(NamedInput):
    brand: str = Field(min_length=1,max_length=80)
    model_year: int = Field(ge=1990,le=2100,strict=True)
    fuel_type: Literal['petrol','diesel','electric','hybrid','plugin_hybrid']
    seats: int = Field(ge=1,le=60,strict=True)
    displacement_ml: int = Field(default=0,ge=0,le=20000,strict=True)
    battery_wh: int = Field(default=0,ge=0,le=2000000,strict=True)
    guide_price_cents: int = Field(default=0,ge=0,le=100000000000,strict=True)

    @model_validator(mode='after')
    def powertrain(self):
        if self.fuel_type == 'electric' and (self.displacement_ml or not self.battery_wh):
            raise ValueError('纯电车型排量必须为零，并填写动力电池容量')
        if self.fuel_type in {'petrol','diesel'} and (not self.displacement_ml or self.battery_wh):
            raise ValueError('燃油车型须填写排量，动力电池容量为零')
        return self


class TierInput(NamedInput):
    annual_fee_cents: int = Field(default=0,ge=0,le=100000000000,strict=True)
    validity_months: int = Field(default=12,ge=1,le=120,strict=True)
    discount_basis_points: int = Field(default=10000,ge=0,le=10000,strict=True)


class ItemProfileInput(Strict):
    item_id: int = Field(gt=0,strict=True)
    category_id: int = Field(gt=0,strict=True)
    location_id: int = Field(gt=0,strict=True)
    supplier_id: int | None = Field(default=None,gt=0,strict=True)
    brand_id: int | None = Field(default=None,gt=0,strict=True)
    active: bool = True


def field(key,label,type='text',required=True,**extra):
    return {'key':key,'label':label,'type':type,'required':required,**extra}


COMMON = [field('code','编码'),field('name','名称'),field('active','启用','bool')]
MANAGE = {'admin','manager'}
STOCK_MANAGE = MANAGE | {'inventory'}
SERVICE_MANAGE = MANAGE | {'service'}
MONEY_READ = MANAGE | {'finance','auditor'}
READ_ROLES = {
    'vehicle_brands':MONEY_READ | {'sales','service','inventory'},
    'vehicle_series':MONEY_READ | {'sales','service','inventory'},
    'suppliers': MONEY_READ | {'inventory'}, 'insurers': MONEY_READ | {'service'},
    'warehouses': MONEY_READ | {'inventory','service','technician'},
    'locations': MONEY_READ | {'inventory','service','technician'},
    'material_brands': MONEY_READ | {'inventory','service','technician'},
    'material_categories': MONEY_READ | {'inventory','service','technician'},
    'work_items': MONEY_READ | {'service','technician'},
    'teams': MONEY_READ | {'service','technician','inventory'},
    'agency_projects': MONEY_READ | {'sales','service'},
    'vehicle_models': MONEY_READ | {'sales','service','inventory'},
    'member_tiers': MONEY_READ | {'sales','service'},
    'item_profiles': MONEY_READ | {'inventory','service','technician'},
}
CATALOG = {
    'vehicle_brands':(VehicleBrand,NamedInput,'车辆品牌',STOCK_MANAGE,[]),
    'vehicle_series':(VehicleSeries,SeriesInput,'车辆车系',STOCK_MANAGE,[field('brand_id','所属品牌','ref',ref_kind='vehicle_brands')]),
    'suppliers':(Supplier,SupplierInput,'供应商',MANAGE,[field('tax_identifier','统一社会信用代码','text',False),field('contact_name','联系人','text',False),field('phone','联系电话','text',False),field('payment_terms_days','约定付款天数','int')]),
    'insurers':(Insurer,InsurerInput,'保险公司',MANAGE,[field('license_number','机构许可证号','text',False),field('claims_phone','理赔联系电话','text',False),field('settlement_days','约定结算天数','int')]),
    'warehouses':(Warehouse,WarehouseInput,'仓库',STOCK_MANAGE,[field('warehouse_type','库别','select',options=['vehicles','materials','mixed']),field('address','地址','text',False)]),
    'locations':(StorageLocation,LocationInput,'库位',STOCK_MANAGE,[field('warehouse_id','所属仓库','ref',ref_kind='warehouses')]),
    'material_brands':(MaterialBrand,NamedInput,'物资品牌',STOCK_MANAGE,[]),
    'material_categories':(MaterialCategory,CategoryInput,'物资分类',STOCK_MANAGE,[field('parent_id','上级分类','ref',False,ref_kind='material_categories')]),
    'work_items':(WorkItem,WorkInput,'作业项目',SERVICE_MANAGE,[field('billing_unit','计费单位','select',options=['job','hour']),field('standard_minutes','参考工时（分钟）','int'),field('standard_fee_cents','参考收费（元）','money_cents'),field('warranty_days','作业质保天数','int')]),
    'teams':(Team,TeamInput,'车间班组',SERVICE_MANAGE,[field('leader_user_id','班组负责人','ref',False,ref_kind='employees')]),
    'agency_projects':(AgencyProject,AgencyInput,'代办项目',SERVICE_MANAGE,[field('service_fee_cents','参考服务收费（元）','money_cents'),field('expected_days','预计办理天数','int')]),
    'vehicle_models':(VehicleModel,VehicleModelInput,'车型参数',STOCK_MANAGE,[field('brand','品牌'),field('model_year','年款','int'),field('fuel_type','动力类型','select',options=['petrol','diesel','electric','hybrid','plugin_hybrid']),field('seats','座位数','int'),field('displacement_ml','发动机排量（毫升）','int'),field('battery_wh','动力电池容量（瓦时）','int'),field('guide_price_cents','指导价（元）','money_cents')]),
    'member_tiers':(MemberTier,TierInput,'会员等级',MANAGE,[field('annual_fee_cents','参考年费（元）','money_cents'),field('validity_months','有效月数','int'),field('discount_basis_points','参考结算比例（万分数；须另行批准实际会员价）','int')]),
    'item_profiles':(ItemProfile,ItemProfileInput,'物资归类与库位',STOCK_MANAGE,[field('item_id','现有物资','ref',ref_kind='items'),field('category_id','物资分类','ref',ref_kind='material_categories'),field('location_id','默认库位','ref',ref_kind='locations'),field('supplier_id','默认供应商','ref',False,ref_kind='suppliers'),field('brand_id','物资品牌','ref',False,ref_kind='material_brands'),field('active','启用','bool')]),
}
REFERENCE_GUARDS = {}


def register_reference_guard(kind, guard):
    """A business subsystem registers a predicate for its open master references."""
    REFERENCE_GUARDS.setdefault(kind,[]).append(guard)


def kind_config(kind):
    if kind not in CATALOG:
        raise HTTPException(404,'主资料类型不存在')
    return CATALOG[kind]


def ensure_read(user, kind):
    kind_config(kind)
    if user.role not in READ_ROLES[kind]:
        raise HTTPException(403,'当前门店岗位不能查看此类经营主资料')


def hidden_fields(user, kind):
    if kind=='suppliers' and user.role=='inventory':
        return {'tax_identifier','payment_terms_days'}
    if kind=='work_items' and user.role=='technician':
        return {'standard_fee_cents'}
    if kind=='item_profiles' and user.role in {'service','technician'}:
        return {'supplier_id'}
    return set()


def visible_master(user, kind, row):
    return {key:value for key,value in plain(row).items() if key not in hidden_fields(user,kind)}


def require_active(db, kind, record_id):
    store = single_store(db)
    model = Item if kind == 'items' else kind_config(kind)[0]
    row = db.scalar(select(model).where(model.id==record_id,model.store_id==store).with_for_update())
    if not row or not row.active:
        raise HTTPException(422,'引用的'+('物资' if kind=='items' else kind_config(kind)[2])+'不存在、已停用或不属于当前门店')
    return row


def _ensure_role(user, roles):
    if user.role not in roles:
        raise HTTPException(403,'当前门店岗位没有维护此资料的权限')


def _digest(operation,payload):
    return hashlib.sha256(json.dumps([operation,payload],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _command(db,user,key,operation,payload,perform):
    store = single_store(db)
    digest = _digest(operation,payload)
    existing = db.scalar(select(MasterReceipt).where(MasterReceipt.store_id==store,MasterReceipt.request_key==key))
    if existing:
        if existing.actor_id != user.id or existing.digest != digest:
            raise HTTPException(409,'此请求编号已用于不同操作或内容，请刷新核对')
        return existing.result
    try:
        result = perform(store)
        db.add(MasterReceipt(store_id=store,request_key=key,digest=digest,actor_id=user.id,result=result))
        db.commit()
    except (IntegrityError,StaleDataError) as exc:
        db.rollback()
        raise HTTPException(409,'编码、引用或版本发生冲突；整次操作未保存，请刷新核对') from exc
    except OperationalError as exc:
        db.rollback()
        code=getattr(exc.orig,'sqlite_errorcode',0)
        sqlstate=getattr(exc.orig,'sqlstate',getattr(exc.orig,'pgcode',None))
        if code & 255 in {5,6} or sqlstate in {'40001','40P01'}:
            raise HTTPException(409,'其他操作正在修改这些资料；本次未保存，请刷新核对，不要盲目重试') from exc
        raise
    return result


def public_catalog(user):
    kinds={}
    for kind,(_,schema,label,roles,fields) in CATALOG.items():
        if user.role not in READ_ROLES[kind]:continue
        definitions=[]
        for field in ([] if kind=='item_profiles' else COMMON)+fields:
            if field['key'] in hidden_fields(user,kind):continue
            definition=dict(field);typed=schema.model_fields[field['key']]
            if not typed.is_required():definition['default']=typed.default
            definitions.append(definition)
        kinds[kind]={'label':label,'can_write':user.role in roles and not getattr(user,'_aggregate_scope',False),'fields':definitions}
    return {'kinds':kinds,'can_import':user.role in MANAGE and not getattr(user,'_aggregate_scope',False)}


def _check_references(db,user,kind,v,row_id=None):
    if kind == 'vehicle_series':
        require_active(db,'vehicle_brands',v['brand_id'])
    elif kind == 'locations':
        require_active(db,'warehouses',v['warehouse_id'])
    elif kind == 'material_categories' and v['parent_id']:
        seen = {row_id} if row_id else set()
        current = v['parent_id']
        while current:
            if current in seen:
                raise HTTPException(422,'物资分类不能引用自身或形成循环')
            seen.add(current)
            parent = require_active(db,'material_categories',current)
            current = parent.parent_id
    elif kind == 'teams' and v['leader_user_id']:
        leader = db.scalar(select(User).where(User.id==v['leader_user_id']))
        if role_for_store(db,leader,single_store(db)) not in {'admin','manager','service','technician'}:
            raise HTTPException(422,'班组负责人必须是本店启用的店长、服务顾问或技师')
    elif kind == 'item_profiles':
        require_active(db,'items',v['item_id'])
        require_active(db,'material_categories',v['category_id'])
        location = require_active(db,'locations',v['location_id'])
        warehouse = require_active(db,'warehouses',location.warehouse_id)
        if warehouse.warehouse_type == 'vehicles':
            raise HTTPException(422,'物资不能归入仅存放整车的仓库')
        if v['supplier_id']:
            require_active(db,'suppliers',v['supplier_id'])
        if v['brand_id']:
            brand = db.scalar(select(MaterialBrand).where(MaterialBrand.id==v['brand_id'],MaterialBrand.store_id==single_store(db)).with_for_update())
            if not brand or (v['active'] and not brand.active):
                raise HTTPException(422,'物资品牌不存在、已停用或不属于当前门店')


def _deactivate_guard(db,kind,row):
    if kind in {'locations','warehouses'}:
        from .vehicle_operations_service import location_in_use
        if location_in_use(db,**{'location_id' if kind=='locations' else 'warehouse_id':row.id}):
            raise HTTPException(409,'仍有实际车辆、隔离车辆或未完成车辆作业，不能停用')
    references = {'vehicle_brands':[(VehicleSeries,VehicleSeries.brand_id)],'warehouses':[(StorageLocation,StorageLocation.warehouse_id)],
        'locations':[(ItemProfile,ItemProfile.location_id)],
        'material_categories':[(MaterialCategory,MaterialCategory.parent_id),(ItemProfile,ItemProfile.category_id)],
        'suppliers':[(ItemProfile,ItemProfile.supplier_id)],
        'material_brands':[(ItemProfile,ItemProfile.brand_id)]}
    for model,column in references.get(kind,[]):
        if db.scalar(select(model.id).where(column==row.id,model.active.is_(True)).limit(1)):
            raise HTTPException(409,'仍有启用的下游资料引用，先调整下游资料后再停用')
    if kind=='vehicle_series' and db.scalar(select(ModelClassification.id).join(VehicleModel,VehicleModel.id==ModelClassification.model_id).where(ModelClassification.series_id==row.id,VehicleModel.active.is_(True)).limit(1)):
        raise HTTPException(409,'仍有启用车型归属此车系，请先核对调整车型归属或停用车型')
    if kind=='suppliers':
        from .procurement_service import has_open_supplier_orders
        from .vehicle_procurement_service import has_open_supplier_orders as has_open_vehicle_orders
        if has_open_supplier_orders(db,row.id) or has_open_vehicle_orders(db,row.id):
            raise HTTPException(409,'仍有未结采购引用此供应商，不能停用')
    if any(guard(db,row.id) for guard in REFERENCE_GUARDS.get(kind,[])):
        raise HTTPException(409,'仍有未结业务引用此资料，不能停用')


def save_master(db,user,kind,key,values,record_id=None,version=None):
    model,schema,label,roles,_ = kind_config(kind)
    _ensure_role(user,roles)
    try:
        parsed = schema.model_validate(values).model_dump()
    except ValidationError as exc:
        fields = '、'.join('.'.join(map(str,e['loc'])) or '资料组合' for e in exc.errors())
        raise HTTPException(422,'请检查'+label+'字段：'+fields+'；整数及金额精度不得超出允许范围')
    def perform(store):
        row = None
        if record_id:
            row = db.scalar(select(model).where(model.id==record_id,model.store_id==store).with_for_update())
            if not row:
                raise HTTPException(404,'当前门店资料不存在')
            if version != row.version:
                raise HTTPException(409,'资料已变化，请刷新后核对，不能覆盖他人的修改')
            if kind=='vehicle_series' and row.brand_id!=parsed['brand_id'] and db.scalar(select(ModelClassification.id).where(ModelClassification.series_id==row.id).limit(1)):
                raise HTTPException(409,'车系已有明确车型归属，不能换品牌；请新建对应车系再明确调整车型归属')
            # Old clients do not know brand_id; omitted is not an instruction to erase it.
            if kind == 'item_profiles' and 'brand_id' not in values:
                parsed['brand_id'] = row.brand_id
            if kind == 'item_profiles' and row.item_id != parsed['item_id']:
                raise HTTPException(409,'物资绑定对象不能直接更换，请停用原绑定后新建')
            if kind=='warehouses' and row.warehouse_type!=parsed['warehouse_type']:
                from .warehouse_stock import has_location_history as material_location_history
                if material_location_history(db,warehouse_id=row.id):
                    raise HTTPException(409,'仓库已有物资库位启用或收发历史，不能改写原仓库类型；请新建仓库保留历史')
            if kind=='warehouses' and parsed['warehouse_type']=='vehicles' and row.warehouse_type!='vehicles':
                from .warehouse_stock import location_in_use
                if any(location_in_use(db,lid) for lid in db.scalars(select(StorageLocation.id).where(StorageLocation.warehouse_id==row.id))):
                    raise HTTPException(409,'仓库仍有实际物资或未完仓储作业，不能改为仅存放整车')
                if db.scalar(select(ItemProfile.id).join(StorageLocation,ItemProfile.location_id==StorageLocation.id)
                    .where(StorageLocation.warehouse_id==row.id,ItemProfile.active.is_(True)).limit(1)):
                    raise HTTPException(409,'仓库仍有启用的物资归类，不能改为仅存放整车')
            if kind=='locations' and parsed['warehouse_id']!=row.warehouse_id:
                from .warehouse_stock import has_location_history as material_location_history
                if material_location_history(db,location_id=row.id):raise HTTPException(409,'库位已有物资启用或收发历史，不能改写所属仓库；请新建库位保留历史')
                from .vehicle_operations_service import has_location_history
                if has_location_history(db,location_id=row.id):raise HTTPException(409,'库位已有车辆出入或隔离历史，不能改写所属仓库；请新建库位保留历史')
                from .vehicle_operations_service import location_in_use as vehicle_location_in_use
                if vehicle_location_in_use(db,location_id=row.id):raise HTTPException(409,'库位仍有车辆或未完成车辆作业，须办理真实移库后再调整所属仓库')
                from .warehouse_stock import location_in_use
                if location_in_use(db,row.id):raise HTTPException(409,'库位仍有实际物资或未完仓储作业，须通过真实移库后再调整所属仓库')
                if db.scalar(select(ItemProfile.id).where(ItemProfile.location_id==row.id,ItemProfile.active.is_(True)).limit(1)):
                    raise HTTPException(409,'库位仍被物资使用，不能直接更换所属仓库；请先调整物资默认库位')
            if row.active and not parsed['active']:
                _deactivate_guard(db,kind,row)
            if kind=='warehouses' and parsed['warehouse_type']!=row.warehouse_type:
                from .vehicle_operations_service import has_location_history
                if has_location_history(db,warehouse_id=row.id):raise HTTPException(409,'仓库已有车辆出入或隔离历史，不能改写仓库类型；请新建仓库保留历史')
            if kind=='warehouses' and parsed['warehouse_type'] not in {'vehicles','mixed'}:
                from .vehicle_operations_service import location_in_use as vehicle_location_in_use
                if vehicle_location_in_use(db,warehouse_id=row.id):raise HTTPException(409,'仓库仍有车辆或未完成车辆作业，不能改为仅存放物资')
        _check_references(db,user,kind,parsed,record_id)
        before = plain(row) if row else None
        if row:
            for name,value in parsed.items():setattr(row,name,value)
            row.updated_at=utcnow()
        else:
            row=model(store_id=store,**parsed);db.add(row)
        db.flush()
        result=plain(row)
        audit(db,user.id,'master_update' if record_id else 'master_create','typed_master',row.id,before,result,reason=label)
        return result
    return _command(db,user,key,'master:'+kind,{'id':record_id,'version':version,'values':values},perform)


def validate_case_references(db,kind,values):
    """Opt-in typed IDs for new workflow versions; callers store returned snapshots."""
    mapping={'supplier_master_id':'suppliers','insurer_master_id':'insurers','work_item_id':'work_items',
             'team_id':'teams','agency_project_id':'agency_projects','vehicle_model_id':'vehicle_models'}
    result={}
    for field_name,master_kind in mapping.items():
        if values.get(field_name) is not None:
            row=require_active(db,master_kind,values[field_name])
            result[field_name]={'id':row.id,'version':row.version,'code':row.code,'name':row.name}
    return result


class OpeningCustomer(Strict):
    name: str = Field(min_length=1,max_length=100)
    phone: str = Field(default='',max_length=30,pattern=r'^[0-9+() \-]*$')
    contact_allowed: bool = False
    owner_username: str = Field(min_length=3,max_length=40)


class OpeningAccount(Strict):
    name: str = Field(min_length=1,max_length=100)
    account_type: Literal['bank','cash']


class OpeningItem(Strict):
    sku: str = Field(min_length=1,max_length=60)
    name: str = Field(min_length=1,max_length=120)
    unit: str = Field(default='件',min_length=1,max_length=20)
    reorder_milli: int = Field(default=0,ge=0,le=10**12,strict=True)
    opening_quantity_milli: int = Field(default=0,ge=0,le=10**12,strict=True)
    opening_value_cents: int = Field(default=0,ge=0,le=10**12,strict=True)
    source_reference: str = Field(default='',max_length=160)

    @model_validator(mode='after')
    def stock_source(self):
        if not self.opening_quantity_milli and self.opening_value_cents:
            raise ValueError('零库存不能有期初库存价值')
        if self.opening_quantity_milli and not self.source_reference:
            raise ValueError('每笔期初实物必须填写盘点或交接来源编号')
        return self


class OpeningSource(Strict):
    opening_date: date
    source_reference: str = Field(min_length=3,max_length=160)
    customers: list[OpeningCustomer] = Field(default_factory=list,max_length=300)
    accounts: list[OpeningAccount] = Field(default_factory=list,max_length=100)
    items: list[OpeningItem] = Field(default_factory=list,max_length=300)


def _reject_duplicate_json(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('JSON 同一对象包含重复字段：'+key)
        result[key]=value
    return result


def _opening_errors(db,source_text):
    errors=[]
    if len(source_text.encode('utf-8'))>85000:
        return None,[{'section':'source','row':0,'field':'JSON','message':'原资料超过 85 KB，请核对并精简到本次清单'}]
    try:
        raw=json.loads(source_text,object_pairs_hook=_reject_duplicate_json)
        source=OpeningSource.model_validate(raw)
    except (json.JSONDecodeError,ValueError,ValidationError) as exc:
        if isinstance(exc,ValidationError):
            for err in exc.errors():
                loc=err['loc'];section=str(loc[0]) if loc else 'source'
                row=loc[1]+1 if len(loc)>1 and isinstance(loc[1],int) else 0
                messages={'missing':'缺少必填资料','extra_forbidden':'不接受未定义字段','int_type':'必须填写整数，不接受小数或文本',
                    'string_type':'必须填写文字','string_too_short':'文字为空或长度不足','string_too_long':'文字超过允许长度',
                    'string_pattern_mismatch':'文字格式不符合要求','literal_error':'选项不在允许范围','date_from_datetime_parsing':'日期格式应为年-月-日',
                    'greater_than_equal':'数值低于允许下限','less_than_equal':'数值超过允许上限'}
                message=messages.get(err['type'],'字段不合法，请核对类型、精度及必填资料')
                if err['type']=='value_error':message=str(err.get('ctx',{}).get('error','资料组合不符合规则'))
                errors.append({'section':section,'row':row,'field':'.'.join(map(str,loc[2:] if row else loc[1:])),
                    'message':message})
        else:errors.append({'section':'source','row':0,'field':'JSON','message':'JSON 格式错误或重复字段，请重新检查原资料'})
        return None,errors
    if not date(2000,1,1)<=source.opening_date<=today():
        errors.append({'section':'source','row':0,'field':'opening_date','message':'期初日期必须为 2000 年起且不晚于今天'})
    if not any((source.customers,source.accounts,source.items)):
        errors.append({'section':'source','row':0,'field':'rows','message':'原资料至少包含一行客户、账户或物资'})
    for section,key in [('accounts','name'),('items','sku')]:
        seen=set()
        for index,row in enumerate(getattr(source,section),1):
            value=getattr(row,key)
            if value in seen:errors.append({'section':section,'row':index,'field':key,'message':'本份资料内编码或名称重复'})
            seen.add(value)
    seen_customers=set()
    for index,row in enumerate(source.customers,1):
        owner=db.scalar(select(User).where(User.username==row.owner_username,User.active.is_(True)))
        if role_for_store(db,owner,single_store(db)) not in {'admin','manager','sales','service','reception','customer_service'}:
            errors.append({'section':'customers','row':index,'field':'owner_username','message':'客户负责人不是本店启用的客户业务岗位'})
        key=(row.name,row.phone)
        if key in seen_customers:errors.append({'section':'customers','row':index,'field':'name','message':'姓名及电话完全相同的记录重复，请人工确认'})
        seen_customers.add(key)
    return source,errors


def _blank_store(db):
    marker=db.get(AppMetadata,'demo')
    if marker and marker.value.get('enabled'):
        raise HTTPException(409,'演示数据库不能导入正式期初资料，请建立新的独立数据库')
    for model in (Customer,Account,Item,Case,Vehicle,Sale,Repair,Policy,CashEntry,StockMove,Member):
        if db.scalar(select(model.id).limit(1)):
            raise HTTPException(409,'当前门店已有业务或经营主档；期初导入只允许新门店空业务数据，不会覆盖或推断旧单')
    if db.scalar(select(OpeningBatch.id).where(OpeningBatch.status=='confirmed').limit(1)):
        raise HTTPException(409,'当前门店期初已确认，不能重复导入')


def _totals(source):
    return {'customer_count':len(source.customers),'account_count':len(source.accounts),'item_count':len(source.items),
        'stock_row_count':sum(i.opening_quantity_milli>0 for i in source.items),
        'quantity_milli':sum(i.opening_quantity_milli for i in source.items),
        'inventory_value_cents':sum(i.opening_value_cents for i in source.items)}


def batch_info(row):
    return {k:v for k,v in plain(row).items() if k!='source_text'}


def preflight(db,user,key,source_text):
    _ensure_role(user,MANAGE)
    single_store(db)
    def perform(store):
        source,errors=_opening_errors(db,source_text)
        try:_blank_store(db)
        except HTTPException as exc:errors.append({'section':'store','row':0,'field':'existing_data','message':exc.detail})
        if errors:return {'valid':False,'errors':errors,'batch':None}
        digest=hashlib.sha256(source_text.encode('utf-8')).hexdigest()
        row=OpeningBatch(store_id=store,source_text=source_text,source_digest=digest,source_reference=source.source_reference,
            opening_date=source.opening_date,totals=_totals(source),prepared_by=user.id)
        db.add(row);db.flush()
        audit(db,user.id,'opening_preflight','opening',row.id,after={'digest':digest,'totals':row.totals},reason='期初原资料预检通过')
        return {'valid':True,'errors':[],'batch':batch_info(row)}
    return _command(db,user,key,'opening_preflight',{'source_text':source_text},perform)


def _apply_opening(db,user,batch,source):
    store=single_store(db)
    for row in source.customers:
        owner=db.scalar(select(User).where(User.username==row.owner_username))
        db.add(Customer(store_id=store,name=row.name,phone=row.phone,contact_allowed=row.contact_allowed,
                        owner_id=owner.id,note='期初资料：'+source.source_reference))
    for row in source.accounts:
        db.add(Account(store_id=store,name=row.name,account_type=row.account_type,active=True))
    for row in source.items:
        qty,value=row.opening_quantity_milli,row.opening_value_cents
        # Unit cost is only a display/reference price; exact authoritative value is preserved separately.
        unit_cost=((value*1000+qty//2)//qty) if qty else 0
        item=Item(store_id=store,sku=row.sku,name=row.name,unit=row.unit,reorder_milli=row.reorder_milli,
                  quantity_milli=qty,inventory_value_cents=value,unit_cost_cents=unit_cost,active=True)
        db.add(item);db.flush()
        if qty:
            db.add(OpeningStockEntry(store_id=store,batch_id=batch.id,item_id=item.id,quantity_milli=qty,value_cents=value,
                business_date=source.opening_date,source_reference=row.source_reference,actor_id=user.id))
    db.flush()


def opening_action(db,user,batch_id,key,version,digest,confirm=False,expected_totals=None):
    _ensure_role(user,MANAGE)
    def perform(store):
        batch=db.scalar(select(OpeningBatch).where(OpeningBatch.id==batch_id,OpeningBatch.store_id==store).with_for_update())
        if not batch:raise HTTPException(404,'当前门店预检批次不存在')
        from .opening_import_models import OpeningImport
        if db.scalar(select(OpeningImport.id).where(OpeningImport.batch_id==batch.id)):raise HTTPException(409,'此批次使用三岗期初流程，请从正式期初核验办理')
        if batch.version!=version:raise HTTPException(409,'预检批次已变化，请刷新核对')
        if digest!=batch.source_digest or hashlib.sha256(batch.source_text.encode('utf-8')).hexdigest()!=digest:
            raise HTTPException(409,'原资料摘要不一致，必须重新预检')
        _blank_store(db)
        source,errors=_opening_errors(db,batch.source_text)
        if errors:raise HTTPException(409,'原资料引用已变化，请重新预检并核对负责人')
        if _totals(source)!=batch.totals:raise HTTPException(409,'原资料与预检汇总不一致')
        if confirm:
            if batch.status!='trial_passed':raise HTTPException(409,'须先完成试导入并核对结果')
            if expected_totals!=batch.totals:raise HTTPException(409,'确认的数量、金额或行数与预检汇总不一致')
            _apply_opening(db,user,batch,source)
            batch.status='confirmed';batch.confirmed_store_key=store;batch.confirmed_by=user.id;batch.confirmed_at=utcnow()
        else:
            if batch.status not in {'prepared','trial_passed'}:raise HTTPException(409,'该批次不能再次试导入')
            nested=db.begin_nested()
            try:
                _apply_opening(db,user,batch,source)
            finally:
                nested.rollback()
            batch.status='trial_passed'
        batch.updated_at=utcnow();db.flush()
        audit(db,user.id,'opening_confirm' if confirm else 'opening_trial','opening',batch.id,
              after={'digest':digest,'totals':batch.totals},reason='期初确认入账' if confirm else '试导入成功，业务记录全部回滚')
        return {'batch':batch_info(batch),'business_rolled_back':not confirm}
    return _command(db,user,key,'opening_confirm' if confirm else 'opening_trial',
        {'batch_id':batch_id,'version':version,'digest':digest,'totals':expected_totals},perform)


def stockflow(db,user,item_id=None):
    _ensure_role(user,{'admin','manager','inventory','finance','auditor'})
    item_query=select(Item).order_by(Item.id)
    if item_id:item_query=item_query.where(Item.id==item_id)
    items=list(db.scalars(item_query.limit(501)))
    if len(items)>500:raise HTTPException(422,'请按物资查询；一次最多核对 500 项物资')
    ids=[item.id for item in items]
    openings=list(db.scalars(select(OpeningStockEntry).where(OpeningStockEntry.item_id.in_(ids))))
    moves=list(db.scalars(select(StockMove).where(StockMove.item_id.in_(ids))))
    cases={c.id:c for c in db.scalars(select(Case).where(Case.id.in_({r.case_id for r in moves})))}
    purposes={'purchase':'采购入库','issue':'领料出库','return':'退料入库','count':'盘点差异',
        'procurement_receipt':'采购验收入库','procurement_return':'采购退货出库',
        'transfer_out':'调拨发出','transfer_in':'调拨验收入库','transfer_return':'调拨退回入库'}
    result=[];totals=[]
    for item in items:
        facts=[{'id':r.id,'source':'期初','date':r.business_date.isoformat(),'quantity_milli':r.quantity_milli,
            'value_cents':r.value_cents,'reference':r.source_reference} for r in openings if r.item_id==item.id]
        facts += [{'id':r.id,'source':'业务','date':r.business_date.isoformat(),'quantity_milli':r.quantity_milli,
            'value_cents':r.value_cents,'case_id':r.case_id,
            'reference':purposes.get(r.purpose,'库存业务')+' / '+(cases[r.case_id].number if r.case_id in cases else str(r.case_id))} for r in moves if r.item_id==item.id]
        qty=value=0
        for fact in sorted(facts,key=lambda r:(r['date'],r['source']!='期初',r['id'])):
            qty+=fact['quantity_milli'];value+=fact['value_cents']
            result.append({'item_id':item.id,'sku':item.sku,'name':item.name,**fact,'running_quantity_milli':qty,'running_value_cents':value})
        totals.append({'item_id':item.id,'sku':item.sku,'quantity_milli':qty,'value_cents':value,
            'current_quantity_milli':item.quantity_milli,'current_value_cents':item.inventory_value_cents,
            'reconciled':qty==item.quantity_milli and value==item.inventory_value_cents})
    can_money=user.role in MONEY_READ
    if not can_money:
        result=[{k:v for k,v in r.items() if k not in {'value_cents','running_value_cents'}} for r in result]
        totals=[{k:v for k,v in r.items() if k not in {'value_cents','current_value_cents'}} | {'reconciled':r['quantity_milli']==r['current_quantity_milli']} for r in totals]
    return {'rows':result,'totals':totals,'can_money':can_money,'all_reconciled':all(r['reconciled'] for r in totals),
        'definition':'期初不可变账本加全部有效库存流水；数量为千分位、价值为分；与当前库存核对，不伪造历史余额'}
