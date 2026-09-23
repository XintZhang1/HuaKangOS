"""Restore-time validation of frozen bundles, independent of ORM write paths."""
import json


def frozen_pricing_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables={'retail_bundle_rules','retail_bundle_components','retail_bundle_sales','retail_bundle_allocations','retail_bundle_receipts'}
    if not names & tables: return {}
    def check(ok,message):
        if not ok: raise ValueError('精品套餐恢复核对失败：'+message)
    check(tables<=names,'结构不完整')
    def rows(table):
        result=connection.execute('SELECT * FROM '+table);columns=[c[0] for c in result.description]
        return [dict(zip(columns,row)) for row in result]
    def index(table):return {row['id']:row for row in rows(table)}
    def same(a,b):return a and b and a['store_id']==b['store_id']
    rules=index('retail_bundle_rules');components=index('retail_bundle_components');sales=index('retail_bundle_sales')
    allocations=rows('retail_bundle_allocations');receipts=rows('retail_bundle_receipts')
    items=index('flow_items');works=index('master_work_items');cases=index('flow_cases');orders=index('retail_orders');lines=index('retail_lines')
    events=rows('flow_events');result={}
    for rule in rules.values():
        parts=sorted([c for c in components.values() if c['rule_id']==rule['id']],key=lambda c:c['sequence'])
        check(parts and [c['sequence'] for c in parts]==list(range(1,len(parts)+1)),'组成序号不完整')
        check(rule['rule_version']>0 and rule['price_cents_per_set']>0 and rule['sale_starts_on']<=rule['sale_ends_on'] and len(rule['refund_terms'])>=10,'冻结规则无效')
        check(len({c['item_id'] for c in parts})==len(parts),'同一套餐重复商品')
        weights=[];actual=[]
        for c in parts:
            check(same(c,rule) and same(items.get(c['item_id']),rule) and c['quantity_milli_per_set']>0,'组成门店或数量无效')
            if c['work_item_id']:check(same(works.get(c['work_item_id']),rule),'安装项目不是本店')
            else:check(c['installation_reference_cents']==c['installation_cents_per_set']==0 and not c['work_code'] and not c['work_name'],'未配置安装却收费')
            check(min(c['goods_reference_cents'],c['installation_reference_cents'],c['goods_cents_per_set'],c['installation_cents_per_set'])>=0,'负金额')
            weights.extend([c['goods_reference_cents'],c['installation_reference_cents']]);actual.extend([c['goods_cents_per_set'],c['installation_cents_per_set']])
        total=rule['price_cents_per_set'];gross=sum(weights)
        check(0<total<=gross,'成交价超出参考金额')
        expected=[total*w//gross for w in weights]
        for n in sorted(range(len(weights)),key=lambda n:(-(total*weights[n]%gross),n))[:total-sum(expected)]:expected[n]+=1
        check(actual==expected,'每套稳定最大余数分摊不符')
        check(len([r for r in receipts if r['rule_id']==rule['id'] and same(r,rule) and r['actor_id']==rule['created_by']])==1,'规则缺发布请求原证据')
    for sale in sales.values():
        rule=rules.get(sale['rule_id']);case=cases.get(sale['case_id']);order=orders.get(sale['case_id'])
        check(same(sale,rule) and same(sale,case) and same(sale,order) and case['kind']=='retail' and case['flow_version']==2,'原单归属或流程无效')
        check(sale['sets']>0 and sale['terms_accepted'] and sale['actor_id']==case['created_by'],'原单份数或条款未确认')
        check(rule['enabled'] and rule['sale_starts_on']<=case['business_date']<=rule['sale_ends_on'],'原单不是有效期内启用版本')
        parts=[c for c in components.values() if c['rule_id']==rule['id']];own=[a for a in allocations if a['sale_id']==sale['id']]
        check(len(own)==len(parts) and {a['component_id'] for a in own}=={c['id'] for c in parts},'原单组成缺项或重复')
        check({a['line_id'] for a in own}=={l['id'] for l in lines.values() if l['case_id']==case['id']},'原单额外加行或丢失商品')
        from .member_pricing_integrity import retail_prices
        member_prices=retail_prices(connection,case['id'])
        expected_lines={};gross=0;final_total=0
        for a in own:
            c=components[a['component_id']];line=lines.get(a['line_id'])
            check(same(a,sale) and same(a,line) and line['case_id']==case['id'],'金额分摊不是原门店原单')
            for field in ('item_id','sku','name','unit','work_item_id','work_code','work_name'):check(line[field]==c[field],'原商品或安装冻结身份发生变化')
            values={'quantity_milli':c['quantity_milli_per_set']*sale['sets'],'goods_reference_cents':c['goods_reference_cents']*sale['sets'],
                'installation_reference_cents':c['installation_reference_cents']*sale['sets'],'goods_cents':c['goods_cents_per_set']*sale['sets'],
                'installation_cents':c['installation_cents_per_set']*sale['sets']}
            check(all(a[k]==v for k,v in values.items()),'原单金额或数量不等于每套规则乘份数')
            final={**values}
            if member_prices:
                final['goods_cents']=member_prices.get(('item'+str(line['item_id']),'goods'))
                final['installation_cents']=member_prices.get(('item'+str(line['item_id']),'installation'))
            check(all(line[k]==final[k] for k in ('quantity_milli','goods_cents','installation_cents')) and line['unit_price_cents']==line['installation_unit_price_cents']==0,'原单绕过套餐分摊及独立会员价改价')
            final_total+=line['goods_cents']+line['installation_cents']
            expected_lines[line['id']]=values;gross+=values['goods_reference_cents']+values['installation_reference_cents']
        check(case['amount_cents']==(final_total if member_prices else rule['price_cents_per_set']*sale['sets']) and order['discount_cents']==gross-case['amount_cents'],'报价合计或优惠不守恒')
        provenance=[e for e in events if e['case_id']==case['id'] and e['action']=='retail_bundle_create']
        check(len(provenance)==1 and same(provenance[0],case) and provenance[0]['actor_id']==sale['actor_id'],'套餐开单来源日志缺失')
        data=json.loads(provenance[0]['detail'] or '{}')
        check(data=={'rule_id':rule['id'],'rule_version':rule['rule_version'],'sets':sale['sets'],'terms_accepted':True},'套餐开单来源日志不符')
        result[case['id']]=expected_lines
    check(all(c['rule_id'] in rules for c in components.values()) and all(a['sale_id'] in sales for a in allocations),'孤立组成或分摊')
    check(all(r['rule_id'] in rules for r in receipts),'孤立发布凭据')
    check(all(e['case_id'] in result for e in events if e['action']=='retail_bundle_create'),'套餐开单来源被删除')
    return result


def validate_retail_bundles_sqlite(connection):
    values=frozen_pricing_sqlite(connection)
    return {'verified_retail_bundle_sales':len(values),'verified_retail_bundle_allocations':sum(len(v) for v in values.values())}
