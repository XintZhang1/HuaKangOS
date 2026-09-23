"""Rebuild original supplier credit, average cost and approved stock reservations."""
from collections import defaultdict
from datetime import datetime


def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'procurement_return_valuations' not in names:return {'verified_purchase_return_valuations':0}
    def rows(name):
        q=connection.execute('SELECT * FROM '+name);keys=[r[0] for r in q.description];return [dict(zip(keys,r)) for r in q]
    def by(name):return {r['id']:r for r in rows(name)}
    def same(*args):return all(r for r in args) and len({r['store_id'] for r in args})==1
    def portion(value,q,total):return value if q==total else (2*value*q+total)//(2*total)
    def fail(message):raise ValueError('采购退货成本恢复检查：'+message)
    cases=by('flow_cases');postings=by('procurement_return_postings');valuations=by('procurement_return_valuations')
    moves=by('flow_stock_moves');items=by('flow_items');receipts=by('procurement_receipts');lines=by('procurement_lines')
    requests=by('procurement_returns');return_lines=by('procurement_return_lines');files=by('flow_files');openings=rows('opening_stock_entries')
    expected={p['id'] for p in postings.values() if cases[p['case_id']]['flow_version']==3}
    if expected!=set(valuations):fail('新版本实物退货缺少唯一原款与成本分离记录，或旧版本被重新解释')
    used_qty=defaultdict(int);used_value=defaultdict(int)
    for p in sorted(postings.values(),key=lambda r:r['id']):
        case=cases[p['case_id']];r=receipts.get(p['receipt_id']);l=return_lines.get(p['return_line_id']);request=requests.get(l['return_id']) if l else None
        move=moves.get(p['stock_move_id']);original=lines.get(r['line_id']) if r else None;proof=files.get(p['evidence_id'])
        if not same(p,case,r,l,request,move,original,proof) or case['kind']!='procurement' or request['case_id']!=case['id'] or r['case_id']!=case['id'] or original['case_id']!=case['id']:fail('原申请、原验收、原单或凭据跨店及错配')
        if request['status']!='dispatched' or request['approved_by'] is None or l['receipt_id']!=r['id'] or p['quantity_milli']!=l['quantity_milli']:fail('未批准实际发出或替换原退货数量')
        if proof['case_id']!=case['id'] or proof['generated']:fail('退货缺少本单实际交接原件')
        remaining=r['quantity_milli']-used_qty[r['id']];value=r['value_cents']-used_value[r['id']]
        if not 0<p['quantity_milli']<=remaining or p['value_cents']!=portion(value,p['quantity_milli'],remaining):fail('原供应商冲款不按原批次剩余金额分摊')
        used_qty[r['id']]+=p['quantity_milli'];used_value[r['id']]+=p['value_cents']
        if move['case_id']!=case['id'] or move['item_id']!=original['item_id'] or move['original_id']!=r['stock_move_id'] or move['purpose']!='procurement_return' or move['quantity_milli']!=-p['quantity_milli']:fail('退货原物资流水不一致')
        if case['flow_version']==2:
            if move['value_cents']!=-p['value_cents']:fail('旧版本原批次成本被改变')
            continue
        if case['flow_version']!=3:fail('采购退货版本不受支持')
        v=valuations[p['id']];item=items[move['item_id']]
        if not same(v,p,item):fail('成本分离记录跨店')
        before=[m for m in moves.values() if m['item_id']==item['id'] and m['id']<move['id']]
        initial=[o for o in openings if o['item_id']==item['id'] and datetime.fromisoformat(o['created_at'])<=datetime.fromisoformat(move['occurred_at'])]
        qty=sum(m['quantity_milli'] for m in before+initial);value=sum(m['value_cents'] for m in before+initial)
        if (v['quantity_before_milli'],v['value_before_cents'])!=(qty,value) or qty<p['quantity_milli'] or value<0:fail('均价计算的原库存数量或价值缺少来源')
        cost=portion(value,p['quantity_milli'],qty)
        if (v['inventory_cost_cents'],v['supplier_credit_cents'],v['variance_cents'],move['value_cents'])!=(cost,p['value_cents'],p['value_cents']-cost,-cost):fail('库存成本、供应商原冲款及差额不守恒')
    # New reservations are actual quantity holds and share the physical balance.
    reserved=defaultdict(int)
    for l in return_lines.values():
        request=requests[l['return_id']];case=cases[request['case_id']]
        if request['status']!='approved' or case['flow_version']!=3:continue
        receipt=receipts[l['receipt_id']];line=lines[receipt['line_id']]
        if not same(l,request,case,receipt,line) or receipt['case_id']!=case['id']:fail('库存占量越过本店原采购')
        reserved[line['item_id']]+=l['quantity_milli']
    for iid,qty in reserved.items():
        if qty>items[iid]['quantity_milli']:fail('批准原退占量超过当前实际库存')
    return {'verified_purchase_return_valuations':len(valuations)}
