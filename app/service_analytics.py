"""Service facts, frozen project amounts and installation scope; never employee rankings."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from fastapi import HTTPException
from .flow_models import FlowEvent
from .flow_specs import STATES
from .repair_models import RepairQuote,RepairLine,RepairSettlement,RepairAuthorization
from .retail_models import RetailLine,RetailDispatch,RetailReturnLine,RetailReturnPosting
from .operations_analytics import local_day


def build_service_analytics(db,user,start,end,cases,stores,bounded,yuan):
    tables={};charts=[];metrics={};byid={r.id:r for r in cases}
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def add(target,values,case_id,**meta):target.append({'values':values,'route':{'type':'case','id':case_id},**meta})
    def chart(key,title,totals,section,caption):
        labels=sorted(totals)
        charts.append({'id':key,'title':title,'type':'bar','unit':'cents','section':section,'table':key,
            'labels':labels,'series':[{'name':'冻结金额','values':[totals[label] for label in labels]}],'caption':caption})
    def quantity(value):return format(Decimal(value)/1000,'f')
    events=bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.action.in_(['service_quote','service_finish','policy_issue','retail_install','retail_return_receive'])).order_by(FlowEvent.id))
    service_quotes={};done={}
    for event in events:
        case=byid.get(event.case_id)
        if not case:continue
        if event.action=='service_quote':service_quotes[event.case_id]=event
        elif event.action in {'service_finish','policy_issue'}:
            if event.case_id in done:raise HTTPException(409,'服务实际完工记录重复，请核对原业务')
            quoted=service_quotes.get(event.case_id)
            if not quoted or type(quoted.detail.get('amount')) is not int:
                raise HTTPException(409,'服务实际完成缺少此前冻结的核价依据，未生成猜测金额')
            done[event.case_id]=(event,quoted)
    for kind,label in [('addon','加装'),('agency','代办'),('insurance','保险')]:
        current=table(kind+'_orders',label+'本期新单及当前状态',['原单','门店','业务日期','当前状态','当前约定金额（元）','实际办理日期'])
        target=table(kind+'_completed','期间'+label+'实际办理核价依据',
            ['原单','门店','实际办理日期','核价金额（元）','预计佣金（元）' if kind=='insurance' else '办理事项'])
        totals=defaultdict(int)
        for case in cases:
            if case.kind!=kind or (kind in {'agency','insurance','addon'} and case.flow_version==3):continue
            fact=done.get(case.id)
            if start<=case.business_date<=end:
                add(current,[case.number,stores.get(case.store_id,''),case.business_date.isoformat(),STATES[case.state],
                    yuan(case.amount_cents),local_day(fact[0].occurred_at).isoformat() if fact else '尚无实际办理事实'],case.id,amount_cents=case.amount_cents)
            if not fact or not start<=local_day(fact[0].occurred_at)<=end:continue
            actual,quoted=fact;amount=quoted.detail['amount'];name=stores.get(case.store_id,'');totals[name]+=amount
            extra=yuan(quoted.detail.get('commission',0)) if kind=='insurance' else '参见原单冻结方案'
            add(target,[case.number,name,local_day(actual.occurred_at).isoformat(),yuan(amount),extra],case.id,amount_cents=amount)
        chart(kind+'_completed','期间'+label+('代收保费核价' if kind=='insurance' else '办理收费依据'),totals,'sales',
            '按实际办理事件日期，取此前核价事件冻结金额；付款晚到不改变办理日。'+
            ('保费是代收金额，佣金只是预计数，均不当作已实现营业收入；不与整车销售额相加。' if kind=='insurance' else '这是原核价与办理事实，收退款及后续售后费用纠正另查原账，不将预计收费当实际到账。'))
        metrics[kind+'_completed_basis_cents']=sum(totals.values())

    quotes={r.id:r for r in bounded(db,RepairQuote)}
    lines=bounded(db,RepairLine);lines_by_quote=defaultdict(list)
    for line in lines:lines_by_quote[line.quote_id].append(line)
    authorizations={r.quote_id for r in bounded(db,RepairAuthorization)}
    project=table('repair_projects','已交车维修的最终报价项目',['原单','门店','接车日期','报价版本','项目代码','项目','数量','计费单位','原核价金额（元）'])
    part=table('repair_parts','已交车维修的最终报价配件',['原单','门店','接车日期','报价版本','配件代码','配件','数量','单位','原核价金额（元）'])
    project_totals=defaultdict(int);part_totals=defaultdict(int)
    for settlement in bounded(db,RepairSettlement):
        case=byid.get(settlement.case_id)
        if not case or not case.data.get('released_date'):continue
        day=date.fromisoformat(case.data['released_date'])
        if not start<=day<=end:continue
        quote=quotes[settlement.quote_id]
        if quote.purpose!='service':continue
        if quote.id not in authorizations or sum(l.amount_cents for l in lines_by_quote[quote.id])!=quote.amount_cents:
            raise HTTPException(409,'维修最终报价授权或明细合计不一致，不能生成项目统计')
        for line in lines_by_quote[quote.id]:
            target=project if line.kind=='work' else part;totals=project_totals if line.kind=='work' else part_totals
            totals[line.code+' · '+line.name]+=line.amount_cents
            add(target,[case.number,stores.get(case.store_id,''),day.isoformat(),quote.revision,line.code,line.name,
                quantity(line.quantity_milli),line.unit,yuan(line.amount_cents)],case.id,amount_cents=line.amount_cents,quantity_milli=line.quantity_milli)
    caption='按客户实际接车日、最终已授权且用于结算的报价版本；增项前的旧报价不重计。项目核价包括各承担方，未推断项目级客户/保险比例；停工保留费另查原单。不是到账或维修对外收入。'
    chart('repair_projects','已交车维修项目核价',project_totals,'repair',caption)
    chart('repair_parts','已交车维修配件核价',part_totals,'repair',caption)
    metrics['repair_project_basis_cents']=sum(project_totals.values())
    metrics['repair_parts_basis_cents']=sum(part_totals.values())

    retail_lines=bounded(db,RetailLine);by_case=defaultdict(list)
    for line in retail_lines:by_case[line.case_id].append(line)
    dispatches={r.id:r for r in bounded(db,RetailDispatch)}
    return_lines={r.id:r for r in bounded(db,RetailReturnLine)}
    returned=bounded(db,RetailReturnPosting)
    return_events={e.detail.get('return_id'):e.id for e in events if e.action=='retail_return_receive'}
    installed=table('retail_installation','期间精品实际安装范围',['原单','门店','实际完工日期','商品','安装项目','实际安装数量','单位','当时安装收费依据（元）'])
    installation_totals=defaultdict(int)
    seen=set()
    for event in events:
        if event.action!='retail_install':continue
        if event.case_id in seen:raise HTTPException(409,'精品实际安装完成事实重复，请核对原单')
        seen.add(event.case_id)
        if event.case_id not in byid or not start<=local_day(event.occurred_at)<=end:continue
        case=byid[event.case_id]
        for line in by_case[case.id]:
            if not line.work_item_id:continue
            own=[r for r in returned if dispatches[r.dispatch_id].line_id==line.id]
            if any(return_lines[r.return_line_id].return_id not in return_events for r in own):
                raise HTTPException(409,'精品退回缺少实际事件顺序，不能猜测安装范围')
            before=[r for r in own if return_events[return_lines[r.return_line_id].return_id]<event.id]
            qty=line.quantity_milli-sum(r.quantity_milli for r in before)
            amount=line.installation_cents-sum(r.installation_cents for r in before)
            if qty<0 or amount<0:raise HTTPException(409,'精品安装前退货与原报价不一致')
            if not qty:continue
            installation_totals[line.work_code+' · '+line.work_name]+=amount
            add(installed,[case.number,stores.get(case.store_id,''),local_day(event.occurred_at).isoformat(),line.name,line.work_name,
                quantity(qty),line.unit,yuan(amount)],case.id,amount_cents=amount,quantity_milli=qty)
    chart('retail_installation','期间精品实际安装核价',installation_totals,'materials',
        '按技师实际完工事件取原安装报价，先扣完工之前实际退回的部分；后来退货不抹除已施工事实。各商品单位不相加，保留费和实际收入在精品结算表另核对。')
    metrics['retail_installation_basis_cents']=sum(installation_totals.values())
    return {'tables':tables,'charts':charts,'metrics':metrics}
