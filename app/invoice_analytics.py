from collections import defaultdict
from sqlalchemy import select
from fastapi import HTTPException
from .invoice_models import InvoiceApplication,InvoiceResult
from .flow_models import Case
from .invoice_service import source_amount,KINDS

def build_invoice_analytics(db,user,start,end,stores,yuan):
    from .flow_analytics import bounded
    aggregate=bool(getattr(user,'_aggregate_scope',False) or len([sid for sid in db.info.get('store_scope',()) if sid])>1)
    cases={r.id:r for r in bounded(db,Case)}
    applications={r.id:r for r in bounded(db,InvoiceApplication)}
    all_results=bounded(db,InvoiceResult)
    results=list(db.scalars(select(InvoiceResult).where(InvoiceResult.issued_on>=start,InvoiceResult.issued_on<=end).limit(25001)))
    if len(results)>25000:raise HTTPException(422,'实际票据超过本版统计上限，未返回截断结果')
    rows=[];bydate=defaultdict(int);blue=red=0
    for actual in results:
        application=applications[actual.case_id];case=cases[actual.case_id];amount=actual.amount_cents*(1 if application.direction=='blue' else -1)
        if application.direction=='blue':blue+=actual.amount_cents
        else:red+=actual.amount_cents
        bydate[actual.issued_on.isoformat()]+=amount
        hidden=aggregate and cases[application.source_case_id].kind=='vehicle_income'
        rows.append({'values':['门店汇总来源' if hidden else case.number,stores.get(case.store_id,''),'往来单位汇总' if hidden else cases[application.source_case_id].number,actual.issued_on.isoformat(),
            '蓝票' if amount>0 else '红票','汇总票据' if hidden else actual.invoice_number,yuan(amount)],'route':None if hidden else {'type':'case','id':case.id},'amount_cents':amount})
    corrections=[]
    actual_totals=defaultdict(int)
    for result in all_results:
        app=applications[result.case_id]
        actual_totals[app.source_case_id]+=result.amount_cents*(1 if app.direction=='blue' else -1)
    for old in cases.values():
        if old.kind=='invoice' and old.flow_version in {1,2} and old.state=='completed':actual_totals[old.parent_id]+=old.amount_cents
    for key,actual in actual_totals.items():
        case=cases.get(key)
        if not case or case.kind not in KINDS:raise HTTPException(409,'实际票据的原业务依据缺失，不能生成核对报表')
        allowed=source_amount(db,case);correction=max(0,actual-allowed)
        hidden=aggregate and case.kind=='vehicle_income'
        if correction:corrections.append({'values':['门店汇总来源' if hidden else case.number,stores.get(case.store_id,''),yuan(allowed),yuan(actual),yuan(correction)],
            'route':None if hidden else {'type':'case','id':case.id},'amount_cents':correction})
    tables={'invoices':{'title':'期间专用发票协同实际结果','headers':['申请单','门店','原业务','实际日期','类型','票号','净金额（元）'],'rows':rows},
        'invoice_corrections':{'title':'当前原业务发票差额','headers':['原业务','门店','当前业务上限（元）','实际蓝减红（元）','待冲红核对（元）'],'rows':corrections}}
    dates=sorted(bydate)
    charts=[{'id':'invoices','title':'期间实际蓝票减红票','section':'finance','type':'bar','unit':'cents','labels':dates,
        'series':[{'name':'票据净额','values':[bydate[d] for d in dates]}],'table':'invoices','caption':'按实际票面日期；仅新专用协同结果。票据金额不是收入或到账，旧登记仍参与原单额度核对。'}]
    return {'tables':tables,'charts':charts,'metrics':{'invoice_blue_cents':blue,'invoice_red_cents':red,'invoice_net_cents':blue-red,'invoice_correction_cents':sum(r['amount_cents'] for r in corrections)}}
