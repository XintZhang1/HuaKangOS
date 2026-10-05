"""Management reporting with explicit period, stock and cohort denominators.
No statutory profit claims, no invented target or employee performance ranking.
Amounts stay integer fen until presentation; tables are the source for drill-down.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .config import settings
from decimal import Decimal
from sqlalchemy import select,func
from fastapi import HTTPException
from .db import today,utcnow
from .models import Vehicle,Sale,Repair,CashEntry,Store,User
from .flow_models import Case,Task,Customer,FlowEvent,VehicleHold,PaymentLink,Item,StockMove,Member,MemberEntry,FileAsset
from .flow_specs import SPECS,STATES,TERMINAL
from .security import ROLES

LIMIT=25000

def bounded(db,model,stmt=None):
    q=stmt if stmt is not None else select(model)
    # Never silently omit excess rows from a financial report.
    if (db.scalar(select(func.count()).select_from(q.subquery())) or 0)>LIMIT:
        raise HTTPException(422,'数据量超过本版报表处理上限，请由管理员升级聚合查询；本次未返回截断统计')
    return list(db.scalars(q))


def yuan(n):return format(Decimal(n)/100,'.2f') if n is not None else '—'


def build_analytics(db,user,start=None,end=None,cash_definition_version=7,include_vehicle_income=True):
    start_explicit=start is not None;end_explicit=end is not None
    end=end or today();start=start or end-timedelta(days=29)
    if start>end or end>today() or (end-start).days>365:raise HTTPException(422,'请选择不晚于今天、跨度不超过一年的日期范围')
    in_period=lambda d: d is not None and start<=d<=end
    stores={s.id:s.name for s in db.scalars(select(Store))}
    # Store 0 contains global audit records; it is not another operating store.
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([sid for sid in db.info.get('store_scope',()) if sid])>1)
    case_stmt=select(Case)
    if aggregate or user.role=='finance':case_stmt=case_stmt.where(Case.kind!='customer_care')
    cases=bounded(db,Case,case_stmt);byid={r.id:r for r in cases}
    cash=bounded(db,CashEntry,select(CashEntry).where(CashEntry.approval_state=='approved'))
    from .cash_basis import effective_cash
    cash=effective_cash(db,cash,cash_definition_version)
    payments=bounded(db,PaymentLink);wallet=bounded(db,MemberEntry)
    cash_by_id={c.id:c for c in cash}
    case_paid=defaultdict(int)
    for p in payments:case_paid[p.case_id]+=p.amount_cents*(1 if p.direction=='in' else -1)
    from .business_finance_models import FinanceCreditLink
    for p in bounded(db,FinanceCreditLink):case_paid[p.case_id]+=p.amount_cents
    for e in wallet:
        if e.purpose=='consume':case_paid[e.case_id]-=e.amount_cents
    from .group_models import GroupPaymentLink
    for p in bounded(db, GroupPaymentLink):
        case_paid[p.case_id] += p.amount_cents
    from .group_benefits_models import BenefitPaymentLink
    from .group_benefits_service import analytics_rows as benefit_analytics
    benefit_data=benefit_analytics(db,user)
    benefit_discounts=defaultdict(int)
    for entry in benefit_data['entries']:benefit_discounts[entry['case_id']]+=entry['external_discount_cents']
    for p in bounded(db,BenefitPaymentLink):case_paid[p.case_id]+=p.amount_cents
    from .repair_package_models import PackagePaymentLink
    from .repair_package_service import analytics_rows as package_analytics
    package_data=package_analytics(db,user)
    for p in bounded(db,PackagePaymentLink):case_paid[p.case_id]+=p.amount_cents
    from .repair_service import is_detailed, gross_revenue_amount, receivable_amount
    from .service_orders_service import is_detailed as detailed_service,source_summary as service_summary
    from .insurance_service import is_detailed as detailed_insurance,summary as insurance_summary
    from .addon_service import is_detailed as detailed_addon,totals as addon_totals
    from .aftercare_service import net_charge
    from .group_aftercare_models import GroupAftercareHold
    original_discounts=benefit_discounts.copy()
    for h in bounded(db,GroupAftercareHold,select(GroupAftercareHold).where(GroupAftercareHold.status=='applied')):
        original_discounts[h.source_case_id]+=h.discount_cents
    for entry in package_data['entries']:
        benefit_discounts[entry['case_id']]+=entry['external_discount_cents']
        if entry['purpose']=='capture':original_discounts[entry['case_id']]+=entry['external_discount_cents']
    legacy_sales=bounded(db,Sale,select(Sale).where(Sale.approval_state=='approved'))
    legacy_repairs=bounded(db,Repair,select(Repair).where(Repair.approval_state=='approved'))
    legacy_paid=defaultdict(int)
    for p in cash:
        key=('sales',p.sale_id) if p.sale_id else (('repairs',p.repair_id) if p.repair_id else None)
        if key and p.category in {'sale_collection','repair_collection','refund'}:legacy_paid[key]+=p.amount_cents*(1 if p.direction=='in' else -1)
    tables={}
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def add(rows,values,route=None,**meta):rows.append({'values':values,'route':route,**meta})
    orders=table('orders','销售订单明细',['订单号','门店','客户','订单日期','当前状态','约定金额（元）','累计已收（元）','直接成本（元）'])
    deliveries=table('deliveries','交付明细',['订单号','门店','客户','交付日期','交付金额（元）','直接成本（元）','直接毛差（元）'])
    repair_rows=table('repairs','维修工单明细',['工单号','门店','客户','开单日期','当前状态','结算金额（元）','累计已收（元）','结算方'])
    repair_settlements=table('repair_settlements','维修结算明细',['工单号','门店','客户','结算日期','结算金额（元）','结算方'])
    member_entries=table('member_entries','会员储值变动明细',['业务单号','门店','发生日期','变动类型','余额变化（元）'])
    receipt_rows=table('cash','实际收支明细',['单号','门店','发生日期','方向','分类','金额（元）','账户','凭证号'])
    receivable_rows=table('receivables','当前待收款',['业务单号','门店','客户','业务','约定金额（元）','累计已收（元）','尚待收取（元）','应收状态'])
    vehicle_rows=table('inventory','当前车辆库存',['入库单号','门店','车型','车架号','库存状态','入库日期','库龄（天）','采购成本（元）'])
    item_rows=table('materials','当前物资库存',['物资编码','门店','名称','账面数量','占用数量','可用数量','单位','账面成本（元）','补货提醒'])
    member_rows=table('members','当前会员储值',['会员号','门店','客户','储值余额（元）','启用状态'])
    task_rows=table('tasks','当前未完成任务',['业务单号','门店','任务','负责岗位','接手员工','计划日期','状态'])
    lead_rows=table('leads','接待客户批次',['业务单号','门店','客户','接待日期','当前状态','曾转意向','曾转订单'])
    movement_rows=table('movements','物资出入库明细',['业务单号','门店','日期','物资','类型','数量','单位','成本变化（元）'])
    daily={d:{'orders':0,'delivery':0,'delivery_count':0,'repair':0,'in':0,'out':0,'material_in':0,'material_out':0} for d in [start+timedelta(days=i) for i in range((end-start).days+1)]}
    group=defaultdict(lambda:dict(orders=0,delivery=0,delivery_count=0,repair=0,cash_in=0,cash_out=0))
    delivery_total=0;delivery_cost=0;delivery_missing=0;delivery_count=0;new_orders=0;repair_total=0;new_repairs=0
    current_due=0;overdue_due=0
    from .business_finance_models import FinanceReturnReceivable
    from .business_finance_return_adjustments import effective_target
    other_return_receivables={r.case_id:r for r in bounded(db,FinanceReturnReceivable)}
    from .vehicle_income_models import VehicleIncomeOrder,VehicleIncomeCash
    from .vehicle_income_service import totals as vehicle_income_totals
    income_orders={r.id:r for r in bounded(db,VehicleIncomeOrder)} if include_vehicle_income else {}
    scope_ids=db.info.get('store_scope') or ([db.info['write_store']] if db.info.get('write_store') else [])
    for sid in scope_ids:
        if sid:group[sid]
    case_delivery=[]
    def receipt_state(amount,paid,is_overdue):
        if paid>amount:return '超额收款待核对'
        return '已超约定日期' if is_overdue else '尚待收取'
    for r in cases:
        store=stores.get(r.store_id,'');route={'type':'case','id':r.id};customer=r.title.split(' · ')[0]
        paid=case_paid[r.id]
        if r.id in income_orders and r.state!='cancelled':
            t=vehicle_income_totals(db,r);gap=t['receivable_cents'];late=bool(r.due_date and r.due_date<today())
            if gap:
                current_due+=gap;overdue_due+=gap if late else 0
                add(receivable_rows,['门店汇总来源' if aggregate else r.number,store,'往来单位汇总' if aggregate else income_orders[r.id].supplier_snapshot['name'],'厂家及供应商整车其他收入',yuan(t['target_cents']),yuan(t['net_received_cents']),yuan(gap),'已超约定日期' if late else '尚待收取'],None if aggregate else route,amount_cents=gap)
        if r.id in other_return_receivables:
            original=other_return_receivables[r.id]
            expected=effective_target(db,original) if cash_definition_version>=4 else original.amount_cents
            gap=max(0,expected-paid)
            if gap:
                current_due+=gap
                add(receivable_rows,[r.number,store,'原退货供应方','其他入库原单退货',yuan(expected),yuan(paid),yuan(gap),'尚待收取'],route,amount_cents=gap)
        if r.kind=='order':
            if in_period(r.business_date):
                new_orders+=1;daily[r.business_date]['orders']+=1;group[r.store_id]['orders']+=1
                add(orders,[r.number,store,customer,r.business_date.isoformat(),STATES[r.state],yuan(r.amount_cents),yuan(paid),yuan(r.cost_cents)],route)
            if r.state=='delivered' and in_period(r.completed_date):case_delivery.append((r.number,r.store_id,customer,r.completed_date,r.amount_cents,r.cost_cents,route))
        if r.kind=='repair':
            if in_period(r.business_date):
                new_repairs+=1;add(repair_rows,[r.number,store,customer,r.business_date.isoformat(),STATES[r.state],yuan(r.amount_cents),yuan(paid),r.data.get('payer','待确认')],route)
            released=r.data.get('released_date');release_day=date.fromisoformat(released) if released else None
            if in_period(release_day) and r.data.get('payer')!='内部':
                external=(gross_revenue_amount(db,r) if is_detailed(r) else r.amount_cents)-original_discounts[r.id]
                if external<0:raise HTTPException(409,'维修外部承担与权益抵扣不一致，请核对原账')
                add(repair_settlements,[r.number,store,customer,release_day.isoformat(),yuan(external),'多方承担' if is_detailed(r) else r.data.get('payer','待确认')],route)
                repair_total+=external;daily[release_day]['repair']+=external;group[r.store_id]['repair']+=external
        if is_detailed(r):
            from .repair_service import receivable_rows as repair_receivables
            for a in repair_receivables(db,r):
                if a['due_cents']<=0:continue
                late=bool(a['due_date'] and a['due_date']<today())
                current_due+=a['due_cents'];overdue_due+=a['due_cents'] if late else 0
                add(receivable_rows,[r.number,store,a['payer_name'],'维修多方承担',yuan(a['amount_cents']),yuan(a['paid_cents']),yuan(a['due_cents']),'已超约定日期' if late else '尚待收取'],route,amount_cents=a['due_cents'],payer_type=a['payer_type'],payer_name=a['payer_name'])
        if r.kind=='retail' and r.flow_version==2:
            from .retail_service import totals as retail_totals
            amount=retail_totals(db,r);gap=amount['receivable_cents']
            if gap:
                current_due+=gap
                add(receivable_rows,[r.number,store,customer,'精品销售',yuan(amount['charge_cents']),yuan(amount['net_paid_cents']),yuan(gap),'尚待收取'],route,amount_cents=gap)
        if detailed_service(r):
            summary=service_summary(db,r)
            if summary['authorized']:
                for bucket,label in [('fee','本店服务费'),('pass','客户代缴本金')]:
                    charge=summary[bucket+'_charge_cents'];settled=summary[bucket+'_paid_cents'];gap=max(0,charge-settled)
                    if not gap:continue
                    late=bool(r.due_date and r.due_date<today())
                    current_due+=gap;overdue_due+=gap if late else 0
                    add(receivable_rows,[r.number,store,customer,label,yuan(charge),yuan(settled),yuan(gap),'已超约定日期' if late else '尚待收取'],route,amount_cents=gap)
        if detailed_insurance(r) and r.state not in {'cancelled','rejected'}:
            summary=insurance_summary(db,r)
            from .insurance_models import InsuranceConsent
            authorized=db.scalar(select(InsuranceConsent.id).where(InsuranceConsent.quote_id==r.data.get('insurance_quote_id')))
            if authorized:
                for label,charge,settled in [('客户原保费',summary['customer_charge_cents'],summary['customer_paid_cents']),('保险公司已确认佣金',summary['confirmed_commission_cents'],summary['actual_commission_cents'])]:
                    gap=max(0,charge-settled)
                    if gap:
                        current_due+=gap
                        add(receivable_rows,[r.number,store,customer,label,yuan(charge),yuan(settled),yuan(gap),'按原保单核对'],route,amount_cents=gap)
        if detailed_addon(r) and r.state not in {'cancelled','rejected'}:
            from .addon_models import AddonAuthorization
            if db.scalar(select(AddonAuthorization.id).where(AddonAuthorization.quote_id==r.data.get('addon_quote_id'))):
                summary=addon_totals(db,r);gap=summary['receivable_cents']
                if gap:
                    current_due+=gap
                    add(receivable_rows,[r.number,store,customer,'加装商品及安装费',yuan(summary['charge_cents']),yuan(summary['paid_cents']),yuan(gap),'按原授权明细核对'],route,amount_cents=gap)
        if not is_detailed(r) and not detailed_service(r) and not detailed_insurance(r) and not detailed_addon(r) and r.kind in {'order','repair','addon','agency','insurance'} and r.state not in {'cancelled','rejected','cancel_review','refund_pending'} and net_charge(db,r)>paid and not r.data.get('internal_settled') and not (r.kind=='repair' and r.data.get('payer')=='内部'):
            charge=net_charge(db,r);gap=charge-paid
            due=r.due_date;overdue=bool(due and due<today() and (r.state in {'delivered','credit_open','completed'}))
            current_due+=gap;overdue_due+=gap if overdue else 0
            if r.kind=='repair':
                payer=r.data.get('payer')
                payer_type={'客户':'customer','保险公司':'insurer','厂家':'manufacturer','内部':'internal'}.get(payer) if isinstance(payer,str) else None
                payer_name=payer if payer_type is not None else None
            else:
                # These original non-detailed customer-charge families are explicit in business_finance_sources.
                payer_type='customer' if r.kind in {'order','addon','agency','insurance'} else None
                payer_name=customer if payer_type is not None else None
            add(receivable_rows,[r.number,store,customer,SPECS[r.kind]['label'],yuan(charge),yuan(paid),yuan(gap),receipt_state(charge,paid,overdue)],route,amount_cents=gap,payer_type=payer_type,payer_name=payer_name)
    for r in legacy_sales:
        store=stores.get(r.store_id,'');route={'type':'legacy','module':'sales','id':r.id}
        if in_period(r.business_date):
            new_orders+=1;daily[r.business_date]['orders']+=1;group[r.store_id]['orders']+=1
            add(orders,[r.doc_no,store,r.customer_name,r.business_date.isoformat(),'已提车' if r.sale_stage=='delivered' else '已确认订单',yuan(r.contract_amount_cents),yuan(legacy_paid['sales',r.id]),yuan(r.purchase_cost_snapshot_cents)],route)
        if r.sale_stage=='delivered' and in_period(r.delivery_date):case_delivery.append((r.doc_no,r.store_id,r.customer_name,r.delivery_date,r.contract_amount_cents,r.purchase_cost_snapshot_cents,route))
        due=max(0,r.contract_amount_cents-legacy_paid['sales',r.id]);overdue=r.sale_stage=='delivered' and (today()-r.delivery_date).days>3
        if due:
            current_due+=due;overdue_due+=due if overdue else 0
            add(receivable_rows,[r.doc_no,store,r.customer_name,'既有销售单',yuan(r.contract_amount_cents),yuan(legacy_paid['sales',r.id]),yuan(due),'已交付待核对' if overdue else '尚待收取'],route,amount_cents=due)
    for number,store_id,customer,d,amount,cost,route in case_delivery:
        delivery_count+=1;delivery_total+=amount;delivery_missing+=int(cost is None);delivery_cost+=cost or 0
        daily[d]['delivery']+=amount;daily[d]['delivery_count']+=1;group[store_id]['delivery']+=amount;group[store_id]['delivery_count']+=1
        add(deliveries,[number,stores.get(store_id,''),customer,d.isoformat(),yuan(amount),yuan(cost),yuan(amount-cost) if cost is not None else '成本待核对'],route)
    for r in legacy_repairs:
        if in_period(r.business_date):
            new_repairs+=1;add(repair_rows,[r.doc_no,stores.get(r.store_id,''),r.customer_name,r.business_date.isoformat(),'已完工' if r.repair_stage=='completed' else '维修中',yuan(r.labor_amount_cents+r.parts_amount_cents-r.discount_cents),yuan(legacy_paid['repairs',r.id]),'既有记录'],{'type':'legacy','module':'repairs','id':r.id})
        if r.repair_stage=='completed' and in_period(r.completion_date):
            amount=r.labor_amount_cents+r.parts_amount_cents-r.discount_cents
            add(repair_settlements,[r.doc_no,stores.get(r.store_id,''),r.customer_name,r.completion_date.isoformat(),yuan(amount),'既有记录'],{'type':'legacy','module':'repairs','id':r.id})
            repair_total+=amount;daily[r.completion_date]['repair']+=amount;group[r.store_id]['repair']+=amount
        due=max(0,r.labor_amount_cents+r.parts_amount_cents-r.discount_cents-legacy_paid['repairs',r.id])
        if due:
            current_due+=due;add(receivable_rows,[r.doc_no,stores.get(r.store_id,''),r.customer_name,'既有维修单',yuan(r.labor_amount_cents+r.parts_amount_cents-r.discount_cents),yuan(legacy_paid['repairs',r.id]),yuan(due),'尚待收取'],{'type':'legacy','module':'repairs','id':r.id},amount_cents=due)
    category_labels={'sale_collection':'车辆收款','repair_collection':'维修收款','premium_collection':'保费代收','commission':'保险佣金','vehicle_purchase':'车辆采购','operating_expense':'经营支出','refund':'业务退款','capital':'资金投入','loan':'借款','transfer':'内部转账','workflow_refund':'流程退款'}
    category_labels.update({'workflow_'+k:('会员充值' if k=='member_topup' else '保费代收' if k=='insurance' else SPECS[k]['label']+'收款') for k in SPECS})
    category_labels.update(group_member_topup='集团会员本金充值', group_member_refund='集团会员本金退款',procurement_payment='物资采购付款',procurement_refund='采购原款退款',benefit_purchase='集团券包购买预收',benefit_refund='集团券包原款退款')
    category_labels['business_finance_other_return_refund']='供应方超收原款实际退回'
    category_labels.update(repair_package_purchase='混合维修套餐实际预收',repair_package_refund='混合维修套餐未用原款退款')
    category_labels.update(group_member_fee='会员续会收款',group_member_fee_refund='会员续会原款退款',business_finance_member_fee_corrected='会员续会收款',business_finance_member_fee_reverse='续会费登记纠错冲正')
    income=expense=0;cash_categories=defaultdict(int);cash_to_case={p.cash_id:p.case_id for p in payments}
    from .reconciliation_service import settlement_rows,internal_cash_ids
    clearing_data=settlement_rows(db,user);internal_ids=internal_cash_ids(db)
    internal_rows=table('internal_cash','期间门店内部实际收支',['单号','门店','日期','方向','金额（元）','账户','凭证号'])
    internal_income=internal_expense=0
    for entry in clearing_data['cash']:
        if entry.get('case_id'):cash_to_case[entry['cash_id']]=entry['case_id']
    category_labels.update(workflow_transfer_recovery='运输损失实际追偿到账',workflow_transfer_rec_return='运输追偿原款退回',interstore_clearing='店间实际清算',vehicle_procurement_payment='整车采购实际付款',vehicle_procurement_refund='整车采购原款退款')
    from .procurement_models import PurchasePayment
    for entry in benefit_data['entries']:
        if entry['cash_id']:cash_to_case[entry['cash_id']]=entry['case_id']
    for entry in package_data['purchases']+package_data['refunds']:
        if entry['cash_id']:cash_to_case[entry['cash_id']]=entry['case_id']
    for p in bounded(db,PurchasePayment):cash_to_case[p.cash_id]=p.case_id
    from .vehicle_procurement_models import VehiclePurchasePayment
    for p in bounded(db,VehiclePurchasePayment):cash_to_case[p.cash_id]=p.case_id
    from .business_finance_models import FinanceCashBatch,FinanceAdvanceEntry
    for p in bounded(db,FinanceCashBatch):cash_to_case[p.cash_id]=p.case_id
    for p in bounded(db,FinanceAdvanceEntry):
        if p.cash_id:cash_to_case[p.cash_id]=p.case_id
    from .membership_models import MembershipFee
    for p in bounded(db,MembershipFee):cash_to_case[p.cash_id]=p.case_id
    if cash_definition_version>=7:
        from .membership_fee_correction_models import MembershipFeeCorrection
        for p in bounded(db,MembershipFeeCorrection):
            cash_to_case[p.reversing_cash_id]=p.case_id
            cash_to_case[p.corrected_cash_id]=p.case_id
    if cash_definition_version>=4:
        from .business_finance_models import FinanceStoredCorrection
        for p in bounded(db,FinanceStoredCorrection):
            cash_to_case[p.reversing_cash_id]=p.case_id
            if p.corrected_cash_id:cash_to_case[p.corrected_cash_id]=p.case_id
    from .service_orders_models import ServicePassEntry
    for p in bounded(db,VehicleIncomeCash):cash_to_case[p.cash_id]=p.case_id
    category_labels.update(vehicle_other_income_in='厂家及供应商整车收入实际到账',vehicle_other_income_out='厂家及供应商原款实际退回')
    for p in bounded(db,ServicePassEntry):cash_to_case[p.cash_id]=p.case_id
    from .insurance_models import InsurancePassEntry,InsuranceCommissionPayment
    for model in (InsurancePassEntry,InsuranceCommissionPayment):
        for p in bounded(db,model):cash_to_case[p.cash_id]=p.case_id
    from .transfer_exception_analytics import analytics_rows as transport_sources
    transport_source_data=transport_sources(db,user)
    from .vehicle_transport_analytics import source_rows as vehicle_transport_sources
    vehicle_transport_data=vehicle_transport_sources(db,user)
    for p in vehicle_transport_data['cash']:
        if p['case_id']:cash_to_case[p['cash_id']]=p['case_id']
    category_labels.update(workflow_vehicle_loss_recovery='整车原损失赔款实际到账',workflow_vehicle_loss_return='整车原赔款实际退款')
    for p in transport_source_data['recovery_cash']:
        if p['case_id']:cash_to_case[p['cash_id']]=p['case_id']
    category_labels.update(workflow_ins_premium='客户保费代收',workflow_ins_premium_refund='客户原保费退款',workflow_ins_disburse='保险公司实际代缴',workflow_ins_insurer_return='保险公司原保费退回',workflow_ins_commission_in='保险佣金实际到账',workflow_ins_commission_out='保险原佣金退回')
    category_labels.update(service_pass_pay='客户原款实际代缴',service_pass_return='第三方代缴原款退回',service_customer_refund='客户服务原款退款')
    for p in cash:
        if not in_period(p.business_date) or p.category=='transfer':continue
        if p.id in internal_ids or p.category=='interstore_clearing':
            if p.direction=='in':internal_income+=p.amount_cents
            else:internal_expense+=p.amount_cents
            route={'type':'case','id':cash_to_case[p.id]} if p.id in cash_to_case else {'type':'legacy','module':'cash','id':p.id}
            add(internal_rows,[p.doc_no,stores.get(p.store_id,''),p.business_date.isoformat(),'收入' if p.direction=='in' else '支出',yuan(p.amount_cents),p.account,p.voucher_no],route,amount_cents=p.amount_cents*(1 if p.direction=='in' else -1))
            if aggregate:continue
        sign=1 if p.direction=='in' else -1
        if sign>0:income+=p.amount_cents;daily[p.business_date]['in']+=p.amount_cents;group[p.store_id]['cash_in']+=p.amount_cents
        else:expense+=p.amount_cents;daily[p.business_date]['out']+=p.amount_cents;group[p.store_id]['cash_out']+=p.amount_cents
        label=category_labels.get(p.category,'其他收支');cash_categories[label]+=p.amount_cents*sign
        route={'type':'case','id':cash_to_case[p.id]} if p.id in cash_to_case else {'type':'legacy','module':'cash','id':p.id}
        if aggregate and p.category in {'vehicle_other_income_in','vehicle_other_income_out'}:
            add(receipt_rows,['门店汇总来源',stores.get(p.store_id,''),p.business_date.isoformat(),'收入' if sign>0 else '支出',label,yuan(p.amount_cents),'汇总账户','汇总凭据'],None)
            continue
        add(receipt_rows,[p.doc_no,stores.get(p.store_id,''),p.business_date.isoformat(),'收入' if sign>0 else '支出',label,yuan(p.amount_cents),p.account,p.voucher_no],route)
    from .vehicle_transfer_analytics import current_vehicles
    vehicle_transfer_holds,vehicle_transit,vehicle_clearing=current_vehicles(db,user,bounded)
    from .vehicle_transfer_analytics import availability_flags
    vehicle_flags=availability_flags(db)
    from .vehicle_operations_models import VehicleOperation,VehiclePosition
    from .vehicle_operations_service import TERMINAL as vehicle_operation_terminal
    active_vehicle_operations={r.source_vehicle_id:r for r in bounded(db,VehicleOperation,select(VehicleOperation).where(VehicleOperation.status.notin_(vehicle_operation_terminal)))}
    vehicle_positions={r.vehicle_id:r for r in bounded(db,VehiclePosition)}
    vehicles=bounded(db,Vehicle,select(Vehicle).where(Vehicle.approval_state=='approved'))
    holds={h.vehicle_id:h for h in bounded(db,VehicleHold)};sold={s.active_vehicle_id for s in legacy_sales if s.sale_stage=='delivered'};reserved={s.active_vehicle_id for s in legacy_sales if s.sale_stage=='ordered'}
    aging=Counter({'0—30天':0,'31—60天':0,'61—90天':0,'90天以上':0});stock_state=Counter({'可售':0,'已预订':0});inventory_cost=0
    for v in vehicles:
        hold=holds.get(v.id)
        if v.id in sold or (hold and hold.delivered):continue
        age=max(0,(today()-v.business_date).days);bucket='0—30天' if age<=30 else '31—60天' if age<=60 else '61—90天' if age<=90 else '90天以上'
        operation=active_vehicle_operations.get(v.id);position=vehicle_positions.get(v.id)
        state='店内移库在途' if position and position.status=='transit' else '出库待客户交接' if position and position.status=='handover' else '车辆作业占用' if operation else '采购退车占用' if vehicle_flags.get(v.id)=='purchase_return' else '调拨占用' if v.id in vehicle_transfer_holds else '已预订' if v.id in reserved or hold else '可售'
        aging[bucket]+=1;stock_state[state]+=1;inventory_cost+=v.purchase_cost_cents
        add(vehicle_rows,[v.doc_no,stores.get(v.store_id,''),v.model,v.vin,state,v.business_date.isoformat(),age,yuan(v.purchase_cost_cents)],{'type':'legacy','module':'vehicles','id':v.id},category=bucket)
    items=bounded(db,Item);item_by_id={i.id:i for i in items};material_value=0;low_stock=0
    for i in items:
        from .inventory_availability import reserved_quantity,available_quantity
        available=available_quantity(db,i);reserved=reserved_quantity(db,i.id)
        material_value+=i.inventory_value_cents;low=available<=i.reorder_milli and i.active;low_stock+=int(low)
        add(item_rows,[i.sku,stores.get(i.store_id,''),i.name,format(Decimal(i.quantity_milli)/1000,'f'),format(Decimal(reserved)/1000,'f'),format(Decimal(available)/1000,'f'),i.unit,yuan(i.inventory_value_cents),'需补货' if low else '正常'],{'type':'master','module':'items','id':i.id})
    moves=bounded(db,StockMove,select(StockMove).where(StockMove.business_date>=start,StockMove.business_date<=end))
    for m in moves:
        item=item_by_id.get(m.item_id);c=byid.get(m.case_id)
        if m.value_cents>=0:daily[m.business_date]['material_in']+=m.value_cents
        else:daily[m.business_date]['material_out']-=m.value_cents
        add(movement_rows,[c.number if c else '',stores.get(m.store_id,''),m.business_date.isoformat(),item.name if item else '',{'purchase':'采购入库','procurement_receive':'采购分批入库','procurement_return':'采购退货出库','transfer_out':'店间调拨发出','transfer_in':'店间调拨验收','transfer_return':'拒收退回入库','issue':'维修领料','return':'维修退料','count':'盘点差异','procurement_receipt':'采购分批入库','repair_issue_v3':'维修明细领料','repair_return_v3':'维修明细退料','retail_dispatch':'精品实际出库','retail_return':'精品原单退货','wh_other_in':'其他实际入库','wh_other_return':'其他入库原单退回','wh_consumable':'耗材领用','wh_consume_return':'耗材原单退回','wh_gift':'礼品领用','wh_gift_return':'礼品原单退回','wh_disposal':'其他实际出库','wh_count':'实盘批准差异'}.get(m.purpose,m.purpose),format(Decimal(m.quantity_milli)/1000,'f'),item.unit if item else '',yuan(m.value_cents)],{'type':'case','id':m.case_id})
    customers={c.id:c for c in bounded(db,Customer)};members=bounded(db,Member);balance=0
    for m in members:
        balance+=m.balance_cents;customer=customers.get(m.customer_id)
        add(member_rows,[m.number,stores.get(m.store_id,''),customer.name if customer else '',yuan(m.balance_cents),'启用' if m.active else '停用'],{'type':'master','module':'members','id':m.id})
    local_day=lambda e:e.occurred_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()
    member_period=[e for e in wallet if in_period(local_day(e))]
    for e in member_period:
        c=byid.get(e.case_id)
        add(member_entries,[c.number if c else '',stores.get(e.store_id,''),local_day(e).isoformat(),{'topup':'充值到账','consume':'余额消费','refund':'余额退款'}.get(e.purpose,'其他'),yuan(e.amount_cents)],{'type':'case','id':e.case_id})
    member_topup=sum(e.amount_cents for e in member_period if e.purpose=='topup');member_use=-sum(e.amount_cents for e in member_period if e.purpose=='consume');member_refund=-sum(e.amount_cents for e in member_period if e.purpose=='refund')
    tasks=[t for t in bounded(db,Task,select(Task).where(Task.status=='open')) if t.case_id in byid];task_by_role=Counter();overdue=0
    user_names={u.id:u.display_name for u in db.scalars(select(User))}
    for t in tasks:
        r=byid.get(t.case_id)
        if not r:continue
        late=t.due_date<today();overdue+=int(late);task_by_role[ROLES.get(t.role,t.role)]+=1
        add(task_rows,[r.number,stores.get(t.store_id,''),t.title,ROLES.get(t.role,t.role),user_names.get(t.assignee_id,''),t.due_date.isoformat(),'已过计划日期' if late else '待处理'],{'type':'case','id':r.id})
    leads=[r for r in cases if r.kind=='lead' and in_period(r.business_date)]
    leadids={r.id for r in leads}
    events=bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.case_id.in_(leadids))) if leads else []
    intended={e.case_id for e in events if e.action in {'intent','reserve'}}
    converted={r.parent_id for r in cases if r.kind=='order' and r.parent_id in leadids}
    intended|=converted
    intended|={r.id for r in leads if r.state=='intent'}
    for r in leads:
        add(lead_rows,[r.number,stores.get(r.store_id,''),r.title.split(' · ')[0],r.business_date.isoformat(),STATES[r.state],'是' if r.id in intended else '否','是' if r.id in converted else '否'],{'type':'case','id':r.id})
    legacy_note='包含既有已审核销售、维修和收支；既有记录保留原口径。'
    labels=[d.strftime('%m-%d') for d in daily]
    charts=[]
    def chart(key,title,type,labels,series,unit,table,section,caption=''):
        charts.append(dict(id=key,title=title,type=type,labels=labels,series=series,unit=unit,table=table,section=section,caption=caption))
    series=lambda name,key:dict(name=name,values=[x[key] for x in daily.values()])
    chart('delivery','车辆交付金额','line',labels,[series('交付金额','delivery')],'cents','deliveries','overview')
    chart('cash_trend','实际收支走势','line',labels,[series('收入','in'),series('支出','out')],'cents','cash','overview','含会员充值及资金性往来；不是营业收入。')
    chart('store','门店交付金额','bar',[stores.get(k,'') for k in sorted(group)],[dict(name='交付金额',values=[group[k]['delivery'] for k in sorted(group)])],'cents','deliveries','overview')
    chart('orders_trend','新增订单数量','line',labels,[series('新增订单','orders')],'count','orders','sales')
    chart('cohort','同批接待客户转化','bar',['本期接待','曾转意向','曾转订单'],[dict(name='接待记录数',values=[len(leads),len(intended),len(converted)])],'count','leads','sales','只跟踪所选期间建立的同一批接待记录，截至今天；不是各阶段存量相除。')
    chart('aging','当前车辆库龄','bar',list(aging),[dict(name='车辆数',values=list(aging.values()))],'count','inventory','inventory','当前库存快照，不随报表日期改变。')
    chart('stock_state','当前库存状态','bar',list(stock_state),[dict(name='车辆数',values=list(stock_state.values()))],'count','inventory','inventory')
    repair_counts=Counter(row['values'][4] for row in repair_rows)
    chart('repair_state','本期工单的当前进度','bar',list(repair_counts),[dict(name='工单数',values=list(repair_counts.values()))],'count','repairs','repair')
    chart('repair_value','维修结算金额','line',labels,[series('结算金额','repair')],'cents','repair_settlements','repair','新流程按实际交还客户日，内部承担不计入；既有单据按原完工日。')
    chart('cash_category','收支分类净额','bar',list(cash_categories),[dict(name='分类净额',values=list(cash_categories.values()))],'cents','cash','finance','收入为正、支出为负；内部转账已排除。')
    chart('material_value','物资成本出入','line',labels,[series('入库成本','material_in'),series('出库成本','material_out')],'cents','movements','materials','不将升、件等不同计量单位直接相加。')
    chart('member_flow','会员储值变动','bar',['充值到账','余额消费','余额退款'],[dict(name='金额',values=[member_topup,member_use,member_refund])],'cents','member_entries','members','充值是储值资金增加，不重复计算为营业收入。')
    chart('workload','当前各岗位待办量','bar',list(task_by_role),[dict(name='待办任务',values=list(task_by_role.values()))],'count','tasks','efficiency','任务数量用于调配工作，不作为个人绩效排名。')
    from .callback_analytics import build_callbacks
    callbacks=build_callbacks(db,user,start,end,stores,aggregate,LIMIT)
    tables.update(callbacks['tables']);charts.extend(callbacks['charts'])
    daily_rows=table('daily','每日经营汇总',['日期','新增订单（单）','交付（台）','交付金额（元）','维修结算（元）','实际收入（元）','实际支出（元）'])
    for d,x in daily.items():add(daily_rows,[d.isoformat(),x['orders'],x['delivery_count'],yuan(x['delivery']),yuan(x['repair']),yuan(x['in']),yuan(x['out'])])
    breakdown=table('stores','门店经营对照',['门店','新增订单（单）','交付（台）','交付金额（元）','维修结算（元）','实际收入（元）','实际支出（元）'])
    for sid,g in sorted(group.items()):add(breakdown,[stores.get(sid,''),g['orders'],g['delivery_count'],yuan(g['delivery']),yuan(g['repair']),yuan(g['cash_in']),yuan(g['cash_out'])])
    from .retail_group_reporting import report_data as retail_group_report
    retail_group_data=retail_group_report(db,user,list(byid))
    from .group_models import GroupSettlementEntry
    clearing=defaultdict(lambda: {'center':0,'store':0})
    for entry in bounded(db, GroupSettlementEntry):
        clearing[entry.store_id][entry.side] += entry.amount_cents
    for entry in retail_group_data['settlements']:
        if entry['kind']=='principal':clearing[entry['store_id']][entry['side']]+=entry['amount_cents']
    clearing_rows=table('group_clearing','当前集团会员往来',['门店','集团应收（元）','门店应收（元）','配对差额（元）'])
    for sid, amounts in sorted(clearing.items()):
        add(clearing_rows,[stores.get(sid,''),yuan(amounts['center']),yuan(amounts['store']),yuan(sum(amounts.values()))])
    chart('group_clearing','当前集团会员往来','bar',[stores.get(sid,'') for sid in sorted(clearing)],
          [dict(name='集团应收',values=[clearing[sid]['center'] for sid in sorted(clearing)]),
           dict(name='门店应收',values=[clearing[sid]['store'] for sid in sorted(clearing)])],
          'cents','group_clearing','members','正数应收、负数应付；内部权益往来，不计第二笔现金或营业收入。当前值不随日期筛选重建。')
    benefit_labels={'bonus':'赠送金额','points':'积分','coupon':'消费券','package':'作业套餐'}
    benefit_purpose={'purchase':'购买发行','grant':'赠送发行','capture':'核销','reverse':'撤销核销','refund':'原款退款','adjust':'积分调整','exchange_in':'兑换获得','exchange_out':'兑换扣减'}
    def benefit_day(e):return datetime.fromisoformat(e['occurred_at']).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()
    benefit_period=[e for e in benefit_data['entries'] if in_period(benefit_day(e))]
    for kind,label in benefit_labels.items():
        units={'bonus':'分','points':'积分','coupon':'张','package':'次'}[kind]
        rows=table('benefit_'+kind,label+'变动明细',['发生日期','门店','来源单号','规则及版本','动作','变动数量（'+units+'）'])
        totals=Counter()
        for e in benefit_period:
            if e['kind']!=kind:continue
            action=benefit_purpose.get(e['purpose'],e['purpose']);totals[action]+=e['units']
            add(rows,[benefit_day(e).isoformat(),stores.get(e['store_id'],''),byid[e['case_id']].number if e['case_id'] in byid else '',e['rule_name']+' / '+str(e['rule_version']),action,e['units']],{'type':'case','id':e['case_id']},units=e['units'])
        chart('benefit_'+kind,label+'单位变动','bar',list(totals),[dict(name='变动数量（'+units+'）',values=list(totals.values()))],'count','benefit_'+kind,'members','独立单位账；增加为正、扣减为负，占额不改变账面余额。各权益单位不互相相加。')
    bredemption=table('benefit_redemptions','权益核销与优惠承担',['发生日期','门店','来源单号','规则','抵扣金额（元）','外部履约对价（元）','集团承担优惠（元）','履约门店承担优惠（元）'])
    bvalue=defaultdict(lambda:dict(recognized=0,group_discount=0,service_discount=0))
    for e in benefit_period+[dict(e,rule_name=e.get('rule_name','混合维修套餐原组件')) for e in package_data['entries'] if in_period(benefit_day(e))]:
        if e['purpose'] not in {'capture','reverse'}:continue
        for name in ('recognized','group_discount','service_discount'):bvalue[e['store_id']][name]+=e[name+'_cents']
        add(bredemption,[benefit_day(e).isoformat(),stores.get(e['store_id'],''),byid[e['case_id']].number if e['case_id'] in byid else '',e['rule_name'],yuan(e['credit_cents']),yuan(e['recognized_cents']),yuan(e['group_discount_cents']),yuan(e['service_discount_cents'])],{'type':'case','id':e['case_id']})
    for e in retail_group_data['adjustments']:
        if e['kind']=='principal' or not in_period(date.fromisoformat(e['business_date'])):continue
        for name in ('recognized','group_discount','service_discount'):bvalue[e['store_id']][name]+=e[name+'_cents']
        add(bredemption,[e['business_date'],stores.get(e['store_id'],''),byid[e['case_id']].number,
            e['label'],yuan(e['credit_cents']),yuan(e['recognized_cents']),yuan(e['group_discount_cents']),
            yuan(e['service_discount_cents'])],{'type':'case','id':e['case_id']},source=e['source'],source_id=e['source_id'])
    chart('benefit_redemptions','权益履约对价与优惠承担','bar',[stores.get(sid,'') for sid in sorted(bvalue)],
        [dict(name=label,values=[bvalue[sid][key] for sid in sorted(bvalue)]) for key,label in [('recognized','外部履约对价'),('group_discount','集团承担优惠'),('service_discount','履约门店承担优惠')]],
        'cents','benefit_redemptions','members','按原核销和实退来源日；精品实退先冲减履约，原券包恢复与对冲合计为零。对价已包含在原维修或精品履约中，不得重复相加。')
    benefit_clearing=defaultdict(lambda:dict(center=0,store=0))
    for e in benefit_data['settlements']:benefit_clearing[e['store_id']][e['side']]+=e['amount_cents']
    for e in package_data['settlements']:benefit_clearing[e['store_id']][e['side']]+=e['amount_cents']
    for e in retail_group_data['settlements']:
        if e['kind']!='principal':benefit_clearing[e['store_id']][e['side']]+=e['amount_cents']
    pending_group=table('retail_group_pending','精品原退待恢复负债',['原单','门店','原单位','种类','待恢复额度（元）','原发行对价（元）','内部结算（元）','可消费（元）','处理条件'])
    for e in retail_group_data['pending']:
        add(pending_group,[byid[e['case_id']].number,stores.get(e['store_id'],''),e['unit_id'],
            {'principal':'本金','bonus':'赠金','coupon':'券','package':'套餐'}[e['kind']],
            yuan(e['credit_cents']),yuan(e['consideration_cents']),yuan(e['settlement_cents']),'0.00',
            '可由财务按原批次恢复' if e['restorable'] else '继续累计原单位；无需重复核销'],
            {'type':'case','id':e['case_id']},amount_cents=e['credit_cents'],unit_id=e['unit_id'])
    bclearing=table('benefit_clearing','当前集团券包及优惠往来',['门店','集团应收（元）','门店应收（元）','配对差额（元）'])
    for sid,amounts in sorted(benefit_clearing.items()):add(bclearing,[stores.get(sid,''),yuan(amounts['center']),yuan(amounts['store']),yuan(sum(amounts.values()))])
    chart('benefit_clearing','当前集团权益往来','bar',[stores.get(sid,'') for sid in sorted(benefit_clearing)],
        [dict(name=label,values=[benefit_clearing[sid][key] for sid in sorted(benefit_clearing)]) for key,label in [('center','集团应收'),('store','门店应收')]],
        'cents','benefit_clearing','members','按冻结内部结算价配对；本金单列。这些记录不产生第二笔现金或集团对外收入。')
    from .transfer_analytics import current_transfers
    transit,interstore=current_transfers(db,user,bounded)
    for offset in clearing_data['settlements']:
        target=interstore if offset['origin_kind'].startswith('material') else vehicle_clearing
        target[offset['store_id']]=target.get(offset['store_id'],0)+offset['amount_cents']
    transit_rows=table('transfer_transit','当前调出在途物资',['调拨号','调出门店','调入门店','物资','数量','单位','在途价值（元）'])
    transit_values=defaultdict(int)
    for entry in transit:
        transit_values[entry['store_id']]+=entry['value_cents']
        add(transit_rows,[entry['number'],stores.get(entry['store_id'],''),stores.get(entry['to_store_id'],''),entry['name'],format(Decimal(entry['quantity_milli'])/1000,'f'),entry['unit'],yuan(entry['value_cents'])],{'type':'case','id':entry['case_id']},amount_cents=entry['value_cents'])
    chart('transfer_transit','当前调出在途价值','bar',[stores.get(sid,'') for sid in sorted(transit_values)],
        [dict(name='在途价值',values=[transit_values[sid] for sid in sorted(transit_values)])],'cents','transfer_transit','materials','原发出减实际验收、原退入库及批准后损失核销；集团按调出方只统计一次。')
    transfer_clearing=table('transfer_clearing','当前店间物资往来',['门店','净应收（元）'])
    for sid,amount in sorted(interstore.items()):add(transfer_clearing,[stores.get(sid,''),yuan(amount)],amount_cents=amount)
    chart('transfer_clearing','当前店间物资往来','bar',[stores.get(sid,'') for sid in sorted(interstore)],
        [dict(name='净应收',values=[interstore[sid] for sid in sorted(interstore)])],'cents','transfer_clearing','finance','验收及运输损失承担原往来加双方实际确认后的核销额；已付款未收款保持未核销。正数应收，负数应付，内部毛利和对外收入均不增加。')
    vtransit=table('vehicle_transit','当前整车调出在途',['调拨号','调出门店','调入门店','VIN','车型','状态','在途价值（元）'])
    vtotals=Counter()
    from .vehicle_transfer_service import LABELS as vehicle_transfer_labels
    for v in vehicle_transit:
        vtotals[v['from_store_id']]+=v['value_cents']
        add(vtransit,[v['number'],stores.get(v['from_store_id'],''),stores.get(v['to_store_id'],''),v['vin'],v['model'],vehicle_transfer_labels[v['status']],yuan(v['value_cents'])],{'type':'case','id':v['case_id']},amount_cents=v['value_cents'])
    chart('vehicle_transit','当前整车在途价值','bar',[stores.get(sid,'') for sid in sorted(vtotals)],
        [dict(name='在途价值',values=[vtotals[sid] for sid in sorted(vtotals)])],'cents','vehicle_transit','inventory','包含拒收待退和退回在途；实际验收、原退入库或批准后的原在途损失核销才离开在途，按调出门店只统计一次。')
    vclearing=table('vehicle_clearing','当前店间整车往来',['门店','净应收（元）'])
    for sid,amount in sorted(vehicle_clearing.items()):add(vclearing,[stores.get(sid,''),yuan(amount)],amount_cents=amount)
    chart('vehicle_clearing','当前店间整车往来','bar',[stores.get(sid,'') for sid in sorted(vehicle_clearing)],
        [dict(name='净应收',values=[vehicle_clearing[sid] for sid in sorted(vehicle_clearing)])],'cents','vehicle_clearing','finance','原库存价值往来加双方确认后核销；未到账保持未核销，不产生内部销售收入。')
    internal_transit=table('internal_cash_transit','当前店间已付待收',['清算号','付款门店','收款门店','约定日期','已付待收（元）'])
    itotals=Counter()
    for entry in clearing_data['in_transit']:
        add(internal_transit,[entry['id'],stores.get(entry['payer_store_id'],''),stores.get(entry['receiver_store_id'],''),entry['due_date'],yuan(entry['amount_cents'])],{'type':'case','id':entry['case_id']},amount_cents=entry['amount_cents'])
        itotals[entry['payer_store_id']]+=entry['amount_cents']
    chart('internal_cash_transit','店间已支付待对方到账','bar',[stores.get(sid,'') for sid in sorted(itotals)],
        [dict(name='已付待收',values=[itotals[sid] for sid in sorted(itotals)])],'cents','internal_cash_transit','finance','两店均在汇总范围时只计一次；没有实际到账确认就不会因集团汇总抵销为零。')
    from .commercial_analytics import build_commercial
    commercial=build_commercial(db,user,start,end,cases,stores,bounded,yuan)
    tables.update(commercial['tables']);charts.extend(commercial['charts'])
    from .retail_bundle_analytics import build_retail_bundle_analytics
    retail_bundles=build_retail_bundle_analytics(db,user,tables,yuan)
    tables.update(retail_bundles['tables']);charts.extend(retail_bundles['charts'])
    from .invoice_analytics import build_invoice_analytics
    invoices=build_invoice_analytics(db,user,start,end,stores,yuan)
    tables.update(invoices['tables']);charts.extend(invoices['charts'])
    from .operations_analytics import build_operations
    operations=build_operations(db,user,start,end,cases,stores,cash,bounded,yuan)
    tables.update(operations['tables']);charts.extend(operations['charts'])
    from .service_analytics import build_service_analytics
    service_analysis=build_service_analytics(db,user,start,end,cases,stores,bounded,yuan)
    tables.update(service_analysis['tables']);charts.extend(service_analysis['charts'])
    from .claims_analytics import build_claims_analytics
    claims_analysis=build_claims_analytics(db,user,cases,stores,bounded,yuan,in_period)
    tables.update(claims_analysis['tables']);charts.extend(claims_analysis['charts'])
    from .procurement_cost_analytics import build as build_procurement_costs
    procurement_cost_analysis=build_procurement_costs(db,user,cases,stores,bounded,yuan,in_period)
    tables.update(procurement_cost_analysis['tables']);charts.extend(procurement_cost_analysis['charts'])
    from .sales_quote_reporting import build_sales_quotes
    sales_quotes_analysis=build_sales_quotes(db,user,stores,yuan,in_period)
    tables.update(sales_quotes_analysis['tables']);charts.extend(sales_quotes_analysis['charts'])
    from .service_orders_analytics import build_service_orders
    service_orders_analysis=build_service_orders(db,user,cases,stores,bounded,yuan,in_period)
    tables.update(service_orders_analysis['tables']);charts.extend(service_orders_analysis['charts'])
    from .repair_material_analytics import build_repair_materials
    repair_materials=build_repair_materials(db,user,start,end)
    tables.update(repair_materials['tables']);charts.extend(repair_materials['charts'])
    from .sales_service_analytics import build as build_sales_services
    sales_services=build_sales_services(db,user,cases,stores,bounded,yuan,in_period)
    tables.update(sales_services['tables']);charts.extend(sales_services['charts'])
    from .aftercare_analytics import build_aftercare_analytics
    aftercare_analysis=build_aftercare_analytics(db,user,cases,stores,tables,bounded,yuan,in_period)
    tables.update(aftercare_analysis['tables']);charts.extend(aftercare_analysis['charts'])
    from .customer_analytics import build_customer_analytics
    customers_analysis=build_customer_analytics(db,user,cases,stores,tables,bounded,yuan)
    tables.update(customers_analysis['tables']);charts.extend(customers_analysis['charts'])
    from .vehicle_operations_analytics import build_vehicle_operations_analytics
    vehicle_operations_analysis=build_vehicle_operations_analytics(db,user,cases,stores,bounded,yuan,in_period)
    tables.update(vehicle_operations_analysis['tables']);charts.extend(vehicle_operations_analysis['charts'])
    from .business_finance_analytics import build_business_finance_analytics
    finance_analysis=build_business_finance_analytics(db,user,start,end,cases,stores,bounded,yuan)
    tables.update(finance_analysis['tables']);charts.extend(finance_analysis['charts'])
    from .supplier_overpayment_analytics import build_supplier_overpayments
    supplier_overpayments=build_supplier_overpayments(db,user,cases,stores,bounded,yuan)
    tables.update(supplier_overpayments['tables']);charts.extend(supplier_overpayments['charts'])
    from .vehicle_income_analytics import build_vehicle_income
    vehicle_income=build_vehicle_income(db,user,cases,stores,bounded,yuan,in_period) if include_vehicle_income else {'tables':{},'charts':[],'metrics':{}}
    tables.update(vehicle_income['tables']);charts.extend(vehicle_income['charts'])
    from .member_pricing_analytics import build_member_pricing
    member_pricing=build_member_pricing(db,user,cases,stores,bounded,yuan,in_period)
    tables.update(member_pricing['tables']);charts.extend(member_pricing['charts'])
    from .repair_package_analytics import build_packages
    package_analysis=build_packages(db,user,package_data,cases,stores,yuan,in_period)
    tables.update(package_analysis['tables']);charts.extend(package_analysis['charts'])
    from .foundation_analytics import build_foundation_analytics
    foundation=build_foundation_analytics(db,user,start,end,cases,stores,cash,bounded,yuan)
    tables.update(foundation['tables']);charts.extend(foundation['charts'])
    from .vehicle_period_analytics import build_vehicle_period
    from .procurement_analytics import build_procurement_cohort
    vehicle_period=build_vehicle_period(db,user,start,end)
    procurement_cohort=build_procurement_cohort(db,user,start,end)
    from .warehouse_period_analytics import build_warehouse_period
    warehouse_period=build_warehouse_period(db,user,start,end)
    from .visit_activity_analytics import build_visit_activity
    from .material_value_analytics import build_material_values
    from .transfer_loss_reports import build_transfer_losses
    transport_losses=build_transfer_losses(db,user,start,end,transport_source_data)
    from .vehicle_transport_analytics import build_vehicle_transport
    vehicle_transport=build_vehicle_transport(db,user,start,end,vehicle_transport_data)
    visit_activity=build_visit_activity(db,user,start,end)
    material_values=build_material_values(db,user,start,end)
    for report in (vehicle_period,procurement_cohort,warehouse_period,visit_activity,material_values,transport_losses,vehicle_transport):
        tables.update(report['tables']);charts.extend(report['charts'])
    risk=[dict(title='超过计划日期的任务',value=overdue,table='tasks'),dict(title='需要补货的物资',value=low_stock,table='materials'),dict(title='超过90天的库存车',value=aging['90天以上'],table='inventory')]
    return {'date_from':start.isoformat(),'date_to':end.isoformat(),'stock_as_of':today().isoformat(),'generated_at':utcnow().isoformat()+'Z',
        'scope':{'view':'flow_analytics','date_from_explicit':start_explicit,'date_to_explicit':end_explicit,
            'period':{'date_from':start.isoformat(),'date_to':end.isoformat(),'inclusive':True,
                'omitted_date_from_rule':'date_to_minus_29_days','omitted_date_to_rule':'server_business_date','natural_month_default':False},
            'cash':{'table':'cash','basis':'actual_cash_in_selected_period','income_metric':'cash_in_cents','expense_metric':'cash_out_cents'},
            'current_snapshot':{'as_of_field':'stock_as_of','tables':['inventory','materials','members','tasks'],'basis':'current_effective_records','not_period_end_snapshot':True},
            'notice':'未指定date_from时默认date_to及之前29天，未指定date_to时默认服务器业务日期；默认近30天不是自然月。cash为所选期间的实际收支，当前库存、储值余额和未完成任务按stock_as_of最新有效记录统计；待收按当前有效原单计算，不是期间收款。'},
        'scope_name':stores.get(db.info.get('write_store'),'已授权门店汇总'),
        'metrics':dict(new_orders=new_orders,delivery_count=delivery_count,delivery_cents=delivery_total,delivery_margin_cents=None if delivery_missing else delivery_total-delivery_cost,
            delivery_missing_cost=delivery_missing,new_repairs=new_repairs,repair_cents=repair_total,cash_in_cents=income,cash_out_cents=expense,cash_net_cents=income-expense,
            receivable_cents=current_due,overdue_receivable_cents=overdue_due,inventory_count=sum(stock_state.values()),inventory_cost_cents=inventory_cost,
            material_cost_cents=material_value,material_in_transit_cents=sum(transit_values.values()),interstore_material_net_cents=sum(interstore.values()),vehicle_in_transit_cents=sum(vtotals.values()),vehicle_in_transit_count=len(vehicle_transit),interstore_vehicle_net_cents=sum(vehicle_clearing.values()),member_balance_cents=balance,member_count=len(members),task_count=len(tasks),overdue_tasks=overdue,
            cohort_receptions=len(leads),cohort_orders=len(converted),cohort_rate=None if not leads else round(len(converted)/len(leads)*100,2),
            **supplier_overpayments['metrics'],
            **vehicle_income['metrics'],
            **member_pricing['metrics'],
            **package_analysis['metrics'],
            internal_cash_in_cents=internal_income,internal_cash_out_cents=internal_expense,internal_cash_in_transit_cents=sum(itotals.values()),**commercial['metrics'],**invoices['metrics'],**operations['metrics'],**service_analysis['metrics'],**aftercare_analysis['metrics'],**customers_analysis['metrics'],**vehicle_operations_analysis['metrics'],**finance_analysis['metrics'],**foundation['metrics'],**claims_analysis['metrics'],**retail_bundles['metrics'],**vehicle_period['metrics'],**procurement_cohort['metrics'],**warehouse_period['metrics'],**sales_quotes_analysis['metrics'],**procurement_cost_analysis['metrics'],**service_orders_analysis['metrics'],**sales_services['metrics'],**repair_materials['metrics'],**visit_activity['metrics'],**material_values['metrics'],**transport_losses['metrics'],**vehicle_transport['metrics'],**callbacks['metrics']),
        'charts':charts,'tables':tables,'risks':risk,'definitions':[
            '期间指标按所选起止日期统计；当前库存、储值余额和未完成任务按今天的最新有效记录统计。',
            '物资在途只归调出门店统计，验收入库或退回入库时减少；库存价值与在途价值需一起核对。店间物资往来按验收价值配对，集团内部互抵，不计对外营业收入。',
            '会员储值余额与变动图为原有门店储值账；集团本金通过集团会员模块查询。集团权益核销计入原业务已结金额，集团内部往来单列，不重复计算现金。',
            '交付金额按车辆实际交付日统计，不是订单签订金额，也不是现金到账金额。',
            '直接毛差＝交付金额－该批交付车辆的采购成本快照；不含税费、返利、人工及其他费用，不是净利润。成本缺失时不显示毛差。',
            '单店实际收支包含本店真实内部清算，内部收支另表可查；集团对外口径排除内部清算现金，已付待收仍单列在途。预收和会员充值不是营业收入。',
            '客户转化使用所选期间的接待记录为同一批次；截至今天查看它们是否曾转意向和订单，重复来访按接待记录计数。',
            '尚待收取包括未到收款时点的订单金额，不等同于逾期欠款。历史报表按当前有效记录重算，并非不可变会计时点账。',legacy_note]+vehicle_period['definitions']+procurement_cohort['definitions']+warehouse_period['definitions']+visit_activity['definitions']+[material_values['definition']]+transport_losses['definitions']+vehicle_transport['definitions']+callbacks['definitions']}
