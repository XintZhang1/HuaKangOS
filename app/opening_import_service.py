"""New-store opening: preview, rollback trial, separate attestations, one commit."""
from contextlib import contextmanager
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib, json, uuid
from typing import Literal
from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select
from .db import today, utcnow
from .config import settings
from .models import User, Store, Vehicle, Sale, Repair, Policy, CashEntry, AppMetadata
from .flow_models import Case, Customer, Account, Item, StockMove, Member, Task, FlowEvent, FileAsset
from .master_models import OpeningBatch, OpeningStockEntry, VehicleModel, StorageLocation
from .master_data import Strict, OpeningSource, OpeningAccount, _command, _reject_duplicate_json, _apply_opening, _totals, require_active
from .tenancy import single_store, role_for_store
from .opening_import_models import OpeningImport, OpeningAttestation, OpeningAccountEntry, OpeningVehicleEntry
from . import flow_engine as flow

READ={'admin','manager','finance','inventory','auditor'}
MONEY={'admin','manager','finance','auditor'}
MANAGE={'admin','manager'}
ROLES={'trial':MANAGE,'approve':MANAGE,'verify_inventory':{'admin','inventory'},'verify_finance':{'admin','finance'},'confirm':MANAGE,'cancel':MANAGE,'reassign':MANAGE}
LABELS={'trial':'试导入并回滚','approve':'主管批准期初资料','verify_inventory':'核对实车与物资数量','verify_finance':'核对账户余额与库存价值','confirm':'确认启用期初资料','cancel':'取消未启用批次','reassign':'转交核验待办'}
STATUS={'prepared':'待试导入','trial_passed':'待主管复核','approved':'待分岗核验与确认','confirmed':'已启用','cancelled':'已取消'}


class AccountSource(OpeningAccount):
    account_id:int|None=Field(default=None,gt=0,strict=True)
    opening_balance_cents:int=Field(ge=0,le=100000000000000,strict=True)
    source_reference:str=Field(min_length=3,max_length=160)


class VehicleSource(Strict):
    vin:str=Field(pattern=r'^[A-HJ-NPR-Z0-9]{17}$')
    model_code:str=Field(min_length=1,max_length=40)
    location_code:str=Field(min_length=1,max_length=40)
    color:str=Field(default='',max_length=40)
    cost_cents:int=Field(ge=0,le=100000000000,strict=True)
    list_price_cents:int=Field(ge=0,le=100000000000,strict=True)
    source_reference:str=Field(min_length=3,max_length=160)
    condition:Literal['available_stock']


class Source(OpeningSource):
    schema_version:Literal[2]
    accounts:list[AccountSource]=Field(default_factory=list,max_length=100)
    vehicles:list[VehicleSource]=Field(default_factory=list,max_length=200)


@contextmanager
def authority(db,user,roles=READ):
    sid=single_store(db)
    if role_for_store(db,user,sid) not in roles:raise HTTPException(403,'当前门店岗位不能办理期初核验')
    previous=db.info.get('_opening_authority');db.info['_opening_authority']=(user.id,sid)
    try:yield sid
    finally:
        if previous is None:db.info.pop('_opening_authority',None)
        else:db.info['_opening_authority']=previous


def can_read_case(db,user,case):
    return not (getattr(user,'_aggregate_scope',False) or db.info.get('aggregate_scope')) and user.role in READ


def is_v2_batch(db,batch_id):
    return bool(db.scalar(select(OpeningImport.id).where(OpeningImport.batch_id==batch_id)))


def _execute(db,user,key,operation,payload,perform):
    try:return _command(db,user,key,operation,payload,perform)
    except HTTPException:
        db.rollback()
        raise


def _error(section,row,field,message):return {'section':section,'row':row,'field':field,'message':message}


def _entity_policy(db,user):
    from . import business_entity_service as entities
    from .business_entity_models import EntityPolicy
    with entities.authority(db,user):return db.scalar(select(EntityPolicy))


def _account_context(db,user,source):
    """Freeze explicit local account/channel IDs, never infer by matching name."""
    from . import business_entity_service as entities
    with entities.authority(db,user):
        policy=_entity_policy(db,user)
        if not policy:return None
        binding=entities.current_store_binding(db)
        if not binding:raise HTTPException(409,'本店尚无已批准经营主体绑定')
        result={'policy_id':policy.id,'binding_id':binding.id,'revision_id':binding.revision_id,'accounts':[]}
        for n,row in enumerate(source.accounts,1):
            account=db.scalar(select(Account).where(Account.id==row.account_id))
            approved=entities.current_account_binding(db,row.account_id)
            if not account or not approved or not account.active or (row.name,row.account_type)!=(account.name,account.account_type) or approved.account_name!=account.name or entities.revision_entity(db,approved.revision_id)!=entities.revision_entity(db,binding.revision_id):
                raise HTTPException(409,'期初账户须按编号明确选择本店已批准、启用且名称和类型一致的实际账户')
            result['accounts'].append({'row':n,'account_id':account.id,'account_version':account.version,'name':account.name,'account_type':account.account_type,'account_binding_id':approved.id,'account_revision_id':approved.revision_id})
        return result


def account_options(db,user):
    from . import business_entity_service as entities
    with entities.authority(db,user):
        if not _entity_policy(db,user):return {'policy_enabled':False,'approved_accounts':[]}
        binding=entities.current_store_binding(db);result=[]
        for account in db.scalars(select(Account).where(Account.active.is_(True)).order_by(Account.id)):
            approved=entities.current_account_binding(db,account.id)
            if binding and approved and approved.account_name==account.name and entities.revision_entity(db,approved.revision_id)==entities.revision_entity(db,binding.revision_id):result.append({'account_id':account.id,'name':account.name,'account_type':account.account_type})
        return {'policy_enabled':True,'approved_accounts':result}


def _blank(db,user):
    flag=db.scalar(select(AppMetadata).where(AppMetadata.key=='demo'))
    if flag and flag.value.get('enabled'):raise HTTPException(409,'演示库不能确认正式期初；请使用全新空业务库')
    # Pending opening cases contain only preparation evidence, never a stock/cash fact.
    if db.scalar(select(Case.id).where(Case.kind.not_in({'opening_import','business_entity'}))):raise HTTPException(409,'本店已有业务单据；空库期初不导入或推断未结旧单')
    policy=_entity_policy(db,user)
    if policy:
        permitted={x['account_id'] for x in account_options(db,user)['approved_accounts']}
        if any(a.id not in permitted for a in db.scalars(select(Account))):raise HTTPException(409,'期初只允许预配置的已批准本店实际账户；请先核清账户归属和启用状态')
    elif db.scalar(select(Account.id)):raise HTTPException(409,'未启用主体策略的旧方式期初要求账户为空，不按名称认领既有账户')
    for model in (Customer,Item,Vehicle,Sale,Repair,Policy,CashEntry,StockMove,Member):
        if db.scalar(select(model.id)):raise HTTPException(409,'本店已有客户、库存、资金或业务资料；不得覆盖或追加空库期初')
    if db.scalar(select(OpeningBatch.id).where(OpeningBatch.status=='confirmed')):raise HTTPException(409,'本店已经确认期初资料，不得重复启用')


def _typed(db,vehicle):
    model=db.scalar(select(VehicleModel).where(VehicleModel.code==vehicle.model_code))
    loc=db.scalar(select(StorageLocation).where(StorageLocation.code==vehicle.location_code))
    if not model or not loc:raise HTTPException(422,'车型或库位编码不存在于本店')
    model=require_active(db,'vehicle_models',model.id)
    from .vehicle_operations_service import typed_location
    loc,wh=typed_location(db,loc.id)
    return model,loc,wh


def _reference_snapshot(db,source):
    result=[]
    for row in source.vehicles:
        model,loc,wh=_typed(db,row)
        result.append({'model_id':model.id,'model_version':model.version,'location_id':loc.id,'location_version':loc.version,'warehouse_id':wh.id,'warehouse_version':wh.version})
    return result


def _owner_snapshot(db,source):
    return [{'username':row.owner_username,'user_id':db.scalar(select(User.id).where(User.username==row.owner_username,User.active.is_(True)))} for row in source.customers]


def _vin_free(db,vin):
    from .vehicle_procurement_service import _vin_state
    from .vehicle_transfer_service import current_custody
    from .vehicle_operations_service import assert_no_vehicle_operation
    assert_no_vehicle_operation(db,vin=vin)
    blocked,generation=_vin_state(db,vin)
    previous=db.info.get('store_scope');history=False
    # Only a boolean leaves the controlled global VIN check; no foreign records.
    try:
        db.info['store_scope']=tuple(db.scalars(select(Store.id)))
        history=bool(db.scalar(select(Vehicle.id).where(Vehicle.vin==vin)))
    finally:
        if previous is None:db.info.pop('store_scope',None)
        else:db.info['store_scope']=previous
    if blocked or history or current_custody(db,vin):
        raise HTTPException(409,'VIN已有库存、历史代次或业务占用；期初不能推断其可售状态')


def validate(db,user,text,check_blank=True):
    errors=[]
    try:
        if len(text.encode('utf-8'))>120000:raise ValueError('资料超过120KB，请拆分核对，单店仍只能一次确认')
        source=Source.model_validate(json.loads(text,object_pairs_hook=_reject_duplicate_json))
    except ValidationError as exc:
        return None,[_error(str(e['loc'][0]),e['loc'][1]+1 if len(e['loc'])>1 and isinstance(e['loc'][1],int) else 0,str(e['loc'][-1]),'字段缺失、格式或取值不符合模板：'+e['msg']) for e in exc.errors()]
    except (ValueError,TypeError) as exc:return None,[_error('source',0,'source_text','JSON资料无法解析：'+str(exc))]
    if source.opening_date>today() or source.opening_date.year<2000:errors.append(_error('source',0,'opening_date','期初基准日须在2000年至今天之间'))
    if not (source.customers or source.accounts or source.items or source.vehicles):errors.append(_error('source',0,'records','至少提供一类期初资料'))
    for kind,key in [('accounts','name'),('items','sku'),('vehicles','vin')]:
        seen=set()
        for index,row in enumerate(getattr(source,kind),1):
            value=getattr(row,key)
            if value in seen:errors.append(_error(kind,index,key,'同一资料内重复，须人工核对后重新预检'))
            seen.add(value)
    policy=_entity_policy(db,user);account_ids=set()
    for n,row in enumerate(source.accounts,1):
        if policy:
            if not row.account_id:errors.append(_error('accounts',n,'account_id','已启用主体策略：必须明确填写本店已批准的实际账户编号，不能按名称自动认领'))
            elif row.account_id in account_ids:errors.append(_error('accounts',n,'account_id','同一实际账户不能在期初资料内重复列示'))
            else:
                try:_account_context(db,user,source.model_copy(update={'accounts':[row]}))
                except HTTPException as exc:errors.append(_error('accounts',n,'account_id',exc.detail))
            account_ids.add(row.account_id)
        elif 'account_id' in row.model_fields_set:errors.append(_error('accounts',n,'account_id','未启用主体策略的旧方式期初不接收账户编号，只能在空库创建新账户'))
    # Source row number is the explicit local mapping. Phone never merges identities.
    seen=set()
    for index,row in enumerate(source.customers,1):
        owner=db.scalar(select(User).where(User.username==row.owner_username,User.active.is_(True)))
        if not owner or role_for_store(db,owner,single_store(db)) not in {'admin','manager','sales','service','reception','customer_service'}:
            errors.append(_error('customers',index,'owner_username','负责人不是本店启用的客户办理岗位'))
        pair=(row.name,row.phone)
        if pair in seen:errors.append(_error('customers',index,'phone','姓名与电话重复，须人工核对；系统不会自动合并'))
        seen.add(pair)
    from .transfer_service import authority as custody_authority
    with custody_authority(db,user,READ):
        for index,row in enumerate(source.vehicles,1):
            try:_typed(db,row);_vin_free(db,row.vin)
            except HTTPException as exc:errors.append(_error('vehicles',index,'vin/model_code/location_code',exc.detail))
    if check_blank:
        try:_blank(db,user)
        except HTTPException as exc:errors.append(_error('target',0,'empty_store',exc.detail))
    return source,errors


def totals(source):
    return {**_totals(source),'vehicle_count':len(source.vehicles),'vehicle_value_cents':sum(v.cost_cents for v in source.vehicles),
        'account_balance_cents':sum(a.opening_balance_cents for a in source.accounts)}


def inventory_observation(source):
    return {'vehicles':[{'vin':v.vin,'location_code':v.location_code} for v in source.vehicles],
        'items':[{'sku':i.sku,'quantity_milli':i.opening_quantity_milli} for i in source.items if i.opening_quantity_milli]}


def same_values(left,right):
    # bool and float must not compare equal to integer fen/thousandths.
    return json.dumps(left,sort_keys=True,separators=(',',':'))==json.dumps(right,sort_keys=True,separators=(',',':'))


def finance_observation(source):
    return {'totals':totals(source),'accounts':[{'name':a.name,'opening_balance_cents':a.opening_balance_cents} for a in source.accounts]}


def local_day(timestamp):
    return timestamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()


def needs(source):return bool(source.vehicles or any(i.opening_quantity_milli for i in source.items)),bool(source.accounts or source.vehicles or any(i.opening_quantity_milli for i in source.items))


def _load(db,case_id):
    sid=single_store(db)
    case=db.scalar(select(Case).where(Case.id==case_id,Case.store_id==sid).with_for_update())
    control=db.scalar(select(OpeningImport).where(OpeningImport.case_id==case_id,OpeningImport.store_id==sid).with_for_update())
    if not case or not control or case.kind!='opening_import' or case.flow_version!=2:raise HTTPException(404,'期初批次不存在或不属于当前门店')
    batch=db.scalar(select(OpeningBatch).where(OpeningBatch.id==control.batch_id,OpeningBatch.store_id==sid).with_for_update())
    if not batch:raise HTTPException(409,'期初资料绑定不完整')
    return case,control,batch


def _proofs(db,control):return {p.kind:p for p in db.scalars(select(OpeningAttestation).where(OpeningAttestation.import_id==control.id))}


def _task(db,user,case,key,role,title,avoid=(),preferred=None):
    task=db.scalar(select(Task).where(Task.case_id==case.id,Task.key==key))
    if task and task.status=='open':return
    people=[u for u in db.scalars(select(User).where(User.active.is_(True)).order_by(User.id)) if u.id not in avoid and role_for_store(db,u,single_store(db)) in {role,'admin'}]
    people.sort(key=lambda u:(u.id!=preferred,role_for_store(db,u,single_store(db))!=role,u.id))
    if not people:raise HTTPException(409,'请先配置不同经办人的本店'+{'manager':'主管','finance':'财务','inventory':'库管'}[role]+'岗位')
    flow.ensure_task(db,case,key,title,role,people[0].id,due=case.due_date,reopen=True)


def _sync(db,user,case,control,batch):
    source=Source.model_validate_json(batch.source_text);physical,financial=needs(source);proofs=_proofs(db,control)
    expected={}
    if control.status=='trial_passed':expected={'opening_approve':('manager','复核已试导入的期初资料',(batch.prepared_by,))}
    elif control.status=='approved':
        if physical and 'inventory' not in proofs:expected['opening_inventory']=('inventory','实际核对期初车辆与物资数量',(proofs['approve'].actor_id,))
        if financial and 'finance' not in proofs:expected['opening_finance']=('finance','核对账户期初余额与库存价值',tuple(p.actor_id for k,p in proofs.items() if k=='inventory'))
        if (not physical or 'inventory' in proofs) and (not financial or 'finance' in proofs):expected['opening_confirm']=('manager','核对三岗凭据并一次启用',())
    for task in db.scalars(select(Task).where(Task.case_id==case.id,Task.status=='open')):
        if task.key not in expected:flow.finish_task(db,case,task.key,user)
    for key,(role,title,avoid) in expected.items():_task(db,user,case,key,role,title,avoid,proofs['approve'].actor_id if key=='opening_confirm' else None)
    case.state='completed' if control.status=='confirmed' else 'cancelled' if control.status=='cancelled' else 'approval' if control.status in {'prepared','trial_passed'} else 'working'
    case.data={'batch_id':batch.id,'opening_status':control.status};case.updated_at=utcnow()
    if control.status=='confirmed':case.completed_date=today()


def serialize(db,user,case,control,batch):
    money=user.role in MONEY;source=Source.model_validate_json(batch.source_text);proofs=_proofs(db,control)
    available={'trial','cancel'} if control.status=='prepared' else {'trial','approve','cancel','reassign'} if control.status=='trial_passed' else {'cancel','reassign'} if control.status=='approved' else set()
    if control.status=='approved':
        for needed,kind in zip(needs(source),('inventory','finance')):
            if needed and kind not in proofs:available.add('verify_'+kind)
        if all(not needed or kind in proofs for needed,kind in zip(needs(source),('inventory','finance'))):available.add('confirm')
    result={'case_id':case.id,'number':case.number,'version':case.version,'batch_id':batch.id,'status':control.status,'status_label':STATUS[control.status],
        'source_digest':batch.source_digest,'source_reference':batch.source_reference,'opening_date':batch.opening_date.isoformat(),'prepared_by':batch.prepared_by,
        'needs_inventory':needs(source)[0],'needs_finance':needs(source)[1],'totals':{k:v for k,v in batch.totals.items() if money or 'cents' not in k},
        'proofs':[{'kind':p.kind,'actor_id':p.actor_id,'actor_name':db.scalar(select(User.display_name).where(User.id==p.actor_id)),'occurred_at':p.occurred_at.isoformat()+'Z','reason':p.reason if money or p.kind=='inventory' else '核验说明按岗位授权查看','evidence_id':p.evidence_id if money or p.kind!='finance' else None} for p in proofs.values()],
        'vehicles':[{'row':n,'vin':v.vin,'model_code':v.model_code,'location_code':v.location_code,'color':v.color,**({'cost_cents':v.cost_cents,'list_price_cents':v.list_price_cents,'source_reference':v.source_reference} if money else {})} for n,v in enumerate(source.vehicles,1)],
        'items':[{'row':n,'sku':v.sku,'name':v.name,'unit':v.unit,'quantity_milli':v.opening_quantity_milli,**({'value_cents':v.opening_value_cents} if money else {})} for n,v in enumerate(source.items,1)],
        'accounts':[a.model_dump() for a in source.accounts] if money else [],'customers':[c.model_dump() for c in source.customers] if user.role in MANAGE else [],
        'actions':[k for k,roles in ROLES.items() if user.role in roles and k in available],
        'own_file_ids':list(db.scalars(select(FileAsset.id).where(FileAsset.case_id==case.id,FileAsset.created_by==user.id,FileAsset.generated.is_(False)))),
        'tasks':[{'id':t.id,'key':t.key,'role':t.role,'assignee_id':t.assignee_id,'title':t.title,'due_date':t.due_date.isoformat()} for t in db.scalars(select(Task).where(Task.case_id==case.id,Task.status=='open'))]}
    return result


def detail(db,user,case_id):
    with authority(db,user):return serialize(db,user,*_load(db,case_id))


def preflight(db,user,key,text):
    with authority(db,user,MANAGE):
        def perform(sid):
            source,errors=validate(db,user,text)
            if errors:return {'valid':False,'errors':errors,'batch':None}
            batch=OpeningBatch(source_text=text,source_digest=hashlib.sha256(text.encode()).hexdigest(),source_reference=source.source_reference,opening_date=source.opening_date,totals=totals(source),prepared_by=user.id)
            case=Case(number='OPEN-'+uuid.uuid4().hex[:18].upper(),kind='opening_import',flow_version=2,state='approval',title='新店期初核验',owner_id=user.id,created_by=user.id,business_date=today(),due_date=today()+timedelta(days=7))
            db.add_all([batch,case]);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,case);control=OpeningImport(case_id=case.id,batch_id=batch.id);db.add(control);db.flush();_sync(db,user,case,control,batch)
            db.add(FlowEvent(case_id=case.id,actor_id=user.id,action='opening_preflight',label='期初原资料预检通过',after_state=case.state,detail={'digest':batch.source_digest,'references':_reference_snapshot(db,source),'owners':_owner_snapshot(db,source),'account_context':_account_context(db,user,source)}));db.flush()
            return {'valid':True,'errors':[],'batch':serialize(db,user,case,control,batch)}
        return _execute(db,user,key,'opening2-preflight',text,perform)


def _evidence(db,user,case,key,category='evidence'):
    file=flow.file_exists(db,case,key,category)
    # A staff member attests their own uploaded review, never someone else's actions.
    if file.created_by!=user.id:raise HTTPException(409,'请上传本人本次核验凭据，不得代替其他员工确认')
    return file


def _apply(db,user,case,control,batch,source,finance,inventory):
    physical_actor=db.scalar(select(User).where(User.id==inventory['actor_id']))
    configured=_account_context(db,user,source)
    # The shared v1 importer retains its creation-only contract. Policy mode
    # imports customers/materials through it and explicitly reuses approved IDs.
    _apply_opening(db,physical_actor,batch,source.model_copy(update={'accounts':[]}) if configured else source)
    if configured:
        from . import business_entity_service as entities
        with entities.authority(db,user):entities.control(db).version+=1;db.flush()
    for n,row in enumerate(source.accounts,1):
        account=db.scalar(select(Account).where(Account.id==row.account_id)) if configured else db.scalar(select(Account).where(Account.name==row.name))
        db.add(OpeningAccountEntry(import_id=control.id,row_number=n,account_id=account.id,account_name=account.name,amount_cents=row.opening_balance_cents,
            business_date=source.opening_date,source_reference=row.source_reference,evidence_id=finance['evidence_id'],actor_id=finance['actor_id']))
    from .transfer_service import authority as custody_authority
    from .vehicle_transfer_service import register_custody
    from .vehicle_operations_service import record_receipt_position
    with custody_authority(db,user,MANAGE):
        for n,row in enumerate(source.vehicles,1):
            _vin_free(db,row.vin);model,location,wh=_typed(db,row)
            vehicle=Vehicle(vin=row.vin,inventory_generation=1,doc_no=case.number+'-'+str(n),business_date=source.opening_date,approval_state='approved',created_by=physical_actor.id,
                brand=model.brand,model=model.name,color=row.color,supplier='',location=wh.name+' / '+location.name,purchase_cost_cents=row.cost_cents,list_price_cents=row.list_price_cents)
            db.add(vehicle);db.flush();custody=register_custody(db,physical_actor,vehicle)
            db.add(OpeningVehicleEntry(import_id=control.id,row_number=n,vehicle_id=vehicle.id,identity_id=custody.identity_id,model_id=model.id,location_id=location.id,vin=row.vin,
                value_cents=row.cost_cents,business_date=source.opening_date,source_reference=row.source_reference,evidence_id=inventory['evidence_id'],actor_id=physical_actor.id))
            record_receipt_position(db,physical_actor,case,vehicle,location.id,inventory['evidence_id'],'opening_receive')
        db.flush()
    return {'customers':[db.scalar(select(Customer.id).where(Customer.name==r.name,Customer.phone==r.phone)) for r in source.customers],
        'items':[db.scalar(select(Item.id).where(Item.sku==r.sku)) for r in source.items]}


def action(db,user,case_id,key,version,digest,action_name,values):
    if action_name not in ROLES:raise HTTPException(404,'期初动作不存在')
    with authority(db,user,ROLES[action_name]):
        def perform(sid):
            case,control,batch=_load(db,case_id)
            if case.version!=version:raise HTTPException(409,'期初批次版本已变化，请刷新核对')
            if digest!=batch.source_digest or hashlib.sha256(batch.source_text.encode()).hexdigest()!=digest:raise HTTPException(409,'原资料摘要不一致，不能继续核验')
            if control.status in {'confirmed','cancelled'}:raise HTTPException(409,'期初批次已结束，不能再次办理')
            proofs=_proofs(db,control);source=Source.model_validate_json(batch.source_text);before=case.state;created_objects=None
            from .transfer_service import assert_task
            task_key={'approve':'opening_approve','verify_inventory':'opening_inventory','verify_finance':'opening_finance','confirm':'opening_confirm'}.get(action_name)
            if task_key:assert_task(db,user,case,task_key)
            if action_name=='cancel':control.status='cancelled'
            elif action_name=='reassign':
                task=db.scalar(select(Task).where(Task.id==values['task_id'],Task.case_id==case.id,Task.status=='open'))
                assignee=db.scalar(select(User).where(User.id==values['assignee_id'],User.active.is_(True)))
                if not task or not assignee or role_for_store(db,assignee,sid) not in {task.role,'admin'}:raise HTTPException(422,'请选择本店当前待办和对应启用岗位')
                if task.key=='opening_approve' and assignee.id==batch.prepared_by or task.key=='opening_inventory' and assignee.id==proofs['approve'].actor_id or task.key=='opening_finance' and 'inventory' in proofs and assignee.id==proofs['inventory'].actor_id:
                    raise HTTPException(409,'准备、审批及分岗核验须由不同经办人承担')
                task.assignee_id=assignee.id
            else:
                checked,errors=validate(db,user,batch.source_text)
                if errors:raise HTTPException(409,{'message':'期初条件已变化，请取消并重新预检','errors':errors})
                if totals(checked)!=batch.totals:raise HTTPException(409,'期初汇总与冻结资料不一致')
                prepared=db.scalar(select(FlowEvent).where(FlowEvent.case_id==case.id,FlowEvent.action=='opening_preflight'))
                if not prepared or prepared.detail.get('references')!=_reference_snapshot(db,checked):raise HTTPException(409,'车型、仓库或库位已变更，请取消本批后重新预检和核验')
                if prepared.detail.get('owners')!=_owner_snapshot(db,checked):raise HTTPException(409,'客户负责人账号映射已改变，请重新预检确认')
                if prepared.detail.get('account_context')!=_account_context(db,user,checked):raise HTTPException(409,'期初账户版本、批准渠道或本店主体绑定已变化，请取消并重新预检')
                if action_name=='trial':
                    if control.status not in {'prepared','trial_passed'}:raise HTTPException(409,'主管批准后不能重新试导入')
                    _evidence(db,user,case,values['evidence_id'])
                    trial={'evidence_id':values['evidence_id'],'actor_id':user.id}
                    with db.begin_nested() as savepoint:
                        _apply(db,user,case,control,batch,source,trial,trial);db.flush();savepoint.rollback()
                    control.status='trial_passed';batch.status='trial_passed'
                elif action_name=='approve':
                    if control.status!='trial_passed':raise HTTPException(409,'须先完成无错误的回滚试导入')
                    if user.id==batch.prepared_by:raise HTTPException(409,'准备人与主管审批人必须不同')
                    _evidence(db,user,case,values['evidence_id'])
                    db.add(OpeningAttestation(import_id=control.id,kind='approve',source_digest=digest,actor_id=user.id,evidence_id=values['evidence_id'],reason=values['reason'],observed={'totals':batch.totals}));control.status='approved'
                elif action_name in {'verify_inventory','verify_finance'}:
                    if control.status!='approved':raise HTTPException(409,'须先由另一位主管批准期初资料')
                    kind='inventory' if action_name=='verify_inventory' else 'finance'
                    if kind in proofs:raise HTTPException(409,'本岗已经核验；有差异请取消批次重新预检')
                    if user.id==proofs['approve'].actor_id or any(p.actor_id==user.id for k,p in proofs.items() if k in {'inventory','finance'}):raise HTTPException(409,'库管、财务核验与主管实物审批不能由同一人代办')
                    if not needs(source)[0 if kind=='inventory' else 1]:raise HTTPException(409,'本批次无需此类核验')
                    expected=inventory_observation(source) if kind=='inventory' else finance_observation(source)
                    if not same_values(values['observed'],expected):raise HTTPException(409,'本次核对数量、VIN、库位或金额与冻结原资料不一致，不能确认')
                    _evidence(db,user,case,values['evidence_id'],'evidence' if kind=='inventory' else 'receipt')
                    db.add(OpeningAttestation(import_id=control.id,kind=kind,source_digest=digest,actor_id=user.id,evidence_id=values['evidence_id'],reason=values['reason'],observed=expected))
                elif action_name=='confirm':
                    if control.status!='approved' or any(needed and kind not in proofs for needed,kind in zip(needs(source),('inventory','finance'))):raise HTTPException(409,'主管批准、实物核验和财务核验尚未齐全')
                    if not same_values(values['expected_totals'],batch.totals):raise HTTPException(409,'确认汇总不一致，请逐项核对原资料')
                    if any(local_day(p.occurred_at)!=today() for k,p in proofs.items() if k in {'inventory','finance'}):raise HTTPException(409,'实物或财务核验已跨日，请取消并重新核验新批次')
                    defaults={'actor_id':user.id,'evidence_id':proofs['approve'].evidence_id}
                    finance={k:getattr(proofs['finance'],k) for k in defaults} if 'finance' in proofs else defaults
                    inventory={k:getattr(proofs['inventory'],k) for k in defaults} if 'inventory' in proofs else defaults
                    created_objects=_apply(db,user,case,control,batch,source,finance,inventory)
                    batch.status='confirmed';batch.confirmed_store_key=sid;batch.confirmed_by=user.id;batch.confirmed_at=utcnow();control.status='confirmed'
            db.flush();_sync(db,user,case,control,batch)
            db.add(FlowEvent(case_id=case.id,actor_id=user.id,action='opening_'+action_name,label=LABELS[action_name],before_state=before,after_state=case.state,
                detail={'digest':digest,'reason':values.get('reason','') if action_name not in {'verify_finance','approve'} else '本岗核验说明保存在受限期初凭据',**({'objects':created_objects} if created_objects else {})}));db.flush()
            return serialize(db,user,case,control,batch)
        return _execute(db,user,key,'opening2-'+action_name,[case_id,version,digest,values],perform)


def account_has_opening(db,account_id):return bool(db.scalar(select(OpeningAccountEntry.id).where(OpeningAccountEntry.account_id==account_id)))


def assert_cash_date(db,account_id,actual_date):
    entry=db.scalar(select(OpeningAccountEntry).where(OpeningAccountEntry.account_id==account_id))
    if entry and actual_date<entry.business_date:raise HTTPException(409,'实际流水日期不能早于该账户期初基准日')


def account_balances(db,user):
    with authority(db,user,MONEY):
        result=[]
        for entry in db.scalars(select(OpeningAccountEntry).order_by(OpeningAccountEntry.id)):
            account=db.scalar(select(Account).where(Account.id==entry.account_id));cash=list(db.scalars(select(CashEntry).where(CashEntry.account==entry.account_name,CashEntry.approval_state=='approved')))
            from .cash_basis import effective_cash
            cash=effective_cash(db,cash,6)
            incoming=sum(c.amount_cents for c in cash if c.direction=='in' and c.business_date>=entry.business_date)
            outgoing=sum(c.amount_cents for c in cash if c.direction=='out' and c.business_date>=entry.business_date)
            result.append({'account_id':entry.account_id,'account_name':entry.account_name,'active':account.active,'opening_date':entry.business_date.isoformat(),'opening_cents':entry.amount_cents,
                'in_cents':incoming,'out_cents':outgoing,'balance_cents':entry.amount_cents+incoming-outgoing,'pre_opening_cash_count':sum(c.business_date<entry.business_date for c in cash)})
        return {'items':result,'basis':'期初基准日日初余额，加该日及以后已确认实际流水；期初余额不计本期收入或现金收款。'}
