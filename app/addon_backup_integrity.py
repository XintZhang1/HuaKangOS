"""Offline reconstruction of accessory authority, physical cost and original cash."""
import json
from datetime import datetime,timezone
from collections import defaultdict
def _data(value):return json.loads(value) if isinstance(value,str) else value
def _dt(value):
    result=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return result.astimezone(timezone.utc).replace(tzinfo=None) if result.tzinfo else result
def _load(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'addon_orders' not in names:return {}
    def rows(name):
        if name not in names:return []
        columns='id,store_id,case_id,category,generated,sha256,created_at' if name=='flow_files' else '*'
        c=connection.execute('SELECT '+columns+' FROM '+name);keys=[x[0] for x in c.description];return [dict(zip(keys,r)) for r in c]
    tables={n:rows(n) for n in names if n.startswith('addon_') or n in {'flow_cases','flow_files','flow_events','flow_items','flow_stock_moves','flow_payment_links','cash_entries','flow_accounts','vehicles','vehicle_operations','vehicle_operation_entries','business_finance_credit_links','business_finance_advance_entries','business_finance_advances','business_finance_cash_batches','business_finance_cash_allocations','master_work_items'}}
    return tables
def _fail(s):raise ValueError('销售加装恢复检查：'+s)
def validate(connection):
    t=_load(connection)
    if not t.get('addon_orders'):return {'verified_addon_orders':0}
    by=lambda n:{r['id']:r for r in t.get(n,[])}
    cases=by('flow_cases');orders=by('addon_orders');quotes=by('addon_quotes');lines=by('addon_lines');targets=by('addon_targets');files=by('flow_files');moves=by('flow_stock_moves');dispatches=by('addon_dispatches');installs=by('addon_installations');checks=by('addon_inspections');plans=by('addon_resolutions');cash=by('cash_entries');payments=by('flow_payment_links');credits=by('business_finance_credit_links');accepts=by('addon_acceptances')
    same=lambda a,b:a and b and a['store_id']==b['store_id']
    def proof(r,case,category):
        f=files.get(r['evidence_id'])
        if not same(r,case) or not same(r,f) or f['case_id']!=case['id'] or f['generated'] or f['category']!=category:_fail('事实原件不属于本单、本店或正确类别')
    for table,records in t.items():
        if not table.startswith('addon_'):continue
        for fk in connection.execute('PRAGMA foreign_key_list('+table+')'):
            target,column=fk[2],fk[3]
            refs=by(target) if target in t else {}
            if not refs:continue
            for r in records:
                if r[column] is not None and not same(r,refs.get(r[column])):_fail('原始关联跨店或缺失：'+table+'.'+column)
    for o in orders.values():
        c=cases.get(o['id']);s=cases.get(o['source_order_id'])
        if not same(o,c) or not same(c,s) or (c['kind'],c['flow_version'])!=('addon',3) or s['kind']!='order' or c['parent_id']!=s['id'] or c['customer_id']!=o['customer_id'] or c['customer_id']!=s['customer_id']:_fail('原销售或客户版本绑定不一致')
        current=quotes.get(_data(c['data']).get('addon_quote_id'))
        if current and (current['case_id']!=c['id'] or c['amount_cents']!=current['goods_cents']+current['installation_cents']):_fail('当前报价金额与原版本不一致')
    auth={a['quote_id']:a for a in t['addon_authorizations']};approvals={a['quote_id']:a for a in t['addon_approvals']}
    for q in quotes.values():
        ls=[l for l in lines.values() if l['quote_id']==q['id']];keys=['line_key','item_id','work_item_id','sku','name','unit','work_code','work_name','quantity_milli','goods_unit_cents','installation_unit_cents','goods_cents','installation_cents']
        payload=[{k:l[k] for k in keys} for l in sorted(ls,key=lambda l:l['id'])]
        # request_digest intentionally uses the workflow canonical representation.
        from .flow_engine import request_digest
        version=q.get('pricing_version',1);terms=_data(q.get('gift_terms','{}'))
        if version not in {1,2} or not isinstance(terms,dict):_fail('未知核价版本或赠送原条款无效')
        if version==1 and (terms or q['goods_cents']+q['installation_cents']<=0):_fail('历史报价不得补记赠送或改为零价')
        if version==2:
            if set(terms)-{l['line_key'] for l in ls}:_fail('赠送条款没有原报价项目')
            prior=[p for p in quotes.values() if p['case_id']==q['case_id'] and p['revision']<q['revision'] and p['id'] in auth]
            for l in ls:
                term=terms.get(l['line_key']);originals=[x for x in lines.values() if any(p['id']==x['quote_id'] for p in prior) and x['line_key']==l['line_key']]
                original=min(originals,key=lambda x:x['id']) if originals else None
                if original:
                    original_terms=_data(quotes[original['quote_id']].get('gift_terms','{}')).get(l['line_key'])
                    if any(original[k]!=l[k] for k in keys) or term!=original_terms:_fail('已授权原行的赠送条款、商品数量或价格被改写')
                if term is not None:
                    if set(term)!={'reason','cost_bearer','burden_store_id'} or not isinstance(term['reason'],str) or not 2<=len(term['reason'])<=1000 or term['cost_bearer']!='selling_store' or term['burden_store_id']!=q['store_id'] or l['goods_cents']+l['installation_cents']!=0:_fail('零价赠送原因、承担门店或冻结价格无效')
                elif l['goods_cents']+l['installation_cents']==0 and not (original and quotes[original['quote_id']].get('pricing_version',1)==1):_fail('新零价原行缺少明确赠送和本店成本承担')
            payload=dict(pricing_version=2,lines=payload,gift_terms=terms)
        from .member_pricing_integrity import quote_digest
        member_price=quote_digest(connection,q['case_id'],'addon',q['id'])
        if member_price:
            if version!=2:_fail('历史报价不能补认会员价格')
            payload['member_pricing']=member_price
        if q['digest']!=request_digest('addon_quote',payload) or sum(l['goods_cents'] for l in ls)!=q['goods_cents'] or sum(l['installation_cents'] for l in ls)!=q['installation_cents']:_fail('报价原明细或摘要被修改')
        if len({l['line_key'] for l in ls})!=len(ls):_fail('原报价项目重复')
        if sum((l['quantity_milli']*l['goods_unit_cents']+500)//1000+(l['quantity_milli']*l['installation_unit_cents']+500)//1000-l['goods_cents']-l['installation_cents'] for l in ls)!=q['discount_cents']:_fail('报价折扣分摊不守恒')
    for a in t['addon_approvals']:
        q=quotes[a['quote_id']];c=cases[q['case_id']];proof(a,c,'authorization')
        if a['actor_id'] in {q['actor_id'],c['created_by']} or not a['allow_below_minimum'] and q['goods_cents']+q['installation_cents']<a['minimum_cents']:_fail('缺少独立价格批准或明确低价授权')
        if bool(_data(q.get('gift_terms','{}')))!=bool(a.get('gift_confirmed',False)):_fail('赠送缺少本版独立经理承担授权或虚记历史赠送')
    for a in auth.values():
        q=quotes[a['quote_id']];proof(a,cases[q['case_id']],'authorization')
        if q['id'] not in approvals or a['created_at']<approvals[q['id']]['created_at']:_fail('客户授权先于主管批准')
    for x in targets.values():
        o=orders[x['case_id']];v=by('vehicles').get(x['vehicle_id'])
        if not v or v['vin']!=x['vin'] or not same(v,x):_fail('实际安装VIN或车辆绑定不一致')
    for d in dispatches.values():
        l=lines[d['line_id']];m=moves.get(d['stock_move_id']);target=targets.get(d['target_id']);q=quotes[l['quote_id']]
        proof(d,cases[d['case_id']],'evidence')
        if q['case_id']!=d['case_id'] or q['id'] not in auth or target['case_id']!=d['case_id'] or l['line_key']!=d['line_key'] or not m or (m['case_id'],m['item_id'],m['quantity_milli'],m['value_cents'],m['purpose'])!=(d['case_id'],l['item_id'],-d['quantity_milli'],-d['value_cents'],'addon_dispatch_v3'):_fail('原领料与授权、库存数量价值不一致')
    for i in installs.values():
        d=dispatches[i['dispatch_id']];proof(i,cases[d['case_id']],'inspection')
    for d in dispatches.values():
        if sum(i['quantity_milli'] for i in installs.values() if i['dispatch_id']==d['id'])>d['quantity_milli']:_fail('安装超过真实原领料')
    for c in checks.values():proof(c,cases[dispatches[installs[c['installation_id']]['dispatch_id']]['case_id']],'inspection')
    for r in t['addon_rectifications']:
        c=checks[r['inspection_id']];proof(r,cases[dispatches[installs[c['installation_id']]['dispatch_id']]['case_id']],'inspection')
        if c['passed']:_fail('合格检查却存在整改')
    for p in plans.values():
        payload={'kind':p['kind'],'lines':_data(p['lines']),'no_goods_refund':p['kind']=='vehicle_gift'}
        from .flow_engine import request_digest
        if request_digest('addon_resolution',payload)!=p['digest']:_fail('原单处置冻结明细被修改')
        proof(p,cases[p['case_id']],'authorization');facts=[f for f in t['addon_resolution_facts'] if f['resolution_id']==p['id']]
        approval=next((f for f in facts if f['action']=='resolution_approve'),None);consent=next((f for f in facts if f['action']=='resolution_consent'),None)
        if approval and approval['actor_id'] in {p['requested_by'],cases[p['case_id']]['created_by']}:_fail('原单处置缺少独立复核')
        if p['status'] not in {'requested','cancelled'} and not approval:_fail('处置未批准')
        if p['status'] in {'consented','rectification','reinspection','handback','rejected','completed'} and not consent:_fail('原处置没有客户当前版同意')
        for f in facts:proof(f,cases[p['case_id']],'authorization' if f['action'].startswith('resolution_') else 'inspection')
    return_qty=defaultdict(int);return_value=defaultdict(int);returned_install=defaultdict(int)
    posting_keys=set()
    for p in t['addon_return_postings']:
        plan=plans[p['resolution_id']];c=cases[p['case_id']];line=lines[p['line_id']]
        if plan['status']!='completed' or plan['kind']=='vehicle_gift' or plan['case_id']!=c['id']:_fail('退回或取消过账没有完成原处置')
        original=next((x for x in _data(plan['lines']) if x['line_id']==p['line_id'] and x['dispatch_id']==p['dispatch_id'] and x['installation_id']==p['installation_id']),None)
        posting_key=(p['resolution_id'],p['line_id'],p['dispatch_id'],p['installation_id'])
        if posting_key in posting_keys:_fail('同一原处置明细被重复过账')
        posting_keys.add(posting_key)
        if not original or any(p[k]!=original[k] for k in ('quantity_milli','value_cents','goods_cents','installation_cents','retained_cents')):_fail('实际退回偏离原获准分摊')
        proof(p,c,'inspection' if plan['kind']=='return' else 'authorization')
        if p['dispatch_id']:
            d=dispatches[p['dispatch_id']];m=moves.get(p['stock_move_id'])
            if not m or (m['case_id'],m['item_id'],m['quantity_milli'],m['value_cents'],m['original_id'],m['purpose'])!=(c['id'],line['item_id'],p['quantity_milli'],p['value_cents'],d['stock_move_id'],'addon_return_v3'):_fail('可售退回没有原出库反向数量成本')
            return_qty[d['id']]+=p['quantity_milli'];return_value[d['id']]+=p['value_cents']
            if p['installation_id']:
                if installs[p['installation_id']]['dispatch_id']!=d['id'] or p['retained_cents']!=p['installation_cents']:_fail('安装保留费用未关联原实际安装')
                returned_install[p['installation_id']]+=p['quantity_milli']
            elif p['retained_cents']:_fail('未安装项目伪造保留安装费')
        elif p['stock_move_id'] or p['value_cents'] or p['retained_cents']:_fail('未领取消不能生成实物库存或保留安装费用')
        if p['acceptance_id'] and (accepts[p['acceptance_id']]['case_id']!=c['id'] or accepts[p['acceptance_id']]['business_date']>p['business_date']):_fail('收入调整未引用原履约')
    for d in dispatches.values():
        if return_qty[d['id']]>d['quantity_milli'] or return_value[d['id']]>d['value_cents']:_fail('原退数量或成本超过原领出')
    for key,quantity in returned_install.items():
        if quantity>installs[key]['quantity_milli']:_fail('原安装被重复拆回')
    for h in t['addon_vehicle_handovers']:
        p=plans[h['resolution_id']];v=by('vehicles').get(h['new_vehicle_id']);op=by('vehicle_operations').get(h['vehicle_operation_id']);f=files.get(h['evidence_id']);target=next((x for x in targets.values() if x['case_id']==h['case_id']),None)
        if p['kind']!='vehicle_gift' or p['status']!='completed' or h['incremental_value_cents']!=0 or not same(h,v) or not target or v['vin']!=h['vin'] or target['vin']!=h['vin'] or v['id']==target['vehicle_id'] or not op or op['received_vehicle_id']!=v['id'] or op['aftercare_case_id']!=h['aftercare_case_id'] or op['source_order_id']!=orders[h['case_id']]['source_order_id'] or not same(h,f) or f['case_id']!=op['id'] or f['generated']:_fail('随车无偿移交没有原VIN、新代次和实际验收原件')
        manifest=[dict(item_id=lines[x['line_id']]['item_id'],name=lines[x['line_id']]['name'],quantity_milli=x['quantity_milli'],dispatch_id=x['dispatch_id'],installation_id=x['installation_id']) for x in _data(p['lines'])]
        if _data(h['attachments'])!=manifest:_fail('实际随车附属物清单偏离客户同意的原商品')
        for x in _data(p['lines']):
            return_qty[x['dispatch_id']]+=x['quantity_milli']
            if return_qty[x['dispatch_id']]>dispatches[x['dispatch_id']]['quantity_milli']:_fail('随车移交与拆回重复使用原装件')
    for o in orders.values():
        c=cases[o['id']];qs=[q for q in quotes.values() if q['case_id']==c['id']];current=quotes.get(_data(c['data']).get('addon_quote_id'));holds=defaultdict(int)
        for r in t['addon_reservations']:
            if r['case_id']!=c['id']:continue
            l=lines[r['line_id']]
            if quotes[l['quote_id']]['case_id']!=c['id'] or l['item_id']!=r['item_id'] or l['line_key']!=r['line_key'] or (r['purpose']=='reserve')!=(r['quantity_milli']>0):_fail('库存占用原行或方向错误')
            holds[r['line_key']]+=r['quantity_milli']
            if holds[r['line_key']]<0:_fail('库存占用重复释放')
        if current:
            for l in [l for l in lines.values() if l['quote_id']==current['id']]:
                reserved=sum(r['quantity_milli'] for r in t['addon_reservations'] if r['case_id']==c['id'] and r['line_key']==l['line_key'] and r['purpose']=='reserve')
                dispatched=sum(d['quantity_milli'] for d in dispatches.values() if d['case_id']==c['id'] and d['line_key']==l['line_key']);cancelled=sum(p['quantity_milli'] for p in t['addon_return_postings'] if p['case_id']==c['id'] and p['line_key']==l['line_key'] and not p['dispatch_id'])
                if reserved not in {0,l['quantity_milli']} or holds[l['line_key']]!=reserved-dispatched-cancelled:_fail('原数量、占用、出库和取消不守恒')
            if current.get('pricing_version',1)==2 and c['state']=='completed' and any(d['case_id']==c['id'] and d['quantity_milli']>return_qty[d['id']] for d in dispatches.values()) and not any(a['quote_id']==current['id'] for a in accepts.values()):_fail('零价赠送未有本版客户实际接收即完成')
    def post_at(p):
        matches=[e for e in t['flow_events'] if e['case_id']==p['case_id'] and e['action'] in {'addon_return_receive','addon_resolution_consent'} and _data(e['detail']).get('evidence_id')==p['evidence_id']]
        if len(matches)!=1:_fail('实际处置过账缺少唯一经办事件')
        return _dt(matches[0]['occurred_at'])
    for a in accepts.values():
        c=cases[a['case_id']];q=quotes[a['quote_id']];proof(a,c,'authorization');at=_dt(a['created_at'])
        if q['case_id']!=c['id'] or q['id'] not in auth or _dt(auth[q['id']]['created_at'])>at:_fail('客户接收没有对应版已批准授权')
        ds=[d for d in dispatches.values() if d['case_id']==c['id'] and _dt(d['created_at'])<=at];ps=[p for p in t['addon_return_postings'] if p['case_id']==c['id'] and post_at(p)<=at];prior=[x for x in accepts.values() if x['case_id']==c['id'] and x['id']<a['id']]
        previous_ids={x['id'] for x in prior};relief=lambda p:p['goods_cents']+p['installation_cents']-p['retained_cents']
        expected=q['goods_cents']+q['installation_cents']-sum(relief(p) for p in ps)-sum(x['amount_cents'] for x in prior)+sum(relief(p) for p in ps if p['acceptance_id'] in previous_ids)
        expected_value=sum(d['value_cents'] for d in ds)-sum(p['value_cents'] for p in ps)-sum(x['value_cents'] for x in prior)+sum(p['value_cents'] for p in ps if p['acceptance_id'] in previous_ids)
        if (a['amount_cents'],a['value_cents'])!=(expected,expected_value):_fail('客户接收增量重复计算原收入或原成本')
        if q.get('pricing_version',1)==2:
            for l in [l for l in lines.values() if l['quote_id']==q['id']]:
                issued=sum(d['quantity_milli'] for d in ds if d['line_key']==l['line_key'])
                cancelled=sum(p['quantity_milli'] for p in ps if p['line_key']==l['line_key'] and not p['dispatch_id'])
                if issued+cancelled!=l['quantity_milli']:_fail('客户接收时仍有未领且未取消的获准项目')
            for d in ds:
                installed=sum(i['quantity_milli'] for i in installs.values() if i['dispatch_id']==d['id'] and _dt(i['created_at'])<=at)
                uninstalled_returns=sum(p['quantity_milli'] for p in ps if p['dispatch_id']==d['id'] and not p['installation_id'])
                if installed+uninstalled_returns!=d['quantity_milli']:_fail('客户接收时仍有实际领料未安装或原退')
        for i in [i for i in installs.values() if any(d['id']==i['dispatch_id'] for d in ds) and _dt(i['created_at'])<=at]:
            remaining=i['quantity_milli']-sum(p['quantity_milli'] for p in ps if p['installation_id']==i['id'])
            last=sorted((x for x in checks.values() if x['installation_id']==i['id'] and _dt(x['created_at'])<=at),key=lambda x:x['id'])
            if remaining>0 and (not last or not last[-1]['passed']):_fail('客户接收时仍有未检查通过的安装批次')
    domain_links=set();domain_credit=set()
    for p in t['addon_payments']:
        c=cases[p['case_id']];f=files.get(p['evidence_id'])
        if not same(p,f) or f['category']!='receipt' or f['generated']:_fail('财务原件无本店收款凭据')
        if p['payment_link_id']:
            l=payments[p['payment_link_id']];domain_links.add(l['id']);ca=cash.get(l['cash_id'])
            if l['case_id']!=c['id'] or not same(l,ca) or ca['direction']!=l['direction']:_fail('原现金与业务链接不一致')
            if p['resolution_id'] and (l['direction']!='out' or not l['original_id'] or payments[l['original_id']]['case_id']!=c['id'] or l['account_id']!=payments[l['original_id']]['account_id']):_fail('客户现金退款未遵循本单原收款账户')
            if l['direction']=='out' and not p['resolution_id'] and not any(b['cash_id']==l['cash_id'] and b['kind']=='correction_reverse' for b in t['business_finance_cash_batches']):_fail('原退款既无获准实物处置也非明确误记冲回')
        else:
            l=credits[p['credit_link_id']];domain_credit.add(l['id'])
            if l['case_id']!=c['id'] or p['resolution_id'] and (l['amount_cents']>=0 or not l['original_id'] or credits[l['original_id']]['case_id']!=c['id']):_fail('预收原退未恢复本单原抵用')
        if f['case_id']!=c['id']:
            batch=any(b['case_id']==f['case_id'] and b['evidence_id']==f['id'] and any(a['batch_id']==b['id'] and a['case_id']==c['id'] for a in t['business_finance_cash_allocations']) for b in t['business_finance_cash_batches'])
            advance=any(e['case_id']==f['case_id'] and e['evidence_id']==f['id'] and any(x['entry_id']==e['id'] and x['case_id']==c['id'] for x in credits.values()) for e in t['business_finance_advance_entries'])
            if not (batch or advance):_fail('借用其它业务资金凭据')
    if domain_links!={p['id'] for p in payments.values() if p['case_id'] in orders} or domain_credit!={p['id'] for p in credits.values() if p['case_id'] in orders}:_fail('本域实际资金没有唯一明细链接')
    for p in plans.values():
        relief=sum(x['goods_cents']+x['installation_cents']-x['retained_cents'] for x in t['addon_return_postings'] if x['resolution_id']==p['id']);actual=0
        for x in t['addon_payments']:
            if x['resolution_id']!=p['id']:continue
            actual+=payments[x['payment_link_id']]['amount_cents'] if x['payment_link_id'] else -credits[x['credit_link_id']]['amount_cents']
        if actual>relief:_fail('实际原款退款超过处置减免')
    return {'verified_addon_orders':len(orders),'verified_addon_dispatches':len(dispatches)}

def validate_parent_aftercare_exclusions(connection,parent_id,excluded_ids,requested_at=None,applied_at=None):
    """Use original request time; later valid events must not rewrite old evidence."""
    t=_load(connection);cases={r['id']:r for r in t.get('flow_cases',[])}
    def before(at,limit):return limit is None or _dt(at)<=_dt(limit)
    orders=[o for o in t.get('addon_orders',[]) if o['source_order_id']==parent_id and before(cases[o['id']]['created_at'],requested_at)]
    if sorted(excluded_ids)!=sorted(o['id'] for o in orders) or len(excluded_ids)!=len(set(excluded_ids)):_fail('父售后独立排除清单与申请时加装来源不一致')
    if not orders:return True
    files={r['id']:r for r in t['flow_files']};cash={r['id']:r for r in t['cash_entries']};advance={r['id']:r for r in t['business_finance_advance_entries']}
    def events(case_id,limit):return [e for e in t['flow_events'] if e['case_id']==case_id and before(e['occurred_at'],limit)]
    def posting_before(p,es):return any(e['action'] in {'addon_return_receive','addon_resolution_consent'} and _data(e['detail']).get('evidence_id')==p['evidence_id'] for e in es)
    for o in orders:
        case=cases[o['id']];es=events(o['id'],requested_at)
        if any(e['action']=='addon_cancel' for e in es):
            if any(e['action'] in {'addon_authorize','addon_dispatch','addon_receive'} for e in es) or any(p['case_id']==o['id'] and before(cash[p['cash_id']]['created_at'],requested_at) for p in t['flow_payment_links']) or any(c['case_id']==o['id'] and before(advance[c['entry_id']]['occurred_at'],requested_at) for c in t['business_finance_credit_links']):_fail('普通取消证明与当时授权、实物或真实资金矛盾')
            continue
        qs=[q for q in t['addon_quotes'] if q['case_id']==o['id'] and before(q['created_at'],requested_at)]
        if not qs:_fail('未报价加装没有独立取消证明')
        q=max(qs,key=lambda q:q['id']);ls=[l for l in t['addon_lines'] if l['quote_id']==q['id']]
        if not any(a['quote_id']==q['id'] and before(a['created_at'],requested_at) for a in t['addon_authorizations']):_fail('申请时原加装未获得客户授权')
        ds=[d for d in t['addon_dispatches'] if d['case_id']==o['id'] and any(e['action']=='addon_dispatch' and _data(e['detail']).get('evidence_id')==d['evidence_id'] for e in es)]
        ps=[p for p in t['addon_return_postings'] if p['case_id']==o['id'] and posting_before(p,es)]
        for l in ls:
            if sum(d['quantity_milli'] for d in ds if d['line_key']==l['line_key'])+sum(p['quantity_milli'] for p in ps if p['line_key']==l['line_key'] and not p['dispatch_id'])!=l['quantity_milli']:_fail('申请时加装尚有未明确取消的占用数量')
        gift=defaultdict(int)
        for p in [p for p in t['addon_resolutions'] if p['case_id']==o['id']]:
            facts=[f for f in t['addon_resolution_facts'] if f['resolution_id']==p['id'] and before(f['created_at'],requested_at)]
            last=facts[-1]['action'] if facts else ''
            if not facts:continue
            if p['kind']=='vehicle_gift' and last=='resolution_consent':
                for x in _data(p['lines']):gift[x['dispatch_id']]+=x['quantity_milli']
                if applied_at and not any(h['resolution_id']==p['id'] and before(h['created_at'],applied_at) for h in t['addon_vehicle_handovers']):_fail('父售后生效时无偿移交装件尚未随原VIN实收')
            elif last not in {'resolution_cancel','return_receive','return_handback','resolution_consent'}:_fail('申请时原加装处置仍未结束')
        for d in ds:
            if sum(p['quantity_milli'] for p in ps if p['dispatch_id']==d['id'])+gift[d['id']]!=d['quantity_milli']:_fail('申请时原装件既未拆回也未明确无偿随车移交')
        charge=q['goods_cents']+q['installation_cents']-sum(p['goods_cents']+p['installation_cents']-p['retained_cents'] for p in ps)
        paid=sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in t['flow_payment_links'] if p['case_id']==o['id'] and before(cash[p['cash_id']]['created_at'],requested_at))
        paid+=sum(c['amount_cents'] for c in t['business_finance_credit_links'] if c['case_id']==o['id'] and before(advance[c['entry_id']]['occurred_at'],requested_at))
        if paid!=charge:_fail('申请时原加装保留费或退款尚未结清')
        needs_acceptance=charge or q.get('pricing_version',1)==2 and any(d['quantity_milli']>sum(p['quantity_milli'] for p in ps if p['dispatch_id']==d['id']) for d in ds)
        if needs_acceptance and not any(a['quote_id']==q['id'] and before(a['created_at'],requested_at) for a in t['addon_acceptances']):_fail('保留收费或赠送实物缺少申请前客户实际接收确认')
    return True

def validate_addon_credit_return(connection,credit_id):
    t=_load(connection)
    if not t:return False
    credits={r['id']:r for r in t['business_finance_credit_links']};credit=credits.get(credit_id)
    if not credit or credit['amount_cents']>=0 or not credit['original_id']:return False
    source=credits.get(credit['original_id']);links=[p for p in t['addon_payments'] if p['credit_link_id']==credit_id]
    if len(links)!=1 or not source or source['amount_cents']<=0 or source['case_id']!=credit['case_id'] or source['store_id']!=credit['store_id'] or not links[0]['resolution_id']:return False
    plan=next((p for p in t['addon_resolutions'] if p['id']==links[0]['resolution_id']),None)
    if not plan or plan['case_id']!=credit['case_id'] or plan['status']!='completed' or plan['kind']=='vehicle_gift':return False
    if -sum(c['amount_cents'] for c in credits.values() if c['original_id']==source['id'])>source['amount_cents']:return False
    original_entries={r['id']:r for r in t['business_finance_advance_entries']};old=original_entries.get(source['entry_id']);new=original_entries.get(credit['entry_id'])
    if not old or not new or old['advance_id']!=new['advance_id'] or new['evidence_id']!=links[0]['evidence_id']:return False
    return True
