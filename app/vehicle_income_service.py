"""Evidence-backed manufacturer/supplier income without invented customers."""
import uuid
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import CashEntry,Vehicle
from .flow_models import Case,Task,Account,PaymentLink,FileAsset,VehicleHold,FlowEvent
from .tenancy import single_store
from .flow_documents import can_file
from .file_security import require_usable
from . import flow_engine as flow
from .vehicle_income_models import *

READ={'admin','manager','finance','auditor'}
WRITE={'admin','manager','finance'}
ROLES={'propose':WRITE,'approve':{'admin','manager'},'reject':{'admin','manager'},'withdraw':WRITE,
       'receive':{'admin','finance'},'refund':{'admin','finance'},'cancel':WRITE}
LABELS={'propose':'提出有据应收目标','approve':'独立批准应收目标','reject':'退回应收依据','withdraw':'撤回未批准目标',
        'receive':'登记厂家实际到账','refund':'原厂家款实际退回','cancel':'取消未批准收入申请'}
CASH_CATEGORIES={'in':'vehicle_other_income_in','out':'vehicle_other_income_out'}
SOURCE_KINDS={'order','vehicle_procurement','vehicle_operations','opening_import'}


def is_detailed(row):return row.kind=='vehicle_income' and row.flow_version==1
def can_read(user,row=None):return user.role in READ and not getattr(user,'_aggregate_scope',False)
def _role(user,roles):
    if user.role not in roles or getattr(user,'_aggregate_scope',False):raise HTTPException(403,'请选择本店有权财务或主管办理非客户整车收入')
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'本店原来源不存在或无权使用')
    return row
def get_order(db,user,key):
    single_store(db);_role(user,READ);row=flow.get_case(db,user,key)
    if not is_detailed(row):raise HTTPException(404,'本店非客户整车收入单不存在')
    _one(db,VehicleIncomeOrder,row.id);return row
def _date(value):
    day=value if isinstance(value,date) else date.fromisoformat(value)
    if not date(2000,1,1)<=day<=today():raise HTTPException(422,'实际业务日期须已发生且在支持范围内')
    return day
def _proof(db,user,row,key,receipt=False):
    asset=_one(db,FileAsset,key);require_usable(db,asset)
    if asset.case_id!=row.id or asset.generated or not can_file(user,row,asset) or (asset.category!='receipt' if receipt else asset.category not in {'evidence','authorization','signed_contract','invoice'}):
        raise HTTPException(403,'请使用本收入单已扫描、当前岗位可读的真实原件和正确凭据类别')
    for model in (VehicleIncomeRevision,VehicleIncomeDecision,VehicleIncomeCash):
        if db.scalar(select(model.id).join(FileAsset,FileAsset.id==model.evidence_id).where(FileAsset.case_id==row.id,FileAsset.sha256==asset.sha256).limit(1)):
            raise HTTPException(409,'该原件已确认其他事实，请上传本次实际依据')
    return asset
def _execute(db,user,key,action,values,operation):
    single_store(db);digest=flow.request_digest('vehicle_income_'+action,values)
    try:
        previous=db.scalar(select(VehicleIncomeReceipt).where(VehicleIncomeReceipt.request_key==key))
        if previous:
            if previous.actor_id!=user.id or previous.digest!=digest:raise HTTPException(409,'原请求编号已用于其他员工或内容')
            return previous.result
        result=operation();db.flush();db.add(VehicleIncomeReceipt(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'原来源、结算编号或资金同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise


def _source_snapshot(db,user,key,vehicle_id=None):
    source=flow.get_case(db,user,key)
    if source.kind not in SOURCE_KINDS or source.state in {'cancelled','rejected'}:raise HTTPException(409,'须选择本店已确认的整车采购、销售或实际原入库来源')
    car=None;allocation=None
    if source.kind=='order':
        if source.flow_version not in {2,3,4} or source.state not in {'executing','delivered','credit_open'}:raise HTTPException(409,'原销售尚未批准，不构成整车收入依据')
        hold=db.scalar(select(VehicleHold).where(VehicleHold.case_id==source.id))
        if vehicle_id and (not hold or hold.vehicle_id!=vehicle_id):raise HTTPException(409,'所选车辆不属于原销售配车')
        if hold:
            car=_one(db,Vehicle,hold.vehicle_id)
            allocation=next((e for e in db.scalars(select(FlowEvent).where(FlowEvent.case_id==source.id,FlowEvent.action=='allocate').order_by(FlowEvent.id.desc())) if e.detail.get('vehicle_id')==car.id),None)
            if not allocation:raise HTTPException(409,'原销售配车缺少不可变办理事实，不能推断历史VIN')
    elif source.kind=='vehicle_procurement':
        from .vehicle_procurement_models import VehiclePurchaseOrder,VehiclePurchasePrice,VehiclePurchaseReceipt
        _one(db,VehiclePurchaseOrder,source.id)
        if source.flow_version!=2 or not db.scalar(select(VehiclePurchasePrice.id).where(VehiclePurchasePrice.case_id==source.id)):raise HTTPException(409,'整车采购尚未独立核价批准')
        if vehicle_id:
            if not db.scalar(select(VehiclePurchaseReceipt.id).where(VehiclePurchaseReceipt.case_id==source.id,VehiclePurchaseReceipt.vehicle_id==vehicle_id)):raise HTTPException(409,'所选车辆没有本采购原单实际接收记录')
            car=_one(db,Vehicle,vehicle_id)
    else:
        from .vehicle_operations_models import VehiclePositionEntry
        if source.flow_version!=2 or not vehicle_id:raise HTTPException(409,'原入库来源须明确实际车辆代次')
        if not db.scalar(select(VehiclePositionEntry.id).where(VehiclePositionEntry.case_id==source.id,VehiclePositionEntry.vehicle_id==vehicle_id,VehiclePositionEntry.quantity==1)):
            raise HTTPException(409,'所选车辆没有本原单实际入库事实')
        car=_one(db,Vehicle,vehicle_id)
    from .business_entity_service import authority
    from .business_entity_models import CaseEntityContext
    with authority(db,user):context=db.scalar(select(CaseEntityContext).where(CaseEntityContext.case_id==source.id))
    return source,dict(case_id=source.id,number=source.number,kind=source.kind,flow_version=source.flow_version,version=source.version,
        business_date=source.business_date.isoformat(),vehicle_id=car.id if car else None,vin=car.vin if car else None,
        entity_revision_id=context.revision_id if context else None,allocation_event_id=allocation.id if allocation else None)


def entity_source_ids(db,row):return {s.source_case_id for s in _rows(db,VehicleIncomeSource,case_id=row.id)}
def _source_entities(db,user,snapshots):
    from .business_entity_service import authority,revision_entity
    revisions={s['entity_revision_id'] for s in snapshots}
    if None in revisions and len(revisions)>1:raise HTTPException(409,'不能合并主体已知与未知的原来源')
    with authority(db,user):identities={revision_entity(db,r) for r in revisions if r is not None}
    if len(identities)>1:raise HTTPException(409,'多个原来源须属于同一本店法人主体')
    if not identities:
        from .business_entity_models import EntityPolicy
        from .config import settings
        with authority(db,user):policy=db.scalar(select(EntityPolicy.id))
        if policy or settings.environment=='production':raise HTTPException(409,'历史原来源主体未知，不能创建正式收入派生或认领本店当前主体')
    return bool(identities)
def _source_versions(db,row):return {str(k):_one(db,Case,k).version for k in sorted(entity_source_ids(db,row))}
def source_candidates(db,user,page=1):
    single_store(db);_role(user,READ)
    q=flow.case_query(user).where(Case.kind.in_(SOURCE_KINDS),Case.state.notin_(['cancelled','rejected']))
    items=[]
    from .vehicle_procurement_models import VehiclePurchaseReceipt
    from .vehicle_operations_models import VehiclePositionEntry
    for row in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*50).limit(50)):
        vehicles=[None]
        if row.kind=='vehicle_procurement':vehicles+=[r.vehicle_id for r in db.scalars(select(VehiclePurchaseReceipt).where(VehiclePurchaseReceipt.case_id==row.id))]
        if row.kind in {'vehicle_operations','opening_import'}:vehicles=list(db.scalars(select(VehiclePositionEntry.vehicle_id).where(VehiclePositionEntry.case_id==row.id,VehiclePositionEntry.quantity==1)))
        for vehicle_id in dict.fromkeys(vehicles):
            try:source,snapshot=_source_snapshot(db,user,row.id,vehicle_id)
            except HTTPException as exc:
                if exc.status_code in {403,404,409}:continue
                raise
            items.append(dict(id=row.id,number=row.number,title=row.title,kind=row.kind,version=row.version,vehicle_id=snapshot['vehicle_id'],vin=snapshot['vin']))
    return dict(items=items,total=db.scalar(select(func.count()).select_from(q.subquery())))


def current_revision(db,row):
    return db.scalar(select(VehicleIncomeRevision).join(VehicleIncomeDecision,VehicleIncomeDecision.revision_id==VehicleIncomeRevision.id).where(VehicleIncomeRevision.case_id==row.id,VehicleIncomeDecision.decision=='approved').order_by(VehicleIncomeRevision.id.desc()))
def pending_revision(db,row):
    return db.scalar(select(VehicleIncomeRevision).where(VehicleIncomeRevision.case_id==row.id,~select(VehicleIncomeDecision.id).where(VehicleIncomeDecision.revision_id==VehicleIncomeRevision.id).exists()).order_by(VehicleIncomeRevision.id.desc()))
def totals(db,row):
    revision=current_revision(db,row);target=revision.target_cents if revision else 0
    cash=_rows(db,VehicleIncomeCash,case_id=row.id);received=sum(c.amount_cents for c in cash if c.direction=='in');refunded=sum(c.amount_cents for c in cash if c.direction=='out');net=received-refunded
    return dict(target_cents=target,received_cents=received,refunded_cents=refunded,net_received_cents=net,receivable_cents=max(0,target-net),refund_due_cents=max(0,net-target))
def invoice_basis(db,row):
    order=_one(db,VehicleIncomeOrder,row.id);revision=current_revision(db,row)
    return dict(kind='vehicle_income',label='厂家及供应商已独立确认整车其他收入',revision_id=revision.id if revision else None,
        digest=revision.digest if revision else None,confirmed_cents=revision.target_cents if revision else 0,
        invoice_mode=revision.invoice_mode if revision else None,buyer_name=order.supplier_snapshot['name'],buyer_tax_id=order.supplier_snapshot['tax_identifier'],
        supplier_id=order.supplier_id,pending_revision=bool(pending_revision(db,row)))
def invoice_source_amount(db,row):
    revision=current_revision(db,row)
    return revision.target_cents if revision and revision.invoice_mode=='store_invoice' and row.state!='cancelled' else 0
def guard_invoice_blue(db,row,application_basis=None):
    basis=invoice_basis(db,row)
    if basis['pending_revision'] or not basis['revision_id'] or basis['invoice_mode']!='store_invoice' or basis['confirmed_cents']<=0:
        raise HTTPException(409,'须有独立批准的门店开票依据和应收目标，原厂家凭据不能自动转为门店蓝票')
    if application_basis is not None and application_basis!=basis:raise HTTPException(409,'原收入批准依据已变化，请取消未提交申请并按当前来源重新申请')
def cash_source_case(db,cash_id):
    entry=db.scalar(select(VehicleIncomeCash).where(VehicleIncomeCash.cash_id==cash_id))
    return _one(db,Case,entry.case_id) if entry else None
def actual_income_rows(db,row):
    return [dict(fact_id=d.id,revision_id=r.id,business_date=d.business_date.isoformat(),amount_cents=r.target_cents-r.previous_cents,
        previous_cents=r.previous_cents,target_cents=r.target_cents) for r in _rows(db,VehicleIncomeRevision,case_id=row.id)
        for d in _rows(db,VehicleIncomeDecision,revision_id=r.id) if d.decision=='approved']


def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='vehicle_income_'+key,Task.status=='open'))
    if not task or user.role!='admin' and task.assignee_id!=user.id:raise HTTPException(409,'请由当前财务或主管接手人办理，或先明确交接')
def _sync(db,user,row):
    if row.state=='cancelled':return
    pending=pending_revision(db,row);revision=current_revision(db,row);t=totals(db,row);desired={}
    if pending:desired['review']=('独立核对厂家应收目标及原依据','manager')
    elif not revision:desired['propose']=('核对原厂家结算依据并提出应收目标','finance')
    elif t['refund_due_cents']:desired['refund']=('按厂家原款原账户实际退款','finance')
    elif t['receivable_cents']:desired['receive']=('登记厂家或供应商实际到账','finance')
    for task in _rows(db,Task,case_id=row.id,status='open'):
        if task.key.startswith('vehicle_income_') and task.key.removeprefix('vehicle_income_') not in desired:flow.finish_task(db,row,task.key,user)
    for key,(title,role) in desired.items():
        old=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='vehicle_income_'+key,Task.status=='open'));assignee=old.assignee_id if old else None
        if key=='review':
            eligible=[u for u in flow.eligible_users(db,'manager',row.store_id) if u.id not in {pending.actor_id,row.created_by}]
            if not eligible:raise HTTPException(409,'请配置另一位主管独立批准，申请人不能自批')
            if assignee not in {u.id for u in eligible}:assignee=eligible[0].id
        flow.ensure_task(db,row,'vehicle_income_'+key,title,role,assignee=assignee,due=old.due_date if old else row.due_date,reopen=True)
    row.amount_cents=t['target_cents'];row.state='approval' if pending else 'pending' if not revision else 'refund_pending' if t['refund_due_cents'] else 'credit_open' if t['receivable_cents'] else 'completed'
    row.completed_date=today() if row.state=='completed' else None


def create(db,user,key,v):
    _role(user,WRITE)
    def run():
        from .master_data import require_active
        supplier=require_active(db,'suppliers',v['supplier_id'])
        if supplier.version!=v['supplier_version']:raise HTTPException(409,'往来单位资料已变化，请刷新核对')
        snapshots=[];seen=set()
        for value in v['sources']:
            source,snapshot=_source_snapshot(db,user,value['source_case_id'],value.get('vehicle_id'))
            if source.version!=value['source_version']:raise HTTPException(409,'原来源版本已变化，请刷新核对')
            identity=(source.id,snapshot['vehicle_id'])
            if identity in seen:raise HTTPException(422,'同一原来源和车辆不能重复')
            seen.add(identity);snapshots.append(snapshot)
        known=_source_entities(db,user,snapshots)
        primary=snapshots[0]['case_id'];row=Case(number='HKVI'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='vehicle_income',flow_version=1,state='pending',title=supplier.name+' · 整车其他收入',owner_id=user.id,created_by=user.id,customer_id=None,parent_id=primary,business_date=today(),due_date=date.fromisoformat(v['due_date']),amount_cents=0,data={})
        db.add(row);db.flush();snapshot={k:getattr(supplier,k) for k in ('id','version','code','name','tax_identifier')}
        db.add(VehicleIncomeOrder(id=row.id,supplier_id=supplier.id,supplier_snapshot=snapshot,external_reference=v['external_reference'],primary_source_case_id=primary,reason=v['reason'],actor_id=user.id));db.flush()
        for s in snapshots:db.add(VehicleIncomeSource(case_id=row.id,source_case_id=s['case_id'],source_version=s['version'],vehicle_id=s['vehicle_id'],snapshot=s,digest=flow.request_digest('vehicle_income_source',s)))
        db.flush()
        if known:
            from .business_entity_service import freeze_case_entity
            freeze_case_entity(db,user,row,source_case=_one(db,Case,primary))
        _sync(db,user,row);flow.log_event(db,user,row,'vehicle_income_create','建立非客户整车收入原来源',detail={'primary_source_case_id':primary,'source_count':len(snapshots),'entity_known':known});db.flush();return describe(db,user,row)
    return _execute(db,user,key,'create',v,run)


def _cash(db,user,row,revision,action,v):
    if pending_revision(db,row):raise HTTPException(409,'原应收目标正在独立修订，请先完成复核')
    t=totals(db,row);original=None;direction='in' if action=='receive' else 'out'
    account=db.scalar(select(Account).where(Account.id==v['account_id']).with_for_update())
    if not account or not account.active:raise HTTPException(409,'请选择本店已启用实际资金账户')
    account.updated_at=utcnow();db.flush()
    if direction=='in':
        if v['amount_cents']>t['receivable_cents']:raise HTTPException(409,'实际到账超过本版已批准尚欠金额')
    else:
        original=_one(db,VehicleIncomeCash,v['original_id'])
        used=sum(x.amount_cents for x in _rows(db,VehicleIncomeCash,original_id=original.id))
        if original.case_id!=row.id or original.direction!='in' or original.account_id!=account.id:raise HTTPException(409,'退款必须使用本收入单原实际到账及原账户')
        if v['amount_cents']>min(original.amount_cents-used,t['refund_due_cents']):raise HTTPException(409,'实际退回超过本次原款可退或已批准超收额度')
    day=_date(v['business_date'])
    decision=db.scalar(select(VehicleIncomeDecision).where(VehicleIncomeDecision.revision_id==revision.id))
    if day<decision.business_date or original and day<original.business_date:raise HTTPException(422,'实际资金日期不能早于对应批准或原款')
    _proof(db,user,row,v['evidence_id'],True)
    if db.scalar(select(VehicleIncomeCash.id).where(VehicleIncomeCash.account_id==account.id,VehicleIncomeCash.reference==v['reference'])) or db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==v['reference'])) or db.scalar(select(PaymentLink.id).where(PaymentLink.account_id==account.id,PaymentLink.reference==v['reference'])):raise HTTPException(409,'该账户实际流水已登记，不能重复记录资金')
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,row,account.id,day,original_cash_id=original.cash_id if original else None)
    order=_one(db,VehicleIncomeOrder,row.id);cash=CashEntry(doc_no='VI-'+uuid.uuid4().hex[:24],business_date=day,created_by=user.id,approval_state='approved',direction=direction,category=CASH_CATEGORIES[direction],amount_cents=v['amount_cents'],account=account.name,counterparty=order.supplier_snapshot['name'],payment_method=account.account_type,voucher_no=v['reference'],note='原整车其他收入 '+row.number)
    db.add(cash);db.flush();record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else None)
    db.add(VehicleIncomeCash(case_id=row.id,revision_id=revision.id,original_id=original.id if original else None,direction=direction,amount_cents=v['amount_cents'],cash_id=cash.id,account_id=account.id,account_snapshot={k:getattr(account,k) for k in ('id','version','name','account_type')},reference=v['reference'],business_date=day,evidence_id=v['evidence_id'],actor_id=user.id))


def command(db,user,key,request_id,version,action,v):
    _role(user,ROLES.get(action,set()))
    def run():
        row=get_order(db,user,key)
        if row.version!=version:raise HTTPException(409,'原收入单已变化，请刷新核对本版目标与原款')
        if row.state=='cancelled':raise HTTPException(409,'已取消的原收入申请只读')
        row.updated_at=utcnow();db.flush();pending=pending_revision(db,row);current=current_revision(db,row)
        if action=='propose':
            if pending:raise HTTPException(409,'已有待复核的原应收版本，请先明确撤回或复核')
            _proof(db,user,row,v['evidence_id'])
            if not current and v['target_cents']<=0:raise HTTPException(422,'首次应收须有真实正金额；无需收款的未批准申请可以取消')
            due=date.fromisoformat(v['due_date'])
            if not date(2000,1,1)<=due<=date(2100,1,1):raise HTTPException(422,'请核对应收期限')
            facts=dict(previous_id=current.id if current else None,previous_cents=current.target_cents if current else 0,target_cents=v['target_cents'],invoice_mode=v['invoice_mode'],due_date=due.isoformat(),source_versions=_source_versions(db,row),reason=v['reason'],evidence_id=v['evidence_id'])
            revision=VehicleIncomeRevision(case_id=row.id,revision=len(_rows(db,VehicleIncomeRevision,case_id=row.id))+1,**{**facts,'due_date':due},digest=flow.request_digest('vehicle_income_revision',facts),actor_id=user.id)
            db.add(revision)
        elif action in {'approve','reject','withdraw'}:
            if not pending or pending.id!=v['revision_id']:raise HTTPException(409,'不是本单当前等待复核的应收版本')
            if action=='withdraw':
                if user.id!=pending.actor_id and user.role not in {'admin','manager'}:raise HTTPException(403,'仅原申请人或主管可撤回未批准版本')
            else:
                _task(db,user,row,'review')
                if user.id in {pending.actor_id,row.created_by}:raise HTTPException(403,'原申请或目标提出人不能自批，管理员也不例外')
                _proof(db,user,row,v['evidence_id'])
            if action=='approve':
                if pending.source_versions!=_source_versions(db,row):raise HTTPException(409,'复核期间原车辆依据已变化，请退回或撤回后重新提出本版目标')
                from .business_entity_service import require_case_entity
                require_case_entity(db,user,row)
                if (pending.previous_id,pending.previous_cents)!=(current.id if current else None,current.target_cents if current else 0):raise HTTPException(409,'前一批准目标已变化')
                row.due_date=pending.due_date
            db.add(VehicleIncomeDecision(revision_id=pending.id,decision={'approve':'approved','reject':'rejected','withdraw':'withdrawn'}[action],reason=v['reason'],evidence_id=v.get('evidence_id'),business_date=today(),actor_id=user.id))
        elif action in {'receive','refund'}:
            if not current:raise HTTPException(409,'尚无独立批准的原应收目标')
            _task(db,user,row,action);_cash(db,user,row,current,action,v)
        elif action=='cancel':
            if current or _rows(db,VehicleIncomeCash,case_id=row.id):raise HTTPException(409,'已批准原收入须追加目标修订及原款退款，不能普通取消')
            if pending:db.add(VehicleIncomeDecision(revision_id=pending.id,decision='withdrawn',reason=v['reason'],evidence_id=None,business_date=today(),actor_id=user.id))
            row.state='cancelled';flow.close_tasks(db,row,user)
        else:raise HTTPException(404,'不存在此整车收入动作')
        db.flush();_sync(db,user,row);flow.log_event(db,user,row,'vehicle_income_'+action,LABELS[action],detail=v)
        from .invoice_service import sync_source
        sync_source(db,user,row);db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,action,dict(case_id=key,version=version,values=v),run)


def describe(db,user,row):
    _role(user,READ);order=_one(db,VehicleIncomeOrder,row.id)
    def plain(r):return {c.name:(getattr(r,c.name).isoformat() if isinstance(getattr(r,c.name),date) else getattr(r,c.name)) for c in r.__table__.columns}
    revisions=[]
    for r in _rows(db,VehicleIncomeRevision,case_id=row.id):
        d=db.scalar(select(VehicleIncomeDecision).where(VehicleIncomeDecision.revision_id==r.id));revisions.append(dict(**plain(r),decision=plain(d) if d else None))
    current=current_revision(db,row);pending=pending_revision(db,row);payments=[]
    for p in _rows(db,VehicleIncomeCash,case_id=row.id):payments.append(dict(**plain(p),available_cents=p.amount_cents-sum(x.amount_cents for x in _rows(db,VehicleIncomeCash,original_id=p.id)) if p.direction=='in' else 0))
    return dict(id=row.id,number=row.number,version=row.version,kind=row.kind,flow_version=row.flow_version,state=row.state,store_id=row.store_id,title=row.title,
        due_date=row.due_date.isoformat(),supplier=order.supplier_snapshot,external_reference=order.external_reference,reason=order.reason,
        sources=[dict(id=s.id,**s.snapshot) for s in _rows(db,VehicleIncomeSource,case_id=row.id)],revisions=revisions,
        current_revision_id=current.id if current else None,pending_revision_id=pending.id if pending else None,totals=totals(db,row),payments=payments,
        tasks=[dict(id=t.id,key=t.key,title=t.title,assignee_id=t.assignee_id,due_date=t.due_date.isoformat()) for t in _rows(db,Task,case_id=row.id,status='open')],
        actions=[a for a,roles in ROLES.items() if user.role in roles and row.state!='cancelled'])
