"""Offline SQLite-source validation used before restore/transfer, without ORM scope."""
def validate_warehouse_integrity(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'warehouse_enrollments' not in names:return {'verified_warehouse_items':0,'verified_warehouse_entries':0}
    count=0;entry_count=0
    def one(sql,args=()):return connection.execute(sql,args).fetchone()
    def total(sql,args=()):return one(sql,args)[0] or 0
    def owned_file(key,sid,cid):
        row=one('SELECT store_id,case_id FROM flow_files WHERE id=?',(key,))
        if not row or tuple(row)!=(sid,cid):raise ValueError('仓储凭据与本店原单不一致')
    if one('SELECT b.id FROM warehouse_balances b LEFT JOIN warehouse_enrollments e ON e.item_id=b.item_id WHERE e.id IS NULL LIMIT 1'):
        raise ValueError('真实库位余额缺少经过核对的启用来源')
    for enrollment,item,cid,sid,baseline_qty,baseline_value,cursor in connection.execute('SELECT id,item_id,case_id,store_id,baseline_quantity_milli,baseline_value_cents,stock_move_cursor FROM warehouse_enrollments'):
        count+=1
        current=one('SELECT store_id,quantity_milli,inventory_value_cents FROM flow_items WHERE id=?',(item,))
        doc=one("SELECT d.operation,c.state,d.item_id,d.store_id FROM warehouse_documents d JOIN flow_cases c ON c.id=d.id WHERE d.id=?",(cid,))
        if not current or current[0]!=sid or not doc or tuple(doc)!=('activate','completed',item,sid):raise ValueError('库位启用与物资原单不一致')
        balances=list(connection.execute('SELECT id,store_id,bucket,location_id,transit_case_id,quantity_milli,value_cents FROM warehouse_balances WHERE item_id=?',(item,)))
        if sum(b[5] for b in balances)!=current[1] or sum(b[6] for b in balances)!=current[2]:raise ValueError('库位及在途余额与门店库存不守恒')
        for bid,bsid,bucket,loc,transit,qty,value in balances:
            if bsid!=sid or qty<0 or value<0 or (not qty and value):raise ValueError('库位余额归属或数量价值无效')
            if loc:
                place=one('SELECT store_id FROM master_locations WHERE id=?',(loc,))
                if not place or place[0]!=sid or bucket!=f'bin:{loc}' or transit:raise ValueError('库存库位不属于本店')
            else:
                original=one("SELECT d.operation,d.item_id,d.store_id FROM warehouse_documents d WHERE d.id=?",(transit,))
                if not original or tuple(original)!=('local_move',item,sid) or bucket!=f'transit:{transit}':raise ValueError('店内在途没有原移库作业')
            facts=list(connection.execute('SELECT store_id,case_id,stock_move_id,quantity_milli,value_cents FROM warehouse_entries WHERE balance_id=?',(bid,)))
            entry_count+=len(facts)
            if sum(e[3] for e in facts)!=qty or sum(e[4] for e in facts)!=value:raise ValueError('库位流水与余额不一致')
            for esid,ecid,move,eq,ev in facts:
                case=one('SELECT store_id FROM flow_cases WHERE id=?',(ecid,))
                if esid!=sid or not case or case[0]!=sid:raise ValueError('库位流水原单跨门店')
                if move:
                    m=one('SELECT store_id,case_id,item_id FROM flow_stock_moves WHERE id=?',(move,))
                    if not m or tuple(m)!=(sid,ecid,item):raise ValueError('库位流水没有对应原物资过账')
        base=one('SELECT COALESCE(SUM(quantity_milli),0),COALESCE(SUM(value_cents),0) FROM warehouse_entries WHERE case_id=? AND stock_move_id IS NULL',(cid,))
        if tuple(base)!=(baseline_qty,baseline_value):raise ValueError('库位启用的原始数量价值分配不一致')
        prior=one('SELECT COALESCE(SUM(quantity_milli),0),COALESCE(SUM(value_cents),0) FROM flow_stock_moves WHERE item_id=? AND id<=?',(item,cursor))
        opening=one('SELECT COALESCE(SUM(quantity_milli),0),COALESCE(SUM(value_cents),0) FROM opening_stock_entries WHERE item_id=?',(item,))
        if (prior[0]+opening[0],prior[1]+opening[1])!=(baseline_qty,baseline_value):raise ValueError('库位启用没有可核对的历史来源')
        for mid,mcid,msid,mqty,mvalue,purpose in connection.execute('SELECT id,case_id,store_id,quantity_milli,value_cents,purpose FROM flow_stock_moves WHERE item_id=? AND id>?',(item,cursor)):
            if msid!=sid:raise ValueError('物资收发跨门店')
            entries=one('SELECT COALESCE(SUM(quantity_milli),0),COALESCE(SUM(value_cents),0) FROM warehouse_entries WHERE stock_move_id=?',(mid,))
            allocation=one('SELECT store_id,case_id,item_id,quantity_milli,purpose,status FROM warehouse_allocations WHERE stock_move_id=?',(mid,))
            if tuple(entries)!=(mqty,mvalue) or not allocation or tuple(allocation)!=(sid,mcid,item,mqty,purpose,'consumed'):
                raise ValueError('启用后的物资收发缺少等额库位分配与流水')
            planned={loc:q*(1 if mqty>=0 else -1) for loc,q in connection.execute('SELECT l.location_id,l.quantity_milli FROM warehouse_allocation_lines l JOIN warehouse_allocations a ON a.id=l.allocation_id WHERE a.stock_move_id=?',(mid,)) if q}
            actual={loc:q for loc,q in connection.execute('SELECT b.location_id,SUM(e.quantity_milli) FROM warehouse_entries e JOIN warehouse_balances b ON b.id=e.balance_id WHERE e.stock_move_id=? GROUP BY b.location_id',(mid,)) if q}
            if planned!=actual:raise ValueError('实际收发库位与员工明确分配不一致')
    for cid,sid,op,item,qty,src,dest,original in connection.execute('SELECT id,store_id,operation,item_id,quantity_milli,source_location_id,destination_location_id,original_move_id FROM warehouse_documents'):
        case=one('SELECT kind,flow_version,state,store_id FROM flow_cases WHERE id=?',(cid,))
        if not case or case[0]!='warehouse' or case[1]!=2 or case[3]!=sid:raise ValueError('仓储作业与流程版本或门店不一致')
        for loc in (src,dest):
            if loc:
                r=one('SELECT store_id FROM master_locations WHERE id=?',(loc,))
                if not r or r[0]!=sid:raise ValueError('仓储作业库位跨门店')
        approval=one('SELECT value_cents,evidence_id,store_id FROM warehouse_approvals WHERE case_id=?',(cid,))
        if approval:
            if approval[2]!=sid:raise ValueError('仓储审批归属错误')
            owned_file(approval[1],sid,cid)
        if case[2] not in {'pending','rejected','cancelled'} and not approval:raise ValueError('仓储实际办理没有主管批准')
        if case[2] in {'pending','rejected','cancelled','ready','counting','review'} and total('SELECT COUNT(*) FROM flow_stock_moves WHERE case_id=?',(cid,)):
            raise ValueError('尚未实物确认或已撤销的仓储作业不能存在库存过账')
        hold=total('SELECT SUM(quantity_milli) FROM warehouse_holds WHERE case_id=?',(cid,))
        for hs,hi,hl in connection.execute('SELECT store_id,item_id,location_id FROM warehouse_holds WHERE case_id=?',(cid,)):
            if (hs,hi,hl)!=(sid,item,src):raise ValueError('仓储预占未关联本单原物资库位')
        expected=qty if case[2]=='ready' and op in {'other_in_return','consumable','gift','disposal','local_move'} else 0
        if hold!=expected:raise ValueError('仓储预占与作业实际进度不一致')
        if op=='local_move':
            entries=one('SELECT COALESCE(SUM(quantity_milli),0),COALESCE(SUM(value_cents),0) FROM warehouse_entries WHERE case_id=? AND stock_move_id IS NULL',(cid,))
            if tuple(entries)!=(0,0):raise ValueError('店内移库数量价值不守恒')
            transit=total('SELECT SUM(quantity_milli) FROM warehouse_balances WHERE transit_case_id=?',(cid,))
            if (case[2] in {'transit','returning'})!=(transit>0) or transit>qty:raise ValueError('店内在途与移库进度不一致')
        if op=='count':
            ob=one('SELECT baseline_quantity_milli,counted_quantity_milli,evidence_id,store_id FROM warehouse_count_observations WHERE case_id=?',(cid,))
            if case[2] in {'review','completed'} and not ob:raise ValueError('盘点没有真实观察')
            if ob:
                if ob[3]!=sid:raise ValueError('盘点观察归属错误')
                owned_file(ob[2],sid,cid)
                delta=total('SELECT SUM(quantity_milli) FROM flow_stock_moves WHERE case_id=?',(cid,))
                if delta!=(ob[1]-ob[0] if case[2]=='completed' else 0):raise ValueError('盘点差异没有按原观察过账')
        if case[2]=='completed' and op not in {'activate','local_move','count'}:
            moves=list(connection.execute('SELECT quantity_milli,value_cents,original_id FROM flow_stock_moves WHERE case_id=?',(cid,)))
            sign=-1 if op in {'other_in_return','consumable','gift','disposal'} else 1
            if len(moves)!=1 or moves[0][0]!=sign*qty or moves[0][2]!=original:raise ValueError('仓储实际收发与获准原单不一致')
            if op=='other_in' and moves[0][1]!=approval[0]:raise ValueError('其他入库价值与批准来源不一致')
            if original:
                m=one('SELECT item_id,store_id,purpose,quantity_milli,value_cents FROM flow_stock_moves WHERE id=?',(original,))
                expected={'other_in_return':'wh_other_in','consumable_return':'wh_consumable','gift_return':'wh_gift'}.get(op)
                if not m or tuple(m[:3])!=(item,sid,expected):raise ValueError('仓储退回没有正确的原始收发来源')
                returned=one('SELECT COALESCE(SUM(ABS(quantity_milli)),0),COALESCE(SUM(ABS(value_cents)),0) FROM flow_stock_moves WHERE original_id=?',(original,))
                if returned[0]>abs(m[3]) or returned[1]>abs(m[4]) or (returned[0]==abs(m[3]) and returned[1]!=abs(m[4])):
                    raise ValueError('仓储原单退回数量价值不守恒')
    return {'verified_warehouse_items':count,'verified_warehouse_entries':entry_count}
