"""Statement v13: original receipt corrections and supplier advance evidence.

These are current original-source associations, not extra cash or revenue.
Actual cash stays in cash_entries; reservations and receipt allocations do not
create payments. Published definitions 1--12 keep their original source sets.
"""

SOURCE_FIELDS={
 'business_finance_stored_correction_requests':('id','store_id','case_id','source_kind','advance_id','member_id','topup_id','original_cash_id','original_amount_cents','corrected_amount_cents','reserved_cents','status','version','created_at','updated_at'),
 'business_finance_stored_corrections':('id','store_id','request_id','case_id','original_cash_id','reversing_cash_id','corrected_cash_id','advance_entry_id','group_entry_id','evidence_id','actor_id','occurred_at'),
 'business_finance_return_target_revisions':('id','store_id','case_id','receivable_id','revision','previous_id','original_amount_cents','amount_cents','received_cents','received_payment_ids','evidence_id','actor_id','occurred_at'),
 'procurement_prepayment_facilities':('id','store_id','actor_id','evidence_id','created_at'),
 'procurement_prepayment_requests':('id','store_id','case_id','amount_cents','valid_until','requested_by','evidence_id','reason','created_at','status','version','updated_at'),
 'procurement_prepayment_decisions':('id','store_id','request_id','action','actor_id','evidence_id','reason','created_at'),
 'procurement_prepayment_disbursements':('id','store_id','request_id','payment_id','actor_id','created_at'),
 'procurement_payment_allocations':('id','store_id','case_id','payment_id','receipt_id','amount_cents','original_id','return_posting_id','actor_id','created_at'),
}
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id','status','version','updated_at'}) for name,fields in SOURCE_FIELDS.items()}
JSON_FIELDS={'business_finance_return_target_revisions':('received_payment_ids',)}
DATETIME_FIELDS={name:tuple(k for k in fields if k in {'created_at','occurred_at'}) for name,fields in FROZEN_FIELDS.items()}
CURRENT_NAMES=set(SOURCE_FIELDS)
PERIOD_NAMES=set()


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        name=entry['source'];data=entry['data']
        if entry['basis']!='current' or set(data)!=set(SOURCE_FIELDS[name]):
            raise ValueError('冻结更正或预付款来源字段、时点口径不一致')
        # A source-local amount only. Never sum these over cash or over tables.
        value=data.get('amount_cents',0)
        if type(value) is not int:raise ValueError('冻结更正或预付款金额必须是整数分')
        result['amount_cents']+=value
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('冻结更正或预付款摘要与原来源不一致')
