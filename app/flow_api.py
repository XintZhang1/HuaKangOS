from datetime import date
from decimal import Decimal
import csv
import io
import uuid
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, or_
from .db import get_db,today,utcnow
from .security import get_user,require_full,ROLES
from .models import User,Store,Vehicle,Sale,AuditLog
from .tenancy import single_store,accessible_stores
from .services import plain,audit
from .flow_models import Case,Task,Customer,FlowEvent,PaymentLink,Account,Item,StockMove,Member,MemberEntry,Reference,DocTemplate,FileAsset,VehicleHold
from .flow_specs import SPECS,STATES,MODULES,TERMINAL,parse_fields,f,flow_spec,CURRENT_FLOW_VERSION
from . import flow_engine as eng
from .flow_documents import file_info,can_file,upload_file,generate_document,UPLOAD_LABELS,DOC_TITLES,ensure_templates
from .file_security import require_usable,is_usable

router=APIRouter(prefix='/api/flow')
class Strict(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class CreateInput(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    kind:str
    values:dict=Field(default_factory=dict)
class ActionInput(Strict):
    request_id:str=Field(min_length=16,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    version:int=Field(ge=1)
    values:dict=Field(default_factory=dict)
class MasterInput(Strict):
    values:dict
    version:int|None=None
class DocumentInput(Strict):kind:str
class AssignInput(Strict):
    version:int=Field(ge=1)
    assignee_id:int=Field(gt=0)
    reason:str=Field(min_length=2,max_length=500)


def describe_case(db,user,row):
    info={key:getattr(row,key) for key in ['id','number','kind','state','title','owner_id','customer_id','parent_id','vehicle_id','version','flow_version','store_id']}
    info.update(kind_label=flow_spec(row.kind,row.flow_version)['label'],state_label=STATES.get(row.state,row.state),data=eng.safe_data(row.data,user,row),
        business_date=row.business_date.isoformat(),due_date=row.due_date.isoformat() if row.due_date else None,
        completed_date=row.completed_date.isoformat() if row.completed_date else None,updated_at=row.updated_at.isoformat()+'Z')
    owner=db.get(User,row.owner_id);info['owner_name']=owner.display_name if owner else '待配置'
    store=db.get(Store,row.store_id);info['store_name']=store.name if store else ''
    if eng.money_visible(user,row):info.update(amount_cents=row.amount_cents,paid_cents=eng.paid_amount(db,row))
    if user.role in eng.MANAGEMENT:info['cost_cents']=row.cost_cents
    return info


def task_info(db,user,t,row):
    actions=eng.available_actions(db,user,row)
    relevant=[x for x in actions if next((a.task for a in flow_spec(row.kind,row.flow_version)['actions'] if a.key==x['key']),None)==t.key]
    reason=''
    if t.status=='open' and relevant and all(not a['enabled'] for a in relevant):reason=relevant[0]['reason']
    owner=db.get(User,t.assignee_id)
    return {'id':t.id,'case_id':t.case_id,'key':t.key,'title':t.title,'role':t.role,'role_label':ROLES.get(t.role,t.role),
        'assignee_id':t.assignee_id,'assignee_name':owner.display_name if owner else '待配置','status':t.status,'due_date':t.due_date.isoformat(),
        'overdue':t.status=='open' and t.due_date<today(),'blocked':bool(reason),'block_reason':reason,'version':t.version,
        'case_number':row.number,'case_title':row.title,'kind_label':SPECS[row.kind]['label'],'state_label':STATES[row.state],
        'updated_at':t.updated_at.isoformat()+'Z'}


@router.get('/catalog')
def catalog(db=Depends(get_db),user=Depends(get_user)):
    allowed=set(SPECS) if user.role in eng.MANAGEMENT else eng.READ_KINDS.get(user.role,set())
    return {'flow_version':CURRENT_FLOW_VERSION,'modules':MODULES,'states':STATES,'kinds':{k:{'label':s['label'],'module':s['module'],'fields':s['fields'],'can_create':user.role in s['create_roles']} for k,s in SPECS.items() if k in allowed},
        'today':today().isoformat(),'master_types':{k:{'label':v['label'],'fields':v['fields'],'can_write':user.role in v['write']} for k,v in MASTERS.items() if user.role in v['read']},
        'upload_categories':UPLOAD_LABELS,'document_types':DOC_TITLES,
        'capabilities':{'rework_extensions':True,'repair_packages':True,'member_pricing':True,'member_fee_corrections':True}}


@router.get('/tasks')
def tasks(scope:str='mine',status:str='open',page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    if status not in {'open','done','cancelled'}:raise HTTPException(422,'任务状态无效')
    q=select(Task).where(Task.status==status,Task.case_id.in_(eng.case_query(user).with_only_columns(Case.id)))
    if scope=='mine':q=q.where(Task.assignee_id==user.id)
    elif scope=='all':
        if user.role not in eng.MANAGEMENT:raise HTTPException(403,'当前岗位仅查看自己的任务')
    else:raise HTTPException(422,'任务范围无效')
    total=db.scalar(select(func.count()).select_from(q.subquery()))
    allrows=list(db.scalars(q.order_by(Task.due_date,Task.id).offset((page-1)*page_size).limit(page_size)))
    return {'items':[task_info(db,user,t,eng.scoped_get(db,Case,t.case_id)) for t in allrows],'total':total,'page':page,'page_size':page_size,
        'overdue_count':db.scalar(select(func.count()).select_from(q.where(Task.due_date<today()).subquery())) if status=='open' else 0}


@router.post('/tasks/{task_id}/assign')
def assign_task(task_id:int,body:AssignInput,db=Depends(get_db),user=Depends(get_user)):
    if user.role not in {'admin','manager'}:raise HTTPException(403,'任务转交需要主管处理')
    single_store(db);task=eng.scoped_get(db,Task,task_id)
    if not task:raise HTTPException(404,'任务不存在')
    if task.version!=body.version or task.status!='open':raise HTTPException(409,'任务已变化，请刷新后重试')
    target=eng.assignable(db,body.assignee_id,task.store_id,{task.role});old=task.assignee_id;task.assignee_id=target.id
    row=eng.get_case(db,user,task.case_id)
    if task.key in {'contact','follow'}:
        old_owner=row.owner_id;row.owner_id=target.id
        customer=eng.scoped_get(db,Customer,row.customer_id) if row.customer_id else None
        if customer and customer.owner_id==old_owner:customer.owner_id=target.id
    eng.log_event(db,user,row,'reassign','转交任务',row.state,{'task_id':task.id,'from':old,'to':target.id,'reason':body.reason})
    db.commit();return task_info(db,user,task,row)


@router.get('/cases')
def list_cases(kind:str='',module:str='',q:str=Query('',max_length=100),state:str='',date_from:date|None=None,date_to:date|None=None,
               page:int=Query(1,ge=1),page_size:int=Query(30,ge=1,le=100),db=Depends(get_db),user=Depends(get_user)):
    stmt=eng.case_query(user)
    if kind:
        if kind not in SPECS:raise HTTPException(422,'业务类别无效')
        stmt=stmt.where(Case.kind==kind)
    if module:stmt=stmt.where(Case.kind.in_([k for k,v in SPECS.items() if v['module']==module]))
    if q:stmt=stmt.where(or_(Case.number.contains(q),Case.title.contains(q)))
    if state=='open':stmt=stmt.where(Case.state.notin_(TERMINAL))
    elif state:stmt=stmt.where(Case.state==state)
    if date_from:stmt=stmt.where(Case.business_date>=date_from)
    if date_to:stmt=stmt.where(Case.business_date<=date_to)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=list(db.scalars(stmt.order_by(Case.updated_at.desc(),Case.id.desc()).offset((page-1)*page_size).limit(page_size)))
    return {'items':[describe_case(db,user,r) for r in rows],'total':total,'page':page,'page_size':page_size}


@router.post('/cases',status_code=201)
def create_case(body:CreateInput,db=Depends(get_db),user=Depends(get_user)):
    single_store(db);digest=eng.request_digest('create',body.model_dump(exclude={'request_id'}))
    old=eng.prior_request(db,user,body.request_id,digest)
    if old:return describe_case(db,user,old)
    row=eng.new_case(db,user,body.kind,body.values);eng.save_receipt(db,user,body.request_id,digest,row)
    db.commit();return describe_case(db,user,row)


@router.get('/cases/{case_id}')
def case_detail(case_id:int,db=Depends(get_db),user=Depends(get_user)):
    row=eng.get_case(db,user,case_id);info=describe_case(db,user,row)
    info['actions']=eng.available_actions(db,user,row)
    info['tasks']=[task_info(db,user,t,row) for t in db.scalars(select(Task).where(Task.case_id==row.id).order_by(Task.id))]
    info['children']=[describe_case(db,user,c) for c in eng.children(db,row) if eng.can_read(db,user,c)]
    from .aftercare_models import AftercareSource
    related=select(Case).join(AftercareSource,AftercareSource.case_id==Case.id).where(AftercareSource.source_case_id==row.id).order_by(Case.id.desc())
    info['aftercare_links']=[{'id':c.id,'number':c.number,'state':c.state,'state_label':STATES.get(c.state,c.state)} for c in db.scalars(related) if eng.can_read(db,user,c)]
    info['files']=[file_info(x,db) for x in db.scalars(select(FileAsset).where(FileAsset.case_id==row.id).order_by(FileAsset.id.desc())) if can_file(user,row,x)]
    customer=eng.scoped_get(db,Customer,row.customer_id) if row.customer_id else None
    info['customer']={'id':customer.id,'name':customer.name,'phone':customer.phone,'contact_allowed':customer.contact_allowed} if customer else None
    events=list(db.scalars(select(FlowEvent).where(FlowEvent.case_id==row.id).order_by(FlowEvent.id.desc()).limit(100)))
    info['events']=[{'id':e.id,'label':e.label,'actor_name':db.get(User,e.actor_id).display_name,'occurred_at':e.occurred_at.isoformat()+'Z',
        'from':STATES.get(e.before_state,''),'to':STATES.get(e.after_state,''),'detail':eng.safe_data(e.detail,user,row)} for e in events]
    info['event_total']=db.scalar(select(func.count()).select_from(FlowEvent).where(FlowEvent.case_id==row.id))
    if eng.money_visible(user,row):
        info['payments']=[plain(p) for p in db.scalars(select(PaymentLink).where(PaymentLink.case_id==row.id).order_by(PaymentLink.id))]
        if row.kind in {'insurance','addon','agency'} and row.flow_version==3 and user.role not in eng.MANAGEMENT:
            info['payments']=[{k:p[k] for k in ('id','direction','amount_cents','business_date')} for p in info['payments']]
    return info


@router.post('/cases/{case_id}/actions/{action}')
def act(case_id:int,action:str,body:ActionInput,db=Depends(get_db),user=Depends(get_user)):
    single_store(db);digest=eng.request_digest(f'{case_id}:{action}',body.model_dump(exclude={'request_id'}))
    old=eng.prior_request(db,user,body.request_id,digest)
    if old:return describe_case(db,user,old)
    row=eng.get_case(db,user,case_id)
    eng.process_action(db,user,row,action,body.values,body.version);eng.save_receipt(db,user,body.request_id,digest,row)
    db.commit();return describe_case(db,user,row)


@router.post('/cases/{case_id}/documents')
def generate(case_id:int,body:DocumentInput,db=Depends(get_db),user=Depends(get_user)):
    single_store(db);row=eng.get_case(db,user,case_id)
    if user.role=='auditor':raise HTTPException(403,'审计账号仅能查看已保存文件')
    file=generate_document(db,user,row,body.kind)
    eng.log_event(db,user,row,'document','生成'+DOC_TITLES[body.kind],row.state,{'file_id':file.id,'sha256':file.sha256})
    db.commit();return file_info(file,db)


@router.post('/cases/{case_id}/files')
async def upload(case_id:int,file:UploadFile=File(...),category:str=Form('evidence'),source_file_id:int|None=Form(None),
                 db=Depends(get_db),user=Depends(get_user)):
    single_store(db);row=eng.get_case(db,user,case_id)
    from .flow_documents import MAX_BYTES
    content=await file.read(MAX_BYTES+1);await file.close()
    asset=upload_file(db,user,row,file.filename or '',content,category,source_file_id)
    db.commit();return file_info(asset,db)


@router.get('/files/{file_id}')
def download(file_id:int,db=Depends(get_db),user=Depends(get_user)):
    asset=eng.scoped_get(db,FileAsset,file_id)
    if not asset:raise HTTPException(404,'文件不存在或不可访问')
    row=eng.get_case(db,user,asset.case_id)
    if not can_file(user,row,asset):raise HTTPException(403,'没有此类文件的查看权限')
    require_usable(db,asset)
    from .private_files import read_content
    content=read_content(db,asset)
    audit(db,user.id,'download','flow',row.id,reason='下载文件 '+str(asset.id));db.commit()
    return Response(content=content,media_type=asset.media_type,headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(asset.name),
        'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Content-Security-Policy':"sandbox; default-src 'none'"})


@router.get('/lookup/{kind}')
def lookup(kind:str,q:str=Query('',max_length=100),case_id:int|None=None,db=Depends(get_db),user=Depends(get_user)):
    row=eng.get_case(db,user,case_id) if case_id else None
    results=[]
    if kind=='employee':
        store=single_store(db);ids={u.id:u for role in ROLES for u in eng.eligible_users(db,role,store)}
        results=[{'id':u.id,'label':u.display_name+' · '+ROLES[u.role]} for u in ids.values()]
    elif kind=='vehicle':
        if user.role not in {'admin','manager','inventory','sales'}:raise HTTPException(403,'没有查看车辆的权限')
        stmt=select(Vehicle).where(Vehicle.approval_state=='approved',Vehicle.id.notin_(select(Sale.active_vehicle_id).where(Sale.active_vehicle_id.is_not(None))),Vehicle.id.notin_(select(VehicleHold.vehicle_id)))
        if q:stmt=stmt.where(or_(Vehicle.vin.contains(q),Vehicle.model.contains(q)))
        from .transfer_service import authority
        from .vehicle_transfer_models import VehicleCustody
        from .vehicle_procurement_models import VehiclePurchaseReceipt,VehiclePurchaseReturn
        pending_returns=select(VehiclePurchaseReceipt.vehicle_id).join(VehiclePurchaseReturn,VehiclePurchaseReturn.shipment_id==VehiclePurchaseReceipt.shipment_id).where(VehiclePurchaseReturn.status.in_(['requested','approved']))
        stmt=stmt.where(Vehicle.id.notin_(pending_returns))
        from .vehicle_operations_service import unavailable_vehicle_ids
        stmt=stmt.where(Vehicle.id.notin_(unavailable_vehicle_ids(db)))
        with authority(db,user,{'admin','manager','inventory','sales'}):
            stmt=stmt.where(Vehicle.id.notin_(select(VehicleCustody.current_vehicle_id).where(VehicleCustody.pending_transfer_id.is_not(None),VehicleCustody.current_vehicle_id.is_not(None))))
            results=[{'id':v.id,'label':v.model+' · '+v.vin} for v in db.scalars(stmt.order_by(Vehicle.id.desc()).limit(101))]
    elif kind in {'file','signed_file','handover_file'}:
        if not row:raise HTTPException(422,'请先选择业务单据')
        stmt=select(FileAsset).where(FileAsset.case_id==row.id,FileAsset.generated.is_(False))
        if kind=='signed_file':stmt=stmt.where(FileAsset.category=='signed_contract')
        if kind=='handover_file':stmt=stmt.where(FileAsset.category=='signed_handover')
        results=[{'id':x.id,'label':x.name+' · '+UPLOAD_LABELS.get(x.category,'凭据')} for x in db.scalars(stmt.order_by(FileAsset.id.desc())) if can_file(user,row,x) and is_usable(db,x)]
    elif kind=='payment':
        if user.role not in {'admin','finance','manager'} or not row:raise HTTPException(403,'没有查看原收款的权限')
        for p in db.scalars(select(PaymentLink).where(PaymentLink.case_id==row.id,PaymentLink.direction=='in')):
            returned=db.scalar(select(func.coalesce(func.sum(PaymentLink.amount_cents),0)).where(PaymentLink.original_id==p.id))
            if returned<p.amount_cents:results.append({'id':p.id,'label':p.reference+' · 可退 '+format(Decimal(p.amount_cents-returned)/100,'.2f')+' 元'})
    elif kind=='stock_issue':
        if not row:raise HTTPException(422,'请先选择维修业务')
        childids=select(Case.id).where(Case.parent_id==row.id)
        results=[{'id':m.id,'label':eng.scoped_get(db,Item,m.item_id).name+' · 已领 '+str(-m.quantity_milli/1000)} for m in db.scalars(select(StockMove).where(StockMove.case_id.in_(childids),StockMove.purpose=='issue'))]
    elif kind=='billable_case':
        require_full(user)
        stmt=eng.case_query(user).where(Case.kind.in_(['order','repair','agency','addon']),Case.state.notin_(['cancelled','rejected']))
        if q:stmt=stmt.where(or_(Case.title.contains(q),Case.number.contains(q)))
        results=[{'id':c.id,'label':c.number+' · '+c.title} for c in db.scalars(stmt.limit(101))]
    elif kind in {'account','item','member','customer'}:
        master={'account':'accounts','item':'items','member':'members','customer':'customers'}[kind]
        config=MASTERS[master]
        if user.role not in config['read']:raise HTTPException(403,'没有查看此资料的权限')
        model=config['model'];stmt=select(model)
        if hasattr(model,'active'):stmt=stmt.where(model.active.is_(True))
        if q:
            field=model.number if kind=='member' else model.name
            stmt=stmt.where(field.contains(q))
        if kind=='customer' and user.role in {'sales','reception'}:stmt=stmt.where(Customer.owner_id==user.id)
        for obj in db.scalars(stmt.order_by(model.id.desc()).limit(101)):
            label=obj.name if hasattr(obj,'name') else obj.number
            if kind=='item':
                from .inventory_availability import available_quantity
                label+=f' · 可用 {available_quantity(db,obj)/1000:g} {obj.unit}'
            if kind=='member':label+=' · '+eng.scoped_get(db,Customer,obj.customer_id).name
            results.append({'id':obj.id,'label':label})
    else:raise HTTPException(404,'查询类别不存在')
    if q and kind in {'employee','file','signed_file','handover_file','stock_issue','payment'}:results=[x for x in results if q in x['label']]
    return {'items':results[:100],'has_more':len(results)>100}


ALL_ROLES=set(ROLES)
MASTERS={
'customers':dict(label='客户档案',model=Customer,read=ALL_ROLES-{'technician','inventory'},write={'admin','manager','sales','reception','service','customer_service'},
 fields=[f('name','客户姓名'),f('phone','联系电话',required=False),f('contact_allowed','允许后续联系','bool',False),f('note','备注','textarea',False),f('confirm_new_customer','已核对另建独立档案','bool',False)]),
'accounts':dict(label='收付款账户',model=Account,read={'admin','manager','finance','auditor'},write={'admin','manager'},
 fields=[f('name','账户名称'),f('account_type','账户类别','select',options=['bank','cash']),f('active','启用','bool',False)]),
'items':dict(label='物资目录',model=Item,read={'admin','manager','inventory','technician','service','finance','auditor'},write={'admin','manager','inventory'},
 fields=[f('sku','物资编码'),f('name','物资名称'),f('unit','计量单位'),f('reorder','补货提醒数量','quantity_zero'),f('active','启用','bool',False)]),
'members':dict(label='会员档案',model=Member,read={'admin','manager','service','customer_service','finance','auditor'},write={'admin','manager','service','customer_service'},
 fields=[f('customer_id','客户','customer'),f('active','启用','bool',False)]),
'references':dict(label='基础资料',model=Reference,read=ALL_ROLES,write={'admin','manager'},
 fields=[f('category','资料类别','select',options=['供应商','保险公司','厂家','品牌车型','车间班组','作业项目','仓库库位','代办项目','会员级别','公共字典','维修字典','整车字典','物资字典','财务字典','客户字典','会员字典']),f('name','名称'),f('detail','说明','textarea',False),f('active','启用','bool',False)]),
 'templates':dict(label='单据模板',model=DocTemplate,read={'admin','manager'},write={'admin','manager'},
 fields=[f('title','文档标题'),f('clauses','条款与确认事项','textarea'),f('approved','条款已经公司确认，启用此模板','bool',False)])}


def master_info(db,user,kind,row):
    data=plain(row)
    if kind=='items':
        from .master_models import ItemProfile, MaterialBrand
        brand=db.execute(select(MaterialBrand.id,MaterialBrand.name,MaterialBrand.code).join(ItemProfile,ItemProfile.brand_id==MaterialBrand.id).where(ItemProfile.item_id==row.id,ItemProfile.store_id==row.store_id,MaterialBrand.store_id==row.store_id)).first()
        data['brand_id']=brand.id if brand else None
        data['brand_name']=brand.name if brand else ''
        data['brand_code']=brand.code if brand else ''
        from .inventory_availability import reserved_quantity,available_quantity
        data['reserved_quantity']=format(Decimal(reserved_quantity(db,row.id))/1000,'f')
        data['available_quantity']=format(Decimal(available_quantity(db,row))/1000,'f')
        data['quantity']=format(Decimal(row.quantity_milli)/1000,'f');data['reorder']=format(Decimal(row.reorder_milli)/1000,'f')
        if user.role not in {'admin','manager','finance','auditor'}:
            data.pop('unit_cost_cents',None);data.pop('inventory_value_cents',None)
    if kind=='members':
        c=eng.scoped_get(db,Customer,row.customer_id);data['customer_name']=c.name if c else '';data['available_cents']=eng.member_available(db,row)
    return data


@router.get('/master/{kind}')
def master_list(kind:str,q:str=Query('',max_length=100),page:int=Query(1,ge=1),db=Depends(get_db),user=Depends(get_user)):
    config=MASTERS.get(kind)
    if not config or user.role not in config['read']:raise HTTPException(403,'没有查看此资料的权限')
    if kind=='templates' and db.info.get('write_store'):ensure_templates(db);db.commit()
    model=config['model'];stmt=select(model)
    if kind=='customers' and user.role in {'sales','reception'}:stmt=stmt.where(Customer.owner_id==user.id)
    if q:
        columns=[getattr(model,k) for k in ('name','phone','sku','number','title') if hasattr(model,k)]
        stmt=stmt.where(or_(*[c.contains(q) for c in columns]))
    total=db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=list(db.scalars(stmt.order_by(model.id.desc()).offset((page-1)*30).limit(30)))
    return {'items':[master_info(db,user,kind,r) for r in rows],'total':total,'page':page,'page_size':30}


@router.post('/master/{kind}',status_code=201)
def add_master(kind:str,body:MasterInput,db=Depends(get_db),user=Depends(get_user)):
    single_store(db);config=MASTERS.get(kind)
    if not config or user.role not in config['write'] or kind=='templates':raise HTTPException(403,'不能新增此资料')
    v=parse_fields(config['fields'],body.values)
    if kind=='customers':
        from .customer_choice import create_master_customer
        row=create_master_customer(db,user,v)
    else:
        if kind=='items':v['reorder_milli']=v.pop('reorder')
        if kind=='members':
            c=eng.scoped_get(db,Customer,v['customer_id'])
            if not c:raise HTTPException(422,'客户不存在')
            v['number']='HY-'+uuid.uuid4().hex[:12].upper()
        row=config['model'](**v);db.add(row);db.flush()
    audit(db,user.id,'master_create','flow_master',row.id,reason=config['label'])
    db.commit();return master_info(db,user,kind,row)


@router.put('/master/{kind}/{record_id}')
def edit_master(kind:str,record_id:int,body:MasterInput,db=Depends(get_db),user=Depends(get_user)):
    single_store(db);config=MASTERS.get(kind)
    if not config or user.role not in config['write']:raise HTTPException(403,'没有修改此资料的权限')
    row=eng.scoped_get(db,config['model'],record_id)
    if not row:raise HTTPException(404,'资料不存在')
    if body.version!=row.version:raise HTTPException(409,'资料已更新，请刷新后重试')
    if kind=='customers' and user.role in {'sales','reception'} and row.owner_id!=user.id:raise HTTPException(403,'只能修改自己负责的客户')
    v=parse_fields(config['fields'],body.values)
    if kind=='references':
        from .dictionary_api import DICTIONARIES
        categories={r['category'] for r in DICTIONARIES.values()}
        if row.category in categories and v['category'] != row.category:
            raise HTTPException(409,'领域字典不能改换类别；请停用原条目并在正确类别新建')
    if kind=='customers' and v['contact_allowed'] and not row.contact_allowed and user.role not in {'admin','manager'}:raise HTTPException(403,'重新启用联系需要主管核对客户意愿')
    if kind=='customers':v.pop('confirm_new_customer',None)
    if kind=='items':
        v['reorder_milli']=v.pop('reorder')
        if v['unit']!=row.unit:
            from .procurement_models import PurchaseLine
            from .repair_models import RepairLine
            from .retail_models import RetailLine
            from .master_models import OpeningStockEntry
            if (db.scalar(select(StockMove.id).where(StockMove.item_id==row.id).limit(1)) or
                db.scalar(select(PurchaseLine.id).where(PurchaseLine.item_id==row.id).limit(1)) or
                db.scalar(select(RepairLine.id).where(RepairLine.item_id==row.id).limit(1)) or
                db.scalar(select(RetailLine.id).where(RetailLine.item_id==row.id).limit(1)) or
                db.scalar(select(OpeningStockEntry.id).where(OpeningStockEntry.item_id==row.id).limit(1))):
                raise HTTPException(409,'已有库存记录、采购或维修约定，不能直接改变计量单位；请另建物资')
    if kind=='members' and v['customer_id']!=row.customer_id:raise HTTPException(409,'会员归属客户不可直接修改')
    if kind=='accounts' and (v['name']!=row.name or v['account_type']!=row.account_type):
        from .procurement_models import PurchasePayment
        from .vehicle_procurement_models import VehiclePurchasePayment
        # All unique cash records store the original account name. Never rewrite it.
        from .models import CashEntry
        linked=db.scalar(select(PaymentLink.id).where(PaymentLink.account_id==row.id).limit(1)) or db.scalar(select(PurchasePayment.id).where(PurchasePayment.account_id==row.id).limit(1)) or db.scalar(select(VehiclePurchasePayment.id).where(VehiclePurchasePayment.account_id==row.id).limit(1)) or db.scalar(select(CashEntry.id).where(CashEntry.account==row.name).limit(1))
        if linked:raise HTTPException(409,'已有收付款记录，不能直接修改账户名称或银行/现金类别；需要时另建账户')
    before=plain(row)
    for k,value in v.items():setattr(row,k,value)
    if kind=='templates':row.reviewed_by=user.id if row.approved else None
    row.updated_at=utcnow();db.flush();audit(db,user.id,'master_update','flow_master',row.id,before,plain(row),reason=config['label'])
    db.commit();return master_info(db,user,kind,row)


@router.get('/analytics')
def analytics(date_from:date|None=None,date_to:date|None=None,db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    from .flow_analytics import build_analytics
    return build_analytics(db,user,date_from,date_to)


@router.get('/analytics/export')
def analytics_export(dataset:str='orders',date_from:date|None=None,date_to:date|None=None,customer_key:str|None=None,db=Depends(get_db),user=Depends(get_user)):
    require_full(user)
    from .flow_analytics import build_analytics
    data=build_analytics(db,user,date_from,date_to)
    if dataset not in data['tables']:raise HTTPException(422,'报表不存在')
    table=data['tables'][dataset]
    if customer_key is not None:
        if dataset!='customer_value_details' or len(customer_key)>60:raise HTTPException(422,'客户筛选仅适用于客户业务明细')
        selected=[r for r in table['rows'] if r.get('customer_key')==customer_key]
        if not selected:raise HTTPException(404,'当前授权范围与期间没有该客户业务')
        table={**table,'rows':selected,'title':'本客户期间已记录业务明细'}
    buf=io.StringIO(newline='');writer=csv.writer(buf);writer.writerow(table['headers'])
    def safe(x):
        if isinstance(x,(int,float)):return x
        s='' if x is None else str(x)
        return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else s
    for r in table['rows']:writer.writerow([safe(x) for x in r['values']])
    audit(db,user.id,'export','flow_analytics',None,reason=table['title']);db.commit()
    return Response(('\ufeff'+buf.getvalue()).encode(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(table['title']+'.csv')})
