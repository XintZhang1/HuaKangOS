"""Immutable claims facts; source locks serialize reimbursement and responsibility limits."""
import uuid
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import utcnow,today
from .models import CashEntry
from .flow_models import Case,Task,Account,PaymentLink,Reference,FileAsset
from .repair_models import RepairQuote,RepairLine,RepairAllocation,RepairPayment,RepairSettlement
from .flow_documents import can_file
from .tenancy import single_store
from . import flow_engine as flow
from .claims_models import (ClaimOrder,ClaimAssessment,ClaimApproval,ClaimTransmission,ClaimResult,ClaimBinding,
    ClaimResolution,ClaimResolutionApproval,ClaimApplication,ClaimResponsibility,ClaimReimbursementApproval,
    ClaimCash,ClaimCustomerPayment,ClaimReturnPlan,ClaimReturnApproval,ClaimReturnCancellation,ClaimClosure,ClaimReceipt)

READ={'admin','manager','service','finance','auditor'}
SERVICE={'admin','service'};MANAGE={'admin','manager'};FINANCE={'admin','finance'}
ROLES={**{k:SERVICE for k in ('assess','transmit','result','bind','resolution','return_plan')},
    **{k:MANAGE for k in ('approve','resolution_approve','reimbursement_approve','return_approve')},
    **{k:FINANCE for k in ('thirdparty_refund','resolution_apply','direct_confirm','pass_receive','pass_pay','direct_return','customer_return','party_return','unused_refund')},
    **{k:SERVICE|MANAGE for k in ('return_cancel','close','cancel')}}
LABELS={'assess':'记录损失明细与核价版本','approve':'独立复核核价','transmit':'确认实际外部提交／补件','result':'记录实际核赔结果',
    'bind':'绑定原承担','resolution':'提出第三方调减及内部吸收','resolution_approve':'独立批准责任调整','thirdparty_refund':'按原第三方收款实际退款',
    'resolution_apply':'生效责任调整','reimbursement_approve':'独立批准客户报销额度','direct_confirm':'核对第三方直接付客户',
    'pass_receive':'确认第三方报销款到店','pass_pay':'按原到账转付客户','return_plan':'提出原报销返还方案','return_approve':'独立批准报销返还',
    'return_cancel':'撤销尚未实际返还的方案','direct_return':'核对客户已退原第三方','customer_return':'确认客户按原付款退回门店',
    'party_return':'将客户退回款原路退给第三方','unused_refund':'未转付原报销款实际退第三方','close':'核对未用额度并结案','cancel':'取消尚无实际资金的申请'}
PHASES={'assessment':'待核损核价','approval':'待独立核价复核','send':'待提交外部','waiting':'等待外部结果','supplement':'待补充资料',
    'ready':'已取得核价结果','bound':'已绑定原承担／等待后续到账','resolution_review':'待责任调整复核','resolution_execute':'待原款退款及生效',
    'reimbursement':'待实际客户报销','completed':'已完成','cancelled':'已取消'}

def _one(db,model,key):
    row=db.scalar(select(model).where(model.id==key))
    if not row:raise HTTPException(404,'本店理赔关联记录不存在')
    return row
def _rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def _first(db,model,**kw):return db.scalar(select(model).filter_by(**kw))
def _role(user,roles):
    if user.role not in roles:raise HTTPException(403,'当前岗位不能办理此理赔步骤')
def get_order(db,user,key):
    _role(user,READ);single_store(db);row=flow.get_case(db,user,key)
    if row.kind!='claim' or row.flow_version!=2:raise HTTPException(404,'本店专用理赔单不存在')
    _one(db,ClaimOrder,key);return row
def _source(db,order):
    source=_one(db,Case,order.source_case_id)
    if source.customer_id!=order.source_snapshot['customer_id'] or source.flow_version!=order.source_snapshot['flow_version']:
        raise HTTPException(409,'原维修客户或流程身份不一致，请先核对原单')
    return source
def _proof(db,user,row,key,financial=False):
    asset=flow.file_exists(db,row,key,'receipt' if financial else 'authorization')
    if asset.generated or not can_file(user,row,asset):raise HTTPException(403,'须使用本理赔单新上传、已扫描并可由当前岗位核对的原件')
    # A document attests to one claim fact. Identical bytes re-uploaded on the same
    # case do not create a new actual external result or bank transaction.
    for model in (ClaimApproval,ClaimTransmission,ClaimResult,ClaimResolution,ClaimResolutionApproval,ClaimApplication,
                  ClaimReimbursementApproval,ClaimCash,ClaimCustomerPayment,ClaimReturnPlan,ClaimReturnApproval,ClaimReturnCancellation,ClaimClosure):
        if db.scalar(select(model.id).join(FileAsset,FileAsset.id==model.evidence_id).where(FileAsset.case_id==row.id,FileAsset.sha256==asset.sha256).limit(1)):
            raise HTTPException(409,'该凭据已经确认过其他事实，请上传本次实际结果原件')
    return asset
def _task(db,user,row,key):
    task=_first(db,Task,case_id=row.id,key=key,status='open')
    if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(409,'请由此理赔待办的当前接手人办理，或先明确交接')
def _manager_task(db,row,key,title,excluded):
    candidates=[u for u in flow.eligible_users(db,'manager',row.store_id) if u.id not in excluded]
    if not candidates:raise HTTPException(409,'本店须配置另一位可独立复核的主管，申请人不能审批自己的方案')
    task=_first(db,Task,case_id=row.id,key=key,status='open')
    flow.ensure_task(db,row,key,title,'manager',assignee=task.assignee_id if task and task.assignee_id not in excluded else candidates[0].id,reopen=True)
def _phase(db,row,user,phase):
    for task in _rows(db,Task,case_id=row.id):
        if task.status=='open' and task.key.startswith('claim_') and not task.key.startswith('claim_return_'):flow.finish_task(db,row,task.key,user)
    flow.set_data(row,phase=phase);row.state={'approval':'approval','resolution_review':'approval','completed':'completed','cancelled':'cancelled'}.get(phase,'working')
    row.completed_date=today() if phase=='completed' else None
    if phase in {'completed','cancelled'}:return
    mapping={'assessment':('assess','核对损失明细并核价','service'),'send':('transmit','提交核赔资料','service'),
        'waiting':('result','跟进实际外部结果','service'),'supplement':('transmit','按外部要求补充资料','service'),
        'ready':('handle','核对承担或客户报销路径','service'),'bound':('settle','跟进原承担到账','finance'),
        'resolution_execute':('resolve','按原款退还后生效责任调整','finance'),'reimbursement':('reimburse','核对实际客户报销','finance')}
    if phase=='approval':
        assessment=_one(db,ClaimAssessment,row.data['assessment_id']);_manager_task(db,row,'claim_approve','独立复核本核价版本',{assessment.actor_id,row.created_by})
    elif phase=='resolution_review':
        plan=_first(db,ClaimResolution,case_id=row.id);_manager_task(db,row,'claim_resolution_approve','独立复核第三方责任调整',{plan.actor_id})
    elif phase=='ready' and _one(db,ClaimOrder,row.id).payment_route in {'customer_direct','customer_via_store'}:
        result=_result(db,row);a=_assessment(db,row)
        _manager_task(db,row,'claim_reimbursement_approve','独立核对原客户现金及核准报销额度',{row.created_by,a.actor_id,result.actor_id})
    else:
        key,title,role=mapping[phase];flow.ensure_task(db,row,'claim_'+key,title,role,assignee=row.owner_id if role=='service' else None,reopen=True)
def _execute(db,user,key,operation,payload,fn):
    single_store(db);digest=flow.request_digest('claims_'+operation,payload)
    try:
        old=_first(db,ClaimReceipt,request_key=key)
        if old:
            if old.actor_id!=user.id or old.digest!=digest:raise HTTPException(409,'同请求编号已用于其他内容或经办人，请核对原结果')
            return old.result
        result=fn();db.flush();db.add(ClaimReceipt(request_key=key,digest=digest,actor_id=user.id,result=result));db.commit();return result
    except (IntegrityError,OperationalError,StaleDataError):
        db.rollback();raise HTTPException(409,'原单、款项或理赔版本同时变化，请刷新核对并保留原请求编号')
    except Exception:db.rollback();raise
def _assessment(db,row,current=True):
    a=_one(db,ClaimAssessment,row.data.get('assessment_id',0));order=_one(db,ClaimOrder,row.id);source=_source(db,order)
    if a.case_id!=row.id:raise HTTPException(409,'核价版本不属于本单')
    if current and source.data.get('quote_id')!=a.quote_id:raise HTTPException(409,'原维修报价已变化，须重新核损核价并复核')
    return a
def _result(db,row):
    result=_one(db,ClaimResult,row.data.get('result_id',0));a=_assessment(db,row)
    if result.case_id!=row.id or result.assessment_id!=a.id or result.outcome=='need_documents':raise HTTPException(409,'尚无当前核价版本的最终外部结果')
    return result
def _allocation(db,order):
    a=_first(db,RepairAllocation,case_id=order.source_case_id,payer_type=order.party_type)
    if not a:raise HTTPException(409,'原维修尚未冻结此承担方，先在原单核对多方分配')
    if order.party_type=='insurer' and a.insurer_id!=order.insurer_id or order.party_type=='manufacturer' and a.manufacturer_id!=order.manufacturer_id or order.party_type=='internal' and a.payer_name!=order.party_name:
        raise HTTPException(409,'核赔单位必须与原维修冻结承担方一致，不能替换原债务人')
    return a
def _approved_amount(db,row,order):
    a=_assessment(db,row)
    if not _first(db,ClaimApproval,assessment_id=a.id):raise HTTPException(409,'当前核价尚未通过独立复核')
    return (a.amount_cents,None) if order.party_type=='internal' else (_result(db,row).amount_cents,_result(db,row).id)
def allocation_delta(db,allocation_id):
    return db.scalar(select(func.coalesce(func.sum(ClaimResponsibility.amount_cents),0)).where(ClaimResponsibility.allocation_id==allocation_id)) or 0
def _cash_amount(db,fact):return _one(db,PaymentLink,fact.payment_link_id).amount_cents
def _cash_total(db,key,purpose):return sum(_cash_amount(db,c) for c in _rows(db,ClaimCash,case_id=key,purpose=purpose))
def _direct_total(db,key,purpose):return sum(p.amount_cents for p in _rows(db,ClaimCustomerPayment,case_id=key,purpose=purpose))
def _reimbursement_usage(db,order):
    a=_first(db,ClaimReimbursementApproval,case_id=order.id)
    if not a:return 0
    close=_first(db,ClaimClosure,case_id=order.id)
    returned=_direct_total(db,order.id,'return') if order.payment_route=='customer_direct' else _cash_total(db,order.id,'party_return')
    return max(0,a.amount_cents-(close.unused_cents if close else 0)-returned)
def customer_reimbursement_available(db,source,excluding_case_id=None):
    from .repair_service import _cash_paid
    a=_first(db,RepairAllocation,case_id=source.id,payer_type='customer')
    cash=_cash_paid(db,a) if a else 0
    used=sum(_reimbursement_usage(db,o) for o in _rows(db,ClaimOrder,source_case_id=source.id) if o.id!=excluding_case_id)
    return max(0,cash-used)
def guard_source_adjustment(db,source,action='adjustment'):
    """Prevent a refund/cash correction from erasing cash already reimbursed to customer."""
    for o in _rows(db,ClaimOrder,source_case_id=source.id):
        if _reimbursement_usage(db,o)>0:raise HTTPException(409,'原客户实付款已用于报销或获准占额，请先到理赔单撤回未用额度或完成原路径返还')
        r=_first(db,ClaimResolution,case_id=o.id)
        if r and _one(db,Case,o.id).state!='cancelled' and _first(db,ClaimResolutionApproval,resolution_id=r.id) and not _first(db,ClaimApplication,resolution_id=r.id):
            raise HTTPException(409,'原第三方承担正在退款调整，请先完成对应理赔责任调整')
def _guard_other_adjustments(db,user,source):
    from .aftercare_service import guard_source_action
    from .business_finance_models import FinanceOrder
    guard_source_action(db,user,source,'claims')
    source_cash=set(db.scalars(select(PaymentLink.cash_id).where(PaymentLink.case_id==source.id)))
    for correction in db.scalars(select(FinanceOrder).where(FinanceOrder.purpose=='correction',FinanceOrder.status.in_(['draft','approved']))):
        if correction.values.get('original_cash_id') in source_cash:raise HTTPException(409,'原客户款正在办理误记更正，请先完成或取消财务更正，再核对理赔报销额度')
def guard_invoice_blue(db,source):
    for o in _rows(db,ClaimOrder,source_case_id=source.id):
        r=_first(db,ClaimResolution,case_id=o.id)
        if r and _one(db,Case,o.id).state!='cancelled' and _first(db,ClaimResolutionApproval,resolution_id=r.id) and not _first(db,ClaimApplication,resolution_id=r.id):raise HTTPException(409,'存在已批准待生效的理赔减免，请先完成责任调整再申请新开票')
def guard_receive(db,source,allocation_id):
    for r in db.scalars(select(ClaimResolution).join(ClaimResolutionApproval).where(ClaimResolution.allocation_id==allocation_id)):
        if _one(db,Case,r.case_id).state!='cancelled' and not _first(db,ClaimApplication,resolution_id=r.id):raise HTTPException(409,'此承担方已有获准调减，请先完成原款退款及责任生效')
def reserved_refund_amount(db,payment_id,excluding_resolution_id=None):
    amount=0
    for r in db.scalars(select(ClaimResolution).join(ClaimResolutionApproval)):
        if r.id==excluding_resolution_id or _one(db,Case,r.case_id).state=='cancelled' or _first(db,ClaimApplication,resolution_id=r.id):continue
        reserved=sum(s['amount_cents'] for s in r.refunds if s['original_id']==payment_id)
        paid=sum(_cash_amount(db,c) for c in _rows(db,ClaimCash,resolution_id=r.id,purpose='thirdparty_refund') if _one(db,PaymentLink,c.payment_link_id).original_id==payment_id)
        amount+=max(0,reserved-paid)
    return amount
def _remaining(db,payment):
    return payment.amount_cents-(db.scalar(select(func.coalesce(func.sum(PaymentLink.amount_cents),0)).where(PaymentLink.original_id==payment.id,PaymentLink.direction=='out')) or 0)

def create(db,user,key,v):
    _role(user,SERVICE)
    def run():
        from .repair_service import get_order as repair_get
        source=repair_get(db,user,v['source_case_id'])
        if source.version!=v['source_version']:raise HTTPException(409,'原维修已变化，请刷新后申请')
        if not source.data.get('quote_id') or source.state=='cancelled':raise HTTPException(409,'须先建立有效维修明细报价')
        from .aftercare_service import guard_source_action
        guard_source_action(db,user,source,'claims')
        party=v['party_type'];route=v['payment_route'];insurer=None;manufacturer=None
        if (party=='internal')!=(route=='internal'):raise HTTPException(422,'内部核价只走内部承担路径，不办理外部报销')
        if party=='insurer':
            from .master_data import require_active
            insurer=require_active(db,'insurers',v['payer_id']);name=insurer.name
        elif party=='manufacturer':
            manufacturer=_one(db,Reference,v['payer_id'])
            if manufacturer.category!='厂家' or not manufacturer.active:raise HTTPException(422,'请选择本店启用的厂家档案')
            name=manufacturer.name
        else:
            name=v['payer_name'].strip()
            if not name:raise HTTPException(422,'内部核价须明确实际承担主体')
        if db.scalar(select(ClaimOrder.id).join(Case,Case.id==ClaimOrder.id).where(ClaimOrder.source_case_id==source.id,ClaimOrder.party_type==party,ClaimOrder.payment_route==route,Case.state.not_in({'completed','cancelled'}))):raise HTTPException(409,'同原单同路径已有未结束的核赔申请，请先办理已有申请')
        source.updated_at=utcnow();db.flush()
        row=Case(number='HKC'+today().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:12].upper(),kind='claim',flow_version=2,state='working',
            title=source.title+' · '+name+'核赔',parent_id=source.id,customer_id=source.customer_id,owner_id=user.id,created_by=user.id,business_date=today(),due_date=today(),data={})
        db.add(row);db.flush();db.add(ClaimOrder(id=row.id,source_case_id=source.id,party_type=party,payment_route=route,party_name=name,
            insurer_id=insurer.id if insurer else None,manufacturer_id=manufacturer.id if manufacturer else None,
            source_snapshot={'number':source.number,'customer_id':source.customer_id,'flow_version':source.flow_version,'plate':source.data.get('plate','')},reason=v['reason']))
        db.flush();from .business_entity_service import freeze_derived_case_entity;freeze_derived_case_entity(db,user,row,source)
        _phase(db,row,user,'assessment');flow.log_event(db,user,row,'claims_create','建立原维修核赔申请');db.flush();return describe(db,user,row)
    return _execute(db,user,key,'create',v,run)

def _line_plan(db,source,lines,limits=None):
    quote=_one(db,RepairQuote,source.data['quote_id']);out=[];seen=set()
    for v in lines:
        line=_one(db,RepairLine,v['line_id']);cap=next((x for x in limits if x['line_id']==line.id),None) if limits is not None else None
        if line.quote_id!=quote.id or line.id in seen or (limits is not None and not cap):raise HTTPException(409,'核损明细须逐项引用当前报价，不得重复或加入未申请项目')
        seen.add(line.id);qty=cap['quantity_milli'] if cap else line.quantity_milli;amount=cap['amount_cents'] if cap else line.amount_cents
        if v['quantity_milli']>qty or v['amount_cents']>amount*v['quantity_milli']//qty:raise HTTPException(409,'核损数量或金额超过对应原报价／申请明细上限')
        out.append({**v,'line_key':line.line_key,'kind':line.kind,'name':line.name,'code':line.code,'unit':line.unit})
    return quote,out,sum(x['amount_cents'] for x in out)

def validate_allocation(db,source,values):
    """Called before freezing repair allocation; no claims preserves historical behavior."""
    for order in _rows(db,ClaimOrder,source_case_id=source.id):
        row=_one(db,Case,order.id)
        if row.state=='cancelled' or order.payment_route not in {'repair_receivable','internal'}:continue
        amount,_=_approved_amount(db,row,order);a=next((v for v in values if v['payer_type']==order.party_type),None)
        if amount==0 and a is None:continue
        if not a or a['amount_cents']!=amount or (order.party_type!='internal' and a.get('payer_id')!=(order.insurer_id or order.manufacturer_id)) or (order.party_type=='internal' and a.get('payer_name')!=order.party_name):raise HTTPException(409,'已建立核赔申请：原维修承担须与当前获准核价金额及单位一致；拒赔部分请明确分配到客户或内部')
def bind_after_allocation(db,user,source):
    for order in _rows(db,ClaimOrder,source_case_id=source.id):
        row=_one(db,Case,order.id)
        if row.state=='cancelled' or order.payment_route not in {'repair_receivable','internal'} or _first(db,ClaimBinding,case_id=row.id):continue
        amount,result_id=_approved_amount(db,row,order)
        if amount==0:
            _phase(db,row,user,'completed');continue
        allocation=_allocation(db,order);a=_assessment(db,row)
        db.add(ClaimBinding(case_id=row.id,allocation_id=allocation.id,assessment_id=a.id,result_id=result_id,approved_cents=amount));_phase(db,row,user,'bound')
def sync_source(db,user,source):
    from .repair_service import _allocation_due
    for order in _rows(db,ClaimOrder,source_case_id=source.id):
        row=_one(db,Case,order.id);binding=_first(db,ClaimBinding,case_id=row.id)
        if row.data.get('phase')=='bound' and binding and _allocation_due(db,source,_one(db,RepairAllocation,binding.allocation_id))==0:_phase(db,row,user,'completed')

def _cash(db,user,row,order,v,direction,source=None,original=None,required_account=None,*,original_cash_id=None):
    _proof(db,user,row,v['evidence_id'],True);account=_one(db,Account,v['account_id'])
    if not account.active:raise HTTPException(422,'原路径账户已停用，请先核实并恢复账户')
    if required_account and account.id!=required_account:raise HTTPException(409,'必须使用本笔原报销款对应的原账户，不允许跨路径换款')
    if db.scalar(select(PaymentLink.id).where(PaymentLink.account_id==account.id,PaymentLink.reference==v['reference'])) or db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==v['reference'])):raise HTTPException(409,'该账户凭证号已使用，请勿重复登记现金')
    if original and (original.direction!='in' or v['amount_cents']>_remaining(db,original)):raise HTTPException(409,'实际转付或退还超过此笔原到账的未使用余额')
    account.updated_at=utcnow();target=source or row
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,row,account.id,today(),original_cash_id=original.cash_id if original else original_cash_id)
    cash=CashEntry(doc_no='CL-'+uuid.uuid4().hex[:20].upper(),business_date=today(),created_by=user.id,approval_state='approved',direction=direction,
        category='workflow_refund' if source else 'claim_pass_through',amount_cents=v['amount_cents'],account=account.name,counterparty=order.party_name,
        payment_method='cash' if account.account_type=='cash' else 'bank',voucher_no=v['reference'],note='理赔 '+row.number+'；原维修 '+str(order.source_case_id))
    db.add(cash);db.flush();record_cash_entity(db,user,row,cash,account.id,original_cash_id=original.cash_id if original else original_cash_id);link=PaymentLink(case_id=target.id,cash_id=cash.id,account_id=account.id,direction=direction,amount_cents=v['amount_cents'],
        reference=v['reference'],business_date=today(),original_id=original.id if original else None);db.add(link);db.flush();return link

def _return_plan(db,row,key,approved=False):
    plan=_one(db,ClaimReturnPlan,key)
    if plan.case_id!=row.id or _first(db,ClaimReturnCancellation,plan_id=plan.id):raise HTTPException(409,'原报销返还方案不属于本单或已撤销')
    if approved and not _first(db,ClaimReturnApproval,plan_id=plan.id):raise HTTPException(409,'原报销返还方案尚未经过独立批准')
    return plan
def _returned(db,order,original_id,plan_id=None,external=False):
    if order.payment_route=='customer_direct':
        rows=_rows(db,ClaimCustomerPayment,case_id=order.id,purpose='return',original_id=original_id)
        return sum(r.amount_cents for r in rows if plan_id is None or r.return_plan_id==plan_id)
    original=_one(db,ClaimCash,original_id)
    if original.purpose=='pass_receive':
        return sum(_cash_amount(db,r) for r in _rows(db,ClaimCash,case_id=order.id,purpose='unused_refund',original_id=original_id) if plan_id is None or r.return_plan_id==plan_id)
    rows=_rows(db,ClaimCash,case_id=order.id,purpose='customer_return',original_id=original_id)
    if plan_id is not None:rows=[r for r in rows if r.return_plan_id==plan_id]
    if external:return sum(_cash_amount(db,c) for r in rows for c in _rows(db,ClaimCash,case_id=order.id,purpose='party_return',original_id=r.id))
    return sum(_cash_amount(db,r) for r in rows)
def _original_payout(db,order,key):
    model=ClaimCustomerPayment if order.payment_route=='customer_direct' else ClaimCash;row=_one(db,model,key)
    if row.case_id!=order.id or row.purpose not in (('reimbursement',) if model==ClaimCustomerPayment else ('pass_pay','pass_receive')):raise HTTPException(409,'只能选择本理赔路径的原实际报销款或未转付的第三方到账')
    return row,row.amount_cents if model==ClaimCustomerPayment else _cash_amount(db,row)
def _return_remaining(db,order,key,excluding=None):
    original,amount=_original_payout(db,order,key);amount-=_returned(db,order,key)
    if order.payment_route=='customer_via_store' and original.purpose=='pass_receive':
        amount-=sum(_cash_amount(db,c) for c in _rows(db,ClaimCash,case_id=order.id,purpose='pass_pay',original_id=key))
    for plan in _rows(db,ClaimReturnPlan,case_id=order.id):
        if plan.id==excluding or _first(db,ClaimReturnCancellation,plan_id=plan.id) or not _first(db,ClaimReturnApproval,plan_id=plan.id):continue
        held=sum(x['amount_cents'] for x in plan.selections if x['original_id']==key)
        amount-=max(0,held-_returned(db,order,key,plan.id))
    return amount
def _sync_return(db,user,row,order,plan):
    if all(_returned(db,order,s['original_id'],plan.id,True)==s['amount_cents'] for s in plan.selections):flow.finish_task(db,row,'claim_return_execute_'+str(plan.id),user)

def command(db,user,key,request_id,version,source_version,action,v):
    _role(user,ROLES[action])
    def run():
        row=get_order(db,user,key);order=_one(db,ClaimOrder,key);source=_source(db,order)
        if row.version!=version or source.version!=source_version:raise HTTPException(409,'原维修或理赔已变化，请刷新后核对办理')
        source.updated_at=utcnow();row.updated_at=utcnow();db.flush();phase=row.data.get('phase');before=row.state
        if row.state=='cancelled':raise HTTPException(409,'已取消理赔不能继续办理')
        if action in {'bind','resolution','resolution_approve','resolution_apply','thirdparty_refund','reimbursement_approve','direct_confirm','pass_receive','pass_pay'}:
            _guard_other_adjustments(db,user,source)
        if action not in {'return_plan','return_approve','return_cancel','direct_return','customer_return','party_return','unused_refund','close'} and row.state=='completed':raise HTTPException(409,'已完成的理赔只可按原款办理返还，不得再次付款')
        if action=='assess':
            if phase not in {'assessment','approval','send','supplement','ready'} or _first(db,ClaimBinding,case_id=row.id) or _first(db,ClaimResolution,case_id=row.id) or _first(db,ClaimReimbursementApproval,case_id=row.id):raise HTTPException(409,'已绑定承担或财务方案的核价不能换版')
            quote,lines,amount=_line_plan(db,source,v['lines'])
            if amount<=0:raise HTTPException(422,'申请核价合计须大于零')
            a=ClaimAssessment(case_id=row.id,revision=len(_rows(db,ClaimAssessment,case_id=row.id))+1,quote_id=quote.id,quote_digest=quote.digest,
                amount_cents=amount,lines=lines,reason=v['reason'],actor_id=user.id);db.add(a);db.flush();flow.set_data(row,assessment_id=a.id,result_id=None);row.amount_cents=amount;_phase(db,row,user,'approval')
        elif action=='approve':
            if phase!='approval':raise HTTPException(409,'当前不在核价复核步骤')
            _task(db,user,row,'claim_approve');a=_assessment(db,row)
            if user.id in {a.actor_id,row.created_by}:raise HTTPException(403,'申请人或核价人不能审批自己的核价，管理员也须独立复核')
            _proof(db,user,row,v['evidence_id']);db.add(ClaimApproval(assessment_id=a.id,evidence_id=v['evidence_id'],actor_id=user.id,reason=v['reason']));_phase(db,row,user,'ready' if order.party_type=='internal' else 'send')
        elif action=='transmit':
            if phase not in {'send','supplement'}:raise HTTPException(409,'须先复核核价或取得补件要求')
            _task(db,user,row,'claim_transmit');a=_assessment(db,row);_proof(db,user,row,v['evidence_id']);supplement=v.get('supplement_result_id')
            if phase=='supplement':
                if not supplement:raise HTTPException(409,'补件必须选择当前外部补件要求')
                result=_one(db,ClaimResult,supplement or 0)
                if result.id!=row.data.get('result_id') or result.case_id!=row.id or result.outcome!='need_documents' or result.assessment_id!=a.id:raise HTTPException(409,'补件必须对应当前外部补件要求与核价版本')
            elif supplement:raise HTTPException(409,'首次提交不能借用其他补件记录')
            if date.fromisoformat(v['submitted_on'])>today():raise HTTPException(422,'实际提交日期不能在未来')
            db.add(ClaimTransmission(case_id=row.id,assessment_id=a.id,supplement_result_id=supplement,external_reference=v['external_reference'],submitted_on=date.fromisoformat(v['submitted_on']),evidence_id=v['evidence_id'],actor_id=user.id));_phase(db,row,user,'waiting')
        elif action=='result':
            if phase!='waiting':raise HTTPException(409,'必须先确认实际外部提交')
            _task(db,user,row,'claim_result');a=_assessment(db,row);t=_one(db,ClaimTransmission,v['transmission_id'])
            if t.case_id!=row.id or t.assessment_id!=a.id or _first(db,ClaimResult,transmission_id=t.id):raise HTTPException(409,'外部结果不属于当前未结提交')
            _proof(db,user,row,v['evidence_id']);_,lines,amount=_line_plan(db,source,v['lines'],a.lines)
            outcome=v['outcome'];when=date.fromisoformat(v['result_on'])
            if when<t.submitted_on or when>today():raise HTTPException(422,'实际核赔日期须在提交日与今天之间')
            if outcome in {'rejected','need_documents'} and amount!=0 or outcome=='approved' and amount!=a.amount_cents or outcome=='partial' and not 0<amount<a.amount_cents:raise HTTPException(422,'核赔结果与逐项批准金额不一致，拒赔或补件不形成批准金额')
            result=ClaimResult(case_id=row.id,assessment_id=a.id,transmission_id=t.id,outcome=outcome,amount_cents=amount,lines=lines,result_on=when,result=v['result'],evidence_id=v['evidence_id'],actor_id=user.id);db.add(result);db.flush();flow.set_data(row,result_id=result.id);_phase(db,row,user,'supplement' if outcome=='need_documents' else 'ready')
        elif action=='bind':
            if phase!='ready' or order.payment_route not in {'repair_receivable','internal'}:raise HTTPException(409,'当前路径不办理原维修承担绑定')
            _proof(db,user,row,v['evidence_id']);amount,result_id=_approved_amount(db,row,order);allocation=_allocation(db,order)
            from .repair_service import allocation_amount
            if allocation_amount(db,source,allocation)!=amount:raise HTTPException(409,'已冻结承担与核赔结果不一致；调减须申请明确的内部吸收及原款退回方案')
            db.add(ClaimBinding(case_id=row.id,allocation_id=allocation.id,assessment_id=_assessment(db,row).id,result_id=result_id,approved_cents=amount));_phase(db,row,user,'bound');sync_source(db,user,source)
        elif action=='resolution':
            if phase!='ready' or order.payment_route!='repair_receivable':raise HTTPException(409,'只有原维修第三方承担可申请调减')
            allocation=_allocation(db,order);result=_result(db,row)
            from .repair_service import allocation_amount,_cash_paid
            original=allocation_amount(db,source,allocation);reduction=original-result.amount_cents;refund=max(0,_cash_paid(db,allocation)-result.amount_cents)
            if reduction<=0:raise HTTPException(409,'本版只允许第三方减少与等额内部吸收；增加客户债务必须另获客户授权')
            _proof(db,user,row,v['evidence_id']);_validate_refunds(db,allocation,v['refunds'],refund)
            db.add(ClaimResolution(case_id=row.id,allocation_id=allocation.id,result_id=result.id,original_cents=original,reduction_cents=reduction,refund_cents=refund,
                internal_bearer=v['internal_bearer'],refunds=v['refunds'],reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id));db.flush();_phase(db,row,user,'resolution_review')
        elif action=='resolution_approve':
            if phase!='resolution_review':raise HTTPException(409,'当前没有待复核责任调整')
            _task(db,user,row,'claim_resolution_approve');r=_first(db,ClaimResolution,case_id=row.id)
            if r.actor_id==user.id:raise HTTPException(403,'责任调整须另一位主管独立批准')
            _check_resolution(db,source,r);_validate_refunds(db,_one(db,RepairAllocation,r.allocation_id),r.refunds,r.refund_cents);_proof(db,user,row,v['evidence_id'])
            db.add(ClaimResolutionApproval(resolution_id=r.id,evidence_id=v['evidence_id'],actor_id=user.id));_phase(db,row,user,'resolution_execute')
        elif action in {'thirdparty_refund','resolution_apply'}:
            if phase!='resolution_execute':raise HTTPException(409,'须先独立批准责任调整')
            _task(db,user,row,'claim_resolve');r=_first(db,ClaimResolution,case_id=row.id);_check_resolution(db,source,r);allocation=_one(db,RepairAllocation,r.allocation_id)
            if action=='thirdparty_refund':
                original=_one(db,PaymentLink,v['original_id']);planned=sum(s['amount_cents'] for s in r.refunds if s['original_id']==original.id)
                done=sum(_cash_amount(db,c) for c in _rows(db,ClaimCash,resolution_id=r.id) if _one(db,PaymentLink,c.payment_link_id).original_id==original.id)
                if v['amount_cents']>planned-done:raise HTTPException(409,'退款超过本方案选定的原第三方款项余额')
                p=_cash(db,user,row,order,v,'out',source,original,original.account_id);db.add(RepairPayment(allocation_id=allocation.id,payment_link_id=p.id,evidence_id=v['evidence_id']))
                db.add(ClaimCash(case_id=row.id,purpose=action,payment_link_id=p.id,resolution_id=r.id,evidence_id=v['evidence_id'],actor_id=user.id))
            else:
                from .repair_service import _cash_paid
                if sum(_cash_amount(db,c) for c in _rows(db,ClaimCash,resolution_id=r.id))!=r.refund_cents or _cash_paid(db,allocation)>r.original_cents-r.reduction_cents:raise HTTPException(409,'须先完成所有计划内原款实际退款，不能只凭批准减掉已经收到的钱')
                _proof(db,user,row,v['evidence_id'],True);applied=ClaimApplication(resolution_id=r.id,evidence_id=v['evidence_id'],actor_id=user.id,business_date=today());db.add(applied);db.flush()
                db.add_all([ClaimResponsibility(application_id=applied.id,source_case_id=source.id,allocation_id=allocation.id,payer_type=allocation.payer_type,payer_name=allocation.payer_name,amount_cents=-r.reduction_cents),
                    ClaimResponsibility(application_id=applied.id,source_case_id=source.id,payer_type='internal',payer_name=r.internal_bearer,amount_cents=r.reduction_cents)])
                _phase(db,row,user,'completed')
        elif action=='reimbursement_approve':
            if phase!='ready' or order.payment_route not in {'customer_direct','customer_via_store'}:raise HTTPException(409,'本步骤只批准客户报销路径')
            _task(db,user,row,'claim_reimbursement_approve');result=_result(db,row)
            if user.id in {row.created_by,_assessment(db,row).actor_id,result.actor_id}:raise HTTPException(403,'客户报销额度须另一位主管独立复核')
            if result.amount_cents<=0 or result.amount_cents>customer_reimbursement_available(db,source):raise HTTPException(409,'报销超过原客户实际现金净付款扣除其他报销占额后的余额，会员权益不折现报销')
            _proof(db,user,row,v['evidence_id']);db.add(ClaimReimbursementApproval(case_id=row.id,result_id=result.id,amount_cents=result.amount_cents,evidence_id=v['evidence_id'],actor_id=user.id));_phase(db,row,user,'reimbursement')
        elif action in {'direct_confirm','pass_receive','pass_pay'}:
            if phase!='reimbursement':raise HTTPException(409,'须先独立批准客户报销额度')
            _task(db,user,row,'claim_reimburse');approval=_first(db,ClaimReimbursementApproval,case_id=row.id)
            if approval.amount_cents>customer_reimbursement_available(db,source,row.id):raise HTTPException(409,'原客户现金净额已经变化，须先核对其他退款或报销')
            if action=='direct_confirm':
                if order.payment_route!='customer_direct' or v['amount_cents']>approval.amount_cents-_direct_total(db,row.id,'reimbursement'):raise HTTPException(409,'直接报销路径或剩余核准金额不符')
                _proof(db,user,row,v['evidence_id'],True);db.add(ClaimCustomerPayment(case_id=row.id,purpose='reimbursement',amount_cents=v['amount_cents'],business_date=today(),evidence_id=v['evidence_id'],actor_id=user.id))
            else:
                if order.payment_route!='customer_via_store':raise HTTPException(409,'此单不是经店转付路径，不得登记公司现金')
                original=None;parent=None
                if action=='pass_receive':
                    if v['amount_cents']>approval.amount_cents-_cash_total(db,row.id,'pass_receive'):raise HTTPException(409,'实际第三方到账超过原核准报销额度')
                else:
                    parent=_one(db,ClaimCash,v['original_id'])
                    if parent.case_id!=row.id or parent.purpose!='pass_receive':raise HTTPException(409,'转付只能引用本单原第三方实际到账')
                    if v['amount_cents']>_return_remaining(db,order,parent.id):raise HTTPException(409,'原到账余额已用或已获准原路退给第三方，不能再转付客户')
                    original=_one(db,PaymentLink,parent.payment_link_id)
                p=_cash(db,user,row,order,v,'in' if action=='pass_receive' else 'out',original=original,required_account=original.account_id if original else None)
                db.add(ClaimCash(case_id=row.id,purpose=action,payment_link_id=p.id,original_id=parent.id if parent else None,evidence_id=v['evidence_id'],actor_id=user.id))
            db.flush();paid=_direct_total(db,row.id,'reimbursement') if order.payment_route=='customer_direct' else _cash_total(db,row.id,'pass_pay')
            if paid==approval.amount_cents:_phase(db,row,user,'completed')
        elif action=='return_plan':
            if order.payment_route not in {'customer_direct','customer_via_store'}:raise HTTPException(409,'本步骤只纠正原客户实际报销')
            seen=set()
            for s in v['selections']:
                if s['original_id'] in seen or s['amount_cents']>_return_remaining(db,order,s['original_id']):raise HTTPException(409,'返还超过原实际报销尚未退还和未被其他批准方案占用的余额')
                seen.add(s['original_id'])
            _proof(db,user,row,v['evidence_id']);plan=ClaimReturnPlan(case_id=row.id,amount_cents=sum(s['amount_cents'] for s in v['selections']),selections=v['selections'],reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id)
            db.add(plan);db.flush();_manager_task(db,row,'claim_return_review_'+str(plan.id),'独立复核原客户报销返还',{user.id})
        elif action=='return_approve':
            plan=_return_plan(db,row,v['plan_id']);_task(db,user,row,'claim_return_review_'+str(plan.id))
            if user.id==plan.actor_id:raise HTTPException(403,'原报销返还须另一位主管独立批准')
            for s in plan.selections:
                if s['amount_cents']>_return_remaining(db,order,s['original_id'],plan.id):raise HTTPException(409,'原报销剩余可退额已被其他方案使用')
            _proof(db,user,row,v['evidence_id']);db.add(ClaimReturnApproval(plan_id=plan.id,evidence_id=v['evidence_id'],actor_id=user.id));flow.finish_task(db,row,'claim_return_review_'+str(plan.id),user)
            flow.ensure_task(db,row,'claim_return_execute_'+str(plan.id),'核对原报销实际原路返还','finance',reopen=True)
        elif action=='return_cancel':
            plan=_return_plan(db,row,v['plan_id'])
            if any(_returned(db,order,s['original_id'],plan.id)>0 for s in plan.selections):raise HTTPException(409,'已发生实际返还，不能取消计划抹除资金；请完成原路径退给第三方')
            _proof(db,user,row,v['evidence_id']);db.add(ClaimReturnCancellation(plan_id=plan.id,reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
            flow.finish_task(db,row,'claim_return_review_'+str(plan.id),user,'cancelled');flow.finish_task(db,row,'claim_return_execute_'+str(plan.id),user,'cancelled')
        elif action in {'direct_return','customer_return','party_return','unused_refund'}:
            plan=_return_plan(db,row,v['plan_id'],True);_task(db,user,row,'claim_return_execute_'+str(plan.id))
            if action=='unused_refund':
                if order.payment_route!='customer_via_store':raise HTTPException(409,'直接报销没有门店代收款可退')
                original,amount=_original_payout(db,order,v['original_id']);selected=sum(s['amount_cents'] for s in plan.selections if s['original_id']==original.id)
                if original.purpose!='pass_receive' or v['amount_cents']>selected-_returned(db,order,original.id,plan.id):raise HTTPException(409,'只能退本方案选定的未转付第三方原到账余额')
                incoming=_one(db,PaymentLink,original.payment_link_id);p=_cash(db,user,row,order,v,'out',original=incoming,required_account=incoming.account_id)
                db.add(ClaimCash(case_id=row.id,purpose=action,payment_link_id=p.id,original_id=original.id,return_plan_id=plan.id,evidence_id=v['evidence_id'],actor_id=user.id))
            elif action=='party_return':
                if order.payment_route!='customer_via_store':raise HTTPException(409,'直接报销返还不发生公司现金')
                incoming=_one(db,ClaimCash,v['original_id'])
                if incoming.case_id!=row.id or incoming.purpose!='customer_return' or incoming.return_plan_id!=plan.id:raise HTTPException(409,'只能退还本方案已实际收到的客户返还款')
                original=_one(db,PaymentLink,incoming.payment_link_id);p=_cash(db,user,row,order,v,'out',original=original,required_account=original.account_id)
                db.add(ClaimCash(case_id=row.id,purpose=action,payment_link_id=p.id,original_id=incoming.id,return_plan_id=plan.id,evidence_id=v['evidence_id'],actor_id=user.id))
            else:
                original,amount=_original_payout(db,order,v['original_id']);selected=sum(s['amount_cents'] for s in plan.selections if s['original_id']==original.id)
                if v['amount_cents']>selected-_returned(db,order,original.id,plan.id):raise HTTPException(409,'实际返还超过本方案所选原报销余额')
                if action=='direct_return':
                    if order.payment_route!='customer_direct':raise HTTPException(409,'经店转付必须实际退回门店并原路退第三方')
                    _proof(db,user,row,v['evidence_id'],True);db.add(ClaimCustomerPayment(case_id=row.id,purpose='return',original_id=original.id,return_plan_id=plan.id,amount_cents=v['amount_cents'],business_date=today(),evidence_id=v['evidence_id'],actor_id=user.id))
                else:
                    if order.payment_route!='customer_via_store':raise HTTPException(409,'直接报销返还不发生公司现金')
                    if original.purpose!='pass_pay':raise HTTPException(409,'客户实际退回只能关联原已转付客户款；未转付第三方款须原路直接退还')
                    link=_one(db,PaymentLink,original.payment_link_id);p=_cash(db,user,row,order,v,'in',required_account=link.account_id,original_cash_id=link.cash_id)
                    db.add(ClaimCash(case_id=row.id,purpose=action,payment_link_id=p.id,original_id=original.id,return_plan_id=plan.id,evidence_id=v['evidence_id'],actor_id=user.id))
            db.flush();_sync_return(db,user,row,order,plan)
        elif action in {'close','cancel'}:
            if _first(db,ClaimClosure,case_id=row.id):raise HTTPException(409,'理赔额度已结案')
            r=_first(db,ClaimResolution,case_id=row.id)
            if r and (action!='cancel' or _rows(db,ClaimCash,resolution_id=r.id) or _first(db,ClaimApplication,resolution_id=r.id)):raise HTTPException(409,'已发生原第三方退款或责任生效，不能取消；请完成原款处理')
            a=_first(db,ClaimReimbursementApproval,case_id=row.id);paid=_direct_total(db,row.id,'reimbursement') if order.payment_route=='customer_direct' else _cash_total(db,row.id,'pass_pay')
            if action=='cancel' and (paid or _cash_total(db,row.id,'pass_receive') or _first(db,ClaimBinding,case_id=row.id)):raise HTTPException(409,'已有实际报销、到账或原承担绑定，不能普通取消')
            if _cash_total(db,row.id,'pass_receive')!=_cash_total(db,row.id,'pass_pay')+_cash_total(db,row.id,'unused_refund') or _cash_total(db,row.id,'customer_return')!=_cash_total(db,row.id,'party_return'):raise HTTPException(409,'仍有经店报销款尚未实际转付或退回第三方，不能结案')
            _proof(db,user,row,v['evidence_id']);db.add(ClaimClosure(case_id=row.id,unused_cents=a.amount_cents-paid if a else 0,reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id));_phase(db,row,user,'cancelled' if action=='cancel' else 'completed')
        else:raise HTTPException(404,'理赔步骤不存在')
        db.flush();flow.log_event(db,user,row,'claims_'+action,LABELS[action],before,{'source_case_id':source.id,**({'evidence_id':v['evidence_id']} if 'evidence_id' in v else {})})
        if action in {'thirdparty_refund','resolution_apply'}:
            from .repair_service import sync_after_member
            from .invoice_service import sync_source as sync_invoice
            sync_after_member(db,user,source);sync_invoice(db,user,source)
        db.flush();return describe(db,user,row)
    return _execute(db,user,request_id,action,{'case_id':key,'version':version,'source_version':source_version,'values':v},run)

def _validate_refunds(db,allocation,selections,total):
    if sum(s['amount_cents'] for s in selections)!=total:raise HTTPException(409,'原款退款选择须恰好覆盖实际已收超过新承担的部分')
    seen=set()
    from .aftercare_service import refund_reservation_amount
    for s in selections:
        p=_one(db,PaymentLink,s['original_id']);rp=_first(db,RepairPayment,payment_link_id=p.id)
        if p.id in seen or not rp or rp.allocation_id!=allocation.id or p.direction!='in':raise HTTPException(409,'须选择此承担方的原实际收款，不得使用客户或其他第三方款项')
        if s['amount_cents']>_remaining(db,p)-reserved_refund_amount(db,p.id)-refund_reservation_amount(db,p.id):raise HTTPException(409,'原款未退款余额不足或已被其他方案占用')
        seen.add(p.id)
def _check_resolution(db,source,r):
    from .repair_service import allocation_amount
    if allocation_amount(db,source,_one(db,RepairAllocation,r.allocation_id))!=r.original_cents:raise HTTPException(409,'原承担净额已经变化，请重新核对方案，不能覆盖已生效调整')

def _dump(row):
    return {c.key:(v.isoformat() if isinstance(v,date) else v) for c in row.__table__.columns if c.key!='store_id' for v in [getattr(row,c.key)]}
def describe(db,user,row):
    _role(user,READ);order=_one(db,ClaimOrder,row.id);source=_source(db,order)
    result={'id':row.id,'number':row.number,'title':row.title,'state':row.state,'version':row.version,'phase':row.data.get('phase'),
        'phase_label':PHASES.get(row.data.get('phase'),''),'amount_cents':row.amount_cents,'source_id':source.id,'source_version':source.version,'source_number':source.number,
        'order':_dump(order),'data':row.data,'source_quote_id':source.data.get('quote_id'),'customer_available_cents':customer_reimbursement_available(db,source,row.id),
        'reimbursement_usage_cents':_reimbursement_usage(db,order),'actions':[k for k,v in ROLES.items() if user.role in v],
        'tasks':[_dump(t) for t in _rows(db,Task,case_id=row.id)]}
    result['source_lines']=[_dump(l) for l in _rows(db,RepairLine,quote_id=source.data.get('quote_id'))]
    for name,model in [('assessments',ClaimAssessment),('transmissions',ClaimTransmission),('results',ClaimResult),('bindings',ClaimBinding),('resolutions',ClaimResolution),
                       ('reimbursement_approvals',ClaimReimbursementApproval),('cash',ClaimCash),('customer_payments',ClaimCustomerPayment),('return_plans',ClaimReturnPlan),('closures',ClaimClosure)]:
        result[name]=[_dump(r) for r in _rows(db,model,case_id=row.id)]
    for plan in result['return_plans']:
        plan['approved']=bool(_first(db,ClaimReturnApproval,plan_id=plan['id']));plan['cancelled']=bool(_first(db,ClaimReturnCancellation,plan_id=plan['id']))
        plan['returned_cents']=sum(_returned(db,order,s['original_id'],plan['id']) for s in plan['selections'])
        plan['returned_external_cents']=sum(_returned(db,order,s['original_id'],plan['id'],True) for s in plan['selections'])
        plan['original_purposes']=list({_original_payout(db,order,s['original_id'])[0].purpose for s in plan['selections']})
    for cash in result['cash']:
        p=_one(db,PaymentLink,cash['payment_link_id']);cash.update({'amount_cents':p.amount_cents,'account_id':p.account_id,'direction':p.direction,'reference':p.reference,'business_date':p.business_date.isoformat(),'remaining_cents':_remaining(db,p) if p.direction=='in' else 0})
    result['source_allocations']=[{**_dump(a),'net_cents':a.amount_cents+allocation_delta(db,a.id)} for a in _rows(db,RepairAllocation,case_id=source.id)]
    result['source_payments']=[{**_dump(p),'allocation_id':rp.allocation_id,'remaining_cents':_remaining(db,p)-reserved_refund_amount(db,p.id)} for p,rp in db.execute(select(PaymentLink,RepairPayment).join(RepairPayment,RepairPayment.payment_link_id==PaymentLink.id).where(PaymentLink.case_id==source.id,PaymentLink.direction=='in'))]
    return result
def list_orders(db,user,page=1):
    _role(user,READ);single_store(db);query=flow.case_query(user).where(Case.kind=='claim',Case.flow_version==2)
    total=db.scalar(select(func.count()).select_from(query.subquery()));rows=list(db.scalars(query.order_by(Case.id.desc()).offset((page-1)*30).limit(30)))
    return {'items':[describe(db,user,r) for r in rows],'page':page,'total':total}
def sources(db,user,page=1):
    _role(user,READ);single_store(db)
    rows=list(db.scalars(flow.case_query(user).where(Case.kind=='repair',Case.flow_version.in_([3,4]),Case.state!='cancelled').order_by(Case.id.desc()).offset((page-1)*50).limit(50)))
    return {'items':[{'id':r.id,'number':r.number,'title':r.title,'version':r.version,'amount_cents':r.amount_cents,'state':r.state} for r in rows if r.data.get('quote_id')],'page':page}
