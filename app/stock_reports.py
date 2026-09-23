"""Period stock reconstruction from immutable opening and movement records."""
from collections import defaultdict
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from .db import today
from .flow_models import Item, StockMove
from .master_models import OpeningStockEntry
from .master_data import stockflow
from .models import Store

READ_ROLES={'admin','manager','inventory','finance','auditor'}
LIMIT=25000


def build_stock_period(db,user,start=None,end=None,item_id=None):
    if user.role not in READ_ROLES:raise HTTPException(403,'当前岗位不能查询物资入出存报表')
    end=end or today();start=start or end.replace(day=1)
    if start>end or end>today() or (end-start).days>365:
        raise HTTPException(422,'请选择不晚于今天、跨度不超过一年的期间')
    query=select(Item.id,Item.version,Item.store_id,Item.name,Item.unit)
    if item_id:query=query.where(Item.id==item_id)
    selected=list(db.execute(query.limit(501)))
    if len(selected)>500:raise HTTPException(422,'请按物资查询，一次最多重建500项物资')
    if item_id and not selected:raise HTTPException(404,'当前门店物资不存在')
    ids=[r.id for r in selected]
    size=sum(db.scalar(select(func.count()).select_from(model).where(model.item_id.in_(ids))) or 0
             for model in (StockMove,OpeningStockEntry))
    if size>LIMIT:raise HTTPException(422,'相关库存来源超过本版重建上限，未返回截断报表')
    ledger=stockflow(db,user,item_id)
    before={r.id:r.version for r in selected}
    after=dict(db.execute(select(Item.id,Item.version).where(Item.id.in_(ids))).all())
    if before!=after or set(before)!={row['item_id'] for row in ledger['totals']}:
        raise HTTPException(409,'查询期间库存发生变化，请刷新后重新核对')
    metadata={r.id:r for r in selected};facts=defaultdict(list)
    stores=dict(db.execute(select(Store.id,Store.name)).all())
    for fact in ledger['rows']:facts[fact['item_id']].append(fact)
    can_money=ledger['can_money'];rows=[];details=[]
    for current in ledger['totals']:
        key=current['item_id'];meta=metadata[key]
        chronology_ok=all(f['running_quantity_milli']>=0 and (not can_money or f['running_value_cents']>=0) for f in facts[key])
        reconciled=current['reconciled'] and chronology_ok
        result={'item_id':key,'store_id':meta.store_id,'sku':current['sku'],'name':meta.name,'unit':meta.unit,
                'reconciled':reconciled,'status':'来源与当前库存一致' if reconciled else '来源不足或差异待核对' if chronology_ok else '来源日期先后关系待核对',
                'quantity_variance_milli':current['current_quantity_milli']-current['quantity_milli']}
        measures={'quantity_milli':0}
        if can_money:
            measures['value_cents']=0
            result['value_variance_cents']=current['current_value_cents']-current['value_cents']
        totals={stage:dict(measures) for stage in ('opening','in','out','closing')}
        for fact in facts[key]:
            occurred=fact['date']
            if occurred<start.isoformat():
                for unit in measures:totals['opening'][unit]+=fact[unit]
            elif occurred<=end.isoformat():
                for unit in measures:
                    amount=fact[unit];totals['in' if amount>=0 else 'out'][unit]+=abs(amount)
                details.append({**fact,'unit':meta.unit,'store_id':meta.store_id})
        for unit in measures:
            totals['closing'][unit]=totals['opening'][unit]+totals['in'][unit]-totals['out'][unit]
        # Missing starting facts are not reconstructed by subtracting from today.
        for stage,values in totals.items():
            result[stage]={unit:amount if result['reconciled'] else None for unit,amount in values.items()}
        rows.append(result)
    complete=all(r['reconciled'] for r in rows)
    chart=None
    if can_money and complete:
        chart={'title':'期间物资账面价值','type':'bar','unit':'cents',
               'labels':['期初','入库','出库','期末'],
               'series':[{'name':'账面价值','values':[sum(r[s]['value_cents'] for r in rows) for s in ('opening','in','out','closing')]}]}
    headers=['门店','物资编码','名称','单位','期初数量','期间入库数量','期间出库数量','期末数量']
    if can_money:headers+=['期初价值（元）','入库价值（元）','出库价值（元）','期末价值（元）']
    headers+=['来源核对','数量差异']+(['价值差异（元）'] if can_money else [])
    def number(value,scale):return '—' if value is None else format(Decimal(value)/scale,'f')
    display=[]
    for row in rows:
        values=[stores.get(row['store_id'],''),row['sku'],row['name'],row['unit']]+[number(row[s]['quantity_milli'],1000) for s in ('opening','in','out','closing')]
        if can_money:values += [number(row[s]['value_cents'],100) for s in ('opening','in','out','closing')]
        values += [row['status'],number(row['quantity_variance_milli'],1000)]
        if can_money:values += [number(row['value_variance_cents'],100)]
        display.append({'item_id':row['item_id'],'values':values})
    return {'date_from':start.isoformat(),'date_to':end.isoformat(),'can_money':can_money,'complete':complete,
            'rows':rows,'details':details,'table':{'headers':headers,'rows':display},'chart':chart,
            'definition':'期初为开始日前全部有据期初及库存流水；期间包含首末日。来源与当前库存不一致时不出期末数或价值合计。期初入账不等于采购，库存出库不等于营业成本；不同单位数量不合计。'}
