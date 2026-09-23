"""Explicit member service orders. All effects share the caller's transaction."""
from calendar import monthrange
from datetime import date,timedelta
import uuid
from fastapi import HTTPException
from sqlalchemy import select,func
from .db import today,utcnow
from .models import Store
from .flow_models import Case,Customer,Task
from .group_models import GroupMember,GroupReceipt
from .group_benefits_models import BenefitRule
from .membership_models import (MembershipRule,MembershipOrder,MembershipCard,MembershipPeriod,
    MembershipPeriodVoid,MembershipFee,MembershipEvent)
from . import group_service as group,flow_engine as eng

FRONT={'admin','manager','finance','sales','service','reception','customer_service'}
READ=FRONT|{'auditor'}
LABELS={'topup':'集团本金充值','benefit_issue':'集团权益发行','card_issue':'发行会员卡','card_loss':'会员卡挂失',
    'card_replace':'会员卡换补','renew':'会员续会','tier_change':'会员等级调整','renew_refund':'未生效续会退款','points_adjust':'积分办理'}

def clean(row):return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),date) else getattr(row,c.name)) for c in row.__table__.columns}
def can_read(user,row):return user.role in READ and (user.role not in {'sales','reception'} or row.owner_id==user.id)
def _order(db,user,key):
    row=eng.get_case(db,user,key)
    if row.kind!='membership' or row.flow_version!=2:raise HTTPException(404,'本店会员业务单不存在')
    order=db.scalar(select(MembershipOrder).where(MembershipOrder.case_id==row.id).with_for_update())
    if not order:raise HTTPException(404,'会员业务来源不存在')
    return row,order
def _rule(db,key):
    rule=db.scalar(select(MembershipRule).where(MembershipRule.id==key))
    if not rule:raise HTTPException(404,'会员规则版本不存在')
    return rule
def _new_rule(db,key,sid):
    rule=_rule(db,key)
    latest=db.scalar(select(func.max(MembershipRule.rule_version)).where(MembershipRule.code==rule.code))
    if not rule.enabled or sid not in rule.allowed_store_ids or rule.rule_version!=latest:
        raise HTTPException(409,'请选择当前已启用且适用本店的会员规则；旧业务按原版本办理')
    return rule
def periods(db,member):
    voided=select(MembershipPeriodVoid.period_id)
    return list(db.scalars(select(MembershipPeriod).where(MembershipPeriod.member_id==member.id,
        ~MembershipPeriod.id.in_(voided)).order_by(MembershipPeriod.starts_on,MembershipPeriod.id)))
def current_period(db,member):
    rows=[p for p in periods(db,member) if p.starts_on<=today()<=p.ends_on]
    return rows[-1] if rows else None
def _end(start,months):
    ordinal=start.year*12+start.month-1+months;year,month=divmod(ordinal,12);month+=1
    return date(year,month,min(start.day,monthrange(year,month)[1]))-timedelta(days=1)
def _event(db,user,row,order,action,values,detail=None):
    db.add(MembershipEvent(case_id=row.id,member_id=order.member_id,actor_id=user.id,action=action,
        reason=values.get('reason',''),evidence_id=values.get('evidence_id'),detail=detail or {}))
    eng.log_event(db,user,row,'membership_'+action,LABELS[order.purpose],detail={'recorded':True} if action=='fee_refund_basis' else detail or {})
def _done(db,user,row,order):
    eng.finish_task(db,row,'membership_execute',user)
    order.status='completed';row.state='completed';row.completed_date=today();eng.close_tasks(db,row,user)
def _assigned(db,user,row,key):
    task=db.scalar(select(Task).where(Task.case_id==row.id,Task.key==key,Task.status=='open'))
    if not task or (task.assignee_id!=user.id and user.role!='admin'):
        raise HTTPException(403,'请由当前待办接手人办理，主管可明确转交')
def _proof(db,user,row,key):return group._evidence(db,row,key,user)


def rules(db,user):
    with group.authority(db,user,READ) as sid:
        rows=list(db.scalars(select(MembershipRule).order_by(MembershipRule.id.desc()).limit(500)))
        return {'items':[clean(r) for r in rows if sid in r.allowed_store_ids]}
def create_rule(db,user,request_id,values):
    def operation(sid):
        ids=values['allowed_store_ids']
        actual=set(db.scalars(select(Store.id).where(Store.id.in_(ids),Store.active.is_(True))))
        if len(ids)!=len(set(ids)) or actual!=set(ids) or sid not in ids:raise HTTPException(422,'适用门店须启用、互不重复并含当前配置门店')
        if values.get('points_benefit_rule_id'):
            rule=db.scalar(select(BenefitRule).where(BenefitRule.id==values['points_benefit_rule_id'],BenefitRule.kind=='points'))
            if not rule or not set(ids)<=set(rule.allowed_store_ids):raise HTTPException(422,'消费积分须关联覆盖适用门店的冻结积分权益规则')
        if values['points_enabled'] and not values.get('points_benefit_rule_id'):raise HTTPException(422,'启用消费积分前必须配置独立积分权益规则')
        if 100000000000*values['points_numerator']//values['points_denominator_fen']>9007199254740991:
            raise HTTPException(422,'积分比例超出整数精度支持范围，请降低配置比例')
        revision=(db.scalar(select(func.max(MembershipRule.rule_version)).where(MembershipRule.code==values['code'])) or 0)+1
        rule=MembershipRule(rule_version=revision,created_by=user.id,**values);db.add(rule);db.flush();return clean(rule)
    return group._execute(db,user,request_id,'membership_rule',values,operation,{'admin'})


def member_detail(db,user,customer_id):
    local=group.member_for_customer(db,user,customer_id)
    if not local['member']:return {**local,'cards':[],'periods':[],'points_debt_units':0}
    with group.authority(db,user,READ) as sid:
        member=group._member(db,local['member']['id'],sid)
        cards=list(db.scalars(select(MembershipCard).where(MembershipCard.member_id==member.id).order_by(MembershipCard.generation.desc())))
        ps=periods(db,member);active=current_period(db,member)
        from .membership_points import outstanding_debt
        return {**local,'cards':[{'id':r.id,'number':r.number,'generation':r.generation,'status':r.status,'version':r.version} for r in cards],
            'periods':[{'id':p.id,'rule':clean(_rule(db,p.rule_id)),'starts_on':str(p.starts_on),'ends_on':str(p.ends_on),
                'kind':p.kind,**({'case_id':p.case_id} if p.store_id==sid else {})} for p in ps],
            'active_period_id':active.id if active else None,'points_debt_units':outstanding_debt(db,member.id)}
def lookup_card(db,user,number):
    with group.authority(db,user,READ) as sid:
        card=db.scalar(select(MembershipCard).where(MembershipCard.number==number,MembershipCard.status=='active'))
        if not card:raise HTTPException(404,'有效会员卡不存在，请核对客户；旧卡与挂失卡不能识别')
        member=group._member(db,card.member_id,sid)
        from .group_models import GroupIdentityLink
        link=db.scalar(select(GroupIdentityLink).where(GroupIdentityLink.identity_id==member.identity_id,GroupIdentityLink.local_kind=='customer',GroupIdentityLink.store_id==sid))
        # This lookup remains subject to local customer ownership. A card is not financial authority.
        return member_detail(db,user,link.local_id)


def create_order(db,user,request_id,customer_id,purpose,values,reason):
    def operation(sid):
        local=group.member_for_customer(db,user,customer_id)
        if not local['member']:raise HTTPException(409,'请先明确关联本店客户并开通集团会员')
        member=group._member(db,local['member']['id'],sid);amount=0
        if purpose in {'renew','tier_change'}:
            rule=_new_rule(db,values['rule_id'],sid)
            if purpose=='renew':amount=rule.fee_cents
        elif purpose in {'card_loss','card_replace'}:
            card=db.scalar(select(MembershipCard).where(MembershipCard.id==values['card_id'],MembershipCard.member_id==member.id))
            if not card or card.status=='replaced':raise HTTPException(409,'请选择本会员仍有效或已挂失的原卡')
        elif purpose=='renew_refund':
            period,fee=_refundable(db,member,values['period_id'],sid);amount=-fee.amount_cents
        elif purpose=='topup':amount=values['amount_cents']
        elif purpose=='benefit_issue':
            from .group_benefits_service import _current_rule
            rule=_current_rule(db,values['rule_id'])
            if sid not in rule.allowed_store_ids:raise HTTPException(409,'权益不适用于本店')
            amount=values['units']*rule.sale_cents_per_unit if values['action']=='purchase' else 0
            if amount>100000000000:raise HTTPException(422,'本次权益金额超出允许范围')
        customer=group._local(db,Customer,customer_id,sid)
        row=Case(kind='membership',flow_version=2,number='HK-MB-'+uuid.uuid4().hex[:16].upper(),title=LABELS[purpose]+' · '+customer.name,
            state='pending',created_by=user.id,owner_id=user.id,customer_id=customer.id,business_date=today(),due_date=today()+timedelta(days=2),amount_cents=max(0,amount),data={})
        db.add(row);db.flush()
        order=MembershipOrder(case_id=row.id,member_id=member.id,purpose=purpose,values=values,requested_by=user.id)
        db.add(order);db.flush()
        from .business_entity_service import freeze_case_entity,freeze_derived_case_entity
        if purpose=='renew_refund':freeze_derived_case_entity(db,user,row,eng.get_case(db,user,fee.case_id))
        else:freeze_case_entity(db,user,row)
        eng.set_data(row,membership_id=order.id)
        review=purpose in {'renew','tier_change','renew_refund'}
        role='manager' if review or values.get('action') in {'grant','adjust'} else 'finance' if purpose in {'topup','benefit_issue','points_adjust'} else user.role
        eng.ensure_task(db,row,'membership_review' if review else 'membership_execute',LABELS[purpose],role,
            assignee=user.id if role==user.role else None)
        member.updated_at=utcnow();_event(db,user,row,order,'create',{'reason':reason});db.flush()
        return describe(db,user,row.id)
    return group._execute(db,user,request_id,'membership_create',dict(customer_id=customer_id,purpose=purpose,values=values,reason=reason),operation,FRONT)


def describe(db,user,key):
    with group.authority(db,user,READ):
        row,order=_order(db,user,key)
        events=list(db.scalars(select(MembershipEvent).where(MembershipEvent.case_id==row.id).order_by(MembershipEvent.id)))
        def visible_event(event):
            value=clean(event)
            if event.action=='fee_refund_basis' and user.role not in {'admin','manager','finance','auditor'}:
                value.update(detail={'recorded':True},evidence_id=None,reason='已按原续会费来源登记实际退款')
            return value
        return {'case':{'id':row.id,'number':row.number,'title':row.title,'version':row.version,'state':row.state,'customer_id':row.customer_id,
            'amount_cents':row.amount_cents},'order':clean(order),'member':group._wallet(group._member(db,order.member_id,row.store_id)),
            'events':[visible_event(e) for e in events]}
def orders(db,user):
    with group.authority(db,user,READ):
        rows=list(db.scalars(select(Case).where(Case.kind=='membership').order_by(Case.id.desc()).limit(200)))
        return {'items':[{'id':r.id,'number':r.number,'title':r.title,'state':r.state,'customer_id':r.customer_id} for r in rows if can_read(user,r)]}
def _refundable(db,member,period_id,sid):
    period=db.scalar(select(MembershipPeriod).where(MembershipPeriod.id==period_id,MembershipPeriod.member_id==member.id,MembershipPeriod.store_id==sid))
    if not period:raise HTTPException(404,'本店原续会记录不存在')
    rule=_rule(db,period.rule_id)
    if period.kind!='renew' or rule.refund_policy!='before_start' or period.starts_on<=today():raise HTTPException(409,'原规则只允许尚未生效的收费续会整笔退款')
    if db.scalar(select(MembershipPeriodVoid.id).where(MembershipPeriodVoid.period_id==period.id)):raise HTTPException(409,'原续会已退款撤销')
    if any(p.starts_on>period.starts_on for p in periods(db,member)):raise HTTPException(409,'请先处理后续续会版本，不能造成期间断档')
    fee=db.scalar(select(MembershipFee).where(MembershipFee.period_id==period.id,MembershipFee.amount_cents>0))
    if not fee:raise HTTPException(409,'原续会无可退实际收费')
    from .membership_fee_corrections import guard_refund
    guard_refund(db,fee)
    return period,fee


def validate_host(db,user,row,member,action,values):
    if row.kind!='membership':return
    order=db.scalar(select(MembershipOrder).where(MembershipOrder.case_id==row.id).with_for_update())
    if not order or order.member_id!=member.id or order.status!='draft':raise HTTPException(409,'会员业务单已结束或不属于当前会员')
    expected='topup' if order.purpose=='topup' else order.values.get('action')
    if action!=expected or order.purpose not in {'topup','benefit_issue','points_adjust'}:raise HTTPException(409,'此业务宿主不能办理该资金或权益动作')
    for key,value in order.values.items():
        if key!='action' and values.get(key)!=value:raise HTTPException(409,'办理金额、规则或积分来源与会员业务单不一致')
    _assigned(db,user,row,'membership_execute')
def complete_host(db,user,row,member,action,values):
    if row.kind!='membership' or action not in {'topup','grant','purchase','adjust','exchange'}:return
    order=db.scalar(select(MembershipOrder).where(MembershipOrder.case_id==row.id))
    _done(db,user,row,order);_event(db,user,row,order,action,values)


def command(db,user,key,request_id,version,case_version,member_version,action,values):
    with group.authority(db,user,READ):
        row,order=_order(db,user,key)
        if action=='execute' and order.purpose in {'topup','benefit_issue','points_adjust'} and order.values.get('action')!='settle_debt':
            prior=db.scalar(select(GroupReceipt).where(GroupReceipt.request_key==request_id))
            if not prior:group._version(order,version);group._version(row,case_version)
            payload={k:v for k,v in order.values.items() if k!='action'}|values|{'case_id':row.id,'case_version':case_version}
            target='topup' if order.purpose=='topup' else order.values['action']
            if target=='topup':result=group.member_command(db,user,order.member_id,request_id,member_version,target,payload)
            else:
                from .group_benefits_service import command as benefit_command
                result=benefit_command(db,user,order.member_id,request_id,member_version,target,payload)
            return {'result':result,**describe(db,user,key)}
    roles={'admin','manager'} if action in {'approve','reject'} else FRONT
    def operation(sid):
        row,order=_order(db,user,key);group._version(row,case_version);group._version(order,version)
        member=group._member(db,order.member_id,sid,member_version);row.updated_at=utcnow();member.updated_at=utcnow()
        if order.status in {'completed','cancelled'}:raise HTTPException(409,'会员办理已结束')
        if action in {'cancel','reject'}:
            if action=='cancel' and user.id!=order.requested_by and user.role not in {'admin','manager'}:raise HTTPException(403,'仅申请人或主管可撤销')
            order.status='cancelled';row.state='cancelled';row.completed_date=today();eng.close_tasks(db,row,user)
        elif action=='approve':
            if order.purpose not in {'renew','tier_change','renew_refund'} or order.status!='draft':raise HTTPException(409,'当前业务不等待复核')
            if user.id==order.requested_by:raise HTTPException(403,'申请与批准须由不同人员办理，管理员也不能自批')
            _assigned(db,user,row,'membership_review');_proof(db,user,row,values['evidence_id'])
            if order.purpose=='renew_refund':_refundable(db,member,order.values['period_id'],sid)
            order.status='approved';order.approved_by=user.id;eng.finish_task(db,row,'membership_review',user)
            eng.ensure_task(db,row,'membership_execute','按已批准规则办理'+LABELS[order.purpose],
                'finance' if order.purpose in {'renew','renew_refund'} else 'service')
        elif action=='execute':
            _proof(db,user,row,values['evidence_id']);_assigned(db,user,row,'membership_execute')
            if order.purpose.startswith('card_'):
                card=None
                if order.purpose!='card_issue':
                    card=db.scalar(select(MembershipCard).where(MembershipCard.id==order.values['card_id'],MembershipCard.member_id==member.id).with_for_update())
                    if not card or card.status=='replaced':raise HTTPException(409,'原卡已被换补或不存在')
                if order.purpose=='card_loss':
                    if card.status!='active':raise HTTPException(409,'原卡已经挂失')
                    card.status='lost'
                else:
                    if order.purpose=='card_issue' and db.scalar(select(MembershipCard.id).where(MembershipCard.member_id==member.id)):
                        raise HTTPException(409,'已有卡历史，请从原卡办理换补，不能重新开户覆盖')
                    generation=(db.scalar(select(func.max(MembershipCard.generation)).where(MembershipCard.member_id==member.id)) or 0)+1
                    if card:card.status='replaced';db.flush()
                    db.add(MembershipCard(member_id=member.id,number='HKC'+uuid.uuid4().hex.upper(),generation=generation,
                        previous_id=card.id if card else None,case_id=row.id,issuer_store_id=sid))
                _done(db,user,row,order)
            elif order.purpose in {'renew','tier_change'}:
                if order.status!='approved':raise HTTPException(409,'会员续会或等级调整须先独立复核')
                rule=_rule(db,order.values['rule_id']);existing=periods(db,member);active=current_period(db,member)
                start=max([today()]+[p.ends_on+timedelta(days=1) for p in existing]) if order.purpose=='renew' else today()
                end=active.ends_on if order.purpose=='tier_change' and active else _end(start,rule.validity_months)
                period=MembershipPeriod(member_id=member.id,rule_id=rule.id,case_id=row.id,store_id=sid,starts_on=start,ends_on=end,kind=order.purpose)
                db.add(period);db.flush()
                if order.purpose=='renew' and rule.fee_cents:
                    if user.role not in {'admin','finance'}:raise HTTPException(403,'收费续会须由财务确认实际到账')
                    _fee(db,user,row,period,values,rule.fee_cents)
                _done(db,user,row,order)
            elif order.purpose=='renew_refund':
                if order.status!='approved' or user.role not in {'admin','finance'}:raise HTTPException(403,'续会退款须独立批准后由财务办理')
                period,original=_refundable(db,member,order.values['period_id'],sid)
                _fee(db,user,row,period,values,-original.amount_cents,original)
                db.add(MembershipPeriodVoid(period_id=period.id,case_id=row.id,store_id=sid));_done(db,user,row,order)
            elif order.purpose=='points_adjust' and order.values['action']=='settle_debt':
                if user.role not in {'admin','finance'}:raise HTTPException(403,'请交财务核对现有积分抵扣原债务')
                from .group_benefits_service import _wallet,_rule as benefit_rule,_usable
                from .membership_points import outstanding_debt,settle_point_debt
                wallet=_wallet(db,member,order.values['wallet_id']);group._version(wallet,values.get('wallet_version'))
                _usable(wallet,benefit_rule(db,wallet.rule_id),sid)
                units=order.values['units']
                if units>wallet.balance_units-wallet.reserved_units or units>outstanding_debt(db,member.id):raise HTTPException(409,'超过现有可用积分或原消费待追回额度')
                used=settle_point_debt(db,user,member,wallet,row,values['evidence_id'],maximum_units=units)
                if used!=units:raise HTTPException(409,'请选择同会员有效的独立积分钱包')
                _done(db,user,row,order)
            else:raise HTTPException(409,'请使用对应财务或权益动作')
        else:raise HTTPException(404,'会员动作不存在')
        _event(db,user,row,order,action,values);db.flush();return describe(db,user,key)
    return group._execute(db,user,request_id,'membership:'+str(key)+':'+action,
        dict(version=version,case_version=case_version,member_version=member_version,values=values),operation,roles)


def _fee(db,user,row,period,values,amount,original=None):
    if not values.get('account_id') or not values.get('reference'):raise HTTPException(422,'收费或退款须填写实际账户和凭证号')
    if original:
        from .membership_fee_corrections import effective_fee
        original=effective_fee(db,original)
        if values['account_id']!=original.account_id:raise HTTPException(409,'续会费退款须退回当前有效原账户，请核对已完成的登记更正')
    cash,account=group._cash(db,user,row,{**values,'amount_cents':abs(amount)},'in' if amount>0 else 'out',original)
    cash.category='group_member_fee' if amount>0 else 'group_member_fee_refund';cash.note='集团会员续会费用；收款门店经营主体 '+row.number
    fee=MembershipFee(case_id=row.id,period_id=period.id,cash_id=cash.id,account_id=account.id,reference=values['reference'],
        original_id=original.id if original else None,amount_cents=amount,evidence_id=values['evidence_id'],actor_id=user.id)
    db.add(fee);db.flush()
    if original:
        from .membership_fee_corrections import record_refund_basis
        record_refund_basis(db,fee,original)
        order=db.scalar(select(MembershipOrder).where(MembershipOrder.case_id==row.id))
        _event(db,user,row,order,'fee_refund_basis',values,{'refund_fee_id':fee.id,'original_fee_id':original.id,'original_cash_id':original.cash_id})


def analytics_rows(db,user):
    if user.role not in eng.MANAGEMENT:raise HTTPException(403,'会员统计需要经营查询权限')
    def bounded(stmt):
        result=list(db.scalars(stmt.limit(25001)))
        if len(result)>25000:raise HTTPException(422,'会员统计超过 25000 条，请缩小门店范围后查询')
        return result
    rows=bounded(select(MembershipFee))
    from .membership_models import PointsChange,PointsDebt,PointsDebtPayment
    ids=tuple(db.info.get('store_scope',()));old=db.info.get('_group_authority');db.info['_group_authority']=('report',ids)
    try:
        changes=bounded(select(PointsChange).where(PointsChange.store_id.in_(ids)))
        change_by_id={r.id:r for r in changes}
        debts=bounded(select(PointsDebt).join(PointsChange,PointsChange.id==PointsDebt.change_id).where(PointsChange.store_id.in_(ids)))
        paid=dict(db.execute(select(PointsDebtPayment.debt_id,func.sum(PointsDebtPayment.units))
            .join(PointsDebt,PointsDebt.id==PointsDebtPayment.debt_id)
            .join(PointsChange,PointsChange.id==PointsDebt.change_id)
            .where(PointsChange.store_id.in_(ids)).group_by(PointsDebtPayment.debt_id)).all())
        from .membership_fee_corrections import effective_fee
        def fee_row(r):
            value=clean(r)
            if r.amount_cents>0:
                current=effective_fee(db,r)
                value.update(effective_cash_id=current.cash_id,effective_account_id=current.account_id,effective_reference=current.reference)
            return value
        return {'fees':[fee_row(r) for r in rows],'point_changes':[clean(r) for r in changes],
            'point_debts':[{'id':d.id,'case_id':change_by_id[d.change_id].case_id,'units':d.units,
                'outstanding_units':d.units-paid.get(d.id,0)} for d in debts]}
    finally:
        if old is None:db.info.pop('_group_authority',None)
        else:db.info['_group_authority']=old


from .membership_points import freeze_points_rule,sync_consumption_points
