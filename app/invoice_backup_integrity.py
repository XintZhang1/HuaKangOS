"""Check restored invoice facts without inferring real-world tax validity."""
import json

def validate_invoices_sqlite(connection):
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'invoice_applications' not in tables:return {'verified_invoices':0}
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);columns=[r[0] for r in cursor.description]
        return [dict(zip(columns,r)) for r in cursor]
    applications={r['id']:r for r in rows('invoice_applications')};cases={r['id']:r for r in rows('flow_cases')}
    files={r['id']:r for r in rows('flow_files')};approvals={r['case_id']:r for r in rows('invoice_approvals')}
    results={r['case_id']:r for r in rows('invoice_results')};events=rows('flow_events')
    commissions={r['id']:r for r in rows('insurance_commissions')} if 'insurance_commissions' in tables else {}
    commission_reviews={r['confirmation_id']:r for r in rows('insurance_commission_reviews')} if 'insurance_commission_reviews' in tables else {}
    insurance_quotes={r['id']:r for r in rows('insurance_quotes')} if 'insurance_quotes' in tables else {}
    vehicle_incomes={r['id']:r for r in rows('vehicle_income_orders')} if 'vehicle_income_orders' in tables else {}
    vehicle_revisions={r['id']:r for r in rows('vehicle_income_revisions')} if 'vehicle_income_revisions' in tables else {}
    vehicle_decisions={r['revision_id']:r for r in rows('vehicle_income_decisions')} if 'vehicle_income_decisions' in tables else {}
    def proof(file_id,case,category=None):
        file=files.get(file_id)
        return file and file['case_id']==case['id'] and file['store_id']==case['store_id'] and not file['generated'] and (category is None or file['category']==category)
    for key,a in applications.items():
        case=cases.get(key);source=cases.get(a['source_case_id'])
        if not case or case['kind']!='invoice' or case['flow_version']!=3 or case['store_id']!=a['store_id'] or case['parent_id']!=a['source_case_id'] or case['amount_cents']!=a['amount_cents'] or not source or source['store_id']!=a['store_id']:
            raise ValueError('发票申请与门店原业务或冻结金额不一致')
        if source['kind']=='insurance':
            creation=[e for e in events if e['case_id']==key and e['action']=='invoice_v3_create']
            detail=json.loads(creation[0]['detail']) if len(creation)==1 else {}
            basis=detail.get('source_basis') or {}
            confirmed=commissions.get(basis.get('confirmation_id'));review=commission_reviews.get(basis.get('confirmation_id'))
            quote=insurance_quotes.get(basis.get('quote_id'))
            if (source['flow_version']!=3 or not confirmed or not review or not quote
                or confirmed['case_id']!=source['id'] or quote['case_id']!=source['id']
                or confirmed['store_id']!=a['store_id'] or review['store_id']!=a['store_id'] or quote['store_id']!=a['store_id']
                or review['decision']!='approved' or review['actor_id']==confirmed['actor_id']
                or detail.get('source_case_id')!=source['id'] or detail.get('direction')!=a['direction']
                or basis!={'kind':'insurance_commission','label':'保险公司已独立确认佣金',
                    'confirmation_id':confirmed['id'],'confirmed_cents':confirmed['target_cents'],
                    'quote_id':quote['id'],'insurer_id':quote['insurer_id'],
                    'buyer_name':json.loads(quote['insurer_snapshot'])['name'],'pending_confirmation':False}
                or a['buyer_name']!=basis.get('buyer_name') or not a['buyer_tax_id']
                or a['amount_cents']>confirmed['target_cents'] and a['direction']=='blue'
                or review['created_at']>creation[0]['occurred_at']):
                raise ValueError('保险佣金发票缺少原实际佣金确认、保险公司抬头或冻结依据')
        if source['kind']=='vehicle_income':
            creation=[e for e in events if e['case_id']==key and e['action']=='invoice_v3_create']
            detail=json.loads(creation[0]['detail']) if len(creation)==1 else {}
            basis=detail.get('source_basis') or {}
            order=vehicle_incomes.get(source['id']);revision=vehicle_revisions.get(basis.get('revision_id'))
            decision=vehicle_decisions.get(basis.get('revision_id'))
            supplier=json.loads(order['supplier_snapshot']) if order else {}
            if (source['flow_version']!=1 or not order or not revision or not decision
                or any(r['store_id']!=a['store_id'] for r in (order,revision,decision))
                or revision['case_id']!=source['id'] or decision['decision']!='approved'
                or decision['actor_id'] in {revision['actor_id'],source['created_by']}
                or detail.get('source_case_id')!=source['id'] or detail.get('direction')!=a['direction']
                or revision['invoice_mode']!='store_invoice'
                or basis!={'kind':'vehicle_income','label':'厂家及供应商已独立确认整车其他收入',
                    'revision_id':revision['id'],'digest':revision['digest'],'confirmed_cents':revision['target_cents'],
                    'invoice_mode':revision['invoice_mode'],'buyer_name':supplier.get('name'),
                    'buyer_tax_id':supplier.get('tax_identifier'),'supplier_id':order['supplier_id'],'pending_revision':False}
                or not a['buyer_tax_id'] or (a['buyer_name'],a['buyer_tax_id'])!=(basis.get('buyer_name'),basis.get('buyer_tax_id'))
                or a['direction']=='blue' and a['amount_cents']>revision['target_cents']
                or decision['created_at']>creation[0]['occurred_at']):
                raise ValueError('整车收入发票缺少原批准应收版本、门店开票约定或往来单位冻结抬头')
        if a['direction']=='red':
            original=applications.get(a['original_case_id'])
            if not original or original['direction']!='blue' or original['id'] not in results or any(a[k]!=original[k] for k in ('store_id','source_case_id','issuer_name','issuer_tax_id','buyer_name','buyer_tax_id')):
                raise ValueError('冲红的原蓝票或经营主体不一致')
            if source['kind'] in {'insurance','vehicle_income'}:
                original_events=[e for e in events if e['case_id']==original['id'] and e['action']=='invoice_v3_create']
                original_basis=json.loads(original_events[0]['detail']).get('source_basis') if len(original_events)==1 else None
                if basis!=original_basis:raise ValueError('冲红没有沿用原蓝票冻结的收入依据')
        approval=approvals.get(key)
        if approval and (approval['actor_id']==case['created_by'] or approval['store_id']!=a['store_id'] or not proof(approval['evidence_id'],case)):
            raise ValueError('开票独立审批或原单凭据不一致')
        result=results.get(key)
        if (case['state'] in {'completed','resolving'} and not result) or (case['state'] in {'pending','working','completed','resolving'} and not approval):
            raise ValueError('开票办理状态缺少实际票据或独立批准')
        if result:
            if not approval or case['state'] not in {'completed','resolving'} or result['store_id']!=a['store_id'] or result['issuer_tax_id']!=a['issuer_tax_id'] or not proof(result['evidence_id'],case,'invoice'):
                raise ValueError('实际发票与批准、门店或原票据文件不一致')
            facts=[e for e in events if e['case_id']==key and e['action']=='invoice_v3_record']
            if len(facts)!=1:raise ValueError('实际发票缺少唯一经办事件')
            details=json.loads(facts[0]['detail'])
            if facts[0]['actor_id']!=result['actor_id'] or any(details.get(k)!=result[k] for k in ('invoice_number','issued_on','amount_cents','evidence_id')):
                raise ValueError('实际发票结果与不可变事件不一致')
    for key,a in applications.items():
        if a['direction']!='blue' or key not in results:continue
        used=sum(results[r['id']]['amount_cents'] if r['id'] in results else r['amount_cents'] if cases[r['id']]['state'] not in {'cancelled','rejected'} else 0 for r in applications.values() if r['original_case_id']==key)
        if used>results[key]['amount_cents']:raise ValueError('原票冲红及待冲占用超过实际蓝票金额')
    return {'verified_invoices':len(results)}
