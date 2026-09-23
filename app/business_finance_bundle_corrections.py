"""Correct original frozen recharge shares without rewriting issuance or use."""
from fastapi import HTTPException
from sqlalchemy import select
from .db import today,utcnow
from .business_finance_models import (FinanceStoredCorrectionRequest,FinanceBundleCorrection,
    FinanceBundleCorrectionComponent,FinanceBundleCorrectionPosting)
from .group_benefits_models import BenefitEntry
from .recharge_bundle_models import RechargeBundleRefund


SOURCE_TABLES=('business_finance_bundle_corrections','business_finance_bundle_correction_components','business_finance_bundle_correction_postings')


def bundle_correction_case_ids(db):
    return set(db.scalars(select(FinanceStoredCorrectionRequest.case_id).join(FinanceBundleCorrection,
        FinanceBundleCorrection.request_id==FinanceStoredCorrectionRequest.id)))


def correction_for(db,request):
    return db.scalar(select(FinanceBundleCorrection).where(FinanceBundleCorrection.request_id==request.id))


def effective_shares(db,purchase):
    delta=sum(c.corrected_shares-c.original_shares for c in db.scalars(select(FinanceBundleCorrection)
        .join(FinanceStoredCorrectionRequest,FinanceStoredCorrectionRequest.id==FinanceBundleCorrection.request_id)
        .where(FinanceBundleCorrection.purchase_id==purchase.id,FinanceStoredCorrectionRequest.status=='applied')))
    return purchase.shares+delta


def _check(db,s,corrected_shares,parts,*,own=False):
    from . import recharge_bundle_service as bundle
    purchase=s['bundle'];rule=bundle._rule(db,purchase.rule_id);original=effective_shares(db,purchase)
    if s['cash'].amount_cents!=original*rule.principal_cents_per_share:
        raise HTTPException(409,'原组合有效本金与完整份数不一致，请先核对原更正账本')
    active=list(db.scalars(select(RechargeBundleRefund).where(RechargeBundleRefund.purchase_id==purchase.id,
        RechargeBundleRefund.status.in_(['reserved','applied']))))
    if corrected_shares<sum(r.shares for r in active):
        raise HTTPException(409,'正确组合份数不能少于已实际退回或已批准原款退款的份数，请先处理未支付申请')
    delta=corrected_shares-original
    if delta>0:
        # Additional usable rights require the still-approved original offering.
        bundle._sale_rule(db,rule.id,purchase.store_id)
        if any(w.expires_on<today() for _p,_c,w,_b in parts):
            raise HTTPException(409,'原组合权益已过期，不能补记可用份额或自动续期；请先按公司原权益责任规则处理')
    for _part,component,wallet,benefit in parts:
        units=component.units_per_share*delta;required=max(0,-units)
        if own and wallet.reserved_units<required:raise HTTPException(409,'原组合赠品更正占额不完整，请先核对原批准')
        available=wallet.balance_units-wallet.reserved_units+(required if own else 0)
        if required>available:
            raise HTTPException(409,'原组合部分赠品已使用或占用，不能纠掉对应份额；须先取消未用占额或经原服务／兑换业务合法回退，不能借其他批次补足')
        if corrected_shares*component.units_per_share>100000000 or corrected_shares*component.units_per_share*benefit.credit_cents_per_unit>100000000000:
            raise HTTPException(422,'更正后的原组合权益总单位或价值超出允许范围')
    return original,delta


def prepare(db,user,s,values):
    from . import recharge_bundle_service as bundle
    purchase=s['bundle']
    if not purchase or values.get('bundle_purchase_id')!=purchase.id:
        raise HTTPException(409,'组合原款更正必须明确同店原购买批次，并完整关联其原赠品')
    rule=bundle._rule(db,purchase.rule_id);amount=values['amount_cents']
    if amount%rule.principal_cents_per_share:raise HTTPException(422,'组合正确本金须是原冻结每份本金的整数倍；不能拆开改赠品比例')
    shares=amount//rule.principal_cents_per_share
    if shares>10000:raise HTTPException(422,'组合正确总份数不能超过10000份')
    parts=bundle._components(db,purchase,True);original,delta=_check(db,s,shares,parts)
    return {'bundle_purchase_id':purchase.id,'bundle_rule_id':rule.id,'original_shares':original,'corrected_shares':shares,
        'bundle_components':[{'component_id':p.id,'wallet_id':w.id,'grant_entry_id':p.grant_entry_id,
            'units_per_share':c.units_per_share,'delta_units':c.units_per_share*delta,'expires_on':str(w.expires_on)} for p,c,w,b in parts]}


def create(db,request,values):
    from datetime import date
    row=FinanceBundleCorrection(request_id=request.id,purchase_id=values['bundle_purchase_id'],rule_id=values['bundle_rule_id'],
        original_shares=values['original_shares'],corrected_shares=values['corrected_shares'])
    db.add(row);db.flush()
    db.add_all([FinanceBundleCorrectionComponent(correction_id=row.id,**{**p,'expires_on':date.fromisoformat(p['expires_on'])}) for p in values['bundle_components']])


def validated_parts(db,request,s,*,own=False):
    from . import recharge_bundle_service as bundle
    fix=correction_for(db,request)
    if not fix:return []
    if not s['bundle'] or fix.purchase_id!=s['bundle'].id or fix.rule_id!=s['bundle'].rule_id:
        raise HTTPException(409,'原组合更正批次与冻结申请不符')
    parts=bundle._components(db,s['bundle'],True);original,delta=_check(db,s,fix.corrected_shares,parts,own=own)
    if fix.original_shares!=original:raise HTTPException(409,'原组合已追加其他份数更正，请重新核对')
    frozen={p.component_id:p for p in db.scalars(select(FinanceBundleCorrectionComponent).where(FinanceBundleCorrectionComponent.correction_id==fix.id))}
    if set(frozen)!={p.id for p,c,w,b in parts}:raise HTTPException(409,'原组合更正缺少完整权益单位')
    result=[]
    for p,c,w,b in parts:
        f=frozen[p.id]
        if (f.wallet_id,f.grant_entry_id,f.units_per_share,f.delta_units,f.expires_on)!=(w.id,p.grant_entry_id,c.units_per_share,c.units_per_share*delta,w.expires_on):
            raise HTTPException(409,'原组合冻结权益或有效期已变化，不能执行')
        result.append((f,w,b))
    return result


def approve(db,request,s):
    for part,wallet,_ in validated_parts(db,request,s):
        wallet.reserved_units+=max(0,-part.delta_units);wallet.updated_at=utcnow()


def release(db,request,s):
    # Releasing an approval must remain possible after the sale/expiry window.
    from .group_benefits_models import BenefitWallet
    fix=correction_for(db,request)
    if not fix:return
    for part in db.scalars(select(FinanceBundleCorrectionComponent).where(FinanceBundleCorrectionComponent.correction_id==fix.id).order_by(FinanceBundleCorrectionComponent.wallet_id)):
        wallet=db.scalar(select(BenefitWallet).where(BenefitWallet.id==part.wallet_id,BenefitWallet.member_id==s['wallet'].id).with_for_update())
        if not wallet or wallet.reserved_units<max(0,-part.delta_units):raise HTTPException(409,'原组合更正占额不一致，请核对')
        wallet.reserved_units-=max(0,-part.delta_units);wallet.updated_at=utcnow()


def post(db,user,row,request,s,values):
    from . import group_benefits_service as benefits
    for part,wallet,rule in validated_parts(db,request,s,own=True):
        wallet.reserved_units-=max(0,-part.delta_units)
        if not part.delta_units:continue
        original=db.scalar(select(BenefitEntry).where(BenefitEntry.id==part.grant_entry_id))
        wallet.correction_units+=part.delta_units;wallet.balance_units+=part.delta_units;wallet.updated_at=utcnow()
        entry=benefits._entry(db,user,wallet,row,'correction',part.delta_units,values['evidence_id'],
            '原组合收款误记同步更正原赠品：'+values['reason'],original=original)
        db.add(FinanceBundleCorrectionPosting(component_id=part.id,benefit_entry_id=entry.id))
        if part.delta_units>0 and rule.kind=='points':
            from .membership_points import settle_point_debt
            settle_point_debt(db,user,s['wallet'],wallet,row,values['evidence_id'])


def describe(db,user,request):
    from .business_finance_service import clean
    from . import group_service as group
    from .group_benefits_models import BenefitWallet,BenefitRule
    from .recharge_bundle_service import UNITS
    fix=correction_for(db,request)
    if not fix:return None
    with group.authority(db,user) as sid:
        group._member(db,request.member_id,sid)
        parts=[]
        for p,w,r in db.execute(select(FinanceBundleCorrectionComponent,BenefitWallet,BenefitRule)
            .join(BenefitWallet,BenefitWallet.id==FinanceBundleCorrectionComponent.wallet_id).join(BenefitRule,BenefitRule.id==BenefitWallet.rule_id)
            .where(FinanceBundleCorrectionComponent.correction_id==fix.id).order_by(FinanceBundleCorrectionComponent.id)):
            parts.append(clean(p)|{'name':r.name,'kind':r.kind,'unit_label':UNITS[r.kind]})
        return clean(fix)|{'components':parts}
