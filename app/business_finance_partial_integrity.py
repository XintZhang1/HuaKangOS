"""Prove the only allowed gross-cash/net-allocation difference: frozen real refunds."""
import json
from datetime import datetime


def validate_partial_corrections_sqlite(connection):
    from .business_finance_partial_corrections import SOURCE_TABLES
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def rows(name):
        c=connection.execute('SELECT * FROM '+name);keys=[x[0] for x in c.description]
        return [dict(zip(keys,r)) for r in c]
    def by(name):return {r['id']:r for r in rows(name)}
    def check(ok,message):
        if not ok:raise ValueError('原退款切片更正恢复：'+message)
    orders={r['case_id']:r for r in rows('business_finance_orders')} if 'business_finance_orders' in names else {}
    partial_orders={k for k,v in orders.items() if json.loads(v['values']).get('correction_basis_version')==2}
    if not set(SOURCE_TABLES)&names:
        check(not partial_orders,'已有新版更正申请但原退款切片表丢失')
        return {'batch_retained':{},'partial_case_ids':set(),'verified_finance_partial_corrections':0}
    check(set(SOURCE_TABLES)<=names,'原退款切片表不完整')
    bases=by(SOURCE_TABLES[0]);slices=by(SOURCE_TABLES[1]);payments=by('flow_payment_links');cash=by('cash_entries');cases=by('flow_cases')
    corrections={r['case_id']:r for r in rows('business_finance_corrections')};batches=by('business_finance_cash_batches');allocations=rows('business_finance_cash_allocations')
    previous_cash={batches[c['corrected_batch_id']]['cash_id']:c for c in corrections.values() if c['corrected_batch_id']}
    by_case={b['case_id']:b for b in bases.values()};retained={}
    check(partial_orders==set(by_case),'新版申请与不可变原退款依据不对应')
    check(all(s['basis_id'] in bases for s in slices.values()),'存在无宿主原退款切片')
    def same(*rr):return all(r and r['store_id']==rr[0]['store_id'] for r in rr)
    def before(stamp,limit):return datetime.fromisoformat(stamp)<=datetime.fromisoformat(limit)
    def actual_refunds(link_ids,limit):
        return {p['id']:p for p in payments.values() if p['original_id'] in link_ids and cash[p['cash_id']]['category']!='business_finance_correction_reverse' and before(cash[p['cash_id']]['created_at'],limit)}
    for basis in bases.values():
        row=cases.get(basis['case_id']);order=orders.get(basis['case_id']);original=cash.get(basis['original_cash_id']);values=json.loads(order['values']) if order else {}
        check(same(basis,row,order,original) and order['purpose']=='correction' and values.get('allocation_basis')=='remaining_after_refunds','宿主、门店或新版原款解释缺失')
        check((basis['original_cash_id'],basis['original_amount_cents'],basis['corrected_amount_cents'],basis['refunded_cents'])==(values.get('original_cash_id'),original['amount_cents'],values.get('amount_cents'),values.get('refunded_cents')),'冻结总额偏离申请或原款')
        check(original['direction']=='in' and original['approval_state']=='approved' and basis['original_amount_cents']>=basis['refunded_cents']>0 and basis['corrected_amount_cents']>=basis['refunded_cents'],'原款方向或已退款下限异常')
        prior_correction=previous_cash.get(original['id']);prior=by_case.get(prior_correction['case_id']) if prior_correction else None
        check(basis['previous_id']==(prior['id'] if prior else None),'前版原款切片关联断裂')
        original_links={p['id']:p for p in payments.values() if p['cash_id']==original['id']}
        inherited={s['refund_payment_id']:payments[s['refund_payment_id']] for s in slices.values() if prior and s['basis_id']==prior['id']}
        check(sum(p['amount_cents'] for p in original_links.values())+sum(p['amount_cents'] for p in inherited.values())==original['amount_cents'],'原总款与剩余分配及继承退款不守恒')
        expected={**inherited,**actual_refunds(original_links,basis['created_at'])}
        own=[s for s in slices.values() if s['basis_id']==basis['id']]
        check({s['refund_payment_id'] for s in own}==set(expected) and len(own)==len(expected),'冻结切片没有完整保留已发生原退款')
        check(sum(s['amount_cents'] for s in own)==basis['refunded_cents'],'累计已退款与原切片不守恒')
        for s in own:
            refund=payments.get(s['refund_payment_id']);old=payments.get(s['original_payment_id']);fact=cash.get(refund['cash_id']) if refund else None;source=cases.get(s['source_case_id'])
            check(same(s,basis,refund,old,fact,source) and source['customer_id']==row['customer_id'] and refund['original_id']==old['id'] and old['direction']=='in' and refund['direction']=='out' and refund['case_id']==old['case_id']==source['id'] and refund['account_id']==old['account_id'],'原实际退款串单、串店或改账户')
            check(refund['amount_cents']==s['amount_cents']>0 and fact['direction']=='out' and fact['approval_state']=='approved' and fact['amount_cents']==refund['amount_cents'] and fact['category']!='business_finance_correction_reverse','误记冲正伪装成已实际退款')
        check(sum(v['amount_cents'] for v in values['allocations'])==basis['corrected_amount_cents']-basis['refunded_cents'],'正确总款与剩余逐单分配不守恒')
        fix=corrections.get(basis['case_id'])
        check((order['status']=='completed')==bool(fix),'执行状态与追加更正不对应')
        if not fix:continue
        reverse=batches.get(fix['reversing_batch_id']);record=batches.get(fix['corrected_batch_id'])
        check(same(basis,fix,reverse,record) and fix['original_cash_id']==original['id'] and reverse['amount_cents']==basis['original_amount_cents'] and record['amount_cents']==basis['corrected_amount_cents'],'正反现金总额未按冻结原款更正')
        check(set(actual_refunds(original_links,cash[reverse['cash_id']]['created_at']))<=set(expected),'实际执行忽略了迟到原退款')
        current_refunds=actual_refunds(original_links,basis['created_at'])
        remaining={key:p['amount_cents']-sum(r['amount_cents'] for r in current_refunds.values() if r['original_id']==key) for key,p in original_links.items()}
        check(all(v>=0 for v in remaining.values()),'原退款超过分配')
        reversal_links=[payments[a['payment_link_id']] for a in allocations if a['batch_id']==reverse['id']]
        check({p['original_id'] for p in reversal_links}=={key for key,v in remaining.items() if v} and len(reversal_links)==sum(v>0 for v in remaining.values()),'剩余原分配冲回数量错误')
        for p in reversal_links:
            old=original_links[p['original_id']]
            check(p['direction']=='out' and p['cash_id']==reverse['cash_id'] and p['case_id']==old['case_id'] and p['account_id']==old['account_id'] and p['amount_cents']==remaining[old['id']],'冲回覆盖了已实际退回的原分配')
        for batch in (reverse,record):
            own_allocations=[a for a in allocations if a['batch_id']==batch['id']]
            check(batch['case_id']==basis['case_id'] and batch['amount_cents']==sum(a['amount_cents'] for a in own_allocations)+basis['refunded_cents'],'批次差额不是完整历史退款切片')
            retained[batch['id']]=basis['refunded_cents']
    return {'batch_retained':retained,'partial_case_ids':set(by_case),'verified_finance_partial_corrections':len(bases)}
