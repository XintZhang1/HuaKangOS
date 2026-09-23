"""Source-bound post-performance adjustments; cash, rights and vehicles stay separate."""
import uuid
from importlib.util import find_spec
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from fastapi import HTTPException
from .db import utcnow,today
from .models import CashEntry,Vehicle
from .flow_models import Case,Task,PaymentLink,Account,FileAsset,StockMove
from .repair_models import RepairAllocation,RepairPayment,RepairSettlement
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .aftercare_models import (AftercareOrder,AftercareSource,AftercareClaim,AftercareExecution,AftercarePlan,AftercarePlanLine,AftercareTender,
    AftercareApproval,AftercareConsent,AftercarePlanCancellation,AftercareApplication,AftercareAdjustment,AftercareCashRefund,AftercareCashCollection,AftercareReceipt)

READ={'admin','manager','sales','service','finance','auditor','inventory','technician'}
MONEY={'admin','manager','sales','service','finance','auditor'}
MANAGE={'admin','manager'}
ROLES={'execution':{'admin','service','technician'},'plan':{'admin','sales','service'},'approve':MANAGE,'reject':MANAGE,
    'cancel_plan':{'admin','manager','sales','service'},'customer_confirm':{'admin','sales','service'},'cancel':{'admin','manager','sales','service'},
    'apply':{'admin','finance'},'refund':{'admin','finance'},'collect':{'admin','finance'}}

def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此售后步骤')
def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'本店记录不存在')
    return row
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _proof(db,user,row,key,category=None):
    asset=flow.file_exists(db,row,key,category)
    if asset.generated or not can_file(user,row,asset):raise HTTPException(403,'须使用本售后单上传且当前岗位可核对的实际凭据')
    return asset
def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(409,'请由当前售后待办接手人办理，或先明确交接')
def _plan(db,row):
    plan=_one(db,AftercarePlan,row.data.get('plan_id',0))
    if plan.case_id!=row.id or db.scalar(select(AftercarePlanCancellation.id).where(AftercarePlanCancellation.plan_id==plan.id)):raise HTTPException(409,'售后方案已失效或不属于当前业务')
    return plan
def _applied(db,row):return db.scalar(select(AftercareApplication).where(AftercareApplication.case_id==row.id))
def _sources(db,row):return _rows(db,AftercareSource,case_id=row.id)
def _source_record(db,user,link):
    # A validated dedicated case grants this narrow relation, not original history/files.
    source=_one(db,Case,link.source_case_id)
    from .service_orders_service import is_detailed
    if is_detailed(source) or (source.kind in {'insurance','addon'} and source.flow_version==3):raise HTTPException(409,'明细服务及保险须按原单独立结清，不能进入整车售后退款分配')
    if source.customer_id!=link.snapshot['customer_id'] or source.flow_version!=link.snapshot['flow_version']:raise HTTPException(409,'原业务客户或版本身份不一致')
    if source.kind=='order' and source.flow_version in {3,4}:
        from .sales_quote_service import active
        quote=active(db,source)
        if not quote or quote.id!=link.snapshot.get('sales_quote_id') or quote.digest!=link.snapshot.get('sales_quote_digest'):raise HTTPException(409,'车辆售后所引用的已确认报价版本不一致')
    return source
def _lock_sources(db,user,row,versions):
    links=_sources(db,row)
    if {str(l.source_case_id) for l in links}!=set(versions):raise HTTPException(409,'请刷新全部关联原单版本，不允许遗漏子单')
    for link in links:
        source=_source_record(db,user,link)
        if source.version!=versions[str(source.id)]:raise HTTPException(409,'原业务已发生变化，请刷新金额与凭据后重办')
        source.updated_at=utcnow()
    db.flush()
def get_order(db,user,key):
    _role(user,READ);row=flow.get_case(db,user,key)
    if row.kind!='aftercare' or row.flow_version!=2:raise HTTPException(404,'本店专用售后单不存在')
    _one(db,AftercareOrder,key);return row
def _execute(db,user,key,operation,payload,callback):
    single_store(db);digest=flow.request_digest('aftercare_'+operation,payload)
    try:
        old=db.scalar(select(AftercareReceipt).where(AftercareReceipt.request_key==key))
        if old:
            if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'同请求编号已用于其他经办人或内容，请核对原结果')
            return old.result
        result=callback();db.flush();db.add(AftercareReceipt(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'原款、原核销、车辆或业务版本同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise

def source_credit(db,source,allocation_id=None):
    query=select(func.coalesce(func.sum(AftercareAdjustment.credit_cents),0)).where(AftercareAdjustment.source_case_id==source.id)
    if allocation_id is not None:query=query.where(AftercareAdjustment.allocation_id==allocation_id)
    return db.scalar(query) or 0
def net_charge(db,source,allocation_id=None):
    amount=_one(db,RepairAllocation,allocation_id).amount_cents if allocation_id else source.amount_cents
    return max(0,amount-source_credit(db,source,allocation_id))

def _source_net_charge(db,source,link):
    # The general case balance still includes other payers. Only this frozen
    # customer-return source excludes them when its original face value is zero.
    if link.snapshot.get('package_zero_customer'):return 0
    return net_charge(db,source,link.allocation_id)
def remaining_commission(db,source):
    credited=db.scalar(select(func.coalesce(func.sum(AftercareAdjustment.revenue_credit_cents),0)).where(AftercareAdjustment.source_case_id==source.id)) or 0
    return max(0,int(source.data.get('commission',0))-credited)
def is_source_ended(db,source):
    return bool(db.scalar(select(AftercareSource.id).join(AftercareOrder,AftercareOrder.id==AftercareSource.case_id)
        .join(AftercareApplication,AftercareApplication.case_id==AftercareOrder.id).where(AftercareSource.source_case_id==source.id,AftercareOrder.scenario!='repair_refund').limit(1)))
def guard_source_action(db,user,source,action,allocation_id=None):
    claimed=db.scalar(select(AftercareClaim).where(AftercareClaim.source_case_id==source.id))
    if source.kind=='repair' and action in {'receive','late_receive'} and allocation_id:
        allocation=_one(db,RepairAllocation,allocation_id)
        if allocation.case_id==source.id and allocation.payer_type!='customer':return
    ancestor=source;seen=set()
    while ancestor:
        if ancestor.id in seen:raise HTTPException(409,'业务来源层级异常，请先核对原单')
        seen.add(ancestor.id)
        if db.scalar(select(AftercareClaim).where(AftercareClaim.source_case_id==ancestor.id)) or is_source_ended(db,ancestor):raise HTTPException(409,'原业务正在办理或已生效售后纠正，请到关联售后单核对保留费用、实物和原路退款')
        ancestor=db.scalar(select(Case).where(Case.id==ancestor.parent_id)) if ancestor.parent_id else None
def _paid(db,source,allocation_id=None):
    query=select(PaymentLink).where(PaymentLink.case_id==source.id)
    if allocation_id:query=query.join(RepairPayment,RepairPayment.payment_link_id==PaymentLink.id).where(RepairPayment.allocation_id==allocation_id)
    elif _package_zero_customer(db,source):query=query.where(False)
    paid=sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in db.scalars(query))
    from .group_service import case_paid_amount
    from .group_benefits_service import case_paid_amount as benefits_paid
    from .repair_package_service import case_paid_amount as packages_paid
    paid+=case_paid_amount(db,source.id)+benefits_paid(db,source.id)+packages_paid(db,source.id)
    if find_spec('app.business_finance_service'):
        from .business_finance_service import case_credit_amount
        paid+=case_credit_amount(db,source.id)
    return paid
def _held(db,source):
    from .group_service import case_reserved_amount
    from .group_benefits_service import case_reserved_amount as benefits_held
    from .repair_package_service import case_reserved_amount as packages_held
    held=case_reserved_amount(db,source.id)+benefits_held(db,source.id)+packages_held(db,source.id)
    if find_spec('app.business_finance_service'):
        from .business_finance_service import case_reserved_amount as finance_held
        held+=finance_held(db,source.id)
    return held
def _cash_remaining(db,original):
    used=db.scalar(select(func.coalesce(func.sum(PaymentLink.amount_cents),0)).where(PaymentLink.original_id==original.id,PaymentLink.direction=='out')) or 0
    return original.amount_cents-used
def _tender_paid(db,tender):
    return db.scalar(select(func.coalesce(func.sum(PaymentLink.amount_cents),0)).join(AftercareCashRefund,AftercareCashRefund.payment_link_id==PaymentLink.id).where(AftercareCashRefund.tender_id==tender.id)) or 0
def refund_reservation_amount(db,original_id,excluding_tender_id=None):
    query=select(AftercareTender).join(AftercareApproval,AftercareApproval.plan_id==AftercareTender.plan_id).join(AftercarePlan,AftercarePlan.id==AftercareTender.plan_id)
    query=query.where(AftercareTender.kind=='cash',AftercareTender.original_id==original_id,~AftercareTender.plan_id.in_(select(AftercarePlanCancellation.plan_id)))
    if excluding_tender_id:query=query.where(AftercareTender.id!=excluding_tender_id)
    return sum(max(0,t.credit_cents-_tender_paid(db,t)) for t in db.scalars(query))
def _eligible(db,user,link,include_group=True):
    source=_source_record(db,user,link);query=select(PaymentLink).where(PaymentLink.case_id==source.id,PaymentLink.direction=='in')
    if link.allocation_id:query=query.join(RepairPayment,RepairPayment.payment_link_id==PaymentLink.id).where(RepairPayment.allocation_id==link.allocation_id)
    elif link.snapshot.get('package_zero_customer'):query=query.where(False)
    result=[]
    for p in db.scalars(query.order_by(PaymentLink.id)):
        remaining=_cash_remaining(db,p)-refund_reservation_amount(db,p.id)
        if remaining>0:result.append({'kind':'cash','entry_id':p.id,'name':'原实际收款 '+p.reference,'remaining_units':remaining,'remaining_credit_cents':remaining,'credit_per_unit':1,'discount_per_unit':0,'account_id':p.account_id})
    if include_group:
        from .group_aftercare import eligible_capture_sources
        result+=eligible_capture_sources(db,user,source)
    return result

def _source_initial(db,user,source):
    allocation=None
    if source.kind=='repair':
        allocation=db.scalar(select(RepairAllocation).where(RepairAllocation.case_id==source.id,RepairAllocation.payer_type=='customer'))
        if not allocation:
            if _package_zero_customer(db,source):return None,0
            raise HTTPException(409,'原维修没有客户承担，不能以客户退费转出保险、厂家或内部款项')
    return allocation,allocation.amount_cents if allocation else source.amount_cents

def _package_zero_customer(db,source):
    """A zero-face captured component never grants access to another payer's cash."""
    if source.kind!='repair' or source.flow_version not in {3,4}:return False
    if db.scalar(select(RepairAllocation.id).where(RepairAllocation.case_id==source.id,RepairAllocation.payer_type=='customer')):return False
    from .repair_package_models import PackagePaymentLink
    captures=list(db.scalars(select(PackagePaymentLink).where(PackagePaymentLink.case_id==source.id,PackagePaymentLink.purpose=='capture')))
    return bool(captures) and all(p.amount_cents==0 for p in captures)
def _sales_quote_snapshot(db,source):
    from .sales_quote_service import active
    quote=active(db,source)
    if not quote:raise HTTPException(409,'销售售后缺少客户已确认的活动报价')
    return {'sales_quote_id':quote.id,'sales_quote_digest':quote.digest}
def create(db,user,key,v):
    _role(user,{'admin','sales','service'})
    def run():
        source=flow.get_case(db,user,v['source_case_id'])
        if source.version!=v['source_version']:raise HTTPException(409,'原单已变化，请刷新后申请售后')
        from .claims_service import guard_source_adjustment
        guard_source_adjustment(db,source,'aftercare_create')
        if v['scenario']=='repair_refund':
            if source.kind!='repair' or source.flow_version not in {3,4} or not source.data.get('released_date') or not db.scalar(select(RepairSettlement.id).where(RepairSettlement.case_id==source.id)):
                raise HTTPException(409,'维修退费须引用已实际接车并冻结承担的维修明细 v3／v4')
        elif source.kind!='order' or source.flow_version not in {2,3,4} or source.state not in {'executing','delivered'}:raise HTTPException(409,'销售售后只接受执行中或已交付的订单 v2／v3／v4')
        elif (v['scenario']=='vehicle_return')!=(source.state=='delivered'):raise HTTPException(409,'已提车使用退车，未提车使用已履约退订；不能混用事实')
        from .sales_quote_service import guard_source_action as quote_guard
        quote_guard(db,user,source,'aftercare')
        if not source.customer_id or is_source_ended(db,source):raise HTTPException(409,'原销售已终止或没有可确认客户')
        from .service_orders_service import guard_parent_aftercare
        excluded_services=guard_parent_aftercare(db,user,source) if source.kind=='order' else set()
        from .insurance_service import guard_parent_aftercare as guard_insurance
        excluded_insurance=guard_insurance(db,user,source) if source.kind=='order' else set()
        from .addon_service import guard_parent_aftercare as guard_addon
        excluded_addons=guard_addon(db,user,source) if source.kind=='order' else set()
        excluded=excluded_services|excluded_insurance|excluded_addons
        sources=[source]
        if source.kind=='order':sources+=list(db.scalars(flow.case_query(user).where(Case.parent_id==source.id,Case.kind.in_(['addon','insurance','agency']),Case.id.not_in(excluded)).order_by(Case.id)))
        all_children=list(db.scalars(select(Case.id).where(Case.parent_id==source.id,Case.kind.in_(['addon','insurance','agency']),Case.id.not_in(excluded))))
        if source.kind=='order' and len(all_children)!=len(sources)-1:raise HTTPException(403,'须能核对所有销售关联服务，不能遗漏不可读子单')
        if db.scalar(select(Case.id).where(Case.parent_id.in_([s.id for s in sources]),Case.kind.in_(['material_issue','material_return']),Case.state.not_in(flow.TERMINAL)).limit(1)):
            raise HTTPException(409,'关联服务仍有未完成领退料；请先核对实际库存事实并结束该申请，再办理售后')
        if any(db.scalar(select(AftercareClaim).where(AftercareClaim.source_case_id==s.id)) for s in sources):raise HTTPException(409,'原单已有未结束售后，请先完成或取消原申请')
        if any(_held(db,s) for s in sources):raise HTTPException(409,'原业务仍有未执行权益或预收占额，请先按原流程释放或完成后再申请')
        from .business_entity_service import assert_same_case_entities
        assert_same_case_entities(db,user,sources)
        row=Case(number='HKA'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='aftercare',flow_version=2,state='pending',
            title=source.title+' · '+{'repair_refund':'维修退费','sale_termination':'履约退订','vehicle_return':'交付后退车'}[v['scenario']],customer_id=source.customer_id,
            owner_id=user.id,created_by=user.id,business_date=today(),due_date=today(),data={'source_case_id':source.id,'independently_resolved_service_ids':sorted(excluded_services),'independently_resolved_insurance_ids':sorted(excluded_insurance),'independently_resolved_addon_ids':sorted(excluded_addons)})
        db.add(row);db.flush();db.add(AftercareOrder(id=row.id,source_case_id=source.id,scenario=v['scenario'],reason=v['reason'],requested_by=user.id));db.flush();from .business_entity_service import freeze_derived_case_entity;freeze_derived_case_entity(db,user,row,source)
        for s in sources:
            s.updated_at=utcnow();allocation,amount=_source_initial(db,user,s)
            link=AftercareSource(case_id=row.id,source_case_id=s.id,allocation_id=allocation.id if allocation else None,original_cents=amount,
                snapshot={'number':s.number,'kind':s.kind,'flow_version':s.flow_version,'customer_id':s.customer_id,'state':s.state,'vehicle_id':s.vehicle_id,'completed_date':s.completed_date.isoformat() if s.completed_date else None,
                    **(_sales_quote_snapshot(db,s) if s.kind=='order' and s.flow_version in {3,4} else {}),
                    **({'package_zero_customer':True} if s.kind=='repair' and allocation is None else {})})
            db.add(link);db.add(AftercareClaim(source_case_id=s.id,case_id=row.id));db.flush()
            if s.id!=source.id:flow.ensure_task(db,row,'aftercare_execution_'+str(link.id),'核对'+flow.flow_spec(s.kind,s.flow_version)['label']+'已履约及终止事实','technician' if s.kind=='addon' else 'service')
        flow.ensure_task(db,row,'aftercare_plan','明确各原单保留费用及原路退回方案','sales' if source.kind=='order' else 'service',assignee=user.id)
        flow.log_event(db,user,row,'aftercare_request','申请独立售后纠正',detail={'source_case_id':source.id,'scenario':v['scenario'],'independently_resolved_service_ids':sorted(excluded_services),'independently_resolved_insurance_ids':sorted(excluded_insurance),'independently_resolved_addon_ids':sorted(excluded_addons)});db.flush();return describe(db,user,row)
    return _execute(db,user,key,'create',v,run)

def assert_group_plan(db,aftercare,source,plan_id,phase):
    order=_one(db,AftercareOrder,aftercare.id);plan=_one(db,AftercarePlan,plan_id)
    link=db.scalar(select(AftercareSource).where(AftercareSource.case_id==aftercare.id,AftercareSource.source_case_id==source.id))
    if not link or plan.case_id!=aftercare.id or aftercare.kind!='aftercare' or aftercare.flow_version!=2 or aftercare.store_id!=source.store_id or source.customer_id!=aftercare.customer_id:raise HTTPException(403,'售后方案未明确关联同店同客户的原核销业务')
    if phase!='cancel':
        if plan.id!=aftercare.data.get('plan_id') or not db.scalar(select(AftercareApproval.id).where(AftercareApproval.plan_id==plan.id)) or db.scalar(select(AftercarePlanCancellation.id).where(AftercarePlanCancellation.plan_id==plan.id)):raise HTTPException(409,'原核销退回缺少当前方案批准')
        if phase=='reserve' and aftercare.state!='authorization':raise HTTPException(409,'仅主管批准时可以占用原核销退回额度')
        if phase=='apply' and (aftercare.state!='working' or not db.scalar(select(AftercareConsent.id).where(AftercareConsent.plan_id==plan.id))):raise HTTPException(409,'实际退回须有客户当前方案确认')
    elif _applied(db,aftercare):raise HTTPException(409,'已应用售后不能取消原核销退回')
    selections=[{'kind':t.kind,'entry_id':t.original_id,'units':t.units,'credit_cents':t.credit_cents} for t in _rows(db,AftercareTender,plan_id=plan.id,source_id=link.id) if t.kind!='cash']
    return {'plan_id':plan.id,'source_case_id':source.id,'selections':selections}
def assert_points_evidence(db,source,evidence_id):
    asset=db.scalar(select(FileAsset).where(FileAsset.id==evidence_id))
    if not asset or asset.store_id!=source.store_id:return False
    app=db.scalar(select(AftercareApplication).join(AftercareSource,AftercareSource.case_id==AftercareApplication.case_id).where(AftercareSource.source_case_id==source.id,AftercareApplication.case_id==asset.case_id))
    if not app:return False
    return bool(app.evidence_id==evidence_id or db.scalar(select(AftercareCashRefund.id).where(AftercareCashRefund.case_id==app.case_id,AftercareCashRefund.evidence_id==evidence_id)) or db.scalar(select(AftercareCashCollection.id).where(AftercareCashCollection.case_id==app.case_id,AftercareCashCollection.evidence_id==evidence_id)))
def require_vehicle_return_authorization(db,user,aftercare,source,evidence_id):
    order=_one(db,AftercareOrder,aftercare.id);plan=_plan(db,aftercare);consent=db.scalar(select(AftercareConsent).where(AftercareConsent.plan_id==plan.id))
    if order.scenario not in {'sale_termination','vehicle_return'} or order.source_case_id!=source.id or aftercare.state!='working' or not consent or consent.evidence_id!=evidence_id or not db.scalar(select(AftercareApproval.id).where(AftercareApproval.plan_id==plan.id)):raise HTTPException(409,'退车资源计划缺少本售后单当前批准与客户授权')
    _proof(db,user,aftercare,evidence_id,'authorization');return True

def _needs_vehicle(db,row):
    order=_one(db,AftercareOrder,row.id);source=_one(db,Case,order.source_case_id)
    return order.scenario!='repair_refund' and bool(source.vehicle_id) and bool(source.state=='delivered' or source.data.get('dispatched_at'))
def _vehicle_proof(db,user,row):
    if not _needs_vehicle(db,row):return None
    from .vehicle_operations_service import get_customer_return_proof
    return get_customer_return_proof(db,user,row.id)
def _new_plan(db,user,row,v):
    if row.state!='pending':raise HTTPException(409,'先撤销尚未确认的旧方案，再明确新版本；实际纠正不能覆盖')
    _task(db,user,row,'aftercare_plan');links=_sources(db,row)
    if {l.id for l in links}!={x['source_id'] for x in v['lines']} or len(links)!=len(v['lines']):raise HTTPException(422,'方案须逐一覆盖原整车及全部关联服务，不可重复或遗漏')
    normalized=[];tenders=[]
    for value in v['lines']:
        link=next(l for l in links if l.id==value['source_id']);source=_source_record(db,user,link);base=_source_net_charge(db,source,link)
        if value['credit_cents']>base:raise HTTPException(422,'本次减免超过该原承担尚未减免金额')
        execution=None
        if source.kind in {'addon','insurance','agency'}:
            execution=db.scalar(select(AftercareExecution).where(AftercareExecution.source_id==link.id).order_by(AftercareExecution.id.desc()))
            if not execution:raise HTTPException(409,'须先由经办岗位确认每项服务实际履约及终止事实')
        retained=base-value['credit_cents'];refund=max(0,_paid(db,source,link.allocation_id)-retained)
        available={(t['kind'],t['entry_id']):t for t in _eligible(db,user,link)};selected=[]
        for t in value['returns']:
            old=available.get((t['kind'],t['original_id']))
            if not old or t['units']>old['remaining_units']:raise HTTPException(409,'原收款或核销剩余额度不足，不能跨原单或重复退回')
            if t['kind']=='repair_package':
                from .repair_package_aftercare import quote_return
                part=quote_return(db,user,source,t['original_id'],t['units'])
                credit,discount=part['credit_cents'],part['discount_cents']
            else:credit,discount=t['units']*old['credit_per_unit'],t['units']*old.get('discount_per_unit',0)
            selected.append({'source_id':link.id,'kind':t['kind'],'original_id':t['original_id'],'units':t['units'],'credit_cents':credit,'discount_cents':discount})
        if len({(t['kind'],t['original_id']) for t in selected})!=len(selected):raise HTTPException(422,'相同原支付请合并为一项')
        if sum(t['credit_cents'] for t in selected)!=refund:raise HTTPException(422,'原路退回合计须精确等于待退结算额；券和套餐只能退原整数份，不能折现，请调整原份数或现金组合')
        revenue_credit=value['credit_cents']-sum(t['discount_cents'] for t in selected)
        if source.kind=='insurance':
            commission=value.get('commission_credit_cents')
            if commission is None or commission>remaining_commission(db,source):raise HTTPException(422,'保险需明确本次佣金减免，不能将代收保费当经营收入或超退原佣金')
            revenue_credit=commission
        elif value.get('commission_credit_cents') is not None:raise HTTPException(422,'只有保险子单填写独立佣金减免')
        normalized.append({'source_id':link.id,'execution_id':execution.id if execution else None,'base_cents':base,'credit_cents':value['credit_cents'],'retained_cents':retained,'refund_cents':refund,'revenue_credit_cents':revenue_credit});tenders.extend(selected)
    zero_package_return=bool(tenders) and all(t['kind']=='repair_package' and t['credit_cents']==0 for t in tenders)
    if not any(l['credit_cents'] for l in normalized) and not zero_package_return and _one(db,AftercareOrder,row.id).scenario=='repair_refund':raise HTTPException(422,'维修退费方案须明确本次实际减免金额或原套餐零分尾数组件的真实退回数量')
    payload={'lines':normalized,'returns':tenders,'reason':v['reason']};revision=(db.scalar(select(func.max(AftercarePlan.revision)).where(AftercarePlan.case_id==row.id)) or 0)+1
    plan=AftercarePlan(case_id=row.id,revision=revision,reason=v['reason'],digest=flow.request_digest('aftercare_plan',payload),created_by=user.id);db.add(plan);db.flush()
    for x in normalized:db.add(AftercarePlanLine(plan_id=plan.id,**x))
    for x in tenders:db.add(AftercareTender(plan_id=plan.id,**x))
    flow.set_data(row,plan_id=plan.id);row.state='approval';flow.finish_task(db,row,'aftercare_plan',user);flow.ensure_task(db,row,'aftercare_approve','主管核对保留费用与原路退回方案','manager',reopen=True)

def _check_plan_money(db,user,row,plan,approval=False):
    for line in _rows(db,AftercarePlanLine,plan_id=plan.id):
        link=_one(db,AftercareSource,line.source_id);source=_source_record(db,user,link)
        if _source_net_charge(db,source,link)!=line.base_cents or max(0,_paid(db,source,link.allocation_id)-line.retained_cents)!=line.refund_cents:raise HTTPException(409,'原应收或原支付已变化，请取消未生效方案后重新核对')
        for t in _rows(db,AftercareTender,plan_id=plan.id,source_id=link.id):
            if t.kind!='cash':continue
            original=_one(db,PaymentLink,t.original_id)
            if original.case_id!=source.id or original.direction!='in' or t.credit_cents>_cash_remaining(db,original)-refund_reservation_amount(db,original.id,t.id):raise HTTPException(409,'原现金可退余额被其他实际退款或批准占额使用')
        if _held(db,source):raise HTTPException(409,'原单出现新的未核销占额，不能应用减免')
def _sync(db,user,row,evidence_id=None):
    applied=_applied(db,row)
    if not applied:return
    plan=_one(db,AftercarePlan,applied.plan_id);pending=False
    for t in _rows(db,AftercareTender,plan_id=plan.id):
        if t.kind!='cash':continue
        due=t.credit_cents-_tender_paid(db,t);key='aftercare_refund_'+str(t.id)
        if due>0:flow.ensure_task(db,row,key,'按原收款逐笔执行实际退款','finance',reopen=True);pending=True
        else:flow.finish_task(db,row,key,user)
    for link in _sources(db,row):
        source=_source_record(db,user,link);due=max(0,_source_net_charge(db,source,link)-_paid(db,source,link.allocation_id));key='aftercare_collect_'+str(link.id)
        if due>0:flow.ensure_task(db,row,key,'核对并收取原单已履约保留费余额','finance',reopen=True);pending=True
        else:flow.finish_task(db,row,key,user)
        if source.kind=='repair':
            from .repair_service import sync_after_member
            sync_after_member(db,user,source,evidence_id=evidence_id)
        from .invoice_service import sync_source
        sync_source(db,user,source)
    row.state='working' if pending else 'completed'
    if not pending:
        row.completed_date=today();flow.close_tasks(db,row,user)
        for claim in db.scalars(select(AftercareClaim).where(AftercareClaim.case_id==row.id)):db.delete(claim)
    db.flush()

def _cash(db,user,row,source,values,direction,original=None):
    account=_one(db,Account,values['account_id'])
    if not account.active:raise HTTPException(409,'原资金账户已停用，请先核对账户配置，不得擅自更换退款账户')
    _proof(db,user,row,values['evidence_id'],'receipt')
    if original and account.id!=original.account_id:raise HTTPException(409,'实际退款必须使用原收款账户')
    if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==values['reference'])):raise HTTPException(409,'该账户实际凭证已登记，请核对重复收退款')
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id if original else None)
    account.updated_at=utcnow();cash=CashEntry(doc_no='AC-'+uuid.uuid4().hex[:20].upper(),business_date=today(),created_by=user.id,approval_state='approved',direction=direction,
        category='workflow_refund' if direction=='out' else 'workflow_'+source.kind,amount_cents=values['amount_cents'],account=account.name,
        counterparty=source.title,payment_method='cash' if account.account_type=='cash' else 'bank',voucher_no=values['reference'],note='售后 '+row.number+'；原单 '+source.number)
    db.add(cash);db.flush();record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else None);payment=PaymentLink(case_id=source.id,cash_id=cash.id,original_id=original.id if original else None,account_id=account.id,direction=direction,
        amount_cents=values['amount_cents'],reference=values['reference'],business_date=today());db.add(payment);db.flush();return payment

def command(db,user,key,request_id,version,source_versions,action,v):
    _role(user,ROLES[action])
    def run():
        row=get_order(db,user,key);order=_one(db,AftercareOrder,key)
        if row.version!=version:raise HTTPException(409,'售后记录已变化，请刷新后核对')
        _lock_sources(db,user,row,source_versions);row.updated_at=utcnow()
        if action in {'execution','plan','approve','customer_confirm','apply','refund','collect'}:
            parent=_one(db,Case,order.source_case_id)
            if parent.kind=='order':
                from .service_orders_service import guard_parent_aftercare
                if guard_parent_aftercare(db,user,parent)!=set(row.data.get('independently_resolved_service_ids',[])):raise HTTPException(409,'销售关联服务已变化，请先核对原服务及售后方案')
                from .insurance_service import guard_parent_aftercare as guard_insurance
                if guard_insurance(db,user,parent)!=set(row.data.get('independently_resolved_insurance_ids',[])):raise HTTPException(409,'销售关联保险已变化，请先核对原保单及售后方案')
                from .addon_service import guard_parent_aftercare as guard_addon
                if guard_addon(db,user,parent,phase='apply' if action in {'apply','refund','collect'} else 'request')!=set(row.data.get('independently_resolved_addon_ids',[])):raise HTTPException(409,'销售关联加装已变化，请先核对原实物处置及售后方案')
            from .claims_service import guard_source_adjustment
            for link in _sources(db,row):guard_source_adjustment(db,_source_record(db,user,link),'aftercare_'+action)
        if action=='execution':
            if row.state!='pending':raise HTTPException(409,'已有待批或已确认方案，先处理该版本再补履约事实')
            link=_one(db,AftercareSource,v['source_id']);source=_source_record(db,user,link)
            if link.case_id!=row.id or source.kind not in {'addon','insurance','agency'}:raise HTTPException(404,'本售后关联服务不存在')
            required={'admin','technician'} if source.kind=='addon' else {'admin','service'};_role(user,required);_task(db,user,row,'aftercare_execution_'+str(link.id));_proof(db,user,row,v['evidence_id'])
            done=flow.task_done(db,source,'work') or source.state in {'completed','settling'}
            stock_cases=[source.id]+list(db.scalars(select(Case.id).where(Case.parent_id==source.id)))
            has_stock=bool(db.scalar(select(StockMove.id).where(StockMove.case_id.in_(stock_cases)).limit(1)))
            if v['outcome']=='not_started' and (done or has_stock):raise HTTPException(409,'原单已有履约或实物记录，不能声明从未执行')
            if source.kind=='insurance' and source.data.get('policy_number') and v['external_result']!='terminated':raise HTTPException(409,'已出保单须先取得真实退保或终止结果，不能以内部取消代替')
            if source.kind=='addon' and v['external_result']!='not_required':raise HTTPException(422,'加装施工不是外部退保结果')
            db.add(AftercareExecution(case_id=row.id,source_id=link.id,actor_id=user.id,**{k:v[k] for k in ('outcome','external_result','result','evidence_id')}));flow.finish_task(db,row,'aftercare_execution_'+str(link.id),user)
        elif action=='plan':_new_plan(db,user,row,v)
        elif action=='approve':
            if row.state!='approval':raise HTTPException(409,'当前没有待审批方案')
            plan=_plan(db,row);_task(db,user,row,'aftercare_approve')
            if user.id in {plan.created_by,order.requested_by}:raise HTTPException(403,'方案申请人与审批人须分开，系统管理员也不能替代独立复核')
            _proof(db,user,row,v['evidence_id'],'authorization');_check_plan_money(db,user,row,plan,True)
            db.add(AftercareApproval(plan_id=plan.id,actor_id=user.id,evidence_id=v['evidence_id'],reason=v['reason']));row.state='authorization';db.flush()
            from .group_aftercare import reserve_returns
            for link in _sources(db,row):
                source=_source_record(db,user,link);selected=assert_group_plan(db,row,source,plan.id,'reserve')['selections']
                if selected:reserve_returns(db,user,row,source,plan.id,selected,v['evidence_id'])
            flow.finish_task(db,row,'aftercare_approve',user);flow.ensure_task(db,row,'aftercare_consent','取得客户对当前售后方案的明确确认','sales' if order.scenario!='repair_refund' else 'service',assignee=row.owner_id)
        elif action=='customer_confirm':
            if row.state!='authorization':raise HTTPException(409,'须主管先批准当前售后方案')
            plan=_plan(db,row);_task(db,user,row,'aftercare_consent');asset=_proof(db,user,row,v['evidence_id'],'authorization')
            approval=db.scalar(select(AftercareApproval).where(AftercareApproval.plan_id==plan.id))
            if approval.evidence_id==asset.id:raise HTTPException(409,'主管审批文件不能代替客户本人对方案的确认凭据')
            db.add(AftercareConsent(plan_id=plan.id,actor_id=user.id,evidence_id=asset.id,plan_digest=plan.digest));row.state='working';db.flush()
            if _needs_vehicle(db,row):
                from .vehicle_operations_service import prepare_customer_return
                prepare_customer_return(db,user,row,_one(db,Case,order.source_case_id),asset.id)
            flow.finish_task(db,row,'aftercare_consent',user);flow.ensure_task(db,row,'aftercare_apply','核实前置事实并应用已批准售后纠正','finance')
        elif action in {'cancel_plan','cancel','reject'}:
            if _applied(db,row) or row.state in {'completed','cancelled','rejected'}:raise HTTPException(409,'已有实际纠正或业务已结束，不能取消覆盖')
            if action=='cancel_plan' and row.state not in {'approval','authorization'}:raise HTTPException(409,'只能撤销未由客户确认的待批方案')
            if action=='reject' and row.state!='approval':raise HTTPException(409,'只有待审批方案可以拒绝')
            if row.state=='working' and _needs_vehicle(db,row):
                from .vehicle_operations_service import cancel_customer_return_plan
                cancel_customer_return_plan(db,user,row,v['reason'])
            if row.data.get('plan_id'):
                plan=_plan(db,row)
                from .group_aftercare import cancel_returns
                for link in _sources(db,row):
                    if db.scalar(select(AftercareApproval.id).where(AftercareApproval.plan_id==plan.id)):cancel_returns(db,user,row,_source_record(db,user,link),plan.id)
                db.add(AftercarePlanCancellation(plan_id=plan.id,actor_id=user.id,reason=v['reason']))
            flow.close_tasks(db,row,user)
            if action=='cancel_plan':
                row.state='pending';flow.set_data(row,plan_id=None);flow.ensure_task(db,row,'aftercare_plan','重新明确售后保留费用和原路退回','sales' if order.scenario!='repair_refund' else 'service',assignee=row.owner_id,reopen=True)
            else:
                row.state='rejected' if action=='reject' else 'cancelled';row.completed_date=today()
                for claim in db.scalars(select(AftercareClaim).where(AftercareClaim.case_id==row.id)):db.delete(claim)
        elif action=='apply':
            if row.state!='working' or _applied(db,row):raise HTTPException(409,'客户确认及前置事实完成后才可应用一次纠正')
            _task(db,user,row,'aftercare_apply');_proof(db,user,row,v['evidence_id'],'receipt');plan=_plan(db,row);_check_plan_money(db,user,row,plan)
            if _needs_vehicle(db,row):
                physical=_vehicle_proof(db,user,row)
                if not physical or not physical.get('accepted') or not physical.get('new_vehicle_id'):raise HTTPException(409,'须完成原VIN退回检查和受控新批次验收入库，不能先退款后假设实车已收回')
            application=AftercareApplication(plan_id=plan.id,case_id=row.id,actor_id=user.id,evidence_id=v['evidence_id'],business_date=today());db.add(application);db.flush()
            from .group_aftercare import apply_returns
            for line in _rows(db,AftercarePlanLine,plan_id=plan.id):
                link=_one(db,AftercareSource,line.source_id);source=_source_record(db,user,link);returns=_rows(db,AftercareTender,plan_id=plan.id,source_id=link.id)
                discount=sum(t.discount_cents for t in returns if t.kind!='cash')
                db.add(AftercareAdjustment(application_id=application.id,plan_line_id=line.id,source_case_id=source.id,allocation_id=link.allocation_id,credit_cents=line.credit_cents,revenue_credit_cents=line.revenue_credit_cents));db.flush()
                if any(t.kind!='cash' for t in returns):apply_returns(db,user,row,source,plan.id,v['evidence_id'])
                if order.scenario!='repair_refund':
                    flow.set_data(source,aftercare_ended=True);flow.close_tasks(db,source,user)
                    for callback in db.scalars(select(Case).where(Case.parent_id==source.id,Case.kind=='callback',Case.state.not_in(flow.TERMINAL))):
                        callback.state='cancelled';callback.completed_date=today();flow.close_tasks(db,callback,user)
                        flow.log_event(db,user,callback,'aftercare_source_ended','原业务售后终止，取消尚未办理的关联回访',detail={'aftercare_case_id':row.id})
                    if source.id==order.source_case_id and source.vehicle_id and not _needs_vehicle(db,row):
                        from .vehicle_operations_service import release_undispatched_order_hold
                        consent=db.scalar(select(AftercareConsent).where(AftercareConsent.plan_id==plan.id))
                        release_undispatched_order_hold(db,user,source,row,consent.evidence_id)
                flow.log_event(db,user,source,'aftercare_adjust','关联售后追加费用纠正',detail={'aftercare_case_id':row.id,'credit_cents':line.credit_cents})
            flow.finish_task(db,row,'aftercare_apply',user);db.flush();_sync(db,user,row,v['evidence_id'])
        elif action in {'refund','collect'}:
            if not _applied(db,row) or row.state!='working':raise HTTPException(409,'先完成售后费用与原权益纠正，随后逐笔记录实际收退款')
            if action=='refund':
                tender=_one(db,AftercareTender,v['tender_id']);plan=_plan(db,row)
                if tender.plan_id!=plan.id or tender.kind!='cash':raise HTTPException(404,'本方案原现金退回项目不存在')
                link=_one(db,AftercareSource,tender.source_id);source=_source_record(db,user,link);original=_one(db,PaymentLink,tender.original_id)
                _task(db,user,row,'aftercare_refund_'+str(tender.id));maximum=min(tender.credit_cents-_tender_paid(db,tender),_cash_remaining(db,original)-refund_reservation_amount(db,original.id,tender.id),max(0,_paid(db,source,link.allocation_id)-_source_net_charge(db,source,link)))
                if v['amount_cents']>maximum:raise HTTPException(409,'退款超过本方案未退额、原收款未退额或当前实际应退款')
                payment=_cash(db,user,row,source,v,'out',original);db.add(AftercareCashRefund(case_id=row.id,tender_id=tender.id,payment_link_id=payment.id,evidence_id=v['evidence_id'],actor_id=user.id))
            else:
                link=_one(db,AftercareSource,v['source_id'])
                if link.case_id!=row.id:raise HTTPException(404,'本售后保留费来源不存在')
                source=_source_record(db,user,link);_task(db,user,row,'aftercare_collect_'+str(link.id))
                if v['amount_cents']>max(0,_source_net_charge(db,source,link)-_paid(db,source,link.allocation_id)):raise HTTPException(409,'收款超过原已履约保留费尚欠金额')
                payment=_cash(db,user,row,source,v,'in');db.add(AftercareCashCollection(case_id=row.id,source_id=link.id,payment_link_id=payment.id,evidence_id=v['evidence_id'],actor_id=user.id))
            if link.allocation_id:db.add(RepairPayment(allocation_id=link.allocation_id,payment_link_id=payment.id,evidence_id=v['evidence_id']))
            db.flush();_sync(db,user,row,v['evidence_id'])
        else:raise HTTPException(404,'售后动作不存在')
        label={'execution':'核对服务履约与终止','plan':'冻结费用及原路退回方案','approve':'主管批准售后方案','reject':'主管拒绝售后方案','cancel_plan':'撤销未确认方案','customer_confirm':'记录客户当前方案确认','cancel':'取消未生效售后','apply':'应用售后费用纠正','refund':'登记原款实际退款','collect':'登记原保留费实际到账'}[action]
        flow.log_event(db,user,row,'aftercare_'+action,label,detail={'plan_id':row.data.get('plan_id'),'evidence_id':v.get('evidence_id'),'reason':v.get('reason','')});db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,action,{'id':key,'version':version,'source_versions':source_versions,'values':v},run)

def describe(db,user,row):
    order=_one(db,AftercareOrder,row.id);money=user.role in MONEY
    result={'id':row.id,'version':row.version,'number':row.number,'title':row.title,'state':row.state,'scenario':order.scenario,'reason':order.reason,'source_case_id':order.source_case_id,
        'plan_id':row.data.get('plan_id'),'applied':bool(_applied(db,row)),'sources':[],'plans':[],'actions':[k for k,r in ROLES.items() if user.role in r]}
    for link in _sources(db,row):
        source=_source_record(db,user,link);entry={'id':link.id,'case_id':source.id,'version':source.version,'number':source.number,'kind':source.kind,'state':source.state,
            'execution':[{'id':e.id,'outcome':e.outcome,'external_result':e.external_result,'result':e.result,'evidence_id':e.evidence_id} for e in _rows(db,AftercareExecution,source_id=link.id)]}
        if money:
            net=_source_net_charge(db,source,link);paid=_paid(db,source,link.allocation_id)
            entry.update(original_cents=link.original_cents,net_cents=net,paid_cents=paid,due_cents=max(0,net-paid),refund_cents=max(0,paid-net),eligible_returns=_eligible(db,user,link) if row.state=='pending' else [])
            if source.kind=='insurance':entry['commission_cents']=remaining_commission(db,source)
        result['sources'].append(entry)
    for plan in _rows(db,AftercarePlan,case_id=row.id):
        item={'id':plan.id,'revision':plan.revision,'reason':plan.reason,'digest':plan.digest,'approved':bool(db.scalar(select(AftercareApproval.id).where(AftercareApproval.plan_id==plan.id))),
            'customer_confirmed':bool(db.scalar(select(AftercareConsent.id).where(AftercareConsent.plan_id==plan.id))),'cancelled':bool(db.scalar(select(AftercarePlanCancellation.id).where(AftercarePlanCancellation.plan_id==plan.id)))}
        if money:
            item['lines']=[{k:getattr(l,k) for k in ('id','source_id','execution_id','base_cents','credit_cents','retained_cents','refund_cents','revenue_credit_cents')} for l in _rows(db,AftercarePlanLine,plan_id=plan.id)]
            item['returns']=[{**{k:getattr(t,k) for k in ('id','source_id','kind','original_id','units','credit_cents')},'paid_cents':_tender_paid(db,t) if t.kind=='cash' else t.credit_cents if _applied(db,row) else 0} for t in _rows(db,AftercareTender,plan_id=plan.id)]
        result['plans'].append(item)
    if money:result['refunds']=[{'id':r.id,'tender_id':r.tender_id,'payment_link_id':r.payment_link_id,'amount_cents':_one(db,PaymentLink,r.payment_link_id).amount_cents} for r in _rows(db,AftercareCashRefund,case_id=row.id)]
    result['vehicle_return']=_vehicle_proof(db,user,row) if row.state in {'working','completed'} and _needs_vehicle(db,row) else None
    return result
def list_orders(db,user,page):
    _role(user,READ);q=flow.case_query(user).where(Case.kind=='aftercare',Case.flow_version==2)
    count=db.scalar(select(func.count()).select_from(q.subquery()));return {'items':[describe(db,user,r) for r in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*30).limit(30))],'total':count,'page':page}
def sources(db,user,page):
    _role(user,MONEY);q=flow.case_query(user).where(((Case.kind=='order')&Case.flow_version.in_([2,3,4])&Case.state.in_(['executing','delivered']))|((Case.kind=='repair')&Case.flow_version.in_([3,4])&Case.data['released_date'].as_string().is_not(None)))
    ended=select(AftercareSource.source_case_id).join(AftercareOrder,AftercareOrder.id==AftercareSource.case_id).join(AftercareApplication,AftercareApplication.case_id==AftercareOrder.id).where(AftercareOrder.scenario!='repair_refund')
    customer_amount=select(func.coalesce(func.sum(RepairAllocation.amount_cents),0)).where(RepairAllocation.case_id==Case.id,RepairAllocation.payer_type=='customer').correlate(Case).scalar_subquery()
    credited=select(func.coalesce(func.sum(AftercareAdjustment.credit_cents),0)).where(AftercareAdjustment.source_case_id==Case.id).correlate(Case).scalar_subquery()
    from . import repair_package_service as packages
    from .repair_package_models import PackageEntry,PackageLot
    from .repair_package_aftercare import remaining_spans
    with packages.authority(db,user) as sid:
        original_components=list(db.scalars(select(PackageEntry).join(PackageLot,PackageLot.id==PackageEntry.lot_id)
            .where(PackageEntry.store_id==sid,PackageEntry.purpose=='capture',PackageLot.snapshot['kind'].as_string()=='part').limit(25001)))
        if len(original_components)>25000:raise HTTPException(422,'原套餐组件来源超过当前候选处理上限，请联系管理员核对')
        package_sources={e.case_id for e in original_components if remaining_spans(db,e)}
    q=q.where(~Case.id.in_(ended),(Case.kind!='repair')|(customer_amount>credited)|Case.id.in_(package_sources))
    total=db.scalar(select(func.count()).select_from(q.subquery()));items=[]
    for row in db.scalars(q.order_by(Case.id.desc()).offset((page-1)*30).limit(30)):
        items.append({'id':row.id,'version':row.version,'number':row.number,'title':row.title,'scenario':'repair_refund' if row.kind=='repair' else 'vehicle_return' if row.state=='delivered' else 'sale_termination'})
    return {'items':items,'total':total,'page':page}
