"""Claims responsibility, actual pass-through cash and external customer facts."""
from collections import defaultdict
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from .flow_models import Case,PaymentLink
from .claims_models import (
    ClaimOrder,ClaimApplication,ClaimResponsibility,ClaimCash,ClaimCustomerPayment,
)


def build_claims_analytics(db,user,cases,stores,bounded,yuan,in_period):
    sources={r.id:r for r in cases};tables={};charts=[]
    orders={r.id:r for r in bounded(db,ClaimOrder)}
    hosts={r.id:r for r in bounded(db,Case,select(Case).where(Case.kind=='claim'))}
    apps={r.id:r for r in bounded(db,ClaimApplication)}
    payments={r.id:r for r in bounded(db,PaymentLink)}
    aggregate=getattr(user,'_aggregate_scope',False)
    def route(row):
        return None if aggregate else {'type':'case','id':row.id}
    def table(key,title,headers):
        rows=[];tables[key]={'title':title,'headers':headers,'rows':rows};return rows
    def chart(key,title,rows,group_index,caption):
        totals=defaultdict(int)
        for row in rows:totals[row['values'][group_index]]+=row['amount_cents']
        labels=sorted(totals)
        charts.append({'id':key,'title':title,'section':'finance','type':'bar','unit':'cents',
            'labels':labels,'series':[{'name':'金额','values':[totals[k] for k in labels]}],
            'table':key,'caption':caption})
    responsibilities=table('claims_responsibility','期间理赔承担调整',
        ['原维修','门店','实际生效日','承担类型','承担方','变化金额（元）'])
    business=table('claims_business_adjustments','期间已履约维修核赔减免',
        ['原维修','门店','业务确认日','实际调整日','业务净额变化（元）'])
    labels={'insurer':'保险','manufacturer':'厂家','internal':'内部'}
    for entry in bounded(db,ClaimResponsibility):
        source=sources.get(entry.source_case_id);app=apps.get(entry.application_id)
        if not source or not app or app.store_id!=entry.store_id or source.store_id!=entry.store_id:
            raise HTTPException(409,'理赔承担调整缺少同店原维修或实际生效来源')
        if in_period(app.business_date):
            responsibilities.append({'values':[source.number,stores.get(entry.store_id,''),
                app.business_date.isoformat(),labels[entry.payer_type],entry.payer_name,yuan(entry.amount_cents)],
                'route':route(source),'amount_cents':entry.amount_cents,
                'entry_id':entry.id,'source_case_id':source.id,'application_id':app.id})
        if entry.payer_type=='internal' or not source.data.get('released_date'):continue
        # A reduction before handover is recognized with that handover, never as
        # negative revenue in an earlier period that had no repair settlement.
        recognized=max(date.fromisoformat(source.data['released_date']),app.business_date)
        if not in_period(recognized):continue
        business.append({'values':[source.number,stores.get(entry.store_id,''),
            recognized.isoformat(),app.business_date.isoformat(),yuan(entry.amount_cents)],
            'route':route(source),'amount_cents':entry.amount_cents,
            'source_case_id':source.id,'application_id':app.id,'source_kind':'repair'})
    cashrows=table('claims_cash','期间理赔实际代收转付与原款退回',
        ['核赔单','原维修','门店','现金日期','实际用途','方向','金额（元）','凭证号'])
    pending=table('claims_payable','当前理赔代收待转付或原退',
        ['核赔单','原维修','门店','实际代收余额（元）'])
    purposes={'thirdparty_refund':'原维修第三方退款','pass_receive':'第三方实际代收',
        'pass_pay':'实际转付客户','customer_return':'客户实退原转付款','party_return':'实际返还原第三方','unused_refund':'未转付原款退第三方'}
    balances=defaultdict(int)
    for fact in bounded(db,ClaimCash):
        order=orders.get(fact.case_id);host=hosts.get(fact.case_id);payment=payments.get(fact.payment_link_id)
        source=sources.get(order.source_case_id) if order else None
        if not source or not host or not payment or any(r.store_id!=fact.store_id for r in (host,order,source,payment)):
            raise HTTPException(409,'理赔现金与原业务归属或现金关联不一致')
        amount=payment.amount_cents*(1 if payment.direction=='in' else -1)
        if fact.purpose!='thirdparty_refund':balances[fact.case_id]+=amount
        if in_period(payment.business_date):
            cashrows.append({'values':[host.number,source.number,stores.get(fact.store_id,''),
                payment.business_date.isoformat(),purposes[fact.purpose],
                '收入' if payment.direction=='in' else '支出',yuan(amount),payment.reference],
                'route':route(host),'amount_cents':amount,'cash_id':payment.cash_id,
                'payment_link_id':payment.id,'purpose':fact.purpose})
    for key,amount in sorted(balances.items()):
        if amount<0:raise HTTPException(409,'理赔实际转付超过原代收余额，请核对原现金')
        if not amount:continue
        host=hosts[key];source=sources[orders[key].source_case_id]
        pending.append({'values':[host.number,source.number,stores.get(host.store_id,''),yuan(amount)],
            'route':route(host),'amount_cents':amount})
    external=table('claims_external_customer','期间第三方与客户直接报销往来',
        ['核赔单','原维修','门店','实际日期','外部事实','金额（元）'])
    for fact in bounded(db,ClaimCustomerPayment):
        order=orders.get(fact.case_id);host=hosts.get(fact.case_id)
        source=sources.get(order.source_case_id) if order else None
        if not source or not host or any(r.store_id!=fact.store_id for r in (source,order,host)):
            raise HTTPException(409,'客户直接报销缺少同店原维修关系')
        if not in_period(fact.business_date):continue
        amount=fact.amount_cents*(1 if fact.purpose=='reimbursement' else -1)
        external.append({'values':[host.number,source.number,stores.get(fact.store_id,''),
            fact.business_date.isoformat(),'第三方直接付客户' if amount>0 else '客户原路返还第三方',yuan(amount)],
            'route':route(host),'amount_cents':amount,'external_payment_id':fact.id})
    chart('claims_responsibility','期间理赔承担调整',responsibilities,3,
        '同一调整外部减少与内部吸收配对为零；内部承担不计客户收入、实际现金或客户应收。')
    chart('claims_business_adjustments','期间已履约维修核赔减免',business,1,
        '实际责任调整按生效日期确认；先调整后交车时随交车确认。原报价及原结算日期保留，实际退款不再扣一次业务金额。')
    chart('claims_cash','期间理赔实际现金专项',cashrows,4,
        '来自已有现金流水及关联收付款记录，只作专项明细；第三方直接付客户不在此表，不能再次加入总现金或维修收入。')
    chart('claims_payable','当前理赔代收待转付或原退',pending,2,
        '实际收到的代收款减已实际转付，加客户实退减原第三方实退；未到账批准额度不作为现金或应付。')
    chart('claims_external_customer','期间客户直接报销事实',external,4,
        '凭外部文件及财务本人确认记录；不产生公司现金，不重复确认维修收入。上传文件本身不证明交易真实性。')
    return {'tables':tables,'charts':charts,'metrics':{
        'claims_revenue_adjustment_cents':sum(r['amount_cents'] for r in business),
        'claims_pass_through_balance_cents':sum(balances.values()),
        'claims_external_reimbursement_net_cents':sum(r['amount_cents'] for r in external)}}

