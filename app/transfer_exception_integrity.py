"""Read-only offline checks for transport v3 and original external recovery.

No mutable ORM metadata is imported. Historical databases without these tables
retain their previous validator and do not receive inferred loss records.
"""
from collections import defaultdict
from datetime import datetime
import json
from .transfer_exception_math import bucket_position


def validate_transfer_exceptions_sqlite(connection):
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'transfer_exceptions' not in tables:return {'transport_exceptions':0,'transport_losses':0,'transport_recoveries':0}
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);columns=[c[0] for c in cursor.description]
        return [dict(zip(columns,r)) for r in cursor.fetchall()]
    def indexed(name):return {r['id']:r for r in rows(name)}
    def check(condition,message):
        if not condition:raise ValueError('调拨运输差异：'+message)
    def at(value):return datetime.fromisoformat(value)
    def collect(records,key):
        result=defaultdict(list)
        for r in records.values() if isinstance(records,dict) else records:result[r[key]].append(r)
        return result
    parents=indexed('material_transfers');cases=indexed('flow_cases');moves=indexed('material_transfer_movements');lines=indexed('material_transfer_lines');files=indexed('flow_files')
    exceptions=indexed('transfer_exceptions');observations=indexed('transfer_exception_observations');plans=indexed('transfer_exception_plans')
    reviews=rows('transfer_exception_reviews');disposals=rows('transfer_exception_disposals');losses=rows('transfer_loss_postings')
    settlements=rows('transfer_loss_settlements');cancels=rows('transfer_exception_cancellations')
    check(all(x['exception_id'] in exceptions for x in losses),'损失缺少原差异记录')
    check(all(x['posting_id'] in {p['id'] for p in losses} for x in settlements),'损失承担往来缺少原过账')
    check(all(o['exception_id'] in exceptions for o in observations.values()) and all(p['exception_id'] in exceptions for p in plans.values()),'观察或方案缺少原差异')
    check(all(r['plan_id'] in plans for r in reviews),'复核缺少原方案')
    obs_by=collect(observations,'exception_id');plan_by=collect(plans,'exception_id');review_by=collect(reviews,'plan_id');disposal_by=collect(disposals,'exception_id')
    loss_by=collect(losses,'exception_id');cancel_by=collect(cancels,'exception_id');settle_by=collect(settlements,'posting_id')
    active=set();loss_by_origin=defaultdict(list);final_plans={}
    def proof(file_id,store,case,financial=False):
        f=files.get(file_id)
        allowed={'receipt','procurement_contract'} if financial else {'evidence','inspection','authorization'}
        check(f and f['store_id']==store and f['case_id']==case and not f['generated'] and f['category'] in allowed,'实际凭据门店、原单或用途不符')
    for e in exceptions.values():
        parent=parents.get(e['transfer_id']);origin=moves.get(e['original_id'])
        check(parent and origin and origin['transfer_id']==parent['id'] and origin['kind'] in {'dispatch','reject','return_ship'},'原始实物批次不属于调拨')
        parties=(parent['from_store_id'],parent['to_store_id']);case_ids={parties[0]:parent['from_case_id'],parties[1]:parent['to_case_id']}
        check(all(cases[cid]['store_id']==sid and cases[cid]['kind']=='material_transfer' and cases[cid]['flow_version']==3 for sid,cid in case_ids.items()),'只允许明确新建第三版双方调拨')
        check(e['request_store_id'] in parties and e['quantity_milli']>0 and 0<=e['value_cents']<=origin['value_cents'],'差异原量或原成本无效')
        check(e['stage']=={'dispatch':'outbound','reject':'rejected','return_ship':'returning'}[origin['kind']],'实物批次与运输阶段不符')
        check(e['finding'] in {'missing','damaged'} and not(e['finding']=='damaged' and e['stage']=='outbound'),'到达坏件必须先真实拒收')
        terminal=e['status'] in {'posted','cancelled'}
        check((terminal and e['active_transfer_id'] is None) or (not terminal and e['active_transfer_id']==parent['id']),'差异调查锁与状态不符')
        if not terminal:
            check(parent['id'] not in active,'同一调拨存在多个未结差异');active.add(parent['id'])
        for o in obs_by[e['id']]:
            check(o['store_id'] in parties and o['quantity_milli']==e['quantity_milli'],'双方观察数量或门店不符')
            dispatch_side=parties[1] if e['stage']=='returning' else parties[0]
            expected=('return_dispatch_verified' if e['stage']=='returning' else 'dispatch_verified') if o['store_id']==dispatch_side else 'held_damaged' if e['finding']=='damaged' else 'missing'
            check(o['observation']==expected,'观察人只能证明本方发运或收到事实');proof(o['evidence_id'],o['store_id'],case_ids[o['store_id']])
        own_plans=sorted(plan_by[e['id']],key=lambda p:p['revision'])
        check([p['revision'] for p in own_plans]==list(range(1,len(own_plans)+1)),'承担方案版本不连续')
        for p in own_plans:
            a=observations.get(p['source_observation_id']);b=observations.get(p['destination_observation_id'])
            check(a and b and a['exception_id']==b['exception_id']==e['id'] and a['store_id']==parties[0] and b['store_id']==parties[1] and a['actor_id']!=b['actor_id'],'承担方案没有两方独立实际观察')
            check(at(a['created_at'])<=at(p['created_at']) and at(b['created_at'])<=at(p['created_at']),'不得引用方案后才产生的观察')
            check(p['source_bearer_cents']>=0 and p['destination_bearer_cents']>=0 and p['source_bearer_cents']+p['destination_bearer_cents']==e['value_cents'],'承担合计不等于原批损失成本')
            proof(p['evidence_id'],parties[0],case_ids[parties[0]],True)
            rv=review_by[p['id']]
            check(len({r['store_id'] for r in rv})==len(rv) and len({r['actor_id'] for r in rv})==len(rv),'两店复核不能重复或同人')
            for r in rv:
                check(r['store_id'] in parties and r['actor_id'] not in {e['requested_by'],p['actor_id'],a['actor_id'],b['actor_id']} and r['decision'] in {'approve','reject'},'复核人与申请、观察或方案经办人不独立')
                check(at(r['created_at'])>=at(p['created_at']),'复核早于本方案');proof(r['evidence_id'],r['store_id'],case_ids[r['store_id']],True)
        latest=own_plans[-1] if own_plans else None
        if e['status'] in {'approved','disposed','posted'}:
            check(latest and {r['store_id'] for r in review_by[latest['id']] if r['decision']=='approve'}==set(parties),'缺少当前方案两位主管的批准')
            final_plans[e['id']]=latest
        if e['status']=='review':check(latest and len(review_by[latest['id']])<2 and all(r['decision']=='approve' for r in review_by[latest['id']]),'当前复核状态不符')
        for d in disposal_by[e['id']]:
            custodian=parties[0] if e['stage']=='returning' else parties[1]
            check(e['finding']=='damaged' and d['store_id']==custodian and latest and d['plan_id']==latest['id'] and d['quantity_milli']==e['quantity_milli'],'实际处置不是原在手坏件或由另一方代办')
            proof(d['evidence_id'],custodian,case_ids[custodian])
        check(len(disposal_by[e['id']])<=1,'同一损失坏件重复处置')
        if e['status'] in {'disposed','posted'} and e['finding']=='damaged':check(len(disposal_by[e['id']])==1,'坏件损失缺少实际处置')
        elif e['status']!='posted':check(not disposal_by[e['id']],'未处置状态含真实处置')
        check((e['status']=='posted')==(len(loss_by[e['id']])==1),'损失确认状态与唯一原过账不符')
        check(len(loss_by[e['id']])<=1,'重复损失过账')
        for loss in loss_by[e['id']]:
            check(loss['store_id']==parties[0] and loss['transfer_id']==parent['id'] and loss['line_id']==origin['line_id'] and loss['original_id']==origin['id'] and loss['plan_id']==latest['id'],'损失不归原调出店或原批次')
            check(all(loss[k]==e[k] for k in ('quantity_milli','value_cents')) and all(loss[k]==latest[k] for k in ('source_bearer_cents','destination_bearer_cents')),'损失量价与原批准方案不符')
            proof(loss['evidence_id'],parties[0],case_ids[parties[0]],True);loss_by_origin[origin['id']].append((loss['quantity_milli'],loss['value_cents']))
            expected=[(parties[0],parties[1],latest['destination_bearer_cents']),(parties[1],parties[0],-latest['destination_bearer_cents'])] if latest['destination_bearer_cents'] else []
            actual=[(x['store_id'],x['counterparty_store_id'],x['amount_cents']) for x in settle_by[loss['id']]]
            check(sorted(actual)==sorted(expected) and all(x['transfer_id']==parent['id'] and x['exception_id']==e['id'] and x['business_date']==loss['business_date'] for x in settle_by[loss['id']]),'损失承担往来不成对或金额不符')
        check((e['status']=='cancelled')==(len(cancel_by[e['id']])==1) and len(cancel_by[e['id']])<=1,'未生效差异取消记录不符')
        for c in cancel_by[e['id']]:
            check(c['store_id'] in parties and not disposal_by[e['id']] and not loss_by[e['id']],'已有真实处置或损失不能取消')
            proof(c['evidence_id'],c['store_id'],case_ids[c['store_id']])
    # Check each nested batch separately. A rejection moves into its own bucket;
    # returning/lost goods must not be charged a second time to dispatch.
    relevant={e['transfer_id'] for e in exceptions.values()}
    for origin in moves.values():
        if origin['transfer_id'] not in relevant or origin['kind'] not in {'dispatch','reject','return_ship'}:continue
        kinds={'dispatch':{'accept','reject'},'reject':{'return_ship'},'return_ship':{'return_receive'}}[origin['kind']]
        completed=[(m['quantity_milli'],m['value_cents']) for m in moves.values() if m['original_id']==origin['id'] and m['kind'] in kinds]+loss_by_origin[origin['id']]
        try:bucket_position(origin['quantity_milli'],origin['value_cents'],completed)
        except ValueError as exc:raise ValueError('调拨运输差异：'+str(exc)) from exc
    for parent_id in relevant:
        parent=parents[parent_id]
        for line in (l for l in lines.values() if l['transfer_id']==parent_id):
            origin=next(m for m in moves.values() if m['line_id']==line['id'] and m['kind']=='dispatch')
            final=[(m['quantity_milli'],m['value_cents']) for m in moves.values() if m['line_id']==line['id'] and m['kind'] in {'accept','return_receive'}]
            final += [(x['quantity_milli'],x['value_cents']) for x in losses if x['line_id']==line['id']]
            q=sum(a for a,b in final);v=sum(b for a,b in final)
            check(q<=origin['quantity_milli'] and v<=origin['value_cents'],'已验收、退回与损失超过原发出')
            if parent['status']=='completed':check(q==origin['quantity_milli'] and v==origin['value_cents'],'已结清实物的数量与原价值不守恒')
    # External recoveries remain local facts; target revisions never create cash.
    claims=indexed('transfer_recovery_claims');rp=indexed('transfer_recovery_plans');rr=rows('transfer_recovery_reviews');rc=rows('transfer_recovery_cancellations');payments=indexed('transfer_recovery_payments')
    rp_by=collect(rp,'claim_id');rr_by=collect(rr,'plan_id');rc_by=collect(rc,'plan_id');pay_by=collect(payments,'claim_id')
    cash=indexed('cash_entries');accounts=indexed('flow_accounts');occupied=defaultdict(int);used_cash=set()
    for claim in claims.values():
        e=exceptions.get(claim['exception_id']);check(e and e['status']=='posted','追偿没有原损失确认')
        parent=parents[e['transfer_id']];sid=claim['store_id'];check(sid in {parent['from_store_id'],parent['to_store_id']},'追偿越过调拨双方')
        cid=parent['from_case_id'] if sid==parent['from_store_id'] else parent['to_case_id'];snapshot=json.loads(claim['counterparty_snapshot'])
        party_id=claim['supplier_id'] if claim['counterparty_kind']=='carrier' else claim['insurer_id']
        check(claim['counterparty_kind'] in {'carrier','insurer'} and snapshot['id']==party_id and snapshot['name'] and snapshot['version']>0,'追偿往来方冻结事实不符')
        parties_table='master_suppliers' if claim['counterparty_kind']=='carrier' else 'master_insurers'
        saved_party=connection.execute('SELECT store_id FROM '+parties_table+' WHERE id=?',(party_id,)).fetchone()
        check(saved_party and saved_party[0]==sid,'追偿往来单位不属于本店')
        own=sorted(rp_by[claim['id']],key=lambda p:p['revision']);approved=[];pending=[]
        check(own and [p['revision'] for p in own]==list(range(1,len(own)+1)),'追偿目标版本缺失或不连续')
        for p in own:
            check(p['store_id']==sid and p['target_cents']>=0,'追偿目标门店或金额无效');proof(p['evidence_id'],sid,cid,True)
            check(len(rr_by[p['id']])+len(rc_by[p['id']])<=1,'追偿目标重复复核或批准后取消')
            for r in rr_by[p['id']]:
                check(r['store_id']==sid and r['actor_id']!=p['actor_id'] and r['decision'] in {'approve','reject'} and at(r['created_at'])>=at(p['created_at']),'追偿须本店独立主管复核')
                proof(r['evidence_id'],sid,cid,True)
                if r['decision']=='approve':approved.append((p,r))
            for cancel in rc_by[p['id']]:
                check(cancel['store_id']==sid,'追偿版本取消越店');proof(cancel['evidence_id'],sid,cid,True)
            if not rr_by[p['id']] and not rc_by[p['id']]:pending.append(p)
        check(len(pending)<=1,'追偿目标有多个在办版本')
        current=approved[-1][0]['target_cents'] if approved else 0;net=0;returned=defaultdict(int)
        for pay in sorted(pay_by[claim['id']],key=lambda p:p['id']):
            active=[(p,r) for p,r in approved if at(r['created_at'])<=at(pay['created_at'])]
            check(active and pay['plan_id']==active[-1][0]['id'],'追偿现金未按当时已批准当前目标')
            for candidate in own:
                if at(candidate['created_at'])>at(pay['created_at']):continue
                outcomes=rr_by[candidate['id']]+rc_by[candidate['id']]
                check(outcomes and at(outcomes[0]['created_at'])<=at(pay['created_at']),'追偿现金发生在目标在审期间')
            target=active[-1][0]['target_cents'];p=rp[pay['plan_id']];c=cash.get(pay['cash_id']);account=accounts.get(pay['account_id'])
            check(pay['store_id']==sid and pay['amount_cents']>0 and c and account and account['store_id']==sid,'追偿现金或账户越店')
            expected='workflow_transfer_recovery' if pay['direction']=='in' else 'workflow_transfer_rec_return'
            check(pay['cash_id'] not in used_cash and c['store_id']==sid and c['approval_state']=='approved' and c['direction']==pay['direction'] and c['category']==expected and c['amount_cents']==pay['amount_cents'],'追偿现金被重用、撤销或金额不符')
            check(c['business_date']==pay['business_date'] and c['account']==account['name'] and c['voucher_no']==pay['reference'] and c['counterparty']==snapshot['name'],'追偿现金日期、流水或原往来方不符')
            check(not connection.execute('SELECT id FROM flow_payment_links WHERE cash_id=?',(c['id'],)).fetchone(),'追偿现金不能再作为客户原单收款')
            used_cash.add(pay['cash_id']);proof(pay['evidence_id'],sid,cid,True)
            if pay['direction']=='in':
                check(pay['original_id'] is None and pay['amount_cents']<=target-net,'实际追偿超过当时应收目标');net+=pay['amount_cents']
            else:
                original=payments.get(pay['original_id']);check(original and original['claim_id']==claim['id'] and original['direction']=='in' and original['id']<pay['id'] and original['account_id']==pay['account_id'],'追偿退款不是本店原实收原账户')
                returned[original['id']]+=pay['amount_cents']
                check(returned[original['id']]<=original['amount_cents'] and pay['amount_cents']<=net-target and pay['business_date']>=original['business_date'],'原追偿款超退或缺少减少后的目标');net-=pay['amount_cents']
        occupied[(e['id'],sid)]+=max(current,net,pending[0]['target_cents'] if pending else 0)
    found=rows('transfer_goods_recoveries') if 'transfer_goods_recoveries' in tables else []
    found_posted=rows('transfer_goods_postings') if 'transfer_goods_postings' in tables else []
    for (eid,sid),amount in occupied.items():
        parent=parents[exceptions[eid]['transfer_id']];p=final_plans[eid]
        cap=p['source_bearer_cents'] if sid==parent['from_store_id'] else p['destination_bearer_cents']
        check(amount<=cap,'本店追偿目标及未退现金超过原损失承担')
        if 'transfer_goods_postings' in tables:
            loss_ids={x['id'] for x in losses if x['exception_id']==eid}
            reverse_field='source_reverse_cents' if sid==parent['from_store_id'] else 'destination_reverse_cents'
            remaining=cap-sum(x[reverse_field] for x in found_posted if x['loss_id'] in loss_ids)
            check(remaining>=0,'找回后原承担为负数')
            # Existing actual compensation may exceed the newly restored asset
            # burden until explicitly confirmed reductions and refunds finish.
            # The found-goods validator verifies this narrow active fact chain;
            # no ordinary new target or collection may use that temporary gap.
            resolving=any(x['exception_id']==eid and x['active_transfer_id']==parent['id'] and x['status']=='financial'
                          and any(y['recovery_id']==x['id'] and y['loss_id'] in loss_ids for y in found_posted) for x in found)
            check(resolving or amount<=remaining,'找回结清后的追偿目标及未退现金超过剩余承担')
    check({c['id'] for c in cash.values() if c['category'] in {'workflow_transfer_recovery','workflow_transfer_rec_return'}}==used_cash,'存在未关联原损失追偿的现金')
    return {'transport_exceptions':len(exceptions),'transport_losses':len(losses),'transport_recoveries':len(claims)}
