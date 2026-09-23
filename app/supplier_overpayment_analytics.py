"""Current supplier overpayments are liabilities, never negative customer receivables."""
from collections import defaultdict
from fastapi import HTTPException
from .business_finance_models import FinanceReturnReceivable,FinanceSupplierRefund
from .business_finance_return_adjustments import effective_target
from .flow_models import PaymentLink


def build_supplier_overpayments(db,user,cases,stores,bounded,yuan):
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([s for s in db.info.get('store_scope',()) if s])>1)
    byid={r.id:r for r in cases};paid=defaultdict(int);reserved=defaultdict(int)
    for p in bounded(db,PaymentLink):paid[p.case_id]+=p.amount_cents*(1 if p.direction=='in' else -1)
    for r in bounded(db,FinanceSupplierRefund):
        if r.status=='reserved':reserved[r.receivable_id]+=r.amount_cents
    rows=[];totals=defaultdict(int)
    for r in bounded(db,FinanceReturnReceivable):
        target=effective_target(db,r);net=paid[r.case_id];over=max(0,net-target);hold=reserved[r.id]
        if hold>over:raise HTTPException(409,'供应方超收应退与批准占额不一致，请核对原单，未返回不完整统计')
        if not over:continue
        source=byid.get(r.case_id)
        if not source:raise HTTPException(409,'供应方超收应退缺少本店原单，未返回截断统计')
        rows.append({'values':['门店汇总来源' if aggregate else source.number,stores.get(r.store_id,''),'原退货供应方',
                              yuan(target),yuan(net),yuan(over),yuan(hold),yuan(over-hold)],
                     'route':None if aggregate else {'type':'case','id':r.case_id},'amount_cents':over,'reserved_cents':hold})
        totals[stores.get(r.store_id,'')]+=over
    name='finance_supplier_overpayments';labels=sorted(totals)
    return {'tables':{name:{'title':'当前供应方超收应退','headers':['原应收办理单','门店','退款对象','当前批准目标（元）','实际净收（元）','超收应退（元）','批准待退占额（元）','尚可申请原退（元）'],'rows':rows}},
            'charts':[{'id':name,'title':'当前供应方超收应退','section':'finance','type':'bar','unit':'cents','labels':labels,
                       'series':[{'name':'应退金额','values':[totals[k] for k in labels]}],'table':name,
                       'caption':'原已收现金仍保留，目标调减形成应退负债；只在财务确认真实原路退款后减少净收。申请与批准不产生现金，不冲减其他客户应收。'}],
            'metrics':{'business_finance_supplier_overpayment_cents':sum(r['amount_cents'] for r in rows)}}
