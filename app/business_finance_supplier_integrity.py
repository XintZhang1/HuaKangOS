"""Original supplier receipts, approved holds and actual refunds must reconcile."""
import json


def validate_supplier_refunds_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_finance_supplier_refunds' not in names:return {'verified_finance_supplier_refunds':0}
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);keys=[r[0] for r in cursor.description]
        return {v['id']:v for v in (dict(zip(keys,r)) for r in cursor)}
    def check(ok,message):
        if not ok:raise ValueError('业务财务供应方退款恢复：'+message)
    def same(*records):return all(r and r['store_id']==records[0]['store_id'] for r in records)
    requests=rows('business_finance_supplier_refunds');receivables=rows('business_finance_return_receivables');payments=rows('flow_payment_links');batches=rows('business_finance_cash_batches')
    allocations=rows('business_finance_cash_allocations');cases=rows('flow_cases');orders={o['case_id']:o for o in rows('business_finance_orders').values()};targets=rows('business_finance_return_target_revisions')
    seen=set()
    for request in requests.values():
        order=orders.get(request['case_id']);values=json.loads(order['values']) if order else {};source=receivables.get(request['receivable_id']);original=payments.get(request['original_payment_id'])
        check(same(request,order,source,original) and order['purpose']=='other_return_refund' and original['case_id']==source['case_id'] and original['direction']=='in' and original['original_id'] is None,'退款申请不是本店原供应方实际收款')
        check(request['amount_cents']==values.get('amount_cents') and request['receivable_id']==values.get('receivable_id') and request['original_payment_id']==values.get('original_payment_id') and original['cash_id']==values.get('original_cash_id') and original['account_id']==values.get('original_account_id'),'退款原款或金额偏离冻结申请')
        check({'requested':'draft','reserved':'approved','released':'cancelled','applied':'completed'}.get(request['status'])==order['status'],'退款占额和办理状态不一致')
        batch=batches.get(request['applied_batch_id']);check(bool(batch)==(request['status']=='applied'),'退款状态与真实现金批次不符')
        if batch:
            own=[a for a in allocations.values() if a['batch_id']==batch['id']]
            check(same(request,batch) and batch['case_id']==request['case_id'] and batch['kind']=='supplier_refund' and batch['amount_cents']==request['amount_cents'] and len(own)==1,'实际退款批次偏离独立批准')
            payment=payments.get(own[0]['payment_link_id'])
            check(same(request,payment) and payment['case_id']==source['case_id'] and payment['cash_id']==batch['cash_id'] and payment['direction']=='out' and payment['original_id']==original['id'] and payment['amount_cents']==request['amount_cents'] and payment['account_id']==original['account_id'],'实际退款未回到本笔原账户或未追原收款')
            seen.add(batch['id'])
    check(seen=={b['id'] for b in batches.values() if b['kind']=='supplier_refund'},'存在绕过独立批准的供应方实退')
    for source in receivables.values():
        revisions=[r for r in targets.values() if r['receivable_id']==source['id']]
        target=max(revisions,key=lambda r:r['revision'])['amount_cents'] if revisions else source['amount_cents']
        own=[p for p in payments.values() if p['case_id']==source['case_id']];net=sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in own)
        held=sum(r['amount_cents'] for r in requests.values() if r['receivable_id']==source['id'] and r['status']=='reserved')
        check(0<=held<=max(0,net-target),'供应方待退占额超过当前真实超收')
        for original in (p for p in own if p['direction']=='in'):
            refunded=sum(p['amount_cents'] for p in own if p['direction']=='out' and p['original_id']==original['id'])
            pending=sum(r['amount_cents'] for r in requests.values() if r['original_payment_id']==original['id'] and r['status']=='reserved')
            check(refunded+pending<=original['amount_cents'],'供应方原收款被重复退回或超额占用')
    return {'verified_finance_supplier_refunds':len(requests)}
