"""Read-only period reports and exports from the exact same table population."""
import csv
import io
from datetime import date
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from .db import get_db
from .security import get_user
from .services import audit
from .vehicle_period_analytics import build_vehicle_period
from .procurement_analytics import build_procurement_cohort
from .warehouse_period_analytics import build_warehouse_period

router = APIRouter(prefix='/api/inventory-reports', tags=['整车入出存与物资订货统计'])


@router.get('/warehouses/options/{kind}')
def warehouse_options(kind: str, q: str = Query('', max_length=100), selected_id: int | None = Query(None, gt=0), db=Depends(get_db), user=Depends(get_user)):
    from sqlalchemy import select, or_
    from .inventory_report_common import READ_ROLES
    from .flow_models import Item
    from .master_models import Warehouse
    if user.role not in READ_ROLES: raise HTTPException(403, '当前岗位不能查询库位统计')
    model = {'items':Item, 'warehouses':Warehouse}.get(kind)
    if model is None: raise HTTPException(404, '筛选资料不存在')
    code = model.sku if kind=='items' else model.code
    stmt=select(model).where(or_(model.name.contains(q,autoescape=True),code.contains(q,autoescape=True))).order_by(model.id)
    rows=list(db.scalars(stmt.limit(101)));more=len(rows)>100;rows=rows[:100]
    if selected_id and not any(r.id==selected_id for r in rows):
        row=db.scalar(select(model).where(model.id==selected_id))
        if row:rows.insert(0,row)
    return {'items':[{'id':r.id,'label':(r.sku if kind=='items' else r.code)+' · '+r.name+('（已停用）' if not r.active else '')} for r in rows],'has_more':more}


def build(kind, db, user, start, end, vin, item_id=None, warehouse_id=None):
    if kind == 'warehouses':
        if vin: raise HTTPException(422, '物资库位报表不使用 VIN 筛选')
        return build_warehouse_period(db, user, start, end, item_id, warehouse_id)
    if item_id or warehouse_id: raise HTTPException(422, '物资和仓库筛选仅适用于物资库位报表')
    if kind == 'vehicle-transport':
        if vin:raise HTTPException(422,'原车运输财务报表按原来源明细核对，不使用库存VIN筛选')
        from .vehicle_transport_analytics import build_vehicle_transport
        return build_vehicle_transport(db,user,start,end)
    if kind == 'vehicles': return build_vehicle_period(db, user, start, end, vin)
    if kind == 'procurement':
        if vin: raise HTTPException(422, '物资订货报表不使用 VIN 筛选')
        return build_procurement_cohort(db, user, start, end)
    raise HTTPException(404, '报表不存在')


@router.get('/{kind}')
def report(kind: str, date_from: date | None = None, date_to: date | None = None,
           vin: str | None = Query(None, max_length=17), item_id: int | None = Query(None, gt=0), warehouse_id: int | None = Query(None, gt=0), db=Depends(get_db), user=Depends(get_user)):
    return build(kind, db, user, date_from, date_to, vin, item_id, warehouse_id)


@router.get('/{kind}/export/{table_key}')
def export(kind: str, table_key: str, date_from: date | None = None, date_to: date | None = None,
           vin: str | None = Query(None, max_length=17), item_id: int | None = Query(None, gt=0), warehouse_id: int | None = Query(None, gt=0), db=Depends(get_db), user=Depends(get_user)):
    result = build(kind, db, user, date_from, date_to, vin, item_id, warehouse_id)
    if table_key not in result['tables']: raise HTTPException(404, '当前报表没有此明细表')
    source = result['tables'][table_key]
    buf = io.StringIO(newline=''); writer = csv.writer(buf)
    def safe(value):
        text = str(value)
        numeric = text.replace('-', '', 1).replace('.', '', 1).isdigit()
        return "'"+text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) and not numeric else text
    writer.writerow(source['headers'])
    for row in source['rows']: writer.writerow([safe(v) for v in row['values']])
    audit(db, user.id, 'export', kind+'_inventory_report', None, reason=result['date_from']+'至'+result['date_to']+' '+table_key); db.commit()
    name = 'huakangos_'+source['title']+'_'+result['date_from']+'_'+result['date_to']+'.csv'
    return Response(('\ufeff'+buf.getvalue()).encode(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': "attachment; filename*=UTF-8''"+quote(name)})
