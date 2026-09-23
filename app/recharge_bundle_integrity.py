"""Read-only restore checks for frozen bundle composition and original returns."""
import json
from collections import defaultdict


def validate_recharge_bundles_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'recharge_bundle_'+x for x in ('rules','rule_components','orders','purchases','components','refunds','refund_components','refund_postings')}
    if not required.intersection(names): return {'verified_recharge_bundle_purchases':0,'verified_recharge_bundle_refunds':0}
    if not required<=names: raise ValueError('充值组合表不完整')
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);keys=[c[0] for c in cursor.description]
        return [dict(zip(keys,row)) for row in cursor]
    def indexed(name):return {r['id']:r for r in rows(name)}
    rules=indexed('recharge_bundle_rules');parts=indexed('recharge_bundle_rule_components')
    orders={r['case_id']:r for r in rows('recharge_bundle_orders')}
    purchases=indexed('recharge_bundle_purchases');components=indexed('recharge_bundle_components')
    refunds=indexed('recharge_bundle_refunds');refund_parts=indexed('recharge_bundle_refund_components')
    postings=rows('recharge_bundle_refund_postings');cases=indexed('flow_cases');files=indexed('flow_files')
    benefit_rules=indexed('benefit_rules');wallets=indexed('benefit_wallets');entries=indexed('benefit_entries')
    principal=indexed('group_entries');members=indexed('group_members');cash=indexed('cash_entries');accounts=indexed('flow_accounts')
    identities={(r['store_id'],r['local_id'],r['identity_id']) for r in rows('group_identity_links') if r['local_kind']=='customer'}
    parts_by_rule=defaultdict(list);components_by_purchase=defaultdict(list);refund_parts_by_refund=defaultdict(list)
    refunds_by_purchase=defaultdict(list);postings_by_part=defaultdict(list)
    events=defaultdict(list)
    for e in rows('group_events'):
        if e['action'].startswith('bundle_'):
            detail=json.loads(e['detail']);e['detail']=detail;events[detail.get('bundle_order_id')].append(e)
    for part in parts.values():parts_by_rule[part['bundle_rule_id']].append(part)
    for component in components.values():components_by_purchase[component['purchase_id']].append(component)
    for part in refund_parts.values():refund_parts_by_refund[part['refund_id']].append(part)
    for refund in refunds.values():refunds_by_purchase[refund['purchase_id']].append(refund)
    for posting in postings:postings_by_part[posting['refund_component_id']].append(posting)
    def source(case_id,store,member,evidence=None,receipt=False):
        row=cases.get(case_id)
        if not row or row['store_id']!=store or member not in members or (store,row['customer_id'],members[member]['identity_id']) not in identities:
            raise ValueError('充值组合原单、客户和门店身份不符')
        if evidence:
            file=files.get(evidence)
            if not file or file['case_id']!=case_id or file['store_id']!=store or file['generated'] or file['category'] not in ({'receipt'} if receipt else {'receipt','evidence'}):
                raise ValueError('充值组合实际办理凭据不属于本单')
        return row
    for rule in rules.values():
        ids=json.loads(rule['allowed_store_ids']);rc=parts_by_rule[rule['id']]
        if not 1<=len(rc)<=4 or rule['principal_cents_per_share']<=0 or len(ids)!=len(set(ids)) or rule['issuer_store_id'] not in ids or rule['sale_starts_on']>rule['sale_ends_on'] or not 10<=len(rule['refund_terms'])<=1000:
            raise ValueError('充值组合冻结规则无效')
        if rule['refund_policy'] not in {'whole_unused_before_expiry','whole_unused_anytime'}:raise ValueError('充值组合退款条款无效')
        kinds=set()
        for part in rc:
            benefit=benefit_rules.get(part['benefit_rule_id'])
            if not benefit or part['units_per_share']<=0 or benefit['sale_cents_per_unit'] or benefit['refund_policy']!='none' or set(json.loads(benefit['allowed_store_ids']))!=set(ids) or benefit['kind'] in kinds:
                raise ValueError('充值组合赠品规则、门店或独立单位不符')
            kinds.add(benefit['kind'])
    for row in orders.values():
        case=source(row['case_id'],row['store_id'],row['member_id']);values=json.loads(row['values'])
        if case['kind']!='recharge_bundle' or case['flow_version']!=2 or values.get('terms_accepted') is not True or not isinstance(values.get('shares'),int) or values['shares']<=0:
            raise ValueError('充值组合宿主或确认条款不符')
        if row['purpose']=='refund' and (row['status'] in {'approved','completed'} or row['approved_by'] is not None):
            approvals=[e for e in events[row['id']] if e['action']=='bundle_approve']
            if len(approvals)!=1 or not row['approved_by'] or row['approved_by']==row['requested_by'] or approvals[0]['actor_id']!=row['approved_by']:
                raise ValueError('充值组合退款缺少独立批准')
            evidence=approvals[0]['detail'].get('evidence_id')
            if not evidence:raise ValueError('充值组合退款批准缺少凭据')
            source(row['case_id'],row['store_id'],row['member_id'],evidence)
        if case['state']!={'draft':'pending','approved':'approved','completed':'completed','cancelled':'cancelled'}[row['status']]:raise ValueError('充值组合办理状态不符')
    from .business_finance_bundle_integrity import bundle_correction_state,validate_bundle_corrections_sqlite
    validate_bundle_corrections_sqlite(connection)
    corrected_shares,_holds,_correction_entries=bundle_correction_state(connection)
    known_topups=set();known_grants=set();known_refunds=set();known_adjustments=set()
    for purchase in purchases.values():
        rule=rules.get(purchase['rule_id']);order=orders.get(purchase['case_id']);entry=principal.get(purchase['principal_entry_id'])
        if not rule or not order or order['purpose']!='purchase' or order['status']!='completed' or order['member_id']!=purchase['member_id'] or order['store_id']!=purchase['store_id']:
            raise ValueError('充值组合购买缺少完整宿主')
        values=json.loads(order['values'])
        if values['rule_id']!=rule['id'] or values['shares']!=purchase['shares'] or purchase['shares']<=0 or purchase['store_id'] not in json.loads(rule['allowed_store_ids']) or not rule['enabled']:
            raise ValueError('充值组合购买偏离冻结版本')
        case=source(purchase['case_id'],purchase['store_id'],purchase['member_id'],purchase['evidence_id'],True)
        fact=cash.get(entry['cash_id']) if entry else None
        amount=rule['principal_cents_per_share']*purchase['shares']
        if not entry or entry['purpose']!='topup' or entry['case_id']!=case['id'] or entry['store_id']!=case['store_id'] or entry['member_id']!=purchase['member_id'] or entry['evidence_id']!=purchase['evidence_id'] or entry['amount_cents']!=amount or case['amount_cents']!=amount or entry['actor_id']!=purchase['actor_id']:
            raise ValueError('充值组合本金分账或来源金额不符')
        if not fact or fact['direction']!='in' or fact['category']!='group_member_topup' or fact['amount_cents']!=amount or fact['store_id']!=case['store_id'] or not rule['sale_starts_on']<=fact['business_date']<=rule['sale_ends_on'] or fact['created_by']!=purchase['actor_id']:
            raise ValueError('充值组合实际收款重复或偏离发行期间')
        known_topups.add(entry['id'])
        pc=components_by_purchase[purchase['id']]
        if {c['rule_component_id'] for c in pc}!={c['id'] for c in parts_by_rule[rule['id']]} or len(pc)!=len(parts_by_rule[rule['id']]):
            raise ValueError('充值组合赠品未完整原子发行')
        for component in pc:
            part=parts[component['rule_component_id']];wallet=wallets.get(component['wallet_id']);grant=entries.get(component['grant_entry_id'])
            if not wallet or not grant or component['store_id']!=purchase['store_id'] or wallet['member_id']!=purchase['member_id'] or wallet['rule_id']!=part['benefit_rule_id'] or wallet['source_case_id']!=purchase['case_id'] or wallet['source_kind']!='grant' or wallet['cash_id'] is not None or wallet['evidence_id']!=purchase['evidence_id']:
                raise ValueError('充值组合赠品批次来源不符或重复现金')
            if wallet['initial_units']!=part['units_per_share']*purchase['shares'] or grant['purpose']!='grant' or grant['wallet_id']!=wallet['id'] or grant['units']!=wallet['initial_units'] or grant['evidence_id']!=purchase['evidence_id']:
                raise ValueError('充值组合赠品未按原规则独立单位分账')
            from datetime import date,timedelta
            expected=date.fromisoformat(fact['business_date'])+timedelta(days=benefit_rules[wallet['rule_id']]['validity_days'])
            if wallet['expires_on']!=str(expected):raise ValueError('充值组合赠品有效期被改变')
            known_grants.add(grant['id'])
        active=[r for r in refunds_by_purchase[purchase['id']] if r['status'] in {'reserved','applied'}]
        if sum(r['shares'] for r in active)>purchase['shares']+corrected_shares.get(purchase['id'],0):raise ValueError('充值组合被重复退还超过有效原份数')
    for refund in refunds.values():
        purchase=purchases.get(refund['purchase_id']);order=orders.get(refund['case_id'])
        if not purchase or not order or order['purpose']!='refund' or refund['store_id']!=purchase['store_id'] or refund['member_id']!=purchase['member_id']:
            raise ValueError('充值组合退款原来源不符')
        values=json.loads(order['values']);rule=rules[purchase['rule_id']]
        if values['purchase_id']!=purchase['id'] or values['shares']!=refund['shares'] or refund['amount_cents']!=refund['shares']*rule['principal_cents_per_share']:
            raise ValueError('充值组合退款偏离原份数和本金')
        case=source(refund['case_id'],refund['store_id'],refund['member_id'])
        if case['amount_cents']!=refund['amount_cents'] or order['status']!={'requested':'draft','reserved':'approved','applied':'completed','released':'cancelled'}[refund['status']]:
            raise ValueError('充值组合退款占额状态不符')
        rp=refund_parts_by_refund[refund['id']]
        if {r['component_id'] for r in rp}!={p['id'] for p in components_by_purchase[purchase['id']]} or len(rp)!=len(components_by_purchase[purchase['id']]):
            raise ValueError('充值组合退款缺少应回收赠品')
        for part in rp:
            component=components[part['component_id']];units=parts[component['rule_component_id']]['units_per_share']*refund['shares']
            if part['store_id']!=refund['store_id'] or part['units']!=units:raise ValueError('充值组合回收赠品的原单位不符')
            posted=postings_by_part[part['id']]
            if len(posted)!=(1 if refund['status']=='applied' else 0):raise ValueError('充值组合退款未原子回收赠品')
            if posted:
                e=entries.get(posted[0]['benefit_entry_id'])
                if not e or posted[0]['store_id']!=refund['store_id'] or e['purpose']!='adjust' or e['wallet_id']!=component['wallet_id'] or e['original_id']!=component['grant_entry_id'] or e['units']!=-units or e['case_id']!=refund['case_id'] or e['cash_id'] is not None:
                    raise ValueError('充值组合回收使用了其他赠品或产生额外现金')
                source(e['case_id'],refund['store_id'],refund['member_id'],e['evidence_id'],True);known_adjustments.add(e['id'])
        if refund['status']=='applied':
            e=principal.get(refund['executed_entry_id']);original=principal[purchase['principal_entry_id']];fact=cash.get(e['cash_id']) if e else None
            from .business_finance_correction_integrity import effective_original_cash_sqlite
            effective_cash=cash.get(effective_original_cash_sqlite(connection,original['cash_id'],e['occurred_at'] if e else None))
            if not e or e['purpose']!='refund' or e['original_id']!=original['id'] or e['case_id']!=refund['case_id'] or e['member_id']!=refund['member_id'] or e['amount_cents']!=-refund['amount_cents'] or not effective_cash or accounts.get(e['account_id'],{}).get('name')!=effective_cash['account']:
                raise ValueError('充值组合退款本金未追溯原收款')
            if not fact or fact['direction']!='out' or fact['category']!='group_member_refund' or fact['amount_cents']!=refund['amount_cents'] or fact['account']!=effective_cash['account'] or fact['store_id']!=refund['store_id']:
                raise ValueError('充值组合未按原账户实际退款')
            source(e['case_id'],refund['store_id'],refund['member_id'],e['evidence_id'],True)
            if rule['refund_policy']=='whole_unused_before_expiry' and any(fact['business_date']>wallets[p['wallet_id']]['expires_on'] for p in components_by_purchase[purchase['id']]):
                raise ValueError('充值组合超过冻结期限实际退款')
            known_refunds.add(e['id'])
    if any(e['purpose']=='refund' and e['original_id'] in known_topups and e['id'] not in known_refunds for e in principal.values()):raise ValueError('组合本金绕过完整赠品回收单独退款')
    bundle_wallets={c['wallet_id'] for c in components.values()}
    debt_entries={r['benefit_entry_id'] for r in rows('membership_points_debt_payments')} if 'membership_points_debt_payments' in names else set()
    for e in entries.values():
        if e['wallet_id'] in bundle_wallets and e['purpose']=='adjust' and e['id'] not in known_adjustments:
            # Automatic recovery of an existing source-linked points debt is a
            # consumption of the issued batch, not an arbitrary gift reversal.
            if e['id'] not in debt_entries:raise ValueError('组合赠品绕过原组合被单独撤销')
    for e in principal.values():
        if e['case_id'] in orders and e['id'] not in known_topups|known_refunds:raise ValueError('充值组合存在未关联的额外本金分账')
    for e in entries.values():
        if e['case_id'] in orders and e['id'] not in known_grants|known_adjustments|debt_entries:raise ValueError('充值组合存在未关联的额外赠品分账')
    return {'verified_recharge_bundle_purchases':len(purchases),'verified_recharge_bundle_refunds':len(refunds)}
