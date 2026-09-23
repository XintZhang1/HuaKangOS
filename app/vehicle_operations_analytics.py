"""Vehicle location facts are a distribution of inventory, never another stock total."""
from collections import defaultdict
from sqlalchemy import select
from fastapi import HTTPException
from .models import Vehicle
from .master_models import StorageLocation,Warehouse
from .vehicle_operations_models import VehiclePosition,VehiclePositionEntry,VehicleOperation,VehicleQuarantineFact
from .vehicle_operations_service import KINDS,STATUS


def build_vehicle_operations_analytics(db,user,cases,stores,bounded,yuan,in_period):
    byid={r.id:r for r in cases};vehicles={r.id:r for r in bounded(db,Vehicle)}
    locations={r.id:r for r in bounded(db,StorageLocation)};warehouses={r.id:r for r in bounded(db,Warehouse)}
    tables={};charts=[];aggregate=bool(getattr(user,'_aggregate_scope',False) or len([i for i in db.info.get('store_scope',()) if i])>1)
    def location(key):
        l=locations.get(key);w=warehouses.get(l.warehouse_id) if l else None
        return (w.name+' / '+l.name) if l and w else '无当前库位'
    def route(key):return None if aggregate else {'type':'case','id':key}
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def chart(key,title,rows,index,unit='cents',caption=''):
        total=defaultdict(int)
        for r in rows:total[r['values'][index]]+=r['amount_cents'] if unit=='cents' else 1
        labels=sorted(total)
        charts.append({'id':key,'title':title,'section':'inventory','type':'bar','unit':unit,'labels':labels,
            'series':[{'name':'库存价值' if unit=='cents' else '实车','values':[total[k] for k in labels]}],'table':key,'caption':caption})
    current=table('vehicle_locations','当前明确车辆库位及店内在途',['车辆编号','门店','VIN','车型','当前库位','实物状态','库存价值（元）'])
    for p in bounded(db,VehiclePosition,select(VehiclePosition).where(VehiclePosition.status.in_(['stored','transit','handover']))):
        car=vehicles[p.vehicle_id]
        current.append({'values':[car.doc_no,stores.get(p.store_id,''),car.vin,car.model,location(p.location_id),
            {'stored':'在库位','transit':'店内移库在途','handover':'出库待客户交接'}[p.status],yuan(car.purchase_cost_cents)],
            'route':{'type':'legacy','module':'vehicles','id':car.id},'amount_cents':car.purchase_cost_cents})
    chart('vehicle_locations','当前已定位实车分布',current,5,'count','只包含已有明确位置记录的车辆；无定位旧车不猜库位。与库存总表交叉核对，位置记录不另增加库存数量或价值。')
    movements=table('vehicle_location_moves','期间整车店内移库位置流水',['作业单','门店','日期','VIN','库位','位置变动（台）','位置价值变动（元）'])
    other=table('vehicle_other_movements','期间整车其他出入库及客户退车入库',['作业单','门店','日期','VIN','业务','库存变动（台）','库存价值变动（元）'])
    operations={r.id:r for r in bounded(db,VehicleOperation)}
    for e in bounded(db,VehiclePositionEntry):
        if not in_period(e.business_date):continue
        op=operations.get(e.operation_id);case=byid[e.case_id];car=vehicles[e.vehicle_id]
        if op and op.kind=='local_move':movements.append({'values':[case.number,stores.get(e.store_id,''),e.business_date.isoformat(),car.vin,location(e.location_id),e.quantity,yuan(e.value_cents)],
            'route':route(case.id),'amount_cents':e.value_cents,'quantity':e.quantity})
        if e.inventory_delta:
            other.append({'values':[case.number,stores.get(e.store_id,''),e.business_date.isoformat(),car.vin,KINDS.get(op.kind if op else '',e.kind),e.inventory_delta,yuan(e.value_cents)],
                'route':route(case.id),'amount_cents':e.value_cents,'quantity':e.inventory_delta})
    chart('vehicle_location_moves','期间车辆移库位置价值变动',movements,4,caption='按真实发出、接收和拒收退回的位置事实取数。期间仅发出时可以为负，在途仍属本店库存；不重复计算采购、店间调拨或销售。')
    chart('vehicle_other_movements','期间车辆其他出入库价值',other,4,caption='仅新增实际库存的原车退回/客户退车验收与退出可售库存的其他出库。申请、批准及隔离接收均不计库存；现金另表。')
    quarantine=table('vehicle_return_quarantine','当前客户退车待检查与处置',['售后实物单','门店','VIN','处理状态','实际隔离库位'])
    intakes={r.operation_id:r for r in bounded(db,VehicleQuarantineFact,select(VehicleQuarantineFact).where(VehicleQuarantineFact.kind=='intake'))}
    for op in operations.values():
        if op.kind!='customer_return' or op.status in {'accepted','returned_to_customer','cancelled','rejected','awaiting_receipt'}:continue
        case=byid[op.id]
        if op.id not in intakes:raise HTTPException(409,'客户退车处理状态缺少实际隔离接收凭据')
        quarantine.append({'values':[case.number,stores.get(op.store_id,''),op.vin,STATUS[op.status],location(intakes[op.id].location_id)],'route':route(op.id)})
    chart('vehicle_return_quarantine','当前退车隔离待办',quarantine,3,'count','反映已实际接收但尚未完成可售验收或交还的退车。不是可售库存，也不自动确认退款。')
    return {'tables':tables,'charts':charts,'metrics':{'vehicle_located_count':len(current),'vehicle_return_quarantine_count':len(quarantine),
        'vehicle_other_stock_delta':sum(r['quantity'] for r in other),'vehicle_other_value_delta_cents':sum(r['amount_cents'] for r in other)}}
