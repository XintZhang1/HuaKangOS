"""Read-only offline statement and original cash/clearing checks."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import hashlib,json


def validate_reconciliation_sqlite(connection):
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'reconciliation_batches','reconciliation_issues','interstore_clearing_buckets','interstore_clearing_orders',
        'interstore_clearing_cash','interstore_clearing_offsets','reconciliation_events','reconciliation_receipts'}
    if not required.intersection(tables):return {'verified_reconciliation_batches':0,'verified_clearing_orders':0}
    if not required<=tables:raise ValueError('对账与清算表不完整')
    def rows(name):
        c=connection.execute('SELECT * FROM '+name);keys=[d[0] for d in c.description];return [dict(zip(keys,r)) for r in c]
    def keyed(name,key='id'):return {r[key]:r for r in rows(name)}
    cases=keyed('flow_cases');files=keyed('flow_files');batches=keyed('reconciliation_batches');issues=rows('reconciliation_issues');events=rows('reconciliation_events')
    origins={'material':keyed('material_transfer_settlements'),'vehicle':keyed('vehicle_transfer_settlements')}
    origins['material_loss']=keyed('transfer_loss_settlements') if 'transfer_loss_settlements' in tables else {}
    origins['material_found']=keyed('transfer_goods_settlements') if 'transfer_goods_settlements' in tables else {}
    origins['vehicle_loss']=keyed('vehicle_transport_loss_settlements') if 'vehicle_transport_loss_settlements' in tables else {}
    origins['vehicle_found']=keyed('vehicle_transport_found_settlements') if 'vehicle_transport_found_settlements' in tables else {}
    goods=keyed('transfer_goods_recoveries') if 'transfer_goods_recoveries' in tables else {}
    goods_postings=keyed('transfer_goods_postings') if 'transfer_goods_postings' in tables else {}
    buckets=keyed('interstore_clearing_buckets');orders=keyed('interstore_clearing_orders');cash=keyed('cash_entries');accounts=keyed('flow_accounts')
    postings=rows('interstore_clearing_cash');offsets=rows('interstore_clearing_offsets')
    points_debts=keyed('membership_points_debts') if 'membership_points_debts' in tables else {}
    points_changes=keyed('membership_points_changes') if 'membership_points_changes' in tables else {}
    partial_cases={r['case_id'] for r in rows('business_finance_correction_bases')} if 'business_finance_correction_bases' in tables else set()
    partial_batches={r['id'] for r in rows('business_finance_cash_batches') if r['case_id'] in partial_cases} if 'business_finance_cash_batches' in tables else set()
    frozen_fields={
        'opening_account_entries':('import_id','account_id','account_name','amount_cents','business_date','evidence_id','actor_id'),
        'opening_vehicle_entries':('import_id','vehicle_id','identity_id','model_id','location_id','vin','value_cents','business_date','evidence_id','actor_id'),
        'private_file_objects':('file_id','object_key','sha256','size'),
        'recharge_bundle_purchases':('case_id','member_id','rule_id','shares','principal_entry_id','evidence_id','actor_id'),
        'recharge_bundle_components':('purchase_id','rule_component_id','wallet_id','grant_entry_id'),
        'recharge_bundle_refund_components':('refund_id','component_id','units'),
        'recharge_bundle_refund_postings':('refund_component_id','benefit_entry_id')}
    frozen_fields.update({
        'claims_orders':('source_case_id','party_type','payment_route','insurer_id','manufacturer_id'),
        'claims_assessments':('case_id','revision','quote_id','quote_digest','amount_cents','actor_id'),
        'claims_approvals':('assessment_id','evidence_id','actor_id'),
        'claims_transmissions':('case_id','assessment_id','supplement_result_id','external_reference','submitted_on','evidence_id','actor_id'),
        'claims_results':('case_id','assessment_id','transmission_id','outcome','amount_cents','result_on','evidence_id','actor_id'),
        'claims_bindings':('case_id','allocation_id','assessment_id','result_id','approved_cents'),
        'claims_resolutions':('case_id','allocation_id','result_id','original_cents','reduction_cents','refund_cents','internal_bearer','evidence_id','actor_id'),
        'claims_resolution_approvals':('resolution_id','evidence_id','actor_id'),
        'claims_applications':('resolution_id','business_date','evidence_id','actor_id'),
        'claims_responsibility_entries':('application_id','source_case_id','allocation_id','payer_type','payer_name','amount_cents'),
        'claims_reimbursement_approvals':('case_id','result_id','amount_cents','evidence_id','actor_id'),
        'claims_cash':('case_id','purpose','payment_link_id','resolution_id','original_id','return_plan_id','evidence_id','actor_id'),
        'claims_customer_payments':('case_id','amount_cents','purpose','original_id','return_plan_id','business_date','evidence_id','actor_id'),
        'claims_return_plans':('case_id','amount_cents','evidence_id','actor_id'),
        'claims_return_approvals':('plan_id','evidence_id','actor_id'),
        'claims_return_cancellations':('plan_id','evidence_id','actor_id'),
        'claims_closures':('case_id','unused_cents','evidence_id','actor_id'),
        'vehicle_import_rows':('batch_id','row_number','source_row','vin','line_id','manifest_row_id','origin_key','vehicle_key'),
        'vehicle_import_results':('row_id','funds_request_id','shipment_id','receipt_id'),
        'retail_bundle_rules':('code','rule_version','name','enabled','sale_starts_on','sale_ends_on','price_cents_per_set','refund_terms','created_by'),
        'retail_bundle_components':('rule_id','sequence','item_id','sku','name','unit','quantity_milli_per_set','goods_reference_cents','work_item_id','work_code','work_name','installation_reference_cents','goods_cents_per_set','installation_cents_per_set'),
        'retail_bundle_sales':('case_id','rule_id','sets','terms_accepted','actor_id'),
        'retail_bundle_allocations':('sale_id','component_id','line_id','quantity_milli','goods_reference_cents','installation_reference_cents','goods_cents','installation_cents')})
    frozen_fields.update({'service_orders': ('subtype', 'source_order_id', 'delivery_blocking', 'customer_name', 'vehicle_snapshot', 'reason', 'created_by'), 'service_quotes': ('case_id', 'revision', 'fee_cents', 'pass_cents', 'discount_cents', 'digest', 'reason', 'actor_id'), 'service_lines': ('quote_id', 'line_key', 'bucket', 'agency_project_id', 'income_item_id', 'payee_id', 'code', 'name', 'unit', 'payee_snapshot', 'quantity_milli', 'unit_price_cents', 'discount_cents', 'amount_cents', 'due_date'), 'service_price_approvals': ('quote_id', 'minimum_fee_cents', 'allow_below_minimum', 'reason', 'evidence_id', 'actor_id'), 'service_authorizations': ('quote_id', 'evidence_id', 'actor_id'), 'service_quote_cancellations': ('quote_id', 'reason', 'actor_id'), 'service_submissions': ('case_id', 'quote_id', 'line_key', 'supplement_result_id', 'external_reference', 'submitted_on', 'evidence_id', 'actor_id'), 'service_external_results': ('submission_id', 'outcome', 'result', 'business_date', 'evidence_id', 'actor_id'), 'service_fulfillments': ('case_id', 'line_id', 'line_key', 'amount_cents', 'business_date', 'result', 'evidence_id', 'actor_id'), 'service_tender_slices': ('case_id', 'line_id', 'line_key', 'bucket', 'amount_cents', 'payment_link_id', 'credit_link_id', 'original_id', 'evidence_id', 'actor_id'), 'service_pass_entries': ('case_id', 'line_id', 'line_key', 'purpose', 'amount_cents', 'tender_id', 'original_id', 'cash_id', 'account_id', 'reference', 'evidence_id', 'business_date', 'actor_id'), 'service_terminations': ('case_id', 'quote_id', 'revision', 'lines', 'returns', 'digest', 'reason', 'evidence_id', 'actor_id'), 'service_termination_approvals': ('plan_id', 'evidence_id', 'actor_id'), 'service_termination_consents': ('plan_id', 'evidence_id', 'actor_id'), 'service_termination_cancellations': ('plan_id', 'reason', 'actor_id'), 'service_termination_applications': ('plan_id', 'evidence_id', 'business_date', 'actor_id'), 'service_charge_adjustments': ('application_id', 'case_id', 'line_id', 'line_key', 'bucket', 'amount_cents'), 'service_refunds': ('plan_id', 'original_tender_id', 'reversal_tender_id', 'amount_cents', 'evidence_id', 'actor_id'), 'sales_quotes': ('case_id', 'revision', 'prior_id', 'model_id', 'model_snapshot', 'amount_cents', 'delivery_due', 'valid_until', 'services', 'terms', 'reason', 'digest', 'actor_id'), 'sales_quote_reviews': ('quote_id', 'decision', 'reason', 'actor_id'), 'sales_quote_resolutions': ('quote_id', 'outcome', 'reason', 'actor_id'), 'sales_quote_consents': ('quote_id', 'vehicle_id', 'evidence_id', 'source_file_id', 'fingerprint', 'paid_before_cents', 'advance_before_cents', 'actor_id'), 'sales_vehicle_releases': ('case_id', 'quote_id', 'vehicle_id', 'evidence_id', 'reason', 'actor_id'), 'sales_quote_adjustments': ('quote_id', 'kind', 'payment_id', 'credit_id', 'amount_cents', 'evidence_id', 'actor_id')})
    json_fields={'service_orders': ('vehicle_snapshot',), 'service_quotes': (), 'service_lines': ('payee_snapshot',), 'service_price_approvals': (), 'service_authorizations': (), 'service_quote_cancellations': (), 'service_submissions': (), 'service_external_results': (), 'service_fulfillments': (), 'service_tender_slices': (), 'service_pass_entries': (), 'service_terminations': ('lines', 'returns'), 'service_termination_approvals': (), 'service_termination_consents': (), 'service_termination_cancellations': (), 'service_termination_applications': (), 'service_charge_adjustments': (), 'service_refunds': (), 'sales_quotes': ('model_snapshot', 'services'), 'sales_quote_reviews': (), 'sales_quote_resolutions': (), 'sales_quote_consents': (), 'sales_vehicle_releases': (), 'sales_quote_adjustments': ()}
    from .reconciliation_v7 import FROZEN_FIELDS,JSON_FIELDS
    frozen_fields.update(FROZEN_FIELDS);json_fields.update(JSON_FIELDS)
    from .reconciliation_v8 import FROZEN_FIELDS as V8_FIELDS,JSON_FIELDS as V8_JSON
    frozen_fields.update(V8_FIELDS);json_fields.update(V8_JSON)
    from .reconciliation_v9 import FROZEN_FIELDS as V9_FIELDS
    frozen_fields.update(V9_FIELDS)
    from .reconciliation_v10 import FROZEN_FIELDS as V10_FIELDS
    frozen_fields.update(V10_FIELDS)
    from .reconciliation_v11 import FROZEN_FIELDS as V11_FIELDS
    frozen_fields.update(V11_FIELDS)
    from .reconciliation_v12 import FROZEN_FIELDS as V12_FIELDS,JSON_FIELDS as V12_JSON,DATETIME_FIELDS as V12_DATES
    frozen_fields.update(V12_FIELDS);json_fields.update(V12_JSON)
    from .reconciliation_v13 import FROZEN_FIELDS as V13_FIELDS,JSON_FIELDS as V13_JSON,DATETIME_FIELDS as V13_DATES
    frozen_fields.update(V13_FIELDS);json_fields.update(V13_JSON)
    from .reconciliation_v14 import FROZEN_FIELDS as V14_FIELDS,DATETIME_FIELDS as V14_DATES
    frozen_fields.update(V14_FIELDS)
    from .reconciliation_v15 import FROZEN_FIELDS as V15_FIELDS,JSON_FIELDS as V15_JSON,DATETIME_FIELDS as V15_DATES
    frozen_fields.update(V15_FIELDS);json_fields.update(V15_JSON)
    from .rework_extension_sources import FROZEN_FIELDS as V16_FIELDS,DATETIME_FIELDS as V16_DATES,SOURCE_KEYS as V16_KEYS
    frozen_fields.update(V16_FIELDS)
    from .reconciliation_v17 import FROZEN_FIELDS as V17_FIELDS,DATETIME_FIELDS as V17_DATES
    frozen_fields.update(V17_FIELDS)
    from .reconciliation_v18 import FROZEN_FIELDS as V18_FIELDS,DATETIME_FIELDS as V18_DATES,JSON_FIELDS as V18_JSON
    frozen_fields.update(V18_FIELDS);json_fields.update(V18_JSON)
    from .reconciliation_v19 import FROZEN_FIELDS as V19_FIELDS,DATETIME_FIELDS as V19_DATES,JSON_FIELDS as V19_JSON
    frozen_fields.update(V19_FIELDS);json_fields.update(V19_JSON)
    from .reconciliation_v20 import FROZEN_FIELDS as V20_FIELDS,DATETIME_FIELDS as V20_DATES
    frozen_fields.update(V20_FIELDS)
    from .reconciliation_v21 import FROZEN_FIELDS as V21_FIELDS,DATETIME_FIELDS as V21_DATES
    frozen_fields.update(V21_FIELDS)
    frozen_rows={name:keyed(name,V16_KEYS.get(name,'id')) for name in frozen_fields if name in tables}
    for name,fields in (V12_DATES|V13_DATES|V14_DATES|V15_DATES|V16_DATES|V17_DATES|V18_DATES|V19_DATES|V20_DATES|V21_DATES).items():
        from .vehicle_transport_rules import timestamp
        for row in frozen_rows.get(name,{}).values():
            for field in fields:
                if row.get(field) is not None:row[field]=timestamp(row[field]).isoformat()
    def casecheck(key,sid,kind):
        c=cases.get(key)
        if not c or c['store_id']!=sid or c['kind']!=kind or c['flow_version']!=2:raise ValueError('对账或清算原单门店不一致')
    def proof(key,sid,cid):
        f=files.get(key)
        if not f or f['store_id']!=sid or f['case_id']!=cid:raise ValueError('对账或清算凭据关联不一致')
    for b in batches.values():
        casecheck(b['case_id'],b['store_id'],'reconciliation')
        manifest=json.loads(b['manifest']);summary=json.loads(b['summary'])
        definition=summary.get('definition_version',1)
        if definition not in {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22}:raise ValueError('冻结对账来源定义版本无效')
        hashed=hashlib.sha256(json.dumps({'manifest':manifest,'summary':summary},sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
        if hashed!=b['digest']:raise ValueError('冻结对账来源摘要不一致')
        if b['previous_id']:
            p=batches.get(b['previous_id'])
            if not p or (p['store_id'],p['start'],p['end'],p['revision']+1)!=(b['store_id'],b['start'],b['end'],b['revision']):raise ValueError('对账版本链不一致')
        elif b['revision']!=1:raise ValueError('初始对账版本无效')
        if len({x['key'] for x in manifest})!=len(manifest):raise ValueError('冻结对账来源重复')
        for entry in manifest:
            data=entry['data'];name=entry['source']
            if definition>=22 and name=='private_file_objects':
                source_file=files.get(data.get('file_id'),{})
                if cases.get(source_file.get('case_id'),{}).get('kind')=='reconciliation':
                    raise ValueError('对账自身凭据不能计入第22版业务来源')
            if definition<20 and ((name in {'business_finance_corrections','business_finance_cash_batches'} and data.get('case_id') in partial_cases)
                                  or (name=='business_finance_cash_allocations' and data.get('batch_id') in partial_batches)):
                raise ValueError('旧对账不能将已退款原款切片更正解释为全额分配更正')
            if name.startswith(('procurement_prepayment_','business_finance_stored_','business_finance_supplier_')) and name not in (V13_FIELDS|V14_FIELDS):
                raise ValueError('更正、预付款或供应方原退来源不属于已冻结定义')
            if name in V13_FIELDS and definition<13:raise ValueError('旧对账不能静默扩充原款更正与采购预付款来源')
            if name in V14_FIELDS and definition<14:raise ValueError('旧对账不能静默扩充供应方超收原退来源')
            if name.startswith('vehicle_income_') and (name not in V15_FIELDS or definition<15):raise ValueError('旧对账不能扩充整车其他收入，或来源不属于冻结定义')
            if name.startswith('rework_') and (name not in V16_FIELDS or definition<16):raise ValueError('旧对账不能扩充返修原责任，中央授权不能混入本店来源')
            if name.startswith('business_finance_bundle_') and (name not in V17_FIELDS or definition<17):raise ValueError('旧对账不能扩充原充值组合更正，或来源不属于冻结定义')
            if name.startswith('member_pricing_') and (name not in V18_FIELDS or definition<18):raise ValueError('旧对账不能扩充会员价格，或来源不属于冻结定义')
            if name.startswith('repair_package_') and (name not in V19_FIELDS or definition<19):raise ValueError('旧对账不能扩充混合维修套餐，中央合同不能混入本店冻结来源')
            if name.startswith('business_finance_correction_') and (name not in V20_FIELDS or definition<20):raise ValueError('旧对账不能扩充已退款更正切片，或来源不属于冻结定义')
            if name.startswith(('membership_fee_correction','membership_fee_refund_')) and (name not in V21_FIELDS or definition<21):raise ValueError('旧对账不能扩充续会费登记更正，或来源不属于冻结定义')
            if name.startswith('vehicle_transport_') and (name not in V12_FIELDS or definition<12):raise ValueError('旧对账不能静默扩充原车运输差异，或来源不属于冻结定义')
            if name.startswith('transfer_goods_') and not ((name in V9_FIELDS and definition>=9) or (name in V11_FIELDS and definition>=11)):
                raise ValueError('旧版对账不能扩充找回来源，或找回来源未在冻结定义中')
            if name.startswith('retail_group_') and (name not in V10_FIELDS or definition<10):
                raise ValueError('旧版对账不能扩充精品集团来源，或来源未在冻结定义中')
            if name in V8_FIELDS and definition<8:raise ValueError('旧版对账不能静默扩充运输差异来源')
            if entry['key']!=name+':'+str(entry['source_id']):raise ValueError('冻结对账来源编号不一致')
            if name in {'invoice_corrections','membership_points_debts'}:
                case=cases.get(entry['case_id']);values=data.get('values',[])
                if (definition not in {2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22} or type(entry['source_id']) is not int or entry['source_id']<0 or entry['basis']!='current'
                    or not case or data.get('route')!={'type':'case','id':entry['case_id']} or not values or values[0]!=case['number']):
                    raise ValueError('冻结派生核对来源或原单不一致')
                if name=='invoice_corrections':
                    if case['kind'] not in ({'order','repair','addon','agency','retail','other_income'}|({'insurance'} if definition>=13 else set())|({'vehicle_income'} if definition>=15 else set())) or len(values)!=5 or type(data.get('amount_cents')) is not int or data['amount_cents']<=0:
                        raise ValueError('冻结发票差额金额无效')
                    try:
                        amounts=[Decimal(str(value))*100 for value in values[2:]]
                        if any(not value.is_finite() or value!=value.to_integral_value() or value<0 for value in amounts) or amounts[2]!=data['amount_cents'] or amounts[1]-amounts[0]!=amounts[2]:
                            raise ValueError('冻结发票差额摘要不一致')
                    except InvalidOperation:raise ValueError('冻结发票差额金额格式无效')
                elif (case['kind'] not in {'repair','retail'} or len(values)!=4 or type(data.get('units')) is not int or type(values[2]) is not int or type(values[3]) is not int
                      or not 0<data['units']==values[3]<=values[2]):
                    raise ValueError('冻结待追回积分摘要不一致')
                elif name=='membership_points_debts':
                    debt=points_debts.get(data.get('debt_id'));change=points_changes.get(debt['change_id']) if debt else None
                    if not debt or not change or debt['units']!=values[2] or (change['case_id'],change['store_id'])!=(entry['case_id'],b['store_id']):
                        raise ValueError('冻结待追回积分原始来源不一致')
            elif name!='receivable':
                if data.get(V16_KEYS.get(name,'id'))!=entry['source_id'] or data.get('store_id')!=b['store_id']:raise ValueError('冻结对账来源门店不一致')
                if entry['case_id']!=data.get('case_id'):raise ValueError('冻结对账原单引用不一致')
            if entry['case_id'] and cases.get(entry['case_id'],{}).get('store_id')!=b['store_id']:raise ValueError('冻结对账原单越店')
            if definition>=4 and name in frozen_fields:
                original=frozen_rows.get(name,{}).get(entry['source_id'])
                if not original or original.get('store_id')!=b['store_id'] or any(data.get(k)!=(json.loads(original[k]) if k in json_fields.get(name,()) and isinstance(original.get(k),str) else original.get(k)) for k in frozen_fields[name]):
                    raise ValueError('冻结业务来源与不可变原始记录不一致')
                if definition>=13 and name in {'addon_quotes','addon_approvals'}:
                    extra={'addon_quotes':('pricing_version','gift_terms'),'addon_approvals':('gift_confirmed',)}[name]
                    for key in extra:
                        value=original.get(key)
                        if key=='gift_terms' and isinstance(value,str):value=json.loads(value)
                        if data.get(key)!=value:raise ValueError('冻结赠送加装价格依据与原报价不一致')

        if definition>=8:
            from .reconciliation_v8 import validate_frozen_summary
            validate_frozen_summary(manifest,summary,b['start'],b['end'])
        if definition>=9:
            from .reconciliation_v9 import validate_frozen_summary as validate_found_summary
            validate_found_summary(manifest,summary,b['start'],b['end'])
        if definition>=10:
            from .reconciliation_v10 import validate_frozen_summary as validate_retail_summary
            validate_retail_summary(manifest,summary,b['start'],b['end'])
        if definition>=11:
            from .reconciliation_v11 import validate_frozen_summary as validate_search_summary
            validate_search_summary(manifest,summary,b['start'],b['end'])
        if definition>=12:
            from .reconciliation_v12 import validate_frozen_summary as validate_vehicle_summary
            validate_vehicle_summary(manifest,summary,b['start'],b['end'])
        if definition>=13:
            from .reconciliation_v13 import validate_frozen_summary as validate_finance_summary
            validate_finance_summary(manifest,summary)
        if definition>=14:
            from .reconciliation_v14 import validate_frozen_summary as validate_supplier_summary
            validate_supplier_summary(manifest,summary)
        if definition>=15:
            from .reconciliation_v15 import validate_frozen_summary as validate_income_summary
            validate_income_summary(manifest,summary,b['start'],b['end'])
        if definition>=16:
            from .rework_extension_sources import validate_frozen_summary as validate_rework_summary
            validate_rework_summary(manifest,summary)
        if definition>=17:
            from .reconciliation_v17 import validate_frozen_summary as validate_bundle_summary
            validate_bundle_summary(manifest,summary)
        if definition>=18:
            from .reconciliation_v18 import validate_frozen_summary as validate_member_price_summary
            validate_member_price_summary(manifest,summary)
        if definition>=19:
            from .reconciliation_v19 import validate_frozen_summary as validate_package_summary
            validate_package_summary(manifest,summary)
        if definition>=20:
            from .reconciliation_v20 import validate_frozen_summary as validate_partial_summary
            validate_partial_summary(manifest,summary)
        if definition>=21:
            from .reconciliation_v21 import validate_frozen_summary as validate_fee_correction_summary
            validate_fee_correction_summary(manifest,summary)
        if sum(x['data']['amount_cents'] for x in manifest if x['source']=='receivable')!=summary['current_receivable_cents']:raise ValueError('冻结应收总额不一致')
        excluded=set()
        if definition>=3:
            batch_facts={x['source_id']:x['data'] for x in manifest if x['source']=='business_finance_cash_batches'}
            corrections=[x['data'] for x in manifest if x['source']=='business_finance_corrections']
            for correction in corrections:
                reverse=batch_facts.get(correction['reversing_batch_id']);corrected=batch_facts.get(correction['corrected_batch_id'])
                if (not reverse or reverse['kind']!='correction_reverse' or reverse['case_id']!=correction['case_id']
                    or (correction['corrected_batch_id'] is not None and (not corrected or corrected['kind']!='correction_record' or corrected['case_id']!=correction['case_id']))):
                    raise ValueError('冻结收款更正的原始批次不一致')
                excluded.update([correction['original_cash_id'],reverse['cash_id']])
            if definition>=13:
                for entry in manifest:
                    if entry['source']=='business_finance_stored_corrections':
                        excluded.update([entry['data']['original_cash_id'],entry['data']['reversing_cash_id']])
            if definition>=21:
                for entry in manifest:
                    if entry['source']=='membership_fee_corrections':
                        excluded.update([entry['data']['original_cash_id'],entry['data']['reversing_cash_id']])
            stored=summary.get('excluded_cash_ids')
            if not isinstance(stored,list) or any(type(i) is not int for i in stored) or sorted(excluded)!=stored:raise ValueError('冻结实际现金排除集合不一致')
            if any(cash.get(i,{}).get('store_id')!=b['store_id'] for i in excluded):raise ValueError('冻结收款更正现金越店')
        for direction,field in [('in','period_cash_in_cents'),('out','period_cash_out_cents')]:
            total=sum(x['data']['amount_cents'] for x in manifest if x['source']=='cash_entries' and x['source_id'] not in excluded and x['data']['direction']==direction and x['data']['category']!='transfer')
            if total!=summary[field]:raise ValueError('冻结现金摘要不一致')
        if b['status']=='sealed' and (b['sealed_by'] in {b['prepared_by'],b['submitted_by']} or b['sealed_by'] is None or b['sealed_at'] is None):raise ValueError('对账独立封存事实不一致')
        if b['status']=='sealed':
            sealed=[e for e in events if e['case_id']==b['case_id'] and e['action']=='reconcile_seal' and e['actor_id']==b['sealed_by']]
            if len(sealed)!=1:raise ValueError('对账封存事件缺失或重复')
            proof(sealed[0]['evidence_id'],b['store_id'],b['case_id'])
    for i in issues:
        b=batches.get(i['batch_id'])
        if not b or i['store_id']!=b['store_id'] or i['line_key'] not in {x['key'] for x in json.loads(b['manifest'])}:raise ValueError('对账差异来源不一致')
        proof(i['evidence_id'],b['store_id'],b['case_id'])
        if i['status']=='resolved':proof(i['resolution_evidence_id'],b['store_id'],b['case_id'])
        elif b['status']=='sealed':raise ValueError('封存对账仍有未处理差异')
    cash_by=defaultdict(list);offset_by=defaultdict(list);reserved=defaultdict(int);settled=defaultdict(int)
    for p in postings:cash_by[p['order_id']].append(p)
    for p in offsets:offset_by[p['order_id']].append(p)
    for o in orders.values():
        b=buckets.get(o['bucket_id'])
        if not b or (o['payer_store_id'],o['receiver_store_id'])!=(b['payer_store_id'],b['receiver_store_id']):raise ValueError('清算原条目与双方不一致')
        for sid,key in [(o['payer_store_id'],o['payer_case_id']),(o['receiver_store_id'],o['receiver_case_id'])]:casecheck(key,sid,'interstore_clearing')
        expected={'requested':[],'cancelled':[],'paid':['out'],'settled':['in','out']}[o['status']]
        if sorted(p['direction'] for p in cash_by[o['id']])!=expected:raise ValueError('清算实际现金与状态不一致')
        for p in cash_by[o['id']]:
            payer=p['direction']=='out';sid=o['payer_store_id'] if payer else o['receiver_store_id'];cid=o['payer_case_id'] if payer else o['receiver_case_id']
            c=cash.get(p['cash_id']);a=accounts.get(p['account_id'])
            if p['store_id']!=sid or p['amount_cents']!=o['amount_cents'] or not c or not a or a['store_id']!=sid:raise ValueError('清算本店现金来源不一致')
            if (c['store_id'],c['direction'],c['amount_cents'],c['category'],c['voucher_no'],c['approval_state'])!=(sid,p['direction'],o['amount_cents'],'interstore_clearing',p['reference'],'approved'):raise ValueError('清算现金金额、方向或原流水不一致')
            proof(p['evidence_id'],sid,cid)
        if o['status']=='settled':
            settled[b['id']]+=o['amount_cents']
            wanted={(o['payer_store_id'],b['origin_kind'],b['debtor_origin_id'],o['amount_cents']),
                (o['receiver_store_id'],b['origin_kind'],b['creditor_origin_id'],-o['amount_cents'])}
            actual={(x['store_id'],x['origin_kind'],x['origin_id'],x['amount_cents']) for x in offset_by[o['id']]}
            if actual!=wanted or len(offset_by[o['id']])!=2:raise ValueError('清算双方原往来核销不守恒')
        elif offset_by[o['id']]:raise ValueError('未实际收齐不得核销往来')
        if o['status'] in {'requested','paid'}:reserved[b['id']]+=o['amount_cents']
    for b in buckets.values():
        source=origins.get(b['origin_kind'],{}).get(b['debtor_origin_id']);target=origins.get(b['origin_kind'],{}).get(b['creditor_origin_id'])
        if not source or not target or (source['store_id'],source['counterparty_store_id'],source['amount_cents'])!=(b['payer_store_id'],b['receiver_store_id'],-b['total_cents']):raise ValueError('清算应付原条目不一致')
        if (target['store_id'],target['counterparty_store_id'],target['amount_cents'],target['transfer_id'])!=(b['receiver_store_id'],b['payer_store_id'],b['total_cents'],source['transfer_id']):raise ValueError('清算原往来配对不一致')
        if b['origin_kind']=='material' and source['movement_id']!=target['movement_id']:raise ValueError('物资清算验收原条目不一致')
        if b['origin_kind']=='material_loss' and (source['posting_id'],source['exception_id'])!=(target['posting_id'],target['exception_id']):raise ValueError('物资运输损失清算不是同一原核销与差异')
        if b['origin_kind']=='vehicle_loss' and (source['loss_id'],source['exception_id'])!=(target['loss_id'],target['exception_id']):raise ValueError('原整车损失清算未追同一实际核销及差异')
        if b['origin_kind']=='vehicle_found' and (source['receipt_id'],source['loss_id'])!=(target['receipt_id'],target['loss_id']):raise ValueError('原整车找回清算未追同一原损失和本次实际接收')
        if b['origin_kind']=='material_found':
            if (source['posting_id'],source['recovery_id'])!=(target['posting_id'],target['recovery_id']):raise ValueError('原物资找回清算不是同一实际恢复与找回')
            found=goods.get(source['recovery_id']);posted=goods_postings.get(source['posting_id'])
            debit=origins['material_loss'].get(source['original_id']);credit=origins['material_loss'].get(target['original_id'])
            if not found or not posted or not debit or not credit or posted['recovery_id']!=found['id'] or posted['loss_id']!=found['loss_id'] or found['transfer_id']!=source['transfer_id']:
                raise ValueError('原物资找回清算缺少原找回、恢复或损失')
            if debit['store_id']!=source['store_id'] or credit['store_id']!=target['store_id'] or debit['posting_id']!=credit['posting_id'] or debit['posting_id']!=found['loss_id'] or debit['amount_cents']!=-credit['amount_cents']:
                raise ValueError('原物资找回清算不是原损失双方反向条目')
            if b['total_cents']!=posted['destination_reverse_cents'] or posted['store_id']!=b['payer_store_id']:
                raise ValueError('原物资找回清算额度超过实际承担冲回')
        if (b['reserved_cents'],b['settled_cents'])!=(reserved[b['id']],settled[b['id']]) or reserved[b['id']]+settled[b['id']]>b['total_cents']:raise ValueError('清算额度占用或已结清金额不守恒')
    if any(p['order_id'] not in orders for p in postings+offsets):raise ValueError('清算过账缺失原申请')
    known={p['cash_id'] for p in postings}
    if {c['id'] for c in cash.values() if c['category']=='interstore_clearing'}!=known:raise ValueError('内部清算现金缺失原关联')
    return {'verified_reconciliation_batches':len(batches),'verified_clearing_orders':len(orders)}
