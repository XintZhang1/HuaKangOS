"""Quote approval activity and current excess liabilities, never a second revenue ledger."""
from collections import defaultdict
from fastapi import HTTPException
from sqlalchemy import select
from .flow_models import Case,PaymentLink
from .business_finance_models import FinanceCreditLink
from .aftercare_models import AftercareClaim
from .sales_quote_models import SalesQuote,SalesQuoteReview,SalesQuoteResolution,SalesQuoteAdjustment

def _bounded(db,statement):
    rows=list(db.scalars(statement.limit(25001)))
    if len(rows)>25000:raise HTTPException(409,'报价统计来源超过安全上限，请缩小门店范围后查询')
    return rows

def analytics_rows(db,user):
    if user.role not in {'admin','manager','finance','auditor'}:raise HTTPException(403,'报价汇总须有当前范围经营或财务查看权限')
    cases={r.id:r for r in _bounded(db,select(Case).where(Case.kind=='order',Case.flow_version.in_([3,4])))};ids=list(cases)
    quotes=_bounded(db,select(SalesQuote).where(SalesQuote.case_id.in_(ids)))
    byquote={q.id:q for q in quotes};reviews={r.quote_id:r for r in _bounded(db,select(SalesQuoteReview).where(SalesQuoteReview.quote_id.in_(byquote)))}
    resolutions={r.quote_id:r for r in _bounded(db,select(SalesQuoteResolution).where(SalesQuoteResolution.quote_id.in_(byquote)))}
    paid=defaultdict(int)
    for p in _bounded(db,select(PaymentLink).where(PaymentLink.case_id.in_(ids))):paid[p.case_id]+=p.amount_cents*(1 if p.direction=='in' else -1)
    for p in _bounded(db,select(FinanceCreditLink).where(FinanceCreditLink.case_id.in_(ids))):paid[p.case_id]+=p.amount_cents
    claimed={r.source_case_id for r in _bounded(db,select(AftercareClaim).where(AftercareClaim.source_case_id.in_(ids)))}
    versions=[];changes=[];excess=[]
    for q in quotes:
        row=cases[q.case_id];review=reviews.get(q.id);result=resolutions.get(q.id)
        value={'id':q.id,'case_id':row.id,'number':row.number,'store_id':row.store_id,'revision':q.revision,
            'model_id':q.model_id,'model_name':q.model_snapshot['name'],'model_code':q.model_snapshot['code'],'amount_cents':q.amount_cents,
            'occurred_at':q.occurred_at.isoformat()+'Z','status':result.outcome if result else review.decision if review else 'pending'}
        versions.append(value)
        if result and result.outcome=='activated' and q.prior_id:
            prior=byquote.get(q.prior_id)
            if not prior or prior.case_id!=q.case_id:raise HTTPException(409,'报价变更统计缺少同店原生效版本')
            changes.append({**value,'occurred_at':result.occurred_at.isoformat()+'Z','prior_quote_id':prior.id,'prior_amount_cents':prior.amount_cents,'amount_cents':q.amount_cents-prior.amount_cents})
        if row.data.get('active_quote_id')==q.id and row.state=='executing' and row.id not in claimed and not row.data.get('pending_quote_id') and paid[row.id]>row.amount_cents:
            excess.append({**value,'amount_cents':paid[row.id]-row.amount_cents,'paid_cents':paid[row.id],'quote_cents':row.amount_cents})
    adjustments=[]
    for a in _bounded(db,select(SalesQuoteAdjustment).where(SalesQuoteAdjustment.quote_id.in_(byquote))):
        q=byquote[a.quote_id];row=cases[q.case_id]
        adjustments.append({'id':a.id,'case_id':row.id,'number':row.number,'store_id':row.store_id,'quote_id':q.id,'revision':q.revision,
            'kind':a.kind,'amount_cents':a.amount_cents,'payment_id':a.payment_id,'credit_id':a.credit_id,'occurred_at':a.occurred_at.isoformat()+'Z'})
    return {'versions':versions,'changes':changes,'excess':excess,'adjustments':adjustments}
