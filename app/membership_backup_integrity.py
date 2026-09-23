"""Read-only validation of lifecycle, original-point recovery and real fee cash."""
import json
from collections import defaultdict
from datetime import date


def source_proof_allowed(connection,case_id,evidence_id,store_id):
    """External proof is valid only through an actual source-specific posting."""
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_finance_cash_allocations' in tables:
        from .business_finance_integrity import source_evidence_allowed_sqlite
        if source_evidence_allowed_sqlite(connection,case_id,evidence_id,store_id):return True
    if 'aftercare_applications' not in tables:return False
    return bool(connection.execute('''SELECT 1 FROM flow_files f
        JOIN aftercare_sources s ON s.case_id=f.case_id AND s.source_case_id=? AND s.store_id=f.store_id
        JOIN aftercare_applications a ON a.case_id=s.case_id AND a.store_id=s.store_id
        WHERE f.id=? AND f.store_id=? AND f.generated=0 AND
        (a.evidence_id=f.id OR EXISTS(SELECT 1 FROM aftercare_cash_refunds r WHERE r.case_id=a.case_id AND r.evidence_id=f.id AND r.store_id=f.store_id)
        OR EXISTS(SELECT 1 FROM aftercare_cash_collections r WHERE r.case_id=a.case_id AND r.evidence_id=f.id AND r.store_id=f.store_id))''',
        (case_id,evidence_id,store_id)).fetchone())


def validate_membership_sqlite(connection):
    from .membership_fee_correction_integrity import validate as validate_fee_corrections,refund_account
    validate_fee_corrections(connection)
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'membership_rules','membership_orders','membership_cards','membership_periods','membership_period_voids','membership_fees',
        'membership_events','membership_points_claims','membership_points_changes','membership_points_recoveries','membership_points_debts','membership_points_debt_payments'}
    if not names&required:return {'verified_membership_orders':0,'verified_points_claims':0}
    if not required<=names:raise ValueError('会员生命周期表不完整')
    def rows(table):
        cursor=connection.execute('SELECT * FROM "'+table+'"');keys=[c[0] for c in cursor.description]
        return [dict(zip(keys,r)) for r in cursor]
    def keyed(table):return {r['id']:r for r in rows(table)}
    def check(ok,message):
        if not ok:raise ValueError('会员恢复校验：'+message)
    rules=keyed('membership_rules');orders=keyed('membership_orders');cards=keyed('membership_cards');periods=keyed('membership_periods')
    fees=keyed('membership_fees');voids=rows('membership_period_voids');claims=keyed('membership_points_claims');changes=keyed('membership_points_changes')
    recoveries=rows('membership_points_recoveries');debts=keyed('membership_points_debts');payments=rows('membership_points_debt_payments')
    cases=keyed('flow_cases');files=keyed('flow_files');members=keyed('group_members');links=rows('group_identity_links')
    cash=keyed('cash_entries');accounts=keyed('flow_accounts');wallets=keyed('benefit_wallets');entries=keyed('benefit_entries');benefits=keyed('benefit_rules')
    events=rows('membership_events');order_by_case={r['case_id']:r for r in orders.values()}
    payment_links=keyed('flow_payment_links');customer_allocations={r['case_id']:r for r in rows('repair_allocations') if r['payer_type']=='customer'}
    repair_paid=defaultdict(int);case_paid=defaultdict(int);principal_paid=defaultdict(int);retail_reduction=defaultdict(int);finance_paid=defaultdict(int);aftercare_reduction=defaultdict(int)
    for payment in payment_links.values():case_paid[payment['case_id']]+=payment['amount_cents']*(1 if payment['direction']=='in' else -1)
    for payment in rows('repair_payments'):
        link=payment_links.get(payment['payment_link_id'])
        check(link,'维修积分基数收款关联缺失')
        repair_paid[payment['allocation_id']]+=link['amount_cents']*(1 if link['direction']=='in' else -1)
    for payment in rows('group_payment_links'):principal_paid[payment['case_id']]+=payment['amount_cents']
    if 'business_finance_credit_links' in names:
        for payment in rows('business_finance_credit_links'):finance_paid[payment['case_id']]+=payment['amount_cents']
    if 'aftercare_adjustments' in names:
        for posting in rows('aftercare_adjustments'):aftercare_reduction[posting['allocation_id']]+=posting['credit_cents']
    package_paid=defaultdict(lambda:[0,0])
    package_sources={'repair_package_entries','repair_package_payment_links'}
    if names & package_sources:
        check(package_sources<=names,'维修套餐原支付来源表不完整')
        package_entries=keyed('repair_package_entries');seen_package_entries=set()
        for payment in rows('repair_package_payment_links'):
            entry=package_entries.get(payment['entry_id']);case=cases.get(payment['case_id'])
            check(entry and case and case['kind']=='repair' and case['flow_version'] in {3,4}
                and entry['case_id']==case['id'] and entry['store_id']==payment['store_id']==case['store_id']
                and entry['purpose']==payment['purpose'] in {'capture','reverse'}
                and entry['id'] not in seen_package_entries,'维修套餐积分原核销来源重复、缺失或串店')
            sign=1 if entry['purpose']=='capture' else -1
            check(payment['amount_cents']==sign*entry['credit_cents']
                and payment['recognized_cents']==sign*entry['paid_cents'],'维修套餐积分原对价投影不符')
            seen_package_entries.add(entry['id'])
            package_paid[case['id']][0]+=payment['amount_cents']
            package_paid[case['id']][1]+=payment['recognized_cents']
        check(seen_package_entries=={e['id'] for e in package_entries.values() if e['purpose'] in {'capture','reverse'}},
            '维修套餐积分缺少实际核销或原退投影')
        # Component intervals preserve independent original C/P curves. P may
        # exceed C in a tail interval; only their net amounts must be nonnegative.
        check(all(face>=0 and paid>=0 for face,paid in package_paid.values()),'维修套餐原对价或原退越界')
    for posting in rows('retail_return_postings'):
        retail_reduction[posting['case_id']]+=posting['goods_cents']+posting['installation_cents']-posting['retained_cents']
    # Independent replay from original captured C/P and actual return parts.
    # Original-wallet restoration is deliberately excluded: fulfillment already
    # decreased at the physical return, and must not decrease for a second time.
    retail_group = defaultdict(lambda: [0, 0])  # Effective C, effective P.
    group_sources = {'retail_group_plans', 'retail_group_tenders',
        'retail_group_captures', 'retail_group_return_parts'}
    if names & group_sources:
        check(group_sources <= names, '精品原支付来源表不完整')
        plans = keyed('retail_group_plans')
        tenders = keyed('retail_group_tenders')
        captures = keyed('retail_group_captures')
        captured_tenders = set()
        for capture in captures.values():
            tender = tenders.get(capture['tender_id'])
            plan = plans.get(tender['plan_id']) if tender else None
            case = cases.get(plan['case_id']) if plan else None
            check(case and case['kind'] == 'retail' and tender['kind'] != 'cash'
                and tender['store_id'] == plan['store_id'] == case['store_id']
                and tender['id'] not in captured_tenders, '精品积分原核销来源重复或串店')
            captured_tenders.add(tender['id'])
            retail_group[case['id']][0] += tender['credit_cents']
            retail_group[case['id']][1] += tender['consideration_cents']
        for part in rows('retail_group_return_parts'):
            if not part['capture_id']:
                continue
            capture = captures.get(part['capture_id'])
            check(capture is not None, '精品实退缺少原核销来源')
            tender = tenders[capture['tender_id']]
            case_id = plans[tender['plan_id']]['case_id']
            check(part['store_id'] == cases[case_id]['store_id'], '精品积分原实退串店')
            retail_group[case_id][0] -= part['credit_cents']
            retail_group[case_id][1] -= part['consideration_cents']
        check(all(0 <= paid <= face for face, paid in retail_group.values()),
            '精品原支付对价或已退金额越界')
    def actual_basis(case):
        data=json.loads(case['data'])
        if case['kind']=='repair' and data.get('released_date'):
            allocation=customer_allocations.get(case['id'])
            face,paid=package_paid[case['id']]
            charge=allocation['amount_cents']-aftercare_reduction[allocation['id']] if allocation else 0
            cash_paid=repair_paid[allocation['id']] if allocation else 0
            return max(0,min(charge-face+paid,cash_paid+principal_paid[case['id']]+finance_paid[case['id']]+paid))
        if case['kind']=='retail' and data.get('accepted_date'):
            charge=0 if data.get('cancelled') else case['amount_cents']-retail_reduction[case['id']]
            face, paid = retail_group[case['id']]
            net_charge = charge - (face - paid)
            return max(0,min(net_charge,case_paid[case['id']]+finance_paid[case['id']]+paid))
        return 0
    def proof(fid,case_id):
        f=files.get(fid);c=cases.get(case_id)
        return bool(f and c and f['store_id']==c['store_id'] and not f['generated'] and
            (f['case_id']==case_id or source_proof_allowed(connection,case_id,fid,c['store_id'])))
    def same_member_case(member_id,case):
        member=members.get(member_id)
        return member and any(l['identity_id']==member['identity_id'] and l['store_id']==case['store_id'] and l['local_kind']=='customer' and l['local_id']==case['customer_id'] for l in links)
    for rule in rules.values():
        ids=json.loads(rule['allowed_store_ids'])
        check(len(ids)==len(set(ids)) and rule['validity_months']>0 and rule['fee_cents']>=0 and rule['points_numerator']>0 and rule['points_denominator_fen']>0,'规则数值或门店重复')
        if rule['points_enabled']:
            benefit=benefits.get(rule['points_benefit_rule_id'])
            check(benefit and benefit['kind']=='points' and set(ids)<=set(json.loads(benefit['allowed_store_ids'])),'消费积分规则与独立积分不一致')
    for order in orders.values():
        case=cases.get(order['case_id']);values=json.loads(order['values'])
        check(case and case['kind']=='membership' and case['flow_version']==2 and case['store_id']==order['store_id'] and same_member_case(order['member_id'],case),'业务宿主、门店或会员客户不一致')
        if order['status']=='completed':check(case['state']=='completed','已完成办理宿主未完成')
        if order['purpose'] in {'renew','tier_change','renew_refund'} and order['status'] in {'approved','completed'}:
            check(order['approved_by'] is not None and order['approved_by']!=order['requested_by'],'独立复核失效')
            check(any(e['case_id']==case['id'] and e['action']=='approve' and e['actor_id']==order['approved_by'] and proof(e['evidence_id'],case['id']) for e in events),'批准缺少本单凭据')
    for event in events:check(event['case_id'] in order_by_case and event['store_id']==cases[event['case_id']]['store_id'] and (not event['evidence_id'] or proof(event['evidence_id'],event['case_id'])),'事件或凭据串店')
    by_member={}
    for card in cards.values():
        order=order_by_case.get(card['case_id']);check(order and order['member_id']==card['member_id'] and order['status']=='completed' and card['issuer_store_id']==order['store_id'],'卡发行无本店完成来源')
        by_member.setdefault(card['member_id'],[]).append(card)
        if card['previous_id']:
            previous=cards.get(card['previous_id']);check(previous and previous['member_id']==card['member_id'] and previous['generation']+1==card['generation'] and previous['status']=='replaced','换补卡代次断裂')
        else:check(card['generation']==1,'初次卡代次错误')
    for values in by_member.values():check(sum(c['status']=='active' for c in values)<=1 and sorted(c['generation'] for c in values)==list(range(1,len(values)+1)),'重复有效卡或代次断裂')
    for period in periods.values():
        order=order_by_case.get(period['case_id']);check(order and order['member_id']==period['member_id'] and order['purpose']==period['kind'] and order['status']=='completed' and order['store_id']==period['store_id'] and json.loads(order['values'])['rule_id']==period['rule_id'],'会员期间来源不一致')
        check(date.fromisoformat(period['starts_on'])<=date.fromisoformat(period['ends_on']),'会员期间倒置')
        if period['kind']=='renew' and rules[period['rule_id']]['fee_cents']:
            check(sum(f['amount_cents'] for f in fees.values() if f['period_id']==period['id'] and f['amount_cents']>0)==rules[period['rule_id']]['fee_cents'],'收费期缺少正确实际收款')
    for fee in fees.values():
        order=order_by_case.get(fee['case_id']);c=cash.get(fee['cash_id']);account=accounts.get(fee['account_id'])
        check(order and account and c and account['store_id']==fee['store_id']==order['store_id']==c['store_id'] and order['status']=='completed','续会现金门店或来源异常')
        check(c['approval_state']=='approved' and c['amount_cents']==abs(fee['amount_cents']) and c['voucher_no']==fee['reference'] and c['direction']==('in' if fee['amount_cents']>0 else 'out') and c['category']==('group_member_fee' if fee['amount_cents']>0 else 'group_member_fee_refund') and proof(fee['evidence_id'],fee['case_id']),'续会现金金额、方向或凭据错误')
        if fee['original_id']:
            original=fees.get(fee['original_id']);check(original and original['amount_cents']==-fee['amount_cents'] and original['period_id']==fee['period_id'] and refund_account(connection,fee,original)==fee['account_id'],'续会退款未追原款原账户')
    for void in voids:
        p=periods.get(void['period_id']);check(p and void['store_id']==p['store_id'] and any(f['case_id']==void['case_id'] and f['period_id']==p['id'] and f['amount_cents']<0 for f in fees.values()),'期间撤销缺少实际原款退款')
    check({c['id'] for c in cash.values() if c['category'] in {'group_member_fee','group_member_fee_refund'}}=={f['cash_id'] for f in fees.values()},'存在无会员业务来源的续会现金')
    for claim in claims.values():
        case=cases.get(claim['case_id']);check(case and case['store_id']==claim['store_id'] and ((case['kind']=='repair' and case['flow_version'] in {3,4}) or (case['kind']=='retail' and case['flow_version']==2)),'积分原消费类型或门店错误')
        if claim['member_id']:check(same_member_case(claim['member_id'],case),'消费积分会员与客户不一致')
        cs=[c for c in changes.values() if c['claim_id']==claim['id']]
        check(sum(c['units'] for c in cs)==claim['target_units'],'积分累计发放追回与当前应得不一致')
        if claim['rule_id']:
            rule=rules.get(claim['rule_id']);check(rule and rule['points_enabled'] and claim['target_units']==claim['basis_cents']*rule['points_numerator']//rule['points_denominator_fen'],'冻结消费积分取整不一致')
            check(claim['basis_cents']==actual_basis(case),'积分基数与原消费实际收付及履约不一致')
        else:check(not cs and claim['target_units']==0 and claim['basis_cents']==0,'无冻结规则却发放积分')
    for change in changes.values():
        claim=claims.get(change['claim_id']);check(claim and claim['case_id']==change['case_id'] and claim['store_id']==change['store_id'] and proof(change['evidence_id'],change['case_id']),'积分变动缺少原履约或退款来源')
        if change['units']>0:
            wallet=wallets.get(change['wallet_id']);check(wallet and wallet['member_id']==claim['member_id'] and wallet['source_case_id']==claim['case_id'] and wallet['initial_units']==change['units'] and wallet['rule_id']==rules[claim['rule_id']]['points_benefit_rule_id'],'消费发放与独立积分钱包不一致')
        else:
            recovered=sum(r['units'] for r in recoveries if r['change_id']==change['id']);owed=sum(d['units'] for d in debts.values() if d['change_id']==change['id'])
            check(not change['wallet_id'] and recovered+owed==-change['units'],'追回积分与原应扣积分不守恒')
    for recovery in recoveries:
        change=changes.get(recovery['change_id']);entry=entries.get(recovery['benefit_entry_id']);original=entries.get(entry['original_id']) if entry else None
        check(change and change['units']<0 and entry and original and original['purpose']=='grant' and entry['purpose']=='adjust' and entry['units']==-recovery['units'] and entry['wallet_id']==original['wallet_id'],'原批次积分追回关联错误')
        check(any(c['claim_id']==change['claim_id'] and c['units']>0 and c['wallet_id']==entry['wallet_id'] for c in changes.values()),'追回了其他消费的积分')
    for debt in debts.values():
        change=changes.get(debt['change_id']);check(change and change['units']<0 and claims[change['claim_id']]['member_id']==debt['member_id'],'积分待追回未关联原消费')
        check(sum(p['units'] for p in payments if p['debt_id']==debt['id'])<=debt['units'],'积分债已过量抵扣')
    for payment in payments:
        debt=debts.get(payment['debt_id']);entry=entries.get(payment['benefit_entry_id']);wallet=wallets.get(entry['wallet_id']) if entry else None
        check(debt and wallet and wallet['member_id']==debt['member_id'] and entry['store_id']==payment['store_id'] and entry['purpose']=='adjust' and entry['units']==-payment['units'] and benefits[wallet['rule_id']]['kind']=='points','未来积分抵债没有相同会员实际扣减')
    return {'verified_membership_orders':len(orders),'verified_points_claims':len(claims)}
