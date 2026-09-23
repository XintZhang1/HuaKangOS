"""Deterministic management metrics; NOT statutory accounting or an audit opinion."""
from collections import Counter, defaultdict
from bisect import bisect_right
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select, func, or_, and_
from .models import MODULES, AuditLog
from .config import settings
from .db import today
from .services import PREFIXES

BASIS = ('金额单位为人民币分；汇总仅计入已审核记录。交付合同金额按实际交车日，维修结算金额按完工日；'
         '保费代收不计为门店营业收入，预计佣金单列；内部转账不计入门店总收支。'
         '销售和维修毛差仅为合同/结算金额减录入直接成本，不含税费、返利、薪酬、折旧等，非会计净利润。'
         '历史日期按当前数据库有效状态重新计算，不是时点账簿还原；已保存日报保留生成时快照。')


def source_revision(db) -> int:
    return db.scalar(select(func.max(AuditLog.id)).where(or_(
        and_(AuditLog.entity_type.in_(list(MODULES)),AuditLog.action.in_(['create','update','submit','approve','reject','advance','void','seed'])),
        and_(AuditLog.entity_type.in_(['flow','flow_master']),~AuditLog.action.in_(['download','export']))))) or 0


def load_data(db, end: date) -> dict:
    data = {module:list(db.scalars(select(model).where(model.business_date <= end).order_by(model.id))) for module,model in MODULES.items()}
    from .cash_basis import effective_cash
    data['cash']=effective_cash(db,data['cash'])
    # Date-indexed cumulative collections keep the dashboard O(days * rows), not O(sales * cash).
    events = defaultdict(list)
    fields = {'sales':'sale_id','repairs':'repair_id','policies':'policy_id'}
    categories = {'sales':{'sale_collection','refund'},'repairs':{'repair_collection','refund'},'policies':{'premium_collection','refund'}}
    for row in data['cash']:
        if row.approval_state != 'approved': continue
        for module,field in fields.items():
            linked = getattr(row,field)
            if linked and row.category in categories[module]:
                events[(module,linked)].append((row.business_date,row.amount_cents*(1 if row.direction=='in' else -1)))
    index = {}
    for key,values in events.items():
        dates,totals,total = [],[],0
        for event_day,amount in sorted(values):
            total += amount; dates.append(event_day); totals.append(total)
        index[key] = (dates,totals)
    from .flow_models import VehicleHold,Case
    data['_flow_delivered'] = set(db.scalars(select(VehicleHold.vehicle_id).join(Case,Case.id==VehicleHold.case_id).where(VehicleHold.delivered.is_(True),Case.completed_date<=end)))
    data['_collections'] = index
    data['_by_id'] = {module:{row.id:row for row in data[module]} for module in MODULES}
    return data


def approved(data, module, end):
    return [r for r in data[module] if r.approval_state == 'approved' and r.business_date <= end]


def collected(data, module, row_id, end):
    dates,totals = data['_collections'].get((module,row_id),([],[]))
    position = bisect_right(dates,end)-1
    return totals[position] if position >= 0 else 0


def daily_metrics(data, day: date):
    sales = [r for r in approved(data,'sales',day) if r.sale_stage == 'delivered' and r.delivery_date == day]
    repairs = [r for r in approved(data,'repairs',day) if r.repair_stage == 'completed' and r.completion_date == day]
    policies = [r for r in approved(data,'policies',day) if r.business_date == day]
    cash = [r for r in approved(data,'cash',day) if r.business_date == day]
    vehicles = approved(data,'vehicles',day)
    allocated = {r.vehicle_id:r for r in approved(data,'sales',day)}
    on_hand = [v for v in vehicles if v.id not in data.get('_flow_delivered',set()) and (v.id not in allocated or not allocated[v.id].delivery_date or allocated[v.id].delivery_date > day)]
    cash_in = sum(r.amount_cents for r in cash if r.direction == 'in' and r.category != 'transfer')
    cash_out = sum(r.amount_cents for r in cash if r.direction == 'out' and r.category != 'transfer')
    result = {
        'date':day.isoformat(), 'delivery_count':len(sales),
        'delivery_amount_cents':sum(r.contract_amount_cents for r in sales),
        'new_order_count':sum(r.business_date == day for r in approved(data,'sales',day)),
        'repair_completed_count':len(repairs),
        'repair_amount_cents':sum(r.labor_amount_cents+r.parts_amount_cents-r.discount_cents for r in repairs),
        'vehicle_gross_difference_cents':sum(r.contract_amount_cents-(r.purchase_cost_snapshot_cents or 0) for r in sales),
        'repair_gross_difference_cents':sum(r.labor_amount_cents+r.parts_amount_cents-r.discount_cents-r.cost_amount_cents for r in repairs),
        'policy_count':len(policies), 'policy_premium_cents':sum(r.premium_cents for r in policies),
        'expected_commission_cents':sum(r.commission_cents for r in policies),
        'cash_in_cents':cash_in, 'cash_out_cents':cash_out, 'net_cash_cents':cash_in-cash_out,
        'operating_net_cash_cents':sum(r.amount_cents*(1 if r.direction=='in' else -1) for r in cash if r.category not in {'capital','loan','transfer'}),
        'internal_transfer_cents':sum(r.amount_cents for r in cash if r.category == 'transfer'),
        'stock_count':len(on_hand), 'stock_cost_cents':sum(r.purchase_cost_cents for r in on_hand),
        'reserved_count':sum(v.id in allocated for v in on_hand),
        'available_count':sum(v.id not in allocated for v in on_hand),
        'aging_stock_count':sum((day-v.business_date).days > settings.inventory_aging for v in on_hand),
        'pending_approval_count':sum(r.approval_state == 'submitted' and r.business_date <= day for module in MODULES for r in data[module]),
        'daily_records_count':sum(r.business_date == day for module in MODULES for r in data[module]),
    }
    result['gross_difference_cents'] = result['vehicle_gross_difference_cents']+result['repair_gross_difference_cents']
    result['sales_receivable_cents'] = sum(max(0,r.contract_amount_cents-collected(data,'sales',r.id,day))
        for r in approved(data,'sales',day) if r.delivery_date and r.delivery_date <= day)
    result['repair_receivable_cents'] = sum(max(0,r.labor_amount_cents+r.parts_amount_cents-r.discount_cents-collected(data,'repairs',r.id,day))
        for r in approved(data,'repairs',day) if r.completion_date and r.completion_date <= day)
    return result


def rules_config():
    return {'rule_version':'1.0.0', 'inventory_aging_days':settings.inventory_aging,
        'repair_overdue_days':settings.repair_overdue, 'receivable_grace_days':settings.receivable_grace,
        'low_gross_margin_percent':settings.low_margin,'large_cash_amount_cents':settings.large_cash_yuan*100,
        'discount_review_percent':settings.discount_review, 'policy_commission_review_percent':30}


def detect(data, day: date):
    """Every evidence field is constructed from controlled codes, IDs, dates or numbers.
    No customer name, plate, VIN, phone, voucher, free-text note, or account is copied.
    Threshold matches are review leads, never a conclusion of fraud.
    """
    findings = []
    def add(rule, severity, module, row, title, evidence, action):
        findings.append({'rule_code':rule,'severity':severity,'entity_type':module,'entity_id':row.id,
            'ref':f'{PREFIXES[module]}-{row.id}','title':title,'evidence':evidence,'suggested_action':action})
    cars = {v.id:v for v in approved(data,'vehicles',day)}
    sales = approved(data,'sales',day)
    occupied = {r.vehicle_id:r for r in sales}
    for v in cars.values():
        if v.id in data.get('_flow_delivered',set()):continue
        s = occupied.get(v.id)
        if s and s.delivery_date and s.delivery_date <= day: continue
        age = (day-v.business_date).days
        if age > settings.inventory_aging:
            add('STOCK_AGING','medium','vehicles',v,'库存库龄超过复核阈值',
                {'age_days':age,'threshold_days':settings.inventory_aging,'purchase_cost_cents':v.purchase_cost_cents},
                '核对实车、入库日期、是否已售未出库，并评估库存处置计划。')
    for s in sales:
        cost = s.purchase_cost_snapshot_cents or 0
        gross = s.contract_amount_cents-cost
        if Decimal(gross)*100 < Decimal(str(settings.low_margin))*s.contract_amount_cents:
            add('SALE_LOW_MARGIN','high' if gross<0 else 'medium','sales',s,'销售毛差偏低或为负',
                {'contract_amount_cents':s.contract_amount_cents,'cost_snapshot_cents':cost,'gross_difference_cents':gross,'threshold_percent':settings.low_margin},
                '核对合同折扣、采购成本及厂家返利；负毛差也可能是已批准的促销，不能直接认定异常交易。')
        v = cars.get(s.vehicle_id)
        if v and v.list_price_cents and Decimal(v.list_price_cents-s.contract_amount_cents)*100 > Decimal(str(settings.discount_review))*v.list_price_cents:
            add('SALE_DISCOUNT','medium','sales',s,'销售折扣超过复核阈值',
                {'list_price_cents':v.list_price_cents,'contract_amount_cents':s.contract_amount_cents,'threshold_percent':settings.discount_review},
                '查看折扣授权和促销政策，检查是否存在金额录入错误。')
        net = collected(data,'sales',s.id,day)
        if net > s.contract_amount_cents:
            add('SALE_OVER_COLLECTION','high','sales',s,'销售净收款超过合同金额',
                {'contract_amount_cents':s.contract_amount_cents,'net_collected_cents':net,'excess_cents':net-s.contract_amount_cents},
                '逐笔核对流水和合同；排查重复录入、费用混记或退款关联错误。')
        if s.delivery_date and s.delivery_date <= day and (day-s.delivery_date).days > settings.receivable_grace and net < s.contract_amount_cents:
            add('SALE_RECEIVABLE','medium','sales',s,'已交车但仍有待收款',
                {'contract_amount_cents':s.contract_amount_cents,'net_collected_cents':net,'uncollected_cents':s.contract_amount_cents-net,'days_since_delivery':(day-s.delivery_date).days},
                '核对贷款放款进度、约定账期及银行到账；确认是正常待收款还是漏记。')
    policies = {p.id:p for p in approved(data,'policies',day)}
    for r in approved(data,'repairs',day):
        total = r.labor_amount_cents+r.parts_amount_cents
        billed = total-r.discount_cents
        completed = r.completion_date is not None and r.completion_date <= day
        overdue = (day-r.business_date).days > settings.repair_overdue or bool(r.due_date and r.due_date < day)
        if not completed and overdue:
            add('REPAIR_OVERDUE','medium','repairs',r,'维修工单未按期完工',
                {'open_days':(day-r.business_date).days,'due_date':r.due_date.isoformat() if r.due_date else None},
                '核对实际车辆状态、配件到货和预计完工时间，排查漏更新。')
        if billed < r.cost_amount_cents:
            add('REPAIR_NEGATIVE_MARGIN','high','repairs',r,'维修结算金额低于录入成本',
                {'billed_amount_cents':billed,'cost_amount_cents':r.cost_amount_cents},
                '核对工时、配件、优惠及质保/保险赔付安排。')
        if total and Decimal(r.discount_cents)*100 > Decimal(str(settings.discount_review))*total:
            add('REPAIR_DISCOUNT','medium','repairs',r,'维修优惠比例较高',
                {'before_discount_cents':total,'discount_cents':r.discount_cents,'threshold_percent':settings.discount_review},
                '核对活动政策、优惠审批和服务单明细。')
        net = collected(data,'repairs',r.id,day)
        if net > billed:
            add('REPAIR_OVER_COLLECTION','high','repairs',r,'维修净收款超过结算金额',
                {'billed_amount_cents':billed,'net_collected_cents':net},'核对重复收款、额外项目和退款记录。')
        if completed and (day-r.completion_date).days > settings.receivable_grace and net < billed:
            add('REPAIR_RECEIVABLE','medium','repairs',r,'维修已完工但仍有待收款',
                {'billed_amount_cents':billed,'net_collected_cents':net,'uncollected_cents':billed-net,'days_since_completion':(day-r.completion_date).days},
                '核实保险理赔、客户账期及收款是否漏录。')
        if r.repair_type == 'insurance':
            p = policies.get(r.policy_id)
            if not p:
                add('CLAIM_MISSING_POLICY','medium','repairs',r,'保险维修缺少有效关联保单',{},'补充关联保单，核对事故/维修对应的保险责任。')
            elif not p.start_date <= r.business_date <= p.end_date or p.plate_number.replace(' ','').upper() != r.plate_number.replace(' ','').upper():
                add('CLAIM_POLICY_MISMATCH','high','repairs',r,'保险维修与保单日期或车牌不一致',
                    {'policy_ref':f'P-{p.id}','date_within_policy':p.start_date <= r.business_date <= p.end_date,
                     'plate_matches':p.plate_number.replace(' ','').upper() == r.plate_number.replace(' ','').upper()},
                    '核对事故日与报修日差异、车牌变更和原始保单；本系统未采集事故日，不据此拒赔。')
    for p in policies.values():
        if p.commission_cents*100 > p.premium_cents*30:
            add('POLICY_COMMISSION','medium','policies',p,'预计佣金比例超过 30% 复核阈值',
                {'premium_cents':p.premium_cents,'commission_cents':p.commission_cents,'threshold_percent':30},
                '核对佣金合同、税费口径及是否把保费代收误填为佣金。')
    cash = approved(data,'cash',day)
    vouchers, payments = defaultdict(list), defaultdict(list)
    for c in cash:
        vouchers[(c.account.strip().lower(), c.voucher_no.strip().lower())].append(c)
        # Empty counterparties are not sufficient evidence of duplicate payment.
        if c.counterparty.strip():
            payments[(c.business_date,c.direction,c.amount_cents,c.account.strip(),c.counterparty.strip())].append(c)
        if c.payment_method == 'cash' and c.amount_cents > settings.large_cash_yuan*100:
            add('LARGE_CASH','medium','cash',c,'现金收支金额超过复核阈值',
                {'amount_cents':c.amount_cents,'direction':c.direction,'threshold_cents':settings.large_cash_yuan*100},
                '核对现金盘点、收据、经办与审批记录。')
        for module,field in [('sales','sale_id'),('repairs','repair_id'),('policies','policy_id'),('vehicles','vehicle_id')]:
            target_id = getattr(c,field)
            target = data['_by_id'][module].get(target_id) if target_id else None
            if target and c.business_date < target.business_date:
                add('PAYMENT_BEFORE_BUSINESS','low','cash',c,'流水日期早于关联业务日期',
                    {'payment_date':c.business_date.isoformat(),'related_date':target.business_date.isoformat(),'related_ref':f'{PREFIXES[module]}-{target.id}'},
                    '核对是否为正常预付款、订金，或日期与关联对象录错。')
    for group in vouchers.values():
        if len(group)>1:
            add('DUPLICATE_VOUCHER','high','cash',group[0],'同一账户存在重复凭证号',
                {'record_refs':[f'C-{r.id}' for r in group],'record_count':len(group)},
                '核对原始银行/支付凭证；同一凭证的合法拆分记账也可能触发，需要人工判断。')
    for group in payments.values():
        if len(group)>1:
            add('SIMILAR_PAYMENT','medium','cash',group[0],'同日同账户同对方出现相同金额流水',
                {'record_refs':[f'C-{r.id}' for r in group],'amount_cents':group[0].amount_cents,'direction':group[0].direction},
                '核对是否为正常分笔付款、重复录入或错误关联，避免直接删除。')
    for module in MODULES:
        rows = data[module]
        for r in rows:
            if r.approval_state == 'submitted' and r.business_date < day:
                add('PENDING_APPROVAL','low',module,r,'前期单据仍待审核，未计入已审核汇总',
                    {'business_date':r.business_date.isoformat(),'waiting_business_days':(day-r.business_date).days},
                    '审核原始单据；日报不会把待审核金额当成已审核业绩。')
    return findings


def build_snapshot(db, day: date):
    revision = source_revision(db)
    data = load_data(db,day)
    metrics = daily_metrics(data,day)
    previous = daily_metrics(data,day-timedelta(days=1))
    candidates = detect(data,day)
    records = []
    accounts, parties = {}, {}
    def alias(mapping, text, prefix):
        if not text: return None
        if text not in mapping: mapping[text] = f'{prefix}{len(mapping)+1}'
        return mapping[text]
    for module in MODULES:
        rows = data[module]
        for r in rows:
            if r.approval_state not in {'approved','submitted'}: continue
            row = {'ref':f'{PREFIXES[module]}-{r.id}','module':module,'business_date':r.business_date.isoformat(),'approval_state':r.approval_state}
            if module == 'vehicles':
                row.update(purchase_cost_cents=r.purchase_cost_cents,list_price_cents=r.list_price_cents,age_days=(day-r.business_date).days)
            elif module == 'sales':
                row.update(vehicle_ref=f'V-{r.vehicle_id}',contract_amount_cents=r.contract_amount_cents,cost_snapshot_cents=r.purchase_cost_snapshot_cents,
                    delivery_date=r.delivery_date.isoformat() if r.delivery_date else None,net_collected_cents=collected(data,'sales',r.id,day))
            elif module == 'repairs':
                row.update(repair_stage=r.repair_stage,repair_type=r.repair_type,labor_amount_cents=r.labor_amount_cents,parts_amount_cents=r.parts_amount_cents,
                    discount_cents=r.discount_cents,cost_amount_cents=r.cost_amount_cents,net_collected_cents=collected(data,'repairs',r.id,day))
            elif module == 'policies':
                row.update(premium_cents=r.premium_cents,commission_cents=r.commission_cents,start_date=r.start_date.isoformat(),end_date=r.end_date.isoformat())
            else:
                row.update(amount_cents=r.amount_cents,direction=r.direction,category=r.category,payment_method=r.payment_method,
                    account_alias=alias(accounts,r.account,'A'),counterparty_alias=alias(parties,r.counterparty,'P'))
            records.append(row)
    flagged = {f['ref'] for f in candidates}
    records.sort(key=lambda r:(r['ref'] not in flagged,r['business_date'] != day.isoformat(),r['ref']))
    # Candidates are also bounded ONLY for external AI. Full rule results are kept locally.
    ai_records = records[:settings.ai_max_records]
    ai_findings = candidates[:settings.ai_max_records]
    snapshot = {'business_date':day.isoformat(),'source_revision':revision,'currency':'CNY','amount_unit':'fen',
        'basis':BASIS,'metrics':metrics,'previous_day':previous,'rule_settings':rules_config(),
        'rule_findings':candidates,'record_count_before_ai_cap':len(records),'records':ai_records,
        'ai_record_count':len(ai_records),'ai_omitted_record_count':max(0,len(records)-len(ai_records)),
        'ai_omitted_finding_count':max(0,len(candidates)-len(ai_findings)),
        'provisional':day == today()}
    # Keep the original legacy snapshot for reproducibility. Combined totals are
    # explicitly separate and MUST NOT be added to the legacy totals.
    from .flow_models import Case,Task
    from .flow_engine import paid_amount
    from .flow_analytics import build_analytics,bounded
    from types import SimpleNamespace
    if db.scalar(select(Case.id).limit(1)):
        flow=build_analytics(db,SimpleNamespace(role='admin'),day,day)
        snapshot['workflow']={'metrics':flow['metrics'],'stock_as_of':flow['stock_as_of'],
            'basis':'新流程与既有记录的合并口径，不能与 metrics 相加；现金流水仅计一次。库存、待收款和待办按生成时当前状态。',
            'previous_day':build_analytics(db,SimpleNamespace(role='admin'),day-timedelta(days=1),day-timedelta(days=1))['metrics']}
        def add_flow(rule,row,title,evidence,action,severity='medium'):
            snapshot['rule_findings'].append({'rule_code':rule,'severity':severity,'entity_type':'flow','entity_id':row.id,
                'ref':f'WF-{row.id}','title':title,'evidence':evidence,'suggested_action':action})
        rows=bounded(db,Case);byid={r.id:r for r in rows}
        for task in bounded(db,Task,select(Task).where(Task.status=='open',Task.due_date<today())):
            row=byid.get(task.case_id)
            if row and row.business_date<=day:
                add_flow('FLOW_TASK_'+task.key.upper(),row,'业务任务超过计划日期',
                    {'as_of':today().isoformat(),'due_date':task.due_date.isoformat(),'task_id':task.id},'核对是否等待客户、材料或接手；确认负责人和下一次处理日期。')
        for row in rows:
            if row.business_date>day or row.state in {'cancelled','rejected'}:continue
            if row.kind in {'order','repair'} and row.cost_cents is not None and row.amount_cents<row.cost_cents:
                add_flow('FLOW_NEGATIVE_MARGIN',row,'约定金额低于直接成本',{'amount_cents':row.amount_cents,'cost_cents':row.cost_cents},'核对报价、录入成本和承担方；内部服务或促销不直接认定异常。')
            if row.state=='credit_open' and row.due_date and row.due_date<today():
                add_flow('FLOW_CREDIT_OVERDUE',row,'月结业务已过约定收款日期',{'due_date':row.due_date.isoformat(),'remaining_cents':row.amount_cents-paid_amount(db,row)},'核对约定账期、付款记录以及到账凭据。')
        snapshot['ai_omitted_finding_count']=max(0,len(snapshot['rule_findings'])-settings.ai_max_records)
    return snapshot


def external_payload(snapshot):
    # Strict top-level allowlist: never send database rows, audit histories or free-text notes.
    keys = ('business_date','currency','amount_unit','basis','metrics','previous_day','rule_settings','records',
            'record_count_before_ai_cap','ai_record_count','ai_omitted_record_count','ai_omitted_finding_count','provisional')
    result = {k:snapshot[k] for k in keys}
    if 'workflow' in snapshot:result['workflow']=snapshot['workflow']
    result['rule_findings'] = snapshot['rule_findings'][:settings.ai_max_records]
    return result


def dashboard(db, day: date, days: int):
    data = load_data(db,day)
    series = [daily_metrics(data,day-timedelta(days=i)) for i in range(days-1,-1,-1)]
    snapshot_keys = {'stock_count','stock_cost_cents','reserved_count','available_count','aging_stock_count',
                     'sales_receivable_cents','repair_receivable_cents','pending_approval_count'}
    totals = {key:(series[-1][key] if key in snapshot_keys else sum(s[key] for s in series)) for key in series[-1] if key != 'date'}
    return {'end_date':day.isoformat(),'start_date':series[0]['date'],'days':days,'totals':totals,'series':series,
            'basis':BASIS,'rule_counts':dict(Counter(x['severity'] for x in detect(data,day)))}
