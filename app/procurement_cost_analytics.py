"""Original supplier credits and inventory cost variances use actual dispatch dates."""
from collections import defaultdict
from decimal import Decimal
from .procurement_cost_models import PurchaseReturnValuation
from .procurement_models import PurchaseReturnPosting,PurchaseReceipt,PurchaseLine
from .flow_models import StockMove,Case


def build(db,user,cases,stores,bounded,yuan,in_period):
    bycase={c.id:c for c in cases if c.kind=='procurement'}
    posts={p.id:p for p in bounded(db,PurchaseReturnPosting)};receipts={r.id:r for r in bounded(db,PurchaseReceipt)}
    lines={l.id:l for l in bounded(db,PurchaseLine)};moves={m.id:m for m in bounded(db,StockMove)}
    rows=[];totals=defaultdict(int);credit=0;cost=0
    for value in bounded(db,PurchaseReturnValuation):
        p=posts[value.id];move=moves[p.stock_move_id];case=bycase.get(p.case_id)
        if not case or not in_period(move.business_date):continue
        line=lines[receipts[p.receipt_id].line_id];name=stores.get(p.store_id,'');totals[name]+=value.variance_cents
        credit+=value.supplier_credit_cents;cost+=value.inventory_cost_cents
        rows.append({'values':[case.number,name,move.business_date.isoformat(),p.receipt_id,line.sku,line.item_name,
            format(Decimal(p.quantity_milli)/1000,'f'),line.unit,yuan(value.supplier_credit_cents),yuan(value.inventory_cost_cents),yuan(value.variance_cents)],
            'route':{'type':'case','id':case.id},'amount_cents':value.variance_cents,'quantity_milli':p.quantity_milli,
            'supplier_credit_cents':value.supplier_credit_cents,'inventory_cost_cents':value.inventory_cost_cents,'stock_move_id':move.id,'source_id':value.id})
    labels=sorted(totals)
    return {'tables':{'procurement_return_costs':{'title':'期间采购原单冲款与实际退货成本','headers':['原单','门店','实物发出日','原验收批次','物资编码','物资','数量','单位','供应商原冲款（元）','实际库存扣减（元）','差额（元）'],'rows':rows}},
        'charts':[{'id':'procurement_return_cost_variance','title':'期间采购原退货成本差额','section':'finance','type':'bar','unit':'cents','labels':labels,'series':[{'name':'原冲款减库存成本','values':[totals[k] for k in labels]}],'table':'procurement_return_costs','caption':'按实际退货日：供应商按原采购批次冲款，库存按发出时均价扣减；差额独立留账，不直接当成现金或营业收入。旧v2维持原批次成本，无重算。'}],
        'metrics':{'purchase_return_supplier_credit_cents':credit,'purchase_return_inventory_cost_cents':cost,'purchase_return_cost_variance_cents':credit-cost}}
