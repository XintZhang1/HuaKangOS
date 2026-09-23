"""One population per chart/table/export; targets never become duplicate cash."""
from collections import defaultdict
from datetime import date
from fastapi import HTTPException
from .models import CashEntry
from .cash_basis import effective_cash
from .vehicle_income_models import VehicleIncomeOrder,VehicleIncomeCash
from .vehicle_income_service import is_detailed,totals,actual_income_rows


def build_vehicle_income(db,user,cases,stores,bounded,yuan,in_period):
    if user.role not in {'admin','manager','finance','auditor'}:return {'tables':{},'charts':[],'metrics':{}}
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([s for s in db.info.get('store_scope',()) if s])>1)
    byid={r.id:r for r in cases if is_detailed(r)};orders={r.id:r for r in bounded(db,VehicleIncomeOrder)}
    tables={};charts=[];groups=defaultdict(int);cash_groups=defaultdict(int);store_balances=defaultdict(lambda:defaultdict(int))
    def table(key,title,headers):tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    recognized=table('vehicle_other_income_facts','期间厂家及供应商整车其他收入确认',
        ['门店','本次确认差额（元）'] if aggregate else ['原单','门店','往来单位','批准日期','前目标（元）','新目标（元）','本次确认差额（元）'])
    balances=table('vehicle_other_income_balances','当前厂家及供应商整车其他收入往来',
        ['门店','有效应收（元）','实际净收（元）','尚欠（元）','超收待退（元）'] if aggregate else ['原单','门店','往来单位','有效应收（元）','实际净收（元）','尚欠（元）','超收待退（元）'])
    cashrows=table('vehicle_other_income_cash','期间厂家及供应商整车其他收入实际资金',
        ['门店','实际净收（元）'] if aggregate else ['原单','门店','往来单位','实际日期','动作','金额（元）','原到账编号'])
    total_due=0;total_refund=0
    for row in byid.values():
        order=orders.get(row.id)
        if not order:raise HTTPException(409,'厂家收入缺少原往来依据，未返回不完整统计')
        store=stores.get(row.store_id,'');name=order.supplier_snapshot['name'];route={'type':'case','id':row.id};t=totals(db,row)
        if row.state!='cancelled':
            total_due+=t['receivable_cents'];total_refund+=t['refund_due_cents']
            if aggregate:
                for key in ('target_cents','net_received_cents','receivable_cents','refund_due_cents'):store_balances[store][key]+=t[key]
            else:balances.append({'values':[row.number,store,name,yuan(t['target_cents']),yuan(t['net_received_cents']),yuan(t['receivable_cents']),yuan(t['refund_due_cents'])],'route':route,'amount_cents':t['receivable_cents'],'refund_due_cents':t['refund_due_cents']})
        for fact in actual_income_rows(db,row):
            if not in_period(date.fromisoformat(fact['business_date'])):continue
            amount=fact['amount_cents'];groups[store if aggregate else name]+=amount
            if not aggregate:recognized.append({'values':[row.number,store,name,fact['business_date'],yuan(fact['previous_cents']),yuan(fact['target_cents']),yuan(amount)],'route':route,**fact})
    # Domain links identify the original source. Actual amount, direction and date come from CashEntry once.
    actual={c.id:c for c in effective_cash(db,bounded(db,CashEntry)) if c.approval_state=='approved'}
    for entry in bounded(db,VehicleIncomeCash):
        row=byid.get(entry.case_id);order=orders.get(entry.case_id);cash=actual.get(entry.cash_id)
        if not row or not order or not cash:raise HTTPException(409,'厂家原款与唯一实际现金不一致，未返回不完整统计')
        if not in_period(cash.business_date):continue
        amount=cash.amount_cents*(1 if cash.direction=='in' else -1);name=order.supplier_snapshot['name'];store=stores.get(row.store_id,'');cash_groups[store if aggregate else name]+=amount
        if not aggregate:cashrows.append({'values':[row.number,store,name,cash.business_date.isoformat(),'实际到账' if cash.direction=='in' else '原款实际退回',yuan(amount),entry.original_id or '—'],'route':{'type':'case','id':row.id},'amount_cents':amount,'cash_id':cash.id,'fact_id':entry.id})
    if aggregate:
        recognized.extend({'values':[store,yuan(amount)],'amount_cents':amount} for store,amount in sorted(groups.items()))
        cashrows.extend({'values':[store,yuan(amount)],'amount_cents':amount} for store,amount in sorted(cash_groups.items()))
        balances.extend({'values':[store,yuan(t['target_cents']),yuan(t['net_received_cents']),yuan(t['receivable_cents']),yuan(t['refund_due_cents'])],'amount_cents':t['receivable_cents'],'refund_due_cents':t['refund_due_cents']} for store,t in sorted(store_balances.items()))
    for key,title,population,measure in [('vehicle_other_income_facts','厂家及供应商收入确认差额',groups,'已独立批准的本次目标差额'),('vehicle_other_income_cash','厂家及供应商收入实际收退',cash_groups,'实际现金净额')]:
        labels=sorted(population);charts.append({'id':key,'title':title,'section':'finance','type':'bar','unit':'cents','labels':labels,'series':[{'name':measure,'values':[population[k] for k in labels]}],'table':key,
            'caption':'目标确认使用独立批准日期，真实现金使用到账或退款日期。来源、应收、发票及现金分开列示；原单批量依据不自动摊到各VIN，不改变整车采购成本或售价。'})
    return {'tables':tables,'charts':charts,'metrics':{'vehicle_other_income_recognized_cents':sum(groups.values()),'vehicle_other_income_cash_net_cents':sum(cash_groups.values()),'vehicle_other_income_receivable_cents':total_due,'vehicle_other_income_refund_due_cents':total_refund}}
