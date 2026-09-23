"""Offline, read-only SQLite checks for fixed-unit benefit ledgers and clearing."""
from collections import defaultdict


def validate_benefits_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'benefit_rules','benefit_wallets','benefit_entries','benefit_reservations','benefit_payment_links','benefit_settlements','benefit_refunds'}
    if not required.intersection(names):return {'verified_benefit_wallets':0,'verified_benefit_entries':0}
    if not required<=names:raise ValueError('集团权益表不完整')
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name)
        keys=[c[0] for c in cursor.description]
        return [dict(zip(keys,r)) for r in cursor]
    rules={r['id']:r for r in rows('benefit_rules')}
    wallets={r['id']:r for r in rows('benefit_wallets')}
    entries={r['id']:r for r in rows('benefit_entries')}
    reservations={r['id']:r for r in rows('benefit_reservations')}
    refunds=rows('benefit_refunds')
    cases={r['id']:r for r in rows('flow_cases')}
    files={r['id']:r for r in rows('flow_files')}
    cash={r['id']:r for r in rows('cash_entries')}
    members={r['id']:r for r in rows('group_members')}
    links={(r['store_id'],r['local_id'],r['identity_id']) for r in rows('group_identity_links') if r['local_kind']=='customer'}
    points_entries=set()
    if 'membership_points_changes' in names:
        changes=rows('membership_points_changes')
        recoveries=rows('membership_points_recoveries')
        debts=rows('membership_points_debt_payments')
        for entry in entries.values():
            if (entry['purpose']=='grant' and any(c['wallet_id']==entry['wallet_id'] and c['case_id']==entry['case_id'] and c['evidence_id']==entry['evidence_id'] and c['units']==entry['units'] for c in changes)) or any(r['benefit_entry_id']==entry['id'] for r in recoveries+debts):points_entries.add(entry['id'])
    def source(store,case_id,evidence,member_id,entry_id=None):
        case=cases.get(case_id);asset=files.get(evidence);member=members.get(member_id)
        from .group_aftercare_integrity import aftercare_evidence_allowed
        from .membership_backup_integrity import source_proof_allowed
        matched=asset and (asset['case_id']==case_id or (entry_id and aftercare_evidence_allowed(connection,'benefit',entry_id,case_id,evidence,store)) or (entry_id in points_entries and source_proof_allowed(connection,case_id,evidence,store)))
        if not case or case['store_id']!=store or not asset or asset['store_id']!=store or not matched or not member or (store,case['customer_id'],member['identity_id']) not in links:
            raise ValueError('权益原单、客户、门店或凭据关系不一致')
    sums=defaultdict(int);held=defaultdict(int);initial=defaultdict(list);by_original=defaultdict(list)
    for e in entries.values():
        wallet=wallets.get(e['wallet_id'])
        if not wallet or wallet['rule_id'] not in rules:raise ValueError('权益流水批次或规则不存在')
        rule=rules[wallet['rule_id']]
        source(e['store_id'],e['case_id'],e['evidence_id'],wallet['member_id'],e['id'])
        sums[wallet['id']]+=e['units']
        if e['purpose'] in {'purchase','grant','exchange_in'}:initial[wallet['id']].append(e)
        if e['original_id']:by_original[e['original_id']].append(e)
        expected_credit=-e['units']*rule['credit_cents_per_unit'] if e['purpose'] in {'capture','reverse'} else 0
        if e['credit_cents']!=expected_credit:raise ValueError('权益核销抵扣与冻结单位价值不符')
        if e['purpose'] in {'purchase','refund'}:
            fact=cash.get(e['cash_id'])
            if not fact or fact['store_id']!=e['store_id'] or fact['amount_cents']!=abs(e['units'])*rule['sale_cents_per_unit'] or fact['direction']!=('in' if e['purpose']=='purchase' else 'out') or fact['category']!=('benefit_purchase' if e['purpose']=='purchase' else 'benefit_refund'):
                raise ValueError('权益实际现金与原收退款不符')
            if e['account_id']!=wallet['account_id']:raise ValueError('权益退款偏离原账户')
        elif e['cash_id'] is not None:raise ValueError('权益赠送或核销重复生成现金')
        if e['purpose'] in {'refund','reverse'}:
            original=entries.get(e['original_id'])
            if not original or original['wallet_id']!=e['wallet_id'] or original['store_id']!=e['store_id'] or original['purpose']!=('purchase' if e['purpose']=='refund' else 'capture'):
                raise ValueError('权益退款或冲正原单关联不符')
    for r in reservations.values():
        w=wallets.get(r['wallet_id'])
        if not w:raise ValueError('权益占额批次不存在')
        source(r['store_id'],r['case_id'],r['evidence_id'],w['member_id'])
        if r['credit_cents']!=r['units']*rules[w['rule_id']]['credit_cents_per_unit']:raise ValueError('权益占额金额与原规则不符')
        if r['status']=='reserved':held[w['id']]+=r['units']
    for r in refunds:
        w=wallets.get(r['wallet_id'])
        if not w or w['source_kind']!='purchase' or r['store_id']!=w['issuer_store_id'] or r['case_id']!=w['source_case_id']:
            raise ValueError('权益退款申请原始批次关系不符')
        source(r['store_id'],r['case_id'],r['evidence_id'],w['member_id'])
        if r['status']=='approved':held[w['id']]+=r['units']
        if r['status']=='executed':
            e=entries.get(r['executed_entry_id'])
            if not e or e['wallet_id']!=w['id'] or e['purpose']!='refund' or -e['units']!=r['units']:raise ValueError('权益退款执行与批准份数不符')
    if 'recharge_bundle_refunds' in names:
        bundle_refunds={r['id']:r for r in rows('recharge_bundle_refunds')}
        bundle_parts={r['id']:r for r in rows('recharge_bundle_components')}
        for r in rows('recharge_bundle_refund_components'):
            refund=bundle_refunds.get(r['refund_id']);part=bundle_parts.get(r['component_id'])
            if not refund or not part:raise ValueError('充值组合退款赠品来源不完整')
            if refund['status']=='reserved':held[part['wallet_id']]+=r['units']
    from .business_finance_bundle_integrity import bundle_correction_state
    _deltas,bundle_holds,_entries=bundle_correction_state(connection)
    for wallet_id,units in bundle_holds.items():held[wallet_id]+=units
    for w in wallets.values():
        origin=initial[w['id']]
        if len(origin)!=1 or origin[0]['units']!=w['initial_units'] or origin[0]['case_id']!=w['source_case_id'] or origin[0]['store_id']!=w['issuer_store_id']:
            raise ValueError('权益发行原始记录不一致')
        if sums[w['id']]!=w['balance_units'] or held[w['id']]!=w['reserved_units'] or not 0<=w['reserved_units']<=w['balance_units']<=w['initial_units']+w.get('correction_units',0):
            raise ValueError('权益单位余额或消费/退款占额不守恒')
        if w['source_kind']=='purchase' and origin[0]['cash_id']!=w['cash_id']:raise ValueError('权益购买批次与原始现金不符')
    for original_id,children in by_original.items():
        original=entries.get(original_id)
        if not original:raise ValueError('权益更正或兑换原记录不存在')
        reversed_units=sum(e['units'] for e in children if e['purpose']=='reverse')
        refunded_units=sum(-e['units'] for e in children if e['purpose']=='refund')
        if reversed_units>abs(original['units']) or refunded_units>abs(original['units']):raise ValueError('权益原单被超额冲正或退款')
        exchanged=[e for e in children if e['purpose']=='exchange_in']
        if exchanged:
            target=exchanged[0];target_rule=rules[wallets[target['wallet_id']]['rule_id']]
            if len(exchanged)!=1 or original['purpose']!='exchange_out' or target['units']*target_rule['exchange_points_per_unit']!=-original['units']:
                raise ValueError('积分兑换与冻结兑换率不守恒')
    postings=defaultdict(list)
    for p in rows('benefit_settlements'):postings[p['entry_id']].append(p)
    for e in entries.values():
        rule=rules[wallets[e['wallet_id']]['rule_id']]
        expected=e['units']*(rule['sale_cents_per_unit'] if e['purpose'] in {'purchase','refund'} else rule['settlement_cents_per_unit']) if e['purpose'] in {'purchase','refund','capture','reverse'} else 0
        actual=postings.pop(e['id'],[])
        if expected:
            if len(actual)!=2 or {p['side']:p['amount_cents'] for p in actual}!={'center':expected,'store':-expected} or any(p['store_id']!=e['store_id'] for p in actual):
                raise ValueError('权益内部往来不配对或偏离冻结结算价')
        elif actual:raise ValueError('零结算权益出现额外内部往来')
    if postings:raise ValueError('权益往来来源不存在')
    payment_ids=set();captures=defaultdict(int)
    for p in rows('benefit_payment_links'):
        e=entries.get(p['entry_id']);r=reservations.get(p['reservation_id'])
        if not e or not r or e['purpose'] not in {'capture','reverse'} or e['wallet_id']!=r['wallet_id'] or e['case_id']!=p['case_id'] or e['store_id']!=p['store_id'] or p['amount_cents']!=e['credit_cents']:
            raise ValueError('权益业务抵扣与原核销/占额关系不符')
        payment_ids.add(e['id'])
        if e['purpose']=='capture':
            if -e['units']!=r['units'] or e['credit_cents']!=r['credit_cents']:raise ValueError('权益实际核销偏离原占额')
            captures[r['id']]+=1
    if any((r['status']=='captured')!=(captures[r['id']]==1) for r in reservations.values()):raise ValueError('权益占额核销状态与单次支付不符')
    if payment_ids!={e['id'] for e in entries.values() if e['purpose'] in {'capture','reverse'}}:raise ValueError('权益核销缺少业务抵扣关联')
    return {'verified_benefit_wallets':len(wallets),'verified_benefit_entries':len(entries)}
