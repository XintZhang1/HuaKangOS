"""Reconstruct immutable agreement, original cash and customer-share boundaries."""
import json,hashlib
from datetime import datetime
from collections import defaultdict

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'aftercare_orders' not in names:return {'verified_aftercare_orders':0,'verified_aftercare_refunds':0}
    def rows(name):
        q=connection.execute('SELECT * FROM '+name);cols=[r[0] for r in q.description];return [dict(zip(cols,r)) for r in q]
    def by(name,key='id'):return {r[key]:r for r in rows(name)}
    def fail(message):raise ValueError('售后恢复检查：'+message)
    def same(a,b):return a and b and a['store_id']==b['store_id']
    def data(r):return json.loads(r['data'])
    cases=by('flow_cases');orders=by('aftercare_orders');sources=by('aftercare_sources');plans=by('aftercare_plans');lines=by('aftercare_plan_lines');tenders=by('aftercare_tenders')
    approvals=by('aftercare_approvals','plan_id');consents=by('aftercare_consents','plan_id');cancelled=by('aftercare_plan_cancellations','plan_id');applications=by('aftercare_applications','plan_id')
    adjustments=by('aftercare_adjustments','plan_line_id');executions=by('aftercare_execution_facts');files=by('flow_files');allocations=by('repair_allocations');payments=by('flow_payment_links');cash=by('cash_entries')
    request_events=[e for e in rows('flow_events') if e['action']=='aftercare_request']
    claims=by('aftercare_claims','source_case_id');refunds=rows('aftercare_cash_refunds');collections=rows('aftercare_cash_collections');allcredits=defaultdict(int)
    def proof(key,case_id,category=None):
        f=files.get(key);c=cases[case_id]
        if not same(f,c) or f['case_id']!=case_id or f['generated'] or category and f['category']!=category:fail('凭据没有关联本售后单和实际类别')
    for order in orders.values():
        case=cases.get(order['id']);source=cases.get(order['source_case_id'])
        if not same(case,order) or case['kind']!='aftercare' or case['flow_version']!=2 or not same(source,case) or source['customer_id']!=case['customer_id']:fail('售后与原单门店、客户或版本不一致')
        if order['scenario']=='repair_refund':
            if source['kind']!='repair' or source['flow_version'] not in (3,4) or not data(source).get('released_date'):fail('维修退费原单未实际交付')
        elif source['kind']!='order' or source['flow_version'] not in (2,3,4) or ((order['scenario']=='vehicle_return')!=(source['state']=='delivered')):fail('销售原单版本或原交付事实不支持')
        links=[s for s in sources.values() if s['case_id']==case['id']]
        excluded=data(case).get('independently_resolved_service_ids',[])
        if not isinstance(excluded,list) or any(type(i) is not int for i in excluded):fail('独立服务排除清单格式错误')
        if 'independently_resolved_service_ids' in data(case):
            events=[e for e in request_events if e['case_id']==case['id']]
            if len(events)!=1 or json.loads(events[0]['detail']).get('independently_resolved_service_ids')!=excluded:fail('独立服务排除清单与申请原事实不一致')
        if source['kind']=='order' and 'service_orders' in names:
            from .service_orders_backup_integrity import validate_parent_aftercare_exclusions
            validate_parent_aftercare_exclusions(connection,source['id'],excluded,case['created_at'])
        elif excluded:fail('非销售售后不能排除独立服务')
        insurance_excluded=data(case).get('independently_resolved_insurance_ids',[])
        if not isinstance(insurance_excluded,list) or any(type(i) is not int for i in insurance_excluded):fail('独立保险排除清单格式错误')
        if 'independently_resolved_insurance_ids' in data(case):
            events=[e for e in request_events if e['case_id']==case['id']]
            if len(events)!=1 or json.loads(events[0]['detail']).get('independently_resolved_insurance_ids')!=insurance_excluded:fail('保险排除清单与申请原事实不一致')
        if source['kind']=='order' and 'insurance_orders' in names:
            from .insurance_backup_integrity import validate_parent_aftercare_exclusions as insurance_exclusions
            insurance_exclusions(connection,source['id'],insurance_excluded,case['created_at'])
        elif insurance_excluded:fail('非销售售后不能排除保险')
        addon_excluded=data(case).get('independently_resolved_addon_ids',[])
        if not isinstance(addon_excluded,list) or any(type(i) is not int for i in addon_excluded):fail('独立加装排除清单格式错误')
        if 'independently_resolved_addon_ids' in data(case):
            events=[e for e in request_events if e['case_id']==case['id']]
            if len(events)!=1 or json.loads(events[0]['detail']).get('independently_resolved_addon_ids')!=addon_excluded:fail('加装排除清单与申请原事实不一致')
        if source['kind']=='order' and 'addon_orders' in names:
            from .addon_backup_integrity import validate_parent_aftercare_exclusions as addon_exclusions
            applied_at=None
            if any(a['case_id']==case['id'] for a in applications.values()):
                applied_events=[e for e in rows('flow_events') if e['case_id']==case['id'] and e['action']=='aftercare_apply']
                if len(applied_events)!=1:fail('售后生效缺少唯一实际执行时间')
                applied_at=applied_events[0]['occurred_at']
            addon_exclusions(connection,source['id'],addon_excluded,case['created_at'],applied_at)
        elif addon_excluded:fail('非销售售后不能排除加装')
        excluded=excluded+insurance_excluded+addon_excluded
        expected={source['id']}|({c['id'] for c in cases.values() if c['parent_id']==source['id'] and c['kind'] in ('addon','insurance','agency') and datetime.fromisoformat(c['created_at'])<=datetime.fromisoformat(case['created_at']) and c['id'] not in excluded} if source['kind']=='order' else set())
        if {s['source_case_id'] for s in links}!=expected:fail('遗漏原单或关联履约服务')
        for s in links:
            original=cases.get(s['source_case_id']);snapshot=json.loads(s['snapshot']);allocation=allocations.get(s['allocation_id'])
            if not same(s,case) or not same(original,case) or original['customer_id']!=case['customer_id'] or any(snapshot[k]!=original[k] for k in ('number','kind','flow_version','customer_id','vehicle_id')):fail('冻结来源被更换或跨店')
            if original['kind']=='order' and original['flow_version'] in (3,4):
                quote=by('sales_quotes').get(snapshot.get('sales_quote_id'))
                if not same(quote,original) or quote['case_id']!=original['id'] or data(original).get('active_quote_id')!=quote['id'] or snapshot.get('sales_quote_digest')!=quote['digest']:fail('车辆售后未冻结本版客户已确认报价')
            if (original['kind'],original['flow_version']) in {('agency',3),('other_income',2),('insurance',3),('addon',3)}:fail('独立服务本金进入整车通用退款')
            amount=original['amount_cents']
            if original['kind']=='repair':
                if snapshot.get('package_zero_customer'):
                    captures=[p for p in rows('repair_package_payment_links') if p['case_id']==original['id'] and p['purpose']=='capture'] if 'repair_package_payment_links' in names else []
                    if (allocation or s['allocation_id'] is not None or not captures or any(p['store_id']!=case['store_id'] or p['amount_cents']!=0 or datetime.fromisoformat(p['occurred_at'])>datetime.fromisoformat(case['created_at']) for p in captures)
                        or any(a['case_id']==original['id'] and a['payer_type']=='customer' for a in allocations.values())):fail('零客户金额原退缺少真实原套餐核销，或借用了其他承担')
                    amount=0
                else:
                    if not same(allocation,case) or allocation['case_id']!=original['id'] or allocation['payer_type']!='customer':fail('维修退费越过原客户承担')
                    amount=allocation['amount_cents']
            elif allocation:fail('非维修原单不能借用维修承担')
            if s['original_cents']!=amount:fail('原承担快照金额变化')
            claim=claims.get(original['id']);active=case['state'] not in ('completed','cancelled','rejected')
            if active and (not same(claim,case) or claim['case_id']!=case['id']):fail('未结售后缺少原单冻结')
            if not active and claim and claim['case_id']==case['id']:fail('终态售后仍占原单')
    for claim in claims.values():
        if not any(s['case_id']==claim['case_id'] and s['source_case_id']==claim['source_case_id'] and same(s,claim) for s in sources.values()):fail('原单冻结未关联具体售后来源')
    for e in executions.values():
        source=sources.get(e['source_id'])
        if not same(e,source) or source['case_id']!=e['case_id'] or cases[source['source_case_id']]['kind'] not in ('addon','insurance','agency'):fail('履约事实没有关联原服务')
        proof(e['evidence_id'],e['case_id'])
    for p in sorted(plans.values(),key=lambda p:p['id']):
        case=cases[p['case_id']];ls=sorted([l for l in lines.values() if l['plan_id']==p['id']],key=lambda l:l['id']);ts=sorted([t for t in tenders.values() if t['plan_id']==p['id']],key=lambda t:t['id'])
        if not same(p,case) or {l['source_id'] for l in ls}!={s['id'] for s in sources.values() if s['case_id']==case['id']}:fail('方案没有完整逐项关联原业务')
        for l in ls:
            s=sources[l['source_id']]
            if not same(l,p) or l['base_cents']!=l['credit_cents']+l['retained_cents'] or min(l['credit_cents'],l['retained_cents'],l['refund_cents'])<0:fail('减免保留费用不守恒')
            if cases[s['source_case_id']]['kind'] in ('addon','insurance','agency'):
                e=executions.get(l['execution_id'])
                if not same(e,p) or e['source_id']!=s['id']:fail('服务保留费缺少实际履约事实')
            if sum(t['credit_cents'] for t in ts if t['source_id']==s['id'])!=l['refund_cents']:fail('原路方案与退款额不一致')
        normalized={'lines':[{k:l[k] for k in ('source_id','execution_id','base_cents','credit_cents','retained_cents','refund_cents','revenue_credit_cents')} for l in ls],
            'returns':[{k:t[k] for k in ('source_id','kind','original_id','units','credit_cents','discount_cents')} for t in ts],'reason':p['reason']}
        digest=hashlib.sha256(json.dumps({'operation':'aftercare_plan','payload':normalized},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if digest!=p['digest']:fail('冻结方案摘要与明细不一致')
        a=approvals.get(p['id']);consent=consents.get(p['id']);application=applications.get(p['id'])
        if a:
            proof(a['evidence_id'],case['id'],'authorization')
            if a['actor_id'] in {p['created_by'],orders[case['id']]['requested_by']}:fail('申请与主管批准不是独立复核')
        if consent:
            proof(consent['evidence_id'],case['id'],'authorization')
            if not a or consent['plan_digest']!=p['digest'] or consent['evidence_id']==a['evidence_id']:fail('客户确认没有独立绑定批准版本')
        if application:
            proof(application['evidence_id'],case['id'],'receipt')
            if not a or not consent or p['id'] in cancelled or application['case_id']!=case['id'] or data(case).get('plan_id')!=p['id']:fail('应用纠正缺少有效审批与客户确认')
            original=cases[orders[case['id']]['source_case_id']]
            if original['kind']=='order' and original['vehicle_id'] and (original['state']=='delivered' or data(original).get('dispatched_at')):
                physical=next((v for v in rows('vehicle_operations') if v['aftercare_case_id']==case['id']),None)
                if not same(physical,case) or physical['status']!='accepted' or not physical['received_vehicle_id'] or physical['source_order_id']!=original['id'] or physical['source_vehicle_id']!=original['vehicle_id']:fail('车辆费用纠正缺少原VIN实际验收入库')
            for l in ls:
                adjustment=adjustments.get(l['id']);s=sources[l['source_id']]
                discount=sum(t['discount_cents'] for t in ts if t['source_id']==s['id'] and t['kind']!='cash')
                if not same(adjustment,case) or adjustment['application_id']!=application['id'] or adjustment['source_case_id']!=s['source_case_id'] or adjustment['allocation_id']!=s['allocation_id'] or adjustment['credit_cents']!=l['credit_cents'] or adjustment['revenue_credit_cents']!=l['revenue_credit_cents']:fail('原费用减免或权益折扣回转不守恒')
                if cases[s['source_case_id']]['kind']=='insurance':
                    total=sum(a['revenue_credit_cents'] for a in adjustments.values() if a['source_case_id']==s['source_case_id'])
                    if l['revenue_credit_cents']<0 or total>data(cases[s['source_case_id']]).get('commission',0):fail('代收保费与佣金减免混淆')
                elif l['revenue_credit_cents']!=l['credit_cents']-discount:fail('经营减免与原权益折扣回转不守恒')
                old=allcredits[s['source_case_id']]
                if l['base_cents']!=s['original_cents']-old:fail('再次售后超出原剩余费用')
                allcredits[s['source_case_id']]+=l['credit_cents']
                if orders[case['id']]['scenario']!='repair_refund' and not data(cases[s['source_case_id']]).get('aftercare_ended'):fail('生效销售终止缺少原单阻断标识')
    refunded=defaultdict(int)
    for record in refunds+collections:
        p=payments.get(record['payment_link_id']);case=cases[record['case_id']];is_refund='tender_id' in record
        proof(record['evidence_id'],case['id'],'receipt')
        if not same(p,case) or p['amount_cents']<=0:fail('实际收退款没有正确原业务现金关联')
        c=cash.get(p['cash_id'])
        if not same(c,p) or c['amount_cents']!=p['amount_cents'] or c['direction']!=p['direction'] or c['approval_state']!='approved' or len([x for x in payments.values() if x['cash_id']==c['id']])!=1:fail('售后现金来源不是唯一真实现金')
        if is_refund:
            t=tenders.get(record['tender_id']);s=sources.get(t['source_id']) if t else None;original=payments.get(t['original_id']) if t else None
            if not same(t,case) or plans[t['plan_id']]['case_id']!=case['id'] or t['plan_id'] not in applications or t['kind']!='cash' or not same(original,case) or original['case_id']!=s['source_case_id'] or original['direction']!='in' or p['direction']!='out' or p['original_id']!=original['id'] or p['case_id']!=original['case_id'] or p['account_id']!=original['account_id']:fail('退款未追本方案原现金或原账户')
            refunded[t['id']]+=p['amount_cents']
            if refunded[t['id']]>t['credit_cents']:fail('本方案重复超额退款')
        else:
            s=sources.get(record['source_id'])
            if not same(s,case) or s['case_id']!=case['id'] or p['case_id']!=s['source_case_id'] or p['direction']!='in' or p['original_id']:fail('保留费收款没有正确原单')
    for original in payments.values():
        if original['direction']=='in' and sum(p['amount_cents'] for p in payments.values() if p['direction']=='out' and p['original_id']==original['id'])>original['amount_cents']:fail('原收款累计超额退回')
    # The latest actual agreement for each source must reconcile its remaining cash.
    repair_links=rows('repair_payments');tasks=rows('flow_tasks')
    extra={name:rows(name) if name in names else [] for name in ('group_payment_links','benefit_payment_links','business_finance_credit_links','repair_package_payment_links')}
    from .business_finance_partial_integrity import validate_partial_corrections_sqlite
    partial=validate_partial_corrections_sqlite(connection)
    partial_cash={b['cash_id'] for b in rows('business_finance_cash_batches') if b['case_id'] in partial['partial_case_ids']} if partial['partial_case_ids'] else set()
    events=rows('flow_events')
    for source_id,credits in allcredits.items():
        latest=max((a for a in adjustments.values() if a['source_case_id']==source_id),key=lambda a:a['application_id'])
        line=lines[latest['plan_line_id']];link=sources[line['source_id']];case=cases[link['case_id']]
        eligible={p['payment_link_id'] for p in repair_links if p['allocation_id']==link['allocation_id']} if link['allocation_id'] else None
        if json.loads(link['snapshot']).get('package_zero_customer'):eligible=set()
        paid=sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in payments.values() if p['case_id']==source_id and (eligible is None or p['id'] in eligible))
        paid+=sum(p['amount_cents'] for collection in extra.values() for p in collection if p['case_id']==source_id)
        net=link['original_cents']-credits
        remaining=sum(t['credit_cents']-refunded[t['id']] for t in tenders.values() if t['plan_id']==line['plan_id'] and t['source_id']==link['id'] and t['kind']=='cash')
        if paid<0 or net<0 or paid-net>0 and paid-net!=remaining or remaining and paid-net!=remaining:fail('当前净收费、实际净支付和方案未退额不一致')
        completions=[e for e in events if e['case_id']==case['id'] and e['action'].startswith('aftercare_') and e['after_state']=='completed']
        cutoff=max((e['occurred_at'] for e in completions),default=None)
        later_correction=bool(cutoff and case['state']=='completed' and cases[source_id]['kind']=='repair' and any(p['case_id']==source_id and p['cash_id'] in partial_cash and datetime.fromisoformat(cash[p['cash_id']]['created_at'])>datetime.fromisoformat(cutoff) for p in payments.values()))
        if later_correction:
            historic=sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in payments.values() if p['case_id']==source_id and (eligible is None or p['id'] in eligible) and datetime.fromisoformat(cash[p['cash_id']]['created_at'])<=datetime.fromisoformat(cutoff))
            for name,collection in extra.items():
                entries=by({'group_payment_links':'group_entries','benefit_payment_links':'benefit_entries','business_finance_credit_links':'business_finance_advance_entries','repair_package_payment_links':'repair_package_entries'}[name]) if collection else {}
                historic+=sum(p['amount_cents'] for p in collection if p['case_id']==source_id and datetime.fromisoformat(entries[p['entry_id']]['occurred_at'])<=datetime.fromisoformat(cutoff))
            if historic!=net or remaining:fail('后继更正不能掩盖原售后完成时未结的真实款项')
        if case['state']=='completed' and paid!=net and not later_correction:fail('已结售后仍有未结原款或保留费')
        required_case=source_id if later_correction else case['id']
        required_key='repair_receive_'+str(link['allocation_id']) if later_correction else 'aftercare_collect_'+str(link['id'])
        if paid<net and not any(t['case_id']==required_case and t['key']==required_key and t['status']=='open' for t in tasks):fail('未收保留费缺少财务责任待办')
    return {'verified_aftercare_orders':len(orders),'verified_aftercare_refunds':len(refunds)}
