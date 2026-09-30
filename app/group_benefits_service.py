"""Fixed-unit benefits. Principal, gift fen, points and passes never mix units."""
from datetime import timedelta
import uuid
from fastapi import HTTPException
from sqlalchemy import select, func
from .db import today, utcnow
from .models import Store, CashEntry
from .flow_models import Case, Task, Customer
from .group_models import GroupMember, GroupEvent
from .group_benefits_models import (BenefitRule, BenefitWallet, BenefitEntry, BenefitReservation,
    BenefitPaymentLink, BenefitSettlement, BenefitRefund)
from . import group_service as group
from . import flow_engine as eng

KINDS = {'bonus':'赠送金额（分）', 'points':'积分', 'coupon':'消费券（张）', 'package':'作业套餐（次）'}
FINANCE = {'admin', 'finance'}
MANAGERS = {'admin', 'manager'}


def case_paid_amount(db, case_id):
    return db.scalar(select(func.coalesce(func.sum(BenefitPaymentLink.amount_cents), 0)).where(BenefitPaymentLink.case_id == case_id)) or 0


def case_reserved_amount(db, case_id):
    return db.scalar(select(func.coalesce(func.sum(BenefitReservation.credit_cents), 0)).where(
        BenefitReservation.case_id == case_id, BenefitReservation.status == 'reserved')) or 0


def _rule(db, key):
    row = db.scalar(select(BenefitRule).where(BenefitRule.id == key))
    if not row:
        raise HTTPException(404, '权益规则版本不存在')
    return row


def _current_rule(db, key):
    row=_rule(db,key)
    latest=db.scalar(select(func.max(BenefitRule.rule_version)).where(
        BenefitRule.issuer_store_id==row.issuer_store_id,BenefitRule.code==row.code))
    if row.rule_version!=latest:
        raise HTTPException(409,'此规则已有新版本，请刷新后发行；已发行批次仍按原版本使用')
    return row


def rule_info(row, financial=True):
    fields = ['id','issuer_store_id','code','rule_version','kind','name','allowed_store_ids',
        'credit_cents_per_unit','sale_cents_per_unit','exchange_points_per_unit','refund_policy',
        'validity_days','service_code']
    if financial:
        fields += ['settlement_cents_per_unit','discount_bearer']
    return {key: getattr(row, key) for key in fields}


def rules(db, user):
    with group.authority(db, user) as sid:
        rows = list(db.scalars(select(BenefitRule).order_by(BenefitRule.id.desc()).limit(501)))
        if len(rows) > 500:
            raise HTTPException(413, '权益规则超过当前查询上限，请由管理员整理查询范围')
        return {'items': [rule_info(row, user.role in eng.MANAGEMENT) for row in rows
                          if sid in row.allowed_store_ids or sid == row.issuer_store_id]}


def create_rule(db, user, request_id, values):
    def operation(sid):
        ids = values['allowed_store_ids']
        actual = set(db.scalars(select(Store.id).where(Store.id.in_(ids), Store.active.is_(True))))
        if len(ids) != len(set(ids)) or actual != set(ids) or sid not in ids:
            raise HTTPException(422, '适用门店必须启用且包含发行门店，不得重复')
        if user.role!='admin' and set(ids)!={sid}:
            raise HTTPException(403, '跨店权益规则须由集团管理员配置，单店主管不能扩大他店优惠承担')
        if values['settlement_cents_per_unit'] > values['credit_cents_per_unit']:
            raise HTTPException(422, '每单位内部结算金额不能超过抵扣金额')
        if values['sale_cents_per_unit']>values['credit_cents_per_unit']:
            raise HTTPException(422,'固定券包售价不能超过抵扣额')
        expected=values['credit_cents_per_unit'] if values['discount_bearer']=='group' else values['sale_cents_per_unit']
        if values['settlement_cents_per_unit']!=expected:
            raise HTTPException(422,'集团承担优惠时结算价须等于抵扣额；履约店承担时须等于售价。共同承担规则尚未开放')
        if values['kind'] == 'bonus' and values['credit_cents_per_unit'] != 1:
            raise HTTPException(422, '赠送金额使用整数分，每单位只能抵扣一分')
        if values['kind'] in {'bonus', 'points'} and (values['sale_cents_per_unit'] or values['exchange_points_per_unit'] or values['refund_policy'] != 'none'):
            raise HTTPException(422, '赠金和积分不能当作现金购买或退款，须独立赠送/调整')
        if (values['kind'] == 'package') != bool(values['service_code']):
            raise HTTPException(422, '次数套餐必须冻结作业项目编码，其他权益不填写作业编码')
        version = (db.scalar(select(func.max(BenefitRule.rule_version)).where(
            BenefitRule.issuer_store_id == sid, BenefitRule.code == values['code'])) or 0) + 1
        row = BenefitRule(issuer_store_id=sid, rule_version=version, created_by=user.id, **values)
        db.add(row)
        db.flush()
        db.add(GroupEvent(store_id=sid, actor_id=user.id, action='benefit_rule', detail={'rule_id':row.id}))
        return rule_info(row)
    return group._execute(db, user, request_id, 'benefit_rule', values, operation, MANAGERS)


def _wallet(db, member, key):
    row = db.scalar(select(BenefitWallet).where(BenefitWallet.id == key,
        BenefitWallet.member_id == member.id).with_for_update())
    if not row:
        raise HTTPException(404, '该会员权益批次不存在')
    return row


def wallet_info(db, wallet, sid, financial=True):
    rule = _rule(db, wallet.rule_id)
    from .recharge_bundle_service import is_bundle_wallet
    info = {k:getattr(wallet,k) for k in ['id','version','member_id','rule_id','initial_units','correction_units','balance_units','reserved_units','source_kind']}
    info['effective_issued_units']=wallet.initial_units+wallet.correction_units
    info.update(available_units=wallet.balance_units-wallet.reserved_units,
        expires_on=wallet.expires_on.isoformat(), expired=wallet.expires_on < today(),
        usable_in_store=sid in rule.allowed_store_ids, rule=rule_info(rule,financial), bundle_origin=is_bundle_wallet(db,wallet.id))
    if wallet.issuer_store_id == sid:
        info.update(source_case_id=wallet.source_case_id, account_id=wallet.account_id)
    return info


def _member_benefits(db, user, member, sid):
    """Project the original benefit detail after its caller proves member access."""
    wallets = list(db.scalars(select(BenefitWallet).where(BenefitWallet.member_id == member.id).order_by(BenefitWallet.id.desc()).limit(501)))
    if len(wallets)>500:
        raise HTTPException(413,'会员权益批次超过当前上限，请联系管理员按期间核对')
    ids=[w.id for w in wallets]
    entries=list(db.scalars(select(BenefitEntry).where(BenefitEntry.wallet_id.in_(ids),BenefitEntry.store_id==sid).order_by(BenefitEntry.id.desc()).limit(100)))
    reservations=list(db.scalars(select(BenefitReservation).where(BenefitReservation.wallet_id.in_(ids)).order_by(BenefitReservation.id.desc()).limit(100)))
    refunds=list(db.scalars(select(BenefitRefund).where(BenefitRefund.wallet_id.in_(ids)).order_by(BenefitRefund.id.desc()).limit(100)))
    return {'member':group._wallet(member),
        'wallets':[wallet_info(db,w,sid,user.role in eng.MANAGEMENT) for w in wallets],
        'entries':[{k:getattr(e,k) for k in ['id','wallet_id','case_id','purpose','units','credit_cents','original_id']} for e in entries],
        'reservations':[{k:getattr(r,k) for k in ['id','version','wallet_id','case_id','units','credit_cents','status']} for r in reservations],
        'refunds':[{k:getattr(r,k) for k in ['id','version','wallet_id','case_id','units','status','requested_by']} for r in refunds]}


def member_detail(db, user, customer_id):
    local = group.member_for_customer(db, user, customer_id)
    if not local['member']:
        return {**local, 'wallets':[], 'entries':[], 'reservations':[], 'refunds':[]}
    with group.authority(db,user) as sid:
        member = group._member(db, local['member']['id'], sid)
        return {**local, **_member_benefits(db,user,member,sid)}


def member_detail_by_id(db, user, member_id):
    # The original detail checks current store/role/member and, for sales and
    # reception, responsibility for a linked local customer. No customer is chosen.
    group.member_detail(db,user,member_id)
    with group.authority(db,user) as sid:
        member = group._member(db,member_id,sid)
        detail = _member_benefits(db,user,member,sid)
        return {**detail, 'history_limit':100,
            'history_may_be_truncated':{key:len(detail[key])>=100
                for key in ('entries','reservations','refunds')}}


def _usable(wallet, rule, sid):
    if sid not in rule.allowed_store_ids or wallet.expires_on < today():
        raise HTTPException(409, '权益不适用于当前门店或已过期；已占用权益仍可明确释放')


def _due(db, row, include_reservations):
    from . import repair_service
    if repair_service.is_detailed(row):
        return repair_service.customer_due(db,row,include_reservations=include_reservations)
    if row.kind!='repair' or row.state not in {'settling','credit_open'} or row.data.get('payer')!='客户':
        raise HTTPException(409,'权益仅用于已质检待结算维修的客户承担部分')
    due=row.amount_cents-eng.paid_amount(db,row)
    if include_reservations:
        due-=group.case_reserved_amount(db,row.id)+case_reserved_amount(db,row.id)
    return max(0,due)


def _sync(db,user,row):
    from . import repair_service
    if repair_service.is_detailed(row):
        repair_service.sync_after_member(db,user,row)
        return
    if _due(db,row,False)<=0:
        eng.finish_task(db,row,'receive',user)
        if row.state=='credit_open':
            row.state='completed';row.completed_date=today()
    else:
        eng.ensure_task(db,row,'receive','登记维修款到账','finance',reopen=True)


def _package_capacity(db, row, rule, units, excluding=None):
    if rule.kind!='package':
        return
    from . import repair_service
    capacity=repair_service.eligible_benefit_units(db,row,rule.service_code)
    # Same service across all frozen package versions/batches shares capacity.
    ids=select(BenefitWallet.id).join(BenefitRule,BenefitRule.id==BenefitWallet.rule_id).where(
        BenefitRule.kind=='package',BenefitRule.service_code==rule.service_code)
    used=-(db.scalar(select(func.coalesce(func.sum(BenefitEntry.units),0)).where(
        BenefitEntry.case_id==row.id,BenefitEntry.store_id==row.store_id,BenefitEntry.wallet_id.in_(ids),
        BenefitEntry.purpose.in_(['capture','reverse']))) or 0)
    holds=select(func.coalesce(func.sum(BenefitReservation.units),0)).where(BenefitReservation.case_id==row.id,
        BenefitReservation.wallet_id.in_(ids),BenefitReservation.status=='reserved')
    if excluding:
        holds=holds.where(BenefitReservation.id!=excluding)
    if used+(db.scalar(holds) or 0)+units>capacity:
        raise HTTPException(409,'套餐核销份数超过本单已授权对应作业数量，请核对作业编码与其他占额')
    credit_capacity=repair_service.eligible_benefit_credit(db,row,rule.service_code)
    used_credit=db.scalar(select(func.coalesce(func.sum(BenefitEntry.credit_cents),0)).where(
        BenefitEntry.case_id==row.id,BenefitEntry.store_id==row.store_id,BenefitEntry.wallet_id.in_(ids),
        BenefitEntry.purpose.in_(['capture','reverse']))) or 0
    held_credit=select(func.coalesce(func.sum(BenefitReservation.credit_cents),0)).where(
        BenefitReservation.case_id==row.id,BenefitReservation.wallet_id.in_(ids),BenefitReservation.status=='reserved')
    if excluding:
        held_credit=held_credit.where(BenefitReservation.id!=excluding)
    if used_credit+(db.scalar(held_credit) or 0)+units*rule.credit_cents_per_unit>credit_capacity:
        raise HTTPException(409,'套餐抵扣超过本单已授权对应作业金额，不能抵用其他项目或配件')


def _cash(db,user,row,values,direction,amount,original=None):
    cash,account=group._cash(db,user,row,{**values,'amount_cents':amount},direction,original)
    cash.category='benefit_purchase' if direction=='in' else 'benefit_refund'
    cash.note='集团权益实际收退款；来源业务 '+row.number
    return cash,account


def _entry(db,user,wallet,row,purpose,units,evidence,reason,credit=0,original=None,cash=None,account=None,reference=None,clearing=0):
    entry=BenefitEntry(wallet_id=wallet.id,store_id=row.store_id,case_id=row.id,purpose=purpose,units=units,
        credit_cents=credit,original_id=original.id if original else None,cash_id=cash.id if cash else None,
        account_id=account.id if account else None,reference=reference,evidence_id=evidence,actor_id=user.id,reason=reason)
    db.add(entry);db.flush()
    if clearing:
        db.add_all([BenefitSettlement(store_id=row.store_id,entry_id=entry.id,side='center',amount_cents=clearing),
                    BenefitSettlement(store_id=row.store_id,entry_id=entry.id,side='store',amount_cents=-clearing)])
    return entry


def _issue(db,user,member,row,rule,units,purpose,evidence,reason,cash=None,account=None,reference=None,original=None):
    # Freeze the approved product annex in this exact issuance transaction.
    # Points remain their own unit and cannot acquire retail eligibility.
    from .retail_group_rules import guard_issuance, attach_issuance
    permit=guard_issuance(db,user,rule) if rule.kind in {'bonus','coupon','package'} else None
    wallet=BenefitWallet(member_id=member.id,rule_id=rule.id,issuer_store_id=row.store_id,source_case_id=row.id,
        source_kind=purpose,initial_units=units,balance_units=units,expires_on=today()+timedelta(days=rule.validity_days),
        cash_id=cash.id if cash else None,account_id=account.id if account else None,evidence_id=evidence,created_by=user.id)
    db.add(wallet);db.flush()
    entry=_entry(db,user,wallet,row,'exchange_in' if purpose=='exchange' else purpose,units,evidence,reason,
        original=original,cash=cash,account=account,reference=reference,clearing=units*rule.sale_cents_per_unit if cash else 0)
    attach_issuance(db,user,wallet,entry,permit)
    return wallet,entry


def _source(db,user,member,values,sid):
    row=group._case(db,user,member,values['case_id'],values['case_version'],sid)
    if row.kind not in {'lead','order','repair','membership'} or row.state in {'completed','cancelled','rejected','closed'}:
        raise HTTPException(409,'发行/赠送/积分调整须关联当前有效的客户接待、销售或维修业务')
    group._evidence(db,row,values['evidence_id'],user)
    return row


def _refund(db,user,member,wallet,rule,action,values,sid):
    if wallet.issuer_store_id!=sid or wallet.source_kind!='purchase' or rule.refund_policy=='none':
        raise HTTPException(409,'只能在原收款门店按已冻结规则退还购买且尚未使用的权益')
    row=group._case(db,user,member,wallet.source_case_id,values['case_version'],sid)
    if action in {'refund_request','refund_approve'} and rule.refund_policy=='unused_before_expiry' and today()>wallet.expires_on:
        raise HTTPException(409,'该发行批次的冻结规则不允许过期后申请或批准退款')
    entry=None
    if action=='refund_request':
        group._evidence(db,row,values['evidence_id'],user)
        if values['units']>wallet.balance_units-wallet.reserved_units:
            raise HTTPException(409,'申请份数超过尚未使用且未占用的权益')
        refund=BenefitRefund(wallet_id=wallet.id,case_id=row.id,units=values['units'],requested_by=user.id,
            evidence_id=values['evidence_id'],reason=values['reason'])
        db.add(refund);db.flush()
        eng.ensure_task(db,row,'benefit_refund_review_'+str(refund.id),'复核集团券包原款退款','manager')
        return row,refund,entry
    refund=db.scalar(select(BenefitRefund).where(BenefitRefund.id==values['refund_id'],BenefitRefund.wallet_id==wallet.id).with_for_update())
    if not refund:raise HTTPException(404,'本店权益退款申请不存在')
    group._version(refund,values['refund_version'])
    if refund.status not in {'requested','approved'}:raise HTTPException(409,'退款申请已结束')
    review='benefit_refund_review_'+str(refund.id);pay='benefit_refund_pay_'+str(refund.id)
    if action=='refund_approve':
        if refund.status!='requested':raise HTTPException(409,'退款已批准')
        if refund.requested_by==user.id and user.role!='admin':raise HTTPException(403,'退款申请人与审批人必须分开')
        if refund.units>wallet.balance_units-wallet.reserved_units:raise HTTPException(409,'权益已消费或占用，不能重复批准退款')
        wallet.reserved_units+=refund.units;refund.status='approved';refund.approved_by=user.id
        eng.finish_task(db,row,review,user);eng.ensure_task(db,row,pay,'按原账户退还集团券包款','finance')
    elif action in {'refund_cancel','refund_reject'}:
        if action=='refund_cancel' and refund.requested_by!=user.id and user.role not in MANAGERS:
            raise HTTPException(403,'仅原申请人或主管可撤销')
        if refund.status=='approved':wallet.reserved_units-=refund.units
        refund.status='cancelled' if action=='refund_cancel' else 'rejected'
        eng.finish_task(db,row,review,user,'cancelled');eng.finish_task(db,row,pay,user,'cancelled')
    elif action=='refund':
        if refund.status!='approved':raise HTTPException(409,'请先完成独立主管复核及占额')
        task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==pay,Task.status=='open'))
        if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(403,'请由当前退款待办财务办理')
        group._evidence(db,row,values['evidence_id'],user)
        amount=refund.units*rule.sale_cents_per_unit
        cash,account=_cash(db,user,row,values,'out',amount,wallet)
        original=db.scalar(select(BenefitEntry).where(BenefitEntry.wallet_id==wallet.id,BenefitEntry.purpose=='purchase'))
        entry=_entry(db,user,wallet,row,'refund',-refund.units,values['evidence_id'],refund.reason,
            original=original,cash=cash,account=account,reference=values['reference'],clearing=-amount)
        wallet.balance_units-=refund.units;wallet.reserved_units-=refund.units
        refund.status='executed';refund.executed_entry_id=entry.id;eng.finish_task(db,row,pay,user)
    return row,refund,entry


def command(db,user,member_id,request_id,version,action,values):
    roles=MANAGERS if action in {'grant','adjust','refund_approve','refund_reject'} else (
        group.REFUND_REQUEST_ROLES|MANAGERS if action in {'refund_request','refund_cancel'} else FINANCE)
    def operation(sid):
        member=group._member(db,member_id,sid,version)
        member.updated_at=utcnow()
        entry=reservation=refund=None
        if action in {'purchase','grant'}:
            rule=_current_rule(db,values['rule_id']);row=_source(db,user,member,values,sid)
            from .membership_service import validate_host
            validate_host(db,user,row,member,action,values)
            if values['units']*max(rule.credit_cents_per_unit,rule.sale_cents_per_unit)>100000000000:
                raise HTTPException(422,'本批权益金额超出允许范围，请按已批准的合理批次发行')
            if rule.issuer_store_id!=sid:raise HTTPException(403,'发行必须由规则的制定门店办理；跨店仅查询和使用已发行权益')
            if action=='purchase' and (rule.kind not in {'coupon','package'} or rule.sale_cents_per_unit<=0):
                raise HTTPException(409,'该版本不是可购买的券或次数套餐')
            if action=='grant' and rule.sale_cents_per_unit:
                raise HTTPException(409,'赠送须使用售价为零的独立规则，不能改变付费批次的优惠承担')
            cash=account=None
            if action=='purchase':cash,account=_cash(db,user,row,values,'in',values['units']*rule.sale_cents_per_unit)
            wallet,entry=_issue(db,user,member,row,rule,values['units'],action,values['evidence_id'],values['reason'],cash,account,values.get('reference'))
            if rule.kind=='points':
                from .membership_points import settle_point_debt
                settle_point_debt(db,user,member,wallet,row,values['evidence_id'])
        else:
            wallet=_wallet(db,member,values['wallet_id']);group._version(wallet,values['wallet_version']);rule=_rule(db,wallet.rule_id)
            from .recharge_bundle_service import guard_component_action
            guard_component_action(db,wallet.id,action)
            if rule.kind=='points' and action in {'reserve','capture','exchange'}:
                from .membership_points import require_points_clear
                require_points_clear(db,member.id)
            if values.get('units',0)*max(rule.credit_cents_per_unit,rule.sale_cents_per_unit)>100000000000:
                raise HTTPException(422,'本次权益金额超出允许范围')
            if action.startswith('refund'):
                row,refund,entry=_refund(db,user,member,wallet,rule,action,values,sid)
            elif action in {'reserve','adjust','exchange'}:
                row=_source(db,user,member,values,sid);_usable(wallet,rule,sid)
                from .membership_service import validate_host
                validate_host(db,user,row,member,action,values)
                units=values['units']
                if units>wallet.balance_units-wallet.reserved_units:raise HTTPException(409,'权益不足或已被消费/退款占用')
                if action=='reserve':
                    from .aftercare_service import guard_source_action
                    guard_source_action(db,user,row,'benefit_reserve')
                    credit=units*rule.credit_cents_per_unit
                    if credit>_due(db,row,True):raise HTTPException(409,'权益抵扣超过客户当前未结且未占用金额，不能抵保险或厂家承担')
                    from .member_pricing_service import guard_benefit_use
                    guard_benefit_use(db,user,row,rule.kind)
                    _package_capacity(db,row,rule,units)
                    reservation=BenefitReservation(wallet_id=wallet.id,case_id=row.id,units=units,credit_cents=credit,evidence_id=values['evidence_id'],actor_id=user.id)
                    db.add(reservation);wallet.reserved_units+=units;db.flush()
                    eng.ensure_task(db,row,'benefit_capture_'+str(reservation.id),'核对并核销或释放集团权益','finance',assignee=user.id)
                elif action=='adjust':
                    if rule.kind!='points':raise HTTPException(409,'只有积分可负向调整；正向调整请明确赠送新批次')
                    wallet.balance_units-=units
                    entry=_entry(db,user,wallet,row,'adjust',-units,values['evidence_id'],values['reason'])
                else:
                    target=_current_rule(db,values['target_rule_id'])
                    if rule.kind!='points' or target.kind not in {'coupon','package'} or target.issuer_store_id!=sid or target.exchange_points_per_unit<=0 or target.sale_cents_per_unit:
                        raise HTTPException(409,'仅用积分兑换本店已配置固定兑换率的券或次数套餐')
                    if units % target.exchange_points_per_unit:
                        raise HTTPException(422,'积分必须是本版本每份兑换积分的整数倍，不会静默舍入')
                    wallet.balance_units-=units
                    outgoing=_entry(db,user,wallet,row,'exchange_out',-units,values['evidence_id'],values['reason'])
                    wallet,entry=_issue(db,user,member,row,target,units//target.exchange_points_per_unit,'exchange',values['evidence_id'],values['reason'],original=outgoing)
            elif action in {'capture','release'}:
                reservation=db.scalar(select(BenefitReservation).where(BenefitReservation.id==values['reservation_id'],BenefitReservation.wallet_id==wallet.id).with_for_update())
                if not reservation:raise HTTPException(404,'本店权益占额不存在')
                group._version(reservation,values['reservation_version'])
                if reservation.status!='reserved':raise HTTPException(409,'占额已结束')
                row=group._case(db,user,member,reservation.case_id,values['case_version'],sid)
                task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key=='benefit_capture_'+str(reservation.id),Task.status=='open'))
                if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(403,'请由权益占额当前待办财务办理，主管可明确转交')
                if action=='capture':
                    from .aftercare_service import guard_source_action
                    guard_source_action(db,user,row,'benefit_capture')
                    _usable(wallet,rule,sid);group._evidence(db,row,values['evidence_id'],user)
                    if reservation.credit_cents>_due(db,row,False):raise HTTPException(409,'本单客户待结金额已减少，请释放占额后核对')
                    _package_capacity(db,row,rule,reservation.units,excluding=reservation.id)
                    wallet.balance_units-=reservation.units;wallet.reserved_units-=reservation.units
                    entry=_entry(db,user,wallet,row,'capture',-reservation.units,values['evidence_id'],values['reason'],
                        credit=reservation.credit_cents,clearing=-reservation.units*rule.settlement_cents_per_unit)
                    db.add(BenefitPaymentLink(case_id=row.id,entry_id=entry.id,reservation_id=reservation.id,amount_cents=reservation.credit_cents))
                    reservation.status='captured'
                else:
                    reservation.status='released';wallet.reserved_units-=reservation.units
                eng.finish_task(db,row,'benefit_capture_'+str(reservation.id),user)
                db.flush()
                if action=='capture':_sync(db,user,row)
            elif action=='reverse':
                original=db.scalar(select(BenefitEntry).where(BenefitEntry.id==values['original_id'],BenefitEntry.wallet_id==wallet.id,
                    BenefitEntry.store_id==sid,BenefitEntry.purpose=='capture'))
                if not original:raise HTTPException(404,'本店原核销记录不存在')
                row=group._case(db,user,member,original.case_id,values['case_version'],sid)
                _due(db,row,False)
                if row.state!='settling':raise HTTPException(409,'客户交车后或已赊账放行的权益更正须另行退修流程')
                from .aftercare_service import guard_source_action
                guard_source_action(db,user,row,'benefit_reverse')
                group._evidence(db,row,values['evidence_id'],user)
                reversed_units=db.scalar(select(func.coalesce(func.sum(BenefitEntry.units),0)).where(BenefitEntry.original_id==original.id,BenefitEntry.purpose=='reverse')) or 0
                if values['units']>-original.units-reversed_units:raise HTTPException(409,'冲正超过原核销尚未撤销份数')
                units=values['units'];wallet.balance_units+=units
                entry=_entry(db,user,wallet,row,'reverse',units,values['evidence_id'],values['reason'],credit=-units*rule.credit_cents_per_unit,
                    original=original,clearing=units*rule.settlement_cents_per_unit)
                if rule.kind=='points':
                    from .membership_points import settle_point_debt
                    settle_point_debt(db,user,member,wallet,row,values['evidence_id'])
                original_link=db.scalar(select(BenefitPaymentLink).where(BenefitPaymentLink.entry_id==original.id))
                db.add(BenefitPaymentLink(case_id=row.id,entry_id=entry.id,reservation_id=original_link.reservation_id,amount_cents=entry.credit_cents))
                db.flush();_sync(db,user,row)
            else:raise HTTPException(404,'权益动作不存在')
        from .membership_service import complete_host
        complete_host(db,user,row,member,action,values)
        from .invoice_service import sync_source
        sync_source(db,user,row)
        wallet.updated_at=utcnow();row.updated_at=utcnow()
        db.add(GroupEvent(store_id=sid,member_id=member.id,actor_id=user.id,action='benefit_'+action,
            detail={'wallet_id':wallet.id,'case_id':row.id,'entry_id':entry.id if entry else None,'reason':values.get('reason','')}))
        eng.log_event(db,user,row,'benefit_'+action,'集团权益办理',detail={'wallet_id':wallet.id,
            'entry_id':entry.id if entry else None,'reason':values.get('reason','')})
        db.flush()
        result={'member':group._wallet(member),'wallet':wallet_info(db,wallet,sid),'case_version':row.version}
        if entry:result['entry_id']=entry.id
        if reservation:result['reservation']={k:getattr(reservation,k) for k in ['id','version','status','case_id','units','credit_cents']}
        if refund:result['refund']={k:getattr(refund,k) for k in ['id','version','status','case_id','units']}
        return result
    return group._execute(db,user,request_id,'benefit:'+str(member_id)+':'+action,{'version':version,'values':values},operation,roles)


def analytics_rows(db,user):
    """Explicit read-only aggregate authority; no shared customer/history expansion."""
    if user.role not in eng.MANAGEMENT:raise HTTPException(403,'权益统计需要经营查询权限')
    ids=tuple(i for i in db.info.get('store_scope',()) if i)
    old=db.info.get('_group_authority');db.info['_group_authority']=('report',ids)
    try:
        entries=list(db.scalars(select(BenefitEntry).where(BenefitEntry.store_id.in_(ids)).order_by(BenefitEntry.id).limit(25001)))
        if len(entries)>25000:raise HTTPException(413,'权益流水超过当前统计上限，不能以截断数据对账')
        rule_by_wallet={};wallet_by_id={}
        for entry in entries:
            if entry.wallet_id not in rule_by_wallet:
                wallet=db.scalar(select(BenefitWallet).where(BenefitWallet.id==entry.wallet_id))
                wallet_by_id[wallet.id]=wallet
                rule_by_wallet[wallet.id]=_rule(db,wallet.rule_id)
        rows=[]
        for e in entries:
            r=rule_by_wallet[e.wallet_id]
            signed_units=-e.units if e.purpose in {'capture','reverse'} else 0
            recognized=signed_units*r.sale_cents_per_unit if wallet_by_id[e.wallet_id].source_kind=='purchase' else 0
            internal=signed_units*r.settlement_cents_per_unit
            rows.append({'id':e.id,'store_id':e.store_id,'case_id':e.case_id,'kind':r.kind,'rule_name':r.name,
                'rule_version':r.rule_version,'purpose':e.purpose,'units':e.units,'credit_cents':e.credit_cents,
                'cash_id':e.cash_id,'discount_bearer':r.discount_bearer,
                'discount_cents':e.credit_cents-recognized,'external_discount_cents':e.credit_cents-recognized,
                'recognized_cents':recognized,'group_discount_cents':internal-recognized,
                'service_discount_cents':e.credit_cents-internal,
                'occurred_at':e.occurred_at.isoformat()})
        settlements=list(db.scalars(select(BenefitSettlement).order_by(BenefitSettlement.id).limit(50001)))
        if len(settlements)>50000:raise HTTPException(413,'权益往来超过当前统计上限')
        return {'entries':rows,'settlements':[{k:getattr(e,k) for k in ['entry_id','store_id','side','amount_cents']} for e in settlements]}
    finally:
        if old is None:db.info.pop('_group_authority',None)
        else:db.info['_group_authority']=old
