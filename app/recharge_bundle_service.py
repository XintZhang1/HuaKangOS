"""One cash receipt funds group principal; gifts retain separate, frozen units."""
import uuid
from datetime import date, timedelta
from sqlalchemy import select, func
from fastapi import HTTPException
from .db import utcnow, today
from .models import Store, CashEntry
from .flow_models import Case, Customer, Task, Account
from .group_models import GroupEntry, GroupEvent
from .group_benefits_models import BenefitRule, BenefitWallet, BenefitEntry
from .recharge_bundle_models import (RechargeBundleRule as Rule, RechargeBundleRuleComponent as RuleComponent,
    RechargeBundleOrder as Order, RechargeBundlePurchase as Purchase, RechargeBundleComponent as Component,
    RechargeBundleRefund as Refund, RechargeBundleRefundComponent as RefundComponent, RechargeBundleRefundPosting as Posting)
from . import group_service as group, group_benefits_service as benefits, flow_engine as eng

READ = group.READ_ROLES
FRONT = {'admin', 'manager', 'finance', 'service', 'customer_service', 'sales', 'reception'}
TERMS = '实收全部记入集团通用本金；赠品单独记账。退款只退原组合仍可完整回收的整份：必须有足够集团可用本金，并回收该购买批次每项赠品。赠品已使用后不能拆单份退款，也不能用其他批次赠品补足。本金按集团钱包通用门店授权使用；适用门店仅限制组合发行和赠品使用。'
POINT_DEBT_TERMS = '组合赠送积分须先抵扣该会员已有的原消费退款待追回积分，抵扣属于本批次已使用积分，会减少可退完整份额。'
UNITS = {'bonus': '分赠送金额', 'points': '积分', 'coupon': '张券', 'package': '次服务'}


def clean(row):
    return {c.name: (getattr(row, c.name).isoformat() if isinstance(getattr(row, c.name), date) else getattr(row, c.name)) for c in row.__table__.columns}


def can_read(user, row):
    return user.role in READ and (user.role not in {'sales', 'reception'} or row.owner_id == user.id)


def _order(db, user, key):
    row = db.scalar(select(Case).where(Case.id == key, Case.kind == 'recharge_bundle').with_for_update())
    if not row: raise HTTPException(404, '当前门店的充值组合办理单不存在')
    if not can_read(user, row): raise HTTPException(403, '当前岗位不能查看此组合业务')
    if row.flow_version != 2: raise HTTPException(409, '充值组合流程版本不支持，请联系管理员')
    order = db.scalar(select(Order).where(Order.case_id == row.id).with_for_update())
    if not order: raise HTTPException(409, '充值组合业务来源不完整')
    return row, order


def _rule(db, key):
    rule = db.scalar(select(Rule).where(Rule.id == key))
    if not rule: raise HTTPException(404, '充值组合规则不存在')
    return rule


def _rule_components(db, rule):
    return list(db.execute(select(RuleComponent, BenefitRule).join(BenefitRule, BenefitRule.id == RuleComponent.benefit_rule_id)
        .where(RuleComponent.bundle_rule_id == rule.id).order_by(RuleComponent.id)))


def _sale_rule(db, key, sid):
    rule = _rule(db, key)
    latest = db.scalar(select(func.max(Rule.rule_version)).where(Rule.issuer_store_id == rule.issuer_store_id, Rule.code == rule.code))
    if rule.rule_version != latest or not rule.enabled or sid not in rule.allowed_store_ids:
        raise HTTPException(409, '只能选用当前启用且适用于本店的最新充值组合版本')
    if not rule.sale_starts_on <= today() <= rule.sale_ends_on:
        raise HTTPException(409, '当前日期不在该组合的发行期间内')
    return rule


def rule_info(db, rule, financial=True):
    return {**clean(rule), 'mandatory_terms': TERMS, 'principal_scope': 'group_common',
        'components': [{'id': c.id, 'units_per_share': c.units_per_share, 'unit_label': UNITS[b.kind],
                        'benefit_rule': benefits.rule_info(b, financial)} for c, b in _rule_components(db, rule)]}


def rules(db, user):
    with group.authority(db, user, READ) as sid:
        rows = list(db.scalars(select(Rule).order_by(Rule.id.desc()).limit(1000)))
        if len(rows) == 1000: raise HTTPException(409, '充值组合规则过多，请按门店分批整理后查询')
        return {'items': [rule_info(db, r, user.role in {'admin','manager','finance','auditor'}) for r in rows if sid in r.allowed_store_ids], 'mandatory_terms': TERMS}


def create_rule(db, user, request_id, values):
    def operation(sid):
        ids = values['allowed_store_ids']
        actual = set(db.scalars(select(Store.id).where(Store.id.in_(ids), Store.active.is_(True))))
        if len(ids) != len(set(ids)) or set(ids) != actual or sid not in ids:
            raise HTTPException(422, '适用门店须启用、互不重复并包含当前配置门店')
        if date.fromisoformat(values['sale_starts_on']) > date.fromisoformat(values['sale_ends_on']):
            raise HTTPException(422, '发行结束日期不能早于开始日期')
        kinds, components = set(), []
        for value in values['components']:
            rule = benefits._current_rule(db, value['benefit_rule_id'])
            if rule.kind in kinds: raise HTTPException(422, '每个组合版本每类赠品只配置一个明确批次规则')
            if rule.sale_cents_per_unit or rule.refund_policy != 'none' or set(rule.allowed_store_ids) != set(ids):
                raise HTTPException(422, '赠品必须选择售价为零、不单独现金退款且适用门店完全一致的冻结权益规则')
            if value['units_per_share'] * rule.credit_cents_per_unit > 100000000000:
                raise HTTPException(422, '单份赠品价值超出允许范围')
            kinds.add(rule.kind); components.append(value)
        revision = (db.scalar(select(func.max(Rule.rule_version)).where(Rule.issuer_store_id == sid, Rule.code == values['code'])) or 0) + 1
        fields = {k: v for k, v in values.items() if k != 'components'}
        if 'points' in kinds and POINT_DEBT_TERMS not in fields['refund_terms']:
            fields['refund_terms'] += '\n'+POINT_DEBT_TERMS
        if len(fields['refund_terms'])>1000: raise HTTPException(422,'退款补充条款过长，请为积分优先抵原欠额说明保留空间')
        fields.update(sale_starts_on=date.fromisoformat(values['sale_starts_on']), sale_ends_on=date.fromisoformat(values['sale_ends_on']))
        rule = Rule(issuer_store_id=sid, rule_version=revision, created_by=user.id, **fields)
        db.add(rule); db.flush()
        db.add_all([RuleComponent(bundle_rule_id=rule.id, **value) for value in components]); db.flush()
        return rule_info(db, rule)
    return group._execute(db, user, request_id, 'recharge_bundle_rule', values, operation, {'admin'})


def _purchase(db, key, member, sid):
    row = db.scalar(select(Purchase).where(Purchase.id == key, Purchase.member_id == member.id, Purchase.store_id == sid))
    if not row: raise HTTPException(404, '当前门店的原组合购买记录不存在')
    return row


def _components(db, purchase, lock=False):
    result = []
    parts = list(db.scalars(select(Component).where(Component.purchase_id == purchase.id).order_by(Component.wallet_id)))
    for part in parts:
        stmt = select(BenefitWallet).where(BenefitWallet.id == part.wallet_id, BenefitWallet.member_id == purchase.member_id)
        wallet = db.scalar(stmt.with_for_update() if lock else stmt)
        component = db.scalar(select(RuleComponent).where(RuleComponent.id == part.rule_component_id, RuleComponent.bundle_rule_id == purchase.rule_id))
        if not wallet or not component or wallet.rule_id != component.benefit_rule_id:
            raise HTTPException(409, '组合赠品来源不完整，请停止办理并核对账本')
        result.append((part, component, wallet, benefits._rule(db, wallet.rule_id)))
    if len(result) != len(_rule_components(db, _rule(db, purchase.rule_id))):
        raise HTTPException(409, '原组合赠品数量不完整，请核对账本')
    return result


def _availability(db, member, purchase, components=None):
    rule = _rule(db, purchase.rule_id)
    refunds = list(db.scalars(select(Refund).where(Refund.purchase_id == purchase.id, Refund.status.in_(['reserved','applied']))))
    from .business_finance_bundle_corrections import effective_shares
    effective=effective_shares(db,purchase)
    remaining = effective - sum(r.shares for r in refunds)
    available = min(remaining, (member.balance_cents - member.reserved_cents) // rule.principal_cents_per_share)
    parts = []
    for part, component, wallet, benefit in components if components is not None else _components(db, purchase):
        available = min(available, (wallet.balance_units - wallet.reserved_units) // component.units_per_share)
        if rule.refund_policy == 'whole_unused_before_expiry' and today() > wallet.expires_on: available = 0
        parts.append({'component_id': part.id, 'wallet_id': wallet.id, 'wallet_version': wallet.version,
            'kind': benefit.kind, 'name': benefit.name, 'unit_label': UNITS[benefit.kind], 'units_per_share': component.units_per_share,
            'balance_units': wallet.balance_units, 'reserved_units': wallet.reserved_units, 'expires_on': str(wallet.expires_on)})
    return {'refundable_shares': max(0, available), 'remaining_original_shares': remaining, 'effective_shares':effective,
            'corrected_share_delta':effective-purchase.shares,'components': parts,
            'reserved_refund_shares': sum(r.shares for r in refunds if r.status == 'reserved'),
            'refunded_shares': sum(r.shares for r in refunds if r.status == 'applied')}


def purchase_info(db, member, purchase, financial=True):
    rule = _rule(db, purchase.rule_id)
    original = db.scalar(select(GroupEntry).where(GroupEntry.id == purchase.principal_entry_id))
    from .business_finance_stored import effective_group_topup
    effective=effective_group_topup(db,original)
    account = db.scalar(select(Account).where(Account.id == original.account_id))
    effective_account=db.scalar(select(Account).where(Account.id==effective.account_id))
    return {**clean(purchase), 'rule': rule_info(db, rule, financial), **_availability(db, member, purchase),
            'effective_principal_cents':effective.amount_cents,
            **({'original_account': {'id': account.id, 'name': account.name}, 'original_reference': original.reference,
                'effective_account':{'id':effective_account.id,'name':effective_account.name} if effective.cash_id else None,
                'effective_reference':effective.reference} if financial else {})}


def purchases(db, user, customer_id):
    local = group.member_for_customer(db, user, customer_id)
    if not local['member']: return {**local, 'items': []}
    with group.authority(db, user, READ) as sid:
        member = group._member(db, local['member']['id'], sid)
        rows = list(db.scalars(select(Purchase).where(Purchase.member_id == member.id).order_by(Purchase.id.desc()).limit(300)))
        if len(rows) == 300: raise HTTPException(409, '本会员组合购买记录较多，请联系管理员分期核对')
        return {**local, 'items': [purchase_info(db, member, p, user.role in {'admin','manager','finance','auditor'}) for p in rows]}


def _assigned(db, user, row, key):
    task = db.scalar(select(Task).where(Task.case_id == row.id, Task.key == key, Task.status == 'open'))
    if not task or (user.role != 'admin' and task.assignee_id != user.id):
        raise HTTPException(403, '请由当前待办接手人办理；主管可明确转交')


def _event(db, user, row, order, action, reason, detail=None):
    detail = {'bundle_order_id': order.id, 'purpose': order.purpose, 'reason': reason, **(detail or {})}
    db.add(GroupEvent(store_id=row.store_id, member_id=order.member_id, actor_id=user.id, action='bundle_'+action, detail=detail))
    eng.log_event(db, user, row, 'bundle_'+action, '会员充值组合办理', detail=detail)


def create_order(db, user, request_id, customer_id, purpose, values, reason):
    def operation(sid):
        local = group.member_for_customer(db, user, customer_id)
        if not local['member']: raise HTTPException(409, '请先确认本店客户关联并开通集团会员')
        member = group._member(db, local['member']['id'], sid)
        if purpose == 'purchase':
            rule = _sale_rule(db, values['rule_id'], sid)
            for component, benefit in _rule_components(db, rule):
                if values['shares'] * component.units_per_share * benefit.credit_cents_per_unit > 100000000000:
                    raise HTTPException(422, '本次赠品总价值过大，请核对购买份数')
        else:
            purchase = _purchase(db, values['purchase_id'], member, sid); rule = _rule(db, purchase.rule_id)
            if values['shares'] > _availability(db, member, purchase)['refundable_shares']:
                raise HTTPException(409, '可退整份不足：请核对可用本金、该购买批次每项赠品及冻结的退款期限')
        amount = values['shares'] * rule.principal_cents_per_share
        if amount > 100000000000: raise HTTPException(422, '本次组合金额超出允许范围')
        customer = group._local(db, Customer, customer_id, sid)
        row = Case(kind='recharge_bundle', flow_version=2, number='HK-RB-'+uuid.uuid4().hex[:16].upper(),
            title=('充值组合购买' if purpose == 'purchase' else '充值组合原路退款')+' · '+customer.name,
            state='pending', created_by=user.id, owner_id=user.id, customer_id=customer.id, business_date=today(),
            due_date=today()+timedelta(days=2), amount_cents=amount, data={})
        db.add(row); db.flush();from .business_entity_service import freeze_case_entity;freeze_case_entity(db,user,row)
        order = Order(case_id=row.id, member_id=member.id, purpose=purpose, values=values, requested_by=user.id)
        db.add(order); db.flush()
        if purpose == 'refund':
            refund = Refund(case_id=row.id, purchase_id=purchase.id, member_id=member.id, shares=values['shares'], amount_cents=amount)
            db.add(refund); db.flush()
            db.add_all([RefundComponent(refund_id=refund.id, component_id=p.id, units=c.units_per_share*refund.shares)
                        for p, c, _w, _b in _components(db, purchase)])
        eng.set_data(row, recharge_bundle_order_id=order.id)
        eng.ensure_task(db, row, 'bundle_review' if purpose == 'refund' else 'bundle_execute',
                        '独立复核整份组合退款' if purpose == 'refund' else '核对条款并确认组合实际收款', 'manager' if purpose == 'refund' else 'finance')
        member.updated_at = utcnow(); _event(db, user, row, order, 'create', reason); db.flush()
        return describe(db, user, row.id)
    return group._execute(db, user, request_id, 'bundle_create', {'customer_id':customer_id,'purpose':purpose,'values':values,'reason':reason}, operation, FRONT)


def describe(db, user, key):
    with group.authority(db, user, READ) as sid:
        row, order = _order(db, user, key); member = group._member(db, order.member_id, sid)
        purchase = db.scalar(select(Purchase).where(Purchase.case_id == row.id)) if order.purpose == 'purchase' else _purchase(db, order.values['purchase_id'], member, sid)
        rule = _rule(db, order.values['rule_id']) if order.purpose == 'purchase' else _rule(db, purchase.rule_id)
        refund = db.scalar(select(Refund).where(Refund.case_id == row.id))
        return {'case': {k:getattr(row,k) for k in ['id','number','title','version','state','customer_id','amount_cents']},
            'order':clean(order), 'member':group._wallet(member), 'rule':rule_info(db, rule, user.role in {'admin','manager','finance','auditor'}),
            'purchase':purchase_info(db, member, purchase, user.role in {'admin','manager','finance','auditor'}) if purchase else None,
            'refund':clean(refund) if refund else None}


def orders(db, user):
    with group.authority(db, user, READ):
        rows = list(db.scalars(select(Case).where(Case.kind == 'recharge_bundle').order_by(Case.id.desc()).limit(200)))
        return {'items': [{k:getattr(r,k) for k in ['id','number','title','state','customer_id']} for r in rows if can_read(user,r)]}


def command(db, user, key, request_id, version, case_version, member_version, action, values):
    roles = {'admin','manager'} if action in {'approve','reject'} else {'admin','finance'} if action == 'execute' else FRONT
    def operation(sid):
        row, order = _order(db, user, key); group._version(row, case_version); group._version(order, version)
        member = group._member(db, order.member_id, sid, member_version)
        row.updated_at = utcnow(); member.updated_at = utcnow()
        if order.status in {'completed','cancelled'}: raise HTTPException(409, '充值组合办理已结束')
        refund = db.scalar(select(Refund).where(Refund.case_id == row.id).with_for_update())
        purchase = _purchase(db, refund.purchase_id, member, sid) if refund else None
        components = _components(db, purchase, True) if purchase else []
        if action in {'cancel','reject'}:
            if action == 'cancel' and user.id != order.requested_by and user.role not in {'admin','manager'}:
                raise HTTPException(403, '仅申请人或主管可撤销组合办理')
            if refund and refund.status == 'reserved':
                member.reserved_cents -= refund.amount_cents
                for _p,c,w,_b in components: w.reserved_units -= c.units_per_share*refund.shares
            if refund: refund.status = 'released'
            order.status = 'cancelled'; row.state = 'cancelled'; row.completed_date = today(); eng.close_tasks(db,row,user)
        elif action == 'approve':
            if not refund or order.status != 'draft': raise HTTPException(409, '只有待复核的组合退款可批准')
            if order.requested_by == user.id: raise HTTPException(403, '退款申请与批准必须由不同员工办理')
            _assigned(db,user,row,'bundle_review'); group._evidence(db,row,values['evidence_id'],user)
            if refund.shares > _availability(db,member,purchase,components)['refundable_shares']:
                raise HTTPException(409, '可退整份已变化；本金、原批次赠品或退款期限不足，请刷新核对')
            member.reserved_cents += refund.amount_cents
            for _p,c,w,_b in components: w.reserved_units += c.units_per_share*refund.shares
            refund.status = 'reserved'; order.status = 'approved'; order.approved_by = user.id; row.state = 'approved'
            eng.finish_task(db,row,'bundle_review',user); eng.ensure_task(db,row,'bundle_execute','按原账户退款并回收原组合赠品','finance')
        elif action == 'execute':
            _assigned(db,user,row,'bundle_execute')
            proof = group._evidence(db,row,values['evidence_id'],user)
            if proof.category != 'receipt': raise HTTPException(422, '实际收退款须提供本单的收付款凭据')
            if order.purpose == 'purchase':
                if order.status != 'draft': raise HTTPException(409, '当前组合购买状态不能确认收款')
                rule = _sale_rule(db,order.values['rule_id'],sid)
                cash, account = group._cash(db,user,row,{**values,'amount_cents':row.amount_cents},'in')
                member.balance_cents += row.amount_cents
                original = group._entry(db,user,member,row,'topup',row.amount_cents,proof.id,cash=cash,account=account,reference=values['reference'])
                purchase = Purchase(case_id=row.id,member_id=member.id,rule_id=rule.id,shares=order.values['shares'],principal_entry_id=original.id,evidence_id=proof.id,actor_id=user.id)
                db.add(purchase); db.flush()
                for component, benefit in _rule_components(db,rule):
                    wallet, entry = benefits._issue(db,user,member,row,benefit,component.units_per_share*purchase.shares,'grant',proof.id,values['reason'])
                    db.add(Component(store_id=sid,purchase_id=purchase.id,rule_component_id=component.id,wallet_id=wallet.id,grant_entry_id=entry.id)); db.flush()
                    if benefit.kind == 'points':
                        from .membership_points import settle_point_debt
                        settle_point_debt(db,user,member,wallet,row,proof.id)
            else:
                if order.status != 'approved' or refund.status != 'reserved': raise HTTPException(409, '须先由独立主管批准并占额再执行退款')
                rule = _rule(db,purchase.rule_id)
                if member.reserved_cents < refund.amount_cents or member.balance_cents < refund.amount_cents:
                    raise HTTPException(409, '本金退款占额不一致，请停止办理并核对')
                if rule.refund_policy == 'whole_unused_before_expiry' and any(today()>w.expires_on for _p,_c,w,_b in components):
                    raise HTTPException(409, '赠品退款期限已过，请撤销占额；不能沿用过期批准执行')
                original = db.scalar(select(GroupEntry).where(GroupEntry.id == purchase.principal_entry_id))
                from .business_finance_stored import effective_group_topup
                original=effective_group_topup(db,original)
                returned = db.scalar(select(func.coalesce(func.sum(-GroupEntry.amount_cents),0)).where(GroupEntry.original_id==original.id,GroupEntry.purpose=='refund')) or 0
                if returned+refund.amount_cents>original.amount_cents: raise HTTPException(409,'原组合本金退款已超额，请核对')
                for part,component,wallet,_benefit in components:
                    units = component.units_per_share*refund.shares
                    if units>wallet.reserved_units or units>wallet.balance_units: raise HTTPException(409,'原赠品退款占额不一致，请停止办理')
                    grant = db.scalar(select(BenefitEntry).where(BenefitEntry.id == part.grant_entry_id))
                    wallet.balance_units -= units; wallet.reserved_units -= units
                    entry = benefits._entry(db,user,wallet,row,'adjust',-units,proof.id,'原组合整份退款回收：'+values['reason'],original=grant)
                    item = db.scalar(select(RefundComponent).where(RefundComponent.refund_id==refund.id,RefundComponent.component_id==part.id))
                    db.add(Posting(refund_component_id=item.id,benefit_entry_id=entry.id))
                cash, account = group._cash(db,user,row,{**values,'amount_cents':refund.amount_cents},'out',original)
                member.balance_cents -= refund.amount_cents; member.reserved_cents -= refund.amount_cents
                entry = group._entry(db,user,member,row,'refund',-refund.amount_cents,proof.id,original,cash,account,values['reference'])
                refund.status = 'applied'; refund.executed_entry_id = entry.id
            order.status = 'completed'; row.state = 'completed'; row.completed_date = today(); eng.close_tasks(db,row,user)
        else: raise HTTPException(404, '充值组合动作不存在')
        _event(db,user,row,order,action,values['reason'],{'evidence_id':values.get('evidence_id')}); db.flush()
        return describe(db,user,key)
    return group._execute(db,user,request_id,'bundle:'+str(key)+':'+action,
        {'version':version,'case_version':case_version,'member_version':member_version,'values':values},operation,roles)


def guard_principal_refund(db, original_id):
    if db.scalar(select(Purchase.id).where(Purchase.principal_entry_id == original_id)):
        raise HTTPException(409, '此本金来自充值组合，请从原组合申请整份退款并同时回收原赠品')


def guard_component_action(db, wallet_id, action):
    if action == 'adjust' or action.startswith('refund'):
        if is_bundle_wallet(db,wallet_id):
            raise HTTPException(409, '组合赠品不能单独撤销或现金退款，请按原组合完整份额办理')


def is_bundle_wallet(db,wallet_id):
    if not db.info.get('_group_authority'): raise HTTPException(403, '赠品来源须经集团服务核对')
    # The central mapping exposes no other-store case or file. Ordinary
    # ORM queries still protect every store business row independently.
    return db.scalar(select(Component.wallet_id).where(Component.wallet_id==wallet_id)) is not None


def analytics_rows(db, user):
    """Scoped read-only source rows; never add these cash rows to raw cash twice."""
    if user.role not in {'admin','manager','finance','auditor'}: return {'cash':[],'gifts':[],'refund_holds':[]}
    previous = db.info.get('_group_authority')
    db.info['_group_authority'] = ('report', tuple(db.info.get('store_scope', ())))
    try:
        def bounded(statement):
            result=list(db.execute(statement.limit(25001)))
            if len(result)>25000: raise HTTPException(413,'充值组合统计超过上限，请缩小授权门店或分批核对')
            return result
        cash_rows=[]; gift_rows=[]; held=[]
        for purchase,rule,entry,cash in bounded(select(Purchase,Rule,GroupEntry,CashEntry)
            .join(Rule,Rule.id==Purchase.rule_id).join(GroupEntry,GroupEntry.id==Purchase.principal_entry_id).join(CashEntry,CashEntry.id==GroupEntry.cash_id)):
            from .business_finance_stored import effective_cash
            from .business_finance_bundle_corrections import effective_shares
            current,_=effective_cash(db,entry.cash_id,entry.account_id)
            if not current:continue
            cash_rows.append({'id':'purchase-'+str(purchase.id),'case_id':purchase.case_id,'store_id':purchase.store_id,
                'rule_id':rule.id,'name':rule.name,'rule_version':rule.rule_version,'cash_id':current.id,
                'business_date':str(current.business_date),'amount_cents':current.amount_cents,'shares':effective_shares(db,purchase),'purpose':'purchase'})
        for refund,purchase,rule,entry,cash in bounded(select(Refund,Purchase,Rule,GroupEntry,CashEntry)
            .join(Purchase,Purchase.id==Refund.purchase_id).join(Rule,Rule.id==Purchase.rule_id)
            .join(GroupEntry,GroupEntry.id==Refund.executed_entry_id).join(CashEntry,CashEntry.id==GroupEntry.cash_id)):
            cash_rows.append({'id':'refund-'+str(refund.id),'case_id':refund.case_id,'store_id':refund.store_id,
                'rule_id':rule.id,'name':rule.name,'rule_version':rule.rule_version,'cash_id':cash.id,
                'business_date':str(cash.business_date),'amount_cents':entry.amount_cents,'shares':-refund.shares,'purpose':'refund'})
        for component,purchase,rule,entry in bounded(select(Component,Purchase,BenefitRule,BenefitEntry)
            .join(Purchase,Purchase.id==Component.purchase_id).join(BenefitEntry,BenefitEntry.id==Component.grant_entry_id)
            .join(BenefitWallet,BenefitWallet.id==Component.wallet_id).join(BenefitRule,BenefitRule.id==BenefitWallet.rule_id)):
            gift_rows.append({'id':entry.id,'case_id':entry.case_id,'store_id':entry.store_id,'purchase_id':purchase.id,
                'kind':rule.kind,'unit_label':UNITS[rule.kind],'name':rule.name,'units':entry.units,'occurred_at':entry.occurred_at.isoformat(),'purpose':'grant'})
        for posting,part,component,entry,wallet,rule in bounded(select(Posting,RefundComponent,Component,BenefitEntry,BenefitWallet,BenefitRule)
            .join(RefundComponent,RefundComponent.id==Posting.refund_component_id).join(Component,Component.id==RefundComponent.component_id)
            .join(BenefitEntry,BenefitEntry.id==Posting.benefit_entry_id).join(BenefitWallet,BenefitWallet.id==Component.wallet_id)
            .join(BenefitRule,BenefitRule.id==BenefitWallet.rule_id)):
            gift_rows.append({'id':entry.id,'case_id':entry.case_id,'store_id':entry.store_id,'purchase_id':component.purchase_id,
                'kind':rule.kind,'unit_label':UNITS[rule.kind],'name':rule.name,'units':entry.units,'occurred_at':entry.occurred_at.isoformat(),'purpose':'refund_recovery'})
        for refund,purchase,rule in bounded(select(Refund,Purchase,Rule).join(Purchase,Purchase.id==Refund.purchase_id)
            .join(Rule,Rule.id==Purchase.rule_id).where(Refund.status=='reserved')):
            held.append({'id':refund.id,'case_id':refund.case_id,'store_id':refund.store_id,'name':rule.name,
                'amount_cents':refund.amount_cents,'shares':refund.shares})
        from .business_finance_models import FinanceBundleCorrectionPosting as FixPost,FinanceBundleCorrectionComponent as FixPart,FinanceBundleCorrection as Fix
        for post,part,fix,purchase,entry,wallet,rule in bounded(select(FixPost,FixPart,Fix,Purchase,BenefitEntry,BenefitWallet,BenefitRule)
            .join(FixPart,FixPart.id==FixPost.component_id).join(Fix,Fix.id==FixPart.correction_id).join(Purchase,Purchase.id==Fix.purchase_id)
            .join(BenefitEntry,BenefitEntry.id==FixPost.benefit_entry_id).join(BenefitWallet,BenefitWallet.id==FixPart.wallet_id).join(BenefitRule,BenefitRule.id==BenefitWallet.rule_id)):
            gift_rows.append({'id':entry.id,'case_id':entry.case_id,'store_id':entry.store_id,'purchase_id':purchase.id,
                'kind':rule.kind,'unit_label':UNITS[rule.kind],'name':rule.name,'units':entry.units,'occurred_at':entry.occurred_at.isoformat(),'purpose':'correction'})
        return {'cash':cash_rows,'gifts':gift_rows,'refund_holds':held}
    finally:
        if previous is None: db.info.pop('_group_authority',None)
        else: db.info['_group_authority']=previous
