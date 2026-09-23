"""Dedicated commercial ledgers contribute explicit period and current datasets."""
from collections import Counter
from datetime import date
from .flow_models import StockMove
from .retail_models import RetailDispatch,RetailReturnPosting
from .retail_service import totals as retail_totals
from .vehicle_procurement_models import (VehiclePurchaseOrder,VehiclePurchasePrice,VehiclePurchaseShipment,
    VehiclePurchaseMovement)
from .vehicle_procurement_service import totals as vehicle_totals


def build_commercial(db,user,start,end,cases,stores,bounded,yuan):
    tables={};charts=[];metrics={};byid={r.id:r for r in cases}
    def table(key,title,headers):
        tables[key]={'title':title,'headers':headers,'rows':[]};return tables[key]['rows']
    def add(rows,values,case_id,amount=None):
        rows.append({'values':values,'route':{'type':'case','id':case_id},'amount_cents':amount})
    def bars(key,title,rows,totals,section,caption):
        keys=sorted(totals)
        charts.append({'id':key,'title':title,'type':'bar','unit':'cents','table':key,'section':section,'caption':caption,
                       'labels':[stores.get(k,'') for k in keys],'series':[{'name':'金额','values':[totals[k] for k in keys]}]})
    current=table('retail_orders','精品当前结算与预收',['单号','门店','客户','调整后约定（元）','已结算抵扣（元）','待收（元）','待退（元）','交付状态'])
    revenue=table('retail_settlements','期间精品履约与退货冲减',['单号','门店','客户','日期','事实','对外结算（元）','商品成本（元）'])
    moves={m.id:m for m in bounded(db,StockMove)};returns=bounded(db,RetailReturnPosting);dispatches=bounded(db,RetailDispatch)
    from .retail_group_reporting import report_data
    mixed=report_data(db,user,[r.id for r in cases if r.kind=='retail'])
    totals=Counter();net_revenue=net_cost=0
    for row in cases:
        if row.kind!='retail' or row.flow_version!=2:continue
        value=retail_totals(db,row)
        accepted=date.fromisoformat(row.data['accepted_date']) if row.data.get('accepted_date') else None
        customer=row.title.split(' · ')[0]
        add(current,[row.number,stores.get(row.store_id,''),customer,yuan(value['charge_cents']),yuan(value['net_paid_cents']),
            yuan(value['receivable_cents']),yuan(value['refund_due_cents']),'已交付' if accepted else '未确认客户接收'],row.id,value['receivable_cents'])
        if not accepted:continue
        postings=[p for p in returns if p.case_id==row.id]
        before=[p for p in postings if moves[p.stock_move_id].business_date<=accepted]
        recognized=row.amount_cents-sum(p.goods_cents+p.installation_cents-p.retained_cents for p in before)
        cost=sum(p.value_cents for p in dispatches if p.case_id==row.id)-sum(p.value_cents for p in before)
        facts=[(accepted,'客户接收',recognized,cost)]
        facts += [(moves[p.stock_move_id].business_date,'原单退货冲减',-(p.goods_cents+p.installation_cents-p.retained_cents),-p.value_cents)
                  for p in postings if moves[p.stock_move_id].business_date>accepted]
        facts += [(date.fromisoformat(f['business_date']),f['label'],f['amount_cents'],0)
            for f in mixed['discounts'] if f['case_id']==row.id]
        for occurred,kind,amount,cost in facts:
            if start<=occurred<=end:
                add(revenue,[row.number,stores.get(row.store_id,''),customer,occurred.isoformat(),kind,yuan(amount),yuan(cost)],row.id,amount)
                totals[row.store_id]+=amount;net_revenue+=amount;net_cost+=cost
    bars('retail_settlements','期间精品履约净额',revenue,totals,'materials','接收前退货先减约定额；接收后退货按实际退回日冲减当期。集团原核销优惠及原退按本次原来源日期单列；原权益恢复不二次冲减。现金预收不计履约。')
    metrics.update(retail_revenue_cents=net_revenue,retail_goods_cost_cents=net_cost)
    purchase=table('vehicle_procurement','当前整车采购与供应商账',['采购号','门店','供应商','采购承诺（元）','验收净值（元）','净付（元）','预付（元）','应付（元）','供应商应退（元）'])
    transit=table('vehicle_procurement_transit','当前供应商发运在途整车',['采购号','门店','供应商','VIN','预计到货','采购成本（元）'])
    movements=table('vehicle_procurement_movements','期间整车采购实物记录',['采购号','门店','日期','事实','数量','账面价值变化（元）'])
    orders={r.id:r for r in bounded(db,VehiclePurchaseOrder)}
    prices={p.line_id:p for p in bounded(db,VehiclePurchasePrice)}
    shipments=bounded(db,VehiclePurchaseShipment);vtotals=Counter();payable=prepaid=refund=0
    for key,order in orders.items():
        row=byid.get(key)
        if not row:continue
        value=vehicle_totals(db,row)
        add(purchase,[row.number,stores.get(row.store_id,''),order.supplier_name,yuan(value['commitment_cents']),
            yuan(value['received_cents']-value['returned_cents']),yuan(value['paid_net_cents']),yuan(value['prepaid_cents']),
            yuan(value['payable_cents']),yuan(value['supplier_refund_due_cents'])],key,value['payable_cents'])
        payable+=value['payable_cents'];prepaid+=value['prepaid_cents'];refund+=value['supplier_refund_due_cents']
        for shipment in shipments:
            if shipment.case_id!=key or shipment.status!='transit':continue
            amount=prices[shipment.line_id].unit_cost_cents;vtotals[row.store_id]+=amount
            add(transit,[row.number,stores.get(row.store_id,''),order.supplier_name,shipment.vin,shipment.expected_date.isoformat(),yuan(amount)],key,amount)
    for move in bounded(db,VehiclePurchaseMovement):
        if start<=move.business_date<=end and move.case_id in byid:
            row=byid[move.case_id]
            add(movements,[row.number,stores.get(move.store_id,''),move.business_date.isoformat(),
                {'receive':'实际验收入库','return':'原入库退回供应商','transit_return':'未入库拒收退回'}.get(move.kind,move.kind),move.quantity,yuan(move.value_cents)],row.id,move.value_cents)
    bars('vehicle_procurement_transit','供应商发运在途成本',transit,vtotals,'inventory','按供应商实际发运记录、冻结采购单价统计；未到货不计可售库存，未验收退回为零库存变化。')
    metrics.update(vehicle_procurement_payable_cents=payable,vehicle_procurement_prepaid_cents=prepaid,
        vehicle_procurement_refund_due_cents=refund,vehicle_procurement_in_transit_cents=sum(vtotals.values()))
    return {'tables':tables,'charts':charts,'metrics':metrics}
