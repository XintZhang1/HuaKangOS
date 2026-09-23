"""Read-only independent validation of restored retail agreements and ledgers."""
import json
from collections import defaultdict

def validate_retail_sqlite(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'retail_orders','retail_lines','retail_reservations','retail_dispatches','retail_returns','retail_return_lines','retail_return_postings','retail_payments'}
    if not names&required:return {'verified_retail_orders':0}
    if not required<=names:raise ValueError('精品账本表不完整')
    from .payment_cash_integrity import validate_payment_cash,finance_payment_evidence_allowed
    try:validate_payment_cash(connection)
    except ValueError as exc:raise ValueError('精品恢复核对失败：'+str(exc)) from exc
    def rows(table):
        cursor=connection.execute('SELECT * FROM '+table);columns=[x[0] for x in cursor.description]
        return [dict(zip(columns,r)) for r in cursor]
    def index(table):return {r['id']:r for r in rows(table)}
    def require(condition,message):
        if not condition:raise ValueError('精品恢复核对失败：'+message)
    orders=index('retail_orders');cases=index('flow_cases');items=index('flow_items');moves=index('flow_stock_moves');cash=index('cash_entries');files=index('flow_files');works=index('master_work_items')
    lines=index('retail_lines');dispatches=index('retail_dispatches');requests=index('retail_returns');returnlines=index('retail_return_lines')
    postings=rows('retail_return_postings');reservations=rows('retail_reservations');payments=rows('retail_payments');links=index('flow_payment_links')
    active={'approved','rectification','reinspection','handback','accepted'};globalholds=defaultdict(int)
    from .retail_bundle_integrity import frozen_pricing_sqlite
    bundle_pricing=frozen_pricing_sqlite(connection)
    def scoped(a,b):return a is not None and b is not None and a['store_id']==b['store_id']
    def evidence(record,case,category=None):
        asset=files.get(record['evidence_id'])
        require(scoped(asset,case) and asset['case_id']==case['id'] and not asset['generated'],'事实凭据不属于原业务')
        if category:require(asset['category']==category,'财务凭据类别未隔离')
    for order in orders.values():
        case=cases.get(order['id']);require(scoped(order,case) and case['kind']=='retail' and case['flow_version']==2,'报价头与业务归属')
        data=json.loads(case['data'] or '{}');own=[l for l in lines.values() if l['case_id']==case['id']]
        require(order['revision']==1 and own and len({l['item_id'] for l in own})==len(own),'报价版本或商品重复')
        gross=0;net=0;weights=[];actual_values=[]
        if order['related_repair_id']:
            repair=cases.get(order['related_repair_id']);require(scoped(repair,case) and repair['kind']=='repair' and repair['customer_id']==case['customer_id'],'关联维修不是同店同客户')
        for line in own:
            item=items.get(line['item_id']);require(scoped(line,case) and scoped(line,item),'商品门店归属')
            quantity=line['quantity_milli'];goods=(quantity*line['unit_price_cents']+500)//1000;installation=(quantity*line['installation_unit_price_cents']+500)//1000
            if case['id'] in bundle_pricing:
                frozen=bundle_pricing[case['id']][line['id']]
                goods=frozen['goods_reference_cents'];installation=frozen['installation_reference_cents']
            require(quantity>0 and 0<=line['goods_cents']<=goods and 0<=line['installation_cents']<=installation,'报价分摊范围')
            require(line['work_item_id'] is not None or line['installation_cents']==line['installation_unit_price_cents']==0,'未配置安装却有安装费')
            if line['work_item_id']:require(scoped(works.get(line['work_item_id']),case),'安装项目门店归属')
            gross+=goods+installation;net+=line['goods_cents']+line['installation_cents']
            weights.extend([goods,installation]);actual_values.extend([line['goods_cents'],line['installation_cents']])
            held=[r for r in reservations if r['case_id']==case['id'] and r['item_id']==line['item_id']]
            expected=0 if data.get('dispatched') or data.get('cancelled') else quantity
            require(sum(r['quantity_milli'] for r in held)==expected,'有效占用与未出库订单不一致')
            require(sum(r['quantity_milli'] for r in held if r['reason']=='reserve')==quantity and len([r for r in held if r['reason']=='reserve'])==1,'初始占用数量')
            for h in held:
                require(scoped(h,case) and ((h['reason']=='reserve' and h['quantity_milli']>0) or (h['reason'] in {'dispatch','cancel'} and h['quantity_milli']<0)),'占用流水归属或方向')
                if h['reason']=='dispatch':require(data.get('dispatched'),'无出库事实却解除出库占用')
                if h['reason']=='cancel':require(data.get('cancelled'),'无取消事实却解除取消占用')
            globalholds[line['item_id']]+=expected
        require(net==case['amount_cents']==gross-order['discount_cents'] and order['discount_cents']>=0,'报价合计与优惠不守恒')
        allocation=[net*w//gross for w in weights] if gross else [0]*len(weights)
        if gross:
            for n in sorted(range(len(weights)),key=lambda x:(-(net*weights[x]%gross),x))[:net-sum(allocation)]:allocation[n]+=1
        from .member_pricing_integrity import retail_prices
        member_prices=retail_prices(connection,case['id'])
        if member_prices:
            require(actual_values==[member_prices.get(('item'+str(l['item_id']),component)) for l in own for component in ('goods','installation')],'会员价原金额不符合冻结组件')
        elif case['id'] not in bundle_pricing:require(allocation==actual_values,'报价优惠分摊不符合冻结规则')
        actual=[d for d in dispatches.values() if d['case_id']==case['id']]
        require(len(actual)==(len(own) if data.get('dispatched') else 0),'出库应为一次完整清单')
        require(not(data.get('cancelled') and actual),'已出库订单不能抹为未出库取消')
        for d in actual:
            evidence(d,case)
            line=lines.get(d['line_id']);move=moves.get(d['stock_move_id'])
            require(scoped(d,line) and line['case_id']==case['id'] and d['quantity_milli']==line['quantity_milli'] and d['value_cents']>=0,'原出库数量、成本或商品归属')
            require(scoped(d,move) and move['case_id']==case['id'] and move['item_id']==line['item_id'] and move['purpose']=='retail_dispatch'
                and move['quantity_milli']==-d['quantity_milli'] and move['value_cents']==-d['value_cents'] and move['original_id'] is None,'原出库与库存账不一致')
            returned=[p for p in postings if p['dispatch_id']==d['id']];qty=sum(p['quantity_milli'] for p in returned)
            value=sum(p['value_cents'] for p in returned);goods=sum(p['goods_cents'] for p in returned);install=sum(p['installation_cents'] for p in returned)
            require(0<=qty<=d['quantity_milli'] and 0<=value<=d['value_cents'] and 0<=goods<=line['goods_cents'] and 0<=install<=line['installation_cents'],'原出库退回超过原数量或价值')
            if qty==d['quantity_milli']:require(value==d['value_cents'] and goods==line['goods_cents'] and install==line['installation_cents'],'退尽原单后有金额余分')
            remaining=d['quantity_milli'];remainders=[d['value_cents'],line['goods_cents'],line['installation_cents']]
            for p in sorted(returned,key=lambda x:x['id']):
                q=p['quantity_milli'];require(q>0 and q<=remaining,'退货分批数量')
                expected=[v if q==remaining else (2*v*q+remaining)//(2*remaining) for v in remainders]
                require(expected==[p['value_cents'],p['goods_cents'],p['installation_cents']],'部分退货原数量与原价值分摊不符')
                remaining-=q;remainders=[v-a for v,a in zip(remainders,expected)]
            occupied=sum(l['quantity_milli'] for l in returnlines.values() if l['dispatch_id']==d['id'] and requests[l['return_id']]['status'] in active)
            require(occupied<=d['quantity_milli'],'批准退货重复占用原数量')
        for request in (r for r in requests.values() if r['case_id']==case['id']):
            evidence(request,case)
            require(scoped(request,case),'退货申请门店归属')
            if request['status'] in active:require(request['approved_by'] is not None,'已执行退货缺审批人')
            children=[l for l in returnlines.values() if l['return_id']==request['id']];require(children,'空退货申请')
            for child in children:
                d=dispatches.get(child['dispatch_id']);require(scoped(child,request) and scoped(child,d) and d['case_id']==case['id'] and 0<child['quantity_milli']<=d['quantity_milli'],'退货原单归属及数量')
                records=[p for p in postings if p['return_line_id']==child['id']]
                require(len(records)==(1 if request['status']=='accepted' else 0),'退货验收状态与实物记录不一致')
                for p in records:
                    evidence(p,case)
                    move=moves.get(p['stock_move_id']);require(scoped(p,case) and p['case_id']==case['id'] and p['dispatch_id']==d['id'] and p['quantity_milli']==child['quantity_milli'],'实际退货原单关联')
                    require(scoped(p,move) and move['case_id']==case['id'] and move['item_id']==lines[d['line_id']]['item_id'] and move['purpose']=='retail_return'
                        and move['quantity_milli']==p['quantity_milli'] and move['value_cents']==p['value_cents'] and move['original_id']==d['stock_move_id'],'退货与原库存流水不一致')
                    require(p['retained_cents']==(p['installation_cents'] if request['retain_installation'] else 0),'安装保留费与批准规则不一致')
                    require(not request['retain_installation'] or data.get('installed'),'未实际安装却保留安装费')
        ownlinks=[p for p in links.values() if p['case_id']==case['id']];cashids=set()
        for p in ownlinks:
            ownpayments=[r for r in payments if r['payment_link_id']==p['id']];entry=cash.get(p['cash_id'])
            require(len(ownpayments)==1 and scoped(ownpayments[0],case) and ownpayments[0]['case_id']==case['id'],'现金链接缺失或重复')
            allocated=finance_payment_evidence_allowed(connection,p['id'],case['id'],ownpayments[0]['evidence_id'])
            if not allocated:evidence(ownpayments[0],case,'receipt')
            require(scoped(p,case) and scoped(p,entry) and p['amount_cents']>0 and (allocated or entry['amount_cents']==p['amount_cents']) and entry['direction']==p['direction'] and entry['voucher_no']==p['reference'],'现金原始记录与业务链接不一致')
            require(allocated or p['cash_id'] not in cashids,'重复计算现金');cashids.add(p['cash_id'])
            account=connection.execute('SELECT name,store_id FROM flow_accounts WHERE id=?',(p['account_id'],)).fetchone()
            require(account and account[0]==entry['account'] and account[1]==case['store_id'],'现金账户与门店')
            if p['direction']=='out':
                original=links.get(p['original_id']);require(original and original['case_id']==case['id'] and original['direction']=='in' and original['account_id']==p['account_id'],'退款不是本单原账户')
            else:
                require(p['original_id'] is None,'收款不能引用退款原单')
                require(sum(r['amount_cents'] for r in ownlinks if r['original_id']==p['id'])<=p['amount_cents'],'退款超过原收款余额')
        for record in (r for r in payments if r['case_id']==case['id']):require(record['payment_link_id'] in {p['id'] for p in ownlinks},'多余现金关联')
    for item_id,quantity in globalholds.items():require(0<=quantity<=items[item_id]['quantity_milli'],'当前库存小于有效占用')
    require(all(c['id'] in orders for c in cases.values() if c['kind']=='retail' and c['flow_version']==2),'精品业务缺少冻结报价')
    require(all(r['case_id'] in orders and any(l['case_id']==r['case_id'] and l['item_id']==r['item_id'] for l in lines.values()) for r in reservations),'多余库存占用')
    for collection in (lines.values(),dispatches.values(),requests.values(),postings,payments):require(all(r['case_id'] in orders for r in collection),'零售账本挂接到非零售业务')
    linked_cash={p['cash_id'] for p in links.values() if p['case_id'] in orders}
    require(all(c['id'] in linked_cash for c in cash.values() if c['category']=='workflow_retail'),'精品现金缺少唯一原单关联')
    return {'verified_retail_orders':len(orders),'verified_retail_dispatches':len(dispatches),'verified_retail_returns':len(postings)}
