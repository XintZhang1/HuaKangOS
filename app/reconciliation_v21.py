"""Same-amount membership fee corrections are local sources, never new fee income."""

SOURCE_FIELDS={
 'membership_fee_correction_requests':('id','store_id','case_id','fee_id','original_cash_id','original_account_id','account_id','reference','amount_cents','business_date','source_version','refunded_fee_id','created_at'),
 'membership_fee_corrections':('id','store_id','request_id','case_id','fee_id','original_cash_id','reversing_cash_id','corrected_cash_id','evidence_id','actor_id','occurred_at'),
 'membership_fee_refund_bases':('id','store_id','refund_fee_id','original_fee_id','original_cash_id','created_at'),
}
CURRENT_NAMES=set(SOURCE_FIELDS)
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id'}) for name,fields in SOURCE_FIELDS.items()}
DATETIME_FIELDS={
 'membership_fee_correction_requests':('created_at',),
 'membership_fee_corrections':('occurred_at',),
 'membership_fee_refund_bases':('created_at',),
}


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        if entry['basis']!='current' or set(entry['data'])!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('续会费更正冻结来源字段或时点口径不一致')
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('续会费更正冻结摘要与原来源不一致')
