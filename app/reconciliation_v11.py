"""V11 freezes local return-search sources without a second economic posting.

All four sets are generation-time workflow associations. Physical observations
and actual original cost restoration still belong to the v9 original ledgers.
A previous return search is never silently inserted into a v1--10 statement.
"""
FROZEN_FIELDS = {
    'transfer_goods_searches': ('recovery_id', 'revision', 'requested_by',
        'evidence_id', 'reason', 'business_date'),
    'transfer_goods_search_reviews': ('search_id', 'decision', 'actor_id',
        'evidence_id', 'reason', 'business_date'),
    'transfer_goods_search_outcomes': ('search_id', 'kind', 'review_id',
        'receive_fact_id', 'actor_id', 'business_date'),
    'transfer_goods_reappearances': ('previous_recovery_id', 'search_id',
        'recovery_id', 'quantity_milli', 'evidence_id', 'actor_id', 'business_date'),
}
PERIOD_NAMES = set()
CURRENT_NAMES = set(FROZEN_FIELDS)


def source_summary(entries):
    result = {'count': len(entries), 'amount_cents': 0, 'value_cents': 0,
        'quantity_milli_by_item': {}, 'units_by_kind': {}}
    for entry in entries:
        name, data = entry['source'], entry['data']
        if entry['basis'] != 'current' or set(data) != {
            'id', 'store_id', 'case_id', 'created_at', *FROZEN_FIELDS[name]}:
            raise ValueError('冻结原退运查找来源字段或生成时点口径不一致')
        if name == 'transfer_goods_reappearances':
            quantity = data['quantity_milli']
            if type(quantity) is not int or quantity <= 0:
                raise ValueError('冻结再次找到数量必须为正整数原单位')
            # One attributed observation, not a stock movement or SKU total.
            result['quantity_milli_by_item'][name + ':' + str(entry['source_id'])] = quantity
    return result


def validate_frozen_summary(manifest, summary, start, end):
    for name in CURRENT_NAMES:
        if summary.get(name) != source_summary([e for e in manifest if e['source'] == name]):
            raise ValueError('冻结原退运查找摘要与原条目不一致；查找不增加损失、库存或现金')
