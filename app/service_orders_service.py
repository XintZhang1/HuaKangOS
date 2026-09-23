"""Versioned customer services; pass-through cash is never fee revenue."""
import uuid
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import CashEntry
from .flow_models import Case,Customer,Task,Account,PaymentLink,FileAsset
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .service_orders_models import *

READ={'admin','manager','sales','service','finance','auditor'}
FRONT={'admin','sales','service'};MANAGE={'admin','manager'};FINANCE={'admin','finance'}
ROLES={**{a:FRONT for a in ('quote','authorize','submit','external_result','fulfill','termination','consent')},
       **{a:MANAGE for a in ('approve','termination_approve')},
       **{a:FINANCE for a in ('receive','disburse','thirdparty_return','termination_apply','refund')},
       **{a:FRONT|MANAGE for a in ('cancel','termination_cancel')}}
LABELS={'quote':'核对项目及报价版本','approve':'独立批准当前价格','authorize':'登记客户当前版授权',
        'submit':'确认实际提交或补件','external_result':'登记实际外部结果','fulfill':'确认本项实际办结',
        'receive':'确认客户实际到账','disburse':'按原资金实际代缴','thirdparty_return':'确认第三方原路退回',
        'termination':'提出终止与保留费用方案','termination_approve':'独立复核终止方案','consent':'登记客户同意终止',
        'termination_apply':'生效已同意的费用调整','refund':'按批准方案退原客户款','termination_cancel':'撤销尚未生效方案','cancel':'取消尚未办理申请'}

def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _first(db,model,**kw):return db.scalar(select(model).filter_by(**kw))
def _one(db,model,key):
    obj=db.scalar(select(model).where(model.id==key))
    if not obj:raise HTTPException(404,'本店服务关联记录不存在')
    return obj
def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此服务步骤')
def is_detailed(row):return (row.kind,row.flow_version) in {('agency',3),('other_income',2)}
def get_order(db,user,key):
    single_store(db);_role(user,READ);row=flow.get_case(db,user,key)
    if not is_detailed(row):raise HTTPException(404,'本店明细服务单不存在')
    _one(db,ServiceOrder,row.id);return row
def _quote(db,row,authorized=False):
    q=_one(db,ServiceQuote,row.data.get('service_quote_id',0))
    if q.case_id!=row.id:raise HTTPException(409,'报价版本不属于本服务单')
    if authorized and not _first(db,ServiceAuthorization,quote_id=q.id):raise HTTPException(409,'请先取得客户对当前报价版本的授权')
    return q
def _lines(db,row):return _rows(db,ServiceLine,quote_id=_quote(db,row).id) if row.data.get('service_quote_id') else []
def _line(db,row,key):
    line=next((x for x in _lines(db,row) if x.line_key==key),None)
    if not line:raise HTTPException(422,'请选择本单当前报价的原项目')
    return line
def _proof(db,user,row,key,financial=False):
    asset=flow.file_exists(db,row,key,'receipt' if financial else 'authorization')
    if asset.generated or not can_file(user,row,asset):raise HTTPException(403,'须使用本服务单新上传并通过扫描的本次原件')
    for model in (ServicePriceApproval,ServiceAuthorization,ServiceSubmission,ServiceExternalResult,ServiceFulfillment,
                  ServiceTenderSlice,ServicePassEntry,ServiceTermination,ServiceTerminationApproval,ServiceTerminationConsent,ServiceTerminationApplication,ServiceRefund):
        if db.scalar(select(model.id).join(FileAsset,FileAsset.id==model.evidence_id).where(FileAsset.case_id==row.id,FileAsset.sha256==asset.sha256).limit(1)):
            raise HTTPException(409,'此原件已登记其他办理事实，请上传本次实际结果凭据')
    return asset
def _execute(db,user,key,operation,payload,fn):
    single_store(db);digest=flow.request_digest('service_orders_'+operation,payload)
    try:
        prior=_first(db,ServiceRequest,request_key=key)
        if prior:
            if prior.actor_id!=user.id or prior.digest!=digest:raise HTTPException(409,'请求编号已用于其他内容或经办人，请核对原结果')
            return prior.result
        result=fn();db.flush();db.add(ServiceRequest(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'服务单或原资金同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise
def _task(db,user,row,key):
    task=_first(db,Task,case_id=row.id,key=key,status='open')
    if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(409,'请由当前服务待办接手人办理，或先明确交接')
def _manager(db,row,key,title,excluded):
    users=[u for u in flow.eligible_users(db,'manager',row.store_id) if u.id not in excluded]
    if not users:raise HTTPException(409,'须配置另一位主管独立复核，技术管理员也不能审批本人申请')
    task=_first(db,Task,case_id=row.id,key=key,status='open')
    flow.ensure_task(db,row,key,title,'manager',assignee=task.assignee_id if task and task.assignee_id not in excluded else users[0].id,reopen=True)
def _split(amount,weights):
    """Integer proportional allocation, stable original order, last share absorbs remainder."""
    total=sum(w for _,w in weights)
    if amount<0 or amount>total:raise HTTPException(409,'分配金额超过本次尚欠明细')
    result=[];left=amount;remaining=total
    for key,weight in weights:
        value=left if weight==remaining else left*weight//remaining if remaining else 0
        result.append((key,value));left-=value;remaining-=weight
    return result
def _line_net(db,row,line):return 0 if row.state=='cancelled' else line.amount_cents+sum(a.amount_cents for a in _rows(db,ServiceChargeAdjustment,case_id=row.id,line_key=line.line_key))
def _line_paid(db,row,line):return sum(t.amount_cents for t in _rows(db,ServiceTenderSlice,case_id=row.id,line_key=line.line_key))
def _reservation(db,row):
    from .business_finance_sources import case_reserved_amount
    return case_reserved_amount(db,row.id)
def _active_plan(db,row):
    for p in reversed(_rows(db,ServiceTermination,case_id=row.id)):
        if not _first(db,ServiceTerminationCancellation,plan_id=p.id) and not _first(db,ServiceTerminationApplication,plan_id=p.id):return p
    return None
def _terminated(db,row):return bool(db.scalar(select(ServiceTerminationApplication.id).join(ServiceTermination,ServiceTermination.id==ServiceTerminationApplication.plan_id).where(ServiceTermination.case_id==row.id).limit(1)))
def _unrefunded(db,tender):return tender.amount_cents+sum(x.amount_cents for x in _rows(db,ServiceTenderSlice,original_id=tender.id))
def _spent(db,tender):return sum(e.amount_cents*(1 if e.purpose=='disburse' else -1) for e in _rows(db,ServicePassEntry,tender_id=tender.id))
def _reserved_refund(db,tender,excluding_plan_id=None):
    amount=0
    for p in _rows(db,ServiceTermination,case_id=tender.case_id):
        if p.id==excluding_plan_id or _first(db,ServiceTerminationCancellation,plan_id=p.id) or not _first(db,ServiceTerminationApproval,plan_id=p.id):continue
        selected=sum(x['amount_cents'] for x in p.returns if x['tender_id']==tender.id)
        refunded=sum(x.amount_cents for x in _rows(db,ServiceRefund,plan_id=p.id,original_tender_id=tender.id))
        amount+=selected-refunded
    return amount
def source_summary(db,row):
    order=_one(db,ServiceOrder,row.id);lines=_lines(db,row);summary={b:{'charge':0,'paid':0,'reserved':0,'due':0} for b in ('fee','pass')}
    weights=[(l.id,max(0,_line_net(db,row,l)-_line_paid(db,row,l))) for l in lines]
    reserved=dict(_split(min(_reservation(db,row),sum(w for _,w in weights)),weights))
    for l in lines:
        part=summary[l.bucket];charge=_line_net(db,row,l);paid=_line_paid(db,row,l);part['charge']+=charge;part['paid']+=paid;part['reserved']+=reserved[l.id];part['due']+=max(0,charge-paid-reserved[l.id])
    entries=_rows(db,ServicePassEntry,case_id=row.id);disbursed=sum(e.amount_cents for e in entries if e.purpose=='disburse');returned=sum(e.amount_cents for e in entries if e.purpose=='thirdparty_return')
    return dict(customer_id=row.customer_id,source_order_id=order.source_order_id,delivery_blocking=order.delivery_blocking,
        authorized=bool(row.state!='cancelled' and row.data.get('service_quote_id') and _first(db,ServiceAuthorization,quote_id=row.data['service_quote_id'])),terminal=row.state in {'completed','cancelled'},
        **{f'{bucket}_{key}_cents':value for bucket,values in summary.items() for key,value in values.items()},
        customer_due_cents=sum(v['due'] for v in summary.values()),customer_paid_cents=sum(v['paid'] for v in summary.values()),
        pass_cash_balance_cents=summary['pass']['paid']-disbursed+returned,thirdparty_paid_cents=disbursed,thirdparty_returned_cents=returned)
def customer_due(db,row,include_reservations=True):
    s=source_summary(db,row);return s['customer_due_cents'] if include_reservations else max(0,s['fee_charge_cents']+s['pass_charge_cents']-s['customer_paid_cents'])
def fee_due(db,row):return source_summary(db,row)['fee_due_cents']
def pass_due(db,row):return source_summary(db,row)['pass_due_cents']
def guard_source_adjustment(db,row,action='adjustment'):
    if not is_detailed(row):return
    if _active_plan(db,row) or any(_reserved_refund(db,t)>0 for t in _rows(db,ServiceTenderSlice,case_id=row.id) if t.amount_cents>0):raise HTTPException(409,'服务单有待生效终止或原款退款占额，请先办理或撤回原方案')
def source_finance(db,user,row,include_reservations=True):
    get_order(db,user,row.id);guard_source_adjustment(db,row);_quote(db,row,True)
    if row.state=='cancelled':raise HTTPException(409,'已取消服务不能收款')
    s=source_summary(db,row)
    return dict(case_id=row.id,number=row.number,kind=row.kind,version=row.version,customer_id=row.customer_id,amount_cents=s['fee_charge_cents']+s['pass_charge_cents'],
        business_date=row.business_date.isoformat(),allocation_id=None,payer_type='customer',due_cents=customer_due(db,row,include_reservations),credit_cents=sum(t.amount_cents for t in _rows(db,ServiceTenderSlice,case_id=row.id) if t.credit_link_id),allocations=[dict(payer_type='customer',bucket=b,amount_cents=s[b+'_charge_cents'],paid_cents=s[b+'_paid_cents'],due_cents=s[b+'_due_cents']+(0 if include_reservations else s[b+'_reserved_cents']),due_date=row.due_date.isoformat()) for b in ('fee','pass')])
def invoice_source_amount(db,row):return source_summary(db,row)['fee_charge_cents']
def gross_revenue_amount(db,row):return sum(f.amount_cents for f in _rows(db,ServiceFulfillment,case_id=row.id) if _one(db,ServiceLine,f.line_id).bucket=='fee')
def actual_income_rows(db,row):
    result=[]
    for fact in _rows(db,ServiceFulfillment,case_id=row.id):
        if _one(db,ServiceLine,fact.line_id).bucket=='fee':result.append(dict(fact_id=fact.id,business_date=fact.business_date.isoformat(),line_id=fact.line_id,amount_cents=fact.amount_cents,kind='fulfillment',original_fact_id=None))
    for a in _rows(db,ServiceChargeAdjustment,case_id=row.id,bucket='fee'):
        f=_first(db,ServiceFulfillment,case_id=row.id,line_key=a.line_key)
        if f:result.append(dict(fact_id=a.id,business_date=_one(db,ServiceTerminationApplication,a.application_id).business_date.isoformat(),line_id=a.line_id,amount_cents=a.amount_cents,kind='fee_reduction',original_fact_id=f.id))
    previous={}
    for p in _rows(db,ServiceTermination,case_id=row.id):
        app=_first(db,ServiceTerminationApplication,plan_id=p.id)
        if not app:continue
        for line in p.lines:
            if line['bucket']=='fee' and not line['fulfilled']:
                amount=line['retained_cents']-previous.get(line['line_key'],0)
                if amount:result.append(dict(fact_id=app.id,business_date=app.business_date.isoformat(),line_id=line['line_id'],amount_cents=amount,kind='retained_fee' if amount>0 else 'fee_reduction',original_fact_id=None))
                previous[line['line_key']]=line['retained_cents']
    return result
def guard_order_delivery(db,row):
    for o in _rows(db,ServiceOrder,source_order_id=row.id,delivery_blocking=True):
        service=_one(db,Case,o.id)
        if service.state not in {'completed','cancelled'}:raise HTTPException(409,'此销售已明确约定交车前办结服务，请先完成关联服务或客户同意的终止结清')
def guard_parent_aftercare(db,user,order):
    """Only independently resolved typed children may be excluded from parent refunds."""
    excluded=set()
    for o in _rows(db,ServiceOrder,source_order_id=order.id):
        row=_one(db,Case,o.id)
        if row.customer_id!=order.customer_id or row.parent_id!=order.id or not is_detailed(row):raise HTTPException(409,'原销售关联服务身份异常，请先核对')
        if row.state=='cancelled':excluded.add(row.id);continue
        if not _terminated(db,row) or row.state!='completed' or _active_plan(db,row):raise HTTPException(409,'关联明细服务须先在原服务单完成客户同意的终止、保留费及原款退款；父销售售后不能代退第三方本金')
        s=source_summary(db,row)
        if s['customer_due_cents'] or s['pass_cash_balance_cents'] or any(_reserved_refund(db,t)>0 for t in _rows(db,ServiceTenderSlice,case_id=row.id) if t.amount_cents>0):raise HTTPException(409,'关联明细服务的客户款或第三方本金仍未结清，请先办理原服务退款')
        excluded.add(row.id)
    return excluded
def _touch_parent(db,row):
    o=_one(db,ServiceOrder,row.id)
    if o.source_order_id:
        p=_one(db,Case,o.source_order_id);p.updated_at=utcnow();db.flush()
def _record_tender(db,user,row,amount,evidence_id,payment=None,credit=None,original=None):
    t=ServiceTenderSlice(case_id=row.id,line_id=original.id if isinstance(original,ServiceLine) else original.line_id,line_key=original.line_key,bucket=original.bucket,amount_cents=amount,
        payment_link_id=payment.id if payment else None,credit_link_id=credit.id if credit else None,original_id=original.id if amount<0 else None,evidence_id=evidence_id,actor_id=user.id)
    db.add(t);db.flush();return t
def _incoming(db,user,row,amount,evidence_id,payment=None,credit=None):
    _quote(db,row,True);guard_source_adjustment(db,row)
    weights=[(l.id,max(0,_line_net(db,row,l)-_line_paid(db,row,l))) for l in _lines(db,row)]
    if amount>sum(w for _,w in weights):raise HTTPException(409,'实际到账超过服务费与代缴本金合计尚欠额')
    result=[]
    for key,part in _split(amount,weights):
        if part:result.append(_record_tender(db,user,row,part,evidence_id,payment,credit,_one(db,ServiceLine,key)))
    return result
def record_collection(db,user,row,payment_link,evidence_id,*,original_payment=None,correction=False):
    """Called after a same-transaction unique CashEntry/PaymentLink, never creates cash."""
    if payment_link.case_id!=row.id:raise HTTPException(409,'资金来源不属于本服务单')
    if _first(db,ServiceTenderSlice,payment_link_id=payment_link.id):raise HTTPException(409,'此真实收款已分配到服务明细')
    if payment_link.direction=='in':return _incoming(db,user,row,payment_link.amount_cents,evidence_id,payment=payment_link)
    if not correction or not original_payment or payment_link.original_id!=original_payment.id:raise HTTPException(409,'退款须使用已批准的服务终止原款路径')
    guard_source_adjustment(db,row);originals=_rows(db,ServiceTenderSlice,payment_link_id=original_payment.id)
    if payment_link.amount_cents!=sum(_unrefunded(db,t) for t in originals):raise HTTPException(409,'误记更正须完整冲正该原收款剩余分配')
    result=[]
    for t in originals:
        if _spent(db,t)>0:raise HTTPException(409,'原代缴资金已实际支付第三方，请先按原路径追回后更正')
        remaining=_unrefunded(db,t)
        if remaining:result.append(_record_tender(db,user,row,-remaining,evidence_id,payment_link,original=t))
    return result
def record_advance_credit(db,user,row,credit_link,evidence_id):
    if credit_link.case_id!=row.id or credit_link.amount_cents<=0 or _first(db,ServiceTenderSlice,credit_link_id=credit_link.id):raise HTTPException(409,'预收抵用来源或已分配事实不一致')
    return _incoming(db,user,row,credit_link.amount_cents,evidence_id,credit=credit_link)
def refund_available(db,row,original_payment_id):
    return [dict(tender_id=t.id,line_id=t.line_id,bucket=t.bucket,original_paid_cents=t.amount_cents,refunded_cents=t.amount_cents-_unrefunded(db,t),reserved_cents=_reserved_refund(db,t),available_cents=max(0,_unrefunded(db,t)-_spent(db,t)-_reserved_refund(db,t))) for t in _rows(db,ServiceTenderSlice,case_id=row.id,payment_link_id=original_payment_id) if t.amount_cents>0]
def _sync(db,user,row):
    if row.state=='cancelled':return
    q=_quote(db,row) if row.data.get('service_quote_id') else None;p=_active_plan(db,row);desired={}
    if p:
        if not _first(db,ServiceTerminationApproval,plan_id=p.id):desired['termination_approve']=('独立复核终止及原款方案','manager',{p.actor_id})
        elif not _first(db,ServiceTerminationConsent,plan_id=p.id):desired['consent']=('记录客户同意终止方案','front',set())
        else:desired['termination_apply']=('核对实际代缴后生效终止费用','finance',set())
    elif not q:desired['quote']=('核对服务明细并报价','front',set())
    elif not _first(db,ServicePriceApproval,quote_id=q.id):desired['approve']=('独立复核当前服务价格','manager',{q.actor_id,row.created_by})
    elif not _first(db,ServiceAuthorization,quote_id=q.id):desired['authorize']=('登记客户当前版服务授权','front',set())
    else:
        if not _terminated(db,row) and any(not _first(db,ServiceFulfillment,case_id=row.id,line_key=l.line_key) for l in _lines(db,row)):desired['handle']=('办理服务并跟进补件及实际结果','front',set())
        if customer_due(db,row)>0:desired['receive']=('核对服务费及代缴本金实际到账','finance',set())
        unused=[t for t in _rows(db,ServiceTenderSlice,case_id=row.id,bucket='pass') if t.amount_cents>0 and _unrefunded(db,t)-_spent(db,t)>0]
        if unused and not _terminated(db,row):
            if any(not _first(db,ServiceFulfillment,case_id=row.id,line_key=t.line_key) for t in unused):desired['pass']=('按原客户资金办理第三方代缴','finance',set())
            else:desired['resolve_pass']=('第三方已退款，请协商原本金返还方案','front',set())
        elif unused and _terminated(db,row) and not any(k.startswith('refund_') for k in desired):desired['resolve_pass']=('核对终止后第三方退回，追加原本金退款方案','front',set())
    for plan in _rows(db,ServiceTermination,case_id=row.id):
        if _first(db,ServiceTerminationApplication,plan_id=plan.id) and any(x['amount_cents']>sum(f.amount_cents for f in _rows(db,ServiceRefund,plan_id=plan.id,original_tender_id=x['tender_id'])) for x in plan.returns):desired['refund_'+str(plan.id)]=('按批准方案退原客户款','finance',set())
    for t in _rows(db,Task,case_id=row.id):
        if t.status=='open' and t.key.startswith('serviceorder_') and t.key.removeprefix('serviceorder_') not in desired:flow.finish_task(db,row,t.key,user)
    for key,(title,role,excluded) in desired.items():
        if role=='manager':_manager(db,row,'serviceorder_'+key,title,excluded)
        else:
            role=(_one(db,ServiceOrder,row.id).subtype=='agency' and 'sales' or 'service') if role=='front' else role
            current=_first(db,Task,case_id=row.id,key='serviceorder_'+key,status='open')
            flow.ensure_task(db,row,'serviceorder_'+key,title,role,assignee=current.assignee_id if current else row.owner_id if role in {'sales','service'} else None,due=current.due_date if current else row.due_date,reopen=True)
    row.state='completed' if not desired else 'approval' if any(r=='manager' for _,r,_ in desired.values()) else 'working'
    row.completed_date=today() if row.state=='completed' else None
def sync_after_finance(db,user,row,evidence_id=None):
    _sync(db,user,row)
    from .invoice_service import sync_source
    sync_source(db,user,row)

def create(db,user,key,v):
    _role(user,FRONT)
    def run():
        customer=_one(db,Customer,v['customer_id']);source=None;vehicle={}
        if user.role=='sales' and customer.owner_id not in {None,user.id}:raise HTTPException(403,'只能为本人负责客户建立服务')
        if v.get('source_order_id'):
            source=flow.get_case(db,user,v['source_order_id'])
            if source.kind!='order' or source.customer_id!=customer.id or source.state=='cancelled':raise HTTPException(409,'关联销售必须是同店、同客户的有效原单')
            if source.version!=v.get('source_version'):raise HTTPException(409,'原销售版本已变化，请刷新')
            if v['delivery_blocking'] and source.data.get('delivered_at'):raise HTTPException(409,'已交付销售不能追加交车前条件')
            from .aftercare_service import guard_source_action
            guard_source_action(db,user,source,'service_orders');source.updated_at=utcnow();db.flush()
            if source.flow_version in {3,4}:
                from .sales_quote_service import guard_source_action as sales_guard
                sales_guard(db,user,source,'service_orders')
        elif v['delivery_blocking']:raise HTTPException(422,'只有明确关联销售才可约定交车前办结')
        if v.get('customer_vehicle_id'):
            from .customer_service_models import CustomerVehicle
            cv=_one(db,CustomerVehicle,v['customer_vehicle_id'])
            if not cv.active or cv.customer_id!=customer.id:raise HTTPException(409,'客户车辆必须属于所选本店客户')
            vehicle={'customer_vehicle_id':cv.id,'vin':cv.vin,'plate':cv.plate,'model_name':cv.model_name}
        row=Case(number='HKS'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind=v['subtype'],flow_version=3 if v['subtype']=='agency' else 2,state='pending',title=customer.name+' · '+('代办服务' if v['subtype']=='agency' else '其它客户服务'),parent_id=source.id if source else None,customer_id=customer.id,owner_id=user.id,created_by=user.id,business_date=today(),due_date=date.fromisoformat(v['due_date']),data={})
        db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(ServiceOrder(id=row.id,subtype=v['subtype'],source_order_id=source.id if source else None,delivery_blocking=v['delivery_blocking'],customer_name=customer.name,vehicle_snapshot=vehicle,reason=v['reason'],created_by=user.id));db.flush();_sync(db,user,row);flow.log_event(db,user,row,'serviceorder_create','建立明细服务');db.flush();return describe(db,user,row)
    return _execute(db,user,key,'create',v,run)

def _quote_command(db,user,row,v):
    if _terminated(db,row) or _active_plan(db,row):raise HTTPException(409,'已终止或正在终止的服务不能重新报价')
    old=_lines(db,row);facts=bool(_rows(db,ServiceTenderSlice,case_id=row.id) or _rows(db,ServiceSubmission,case_id=row.id) or _rows(db,ServiceFulfillment,case_id=row.id))
    data=[];seen=set()
    for x in v['lines']:
        k=x['line_key']
        if k in seen:raise HTTPException(422,'明细编号不能重复')
        seen.add(k);bucket=x['bucket'];payee={};pid=iid=aid=None
        if bucket=='pass':
            p=_one(db,ServicePayee,x.get('payee_id',0))
            if not p.active:raise HTTPException(422,'第三方代缴单位已停用')
            if not x['name'].strip() or x.get('agency_project_id') or x.get('income_item_id'):raise HTTPException(422,'代缴本金须明确事项，不能混用服务费项目')
            pid=p.id;code=p.code;name=x['name'];unit='项';payee={'name':p.name,'account_name':p.account_name,'account_reference':p.account_reference}
        elif row.kind=='agency':
            if x.get('payee_id') or x.get('income_item_id'):raise HTTPException(422,'代办收费不能混用代缴或其它收入主档')
            from .master_data import require_active
            p=require_active(db,'agency_projects',x.get('agency_project_id',0));aid=p.id;code=p.code;name=p.name;unit='项'
        else:
            if x.get('payee_id') or x.get('agency_project_id'):raise HTTPException(422,'其它客户服务不能混用代缴或代办主档')
            p=_one(db,ServiceIncomeItem,x.get('income_item_id',0))
            if not p.active:raise HTTPException(422,'其它客户服务项目已停用')
            iid=p.id;code=p.code;name=p.name;unit=p.unit
        raw=(x['quantity_milli']*x['unit_price_cents']+500)//1000
        if raw>1_000_000_000_000:raise HTTPException(422,'单项金额超过本系统可办理上限，请核对数量和单价')
        data.append(dict(line_key=k,bucket=bucket,agency_project_id=aid,income_item_id=iid,payee_id=pid,code=code,name=name,unit=unit,payee_snapshot=payee,quantity_milli=x['quantity_milli'],unit_price_cents=x['unit_price_cents'],discount_cents=0,amount_cents=raw,due_date=date.fromisoformat(x['due_date'])))
    previous={l.line_key:l for l in old}
    if facts:
        if not set(previous)<=seen:raise HTTPException(409,'已有实际办理或资金明细不能删除，请走终止保留费方案')
        for d in data:
            if d['line_key'] in previous:
                p=previous[d['line_key']]
                if any(d[k]!=getattr(p,k) for k in ('bucket','agency_project_id','income_item_id','payee_id','quantity_milli','unit_price_cents','due_date','payee_snapshot')):raise HTTPException(409,'已有事实的原行不能改价改项；增项请使用新明细编号')
                d['discount_cents']=p.discount_cents;d['amount_cents']=p.amount_cents
    candidates=[(i,d['amount_cents']) for i,d in enumerate(data) if d['bucket']=='fee' and (not facts or d['line_key'] not in previous)]
    for i,amount in _split(v['discount_cents'],candidates):data[i]['discount_cents']=amount;data[i]['amount_cents']-=amount
    fee=sum(x['amount_cents'] for x in data if x['bucket']=='fee');principal=sum(x['amount_cents'] for x in data if x['bucket']=='pass')
    if fee+principal<=0:raise HTTPException(422,'报价应有正数客户收费或代缴本金')
    if fee+principal>1_000_000_000_000:raise HTTPException(422,'服务单合计超过可办理金额上限，请核对明细')
    revision=len(_rows(db,ServiceQuote,case_id=row.id))+1
    q=ServiceQuote(case_id=row.id,revision=revision,fee_cents=fee,pass_cents=principal,discount_cents=sum(x['discount_cents'] for x in data),digest=flow.request_digest('service_quote',[{k:(val.isoformat() if isinstance(val,date) else val) for k,val in d.items()} for d in data]),reason=v['reason'],actor_id=user.id)
    db.add(q);db.flush()
    for d in data:db.add(ServiceLine(quote_id=q.id,**d))
    row.amount_cents=fee+principal;flow.set_data(row,service_quote_id=q.id);db.flush()

def _account_for_tender(db,t):
    if t.payment_link_id:return _one(db,PaymentLink,t.payment_link_id).account_id
    from .business_finance_models import FinanceCreditLink,FinanceAdvanceEntry,FinanceAdvance
    credit=_one(db,FinanceCreditLink,t.credit_link_id);entry=_one(db,FinanceAdvanceEntry,credit.entry_id);return _one(db,FinanceAdvance,entry.advance_id).account_id
def _cash(db,user,row,v,direction,category,account_id,*,original_cash_id=None):
    a=_one(db,Account,v['account_id'])
    if not a.active or a.id!=account_id:raise HTTPException(409,'必须使用原资金账户确认实际收支')
    if db.scalar(select(CashEntry.id).where(CashEntry.account==a.name,CashEntry.voucher_no==v['reference'])):raise HTTPException(409,'此账户凭证号已经登记，请核对真实银行流水')
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,row,a.id,today(),original_cash_id=original_cash_id)
    a.updated_at=utcnow();cash=CashEntry(doc_no='SO-'+uuid.uuid4().hex[:20],business_date=today(),created_by=user.id,approval_state='approved',direction=direction,category=category,amount_cents=v['amount_cents'],account=a.name,counterparty=row.title,payment_method=a.account_type,voucher_no=v['reference'],note='明细服务 '+row.number)
    db.add(cash);db.flush();record_cash_entity(db,user,row,cash,a.id,original_cash_id=original_cash_id);return cash
def _plan(db,row,key):
    p=_one(db,ServiceTermination,key)
    if p.case_id!=row.id or _first(db,ServiceTerminationCancellation,plan_id=p.id):raise HTTPException(409,'终止方案不属于本单或已经撤回')
    return p
def _refund_limit(db,row,p,t):
    selected=sum(x['amount_cents'] for x in p.returns if x['tender_id']==t.id)
    done=sum(x.amount_cents for x in _rows(db,ServiceRefund,plan_id=p.id,original_tender_id=t.id))
    return min(selected-done,_unrefunded(db,t)-_spent(db,t)-_reserved_refund(db,t,p.id))
def assert_advance_return(db,user,row,credit_link,amount,evidence_id,plan_id):
    _role(user,FINANCE);get_order(db,user,row.id);p=_plan(db,row,plan_id)
    if not _first(db,ServiceTerminationApplication,plan_id=p.id) or credit_link.case_id!=row.id or amount<=0:raise HTTPException(409,'预收退抵须引用本单已生效终止原款方案')
    flow.file_exists(db,row,evidence_id,'receipt')
    if amount>sum(_refund_limit(db,row,p,t) for t in _rows(db,ServiceTenderSlice,credit_link_id=credit_link.id) if t.amount_cents>0):raise HTTPException(409,'退抵超过原预收尚可退额度')
    return True

def _termination(db,user,row,v):
    q=_quote(db,row,True)
    if _active_plan(db,row) or _reservation(db,row):raise HTTPException(409,'请先结束现有终止方案或释放预收抵用占额')
    lines=_lines(db,row);keys={l.line_key for l in lines}
    if {x['line_key'] for x in v['lines']}!=keys or len(v['lines'])!=len(keys):raise HTTPException(422,'终止方案须逐项核对全部原收费及代缴本金')
    frozen=[];by={x['line_key']:x for x in v['lines']}
    for l in lines:
        base=_line_net(db,row,l);retained=by[l.line_key]['retained_cents']
        if retained>base:raise HTTPException(409,'保留费不能超过当前原项目净收费')
        spent=sum(_spent(db,t) for t in _rows(db,ServiceTenderSlice,case_id=row.id,line_key=l.line_key) if t.amount_cents>0)
        if l.bucket=='pass' and retained!=spent:raise HTTPException(409,'终止后仅可保留已实际发生的第三方净代缴；其余本金须按原客户款退回')
        frozen.append(dict(line_key=l.line_key,line_id=l.id,bucket=l.bucket,base_cents=base,retained_cents=retained,credit_cents=base-retained,fulfilled=bool(_first(db,ServiceFulfillment,case_id=row.id,line_key=l.line_key))))
    returns=[];seen=set()
    for x in v['returns']:
        t=_one(db,ServiceTenderSlice,x['tender_id'])
        if t.case_id!=row.id or t.amount_cents<=0 or t.id in seen:raise HTTPException(409,'退款选择必须是本单未重复的原客户资金分配')
        seen.add(t.id)
        if x['amount_cents']>_unrefunded(db,t)-_spent(db,t)-_reserved_refund(db,t):raise HTTPException(409,'退款超过原客户款未使用及未退余额')
        returns.append(dict(tender_id=t.id,amount_cents=x['amount_cents']))
    for l in frozen:
        required=max(0,_line_paid(db,row,_line(db,row,l['line_key']))-l['retained_cents'])
        chosen=sum(x['amount_cents'] for x in returns if _one(db,ServiceTenderSlice,x['tender_id']).line_key==l['line_key'])
        if chosen!=required:raise HTTPException(409,'每项原款退款选择必须等于已收超过保留费的金额，不能挪用其它项目资金')
    if _terminated(db,row) and not any(x['credit_cents'] for x in frozen):raise HTTPException(409,'原终止已确认全部保留费用，没有新的费用调整')
    _proof(db,user,row,v['evidence_id']);p=ServiceTermination(case_id=row.id,quote_id=q.id,revision=len(_rows(db,ServiceTermination,case_id=row.id))+1,lines=frozen,returns=returns,digest=flow.request_digest('service_termination',[frozen,returns]),reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id);db.add(p);db.flush()

def command(db,user,key,request_id,version,action,v):
    _role(user,ROLES[action])
    def run():
        row=get_order(db,user,key)
        if row.version!=version:raise HTTPException(409,'服务版本已变化，请刷新核对')
        if row.state=='cancelled':raise HTTPException(409,'已取消服务不能继续办理')
        row.updated_at=utcnow();_touch_parent(db,row);db.flush()
        order=_one(db,ServiceOrder,row.id)
        if order.source_order_id:
            from .sales_quote_service import guard_child_action
            guard_child_action(db,user,_one(db,Case,order.source_order_id),'service_orders_'+action)
        taskkey={'quote':'quote','approve':'approve','authorize':'authorize','receive':'receive','submit':'handle','external_result':'handle','fulfill':'handle','disburse':'pass','termination_approve':'termination_approve','consent':'consent','termination_apply':'termination_apply'}.get(action)
        if action in {'quote','termination','cancel','termination_cancel'} and user.role!='admin' and user.id!=row.owner_id and user.role!='manager' and not any(t.assignee_id==user.id and t.key.startswith('serviceorder_') for t in _rows(db,Task,case_id=row.id,status='open')):raise HTTPException(403,'请由本单经办人或明确接手待办的人提出服务变更或终止')
        if taskkey and not (action=='quote' and row.data.get('service_quote_id')):_task(db,user,row,'serviceorder_'+taskkey)
        if action=='quote':_quote_command(db,user,row,v)
        elif action=='approve':
            q=_quote(db,row)
            if user.id in {q.actor_id,row.created_by}:raise HTTPException(403,'申请人和报价人不能审批自己的价格，管理员也须独立复核')
            if q.fee_cents<v['minimum_fee_cents'] and not v['allow_below_minimum']:raise HTTPException(409,'当前服务费低于主管明确的最低金额，须明确批准本版低价原因')
            _proof(db,user,row,v['evidence_id']);db.add(ServicePriceApproval(quote_id=q.id,minimum_fee_cents=v['minimum_fee_cents'],allow_below_minimum=v['allow_below_minimum'],reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='authorize':
            q=_quote(db,row)
            if v['quote_id']!=q.id or not _first(db,ServicePriceApproval,quote_id=q.id):raise HTTPException(409,'客户授权必须关联当前已批准报价')
            _proof(db,user,row,v['evidence_id']);db.add(ServiceAuthorization(quote_id=q.id,evidence_id=v['evidence_id'],actor_id=user.id))
        elif action in {'submit','external_result','fulfill'}:
            q=_quote(db,row,True)
            if _terminated(db,row) or _active_plan(db,row):raise HTTPException(409,'终止期间不能继续新增服务事实')
            l=_line(db,row,v['line_key'])
            if _first(db,ServiceFulfillment,case_id=row.id,line_key=l.line_key):raise HTTPException(409,'此项目已经实际办结')
            _proof(db,user,row,v['evidence_id'])
            submissions=_rows(db,ServiceSubmission,case_id=row.id,line_key=l.line_key);last=submissions[-1] if submissions else None;result=_first(db,ServiceExternalResult,submission_id=last.id) if last else None
            if action=='submit':
                if row.kind!='agency':raise HTTPException(409,'其它服务不需要虚构外部代办提交')
                if date.fromisoformat(v['submitted_on'])>today():raise HTTPException(422,'实际提交日期不能晚于今天')
                if last and (not result or result.outcome!='need_documents' or v.get('supplement_result_id')!=result.id):raise HTTPException(409,'已有提交须先取得真实补件要求，再引用该要求追加提交')
                if not last and v.get('supplement_result_id'):raise HTTPException(409,'首次提交不能借用其它补件结果')
                db.add(ServiceSubmission(case_id=row.id,quote_id=q.id,line_key=l.line_key,supplement_result_id=v.get('supplement_result_id'),external_reference=v['external_reference'],submitted_on=date.fromisoformat(v['submitted_on']),evidence_id=v['evidence_id'],actor_id=user.id))
            elif action=='external_result':
                if not last or v['submission_id']!=last.id or result:raise HTTPException(409,'请选择本项目尚未登记结果的最新实际提交')
                db.add(ServiceExternalResult(submission_id=last.id,outcome=v['outcome'],result=v['result'],business_date=today(),evidence_id=v['evidence_id'],actor_id=user.id))
            else:
                if row.kind=='agency' and (not result or result.outcome!='approved'):raise HTTPException(409,'代办须取得实际批准结果；拒绝和补件不能标为办结')
                if l.bucket=='pass' and sum(_spent(db,t) for t in _rows(db,ServiceTenderSlice,case_id=row.id,line_key=l.line_key) if t.amount_cents>0)!=_line_net(db,row,l):raise HTTPException(409,'代缴项目须与实际第三方净支付金额一致后办结')
                db.add(ServiceFulfillment(case_id=row.id,line_id=l.id,line_key=l.line_key,amount_cents=l.amount_cents,business_date=today(),result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='receive':
            source_finance(db,user,row);_proof(db,user,row,v['evidence_id'],True)
            if v['amount_cents']>customer_due(db,row):raise HTTPException(409,'本次到账超过扣除预收占额的服务尚欠金额')
            p=flow.add_payment(db,user,row,v,amount=v['amount_cents']);record_collection(db,user,row,p,v['evidence_id'])
        elif action in {'disburse','thirdparty_return'}:
            _quote(db,row,True);_proof(db,user,row,v['evidence_id'],True)
            if action=='disburse':
                if _active_plan(db,row) or _terminated(db,row):raise HTTPException(409,'终止期间不能新增第三方代缴')
                t=_one(db,ServiceTenderSlice,v['tender_id']);original=None
                if t.case_id!=row.id or t.bucket!='pass' or t.amount_cents<=0 or v['amount_cents']>_unrefunded(db,t)-_spent(db,t)-_reserved_refund(db,t):raise HTTPException(409,'代缴超过本项原客户本金实际可用余额')
                if _first(db,ServiceFulfillment,case_id=row.id,line_key=t.line_key):raise HTTPException(409,'已办结代缴不能重新付款；第三方退回请追加原客户退款方案')
                direction='out'
            else:
                original=_one(db,ServicePassEntry,v['original_id']);t=_one(db,ServiceTenderSlice,original.tender_id);direction='in'
                if original.case_id!=row.id or original.purpose!='disburse' or v['amount_cents']>original.amount_cents-sum(e.amount_cents for e in _rows(db,ServicePassEntry,original_id=original.id)):raise HTTPException(409,'第三方退回超过原实际代缴尚未返还金额')
            cash=_cash(db,user,row,v,direction,'service_pass_'+('pay' if direction=='out' else 'return'),_account_for_tender(db,t),original_cash_id=original.cash_id if original else None);db.add(ServicePassEntry(case_id=row.id,line_id=t.line_id,line_key=t.line_key,purpose=action,amount_cents=v['amount_cents'],tender_id=t.id,original_id=original.id if original else None,cash_id=cash.id,account_id=v['account_id'],reference=v['reference'],evidence_id=v['evidence_id'],business_date=today(),actor_id=user.id))
        elif action=='termination':_termination(db,user,row,v)
        elif action in {'termination_approve','consent','termination_apply','termination_cancel'}:
            p=_plan(db,row,v['plan_id'])
            if _first(db,ServiceTerminationApplication,plan_id=p.id):raise HTTPException(409,'已生效费用不能撤回或重复生效，请追加原单新方案')
            if p.quote_id!=_quote(db,row).id:raise HTTPException(409,'终止方案报价版本已经变化')
            if action=='termination_cancel':db.add(ServiceTerminationCancellation(plan_id=p.id,reason=v['reason'],actor_id=user.id))
            else:
                _proof(db,user,row,v['evidence_id'],action=='termination_apply')
                if action=='termination_approve':
                    if user.id in {p.actor_id,row.created_by}:raise HTTPException(403,'终止申请人不能审批自己的方案')
                    for x in p.returns:
                        t=_one(db,ServiceTenderSlice,x['tender_id'])
                        if x['amount_cents']>_unrefunded(db,t)-_spent(db,t)-_reserved_refund(db,t):raise HTTPException(409,'原资金可退余额已变化，请重拟方案')
                    db.add(ServiceTerminationApproval(plan_id=p.id,evidence_id=v['evidence_id'],actor_id=user.id))
                elif action=='consent':
                    if not _first(db,ServiceTerminationApproval,plan_id=p.id):raise HTTPException(409,'请先独立批准终止方案')
                    db.add(ServiceTerminationConsent(plan_id=p.id,evidence_id=v['evidence_id'],actor_id=user.id))
                else:
                    if not _first(db,ServiceTerminationConsent,plan_id=p.id):raise HTTPException(409,'须先记录客户对保留费及原款退款的同意')
                    application=ServiceTerminationApplication(plan_id=p.id,evidence_id=v['evidence_id'],business_date=today(),actor_id=user.id);db.add(application);db.flush()
                    for x in p.lines:
                        if x['credit_cents']:db.add(ServiceChargeAdjustment(application_id=application.id,case_id=row.id,line_id=x['line_id'],line_key=x['line_key'],bucket=x['bucket'],amount_cents=-x['credit_cents']))
        elif action=='refund':
            p=_plan(db,row,v['plan_id']);t=_one(db,ServiceTenderSlice,v['tender_id']);_task(db,user,row,'serviceorder_refund_'+str(p.id))
            if not _first(db,ServiceTerminationApplication,plan_id=p.id) or t.case_id!=row.id or t.amount_cents<=0 or v['amount_cents']>_refund_limit(db,row,p,t):raise HTTPException(409,'退款超过已生效方案和原款未退款额度')
            _proof(db,user,row,v['evidence_id'],True)
            if t.payment_link_id:
                if not v.get('account_id') or not v.get('reference','').strip():raise HTTPException(422,'真实客户退款必须选择原账户并填写本次独立流水号')
                original=_one(db,PaymentLink,t.payment_link_id);cash=_cash(db,user,row,v,'out','service_customer_refund',original.account_id,original_cash_id=original.cash_id)
                link=PaymentLink(case_id=row.id,cash_id=cash.id,original_id=original.id,account_id=original.account_id,direction='out',amount_cents=v['amount_cents'],reference=v['reference'],business_date=today());db.add(link);db.flush();reverse=_record_tender(db,user,row,-v['amount_cents'],v['evidence_id'],payment=link,original=t)
            else:
                from .business_finance_models import FinanceCreditLink
                from .business_finance_sources import restore_service_credit
                credit=restore_service_credit(db,user,row,_one(db,FinanceCreditLink,t.credit_link_id),v['amount_cents'],v['evidence_id'],p.id)
                reverse=_record_tender(db,user,row,-v['amount_cents'],v['evidence_id'],credit=credit,original=t)
            db.add(ServiceRefund(plan_id=p.id,original_tender_id=t.id,reversal_tender_id=reverse.id,amount_cents=v['amount_cents'],evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='cancel':
            if _rows(db,ServiceTenderSlice,case_id=row.id) or _rows(db,ServiceSubmission,case_id=row.id) or _rows(db,ServiceFulfillment,case_id=row.id) or _reservation(db,row):raise HTTPException(409,'已有资金、实际提交或履约不能普通取消，请走终止保留费及原款退款')
            row.state='cancelled';flow.close_tasks(db,row,user)
        db.flush();_sync(db,user,row);flow.log_event(db,user,row,'serviceorder_'+action,LABELS[action],detail=v)
        from .invoice_service import sync_source
        sync_source(db,user,row);db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,action,{'case_id':key,'version':version,'values':v},run)

def _serialize(obj):
    return {c.name:(getattr(obj,c.name).isoformat() if isinstance(getattr(obj,c.name),date) else getattr(obj,c.name)) for c in obj.__table__.columns if c.name!='store_id'}
def describe(db,user,row):
    order=_one(db,ServiceOrder,row.id);q=_quote(db,row) if row.data.get('service_quote_id') else None
    lines=[]
    for l in _lines(db,row):
        d=_serialize(l);d.update(charge_cents=_line_net(db,row,l),paid_cents=_line_paid(db,row,l),fulfilled=bool(_first(db,ServiceFulfillment,case_id=row.id,line_key=l.line_key)));lines.append(d)
    tenders=[]
    for t in _rows(db,ServiceTenderSlice,case_id=row.id):
        d=_serialize(t)
        if t.amount_cents>0:d.update(available_cents=max(0,_unrefunded(db,t)-_spent(db,t)-_reserved_refund(db,t)),unrefunded_cents=_unrefunded(db,t),spent_cents=_spent(db,t),account_id=_account_for_tender(db,t))
        tenders.append(d)
    plans=[]
    for p in _rows(db,ServiceTermination,case_id=row.id):
        d=_serialize(p);d.update(approved=bool(_first(db,ServiceTerminationApproval,plan_id=p.id)),consented=bool(_first(db,ServiceTerminationConsent,plan_id=p.id)),applied=bool(_first(db,ServiceTerminationApplication,plan_id=p.id)),cancelled=bool(_first(db,ServiceTerminationCancellation,plan_id=p.id)),refunds=[_serialize(x) for x in _rows(db,ServiceRefund,plan_id=p.id)]);plans.append(d)
    submissions=_rows(db,ServiceSubmission,case_id=row.id);results=[_serialize(r) for s in submissions for r in _rows(db,ServiceExternalResult,submission_id=s.id)]
    tasks=[dict(id=t.id,key=t.key,title=t.title,assignee_id=t.assignee_id,status=t.status) for t in _rows(db,Task,case_id=row.id)]
    available=[a for a,roles in ROLES.items() if user.role in roles and row.state!='cancelled']
    history=[]
    for old in _rows(db,ServiceQuote,case_id=row.id):
        a=_first(db,ServicePriceApproval,quote_id=old.id);consent=_first(db,ServiceAuthorization,quote_id=old.id)
        history.append(dict(quote=_serialize(old),lines=[_serialize(l) for l in _rows(db,ServiceLine,quote_id=old.id)],approval=_serialize(a) if a else None,authorization=_serialize(consent) if consent else None))
    return dict(id=row.id,number=row.number,kind=row.kind,version=row.version,state=row.state,title=row.title,owner_id=row.owner_id,due_date=row.due_date.isoformat(),order=_serialize(order),quote=_serialize(q) if q else None,quote_history=history,quote_approved=bool(q and _first(db,ServicePriceApproval,quote_id=q.id)),summary=source_summary(db,row),lines=lines,tenders=tenders,submissions=[_serialize(s) for s in submissions],results=results,fulfillments=[_serialize(f) for f in _rows(db,ServiceFulfillment,case_id=row.id)],pass_entries=[_serialize(e) for e in _rows(db,ServicePassEntry,case_id=row.id)],plans=plans,tasks=tasks,actions=available)
def list_orders(db,user,page=1):
    single_store(db);_role(user,READ);rows=list(db.scalars(flow.case_query(user).join(ServiceOrder,ServiceOrder.id==Case.id).order_by(Case.id.desc()).offset((page-1)*30).limit(30)))
    return {'rows':[dict(id=r.id,number=r.number,title=r.title,state=r.state,kind=r.kind,version=r.version) for r in rows],'page':page}
def catalog(db,user):
    single_store(db);_role(user,READ)
    from .master_models import AgencyProject
    from .customer_service_models import CustomerVehicle
    customers=list(db.scalars(select(Customer).where(Customer.owner_id==user.id))) if user.role=='sales' else list(db.scalars(select(Customer)))
    return dict(customers=[dict(id=c.id,name=c.name) for c in customers],projects=[_serialize(x) for x in db.scalars(select(AgencyProject).where(AgencyProject.active==True))],income_items=[_serialize(x) for x in db.scalars(select(ServiceIncomeItem).where(ServiceIncomeItem.active==True))],payees=[_serialize(x) for x in db.scalars(select(ServicePayee).where(ServicePayee.active==True))],vehicles=[dict(id=x.id,customer_id=x.customer_id,vin=x.vin,plate=x.plate) for x in db.scalars(select(CustomerVehicle).where(CustomerVehicle.active==True,CustomerVehicle.customer_id.in_([c.id for c in customers])))],accounts=[dict(id=x.id,name=x.name) for x in db.scalars(select(Account).where(Account.active==True))],sources=[dict(id=r.id,number=r.number,customer_id=r.customer_id,version=r.version) for r in db.scalars(flow.case_query(user).where(Case.kind=='order',Case.state!='cancelled'))])
def master(db,user,key,kind,v):
    _role(user,MANAGE)
    def run():
        model={'payees':ServicePayee,'income-items':ServiceIncomeItem}[kind];obj=model(**v);db.add(obj);db.flush();return _serialize(obj)
    return _execute(db,user,key,'master_'+kind,v,run)
