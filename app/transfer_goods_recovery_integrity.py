"""Read-only restore checks. Never import mutable model metadata."""
from collections import defaultdict
from datetime import datetime
from .transfer_goods_recovery_math import allocation


def validate_transfer_goods_recovery_sqlite(connection):
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'transfer_goods_recoveries' not in tables:return {'found_goods':0,'found_goods_postings':0}
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);keys=[c[0] for c in cursor.description]
        return [dict(zip(keys,r)) for r in cursor.fetchall()]
    def indexed(name):return {r['id']:r for r in rows(name)}
    def grouped(data,key):
        result=defaultdict(list)
        for r in data.values() if isinstance(data,dict) else data:result[r[key]].append(r)
        return result
    def check(value,message):
        if not value:raise ValueError('找回原物资：'+message)
    def at(value):return datetime.fromisoformat(value)
    headers=indexed('transfer_goods_recoveries');facts=indexed('transfer_goods_facts');plans=indexed('transfer_goods_plans')
    reviews=rows('transfer_goods_reviews');postings=indexed('transfer_goods_postings');settlements=rows('transfer_goods_settlements')
    terms=indexed('transfer_goods_terms');refunds=rows('transfer_goods_refunds')
    losses=indexed('transfer_loss_postings');parents=indexed('material_transfers');cases=indexed('flow_cases');files=indexed('flow_files')
    stock=indexed('flow_stock_moves');lines=indexed('material_transfer_lines');moves=indexed('material_transfer_movements');old_settlements=indexed('transfer_loss_settlements')
    claims=indexed('transfer_recovery_claims');oldplans=indexed('transfer_recovery_plans');oldreviews=rows('transfer_recovery_reviews');oldcancels=rows('transfer_recovery_cancellations');payments=indexed('transfer_recovery_payments')
    fb=grouped(facts,'recovery_id');pb=grouped(plans,'recovery_id');rb=grouped(reviews,'plan_id');posted=grouped(postings,'recovery_id');sb=grouped(settlements,'posting_id')
    check(all(f['recovery_id'] in headers for f in facts.values()) and all(p['recovery_id'] in headers for p in plans.values()),'观察或方案没有原找回记录')
    check(all(r['plan_id'] in plans for r in reviews) and all(p['recovery_id'] in headers for p in postings.values()),'批准或过账缺少原找回方案')
    check(all(s['posting_id'] in postings for s in settlements),'反向承担缺少原恢复过账')
    active=set()
    def proof(fid,sid,cid,financial=False):
        f=files.get(fid);allowed={'receipt','procurement_contract'} if financial else {'evidence','inspection','authorization'}
        check(f and f['store_id']==sid and f['case_id']==cid and not f['generated'] and f['category'] in allowed,'实际凭据原单、门店或类别不符')
    for h in headers.values():
        loss=losses.get(h['loss_id']);parent=parents.get(h['transfer_id'])
        check(loss and parent and loss['transfer_id']==parent['id'] and loss['exception_id']==h['exception_id'],'找回不是该调拨原损失')
        parties=(parent['from_store_id'],parent['to_store_id']);caseids={parties[0]:parent['from_case_id'],parties[1]:parent['to_case_id']}
        check(all(cases[c]['store_id']==sid and cases[c]['flow_version']==3 and cases[c]['kind']=='material_transfer' for sid,c in caseids.items()),'双方原流程不是第三版物资调拨')
        check(h['found_store_id'] in parties and 0<h['quantity_milli']<=loss['quantity_milli'],'找到数量或保管门店无效')
        terminal=h['status'] in {'closed','cancelled','unlocated'}
        check((terminal and h['active_transfer_id'] is None) or (not terminal and h['active_transfer_id']==parent['id']),'暂停锁与状态不符')
        if not terminal:check(parent['id'] not in active,'原调拨有多个找到物资在办');active.add(parent['id'])
        own=sorted(fb[h['id']],key=lambda f:f['id']);found=[f for f in own if f['kind']=='found'];matched=[f for f in own if f['kind']=='match']
        shipped=[f for f in own if f['kind']=='ship'];received=[f for f in own if f['kind']=='receive'];disposed=[f for f in own if f['kind']=='dispose'];cancelled=[f for f in own if f['kind']=='cancel']
        check(len(found)==1 and (found[0]['store_id'],found[0]['actor_id'])==(h['found_store_id'],h['requested_by']),'实际找到原件缺失或经办不符')
        check(len(matched)<=1 and (not matched or matched[0]['store_id']!=h['found_store_id'] and matched[0]['actor_id']!=h['requested_by']),'双方本人核对不独立')
        check(len(shipped)<=1 and len(received)<=1 and len(disposed)<=1 and len(cancelled)<=1,'实际发回、复验入场、处置或撤回重复')
        for f in own:
            check(f['store_id'] in parties and f['quantity_milli']==h['quantity_milli'],'实物观察越店或数量不符');proof(f['evidence_id'],f['store_id'],caseids[f['store_id']])
            check((f['kind'] in {'inspect','receive'} and f['passed'] in (0,1)) or (f['kind'] not in {'inspect','receive'} and f['passed'] is None),'复验事实不明确')
        if shipped:
            ship=shipped[0];prior=[f for f in own if f['kind']=='inspect' and f['id']<ship['id']]
            check(h['found_store_id']==parties[1] and ship['store_id']==parties[1] and matched and prior and prior[-1]['passed']==1,'实际发回缺少本店找到、复验及另一方关联核对')
        if received:check(shipped and received[0]['store_id']==parties[0] and received[0]['id']>shipped[0]['id'],'原店接收缺少对方实际退运')
        if h['status']=='transit':check(shipped and not received,'退运在途与实际接收不符')
        check((h['status']=='cancelled')==bool(cancelled),'撤回状态没有对应不可变原件')
        if cancelled:check(not shipped and not received and not disposed and not posted[h['id']],'实际退运、接收、处置、恢复后不能撤回')
        ownplans=sorted(pb[h['id']],key=lambda p:p['revision']);check([p['revision'] for p in ownplans]==list(range(1,len(ownplans)+1)),'找回方案版本不连续')
        for plan in ownplans:
            quality=facts.get(plan['inspection_id']);match=facts.get(plan['match_id'])
            check(quality and match and quality['recovery_id']==match['recovery_id']==h['id'] and match['kind']=='match' and quality['kind'] in {'inspect','receive'},'方案引用其他找回或缺少实际复验')
            check(at(quality['created_at'])<=at(plan['created_at']) and at(match['created_at'])<=at(plan['created_at']),'方案早于实际事实')
            check((plan['restored_quantity_milli']==h['quantity_milli'] and quality['passed']==1 and quality['store_id']==parties[0]) or (plan['restored_quantity_milli']==0 and quality['passed']==0),'未回原店合格实物不能恢复库存')
            before=[p for p in postings.values() if p['loss_id']==loss['id'] and at(p['created_at'])<=at(plan['created_at'])]
            expected=allocation(loss['quantity_milli'],loss['value_cents'],loss['destination_bearer_cents'],
                sum(p['found_quantity_milli'] for p in before),sum(p['restored_quantity_milli'] for p in before),
                sum(p['value_cents'] for p in before),sum(p['destination_reverse_cents'] for p in before),h['quantity_milli'],bool(quality['passed']))
            check(all(plan[k]==v for k,v in expected.items() if k!='found_quantity_milli'),'原恢复方案累计量价不符')
            proof(plan['evidence_id'],parties[0],caseids[parties[0]],True)
            blocked={f['actor_id'] for f in own if at(f['created_at'])<=at(plan['created_at'])}|{plan['actor_id'],h['requested_by']}
            check(len({r['actor_id'] for r in rb[plan['id']]})==len(rb[plan['id']]),'双方主管不是不同人员')
            for review in rb[plan['id']]:
                check(review['store_id'] in parties and review['actor_id'] not in blocked and at(review['created_at'])>=at(plan['created_at']),'主管复核与本次事实不独立')
                proof(review['evidence_id'],review['store_id'],caseids[review['store_id']],True)
        latest=ownplans[-1] if ownplans else None
        if h['status'] in {'approved','financial','closed'}:
            check(latest and {r['store_id'] for r in rb[latest['id']] if r['decision']=='approve'}==set(parties),'没有当前方案双方独立批准')
        if disposed:
            quality=facts.get(latest['inspection_id']) if latest else None
            check(quality and quality['passed']==0 and disposed[0]['store_id']==quality['store_id'],'坏件不是实际保管店处置')
            check(all(at(r['created_at'])<=at(disposed[0]['created_at']) for r in rb[latest['id']]) and len(rb[latest['id']])==2,'实际处置早于双方批准')
        check((h['status'] in {'financial','closed'})==(len(posted[h['id']])==1),'实物处理状态与原过账不符')
        for p in posted[h['id']]:
            check(p['store_id']==parties[0] and p['loss_id']==loss['id'] and p['plan_id']==latest['id'],'恢复不属于原调出店或当前方案')
            check(p['found_quantity_milli']==h['quantity_milli'] and all(p[k]==latest[k] for k in ('restored_quantity_milli','value_cents','source_reverse_cents','destination_reverse_cents')),'实际恢复数量成本与批准不符')
            proof(p['evidence_id'],parties[0],caseids[parties[0]],not bool(p['restored_quantity_milli']))
            if p['restored_quantity_milli']:
                st=stock.get(p['stock_move_id']);line=lines[loss['line_id']];dispatch=next(m for m in moves.values() if m['line_id']==line['id'] and m['kind']=='dispatch')
                check(st and (st['store_id'],st['case_id'],st['item_id'],st['quantity_milli'],st['value_cents'],st['purpose'],st['original_id'])==(parties[0],caseids[parties[0]],line['source_item_id'],p['restored_quantity_milli'],p['value_cents'],'transfer_found',dispatch['stock_move_id']),'实际库存恢复不是原物资原成本')
            else:check(disposed and p['stock_move_id'] is None and p['value_cents']==0,'坏件未实际处置或伪造库存')
            expected=[(parties[0],parties[1],-p['destination_reverse_cents']),(parties[1],parties[0],p['destination_reverse_cents'])] if p['destination_reverse_cents'] else []
            actual=sb[p['id']];check(sorted((r['store_id'],r['counterparty_store_id'],r['amount_cents']) for r in actual)==sorted(expected),'承担冲回不成对或金额错误')
            for r in actual:
                prior=old_settlements.get(r['original_id'])
                check(prior and prior['posting_id']==loss['id'] and prior['store_id']==r['store_id'] and r['transfer_id']==parent['id'] and r['recovery_id']==h['id'] and r['business_date']==p['business_date'],'反向往来未追原损失本店条目')
    for lid,ps in grouped(postings,'loss_id').items():
        loss=losses[lid];done=dict(found=0,restored=0,value=0,destination=0)
        for p in sorted(ps,key=lambda x:x['id']):
            expected=allocation(loss['quantity_milli'],loss['value_cents'],loss['destination_bearer_cents'],done['found'],done['restored'],done['value'],done['destination'],p['found_quantity_milli'],bool(p['restored_quantity_milli']))
            check(all(p[k]==v for k,v in expected.items()),'原损失累计数量、价值或承担尾差不守恒')
            done['found']+=p['found_quantity_milli'];done['restored']+=p['restored_quantity_milli'];done['value']+=p['value_cents'];done['destination']+=p['destination_reverse_cents']
    for t in terms.values():
        h=headers.get(t['recovery_id']);claim=claims.get(t['claim_id']);old=oldplans.get(t['previous_plan_id']);new=oldplans.get(t['plan_id'])
        check(h and claim and old and new and posted[h['id']] and old['claim_id']==new['claim_id']==claim['id'] and claim['exception_id']==h['exception_id'] and t['store_id']==claim['store_id'],'新赔付条件没有追原本店条目')
        check(new['revision']>old['revision'] and new['target_cents']<=old['target_cents'] and at(new['created_at'])>=at(posted[h['id']][0]['created_at']),'新条件没有原物资恢复事实或增加猜测赔偿')
        loss=losses[h['loss_id']];parent=parents[h['transfer_id']];source=claim['store_id']==parent['from_store_id']
        reversed_amount=sum(p['source_reverse_cents'] if source else p['destination_reverse_cents'] for p in postings.values() if p['loss_id']==loss['id'] and at(p['created_at'])<=at(new['created_at']))
        check(new['target_cents']<=(loss['source_bearer_cents'] if source else loss['destination_bearer_cents'])-reversed_amount,'往来方新目标超过找到后本店剩余承担')
    for refund in refunds:
        t=terms.get(refund['terms_id']);payment=payments.get(refund['payment_id'])
        check(t and payment and refund['recovery_id']==t['recovery_id'] and refund['store_id']==t['store_id']==payment['store_id'] and payment['plan_id']==t['plan_id'] and payment['direction']=='out','实际退款没有本次原赔付条件')
    for h in headers.values():
        if h['status']!='closed' or not posted[h['id']][0]['restored_quantity_milli']:continue
        loss=losses[h['loss_id']];parent=parents[h['transfer_id']]
        for sid in (parent['from_store_id'],parent['to_store_id']):
            current_total=0
            cutoff=at(h['updated_at'])
            for claim in (c for c in claims.values() if c['exception_id']==h['exception_id'] and c['store_id']==sid and at(c['created_at'])<=cutoff):
                available=[p for p in oldplans.values() if p['claim_id']==claim['id'] and at(p['created_at'])<=cutoff]
                approved=[p for p in available if any(r['plan_id']==p['id'] and r['decision']=='approve' and at(r['created_at'])<=cutoff for r in oldreviews)]
                pending=[p for p in available if not any(r['plan_id']==p['id'] and at(r['created_at'])<=cutoff for r in oldreviews+oldcancels)]
                check(not pending,'已结清找回仍有未定赔付目标')
                if not approved:continue
                plan=max(approved,key=lambda p:p['revision']);net=sum(p['amount_cents']*(1 if p['direction']=='in' else -1) for p in payments.values() if p['claim_id']==claim['id'] and at(p['created_at'])<=cutoff)
                check(any(t['recovery_id']==h['id'] and t['plan_id']==plan['id'] for t in terms.values()) and net<=plan['target_cents'],'未确认原赔付条件或未退实际超收前不能结清找回')
                current_total+=max(net,plan['target_cents'])
            reversed_amount=sum(p['source_reverse_cents'] if sid==parent['from_store_id'] else p['destination_reverse_cents'] for p in postings.values() if p['loss_id']==loss['id'] and at(p['created_at'])<=cutoff)
            cap=(loss['source_bearer_cents'] if sid==parent['from_store_id'] else loss['destination_bearer_cents'])-reversed_amount
            check(current_total<=cap,'结清后赔付占用超过找回后原承担')
    check({s['id'] for s in stock.values() if s['purpose']=='transfer_found'}=={p['stock_move_id'] for p in postings.values() if p['stock_move_id'] is not None},'有原物资恢复库存未关联原损失')
    from .transfer_goods_search_integrity import validate_transfer_goods_searches
    validate_transfer_goods_searches(connection)
    return {'found_goods':len(headers),'found_goods_postings':len(postings)}
