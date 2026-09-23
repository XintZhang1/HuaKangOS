"""Read-only validation for original advances and single-cash source allocation."""
import json,hashlib
from collections import defaultdict
def source_evidence_allowed_sqlite(connection,case_id,evidence_id,store_id):
    return bool(connection.execute('''SELECT 1 FROM flow_files f JOIN flow_cases c ON c.id=? AND c.store_id=f.store_id
        WHERE f.id=? AND f.store_id=? AND f.generated=0 AND
        (EXISTS(SELECT 1 FROM business_finance_cash_batches b JOIN business_finance_cash_allocations a ON a.batch_id=b.id AND a.store_id=b.store_id
            WHERE b.case_id=f.case_id AND b.evidence_id=f.id AND a.case_id=c.id AND b.store_id=f.store_id)
        OR EXISTS(SELECT 1 FROM business_finance_advance_entries e JOIN business_finance_credit_links l ON l.entry_id=e.id AND l.store_id=e.store_id
            JOIN business_finance_advances v ON v.id=e.advance_id AND v.store_id=e.store_id
            WHERE e.case_id=f.case_id AND e.evidence_id=f.id AND l.case_id=c.id AND v.customer_id=c.customer_id AND e.store_id=f.store_id))''',
        (case_id,evidence_id,store_id)).fetchone())


def validate_business_finance_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables=['orders','advances','advance_entries','applications','credit_links','statements','statement_lines','cash_batches','cash_allocations','corrections','return_receivables','advance_returns','events','receipts']
    required={'business_finance_'+t for t in tables}
    if not required&names:return {'verified_finance_orders':0,'verified_finance_cash_batches':0}
    if not required<=names:raise ValueError('业务财务恢复表不完整')
    def rows(table):
        c=connection.execute('SELECT * FROM '+table);keys=[v[0] for v in c.description];return [dict(zip(keys,r)) for r in c]
    def keyed(table):return {r['id']:r for r in rows(table)}
    data={t:keyed('business_finance_'+t) for t in tables}
    from .business_finance_partial_integrity import validate_partial_corrections_sqlite
    partial=validate_partial_corrections_sqlite(connection)
    orders={o['case_id']:o for o in data['orders'].values()};cases=keyed('flow_cases');files=keyed('flow_files');cash=keyed('cash_entries');accounts=keyed('flow_accounts');payments=keyed('flow_payment_links')
    def check(ok,message):
        if not ok:raise ValueError('业务财务恢复：'+message)
    def proof(fid,case_id):
        f=files.get(fid);c=cases.get(case_id)
        return f and c and f['case_id']==case_id and f['store_id']==c['store_id'] and not f['generated']
    def equal_store(*records):return all(r and r['store_id']==records[0]['store_id'] for r in records)
    def hashed(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    entries=data['advance_entries'];advances=data['advances'];apps=data['applications'];credits=data['credit_links'];batches=data['cash_batches'];allocations=data['cash_allocations'];statements=data['statements'];lines=data['statement_lines']
    stored_requests=rows('business_finance_stored_correction_requests') if 'business_finance_stored_correction_requests' in names else []
    from .business_finance_correction_integrity import effective_original_cash_sqlite,validate_corrections_sqlite
    for order in orders.values():
        c=cases.get(order['case_id']);check(equal_store(order,c) and c['kind']=='business_finance' and c['flow_version']==2,'财务宿主门店或类型异常')
        if order['purpose']!='advance' and order['status'] in {'approved','completed'}:
            check(order['approved_by'] and order['approved_by']!=order['requested_by'] and any(e['case_id']==c['id'] and e['action']=='approve' and e['actor_id']==order['approved_by'] and proof(e['evidence_id'],c['id']) for e in data['events'].values()),'独立复核或批准凭据缺失')
    for event in data['events'].values():check(equal_store(event,cases.get(event['case_id'])) and event['case_id'] in orders and (not event['evidence_id'] or proof(event['evidence_id'],event['case_id'])),'财务事件或凭据越店串单')
    for a in advances.values():
        c=cases.get(a['case_id']);fact=cash.get(a['cash_id']);account=accounts.get(a['account_id']);own=[e for e in entries.values() if e['advance_id']==a['id']]
        check(equal_store(a,c,fact,account) and c['customer_id']==a['customer_id'] and orders[c['id']]['purpose']=='advance' and orders[c['id']]['status']=='completed','预收来源或客户错误')
        check(fact['direction']=='in' and fact['category']=='business_finance_advance' and fact['amount_cents']==a['initial_cents'] and fact['account']==account['name'],'预收真实现金不符')
        check(sum(e['amount_cents'] for e in own)==a['balance_cents'] and sum(e['purpose']=='receive' for e in own)==1,'预收余额与原流水不守恒')
        held=sum(p['amount_cents'] for p in apps.values() if p['advance_id']==a['id'] and p['status']=='reserved')+sum(p['reserved_cents'] for p in stored_requests if p['advance_id']==a['id'] and p['status']=='reserved')
        check(held==a['reserved_cents'] and 0<=held<=a['balance_cents']<=a['initial_cents']+a.get('correction_cents',0),'预收批准占额与可用余额不守恒')
    for e in entries.values():
        a=advances.get(e['advance_id']);c=cases.get(e['case_id']);check(equal_store(e,a,c) and c['customer_id']==a['customer_id'] and proof(e['evidence_id'],c['id']),'预收流水客户、门店或本次凭据错误')
        if e['purpose'] in {'receive','refund'}:
            original_cash=cash.get(effective_original_cash_sqlite(connection,a['cash_id'],e['occurred_at'])) if e['purpose']=='refund' else cash.get(a['cash_id'])
            fact=cash.get(e['cash_id']);check(equal_store(e,fact) and original_cash and fact['approval_state']=='approved' and fact['amount_cents']==abs(e['amount_cents']) and fact['direction']==('in' if e['purpose']=='receive' else 'out') and fact['account']==original_cash['account'] and fact['category']==('business_finance_advance' if e['purpose']=='receive' else 'business_finance_advance_refund') and files[e['evidence_id']]['category']=='receipt','原预收收退款现金不符')
        else:check(e['cash_id'] is None,'抵用或回退伪造现金')
        if e['purpose']!='receive':
            original=entries.get(e['original_id']);check(original and original['advance_id']==a['id'] and original['purpose']==('apply' if e['purpose']=='return' else 'receive'),'预收流水未追正确原款或原抵用')
    for p in apps.values():
        a=advances.get(p['advance_id']);o=orders.get(p['case_id']);c=cases.get(p['case_id'])
        check(equal_store(p,a,o,c) and c['customer_id']==a['customer_id'] and o['purpose']=='advance_'+('apply' if p['kind']=='apply' else 'refund'),'预收申请来源错误')
        matches=[e for e in entries.values() if e['case_id']==p['case_id'] and e['purpose']==p['kind']]
        check((p['status']=='applied')==(len(matches)==1),'预收申请与实际执行次数不符')
        if matches:check(matches[0]['amount_cents']==-p['amount_cents'] and matches[0]['advance_id']==a['id'],'预收执行偏离批准数额')
    for credit in credits.values():
        e=entries.get(credit['entry_id']);a=advances.get(e['advance_id']) if e else None;p=apps.get(credit['application_id']);c=cases.get(credit['case_id'])
        check(equal_store(credit,e,a,p,c) and p['kind']=='apply' and p['target_case_id']==c['id'] and a['customer_id']==c['customer_id'] and credit['amount_cents']==-e['amount_cents'],'原单抵用与预收原流水不一致')
        if credit['amount_cents']>0:check(not credit['original_id'] and e['purpose']=='apply' and p['status']=='applied','正向抵用来源错误')
        else:
            original=credits.get(credit['original_id']);check(original and original['amount_cents']>0 and original['case_id']==c['id'] and original['application_id']==p['id'] and e['original_id']==original['entry_id'] and e['purpose']=='return','预收回退未冲正确原抵用')
            if c['kind']=='retail':
                events=rows('flow_events');postings=rows('retail_return_postings');state=json.loads(c['data'])
                valid=any(x['case_id']==c['id'] and x['evidence_id']==e['evidence_id'] for x in postings) or (state.get('cancelled') and any(x['case_id']==c['id'] and x['action']=='retail_cancel' for x in events))
                check(e['case_id']==c['id'] and valid,'精品原预收回退缺少实际退货或取消')
            elif (c['kind'],c['flow_version']) in {('agency',3),('other_income',2)}:
                check(service_credit_return_allowed(connection,credit,e),'服务原预收回退缺少已批准并同意的原款终止方案')
            elif c['kind']=='addon' and c['flow_version']==3:
                from .addon_backup_integrity import validate_addon_credit_return
                check(validate_addon_credit_return(connection,credit['id']),'加装预收回退缺少原独立处置')
            elif c['kind']=='insurance' and c['flow_version']==3:
                from .insurance_backup_integrity import validate_insurance_credit_return
                check(validate_insurance_credit_return(connection,credit['id']),'保险预收回退缺少原撤保方案')
            elif c['kind']=='order' and c['flow_version'] in (3,4):
                from .sales_quote_integrity import validate_sales_credit_return
                allowed=any(h['returned_credit_id']==credit['id'] and h['status']=='applied' for h in data['advance_returns'].values())
                check(allowed or validate_sales_credit_return(connection,credit['id']),'车辆原预收回退缺少已签回报价或售后原单方案')
            else:check(any(h['returned_credit_id']==credit['id'] and h['status']=='applied' for h in data['advance_returns'].values()),'已履约原预收回退缺少售后批准执行')
    for credit in (c for c in credits.values() if c['amount_cents']>0):
        returned=-sum(c['amount_cents'] for c in credits.values() if c['original_id']==credit['id']);held=sum(h['amount_cents'] for h in data['advance_returns'].values() if h['original_credit_id']==credit['id'] and h['status']=='reserved')
        check(0<=returned+held<=credit['amount_cents'],'原抵用回退或在批占额超量')
    for batch in batches.values():
        fact=cash.get(batch['cash_id']);c=cases.get(batch['case_id']);own=[a for a in allocations.values() if a['batch_id']==batch['id']]
        check(equal_store(batch,fact,c) and c['id'] in orders and proof(batch['evidence_id'],c['id']) and files[batch['evidence_id']]['category']=='receipt' and fact['amount_cents']==batch['amount_cents'],'集中收款批次真实现金或凭据不一致')
        check(sum(a['amount_cents'] for a in own)+partial['batch_retained'].get(batch['id'],0)==batch['amount_cents'] and {a['payment_link_id'] for a in own}=={p['id'] for p in payments.values() if p['cash_id']==fact['id']},'一笔实际现金与全部逐单分配不守恒')
        check(fact['category']=={'collection':'business_finance_collection','correction_reverse':'business_finance_correction_reverse','correction_record':'business_finance_corrected','supplier_refund':'business_finance_other_return_refund'}[batch['kind']] and fact['direction']==('out' if batch['kind'] in {'correction_reverse','supplier_refund'} else 'in'),'批次类别或收付方向错误')
        for allocation in own:
            p=payments.get(allocation['payment_link_id']);target=cases.get(allocation['case_id'])
            check(equal_store(batch,allocation,p,target) and p['case_id']==target['id'] and p['cash_id']==fact['id'] and p['amount_cents']==allocation['amount_cents'] and p['direction']==fact['direction'] and p['reference']==fact['voucher_no'] and p['business_date']==fact['business_date'] and accounts[p['account_id']]['name']==fact['account'],'集中收款分配串店串客户或现金来源错误')
            check(target['customer_id']==c['customer_id'],'集中收款混入另一客户')
            if allocation['statement_line_id']:
                line=lines.get(allocation['statement_line_id']);check(line and statements[line['statement_id']]['case_id']==c['id'] and line['source_case_id']==target['id'],'集中收款越出冻结客户账单')
    for statement in statements.values():
        own=sorted([l for l in lines.values() if l['statement_id']==statement['id']],key=lambda l:l['id']);snapshots=[json.loads(l['snapshot']) for l in own];c=cases.get(statement['case_id'])
        check(equal_store(statement,c) and c['customer_id']==statement['customer_id'] and statement['digest']==hashed(snapshots) and sum(l['due_cents'] for l in own)==c['amount_cents'],'客户账单冻结摘要或合计不符')
        for line,snapshot in zip(own,snapshots):
            target=cases.get(line['source_case_id']);check(equal_store(line,statement,target) and target['customer_id']==statement['customer_id'] and snapshot['case_id']==target['id'] and snapshot['customer_id']==target['customer_id'] and snapshot['due_cents']==line['due_cents'] and statement['starts_on']<=target['business_date']<=statement['ends_on'],'冻结原单、客户、期间或余额不符')
            check(sum(a['amount_cents'] for a in allocations.values() if a['statement_line_id']==line['id'])<=line['due_cents'],'客户账单分配超过冻结额度')
        if statement['previous_id']:
            previous=statements.get(statement['previous_id']);check(previous and previous['customer_id']==statement['customer_id'] and equal_store(previous,statement) and previous['revision']+1==statement['revision'] and previous['starts_on']==statement['starts_on'] and previous['ends_on']==statement['ends_on'],'客户账单追加版本断裂')
        else:check(statement['revision']==1,'初始客户账单版本错误')
    for correction in data['corrections'].values():
        original=cash.get(correction['original_cash_id']);reverse=batches.get(correction['reversing_batch_id']);record=batches.get(correction['corrected_batch_id']);order=orders.get(correction['case_id']);values=json.loads(order['values']) if order else {}
        check(equal_store(correction,original,reverse,order) and reverse['case_id']==order['case_id'] and reverse['kind']=='correction_reverse' and reverse['amount_cents']==original['amount_cents'] and values['original_cash_id']==original['id'],'原现金追加更正来源或数额异常')
        check(bool(record)==(values.get('amount_cents',0)>0),'纯撤错不应伪造零元正确到账')
        if record:
            check(equal_store(correction,record) and record['case_id']==order['case_id'] and record['kind']=='correction_record' and record['amount_cents']==values['amount_cents'],'正确重记与批准金额不符')
            check(cash[record['cash_id']]['business_date']==values['actual_business_date'],'更正真实到账日偏离冻结凭据')
        originals={p['id']:p for p in payments.values() if p['cash_id']==original['id']};reversals=[payments[a['payment_link_id']] for a in allocations.values() if a['batch_id']==reverse['id']]
        if correction['case_id'] not in partial['partial_case_ids']:
            check({p['original_id'] for p in reversals}==set(originals) and all((p['case_id'],p['amount_cents'])==(originals[p['original_id']]['case_id'],originals[p['original_id']]['amount_cents']) for p in reversals),'更正未完整冲原逐单分配')
        actual_allocations=sorted((a['case_id'],a['amount_cents']) for a in allocations.values() if record and a['batch_id']==record['id'])
        check(actual_allocations==sorted((a['source_case_id'],a['amount_cents']) for a in values['allocations']),'正确重记偏离批准分配')
    for receipt in data['return_receivables'].values():
        move=keyed('flow_stock_moves').get(receipt['stock_move_id']);order=orders.get(receipt['case_id']);supplier=keyed('master_suppliers').get(receipt['supplier_id'])
        check(equal_store(receipt,move,order,supplier) and move['purpose']=='wh_other_return' and move['original_id'] and (-move['quantity_milli'],-move['value_cents'])==(receipt['quantity_milli'],receipt['value_cents']) and receipt['amount_cents']==json.loads(order['values'])['amount_cents'] and proof(receipt['evidence_id'],order['case_id']),'其他入库退货应收缺少原实物成本或独立批准')
    for hold in data['advance_returns'].values():
        original=credits.get(hold['original_credit_id']);source=cases.get(hold['source_case_id']);case=cases.get(hold['aftercare_case_id']);plan=keyed('aftercare_plans').get(hold['plan_id'])
        check(equal_store(hold,original,source,case,plan) and original['case_id']==source['id'] and case['customer_id']==source['customer_id'] and plan['case_id']==case['id'],'预收售后占额来源异常')
        source_ids={s['id'] for s in rows('aftercare_sources') if s['case_id']==case['id'] and s['source_case_id']==source['id']}
        check(any(t['plan_id']==plan['id'] and t['source_id'] in source_ids and t['kind']=='advance' and t['original_id']==original['id'] and t['units']==t['credit_cents']==hold['amount_cents'] for t in rows('aftercare_tenders')),'预收退回偏离原路批准方案')
        returned=credits.get(hold['returned_credit_id']);check((hold['status']=='applied')==bool(returned),'预收售后占额与实际过账不一致')
        if returned:check(returned['original_id']==original['id'] and returned['amount_cents']==-hold['amount_cents'] and entries[returned['entry_id']]['case_id']==case['id'],'预收售后实际回退原单错误')
    corrections=validate_corrections_sqlite(connection)
    from .business_finance_bundle_integrity import validate_bundle_corrections_sqlite
    corrections.update(validate_bundle_corrections_sqlite(connection))
    from .business_finance_supplier_integrity import validate_supplier_refunds_sqlite
    corrections.update(validate_supplier_refunds_sqlite(connection))
    expected={e['cash_id'] for e in entries.values() if e['cash_id']}|{b['cash_id'] for b in batches.values()}|corrections.pop('cash_ids')
    from .membership_fee_correction_integrity import validate as validate_fee_corrections
    fee_corrections=validate_fee_corrections(connection)
    expected|=fee_corrections.pop('cash_ids')
    corrections.update(fee_corrections)
    check(expected=={c['id'] for c in cash.values() if c['category'].startswith('business_finance_')},'存在无原单事实的业务财务现金')
    return {'verified_finance_orders':len(orders),'verified_finance_cash_batches':len(batches),'verified_finance_partial_corrections':partial['verified_finance_partial_corrections'],**corrections}


def service_credit_return_allowed(connection,credit,entry):
    """Only an exact original service tender return permits a negative credit."""
    rows=connection.execute("""
        SELECT t.amount_cents,r.amount_cents
        FROM service_tender_slices t
        JOIN service_refunds r ON r.reversal_tender_id=t.id AND r.store_id=t.store_id
        JOIN service_tender_slices o ON o.id=r.original_tender_id AND o.id=t.original_id AND o.store_id=t.store_id
        JOIN service_terminations p ON p.id=r.plan_id AND p.case_id=t.case_id AND p.store_id=t.store_id
        JOIN service_termination_approvals a ON a.plan_id=p.id AND a.store_id=p.store_id AND a.actor_id!=p.actor_id
        JOIN service_termination_consents c ON c.plan_id=p.id AND c.store_id=p.store_id
        JOIN service_termination_applications x ON x.plan_id=p.id AND x.store_id=p.store_id
        WHERE t.credit_link_id=? AND o.credit_link_id=? AND t.case_id=? AND o.case_id=t.case_id
        AND t.store_id=? AND t.amount_cents=-r.amount_cents AND t.evidence_id=? AND r.evidence_id=t.evidence_id
        AND t.actor_id=? AND r.actor_id=t.actor_id AND o.line_id=t.line_id AND o.bucket=t.bucket
        AND NOT EXISTS(SELECT 1 FROM service_termination_cancellations z WHERE z.plan_id=p.id)
    """,(credit['id'],credit['original_id'],credit['case_id'],credit['store_id'],entry['evidence_id'],entry['actor_id'])).fetchall()
    return bool(rows and entry['case_id']==credit['case_id'] and sum(r[0] for r in rows)==credit['amount_cents'])
