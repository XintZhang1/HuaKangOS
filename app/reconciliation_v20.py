"""Retained real refunds explain corrected gross cash versus remaining allocation."""

SOURCE_FIELDS={
 'business_finance_correction_bases':('id','store_id','case_id','original_cash_id','previous_id','original_amount_cents','corrected_amount_cents','refunded_cents','created_at'),
 'business_finance_correction_refund_slices':('id','store_id','basis_id','refund_payment_id','original_payment_id','source_case_id','amount_cents','created_at'),
}
CURRENT_NAMES=set(SOURCE_FIELDS)
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id'}) for name,fields in SOURCE_FIELDS.items()}
DATETIME_FIELDS={name:('created_at',) for name in SOURCE_FIELDS}


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        if entry['basis']!='current' or set(entry['data'])!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('已退款原款更正冻结来源字段或时点口径不一致')
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('已退款原款更正冻结摘要与原来源不一致')
