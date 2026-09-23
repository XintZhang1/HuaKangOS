"""Offline replay of original-VIN investigations; no writes, no file byte loading.

Checks internal consistency and original attribution. This is not an external
signature protecting against an administrator rewriting all original evidence.
"""
from collections import defaultdict
from datetime import datetime
import json
from . import vehicle_transport_rules as rules

DOMAIN_TABLES = {
    'vehicle_transport_exceptions', 'vehicle_transport_observations', 'vehicle_transport_plans',
    'vehicle_transport_reviews', 'vehicle_transport_withdrawals', 'vehicle_transport_disposals',
    'vehicle_transport_found_unavailable', 'vehicle_transport_losses', 'vehicle_transport_loss_settlements',
    'vehicle_transport_found_receipts', 'vehicle_transport_found_settlements', 'vehicle_transport_requests',
    'vehicle_transport_claims', 'vehicle_transport_claim_plans', 'vehicle_transport_claim_reviews',
    'vehicle_transport_claim_withdrawals', 'vehicle_transport_claim_payments',
}
DATETIMES = {'created_at', 'updated_at', 'actual_at', 'occurred_at'}
JSON_FIELDS = {'snapshot', 'detail', 'data', 'counterparty_snapshot', 'result'}


def read_rows(connection, name, columns='*'):
    cursor = connection.execute('SELECT ' + columns + ' FROM ' + name)
    keys = [d[0] for d in cursor.description]
    result = []
    for values in cursor:
        row = dict(zip(keys, values))
        for key in DATETIMES & row.keys():
            if row[key] is not None: row[key] = rules.timestamp(row[key]).isoformat()
        for key in JSON_FIELDS & row.keys():
            if row[key] is not None and isinstance(row[key], str): row[key] = json.loads(row[key])
        result.append(row)
    return result


def group(rows, field):
    result = defaultdict(list)
    for row in rows: result[row[field]].append(row)
    return result


def keyed(rows): return {r['id']: r for r in rows}


def validate_vehicle_transport(connection):
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    empty = {'verified_vehicle_transport_exceptions': 0, 'verified_vehicle_transport_losses': 0,
        'verified_vehicle_transport_found': 0, 'verified_vehicle_transport_claims': 0}
    if not DOMAIN_TABLES & tables: return empty
    if not DOMAIN_TABLES <= tables: raise ValueError('整车运输差异来源表不完整，不能按旧库空域忽略')
    data = {name: read_rows(connection, name) for name in DOMAIN_TABLES}
    parents = keyed(read_rows(connection, 'vehicle_transfers'))
    cars = keyed(read_rows(connection, 'vehicles'))
    cases = keyed(read_rows(connection, 'flow_cases'))
    files = keyed(read_rows(connection, 'flow_files', 'id,store_id,case_id,category,generated'))
    events = read_rows(connection, 'flow_events')
    event_by = group(events, 'case_id')
    moves = keyed(read_rows(connection, 'vehicle_movements'))
    positions = read_rows(connection, 'vehicle_position_entries')
    locs = keyed(read_rows(connection, 'master_locations'))
    warehouses = keyed(read_rows(connection, 'master_warehouses'))
    identities=read_rows(connection,'group_identity_links')
    exs = keyed(data['vehicle_transport_exceptions'])
    observations = keyed(data['vehicle_transport_observations'])
    plans = keyed(data['vehicle_transport_plans'])
    reviews = group(data['vehicle_transport_reviews'], 'plan_id')
    withdrawals = group(data['vehicle_transport_withdrawals'], 'plan_id')
    loss_by_ex = group(data['vehicle_transport_losses'], 'exception_id')
    found_by_ex = group(data['vehicle_transport_found_receipts'], 'exception_id')
    active_by_parent = defaultdict(list)
    by_ex = {name: group(rows, 'exception_id') for name, rows in data.items() if rows and 'exception_id' in rows[0]}
    from .config import settings
    zone = settings.timezone

    def local_case(parent, sid):
        if sid not in {parent['from_store_id'], parent['to_store_id']}: raise ValueError('整车差异记录超出原调拨双方')
        key = parent['from_case_id'] if sid == parent['from_store_id'] else parent['to_case_id']
        case = cases.get(key)
        if not case or (case['store_id'], case['kind'], case['flow_version']) != (sid, 'vehicle_transfer', 2):
            raise ValueError('整车差异未绑定本店原调拨单')
        return key

    def proof(row, parent, financial=False):
        cid = local_case(parent, row['store_id'])
        f = files.get(row['evidence_id'])
        categories = {'receipt', 'procurement_contract'} if financial else {'evidence', 'inspection', 'authorization'}
        if not f or (f['store_id'], f['case_id']) != (row['store_id'], cid) or f['generated'] or f['category'] not in categories:
            raise ValueError('整车原观察、审批或资金凭据跨店、跨原单或为生成草稿')
        return cid

    def event(row, parent, action, id_key, original_fields=(), physical=False):
        cid = local_case(parent, row['store_id'])
        matches = [e for e in event_by[cid] if e['action'] == 'vehicle_transport_' + action and e['detail'].get(id_key) == row['id']]
        if len(matches) != 1: raise ValueError('整车不可变事实缺少唯一对应原动作')
        source = matches[0]; detail = source['detail']
        if source['actor_id'] != row.get('actor_id', row.get('requested_by')): raise ValueError('整车原动作与实际经办人不一致')
        for field in original_fields:
            if detail.get(field) != row.get(field): raise ValueError('整车原动作与冻结事实字段不一致')
        if physical and (detail.get('confirmed') is not True or str(detail.get('vin', '')).upper() != parent['vin']):
            raise ValueError('实车实际事实缺少本人明确原VIN确认')
        return detail

    for ex in exs.values():
        parent = parents.get(ex['transfer_id']); original = moves.get(ex['original_id'])
        if not parent or not original or ex['origin_status'] not in rules.ACTIVE_ORIGINS:
            raise ValueError('整车差异原在途和原发出来源缺失')
        cost = parent['snapshot']['purchase_cost_cents']; car = cars.get(parent['source_vehicle_id'])
        if not car or car['store_id'] != parent['from_store_id'] or car['vin'].upper() != parent['vin'] or car['purchase_cost_cents'] != cost:
            raise ValueError('原VIN差异冻结成本与原资产不一致')
        if (original['transfer_id'], original['store_id'], original['vehicle_id'], original['quantity'], original['value_cents'], original['kind']) != (parent['id'], parent['from_store_id'], car['id'], -1, -cost, 'dispatch'):
            raise ValueError('整车原损失未追唯一原发出，或重复出库')
        proof(ex, parent)
        opened = [e for e in event_by[local_case(parent, ex['store_id'])] if e['action']=='vehicle_transport_open' and e['detail'].get('exception_id')==ex['id']]
        if len(opened)!=1 or opened[0]['actor_id']!=ex['requested_by'] or any(opened[0]['detail'].get(k)!=ex[k] for k in ('transfer_id','kind','evidence_id','reason')):
            raise ValueError('原整车差异申请与本人原动作不一致')
        losses = loss_by_ex[ex['id']]; found_receipts = found_by_ex[ex['id']]
        if len(losses)>1 or len(found_receipts)>1: raise ValueError('同一原VIN损失或找回不能重复确认')
        loss = losses[0] if losses else None; receipt = found_receipts[0] if found_receipts else None
        if ex['active_transfer_id'] is not None: active_by_parent[parent['id']].append(ex['id'])
        timeline = []
        priority = {'observation':0,'plan':1,'review':2,'withdraw':3,'dispose':4,'loss':5,'unavailable':6,'receipt':7}
        def add(kind, rows):
            for r in rows: timeline.append((r['created_at'],priority[kind],r['id'],kind,r))
        add('observation', by_ex.get('vehicle_transport_observations',{}).get(ex['id'],[]))
        all_plans = by_ex.get('vehicle_transport_plans',{}).get(ex['id'],[])
        add('plan',all_plans)
        for p in all_plans: add('review',reviews[p['id']]);add('withdraw',withdrawals[p['id']])
        add('dispose',by_ex.get('vehicle_transport_disposals',{}).get(ex['id'],[]))
        add('unavailable',by_ex.get('vehicle_transport_found_unavailable',{}).get(ex['id'],[]))
        add('loss',losses);add('receipt',found_receipts)
        state='investigating';current=None;observed={};seen=[];retired=set();reviewed={};posted=None;disposed=None;revision=0;last_unavailable=None
        for stamp,_,_,kind,r in sorted(timeline):
            if stamp<ex['created_at']: raise ValueError('整车差异事实早于原差异建立')
            if kind=='observation':
                found=r['kind']=='found_usable'
                if state!=('posted' if found else 'investigating'): raise ValueError('整车观察越过原调查或锁定方案状态')
                rules.validate_observation(parent,ex,r,original,loss=posted,timezone_name=zone)
                if found and last_unavailable and r['actual_at']<last_unavailable:raise ValueError('再次找到不能复用此前已失效的在场时间')
                proof(r,parent)
                payload=event(r,parent,'observe_found' if found else 'observe','observation_id',('evidence_id','reason'))
                if payload.get('confirmed') is not True or str(payload.get('vin','')).upper()!=r['vin'] or rules.timestamp(payload.get('actual_at'))!=rules.timestamp(r['actual_at']) or not found and payload.get('kind')!=r['kind']:
                    raise ValueError('原车观察与本人明确核对内容不一致')
                if found:seen.append(r)
                else:observed[r['store_id']]=r
            elif kind=='plan':
                found=r['kind']=='found_receive'
                if state!=('posted' if found else 'investigating') or r['revision']!=revision+1:
                    raise ValueError('整车差异方案版本或原办理顺序不一致')
                source=observations.get(r['source_observation_id']);destination=observations.get(r['destination_observation_id'])
                finding=observations.get(r['found_observation_id']) if found else None
                if observed.get(parent['from_store_id'])!=source or observed.get(parent['to_store_id'])!=destination:
                    raise ValueError('整车方案没有冻结提出时两店最新原观察')
                candidates=[x for x in seen if x['id'] not in retired]
                if found and (not candidates or candidates[-1]!=finding):raise ValueError('整车找回方案复用失效或过时的在场观察')
                rules.validate_plan(parent,ex,original,source,destination,r,finding,posted if found else None,timezone_name=zone)
                proof(r,parent,financial=r['kind']!='resume')
                action={'resume':'plan_resume','loss':'plan_loss','found_receive':'plan_found'}[r['kind']]
                fields=['reason','evidence_id']+(['source_bearer_cents','destination_bearer_cents','loss_method'] if r['kind']=='loss' else ['found_observation_id'] if found else [])
                event(r,parent,action,'plan_id',fields)
                state='review';current=r;reviewed={};revision+=1
            elif kind=='review':
                if state!='review' or r['plan_id']!=current['id'] or r['store_id'] in reviewed:
                    raise ValueError('整车复核不属于当前尚未完成的本版方案')
                facts=[observations[current['source_observation_id']],observations[current['destination_observation_id']]]
                if current['found_observation_id']:facts.append(observations[current['found_observation_id']])
                excluded=rules.independent_reviewers(ex,current,facts)|{x['actor_id'] for x in reviewed.values()}
                if r['actor_id'] in excluded:raise ValueError('整车两店复核不独立或由同一人兼任')
                proof(r,parent,financial=current['kind']!='resume')
                own=[e for e in event_by[local_case(parent,r['store_id'])] if e['action']=='vehicle_transport_'+r['decision'] and e['detail'].get('exception_id')==ex['id'] and e['detail'].get('plan_id')==r['plan_id']]
                if len(own)!=1 or own[0]['actor_id']!=r['actor_id'] or any(own[0]['detail'].get(k)!=r[k] for k in ('reason','evidence_id')):raise ValueError('整车复核与原动作不一致')
                reviewed[r['store_id']]=r
                if r['decision']=='reject':state='posted' if current['kind']=='found_receive' else 'investigating'
                elif r['decision']!='approve':raise ValueError('整车复核意见不受支持')
                elif len(reviewed)==2:state='resolved' if current['kind']=='resume' else 'approved'
            elif kind=='withdraw':
                if state!='review' or r['plan_id']!=current['id'] or r['actor_id']!=current['actor_id'] or r['store_id']!=current['store_id']:
                    raise ValueError('整车方案撤回不是本版原经办人或已越过生效状态')
                proof(r,parent,financial=current['kind']!='resume')
                state='posted' if current['kind']=='found_receive' else 'investigating'
            elif kind=='dispose':
                receiver=rules.parties(parent,ex)[1]
                if state!='approved' or current['kind']!='loss' or current['loss_method']!='destroyed' or disposed or r['plan_id']!=current['id'] or r['store_id']!=receiver or r['vin']!=parent['vin']:
                    raise ValueError('不可用原车处置缺少双方批准或不是原实车所在门店')
                proof(r,parent);disposed=r
                own=[e for e in event_by[local_case(parent,r['store_id'])] if e['action']=='vehicle_transport_dispose' and e['detail'].get('exception_id')==ex['id']]
                if len(own)!=1 or own[0]['actor_id']!=r['actor_id'] or own[0]['detail'].get('confirmed') is not True or str(own[0]['detail'].get('vin','')).upper()!=r['vin'] or any(own[0]['detail'].get(k)!=r[k] for k in ('evidence_id','reason')):
                    raise ValueError('原車实际处置缺少本人明确凭据确认')
            elif kind=='loss':
                if state!='approved' or current['kind']!='loss' or posted or current['loss_method']=='destroyed' and not disposed:
                    raise ValueError('原车损失越过双方批准或实际处置')
                expected=(parent['id'],ex['id'],ex['original_id'],current['id'],parent['from_store_id'],parent['from_case_id'],cost,current['source_bearer_cents'],current['destination_bearer_cents'],current['loss_method'])
                if tuple(r[k] for k in ('transfer_id','exception_id','original_id','plan_id','store_id','case_id','value_cents','source_bearer_cents','destination_bearer_cents','kind'))!=expected:
                    raise ValueError('原车损失数量价值或双店成本承担不守恒')
                proof(r,parent,True)
                payload=event(r,parent,'post_loss','loss_id',('evidence_id',))
                if payload.get('confirmed') is not True:raise ValueError('原车损失没有财务本人实际确认')
                state='posted';posted=r
            elif kind=='unavailable':
                if state!='approved' or current['kind']!='found_receive' or r['plan_id']!=current['id'] or r['observation_id']!=current['found_observation_id'] or r['store_id']!=current['receiving_store_id'] or r['vin']!=parent['vin'] or r['kind'] not in {'missing_again','not_usable'}:
                    raise ValueError('找回未能接收事实不属于本版原在场及指定接收门店')
                proof(r,parent);event(r,parent,'found_unavailable','unavailable_id',('kind','evidence_id','reason'),True)
                retired.add(r['observation_id']);last_unavailable=r['created_at'];state='posted'
            elif kind=='receipt':
                if state!='approved' or current['kind']!='found_receive' or not posted or posted['kind']!='missing':raise ValueError('原车找回入库缺少原失联及本版独立批准')
                expected=(parent['id'],ex['id'],posted['id'],current['id'],current['found_observation_id'],current['receiving_store_id'],cost)
                if tuple(r[k] for k in ('transfer_id','exception_id','loss_id','plan_id','observation_id','store_id','value_cents'))!=expected:raise ValueError('找回原VIN入库没有追同一原损失成本')
                local=proof(r,parent);new=cars.get(r['vehicle_id']);loc=locs.get(r['location_id']);warehouse=warehouses.get(loc['warehouse_id']) if loc else None
                if r['case_id']!=local or not new or (new['store_id'],new['vin'],new['inventory_generation'],new['purchase_cost_cents'])!=(r['store_id'],parent['vin'],car['inventory_generation']+1,cost) or parent['received_vehicle_id']!=new['id']:
                    raise ValueError('找回原车须在真实接收店建立唯一新代次并保留原成本')
                origin_links=[x for x in identities if x['local_kind']=='vehicle' and x['local_id']==car['id']]
                found_links=[x for x in identities if x['local_kind']=='vehicle' and x['local_id']==new['id']]
                if len(origin_links)!=1 or len(found_links)!=1 or found_links[0]['identity_id']!=origin_links[0]['identity_id'] or found_links[0]['store_id']!=r['store_id']:raise ValueError('找回库存代次未沿用同一原VIN身份')
                if not loc or not warehouse or (loc['store_id'],warehouse['store_id'])!=(r['store_id'],r['store_id']) or warehouse['warehouse_type'] not in {'vehicles','mixed'}:
                    raise ValueError('找回原车库位不属于实际接收门店')
                original_positions=[p for p in positions if p['vehicle_id']==new['id'] and p['kind']=='transfer_receive']
                if len(original_positions)!=1 or any(original_positions[0][k]!=v for k,v in {'store_id':r['store_id'],'case_id':r['case_id'],'location_id':r['location_id'],'quantity':1,'inventory_delta':0,'value_cents':cost,'evidence_id':r['evidence_id'],'actor_id':r['actor_id'],'business_date':r['business_date']}.items()):
                    raise ValueError('找回原车入库与实际库位原事实不一致')
                event(r,parent,'found_receive','receipt_id',('vehicle_id','location_id','evidence_id'),True)
                state='recovered'
        if state!=ex['status']:raise ValueError('整车差异当前状态与不可变原事实重放结果不一致')
        expected_active=None if state in {'resolved','recovered'} else parent['id']
        if ex['active_transfer_id']!=expected_active:raise ValueError('整车差异状态与原VIN独占占用不一致')
        if posted and parent['status']!=('recovered' if state=='recovered' else 'lost'):raise ValueError('原调拨未保留损失或实际找回状态')
        if not posted and state!='resolved' and parent['status']!=ex['origin_status']:raise ValueError('原车差异未解除却绕过普通交接')
        pair=data['vehicle_transport_loss_settlements']
        actual=[p for p in pair if p['exception_id']==ex['id']]
        wanted=[]
        if posted and posted['destination_bearer_cents']:
            amount=posted['destination_bearer_cents']
            wanted=[(parent['from_store_id'],parent['to_store_id'],amount),(parent['to_store_id'],parent['from_store_id'],-amount)]
        if sorted((r['store_id'],r['counterparty_store_id'],r['amount_cents']) for r in actual)!=sorted(wanted):raise ValueError('原车损失双方往来不配对')
        if posted and any((r['transfer_id'],r['loss_id'],r['business_date'])!=(parent['id'],posted['id'],posted['business_date']) for r in actual):raise ValueError('原车损失往来未追同一实际原核销')
        actual=[p for p in data['vehicle_transport_found_settlements'] if posted and p['loss_id']==posted['id']]
        wanted=[]
        if receipt:
            amount=rules.found_pair_amount(parent,posted,receipt['store_id'])
            if amount:wanted=[(parent['from_store_id'],parent['to_store_id'],amount),(parent['to_store_id'],parent['from_store_id'],-amount)]
        if sorted((r['store_id'],r['counterparty_store_id'],r['amount_cents']) for r in actual)!=sorted(wanted):raise ValueError('找回实际资产归属与原承担冲回的净往来不守恒')
        if receipt and any((r['receipt_id'],r['loss_id'],r['business_date'])!=(receipt['id'],posted['id'],receipt['business_date']) for r in actual):raise ValueError('原车找回往来未追同一原核销和本次真实入库')
    if any(len(ids)>1 for ids in active_by_parent.values()):raise ValueError('同一原VIN存在多个并行在办差异')
    # Orphans are rejected even where a database administrator removed FK checks.
    for name, entries in data.items():
        for row in entries:
            if 'exception_id' in row and row['exception_id'] not in exs:raise ValueError('整车差异事实缺少原差异')
            if name in {'vehicle_transport_reviews','vehicle_transport_withdrawals'} and row['plan_id'] not in plans:raise ValueError('整车审批或撤回缺少原方案')
    count=validate_claims(connection,data,exs,parents,loss_by_ex,found_by_ex,cases,files,event_by,proof,local_case)
    return {'verified_vehicle_transport_exceptions':len(exs),'verified_vehicle_transport_losses':len(data['vehicle_transport_losses']),
        'verified_vehicle_transport_found':len(data['vehicle_transport_found_receipts']),'verified_vehicle_transport_claims':count}


def validate_claims(connection,data,exs,parents,loss_by_ex,found_by_ex,cases,files,event_by,proof,local_case):
    claims=keyed(data['vehicle_transport_claims']);plans=keyed(data['vehicle_transport_claim_plans'])
    by_claim=group(plans.values(),'claim_id');payments=group(data['vehicle_transport_claim_payments'],'claim_id')
    reviews=group(data['vehicle_transport_claim_reviews'],'plan_id');withdrawals=group(data['vehicle_transport_claim_withdrawals'],'plan_id')
    cash=keyed(read_rows(connection,'cash_entries'));accounts=keyed(read_rows(connection,'flow_accounts'))
    suppliers=keyed(read_rows(connection,'master_suppliers'));insurers=keyed(read_rows(connection,'master_insurers'))
    known_cash=set();allpayments=keyed(data['vehicle_transport_claim_payments'])
    capacity_history=defaultdict(list)
    for claim in claims.values():
        ex=exs.get(claim['exception_id']);parent=parents.get(ex['transfer_id']) if ex else None
        losses=loss_by_ex.get(claim['exception_id'],[])
        if not parent or len(losses)!=1 or claim['store_id'] not in {parent['from_store_id'],parent['to_store_id']}:raise ValueError('原车追偿缺少原损失或越店')
        loss=losses[0];cid=local_case(parent,claim['store_id'])
        model=suppliers if claim['counterparty_kind']=='carrier' else insurers if claim['counterparty_kind']=='insurer' else {}
        key=claim['supplier_id'] if claim['counterparty_kind']=='carrier' else claim['insurer_id']
        party=model.get(key);snapshot=claim['counterparty_snapshot']
        if not party or party['store_id']!=claim['store_id'] or snapshot.get('id')!=key or not snapshot.get('name') or not snapshot.get('code') or not isinstance(snapshot.get('version'),int):
            raise ValueError('原车追偿没有明确本店原承运或保险往来方')
        if claim['created_at']<loss['created_at']:raise ValueError('原车未确认损失即建立追偿')
        timeline=[];rank={'plan':0,'review':1,'withdraw':2,'payment':3}
        for plan in by_claim[claim['id']]:
            timeline.append((plan['created_at'],rank['plan'],plan['id'],'plan',plan))
            for review in reviews[plan['id']]:timeline.append((review['created_at'],rank['review'],review['id'],'review',review))
            for withdrawal in withdrawals[plan['id']]:timeline.append((withdrawal['created_at'],rank['withdraw'],withdrawal['id'],'withdraw',withdrawal))
        for payment in payments[claim['id']]:timeline.append((payment['created_at'],rank['payment'],payment['id'],'payment',payment))
        pending=None;current=None;revision=0;paid=0;seen={};refunds=defaultdict(int)
        found=found_by_ex.get(ex['id'],[]);found_time=found[0]['created_at'] if found else None
        for stamp,_,_,kind,row in sorted(timeline):
            if row['store_id']!=claim['store_id'] or stamp<claim['created_at']:raise ValueError('原车追偿原单门店或来源时间不一致')
            proof(row,parent,True)
            table={'plan':'vehicle_transport_claim_plans','review':'vehicle_transport_claim_reviews','withdraw':'vehicle_transport_claim_withdrawals','payment':'vehicle_transport_claim_payments'}[kind]
            action=('recovery_create' if row.get('revision')==1 else 'recovery_plan') if kind=='plan' else ('recovery_'+row['decision']) if kind=='review' else 'recovery_cancel' if kind=='withdraw' else ('recovery_receive' if row['direction']=='in' else 'recovery_refund')
            events=[e for e in event_by[cid] if e['action']=='vehicle_transport_'+action and e['detail'].get('fact_table')==table and e['detail'].get('fact_id')==row['id']]
            original_fields=('id','store_id','exception_id','counterparty_kind','supplier_id','insurer_id','counterparty_snapshot','requested_by','created_at')
            if len(events)!=1 or events[0]['actor_id']!=row['actor_id'] or events[0]['detail'].get('fact')!=row or events[0]['detail'].get('claim_origin')!={k:claim[k] for k in original_fields}:raise ValueError('原车追偿事实与本店本人原动作及冻结往来方不一致')
            if kind=='payment' and events[0]['detail'].get('confirmed') is not True:raise ValueError('原车追偿收退款缺少本人明确实际确认')
            if kind=='plan':
                if pending or row['revision']!=revision+1 or type(row['target_cents']) is not int or row['target_cents']<0:raise ValueError('原车追偿目标版本或金额不一致')
                if found_time and stamp>=found_time and row['target_cents']!=0:raise ValueError('原车找回后不能新增正的损失追偿目标')
                pending=row;revision+=1
            elif kind=='review':
                if not pending or row['plan_id']!=pending['id'] or row['actor_id']==pending['actor_id']:raise ValueError('原车追偿目标未独立复核或本版不在办')
                if row['decision']=='approve':
                    if found_time and stamp>=found_time and pending['target_cents']!=0:raise ValueError('找回原资产后仍批准新收损失追偿')
                    current=pending
                elif row['decision']!='reject':raise ValueError('原车追偿复核意见不受支持')
                pending=None
            elif kind=='withdraw':
                if not pending or row['plan_id']!=pending['id']:raise ValueError('原车追偿撤回越过原未生效版本')
                pending=None
            elif kind=='payment':
                if pending or not current or row['plan_id']!=current['id'] or row['amount_cents']<=0:raise ValueError('原车追偿收退款缺少当前已批准目标')
                incoming=row['direction']=='in';amount=row['amount_cents']
                if incoming:
                    if row['original_id'] is not None or amount>max(0,current['target_cents']-paid) or found_time and stamp>=found_time:raise ValueError('原车实际追偿超过原批准应收或找回后重复收款')
                elif row['direction']=='out':
                    original=seen.get(row['original_id'])
                    if not original or original['direction']!='in' or amount>max(0,paid-current['target_cents']) or amount>original['amount_cents']-refunds[original['id']] or row['account_id']!=original['account_id'] or row['business_date']<original['business_date']:
                        raise ValueError('原车退款未回到同一原款或超过实际已收及原款应退')
                    refunds[original['id']]+=amount
                else:raise ValueError('原车追偿现金方向不受支持')
                account=accounts.get(row['account_id']);fact=cash.get(row['cash_id'])
                category='workflow_vehicle_loss_recovery' if incoming else 'workflow_vehicle_loss_return'
                if not account or account['store_id']!=claim['store_id'] or not fact or (fact['store_id'],fact['direction'],fact['amount_cents'],fact['account'],fact['category'],fact['voucher_no'],fact['business_date'],fact['approval_state'])!=(claim['store_id'],row['direction'],amount,account['name'],category,row['reference'],row['business_date'],'approved'):
                    raise ValueError('原车收退款关联与唯一真实现金不一致')
                if row['cash_id'] in known_cash:raise ValueError('原车追偿现金被重复关联')
                known_cash.add(row['cash_id']);paid+=amount if incoming else -amount;seen[row['id']]=row
            capacity_history[(ex['id'],claim['store_id'])].append((stamp,claim['id'],kind,
                current['target_cents'] if current else 0,paid,pending['target_cents'] if pending else 0))
        if paid<0:raise ValueError('原车追偿退款超过原实际到账')
    # Replay joint reservations, including reduced-but-unreturned original cash.
    # An unapproved second proposal consumes capacity too, as in live commands.
    for (eid,sid),timeline in capacity_history.items():
        loss=loss_by_ex[eid][0];parent=parents[exs[eid]['transfer_id']]
        cap=loss['source_bearer_cents'] if sid==parent['from_store_id'] else loss['destination_bearer_cents']
        found=found_by_ex.get(eid,[]);found_time=found[0]['created_at'] if found else None
        positions={}
        for stamp,claimid,kind,target,paid,pending in sorted(timeline):
            positions[claimid]=max(target,paid,pending)
            if not found_time or stamp<found_time:
                if sum(positions.values())>cap:raise ValueError('原车追偿批准、未决占用或未退原款合计超过本店原损失承担')
            # Found receipts may precede actual refunds; old cash is retained,
            # not treated as spendable capacity. Target transitions were checked above.
    for name in ('vehicle_transport_claim_reviews','vehicle_transport_claim_withdrawals'):
        if any(r['plan_id'] not in plans for r in data[name]):raise ValueError('原车追偿审批缺少原版本')
    if any(p['claim_id'] not in claims for p in plans.values()) or any(p['claim_id'] not in claims for p in allpayments.values()):raise ValueError('原车追偿来源缺少原条目')
    expected={c['id'] for c in cash.values() if c['category'] in {'workflow_vehicle_loss_recovery','workflow_vehicle_loss_return'}}
    if known_cash!=expected:raise ValueError('原车追偿现金缺少唯一原条目关联')
    return len(claims)


def frozen_vehicle_movement_kinds(connection, transfer_id):
    """Called only after the complete transport validator by the original custody check."""
    row=connection.execute('SELECT e.origin_status FROM vehicle_transport_losses l JOIN vehicle_transport_exceptions e ON e.id=l.exception_id WHERE l.transfer_id=?',(transfer_id,)).fetchone()
    if not row:raise ValueError('原车损失或找回状态缺少原损失来源')
    return {'transit':{'dispatch'},'rejected':{'dispatch','reject'},'return_transit':{'dispatch','reject','return_ship'}}[row[0]]
