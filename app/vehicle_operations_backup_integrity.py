"""Offline physical custody reconciliation; does not repair or infer missing facts."""
from collections import defaultdict


def validate_vehicle_operations(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'vehicle_operations' not in names:return {'verified_vehicle_operations':0,'verified_vehicle_positions':0}
    totals=defaultdict(int);operations={}
    def file(key,sid,cid):
        f=connection.execute('SELECT store_id,case_id FROM flow_files WHERE id=?',(key,)).fetchone()
        if not f or tuple(f)!=(sid,cid):raise ValueError('车辆作业凭据未绑定本店原单')
    def location(key,sid):
        row=connection.execute('SELECT l.store_id,w.store_id,w.warehouse_type FROM master_locations l JOIN master_warehouses w ON w.id=l.warehouse_id WHERE l.id=?',(key,)).fetchone()
        if not row or tuple(row[:2])!=(sid,sid) or row[2] not in {'vehicles','mixed'}:raise ValueError('整车实际库位门店或仓库类型不一致')
    for key,sid,kind,status,vehicle,generation,vin,src,dest,original,aftercare,source_order,authorization,new,cost in connection.execute('SELECT id,store_id,kind,status,source_vehicle_id,source_generation,vin,source_location_id,destination_location_id,original_operation_id,aftercare_case_id,source_order_id,authorization_evidence_id,received_vehicle_id,cost_cents FROM vehicle_operations'):
        operations[key]=(kind,status,vehicle,vin,cost)
        c=connection.execute('SELECT kind,flow_version,store_id FROM flow_cases WHERE id=?',(key,)).fetchone()
        car=connection.execute('SELECT store_id,vin,inventory_generation,purchase_cost_cents FROM vehicles WHERE id=?',(vehicle,)).fetchone()
        if not c or tuple(c)!=('vehicle_operations',2,sid) or not car or tuple(car)!=(sid,vin,generation,cost):raise ValueError('车辆作业原单、VIN代次或成本来源不一致')
        claim=connection.execute('SELECT store_id,vin,active_vin FROM vehicle_operation_claims WHERE case_id=?',(key,)).fetchone()
        active=None if status in {'completed','cancelled','rejected','accepted','returned_to_customer'} else vin
        if not claim or tuple(claim)!=(sid,vin,active):raise ValueError('车辆作业状态与VIN占用不一致')
        if src:location(src,sid)
        if dest:location(dest,sid)
        entries=list(connection.execute('SELECT kind,quantity,inventory_delta,value_cents,vehicle_id,original_id FROM vehicle_position_entries WHERE operation_id=?',(key,)))
        facts={e[0]:e for e in entries}
        if len(facts)!=len(entries):raise ValueError('车辆作业重复实物确认')
        reviews=list(connection.execute('SELECT decision,inspection_id,evidence_id FROM vehicle_operation_reviews WHERE operation_id=?',(key,)))
        requester=connection.execute('SELECT requested_by FROM vehicle_operations WHERE id=?',(key,)).fetchone()[0]
        for decision,inspection,actor in connection.execute('SELECT decision,inspection_id,actor_id FROM vehicle_operation_reviews WHERE operation_id=?',(key,)):
            if decision in {'approve','reject'} and actor==requester:raise ValueError('车辆作业申请与批准必须由不同员工完成')
            if inspection:
                checker=connection.execute('SELECT actor_id FROM vehicle_return_inspections WHERE id=?',(inspection,)).fetchone()
                if not checker or checker[0]==actor:raise ValueError('退车检查与主管判定必须由不同员工完成')
        for decision,inspection,eid in reviews:
            file(eid,sid,key)
            if decision in {'release','rectify','return_to_customer'}:
                check=connection.execute('SELECT operation_id,outcome FROM vehicle_return_inspections WHERE id=?',(inspection,)).fetchone()
                if not check or check[0]!=key or decision=='release' and check[1]!='pass':raise ValueError('退车判定缺少对应检查，或不合格被放行')
        if kind!='customer_return':
            if status not in {'requested','cancelled','rejected'} and not any(r[0]=='approve' for r in reviews):raise ValueError('车辆实物作业缺少主管批准')
            expected=set()
            if kind=='locate' and status=='completed':expected={'locate'}
            if kind=='other_out' and status=='completed':expected={'other_out'}
            if kind=='other_return' and status=='completed':expected={'other_return'}
            if kind=='local_move':
                if status=='transit':expected={'local_dispatch'}
                elif status=='returning':expected={'local_dispatch','local_reject'}
                elif status=='completed':expected={'local_dispatch','local_accept'} if 'local_accept' in facts else {'local_dispatch','local_reject','local_return'}
            if set(facts)!=expected:raise ValueError('车辆作业状态与实际出入库记录不一致')
            if kind=='other_return':
                origin=connection.execute('SELECT store_id,kind,status,source_vehicle_id,cost_cents FROM vehicle_operations WHERE id=?',(original,)).fetchone()
                if not origin or tuple(origin)!=(sid,'other_out','completed',vehicle,cost):raise ValueError('原车退回未关联真实原出库与原成本')
                if status=='completed':
                    entry=connection.execute("SELECT id FROM vehicle_position_entries WHERE operation_id=? AND kind='other_out'",(original,)).fetchone()
                    if not entry or facts['other_return'][5]!=entry[0]:raise ValueError('车辆退回没有冲回原实际出库')
        else:
            if not aftercare or not source_order or not authorization:raise ValueError('客户退车没有原售后授权与销售来源')
            file(authorization,sid,aftercare)
            source=connection.execute('SELECT store_id,kind,vehicle_id,data FROM flow_cases WHERE id=?',(source_order,)).fetchone()
            import json
            if not source or tuple(source[:3])!=(sid,'order',vehicle) or not json.loads(source[3]).get('dispatched_at'):raise ValueError('客户实退缺少原车实际出库来源')
            q=list(connection.execute('SELECT kind,location_id,evidence_id FROM vehicle_quarantine_facts WHERE operation_id=?',(key,)))
            for qkind,loc,eid in q:location(loc,sid);file(eid,sid,key)
            kinds={r[0] for r in q}
            expected=set() if status in {'awaiting_receipt','cancelled'} else {'intake','release'} if status=='accepted' else {'intake','return_to_customer'} if status=='returned_to_customer' else {'intake'}
            if kinds!=expected or len(kinds)!=len(q):raise ValueError('隔离状态与实际车辆交接不一致')
            for eid, in connection.execute('SELECT evidence_id FROM vehicle_return_inspections WHERE operation_id=?',(key,)):file(eid,sid,key)
            if status=='accepted':
                if set(facts)!={'customer_return'} or not any(r[0]=='release' for r in reviews):raise ValueError('退回车辆未通过检查批准即变为可售')
            elif facts:raise ValueError('尚未合格实际入库的退车不得改变可售库存')
        if (kind=='other_return' and status=='completed') or status=='accepted':
            carnew=connection.execute('SELECT store_id,vin,inventory_generation,purchase_cost_cents FROM vehicles WHERE id=?',(new,)).fetchone()
            if not carnew or tuple(carnew[:2])!=(sid,vin) or carnew[2]<=generation or carnew[3]!=cost:raise ValueError('原车实退必须建立本店新代次并保留原成本')
        elif new is not None:raise ValueError('尚未实际验收入库不得创建新代次')
    for key,sid,cid,op,vehicle,loc,kind,qty,delta,value,original,eid in connection.execute('SELECT id,store_id,case_id,operation_id,vehicle_id,location_id,kind,quantity,inventory_delta,value_cents,original_id,evidence_id FROM vehicle_position_entries'):
        file(eid,sid,cid)
        car=connection.execute('SELECT store_id,purchase_cost_cents FROM vehicles WHERE id=?',(vehicle,)).fetchone()
        if not car or car[0]!=sid or qty not in {-1,0,1} or value!=qty*car[1]:raise ValueError('车辆库位账数量价值与原车不守恒')
        expected_delta=-1 if kind=='other_out' else 1 if kind in {'other_return','customer_return'} else 0
        if delta!=expected_delta:raise ValueError('整车门店库存移动与库位移动统计重复或漏记')
        if loc:location(loc,sid);totals[(vehicle,loc)]+=qty
        elif qty:raise ValueError('明确库位账缺少实际库位')
        if op and (op not in operations or cid!=op):raise ValueError('车辆库位账作业关联不一致')
        if original:
            old=connection.execute('SELECT store_id,quantity,value_cents FROM vehicle_position_entries WHERE id=?',(original,)).fetchone()
            if not old or tuple(old)!=(sid,-qty,-value):raise ValueError('车辆原单退回数量价值没有成对冲回')
    positions=list(connection.execute('SELECT vehicle_id,store_id,location_id,status FROM vehicle_positions'))
    for vehicle,sid,loc,status in positions:
        current={l:q for (v,l),q in totals.items() if v==vehicle and q}
        if current!=({loc:1} if status=='stored' else {}):raise ValueError('车辆当前库位与不可变位置账不一致')
        if status=='stored':location(loc,sid)
    if any(v not in {p[0] for p in positions} for v,l in totals):raise ValueError('车辆库位账缺少对应定位记录')
    for source,aftercare,vehicle,eid,sid in connection.execute('SELECT source_case_id,aftercare_case_id,vehicle_id,evidence_id,store_id FROM vehicle_order_hold_releases'):
        src=connection.execute('SELECT store_id,vehicle_id FROM flow_cases WHERE id=?',(source,)).fetchone()
        f=connection.execute('SELECT store_id FROM flow_files WHERE id=?',(eid,)).fetchone()
        if not src or tuple(src)!=(sid,vehicle) or not f or f[0]!=sid:raise ValueError('销售释放凭据未绑定本店原车')
        if connection.execute('SELECT 1 FROM flow_vehicle_holds WHERE case_id=?',(source,)).fetchone():raise ValueError('已生效原单释放与当前车辆占用不一致')
    return {'verified_vehicle_operations':len(operations),'verified_vehicle_positions':len(positions)}


def valid_exit_vins(connection):
    """Only a verified, latest-generation actual other-out permits empty custody."""
    validate_vehicle_operations(connection)
    return {r[0] for r in connection.execute("SELECT o.vin FROM vehicle_operations o JOIN vehicle_position_entries e ON e.operation_id=o.id AND e.kind='other_out' JOIN vehicle_custodies c ON c.vin=o.vin WHERE o.kind='other_out' AND o.status='completed' AND c.current_vehicle_id IS NULL AND c.generation=o.source_generation AND e.inventory_delta=-1 AND e.value_cents=-o.cost_cents")}
