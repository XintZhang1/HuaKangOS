"""Offline checks for cash corrections, principal conservation and target history."""
import json


def effective_original_cash_sqlite(connection,root_cash_id,at=None):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_finance_stored_corrections' not in names:return root_cash_id
    cursor=root_cash_id;seen=set()
    while cursor:
        if cursor in seen or len(seen)>=1000:raise ValueError('业务财务恢复：原款更正链循环')
        seen.add(cursor)
        row=connection.execute('SELECT corrected_cash_id,occurred_at FROM business_finance_stored_corrections WHERE original_cash_id=?',(cursor,)).fetchone()
        if not row or at and row[1]>at:break
        cursor=row[0]
    return cursor


def validate_corrections_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables={'business_finance_stored_correction_requests','business_finance_stored_corrections','business_finance_return_target_revisions'}
    if not tables&names:return {'cash_ids':set(),'verified_finance_stored_corrections':0,'verified_finance_return_target_revisions':0}
    if not tables<=names:raise ValueError('业务财务恢复：原款更正表不完整')
    def rows(table):
        cursor=connection.execute('SELECT * FROM '+table);keys=[c[0] for c in cursor.description]
        return {r['id']:r for r in (dict(zip(keys,row)) for row in cursor)}
    def check(value,message):
        if not value:raise ValueError('业务财务恢复：'+message)
    def equal(*records):return all(r and r['store_id']==records[0]['store_id'] for r in records)
    requests=rows('business_finance_stored_correction_requests');fixes=rows('business_finance_stored_corrections');revisions=rows('business_finance_return_target_revisions')
    orders={r['case_id']:r for r in rows('business_finance_orders').values()};cases=rows('flow_cases');cash=rows('cash_entries');accounts=rows('flow_accounts');files=rows('flow_files')
    advances=rows('business_finance_advances');advance_entries=rows('business_finance_advance_entries');entries=rows('group_entries');receivables=rows('business_finance_return_receivables');payments=rows('flow_payment_links')
    by_request={f['request_id']:f for f in fixes.values()};by_result={f['corrected_cash_id']:f for f in fixes.values() if f['corrected_cash_id']}
    expected=set();used_advance=set();used_group=set()
    for request in requests.values():
        case=cases.get(request['case_id']);order=orders.get(request['case_id']);values=json.loads(order['values']) if order else {};original=cash.get(request['original_cash_id'])
        check(equal(request,case,order,original) and order['purpose']=='stored_correction','原款更正申请串店或无独立财务宿主')
        check(request['original_amount_cents']==original['amount_cents']==values.get('original_amount_cents') and request['corrected_amount_cents']==values.get('amount_cents')
            and request['original_cash_id']==values.get('original_cash_id') and request['reserved_cents']==max(0,request['original_amount_cents']-request['corrected_amount_cents']),'原款更正批准金额或占额偏离冻结原款')
        check(request['source_kind']==values.get('source_kind') and all(request[k]==values.get(k) for k in ('advance_id','member_id','topup_id')),'原款更正来源偏离冻结申请')
        check({'requested':'draft','reserved':'approved','applied':'completed','released':'cancelled'}.get(request['status'])==order['status'],'原款更正占额状态与办理状态不符')
        origin=advances.get(request['advance_id']) if request['source_kind']=='advance' else entries.get(request['topup_id'])
        source=cases.get(origin['case_id']) if origin else None
        check(equal(request,origin,source) and source['customer_id']==case['customer_id'] and source['id']==values.get('source_case_id'),'原款更正来源客户或门店错误')
        if request['source_kind']=='member':check(origin['purpose']=='topup' and origin['member_id']==request['member_id'],'会员原充值来源不符')
        cursor=original['id'];seen=set()
        while cursor in by_result:
            check(cursor not in seen,'原款更正链循环');seen.add(cursor);previous=by_result[cursor]
            check(equal(request,previous) and previous['request_id'] in requests,'原款更正链跨店')
            old=requests[previous['request_id']];check(all(request[k]==old[k] for k in ('source_kind','advance_id','member_id','topup_id')),'原款更正链更换本金来源')
            cursor=previous['original_cash_id']
        check(cursor==origin['cash_id'],'原款更正未追溯原始发行现金')
        fix=by_request.get(request['id']);check((request['status']=='applied')==bool(fix),'原款更正执行次数错误')
        if not fix:continue
        reverse=cash.get(fix['reversing_cash_id']);record=cash.get(fix['corrected_cash_id']);proof=files.get(fix['evidence_id'])
        check(equal(fix,request,reverse,proof) and fix['case_id']==case['id'] and fix['original_cash_id']==original['id'] and proof['case_id']==case['id'] and not proof['generated'] and proof['category']=='receipt','原款更正现金与本次凭据串单')
        check(reverse['direction']=='out' and reverse['approval_state']=='approved' and reverse['category']=='business_finance_stored_reverse' and reverse['amount_cents']==original['amount_cents'] and reverse['account']==original['account'],'误记冲正偏离原收款现金')
        expected.add(reverse['id'])
        check(bool(record)==(request['corrected_amount_cents']>0),'零元撤错不应伪造替代到账')
        if record:
            account=accounts.get(values.get('account_id'))
            check(equal(fix,record,account) and record['direction']=='in' and record['approval_state']=='approved' and record['category']=='business_finance_stored_corrected' and record['amount_cents']==request['corrected_amount_cents'] and record['account']==account['name'] and record['voucher_no']==values.get('reference') and record['business_date']==values.get('actual_business_date'),'正确原款现金偏离冻结账户金额日期')
            expected.add(record['id'])
        delta=request['corrected_amount_cents']-request['original_amount_cents']
        entry=(advance_entries if request['source_kind']=='advance' else entries).get(fix['advance_entry_id'] if request['source_kind']=='advance' else fix['group_entry_id'])
        check(bool(entry)==bool(delta),'原款误记差额与本金更正流水不符')
        check(not (fix['group_entry_id'] if request['source_kind']=='advance' else fix['advance_entry_id']),'原款更正混用会员与预收账本')
        if entry:
            check(equal(fix,entry) and entry['purpose']=='correction' and entry['case_id']==case['id'] and entry['amount_cents']==delta and entry['cash_id'] is None and entry['evidence_id']==proof['id'] and entry['actor_id']==fix['actor_id'],'更正余额流水伪造现金或偏离原差额')
            if request['source_kind']=='advance':
                original_entry=advance_entries.get(entry['original_id'])
                check(entry['advance_id']==origin['id'] and original_entry and original_entry['advance_id']==origin['id'] and original_entry['purpose']=='receive','预收更正未追原收款流水');used_advance.add(entry['id'])
            else:
                check(entry['member_id']==request['member_id'] and entry['original_id']==origin['id'],'会员更正未追原本金');used_group.add(entry['id'])
    check(used_advance=={e['id'] for e in advance_entries.values() if e['purpose']=='correction'} and used_group=={e['id'] for e in entries.values() if e['purpose']=='correction'},'存在未获独立审批的本金更正流水')
    for advance in advances.values():
        check(advance.get('correction_cents',0)==sum(e['amount_cents'] for e in advance_entries.values() if e['advance_id']==advance['id'] and e['purpose']=='correction'),'原预收累计更正与不可变流水不守恒')
    for revision in sorted(revisions.values(),key=lambda r:r['revision']):
        receivable=receivables.get(revision['receivable_id']);case=cases.get(revision['case_id']);order=orders.get(revision['case_id']);values=json.loads(order['values']) if order else {};proof=files.get(revision['evidence_id'])
        check(equal(revision,receivable,case,order,proof) and order['purpose']=='other_return_adjust' and order['status']=='completed' and proof['case_id']==case['id'] and not proof['generated'],'应退目标修订审批来源或凭据错误')
        previous=revisions.get(revision['previous_id']);prior=previous['amount_cents'] if previous else receivable['amount_cents']
        check((previous is None and revision['revision']==1 or previous and equal(previous,revision) and previous['receivable_id']==receivable['id'] and previous['revision']+1==revision['revision'])
            and revision['original_amount_cents']==prior==values.get('original_amount_cents') and revision['amount_cents']==values.get('amount_cents') and revision['previous_id']==values.get('previous_revision_id') and receivable['id']==values.get('receivable_id'),'应退目标追加版本断裂或改写原目标')
        ids=json.loads(revision['received_payment_ids']);known=[payments.get(key) for key in ids]
        check(isinstance(ids,list) and len(ids)==len(set(ids)) and all(equal(revision,p) and p['case_id']==receivable['case_id'] for p in known),'目标修订使用了其他原款来源')
        check(sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in known)==revision['received_cents'],'目标修订抹去实际已收现金')
        check(revision['amount_cents']>=revision['received_cents'] or values.get('target_policy')=='supplier_overpayment_v1','旧目标修订不得默认为新增超收退款规则')
    for receivable in receivables.values():
        own=[r for r in revisions.values() if r['receivable_id']==receivable['id']]
        if own:
            target=max(own,key=lambda r:r['revision'])['amount_cents'];source=cases[receivable['case_id']]
            check(source['amount_cents']==target and target>=0,'当前应退目标与修订不一致')
    return {'cash_ids':expected,'verified_finance_stored_corrections':len(fixes),'verified_finance_return_target_revisions':len(revisions)}
