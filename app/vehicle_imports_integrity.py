"""Offline source/result verification; imports do not create another stock/cash ledger."""
import hashlib,json
from .vehicle_imports_csv import parse
from .vehicle_imports_service import _key


def validate_vehicle_imports(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'vehicle_import_batches' not in names:return {'verified_vehicle_import_batches':0,'verified_vehicle_import_results':0}
    batches=0;results=0
    for b in connection.execute('SELECT id,store_id,case_id,kind,status,source_file_id,source_digest,source_reference,source_case_version,replacement_batch_id,prepared_by,reviewed_by,confirmed_by,row_count,amount_cents,errors FROM vehicle_import_batches'):
        bid,sid,cid,kind,status,eid,digest,reference,version,replacement,preparer,reviewer,confirmer,count,amount,errors=b;batches+=1
        case=connection.execute('SELECT store_id,kind,flow_version,version FROM flow_cases WHERE id=?',(cid,)).fetchone()
        source=connection.execute('SELECT store_id,case_id,sha256,created_by,category,generated,content FROM flow_files WHERE id=?',(eid,)).fetchone()
        if not case or tuple(case[:3])!=(sid,'vehicle_procurement',2) or version>case[3]:raise ValueError('车辆导入原单或版本范围不一致')
        if not source or (source[0],source[1],source[2],source[4],source[5])!=(sid,cid,digest,'procurement_contract' if kind=='funds' else 'evidence',0):raise ValueError('车辆导入原文件与原单及摘要不一致')
        parsed=None
        if source[6]:
            if hashlib.sha256(source[6]).hexdigest()!=digest:raise ValueError('车辆导入来源文件内容损坏')
            try:parsed=parse(kind,source[6])
            except Exception as exc:raise ValueError('车辆导入来源文件结构不合法') from exc
        rows=list(connection.execute('SELECT id,store_id,row_number,source_row,vin,line_id,manifest_row_id,origin_key,vehicle_key,"values",errors FROM vehicle_import_rows WHERE batch_id=? ORDER BY row_number',(bid,)))
        if len(rows)!=count or [r[2] for r in rows]!=list(range(2,count+2)):raise ValueError('车辆导入清单行数或行号不完整')
        events=[json.loads(r[0]) for r in connection.execute("SELECT detail FROM flow_events WHERE case_id=? AND store_id=? AND actor_id=? AND action='vi_prepare'",(cid,sid,preparer))]
        record=next((v for v in events if v.get('batch_id')==bid),None)
        frozen=[{'number':r[2],'values':json.loads(r[9])} for r in rows]
        if not record or record.get('source_digest')!=digest or record.get('rows_digest')!=_key(digest,frozen):raise ValueError('车辆导入冻结行与原登记摘要不一致')
        if status in {'reviewed','confirmed'} and (not reviewer or reviewer==preparer):raise ValueError('车辆导入缺少独立主管复核')
        if status=='confirmed' and confirmer!=preparer:raise ValueError('车辆导入须由原编制人确认自己的实际动作')
        if status!='confirmed' and confirmer is not None:raise ValueError('未执行导入批次不能记录执行人')
        for action,actor,required in [('trial',preparer,status in {'trial_passed','reviewed','confirmed'}),('review',reviewer,status in {'reviewed','confirmed'}),('confirm',confirmer,status=='confirmed')]:
            if required:
                proof=[json.loads(r[0]) for r in connection.execute('SELECT detail FROM flow_events WHERE case_id=? AND store_id=? AND actor_id=? AND action=?',(cid,sid,actor,'vi_'+action))]
                if not any(p.get('batch_id')==bid and p.get('kind')==kind for p in proof):raise ValueError('车辆导入核验与本人办理记录不一致')
        if replacement:
            old=connection.execute('SELECT store_id,case_id,kind,status FROM vehicle_import_batches WHERE id=?',(replacement,)).fetchone()
            if not old or tuple(old)!=(sid,cid,kind,'cancelled') or replacement>=bid:raise ValueError('车辆导入替代链不合法')
        computed=0;row_errors=[]
        for offset,r in enumerate(rows):
            rid,rsid,number,source_row,vin,line,manifest,origin,vehicle,values,rerrors=r;v=json.loads(values);err=json.loads(rerrors)
            if rsid!=sid or source_row!=v.get('source_row','') or vin!=v.get('vin',''):raise ValueError('车辆导入行身份与原资料不一致')
            if parsed is not None and (parsed[offset]['values']!=v or parsed[offset]['number']!=number):raise ValueError('车辆导入冻结行与来源文件不一致')
            if origin!=_key(sid,kind,reference,v.get('source_row','invalid-'+str(number))) or vehicle!=_key(sid,cid,kind,v.get('vin','invalid-'+str(number))):raise ValueError('车辆导入重复占用键与来源不一致')
            claims=list(connection.execute('SELECT key,store_id FROM vehicle_import_claims WHERE row_id=?',(rid,)))
            if status in {'invalid','cancelled'}:
                if claims:raise ValueError('未通过或已取消批次不能继续占用来源行')
            elif {(x[0],x[1]) for x in claims}!={(origin,sid),(vehicle,sid)}:raise ValueError('有效车辆导入缺少来源与 VIN 防重复占用')
            if err:row_errors.append({'row_number':number,'errors':err})
            if not err:
                parentline=connection.execute('SELECT case_id,store_id FROM vehicle_purchase_lines WHERE id=?',(line,)).fetchone()
                if not parentline or tuple(parentline)!=(cid,sid):raise ValueError('车辆导入车型行不属于本采购单')
                if kind=='funds':
                    cost=connection.execute('SELECT unit_cost_cents FROM vehicle_purchase_prices WHERE line_id=?',(line,)).fetchone()
                    if not cost or not 0<v['amount_cents']<=cost[0]:raise ValueError('逐 VIN 请款超过原冻结成本')
                    computed+=v['amount_cents']
                else:
                    parent=connection.execute('SELECT r.store_id,b.case_id,b.kind,b.status,r.vin,r.line_id FROM vehicle_import_rows r JOIN vehicle_import_batches b ON b.id=r.batch_id WHERE r.id=?',(manifest,)).fetchone()
                    if not parent or tuple(parent)!=(sid,cid,'funds','confirmed',vin,line):raise ValueError('发运到货清单与原已确认请款 VIN 不一致')
            fact=connection.execute('SELECT store_id,funds_request_id,shipment_id,receipt_id FROM vehicle_import_results WHERE row_id=?',(rid,)).fetchone()
            if status!='confirmed':
                if fact:raise ValueError('未正式确认批次不能留下原单执行结果')
                continue
            if err or not fact or fact[0]!=sid or sum(x is not None for x in fact[1:])!=1:raise ValueError('已确认车辆导入缺少逐行唯一结果')
            results+=1
            if kind=='funds':
                result=connection.execute('SELECT case_id,store_id,amount_cents,evidence_id,requested_by FROM vehicle_purchase_funds_requests WHERE id=?',(fact[1],)).fetchone()
                if not result or tuple(result)!=(cid,sid,v['amount_cents'],eid,preparer) or fact[2] is not None or fact[3] is not None:raise ValueError('导入请款与原单金额及凭据不一致')
            elif kind=='ship':
                result=connection.execute('SELECT case_id,store_id,line_id,vin,shipped_date,expected_date,evidence_id,actor_id FROM vehicle_purchase_shipments WHERE id=?',(fact[2],)).fetchone()
                if not result or tuple(result)!=(cid,sid,line,vin,v['shipped_date'],v['expected_date'],eid,preparer) or fact[1] is not None or fact[3] is not None:raise ValueError('导入发运与原 VIN、日期及凭据不一致')
            else:
                result=connection.execute('SELECT r.case_id,r.store_id,r.location_id,r.business_date,r.evidence_id,r.actor_id,s.vin,s.line_id,r.shipment_id FROM vehicle_purchase_receipts r JOIN vehicle_purchase_shipments s ON s.id=r.shipment_id WHERE r.id=?',(fact[3],)).fetchone()
                original=connection.execute("SELECT f.shipment_id FROM vehicle_import_results f JOIN vehicle_import_rows r ON r.id=f.row_id JOIN vehicle_import_batches b ON b.id=r.batch_id WHERE r.manifest_row_id=? AND b.kind='ship' AND b.status='confirmed'",(manifest,)).fetchone()
                if not result or not original or tuple(result)!=(cid,sid,v['location_id'],v['received_date'],eid,preparer,vin,line,original[0]) or fact[1] is not None or fact[2] is not None:raise ValueError('导入到货与原发运、实际库位及凭据不一致')
        if computed!=amount or row_errors!=json.loads(errors):raise ValueError('车辆导入金额或逐行错误清单与冻结行不一致')
    return {'verified_vehicle_import_batches':batches,'verified_vehicle_import_results':results}
