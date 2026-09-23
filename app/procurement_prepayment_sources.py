"""Frozen v24i facts shared by source events, restore and new statement adapters."""
from datetime import datetime
import hashlib,json

SOURCE_FIELDS={
 'procurement_prepayment_facilities':('id','store_id','actor_id','evidence_id','created_at'),
 'procurement_prepayment_requests':('id','store_id','case_id','amount_cents','valid_until','requested_by','evidence_id','reason','created_at'),
 'procurement_prepayment_decisions':('id','store_id','request_id','action','actor_id','evidence_id','reason','created_at'),
 'procurement_prepayment_disbursements':('id','store_id','request_id','payment_id','actor_id','created_at'),
 'procurement_payment_allocations':('id','store_id','case_id','payment_id','receipt_id','amount_cents','original_id','return_posting_id','actor_id','created_at'),
}


def digest(table,record):
    values={k:record[k] if isinstance(record,dict) else getattr(record,k) for k in SOURCE_FIELDS[table]}
    values={k:datetime.fromisoformat(str(v)).isoformat() if k.endswith('_at') else v for k,v in values.items()}
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
