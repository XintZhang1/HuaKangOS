"""Independent read-only restore proof. No ORM, settings, app or current user."""
import hashlib,json
from datetime import datetime

TABLES=('rework_source_grants','rework_grant_decisions','rework_grant_receipts','rework_extensions','rework_quote_scopes','rework_line_scopes')
GRANT_FIELDS=('definition_version','from_store_id','to_store_id','source_case_id','source_case_version','source_quote_id','from_vehicle_id','to_vehicle_id','customer_identity_id','vehicle_identity_id','vin','source_number','source_lines','original_liability_limit_cents','responsible_name','recipient_id','recipient_role','recipient_access_version','requested_by','requester_role','requester_access_version','evidence_id','reason','expires_at','created_at')
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def data(value):return json.loads(value) if isinstance(value,str) else value
def timestamp(value):return datetime.fromisoformat(str(value).replace('Z','+00:00')).replace(tzinfo=None)

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    zero={'verified_rework_extension_grants':0,'verified_rework_extensions':0,'verified_rework_quote_scopes':0}
    def fail(message):raise ValueError('原责任返修恢复检查：'+message)
    if not names.intersection(TABLES):
        if 'flow_events' in names:
            if any(data(r[0]).get('rework_definition')==1 for r in connection.execute("SELECT detail FROM flow_events WHERE action='intake_rework_request'")):
                fail('已领用新责任授权但扩展来源表缺失')
        return zero
    if not set(TABLES)<=names:fail('扩展表不完整')
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);columns=[v[0] for v in cursor.description]
        return [dict(zip(columns,r)) for r in cursor]
    def by(name,key='id'):return {r[key]:r for r in rows(name)}
    grants=by(TABLES[0]);decisions=rows(TABLES[1]);extensions=by(TABLES[3],'request_id');scopes=by(TABLES[4],'quote_id');line_scopes=by(TABLES[5],'line_id')
    cases=by('flow_cases');vehicles=by('care_customer_vehicles');bindings=by('intake_vehicle_bindings','case_id');requests=by('intake_rework_requests')
    quotes=by('repair_quotes');lines=by('repair_lines');settlements=by('repair_settlements','case_id');files=by('flow_files');users=by('users');stores=by('stores')
    selected=rows('intake_rework_source_lines');contexts=by('intake_repair_contexts','case_id');events=rows('flow_events');payments=by('flow_payment_links');repair_payments=rows('repair_payments');allocations=by('repair_allocations');liabilities=by('intake_rework_liabilities','request_id')
    def same(a,b):return a and b and a['store_id']==b['store_id']
    for g in grants.values():
        scope={k:g[k] for k in GRANT_FIELDS};scope['source_lines']=data(g['source_lines'])
        for key in ('created_at','expires_at'):scope[key]=timestamp(g[key]).isoformat()
        if g['definition_version']!=1 or digest(scope)!=g['scope_digest'] or g['original_liability_limit_cents']<0 or timestamp(g['expires_at'])<=timestamp(g['created_at']):fail('授权定义、摘要或额度无效')
        source=cases.get(g['source_case_id']);settlement=settlements.get(g['source_case_id']);binding=bindings.get(g['source_case_id']);a=vehicles.get(g['from_vehicle_id']);b=vehicles.get(g['to_vehicle_id']);proof=files.get(g['evidence_id'])
        if not source or source['store_id']!=g['from_store_id'] or source['kind']!='repair' or source['flow_version'] not in (3,4) or not data(source['data']).get('released_date') or not settlement or settlement['quote_id']!=g['source_quote_id'] or source['number']!=g['source_number'] or source['version']<g['source_case_version']:fail('原维修、已交车结算或原版本不一致')
        if not binding or not a or not b or a['store_id']!=g['from_store_id'] or b['store_id']!=g['to_store_id'] or binding['customer_vehicle_id']!=a['id'] or source['customer_id']!=a['customer_id'] or any(any(v[k]!=g[k] for k in ('vin','customer_identity_id','vehicle_identity_id')) for v in (binding,a,b)):fail('原单与接收车辆客户身份或 VIN 不一致')
        if not proof or not same(proof,source) or proof['case_id']!=source['id'] or proof['generated']:fail('原责任核验凭据不属于原店原单')
        source_lines=scope['source_lines']
        if not isinstance(source_lines,list) or not source_lines or len({v.get('id') for v in source_lines})!=len(source_lines):fail('原项目范围为空或重复')
        for l in source_lines:
            original=lines.get(l.get('id'))
            if set(l)!={'id','code','name','quantity_milli'} or not original or original['quote_id']!=g['source_quote_id'] or {k:original[k] for k in l}!=l:fail('原项目范围并非冻结原结算行或超出最小投影')
        if g['requested_by'] not in users or g['recipient_id'] not in users or g['from_store_id'] not in stores or g['to_store_id'] not in stores or g['requester_role'] not in ('admin','service') or g['recipient_role'] not in ('admin','service'):fail('原责任参与身份缺失')
        chain=sorted([d for d in decisions if d['grant_id']==g['id']],key=lambda d:d['previous_version']);state='pending';version=1;last=timestamp(g['created_at'])
        for d in chain:
            action=d['action'];when=timestamp(d['occurred_at'])
            expected={'approve':'pending','reject':'pending','cancel':'pending','revoke':'approved','consume':'approved'}.get(action)
            if not expected or state!=expected or d['previous_version']!=version or d['scope_digest']!=g['scope_digest'] or d['actor_id'] not in users or when<last:fail('授权决定状态、版本、摘要或时间断链')
            if action=='consume':
                if d['store_id']!=g['to_store_id'] or d['actor_id']!=g['recipient_id'] or d['actor_role']!=g['recipient_role'] or d['actor_access_version']!=g['recipient_access_version']:fail('授权并非指定接收员工领用')
            else:
                if d['store_id']!=g['from_store_id']:fail('原责任决定不在原门店')
                if action in ('approve','reject') and (d['actor_id']==g['requested_by'] or d['actor_role'] not in ('admin','manager')):fail('原责任未独立批准')
            if action in ('approve','consume') and when>=timestamp(g['expires_at']):fail('原责任在过期后批准或领用')
            state={'approve':'approved','reject':'rejected','cancel':'cancelled','revoke':'revoked','consume':'consumed'}[action];version+=1;last=when
        if g['status']!=state or g['version']!=version:fail('当前授权与原决定链不一致')
        linked=[e for e in extensions.values() if e['grant_id']==g['id']]
        if len(linked)!=(1 if state=='consumed' else 0):fail('单次原责任授权领用数量不一致')
    if any(d['grant_id'] not in grants for d in decisions):fail('授权决定缺少原授权')
    for receipt in rows(TABLES[2]):
        g=grants.get(receipt['grant_id'])
        if not g or receipt['actor_id'] not in users or receipt['store_id']!=g['from_store_id']:fail('原责任回执来源不完整')
    for ext in extensions.values():
        g=grants.get(ext['grant_id']);r=requests.get(ext['request_id'])
        if not g or not r or ext['definition_version']!=1 or ext['grant_digest']!=g['scope_digest'] or ext['store_id']!=g['to_store_id'] or not same(ext,r) or ext['actor_id']!=g['recipient_id'] or r['requested_by']!=g['recipient_id'] or r['source_case_id']!=g['source_case_id'] or r['source_quote_id']!=g['source_quote_id'] or r['customer_vehicle_id']!=g['to_vehicle_id']:fail('本店返修契约与单次原授权不一致')
        if r['approved_by'] and r['approved_by']==r['requested_by']:fail('接收店返修未经独立复核')
        liability=liabilities.get(r['id'])
        if liability and liability['internal_name']!=g['responsible_name']:fail('接收店责任主体不是原店授权主体')
        own=[l for l in selected if l['request_id']==r['id']]
        if sorted(l['source_line_id'] for l in own)!=sorted(l['id'] for l in data(g['source_lines'])) or any(not same(l,r) for l in own):fail('本次责任原行与原授权不一致')
        created=[e for e in events if e['case_id']==r['case_id'] and e['action']=='intake_rework_request']
        if len(created)!=1 or data(created[0]['detail'])!={'rework_definition':1,'grant_id':g['id'],'grant_digest':g['scope_digest']}:fail('本次领用缺少原授权事件摘要')
        if not r['repair_case_id']:continue
        repair=cases.get(r['repair_case_id']);ctx=contexts.get(r['repair_case_id'])
        if not same(repair,r) or not ctx or ctx['rework_id']!=r['id'] or repair['flow_version']!=4:fail('扩展工单缺少明确返修来源')
        own_quotes=[q for q in quotes.values() if q['case_id']==repair['id']]
        if any(q['id'] not in scopes or scopes[q['id']]['request_id']!=r['id'] for q in own_quotes):fail('扩展报价缺少不可变责任分类')
        settlement=settlements.get(repair['id'])
        own_allocations=[a for a in allocations.values() if a['case_id']==repair['id']]
        if settlement:
            q=scopes.get(settlement['quote_id']);expected={}
            if not q:fail('已结算扩展缺少当前分类')
            if q['original_liability_cents']:expected['internal']=q['original_liability_cents']
            if q['customer_extra_cents']:expected['customer']=q['customer_extra_cents']
            if {a['payer_type']:a['amount_cents'] for a in own_allocations}!=expected or len(own_allocations)!=len(expected) or any(not same(a,repair) or (a['payer_type']=='internal' and a['payer_name']!=g['responsible_name']) for a in own_allocations):fail('原责任与客户承担并非冻结行合计')
        for p in payments.values():
            if p['case_id']!=repair['id']:continue
            links=[x for x in repair_payments if x['payment_link_id']==p['id']]
            a=allocations.get(links[0]['allocation_id']) if len(links)==1 else None
            if not a or a['case_id']!=repair['id'] or a['payer_type']!='customer' or not same(p,repair) or not same(links[0],repair):fail('返修现金不是本次客户新增承担的实际收款')
    for q in scopes.values():
        ext=extensions.get(q['request_id']);quote=quotes.get(q['quote_id']);r=requests.get(q['request_id'])
        if not ext or not r or not quote or quote['case_id']!=r['repair_case_id'] or not same(q,quote):fail('报价责任分类不在关联返修')
        g=grants[ext['grant_id']];allowed={l['id'] for l in data(g['source_lines'])};quote_lines=sorted([l for l in lines.values() if l['quote_id']==quote['id']],key=lambda l:l['id']);parts=[];specs=[];totals={'original_liability':0,'customer_extra':0}
        for line in quote_lines:
            p=line_scopes.get(line['id'])
            if not p or not same(p,line) or p['quote_id']!=quote['id'] or p['charge_scope'] not in totals or (p['charge_scope']=='original_liability' and p['source_line_id'] not in allowed) or (p['charge_scope']=='customer_extra' and p['source_line_id'] is not None):fail('报价行责任范围无效')
            parts.append({k:p[k] for k in ('charge_scope','source_line_id')});totals[p['charge_scope']]+=line['amount_cents']
            specs.append({k:line[k] for k in ('line_key','kind','work_item_id','item_id','code','name','unit','standard_fee_cents','quantity_milli','unit_price_cents','amount_cents','discount_cents')})
        quote_payload={'purpose':quote['purpose'],'reason':quote['reason'],'lines':specs,'rework_scopes':parts}
        from .member_pricing_integrity import quote_digest as member_quote_digest
        member_price=member_quote_digest(connection,quote['case_id'],'repair',quote['id'])
        if member_price:quote_payload['member_pricing']=member_price
        from .repair_package_integrity import quote_digest as package_quote_digest
        package_price=package_quote_digest(connection,quote['case_id'],quote['id'])
        if package_price:quote_payload['repair_package']=package_price
        quote_digest=hashlib.sha256(json.dumps(quote_payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if quote_digest!=quote['digest'] or q['digest']!=digest({'quote_digest':quote['digest'],'scopes':parts}) or totals['original_liability']!=q['original_liability_cents'] or totals['customer_extra']!=q['customer_extra_cents'] or sum(totals.values())!=quote['amount_cents'] or totals['original_liability']>g['original_liability_limit_cents']:fail('报价分类摘要、金额或原责任限额不一致')
    if any(p['quote_id'] not in scopes or p['line_id'] not in lines for p in line_scopes.values()):fail('报价行分类存在孤立来源')
    return {'verified_rework_extension_grants':len(grants),'verified_rework_extensions':len(extensions),'verified_rework_quote_scopes':len(scopes)}
