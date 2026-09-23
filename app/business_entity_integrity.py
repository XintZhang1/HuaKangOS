"""Offline identity/source validation; no inferred legal or historic attribution."""
import hashlib,json


def validate_business_entities(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_entity_applications' not in names:return {'verified_entity_applications':0,'verified_entity_cases':0,'verified_entity_cash':0}
    def rows(table):
        cursor=connection.execute('SELECT * FROM '+table);keys=[c[0] for c in cursor.description]
        return [dict(zip(keys,r)) for r in cursor]
    def keyed(table,key='id'):return {r[key]:r for r in rows(table)}
    def fail(message):raise ValueError('经营主体恢复校验：'+message)
    entities=keyed('business_entities');revisions=keyed('business_entity_revisions');applications=keyed('business_entity_applications')
    cases=keyed('flow_cases');files=keyed('flow_files');submissions=keyed('business_entity_submissions','application_id');decisions=keyed('business_entity_decisions','application_id')
    bindings=keyed('business_entity_store_bindings');accounts=keyed('flow_accounts');channels=keyed('business_entity_account_channels');abindings=keyed('business_entity_account_bindings');policies=keyed('business_entity_policies')
    contexts=keyed('business_entity_case_contexts','case_id');cash_contexts=keyed('business_entity_cash_contexts','cash_id');cash=keyed('cash_entries')
    proposals={kind:keyed(table,'application_id') for kind,table in {'revision':'business_entity_revision_proposals','store_binding':'business_entity_store_proposals','account_binding':'business_entity_account_proposals','policy':'business_entity_policy_proposals'}.items()}
    events={}
    for e in rows('flow_events'):events.setdefault(e['case_id'],[]).append(e)
    def entity(revision_id):return revisions.get(revision_id,{}).get('entity_id')
    for policy in policies.values():
        for source in cases.values():
            if source['store_id']==policy['store_id'] and source['id']>policy['case_cursor'] and source['kind']!='business_entity' and source['id'] not in contexts:fail('策略启用后新业务缺少创建时主体冻结记录')
        for source in cash.values():
            if source['store_id']==policy['store_id'] and source['id']>policy['cash_cursor'] and source['approval_state']=='approved' and source['id'] not in cash_contexts:fail('策略启用后实际现金缺少主体与渠道归属记录')
    for eid,record in entities.items():
        versions=sorted(r['revision'] for r in revisions.values() if r['entity_id']==eid)
        if versions!=list(range(1,record['version']+1)):fail('主体版本不连续或缺失原批准版本')
    for cid,a in applications.items():
        case=cases.get(cid);p=proposals.get(a['operation'],{}).get(cid);s=submissions.get(cid);d=decisions.get(cid)
        if not case or (case['kind'],case['flow_version'],case['store_id'],case['created_by'])!=('business_entity',1,a['store_id'],a['requested_by']) or not p or p['store_id']!=a['store_id']:fail('申请、门店或类型化资料关联不一致')
        original=[e for e in events.get(cid,[]) if e['action']=='entity_create' and e['actor_id']==a['requested_by'] and e['store_id']==a['store_id']]
        if len(original)!=1:fail('申请缺少本人创建事件')
        detail=json.loads(original[0]['detail'])
        if detail.get('operation')!=a['operation'] or detail.get('proposal')!=p or detail.get('reason')!=a['reason']:fail('类型化原资料与不可变申请快照不一致')
        if case['state']=='draft' and (s or d):fail('草稿存在提交或终态批准')
        if case['state']=='approval' and (not s or d):fail('待批申请缺少有效提交或已存在终态')
        if case['state'] in {'completed','cancelled','rejected'} and (not d or d['decision']!={'completed':'approved','cancelled':'cancelled','rejected':'rejected'}[case['state']]):fail('申请终态与独立决议不一致')
        if s:
            f=files.get(s['source_evidence_id'])
            if s['store_id']!=a['store_id'] or s['actor_id']!=a['requested_by'] or not f or (f['store_id'],f['case_id'],f['created_by'],f['generated'])!=(a['store_id'],cid,a['requested_by'],0):fail('提交来源文件不是申请人本店本单实际资料')
        if d:
            if d['store_id']!=a['store_id']:fail('独立决议门店不一致')
            if d['decision'] in {'approved','rejected'} and (not s or d['actor_id']==a['requested_by']):fail('申请与复核不是独立两人')
            if d['decision']=='approved':
                proof=files.get(d['evidence_id'])
                if not proof or (proof['store_id'],proof['case_id'],proof['created_by'],proof['generated'])!=(a['store_id'],cid,d['actor_id'],0):fail('缺少本复核人本单实际核对凭据')
        effects=[r for collection in (revisions,bindings,abindings,policies) for r in collection.values() if r['application_id']==cid]
        if len(effects)!=(1 if d and d['decision']=='approved' else 0):fail('申请批准与实际配置生效记录数量不一致')
        if not effects:continue
        result=effects[0]
        if a['operation']=='revision':
            e=entities.get(result.get('entity_id'));wanted=p['expected_entity_version']+1 if p['entity_id'] else 1
            if result not in revisions.values() or not e or (result['source_store_id'],result['approved_by'],result['source_evidence_id'],result['revision'])!=(a['store_id'],d['actor_id'],s['source_evidence_id'],wanted):fail('主体版本原批准来源不一致')
            if (e['code'],e['tax_identifier'])!=(p['code'],p['tax_identifier']) or any(result[k]!=p[k] for k in ('legal_name','registered_address','contact_phone')):fail('主体批准资料与原申请内容不一致')
        elif a['operation']=='store_binding':
            if result not in bindings.values() or result['store_id']!=a['store_id'] or any(result[k]!=p[k] for k in ('revision_id','effective_from')):fail('门店主体绑定与批准来源不一致')
        elif a['operation']=='account_binding':
            if result not in abindings.values() or result['store_id']!=a['store_id'] or any(result[k]!=p[k] for k in ('account_id','revision_id','effective_from','holder_name','channel_type','channel_identifier','institution_name')):fail('账户批准快照与原申请不一致')
        else:
            if result not in policies.values() or result['store_id']!=a['store_id'] or (result['binding_id'],result['policy_version'])!=(p['binding_id'],1) or result['case_cursor']<cid:fail('策略启用范围与原批准不一致')
    for bid,b in abindings.items():
        a=accounts.get(b['account_id']);c=channels.get(b['channel_id']);r=revisions.get(b['revision_id'])
        if not a or a['store_id']!=b['store_id'] or not c or (c['owner_store_id'],c['account_id'])!=(b['store_id'],b['account_id']) or not r or b['holder_name']!=r['legal_name']:fail('实际资金账户绑定串店或主体户名不一致')
        parts=[b['channel_type'],str(b['store_id']) if b['channel_type']=='cash' else '',b['channel_identifier'].replace(' ','').upper()]
        digest=hashlib.sha256(json.dumps(parts,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if c['digest']!=digest:fail('资金渠道与全局防重复标识不一致')
    for cid,c in contexts.items():
        source=cases.get(cid);p=policies.get(c['policy_id']);b=bindings.get(c['binding_id'])
        if not source or not p or not b or (source['store_id'],p['store_id'],b['store_id'])!=(c['store_id'],)*3 or cid<=p['case_cursor'] or c['revision_id']!=b['revision_id'] or c['actor_id']!=source['created_by']:fail('业务主体不是本店创建时的批准版本，或历史资料被自动补记')
        if b['effective_from']>source['business_date'] or b['approved_at']>c['frozen_at'] or p['approved_at']>c['frozen_at']:fail('业务主体引用了未来生效资料')
        if c.get('source_case_id') is not None:
            parent=contexts.get(c['source_case_id']);kind=c.get('derived_kind');allowed=set()
            if not parent or c['source_case_id']>=cid or parent['store_id']!=c['store_id'] or any(parent[k]!=c[k] for k in ('policy_id','binding_id','revision_id')):fail('派生主体没有完整继承本店原业务冻结版本')
            if kind=='aftercare' and (source['kind'],source['flow_version'])==('aftercare',2):
                r=connection.execute('SELECT source_case_id FROM aftercare_orders WHERE id=? AND store_id=?',(cid,c['store_id'])).fetchone();allowed={r[0]} if r else set()
            elif kind=='invoice' and (source['kind'],source['flow_version'])==('invoice',3):
                r=connection.execute('SELECT source_case_id,original_case_id FROM invoice_applications WHERE id=? AND store_id=?',(cid,c['store_id'])).fetchone();allowed={r[1] or r[0]} if r else set()
            elif kind=='claim' and (source['kind'],source['flow_version'])==('claim',2):
                r=connection.execute('SELECT source_case_id FROM claims_orders WHERE id=? AND store_id=?',(cid,c['store_id'])).fetchone();allowed={r[0]} if r else set()
            elif kind=='membership_refund' and (source['kind'],source['flow_version'])==('membership',2):
                order=connection.execute('SELECT purpose,"values" FROM membership_orders WHERE case_id=? AND store_id=?',(cid,c['store_id'])).fetchone()
                values=json.loads(order[1]) if order else {}
                period=connection.execute('SELECT case_id FROM membership_periods WHERE id=? AND store_id=?',(values.get('period_id'),c['store_id'])).fetchone() if order and order[0]=='renew_refund' else None
                allowed={period[0]} if period else set()
            elif kind=='vehicle_return' and (source['kind'],source['flow_version'])==('vehicle_operations',2):
                r=connection.execute('SELECT kind,original_operation_id,aftercare_case_id,source_order_id FROM vehicle_operations WHERE id=? AND store_id=?',(cid,c['store_id'])).fetchone()
                allowed={r[1]} if r and r[0]=='other_return' else {r[2],r[3]} if r and r[0]=='customer_return' else set()
            elif kind=='vehicle_income' and (source['kind'],source['flow_version'])==('vehicle_income',1):
                if not {'vehicle_income_orders','vehicle_income_sources'}<=names:fail('整车其他收入缺少原来源表')
                order=connection.execute('SELECT primary_source_case_id FROM vehicle_income_orders WHERE id=? AND store_id=?',(cid,c['store_id'])).fetchone()
                if not order or order[0]!=c['source_case_id']:fail('整车其他收入主体不属于原主来源')
                allowed={r[0] for r in connection.execute('SELECT source_case_id FROM vehicle_income_sources WHERE case_id=? AND store_id=?',(cid,c['store_id']))}
            elif kind in {'advance_refund','finance_correction','other_return'} and (source['kind'],source['flow_version'])==('business_finance',2):
                r=connection.execute('SELECT purpose,"values" FROM business_finance_orders WHERE case_id=? AND store_id=?',(cid,c['store_id'])).fetchone();v=json.loads(r[1]) if r else {}
                if r and r[0]=='advance_refund' and kind=='advance_refund':
                    a=connection.execute('SELECT case_id FROM business_finance_advances WHERE id=? AND store_id=?',(v.get('advance_id'),c['store_id'])).fetchone();allowed={a[0]} if a else set()
                elif r and r[0] in {'correction','stored_correction','fee_correction'} and kind=='finance_correction':
                    a=cash_contexts.get(v.get('original_cash_id'));allowed={a['case_id']} if a else set()
                elif r and r[0]=='other_return' and kind=='other_return':
                    a=connection.execute('SELECT case_id FROM flow_stock_moves WHERE id=? AND store_id=?',(v.get('stock_move_id'),c['store_id'])).fetchone();allowed={a[0]} if a else set()
                elif r and r[0] in {'other_return_adjust','other_return_refund'} and kind=='other_return':
                    a=connection.execute('SELECT case_id FROM business_finance_return_receivables WHERE id=? AND store_id=?',(v.get('receivable_id'),c['store_id'])).fetchone();allowed={a[0]} if a else set()
            if c['source_case_id'] not in allowed or None in allowed:fail('派生主体与实际原单关系不一致，不能借用旧主体')
            for related in allowed:
                if related not in contexts or entity(contexts[related]['revision_id'])!=entity(c['revision_id']):fail('派生的多个责任来源不是同一主体')
        elif c.get('derived_kind') is not None:fail('派生用途缺少原单主体引用')
        if source['kind']=='aftercare':
            for related in connection.execute('SELECT source_case_id FROM aftercare_sources WHERE case_id=? AND store_id=?',(cid,c['store_id'])):
                if related[0] not in contexts or entity(contexts[related[0]]['revision_id'])!=entity(c['revision_id']):fail('售后多个原业务的经营主体不一致')
        if source['kind']=='invoice' and source['flow_version']==3:
            invoice=connection.execute('SELECT issuer_name,issuer_tax_id FROM invoice_applications WHERE id=? AND store_id=?',(cid,c['store_id'])).fetchone();revision=revisions[c['revision_id']]
            if not invoice or tuple(invoice)!=(revision['legal_name'],entities[revision['entity_id']]['tax_identifier']):fail('发票销售方与原业务冻结主体不一致')
        keys=('经营主体法定名称','主体识别号','登记地址','主体资料版本编号');revision=revisions[c['revision_id']]
        expected=(revision['legal_name'],entities[revision['entity_id']]['tax_identifier'],revision['registered_address'],revision['id'])
        for f in files.values():
            if f['case_id']!=cid or not f['generated']:continue
            snapshot=json.loads(f['snapshot']) if isinstance(f['snapshot'],str) else f['snapshot']
            if f['store_id']!=c['store_id'] or not isinstance(snapshot,dict) or tuple(snapshot.get(k) for k in keys)!=expected:fail('正式文档快照缺少或改变了原业务冻结主体四项资料')
        coordination=[e for e in events.get(cid,[]) if e['action']=='entity_coordinated_freeze']
        if coordination:
            if len(coordination)!=1 or coordination[0]['actor_id']!=c['actor_id'] or coordination[0]['store_id']!=c['store_id']:fail('协调主体冻结事件不唯一或经办来源不一致')
            v=json.loads(coordination[0]['detail']);contracts={'material_transfer':('material_transfers','from_store_id','to_store_id','from_case_id','to_case_id'),
                'vehicle_transfer':('vehicle_transfers','from_store_id','to_store_id','from_case_id','to_case_id'),
                'interstore_clearing':('interstore_clearing_orders','payer_store_id','receiver_store_id','payer_case_id','receiver_case_id')}
            contract=contracts.get(v.get('source_kind'))
            if not contract or source['kind']!=v['source_kind']:fail('协调主体来源类型错误')
            table,left,right,lc,rc=contract;q=connection.execute('SELECT '+','.join((left,right,lc,rc,'requested_by'))+' FROM '+table+' WHERE id=?',(v.get('source_id'),)).fetchone()
            if not q or q[0]!=v.get('initiating_store_id') or q[4]!=c['actor_id'] or (c['store_id'],cid) not in ((q[0],q[2]),(q[1],q[3])):fail('协调主体来源不是固定双方原单')
    for cid,c in cash_contexts.items():
        source=cash.get(cid);parent=contexts.get(c['case_id']);b=abindings.get(c['account_binding_id']);p=policies.get(parent['policy_id']) if parent else None
        if not source or not parent or not b or not p or (source['store_id'],parent['store_id'],b['store_id'])!=(c['store_id'],)*3 or cid<=p['cash_cursor']:fail('资金原账串店、缺原业务或自动补记历史')
        if source['approval_state']!='approved' or source['created_by']!=c['actor_id'] or source['account']!=b['account_name'] or entity(parent['revision_id'])!=entity(b['revision_id']):fail('实际资金渠道与原业务主体不一致')
        if c['original_cash_id']:
            original=cash_contexts.get(c['original_cash_id']);original_source=cash.get(c['original_cash_id']);original_binding=abindings.get(original['account_binding_id']) if original else None
            if not original or not original_source or not original_binding or c['original_cash_id']>=cid or original_binding['account_id']!=b['account_id'] or entity(original_binding['revision_id'])!=entity(b['revision_id']) or original_source['direction']==source['direction'] or original_source['business_date']>source['business_date']:fail('原路资金反向链与原主体及账户不一致')
    return {'verified_entity_applications':len(applications),'verified_entity_cases':len(contexts),'verified_entity_cash':len(cash_contexts)}
