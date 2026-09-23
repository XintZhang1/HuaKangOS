"""Local approved membership prices are provenance, not a second revenue source."""

SOURCE_FIELDS={
 'member_pricing_rules':('id','store_id','case_id','code','rule_version','name','enabled','membership_rule_id','membership_snapshot','reference_tier_id','reference_tier_snapshot','starts_on','ends_on','stack_mode','reason','digest','actor_id','created_at'),
 'member_pricing_scopes':('id','store_id','rule_id','sequence','business_kind','component','source_id','source_snapshot','basis_points','bundle_rule_id','bundle_snapshot','allow_contract_pricing'),
 'member_pricing_decisions':('id','store_id','rule_id','decision','reason','evidence_id','actor_id','created_at'),
 'member_pricing_snapshots':('id','store_id','case_id','quote_kind','quote_id','rule_id','customer_id','member_id','period_id','definition_version','contract','digest','actor_id','created_at'),
 'member_pricing_lines':('id','store_id','snapshot_id','line_key','component','source_id','scope_id','charge_scope','basis_cents','member_discount_cents','manual_discount_cents','net_cents','carry_cents','basis_points'),
 'member_pricing_authorizations':('id','store_id','snapshot_id','evidence_id','snapshot_digest','actor_id','created_at'),
}
CURRENT_NAMES=set(SOURCE_FIELDS)
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id'}) for name,fields in SOURCE_FIELDS.items()}
JSON_FIELDS={
 'member_pricing_rules':('membership_snapshot','reference_tier_snapshot'),
 'member_pricing_scopes':('source_snapshot','bundle_snapshot'),
 'member_pricing_snapshots':('contract',),
}
DATETIME_FIELDS={name:('created_at',) for name,fields in SOURCE_FIELDS.items() if 'created_at' in fields}


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        if entry['basis']!='current' or set(entry['data'])!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('会员价格冻结来源字段或时点口径不一致')
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('会员价格冻结摘要与原来源不一致')
