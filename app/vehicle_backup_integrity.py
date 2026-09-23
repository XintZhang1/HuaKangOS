"""Validate stored vehicle custody and immutable handoffs without exposing records."""
import json


def _purchase_sources(connection,names):
    """Offline restore check: no-current custody requires verifiable purchase facts."""
    if 'vehicle_purchase_shipments' not in names:return set(),0
    latest_sources={};count=0
    def owned_file(key,sid,cid):
        asset=connection.execute('SELECT store_id,case_id FROM flow_files WHERE id=?',(key,)).fetchone()
        if not asset or tuple(asset)!=(sid,cid):raise ValueError('整车采购凭据与本店原单不一致')
    for cid,sid,supplier in connection.execute('SELECT id,store_id,supplier_id FROM vehicle_purchase_orders'):
        count+=1
        case=connection.execute('SELECT kind,flow_version,state,amount_cents,store_id FROM flow_cases WHERE id=?',(cid,)).fetchone()
        if not case or case[0]!='vehicle_procurement' or case[1]!=2 or case[4]!=sid:raise ValueError('整车采购与原单范围不一致')
        approved=0;commitment=0
        for line,qty in connection.execute('SELECT id,quantity FROM vehicle_purchase_lines WHERE case_id=? AND store_id=?',(cid,sid)):
            price=connection.execute('SELECT unit_cost_cents,evidence_id,case_id,store_id FROM vehicle_purchase_prices WHERE line_id=?',(line,)).fetchone()
            shipped=connection.execute('SELECT COUNT(*) FROM vehicle_purchase_shipments WHERE line_id=?',(line,)).fetchone()[0]
            cancelled=connection.execute('SELECT COALESCE(SUM(quantity),0) FROM vehicle_purchase_cancellations WHERE line_id=?',(line,)).fetchone()[0]
            if shipped+cancelled>qty:raise ValueError('整车采购计划数量与发运取消不守恒')
            if case[2] in {'approval','rejected'}:
                if price or shipped or cancelled:raise ValueError('未批准整车采购不能核价发运或取消余量')
            else:
                if not price or tuple(price[2:])!=(cid,sid):raise ValueError('整车采购核价不完整或归属不一致')
                owned_file(price[1],sid,cid);approved+=qty*price[0];commitment+=(qty-cancelled)*price[0]
        if approved!=case[3]:raise ValueError('整车采购批准总额与逐行价格不一致')
        paid=0
        for key,psid,account,original,direction,amount,cash,eid,reference,funds_id in connection.execute('SELECT id,store_id,account_id,original_id,direction,amount_cents,cash_id,evidence_id,reference,funds_request_id FROM vehicle_purchase_payments WHERE case_id=?',(cid,)):
            acct=connection.execute('SELECT store_id,name FROM flow_accounts WHERE id=?',(account,)).fetchone()
            fact=connection.execute('SELECT store_id,direction,amount_cents,account,voucher_no,category FROM cash_entries WHERE id=?',(cash,)).fetchone()
            expected_category='vehicle_procurement_payment' if direction=='out' else 'vehicle_procurement_refund'
            if psid!=sid or not acct or acct[0]!=sid or not fact or tuple(fact)!=(sid,direction,amount,acct[1],reference,expected_category):raise ValueError('整车采购款与唯一现金事实不一致')
            owned_file(eid,sid,cid);paid+=amount*(1 if direction=='out' else -1)
            if original:
                origin=connection.execute('SELECT case_id,store_id,account_id,direction,amount_cents FROM vehicle_purchase_payments WHERE id=?',(original,)).fetchone()
                total=connection.execute('SELECT SUM(amount_cents) FROM vehicle_purchase_payments WHERE original_id=?',(original,)).fetchone()[0]
                if not origin or tuple(origin[:4])!=(cid,sid,account,'out') or total>origin[4]:raise ValueError('整车采购退款超过原付款或关联错误')
            else:
                funds=connection.execute('SELECT case_id,store_id,amount_cents FROM vehicle_purchase_funds_requests WHERE id=?',(funds_id,)).fetchone()
                total=connection.execute('SELECT SUM(amount_cents) FROM vehicle_purchase_payments WHERE funds_request_id=?',(funds_id,)).fetchone()[0]
                if not funds or tuple(funds[:2])!=(cid,sid) or total>funds[2]:raise ValueError('整车采购付款超过获准请款或归属错误')
        if paid<0:raise ValueError('整车采购退款超过实际付款')
        for key,ss,vin,active,line,eid in connection.execute('SELECT id,status,vin,active_vin,line_id,evidence_id FROM vehicle_purchase_shipments WHERE case_id=? AND store_id=?',(cid,sid)):
            owned_file(eid,sid,cid)
            custody=connection.execute('SELECT identity_id FROM vehicle_custodies WHERE vin=?',(vin,)).fetchone()
            identity=connection.execute("SELECT id FROM group_identities WHERE kind='vehicle' AND canonical_key=?",(vin,)).fetchone()
            if not custody or not identity or custody[0]!=identity[0]:raise ValueError('采购VIN没有一致的集团身份及保管来源')
            price=connection.execute('SELECT unit_cost_cents FROM vehicle_purchase_prices WHERE line_id=? AND case_id=? AND store_id=?',(line,cid,sid)).fetchone()
            if not price:raise ValueError('发运VIN缺少已批准车型价格')
            receipt=connection.execute('SELECT id,vehicle_id,value_cents,evidence_id,location_id FROM vehicle_purchase_receipts WHERE shipment_id=? AND case_id=? AND store_id=?',(key,cid,sid)).fetchone()
            moves=list(connection.execute('SELECT id,kind,vehicle_id,quantity,value_cents,original_id,return_id,evidence_id,store_id,case_id FROM vehicle_purchase_movements WHERE shipment_id=?',(key,)))
            kinds={m[1] for m in moves}
            if ss=='transit':expected=set()
            elif ss=='received':expected={'receive'}
            else:expected={'receive','return'} if receipt else {'transit_return'}
            if kinds!=expected or len(kinds)!=len(moves) or (ss=='transit' and active!=vin) or (ss!='transit' and active is not None):raise ValueError('采购VIN状态与实际移动或占用不一致')
            if ss=='received' and not receipt or ss=='transit' and receipt:raise ValueError('采购VIN验收来源缺失或越过实物状态')
            if receipt:
                car=connection.execute('SELECT store_id,vin,purchase_cost_cents FROM vehicles WHERE id=?',(receipt[1],)).fetchone()
                if not car or tuple(car)!=(sid,vin,price[0]) or receipt[2]!=price[0]:raise ValueError('整车采购入库成本与原核价不一致')
                owned_file(receipt[3],sid,cid)
                loc=connection.execute('SELECT store_id FROM master_locations WHERE id=?',(receipt[4],)).fetchone()
                if not loc or loc[0]!=sid:raise ValueError('整车入库库位不属于原门店')
                link=connection.execute("SELECT identity_id,store_id FROM group_identity_links WHERE local_kind='vehicle' AND local_id=?",(receipt[1],)).fetchone()
                if not link or tuple(link)!=(identity[0],sid):raise ValueError('采购入库车辆与共享VIN身份未关联')
            origin=next((m for m in moves if m[1]=='receive'),None)
            for move,kind,vehicle,qty,value,original,ret,evidence_id,msid,mcid in moves:
                if (msid,mcid)!=(sid,cid):raise ValueError('整车采购移动归属不一致')
                owned_file(evidence_id,sid,cid)
                sign=1 if kind=='receive' else -1 if kind=='return' else 0
                if qty!=sign or value!=sign*price[0] or vehicle!=(receipt[1] if receipt else None):raise ValueError('整车采购移动数量价值不守恒')
                if kind=='return' and (not origin or original!=origin[0]):raise ValueError('整车退回没有冲回原入库记录')
                if kind!='receive':
                    retrow=connection.execute('SELECT shipment_id,case_id,store_id,status,approved_by FROM vehicle_purchase_returns WHERE id=?',(ret,)).fetchone()
                    if not retrow or tuple(retrow[:4])!=(key,cid,sid,'dispatched') or not retrow[4]:raise ValueError('整车退回没有原申请及主管批准')
            if key>latest_sources.get(vin,(0,''))[0]:latest_sources[vin]=(key,ss)
    return {vin for vin,(_,status) in latest_sources.items() if status in {'transit','returned'}},count


def validate_vehicle_custody(connection):
    names={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'vehicle_custodies' not in names:return {'verified_vehicle_transfers':0}
    from .vehicle_transport_integrity import validate_vehicle_transport, frozen_vehicle_movement_kinds
    transport_counts=validate_vehicle_transport(connection)
    purchase_sources,purchase_count=_purchase_sources(connection,names)
    if 'vehicle_operations' in names:
        from .vehicle_operations_backup_integrity import valid_exit_vins
        purchase_sources |= valid_exit_vins(connection)
    transfers={row[0]:row for row in connection.execute('SELECT id,from_store_id,to_store_id,from_case_id,to_case_id,source_vehicle_id,received_vehicle_id,vin,snapshot,status FROM vehicle_transfers')}
    for key,source,target,out_case,in_case,original_id,received_id,vin,snapshot,status in transfers.values():
        value=json.loads(snapshot)['purchase_cost_cents']
        moves=list(connection.execute('SELECT kind,store_id,case_id,vehicle_id,quantity,value_cents FROM vehicle_movements WHERE transfer_id=?',(key,)))
        kinds={m[0] for m in moves}
        expected={'requested':set(),'approved':set(),'cancelled':set(),'transit':{'dispatch'},'rejected':{'dispatch','reject'},
            'return_transit':{'dispatch','reject','return_ship'},'accepted':{'dispatch','accept'},'returned':{'dispatch','reject','return_ship','return_receive'}}.get(status)
        if status in {'lost','recovered'}:
            expected=frozen_vehicle_movement_kinds(connection,key)
        if expected is None:raise ValueError('整车调拨状态不受支持')
        if kinds!=expected or len(kinds)!=len(moves):raise ValueError('整车调拨状态与实际交接记录不一致')
        for kind,sid,cid,vehicle_id,qty,amount in moves:
            out=kind in {'dispatch','return_receive'}
            if sid!=(source if out else target) or cid!=(out_case if out else in_case):raise ValueError('整车交接记录门店与来源单据不一致')
            if kind in {'dispatch','accept','return_receive'}:
                sign=-1 if kind=='dispatch' else 1
                car=connection.execute('SELECT store_id,vin,purchase_cost_cents FROM vehicles WHERE id=?',(vehicle_id,)).fetchone()
                if not car or car[0]!=sid or car[1].upper()!=vin or car[2]!=value or qty!=sign or amount!=sign*value:
                    raise ValueError('整车实物记录与库存价值不一致')
                if vehicle_id!=(original_id if kind=='dispatch' else received_id):raise ValueError('整车调拨入出库来源关联不一致')
            elif vehicle_id is not None or qty!=0 or amount!=0:raise ValueError('拒收或发运记录不能直接改变可用库存')
        clearing=list(connection.execute('SELECT store_id,counterparty_store_id,amount_cents FROM vehicle_transfer_settlements WHERE transfer_id=?',(key,)))
        if status=='accepted':
            if sorted(clearing)!=sorted([(source,target,value),(target,source,-value)]):raise ValueError('整车调拨双方往来不配对')
        elif clearing:raise ValueError('尚未接受的整车调拨不能确认店间往来')
    for vin,current_id,sid,generation,pending in connection.execute('SELECT vin,current_vehicle_id,current_store_id,generation,pending_transfer_id FROM vehicle_custodies'):
        cars=list(connection.execute('SELECT id,store_id,inventory_generation,approval_state FROM vehicles WHERE UPPER(vin)=?',(vin,)))
        if (not cars and (generation!=0 or vin not in purchase_sources)) or (cars and max(c[2] for c in cars)!=generation):raise ValueError('整车VIN当前库存批次不一致')
        def delivered(car):
            return bool(connection.execute("SELECT 1 FROM flow_vehicle_holds h JOIN flow_cases c ON c.id=h.case_id AND c.store_id=h.store_id WHERE h.vehicle_id=? AND h.delivered=1 AND c.kind='order' AND c.state IN ('delivered','completed','credit_open') AND c.completed_date IS NOT NULL",(car[0],)).fetchone() or
                connection.execute("SELECT 1 FROM sales WHERE vehicle_id=? AND approval_state='approved' AND sale_stage='delivered'",(car[0],)).fetchone())
        approved=[c for c in cars if c[3]=='approved' and not delivered(c)]
        if current_id is not None:
            current=next((c for c in cars if c[0]==current_id and c[1]==sid and c[3]=='approved'),None)
            if not current or current[2]!=generation or any(c[0]!=current_id for c in approved):raise ValueError('同一VIN当前库存不唯一或门店归属不一致')
        elif sid is not None or approved:raise ValueError('在途车辆不能同时存在可用库存')
        if pending:
            t=transfers.get(pending)
            if not t or t[7]!=vin or t[-1] not in {'requested','approved','transit','rejected','return_transit','lost'}:raise ValueError('整车调拨占用与未结束调拨不一致')
        elif current_id is None and vin not in purchase_sources:raise ValueError('整车既无当前库存也无在途或退回来源')
    return {'verified_vehicle_transfers':len(transfers),'verified_vehicle_purchases':purchase_count,**transport_counts}
