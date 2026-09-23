"""Earned points follow completed customer consumption, including original refunds."""
from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import today,utcnow
from .tenancy import single_store
from .group_models import GroupMember,GroupIdentityLink
from .flow_models import Case,PaymentLink,FileAsset,FlowEvent
from .group_benefits_models import BenefitWallet,BenefitRule,BenefitEntry
from .membership_models import (MembershipRule,PointsClaim,PointsChange,PointsRecovery,PointsDebt,PointsDebtPayment)
from . import group_service as group


def supported(row):
    from .repair_service import is_detailed
    return is_detailed(row) or (row.kind=='retail' and row.flow_version==2)
@contextmanager
def source_authority(db,user,row):
    if single_store(db)!=row.store_id or not supported(row):raise HTTPException(403,'消费积分只能由本店受支持原业务同步')
    old=db.info.get('_group_authority');db.info['_group_authority']=('consumption',user.id,row.store_id)
    try:yield
    finally:
        if old is None:db.info.pop('_group_authority',None)
        else:db.info['_group_authority']=old


def freeze_points_rule(db,user,row):
    """Called at first customer authorization; an absent rule freezes no reward."""
    if not supported(row):return
    with source_authority(db,user,row):
        if db.scalar(select(PointsClaim.id).where(PointsClaim.case_id==row.id)):return
        from .membership_service import current_period
        member=db.scalar(select(GroupMember).join(GroupIdentityLink,GroupIdentityLink.identity_id==GroupMember.identity_id)
            .where(GroupIdentityLink.local_kind=='customer',GroupIdentityLink.local_id==row.customer_id,
                GroupIdentityLink.store_id==row.store_id,GroupMember.active.is_(True)).with_for_update())
        rule=None
        if member:
            period=current_period(db,member)
            if period:
                prior=db.scalar(select(MembershipRule).where(MembershipRule.id==period.rule_id))
                latest=db.scalar(select(MembershipRule).where(MembershipRule.code==prior.code).order_by(MembershipRule.rule_version.desc()))
                if latest.enabled and latest.points_enabled and row.store_id in latest.allowed_store_ids:rule=latest
        db.add(PointsClaim(case_id=row.id,store_id=row.store_id,member_id=member.id if member else None,rule_id=rule.id if rule else None))
        if member:member.updated_at=utcnow()
        db.flush()


def outstanding_debt(db,member_id):
    debts=list(db.scalars(select(PointsDebt).where(PointsDebt.member_id==member_id)))
    return sum(d.units-(db.scalar(select(func.coalesce(func.sum(PointsDebtPayment.units),0)).where(PointsDebtPayment.debt_id==d.id)) or 0) for d in debts)
def require_points_clear(db,member_id):
    if outstanding_debt(db,member_id)>0:raise HTTPException(409,'原消费退款尚有待追回积分；请先核对抵扣，不能继续使用或兑换积分，已有占额可释放')


def settle_point_debt(db,user,member,wallet,row,evidence_id,maximum_units=None):
    """New/free-returned points repay attributable debt; no negative wallet."""
    rule=db.scalar(select(BenefitRule).where(BenefitRule.id==wallet.rule_id))
    if rule.kind!='points':return 0
    from .group_benefits_service import _entry
    debts=list(db.scalars(select(PointsDebt).where(PointsDebt.member_id==member.id).order_by(PointsDebt.id)));consumed=0
    for debt in debts:
        paid=db.scalar(select(func.coalesce(func.sum(PointsDebtPayment.units),0)).where(PointsDebtPayment.debt_id==debt.id)) or 0
        amount=min(debt.units-paid,wallet.balance_units-wallet.reserved_units)
        if maximum_units is not None:amount=min(amount,maximum_units-consumed)
        if amount<=0:continue
        wallet.balance_units-=amount
        entry=_entry(db,user,wallet,row,'adjust',-amount,evidence_id,'新增或退回积分先抵原消费退货待追回积分')
        db.add(PointsDebtPayment(debt_id=debt.id,benefit_entry_id=entry.id,store_id=row.store_id,units=amount))
        consumed+=amount;db.flush()
    return consumed


def basis_amount(db,row):
    from .repair_service import is_detailed
    if is_detailed(row):
        if not row.data.get('released_date'):return 0
        from .repair_models import RepairAllocation,RepairPayment
        allocation=db.scalar(select(RepairAllocation).where(RepairAllocation.case_id==row.id,RepairAllocation.payer_type=='customer'))
        links=list(db.scalars(select(PaymentLink).join(RepairPayment,RepairPayment.payment_link_id==PaymentLink.id)
            .where(RepairPayment.allocation_id==allocation.id))) if allocation else []
        cash=sum(p.amount_cents*(1 if p.direction=='in' else -1) for p in links)
        principal=group.case_paid_amount(db,row.id)
        from .business_finance_sources import case_credit_amount
        from .aftercare_service import net_charge
        from .repair_package_models import PackagePaymentLink
        packages=list(db.scalars(select(PackagePaymentLink).where(PackagePaymentLink.case_id==row.id,
            PackagePaymentLink.store_id==row.store_id)))
        face=sum(p.amount_cents for p in packages);paid=sum(p.recognized_cents for p in packages)
        # Only actual component captures/reversals count. Independent interval
        # rounding may give C=0/P=1, so adjust the charge cap as well as the paid
        # basis; reservations and unused-package purchase/refund cash earn none.
        charge=net_charge(db,row,allocation.id) if allocation else 0
        return max(0,min(charge-face+paid,cash+principal+case_credit_amount(db,row.id)+paid))
    if row.kind=='retail' and row.flow_version==2 and row.data.get('accepted_date'):
        from .retail_service import totals
        amounts=totals(db,row)
        # Gift face and internal settlement are not paid consumption. Restoring
        # original units later does not award/recover points a second time.
        consideration=amounts['cash_paid_cents']+amounts['advance_credit_cents']+amounts.get('group_recognized_cents',0)
        return max(0,min(amounts['net_price_cents'],consideration))
    return 0


def _proof(db,row,evidence_id):
    if not evidence_id:
        evidence_id=row.data.get('release_evidence_id')
    if not evidence_id:
        events=list(db.scalars(select(FlowEvent).where(FlowEvent.case_id==row.id).order_by(FlowEvent.id.desc()).limit(25)))
        evidence_id=next((e.detail.get('evidence_id') for e in events if e.detail.get('evidence_id')),None)
    asset=db.scalar(select(FileAsset).where(FileAsset.id==evidence_id,FileAsset.store_id==row.store_id))
    if not asset or asset.generated:raise HTTPException(409,'消费积分同步缺少原业务实际履约或收退款凭据')
    if asset.case_id!=row.id:
        from .aftercare_service import assert_points_evidence
        from .business_finance_sources import source_evidence_allowed
        if not assert_points_evidence(db,row,evidence_id) and not source_evidence_allowed(db,row,asset):
            raise HTTPException(409,'积分同步凭据未关联本次原业务的已生效售后或财务事实')
    from .file_security import require_usable
    require_usable(db,asset);return asset.id


def sync_consumption_points(db,user,row,evidence_id=None):
    if not supported(row):return
    with source_authority(db,user,row):
        claim=db.scalar(select(PointsClaim).where(PointsClaim.case_id==row.id).with_for_update())
        # No retroactive signup or reward for a source without an authorized frozen rule.
        if not claim or not claim.rule_id or not claim.member_id:return
        member=db.scalar(select(GroupMember).where(GroupMember.id==claim.member_id).with_for_update())
        rule=db.scalar(select(MembershipRule).where(MembershipRule.id==claim.rule_id))
        basis=basis_amount(db,row);target=basis*rule.points_numerator//rule.points_denominator_fen
        if target>9007199254740991:raise HTTPException(409,'本单累计消费积分超过整数精度支持范围，请核对配置')
        delta=target-claim.target_units
        if not delta:
            if basis!=claim.basis_cents:claim.basis_cents=basis
            return
        evidence=_proof(db,row,evidence_id)
        from .group_benefits_service import _issue,_entry
        change=PointsChange(claim_id=claim.id,store_id=row.store_id,case_id=row.id,units=delta,basis_cents=basis,evidence_id=evidence,actor_id=user.id)
        if delta>0:
            benefit_rule=db.scalar(select(BenefitRule).where(BenefitRule.id==rule.points_benefit_rule_id))
            wallet,entry=_issue(db,user,member,row,benefit_rule,delta,'grant',evidence,'按冻结规则及已履约客户净消费累计发放积分')
            change.wallet_id=wallet.id;db.add(change);db.flush()
            settle_point_debt(db,user,member,wallet,row,evidence)
        else:
            db.add(change);db.flush();remaining=-delta
            # Recovery only consumes unreserved units from this source's original awards.
            ids=select(PointsChange.wallet_id).where(PointsChange.claim_id==claim.id,PointsChange.units>0)
            wallets=list(db.scalars(select(BenefitWallet).where(BenefitWallet.id.in_(ids)).order_by(BenefitWallet.id).with_for_update()))
            for wallet in wallets:
                amount=min(remaining,wallet.balance_units-wallet.reserved_units)
                if amount<=0:continue
                original=db.scalar(select(BenefitEntry).where(BenefitEntry.wallet_id==wallet.id,BenefitEntry.purpose=='grant'))
                wallet.balance_units-=amount
                entry=_entry(db,user,wallet,row,'adjust',-amount,evidence,'原实际消费减少，追回原批次积分',original=original)
                db.add(PointsRecovery(change_id=change.id,benefit_entry_id=entry.id,units=amount));remaining-=amount
            if remaining:db.add(PointsDebt(change_id=change.id,member_id=member.id,units=remaining))
        claim.basis_cents=basis;claim.target_units=target;member.updated_at=utcnow();db.flush()
