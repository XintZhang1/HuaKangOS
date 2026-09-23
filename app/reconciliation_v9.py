"""Frozen v9 local found-goods facts and their original financial links.

A physical finding is not a stock receipt. Only GoodsPosting restores original
inventory value. Settlements reverse internal liability, not cash. GoodsRefund
links to an existing actual recovery payment; it must never add a second cash
entry. Preserve versions 1--8 and do not expand historical snapshots at restore.
"""

PERIOD_NAMES = {'transfer_goods_facts', 'transfer_goods_postings'}
CURRENT_NAMES = {'transfer_goods_reviews', 'transfer_goods_settlements',
                 'transfer_goods_terms', 'transfer_goods_refunds'}
FROZEN_FIELDS = {
    'transfer_goods_facts': ('recovery_id', 'kind', 'passed', 'quantity_milli',
        'result', 'evidence_id', 'actor_id', 'business_date'),
    'transfer_goods_postings': ('recovery_id', 'loss_id', 'plan_id',
        'found_quantity_milli', 'restored_quantity_milli', 'value_cents',
        'source_reverse_cents', 'destination_reverse_cents', 'stock_move_id',
        'evidence_id', 'actor_id', 'business_date'),
    'transfer_goods_reviews': ('plan_id', 'decision', 'actor_id', 'evidence_id', 'reason'),
    'transfer_goods_settlements': ('transfer_id', 'recovery_id', 'posting_id',
        'original_id', 'counterparty_store_id', 'amount_cents', 'business_date'),
    'transfer_goods_terms': ('recovery_id', 'claim_id', 'previous_plan_id', 'plan_id'),
    'transfer_goods_refunds': ('recovery_id', 'terms_id', 'payment_id'),
}


def validate_frozen_summary(manifest, summary, start, end):
    """Validate the frozen subset, never substitute later live facts for it.

    Original-field equality and tenant checks are performed by the caller.
    Counts and amounts are separate books, not an additive business total.
    The digest is an integrity check, not a signature against an administrator
    who can rewrite both a database and all of its verification metadata.
    """
    for name in PERIOD_NAMES | CURRENT_NAMES:
        entries = [entry for entry in manifest if entry['source'] == name]
        expected = {'count': len(entries), 'amount_cents': 0, 'value_cents': 0,
                    'quantity_milli_by_item': {}, 'units_by_kind': {}}
        for entry in entries:
            data = entry['data']
            basis = 'period' if name in PERIOD_NAMES else 'current'
            if entry['basis'] != basis:
                raise ValueError('冻结找回来源期间或时点口径不一致')
            if basis == 'period' and not start <= data.get('business_date', '') <= end:
                raise ValueError('冻结找回来源日期不在原期间内')
            expected['amount_cents'] += data.get('amount_cents', 0)
            expected['value_cents'] += data.get('value_cents', 0)
            if 'quantity_milli' in data:
                # Physical observations may repeat across workflow stages.
                # Keep distinct fact IDs; these are NOT inventory quantities.
                expected['quantity_milli_by_item'][name + ':' + str(entry['source_id'])] = data['quantity_milli']
        if summary.get(name) != expected:
            raise ValueError('冻结原物资找回摘要与原条目集合不一致')
