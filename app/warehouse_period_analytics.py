"""Location history starts at witnessed activation, never an invented midnight."""
from collections import defaultdict
from sqlalchemy import select, or_
from fastapi import HTTPException
from .models import Store, AuditLog
from .db import today
from .flow_models import Item, Case, FlowEvent, StockMove
from .master_models import StorageLocation, Warehouse, OpeningStockEntry
from .warehouse_models import WarehouseBalance, WarehouseEntry, WarehouseEnrollment, WarehouseDocument, WarehouseAllocation, WarehouseAllocationLine
from .inventory_report_common import bounded, period, local_date, yuan, qty, as_of, route, table, MONEY_ROLES

DEFINITION = ('库位历史从主管实际批准启用的桥接时刻开始；启用基准不算当期进货。开始日不晚于启用日时，'
              '午夜期初与全期间收发未知，只列有据片段和可核对期末。店内在途归发出仓并单列，不能重复计入目的仓。'
              '价值为门店均价分配到各库位的账面值；收发价值保留原有符号，零数量的均价分摊调整单列，不视为实物进货或销售成本。')
REASONS = {'activation':'库位启用基准','local_dispatch':'店内实际移出','local_accept':'店内实际接收','local_return':'店内拒收原退',
           'average_revaluation':'均价分摊调整','wh_other_in':'其他实际入库','wh_other_in_return':'其他入库原退',
           'wh_consumable':'耗材实际领用','wh_consumable_return':'耗材原单退回','wh_gift':'礼品实际发出','wh_gift_return':'礼品原单退回',
           'wh_disposal':'物资实际处置','wh_count':'盘点差异实际过账','procurement_receipt':'采购实际验收','procurement_return':'采购实际退回',
           'transfer_out':'跨店实际发出','transfer_in':'跨店实际接收','transfer_return':'跨店原退接收','repair_issue_v3':'维修实际领料',
           'repair_return_v3':'维修原料退回','retail_dispatch':'精品实际出库','retail_return':'精品原单退货',
           'purchase':'原采购实际收货','issue':'原物资实际领用','return':'原物资退回','count':'原盘点实际过账'}


def build_warehouse_period(db,user,start=None,end=None,item_id=None,warehouse_id=None):
    start,end=period(user,start,end);can_money=user.role in MONEY_ROLES
    stores=dict(db.execute(select(Store.id,Store.name)).all())
    warehouses={w.id:w for w in bounded(db,Warehouse)}
    if warehouse_id and warehouse_id not in warehouses:raise HTTPException(404,'当前授权门店没有该仓库')
    locations={l.id:l for l in bounded(db,StorageLocation)}
    location_changes=bounded(db,AuditLog,select(AuditLog).where(AuditLog.entity_type=='typed_master',AuditLog.action=='master_update',AuditLog.entity_id.in_(locations)))
    item_query=select(Item)
    if item_id:item_query=item_query.where(Item.id==item_id)
    if warehouse_id:
        lids=[l.id for l in locations.values() if l.warehouse_id==warehouse_id]
        # A historical parent change must not erase the old warehouse from a
        # filtered report. Include the affected locations for the evidence
        # check below, then reject ambiguous post-activation reparenting.
        for audit in location_changes:
            before=audit.before_data or {};after=audit.after_data or {}
            if warehouse_id in {before.get('warehouse_id'),after.get('warehouse_id')}:
                lids.append(audit.entity_id)
        moves=select(WarehouseDocument.id).where(WarehouseDocument.operation=='local_move',WarehouseDocument.source_location_id.in_(lids))
        members=select(WarehouseBalance.item_id).where(or_(WarehouseBalance.location_id.in_(lids),WarehouseBalance.transit_case_id.in_(moves)))
        item_query=item_query.where(Item.id.in_(members))
    items={r.id:r for r in bounded(db,Item,item_query)}
    if item_id and not items and not warehouse_id:raise HTTPException(404,'当前授权门店没有该物资')
    ids=list(items)
    enrollments={r.item_id:r for r in bounded(db,WarehouseEnrollment,select(WarehouseEnrollment).where(WarehouseEnrollment.item_id.in_(ids)))}
    balances=bounded(db,WarehouseBalance,select(WarehouseBalance).where(WarehouseBalance.item_id.in_(ids)))
    by_balance={r.id:r for r in balances};by_item=defaultdict(list)
    for b in balances:by_item[b.item_id].append(b)
    entries=bounded(db,WarehouseEntry,select(WarehouseEntry).where(WarehouseEntry.balance_id.in_(by_balance)))
    docs={r.id:r for r in bounded(db,WarehouseDocument,select(WarehouseDocument).where(WarehouseDocument.item_id.in_(ids)))}
    case_ids={e.case_id for e in entries}|{e.case_id for e in enrollments.values()}|set(docs)
    cases={r.id:r for r in bounded(db,Case,select(Case).where(Case.id.in_(case_ids)))}
    approvals=defaultdict(list)
    for e in bounded(db,FlowEvent,select(FlowEvent).where(FlowEvent.case_id.in_([x.case_id for x in enrollments.values()]),FlowEvent.action=='warehouse_approve')):
        approvals[e.case_id].append(e)
    activation_plans={a.id:a for a in bounded(db,WarehouseAllocation,select(WarehouseAllocation).where(WarehouseAllocation.case_id.in_([e.case_id for e in enrollments.values()]),WarehouseAllocation.purpose=='activation',WarehouseAllocation.status=='consumed'))}
    initial_locations=defaultdict(set)
    for line in bounded(db,WarehouseAllocationLine,select(WarehouseAllocationLine).where(WarehouseAllocationLine.allocation_id.in_(activation_plans))):
        initial_locations[activation_plans[line.allocation_id].item_id].add(line.location_id)
    moves=bounded(db,StockMove,select(StockMove).where(StockMove.item_id.in_(ids)))
    opening=bounded(db,OpeningStockEntry,select(OpeningStockEntry).where(OpeningStockEntry.item_id.in_(ids)))
    efacts=defaultdict(list);move_entries=defaultdict(list);item_entries=defaultdict(list)
    for e in entries:
        efacts[e.balance_id].append(e);item_entries[by_balance[e.balance_id].item_id].append(e)
        if e.stock_move_id:move_entries[e.stock_move_id].append(e)
    errors=defaultdict(list);bridges={}
    def issue(key,message):
        if message not in errors[key]:errors[key].append(message)
    for key,item in items.items():
        en=enrollments.get(key)
        if not en:issue(key,'尚无经批准的真实库位启用来源，不能推断历史库位');continue
        ev=approvals[en.case_id];case=cases.get(en.case_id);doc=docs.get(en.case_id)
        if len(ev)!=1 or not case or case.state!='completed' or not doc or doc.operation!='activate':
            issue(key,'库位启用缺少唯一完成批准事实');continue
        bridges[key]=ev[0].occurred_at
        if not initial_locations[key]:issue(key,'启用桥接没有实际选定的初始库位')
        old=[m for m in moves if m.item_id==key and m.id<=en.stock_move_cursor]
        initial=[o for o in opening if o.item_id==key]
        prior=(sum(m.quantity_milli for m in old)+sum(o.quantity_milli for o in initial),sum(m.value_cents for m in old)+sum(o.value_cents for o in initial))
        baseline=[e for e in item_entries[key] if e.case_id==en.case_id and e.stock_move_id is None]
        actual=(sum(e.quantity_milli for e in baseline),sum(e.value_cents for e in baseline))
        if prior!=actual or actual!=(en.baseline_quantity_milli,en.baseline_value_cents):issue(key,'启用基准与原期初、历史收发或库位分配不守恒')
        if any(e.reason!='activation' or e.business_date!=local_date(bridges[key]) for e in baseline):issue(key,'启用分配与实际批准日期不一致')
        for m in [m for m in moves if m.item_id==key and m.id>en.stock_move_cursor]:
            ee=move_entries[m.id]
            if (sum(e.quantity_milli for e in ee),sum(e.value_cents for e in ee))!=(m.quantity_milli,m.value_cents):issue(key,'启用后原物资收发与库位流水不守恒')
            if any(e.case_id!=m.case_id or e.store_id!=m.store_id or e.business_date!=m.business_date for e in ee):issue(key,'原物资收发的日期或门店关联不一致')
        after_ids={m.id for m in moves if m.item_id==key and m.id>en.stock_move_cursor}
        if any(e.stock_move_id and e.stock_move_id not in after_ids for e in item_entries[key]):issue(key,'库位流水关联到启用前或其他物资原收发')
        for e in item_entries[key]:
            if e.store_id!=item.store_id or not cases.get(e.case_id) or cases[e.case_id].store_id!=item.store_id:issue(key,'库位流水原业务归属不一致')
            if e.business_date<local_date(bridges[key]):issue(key,'启用后流水日期早于真实启用桥接日')
            if e.business_date>today():issue(key,'实际库位流水日期晚于今天')
        if (sum(b.quantity_milli for b in by_item[key]),sum(b.value_cents for b in by_item[key]))!=(item.quantity_milli,item.inventory_value_cents):issue(key,'当前库位及在途合计与门店库存不守恒')
    # Previous versions could reparent an emptied material bin. Do not use the
    # new parent as its old warehouse. Audit facts identify ambiguity, not a
    # guessed automatic migration of historical ownership.
    changed=set()
    for audit in location_changes:
        before=audit.before_data or {};after=audit.after_data or {}
        if 'warehouse_id' in before and 'warehouse_id' in after and before['warehouse_id']!=after['warehouse_id']:
            relevant=[b for b in balances if b.location_id==audit.entity_id and b.store_id==audit.store_id and bridges.get(b.item_id) and audit.occurred_at>=bridges[b.item_id]]
            if relevant:
                changed.add(audit.entity_id)
                if warehouse_id in {before['warehouse_id'],after['warehouse_id']}:raise HTTPException(409,'该仓库有启用后变更所属仓的历史库位，请先按物资或全店核对历史归属')
    rows=[];details=[];baseline_rows=[]
    for key,item in items.items():
        bridge=bridges.get(key);day=local_date(bridge) if bridge else None
        if not by_item[key]:
            rows.append({'item_id':key,'store_id':item.store_id,'sku':item.sku,'name':item.name,'unit':item.unit,'balance_id':None,'warehouse_id':None,
                         'warehouse':'未明确仓库','location':'未启用真实库位','period_complete':False,'closing_complete':False,'coverage_start':None,
                         'issues':errors[key] or ['没有真实库位来源'],'opening':None,'in':None,'out':None,'closing':None,'revaluation_cents':None,
                         'known_in_milli':0,'known_out_milli':0,'known_value_delta_cents':0})
            continue
        for b in by_item[key]:
            loc=locations.get(b.location_id);doc=docs.get(b.transit_case_id) if b.transit_case_id else None
            source=locations.get(doc.source_location_id) if doc else None
            wh_id=loc.warehouse_id if loc else source.warehouse_id if source else None
            if warehouse_id and wh_id!=warehouse_id:continue
            wh=warehouses.get(wh_id);problems=list(errors[key])
            if (loc and loc.id in changed) or (source and source.id in changed):problems.append('库位启用后曾改变所属仓，历史仓库归属待核对')
            if not wh or wh.store_id!=item.store_id or (b.location_id and not loc) or (not b.location_id and (not doc or doc.operation!='local_move')):problems.append('库位或在途缺少本店原仓库作业来源')
            ff=sorted(efacts[b.id],key=lambda e:(e.business_date,e.occurred_at,e.id))
            running_q=running_v=0
            for e in ff:
                running_q+=e.quantity_milli;running_v+=e.value_cents
                if running_q<0 or running_v<0 or (not running_q and running_v):problems.append('原始库位数量或价值次序不能重建')
            if (running_q,running_v)!=(b.quantity_milli,b.value_cents):problems.append('库位原始流水与当前余额不一致')
            base=[e for e in ff if enrollments.get(key) and e.case_id==enrollments[key].case_id and e.stock_move_id is None]
            base_q=sum(e.quantity_milli for e in base);base_v=sum(e.value_cents for e in base)
            location_label=loc.name if loc else '店内在途 · '+(cases[b.transit_case_id].number if b.transit_case_id in cases else str(b.transit_case_id))
            if b.location_id in initial_locations[key]:baseline_rows.append({'item_id':key,'store_id':item.store_id,'balance_id':b.id,'sku':item.sku,'unit':item.unit,
                                  'warehouse':wh.name if wh else '待核对','location':location_label,
                                  'quantity_milli':base_q,'value_cents':base_v,'coverage_start':bridge.isoformat()+'Z' if bridge else None,
                                  'case_id':enrollments[key].case_id if key in enrollments else None})
            totals={s:{'quantity_milli':0,'value_cents':0} for s in ('opening','in','out','closing')};revalue=0
            known_in=known_out=known_value=0
            for e in ff:
                if e.business_date<start:
                    totals['opening']['quantity_milli']+=e.quantity_milli;totals['opening']['value_cents']+=e.value_cents
                if e.business_date<=end:
                    totals['closing']['quantity_milli']+=e.quantity_milli;totals['closing']['value_cents']+=e.value_cents
                if not start<=e.business_date<=end:continue
                is_base=e in base
                details.append({'item_id':key,'store_id':item.store_id,'balance_id':b.id,'sku':item.sku,'name':item.name,'unit':item.unit,
                                'warehouse':wh.name if wh else '待核对','location':location_label,'source_id':e.id,'case_id':e.case_id,
                                'stock_move_id':e.stock_move_id,'date':e.business_date.isoformat(),'quantity_milli':e.quantity_milli,
                                'value_cents':e.value_cents,'label':REASONS.get(e.reason,'原业务库位变动'),'is_baseline':is_base})
                if is_base:continue
                known_in+=max(0,e.quantity_milli);known_out+=max(0,-e.quantity_milli);known_value+=e.value_cents
                if e.quantity_milli:
                    stage='in' if e.quantity_milli>0 else 'out'
                    totals[stage]['quantity_milli']+=abs(e.quantity_milli)
                    totals[stage]['value_cents']+=e.value_cents # Outbound value remains signed, including reallocation effects.
                else:revalue+=e.value_cents
            ok=not problems;period_ok=ok and day is not None and start>day;closing_ok=ok and day is not None and end>=day
            if not day or start<=day:problems.append('请求期初不晚于启用日，午夜期初及启用前收发未知')
            if not day or end<day:problems.append('请求期末早于有据启用桥接，不能推断历史结存')
            if not period_ok:
                for stage in ('opening','in','out'):totals[stage]=None
                revalue=None
            if not closing_ok:totals['closing']=None
            rows.append({'item_id':key,'store_id':item.store_id,'sku':item.sku,'name':item.name,'unit':item.unit,'balance_id':b.id,'warehouse_id':wh_id,
                         'warehouse':wh.name if wh else '待核对','location':location_label,'transit_case_id':b.transit_case_id,
                         'period_complete':period_ok,'closing_complete':closing_ok,'coverage_start':bridge.isoformat()+'Z' if bridge else None,
                         'issues':list(dict.fromkeys(problems)),**totals,'revaluation_cents':revalue,
                         'known_in_milli':known_in,'known_out_milli':known_out,'known_value_delta_cents':known_value})
    complete=all(r['period_complete'] for r in rows);closing_complete=all(r['closing_complete'] for r in rows)
    tables={}
    headers=['门店','物资编码','物资','单位','仓库','库位或店内在途','期初数量','完整期间入库数量','完整期间出库数量','已知期末数量']
    if can_money:headers+=['期初价值（元）','入库有符号价值变动（元）','出库有符号价值变动（元）','均价分摊调整（元）','已知期末价值（元）']
    headers+=['期间是否完整','期末是否完整','来源说明']
    total_table=table('库位期间入出存及覆盖范围',headers);tables['warehouse_period_balances']=total_table
    for r in rows:
        vals=[stores.get(r['store_id'],''),r['sku'],r['name'],r['unit'],r['warehouse'],r['location']]+[qty(r[s]['quantity_milli']) if r[s] is not None else '—' for s in ('opening','in','out','closing')]
        if can_money:vals+=[yuan(r[s]['value_cents']) if r[s] is not None else '—' for s in ('opening','in','out')]+[yuan(r['revaluation_cents']),yuan(r['closing']['value_cents']) if r['closing'] is not None else '—']
        total_table['rows'].append({'values':vals+['完整' if r['period_complete'] else '有覆盖缺口','完整' if r['closing_complete'] else '来源不足','；'.join(r['issues'])],
                                    'item_id':r['item_id'],'closing_quantity_milli':r['closing']['quantity_milli'] if r['closing'] is not None else None,
                                    **({'closing_value_cents':r['closing']['value_cents'] if r['closing'] is not None else None} if can_money else {})})
    baseline_table=table('真实启用桥接基准（不是当期进货）',['门店','物资编码','单位','仓库','库位或在途','实际启用时刻（UTC）','分配基准数量']+(['分配基准价值（元）'] if can_money else []));tables['warehouse_period_baselines']=baseline_table
    for r in baseline_rows:
        baseline_table['rows'].append({'values':[stores.get(r['store_id'],''),r['sku'],r['unit'],r['warehouse'],r['location'],r['coverage_start'] or '来源不足',qty(r['quantity_milli'])]+([yuan(r['value_cents'])] if can_money else []),'route':route(db,r['case_id']) if r['case_id'] else None})
    detail_table=table('所选期间已记录库位流水',['门店','实际日期','物资编码','单位','仓库','库位或在途','实际业务','原库位流水','原物资流水','数量变化']+(['有符号价值变化（元）'] if can_money else []));tables['warehouse_period_entries']=detail_table
    details.sort(key=lambda r:(r['date'],r['source_id']))
    for r in details:
        detail_table['rows'].append({'values':[stores.get(r['store_id'],''),r['date'],r['sku'],r['unit'],r['warehouse'],r['location'],r['label'],r['source_id'],r['stock_move_id'] or '不新增门店收发',qty(r['quantity_milli'])]+([yuan(r['value_cents'])] if can_money else []),'route':route(db,r['case_id']),
                                     'quantity_milli':r['quantity_milli'],**({'amount_cents':r['value_cents']} if can_money else {})})
    charts=[]
    if closing_complete and can_money:
        totals=defaultdict(int)
        for r in rows:totals[stores.get(r['store_id'],'')+' · '+r['warehouse']]+=r['closing']['value_cents']
        labels=sorted(totals)
        charts.append({'id':'warehouse_period_closing','title':'有据期末库位及店内在途价值','section':'inventory','type':'bar','unit':'cents','labels':labels,
                       'series':[{'name':'账面价值','values':[totals[k] for k in labels]}],'table':'warehouse_period_balances',
                       'caption':'此图仅表示已知期末；期间完整性另行标示。店内在途按发出仓列一次，不增加门店库存。'})
    if not can_money:
        for r in rows:
            for s in ('opening','in','out','closing'):
                if r[s] is not None:r[s].pop('value_cents')
            r.pop('revaluation_cents');r.pop('known_value_delta_cents')
        for r in details+baseline_rows:r.pop('value_cents')
    return {'date_from':start.isoformat(),'date_to':end.isoformat(),'as_of':as_of(),'can_money':can_money,'complete':complete,'closing_complete':closing_complete,
            'rows':rows,'details':details,'baselines':baseline_rows,'tables':tables,'charts':charts,'definition':DEFINITION,'definitions':[DEFINITION],
            'metrics':{'warehouse_period_complete':complete,'warehouse_period_closing_complete':closing_complete,'warehouse_period_gap_count':sum(not r['period_complete'] for r in rows)},
            'filters':{'item_id':item_id,'warehouse_id':warehouse_id,'note':'仓库筛选只含有明确归属的库位及该仓发出的店内在途；未定位物资请在全店视图单独核对。'}}
