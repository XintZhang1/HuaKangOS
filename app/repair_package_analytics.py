"""Original purchase cash and separate current component liabilities."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from .db import today


def build_packages(db,user,data,cases,stores,yuan,in_period):
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([s for s in db.info.get('store_scope',()) if s])>1)
    byid={r.id:r for r in cases};tables={};charts=[]
    quantity=lambda n:format(Decimal(n)/1000,'f')
    period=[];totals=defaultdict(lambda:{'purchase':0,'refund':0})
    for key,action,sign in [('purchases','购买预收',1),('refunds','未用原款退款',-1)]:
        for row in data[key]:
            if not in_period(date.fromisoformat(row['business_date'])):continue
            value=row['amount_cents'];store=stores.get(row['store_id'],'')
            totals[store]['purchase' if sign==1 else 'refund']+=value
            if not aggregate:
                period.append({'values':[row['business_date'],store,byid[row['case_id']].number if row['case_id'] in byid else '',action,yuan(value)],
                               'amount_cents':sign*value,'source_id':row['id'],'source':key,'route':{'type':'case','id':row['case_id']}})
    if aggregate:
        period=[{'values':[store,yuan(t['purchase']),yuan(t['refund'])],'purchase_cents':t['purchase'],'refund_cents':t['refund']} for store,t in sorted(totals.items())]
    tables['repair_package_cash']={'title':'维修套餐实际购买与未用退款','headers':['门店','购买预收（元）','未用原款退款（元）'] if aggregate else ['实际日期','门店','原单','动作','实际金额（元）'],'rows':period}
    labels=sorted(totals)
    charts.append({'id':'repair_package_cash','title':'维修套餐实际购买与未用退款','section':'members','type':'bar','unit':'cents','labels':labels,
                   'series':[{'name':label,'values':[totals[s][field] for s in labels]} for field,label in [('purchase','购买预收'),('refund','未用原款退款')]],
                   'table':'repair_package_cash','caption':'按原实际到账或退款日期；现金已包含在全店收支中，购买预收不计维修营业收入。零元组件退还没有虚构现金。'})
    balances=[];liability=defaultdict(lambda:{'free':0,'use':0,'refund':0});quantities=defaultdict(lambda:[0,0,0])
    for row in data['lots']:
        store=stores.get(row['store_id'],'');expired=date.fromisoformat(row['expires_on'])<today()
        refund_qty=row.get('refund_reserved_quantity_milli',0);refund_paid=row.get('refund_reserved_paid_cents',0)
        liability[store]['free']+=row['available_paid_cents'];liability[store]['use']+=row['reserved_paid_cents'];liability[store]['refund']+=refund_paid
        key=(store,'作业' if row['kind']=='work' else '配件',row['unit'],'已到期' if expired else '有效期内')
        values=quantities[key];values[0]+=row['available_quantity_milli'];values[1]+=row['reserved_quantity_milli'];values[2]+=refund_qty
        if not aggregate:
            balances.append({'values':[store,byid[row['case_id']].number if row['case_id'] in byid else '',row['name'],row['unit'],
                                      quantity(row['available_quantity_milli']),quantity(row['reserved_quantity_milli']),quantity(refund_qty),
                                      yuan(row['available_paid_cents']),yuan(row['reserved_paid_cents']),yuan(refund_paid),row['expires_on'],'已到期' if expired else '有效期内'],
                             'lot_id':row['id'],'available_milli':row['available_quantity_milli'],'reserved_milli':row['reserved_quantity_milli'],'refund_reserved_milli':refund_qty,
                             'route':{'type':'case','id':row['case_id']}})
    if aggregate:
        balances=[{'values':[store,kind,unit,state,quantity(q[0]),quantity(q[1]),quantity(q[2])],'available_milli':q[0],'reserved_milli':q[1],'refund_reserved_milli':q[2]}
                  for (store,kind,unit,state),q in sorted(quantities.items())]
    tables['repair_package_components']={'title':'当前维修套餐原组件余量','headers':['发行门店','类型','单位','有效状态','未用未占量','维修占量','已批退款占量'] if aggregate else
        ['发行门店','原购买单','原组件','单位','未用未占量','维修占量','已批退款占量','未用未占原价（元）','维修占用原价（元）','待退原价（元）','原到期日','有效状态'],'rows':balances}
    tables['repair_package_liability']={'title':'当前维修套餐未履约原款','headers':['发行门店','未用未占原价（元）','维修占用原价（元）','已批待退原价（元）'],
        'rows':[{'values':[s,yuan(v['free']),yuan(v['use']),yuan(v['refund'])],'unconsumed_cents':sum(v.values())} for s,v in sorted(liability.items())]}
    labels=sorted(liability)
    charts.append({'id':'repair_package_liability','title':'当前维修套餐未履约原款','section':'members','type':'bar','unit':'cents','labels':labels,
        'series':[{'name':label,'values':[liability[s][key] for s in labels]} for key,label in [('free','未用未占原价'),('use','维修占用原价'),('refund','已批待退原价')]],
        'table':'repair_package_liability','caption':'只按发行店统计原批次尚未履约的购买对价；跨店履约不重复增加购买现金。到期未用另列状态，未自动确认为收入；不同作业和物资单位不相加。当前余额不随日期范围重建。'})
    return {'tables':tables,'charts':charts,'metrics':{
        'repair_package_purchase_cash_cents':sum(v['purchase'] for v in totals.values()),
        'repair_package_refund_cash_cents':sum(v['refund'] for v in totals.values()),
        'repair_package_unconsumed_paid_cents':sum(sum(v.values()) for v in liability.values())}}
