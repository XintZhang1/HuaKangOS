"""Read-only reconstruction of independent member price authority and original amounts."""
import json,hashlib
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from .config import settings

def data(v):return json.loads(v) if isinstance(v,str) else v

def stamp(v):
    d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d

def business_day(value):return stamp(value).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()

def has_tables(connection):return {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

def quote_digest(connection,case_id,kind,quote_id):
    if 'member_pricing_snapshots' not in has_tables(connection):return None
    row=connection.execute('SELECT digest FROM member_pricing_snapshots WHERE case_id=? AND quote_kind=? AND quote_id=?',(case_id,kind,quote_id)).fetchone()
    return row[0] if row else None

def retail_prices(connection,case_id):
    if 'member_pricing_snapshots' not in has_tables(connection):return None
    row=connection.execute("SELECT contract FROM member_pricing_snapshots WHERE case_id=? AND quote_kind='retail' AND quote_id=?",(case_id,case_id)).fetchone()
    if not row:return None
    return {(p['line_key'],p['component']):p['carry_cents']+p['net_cents'] for p in data(row[0])['lines']}

def validate(connection):
    names=has_tables(connection)
    required={'member_pricing_rules','member_pricing_scopes','member_pricing_decisions','member_pricing_snapshots','member_pricing_lines','member_pricing_authorizations'}
    if not names&required:
        case_exists='flow_cases' in names and connection.execute("SELECT 1 FROM flow_cases WHERE kind='member_pricing_rule' LIMIT 1").fetchone()
        event_exists='flow_events' in names and connection.execute("SELECT 1 FROM flow_events WHERE action LIKE 'member_price_%' LIMIT 1").fetchone()
        if case_exists or event_exists:raise ValueError('会员价格恢复核对：已有原规则或批准事件但六张价格表全部缺失')
        return {'verified_member_pricing_rules':0,'verified_member_pricing_snapshots':0}
    def require(ok,msg):
        if not ok:raise ValueError('会员价格恢复核对：'+msg)
    require(required<=names,'新价格结构不完整')
    def rows(name):
        if name not in names:return []
        fields='id,store_id,case_id,category,generated,sha256,created_at' if name=='flow_files' else '*'
        c=connection.execute('SELECT '+fields+' FROM '+name);keys=[x[0] for x in c.description];return [dict(zip(keys,r)) for r in c]
    tables={name:rows(name) for name in required|{'flow_cases','flow_files','flow_events','flow_items','master_work_items','master_member_tiers','membership_rules','membership_periods','membership_period_voids','membership_events','group_members','group_identity_links','repair_quotes','repair_lines','repair_authorizations','addon_quotes','addon_lines','addon_authorizations','retail_lines','retail_bundle_allocations','retail_bundle_sales','rework_line_scopes'}}
    indexed=lambda n:{x['id']:x for x in tables[n]}
    rules=indexed('member_pricing_rules');cases=indexed('flow_cases');files=indexed('flow_files');m_rules=indexed('membership_rules');periods=indexed('membership_periods');members=indexed('group_members');scopes=indexed('member_pricing_scopes');snaps=indexed('member_pricing_snapshots')
    decisions=tables['member_pricing_decisions'];authorizations=tables['member_pricing_authorizations'];price_lines=tables['member_pricing_lines']
    from .member_pricing_service import canonical,_distribute,LINE_FIELDS
    def same(a,b):return a and b and a['store_id']==b['store_id']
    def proof(fact,case):
        f=files.get(fact['evidence_id']);require(same(f,case) and f['case_id']==case['id'] and not f['generated'] and f['category'] in {'evidence','authorization'},'价格批准凭据不是本店本人原申请依据');return f
    def approved_at(rule_id,at):return next((d for d in decisions if d['rule_id']==rule_id and d['decision']=='approved' and stamp(d['created_at'])<=at),None)
    def latest_at(rule,at):return max((r for r in rules.values() if r['store_id']==rule['store_id'] and r['code']==rule['code'] and approved_at(r['id'],at)),key=lambda r:r['rule_version'],default=None)
    def execution_at(case_id):
        events=[e for e in tables['membership_events'] if e['case_id']==case_id and e['action']=='execute']
        return min((stamp(e['occurred_at']) for e in events),default=None)
    def period_at(member_id,at):
        day=business_day(at).isoformat();eligible=[]
        for p in periods.values():
            t=execution_at(p['case_id'])
            if p['member_id']!=member_id or not t or t>at or not p['starts_on']<=day<=p['ends_on']:continue
            if any(v['period_id']==p['id'] and execution_at(v['case_id']) and execution_at(v['case_id'])<=at for v in tables['membership_period_voids']):continue
            eligible.append(p)
        return max(eligible,key=lambda p:(p['starts_on'],p['id']),default=None)
    def membership_at(rule,at):
        origin=m_rules[rule['membership_rule_id']]
        return max((m for m in m_rules.values() if m['code']==origin['code'] and stamp(m['created_at'])<=at),key=lambda m:m['rule_version'],default=None)
    for rule in rules.values():
        case=cases.get(rule['case_id']);original=m_rules.get(rule['membership_rule_id']);own=sorted((s for s in scopes.values() if s['rule_id']==rule['id']),key=lambda s:s['sequence'])
        require(same(case,rule) and case['kind']=='member_pricing_rule' and case['flow_version']==1 and case['created_by']==rule['actor_id'] and original,'规则门店、原会期版本或申请主体无效')
        member_snapshot={k:original[k] for k in ('id','code','rule_version','name','allowed_store_ids')};member_snapshot['allowed_store_ids']=data(member_snapshot['allowed_store_ids'])
        require(data(rule['membership_snapshot'])==member_snapshot and rule['store_id'] in member_snapshot['allowed_store_ids'],'规则不是当时明确适用本店的集团等级原版本')
        require([s['sequence'] for s in own]==list(range(1,len(own)+1)) and (own or not rule['enabled']),'明确项目范围缺失')
        scope_payload=[];seen=set()
        for s in own:
            source=indexed('master_work_items' if s['component'] in {'work','installation'} else 'flow_items').get(s['source_id']);frozen=data(s['source_snapshot'])
            key=(s['business_kind'],s['component'],s['source_id'],s['bundle_rule_id'],s['allow_contract_pricing'])
            require(same(s,rule) and same(source,s) and key not in seen and frozen['id']==source['id'] and frozen['version']<=source['version'] and 1<=s['basis_points']<=10000,'明确项目门店、比例或冻结版本无效');seen.add(key)
            part={k:data(s[k]) if k in {'source_snapshot','bundle_snapshot'} else s[k] for k in ('business_kind','component','source_id','source_snapshot','basis_points','bundle_rule_id','bundle_snapshot','allow_contract_pricing')};part['allow_contract_pricing']=bool(part['allow_contract_pricing']);scope_payload.append(part)
        payload={k:rule[k] for k in ('code','name','enabled','membership_rule_id','starts_on','ends_on','stack_mode','reason','rule_version','reference_tier_id')};payload.update(enabled=bool(rule['enabled']),membership_snapshot=member_snapshot,reference_tier_snapshot=data(rule['reference_tier_snapshot']),scopes=scope_payload)
        require(canonical(payload)==rule['digest'],'本店规则、参考等级或明确比例冻结摘要被更改')
        own_d=sorted((d for d in decisions if d['rule_id']==rule['id']),key=lambda d:d['id']);past=None;used=set()
        for d in own_d:
            require(same(d,rule) and stamp(d['created_at'])>=stamp(rule['created_at']),'决定早于申请或跨店')
            if d['decision']=='cancelled':require(past in {None,'submitted'},'已批准后普通取消价格')
            else:
                f=proof(d,case);require(f['sha256'] not in used,'同一原件充当独立核对');used.add(f['sha256'])
                if d['decision']=='submitted':require(past is None and d['actor_id']==rule['actor_id'],'未由原申请人提交')
                else:require(past=='submitted' and d['decision'] in {'approved','rejected'} and d['actor_id']!=rule['actor_id'],'会员价格缺少独立复核')
            past=d['decision']
        expected={'submitted':'approval','approved':'completed','rejected':'rejected','cancelled':'cancelled',None:'draft'}[past]
        require(case['state']==expected,'规则状态不来自独立决定')
    for snap in snaps.values():
        case=cases.get(snap['case_id']);rule=rules.get(snap['rule_id']);contract=data(snap['contract']);identity=contract['identity'];at=stamp(snap['created_at']);period=periods.get(snap['period_id']);member=members.get(snap['member_id']);last=latest_at(rule,at) if rule else None
        require(same(snap,case) and same(snap,rule) and snap['definition_version']==1 and snap['quote_kind']==case['kind'] and case['customer_id']==snap['customer_id'],'会员价格串店、串单、串客户或版本未知')
        require(canonical(contract)==snap['digest'] and contract['rule_digest']==rule['digest'] and contract['rule_id']==rule['id'] and contract['rule_version']==rule['rule_version'] and contract['stack_mode']==rule['stack_mode'],'报价不来自冻结的独立批准价格版本')
        require(contract['store_id']==case['store_id'] and contract['customer_id']==case['customer_id'] and contract['case_kind']==case['kind'] and contract['flow_version']==case['flow_version'],'报价身份与原业务不一致')
        require(last and last['id']==rule['id'] and rule['enabled'] and contract['priced_on']==business_day(at).isoformat() and rule['starts_on']<=contract['priced_on']<=rule['ends_on'],'报价当时没有本店已生效原规则')
        require(period and member and period['member_id']==member['id'] and period['rule_id']==rule['membership_rule_id'] and member['identity_id']==identity['identity_id'],'报价会员和实际会期来源不一致')
        expected=dict(member_id=member['id'],identity_id=member['identity_id'],period_id=period['id'],membership_rule_id=period['rule_id'],starts_on=period['starts_on'],ends_on=period['ends_on'])
        require(identity==expected and period_at(member['id'],at)==period,'报价当时有效会期或等级被替换')
        member_rule=membership_at(rule,at);require(member_rule and member_rule['enabled'] and case['store_id'] in data(member_rule['allowed_store_ids']),'报价使用当时已停用或无本店适用权限的等级')
        require(any(l['store_id']==case['store_id'] and l['local_kind']=='customer' and l['local_id']==case['customer_id'] and l['identity_id']==member['identity_id'] and stamp(l['confirmed_at'])<=at for l in tables['group_identity_links']),'报价借用未明确关联的客户身份')
        own=[p for p in price_lines if p['snapshot_id']==snap['id']];parts=contract['lines'];require(len(own)==len(parts) and len({(p['line_key'],p['component']) for p in parts})==len(parts),'会员价格组件缺失或重复')
        matched=False;weights=[]
        for p,line in zip(parts,own):
            require(same(line,snap) and all(line[k]==p[k] for k in LINE_FIELDS),'原价格拆分与冻结合同不一致')
            scope=scopes.get(p['scope_id']) if p['scope_id'] else None;rate=10000
            if p.get('price_source')=='package_contract':require(p.get('contract_rule_id') and p.get('contract_component_id') and not scope and p['member_discount_cents']==p['manual_discount_cents']==0 and p['net_cents']==p['basis_cents'],'已购套餐合同被再次会员或人工折价')
            if scope:
                matched=True;rate=scope['basis_points']
                require(scope['rule_id']==rule['id'] and scope['business_kind']==case['kind'] and (scope['component'],scope['source_id'],scope['bundle_rule_id'])==(p['component'],p['source_id'],p.get('bundle_rule_id')) and p['charge_scope']!='original_liability','会员折扣用于未批准项目、套装或原责任')
            require(p['basis_points']==rate and p['member_discount_cents']==p['basis_cents']-(p['basis_cents']*rate+5000)//10000 and (p['basis_cents']==0 or p['basis_cents']-p['member_discount_cents']>0),'会员折扣比例、整数舍入或零价赠送边界不符')
            require(p['basis_cents']==p['member_discount_cents']+p['manual_discount_cents']+p['net_cents'] and min(p['carry_cents'],p['basis_cents'],p['manual_discount_cents'],p['net_cents'])>=0,'会员价格分摊不守恒')
            weights.append(p['basis_cents']-p['member_discount_cents'] if p['charge_scope']!='original_liability' and p.get('price_source')!='package_contract' else 0)
        require(matched and _distribute(sum(p['manual_discount_cents'] for p in parts),weights)==[p['manual_discount_cents'] for p in parts],'人工优惠没有沿会员价后的新增部分分摊')
        kind=snap['quote_kind'];qid=snap['quote_id']
        if kind=='repair':
            quote=indexed('repair_quotes').get(qid);lines=[l for l in tables['repair_lines'] if l['quote_id']==qid]
            require(same(quote,case) and quote['case_id']==case['id'] and len(parts)==len(lines),'原维修报价或明细关联缺失')
            for line in lines:
                p=next((p for p in parts if p['line_key']==line['line_key'] and p['component']==line['kind']),None)
                require(p and p['source_id']==(line['work_item_id'] if line['kind']=='work' else line['item_id']) and line['amount_cents']==p['carry_cents']+p['net_cents'],'维修原金额不等于冻结会员价')
                previous_quotes=[q for q in tables['repair_quotes'] if q['case_id']==case['id'] and q['revision']<quote['revision'] and any(a['quote_id']==q['id'] and stamp(a['created_at'])<=at for a in tables['repair_authorizations'])]
                previous=max(previous_quotes,key=lambda q:q['revision'],default=None)
                prior=next((l for l in tables['repair_lines'] if previous and l['quote_id']==previous['id'] and l['line_key']==line['line_key']),None)
                gross=(line['quantity_milli']*line['unit_price_cents']+500)//1000
                if prior:
                    require(line['kind']==prior['kind'] and line['work_item_id']==prior['work_item_id'] and line['item_id']==prior['item_id'] and line['unit_price_cents']==prior['unit_price_cents'] and line['quantity_milli']>=prior['quantity_milli'],'维修承接行更换了已授权来源或基价')
                if p.get('price_source')=='package_contract':
                    from .repair_package_integrity import member_quote_basis
                    original=member_quote_basis(connection,case['id'],qid,line['line_key'])
                    require(original and all(p[k]==original[k] for k in ('basis_cents','carry_cents','contract_rule_id','contract_component_id')),'已购套餐原组件基价被替换')
                else:
                    expected_basis=gross-((prior['quantity_milli']*prior['unit_price_cents']+500)//1000 if prior else 0)
                    require(p['basis_cents']==expected_basis and p['carry_cents']==(prior['amount_cents'] if prior else 0),'维修新增原基价或原已授权金额被改写')
                responsibility=next((x['charge_scope'] for x in tables['rework_line_scopes'] if x['line_id']==line['id']),'customer');require(p['charge_scope']==responsibility,'原责任分类被偷换成折扣消费')
            ordered=sorted(lines,key=lambda l:l['id']);payload={'purpose':quote['purpose'],'reason':quote['reason'],'lines':[{k:l[k] for k in ('line_key','kind','work_item_id','item_id','code','name','unit','standard_fee_cents','quantity_milli','unit_price_cents','amount_cents','discount_cents')} for l in ordered],'member_pricing':snap['digest']}
            responsibility=[next((x for x in tables['rework_line_scopes'] if x['line_id']==l['id']),None) for l in ordered]
            if any(responsibility):
                require(all(responsibility),'原返修逐行分类缺失');payload['rework_scopes']=[{k:x[k] for k in ('charge_scope','source_line_id')} for x in responsibility]
            if 'repair_package_quote_snapshots' in names:
                original=connection.execute('SELECT digest FROM repair_package_quote_snapshots WHERE case_id=? AND quote_id=?',(case['id'],qid)).fetchone()
                if original:payload['repair_package']=original[0]
            require(hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()==quote['digest'],'维修报价摘要未绑定会员及原组件冻结事实')
        elif kind=='addon':
            quote=indexed('addon_quotes').get(qid);lines=[l for l in tables['addon_lines'] if l['quote_id']==qid];require(same(quote,case) and quote['case_id']==case['id'] and len(parts)==2*len(lines),'原加装报价或明细关联缺失')
            for line in lines:
                for component,field,source in [('goods','goods_cents','item_id'),('installation','installation_cents','work_item_id')]:
                    p=next((p for p in parts if p['line_key']==line['line_key'] and p['component']==component),None);require(p and p['source_id']==line[source] and line[field]==p['carry_cents']+p['net_cents'],'加装原价与会员冻结金额不一致')
                    fixed=any(a['quote_id'] in {q['id'] for q in tables['addon_quotes'] if q['case_id']==case['id']} and stamp(a['created_at'])<=at for a in tables['addon_authorizations'])
                    previous=max((q for q in tables['addon_quotes'] if q['case_id']==case['id'] and q['revision']<quote['revision']),key=lambda q:q['revision'],default=None)
                    prior=next((l for l in tables['addon_lines'] if fixed and previous and l['quote_id']==previous['id'] and l['line_key']==line['line_key']),None)
                    unit='goods_unit_cents' if component=='goods' else 'installation_unit_cents'
                    require(not prior or all(line[k]==prior[k] for k in ('quantity_milli','goods_unit_cents','installation_unit_cents','item_id','work_item_id')),'加装已授权行来源、数量或基价被改写')
                    require(p['basis_cents']==(0 if prior else (line['quantity_milli']*line[unit]+500)//1000) and p['carry_cents']==(prior[field] if prior else 0),'加装新增原基价或已冻结承接金额被改写')
        elif kind=='retail':
            lines=[l for l in tables['retail_lines'] if l['case_id']==case['id']];require(qid==case['id'] and len(parts)==2*len(lines),'原精品报价或明细缺失')
            sale=next((s for s in tables['retail_bundle_sales'] if s['case_id']==case['id']),None)
            for line in lines:
                for component,field,source,unit in [('goods','goods_cents','item_id','unit_price_cents'),('installation','installation_cents','work_item_id','installation_unit_price_cents')]:
                    p=next((p for p in parts if p['line_key']=='item'+str(line['item_id']) and p['component']==component),None)
                    allocation=next((a for a in tables['retail_bundle_allocations'] if a['line_id']==line['id']),None)
                    basis=allocation[field] if sale and allocation else (line['quantity_milli']*line[unit]+500)//1000
                    require(p and p['source_id']==(line[source] or 0) and p['basis_cents']==basis and p['carry_cents']==0 and line[field]==p['net_cents'] and p.get('bundle_rule_id')==(sale['rule_id'] if sale else None),'精品原套装基础、会员价或分摊被改写')
        else:require(False,'不支持的会员价格业务')
        auth=[a for a in authorizations if a['snapshot_id']==snap['id']];require(len(auth)<=1,'报价客户授权重复')
        for a in auth:
            at=stamp(a['created_at']);f=files.get(a['evidence_id']);latest=latest_at(rule,at);m=membership_at(rule,at)
            require(same(a,snap) and same(f,case) and f['case_id']==case['id'] and not f['generated'] and a['snapshot_digest']==snap['digest'] and at>=stamp(snap['created_at']),'本版会员价授权不属于本单原件')
            require(latest and latest['id']==rule['id'] and rule['starts_on']<=business_day(at).isoformat()<=rule['ends_on'] and period_at(member['id'],at)==period and m and m['enabled'] and case['store_id'] in data(m['allowed_store_ids']),'原客户授权时会期或规则已失效')
            originals=tables['repair_authorizations'] if kind=='repair' else tables['addon_authorizations'] if kind=='addon' else [e for e in tables['flow_events'] if e['case_id']==case['id'] and e['action']=='retail_authorize']
            require(any((x.get('quote_id')==qid and x['evidence_id']==a['evidence_id']) if kind!='retail' else data(x['detail']).get('evidence_id')==a['evidence_id'] for x in originals),'会员价授权没有原域客户确认')
    require(all(p['snapshot_id'] in snaps for p in price_lines) and all(a['snapshot_id'] in snaps for a in authorizations),'孤立会员价格金额或授权')
    return {'verified_member_pricing_rules':len(rules),'verified_member_pricing_snapshots':len(snaps),'verified_member_pricing_authorizations':len(authorizations)}
