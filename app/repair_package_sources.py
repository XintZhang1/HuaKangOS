"""Only local original records enter the receiving store's statement."""
SOURCE_FIELDS={
 'repair_package_quote_snapshots':('id','store_id','case_id','quote_id','contract','digest','actor_id','occurred_at'),
 'repair_package_purchase_events':('id','store_id','purchase_id','action','digest','actor_id','occurred_at'),
 'repair_package_reservation_links':('id','store_id','hold_id','case_id','quote_id','amount_cents','recognized_cents','status','version','created_at','updated_at'),
 'repair_package_payment_links':('id','store_id','case_id','entry_id','purpose','amount_cents','recognized_cents','actor_id','occurred_at'),
 'repair_package_settlements':('id','store_id','entry_id','side','amount_cents','actor_id','occurred_at'),
 'repair_package_refunds':('id','store_id','purchase_id','case_id','selections','amount_cents','status','approved_by','cash_id','version','requested_by','reason','created_at','updated_at'),
 'repair_package_aftercare_holds':('id','store_id','aftercare_case_id','source_case_id','plan_id','original_id','spans','quantity_milli','credit_cents','paid_cents','settlement_cents','status','version','created_at','updated_at'),
 'repair_package_stock_returns':('id','store_id','hold_id','original_stock_id','stock_fact_id','quantity_milli','value_cents','actor_id','occurred_at'),
}
SOURCE_KEYS={name:'id' for name in SOURCE_FIELDS}
SOURCE_BASIS={name:'current' for name in SOURCE_FIELDS}
# Provenance summaries do not count these links as new cash or second revenue.
SOURCE_AMOUNT_FIELDS={name:None for name in SOURCE_FIELDS}
