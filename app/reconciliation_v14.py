"""V14 freezes the separately approved original supplier overpayment refunds."""
SOURCE_FIELDS={'business_finance_supplier_refunds':('id','store_id','case_id','receivable_id','original_payment_id','amount_cents','status','applied_batch_id','version','created_at','updated_at')}
FROZEN_FIELDS={'business_finance_supplier_refunds':('case_id','receivable_id','original_payment_id','amount_cents','created_at')}
DATETIME_FIELDS={'business_finance_supplier_refunds':('created_at',)}
CURRENT_NAMES=set(SOURCE_FIELDS)


def source_summary(entries):
    result={'count':len(entries),'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
    for entry in entries:
        data=entry['data']
        if entry['basis']!='current' or set(data)!=set(SOURCE_FIELDS[entry['source']]):
            raise ValueError('供应方超收原退来源字段或时点口径不一致')
        if type(data['amount_cents']) is not int or data['amount_cents']<=0:
            raise ValueError('供应方超收原退金额必须是正整数分')
        if data['status'] not in {'requested','reserved','applied','released'} or (data['status']=='applied')!=(data['applied_batch_id'] is not None):
            raise ValueError('供应方超收原退冻结状态与原过账不一致')
        result['amount_cents']+=data['amount_cents']
    return result


def validate_frozen_summary(manifest,summary):
    for name in SOURCE_FIELDS:
        if summary.get(name)!=source_summary([e for e in manifest if e['source']==name]):
            raise ValueError('供应方超收原退冻结摘要与原来源不一致')
