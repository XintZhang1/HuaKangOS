"""Original principal and commission paths. No commit; caller owns case version."""
import uuid
from sqlalchemy import select
from fastapi import HTTPException
from .db import today,utcnow
from .models import CashEntry
from .flow_models import Account,PaymentLink,FileAsset
from .insurance_models import *
from . import insurance_service as s

CASH_CATEGORIES={'premium':'workflow_ins_premium','premium_refund':'workflow_ins_premium_refund',
    'disburse':'workflow_ins_disburse','insurer_return':'workflow_ins_insurer_return',
    'commission_receive':'workflow_ins_commission_in','commission_return':'workflow_ins_commission_out'}

def account_for_tender(db,t):
    if t.payment_link_id:return s._one(db,PaymentLink,t.payment_link_id).account_id
    from .business_finance_models import FinanceCreditLink,FinanceAdvanceEntry,FinanceAdvance
    credit=s._one(db,FinanceCreditLink,t.credit_link_id);entry=s._one(db,FinanceAdvanceEntry,credit.entry_id);return s._one(db,FinanceAdvance,entry.advance_id).account_id
def _cash(db,user,row,v,direction,category,account_id=None,*,original_cash_id=None):
    account=db.scalar(select(Account).where(Account.id==v['account_id']).with_for_update())
    if not account or not account.active or (account_id is not None and account.id!=account_id):raise HTTPException(409,'须选择本店实际原资金账户')
    account.updated_at=utcnow();db.flush()
    if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==v['reference'])) or db.scalar(select(PaymentLink.id).where(PaymentLink.account_id==account.id,PaymentLink.reference==v['reference'])):raise HTTPException(409,'该账户银行流水已登记，不能重复作为保险收支')
    from .business_entity_service import require_account_entity,record_cash_entity
    require_account_entity(db,user,row,account.id,s._date(v['business_date']),original_cash_id=original_cash_id)
    q=s._quote(db,row);cash=CashEntry(doc_no='INS-'+uuid.uuid4().hex[:20],business_date=s._date(v['business_date']),created_by=user.id,approval_state='approved',direction=direction,category=CASH_CATEGORIES[category],amount_cents=v['amount_cents'],account=account.name,counterparty=q.insurer_snapshot['name'] if category!='premium' and category!='premium_refund' else s._one(db,InsuranceOrder,row.id).customer_name,payment_method=account.account_type,voucher_no=v['reference'],note='保险原单 '+row.number)
    db.add(cash);db.flush();record_cash_entity(db,user,row,cash,account.id,original_cash_id=original_cash_id);return cash
def _tender(db,user,row,amount,evidence_id,payment=None,credit=None,original=None):
    t=InsuranceTender(case_id=row.id,amount_cents=amount,payment_link_id=payment.id if payment else None,credit_link_id=credit.id if credit else None,original_id=original.id if original else None,evidence_id=evidence_id,actor_id=user.id)
    db.add(t);db.flush();return t
def _linked_proof(db,user,row,evidence_id):
    asset=s._one(db,FileAsset,evidence_id)
    if asset.generated or asset.category!='receipt':raise HTTPException(409,'保险资金须引用实际收款凭据')
    if asset.case_id!=row.id:
        from .business_finance_sources import source_evidence_allowed
        if not source_evidence_allowed(db,row,asset):raise HTTPException(409,'资金凭据未通过本保险单的明确集中分配或预收抵用关联')
    from .file_security import require_usable
    require_usable(db,asset)
def _incoming(db,user,row,amount,evidence_id,payment=None,credit=None):
    s.guard_source_adjustment(db,row);q=s._quote(db,row,True)
    if q.collection_mode!='store_collect':raise HTTPException(409,'客户直付不能使用门店资金来源')
    remaining=q.premium_cents-sum(t.amount_cents for t in s._rows(db,InsuranceTender,case_id=row.id))
    if not 0<amount<=remaining:raise HTTPException(409,'本次分配超过本单客户尚欠保费')
    _linked_proof(db,user,row,evidence_id)
    return _tender(db,user,row,amount,evidence_id,payment,credit)
def record_collection(db,user,row,payment_link,evidence_id,*,original_payment=None,correction=False):
    _linked_proof(db,user,row,evidence_id)
    if payment_link.case_id!=row.id or s._first(db,InsuranceTender,payment_link_id=payment_link.id):raise HTTPException(409,'此原款已经分配或不属于本保险单')
    if payment_link.direction=='in':return _incoming(db,user,row,payment_link.amount_cents,evidence_id,payment=payment_link)
    original=s._first(db,InsuranceTender,payment_link_id=original_payment.id) if original_payment else None
    if not correction or not original or original.amount_cents<=0 or payment_link.original_id!=original_payment.id:raise HTTPException(409,'客户退款须沿已批准撤保方案，不得通用冲销')
    s.guard_source_adjustment(db,row)
    if s._spent(db,original) or payment_link.amount_cents!=s._unrefunded(db,original):raise HTTPException(409,'已代缴原保费须先实际追回；更正只能冲原款完整剩余额')
    return _tender(db,user,row,-payment_link.amount_cents,evidence_id,payment=payment_link,original=original)
def record_advance_credit(db,user,row,credit_link,evidence_id):
    if credit_link.case_id!=row.id or credit_link.amount_cents<=0 or s._first(db,InsuranceTender,credit_link_id=credit_link.id):raise HTTPException(409,'预收来源不属于本保险单或已分配')
    return _incoming(db,user,row,credit_link.amount_cents,evidence_id,credit=credit_link)
def _reserved(db,t,exclude=None):
    reserved=0
    for plan in s._rows(db,InsuranceTermination,case_id=t.case_id):
        review=s._first(db,InsuranceTerminationReview,plan_id=plan.id)
        if plan.id==exclude or not review or review.decision!='approved' or s._first(db,InsuranceTerminationCancellation,plan_id=plan.id):continue
        reserved+=sum(x['amount_cents'] for x in plan.returns if x['tender_id']==t.id)-sum(x.amount_cents for x in s._rows(db,InsuranceCustomerRefund,plan_id=plan.id,original_tender_id=t.id))
    return reserved
def refund_limit(db,row,plan,t):
    target=sum(x['amount_cents'] for x in plan.returns if x['tender_id']==t.id)
    done=sum(x.amount_cents for x in s._rows(db,InsuranceCustomerRefund,plan_id=plan.id,original_tender_id=t.id))
    return min(target-done,s._unrefunded(db,t)-s._spent(db,t)-_reserved(db,t,plan.id))
def assert_advance_return(db,user,row,credit_link,amount,evidence_id,plan_id):
    s._role(user,s.FINANCE);s.get_order(db,user,row.id);plan=s._plan(db,row,plan_id);t=s._first(db,InsuranceTender,credit_link_id=credit_link.id)
    if not s._first(db,InsuranceTerminationApplication,plan_id=plan.id) or not t or t.case_id!=row.id or t.amount_cents<=0 or not 0<amount<=refund_limit(db,row,plan,t):raise HTTPException(409,'预收回退须引用已生效撤保方案与原抵用可退额度')
    s.flow.file_exists(db,row,evidence_id,'receipt');return True
def _plan_check(db,row,plan):
    applied=s._applied(db,row);current=applied[-1].retained_cents if applied else s._quote(db,row).premium_cents
    if plan.retained_cents>current:raise HTTPException(409,'撤保保留额不能增加原客户保费')
    if s._policy(db,row) and plan.external_result!='terminated':raise HTTPException(409,'已经实际出保，必须重新核对真实退保结果，不能沿未出保方案结清')
    q=s._quote(db,row);paid=sum(t.amount_cents for t in s._rows(db,InsuranceTender,case_id=row.id));expected=max(0,paid-plan.retained_cents) if q.collection_mode=='store_collect' else 0
    existing=sum(_reserved(db,t,plan.id) for t in s._rows(db,InsuranceTender,case_id=row.id) if t.amount_cents>0)
    if sum(x['amount_cents'] for x in plan.returns)!=max(0,expected-existing):raise HTTPException(409,'客户原款分配已经变化，请撤回方案后重新核对')
    for selected in plan.returns:
        t=s._one(db,InsuranceTender,selected['tender_id'])
        if t.case_id!=row.id or t.amount_cents<=0 or selected['amount_cents']>s._unrefunded(db,t)-_reserved(db,t,plan.id):raise HTTPException(409,'原款可退额度不足或已被其他批准方案占用')

def financial_action(db,user,row,action,v):
    q=s._quote(db,row,True)
    if action=='receive':
        s._task(db,user,row,'receive');s._proof(db,user,row,v['evidence_id'],True);s.source_finance(db,user,row)
        if v['amount_cents']>s.summary(db,row)['customer_due_cents']:raise HTTPException(409,'超过本单尚欠保费或余额正在抵用')
        cash=_cash(db,user,row,v,'in','premium');link=PaymentLink(case_id=row.id,cash_id=cash.id,direction='in',amount_cents=cash.amount_cents,account_id=v['account_id'],reference=v['reference'],business_date=cash.business_date);db.add(link);db.flush();record_collection(db,user,row,link,v['evidence_id'])
    elif action in {'disburse','insurer_return'}:
        s._proof(db,user,row,v['evidence_id'],True)
        if q.collection_mode!='store_collect':raise HTTPException(409,'客户直付不能登记门店代缴现金')
        original=None
        if action=='disburse':
            s._task(db,user,row,'disburse');s.guard_source_adjustment(db,row);t=s._one(db,InsuranceTender,v['tender_id'])
            if t.case_id!=row.id or t.amount_cents<=0 or v['amount_cents']>min(s._unrefunded(db,t)-s._spent(db,t)-_reserved(db,t),s.summary(db,row)['insurer_due_cents']):raise HTTPException(409,'代缴不得超过本客户原款未支付额度及应付保险保费')
        else:
            original=s._one(db,InsurancePassEntry,v['original_id']);t=s._one(db,InsuranceTender,original.tender_id)
            returned=sum(x.amount_cents for x in s._rows(db,InsurancePassEntry,original_id=original.id))
            if original.case_id!=row.id or original.purpose!='disburse' or v['amount_cents']>original.amount_cents-returned:raise HTTPException(409,'保险公司退款超过本单该笔实际代缴未退额')
        cash=_cash(db,user,row,v,'out' if action=='disburse' else 'in',action,account_for_tender(db,t),original_cash_id=original.cash_id if original else None)
        db.add(InsurancePassEntry(case_id=row.id,tender_id=t.id,purpose=action,original_id=original.id if original else None,amount_cents=cash.amount_cents,cash_id=cash.id,account_id=v['account_id'],reference=v['reference'],business_date=cash.business_date,evidence_id=v['evidence_id'],actor_id=user.id))
    elif action in {'direct_paid','direct_return'}:
        s._proof(db,user,row,v['evidence_id'],True)
        if q.collection_mode!='customer_direct':raise HTTPException(409,'本单是门店代收模式，不登记客户直付保险公司')
        old=None
        if action=='direct_paid':
            s.guard_source_adjustment(db,row);s._task(db,user,row,'direct_paid')
            if v.get('original_id') or v['amount_cents']>s.summary(db,row)['direct_due_cents']:raise HTTPException(409,'客户直付不得超过当前约定保费')
        else:
            old=s._one(db,InsuranceDirectEntry,v.get('original_id',0));used=sum(x.amount_cents for x in s._rows(db,InsuranceDirectEntry,original_id=old.id))
            if old.case_id!=row.id or old.purpose!='paid' or not s._applied(db,row) or v['amount_cents']>min(old.amount_cents-used,s.summary(db,row)['direct_return_due_cents']):raise HTTPException(409,'直退客户须有已生效撤保及本单原直付证明，不能超退')
        db.add(InsuranceDirectEntry(case_id=row.id,purpose='paid' if action=='direct_paid' else 'returned',original_id=old.id if old else None,amount_cents=v['amount_cents'],external_reference=v['external_reference'],business_date=s._date(v['business_date']),evidence_id=v['evidence_id'],actor_id=user.id))
    elif action=='termination':
        s._proof(db,user,row,v['evidence_id'])
        if s._active_plan(db,row) or s._reservation(db,row):raise HTTPException(409,'请先处理当前撤保方案或预收占额')
        if len({x['tender_id'] for x in v['returns']})!=len(v['returns']):raise HTTPException(422,'相同原款请合并为一项退款分配')
        if s._policy(db,row) and v['external_result']!='terminated':raise HTTPException(409,'实际已出保，须取得保险公司真实退保结果和保留保费')
        if not s._policy(db,row) and v['external_result']!='not_issued':raise HTTPException(409,'尚未实际出保，请提交保险公司未出保或失败结果')
        submissions=s._rows(db,InsuranceSubmission,quote_id=q.id)
        if submissions and not s._first(db,InsuranceResult,submission_id=submissions[-1].id):raise HTTPException(409,'已提交保险公司尚无结果，不能把在途投保当作未出保取消')
        p=InsuranceTermination(case_id=row.id,quote_id=q.id,revision=len(s._rows(db,InsuranceTermination,case_id=row.id))+1,retained_cents=v['retained_cents'],returns=v['returns'],external_result=v['external_result'],reason=v['reason'],digest=s.flow.request_digest('insurance_termination',{'quote_id':q.id,**v}),evidence_id=v['evidence_id'],actor_id=user.id)
        _plan_check(db,row,p);db.add(p)
    elif action in {'termination_review','termination_consent','termination_apply','termination_cancel'}:
        p=s._plan(db,row,v['plan_id'])
        if s._first(db,InsuranceTerminationApplication,plan_id=p.id):raise HTTPException(409,'撤保方案已生效，不能覆盖或取消')
        if action=='termination_cancel':
            db.add(InsuranceTerminationCancellation(plan_id=p.id,reason=v['reason'],actor_id=user.id));return
        s._proof(db,user,row,v['evidence_id'],action=='termination_apply');s._task(db,user,row,action)
        if action=='termination_review':
            if p.actor_id==user.id or s._first(db,InsuranceTerminationReview,plan_id=p.id):raise HTTPException(409,'须由另一主管独立复核本次撤保方案')
            _plan_check(db,row,p);db.add(InsuranceTerminationReview(plan_id=p.id,decision=v['decision'],reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
        else:
            review=s._first(db,InsuranceTerminationReview,plan_id=p.id)
            if not review or review.decision!='approved':raise HTTPException(409,'请先独立批准本次撤保方案')
            if action=='termination_consent':
                if v['digest']!=p.digest:raise HTTPException(409,'客户撤保同意不是当前方案摘要')
                db.add(InsuranceTerminationConsent(plan_id=p.id,digest=p.digest,evidence_id=v['evidence_id'],actor_id=user.id))
            else:
                if not s._first(db,InsuranceTerminationConsent,plan_id=p.id):raise HTTPException(409,'须取得客户对本版撤保方案的实际同意')
                _plan_check(db,row,p);db.add(InsuranceTerminationApplication(plan_id=p.id,business_date=today(),evidence_id=v['evidence_id'],actor_id=user.id))
    elif action=='refund':
        p=s._plan(db,row,v['plan_id']);t=s._one(db,InsuranceTender,v['tender_id']);s._task(db,user,row,'refund');s._proof(db,user,row,v['evidence_id'],True)
        if not s._first(db,InsuranceTerminationApplication,plan_id=p.id) or t.case_id!=row.id or t.amount_cents<=0 or not 0<v['amount_cents']<=refund_limit(db,row,p,t):raise HTTPException(409,'可退额度不足：须按原代缴追回、已批准方案和原客户款办理')
        if t.payment_link_id:
            original=s._one(db,PaymentLink,t.payment_link_id);cash=_cash(db,user,row,v,'out','premium_refund',original.account_id,original_cash_id=original.cash_id)
            link=PaymentLink(case_id=row.id,cash_id=cash.id,original_id=original.id,direction='out',amount_cents=cash.amount_cents,account_id=original.account_id,reference=v['reference'],business_date=cash.business_date);db.add(link);db.flush();reverse=_tender(db,user,row,-v['amount_cents'],v['evidence_id'],payment=link,original=t)
        else:
            if v.get('account_id') or v.get('reference'):raise HTTPException(422,'预收抵用只退原预收余额，不填写新的现金流水')
            from .business_finance_models import FinanceCreditLink
            from .business_finance_sources import restore_insurance_credit
            credit=restore_insurance_credit(db,user,row,s._one(db,FinanceCreditLink,t.credit_link_id),v['amount_cents'],v['evidence_id'],p.id)
            reverse=_tender(db,user,row,-v['amount_cents'],v['evidence_id'],credit=credit,original=t)
        db.add(InsuranceCustomerRefund(plan_id=p.id,original_tender_id=t.id,reversal_tender_id=reverse.id,amount_cents=v['amount_cents'],evidence_id=v['evidence_id'],actor_id=user.id))
    elif action=='commission':
        s._proof(db,user,row,v['evidence_id'],True)
        if not s._policy(db,row) and not s._applied(db,row):raise HTTPException(409,'须有实际出保或终止依据才能确认佣金')
        if s._commission_pending(db,row):raise HTTPException(409,'先处理待复核的实际佣金版本')
        current=s._commission(db,row);db.add(InsuranceCommission(case_id=row.id,revision=len(s._rows(db,InsuranceCommission,case_id=row.id))+1,target_cents=v['target_cents'],previous_cents=current.target_cents if current else 0,reason=v['reason'],evidence_id=v['evidence_id'],actor_id=user.id))
    elif action=='commission_review':
        c=s._one(db,InsuranceCommission,v['confirmation_id']);s._task(db,user,row,'commission_review');s._proof(db,user,row,v['evidence_id'],True)
        current=s._commission(db,row)
        if c.case_id!=row.id or c.actor_id==user.id or s._first(db,InsuranceCommissionReview,confirmation_id=c.id) or c.previous_cents!=(current.target_cents if current else 0):raise HTTPException(409,'实际佣金须由另一主管核对当前累计金额，不能审批本人申请')
        db.add(InsuranceCommissionReview(confirmation_id=c.id,decision=v['decision'],reason=v['reason'],business_date=s._date(v['business_date']),evidence_id=v['evidence_id'],actor_id=user.id))
    elif action in {'commission_receive','commission_return'}:
        s._task(db,user,row,action);s._proof(db,user,row,v['evidence_id'],True);c=s._commission(db,row)
        if not c or c.id!=v['confirmation_id'] or s._commission_pending(db,row):raise HTTPException(409,'须按当前已独立确认的佣金版本结算')
        state=s.summary(db,row);original=None
        if action=='commission_receive':
            if v.get('original_id') or v['amount_cents']>state['commission_due_cents']:raise HTTPException(409,'实际佣金收款不能超过已确认未收金额')
        else:
            original=s._one(db,InsuranceCommissionPayment,v.get('original_id',0));used=sum(x.amount_cents for x in s._rows(db,InsuranceCommissionPayment,original_id=original.id))
            if original.case_id!=row.id or original.direction!='in' or v['amount_cents']>min(state['commission_return_due_cents'],original.amount_cents-used):raise HTTPException(409,'佣金退回不得超过本单超收及原佣金未退金额')
        cash=_cash(db,user,row,v,'in' if action=='commission_receive' else 'out',action,original.account_id if original else None,original_cash_id=original.cash_id if original else None)
        db.add(InsuranceCommissionPayment(case_id=row.id,confirmation_id=c.id,original_id=original.id if original else None,amount_cents=v['amount_cents'],direction=cash.direction,cash_id=cash.id,account_id=v['account_id'],reference=v['reference'],business_date=cash.business_date,evidence_id=v['evidence_id'],actor_id=user.id))
