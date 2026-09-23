"""Read-only SQLite restore proof of original procurement funding and allocations."""
from collections import defaultdict
from datetime import datetime,date
import json
from .procurement_prepayment_sources import SOURCE_FIELDS,digest

TABLES=('procurement_prepayment_facilities','procurement_prepayment_requests','procurement_prepayment_decisions',
    'procurement_prepayment_disbursements','procurement_payment_allocations')


def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    found=set(TABLES)&names
    def fail(message):raise ValueError('采购预付款恢复检查：'+message)
    if not found:
        if 'flow_events' in names and connection.execute("SELECT 1 FROM flow_events WHERE action LIKE 'procurement_%' AND detail LIKE '%prepayment_sources%' LIMIT 1").fetchone():fail('原事件已有预付款，但全部来源表缺失')
        return {'verified_procurement_prepayments':0,'verified_procurement_payment_allocations':0}
    if found!=set(TABLES):fail('预付款来源表不完整')
    for table,fields in SOURCE_FIELDS.items():
        columns={r[1] for r in connection.execute('PRAGMA table_info('+table+')')}
        expected=set(fields)|({'status','version','updated_at'} if table=='procurement_prepayment_requests' else set())
        if not expected<=columns:fail('预付款来源字段不完整：'+table)
    def rows(name):
        q=connection.execute('SELECT * FROM '+name);keys=[r[0] for r in q.description];return [dict(zip(keys,r)) for r in q]
    def by(name):return {r['id']:r for r in rows(name)}
    def same(*args):return all(args) and len({r['store_id'] for r in args})==1
    def timestamp(r):return datetime.fromisoformat(r['created_at'])
    facilities,requests,decisions,disbursements,allocations=[by(n) for n in TABLES]
    originals=dict(zip(TABLES,(facilities,requests,decisions,disbursements,allocations)))
    cases=by('flow_cases');orders=by('procurement_orders');files=by('flow_files');payments=by('procurement_payments')
    receipts=by('procurement_receipts');returns=by('procurement_return_postings');cash=by('cash_entries');accounts=by('flow_accounts')
    seen={name:set() for name in TABLES}
    for event in rows('flow_events'):
        source=json.loads(event['detail']).get('prepayment_sources',{})
        if not source:continue
        if not event['action'].startswith('procurement_'):fail('原预付款来源被挂到其他流程动作')
        for table,entries in source.items():
            if table not in SOURCE_FIELDS:fail('未知预付款来源版本')
            for entry in entries:
                record=originals[table].get(entry['id'])
                if not record or not same(event,record) or entry['id'] in seen[table] or digest(table,record)!=entry['digest']:fail('原业务事件与预付款事实缺失、重复或被改写')
                if event['actor_id']!=record.get('actor_id',record.get('requested_by')):fail('原事件经办人与本次新增事实不一致')
                if table in TABLES[:2] and event['action']!='procurement_prepay_request':fail('原申请缺少明确申请动作')
                if table==TABLES[3] and event['action']!='procurement_prepay_pay':fail('实际预付款缺少原登记动作')
                if table==TABLES[2]:
                    allowed={'procurement_prepay_'+record['action']}
                    if record['action']=='cancel':allowed|={'procurement_close_receiving','procurement_return_dispatch'}
                    if event['action'] not in allowed:fail('原批准或结束决定不属于对应办理动作')
                case_id=record.get('case_id') or (record['id'] if table==TABLES[0] else requests.get(record['request_id'],{}).get('case_id'))
                if event['case_id']!=case_id:fail('预付款事实不属于原业务事件')
                seen[table].add(entry['id'])
    if any(seen[table]!=set(originals[table]) for table in TABLES):fail('预付款事实缺少原动作事件')
    def proof(key,case,financial=False):
        f=files.get(key)
        if not same(f,case) or f['case_id']!=case['id'] or f['generated']:fail('依据不是本店原采购真实凭据')
        if financial and f['category'] not in {'receipt','procurement_contract','signed_contract','invoice'}:fail('原申请或批准缺少财务依据')
    for f in facilities.values():
        case=cases.get(f['id']);order=orders.get(f['id'])
        if not same(f,case,order) or case['kind']!='procurement' or case['flow_version']!=3:fail('预付范围不是原店已批准采购v3')
        proof(f['evidence_id'],case,True)
        if not any(r['case_id']==f['id'] and r['requested_by']==f['actor_id'] and r['evidence_id']==f['evidence_id'] for r in requests.values()):fail('启用依据缺少原申请')
        for p in payments.values():
            if p['case_id']==case['id'] and timestamp(cash[p['cash_id']])<timestamp(f):fail('已实际付款的历史单被重分类为预付款')
    used_payment=set();paid=defaultdict(int)
    for d in disbursements.values():
        r=requests.get(d['request_id']);p=payments.get(d['payment_id']);c=cash.get(p['cash_id']) if p else None
        if not same(d,r,p,c) or p['case_id']!=r['case_id'] or p['direction']!='out' or p['id'] in used_payment:fail('实际预付没有唯一同店原申请和原现金')
        if d['actor_id']!=c['created_by']:fail('实际登记人与原现金不一致')
        approved=[x for x in decisions.values() if x['request_id']==r['id'] and x['action']=='approve']
        if len(approved)!=1 or not timestamp(r)<=timestamp(approved[0])<=timestamp(c)<=timestamp(d):fail('原实际付款未取得先行独立批准')
        if date.fromisoformat(c['business_date'])>date.fromisoformat(r['valid_until']):fail('实际付款使用过期申请')
        if any(x['request_id']==r['id'] and x['action'] in {'reject','cancel','expire'} and timestamp(x)<timestamp(c) for x in decisions.values()):fail('已结束申请被继续付款')
        used_payment.add(p['id']);paid[r['id']]+=p['amount_cents']
        if paid[r['id']]>r['amount_cents']:fail('实际付款超过原申请批准金额')
    for r in requests.values():
        f=facilities.get(r['case_id']);case=cases.get(r['case_id'])
        if not same(r,f,case) or r['amount_cents']<=0:fail('原申请跨店、缺原单或金额无效')
        proof(r['evidence_id'],case,True)
        ds=sorted([d for d in decisions.values() if d['request_id']==r['id']],key=lambda d:d['id'])
        state='pending'
        for d in ds:
            if not same(d,r) or timestamp(d)<timestamp(r):fail('决定错配原申请或时间倒置')
            if d['action'] in {'approve','reject'}:
                if state!='pending' or d['actor_id']==r['requested_by']:fail('决定未独立或重复批准')
                proof(d['evidence_id'],case,True);state='approved' if d['action']=='approve' else 'rejected'
            elif d['action'] in {'cancel','expire'}:
                if state not in {'pending','approved'}:fail('结束决定无有效原未付申请')
                state='cancelled' if d['action']=='cancel' else 'expired'
            else:fail('未知原申请决定')
        if paid[r['id']]==r['amount_cents']:
            if state!='approved':fail('已全额支付原申请被覆盖结束')
            state='paid'
        if state!=r['status'] or (paid[r['id']] and not any(d['action']=='approve' for d in ds)):fail('请求状态与原批准/实际付款不一致')
    if any(d['request_id'] not in requests for d in decisions.values()):fail('决定缺少原申请')
    reversed_by_original=defaultdict(int);applied_payment=defaultdict(int);applied_receipt=defaultdict(int);reversed_return=defaultdict(int)
    for a in sorted(allocations.values(),key=lambda a:a['id']):
        f=facilities.get(a['case_id']);p=payments.get(a['payment_id']);r=receipts.get(a['receipt_id'])
        if not same(a,f,p,r) or p['case_id']!=f['id'] or r['case_id']!=f['id'] or p['direction']!='out':fail('抵用错配原单、原付款或到货批次')
        if a['amount_cents']>0:
            if a['original_id'] is not None or a['return_posting_id'] is not None:fail('正向抵用携带虚假冲回来源')
        elif a['amount_cents']<0:
            original=allocations.get(a['original_id']);ret=returns.get(a['return_posting_id'])
            if not same(a,original,ret) or original['id']>=a['id'] or original['amount_cents']<=0 or original['payment_id']!=p['id'] or original['receipt_id']!=r['id'] or ret['receipt_id']!=r['id'] or ret['case_id']!=f['id']:fail('冲回未指向原抵用和真实原批退货')
            reversed_by_original[original['id']]-=a['amount_cents'];reversed_return[ret['id']]-=a['amount_cents']
            if reversed_by_original[original['id']]>original['amount_cents'] or reversed_return[ret['id']]>ret['value_cents']:fail('原抵用或原退货被重复冲回')
        else:fail('抵用金额不能为零')
        applied_payment[p['id']]+=a['amount_cents'];applied_receipt[r['id']]+=a['amount_cents']
        if min(applied_payment[p['id']],applied_receipt[r['id']])<0:fail('抵用被过度冲回')
    for f in facilities.values():
        case=cases[f['id']];ps=[p for p in payments.values() if p['case_id']==case['id']]
        rs=[r for r in receipts.values() if r['case_id']==case['id']];rets=[r for r in returns.values() if r['case_id']==case['id']]
        net_paid=0
        for p in ps:
            c=cash.get(p['cash_id']);account=accounts.get(p['account_id'])
            if not same(p,case,c,account) or (c['amount_cents'],c['direction'],c['voucher_no'],c['approval_state'])!=(p['amount_cents'],p['direction'],p['reference'],'approved'):fail('实际原现金金额、方向、凭证或账户不一致')
            proof(p['evidence_id'],case)
            if p['direction']=='out':
                refunded=sum(x['amount_cents'] for x in ps if x['original_id']==p['id'])
                if not 0<=applied_payment[p['id']]<=p['amount_cents']-refunded:fail('原付款抵用与退款超过原现金')
            else:
                original=payments.get(p['original_id'])
                if not same(p,original) or original['case_id']!=case['id'] or original['direction']!='out' or original['account_id']!=p['account_id']:fail('退款未沿原实际付款账户')
            net_paid+=p['amount_cents']*(1 if p['direction']=='out' else -1)
        accepted=sum(r['value_cents'] for r in rs)-sum(r['value_cents'] for r in rets)
        for r in rs:
            if not 0<=applied_receipt[r['id']]<=r['value_cents']-sum(x['value_cents'] for x in rets if x['receipt_id']==r['id']):fail('原到货应付被过度抵用')
        if sum(applied_receipt[r['id']] for r in rs)!=min(net_paid,accepted):fail('实际净付款与净验收抵用不完整或不守恒')
        closed=json.loads(case['data']).get('receiving_closed',False)
        commitment=(sum(r['value_cents'] for r in rs) if closed else case['amount_cents'])-sum(r['value_cents'] for r in rets)
        reserved=sum(r['amount_cents']-paid[r['id']] for r in requests.values() if r['case_id']==case['id'] and r['status'] in {'pending','approved'})
        if min(net_paid,commitment)+reserved>commitment:fail('未付原申请占额超出有效约定')
    return {'verified_procurement_prepayments':len(requests),'verified_procurement_payment_allocations':len(allocations)}
