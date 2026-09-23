"""Single-store insurance commands with separate external facts and principal."""
import uuid
from copy import deepcopy
from datetime import date,datetime
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import today,utcnow
from .models import Vehicle
from .flow_models import Case,Customer,Task,FileAsset,PaymentLink
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .insurance_models import *

READ={'admin','manager','sales','service','finance','auditor'}
FRONT={'admin','sales','service'};MANAGE={'admin','manager'};FINANCE={'admin','finance'}
ROLES={**{a:FRONT for a in ('quote','authorize','submit','result','termination','termination_consent')},
       **{a:MANAGE for a in ('review','termination_review','commission_review')},
       **{a:FINANCE for a in ('receive','disburse','insurer_return','direct_paid','direct_return','termination_apply','refund','commission','commission_receive','commission_return')},
       **{a:FRONT|MANAGE for a in ('quote_cancel','termination_cancel','cancel')}}
LABELS={'quote':'提交保险报价新版本','review':'独立复核保险核价','authorize':'登记客户本版授权','quote_cancel':'撤回未执行核价',
 'submit':'登记实际投保或补件提交','result':'登记保险公司真实结果','receive':'登记代收保费','disburse':'按原资金实际代缴',
 'insurer_return':'保险公司退回原代缴','direct_paid':'登记客户直接支付保险公司','direct_return':'登记保险公司直接退客户',
 'termination':'申请撤保及保留保费','termination_review':'独立复核撤保方案','termination_consent':'登记客户本版撤保同意',
 'termination_apply':'生效已批准撤保金额','termination_cancel':'撤回未生效撤保方案','refund':'按原路退客户保费',
 'commission':'申请确认实际佣金','commission_review':'独立确认实际佣金','commission_receive':'登记实际佣金到账','commission_return':'退回原佣金超收','cancel':'取消未执行保险申请'}
def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此保险步骤')
def _one(db,model,key):
    row=db.scalar(select(model).where((model.id if hasattr(model,'id') else model.case_id)==key))
    if not row:raise HTTPException(404,'本店保险关联记录不存在')
    return row
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _first(db,model,**kw):return db.scalar(select(model).filter_by(**kw))
def is_detailed(row):return row.kind=='insurance' and row.flow_version==3
def can_read(db,user,row):
    if user.role not in READ or getattr(user,'_aggregate_scope',False):return False
    if user.role=='sales':
        parent=flow.scoped_get(db,Case,row.parent_id) if row.parent_id else None
        return row.owner_id==user.id or row.created_by==user.id or bool(parent and parent.owner_id==user.id) or bool(_first(db,Task,case_id=row.id,assignee_id=user.id,status='open'))
    return True
def get_order(db,user,key):
    single_store(db);_role(user,READ);row=flow.get_case(db,user,key)
    if not is_detailed(row):raise HTTPException(404,'本店独立保险单不存在')
    _one(db,InsuranceOrder,row.id);return row
def _proof(db,user,row,key,financial=False):
    asset=flow.file_exists(db,row,key,'receipt' if financial else 'authorization')
    if asset.generated or not can_file(user,row,asset):raise HTTPException(403,'须上传本保险单本次实际原件，生成报价不能代替实际确认')
    if any(db.scalar(select(m.id).join(FileAsset,FileAsset.id==m.evidence_id).where(FileAsset.case_id==row.id,FileAsset.sha256==asset.sha256).limit(1)) for m in IMMUTABLE if hasattr(m,'evidence_id')):raise HTTPException(409,'此原件已用于另一办理事实，请提交本次实际凭据')
    return asset
def _date(value):
    result=date.fromisoformat(value) if isinstance(value,str) else value
    if not date(2000,1,1)<=result<=today():raise HTTPException(422,'实际发生日期不能晚于今天或早于支持范围')
    return result
def _execute(db,user,key,action,payload,callback):
    single_store(db);digest=flow.request_digest('insurance_'+action,payload)
    try:
        old=_first(db,InsuranceRequest,request_key=key)
        if old:
            if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'此请求编号已用于其他人员或内容，请核对原结果')
            # A task may have moved since the original command. A receipt is not
            # a permanent bypass around today's case-read authorization.
            get_order(db,user,old.result['id'])
            return safe_description(old.result,user)
        result=callback();db.flush();db.add(InsuranceRequest(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'保险版本、原款或账户同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise
    finally:db.info.pop('_observation_vehicle_locks',None)
def _quote(db,row,authorized=False):
    q=_one(db,InsuranceQuote,row.data.get('insurance_quote_id',0))
    if q.case_id!=row.id or _first(db,InsuranceQuoteCancellation,quote_id=q.id):raise HTTPException(409,'保险报价不属于本单或已经撤回')
    if authorized and not _first(db,InsuranceConsent,quote_id=q.id):raise HTTPException(409,'须先取得客户本版核价授权')
    return q
def _policy(db,row):return _first(db,InsuranceResult,case_id=row.id,outcome='issued')
def _previous_policy_id(db,order):
    link=_first(db,InsuranceRenewalLink,case_id=order.id)
    return link.previous_policy_id if link else None
def _applied(db,row):
    return list(db.scalars(select(InsuranceTermination).join(InsuranceTerminationApplication,InsuranceTerminationApplication.plan_id==InsuranceTermination.id).where(InsuranceTermination.case_id==row.id).order_by(InsuranceTermination.id)))
def _active_plan(db,row):
    for p in reversed(_rows(db,InsuranceTermination,case_id=row.id)):
        review=_first(db,InsuranceTerminationReview,plan_id=p.id)
        if not _first(db,InsuranceTerminationCancellation,plan_id=p.id) and not _first(db,InsuranceTerminationApplication,plan_id=p.id) and (not review or review.decision=='approved'):return p
    return None
def _plan(db,row,key):
    p=_one(db,InsuranceTermination,key);review=_first(db,InsuranceTerminationReview,plan_id=key)
    if p.case_id!=row.id or _first(db,InsuranceTerminationCancellation,plan_id=key) or (review and review.decision=='rejected'):raise HTTPException(409,'本次撤保方案已经失效或不属于本单')
    return p
def _reservation(db,row):
    from .business_finance_sources import case_reserved_amount
    return case_reserved_amount(db,row.id)
def _unrefunded(db,t):return t.amount_cents+sum(x.amount_cents for x in _rows(db,InsuranceTender,original_id=t.id))
def _spent(db,t):return sum(x.amount_cents*(1 if x.purpose=='disburse' else -1) for x in _rows(db,InsurancePassEntry,tender_id=t.id))
def _commission(db,row):
    confirmed=list(db.scalars(select(InsuranceCommission).join(InsuranceCommissionReview,InsuranceCommissionReview.confirmation_id==InsuranceCommission.id).where(InsuranceCommission.case_id==row.id,InsuranceCommissionReview.decision=='approved').order_by(InsuranceCommission.id)))
    return confirmed[-1] if confirmed else None
def _commission_pending(db,row):
    return next((r for r in reversed(_rows(db,InsuranceCommission,case_id=row.id)) if not _first(db,InsuranceCommissionReview,confirmation_id=r.id)),None)
def summary(db,row):
    q=_quote(db,row) if row.data.get('insurance_quote_id') else None;applied=_applied(db,row);tenders=_rows(db,InsuranceTender,case_id=row.id)
    premium=applied[-1].retained_cents if applied else q.premium_cents if q else 0
    paid=sum(t.amount_cents for t in tenders);spent=sum(e.amount_cents*(1 if e.purpose=='disburse' else -1) for e in _rows(db,InsurancePassEntry,case_id=row.id))
    direct=sum(e.amount_cents*(1 if e.purpose=='paid' else -1) for e in _rows(db,InsuranceDirectEntry,case_id=row.id))
    collect=bool(q and q.collection_mode=='store_collect');confirmed=_commission(db,row);commission=confirmed.target_cents if confirmed else 0
    actual=sum(x.amount_cents*(1 if x.direction=='in' else -1) for x in _rows(db,InsuranceCommissionPayment,case_id=row.id))
    return dict(premium_cents=premium,quoted_premium_cents=q.premium_cents if q else 0,customer_charge_cents=premium if collect else 0,
        customer_paid_cents=paid,customer_due_cents=max(0,premium-paid-_reservation(db,row)) if collect else 0,
        customer_refund_cents=max(0,paid-premium) if collect else 0,insurer_paid_cents=spent,insurer_due_cents=max(0,premium-spent) if collect else 0,
        insurer_return_due_cents=max(0,spent-premium) if collect else 0,held_principal_cents=paid-spent,direct_net_cents=direct,
        direct_due_cents=max(0,premium-direct) if not collect and q else 0,direct_return_due_cents=max(0,direct-premium) if not collect and q else 0,
        expected_commission_cents=q.expected_commission_cents if q else 0,confirmed_commission_cents=commission,actual_commission_cents=actual,
        commission_due_cents=max(0,commission-actual),commission_return_due_cents=max(0,actual-commission),terminated=bool(applied),issued=bool(_policy(db,row)))
def guard_source_adjustment(db,row,action='adjustment'):
    if not is_detailed(row):return
    if _active_plan(db,row) or _applied(db,row):raise HTTPException(409,'保险正在或已经撤保，请在原保险单办理原款结清')
    if row.state=='cancelled':raise HTTPException(409,'已取消保险不能办理资金')
def source_finance(db,user,row,include_reservations=True):
    get_order(db,user,row.id);guard_source_adjustment(db,row);q=_quote(db,row,True)
    if q.collection_mode!='store_collect':raise HTTPException(409,'客户直付保险公司不能登记门店收款或抵用')
    s=summary(db,row);due=s['customer_due_cents']+(0 if include_reservations else _reservation(db,row))
    return dict(case_id=row.id,number=row.number,kind=row.kind,version=row.version,customer_id=row.customer_id,business_date=row.business_date.isoformat(),allocation_id=None,payer_type='customer',amount_cents=s['customer_charge_cents'],due_cents=due,credit_cents=sum(t.amount_cents for t in _rows(db,InsuranceTender,case_id=row.id) if t.credit_link_id),allocations=[])
def _task(db,user,row,key):
    task=_first(db,Task,case_id=row.id,key='insurance_'+key,status='open')
    if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(409,'请由当前保险待办接手人办理，或先明确交接')
def _manager_task(db,row,key,title,excluded):
    candidates=[u for u in flow.eligible_users(db,'manager',row.store_id) if u.id not in excluded]
    if not candidates:raise HTTPException(409,'须配置另一位主管独立复核，管理员不能审批本人申请')
    existing=_first(db,Task,case_id=row.id,key=key,status='open')
    flow.ensure_task(db,row,key,title,'manager',existing.assignee_id if existing and existing.assignee_id not in excluded else candidates[0].id,reopen=True)
def _sync(db,user,row):
    if row.state=='cancelled':return
    q=_quote(db,row) if row.data.get('insurance_quote_id') else None;p=_active_plan(db,row);s=summary(db,row);desired={}
    if p:
        if not _first(db,InsuranceTerminationReview,plan_id=p.id):desired['termination_review']=('独立核对撤保及原款方案','manager',{p.actor_id})
        elif not _first(db,InsuranceTerminationConsent,plan_id=p.id):desired['termination_consent']=('登记客户本版撤保同意','front',set())
        else:desired['termination_apply']=('生效已批准撤保金额','finance',set())
    elif not q:desired['quote']=('核对险种和保险公司报价','front',set())
    else:
        review=_first(db,InsuranceReview,quote_id=q.id)
        if not review:desired['review']=('独立复核本版保险方案','manager',{q.actor_id})
        elif review.decision=='rejected':desired['quote']=('重新核对保险方案','front',set())
        elif not _first(db,InsuranceConsent,quote_id=q.id):desired['authorize']=('登记客户本版保险授权','front',set())
        elif not s['terminated']:
            if not s['issued']:desired['handle']=('投保提交、补件与实际出保','front',set())
            if s['customer_due_cents']:desired['receive']=('核对客户实际保费到账','finance',set())
            if s['insurer_due_cents']:desired['disburse']=('按本单原款实际代缴保费','finance',set())
            if s['direct_due_cents']:desired['direct_paid']=('核对客户直付保险公司证明','finance',set())
    if s['terminated']:
        if s['insurer_return_due_cents']:desired['insurer_return']=('追回保险公司原代缴保费','finance',set())
        if s['customer_refund_cents']:desired['refund']=('按批准方案退原客户款','finance',set())
        if s['direct_return_due_cents']:desired['direct_return']=('核对保险公司直退客户证明','finance',set())
    if s['issued'] or s['terminated']:
        commission=_commission_pending(db,row)
        if commission:desired['commission_review']=('独立核对保险公司实际佣金结算','manager',{commission.actor_id})
        elif not _commission(db,row) or (s['terminated'] and _commission(db,row).created_at<_first(db,InsuranceTerminationApplication,plan_id=_applied(db,row)[-1].id).created_at):desired['commission']=('核对出保或撤保后的实际佣金','finance',set())
        if s['commission_due_cents']:desired['commission_receive']=('核对佣金实际到账','finance',set())
        if s['commission_return_due_cents']:desired['commission_return']=('退回原超收佣金','finance',set())
    for t in _rows(db,Task,case_id=row.id):
        if t.status=='open' and t.key.startswith('insurance_') and t.key[10:] not in desired:flow.finish_task(db,row,t.key,user)
    for key,(title,role,excluded) in desired.items():
        if role=='manager':_manager_task(db,row,'insurance_'+key,title,excluded)
        else:
            role='service' if role=='front' else role;old=_first(db,Task,case_id=row.id,key='insurance_'+key,status='open')
            flow.ensure_task(db,row,'insurance_'+key,title,role,old.assignee_id if old else row.owner_id if role=='service' else None,old.due_date if old else row.due_date,reopen=True)
    row.state='completed' if not desired else 'approval' if any(r=='manager' for _,r,_ in desired.values()) else 'working';row.completed_date=today() if not desired else None
def sync_after_finance(db,user,row,evidence_id=None):_sync(db,user,row)

def _guard_renewal_task(db,user,task_id,vehicle_id,version=None):
    from .customer_service_models import CareCase
    from .observation_corrections_service import control_vehicle,guard_reminder_action,sync_vehicle_insurance_bases
    vehicle=control_vehicle(db,user,vehicle_id)
    sync_vehicle_insurance_bases(db,user,vehicle)
    task=db.scalar(select(Case).where(Case.id==task_id).with_for_update(nowait=True).execution_options(populate_existing=True))
    if not task or not flow.can_read(db,user,task):raise HTTPException(404,'本店续保任务不存在或无权办理')
    care=_one(db,CareCase,task.id)
    if care.subtype!='renewal' or care.vehicle_id!=vehicle_id or task.state not in {'pending','working'} or version is not None and task.version!=version:
        raise HTTPException(409,'须明确同客户车辆的在办续保任务及当前版本')
    guard_reminder_action(db,user,task,'insurance_application')
    task.updated_at=utcnow();db.flush();return task

def create(db,user,key,v):
    _role(user,FRONT)
    def operation():
        from .customer_service_models import CustomerVehicle,CareCase
        customer=_one(db,Customer,v['customer_id']);source=None;cv=None;vehicle={}
        if user.role=='sales' and customer.owner_id!=user.id:raise HTTPException(403,'只能为本人负责客户建立保险')
        if v.get('source_order_id'):
            source=flow.get_case(db,user,v['source_order_id'])
            if source.kind!='order' or source.flow_version not in {2,3,4} or source.state=='cancelled' or source.customer_id!=customer.id or source.version!=v.get('source_version'):raise HTTPException(409,'须选择同店同客户的当前有效整车订单版本')
            from .aftercare_service import guard_source_action
            from .sales_quote_service import guard_source_action as quote_guard
            guard_source_action(db,user,source,'insurance');quote_guard(db,user,source,'insurance')
            if not source.vehicle_id:raise HTTPException(409,'关联整车须先明确实际 VIN 配车')
            if v['delivery_blocking'] and source.data.get('dispatched_at'):raise HTTPException(409,'已出库订单不能追加交车前条件')
            car=_one(db,Vehicle,source.vehicle_id);vehicle=dict(vin=car.vin,model_name=car.model,stock_vehicle_id=car.id);source.updated_at=utcnow();db.flush()
        elif v['delivery_blocking'] or v.get('source_version'):raise HTTPException(422,'交车前条件和原单版本须有关联整车订单')
        if v.get('customer_vehicle_id'):
            from .observation_corrections_service import control_vehicle
            cv=control_vehicle(db,user,v['customer_vehicle_id'],active=True)
            if not cv.active or cv.customer_id!=customer.id or (vehicle and vehicle['vin']!=cv.vin):raise HTTPException(409,'客户车辆、原订单及 VIN 必须一致')
            vehicle.update(vin=cv.vin,plate=cv.plate,model_name=cv.model_name)
        if not vehicle:raise HTTPException(422,'请选择客户车辆或已有实际配车的销售原单')
        if v.get('previous_policy_id'):
            previous=_one(db,InsuranceResult,v['previous_policy_id']);original=_one(db,InsuranceOrder,previous.case_id);oldcase=flow.get_case(db,user,previous.case_id)
            if previous.outcome!='issued' or oldcase.customer_id!=customer.id or original.vin!=vehicle['vin']:raise HTTPException(409,'续保原保单必须属于同客户同 VIN')
        if v.get('renewal_task_id'):
            if not cv:raise HTTPException(409,'须明确同客户车辆的在办续保任务及当前版本')
            task=_guard_renewal_task(db,user,v['renewal_task_id'],cv.id,v.get('renewal_version'))
            if task.customer_id!=customer.id:raise HTTPException(409,'续保任务客户与原单不符')
        elif v.get('renewal_version'):raise HTTPException(422,'续保任务版本须与原任务一起提交')
        due=date.fromisoformat(v['due_date'])
        if not today()<=due<=date(2100,1,1):raise HTTPException(422,'办理期限不能早于今天')
        row=Case(number='HKI'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='insurance',flow_version=3,state='pending',title=customer.name+' · 保险核价与结算',parent_id=source.id if source else None,customer_id=customer.id,owner_id=user.id,created_by=user.id,business_date=today(),due_date=due,amount_cents=0,data={})
        db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(InsuranceOrder(id=row.id,source_order_id=source.id if source else None,customer_vehicle_id=cv.id if cv else None,renewal_task_id=v.get('renewal_task_id'),delivery_blocking=v['delivery_blocking'],customer_name=customer.name,vin=vehicle['vin'],vehicle_snapshot=vehicle,reason=v['reason']));db.flush()
        if v.get('previous_policy_id'):db.add(InsuranceRenewalLink(case_id=row.id,previous_policy_id=v['previous_policy_id'],actor_id=user.id));db.flush()
        _sync(db,user,row);flow.log_event(db,user,row,'insurance_create','建立独立保险核价');return describe(db,user,row)
    return _execute(db,user,key,'create',v,operation)
def _quote_command(db,user,row,v):
    from .master_data import require_active
    if _applied(db,row) or _active_plan(db,row) or _reservation(db,row):raise HTTPException(409,'已有撤保或资金占额不能重新核价')
    if _rows(db,InsuranceTender,case_id=row.id) or _rows(db,InsuranceDirectEntry,case_id=row.id) or db.scalar(select(InsuranceSubmission.id).join(InsuranceQuote,InsuranceQuote.id==InsuranceSubmission.quote_id).where(InsuranceQuote.case_id==row.id)):raise HTTPException(409,'已有实际资金或外部提交，请按原保险终止及原路退款，不覆盖原报价')
    insurer=require_active(db,'insurers',v['insurer_id'])
    if insurer.version!=v['insurer_version']:raise HTTPException(409,'保险公司资料版本已变化，请刷新')
    start=date.fromisoformat(v['start_date']);end=date.fromisoformat(v['end_date']);expiry=date.fromisoformat(v['valid_until'])
    if not date(2000,1,1)<=start<=end<=date(2100,1,1) or not today()<=expiry<=date(2100,1,1):raise HTTPException(422,'保险起止日期或确认有效期不正确')
    order=_one(db,InsuranceOrder,row.id)
    previous_id=_previous_policy_id(db,order)
    if previous_id:
        previous=_one(db,InsuranceResult,previous_id);old_submission=_one(db,InsuranceSubmission,previous.submission_id);old_quote=_one(db,InsuranceQuote,old_submission.quote_id)
        if end<=old_quote.end_date:raise HTTPException(409,'续保期限必须晚于明确关联的原保单截止日')
    if len({x['name'].casefold() for x in v['lines']})!=len(v['lines']):raise HTTPException(422,'同名险种请合并核对，不要重复登记')
    premium=sum(x['premium_cents'] for x in v['lines'])
    if premium>1_000_000_000_000:raise HTTPException(422,'保费合计超过支持范围')
    if v['collection_mode']=='store_collect' and (not v['payee_account_name'] or not v['payee_account_reference']):raise HTTPException(422,'门店代缴须先核对并冻结保险公司实际收款户名及账户或缴费识别号')
    old=row.data.get('insurance_quote_id');revision=len(_rows(db,InsuranceQuote,case_id=row.id))+1
    if old and not _first(db,InsuranceQuoteCancellation,quote_id=old):db.add(InsuranceQuoteCancellation(quote_id=old,reason='客户需求重新核价并保留原版',actor_id=user.id))
    snap={k:getattr(insurer,k) for k in ('id','version','code','name','license_number','settlement_days')}
    snap.update(account_name=v['payee_account_name'],account_reference=v['payee_account_reference'])
    facts={**{k:v[k] for k in ('lines','expected_commission_cents','collection_mode','start_date','end_date','valid_until','terms','reason')},'insurer_snapshot':snap,'premium_cents':premium,'revision':revision,'vin':_one(db,InsuranceOrder,row.id).vin}
    q=InsuranceQuote(case_id=row.id,revision=revision,insurer_id=insurer.id,insurer_snapshot=snap,lines=v['lines'],premium_cents=premium,expected_commission_cents=v['expected_commission_cents'],collection_mode=v['collection_mode'],start_date=start,end_date=end,valid_until=expiry,terms=v['terms'],reason=v['reason'],digest=flow.request_digest('insurance_quote',facts),actor_id=user.id)
    db.add(q);db.flush();flow.set_data(row,insurance_quote_id=q.id);row.amount_cents=premium if q.collection_mode=='store_collect' else 0

def command(db,user,key,request_id,version,action,v):
    _role(user,ROLES[action])
    def operation():
        row=get_order(db,user,key);db.scalar(select(Case).where(Case.id==row.id).with_for_update())
        if row.version!=version:raise HTTPException(409,'保险单已变化，请刷新本版金额、原款与任务')
        if row.state=='cancelled':raise HTTPException(409,'保险申请已取消')
        row.updated_at=utcnow();db.flush();order=_one(db,InsuranceOrder,row.id)
        if order.source_order_id:
            parent=_one(db,Case,order.source_order_id);parent.updated_at=utcnow();db.flush()
            from .sales_quote_service import guard_child_action
            guard_child_action(db,user,parent,'insurance_'+action)
        from .insurance_finance import financial_action
        if order.renewal_task_id and action in {'quote','authorize','submit'}:
            _guard_renewal_task(db,user,order.renewal_task_id,order.customer_vehicle_id)
        if action in {'receive','disburse','insurer_return','direct_paid','direct_return','termination','termination_review','termination_consent','termination_apply','termination_cancel','refund','commission','commission_review','commission_receive','commission_return'}:
            financial_action(db,user,row,action,v)
        elif action=='quote':_quote_command(db,user,row,v)
        elif action=='review':
            q=_quote(db,row);_task(db,user,row,'review');_proof(db,user,row,v['evidence_id'])
            if q.actor_id==user.id or _first(db,InsuranceReview,quote_id=q.id):raise HTTPException(409,'报价必须由另一主管复核，不能重复审批')
            if v['decision']=='approved' and q.valid_until<today():raise HTTPException(409,'报价已过确认有效期')
            db.add(InsuranceReview(quote_id=q.id,actor_id=user.id,**v))
        elif action=='authorize':
            q=_quote(db,row);_task(db,user,row,'authorize');_proof(db,user,row,v['evidence_id']);review=_first(db,InsuranceReview,quote_id=q.id)
            if not review or review.decision!='approved' or v['quote_id']!=q.id or v['digest']!=q.digest or q.valid_until<today():raise HTTPException(409,'客户授权须对应已批准且未过期的当前报价及摘要')
            db.add(InsuranceConsent(quote_id=q.id,digest=q.digest,evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='quote_cancel':
            q=_quote(db,row)
            if _rows(db,InsuranceTender,case_id=row.id) or _rows(db,InsuranceDirectEntry,case_id=row.id) or _rows(db,InsuranceSubmission,quote_id=q.id) or _reservation(db,row):raise HTTPException(409,'已有实际资金、外部提交或占额，须走原保险终止')
            db.add(InsuranceQuoteCancellation(quote_id=q.id,reason=v['reason'],actor_id=user.id));flow.set_data(row,insurance_quote_id=None);row.amount_cents=0
        elif action=='submit':
            q=_quote(db,row,True);_task(db,user,row,'handle');_proof(db,user,row,v['evidence_id']);previous=_rows(db,InsuranceSubmission,quote_id=q.id)
            if _applied(db,row) or _active_plan(db,row) or _policy(db,row):raise HTTPException(409,'正在撤保或已出保，不能再次提交投保')
            if previous and not _first(db,InsuranceResult,submission_id=previous[-1].id):raise HTTPException(409,'上一提交尚无保险公司实际结果，请先登记')
            db.add(InsuranceSubmission(quote_id=q.id,external_reference=v['external_reference'],business_date=_date(v['business_date']),evidence_id=v['evidence_id'],actor_id=user.id))
        elif action=='result':
            q=_quote(db,row,True);_task(db,user,row,'handle');_proof(db,user,row,v['evidence_id']);submission=_one(db,InsuranceSubmission,v['submission_id'])
            if submission.quote_id!=q.id or _first(db,InsuranceResult,submission_id=submission.id) or _policy(db,row):raise HTTPException(409,'实际结果须对应本单尚未记录结果的提交')
            if (v['outcome']=='issued')!=bool(v['policy_number']):raise HTTPException(422,'实际出保必须填写保单号；失败或补件不能伪造保单号')
            issued=InsuranceResult(submission_id=submission.id,case_id=row.id,insurer_id=q.insurer_id,outcome=v['outcome'],policy_number=v['policy_number'] or None,result=v['result'],business_date=_date(v['business_date']),evidence_id=v['evidence_id'],actor_id=user.id)
            if v['outcome']=='issued' and order.customer_vehicle_id:
                from .customer_service_models import CustomerVehicle,VehicleObservation
                from .observation_corrections_service import control_vehicle
                cv=control_vehicle(db,user,order.customer_vehicle_id)
                observations=_rows(db,VehicleObservation,vehicle_id=cv.id)
                obs=VehicleObservation(vehicle_id=cv.id,kind='insurance',observed_date=issued.business_date,odometer_km=max([o.odometer_km for o in observations] or [0]),valid_until=q.end_date,source_reference='保险原单 '+row.number+' / '+v['policy_number'],evidence_id=v['evidence_id'],actor_id=user.id)
                db.add(obs);db.flush();issued.observation_id=obs.id
            db.add(issued)
        elif action=='cancel':
            if _rows(db,InsuranceTender,case_id=row.id) or _rows(db,InsuranceDirectEntry,case_id=row.id) or db.scalar(select(InsuranceSubmission.id).join(InsuranceQuote,InsuranceQuote.id==InsuranceSubmission.quote_id).where(InsuranceQuote.case_id==row.id)) or _reservation(db,row):raise HTTPException(409,'已有实际资金、提交或占额，须办理原保险终止')
            row.state='cancelled';row.completed_date=today();flow.close_tasks(db,row,user)
        db.flush()
        if action=='termination_apply':
            from .observation_corrections_service import sync_insurance_basis
            sync_insurance_basis(db,user,row)
        _sync(db,user,row)
        if action=='commission_review':
            from .invoice_service import sync_source as sync_invoice
            sync_invoice(db,user,row)
        flow.log_event(db,user,row,'insurance_'+action,LABELS[action],detail=v);db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,action,{'case_id':key,'version':version,'values':v},operation)

def _serialize(obj):return {c.name:(getattr(obj,c.name).isoformat() if isinstance(getattr(obj,c.name),(date,datetime)) else getattr(obj,c.name)) for c in obj.__table__.columns}

def safe_description(result,user):
    """Project current finance authority, including historical request receipts."""
    result=deepcopy(result);result['financial_visible']=user.role in flow.MANAGEMENT
    if result['financial_visible']:return result
    result['commissions']=[];result['commission_payments']=[];result['pass_entries']=[]
    result['summary']={k:v for k,v in result['summary'].items() if 'commission' not in k or k=='expected_commission_cents'}
    for tender in result['tenders']:
        for key in ('account_id','evidence_id'):tender.pop(key,None)
    for entry in result['direct_entries']:
        for key in ('external_reference','evidence_id'):entry.pop(key,None)
    for plan in result['plans']:
        for refund in plan['refunds']:refund.pop('evidence_id',None)
    return result
def describe(db,user,row):
    from .insurance_finance import account_for_tender,refund_limit
    order=_one(db,InsuranceOrder,row.id);q=_quote(db,row) if row.data.get('insurance_quote_id') else None
    history=[]
    for quote in _rows(db,InsuranceQuote,case_id=row.id):
        review=_first(db,InsuranceReview,quote_id=quote.id);history.append(dict(quote=_serialize(quote),review=_serialize(review) if review else None,authorized=bool(_first(db,InsuranceConsent,quote_id=quote.id)),cancelled=bool(_first(db,InsuranceQuoteCancellation,quote_id=quote.id))))
    plans=[]
    for p in _rows(db,InsuranceTermination,case_id=row.id):
        review=_first(db,InsuranceTerminationReview,plan_id=p.id);plans.append({**_serialize(p),'review':_serialize(review) if review else None,'consented':bool(_first(db,InsuranceTerminationConsent,plan_id=p.id)),'applied':bool(_first(db,InsuranceTerminationApplication,plan_id=p.id)),'cancelled':bool(_first(db,InsuranceTerminationCancellation,plan_id=p.id)),'refunds':[_serialize(r) for r in _rows(db,InsuranceCustomerRefund,plan_id=p.id)]})
    tenders=[{**_serialize(t),'unrefunded_cents':_unrefunded(db,t),'spent_cents':_spent(db,t),'available_cents':_unrefunded(db,t)-_spent(db,t),'account_id':account_for_tender(db,t)} for t in _rows(db,InsuranceTender,case_id=row.id) if t.amount_cents>0]
    submissions=[s for quote in _rows(db,InsuranceQuote,case_id=row.id) for s in _rows(db,InsuranceSubmission,quote_id=quote.id)]
    confirmations=[]
    for c in _rows(db,InsuranceCommission,case_id=row.id):
        review=_first(db,InsuranceCommissionReview,confirmation_id=c.id);confirmations.append({**_serialize(c),'review':_serialize(review) if review else None})
    tasks=[{**_serialize(t),'assignee_name':_one(db,__import__('app.models',fromlist=['User']).User,t.assignee_id).display_name} for t in _rows(db,Task,case_id=row.id)]
    return safe_description(dict(id=row.id,number=row.number,kind=row.kind,flow_version=row.flow_version,version=row.version,state=row.state,title=row.title,customer_id=row.customer_id,owner_id=row.owner_id,due_date=row.due_date.isoformat(),order={**_serialize(order),'previous_policy_id':_previous_policy_id(db,order)},quote=_serialize(q) if q else None,quote_history=history,summary=summary(db,row),plans=plans,tenders=tenders,submissions=[_serialize(x) for x in submissions],results=[_serialize(x) for x in _rows(db,InsuranceResult,case_id=row.id)],pass_entries=[_serialize(x) for x in _rows(db,InsurancePassEntry,case_id=row.id)],direct_entries=[_serialize(x) for x in _rows(db,InsuranceDirectEntry,case_id=row.id)],commissions=confirmations,commission_payments=[_serialize(x) for x in _rows(db,InsuranceCommissionPayment,case_id=row.id)],tasks=tasks,actions=[k for k,v in ROLES.items() if user.role in v and row.state!='cancelled']),user)
def list_orders(db,user,page=1):
    single_store(db);_role(user,READ);rows=list(db.scalars(flow.case_query(user).join(InsuranceOrder,InsuranceOrder.id==Case.id).order_by(Case.id.desc()).offset((page-1)*30).limit(30)))
    return dict(rows=[dict(id=r.id,number=r.number,title=r.title,state=r.state,version=r.version,customer_id=r.customer_id) for r in rows],page=page)
def catalog(db,user,q='',customer_id=None):
    from sqlalchemy import or_
    from .master_models import Insurer
    from .customer_service_models import CustomerVehicle,CareCase
    from .flow_models import Account
    single_store(db);_role(user,READ);stmt=select(Customer)
    if user.role=='sales':stmt=stmt.where(Customer.owner_id==user.id)
    if q:stmt=stmt.where(or_(Customer.name.contains(q),Customer.phone.contains(q)))
    if customer_id:stmt=stmt.where(Customer.id==customer_id)
    total=db.scalar(select(func.count()).select_from(stmt.subquery()));customers=list(db.scalars(stmt.order_by(Customer.id.desc()).limit(30)));ids=[r.id for r in customers]
    insurers=list(db.scalars(select(Insurer).where(Insurer.active.is_(True)).limit(1001)));accounts=list(db.scalars(select(Account).where(Account.active.is_(True)).limit(1001)))
    if len(insurers)>1000 or len(accounts)>1000:raise HTTPException(409,'基础资料范围过大，请管理员核对停用重复记录')
    vehicles=list(db.scalars(select(CustomerVehicle).where(CustomerVehicle.active.is_(True),CustomerVehicle.customer_id.in_(ids)).limit(501)))
    if len(vehicles)>500:raise HTTPException(409,'客户车辆过多，请先缩小到单个客户')
    sources=list(db.scalars(flow.case_query(user).where(Case.kind=='order',Case.customer_id.in_(ids),Case.vehicle_id.is_not(None),Case.state.notin_(['cancelled','rejected'])).limit(100)))
    renewals=list(db.scalars(flow.case_query(user).join(CareCase,CareCase.case_id==Case.id).where(CareCase.subtype=='renewal',Case.customer_id.in_(ids),Case.state.in_(['pending','working'])).limit(100)))
    policies=list(db.scalars(select(InsuranceResult).join(Case,Case.id==InsuranceResult.case_id).where(InsuranceResult.outcome=='issued',Case.customer_id.in_(ids),Case.id.in_(flow.case_query(user).with_only_columns(Case.id))).limit(100)))
    return dict(customers=[dict(id=r.id,name=r.name,phone=r.phone) for r in customers],total=total,vehicles=[dict(id=r.id,customer_id=r.customer_id,vin=r.vin,plate=r.plate) for r in vehicles],insurers=[_serialize(r) for r in insurers],accounts=[dict(id=r.id,name=r.name) for r in accounts] if user.role in flow.MANAGEMENT else [],sources=[dict(id=r.id,number=r.number,version=r.version,customer_id=r.customer_id) for r in sources],renewals=[dict(id=r.id,title=r.title,version=r.version,customer_id=r.customer_id) for r in renewals],policies=[dict(id=r.id,policy_number=r.policy_number,case_id=r.case_id,vin=_one(db,InsuranceOrder,r.case_id).vin) for r in policies])
def guard_order_delivery(db,order):
    for link in _rows(db,InsuranceOrder,source_order_id=order.id,delivery_blocking=True):
        row=_one(db,Case,link.id);s=summary(db,row)
        if row.state=='cancelled':continue
        if not (s['issued'] or s['terminated']) or any(s[k] for k in ('customer_due_cents','customer_refund_cents','insurer_due_cents','insurer_return_due_cents','direct_due_cents','direct_return_due_cents')) or _active_plan(db,row) or _reservation(db,row):raise HTTPException(409,'本单明确要求交车前保险办结，请完成原保单与保费结清；佣金独立后续核对')
def guard_parent_aftercare(db,user,order):
    excluded=set()
    for link in _rows(db,InsuranceOrder,source_order_id=order.id):
        row=_one(db,Case,link.id)
        if row.customer_id!=order.customer_id or row.parent_id!=order.id or not is_detailed(row):raise HTTPException(409,'原销售保险关联身份异常')
        if row.state!='cancelled' and (row.state!='completed' or not _applied(db,row)):raise HTTPException(409,'原保险须先独立完成真实退保、客户原款及佣金结清，销售售后不能代退保险公司本金')
        excluded.add(row.id)
    return excluded

# Narrow finance hooks keep the shared settlement domain from duplicating cash.
def record_collection(db,user,row,payment_link,evidence_id,*,original_payment=None,correction=False):
    from .insurance_finance import record_collection as record
    return record(db,user,row,payment_link,evidence_id,original_payment=original_payment,correction=correction)
def record_advance_credit(db,user,row,credit_link,evidence_id):
    from .insurance_finance import record_advance_credit as record
    return record(db,user,row,credit_link,evidence_id)
def assert_advance_return(db,user,row,credit_link,amount,evidence_id,plan_id):
    from .insurance_finance import assert_advance_return as check
    return check(db,user,row,credit_link,amount,evidence_id,plan_id)

def create_for_sales_quote(db,user,source,quote):
    """Order v4 client authorization creates one unpriced insurance responsibility."""
    from .sales_quote_models import SalesQuoteConsent,SalesQuoteResolution
    if source.kind!='order' or source.flow_version!=4 or quote.case_id!=source.id or source.data.get('active_quote_id')!=quote.id or not quote.services.get('insurance') or not source.vehicle_id:raise HTTPException(409,'保险自动待办须来源于本版已确认销售与实际配车')
    consent=db.scalar(select(SalesQuoteConsent).where(SalesQuoteConsent.quote_id==quote.id,SalesQuoteConsent.vehicle_id==source.vehicle_id))
    resolved=db.scalar(select(SalesQuoteResolution).where(SalesQuoteResolution.quote_id==quote.id,SalesQuoteResolution.outcome=='activated'))
    if not consent or not resolved:raise HTTPException(409,'销售本版尚无实际客户签回，不能推定保险委托')
    existing=db.scalar(select(Case).where(Case.parent_id==source.id,Case.kind=='insurance',Case.state.notin_(['cancelled','rejected'])))
    if existing:return existing
    customer=_one(db,Customer,source.customer_id);car=_one(db,Vehicle,source.vehicle_id)
    row=Case(number='HKI'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='insurance',flow_version=3,state='pending',title=customer.name+' · 保险核价与结算',parent_id=source.id,customer_id=customer.id,owner_id=source.owner_id,created_by=user.id,business_date=today(),due_date=quote.delivery_due,amount_cents=0,data={})
    db.add(row);db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row);db.add(InsuranceOrder(id=row.id,source_order_id=source.id,customer_vehicle_id=None,renewal_task_id=None,delivery_blocking=True,customer_name=customer.name,vin=car.vin,vehicle_snapshot=dict(vin=car.vin,stock_vehicle_id=car.id,model_name=car.model),reason='销售报价第 '+str(quote.revision)+' 版客户确认另行核价办理保险；保费尚未确定'))
    db.flush();_sync(db,user,row);flow.log_event(db,user,row,'insurance_create','客户当前销售报价产生独立保险核价待办',detail={'source_quote_id':quote.id});return row
