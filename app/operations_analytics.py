"""Physical positions, service intake and membership facts with separate denominators."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import select
from fastapi import HTTPException
from .config import settings
from .flow_models import Item,StockMove,FlowEvent
from .master_models import Warehouse,StorageLocation
from .warehouse_models import WarehouseBalance,WarehouseEntry,WarehouseDocument,WarehouseEnrollment
from .service_intake_models import ServiceAppointment,ArrivalFact,ServiceResource,RepairIntake,ReworkRequest
from .membership_service import analytics_rows


def local_day(value):
    if isinstance(value,str):value=datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()


def build_operations(db,user,start,end,cases,stores,cash,bounded,yuan):
    byid={r.id:r for r in cases};tables={};charts=[];metrics={}
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def row(target,values,case_id=None,**meta):
        target.append({'values':values,'route':{'type':'case','id':case_id} if case_id else None,**meta})
    def chart(key,title,section,totals,caption,unit='cents',series='金额'):
        labels=sorted(totals)
        charts.append({'id':key,'title':title,'section':section,'type':'bar','unit':unit,'labels':labels,
            'series':[{'name':series,'values':[totals[k] for k in labels]}],'table':key,'caption':caption})
    def number(key):return byid[key].number if key in byid else str(key)
    def qty(value):return format(Decimal(value)/1000,'f')
    items={r.id:r for r in bounded(db,Item)}
    warehouses={r.id:r for r in bounded(db,Warehouse)}
    locations={r.id:r for r in bounded(db,StorageLocation)}
    balances={r.id:r for r in bounded(db,WarehouseBalance)}
    docs={r.id:r for r in bounded(db,WarehouseDocument)}
    enrollments={r.item_id:r for r in bounded(db,WarehouseEnrollment)}
    totals=defaultdict(lambda:[0,0])
    values=defaultdict(int)
    target=table('warehouse_balances','当前已启用物资的库位与店内在途',['门店','物资编码','名称','仓库','库位或在途单','数量','单位','成本（元）'])
    for b in balances.values():
        item=items[b.item_id];location=locations.get(b.location_id)
        warehouse=warehouses[location.warehouse_id].name if location else '店内移库在途'
        label=location.name if location else number(b.transit_case_id)
        totals[item.id][0]+=b.quantity_milli;totals[item.id][1]+=b.value_cents
        values[stores.get(b.store_id,'')+' · '+warehouse]+=b.value_cents
        row(target,[stores.get(b.store_id,''),item.sku,item.name,warehouse,label,qty(b.quantity_milli),item.unit,yuan(b.value_cents)],
            b.transit_case_id or enrollments[item.id].case_id,quantity_milli=b.quantity_milli,amount_cents=b.value_cents)
    for key in enrollments:
        if totals[key]!=[items[key].quantity_milli,items[key].inventory_value_cents]:
            raise HTTPException(409,'库位及店内在途合计与门店库存不符，已停止生成统计，请核对原始收发账')
    chart('warehouse_balances','当前库位与店内在途价值','materials',values,
        '仅已明确启用库位的物资；库位加店内在途等于本店物资总账。这是总库存的分布，不能再加到总库存；不同单位数量不相加。')
    metrics['warehouse_enrolled_value_cents']=sum(values.values())
    metrics['warehouse_local_transit_cents']=sum(b.value_cents for b in balances.values() if b.transit_case_id)
    target=table('warehouse_local_moves','期间店内移库配对明细',['作业单','门店','日期','物资编码','名称','库位或在途单','动作','数量变化','单位','价值变化（元）'])
    labels={'local_dispatch':'实际发出','local_accept':'实际接收','local_return':'原库位实际退回','average_revaluation':'移动平均价值分摊'}
    net=defaultdict(int)
    for e in bounded(db,WarehouseEntry,select(WarehouseEntry).where(WarehouseEntry.business_date>=start,WarehouseEntry.business_date<=end)):
        if e.case_id not in docs or docs[e.case_id].operation!='local_move':continue
        b=balances[e.balance_id];item=items[b.item_id];location=locations.get(b.location_id)
        label=location.name if location else '在途 '+number(b.transit_case_id)
        net[e.business_date.isoformat()]+=e.value_cents
        row(target,[number(e.case_id),stores.get(e.store_id,''),e.business_date.isoformat(),item.sku,item.name,label,
            labels.get(e.reason,e.reason),qty(e.quantity_milli),item.unit,yuan(e.value_cents)],e.case_id,
            quantity_milli=e.quantity_milli,amount_cents=e.value_cents)
    chart('warehouse_local_moves','期间店内移库价值净变化','materials',net,
        '每次真实移库的原库位、在途、目的库位及移动平均分摊逐项列出；各次净变化应为零，不计采购、销售或新的店间往来。')
    target=table('warehouse_counts','期间实盘批准差异过账',['作业单','门店','日期','物资编码','名称','数量差异','单位','价值差异（元）'])
    count_values=defaultdict(int)
    for move in bounded(db,StockMove,select(StockMove).where(StockMove.purpose=='wh_count',StockMove.business_date>=start,StockMove.business_date<=end)):
        item=items[move.item_id];count_values[stores.get(move.store_id,'')]+=move.value_cents
        row(target,[number(move.case_id),stores.get(move.store_id,''),move.business_date.isoformat(),item.sku,item.name,
            qty(move.quantity_milli),item.unit,yuan(move.value_cents)],move.case_id,quantity_milli=move.quantity_milli,amount_cents=move.value_cents)
    chart('warehouse_counts','期间实盘批准差异价值','materials',count_values,
        '只统计批准后真实追加的盘盈盘亏流水；作废观察不计。此金额已经包含在期间物资出入库，不重复计入。')

    membership=analytics_rows(db,user);cash_byid={r.id:r for r in cash}
    target=table('membership_fees','期间会员续会实际收退费',['业务单','门店','实际收退日期','方向','金额（元）'])
    fees=defaultdict(int)
    for e in membership['fees']:
        actual=cash_byid[e.get('effective_cash_id',e['cash_id'])]
        if not start<=actual.business_date<=end:continue
        fees[stores.get(e['store_id'],'')]+=e['amount_cents']
        row(target,[number(e['case_id']),stores.get(e['store_id'],''),actual.business_date.isoformat(),
            '实际收取' if e['amount_cents']>0 else '原款退回',yuan(e['amount_cents'])],e['case_id'],amount_cents=e['amount_cents'])
    chart('membership_fees','期间会员续会实际收退费','members',fees,
        '按关联现金账实际业务日期；收取为正、原款退款为负。已包含在实际现金收支，不代表会员服务期间的收入确认，也不作为储值本金。')
    metrics['membership_fee_net_cents']=sum(fees.values())
    target=table('membership_points','期间消费积分目标变动',['原业务','门店','发生日期','积分变动','变更后符合规则的消费基数（元）'])
    points=defaultdict(int)
    for e in membership['point_changes']:
        day=local_day(e['occurred_at'])
        if not start<=day<=end:continue
        points[stores.get(e['store_id'],'')]+=e['units']
        row(target,[number(e['case_id']),stores.get(e['store_id'],''),day.isoformat(),e['units'],yuan(e['basis_cents'])],e['case_id'],units=e['units'])
    chart('membership_points','期间消费积分目标变动','members',points,
        '冻结规则计算的应得积分变动，退费需要追回的目标为负；实际可用积分见权益单位账，未追回部分另列。消费基数是各次变更后的值，不得按行相加。',unit='count',series='积分')
    target=table('membership_points_debts','当前退费后尚待追回积分',['原业务','门店','本次原应追回积分','当前未追回积分'])
    debts=defaultdict(int)
    for e in membership['point_debts']:
        if not e['outstanding_units']:continue
        case=byid[e['case_id']];name=stores.get(case.store_id,'');debts[name]+=e['outstanding_units']
        row(target,[case.number,name,e['units'],e['outstanding_units']],case.id,units=e['outstanding_units'],debt_id=e['id'])
    chart('membership_points_debts','当前尚待追回积分','members',debts,
        '原店消费退费产生的待追回权益；历史已消费积分不阻断真实退款，后续积分抵补后减少。不是现金应收，不计入客户欠款。',unit='count',series='积分')
    metrics['membership_points_change_units']=sum(points.values());metrics['membership_points_debt_units']=sum(debts.values())

    resources={r.id:r for r in bounded(db,ServiceResource)}
    appointments={r.id:r for r in bounded(db,ServiceAppointment)}
    arrivals={r.appointment_id:r for r in bounded(db,ArrivalFact)}
    context={r.case_id:r for r in bounded(db,RepairIntake)}
    states={'scheduled':'预约待到店','arrived':'已到店待开单','converted':'已转维修工单','cancelled':'已取消或离场','no_show':'未到店结案'}
    target=table('service_appointments','按预约开始日期的接待批次',['接待单','门店','预约开始时间','类型','当前状态','本批次实际到店','关联维修单'])
    appointment_totals=defaultdict(int)
    for a in appointments.values():
        if not start<=local_day(a.starts_at)<=end:continue
        state=states[a.status];appointment_totals[state]+=1
        stamp=a.starts_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).strftime('%Y-%m-%d %H:%M')
        row(target,[number(a.case_id),stores.get(a.store_id,''),stamp,'预约' if a.mode=='appointment' else '直接到店',state,
            '是' if a.id in arrivals else '否',number(a.repair_case_id) if a.repair_case_id else ''],a.case_id)
    chart('service_appointments','所选接待批次的当前状态','repair',appointment_totals,
        '按预约开始日选择同一批接待记录，并查看它们截至当前的状态；改约会调整所属批次。不可与实际到店日的记录相除作为转化率。',unit='count',series='接待单')
    target=table('service_arrivals','期间实际到店事实',['接待单','门店','实际到店日期','类型','关联维修单'])
    arrival_totals=defaultdict(int)
    for e in arrivals.values():
        day=local_day(e.occurred_at)
        if not start<=day<=end:continue
        a=appointments[e.appointment_id];arrival_totals[day.isoformat()]+=1
        row(target,[number(a.case_id),stores.get(e.store_id,''),day.isoformat(),'预约' if a.mode=='appointment' else '直接到店',
            number(a.repair_case_id) if a.repair_case_id else ''],a.case_id)
    reworks={r.case_id:r for r in bounded(db,ReworkRequest)}
    for e in bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.action=='intake_rework_convert')):
        day=local_day(e.occurred_at)
        if not start<=day<=end:continue
        request=reworks.get(e.case_id)
        if not request or not request.repair_case_id:raise HTTPException(409,'返修实际到店事实缺少关联工单，请核对原记录')
        arrival_totals[day.isoformat()]+=1
        row(target,[number(e.case_id),stores.get(e.store_id,''),day.isoformat(),'原单返修',number(request.repair_case_id)],e.case_id)
    chart('service_arrivals','期间实际到店次数','repair',arrival_totals,
        '按预约、现场及返修不可变到店事实的当地日期；到店后离场或未开工仍保留次数，不等于完工或收款次数。未推断旧单的到店记录。',unit='count',series='实际到店')
    target=table('service_resources','当前工位实际占用',['门店','工位','用途','当前实际占用','维修单','维修类型'])
    resource_totals=defaultdict(int);profiles={'regular':'普通维修','wash':'洗车','quick':'快捷开单','rework':'原单返修'}
    for r in resources.values():
        if not r.active and not r.active_case_id:continue
        busy=bool(r.active_case_id);resource_totals['已实际占用' if busy else '空闲']+=1
        intake=context.get(r.active_case_id)
        row(target,[stores.get(r.store_id,''),r.name,'洗车工位' if r.resource_type=='wash' else '维修工位',
            '已占用' if busy else '空闲',number(r.active_case_id) if busy else '',profiles.get(intake.profile,'') if intake else ''],r.active_case_id)
    chart('service_resources','当前工位实际占用','repair',resource_totals,
        '由实际接手和释放记录决定；预约时间结束不会自动释放尚在施工的车辆。本表用于资源安排，不是员工绩效。',unit='count',series='工位')
    metrics['service_arrivals_count']=sum(arrival_totals.values());metrics['service_resources_busy']=resource_totals['已实际占用']
    return {'tables':tables,'charts':charts,'metrics':metrics}
