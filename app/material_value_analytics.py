"""Actual material value, fulfillment and explicitly unallocated business amounts.

No arbitrary SKU allocation, cash-as-revenue, labor margin or inventory GL.
Every chart consumes its exported table. All model reads retain tenant scope.
"""
from collections import defaultdict
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from .models import Store
from .flow_models import Case, Item, StockMove
from .retail_models import RetailLine, RetailDispatch, RetailReturnPosting
from .addon_models import AddonLine, AddonQuote, AddonDispatch, AddonAcceptance, AddonReturnPosting
from .repair_models import RepairLine, RepairQuote, RepairStock, RepairSettlement, RepairAllocation
from .aftercare_models import AftercareAdjustment, AftercareApplication
from .claims_models import ClaimResponsibility, ClaimApplication
from .group_aftercare_models import GroupAftercareHold
from .repair_package_models import PackagePaymentLink, PackageQuoteSnapshot, PackageStockReturn
from .inventory_report_common import bounded, period, yuan, qty, route, table, as_of, MONEY_ROLES
from .warehouse_period_analytics import REASONS

SOURCES = {'retail': '精品销售', 'addon': '销售加装', 'repair': '维修', 'stock': '非履约库存变化'}
DEFINITION = ('精品按客户接收日、加装按每版实际验收日、维修按交车日确认。商品原行和服务原行分别列示；'
    '整单内部承担、会员对外优惠、套餐原面值与实付对价差额、售后及核赔减免未按商品分配，不用于宣称单品利润。'
    '商品＋服务＋未分配调整＝原业务对外净额；直接材料成本仅取实际领退料原成本，不含人工及管理费用。'
    '实际领退日期与履约日期分别统计。采购、调拨、耗材、礼品及盘点等库存变化不当作销售收入。'
    '选择物资后，原单核对仍保留相关原单全部行及未分配调整，选中物资金额仅在商品表单列。')


def _group(rows, field):
    result = defaultdict(list)
    for row in rows: result[getattr(row, field)].append(row)
    return result


def _check(condition, message):
    if not condition: raise HTTPException(409, '物资收入成本来源不一致：' + message)


def build_material_values(db, user, start=None, end=None, source=None, item_id=None, case_id=None):
    if user.role not in MONEY_ROLES: raise HTTPException(403, '当前岗位不能查看物资收入与成本金额')
    if source and source not in SOURCES: raise HTTPException(422, '请选择精品、加装、维修或非履约库存变化')
    start, end = period(user, start, end)
    stores = dict(db.execute(select(Store.id, Store.name)).all())
    allcases = {r.id: r for r in bounded(db, Case)}
    items = {r.id: r for r in bounded(db, Item)}
    if case_id and case_id not in allcases: raise HTTPException(404, '当前授权门店没有该原单')
    if item_id and item_id not in items: raise HTTPException(404, '当前授权门店没有该物资')
    cases = {i: r for i, r in allcases.items() if ((r.kind == 'retail' and r.flow_version == 2)
        or (r.kind == 'addon' and r.flow_version == 3) or (r.kind == 'repair' and r.flow_version in {3, 4}))
        and (not source or r.kind == source) and (not case_id or i == case_id)}
    ids = list(cases)
    def load(model, field='case_id', values=None):
        return bounded(db, model, select(model).where(getattr(model, field).in_(ids if values is None else values)))
    moves = {r.id: r for r in bounded(db, StockMove)}
    facts = []; expected = defaultdict(int); physical = {}; source_items = defaultdict(set)

    def stock(move_id, row, item, amount, quantity):
        m = moves.get(move_id)
        _check(m and m.store_id == row.store_id and m.case_id == row.id and m.item_id == item and m.value_cents == -amount
               and m.quantity_milli == -quantity, '原领退料金额、数量或门店不符')
        _check(move_id not in physical, '同一物资流水重复归属业务')
        physical[move_id] = row.id; source_items[row.id].add(item)

    def add(row, day, category, kind, origin, origin_id, amount=0, cost=0, line=None, quantity=0):
        _check(day is not None, '履约记录缺少实际日期')
        _check(line is None or line.store_id == row.store_id, '冻结原行与业务门店不符')
        from .inventory_report_common import LIMIT
        if len(facts) >= LIMIT: raise HTTPException(422, '履约来源超过报表上限，本次未返回截断统计；请缩小查询范围')
        item = getattr(line, 'item_id', None) if category == 'goods' else None
        if item: source_items[row.id].add(item)
        facts.append(dict(case_id=row.id, store_id=row.store_id, source=row.kind,
            business_date=day, category=category, kind=kind, source_table=origin, source_id=origin_id,
            line_id=getattr(line, 'id', None), item_id=item,
            code=getattr(line, 'sku', getattr(line, 'code', '')) if category == 'goods' else getattr(line, 'work_code', getattr(line, 'code', '')),
            name=getattr(line, 'name', '') if category == 'goods' else getattr(line, 'work_name', getattr(line, 'name', '')),
            unit=getattr(line, 'unit', '') if category == 'goods' else '', quantity_milli=quantity,
            amount_cents=amount, cost_cents=cost))

    # Retail allocation is already frozen on each original line, including package discounts.
    rl = load(RetailLine); rd = load(RetailDispatch); rr = load(RetailReturnPosting)
    lines = {l.id: l for l in rl}; dispatches = {d.id: d for d in rd}
    returns = _group(rr, 'dispatch_id'); byline = {d.line_id: d for d in rd}
    for d in rd: stock(d.stock_move_id, cases[d.case_id], lines[d.line_id].item_id, d.value_cents, d.quantity_milli)
    for p in rr:
        d = dispatches[p.dispatch_id]; stock(p.stock_move_id, cases[p.case_id], lines[d.line_id].item_id, -p.value_cents, -p.quantity_milli)
    for l in rl:
        row = cases[l.case_id]; source_items[row.id].add(l.item_id)
        if not row.data.get('accepted_date'): continue
        day = date.fromisoformat(row.data['accepted_date']); d = byline.get(l.id)
        _check(d, '已接收精品缺少实际出库原行')
        prior = [p for p in returns[d.id] if moves[p.stock_move_id].business_date <= day]
        goods = l.goods_cents - sum(p.goods_cents for p in prior)
        service = l.installation_cents - sum(p.installation_cents - p.retained_cents for p in prior)
        cost = d.value_cents - sum(p.value_cents for p in prior)
        _check(min(goods, service, cost) >= 0, '接收前原退超过精品原行')
        add(row, day, 'goods', '客户接收', 'retail_lines', l.id, goods, cost, l, l.quantity_milli - sum(p.quantity_milli for p in prior))
        if l.installation_cents: add(row, day, 'service', '安装履约及保留费', 'retail_lines', l.id, service, line=l)
        for p in returns[d.id]:
            if p in prior: continue
            day2 = moves[p.stock_move_id].business_date
            add(row, day2, 'goods', '原单退货', 'retail_return_postings', p.id, -p.goods_cents, -p.value_cents, l, -p.quantity_milli)
            if p.installation_cents: add(row, day2, 'service', '原安装退款（扣除保留费）', 'retail_return_postings', p.id, -(p.installation_cents-p.retained_cents), line=l)
    for row in cases.values():
        if row.kind == 'retail' and row.data.get('accepted_date'):
            expected[row.id] = row.amount_cents - sum(p.goods_cents+p.installation_cents-p.retained_cents for p in rr if p.case_id == row.id)

    # Retail C/P/S allocations already identify the exact original goods or
    # installation component. Never allocate a fresh order-level discount.
    from .retail_group_reporting import report_data
    for fact in report_data(db,user,ids)['discounts']:
        row=cases[fact['case_id']];line=lines[fact['line_id']]
        add(row,date.fromisoformat(fact['business_date']),
            'goods' if fact['component']=='goods' else 'service',fact['label'],
            fact['source'],fact['source_id'],fact['amount_cents'],line=line)
        expected[row.id]+=fact['amount_cents']

    # Already executed addon lines cannot be repriced; later versions add new line keys.
    aq = load(AddonQuote); al = load(AddonLine, 'quote_id', [q.id for q in aq]); ad = load(AddonDispatch)
    ar = load(AddonReturnPosting); aa = load(AddonAcceptance)
    aline = {l.id:l for l in al}; qlines = _group(al, 'quote_id'); ds = _group(ad, 'case_id'); ps = _group(ar, 'case_id')
    for d in ad: stock(d.stock_move_id, cases[d.case_id], aline[d.line_id].item_id, d.value_cents, d.quantity_milli)
    for p in ar:
        if p.stock_move_id: stock(p.stock_move_id, cases[p.case_id], aline[p.line_id].item_id, -p.value_cents, -p.quantity_milli)
    for key, accepted in _group(aa, 'case_id').items():
        row = cases[key]; known = set()
        for a in sorted(accepted, key=lambda x:x.id):
            before_count = len(facts)
            for l in qlines[a.quote_id]:
                if l.line_key in known: continue
                known.add(l.line_key); prior = [p for p in ps[key] if p.line_key == l.line_key and p.acceptance_id is None]
                goods = l.goods_cents - sum(p.goods_cents for p in prior)
                service = l.installation_cents - sum(p.installation_cents-p.retained_cents for p in prior)
                cost = sum(d.value_cents for d in ds[key] if d.line_key == l.line_key) - sum(p.value_cents for p in prior)
                _check(min(goods, service, cost) >= 0, '加装验收前原退超过冻结原行')
                add(row, a.business_date, 'goods', '本版实际验收', 'addon_acceptances', a.id, goods, cost, l, l.quantity_milli-sum(p.quantity_milli for p in prior))
                add(row, a.business_date, 'service', '本版安装履约及保留费', 'addon_acceptances', a.id, service, line=l)
            new = facts[before_count:]
            _check(sum(f['amount_cents'] for f in new) == a.amount_cents and sum(f['cost_cents'] for f in new) == a.value_cents,
                   '加装冻结行与实际验收增量不符')
            expected[key] += a.amount_cents
        for p in ps[key]:
            if not p.acceptance_id: continue
            l = aline[p.line_id]
            add(row, p.business_date, 'goods', '已验收原商品退回', 'addon_return_postings', p.id, -p.goods_cents, -p.value_cents, l, -p.quantity_milli)
            add(row, p.business_date, 'service', '原安装退款（扣除保留费）', 'addon_return_postings', p.id, -(p.installation_cents-p.retained_cents), line=l)
            expected[key] -= p.goods_cents+p.installation_cents-p.retained_cents

    # Repair source line prices have no payer-to-SKU mapping. Preserve that absence.
    rq = load(RepairQuote); rqmap = {q.id:q for q in rq}; rlines = load(RepairLine, 'quote_id', [q.id for q in rq]); rs = load(RepairStock)
    settlements = load(RepairSettlement); allocations = _group(load(RepairAllocation), 'case_id')
    rline = {(l.quote_id,l.line_key):l for l in rlines}; rqline = _group(rlines, 'quote_id')
    repair_cost = defaultdict(int)
    package_returns={r.stock_fact_id:r for r in bounded(db,PackageStockReturn)}
    package_quotes={r.quote_id:r for r in load(PackageQuoteSnapshot)}
    for s in rs:
        l = rline[(s.quote_id,s.line_key)]; stock(s.stock_move_id, cases[s.case_id], l.item_id, s.value_cents, s.quantity_milli)
        if s.id not in package_returns:repair_cost[(s.case_id,l.line_key)] += s.value_cents
    from .group_benefits_service import analytics_rows
    discounts = defaultdict(int)
    for e in analytics_rows(db,user)['entries']:
        if e['case_id'] in cases: discounts[e['case_id']] += e['external_discount_cents']
    for h in load(GroupAftercareHold, 'source_case_id'):
        if h.status == 'applied': discounts[h.source_case_id] += h.discount_cents
    package_discounts=defaultdict(int)
    for p in load(PackagePaymentLink):
        # Keep original fulfillment P frozen. Later return P is already an
        # aftercare revenue adjustment at its actual application date.
        if p.purpose=='capture':package_discounts[p.case_id]+=p.amount_cents-p.recognized_cents
    for s in settlements:
        row = cases[s.case_id]
        if not row.data.get('released_date'): continue
        day = date.fromisoformat(row.data['released_date']); seen_keys = set()
        q = rqmap[s.quote_id]
        package_stop=package_quotes.get(q.id) if q.purpose=='stop' else None
        if q.purpose == 'stop' and not package_stop:
            _check(not any(amount for (cid,_),amount in repair_cost.items() if cid==row.id), '停工原材料尚未全部退回')
            add(row, day, 'service', '客户授权停工保留费', 'repair_quotes', q.id, q.amount_cents)
        for l in rqline[s.quote_id]:
            if q.purpose == 'stop' and not package_stop: continue
            if package_stop and l.line_key not in package_stop.contract['retained']:
                # The ordinary stop contract remains a retained service fee;
                # it does not manufacture an unconsumed SKU sale beside the
                # explicitly retained package components.
                add(row,day,'service','客户授权停工保留费（非套餐项目）','repair_lines',l.id,l.amount_cents,line=l)
                continue
            if l.kind == 'part':
                seen_keys.add(l.line_key)
                quantity=package_stop.contract['retained'].get(l.line_key,0) if package_stop else l.quantity_milli
                add(row, day, 'goods', '停工原组件实际保留' if package_stop else '维修实际交车', 'repair_lines', l.id, l.amount_cents, repair_cost[(row.id,l.line_key)], l, quantity)
            else: add(row, day, 'service', '维修作业履约', 'repair_lines', l.id, l.amount_cents, line=l)
        _check(not any(amount and key not in seen_keys for (cid,key),amount in repair_cost.items() if cid == row.id), '维修实际消耗缺少最终授权原行')
        internal = sum(a.amount_cents for a in allocations[row.id] if a.payer_type == 'internal')
        if internal: add(row, day, 'unallocated', '原整单内部承担（未分配商品）', 'repair_settlements', s.id, -internal)
        if discounts[row.id]: add(row, day, 'unallocated', '会员对外优惠（未分配商品）', 'repair_settlements', s.id, -discounts[row.id])
        if package_discounts[row.id]:add(row,day,'unallocated','套餐原面值与实付对价差额（未分配商品）','repair_settlements',s.id,-package_discounts[row.id])
        expected[row.id] = sum(a.amount_cents for a in allocations[row.id] if a.payer_type != 'internal') - discounts[row.id]-package_discounts[row.id]
    for s in rs:
        if s.id not in package_returns or not cases[s.case_id].data.get('released_date'):continue
        returned=package_returns[s.id];l=rline[(s.quote_id,s.line_key)]
        _check(s.quantity_milli==-returned.quantity_milli and s.value_cents==-returned.value_cents,
            '套餐实际原退与原领料成本不符')
        add(cases[s.case_id],moves[s.stock_move_id].business_date,'goods','原套餐配件实际退回成本（收入按售后原单调整）',
            PackageStockReturn.__tablename__,returned.id,0,s.value_cents,l,s.quantity_milli)
    apps = {a.id:a for a in bounded(db,AftercareApplication)}
    for a in load(AftercareAdjustment, 'source_case_id'):
        row = cases[a.source_case_id]
        if row.kind != 'repair' or not row.data.get('released_date'): continue
        app = apps[a.application_id]
        add(row, app.business_date, 'unallocated', '原单售后减免（未分配商品）', 'aftercare_adjustments', a.id, -a.revenue_credit_cents)
        expected[row.id] -= a.revenue_credit_cents
    claim_apps = {a.id:a for a in bounded(db,ClaimApplication)}
    for a in load(ClaimResponsibility, 'source_case_id'):
        row = cases[a.source_case_id]
        if row.kind != 'repair' or not row.data.get('released_date') or a.payer_type == 'internal': continue
        day = max(claim_apps[a.application_id].business_date, date.fromisoformat(row.data['released_date']))
        add(row, day, 'unallocated', '原维修核赔责任调整（未分配商品）', ClaimResponsibility.__tablename__, a.id, a.amount_cents)
        expected[row.id] += a.amount_cents

    # Exclude every detailed business movement from the non-fulfillment table,
    # also when its business has been removed by a report filter.
    commercial_moves = set(physical)
    for model in (RetailDispatch, RetailReturnPosting, AddonDispatch, AddonReturnPosting, RepairStock):
        commercial_moves.update(r.stock_move_id for r in bounded(db,model) if r.stock_move_id)
    return _present(db, cases, allcases, items, stores, facts, expected, physical, commercial_moves, moves, source_items,
                    start, end, source, item_id, case_id)


def _present(db, cases, allcases, items, stores, facts, expected, physical, commercial_moves, moves, source_items, start, end, source, item_id, case_id):
    related = {key for key in cases if not item_id or item_id in source_items[key]}
    tables = {
        'material_goods': table('期间商品收入与直接材料成本', ['单号','门店','业务','确认日期','事实','物资编码','原行名称','单位','数量','商品金额（元）','材料成本（元）']),
        'material_services': table('期间原单服务与安装金额', ['单号','门店','业务','确认日期','事实','作业编码','原行名称','服务金额（元）']),
        'material_unallocated': table('期间原单未分配调整', ['单号','门店','业务','确认日期','未分配原因','金额（元）']),
        'material_sources': table('相关原单期间对外金额核对', ['单号','门店','业务','全部商品（元）','全部服务（元）','未分配调整（元）','对外净额（元）','直接材料成本（元）']),
        'material_actual_stock': table('期间实际业务领退料', ['单号','门店','业务','实际日期','物资编码','名称','单位','实际净领数量','实际净领成本（元）','原物资流水']),
        'material_other_stock': table('期间非履约库存变化', ['单号','门店','实际日期','事实','物资编码','名称','单位','库存数量变化','库存价值变化（元）','原物资流水']),
        'material_unfulfilled': table('当前已领未履约成本核对', ['单号','门店','业务','物资编码','名称','累计实际净领（元）','累计已履约成本（元）','已领未履约成本（元）']),
    }
    summaries = defaultdict(lambda:defaultdict(int)); alltotals = defaultdict(int); recognized = defaultdict(int)
    for f in facts:
        alltotals[f['case_id']] += f['amount_cents']
        if f['category'] == 'goods': recognized[(f['case_id'],f['item_id'])] += f['cost_cents']
        if f['case_id'] not in related or not start <= f['business_date'] <= end: continue
        row = cases[f['case_id']]; sums = summaries[row.id]
        sums[f['category']] += f['amount_cents']; sums['cost'] += f['cost_cents']
        if f['category'] == 'goods' and item_id and f['item_id'] != item_id: continue
        base = [row.number,stores.get(row.store_id,''),SOURCES[row.kind],f['business_date'].isoformat(),f['kind']]
        if f['category'] == 'goods': values = base+[f['code'],f['name'],f['unit'],qty(f['quantity_milli']),yuan(f['amount_cents']),yuan(f['cost_cents'])]; key='material_goods'
        elif f['category'] == 'service': values=base+[f['code'],f['name'],yuan(f['amount_cents'])];key='material_services'
        else: values=base+[yuan(f['amount_cents'])];key='material_unallocated'
        data={**f,'business_date':f['business_date'].isoformat(),'values':values,'route':route(db,row.id)}
        tables[key]['rows'].append(data)
    for key in cases: _check(alltotals[key] == expected[key], '商品、服务及未分配调整无法对上原单对外净额')
    for key,s in sorted(summaries.items()):
        row=cases[key]; amount=s['goods']+s['service']+s['unallocated']
        tables['material_sources']['rows'].append(dict(values=[row.number,stores.get(row.store_id,''),SOURCES[row.kind],yuan(s['goods']),yuan(s['service']),yuan(s['unallocated']),yuan(amount),yuan(s['cost'])],
            case_id=key,amount_cents=amount,goods_cents=s['goods'],service_cents=s['service'],unallocated_cents=s['unallocated'],cost_cents=s['cost'],route=route(db,key)))
    netstock=defaultdict(int)
    for m in moves.values():
        business_id=physical.get(m.id)
        if business_id: netstock[(business_id,m.item_id)] -= m.value_cents
        if not start <= m.business_date <= end or item_id and m.item_id != item_id: continue
        cid=business_id or m.case_id
        if case_id and cid != case_id: continue
        if business_id:
            if business_id not in related: continue
            row=cases[business_id]; item=items[m.item_id];key='material_actual_stock';amount=-m.value_cents
            values=[row.number,stores.get(row.store_id,''),SOURCES[row.kind],m.business_date.isoformat(),item.sku,item.name,item.unit,qty(-m.quantity_milli),yuan(amount),m.id]
        else:
            if source and source != 'stock':continue
            if m.id in commercial_moves:continue
            row=allcases.get(cid);item=items[m.item_id];key='material_other_stock';amount=m.value_cents
            _check(row and row.store_id==m.store_id,'库存原单不在同店')
            # Detailed business movements outside selected source are not non-business income.
            if row.kind in {'retail','addon','repair'} and ((row.kind=='retail' and row.flow_version==2) or (row.kind=='addon' and row.flow_version==3) or (row.kind=='repair' and row.flow_version in {3,4})):continue
            values=[row.number,stores.get(row.store_id,''),m.business_date.isoformat(),REASONS.get(m.purpose,m.purpose),item.sku,item.name,item.unit,qty(m.quantity_milli),yuan(amount),m.id]
        tables[key]['rows'].append(dict(values=values,amount_cents=amount,case_id=cid,item_id=m.item_id,stock_move_id=m.id,
            quantity_milli=-m.quantity_milli if business_id else m.quantity_milli,business_date=m.business_date.isoformat(),purpose=m.purpose,route=route(db,cid)))
    for key in sorted(set(netstock)|set(recognized)):
        cid,iid=key
        if cid not in related or item_id and iid != item_id:continue
        row=cases[cid];item=items[iid];actual=netstock[key];cost=recognized[key];pending=actual-cost
        _check(pending>=0,'已履约材料成本超过原单实际净领成本')
        tables['material_unfulfilled']['rows'].append(dict(values=[row.number,stores.get(row.store_id,''),SOURCES[row.kind],item.sku,item.name,yuan(actual),yuan(cost),yuan(pending)],
            case_id=cid,item_id=iid,actual_cost_cents=actual,recognized_cost_cents=cost,amount_cents=pending,route=route(db,cid)))
    charts=[]
    for t in tables.values():
        t['rows'].sort(key=lambda r:(r.get('case_id',0),r.get('business_date',''),r.get('source_table',''),
                                    r.get('source_id',0),r.get('line_id') or 0,r.get('item_id') or 0,r.get('stock_move_id',0)))
    for key,title,index,caption in (
        ('material_goods','期间商品金额与直接材料成本',2,'冻结商品金额；未分配整单减免另表，不据此宣称商品利润。'),
        ('material_sources','期间相关原单对外净额',2,'完整相关原单全部商品、服务和未分配调整之和，不是选中物资的单品净额。'),
        ('material_unallocated','期间未分配原单调整',4,'没有原商品分配依据，保留原单事实；不虚构 SKU 承担。'),
        ('material_other_stock','期间非履约库存价值变化',3,'库存收发的实际符号；采购、自耗、礼品、盘点、调拨等不算商品销售收入。'),
        ('material_unfulfilled','当前已领未履约成本',2,'累计实际净领减累计履约成本；与所选期间收入不是同一时点。')):
        totals=defaultdict(int);costs=defaultdict(int)
        for r in tables[key]['rows']:totals[r['values'][index]]+=r['amount_cents'];costs[r['values'][index]]+=r.get('cost_cents',0)
        labels=sorted(totals);series=[{'name':'金额','values':[totals[k] for k in labels]}]
        if key=='material_goods':series.append({'name':'直接材料成本','values':[costs[k] for k in labels]})
        charts.append(dict(id=key,title=title,type='bar',section='materials',unit='cents',labels=labels,series=series,table=key,caption=caption))
    return dict(definition=DEFINITION,definition_version=1,complete=True,as_of=as_of(),date_from=start.isoformat(),date_to=end.isoformat(),
        filters=dict(source=source,item_id=item_id,case_id=case_id),charts=charts,tables=tables,
        metrics={'material_selected_goods_cents':sum(r['amount_cents'] for r in tables['material_goods']['rows']),
                 'material_selected_goods_cost_cents':sum(r['cost_cents'] for r in tables['material_goods']['rows']),
                 'material_source_net_cents':sum(r['amount_cents'] for r in tables['material_sources']['rows']),
                 'material_unfulfilled_cost_cents':sum(r['amount_cents'] for r in tables['material_unfulfilled']['rows'])},
        options={'sources':[{'id':k,'label':v} for k,v in SOURCES.items()],
                 'cases':[] if db.info.get('aggregate_scope') else [{'id':r.id,'label':r.number+' · '+SOURCES[r.kind]} for r in cases.values()],
                 'items':[{'id':r.id,'label':r.sku+' · '+r.name+'（'+r.unit+'）'} for r in items.values()]})
