"""Local immutable provenance for a new statement definition, never extra cash.

Central grants remain private to the source service. A receiving-store
manifest contains the original grant digest and its own classified quote,
not the original store's file identifiers, finances or customer contact.
"""
SOURCE_FIELDS={
 'rework_extensions':('request_id','store_id','definition_version','grant_id','grant_digest','actor_id','created_at'),
 'rework_quote_scopes':('quote_id','store_id','request_id','original_liability_cents','customer_extra_cents','digest'),
 'rework_line_scopes':('line_id','store_id','quote_id','charge_scope','source_line_id'),
}
SOURCE_KEYS={'rework_extensions':'request_id','rework_quote_scopes':'quote_id','rework_line_scopes':'line_id'}
FROZEN_FIELDS={name:tuple(k for k in fields if k!='store_id') for name,fields in SOURCE_FIELDS.items()}
JSON_FIELDS={}
DATETIME_FIELDS={'rework_extensions':('created_at',)}
CURRENT_NAMES=set(SOURCE_FIELDS)
PERIOD_NAMES=set()

def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        if entry['basis']!='current' or set(entry['data'])!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('原责任返修冻结来源字段或时点口径不一致')
    # These prove a responsibility split. Existing repair allocation, stock and
    # cash sources retain their single authoritative economic amounts.
    return result

def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('原责任返修冻结摘要与本店原来源不一致')
