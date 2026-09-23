"""Reconstruct claim approvals, responsibility deltas and every original cash path."""
import json
from collections import defaultdict

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'claims_orders' not in names:return {'verified_claims':0,'verified_claim_cash':0}
    def rows(name):
        columns='id,store_id,case_id,category,generated,sha256' if name=='flow_files' else '*'
        c=connection.execute('SELECT '+columns+' FROM '+name);keys=[v[0] for v in c.description];return [dict(zip(keys,r)) for r in c]
    def by(name,key='id'):return {r[key]:r for r in rows(name)}
    def fail(message):raise ValueError('理赔恢复检查：'+message)
    def same(a,b):return a and b and a['store_id']==b['store_id']
    def data(v):return json.loads(v) if isinstance(v,str) else v
    cases=by('flow_cases');orders=by('claims_orders');assessments=by('claims_assessments');approvals=by('claims_approvals','assessment_id')
    transmissions=by('claims_transmissions');results=by('claims_results');bindings=by('claims_bindings');resolutions=by('claims_resolutions')
    resolution_approvals=by('claims_resolution_approvals','resolution_id');applications=by('claims_applications','resolution_id');responsibilities=rows('claims_responsibility_entries')
    reimbursement=by('claims_reimbursement_approvals','case_id');claims_cash=by('claims_cash');direct=by('claims_customer_payments')
    plans=by('claims_return_plans');return_approvals=by('claims_return_approvals','plan_id');cancelled=by('claims_return_cancellations','plan_id');closures=by('claims_closures','case_id')
    files=by('flow_files');quotes=by('repair_quotes');lines=by('repair_lines');allocations=by('repair_allocations');payments=by('flow_payment_links');cash=by('cash_entries');repair_payments=by('repair_payments','payment_link_id')
    insurers=by('master_insurers');manufacturers=by('flow_references')
    proof_uses=set()
    def proof(record,case_id,financial=False):
        f=files.get(record['evidence_id']);c=cases[case_id]
        if not same(record,c) or not same(f,c) or f['case_id']!=case_id or f['generated'] or f['category']!=('receipt' if financial else 'authorization'):fail('事实原件没有绑定本核赔单和正确类别')
        key=(case_id,f['sha256'])
        if key in proof_uses:fail('同一原件被重复用于不同实际事实')
        proof_uses.add(key)
    def amount(record):
        p=payments.get(record['payment_link_id'])
        if not same(p,record):fail('现金关联缺少本店原支付链接')
        return p['amount_cents']
    def paid(allocation):return sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in payments.values() if repair_payments.get(p['id'],{}).get('allocation_id')==allocation['id'])
    def selected(record,limit_lines):
        parts=data(record['lines']);seen=set();total=0
        for l in parts:
            original=limit_lines.get(l['line_id'])
            if not original or l['line_id'] in seen or l['quantity_milli']<=0 or l['quantity_milli']>original['quantity_milli'] or not 0<=l['amount_cents']<=original['amount_cents']*l['quantity_milli']//original['quantity_milli']:fail('逐行核损数量、金额或原明细关联越界')
            if any(l[k]!=original[k] for k in ('line_key','kind','name','code','unit')):fail('核损明细快照被更换')
            seen.add(l['line_id']);total+=l['amount_cents']
        if total!=record['amount_cents']:fail('核价／核赔逐项金额不守恒')
    for order in orders.values():
        c=cases.get(order['id']);s=cases.get(order['source_case_id']);snapshot=data(order['source_snapshot'])
        if not same(c,order) or c['kind']!='claim' or c['flow_version']!=2 or not same(s,c) or s['kind']!='repair' or s['flow_version'] not in (3,4) or c['customer_id']!=s['customer_id'] or c['parent_id']!=s['id']:fail('原维修客户、门店或流程版本关联异常')
        if any(snapshot[k]!=s[k] for k in ('number','customer_id','flow_version')):fail('冻结原维修身份不一致')
        if (order['party_type']=='internal')!=(order['payment_route']=='internal'):fail('内部核价不能伪造外部报销')
        if order['party_type']=='insurer' and not same(order,insurers.get(order['insurer_id'])):fail('保险主体跨店或缺少原主档')
        if order['party_type']=='manufacturer' and (not same(order,manufacturers.get(order['manufacturer_id'])) or manufacturers[order['manufacturer_id']]['category']!='厂家'):fail('厂家主体跨店或使用其他类别主档')
    def same_payer(order,allocation):
        return allocation['payer_type']==order['party_type'] and (allocation['insurer_id']==order['insurer_id'] if order['party_type']=='insurer' else allocation['manufacturer_id']==order['manufacturer_id'] if order['party_type']=='manufacturer' else allocation['payer_name']==order['party_name'])
    for a in assessments.values():
        o=orders.get(a['case_id']);q=quotes.get(a['quote_id'])
        if not same(o,a) or not same(q,a) or q['case_id']!=o['source_case_id'] or a['quote_digest']!=q['digest'] or a['amount_cents']<=0:fail('核价不是原维修报价版本')
        selected(a,{l['id']:l for l in lines.values() if l['quote_id']==q['id']})
        approval=approvals.get(a['id'])
        if approval:
            proof(approval,a['case_id'])
            if approval['actor_id'] in (a['actor_id'],cases[a['case_id']]['created_by']):fail('申请／核价与主管复核不是独立员工')
    for t in transmissions.values():
        a=assessments.get(t['assessment_id']);proof(t,t['case_id'])
        if not same(t,a) or t['case_id']!=a['case_id'] or a['id'] not in approvals:fail('外部提交没有对应获准核价')
        if t['supplement_result_id']:
            r=results.get(t['supplement_result_id'])
            if not same(t,r) or r['case_id']!=t['case_id'] or r['assessment_id']!=a['id'] or r['outcome']!='need_documents' or r['result_on']>t['submitted_on']:fail('补件没有关联原要求')
    for r in results.values():
        t=transmissions.get(r['transmission_id']);a=assessments.get(r['assessment_id']);proof(r,r['case_id'])
        if not same(r,t) or t['case_id']!=r['case_id'] or t['assessment_id']!=r['assessment_id'] or r['result_on']<t['submitted_on']:fail('外部结果未关联原提交')
        selected(r,{l['line_id']:l for l in data(a['lines'])})
        if r['outcome'] in ('need_documents','rejected') and r['amount_cents'] or r['outcome']=='approved' and r['amount_cents']!=a['amount_cents'] or r['outcome']=='partial' and not 0<r['amount_cents']<a['amount_cents']:fail('外部结果状态和金额不一致')
    for b in bindings.values():
        o=orders.get(b['case_id']);a=allocations.get(b['allocation_id']);assessment=assessments.get(b['assessment_id']);result=results.get(b['result_id'])
        if not same(b,o) or not same(a,b) or a['case_id']!=o['source_case_id'] or not same_payer(o,a) or not same(assessment,b) or assessment['case_id']!=o['id'] or assessment['id'] not in approvals:fail('原承担绑定无有效核价或关联错误')
        value=assessment['amount_cents'] if o['party_type']=='internal' else result['amount_cents'] if same(result,b) and result['case_id']==o['id'] else -1
        if b['approved_cents']!=value or value>a['amount_cents']:fail('绑定金额不是核准承担金额')
    applied_delta=defaultdict(int);expected_entries=set()
    for r in resolutions.values():
        o=orders.get(r['case_id']);a=allocations.get(r['allocation_id']);result=results.get(r['result_id']);proof(r,r['case_id'])
        if not same(r,o) or o['payment_route']!='repair_receivable' or not same(a,r) or a['case_id']!=o['source_case_id'] or not same_payer(o,a) or not same(result,r) or result['case_id']!=o['id'] or r['original_cents']-r['reduction_cents']!=result['amount_cents']:fail('责任调减没有对应原承担及核准差额')
        selections=data(r['refunds']);seen=set()
        if sum(s['amount_cents'] for s in selections)!=r['refund_cents']:fail('原款退款方案不守恒')
        for s in selections:
            p=payments.get(s['original_id']);rp=repair_payments.get(s['original_id'])
            if not same(p,r) or p['id'] in seen or p['direction']!='in' or not rp or rp['allocation_id']!=a['id'] or not 0<s['amount_cents']<=p['amount_cents']:fail('责任退款选择了其他承担方或超额原款')
            seen.add(p['id'])
        approval=resolution_approvals.get(r['id']);application=applications.get(r['id'])
        if approval:
            proof(approval,o['id'])
            if approval['actor_id']==r['actor_id']:fail('责任调整未独立批准')
        if application:
            proof(application,o['id'],True)
            if not approval or cases[o['id']]['state']=='cancelled' or sum(amount(c) for c in claims_cash.values() if c['resolution_id']==r['id'])!=r['refund_cents']:fail('责任生效缺批准或原款实际退款')
            entries=[e for e in responsibilities if e['application_id']==application['id']]
            if len(entries)!=2 or sorted(e['amount_cents'] for e in entries)!=[-r['reduction_cents'],r['reduction_cents']] or any(not same(e,r) or e['source_case_id']!=o['source_case_id'] for e in entries):fail('外部调减与内部吸收不守恒')
            external=next(e for e in entries if e['amount_cents']<0);internal=next(e for e in entries if e['amount_cents']>0)
            if external['allocation_id']!=a['id'] or external['payer_type']!=a['payer_type'] or internal['allocation_id'] is not None or internal['payer_type']!='internal' or internal['payer_name']!=r['internal_bearer']:fail('责任分录错误转移客户或其他第三方债务')
            applied_delta[a['id']]+=r['reduction_cents'];expected_entries.update(e['id'] for e in entries)
    if {e['id'] for e in responsibilities}!=expected_entries:fail('存在无生效方案的责任分录')
    if any(v>allocations[k]['amount_cents'] or paid(allocations[k])>allocations[k]['amount_cents']-v for k,v in applied_delta.items()):fail('累计责任调减越过原金额或实际已收款')
    for a in reimbursement.values():
        o=orders.get(a['case_id']);r=results.get(a['result_id']);proof(a,a['case_id'])
        if not same(a,o) or o['payment_route'] not in ('customer_direct','customer_via_store') or not same(r,a) or r['case_id']!=o['id'] or a['amount_cents']!=r['amount_cents'] or a['actor_id'] in (cases[o['id']]['created_by'],assessments[r['assessment_id']]['actor_id'],r['actor_id']):fail('客户报销缺少独立批准或实际核准额度')
    cash_used=defaultdict(int);cash_link_ids=set()
    for c in claims_cash.values():
        o=orders[c['case_id']];p=payments.get(c['payment_link_id']);proof(c,c['case_id'],True);value=amount(c);money=cash.get(p['cash_id']);cash_link_ids.add(p['id'])
        if not same(money,c) or money['direction']!=p['direction'] or money['amount_cents']!=value or money['business_date']!=p['business_date'] or money['voucher_no']!=p['reference']:fail('实际公司现金与支付链接不一致')
        expected_direction='in' if c['purpose'] in ('pass_receive','customer_return') else 'out'
        if p['direction']!=expected_direction:fail('实际款项方向不符原路径')
        if c['purpose']=='thirdparty_refund':
            r=resolutions.get(c['resolution_id']);rp=repair_payments.get(p['id']);original=payments.get(p['original_id'])
            if not same(r,c) or r['case_id']!=o['id'] or r['id'] not in resolution_approvals or p['case_id']!=o['source_case_id'] or not rp or rp['allocation_id']!=r['allocation_id'] or rp['evidence_id']!=c['evidence_id'] or not same(original,c):fail('第三方退款缺原承担或对应原单证明')
            cash_used[(r['id'],p['original_id'])]+=value
            selected_amount=sum(s['amount_cents'] for s in data(r['refunds']) if s['original_id']==p['original_id'])
            if cash_used[(r['id'],p['original_id'])]>selected_amount or p['account_id']!=original['account_id']:fail('第三方退款超过批准原款或变换账户')
        else:
            if o['payment_route']!='customer_via_store' or p['case_id']!=o['id'] or o['id'] not in reimbursement:fail('非经店报销生成了公司现金')
            original=claims_cash.get(c['original_id'])
            if c['purpose']=='pass_receive':
                if original or p['original_id']:fail('首次报销到账不应借用另一款项')
            else:
                expected={'pass_pay':'pass_receive','customer_return':'pass_pay','party_return':'customer_return','unused_refund':'pass_receive'}[c['purpose']]
                if not same(original,c) or original['case_id']!=o['id'] or original['purpose']!=expected:fail('返还／转付没有关联同路径原实际款')
                op=payments[original['payment_link_id']]
                if p['account_id']!=op['account_id'] or p['original_id']!=(None if c['purpose']=='customer_return' else op['id']):fail('原账户或支付原款链接被替换')
                cash_used[(c['purpose'],original['id'])]+=value
                if cash_used[(c['purpose'],original['id'])]>amount(original):fail('累计返还／转付超过原实际款')
                if c['purpose']=='party_return' and c['return_plan_id']!=original['return_plan_id']:fail('退第三方借用了其他返还方案现金')
    if {p['id'] for p in payments.values() if p['case_id'] in orders}!=cash_link_ids.intersection({p['id'] for p in payments.values() if p['case_id'] in orders}):fail('核赔单存在无实际款项事实的支付链接')
    for p in direct.values():
        o=orders[p['case_id']];proof(p,p['case_id'],True)
        if o['payment_route']!='customer_direct' or o['id'] not in reimbursement:fail('直接客户报销路径错误或未经独立批准')
        if p['purpose']=='return':
            original=direct.get(p['original_id'])
            if not same(p,original) or original['case_id']!=p['case_id'] or original['purpose']!='reimbursement':fail('直接返还没有对应原实际报销')
        elif p['original_id'] or p['return_plan_id']:fail('首次直接报销不能借用返还方案')
    def returned(o,key,plan=None,external=False):
        if o['payment_route']=='customer_direct':return sum(p['amount_cents'] for p in direct.values() if p['original_id']==key and p['purpose']=='return' and (plan is None or p['return_plan_id']==plan))
        if claims_cash[key]['purpose']=='pass_receive':return sum(amount(c) for c in claims_cash.values() if c['original_id']==key and c['purpose']=='unused_refund' and (plan is None or c['return_plan_id']==plan))
        incoming=[c for c in claims_cash.values() if c['purpose']=='customer_return' and c['original_id']==key and (plan is None or c['return_plan_id']==plan)]
        return sum(amount(p) for c in incoming for p in claims_cash.values() if p['original_id']==c['id'] and p['purpose']=='party_return') if external else sum(amount(c) for c in incoming)
    reserved=defaultdict(int)
    for plan in plans.values():
        o=orders[plan['case_id']];proof(plan,plan['case_id']);selection=data(plan['selections']);a=return_approvals.get(plan['id']);cancel=cancelled.get(plan['id'])
        if sum(s['amount_cents'] for s in selection)!=plan['amount_cents'] or len({s['original_id'] for s in selection})!=len(selection):fail('原报销返还方案金额不守恒或重复选择')
        if a:
            proof(a,plan['case_id'])
            if a['actor_id']==plan['actor_id']:fail('原报销返还未独立批准')
        if cancel:proof(cancel,plan['case_id'])
        for s in selection:
            original=(direct if o['payment_route']=='customer_direct' else claims_cash).get(s['original_id'])
            if not same(original,plan) or original['case_id']!=o['id'] or original['purpose'] not in (('reimbursement',) if o['payment_route']=='customer_direct' else ('pass_pay','pass_receive')):fail('返还方案关联了其他路径原报销')
            value=original['amount_cents'] if o['payment_route']=='customer_direct' else amount(original);done=returned(o,original['id'],plan['id'])
            if done>s['amount_cents'] or done and (not a or cancel):fail('实际返还超过批准方案或方案无效')
            if a and not cancel:reserved[(o['id'],original['id'])]+=s['amount_cents']
            if o['payment_route']=='customer_via_store' and original['purpose']=='pass_receive':value-=sum(amount(c) for c in claims_cash.values() if c['purpose']=='pass_pay' and c['original_id']==original['id'])
            if reserved[(o['id'],original['id'])]>value:fail('并存批准返还超过原实际报销')
    for fact in list(direct.values())+list(claims_cash.values()):
        if fact['purpose'] in ('return','customer_return','party_return','unused_refund'):
            plan=plans.get(fact['return_plan_id'])
            if not same(plan,fact) or plan['case_id']!=fact['case_id'] or plan['id'] not in return_approvals or plan['id'] in cancelled:fail('实际原路径返还缺少有效批准方案')
            original_id=claims_cash[fact['original_id']]['original_id'] if fact['purpose']=='party_return' else fact['original_id']
            if original_id not in {s['original_id'] for s in data(plan['selections'])}:fail('实际返还借用了批准方案之外的原款')
    usage=defaultdict(int)
    for o in orders.values():
        a=reimbursement.get(o['id']);close=closures.get(o['id'])
        if close:proof(close,o['id'])
        if not a:continue
        collected=sum(amount(c) for c in claims_cash.values() if c['case_id']==o['id'] and c['purpose']=='pass_receive')
        payout=sum(p['amount_cents'] for p in direct.values() if p['case_id']==o['id'] and p['purpose']=='reimbursement') if o['payment_route']=='customer_direct' else sum(amount(c) for c in claims_cash.values() if c['case_id']==o['id'] and c['purpose']=='pass_pay')
        external=sum(p['amount_cents'] for p in direct.values() if p['case_id']==o['id'] and p['purpose']=='return') if o['payment_route']=='customer_direct' else sum(amount(c) for c in claims_cash.values() if c['case_id']==o['id'] and c['purpose']=='party_return')
        unused=sum(amount(c) for c in claims_cash.values() if c['case_id']==o['id'] and c['purpose']=='unused_refund')
        if max(collected,payout)>a['amount_cents'] or external>payout or close and (close['unused_cents']!=a['amount_cents']-payout or o['payment_route']=='customer_via_store' and collected!=payout+unused):fail('客户批准额、实际支付或未用结案额度不守恒')
        usage[o['source_case_id']]+=a['amount_cents']-(close['unused_cents'] if close else 0)-external
    for source_id,value in usage.items():
        a=next((a for a in allocations.values() if a['case_id']==source_id and a['payer_type']=='customer'),None)
        if not a or value>paid(a):fail('跨案件实际报销及有效占额超过原客户现金净付款')
    return {'verified_claims':len(orders),'verified_claim_cash':len(claims_cash),'verified_claim_direct_facts':len(direct)}
