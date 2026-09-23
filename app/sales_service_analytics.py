"""Detailed sales services: actual accessory acceptance and approved insurer commission."""
from collections import defaultdict
from .insurance_models import (InsuranceOrder,InsuranceQuote,InsuranceSubmission,InsuranceResult,
    InsuranceCommission,InsuranceCommissionReview,InsuranceCommissionPayment)
from .addon_models import AddonAcceptance,AddonReturnPosting


def build(db,user,cases,stores,bounded,yuan,in_period):
    bycase={c.id:c for c in cases};tables={};charts=[]
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def chart(key,title,rows,index,caption):
        sums=defaultdict(int)
        for row in rows:sums[row['values'][index]]+=row['amount_cents']
        labels=sorted(sums)
        charts.append({'id':key,'title':title,'section':'sales','type':'bar','unit':'cents','labels':labels,
            'series':[{'name':'金额','values':[sums[k] for k in labels]}],'table':key,'caption':caption})
    def case(key):return bycase.get(key)
    def route(c):return {'type':'case','id':c.id}
    addon=table('addon_actual_facts','期间加装客户验收及原单退货',['原单','门店','实际发生日','事实','业务净额（元）','商品成本（元）'])
    for model,kind in ((AddonAcceptance,'acceptance'),(AddonReturnPosting,'return')):
        for fact in bounded(db,model):
            c=case(fact.case_id)
            if not c or not in_period(fact.business_date) or kind=='return' and not fact.acceptance_id:continue
            amount=fact.amount_cents if kind=='acceptance' else -(fact.goods_cents+fact.installation_cents-fact.retained_cents)
            cost=fact.value_cents*(1 if kind=='acceptance' else -1)
            addon.append({'values':[c.number,stores.get(c.store_id,''),fact.business_date.isoformat(),'客户实际验收' if kind=='acceptance' else '原验收明细实际退回',yuan(amount),yuan(cost)],
                'route':route(c),'amount_cents':amount,'value_cents':cost,'source_kind':'addon','fact_kind':kind,'fact_id':fact.id})
    chart('addon_actual_facts','期间加装履约净额',addon,1,'客户实际验收确认商品及安装收入，原退货在实退日追加减项；领料和安装本身不确认收入，收退款另查现金。商品成本不含人工费用。')
    orders={r.id:r for r in bounded(db,InsuranceOrder)};quotes={r.id:r for r in bounded(db,InsuranceQuote)}
    submissions={r.id:r for r in bounded(db,InsuranceSubmission)};commissions={r.id:r for r in bounded(db,InsuranceCommission)}
    policies=table('insurance_policy_facts','期间实际出保信息',['原单','门店','实际出保日','保险公司','保单号','保费（元）','收付方式'])
    for r in bounded(db,InsuranceResult):
        c=case(r.case_id)
        if not c or r.outcome!='issued' or not in_period(r.business_date):continue
        q=quotes[submissions[r.submission_id].quote_id]
        policies.append({'values':[c.number,stores.get(c.store_id,''),r.business_date.isoformat(),q.insurer_snapshot['name'],r.policy_number,yuan(q.premium_cents),'门店代收代缴' if q.collection_mode=='store_collect' else '客户直付保险公司'],
            'route':route(c),'premium_cents':q.premium_cents,'policy_count':1,'fact_id':r.id})
    commission=table('insurance_commission_facts','期间保险公司已确认佣金变动',['原单','门店','独立确认日','保险公司','佣金版本','累计确认（元）','本次变动（元）'])
    for review in bounded(db,InsuranceCommissionReview):
        fact=commissions[review.confirmation_id];c=case(fact.case_id)
        if not c or review.decision!='approved' or not in_period(review.business_date):continue
        q=quotes[c.data['insurance_quote_id']];amount=fact.target_cents-fact.previous_cents
        commission.append({'values':[c.number,stores.get(c.store_id,''),review.business_date.isoformat(),q.insurer_snapshot['name'],fact.revision,yuan(fact.target_cents),yuan(amount)],
            'route':route(c),'amount_cents':amount,'source_kind':'insurance','fact_kind':'commission_review','fact_id':review.id})
    chart('insurance_commission_facts','期间已确认保险佣金净额',commission,3,'仅有保险公司实际结算依据并经独立批准的佣金；按本次目标与此前已确认目标之差计入批准日。预计佣金、代收保费、客户直付款均不计收入。')
    payments=table('insurance_commission_cash','期间保险佣金实际收退',['原单','门店','实际收付日','保险公司','方向','金额（元）'])
    for p in bounded(db,InsuranceCommissionPayment):
        c=case(p.case_id)
        if not c or not in_period(p.business_date):continue
        q=quotes[c.data['insurance_quote_id']];amount=p.amount_cents*(1 if p.direction=='in' else -1)
        payments.append({'values':[c.number,stores.get(c.store_id,''),p.business_date.isoformat(),q.insurer_snapshot['name'],'到账' if p.direction=='in' else '原佣金退回',yuan(amount)],
            'route':route(c),'amount_cents':amount,'cash_id':p.cash_id,'fact_id':p.id})
    chart('insurance_commission_cash','期间佣金实际收退',payments,3,'每笔只引用一个实际现金记录；与全系统收支明细为同一笔现金，不可再次相加。')
    return {'tables':tables,'charts':charts,'metrics':{'addon_actual_net_cents':sum(r['amount_cents'] for r in addon),
        'addon_actual_goods_cost_cents':sum(r['value_cents'] for r in addon),'insurance_issued_count':len(policies),
        'insurance_issued_premium_cents':sum(r['premium_cents'] for r in policies),'insurance_confirmed_commission_delta_cents':sum(r['amount_cents'] for r in commission),
        'insurance_commission_actual_net_cents':sum(r['amount_cents'] for r in payments)}}
