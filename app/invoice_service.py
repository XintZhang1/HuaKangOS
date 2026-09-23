"""External invoice coordination; it neither calls a tax provider nor moves cash."""
import uuid
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,func,and_,or_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .flow_models import Case,Task,FlowEvent
from .tenancy import single_store
from .flow_documents import can_file
from .invoice_models import InvoiceApplication,InvoiceApproval,InvoiceResult
from . import flow_engine as flow

READ={'admin','manager','finance','auditor'}
ROLES={'approve':{'admin','manager'},'reject':{'admin','manager'},'cancel':{'admin','manager','finance'},
       'submit':{'admin','finance'},'failure':{'admin','finance'},'difference':{'admin','finance'},'record':{'admin','finance'},'review_result':{'admin','manager'}}
LABELS={'approve':'复核开票申请','reject':'退回申请','cancel':'取消未办理申请','submit':'登记已向外部提交',
        'failure':'登记外部办理失败','difference':'记录外部票据差异','record':'登记实际发票结果','review_result':'复核实际结果差异'}
KINDS={'order','repair','addon','agency','retail','other_income','insurance','vehicle_income'}


def source_basis(db,source):
    """Derive invoice capacity from the independently approved original domain."""
    if source.kind=='vehicle_income':
        from .vehicle_income_service import invoice_basis
        return invoice_basis(db,source)
    if source.kind!='insurance':return {'kind':'business_charge','label':'原业务已确认金额'}
    from .insurance_service import _commission,_commission_pending,_quote,is_detailed
    if not is_detailed(source):raise HTTPException(409,'旧保险单没有可核验的佣金开票来源')
    confirmed=_commission(db,source)
    quote=_quote(db,source) if source.data.get('insurance_quote_id') else None
    return {'kind':'insurance_commission','label':'保险公司已独立确认佣金',
            'confirmation_id':confirmed.id if confirmed else None,
            'confirmed_cents':confirmed.target_cents if confirmed else 0,
            'quote_id':quote.id if quote else None,
            'insurer_id':quote.insurer_id if quote else None,
            'buyer_name':quote.insurer_snapshot['name'] if quote else '',
            'pending_confirmation':bool(_commission_pending(db,source))}


def _created_basis(db,application):
    event=db.scalar(select(FlowEvent).where(FlowEvent.case_id==application.id,FlowEvent.action=='invoice_v3_create'))
    basis=(event.detail or {}).get('source_basis') if event else None
    if not isinstance(basis,dict):raise HTTPException(409,'发票缺少原申请的冻结依据，请联系管理员核对原始记录')
    return basis


def _guard_commission_blue(db,source,application=None):
    if source.kind=='vehicle_income':
        from .vehicle_income_service import guard_invoice_blue
        guard_invoice_blue(db,source,_created_basis(db,application) if application else None)
        return
    if source.kind!='insurance':return
    basis=source_basis(db,source)
    if basis['pending_confirmation'] or not basis['confirmation_id'] or basis['confirmed_cents']<=0:
        raise HTTPException(409,'须先由另一主管完成实际佣金确认；预计佣金和客户保费不能开门店佣金发票')
    if application and _created_basis(db,application)!=basis:
        raise HTTPException(409,'实际佣金依据已变更，请取消未提交申请并按当前佣金重新申请')


def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'当前门店记录不存在')
    return row
def can_read(user,row):return user.role in READ
def _read(user):
    if user.role not in READ:raise HTTPException(403,'当前岗位不能查看发票协同资料')
def _source(db,user,key,version=None):
    _read(user);row=flow.get_case(db,user,key)
    if row.kind not in KINDS or row.kind=='insurance' and row.flow_version!=3 or row.kind=='vehicle_income' and row.flow_version!=1:raise HTTPException(422,'请选择本店已确认的销售、维修、精品、代办、保险佣金或整车其他收入原单')
    if version is not None and row.version!=version:raise HTTPException(409,'原业务已经变化，请刷新核对开票依据')
    return row
def _order(db,user,key):
    _read(user);row=flow.get_case(db,user,key)
    if row.kind!='invoice' or row.flow_version!=3:raise HTTPException(404,'本店专用开票申请不存在')
    _one(db,InvoiceApplication,key);return row
def _proof(db,user,row,key,category=None):
    asset=flow.file_exists(db,row,key,category)
    if not can_file(user,row,asset):raise HTTPException(403,'当前岗位不能使用该凭据')
    return asset
def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role!='admin'):raise HTTPException(409,'请由当前待办接手人办理，或先明确转交')


def source_amount(db,row):
    if row.kind not in KINDS or row.state in {'cancelled','rejected'}:return 0
    # Customer premiums belong to the insurer, never the store's sales invoice basis.
    if row.kind=='insurance':return source_basis(db,row)['confirmed_cents'] if row.flow_version==3 else 0
    if row.kind=='vehicle_income':
        from .vehicle_income_service import invoice_source_amount
        return invoice_source_amount(db,row) if row.flow_version==1 else 0
    if row.kind=='addon' and row.flow_version==3:
        from .addon_service import invoice_source_amount
        return invoice_source_amount(db,row)
    if row.kind=='order' and row.flow_version in {3,4}:
        from .sales_quote_service import active
        quote=active(db,row)
        return quote.amount_cents if quote else 0
    from .service_orders_service import is_detailed as service_order,source_summary
    if service_order(row):
        summary=source_summary(db,row)
        return summary['fee_charge_cents'] if summary['authorized'] else 0
    if row.kind=='retail':
        from .retail_service import totals
        return totals(db,row)['net_price_cents'] if row.data.get('authorized') else 0
    from .repair_service import is_detailed,revenue_amount
    if is_detailed(row):
        from .repair_models import RepairSettlement
        if not db.scalar(select(RepairSettlement.id).where(RepairSettlement.case_id==row.id)):
            return 0
        from .repair_package_service import invoice_source_discount
        amount=revenue_amount(db,row)-invoice_source_discount(db,row)
        if amount<0:raise HTTPException(409,'原套餐履约对价与维修应开票额不守恒，请先核对原组件及售后来源')
        return amount
    return row.amount_cents


def balance(db,source,exclude=None):
    """Unexecuted red applications do not free blue invoice capacity."""
    actual=0;pending=0
    legacy=list(db.scalars(select(Case).where(Case.kind=='invoice',Case.flow_version.in_([1,2]),Case.parent_id==source.id,Case.state.notin_(['cancelled','rejected']))))
    for old in legacy:
        if old.id==exclude:continue
        if old.state=='completed':actual+=old.amount_cents
        else:pending+=old.amount_cents
    for application in _rows(db,InvoiceApplication,source_case_id=source.id):
        result=db.scalar(select(InvoiceResult).where(InvoiceResult.case_id==application.id))
        if result:actual+=result.amount_cents*(1 if application.direction=='blue' else -1)
        elif application.id!=exclude and application.direction=='blue':
            state=db.scalar(select(Case.state).where(Case.id==application.id))
            if state not in {'cancelled','rejected'}:pending+=application.amount_cents
    allowed=source_amount(db,source)
    return {'invoiceable_cents':allowed,'actual_net_cents':actual,'pending_blue_cents':pending,
            'available_cents':max(0,allowed-actual-pending),'correction_cents':max(0,actual-allowed)}


def red_available(db,original_id,exclude=None,include_pending=True):
    original=_one(db,InvoiceApplication,original_id)
    result=db.scalar(select(InvoiceResult).where(InvoiceResult.case_id==original_id))
    if original.direction!='blue' or not result:raise HTTPException(409,'只能关联已登记实际结果的本店蓝票')
    used=0
    for request in _rows(db,InvoiceApplication,original_case_id=original_id):
        actual=db.scalar(select(InvoiceResult).where(InvoiceResult.case_id==request.id))
        if actual:used+=actual.amount_cents
        elif include_pending and request.id!=exclude:
            state=db.scalar(select(Case.state).where(Case.id==request.id))
            if state not in {'cancelled','rejected'}:used+=request.amount_cents
    return max(0,result.amount_cents-used)


def sync_source(db,user,row):
    if row.kind not in KINDS or row.kind=='insurance' and row.flow_version!=3 or row.kind=='vehicle_income' and row.flow_version!=1:return
    db.flush();summary=balance(db,row)
    if summary['correction_cents']:
        flow.ensure_task(db,row,'invoice_adjust','核对原业务变化后的原票冲红','finance',reopen=True)
    else:flow.finish_task(db,row,'invoice_adjust',user)


def _execute(db,user,request_id,operation,payload,callback):
    single_store(db);payload={k:value.isoformat() if isinstance(value,date) else value for k,value in payload.items()}
    digest=flow.request_digest('invoice_v3_'+operation,payload)
    try:
        previous=flow.prior_request(db,user,request_id,digest)
        if previous:return describe(db,user,previous)
        row=callback();db.flush();flow.save_receipt(db,user,request_id,digest,row);db.commit()
        return describe(db,user,row)
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'票号重复或其他员工正在办理，请保留原请求号并刷新核对')
    except Exception:db.rollback();raise


def create(db,user,request_id,v):
    if user.role not in {'admin','finance'}:raise HTTPException(403,'请由本店财务建立开票或冲红申请')
    def run():
        source=_source(db,user,v['source_case_id'],v['source_version'])
        if v['direction']=='blue':
            _guard_commission_blue(db,source)
            from .claims_service import guard_invoice_blue
            guard_invoice_blue(db,source)
            from .sales_quote_service import guard_source_action as guard_quote
            guard_quote(db,user,source,'invoice_blue')
            from .service_orders_service import guard_source_adjustment as guard_service
            guard_service(db,source,'invoice_blue')
            from .addon_service import guard_source_adjustment as guard_addon
            guard_addon(db,source,'invoice_blue')
        if v['direction']=='red':
            if not v['original_case_id']:raise HTTPException(422,'冲红必须选择原蓝票')
            original=_one(db,InvoiceApplication,v['original_case_id'])
            if original.source_case_id!=source.id:raise HTTPException(404,'原票与当前业务不匹配')
            if v['amount_cents']>red_available(db,original.id):raise HTTPException(409,'超过原蓝票尚未冲红及占用的金额')
            if any(v[k]!=getattr(original,k) for k in ('issuer_name','issuer_tax_id','buyer_name','buyer_tax_id')):
                raise HTTPException(422,'冲红须保持原蓝票的销售方和购买方，换抬头须先按原票冲红再另申请')
        elif v['original_case_id'] is not None:raise HTTPException(422,'蓝票申请不能填写原票')
        elif source.state in {'cancelled','rejected'} or v['amount_cents']>balance(db,source)['available_cents']:
            raise HTTPException(409,'超过原单当前已确认且尚未申请开票的金额')
        basis=source_basis(db,source)
        if source.kind=='insurance':
            if v['direction']=='red':basis=_created_basis(db,original)
            elif v['buyer_name']!=basis['buyer_name'] or not v['buyer_tax_id']:
                raise HTTPException(422,'佣金发票购买方须为原保险公司，并填写其实际开票税号；不能给投保客户开保费票')
        if source.kind=='vehicle_income':
            if v['direction']=='red':basis=_created_basis(db,original)
            elif not basis['buyer_tax_id'] or (v['buyer_name'],v['buyer_tax_id'])!=(basis['buyer_name'],basis['buyer_tax_id']):
                raise HTTPException(422,'整车收入发票购买方须为原往来单位及其冻结税号，请先核对供应商原始资料')
        source.updated_at=utcnow();db.flush()
        row=Case(number='HKI'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='invoice',flow_version=3,state='approval',
                 title=('原票冲红' if v['direction']=='red' else '开票申请')+' · '+v['buyer_name'],parent_id=source.id,customer_id=source.customer_id,
                 owner_id=user.id,created_by=user.id,business_date=today(),due_date=v['due_date'],amount_cents=v['amount_cents'],data={})
        db.add(row);db.flush();db.add(InvoiceApplication(id=row.id,**{k:v[k] for k in ('source_case_id','original_case_id','direction','amount_cents','issuer_name','issuer_tax_id','buyer_name','buyer_tax_id','reason')},source_version=source.version))
        db.flush();from .business_entity_service import freeze_derived_case_entity,case_entity_snapshot
        context=freeze_derived_case_entity(db,user,row,_one(db,Case,v['original_case_id']) if v['direction']=='red' else source)
        if context:
            entity=case_entity_snapshot(db,user,row)['entity']
            if (v['issuer_name'],v['issuer_tax_id'])!=(entity['legal_name'],entity['tax_identifier']):raise HTTPException(409,'开票销售方必须与原业务冻结的经营主体一致，请核对主体全称与识别号')
        flow.ensure_task(db,row,'invoice_review','独立复核原单、抬头和开票金额','manager')
        flow.log_event(db,user,row,'invoice_v3_create','申请原单开票协同',detail={'source_case_id':source.id,'direction':v['direction'],'reason':v['reason'],'source_basis':basis})
        return row
    return _execute(db,user,request_id,'create',v,run)


def command(db,user,key,request_id,version,source_version,action,v):
    if action not in ROLES:raise HTTPException(404,'发票动作不存在')
    if user.role not in ROLES[action]:raise HTTPException(403,'当前岗位不能办理此发票动作')
    def run():
        row=_order(db,user,key);application=_one(db,InvoiceApplication,key)
        source=_source(db,user,application.source_case_id,source_version)
        if application.direction=='blue' and action in {'approve','submit'}:
            _guard_commission_blue(db,source,application)
            from .claims_service import guard_invoice_blue
            guard_invoice_blue(db,source)
            from .service_orders_service import guard_source_adjustment as guard_service
            guard_service(db,source,'invoice_blue')
            from .addon_service import guard_source_adjustment as guard_addon
            guard_addon(db,source,'invoice_blue')
            from .sales_quote_service import guard_source_action as guard_quote
            guard_quote(db,user,source,'invoice_blue')
        if row.version!=version:raise HTTPException(409,'开票记录已变化，请刷新后核对')
        source.updated_at=utcnow();row.updated_at=utcnow();before=row.state
        if action in {'approve','reject'}:
            if row.state!='approval':raise HTTPException(409,'当前申请不在待复核状态')
            _task(db,user,row,'invoice_review')
            if user.id==row.created_by:raise HTTPException(409,'开票申请须由另一位主管独立复核')
            if action=='approve':
                _proof(db,user,row,v['evidence_id']);db.add(InvoiceApproval(case_id=row.id,actor_id=user.id,evidence_id=v['evidence_id'],reason=v['reason']))
                row.state='pending';flow.ensure_task(db,row,'invoice_submit','按已批准内容办理外部开票','finance',assignee=row.owner_id)
            else:row.state='rejected';row.completed_date=today()
            flow.finish_task(db,row,'invoice_review',user)
        elif action=='cancel':
            if row.state not in {'approval','pending'}:raise HTTPException(409,'外部办理中或已有实际票据不能取消；请记录失败或关联原票冲红')
            row.state='cancelled';row.completed_date=today();flow.close_tasks(db,row,user)
        elif action=='submit':
            if row.state!='pending':raise HTTPException(409,'请先完成申请复核；重复提交须先登记外部失败结果')
            _task(db,user,row,'invoice_submit');_proof(db,user,row,v['evidence_id'])
            room=balance(db,source,exclude=row.id)['available_cents'] if application.direction=='blue' else red_available(db,application.original_case_id,exclude=row.id)
            if application.amount_cents>room:raise HTTPException(409,'原业务或原票额度已变更，请取消未提交申请并按当前事实重建')
            row.state='working';flow.set_data(row,external_reference=v['reference']);flow.finish_task(db,row,'invoice_submit',user)
            flow.ensure_task(db,row,'invoice_result','核对外部办理结果及实际发票','finance',assignee=row.owner_id,reopen=True)
        elif action in {'failure','difference'}:
            if row.state!='working':raise HTTPException(409,'当前没有正在办理的外部申请')
            _task(db,user,row,'invoice_result');_proof(db,user,row,v['evidence_id'])
            if action=='failure':
                row.state='pending';flow.finish_task(db,row,'invoice_result',user)
                flow.ensure_task(db,row,'invoice_submit','根据失败凭据重新办理或取消申请','finance',assignee=row.owner_id,reopen=True)
        elif action=='record':
            if row.state!='working':raise HTTPException(409,'须先记录外部提交事实，再登记实际开票结果')
            _task(db,user,row,'invoice_result');_proof(db,user,row,v['evidence_id'],'invoice')
            if not date(2000,1,1)<=v['issued_on']<=today():raise HTTPException(422,'请填写不晚于今天的真实开票日期')
            if application.direction=='red' and v['amount_cents']>red_available(db,application.original_case_id,exclude=row.id):
                raise HTTPException(409,'外部红票金额超过原票可冲金额，请先记录票据差异并核对原票，不能重复冲销')
            if any(c.data.get('invoice_number')==v['invoice_number'] for c in db.scalars(select(Case).where(Case.kind=='invoice',Case.flow_version.in_([1,2])))):
                raise HTTPException(409,'本店历史记录已有该票号，请核对是否重复登记')
            db.add(InvoiceResult(case_id=row.id,invoice_number=v['invoice_number'],issuer_tax_id=application.issuer_tax_id,
                amount_cents=v['amount_cents'],issued_on=v['issued_on'],evidence_id=v['evidence_id'],actor_id=user.id))
            flow.finish_task(db,row,'invoice_result',user);db.flush()
            mismatch=v['amount_cents']!=application.amount_cents or balance(db,source)['correction_cents']>0
            row.state='resolving' if mismatch else 'completed';row.completed_date=None if mismatch else today()
            if mismatch:flow.ensure_task(db,row,'invoice_result_review','独立复核实际票据与批准或原单金额差异','manager')
        elif action=='review_result':
            if row.state!='resolving':raise HTTPException(409,'当前没有待复核的实际结果差异')
            _task(db,user,row,'invoice_result_review');_proof(db,user,row,v['evidence_id'])
            result=db.scalar(select(InvoiceResult).where(InvoiceResult.case_id==row.id))
            if not result or user.id in {result.actor_id,row.created_by}:raise HTTPException(409,'须由另一位主管核对实际结果差异')
            flow.finish_task(db,row,'invoice_result_review',user);row.state='completed';row.completed_date=today()
        sync_source(db,user,source)
        flow.log_event(db,user,row,'invoice_v3_'+action,LABELS[action],before,{**v,'issued_on':v['issued_on'].isoformat()} if 'issued_on' in v else v)
        return row
    return _execute(db,user,request_id,action,{'id':key,'version':version,'source_version':source_version,'values':{k:value.isoformat() if isinstance(value,date) else value for k,value in v.items()}},run)


def describe(db,user,row):
    _read(user);application=_one(db,InvoiceApplication,row.id);source=_source(db,user,application.source_case_id)
    result=db.scalar(select(InvoiceResult).where(InvoiceResult.case_id==row.id))
    info={k:getattr(row,k) for k in ('id','number','state','version','store_id','title','amount_cents')}
    info.update({k:getattr(application,k) for k in ('source_case_id','original_case_id','direction','issuer_name','issuer_tax_id','buyer_name','buyer_tax_id','reason')})
    info.update(source_version=source.version,source_number=source.number,due_date=row.due_date.isoformat(),balance=balance(db,source),
        actions=[key for key,roles in ROLES.items() if user.role in roles],result=None)
    info['source_basis']=_created_basis(db,application) if source.kind in {'insurance','vehicle_income'} else source_basis(db,source)
    if result:info['result']={**{k:getattr(result,k) for k in ('invoice_number','amount_cents','evidence_id')},'issued_on':result.issued_on.isoformat()}
    if application.direction=='blue' and result:info['red_available_cents']=red_available(db,row.id)
    info['events']=[{'action':e.action,'label':e.label,'detail':e.detail,'actor_id':e.actor_id,'occurred_at':e.occurred_at.isoformat()+'Z'} for e in db.scalars(select(FlowEvent).where(FlowEvent.case_id==row.id).order_by(FlowEvent.id))]
    return info


def list_orders(db,user,page=1,page_size=30):
    _read(user);q=select(Case).where(Case.kind=='invoice',Case.flow_version==3)
    count=db.scalar(select(func.count()).select_from(q.subquery()))
    rows=list(db.scalars(q.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size)))
    return {'items':[describe(db,user,row) for row in rows],'total':count,'page':page,'page_size':page_size}
def sources(db,user,page=1,page_size=30):
    _read(user);q=select(Case).where(or_(Case.kind.in_(KINDS-{'insurance','vehicle_income'}),and_(Case.kind=='insurance',Case.flow_version==3),and_(Case.kind=='vehicle_income',Case.flow_version==1)))
    count=db.scalar(select(func.count()).select_from(q.subquery()))
    rows=list(db.scalars(q.order_by(Case.id.desc()).offset((page-1)*page_size).limit(page_size)))
    return {'items':[{'id':r.id,'number':r.number,'title':r.title,'kind':r.kind,'version':r.version,'source_basis':source_basis(db,r),**balance(db,r)} for r in rows],
            'total':count,'page':page,'page_size':page_size}
