"""Reconstruct service quotes, principal ownership and original-path cash on restore."""
import json
import hashlib
from datetime import datetime
from collections import defaultdict

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'service_orders' not in names:return {'verified_service_orders':0,'verified_service_tenders':0}
    def rows(table):
        columns='id,store_id,case_id,category,generated,sha256' if table=='flow_files' else '*'
        cursor=connection.execute('SELECT '+columns+' FROM '+table);keys=[x[0] for x in cursor.description];return [dict(zip(keys,r)) for r in cursor]
    def by(table,key='id'):return {r[key]:r for r in rows(table)}
    def data(v):return json.loads(v) if isinstance(v,str) else v
    def fail(s):raise ValueError('明细服务恢复检查：'+s)
    def same(a,b):return bool(a and b and a['store_id']==b['store_id'])
    cases=by('flow_cases');orders=by('service_orders');quotes=by('service_quotes');lines=by('service_lines');approvals=by('service_price_approvals','quote_id');auth=by('service_authorizations','quote_id')
    files=by('flow_files');payments=by('flow_payment_links');cash=by('cash_entries');accounts=by('flow_accounts');credits=by('business_finance_credit_links')
    advance_entries=by('business_finance_advance_entries');advances=by('business_finance_advances');batches=by('business_finance_cash_batches')
    finance_allocations=rows('business_finance_cash_allocations');payees=by('service_payees');income=by('service_income_items');agency=by('master_agency_projects')
    submissions=by('service_submissions');results=by('service_external_results','submission_id');fulfillments=by('service_fulfillments');tenders=by('service_tender_slices');pass_entries=by('service_pass_entries')
    plans=by('service_terminations');plan_approvals=by('service_termination_approvals','plan_id');consents=by('service_termination_consents','plan_id');cancelled=by('service_termination_cancellations','plan_id');applications=by('service_termination_applications','plan_id');adjustments=rows('service_charge_adjustments');refunds=rows('service_refunds')
    proof_uses=set()
    def proof(fact,case_id,financial=False,reused=False,central=False):
        f=files.get(fact['evidence_id']);c=cases.get(case_id)
        if not same(f,fact) or not same(c,fact) or f['generated'] or f['category']!=('receipt' if financial else 'authorization'):fail('凭据门店、类别或原件属性不一致')
        if f['case_id']!=case_id:
            allowed=central and any(a['case_id']==case_id and batches.get(a['batch_id'],{}).get('evidence_id')==f['id'] and batches.get(a['batch_id'],{}).get('case_id')==f['case_id'] for a in finance_allocations)
            allowed=allowed or central and any(cl['case_id']==case_id and advance_entries.get(cl['entry_id'],{}).get('evidence_id')==f['id'] and advance_entries.get(cl['entry_id'],{}).get('case_id')==f['case_id'] for cl in credits.values())
            if not allowed:fail('事实原件没有明确绑定本单或原集中资金事实')
        k=(case_id,f['sha256'])
        if not reused and k in proof_uses:fail('同一原件被重复用作不同办理事实')
        if not reused:proof_uses.add(k)
    for o in orders.values():
        c=cases.get(o['id']);snapshot=data(o['vehicle_snapshot'])
        if not same(c,o) or (c['kind'],c['flow_version']) not in {('agency',3),('other_income',2)} or c['kind']!=o['subtype']:fail('服务门店或版本身份不一致')
        if o['source_order_id']:
            s=cases.get(o['source_order_id'])
            if not same(s,c) or s['kind']!='order' or s['customer_id']!=c['customer_id'] or c['parent_id']!=s['id']:fail('关联销售跨店或客户不一致')
        elif o['delivery_blocking']:fail('无关联销售却有交车门禁')
        if snapshot:
            if snapshot.get('customer_vehicle_id'):
                vehicles=by('care_customer_vehicles');v=vehicles.get(snapshot['customer_vehicle_id'])
                if not same(v,c) or v['customer_id']!=c['customer_id'] or v['vin']!=snapshot['vin']:fail('冻结客户车辆关联不一致')
            elif snapshot.get('stock_vehicle_id') and snapshot.get('sales_quote_id'):
                car=by('vehicles').get(snapshot['stock_vehicle_id']);sales_quote=by('sales_quotes').get(snapshot['sales_quote_id']);parent=cases.get(o['source_order_id'])
                if not all(same(x,c) for x in (car,sales_quote,parent)) or parent['flow_version']!=4 or sales_quote['case_id']!=parent['id'] or not data(sales_quote['services']).get('agency') or car['vin']!=snapshot.get('vin'):fail('代办实际车辆未追本版销售约定')
                if not any(x['quote_id']==sales_quote['id'] and x['vehicle_id']==car['id'] for x in rows('sales_quote_consents')):fail('代办原车辆缺少客户本版签回')
            else:fail('冻结车辆身份来源不受支持')
    for q in quotes.values():
        c=cases.get(q['case_id']);ls=[l for l in lines.values() if l['quote_id']==q['id']]
        if not same(c,q) or c['id'] not in orders or not ls:fail('报价缺少本单明细')
        encoded=[]
        for l in ls:
            raw=(l['quantity_milli']*l['unit_price_cents']+500)//1000
            if not same(q,l) or l['amount_cents']!=raw-l['discount_cents'] or l['amount_cents']<0:fail('报价逐项数量金额或折扣不守恒')
            if l['bucket']=='pass':
                p=payees.get(l['payee_id'])
                if not same(l,p) or l['discount_cents'] or l['agency_project_id'] or l['income_item_id'] or not data(l['payee_snapshot']):fail('代缴本金被折扣或改成服务费')
            elif c['kind']=='agency':
                if not same(l,agency.get(l['agency_project_id'])) or l['payee_id'] or l['income_item_id']:fail('代办项目主档关联不一致')
            elif not same(l,income.get(l['income_item_id'])) or l['payee_id'] or l['agency_project_id']:fail('其它客户服务项目关联不一致')
            encoded.append({k:(data(l[k]) if k=='payee_snapshot' else l[k]) for k in ('line_key','bucket','agency_project_id','income_item_id','payee_id','code','name','unit','payee_snapshot','quantity_milli','unit_price_cents','discount_cents','amount_cents','due_date')})
        digest=hashlib.sha256(json.dumps({'operation':'service_quote','payload':encoded},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=q['digest'] or q['fee_cents']!=sum(l['amount_cents'] for l in ls if l['bucket']=='fee') or q['pass_cents']!=sum(l['amount_cents'] for l in ls if l['bucket']=='pass') or q['discount_cents']!=sum(l['discount_cents'] for l in ls):fail('冻结报价摘要或合计不一致')
        a=approvals.get(q['id'])
        if a:
            proof(a,c['id'])
            if a['actor_id'] in {q['actor_id'],c['created_by']} or q['fee_cents']<a['minimum_fee_cents'] and not a['allow_below_minimum']:fail('价格缺少独立主管明确授权')
        a=auth.get(q['id'])
        if a:
            proof(a,c['id'])
            if q['id'] not in approvals:fail('客户授权报价没有主管价格批准')
    for s in submissions.values():
        q=quotes.get(s['quote_id']);proof(s,s['case_id'])
        if not same(q,s) or q['case_id']!=s['case_id'] or q['id'] not in auth or not any(l['quote_id']==q['id'] and l['line_key']==s['line_key'] for l in lines.values()):fail('外部提交没有当前获准项目')
        if s['supplement_result_id']:
            prior=next((r for r in results.values() if r['id']==s['supplement_result_id']),None);original=submissions.get(prior['submission_id']) if prior else None
            if not same(prior,s) or prior['outcome']!='need_documents' or original['case_id']!=s['case_id'] or original['line_key']!=s['line_key']:fail('补件未关联本项目真实要求')
    for submission_id,r in results.items():proof(r,submissions[submission_id]['case_id'])
    for f in fulfillments.values():
        l=lines.get(f['line_id']);q=quotes.get(l['quote_id']) if l else None;proof(f,f['case_id'])
        if not same(l,f) or q['case_id']!=f['case_id'] or q['id'] not in auth or l['line_key']!=f['line_key'] or f['amount_cents']!=l['amount_cents']:fail('实际办结未绑定原授权价格')
        if cases[f['case_id']]['kind']=='agency' and not any(s['case_id']==f['case_id'] and s['line_key']==f['line_key'] and results.get(s['id'],{}).get('outcome')=='approved' for s in submissions.values()):fail('代办办结缺少真实批准结果')
    tender_totals=defaultdict(int);credit_totals=defaultdict(int);reversed_totals=defaultdict(int);spent=defaultdict(int);refund_by_tender=defaultdict(int)
    for t in tenders.values():
        l=lines.get(t['line_id']);q=quotes.get(l['quote_id']) if l else None
        if not same(l,t) or q['case_id']!=t['case_id'] or l['line_key']!=t['line_key'] or l['bucket']!=t['bucket'] or q['id'] not in auth:fail('客户资金未分配到本单原授权项目')
        proof(t,t['case_id'],True,reused=True,central=True)
        if t['payment_link_id']:
            p=payments.get(t['payment_link_id'])
            if not same(p,t) or p['case_id']!=t['case_id'] or (p['direction']=='in')!=(t['amount_cents']>0):fail('客户资金分配方向或原单不一致')
            tender_totals[p['id']]+=t['amount_cents']
        else:
            cr=credits.get(t['credit_link_id'])
            if not same(cr,t) or cr['case_id']!=t['case_id'] or (cr['amount_cents']>0)!=(t['amount_cents']>0):fail('预收抵用与明细分配不一致')
            credit_totals[cr['id']]+=t['amount_cents']
        if t['amount_cents']<0:
            orig=tenders.get(t['original_id'])
            if not same(orig,t) or orig['amount_cents']<=0 or any(orig[k]!=t[k] for k in ('case_id','line_id','line_key','bucket')):fail('客户退款未追溯同一原行分配')
            if t['payment_link_id'] and payments[t['payment_link_id']]['original_id']!=orig['payment_link_id'] or t['credit_link_id'] and credits[t['credit_link_id']]['original_id']!=orig['credit_link_id']:fail('客户退回替换了原现金或预收来源')
            reversed_totals[orig['id']]-=t['amount_cents']
        elif t['original_id']:fail('正向客户资金不应伪装退款')
    for p in payments.values():
        if p['case_id'] in orders and tender_totals[p['id']]!=p['amount_cents']*(1 if p['direction']=='in' else -1):fail('单笔真实收退款与全部服务明细分配不守恒')
    for cr in credits.values():
        if cr['case_id'] in orders and credit_totals[cr['id']]!=cr['amount_cents']:fail('预收净抵用与明细分配不守恒')
    used_cash=set()
    for e in pass_entries.values():
        t=tenders.get(e['tender_id']);c=cash.get(e['cash_id']);a=accounts.get(e['account_id']);proof(e,e['case_id'],True)
        if not same(t,e) or t['case_id']!=e['case_id'] or t['bucket']!='pass' or t['amount_cents']<=0 or any(t[k]!=e[k] for k in ('line_id','line_key')):fail('代缴未引用原客户本金')
        if t['payment_link_id']:original_account=payments[t['payment_link_id']]['account_id']
        else:original_account=advances[advance_entries[credits[t['credit_link_id']]['entry_id']]['advance_id']]['account_id']
        if not same(c,e) or not same(a,e) or a['id']!=original_account or c['account']!=a['name'] or c['amount_cents']!=e['amount_cents'] or c['voucher_no']!=e['reference'] or c['business_date']!=e['business_date']:fail('实际代缴账户、金额、日期或凭证与原本金不一致')
        if e['cash_id'] in used_cash or any(p['cash_id']==e['cash_id'] for p in payments.values()):fail('代缴现金重复记作客户退款')
        used_cash.add(e['cash_id'])
        if e['purpose']=='disburse':
            if e['original_id'] or c['direction']!='out' or c['category']!='service_pass_pay':fail('代缴支出方向或分类错误')
            spent[t['id']]+=e['amount_cents']
        else:
            original=pass_entries.get(e['original_id'])
            if not same(original,e) or original['purpose']!='disburse' or original['tender_id']!=t['id'] or c['direction']!='in' or c['category']!='service_pass_return':fail('第三方返回不是原代缴账户路径')
            if sum(x['amount_cents'] for x in pass_entries.values() if x['original_id']==original['id'])>original['amount_cents']:fail('第三方退回超过原实际支出')
            spent[t['id']]-=e['amount_cents']
    for p in plans.values():
        q=quotes.get(p['quote_id']);ls=data(p['lines']);selected=data(p['returns']);proof(p,p['case_id'])
        if not same(q,p) or q['case_id']!=p['case_id'] or q['id'] not in auth:fail('终止不是本单授权报价')
        digest=hashlib.sha256(json.dumps({'operation':'service_termination','payload':[ls,selected]},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=p['digest']:fail('终止方案冻结摘要不一致')
        if len({x['line_key'] for x in ls})!=len(ls) or {x['line_key'] for x in ls}!={l['line_key'] for l in lines.values() if l['quote_id']==q['id']}:fail('终止遗漏或重复原明细')
        for x in ls:
            l=lines.get(x['line_id'])
            if not same(l,p) or l['quote_id']!=q['id'] or any(l[k]!=x[k] for k in ('line_key','bucket')) or x['base_cents']!=x['retained_cents']+x['credit_cents'] or min(x['retained_cents'],x['credit_cents'])<0:fail('终止保留费与减免不守恒')
        if p['id'] in plan_approvals:
            a=plan_approvals[p['id']];proof(a,p['case_id'])
            if a['actor_id'] in {p['actor_id'],cases[p['case_id']]['created_by']}:fail('终止缺少独立复核')
        if p['id'] in consents:
            proof(consents[p['id']],p['case_id'])
            if p['id'] not in plan_approvals:fail('客户同意前没有批准终止方案')
        if p['id'] in applications:
            app=applications[p['id']];proof(app,p['case_id'],True)
            if p['id'] not in consents or p['id'] in cancelled:fail('生效方案未获客户同意或已撤回')
            actual=[a for a in adjustments if a['application_id']==app['id']]
            if {(a['line_id'],a['amount_cents']) for a in actual}!={(x['line_id'],-x['credit_cents']) for x in ls if x['credit_cents']}:fail('净收费调整与获准逐行减免不一致')
        if len({x['tender_id'] for x in selected})!=len(selected):fail('终止退款重复选择同一原款')
        for x in selected:
            t=tenders.get(x['tender_id'])
            if not same(t,p) or t['case_id']!=p['case_id'] or t['amount_cents']<=0 or x['amount_cents']<=0:fail('终止退款选择其它单款项')
    for r in refunds:
        p=plans.get(r['plan_id']);original=tenders.get(r['original_tender_id']);reverse=tenders.get(r['reversal_tender_id'])
        if not same(p,r) or not same(original,r) or not same(reverse,r) or p['id'] not in applications or reverse['original_id']!=original['id'] or reverse['amount_cents']!=-r['amount_cents']:fail('退款没有对应生效方案及原分配冲正')
        proof(r,p['case_id'],True)
        if reverse['evidence_id']!=r['evidence_id']:fail('退款原件与资金冲正不一致')
        permitted=sum(x['amount_cents'] for x in data(p['returns']) if x['tender_id']==original['id'])
        if sum(x['amount_cents'] for x in refunds if x['plan_id']==p['id'] and x['original_tender_id']==original['id'])>permitted:fail('实际客户退款超过批准的原款上限')
        refund_by_tender[original['id']]+=r['amount_cents']
    for t in tenders.values():
        if t['amount_cents']>0 and (reversed_totals[t['id']]+spent[t['id']]>t['amount_cents'] or spent[t['id']]<0):fail('原客户资金退款及第三方净使用超过原额')
    # Later quotes cannot silently replace a line already referenced by actual
    # money or fulfillment; original IDs stay on the immutable facts.
    protected={t['line_id'] for t in tenders.values()}|{f['line_id'] for f in fulfillments.values()}
    protected|={l['id'] for s in submissions.values() for l in lines.values() if l['quote_id']==s['quote_id'] and l['line_key']==s['line_key']}
    for lid in protected:
        original=lines[lid];q=quotes[original['quote_id']]
        for newer in quotes.values():
            if newer['case_id']!=q['case_id'] or newer['revision']<=q['revision']:continue
            l=next((l for l in lines.values() if l['quote_id']==newer['id'] and l['line_key']==original['line_key']),None)
            if not l or any(data(l[k])!=data(original[k]) if k=='payee_snapshot' else l[k]!=original[k] for k in ('bucket','agency_project_id','income_item_id','payee_id','quantity_milli','unit_price_cents','discount_cents','amount_cents','due_date','payee_snapshot')):fail('后续报价修改或删除已有真实事实的原明细')
    for a in adjustments:
        if not any(app['id']==a['application_id'] for app in applications.values()) or a['amount_cents']>=0:fail('发现无原方案净额调整')
    for o in orders.values():
        cid=o['id'];q=quotes.get(data(cases[cid]['data']).get('service_quote_id'))
        if not q:continue
        for l in [l for l in lines.values() if l['quote_id']==q['id']]:
            if l['amount_cents']+sum(a['amount_cents'] for a in adjustments if a['case_id']==cid and a['line_key']==l['line_key'])<0:fail('原项目累计减免超过原收费')
    return {'verified_service_orders':len(orders),'verified_service_tenders':len(tenders)}

def validate_parent_aftercare_exclusions(connection,parent_id,excluded_ids,requested_at=None):
    """Validate original independent resolution as of the parent request.

    The immutable command event timestamps and actual cash/advance entry times
    provide the cutoff. A legitimate later third-party return cannot rewrite a
    previously completed parent return's exclusion proof.
    """
    def rows(name):
        c=connection.execute('SELECT * FROM '+name);keys=[v[0] for v in c.description];return [dict(zip(keys,r)) for r in c]
    def parsed(v):return json.loads(v) if isinstance(v,str) else v
    def dt(v):return datetime.fromisoformat(v.replace('Z','+00:00')).replace(tzinfo=None) if isinstance(v,str) else v.replace(tzinfo=None)
    limit=dt(requested_at) if requested_at else datetime.max
    def before(v):return dt(v)<=limit
    def fail(msg):raise ValueError('明细服务售后排除检查：'+msg)
    cases={r['id']:r for r in rows('flow_cases')};parent=cases.get(parent_id)
    if not parent or parent['kind']!='order':fail('排除证明缺少原销售')
    expected=[r for r in rows('service_orders') if r['source_order_id']==parent_id and before(cases[r['id']]['created_at'])]
    if sorted(excluded_ids)!=sorted(r['id'] for r in expected) or len(set(excluded_ids))!=len(excluded_ids):fail('冻结排除清单与申请时已存在的明细服务不一致')
    events=[r for r in rows('flow_events') if before(r['occurred_at'])]
    def happened(case_id,action,**values):
        return any(e['case_id']==case_id and e['action']=='serviceorder_'+action and all(parsed(e['detail']).get(k)==v for k,v in values.items()) for e in events)
    quotes={r['id']:r for r in rows('service_quotes')};lines=rows('service_lines');plans=rows('service_terminations');applications=rows('service_termination_applications');adjustments=rows('service_charge_adjustments');tenders=rows('service_tender_slices')
    payments={r['id']:r for r in rows('flow_payment_links')};cash={r['id']:r for r in rows('cash_entries')};credits={r['id']:r for r in rows('business_finance_credit_links')};advance={r['id']:r for r in rows('business_finance_advance_entries')};passes=rows('service_pass_entries')
    approvals={r['plan_id']:r for r in rows('service_termination_approvals')};consents={r['plan_id']:r for r in rows('service_termination_consents')}
    for order in expected:
        cid=order['id'];c=cases[cid]
        if c['store_id']!=parent['store_id'] or c['customer_id']!=parent['customer_id'] or c['parent_id']!=parent_id:fail('被排除服务跨店、跨客户或替换原销售')
        if happened(cid,'cancel'):
            if any(t['case_id']==cid for t in tenders) or any(r['case_id']==cid for r in rows('service_submissions')) or any(r['case_id']==cid for r in rows('service_fulfillments')):fail('普通取消的服务存在真实资金或履约')
            continue
        own=[p for p in plans if p['case_id']==cid and happened(cid,'termination',evidence_id=p['evidence_id'])]
        active=[p for p in own if not happened(cid,'termination_cancel',plan_id=p['id']) and not happened(cid,'termination_apply',plan_id=p['id'])]
        applied=[a for a in applications if any(p['id']==a['plan_id'] for p in own) and happened(cid,'termination_apply',plan_id=a['plan_id'],evidence_id=a['evidence_id'])]
        if active or not applied:fail('申请当时服务没有完成明确终止及客户保留费确认')
        for app in applied:
            a=approvals.get(app['plan_id']);consent=consents.get(app['plan_id'])
            if not a or not consent or not happened(cid,'termination_approve',plan_id=app['plan_id'],evidence_id=a['evidence_id']) or not happened(cid,'consent',plan_id=app['plan_id'],evidence_id=consent['evidence_id']):fail('申请当时终止缺少主管及客户同意事实')
        q=max((q for q in quotes.values() if q['case_id']==cid and before(q['created_at'])),key=lambda q:q['revision'])
        net={l['line_key']:l['amount_cents'] for l in lines if l['quote_id']==q['id']};paid=defaultdict(int);pass_paid=0;pass_spent=0
        for a in adjustments:
            if a['case_id']==cid and any(p['id']==a['application_id'] for p in applied):net[a['line_key']]+=a['amount_cents']
        for t in tenders:
            if t['case_id']!=cid:continue
            when=cash[payments[t['payment_link_id']]['cash_id']]['created_at'] if t['payment_link_id'] else advance[credits[t['credit_link_id']]['entry_id']]['occurred_at']
            if before(when):
                paid[t['line_key']]+=t['amount_cents']
                if t['bucket']=='pass':pass_paid+=t['amount_cents']
        for p in passes:
            if p['case_id']==cid and before(cash[p['cash_id']]['created_at']):pass_spent+=p['amount_cents']*(1 if p['purpose']=='disburse' else -1)
        if any(paid[k]!=amount for k,amount in net.items()) or pass_paid!=pass_spent:fail('申请当时独立服务的原客户款或代缴本金未结清')
    return True
