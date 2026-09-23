"""Original advance returns authorized by a signed, independently approved quote."""
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .business_finance_models import FinanceAdvance,FinanceAdvanceEntry,FinanceCreditLink
from .business_finance_sources import case_credit_amount,_credit_remaining
from .sales_quote_models import SalesQuoteResolution,SalesQuoteReview,SalesQuoteAdjustment
from . import flow_engine as flow

def restore_excess_advance(db,user,row,quote,evidence_id):
    if row.kind!='order' or row.flow_version not in {3,4} or row.data.get('active_quote_id')!=quote.id or row.data.get('pending_quote_id'):
        raise HTTPException(409,'预收回退须由本次有效车辆报价激活触发')
    review=db.scalar(select(SalesQuoteReview).where(SalesQuoteReview.quote_id==quote.id,SalesQuoteReview.decision=='approved'))
    resolution=db.scalar(select(SalesQuoteResolution).where(SalesQuoteResolution.quote_id==quote.id,SalesQuoteResolution.outcome=='activated',SalesQuoteResolution.actor_id==user.id))
    if not review or review.actor_id==quote.actor_id or not resolution:raise HTTPException(409,'报价预收回退缺少独立批准和客户确认事实')
    flow.file_exists(db,row,evidence_id,'signed_contract')
    excess=max(0,case_credit_amount(db,row.id)-quote.amount_cents)
    if not excess:return
    from .business_finance_service import authority
    with authority(db,user,{'admin','manager','sales'}):
        for original in db.scalars(select(FinanceCreditLink).where(FinanceCreditLink.case_id==row.id,FinanceCreditLink.amount_cents>0).order_by(FinanceCreditLink.id).with_for_update()):
            amount=min(excess,_credit_remaining(db,original))
            if amount<=0:continue
            previous=db.scalar(select(FinanceAdvanceEntry).where(FinanceAdvanceEntry.id==original.entry_id))
            advance=db.scalar(select(FinanceAdvance).where(FinanceAdvance.id==previous.advance_id).with_for_update())
            if advance.customer_id!=row.customer_id or advance.balance_cents+amount>advance.initial_cents:raise HTTPException(409,'原客户预收回退不守恒')
            advance.balance_cents+=amount;advance.updated_at=utcnow()
            entry=FinanceAdvanceEntry(advance_id=advance.id,case_id=row.id,purpose='return',amount_cents=amount,original_id=previous.id,evidence_id=evidence_id,actor_id=user.id)
            db.add(entry);db.flush()
            credit=FinanceCreditLink(case_id=row.id,entry_id=entry.id,application_id=original.application_id,original_id=original.id,amount_cents=-amount)
            db.add(credit);db.flush()
            db.add(SalesQuoteAdjustment(quote_id=quote.id,kind='advance_return',credit_id=credit.id,amount_cents=amount,evidence_id=evidence_id,actor_id=user.id))
            excess-=amount
            if not excess:break
        if excess:raise HTTPException(409,'原预收抵用正在其他退回方案中占用，不能重复回退')
        db.flush()
