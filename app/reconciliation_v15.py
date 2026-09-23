"""Statement v15: original supplier vehicle income; each cash fact links once.

Frozen target revisions are evidence, not additional revenue or money. Current
source sets preserve rejected/withdrawn targets. Cash uses its actual date.
Idempotency response caches are not a financial statement source.
"""
SOURCE_FIELDS={
 'vehicle_income_orders':('id','store_id','supplier_id','supplier_snapshot','external_reference','primary_source_case_id','reason','actor_id'),
 'vehicle_income_sources':('id','store_id','case_id','source_case_id','source_version','vehicle_id','snapshot','digest'),
 'vehicle_income_revisions':('id','store_id','case_id','revision','previous_id','previous_cents','target_cents','invoice_mode','due_date','source_versions','reason','evidence_id','digest','actor_id','created_at'),
 'vehicle_income_decisions':('id','store_id','revision_id','decision','reason','evidence_id','business_date','actor_id','created_at'),
 'vehicle_income_cash':('id','store_id','case_id','revision_id','original_id','direction','amount_cents','cash_id','account_id','account_snapshot','reference','business_date','evidence_id','actor_id','created_at'),
}
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id'}) for name,fields in SOURCE_FIELDS.items()}
JSON_FIELDS={'vehicle_income_orders':('supplier_snapshot',),'vehicle_income_sources':('snapshot',),'vehicle_income_revisions':('source_versions',),'vehicle_income_cash':('account_snapshot',)}
DATETIME_FIELDS={name:('created_at',) for name in ('vehicle_income_revisions','vehicle_income_decisions','vehicle_income_cash')}
PERIOD_NAMES={'vehicle_income_cash'}
CURRENT_NAMES=set(SOURCE_FIELDS)-PERIOD_NAMES


def source_summary(entries,start,end):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        name=entry['source'];data=entry['data']
        if set(data)!=set(SOURCE_FIELDS[name]) or entry['basis']!=('period' if name in PERIOD_NAMES else 'current'):
            raise ValueError('整车其他收入冻结来源字段或时点口径不一致')
        if name in PERIOD_NAMES:
            if not start<=data['business_date']<=end or type(data['amount_cents']) is not int or data['amount_cents']<=0 or data['direction'] not in {'in','out'}:
                raise ValueError('整车其他收入现金来源期间、方向或整数金额不一致')
            result['amount_cents']+=data['amount_cents']*(1 if data['direction']=='in' else -1)
    return result


def validate_frozen_summary(manifest,summary,start,end):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name],start,end):
            raise ValueError('整车其他收入冻结摘要与原来源不一致')
