"""Restore validation for original bundle principal and gift correction linkage."""
import json
from collections import defaultdict


def bundle_correction_state(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_finance_bundle_corrections' not in names:return {},{},set()
    def rows(name):
        cur=connection.execute('SELECT * FROM '+name);keys=[r[0] for r in cur.description]
        return {v['id']:v for v in (dict(zip(keys,r)) for r in cur)}
    fixes=rows('business_finance_bundle_corrections');requests=rows('business_finance_stored_correction_requests')
    parts=rows('business_finance_bundle_correction_components');postings=rows('business_finance_bundle_correction_postings')
    deltas=defaultdict(int);held=defaultdict(int)
    for fix in fixes.values():
        request=requests.get(fix['request_id'])
        if not request:raise ValueError('组合更正缺少原财务申请')
        if request['status']=='applied':deltas[fix['purchase_id']]+=fix['corrected_shares']-fix['original_shares']
        if request['status']=='reserved':
            for part in parts.values():
                if part['correction_id']==fix['id']:held[part['wallet_id']]+=max(0,-part['delta_units'])
    return dict(deltas),dict(held),{p['benefit_entry_id'] for p in postings.values()}


def validate_bundle_corrections_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'business_finance_bundle_corrections','business_finance_bundle_correction_components','business_finance_bundle_correction_postings'}
    if not required&names:
        has_entries='benefit_entries' in names and connection.execute("SELECT 1 FROM benefit_entries WHERE purpose='correction' LIMIT 1").fetchone()
        has_orders='business_finance_orders' in names and any(json.loads(r[0]).get('bundle_purchase_id') for r in connection.execute('SELECT "values" FROM business_finance_orders WHERE purpose=\'stored_correction\''))
        if has_entries or has_orders:raise ValueError('组合更正事实存在，但原组合关联表缺失')
        return {'verified_finance_bundle_corrections':0}
    if not required<=names:raise ValueError('组合更正表不完整')
    def rows(name):
        cur=connection.execute('SELECT * FROM '+name);keys=[r[0] for r in cur.description]
        return {v['id']:v for v in (dict(zip(keys,r)) for r in cur)}
    def check(value,message):
        if not value:raise ValueError('原组合误记更正恢复：'+message)
    def same(*records):return all(r and r['store_id']==records[0]['store_id'] for r in records)
    fixes=rows('business_finance_bundle_corrections');requests=rows('business_finance_stored_correction_requests')
    parts=rows('business_finance_bundle_correction_components');posts=rows('business_finance_bundle_correction_postings')
    purchases=rows('recharge_bundle_purchases');components=rows('recharge_bundle_components');rules=rows('recharge_bundle_rules');ruleparts=rows('recharge_bundle_rule_components')
    wallets=rows('benefit_wallets');entries=rows('benefit_entries');orders={o['case_id']:o for o in rows('business_finance_orders').values()}
    known=set();covered=set()
    for fix in fixes.values():
        request=requests.get(fix['request_id']);purchase=purchases.get(fix['purchase_id']);rule=rules.get(fix['rule_id']);order=orders.get(request['case_id']) if request else None
        values=json.loads(order['values']) if order else {}
        check(same(fix,request,purchase,order) and rule and purchase['rule_id']==rule['id'] and request['source_kind']=='member' and request['topup_id']==purchase['principal_entry_id'] and request['member_id']==purchase['member_id'],'申请未追同店原组合本金')
        check(fix['original_shares']*rule['principal_cents_per_share']==request['original_amount_cents'] and fix['corrected_shares']*rule['principal_cents_per_share']==request['corrected_amount_cents'],'本金更正没有按原完整份数计算')
        check(all(values.get(k)==fix[v] for k,v in [('bundle_purchase_id','purchase_id'),('bundle_rule_id','rule_id'),('original_shares','original_shares'),('corrected_shares','corrected_shares')]),'组合申请冻结内容偏离不可变关联')
        own=[p for p in parts.values() if p['correction_id']==fix['id']];original=[p for p in components.values() if p['purchase_id']==purchase['id']]
        check(len(own)==len(original) and {p['component_id'] for p in own}=={p['id'] for p in original},'没有完整同步原赠品种类')
        frozen={p['component_id']:p for p in values.get('bundle_components',[])}
        check(set(frozen)=={p['component_id'] for p in own},'申请遗漏或新增原权益组件')
        for part in own:
            origin=components[part['component_id']];rulepart=ruleparts[origin['rule_component_id']];wallet=wallets.get(part['wallet_id'])
            delta=rulepart['units_per_share']*(fix['corrected_shares']-fix['original_shares'])
            check(same(fix,part,origin) and wallet and part['wallet_id']==origin['wallet_id'] and part['grant_entry_id']==origin['grant_entry_id'] and wallet['member_id']==purchase['member_id'] and part['units_per_share']==rulepart['units_per_share'] and part['delta_units']==delta and part['expires_on']==wallet['expires_on'],'原单位差额、钱包或冻结到期日不符')
            check(all(frozen[part['component_id']].get(k)==part[k] for k in ('wallet_id','grant_entry_id','units_per_share','delta_units','expires_on')),'组件事实偏离冻结申请')
            applied=[p for p in posts.values() if p['component_id']==part['id']]
            check(len(applied)==(1 if delta and request['status']=='applied' else 0),'权益更正次数与财务执行状态不符')
            covered.add(part['id'])
            if not applied:continue
            post=applied[0];entry=entries.get(post['benefit_entry_id'])
            check(same(fix,post,entry) and entry['wallet_id']==wallet['id'] and entry['original_id']==origin['grant_entry_id'] and entry['case_id']==request['case_id'] and entry['purpose']=='correction' and entry['units']==delta and entry['credit_cents']==0 and entry['cash_id'] is None,'权益差额未追原赠送或伪造现金／营业核销')
            known.add(entry['id'])
    check(covered==set(parts),'存在无原申请的权益组件')
    check(all(p['component_id'] in covered for p in posts.values()),'存在无原组件的权益更正流水')
    check(known=={e['id'] for e in entries.values() if e['purpose']=='correction'},'存在绕过原组合批准的权益更正')
    check({f['request_id'] for f in fixes.values()}=={r['id'] for r in requests.values() if json.loads(orders[r['case_id']]['values']).get('bundle_purchase_id')},'本金更正绕过原组合权益适配')
    for wallet in wallets.values():
        check(wallet.get('correction_units',0)==sum(e['units'] for e in entries.values() if e['wallet_id']==wallet['id'] and e['purpose']=='correction'),'原权益累计更正缓存不守恒')
    return {'verified_finance_bundle_corrections':len(fixes)}
