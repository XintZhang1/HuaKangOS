"""Actual customer service fees and pass-through cash with separate bases."""
from collections import defaultdict
from datetime import date
from sqlalchemy import select
from .flow_models import Case
from .models import CashEntry
from .service_orders_models import ServicePassEntry,ServiceLine
from .service_orders_service import is_detailed,source_summary,actual_income_rows

def build_service_orders(db,user,cases,stores,bounded,yuan,in_period):
    tables={};charts=[];metrics={};income=defaultdict(int);balances=defaultdict(int)
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    fees=table('service_fee_facts','期间代办及其它服务实际收费事实',['原单','门店','发生日期','服务类型','项目','事实','金额（元）'])
    current=table('service_customer_balances','当前服务费与代收代缴余额',['原单','门店','款项','已授权净收费（元）','客户净结算（元）','尚待结算（元）','代缴款尚在本店（元）'])
    cashrows=table('service_pass_cash','期间原客户资金实际代缴与退回',['原单','门店','发生日期','动作','原资金分配','本次现金（元）'])
    byid={c.id:c for c in cases if is_detailed(c)}
    lines={l.id:l for l in bounded(db,ServiceLine)}
    for row in byid.values():
        route={'type':'case','id':row.id};label='代办服务' if row.kind=='agency' else '其它客户服务'
        s=source_summary(db,row)
        if s['authorized']:
            for bucket,caption in [('fee','本店服务费'),('pass','客户代缴本金')]:
                charge=s[bucket+'_charge_cents'];paid=s[bucket+'_paid_cents'];due=max(0,charge-paid)
                balances[bucket]+=due
                current.append({'values':[row.number,stores.get(row.store_id,''),caption,yuan(charge),yuan(paid),yuan(due),yuan(s['pass_cash_balance_cents']) if bucket=='pass' else '—'],'route':route,'amount_cents':due,'bucket':bucket})
        for fact in actual_income_rows(db,row):
            if not in_period(date.fromisoformat(fact['business_date'])):continue
            amount=fact['amount_cents'];income[label]+=amount
            fees.append({'values':[row.number,stores.get(row.store_id,''),fact['business_date'],label,lines[fact['line_id']].name,
                {'fulfillment':'原项目实际履约','fee_reduction':'原项目已生效减免','retained_fee':'客户确认保留的实际办理费'}[fact['kind']],yuan(amount)],'route':route,'amount_cents':amount,
                'source_kind':row.kind,'fact_kind':fact['kind'],'fact_id':fact['fact_id'],'original_fact_id':fact['original_fact_id']})
    actual={r.id:r for r in bounded(db,CashEntry)}
    for entry in bounded(db,ServicePassEntry):
        row=byid.get(entry.case_id);cash=actual.get(entry.cash_id)
        if not row or not cash or not in_period(cash.business_date):continue
        cashrows.append({'values':[row.number,stores.get(row.store_id,''),cash.business_date.isoformat(),
            '第三方原路退回' if entry.purpose=='thirdparty_return' else '本次实际代缴',entry.tender_id,yuan(cash.amount_cents)],
            'route':{'type':'case','id':row.id},'amount_cents':cash.amount_cents*(1 if cash.direction=='in' else -1),'cash_id':cash.id})
    labels=sorted(income)
    charts.append({'id':'service_fee_facts','title':'期间代办及其它服务履约净额','section':'sales','type':'bar','unit':'cents','labels':labels,
        'series':[{'name':'服务费','values':[income[k] for k in labels]}],'table':'service_fee_facts',
        'caption':'原项目实际履约与后来已生效减免分别使用事实日期。客户代缴本金、预收及实际收退款不计为服务费收入。'})
    metrics.update(service_fee_net_cents=sum(income.values()),service_fee_receivable_cents=balances['fee'],service_pass_receivable_cents=balances['pass'])
    return {'tables':tables,'charts':charts,'metrics':metrics}
