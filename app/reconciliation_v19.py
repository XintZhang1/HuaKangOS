"""Frozen local mixed-package sources; original cash/stock rows remain authoritative."""

SOURCE_FIELDS={'repair_package_quote_snapshots': ('id', 'store_id', 'case_id', 'quote_id', 'contract', 'digest', 'actor_id', 'occurred_at'),
 'repair_package_purchase_events': ('id', 'store_id', 'purchase_id', 'action', 'digest', 'actor_id', 'occurred_at'),
 'repair_package_reservation_links': ('id',
                                      'store_id',
                                      'hold_id',
                                      'case_id',
                                      'quote_id',
                                      'amount_cents',
                                      'recognized_cents',
                                      'status',
                                      'version',
                                      'created_at',
                                      'updated_at'),
 'repair_package_payment_links': ('id', 'store_id', 'case_id', 'entry_id', 'purpose', 'amount_cents', 'recognized_cents', 'actor_id', 'occurred_at'),
 'repair_package_settlements': ('id', 'store_id', 'entry_id', 'side', 'amount_cents', 'actor_id', 'occurred_at'),
 'repair_package_refunds': ('id',
                            'store_id',
                            'purchase_id',
                            'case_id',
                            'selections',
                            'amount_cents',
                            'status',
                            'approved_by',
                            'cash_id',
                            'version',
                            'requested_by',
                            'reason',
                            'created_at',
                            'updated_at'),
 'repair_package_aftercare_holds': ('id',
                                    'store_id',
                                    'aftercare_case_id',
                                    'source_case_id',
                                    'plan_id',
                                    'original_id',
                                    'spans',
                                    'quantity_milli',
                                    'credit_cents',
                                    'paid_cents',
                                    'settlement_cents',
                                    'status',
                                    'version',
                                    'created_at',
                                    'updated_at'),
 'repair_package_stock_returns': ('id',
                                  'store_id',
                                  'hold_id',
                                  'original_stock_id',
                                  'stock_fact_id',
                                  'quantity_milli',
                                  'value_cents',
                                  'actor_id',
                                  'occurred_at')}
CURRENT_NAMES=set(SOURCE_FIELDS)
FROZEN_FIELDS={name:tuple(k for k in fields if k not in {'id','store_id','status','version','updated_at','approved_by','cash_id'}) for name,fields in SOURCE_FIELDS.items()}
JSON_FIELDS={'repair_package_quote_snapshots':('contract',),'repair_package_refunds':('selections',),'repair_package_aftercare_holds':('spans',)}
DATETIME_FIELDS={name:tuple(k for k in fields if k in {'created_at','occurred_at'}) for name,fields in SOURCE_FIELDS.items()}


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        if entry['basis']!='current' or set(entry['data'])!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('混合维修套餐冻结来源字段或时点口径不一致')
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('混合维修套餐冻结摘要与原来源不一致')
