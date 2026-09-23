"""Trusted aftercare callbacks; no endpoint, cash creation, or intermediate commit."""
from contextlib import contextmanager
from sqlalchemy import select,func
from fastapi import HTTPException
from .db import utcnow
from .flow_models import Case
from .group_models import GroupMember,GroupEntry,GroupPaymentLink,GroupEvent
from .group_benefits_models import BenefitEntry,BenefitWallet,BenefitPaymentLink
from .group_aftercare_models import GroupAftercareHold,GroupAftercarePosting
from . import group_service as group,group_benefits_service as benefits,flow_engine as flow


@contextmanager
def authority(db,user,aftercare,source,plan_id,phase):
    roles={'admin','manager'} if phase=='reserve' else {'admin','finance'} if phase=='apply' else {'admin','manager','finance','sales','service','reception','customer_service'}
    with group.authority(db,user,roles) as sid:
        if aftercare.store_id!=sid or source.store_id!=sid or aftercare.id==source.id:raise HTTPException(404,'售后方案与原业务必须属于当前门店')
        from .aftercare_service import assert_group_plan
        plan=assert_group_plan(db,aftercare,source,plan_id,phase)
        old=db.info.get('_group_aftercare_authority');db.info['_group_aftercare_authority']=(aftercare.id,source.id,plan_id,phase)
        try:yield plan
        finally:
            db.flush()
            if old is None:db.info.pop('_group_aftercare_authority',None)
            else:db.info['_group_aftercare_authority']=old


def _source_member(db,user,source,member_id):
    member=group._member(db,member_id,source.store_id)
    relation=group.member_for_customer(db,user,source.customer_id)
    if not relation['member'] or relation['member']['id']!=member.id:raise HTTPException(409,'原核销会员与原单客户不一致')
    return member


def _remaining(db,kind,original):
    if kind=='principal':
        used=db.scalar(select(func.coalesce(func.sum(GroupEntry.amount_cents),0)).where(GroupEntry.original_id==original.id,GroupEntry.purpose=='reverse')) or 0
        initial=-original.amount_cents
    else:
        used=db.scalar(select(func.coalesce(func.sum(BenefitEntry.units),0)).where(BenefitEntry.original_id==original.id,BenefitEntry.purpose=='reverse')) or 0
        initial=-original.units
    reserved=db.scalar(select(func.coalesce(func.sum(GroupAftercareHold.units),0)).where(GroupAftercareHold.kind==kind,GroupAftercareHold.original_id==original.id,GroupAftercareHold.status=='reserved')) or 0
    return initial-used-reserved


def _list(db,user,source):
    result=[]
    for original in db.scalars(select(GroupEntry).where(GroupEntry.case_id==source.id,GroupEntry.store_id==source.store_id,GroupEntry.purpose=='capture').order_by(GroupEntry.id)):
        _source_member(db,user,source,original.member_id)
        remaining=_remaining(db,'principal',original)
        if remaining>0:result.append({'kind':'principal','entry_id':original.id,'member_id':original.member_id,'remaining_units':remaining,
            'remaining_credit_cents':remaining,'credit_per_unit':1,'discount_per_unit':0,'discount_remaining_cents':0,'unit':'分','name':'原集团本金核销'})
    for original in db.scalars(select(BenefitEntry).where(BenefitEntry.case_id==source.id,BenefitEntry.store_id==source.store_id,BenefitEntry.purpose=='capture').order_by(BenefitEntry.id)):
        wallet=db.scalar(select(BenefitWallet).where(BenefitWallet.id==original.wallet_id));_source_member(db,user,source,wallet.member_id)
        rule=benefits._rule(db,wallet.rule_id);remaining=_remaining(db,'benefit',original)
        discount=rule.credit_cents_per_unit-(rule.sale_cents_per_unit if wallet.source_kind=='purchase' else 0)
        if remaining>0:result.append({'kind':'benefit','entry_id':original.id,'member_id':wallet.member_id,'wallet_id':wallet.id,'remaining_units':remaining,
            'remaining_credit_cents':remaining*rule.credit_cents_per_unit,'credit_per_unit':rule.credit_cents_per_unit,
            'discount_per_unit':discount,'discount_remaining_cents':remaining*discount,'unit':benefits.KINDS[rule.kind],'name':rule.name,
            'rule_id':rule.id,'rule_version':rule.rule_version,'expires_on':wallet.expires_on.isoformat()})
    return result


def eligible_capture_sources(db,user,source_case):
    with group.authority(db,user,{'admin','manager','finance','sales','service','auditor'}) as sid:
        row=flow.get_case(db,user,source_case.id)
        if row.store_id!=sid:raise HTTPException(404,'本店原核销业务不存在')
        from .business_finance_sources import eligible_advance_credits
        from .repair_package_aftercare import eligible_capture_sources as package_sources
        return _list(db,user,row)+eligible_advance_credits(db,user,row)+package_sources(db,user,row)


def _selections(values):
    cleaned=[]
    for value in values:
        if value.get('kind') not in {'principal','benefit','advance','repair_package'}:raise HTTPException(422,'原核销退回类型不受支持')
        if any(type(value.get(k)) is not int or value[k]<=0 for k in ('entry_id','units')) or type(value.get('credit_cents')) is not int or value['credit_cents']<0 or value['credit_cents']==0 and value['kind']!='repair_package':raise HTTPException(422,'原核销编号和退回数量必须为正整数；只有套餐原组件可以有零分价值尾数')
        cleaned.append({k:value[k] for k in ('kind','entry_id','units','credit_cents')})
    if len({(x['kind'],x['entry_id']) for x in cleaned})!=len(cleaned):raise HTTPException(422,'同一原核销不能重复选择')
    return sorted(cleaned,key=lambda x:(x['kind'],x['entry_id']))


def reserve_returns(db,user,aftercare_case,source_case,plan_id,selections,evidence_id):
    with authority(db,user,aftercare_case,source_case,plan_id,'reserve') as plan:
        selected=_selections(selections)
        if selected!=_selections(plan['selections']):raise HTTPException(409,'原核销退回与独立批准的原路方案不一致')
        flow.file_exists(db,aftercare_case,evidence_id)
        if db.scalar(select(GroupAftercareHold.id).where(GroupAftercareHold.plan_id==plan_id,GroupAftercareHold.source_case_id==source_case.id)):
            raise HTTPException(409,'本方案原核销退回已登记，不能重复批准占额')
        # All group operations serialize on the member before querying remaining.
        for key in sorted({r['member_id'] for r in _list(db,user,source_case)}):
            member=_source_member(db,user,source_case,key);member.updated_at=utcnow()
        db.flush();available={(r['kind'],r['entry_id']):r for r in _list(db,user,source_case)}
        for value in selected:
            if value['kind'] in {'advance','repair_package'}:continue
            source=available.get((value['kind'],value['entry_id']))
            if not source or value['units']>source['remaining_units'] or value['credit_cents']!=value['units']*source['credit_per_unit']:
                raise HTTPException(409,'退回超过原核销剩余额度或不符冻结单位价值')
            db.add(GroupAftercareHold(aftercare_case_id=aftercare_case.id,source_case_id=source_case.id,plan_id=plan_id,
                kind=value['kind'],original_id=value['entry_id'],member_id=source['member_id'],wallet_id=source.get('wallet_id'),
                units=value['units'],credit_cents=value['credit_cents'],discount_cents=value['units']*source['discount_per_unit'],evidence_id=evidence_id))
        from .business_finance_sources import reserve_advance_returns
        reserve_advance_returns(db,user,aftercare_case,source_case,plan_id,selected,evidence_id)
        from .repair_package_aftercare import reserve_returns as reserve_package_returns
        reserve_package_returns(db,user,aftercare_case,source_case,plan_id,selected,evidence_id)
        db.flush()
        return {'credit_cents':sum(v['credit_cents'] for v in selected if v['kind']!='advance')}


def cancel_returns(db,user,aftercare_case,source_case,plan_id):
    with authority(db,user,aftercare_case,source_case,plan_id,'cancel'):
        holds=list(db.scalars(select(GroupAftercareHold).where(GroupAftercareHold.plan_id==plan_id,GroupAftercareHold.source_case_id==source_case.id).with_for_update()))
        if any(h.status=='applied' for h in holds):raise HTTPException(409,'已生效原核销退回不能取消或覆盖')
        for hold in holds:
            if hold.status=='reserved':hold.status='released'
        from .business_finance_sources import cancel_advance_returns
        cancel_advance_returns(db,user,aftercare_case,source_case,plan_id)
        from .repair_package_aftercare import cancel_returns as cancel_package_returns
        cancel_package_returns(db,user,aftercare_case,source_case,plan_id)
        db.flush()


def apply_returns(db,user,aftercare_case,source_case,plan_id,evidence_id):
    with authority(db,user,aftercare_case,source_case,plan_id,'apply') as plan:
        flow.file_exists(db,aftercare_case,evidence_id)
        holds=list(db.scalars(select(GroupAftercareHold).where(GroupAftercareHold.plan_id==plan_id,GroupAftercareHold.source_case_id==source_case.id).order_by(GroupAftercareHold.id).with_for_update()))
        expected=[x for x in _selections(plan['selections']) if x['kind'] not in {'advance','repair_package'}]
        actual=_selections([{'kind':h.kind,'entry_id':h.original_id,'units':h.units,'credit_cents':h.credit_cents} for h in holds])
        if expected!=actual or any(h.status!='reserved' for h in holds):raise HTTPException(409,'原核销退回占额缺失、已释放或已生效')
        output=[]
        for hold in holds:
            member=_source_member(db,user,source_case,hold.member_id);member.updated_at=utcnow()
            if hold.kind=='principal':
                original=db.scalar(select(GroupEntry).where(GroupEntry.id==hold.original_id,GroupEntry.case_id==source_case.id,GroupEntry.purpose=='capture').with_for_update())
                if not original or _remaining(db,'principal',original)<0:raise HTTPException(409,'原本金可退额度不守恒')
                source=db.scalar(select(GroupPaymentLink).where(GroupPaymentLink.entry_id==original.id))
                if not source:raise HTTPException(409,'原本金核销缺少业务抵扣')
                member.balance_cents+=hold.units
                entry=group._entry(db,user,member,source_case,'reverse',hold.units,evidence_id,original)
                db.add(GroupPaymentLink(case_id=source_case.id,entry_id=entry.id,reservation_id=source.reservation_id,amount_cents=-hold.credit_cents))
            else:
                wallet=benefits._wallet(db,member,hold.wallet_id);rule=benefits._rule(db,wallet.rule_id)
                original=db.scalar(select(BenefitEntry).where(BenefitEntry.id==hold.original_id,BenefitEntry.case_id==source_case.id,BenefitEntry.wallet_id==wallet.id,BenefitEntry.purpose=='capture').with_for_update())
                if not original or _remaining(db,'benefit',original)<0:raise HTTPException(409,'原权益可退份数不守恒')
                source=db.scalar(select(BenefitPaymentLink).where(BenefitPaymentLink.entry_id==original.id))
                if not source:raise HTTPException(409,'原权益核销缺少业务抵扣')
                wallet.balance_units+=hold.units;wallet.updated_at=utcnow()
                entry=benefits._entry(db,user,wallet,source_case,'reverse',hold.units,evidence_id,'已批准售后原路退回',
                    credit=-hold.credit_cents,original=original,clearing=hold.units*rule.settlement_cents_per_unit)
                db.add(BenefitPaymentLink(case_id=source_case.id,entry_id=entry.id,reservation_id=source.reservation_id,amount_cents=-hold.credit_cents))
                if rule.kind=='points':
                    from .membership_points import settle_point_debt
                    settle_point_debt(db,user,member,wallet,aftercare_case,evidence_id)
            hold.status='applied'
            db.add(GroupAftercarePosting(hold_id=hold.id,kind=hold.kind,entry_id=entry.id,evidence_id=evidence_id,actor_id=user.id))
            db.add(GroupEvent(member_id=member.id,actor_id=user.id,action='aftercare_return',detail={'case_id':source_case.id,'aftercare_case_id':aftercare_case.id,'plan_id':plan_id,'kind':hold.kind,'entry_id':entry.id}))
            output.append({'kind':hold.kind,'entry_id':entry.id,'credit_cents':hold.credit_cents,'external_discount_cents':hold.discount_cents})
        from .business_finance_sources import apply_advance_returns
        output+=apply_advance_returns(db,user,aftercare_case,source_case,plan_id,plan['selections'],evidence_id)
        from .repair_package_aftercare import apply_returns as apply_package_returns
        output+=apply_package_returns(db,user,aftercare_case,source_case,plan_id,evidence_id)
        db.flush();return output
