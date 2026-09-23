"""Registered retail/group transaction primitives and native accounting hooks.

Every public command checks the current store and persists one receipt. Hooks
are no-commit fragments for the native retail command; they never infer a
delivery, cash receipt or physical return. Existing wallet unit ledgers keep
their original semantics, including whole-unit coupon/package reversals.
"""
from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy import select, func
from .db import today, utcnow
from .tenancy import single_store
from .flow_models import Case, PaymentLink, FlowEvent, Task,StockMove
from .retail_models import RetailLine, RetailDispatch, RetailReturnPosting
from .group_models import GroupMember, GroupReservation, GroupEntry, GroupPaymentLink
from .group_benefits_models import BenefitRule, BenefitWallet, BenefitEntry, BenefitReservation, BenefitPaymentLink
from . import group_service as group, group_benefits_service as benefits, retail_service as retail
from .retail_group_math import Value, integer, allocate_unit, allocate_return, summarize_pending
from .retail_group_models import (RetailGroupEligibility as Eligibility, RetailGroupDecision as Decision, RetailGroupScope as Scope, RetailGroupWallet as WalletBinding,
    RetailGroupPlan as Plan, RetailGroupTender as Tender, RetailGroupUnit as Unit, RetailGroupAllocation as Allocation,
    RetailGroupReservation as Reservation, RetailGroupCapture as Capture, RetailGroupClosure as Closure,
    RetailGroupReturn as Return, RetailGroupReturnPart as Part, RetailGroupRestore as Restore,
    RetailGroupSettlement as Settlement, RetailGroupCashAllocation as CashAllocation)

READ={'admin','manager','finance','auditor','sales','service'}
FRONT={'admin','sales','service'}
FINANCE={'admin','finance'}
MODES={'partial_return_mode':'accumulate_original_unit','expiry_mode':'original_expiry','pending_claim_expiry':'none'}


@contextmanager
def authority(db,user,roles=READ):
    with group.authority(db,user,roles) as sid:
        previous=db.info.get('_retail_group_authority')
        db.info['_retail_group_authority']=(user.id,sid)
        try:yield sid
        finally:
            if previous is None:db.info.pop('_retail_group_authority',None)
            else:db.info['_retail_group_authority']=previous


def rows(db,model,**kw):return list(db.scalars(select(model).filter_by(**kw).order_by(model.id)))
def one(db,model,key):
    result=db.scalar(select(model).where(model.id==key))
    if result is None:raise HTTPException(404,'本店原支付或原退记录不存在')
    return result
def val(row):return Value(row.credit_cents,row.consideration_cents,row.settlement_cents)
def total(values):
    values=list(values)
    return Value(*(sum(getattr(v,k) for v in values) for k in ('face','consideration','settlement')))
def require_plan(db,row):
    plan=db.scalar(select(Plan).where(Plan.case_id==row.id))
    if not plan:raise HTTPException(409,'本单尚未明确授权集团混合付款方案')
    return plan
def exists(db,row):return db.scalar(select(Plan.id).where(Plan.case_id==row.id)) is not None
def allocations(db,plan):
    return list(db.scalars(select(Allocation).join(Unit,Unit.id==Allocation.unit_id).join(Tender,Tender.id==Unit.tender_id)
        .where(Tender.plan_id==plan.id).order_by(Allocation.id)))
def capture_for(db,tender):return db.scalar(select(Capture).where(Capture.tender_id==tender.id))
def is_closed(db,tender):return db.scalar(select(Closure.id).where(Closure.tender_id==tender.id)) is not None
def returned(db,allocation):return total(val(p) for p in rows(db,Part,allocation_id=allocation.id))
def restored(db,unit):return total(val(r) for r in rows(db,Restore,unit_id=unit.id))


def _evidence(db,user,row,key,category=None):
    # FileAsset preserves the uploader; each command/ledger separately records
    # its actual actor. Reusing an authorized original never attests that this
    # actor uploaded it, nor does upload alone approve a business action.
    return retail._evidence(db,user,row,key,category)


def _member(db,user,row,member_id,version):
    member=group._member(db,member_id,single_store(db),version)
    group._case(db,user,member,row.id,row.version,row.store_id)
    return member


def _eligible(db,wallet,row):
    rule=benefits._rule(db,wallet.rule_id)
    eligibility=db.scalar(select(Eligibility).join(Decision,Decision.eligibility_id==Eligibility.id)
        .where(Eligibility.rule_id==rule.id,Decision.approved.is_(True)))
    binding=db.scalar(select(WalletBinding).where(WalletBinding.wallet_id==wallet.id))
    if not eligibility or not binding or binding.eligibility_id!=eligibility.id:raise HTTPException(409,'该原权益批次没有发行时冻结的商品适用与部分退回规则；旧维修规则不能推断为精品适用')
    decision=db.scalar(select(Decision).where(Decision.eligibility_id==eligibility.id))
    origin=db.scalar(select(BenefitEntry).where(BenefitEntry.wallet_id==wallet.id,BenefitEntry.purpose.in_(['purchase','grant','exchange_in'])))
    if not origin or origin.id!=binding.origin_id or decision.id!=binding.decision_id or origin.occurred_at<decision.occurred_at:
        raise HTTPException(409,'原权益先于商品规则批准发行，不能补授商品使用范围')
    benefits._usable(wallet,rule,row.store_id)
    if rule.kind not in {'bonus','coupon','package'}:raise HTTPException(409,'本版精品不直接使用积分抵款；须按已批准规则另行兑换明确权益')
    scopes=rows(db,Scope,eligibility_id=eligibility.id,store_id=row.store_id)
    return rule,eligibility,scopes


def scope_matches(scope,line,component):
    # Match two immutable originals, never reinterpret an earlier wallet with
    # a current renamed item/unit or current work-code configuration.
    return scope.item_id==line.item_id and scope.unit==line.unit and scope.component==component and (
        component=='goods' or (scope.work_item_id==line.work_item_id and scope.work_code==line.work_code))


def prepare_plan(db,user,row,member_id,member_version,evidence_id,selections):
    """No commit. Customer authorizes original funding allocation, not payment."""
    if not db.info.get('_retail_group_authority'):raise HTTPException(403,'须由精品集团支付服务办理')
    if exists(db,row):raise HTTPException(409,'本单已有冻结付款方案，不能重分原支付批次')
    if not row.data.get('accepted_date') or not db.scalar(select(FlowEvent.id).where(FlowEvent.case_id==row.id,FlowEvent.action=='retail_accept')) or retail._active(db,row):
        raise HTTPException(409,'本版集团混合付款须在客户实际接收精品、且无待处理退货后授权')
    from .business_finance_sources import case_credit_amount,case_reserved_amount
    if db.scalar(select(PaymentLink.id).where(PaymentLink.case_id==row.id)) or case_credit_amount(db,row.id) or case_reserved_amount(db,row.id) or group.case_paid_amount(db,row.id) or benefits.case_paid_amount(db,row.id):
        raise HTTPException(409,'原单已有实际收款、预收抵用或其它支付，不能按新计划重分原支付；请保留原结算流程')
    if rows(db,RetailReturnPosting,case_id=row.id):raise HTTPException(409,'原单已有实际退货，本版不重分历史付款方案')
    if not selections or len(selections)>20:raise HTTPException(422,'请明确选择 1 至 20 个原本金或权益批次')
    member=_member(db,user,row,member_id,member_version);_evidence(db,user,row,evidence_id,'authorization')
    lines=rows(db,RetailLine,case_id=row.id)
    components=[(line,kind,getattr(line,'goods_cents' if kind=='goods' else 'installation_cents')) for line in lines for kind in ('goods','installation') if getattr(line,'goods_cents' if kind=='goods' else 'installation_cents')]
    remaining=[c[2] for c in components]
    plan=Plan(case_id=row.id,member_id=member.id,evidence_id=evidence_id,actor_id=user.id,digest=group._digest('retail_group_plan',{'selections':selections,'evidence_id':evidence_id,'case_id':row.id}))
    db.add(plan);db.flush();seen=set();count=0
    for sequence,selection in enumerate(selections,1):
        kind=selection.get('kind')
        if kind=='principal':
            if ('principal',0) in seen:raise HTTPException(422,'集团本金请合并为一笔明确额度')
            seen.add(('principal',0));amount=integer(selection.get('amount_cents'),'本金',1)
            if amount>member.balance_cents-member.reserved_cents:raise HTTPException(409,'集团本金可用额度不足；授权不会占额')
            value=Value(amount,amount,amount);unit_values=[value];units=amount;wallet=None;eligibility=None;allowed=list(range(len(components)))
        elif kind in {'bonus','coupon','package'}:
            wid=integer(selection.get('wallet_id'),'权益批次',1)
            if ('wallet',wid) in seen:raise HTTPException(422,'同一权益批次请合并为一项')
            seen.add(('wallet',wid));wallet=benefits._wallet(db,member,wid);group._version(wallet,selection.get('wallet_version'))
            rule,eligibility,scopes=_eligible(db,wallet,row)
            if rule.kind!=kind:raise HTTPException(422,'权益种类须与原批次一致')
            units=integer(selection.get('units'),'原权益整数份数',1,1_000_000_000 if kind=='bonus' else 100)
            if units>wallet.balance_units-wallet.reserved_units:raise HTTPException(409,'原权益可用份数不足；授权不会占额')
            from .member_pricing_service import benefit_exclusions
            blocked=benefit_exclusions(db,row,kind)
            allowed=[i for i,(line,component,_) in enumerate(components) if ('item'+str(line.item_id),component) not in blocked and any(scope_matches(s,line,component) for s in scopes)]
            unit_value=Value(rule.credit_cents_per_unit,rule.sale_cents_per_unit if wallet.source_kind=='purchase' else 0,rule.settlement_cents_per_unit)
            value=Value(unit_value.face*units,unit_value.consideration*units,unit_value.settlement*units)
            unit_values=[value] if kind=='bonus' else [unit_value]*units
        else:raise HTTPException(422,'请选择本金、赠金、券或套餐；现金余额由原行剩余额度生成')
        if value.face>sum(remaining[i] for i in allowed):raise HTTPException(409,'本次抵扣超过原规则明确适用商品、单位或安装项目的未分配金额')
        tender=Tender(plan_id=plan.id,sequence=sequence,kind=kind,wallet_id=wallet.id if wallet else None,eligibility_id=eligibility.id if eligibility else None,
            units=units,expires_on=wallet.expires_on if wallet else None,**value.fields());db.add(tender);db.flush()
        for n,unit_value in enumerate(unit_values,1):
            unit=Unit(tender_id=tender.id,sequence=n,**unit_value.fields());db.add(unit);db.flush()
            shares=allocate_unit(unit_value,[remaining[i] for i in allowed])
            for i,share in zip(allowed,shares):
                if not share.face:continue
                line,component,_=components[i];db.add(Allocation(unit_id=unit.id,line_id=line.id,component=component,**share.fields()));remaining[i]-=share.face;count+=1
    if sum(remaining):
        value=Value(sum(remaining),sum(remaining),sum(remaining))
        tender=Tender(plan_id=plan.id,sequence=len(selections)+1,kind='cash',units=value.face,**value.fields());db.add(tender);db.flush()
        unit=Unit(tender_id=tender.id,sequence=1,**value.fields());db.add(unit);db.flush()
        for (line,component,_),amount in zip(components,remaining):
            if amount:db.add(Allocation(unit_id=unit.id,line_id=line.id,component=component,**Value(amount,amount,amount).fields()));count+=1
    if count>1000:raise HTTPException(413,'付款分摊超过 1000 项，请减少同次使用的券或套餐份数')
    row.updated_at=utcnow();db.flush()
    retail.flow.ensure_task(db,row,'retail_group_payment','按已授权原批次核对占额、核销或释放','finance')
    return plan


def _reservation(db,tender):
    links=rows(db,Reservation,tender_id=tender.id)
    if len(links)>1:raise HTTPException(409,'原支付批次重复占额，请核对原账')
    if not links:return None,None
    link=links[0];model=GroupReservation if link.principal_id else BenefitReservation
    return link,one(db,model,link.principal_id or link.benefit_id)


def reserve(db,user,row,plan,tender,evidence_id):
    if tender.kind=='cash' or capture_for(db,tender) or is_closed(db,tender) or _reservation(db,tender)[0]:raise HTTPException(409,'该原批次已占额、核销或改为现金待结')
    _evidence(db,user,row,evidence_id)
    if any(returned(db,a).face for u in rows(db,Unit,tender_id=tender.id) for a in rows(db,Allocation,unit_id=u.id)):
        raise HTTPException(409,'原分配商品已经实际退回，请释放未核销方案并核对剩余现金待结')
    member=_member(db,user,row,plan.member_id,None)
    if tender.kind=='principal':
        if tender.credit_cents>member.balance_cents-member.reserved_cents:raise HTTPException(409,'本金已被其他消费或退款占用')
        member.reserved_cents+=tender.credit_cents
        record=GroupReservation(member_id=member.id,case_id=row.id,amount_cents=tender.credit_cents,evidence_id=evidence_id,actor_id=user.id)
    else:
        wallet=benefits._wallet(db,member,tender.wallet_id);_eligible(db,wallet,row)
        if tender.units>wallet.balance_units-wallet.reserved_units:raise HTTPException(409,'原权益已被其他消费或退款占用')
        wallet.reserved_units+=tender.units;wallet.updated_at=utcnow()
        record=BenefitReservation(wallet_id=wallet.id,case_id=row.id,units=tender.units,credit_cents=tender.credit_cents,evidence_id=evidence_id,actor_id=user.id)
    member.updated_at=utcnow();db.add(record);db.flush()
    link=Reservation(tender_id=tender.id,principal_id=record.id if tender.kind=='principal' else None,benefit_id=record.id if tender.kind!='principal' else None)
    db.add(link);db.flush();return link


def capture(db,user,row,plan,tender,evidence_id,reservation_version):
    link,record=_reservation(db,tender)
    if not record or record.status!='reserved' or capture_for(db,tender) or is_closed(db,tender):raise HTTPException(409,'原占额已结束或尚未办理')
    group._version(record,reservation_version);_evidence(db,user,row,evidence_id)
    if any(returned(db,a).face for u in rows(db,Unit,tender_id=tender.id) for a in rows(db,Allocation,unit_id=u.id)):
        raise HTTPException(409,'原分配商品已有实退，请释放尚未核销占额；实际退货不受占额阻挡')
    member=_member(db,user,row,plan.member_id,None)
    if tender.kind=='principal':
        member.reserved_cents-=tender.credit_cents;member.balance_cents-=tender.credit_cents
        entry=group._entry(db,user,member,row,'capture',-tender.credit_cents,evidence_id)
        db.add(GroupPaymentLink(case_id=row.id,entry_id=entry.id,reservation_id=record.id,amount_cents=tender.credit_cents))
    else:
        wallet=benefits._wallet(db,member,tender.wallet_id);rule,_,_=_eligible(db,wallet,row)
        wallet.reserved_units-=tender.units;wallet.balance_units-=tender.units;wallet.updated_at=utcnow()
        entry=benefits._entry(db,user,wallet,row,'capture',-tender.units,evidence_id,'按已授权精品原批次实际核销',credit=tender.credit_cents,clearing=-tender.settlement_cents)
        db.add(BenefitPaymentLink(case_id=row.id,entry_id=entry.id,reservation_id=record.id,amount_cents=tender.credit_cents))
    member.updated_at=utcnow();record.status='captured'
    result=Capture(tender_id=tender.id,reservation_id=link.id,principal_id=entry.id if tender.kind=='principal' else None,benefit_id=entry.id if tender.kind!='principal' else None)
    db.add(result);db.flush();return result


def release(db,user,row,plan,tender,evidence_id,reason):
    if tender.kind=='cash' or capture_for(db,tender) or is_closed(db,tender):raise HTTPException(409,'已实际核销须按原实退恢复，不能取消已发生支付')
    _evidence(db,user,row,evidence_id);link,record=_reservation(db,tender)
    if record:
        if record.status!='reserved':raise HTTPException(409,'占额已结束')
        member=_member(db,user,row,plan.member_id,None)
        if tender.kind=='principal':member.reserved_cents-=tender.credit_cents
        else:
            wallet=benefits._wallet(db,member,tender.wallet_id);wallet.reserved_units-=tender.units;wallet.updated_at=utcnow()
        member.updated_at=utcnow();record.status='released'
    db.add(Closure(tender_id=tender.id,evidence_id=evidence_id,actor_id=user.id,reason=reason));db.flush()


def _settlement(db,amount,part_id=None,restore_id=None):
    if amount:db.add_all([Settlement(return_part_id=part_id,restore_id=restore_id,side='center',amount_cents=amount),
        Settlement(return_part_id=part_id,restore_id=restore_id,side='store',amount_cents=-amount)])


def record_actual_return(db,user,row,posting):
    """No commit. Called only AFTER native accepted RetailReturnPosting flush."""
    if not exists(db,row):return
    with authority(db,user,retail.READ_ROLES):
        plan=require_plan(db,row)
        source=db.scalar(select(RetailReturnPosting).where(RetailReturnPosting.id==posting.id,RetailReturnPosting.case_id==row.id))
        if source is None or posting is not source:raise HTTPException(409,'须先保存本单实际验收退货事实')
        prior=db.scalar(select(Return).where(Return.posting_id==source.id))
        if prior:return prior
        dispatch=one(db,RetailDispatch,source.dispatch_id)
        if dispatch.case_id!=row.id:raise HTTPException(409,'原出库行与精品单不符')
        record=Return(plan_id=plan.id,posting_id=source.id);db.add(record);db.flush();liability=False
        for component,amount in [('goods',source.goods_cents),('installation',source.installation_cents-source.retained_cents)]:
            if not amount:continue
            cells=[a for a in allocations(db,plan) if a.line_id==dispatch.line_id and a.component==component]
            left=[val(a).subtract(returned(db,a)) for a in cells]
            parts=allocate_return(amount,left)
            for allocation,value in zip(cells,parts):
                if not value.face:continue
                tender=one(db,Tender,one(db,Unit,allocation.unit_id).tender_id);captured=capture_for(db,tender)
                part=Part(return_id=record.id,allocation_id=allocation.id,capture_id=captured.id if captured else None,**value.fields())
                db.add(part);db.flush()
                if captured:
                    _settlement(db,value.settlement,part_id=part.id);liability=True
        plan.updated_at=utcnow();db.flush()
        if liability:retail.flow.ensure_task(db,row,'retail_group_restore','按原批次恢复本金、赠金或完整权益；零头单列待恢复','finance',reopen=True)
        return record


def restore_original(db,user,row,plan,unit,evidence_id):
    """Finance restores available original units; no cash is created here."""
    tender=one(db,Tender,unit.tender_id);captured=capture_for(db,tender)
    if not captured:raise HTTPException(409,'原批次未实际核销，没有可恢复的余额')
    values=total(val(p) for a in rows(db,Allocation,unit_id=unit.id) for p in rows(db,Part,allocation_id=a.id) if p.capture_id==captured.id)
    already=restored(db,unit);pending=values.subtract(already)
    info=summarize_pending(tender.kind,val(unit),values,already)
    if not info['restorable']:raise HTTPException(409,'原券或套餐退回额度尚未凑整，或已恢复；待恢复额度不可消费、不能在履约店退成现金')
    _evidence(db,user,row,evidence_id);member=_member(db,user,row,plan.member_id,None)
    link,reservation=_reservation(db,tender)
    if tender.kind=='principal':
        original=one(db,GroupEntry,captured.principal_id);member.balance_cents+=pending.face
        entry=group._entry(db,user,member,row,'reverse',pending.face,evidence_id,original)
        db.add(GroupPaymentLink(case_id=row.id,entry_id=entry.id,reservation_id=reservation.id,amount_cents=-pending.face))
    else:
        wallet=benefits._wallet(db,member,tender.wallet_id);rule=benefits._rule(db,wallet.rule_id)
        units=pending.face if tender.kind=='bonus' else 1
        if pending.face!=units*rule.credit_cents_per_unit:raise HTTPException(409,'原恢复额度与冻结整数单位不符')
        wallet.balance_units+=units;wallet.updated_at=utcnow();original=one(db,BenefitEntry,captured.benefit_id)
        entry=benefits._entry(db,user,wallet,row,'reverse',units,evidence_id,'精品原实退恢复；保留原有效期',credit=-pending.face,original=original,clearing=pending.settlement)
        db.add(BenefitPaymentLink(case_id=row.id,entry_id=entry.id,reservation_id=reservation.id,amount_cents=-pending.face))
    member.updated_at=utcnow()
    result=Restore(unit_id=unit.id,capture_id=captured.id,principal_id=entry.id if tender.kind=='principal' else None,benefit_id=entry.id if tender.kind!='principal' else None,
        evidence_id=evidence_id,actor_id=user.id,**pending.fields());db.add(result);db.flush()
    # Native reverse already restores S. Offset the pending-clearing side at
    # this transition: the actual return reduced S exactly once, at receipt.
    _settlement(db,-pending.settlement,restore_id=result.id)
    return result


def _cash_cells(db,plan):
    result=[]
    for allocation in allocations(db,plan):
        tender=one(db,Tender,one(db,Unit,allocation.unit_id).tender_id)
        if tender.kind=='cash' or is_closed(db,tender):result.append(allocation)
    return result


def cash_capacity(db,row):
    plan=require_plan(db,row);capacity=0
    for a in _cash_cells(db,plan):
        paid=sum(x.amount_cents for x in rows(db,CashAllocation,allocation_id=a.id))
        capacity+=max(0,a.credit_cents-returned(db,a).face-paid)
    return capacity


def guard_cash_receive(db,user,row,amount):
    """No commit: native retail payment calls this before creating cash."""
    if not exists(db,row):return
    with authority(db,user,FINANCE):
        if integer(amount,'实际收款',1)>cash_capacity(db,row):raise HTTPException(409,'实际收款超过冻结原行的现金待结额度；未核销集团占额须明确释放，不能重复收款')


def guard_external_settlement(db,row,action):
    """Other domains call before credit, collection or cash correction mutation."""
    if exists(db,row):raise HTTPException(409,'本精品单已有原行集团混合付款方案；不能另加预收抵用、代收或通用收款更正。请从精品原单按原现金份额及原权益分别办理')


def guard_legacy_wallet_action(db,row):
    """Called by group._case; old release must not orphan the retail plan."""
    if row.kind=='retail' and exists(db,row) and not db.info.get('_retail_group_authority'):
        raise HTTPException(409,'本精品单已有原行集团混合付款方案；占额、核销、释放和原退须从精品集团付款页办理，不能使用旧维修权益入口')


def attach_cash(db,user,row,payment):
    """No commit: bind a NEW original native PaymentLink to remaining cash cells."""
    if not exists(db,row):return
    with authority(db,user,FINANCE):
        source=db.scalar(select(PaymentLink).where(PaymentLink.id==payment.id,PaymentLink.case_id==row.id))
        if source is not payment or source.direction!='in':raise HTTPException(409,'须关联本单实际原收款记录')
        prior=rows(db,CashAllocation,payment_link_id=source.id)
        if prior:
            if sum(x.amount_cents for x in prior)!=source.amount_cents:raise HTTPException(409,'原现金分摊缺失')
            return
        plan=require_plan(db,row);left=source.amount_cents
        for a in _cash_cells(db,plan):
            paid=sum(x.amount_cents for x in rows(db,CashAllocation,allocation_id=a.id))
            amount=min(left,max(0,a.credit_cents-returned(db,a).face-paid))
            if amount:db.add(CashAllocation(allocation_id=a.id,payment_link_id=source.id,amount_cents=amount));left-=amount
            if not left:break
        if left:raise HTTPException(409,'本次实际收款没有足够的冻结现金份额，整笔收款须回滚')
        plan.updated_at=utcnow();db.flush()


def cash_refundable(db,row,payment_id=None):
    plan=require_plan(db,row);result=[]
    for a in _cash_cells(db,plan):
        all_rows=rows(db,CashAllocation,allocation_id=a.id)
        surplus=max(0,sum(x.amount_cents for x in all_rows)-(a.credit_cents-returned(db,a).face))
        for source in sorted((x for x in all_rows if x.amount_cents>0),key=lambda x:x.id,reverse=True):
            remaining=source.amount_cents+sum(x.amount_cents for x in all_rows if x.original_id==source.id)
            amount=min(surplus,remaining);surplus-=amount
            if amount and (payment_id is None or source.payment_link_id==payment_id):result.append((source,amount))
    return result


def guard_cash_refund(db,user,row,original_payment_id,amount):
    if not exists(db,row):return
    with authority(db,user,FINANCE):
        cap=sum(amount for _,amount in cash_refundable(db,row,original_payment_id))
        if integer(amount,'实际原款退款',1)>cap:raise HTTPException(409,'退款超过该原收款在实际退货行中的剩余现金份额；本金、赠金和券套餐不能混退为现金')


def attach_cash_refund(db,user,row,payment,original_payment_id):
    if not exists(db,row):return
    with authority(db,user,FINANCE):
        source=db.scalar(select(PaymentLink).where(PaymentLink.id==payment.id,PaymentLink.case_id==row.id,PaymentLink.direction=='out'))
        if source is not payment or source.original_id!=original_payment_id:raise HTTPException(409,'须关联本单实际原路退款记录')
        if rows(db,CashAllocation,payment_link_id=source.id):return
        left=source.amount_cents
        for original,cap in cash_refundable(db,row,original_payment_id):
            amount=min(left,cap)
            if amount:db.add(CashAllocation(allocation_id=original.allocation_id,payment_link_id=source.id,amount_cents=-amount,original_id=original.id));left-=amount
            if not left:break
        if left:raise HTTPException(409,'原现金退款分摊不足，整笔退款须回滚')
        require_plan(db,row).updated_at=utcnow();db.flush()


def totals_adjustment(db,row):
    """Same scoped rows feed retail totals, detail, reports and source exports."""
    if not exists(db,row):return None
    plan=require_plan(db,row);paid=discount=settlement=0;pending={k:0 for k in ('principal','bonus','coupon','package')}
    for tender in rows(db,Tender,plan_id=plan.id):
        captured=capture_for(db,tender)
        if not captured:continue
        parts=total(val(p) for unit in rows(db,Unit,tender_id=tender.id) for a in rows(db,Allocation,unit_id=unit.id) for p in rows(db,Part,allocation_id=a.id) if p.capture_id==captured.id)
        remaining=val(tender).subtract(parts)
        paid+=remaining.face;discount+=remaining.face-remaining.consideration;settlement+=remaining.settlement
        pending[tender.kind]+=parts.face-sum(r.credit_cents for u in rows(db,Unit,tender_id=tender.id) for r in rows(db,Restore,unit_id=u.id))
    return {'group_paid_cents':paid,'group_external_discount_cents':discount,'group_internal_settlement_cents':settlement,
        'group_recognized_cents':paid-discount,'group_discount_borne_cents':settlement-(paid-discount),'service_discount_borne_cents':paid-settlement,
        'group_return_pending_cents':pending,'cash_collectable_cents':cash_capacity(db,row),'cash_refund_due_cents':sum(v for _,v in cash_refundable(db,row))}


def analytics_adjustments(db,row):
    """Add to standard wallet C/P/S facts; restored original units offset here."""
    if not exists(db,row):return []
    plan=require_plan(db,row);result=[]
    for tender in rows(db,Tender,plan_id=plan.id):
        if not capture_for(db,tender):continue
        for unit in rows(db,Unit,tender_id=tender.id):
            for a in rows(db,Allocation,unit_id=unit.id):
                for p in rows(db,Part,allocation_id=a.id):
                    if p.capture_id:
                        original_return=one(db,Return,p.return_id);posting=one(db,RetailReturnPosting,original_return.posting_id);move=one(db,StockMove,posting.stock_move_id)
                        result.append({'source':'retail_group_return','id':p.id,'store_id':row.store_id,'case_id':row.id,'unit_id':unit.id,'business_date':str(move.business_date),'occurred_at':original_return.occurred_at.isoformat(),'stock_move_id':move.id,
                            'credit_cents':-p.credit_cents,'consideration_cents':-p.consideration_cents,'settlement_cents':-p.settlement_cents})
            for r in rows(db,Restore,unit_id=unit.id):result.append({'source':'retail_group_restore_offset','id':r.id,'store_id':row.store_id,'case_id':row.id,'unit_id':unit.id,'occurred_at':r.occurred_at.isoformat(),**val(r).fields()})
    return result


def _sync(db,user,row):
    """All commands use the same native settlement, invoice and points hooks."""
    retail._sync(db,user,row)


def sync_tasks(db,user,row,amount):
    """No commit; maintain only this plan's tasks, never close other workflows."""
    if 'group_return_pending_cents' not in amount:return
    plan=require_plan(db,row)
    unresolved=[t for t in rows(db,Tender,plan_id=plan.id)
        if t.kind!='cash' and not capture_for(db,t) and not is_closed(db,t)]
    if not unresolved:retail.flow.finish_task(db,row,'retail_group_payment',user)
    pending=bool(sum(amount['group_return_pending_cents'].values()))
    # An incomplete original coupon is a recorded liability, not an employee
    # action that can be completed today. Do not create an impossible overdue
    # task; reopen it when a later actual return makes an original unit whole.
    ready=False
    for tender in rows(db,Tender,plan_id=plan.id):
        if not capture_for(db,tender):continue
        for unit in rows(db,Unit,tender_id=tender.id):
            returned_value=total(val(p) for a in rows(db,Allocation,unit_id=unit.id)
                for p in rows(db,Part,allocation_id=a.id) if p.capture_id)
            claim=summarize_pending(tender.kind,val(unit),returned_value,restored(db,unit))
            if claim['restorable']:ready=True
    if ready:
        retail.flow.ensure_task(db,row,'retail_group_restore',
            '按已具备条件的原单位恢复本金、赠金或完整权益','finance',reopen=True)
    else:retail.flow.finish_task(db,row,'retail_group_restore',user)
    if unresolved or pending:row.state='settling'
    row.completed_date=today() if row.state=='completed' else None



def _task(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if task is None or task.assignee_id!=user.id:raise HTTPException(403,'请由当前精品集团待办的财务办理；需要换人时先明确交接')
    return task


def command(db,user,case_id,request_id,version,action,values):
    roles=FRONT if action=='authorize' else FINANCE if action in {'reserve','capture','release','restore'} else {'admin','manager'}
    if action not in {'authorize','reserve','capture','release','restore','reassign'}:raise HTTPException(404,'精品集团支付动作不存在')
    def operation(sid):
        with authority(db,user,roles):
            row=retail.get_order(db,user,case_id);group._version(row,version)
            if action=='authorize':
                plan=prepare_plan(db,user,row,values['member_id'],values['member_version'],values['evidence_id'],values['selections'])
            else:
                plan=require_plan(db,row);group._version(plan,values['plan_version'])
                if action=='reassign':
                    key=values['task_key']
                    if key not in {'retail_group_payment','retail_group_restore'}:raise HTTPException(422,'只能交接本单集团支付或原权益恢复待办')
                    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
                    if not task:raise HTTPException(409,'指定原待办已经结束')
                    actor=retail.flow.assignable(db,values['assignee_id'],sid,{'finance'});task.assignee_id=actor.id;task.due_date=values['due_date']
                else:
                    _task(db,user,row,'retail_group_restore' if action=='restore' else 'retail_group_payment')
                    _member(db,user,row,plan.member_id,values['member_version'])
                    if action=='restore':
                        unit=one(db,Unit,values['unit_id']);tender=one(db,Tender,unit.tender_id)
                    else:tender=one(db,Tender,values['tender_id'])
                    if tender.plan_id!=plan.id:raise HTTPException(404,'本单没有该原支付批次')
                    if tender.wallet_id:
                        wallet=benefits._wallet(db,one(db,GroupMember,plan.member_id),tender.wallet_id);group._version(wallet,values['wallet_version'])
                    if action=='reserve':reserve(db,user,row,plan,tender,values['evidence_id'])
                    elif action=='capture':capture(db,user,row,plan,tender,values['evidence_id'],values['reservation_version'])
                    elif action=='release':release(db,user,row,plan,tender,values['evidence_id'],values['reason'])
                    else:restore_original(db,user,row,plan,unit,values['evidence_id'])
            row.updated_at=utcnow();plan.updated_at=utcnow();db.flush();_sync(db,user,row)
            detail={k:values[k] for k in ('evidence_id','tender_id','unit_id','assignee_id','task_key','reason') if k in values}
            detail['plan_id']=plan.id
            if action=='authorize':detail['digest']=plan.digest
            if values.get('due_date'):detail['due_date']=str(values['due_date'])
            retail.flow.log_event(db,user,row,'retail_group_'+action,{'authorize':'确认精品集团付款方案','reserve':'占用原本金或权益','capture':'实际核销原本金或权益','release':'释放未核销原占额','restore':'恢复原本金或完整权益','reassign':'明确交接集团支付待办'}[action],detail=detail)
            db.flush()
            from .membership_service import sync_consumption_points
            from .invoice_service import sync_source
            sync_consumption_points(db,user,row,evidence_id=values.get('evidence_id'))
            sync_source(db,user,row)
            db.flush();return describe(db,user,row)
    payload_values={k:(str(v) if k=='due_date' else v) for k,v in values.items()}
    return group._execute(db,user,request_id,'retail_group_'+action,{'case_id':case_id,'version':version,'values':payload_values},operation,roles)


def describe(db,user,row):
    with authority(db,user,READ):
        plan=require_plan(db,row);member=group._member(db,plan.member_id,row.store_id)
        financial=user.role in retail.COST_ROLES
        result={'case_id':row.id,'number':row.number,'version':row.version,'plan_id':plan.id,'plan_version':plan.version,
            'member_id':member.id,'member_version':member.version,'evidence_id':plan.evidence_id,'tenders':[],
            'tasks':[{'id':t.id,'key':t.key,'title':t.title,'assignee_id':t.assignee_id,'due_date':str(t.due_date)} for t in rows(db,Task,case_id=row.id) if t.status=='open' and t.key in {'retail_group_payment','retail_group_restore'}],
            'notice':'券和套餐待凑整额度不可消费；恢复保留原批次有效期，原发行退款须由原发行店按原款另行办理。'}
        for tender in rows(db,Tender,plan_id=plan.id):
            captured=capture_for(db,tender);link,reservation=_reservation(db,tender)
            record={'id':tender.id,'kind':tender.kind,'credit_cents':tender.credit_cents,'units':tender.units,'wallet_id':tender.wallet_id,
                'status':'captured' if captured else 'cash' if tender.kind=='cash' else 'released' if is_closed(db,tender) else 'reserved' if reservation else 'authorized','units_detail':[]}
            if financial:record.update(consideration_cents=tender.consideration_cents,settlement_cents=tender.settlement_cents)
            if reservation:record['reservation_version']=reservation.version
            if tender.wallet_id:
                wallet=benefits._wallet(db,member,tender.wallet_id);rule=benefits._rule(db,wallet.rule_id)
                record.update(wallet_version=wallet.version,rule_name=rule.name,rule_version=rule.rule_version,issuer_store_id=wallet.issuer_store_id,
                    expires_on=str(wallet.expires_on),expired=wallet.expires_on<today(),original_refund_policy=rule.refund_policy,source_kind=wallet.source_kind)
                if wallet.issuer_store_id==row.store_id:
                    original_case=db.scalar(select(Case).where(Case.id==wallet.source_case_id))
                    if original_case and retail.flow.can_read(db,user,original_case):record['original_issuance_case_id']=wallet.source_case_id
            for unit in rows(db,Unit,tender_id=tender.id):
                entries=[p for a in rows(db,Allocation,unit_id=unit.id) for p in rows(db,Part,allocation_id=a.id) if p.capture_id]
                ret=total(val(p) for p in entries);back=restored(db,unit)
                pending=summarize_pending(tender.kind,val(unit),ret,back)
                info={'id':unit.id,'sequence':unit.sequence,'credit_cents':unit.credit_cents,'returned_credit_cents':ret.face,'restored_credit_cents':back.face,'pending_credit_cents':pending['credit_cents'],
                    'restorable':pending['restorable'],'pending_original_unit':pending['pending_original_unit'],'spendable_pending_cents':0,
                    'allocations':[{'line_id':a.line_id,'component':a.component,'credit_cents':a.credit_cents,'returned_credit_cents':returned(db,a).face} for a in rows(db,Allocation,unit_id=unit.id)]}
                record['units_detail'].append(info)
            result['tenders'].append(record)
        adjustment=totals_adjustment(db,row)
        if not financial:
            for key in ('group_external_discount_cents','group_internal_settlement_cents','group_recognized_cents','group_discount_borne_cents','service_discount_borne_cents'):adjustment.pop(key,None)
        result['totals']=adjustment
        if user.role in {'admin','manager','finance','auditor'}:
            by_original={}
            for original,amount in cash_refundable(db,row):by_original[original.payment_link_id]=by_original.get(original.payment_link_id,0)+amount
            result['original_cash_refundable']=[{'payment_link_id':key,'amount_cents':value} for key,value in sorted(by_original.items())]
        return result


def catalogue(db,user,row):
    with authority(db,user,READ):
        current=group.member_for_customer(db,user,row.customer_id)
        member=current['member'];result={'case_id':row.id,'number':row.number,'version':row.version,'member':member,'wallets':[],
            'has_plan':exists(db,row),'can_authorize':user.role in FRONT,
            'limitation':'仅客户实际接收、无待处理退货、且尚无实际收款或预收抵用的精品单可新建集团混合付款方案；本版不提供集团混合预付款。'}
        if not member:return result
        wallets=list(db.scalars(select(BenefitWallet).join(BenefitRule,BenefitRule.id==BenefitWallet.rule_id)
            .where(BenefitWallet.member_id==member['id'],BenefitRule.kind.in_(['bonus','coupon','package'])).order_by(BenefitWallet.id).limit(501)))
        if len(wallets)>500:raise HTTPException(413,'原权益批次超过当前查看上限，请先按原会员账核对')
        for wallet in wallets:
            rule=benefits._rule(db,wallet.rule_id)
            if rule.kind not in {'bonus','coupon','package'}:continue
            item={'id':wallet.id,'version':wallet.version,'kind':rule.kind,'name':rule.name,'rule_version':rule.rule_version,
                'available_units':wallet.balance_units-wallet.reserved_units,'credit_cents_per_unit':rule.credit_cents_per_unit,'expires_on':str(wallet.expires_on),
                'issuer_store_id':wallet.issuer_store_id,'usable':True}
            try:
                _,e,scopes=_eligible(db,wallet,row)
                item['scopes']=[{'item_id':s.item_id,'component':s.component,'work_item_id':s.work_item_id,'name':s.name,'sku':s.sku} for s in scopes]
                if not scopes:item.update(usable=False,reason='本店没有该规则明确批准的商品用途')
            except HTTPException as error:item.update(usable=False,reason=error.detail)
            result['wallets'].append(item)
        return result
