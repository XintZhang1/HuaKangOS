"""Source-backed transport loss charts; period facts and current claims separate."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from .models import Store
from .transfer_exception_analytics import analytics_rows
from .reconciliation_service import settlement_rows


DEFINITIONS=[
    '运输损失按批准后实际核销日期、原发出批次数量及成本统计；在调出方记录一次资产减少，不伪造验收入库或现金。',
    '门店承担按冻结责任分配统计，两店承担之和等于原损失。承担与原库存成本是两种观察口径，不能重复相加。',
    '追偿确认是经独立批准的目标增减；实际到账及原款退款另列，并且只引用原现金。追偿不算商品销售收入。',
    '追偿余额和损失店间往来为查询时点数据。实际双方清算后才抵销往来；集团汇总不增加第二笔对外收入。',
    '找到原物资后的合格入库按实际恢复日和原批次成本记录；原运输损失不改写、旧在途不重开。期间净损失变化为本期原损失减本期实际恢复，跨期恢复可显示负值。',
    '找回承担冲回为本店成本负向变化，两店合计等于原资产恢复；反向往来独立清算，保留原清算现金。找回暂管或再次实际退运只是当前物理事实，尚不是可用库存。']


def build_transfer_losses(db,user,start,end,source_data=None):
    data=source_data if source_data is not None else analytics_rows(db,user);stores={r.id:r.name for r in db.scalars(select(Store))}
    from .transfer_goods_recovery_analytics import analytics_rows as found_rows
    found=found_rows(db,user)
    tables={};charts=[];metrics={}
    yuan=lambda value:format(Decimal(value)/100,'.2f')
    in_period=lambda r:start<=date.fromisoformat(r['business_date'])<=end
    aggregate=bool(db.info.get('aggregate_scope') or getattr(user,'_aggregate_scope',False) or len(db.info.get('store_scope',()))>1)
    def table(key,title,headers):
        t=dict(id=key,title=title,headers=headers,rows=[]);tables[key]=t;return t
    def put(t,row,values,**facts):
        t['rows'].append(dict(values=values,store_id=row['store_id'],exception_id=row['exception_id'],
            source_id=row['id'],route=None if aggregate or not row.get('case_id') else {'type':'case','id':row['case_id']},**facts))
    def bars(t,fields,caption,section='materials',unit='cents'):
        totals={field:defaultdict(int) for field,label in fields}
        for r in t['rows']:
            for field,label in fields:totals[field][r['store_id']]+=r[field]
        ids=sorted({r['store_id'] for r in t['rows']})
        charts.append(dict(id=t['id'],title=t['title'],type='bar',section=section,unit=unit,table=t['id'],
            labels=[stores.get(sid,'') for sid in ids],series=[dict(name=label,values=[totals[field][sid] for sid in ids]) for field,label in fields],caption=caption))
    loss=table('transport_loss_cost','期间物资运输损失原成本',['门店','调拨号','原差异','核销日期','物资','数量','单位','原成本（元）'])
    for r in filter(in_period,data['losses']):
        put(loss,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['business_date'],r['name'],
            format(Decimal(r['quantity_milli'])/1000,'f'),r['unit'],yuan(r['amount_cents'])],
            amount_cents=r['amount_cents'],quantity_milli=r['quantity_milli'],business_date=r['business_date'])
    bars(loss,[('amount_cents','原损失成本')],DEFINITIONS[0])
    burden=table('transport_loss_burden','期间各店运输损失承担',['门店','调拨号','原差异','核销日期','物资','本店承担（元）'])
    for r in filter(in_period,data['burdens']):put(burden,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['business_date'],r['name'],yuan(r['amount_cents'])],amount_cents=r['amount_cents'],business_date=r['business_date'])
    bars(burden,[('amount_cents','本店承担')],DEFINITIONS[1])
    restored=table('transport_found_cost','期间找到原物资的实际恢复',['门店','调拨号','原差异','恢复日期','物资','本次找到数量','合格入库数量','单位','原成本恢复（元）'])
    for r in filter(in_period,found['restored']):
        put(restored,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['business_date'],r['name'],
            format(Decimal(r['found_quantity_milli'])/1000,'f'),format(Decimal(r['quantity_milli'])/1000,'f'),r['unit'],yuan(r['amount_cents'])],
            amount_cents=r['amount_cents'],quantity_milli=r['quantity_milli'],found_quantity_milli=r['found_quantity_milli'],business_date=r['business_date'],recovery_id=r['recovery_id'])
    bars(restored,[('amount_cents','实际恢复原成本')],DEFINITIONS[4])
    reversals=table('transport_found_burden','期间找回原物资的承担冲回',['门店','调拨号','原差异','恢复日期','物资','本店承担冲回（元；负为减少）'])
    for r in filter(in_period,found['burden_reversals']):put(reversals,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['business_date'],r['name'],yuan(r['amount_cents'])],amount_cents=r['amount_cents'],business_date=r['business_date'],recovery_id=r['recovery_id'])
    bars(reversals,[('amount_cents','本店承担负向变化')],DEFINITIONS[5])
    changes=table('transport_asset_changes','期间运输损失与原资产恢复净变化',['门店','调拨号','原差异','实际日期','原事实','物资','损失净增减（元）'])
    for name,entries,sign in [('原运输损失',data['losses'],1),('原物资实际恢复',found['restored'],-1)]:
        for r in filter(in_period,entries):
            put(changes,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['business_date'],name,r['name'],yuan(sign*r['amount_cents'])],amount_cents=sign*r['amount_cents'],business_date=r['business_date'],fact_kind='loss' if sign==1 else 'found')
    bars(changes,[('amount_cents','原资产损失净增减')],DEFINITIONS[4])
    pending=table('transport_found_custody','当前找回原物资暂管与实际退运',['归属门店','调拨号','原差异','物资','实物数量','单位','当前实际状态','下次核对日期'])
    for r in found['pending']:
        put(pending,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['name'],format(Decimal(r['quantity_milli'])/1000,'f'),r['unit'],
            '实际退运，尚未收到' if r['in_transit'] else '本店暂管，未恢复可用库存',r['due_date']],count=1,quantity_milli=r['quantity_milli'],in_transit=r['in_transit'],recovery_id=r['recovery_id'])
    bars(pending,[('count','当前未处理份数')],'按可辨认找回份数统计；各物资实际数量和单位逐条列出，不跨SKU合计数量。'+DEFINITIONS[5],unit='count')
    confirmation=table('transport_recovery_confirmed','期间追偿目标确认增减',['门店','调拨号','原差异','追偿条目','确认日期','往来方','目标增减（元）'])
    for r in filter(in_period,data['recovery_confirmations']):put(confirmation,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['claim_id'],r['business_date'],r['counterparty'],yuan(r['amount_cents'])],amount_cents=r['amount_cents'],business_date=r['business_date'])
    bars(confirmation,[('amount_cents','确认增减')],DEFINITIONS[2],'finance')
    cash=table('transport_recovery_cash','期间追偿实际收退关联',['门店','调拨号','原差异','追偿条目','实际日期','往来方','原现金','实际收退净额（元）'])
    for r in filter(in_period,data['recovery_cash']):put(cash,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['claim_id'],r['business_date'],r['counterparty'],r['cash_id'],yuan(r['amount_cents'])],amount_cents=r['amount_cents'],cash_id=r['cash_id'],business_date=r['business_date'])
    bars(cash,[('amount_cents','实际收退净额')],'只引用实际现金来源；不得与总现金再次相加。','finance')
    balances=table('transport_recovery_balances','当前追偿应收及原款待退',['门店','调拨号','原差异','追偿条目','往来方','已确认目标（元）','累计实收净额（元）','尚待收取（元）','原款待退（元）','已占原承担额度（元）'])
    for r in data['recovery_balances']:put(balances,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['claim_id'],r['counterparty']]+[yuan(r[f]) for f in ('target_cents','paid_cents','due_cents','refund_cents','occupied_cents')],**{f:r[f] for f in ('target_cents','paid_cents','due_cents','refund_cents','occupied_cents')})
    bars(balances,[('due_cents','尚待收取'),('refund_cents','原款待退')],DEFINITIONS[3],'finance')
    offsets=defaultdict(int);found_offsets=defaultdict(int)
    for r in settlement_rows(db,user)['settlements']:
        if r['origin_kind']=='material_loss':offsets[r['store_id'],r['origin_id']]+=r['amount_cents']
        if r['origin_kind']=='material_found':found_offsets[r['store_id'],r['origin_id']]+=r['amount_cents']
    clearing=table('transport_loss_clearing','当前运输损失店间往来',['门店','对方店','调拨号','原差异','原承担往来（元）','双方实结核销（元）','尚未结清（元）'])
    for r in data['clearing']:
        offset=offsets[r['store_id'],r['id']];net=r['amount_cents']+offset
        put(clearing,r,[stores.get(r['store_id'],''),stores.get(r['counterparty_store_id'],''),r['number'],r['exception_id'],yuan(r['amount_cents']),yuan(offset),yuan(net)],amount_cents=net,original_cents=r['amount_cents'],offset_cents=offset)
    bars(clearing,[('amount_cents','净应收；负为应付')],DEFINITIONS[3],'finance')
    found_clearing=table('transport_found_clearing','当前原物资找回反向往来',['门店','对方店','调拨号','原差异','承担反向往来（元）','双方实际结清（元）','尚未结清（元）'])
    for r in found['clearing']:
        offset=found_offsets[r['store_id'],r['id']];net=r['amount_cents']+offset
        put(found_clearing,r,[stores.get(r['store_id'],''),stores.get(r['counterparty_store_id'],''),r['number'],r['exception_id'],yuan(r['amount_cents']),yuan(offset),yuan(net)],amount_cents=net,original_cents=r['amount_cents'],offset_cents=offset,recovery_id=r['recovery_id'])
    bars(found_clearing,[('amount_cents','反向净应收；负为应付')],DEFINITIONS[5],'finance')
    for key,t in [('transport_loss_cost_cents',loss),('transport_loss_burden_cents',burden),('transport_recovery_confirmed_cents',confirmation),('transport_recovery_cash_net_cents',cash),('transport_loss_internal_net_cents',clearing)]:metrics[key]=sum(r['amount_cents'] for r in t['rows'])
    for field in ('due_cents','refund_cents','occupied_cents'):metrics['transport_recovery_'+field]=sum(r[field] for r in balances['rows'])
    for key,t in [('transport_found_cost_cents',restored),('transport_found_burden_cents',reversals),('transport_asset_change_cents',changes),('transport_found_internal_net_cents',found_clearing)]:metrics[key]=sum(r['amount_cents'] for r in t['rows'])
    searches=table('transport_found_searches','当前原退运查找及再次找到关联',['实际退运门店','调拨号','原差异','物资','原退运数量','再次找到关联量','该次仍未找到量','单位','当前查找结果'])
    from .transfer_goods_search_service import OUTCOMES
    for r in found['searches']:
        put(searches,r,[stores.get(r['store_id'],''),r['number'],r['exception_id'],r['name'],
            *[format(Decimal(r[field])/1000,'f') for field in ('quantity_milli','reappeared_quantity_milli','unlocated_remaining_milli')],
            r['unit'],OUTCOMES[r['status']]],count=1,unlocated_count=int(r['unlocated_remaining_milli']>0),
            review_count=int(r['status']=='review'),search_id=r['search_id'],recovery_id=r['recovery_id'],
            quantity_milli=r['quantity_milli'],reappeared_quantity_milli=r['reappeared_quantity_milli'],
            unlocated_remaining_milli=r['unlocated_remaining_milli'],status=r['status'])
    bars(searches,[('review_count','双方查找复核中'),('unlocated_count','本次尚有未找到量')],
        '生成时点；每次实际退运仅归属其发运门店一次。按原查找逐份保留数量，不跨SKU加总；再次找到关联量不代表已恢复库存。结束查找不增加第二笔损失、现金或应收。',unit='count')
    metrics['transport_found_search_review_count']=sum(r['review_count'] for r in searches['rows'])
    metrics['transport_found_unlocated_count']=sum(r['unlocated_count'] for r in searches['rows'])
    metrics['transport_found_pending_count']=len(pending['rows'])
    return dict(tables=tables,charts=charts,metrics=metrics,definitions=DEFINITIONS)
