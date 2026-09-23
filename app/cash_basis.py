"""Read the effective actual collections without turning bookkeeping corrections into cash."""
from .business_finance_service import superseded_cash_ids,adjustment_cash_ids
from sqlalchemy import select
from .business_finance_models import FinanceCorrection,FinanceCashBatch,FinanceStoredCorrection


def excluded_cash_ids(db,definition_version=7):
    if definition_version in {3,4,5}:
        # Published statements 3--12 predate stored-principal corrections.
        # Definitions through 5 predate explicit gross/refunded/net cash slices.
        from .business_finance_partial_corrections import partial_correction_case_ids
        partial_cases=partial_correction_case_ids(db)
        excluded=set(db.scalars(select(FinanceCorrection.original_cash_id).where(FinanceCorrection.case_id.notin_(partial_cases))))|set(db.scalars(
            select(FinanceCashBatch.cash_id).where(FinanceCashBatch.kind=='correction_reverse',FinanceCashBatch.case_id.notin_(partial_cases))))
        if definition_version>=4:
            # Statements 13--16 freeze ordinary topups/advances, not the new
            # original-bundle correction contract introduced by statement 17.
            from .business_finance_bundle_corrections import bundle_correction_case_ids
            excluded_cases=bundle_correction_case_ids(db) if definition_version==4 else set()
            for entry in db.scalars(select(FinanceStoredCorrection).where(FinanceStoredCorrection.case_id.notin_(excluded_cases))):
                excluded.update((entry.original_cash_id,entry.reversing_cash_id))
        return excluded
    if definition_version not in {6,7}:raise ValueError('不支持的现金统计定义版本')
    excluded=superseded_cash_ids(db)|adjustment_cash_ids(db)
    if definition_version>=7:
        from .membership_fee_corrections import excluded_cash_ids as excluded_membership_fee_cash
        excluded|=excluded_membership_fee_cash(db)
    return excluded


def effective_cash(db,rows,definition_version=7):
    if definition_version in {1,2}:return rows
    excluded=excluded_cash_ids(db,definition_version)
    return [row for row in rows if row.id not in excluded]
