"""Standalone read-only SQLite validation of mixed component contracts and returns."""
import hashlib,json
from datetime import datetime,date

TABLES=('repair_package_rules','repair_package_rule_decisions','repair_package_mappings','repair_package_purchases','repair_package_purchase_events','repair_package_lots','repair_package_holds','repair_package_entries','repair_package_reservation_links','repair_package_payment_links','repair_package_settlements','repair_package_refunds','repair_package_refund_claims','repair_package_aftercare_holds','repair_package_stock_returns','repair_package_quote_snapshots')
def canonical(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def value(v):return json.loads(v) if isinstance(v,str) else v
def subtract(spans,cuts):
    result=[list(p) for p in spans]
    for a,b in cuts:result=[r for x,y in result for r in ([[x,y]] if b<=x or a>=y else ([[x,a]] if x<a else [])+([[b,y]] if b<y else []))]
    return sorted(result)
def fail(message):raise ValueError('混合维修套餐恢复检查：'+message)
def check(ok,message):
    if not ok:fail(message)
def quote_contract(connection,case_id,quote_id):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repair_package_quote_snapshots'").fetchone():return None
    row=connection.execute('SELECT contract,digest,case_id FROM repair_package_quote_snapshots WHERE quote_id=?',(quote_id,)).fetchone()
    if not row:return None
    c=value(row[0]);check(row[2]==case_id and row[1]==canonical(c),'报价套餐契约摘要错误');return c
def quote_digest(connection,case_id,quote_id):
    c=quote_contract(connection,case_id,quote_id);return canonical(c) if c is not None else None
def member_quote_basis(connection,case_id,quote_id,line_key):
    c=quote_contract(connection,case_id,quote_id)
    if c is None:return None
    p=next((p for p in c['lines'] if p['line_key']==line_key),None)
    check(p is not None,'会员报价中的套餐行缺原合同')
    return {'basis_cents':p['credit_cents'],'carry_cents':0,'contract_rule_id':p['rule_id'],'contract_component_id':p['component_key']}
def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    zero={'verified_repair_package_purchases':0,'verified_repair_package_lots':0,'verified_repair_package_entries':0,'verified_repair_package_refunds':0}
    if not set(TABLES)&names:
        if 'flow_events' in names and connection.execute("SELECT 1 FROM flow_events WHERE action='repair_package_propose' LIMIT 1").fetchone():fail('新业务事件存在但套餐表缺失')
        return zero
    check(set(TABLES)<=names,'组件事实表不完整')
    def rows(table):
        cursor=connection.execute('SELECT * FROM '+table);cols=[x[0] for x in cursor.description]
        return [dict(zip(cols,row)) for row in cursor.fetchall()]
    tables={n:rows(n) for n in TABLES}
    def by(table,key='id'):return {r[key]:r for r in tables.get(table,rows(table))}
    rules=by('repair_package_rules');purchases=by('repair_package_purchases');lots=by('repair_package_lots');holds=by('repair_package_holds');entries=by('repair_package_entries');refunds=by('repair_package_refunds');after=by('repair_package_aftercare_holds')
    cases=by('flow_cases');cash=by('cash_entries');files=by('flow_files');quotes=by('repair_quotes');lines=by('repair_lines');members=by('group_members');accounts=by('flow_accounts');stocks=by('repair_stock');moves=by('flow_stock_moves')
    links=rows('group_identity_links');authorizations=rows('repair_authorizations');settled={x['case_id']:x for x in rows('repair_settlements')};quote_cancelled={x['quote_id'] for x in rows('repair_quote_cancellations')}
    def proof(key,case_id,category=None):
        f=files.get(key);check(f and f['case_id']==case_id and f['store_id']==cases[case_id]['store_id'] and not f['generated'] and (not category or f['category']==category),'原凭据门店/业务/类别不一致')
    def identity(p,row):
        m=members.get(p['member_id']);check(m and any(l['store_id']==row['store_id'] and l['local_kind']=='customer' and l['local_id']==row['customer_id'] and l['identity_id']==m['identity_id'] for l in links),'原客户身份关联不一致')
    def spans(lot,raw):
        s=value(raw);check(isinstance(s,list) and s and all(isinstance(p,list) and len(p)==2 and all(type(n)is int for n in p) and 0<=p[0]<p[1]<=lot['quantity_milli'] for p in s),'原数量区间非法')
        check(s==sorted(s) and all(a[1]<=b[0] for a,b in zip(s,s[1:])),'原数量区间重叠')
        return s
    def amounts(lot,s):return {'quantity_milli':sum(b-a for a,b in s),**{k:sum(lot[k]*b//lot['quantity_milli']-lot[k]*a//lot['quantity_milli'] for a,b in s) for k in ('credit_cents','paid_cents','settlement_cents')}}
    def money(lot,obj):
        s=spans(lot,obj['spans']);a=amounts(lot,s);check(all(obj[k]==a[k] for k in a),'原数量区间C/P/S不守恒');return s
    for r in rules.values():
        c=value(r['contract']);check(r['definition_version']==c['definition_version']==1 and r['issuer_store_id']==c['issuer_store_id'] and r['digest']==canonical(c),'原规则摘要不一致')
        cs=c['components'];check(len({x['key'] for x in cs})==len(cs) and {'work','part'}<={x['kind'] for x in cs},'原组件重复或非混合产品')
        for x in cs:check(x['quantity_milli']>0 and 0<=x['paid_cents']<=x['settlement_cents']<=x['credit_cents'] and x['credit_cents']>0 and x['settlement_cents']==(x['credit_cents'] if c['discount_bearer']=='group' else x['paid_cents']),'规则金额/责任不守恒')
        ds=[d for d in tables['repair_package_rule_decisions'] if d['rule_id']==r['id']]
        check(all(d['store_id']==r['issuer_store_id'] and (d['action'] not in {'approve','reject'} or d['actor_id']!=r['actor_id']) for d in ds),'原规则独立批准缺失')
    for m in tables['repair_package_mappings']:
        rule=rules.get(m['rule_id']);check(rule is not None,'组件本店映射缺规则');c=value(rule['contract']);component=next((x for x in c['components'] if x['key']==m['component_key']),None)
        source=by('master_work_items' if m['kind']=='work' else 'flow_items').get(m['source_id']);snapshot=value(m['snapshot'])
        check(component and m['store_id'] in c['allowed_store_ids'] and m['kind']==component['kind'] and source and source['store_id']==m['store_id'] and snapshot['unit']==component['unit'] and snapshot['specification']==component['specification'],'本店组件映射来源不一致')
    for p in purchases.values():
        rule=rules.get(p['rule_id']);row=cases.get(p['case_id']);c=value(p['contract']);check(rule and row and row['store_id']==p['issuer_store_id'] and p['digest']==canonical(c),'原购买摘要或来源异常')
        identity(p,row);rc=value(rule['contract']);check(all(c[k]==v for k,v in rc.items()) and c['rule_digest']==rule['digest'] and c['sets']==p['sets'] and c['member_id']==p['member_id'] and c['source_customer_id']==row['customer_id'] and p['amount_cents']==p['sets']*sum(x['paid_cents'] for x in c['components']),'原购买分摊不一致')
        events=[e for e in tables['repair_package_purchase_events'] if e['purchase_id']==p['id']];actions=[e['action'] for e in events]
        check(len(actions)==len(set(actions)) and 'propose' in actions and all(e['store_id']==row['store_id'] and e['digest']==p['digest'] for e in events),'购买事件来源不完整')
        check((p['status']=='issued')==('issue' in actions) and (p['status']=='cancelled')==('cancel' in actions) and (p['status'] not in {'authorized','issued'} or 'authorize' in actions),'购买状态与实际事件不符')
        if 'authorize' in actions:proof(next(e['evidence_id'] for e in events if e['action']=='authorize'),row['id'],'authorization')
        ps=[l for l in lots.values() if l['purchase_id']==p['id']]
        if p['status']=='issued':
            approved=[d for d in tables['repair_package_rule_decisions'] if d['rule_id']==rule['id'] and d['action']=='approve'];check(approved,'发行缺独立批准')
            original=cash.get(p['cash_id']);account=accounts.get(p['account_id']);check(original and account and original['store_id']==account['store_id']==row['store_id'] and original['direction']=='in' and original['category']=='repair_package_purchase' and original['amount_cents']==p['amount_cents'] and original['account']==account['name'],'购买实际现金或原账户不一致')
            proof(next(e['evidence_id'] for e in events if e['action']=='issue'),row['id']);check(len(ps)==len(c['components']),'实收组件发行不全')
            check(not any(x['cash_id']==p['cash_id'] for x in rows('flow_payment_links')),'购买现金重复记为原维修现金')
            for l in ps:
                component=next((x for x in c['components'] if x['key']==l['component_key']),None);check(component and value(l['snapshot'])==component and all(l[k]==component[k]*p['sets'] for k in ('quantity_milli','credit_cents','paid_cents','settlement_cents')),'发行组件与原购买不符')
        else:check(not ps and p['cash_id'] is None and p['account_id'] is None,'未实收合同产生权益或现金')
    reservation_links=tables['repair_package_reservation_links']
    for snap in tables['repair_package_quote_snapshots']:
        quote=quotes.get(snap['quote_id']);check(quote and snap['case_id']==quote['case_id'] and snap['store_id']==quote['store_id'],'报价合同归属异常');contract=quote_contract(connection,snap['case_id'],snap['quote_id']);qs=sorted([l for l in lines.values() if l['quote_id']==quote['id']],key=lambda l:l['id'])
        for p in contract['lines']:
            lot=lots.get(p['lot_id']);check(lot and 0<=p['index']<len(qs),'报价合同组件缺失');money(lot,p);line=qs[p['index']];check(p['line_key']==line['line_key'] and p['credit_cents']==line['amount_cents'],'报价合同与实际行不符')
            check(any(h['quote_id']==quote['id'] and h['line_id']==line['id'] and h['lot_id']==lot['id'] and value(h['spans'])==p['spans'] for h in holds.values()),'报价合同缺原区间占额')
        spec_fields=('line_key','kind','work_item_id','item_id','code','name','unit','standard_fee_cents','quantity_milli','unit_price_cents','amount_cents','discount_cents')
        payload={'purpose':quote['purpose'],'reason':quote['reason'],'lines':[{k:l[k] for k in spec_fields} for l in qs],'repair_package':snap['digest']}
        if 'rework_quote_scopes' in names and connection.execute('SELECT 1 FROM rework_quote_scopes WHERE quote_id=?',(quote['id'],)).fetchone():
            parts=by('rework_line_scopes','line_id');payload['rework_scopes']=[{'charge_scope':parts[l['id']]['charge_scope'],'source_line_id':parts[l['id']]['source_line_id']} for l in qs]
        if 'member_pricing_snapshots' in names:
            member=connection.execute("SELECT digest FROM member_pricing_snapshots WHERE quote_kind='repair' AND quote_id=?",(quote['id'],)).fetchone()
            if member:payload['member_pricing']=member[0]
        check(quote['digest']==hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'实际报价摘要未绑定原套餐组件契约')
    for h in holds.values():
        lot=lots.get(h['lot_id']);line=lines.get(h['line_id']);quote=quotes.get(h['quote_id']);row=cases.get(h['case_id']);check(lot and line and quote and row,'组件报价缺原对象');p=purchases[lot['purchase_id']];identity(p,row);s=money(lot,h)
        check(row['store_id']==h['store_id']==line['store_id']==quote['store_id'] and quote['case_id']==row['id'] and line['quote_id']==quote['id'] and line['line_key']==h['line_key'] and (line['quantity_milli']==h['quantity_milli'] or (quote['purpose']=='stop' and line['quantity_milli']>=h['quantity_milli'])) and line['amount_cents']==h['credit_cents'],'本店当前报价数量/金额/来源不符')
        check(h['digest']==canonical({'quote_digest':quote['digest'],'lot_id':lot['id'],'spans':s,**amounts(lot,s)}),'报价组件摘要异常')
        mappings=[m for m in tables['repair_package_mappings'] if m['rule_id']==p['rule_id'] and m['component_key']==lot['component_key'] and m['store_id']==row['store_id']]
        check(len(mappings)==1 and mappings[0]['kind']==line['kind'] and mappings[0]['source_id']==line['work_item_id' if line['kind']=='work' else 'item_id'],'报价不是获准的本店真实组件')
        rs=[r for r in reservation_links if r['hold_id']==h['id']];check(len(rs)==1 and all(rs[0][k]==h[k] for k in ('store_id','case_id','quote_id','status')) and rs[0]['amount_cents']==h['credit_cents'] and rs[0]['recognized_cents']==h['paid_cents'],'本店占额链接不一致')
        if h['status']=='reserved':check(quote['id'] not in quote_cancelled and row['state']!='cancelled' and not value(row['data']).get('released_date'),'已撤销报价或已交车仍有组件占额')
        if 'rework_line_scopes' in names:check(not any(x['line_id']==line['id'] and x['charge_scope']=='original_liability' for x in rows('rework_line_scopes')),'原责任项目核销了客户套餐')
    for e in entries.values():
        lot=lots.get(e['lot_id']);row=cases.get(e['case_id']);check(lot and row and row['store_id']==e['store_id'],'组件账归属不一致');money(lot,e);p=purchases[lot['purchase_id']];identity(p,row)
        if e['purpose']=='capture':
            h=holds.get(e['hold_id']);check(h and h['status']=='captured' and h['lot_id']==lot['id'] and h['case_id']==row['id'] and value(e['spans'])==value(h['spans']),'实际核销缺原占额');check(row['id'] in settled and settled[row['id']]['quote_id']==h['quote_id'] and any(a['quote_id']==h['quote_id'] for a in authorizations),'实际核销缺原客户授权或质检结算');proof(e['evidence_id'],row['id'])
            if value(lot['snapshot'])['kind']=='part':check(sum(s['quantity_milli'] for s in stocks.values() if s['case_id']==row['id'] and s['line_key']==h['line_key'] and not s['original_id'])>=e['quantity_milli'],'核销配件没有真实原领料')
        elif e['purpose']=='reverse':
            original=entries.get(e['original_id']);check(original and original['purpose']=='capture' and original['lot_id']==lot['id'] and original['case_id']==row['id'] and e['hold_id']==original['hold_id'] and not subtract(value(e['spans']),value(original['spans'])),'组件原退不是原核销区间')
            hs=[h for h in after.values() if h['original_id']==original['id'] and h['status']=='applied' and value(h['spans'])==value(e['spans'])];check(len(hs)==1,'组件冲正缺原售后批准');proof(e['evidence_id'],hs[0]['aftercare_case_id'])
        else:
            refund=refunds.get(e['refund_id']);check(refund and refund['status']=='executed' and refund['purchase_id']==p['id'] and e['case_id']==p['case_id'],'未用退款缺原购买');proof(e['evidence_id'],row['id'])
        local=[l for l in tables['repair_package_payment_links'] if l['entry_id']==e['id']]
        paired=[s for s in tables['repair_package_settlements'] if s['entry_id']==e['id']]
        if e['purpose']=='refund':check(not local and not paired,'未用原退款被重复记为履约抵款')
        else:
            sign=1 if e['purpose']=='capture' else -1
            check(len(local)==1 and local[0]['purpose']==e['purpose'] and local[0]['store_id']==e['store_id'] and local[0]['case_id']==e['case_id'] and local[0]['amount_cents']==sign*e['credit_cents'] and local[0]['recognized_cents']==sign*e['paid_cents'],'本店C/P抵款不一致')
            check(({s['side']:s['amount_cents'] for s in paired}==({'center':-sign*e['settlement_cents'],'store':sign*e['settlement_cents']} if e['settlement_cents'] else {})) and all(s['store_id']==e['store_id'] for s in paired),'内部S配对不守恒')
    for r in refunds.values():
        p=purchases.get(r['purchase_id']);check(p and r['case_id']==p['case_id'] and r['store_id']==p['issuer_store_id'],'原退款归属错误');chosen=value(r['selections']);check(len({s['lot_id'] for s in chosen})==len(chosen),'原退款重复组件')
        for s in chosen:check(lots[s['lot_id']]['purchase_id']==p['id'],'退款串用购买');money(lots[s['lot_id']],s)
        check(sum(s['paid_cents'] for s in chosen)==r['amount_cents'],'退款不等于原P分摊')
        if r['status'] in {'approved','executed'}:check(r['approved_by'] and r['approved_by']!=r['requested_by'],'退款缺独立批准')
        claims=[x for x in tables['repair_package_refund_claims'] if x['refund_id']==r['id']]
        if r['status'] in {'approved','executed'}:check(len(claims)==len(chosen),'原退款缺跨店中央占额')
        for claim in claims:check(claim['store_id']==r['store_id'] and any(s['lot_id']==claim['lot_id'] and s['spans']==value(claim['spans']) for s in chosen) and claim['status']==('reserved' if r['status']=='approved' else 'applied' if r['status']=='executed' else 'released'),'原退款占额状态不符')
        if r['status']=='executed':
            es=[e for e in entries.values() if e['refund_id']==r['id']];check(len(es)==len(chosen) and sorted((e['lot_id'],value(e['spans'])) for e in es)==sorted((s['lot_id'],s['spans']) for s in chosen),'实际退款未注销原组件')
            if r['amount_cents']:
                actual=cash.get(r['cash_id']);check(actual and actual['direction']=='out' and actual['category']=='repair_package_refund' and actual['store_id']==r['store_id'] and actual['account']==accounts[p['account_id']]['name'] and actual['amount_cents']==r['amount_cents'],'原退款现金/账户错误')
            else:check(r['cash_id'] is None,'零分权益注销伪造实际现金')
    for lot in lots.values():
        blocked=[]
        for e in entries.values():
            if e['lot_id']!=lot['id'] or e['purpose'] not in {'capture','refund'}:continue
            used=[]
            for reverse in entries.values():
                if reverse['original_id']==e['id']:
                    check(not any(max(a,c)<min(b,d) for a,b in used for c,d in value(reverse['spans'])),'原核销重复退回');used+=value(reverse['spans'])
            blocked+=subtract(value(e['spans']),used)
        blocked += [p for h in holds.values() if h['lot_id']==lot['id'] and h['status']=='reserved' for p in value(h['spans'])]
        blocked += [p for h in tables['repair_package_refund_claims'] if h['lot_id']==lot['id'] and h['status']=='reserved' for p in value(h['spans'])]
        ordered=sorted(blocked);check(all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:])),'组件被重复核销、退款或占用')
    for h in after.values():
        original=entries.get(h['original_id']);check(original and original['purpose']=='capture' and original['case_id']==h['source_case_id'] and original['store_id']==h['store_id'],'售后原组件来源不符');lot=lots[original['lot_id']];money(lot,h)
        check(any(t['plan_id']==h['plan_id'] and t['kind']=='repair_package' and t['original_id']==original['id'] and t['units']==h['quantity_milli'] and t['credit_cents']==h['credit_cents'] for t in rows('aftercare_tenders')),'组件原退不符批准方案')
        actual=[x for x in tables['repair_package_stock_returns'] if x['hold_id']==h['id']]
        if h['status']=='applied':check(sum(x['quantity_milli'] for x in actual)==h['quantity_milli'],'组件原退缺实际原物料入库')
        if actual:check(h['status']!='released','已经实际退货的方案被抹除')
        for x in actual:
            old=stocks.get(x['original_stock_id']);new=stocks.get(x['stock_fact_id']);claim=holds[original['hold_id']]
            check(old and new and old['case_id']==h['source_case_id'] and old['line_key']==claim['line_key'] and not old['original_id'] and new['original_id']==old['id'] and new['quantity_milli']==-x['quantity_milli'] and new['value_cents']==-x['value_cents'],'实物退回未引用原领料成本')
            move=moves.get(new['stock_move_id']);check(move and move['original_id']==old['stock_move_id'] and move['quantity_milli']==x['quantity_milli'] and move['value_cents']==x['value_cents'],'实物退回与实际库存账不符');proof(x['evidence_id'],h['aftercare_case_id'])
    return {'verified_repair_package_purchases':len(purchases),'verified_repair_package_lots':len(lots),'verified_repair_package_entries':len(entries),'verified_repair_package_refunds':len(refunds)}
