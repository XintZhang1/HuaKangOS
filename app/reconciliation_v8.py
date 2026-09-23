"""Frozen v8 local transport loss and recovery sources; old 1–7 stay unchanged.

Physical findings and the other store's files remain in their original domain.
Statements include only the current store's immutable loss, liability, approved
recovery source and actual cash linkage. Amounts across these books are separate.
"""

PERIOD_NAMES={'transfer_loss_postings','transfer_recovery_payments'}
CURRENT_NAMES={'transfer_loss_settlements','transfer_recovery_claims','transfer_recovery_plans',
               'transfer_recovery_reviews','transfer_recovery_cancellations'}
FROZEN_FIELDS={
    'transfer_loss_postings':('exception_id','transfer_id','line_id','original_id','plan_id','quantity_milli','value_cents',
        'source_bearer_cents','destination_bearer_cents','evidence_id','actor_id','business_date'),
    'transfer_loss_settlements':('transfer_id','posting_id','exception_id','counterparty_store_id','amount_cents','business_date'),
    'transfer_recovery_claims':('exception_id','counterparty_kind','supplier_id','insurer_id','counterparty_snapshot','requested_by'),
    'transfer_recovery_plans':('claim_id','revision','target_cents','due_date','reason','evidence_id','actor_id'),
    'transfer_recovery_reviews':('plan_id','decision','reason','evidence_id','actor_id','business_date'),
    'transfer_recovery_cancellations':('plan_id','reason','evidence_id','actor_id'),
    'transfer_recovery_payments':('claim_id','plan_id','original_id','direction','amount_cents','account_id','reference',
        'cash_id','evidence_id','actor_id','business_date')}
JSON_FIELDS={'transfer_recovery_claims':('counterparty_snapshot',)}


def validate_frozen_summary(manifest,summary,start,end):
    """Check the frozen subset itself, without expanding it with later facts."""
    for name in PERIOD_NAMES|CURRENT_NAMES:
        entries=[entry for entry in manifest if entry['source']==name]
        expected={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
        for entry in entries:
            data=entry['data'];basis='period' if name in PERIOD_NAMES else 'current'
            if entry['basis']!=basis:raise ValueError('冻结运输来源期间或时点口径不一致')
            if basis=='period' and not start<=data.get('business_date','')<=end:raise ValueError('冻结运输来源日期不在原期间内')
            expected['amount_cents']+=data.get('amount_cents',0)*(-1 if data.get('direction')=='out' else 1)
            expected['value_cents']+=data.get('value_cents',0)
            if 'quantity_milli' in data:expected['quantity_milli_by_item'][name+':'+str(entry['source_id'])]=data['quantity_milli']
        if summary.get(name)!=expected:raise ValueError('冻结运输损失或追偿摘要与原条目集合不一致')
