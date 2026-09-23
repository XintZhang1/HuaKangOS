"""Statement v17 freezes original recharge-bundle correction associations.

Postings and original per-component deltas reconstruct corrected issuance.
They are neither a second cash source nor new customer/service revenue.
"""
SOURCE_FIELDS={
 'business_finance_bundle_corrections':('id','store_id','request_id','purchase_id','rule_id','original_shares','corrected_shares','created_at'),
 'business_finance_bundle_correction_components':('id','store_id','correction_id','component_id','wallet_id','grant_entry_id','units_per_share','delta_units','expires_on','created_at'),
 'business_finance_bundle_correction_postings':('id','store_id','component_id','benefit_entry_id','created_at'),
}
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id'}) for name,fields in SOURCE_FIELDS.items()}
DATETIME_FIELDS={name:('created_at',) for name in SOURCE_FIELDS}
CURRENT_NAMES=set(SOURCE_FIELDS)


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        if entry['basis']!='current' or set(entry['data'])!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('原充值组合更正冻结来源字段或时点口径不一致')
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('原充值组合更正冻结摘要与原来源不一致')
