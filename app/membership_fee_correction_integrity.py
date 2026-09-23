"""Independent replay of same-amount fees and each real refund's original cash."""
import json


def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'membership_fee_correction_requests','membership_fee_corrections','membership_fee_refund_bases'}
    def rows(table):
        if table not in names:return []
        c=connection.execute('SELECT * FROM "'+table+'"');keys=[r[0] for r in c.description]
        return [dict(zip(keys,r)) for r in c]
    def keyed(table):return {r['id']:r for r in rows(table)}
    def check(ok,message):
        if not ok:raise ValueError('续会费更正恢复：'+message)
    orders={r['case_id']:r for r in rows('business_finance_orders') if r['purpose']=='fee_correction'}
    cash=keyed('cash_entries');member_events=rows('membership_events')
    categories={'business_finance_member_fee_reverse','business_finance_member_fee_corrected'}
    tagged={r['id'] for r in cash.values() if r['category'] in categories}
    basis_events=[e for e in member_events if e['action']=='fee_refund_basis']
    empty={'verified_member_fee_corrections':0,'verified_member_fee_refund_bases':0,'cash_ids':set()}
    if not names&required:
        check(not orders and not tagged and not basis_events,'新原款依据整套缺失')
        return empty
    check(required<=names,'新原款依据表不完整')
    requests=keyed('membership_fee_correction_requests');facts=keyed('membership_fee_corrections');bases=keyed('membership_fee_refund_bases')
    fees=keyed('membership_fees');cases=keyed('flow_cases');files=keyed('flow_files');accounts=keyed('flow_accounts')
    periods=keyed('membership_periods');member_orders={r['case_id']:r for r in rows('membership_orders')}
    finance_events=rows('business_finance_events')
    def same(*records):return bool(records) and all(r and r['store_id']==records[0]['store_id'] for r in records)
    def proof(fid,cid,receipt=False):
        f=files.get(fid);c=cases.get(cid)
        return same(f,c) and f['case_id']==cid and not f['generated'] and (not receipt or f['category']=='receipt')
    def source(fee):
        if not fee:return False
        root=cases.get(fee['case_id']);order=member_orders.get(fee['case_id']);period=periods.get(fee['period_id'])
        return same(fee,root,order,period) and fee['original_id'] is None and fee['amount_cents']>0 and order['purpose']=='renew' and order['status']=='completed' and period['case_id']==root['id'] and period['member_id']==order['member_id'] and proof(fee['evidence_id'],root['id'])
    successors={};by_request={};seen_cash=set()
    for fact in facts.values():
        request=requests.get(fact['request_id']);order=orders.get(fact['case_id']);fee=fees.get(fact['fee_id'])
        check(same(fact,request,order,fee) and request['case_id']==fact['case_id']==order['case_id'] and request['fee_id']==fee['id'] and request['status']=='applied' and order['status']=='completed','实际更正缺少已批准完成的同店来源')
        check(fact['request_id'] not in by_request and fact['original_cash_id'] not in successors,'原款存在重复或分叉更正')
        original=cash.get(fact['original_cash_id']);reverse=cash.get(fact['reversing_cash_id']);corrected=cash.get(fact['corrected_cash_id'])
        check(same(fact,original,reverse,corrected) and fact['original_cash_id']==request['original_cash_id'],'现金来源缺失或串店')
        check(original['direction']=='in' and original['amount_cents']==request['amount_cents'] and reverse['direction']=='out' and corrected['direction']=='in'
            and reverse['category']=='business_finance_member_fee_reverse' and corrected['category']=='business_finance_member_fee_corrected'
            and reverse['amount_cents']==corrected['amount_cents']==request['amount_cents'] and all(c['approval_state']=='approved' for c in (original,reverse,corrected)),'同额冲正与正确登记金额或方向不符')
        old_account=accounts.get(request['original_account_id']);new_account=accounts.get(request['account_id'])
        check(same(fact,old_account,new_account) and original['account']==reverse['account']==old_account['name'] and corrected['account']==new_account['name']
            and corrected['voucher_no']==request['reference'] and corrected['business_date']==original['business_date']==request['business_date'],'冻结账户、凭证或原日期被改变')
        check(original['id']<reverse['id']<corrected['id'] and corrected['created_by']==reverse['created_by']==fact['actor_id'],'原款更正先后或经办人异常')
        check(proof(fact['evidence_id'],fact['case_id'],True) and any(e['case_id']==fact['case_id'] and e['action']=='execute' and e['actor_id']==fact['actor_id'] and e['evidence_id']==fact['evidence_id'] for e in finance_events),'正确登记缺少原执行凭据')
        check(not ({reverse['id'],corrected['id']}&seen_cash),'更正现金被重复使用')
        seen_cash.update((reverse['id'],corrected['id']));successors[original['id']]=fact;by_request[fact['request_id']]=fact
    check(seen_cash==tagged,'存在无来源或漏记的续会费更正现金')
    check({r['case_id'] for r in requests.values()}==set(orders),'财务申请与续会费来源不成对')
    frozen=('fee_id','original_cash_id','original_account_id','account_id','reference','amount_cents','source_version','refunded_fee_id','business_date')
    for request in requests.values():
        order=orders.get(request['case_id']);case=cases.get(request['case_id']);fee=fees.get(request['fee_id']);values=json.loads(order['values']) if order else {}
        check(source(fee) and same(request,order,case,fee) and case['kind']=='business_finance' and case['flow_version']==2 and case['customer_id']==cases[fee['case_id']]['customer_id'],'续会原业务、会员或客户不符')
        check(values.get('source_case_id')==fee['case_id'] and all(values.get(k)==request[k] for k in frozen) and request['amount_cents']==fee['amount_cents']
            and request['source_version']>0 and cases[fee['case_id']]['version']>=request['source_version'],'申请冻结来源、正金额或版本不符')
        check((request['status']=='applied')==(request['id'] in by_request) and request['status']=={'draft':'requested','approved':'reserved','completed':'applied','cancelled':'released'}.get(order['status']),'申请状态与实际更正不符')
        if order['status'] in {'approved','completed'}:
            check(order['approved_by'] and order['approved_by']!=order['requested_by'] and any(e['case_id']==case['id'] and e['action']=='approve' and e['actor_id']==order['approved_by'] and proof(e['evidence_id'],case['id']) for e in finance_events),'缺少独立批准及凭据')
        root_cash=cash.get(fee['cash_id']);cursor=fee['cash_id'];seen=set();account=fee['account_id']
        check(root_cash and request['business_date']==root_cash['business_date'],'原实际日期改变')
        while cursor!=request['original_cash_id']:
            check(cursor not in seen and cursor in successors,'更正链未追原续会费')
            seen.add(cursor);fact=successors[cursor];previous=requests[fact['request_id']]
            check(fact['fee_id']==fee['id'] and fact['case_id']<request['case_id'],'更正链串原款或时间倒置')
            cursor=fact['corrected_cash_id'];account=previous['account_id']
        check(account==request['original_account_id'],'更正未使用当时原账户')
        refund=fees.get(request['refunded_fee_id']) if request['refunded_fee_id'] else None
        if refund:check(refund['original_id']==fee['id'] and refund['occurred_at']<=request['created_at'],'已退款切片与原款或时点不符')
        earlier=[f for f in fees.values() if f['original_id']==fee['id'] and f['occurred_at']<=request['created_at']]
        check({f['id'] for f in earlier}==({refund['id']} if refund else set()),'遗漏申请前已真实退款')
    refunds={r['refund_fee_id']:r for r in bases.values()}
    check(len(refunds)==len(bases),'实际退款依据重复')
    for fee in fees.values():
        if not fee['original_id']:continue
        original=fees.get(fee['original_id']);check(source(original),'实际退款原收费来源缺失')
        cursor=original['cash_id'];account=original['account_id'];seen=set()
        while cursor in successors and successors[cursor]['corrected_cash_id']<fee['cash_id']:
            check(cursor not in seen,'实际退款来源更正链循环');seen.add(cursor)
            fact=successors[cursor];check(fact['fee_id']==original['id'],'实际退款串原更正')
            cursor=fact['corrected_cash_id'];account=requests[fact['request_id']]['account_id']
        basis=refunds.get(fee['id']);tag=[e for e in basis_events if json.loads(e['detail']).get('refund_fee_id')==fee['id']]
        if basis:
            check(same(basis,fee,original) and basis['original_fee_id']==original['id'] and basis['original_cash_id']==cursor and account==fee['account_id'],'实际退款未沿当时有效原款原账户')
            check(len(tag)==1 and tag[0]['case_id']==fee['case_id'] and tag[0]['actor_id']==fee['actor_id'] and tag[0]['evidence_id']==fee['evidence_id']
                and json.loads(tag[0]['detail'])=={'refund_fee_id':fee['id'],'original_fee_id':original['id'],'original_cash_id':cursor},'实际退款冻结事件不符')
        else:check(not tag and cursor==original['cash_id'] and fee['account_id']==original['account_id'],'更正后的实际退款缺少原款依据')
    check(set(refunds)<={f['id'] for f in fees.values() if f['original_id']} and len(basis_events)==len(bases),'存在孤立退款依据或事件')
    return {'verified_member_fee_corrections':len(facts),'verified_member_fee_refund_bases':len(bases),'cash_ids':seen_cash}


def refund_account(connection,fee,original):
    """After validate(), allow only a persisted same-fee original cash basis."""
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'membership_fee_refund_bases' not in names:return original['account_id']
    basis=connection.execute('SELECT original_cash_id FROM membership_fee_refund_bases WHERE refund_fee_id=?',(fee['id'],)).fetchone()
    if not basis or basis[0]==original['cash_id']:return original['account_id']
    row=connection.execute('''SELECT r.account_id FROM membership_fee_corrections f JOIN membership_fee_correction_requests r ON r.id=f.request_id
        WHERE f.corrected_cash_id=? AND f.fee_id=? AND f.store_id=?''',(basis[0],original['id'],original['store_id'])).fetchone()
    if not row:raise ValueError('续会费更正恢复：退款账户缺少原有效更正')
    return row[0]
