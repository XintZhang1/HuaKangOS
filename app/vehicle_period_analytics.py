"""Actual vehicle stock by immutable inventory generation, never inferred opening.

SQLite explicit read transactions and PostgreSQL REPEATABLE READ (db.py) give one
snapshot to every component of this report. No writes or expanded tenant scope.
"""
from collections import defaultdict
from sqlalchemy import select, or_
from fastapi import HTTPException
from .db import today
from .models import Vehicle, Store, Sale
from .flow_models import Case, FlowEvent
from .opening_import_models import OpeningVehicleEntry, OpeningImport
from .vehicle_procurement_models import VehiclePurchaseMovement, VehiclePurchaseShipment, VehiclePurchaseReceipt
from .vehicle_transfer_models import VehicleMovement, VehicleTransfer
from .vehicle_operations_models import VehiclePosition, VehiclePositionEntry
from .inventory_report_common import bounded, period, local_date, yuan, as_of, route, table, MONEY_ROLES

LABELS = {'opening': '经确认期初', 'purchase_receive': '采购实际验收', 'purchase_return': '采购实际退回',
          'transfer_dispatch': '跨店实际发出', 'transfer_accept': '跨店实际接收', 'transfer_return_receive': '跨店拒收后原退',
          'other_out': '其他实际出库', 'other_return': '其他原单实际退回', 'customer_return': '客户退车验收入库',
          'sale_dispatch': '销售实际出库', 'transport_found': '损失原车找到后实际入库'}
SOURCE_LABELS = {'opening_vehicle_entries': '期初车辆原账', 'vehicle_purchase_movements': '采购车辆原账',
                 'vehicle_transport_found_receipts': '原损失车辆真实找回入库', 'vehicle_movements': '跨店交接原账', 'vehicle_position_entries': '实车交接原账', 'flow_events': '原订单出库确认'}
STAGES = ('opening', 'in', 'out', 'closing')
DEFINITION = ('按车辆库存编号和代次重建：开始日前的有据流水为期初，首末日均计入期间。销售按实际出库日期，'
              '待客户交车已退出库内；营业收入仍按交车日期另表。店内移库不改变门店库存，采购发运未验收不计入库。'
              '调拨双边收发单列，不作集团对外采购销售；集团在途单独核对。缺历史来源时不反推期初、不出完整期末图。')


def build_vehicle_period(db, user, start=None, end=None, vin=None):
    start, end = period(user, start, end)
    can_money = user.role in MONEY_ROLES
    car_query = select(Vehicle)
    if vin:
        vin = vin.strip().upper()
        car_query = car_query.where(Vehicle.vin == vin)
    cars = {r.id: r for r in bounded(db, Vehicle, car_query)}
    # An in-transit purchase can have a VIN without a Vehicle row yet.
    shipments = bounded(db, VehiclePurchaseShipment, select(VehiclePurchaseShipment).where(VehiclePurchaseShipment.vin == vin) if vin else None)
    if vin and not cars and not shipments:
        raise HTTPException(404, '本次授权门店没有该 VIN 的库存或采购来源')
    ids = list(cars)
    stores = dict(db.execute(select(Store.id, Store.name)).all())
    cases = {c.id: c for c in bounded(db, Case)}
    positions = {p.vehicle_id: p for p in bounded(db, VehiclePosition, select(VehiclePosition).where(VehiclePosition.vehicle_id.in_(ids)))}
    entries = bounded(db, VehiclePositionEntry, select(VehiclePositionEntry).where(VehiclePositionEntry.vehicle_id.in_(ids)))
    issues = defaultdict(list)
    facts = []

    def issue(key, text):
        if text not in issues[key]: issues[key].append(text)

    def add(r, key, source, kind, quantity, value, day, case_id=None, internal='不涉及店间移转'):
        if key not in cars:
            raise HTTPException(409, '库存流水关联车辆不在同一授权范围，请核对来源')
        car = cars[key]
        if r.store_id != car.store_id:
            raise HTTPException(409, '库存流水与车辆归属不一致，请核对来源')
        facts.append({'source': source, 'source_id': r.id, 'vehicle_id': key, 'store_id': car.store_id,
                      'vin': car.vin, 'generation': car.inventory_generation, 'date': day.isoformat(),
                      'kind': kind, 'label': LABELS.get(kind, kind), 'quantity': quantity, 'value_cents': value,
                      'case_id': case_id, 'internal': internal})
        if day > today(): issue(key, '原始业务日期晚于今天')

    opening_imports = {r.id: r for r in bounded(db, OpeningImport)}
    for r in bounded(db, OpeningVehicleEntry, select(OpeningVehicleEntry).where(OpeningVehicleEntry.vehicle_id.in_(ids))):
        batch = opening_imports.get(r.import_id)
        add(r, r.vehicle_id, 'opening_vehicle_entries', 'opening', 1, r.value_cents, r.business_date, batch.case_id if batch else None)
        if not batch or batch.status != 'confirmed': issue(r.vehicle_id, '期初车辆缺少已确认批次')
    purchase_moves = bounded(db, VehiclePurchaseMovement)
    receipts = {r.shipment_id: r for r in bounded(db, VehiclePurchaseReceipt)}
    for r in purchase_moves:
        if r.vehicle_id not in cars or not r.quantity: continue
        add(r, r.vehicle_id, 'vehicle_purchase_movements', 'purchase_'+r.kind, r.quantity, r.value_cents, r.business_date, r.case_id)
        if r.kind == 'receive':
            rec = receipts.get(r.shipment_id)
            if not rec or (rec.vehicle_id, rec.value_cents, rec.business_date) != (r.vehicle_id, r.value_cents, r.business_date):
                issue(r.vehicle_id, '采购验收与原库存流水不一致')
    scope = tuple(i for i in db.info.get('store_scope', ()) if i)
    previous = db.info.get('_transfer_authority')
    db.info['_transfer_authority'] = ('report', scope)
    try:
        query = select(VehicleTransfer).where(or_(VehicleTransfer.from_store_id.in_(scope), VehicleTransfer.to_store_id.in_(scope)))
        if vin: query = query.where(VehicleTransfer.vin == vin)
        transfers = {r.id: r for r in bounded(db, VehicleTransfer, query)}
    finally:
        if previous is None: db.info.pop('_transfer_authority', None)
        else: db.info['_transfer_authority'] = previous
    transfer_moves = bounded(db, VehicleMovement, select(VehicleMovement).where(VehicleMovement.transfer_id.in_(transfers)))
    transfer_facts = defaultdict(dict)
    for r in transfer_moves:
        transfer_facts[r.transfer_id][r.kind] = r
        if not r.quantity or r.vehicle_id not in cars: continue
        transfer = transfers[r.transfer_id]
        internal = '授权范围内双边调拨' if transfer.from_store_id in scope and transfer.to_store_id in scope else '跨授权边界调拨'
        add(r, r.vehicle_id, 'vehicle_movements', 'transfer_'+r.kind, r.quantity, r.value_cents, r.business_date, r.case_id, internal)
    from .vehicle_transport_models import VehicleTransportFoundReceipt,VehicleTransportLoss
    transport_losses={r.transfer_id:r for r in bounded(db,VehicleTransportLoss,select(VehicleTransportLoss).where(VehicleTransportLoss.transfer_id.in_(transfers)))}
    for r in bounded(db,VehicleTransportFoundReceipt,select(VehicleTransportFoundReceipt).where(VehicleTransportFoundReceipt.vehicle_id.in_(cars))):
        if r.transfer_id not in transfers:raise HTTPException(409,'找回原车缺少本店原调拨来源')
        add(r,r.vehicle_id,'vehicle_transport_found_receipts','transport_found',1,r.value_cents,r.business_date,r.case_id,'原损失找回，不是第二次调拨验收')
    for r in entries:
        if r.inventory_delta:
            kind = 'other_out' if r.inventory_delta < 0 else 'customer_return' if 'customer' in r.kind else 'other_return'
            add(r, r.vehicle_id, 'vehicle_position_entries', kind, r.inventory_delta, r.value_cents, r.business_date, r.case_id)

    # Allocation binds an immutable order event to this exact inventory generation.
    # A position entry is not double counted with its confirming dispatch event.
    events = bounded(db, FlowEvent, select(FlowEvent).where(FlowEvent.action.in_(['allocate', 'dispatch'])))
    allocations = defaultdict(list); dispatches = defaultdict(list)
    for e in events:
        if cases.get(e.case_id) and cases[e.case_id].kind == 'order':
            (allocations if e.action == 'allocate' else dispatches)[e.case_id].append(e)
    sale_entries = defaultdict(list)
    for r in entries:
        if r.kind == 'sale_dispatch': sale_entries[r.case_id].append(r)
    positive = defaultdict(list)
    for f in facts:
        if f['quantity'] > 0: positive[f['vehicle_id']].append(f)
    for case_id in set(dispatches) | set(sale_entries):
        aa, ee, pp = allocations[case_id], dispatches[case_id], sale_entries[case_id]
        key = aa[0].detail.get('vehicle_id') if len(aa) == 1 else None
        keys = {p.vehicle_id for p in pp} | ({key} if key in cars else set())
        if not keys: continue
        if len(aa) != 1 or len(ee) != 1 or len(pp) > 1 or key not in cars or (pp and pp[0].vehicle_id != key):
            for k in keys: issue(k, '销售出库缺少唯一原配车及出库确认来源')
            continue
        event = ee[0]; day = local_date(event.occurred_at)
        if not isinstance(event.detail.get('evidence_id'), int): issue(key, '销售出库缺少原凭据关联')
        if pp:
            p = pp[0]
            add(p, key, 'vehicle_position_entries', 'sale_dispatch', -1, p.value_cents, p.business_date, case_id)
            if day != p.business_date: issue(key, '销售出库日期与实际确认日期不一致')
        elif len(positive[key]) == 1:
            add(event, key, 'flow_events', 'sale_dispatch', -1, -positive[key][0]['value_cents'], day, case_id)
        else:
            issue(key, '销售出库有确认记录但原车辆入库成本来源不足')
    # Read-only legacy sales do not gain an invented physical dispatch date.
    for sale in bounded(db, Sale, select(Sale).where(Sale.vehicle_id.in_(ids), Sale.approval_state == 'approved')):
        issue(sale.vehicle_id, '旧销售记录没有本报表要求的实际出库来源，请单独核对历史资料')

    by_car = defaultdict(list)
    for f in facts: by_car[f['vehicle_id']].append(f)
    # One VIN cannot leave two inventory generations in stock at any day-end.
    # No artificial intraday ordering is inferred from unrelated table IDs.
    vin_dates = defaultdict(lambda: defaultdict(int))
    for f in facts: vin_dates[f['vin']][f['date']] += f['quantity']
    for identity, days in vin_dates.items():
        net = 0
        for _, delta in sorted(days.items()):
            net += delta
            if net > 1:
                for key, car in cars.items():
                    if car.vin == identity: issue(key, '同一 VIN 的不同库存代次出现期末重叠')
    rows = []
    for key, car in cars.items():
        ff = sorted(by_car[key], key=lambda f: (f['date'], -f['quantity'], f['source'], f['source_id']))
        if not ff and car.approval_state in {'draft', 'submitted', 'rejected'} and key not in positions: continue
        ins = [f for f in ff if f['quantity'] == 1]
        outs = [f for f in ff if f['quantity'] == -1]
        if len(ins) != 1: issue(key, '缺少唯一原始入库来源；不按当前批准状态或日期反推期初')
        if len(outs) > 1: issue(key, '同一库存代次存在重复出库来源')
        if len(ins) == 1 and any(-f['value_cents'] != ins[0]['value_cents'] for f in outs): issue(key, '出库原成本与该代次入库来源不守恒')
        by_day = defaultdict(int)
        for f in ff: by_day[f['date']] += f['quantity']
        running = 0
        for day, delta in sorted(by_day.items()):
            running += delta
            if running not in {0, 1}: issue(key, '来源日期或数量次序不能重建单车库存')
        p = positions.get(key)
        expected = (1 if p.status in {'stored', 'transit'} else 0) if p else None
        if expected is None and car.inventory_generation > 0: issue(key, '受控库存代次缺少当前保管位置')
        if expected is not None and running != expected: issue(key, '原流水结存与当前实际保管位置不一致')
        if running == 1 and len(ins) == 1 and car.purchase_cost_cents != ins[0]['value_cents']: issue(key, '当前库存价值与原始入库来源不一致')
        totals = {s: {'quantity': 0, 'value_cents': 0} for s in STAGES}
        for f in ff:
            s = 'opening' if f['date'] < start.isoformat() else ('in' if f['quantity'] > 0 else 'out') if f['date'] <= end.isoformat() else None
            if s:
                totals[s]['quantity'] += f['quantity'] if s == 'opening' else abs(f['quantity'])
                totals[s]['value_cents'] += f['value_cents'] if s == 'opening' else abs(f['value_cents'])
        for unit in ('quantity', 'value_cents'):
            totals['closing'][unit] = totals['opening'][unit]+totals['in'][unit]-totals['out'][unit]
        ok = not issues[key]
        if not ok: totals = {s: {'quantity': None, 'value_cents': None} for s in STAGES}
        rows.append({'vehicle_id': key, 'store_id': car.store_id, 'number': car.doc_no, 'vin': car.vin,
                     'generation': car.inventory_generation, 'model': car.model, 'reconciled': ok,
                     'issues': issues[key], 'quantity_variance': None if expected is None else expected-running,
                     'source_case_id': ins[0]['case_id'] if len(ins) == 1 else None,
                     **totals})
    complete = all(r['reconciled'] for r in rows)
    details = sorted([f for f in facts if start.isoformat() <= f['date'] <= end.isoformat()], key=lambda f: (f['date'], f['store_id'], f['vehicle_id'], -f['quantity']))
    transit = []; transit_complete = True
    for t in transfers.values():
        if t.from_store_id not in scope: continue  # Avoid counting the same vehicle at both parties.
        mm = transfer_facts[t.id]; dispatch = mm.get('dispatch')
        if not dispatch or dispatch.business_date > end: continue
        original_loss=transport_losses.get(t.id)
        if original_loss and original_loss.business_date<=end:continue  # Loss removed original transit; finding never reopens it.
        finish = mm.get('accept') or mm.get('return_receive')
        if finish and finish.business_date <= end: continue
        known = t.to_store_id in scope or bool(finish)
        if not known: transit_complete = False
        transit.append({'store_id': t.from_store_id, 'vin': t.vin, 'source_id': t.id, 'case_id': t.from_case_id,
                        'date': dispatch.business_date.isoformat(), 'kind': 'transfer', 'label': '跨店调拨在途',
                        'quantity': 1 if known else None, 'value_cents': -dispatch.value_cents if known else None,
                        'status': '截至期末未有实际接收或原退' if known else '历史在途确认来源不在本次授权范围', 'verified': known})
    purchase_by_shipment = defaultdict(list)
    for m in purchase_moves: purchase_by_shipment[m.shipment_id].append(m)
    for s in shipments:
        if s.shipped_date > end or any(m.business_date <= end for m in purchase_by_shipment[s.id] if m.kind in {'receive', 'transit_return'}): continue
        transit.append({'store_id': s.store_id, 'vin': s.vin, 'source_id': s.id, 'case_id': s.case_id,
                        'date': s.shipped_date.isoformat(), 'kind': 'supplier', 'label': '供应商已发运未验收',
                        'quantity': 1, 'value_cents': None, 'status': '未计入本店库存与库存价值', 'verified': True})
    tables = {}
    headers = ['门店', '库存编号', 'VIN', '代次', '车型', '期初（台）', '入库（台）', '出库（台）', '期末（台）']
    if can_money: headers += ['期初价值（元）', '入库价值（元）', '出库价值（元）', '期末价值（元）']
    headers += ['来源核对', '差异说明']
    balance = table('整车期间入出存', headers); tables['vehicle_period_balances'] = balance
    for r in rows:
        values = [stores.get(r['store_id'], ''), r['number'], r['vin'], r['generation'], r['model']]+[r[s]['quantity'] if r[s]['quantity'] is not None else '—' for s in STAGES]
        if can_money: values += [yuan(r[s]['value_cents']) for s in STAGES]
        balance['rows'].append({'vehicle_id': r['vehicle_id'], 'values': values+['已核对' if r['reconciled'] else '来源不完整', '；'.join(r['issues'])],
                                'route': route(db, r['source_case_id']) if r['source_case_id'] else None,
                                **{s+'_quantity': r[s]['quantity'] for s in STAGES},
                                **({s+'_cents': r[s]['value_cents'] for s in STAGES} if can_money else {})})
    detail_table = table('整车期间原始入出库明细', ['门店', '日期', 'VIN', '代次', '实际业务', '来源记录', '记录编号', '数量（台）']+(['原成本变动（元）'] if can_money else [])+['店间口径'])
    tables['vehicle_period_movements'] = detail_table
    for f in details:
        detail_table['rows'].append({'values': [stores.get(f['store_id'], ''), f['date'], f['vin'], f['generation'], f['label'], SOURCE_LABELS[f['source']], f['source_id'], f['quantity']]+([yuan(f['value_cents'])] if can_money else [])+[f['internal']],
                                    'quantity': f['quantity'], **({'amount_cents': f['value_cents']} if can_money else {}), 'route': route(db, f['case_id']) if f['case_id'] else None})
    transit_table = table('期末供应商及集团调拨在途', ['发出或采购门店', 'VIN', '来源', '发运日期', '可核对数量（台）']+(['已入账调拨原值（元）'] if can_money else [])+['核对状态'])
    tables['vehicle_period_transit'] = transit_table
    for r in transit:
        transit_table['rows'].append({'values': [stores.get(r['store_id'], ''), r['vin'], r['label'], r['date'], r['quantity'] if r['quantity'] is not None else '—']+([yuan(r['value_cents'])] if can_money else [])+[r['status']], 'route': route(db, r['case_id']), 'quantity': r['quantity']})
    charts = []
    if complete:
        charts.append({'id': 'vehicle_period_balances', 'title': '整车期间库内数量', 'section': 'inventory', 'type': 'bar', 'unit': 'count',
                       'labels': ['期初', '入库', '出库', '期末'], 'series': [{'name': '台', 'values': [sum(r[s]['quantity'] for r in rows) for s in STAGES]}],
                       'table': 'vehicle_period_balances', 'caption': DEFINITION})
    # Role filtering includes every raw fact, total, table metadata and chart.
    if not can_money:
        for r in rows:
            for s in STAGES: r[s].pop('value_cents')
        for f in details: f.pop('value_cents')
        for r in transit: r.pop('value_cents')
    return {'date_from': start.isoformat(), 'date_to': end.isoformat(), 'as_of': as_of(), 'can_money': can_money,
            'scope': {'view': 'vehicle_period_reconstruction', 'rows_unit': '原车辆VIN及库存代次核对行',
                      'rows_are_current_stock': False, 'current_availability_included': False,
                      'closing_quantity_metric': 'metrics.vehicle_period_closing_count',
                      'closing_quantity_date': end.isoformat(),
                      'quantity_note': 'rows包含原车辆及历史代次，不是当前在库清单。期末台数只读closing_quantity_metric；complete为false或该指标为null时数量未知，不能用行数补算。期末截至date_to，不等于当前在库或当前可配。',
                      'current_stock_operation': 'GET /api/vehicle-catalog'},
            'complete': complete, 'transit_complete': transit_complete, 'rows': rows, 'details': details, 'transit': transit,
            'tables': tables, 'charts': charts, 'definition': DEFINITION, 'definitions': [DEFINITION],
            'metrics': {'vehicle_period_complete': complete, 'vehicle_period_unverified_generations': sum(not r['reconciled'] for r in rows),
                        'vehicle_period_closing_count': sum(r['closing']['quantity'] for r in rows) if complete else None,
                        'vehicle_period_transit_complete': transit_complete}}
