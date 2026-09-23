"""Offline reconstruction of original supplier authority and exact cash capacity."""
import json
from datetime import datetime,timezone

def _json(value):return json.loads(value) if isinstance(value,str) else value
def _time(value):
    value=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
def _fail(message):raise ValueError('非客户整车收入恢复检查：'+message)

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'vehicle_income_orders' not in names:return {'verified_vehicle_income_orders':0}
    def rows(name):
        if name not in names:return []
        fields='id,store_id,case_id,category,generated,sha256,created_at' if name=='flow_files' else '*'
        cursor=connection.execute('SELECT '+fields+' FROM '+name);keys=[c[0] for c in cursor.description];return [dict(zip(keys,r)) for r in cursor]
    tables={n:rows(n) for n in names if n.startswith('vehicle_income_') or n in {'flow_cases','flow_files','flow_events','flow_accounts','cash_entries','flow_payment_links','flow_vehicle_holds','vehicles','master_suppliers','vehicle_purchase_orders','vehicle_purchase_prices','vehicle_purchase_receipts','vehicle_position_entries','business_entity_case_contexts'}}
    by=lambda name:{r['id']:r for r in tables.get(name,[])}
    orders=by('vehicle_income_orders');cases=by('flow_cases');files=by('flow_files');cash=by('cash_entries');accounts=by('flow_accounts');vehicles=by('vehicles');revisions=by('vehicle_income_revisions');entries=by('vehicle_income_cash');events=by('flow_events')
    decisions={r['revision_id']:r for r in tables.get('vehicle_income_decisions',[])}
    if len(decisions)!=len(tables.get('vehicle_income_decisions',[])):_fail('同一目标被重复决定')
    from .flow_engine import request_digest
    def same(left,right):return left and right and left['store_id']==right['store_id']
    used_proofs=set()
    def proof(row,case,receipt=False):
        f=files.get(row.get('evidence_id'))
        if not same(row,case) or not same(case,f) or f['case_id']!=case['id'] or f['generated'] or (f['category']!='receipt' if receipt else f['category'] not in {'evidence','authorization','signed_contract','invoice'}):_fail('事实没有本单本店的实际原件')
        key=(case['id'],f['sha256'])
        if key in used_proofs:_fail('同一原件重复确认不同事实')
        used_proofs.add(key)
    contexts={r['case_id']:r for r in tables.get('business_entity_case_contexts',[])}
    for order in orders.values():
        case=cases.get(order['id']);supplier=by('master_suppliers').get(order['supplier_id']);snapshot=_json(order['supplier_snapshot'])
        if not same(case,order) or not same(order,supplier) or case['kind']!='vehicle_income' or case['flow_version']!=1 or case['customer_id'] is not None or case['parent_id']!=order['primary_source_case_id'] or snapshot['id']!=supplier['id'] or order['actor_id']!=case['created_by']:_fail('原往来单位、门店或非客户身份被改写')
        sources=[s for s in tables.get('vehicle_income_sources',[]) if s['case_id']==case['id']]
        if not sources or order['primary_source_case_id'] not in {s['source_case_id'] for s in sources}:_fail('没有明确原车辆业务依据')
        seen=set()
        for s in sources:
            original=cases.get(s['source_case_id']);snap=_json(s['snapshot']);identity=(s['source_case_id'],s['vehicle_id'])
            if identity in seen:_fail('原来源车辆重复')
            seen.add(identity)
            if not same(case,s) or not same(s,original) or original['id']>=case['id'] or s['digest']!=request_digest('vehicle_income_source',snap):_fail('原来源关联或冻结摘要无效')
            if any(snap[k]!=original[field] for k,field in [('case_id','id'),('number','number'),('kind','kind'),('flow_version','flow_version')]) or snap['version']!=s['source_version'] or s['source_version']>original['version'] or snap['vehicle_id']!=s['vehicle_id']:_fail('冻结原单身份或版本不一致')
            context=contexts.get(original['id'])
            if snap['entity_revision_id']!=(context['revision_id'] if context else None):_fail('原来源冻结主体被替换或补认')
            if s['vehicle_id']:
                vehicle=vehicles.get(s['vehicle_id'])
                if not same(vehicle,case) or vehicle['vin']!=snap['vin']:_fail('原VIN或车辆代次串单')
                if original['kind']=='order':
                    event=events.get(snap.get('allocation_event_id'))
                    if not same(event,case) or event['case_id']!=original['id'] or event['action']!='allocate' or _json(event['detail']).get('vehicle_id')!=vehicle['id'] or _time(event['occurred_at'])>_time(case['created_at']):_fail('原销售VIN没有当时配车事实')
                elif original['kind']=='vehicle_procurement':
                    if not any(r['case_id']==original['id'] and r['vehicle_id']==vehicle['id'] for r in tables.get('vehicle_purchase_receipts',[])):_fail('原采购VIN没有实际接收')
                elif original['kind'] in {'vehicle_operations','opening_import'}:
                    if not any(r['case_id']==original['id'] and r['vehicle_id']==vehicle['id'] and r['quantity']==1 for r in tables.get('vehicle_position_entries',[])):_fail('原VIN没有对应实际入库')
                else:_fail('不支持此整车来源')
            elif original['kind'] not in {'order','vehicle_procurement'} or snap['vin'] is not None or snap.get('allocation_event_id') is not None:_fail('无VIN来源须明确关联原销售或采购整单')
        prior=None
        sequence=sorted((r for r in revisions.values() if r['case_id']==case['id']),key=lambda r:r['id'])
        for number,r in enumerate(sequence,1):
            proof(r,case)
            fields=['previous_id','previous_cents','target_cents','invoice_mode','due_date','source_versions','reason','evidence_id'];payload={k:_json(r[k]) if k=='source_versions' else r[k] for k in fields}
            if r['revision']!=number or r['digest']!=request_digest('vehicle_income_revision',payload) or set(payload['source_versions'])!={str(s['source_case_id']) for s in sources}:_fail('目标修订次序、来源版本或摘要被改写')
            if r['invoice_mode'] not in {'store_invoice','external_document'} or r['target_cents']<0 or (r['previous_id'],r['previous_cents'])!=(prior['id'] if prior else None,prior['target_cents'] if prior else 0):_fail('应收目标没有沿原已批准版本追加')
            d=decisions.get(r['id'])
            if d:
                if not same(r,d) or _time(d['created_at'])<_time(r['created_at']):_fail('决定先于原提议或跨店')
                if d['decision'] in {'approved','rejected'}:
                    proof(d,case)
                    if d['actor_id'] in {r['actor_id'],case['created_by']}:_fail('目标批准或拒绝没有独立主管')
                elif d['decision']!='withdrawn':_fail('未知目标决定')
                if d['decision']=='approved':prior=r
            elif r is not sequence[-1]:_fail('待复核目标未处理又追加新版本')
        if case['amount_cents']!=(prior['target_cents'] if prior else 0):_fail('当前应收没有来自最后独立批准目标')
        if case['state']=='cancelled' and (prior or any(p['case_id']==case['id'] for p in entries.values())):_fail('已批准或真实收款被普通取消')
        net=0;returned={}
        for p in sorted((p for p in entries.values() if p['case_id']==case['id']),key=lambda p:p['id']):
            proof(p,case,True);actual=cash.get(p['cash_id']);account=accounts.get(p['account_id']);r=revisions.get(p['revision_id']);d=decisions.get(p['revision_id']);at=_time(p['created_at'])
            approved=[x for x in sequence if decisions.get(x['id'],{}).get('decision')=='approved' and _time(decisions[x['id']]['created_at'])<=at]
            pending=[x for x in sequence if _time(x['created_at'])<=at and (x['id'] not in decisions or _time(decisions[x['id']]['created_at'])>at)]
            if not same(p,actual) or not same(p,account) or not approved or pending or approved[-1]['id']!=p['revision_id'] or not r or r['case_id']!=case['id'] or not d or d['decision']!='approved':_fail('资金没有当时有效且无待修订的独立批准目标')
            expected_category='vehicle_other_income_in' if p['direction']=='in' else 'vehicle_other_income_out';account_snapshot=_json(p['account_snapshot'])
            if account_snapshot['id']!=account['id'] or account_snapshot['version']>account['version']:_fail('原资金账户快照与本店账户版本不一致')
            if (actual['direction'],actual['amount_cents'],actual['business_date'],actual['account'],actual['voucher_no'],actual['counterparty'],actual['category'],actual['created_by'])!=(p['direction'],p['amount_cents'],p['business_date'],account_snapshot['name'],p['reference'],snapshot['name'],expected_category,p['actor_id']) or actual['approval_state']!='approved' or p['business_date']<d['business_date']:_fail('专域资金链接与唯一实际现金或原往来单位不符')
            if p['direction']=='in':
                if p['original_id'] or p['amount_cents']>r['target_cents']-net:_fail('到账超过当时批准未收余额')
                net+=p['amount_cents']
            elif p['direction']=='out':
                original=entries.get(p['original_id'])
                if not original or original['id']>=p['id'] or (original['case_id'],original['direction'],original['account_id'])!=(case['id'],'in',p['account_id']) or p['business_date']<original['business_date']:_fail('退款没有本单原到账或改换原账户')
                returned[original['id']]=returned.get(original['id'],0)+p['amount_cents']
                if returned[original['id']]>original['amount_cents'] or p['amount_cents']>net-r['target_cents']:_fail('退款超过原款余额或已批准超收')
                net-=p['amount_cents']
            else:_fail('资金方向无效')
        if case['state']=='completed' and (not prior or net!=prior['target_cents'] or any(r['id'] not in decisions for r in sequence)):_fail('尚有未结原款或目标复核就标记完成')
    domain_ids={p['cash_id'] for p in entries.values()}
    if len(domain_ids)!=len(entries) or domain_ids!={c['id'] for c in cash.values() if c['category'] in {'vehicle_other_income_in','vehicle_other_income_out'}}:_fail('实际现金缺少唯一非客户来源链接')
    if any(p['case_id'] in orders for p in tables.get('flow_payment_links',[])):_fail('非客户收入被伪装成客户收款')
    return {'verified_vehicle_income_orders':len(orders),'verified_vehicle_income_revisions':len(revisions),'verified_vehicle_income_cash':len(entries)}
