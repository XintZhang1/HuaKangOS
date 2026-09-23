"""Offline restoration proof for reviewed opening facts; never expose source rows."""
import hashlib, json


def validate_opening_import(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'opening_imports' not in names:return {'verified_opening_imports':0}
    count=0
    def evidence(key,sid,cid,actor,category):
        row=connection.execute('SELECT store_id,case_id,created_by,category,generated FROM flow_files WHERE id=?',(key,)).fetchone()
        if not row or tuple(row)!=(sid,cid,actor,category,0):raise ValueError('期初核验凭据不是该员工本人上传的本店本单来源')
    for control,sid,cid,bid,status in connection.execute('SELECT id,store_id,case_id,batch_id,status FROM opening_imports'):
        batch=connection.execute('SELECT store_id,source_text,source_digest,status,prepared_by,confirmed_store_key,opening_date,totals FROM opening_batches WHERE id=?',(bid,)).fetchone()
        case=connection.execute('SELECT store_id,kind,flow_version,state FROM flow_cases WHERE id=?',(cid,)).fetchone()
        expected_state='completed' if status=='confirmed' else 'cancelled' if status=='cancelled' else 'working' if status=='approved' else 'approval'
        if not batch or batch[0]!=sid or not case or tuple(case)!=(sid,'opening_import',2,expected_state):raise ValueError('期初批次与本店版本化原单不一致')
        if hashlib.sha256(batch[1].encode()).hexdigest()!=batch[2]:raise ValueError('期初原资料摘要不一致')
        source=json.loads(batch[1]);totals=json.loads(batch[7]);accounts=source.get('accounts',[]);vehicles=source.get('vehicles',[]);items=source.get('items',[])
        event=connection.execute("SELECT detail FROM flow_events WHERE case_id=? AND store_id=? AND action='opening_preflight'",(cid,sid)).fetchone()
        prepared=json.loads(event[0]) if event else {}
        if prepared.get('digest')!=batch[2] or len(prepared.get('references',[]))!=len(vehicles):raise ValueError('期初预检缺少冻结的资料摘要和主档关联')
        context=connection.execute('SELECT policy_id,binding_id,revision_id FROM business_entity_case_contexts WHERE case_id=? AND store_id=?',(cid,sid)).fetchone() if 'business_entity_case_contexts' in names else None
        mapping=prepared.get('account_context')
        if context:
            if not mapping or tuple(mapping.get(k) for k in ('policy_id','binding_id','revision_id'))!=tuple(context) or len(mapping.get('accounts',[]))!=len(accounts):raise ValueError('期初账户映射缺少原业务冻结主体与批准来源')
            entity=connection.execute('SELECT entity_id FROM business_entity_revisions WHERE id=?',(context[2],)).fetchone()
            for n,(source_account,frozen) in enumerate(zip(accounts,mapping['accounts']),1):
                approved=connection.execute('SELECT store_id,account_id,account_name,revision_id FROM business_entity_account_bindings WHERE id=?',(frozen.get('account_binding_id'),)).fetchone()
                current=connection.execute('SELECT store_id,name,account_type,version FROM flow_accounts WHERE id=?',(frozen.get('account_id'),)).fetchone()
                owner=connection.execute('SELECT entity_id FROM business_entity_revisions WHERE id=?',(frozen.get('account_revision_id'),)).fetchone()
                if (frozen.get('row'),frozen.get('account_id'),frozen.get('name'),frozen.get('account_type'))!=(n,source_account.get('account_id'),source_account['name'],source_account['account_type']) or not approved or tuple(approved)!=(sid,source_account.get('account_id'),source_account['name'],frozen.get('account_revision_id')) or not current or tuple(current[:3])!=(sid,source_account['name'],source_account['account_type']) or not isinstance(frozen.get('account_version'),int) or not 0<frozen['account_version']<=current[3] or not owner or owner!=entity:raise ValueError('期初账户编号、原版本、批准渠道与冻结主体不一致')
        elif mapping is not None or any('account_id' in a for a in accounts):raise ValueError('旧方式期初不得按账户编号认领既有账户或伪造主体归属')
        expected={'customer_count':len(source.get('customers',[])),'account_count':len(accounts),'item_count':len(items),'stock_row_count':sum(i.get('opening_quantity_milli',0)>0 for i in items),
            'quantity_milli':sum(i.get('opening_quantity_milli',0) for i in items),'inventory_value_cents':sum(i.get('opening_value_cents',0) for i in items),
            'vehicle_count':len(vehicles),'vehicle_value_cents':sum(v['cost_cents'] for v in vehicles),'account_balance_cents':sum(a['opening_balance_cents'] for a in accounts)}
        if totals!=expected:raise ValueError('期初汇总与冻结原资料不一致')
        proofs={}
        for kind,psid,digest,actor,eid,observed in connection.execute('SELECT kind,store_id,source_digest,actor_id,evidence_id,observed FROM opening_attestations WHERE import_id=?',(control,)):
            if psid!=sid or digest!=batch[2]:raise ValueError('期初分岗核验与来源摘要不一致')
            evidence(eid,sid,cid,actor,'receipt' if kind=='finance' else 'evidence');proofs[kind]=(actor,eid,json.loads(observed))
        if 'approve' in proofs and proofs['approve'][0]==batch[4]:raise ValueError('期初准备人与主管审批人必须不同')
        actors=[p[0] for p in proofs.values()]
        if len(set(actors))!=len(actors):raise ValueError('期初主管、财务与库管须分别核验')
        physical=bool(vehicles or expected['stock_row_count']);financial=bool(accounts or physical)
        if 'finance' in proofs and proofs['finance'][2]!={'totals':totals,'accounts':[{'name':a['name'],'opening_balance_cents':a['opening_balance_cents']} for a in accounts]}:raise ValueError('期初财务核验数值与原资料不一致')
        inventory={'vehicles':[{'vin':v['vin'],'location_code':v['location_code']} for v in vehicles],
            'items':[{'sku':i['sku'],'quantity_milli':i['opening_quantity_milli']} for i in items if i.get('opening_quantity_milli',0)]}
        if 'inventory' in proofs and proofs['inventory'][2]!=inventory:raise ValueError('期初实物核验与原VIN、库位和数量不一致')
        account_entries=list(connection.execute('SELECT store_id,row_number,account_id,account_name,amount_cents,business_date,source_reference,evidence_id,actor_id FROM opening_account_entries WHERE import_id=?',(control,)))
        vehicle_entries=list(connection.execute('SELECT store_id,row_number,vehicle_id,identity_id,model_id,location_id,vin,value_cents,business_date,source_reference,evidence_id,actor_id FROM opening_vehicle_entries WHERE import_id=?',(control,)))
        stock=list(connection.execute('SELECT quantity_milli,value_cents,store_id FROM opening_stock_entries WHERE batch_id=?',(bid,)))
        if status!='confirmed':
            if account_entries or vehicle_entries or stock or batch[3]=='confirmed' or batch[5] is not None:raise ValueError('未确认期初批次不能留下账户或库存事实')
            continue
        if batch[3]!='confirmed' or batch[5]!=sid or 'approve' not in proofs or physical and 'inventory' not in proofs or financial and 'finance' not in proofs:raise ValueError('期初正式启用缺少三岗核验或唯一门店确认')
        confirmed=connection.execute("SELECT detail FROM flow_events WHERE case_id=? AND store_id=? AND action='opening_confirm'",(cid,sid)).fetchone()
        objects=json.loads(confirmed[0]).get('objects',{}) if confirmed else {}
        for key,table,expected_count in [('customers','flow_customers',expected['customer_count']),('items','flow_items',expected['item_count'])]:
            identifiers=objects.get(key,[])
            if len(identifiers)!=expected_count or len(set(identifiers))!=expected_count:raise ValueError('期初客户或物资缺少逐行独立创建映射')
            for identifier in identifiers:
                linked=connection.execute('SELECT store_id FROM '+table+' WHERE id=?',(identifier,)).fetchone()
                if not linked or linked[0]!=sid:raise ValueError('期初创建映射指向了错误门店')
        if len(account_entries)!=len(accounts) or len(vehicle_entries)!=len(vehicles) or len(stock)!=expected['stock_row_count']:raise ValueError('期初正式入账行数不完整')
        if sum(s[0] for s in stock)!=expected['quantity_milli'] or sum(s[1] for s in stock)!=expected['inventory_value_cents'] or any(s[2]!=sid for s in stock):raise ValueError('期初物资数量价值与原资料不守恒')
        for esid,n,aid,name,amount,bdate,reference,eid,actor in account_entries:
            row=accounts[n-1];account=connection.execute('SELECT store_id,name,account_type FROM flow_accounts WHERE id=?',(aid,)).fetchone()
            if context and aid!=mapping['accounts'][n-1]['account_id']:raise ValueError('期初余额未记入原先明确批准的实际账户')
            if esid!=sid or not account or tuple(account)!=(sid,name,row['account_type']) or (name,amount,bdate,reference)!=(row['name'],row['opening_balance_cents'],source['opening_date'],row['source_reference']) or (actor,eid)!=proofs['finance'][:2]:raise ValueError('账户期初余额与原始核对表不一致')
            evidence(eid,sid,cid,actor,'receipt')
        for esid,n,vid,identity,model,location,vin,value,bdate,reference,eid,actor in vehicle_entries:
            row=vehicles[n-1];car=connection.execute('SELECT store_id,vin,inventory_generation,purchase_cost_cents,list_price_cents FROM vehicles WHERE id=?',(vid,)).fetchone()
            frozen=prepared['references'][n-1]
            if (model,location)!=(frozen['model_id'],frozen['location_id']):raise ValueError('期初车辆主档或库位被替换为另一份资料')
            typed=connection.execute('SELECT store_id,code FROM master_vehicle_models WHERE id=?',(model,)).fetchone();loc=connection.execute('SELECT store_id,code FROM master_locations WHERE id=?',(location,)).fetchone()
            ident=connection.execute("SELECT kind,canonical_key FROM group_identities WHERE id=?",(identity,)).fetchone();link=connection.execute("SELECT identity_id,store_id FROM group_identity_links WHERE local_kind='vehicle' AND local_id=?",(vid,)).fetchone()
            if esid!=sid or not car or tuple(car)!=(sid,vin,1,value,row['list_price_cents']) or (vin,value,bdate,reference)!=(row['vin'],row['cost_cents'],source['opening_date'],row['source_reference']) or (actor,eid)!=proofs['inventory'][:2]:raise ValueError('期初车辆来源、首代次或原成本不一致')
            # Codes and names remain editable masters; immutable IDs retain the original link.
            if not typed or typed[0]!=sid or not loc or loc[0]!=sid or not ident or tuple(ident)!=('vehicle',vin) or not link or tuple(link)!=(identity,sid):raise ValueError('期初车辆主档、库位和共享身份归属不一致')
            position=connection.execute("SELECT store_id,location_id,quantity,inventory_delta,value_cents,evidence_id,actor_id FROM vehicle_position_entries WHERE vehicle_id=? AND case_id=? AND kind='opening_receive'",(vid,cid)).fetchone()
            if not position or tuple(position)!=(sid,location,1,0,value,eid,actor):raise ValueError('期初车辆缺少对应实际库位记录')
            evidence(eid,sid,cid,actor,'evidence')
        count+=1
    return {'verified_opening_imports':count}
