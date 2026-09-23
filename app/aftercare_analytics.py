"""Original fulfillment stays dated; approved credits appear on their own application date."""
from collections import defaultdict
from decimal import Decimal
from sqlalchemy import select
from fastapi import HTTPException
from .aftercare_models import AftercareApplication,AftercareAdjustment
from .flow_models import FlowEvent


def build_aftercare_analytics(db,user,cases,stores,source_tables,bounded,yuan,in_period):
    byid={r.id:r for r in cases};tables={};charts=[]
    apps={r.id:r for r in bounded(db,AftercareApplication)}
    completed={r.case_id for r in bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.action=='service_finish'))}
    adjustments=[];net=[];totals=defaultdict(int)
    names={'order':'整车交付','repair':'维修对外结算','addon':'加装办理核价','agency':'代办办理核价','insurance':'代收保费'}
    datasets=[('deliveries','order',3,4),('repair_settlements','repair',3,4),('retail_settlements','retail',3,5),('addon_completed','addon',2,3),('agency_completed','agency',2,3)]
    for key,kind,day_index,amount_index in datasets:
        for row in source_tables[key]['rows']:
            values=row['values'];amount=int(Decimal(str(values[amount_index]))*100);totals[kind]+=amount
            net.append({'values':[values[0],values[1],values[day_index],names.get(kind,'精品履约或原单退货'),'原履约事实',yuan(amount)],
                'route':row.get('route'),'amount_cents':amount,'source_kind':kind})
    for row in bounded(db,AftercareAdjustment):
        app=apps.get(row.application_id);source=byid.get(row.source_case_id)
        if not app or not source or app.store_id!=row.store_id or source.store_id!=row.store_id:raise HTTPException(409,'售后调整与原业务归属不一致')
        if not in_period(app.business_date):continue
        recognized=(source.kind=='order' and source.state=='delivered' and bool(source.completed_date)) or (source.kind=='repair' and bool(source.data.get('released_date'))) or (source.kind in {'addon','agency'} and source.id in completed)
        amount=-row.revenue_credit_cents if recognized else 0
        adjustments.append({'values':[source.number,stores.get(row.store_id,''),app.business_date.isoformat(),names.get(source.kind,source.kind),
            yuan(row.credit_cents),yuan(amount),'计入调整发生期' if recognized else '原单尚无本表履约金额或属于代收保费'],
            'route':{'type':'case','id':source.id},'amount_cents':amount,'credit_cents':row.credit_cents,'source_kind':source.kind,'aftercare_case_id':app.case_id})
        if recognized:
            totals[source.kind]+=amount
            net.append({'values':[source.number,stores.get(row.store_id,''),app.business_date.isoformat(),names[source.kind],'已批准售后减免',yuan(amount)],
                'route':{'type':'case','id':source.id},'amount_cents':amount,'source_kind':source.kind,'aftercare_case_id':app.case_id})
    for row in source_tables.get('claims_business_adjustments',{}).get('rows',[]):
        values=row['values'];amount=row['amount_cents'];totals['repair']+=amount
        net.append({'values':[values[0],values[1],values[2],'维修对外结算','已生效核赔减免',yuan(amount)],
            'route':{'type':'case','id':row['source_case_id']},'amount_cents':amount,'source_kind':'repair','claim_application_id':row['application_id']})
    for row in source_tables.get('service_fee_facts',{}).get('rows',[]):
        values=row['values'];kind=row['source_kind'];amount=row['amount_cents'];totals[kind]+=amount
        net.append({'values':[values[0],values[1],values[2],values[3],values[5],yuan(amount)],'route':row['route'],
            'amount_cents':amount,'source_kind':kind,'service_fact_id':row['fact_id'],'service_fact_kind':row['fact_kind']})
    for key,label,index in [('addon_actual_facts','加装实际履约净额',3),('insurance_commission_facts','保险公司已确认佣金',4)]:
        for row in source_tables.get(key,{}).get('rows',[]):
            values=row['values'];kind=row['source_kind'];amount=row['amount_cents'];totals[kind]+=amount
            net.append({'values':[values[0],values[1],values[2],label,str(values[index]),yuan(amount)],'route':row['route'],
                'amount_cents':amount,'source_kind':kind,'service_fact_id':row['fact_id'],'service_fact_kind':row['fact_kind']})
    tables['aftercare_adjustments']={'title':'期间售后原单减免','headers':['原业务','门店','调整日期','业务口径','原单减免（元）','已记录履约金额调整（元）','统计依据'],'rows':adjustments}
    tables['business_net_facts']={'title':'期间已记录业务净额明细','headers':['原业务','门店','发生日期','业务口径','来源事实','业务净额（元）'],'rows':net}
    for key,title,rows,index in [('aftercare_adjustments','期间售后履约金额调整',adjustments,3),('business_net_facts','期间已记录业务净额',net,3)]:
        grouped=defaultdict(int)
        for row in rows:grouped[row['values'][index]]+=row['amount_cents']
        labels=sorted(grouped)
        charts.append({'id':key,'title':title,'section':'finance','type':'bar','unit':'cents','labels':labels,'series':[{'name':'业务金额','values':[grouped[k] for k in labels]}],
            'table':key,'caption':'原履约金额保留原发生日期；已生效售后减免记在调整日期。原款实际退款另计现金，不能再次扣业务金额；未交付车价与代收保费不计入本表。不是会计利润。'})
    return {'tables':tables,'charts':charts,'metrics':{'recorded_business_net_cents':sum(totals.values()),'aftercare_revenue_adjustment_cents':sum(r['amount_cents'] for r in adjustments),
        'vehicle_delivery_net_cents':totals['order'],'repair_settlement_net_cents':totals['repair']}}
