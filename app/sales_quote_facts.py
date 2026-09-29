"""Read-only facts for the original authorized sales detail, not a second workflow.

The Runtime consumes this projection through its normal scoped GET. No adapter
receives a database handle, and no fact lookup writes or confirms an operation.
Absent privileges or incomplete evidence are unknown, not a negative decision.
"""
from fastapi import HTTPException
from sqlalchemy import select

from . import flow_engine as flow
from .flow_models import FileAsset, FlowEvent, Task, VehicleHold
from .sales_quote_models import SalesQuoteConsent, SalesQuoteResolution

FACT_KEYS = ('sales.active_quote_approved', 'sales.active_quote_consented',
             'sales.delivery_recorded')


def _positive(value):
    return type(value) is int and value > 0


def _signed_source(db, user, row, evidence_id, kind):
    """Re-use the native signature/fingerprint/scan guards under this employee."""
    from .flow_documents import can_file, fingerprint, verify_signed
    if not _positive(evidence_id):
        return None
    signed = flow.scoped_get(db, FileAsset, evidence_id)
    if not signed or signed.case_id != row.id or not can_file(user, row, signed):
        return None
    source = (flow.scoped_get(db, FileAsset, signed.source_file_id)
              if _positive(signed.source_file_id) else None)
    if not source or source.case_id != row.id or not can_file(user, row, source):
        return None
    try:
        verify_signed(db, row, evidence_id, kind, user=user)
    except HTTPException as exc:
        # A missing, superseded or quarantined file is not proof of an unsigned
        # customer or an undelivered vehicle. Do not expose attachment errors.
        if exc.status_code in {401, 403, 404, 409, 422, 503}:
            return None
        raise
    if not source.snapshot or fingerprint(source.snapshot) != source.source_fingerprint:
        return None
    return source


def project_facts(db, user, row):
    """Only call after get_case; use the same read/financial/file visibility."""
    from .sales_quote_service import active, is_quoted, pending, review, vehicle_model
    facts = {key: None for key in FACT_KEYS}
    result = {'schema_version': 1, 'case_version': row.version,
              'active_quote_id': row.data.get('active_quote_id'),
              'pending_quote_id': row.data.get('pending_quote_id'), 'facts': facts}
    if not is_quoted(row) or not flow.money_visible(user, row):
        return result
    # Never let the previous signed version satisfy a newly pending intention.
    # Withdrawing that revision restores the old active quote's original facts.
    if pending(db, row):
        return result
    quote = active(db, row)
    if quote is None:
        facts.update({key: False for key in FACT_KEYS})
        return result
    approval = review(db, quote)
    resolution = db.scalar(select(SalesQuoteResolution).where(
        SalesQuoteResolution.store_id == row.store_id,
        SalesQuoteResolution.quote_id == quote.id))
    if approval is None or resolution is None:
        return result
    facts[FACT_KEYS[0]] = (approval.store_id == row.store_id
        and approval.decision == 'approved' and approval.actor_id != quote.actor_id
        and resolution.outcome == 'activated')
    if not facts[FACT_KEYS[0]]:
        return result

    consent_id = row.data.get('sales_consent_id')
    signed_id = row.data.get('signed_file')
    if not _positive(consent_id) or not _positive(signed_id) or not _positive(row.vehicle_id):
        facts[FACT_KEYS[1]] = False
    else:
        consent = flow.scoped_get(db, SalesQuoteConsent, consent_id)
        if consent is not None:
            if (consent.quote_id, consent.vehicle_id, consent.evidence_id) != (quote.id, row.vehicle_id, signed_id):
                facts[FACT_KEYS[1]] = False
            else:
                source = _signed_source(db, user, row, signed_id, 'contract')
                if source and (consent.source_file_id, consent.fingerprint) == (source.id, source.source_fingerprint):
                    try:
                        facts[FACT_KEYS[1]] = vehicle_model(db, row.vehicle_id) == quote.model_id
                    except HTTPException as exc:
                        if exc.status_code not in {404, 409, 422}: raise

    handover_id = row.data.get('handover_file')
    if not _positive(handover_id):
        facts[FACT_KEYS[2]] = False
        return result
    # A successful native deliver persists the task, event, vehicle hold and
    # exact uploaded handover in the same transaction. No timestamp guess and
    # no "dispatch/paid/task done means delivered" shortcut is sufficient.
    if facts[FACT_KEYS[1]] is not True:
        return result
    task = db.scalar(select(Task).where(Task.store_id == row.store_id,
        Task.case_id == row.id, Task.key == 'deliver'))
    hold = db.scalar(select(VehicleHold).where(VehicleHold.store_id == row.store_id,
        VehicleHold.case_id == row.id, VehicleHold.vehicle_id == row.vehicle_id))
    if (not task or task.status != 'done' or not task.done_by or not task.done_at
            or not hold or hold.delivered is not True):
        return result
    event = db.scalar(select(FlowEvent).where(FlowEvent.store_id == row.store_id,
        FlowEvent.case_id == row.id, FlowEvent.action == 'deliver',
        FlowEvent.actor_id == task.done_by).order_by(FlowEvent.id.desc()).limit(1))
    if (not event or type(event.detail) is not dict or event.after_state != 'delivered'
            or type(event.detail.get('evidence_id')) is not int
            or event.detail['evidence_id'] != handover_id
            or type(event.detail.get('flow_version')) is not int
            or event.detail['flow_version'] != row.flow_version):
        return result
    if _signed_source(db, user, row, handover_id, 'handover') is not None:
        facts[FACT_KEYS[2]] = True
    return result
