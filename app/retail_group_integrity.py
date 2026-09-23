"""Read-only validation of retail original allocations and pending liabilities."""
import json
from collections import defaultdict


def validate_retail_group(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'retail_group_'+name for name in ('eligibility','scopes','decisions','wallets','plans','tenders','units','allocations','reservations','captures','closures','returns','return_parts','restores','settlements','cash_allocations')}
    if not required.intersection(names):return {'verified_retail_group_plans':0,'verified_retail_group_returns':0}
    if not required<=names:raise ValueError('精品集团支付表不完整')
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);keys=[x[0] for x in cursor.description]
        return [dict(zip(keys,r)) for r in cursor]
    def keyed(name):return {r['id']:r for r in rows(name)}
    def vector(r):return tuple(r[k] for k in ('credit_cents','consideration_cents','settlement_cents'))
    def add(a,b):return tuple(x+y for x,y in zip(a,b))
    def sumv(rs):
        out=(0,0,0)
        for r in rs:out=add(out,vector(r))
        return out
    def bounded(value,cap):return all(0<=x<=y for x,y in zip(value,cap))
    cases=keyed('flow_cases');files=keyed('flow_files');rules=keyed('benefit_rules');wallets=keyed('benefit_wallets');entries=keyed('benefit_entries')
    group_entries=keyed('group_entries');payments=keyed('flow_payment_links');lines=keyed('retail_lines');dispatches=keyed('retail_dispatches');postings=keyed('retail_return_postings')
    eligibility=keyed('retail_group_eligibility');decisions=keyed('retail_group_decisions');bindings=keyed('retail_group_wallets');plans=keyed('retail_group_plans');tenders=keyed('retail_group_tenders')
    units=keyed('retail_group_units');allocations=keyed('retail_group_allocations');reservations=keyed('retail_group_reservations');captures=keyed('retail_group_captures')
    returns=keyed('retail_group_returns');parts=keyed('retail_group_return_parts');restores=keyed('retail_group_restores');cash_allocations=keyed('retail_group_cash_allocations')
    decisions_by={d['eligibility_id']:d for d in decisions.values()};bindings_by={b['wallet_id']:b for b in bindings.values()};captures_by={c['tender_id']:c for c in captures.values()}
    scopes=rows('retail_group_scopes');closures={r['tender_id']:r for r in rows('retail_group_closures')}
    def proof(case_id,file_id,actor=None):
        case=cases.get(case_id);asset=files.get(file_id)
        # Upload and business confirmation are distinct original facts. An
        # authorized colleague may confirm against the same uploaded original.
        if not case or not asset or asset['case_id']!=case_id or asset['store_id']!=case['store_id'] or asset['generated']:raise ValueError('精品集团本店原单与上传原件关联不符')
    def same_store(*rs):
        if any(r is None for r in rs) or len({r['store_id'] for r in rs})!=1:raise ValueError('精品集团原账发生跨店关联')
    for e in eligibility.values():
        rule=rules.get(e['rule_id']);case=cases.get(e['case_id'])
        if not rule or not case or rule['issuer_store_id']!=e['issuer_store_id'] or case['store_id']!=e['issuer_store_id'] or case['kind']!='retail_group_rule' or case['flow_version']!=2 or e['partial_return_mode']!='accumulate_original_unit' or e['expiry_mode']!='original_expiry' or e['pending_claim_expiry']!='none':raise ValueError('精品权益冻结商品规则不一致')
        proof(e['case_id'],e['evidence_id'],e['requested_by'])
        decision=decisions_by.get(e['id'])
        if decision:
            proof(e['case_id'],decision['evidence_id'],decision['actor_id'])
            if decision['approved'] and (decision['actor_id']==e['requested_by'] or case['state']!='completed'):raise ValueError('精品商品用途未获独立批准')
        if not any(s['eligibility_id']==e['id'] for s in scopes):raise ValueError('精品权益缺少明确商品范围')
    for binding in bindings.values():
        wallet=wallets.get(binding['wallet_id']);e=eligibility.get(binding['eligibility_id']);decision=decisions.get(binding['decision_id']);origin=entries.get(binding['origin_id'])
        if not wallet or not e or not decision or not decision['approved'] or decision['eligibility_id']!=e['id'] or wallet['rule_id']!=e['rule_id'] or not origin or origin['wallet_id']!=wallet['id'] or origin['purpose'] not in {'purchase','grant','exchange_in'} or origin['actor_id']!=binding['actor_id'] or str(origin['occurred_at'])<str(decision['occurred_at']):raise ValueError('商品适用必须在原批次发行时冻结，不能重标旧钱包')
    for wallet in wallets.values():
        e=next((e for e in eligibility.values() if e['rule_id']==wallet['rule_id']),None)
        if e and (not decisions_by.get(e['id'],{}).get('approved') or wallet['id'] not in bindings_by):raise ValueError('新商品权益发行缺少批准或发行冻结来源')
    for plan in plans.values():
        case=cases.get(plan['case_id']);same_store(plan,case)
        if case['kind']!='retail' or case['flow_version']!=2:raise ValueError('集团混合付款只可绑定详细精品原单')
        proof(case['id'],plan['evidence_id'],plan['actor_id'])
        if files[plan['evidence_id']]['category']!='authorization':raise ValueError('集团付款缺少明确客户授权')
        plan_tenders=[t for t in tenders.values() if t['plan_id']==plan['id']]
        if sum(t['credit_cents'] for t in plan_tenders)!=case['amount_cents']:raise ValueError('冻结支付总额偏离精品原报价')
        for line in (l for l in lines.values() if l['case_id']==case['id']):
            for component,key in [('goods','goods_cents'),('installation','installation_cents')]:
                assigned=sum(a['credit_cents'] for a in allocations.values() if a['line_id']==line['id'] and a['component']==component)
                if assigned!=line[key]:raise ValueError('原行商品或安装支付分摊不守恒')
    for tender in tenders.values():
        plan=plans.get(tender['plan_id']);same_store(tender,plan)
        selected=[u for u in units.values() if u['tender_id']==tender['id']]
        if sumv(selected)!=vector(tender):raise ValueError('原支付批次单位金额不守恒')
        if tender['kind'] in {'coupon','package'}:
            if sorted(u['sequence'] for u in selected)!=list(range(1,tender['units']+1)):raise ValueError('券或套餐原整数单位不完整')
        elif len(selected)!=1:raise ValueError('本金赠金或现金分账出现重复原额度')
        if tender['wallet_id']:
            wallet=wallets.get(tender['wallet_id']);binding=bindings_by.get(tender['wallet_id']);rule=rules[wallet['rule_id']] if wallet else None
            if not wallet or not binding or wallet['member_id']!=plan['member_id'] or binding['eligibility_id']!=tender['eligibility_id'] or rule['kind']!=tender['kind'] or wallet['expires_on']!=tender['expires_on']:raise ValueError('付款偏离原会员批次或冻结有效期')
            expected=(rule['credit_cents_per_unit']*tender['units'],(rule['sale_cents_per_unit'] if wallet['source_kind']=='purchase' else 0)*tender['units'],rule['settlement_cents_per_unit']*tender['units'])
            if vector(tender)!=expected:raise ValueError('付款 C/P/S 与原发行批次不一致')
        elif vector(tender)!=(tender['credit_cents'],)*3:raise ValueError('现金或本金份额被混记为优惠')
    for unit in units.values():
        tender=tenders.get(unit['tender_id']);same_store(unit,tender)
        cells=[a for a in allocations.values() if a['unit_id']==unit['id']]
        if sumv(cells)!=vector(unit):raise ValueError('原核销单位的逐行分摊不守恒')
        if tender['kind'] in {'coupon','package'} and vector(unit)!=tuple(x//tender['units'] for x in vector(tender)):raise ValueError('原券或套餐单位价值被改写')
    for allocation in allocations.values():
        unit=units.get(allocation['unit_id']);line=lines.get(allocation['line_id']);same_store(allocation,unit,line)
        tender=tenders[unit['tender_id']];plan=plans[tender['plan_id']]
        if line['case_id']!=plan['case_id']:raise ValueError('原支付分摊关联了其它精品单')
        if tender['wallet_id'] and not any(s['eligibility_id']==tender['eligibility_id'] and s['store_id']==plan['store_id'] and s['item_id']==line['item_id'] and s['unit']==line['unit'] and s['component']==allocation['component'] and (s['component']=='goods' or (s['work_item_id']==line['work_item_id'] and s['work_code']==line['work_code'])) for s in scopes):raise ValueError('权益抵扣超出冻结商品用途、原单位或原作业')
        if not bounded(sumv(p for p in parts.values() if p['allocation_id']==allocation['id']),vector(allocation)):raise ValueError('原行支付被超额退回')
    principal_res=keyed('group_reservations');benefit_res=keyed('benefit_reservations')
    for reservation in reservations.values():
        tender=tenders.get(reservation['tender_id']);same_store(reservation,tender)
        source=(principal_res if reservation['principal_id'] else benefit_res).get(reservation['principal_id'] or reservation['benefit_id'])
        if not source or source['case_id']!=plans[tender['plan_id']]['case_id']:raise ValueError('精品占额偏离原业务')
        amount=source['amount_cents'] if reservation['principal_id'] else source['credit_cents']
        if amount!=tender['credit_cents']:raise ValueError('集团实际占额偏离原授权金额')
        plan=plans[tender['plan_id']]
        if source['store_id']!=plan['store_id'] or (reservation['principal_id'] and source['member_id']!=plan['member_id']) or (reservation['benefit_id'] and source['wallet_id']!=tender['wallet_id']):raise ValueError('精品占额引用了其它会员或原批次')
        expected='captured' if tender['id'] in captures_by else 'released' if tender['id'] in closures else 'reserved'
        if source['status']!=expected:raise ValueError('精品原占额状态与实际核销或释放不符')
    for captured in captures.values():
        tender=tenders.get(captured['tender_id']);reservation=reservations.get(captured['reservation_id']);same_store(captured,tender,reservation)
        source=(group_entries if captured['principal_id'] else entries).get(captured['principal_id'] or captured['benefit_id'])
        if not source or source['purpose']!='capture' or source['case_id']!=plans[tender['plan_id']]['case_id'] or reservation['tender_id']!=tender['id']:raise ValueError('实际核销没有本单原占额来源')
        credit=-source['amount_cents'] if captured['principal_id'] else source['credit_cents']
        if credit!=tender['credit_cents'] or tender['id'] in closures:raise ValueError('实际核销偏离原授权或同时被取消')
        plan=plans[tender['plan_id']]
        if source['store_id']!=plan['store_id'] or (captured['principal_id'] and source['member_id']!=plan['member_id']) or (captured['benefit_id'] and source['wallet_id']!=tender['wallet_id']):raise ValueError('实际精品核销偏离原会员批次')
    for record in returns.values():
        plan=plans.get(record['plan_id']);posting=postings.get(record['posting_id']);same_store(record,plan,posting)
        if posting['case_id']!=plan['case_id']:raise ValueError('原支付退回没有本单实际退货')
        dispatch=dispatches[posting['dispatch_id']]
        for component,expected in [('goods',posting['goods_cents']),('installation',posting['installation_cents']-posting['retained_cents'])]:
            selected=[p for p in parts.values() if p['return_id']==record['id'] and allocations[p['allocation_id']]['component']==component]
            if sum(p['credit_cents'] for p in selected)!=expected or any(allocations[p['allocation_id']]['line_id']!=dispatch['line_id'] for p in selected):raise ValueError('实际退货对应原支付分摊不守恒或误退保留安装费')
    plan_cases={p['case_id'] for p in plans.values()}
    if {p['id'] for p in postings.values() if p['case_id'] in plan_cases}!={r['posting_id'] for r in returns.values()}:
        raise ValueError('精品实际退货缺少原支付份额与非现金负债记录')
    for part in parts.values():
        record=returns.get(part['return_id']);allocation=allocations.get(part['allocation_id']);same_store(part,record,allocation)
        tender=tenders[units[allocation['unit_id']]['tender_id']]
        if part['capture_id']!=captures_by.get(tender['id'],{}).get('id'):raise ValueError('原退负债缺少原核销批次或引用了其它批次')
    for unit in units.values():
        back=[r for r in restores.values() if r['unit_id']==unit['id']]
        returned=sumv(p for p in parts.values() if allocations[p['allocation_id']]['unit_id']==unit['id'] and p['capture_id'])
        if not bounded(sumv(back),returned):raise ValueError('原单位恢复超过实际退回额度')
        tender=tenders[unit['tender_id']]
        if tender['kind'] in {'coupon','package'} and back and (len(back)!=1 or vector(back[0])!=vector(unit) or returned!=vector(unit)):raise ValueError('未凑整权益被恢复或重复还整份')
    for restored in restores.values():
        unit=units.get(restored['unit_id']);captured=captures.get(restored['capture_id']);same_store(restored,unit,captured)
        tender=tenders[unit['tender_id']]
        source=(group_entries if restored['principal_id'] else entries).get(restored['principal_id'] or restored['benefit_id'])
        if not source or source['purpose']!='reverse' or source['original_id']!=(captured['principal_id'] or captured['benefit_id']) or captured['tender_id']!=tender['id']:raise ValueError('原权益恢复偏离原核销来源')
        amount=source['amount_cents'] if restored['principal_id'] else -source['credit_cents']
        if amount!=restored['credit_cents']:raise ValueError('原权益实际恢复与待恢复负债抵消不符')
        plan=plans[tender['plan_id']]
        if source['store_id']!=plan['store_id'] or source['case_id']!=plan['case_id']:raise ValueError('原恢复偏离本店原精品单')
        if tender['kind']=='principal':expected=(amount,amount,amount)
        else:
            wallet=wallets[tender['wallet_id']];rule=rules[wallet['rule_id']]
            if amount%rule['credit_cents_per_unit']:raise ValueError('原恢复出现非整数权益单位')
            count=amount//rule['credit_cents_per_unit']
            expected=(amount,count*(rule['sale_cents_per_unit'] if wallet['source_kind']=='purchase' else 0),count*rule['settlement_cents_per_unit'])
        if vector(restored)!=expected:raise ValueError('原恢复对冲没有使用原冻结 C/P/S')
        proof(plans[tender['plan_id']]['case_id'],restored['evidence_id'],restored['actor_id'])
    settlements=rows('retail_group_settlements')
    for kind,records in [('return_part_id',parts),('restore_id',restores)]:
        for r in records.values():
            expected=r['settlement_cents']*(1 if kind=='return_part_id' else -1)
            if kind=='return_part_id' and not r['capture_id']:expected=0
            actual=[s for s in settlements if s[kind]==r['id']]
            if expected:
                if len(actual)!=2 or {s['side']:s['amount_cents'] for s in actual}!={'center':expected,'store':-expected} or any(s['store_id']!=r['store_id'] for s in actual):raise ValueError('待恢复及整份恢复内部结算抵消不守恒')
            elif actual:raise ValueError('尚未核销或零结算份额产生额外内部往来')
    for allocation in cash_allocations.values():
        source=payments.get(allocation['payment_link_id']);cell=allocations.get(allocation['allocation_id']);same_store(allocation,source,cell)
        tender=tenders[units[cell['unit_id']]['tender_id']]
        if source['case_id']!=plans[tender['plan_id']]['case_id'] or (tender['kind']!='cash' and tender['id'] not in closures):raise ValueError('实际现金被分配给未释放集团支付份额')
        if allocation['amount_cents']>0:
            if source['direction']!='in':raise ValueError('现金原分摊方向错误')
        else:
            original=cash_allocations.get(allocation['original_id'])
            if not original or original['amount_cents']<=0 or original['allocation_id']!=cell['id'] or source['direction']!='out' or source['original_id']!=original['payment_link_id']:raise ValueError('现金退款偏离原收款原商品份额')
    for payment in payments.values():
        if not any(p['case_id']==payment['case_id'] for p in plans.values()):continue
        assigned=sum(r['amount_cents'] for r in cash_allocations.values() if r['payment_link_id']==payment['id'])
        if assigned!=payment['amount_cents']*(1 if payment['direction']=='in' else -1):raise ValueError('精品实际现金缺少原行分摊或被重复计账')
    for a in allocations.values():
        money=[r for r in cash_allocations.values() if r['allocation_id']==a['id']]
        original_paid=sum(r['amount_cents'] for r in money if r['amount_cents']>0)
        out=-sum(r['amount_cents'] for r in money if r['amount_cents']<0)
        reduced=sum(p['credit_cents'] for p in parts.values() if p['allocation_id']==a['id'])
        if original_paid>a['credit_cents'] or out>max(0,original_paid-(a['credit_cents']-reduced)):raise ValueError('原现金份额超收或超出实退原行退款')
    for original in cash_allocations.values():
        if original['amount_cents']>0 and original['amount_cents']+sum(r['amount_cents'] for r in cash_allocations.values() if r['original_id']==original['id'])<0:raise ValueError('同笔原现金份额被重复退款')
    return {'verified_retail_group_plans':len(plans),'verified_retail_group_returns':len(returns),'verified_retail_group_restores':len(restores)}
