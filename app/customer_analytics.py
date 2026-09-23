"""Authorized shared identities group facts; phone/name never merge customers."""
from collections import defaultdict
from decimal import Decimal
from sqlalchemy import select
from fastapi import HTTPException
from .flow_models import Customer
from .group_models import GroupIdentityLink
from .customer_service_models import CustomerVehicle


def build_customer_analytics(db,user,cases,stores,source_tables,bounded,yuan):
    tables={};charts=[];metrics={};byid={r.id:r for r in cases}
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([i for i in db.info.get('store_scope',()) if i])>1)
    customers={r.id:r for r in bounded(db,Customer)}
    identities={r.local_id:r.identity_id for r in bounded(db,GroupIdentityLink,select(GroupIdentityLink).where(GroupIdentityLink.local_kind=='customer'))}
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def chart(key,title,totals,caption,unit='cents'):
        labels=sorted(totals)
        charts.append({'id':key,'title':title,'section':'customers','type':'bar','unit':unit,'labels':labels,
            'series':[{'name':'业务金额' if unit=='cents' else '车辆','values':[totals[k] for k in labels]}],
            'table':key,'caption':caption})
    vehicles=defaultdict(list)
    for v in bounded(db,CustomerVehicle,select(CustomerVehicle).where(CustomerVehicle.active.is_(True))):vehicles[v.vehicle_identity_id].append(v)
    vehicle_rows=table('customer_vehicle_stats','当前客户车辆身份统计',['共享车辆编号','登记车型','关联门店','有效客户关系数','车型资料'])
    vehicle_totals=defaultdict(int)
    for identity,relations in sorted(vehicles.items()):
        models={v.model_name for v in relations};model=next(iter(models)) if len(models)==1 else '车型资料待核对'
        vehicle_totals[model]+=1
        route={'type':'customer_vehicle','id':relations[0].id} if not aggregate and user.role in {'admin','manager','auditor'} else None
        vehicle_rows.append({'values':['GV-'+str(identity),model,' / '.join(sorted({stores.get(v.store_id,'') for v in relations})),len(relations),
            '一致' if len(models)==1 else '各门店登记车型不一致'],'route':route,'vehicle_count':1})
    chart('customer_vehicle_stats','当前客户车辆按车型分布',vehicle_totals,
        '仅有效客户车辆关系，按已人工确认的共享车辆身份去重；相同VIN跨获权门店只计一辆。不是整车库存、所有权证明或历史期末数；不同车型登记先列待核对，不猜车型。',unit='count')
    metrics['customer_vehicle_identity_count']=len(vehicles)
    metrics['customer_vehicle_relation_count']=sum(len(v) for v in vehicles.values())

    headers=['客户归集编号','客户显示名','门店','原单','发生日期','业务事实','业务金额（元）']
    details=table('customer_value_details','期间客户已记录业务明细',headers)
    legacy=table('customer_value_unlinked','期间尚未绑定客户身份的历史业务',['原单','门店','发生日期','业务事实','业务金额（元）'])
    groups={};unlinked=defaultdict(int)
    datasets=[('business_net_facts','',2,5)]
    for key,label,day_index,amount_index in datasets:
        for entry in source_tables[key]['rows']:
            values=entry['values'];route=entry.get('route') or {};amount=int(Decimal(str(values[amount_index]))*100)
            label=values[3]+' · '+values[4]
            case=byid.get(route.get('id')) if route.get('type')=='case' else None
            if not case or not case.customer_id:
                legacy.append({'values':[values[0],values[1],values[day_index],label,yuan(amount)],'route':entry.get('route'),'amount_cents':amount})
                unlinked[label]+=amount;continue
            customer=customers.get(case.customer_id)
            if not customer:raise HTTPException(409,'业务原客户档案缺失，不能按姓名或电话猜测归集')
            identity=identities.get(customer.id);token='g'+str(identity) if identity else 's'+str(customer.store_id)+'c'+str(customer.id)
            g=groups.setdefault(token,{'names':set(),'stores':set(),'cases':set(),'total':0,'vehicle':0,'repair':0,'retail':0,'services':0})
            g['names'].add(customer.name);g['stores'].add(case.store_id);g['cases'].add(case.id);g['total']+=amount
            category={'order':'vehicle','repair':'repair','retail':'retail'}.get(entry['source_kind'],'services');g[category]+=amount
            details.append({'values':[token,customer.name,stores.get(case.store_id,''),case.number,values[day_index],label,yuan(amount)],
                'route':route,'amount_cents':amount,'customer_key':token})
    summary=table('customer_value','期间客户已记录业务归集',['客户归集编号','客户显示名','涉及门店','涉及原单数','整车交付（元）','维修对外结算（元）','精品履约净额（元）','服务履约及已确认佣金（元）','业务金额合计（元）'])
    totals=defaultdict(int)
    for token,g in sorted(groups.items()):
        name=' / '.join(sorted(g['names']));total=g['total'];totals[token+' · '+name]+=total
        summary.append({'values':[token,name,' / '.join(stores.get(i,'') for i in sorted(g['stores'])),len(g['cases']),
            yuan(g['vehicle']),yuan(g['repair']),yuan(g['retail']),yuan(g['services']),yuan(total)],
            'route':{'type':'customer_value','id':token},'amount_cents':total,'customer_key':token})
    chart('customer_value','期间客户业务金额',totals,
        '按原业务版本归集整车交付、维修对外结算、精品及加装履约净额、代办服务和已确认保险佣金；保险佣金由保险公司承担，不代表客户直接消费。不是利润或客户未来价值。充值、预收、代收保费及预计佣金不计。相同姓名/电话不合并，跨店归集只使用明确共享身份。')
    chart('customer_value_unlinked','尚未绑定客户身份的历史业务金额',unlinked,
        '保留历史原单的同口径金额，但不按姓名、车牌或电话自动并入某位客户；明细可回原单核对。此表与已关联客户表互不重复。')
    metrics.update(customer_period_amount_cents=sum(totals.values()),customer_unlinked_amount_cents=sum(unlinked.values()),customer_period_count=len(groups))
    return {'tables':tables,'charts':charts,'metrics':metrics}
